"""
Manifiesto de estado de cada video: pendiente / rechazado / publicado.

Un archivo estado_videos.json por cliente (o en la raíz si no hay --cliente), con
un registro por brief_id: prompt, urls, plataformas a publicar, y en qué estado va.
"""
import os

import _json_store

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "estado_videos.json")
    return os.path.join(BASE_DIR, "estado_videos.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, estado):
    _json_store.guardar(_path(cliente), estado)


def listar_clientes():
    """Nombres de carpeta bajo clientes/, ordenados alfabéticamente."""
    clientes_dir = os.path.join(BASE_DIR, "clientes")
    if not os.path.isdir(clientes_dir):
        return []
    return sorted(
        d for d in os.listdir(clientes_dir)
        if os.path.isdir(os.path.join(clientes_dir, d)) and not d.startswith(".")
    )
