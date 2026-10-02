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
import logging

log = logging.getLogger("creatv.meta_detalle")

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
        return float(valor or 0)
    except (TypeError, ValueError):
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
    return None if not valor or valor == "UNKNOWN" else valor


def rankings_de(fila):
    return {"calidad": _ranking(fila.get("quality_ranking")),
            "interaccion": _ranking(fila.get("engagement_rate_ranking")),
            "conversion": _ranking(fila.get("conversion_rate_ranking"))}
