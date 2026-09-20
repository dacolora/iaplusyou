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
"""
import re


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

# Enfoques de una misma idea. Cuando la persona pide N versiones, se genera una
# por enfoque, en este orden, y la tarjeta dice cuál es cuál.
ENFOQUES = {
    "producto": {
        "nombre": "Solo producto",
        "descripcion": "El producto solo, sin nadie: vacío, sin usar, sobre la superficie o flotando.",
        "con_persona": False,
        "bloque": None,
    },
    "persona": {
        "nombre": "Con persona",
        "descripcion": "Una persona real usando el producto de forma natural; el producto sigue siendo el protagonista.",
        "con_persona": True,
        "bloque": None,
    },
    "unboxing": {
        "nombre": "Unboxing",
        "descripcion": "Alguien recibe la compra y abre la caja o bolsa hasta descubrir el producto, con la emoción de estrenarlo.",
        "con_persona": True,
        "bloque": (
            "ENFOQUE UNBOXING: la escena es una persona recibiendo su compra. Empieza con la caja o "
            "bolsa cerrada sobre la mesa o en sus manos, la abre con curiosidad y saca el producto; "
            "termina mostrándolo de cerca, feliz de estrenarlo. Solo se ven las manos y, si acaso, "
            "parte del cuerpo; el producto es lo que la cámara busca."
        ),
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


def _lineas_contexto(contexto):
    """Líneas AUDIENCIA/TEMPORADA a partir del contexto de una campaña de
    sprint. Solo emite lo que viene; sin contexto no emite nada."""
    if not contexto:
        return []
    lineas = []
    p = contexto.get("persona") or {}
    partes_p = [str(p[k]).strip().rstrip(".") for k in ("resumen", "descripcion") if p.get(k)]
    if p.get("senales_visuales"):
        partes_p.append("Señales visuales: " + ", ".join(str(s) for s in p["senales_visuales"]))
    if p.get("tono"):
        partes_p.append(f"Tono: {str(p['tono']).strip().rstrip('.')}")
    if partes_p:
        lineas.append("AUDIENCIA: " + ". ".join(partes_p) + ".")
    t = contexto.get("temporada") or {}
    partes_t = [str(t[k]).strip().rstrip(".") for k in ("nombre", "contexto") if t.get(k)]
    mood = t.get("mood_visual") or {}
    if mood.get("paleta"):
        partes_t.append("Paleta: " + ", ".join(str(c) for c in mood["paleta"]))
    if mood.get("luz"):
        partes_t.append(f"Luz: {str(mood['luz']).strip().rstrip('.')}")
    if mood.get("elementos"):
        partes_t.append("Elementos: " + ", ".join(str(e) for e in mood["elementos"]))
    if partes_t:
        lineas.append("TEMPORADA: " + ". ".join(partes_t) + ".")
    return lineas


# Vocabulario cerrado de cámara de la Etapa 1 (spec director §2.1.5): id ->
# cómo se escribe el movimiento en el prompt (verbo + velocidad + punto final,
# como piden las guías de cámara de Kling y Alibaba). La Etapa 2 lo sustituye
# por presets_camara.
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


def _bloque_planos(planos, con_sonido):
    """Líneas `Shot N (a-bs): plano, cámara. Acción. Sonido: ...` (el sonido
    solo cuando la sesión lo pide). Un id de cámara desconocido es un error
    de programación (el director ya lo validó): se lanza, no se disimula."""
    lineas = []
    for p in planos:
        cam = CAMARAS.get(p.get("camara"))
        if cam is None:
            raise ValueError(f"Movimiento de cámara desconocido: {p.get('camara')!r}")
        accion = str(p.get("accion") or "").strip().rstrip(".")
        accion = accion[:1].upper() + accion[1:]
        linea = f"Shot {int(p['n'])} ({int(p['inicio_s'])}-{int(p['fin_s'])}s): {p.get('plano', '').strip()}, {cam}. {accion}."
        sonido = str(p.get("sonido") or "").strip().rstrip(".")
        if con_sonido and sonido:
            linea += f" Sonido: {sonido}."
        lineas.append(linea)
    return lineas


SIN_VOZ_NI_MUSICA = "Sin diálogo hablado ni música de fondo."
SONIDO_AMBIENTE = "ambiente natural de la escena"


def _linea_sonido(sonido, con_sonido, cierre=None):
    """Línea SONIDO (spec estudio S1). Con texto lo usa tal cual; sin texto y
    con sonido pide el ambiente natural; sin ninguno no emite nada (el prompt
    queda idéntico al de antes). "Sin diálogo" evita las voces nativas de
    Kling (chino/inglés): la voz en español la pone final edition. `cierre`
    agrega la frase literal del fabricante (flowplus_modelos.cierre_sonido)
    al final de la línea."""
    texto = (sonido or "").strip().rstrip(".")
    sufijo = f" {cierre}" if cierre else ""
    if texto:
        return f"SONIDO: {texto}. {SIN_VOZ_NI_MUSICA}{sufijo}"
    if con_sonido:
        return f"SONIDO: {SONIDO_AMBIENTE}. {SIN_VOZ_NI_MUSICA}{sufijo}"
    return None


def armar(texto, referencias, con_persona=False, guia_marca="", negative_marca=None, logos=None, enfoque=None,
          contexto=None, sonido=None, con_sonido=False, planos=None, cierre_sonido=None):
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
    Devuelve el prompt completo (str)."""
    partes = []
    info_enfoque = ENFOQUES.get(enfoque) if enfoque else None
    if info_enfoque:
        con_persona = info_enfoque["con_persona"]
    personajes = [r for r in referencias if r.get("categoria") == "personaje"]
    if personajes:
        # Con un personaje del catálogo la escena lleva persona sí o sí: ese personaje.
        con_persona = True

    # Lo primero que lee el modelo pesa más: si no hay persona, se dice antes que
    # nada (Wan 3.0 asocia "sandalia" con "pie" con mucha fuerza y, dicho solo al
    # final, lo ignoraba en el último tramo del video).
    if not con_persona:
        partes.append(
            "VIDEO DE PRODUCTO SOLO, SIN NINGUNA PERSONA: el producto aparece vacío, sin usar, "
            "sobre la superficie o flotando. Nadie lo lleva puesto. No hay pies, piernas, manos ni "
            "cuerpo en ningún momento del video, ni al principio ni al final."
        )

    # --- Contexto de campaña (Sprints): audiencia y temporada ---
    partes.extend(_lineas_contexto(contexto))

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
            et = f"{r['activo']} ({', '.join(x['token'] for x in vistas)}: la misma persona)"
            partes.append(f"PERSONAJE: {et}. {r.get('regla') or ''}".strip())
            continue
        if cat == "producto":
            partes.append(f"PRODUCTO EXACTO: {et} es el producto \"{r['activo']}\". {r.get('regla') or ''}".strip())
        elif cat == "personaje":
            partes.append(f"PERSONAJE: {et} es \"{r['activo']}\" (sus vistas son la misma persona). {r.get('regla') or ''}".strip())
        elif cat == "entorno":
            partes.append(f"ENTORNO: {et} es \"{r['activo']}\". {r.get('regla') or ''}".strip())
    if not vistos and imagenes:
        partes.append(
            "FIDELIDAD: los productos que aparecen en las imágenes de referencia se reproducen "
            "idénticos — forma, color, textura y cualquier logotipo tal como se ve. No inventes ni "
            "cambies letras, logos, etiquetas ni textos."
        )
    if logos:
        et = ", ".join(_nombre(l) for l in logos)
        partes.append(
            f"LOGO OFICIAL: {et} muestra el logotipo real de la marca. Si el logo se ve en el video, "
            "es exactamente ese; nunca otro."
        )
    if videos:
        et = ", ".join(_nombre(v) for v in videos)
        partes.append(f"{et}: referencia de movimiento, ritmo y encuadre de cámara; no copies sus objetos ni personas.")

    # --- Personas ---
    if con_persona and personajes:
        nombres = ", ".join(sorted({r["activo"] for r in personajes}))
        partes.append(
            f"CON PERSONA: la única persona en escena es {nombres}, exactamente como en sus referencias. "
            "No aparece nadie más. Manos y pies anatómicamente correctos."
        )
    elif con_persona:
        partes.append(
            "CON PERSONA: las personas son reales y naturales, captadas en movimiento; manos y pies "
            "anatómicamente correctos (cinco dedos, dedos relajados y juntos, uñas naturales). "
            "El producto es el protagonista; la persona lo acompaña."
        )

    # --- Guía de marca (invariantes) ---
    if guia_marca:
        partes.append(f"ESTILO DE MARCA: {_guia_sin_personas(guia_marca) if not con_persona else guia_marca.strip()}")

    # --- Enfoque (unboxing, etc.) ---
    if info_enfoque and info_enfoque["bloque"]:
        partes.append(info_enfoque["bloque"])

    # --- Escena: los planos del director, o el texto de la persona íntegro ---
    if planos:
        partes.extend(_bloque_planos(planos, con_sonido))
        if con_sonido and cierre_sonido:
            partes.append(cierre_sonido)
    else:
        partes.append(f"ESCENA: {sustituir_tokens(texto.strip(), referencias)}")
        linea_sonido = _linea_sonido(sonido, con_sonido, cierre=cierre_sonido)
        if linea_sonido:
            partes.append(linea_sonido)

    # --- Prohibiciones (los modelos no aceptan negative_prompt) ---
    prohibido = ["texto inventado", "logos inventados", "marcas de agua", "subtítulos"]
    if not con_persona:
        prohibido = ["personas", "pies", "manos"] + prohibido
    if negative_marca:
        prohibido.append(negative_marca.strip().rstrip(".")[:400])
    partes.append("EVITAR: " + ", ".join(prohibido) + ".")
    if not con_persona:
        partes.append("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")

    return "\n".join(partes)
