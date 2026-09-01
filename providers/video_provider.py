"""
Capa única de generación de video — mismo patrón que image_provider.py. El resto
del programa pide "generame un video con este proveedor" sin saber si por dentro
es Higgsfield (lanzar+poll) o Seedance vía fal.ai (llamada directa).
"""
import requests

import higgsfield_client
from providers import seedance_client

PROVEEDORES_VALIDOS = ("higgsfield", "seedance")


def generar_video(proveedor, imagen_url, prompt, local_path, duration=5, aspect_ratio="9:16",
                   negative_prompt=None, extra_params=None):
    """Genera un video y lo guarda en local_path. Devuelve {"credits", "usd"} — para
    Seedance "credits" siempre es None (cobra directo en USD, sin créditos)."""
    if proveedor == "seedance":
        video_url = seedance_client.generate_video(
            imagen_url, prompt, duration=duration, aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
        )
        resp = requests.get(video_url, timeout=120)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        return seedance_client.estimate_video(duration=duration)

    if proveedor == "higgsfield":
        launch = higgsfield_client.generate_video(
            image_url=imagen_url, prompt=prompt, model="kling-2.1-pro", extra_params=extra_params,
        )
        result = higgsfield_client.poll_until_done(launch["status_url"])
        higgsfield_client.download_result(result, local_path)
        return higgsfield_client.estimate_video(imagen_url, prompt, model="kling-2.1-pro", extra_params=extra_params)

    raise ValueError(f"Proveedor de video desconocido: {proveedor}. Opciones: {PROVEEDORES_VALIDOS}")
