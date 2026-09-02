"""
Estado del flujo "cambiar calzado": el usuario sube una foto, elige un producto del
catálogo, y se genera una versión de esa foto con el calzado reemplazado — nada más
cambia. Un archivo swaps.json por cliente.
"""
import os
from datetime import datetime

import _json_store

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "swaps.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)


def crear(cliente, foto_original_local, producto_id, aspect_ratio, proveedor="nano_banana", tipo="foto"):
    data = cargar(cliente)
    swap_id = "swap_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    data[swap_id] = {
        "foto_original_local": foto_original_local,
        "producto_id": producto_id,
        "aspect_ratio": aspect_ratio,
        "proveedor": proveedor,
        "tipo": tipo,
        "estado": "generando",
        "resultado_url": None,
        "resultado_local": None,
        "credits": None,
        "usd": None,
        "evaluacion": None,
        "error": None,
        "creado_en": datetime.now().isoformat(),
    }
    guardar(cliente, data)
    return swap_id


def actualizar(cliente, swap_id, **campos):
    data = cargar(cliente)
    if swap_id not in data:
        return False
    data[swap_id].update(campos)
    guardar(cliente, data)
    return True


def eliminar(cliente, swap_id):
    data = cargar(cliente)
    if swap_id in data:
        del data[swap_id]
        guardar(cliente, data)
        return True
    return False
