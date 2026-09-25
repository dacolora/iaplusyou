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

REGISTRO = {
    "atria": "referentes.fuentes.atria",
}
NOMBRES = {"atria": "Atria (Ad Library de Meta)"}
LLAVES = {
    "atria": ("ATRIA_API_KEY",),
}


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> el módulo de la fuente. KeyError si el tipo no está registrado."""
    return importlib.import_module(REGISTRO[tipo])


def llaves_faltantes(tipo):
    """Variables de entorno vacías para esa fuente (lista vacía = lista para usar)."""
    return [v for v in LLAVES.get(tipo, ()) if not (os.environ.get(v) or "").strip()]
