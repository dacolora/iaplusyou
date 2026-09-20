"""
Registro de fuentes de comentarios por `tipo`, con carga perezosa (como
`conectores.por_tipo`): la Parte 2 agrega reddit, youtube y apify acá mismo.
"""
import importlib

REGISTRO = {
    "texto": ("nicho.fuentes.texto", "FuenteTexto"),
    "csv": ("nicho.fuentes.archivo", "FuenteArchivo"),
}
NOMBRES = {"texto": "Texto pegado", "csv": "CSV o Excel", "reddit": "Reddit", "youtube": "YouTube",
           "apify": "Amazon / TikTok (Apify)"}


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> la clase de la fuente. KeyError si el tipo no está registrado."""
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)
