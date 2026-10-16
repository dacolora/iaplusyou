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


class EsperaAgotadaFal(TimeoutError):
    """PND-313 (decisión 2026-10-13, lote 1): dejamos de esperar y fal sigue con el pedido. fal cobra lo que
    termina, así que `cobrado` dice si lo cobra (o lo cobrará): estaba en curso, terminó sin que pudiéramos
    traer el resultado, o no se pudo preguntar (una línea de costo algo inexacta es mejor que perder lo
    pagado). False solo si seguía en cola y fal aceptó cancelarlo. Es un TimeoutError, como antes; quien lo
    atrapa anota lo cobrado (los de `fal_audio` le pegan `costo_usd`)."""

    def __init__(self, model_path, request_id, estado, cobrado):
        self.model_path, self.request_id, self.estado, self.cobrado = model_path, request_id, estado, cobrado
        super().__init__(f"fal.ai ({model_path}) no terminó a tiempo (request_id={request_id}, estado={estado}, "
                         f"{'lo cobra' if cobrado else 'cancelado en cola, sin cobro'}).")


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
        _sin_saldo(resp, model_path)
        raise RuntimeError(f"fal.ai ({model_path}) respondió {resp.status_code} al encolar: {resp.text[:500]}")
    encolado = resp.json()
    status_url = encolado["status_url"]
    response_url = encolado["response_url"]
    _avisar(on_progreso, {"fase": "IN_QUEUE", "queue_position": encolado.get("queue_position")})

    def _resultado():
        resultado = requests.get(response_url, headers=_headers(), timeout=30)
        if not resultado.ok:
            raise RuntimeError(f"fal.ai ({model_path}) respondió {resultado.status_code} al buscar el resultado: {resultado.text[:500]}")
        return resultado.json()

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
            return _resultado()
        if estado not in ESTADOS_EN_CURSO:
            raise RuntimeError(f"fal.ai ({model_path}) falló ({estado}): {r.text[:500]}")
        time.sleep(poll_interval)

    # PND-313: una última pregunta antes de rendirse. Terminado → se entrega; en cola → se intenta cancelar
    # (nunca empezó, no se cobra); en curso o sin respuesta → fal lo cobra y quien llama lo anota.
    try:
        estado = requests.get(status_url, headers=_headers(), timeout=30).json().get("status")
    except Exception:  # noqa: BLE001 — sin poder preguntar se cuenta como cobrado
        estado = None
    if estado == "COMPLETED":
        return _resultado()
    cobrado = not (estado == "IN_QUEUE" and _cancelar(status_url))
    raise EsperaAgotadaFal(model_path, encolado.get("request_id"), estado, cobrado)


def _sin_saldo(resp, model_path):
    """PND-215 (decisión 2026-10-13, lote 2): si fal rechazó el pedido por falta de saldo (403 «Exhausted balance»,
    402…), lo anota como Seedance (`saldo.marcar("fal")`: el aviso de Crear, la alerta de fal y el correo al admin) y
    lanza `fal_video.SinSaldo`, que las tareas de voz y música dicen en palabras. Las voces, la música y los
    subtítulos pasan por aquí; antes fallaban con el texto crudo de fal y nadie se enteraba. Otro rechazo: no hace
    nada (quien llama lanza el RuntimeError de siempre)."""
    from providers import fal_video  # noqa: PLC0415 — fal_video importa este módulo
    error = fal_video.error_de_respuesta(resp, model_path)
    if not isinstance(error, fal_video.SinSaldo):
        return
    import saldo  # noqa: PLC0415 — perezoso: solo en este caso raro (nunca lanza)
    saldo.marcar("fal", error.detalle)
    raise error


def _cancelar(status_url):
    """Pide a fal cancelar un pedido que sigue en cola (`PUT …/requests/<id>/cancel`). True solo si fal lo
    aceptó (202, CANCELLATION_REQUESTED). Nunca lanza."""
    if not status_url.endswith("/status"):
        return False
    try:
        r = requests.put(status_url[: -len("/status")] + "/cancel", headers=_headers(), timeout=30)
        return r.status_code == 202 and (r.json() or {}).get("status") == "CANCELLATION_REQUESTED"
    except Exception:  # noqa: BLE001
        return False
