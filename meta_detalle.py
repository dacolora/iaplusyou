"""
Detalle de Meta por anuncio para el centro de resultados (spec
2026-10-02-experimentos-centro-de-resultados §3): día a día (con embudo y
retención de video), desgloses desde el inicio (ubicación, edad y género,
dispositivo, región) y los rankings de calidad de Meta.

Único escritor de `metrica_dia` y `metrica_desglose`, y de
`experimento_pieza.extra["rankings_meta"]` (vía experimentos.marcar_pieza).
Pide a nivel campaña con level=ad (una llamada por experimento, no por
anuncio) usando meta_ads.auth.llamar; no toca el submódulo meta_ads. Leer de
Meta no cuesta: nada de aquí registra gasto. Un fallo de aquí nunca debe
tumbar lanzador.refrescar ni el decisor.
"""
import json
import logging
import math
import time
from contextvars import ContextVar
from flask_babel import gettext
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

from meta_ads import auth

import cola
import db
import experimentos
import lanzador
import meta_errores

log = logging.getLogger("creatv.meta_detalle")

MAX_PAGINAS = 20
PLAZO_S = 60
_PLAZO = ContextVar("detalle_meta_plazo", default=None)


class Paginas(list):
    incompleto = False


def _comprobar_plazo():
    plazo = _PLAZO.get()
    if plazo is not None and time.monotonic() >= plazo:
        raise _Corte(gettext("El detalle de Meta quedó incompleto por el límite de tiempo."))

_BASE = "ad_id,impressions,reach,frequency,clicks,inline_link_clicks,spend,cpm,actions,action_values"
CAMPOS_DIA = (_BASE + ",video_play_actions,video_p25_watched_actions,video_p50_watched_actions"
              ",video_p75_watched_actions,video_p95_watched_actions,video_p100_watched_actions"
              ",video_thruplay_watched_actions,video_avg_time_watched_actions")
# Desgloses: solo lo que fila_desglose guarda (sin reach/frequency/cpm/clicks: el alcance con desgloses
# es caro y Meta lo restringe a 13 meses) y sin los campos de retención (Meta rechaza algunas
# combinaciones de video con desgloses); el gancho sale de actions[video_view].
CAMPOS_DESGLOSE = "ad_id,impressions,inline_link_clicks,spend,actions,action_values,video_thruplay_watched_actions"
CAMPOS_RANKINGS = "ad_id,impressions,quality_ranking,engagement_rate_ranking,conversion_rate_ranking"

# Dimensión -> breakdowns de la Graph API (la clave guardada une sus valores con «|»).
DIMENSIONES = {"ubicacion": "publisher_platform,platform_position", "edad_genero": "age,gender",
               "dispositivo": "device_platform", "region": "region"}

# Tipos de acción por paso del embudo, en orden de preferencia: Meta repite el
# mismo evento con y sin «omni_»; se toma el primero que exista (sumarlos
# contaría doble).
_CARRITO = ("omni_add_to_cart", "add_to_cart", "offsite_conversion.fb_pixel_add_to_cart")
_PAGO = ("omni_initiated_checkout", "initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout")
_COMPRA = ("purchase", "omni_purchase")   # mismo orden que meta_ads/insights.obtener_resultados


def _num(valor):
    try:
        n = float(valor or 0)
        return n if math.isfinite(n) and abs(n) < 2**63 else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _accion(lista, tipo):
    for a in lista or []:
        if a.get("action_type") == tipo:
            return _num(a.get("value"))
    return 0.0


def _primera(lista, tipos):
    """Valor del primer tipo de acción presente (aunque valga 0)."""
    presentes = {a.get("action_type") for a in lista or []}
    for t in tipos:
        if t in presentes:
            return _accion(lista, t)
    return 0.0


def _video(fila, campo):
    return _accion(fila.get(campo), "video_view")


def fila_diaria(fila):
    """Fila de insights (level=ad, time_increment=1) -> columnas de metrica_dia."""
    acciones = fila.get("actions")
    return {
        "fecha": fila.get("date_start"),
        "impresiones": int(_num(fila.get("impressions"))), "alcance": int(_num(fila.get("reach"))),
        "frecuencia": _num(fila.get("frequency")), "clics": int(_num(fila.get("clicks"))),
        "clics_enlace": int(_num(fila.get("inline_link_clicks"))), "gasto": _num(fila.get("spend")),
        "cpm": _num(fila.get("cpm")),
        "vistas_3s": int(_accion(acciones, "video_view")),
        "reproducciones": int(_video(fila, "video_play_actions")),
        "p25": int(_video(fila, "video_p25_watched_actions")), "p50": int(_video(fila, "video_p50_watched_actions")),
        "p75": int(_video(fila, "video_p75_watched_actions")), "p95": int(_video(fila, "video_p95_watched_actions")),
        "p100": int(_video(fila, "video_p100_watched_actions")),
        "thruplay": int(_video(fila, "video_thruplay_watched_actions")),
        "tiempo_medio_s": _video(fila, "video_avg_time_watched_actions"),
        "visitas_pagina": int(_accion(acciones, "landing_page_view")),
        "carrito": int(_primera(acciones, _CARRITO)), "pago_iniciado": int(_primera(acciones, _PAGO)),
        "compras_meta": int(_primera(acciones, _COMPRA)),
        "ingresos_meta": _primera(fila.get("action_values"), _COMPRA),
    }


def fila_desglose(fila, dimension):
    """Fila de insights con breakdowns -> (clave, columnas de metrica_desglose)."""
    clave = "|".join(str(fila.get(c) or "") for c in DIMENSIONES[dimension].split(","))
    d = fila_diaria(fila)
    return clave, {k: d[k] for k in ("impresiones", "clics_enlace", "gasto", "vistas_3s", "thruplay",
                                     "compras_meta", "ingresos_meta")}


def _ranking(valor):
    return valor if isinstance(valor, str) and valor in {
        "ABOVE_AVERAGE", "AVERAGE", "BELOW_AVERAGE_10", "BELOW_AVERAGE_20", "BELOW_AVERAGE_35"
    } else None


def rankings_de(fila):
    return {"calidad": _ranking(fila.get("quality_ranking")),
            "interaccion": _ranking(fila.get("engagement_rate_ranking")),
            "conversion": _ranking(fila.get("conversion_rate_ranking"))}


def _filtro_campana(campaign_id):
    return json.dumps([{"field": "campaign.id", "operator": "EQUAL", "value": str(campaign_id)}])


def _paginas(params):
    """GET act_<cuenta>/insights siguiendo el cursor `after` hasta MAX_PAGINAS."""
    filas, after = Paginas(), None
    for _ in range(MAX_PAGINAS):
        _comprobar_plazo()
        p = dict(params, limit=500)
        if after:
            p["after"] = after
        data = auth.llamar("GET", f"act_{auth.ad_account_id()}/insights", params=p) or {}
        filas.extend(data.get("data") or [])
        paging = data.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            return filas
    filas.incompleto = True
    log.warning("Detalle de Meta: se cortó en %s páginas", MAX_PAGINAS)
    return filas


def _rango(desde, hasta):
    return json.dumps({"since": desde, "until": hasta})


def pedir_diario(campaign_id, desde, hasta):
    return _paginas({"level": "ad", "fields": CAMPOS_DIA, "filtering": _filtro_campana(campaign_id),
                     "time_increment": 1, "time_range": _rango(desde, hasta)})


def pedir_desglose(campaign_id, dimension, desde, hasta):
    """Total del periodo desde-hasta (no día a día) por dimensión; `desde` es la creación del experimento."""
    return _paginas({"level": "ad", "fields": CAMPOS_DESGLOSE, "filtering": _filtro_campana(campaign_id),
                     "time_range": _rango(desde, hasta), "breakdowns": DIMENSIONES[dimension]})


def pedir_rankings(campaign_id, desde, hasta):
    return _paginas({"level": "ad", "fields": CAMPOS_RANKINGS, "filtering": _filtro_campana(campaign_id),
                     "time_range": _rango(desde, hasta)})


# Días hacia atrás que se vuelven a pedir aunque ya estén: Meta corrige los últimos días.
DIAS_REPASO = 2


def _completas(filas):
    if getattr(filas, "incompleto", False):
        raise _Corte(gettext("El detalle de Meta quedó incompleto por el límite de páginas."))


def guardar_dias(ep_por_ad, filas):
    """Upsert por (anuncio, fecha). Filas de anuncios fuera de `ep_por_ad` se ignoran."""
    _completas(filas)
    n = 0
    ahora = db.ahora()
    with db.conectar() as con:
        for fila in filas:
            ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
            valores = fila_diaria(fila)
            if not ep_id or not valores["fecha"]:
                continue
            try:
                valores["fecha"] = date.fromisoformat(valores["fecha"]).isoformat()
            except (TypeError, ValueError):
                continue
            valores.update(experimento_pieza_id=ep_id, actualizado_en=ahora)
            stmt = insert_sqlite(db.metrica_dia).values(**valores)
            con.execute(stmt.on_conflict_do_update(
                index_elements=["experimento_pieza_id", "fecha"],
                set_={k: v for k, v in valores.items() if k not in ("experimento_pieza_id", "fecha")}))
            n += 1
    return n


def guardar_desglose(ep_por_ad, dimension, filas):
    """Reemplaza, en una transacción, el juego (anuncio, dimensión) de cada anuncio que vino en `filas`."""
    _completas(filas)
    por_ep = {}
    for fila in filas:
        ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
        if ep_id:
            clave, valores = fila_desglose(fila, dimension)
            por_ep.setdefault(ep_id, {})[clave[:120]] = valores
    ahora = db.ahora()
    t = db.metrica_desglose
    with db.conectar() as con:
        for ep_id, por_clave in por_ep.items():
            con.execute(t.delete().where(t.c.experimento_pieza_id == ep_id, t.c.dimension == dimension))
            for clave, valores in por_clave.items():
                con.execute(t.insert().values(experimento_pieza_id=ep_id, dimension=dimension, clave=clave[:120],
                                              actualizado_en=ahora, **valores))
    return sum(len(v) for v in por_ep.values())


def guardar_rankings(cliente, ep_por_ad, filas):
    _completas(filas)
    n = 0
    for fila in filas:
        ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
        if ep_id:
            experimentos.marcar_pieza(cliente, ep_id, rankings_meta=rankings_de(fila))
            n += 1
    return n


def desde_para(ep_ids, creado_en, hoy):
    """Desde qué día pedir: el último guardado menos DIAS_REPASO (se cura solo si
    el worker estuvo parado), o el día en que se creó el experimento. Nunca
    después de hoy."""
    with db.conectar() as con:
        ultimo = con.execute(sa.select(sa.func.max(db.metrica_dia.c.fecha))
                             .where(db.metrica_dia.c.experimento_pieza_id.in_(list(ep_ids) or [-1]))).scalar()
    try:
        desde = date.fromisoformat(ultimo) - timedelta(days=DIAS_REPASO) if ultimo else date.fromisoformat((creado_en or hoy.isoformat())[:10])
    except (TypeError, ValueError):
        desde = date.fromisoformat(desde_creacion(creado_en, hoy))
    return min(desde, hoy).isoformat()


class _Limite(Exception):
    """Meta pidió esperar (códigos de límite): se corta la pasada entera."""


class _Corte(Exception):
    """Fallo de red o HTTP 5xx: se corta la pasada entera, pero no es un límite (no se reintenta con espera)."""


def es_limite(texto):
    return meta_errores.es_limite(texto)


def _es_corte_de_red(texto):
    """Formato de meta_ads.auth.llamar cuando Meta no contesta o responde con un error del servidor:
    «Meta Ads (<edge>) respondió <status>: …» / «Meta Ads (<edge>) falló en red: <Tipo>»."""
    return "falló en red" in texto or "respondió 5" in texto


def desde_creacion(creado_en, hoy):
    """Día en que se creó el experimento (nunca después de hoy): desde dónde se piden los desgloses y los rankings."""
    try:
        d = date.fromisoformat((creado_en or hoy.isoformat())[:10])
    except (TypeError, ValueError):
        d = hoy
    return min(d, hoy).isoformat()


def _con_detalle(resultado):
    def fn(extra):
        return {**extra, "detalle_meta": {"actualizado_en": db.ahora(), "desde": resultado.get("desde"),
                                           "errores": resultado["errores"], "limite": resultado["limite"],
                                           "cortado": resultado["cortado"]}}
    return fn


def refrescar_detalle(cliente, experimento_id, hoy=None):
    """Pide y guarda el detalle de un experimento. Nunca lanza: los errores
    (sin token) quedan en el resultado y en experimento.extra["detalle_meta"]."""
    r = {"dias": 0, "desgloses": 0, "rankings": 0, "limite": False, "cortado": False, "errores": {}}

    try:
        ex = experimentos.obtener(cliente, experimento_id)
        if not ex or not ex.get("meta_campaign_id"):
            return r
        ep_por_ad = {str(p["meta_ad_id"]): p["id"] for p in ex["piezas"] if p.get("meta_ad_id")}
        if not ep_por_ad:
            return r
        hoy = hoy or date.today()
        r["desde"] = desde_para(list(ep_por_ad.values()), ex.get("creado_en"), hoy)
        desde_total = desde_creacion(ex.get("creado_en"), hoy)   # desgloses y rankings: de la creación a hoy
        campana = ex["meta_campaign_id"]

        def _parte(nombre, fn):
            try:
                _comprobar_plazo()
                fn()
            except Exception as e:  # noqa: BLE001 — una parte no tumba las otras
                texto = cola.sin_token(str(e))
                r["errores"][nombre] = cola.recortar(texto)
                log.warning("Detalle de Meta (%s, exp %s, %s): %s", cliente, experimento_id, nombre, texto)
                if isinstance(e, _Corte):
                    raise
                if es_limite(texto):
                    raise _Limite() from None
                if _es_corte_de_red(texto):   # Meta caída o con error 5xx: no seguir golpeándola
                    raise _Corte() from None

        def _correr(_creds):
            _parte("diario", lambda: r.__setitem__("dias", guardar_dias(ep_por_ad, pedir_diario(campana, r["desde"], hoy.isoformat()))))
            for dim in DIMENSIONES:
                _parte(dim, lambda dim=dim: r.__setitem__("desgloses", r["desgloses"] + guardar_desglose(ep_por_ad, dim, pedir_desglose(campana, dim, desde_total, hoy.isoformat()))))
            _parte("rankings", lambda: r.__setitem__("rankings", guardar_rankings(cliente, ep_por_ad, pedir_rankings(campana, desde_total, hoy.isoformat()))))

        plazo_token = _PLAZO.set(time.monotonic() + PLAZO_S)
        try:
            lanzador._con_credenciales(cliente, _correr)
        except _Limite:
            r["limite"] = True
        except _Corte:
            r["cortado"] = True
        except Exception as e:  # noqa: BLE001 — p. ej. Meta sin conectar
            texto = cola.sin_token(str(e))
            r["errores"]["credenciales"] = cola.recortar(texto)
            log.warning("Detalle de Meta (%s, exp %s, credenciales): %s", cliente, experimento_id, texto)
        finally:
            _PLAZO.reset(plazo_token)
    except Exception as e:  # noqa: BLE001 — desde_para, obtener, etc.
        texto = cola.sin_token(str(e))
        r["errores"]["interno"] = cola.recortar(texto)
        log.warning("Detalle de Meta (%s, exp %s, interno): %s", cliente, experimento_id, texto)

    try:
        experimentos.actualizar_extra(cliente, experimento_id, _con_detalle(r))
    except Exception as e:  # noqa: BLE001 — database locked, etc.
        texto = cola.sin_token(str(e))
        log.warning("Detalle de Meta (%s, exp %s, actualizar_extra): %s", cliente, experimento_id, texto)

    return r


def encolar_todos():
    """Carga inicial (al desplegar E1): una tarea exp_detalle por experimento
    con campaña en Meta. Idempotente por job_id. En el VPS correr con
    TZ=America/Bogota (nota de despliegue)."""
    from tareas.experimentos import job_id_detalle
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
            db.experimento.c.legado.is_(False), db.experimento.c.meta_campaign_id.isnot(None))).all()
    inicio = datetime.now()
    for posicion, (eid, cliente) in enumerate(filas):
        cola.encolar("exp_detalle", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_detalle(cliente, eid), duracion_estimada=60, max_intentos=2,
                     prioridad=1, ejecutar_desde=(inicio + timedelta(seconds=posicion * PLAZO_S)).isoformat(timespec="seconds"))
    return len(filas)
