"""
Cliente para Kling O1 Video Edit (Kuaishou) vía fal.ai — el único modelo que
realmente EDITA un video existente (no genera uno nuevo desde una imagen fija):
preserva el movimiento y la escena original, y solo cambia lo que el prompt le pide.
Acepta hasta 4 imágenes de referencia citables como @Image1, @Image2... en el prompt.

Requiere FAL_KEY en el .env (el mismo que usa fal_client.py).
"""
from providers import fal_client

MODEL_PATH = "fal-ai/kling-video/o1/standard/video-to-video/edit"

# $/segundo verificado en la página oficial de precios de fal.ai (29 ago 2026).
COSTO_USD_POR_SEGUNDO = 0.168

# Restricción documentada por fal.ai (confirmada empíricamente vía el error
# real que devuelve la API: "Video dimensions are too small. Minimum width is
# 720 pixels."): el video de entrada necesita al menos 720px de ancho.
ANCHO_MINIMO_PX = 720


def editar_video(video_url, prompt, referencias_urls=None, keep_audio=False):
    """Edita video_url (URL pública, mp4/mov, 3-10s, mínimo 720px de ancho,
    máx 200MB) según prompt. referencias_urls: hasta 4 URLs públicas de
    imágenes citables en el prompt como @Image1, @Image2, etc. Devuelve la
    URL pública del video editado."""
    payload = {"prompt": prompt, "video_url": video_url, "keep_audio": keep_audio}
    if referencias_urls:
        payload["image_urls"] = referencias_urls[:4]

    data = fal_client.llamar(MODEL_PATH, payload)

    video = data.get("video") or {}
    url = video.get("url")
    if not url:
        raise RuntimeError(f"Kling O1 no devolvió una URL de video: {data}")
    return url


def estimate_video(duration_seconds=5):
    """Sin endpoint de estimación — costo conocido de antemano por segundo."""
    return {"credits": None, "usd": round(COSTO_USD_POR_SEGUNDO * duration_seconds, 3)}
