"""Lectura de la Graph API con el token y la cuenta como argumentos (spec §2.6).

No usa `meta_ads.auth` (estado global con candado del lanzador): copiar siete
cuentas en un hilo del worker no debe bloquear un lanzamiento. Leer no cobra.
Ningún error lleva el token: los de red se resumen con el nombre de la
excepción (su texto puede traer la URL con `access_token`), y los de Meta pasan
por `cola.sin_token` (y por quitar el token literal, que Meta a veces cita suelto).
Las URL `paging.next` traen el token: nunca se registran ni se siguen.

Freno de uso (ruling R22 de la revisión final, 2026-10-08): cada respuesta trae en sus cabeceras cuánto lleva
gastado el usuario + la app (`x-app-usage`), cada negocio por caso de uso (`x-business-use-case-usage`) y la
cuenta (`x-ad-account-usage`). El mismo usuario y la misma app de Meta lanzan los experimentos de colorado_forja:
si cualquiera pasa del 75 % la lectura se detiene con un `ErrorGraph` de límite (`limite=True`, `espera_min` con lo
que Meta dice que falta, o 30 min), antes de que Meta empiece a rechazar también los lanzamientos."""
import json
import time

import requests
from flask_babel import gettext

import cola
import meta_conexion
import meta_errores

TIPOS_COMPRA = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")


class ErrorGraph(Exception):
    """`limite`: Meta pidió esperar (códigos 4/17/32/613/8000x) o el uso pasó del 75 % (`UMBRAL_USO`); `espera_min`:
    los minutos que Meta dice que faltan para recuperar el acceso (None si no lo dijo)."""

    def __init__(self, mensaje, codigo=None, limite=None, espera_min=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.limite = meta_errores.es_codigo_limite(codigo) if limite is None else bool(limite)
        self.espera_min = espera_min
        self.token_roto = codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102


def _url(edge):
    """La URL de un edge RELATIVO de la Graph API. Nunca una URL completa: el token va en los parámetros y solo debe
    viajar a graph.facebook.com (una URL que vino de una respuesta, como `paging.next`, ya lo trae adentro).
    Un edge vacío es la raíz de Graph (`?ids=a,b`): la URL base tal cual, sin una barra de más al final."""
    ruta = str(edge or "").lstrip("/")
    return f"{meta_conexion.GRAPH_URL}/{ruta}" if ruta else meta_conexion.GRAPH_URL


# --------------------------------------------------------- freno de uso ---

UMBRAL_USO = 75           # % de cualquier contador de uso a partir del cual se deja de leer
ESPERA_DEFECTO_MIN = 30   # si Meta no dice cuánto falta
_CAMPOS_PCT = ("call_count", "total_cputime", "total_time", "acc_id_util_pct")


def _numero(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None


def _cabecera_json(cabeceras, nombre):
    try:
        crudo = cabeceras.get(nombre) if cabeceras is not None else None
    except Exception:  # noqa: BLE001 — una respuesta de prueba o rara sin cabeceras normales
        return None
    if not crudo:
        return None
    try:
        return json.loads(crudo)
    except (TypeError, ValueError):
        return None


def uso(cabeceras):
    """(porcentaje máximo de uso, minutos de espera que pide Meta o None) de las cabeceras de una respuesta. Una
    cabecera que no se entiende se ignora (nunca frena por eso)."""
    maximo, espera = 0.0, None
    registros = []
    app = _cabecera_json(cabeceras, "x-app-usage")
    if isinstance(app, dict):
        registros.append(app)
    cuenta = _cabecera_json(cabeceras, "x-ad-account-usage")
    if isinstance(cuenta, dict):
        registros.append(cuenta)
    negocio = _cabecera_json(cabeceras, "x-business-use-case-usage")
    if isinstance(negocio, dict):
        for lista in negocio.values():
            registros.extend(r for r in (lista if isinstance(lista, list) else [lista]) if isinstance(r, dict))
    for r in registros:
        for campo in _CAMPOS_PCT:
            n = _numero(r.get(campo))
            if n is not None:
                maximo = max(maximo, n)
        minutos = _numero(r.get("estimated_time_to_regain_access"))
        if minutos is not None and minutos > 0:
            espera = max(espera or 0, minutos)
    return maximo, espera


def _respuesta(resp, token=None):
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    pct, espera = uso(getattr(resp, "headers", None))
    if not resp.ok or (isinstance(datos, dict) and "error" in datos):
        err = (datos.get("error") if isinstance(datos, dict) else None) or {}
        if not isinstance(err, dict):
            err = {}
        try:   # Meta lo manda como número; a veces como texto («190»); cualquier otra cosa no es un código
            codigo = int(err.get("code")) if err.get("code") is not None else None
        except (TypeError, ValueError):
            codigo = None
        if meta_errores.es_codigo_limite(codigo):
            texto = gettext("Meta pidió esperar (límite de uso de la API). La próxima copia lo reintenta sola.")
        elif codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102:
            texto = gettext("Meta rechazó el acceso: reconecta Meta en Configuración › Conexiones.")
        else:
            texto = gettext("Meta respondió: %(mensaje)s", mensaje=err.get("message") or f"HTTP {resp.status_code}")
        texto = cola.sin_token(texto)
        if token:
            texto = texto.replace(token, "***")
        raise ErrorGraph(cola.recortar(texto, 500), codigo=codigo, espera_min=espera)
    if pct >= UMBRAL_USO:
        # La respuesta llegó bien, pero seguir leyendo acercaría al límite a los lanzamientos del mismo usuario y app.
        raise ErrorGraph(gettext("Meta está cerca de su límite de uso; la copia sigue más tarde."), limite=True,
                         espera_min=espera or ESPERA_DEFECTO_MIN)
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
MAX_PAGINAS_INFORME = 2000   # holgado aun con el límite reducido a 62 o 25: un informe nunca debería llegar aquí


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
    (así un listado enorme no vive entero en memoria).

    Si llega a `max_paginas` y Meta todavía tiene más páginas, sube ErrorGraph: devolver lo leído como si fuera
    todo dejaría a quien llama borrando y reescribiendo con datos incompletos."""
    p = dict(params or {})
    filas, total, paginas, reducciones = [], 0, 0, 0
    while True:
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
        if paginas >= max_paginas:
            raise ErrorGraph(gettext("Meta devolvió más páginas de las esperadas; la copia se reintenta más tarde."))
        p["after"] = despues
    return total if por_pagina is not None else filas


def informe(ad_account_id, token, params, espera_max_s=600, intervalo_s=5, dormir=time.sleep, por_pagina=None,
            intervalo_max_s=30):
    """Insights asíncronos (para level=ad con muchos días): crea el informe, espera
    a «Job Completed» y devuelve sus filas. ErrorGraph si falla o tarda más de `espera_max_s`.
    Con `por_pagina` (ver `paginar`) las filas se entregan página a página y se devuelve cuántas fueron.

    Sondea con una espera que crece (5, 10, 15, 20, 25, 30, 30… s): cada sondeo cuenta contra el límite de uso de
    la cuenta, y con siete cuentas cada 3 horas un sondeo fijo cada 5 s lo agotaba. La suma de las esperas nunca
    pasa de `espera_max_s` (la última se acorta)."""
    run = str(post(f"{ad_account_id}/insights", token, params).get("report_run_id") or "")
    if not run.isdigit():
        # Es un id numérico; cualquier otra cosa no se usa como edge (el token iría a esa ruta).
        raise ErrorGraph(gettext("Meta no creó el informe de métricas."))
    esperado, sondeos = 0.0, 0
    while True:
        estado = get(run, token, {"fields": "async_status,async_percent_completion"})
        st = estado.get("async_status")
        if st == "Job Completed":
            break
        if st in ("Job Failed", "Job Skipped"):
            raise ErrorGraph(gettext("Meta no pudo armar el informe de métricas (%(estado)s).", estado=st))
        if esperado >= espera_max_s:
            raise ErrorGraph(gettext("El informe de Meta tardó demasiado; la próxima copia lo reintenta."))
        sondeos += 1
        paso = min(intervalo_s * sondeos, intervalo_max_s, espera_max_s - esperado)
        dormir(paso)
        esperado += paso
    return paginar(f"{run}/insights", token, {"limit": 500}, max_paginas=MAX_PAGINAS_INFORME,
                   por_pagina=por_pagina)


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
