"""resultados.py (spec 2026-10-02 §4): todo lo que pinta el centro de resultados."""
from datetime import date

import pytest
import sqlalchemy as sa

from tests.test_experimentos_db import PAISES, _pieza

AHORA = "2026-10-02T12:00:00"


def _dia(db, ep, fecha, **v):
    base = {"impresiones": 0, "alcance": 0, "frecuencia": 0.0, "clics": 0, "clics_enlace": 0, "gasto": 0.0, "cpm": 0.0,
            "vistas_3s": 0, "reproducciones": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0, "p100": 0, "thruplay": 0,
            "tiempo_medio_s": 0.0, "visitas_pagina": 0, "carrito": 0, "pago_iniciado": 0, "compras_meta": 0,
            "ingresos_meta": 0.0}
    base.update(v)
    with db.conectar() as con:
        con.execute(db.metrica_dia.insert().values(experimento_pieza_id=ep, fecha=fecha, actualizado_en=AHORA, **base))


@pytest.fixture()
def sembrado(base_temporal):
    """acme: experimento «Uno» (video ep_v en CO, imagen ep_i en MX) con 4 días de detalle y snapshots
    acumulados; «otro» proyecto con un experimento que nunca debe aparecer."""
    db = base_temporal
    import experimentos as ex
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    img = _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_img")
    e1 = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 14, 500000.0, "https://t.co/p", "COP")
    ep_v = ex.agregar_pieza("acme", e1, clon, "CO")
    ep_i = ex.agregar_pieza("acme", e1, img, "MX")
    for ep, imp, clics, gasto, v3 in ((ep_v, 1000, 20, 10.0, 300), (ep_i, 1000, 10, 10.0, 0)):
        for i, f in enumerate(("2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02")):
            _dia(db, ep, f, impresiones=imp, clics_enlace=clics + i, gasto=gasto, vistas_3s=v3, frecuencia=1.2,
                 visitas_pagina=clics // 2, carrito=2, pago_iniciado=1, compras_meta=1, ingresos_meta=30.0)
        acumulado = 0.0
        for i, f in enumerate(("2026-09-29T23:00:00", "2026-09-30T23:00:00", "2026-10-01T23:00:00", "2026-10-02T11:00:00")):
            acumulado += gasto
            ex.snapshot(ep, {"impresiones": imp * (i + 1), "gasto": acumulado, "clics_enlace": clics * (i + 1),
                             "compras": i + 1, "ingresos": 30.0 * (i + 1), "frecuencia": 1.5, "fuente_ventas": "meta"},
                        tomado_en=f)
    otro = _pieza(db, cliente="otro", tipo="video", estado="listo", pais=None, idioma=None, legado="cf_o")
    eo = ex.crear("otro", "Ajeno", PAISES, "OUTCOME_TRAFFIC", 7, 1.0, "https://t.co/p", "COP")
    ep_o = ex.agregar_pieza("otro", eo, otro, "CO")
    _dia(db, ep_o, "2026-10-01", impresiones=99999, clics_enlace=9999, gasto=999.0)
    return {"db": db, "e1": e1, "ep_v": ep_v, "ep_i": ep_i, "ep_o": ep_o}


def _evento(db, cliente, experimento_id, tipo, mensaje, creado_en, ep_id=None, datos=None):
    with db.conectar() as con:
        con.execute(db.evento.insert().values(cliente=cliente, experimento_id=experimento_id, experimento_pieza_id=ep_id,
                                              tipo=tipo, mensaje=mensaje, datos=datos or {}, creado_en=creado_en))


def test_filtro_de_y_a_query():
    import resultados as r
    f = r.filtro_de({"dias": "30", "exp": "3", "pais": "co", "pieza": "x", "tipo": "imagen", "moneda": "cop"})
    assert f == r.Filtro(dias=30, experimento_id=3, pais="CO", ep_id=None, tipo="imagen", moneda="COP")
    assert r.filtro_de({"dias": "5", "tipo": "otro", "pais": "C0"}) == r.Filtro()
    assert r.filtro_de({"dias": "0"}).dias == 0
    assert r.a_query(r.Filtro()) == {}
    assert r.a_query(r.Filtro(dias=7, experimento_id=3), experimento_id=None) == {"dias": 7}


def test_periodo():
    import resultados as r
    p = r.periodo(AHORA, 7)
    assert p["n"] == 7 and p["lista"][0] == date(2026, 9, 26) and p["lista"][-1] == date(2026, 10, 2)
    assert p["desde"] == "2026-09-26T00:00:00" and p["hasta"] == "2026-10-03T00:00:00"
    assert p["anterior_desde"] == "2026-09-19T00:00:00" and p["anterior_hasta"] == "2026-09-26T00:00:00"
    t = r.periodo(AHORA, 0, primer_dia=date(2026, 9, 29))
    assert t["es_todo"] and t["n"] == 4 and t["anterior_desde"] is None
    assert r.periodo(AHORA, 0, primer_dia=date(2020, 1, 1))["n"] == r.DIAS_MAX_INICIO
    futuro = r.periodo(AHORA, 0, primer_dia=date(2026, 10, 5))      # un primer día posterior a hoy: nunca vacío
    assert futuro["n"] == 1 and futuro["lista"] == [date(2026, 10, 2)]


def test_indicadores_dinero_y_detalle(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert list(k) == [x[0] for x in r.KPIS]
    assert k["gasto"]["valor"] == 80.0                     # motor del Tablero (snapshots)
    assert k["impresiones"]["valor"] == 8000              # metrica_dia, 2 piezas × 4 días, nada de «otro»
    assert k["ctr"]["valor"] == pytest.approx((20 + 21 + 22 + 23 + 10 + 11 + 12 + 13) / 8000 * 100)
    assert k["gancho"]["valor"] == pytest.approx(1200 / 4000 * 100)   # solo el video
    assert k["frecuencia"]["valor"] == pytest.approx(1.5)
    assert k["cpc"]["valor"] == pytest.approx(80.0 / 132)
    assert k["gasto"]["cambio"] is None or k["gasto"]["cambio"]["sentido"] == "neutro"
    assert len(k["gasto"]["tendencia"]) == 7


def test_cambio_mejor_y_peor():
    import resultados as r
    assert r.cambio(10.0, 8.0, "baja", "dinero")["sentido"] == "peor"
    assert r.cambio(10.0, 8.0, "sube", "dinero")["sentido"] == "mejor"
    assert r.cambio(2.0, 1.5, "sube", "pct")["texto"].startswith("+0,5") or r.cambio(2.0, 1.5, "sube", "pct")["texto"].startswith("+0.5")
    assert r.cambio(5.0, None, "sube", "entero") is None and r.cambio(5.0, 0, "sube", "entero") is None


def test_filtros_aislan_y_recortan(sembrado):
    import resultados as r
    solo_mx = r.indicadores(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))
    assert {i["clave"]: i for i in solo_mx}["impresiones"]["valor"] == 4000
    vacio = r.indicadores(r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA))
    assert {i["clave"]: i for i in vacio}["impresiones"]["valor"] in (0, None)


def test_serie_y_marcas(sembrado):
    import resultados as r
    _evento(sembrado["db"], "acme", sembrado["e1"], "accion", "Se pausó «Unboxing» en CO", "2026-10-01T09:00:00",
            ep_id=sembrado["ep_v"])
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    s = r.serie(c)
    assert s["dias"][-1] == "2026-10-02" and len(s["dias"]) == 7
    assert s["gasto"][-1] == pytest.approx(20.0) and s["ctr"][0] is None
    assert any(m["texto"].startswith("Se pausó") for m in r.marcas(c))


# ---- lo que el sembrado de la tarea no cubre (la revisión de la tarea 2) ----

def test_el_filtro_llega_al_dinero_y_nada_de_otro_proyecto(sembrado):
    """El gasto sale del motor del Tablero sobre los datos YA filtrados: un filtro no se pierde por el camino
    (tablero._datos recarga el proyecto entero si la ventana empieza antes de datos.desde)."""
    import resultados as r

    def gasto(**f):
        return {i["clave"]: i for i in r.indicadores(r.cargar("acme", r.Filtro(**f), AHORA))}["gasto"]["valor"]
    assert gasto(dias=7) == 80.0
    assert gasto(dias=7, pais="MX") == 40.0 and gasto(dias=7, pais="CO") == 40.0
    assert gasto(dias=7, ep_id=sembrado["ep_i"]) == 40.0
    assert gasto(dias=7, tipo="video") == 40.0
    assert gasto(dias=7, experimento_id=999999) == 0.0
    # el periodo anterior también sale de los datos filtrados (no recarga el proyecto entero)
    k = {i["clave"]: i for i in r.indicadores(r.cargar("acme", r.Filtro(dias=3, pais="MX"), AHORA))}
    assert k["gasto"]["valor"] == 30.0 and k["gasto"]["anterior"] == 10.0
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    usados = {f["experimento_pieza_id"] for f in c.dias_act + c.dias_ant}
    assert usados == {sembrado["ep_v"], sembrado["ep_i"]} and sembrado["ep_o"] not in usados
    assert set(c.es_imagen) == {sembrado["ep_v"], sembrado["ep_i"]} and c.es_imagen[sembrado["ep_i"]] is True
    assert c.es_imagen[sembrado["ep_v"]] is False


def test_variacion_contra_el_periodo_anterior(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=3), AHORA)        # 30-sep..02-oct contra 27..29-sep
    assert len(c.dias_act) == 6 and len(c.dias_ant) == 2
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["gasto"]["valor"] == 60.0 and k["gasto"]["anterior"] == 20.0
    assert k["gasto"]["cambio"] == {"texto": "+200,0%", "sentido": "neutro", "flecha": "▲"}
    assert k["ctr"]["valor"] == pytest.approx(102 / 6000 * 100) and k["ctr"]["anterior"] == pytest.approx(1.5)
    assert k["ctr"]["cambio"]["texto"] == "+0,2 pp" and k["ctr"]["cambio"]["sentido"] == "mejor"
    assert k["cpc"]["cambio"]["flecha"] == "▼" and k["cpc"]["cambio"]["sentido"] == "mejor"   # el costo baja: verde
    assert len(k["ctr"]["tendencia"]) == 3 and all(len(i["tendencia"]) == 3 for i in k.values())


def test_desde_el_inicio_no_compara(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=0), AHORA)
    assert c.per["es_todo"] and c.per["n"] == 4 and c.dias_ant == []
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["gasto"]["valor"] == 80.0 and k["compras"]["valor"] == 8
    assert all(i["cambio"] is None and i["anterior"] is None for i in k.values())
    assert k["cpa"]["valor"] == pytest.approx(10.0) and k["roas"]["valor"] == pytest.approx(3.0)
    assert len(r.serie(c)["dias"]) == 4


def test_sin_detalle_diario_no_inventa_ceros(sembrado):
    """Un experimento sin metrica_dia todavía: lo de Meta queda en None (la UI dice «cargando»); el dinero sale igual."""
    import resultados as r
    k = {i["clave"]: i for i in r.indicadores(r.cargar("acme", r.Filtro(dias=7, ep_id=sembrado["ep_v"]), AHORA))}
    assert k["impresiones"]["valor"] == 4000
    db = sembrado["db"]
    with db.conectar() as con:
        con.execute(db.metrica_dia.delete())
    k = {i["clave"]: i for i in r.indicadores(r.cargar("acme", r.Filtro(dias=7), AHORA))}
    assert k["gasto"]["valor"] == 80.0
    assert all(k[c]["valor"] is None for c in ("impresiones", "ctr", "cpc", "cpm", "gancho", "thruplay"))
    s = r.serie(r.cargar("acme", r.Filtro(dias=7), AHORA))
    assert s["ctr"] == [None] * 7 and s["gasto"][-1] == pytest.approx(20.0)


def test_moneda_por_defecto_y_filtro_de_moneda(sembrado):
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_usd")
    e2 = ex.crear("acme", "Dolares", PAISES, "OUTCOME_TRAFFIC", 7, 900.0, "https://t.co/p", "USD")
    ep = ex.agregar_pieza("acme", e2, clon, "CO")
    ex.snapshot(ep, {"impresiones": 10, "gasto": 500.0, "clics_enlace": 1}, tomado_en="2026-10-01T10:00:00")
    _dia(db, ep, "2026-10-01", impresiones=1000, clics_enlace=10, gasto=100.0)
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert c.monedas == ["COP", "USD"] and c.moneda == "USD"                # la de más gasto del periodo
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["gasto"]["valor"] == 500.0 and k["impresiones"]["valor"] == 1000 and k["cpc"]["valor"] == 10.0
    c = r.cargar("acme", r.Filtro(dias=7, moneda="COP"), AHORA)             # nunca se mezclan monedas en un cociente
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert c.moneda == "COP" and k["gasto"]["valor"] == 80.0 and k["impresiones"]["valor"] == 8000
    assert r.serie(c)["moneda"] == "COP"
    c = r.cargar("acme", r.Filtro(dias=7, moneda="EUR"), AHORA)             # una moneda que no existe: la de más gasto
    assert c.moneda == "USD"
    c = r.cargar("acme", r.Filtro(dias=7, experimento_id=sembrado["e1"]), AHORA)
    assert c.moneda == "COP"                                                 # el experimento elegido manda sobre el gasto


def test_las_monedas_son_las_de_los_experimentos_aunque_no_tengan_piezas(base_temporal):
    """Un borrador sin piezas (o con la última quitada) todavía no tiene filas pieza×snapshot, pero su moneda cuenta:
    el proyecto abre en ella, su tarjeta sale y está en el filtro de experimentos (revisión de R3)."""
    import experimentos as ex
    import resultados as r
    vacio = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert vacio.monedas == [] and vacio.moneda == "USD"                      # sin experimentos: el valor de fábrica
    borrador = ex.crear("acme", "Borrador", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t.co/p", "COP")
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert c.datos.filas == [] and c.monedas == ["COP"] and c.moneda == "COP"        # ya no cae en USD
    assert [t["id"] for t in r.experimentos_tarjetas(c)] == [borrador]
    assert r.experimentos_tarjetas(c)[0]["n_piezas"] == 0 and r.experimentos_tarjetas(c)[0]["valor"] is None
    o = r.contexto("acme", r.Filtro(dias=7), AHORA)["opciones"]
    assert [e["id"] for e in o["experimentos"]] == [borrador] and o["monedas"] == ["COP"]
    # Una moneda pedida que el proyecto no tiene cae en la suya, no en USD.
    assert r.cargar("acme", r.Filtro(dias=7, moneda="EUR"), AHORA).moneda == "COP"
    # Una pieza que se agrega y se quita deja el borrador igual de visible.
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_q")
    ep = ex.agregar_pieza("acme", borrador, clon, "CO")
    assert [t["n_piezas"] for t in r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7), AHORA))] == [1]
    ex.quitar_pieza("acme", borrador, ep)
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert c.datos.filas == [] and c.moneda == "COP" and [t["id"] for t in r.experimentos_tarjetas(c)] == [borrador]
    # Otro proyecto no se mezcla.
    assert r.cargar("otro", r.Filtro(dias=7), AHORA).monedas == []


def test_un_borrador_sin_piezas_en_otra_moneda_no_cambia_la_moneda_con_datos(sembrado):
    """«Uno» (COP, con gasto) + un borrador en USD sin piezas: la moneda por defecto sigue siendo la que tiene
    datos (COP); la del borrador se ofrece y, pedida o con su experimento elegido, es la que se muestra."""
    import experimentos as ex
    import resultados as r
    borrador = ex.crear("acme", "Borrador USD", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t.co/p", "USD")
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert c.monedas == ["COP", "USD"] and c.moneda == "COP"
    assert [t["nombre"] for t in r.experimentos_tarjetas(c)] == ["Uno"]
    o = r.contexto("acme", r.Filtro(dias=7), AHORA)["opciones"]
    assert [e["nombre"] for e in o["experimentos"]] == ["Uno"] and o["monedas"] == ["COP", "USD"]
    c = r.cargar("acme", r.Filtro(dias=7, moneda="USD"), AHORA)
    assert c.moneda == "USD" and [t["id"] for t in r.experimentos_tarjetas(c)] == [borrador]
    assert [e["id"] for e in r.contexto("acme", r.Filtro(dias=7, moneda="USD"), AHORA)["opciones"]["experimentos"]] == [borrador]
    # Con el borrador elegido y sin moneda pedida, manda su moneda aunque no tenga filas que midan gasto.
    c = r.cargar("acme", r.Filtro(dias=7, experimento_id=borrador), AHORA)
    assert c.moneda == "USD" and [t["seleccionado"] for t in r.experimentos_tarjetas(c)] == [True]
    # Un experimento elegido que no existe en el proyecto (o es de otro) no mueve la moneda.
    assert r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA).moneda == "COP"


def test_con_filas_en_una_moneda_y_sin_gasto_gana_la_de_las_filas(base_temporal):
    """Sin gasto en ninguna parte, la moneda por defecto es la de las piezas (empate: orden alfabético), no la de un
    borrador sin piezas que sale antes en el abecedario."""
    import experimentos as ex
    import resultados as r
    ex.crear("acme", "Borrador COP", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t.co/p", "COP")
    dolares = ex.crear("acme", "Dolares", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t.co/p", "USD")
    ex.agregar_pieza("acme", dolares, _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_d"), "CO")
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert c.monedas == ["COP", "USD"] and c.moneda == "USD"


def test_marcas_solo_las_del_proyecto_y_del_periodo(sembrado):
    import resultados as r
    db, e1 = sembrado["db"], sembrado["e1"]
    _evento(db, "acme", e1, "veredicto", "Veredicto uno", "2026-10-01T09:00:00")
    _evento(db, "acme", e1, "tope", "Tope dos", "2026-09-30T08:00:00")
    _evento(db, "acme", e1, "accion", "Muy viejo", "2026-09-01T08:00:00")           # fuera del periodo
    _evento(db, "acme", e1, "lanzado", "Tipo que no se marca", "2026-10-01T10:00:00")
    _evento(db, "otro", e1, "accion", "Evento de otro proyecto", "2026-10-01T11:00:00")
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert [m["texto"] for m in r.marcas(c)] == ["Tope dos", "Veredicto uno"]
    assert [m["dia"] for m in r.marcas(c)] == ["2026-09-30", "2026-10-01"]
    assert r.marcas(r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA)) == []
    for i in range(15):
        _evento(db, "acme", e1, "accion", "x" * 300, f"2026-10-02T{i:02d}:00:00")
    marcas = r.marcas(c)
    assert len(marcas) == 12 and all(len(m["texto"]) <= 140 for m in marcas)
    assert [m["dia"] for m in marcas] == sorted(m["dia"] for m in marcas)


def test_serie_respeta_el_filtro(sembrado):
    import resultados as r
    s = r.serie(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))
    assert s["gasto"][-1] == pytest.approx(10.0) and sum(s["gasto"]) == pytest.approx(40.0)
    assert s["ctr"][-1] == pytest.approx(13 / 1000 * 100) and s["gancho"][-1] is None      # la imagen no tiene gancho
    assert s["roas"][-1] == pytest.approx(30.0 / 10.0) and s["frecuencia"][-1] == pytest.approx(1.2)


def test_etiquetas_y_numeros_en_el_idioma_de_quien_mira(sembrado):
    import idiomas
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    with idiomas.en_idioma("en"):
        k = {i["clave"]: i["etiqueta"] for i in r.indicadores(c)}
        assert r.cambio(10.0, 8.0, "baja", "dinero")["texto"] == "+25.0%"
    assert k["ctr"] == "Link CTR" and k["gasto"] == "Spend" and k["cpa"] == "Cost per purchase"
    assert {i["clave"]: i["etiqueta"] for i in r.indicadores(c)}["ctr"] == "CTR del enlace"
    assert r.cambio(10.0, 8.0, "baja", "dinero")["texto"] == "+25,0%"


def test_desde_el_inicio_suma_todo_el_historial_del_detalle(sembrado):
    """El tope de 180 días solo recorta lo que se dibuja: los indicadores de metrica_dia cubren la misma ventana
    que el dinero (todo el historial)."""
    import experimentos as ex
    import resultados as r
    db, ep = sembrado["db"], sembrado["ep_v"]
    ex.snapshot(ep, {"impresiones": 100, "gasto": 1.0, "clics_enlace": 10}, tomado_en="2025-01-15T12:00:00")
    _dia(db, ep, "2025-01-15", impresiones=1000, clics_enlace=100, gasto=5.0, vistas_3s=500)
    c = r.cargar("acme", r.Filtro(dias=0), AHORA)
    assert c.per["n"] == r.DIAS_MAX_INICIO and c.per["lista"][0] == date(2026, 4, 6)
    assert len(c.dias_act) == 9 and c.dias_ant == []
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["impresiones"]["valor"] == 9000
    assert k["ctr"]["valor"] == pytest.approx((132 + 100) / 9000 * 100)
    assert k["gancho"]["valor"] == pytest.approx((1200 + 500) / 5000 * 100)
    assert k["cpc"]["valor"] == pytest.approx(85.0 / 232)
    assert k["gasto"]["valor"] == 80.0                                  # el dinero: la misma ventana (todo)
    assert all(i["cambio"] is None for i in k.values())
    s = r.serie(c)
    assert len(s["dias"]) == 180 and s["dias"][0] == "2026-04-06"       # lo dibujado sí queda en 180 días
    assert s["ctr"][:-4] == [None] * 176 and s["ctr"][-1] == pytest.approx((23 + 13) / 2000 * 100)   # sin el 2025
    assert all(len(i["tendencia"]) == 14 for i in k.values())
    assert k["impresiones"]["tendencia"][:-4] == [None] * 10            # el 2025 no entra en las curvas
    siete = {i["clave"]: i for i in r.indicadores(r.cargar("acme", r.Filtro(dias=7), AHORA))}
    assert siete["impresiones"]["valor"] == 8000                         # los demás periodos no cambian


# ---- embudo, desgloses y países (tarea 3) ----

def _desglose(db, ep, dimension, clave, **v):
    base = dict(impresiones=100, clics_enlace=2, gasto=0.0, vistas_3s=0, thruplay=0, compras_meta=0, ingresos_meta=0.0)
    base.update(v)
    with db.conectar() as con:
        con.execute(db.metrica_desglose.insert().values(experimento_pieza_id=ep, dimension=dimension, clave=clave,
                                                         actualizado_en=AHORA, **base))


def test_embudo_con_frase_solo_con_dos_experimentos(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert r.promedio_embudo("acme") is None                    # un solo experimento con datos
    e = r.embudo(c, None)
    assert [p["clave"] for p in e["pasos"]] == [x[0] for x in r.PASOS_EMBUDO]
    assert e["pasos"][0]["valor"] == 8000 and e["pasos"][0]["pct"] is None and e["frase"] is None
    assert e["pasos"][3]["pct"] == pytest.approx(16 / e["pasos"][2]["valor"] * 100)


def test_embudo_frase_nombra_la_peor_caida():
    import resultados as r
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 15, "carrito": 1, "pago_iniciado": 1, "compras_meta": 1}
    prom = {"clics_enlace": 2.0, "visitas_pagina": 70.0, "carrito": 12.0, "pago_iniciado": 40.0, "compras_meta": 50.0}
    e = r.embudo_desde_sumas(pasos, prom)
    assert "carrito" in e["frase"].lower() or "Agregaron al carrito" in e["frase"]
    assert e["frase"] == "La caída más grande está en «Agregaron al carrito»: 6,7 % contra 12,0 % de tu promedio."
    p = {x["clave"]: x for x in e["pasos"]}
    assert p["carrito"]["pct"] == pytest.approx(1 / 15 * 100) and p["carrito"]["prom"] == 12.0
    assert p["impresiones"]["prom"] is None and p["impresiones"]["pct"] is None


def test_embudo_sin_pixel_se_apaga_y_no_se_nombra_como_caida():
    import resultados as r
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 15, "carrito": 0, "pago_iniciado": 0, "compras_meta": 0}
    prom = {"clics_enlace": 2.0, "visitas_pagina": 70.0, "carrito": 12.0, "pago_iniciado": 40.0, "compras_meta": 50.0}
    e = r.embudo_desde_sumas(pasos, prom)
    p = {x["clave"]: x for x in e["pasos"]}
    assert p["carrito"]["sin_datos"] is True                    # 0 con visitas antes: el Pixel no lo mide
    assert p["pago_iniciado"]["sin_datos"] is False and p["pago_iniciado"]["pct"] is None   # anterior 0: nada que dividir
    assert p["clics_enlace"]["sin_datos"] is False and p["visitas_pagina"]["sin_datos"] is False
    # Lo sin Pixel no es «la peor caída», y con pasos sin medir tampoco se dice que «todos» están bien (revisión
    # final de E2): lo medido está en su promedio, pero no hay frase.
    assert e["frase"] is None


def test_embudo_sin_pixel_tampoco_cuenta_las_visitas():
    """I2 (revisión final de E2): las visitas a la página también las cuenta el Pixel. Sin él llegan en 0 después de
    los clics; antes la frase decía «La caída más grande está en «Visitas a la página»: 0 % contra 60 %»."""
    import resultados as r
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 0, "carrito": 0, "pago_iniciado": 0, "compras_meta": 0}
    prom = {"clics_enlace": 2.0, "visitas_pagina": 60.0, "carrito": 12.0, "pago_iniciado": 40.0, "compras_meta": 50.0}
    e = r.embudo_desde_sumas(pasos, prom)
    p = {x["clave"]: x for x in e["pasos"]}
    assert p["visitas_pagina"]["sin_datos"] is True and p["clics_enlace"]["sin_datos"] is False
    assert e["frase"] is None                                            # los clics están en su promedio
    # con los clics por debajo, la caída se nombra igual: es un paso que Meta sí mide sin Pixel
    e = r.embudo_desde_sumas(pasos, dict(prom, clics_enlace=4.0))
    assert e["frase"] == "La caída más grande está en «Clics en el enlace»: 2,0 % contra 4,0 % de tu promedio."
    assert "Visitas" not in e["frase"]


def test_embudo_sin_promedio_ni_detalle_no_inventa(sembrado):
    import resultados as r
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 15, "carrito": 1, "pago_iniciado": 1, "compras_meta": 1}
    assert r.embudo_desde_sumas(pasos, None)["frase"] is None
    assert all(p["prom"] is None for p in r.embudo_desde_sumas(pasos, None)["pasos"])
    db = sembrado["db"]
    with db.conectar() as con:
        con.execute(db.metrica_dia.delete())
    e = r.embudo(r.cargar("acme", r.Filtro(dias=7), AHORA), {"clics_enlace": 2.0})
    assert [p["valor"] for p in e["pasos"]] == [None] * 6 and e["frase"] is None     # «cargando», no ceros
    assert not any(p["sin_datos"] for p in e["pasos"])


def test_promedio_embudo_es_del_proyecto_y_pide_dos_experimentos(sembrado):
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_dos")
    e2 = ex.crear("acme", "Dos", PAISES, "OUTCOME_TRAFFIC", 7, 1.0, "https://t.co/p", "COP")
    ep = ex.agregar_pieza("acme", e2, clon, "CO")
    assert r.promedio_embudo("acme") is None                    # e2 todavía sin impresiones
    _dia(db, ep, "2026-10-01", impresiones=1000, clics_enlace=10, visitas_pagina=5, carrito=2, pago_iniciado=1,
         compras_meta=1)
    p = r.promedio_embudo("acme")
    # e1 suma 8000 / 132 / 60 / 16 / 8 / 8 y e2 1000 / 10 / 5 / 2 / 1 / 1: nada del experimento de «otro»
    assert set(p) == {"clics_enlace", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta"}
    assert p["clics_enlace"] == pytest.approx(142 / 9000 * 100) and p["visitas_pagina"] == pytest.approx(65 / 142 * 100)
    assert p["carrito"] == pytest.approx(18 / 65 * 100) and p["pago_iniciado"] == pytest.approx(9 / 18 * 100)
    assert p["compras_meta"] == pytest.approx(100.0)
    assert r.promedio_embudo("otro") is None and r.promedio_embudo("nadie") is None


def test_embudo_contra_el_promedio_en_una_carga_real(sembrado):
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_dos")
    e2 = ex.crear("acme", "Dos", PAISES, "OUTCOME_TRAFFIC", 7, 1.0, "https://t.co/p", "COP")
    ep = ex.agregar_pieza("acme", e2, clon, "CO")
    _dia(db, ep, "2026-10-01", impresiones=1000, clics_enlace=10, visitas_pagina=5, carrito=2, pago_iniciado=1,
         compras_meta=1)
    prom = r.promedio_embudo("acme")
    uno = r.embudo(r.cargar("acme", r.Filtro(dias=7, experimento_id=sembrado["e1"]), AHORA), prom)
    assert {p["clave"]: p["prom"] for p in uno["pasos"]}["clics_enlace"] == pytest.approx(142 / 9000 * 100)
    assert uno["frase"] == "Todos los pasos están en tu promedio o mejor."           # e1 pesa casi todo el promedio
    dos = r.embudo(r.cargar("acme", r.Filtro(dias=7, experimento_id=e2), AHORA), prom)
    assert dos["pasos"][0]["valor"] == 1000 and dos["pasos"][1]["pct"] == pytest.approx(1.0)
    assert dos["frase"] == "La caída más grande está en «Clics en el enlace»: 1,0 % contra 1,6 % de tu promedio."
    todo = r.embudo(r.cargar("acme", r.Filtro(dias=7), AHORA), None)
    assert todo["frase"] is None and todo["pasos"][0]["valor"] == 9000        # sin promedio, sin frase


def test_embudo_en_ingles():
    import idiomas
    import resultados as r
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 15, "carrito": 1, "pago_iniciado": 1, "compras_meta": 1}
    prom = {"clics_enlace": 2.0, "visitas_pagina": 70.0, "carrito": 12.0, "pago_iniciado": 40.0, "compras_meta": 50.0}
    with idiomas.en_idioma("en"):
        e = r.embudo_desde_sumas(pasos, prom)
        assert e["pasos"][3]["etiqueta"] == "Added to cart"
        assert e["frase"] == "The biggest drop is at “Added to cart”: 6.7 % vs your average of 12.0 %."
        todo = r.embudo_desde_sumas(pasos, {"clics_enlace": 2.0, "visitas_pagina": 70.0})
        assert todo["frase"] == "Every step is at your average or better."


def test_desgloses_suman_solo_lo_del_proyecto(sembrado):
    import resultados as r
    db = sembrado["db"]
    with db.conectar() as con:
        for ep, dim, clave, gasto in ((sembrado["ep_v"], "ubicacion", "instagram|instagram_reels", 30.0),
                                      (sembrado["ep_v"], "ubicacion", "facebook|feed", 10.0),
                                      (sembrado["ep_v"], "edad_genero", "25-34|female", 40.0),
                                      (sembrado["ep_o"], "ubicacion", "instagram|instagram_reels", 999.0)):
            con.execute(db.metrica_desglose.insert().values(experimento_pieza_id=ep, dimension=dim, clave=clave,
                        impresiones=100, clics_enlace=2, gasto=gasto, vistas_3s=0, thruplay=0, compras_meta=0,
                        ingresos_meta=0.0, actualizado_en=AHORA))
    d = r.desgloses(r.cargar("acme", r.Filtro(dias=7), AHORA))
    assert [u["gasto"] for u in d["ubicacion"]] == [30.0, 10.0]
    assert d["ubicacion"][0]["pct_gasto"] == pytest.approx(75.0) and "Reels" in d["ubicacion"][0]["etiqueta"]
    assert d["edad"][0]["clave"] == "25-34" and d["genero"][0]["clave"] == "female" and d["metrica"] == "ctr"


def test_desgloses_edad_genero_dispositivo_region_y_roas(sembrado):
    import resultados as r
    db, ep = sembrado["db"], sembrado["ep_v"]
    _desglose(db, ep, "edad_genero", "25-34|female", gasto=40.0, impresiones=1000, clics_enlace=20, ingresos_meta=120.0)
    _desglose(db, ep, "edad_genero", "25-34|male", gasto=20.0, impresiones=500, clics_enlace=5)
    _desglose(db, ep, "edad_genero", "35-44|female", gasto=10.0, impresiones=200, clics_enlace=2, ingresos_meta=30.0)
    _desglose(db, ep, "edad_genero", "Unknown|unknown", gasto=1.0)
    _desglose(db, ep, "dispositivo", "mobile_app", gasto=50.0)
    _desglose(db, ep, "dispositivo", "desktop", gasto=20.0)
    _desglose(db, ep, "dispositivo", "mobile_web", gasto=5.0)
    for i in range(12):
        _desglose(db, ep, "region", f"Region {i:02d}", gasto=float(i + 1))
    d = r.desgloses(r.cargar("acme", r.Filtro(dias=7), AHORA))
    assert d["metrica"] == "roas"
    assert [(x["clave"], x["gasto"]) for x in d["edad"]] == [("25-34", 60.0), ("35-44", 10.0), ("Unknown", 1.0)]
    primera = d["edad"][0]
    assert primera["impresiones"] == 1500 and primera["ctr"] == pytest.approx(25 / 1500 * 100)
    assert primera["roas"] == pytest.approx(120.0 / 60.0) and primera["pct_gasto"] == pytest.approx(60 / 71 * 100)
    assert d["edad"][2]["etiqueta"] == "Sin dato" and d["edad"][0]["etiqueta"] == "25-34"
    assert [(x["clave"], x["etiqueta"]) for x in d["genero"]] == [("female", "Mujeres"), ("male", "Hombres"),
                                                                    ("unknown", "Sin dato")]
    assert [x["etiqueta"] for x in d["dispositivo"]] == ["Celular (app)", "Computador", "Celular (web)"]
    assert len(d["region"]) == 10 and d["region"][0]["clave"] == "Region 11" and d["region"][0]["etiqueta"] == "Region 11"
    assert d["region"][0]["pct_gasto"] == pytest.approx(12 / 78 * 100)       # la parte sobre TODAS las regiones
    assert d["ubicacion"] == []                                              # sin datos: lista vacía, no error


def test_desgloses_etiquetas_de_ubicacion(sembrado):
    import resultados as r
    db, ep = sembrado["db"], sembrado["ep_v"]
    for i, clave in enumerate(("facebook|feed", "instagram|instagram_reels", "instagram|instagram_stories",
                               "facebook|facebook_stories", "instagram|instagram_explore", "facebook|marketplace",
                               "facebook|video_feeds", "facebook|instream_video", "facebook|search",
                               "facebook|right_hand_column", "audience_network|an_classic", "messenger|messenger_inbox",
                               "threads|threads_stream", "instagram|", "|feed")):
        _desglose(db, ep, "ubicacion", clave, gasto=float(100 - i))
    d = r.desgloses(r.cargar("acme", r.Filtro(dias=7), AHORA))
    et = {u["clave"]: u["etiqueta"] for u in d["ubicacion"]}
    assert et["facebook|feed"] == "Facebook · Feed" and et["instagram|instagram_reels"] == "Instagram · Reels"
    assert et["instagram|instagram_stories"] == "Instagram · Historias" and et["facebook|facebook_stories"] == "Facebook · Historias"
    assert et["instagram|instagram_explore"] == "Instagram · Explorar" and et["facebook|marketplace"] == "Facebook · Marketplace"
    assert et["facebook|video_feeds"] == "Facebook · Videos" and et["facebook|instream_video"] == "Facebook · En el video"
    assert et["facebook|search"] == "Facebook · Búsqueda" and et["facebook|right_hand_column"] == "Facebook · Columna derecha"
    assert et["audience_network|an_classic"] == "Audience Network · an classic"          # sin regla: la clave con espacios
    assert et["messenger|messenger_inbox"] == "Messenger · messenger inbox" and et["threads|threads_stream"] == "Threads · threads stream"
    assert et["instagram|"] == "Instagram" and et["|feed"] == "Feed"


def test_desgloses_respetan_el_filtro_y_el_idioma(sembrado):
    import idiomas
    import resultados as r
    db = sembrado["db"]
    _desglose(db, sembrado["ep_v"], "ubicacion", "instagram|instagram_reels", gasto=30.0)
    _desglose(db, sembrado["ep_i"], "ubicacion", "facebook|feed", gasto=7.0)
    _desglose(db, sembrado["ep_i"], "edad_genero", "25-34|female", gasto=7.0)
    solo_mx = r.desgloses(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))
    assert [u["clave"] for u in solo_mx["ubicacion"]] == ["facebook|feed"] and solo_mx["ubicacion"][0]["pct_gasto"] == 100.0
    nada = r.desgloses(r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA))
    assert nada == {"ubicacion": [], "edad": [], "genero": [], "dispositivo": [], "region": [], "metrica": "ctr"}
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    with idiomas.en_idioma("en"):
        d = r.desgloses(c)
        assert d["genero"][0]["etiqueta"] == "Women"
        assert [u["etiqueta"] for u in d["ubicacion"]] == ["Instagram · Reels", "Facebook · Feed"]
    assert r.desgloses(c)["genero"][0]["etiqueta"] == "Mujeres"


def test_paises(sembrado):
    import resultados as r
    p = {x["pais"]: x for x in r.paises(r.cargar("acme", r.Filtro(dias=7), AHORA))}
    assert set(p) == {"CO", "MX"} and p["CO"]["impresiones"] == 4000 and p["CO"]["gasto"] == 40.0


def test_paises_dinero_del_motor_y_detalle_de_meta(sembrado):
    import resultados as r
    lista = r.paises(r.cargar("acme", r.Filtro(dias=7), AHORA))
    assert [x["pais"] for x in lista] == ["CO", "MX"]                      # mismo gasto: por código
    co = lista[0]
    assert set(co) == {"pais", "impresiones", "clics_enlace", "gasto", "ctr", "roas"}
    assert co["clics_enlace"] == 86 and co["ctr"] == pytest.approx(86 / 4000 * 100)      # metrica_dia
    assert co["roas"] == pytest.approx(120.0 / 40.0)                                      # el motor (snapshots)
    assert lista[1]["clics_enlace"] == 46 and lista[1]["ctr"] == pytest.approx(46 / 4000 * 100)
    una = r.paises(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))
    assert [x["pais"] for x in una] == ["MX"] and una[0]["gasto"] == 40.0
    assert r.paises(r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA)) == []
    todo = {x["pais"]: x for x in r.paises(r.cargar("acme", r.Filtro(dias=0), AHORA))}
    assert todo["CO"]["gasto"] == 40.0 and todo["CO"]["impresiones"] == 4000


def test_paises_desde_el_inicio_cuentan_todo_el_historial(sembrado):
    """Con un snapshot de 2025 (fuera de los 180 días que se dibujan) el gasto sigue siendo todo el historial,
    la misma ventana de los indicadores."""
    import experimentos as ex
    import resultados as r
    ex.snapshot(sembrado["ep_v"], {"impresiones": 100, "gasto": 1.0, "clics_enlace": 10}, tomado_en="2025-01-15T12:00:00")
    c = r.cargar("acme", r.Filtro(dias=0), AHORA)
    gasto = {i["clave"]: i for i in r.indicadores(c)}["gasto"]["valor"]
    p = {x["pais"]: x for x in r.paises(c)}
    assert p["CO"]["gasto"] == 40.0 and p["MX"]["gasto"] == 40.0 and gasto == 80.0 == p["CO"]["gasto"] + p["MX"]["gasto"]


def test_paises_sin_gasto_ni_detalle_no_inventan(sembrado):
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_br")
    e2 = ex.crear("acme", "Brasil", [{"pais": "BR", "idioma": "pt", "presupuesto_dia": 10.0}], "OUTCOME_TRAFFIC", 7,
                  1.0, "https://t.co/p", "COP")
    ex.agregar_pieza("acme", e2, clon, "BR")
    p = {x["pais"]: x for x in r.paises(r.cargar("acme", r.Filtro(dias=7), AHORA))}
    assert p["BR"]["gasto"] == 0.0 and p["BR"]["roas"] is None             # nunca un ROAS de 0 contra 0
    assert p["BR"]["impresiones"] is None and p["BR"]["ctr"] is None and p["BR"]["clics_enlace"] is None   # «cargando»
    assert list(p)[-1] == "BR"                                              # ordenado por gasto


# ---- piezas, historia, tarjetas, detalle y contexto (tarea 4) ----

def test_tendencia():
    import resultados as r
    assert r.tendencia([1.0, 1.1, 1.3, 1.5, 1.7]) == "sube"
    assert r.tendencia([2.0, 1.8, 1.5, 1.2, 1.0]) == "baja"
    assert r.tendencia([1.0, 1.02, 0.99, 1.01, 1.0]) == "estable"
    assert r.tendencia([1.0, None]) is None


def test_tendencia_bordes():
    import resultados as r
    assert r.tendencia([None, 1.0, None, 1.5, 2.0]) == "sube"            # solo cuentan los que tienen dato
    assert r.tendencia([9.0, 9.0, 1.0, 1.0, 1.0, 1.0, 1.0]) == "estable"  # los últimos 5 con dato
    assert r.tendencia([1.0, 2.0, 3.0, None, None]) == "sube" and r.tendencia([]) is None
    assert r.tendencia([1.0, 1.0, 1.1]) == "estable"                      # exactamente +10 % no es «sube»
    assert r.tendencia([0.0, 0.0, 0.0]) == "estable" and r.tendencia([0.0, 0.0, 2.0]) == "sube"


def test_faltan_impresiones_y_horas(sembrado):
    import experimentos as ex
    import resultados as r
    from decisor import REGLAS_DEFECTO
    e = ex.obtener("acme", sembrado["e1"])
    pz = dict(e["piezas"][0], veredicto="pendiente", metricas={"impresiones": 620, "gasto": 1.0})
    assert r.faltan(pz, e, REGLAS_DEFECTO, AHORA) == {"impresiones": 380}
    pz2 = dict(pz, metricas={"impresiones": 5000, "gasto": 1.0})
    e2 = dict(e, extra={"activado_en": "2026-10-02T00:00:00"})
    assert r.faltan(pz2, e2, REGLAS_DEFECTO, AHORA) == {"horas": 36}
    assert r.faltan(dict(pz, veredicto="ganador"), e, REGLAS_DEFECTO, AHORA) is None


def test_faltan_sigue_la_evidencia_del_decisor(sembrado):
    """Las dos vías del decisor (impresiones + gasto, o la ventana de horas con impresiones) y sus bordes."""
    import experimentos as ex
    import resultados as r
    from decisor import REGLAS_DEFECTO
    e = dict(ex.obtener("acme", sembrado["e1"]), extra={"activado_en": "2026-10-02T00:00:00"})
    base = dict(e["piezas"][0], veredicto="pendiente")                        # país CO: presupuesto diario 20 000
    # vía 1: impresiones ≥ 1 000 y gasto ≥ 2 × 20 000
    assert r.faltan(dict(base, metricas={"impresiones": 1000, "gasto": 40000.0}), e, REGLAS_DEFECTO, AHORA) is None
    assert r.faltan(dict(base, metricas={"impresiones": 1000, "gasto": 39999.0}), e, REGLAS_DEFECTO, AHORA) == {"horas": 36}
    # vía 2: la ventana de 48 h cumplida con impresiones
    tarde = dict(e, extra={"activado_en": "2026-09-30T12:00:00"})
    assert r.faltan(dict(base, metricas={"impresiones": 1500, "gasto": 1.0}), tarde, REGLAS_DEFECTO, AHORA) is None
    assert r.faltan(dict(base, metricas={"impresiones": 0, "gasto": 0.0}), tarde, REGLAS_DEFECTO, AHORA) == {"impresiones": 1000}
    # reglas propias: ventana de 24 h y 5 000 impresiones
    reglas = dict(REGLAS_DEFECTO, ventana_horas=24, impresiones_min=5000)
    assert r.faltan(dict(base, metricas={"impresiones": 4200, "gasto": 1.0}), e, reglas, AHORA) == {"impresiones": 800}
    assert r.faltan(dict(base, metricas={"impresiones": 5200, "gasto": 1.0}), e, reglas, AHORA) == {"horas": 12}
    # sin gasto de referencia (país sin presupuesto) el gasto mínimo es 0, como en el decisor
    sin_presupuesto = dict(e, paises=[{"pais": "CO", "presupuesto_dia": 0}])
    assert r.faltan(dict(base, metricas={"impresiones": 1000, "gasto": 0.0}), sin_presupuesto, REGLAS_DEFECTO, AHORA) is None
    # sin cuándo se activó no se inventan horas
    assert r.faltan(dict(base, metricas={"impresiones": 5000, "gasto": 1.0}), dict(e, extra={}), REGLAS_DEFECTO, AHORA) is None
    # la fecha de la pieza (la que lee el decisor) manda sobre la del experimento
    con_pieza = dict(base, metricas={"impresiones": 5000, "gasto": 1.0}, extra={"activado_en": "2026-10-02T06:00:00"})
    assert r.faltan(con_pieza, e, REGLAS_DEFECTO, AHORA) == {"horas": 42}
    # una hora a medias cuenta como hora entera que falta (19,5 h de 48 → 29)
    media = dict(base, metricas={"impresiones": 5000, "gasto": 1.0}, extra={"activado_en": "2026-10-01T16:30:00"})
    assert r.faltan(media, e, REGLAS_DEFECTO, AHORA) == {"horas": 29}


def test_historia_fatiga_gancho_y_promedio():
    import resultados as r
    h = r.historia(serie=[2.0, 1.8, 1.5, 1.2, 1.0], promedio=[1.0] * 5, frecuencia=3.1, gancho=18.0, es_imagen=False,
                   faltan=None, escalon=0, causas=[], tramos=[])
    texto = " · ".join(h)
    assert "fatiga" in texto and "18" in texto and "baja" in texto


def test_historia_frases_en_su_orden():
    import idiomas
    import resultados as r
    tramos = [("pendiente", "2026-09-28T10:00:00"), ("perdedor", "2026-09-30T08:00:00")]
    h = r.historia(tramos=tramos, serie=[2.0, 1.8, 1.5, 1.2, 1.0], promedio=[1.0] * 5, frecuencia=3.1, gancho=18.0,
                   es_imagen=False, faltan={"horas": 12}, escalon=2, causas=["gancho", "repeticion"])
    assert h[0] == (f"Aprendiendo desde el {idiomas.fecha_corta(date(2026, 9, 28))} → "
                    f"Perdiendo desde el {idiomas.fecha_corta(date(2026, 9, 30))}")
    assert h[1:] == ["1,5× el promedio", "baja", "fatiga: frecuencia 3,1", "el gancho no detiene: 18 %",
                     "12 h más para que el motor decida", "rescate 2/3",
                     "posibles causas: el gancho no retiene, repetición: ya lo vieron"]


def test_historia_no_dice_lo_que_no_aplica():
    import resultados as r
    estable = [1.0] * 5
    assert r.historia(serie=estable, promedio=estable) == ["estable"]                   # ni 1,0× ni fatiga ni nada
    assert r.historia(serie=[1.0, 1.0], promedio=[1.0, 1.0]) == []                      # menos de 3 días: sin tendencia
    # una imagen no tiene gancho; con la métrica estable no hay fatiga aunque la frecuencia sea alta
    assert r.historia(serie=estable, promedio=estable, frecuencia=4.0, gancho=5.0, es_imagen=True) == ["estable"]
    assert r.historia(serie=estable, promedio=estable, frecuencia=2.5, gancho=25.0) == ["estable"]    # los bordes no cuentan
    assert r.historia(serie=[], promedio=[], faltan={"impresiones": 380}) == [
        "le faltan 380 impresiones para que el motor decida"]
    assert r.historia(serie=[1.2, 1.2, 1.2, 1.2, 1.2], promedio=[1.0] * 5)[0] == "1,2× el promedio"
    assert r.historia(serie=[0.8] * 5, promedio=[1.0] * 5)[0] == "0,8× el promedio"
    assert r.historia(serie=[None, 3.0, None, 3.0, 3.0], promedio=[1.0, 1.0, 1.0, 1.0, None])[0] == "3,0× el promedio"
    assert r.historia(tramos=[("ganador", None)])[0] == "Ganadora"                         # sin fecha, solo el nombre


def test_historia_en_ingles():
    import idiomas
    import resultados as r
    with idiomas.en_idioma("en"):
        h = r.historia(serie=[2.0, 1.8, 1.5, 1.2, 1.0], promedio=[1.0] * 5, frecuencia=3.1, gancho=18.0,
                       faltan={"impresiones": 1380}, escalon=1, causas=["gancho"], tramos=[("perdedor", None)])
    assert h == ["Losing", "1.5× the average", "down", "fatigue: frequency 3.1", "the hook isn't stopping people: 18 %",
                 "1,380 impressions to go before the engine decides", "rescue 1/3", "likely causes: the hook doesn't hold attention"]


def test_piezas_ranking_veredicto_y_aislamiento(sembrado):
    import experimentos as ex
    import resultados as r
    ex.actualizar_pieza("acme", sembrado["ep_v"], veredicto="ganador")
    ps = r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})
    assert {p["ep_id"] for p in ps} == {sembrado["ep_v"], sembrado["ep_i"]}
    v = [p for p in ps if p["ep_id"] == sembrado["ep_v"]][0]
    assert v["veredicto"]["etiqueta"] == "Ganadora" and v["metrica"] == "ctr" and len(v["serie"]) == 7
    assert v["gancho"] == pytest.approx(30.0) and [p for p in ps if p["es_imagen"]][0]["gancho"] is None


def test_piezas_campos_serie_y_promedio_del_experimento(sembrado):
    import resultados as r
    ps = r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})
    v, i = ps                                           # mismo gasto: por id (la de video se creó antes)
    assert v["ep_id"] == sembrado["ep_v"] and v["experimento_id"] == sembrado["e1"] and v["pais"] == "CO"
    assert v["nombre"] == "cf_1" and v["es_imagen"] is False and v["url_video"] == "https://r2/f.mp4"
    assert i["es_imagen"] is True and i["pais"] == "MX"
    assert v["gasto"] == pytest.approx(40.0) and v["compras"] == 4 and v["roas"] == pytest.approx(3.0)
    assert v["ctr"] == pytest.approx(86 / 4000 * 100) and v["cpc"] == pytest.approx(40.0 / 86)
    assert i["ctr"] == pytest.approx(46 / 4000 * 100)
    assert v["serie"][:3] == [None] * 3 and v["serie"][3:] == pytest.approx([2.0, 2.1, 2.2, 2.3])
    assert i["serie"][3:] == pytest.approx([1.0, 1.1, 1.2, 1.3])
    # el promedio es el del experimento (las dos piezas juntas), la misma línea para las dos
    assert v["promedio"][3:] == pytest.approx([1.5, 1.6, 1.7, 1.8]) and v["promedio"] == i["promedio"]
    assert v["delta_roas"] is None                       # el periodo anterior no tuvo gasto
    assert v["veredicto"] == {"etiqueta": "Aprendiendo", "clase": "aprendiendo"}
    assert v["historia"][0] == "1,3× el promedio"        # 8,6 contra 6,6 de promedio los mismos 4 días


def test_piezas_ordenadas_por_gasto_y_sin_otro_proyecto(sembrado):
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_gasta_mas")
    ep = ex.agregar_pieza("acme", sembrado["e1"], clon, "CO")
    ex.snapshot(ep, {"impresiones": 500, "gasto": 100.0, "clics_enlace": 5}, tomado_en="2026-10-02T10:00:00")
    ps = r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})
    assert [p["ep_id"] for p in ps] == [ep, sembrado["ep_v"], sembrado["ep_i"]]
    assert sembrado["ep_o"] not in {p["ep_id"] for p in ps}
    assert ps[0]["ctr"] is None and ps[0]["serie"] == [None] * 7          # sin detalle de Meta: «cargando», no ceros
    uno = r.piezas(r.cargar("acme", r.Filtro(dias=7, ep_id=sembrado["ep_v"]), AHORA), {})
    assert [p["ep_id"] for p in uno] == [sembrado["ep_v"]]
    # filtrada a una pieza, la línea del experimento sigue siendo la de TODO el experimento
    assert uno[0]["promedio"][3:] == pytest.approx([1.5, 1.6, 1.7, 1.8])


def _experimento_de_ventas(sembrado, tope=1000.0):
    import experimentos as ex
    from tests.test_experimentos_db import PAISES as P
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_ventas")
    e2 = ex.crear("acme", "Ventas", P, "OUTCOME_SALES", 7, tope, "https://t.co/p", "COP")
    ep = ex.agregar_pieza("acme", e2, clon, "CO")
    for f, gasto, ing in (("2026-09-28T12:00:00", 5.0, 5.0), ("2026-09-30T23:00:00", 10.0, 20.0),
                          ("2026-10-01T23:00:00", 20.0, 60.0), ("2026-10-02T11:00:00", 30.0, 90.0)):
        ex.snapshot(ep, {"impresiones": 1000, "gasto": gasto, "clics_enlace": 10, "compras": 1, "ingresos": ing,
                         "fuente_ventas": "meta"}, tomado_en=f)
    return e2, ep


def test_metrica_principal_roas_con_objetivo_de_ventas(sembrado):
    import resultados as r
    e2, ep = _experimento_de_ventas(sembrado)
    c = r.cargar("acme", r.Filtro(dias=3, experimento_id=e2), AHORA)
    p = r.piezas(c, {})[0]
    assert p["metrica"] == "roas" and p["serie"] == pytest.approx([3.0, 4.0, 3.0])      # 30-sep, 1-oct, 2-oct
    assert p["promedio"] == pytest.approx([3.0, 4.0, 3.0])                               # él solo es el experimento
    assert p["gasto"] == pytest.approx(25.0) and p["roas"] == pytest.approx(85.0 / 25.0)
    assert p["delta_roas"] == pytest.approx(85.0 / 25.0 - 1.0)                           # contra 27..29-sep (5 / 5)
    todo = r.cargar("acme", r.Filtro(dias=0, experimento_id=e2), AHORA)
    assert r.piezas(todo, {})[0]["delta_roas"] is None                                   # «desde el inicio» no compara


def test_veredictos_con_nombre_humano_y_recuperandose(sembrado):
    import experimentos as ex
    import resultados as r
    ep_v, ep_i = sembrado["ep_v"], sembrado["ep_i"]
    c = lambda: {p["ep_id"]: p["veredicto"] for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})}   # noqa: E731
    ex.actualizar_pieza("acme", ep_v, veredicto="perdedor")
    ex.actualizar_pieza("acme", ep_i, veredicto="inconcluso")
    assert c()[ep_v] == {"etiqueta": "Perdiendo", "clase": "perdiendo"}
    assert c()[ep_i] == {"etiqueta": "Sin diferencia clara", "clase": "neutra"}
    ex.actualizar_pieza("acme", ep_v, escalon_rescate=2)                       # en rescate y no ganadora
    assert c()[ep_v] == {"etiqueta": "Recuperándose", "clase": "recuperandose"}
    ex.actualizar_pieza("acme", ep_v, veredicto="ganador")                     # una ganadora sigue siendo ganadora
    assert c()[ep_v] == {"etiqueta": "Ganadora", "clase": "ganadora"}
    ex.actualizar_pieza("acme", ep_v, veredicto="algo raro", escalon_rescate=0)
    assert c()[ep_v] == {"etiqueta": "Aprendiendo", "clase": "aprendiendo"}


def test_historia_de_la_pieza_con_tramos_rescate_y_causas(sembrado):
    import experimentos as ex
    import resultados as r
    db, e1, ep_v = sembrado["db"], sembrado["e1"], sembrado["ep_v"]
    ex.marcar_pieza("acme", ep_v, activado_en="2026-09-29T10:00:00",
                    diagnostico={"causas": [{"codigo": "gancho", "detalle": "d", "evidencia": "e"},
                                            {"codigo": "no_existe"}], "siguiente": {"que": "gancho", "porque": "p"}})
    ex.actualizar_pieza("acme", ep_v, veredicto="perdedor", escalon_rescate=1)
    _evento(db, "acme", e1, "veredicto", "uno", "2026-10-01T09:00:00", ep_id=ep_v, datos={"veredicto": "perdedor"})
    _evento(db, "acme", e1, "veredicto", "repetido", "2026-10-01T09:05:00", ep_id=ep_v, datos={"veredicto": "perdedor"})
    _evento(db, "acme", e1, "veredicto", "de otra pieza", "2026-09-30T09:00:00", ep_id=sembrado["ep_i"],
            datos={"veredicto": "ganador"})
    _evento(db, "otro", e1, "veredicto", "de otro proyecto", "2026-09-30T10:00:00", ep_id=ep_v,
            datos={"veredicto": "ganador"})
    _evento(db, "acme", e1, "accion", "no es un veredicto", "2026-09-30T11:00:00", ep_id=ep_v, datos={"veredicto": "ganador"})
    p = [x for x in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {}) if x["ep_id"] == ep_v][0]
    h = p["historia"]
    assert h[0].startswith("Aprendiendo desde el ") and h[0].count("→") == 1 and "Perdiendo desde el " in h[0]
    assert "Ganadora" not in " ".join(h)
    assert "rescate 1/3" in h and h[-1] == "posibles causas: el gancho no retiene"
    assert p["veredicto"]["clase"] == "recuperandose"


def test_historia_le_faltan_solo_si_el_motor_la_esta_juzgando(sembrado):
    import experimentos as ex
    import resultados as r
    e1, ep_v = sembrado["e1"], sembrado["ep_v"]
    ex.actualizar(("acme"), e1, estado="corriendo")
    ex.actualizar_pieza("acme", ep_v, estado="activo", meta_ad_id="ad_1")     # el decisor solo mira piezas con anuncio
    ex.actualizar_extra("acme", e1, lambda extra: dict(extra, activado_en="2026-10-02T00:00:00"))
    # 4 000 impresiones y 40 de gasto contra un presupuesto de 20 000: falta la ventana de 48 h (van 12)
    ps = {p["ep_id"]: p for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})}
    assert "36 h más para que el motor decida" in ps[ep_v]["historia"]
    assert not any("motor" in f for f in ps[sembrado["ep_i"]]["historia"])      # la imagen no está activa
    # las reglas del proyecto cuentan: una ventana de 24 h
    ps = {p["ep_id"]: p for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {"ventana_horas": 24})}
    assert "12 h más para que el motor decida" in ps[ep_v]["historia"]
    ex.actualizar(("acme"), e1, estado="pausado")
    ps = {p["ep_id"]: p for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})}
    assert not any("motor" in f for f in ps[ep_v]["historia"])


def test_le_faltan_no_aparece_en_un_anuncio_rechazado_ni_sin_anuncio_en_meta(sembrado):
    """El decisor no evalúa un anuncio DISAPPROVED / WITH_ISSUES ni una pieza sin `meta_ad_id`
    (tareas/experimentos._rechazada_por_meta y el filtro de la pasada): no se le promete que «el motor decida»."""
    import experimentos as ex
    import lanzador
    import resultados as r
    import tablero
    assert tablero.ESTADOS_META_RECHAZO == lanzador.ESTADOS_META_RECHAZO       # la copia local del tablero no se desvía
    e1, ep_v = sembrado["e1"], sembrado["ep_v"]
    ex.actualizar(("acme"), e1, estado="corriendo")
    ex.actualizar_extra("acme", e1, lambda extra: dict(extra, activado_en="2026-10-02T00:00:00"))

    def historia_de_video():
        return [p for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {}) if p["ep_id"] == ep_v][0]["historia"]
    ex.actualizar_pieza("acme", ep_v, estado="activo")                          # activa pero sin anuncio en Meta
    assert not any("motor" in f for f in historia_de_video())
    ex.actualizar_pieza("acme", ep_v, meta_ad_id="ad_1", estado_meta="ACTIVE")  # con anuncio y aprobado: sí se evalúa
    assert "36 h más para que el motor decida" in historia_de_video()
    for rechazo in ("DISAPPROVED", "WITH_ISSUES"):
        ex.actualizar_pieza("acme", ep_v, estado_meta=rechazo)
        assert not any("motor" in f for f in historia_de_video()), rechazo
    ex.actualizar_pieza("acme", ep_v, estado_meta="PENDING_REVIEW")             # en revisión no es un rechazo
    assert "36 h más para que el motor decida" in historia_de_video()


def test_fatiga_usa_la_frecuencia_acumulada_y_no_la_diaria(sembrado):
    """Spec §4.4: la fatiga mira la frecuencia ACUMULADA (el último metrica_snapshot), no la diaria de metrica_dia."""
    import experimentos as ex
    import resultados as r
    db, ep_v = sembrado["db"], sembrado["ep_v"]
    with db.conectar() as con:                                          # el CTR del video va cayendo: 2,3 → 2,0 %
        for fecha, clics in (("2026-09-29", 23), ("2026-09-30", 22), ("2026-10-01", 21), ("2026-10-02", 20)):
            con.execute(db.metrica_dia.update().where(db.metrica_dia.c.experimento_pieza_id == ep_v,
                                                      db.metrica_dia.c.fecha == fecha).values(clics_enlace=clics, frecuencia=4.0))

    def historia_de_video():
        return [p for p in r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {}) if p["ep_id"] == ep_v][0]["historia"]
    assert "baja" in historia_de_video()
    assert not any("fatiga" in f for f in historia_de_video())          # diaria 4,0 pero acumulada 1,5: no hay fatiga
    ex.snapshot(ep_v, {"impresiones": 5000, "gasto": 50.0, "clics_enlace": 100, "frecuencia": 3.0}, tomado_en="2026-10-02T11:30:00")
    assert "fatiga: frecuencia 3,0" in historia_de_video()              # acumulada 3,0 con la métrica cayendo


def test_piezas_leen_los_veredictos_en_una_consulta(sembrado):
    import experimentos as ex
    import resultados as r
    from sqlalchemy import event
    db = sembrado["db"]
    for k in range(6):
        clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_muchas{k}")
        ep = ex.agregar_pieza("acme", sembrado["e1"], clon, "CO")
        _evento(db, "acme", sembrado["e1"], "veredicto", "x", "2026-10-01T09:00:00", ep_id=ep, datos={"veredicto": "ganador"})
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    consultas = []

    def cuenta(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(sa.engine.Engine, "before_cursor_execute", cuenta)
    try:
        r.piezas(c, {})
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", cuenta)
    assert len([q for q in consultas if "FROM evento" in q]) == 1, consultas       # una, no una por pieza
    assert len(consultas) <= 2, consultas                                            # y nada más (todo lo demás ya estaba cargado)


def test_detalle_de_pieza_y_otro_proyecto(sembrado):
    import resultados as r
    d = r.pieza("acme", sembrado["ep_v"], r.Filtro(dias=7), AHORA)
    assert d["curva"][0][0] == "3 s" and d["curva"][0][1] == pytest.approx(30.0)
    assert r.pieza("acme", sembrado["ep_o"], r.Filtro(), AHORA) is None
    assert r.pieza("otro", sembrado["ep_v"], r.Filtro(), AHORA) is None


def test_detalle_de_pieza_completo(sembrado):
    import json
    import experimentos as ex
    import resultados as r
    db, e1, ep_v = sembrado["db"], sembrado["e1"], sembrado["ep_v"]
    ex.marcar_pieza("acme", ep_v, rankings_meta={"calidad": "ABOVE_AVERAGE", "interaccion": None, "conversion": "AVERAGE"},
                    diagnostico={"causas": [{"codigo": "gancho"}], "siguiente": {"que": "gancho"}})
    _evento(db, "acme", e1, "accion", "Se pausó", "2026-10-01T09:00:00", ep_id=ep_v)
    _evento(db, "acme", e1, "accion", "de la imagen", "2026-10-01T10:00:00", ep_id=sembrado["ep_i"])
    _evento(db, "otro", e1, "accion", "ajeno", "2026-10-01T11:00:00", ep_id=ep_v)
    with db.conectar() as con:
        con.execute(db.metrica_dia.update().where(db.metrica_dia.c.experimento_pieza_id == ep_v,
                                                  db.metrica_dia.c.fecha == "2026-10-02").values(p25=500, p50=250, p75=100, p95=50, p100=10))
    # los otros filtros (país, tipo, experimento…) no esconden la pieza que se abre
    d = r.pieza("acme", ep_v, r.Filtro(dias=7, pais="MX", tipo="imagen", experimento_id=999, moneda="USD"), AHORA)
    assert d["ep_id"] == ep_v and d["experimento"] == {"id": e1, "nombre": "Uno"} and d["moneda"] == "COP"
    assert [c[0] for c in d["curva"]] == ["3 s", "25 %", "50 %", "75 %", "95 %", "100 %"]
    assert [c[1] for c in d["curva"]] == pytest.approx([30.0, 12.5, 6.25, 2.5, 1.25, 0.25])      # % de las 4 000 impresiones
    assert d["series"]["dias"][-1] == "2026-10-02" and len(d["series"]["dias"]) == 7
    assert d["series"]["ctr"][3:] == pytest.approx([2.0, 2.1, 2.2, 2.3]) and d["series"]["gancho"][-1] == pytest.approx(30.0)
    assert d["series"]["cpc"][-1] == pytest.approx(10.0 / 23) and d["series"]["frecuencia"][-1] == pytest.approx(1.2)
    assert d["rankings"] == {"calidad": "ABOVE_AVERAGE", "interaccion": None, "conversion": "AVERAGE"}
    assert d["diagnostico"]["causas"][0]["codigo"] == "gancho"
    assert [e["mensaje"] for e in d["eventos"]] == ["Se pausó"] and d["eventos"][0]["tipo"] == "accion"
    assert d["eventos"][0]["creado_en"] == "2026-10-01T09:00:00"
    k = {i["clave"]: i for i in d["indicadores"]}
    assert k["gasto"]["valor"] == 40.0 and k["impresiones"]["valor"] == 4000 and k["gancho"]["valor"] == pytest.approx(30.0)
    assert d["periodo"]["n"] == 7 and "lista" not in d["periodo"]
    assert d["desgloses"]["ubicacion"] == [] and d["desgloses"]["metrica"] == "ctr"
    assert d["promedio"][3:] == pytest.approx([1.5, 1.6, 1.7, 1.8])                  # el del experimento, no el de ella sola
    # lo del panel (R2): la gráfica de la pieza con su gasto, y sus acciones (la pieza de Crear, el país en Meta)
    assert len(d["series"]["gasto"]) == 7 and d["series"]["moneda"] == "COP" and "roas" in d["series"]
    assert d["pieza_id"] and d["estado_experimento"] == ex.obtener("acme", e1)["estado"]
    assert d["pais_experimento"]["pais"] == d["pais"] and set(d["pais_experimento"]) == {"pais", "estado", "meta_adset_id", "presupuesto_dia"}
    json.dumps({k2: d[k2] for k2 in ("curva", "series", "serie", "promedio", "historia", "eventos", "periodo",
                                     "pais_experimento")})


def test_detalle_de_una_imagen_sin_curva_ni_gancho(sembrado):
    import resultados as r
    d = r.pieza("acme", sembrado["ep_i"], r.Filtro(dias=7), AHORA)
    assert d["es_imagen"] is True and d["curva"] == [] and d["gancho"] is None
    assert d["series"]["gancho"] == [None] * 7 and d["rankings"] == {} and d["diagnostico"] is None
    assert d["eventos"] == []


def test_detalle_con_los_desgloses_de_solo_esa_pieza(sembrado):
    import resultados as r
    db = sembrado["db"]
    _desglose(db, sembrado["ep_v"], "ubicacion", "facebook|feed", gasto=30.0)
    _desglose(db, sembrado["ep_i"], "ubicacion", "instagram|instagram_reels", gasto=7.0)
    d = r.pieza("acme", sembrado["ep_v"], r.Filtro(dias=7), AHORA)
    assert [u["clave"] for u in d["desgloses"]["ubicacion"]] == ["facebook|feed"]


def test_detalle_sin_detalle_de_meta_no_inventa_ceros(sembrado):
    import resultados as r
    db = sembrado["db"]
    with db.conectar() as con:
        con.execute(db.metrica_dia.delete())
    d = r.pieza("acme", sembrado["ep_v"], r.Filtro(dias=7), AHORA)
    assert d["curva"] == [] and d["ctr"] is None and d["series"]["ctr"] == [None] * 7 and d["gasto"] == 40.0


def test_tarjetas_de_experimentos(sembrado):
    import experimentos as ex
    import resultados as r
    ex.actualizar_pieza("acme", sembrado["ep_v"], veredicto="ganador")
    ex.actualizar_extra("acme", sembrado["e1"], lambda extra: dict(extra, activado_en="2026-09-30T08:00:00"))
    c = r.cargar("acme", r.Filtro(dias=7, pais="MX", tipo="imagen"), AHORA)          # el filtro no toca las tarjetas
    t = r.experimentos_tarjetas(c)
    assert [x["nombre"] for x in t] == ["Uno"]                                           # nada de «otro»
    u = t[0]
    assert u["id"] == sembrado["e1"] and u["estado"] == "armando" and u["n_piezas"] == 2 and u["dias"] == 14
    assert u["paises"] == ["CO", "MX"] and u["ganadoras"] == 1 and u["seleccionado"] is False
    assert u["gasto"] == pytest.approx(80.0) and u["tope"] == 500000.0 and u["pct_tope"] == pytest.approx(80 / 500000 * 100)
    assert u["dia"] == 3                                                                 # 2,2 días desde el 30-sep 08:00
    assert u["metrica"] == "ctr" and u["valor"] == pytest.approx(132 / 8000 * 100) and u["mejor"] == "cf_1"
    c = r.cargar("acme", r.Filtro(dias=7, experimento_id=sembrado["e1"]), AHORA)
    assert r.experimentos_tarjetas(c)[0]["seleccionado"] is True


def test_tarjetas_dia_tope_y_moneda(sembrado):
    import experimentos as ex
    import resultados as r
    db, e1 = sembrado["db"], sembrado["e1"]
    assert r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7), AHORA))[0]["dia"] is None    # no se activó
    ex.actualizar_extra("acme", e1, lambda extra: dict(extra, activado_en="2026-09-01T08:00:00"))
    assert r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7), AHORA))[0]["dia"] == 14       # nunca pasa de «de 14»
    ex.actualizar("acme", e1, tope_total=0)
    assert r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7), AHORA))[0]["pct_tope"] is None
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_usd")
    e2 = ex.crear("acme", "Dolares", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t.co/p", "USD")
    ep = ex.agregar_pieza("acme", e2, clon, "CO")
    ex.snapshot(ep, {"impresiones": 10, "gasto": 500.0, "clics_enlace": 1}, tomado_en="2026-10-01T10:00:00")
    t = {x["nombre"]: x for x in r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7, moneda="USD"), AHORA))}
    assert list(t) == ["Dolares"] and t["Dolares"]["pct_tope"] == 100.0                  # el gasto pasa del tope: 100 %
    assert t["Dolares"]["valor"] is None and t["Dolares"]["mejor"] is None               # sin detalle de Meta
    assert list(r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7, moneda="COP"), AHORA))) != []
    assert [x["nombre"] for x in r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7, moneda="COP"), AHORA))] == ["Uno"]


def test_tarjeta_de_ventas_con_roas_y_su_mejor_pieza(sembrado):
    import resultados as r
    e2, _ep = _experimento_de_ventas(sembrado)
    t = {x["nombre"]: x for x in r.experimentos_tarjetas(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))}
    assert t["Ventas"]["metrica"] == "roas" and t["Ventas"]["valor"] == pytest.approx(90.0 / 30.0)
    assert t["Ventas"]["mejor"] == "cf_ventas" and t["Ventas"]["dia"] is None
    assert t["Ventas"]["mide_ventas"] is True


# ---- ventas medibles (I1 de la revisión final de E2, 2026-10-03) ----

def _sin_ventas(sembrado, objetivo="OUTCOME_TRAFFIC", nombre="Sin pixel", legado="cf_sin", gasto=100.0):
    """Un experimento que gasta sin nada que mida ventas: ningún snapshot con Pixel (con compras), tienda ni Triple
    Whale (`fuente_ventas` queda «ninguna», como en uno de tráfico con atribución «ninguna»)."""
    import experimentos as ex
    db = sembrado["db"]
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado=legado)
    e = ex.crear("acme", nombre, PAISES, objetivo, 7, 1000.0, "https://t.co/p", "COP")
    ep = ex.agregar_pieza("acme", e, clon, "CO")
    for f, g in (("2026-09-30T23:00:00", gasto / 2), ("2026-10-02T11:00:00", gasto)):
        ex.snapshot(ep, {"impresiones": 1000, "gasto": g, "clics_enlace": 10}, tomado_en=f)
    return e, ep


def test_sin_ventas_medibles_el_roas_y_las_compras_no_son_cero(sembrado):
    """Antes el ROAS salía 0,0 siempre que hubiera gasto: el KPI destacado, el ranking, la línea del día a día, el país y
    la tarjeta decían 0,0× en un experimento que no mide ventas. El Tablero viejo decía «—» y «sin ventas medibles»."""
    import resultados as r
    e, _ep = _sin_ventas(sembrado, objetivo="OUTCOME_SALES")
    c = r.cargar("acme", r.Filtro(dias=7, experimento_id=e), AHORA)
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["gasto"]["valor"] == 100.0 and k["gasto"]["sin_ventas"] is False and k["ctr"]["sin_ventas"] is False
    for clave in ("roas", "cpa", "compras", "ingresos"):
        assert k[clave]["valor"] is None and k[clave]["sin_ventas"] is True, clave
        assert all(v is None for v in k[clave]["tendencia"]), clave
    (p,) = r.piezas(c, {})
    assert p["metrica"] == "roas" and p["roas"] is None and p["compras"] is None and p["mide_ventas"] is False
    assert p["delta_roas"] is None and all(v is None for v in p["serie"] + p["promedio"])
    s = r.serie(c)
    assert all(v is None for v in s["roas"]) and s["gasto"][-1] == 50.0
    (pais,) = r.paises(c)
    assert pais["gasto"] == 100.0 and pais["roas"] is None
    t = {x["nombre"]: x for x in r.experimentos_tarjetas(c)}["Sin pixel"]
    assert t["metrica"] == "roas" and t["valor"] is None and t["mide_ventas"] is False and t["mejor"] is None


def test_con_y_sin_ventas_juntos_el_roas_sale_de_los_que_miden(sembrado):
    """Un experimento con Pixel («Uno»: 80 de gasto, 240 de ingresos, 8 compras) y uno sin nada que mida ventas (100 de
    gasto), filtrados juntos: el gasto es de los dos; el ROAS y el costo por compra, solo del que mide (no 240 / 180)."""
    import resultados as r
    _sin_ventas(sembrado)
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert k["gasto"]["valor"] == 180.0
    assert k["roas"]["valor"] == pytest.approx(240.0 / 80.0) and k["roas"]["sin_ventas"] is False
    assert k["cpa"]["valor"] == pytest.approx(80.0 / 8) and k["compras"]["valor"] == 8 and k["ingresos"]["valor"] == 240.0
    p = {x["nombre"]: x for x in r.piezas(c, {})}
    assert p["cf_sin"]["roas"] is None and p["cf_sin"]["mide_ventas"] is False
    assert p["cf_1"]["roas"] == pytest.approx(3.0) and p["cf_1"]["mide_ventas"] is True
    co = {x["pais"]: x for x in r.paises(c)}["CO"]                       # CO: cf_1 (mide) y cf_sin (no)
    assert co["gasto"] == 140.0 and co["roas"] == pytest.approx(120.0 / 40.0)
    assert r.serie(c)["roas"][-1] == pytest.approx(60.0 / 20.0)          # el día: 20 de «Uno», 50 de cf_sin


def test_contexto_completo_y_json(sembrado):
    import json
    import resultados as r
    c = r.contexto("acme", r.Filtro(dias=7), AHORA)
    for k in ("filtro", "query", "opciones", "periodo", "moneda", "indicadores", "serie", "marcas", "embudo",
              "piezas", "evolucion", "desgloses", "paises", "experimentos", "generacion", "detalle_meta",
              "hay_detalle", "datos_graficos"):
        assert k in c, k
    json.dumps(c["datos_graficos"])
    assert c["experimentos"][0]["nombre"] == "Uno" and c["moneda"] == "COP"
    assert all(p["ep_id"] != sembrado["ep_o"] for p in c["piezas"])


def test_contexto_forma_de_cada_parte(sembrado):
    import json
    import experimentos as ex
    import resultados as r
    db, e1 = sembrado["db"], sembrado["e1"]
    ex.actualizar_extra("acme", e1, lambda extra: dict(extra, detalle_meta={"actualizado_en": AHORA, "errores": []}))
    _evento(db, "acme", e1, "accion", "Se pausó", "2026-10-01T09:00:00", ep_id=sembrado["ep_v"])
    _desglose(db, sembrado["ep_v"], "ubicacion", "facebook|feed", gasto=30.0)
    with db.conectar() as con:
        con.execute(db.gasto.insert().values(cliente="acme", creado_en="2026-10-01T12:00:00", tipo="video", usd=1.5,
                                             referencia="video:1"))
        con.execute(db.gasto.insert().values(cliente="acme", creado_en="2026-09-01T12:00:00", tipo="video", usd=9.0,
                                             referencia="video:2"))
        con.execute(db.gasto.insert().values(cliente="otro", creado_en="2026-10-01T12:00:00", tipo="video", usd=70.0,
                                             referencia="video:3"))
    f = r.Filtro(dias=7, pais="CO")
    c = r.contexto("acme", f, AHORA)
    assert c["filtro"] == f and c["query"] == {"dias": 7, "pais": "CO"}
    assert c["periodo"] == {"n": 7, "desde": "2026-09-26T00:00:00", "hasta": "2026-10-03T00:00:00", "es_todo": False}
    assert [i["clave"] for i in c["indicadores"]] == [k[0] for k in r.KPIS] and c["serie"]["moneda"] == "COP"
    assert c["marcas"] == [{"dia": "2026-10-01", "texto": "Se pausó"}] and c["embudo"]["pasos"][0]["valor"] == 4000
    assert [p["ep_id"] for p in c["piezas"]] == [sembrado["ep_v"]] and c["evolucion"] == c["piezas"]
    assert c["desgloses"]["ubicacion"][0]["clave"] == "facebook|feed" and [p["pais"] for p in c["paises"]] == ["CO"]
    assert c["generacion"] == {"usd": 1.5, "n": 1}
    assert c["detalle_meta"] == {e1: {"actualizado_en": AHORA, "errores": []}} and c["hay_detalle"] is True
    o = c["opciones"]
    assert o["experimentos"] == [{"id": e1, "nombre": "Uno", "estado": "armando", "moneda": "COP"}] and o["monedas"] == ["COP"]
    assert o["paises"] == ["CO", "MX"]                                                    # el filtro no recorta las opciones
    assert {x["ep_id"] for x in o["piezas"]} == {sembrado["ep_v"], sembrado["ep_i"]}
    assert all(set(x) >= {"ep_id", "nombre"} for x in o["piezas"])
    g = c["datos_graficos"]
    assert set(g) == {"serie", "marcas", "evolucion", "ubicacion", "tendencias"}
    assert g["evolucion"] == [{"ep_id": sembrado["ep_v"], "serie": c["piezas"][0]["serie"], "promedio": c["piezas"][0]["promedio"]}]
    assert g["ubicacion"] == c["desgloses"]["ubicacion"] and set(g["tendencias"]) == {k[0] for k in r.KPIS}
    assert g["tendencias"]["gasto"] == c["indicadores"][0]["tendencia"]
    json.dumps(g)


def test_contexto_evolucion_son_las_ocho_primeras_y_todo_es_json(sembrado):
    import json
    import experimentos as ex
    import resultados as r
    db = sembrado["db"]
    for k in range(8):
        clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_mas{k}")
        ex.agregar_pieza("acme", sembrado["e1"], clon, "CO")
    c = r.contexto("acme", r.Filtro(dias=7), AHORA)
    assert len(c["piezas"]) == 10 and len(c["evolucion"]) == 8 and c["evolucion"] == c["piezas"][:8]
    assert len(c["datos_graficos"]["evolucion"]) == 8
    json.dumps(c["datos_graficos"])
    json.dumps(c["periodo"])


def test_contexto_sin_detalle_ni_gasto(sembrado):
    import resultados as r
    db = sembrado["db"]
    with db.conectar() as con:
        con.execute(db.metrica_dia.delete())
    c = r.contexto("acme", r.Filtro(dias=7), AHORA)
    assert c["hay_detalle"] is False and c["generacion"] == {"usd": 0.0, "n": 0}
    assert c["detalle_meta"] == {sembrado["e1"]: None}
    vacio = r.contexto("nadie", r.Filtro(dias=7), AHORA)
    assert vacio["piezas"] == [] and vacio["experimentos"] == [] and vacio["opciones"]["experimentos"] == []
    assert vacio["hay_detalle"] is False and vacio["datos_graficos"]["evolucion"] == []


def test_contexto_desde_el_inicio_cuenta_toda_la_generacion(sembrado):
    import resultados as r
    db = sembrado["db"]
    with db.conectar() as con:
        con.execute(db.gasto.insert().values(cliente="acme", creado_en="2025-01-01T12:00:00", tipo="video", usd=4.0,
                                             referencia="video:viejo"))
    assert r.contexto("acme", r.Filtro(dias=7), AHORA)["generacion"]["usd"] == 0.0
    c = r.contexto("acme", r.Filtro(dias=0), AHORA)
    assert c["generacion"]["usd"] == 4.0 and c["periodo"]["es_todo"] is True
