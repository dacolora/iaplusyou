"""
Cliente para Wan 3.0 (Alibaba) vía WaveSpeed AI — genera un video NUEVO guiado
por referencias de personaje/producto/escena y un prompt, hasta 30s en una
sola llamada, con audio nativo opcional. A diferencia de wan-2.7/video-edit
(providers/wavespeed_client.py), esto NO edita un video existente — es
generación desde cero a partir de imágenes de referencia, más parecido en
espíritu a Higgsfield Soul, pero con más duración y más referencias
simultáneas (hasta 10 imágenes).

Esquema verificado contra wavespeed.ai/models/alibaba/wan-3.0/reference-to-video
(1 sep 2026):
  POST https://api.wavespeed.ai/api/v3/alibaba/wan-3.0/reference-to-video
    { "prompt": str, "resolution": "480p"|"720p"|"1080p", "aspect_ratio": str,
      "duration": int (2-30), "enable_audio": bool,
      "reference_images": [url, ...] (hasta 10),
      "reference_videos": [url, ...] (opcional, hasta 5, no usado por este cliente),
      "reference_audios": [url, ...] (opcional, hasta 5, no usado por este cliente) }
  -> { "data": { "id": "<prediction_id>", ... } }
  GET https://api.wavespeed.ai/api/v3/predictions/{id}/result  (poll, mismo
      patrón que wan-2.7/video-edit — ver providers/wavespeed_common.py)
  -> { "data": { "status": "completed"|"failed"|..., "outputs": [...] } }

Precio verificado en la misma página (1 sep 2026): $0.05/seg (480p),
$0.10/seg (720p), $0.20/seg (1080p). Factura solo la salida (a diferencia de
wan-2.7/video-edit, que factura entrada+salida — esto es generación nueva, no
hay "entrada" que facturar).

NOTA (2 sep 2026): esquema confirmado con una llamada real contra la API en
vivo (2s, 480p, una imagen de referencia real de `happyflops`) — devolvió un
video generado exitosamente (`.../predictions/09053c080b1844b9b7b3d095cf4e41af/1.mp4`).
El payload documentado arriba es correcto tal cual está.

Requiere WAVESPEED_API_KEY en el .env (la misma que ya usa wavespeed_client.py).
"""
import requests

from providers import wavespeed_common

MODEL_PATH = "alibaba/wan-3.0/reference-to-video"

COSTO_USD_POR_SEGUNDO = {"480p": 0.05, "720p": 0.10, "1080p": 0.20}


def generar_video(prompt, reference_images, duration=12, resolution="720p",
                   aspect_ratio="9:16", enable_audio=False):
    """reference_images: lista de URLs públicas, en el orden
    personajes -> productos -> escenas (así @Imagen 1, @Imagen 2... del prompt
    final corresponden exactamente al orden que ve el modelo). Devuelve la URL
    pública del video resultante."""
    if not reference_images:
        raise ValueError("Wan 3.0 reference-to-video necesita al menos una imagen de referencia.")

    payload = {
        "prompt": prompt,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
        "enable_audio": enable_audio,
        "reference_images": reference_images[:10],
    }
    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{MODEL_PATH}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({MODEL_PATH}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = wavespeed_common.poll_hasta_listo(prediction_id, "Wan 3.0", timeout_seconds=1200)
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"Wan 3.0 no devolvió ningún video: {resultado}")
    return outputs[0]


def estimate_video(duration=12, resolution="720p"):
    costo_seg = COSTO_USD_POR_SEGUNDO.get(resolution, COSTO_USD_POR_SEGUNDO["720p"])
    return {"credits": None, "usd": round(costo_seg * duration, 3)}
