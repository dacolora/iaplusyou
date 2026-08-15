"""
Ideas y sus prompts candidatos, esperando aprobación ANTES de gastar créditos
generando nada. Un archivo prompts_pendientes.json por cliente.

Estructura: cada "idea" es un contenedor con varios prompts variantes debajo.

{
  "idea_20260814_130501": {
    "idea": "texto de la idea original",
    "creado_en": "...",
    "prompts": {
      "idea_20260814_130501_p1": {
        "prompt": "...",
        "image_url": "...",           # foto del personaje, referencia de identidad
        "model": "kling-2.1-pro",
        "duration": 5,
        "cfg_scale": 0.5,
        "aspect_ratio": "9:16",
        "title": "...",
        "caption": "...",
        "platforms": [...],
        "estado": "pendiente",        # pendiente -> imagen_pendiente -> (se va a estado_videos.json)
        "imagen_url": null,           # se llena al generar la imagen candidata
        "imagen_local": null,
        "creado_en": "..."
      }
    }
  }
}

Flujo en 3 pasos, cada uno con su propia aprobación:
  1. "pendiente": Claude (en el chat, o el formulario "Nueva idea" del dashboard)
     propuso el prompt. Al aprobarlo se genera una IMAGEN candidata (barata,
     ~1.5 créditos) con el modelo soul/reference — mantiene la identidad del
     personaje pero puede variar fondo/pose/estilo/aspect_ratio según el prompt.
  2. "imagen_pendiente": esa imagen queda para aprobar o descartar. Al aprobarla
     se genera el VIDEO real (caro, ~8 créditos) usando esa imagen ya aprobada
     como referencia — así nunca se gasta en video algo que no gustó primero.
  3. Al generarse el video, el prompt sale de este archivo y entra a
     estado_videos.json con estado "pendiente" (la revisión final de siempre,
     la que dispara la publicación en redes al aprobar).
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)

MODELOS_VALIDOS = ("kling-2.1-pro", "dop-standard")
ASPECT_RATIOS_VALIDOS = ("9:16", "16:9", "4:3", "3:4", "1:1", "2:3", "3:2")


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


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _slug(texto, max_len=30):
    s = "".join(c if c.isalnum() else "_" for c in texto.strip().lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:max_len] or "idea"


def agregar_idea(cliente, idea_texto, items):
    """Crea una idea nueva con sus prompts variantes.

    items: lista de dicts, cada uno con al menos {"prompt", "image_url"} y
    opcionalmente {"model", "duration", "cfg_scale", "title", "caption", "platforms"}.
    Devuelve el idea_id creado.
    """
    data = cargar(cliente)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    idea_id = f"idea_{ts}_{_slug(idea_texto, 20)}"
    while idea_id in data:
        idea_id += "x"

    ahora = datetime.now().isoformat()
    idea_prompts = {}
    for i, item in enumerate(items, start=1):
        pid = f"{idea_id}_p{i}"
        idea_prompts[pid] = {
            "prompt": item["prompt"],
            "image_url": item["image_url"],
            "model": item.get("model", "kling-2.1-pro"),
            "duration": item.get("duration", 5),
            "cfg_scale": item.get("cfg_scale", 0.5),
            "aspect_ratio": item.get("aspect_ratio", "9:16"),
            "title": item.get("title", pid),
            "caption": item.get("caption", item["prompt"]),
            "platforms": item.get("platforms", []),
            "estado": "pendiente",
            "imagen_url": None,
            "imagen_local": None,
            "creado_en": ahora,
        }

    data[idea_id] = {"idea": idea_texto, "creado_en": ahora, "prompts": idea_prompts}
    guardar(cliente, data)
    return idea_id


def encontrar_prompt(data, prompt_id):
    """Busca un prompt por id en cualquier idea. Devuelve (idea_id, prompt_entry) o (None, None)."""
    for idea_id, idea in data.items():
        if prompt_id in idea.get("prompts", {}):
            return idea_id, idea["prompts"][prompt_id]
    return None, None
