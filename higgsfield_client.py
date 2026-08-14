"""
Cliente simple para la API de Higgsfield (generación de video imagen-a-video).

Requiere dos variables de entorno: HF_API_KEY_ID y HF_API_KEY_SECRET.
Se leen automáticamente desde un archivo .env en esta misma carpeta (ver .env.example).
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://platform.higgsfield.ai"

# Endpoints confirmados en la documentación oficial (imagen -> video).
ENDPOINTS = {
    "dop-standard": "/higgsfield-ai/dop/standard",
    "kling-2.1-pro": "/kling-video/v2.1/pro/image-to-video",
}


def _auth_header():
    key_id = os.environ.get("HF_API_KEY_ID")
    key_secret = os.environ.get("HF_API_KEY_SECRET")
    if not key_id or not key_secret:
        raise RuntimeError(
            "Faltan HF_API_KEY_ID / HF_API_KEY_SECRET. Configúralas en tu archivo .env"
        )
    return {"Authorization": f"Key {key_id}:{key_secret}"}


def generate_video(image_url, prompt, model="kling-2.1-pro", extra_params=None):
    """Lanza una generación de imagen-a-video.

    image_url debe ser una URL PÚBLICA (Higgsfield descarga la imagen desde ahí,
    no acepta archivos subidos directamente en este flujo simple).

    Devuelve el JSON de respuesta, que incluye request_id, status_url y cancel_url.
    """
    if model not in ENDPOINTS:
        raise ValueError(f"Modelo desconocido: {model}. Opciones: {list(ENDPOINTS)}")
    url = BASE_URL + ENDPOINTS[model]
    payload = {"image_url": image_url, "prompt": prompt}
    if extra_params:
        payload.update(extra_params)
    headers = {**_auth_header(), "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def estimate_video(image_url, prompt, model="kling-2.1-pro", extra_params=None):
    """Consulta cuántos créditos (y USD) costaría esta generación, sin lanzarla ni gastar
    créditos. Devuelve un dict {"credits": float, "usd": float}.
    """
    if model not in ENDPOINTS:
        raise ValueError(f"Modelo desconocido: {model}. Opciones: {list(ENDPOINTS)}")
    url = BASE_URL + "/estimate" + ENDPOINTS[model]
    payload = {"image_url": image_url, "prompt": prompt}
    if extra_params:
        payload.update(extra_params)
    headers = {**_auth_header(), "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {"credits": float(data["credits"]), "usd": float(data["usd"])}


def poll_until_done(status_url, interval_seconds=5, timeout_seconds=600):
    """Consulta status_url cada `interval_seconds` hasta que el video esté listo.

    La primera vez imprime la respuesta cruda: la documentación pública no muestra
    el formato exacto de esta respuesta, así que la primera corrida real nos sirve
    para confirmar los nombres de campo y ajustar el script si hace falta.
    """
    headers = _auth_header()
    start = time.time()
    seen_shape = False
    while time.time() - start < timeout_seconds:
        resp = requests.get(status_url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not seen_shape:
            print("Respuesta cruda de status (para depurar el formato):")
            print(data)
            seen_shape = True
        status = data.get("status") or data.get("state")
        if status in ("completed", "succeeded", "success", "done"):
            return data
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError(f"La generación falló: {data}")
        time.sleep(interval_seconds)
    raise TimeoutError("Se agotó el tiempo esperando el resultado (timeout_seconds).")


def extract_video_url(result_json):
    """Busca la URL pública del video dentro de la respuesta final de Higgsfield.

    Esta misma URL (hospedada por Higgsfield) sirve para publicar directamente en
    Instagram, que exige una URL pública en vez de un archivo local.
    """
    candidates = []
    for key in ("video", "output", "video_url", "result", "url", "output_url"):
        val = result_json.get(key)
        if isinstance(val, str):
            candidates.append(val)
        elif isinstance(val, dict):
            for k2 in ("url", "video_url"):
                if k2 in val:
                    candidates.append(val[k2])
        elif isinstance(val, list) and val:
            first = val[0]
            candidates.append(first if isinstance(first, str) else first.get("url"))

    if not candidates:
        raise RuntimeError(
            f"No encontré una URL de video en la respuesta. JSON crudo: {result_json}"
        )
    return candidates[0]


def download_result(result_json, out_path):
    """Descarga a out_path el video referenciado en la respuesta final."""
    video_url = extract_video_url(result_json)
    r = requests.get(video_url, timeout=120)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path
