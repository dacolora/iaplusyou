"""Copia de UNA cuenta publicitaria de Meta en la base (spec §6): datos de la cuenta, campañas, conjuntos y
anuncios, métricas por día de la cuenta y de cada anuncio, alcance por ventana y tasas de cambio.

Leer de Meta no cobra. La primera copia trae 13 meses de cuenta y 90 días de anuncio; después solo se repasan
los últimos 7 días (Meta reatribuye compras de días pasados, así que ese rango se borra y se vuelve a escribir).
La primera copia va del tramo más NUEVO al más viejo y apunta hasta dónde llegó (`cuenta_desde`, `anuncios_desde`):
si Meta pide esperar a mitad (límite de uso), la siguiente corrida repasa lo reciente y sigue desde ahí hacia atrás
en vez de empezar de nuevo. Leer de Meta cuenta contra el límite de uso de la cuenta, así que el listado completo de
anuncios (pausados y limpieza de archivados) se hace como mucho una vez cada 20 horas.
Una `ErrorGraph` sube tal cual: la tarea la anota en la cuenta; aquí la cuenta queda en «copiando», nunca «ok»
a medias. Los textos de error ya vienen traducidos y sin token (graph.py)."""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
import idiomas
from meta_rendimiento import cuentas, datos, graph, tasas
from tareas.meta import MONEDAS_SIN_DECIMALES

log = logging.getLogger("creatv.meta_rendimiento.sync")

CAMPOS_CUENTA_DIA = ("spend,impressions,reach,clicks,outbound_clicks,inline_link_clicks,actions,action_values,"
                     "video_thruplay_watched_actions,date_start")
CAMPOS_ANUNCIO_DIA = ("ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,spend,impressions,clicks,"
                      "outbound_clicks,inline_link_clicks,actions,action_values,video_thruplay_watched_actions,"
                      "video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,"
                      "video_p100_watched_actions,date_start")
DIAS_CUENTA_INICIAL = 395
DIAS_ANUNCIO_INICIAL = 90
DIAS_RECOPIA = 7
TRAMO_ANUNCIO = 10   # un informe de anuncios de 10 días: ~12 000 filas a la vez como mucho (VPS de 2 GB)
TRAMO_CUENTA = 90
VENTANAS_ALCANCE = (7, 14, 30, 90)

ESTADOS = ["ACTIVE", "PAUSED", "WITH_ISSUES", "IN_PROCESS", "PENDING_REVIEW", "DISAPPROVED", "CAMPAIGN_PAUSED",
           "ADSET_PAUSED"]
# Los anuncios se listan en dos tandas: los que entregan o esperan (con su creativo para la miniatura, pesados: de
# 100 en 100) y los pausados (solo campos ligeros: de 500 en 500). Un anuncio que no sale en ninguna de las dos
# está archivado o borrado y se queda sin estado.
ESTADOS_ANUNCIO = ["ACTIVE", "WITH_ISSUES", "PENDING_REVIEW", "DISAPPROVED", "IN_PROCESS"]
ESTADOS_ANUNCIO_PAUSADOS = ["PAUSED", "ADSET_PAUSED", "CAMPAIGN_PAUSED"]
HORAS_LISTADO_COMPLETO = 20
CODIGO_PARAMETRO_INVALIDO = 100
LIMITE_PAGINA = 500
LIMITE_ANUNCIOS = 100   # con `creative{…}` Meta responde «reduce the amount of data» a 500 por página
# Un listado cortado por el tope de páginas dejaría sin estado a todo lo que falta: el tope es holgado aun con el
# límite reducido a 25 (graph.paginar).
MAX_PAGINAS_LISTADO = 1000

CAMPOS_INFO = "name,currency,timezone_name,account_status,disable_reason,amount_spent,spend_cap"
CAMPOS_CAMPANA = "id,name,objective,effective_status,daily_budget,lifetime_budget,bid_strategy,created_time"
CAMPOS_CONJUNTO = ("id,name,campaign_id,effective_status,daily_budget,lifetime_budget,optimization_goal,"
                   "bid_strategy,learning_stage_info,created_time")
CAMPOS_ANUNCIO = "id,name,adset_id,campaign_id,effective_status,created_time,creative{id,thumbnail_url,video_id}"
CAMPOS_ANUNCIO_LIGERO = "id,name,adset_id,campaign_id,effective_status"

ETAPA_CUENTA = idiomas.N_("Leyendo la cuenta")
ETAPA_OBJETOS = idiomas.N_("Campañas, conjuntos y anuncios")
ETAPA_METRICAS = idiomas.N_("Métricas por día")
ETAPA_ALCANCE = idiomas.N_("Alcance")


# ------------------------------------------------------------ filas (puras) ---

def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _salida(f):
    salida = graph.acciones(f.get("outbound_clicks"), ("outbound_click",))
    return int(salida or _n(f.get("inline_link_clicks")))


def _video(f, campo):
    return int(graph.acciones(f.get(campo), ("video_view",)))


def fila_cuenta(f):
    return {"fecha": f.get("date_start"), "gasto": _n(f.get("spend")), "impresiones": int(_n(f.get("impressions"))),
            "alcance": int(_n(f.get("reach"))), "clics": int(_n(f.get("clicks"))), "clics_salida": _salida(f),
            "compras": graph.acciones(f.get("actions"), graph.TIPOS_COMPRA),
            "valor": graph.acciones(f.get("action_values"), graph.TIPOS_COMPRA),
            "vistas_3s": int(graph.acciones(f.get("actions"), ("video_view",))),
            "thruplays": _video(f, "video_thruplay_watched_actions")}


def fila_anuncio(f):
    base = fila_cuenta(f)
    base.pop("alcance")
    # Sin ad_id queda None (datos ignora la fila): nunca el texto «None» como si fuera un anuncio.
    return dict(base, ad_id=str(f["ad_id"]) if f.get("ad_id") else None, adset_id=f.get("adset_id"),
                campaign_id=f.get("campaign_id"),
                p25=_video(f, "video_p25_watched_actions"), p50=_video(f, "video_p50_watched_actions"),
                p75=_video(f, "video_p75_watched_actions"), p100=_video(f, "video_p100_watched_actions"))


# --------------------------------------------------------- objetos (puros) ---

def _presupuesto(valor, moneda):
    """Meta manda el presupuesto en la unidad menor de la moneda (centavos) como texto; en las monedas sin
    decimales ya viene entero. «0», vacío o ilegible = sin presupuesto en ese nivel (None, nunca 0)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v if (moneda or "").upper() in MONEDAS_SIN_DECIMALES else round(v / 100, 2)


def _creado(f):
    return str(f["created_time"])[:25] if f.get("created_time") else None


def _campana(f, moneda):
    return {"nivel": "campana", "objeto_id": str(f["id"]), "nombre": f.get("name"), "estado": f.get("effective_status"),
            "objetivo": f.get("objective"), "presupuesto_diario": _presupuesto(f.get("daily_budget"), moneda),
            "presupuesto_total": _presupuesto(f.get("lifetime_budget"), moneda),
            "estrategia_puja": f.get("bid_strategy"), "creado_en_meta": _creado(f)}


def _conjunto(f, moneda):
    return {"nivel": "conjunto", "objeto_id": str(f["id"]), "padre_id": f.get("campaign_id"),
            "campaign_id": f.get("campaign_id"), "nombre": f.get("name"), "estado": f.get("effective_status"),
            "optimizacion": f.get("optimization_goal"), "presupuesto_diario": _presupuesto(f.get("daily_budget"), moneda),
            "presupuesto_total": _presupuesto(f.get("lifetime_budget"), moneda),
            "estrategia_puja": f.get("bid_strategy"),
            "aprendizaje": (f.get("learning_stage_info") or {}).get("status"), "creado_en_meta": _creado(f)}


def _anuncio(f):
    creative = f.get("creative") or {}
    return {"nivel": "anuncio", "objeto_id": str(f["id"]), "padre_id": f.get("adset_id"),
            "campaign_id": f.get("campaign_id"), "nombre": f.get("name"), "estado": f.get("effective_status"),
            "creative_id": creative.get("id"), "miniatura_url": creative.get("thumbnail_url"),
            "video_id": creative.get("video_id"), "creado_en_meta": _creado(f)}


def _anuncio_ligero(f):
    """Un anuncio pausado, de un listado sin creativo: no trae miniatura ni video y por eso esas claves NO van
    (guardar_objetos solo toca las columnas presentes: la miniatura que ya se copió se conserva)."""
    return {"nivel": "anuncio", "objeto_id": str(f["id"]), "padre_id": f.get("adset_id"),
            "campaign_id": f.get("campaign_id"), "nombre": f.get("name"), "estado": f.get("effective_status")}


def objetos_de(campanas, conjuntos, anuncios, moneda=None, anuncios_ligeros=None):
    """Graph → filas de `meta_objeto` (para `datos.guardar_objetos`). `moneda` decide si el presupuesto se divide
    entre 100 (casi todas) o viene entero (JPY, CLP, COP…). `anuncios_ligeros`: anuncios de un listado sin
    creativo (los pausados)."""
    return ([_campana(f, moneda) for f in campanas or [] if f.get("id")]
            + [_conjunto(f, moneda) for f in conjuntos or [] if f.get("id")]
            + [_anuncio(f) for f in anuncios or [] if f.get("id")]
            + [_anuncio_ligero(f) for f in anuncios_ligeros or [] if f.get("id")])


def _recoger_nombres(por_id, filas):
    """Suma a `por_id` los objetos con SOLO el nombre (y quién es su padre) que traen filas de insights. Sin la
    clave «estado»: `datos.guardar_objetos` solo toca las columnas presentes, así que no borran el estado, el
    presupuesto ni la miniatura que ya se copiaron del listado. Una fila sin nombre no crea nada."""
    for f in filas:
        for nivel, campo, nombre, padre in (("anuncio", "ad_id", "ad_name", "adset_id"),
                                            ("conjunto", "adset_id", "adset_name", "campaign_id"),
                                            ("campana", "campaign_id", "campaign_name", None)):
            if not f.get(campo) or not f.get(nombre):
                continue
            o = {"nivel": nivel, "objeto_id": str(f[campo]), "nombre": f[nombre]}
            if padre and f.get(padre):
                o["padre_id"] = str(f[padre])
            if nivel != "campana" and f.get("campaign_id"):
                o["campaign_id"] = str(f["campaign_id"])
            por_id[(nivel, o["objeto_id"])] = o


# ------------------------------------------------------------------ apoyo ---

def _hoy_local(zona, ahora=None):
    """La fecha de hoy en la zona de la cuenta (Meta da el día de las métricas en esa zona). Sin zona o con una
    que no existe, la del servidor."""
    try:
        return (ahora or datetime.now(timezone.utc)).astimezone(ZoneInfo(zona)).date()
    except Exception:  # noqa: BLE001 — ZoneInfoNotFoundError, ValueError, TypeError (zona None): todo cae a la fecha local
        return date.today()


def _tramos(desde, hasta, dias):
    """[desde, hasta] partido en tramos seguidos de hasta `dias` días, como (AAAA-MM-DD, AAAA-MM-DD)."""
    a = desde
    while a <= hasta:
        b = min(a + timedelta(days=dias - 1), hasta)
        yield a.isoformat(), b.isoformat()
        a = b + timedelta(days=1)


def _rango(a, b):
    return json.dumps({"since": a, "until": b})


def _listar(act, token, edge, campos, estados, limite=LIMITE_PAGINA):
    return graph.paginar(f"{act}/{edge}", token, {
        "fields": campos, "limit": limite,
        "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": estados}])},
        max_paginas=MAX_PAGINAS_LISTADO)


def _fecha(texto):
    try:
        return date.fromisoformat(str(texto)[:10])
    except ValueError:
        return None


def _tramos_atras(desde, hasta, dias):
    """[desde, hasta] partido en tramos de hasta `dias` días, del más NUEVO al más viejo."""
    b = hasta
    while b >= desde:
        a = max(desde, b - timedelta(days=dias - 1))
        yield a.isoformat(), b.isoformat()
        b = a - timedelta(days=1)


def _plan(hoy, dias_atras, tramo, hecho, marcador, ultima):
    """Los tramos a pedir, en orden, como (desde, hasta, es_relleno). `es_relleno` = parte de la primera copia
    (tras cada uno se apunta hasta dónde se llegó).

    - Primera vez (sin `hecho` ni `marcador`): toda la ventana inicial (`dias_atras` días antes de hoy), del tramo
      más nuevo al más viejo.
    - Ya hecha: lo reciente = los últimos 7 días, o desde el ÚLTIMO día ya copiado si pasó más tiempo (cubre el
      hueco; ese día se repite porque pudo copiarse con el día a medias), sin pasar de la ventana inicial.
    - Relleno a medias (`marcador` = el día más viejo ya copiado): lo reciente como arriba, y después sigue hacia
      atrás desde el día anterior al marcador hasta el fondo de la ventana."""
    tope = hoy - timedelta(days=dias_atras)
    marca = None if hecho else _fecha(marcador)
    if not hecho and marca is None:
        return [(a, b, True) for a, b in _tramos_atras(tope, hoy, tramo)]
    desde = hoy - timedelta(days=DIAS_RECOPIA - 1)
    ultimo = _fecha(ultima) or marca
    if ultimo:
        desde = min(desde, ultimo)
    plan = [(a, b, False) for a, b in _tramos(max(desde, tope), hoy, tramo)]
    if marca:
        plan += [(a, b, True) for a, b in _tramos_atras(tope, marca - timedelta(days=1), tramo)]
    return plan


def _listado_vencido(marca):
    """True si el listado completo de anuncios nunca se hizo o se hizo hace más de 20 horas."""
    try:
        return datetime.fromisoformat(db.ahora()) - datetime.fromisoformat(str(marca)) > timedelta(
            hours=HORAS_LISTADO_COMPLETO)
    except (TypeError, ValueError):
        return True


def _por_pagina(filas, nombres):
    """Callback de `graph.informe`: cada página cruda de insights de anuncios se convierte en filas chicas
    (`fila_anuncio`) y en nombres de objetos, y la página cruda se suelta."""
    def pagina(crudas):
        filas.extend(fila_anuncio(f) for f in crudas)
        _recoger_nombres(nombres, crudas)
    return pagina


def _alcance_de_ventana(act, token, w):
    """Filas de `meta_alcance` de una ventana (cuenta + cada campaña con entrega), o None si Meta no acepta la
    ventana (parámetro inválido): esa ventana se salta sin romper la copia. Cualquier otro error sube."""
    preset = f"last_{w}d"
    try:
        cuenta = graph.get(f"{act}/insights", token, {"level": "account", "date_preset": preset,
                                                       "fields": "reach,frequency"})
        campanas = graph.paginar(f"{act}/insights", token, {
            "level": "campaign", "date_preset": preset, "fields": "campaign_id,reach,frequency",
            "limit": LIMITE_PAGINA})
    except graph.ErrorGraph as e:
        if e.codigo == CODIGO_PARAMETRO_INVALIDO:
            log.warning("meta alcance %s: ventana %s no aceptada por Meta", act, preset)
            return None
        raise

    def fila(nivel, objeto_id, f):
        frec = f.get("frequency")
        return {"nivel": nivel, "objeto_id": objeto_id, "ventana": w, "alcance": int(_n(f.get("reach"))),
                "frecuencia": None if frec in (None, "") else _n(frec)}

    # Sin entrega en la ventana Meta no devuelve fila: es alcance 0, y se escribe para no dejar el de antes.
    filas = [fila("cuenta", act, (cuenta.get("data") or [{}])[0])]
    filas += [fila("campana", str(f["campaign_id"]), f) for f in campanas if f.get("campaign_id")]
    return filas


# --------------------------------------------------------------- sincronizar ---

def sincronizar(cliente, ad_account_id, token, hoy=None, on_etapa=None):
    """Copia la cuenta `ad_account_id` del proyecto `cliente`. Devuelve
    {"omitida", "dias_cuenta", "filas_anuncio", "objetos", "desde", "hasta"}. `on_etapa(nombre, progreso 0-100)`
    se llama al empezar cada paso. Una ErrorGraph sube sin tocar el estado de la cuenta (queda «copiando»).

    Si la cuenta ya no está en el proyecto (la quitaron mientras esperaba su turno) no se llama a Meta ni se
    escribe nada: devuelve `omitida=True`."""
    act = cuentas.normalizar_id(ad_account_id)
    guardada = cuentas.cuenta(cliente, act)
    if guardada is None:
        return {"omitida": True, "dias_cuenta": 0, "filas_anuncio": 0, "objetos": 0, "desde": None, "hasta": None}

    def etapa(nombre, progreso):
        if on_etapa:
            on_etapa(nombre, progreso)

    # 1. La cuenta.
    etapa(ETAPA_CUENTA, 5)
    info = graph.get(act, token, {"fields": CAMPOS_INFO}) or {}
    moneda = (info.get("currency") or guardada.get("moneda") or "")[:3].upper() or None
    cambios = {k: v for k, v in (("nombre", info.get("name")), ("moneda", moneda),
                                 ("zona_horaria", info.get("timezone_name"))) if v}
    cuentas.actualizar(cliente, act, **cambios, estado="copiando", error=None)
    cuentas.actualizar_extra(cliente, act, {"cuenta": {k: info.get(k) for k in (
        "account_status", "disable_reason", "amount_spent", "spend_cap")}})
    hoy = hoy or _hoy_local(info.get("timezone_name") or guardada.get("zona_horaria"))
    extra = guardada.get("extra") or {}
    # `backfill_hecho` (copias anteriores) vale por las dos; así un fallo en el alcance no repite los 13 meses.
    cuenta_hecha = bool(extra.get("backfill_cuenta") or extra.get("backfill_hecho"))
    anuncios_hecho = bool(extra.get("backfill_anuncios") or extra.get("backfill_hecho"))

    # 2. Campañas, conjuntos y anuncios. Cada nivel se guarda y se marca apenas su listado termina COMPLETO:
    # si una página falla, la ErrorGraph sube antes de marcar y nadie queda sin estado por un listado a medias.
    etapa(ETAPA_OBJETOS, 15)
    n_objetos = 0
    campanas = _listar(act, token, "campaigns", CAMPOS_CAMPANA, ESTADOS)
    objetos = objetos_de(campanas, [], [], moneda)
    n_objetos += datos.guardar_objetos(cliente, act, objetos)
    datos.marcar_sin_estado(cliente, act, "campana", [o["objeto_id"] for o in objetos])
    conjuntos = _listar(act, token, "adsets", CAMPOS_CONJUNTO, ESTADOS)
    objetos = objetos_de([], conjuntos, [], moneda)
    n_objetos += datos.guardar_objetos(cliente, act, objetos)
    datos.marcar_sin_estado(cliente, act, "conjunto", [o["objeto_id"] for o in objetos])
    # Anuncios: siempre los que entregan o esperan (con creativo). Los pausados (campos ligeros) y la limpieza de
    # los archivados solo cuando el último listado completo tiene más de 20 horas: son miles de filas y cada página
    # cuenta contra el límite de uso de la cuenta. Solo cuando LAS DOS listas terminaron se quita el estado a los que
    # no salieron en ninguna (archivados o borrados).
    completo = _listado_vencido(extra.get("listado_completo_en"))
    anuncios = _listar(act, token, "ads", CAMPOS_ANUNCIO, ESTADOS_ANUNCIO, LIMITE_ANUNCIOS)
    objetos = objetos_de([], [], anuncios, moneda)
    n_objetos += datos.guardar_objetos(cliente, act, objetos)
    vistos = {o["objeto_id"] for o in objetos}
    anuncios = objetos = None
    if completo:
        pausados = _listar(act, token, "ads", CAMPOS_ANUNCIO_LIGERO, ESTADOS_ANUNCIO_PAUSADOS)
        objetos = objetos_de([], [], [], moneda, anuncios_ligeros=pausados)
        n_objetos += datos.guardar_objetos(cliente, act, objetos)
        vistos.update(o["objeto_id"] for o in objetos)
        pausados = objetos = None
        datos.marcar_sin_estado(cliente, act, "anuncio", vistos)
        cuentas.actualizar_extra(cliente, act, {"listado_completo_en": db.ahora()})
    vistos = None

    # 3 y 4. Métricas por día de la cuenta y de cada anuncio. Se lee hasta qué día hay datos ANTES de escribir.
    plan_cuenta = _plan(hoy, DIAS_CUENTA_INICIAL, TRAMO_CUENTA, cuenta_hecha, extra.get("cuenta_desde"),
                        datos.ultima_fecha(cliente, act, "cuenta"))
    plan_anuncio = _plan(hoy, DIAS_ANUNCIO_INICIAL - 1, TRAMO_ANUNCIO, anuncios_hecho, extra.get("anuncios_desde"),
                         datos.ultima_fecha(cliente, act, "anuncio"))
    desde_cuenta = min(_fecha(a) for a, _, _ in plan_cuenta)
    total = len(plan_cuenta) + len(plan_anuncio)
    hecho = 0
    dias_cuenta = filas_anuncio = 0
    for a, b, relleno in plan_cuenta:
        etapa(ETAPA_METRICAS, 30 + 55.0 * hecho / total)
        filas = graph.paginar(f"{act}/insights", token, {
            "level": "account", "time_increment": 1, "time_range": _rango(a, b), "fields": CAMPOS_CUENTA_DIA,
            "limit": LIMITE_PAGINA})
        dias_cuenta += datos.reemplazar_cuenta_dias(cliente, act, a, b, [fila_cuenta(f) for f in filas])
        filas = None
        if relleno:   # hasta dónde llegó la primera copia: si Meta pide esperar, la siguiente sigue desde aquí
            cuentas.actualizar_extra(cliente, act, {"cuenta_desde": a})
        hecho += 1
    cuentas.actualizar_extra(cliente, act, {"backfill_cuenta": True})
    for a, b, relleno in plan_anuncio:
        etapa(ETAPA_METRICAS, 30 + 55.0 * hecho / total)
        # Cada página de insights se vuelve filas chicas y se suelta (una fila cruda pesa ~8 KB): en un tramo
        # grande las filas crudas nunca viven todas a la vez.
        filas, nombres = [], {}
        graph.informe(act, token, {
            "level": "ad", "time_increment": 1, "time_range": _rango(a, b), "fields": CAMPOS_ANUNCIO_DIA,
            "limit": LIMITE_PAGINA}, por_pagina=_por_pagina(filas, nombres))
        filas_anuncio += datos.reemplazar_anuncio_dias(cliente, act, a, b, filas)
        datos.guardar_objetos(cliente, act, list(nombres.values()))
        filas = nombres = None
        if relleno:
            cuentas.actualizar_extra(cliente, act, {"anuncios_desde": a})
        hecho += 1
    cuentas.actualizar_extra(cliente, act, {"backfill_anuncios": True})

    # 5. Alcance (gente única: se pide por ventana, no se suma de los días).
    etapa(ETAPA_ALCANCE, 90)
    for w in VENTANAS_ALCANCE:
        filas = _alcance_de_ventana(act, token, w)
        if filas:
            datos.guardar_alcance(cliente, act, filas)

    # 6. Tasas de cambio a USD (nunca lanza). Desde el día más viejo YA guardado de la cuenta, no solo desde esta
    # corrida: si el relleno se hizo en varias corridas, los días de las primeras también necesitan su tasa.
    if moneda:
        tasas.asegurar([moneda], datos.primera_fecha(cliente, act, "cuenta") or desde_cuenta.isoformat(),
                       hoy.isoformat(), hoy=hoy)

    cuentas.actualizar(cliente, act, estado="ok", error=None, ultima_copia=db.ahora())
    cuentas.actualizar_extra(cliente, act, {"backfill_hecho": True})
    return {"omitida": False, "dias_cuenta": dias_cuenta, "filas_anuncio": filas_anuncio, "objetos": n_objetos,
            "desde": desde_cuenta.isoformat(), "hasta": hoy.isoformat()}
