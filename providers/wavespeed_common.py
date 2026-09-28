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


class ErrorProveedor(RuntimeError):
    """WaveSpeed dio por terminada la predicción sin resultado (failed,
    cancelled, timeout, deleted). Lleva lo que la persona necesita leer — el
    mensaje del proveedor, su código y el id de la predicción — en vez del
    dict crudo (incidente 2026-09-28: la tarjeta mostraba el JSON entero de
    Kling con «Content flagged as potentially sensitive» perdido adentro)."""

    def __init__(self, nombre_modelo, estado, detalle=None, codigo=None, prediction_id=None, datos=None):
        self.nombre_modelo, self.estado, self.detalle = nombre_modelo, estado, detalle
        self.codigo, self.prediction_id, self.datos = codigo, prediction_id, datos
        partes = [f"{nombre_modelo} no pudo generar: {detalle or estado}"]
        if codigo is not None:
            partes.append(f"(código {codigo})")
        if prediction_id:
            partes.append(f"· predicción {prediction_id}")
        super().__init__(" ".join(partes))


class EsperaAgotada(TimeoutError):
    """El worker dejó de esperar, pero WaveSpeed sigue trabajando: la
    predicción (`prediction_id`) suele terminar y cobrarse igual. Quien la
    atrape guarda el id para recuperar el resultado después sin pagar de
    nuevo (tareas/flowplus.recuperar_video)."""

    def __init__(self, nombre_modelo, prediction_id, timeout_seconds):
        self.nombre_modelo, self.prediction_id, self.timeout_seconds = nombre_modelo, prediction_id, timeout_seconds
        super().__init__(f"Se agotó el tiempo esperando el resultado de {nombre_modelo} "
                         f"({int(timeout_seconds // 60)} min; predicción {prediction_id}).")


def avisar_lanzada(on_progreso, prediction_id):
    """Primera señal de progreso, apenas WaveSpeed devuelve el id de la
    predicción: así la sesión lo guarda aunque el primer GET del poll falle.
    Un fallo reportando jamás tumba una generación que ya está gastando."""
    if not on_progreso:
        return
    try:
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": prediction_id})
    except Exception:
        pass


def poll_hasta_listo(prediction_id, nombre_modelo, interval_seconds=5, timeout_seconds=900,
                     on_progreso=None):
    """on_progreso (opcional): se llama en cada vuelta con {"fase": <status crudo>,
    "elapsed": <segundos>, "prediction_id": <id>} para que la UI pueda decir en
    qué va el proveedor (y la sesión guarde el id). WaveSpeed no entrega ningún
    porcentaje numérico — solo estados textuales (created/processing/completed/
    failed), así que eso es lo único honesto que se puede mostrar. El parámetro
    va AL FINAL para no romper a los llamadores que pasan interval/timeout de
    forma posicional. Un estado terminal sin resultado lanza ErrorProveedor
    (RuntimeError, legible); el tiempo agotado, EsperaAgotada (TimeoutError,
    con el id para recuperar el resultado después)."""
    url = f"{BASE_URL}/predictions/{prediction_id}/result"
    inicio = time.time()
    while time.time() - inicio < timeout_seconds:
        resp = requests.get(url, headers=headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        estado = data.get("status")
        if on_progreso:
            # Un fallo reportando progreso jamás debe tumbar una generación que
            # ya está gastando créditos.
            try:
                on_progreso({"fase": estado, "elapsed": time.time() - inicio, "prediction_id": prediction_id})
            except Exception:
                pass
        if estado == "completed":
            return data
        if estado in ("failed", "cancelled", "timeout", "deleted"):
            raise ErrorProveedor(nombre_modelo, estado, detalle=data.get("error") or None, codigo=data.get("code"),
                                 prediction_id=prediction_id, datos=data)
        time.sleep(interval_seconds)
    raise EsperaAgotada(nombre_modelo, prediction_id, timeout_seconds)
