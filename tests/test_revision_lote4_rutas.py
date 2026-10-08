import re
import pytest
from tests.test_rutas_resultados import _experimento, _pieza_en, _kpi_roas, AJAX, _proyectos_en_tmp  # noqa: F401
from tests.test_rutas_experimentos import app  # noqa: F401


def _txt(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def test_sonda_solo_trafico(app, base_temporal):
    eid = _experimento("Trafico")
    _pieza_en(base_temporal, eid)
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    assert "sin ventas medibles" in _kpi_roas(html)
    assert "de gasto sin ventas medibles" not in html


@pytest.mark.parametrize("atribucion", ["pixel", "triple_whale"])
def test_sonda_pixel_sin_gasto_historial(app, base_temporal, atribucion):
    import experimentos as ex
    from tests.test_experimentos_db import _pieza
    eid = ex.crear("acme", "Pixel nuevo", ex and __import__("tests.test_experimentos_db", fromlist=["PAISES"]).PAISES,
                   "OUTCOME_SALES", 7, 500000.0, "https://t.co/p", "COP", atribucion=atribucion)
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_9")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.snapshot(ep, {"impresiones": 1, "gasto": 0.0})
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    hist = html[html.index('class="tb-tiles"'):]
    tiles = hist[:hist.index('class="tb-meses')]
    assert '0,0×' not in tiles
    assert '<strong class="tb-sin-dato">—</strong>' in tiles
    assert '0,0×' not in hist
    assert '—' in _kpi_roas(html)


def test_pnd138_gestionar_moneda_ajena(app, base_temporal):
    import experimentos as ex
    eid = _experimento("Tienda", atribucion="tienda", objetivo_meta="OUTCOME_SALES", extra={"aviso_moneda": "USD"})
    _, ep = _pieza_en(base_temporal, eid)
    ex.snapshot(ep, {"gasto": 100, "compras": 2, "ingresos": 300, "roas": 0, "fuente_ventas": "tienda"})
    html = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={eid}", headers=AJAX).get_data(as_text=True)
    gestion = html[html.index('class="kpis kpis-mini"'):]
    bloque = gestion[:gestion.index('</span>\n          </span>') + 7] if '</span>\n          </span>' in gestion else gestion[:700]
    assert '<b>2</b>' in bloque and 'ROAS no comparable' in bloque
    assert 'ROAS 0.0' not in bloque and 'ROAS 0,0' not in bloque


def test_pnd138_historial_meses_previos_comparables(app, base_temporal, monkeypatch):
    import db
    import experimentos as ex
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-16T12:00:00")
    sano = _experimento("Sano", atribucion="pixel", objetivo_meta="OUTCOME_SALES")
    from tests.test_experimentos_db import _pieza
    ep = ex.agregar_pieza("acme", sano, _pieza(base_temporal, legado="cf_sano"), "CO")
    for t, g, c, i in [("2026-07-10T08:00:00", 100, 1, 300), ("2026-08-15T08:00:00", 200, 2, 600),
                        ("2026-09-10T08:00:00", 300, 3, 900)]:
        ex.snapshot(ep, dict(gasto=g, compras=c, ingresos=i, fuente_ventas="meta"), tomado_en=t)
    ajeno = _experimento("Ajeno", atribucion="tienda", estado="cerrado", extra={"aviso_moneda": "USD"})
    ep2 = ex.agregar_pieza("acme", ajeno, _pieza(base_temporal, legado="cf_ajeno"), "CO")
    # Sin snapshots: no hay actividad; ni siquiera el Total pierde su ROAS.
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    hist = html[html.index('class="tb-tiles"'):]
    tiles = hist[:hist.index('class="tb-meses')]
    assert '<strong>3,0×</strong>' in tiles and 'ROAS no comparable' not in tiles
    ex.snapshot(ep2, dict(gasto=10, compras=1, ingresos=40000, fuente_ventas="tienda"), tomado_en="2026-09-12T08:00:00")
    html = app["c"].get("/cliente/acme/experimentos/resultados", headers=AJAX).get_data(as_text=True)
    meses = html[html.index('class="tb-meses'):]
    meses = meses[:meses.index('</table>')]
    filas = re.findall(r'<tr[^>]*>(.*?)</tr>', meses, re.S)
    for mes in ('julio 2026', 'agosto 2026'):
        fila = next(f for f in filas if mes in f)
        assert '<td class="num">3,0×</td>' in fila and 'ROAS no comparable' not in fila


def test_pnd139_centro_e_historial_cambio_de_fuente(app, base_temporal, monkeypatch):
    import db
    import experimentos as ex
    import resultados as r
    from tests.test_experimentos_db import _pieza
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-16T12:00:00")
    eid = _experimento("TW", atribucion="triple_whale", objetivo_meta="OUTCOME_SALES")
    ep = ex.agregar_pieza("acme", eid, _pieza(base_temporal, legado="cf_tw"), "CO")
    for t, g, c, i, f in [("2026-08-10T08:00:00", 100, 2, 300, "triple_whale"),
                          ("2026-08-31T08:00:00", 150, 0, 0, "ninguna"),
                          ("2026-09-10T08:00:00", 200, 6, 600, "meta")]:
        ex.snapshot(ep, dict(gasto=g, compras=c, ingresos=i, fuente_ventas=f), tomado_en=t)
    carga = r.cargar("acme", r.Filtro(dias=30), db.ahora())
    k = {i['clave']: i for i in r.indicadores(carga)}
    for clave in ('compras', 'ingresos', 'roas', 'cpa'):
        assert k[clave]['valor'] is None and k[clave]['roas_no_comparable']
    assert r.piezas(carga, {})[0]['compras'] is None
    assert r.paises(carga)[0]['roas'] is None
    assert r.experimentos_tarjetas(carga)[0]['valor'] is None
    html = app["c"].get("/cliente/acme/experimentos/resultados?dias=30", headers=AJAX).get_data(as_text=True)
    assert 'Las ventas cambiaron de fuente en este período' in _kpi_roas(html)
    hist = html[html.index('class="tb-tiles"'):]
    assert 'Las ventas cambiaron de fuente en este período' in hist
    tiles = hist[:hist.index('class="tb-meses')]
    assert '<strong>—</strong>' in tiles and '<strong>None</strong>' not in tiles
    meses = hist[hist.index('class="tb-meses'):]
    septiembre = next(f for f in re.findall(r'<tr[^>]*>(.*?)</tr>', meses, re.S) if 'septiembre 2026' in f)
    assert septiembre.count('—') >= 3
