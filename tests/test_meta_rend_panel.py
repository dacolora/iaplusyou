"""Lo que pinta la pestaña «Meta» (spec 2026-10-08 meta rendimiento §8): «Todas» en USD con la tasa de cada día,
una cuenta en su moneda, la variación contra el período anterior, el veredicto de cada anuncio contra SU cuenta,
la paginación y pocas consultas para todo."""
from datetime import date

import pytest
from sqlalchemy import event

import db
from meta_rendimiento import cuentas, datos, panel

HOY = date(2026, 10, 8)          # dias=30 -> 2026-09-09..2026-10-08; previo 2026-08-10..2026-09-08
A, B, C = "act_1", "act_2", "act_3"


@pytest.fixture
def conectado(monkeypatch):
    monkeypatch.setattr(panel.meta_conexion, "cargar", lambda cliente: {"token": "tok-prueba", "page_id": None})
    monkeypatch.setattr(panel.meta_conexion, "modo", lambda cliente: "propia")
    monkeypatch.setattr(panel.proyectos, "reglas_defecto", lambda cliente: {})


def _cuentas(*pares):
    cuentas.elegir("hf", [{"id": act, "name": f"HappyFlops {act}", "currency": moneda, "pais": pais}
                          for act, moneda, pais in pares])


def _dia(fecha, gasto, valor, compras=1, impresiones=1000):
    return dict(fecha=fecha, gasto=gasto, impresiones=impresiones, alcance=800, clics=20, clics_salida=10,
                compras=compras, valor=valor, vistas_3s=300, thruplays=100)


def _ad(fecha, ad, gasto, valor, compras=0, impresiones=5000, campaign="c1", adset="s1"):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=impresiones,
                clics=100, clics_salida=60, compras=compras, valor=valor, vistas_3s=1500, thruplays=500,
                p25=900, p50=700, p75=500, p100=300)


def _tasa(moneda, fecha, usd):
    with db.conectar() as con:
        con.execute(db.tasa_cambio.insert().values(fecha=fecha, moneda=moneda, usd_por_unidad=usd, fuente="bce",
                                                   creado_en=db.ahora()))


def test_sin_token_no_esta_conectado_y_no_calcula_nada(base_temporal, monkeypatch):
    monkeypatch.setattr(panel.meta_conexion, "cargar", lambda cliente: {})
    _cuentas((A, "SEK", "NO"))
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["conectado"] is False and ctx["modo"] is None
    assert ctx["cuentas"] == [] and ctx["kpis"] is None and ctx["anuncios"] == []


def test_sin_cuentas_y_sin_filas(base_temporal, conectado):
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["conectado"] is True and ctx["solo_metricas"] is True and ctx["modo"] == "propia"
    assert ctx["cuentas"] == [] and ctx["kpis"] is None
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    ctx = panel.contexto("hf", hoy=HOY)
    assert len(ctx["cuentas"]) == 2 and ctx["rango"]["filas"] == 0
    assert ctx["kpis"] is None and ctx["serie"] is None and ctx["anuncios"] == [] and ctx["por_cuenta"] == []


def test_todas_en_usd_con_moneda_comun(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 100, 300, compras=2)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-02", "2026-10-02", [_dia("2026-10-02", 50, 100, compras=1)])
    _tasa("SEK", "2026-10-01", 0.1)
    _tasa("SEK", "2026-10-02", 0.2)
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 700,
                                     "frecuencia": 1.5}])
    datos.guardar_alcance("hf", B, [{"nivel": "cuenta", "objeto_id": B, "ventana": 30, "alcance": 300,
                                     "frecuencia": 2.0}])
    datos.guardar_objetos("hf", A, [{"nivel": "conjunto", "objeto_id": "s1", "estado": "ACTIVE",
                                     "aprendizaje": "FAIL"}])
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["actual"] is None and ctx["ids"] == [A, B] and ctx["varias_cuentas"] is True
    assert ctx["moneda"] == "USD" and ctx["moneda_comun"] == "SEK" and ctx["usd_ok"] is True
    assert ctx["kpis"]["gasto"] == pytest.approx(100 * 0.1 + 50 * 0.2)
    assert ctx["kpis"]["valor"] == pytest.approx(300 * 0.1 + 100 * 0.2)
    assert ctx["kpis"]["roas"] == pytest.approx(50 / 20) and ctx["kpis"]["compras"] == 3
    assert ctx["kpis_moneda_comun"]["gasto"] == 150 and ctx["kpis_moneda_comun"]["valor"] == 400
    # El alcance de «Todas» es la suma de las cuentas (gente única por cuenta); la frecuencia solo en una cuenta.
    assert ctx["alcance"] == 1000 and ctx["frecuencia"] is None and ctx["ventana_alcance"] == 30
    # La serie en USD, un punto por día del período.
    assert ctx["serie"]["moneda"] == "USD" and len(ctx["serie"]["dias"]) == 30
    dia1 = next(d for d in ctx["serie"]["dias"] if d["dia"] == "2026-10-01")
    assert dia1["gasto"] == pytest.approx(10) and dia1["ingresos"] == pytest.approx(30) and dia1["compras"] == 2
    # «Por cuenta»: en USD, con su moneda propia al lado, su alcance y lo activo.
    filas = {f["ad_account_id"]: f for f in ctx["por_cuenta"]}
    assert filas[A]["gasto"] == pytest.approx(10) and filas[A]["gasto_cuenta"] == 100
    assert filas[A]["moneda"] == "USD" and filas[A]["moneda_cuenta"] == "SEK"
    assert filas[A]["alcance"] == 700 and filas[A]["activos"]["aprendizaje_limitado"] == 1
    assert filas[B]["roas"] == pytest.approx(2.0)
    assert ctx["cuentas"][0]["bandera"] and ctx["cuentas"][0]["nombre_pais"]


def test_una_cuenta_en_su_moneda_y_un_id_ajeno_es_todas(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 80, 0, compras=0)])
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 700,
                                     "frecuencia": 1.5}])
    ctx = panel.contexto("hf", cuenta=A, hoy=HOY)
    assert ctx["actual"]["ad_account_id"] == A and ctx["ids"] == [A]
    assert ctx["moneda"] == "SEK" and ctx["usd_ok"] is True and ctx["kpis"]["gasto"] == 100
    assert ctx["kpis_moneda_comun"] is None and ctx["serie"]["moneda"] == "SEK"
    assert ctx["alcance"] == 700 and ctx["frecuencia"] == 1.5
    for ajeno in ("act_999", "todas", None, 7):
        ctx = panel.contexto("hf", cuenta=ajeno, hoy=HOY)
        assert ctx["actual"] is None and ctx["moneda"] == "USD" and ctx["moneda_comun"] is None
    # Sin moneda común no hay total exacto en una moneda, pero sí el total de cada moneda.
    assert {m["moneda"]: m["gasto"] for m in ctx["por_moneda"]} == {"SEK": 100, "NOK": 80}


def test_cuenta_elegida():
    unas = [{"ad_account_id": A}, {"ad_account_id": B}]
    assert panel.cuenta_elegida(unas, B) is unas[1]
    assert panel.cuenta_elegida(unas, "2") is unas[1]
    assert panel.cuenta_elegida(unas, "act_9") is None and panel.cuenta_elegida(unas, "") is None
    assert panel.cuenta_elegida(unas, None) is None and panel.cuenta_elegida(unas, ["x"]) is None
    assert panel.cuenta_elegida(unas[:1], None) is unas[0]           # con una sola cuenta, siempre esa
    assert panel.cuenta_elegida([], A) is None


def test_sin_tasa_un_dia_con_gasto_usd_no_disponible(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 50, 0, compras=0)])
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["usd_ok"] is False
    assert ctx["kpis"]["gasto"] is None and ctx["kpis"]["roas"] is None and ctx["kpis"]["compras"] == 1
    # Nunca una tasa inventada: la serie y la tabla caen a la moneda común, sin convertir.
    assert ctx["kpis_moneda_comun"]["gasto"] == 150
    assert ctx["serie"]["moneda"] == "SEK"
    assert next(d for d in ctx["serie"]["dias"] if d["dia"] == "2026-10-01")["gasto"] == 150
    assert all(f["gasto"] is None and f["usd_ok"] is False for f in ctx["por_cuenta"])
    # Un día sin gasto ni valor no necesita tasa.
    kp = panel.kpis([dict(_dia("2026-10-03", 0, 0, compras=0), ad_account_id=A)], {})
    assert kp["usd_ok"] is True and kp["gasto"] == 0


def test_tasa_de_hace_cuatro_dias_aun_sirve_y_de_hace_cinco_ya_no(base_temporal, conectado):
    """Ruling R24: un día sin tasa publicada usa la última anterior solo si es de hace 4 días o menos."""
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    _tasa("SEK", "2026-09-30", 0.1)
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-04", "2026-10-04", [_dia("2026-10-04", 100, 300)])
    ctx = panel.contexto("hf", hoy=HOY)                                  # el 4 oct está a 4 días del 30 sep
    assert ctx["usd_ok"] is True and ctx["kpis"]["gasto"] == pytest.approx(10)


def test_hueco_de_cinco_dias_con_gasto_usd_no_disponible(base_temporal, conectado):
    """Con gasto cinco días después de la última tasa publicada no hay USD (ni una tasa de hace semanas)."""
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    _tasa("SEK", "2026-09-30", 0.1)
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 100, 300)])
    ctx = panel.contexto("hf", hoy=HOY)                                  # el 5 oct está a 5 días del 30 sep
    assert ctx["usd_ok"] is False
    assert ctx["kpis"]["gasto"] is None and ctx["kpis"]["roas"] is None
    assert ctx["kpis_moneda_comun"]["gasto"] == 100 and ctx["serie"]["moneda"] == "SEK"
    assert all(f["usd_ok"] is False for f in ctx["por_cuenta"] if f["ad_account_id"] == A)


def test_todas_con_una_cuenta_sin_moneda_usd_no_disponible_y_sin_moneda_comun(base_temporal, conectado):
    """Una cuenta sin moneda conocida no se convierte (no hay tasa para ella) ni se suma como si fuera de la moneda de
    las demás: «Todas» dice USD no disponible, no hay moneda común y el total de cada moneda la deja aparte."""
    _cuentas((A, "SEK", "NO"), (B, "", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 100, 300)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 50, 100)])
    _tasa("SEK", "2026-10-01", 0.1)
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["actual"] is None and ctx["moneda"] == "USD"
    assert ctx["usd_ok"] is False and ctx["kpis"]["gasto"] is None
    assert ctx["moneda_comun"] is None and ctx["kpis_moneda_comun"] is None and ctx["serie"] is None
    # El gasto de la cuenta sin moneda no entra en el total de SEK.
    assert {m["moneda"]: m["gasto"] for m in ctx["por_moneda"]} == {"SEK": 100, "": 50}
    filas = {f["ad_account_id"]: f for f in ctx["por_cuenta"]}
    assert filas[A]["usd_ok"] is True and filas[A]["gasto"] == pytest.approx(10)
    assert filas[B]["usd_ok"] is False and filas[B]["gasto"] is None
    # La cuenta con moneda, sola, sí se ve en su moneda.
    solo = panel.contexto("hf", cuenta=A, hoy=HOY)
    assert solo["moneda"] == "SEK" and solo["usd_ok"] is True and solo["kpis"]["gasto"] == 100


def test_kpis_derivados():
    filas = [dict(_dia("2026-10-01", 100, 300, compras=2, impresiones=10000), ad_account_id=A),
             dict(_dia("2026-10-02", 100, 100, compras=2, impresiones=10000), ad_account_id=A)]
    k = panel.kpis(filas)
    assert k["gasto"] == 200 and k["valor"] == 400 and k["roas"] == 2 and k["cpa"] == 50
    assert k["cpm"] == pytest.approx(10) and k["ctr_salida"] == pytest.approx(0.1) and k["usd_ok"] is True
    k = panel.kpis(filas, {(A, "2026-10-01"): 0.5, (A, "2026-10-02"): 0.25})
    assert k["gasto"] == pytest.approx(75) and k["valor"] == pytest.approx(175)


def test_variacion_contra_el_periodo_anterior(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-08-20", "2026-10-01",
                                 [_dia("2026-08-20", 100, 200, compras=2), _dia("2026-10-01", 150, 600, compras=3)])
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["kpis"]["gasto"] == 150 and ctx["kpis_prev"]["gasto"] == 100
    assert ctx["variacion"]["gasto"] == pytest.approx((150 - 100) / 100)
    assert ctx["variacion"]["roas"] == pytest.approx(4 / 2 - 1)
    assert ctx["variacion"]["compras"] == pytest.approx(0.5)


def test_veredicto_por_anuncio_contra_su_propia_cuenta(base_temporal, conectado, monkeypatch):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 400, 1000)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 10000, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-05", "2026-10-05", [
        _ad("2026-10-05", "gana", 100, 1000, compras=5), _ad("2026-10-05", "pierde", 300, 0, compras=0)])
    # En la otra cuenta, un anuncio caro con muchas compras: si se mezclaran las cuentas, el costo por venta subiría
    # (de 80 a casi 700) y «pierde» dejaría de ser perdedor.
    datos.reemplazar_anuncio_dias("hf", B, "2026-10-05", "2026-10-05", [
        _ad("2026-10-05", "grande", 10000, 30000, compras=10, campaign="c2", adset="s2")])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "gana", "nombre": "Video gana",
                                     "estado": "ACTIVE", "miniatura_url": "https://scontent.xx.fbcdn.net/gana.jpg"}])
    leer = datos.totales_por_anuncio

    def con_rastreo_roto(*a, **k):                  # «sin_rastreo» es de Triple Whale: aquí nunca se muestra
        return [dict(t, utm_ok=False) for t in leer(*a, **k)]
    monkeypatch.setattr(panel.datos, "totales_por_anuncio", con_rastreo_roto)
    ctx = panel.contexto("hf", hoy=HOY)
    por_id = {a["ad_id"]: a for a in ctx["anuncios"]}
    assert por_id["gana"]["veredicto"] == "ganador" and por_id["pierde"]["veredicto"] == "perdedor"
    assert [a["ad_id"] for a in ctx["anuncios"]] == ["grande", "gana", "pierde"]   # veredicto y luego gasto
    assert all("sin_rastreo" not in a["problemas"] for a in ctx["anuncios"])
    assert por_id["gana"]["ad_account_id"] == A and por_id["gana"]["moneda"] == "SEK"
    assert por_id["gana"]["estado"] == "ACTIVE" and por_id["gana"]["miniatura_url"] == "https://scontent.xx.fbcdn.net/gana.jpg"
    assert por_id["gana"]["nombre"] == "Video gana" and por_id["grande"]["ad_account_id"] == B
    assert ctx["conteo"]["ganador"] == 2 and ctx["conteo"]["perdedor"] == 1 and ctx["meta_roas"] == 2.0
    # Campañas y conjuntos en la moneda de su cuenta.
    assert {c["campaign_id"]: c["moneda"] for c in ctx["campanas"]} == {"c1": "SEK", "c2": "SEK"}
    assert ctx["conjuntos"][0]["adset_id"] == "s2" and ctx["conjuntos"][0]["m"]["roas"] == 3


def test_paginacion_de_anuncios(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"))
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-05", "2026-10-05", [_dia("2026-10-05", 300, 0)])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-05", "2026-10-05",
                                  [_ad("2026-10-05", f"a{i:02d}", 10 + i, 0) for i in range(30)])
    ctx = panel.contexto("hf", hoy=HOY)
    assert len(ctx["anuncios"]) == panel.POR_PAGINA == 24 and ctx["hay_mas_anuncios"] is True
    assert ctx["n_anuncios"] == 30
    ctx2 = panel.contexto("hf", hoy=HOY, pagina_anuncios=1)
    assert len(ctx2["anuncios"]) == 6 and ctx2["hay_mas_anuncios"] is False
    vistos = [a["ad_id"] for a in ctx["anuncios"] + ctx2["anuncios"]]
    assert len(set(vistos)) == 30
    assert panel.contexto("hf", hoy=HOY, pagina_anuncios="x")["anuncios"] == ctx["anuncios"]


def test_jobs_sync_y_ultima_copia_del_alcance(base_temporal, conectado, monkeypatch):
    _cuentas((A, "SEK", "NO"), (B, "SEK", "SE"))
    cuentas.actualizar("hf", A, ultima_copia="2026-10-08T06:00:00")
    cuentas.actualizar("hf", B, ultima_copia="2026-10-08T03:00:00")
    monkeypatch.setattr(panel.tareas_mr, "syncs_en_curso", lambda cliente: [panel.tareas_mr.job_id_sync("hf", B)])
    ctx = panel.contexto("hf", hoy=HOY)
    assert ctx["ultima_copia"] == "2026-10-08T03:00:00"
    assert [j["cuenta"]["ad_account_id"] for j in ctx["jobs_sync"]] == [B]
    ctx = panel.contexto("hf", cuenta=A, hoy=HOY)
    assert ctx["ultima_copia"] == "2026-10-08T06:00:00" and ctx["jobs_sync"] == []


def test_pocas_consultas_con_tres_cuentas(base_temporal, conectado):
    _cuentas((A, "SEK", "NO"), (B, "NOK", "SE"), (C, "EUR", "FI"))
    for act, moneda in ((A, "SEK"), (B, "NOK"), (C, "EUR")):
        datos.reemplazar_cuenta_dias("hf", act, "2026-08-15", "2026-10-07",
                                     [_dia("2026-08-15", 10, 20), _dia("2026-10-07", 30, 90)])
        datos.reemplazar_anuncio_dias("hf", act, "2026-09-25", "2026-10-07",
                                      [_ad(f, f"{act}-{i}", 5, 10, compras=1) for f in ("2026-09-25", "2026-10-07")
                                       for i in range(5)])
        datos.guardar_alcance("hf", act, [{"nivel": "cuenta", "objeto_id": act, "ventana": 30, "alcance": 10,
                                           "frecuencia": 1.0}])
        # Una tasa publicada poco antes de cada día con datos (las tasas viejas ya no rellenan: ruling R24).
        for dia_tasa in ("2026-08-14", "2026-09-24", "2026-10-06"):
            _tasa(moneda, dia_tasa, 0.1)
    consultas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        ctx = panel.contexto("hf", hoy=HOY)
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert len(ctx["anuncios"]) == 15 and ctx["usd_ok"] is True and len(ctx["por_cuenta"]) == 3
    assert len(consultas) <= 15, consultas
