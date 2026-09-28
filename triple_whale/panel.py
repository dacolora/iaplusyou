"""Lo que pinta la pestaña Triple Whale (spec 2026-09-28 §8). Lee la copia
local (nunca llama a Triple Whale ni a Claude) y arma la evaluación gratis:
resumen de la tienda, anuncios con veredicto y diagnóstico, alertas, serie
diaria y el estado de las evaluaciones con IA. La pestaña lo pide por fetch
al abrirse, así la página del proyecto no paga este cálculo al cargar.
"""
from datetime import date, timedelta

import decisor
import gastos
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, evaluacion

PERIODOS = (7, 14, 30, 90)
PERIODO_DEFECTO = 30
MAX_FILAS = 200


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


def evaluar_periodo(cliente, dias=PERIODO_DEFECTO, canal=None, hoy=None):
    """(evaluación, desde, hasta) — lo mismo que ve la pestaña; también lo usa
    la ruta que encola el análisis con IA, para que Claude vea exactamente eso."""
    hoy = hoy or date.today()
    desde, hasta, _, _ = periodo(dias, hoy)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    ev = evaluacion.evaluar(
        datos.totales_por_anuncio(cliente, desde, hasta, canal),
        datos.totales_por_anuncio(cliente, _iso(hoy - timedelta(days=6)), _iso(hoy), canal),
        datos.totales_por_anuncio(cliente, _iso(hoy - timedelta(days=13)), _iso(hoy - timedelta(days=7)), canal),
        reglas)
    return ev, desde, hasta


def contexto(cliente, dias=PERIODO_DEFECTO, canal=None, hoy=None):
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return {"conectado": False}
    hoy = hoy or date.today()
    dias = dias if dias in PERIODOS else PERIODO_DEFECTO
    desde, hasta, desde_prev, hasta_prev = periodo(dias, hoy)
    canales = datos.canales(cliente, desde, hasta)
    canal = canal if canal in canales else None
    ev, _, _ = evaluar_periodo(cliente, dias, canal, hoy)

    serie_tienda = datos.serie_tienda(cliente, desde, hasta)
    tienda = evaluacion.resumen_tienda(serie_tienda, datos.serie_tienda(cliente, desde_prev, hasta_prev))
    if serie_tienda and not canal:
        serie = {"fuente": "tienda", "dias": _serie_dias(desde, hasta, serie_tienda)}
    else:
        serie = {"fuente": "anuncios", "dias": _serie_dias(desde, hasta, datos.serie_anuncios(cliente, desde, hasta))}
    serie["moneda"] = config["moneda"]
    rastreo = evaluacion.rastreo(ev["anuncios"], triple_whale.CANAL_META)

    creatv = datos.piezas_creatv(cliente, [a["ad_id"] for a in ev["anuncios"] if a["canal"] == triple_whale.CANAL_META])
    for a in ev["anuncios"]:
        a["creatv"] = creatv.get(a["ad_id"]) if a["canal"] == triple_whale.CANAL_META else None

    muestra = analisis.muestra(ev)
    evaluaciones = datos.evaluaciones(cliente, limite=5)
    return {
        "conectado": True, "config": config, "moneda": config["moneda"], "dias": dias, "periodos": PERIODOS,
        "desde": desde, "hasta": hasta, "canal": canal, "canales": canales,
        "rango": datos.rango(cliente), "ev": ev, "anuncios": ev["anuncios"][:MAX_FILAS],
        "mas_anuncios": max(0, len(ev["anuncios"]) - MAX_FILAS),
        "tienda": tienda, "serie": serie, "rastreo": rastreo,
        "alertas": evaluacion.alertas(ev, tienda, rastreo),
        "muestra_ia": muestra, "estimado_ia": gastos.estimar("evaluacion_tw", n=len(muestra)) if muestra else None,
        "evaluaciones": evaluaciones,
        "ultima_lista": next((e for e in evaluaciones if e["estado"] == "lista"), None),
        "job_sync": tareas_tw.job_id_sync(cliente) if trabajos.en_curso(tareas_tw.job_id_sync(cliente)) else None,
        "job_evaluar": (tareas_tw.job_id_evaluar(cliente)
                        if trabajos.en_curso(tareas_tw.job_id_evaluar(cliente)) else None),
        "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO, "problemas": evaluacion.PROBLEMAS,
        "fortalezas": evaluacion.FORTALEZAS, "veredictos": evaluacion.VEREDICTOS,
    }
