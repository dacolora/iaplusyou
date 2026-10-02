"""meta_detalle (spec 2026-10-02 §3): traducir filas de Meta, pedir con
paginación, guardar sin cruzar proyectos y refrescar sin tumbar nada."""
import pytest

FILA_DIA = {
    "ad_id": "ad_1", "date_start": "2026-09-30", "date_stop": "2026-09-30",
    "impressions": "1000", "reach": "800", "frequency": "1.25", "clicks": "40", "inline_link_clicks": "25",
    "spend": "12.5", "cpm": "12.5",
    "actions": [{"action_type": "video_view", "value": "300"}, {"action_type": "landing_page_view", "value": "18"},
                {"action_type": "omni_add_to_cart", "value": "4"}, {"action_type": "add_to_cart", "value": "4"},
                {"action_type": "omni_initiated_checkout", "value": "2"}, {"action_type": "purchase", "value": "1"}],
    "action_values": [{"action_type": "purchase", "value": "59.9"}],
    "video_play_actions": [{"action_type": "video_view", "value": "900"}],
    "video_p25_watched_actions": [{"action_type": "video_view", "value": "220"}],
    "video_p50_watched_actions": [{"action_type": "video_view", "value": "150"}],
    "video_p75_watched_actions": [{"action_type": "video_view", "value": "90"}],
    "video_p95_watched_actions": [{"action_type": "video_view", "value": "60"}],
    "video_p100_watched_actions": [{"action_type": "video_view", "value": "50"}],
    "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "70"}],
    "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4.2"}],
}


def test_fila_diaria_traduce_campos_y_acciones():
    import meta_detalle as md
    f = md.fila_diaria(FILA_DIA)
    assert f["fecha"] == "2026-09-30"
    assert (f["impresiones"], f["alcance"], f["clics"], f["clics_enlace"]) == (1000, 800, 40, 25)
    assert f["frecuencia"] == 1.25 and f["gasto"] == 12.5 and f["cpm"] == 12.5
    assert f["vistas_3s"] == 300 and f["reproducciones"] == 900
    assert (f["p25"], f["p50"], f["p75"], f["p95"], f["p100"]) == (220, 150, 90, 60, 50)
    assert f["thruplay"] == 70 and f["tiempo_medio_s"] == 4.2
    # carrito: omni_ primero y sin sumar el duplicado add_to_cart
    assert f["visitas_pagina"] == 18 and f["carrito"] == 4 and f["pago_iniciado"] == 2
    assert f["compras_meta"] == 1 and f["ingresos_meta"] == 59.9


def test_fila_diaria_sin_video_ni_acciones_da_ceros():
    import meta_detalle as md
    f = md.fila_diaria({"date_start": "2026-10-01", "impressions": "10", "spend": "1"})
    assert f["impresiones"] == 10 and f["gasto"] == 1.0
    assert f["vistas_3s"] == f["p25"] == f["carrito"] == f["compras_meta"] == 0 and f["ingresos_meta"] == 0.0


@pytest.mark.parametrize("dimension, extra, clave", [
    ("ubicacion", {"publisher_platform": "instagram", "platform_position": "instagram_reels"}, "instagram|instagram_reels"),
    ("edad_genero", {"age": "25-34", "gender": "female"}, "25-34|female"),
    ("dispositivo", {"device_platform": "mobile_app"}, "mobile_app"),
    ("region", {"region": "Antioquia"}, "Antioquia"),
])
def test_fila_desglose_arma_la_clave(dimension, extra, clave):
    import meta_detalle as md
    fila = {**FILA_DIA, **extra}
    k, v = md.fila_desglose(fila, dimension)
    assert k == clave
    assert v == {"impresiones": 1000, "clics_enlace": 25, "gasto": 12.5, "vistas_3s": 300, "thruplay": 70,
                 "compras_meta": 1, "ingresos_meta": 59.9}


def test_rankings_de():
    import meta_detalle as md
    r = md.rankings_de({"quality_ranking": "ABOVE_AVERAGE", "engagement_rate_ranking": "AVERAGE",
                        "conversion_rate_ranking": "UNKNOWN"})
    assert r == {"calidad": "ABOVE_AVERAGE", "interaccion": "AVERAGE", "conversion": None}
