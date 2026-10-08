from tests.test_tablero import _experimento, _pieza_en, sin_red, AHORA  # noqa: F401


def test_pnd138_moneda_ajena_con_solo_ingresos(base_temporal, sin_red):
    import experimentos as ex
    import tablero
    sano = _experimento(base_temporal, "Sano", moneda="USD", atribucion="pixel")
    ep = _pieza_en(base_temporal, sano)
    ex.snapshot(ep, {"gasto": 100, "compras": 3, "ingresos": 300, "fuente_ventas": "meta"}, tomado_en="2026-09-10T08:00:00")
    cop = _experimento(base_temporal, "TiendaCOP", moneda="USD", atribucion="tienda", estado="cerrado", extra={"aviso_moneda": "COP"})
    ep2 = _pieza_en(base_temporal, cop, legado="cf_2__es_CO")
    ex.snapshot(ep2, {"gasto": 10, "compras": 1, "ingresos": 40000, "fuente_ventas": "tienda"}, tomado_en="2026-08-20T08:00:00")
    # En septiembre el pedido se editó: mismos pedidos, más ingresos en COP; sin gasto ni impresiones.
    ex.snapshot(ep2, {"gasto": 10, "compras": 1, "ingresos": 90000, "fuente_ventas": "tienda"}, tomado_en="2026-09-12T08:00:00")
    g = tablero.resumen_mes("acme", ahora_iso=AHORA)["por_moneda"]["USD"]
    print("\nSEPTIEMBRE USD", {k: g[k] for k in ("gasto", "compras", "ingresos", "roas", "roas_comparable")})
    assert g["roas"] == 3.0 and g["excluidos"] == 1, "el ROAS excluye COP"
    assert g["ingresos"] == 300 and g["roas_comparable"]
    assert g["compras"] == 3 and g["gasto"] == 100
