"""
Manifiesto de estado de cada video: pendiente / rechazado / publicado.

Un archivo estado_videos.json por cliente (o en la raíz si no hay --cliente), con
un registro por brief_id: prompt, urls, plataformas a publicar, y en qué estado va.
"""
import json
import os

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "estado_videos.json")
    return os.path.join(BASE_DIR, "estado_videos.json")


def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, estado):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)
