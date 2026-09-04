"""
Cliente para Wan 2.7 Video Edit (Alibaba) vía WaveSpeed AI — edita un video
existente de verdad: toma video + hasta 3 imágenes de referencia y preserva
movimiento/escena, cambiando solo lo que el prompt pide (no es generación con
referencias como Wan 3.0/Seedance).

Esquema verificado contra wavespeed.ai/models/alibaba/wan-2.7/video-edit:
  POST https://api.wavespeed.ai/api/v3/alibaba/wan-2.7/video-edit
    { "video": url, "prompt": str, "images": [url, ...] }
  -> { "data": { "id": "<prediction_id>", ... } }
  GET https://api.wavespeed.ai/api/v3/predictions/{id}/result  (polling)
  -> { "data": { "status": "completed"|"failed"|..., "outputs": [...] } }

OJO: la página de documentación dice que `images` acepta "1–9 imágenes", pero
la API real rechaza más de 3 con un 400 explícito ("must contain at most 3
item(s)") — confirmado con una llamada real (1 sep 2026). Confía en este
límite (3), no en lo que diga la doc si algún día cambia el mensaje de error.

Precio verificado en la misma página: $0.10/seg en 720p, $0.15/seg en 1080p
(factura tanto el video de entrada como el de salida). Mínimo 2s, máximo 10s
facturados. Tiempo de generación reportado: ~383s en promedio.

Requiere WAVESPEED_API_KEY en el .env (wavespeed.ai > API Keys).
"""
import requests

from providers import wavespeed_common

MODEL_PATH = "alibaba/wan-2.7/video-edit"

COSTO_USD_POR_SEGUNDO = {"720p": 0.10, "1080p": 0.15}


def editar_video(video_url, prompt, referencias_urls=None, resolution="720p", on_progreso=None):
    """Edita video_url reemplazando lo que indique el prompt, usando hasta 3
    referencias_urls como guía visual. Devuelve la URL pública del video
    resultante. on_progreso se propaga tal cual al poll (ver wavespeed_common)."""
    payload = {"video": video_url, "prompt": prompt}
    if referencias_urls:
        payload["images"] = referencias_urls[:3]
    if resolution:
        payload["resolution"] = resolution

    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{MODEL_PATH}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({MODEL_PATH}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = wavespeed_common.poll_hasta_listo(
        prediction_id, "Wan 2.7 Video Edit", on_progreso=on_progreso,
    )
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"Wan 2.7 Video Edit no devolvió ningún video: {resultado}")
    return outputs[0]


def estimate_video(duration_seconds=5, resolution="720p"):
    costo_seg = COSTO_USD_POR_SEGUNDO.get(resolution, COSTO_USD_POR_SEGUNDO["720p"])
    # Factura entrada + salida — esto es solo el costo de la salida; el real
    # termina siendo más alto según cuánto dure el video que subiste.
    return {"credits": None, "usd": round(costo_seg * max(duration_seconds, 2), 3)}
