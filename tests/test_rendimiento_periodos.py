"""Periodos de Rendimiento (Daniel, 2026-10-15): «Desde el inicio» (defecto), 7 días, 15 días, 1 mes, 3 meses, 6 meses y
1 año, iguales para Triple Whale, Meta, «Por país» y las métricas que faltaban. La evaluación pagada de Meta mira lo que
hay: sus anuncios se guardan 90 días."""
from datetime import date

import pytest

from meta_rendimiento import panel as meta_panel
from pestana_rendimiento import panel as rpanel
from pestana_rendimiento import resumen
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from triple_whale import panel as tw_panel

NUEVOS = (0, 7, 15, 30, 90, 180, 365)


def test_un_solo_juego_de_periodos_en_todas_las_partes():
    assert tw_panel.PERIODOS == rpanel.PERIODOS == meta_panel.PERIODOS_RENDIMIENTO == resumen.PERIODOS == NUEVOS


@pytest.mark.parametrize("dias, esperado", [(15, 15), (180, 180), (365, 365), (14, 0), (60, 0), ("x", 0), (None, 0),
                                            (True, 0)])
def test_un_periodo_que_no_es_del_selector_abre_desde_el_inicio(dias, esperado):
    assert rpanel.periodo_valido(dias) == esperado


@pytest.mark.parametrize("dias, esperado", [(7, 7), (14, 30), (15, 15), (30, 30), (90, 90), (180, 90), (365, 90),
                                            (0, 30), (None, 30), ("x", 30), (60, 30)])
def test_la_evaluacion_pagada_de_meta_mira_a_lo_sumo_90_dias(dias, esperado):
    """Sus anuncios se guardan 90 días: con 6 meses o 1 año evalúa 90 (lo que hay), «Desde el inicio» sigue en 30."""
    assert meta_panel._dias_periodo(dias) == esperado


def test_un_ano_va_desde_hace_364_dias():
    hoy = date(2026, 10, 15)
    desde, hasta, desde_prev, hasta_prev = tw_panel.periodo(365, hoy)
    assert (desde, hasta) == ("2025-10-16", "2026-10-15")
    assert (desde_prev, hasta_prev) == ("2024-10-16", "2025-10-15")


def test_el_selector_dice_cada_periodo_en_palabras(app):  # noqa: F811
    from tests.test_rendimiento_destacados import _sembrar_anuncios, _tienda
    import os
    os.environ.setdefault("FLASK_SECRET_KEY", "test_secret_key_12345678")
    _sembrar_anuncios(_tienda())
    html = app["c"].get("/cliente/acme/rendimiento/panel?entrada=NO&dias=180").data.decode()
    selector = html[html.index('data-rend-param="dias"'):]
    selector = selector[:selector.index("</select>")]
    for texto in ("Desde el inicio", "Últimos 7 días", "Últimos 15 días", "Último mes", "Últimos 3 meses",
                  "Últimos 6 meses", "Último año"):
        assert texto in selector, texto
    assert '<option value="180" selected>' in selector
    assert "Últimos 14 días" not in selector


def test_en_ingles_los_periodos_dicen_dias_y_meses_no_el_mes_calendario():
    """«Last month» se lee como el mes calendario anterior; el periodo son los últimos 30 días (revisión 2026-10-15)."""
    import idiomas
    from flask_babel import gettext
    with idiomas.en_idioma("en"):
        assert gettext("Último mes") == "Last 30 days"
        assert gettext("Último año") == "Last 12 months"
