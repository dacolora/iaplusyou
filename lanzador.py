"""
Lanzador multi-país (spec §4): traduce un experimento a objetos de Meta —
1 campaña (spend_cap = tope total) → 1 conjunto por país (presupuesto diario
propio, targeting país + edad) → 1 anuncio por pieza — y guarda cada id apenas
Meta lo devuelve, así un reintento retoma donde quedó sin duplicar nada. Todo
nace PAUSED: activar es otro clic (cambiar_estado). Las credenciales se cargan
y limpian bajo el lock de tareas.meta (mismo motivo que allá).
"""
import cola
import db
import experimentos
import meta_conexion
import notificaciones
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights
from meta_ads.targeting import Targeting
from tareas.meta import MONEDAS_SIN_DECIMALES, _LOCK, _miniatura_para_ad

ETAPAS_LANZAR = [("Campaña", 15), ("Conjuntos por país", 25), ("Anuncios", 60)]
# Meta rechaza spend_cap por debajo de ~100 USD; por debajo no se manda.
SPEND_CAP_MINIMO_USD = 100.0
_MIN_POR_MONEDA = {"COP": 400000.0, "MXN": 2000.0, "BRL": 600.0, "EUR": 100.0, "PEN": 400.0, "CLP": 100000.0, "ARS": 100000.0, "USD": 100.0}
_SNAP_DESDE_INSIGHTS = {"impresiones": "impresiones", "alcance": "alcance", "frecuencia": "frecuencia", "clics": "clics",
                        "clics_enlace": "clics_enlace", "ctr": "ctr", "cpc": "cpc", "cpm": "cpm", "thruplay": "thruplay",
                        "thruplay_rate": "thruplay_rate", "gasto_usd": "gasto", "compras": "compras", "ingresos": "ingresos", "roas": "roas",
                        "costo_por_resultado": "cpa"}


def centavos(monto, moneda):
    return int(round(float(monto) * (1 if moneda in MONEDAS_SIN_DECIMALES else 100)))


def url_destino(base, pieza_id):
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}utm_source=creatv&utm_medium=meta&utm_content={pieza_id}"


def _con_credenciales(cliente, fn):
    with _LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            return fn(creds)
        finally:
            meta_auth.limpiar()


def _validar_para_lanzar(cliente, experimento_id):
    """Chequeos previos a tocar Meta. Separado de lanzar() para poder
    envolverlos en el mismo try/except que sana el estado (M3): si el
    llamador (la ruta) ya puso 'lanzando' antes de encolar, un pre-flight que
    falla acá no debe dejar el experimento colgado en 'lanzando' para siempre."""
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    if ex["estado"] not in ("armando", "error", "lanzando"):
        raise ValueError("Ese experimento ya fue lanzado.")
    if not ex["piezas"]:
        raise ValueError("El experimento no tiene piezas: agrega al menos una antes de lanzar.")
    paises_con_piezas = {p["pais"] for p in ex["piezas"]}
    faltan = [p["pais"] for p in ex["paises"] if p["pais"] not in paises_con_piezas]
    if faltan:
        raise ValueError(f"Sin piezas para: {', '.join(faltan)}. Agrega una pieza por país o quita el país.")
    return ex


def _crear_anuncios(cliente, ex, creds, adsets, cache=None):
    """El paso "Anuncios" de lanzar(): crea creative (si falta) + ad para cada
    pieza sin meta_ad_id de ex['piezas']. Devuelve cuántos anuncios creó.
    Compartido con lanzar_piezas_nuevas, que lo llama pieza por pieza para
    poder aislar el error de una sin frenar a las demás — por eso `cache`
    es un parámetro: lanzar_piezas_nuevas construye un solo dict, sembrado
    con TODAS las piezas del experimento (no solo las nuevas), y lo pasa
    igual en cada llamada, así la segunda pieza nueva con el mismo pieza_id
    ve el creative que subió la primera en la misma corrida."""
    experimento_id = ex["id"]
    # M4: la misma pieza (mismo pieza_id) clonada a dos países comparte
    # video+creative — el link (utm_content=pieza_id) es idéntico para
    # ambas, así que crearlo dos veces solo duplica la subida (hasta 180s
    # bajo _LOCK) sin ganar nada. Se cachea por pieza_id dentro de esta
    # corrida, sembrado con lo que ya esté guardado de una corrida previa.
    creativos_por_pieza = {} if cache is None else cache
    for pz in ex["piezas"]:
        if pz.get("meta_creative_id"):
            creativos_por_pieza.setdefault(pz["pieza_id"], {
                "video_id": (pz.get("extra") or {}).get("meta_video_id"),
                "creative_id": pz["meta_creative_id"]})
    creadas = 0
    for pz in ex["piezas"]:
        if pz["meta_ad_id"]:
            continue
        experimentos.actualizar_pieza(cliente, pz["id"], estado="publicando", meta_adset_id=adsets[pz["pais"]])
        creative_id = pz["meta_creative_id"]
        if not creative_id:
            cache = creativos_por_pieza.get(pz["pieza_id"])
            if cache and cache.get("creative_id"):
                creative_id = cache["creative_id"]
                experimentos.actualizar_pieza(cliente, pz["id"], meta_creative_id=creative_id,
                                              extra={**(pz.get("extra") or {}), "meta_video_id": cache.get("video_id")})
            else:
                video_id = (pz.get("extra") or {}).get("meta_video_id") or (cache and cache.get("video_id"))
                if not video_id:
                    video_id = meta_creative.subir_video(pz["url_video"], titulo=pz["nombre"])
                    experimentos.actualizar_pieza(cliente, pz["id"],
                                                  extra={**(pz.get("extra") or {}), "meta_video_id": video_id})
                mini = pz["url_miniatura"] or _miniatura_para_ad(cliente, f"exp{experimento_id}_{pz['id']}", pz["url_video"])
                creative_id = meta_creative.crear_creative_video(
                    f"{pz['nombre']} — {pz['pais']}", video_id, mini, ex["nombre"],
                    url_destino(ex["destino_url"], pz["pieza_id"]), instagram_user_id=creds.get("ig_user_id"))["id"]
                experimentos.actualizar_pieza(cliente, pz["id"], meta_creative_id=creative_id)
                creativos_por_pieza[pz["pieza_id"]] = {"video_id": video_id, "creative_id": creative_id}
        ad_id = meta_ad.crear_ad(f"{pz['nombre']} — {pz['pais']}", adsets[pz["pais"]], creative_id)["id"]
        experimentos.actualizar_pieza(cliente, pz["id"], meta_ad_id=ad_id, estado="pausado",
                                      presupuesto_dia_actual=next(p["presupuesto_dia"] for p in ex["paises"] if p["pais"] == pz["pais"]))
        experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", f"Anuncio creado: {pz['nombre']} ({pz['pais']})",
                                      {"ad_id": ad_id}, ep_id=pz["id"])
        creadas += 1
    return creadas


def lanzar(cliente, experimento_id, on_etapa=None):
    try:
        ex = _validar_para_lanzar(cliente, experimento_id)
    except ValueError as e:
        actual = experimentos.obtener(cliente, experimento_id)
        if actual and actual["estado"] == "lanzando":
            experimentos.actualizar(cliente, experimento_id, estado="error", error=str(e))
        raise
    moneda = ex["moneda"] or (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    etapa = on_etapa or (lambda n: None)
    experimentos.actualizar(cliente, experimento_id, estado="lanzando", error=None)

    def _correr(creds):
        etapa(ETAPAS_LANZAR[0][0])
        campaign_id = ex["meta_campaign_id"]
        if not campaign_id:
            cap = centavos(ex["tope_total"], moneda) if float(ex["tope_total"] or 0) >= _MIN_POR_MONEDA.get(moneda, SPEND_CAP_MINIMO_USD) else None
            campaign_id = meta_campaign.crear_campaign(ex["nombre"], ex["objetivo_meta"], spend_cap_centavos=cap)["id"]
            experimentos.actualizar(cliente, experimento_id, meta_campaign_id=campaign_id)
            experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", "Campaña creada en Meta (en pausa)",
                                          {"campaign_id": campaign_id, "spend_cap": cap})
        etapa(ETAPAS_LANZAR[1][0])
        adsets = {}
        for p in ex["paises"]:
            adset_id = p.get("meta_adset_id")
            if not adset_id:
                targeting = Targeting().edad(int(ex["edad_min"] or 18), int(ex["edad_max"] or 65)).paises([p["pais"]]).to_dict()
                adset_id = meta_adset.crear_adset(f"{ex['nombre']} — {p['pais']}", campaign_id, ex["objetivo_meta"], targeting,
                                                  centavos(p["presupuesto_dia"], moneda), int(ex["dias"] or 7))["id"]
                experimentos.actualizar_pais(cliente, experimento_id, p["pais"], meta_adset_id=adset_id, estado="pausado")
                experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", f"Conjunto {p['pais']} creado",
                                              {"adset_id": adset_id, "presupuesto_dia": p["presupuesto_dia"]})
            adsets[p["pais"]] = adset_id
        etapa(ETAPAS_LANZAR[2][0])
        _crear_anuncios(cliente, ex, creds, adsets)

    try:
        _con_credenciales(cliente, _correr)
    except Exception as e:
        mensaje = cola.sin_token(str(e))
        ex_actual = experimentos.obtener(cliente, experimento_id)
        for pz in (ex_actual["piezas"] if ex_actual else []):
            if pz["estado"] == "publicando" and not pz["meta_ad_id"]:
                experimentos.actualizar_pieza(cliente, pz["id"], estado="en_cola")
        experimentos.actualizar(cliente, experimento_id, estado="error", error=mensaje)
        experimentos.registrar_evento(cliente, experimento_id, "error", f"Falló el lanzamiento: {mensaje}")
        notificaciones.avisar(cliente, "error_lanzamiento", f"Falló el lanzamiento de «{ex['nombre']}»",
                              f"El experimento «{ex['nombre']}» (#{experimento_id}) no se pudo lanzar a Meta.\n\n"
                              f"Motivo: {mensaje}\n\nRevísalo en el panel y vuelve a intentar.")
        raise
    experimentos.actualizar(cliente, experimento_id, estado="pausado", error=None)
    return "Experimento en Meta, en pausa. Actívalo cuando quieras empezar a gastar."


def _piezas_de(ex, pais=None):
    return [p for p in ex["piezas"] if p["meta_ad_id"] and (pais is None or p["pais"] == pais)]


def _con_activado(extra):
    """`extra` del experimento con 'activado_en' sembrado la primera vez que
    pasa a 'corriendo' (Bloque 4: el decisor lo usa para medir cuánto lleva
    corriendo). Si ya estaba, se conserva sin tocar."""
    if extra.get("activado_en"):
        return extra
    return {**extra, "activado_en": db.ahora()}


def _a_corriendo(cliente, experimento_id):
    """Pasa a `corriendo` sembrando `activado_en` con un read-modify-write
    atómico de `extra` (`experimentos.actualizar_extra`): entre que se leyó
    el experimento y acá pasaron segundos hablando con Meta, y el worker
    (derivaciones) pudo escribir `extra.derivaciones` en ese intervalo —
    escribir la foto vieja las pisaría."""
    experimentos.actualizar_extra(cliente, experimento_id, _con_activado, estado="corriendo")


def cambiar_estado(cliente, experimento_id, status, pais=None):
    if status not in ("ACTIVE", "PAUSED"):
        raise ValueError("Estado no permitido.")
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None or not ex["meta_campaign_id"] or ex["estado"] in ("armando", "lanzando", "error"):
        raise ValueError("Ese experimento todavía no está en Meta.")
    if ex["estado"] == "cerrado":
        raise ValueError("Ese experimento está cerrado.")
    local = "activo" if status == "ACTIVE" else "pausado"

    def _correr(_creds):
        if pais is None:
            meta_campaign.actualizar_estado(ex["meta_campaign_id"], status)
            for p in ex["paises"]:
                if p.get("meta_adset_id"):
                    meta_adset.actualizar_estado(p["meta_adset_id"], status)
                    experimentos.actualizar_pais(cliente, experimento_id, p["pais"], estado=local)
        else:
            p = next((p for p in ex["paises"] if p["pais"] == pais), None)
            if not p or not p.get("meta_adset_id"):
                raise ValueError("Ese país no tiene conjunto en Meta.")
            if status == "ACTIVE" and ex["estado"] != "corriendo":
                # Activar un solo país no sirve de nada si la campaña sigue en pausa
                # en Meta: sin ella, el conjunto no entrega aunque quede ACTIVE local.
                meta_campaign.actualizar_estado(ex["meta_campaign_id"], status)
            meta_adset.actualizar_estado(p["meta_adset_id"], status)
            experimentos.actualizar_pais(cliente, experimento_id, pais, estado=local)
        for pz in _piezas_de(ex, pais):
            meta_ad.actualizar_estado(pz["meta_ad_id"], status)
            if local == "activo":
                experimentos.actualizar_pieza(cliente, pz["id"], estado=local,
                                              extra={**(pz.get("extra") or {}), "activado_en": db.ahora()})
            else:
                experimentos.actualizar_pieza(cliente, pz["id"], estado=local)

    _con_credenciales(cliente, _correr)
    if pais is None:
        if status == "ACTIVE":
            _a_corriendo(cliente, experimento_id)
        else:
            experimentos.actualizar(cliente, experimento_id, estado="pausado")
    elif status == "ACTIVE" and ex["estado"] != "corriendo":
        _a_corriendo(cliente, experimento_id)
    elif status == "PAUSED":
        # M5: si ese país era el último activo, "corriendo" ya no refleja la
        # realidad (todos los conjuntos quedaron PAUSED en Meta) — el rótulo
        # importa porque exp_refrescar_todos sigue puliendo lo que está
        # "corriendo".
        otros_activos = any(p["estado"] == "activo" for p in ex["paises"] if p["pais"] != pais)
        if not otros_activos:
            experimentos.actualizar(cliente, experimento_id, estado="pausado")
    experimentos.registrar_evento(cliente, experimento_id, "estado",
                                  f"{'Activado' if status == 'ACTIVE' else 'Pausado'}{' ' + pais if pais else ' todo el experimento'}")


def cambiar_presupuesto_pais(cliente, experimento_id, pais, presupuesto_dia):
    if float(presupuesto_dia or 0) <= 0:
        raise ValueError("El presupuesto diario debe ser mayor que cero.")
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    if ex["estado"] == "cerrado":
        raise ValueError("Ese experimento está cerrado.")
    if ex["estado"] in ("armando", "lanzando", "error"):
        # M1: mientras lanza, lanzador.lanzar hace un read-modify-write sobre
        # experimento.paises sin ningún lock — si esta ruta escribiera encima
        # a mitad de ese lanzamiento podría perder el meta_adset_id que el
        # worker acaba de guardar, y el reintento crearía un segundo adset.
        raise ValueError("Ese experimento todavía no está en Meta.")
    p = next((p for p in ex.get("paises", []) if p["pais"] == pais), None)
    if not p or not p.get("meta_adset_id"):
        raise ValueError("Ese país no tiene conjunto en Meta.")
    moneda = ex["moneda"] or "USD"
    _con_credenciales(cliente, lambda _c: meta_adset.actualizar_presupuesto(p["meta_adset_id"], centavos(presupuesto_dia, moneda)))
    experimentos.actualizar_pais(cliente, experimento_id, pais, presupuesto_dia=float(presupuesto_dia))
    for pz in _piezas_de(ex, pais):
        experimentos.actualizar_pieza(cliente, pz["id"], presupuesto_dia_actual=float(presupuesto_dia))
    experimentos.registrar_evento(cliente, experimento_id, "presupuesto", f"Presupuesto diario de {pais}: {presupuesto_dia} {moneda}",
                                  {"anterior": p["presupuesto_dia"], "nuevo": float(presupuesto_dia)})


def lanzar_piezas_nuevas(cliente, experimento_id):
    """Bloque 4: crea el anuncio de cada pieza que se agregó después de
    lanzar() — solo las 'en_cola' cuyo país ya tiene conjunto en Meta; no
    toca campaña ni conjuntos (reusa el mismo bloque de lanzar() vía
    _crear_anuncios). Una pieza que falla queda en 'error' con su mensaje;
    las demás siguen, y si alguna falló se relanza la excepción al final —
    el estado del experimento no lo cambia esta función."""
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    if ex["estado"] not in ("pausado", "corriendo") or not ex["meta_campaign_id"]:
        raise ValueError("Ese experimento todavía no está en Meta.")
    adsets = {p["pais"]: p["meta_adset_id"] for p in ex["paises"] if p.get("meta_adset_id")}
    piezas_nuevas = [p for p in ex["piezas"] if p["estado"] == "en_cola" and p["pais"] in adsets]
    if not piezas_nuevas:
        return 0

    def _correr(creds):
        creadas = 0
        fallidas = []
        # Cache de creative/video compartido entre TODAS las piezas nuevas de
        # esta corrida (no uno nuevo por llamada a _crear_anuncios): así la
        # segunda pieza nueva con el mismo pieza_id reutiliza lo que subió la
        # primera en vez de repetir subir_video/crear_creative_video. Sembrado
        # desde ex["piezas"] completo (no solo piezas_nuevas), para cubrir
        # también el caso de una pieza nueva cuyo pieza_id ya tiene creative
        # en una pieza vieja de otra corrida/lanzar().
        cache = {}
        for pz_ in ex["piezas"]:
            if pz_.get("meta_creative_id"):
                cache.setdefault(pz_["pieza_id"], {
                    "video_id": (pz_.get("extra") or {}).get("meta_video_id"),
                    "creative_id": pz_["meta_creative_id"]})
        for pz in piezas_nuevas:
            try:
                creadas += _crear_anuncios(cliente, {**ex, "piezas": [pz]}, creds, adsets, cache=cache)
            except Exception as e:
                mensaje = cola.sin_token(str(e))
                experimentos.actualizar_pieza(cliente, pz["id"], estado="error", error=mensaje)
                experimentos.registrar_evento(cliente, experimento_id, "error",
                                              f"No se pudo crear el anuncio de {pz['nombre']} ({pz['pais']}): {mensaje}", ep_id=pz["id"])
                fallidas.append(pz["nombre"])
        if fallidas:
            raise RuntimeError(f"Fallaron {len(fallidas)} pieza(s) al crear su anuncio: {', '.join(fallidas)}")
        return creadas

    return _con_credenciales(cliente, _correr)


def _experimento_de_pieza(cliente, ep_id):
    experimento_id = experimentos.experimento_de_pieza(cliente, ep_id)
    if experimento_id is None:
        raise ValueError("Esa pieza no existe.")
    ex = experimentos.obtener(cliente, experimento_id)
    pz = next((p for p in (ex["piezas"] if ex else []) if p["id"] == ep_id), None)
    if pz is None:
        raise ValueError("Esa pieza no existe.")
    return ex, pz


def pausar_pieza(cliente, ep_id):
    ex, pz = _experimento_de_pieza(cliente, ep_id)
    if not pz["meta_ad_id"]:
        raise ValueError("Esa pieza todavía no tiene anuncio en Meta.")
    _con_credenciales(cliente, lambda _c: meta_ad.actualizar_estado(pz["meta_ad_id"], "PAUSED"))
    experimentos.actualizar_pieza(cliente, ep_id, estado="pausado")
    experimentos.registrar_evento(cliente, ex["id"], "estado", f"Pausado: {pz['nombre']} ({pz['pais']})", ep_id=ep_id)


def activar_pieza(cliente, ep_id):
    """Activar una pieza exige el experimento en Meta (pausado o corriendo).
    Reactiva la campaña si el experimento entero seguía 'pausado' (nunca se
    activó nada), y reactiva el conjunto del país si el estado LOCAL de ese
    país no es 'activo' — no si el experimento entero sigue 'corriendo',
    porque cambiar_estado(pais=) permite pausar un país individual sin bajar
    el experimento completo a 'pausado' (queda 'corriendo' mientras otro país
    siga activo). Mirar solo ex['estado'] dejaría ese conjunto en PAUSED en
    Meta con el anuncio ACTIVE encima — sin entrega — igual que hace
    cambiar_estado con pais=, que reactiva el conjunto incondicionalmente
    dentro de esa rama."""
    ex, pz = _experimento_de_pieza(cliente, ep_id)
    if ex["estado"] not in ("pausado", "corriendo"):
        raise ValueError("Ese experimento todavía no está en Meta.")
    if not pz["meta_ad_id"]:
        raise ValueError("Esa pieza todavía no tiene anuncio en Meta.")
    pais = next((p for p in ex["paises"] if p["pais"] == pz["pais"]), None)
    campaña_pausada = ex["estado"] == "pausado"
    pais_pausado = bool(pais) and pais["estado"] != "activo"

    def _correr(_creds):
        if campaña_pausada:
            meta_campaign.actualizar_estado(ex["meta_campaign_id"], "ACTIVE")
        if pais_pausado and pais.get("meta_adset_id"):
            meta_adset.actualizar_estado(pais["meta_adset_id"], "ACTIVE")
        meta_ad.actualizar_estado(pz["meta_ad_id"], "ACTIVE")

    _con_credenciales(cliente, _correr)
    experimentos.actualizar_pieza(cliente, ep_id, estado="activo",
                                  extra={**(pz.get("extra") or {}), "activado_en": db.ahora()})
    if pais:
        experimentos.actualizar_pais(cliente, ex["id"], pz["pais"], estado="activo")
    if campaña_pausada:
        _a_corriendo(cliente, ex["id"])
    experimentos.registrar_evento(cliente, ex["id"], "estado", f"Activado: {pz['nombre']} ({pz['pais']})", ep_id=ep_id)


def escalar_pais(cliente, experimento_id, pais, pct, tope_dia=None):
    """Bloque 4 (decisor): sube el presupuesto diario de un país en pct%,
    limitado por tope_dia si se da. Si el resultado no supera el actual (pct
    <= 0, o el tope ya estaba alcanzado) no llama a Meta y devuelve el actual
    sin cambios."""
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    p = next((p for p in ex.get("paises", []) if p["pais"] == pais), None)
    if not p:
        raise ValueError("Ese país no existe en el experimento.")
    actual = float(p["presupuesto_dia"] or 0)
    nuevo = round(actual * (1 + float(pct) / 100), 2)
    if tope_dia is not None:
        nuevo = min(nuevo, float(tope_dia))
    if nuevo <= actual:
        return actual
    cambiar_presupuesto_pais(cliente, experimento_id, pais, nuevo)
    return nuevo


def refrescar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    piezas = _piezas_de(ex) if ex else []
    if not piezas:
        return 0

    rechazados = []

    def _correr(_creds):
        n = 0
        for pz in piezas:
            try:
                r = meta_insights.obtener_resultados(pz["meta_ad_id"], objetivo=ex["objetivo_meta"])
                snap = {dest: r.get(src) for src, dest in _SNAP_DESDE_INSIGHTS.items() if src in r}
                snap["fuente_ventas"] = "meta" if (r.get("compras") or 0) > 0 else "ninguna"
                for k in ("resultado_nombre", "resultado", "estado_meta_texto", "motivo_rechazo"):
                    snap[k] = r.get(k)
                experimentos.snapshot(pz["id"], snap)
                estado_meta = r.get("estado_meta")
                experimentos.actualizar_pieza(cliente, pz["id"], estado_meta=estado_meta)
                if estado_meta in ESTADOS_META_RECHAZO and pz.get("estado_meta") not in ESTADOS_META_RECHAZO:
                    rechazados.append((pz, estado_meta, r.get("motivo_rechazo")))
                n += 1
            except Exception as e:
                experimentos.registrar_evento(
                    cliente, experimento_id, "error",
                    f"No se pudo refrescar {pz['nombre']} ({pz['pais']}): {cola.sin_token(str(e))}", ep_id=pz["id"])
        return n

    n = _con_credenciales(cliente, _correr)
    gasto = sum(float((p["metricas"] or {}).get("gasto") or 0) for p in experimentos.piezas(cliente, experimento_id))
    experimentos.actualizar(cliente, experimento_id, gasto_acumulado=round(gasto, 2))
    for pz, estado_meta, motivo in rechazados:
        _avisar_rechazo_meta(cliente, ex, pz, estado_meta, motivo)
    return n


# Estados de Meta que significan "este anuncio no entrega hasta que alguien
# lo mire": rechazado por políticas o con problemas de revisión.
ESTADOS_META_RECHAZO = ("DISAPPROVED", "WITH_ISSUES")


def _avisar_rechazo_meta(cliente, ex, pz, estado_meta, motivo):
    """Evento `rechazo_meta` + aviso por correo la primera vez que un anuncio
    pasa a DISAPPROVED/WITH_ISSUES (no en cada refresco mientras siga así)."""
    detalle = cola.sin_token(str(motivo)) if motivo else "Meta no dio un motivo"
    texto = f"Meta rechazó el anuncio de {pz['nombre']} ({pz['pais']}): {estado_meta}. {detalle}"
    experimentos.registrar_evento(cliente, ex["id"], "rechazo_meta", texto,
                                  {"estado_meta": estado_meta, "motivo": detalle}, ep_id=pz["id"])
    notificaciones.avisar(cliente, "rechazo_meta", f"Meta rechazó un anuncio de «{ex['nombre']}»",
                          f"{texto}\n\nEl anuncio no entrega hasta que se corrija o se reemplace. "
                          f"Revísalo en el panel del experimento #{ex['id']}.")


def cerrar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex and ex["meta_campaign_id"] and ex["estado"] in ("corriendo", "pausado"):
        cambiar_estado(cliente, experimento_id, "PAUSED")
    experimentos.actualizar(cliente, experimento_id, estado="cerrado")
    experimentos.registrar_evento(cliente, experimento_id, "estado", "Experimento cerrado")
