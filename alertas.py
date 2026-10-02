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
alerta pasan por `_limpio` (cola.sin_token + cola.recortar). Nada de aquí
gasta, encola, publica ni llama a un proveedor. Sin rutas ni app de Flask
(solo `gettext`, que fuera de una petición devuelve el español): lo importan
dashboard.py y los tests. El ÚNICO escritor de `alerta_descartada` es este
módulo.
"""
import hashlib
import os
import re
from datetime import datetime

import sqlalchemy as sa
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
import idiomas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NIVELES = ("bloquea", "atencion", "info")
GRUPOS = ("puesta_a_punto", "faltantes", "decision", "fallos")
NOMBRES_GRUPO = {"puesta_a_punto": idiomas.N_("Puesta a punto pendiente"), "faltantes": idiomas.N_("Faltantes del proyecto"),
                 "decision": idiomas.N_("Esperan tu decisión"), "fallos": idiomas.N_("Fallos y errores")}
NOMBRES_NIVEL = {"bloquea": idiomas.N_("bloquea"), "atencion": idiomas.N_("atención"), "info": idiomas.N_("info")}
NOMBRES_TAB = {"settings": idiomas.N_("Configuración"), "catalogo": idiomas.N_("Catálogo"), "creativeflowplus": idiomas.N_("Crear"),
               "experimentos": idiomas.N_("Experimentos"), "sprints": idiomas.N_("Sprints"), "nicho": idiomas.N_("Nicho")}

MINUTOS_WORKER = 30                                  # más de esto sin señal de vida y el worker está parado
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")      # lo que cuenta como logo en clientes/<c>/logos/

# Lo que las rutas aceptan al descartar/restaurar (una clave o huella que no
# calce no se guarda). La clave: `<fuente>:<tipo>[:<entidad>]`; la huella: sha256 hex.
CLAVE_VALIDA = r"^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$"
HUELLA_VALIDA = r"^[0-9a-f]{64}$"

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
    """Texto de error apto para una alerta: sin tokens y recortado."""
    return cola.recortar(cola.sin_token(texto), n)


# ---------- fuentes: puesta a punto ----------
# Cada fuente es `fn(cliente, ahora_iso) -> lista de alertas`. Sus dependencias
# se importan adentro (como `tablero` o `organico`, que arrastran requests y el
# motor de experimentos): este módulo lo importan el worker y los tests, y nunca
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
    (`_requiere_correo_verificado`). La ve la propia persona: es su cuenta."""
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
                  "experimento_error": "fallos", "anuncios_rechazados": "fallos", "sin_metricas": "fallos"}
_NIVEL_TABLERO = {"alta": "bloquea", "media": "atencion", "baja": "info"}


def _fuente_tablero(cliente, ahora):
    """`tablero.alertas` traducida a alertas: el texto del Tablero es el
    título, sin tokens (el de una tienda rota arrastra el error de su
    conector). Tope de 400 y no de 200: la guía de Meta en modo Desarrollo
    ronda los 330 caracteres y su llamado a la acción va al final; el error
    crudo de un conector sí queda acotado. `sin_metricas` lleva huella vacía:
    su texto dice «lleva N h» y cambiaría cada hora, así que un descarte nunca
    serviría."""
    import tablero  # noqa: PLC0415
    out = []
    for a in tablero.alertas(cliente, ahora_iso=ahora):
        eid = a.get("experimento_id")
        texto = _limpio(a["texto"], 400)
        out.append(_alerta(f"tablero:{a['tipo']}:{eid if eid is not None else '-'}",
                           huella() if a["tipo"] == "sin_metricas" else huella(texto),
                           _NIVEL_TABLERO.get(a["nivel"], "info"), _GRUPO_TABLERO.get(a["tipo"], "decision"),
                           texto, "", a["tab"], url=(f"?exp={eid}#experimentos" if eid is not None else None),
                           entidad=eid))
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
])
