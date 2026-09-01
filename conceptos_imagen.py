"""
Estado del flujo imagen-primero: una idea -> N escenas (conceptos) -> cada escena se
genera con AMBOS proveedores (Nano Banana e Higgsfield) -> se aprueban las imágenes
que sirvan -> cada imagen aprobada recibe sus propias propuestas de animación.

Un archivo conceptos_pendientes.json por cliente:
{
  "idea_20260827_140000_mi_idea": {
    "idea": "texto original",
    "creado_en": "...",
    "conceptos": {
      "concepto_1": {
        "texto": "descripción de la escena",
        "nano_banana": {
          "estado": "generando|listo|error|aprobado",
          "url": null, "local": null, "error": null,
          "usd": null,
          "animaciones": { "anim_1": {"prompt": "...", "estado": "pendiente", ...} }
        },
        "higgsfield": { ... misma forma, además "credits" ... }
      }
    }
  }
}

Cada entrada de "animaciones" tiene la misma forma que un prompt de video de
prompts.py, para poder reusar la lógica de generación de video sin reescribirla.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)

PROVEEDORES = ("nano_banana", "higgsfield")


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "conceptos_pendientes.json")


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


def crear_idea(cliente, idea_texto, escenas):
    """escenas: lista de strings (las descripciones generadas por Claude). Crea la
    idea con un concepto por escena, cada uno con sus dos proveedores en estado
    'generando' — el llamador es responsable de lanzar los jobs reales y actualizar
    cada entrada con marcar_imagen(). Devuelve idea_id."""
    data = cargar(cliente)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    idea_id = f"idea_{ts}_{_slug(idea_texto, 20)}"
    while idea_id in data:
        idea_id += "x"

    ahora = datetime.now().isoformat()
    conceptos = {}
    for i, texto in enumerate(escenas, start=1):
        conceptos[f"concepto_{i}"] = {
            "texto": texto,
            "nano_banana": {"estado": "generando", "url": None, "local": None, "error": None, "usd": None, "animaciones": {}},
            "higgsfield": {"estado": "generando", "url": None, "local": None, "error": None, "credits": None, "usd": None, "animaciones": {}},
        }

    data[idea_id] = {"idea": idea_texto, "creado_en": ahora, "conceptos": conceptos}
    guardar(cliente, data)
    return idea_id


def encontrar_concepto(data, idea_id, concepto_id):
    return data.get(idea_id, {}).get("conceptos", {}).get(concepto_id)


def marcar_imagen(cliente, idea_id, concepto_id, proveedor, **campos):
    """Actualiza los campos de data[idea_id]['conceptos'][concepto_id][proveedor] —
    ej. marcar_imagen(cliente, iid, cid, 'nano_banana', estado='listo', url=..., local=...)."""
    data = cargar(cliente)
    concepto = encontrar_concepto(data, idea_id, concepto_id)
    if not concepto or proveedor not in concepto:
        return False
    concepto[proveedor].update(campos)
    guardar(cliente, data)
    return True


def agregar_animaciones(cliente, idea_id, concepto_id, proveedor, prompts):
    """prompts: lista de strings (texto de animación). Las guarda como candidatas
    pendientes bajo esa imagen aprobada."""
    data = cargar(cliente)
    concepto = encontrar_concepto(data, idea_id, concepto_id)
    if not concepto:
        return False
    imagen = concepto[proveedor]
    ahora = datetime.now().isoformat()
    for i, texto in enumerate(prompts, start=1):
        aid = f"anim_{i}"
        imagen["animaciones"][aid] = {
            "prompt": texto,
            "estado": "pendiente",
            "creado_en": ahora,
        }
    guardar(cliente, data)
    return True


def encontrar_animacion(data, idea_id, concepto_id, proveedor, anim_id):
    concepto = encontrar_concepto(data, idea_id, concepto_id)
    if not concepto:
        return None
    return concepto[proveedor]["animaciones"].get(anim_id)
