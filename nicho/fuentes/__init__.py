"""
Registro de fuentes de comentarios por `tipo`, con carga perezosa (como
`conectores.por_tipo`). `texto` y `csv` corren en la ruta; `CONECTADAS`
(reddit, youtube, apify) corren en el worker (`nicho_recolectar`) y cada una
necesita sus llaves del `.env` raíz (`LLAVES`); `llaves_faltantes` solo mira
`bool(os.environ.get(var))`, nunca el valor. `PLATAFORMAS` (amazon, meli,
tiktok_shop) corren solo dentro de la investigación automática del nicho, no
como una fuente manual más.
"""
import importlib
import os

from idiomas import N_

REGISTRO = {
    "texto": ("nicho.fuentes.texto", "FuenteTexto"),
    "csv": ("nicho.fuentes.archivo", "FuenteArchivo"),
    "reddit": ("nicho.fuentes.reddit", "FuenteReddit"),
    "youtube": ("nicho.fuentes.youtube", "FuenteYouTube"),
    "apify": ("nicho.fuentes.apify", "FuenteApify"),
}
NOMBRES = {"texto": N_("Texto pegado"), "csv": N_("CSV o Excel"), "reddit": "Reddit", "youtube": "YouTube",
           "apify": "Amazon / TikTok (Apify)"}
CONECTADAS = ("reddit", "youtube", "apify")
LLAVES = {
    "reddit": ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"),
    "youtube": ("YOUTUBE_API_KEY",),
    "apify": ("APIFY_TOKEN",),
}
PLATAFORMAS = ("amazon", "meli", "tiktok_shop")     # claves de nicho.fuentes.plataformas (corren solo dentro de la investigación)
EN_WORKER = CONECTADAS + PLATAFORMAS                 # lo que nicho_recolectar acepta como `fuente`
NOMBRES.update({"amazon": "Amazon", "meli": "Mercado Libre", "tiktok_shop": "TikTok Shop"})
LLAVES.update({clave: ("APIFY_TOKEN",) for clave in PLATAFORMAS})


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> la clase de la fuente (o, para una plataforma, una fábrica que se llama
    igual, sin argumentos). KeyError si el tipo no está registrado."""
    if tipo in PLATAFORMAS:
        from nicho.fuentes.plataforma import fabrica
        return fabrica(tipo)
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)


def llaves_faltantes(tipo):
    """Variables de entorno vacías para esa fuente (lista vacía = lista para usar)."""
    return [v for v in LLAVES.get(tipo, ()) if not (os.environ.get(v) or "").strip()]
