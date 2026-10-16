"""Texto ajeno dentro de un prompt a Claude: lo que viene de afuera (una tienda, un anuncio, un guion, un ángulo) va
entre <etiqueta>…</etiqueta> y nunca puede cerrar su propio bloque.

Por qué existe (auditoría de seguridad de PND-037, 2026-10-16): cada módulo tenía su `_sin_cierre` con un solo
`replace` que distingue mayúsculas. «</DESCRIPCION>» pasaba, y «</desc</descripcion>ripcion>» se rearmaba al quitar el
de adentro: el dato salía de su bloque y se leía como instrucción (OWASP LLM01).
"""
import re


def sin_cierre(texto, etiqueta):
    """`texto` sin NINGÚN cierre de `etiqueta`: sin distinguir mayúsculas ni espacios y repitiendo hasta que no quede
    ninguno."""
    patron = re.compile(r"<\s*/\s*" + re.escape(etiqueta) + r"\s*>", re.IGNORECASE)
    t = str(texto or "")
    while True:
        nuevo = patron.sub("", t)
        if nuevo == t:
            return t
        t = nuevo
