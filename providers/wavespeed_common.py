"""
Helpers compartidos por los clientes de WaveSpeed AI — autenticación y el poll
genérico contra /predictions/{id}/result, que usan por igual
providers/wavespeed_client.py (Wan 2.7 Video Edit) y providers/wan3_client.py
(Wan 3.0).
"""
import os
import time

import requests

BASE_URL = "https://api.wavespeed.ai/api/v3"


def api_key():
    key = os.environ.get("WAVESPEED_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta WAVESPEED_API_KEY en tu .env. Consíguela en wavespeed.ai (API Keys)."
        )
    return key


def headers():
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def poll_hasta_listo(prediction_id, nombre_modelo, interval_seconds=5, timeout_seconds=900):
    url = f"{BASE_URL}/predictions/{prediction_id}/result"
    inicio = time.time()
    while time.time() - inicio < timeout_seconds:
        resp = requests.get(url, headers=headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        estado = data.get("status")
        if estado == "completed":
            return data
        if estado in ("failed", "cancelled", "timeout", "deleted"):
            raise RuntimeError(f"{nombre_modelo} falló ({estado}): {data}")
        time.sleep(interval_seconds)
    raise TimeoutError(f"Se agotó el tiempo esperando el resultado de {nombre_modelo}.")
