"""Sonda del guardián: el respaldo ciego es el CIERRE y la primera venta cayó dentro de la ventana."""
import re
import pytest
from tests.test_rutas_experimentos import app  # noqa: F401
from tests.test_rutas_resultados import AJAX, _kpi_roas, _proyectos_en_tmp  # noqa: F401
from tests.test_tablero import _snap, _experimento, _pieza_en, sin_red, AHORA  # noqa: F401


SNAPS = [_snap("2026-08-20T08:00:00", gasto=50, compras=0, ingresos=0, fuente_ventas="ninguna"),   # antes de vender
         _snap("2026-09-05T08:00:00", gasto=100, compras=5, ingresos=500, fuente_ventas="triple_whale"),
         _snap("2026-09-06T08:00:00", gasto=150, compras=0, ingresos=0, fuente_ventas="ninguna")]  # TW no respondió


def test_pnd139_cierre_ciego_no_es_cero():
    import tablero
    d = tablero._deltas_pieza(SNAPS, "2026-09-01T00:00:00", "2026-09-07T00:00:00")
    print("\nPERIODO", {k: d[k] for k in ("gasto", "compras", "ingresos", "roas_comparable", "ventas_cambiaron")})
    dias = [tablero._deltas_pieza(SNAPS, f"2026-09-0{i}T00:00:00", f"2026-09-0{i+1}T00:00:00") for i in range(1, 7)]
    print("DIAS compras", [x["compras"] for x in dias])
    assert d["compras"] is None, "la ventana vendió 5 según TW y el período dice compras 0"
    assert d["ingresos"] is None and not d["roas_comparable"]
    assert d["ventas_cambiaron"] and d["gasto"] == 100
    assert dias[4]["compras"] == 5


def test_pnd139_cierre_ciego_en_el_centro():
    import resultados as r
    d = r._deltas({"atribucion": "triple_whale"}, SNAPS, "2026-09-01T00:00:00", "2026-09-07T00:00:00")
    v = r._con_ventas(d["gasto"], r.tablero.ventas_medidas([d]))
    print("\nCENTRO", v)
    assert v["roas"] is None, "ROAS 0,0x falso"
    assert all(v[k] is None for k in ("compras", "ingresos", "cpa"))
    assert v["ventas_cambiaron"]


def test_pnd139_cierre_ciego_mes_y_csv(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    e = _experimento(base_temporal, moneda="USD", atribucion="triple_whale")
    p = _pieza_en(base_temporal, e)
    for s in SNAPS:
        ex.snapshot(p, {k: s[k] for k in ("gasto", "compras", "ingresos", "fuente_ventas")}, tomado_en=s["tomado_en"])
    g = tablero.resumen_mes("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    fila = tablero.csv_mes("acme", ahora_iso=AHORA).lstrip("﻿").splitlines()[1].split(";")
    print("\nMES", g, "\nCSV", fila)
    assert g["roas"] is None
    assert g["compras"] is None and g["ingresos"] is None
    assert g["ventas_cambiaron"] and not g["roas_comparable"]
    assert fila[7:10] == ["", "", ""]
    meses = tablero.mes_a_mes("acme", ahora_iso=AHORA)
    septiembre = next(m for m in meses if m["mes"] == "2026-09")
    assert septiembre["por_moneda"]["USD"]["roas"] is None


def test_pnd139_cierre_ciego_total(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    e = _experimento(base_temporal, moneda="USD", atribucion="triple_whale")
    p = _pieza_en(base_temporal, e)
    for t, g, c, i, f in [("2026-07-01T08:00:00", 100, 5, 500, "triple_whale"), ("2026-08-01T08:00:00", 200, 9, 900, "triple_whale"),
                          ("2026-09-10T08:00:00", 250, 0, 0, "ninguna")]:   # TW se desconectó; Meta no ve compras
        ex.snapshot(p, dict(gasto=g, compras=c, ingresos=i, fuente_ventas=f), tomado_en=t)
    g = tablero.resumen_total("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    print("\nTOTAL", {k: g[k] for k in ("gasto", "compras", "ingresos", "roas", "ventas_cambiaron")})
    assert all(g[k] is None for k in ("compras", "ingresos", "roas"))
    assert g["ventas_cambiaron"] and not g["roas_comparable"]


@pytest.mark.parametrize("historia", [SNAPS, [
    _snap("2026-07-01T08:00:00", gasto=100, compras=5, ingresos=500, fuente_ventas="triple_whale"),
    _snap("2026-08-01T08:00:00", gasto=200, compras=9, ingresos=900, fuente_ventas="triple_whale"),
    _snap("2026-09-10T08:00:00", gasto=250, compras=0, ingresos=0, fuente_ventas="ninguna"),
]], ids=["primera_venta_dentro", "ventas_anteriores"])
def test_pnd139_cierre_ciego_pantalla_centro_total_y_mes(app, base_temporal, sin_red, monkeypatch, historia):
    import db
    import experimentos as ex
    import resultados as r
    monkeypatch.setattr(db, "ahora", lambda: AHORA)
    eid = _experimento(base_temporal, moneda="USD", atribucion="triple_whale", objetivo_meta="OUTCOME_SALES")
    ep = _pieza_en(base_temporal, eid)
    for s in historia:
        ex.snapshot(ep, {k: s[k] for k in ("gasto", "compras", "ingresos", "fuente_ventas")}, tomado_en=s["tomado_en"])
    carga = r.cargar("acme", r.Filtro(dias=30), AHORA)
    kpis = {k["clave"]: k for k in r.indicadores(carga)}
    for k in ("compras", "ingresos", "roas", "cpa"):
        assert kpis[k]["valor"] is None and kpis[k]["roas_no_comparable"]
    assert r.piezas(carga, {})[0]["compras"] is None
    assert r.paises(carga)[0]["roas"] is None
    assert r.experimentos_tarjetas(carga)[0]["valor"] is None
    respuesta = app["c"].get("/cliente/acme/experimentos/resultados?dias=30", headers=AJAX)
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "Las ventas cambiaron de fuente en este período" in _kpi_roas(html)
    historial = html[html.index('class="tb-tiles"'):]
    tiles = historial[:historial.index('class="tb-meses')]
    assert tiles.count("—") >= 3 and "0,0×" not in tiles
    meses = historial[historial.index('class="tb-meses'):]
    septiembre = next(f for f in re.findall(r'<tr[^>]*>(.*?)</tr>', meses, re.S) if "septiembre 2026" in f)
    assert septiembre.count("—") >= 3 and "0,0×" not in septiembre
