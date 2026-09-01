"""
Cliente simple para Seedance 2.0 (ByteDance) vía fal.ai — el partner internacional
oficial de ByteDance para este modelo (no hace falta pasar por BytePlus/Volcengine
directo, que exige verificación de cuenta empresarial más pesada).

Requiere FAL_KEY en el .env. Consíguela en fal.ai (registro simple, sin
verificación de negocio) -> Dashboard -> API Keys.
"""
import os

import requests

BASE_URL = "https://fal.run/bytedance/seedance-2.0/image-to-video"

# $/segundo a 720p con audio, verificado en la página oficial de precios de fal.ai
# el 28 ago 2026 (ver ROADMAP.md) — NO usar cifras de blogs de terceros, ya nos
# equivocamos una vez con eso.
COSTO_USD_POR_SEGUNDO_720P = 0.473


def _api_key():
    key = os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError(
            "Falta FAL_KEY en tu .env. Consíguela en fal.ai (Dashboard > API Keys)."
        )
    return key


def generate_video(image_url, prompt, duration=5, aspect_ratio="9:16", negative_prompt=None):
    """Genera un video imagen-a-video con Seedance 2.0. Llamada síncrona (fal.run
    bloquea hasta tener el resultado, sin polling separado). Devuelve la URL
    pública del video ya generado."""
    payload = {
        "image_url": image_url,
        "prompt": prompt,
        "duration": duration,
        "resolution": "720p",
        "aspect_ratio": aspect_ratio,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    headers = {"Authorization": f"Key {_api_key()}", "Content-Type": "application/json"}
    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=600)
    resp.raise_for_status()
    data = resp.json()

    video = data.get("video") or {}
    url = video.get("url")
    if not url:
        raise RuntimeError(f"Seedance no devolvió una URL de video: {data}")
    return url


def estimate_video(duration=5):
    """Sin endpoint de estimación — costo aproximado conocido de antemano a 720p."""
    return {"credits": None, "usd": round(COSTO_USD_POR_SEGUNDO_720P * duration, 3)}
