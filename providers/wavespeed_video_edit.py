"""
Los editores de video "pesados" (premium) de WaveSpeed AI — todos toman un
video real + referencias y editan preservando movimiento/escena, igual que
Wan 2.7 Video Edit (wavespeed_client.py) pero de proveedores distintos y más
caros/potentes. Comparten el mismo patrón encolar+poll vía wavespeed_common.

Esquemas verificados contra wavespeed.ai (1 sep 2026) — cada modelo tiene su
propio nombre de campo para las referencias, así que NO asumas que son
intercambiables sin revisar MODELOS abajo:
  - Seedance 2.5 Video-Edit (bytedance/seedance-2.5/video-edit):
    `video` + `prompt` + `reference_images` (opcional). $0.22/seg en 720p
    (factura entrada+salida), hasta 4k. La más cara y de mejor calidad.
  - Kling Omni Video O3 Pro Video-Edit (kwaivgi/kling-video-o3-pro/video-edit):
    `video` + `prompt` + `images` (hasta 4). $0.168/seg, mínimo 3s, máx 10s
    facturados — mismo precio por segundo que Kling O1, pero modelo más nuevo.
  - Luma Ray 3.2 Video Edit (luma/ray-3.2/video-edit):
    `video` + `prompt` + `start_image` (UNA sola imagen, no lista).
    Resolución 540p/720p/1080p, duración fija 5s o 10s. Desde $0.72 (540p/5s).
"""
import requests

from providers import wavespeed_common

MODELOS = {
    "seedance25_edit": {
        "path": "bytedance/seedance-2.5/video-edit",
        "nombre": "Seedance 2.5 Video Edit",
        "campo_referencias": "reference_images",
        "max_referencias": 4,
        "costo_usd_por_segundo": 0.22,  # 720p; 480p 0.11, 1080p 0.55, 4k 1.10
    },
    "kling_o3_pro_edit": {
        "path": "kwaivgi/kling-video-o3-pro/video-edit",
        "nombre": "Kling Omni O3 Pro Video Edit",
        "campo_referencias": "images",
        "max_referencias": 4,
        "costo_usd_por_segundo": 0.168,
    },
    "luma_ray32_edit": {
        "path": "luma/ray-3.2/video-edit",
        "nombre": "Luma Ray 3.2 Video Edit",
        "campo_referencias": "start_image",  # una sola imagen, no lista
        "max_referencias": 1,
        "costo_usd_por_segundo": 0.144,  # 540p/5s; sube con resolución/duración
    },
}


def editar_video(modelo_id, video_url, prompt, referencias_urls=None, on_progreso=None):
    """Edita video_url según prompt, usando el modelo_id indicado (ver
    MODELOS). Devuelve la URL pública del video resultante. on_progreso se
    propaga tal cual al poll (ver wavespeed_common.poll_hasta_listo)."""
    info = MODELOS[modelo_id]
    payload = {"video": video_url, "prompt": prompt}

    referencias_urls = referencias_urls or []
    if referencias_urls:
        if info["max_referencias"] == 1:
            payload[info["campo_referencias"]] = referencias_urls[0]
        else:
            payload[info["campo_referencias"]] = referencias_urls[: info["max_referencias"]]

    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{info['path']}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({info['path']}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = wavespeed_common.poll_hasta_listo(
        prediction_id, info["nombre"], on_progreso=on_progreso,
    )
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"{info['nombre']} no devolvió ningún video: {resultado}")
    return outputs[0]


def estimate_video(modelo_id, duration_seconds=5):
    costo_seg = MODELOS[modelo_id]["costo_usd_por_segundo"]
    return {"credits": None, "usd": round(costo_seg * duration_seconds, 3)}
