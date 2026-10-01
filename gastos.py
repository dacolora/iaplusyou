"""
Gasto real por proyecto: cuánto dinero (USD) se le pagó a los proveedores
(WaveSpeed/Higgsfield, fal.ai, Anthropic...) por cada cosa que generó un
proyecto. Sin créditos ni saldo: solo el precio, antes (estimado) y después
(real). La pauta de Meta NO se registra aquí — vive en `metrica_snapshot`
en la moneda de la cuenta publicitaria y se muestra al lado.

Un solo punto de escritura: `registrar(cliente, tipo, usd, referencia, ...)`.
Cada tarea que paga lo llama UNA vez al terminar (o al fallar si el
proveedor ya cobró) con una `referencia` única por cobro (`f"{tipo}:{id}"`);
el índice único `(cliente, referencia)` hace la llamada idempotente: repetir
actualiza `usd`/`detalle`, nunca duplica. Un fallo al registrar jamás debe
tumbar la tarea que ya pagó: los llamadores envuelven en try/except.

`estimar(tipo, **params)` da el precio ANTES de gastar, con la tabla
`TARIFAS` y los `estimate_*` de los proveedores; cuando no hay tarifa
devuelve `usd=None` y el texto "precio no disponible" — nunca se inventa.

Lecturas: `resumen_mes`, `historial`, `serie_diaria`, `csv_mes`,
`por_proyecto_mes`; `formatear(usd)` -> "US$ 0,07".
"""
import csv
import io
import logging
import math
from datetime import datetime, timedelta

import sqlalchemy as sa
from flask_babel import gettext

import db
import idiomas
from idiomas import N_

log = logging.getLogger(__name__)

TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "recoleccion", "investigacion", "adaptar_referente", "sugerir_ia", "clasificacion", "refinar_prompt", "guion_clips", "ideas", "pedidos", "revision", "evaluacion", "locucion", "voz_propia", "transcripcion", "otro")

# Tarifas fijas (USD) de lo que no tiene `estimate_*` propio. Fuentes:
#  - Anthropic (claude-sonnet-5, US$ 2/M tokens de entrada y US$ 10/M de
#    salida, lista pública 2026): una regla de producto (~600 tokens) o un
#    caption (~1.500 tokens) cuestan < US$ 0,01; un guion base/localizado
#    (~4.000 tokens con la guía de marca) ~US$ 0,02. Se redondea HACIA ARRIBA
#    a un tope redondo: el estimado nunca queda por debajo del real.
#  - fal.ai: ElevenLabs multilingual-v2 ~US$ 0,05 por pieza de 15-20 s de
#    voz (por carácter); Stable Audio ~US$ 0,02 por pista (cacheada por
#    estilo+duración, así que suele salir 0); whisper ~US$ 0,01 por clip.
#  - final = guion localizado + voz + música + whisper ≈ US$ 0,10 por país.
#    `derivaciones._avanzar_finales` encola un `final_producir` POR país
#    (guion localizado, voz vía fal/ElevenLabs y whisper propios; solo la
#    música se cachea y a veces sale gratis) — no hay descuento por país
#    extra: cada país adicional cuesta lo mismo que el primero, no solo el
#    guion. `estimar("final", paises=n)` es n × esta tarifa.
#  - avatares (Claude, dos pasadas): el estimado lo calcula
#    nicho/avatares.estimar_costo por tokens; el real sale de usage.
#  - recoleccion (Apify): resultados × precio por resultado del actor
#    (nicho/fuentes/apify_actores.py), "aprox." porque Apify suma cómputo.
#  - referentes, medido en producción el 2026-09-25 (claude-sonnet-5 piensa
#    antes de responder y eso se cobra como salida): clasificar un anuncio
#    ~US$ 0,0103 (entrada ~4.000 tokens con el vocabulario de ~190 familias,
#    salida 160-300); «Sugerir con IA» ~US$ 0,030 (60 candidatos, objetivo 5,
#    ~1.700 tokens de salida, casi todo pensamiento); «Adaptar con IA»
#    ~US$ 0,008.
#  - refinar_prompt (un mensaje del chat de Flow Plus): el prompt vigente de
#    un clip (~2-3k tokens) + contexto e historial entran (~5k, US$ 0,01) y
#    sale el prompt completo revisado más el razonamiento (~4k, US$ 0,04).
#  - guion_clips (pipeline de Flow Plus): leer/recorte/armar/imágenes; el
#    estimado redondea hacia arriba y se revisa contra `gasto` con uso real.
#    Armar, medido el 2026-09-30 con un guion real de 34 líneas / 266 palabras:
#    8 157 tokens de entrada y 19 809 de salida (casi todo pensamiento) =
#    US$ 0,21; con el tope viejo de 16 000 no terminaba. Se estima 0,07 por
#    cada 100 palabras sobre 0,06, sin pasar del peor caso del tope (48 000).
TARIFAS = {
    "guion": 0.02,
    "regla_producto": 0.01,
    "caption_organico": 0.01,
    "adaptar_referente": 0.01,
    # «Recrear» fiel (spec 2026-09-30): una llamada de visión que describe la
    # composición y lee los textos de la referencia, una vez por referente.
    # Inicial; se ajusta con lo medido en la prueba real.
    "leer_referente": 0.01,
    "sugerir_ia": 0.04,
    "clasificacion": 0.012,
    # La de siempre + la salida del segundo idioma (~60 tokens más por anuncio,
    # redondeado hacia arriba): un referente global sale en español e inglés
    # en la misma llamada (spec §B7).
    "clasificacion_bilingue": 0.014,
    "refinar_prompt": 0.05,
    "voz": 0.05,
    "musica": 0.02,
    "musica_elevenlabs": 0.60,   # canción de 60 s con ElevenLabs vía fal (US$ 0,60 por minuto empezado)
    "whisper": 0.01,
    "final": 0.10,
    # Doctrina, bloque 2: una llamada con la doctrina en el system y pensamiento
    # adaptativo. Medido en la prueba real (2026-09-27) con la caché fría, el
    # peor caso: reescribir ≈ US$ 0,026, pedidos ≈ US$ 0,007. Redondeado hacia arriba.
    "reescribir_idea": 0.03,
    "pedidos_producto": 0.01,
    # Doctrina, bloque 3: una llamada con visión (hasta 8 fotogramas) y la rebanada
    # «revisar». Medido en la prueba real (2026-09-27, caché fría, 4 fotogramas):
    # ≈ US$ 0,060 (casi todo es la salida con pensamiento); redondeado hacia arriba.
    "revision_pieza": 0.07,
    # Doctrina, bloque 4: el diagnóstico de una perdedora (una llamada sin visión).
    # Inicial; se ajusta con lo medido en la prueba real.
    "diagnostico_pieza": 0.03,
}

# Evaluación de anuncios de Triple Whale con IA (spec 2026-09-28 §6): una
# llamada con visión (una miniatura por anuncio), la doctrina de clasificar,
# ángulo, gancho y video en el system (caché) y hasta ~10k tokens de salida con
# pensamiento. Cálculo a la tarifa de claude-sonnet-5: entrada ~6k de doctrina +
# ~900 por anuncio (datos + miniatura) ≈ US$ 0,03 con 10 anuncios; salida ≈
# US$ 0,10. Redondeado hacia arriba; el real se registra con los tokens medidos.
EVALUACION_TW_BASE_USD = 0.08
EVALUACION_TW_POR_ANUNCIO_USD = 0.012

# «Proponer ideas» de Sprints (entrega 2 del tablero): una llamada a Claude con
# la doctrina en el system (caché) y hasta ~1 200 tokens de salida por idea
# (`sprints.ideas.max_tokens_para`). El gasto REAL se registra con los tokens
# medidos (tipo "ideas"); estas dos cifras solo dan el «≈» del botón.
IDEAS_BASE_USD = 0.015
IDEAS_POR_IDEA_USD = 0.012

SIN_PRECIO = N_("precio no disponible")


# ------------------------------------------------------------ formato ---

def formatear(usd):
    """`None` -> "—"; menos de un centavo -> "US$ <0,01"; si no, dos
    decimales con coma decimal y punto de miles ("US$ 1.234,56") — o el
    separador del idioma activo (`idiomas.numero`)."""
    if usd is None:
        return "—"
    try:
        v = float(usd)
    except (TypeError, ValueError):
        return "—"
    if 0 < v < 0.01:
        return "US$ <" + idiomas.numero(0.01, 2)
    return f"US$ {idiomas.numero(v, 2)}"


def _texto_estimado(usd):
    if usd is None:
        return gettext(SIN_PRECIO)
    return gettext("%(precio)s aprox.", precio=formatear(usd))


def _estimado(usd, detalle=""):
    usd = None if usd is None else round(float(usd), 4)
    return {"usd": usd, "texto": _texto_estimado(usd), "detalle": detalle}


# ------------------------------------------------------------ estimar ---

def _estimar_video(modelo=None, duracion=None, con_sonido=True, **_):
    from providers import flowplus_modelos
    if not modelo or not duracion:
        return None, "faltan modelo o duración"
    r = flowplus_modelos.estimate_video(modelo, float(duracion), con_sonido=bool(con_sonido))
    return r.get("usd"), f"{modelo} · {int(float(duracion))} s" + ("" if con_sonido else " · sin sonido")


def _estimar_imagen(modelo=None, n_referencias=1, **_):
    from providers import flowplus_modelos
    if not modelo:
        return None, "falta el modelo"
    r = flowplus_modelos.estimate_imagen(modelo, n_referencias=max(1, int(n_referencias or 1)))
    return r.get("usd"), f"{modelo} · {max(1, int(n_referencias or 1))} referencia(s)"


def _estimar_swap(proveedor=None, formato="foto", mejorar_calidad=False, duracion=5, n_referencias=1, **_):
    """Misma tabla que usa `tareas/swap.py` al cobrar: cada proveedor tiene
    su `estimate_*`; el que no esté aquí no tiene tarifa (None). `formato`
    es "foto" | "video" (el `tipo` del swap)."""
    from providers import (comparador_modelos, kling_o1_client, nano_banana_client, wavespeed_client,
                           wavespeed_imagen, wavespeed_video_edit)
    if not proveedor:
        return None, "falta el proveedor"
    duracion = float(duracion or 5)
    if formato == "video":
        if proveedor == "kling_o1":
            usd = kling_o1_client.estimate_video(duracion)["usd"]
        elif proveedor == "wan27_edit":
            usd = wavespeed_client.estimate_video(duracion)["usd"]
        elif proveedor in wavespeed_video_edit.MODELOS:
            usd = wavespeed_video_edit.estimate_video(proveedor, duracion)["usd"]
        elif proveedor in comparador_modelos.MODELOS_VIDEO:
            usd = comparador_modelos.estimate_video(proveedor, duracion)["usd"]
        else:
            return None, f"{proveedor}: sin tarifa"
        return usd, f"{proveedor} · video {int(duracion)} s"
    if proveedor == "nano_banana":
        usd = nano_banana_client.estimate_image()["usd"]
    elif proveedor == "nano_banana_pro_ultra":
        usd = wavespeed_imagen.estimate_image()["usd"]
    elif proveedor == "seedream_v5_pro":
        usd = wavespeed_imagen.estimate_seedream(n_imagenes=max(1, int(n_referencias or 1)) + 1)["usd"]
    elif proveedor in comparador_modelos.MODELOS_IMAGEN:
        usd = comparador_modelos.estimate_image(proveedor)["usd"]
    else:
        return None, f"{proveedor}: sin tarifa"
    if usd is not None and mejorar_calidad:
        usd = float(usd) + wavespeed_imagen.COSTO_USD_UPSCALE
    return usd, f"{proveedor} · foto" + (" · con mejora" if mejorar_calidad else "")


def _estimar_final(paises=1, **_):
    """n × `TARIFAS["final"]`: cada país es su propia tarea `final_producir`
    con guion localizado, voz y whisper propios (I2) — no hay descuento por
    país adicional."""
    n = max(1, int(paises or 1))
    usd = TARIFAS["final"] * n
    return usd, f"{n} país(es): guion localizado, voz, música y whisper"


def _estimar_guion_clips(paso="armar", palabras=0, **_):
    p = max(0, int(palabras or 0))
    if paso == "leer":
        return 0.02 + 0.01 * math.ceil(p / 500), "leer el guion con Claude"
    if paso == "recorte":
        return 0.05, "proponer qué quitar con Claude"
    if paso == "armar":
        return min(0.50, 0.06 + 0.07 * math.ceil(p / 100)), "planear los clips con Claude"
    if paso == "imagenes":
        return 0.08, "escribir los prompts de imágenes con Claude"
    raise ValueError(f"paso desconocido: {paso}")


def _estimar_locucion(caracteres=0, **_):
    """Audios en Crear: ElevenLabs vía fal cobra por carácter; el mismo texto
    con la misma voz y velocidad no se paga dos veces (caché por hash), pero el
    estimado no lo sabe y muestra el precio completo."""
    from providers import fal_audio
    n = max(1, int(caracteres or 0))
    return n * fal_audio.COSTO_USD_POR_CARACTER, f"{n} caracteres con ElevenLabs"


def _estimar_voz_clonada(**_):
    """Voces propias de Audios: clonar una voz con MiniMax vía fal. La vista
    previa de la frase de muestra se cobra aparte (US$ 0,0003 por carácter:
    1-3 ¢ para una frase típica) y no entra en este estimado."""
    from providers import fal_audio
    return fal_audio.COSTO_CLONAR_VOZ, "una voz clonada con MiniMax"


def _estimar_voz_disenada(**_):
    from providers import fal_audio
    return fal_audio.COSTO_DISENAR_VOZ, "una voz diseñada con MiniMax"


def _estimar_transcripcion(segundos=0, **_):
    """Editor capa 5a: subtítulos automáticos con Whisper vía fal, por
    duración del audio (misma fórmula del gasto real, `fal_audio.costo_whisper`)."""
    from providers import fal_audio
    n = max(0, int(segundos or 0))
    return fal_audio.costo_whisper(n * 1000), f"{n} s de audio con Whisper"


def _estimar_voz_editor(caracteres=0, **_):
    """Editor capa 5a (D9): voz con IA + sus subtítulos, en un solo botón —
    la locución del texto completo más Whisper sobre ella. `ceil(N / 12)`
    segundos: 12 caracteres por segundo, una locución lenta (el estimado
    nunca queda por debajo del real)."""
    from providers import fal_audio
    n = max(1, int(caracteres or 0))
    usd_voz = n * fal_audio.COSTO_USD_POR_CARACTER
    segundos = math.ceil(n / 12)
    return usd_voz + fal_audio.costo_whisper(segundos * 1000), f"{n} caracteres con ElevenLabs y sus subtítulos"


_ESTIMADORES = {
    "video": _estimar_video,
    "regeneracion": _estimar_video,
    "imagen": _estimar_imagen,
    "swap": _estimar_swap,
    "final": _estimar_final,
    "reedicion": _estimar_final,
    "guion": lambda **_: (TARIFAS["guion"], "una llamada a Claude"),
    "regla_producto": lambda **_: (TARIFAS["regla_producto"], "una llamada corta a Claude"),
    "caption_organico": lambda **_: (TARIFAS["caption_organico"], "una llamada a Claude"),
    "adaptar_referente": lambda **_: (TARIFAS["adaptar_referente"], "una llamada corta a Claude"),
    "leer_referente": lambda **_: (TARIFAS["leer_referente"], "una llamada corta a Claude con visión"),
    "sugerir_ia": lambda **_: (TARIFAS["sugerir_ia"], "una llamada a Claude"),
    "refinar_prompt": lambda **_: (TARIFAS["refinar_prompt"], "un mensaje a Claude"),
    "clasificacion": lambda n=1, bilingue=False, **_: (
        TARIFAS["clasificacion_bilingue" if bilingue else "clasificacion"] * max(1, int(n)),
        f"{max(1, int(n))} anuncio(s) con Claude" + (", en español e inglés" if bilingue else "")),
    "musica_elevenlabs": lambda **_: (TARIFAS["musica_elevenlabs"], "una canción de 60 s con ElevenLabs"),
    "locucion": _estimar_locucion,
    "voz_clonada": _estimar_voz_clonada,
    "voz_disenada": _estimar_voz_disenada,
    "transcripcion": _estimar_transcripcion,
    "voz_editor": _estimar_voz_editor,
    "guion_clips": _estimar_guion_clips,
    "reescribir_idea": lambda **_: (TARIFAS["reescribir_idea"], "una llamada a Claude"),
    "pedidos_producto": lambda **_: (TARIFAS["pedidos_producto"], "una llamada a Claude"),
    "revision_pieza": lambda **_: (TARIFAS["revision_pieza"], "una llamada a Claude con visión"),
    "evaluacion_tw": lambda n=1, **_: (EVALUACION_TW_BASE_USD + EVALUACION_TW_POR_ANUNCIO_USD * max(1, int(n or 0)),
                                       f"{max(1, int(n or 0))} anuncio(s) con Claude"),
    "diagnostico_pieza": lambda **_: (TARIFAS["diagnostico_pieza"], "una llamada a Claude"),
    "proponer_ideas": lambda n=1, **_: (IDEAS_BASE_USD + IDEAS_POR_IDEA_USD * max(1, int(n or 0)),
                                        f"{max(1, int(n or 0))} idea(s) con Claude"),
}


def estimar(tipo, **params):
    """{"usd": float|None, "texto": "US$ 0,10 aprox." | "precio no disponible",
    "detalle": str}. Nunca lanza: sin tarifa (tipo o modelo desconocido,
    proveedor que revienta) devuelve usd=None."""
    fn = _ESTIMADORES.get(tipo)
    if fn is None:
        return _estimado(None, f"tipo desconocido: {tipo}")
    try:
        usd, detalle = fn(**params)
    except Exception as e:  # noqa: BLE001 — el precio es informativo, nunca bloquea
        log.warning("estimar(%s, %s) falló: %s", tipo, params, e)
        return _estimado(None, "sin tarifa para esos parámetros")
    return _estimado(usd, detalle)


# ----------------------------------------------------------- registrar ---

def registrar(cliente, tipo, usd, referencia, detalle="", proveedor=None, extra=None, creado_en=None):
    """Guarda (o actualiza, misma `referencia`) un cobro real. `usd` None/0 se
    guarda como 0 (queda constancia de la llamada aunque no haya tarifa).
    Devuelve el id de la fila. `creado_en` solo se fija al crear (la fecha
    del primer cobro se conserva al actualizar)."""
    if not cliente or not referencia:
        raise ValueError("registrar necesita cliente y referencia.")
    tipo = tipo if tipo in TIPOS else "otro"
    try:
        monto = round(float(usd or 0.0), 4)
    except (TypeError, ValueError):
        monto = 0.0
    if monto < 0:
        monto = 0.0
    detalle = (detalle or "")[:300]
    proveedor = (proveedor or None) and str(proveedor)[:30]
    referencia = str(referencia)[:160]
    valores = {"tipo": tipo, "usd": monto, "detalle": detalle}
    # Al actualizar, proveedor/extra solo se pisan si vienen (una segunda
    # llamada que solo corrige el monto no borra lo que ya se sabía).
    cambios = dict(valores)
    if proveedor:
        cambios["proveedor"] = proveedor
    if extra is not None:
        cambios["extra"] = extra
    g = db.gasto
    with db.conectar() as con:
        fila = con.execute(sa.select(g.c.id).where(g.c.cliente == cliente, g.c.referencia == referencia)).first()
        if fila:
            con.execute(sa.update(g).where(g.c.id == fila.id).values(**cambios))
            return int(fila.id)
        try:
            with con.begin_nested():
                r = con.execute(sa.insert(g).values(cliente=cliente, referencia=referencia,
                                                    creado_en=(creado_en or db.ahora())[:19],
                                                    proveedor=proveedor, extra=extra or {}, **valores))
                return int(r.inserted_primary_key[0])
        except sa.exc.IntegrityError:
            # Carrera: otro proceso insertó la misma referencia entre el select y el insert.
            fila = con.execute(sa.select(g.c.id).where(g.c.cliente == cliente, g.c.referencia == referencia)).first()
            con.execute(sa.update(g).where(g.c.id == fila.id).values(**cambios))
            return int(fila.id)


def registrar_seguro(cliente, tipo, usd, referencia, **kw):
    """`registrar` que NUNCA lanza: lo llaman las tareas justo después de
    que el proveedor cobró, y un fallo anotando el gasto (base bloqueada,
    disco lleno) no puede tumbar una generación ya pagada. Devuelve el id o
    None si falló (queda en el log)."""
    try:
        return registrar(cliente, tipo, usd, referencia, **kw)
    except Exception:  # noqa: BLE001 — ver docstring
        log.exception("No se pudo registrar el gasto %s de %s (US$ %s)", referencia, cliente, usd)
        return None


# ------------------------------------------------------------ lecturas ---

def _ahora(ahora_iso):
    return (ahora_iso or db.ahora())[:19]


def _inicio_mes(ahora_iso):
    return ahora_iso[:7] + "-01T00:00:00"


def _fila(r):
    d = dict(r._mapping)
    d["usd"] = float(d.get("usd") or 0.0)
    d["extra"] = d.get("extra") or {}
    return d


def resumen_mes(cliente, ahora_iso=None):
    """{"desde", "hasta", "total", "por_tipo": {tipo: {"usd", "n"}}, "n"} del
    mes en curso (o del mes de `ahora_iso`)."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    g = db.gasto
    q = (sa.select(g.c.tipo, sa.func.sum(g.c.usd), sa.func.count())
         .where(g.c.cliente == cliente, g.c.creado_en >= desde, g.c.creado_en <= hasta)
         .group_by(g.c.tipo))
    por_tipo = {}
    with db.conectar() as con:
        for tipo, suma, n in con.execute(q):
            por_tipo[tipo] = {"usd": round(float(suma or 0.0), 4), "n": int(n)}
    total = round(sum(v["usd"] for v in por_tipo.values()), 4)
    return {"desde": desde, "hasta": hasta, "total": total, "por_tipo": por_tipo,
            "n": sum(v["n"] for v in por_tipo.values())}


def historial(cliente, limite=200, desde=None):
    """Filas del proyecto, la más nueva primero (`desde` = ISO inclusivo)."""
    g = db.gasto
    q = sa.select(g).where(g.c.cliente == cliente)
    if desde:
        q = q.where(g.c.creado_en >= desde[:19])
    q = q.order_by(g.c.creado_en.desc(), g.c.id.desc()).limit(int(limite))
    with db.conectar() as con:
        return [_fila(r) for r in con.execute(q)]


def serie_diaria(cliente, dias=30, ahora_iso=None):
    """[{"dia": "YYYY-MM-DD", "usd": f}] para los últimos `dias` días (hoy
    incluido, días sin gasto en 0), en orden cronológico."""
    hasta = _ahora(ahora_iso)
    hoy = datetime.fromisoformat(hasta).date()
    dias = max(1, int(dias))
    primer_dia = hoy - timedelta(days=dias - 1)
    g = db.gasto
    q = (sa.select(sa.func.substr(g.c.creado_en, 1, 10), sa.func.sum(g.c.usd))
         .where(g.c.cliente == cliente, g.c.creado_en >= primer_dia.isoformat() + "T00:00:00",
                g.c.creado_en <= hasta)
         .group_by(sa.func.substr(g.c.creado_en, 1, 10)))
    por_dia = {}
    with db.conectar() as con:
        for dia, suma in con.execute(q):
            por_dia[dia] = round(float(suma or 0.0), 4)
    return [{"dia": (primer_dia + timedelta(days=i)).isoformat(),
             "usd": por_dia.get((primer_dia + timedelta(days=i)).isoformat(), 0.0)} for i in range(dias)]


def por_proyecto_mes(clientes, ahora_iso=None):
    """{cliente: total USD del mes} en UNA consulta; los proyectos sin gasto
    salen con 0."""
    clientes = list(clientes or [])
    out = {c: 0.0 for c in clientes}
    if not clientes:
        return out
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    g = db.gasto
    q = (sa.select(g.c.cliente, sa.func.sum(g.c.usd))
         .where(g.c.cliente.in_(clientes), g.c.creado_en >= desde, g.c.creado_en <= hasta)
         .group_by(g.c.cliente))
    with db.conectar() as con:
        for cliente, suma in con.execute(q):
            out[cliente] = round(float(suma or 0.0), 4)
    return out


# ----------------------------------------------------------------- CSV ---

# La línea entera es UN msgid (una palabra suelta como «proyecto» ya existe en
# el catálogo como plural y chocaría); `csv_mes` la traduce al escribirla.
ENCABEZADO_CSV = N_("fecha;tipo;proveedor;referencia;detalle;usd").split(";")
_INICIOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celda(v):
    """Texto seguro para Excel/Sheets (mismo criterio que `tablero._celda`):
    lo que empiece por `=`, `+`, `-`, `@`, tab o CR se evaluaría como
    fórmula, así que se antepone `'`."""
    s = str(v or "")
    return "'" + s if s[:1] in _INICIOS_FORMULA else s


def csv_mes(cliente, ahora_iso=None):
    """CSV (`;`) con una fila por cobro del mes en curso, con BOM para que
    Excel lo abra en UTF-8. `usd` con coma decimal y 4 decimales (M5: mismo
    separador que `tablero.csv_mes`, coherente con el `;` de delimitador).
    Encabezados en el idioma activo (en la ruta, el de quien lo descarga); los
    `detalle` guardados salen tal cual."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(idiomas.traducir(";".join(ENCABEZADO_CSV)).split(";"))
    g = db.gasto
    q = (sa.select(g).where(g.c.cliente == cliente, g.c.creado_en >= desde, g.c.creado_en <= hasta)
         .order_by(g.c.creado_en.asc(), g.c.id.asc()))
    with db.conectar() as con:
        for r in con.execute(q):
            f = _fila(r)
            w.writerow([_celda(f["creado_en"]), _celda(f["tipo"]), _celda(f.get("proveedor")),
                        _celda(f["referencia"]), _celda(f.get("detalle")), f"{f['usd']:.4f}".replace(".", ",")])
    return "﻿" + buf.getvalue()


# ------------------------------------------------------- relleno histórico ---

# Estados de `pieza` que significan "el proveedor cobró": listo y degradada
# (una final con capas caídas también se pagó). `error` no: no se sabe si el
# cobro alcanzó a ocurrir; `pendiente`/`generando` lo registrará su tarea.
ESTADOS_PIEZA_COBRADA = ("listo", "degradada")
_TIPOS_PIEZA = {"video": "video", "imagen": "imagen", "final": "final"}
_PROVEEDOR_PIEZA = {"video": "wavespeed", "imagen": "wavespeed", "final": "fal/anthropic"}


def _ya_registrado(referencias, ref):
    """La tarea registra `ref` o `ref:<tarea_id>` (su ref_sufijo): cualquiera
    de las dos significa que ese cobro ya está en la tabla."""
    return any(r == ref or r.startswith(ref + ":") for r in referencias)


def importar_historico(cliente, swaps=None):
    """Copia a `gasto`, UNA vez, los cobros anteriores a la tabla (nació el
    2026-09-18): el `costo_usd` de cada `pieza` cobrada y el `usd` de cada
    swap listo de swaps.json. Misma referencia que usan las tareas
    (`video:<cf_id>`, `final:<final_id>`, `swap:<swap_id>`) y la fecha
    original de la pieza, así cae en su mes. Idempotente: lo que ya está
    (importado o registrado por su tarea) se salta. `swaps` es el dict de
    swaps.json; sin él se lee el del proyecto. Devuelve el resumen."""
    if swaps is None:
        import swaps as swaps_mod
        swaps = swaps_mod.cargar(cliente) or {}
    g = db.gasto
    with db.conectar() as con:
        existentes = [r[0] for r in con.execute(sa.select(g.c.referencia).where(g.c.cliente == cliente))]
        piezas = [dict(r._mapping) for r in con.execute(
            sa.select(db.pieza).where(db.pieza.c.cliente == cliente).order_by(db.pieza.c.id))]
    n_piezas = n_swaps = 0
    total = 0.0
    for p in piezas:
        usd = float(p.get("costo_usd") or 0.0)
        if p.get("estado") not in ESTADOS_PIEZA_COBRADA or usd <= 0 or not p.get("legado_id"):
            continue
        tipo = _TIPOS_PIEZA.get(p.get("tipo"), "otro")
        ref = f"{tipo}:{p['legado_id']}"
        if _ya_registrado(existentes, ref):
            continue
        registrar(cliente, tipo, usd, ref, detalle="importado del historial de piezas",
                  proveedor=_PROVEEDOR_PIEZA.get(tipo), creado_en=p.get("creado_en"),
                  extra={"modelo": p.get("modelo"), "importado": True})
        existentes.append(ref)
        n_piezas += 1
        total += usd
    for swap_id, s in (swaps or {}).items():
        s = s or {}
        usd = float(s.get("usd") or 0.0)
        if s.get("estado") != "listo" or usd <= 0:
            continue
        ref = f"swap:{swap_id}"
        if _ya_registrado(existentes, ref):
            continue
        detalle = " · ".join(x for x in ("importado del historial de swaps", s.get("proveedor"), s.get("tipo")) if x)
        registrar(cliente, "swap", usd, ref, detalle=detalle, proveedor=s.get("proveedor"),
                  creado_en=s.get("creado_en"), extra={"credits": s.get("credits"), "importado": True})
        existentes.append(ref)
        n_swaps += 1
        total += usd
    return {"piezas": n_piezas, "swaps": n_swaps, "usd": round(total, 4)}
