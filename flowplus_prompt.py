"""
Arma el prompt final de FlowPlus a partir de lo que escribió la persona.

Con el director (`director.py`, spec 2026-09-18) el texto de la persona se convierte en planos `Shot N`; sin director (fallback y sesiones anteriores) se manda TAL CUAL. Lo que sí se antepone es lo que evita los dos fallos
que se vieron en los primeros videos de Happy Flops:

  1. El modelo inventó un logo cursivo en la sandalia. -> Bloque de fidelidad:
     cada referencia de producto se reproduce exacta, incluida la marca tal como
     aparece; nunca se inventan letras. Si el proyecto tiene logos subidos en
     FlowSettings, van como referencias extra "@Logo N".
  2. Salieron pies/personas cuando solo se quería el producto. -> Regla de
     personas: sin persona por defecto (solo producto); si hay persona, se aplica
     la guía de marca de personas/pies.

Ningún modelo de FlowPlus acepta negative_prompt (verificado en WaveSpeed para
Wan 3.0), así que las prohibiciones van dentro del prompt como frases negativas
explícitas. Las referencias se nombran con los tokens que documentan los
fabricantes (`Image N` / `Video N`, por orden de subida; spec director §5):
`asignar_tokens` los calcula por modelo y `sustituir_tokens` cambia las
menciones `@Imagen N` / `@Video N` / `@Logo N` del texto de la persona.

Idioma del proyecto (spec 2026-09-26 §B4-§B5): todas las frases fijas que van
al modelo viven en `TEXTOS`, un diccionario por idioma ("es"/"en"); cada
función recibe `idioma` y elige su bloque de textos con
`TEXTOS[idioma if idioma in TEXTOS else "es"]`. El texto de la persona
(`texto`, `sonido`, `guia_marca`, `regla` de cada activo...) nunca se toca ni
se traduce — solo las etiquetas fijas cambian de idioma.
"""
import re

from idiomas import N_


def _lista(refs, tipo):
    return [r for r in refs if r.get("tipo") == tipo]


_MENCION = re.compile(r"@(Imagen|Video|Logo) (\d+)")


def asignar_tokens(referencias, modelo_id):
    """Escribe `token` en cada referencia (en su lugar) según lo que ve el
    modelo: con Wan 3.0 los videos viajan aparte (`Video N`) y las imágenes
    (activos, vistas y logos incluidos) se numeran `Image N`; con los demás
    modelos el video entra por su fotograma, así que cuenta como una imagen
    más. Devuelve la misma lista."""
    from providers import flowplus_modelos
    videos_aparte = flowplus_modelos.VIDEO.get(modelo_id, {}).get("max_videos", 0) > 0
    n_img = n_vid = 0
    for r in referencias:
        if r.get("tipo") == "video" and videos_aparte:
            n_vid += 1
            r["token"] = f"Video {n_vid}"
        else:
            n_img += 1
            r["token"] = f"Image {n_img}"
    return referencias


def sustituir_tokens(texto, referencias):
    """Cambia las menciones `@Imagen N` / `@Video N` / `@Logo N` que escribió
    la persona por el token final de esa referencia. Mapea por la `etiqueta`
    visible — el chip que la persona (o "Describir con IA") vio y usó para
    mencionarla —, no por su posición: en Sprints el producto del catálogo va
    primero en `referencias` pero se menciona `@Producto 1`, y las imágenes de
    campaña que vienen después son `@Imagen 1..`; numerar por posición
    correría esos números y apuntaría al producto. Un activo del catálogo con
    una etiqueta propia (p. ej. "Personaje 1") nunca es `@Imagen N` en la UI,
    así que esa mención no existe para él. Una mención sin referencia
    correspondiente se deja tal cual: no se inventan imágenes que el modelo no
    va a recibir."""
    por_etiqueta = {r.get("etiqueta"): r.get("token") for r in referencias if r.get("token")}

    def _cambiar(m):
        return por_etiqueta.get(m.group(0), m.group(0))

    return _MENCION.sub(_cambiar, texto or "")


def _nombre(r):
    """Token si la referencia lo tiene; si no (sesiones anteriores), su etiqueta."""
    return r.get("token") or r["etiqueta"].replace(" (vista 1)", "")


_PALABRAS_PERSONA = ("people", "person", "feet", "foot", "toes", "hands", "skin", "nails",
                     "persona", "gente", "pies", "pie ", "dedos", "manos", "piel", "uñas")


def _guia_sin_personas(guia):
    """Quita de la guía de marca las frases que hablan de personas, pies o manos:
    en un video de solo producto esas frases empujan al modelo a meter un pie."""
    frases = [f.strip() for f in guia.replace("\n", " ").split(".") if f.strip()]
    utiles = [f for f in frases if not any(p in f.lower() for p in _PALABRAS_PERSONA)]
    return (". ".join(utiles) + ".") if utiles else ""

# Bloque del enfoque unboxing en español (spec 2026-09-26 §B5: extraído para
# que TEXTOS["es"]["enfoques"]["unboxing"] y ENFOQUES["unboxing"]["bloque"]
# compartan el mismo texto, sin cambiar ni una letra del de siempre).
ENFOQUES_UNBOXING_ES = (
    "ENFOQUE UNBOXING: la escena es una persona recibiendo su compra. Empieza con la caja o "
    "bolsa cerrada sobre la mesa o en sus manos, la abre con curiosidad y saca el producto; "
    "termina mostrándolo de cerca, feliz de estrenarlo. Solo se ven las manos y, si acaso, "
    "parte del cuerpo; el producto es lo que la cámara busca."
)

# Enfoques de una misma idea. Cuando la persona pide N versiones, se genera una
# por enfoque, en este orden, y la tarjeta dice cuál es cuál.
ENFOQUES = {
    "producto": {
        "nombre": N_("Solo producto"),
        "descripcion": N_("El producto solo, sin nadie: vacío, sin usar, sobre la superficie o flotando."),
        "con_persona": False,
        "bloque": None,
    },
    "persona": {
        "nombre": N_("Con persona"),
        "descripcion": N_("Una persona real usando el producto de forma natural; el producto sigue siendo el protagonista."),
        "con_persona": True,
        "bloque": None,
    },
    "unboxing": {
        "nombre": N_("Unboxing"),
        "descripcion": N_("Alguien recibe la compra y abre la caja o bolsa hasta descubrir el producto, con la emoción de estrenarlo."),
        "con_persona": True,
        "bloque": ENFOQUES_UNBOXING_ES,
    },
    # Crear sin referencias ni producto (2026-09-25): no rota con los demás
    # (ORDEN_ENFOQUES) y armar() devuelve el texto de la persona tal cual.
    "libre": {
        "nombre": N_("Solo texto"),
        "descripcion": N_("Sin referencias ni producto: el modelo recibe el texto tal cual, sin marca ni logos."),
        "con_persona": False,
        "bloque": None,
    },
}
ORDEN_ENFOQUES = ("producto", "persona", "unboxing")


def enfoques_para(n, con_persona=False, elegidos=None):
    """Qué enfoque lleva cada una de las n versiones (1-3). La persona marca
    los enfoques que quiere (`elegidos`, en cualquier orden); si marca menos
    que n se completa con los que faltan en el orden por defecto, y si marca
    más se recortan. Con una sola versión y nada marcado manda con_persona."""
    n = max(1, min(3, int(n)))
    validos = [e for e in (elegidos or []) if e in ENFOQUES]
    # sin duplicados, respetando el orden en que se marcaron
    lista = []
    for e in validos:
        if e not in lista:
            lista.append(e)
    if not lista and n == 1:
        lista = ["persona" if con_persona else "producto"]
    for e in ORDEN_ENFOQUES:
        if len(lista) >= n:
            break
        if e not in lista:
            lista.append(e)
    return lista[:n]


def _lineas_contexto(contexto, idioma="es"):
    """Líneas AUDIENCIA/TEMPORADA a partir del contexto de una campaña de
    sprint. Solo emite lo que viene; sin contexto no emite nada."""
    if not contexto:
        return []
    t = TEXTOS[idioma if idioma in TEXTOS else "es"]
    lineas = []
    p = contexto.get("persona") or {}
    partes_p = [str(p[k]).strip().rstrip(".") for k in ("resumen", "descripcion") if p.get(k)]
    if p.get("senales_visuales"):
        partes_p.append(f"{t['senales']}: " + ", ".join(str(s) for s in p["senales_visuales"]))
    if p.get("tono"):
        partes_p.append(f"{t['tono']}: {str(p['tono']).strip().rstrip('.')}")
    if partes_p:
        lineas.append(f"{t['audiencia']}: " + ". ".join(partes_p) + ".")
    temporada = contexto.get("temporada") or {}
    partes_t = [str(temporada[k]).strip().rstrip(".") for k in ("nombre", "contexto") if temporada.get(k)]
    mood = temporada.get("mood_visual") or {}
    if mood.get("paleta"):
        partes_t.append(f"{t['paleta']}: " + ", ".join(str(c) for c in mood["paleta"]))
    if mood.get("luz"):
        partes_t.append(f"{t['luz']}: {str(mood['luz']).strip().rstrip('.')}")
    if mood.get("elementos"):
        partes_t.append(f"{t['elementos']}: " + ", ".join(str(e) for e in mood["elementos"]))
    if partes_t:
        lineas.append(f"{t['temporada']}: " + ". ".join(partes_t) + ".")
    return lineas


# Vocabulario cerrado de cámara de la Etapa 1 (spec director §2.1.5): id ->
# cómo se escribe el movimiento en el prompt (verbo + velocidad + punto final,
# como piden las guías de cámara de Kling y Alibaba), por idioma del proyecto
# (spec 2026-09-26 §B5) — SÍ está cubierto por §B5: la fase 3, ronda de
# revisión, encontró que `_bloque_planos` metía este texto en español dentro
# de un prompt en inglés. La Etapa 2 del spec del director sustituye este
# vocabulario por presets_camara.
#
# `CAMARAS` (español) mantiene el nombre y el dict de siempre porque
# `director.py` lo usa como la lista de ids válidos, no solo como texto:
# `", ".join(flowplus_prompt.CAMARAS)` arma el vocabulario que se le muestra a
# Claude y `p.get("camara") not in flowplus_prompt.CAMARAS` valida su
# respuesta — los dos iteran las LLAVES del dict, así que siguen funcionando
# igual. `CAMARAS_EN` traduce los mismos ids; `_bloque_planos` elige el dict
# según `idioma`.
CAMARAS = {
    "estatico": "cámara fija sobre trípode, horizonte nivelado, sin movimiento",
    "dolly_in": "la cámara avanza en línea recta hacia el sujeto, despacio y a velocidad constante, sin zoom",
    "dolly_out": "la cámara retrocede en línea recta alejándose del sujeto, despacio y a velocidad constante, sin zoom",
    "paneo_izq": "paneo suave de derecha a izquierda desde un punto fijo, horizonte nivelado",
    "paneo_der": "paneo suave de izquierda a derecha desde un punto fijo, horizonte nivelado",
    "tilt_arriba": "la cámara inclina lentamente hacia arriba desde un punto fijo",
    "tilt_abajo": "la cámara inclina lentamente hacia abajo desde un punto fijo",
    "travelling_lateral": "la cámara se desplaza de lado acompañando al sujeto, a su misma velocidad",
    "seguimiento_mano": "cámara en mano que sigue al sujeto con un ligero temblor natural",
    "orbita_corta": "la cámara rodea al sujeto en un arco corto de menos de 45 grados",
    "orbita_360": "la cámara da una vuelta completa alrededor del sujeto a velocidad constante",
    "grua_arriba": "la cámara se eleva verticalmente mientras mantiene al sujeto en cuadro",
    "cenital": "vista cenital fija, la cámara mira al sujeto desde arriba en vertical",
    "macro_a_abierto": "empieza en un macro de la textura y se aleja de forma continua hasta un plano abierto",
    "zoom_in": "zoom óptico lento hacia el sujeto sin mover la cámara",
    "crash_zoom": "zoom brusco y rápido hacia el sujeto en menos de un segundo",
    "dolly_zoom": "la cámara retrocede mientras hace zoom hacia el sujeto, el fondo se deforma y el sujeto no",
    "bullet_time": "el movimiento se congela y la cámara orbita alrededor de la escena detenida",
    "whip_pan": "paneo rapidísimo con desenfoque de movimiento que corta a la siguiente acción",
    "pov_objeto": "punto de vista desde el propio objeto, la cámara va pegada a él",
}

CAMARAS_EN = {
    "estatico": "camera fixed on a tripod, level horizon, no movement",
    "dolly_in": "the camera moves straight toward the subject, slowly and at a constant speed, no zoom",
    "dolly_out": "the camera moves straight away from the subject, slowly and at a constant speed, no zoom",
    "paneo_izq": "smooth pan from right to left from a fixed point, level horizon",
    "paneo_der": "smooth pan from left to right from a fixed point, level horizon",
    "tilt_arriba": "the camera tilts slowly upward from a fixed point",
    "tilt_abajo": "the camera tilts slowly downward from a fixed point",
    "travelling_lateral": "the camera moves sideways alongside the subject, at the subject's own speed",
    "seguimiento_mano": "handheld camera following the subject with a slight natural shake",
    "orbita_corta": "the camera circles the subject in a short arc of less than 45 degrees",
    "orbita_360": "the camera makes one full turn around the subject at a constant speed",
    "grua_arriba": "the camera rises vertically while keeping the subject in frame",
    "cenital": "fixed overhead shot, the camera looks straight down at the subject from above",
    "macro_a_abierto": "starts on a macro shot of the texture and pulls back continuously to a wide shot",
    "zoom_in": "slow optical zoom toward the subject without moving the camera",
    "crash_zoom": "a sudden, fast zoom toward the subject in under a second",
    "dolly_zoom": "the camera pulls back while zooming toward the subject, the background warps and the subject doesn't",
    "bullet_time": "motion freezes and the camera orbits around the frozen scene",
    "whip_pan": "an extremely fast pan with motion blur that cuts to the next action",
    "pov_objeto": "point of view from the object itself, the camera stays glued to it",
}
CAMARAS_POR_IDIOMA = {"es": CAMARAS, "en": CAMARAS_EN}


# Cómo se pasa de un plano al siguiente, con la frase literal de la guía
# multi-shot de Wan («Hard cut transition», alibabacloud.com/help/en/model-studio/
# text-to-video-prompt). Sin decirlo, Wan improvisa: en la prueba real del
# 2026-09-20 (docs/investigacion/2026-09-20-prueba-tokens-idioma.md) fundió los
# dos planos con la sandalia semitransparente. Va en inglés como el cierre de
# sonido: es un token del fabricante, no texto para la persona.
CORTE = "Hard cut."


def _bloque_planos(planos, con_sonido, idioma="es"):
    """Líneas `Shot N (a-bs): plano, cámara. Acción. Sonido: ...` (el sonido
    solo cuando la sesión lo pide); a partir del segundo plano la línea abre con
    `Hard cut.` (CORTE). Un id de cámara desconocido es un error de programación
    (el director ya lo validó): se lanza, no se disimula."""
    t = TEXTOS[idioma if idioma in TEXTOS else "es"]
    cams = CAMARAS_POR_IDIOMA[idioma if idioma in CAMARAS_POR_IDIOMA else "es"]
    lineas = []
    for i, p in enumerate(planos):
        cam = cams.get(p.get("camara"))
        if cam is None:
            raise ValueError(f"Movimiento de cámara desconocido: {p.get('camara')!r}")
        accion = str(p.get("accion") or "").strip().rstrip(".")
        accion = accion[:1].upper() + accion[1:]
        corte = f"{CORTE} " if i > 0 else ""
        linea = f"Shot {int(p['n'])} ({int(p['inicio_s'])}-{int(p['fin_s'])}s): {corte}{p.get('plano', '').strip()}, {cam}. {accion}."
        sonido = str(p.get("sonido") or "").strip().rstrip(".")
        if con_sonido and sonido:
            linea += f" {t['sonido_plano']}: {sonido}."
        lineas.append(linea)
    return lineas


# Textos fijos que van al modelo, por idioma del proyecto (spec 2026-09-26
# §B4-§B5, `idiomas.de_proyecto`). El texto de la persona (acción central,
# sonido, guía de marca, regla de cada activo) nunca entra acá: solo las
# etiquetas y frases que arma este módulo. Los tokens de referencia
# (Image N / Video N) y "Hard cut." siguen en inglés en los dos idiomas
# (no viven en este diccionario).
TEXTOS = {
    "es": {
        "sonido": "SONIDO", "sonido_plano": "Sonido", "sin_voz": "Sin diálogo hablado ni música de fondo.",
        "ambiente": "ambiente natural de la escena", "escena": "ESCENA", "audiencia": "AUDIENCIA",
        "temporada": "TEMPORADA", "senales": "Señales visuales", "tono": "Tono", "paleta": "Paleta", "luz": "Luz",
        "elementos": "Elementos", "personaje": "PERSONAJE", "misma_persona": "la misma persona",
        "producto_exacto": "PRODUCTO EXACTO", "es_el_producto": "es el producto",
        "es_personaje": "(sus vistas son la misma persona)", "entorno": "ENTORNO", "es": "es",
        "fidelidad": ("FIDELIDAD: los productos que aparecen en las imágenes de referencia se reproducen "
                      "idénticos — forma, color, textura y cualquier logotipo tal como se ve. No inventes ni "
                      "cambies letras, logos, etiquetas ni textos."),
        "logo": ("LOGO OFICIAL: {et} muestra el logotipo real de la marca. Si el logo se ve en el video, "
                 "es exactamente ese; nunca otro."),
        "video_ref": "{et}: referencia de movimiento, ritmo y encuadre de cámara; no copies sus objetos ni personas.",
        "con_personaje": ("CON PERSONA: la única persona en escena es {nombres}, exactamente como en sus referencias. "
                          "No aparece nadie más. Manos y pies anatómicamente correctos."),
        "con_persona": ("CON PERSONA: las personas son reales y naturales, captadas en movimiento; manos y pies "
                        "anatómicamente correctos (cinco dedos, dedos relajados y juntos, uñas naturales). "
                        "El producto es el protagonista; la persona lo acompaña."),
        "estilo": "ESTILO DE MARCA", "evitar": "EVITAR",
        "prohibido": ["texto inventado", "logos inventados", "marcas de agua", "subtítulos"],
        "prohibido_sin_persona": ["personas", "pies", "manos"],
        "recordatorio": "Recordatorio final: el producto permanece solo y sin nadie durante todo el video.",
        # Bloques por enfoque (ENFOQUES[...]["bloque"]), en su propio
        # subdiccionario para no compartir espacio de nombres con las
        # etiquetas de arriba (una id de enfoque nunca debe poder pisar, p.
        # ej., la llave "escena" o "sonido" de una futura etiqueta nueva).
        "enfoques": {"unboxing": ENFOQUES_UNBOXING_ES},
    },
    "en": {
        "sonido": "SOUND", "sonido_plano": "Sound", "sin_voz": "No spoken dialogue and no background music.",
        "ambiente": "natural ambient sound of the scene", "escena": "SCENE", "audiencia": "AUDIENCE",
        "temporada": "SEASON", "senales": "Visual cues", "tono": "Tone", "paleta": "Palette", "luz": "Light",
        "elementos": "Elements", "personaje": "CHARACTER", "misma_persona": "the same person",
        "producto_exacto": "EXACT PRODUCT", "es_el_producto": "is the product",
        "es_personaje": "(all their views are the same person)", "entorno": "SETTING", "es": "is",
        "fidelidad": ("FIDELITY: the products shown in the reference images are reproduced identically — "
                      "shape, color, texture and any logo exactly as seen. Do not invent or change letters, logos, "
                      "labels or text."),
        "logo": ("OFFICIAL LOGO: {et} shows the brand's real logo. If the logo appears in the video, it is exactly "
                 "that one; never another."),
        "video_ref": "{et}: reference for camera movement, pacing and framing; do not copy its objects or people.",
        "con_personaje": ("WITH PERSON: the only person in the scene is {nombres}, exactly as in their references. "
                          "Nobody else appears. Anatomically correct hands and feet."),
        "con_persona": ("WITH PERSON: people are real and natural, caught in motion; anatomically correct hands and "
                        "feet (five toes and fingers, relaxed and together, natural nails). The product is the star; "
                        "the person accompanies it."),
        "estilo": "BRAND STYLE", "evitar": "AVOID",
        "prohibido": ["invented text", "invented logos", "watermarks", "subtitles"],
        "prohibido_sin_persona": ["people", "feet", "hands"],
        "recordatorio": "Final reminder: the product stays alone, with nobody, for the whole video.",
        "enfoques": {"unboxing": (
            "UNBOXING FOCUS: the scene is a person receiving their purchase. It starts with the closed box "
            "or bag on the table or in their hands; they open it with curiosity and take the product out; "
            "it ends showing it up close, happy to use it for the first time. Only the hands and, at most, "
            "part of the body are seen; the product is what the camera looks for."
        )},
    },
}


# Alias para no romper importadores de las constantes de antes de TEXTOS
# (spec 2026-09-26 §B5): siguen siendo el texto en español, ahora leído del
# diccionario por idioma.
SIN_VOZ_NI_MUSICA = TEXTOS["es"]["sin_voz"]
SONIDO_AMBIENTE = TEXTOS["es"]["ambiente"]


def _linea_sonido(sonido, con_sonido, cierre=None, idioma="es"):
    """Línea SONIDO (spec estudio S1). Con texto lo usa tal cual; sin texto y
    con sonido pide el ambiente natural; sin ninguno no emite nada (el prompt
    queda idéntico al de antes). "Sin diálogo" evita las voces nativas de
    Kling (chino/inglés): la voz en español la pone final edition. `cierre`
    agrega la frase literal del fabricante (flowplus_modelos.cierre_sonido)
    al final de la línea. `idioma`: solo cambia la etiqueta y la frase fija,
    nunca el texto que escribió la persona (spec 2026-09-26 §B5)."""
    t = TEXTOS[idioma if idioma in TEXTOS else "es"]
    texto = (sonido or "").strip().rstrip(".")
    sufijo = f" {cierre}" if cierre else ""
    if texto:
        return f"{t['sonido']}: {texto}. {t['sin_voz']}{sufijo}"
    if con_sonido:
        return f"{t['sonido']}: {t['ambiente']}. {t['sin_voz']}{sufijo}"
    return None


def tal_cual(texto, referencias, sonido=None, idioma="es"):
    """Prompt de la generación directa de Crear: el texto de la persona sin
    nada agregado de fondo (ni marca, ni EVITAR, ni reglas, ni logos). Solo
    cambia sus menciones @Imagen N por el token que ve el modelo y, si ella
    escribió un sonido, lo agrega como línea SONIDO — en el idioma del
    proyecto (spec 2026-09-26 §B5): `idioma` solo cambia la etiqueta
    (SONIDO/SOUND), nunca el texto de la persona."""
    t = TEXTOS[idioma if idioma in TEXTOS else "es"]
    partes = [sustituir_tokens(texto.strip(), referencias)]
    texto_sonido = (sonido or "").strip().rstrip(".")
    if texto_sonido:
        partes.append(f"{t['sonido']}: {texto_sonido}.")
    return "\n".join(partes)


def armar(texto, referencias, con_persona=False, guia_marca="", negative_marca=None, logos=None, enfoque=None,
          contexto=None, sonido=None, con_sonido=False, planos=None, cierre_sonido=None, idioma="es"):
    """texto: lo que escribió la persona (se respeta íntegro).
    referencias: [{tipo, etiqueta, producto?}] ya numeradas.
    logos: [{etiqueta}] referencias de logo agregadas por el proyecto.
    enfoque: clave de ENFOQUES (manda sobre con_persona) o None.
    contexto: opcional (Sprints): {"persona": {resumen, descripcion, tono,
    senales_visuales}, "temporada": {nombre, contexto, mood_visual}}; agrega
    las líneas AUDIENCIA y TEMPORADA. Con None el prompt es idéntico.
    sonido / con_sonido: línea SONIDO después de la ESCENA (ver
    _linea_sonido); con sonido=None y con_sonido=False el prompt es idéntico.
    planos: lista de planos del director (spec §2); con planos el bloque
    `Shot N` sustituye a `ESCENA:` y a la línea `SONIDO:`.
    cierre_sonido: frase literal del fabricante (`flowplus_modelos.cierre_sonido`)
    que cierra el sonido; None = sin cierre (prompt idéntico al anterior).
    idioma: idioma del proyecto (spec 2026-09-26 §B4-§B5, `idiomas.de_proyecto`);
    solo cambia las frases fijas de este módulo (TEXTOS) — el texto de la
    persona, la guía de marca y la regla de cada activo nunca se traducen.
    "es" (por defecto) deja el prompt idéntico al de siempre.
    Con enfoque `libre` (solo texto) el prompt es el texto de la persona (o los
    planos del director) y, si se pide, la línea de sonido: sin marca, sin
    reglas de producto ni EVITAR.
    Devuelve el prompt completo (str)."""
    if enfoque == "libre":
        if planos:
            partes = _bloque_planos(planos, con_sonido, idioma)
            if con_sonido and cierre_sonido:
                partes.append(cierre_sonido)
        else:
            partes = [texto.strip()]
            linea_sonido = _linea_sonido(sonido, con_sonido, cierre=cierre_sonido, idioma=idioma)
            if linea_sonido:
                partes.append(linea_sonido)
        return "\n".join(partes)
    t = TEXTOS[idioma if idioma in TEXTOS else "es"]
    partes = []
    info_enfoque = ENFOQUES.get(enfoque) if enfoque else None
    if info_enfoque:
        con_persona = info_enfoque["con_persona"]
    personajes = [r for r in referencias if r.get("categoria") == "personaje"]
    if personajes:
        # Con un personaje del catálogo la escena lleva persona sí o sí: ese personaje.
        con_persona = True

    # Nota: ya no hardcodeamos "VIDEO DE PRODUCTO SOLO" — el usuario edita libremente
    # el prompt con el esquema de frames/tomas que prefiera. El prompt es completamente
    # editable en la UI.

    # --- Contexto de campaña (Sprints): audiencia y temporada ---
    partes.extend(_lineas_contexto(contexto, idioma))

    productos = [r for r in referencias if r.get("producto")]
    imagenes = _lista(referencias, "imagen")
    videos = _lista(referencias, "video")

    # --- Activos del catálogo: cada uno con su regla de consistencia ---
    vistos = set()
    for r in referencias:
        if not r.get("activo") or r["activo"] in vistos:
            continue
        vistos.add(r["activo"])
        cat = r.get("categoria", "producto")
        vistas = [x for x in referencias if x.get("activo") == r["activo"]]
        et = _nombre(r)
        if cat == "personaje" and len(vistas) > 1 and all(x.get("token") for x in vistas):
            et = f"{r['activo']} ({', '.join(x['token'] for x in vistas)}: {t['misma_persona']})"
            partes.append(f"{t['personaje']}: {et}. {r.get('regla') or ''}".strip())
            continue
        if cat == "producto":
            partes.append(f"{t['producto_exacto']}: {et} {t['es_el_producto']} \"{r['activo']}\". {r.get('regla') or ''}".strip())
        elif cat == "personaje":
            partes.append(f"{t['personaje']}: {et} {t['es']} \"{r['activo']}\" {t['es_personaje']}. {r.get('regla') or ''}".strip())
        elif cat == "entorno":
            partes.append(f"{t['entorno']}: {et} {t['es']} \"{r['activo']}\". {r.get('regla') or ''}".strip())
    if not vistos and imagenes:
        partes.append(t["fidelidad"])
    if logos:
        et = ", ".join(_nombre(l) for l in logos)
        partes.append(t["logo"].format(et=et))
    if videos:
        et = ", ".join(_nombre(v) for v in videos)
        partes.append(t["video_ref"].format(et=et))

    # --- Personas ---
    if con_persona and personajes:
        nombres = ", ".join(sorted({r["activo"] for r in personajes}))
        partes.append(t["con_personaje"].format(nombres=nombres))
    elif con_persona:
        partes.append(t["con_persona"])

    # --- Guía de marca (invariantes) ---
    if guia_marca:
        partes.append(f"{t['estilo']}: {_guia_sin_personas(guia_marca) if not con_persona else guia_marca.strip()}")

    # --- Enfoque (unboxing, etc.) ---
    if info_enfoque and info_enfoque["bloque"]:
        partes.append(t["enfoques"].get(enfoque, info_enfoque["bloque"]))

    # --- Escena: los planos del director, o el texto de la persona íntegro ---
    if planos:
        partes.extend(_bloque_planos(planos, con_sonido, idioma))
        if con_sonido and cierre_sonido:
            partes.append(cierre_sonido)
    else:
        partes.append(f"{t['escena']}: {sustituir_tokens(texto.strip(), referencias)}")
        linea_sonido = _linea_sonido(sonido, con_sonido, cierre=cierre_sonido, idioma=idioma)
        if linea_sonido:
            partes.append(linea_sonido)

    # --- Prohibiciones (los modelos no aceptan negative_prompt) ---
    prohibido = list(t["prohibido"])
    if not con_persona:
        prohibido = list(t["prohibido_sin_persona"]) + prohibido
    if negative_marca:
        prohibido.append(negative_marca.strip().rstrip(".")[:400])
    partes.append(f"{t['evitar']}: " + ", ".join(prohibido) + ".")
    if not con_persona:
        partes.append(t["recordatorio"])

    return "\n".join(partes)
