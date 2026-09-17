"""
Paquete de conectores de tienda. `por_tipo("shopify")` devuelve la clase
registrada con `@registrar`; los módulos de tienda (`conectores.shopify`,
`conectores.woo`, `conectores.meli`) se importan perezosamente la primera
vez que se pide su tipo, así importar `conectores` no arrastra sus
dependencias. `csv_excel` y `url` no son conectores registrados (no hay
credenciales ni sync): se usan directo como `conectores.csv_excel.leer(...)`.
"""
import importlib

from .base import Conector, ErrorConector  # noqa: F401 (re-export)

REGISTRO = {}


def registrar(cls):
    """Decorador: registra `cls` bajo `cls.tipo`. Devuelve la clase intacta."""
    if not getattr(cls, "tipo", None):
        raise ValueError("Un conector registrado necesita `tipo`.")
    REGISTRO[cls.tipo] = cls
    return cls


def por_tipo(tipo):
    """Clase del conector para `tipo`; importa `conectores.<tipo>` si aún no
    está registrado. ValueError si no existe."""
    tipo = (tipo or "").strip()
    if tipo not in REGISTRO and tipo.isidentifier():
        try:
            importlib.import_module(f"conectores.{tipo}")
        except ModuleNotFoundError as e:
            # solo se tolera que NO exista el módulo del tipo; si el módulo
            # existe pero le falta una dependencia, ese error sí debe verse
            if e.name != f"conectores.{tipo}":
                raise
    if tipo not in REGISTRO:
        raise ValueError(f"Tipo de tienda no soportado: {tipo or '(vacío)'}")
    return REGISTRO[tipo]


def tipos():
    """Tipos registrados hasta ahora (en orden de registro)."""
    return list(REGISTRO)
