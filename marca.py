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


def _root_path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "marca", "root.json")


def cargar_root(cliente):
    """Sistema de marca formal (invariantes + variables libres + prompt_blocks ya
    redactados) si este cliente trae el suyo propio — ej. Happyflops. Se guarda tal
    cual la fuente de verdad del cliente, en clientes/<cliente>/marca/root.json, sin
    reinterpretar nada. Devuelve None si no existe."""
    if not cliente:
        return None
    path = _root_path(cliente)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guia_efectiva(cliente):
    """Lo que se inyecta al generar prompts: el invariant_block real del root.json
    del cliente si existe (autoritativo, nunca reinterpretado por Claude), o si no,
    la guía de estilo en texto libre (generada por visión o escrita a mano)."""
    root = cargar_root(cliente)
    if root:
        return root.get("prompt_blocks", {}).get("invariant_block", "")
    return cargar(cliente).get("guia_estilo", "")


def negative_prompt_efectivo(cliente):
    """El negative prompt real del root.json del cliente, si existe."""
    root = cargar_root(cliente)
    if root:
        return root.get("prompt_blocks", {}).get("negative_prompt")
    return None
