"""
Conector de barrido Atria (spec 2026-09-23 §2.2, §4.1): Ad Library de Meta
vía la API REST de Atria. Contrato común con las demás fuentes de barrido
(`referentes/fuentes/base.py`): `estimar`, `probar`, `traer`. Formas de
respuesta verificadas en vivo 2026-09-24 (ver el plan del bloque 4).
`_pedir` es la costura de pruebas — las pruebas la reemplazan con
`tests/fixtures/atria_*.json`.
"""
import math
import os
import time
from datetime import date

import requests
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from referentes.fuentes.base import AVISO_CUOTA_AGOTADA, ErrorFuente

BASE_URL = "https://api.tryatria.com/open/v1"
PAGE_SIZE = 50
ESPERA_ENTRE_LLAMADAS = 3.2
ESPERA_LIMITE = 60
LLAMADAS_MES_DEFECTO = 1200
TIMEOUT = 20


class _LimiteExcedido(RuntimeError):
    """code 42901 dos veces seguidas: se acabaron las llamadas del plan este mes."""


def _api_key():
    return (os.environ.get("ATRIA_API_KEY") or "").strip()


def limite_mensual():
    try:
        return int(os.environ.get("ATRIA_LLAMADAS_MES") or LLAMADAS_MES_DEFECTO)
    except (TypeError, ValueError):
        return LLAMADAS_MES_DEFECTO


def _clave_mes():
    return f"atria_llamadas:{date.today().strftime('%Y-%m')}"


def llamadas_este_mes():
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave_mes())).scalar()
    try:
        return int(crudo or 0)
    except (TypeError, ValueError):
        return 0


def _incrementar_contador():
    clave = _clave_mes()
    with db.conectar() as con:
        # Lock de escritura antes de leer (mismo truco que cuentas.limite_ok):
        # sin él dos tramos a la vez leen el mismo contador y uno pisa al otro.
        con.execute(db.kv.update().where(db.kv.c.clave == clave).values(valor=db.kv.c.valor))
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
        try:
            n = int(crudo or 0) + 1
        except (TypeError, ValueError):
            n = 1
        con.execute(insert_sqlite(db.kv).values(clave=clave, valor=str(n), actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"], set_={"valor": str(n), "actualizado_en": db.ahora()}))
    return n


def _sesion():
    return requests.Session()


def _get(sesion, ruta, params, llave):
    """Una petición GET real a Atria. Un `requests.RequestException` (timeout,
    error de conexión) se envuelve como `ErrorFuente` en vez de dejarlo
    escapar crudo: sin esto, un blip transitorio de red no entra por el
    camino de entrega parcial que `traer()` ya tiene para el 42901 -- revienta
    la tarea entera aunque ya hubiera avance real guardado (spec §12)."""
    try:
        return sesion.get(f"{BASE_URL}{ruta}", params=params, headers={"X-API-Key": llave}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ErrorFuente(f"No se pudo conectar con Atria: {type(e).__name__}.") from e


def _pedir(sesion, ruta, params):
    """Una llamada real a Atria (espaciada, cuenta para el contador mensual).
    Ante `code 42901` espera ESPERA_LIMITE y reintenta una vez; si vuelve a
    fallar, lanza `_LimiteExcedido` (traer() decide entre entrega parcial o
    ErrorFuente según cuánto se haya traído ya)."""
    llave = _api_key()
    if not llave:
        raise ErrorFuente("Atria no está configurado (falta ATRIA_API_KEY).")
    time.sleep(ESPERA_ENTRE_LLAMADAS)
    r = _get(sesion, ruta, params, llave)
    if r.status_code == 401:
        raise ErrorFuente("Atria no aceptó la llave (ATRIA_API_KEY).")
    _incrementar_contador()
    try:
        sobre = r.json()
    except ValueError:
        raise ErrorFuente(f"Atria respondió algo inesperado (HTTP {r.status_code}).")
    codigo = sobre.get("code")
    if codigo == 42901:
        time.sleep(ESPERA_LIMITE)
        time.sleep(ESPERA_ENTRE_LLAMADAS)
        r2 = _get(sesion, ruta, params, llave)
        _incrementar_contador()
        sobre = r2.json()
        codigo = sobre.get("code")
        if codigo == 42901:
            raise _LimiteExcedido()
    if codigo == 40401:
        raise ErrorFuente("Esa marca no existe en Atria.")
    if codigo not in (0, None):
        raise ErrorFuente(sobre.get("message") or f"Atria devolvió un error ({codigo}).")
    return sobre.get("data") or {}


def probar():
    _pedir(_sesion(), "/ad-library/search", {"page_size": 1, "query": "a", "language": "es"})
    return None


def estimar(consulta, tope):
    llamadas = max(1, math.ceil(int(tope or 0) / PAGE_SIZE))
    return {"usd_fuente": 0.0, "llamadas": llamadas,
            "detalle": f"{llamadas} llamada{'s' if llamadas != 1 else ''} del plan de Atria"}


def _normalizar(item):
    if not item.get("platform_native_id"):
        return None
    fecha = (item.get("start_date") or "")[:10] or None
    imagenes = item.get("images") or []
    videos = item.get("videos") or []
    imagen_origen = imagenes[0]["url"] if imagenes else (videos[0]["preview_image_url"] if videos else None)
    pagina_id = (item.get("brand_id") or "").lstrip("m") or None
    extra = {"video_url": videos[0]["url"]} if videos else {}
    return {
        "anuncio_id": str(item["platform_native_id"]),
        "pagina_id": pagina_id,
        "marca": item.get("brand_name") or "",
        "titular": item.get("title") or "",
        "cuerpo": item.get("body") or "",
        "idioma": item.get("language") or None,
        "pais": None,
        "tipo": {"image": "imagen", "video": "video", "carousel": "carrusel"}.get(item.get("display_format"), "imagen"),
        "imagen_origen": imagen_origen,
        "dias": item.get("days_running"),
        "variantes": item.get("creative_duplicates"),
        "primera_vez": fecha,
        "ultima_vez": item.get("last_seen_date") or fecha,
        "activo": item.get("status") == "active",
        "url_anuncio": f"https://www.facebook.com/ads/library/?id={item['platform_native_id']}",
        "url_marca": f"https://www.facebook.com/ads/library/?view_all_page_id={pagina_id or ''}",
        "etiquetas_fuente": {"themes": item.get("themes") or [], "industrias": item.get("brand_industries") or []},
        "extra": extra,
    }


def _formato_atria(consulta):
    return {"imagen": "image", "video": "video"}.get(consulta.get("formato") or "imagen", "image")


def _params(consulta, cursor):
    p = {"display_format": _formato_atria(consulta), "page_size": PAGE_SIZE}
    if consulta.get("solo_activos", True):
        p["status"] = "active"
    if consulta.get("min_dias"):
        p["min_days_running"] = int(consulta["min_dias"])
    if consulta.get("min_variantes"):
        p["min_creative_duplicates"] = int(consulta["min_variantes"])
    if cursor:
        p["cursor"] = cursor
    return p


def traer(consulta, tope, avanzar, cursor=None):
    """Itera páginas de hasta PAGE_SIZE anuncios normalizados (o None para un
    ítem sin platform_native_id), reanudable desde cursor (el
    barrido.extra.cursor_atria de la corrida anterior). Cada página se
    entrega como (anuncios, cursor_siguiente, meta) -- meta siempre {} para
    Atria, que no tiene costo propio por llamada (solo consume el cupo
    mensual del plan; ver referentes.fuentes.base para el contrato general de
    meta). `cursor_siguiente` es None cuando ya no hay más. Ante el límite
    mensual agotado a mitad de camino, entrega una página vacía con cursor
    None (entrega parcial) en vez de lanzar — a menos que no se haya traído
    nada todavía en esta llamada, en cuyo caso levanta ErrorFuente."""
    modo = consulta.get("modo")
    sesion = _sesion()
    traidos = 0
    tope = int(tope or 0)
    while traidos < tope:
        params = _params(consulta, cursor)
        if modo == "marca":
            ruta = f"/brand-library/m{consulta['pagina_id']}/ads"
            params["order"] = "most_active"
        else:
            ruta = "/ad-library/search"
            params["query"] = consulta.get("palabra") or ""
            params["language"] = consulta.get("idioma") or "es"
        try:
            data = _pedir(sesion, ruta, params)
        except _LimiteExcedido:
            if traidos == 0:
                raise ErrorFuente("Atria: se acabaron las llamadas del plan este mes.")
            # Entrega parcial "graciosa" (spec §12): no se lanza porque ya se
            # trajo algo en ESTA llamada, pero `traer()` no tiene forma de
            # decirle al llamador POR QUÉ dejó de traer -- `([], None)` es la
            # misma forma que una búsqueda genuinamente agotada. `avanzar` con
            # este detalle reservado es la única señal fuera de banda.
            avanzar(detalle=AVISO_CUOTA_AGOTADA)
            yield [], None, {}
            return
        items_originales = data.get("items") or []
        if not items_originales:
            yield [], None, {}
            return
        # "Hay más" se decide contra el page_size que la PROPIA respuesta
        # declara (data.page_size) y sobre la cuenta ANTES de recortar por
        # tope — nunca contra la constante del módulo ni contra la lista ya
        # recortada, o una página completa pero con tope alcanzado se leería
        # como "última página" y cortaría el cursor de más.
        tam_pagina = data.get("page_size") or PAGE_SIZE
        hay_mas = len(items_originales) >= tam_pagina
        items = items_originales[:max(0, tope - traidos)]
        pagina = [_normalizar(it) for it in items]
        traidos += len(items)
        cursor_siguiente = data.get("cursor") if hay_mas else None
        avanzar(detalle=f"{min(traidos, tope)}/{tope}")
        yield pagina, cursor_siguiente, {}
        if not cursor_siguiente:
            return
        cursor = cursor_siguiente
