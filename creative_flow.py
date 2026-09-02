"""
Estado del tab CreativeFlowPlus: variables simples del Paso 1/2 -> prompt final
relleno por Claude a partir de la plantilla maestra -> video generado con
Wan 3.0. Un archivo creative_flow_pendientes.json por cliente.
"""
import os
from datetime import datetime

import _json_store

BASE_DIR = os.path.dirname(__file__)

MODOS_VALIDOS = ("A", "B")


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "creative_flow_pendientes.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)


def crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central,
          duracion_objetivo, tono, modo):
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"Modo inválido: {modo}. Opciones: {MODOS_VALIDOS}")
    data = cargar(cliente)
    cf_id = "cf_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    data[cf_id] = {
        "personajes_ids": personajes_ids,
        "productos_ids": productos_ids,
        "escenas_ids": escenas_ids,
        "accion_central": accion_central,
        "duracion_objetivo": duracion_objetivo,
        "tono": tono,
        "modo": modo,
        "estado": "prompt_pendiente",
        "prompt_relleno": None,
        "video_url": None,
        "video_local": None,
        "credits": None,
        "usd": None,
        "error": None,
        "creado_en": datetime.now().isoformat(),
    }
    guardar(cliente, data)
    return cf_id


def actualizar(cliente, cf_id, **campos):
    data = cargar(cliente)
    if cf_id not in data:
        return False
    data[cf_id].update(campos)
    guardar(cliente, data)
    return True


def eliminar(cliente, cf_id):
    data = cargar(cliente)
    if cf_id in data:
        del data[cf_id]
        guardar(cliente, data)
        return True
    return False
