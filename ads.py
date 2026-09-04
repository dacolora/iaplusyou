"""
Estado del módulo de Publicidad (Meta Ads) — un JSON por cliente, mismo
patrón que swaps.py: sin base de datos, sin conocer nada de meta_ads/.

Cualquier módulo de contenido (cambiar calzado, Nueva idea, CreativeFlowPlus)
puede encolar algo acá con crear(...) sin conocer nada más de este archivo —
"contrato Enviar a Publicidad", ver
docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)


def _ruta(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "ads.json")


def cargar(cliente):
    ruta = _ruta(cliente)
    if not os.path.exists(ruta):
        return {}
    with open(ruta) as f:
        return json.load(f)


def _guardar(cliente, data):
    ruta = _ruta(cliente)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def crear(cliente, fuente, fuente_id, contenido_url, contenido_tipo, nombre):
    """Contrato mínimo de "Enviar a Publicidad". Devuelve el id nuevo."""
    data = cargar(cliente)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ad_id = f"ad_{ts}"
    data[ad_id] = {
        "fuente": fuente,
        "fuente_id": fuente_id,
        "contenido_url": contenido_url,
        "contenido_tipo": contenido_tipo,
        "nombre": nombre,
        "estado": "en_cola",
        "objetivo": None,
        "presupuesto_diario_usd": None,
        "dias": None,
        "audiencia": None,
        "meta_ids": {"campaign_id": None, "adset_id": None, "ad_id": None, "creative_id": None},
        "metricas": {"impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0, "actualizado_en": None},
        "error": None,
        "creado_en": datetime.now().isoformat(),
    }
    _guardar(cliente, data)
    return ad_id


def actualizar(cliente, ad_id, **campos):
    data = cargar(cliente)
    if ad_id not in data:
        raise KeyError(f"No existe el anuncio {ad_id} para {cliente}")
    data[ad_id].update(campos)
    _guardar(cliente, data)


def eliminar(cliente, ad_id):
    data = cargar(cliente)
    data.pop(ad_id, None)
    _guardar(cliente, data)
