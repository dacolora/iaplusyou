"""«01 Resultados» y «02 Por país» de la pestaña Rendimiento con Meta y mezcla (spec 2026-10-09 R5–R8)."""
from datetime import date, timedelta

import pytest

import idiomas
import triple_whale_tiendas
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import entradas as E, resumen
from tests.test_rutas_meta_rendimiento import _cuentas, _dia, _tasa
from triple_whale import datos as twdatos

HOY = date.today()


@pytest.fixture(autouse=True)
def _llave_de_cifrado(monkeypatch):
    # `triple_whale_tiendas.agregar` cifra la llave de la tienda con la clave de la app.
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")


def _hace(n):
    return (HOY - timedelta(days=n)).isoformat()


def _sembrar(cubierta_ww=False, dias_tw=5, dias_meta=20):
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    for n in range(dias_tw):
        f = _hace(n)
        twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 10, "ingresos": 30, "pedidos": 1}])
        if cubierta_ww:
            twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "w1", "fecha": f,
                                                                   "gasto": 1, "cuenta_id": "act_ww"}])
    _cuentas("acme", ("act_no", "HappyFlops Norway", "NO"), ("act_se", "HappyFlops Sweden", "SE"),
             ("act_ww", "HappyFlops World Wide", None))
    for act in ("act_se", "act_ww"):
        for n in range(dias_meta):
            f = _hace(n)
            mdatos.reemplazar_cuenta_dias("acme", act, f, f, [_dia(f, 100, 150, compras=2)])
    for n in range(dias_meta):
        _tasa(_hace(n), 0.1, "SEK")
    return tid


def _ctx(dias=0, clave=None, moneda_tw="USD"):
    tiendas = triple_whale_tiendas.tiendas("acme")
    from meta_rendimiento import panel as mpanel
    es = E.armar(tiendas, mpanel.lista("acme"), twdatos.cuentas_meta_de_tiendas("acme"))
    actual = E.elegir(es, clave)
    with idiomas.en_idioma("es"):
        return resumen.contexto("acme", es, actual, E.alcance(es, actual), dias, HOY, moneda_tw)


def test_todas_mezcla_en_usd_desde_el_inicio_comun(base_temporal):
    _sembrar()
    c = _ctx()
    assert c["moneda"] == "USD" and c["usd_ok"] is True and c["inicio_comun"] == _hace(4)
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    # 5 días: tienda 5×10 USD de gasto y 5×30 de ventas; Meta (SE y WW) 2 cuentas × 5 días × 100 SEK × 0,1.
    assert round(tarjetas["gasto"], 2) == 50 + 100 and round(tarjetas["ventas"], 2) == 150 + 150
    assert {o["origen"] for o in c["origen"]} == {"tienda", "pixel_meta"}


def test_una_cuenta_cubierta_no_se_suma_en_todas(base_temporal):
    _sembrar(cubierta_ww=True)
    c = _ctx()
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    assert round(tarjetas["gasto"], 2) == 50 + 50          # solo SE suma aparte
    fila_ww = next(f for f in c["por_pais"] if f["entrada"]["clave"] == "cuenta:act_ww")
    assert fila_ww["fuera_de_todas"] is True


def test_sin_tasa_no_inventa_usd(base_temporal):
    _sembrar()
    import db
    with db.conectar() as con:
        con.execute(db.tasa_cambio.delete())
    c = _ctx()
    assert c["usd_ok"] is False and c["resultados"] is None


def test_solo_triple_whale_deja_los_resultados_a_su_bloque(base_temporal):
    _sembrar()
    c = _ctx(clave="NO")
    assert c["resultados"] is None and c["por_pais"] == []


def test_una_entrada_meta_sola_en_su_moneda(base_temporal):
    _sembrar()
    c = _ctx(clave="SE")
    assert c["moneda"] == "SEK" and c["resultados"]["fuente"] == "meta"
    assert c["inicio_comun"] is None


# ------------------------------------------------------------ más reglas ---

def test_el_origen_dice_de_donde_sale_cada_parte(base_temporal):
    _sembrar(cubierta_ww=True)
    with idiomas.en_idioma("es"):
        origen = _ctx()["origen"]
    # WW está dentro de la tienda: no suma aparte y no aparece; Noruega es la tienda y Suecia el Pixel de Meta.
    assert origen == [{"nombre": "Noruega", "origen": "tienda"}, {"nombre": "Suecia", "origen": "pixel_meta"}]


def test_por_pais_trae_cada_entrada_en_su_moneda_y_en_usd(base_temporal):
    _sembrar()
    por = {f["entrada"]["clave"]: f for f in _ctx()["por_pais"]}
    no, se, ww = por["NO"], por["SE"], por["cuenta:act_ww"]
    assert (no["fuente"], no["origen"], no["moneda"]) == ("tw", "tienda", "USD")
    assert (no["gasto"], no["ventas"], no["pedidos"], no["retorno"]) == (50, 150, 5, 3.0)
    assert no["gasto_usd"] == 50 and no["ventas_usd"] == 150 and no["fuera_de_todas"] is False
    assert (se["fuente"], se["origen"], se["moneda"]) == ("meta", "pixel_meta", "SEK")
    assert (se["gasto"], se["ventas"], se["pedidos"], se["retorno"]) == (500, 750, 10, 1.5)
    assert round(se["gasto_usd"], 2) == 50 and round(se["ventas_usd"], 2) == 75
    assert ww["fuera_de_todas"] is False and ww["gasto"] == se["gasto"]


def test_por_pais_no_inventa_usd_sin_tasa(base_temporal):
    _sembrar()
    import db
    with db.conectar() as con:
        con.execute(db.tasa_cambio.delete())
    se = next(f for f in _ctx()["por_pais"] if f["entrada"]["clave"] == "SE")
    assert se["gasto"] == 500 and se["gasto_usd"] is None and se["ventas_usd"] is None


def test_si_todas_comparten_moneda_va_en_esa_y_no_pide_tasas(base_temporal):
    _sembrar()
    import db
    with db.conectar() as con:
        con.execute(db.tasa_cambio.delete())
    c = _ctx(moneda_tw="SEK")
    assert c["moneda"] == "SEK" and c["usd_ok"] is True
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    assert tarjetas["gasto"] == 50 + 1000 and tarjetas["ventas"] == 150 + 1500


def test_con_un_periodo_fijo_compara_con_el_anterior_si_todas_las_fuentes_tienen_historia(base_temporal):
    _sembrar(dias_tw=14, dias_meta=20)
    c = _ctx(dias=7)
    assert c["inicio_comun"] is None                      # R7 solo vale para «Desde el inicio»
    variaciones = {t["clave"]: t["variacion"] for t in c["resultados"]["tarjetas"]}
    assert variaciones["gasto"] == 0                      # 6 días completos contra los 6 anteriores, datos iguales
    corto = _ctx(dias=14)                                 # el periodo anterior empieza antes de la tienda: sin comparar
    assert all(t["variacion"] is None for t in corto["resultados"]["tarjetas"])


def test_sin_pixel_de_tienda_la_parte_triple_whale_viene_de_los_anuncios_pagados(base_temporal):
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    f = _hace(1)
    twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "a1", "fecha": f,
                                                           "gasto": 10}])
    twdatos.reemplazar_anuncios_pixel("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "pedidos": 2, "ingresos": 40},
        {"canal": "klaviyo", "ad_id": "flujo", "fecha": f, "pedidos": 9, "ingresos": 900}])
    _cuentas("acme", ("act_se", "HappyFlops Sweden", "SE"))
    mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 100, 150, compras=2)])
    _tasa(f, 0.1, "SEK")
    c = _ctx()
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    assert round(tarjetas["ventas"], 2) == 40 + 15          # Klaviyo no es una venta de anuncio
    assert {o["origen"] for o in c["origen"]} == {"pixel_tw", "pixel_meta"}
    no = next(x for x in c["por_pais"] if x["entrada"]["clave"] == "NO")
    assert (no["origen"], no["ventas"], no["gasto"]) == ("pixel_tw", 40, 10)


def test_sin_nada_copiado_no_se_rompe(base_temporal):
    triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    _cuentas("acme", ("act_se", "HappyFlops Sweden", "SE"))
    c = _ctx()
    assert c["usd_ok"] is True and c["inicio_comun"] is None
    assert c["resultados"] is not None and all(t["valor"] in (0, None) for t in c["resultados"]["tarjetas"])
    assert all(f["gasto"] == 0 and f["retorno"] is None for f in c["por_pais"])


def test_cuenta_sin_dias_no_atrasa_el_inicio_comun(base_temporal):
    _sembrar()
    _cuentas("acme", ("act_no", "HappyFlops Norway", "NO"), ("act_se", "HappyFlops Sweden", "SE"),
             ("act_ww", "HappyFlops World Wide", None), ("act_fi", "HappyFlops Finland", "FI"))
    c = _ctx()
    assert c["inicio_comun"] == _hace(4)                   # Finlandia aún no tiene días copiados


def test_los_dias_de_antes_de_que_haya_datos_no_cuentan_como_semanas_normales(base_temporal):
    """Con datos de todas las fuentes desde hace 17 días, un día de esta semana solo tiene dos semanas previas con
    dato: no se juzga como raro (las semanas sin copia no son semanas en cero)."""
    _sembrar(dias_tw=18, dias_meta=20)
    c = _ctx(dias=7)
    assert all(v == {} for v in c["resultados"]["datos"]["raros"].values())
