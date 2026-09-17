"""Pestaña Tablero (Bloque 6): render de ver_cliente con datos sembrados,
estado vacío, descarga CSV, aislamiento entre proyectos y tolerancia a que
una parte del tablero explote (`_contexto_tablero`). Sin red: meta_conexion
y tiendas se fingen con monkeypatch, como en test_tablero."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza

AHORA = "2026-09-16T10:00:00"


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch):
    import dashboard
    import tiendas
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(tiendas, "listar", lambda c: [])
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda *a, **kw: True)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def _reloj(monkeypatch, iso=AHORA):
    """Fija «ahora» DESPUÉS de sembrar: las inserciones de la siembra usan
    tomado_en explícito, y el GET no escribe nada."""
    import db
    monkeypatch.setattr(db, "ahora", lambda: iso)


def _sembrar(base_temporal):
    """Un experimento corriendo con una pieza ganadora y dos snapshots (uno
    antes del mes, otro dentro): el mes suma gasto 250, compras 2, ingresos
    7000 COP (ROAS 28)."""
    import experimentos as ex
    eid = ex.crear("acme", "Cojín abrazable", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="corriendo")
    pid = _pieza(base_temporal)
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, estado="activo", veredicto="ganador", veredicto_motivo="ROAS por encima del umbral",
                        veredicto_en=AHORA)
    ex.snapshot(ep, {"gasto": 100, "impresiones": 1000, "clics_enlace": 10, "compras": 1, "ingresos": 5000,
                     "fuente_ventas": "meta", "ctr": 1.0, "cpc": 10.0, "roas": 50.0}, tomado_en="2026-08-31T23:00:00")
    ex.snapshot(ep, {"gasto": 350, "impresiones": 4000, "clics_enlace": 40, "compras": 3, "ingresos": 12000,
                     "fuente_ventas": "meta", "ctr": 1.5, "cpc": 8.75, "roas": 34.29}, tomado_en="2026-09-15T23:00:00")
    return eid, ep


def test_tablero_con_datos(app, base_temporal, monkeypatch):
    eid, _ep = _sembrar(base_temporal)
    _reloj(monkeypatch)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Tablero · septiembre 2026" in html
    assert 'id="tab-tablero"' in html
    # Tiles del mes (deltas, no acumulados): gasto 250, compras 2, ingresos 7.000, ROAS 28.
    assert "250 COP" in html and "7.000 COP" in html
    assert "ROAS" in html and "28,0" in html
    assert "Experimentos corriendo" in html and "Propuestas pendientes" in html
    # Gráfico de 30 días: SVG inline con barras (gasto) y línea (ingresos).
    assert "<svg" in html and 'class="tb-grafico"' in html
    assert "tb-barra" in html and "tb-linea" in html
    # Top ganadoras: nombre de la pieza, bandera, motivo y enlace al experimento.
    assert "Final es_CO" in html and "🇨🇴" in html
    assert "ROAS por encima del umbral" in html
    assert f"?exp={eid}#experimentos" in html
    # Alertas: no hay ninguna que urja salvo que el experimento corriendo lleva 11 h sin métricas.
    assert "11 h sin métricas nuevas de Meta" in html
    assert "Descargar CSV del mes" in html and "/cliente/acme/tablero/mes.csv" in html


def test_tablero_vacio(app, base_temporal, monkeypatch):
    _reloj(monkeypatch)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Tablero · septiembre 2026" in html
    assert "Crea tu primer experimento" in html
    assert "Sin alertas" in html
    assert "sin ventas medibles" in html
    assert "tb-barra" not in html   # sin datos no se pinta un gráfico vacío


def test_tablero_pestana_por_defecto_y_sidebar(app, base_temporal):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-tab="tablero"' in html
    # El sidebar lista Tablero antes que Crear.
    assert html.index('data-tab="tablero"') < html.index('data-tab="creativeflowplus"')
    # Sin hash ni pestaña recordada, la página abre en el Tablero.
    assert "activar(paneles[inicial] ? inicial : 'tablero')" in html


def test_csv_del_mes(app, base_temporal, monkeypatch):
    _sembrar(base_temporal)
    _reloj(monkeypatch)
    r = app["c"].get("/cliente/acme/tablero/mes.csv")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    assert "charset=utf-8" in r.headers["Content-Type"]
    assert r.headers["Content-Disposition"] == 'attachment; filename="tablero_acme_2026-09.csv"'
    lineas = r.get_data(as_text=True).lstrip("﻿").splitlines()
    assert lineas[0] == "experimento;pais;pieza;veredicto;impresiones;clics;gasto;compras;ingresos;roas;moneda"
    assert lineas[1].startswith("Cojín abrazable;CO;Final es_CO;ganador;3000;30;250;2;7000;28;COP")


def test_csv_rechaza_cliente_cruzado(app, base_temporal):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    r = c.get("/cliente/otro/tablero/mes.csv")
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    r = c.get("/cliente/acme/tablero/mes.csv")
    assert r.status_code == 200


def test_contexto_tablero_tolera_una_parte_rota(app, base_temporal, monkeypatch):
    import tablero
    d = app["dashboard"]
    _sembrar(base_temporal)
    _reloj(monkeypatch)

    def _explota(cliente, ahora_iso=None):
        raise RuntimeError("token=SECRETO Meta caída")
    monkeypatch.setattr(tablero, "alertas", _explota)
    ctx = d._contexto_tablero("acme")
    assert ctx["alertas"] is None
    assert ctx["resumen"] is not None and ctx["serie"] is not None and ctx["top"]
    assert ctx["errores"] == ["alertas: RuntimeError"]   # sin el mensaje: podría traer un token
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "No se pudo calcular las alertas" in html
    assert "SECRETO" not in html
    assert "250 COP" in html and "Final es_CO" in html   # el resto se sigue mostrando


def test_grafico_tablero_geometria(app):
    """Un eje: barras de gasto y línea de ingresos comparten escala (misma
    moneda); 4 marcas + máximo redondeado; etiqueta cada 5 días."""
    d = app["dashboard"]
    dias = [{"dia": f"2026-09-{i:02d}", "gasto": 1000.0 * i, "compras": 0, "ingresos": 0.0} for i in range(1, 31)]
    dias[-1]["ingresos"] = 42000.0
    g = d._grafico_tablero({"moneda": "COP", "dias": dias})
    assert g["maximo"] == 50000.0
    assert [t["valor"] for t in g["marcas"]] == [0.0, 12500.0, 25000.0, 37500.0, 50000.0]
    assert len(g["dias"]) == 30 and g["dias"][0]["etiqueta"] == "01/09" and g["dias"][1]["etiqueta"] == ""
    assert g["dias"][5]["etiqueta"] == "06/09"
    assert g["dias"][-1]["ingresos_y"] < g["dias"][-1]["gasto_y"]   # 42.000 queda por encima de 30.000
    assert g["dias"][0]["titulo"] == "01/09 · gasto 1.000 COP · ingresos 0 COP"
    assert d._grafico_tablero({"moneda": None, "dias": []}) is None
    vacio = [{"dia": "2026-09-01", "gasto": 0, "compras": 0, "ingresos": 0}]
    assert d._grafico_tablero({"moneda": "COP", "dias": vacio}) is None
