from tests.test_tablero import _experimento, _pieza_en, _snap, sin_red, AHORA  # noqa: F401


def test_sonda_un_experimento_cop_apaga_el_roas_de_todos_los_meses(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    # Experimento USD sano, con Pixel y ventas en julio, agosto y septiembre.
    sano = _experimento(base_temporal, "Sano", moneda="USD", atribucion="pixel")
    ep = _pieza_en(base_temporal, sano)
    for t, g, c, i in (("2026-07-10T08:00:00", 100, 1, 300), ("2026-08-15T08:00:00", 200, 2, 600),
                       ("2026-09-10T08:00:00", 300, 3, 900)):
        ex.snapshot(ep, {"gasto": g, "compras": c, "ingresos": i, "fuente_ventas": "meta"}, tomado_en=t)
    antes = tablero.mes_a_mes("acme", ahora_iso=AHORA)
    total_antes = tablero.resumen_total("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    # Otro experimento USD, cerrado, con tienda en COP; solo gastó en septiembre.
    cop = _experimento(base_temporal, "TiendaCOP", moneda="USD", atribucion="tienda", estado="cerrado",
                       extra={"aviso_moneda": "COP"})
    ep2 = _pieza_en(base_temporal, cop, legado="cf_2__es_CO")
    ex.snapshot(ep2, {"gasto": 10, "compras": 1, "ingresos": 40000, "fuente_ventas": "tienda"},
                tomado_en="2026-09-12T08:00:00")
    despues = tablero.mes_a_mes("acme", ahora_iso=AHORA)
    total = tablero.resumen_total("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    assert total["roas"] is None
    for a, b in zip(antes, despues):
        if a["mes"] < "2026-09":
            assert b["por_moneda"]["USD"]["roas"] == a["por_moneda"]["USD"]["roas"] == 3.0


def test_sonda_tw_cae_a_meta_sin_compras_y_vuelve():
    import tablero
    snaps = [_snap("2026-09-01T08:00:00", gasto=100, compras=5, ingresos=500, fuente_ventas="triple_whale"),
             _snap("2026-09-02T08:00:00", gasto=150, compras=0, ingresos=0, fuente_ventas="ninguna"),
             _snap("2026-09-03T08:00:00", gasto=200, compras=6, ingresos=600, fuente_ventas="triple_whale")]
    dias = [("2026-09-01T00:00:00", "2026-09-02T00:00:00"), ("2026-09-02T00:00:00", "2026-09-03T00:00:00"),
            ("2026-09-03T00:00:00", "2026-09-04T00:00:00")]
    suma = [tablero._deltas_pieza(snaps, a, b) for a, b in dias]
    periodo = tablero._deltas_pieza(snaps, "2026-09-01T00:00:00", "2026-09-04T00:00:00")
    assert periodo["compras"] == 6 and periodo["ingresos"] == 600
    assert suma[1]["compras"] is None and suma[2]["compras"] is None
    assert sum(d["compras"] or 0 for d in suma) <= periodo["compras"]
    assert sum(d["ingresos"] or 0 for d in suma) <= periodo["ingresos"]


def test_sonda_centro_con_un_experimento_cop_cerrado(base_temporal):
    import experimentos as ex
    import resultados as r
    from tests.test_resultados import sembrado as _s  # noqa
    from tests.test_experimentos_db import _pieza, PAISES
    e1 = ex.crear("acme", "Sano", PAISES, "OUTCOME_SALES", 14, 500.0, "https://t.co/p", "USD", atribucion="pixel")
    p1 = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    ep1 = ex.agregar_pieza("acme", e1, p1, "CO")
    ex.snapshot(ep1, {"gasto": 100, "compras": 2, "ingresos": 300, "fuente_ventas": "meta", "impresiones": 1000},
                tomado_en="2026-10-01T10:00:00")
    ahora = "2026-10-02T12:00:00"
    antes = {i["clave"]: (i["valor"], i.get("roas_no_comparable")) for i in r.indicadores(r.cargar("acme", r.Filtro(dias=7), ahora))}
    e2 = ex.crear("acme", "Viejo COP", PAISES, "OUTCOME_SALES", 7, 500.0, "https://t.co/p", "USD", atribucion="tienda")
    ex.actualizar_extra("acme", e2, lambda extra: dict(extra, aviso_moneda="COP"))
    ex.actualizar("acme", e2, estado="cerrado")
    p2 = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    ep2 = ex.agregar_pieza("acme", e2, p2, "CO")
    ex.snapshot(ep2, {"gasto": 5, "compras": 1, "ingresos": 20000, "fuente_ventas": "tienda", "impresiones": 10},
                tomado_en="2026-07-01T10:00:00")
    despues = {i["clave"]: (i["valor"], i.get("roas_no_comparable")) for i in r.indicadores(r.cargar("acme", r.Filtro(dias=7), ahora))}
    assert despues["roas"] == antes["roas"] == (3.0, False)
    assert despues["ingresos"] == antes["ingresos"]


def test_pnd139_respaldo_ciego_anterior_a_ventana(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    e = _experimento(base_temporal, moneda="USD", atribucion="triple_whale")
    p = _pieza_en(base_temporal, e)
    for t, g, c, i, f in [("2026-07-01T08:00:00", 100, 5, 500, "triple_whale"),
                          ("2026-08-31T08:00:00", 150, 0, 0, "ninguna"),
                          ("2026-09-03T08:00:00", 200, 6, 600, "triple_whale")]:
        ex.snapshot(p, dict(gasto=g, compras=c, ingresos=i, fuente_ventas=f), tomado_en=t)
    r = tablero.resumen_mes("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    assert r["roas"] is None and r["compras"] is None and r["ingresos"] is None
    meses = {m["mes"]: m for m in tablero.mes_a_mes("acme", ahora_iso=AHORA)}
    assert meses["2026-09"]["por_moneda"]["USD"]["roas"] is None
    fila = tablero.csv_mes("acme", ahora_iso=AHORA).splitlines()[1].split(";")
    assert fila[7:10] == ["", "", ""]


def test_pnd139_cambio_de_fuente_no_es_cero():
    import resultados as r
    snaps = [_snap("2026-09-01T08:00:00", gasto=100, compras=2, ingresos=300, fuente_ventas="triple_whale"),
             _snap("2026-09-03T08:00:00", gasto=300, compras=6, ingresos=1000, fuente_ventas="meta")]
    d = r._deltas({"atribucion": "triple_whale"}, snaps, "2026-09-01T12:00:00", "2026-09-03T12:00:00")
    v = r._con_ventas(d["gasto"], r.tablero.ventas_medidas([d]))
    assert v["roas"] is None and v["roas_comparable"] is False
    assert all(v[k] is None for k in ("compras", "ingresos", "cpa"))
