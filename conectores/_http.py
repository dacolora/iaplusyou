"""
HTTP común de los conectores con API (Shopify, Woo, MELI).

`pedir(sesion, metodo, url, nombre=..., **kw)` hace UNA petición con timeout
de 30 s y estas reglas, iguales para las tres tiendas:
  - timeout o 5xx: se reintenta una sola vez;
  - 429: se reintenta una sola vez tras esperar `Retry-After` (tope 5 s);
  - error de conexión: `ErrorConector` en español, sin la URL completa.
Devuelve la respuesta tal cual (cualquier código): interpretar 4xx es cosa
de cada conector, que sabe qué significa en su API. Nunca se registran
cabeceras ni cuerpos: lo único que llega al usuario es el código HTTP.
"""
import time

import requests

from .base import ErrorConector

TIMEOUT = 30
MAX_ESPERA_429 = 5


def sesion():
    return requests.Session()


def _espera_429(respuesta):
    bruto = (respuesta.headers or {}).get("Retry-After")
    try:
        segundos = float(bruto)
    except (TypeError, ValueError):
        segundos = 1.0
    return max(0.0, min(segundos, MAX_ESPERA_429))


def pedir(sesion, metodo, url, nombre="la tienda", **kw):
    kw.setdefault("timeout", TIMEOUT)
    reintento_5xx = reintento_429 = reintento_timeout = False
    while True:
        try:
            r = sesion.request(metodo, url, **kw)
        except requests.exceptions.Timeout:
            if reintento_timeout:
                raise ErrorConector(f"{nombre} no respondió a tiempo (más de {TIMEOUT} s). Intenta de nuevo.")
            reintento_timeout = True
            continue
        except requests.exceptions.ConnectionError:
            raise ErrorConector(f"No se pudo conectar con {nombre}. Revisa la URL/dominio o la red.")
        except requests.exceptions.RequestException:
            raise ErrorConector(f"Error de red al hablar con {nombre}.")
        if r.status_code >= 500 and not reintento_5xx:
            reintento_5xx = True
            continue
        if r.status_code == 429 and not reintento_429:
            reintento_429 = True
            time.sleep(_espera_429(r))
            continue
        return r


def error_generico(respuesta, nombre="la tienda"):
    """ErrorConector para un código que el conector no interpreta a mano."""
    codigo = respuesta.status_code
    if codigo == 429:
        return ErrorConector(f"{nombre} limitó las peticiones (HTTP 429). Intenta en unos minutos.")
    if codigo >= 500:
        return ErrorConector(f"{nombre} tiene problemas en este momento (HTTP {codigo}). Intenta más tarde.")
    return ErrorConector(f"{nombre} respondió HTTP {codigo}.")


def json_de(respuesta, nombre="la tienda"):
    try:
        return respuesta.json()
    except ValueError:
        raise ErrorConector(f"{nombre} respondió algo que no es JSON (HTTP {respuesta.status_code}).")
