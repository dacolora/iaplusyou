"""Lectura de la Graph API con el token y la cuenta como argumentos (spec §2.6).

No usa `meta_ads.auth` (estado global con candado del lanzador): copiar siete
cuentas en un hilo del worker no debe bloquear un lanzamiento. Leer no cobra.
Ningún error lleva el token: los de red se resumen con el nombre de la
excepción (su texto puede traer la URL con `access_token`), y los de Meta pasan
por `cola.sin_token` (y por quitar el token literal, que Meta a veces cita suelto).
Las URL `paging.next` traen el token: nunca se registran ni se siguen."""
import time

import requests
from flask_babel import gettext

import cola
import meta_conexion
import meta_errores

TIPOS_COMPRA = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")


class ErrorGraph(Exception):
    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.limite = meta_errores.es_codigo_limite(codigo)
        self.token_roto = codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102


def _url(edge):
    return edge if edge.startswith("https://") else f"{meta_conexion.GRAPH_URL}/{edge.lstrip('/')}"


def _respuesta(resp, token=None):
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or (isinstance(datos, dict) and "error" in datos):
        err = (datos or {}).get("error") or {}
        codigo = err.get("code")
        if meta_errores.es_codigo_limite(codigo):
            texto = gettext("Meta pidió esperar (límite de uso de la API). La próxima copia lo reintenta sola.")
        elif codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102:
            texto = gettext("Meta rechazó el acceso: reconecta Meta en Configuración › Conexiones.")
        else:
            texto = gettext("Meta respondió: %(mensaje)s", mensaje=err.get("message") or f"HTTP {resp.status_code}")
        texto = cola.sin_token(texto)
        if token:
            texto = texto.replace(token, "***")
        raise ErrorGraph(cola.recortar(texto, 500), codigo=codigo)
    return datos


def _llamar(metodo, edge, token, params, timeout):
    p = dict(params or {})
    p["access_token"] = token
    try:
        if metodo == "POST":
            resp = requests.post(_url(edge), data=p, timeout=timeout)
        else:
            resp = requests.get(_url(edge), params=p, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ErrorGraph(gettext("No pude hablar con Meta (%(error)s).", error=type(e).__name__)) from None
    return _respuesta(resp, token)


def get(edge, token, params=None, timeout=60):
    return _llamar("GET", edge, token, params, timeout)


def post(edge, token, params=None, timeout=60):
    return _llamar("POST", edge, token, params, timeout)


# Meta responde 1 («Please reduce the amount of data…») o 2 (servicio no disponible por el tamaño) cuando una
# página pide demasiado (anuncios con `creative{…}` y 500 por página): se baja el límite a la mitad y se reintenta
# la MISMA página, como máximo 3 veces por llamada y sin bajar de 25.
CODIGOS_MUCHOS_DATOS = (1, 2)
LIMITE_MINIMO = 25
MAX_REDUCCIONES = 3


def _limite(params):
    try:
        return int(params.get("limit"))
    except (TypeError, ValueError):
        return None


def paginar(edge, token, params=None, max_paginas=200, timeout=60, por_pagina=None):
    """Todas las filas de `data`, siguiendo el cursor `after` (no la URL `next`, que trae el token).

    Si una página falla con «demasiados datos» (código 1 o 2) y `limit` pasa de 25, baja el `limit` a la mitad y
    reintenta esa misma página (el nuevo límite sigue para las demás), hasta 3 veces; después sube el error.
    Con `por_pagina` cada página se le entrega a esa función y NO se acumula: devuelve cuántas filas pasaron
    (así un listado enorme no vive entero en memoria)."""
    p = dict(params or {})
    filas, total, paginas, reducciones = [], 0, 0, 0
    while paginas < max_paginas:
        try:
            datos = get(edge, token, p, timeout)
        except ErrorGraph as e:
            limite = _limite(p)
            if (e.codigo not in CODIGOS_MUCHOS_DATOS or not limite or limite <= LIMITE_MINIMO
                    or reducciones >= MAX_REDUCCIONES):
                raise
            p["limit"] = max(LIMITE_MINIMO, limite // 2)
            reducciones += 1
            continue
        paginas += 1
        pagina = datos.get("data") or []
        total += len(pagina)
        if por_pagina is not None:
            por_pagina(pagina)
        else:
            filas.extend(pagina)
        paging = datos.get("paging") or {}
        despues = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not despues:
            break
        p["after"] = despues
    return total if por_pagina is not None else filas


def informe(ad_account_id, token, params, espera_max_s=600, intervalo_s=5, dormir=time.sleep, por_pagina=None):
    """Insights asíncronos (para level=ad con muchos días): crea el informe, espera
    a «Job Completed» y devuelve sus filas. ErrorGraph si falla o tarda más de `espera_max_s`.
    Con `por_pagina` (ver `paginar`) las filas se entregan página a página y se devuelve cuántas fueron."""
    run = post(f"{ad_account_id}/insights", token, params).get("report_run_id")
    if not run:
        raise ErrorGraph(gettext("Meta no creó el informe de métricas."))
    esperado = 0.0
    while True:
        estado = get(str(run), token, {"fields": "async_status,async_percent_completion"})
        st = estado.get("async_status")
        if st == "Job Completed":
            break
        if st in ("Job Failed", "Job Skipped"):
            raise ErrorGraph(gettext("Meta no pudo armar el informe de métricas (%(estado)s).", estado=st))
        if esperado >= espera_max_s:
            raise ErrorGraph(gettext("El informe de Meta tardó demasiado; la próxima copia lo reintenta."))
        dormir(intervalo_s)
        esperado += intervalo_s
    return paginar(f"{run}/insights", token, {"limit": 500}, por_pagina=por_pagina)


def acciones(lista, tipos):
    """Valor del primer tipo de `tipos` presente en una lista `actions`/`action_values` de Meta."""
    por_tipo = {a.get("action_type"): a.get("value") for a in (lista or []) if isinstance(a, dict)}
    for t in tipos:
        if t in por_tipo:
            try:
                return float(por_tipo[t] or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0
