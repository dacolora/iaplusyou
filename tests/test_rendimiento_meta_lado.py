"""Lado Meta de la pestaña Rendimiento (spec 2026-10-09 §4): lecturas por partes sobre una lista de cuentas."""
from datetime import date

import idiomas
from meta_rendimiento import datos, panel
from tests.test_rutas_meta_rendimiento import _ad, _cuentas, _dia, _hace

A, B, C = "act_1", "act_2", "act_3"


def _tres():
    _cuentas("acme", (A, "HappyFlops Norway", "NO"), (B, "HappyFlops Sweden", "SE"), (C, "HappyFlops World Wide", None))
    datos.reemplazar_cuenta_dias("acme", A, _hace(40), _hace(40), [_dia(_hace(40), 100, 200)])
    datos.reemplazar_cuenta_dias("acme", B, _hace(5), _hace(5), [_dia(_hace(5), 50, 80)])
    f = _hace(2)
    datos.reemplazar_anuncio_dias("acme", A, f, f, [_ad(f, "a1", 100, 300, compras=3)])
    datos.reemplazar_anuncio_dias("acme", B, f, f, [_ad(f, "b1", 60, 0, adset="s2", campaign="c2")])


def test_primeras_fechas_una_por_cuenta(base_temporal):
    _tres()
    assert datos.primeras_fechas("acme", [A, B, C]) == {A: _hace(40), B: _hace(5)}
    assert datos.primeras_fechas("acme", []) == {}


def test_desde_el_inicio_arranca_en_el_primer_dia_de_esas_cuentas(base_temporal):
    _tres()
    hoy = date.today()
    assert panel.rango_fechas("acme", [B], 0, hoy)[0] == _hace(5)
    assert panel.rango_fechas("acme", [A, B], 0, hoy)[0] == _hace(40)
    assert panel.rango_fechas("acme", [A], 7, hoy)[0] == _hace(6)


def test_anuncios_y_estructura_solo_de_las_cuentas_pedidas(base_temporal):
    _tres()
    hoy = date.today()
    por_id = {c["ad_account_id"]: c for c in panel.lista("acme")}
    desde, hasta, _, _ = panel.rango_fechas("acme", [B], 0, hoy)
    with idiomas.en_idioma("es"):
        an = panel.anuncios_evaluados("acme", [B], desde, hasta, hoy, por_id)
        es = panel.estructura("acme", [B], desde, hasta, 0, por_id)
    assert [a["ad_id"] for a in an["anuncios"]] == ["b1"] and an["n_anuncios"] == 1
    assert an["ev"]["hay_ventas"] is False and an["ev"]["cuenta"]["m"]["gasto"] == 60
    assert {c["campaign_id"] for c in es["campanas"]} <= {"c2"}


def test_estado_copia_dice_los_errores(base_temporal):
    from meta_rendimiento import cuentas
    _tres()
    cuentas.actualizar("acme", B, estado="error", error="Meta pidió esperar")
    estado = panel.estado_copia("acme", [c for c in panel.lista("acme") if c["ad_account_id"] in (A, B)])
    assert [c["ad_account_id"] for c in estado["errores"]] == [B]


def test_estructura_y_anuncios_siguen_a_la_lista_de_cuentas(base_temporal):
    """Con otra lista de cuentas cambian las campañas y los anuncios; «desde el inicio» usa la ventana de 90 días."""
    _tres()
    hoy = date.today()
    por_id = {c["ad_account_id"]: c for c in panel.lista("acme")}
    desde, hasta, _, _ = panel.rango_fechas("acme", [A, B], 0, hoy)
    with idiomas.en_idioma("es"):
        solo_a = panel.estructura("acme", [A], desde, hasta, 0, por_id)
        las_dos = panel.estructura("acme", [A, B], desde, hasta, 0, por_id)
        anuncios = panel.anuncios_evaluados("acme", [A, B], desde, hasta, hoy, por_id)
    assert {c["campaign_id"] for c in solo_a["campanas"]} == {"c1"}
    assert {c["campaign_id"] for c in las_dos["campanas"]} == {"c1", "c2"}
    assert las_dos["ventana_alcance"] == 90 and las_dos["pagina_conjuntos"] == 0
    assert {a["ad_id"] for a in anuncios["anuncios"]} == {"a1", "b1"}
    assert anuncios["ev"]["hay_ventas"] is True and len(anuncios["ev"]["anuncios"]) == 2


def test_periodos_raros_caen_en_desde_el_inicio_y_sin_cuentas_no_hay_nada(base_temporal):
    _tres()
    hoy = date.today()
    assert panel.rango_fechas("acme", [A], 5, hoy)[0] == _hace(40)
    assert panel.rango_fechas("acme", [], 0, hoy)[0] == hoy.isoformat()
    vacio = panel.estado_copia("acme", [])
    assert vacio["sync_ocupado"] is False and vacio["errores"] == [] and vacio["rango"]["filas"] == 0
