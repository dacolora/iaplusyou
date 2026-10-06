"""
Helpers compartidos por los clientes de WaveSpeed AI — autenticación y el poll
genérico contra /predictions/{id}/result, que usan por igual
providers/wavespeed_client.py (Wan 2.7 Video Edit) y providers/wan3_client.py
(Wan 3.0).
"""
import os
import threading
import time
from contextlib import contextmanager

import requests
from flask_babel import gettext

BASE_URL = "https://api.wavespeed.ai/api/v3"


def api_key():
    key = os.environ.get("WAVESPEED_API_KEY")
    if not key:
        raise RuntimeError(
            gettext("Falta WAVESPEED_API_KEY en tu .env. Consíguela en wavespeed.ai (API Keys).")
        )
    return key


def headers():
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


class SinSaldo(RuntimeError):
    """WaveSpeed rechazó el pedido porque la cuenta de Creatv no tiene saldo
    (incidente 2026-09-30: «Insufficient credits. Please top up your account
    to continue.» salía crudo en la tarjeta). Es un RuntimeError para que todo
    el manejo de errores de siempre lo siga atrapando; quien lo atrape lo
    cuenta en palabras y avisa al administrador (saldo.marcar). Nada se lanzó,
    así que nada se cobró."""

    proveedor = "wavespeed"

    def __init__(self, path, status, detalle):
        self.path, self.status, self.detalle = path, status, detalle
        super().__init__(f"WaveSpeed ({path}) respondió {status}: sin saldo en la cuenta ({detalle})")


class PedidoRechazado(RuntimeError):
    """WaveSpeed rechazó el pedido al lanzarlo (400, 422, 1405…) por algo que no
    es el saldo: un parámetro que el modelo no acepta, una duración, una
    referencia. Nada se lanzó, así que nada se cobró. `str(e)` sigue siendo el
    texto técnico de siempre (bitácora, `tarea.error`); `mensaje` es lo que dijo
    el proveedor, para contarlo en palabras en la tarjeta (PND-107: antes la
    tarjeta mostraba el JSON crudo)."""

    def __init__(self, path, status, mensaje, texto):
        self.path, self.status, self.mensaje = path, status, mensaje
        super().__init__(f"WaveSpeed ({path}) respondió {status}: {texto[:500]}")


def error_de_respuesta(resp, path):
    """La excepción para una respuesta no-ok al lanzar una predicción:
    `SinSaldo` si WaveSpeed dice que la cuenta no tiene saldo (402, o su
    mensaje de «insufficient credits» / «top up»), y `PedidoRechazado` — un
    RuntimeError con el mismo texto de siempre — en cualquier otro caso."""
    texto = resp.text or ""
    mensaje = ""
    try:
        cuerpo = resp.json()
        if isinstance(cuerpo, dict):
            mensaje = str(cuerpo.get("message") or cuerpo.get("error") or "")
    except ValueError:
        pass
    minusculas = (mensaje or texto).lower()
    if (resp.status_code == 402 or ("insufficient" in minusculas and ("credit" in minusculas or "balance" in minusculas))
            or "top up" in minusculas):
        return SinSaldo(path, resp.status_code, (mensaje or texto)[:300])
    return PedidoRechazado(path, resp.status_code, mensaje[:300], texto)


class ErrorProveedor(RuntimeError):
    """WaveSpeed dio por terminada la predicción sin resultado (failed,
    cancelled, timeout, deleted). Lleva lo que la persona necesita leer — el
    mensaje del proveedor, su código y el id de la predicción — en vez del
    dict crudo (incidente 2026-09-28: la tarjeta mostraba el JSON entero de
    Kling con «Content flagged as potentially sensitive» perdido adentro)."""

    def __init__(self, nombre_modelo, estado, detalle=None, codigo=None, prediction_id=None, datos=None):
        self.nombre_modelo, self.estado, self.detalle = nombre_modelo, estado, detalle
        self.codigo, self.prediction_id, self.datos = codigo, prediction_id, datos
        # El texto se guarda (tarjeta de Crear, mensaje de la tarea): gettext en el
        # idioma ambiente, que en el worker es el del proyecto.
        partes = [gettext("%(modelo)s no pudo generar: %(detalle)s", modelo=nombre_modelo, detalle=detalle or estado)]
        if codigo is not None:
            partes.append(gettext("(código %(codigo)s)", codigo=codigo))
        if prediction_id:
            partes.append(gettext("· predicción %(id)s", id=prediction_id))
        super().__init__(" ".join(partes))


class EsperaAgotada(TimeoutError):
    """El worker dejó de esperar, pero WaveSpeed sigue trabajando: la
    predicción (`prediction_id`) suele terminar y cobrarse igual. Quien la
    atrape guarda el id para recuperar el resultado después sin pagar de
    nuevo (tareas/flowplus.recuperar_video)."""

    def __init__(self, nombre_modelo, prediction_id, timeout_seconds):
        self.nombre_modelo, self.prediction_id, self.timeout_seconds = nombre_modelo, prediction_id, timeout_seconds
        super().__init__(gettext("Se agotó el tiempo esperando el resultado de %(modelo)s (%(min)s min; "
                                 "predicción %(id)s).", modelo=nombre_modelo, min=int(timeout_seconds // 60),
                                 id=prediction_id))


class EsperaInterrumpida(EsperaAgotada):
    """El worker se está deteniendo (reinicio, despliegue) y cortó la espera
    antes de tiempo: la predicción sigue en WaveSpeed y se retoma por su id
    (tareas/flowplus: `flowplus_recuperar`). Solo pasa dentro de `cortable()`."""

    def __init__(self, nombre_modelo, prediction_id, esperado_s):
        self.nombre_modelo, self.prediction_id, self.timeout_seconds = nombre_modelo, prediction_id, esperado_s
        TimeoutError.__init__(self, gettext("Se cortó la espera de %(modelo)s porque el worker se está reiniciando "
                                            "(predicción %(id)s); se retoma sola.",
                                            modelo=nombre_modelo, id=prediction_id))


# Parada del worker (`worker.main` la fija con `debe_parar`). Solo corta las
# esperas de quien la pidió con `cortable()`: las tareas que saben retomar una
# predicción por su id. Un swap o una imagen siguen hasta el final como antes.
_DETENER = None
_LOCAL = threading.local()
# Consultas fallidas seguidas (red caída, 5xx) antes de rendirse.
FALLOS_SEGUIDOS = 6


def fijar_detener(fn):
    global _DETENER
    _DETENER = fn


@contextmanager
def cortable(plazo_s=None):
    """Dentro de este bloque (del hilo actual), una parada del worker corta la
    espera con `EsperaInterrumpida` en vez de dejarla hasta el final, y
    `plazo_s` (opcional) acorta la espera: pasado ese tiempo sale
    `EsperaAgotada` y quien la pidió la retoma después por el id (el hilo del
    carril de Crear queda libre para otra pieza)."""
    antes = (getattr(_LOCAL, "cortable", False), getattr(_LOCAL, "plazo", None))
    _LOCAL.cortable, _LOCAL.plazo = True, plazo_s
    try:
        yield
    finally:
        _LOCAL.cortable, _LOCAL.plazo = antes


def en_cortable():
    return bool(getattr(_LOCAL, "cortable", False))


def _hay_que_cortar():
    try:
        return en_cortable() and _DETENER is not None and bool(_DETENER())
    except Exception:  # noqa: BLE001 — preguntar nunca tumba una espera
        return False


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
    plazo = getattr(_LOCAL, "plazo", None) if en_cortable() else None
    limite = timeout_seconds if plazo is None else min(timeout_seconds, plazo)
    fallos = 0
    while time.time() - inicio < limite:
        # Un corte suelto de la red (502, timeout, conexión) no tumba la espera
        # de un video ya pagado; varios seguidos sí (la red está caída de verdad).
        try:
            resp = requests.get(url, headers=headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data") or {}
        except requests.RequestException as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            fallos += 1
            if (codigo is not None and codigo < 500 and codigo != 429) or fallos >= FALLOS_SEGUIDOS:
                raise
            time.sleep(interval_seconds)
            continue
        fallos = 0
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
        # Después de avisar el progreso (el id ya quedó guardado): si el worker
        # se detiene, la espera se corta y otra tarea la retoma por el id.
        if _hay_que_cortar():
            raise EsperaInterrumpida(nombre_modelo, prediction_id, time.time() - inicio)
        time.sleep(interval_seconds)
    raise EsperaAgotada(nombre_modelo, prediction_id, limite)
