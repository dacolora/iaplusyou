"""
Registro de fuentes de comentarios por `tipo`, con carga perezosa (como
`conectores.por_tipo`). `texto` y `csv` corren en la ruta; `CONECTADAS`
(reddit, youtube, apify) corren en el worker (`nicho_recolectar`) y cada una
necesita sus llaves del `.env` raíz (`LLAVES`); `llaves_faltantes` solo mira
`bool(os.environ.get(var))`, nunca el valor.
"""
import importlib
import os

REGISTRO = {
    "texto": ("nicho.fuentes.texto", "FuenteTexto"),
    "csv": ("nicho.fuentes.archivo", "FuenteArchivo"),
    "reddit": ("nicho.fuentes.reddit", "FuenteReddit"),
}
NOMBRES = {"texto": "Texto pegado", "csv": "CSV o Excel", "reddit": "Reddit", "youtube": "YouTube",
           "apify": "Amazon / TikTok (Apify)"}
CONECTADAS = ("reddit", "youtube", "apify")
LLAVES = {
    "reddit": ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"),
    "youtube": ("YOUTUBE_API_KEY",),
    "apify": ("APIFY_TOKEN",),
}


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> la clase de la fuente. KeyError si el tipo no está registrado."""
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)


def llaves_faltantes(tipo):
    """Variables de entorno vacías para esa fuente (lista vacía = lista para usar)."""
    return [v for v in LLAVES.get(tipo, ()) if not (os.environ.get(v) or "").strip()]
