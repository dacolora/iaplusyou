"""
Helpers compartidos por los clientes de WaveSpeed AI — autenticación y el poll
genérico contra /predictions/{id}/result, que usan por igual
providers/wavespeed_client.py (Wan 2.7 Video Edit) y providers/wan3_client.py
(Wan 3.0).
"""
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import requests
from flask_babel import gettext
from urllib3.exceptions import NewConnectionError

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

    proveedor = "wavespeed"

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


class SinConexion(RuntimeError):
    """No se pudo ni conectar con WaveSpeed al lanzar (tiempo agotado al
    conectar, nombre que no resuelve, conexión rechazada): el pedido no salió,
    así que no se creó ni se cobró nada (PND-214). Antes salía crudo en la
    tarjeta («HTTPSConnectionPool…»)."""

    proveedor = "wavespeed"

    def __init__(self, path, causa):
        self.path, self.causa = path, causa
        super().__init__(f"WaveSpeed ({path}): no se pudo conectar para lanzar ({causa}); el pedido no salió")


class LanzamientoIncierto(RuntimeError):
    """El pedido salió pero su respuesta no llegó (lectura agotada, conexión
    cortada a mitad, respuesta sin id): WaveSpeed pudo crear la predicción y
    cobrarla sin que sepamos su id (PND-214, decisión 2026-10-13). `desde` y
    `hasta` (UTC) son la ventana en que se lanzó: `buscar_lanzada` la busca ahí
    en el historial de la cuenta para recuperarla sin pagar de nuevo. Quien la
    atrape nunca vuelve a lanzar el mismo pedido."""

    proveedor = "wavespeed"

    def __init__(self, path, causa, desde, hasta):
        self.path, self.causa, self.desde, self.hasta = path, causa, desde, hasta
        super().__init__(f"WaveSpeed ({path}) no respondió al lanzar ({causa}): el pedido pudo crearse")


def _ahora_utc():
    return datetime.now(timezone.utc)


# Respuestas de la pasarela (no de WaveSpeed): el pedido pudo llegar y crearse
# aunque la respuesta no (revisión del guardián de gasto, PND-214).
PASARELA_SIN_RESPUESTA = (502, 504, 520, 521, 522, 523, 524)

# Errores de `requests` que pasan ANTES de mandar el pedido: nada salió.
_ANTES_DE_MANDAR = (requests.ConnectTimeout, requests.exceptions.InvalidURL, requests.exceptions.MissingSchema,
                    requests.exceptions.InvalidSchema, requests.exceptions.InvalidHeader)


def _no_salio(e):
    """True solo si se sabe que el pedido no llegó a mandarse: no se pudo
    conectar (tiempo agotado conectando, DNS, conexión rechazada) o el pedido
    estaba mal armado. Todo lo demás (lectura agotada, conexión cortada, TLS a
    mitad) puede haber llegado: incierto."""
    if isinstance(e, _ANTES_DE_MANDAR):
        return True
    if isinstance(e, requests.ConnectionError) and not isinstance(e, requests.exceptions.SSLError):
        razon = getattr(e.args[0], "reason", None) if e.args else None
        return isinstance(razon, NewConnectionError)
    return False


def lanzar_prediccion(path, payload, timeout=60):
    """Lanza una predicción en WaveSpeed y devuelve su id. Lo comparten
    `flowplus_modelos._lanzar` y `wan3_client.generar_video`. Una respuesta
    no-ok es `SinSaldo` o `PedidoRechazado` (`error_de_respuesta`); si no se
    pudo ni conectar, `SinConexion`; si el pedido salió y la respuesta no llegó,
    llegó sin id o la dio la pasarela (502, 504, 52x), `LanzamientoIncierto`
    con la ventana del lanzamiento (PND-214): pudo cobrarse, nunca se vuelve a
    mandar."""
    desde = _ahora_utc()
    try:
        resp = requests.post(f"{BASE_URL}/{path}", json=payload, headers=headers(), timeout=timeout)
    except requests.RequestException as e:
        if _no_salio(e):
            raise SinConexion(path, type(e).__name__) from e
        raise LanzamientoIncierto(path, type(e).__name__, desde, _ahora_utc()) from e
    if not resp.ok:
        if resp.status_code in PASARELA_SIN_RESPUESTA:
            raise LanzamientoIncierto(path, f"HTTP {resp.status_code}", desde, _ahora_utc())
        raise error_de_respuesta(resp, path)
    try:
        prediction_id = ((resp.json() or {}).get("data") or {}).get("id")
    except (ValueError, AttributeError):
        prediction_id = None
    if not prediction_id:
        # WaveSpeed aceptó (2xx) pero no dijo qué creó: pudo crearse y cobrarse.
        raise LanzamientoIncierto(path, "sin_id", desde, _ahora_utc())
    return prediction_id


# Búsqueda de un lanzamiento incierto en el historial (PND-214). El historial
# (POST /predictions, documentado en wavespeed.ai/docs/predictions-api el
# 2026-10-15) trae id, model, status y created_at (RFC 3339, UTC), sin el
# prompt: la predicción se reconoce por la ruta del modelo y la hora.
HOLGURA_VENTANA_S = 20          # relojes de WaveSpeed y del VPS
# Una predicción puede crearse un rato DESPUÉS de que la lectura se agotó (WaveSpeed
# lento justo entonces): la ventana sigue abierta este tiempo tras `hasta`, y la
# búsqueda espera a que pase (revisión del guardián de gasto, PND-214).
TARDANZA_MAX_S = 300
# Forma de un id de predicción (hex o uuid): otro texto no se toma ni se descarta.
ID_PREDICCION = re.compile(r"^[A-Za-z0-9-]{6,80}$")
POR_PAGINA = 100                # el máximo que admite
MAX_PAGINAS = 3
# Estados terminales sin video: nada que recuperar (un intento fallido normalmente no se cobra).
ESTADOS_SIN_VIDEO = ("failed", "cancelled", "timeout", "deleted")


class HistorialNoDisponible(RuntimeError):
    """El historial de WaveSpeed no se pudo leer entero (respuesta no-ok o más
    predicciones en la ventana de las que se pueden mirar): sin él no se
    concluye nada sobre un lanzamiento incierto. Texto técnico (bitácora)."""

    def __init__(self, status=None, demasiadas=None):
        self.status, self.demasiadas = status, demasiadas
        motivo = (f"más de {demasiadas} predicciones en la ventana" if demasiadas
                  else f"respondió {status}")
        super().__init__(f"WaveSpeed (historial de predicciones): {motivo}")


def _iso_utc(momento):
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _leer_fecha(texto):
    """created_at de WaveSpeed («2025-05-19T06:09:15.948268264Z») como datetime
    UTC; None si no se entiende. Python 3.9 no lee la «Z» ni los nanosegundos."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$", str(texto or "").strip())
    if not m:
        return None
    base, fraccion, zona = m.groups()
    try:
        fecha = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    if fraccion:
        fecha = fecha.replace(microsecond=int(fraccion[:6].ljust(6, "0")))
    if zona and zona != "Z":
        signo = 1 if zona[0] == "+" else -1
        horas, minutos = int(zona[1:3]), int(zona[-2:])
        fecha = fecha - signo * timedelta(hours=horas, minutes=minutos)
    return fecha.replace(tzinfo=timezone.utc)


def predicciones_en_ventana(desde, hasta, holgura_s=HOLGURA_VENTANA_S):
    """(predicciones, fiable): las de la cuenta creadas entre `desde − holgura`
    y `hasta + TARDANZA_MAX_S + holgura` (historial de WaveSpeed), y si el
    historial se puede creer entero: False si devolvió alguna fuera de la
    ventana (no aplicó el filtro) o con una fecha que no se entiende. Lanza
    `HistorialNoDisponible` si no se pudo leer entero o no tiene la forma
    documentada: quien busca no concluye nada sin el historial completo."""
    inicio = desde - timedelta(seconds=holgura_s)
    fin = hasta + timedelta(seconds=TARDANZA_MAX_S + holgura_s)
    items = []
    for pagina in range(1, MAX_PAGINAS + 1):
        resp = requests.post(f"{BASE_URL}/predictions", headers=headers(), timeout=30, json={
            "page": pagina, "page_size": POR_PAGINA, "created_after": _iso_utc(inicio), "created_before": _iso_utc(fin)})
        if not resp.ok:
            raise HistorialNoDisponible(status=resp.status_code)
        try:
            lote = ((resp.json() or {}).get("data") or {}).get("items")
        except (ValueError, AttributeError):
            lote = None
        if not isinstance(lote, list):
            raise HistorialNoDisponible(status=resp.status_code)
        items.extend(i for i in lote if isinstance(i, dict))
        if len(lote) < POR_PAGINA:
            break
    else:
        raise HistorialNoDisponible(demasiadas=MAX_PAGINAS * POR_PAGINA)
    fechas = [_leer_fecha(i.get("created_at")) for i in items]
    fiable = all(f is not None and inicio <= f <= fin for f in fechas)
    return [i for i, f in zip(items, fechas) if f is None or inicio <= f <= fin], fiable


def _es_de_la_ruta(modelo, path):
    """El `model` del historial es esta ruta (o la lleva entera con un prefijo).
    Un nombre más corto que la ruta («reference-to-video» sirve a Wan y a Kling)
    no cuenta como de esta ruta."""
    m, p = str(modelo or "").strip().strip("/").lower(), path.strip("/").lower()
    return bool(m) and (m == p or m.endswith("/" + p))


def buscar_lanzada(path, desde, hasta, en_uso=lambda pid: False):
    """¿Qué fue del pedido lanzado en `path` entre `desde` y `hasta` (UTC)?
    `en_uso(id)` dice si una predicción ya es de otra pieza. Devuelve
    {"resultado", "prediccion", "ids"}:
      - "encontrada": una sola predicción de esa ruta en la ventana, viva o
        terminada con video, de nadie más (`prediccion` = el ítem del historial);
      - "ninguna": ninguna que pueda ser la nuestra: no se creó (o falló, y un
        intento fallido normalmente no se cobra);
      - "dudosa": más de una, o algo que no se entiende (un `model` que no es
        una ruta completa, un id raro, un historial que no filtró): no se puede
        saber sin arriesgarse a traer la de otra pieza.
    Lanza `HistorialNoDisponible` (RuntimeError) si el historial no responde."""
    items, fiable = predicciones_en_ventana(desde, hasta)
    candidatas, raras = [], []
    for item in items:
        pid = str(item.get("id") or "")
        modelo = str(item.get("model") or "")
        if not ID_PREDICCION.match(pid):
            raras.append(item)
        elif en_uso(pid):
            continue
        elif _es_de_la_ruta(modelo, path):
            if str(item.get("status") or "").lower() not in ESTADOS_SIN_VIDEO:
                candidatas.append(item)
        elif path.strip("/").lower().endswith(modelo.strip().strip("/").lower()) or "/" not in modelo:
            raras.append(item)
    ids = [str(i.get("id")) for i in candidatas + raras]
    if fiable and len(candidatas) == 1 and not raras:
        return {"resultado": "encontrada", "prediccion": candidatas[0], "ids": ids}
    if fiable and not candidatas and not raras:
        return {"resultado": "ninguna", "prediccion": None, "ids": []}
    return {"resultado": "dudosa", "prediccion": None, "ids": ids}


class ErrorProveedor(RuntimeError):
    """WaveSpeed dio por terminada la predicción sin resultado (failed,
    cancelled, timeout, deleted). Lleva lo que la persona necesita leer — el
    mensaje del proveedor, su código y el id de la predicción — en vez del
    dict crudo (incidente 2026-09-28: la tarjeta mostraba el JSON entero de
    Kling con «Content flagged as potentially sensitive» perdido adentro).
    `proveedor` dice quién la dio («fal» en providers/fal_video.py)."""

    proveedor = "wavespeed"

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

    proveedor = "wavespeed"

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


def plazo_cortable():
    """El `plazo_s` del `cortable()` en curso en este hilo, o None. Lo leen
    las esperas de WaveSpeed y de fal (providers/fal_video.py)."""
    return getattr(_LOCAL, "plazo", None) if en_cortable() else None


def hay_que_cortar():
    """True si el worker se está deteniendo y la espera de este hilo está
    dentro de `cortable()`."""
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
    plazo = plazo_cortable()
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
        if hay_que_cortar():
            raise EsperaInterrumpida(nombre_modelo, prediction_id, time.time() - inicio)
        time.sleep(interval_seconds)
    raise EsperaAgotada(nombre_modelo, prediction_id, limite)
