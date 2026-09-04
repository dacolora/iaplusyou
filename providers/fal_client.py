"""
Helper genérico para llamar cualquier modelo de fal.ai (todos comparten el mismo
patrón: encolar en https://queue.fal.run/{model_path}, esperar el resultado con
poll, y buscarlo en response_url — lanzar+poll, igual que higgsfield_client.py).
Usado por comparador_modelos.py y por kling_o1_client.py.

Antes esto pegaba directo a https://fal.run/{model_path} (endpoint síncrono, deja
la conexión HTTP abierta hasta que el modelo termina). Para modelos lentos
(confirmado con wan_animate_replace, 1 sep 2026) eso revienta con
"Read timed out" pasados los 10 minutos aunque fal.ai sí termine de procesar del
otro lado — el resultado se pierde porque nadie se quedó esperándolo. La cola
asíncrona no tiene ese problema: cada poll es una llamada corta.

Esquema verificado contra docs.fal.ai/model-endpoints/queue (1 sep 2026):
  POST https://queue.fal.run/{model_path}
    -> {"request_id", "status_url", "response_url", "queue_position"}
  GET {status_url}
    -> {"status": "IN_QUEUE"|"IN_PROGRESS"|"COMPLETED"|"FAILED", ...}
  GET {response_url}  (solo una vez que status == "COMPLETED")
    -> el resultado real del modelo (mismo JSON que devolvía el endpoint síncrono)

Requiere FAL_KEY en el .env (fal.ai > Dashboard > API Keys).
"""
import os
import time

import requests

QUEUE_BASE_URL = "https://queue.fal.run"
ESTADOS_EN_CURSO = ("IN_QUEUE", "IN_PROGRESS")


def api_key():
    key = os.environ.get("FAL_KEY")
    if not key:
        raise RuntimeError("Falta FAL_KEY en tu .env. Consíguela en fal.ai (Dashboard > API Keys).")
    return key


def _headers():
    return {"Authorization": f"Key {api_key()}", "Content-Type": "application/json"}


def _avisar(on_progreso, info):
    """Reportar progreso es un extra: si falla, se ignora — nunca puede tumbar una
    generación que ya está gastando créditos."""
    if not on_progreso:
        return
    try:
        on_progreso(info)
    except Exception:
        pass


def llamar(model_path, payload, timeout=600, poll_interval=3, on_progreso=None):
    """Encola model_path en la cola async de fal.ai, espera hasta timeout segundos
    a que termine (poll cada poll_interval segundos) y devuelve el JSON del
    resultado ya parseado — misma forma que devolvía el endpoint síncrono viejo.

    on_progreso (opcional): se llama con {"fase": "IN_QUEUE"|"IN_PROGRESS"|...,
    "queue_position": int|None} para que la UI pueda decir "en cola (puesto 3)"
    en vez de un porcentaje inventado. fal.ai no entrega ningún porcentaje real.
    Va AL FINAL de la firma para no romper a los llamadores existentes."""
    resp = requests.post(f"{QUEUE_BASE_URL}/{model_path}", json=payload, headers=_headers(), timeout=30)
    if not resp.ok:
        raise RuntimeError(f"fal.ai ({model_path}) respondió {resp.status_code} al encolar: {resp.text[:500]}")
    encolado = resp.json()
    status_url = encolado["status_url"]
    response_url = encolado["response_url"]
    _avisar(on_progreso, {"fase": "IN_QUEUE", "queue_position": encolado.get("queue_position")})

    inicio = time.time()
    while time.time() - inicio < timeout:
        r = requests.get(status_url, headers=_headers(), timeout=30)
        r.raise_for_status()
        # Antes esto era `r.json().get("status")` y tiraba el resto de la
        # respuesta en la misma expresión; se guarda el cuerpo entero para poder
        # leer también queue_position cuando fal.ai lo manda.
        cuerpo = r.json()
        estado = cuerpo.get("status")
        _avisar(on_progreso, {"fase": estado, "queue_position": cuerpo.get("queue_position")})
        if estado == "COMPLETED":
            resultado = requests.get(response_url, headers=_headers(), timeout=30)
            if not resultado.ok:
                raise RuntimeError(f"fal.ai ({model_path}) respondió {resultado.status_code} al buscar el resultado: {resultado.text[:500]}")
            return resultado.json()
        if estado not in ESTADOS_EN_CURSO:
            raise RuntimeError(f"fal.ai ({model_path}) falló ({estado}): {r.text[:500]}")
        time.sleep(poll_interval)

    raise TimeoutError(f"fal.ai ({model_path}) no terminó en {timeout}s (request_id={encolado.get('request_id')}).")
