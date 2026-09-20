"""
HTTP común de las fuentes conectadas que hablan con `requests` (Reddit y
Apify; YouTube usa la librería de Google). `pedir(sesion, metodo, url,
nombre, **kw)` hace UNA petición con timeout de TIMEOUT s y estas reglas:
  - 429: espera `Retry-After` (mínimo 0.5 s, tope MAX_ESPERA_429) y reintenta
    hasta MAX_429 veces; después lanza `Error429` (la fuente decide si entrega
    lo que lleva);
  - 5xx: un solo reintento tras ESPERA_5XX;
  - timeout o error de conexión: un solo reintento y luego `ErrorFuente` en
    español, sin la URL (que puede llevar parámetros) ni cabeceras (llaves).
Devuelve la respuesta tal cual (cualquier código): interpretar 4xx es cosa de
cada fuente. `dormir` envuelve `time.sleep` para que las pruebas no esperen.
"""
import time

import requests

from nicho.fuentes.base import ErrorFuente

TIMEOUT = 30
MAX_ESPERA_429 = 10.0
MAX_429 = 3
ESPERA_5XX = 1.0


class Error429(ErrorFuente):
    """La fuente limitó las llamadas y no cedió tras MAX_429 esperas."""


def dormir(segundos):
    time.sleep(segundos)


def sesion():
    return requests.Session()


def _espera_429(respuesta):
    bruto = (respuesta.headers or {}).get("Retry-After")
    try:
        segundos = float(bruto)
    except (TypeError, ValueError):
        segundos = 2.0
    return max(0.5, min(segundos, MAX_ESPERA_429))


def pedir(sesion, metodo, url, nombre, **kw):
    kw.setdefault("timeout", TIMEOUT)
    reintento_5xx = reintento_red = False
    veces_429 = 0
    while True:
        try:
            r = sesion.request(metodo, url, **kw)
        except requests.exceptions.RequestException as e:
            if reintento_red:
                raise ErrorFuente(f"{nombre} no respondió ({type(e).__name__}). Intenta de nuevo en un rato.") from None
            reintento_red = True
            dormir(ESPERA_5XX)
            continue
        if r.status_code == 429:
            if veces_429 >= MAX_429:
                raise Error429(f"{nombre} limitó las llamadas (429) y no cedió tras {MAX_429} esperas.")
            veces_429 += 1
            dormir(_espera_429(r))
            continue
        if 500 <= r.status_code < 600 and not reintento_5xx:
            reintento_5xx = True
            dormir(ESPERA_5XX)
            continue
        return r
