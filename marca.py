"""
Identidad de marca de un cliente: imágenes/videos de referencia + una guía de
estilo (texto) que se inyecta en cada generación de prompts para que el
contenido mantenga siempre el mismo look — paleta, tono, iluminación, etc.

Un archivo marca.json por cliente:
{
  "guia_estilo": "texto...",
  "style_id": null,          # opcional: si el cliente ya tiene un style_id de Higgsfield
  "style_strength": 0.5,
  "actualizado_en": "..."
}

Las referencias en sí (imágenes/videos subidos) NO se listan aquí — se leen
directo de la carpeta clientes/<cliente>/marca/, igual que personajes/.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "marca.json")
    return os.path.join(BASE_DIR, "marca.json")


def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {"guia_estilo": "", "style_id": None, "style_strength": 0.5, "actualizado_en": None}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["actualizado_en"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
