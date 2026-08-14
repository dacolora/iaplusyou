"""
Prompts candidatos generados a partir de una idea, esperando aprobación ANTES de
gastar créditos generando el video. Un archivo prompts_pendientes.json por cliente.

Flujo: alguien (Claude, en el chat) escribe aquí varias variantes de prompt para
una idea. El admin las revisa en el dashboard (con costo estimado en créditos) y
aprueba o rechaza cada una. Aprobar dispara la generación real del video.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "prompts_pendientes.json")
    return os.path.join(BASE_DIR, "prompts_pendientes.json")


def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, prompts):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)


def agregar(cliente, idea, items, prefijo=None):
    """Agrega varias variantes de prompt para una misma idea.

    items: lista de dicts, cada uno con al menos {"prompt", "image_url"} y
    opcionalmente {"model", "title", "caption", "platforms"}.
    Devuelve la lista de ids agregados.
    """
    prompts = cargar(cliente)
    slug = prefijo or idea.strip().lower()
    slug = "".join(c if c.isalnum() else "_" for c in slug)[:40].strip("_") or "idea"

    existentes = [pid for pid in prompts if pid.startswith(slug)]
    inicio = len(existentes) + 1

    nuevos_ids = []
    for i, item in enumerate(items, start=inicio):
        pid = f"{slug}_{i:02d}"
        prompts[pid] = {
            "idea": idea,
            "prompt": item["prompt"],
            "image_url": item["image_url"],
            "model": item.get("model", "kling-2.1-pro"),
            "title": item.get("title", pid),
            "caption": item.get("caption", item["prompt"]),
            "platforms": item.get("platforms", []),
            "estado": "pendiente",
            "creado_en": datetime.now().isoformat(),
        }
        nuevos_ids.append(pid)

    guardar(cliente, prompts)
    return nuevos_ids
