"""
Lanzador multi-país (spec §4): traduce un experimento a objetos de Meta —
1 campaña (spend_cap = tope total) → 1 conjunto por país (presupuesto diario
propio, targeting país + edad) → 1 anuncio por pieza — y guarda cada id apenas
Meta lo devuelve, así un reintento retoma donde quedó sin duplicar nada. Todo
nace PAUSED: activar es otro clic (cambiar_estado). Las credenciales se cargan
y limpian bajo el lock de tareas.meta (mismo motivo que allá).
"""
import cola
import experimentos
import meta_conexion
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights
from meta_ads.targeting import Targeting
from tareas.meta import MONEDAS_SIN_DECIMALES, _LOCK, _miniatura_para_ad

ETAPAS_LANZAR = ["Campaña", "Conjuntos por país", "Anuncios"]
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


def lanzar(cliente, experimento_id, on_etapa=None):
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
    moneda = ex["moneda"] or (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    etapa = on_etapa or (lambda n: None)
    experimentos.actualizar(cliente, experimento_id, estado="lanzando", error=None)

    def _correr(creds):
        etapa(ETAPAS_LANZAR[0])
        campaign_id = ex["meta_campaign_id"]
        if not campaign_id:
            cap = centavos(ex["tope_total"], moneda) if float(ex["tope_total"] or 0) >= _MIN_POR_MONEDA.get(moneda, SPEND_CAP_MINIMO_USD) else None
            campaign_id = meta_campaign.crear_campaign(ex["nombre"], ex["objetivo_meta"], spend_cap_centavos=cap)["id"]
            experimentos.actualizar(cliente, experimento_id, meta_campaign_id=campaign_id)
            experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", "Campaña creada en Meta (en pausa)",
                                          {"campaign_id": campaign_id, "spend_cap": cap})
        etapa(ETAPAS_LANZAR[1])
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
        etapa(ETAPAS_LANZAR[2])
        for pz in ex["piezas"]:
            if pz["meta_ad_id"]:
                continue
            experimentos.actualizar_pieza(cliente, pz["id"], estado="publicando", meta_adset_id=adsets[pz["pais"]])
            creative_id = pz["meta_creative_id"]
            if not creative_id:
                video_id = (pz.get("extra") or {}).get("meta_video_id")
                if not video_id:
                    video_id = meta_creative.subir_video(pz["url_video"], titulo=pz["nombre"])
                    experimentos.actualizar_pieza(cliente, pz["id"],
                                                  extra={**(pz.get("extra") or {}), "meta_video_id": video_id})
                mini = pz["url_miniatura"] or _miniatura_para_ad(cliente, f"exp{experimento_id}_{pz['id']}", pz["url_video"])
                creative_id = meta_creative.crear_creative_video(
                    f"{pz['nombre']} — {pz['pais']}", video_id, mini, ex["nombre"],
                    url_destino(ex["destino_url"], pz["pieza_id"]), instagram_user_id=creds.get("ig_user_id"))["id"]
                experimentos.actualizar_pieza(cliente, pz["id"], meta_creative_id=creative_id)
            ad_id = meta_ad.crear_ad(f"{pz['nombre']} — {pz['pais']}", adsets[pz["pais"]], creative_id)["id"]
            experimentos.actualizar_pieza(cliente, pz["id"], meta_ad_id=ad_id, estado="pausado",
                                          presupuesto_dia_actual=next(p["presupuesto_dia"] for p in ex["paises"] if p["pais"] == pz["pais"]))
            experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", f"Anuncio creado: {pz['nombre']} ({pz['pais']})",
                                          {"ad_id": ad_id}, ep_id=pz["id"])

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
        raise
    experimentos.actualizar(cliente, experimento_id, estado="pausado", error=None)
    return "Experimento en Meta, en pausa. Actívalo cuando quieras empezar a gastar."


def _piezas_de(ex, pais=None):
    return [p for p in ex["piezas"] if p["meta_ad_id"] and (pais is None or p["pais"] == pais)]


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
            experimentos.actualizar_pieza(cliente, pz["id"], estado=local)

    _con_credenciales(cliente, _correr)
    if pais is None:
        experimentos.actualizar(cliente, experimento_id, estado="corriendo" if status == "ACTIVE" else "pausado")
    elif status == "ACTIVE" and ex["estado"] != "corriendo":
        experimentos.actualizar(cliente, experimento_id, estado="corriendo")
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


def refrescar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    piezas = _piezas_de(ex) if ex else []
    if not piezas:
        return 0

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
                experimentos.actualizar_pieza(cliente, pz["id"], estado_meta=r.get("estado_meta"))
                n += 1
            except Exception as e:
                experimentos.registrar_evento(
                    cliente, experimento_id, "error",
                    f"No se pudo refrescar {pz['nombre']} ({pz['pais']}): {cola.sin_token(str(e))}", ep_id=pz["id"])
        return n

    n = _con_credenciales(cliente, _correr)
    gasto = sum(float((p["metricas"] or {}).get("gasto") or 0) for p in experimentos.piezas(cliente, experimento_id))
    experimentos.actualizar(cliente, experimento_id, gasto_acumulado=round(gasto, 2))
    return n


def cerrar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex and ex["meta_campaign_id"] and ex["estado"] in ("corriendo", "pausado"):
        cambiar_estado(cliente, experimento_id, "PAUSED")
    experimentos.actualizar(cliente, experimento_id, estado="cerrado")
    experimentos.registrar_evento(cliente, experimento_id, "estado", "Experimento cerrado")
