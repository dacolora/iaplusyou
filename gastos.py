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

Lecturas: `resumen_mes`, `resumen_todo`, `resumen_total`, `total_entre`, `por_mes`, `historial`,
`serie_diaria`, `csv_mes`, `por_proyecto_mes`; `formatear(usd)` -> "US$ 0,07".

Precios que se ven (cobros, spec 2026-10-08 §6): `margen_vigente()`, `precio(usd)`
y `texto_precio(usd)` multiplican por el margen del proyecto de la petición; el
`usd` de `estimar` sigue siendo el costo.
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

TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "recoleccion", "investigacion", "adaptar_referente", "sugerir_ia", "clasificacion", "refinar_prompt", "guion_clips", "ideas", "pedidos", "revision", "evaluacion", "locucion", "voz_propia", "transcripcion",
         # PND-299: las ayudas con IA que pagaba Creatv (`_creatv`, tipo «otro») y ahora paga el proyecto.
         "director", "describir_referencias", "sugerir_sonido", "analizar_marca", "otro")

# Tarifas fijas (USD) de lo que no tiene `estimate_*` propio. Fuentes:
#  - Anthropic (claude-sonnet-5, US$ 2/M tokens de entrada y US$ 10/M de
#    salida, lista pública 2026): una regla de producto (~600 tokens) o un
#    caption (~1.500 tokens) cuestan < US$ 0,01. Un guion (base, localizado o
#    variante) se paga ahora por su `usage` real (PND-001, 2026-10-02: antes se
#    anotaba US$ 0,01 fijo y lo real es ≈ 0,04–0,05 por llamada). Su peor caso:
#    dos llamadas (la corrección) con la salida al tope de 4 000 tokens
#    (2 × US$ 0,04) más ≈ 10 000 de entrada cada una (2 × US$ 0,02) y Whisper
#    de la referencia (US$ 0,01) = US$ 0,13. Se redondea HACIA ARRIBA a un
#    tope redondo: el estimado nunca queda por debajo del real.
#  - fal.ai: ElevenLabs multilingual-v2 ~US$ 0,05 por pieza de 15-20 s de
#    voz (por carácter); Stable Audio ~US$ 0,02 por pista (cacheada por
#    estilo+duración, así que suele salir 0); whisper ~US$ 0,01 por clip.
#  - final = guion localizado (peor caso US$ 0,12: dos llamadas al tope) + voz
#    (0,05) + música (0,02, casi siempre en caché) + whisper (0,01) ≈ US$ 0,20
#    por país (era 0,10 con el guion a 0,01 fijo; 2026-10-02).
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
    "guion": 0.13,
    "regla_producto": 0.01,
    # Texto orgánico («Escribir con IA», la publicación de una ganadora): la doctrina en el system y hasta 4 000
    # tokens de salida con el pensamiento. Peor caso con ese tope: 4 000 × US$ 10/M + ≈ 6 000 de entrada (la
    # doctrina escrita en caché, 1,25×) × US$ 2/M ≈ 0,055. Era 0,01 fijo y se anotaba eso (PND-315: ahora se anota
    # lo real; revisión de guardian-gasto, 2026-10-15: el botón tiene que mostrar un precio que no se quede corto).
    "caption_organico": 0.06,
    "adaptar_referente": 0.01,
    # «Recrear» fiel (spec 2026-09-30): una llamada de visión que describe la
    # composición y lee los textos de la referencia, una vez por referente.
    # Inicial; se ajusta con lo medido en la prueba real.
    "leer_referente": 0.01,
    "sugerir_ia": 0.04,
    # PND-166, 2026-10-09: estimados iniciales con salidas al tope vigente y
    # ~10k tokens de entrada equivalentes por llamada (doctrina/visión/catálogo).
    # Análisis: hasta 2 × (4000 salida + entrada); personas: 6000 salida + entrada.
    "analizar_referencia": 0.12,
    "sugerir_personas": 0.08,
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
    "final": 0.20,
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
    # Triple Whale, «Cómo mejorarlo» (spec 2026-10-08 tarjetas §6.1): una llamada con visión (hasta 8 fotogramas),
    # la doctrina en el system (caché) y hasta 12 000 tokens de salida.
    # Medido en la prueba real (2026-10-08, claude-sonnet-5, 4 anuncios de happyflops, caché caliente): una llamada
    # US$ 0,067–0,084; 1 de 4 necesitó la corrección (US$ 0,16 en total, la primera con la caché fría: US$ 0,095);
    # Whisper ≤ US$ 0,0014. Esperado ≈ 0,075 × 1,25 + Whisper; redondeado hacia arriba. Informe:
    # docs/superpowers/evals/2026-10-08-tw-como-mejorarlo.md (PND-179).
    # Desde el 2026-10-09 el análisis trae además tres ganchos y el copy nuevo para Meta (spec tw-ganchos-y-copy §3.3):
    # medido 2026-10-09 con ganchos y copy: 0,086–0,111 con la caché caliente (tanda) y 0,131–0,170 con la caché fría
    # (un clic suelto, media 0,142); se muestra 0,17, lo más caro medido de un clic suelto; en una tanda (caché
    # caliente) se cobra lo real, menos.
    "analisis_anuncio_tw": 0.17,
    # Meta rendimiento, «Evaluar con IA» (spec E2 §8): base + por anuncio de la muestra (estimador «evaluacion_meta»).
    # Una llamada con visión, la doctrina en el system (caché) y hasta 48 000 tokens de salida (E2-R8).
    # Segunda medición (2026-10-10, claude-sonnet-5, happyflops, muestra de 10 anuncios, 5 con imagen): una sola
    # llamada que termina sola (end_turn), ≈ 21 000 tokens de salida (pensamiento + JSON): US$ 0,2245–0,2527. Lo que no
    # crece con N (la salida, ≈ 0,21, y la doctrina escrita en caché, ≈ 0,02) va en la base; cada anuncio suma su
    # bloque de DATOS, su imagen y su nota (≈ 0,004). Con N = 10 da 0,30, sobre lo más caro medido y lo peor esperable
    # sin corrección (10 imágenes, caché fría, segmentos: ≈ 0,28). Una corrección (rara desde E2-R8) cuesta otra
    # llamada. Informe: docs/superpowers/evals/2026-10-10-meta-evaluacion.md («Segunda medición»).
    "evaluacion_meta": 0.25,
    "evaluacion_meta_por_anuncio": 0.005,
    # Las ayudas con IA de Crear y de la marca, que pagaba Creatv (`_creatv`) y desde PND-299 (decisión 2026-10-13,
    # lote 1) cobran del saldo del proyecto como todo lo demás. Costo de proveedor; el real se anota con los tokens.
    # Director («Crear super prompt», `director.compilar`): una llamada con la doctrina de video; con corrección, dos.
    # Medido el 2026-10-09 (docs/superpowers/evals/2026-10-09-director-seedance-ref.md): 0,015–0,026 una llamada y
    # 0,035–0,050 con la corrección. Se muestra lo más caro medido.
    "director": 0.05,
    # Describir referencias (`referencias_link.describir`, visión): medido el 2026-10-10 (PND-141) 0,004 con una imagen
    # y 0,010 con seis; base + lo de cada imagen, redondeado hacia arriba (hasta 16 imágenes ≈ 0,028).
    "describir_referencias": 0.004,
    "describir_referencias_por_imagen": 0.0015,
    # Sugerir sonido (`final_edition.sonido.sugerir_descripcion`): medido 0,0013 (PND-141).
    "sugerir_sonido": 0.002,
    # Analizar marca (`generador_prompts.analizar_marca`): hasta 5 imágenes (~1 600 tokens c/u) y 400 de salida.
    "analizar_marca": 0.025,
    # La revisión de marca de cada swap (`generador_prompts.evaluar_contra_matriz`): una llamada con visión y hasta
    # 1 500 tokens de salida. Peor caso con ese tope: 1 500 × US$ 10/M + ≈ 3 000 de entrada (imagen y reglas) ×
    # US$ 2/M ≈ 0,021; se anota lo real (PND-315) y este es el precio que se ve antes (revisión de guardian-gasto,
    # 2026-10-15: se cobraba sin estar en el precio del swap).
    "revision_marca": 0.02,
}

# Evaluación de anuncios de Triple Whale con IA (spec 2026-09-28 §6): una llamada con visión (una miniatura por
# anuncio), la doctrina de clasificar, ángulo, gancho y video en el system (caché), hasta 32 000 tokens de salida con
# pensamiento y UNA corrección si la respuesta no sirve (`triple_whale.analisis`). El precio a la vista es el del PEOR
# caso (PND-217, decisión del lote 1, 2026-10-13): las dos llamadas agotando el tope de salida (2 × 32 000 × US$ 10 por
# millón = 0,64) más la entrada de las dos con la caché fría (doctrina ≈ 7 000 tokens escritos a 1,25×, el prompt y, por
# anuncio, su bloque y su miniatura ≈ 1 000 tokens por llamada a US$ 2 por millón): 0,67 de base + 0,005 por anuncio,
# 0,72 con 10. Lo que no crece con N va en la base. Lo medido de verdad (una sola llamada que termina sola) sale entre
# US$ 0,12 y 0,23 (evals 2026-10-09, 2026-10-12 y docs/superpowers/evals/2026-10-15-tw-evaluar-32000-nvp.md): Cobros
# cobra el costo real × margen; esto es solo el precio visto antes, que nunca queda por debajo de lo que puede costar.
# Hasta el 2026-10-15 eran 0,08 + 0,012 por anuncio (0,20 con 10), por debajo de lo medido con corrección (0,30).
EVALUACION_TW_BASE_USD = 0.67
EVALUACION_TW_POR_ANUNCIO_USD = 0.005
# Un anuncio hecho en Creatv con video no manda una miniatura sino hasta 8 fotogramas de 640 px (`doctrina.revisor`,
# ≈ 970 tokens cada uno, ≈ 8 000 por anuncio) en CADA una de las dos llamadas: ≈ US$ 0,032 más por anuncio así
# (revisión del gasto, 2026-10-15: con 10 piezas de Creatv el peor caso llegaba a ≈ 1,00 y se habría cobrado más de lo
# visto). `triple_whale.analisis.estimado` los cuenta (`n_video`) con la misma regla en el botón, la ruta y la tarea.
EVALUACION_TW_POR_VIDEO_USD = 0.032

# «Proponer ideas» de Sprints (entrega 2 del tablero): una llamada a Claude con
# la doctrina en el system (caché) y hasta ~1 200 tokens de salida por idea
# (`sprints.ideas.max_tokens_para`). El gasto REAL se registra con los tokens
# medidos (tipo "ideas"); estas dos cifras solo dan el «≈» del botón.
IDEAS_BASE_USD = 0.015
IDEAS_POR_IDEA_USD = 0.012

# El nombre de cada tipo de gasto en pantalla (Configuración › Gasto, panel, cobros.vista).
NOMBRES_TIPO = {
    "video": N_("Videos"), "imagen": N_("Imágenes"), "swap": N_("Cambios de producto"),
    "guion": N_("Guiones"), "final": N_("Finales"), "regla_producto": N_("Reglas de producto (IA)"),
    "caption_organico": N_("Textos orgánicos (IA)"), "musica": N_("Música"),
    "locucion": N_("Locuciones (audios)"), "voz_propia": N_("Voces propias"),
    "refinar_prompt": N_("Correcciones de prompt (Flow Plus)"), "guion_clips": N_("Guiones a clips (Flow Plus)"),
    "ideas": N_("Ideas de sprint (IA)"), "pedidos": N_("Pedidos al cliente (IA)"),
    "revision": N_("Revisión de la doctrina (IA)"),
    "evaluacion": N_("Evaluación de anuncios (IA)"),
    "transcripcion": N_("Subtítulos (transcripción)"),
    # Sin nombre hasta 2026-10-13: el cliente de un proyecto que cobra no veía estos gastos en su historial;
    # desde que ve lo usado antes de cobrar (libro.detallar_uso_previo) aparecían con su código.
    "clasificacion": N_("Clasificación de referentes (IA)"), "adaptar_referente": N_("Recrear referentes (IA)"),
    "sugerir_ia": N_("Sugerencias de referentes (IA)"), "recoleccion": N_("Recolección de comentarios"),
    "investigacion": N_("Investigación de nicho (IA)"), "avatares": N_("Avatares (IA)"),
    # Las ayudas con IA que pagaba Creatv y desde PND-299 paga el proyecto.
    "director": N_("Prompts armados con IA"), "describir_referencias": N_("Referencias descritas con IA"),
    "sugerir_sonido": N_("Sonidos sugeridos con IA"), "analizar_marca": N_("Guía de marca con IA"),
    "otro": N_("Otros"),
}

SIN_PRECIO = N_("precio no disponible")


class SinPrecio(str):
    """«precio no disponible» en el idioma de quien mira: lo que devuelve el filtro de plantilla `|precio` cuando el
    margen de la petición no se pudo leer (PND-231, como `texto_precio`). Es texto: los filtros `|usd`, `|usd_fino` y
    `|precio_fmt` lo dejan pasar tal cual, y como `total_visto` no vuelve a ser un precio (`costo_de_precio` → None:
    el servidor no cobra con eso)."""

    @classmethod
    def ahora(cls):
        return cls(gettext(SIN_PRECIO))


# ------------------------------------------------------------ formato ---

def formatear(usd):
    """`None` -> "—"; menos de un centavo -> "US$ <0,01"; si no, dos
    decimales con coma decimal y punto de miles ("US$ 1.234,56") — o el
    separador del idioma activo (`idiomas.numero`). Un `SinPrecio` (el
    `|precio` sin margen) pasa tal cual: «precio no disponible»."""
    if isinstance(usd, SinPrecio):
        return usd
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


def _leer_margen(cliente):
    """Margen de `cliente` (1.0 si no cobra), o None si la lectura falla."""
    if not cliente:
        return 1.0
    try:
        from cobros import libro  # noqa: PLC0415 — cobros.libro importa gastos
        return float(libro.margen_precio(cliente))
    except Exception as e:  # noqa: BLE001
        log.warning("margen de %s no se pudo leer: %s", cliente, e)
        return None


def _margen_de(cliente):
    """Margen de `cliente` (1.0 si no cobra o si la lectura falla: lo que se
    cobra lo decide el libro, no este número). Los textos de precio de una
    petición no caen al costo: ver `_margen_fallido`."""
    margen = _leer_margen(cliente)
    return 1.0 if margen is None else margen


def margen_vigente():
    """Margen de precio de la petición en curso (cobros, spec 2026-10-08 §6):
    en un proyecto que cobra, todo «≈ US$» que ve una persona es precio
    (costo × margen). `dashboard._margen_de_precio` deja en `g.cliente_precio`
    el proyecto de la petición (el <cliente> de la URL o, sin él, el de la
    sesión de un cliente); el margen se lee la primera vez que se pide y queda
    en `g.margen_precio` (una lectura por petición, y ninguna en las que no
    pintan precios: sondeos, estáticos). Fuera de una petición, o en un
    proyecto que no cobra, 1.0."""
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if not has_request_context():
            return 1.0
        if "margen_precio" not in g:
            margen = _leer_margen(g.get("cliente_precio"))
            g.margen_precio_fallo = margen is None
            g.margen_precio = 1.0 if margen is None else margen
        return float(g.margen_precio)
    except Exception:  # noqa: BLE001
        return 1.0


def _margen_fallido():
    """¿Falló la lectura del margen de esta petición? Entonces el texto de un
    precio dice «precio no disponible» en vez de mostrar el costo como si fuera
    el precio (revisión final 2026-10-08, M1). Nunca lanza."""
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if not has_request_context():
            return False
        margen_vigente()
        return bool(g.get("margen_precio_fallo"))
    except Exception:  # noqa: BLE001
        return False


def precio(usd, cliente=None):
    """`usd` (costo) × margen de la petición, o None. Solo para mostrar: las
    reservas y el cobro los calcula `cobros.libro` desde el costo. `cliente`:
    para un texto que se arma fuera de una petición (el worker), el margen de
    ese proyecto."""
    if usd is None:
        return None
    margen = _margen_de(cliente) if cliente else margen_vigente()
    return round(float(usd) * margen, 4)


def costo_de_precio(valor):
    """Lo que la persona vio y devolvió el navegador (un precio, con el margen
    de la petición) → el costo, para compararlo con el costo recalculado o
    pedírselo al libro: la ÚNICA vuelta de precio a costo (spec 2026-10-08 §6:
    al navegador de un proyecto que cobra nunca le llega el costo). None si no
    es un número finito entre 0 y 1 000 (excluidos)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or not 0 < v < 1000:
        return None
    return v / margen_vigente()


def texto_precio(usd):
    """El «US$ 0,30 aprox.» de un costo, ya con el margen de la petición. Si el
    margen no se pudo leer, «precio no disponible» (nunca el costo)."""
    if usd is not None and _margen_fallido():
        return gettext(SIN_PRECIO)
    return _texto_estimado(precio(usd))


def _estimado(usd, detalle=""):
    """`usd` es el COSTO (lo usan las reservas y el libro); `usd_precio` y
    `texto`, lo que ve la persona (con el margen si el proyecto cobra; sin
    precio si el margen no se pudo leer)."""
    usd = None if usd is None else round(float(usd), 4)
    usd_precio = None if usd is not None and _margen_fallido() else precio(usd)
    return {"usd": usd, "usd_precio": usd_precio, "texto": texto_precio(usd), "detalle": detalle}


# ------------------------------------------------------------ estimar ---

def costo_musica_estimada(estilo):
    from mi_musica import es_propia
    from providers.fal_audio import COSTO_USD_POR_PISTA_MUSICA
    return COSTO_USD_POR_PISTA_MUSICA if estilo and not es_propia(estilo) else 0.0


def _estimar_video(modelo=None, duracion=None, con_sonido=True, musica_estilo="", **_):
    from providers import flowplus_modelos
    if not modelo or not duracion:
        return None, "faltan modelo o duración"
    r = flowplus_modelos.estimate_video(modelo, float(duracion), con_sonido=bool(con_sonido))
    usd = r.get("usd")
    usd = None if usd is None else usd + costo_musica_estimada(musica_estilo)
    return usd, f"{modelo} · {int(float(duracion))} s" + ("" if con_sonido else " · sin sonido")


def _estimar_imagen(modelo=None, n_referencias=1, **_):
    from providers import flowplus_modelos
    if not modelo:
        return None, "falta el modelo"
    r = flowplus_modelos.estimate_imagen(modelo, n_referencias=max(1, int(n_referencias or 1)))
    return r.get("usd"), f"{modelo} · {max(1, int(n_referencias or 1))} referencia(s)"


def _estimar_swap(proveedor=None, formato="foto", mejorar_calidad=False, duracion=5, n_referencias=1, fps=None,
                  con_revision=False, **_):
    """Misma tabla que usa `tareas/swap.py` al cobrar: cada proveedor tiene
    su `estimate_*`; el que no esté aquí no tiene tarifa (None). `formato`
    es "foto" | "video" (el `tipo` del swap). En video, `duracion` y `fps` son
    los del video que se sube (`providers.swap_video_precio`, PND-312). `con_revision`: el proyecto tiene reglas
    de marca y cada swap pasa por la revisión de marca con Claude, que se cobra (`TARIFAS["revision_marca"]`)."""
    usd, detalle = _estimar_swap_proveedor(proveedor, formato, mejorar_calidad, duracion, n_referencias, fps)
    if usd is not None and con_revision:
        usd, detalle = float(usd) + TARIFAS["revision_marca"], f"{detalle} · revisión de marca"
    return usd, detalle


def _estimar_swap_proveedor(proveedor, formato, mejorar_calidad, duracion, n_referencias, fps):
    from providers import (comparador_modelos, kling_o1_client, nano_banana_client, wavespeed_client,
                           wavespeed_imagen, wavespeed_video_edit)
    if not proveedor:
        return None, "falta el proveedor"
    duracion = float(duracion or 5)
    if formato == "video":
        if proveedor == "kling_o1":
            usd = kling_o1_client.estimate_video(duracion, fps)["usd"]
        elif proveedor == "wan27_edit":
            usd = wavespeed_client.estimate_video(duracion, fps)["usd"]
        elif proveedor in wavespeed_video_edit.MODELOS:
            usd = wavespeed_video_edit.estimate_video(proveedor, duracion, fps)["usd"]
        elif proveedor in comparador_modelos.MODELOS_VIDEO:
            usd = comparador_modelos.estimate_video(proveedor, duracion, fps)["usd"]
        else:
            return None, f"{proveedor}: sin tarifa"
        return usd, f"{proveedor} · video {duracion:g} s"
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


def _estimar_voz_clonada(nombre="", idioma="es", **_):
    """Clon, vista previa y estreno con la misma frase que usa la tarea."""
    from providers import fal_audio
    from voces_propias import frase_muestra
    frase = frase_muestra(nombre, idioma)
    return (fal_audio.costo_clonar_voz(frase) + len(frase) * fal_audio.COSTO_MINIMAX_POR_CARACTER,
            "una voz clonada con MiniMax")


def _estimar_voz_disenada(nombre="", idioma="es", **_):
    from providers import fal_audio
    from voces_propias import frase_muestra
    frase = frase_muestra(nombre, idioma)
    usd = (fal_audio.costo_disenar_voz(frase)
           + round(len(frase) * fal_audio.COSTO_MINIMAX_POR_CARACTER, 4))
    return round(usd, 4), "una voz diseñada con MiniMax"


def _estimar_transcripcion(segundos=0, sin_duracion=False, **_):
    """Editor capa 5a: subtítulos automáticos con Whisper vía fal, por
    duración del audio (misma fórmula del gasto real, `fal_audio.costo_whisper`).
    `sin_duracion`: algún archivo no sabe cuánto dura — sin precio (nunca
    «gratis»: el botón queda apagado y la ruta no transcribe)."""
    from providers import fal_audio
    if sin_duracion:
        return None, "duración desconocida"
    n = max(0, int(segundos or 0))
    return fal_audio.costo_whisper(n * 1000), f"{n} s de audio con Whisper"


def _estimar_voz_editor(caracteres=0, solo_subtitulos=False, duracion_ms=None, **_):
    """Editor capa 5a (D9): voz con IA + sus subtítulos, en un solo botón —
    la locución del texto completo más Whisper sobre ella. `ceil(N / 12)`
    segundos: 12 caracteres por segundo, una locución lenta (el estimado
    nunca queda por debajo del real). `solo_subtitulos` (revisión final): esa
    voz ya existe (mismo `hash_voz`) pero sin palabras — solo se paga Whisper,
    sobre su `duracion_ms` real si se conoce (la misma cuenta del gasto)."""
    from providers import fal_audio
    n = max(1, int(caracteres or 0))
    segundos = math.ceil(n / 12)
    if solo_subtitulos:
        ms = int(duracion_ms) if duracion_ms else segundos * 1000
        return fal_audio.costo_whisper(ms), f"subtítulos de una voz ya creada ({n} caracteres)"
    usd_voz = n * fal_audio.COSTO_USD_POR_CARACTER
    return usd_voz + fal_audio.costo_whisper(segundos * 1000), f"{n} caracteres con ElevenLabs y sus subtítulos"


DURACION_ANUNCIO_DEFECTO_S = 30


def _estimar_analisis_anuncio_tw(segundos=None, **_):
    """Claude con visión + Whisper por la duración del video (sin duración, 30 s)."""
    from providers import fal_audio
    try:
        s = float(segundos) if segundos else DURACION_ANUNCIO_DEFECTO_S
    except (TypeError, ValueError):
        s = DURACION_ANUNCIO_DEFECTO_S
    return (round(TARIFAS["analisis_anuncio_tw"] + fal_audio.costo_whisper(s * 1000), 4),
            "una llamada a Claude con visión y la voz con Whisper")


# Ganchos de Triple Whale (spec 2026-10-09-tw-ganchos-y-copy §4.1): cada variante es un clip de Kling O3 Pro, imagen
# a video, de 3 s y sin sonido; armarlo y producirlo es ffmpeg (gratis).
GANCHO_TW_MODELO = "kling_o3_pro"
GANCHO_TW_SEGUNDOS = 3


def estimar_ganchos_tw(n):
    """El precio de «Probar los N ganchos»: n × el clip de Kling, la MISMA cuenta en la ruta y en la plantilla. La
    misma forma que `estimar` (`usd` es el costo). Sin ganchos o sin tarifa, «precio no disponible» (usd None), nunca
    US$ 0."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    uno = estimar("video", modelo=GANCHO_TW_MODELO, duracion=GANCHO_TW_SEGUNDOS, con_sonido=False)["usd"]
    if n <= 0:
        return _estimado(None, "sin ganchos que generar")
    if uno is None:
        return _estimado(None, f"{SIN_PRECIO}: sin tarifa de Kling O3 Pro")
    return _estimado(uno * n, f"{n} clip(s) de {GANCHO_TW_SEGUNDOS} s con Kling O3 Pro, imagen a video")


_ESTIMADORES = {
    "video": _estimar_video,
    "regeneracion": _estimar_video,
    "imagen": _estimar_imagen,
    "swap": _estimar_swap,
    "final": _estimar_final,
    "reedicion": _estimar_final,
    "guion": lambda **_: (TARIFAS["guion"], "hasta dos llamadas a Claude y la transcripción de la referencia"),
    "regla_producto": lambda **_: (TARIFAS["regla_producto"], "una llamada corta a Claude"),
    "caption_organico": lambda **_: (TARIFAS["caption_organico"], "una llamada a Claude"),
    "adaptar_referente": lambda **_: (TARIFAS["adaptar_referente"], "una llamada corta a Claude"),
    "leer_referente": lambda **_: (TARIFAS["leer_referente"], "una llamada corta a Claude con visión"),
    "analizar_referencia": lambda **_: (TARIFAS["analizar_referencia"], ""),
    "sugerir_personas": lambda **_: (TARIFAS["sugerir_personas"], ""),
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
    "evaluacion_tw": lambda n=1, n_video=0, **_: (
        EVALUACION_TW_BASE_USD + EVALUACION_TW_POR_ANUNCIO_USD * max(1, int(n or 0))
        + EVALUACION_TW_POR_VIDEO_USD * max(0, int(n_video or 0)),
        f"{max(1, int(n or 0))} anuncio(s) con Claude"),
    "evaluacion_meta": lambda n=1, **_: (
        TARIFAS["evaluacion_meta"] + TARIFAS["evaluacion_meta_por_anuncio"] * max(1, int(n or 0)),
        f"{max(1, int(n or 0))} anuncio(s) de Meta con Claude"),
    "diagnostico_pieza": lambda **_: (TARIFAS["diagnostico_pieza"], "una llamada a Claude"),
    "analisis_anuncio_tw": _estimar_analisis_anuncio_tw,
    "proponer_ideas": lambda n=1, **_: (IDEAS_BASE_USD + IDEAS_POR_IDEA_USD * max(1, int(n or 0)),
                                        f"{max(1, int(n or 0))} idea(s) con Claude"),
    "director": lambda **_: (TARIFAS["director"], "una o dos llamadas a Claude"),
    "describir_referencias": lambda imagenes=1, **_: (
        TARIFAS["describir_referencias"] + TARIFAS["describir_referencias_por_imagen"] * max(1, int(imagenes or 0)),
        f"{max(1, int(imagenes or 0))} imagen(es) con Claude"),
    "sugerir_sonido": lambda **_: (TARIFAS["sugerir_sonido"], "una llamada corta a Claude"),
    "analizar_marca": lambda **_: (TARIFAS["analizar_marca"], "una llamada a Claude con visión"),
}


# Estimador → el tipo de GASTO que anota (solo los de Claude y la transcripción, que un plan puede incluir:
# cobros.planes.TIPOS_INCLUIDOS). Con plan y tope libre su texto dice «Incluido en tu plan» (spec planes §4 y §8).
GASTO_DE_ESTIMADOR = {
    "guion": "guion", "regla_producto": "regla_producto", "caption_organico": "caption_organico",
    "adaptar_referente": "adaptar_referente", "leer_referente": "adaptar_referente", "sugerir_ia": "sugerir_ia",
    "refinar_prompt": "refinar_prompt", "clasificacion": "clasificacion", "transcripcion": "transcripcion",
    "guion_clips": "guion_clips", "reescribir_idea": "ideas", "proponer_ideas": "ideas",
    "pedidos_producto": "pedidos", "revision_pieza": "revision", "diagnostico_pieza": "revision",
    "evaluacion_tw": "evaluacion", "analisis_anuncio_tw": "evaluacion",
}
INCLUIDO = N_("Incluido en tu plan")


def _incluido_aqui(tipo_estimador, usd):
    """¿En esta petición el gasto entra en lo incluido del plan del proyecto? Nunca lanza."""
    gasto = GASTO_DE_ESTIMADOR.get(tipo_estimador)
    if gasto is None or usd is None:
        return False
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if not has_request_context():
            return False
        from cobros import planes  # noqa: PLC0415
        return planes.incluye(g.get("cliente_precio"), gasto, usd)
    except Exception:  # noqa: BLE001
        return False


def estimar(tipo, **params):
    """{"usd": float|None, "texto": "US$ 0,10 aprox." | "precio no disponible",
    "detalle": str}. Nunca lanza: sin tarifa (tipo o modelo desconocido,
    proveedor que revienta) devuelve usd=None. Con un plan que lo incluye (y
    tope libre), `texto` dice «Incluido en tu plan» e `incluido` es True; `usd`
    sigue siendo el costo."""
    fn = _ESTIMADORES.get(tipo)
    if fn is None:
        return _estimado(None, f"tipo desconocido: {tipo}")
    try:
        usd, detalle = fn(**params)
    except Exception as e:  # noqa: BLE001 — el precio es informativo, nunca bloquea
        log.warning("estimar(%s, %s) falló: %s", tipo, params, e)
        return _estimado(None, "sin tarifa para esos parámetros")
    est = _estimado(usd, detalle)
    if _incluido_aqui(tipo, est["usd"]):
        est = {**est, "texto": gettext(INCLUIDO), "incluido": True}
    return est


# ----------------------------------------------------------- registrar ---

def registrar(cliente, tipo, usd, referencia, detalle="", proveedor=None, extra=None, creado_en=None,
              conservar_mayor=False, entregado=True):
    """Guarda (o actualiza, misma `referencia`) un cobro real. `usd` None/0 se
    guarda como 0 (queda constancia de la llamada aunque no haya tarifa).
    Devuelve el id de la fila. `creado_en` solo se fija al crear (la fecha
    del primer cobro se conserva al actualizar). `conservar_mayor` evita reducir
    un cobro al recuperar un componente pagado que ahora llega de caché.

    Si el proyecto cobra (cobros, spec 2026-10-08 §3), el cobro al cliente se
    escribe aquí mismo, en un savepoint propio: si falla, el costo queda igual
    y se avisa a los admins. Solo un gasto NUEVO estrena cobro; corregir uno que
    ya existía recalcula su cobro si lo tenía y nunca lo crea (§3.2).
    `entregado=False`: el proveedor cobró pero la pieza no llegó; el costo se
    anota igual y al cliente no se le cobra (spec §3.4)."""
    fila = _normalizar(cliente, tipo, usd, referencia, detalle, proveedor)
    with db.conectar() as con:
        gasto_id, resultado_cobro, usd_final = _escribir(con, cliente, *fila, extra=extra, creado_en=creado_en,
                                                         conservar_mayor=conservar_mayor, entregado=entregado)
    _despues_del_cobro(cliente, resultado_cobro, gasto_id, usd_final, fila[0], fila[2])
    return gasto_id


def _normalizar(cliente, tipo, usd, referencia, detalle, proveedor):
    """(tipo, monto, referencia, detalle, proveedor) como se guardan."""
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
    return tipo, monto, referencia, detalle, proveedor


def _escribir(con, cliente, tipo, monto, referencia, detalle, proveedor, *, extra=None, creado_en=None,
              conservar_mayor=False, entregado=True):
    """El upsert del gasto y su cobro, dentro de la transacción `con`.
    Devuelve (gasto_id, resultado_cobro, usd_final)."""
    valores = {"tipo": tipo, "usd": monto, "detalle": detalle}
    # Al actualizar, proveedor/extra solo se pisan si vienen (una segunda
    # llamada que solo corrige el monto no borra lo que ya se sabía).
    cambios = dict(valores)
    if proveedor:
        cambios["proveedor"] = proveedor
    if extra is not None:
        cambios["extra"] = extra
    g = db.gasto

    def _actualizar(gasto_id):
        con.execute(sa.update(g).where(g.c.id == gasto_id,
            g.c.usd <= monto if conservar_mayor else sa.true()).values(**cambios))

    def _cobrar(gasto_id, nuevo):
        """El cobro en su propio savepoint, con el candado de escritura YA tomado
        por el INSERT/UPDATE del gasto: en WAL, una transacción diferida que lee y
        después escribe recibe «database is locked» al instante si otro escritor
        confirmó en medio (SQLITE_BUSY_SNAPSHOT; busy_timeout no aplica). Un cobro
        que falla vuelve a su savepoint y el gasto queda. Nunca lanza."""
        usd_final = monto
        try:
            # Con conservar_mayor el UPDATE pudo no aplicar: se cobra sobre lo que
            # quedó guardado. Dentro del try (revisión final 2026-10-08, M2): si
            # esta lectura lanzara fuera, desharía el INSERT del gasto.
            usd_final = float(con.execute(sa.select(g.c.usd).where(g.c.id == gasto_id)).scalar() or 0.0)
            with con.begin_nested():
                from cobros import libro as _libro  # noqa: PLC0415 — evita el import circular
                antes = _neto_del_gasto(con, gasto_id)
                resultado = _libro.cobrar_gasto(con, gasto_id, cliente, usd_final, tipo,
                                                entregado=entregado, nuevo=nuevo)
                if resultado == "recalculado" and _neto_del_gasto(con, gasto_id) < antes:
                    resultado = "recalculado_mayor"   # cobra más: mira el saldo como un cobro nuevo
        except Exception:  # noqa: BLE001 — el costo no se pierde por el cobro (spec §3.1)
            log.exception("No se pudo anotar el cobro del gasto %s de %s", referencia, cliente)
            resultado = "error"
        return resultado, usd_final

    fila = con.execute(sa.select(g.c.id).where(g.c.cliente == cliente, g.c.referencia == referencia)).first()
    if fila:
        gasto_id = int(fila.id)
        _actualizar(gasto_id)   # el UPDATE abre la transacción y toma el candado
        resultado_cobro, usd_final = _cobrar(gasto_id, nuevo=False)
        return gasto_id, resultado_cobro, usd_final
    try:
        with con.begin_nested():
            r = con.execute(sa.insert(g).values(cliente=cliente, referencia=referencia,
                                                creado_en=(creado_en or db.ahora())[:19],
                                                proveedor=proveedor, extra=extra or {}, **valores))
            gasto_id = int(r.inserted_primary_key[0])
            # DENTRO del savepoint del gasto: pysqlite no emite BEGIN antes de un
            # SAVEPOINT, así que este es el más externo; el INSERT ya tomó el candado
            # y su RELEASE confirma gasto y cobro juntos.
            resultado_cobro, usd_final = _cobrar(gasto_id, nuevo=True)
    except sa.exc.IntegrityError:
        # Carrera: otro proceso insertó la misma referencia entre el select y el insert.
        fila = con.execute(sa.select(g.c.id).where(g.c.cliente == cliente,
                                                   g.c.referencia == referencia)).first()
        gasto_id = int(fila.id)
        _actualizar(gasto_id)
        resultado_cobro, usd_final = _cobrar(gasto_id, nuevo=False)
    return gasto_id, resultado_cobro, usd_final


# ------------------------------------------- cobrar lo que se entrega después ---

def _pendiente_de_cobro(con, gasto_id):
    """¿Se pagó y al cliente no se le cobró? Un `no_cobrado` (el proveedor cobró y la pieza no llegó), o un
    `cobro` con su `reverso` (la tarea falló después). Sin movimientos (un proyecto que no cobra) o con un
    `cobro` vivo o `incluido`: no. Solo lee."""
    m = db.movimiento_saldo
    tipos = {r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gasto_id))}
    return "no_cobrado" in tipos or {"cobro", "reverso"} <= tipos


def pendientes_por_clave(cliente, prefijos, claves):
    """Las partes que quedaron en caché tras un trabajo que falló después de pagar y que nadie le cobró al
    cliente: filas del proyecto cuya referencia empieza con alguno de `prefijos`, con `extra.cache[clave]`
    para una de `claves` y pendientes de cobro (`_pendiente_de_cobro`). Devuelve
    [{"referencia", "clave", "usd"}], lo que `registrar_trasladando` recibe. Solo lee."""
    claves = set(claves or ())
    if not claves or not prefijos:
        return []
    g = db.gasto
    filtro = sa.or_(*[g.c.referencia.startswith(p, autoescape=True) for p in prefijos])
    salida = []
    with db.conectar() as con:
        filas = con.execute(sa.select(g.c.id, g.c.referencia, g.c.extra)
                            .where(g.c.cliente == cliente, filtro).order_by(g.c.id)).all()
        for f in filas:
            cache = (f.extra or {}).get("cache") or {}
            propias = [k for k in cache if k in claves]
            if propias and _pendiente_de_cobro(con, f.id):
                salida += [{"referencia": f.referencia, "clave": k, "usd": float(cache[k] or 0)} for k in propias]
    return salida


def registrar_trasladando(cliente, tipo, usd, referencia, traslados, detalle="", proveedor=None, extra=None,
                          entregado=True):
    """`registrar` de una entrega que además se lleva lo que el proveedor cobró antes y nunca se le cobró al
    cliente (PND-314 y PND-318, decisión 2026-10-13, lote 1: «se cobra cuando se reusa»): la pieza recuperada
    sin pagar de nuevo, o lo que quedó en caché tras una final que falló. Cada traslado es
    {"referencia": <fila de origen>, "clave": <clave de su extra.cache> | None}; con clave se mueve ese monto (la
    clave sale de `extra.cache`), sin clave toda la fila. El origen BAJA en lo movido y anota a dónde fue en
    `extra.trasladado`: el proveedor cobró una sola vez y la tabla sigue sumando lo mismo que su factura. Un
    origen ya cobrado, de otro proyecto o de un proyecto que no cobra no se toca. Todo en una transacción, con
    el candado tomado antes de leer. Sin nada que mover y con `usd` 0 no escribe nada.
    Devuelve (gasto_id | None, usd_movido)."""
    tipo_n, monto, referencia_n, detalle_n, proveedor_n = _normalizar(cliente, tipo, usd, referencia, detalle,
                                                                      proveedor)
    g = db.gasto
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(db.kv.update().where(db.kv.c.clave == "gastos:candado").values(valor=db.kv.c.valor))
        movido, hechos = 0.0, []
        # Una fila de origen puede traer varias claves (el borrador y el destino de la misma final fallida): se
        # lee UNA vez y se le descuentan todas, para que cada clave salga y se cobre una sola vez.
        origenes = {}
        for t in traslados or ():
            ref_origen = str(t.get("referencia") or "")
            if ref_origen not in origenes:
                fila = con.execute(sa.select(g).where(g.c.cliente == cliente, g.c.referencia == ref_origen)).first()
                if fila is None or fila.referencia == referencia_n or not _pendiente_de_cobro(con, fila.id):
                    origenes[ref_origen] = None
                    continue
                origenes[ref_origen] = {"fila": fila, "usd": float(fila.usd or 0.0), "extra": dict(fila.extra or {})}
            o = origenes[ref_origen]
            if o is None:
                continue
            clave = t.get("clave")
            if clave:
                cache = dict(o["extra"].get("cache") or {})
                if clave not in cache:
                    continue
                parte = min(float(cache.pop(clave) or 0.0), o["usd"])
                o["extra"]["cache"] = cache
            else:
                parte = o["usd"]
            parte = round(max(0.0, parte), 4)
            if parte <= 0:
                continue
            o["usd"] = round(o["usd"] - parte, 4)
            o["extra"]["trasladado"] = list(o["extra"].get("trasladado") or []) + [
                {"a": referencia_n, "clave": clave, "usd": parte, "en": ahora}]
            o["movido"] = True
            hechos.append({"de": ref_origen, "clave": clave or f"traslado:{ref_origen}", "usd": parte})
            movido += parte
        correcciones = [o for o in origenes.values() if o and o.get("movido")]
        movido = round(movido, 4)
        if not movido and not monto:
            return None, 0.0
        for o in correcciones:
            # Una corrección (nuevo=False): un `no_cobrado` sigue igual; un cobro con su reverso baja en par.
            f = o["fila"]
            _escribir(con, cliente, f.tipo, o["usd"], f.referencia, f.detalle or "", f.proveedor, extra=o["extra"],
                      entregado=False)
        extra_destino = dict(extra or {})
        if hechos:
            extra_destino["traslados"] = list(extra_destino.get("traslados") or []) + hechos
            extra_destino["usd_trasladado"] = movido
            # Si la entrega falla después y se le devuelve el cobro, lo movido queda pendiente aquí con sus mismas
            # claves: la próxima que lo reuse lo encuentra (revisión de guardian-gasto, 2026-10-15).
            cache = dict(extra_destino.get("cache") or {})
            for h in hechos:
                cache[h["clave"]] = round(float(cache.get(h["clave"]) or 0.0) + h["usd"], 4)
            extra_destino["cache"] = cache
        gasto_id, resultado, usd_final = _escribir(con, cliente, tipo_n, round(monto + movido, 4), referencia_n,
                                                   detalle_n, proveedor_n, extra=extra_destino, entregado=entregado)
    _despues_del_cobro(cliente, resultado, gasto_id, usd_final, tipo_n, referencia_n)
    return gasto_id, movido


def registrar_trasladando_seguro(cliente, tipo, usd, referencia, traslados, **kw):
    """`registrar_trasladando` que nunca lanza: si falla, anota la entrega sola con `registrar_seguro` (lo
    pagado en esta corrida no se pierde; lo de antes sigue pendiente en su fila). Devuelve lo mismo."""
    try:
        return registrar_trasladando(cliente, tipo, usd, referencia, traslados, **kw)
    except Exception:  # noqa: BLE001 — ver docstring
        log.exception("No se pudo trasladar lo pendiente de cobro a %s de %s", referencia, cliente)
        if not usd:
            return None, 0.0
        return registrar_seguro(cliente, tipo, usd, referencia, **kw), 0.0


def _neto_del_gasto(con, gasto_id):
    m = db.movimiento_saldo
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0))
                           .where(m.c.gasto_id == gasto_id)).scalar())


def _despues_del_cobro(cliente, resultado, gasto_id, usd, tipo, referencia):
    """Avisos del cobro, ya con la transacción confirmada (spec §3.6, §8). Nunca lanza."""
    if not resultado:
        return
    try:
        from cobros import avisos, libro  # noqa: PLC0415
        if resultado == "error":
            avisos.admin(
                "cobro_no_anotado",
                lambda: gettext("No se pudo anotar un cobro"),
                lambda: gettext("El gasto %(ref)s de %(cliente)s (%(usd)s) quedó sin su cobro al cliente.",
                                ref=referencia, cliente=cliente, usd=formatear(usd)),
                cliente=cliente)
        elif resultado in ("no_cobrado", "reverso"):
            avisos.pieza_no_cobrada(cliente, _no_cobrado_milesimas(gasto_id, resultado, usd, cliente), tipo)
        elif resultado in ("cobro", "recalculado_mayor"):
            c = libro.cuenta(cliente)
            if c["pospago"]:   # pospago: no hay «saldo bajo»; al admin, cada US$ 200 de deuda nueva
                avisos.deuda_pospago(cliente, libro.deuda(cliente))
            else:
                s = libro.saldo(cliente)
                if s < c["umbral"]:
                    avisos.saldo_bajo(cliente, s)
        # Planes (spec 2026-10-09 §4): lo incluido no le avisa nada al cliente; al admin, al 80 % y al 100 % del
        # tope. Un `cobro` de un tipo incluido con el periodo abierto es uno que ya no cupo en el tope.
        if resultado in ("incluido", "cobro"):
            from cobros import planes  # noqa: PLC0415
            if tipo in planes.TIPOS_INCLUIDOS:
                periodo = planes.periodo_abierto(None, cliente, ahora=db.ahora())
                if periodo is not None:
                    avisos.tope_incluido(cliente, periodo, planes.incluido_usado(cliente, periodo),
                                         agotado=resultado == "cobro")
    except Exception:  # noqa: BLE001
        log.exception("aviso del cobro de %s falló", referencia)


def _no_cobrado_milesimas(gasto_id, resultado, usd, cliente):
    """Lo que no se descontó, con el margen que quedó guardado al cobrar (el
    margen actual pudo cambiar después): el monto del reverso o el precio del
    no_cobrado. Sin esa fila, el margen de hoy."""
    from cobros import libro  # noqa: PLC0415
    m = db.movimiento_saldo
    with db.conectar() as con:
        fila = con.execute(sa.select(m.c.milesimas, m.c.extra)
                           .where(m.c.gasto_id == gasto_id, m.c.tipo == resultado)).first()
    if fila is not None:
        if resultado == "reverso" and fila.milesimas:
            return int(fila.milesimas)
        precio = (fila.extra or {}).get("precio")
        if precio is not None:
            return int(precio)
    return libro.precio_milesimas(usd, libro.cuenta(cliente)["margen"])


def registrar_seguro(cliente, tipo, usd, referencia, **kw):
    """`registrar` que NUNCA lanza: lo llaman las tareas justo después de
    que el proveedor cobró, y un fallo anotando el gasto (base bloqueada,
    disco lleno) no puede tumbar una generación ya pagada. Devuelve el id o
    None si falló (queda en el log). Acepta `entregado=False` (ver `registrar`):
    pagado pero no entregado, al cliente no se le cobra."""
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


def resumen_mes(cliente, ahora_iso=None, desde=None):
    """{"desde", "hasta", "total", "por_tipo": {tipo: {"usd", "n"}}, "n"} del
    mes en curso (o del mes de `ahora_iso`; o desde `desde`)."""
    hasta = _ahora(ahora_iso)
    desde = desde or _inicio_mes(hasta)
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


def resumen_todo(cliente, ahora_iso=None):
    """Como `resumen_mes` pero con todo lo cobrado desde el primer cobro (la
    tabla «Por tipo» de Configuración › Gasto desde 2026-10-08)."""
    return resumen_mes(cliente, ahora_iso, desde="0001-01-01T00:00:00")


def resumen_total(cliente, ahora_iso=None):
    """{"total", "n", "desde"} de todo lo cobrado al proyecto hasta `ahora`
    (Tablero y Configuración › Gasto: el total desde el inicio; `desde` es la
    fecha del primer cobro, None sin cobros)."""
    g = db.gasto
    q = (sa.select(sa.func.sum(g.c.usd), sa.func.count(), sa.func.min(g.c.creado_en))
         .where(g.c.cliente == cliente, g.c.creado_en <= _ahora(ahora_iso)))
    with db.conectar() as con:
        suma, n, desde = con.execute(q).first()
    return {"total": round(float(suma or 0.0), 4), "n": int(n or 0), "desde": desde}


def total_entre(cliente, desde_iso, hasta_iso):
    """Generación pagada en [desde, hasta): {"usd", "n"} (centro de resultados;
    mismo origen que `resumen_mes`)."""
    g = db.gasto
    q = (sa.select(sa.func.coalesce(sa.func.sum(g.c.usd), 0.0), sa.func.count())
         .where(g.c.cliente == cliente, g.c.creado_en >= desde_iso[:19], g.c.creado_en < hasta_iso[:19]))
    with db.conectar() as con:
        usd, n = con.execute(q).one()
    return {"usd": round(float(usd or 0.0), 4), "n": int(n or 0)}


def por_mes(cliente, ahora_iso=None):
    """{"YYYY-MM": {"usd", "n"}} de todo lo cobrado al proyecto hasta `ahora`,
    un mes por clave (Tablero: el desglose mes a mes)."""
    g = db.gasto
    mes = sa.func.substr(g.c.creado_en, 1, 7)
    q = (sa.select(mes, sa.func.sum(g.c.usd), sa.func.count())
         .where(g.c.cliente == cliente, g.c.creado_en <= _ahora(ahora_iso)).group_by(mes))
    with db.conectar() as con:
        return {m: {"usd": round(float(suma or 0.0), 4), "n": int(n)} for m, suma, n in con.execute(q)}


def historial(cliente, limite=200, desde=None, desplazamiento=0):
    """Filas del proyecto, la más nueva primero (`desde` = ISO inclusivo)."""
    g = db.gasto
    q = sa.select(g).where(g.c.cliente == cliente)
    if desde:
        q = q.where(g.c.creado_en >= desde[:19])
    q = q.order_by(g.c.creado_en.desc(), g.c.id.desc()).limit(int(limite)).offset(int(desplazamiento))
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
    return _csv(cliente, _inicio_mes(hasta), hasta)


def csv_todo(cliente, ahora_iso=None):
    """Como `csv_mes` pero con TODOS los cobros del proyecto desde el primero
    (2026-10-07: la pantalla de Gasto solo mostraba el mes y Daniel creyó
    perdidos los meses anteriores)."""
    return _csv(cliente, None, _ahora(ahora_iso))


def _csv(cliente, desde, hasta):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(idiomas.traducir(";".join(ENCABEZADO_CSV)).split(";"))
    g = db.gasto
    q = sa.select(g).where(g.c.cliente == cliente, g.c.creado_en <= hasta)
    if desde:
        q = q.where(g.c.creado_en >= desde)
    q = q.order_by(g.c.creado_en.asc(), g.c.id.asc())
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


# PND-307 (decisión 2026-10-13): el detalle de las filas que copió `importar_historico`
# (2026-09) quedó guardado en español. Se traduce al pintar; la base no se reescribe.
DETALLE_IMPORTADO_PIEZAS = N_("importado del historial de piezas")
DETALLE_IMPORTADO_SWAPS = N_("importado del historial de swaps")


def detalle_visible(detalle):
    """El `detalle` de un gasto como lo ve quien mira: los dos prefijos de la
    importación, en su idioma; cualquier otro detalle, tal cual."""
    texto = detalle or ""
    for prefijo in (DETALLE_IMPORTADO_PIEZAS, DETALLE_IMPORTADO_SWAPS):
        if texto.startswith(prefijo):
            return gettext(prefijo) + texto[len(prefijo):]
    return detalle


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
        registrar(cliente, tipo, usd, ref, detalle=DETALLE_IMPORTADO_PIEZAS,
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
        detalle = " · ".join(x for x in (DETALLE_IMPORTADO_SWAPS, s.get("proveedor"), s.get("tipo")) if x)
        registrar(cliente, "swap", usd, ref, detalle=detalle, proveedor=s.get("proveedor"),
                  creado_en=s.get("creado_en"), extra={"credits": s.get("credits"), "importado": True})
        existentes.append(ref)
        n_swaps += 1
        total += usd
    return {"piezas": n_piezas, "swaps": n_swaps, "usd": round(total, 4)}


def total_tipo(cliente, tipo):
    """Todo el gasto real de un tipo del proyecto, incluidas tareas fallidas."""
    g = db.gasto
    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.coalesce(sa.func.sum(g.c.usd), 0.0)).where(
            g.c.cliente == cliente, g.c.tipo == tipo)).scalar()
    return round(float(total), 4)


def costos_sesiones(cliente):
    """Acumulados por sesión de Crear, una consulta para todas las tarjetas."""
    g = db.gasto
    with db.conectar() as con:
        filas = con.execute(sa.select(g.c.referencia, g.c.usd, g.c.extra).where(
            g.c.cliente == cliente, g.c.tipo.in_(("video", "imagen")))).all()
    out = {}
    for ref, usd, extra in filas:
        partes = ref.split(":")
        if len(partes) < 2 or partes[0] not in ("video", "imagen"):
            continue
        v = out.setdefault(partes[1], {"usd": 0.0, "usd_musica": 0.0})
        v["usd"] += float(usd)
        v["usd_musica"] += float((extra or {}).get("usd_musica") or 0)
    return {cf_id: {k: round(n, 4) for k, n in v.items()} for cf_id, v in out.items()}


def por_referencia(cliente, referencia):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente,
                                                   db.gasto.c.referencia == referencia)).first()
    if fila:
        return _fila(fila)
    import json
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave_reserva(cliente, referencia))).scalar()
    return json.loads(valor) if valor else None


def fichas_pendientes(cliente, tipo):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente, db.gasto.c.tipo == tipo,
                 db.gasto.c.extra["ficha_guardada"].as_boolean().isnot(True))).all()
    return [_fila(f) for f in filas if (f._mapping[db.gasto.c.extra] or {}).get("ficha")]


def _clave_reserva(cliente, referencia):
    import hashlib
    return "reserva_gasto:" + hashlib.sha256(f"{cliente}\x1f{referencia}".encode()).hexdigest()


def reservar_ficha(cliente, tipo, referencia, *, detalle, proveedor, extra):
    """Reserva previa al proveedor, fuera de Gasto: todavía no hubo cobro."""
    import json
    from sqlalchemy.dialects.sqlite import insert
    try:
        valor = json.dumps({"cliente": cliente, "tipo": tipo, "referencia": referencia,
                            "detalle": detalle, "proveedor": proveedor, "extra": extra, "usd": 0})
        with db.conectar() as con:
            con.execute(insert(db.kv).values(clave=_clave_reserva(cliente, referencia), valor=valor,
                        actualizado_en=db.ahora()).on_conflict_do_nothing(index_elements=[db.kv.c.clave]))
        return True
    except Exception:
        log.exception("No se pudo reservar la ficha de voz")
        return None
