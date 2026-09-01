"""
Helper genérico para llamar cualquier modelo de fal.ai (todos comparten el mismo
patrón: POST a https://fal.run/{model_path} con Authorization: Key, respuesta
síncrona en JSON — sin lanzar+poll). Usado por comparador_modelos.py y por
kling_o1_client.py.

Requiere FAL_KEY en el .env (fal.ai > Dashboard > API Keys).
"""
import os

import requests

BASE_URL = "https://fal.run"


def api_key():
    key = os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError("Falta FAL_KEY en tu .env. Consíguela en fal.ai (Dashboard > API Keys).")
    return key


def llamar(model_path, payload, timeout=600):
    """POST a fal.run/{model_path}. Devuelve el JSON de respuesta ya parseado."""
    url = f"{BASE_URL}/{model_path}"
    headers = {"Authorization": f"Key {api_key()}", "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"fal.ai ({model_path}) respondió {resp.status_code}: {resp.text[:500]}")
    return resp.json()
