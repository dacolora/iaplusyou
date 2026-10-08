"""Lo que pinta la pestaña Triple Whale (spec 2026-09-28 §8). Lee la copia
local (nunca llama a Triple Whale ni a Claude) y arma la evaluación gratis:
resumen de la tienda, anuncios con veredicto y diagnóstico, alertas, serie
diaria y el estado de las evaluaciones con IA. La pestaña lo pide por fetch
al abrirse, así la página del proyecto no paga este cálculo al cargar.

Varias tiendas (spec 2026-10-08 §6.2): todo se lee en un alcance, una tienda
o «Todas» (`tienda_id=None`). `tienda_elegida` resuelve lo que pide la
persona: una tienda que no es del proyecto (o un valor raro) es «Todas», y
con una sola tienda conectada el alcance es esa tienda.
"""
from datetime import date, timedelta

from flask_babel import gettext

import decisor
import gastos
import idiomas
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from idiomas import N_
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, evaluacion, paises

PERIODOS = (7, 14, 30, 90)
PERIODO_DEFECTO = 30
MAX_FILAS = 200
MAX_PRODUCTOS_PANEL = 8
# Estados de Crear tal como los dice la tarjeta de una idea (idea → pieza).
ETIQUETAS_PIEZA = {"prompt_pendiente": N_("armando el prompt"), "prompt_listo": N_("prompt listo, falta generar"),
                   "video_generando": N_("generando"), "video_listo": N_("lista"), "error": N_("con error")}


def _iso(d):
    return d.isoformat()


def periodo(dias, hoy):
    """(desde, hasta, desde_previo, hasta_previo) de un periodo que termina hoy."""
    dias = dias if dias in PERIODOS else PERIODO_DEFECTO
    desde = hoy - timedelta(days=dias - 1)
    hasta_prev = desde - timedelta(days=1)
    return _iso(desde), _iso(hoy), _iso(hasta_prev - timedelta(days=dias - 1)), _iso(hasta_prev)


def _serie_dias(desde, hasta, filas, clave_gasto="gasto", clave_ingresos="ingresos", clave_pedidos="pedidos"):
    """Un punto por día del rango (los días sin fila en cero), con la forma
    que espera el gráfico del Tablero."""
    por_dia = {f["fecha"]: f for f in filas}
    d, fin, salida = date.fromisoformat(desde), date.fromisoformat(hasta), []
    while d <= fin:
        f = por_dia.get(_iso(d)) or {}
        salida.append({"dia": _iso(d), "gasto": float(f.get(clave_gasto) or 0),
                       "ingresos": float(f.get(clave_ingresos) or 0), "compras": int(round(f.get(clave_pedidos) or 0))})
        d += timedelta(days=1)
    return salida


def tienda_elegida(tiendas, valor):
    """La tienda (dict) del alcance pedido, o None = «Todas». `tiendas` son las
    del proyecto (`triple_whale_tiendas.tiendas`): un id que no está ahí, o que
    no es un entero, es «Todas»; con una sola tienda siempre es esa."""
    if len(tiendas) == 1:
        return tiendas[0]
    try:
        tid = int(valor)
    except (TypeError, ValueError):
        return None
    return next((t for t in tiendas if t["id"] == tid), None)


def nombre_tienda(tienda, locale=None):
    """«Noruega» en el idioma de quien mira, o el dominio si la tienda no tiene país."""
    if tienda.get("pais"):
        return paises.nombre_pais(tienda["pais"], locale or idiomas.activo())
    return tienda.get("dominio") or ""


def _con_nombre(tienda, locale):
    return dict(tienda, nombre=nombre_tienda(tienda, locale), bandera=paises.bandera(tienda.get("pais")))


def evaluar_periodo(cliente, dias=PERIODO_DEFECTO, canal=None, tienda_id=None, hoy=None):
    """(evaluación, desde, hasta) — lo mismo que ve la pestaña; también lo usa
    la ruta que encola el análisis con IA, para que Claude vea exactamente eso.
    `tienda_id=None` evalúa «Todas las tiendas»."""
    hoy = hoy or date.today()
    desde, hasta, _, _ = periodo(dias, hoy)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    ev = evaluacion.evaluar(
        datos.totales_por_anuncio(cliente, tienda_id, desde, hasta, canal),
        datos.totales_por_anuncio(cliente, tienda_id, _iso(hoy - timedelta(days=6)), _iso(hoy), canal),
        datos.totales_por_anuncio(cliente, tienda_id, _iso(hoy - timedelta(days=13)), _iso(hoy - timedelta(days=7)), canal),
        reglas)
    return ev, desde, hasta


def _clave_producto(p, por_nombre):
    """Con «Todas» los productos se agrupan por nombre normalizado (cada tienda
    tiene sus propios ids), así que el periodo anterior se empareja igual."""
    if por_nombre:
        nombre = " ".join((p.get("nombre") or "").lower().split())
        if nombre:
            return nombre
    return str(p["producto_id"])


def productos_periodo(cliente, tienda_id, desde, hasta, desde_prev, hasta_prev, limite=MAX_PRODUCTOS_PANEL):
    """Los productos que más vendieron (tw_producto_dia) en ese alcance con su
    variación contra el periodo anterior y, si el nombre o el id coincide con
    un producto del Catálogo, ese producto (para llevar la idea a Crear con él)."""
    import tiendas
    top = datos.top_productos(cliente, tienda_id, desde, hasta, limite)
    if not top:
        return []
    por_nombre = tienda_id is None
    previos = {_clave_producto(p, por_nombre): p
               for p in datos.top_productos(cliente, tienda_id, desde_prev, hasta_prev, limite=500)}
    total = sum(float(p["ingresos"] or 0) for p in top) or 0.0
    catalogo = {}
    try:
        for prod in tiendas.productos(cliente):
            for clave in (str(prod.get("fuente_id") or ""), (prod.get("nombre") or "").strip().lower()):
                if clave:
                    catalogo.setdefault(clave, prod)
    except Exception:  # noqa: BLE001 — sin catálogo, la lista igual sirve
        catalogo = {}
    salida = []
    for p in top:
        prev = previos.get(_clave_producto(p, por_nombre)) or {}
        ingresos_prev = float(prev.get("ingresos") or 0)
        variacion = (float(p["ingresos"] or 0) / ingresos_prev - 1) if ingresos_prev else None
        en_catalogo = catalogo.get(str(p["producto_id"])) or catalogo.get((p.get("nombre") or "").strip().lower())
        salida.append(dict(p, variacion=variacion, pct_ingresos=(float(p["ingresos"] or 0) / total) if total else None,
                           catalogo=({"id": en_catalogo["id"], "nombre": en_catalogo["nombre"],
                                      "activo_id": en_catalogo.get("activo_catalogo_id")} if en_catalogo else None)))
    return salida


def resumen_mes_tienda(cliente, hoy=None):
    """La tienda según Triple Whale en el mes en curso (para el Tablero):
    ingresos, pedidos, gasto en publicidad, MER y % de clientes nuevos, más
    la variación contra los mismos días del mes anterior. None sin conexión o
    sin datos de tienda. Siempre «Todas las tiendas» (el gasto compartido
    entre tiendas cuenta una vez), en la moneda de los ajustes del proyecto."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return None
    hoy = hoy or date.today()
    desde = hoy.replace(day=1)
    dias = (hoy - desde).days + 1
    serie = datos.serie_tienda(cliente, None, _iso(desde), _iso(hoy))
    if not serie:
        return None
    fin_prev = desde - timedelta(days=1)
    ini_prev = fin_prev.replace(day=1)
    fin_prev_mismo = min(fin_prev, ini_prev + timedelta(days=dias - 1))
    r = evaluacion.resumen_tienda(serie, datos.serie_tienda(cliente, None, _iso(ini_prev), _iso(fin_prev_mismo)))
    r["moneda"] = config["moneda"]
    r["desde"], r["hasta"] = _iso(desde), _iso(hoy)
    return r


def enlazar_ideas(cliente, anuncios, evaluacion_lista):
    """Cierra el círculo idea → pieza → anuncio (spec §14), sin consultas por
    fila. En cada anuncio hecho en Creatv que nació de una idea deja
    `idea_origen` = {"evaluacion_id", "idea", "titulo"}; en la última
    evaluación lista deja `piezas_por_idea` ({índice: [piezas]}, cada pieza
    con `anuncio` = {"nombre", "veredicto"} si ya corre en Meta y aparece en
    el periodo)."""
    for a in anuncios:
        origen = (a.get("creatv") or {}).get("tw_idea")
        a["idea_origen"] = origen or None
    if not evaluacion_lista:
        return
    piezas = datos.piezas_de_evaluacion(cliente, evaluacion_lista["id"])
    por_pieza = {a["creatv"]["pieza_id"]: a for a in anuncios if a.get("creatv") and a["creatv"].get("pieza_id")}
    for lista in piezas.values():
        for p in lista:
            en_meta = por_pieza.get(p["pieza_id"])
            p["anuncio"] = {"nombre": en_meta["nombre"], "veredicto": en_meta["veredicto"]} if en_meta else None
    evaluacion_lista["piezas_por_idea"] = piezas


def _por_tienda(cliente, tiendas_por_id, desde, hasta, desde_prev, hasta_prev):
    """«Por tienda»: una fila por tienda con sus totales, su MER y la variación
    de sus ingresos contra el periodo anterior (una consulta)."""
    filas = []
    for f in datos.por_tienda(cliente, desde, hasta, desde_prev, hasta_prev):
        tienda = tiendas_por_id.get(f["tienda_id"])
        if not tienda:
            continue
        a, p = f["actual"], f["previo"]
        ingresos, ingresos_prev = float(a["ingresos"] or 0), float(p["ingresos"] or 0)
        gasto = float(a["gasto"] or 0)
        filas.append({"tienda": tienda, "actual": a, "previo": p,
                      "mer": ingresos / gasto if gasto else None,
                      "variacion_ingresos": (ingresos / ingresos_prev - 1) if ingresos_prev else None})
    return filas


def _alcance_evaluacion(ev, tiendas_por_id, locale):
    """Lo que la lista de evaluaciones dice de cada una: «Noruega», «Todas las
    tiendas» o "" (una evaluación de antes de las varias tiendas)."""
    extra = ev.get("extra") or {}
    if "tienda_id" not in extra:
        return ""
    if extra["tienda_id"] is None:
        return gettext("Todas las tiendas")
    tienda = tiendas_por_id.get(extra["tienda_id"])
    if tienda:
        return tienda["nombre"]
    return paises.nombre_pais(extra["pais"], locale) if extra.get("pais") else ""


def _jobs_sync(cliente, tiendas):
    """[{"job_id", "tienda"}] de las copias en cola o en curso (una consulta)."""
    vivos = set(tareas_tw.syncs_en_curso(cliente))
    salida = []
    for t in tiendas:
        job_id = tareas_tw.job_id_sync(cliente, t["id"])
        if job_id in vivos:
            salida.append({"job_id": job_id, "tienda": t})
    return salida


def contexto(cliente, dias=PERIODO_DEFECTO, canal=None, tienda_id=None, hoy=None):
    """Todo lo que pinta `_tw_panel.html` en el alcance pedido (`tienda_id`:
    una tienda del proyecto, o None = «Todas»; un id ajeno se ignora)."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return {"conectado": False}
    locale = idiomas.activo()
    tiendas = [_con_nombre(t, locale) for t in config["tiendas"]]
    tiendas_por_id = {t["id"]: t for t in tiendas}
    tienda_actual = tienda_elegida(tiendas, tienda_id)
    tienda_id = tienda_actual["id"] if tienda_actual else None
    varias = len(tiendas) > 1
    hoy = hoy or date.today()
    dias = dias if dias in PERIODOS else PERIODO_DEFECTO
    desde, hasta, desde_prev, hasta_prev = periodo(dias, hoy)
    canales = datos.canales(cliente, tienda_id, desde, hasta)
    canal = canal if canal in canales else None
    ev, _, _ = evaluar_periodo(cliente, dias, canal, tienda_id=tienda_id, hoy=hoy)

    serie_tienda = datos.serie_tienda(cliente, tienda_id, desde, hasta)
    tienda = evaluacion.resumen_tienda(serie_tienda, datos.serie_tienda(cliente, tienda_id, desde_prev, hasta_prev))
    if serie_tienda and not canal:
        serie = {"fuente": "tienda", "dias": _serie_dias(desde, hasta, serie_tienda)}
    else:
        serie = {"fuente": "anuncios",
                 "dias": _serie_dias(desde, hasta, datos.serie_anuncios(cliente, tienda_id, desde, hasta))}
    serie["moneda"] = config["moneda"]
    rastreo = evaluacion.rastreo(ev["anuncios"], triple_whale.CANAL_META)

    creatv = datos.piezas_creatv(cliente, [a["ad_id"] for a in ev["anuncios"] if a["canal"] == triple_whale.CANAL_META])
    for a in ev["anuncios"]:
        a["creatv"] = creatv.get(a["ad_id"]) if a["canal"] == triple_whale.CANAL_META else None

    muestra = analisis.muestra(ev)
    evaluaciones = datos.evaluaciones(cliente, limite=5)
    for e in evaluaciones:
        e["alcance"] = _alcance_evaluacion(e, tiendas_por_id, locale)
    ultima_lista = next((e for e in evaluaciones if e["estado"] == "lista"), None)
    enlazar_ideas(cliente, ev["anuncios"], ultima_lista)
    productos = productos_periodo(cliente, tienda_id, desde, hasta, desde_prev, hasta_prev) if not canal else []
    jobs_sync = _jobs_sync(cliente, tiendas)
    # Las tiendas del alcance: su estado, sus errores y su última copia.
    en_alcance = [tienda_actual] if tienda_actual else tiendas
    ocupadas = {j["tienda"]["id"] for j in jobs_sync}
    copias = [t["ultima_sincronizacion"] for t in en_alcance if t.get("ultima_sincronizacion")]
    return {
        "productos": productos, "etiquetas_pieza": ETIQUETAS_PIEZA,
        "conectado": True, "config": config, "moneda": config["moneda"], "dias": dias, "periodos": PERIODOS,
        "desde": desde, "hasta": hasta, "canal": canal, "canales": canales,
        "tiendas": tiendas, "tienda_actual": tienda_actual, "varias_tiendas": varias, "en_alcance": en_alcance,
        "ultima_copia": (min(copias) if len(copias) == len(en_alcance) else None) if copias else None,
        "por_tienda": (_por_tienda(cliente, tiendas_por_id, desde, hasta, desde_prev, hasta_prev)
                       if varias and tienda_actual is None else []),
        # La nota de cuenta compartida mira el alcance: una tienda con cuenta propia no la lleva.
        "gasto_duplicado": datos.gasto_duplicado(cliente, desde, hasta, tienda_id) if varias else 0.0,
        "jobs_sync": jobs_sync,
        "sync_ocupado": all(t["id"] in ocupadas for t in en_alcance),
        "rango": datos.rango(cliente, tienda_id), "ev": ev, "anuncios": ev["anuncios"][:MAX_FILAS],
        "mas_anuncios": max(0, len(ev["anuncios"]) - MAX_FILAS),
        "tienda": tienda, "serie": serie, "rastreo": rastreo,
        "alertas": evaluacion.alertas(ev, tienda, rastreo),
        "muestra_ia": muestra, "estimado_ia": gastos.estimar("evaluacion_tw", n=len(muestra)) if muestra else None,
        "evaluaciones": evaluaciones, "ultima_lista": ultima_lista,
        "job_evaluar": (tareas_tw.job_id_evaluar(cliente)
                        if trabajos.en_curso(tareas_tw.job_id_evaluar(cliente)) else None),
        "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO, "problemas": evaluacion.PROBLEMAS,
        "fortalezas": evaluacion.FORTALEZAS, "veredictos": evaluacion.VEREDICTOS,
    }
