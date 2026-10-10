"""Contexto de la pestaña Rendimiento (spec 2026-10-09 §4–§5)."""
from datetime import date

import pytest

import idiomas
from pestana_rendimiento import panel
from tests.test_rendimiento_resumen import _llave_de_cifrado, _sembrar  # noqa: F401  (fixture autouse: cifra la llave)


@pytest.fixture()
def meta_conectado(monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba


def test_todas_mezcla_trae_los_dos_bloques(base_temporal, meta_conectado):
    _sembrar()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=date.today())
    assert r["fuente"] == "mixta" and r["tw"] is not None and r["meta"]["ids_fuente"] == ["act_se", "act_ww"]
    assert r["tw"]["resultados"] is None and r["resumen"]["resultados"]["fuente"] == "mixta"
    assert [e["clave"] for e in r["entradas"]] == ["NO", "SE", "cuenta:act_ww"]
    assert r["entradas"][0]["nombre"] == "Noruega"


def test_una_entrada_tw_usa_los_resultados_de_triple_whale(base_temporal, meta_conectado):
    _sembrar()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, entrada="NO", hoy=date.today())
    assert r["fuente"] == "tw" and r["tw"]["resultados"] is not None and r["resumen"]["resultados"] is None
    assert r["meta"]["ids_fuente"] == [] and r["meta"]["ids_estructura"] == ["act_no"]


def test_legado_tienda_y_cuenta(base_temporal, meta_conectado):
    tid = _sembrar()
    with idiomas.en_idioma("es"):
        assert panel.contexto("acme", 0, tienda=str(tid))["actual"]["clave"] == "NO"
        assert panel.contexto("acme", 0, cuenta="act_se")["actual"]["clave"] == "SE"


def test_sin_nada_conectado(base_temporal):
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0)
    assert r["conectado"] is False and r["tw"] is None and r["meta"] is None


# ---- más allá del brief: las ventas de Triple Whale en las campañas y los conjuntos (regla 6) -------------------

def _con_campanas_de_noruega():
    """`_sembrar` + 3 días de una campaña de la cuenta de Noruega que Triple Whale trae en su copia (cno/sno) y otra
    que no trae (cno2/sno2)."""
    from datetime import timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _ad
    from triple_whale import datos as twdatos
    tid = _sembrar()
    for n in range(3):
        f = (date.today() - timedelta(days=n)).isoformat()
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "gasto": 10, "cuenta_id": "act_no", "campana_id": "cno",
                                                               "conjunto_id": "sno"}])
        twdatos.reemplazar_anuncios_pixel("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "pedidos": 2, "ingresos": 80}])
        mdatos.reemplazar_anuncio_dias("acme", "act_no", f, f, [
            _ad(f, "n1", 10, 20, compras=1, adset="sno", campaign="cno"),
            _ad(f, "n2", 5, 15, compras=1, adset="sno2", campaign="cno2")])
    return tid


def test_las_campanas_de_una_cuenta_con_tienda_llevan_las_ventas_de_triple_whale(base_temporal, meta_conectado):
    _con_campanas_de_noruega()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 7, entrada="NO", hoy=date.today())
    campanas = {c["campaign_id"]: c for c in r["meta"]["estructura"]["campanas"]}
    # Triple Whale: 3 días × 2 pedidos y 80 de ventas; el gasto sigue siendo el de Meta (3 × 10).
    assert campanas["cno"]["origen"] == "tw" and campanas["cno"]["compras"] == 6 and campanas["cno"]["valor"] == 240
    assert campanas["cno"]["pedidos"] == 6 and campanas["cno"]["ingresos"] == 240
    assert round(campanas["cno"]["m"]["roas"], 2) == 8.0
    # Una campaña que Triple Whale no tiene en su copia conserva lo de Meta, y dice de dónde sale.
    assert campanas["cno2"]["origen"] == "meta" and campanas["cno2"]["valor"] == 45
    conjuntos = {s["adset_id"]: s for s in r["meta"]["estructura"]["conjuntos"]}
    assert conjuntos["sno"]["origen"] == "tw" and conjuntos["sno"]["valor"] == 240
    assert conjuntos["sno2"]["origen"] == "meta"
    # La página siguiente de conjuntos («Ver más») hace la misma cuenta.
    with idiomas.en_idioma("es"):
        pagina = panel.conjuntos_pagina("acme", 7, "NO", 0, hoy=date.today())
    assert {s["adset_id"]: s["origen"] for s in pagina["conjuntos"]} == {"sno": "tw", "sno2": "meta"}


def test_una_entrada_de_meta_no_lleva_ventas_de_triple_whale(base_temporal, meta_conectado):
    from datetime import timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _ad
    _sembrar()
    f = (date.today() - timedelta(days=1)).isoformat()
    mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, "se1", 60, 90, compras=1, campaign="cse")])
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 7, entrada="SE", hoy=date.today())
    assert r["fuente"] == "meta" and r["tw"] is None
    assert [(c["campaign_id"], c["origen"], c["valor"]) for c in r["meta"]["estructura"]["campanas"]] == [
        ("cse", "meta", 90)]
    assert [a["ad_id"] for a in r["meta"]["anuncios"]["anuncios"]] == ["se1"]
    assert r["params"] == {"entrada": "SE", "dias": 7, "canal": ""} and r["canales"] == []


def test_periodo_fuera_de_la_lista_es_desde_el_inicio(base_temporal, meta_conectado):
    _sembrar()
    with idiomas.en_idioma("es"):
        assert panel.contexto("acme", 45)["dias"] == 0
        assert panel.contexto("acme", "7")["dias"] == 0
