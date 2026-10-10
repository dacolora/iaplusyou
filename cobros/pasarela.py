"""Qué pasarela cobra las recargas (spec planes 2026-10-09 §5): Wompi si
tiene sus cuatro llaves (y, si son de pruebas, el servidor es local); si no,
Bold si tiene la suya; si no, ninguna (solo la recarga manual del admin).
Bold queda en el código, apagado sin llaves (ruling 8)."""
from cobros import bold, wompi


def para_recargas():
    """"wompi", "bold" o None."""
    if wompi.configurado():
        return "wompi"
    if bold.configurado():
        return "bold"
    return None
