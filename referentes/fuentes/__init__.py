"""
Registro de fuentes de barrido por `tipo`, con carga perezosa (como
`nicho.fuentes` y `conectores.por_tipo`). A diferencia de esos dos paquetes,
cada fuente aquí es un MÓDULO con tres funciones de nivel de módulo
(`estimar`/`probar`/`traer`), no una clase: `por_tipo` devuelve el módulo
mismo, no una instancia. `llaves_faltantes` solo mira
`bool(os.environ.get(var))`, nunca el valor.
"""
import importlib
import os

from idiomas import N_

REGISTRO = {
    "atria": "referentes.fuentes.atria",
    "apify": "referentes.fuentes.apify_adlibrary",
    "trendtrack": "referentes.fuentes.trendtrack",
}
# Se muestran con |traducir / idiomas.traducir (la clave no cambia).
NOMBRES = {"atria": N_("Atria (Ad Library de Meta)"), "apify": N_("Apify (Ad Library de Meta)"),
           "trendtrack": N_("TrendTrack (anuncios de Meta)")}
LLAVES = {
    "atria": ("ATRIA_API_KEY",),
    "apify": ("APIFY_TOKEN",),
    "trendtrack": ("TRENDTRACK_API_KEY",),
}
MODOS_POR_DEFECTO = ("palabra", "marca")


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> el módulo de la fuente. KeyError si el tipo no está registrado."""
    return importlib.import_module(REGISTRO[tipo])


def modos(tipo):
    """Modos de búsqueda que admite la fuente: `("palabra", "marca")` salvo que el
    módulo declare `MODOS` (TrendTrack solo busca por palabra clave)."""
    return tuple(getattr(por_tipo(tipo), "MODOS", MODOS_POR_DEFECTO))


def llaves_faltantes(tipo):
    """Variables de entorno vacías para esa fuente (lista vacía = lista para usar)."""
    return [v for v in LLAVES.get(tipo, ()) if not (os.environ.get(v) or "").strip()]
