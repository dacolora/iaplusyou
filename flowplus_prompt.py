"""
Arma el prompt final de FlowPlus a partir de lo que escribió la persona.

El texto de la persona se manda TAL CUAL (esa fue la decisión: sin plantilla
maestra de 11 secciones). Lo que sí se antepone es lo que evita los dos fallos
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
explícitas. Las referencias se nombran @Imagen N / @Video N / @Logo N en el
texto — los modelos las leen en lenguaje natural, no hay sintaxis oficial.
"""


def _lista(refs, tipo):
    return [r for r in refs if r.get("tipo") == tipo]


_PALABRAS_PERSONA = ("people", "person", "feet", "foot", "toes", "hands", "skin", "nails",
                     "persona", "gente", "pies", "pie ", "dedos", "manos", "piel", "uñas")


def _guia_sin_personas(guia):
    """Quita de la guía de marca las frases que hablan de personas, pies o manos:
    en un video de solo producto esas frases empujan al modelo a meter un pie."""
    frases = [f.strip() for f in guia.replace("\n", " ").split(".") if f.strip()]
    utiles = [f for f in frases if not any(p in f.lower() for p in _PALABRAS_PERSONA)]
    return (". ".join(utiles) + ".") if utiles else ""

def armar(texto, referencias, con_persona=False, guia_marca="", negative_marca=None, logos=None):
    """texto: lo que escribió la persona (se respeta íntegro).
    referencias: [{tipo, etiqueta, producto?}] ya numeradas.
    logos: [{etiqueta}] referencias de logo agregadas por el proyecto.
    Devuelve el prompt completo (str)."""
    partes = []

    # Lo primero que lee el modelo pesa más: si no hay persona, se dice antes que
    # nada (Wan 3.0 asocia "sandalia" con "pie" con mucha fuerza y, dicho solo al
    # final, lo ignoraba en el último tramo del video).
    if not con_persona:
        partes.append(
            "VIDEO DE PRODUCTO SOLO, SIN NINGUNA PERSONA: el producto aparece vacío, sin usar, "
            "sobre la superficie o flotando. Nadie lo lleva puesto. No hay pies, piernas, manos ni "
            "cuerpo en ningún momento del video, ni al principio ni al final."
        )

    productos = [r for r in referencias if r.get("producto")]
    imagenes = _lista(referencias, "imagen")
    videos = _lista(referencias, "video")

    # --- Fidelidad de producto y de marca ---
    if productos:
        nombres = "; ".join(f"{r['etiqueta']} es el producto \"{r['producto']}\"" for r in productos)
        partes.append(
            f"PRODUCTO EXACTO: {nombres}. Reprodúcelo idéntico a su referencia: misma forma, "
            "mismo color, misma textura y el mismo logotipo o marca tal como aparece en la imagen, "
            "en el mismo lugar. No inventes, cambies ni agregues letras, logos, etiquetas ni textos."
        )
    elif imagenes:
        partes.append(
            "FIDELIDAD: los productos que aparecen en las imágenes de referencia se reproducen "
            "idénticos — forma, color, textura y cualquier logotipo tal como se ve. No inventes ni "
            "cambies letras, logos, etiquetas ni textos."
        )
    if logos:
        et = ", ".join(l["etiqueta"] for l in logos)
        partes.append(
            f"LOGO OFICIAL: {et} muestra el logotipo real de la marca. Si el logo se ve en el video, "
            "es exactamente ese; nunca otro."
        )
    if videos:
        et = ", ".join(v["etiqueta"] for v in videos)
        partes.append(f"{et}: referencia de movimiento, ritmo y encuadre de cámara; no copies sus objetos ni personas.")

    # --- Personas ---
    if con_persona:
        partes.append(
            "CON PERSONA: las personas son reales y naturales, captadas en movimiento; manos y pies "
            "anatómicamente correctos (cinco dedos, dedos relajados y juntos, uñas naturales). "
            "El producto es el protagonista; la persona lo acompaña."
        )

    # --- Guía de marca (invariantes) ---
    if guia_marca:
        partes.append(f"ESTILO DE MARCA: {_guia_sin_personas(guia_marca) if not con_persona else guia_marca.strip()}")

    # --- Texto de la persona, íntegro ---
    partes.append(f"ESCENA: {texto.strip()}")

    # --- Prohibiciones (los modelos no aceptan negative_prompt) ---
    prohibido = ["texto inventado", "logos inventados", "marcas de agua", "subtítulos", "deformaciones"]
    if not con_persona:
        prohibido = ["personas", "pies", "manos"] + prohibido
    if negative_marca:
        prohibido.append(negative_marca.strip().rstrip(".")[:400])
    partes.append("EVITAR: " + ", ".join(prohibido) + ".")
    if not con_persona:
        partes.append("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")

    return "\n".join(partes)
