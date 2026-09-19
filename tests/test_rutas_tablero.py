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

    def _explota(cliente, ahora_iso=None, datos=None):
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


def test_grafico_tablero_tope_menor_que_uno(app):
    """Gasto en céntimos (< 1): el máximo «bonito» y las etiquetas siguen
    siendo números razonables, no 0 ni un eje vacío."""
    d = app["dashboard"]
    dias = [{"dia": "2026-09-01", "gasto": 0.42, "compras": 0, "ingresos": 0.0},
            {"dia": "2026-09-02", "gasto": 0.07, "compras": 0, "ingresos": 0.3}]
    g = d._grafico_tablero({"moneda": "USD", "dias": dias})
    assert g["maximo"] == 0.5
    assert [t["texto"] for t in g["marcas"]] == ["0", "0,12", "0,25", "0,38", "0,5"]
    assert g["dias"][0]["gasto_y"] < g["dias"][1]["gasto_y"] < g["base_y"]   # 0,42 más alto que 0,07
    assert g["dias"][1]["ingresos_y"] < g["dias"][1]["gasto_y"]
    assert d._nice_max(0.001) == 0.001 and d._nice_max(0.0011) == 0.002


def test_top_ganadora_de_experimento_cerrado_lo_avisa(app, base_temporal, monkeypatch):
    import experimentos as ex
    eid, _ep = _sembrar(base_temporal)
    ex.actualizar("acme", eid, estado="cerrado")
    _reloj(monkeypatch)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Cojín abrazable (cerrado)" in html


def test_contexto_tablero_cachea_60s_e_invalida_con_snapshot(app, base_temporal, monkeypatch):
    """Mismo objeto dentro de los 60 s; uno nuevo cuando entra un snapshot,
    una propuesta, cambia un experimento o vence el TTL."""
    import experimentos as ex
    import propuestas
    d = app["dashboard"]
    eid, ep = _sembrar(base_temporal)
    _reloj(monkeypatch)
    reloj = {"t": 1000.0}
    monkeypatch.setattr(d.time, "monotonic", lambda: reloj["t"])

    ctx1 = d._contexto_tablero("acme")
    reloj["t"] += 59
    assert d._contexto_tablero("acme") is ctx1
    assert d._contexto_tablero("otro") is not ctx1          # por proyecto
    # Un snapshot nuevo invalida al instante (sin esperar el TTL).
    ex.snapshot(ep, {"gasto": 400, "impresiones": 5000, "clics_enlace": 50, "compras": 4, "ingresos": 15000,
                     "fuente_ventas": "meta"}, tomado_en="2026-09-16T09:00:00")
    ctx2 = d._contexto_tablero("acme")
    assert ctx2 is not ctx1
    assert ctx2["resumen"]["por_moneda"]["COP"]["gasto"] == 300.0
    assert d._contexto_tablero("acme") is ctx2
    # Una propuesta pendiente también.
    propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "prueba")
    ctx3 = d._contexto_tablero("acme")
    assert ctx3 is not ctx2 and ctx3["resumen"]["propuestas_pendientes"] == 1
    # Y un cambio de estado del experimento (actualizado_en).
    monkeypatch.setattr(d.db, "ahora", lambda: "2026-09-16T10:00:01")
    ex.actualizar("acme", eid, estado="pausado")
    ctx4 = d._contexto_tablero("acme")
    assert ctx4 is not ctx3 and ctx4["resumen"]["experimentos_corriendo"] == 0
    # Y un cambio en una pieza (veredicto): desaparece del top al instante.
    monkeypatch.setattr(d.db, "ahora", lambda: "2026-09-16T10:00:02")
    ex.actualizar_pieza("acme", ep, veredicto="perdedor")
    ctx4b = d._contexto_tablero("acme")
    assert ctx4b is not ctx4 and ctx4b["top"] == []
    # TTL: pasados 60 s se recalcula aunque nada cambie.
    reloj["t"] += 60
    ctx5 = d._contexto_tablero("acme")
    assert ctx5 is not ctx4b and ctx5["resumen"] == ctx4b["resumen"]
    d.invalidar_tablero("acme")
    assert d._contexto_tablero("acme") is not ctx5
    # El CSV sale del mismo contexto cacheado.
    r = app["c"].get("/cliente/acme/tablero/mes.csv")
    assert r.status_code == 200 and r.get_data(as_text=True) == d._contexto_tablero("acme")["csv"]


def _sembrar_masivo(base_temporal, n_exp, n_piezas, n_snaps, ahora=AHORA):
    """n_exp experimentos corriendo × n_piezas × n_snaps snapshots cada 2 h
    hacia atrás desde `ahora`, insertados en bloque."""
    from datetime import datetime, timedelta
    import db
    paises = [{"pais": "CO", "presupuesto_dia": 20000.0}]
    t0 = datetime.fromisoformat(ahora) - timedelta(hours=2 * n_snaps)
    with db.conectar() as con:
        for i in range(n_exp):
            eid = con.execute(db.experimento.insert().values(
                cliente="acme", nombre=f"Exp {i}", paises=paises, moneda="COP", tope_total=500000.0, dias=7,
                objetivo_meta="OUTCOME_TRAFFIC", estado="corriendo", creado_en=ahora, actualizado_en=ahora,
                legado=False)).inserted_primary_key[0]
            for j in range(n_piezas):
                ep = con.execute(db.experimento_pieza.insert().values(
                    cliente="acme", experimento_id=eid, pais="CO", estado="activo",
                    veredicto="ganador" if j == 0 else "pendiente", creado_en=ahora, actualizado_en=ahora,
                    extra={})).inserted_primary_key[0]
                con.execute(db.metrica_snapshot.insert(), [
                    dict(experimento_pieza_id=ep, tomado_en=(t0 + timedelta(hours=2 * k)).isoformat(timespec="seconds"),
                         gasto=float(k * 100), compras=k, ingresos=float(k * 1000), clics_enlace=k * 3,
                         impresiones=k * 50, fuente_ventas="meta", extra={})
                    for k in range(n_snaps)])


def test_contexto_tablero_rinde_con_20_experimentos(app, base_temporal, monkeypatch):
    """20 experimentos × 3 piezas × 90 snapshots: el tablero frío (sin caché)
    se calcula en menos de 0,5 s. Antes de indexar las series y acotar la
    consulta de snapshots tardaba ~190 ms aquí y crecía con el histórico."""
    import time
    d = app["dashboard"]
    _sembrar_masivo(base_temporal, 20, 3, 90)
    _reloj(monkeypatch)
    d.invalidar_tablero("acme")
    d._contexto_tablero("acme")            # calienta imports/conexión
    d.invalidar_tablero("acme")
    inicio = time.perf_counter()
    ctx = d._contexto_tablero("acme")
    duracion = time.perf_counter() - inicio
    assert ctx["errores"] == []
    assert ctx["resumen"]["experimentos_corriendo"] == 20 and len(ctx["top"]) == 5
    assert len(ctx["serie"]["dias"]) == 30 and ctx["csv"].count("\n") == 61
    print(f"\n_contexto_tablero frío 20x3x90: {duracion * 1000:.0f} ms")
    assert duracion < 0.5, f"{duracion:.3f}s"


def test_contexto_tablero_tolera_grafico_roto(app, base_temporal, monkeypatch):
    d = app["dashboard"]
    _sembrar(base_temporal)
    _reloj(monkeypatch)
    monkeypatch.setattr(d, "_grafico_tablero", lambda serie: (_ for _ in ()).throw(ZeroDivisionError("x")))
    ctx = d._contexto_tablero("acme")
    assert ctx["grafico"] is None and ctx["serie"] is not None
    assert "grafico: ZeroDivisionError" in ctx["errores"]
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200 and "250 COP" in r.get_data(as_text=True)


def test_tile_generacion_este_mes(app, base_temporal, monkeypatch):
    """Task 3: junto al gasto de pauta va lo pagado en generación (tabla
    `gasto`, USD) este mes; fuera del mes no cuenta. Lleva a Configuración."""
    import gastos
    _sembrar(base_temporal)
    gastos.registrar("acme", "video", 0.85, "video:cf_1", detalle="wan3 · 8 s", creado_en="2026-09-10T09:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:cf_1", creado_en="2026-09-11T09:00:00")
    gastos.registrar("acme", "video", 5.0, "video:viejo", creado_en="2026-08-20T09:00:00")
    _reloj(monkeypatch)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    tb = html[html.index('id="tab-tablero"'):html.index('id="tab-creativeflowplus"')]
    ini = tb.index("Generación este mes")
    tile = tb[tb.rindex("<a", 0, ini):tb.index("</a>", ini)]
    assert "US$ 0,87" in tile and "2 cobro(s) a proveedores" in tile
    assert 'data-ir-tab="settings"' in tile
    assert "250 COP" in tb   # la pauta sigue en su moneda, al lado


def test_tile_generacion_sin_gasto(app, base_temporal, monkeypatch):
    _reloj(monkeypatch)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    tb = html[html.index('id="tab-tablero"'):html.index('id="tab-creativeflowplus"')]
    assert "Generación este mes" in tb and "US$ 0,00" in tb and "sin generación pagada" in tb
