"""El Tablero (Bloque 6) fundido en Experimentos (E2, spec 2026-10-02): lo que antes era la pestaña Tablero ahora
vive en el centro de resultados — los totales y el mes a mes en el historial (sección 09 de `exp_resultados`), el
gráfico de 30 días en «Día a día» (sección 02), las ganadoras en el ranking (sección 05), la línea de alertas en
«Necesita tu decisión» — y la pestaña ya no existe (`tablero` resuelve a `experimentos`, que es la primera y la de
por defecto). Se prueba el render de la página y del fragmento con datos sembrados, el estado vacío, la descarga
CSV, el aislamiento entre proyectos y la tolerancia a que una parte del tablero explote (`_contexto_tablero`).
Sin red: meta_conexion y tiendas se fingen con monkeypatch, como en test_tablero."""
import json

import pytest

import idiomas
from tests.test_experimentos_db import PAISES, _pieza
from tests.test_rutas_experimentos import _resultados

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


def _historial(c, **filtro):
    """El historial (sección 09 de `exp_resultados`): los totales, el mes a mes y la tienda según Triple Whale, que
    eran el cuerpo de la pestaña Tablero."""
    html = _resultados(c, **filtro)
    return html[html.index("Historial mes a mes"):]


def _seccion_alertas(html):
    ini = html.index('<section id="tab-alertas"')
    return html[ini:html.index('<section id="tab-', ini + 10)]


def _mes_a_mes(tb):
    ini = tb.index('class="tb-meses')
    return tb[ini:tb.index("</table>", ini)]


def _datos_graficos(html):
    """El JSON que el JS del centro dibuja (`#cr-datos`)."""
    ini = html.index('id="cr-datos">') + len('id="cr-datos">')
    return json.loads(html[ini:html.index("</script>", ini)])


def _dia_de_meta(base_temporal, ep, fecha, **campos):
    """Una fila de `metrica_dia` (el detalle día a día de Meta, que dibuja la sección 02)."""
    import db
    base = dict(impresiones=500, alcance=400, frecuencia=1.2, clics=12, clics_enlace=10, gasto=5.0, cpm=10.0,
                vistas_3s=100, reproducciones=300, p25=90, p50=60, p75=40, p95=20, p100=10, thruplay=30,
                tiempo_medio_s=3.0, visitas_pagina=6, carrito=2, pago_iniciado=1, compras_meta=1, ingresos_meta=30.0)
    base.update(campos)
    with db.conectar() as con:
        con.execute(db.metrica_dia.insert().values(experimento_pieza_id=ep, fecha=fecha, actualizado_en=fecha + "T12:00:00",
                                                   **base))


def test_tablero_con_datos(app, base_temporal, monkeypatch):
    eid, ep = _sembrar(base_temporal)
    _dia_de_meta(base_temporal, ep, "2026-09-15")
    _reloj(monkeypatch)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    pagina = r.get_data(as_text=True)
    # La pestaña Tablero se fundió en Experimentos (la primera): no hay panel ni botón «tablero» y la página no trae
    # los totales (llegan en el fragmento de resultados).
    assert 'id="tab-tablero"' not in pagina and 'data-tab="tablero"' not in pagina
    exp = pagina[pagina.index('<section id="tab-experimentos"'):pagina.index('<section id="tab-alertas"')]
    assert "<h2>Experimentos</h2>" in exp and "Tablero · septiembre 2026" not in pagina
    html = _resultados(app["c"])
    hist = html[html.index("Historial mes a mes"):]
    # Tiles: el total desde el inicio (el último acumulado): gasto 350, compras 3, ingresos 12.000, ROAS 34,3.
    tiles = hist[:hist.index('class="tb-meses')]
    assert "Gasto total" in tiles and "350 COP" in tiles and "12.000 COP" in tiles and "34,3" in tiles
    assert "Gasto del mes" not in tiles and "250 COP" not in tiles
    assert "Experimentos corriendo" in tiles and "Propuestas pendientes" in tiles
    # Mes a mes: septiembre (250, 2, 7.000, ROAS 28) arriba de agosto (100, 1, 5.000, ROAS 50).
    meses = _mes_a_mes(hist)
    assert "Mes a mes" in hist
    assert meses.index("septiembre 2026") < meses.index("agosto 2026")
    sep = meses[meses.index("septiembre 2026"):meses.index("agosto 2026")]
    assert "250 COP" in sep and "7.000 COP" in sep and "28,0" in sep and "<td" in sep
    ago = meses[meses.index("agosto 2026"):]
    assert "100 COP" in ago and "5.000 COP" in ago and "50,0" in ago
    # El gráfico de 30 días (SVG del Tablero) lo reemplaza «Día a día» (sección 02): el JS dibuja las barras de
    # gasto y la línea de la métrica con el JSON del fragmento, que lleva el gasto de cada día.
    assert 'data-cr-grafico="dia"' in html and 'class="tb-grafico"' not in html
    serie = _datos_graficos(html)["serie"]
    assert serie["gasto"][serie["dias"].index("2026-09-15")] == 250.0 and serie["moneda"] == "COP"
    # «Top 5 ganadoras» lo reemplaza el ranking de piezas (sección 05): nombre, bandera y veredicto de la pieza; el
    # motivo del veredicto va en la gestión del experimento y la tarjeta del experimento (07) lleva a esa gestión.
    ranking = html[html.index('id="cr-ranking"'):html.index('aria-labelledby="cr-s06"')]
    assert "Final es_CO" in ranking and "🇨🇴" in ranking and "cr-v-ganadora" in ranking
    assert "ROAS por encima del umbral" in _resultados(app["c"], exp=eid)
    assert f'href="#experimentos?exp={eid}"' in html
    # Alertas: el experimento corriendo lleva 11 h sin métricas. La lista vive en la pestaña Alertas; el centro de
    # resultados solo dice cuántas hay.
    al = _seccion_alertas(pagina)
    assert "11 h sin métricas nuevas de Meta" in al
    assert "11 h sin métricas nuevas de Meta" not in html and "alertas necesitan tu atención" in html
    assert "Descargar CSV del mes" in pagina and "/cliente/acme/tablero/mes.csv" in pagina
    # m3 (revisión final de E2): una sola vez, en la cabecera; el historial del fragmento ya no lo repite
    assert exp.count("Descargar CSV del mes") == 1 and "Descargar CSV del mes" not in html


def test_tablero_vacio(app, base_temporal, monkeypatch):
    import alertas
    monkeypatch.setattr(alertas, "calcular", lambda cliente, ahora_iso=None: [])
    app["dashboard"].invalidar_alertas()
    _reloj(monkeypatch)
    pagina = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "<h2>Experimentos</h2>" in pagina and 'id="tab-tablero"' not in pagina
    html = _resultados(app["c"])
    # «Crea tu primer experimento» lo reemplaza el estado vacío del centro, con su botón.
    assert "Todavía no hay experimentos" in html and "+ Nuevo experimento" in html
    # Sin alertas ni propuestas: «Sin alertas. Todo en orden.» ya no tiene línea propia; lo dice «Nada por decidir»
    # y la línea de alertas solo sale cuando hay (el conteo vive en la burbuja del menú).
    assert "Nada por decidir" in html and "cr-alertas-linea" not in html and "Sin alertas. Todo en orden." not in html
    hist = html[html.index("Historial mes a mes"):]
    assert "sin ventas medibles" in hist
    assert "tb-barra" not in html   # sin datos no se pinta un gráfico vacío
    assert 'data-cr-grafico="dia"' not in html and "Sin datos en este periodo" in html
    assert "Mes a mes" in hist and 'class="tb-meses' not in hist
    assert "Todavía no hay gasto en ningún mes" in hist


def test_tablero_resume_las_alertas_en_una_linea(app, base_temporal, monkeypatch):
    """Spec alertas §7 y §12.9: la lista vive en la pestaña Alertas; el centro de resultados (donde se fundió el
    Tablero) dice cuántas hay en «Necesita tu decisión» y enlaza allá."""
    import alertas
    lista = [alertas._alerta("llave:r2", alertas.huella(), "bloquea", "puesta_a_punto", "Falta R2", "d", "settings"),
             alertas._alerta("proyecto:logo", alertas.huella(), "info", "faltantes", "Sin logos", "d", "settings")]
    monkeypatch.setattr(alertas, "calcular", lambda cliente, ahora_iso=None: [dict(a) for a in lista])
    app["dashboard"].invalidar_alertas()
    tb = _resultados(app["c"])
    assert "2 alertas necesitan tu atención" in tb
    assert "Nada por decidir" not in tb          # m1: con alertas y sin propuestas, solo la línea de alertas
    assert 'href="#alertas" data-ir-tab="alertas">Ver Alertas' in tb
    assert "tb-alerta" not in tb and "Falta R2" not in tb and "Sin logos" not in tb
    monkeypatch.setattr(alertas, "calcular", lambda cliente, ahora_iso=None: [dict(lista[1])])
    app["dashboard"].invalidar_alertas()
    tb = _resultados(app["c"])
    assert "1 alerta necesita tu atención" in tb


def test_tablero_pestana_por_defecto_y_sidebar(app, base_temporal):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    # El Tablero ya no es pestaña: sale del menú y de los paneles; Experimentos lo absorbe y va primero.
    assert 'data-tab="tablero"' not in html and 'id="tab-tablero"' not in html and "tablero:" not in html
    assert 'data-tab="experimentos"' in html
    # El sidebar lista Experimentos antes que Crear (y que Alertas), y su panel es el primero de la página.
    assert html.index('data-tab="experimentos"') < html.index('data-tab="alertas"') < html.index('data-tab="creativeflowplus"')
    assert html.index('id="tab-experimentos"') < html.index('id="tab-alertas"') < html.index('id="tab-creativeflowplus"')
    # Sin hash ni pestaña recordada, la página abre en Experimentos; un hash o una pestaña recordada «tablero»
    # (de antes de E2) también caen ahí.
    assert "activar(paneles[inicial] ? inicial : 'experimentos')" in html
    assert "t === 'ads' || t === 'tablero') return 'experimentos'" in html


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
    assert "alertas" not in ctx                          # el Tablero ya no calcula alertas: lo hace alertas.py
    assert ctx["resumen"] is not None and ctx["total"] is not None and ctx["meses"]
    assert ctx["errores"] == []
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # La fuente `tablero` de alertas.py falló: sale en Alertas con solo el nombre de la clase.
    al = _seccion_alertas(html)
    assert "No se pudo revisar tablero" in al and "RuntimeError" in al
    assert "SECRETO" not in html
    # El resto se sigue mostrando: el centro de resultados (donde se fundió el Tablero) trae el gasto y la pieza.
    resultados = _resultados(app["c"])
    assert "SECRETO" not in resultados
    assert "250 COP" in resultados and "Final es_CO" in resultados


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


def test_grafico_tooltip_en_ingles(app):
    """Fix round 1: el tooltip nativo (<title>) sigue el idioma de quien
    mira — nunca «gasto»/«ingresos» crudos para alguien viendo en inglés;
    los números del tooltip usan el separador de miles de ese idioma
    (`tablero.dinero` ya pasa por `idiomas.numero`)."""
    d = app["dashboard"]
    dias = [{"dia": f"2026-09-{i:02d}", "gasto": 1000.0 * i, "compras": 0, "ingresos": 0.0} for i in range(1, 31)]
    dias[-1]["ingresos"] = 42000.0
    with idiomas.en_idioma("en"):
        g = d._grafico_tablero({"moneda": "COP", "dias": dias})
    titulo = g["dias"][0]["titulo"]
    assert "spend" in titulo and "revenue" in titulo
    assert "gasto" not in titulo and "ingresos" not in titulo
    assert titulo == "01/09 · spend 1,000 COP · revenue 0 COP"
    # En español el tooltip queda exactamente como antes (test_grafico_tablero_geometria).
    g_es = d._grafico_tablero({"moneda": "COP", "dias": dias})
    assert g_es["dias"][0]["titulo"] == "01/09 · gasto 1.000 COP · ingresos 0 COP"


def test_filtro_roas_redondea_igual_que_main(app):
    """El filtro `roas` pasa por `idiomas.numero` (revisión final fase 4,
    M2): confirma que llega hasta acá también, no solo hasta
    `idiomas.numero`/`tablero.dinero`."""
    d = app["dashboard"]
    assert d._filtro_roas(12.345) == "12,3"
    assert d._filtro_roas(0.015) == "0,0"


def test_compacto_eje_en_ingles(app):
    """Fix round 1: `_compacto` (etiquetas del eje) usa el separador decimal
    del idioma activo — coma en español (sin cambios), punto en inglés."""
    d = app["dashboard"]
    assert d._compacto(1_200_000) == "1,2 M"
    assert d._compacto(0.5) == "0,5"
    with idiomas.en_idioma("en"):
        assert d._compacto(1_200_000) == "1.2 M"
        assert d._compacto(0.5) == "0.5"


def test_top_ganadora_de_experimento_cerrado_lo_avisa(app, base_temporal, monkeypatch):
    import experimentos as ex
    eid, _ep = _sembrar(base_temporal)
    ex.actualizar("acme", eid, estado="cerrado")
    _reloj(monkeypatch)
    # «Top 5 ganadoras» ya no existe: la ganadora de un experimento cerrado sigue en el ranking de piezas (05) y su
    # experimento, en la lista (07), dice que está cerrado.
    html = _resultados(app["c"])
    ranking = html[html.index('id="cr-ranking"'):html.index('aria-labelledby="cr-s06"')]
    assert "Final es_CO" in ranking and "cr-v-ganadora" in ranking
    lista = html[html.index('aria-labelledby="cr-s07"'):]
    tarjeta = lista[lista.index('<a data-cr-filtro href="#experimentos?exp=%d"' % eid):]
    tarjeta = tarjeta[:tarjeta.index("</a>")]
    assert "Cojín abrazable" in tarjeta and "cr-estado-cerrado" in tarjeta and "<small>cerrado" in tarjeta


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
    # Y un cambio en una pieza (veredicto): el CSV del mes lo dice al instante.
    monkeypatch.setattr(d.db, "ahora", lambda: "2026-09-16T10:00:02")
    ex.actualizar_pieza("acme", ep, veredicto="perdedor")
    ctx4b = d._contexto_tablero("acme")
    assert ctx4b is not ctx4 and "perdedor" in ctx4b["csv"] and "perdedor" not in ctx4["csv"]
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
    assert ctx["resumen"]["experimentos_corriendo"] == 20 and ctx["total"]["experimentos_corriendo"] == 20
    assert ctx["meses"] and ctx["csv"].count("\n") == 61
    print(f"\n_contexto_tablero frío 20x3x90: {duracion * 1000:.0f} ms")
    assert duracion < 0.5, f"{duracion:.3f}s"


def test_contexto_tablero_solo_calcula_lo_que_alguien_pinta(app, base_temporal, monkeypatch):
    """m2 de la revisión final de E2: la serie de 30 días, el top de ganadoras y los dos gráficos del Tablero viejo se
    calculaban en cada carga y nadie los leía. El CSV se queda (lo lee `tab_descargar_csv`)."""
    import tablero
    d = app["dashboard"]
    _sembrar(base_temporal)
    _reloj(monkeypatch)
    for nombre in ("serie_diaria", "serie_diaria_triple_whale", "top_ganadoras"):
        monkeypatch.setattr(tablero, nombre, lambda *a, **k: pytest.fail("nadie lo pinta"))
    monkeypatch.setattr(d, "_grafico_tablero", lambda serie: pytest.fail("nadie lo pinta"))
    ctx = d._contexto_tablero("acme")
    assert not {"serie", "serie_triple_whale", "top", "grafico", "grafico_triple_whale"} & set(ctx)
    assert ctx["errores"] == [] and ctx["csv"] and ctx["total"] is not None and ctx["meses"]


def test_contexto_tablero_tolera_el_mes_a_mes_roto(app, base_temporal, monkeypatch):
    import tablero
    d = app["dashboard"]
    _sembrar(base_temporal)
    _reloj(monkeypatch)
    monkeypatch.setattr(tablero, "mes_a_mes", lambda *a, **k: (_ for _ in ()).throw(ZeroDivisionError("x")))
    ctx = d._contexto_tablero("acme")
    assert ctx["meses"] is None and ctx["total"] is not None
    assert "meses: ZeroDivisionError" in ctx["errores"]
    hist = _historial(app["c"])
    assert "No se pudo calcular el desglose por mes." in hist and "350 COP" in hist     # el total sigue


def test_tile_generacion_total_y_por_mes(app, base_temporal, monkeypatch):
    """Junto al gasto de pauta va lo pagado en generación (tabla `gasto`,
    USD): el tile es el total desde el inicio y la tabla lo abre por mes.
    Lleva a Configuración."""
    import gastos
    _sembrar(base_temporal)
    gastos.registrar("acme", "video", 0.85, "video:cf_1", detalle="wan3 · 8 s", creado_en="2026-09-10T09:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:cf_1", creado_en="2026-09-11T09:00:00")
    gastos.registrar("acme", "video", 5.0, "video:viejo", creado_en="2026-08-20T09:00:00")
    _reloj(monkeypatch)
    tb = _historial(app["c"])
    ini = tb.index("Generación total")
    tile = tb[tb.rindex("<a", 0, ini):tb.index("</a>", ini)]
    assert "US$ 5,87" in tile and "3 cobro(s) a proveedores" in tile
    assert 'data-ir-tab="settings"' in tile
    assert "350 COP" in tb   # la pauta sigue en su moneda, al lado
    meses = _mes_a_mes(tb)
    assert "US$ 0,87" in meses[meses.index("septiembre 2026"):meses.index("agosto 2026")]
    assert "US$ 5,00" in meses[meses.index("agosto 2026"):]


def test_tile_generacion_sin_gasto(app, base_temporal, monkeypatch):
    _reloj(monkeypatch)
    tb = _historial(app["c"])
    assert "Generación total" in tb and "US$ 0,00" in tb and "sin generación pagada" in tb


def test_mes_a_mes_una_fila_por_moneda(app, base_temporal, monkeypatch):
    """Pauta en dos monedas el mismo mes: una fila por moneda, nunca se
    convierte; la generación va una sola vez, en la primera fila del mes."""
    import experimentos as ex
    import gastos
    _sembrar(base_temporal)
    eid = ex.crear("acme", "Manta USA", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t", "USD")
    ep = ex.agregar_pieza("acme", eid, _pieza(base_temporal, legado="cf_9__es_CO"), "CO")
    ex.snapshot(ep, {"gasto": 12.5, "impresiones": 40}, tomado_en="2026-09-05T08:00:00")
    gastos.registrar("acme", "video", 0.85, "video:cf_1", creado_en="2026-09-10T09:00:00")
    _reloj(monkeypatch)
    meses = _mes_a_mes(_historial(app["c"]))
    sep = meses[meses.index("septiembre 2026"):meses.index("agosto 2026")]
    assert sep.count("<tr") == 2 and "250 COP" in sep and "12,50 USD" in sep
    assert sep.count("US$ 0,85") == 1


def test_contexto_tablero_invalida_con_un_cobro_nuevo(app, base_temporal, monkeypatch):
    """La generación está en el tablero cacheado: un cobro nuevo lo
    invalida al instante, como un snapshot."""
    import gastos
    d = app["dashboard"]
    _sembrar(base_temporal)
    _reloj(monkeypatch)
    monkeypatch.setattr(d.time, "monotonic", lambda: 1000.0)
    ctx1 = d._contexto_tablero("acme")
    assert ctx1["generacion_total"] == {"total": 0.0, "n": 0}
    gastos.registrar("acme", "video", 0.85, "video:cf_1", creado_en="2026-09-10T09:00:00")
    ctx2 = d._contexto_tablero("acme")
    assert ctx2 is not ctx1 and ctx2["generacion_total"] == {"total": 0.85, "n": 1}
    assert ctx2["meses"][0]["generacion"] == {"usd": 0.85, "n": 1}
