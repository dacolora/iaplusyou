"""
Alertas del proyecto: todo lo que necesita la atención de la persona, en un
solo lugar (pestaña Alertas). Spec: docs/superpowers/specs/2026-09-20-alertas-design.md
(§12 «Rescate del 2026-10-02» manda donde difiere de las secciones viejas).

Regla de oro: NADA se almacena salvo los descartes. Cada alerta se calcula al
vuelo desde el estado real (llaves, tablas, archivos del proyecto), así nunca
hay una alerta vieja que ya no corresponda: si algo se resuelve, desaparece
sola. Cada fuente (FUENTES) corre en su propio try/except: si una revienta
sale una alerta `revision:<fuente>` con SOLO el nombre de la clase de la
excepción (nunca el mensaje, que podría arrastrar un token) y el resto se
calcula igual.

Una alerta es un dict (spec §1) con `clave` estable (`<fuente>:<tipo>[:<entidad>]`)
y `huella` (sha256 de la situación): un descarte vive mientras la alerta
exista con esa misma huella; si cambia la situación, vuelve a mostrarse; si
la alerta desaparece, `visibles` poda el descarte. Las que llevan
`solo_admin` (las llaves del .env, el worker y el enlace de recarga del saldo
son de Creatv) no las ve un cliente.

Idioma: los títulos y detalles se arman con `gettext` al calcular (así salen
en el idioma de quien mira); los nombres de grupo, nivel y pestaña son
constantes `idiomas.N_` que la plantilla traduce con `|traducir`.

Ningún valor de llave sale de aquí; los textos de error que llegan a una
alerta pasan por `_limpio` (monitoreo.limpiar_texto: tokens, Bearer, sk-…, secret=, password=…). Nada de aquí
gasta, encola, publica ni llama a un proveedor. Sin rutas ni app de Flask
(solo `gettext`, que fuera de una petición devuelve el español): lo importan
dashboard.py y los tests. El ÚNICO escritor de `alerta_descartada` es este
módulo.
"""
import hashlib
import os
import re
from datetime import datetime, timedelta
from urllib.parse import quote

import sqlalchemy as sa
from flask_babel import gettext, ngettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
import idiomas
import monitoreo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NIVELES = ("bloquea", "atencion", "info")
GRUPOS = ("puesta_a_punto", "faltantes", "decision", "fallos")
NOMBRES_GRUPO = {"puesta_a_punto": idiomas.N_("Puesta a punto pendiente"), "faltantes": idiomas.N_("Faltantes del proyecto"),
                 "decision": idiomas.N_("Esperan tu decisión"), "fallos": idiomas.N_("Fallos y errores")}
NOMBRES_NIVEL = {"bloquea": idiomas.N_("bloquea"), "atencion": idiomas.N_("atención"), "info": idiomas.N_("info")}
NOMBRES_TAB = {"settings": idiomas.N_("Configuración"), "catalogo": idiomas.N_("Catálogo"), "creativeflowplus": idiomas.N_("Crear"),
               "experimentos": idiomas.N_("Experimentos"), "sprints": idiomas.N_("Sprints"), "nicho": idiomas.N_("Nicho")}

MINUTOS_WORKER = 30                                  # más de esto sin señal de vida y el worker está parado
MINUTOS_PROMPT_LISTO = 60                            # un prompt listo más nuevo que esto no molesta: la persona sigue trabajando
DIAS_FALLOS = 30                                     # un fallo más viejo que esto es historia, no una alerta
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")      # lo que cuenta como logo en clientes/<c>/logos/

# Lo que las rutas aceptan al descartar/restaurar (una clave o huella que no
# calce no se guarda). La clave: `<fuente>:<tipo>[:<entidad>]`; la huella: sha256 hex.
CLAVE_VALIDA = r"^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$"
HUELLA_VALIDA = r"^[0-9a-f]{64}$"

# Claves de las alertas `solo_admin` (llaves del .env, worker, el enlace de
# recarga del saldo, fuentes caídas). Los descartes son del proyecto: si un
# cliente pudiera descartarlas, se las escondería al admin. Las rutas lo
# frenan con `es_solo_admin` (fix de la revisión de la Task 5, 2026-10-02);
# `tests/test_rutas_alertas.py` comprueba que toda alerta `solo_admin` que
# producen las fuentes empiece por uno de estos prefijos.
PREFIJOS_SOLO_ADMIN = ("llave:", "worker:", "revision:", "saldo:wavespeed_recarga")

# (nombre, función(cliente, ahora_iso) -> lista de alertas), en el orden en
# que se muestran dentro de un mismo grupo y nivel. Las fuentes reales se
# registran aquí; los tests lo reemplazan con fuentes falsas.
FUENTES = []


def huella(*partes):
    """sha256 hex de la «situación» de una alerta. Sin partes es la huella
    vacía: una constante para las alertas cuya situación no cambia."""
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def _alerta(clave, huella_, nivel, grupo, titulo, detalle, tab, ancla=None, url=None, entidad=None,
            solo_admin=False):
    """El constructor de toda alerta (spec §1). `solo_admin`: la ve solo un
    admin (llaves del .env, worker, fuentes caídas)."""
    if nivel not in NIVELES:
        raise ValueError(f"nivel inválido: {nivel}")
    if grupo not in GRUPOS:
        raise ValueError(f"grupo inválido: {grupo}")
    return {"clave": clave, "huella": huella_, "nivel": nivel, "grupo": grupo, "titulo": titulo,
            "detalle": detalle, "tab": tab, "ancla": ancla, "url": url, "entidad": entidad,
            "solo_admin": bool(solo_admin)}


def _minutos(desde_iso, ahora_iso):
    """Minutos entre dos ISO (None si alguno no se puede leer)."""
    try:
        return (datetime.fromisoformat(str(ahora_iso)[:19]) - datetime.fromisoformat(str(desde_iso)[:19])).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def _limpio(texto, n=200):
    """Texto de error apto para una alerta: sin tokens ni llaves y recortado a `n` (sin recorte si `n` es None; None
    es vacío). Lo limpia `monitoreo.limpiar_texto`, que además de los tokens en URLs de `cola.sin_token` cubre
    `Bearer …`, `sk-…`, `secret=`, `password=`…: el error de un proveedor llega aquí tal cual."""
    return monitoreo.limpiar_texto(texto, n)


def _hace(ahora_iso, **tiempo):
    """El ISO de 19 caracteres de `tiempo` (days=, minutes=) antes de `ahora_iso`: el borde con el que se compara,
    como texto, una columna de fecha de la base (todas guardan `YYYY-MM-DDTHH:MM:SS`)."""
    return (datetime.fromisoformat(str(ahora_iso)[:19]) - timedelta(**tiempo)).isoformat(timespec="seconds")


def _url_proyecto(cliente, *partes):
    """Ruta de una página propia del proyecto (`/cliente/<c>/…`) armada sin Flask: este módulo nunca importa
    `dashboard`, así que no puede usar `url_for`. `tests/test_alertas_fuentes.py` la compara con la ruta real."""
    return "/".join(("/cliente", quote(str(cliente), safe=""), *(str(p) for p in partes)))


def _con_error(error, accion):
    """«<error> <qué hacer>», o solo lo que hay que hacer si la fila no guardó el error."""
    return f"{error} {accion}" if error else accion


# ---------- fuentes: puesta a punto ----------
# Cada fuente es `fn(cliente, ahora_iso) -> lista de alertas`. Sus dependencias
# se importan adentro (como `tablero` o `organico`, que arrastran requests y el
# motor de experimentos): este módulo lo importan dashboard.py y los tests, y nunca
# debe importar `dashboard` (círculo).

def _fuente_llaves(cliente, ahora):
    """Una alerta por tarjeta de Puesta a punto que no esté configurada; la de
    Meta no (la cubre `tablero:meta_*`, que además sabe si está rota). Las
    llaves del .env son de Creatv: la ve solo un admin (`solo_admin`). Una
    tarjeta `opcional` es `info` (conviene, no urge). Solo nombres de
    variables: `llaves.estado` nunca entrega un valor."""
    import llaves  # noqa: PLC0415
    out = []
    for t in llaves.estado():
        if t["estado"] == "configurada" or t["id"] == "meta":
            continue
        faltan = list(t["faltan"])
        nombre, nota = t["nombre"], t["nota"]
        if t["estado"] == "falta":
            titulo = gettext("Falta la llave de %(nombre)s", nombre=nombre)
        else:
            titulo = gettext("Llave incompleta de %(nombre)s", nombre=nombre)
        detalle = gettext("Variables que faltan en el .env del servidor: %(variables)s. %(nota)s",
                          variables=", ".join(faltan), nota=nota)
        out.append(_alerta(f"llave:{t['id']}", huella(*faltan), "info" if t["opcional"] else "bloquea",
                           "puesta_a_punto", titulo, detalle, "settings", ancla=f"llave-{t['id']}", solo_admin=True))
    return out


def _fuente_cuentas(cliente, ahora):
    """Cuentas rol cliente del proyecto sin correo o con el correo sin
    confirmar: sin él no se conecta Meta ni una tienda
    (`_requiere_correo_verificado`). Son TODAS las cuentas del proyecto, no solo la de quien mira: cada cuenta del
    proyecto ve las alertas, el correo y el nombre de las demás cuentas cliente y puede descartarlas (los descartes
    son del proyecto). Hoy el alta web crea una cuenta por proyecto, así que solo afecta a las agregadas por la
    línea de comandos; filtrar por quien mira es una decisión pendiente (PND-123)."""
    import usuarios  # noqa: PLC0415
    out = []
    for u in usuarios.por_cliente(cliente):
        if u.get("correo_verificado"):
            continue
        nombre = u["usuario"]
        # La clave tiene que pasar CLAVE_VALIDA aunque la cuenta sea vieja y traiga
        # espacios o acentos (usuarios.validar_usuario solo exige el formato al crear).
        clave = f"cuenta:correo:{re.sub(r'[^A-Za-z0-9_.-]', '_', nombre)[:100]}"
        if not u.get("correo"):
            out.append(_alerta(clave, huella("sin_correo"), "bloquea", "puesta_a_punto",
                               gettext("La cuenta %(usuario)s no tiene correo", usuario=nombre),
                               gettext("Ponlo en Configuración › Cuenta para poder confirmarla y recuperar la contraseña. "
                                       "Sin correo confirmado no puedes conectar Meta ni una tienda."),
                               "settings", ancla="config-cuenta"))
        else:
            out.append(_alerta(clave, huella("sin_verificar", u["correo"]), "bloquea", "puesta_a_punto",
                               gettext("Confirma el correo de la cuenta %(usuario)s", usuario=nombre),
                               gettext("%(correo)s: abre el enlace que te mandamos o pide uno nuevo en Configuración › Cuenta. "
                                       "Sin correo confirmado no puedes conectar Meta ni una tienda.", correo=u["correo"]),
                               "settings", ancla="config-cuenta"))
    return out


def _senal_del_worker():
    """La señal de vida más reciente del worker (ISO de 19 caracteres) o None:
    lo más nuevo entre las marcas `ultimo_<tipo>` que su bucle escribe en `kv`
    al encolar sus periódicas (`worker.encolar_periodicas`) y la última tarea
    iniciada (el worker es de un solo hilo: una render larga lo tiene ocupado
    sin pasar por el bucle). Una consulta para cada fuente, sin importar
    cuántas marcas haya; un valor que no es una fecha no cuenta."""
    t = db.tarea
    with db.conectar() as con:
        marcas = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave.startswith("ultimo_", autoescape=True))).scalars().all()
        tarea = con.execute(sa.select(sa.func.max(t.c.iniciada_en))).scalar()
    candidatas = []
    for valor in (*marcas, tarea):
        try:
            candidatas.append((datetime.fromisoformat(str(valor)[:19]), str(valor)[:19]))
        except ValueError:      # None, vacío o basura: no es una señal
            continue
    return max(candidatas)[1] if candidatas else None


def _fuente_worker(cliente, ahora):
    """El worker parado: más de MINUTOS_WORKER sin señal de vida, o nunca. Es
    de Creatv, no del proyecto: `solo_admin`. Huella = esa señal, así cada
    caída nueva reaparece aunque la anterior se haya descartado."""
    ultima = _senal_del_worker()
    minutos = _minutos(ultima, ahora) if ultima else None
    if minutos is not None and minutos <= MINUTOS_WORKER:
        return []
    cuando = gettext("hace %(n)s min", n=int(minutos)) if minutos is not None else gettext("nunca")
    return [_alerta("worker:parado", huella(ultima or "nunca"), "bloquea", "puesta_a_punto",
                    gettext("El worker no está corriendo"),
                    gettext("Sin él no se genera, no se lanza ni se publica nada. Última actividad: %(cuando)s. "
                            "Revisa el servicio creatv-worker en el servidor.", cuando=cuando),
                    "settings", ancla="config-puesta-a-punto", solo_admin=True)]


def _fuente_saldo(cliente, ahora):
    """WaveSpeed sin saldo (`saldo.vigente`, el mismo aviso de Crear). DOS
    alertas con la misma huella (`desde`): la del cliente, neutra (la cuenta es
    de Creatv, no suya: sin enlace de recarga, sin respuesta del proveedor ni
    el proyecto que falló) y la del admin, con desde cuándo y dónde recargar."""
    import saldo  # noqa: PLC0415
    aviso = saldo.vigente("wavespeed")
    if not aviso:
        return []
    h = huella(aviso.get("desde"))
    desde = (aviso.get("desde") or "")[:16].replace("T", " ")
    return [
        _alerta("saldo:wavespeed", h, "bloquea", "puesta_a_punto",
                gettext("La generación de videos e imágenes está en pausa"),
                gettext("Hay un problema con el proveedor y ya le avisamos a Creatv. Vuelve a intentarlo en un rato: "
                        "los intentos fallidos no se cobran."),
                "creativeflowplus"),
        _alerta("saldo:wavespeed_recarga", h, "bloquea", "puesta_a_punto",
                gettext("%(proveedor)s se quedó sin saldo", proveedor=aviso["nombre"]),
                gettext("Desde el %(desde)s las generaciones de Crear y de Cambiar producto fallan (sin cobrar). "
                        "Recarga la cuenta en %(recarga)s; esta alerta se quita sola con la próxima generación que "
                        "salga bien.", desde=desde, recarga=aviso["recarga"]),
                "creativeflowplus", solo_admin=True),
    ]


# Las alertas del Tablero (tablero.alertas) NO se reescriben: solo se les pone
# clave, nivel y grupo. La única lógica de experimentos sigue en tablero.py.
_GRUPO_TABLERO = {"meta_sin_conectar": "puesta_a_punto", "meta_roto": "puesta_a_punto", "tienda_rota": "puesta_a_punto",
                  "pixel_sin_datos": "puesta_a_punto", "productos_sin_experimento": "faltantes",
                  "propuestas_pendientes": "decision", "tope_alcanzado": "decision", "ganador_sin_publicar": "decision",
                  "experimento_error": "fallos", "anuncios_rechazados": "fallos", "sin_metricas": "fallos", "pedidos_sin_atribuir": "fallos"}
_NIVEL_TABLERO = {"alta": "bloquea", "media": "atencion", "baja": "info"}


def _fuente_tablero(cliente, ahora):
    """`tablero.alertas` traducida a alertas: el texto del Tablero es el
    título, sin tokens (el de una tienda rota arrastra el error de su
    conector). Tope de 400 y no de 200: la guía de Meta en modo Desarrollo
    ronda los 330 caracteres y su llamado a la acción va al final; el error
    crudo de un conector sí queda acotado.

    La huella NO sale del texto: el texto viene traducido al idioma de quien
    mira, y un descarte es del proyecto (lo comparten un admin en español y un
    cliente en inglés): con el texto, el «Descartar» de uno no valdría para el
    otro y cada uno pisaría el del otro. Sale del tipo, el experimento y los
    números del texto en el orden en que aparecen (cuántas propuestas, cuánto
    gastado, el código de un error): «1.250» y «1,250» dan los mismos
    números. `sin_metricas` lleva huella vacía: su texto dice «lleva N h» y
    cambiaría cada hora, así que un descarte nunca serviría."""
    import tablero  # noqa: PLC0415
    out = []
    for a in tablero.alertas(cliente, ahora_iso=ahora):
        eid = a.get("experimento_id")
        entidad = a.get("tienda_id") if a["tipo"] == "tienda_rota" else eid
        texto = _limpio(a["texto"], 400)
        # Los números salen del texto entero y limpio, no del recortado a 400: un texto que se corta en un idioma y
        # en el otro no tiene que cambiar la huella.
        numeros = re.findall(r"\d+", _limpio(a["texto"], None))
        situacion = huella() if a["tipo"] == "sin_metricas" else huella(
            a["tipo"], entidad if entidad is not None else "-", *numeros)
        out.append(_alerta(f"tablero:{a['tipo']}:{entidad if entidad is not None else '-'}", situacion,
                           _NIVEL_TABLERO.get(a["nivel"], "info"), _GRUPO_TABLERO.get(a["tipo"], "decision"),
                           texto, "", a["tab"], url=(f"#experimentos?exp={eid}" if eid is not None else None),
                           entidad=entidad))
    return out


# ---------- fuentes: faltantes del proyecto ----------

def _fuente_proyecto(cliente, ahora):
    """Lo que el proyecto todavía no tiene. Huella vacía a propósito: un
    faltante descartado se queda descartado hasta que se resuelva (entonces la
    alerta desaparece y `visibles` poda el descarte)."""
    import catalogo_productos  # noqa: PLC0415
    import marca  # noqa: PLC0415
    import organico  # noqa: PLC0415
    import proyectos  # noqa: PLC0415
    import tiendas  # noqa: PLC0415
    out = []
    if not (marca.guia_efectiva(cliente) or "").strip():
        out.append(_alerta("proyecto:guia_marca", huella(), "atencion", "faltantes",
                           gettext("El proyecto no tiene guía de marca"),
                           gettext("Sin ella cada prompt sale sin el estilo de la marca: súbela o genérala en "
                                   "Configuración › Identidad de marca."),
                           "settings", ancla="config-marca"))
    # Un producto archivado no cuenta: Crear, Sprints y los demás selectores no lo ofrecen.
    productos = catalogo_productos.listar_productos(cliente)
    if productos:
        productos = catalogo_productos.sin_archivados(productos, tiendas.activos_archivados(cliente), set())
    if not productos:
        out.append(_alerta("proyecto:producto", huella(), "atencion", "faltantes",
                           gettext("No hay ningún producto con foto en el catálogo"),
                           gettext("Crear y Sprints necesitan al menos uno: súbelo en Catálogo › Productos."),
                           "catalogo"))
    carpeta = os.path.join(BASE_DIR, "clientes", cliente, "logos")
    archivos = os.listdir(carpeta) if os.path.isdir(carpeta) else []
    if not any(f.lower().endswith(IMAGE_EXTS) for f in archivos):
        out.append(_alerta("proyecto:logo", huella(), "info", "faltantes",
                           gettext("Sin logos oficiales"),
                           gettext("Con un logo el modelo no se lo inventa: súbelo en Configuración › Logos oficiales."),
                           "settings", ancla="config-logos"))
    if not catalogo_productos.listar(cliente, "personaje"):
        out.append(_alerta("proyecto:personaje", huella(), "info", "faltantes",
                           gettext("Sin personaje en el catálogo"),
                           gettext("Crear solo hará videos de producto. Sube un personaje en Catálogo › Personajes si "
                                   "quieres gente en los videos."),
                           "catalogo"))
    if not tiendas.listar(cliente):
        out.append(_alerta("proyecto:tienda", huella(), "info", "faltantes",
                           gettext("Sin tienda conectada"),
                           gettext("Con una tienda los experimentos atribuyen ventas reales. Conéctala en "
                                   "Configuración › Conectar tu tienda."),
                           "settings", ancla="config-tienda"))
    if (os.environ.get("SMTP_HOST") or "").strip() and not (proyectos.correo_notificaciones(cliente) or "").strip():
        out.append(_alerta("proyecto:correo_avisos", huella(), "atencion", "faltantes",
                           gettext("Sin correo de avisos"),
                           gettext("El motor no tiene a quién avisarle de propuestas, ganadores y rechazos: escríbelo en "
                                   "Configuración › Correo de avisos."),
                           "settings", ancla="config-correo"))
    if not organico.disponibles(cliente):
        out.append(_alerta("proyecto:canal_organico", huella(), "info", "faltantes",
                           gettext("Sin canales orgánicos"),
                           gettext("Las ganadoras no se pueden publicar en Instagram, Facebook, TikTok ni YouTube: "
                                   "conecta un canal en Configuración › Canales orgánicos."),
                           "settings", ancla="config-canales-organicos"))
    return out


# ---------- fuentes: decisión y fallos ----------
# Una consulta acotada por fuente (nunca una por tarjeta ni `creative_flow.cargar`): la pestaña se calcula en cada
# carga de página (con caché de 60 s), y `tests/test_alertas_fuentes.py` vigila que las sentencias no crezcan con
# el número de sesiones, sprints o estudios.

def _fuente_crear(cliente, ahora):
    """Sesiones de Crear que esperan o fallaron, de los últimos DIAS_FALLOS días, en UNA consulta. Los prompts
    listos son UNA alerta con el conteo (solo los de hace más de MINUTOS_PROMPT_LISTO: las recién armadas no
    molestan mientras la persona trabaja; huella = ids ordenados, ancla = la más vieja); cada sesión en error es
    una alerta. El estado sale como en `creative_flow._a_dict` (el `estado_legado` guardado, o el de la pieza), pero
    calculado en SQL: así solo vuelven las filas que sirven, sin cargar las sesiones."""
    co, pz = db.concepto, db.pieza
    legado = sa.func.coalesce(sa.func.json_extract(pz.c.extra, "$.estado_legado"),
                              sa.func.json_extract(co.c.extra, "$.estado_legado"))
    estado = sa.func.coalesce(legado, sa.case((pz.c.estado == "pendiente", "prompt_listo"), else_=pz.c.estado))
    accion = sa.func.coalesce(sa.func.json_extract(pz.c.extra, "$.accion_central"),
                              sa.func.json_extract(co.c.extra, "$.accion_central"))
    q = (sa.select(co.c.legado_id, estado.label("estado"), accion.label("accion"), pz.c.error)
         .select_from(co.join(pz, pz.c.concepto_id == co.c.id))
         .where(co.c.cliente == cliente, co.c.legado_id.isnot(None), pz.c.tipo != "final",
                co.c.creado_en >= _hace(ahora, days=DIAS_FALLOS),
                sa.or_(sa.and_(estado == "prompt_listo", co.c.creado_en < _hace(ahora, minutes=MINUTOS_PROMPT_LISTO)),
                       estado == "error"))
         .order_by(co.c.id.desc()))
    with db.conectar() as con:
        filas = con.execute(q).fetchall()
    listos, con_error, out = set(), set(), []
    for f in filas:  # una sesión con dos piezas no se cuenta dos veces
        if f.estado == "prompt_listo":
            listos.add(f.legado_id)
            continue
        if f.legado_id in con_error:
            continue
        con_error.add(f.legado_id)
        error = _limpio(f.error)
        nombre = " ".join(str(f.accion or "").split())[:60] or f.legado_id
        out.append(_alerta(f"crear:error:{f.legado_id}", huella(error), "atencion", "fallos",
                           gettext("Falló «%(nombre)s» en Crear", nombre=nombre),
                           _con_error(error, gettext("Rearma el prompt o vuelve a generar.")),
                           "creativeflowplus", ancla=f"cf-{f.legado_id}", entidad=f.legado_id,
                           url="#creativeflowplus?cf=" + quote(f.legado_id, safe="")))
    if listos:
        listos = sorted(listos)
        out.insert(0, _alerta("crear:prompt_listo", huella(*listos), "atencion", "decision",
                              ngettext("%(num)s prompt listo sin generar en Crear",
                                       "%(num)s prompts listos sin generar en Crear", len(listos)),
                              gettext("Revisa y genera (o descarta): el prompt ya está armado y generar cuesta lo que "
                                      "dice el botón."),
                              "creativeflowplus", ancla=f"cf-{listos[0]}",
                              url="#creativeflowplus?cf=" + quote(listos[0], safe="")))
    return out


def _fuente_organico(cliente, ahora):
    """Publicaciones orgánicas en error de los últimos DIAS_FALLOS días, en UNA consulta (con el nombre de la pieza
    sacado del concepto). Reintentar es una acción de la persona sobre la pieza: aquí solo se avisa."""
    import organico  # noqa: PLC0415 — arrastra requests
    pub, pz, co = db.publicacion, db.pieza, db.concepto
    posterior = pub.alias("posterior")
    resuelta = sa.exists(sa.select(posterior.c.id).where(
        posterior.c.cliente == pub.c.cliente, posterior.c.pieza_id == pub.c.pieza_id,
        posterior.c.plataforma == pub.c.plataforma, posterior.c.id > pub.c.id,
        posterior.c.estado.in_(("en_cola", "publicando", "publicada"))))
    q = (sa.select(pub.c.id, pub.c.plataforma, pub.c.error, pub.c.pieza_id,
                   sa.func.json_extract(co.c.extra, "$.accion_central").label("accion"))
         .select_from(pub.join(pz, pz.c.id == pub.c.pieza_id).outerjoin(co, co.c.id == pz.c.concepto_id))
         .where(pub.c.cliente == cliente, pub.c.estado == "error", ~resuelta,
                pub.c.actualizado_en >= _hace(ahora, days=DIAS_FALLOS))
         .order_by(pub.c.id.desc()))
    with db.conectar() as con:
        filas = con.execute(q).fetchall()
    out = []
    for f in filas:
        nombre = " ".join(str(f.accion or "").split())[:60] or gettext("pieza %(n)s", n=f.pieza_id)
        plataforma = idiomas.traducir(organico.PLATAFORMAS.get(f.plataforma, {}).get("nombre", f.plataforma))
        error = _limpio(f.error)
        out.append(_alerta(f"organico:error:{f.id}", huella(error), "atencion", "fallos",
                           gettext("Falló la publicación en %(plataforma)s de «%(nombre)s»",
                                   plataforma=plataforma, nombre=nombre),
                           _con_error(error, gettext("Reintenta desde la pieza.")),
                           "experimentos", entidad=f.id))
    return out


def _fuente_sprints(cliente, ahora):
    """Por sprint vivo (ni archivado ni completado): ideas propuestas sin aprobar (en campañas que esperan ideas),
    piezas terminadas por revisar, piezas fallidas (error o QA «falla») y referencias cuyo análisis falló. Enlaza
    a la página del sprint. DOS consultas en total, sin importar cuántos sprints ni campañas haya
    (`sprints.datos.sprint` haría una por campaña): una trae las ideas de todos los sprints vivos con su pieza de
    Crear, otra las referencias en error. Una «pieza» es una idea con sesión (no una reserva vencida) que no se
    descartó, la misma cuenta que `datos._campanas` y `sprints.revision.resumen`."""
    from sprints import datos, revision  # noqa: PLC0415
    sp, c, cp, pz, r = db.sprint, db.campana, db.campana_pieza, db.pieza, db.referencia
    vivo = sa.and_(sp.c.cliente == cliente, c.c.cliente == cliente, sp.c.archivado.is_(False),
                   sp.c.estado != "completado")
    ideas_q = (sa.select(sp.c.id.label("sid"), sp.c.nombre, sp.c.inicio, c.c.estado.label("campana_estado"),
                         cp.c.id.label("cp_id"), cp.c.estado_idea, cp.c.revision, cp.c.cf_id,
                         sa.func.json_extract(cp.c.qa, "$.veredicto").label("veredicto"),
                         pz.c.estado.label("pieza_estado"))
               .select_from(sp.join(c, c.c.sprint_id == sp.c.id).join(cp, cp.c.campana_id == c.c.id)
                            .outerjoin(pz, sa.and_(pz.c.legado_id == cp.c.cf_id, pz.c.cliente == cp.c.cliente,
                                                   pz.c.tipo.in_(datos.TIPOS_PIEZA))))
               .where(vivo, cp.c.cliente == cliente))
    refs_q = (sa.select(sp.c.id.label("sid"), sp.c.nombre, sp.c.inicio, r.c.id.label("ref_id"))
              .select_from(sp.join(c, c.c.sprint_id == sp.c.id).join(r, r.c.campana_id == c.c.id))
              .where(vivo, r.c.cliente == cliente, r.c.analisis_estado == "error"))
    por_sprint = {}

    def _de(f):
        return por_sprint.setdefault(f.sid, {"nombre": f.nombre or f"#{f.sid}", "inicio": f.inicio, "ideas": set(),
                                             "por_revisar": set(), "fallidas": set(), "refs": set()})
    with db.conectar() as con:
        ideas, refs = con.execute(ideas_q).fetchall(), con.execute(refs_q).fetchall()
    for f in ideas:
        s = _de(f)
        if f.campana_estado == "ideas_propuestas" and f.estado_idea == "propuesta":
            s["ideas"].add(f.cp_id)
        if f.estado_idea == "descartada" or not f.cf_id or datos.reserva_vencida(f.cf_id):
            continue                                       # sin sesión que la represente: todavía no es una pieza
        if f.revision == "pendiente" and f.pieza_estado in revision.TERMINADAS:
            s["por_revisar"].add(f.cp_id)
        if f.pieza_estado == "error" or f.veredicto == "falla":
            s["fallidas"].add(f.cp_id)
    for f in refs:
        _de(f)["refs"].add(f.ref_id)
    out = []
    # El orden de la lista de sprints (el más nuevo primero), sin importar de qué consulta salió cada uno.
    for sid, s in sorted(por_sprint.items(), key=lambda kv: (kv[1]["inicio"], kv[0]), reverse=True):
        nombre, url = s["nombre"], _url_proyecto(cliente, "sprints", sid)
        if s["ideas"]:
            out.append(_alerta(f"sprint:ideas:{sid}", huella(*sorted(s["ideas"])), "atencion", "decision",
                               ngettext("%(num)s idea por aprobar en el sprint «%(nombre)s»",
                                        "%(num)s ideas por aprobar en el sprint «%(nombre)s»", len(s["ideas"]),
                                        nombre=nombre),
                               gettext("Aprueba o descarta las ideas propuestas para poder generar el lote."),
                               "sprints", url=url, entidad=sid))
        if s["por_revisar"]:
            out.append(_alerta(f"sprint:revision:{sid}", huella(len(s["por_revisar"])), "atencion", "decision",
                               ngettext("%(num)s pieza por revisar en el sprint «%(nombre)s»",
                                        "%(num)s piezas por revisar en el sprint «%(nombre)s»", len(s["por_revisar"]),
                                        nombre=nombre),
                               gettext("Aprueba o rechaza cada una desde el sprint; las aprobadas entran a la entrega."),
                               "sprints", url=url, entidad=sid))
        if s["fallidas"]:
            out.append(_alerta(f"sprint:fallos:{sid}", huella(*sorted(s["fallidas"])), "atencion", "fallos",
                               ngettext("%(num)s pieza fallida en el sprint «%(nombre)s»",
                                        "%(num)s piezas fallidas en el sprint «%(nombre)s»", len(s["fallidas"]),
                                        nombre=nombre),
                               gettext("Regenera las que quieras desde el sprint; cada una vuelve a pasar por el costo."),
                               "sprints", url=url, entidad=sid))
        if s["refs"]:
            out.append(_alerta(f"sprint:referencias:{sid}", huella(*sorted(s["refs"])), "info", "fallos",
                               ngettext("%(num)s referencia sin analizar en el sprint «%(nombre)s»",
                                        "%(num)s referencias sin analizar en el sprint «%(nombre)s»", len(s["refs"]),
                                        nombre=nombre),
                               gettext("El análisis con Claude falló: vuelve a intentarlo desde la campaña."),
                               "sprints", url=url, entidad=sid))
    return out


def _fuente_nicho(cliente, ahora):
    """Nicho: UNA alerta de decisión por proyecto con los avatares propuestos por aprobar
    (`nicho.datos.resumen_avatares`, la misma cuenta de la pestaña; lleva a la página de avatares) y, por estudio,
    un fallo si su investigación quedó `interrumpida` o `detenida` (salvo que la persona la cancelara) o si su
    última generación de avatares falló (`extra.ultimo_error`). Una consulta trae solo los estudios con algo roto
    (los archivados y el oculto de avatares a mano no cuentan). Un estudio, una alerta: la investigación manda
    sobre el error de generación. Reanudar o volver a generar la quita sola."""
    from nicho import datos  # noqa: PLC0415
    out = []
    nuevos = datos.resumen_avatares(cliente)["nuevos"]
    if nuevos > 0:
        out.append(_alerta("nicho:avatares", huella(nuevos), "atencion", "decision",
                           ngettext("%(num)s avatar propuesto por aprobar", "%(num)s avatares propuestos por aprobar",
                                    nuevos),
                           gettext("Aprueba los que sirvan (cada uno se vuelve una persona de Sprints) y descarta "
                                   "el resto."),
                           "nicho", url=_url_proyecto(cliente, "nicho", "avatares")))
    t = db.estudio
    q = (sa.select(t.c.id, t.c.nombre, t.c.extra)
         .where(t.c.cliente == cliente, t.c.archivado.is_(False),
                sa.or_(sa.func.json_extract(t.c.extra, "$.ultimo_error").isnot(None),
                       sa.func.json_extract(t.c.extra, "$.investigacion.estado").in_(("detenida", "interrumpida"))))
         .order_by(t.c.id.desc()))
    with db.conectar() as con:
        filas = con.execute(q).fetchall()
    for f in filas:
        extra = f.extra if isinstance(f.extra, dict) else {}
        if datos.es_manual({"extra": extra}):
            continue
        eid, nombre, url = f.id, f.nombre, _url_proyecto(cliente, "nicho", f.id)
        inv = extra.get("investigacion") if isinstance(extra.get("investigacion"), dict) else {}
        motivo = inv.get("detenida_por")
        if inv.get("estado") == "interrumpida":
            error = _limpio(inv.get("ultimo_error"))
            titulo = gettext("Se interrumpió la investigación de «%(estudio)s»", estudio=nombre)
            detalle = _con_error(error, gettext("Ábrela y pulsa «Reanudar» para retomarla donde quedó."))
        elif inv.get("estado") == "detenida" and motivo and motivo != "cancelada":
            # Lo que se guardó, no su traducción: la huella no puede depender del idioma de quien mira.
            error = _limpio(motivo)
            titulo = gettext("Se detuvo la investigación de «%(estudio)s»", estudio=nombre)
            detalle = gettext("Detenida: %(motivo)s. Ábrela en el estudio para reanudarla o investigar de nuevo.",
                              motivo=idiomas.traducir(error))
        elif extra.get("ultimo_error"):
            error = _limpio(extra["ultimo_error"])
            titulo = gettext("Falló la generación de avatares en «%(estudio)s»", estudio=nombre)
            detalle = _con_error(error, gettext("Vuelve a generar desde el estudio."))
        else:
            continue                          # nada que avisar: la persona canceló la investigación, o no hay texto de error
        out.append(_alerta(f"nicho:error:{eid}", huella(error), "atencion", "fallos", titulo, detalle, "nicho",
                           url=url, entidad=eid))
    return out


# ---------- cálculo ----------

def calcular(cliente, ahora_iso=None):
    """Todas las alertas del proyecto, sin mirar descartes ni rol, ordenadas
    por grupo (GRUPOS) y nivel (NIVELES); dentro del mismo nivel, en el orden
    en que las produjo su fuente (sorted es estable)."""
    ahora = ahora_iso or db.ahora()
    out = []
    for nombre, fn in FUENTES:
        try:
            out.extend(fn(cliente, ahora))
        except Exception as e:  # noqa: BLE001 — una fuente rota no tumba las demás ni la página
            clase = type(e).__name__          # solo la clase: el mensaje podría arrastrar un token
            out.append(_alerta(f"revision:{nombre}", huella(clase), "info", "puesta_a_punto",
                               gettext("No se pudo revisar %(fuente)s", fuente=nombre),
                               gettext("Falló el cálculo (%(error)s). El resto de alertas sigue abajo.", error=clase),
                               "settings", solo_admin=True))
    orden_grupo = {g: i for i, g in enumerate(GRUPOS)}
    orden_nivel = {n: i for i, n in enumerate(NIVELES)}
    return sorted(out, key=lambda a: (orden_grupo[a["grupo"]], orden_nivel[a["nivel"]]))


def es_solo_admin(clave, calculadas):
    """¿`clave` es de una alerta que solo puede tocar un admin? Manda la lista
    ya calculada (`calcular`); si la alerta no está en ella (ya se resolvió, o
    la clave es inventada), decide el prefijo."""
    for a in calculadas:
        if a["clave"] == clave:
            return bool(a.get("solo_admin"))
    return clave.startswith(PREFIJOS_SOLO_ADMIN)


def resumen(lista):
    r = {"n": len(lista), "bloquea": 0, "atencion": 0, "info": 0}
    for a in lista:
        r[a["nivel"]] += 1
    return r


# ---------- descartes ----------

def _descartes(cliente):
    """{clave: (huella, descartada_en)} de los descartes del proyecto."""
    t = db.alerta_descartada
    with db.conectar() as con:
        return {f.clave: (f.huella, f.descartada_en) for f in con.execute(
            sa.select(t.c.clave, t.c.huella, t.c.descartada_en).where(t.c.cliente == cliente))}


def descartar(cliente, clave, huella_):
    """Upsert atómico de (cliente, clave) → huella: un descarte nuevo sobre la
    misma clave reemplaza al anterior."""
    t = db.alerta_descartada
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(insert_sqlite(t).values(cliente=cliente, clave=clave, huella=huella_, descartada_en=ahora)
                    .on_conflict_do_update(index_elements=["cliente", "clave"],
                                           set_={"huella": huella_, "descartada_en": ahora}))


def restaurar(cliente, clave):
    t = db.alerta_descartada
    with db.conectar() as con:
        con.execute(sa.delete(t).where(t.c.cliente == cliente, t.c.clave == clave))


def _borrar_descartes(cliente, huerfanos):
    """Borra los descartes `{clave: huella}` que `visibles` leyó y vio huérfanos.
    Cada borrado exige también la huella que se leyó: si otro proceso reescribió
    ese descarte entre la lectura y este borrado (otra huella), no se lo lleva."""
    t = db.alerta_descartada
    with db.conectar() as con:
        for clave, huella_ in huerfanos.items():
            con.execute(sa.delete(t).where(t.c.cliente == cliente, t.c.clave == clave, t.c.huella == huella_))


def visibles(cliente, ahora_iso=None, rol="cliente", calculadas=None):
    """calcular() menos las alertas descartadas con la MISMA huella, y menos
    las `solo_admin` salvo que `rol == "admin"`. `calculadas` deja al llamador
    pasar un `calcular` ya hecho (la caché de 60 s del context processor); los
    descartes siempre se leen en vivo. Devuelve {"visibles", "descartadas"
    (las actuales que coinciden con un descarte, con `descartada_en`),
    "resumen" (de las visibles)}. De paso poda los descartes cuya clave ya no
    existe (la alerta se resolvió) mirando TODAS las alertas, no solo las que
    ve esta persona, salvo que en esta pasada haya fallado alguna fuente
    (`revision:*`): sus alertas podrían faltar por el fallo y se perderían
    descartes válidos."""
    todas = calculadas if calculadas is not None else calcular(cliente, ahora_iso)
    filas = _descartes(cliente)
    vis, desc = [], []
    for a in todas:
        if a.get("solo_admin") and rol != "admin":
            continue
        d = filas.get(a["clave"])
        if d and d[0] == a["huella"]:
            desc.append({**a, "descartada_en": d[1]})
        else:
            vis.append(a)
    claves = {a["clave"] for a in todas}
    huerfanos = {c: f[0] for c, f in filas.items() if c not in claves}
    if huerfanos and not any(a["clave"].startswith("revision:") for a in todas):
        _borrar_descartes(cliente, huerfanos)
    return {"visibles": vis, "descartadas": desc, "resumen": resumen(vis)}


# ---------- registro de fuentes (orden = orden dentro de un mismo grupo y nivel) ----------

FUENTES.extend([
    ("llaves", _fuente_llaves),
    ("cuentas", _fuente_cuentas),
    ("worker", _fuente_worker),
    ("saldo", _fuente_saldo),
    ("tablero", _fuente_tablero),
    ("proyecto", _fuente_proyecto),
    ("crear", _fuente_crear),
    ("organico", _fuente_organico),
    ("sprints", _fuente_sprints),
    ("nicho", _fuente_nicho),
])
