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


def _evento(db, cliente, experimento_id, tipo, mensaje, creado_en, ep_id=None):
    with db.conectar() as con:
        con.execute(db.evento.insert().values(cliente=cliente, experimento_id=experimento_id, experimento_pieza_id=ep_id,
                                              tipo=tipo, mensaje=mensaje, datos={}, creado_en=creado_en))


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
    assert e["frase"] == "Todos los pasos están en tu promedio o mejor."     # lo sin Pixel no es «la peor caída»


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
        assert e["frase"] == "The biggest drop is at “Added to cart”: 6.7 % vs 12.0 % of your average."
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
