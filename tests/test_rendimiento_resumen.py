"""«01 Resultados» y «02 Por país» de la pestaña Rendimiento con Meta y mezcla (spec 2026-10-09 R5–R8)."""
from datetime import date, timedelta

import pytest

import db
import idiomas
import triple_whale_tiendas
from meta_rendimiento import cuentas as mcuentas
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


# ------------------------------------------------- ronda de arreglos 1 ---

def _tarjetas(c):
    return {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}


def _sin_copia(c):
    return [bool(d.get("sin_copia")) for d in c["resultados"]["datos"]["dias"]]


def test_con_un_periodo_fijo_todas_cuadra_con_las_filas_de_por_pais(base_temporal):
    """La tienda empezó dentro de los últimos 7 días y Meta antes: lo que cae dentro del periodo cuenta entero (la
    fecha común solo vale para «Desde el inicio»)."""
    _sembrar(dias_tw=5, dias_meta=20)
    c = _ctx(dias=7)
    filas = [f for f in c["por_pais"] if not f["fuera_de_todas"]]
    assert round(_tarjetas(c)["gasto"], 2) == round(sum(f["gasto_usd"] for f in filas), 2) == 50 + 70 + 70
    assert round(_tarjetas(c)["ventas"], 2) == round(sum(f["ventas_usd"] for f in filas), 2) == 150 + 105 + 105


def test_una_fuente_atrasada_no_cuenta_como_ventas_en_cero(base_temporal):
    """Meta de Suecia dejó de copiarse hace 3 días: esos días salen «sin copia» y no se suma solo a las demás."""
    _sembrar()
    mdatos.reemplazar_cuenta_dias("acme", "act_se", _hace(2), _hace(0), [])
    mcuentas.actualizar("acme", "act_se", ultima_copia=f"{_hace(3)}T10:00:00")
    c = _ctx()
    assert _sin_copia(c) == [False, False, True, True, True]      # del hace 4 a hoy
    assert round(_tarjetas(c)["gasto"], 2) == 2 * (10 + 10 + 10)  # solo los dos días que todas ya traen


def test_una_cuenta_en_pausa_con_la_copia_al_dia_no_atrasa_a_las_demas(base_temporal):
    """Sin entrega no hay filas, pero la copia está al día: sus días sin filas son días en cero de verdad."""
    _sembrar()
    mdatos.reemplazar_cuenta_dias("acme", "act_ww", _hace(2), _hace(0), [])
    mcuentas.actualizar("acme", "act_ww", ultima_copia=db.ahora())
    c = _ctx()
    assert _sin_copia(c) == [False] * 5
    assert round(_tarjetas(c)["gasto"], 2) == 50 + 50 + 20


def test_una_tienda_que_no_trajo_sus_ultimos_dias_atrasa_aunque_la_copia_diga_hoy(base_temporal):
    """La sincronización terminó hoy (fecha de copia al día) pero la consulta de la tienda no trajo los últimos 3
    días: la última fila manda."""
    tid = _sembrar()
    twdatos.reemplazar_tienda("acme", tid, _hace(2), _hace(0), [])
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    c = _ctx()
    assert _sin_copia(c) == [False, False, True, True, True]
    assert round(_tarjetas(c)["gasto"], 2) == 2 * (10 + 10 + 10)


def test_fuentes_que_no_se_cruzan_no_rompen_la_seccion(base_temporal):
    """La tienda termina antes de que empiece Meta: no hay ningún día que todas traigan, todos salen «sin copia»."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    for n in range(10, 15):
        twdatos.reemplazar_tienda("acme", tid, _hace(n), _hace(n), [{"fecha": _hace(n), "gasto": 10, "ingresos": 30,
                                                                     "pedidos": 1}])
    _cuentas("acme", ("act_se", "HappyFlops Sweden", "SE"))
    for n in range(0, 6):
        mdatos.reemplazar_cuenta_dias("acme", "act_se", _hace(n), _hace(n), [_dia(_hace(n), 100, 150, compras=2)])
        _tasa(_hace(n), 0.1, "SEK")
    c = _ctx()
    assert c["usd_ok"] is True and all(_sin_copia(c))
    assert _tarjetas(c)["gasto"] == 0


def test_un_dia_sin_montos_no_necesita_tasa_y_uno_con_gasto_si(base_temporal):
    """R6 (migrada del panel viejo de Meta, revisión de la tarea 8): «Todas» con la tienda en USD y Meta en SEK. Un día
    de Meta en 0/0 en una fecha sin tasa no deja «USD no disponible» (no hay nada que convertir), ni en «Resultados»
    ni en «Por país»; el mismo día CON gasto y sin tasa sí, y nunca con una tasa inventada."""
    _sembrar(dias_tw=5, dias_meta=5)                       # tasas de SEK solo en los últimos 5 días
    f = _hace(15)                                          # sin tasa publicada ni una de hasta 4 días antes
    mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 0, 0, compras=0)])
    c = _ctx(dias=30)
    assert c["moneda"] == "USD" and c["usd_ok"] is True and c["resultados"] is not None
    assert round(_tarjetas(c)["gasto"], 2) == 50 + 100
    se = next(x for x in c["por_pais"] if x["entrada"]["clave"] == "SE")
    assert round(se["gasto_usd"], 2) == 50
    mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 100, 0, compras=0)])
    c = _ctx(dias=30)
    assert c["usd_ok"] is False and c["resultados"] is None
    se = next(x for x in c["por_pais"] if x["entrada"]["clave"] == "SE")
    assert se["gasto"] == 600 and se["gasto_usd"] is None
