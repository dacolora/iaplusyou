"""
Video de Crear por la cola de fal.ai (Seedance 2.5 con varias referencias,
2026-10-09: WaveSpeed solo tiene su imagen-a-video, que usa una imagen).

Mismas garantías que WaveSpeed en `tareas/flowplus.py`, con las mismas
excepciones de `wavespeed_common` (marcadas `proveedor = "fal"`):
  - el id del pedido sale por `on_progreso` apenas fal lo entrega
    (`avisar_lanzada`), así la sesión lo guarda y «Recuperar el video»
    vuelve a preguntar por él sin pagar de nuevo;
  - dentro de `wavespeed_common.cortable()` la espera se acorta al plazo
    pedido (`EsperaAgotada`) o se corta en un reinicio (`EsperaInterrumpida`);
  - sin saldo es `SinSaldo` y un pedido que fal no acepta es
    `PedidoRechazado`, con lo que dijo fal en palabras; un pedido que terminó
    sin video es `ErrorProveedor`.
`providers/fal_client.py` (audio) no hace nada de eso y se deja como está.

Contrato verificado el 2026-10-09 con un pedido real (PND-211):
  POST {COLA}/{ruta}                          -> {"request_id", "status_url", "response_url", ...}
  GET  {COLA}/{app}/requests/{id}/status      -> 202 {"status": IN_QUEUE|IN_PROGRESS, "queue_position"?} / 200 COMPLETED
  GET  {COLA}/{app}/requests/{id}             -> {"video": {"url"}, "seed"} (o el error, si falló;
                                                 400 «still in progress» si se pide antes de tiempo)
donde `app` son los dos primeros tramos de la ruta (`bytedance/seedance-2.5`): con la ruta completa, como la
escribe el OpenAPI de fal, el estado responde 405 (la prueba real lo destapó; el pedido ya estaba pagado y se
recuperó por la raíz). Los errores de fal traen `detail` (texto o lista de {"msg"}).
"""
import time

import requests
from flask_babel import gettext

from providers import fal_client, wavespeed_common

COLA = fal_client.QUEUE_BASE_URL
EN_CURSO = ("IN_QUEUE", "IN_PROGRESS")


class SinSaldo(wavespeed_common.SinSaldo):
    """La cuenta de fal de Creatv no tiene saldo (fal responde 403 «User is
    locked. Reason: Exhausted balance. Top up your balance…»)."""

    proveedor = "fal"

    def __init__(self, ruta, status, detalle):
        self.path, self.status, self.detalle = ruta, status, detalle
        RuntimeError.__init__(self, f"fal.ai ({ruta}) respondió {status}: sin saldo en la cuenta ({detalle})")


class PedidoRechazado(wavespeed_common.PedidoRechazado):
    """fal no aceptó el pedido al lanzarlo (422 de validación, llave, 429, 5xx)."""

    proveedor = "fal"

    def __init__(self, ruta, status, mensaje, texto):
        self.path, self.status, self.mensaje = ruta, status, mensaje
        RuntimeError.__init__(self, f"fal.ai ({ruta}) respondió {status}: {texto[:500]}")


def _mensaje(resp):
    """Lo que dijo fal en palabras: `detail` como texto, o los `msg` de una
    lista de validación unidos; vacío si no hay nada legible."""
    try:
        cuerpo = resp.json()
    except ValueError:
        return ""
    if not isinstance(cuerpo, dict):
        return ""
    detalle = cuerpo.get("detail") or cuerpo.get("error") or cuerpo.get("message") or ""
    if isinstance(detalle, list):
        detalle = "; ".join(str(d.get("msg") or d) if isinstance(d, dict) else str(d) for d in detalle)
    return str(detalle)


def error_de_respuesta(resp, ruta):
    """`SinSaldo` si fal dice que la cuenta no tiene saldo; `PedidoRechazado`
    en cualquier otro caso."""
    texto = resp.text or ""
    mensaje = _mensaje(resp)
    minusculas = (mensaje or texto).lower()
    if (resp.status_code == 402 or "exhausted balance" in minusculas or "top up" in minusculas
            or ("insufficient" in minusculas and ("credit" in minusculas or "balance" in minusculas))):
        return SinSaldo(ruta, resp.status_code, (mensaje or texto)[:300])
    return PedidoRechazado(ruta, resp.status_code, mensaje[:300], texto)


def _espera_agotada(nombre, request_id, segundos, interrumpida=False):
    clase = wavespeed_common.EsperaInterrumpida if interrumpida else wavespeed_common.EsperaAgotada
    e = clase(nombre, request_id, segundos)
    e.proveedor = "fal"
    return e


def _error_proveedor(nombre, estado, detalle, request_id, codigo=None, datos=None):
    e = wavespeed_common.ErrorProveedor(nombre, estado, detalle=detalle or None, codigo=codigo,
                                        prediction_id=request_id, datos=datos)
    e.proveedor = "fal"
    return e


def _base(ruta, request_id):
    """URL del pedido en la cola: la app (dos primeros tramos de la ruta), no la
    ruta completa — así la arma fal en `status_url`/`response_url` y así la piden
    sus clientes oficiales."""
    app = "/".join(ruta.split("/")[:2])
    return f"{COLA}/{app}/requests/{request_id}"


def lanzar(ruta, payload, nombre, on_progreso=None, timeout_seconds=1200):
    """Encola `payload` en `ruta`, avisa el id y espera el video. Devuelve la
    URL pública del video."""
    try:
        resp = requests.post(f"{COLA}/{ruta}", json=payload, headers=fal_client._headers(), timeout=60)
    except (requests.Timeout, requests.ConnectionError) as e:
        # Sin respuesta: fal pudo haber encolado (y cobrar) sin que sepamos el id.
        # Se cuenta como una falla de su lado (5xx), que NO promete que no se cobró.
        raise PedidoRechazado(ruta, 504, "", f"sin respuesta al encolar ({type(e).__name__}): {e}") from e
    if not resp.ok:
        raise error_de_respuesta(resp, ruta)
    request_id = (resp.json() or {}).get("request_id")
    if not request_id:
        raise RuntimeError(f"fal.ai ({ruta}) no devolvió un id de pedido: {resp.text[:500]}")
    wavespeed_common.avisar_lanzada(on_progreso, request_id)
    return esperar(ruta, request_id, nombre, timeout_seconds=timeout_seconds, on_progreso=on_progreso)


def esperar(ruta, request_id, nombre, interval_seconds=5, timeout_seconds=900, on_progreso=None):
    """Pregunta por el pedido `request_id` hasta que termine y devuelve la URL
    del video. Lo usan la generación y «Recuperar el video» (que nunca vuelve
    a lanzar). Igual que `wavespeed_common.poll_hasta_listo`: varios cortes de
    red seguidos o un 4xx tumban la espera; un 5xx suelto, no."""
    base = _base(ruta, request_id)
    inicio = time.time()
    plazo = wavespeed_common.plazo_cortable()
    limite = timeout_seconds if plazo is None else min(timeout_seconds, plazo)
    fallos = 0
    while time.time() - inicio < limite:
        try:
            r = requests.get(f"{base}/status", headers=fal_client._headers(), timeout=30)
            r.raise_for_status()
            cuerpo = r.json() or {}
        except requests.RequestException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            fallos += 1
            if (codigo is not None and codigo < 500 and codigo != 429) or fallos >= wavespeed_common.FALLOS_SEGUIDOS:
                raise
            time.sleep(interval_seconds)
            continue
        fallos = 0
        estado = cuerpo.get("status")
        if on_progreso:
            try:
                on_progreso({"fase": estado, "elapsed": time.time() - inicio, "prediction_id": request_id,
                             "queue_position": cuerpo.get("queue_position")})
            except Exception:
                pass
        if estado == "COMPLETED":
            return _resultado(base, nombre, request_id)
        if estado not in EN_CURSO:
            raise _error_proveedor(nombre, estado or "desconocido", cuerpo.get("error"), request_id, datos=cuerpo)
        if wavespeed_common.hay_que_cortar():
            raise _espera_agotada(nombre, request_id, time.time() - inicio, interrumpida=True)
        time.sleep(interval_seconds)
    raise _espera_agotada(nombre, request_id, limite)


# Respuestas del resultado que no dicen nada del video: la llave, un id que fal
# no encuentra todavía, demasiados pedidos. Junto con los 5xx y los cortes de red
# salen como `requests.HTTPError` (el id se conserva y se sigue esperando), nunca
# como `ErrorProveedor` (que borra el id y dice «no se cobró»).
_RESULTADO_PASAJERO = (401, 403, 404, 408, 409, 429)


def _resultado(base, nombre, request_id):
    """El pedido terminó: el video, o `ErrorProveedor` con lo que dijo fal
    cuando el pedido falló de verdad (un 4xx con su motivo, p. ej. 422 de
    contenido). Revisión del guardián de gasto (2026-10-09): fal ya cobró un
    video COMPLETED; si lo que falla es TRAERLO (429, 5xx seguidos, la red),
    sale como error de red y la sesión conserva el id para recuperarlo sin pagar
    de nuevo, nunca como «no pudo generar»."""
    fallos = 0
    while True:
        try:
            r = requests.get(base, headers=fal_client._headers(), timeout=30)
        except requests.RequestException:
            fallos += 1
            if fallos >= wavespeed_common.FALLOS_SEGUIDOS:
                raise
            time.sleep(2)
            continue
        pasajero = r.status_code >= 500 or r.status_code in _RESULTADO_PASAJERO
        if pasajero and fallos + 1 < wavespeed_common.FALLOS_SEGUIDOS:
            fallos += 1
            time.sleep(2)
            continue
        break
    if r.status_code >= 500 or r.status_code in _RESULTADO_PASAJERO:
        r.raise_for_status()
    if not r.ok:
        raise _error_proveedor(nombre, "failed", _mensaje(r) or r.text[:300], request_id, codigo=r.status_code)
    datos = r.json() or {}
    url = (datos.get("video") or {}).get("url")
    if not url:
        raise _error_proveedor(nombre, "completed", gettext("terminó sin ningún video"), request_id, datos=datos)
    return url
