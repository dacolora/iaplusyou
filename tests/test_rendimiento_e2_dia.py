"""Rendimiento E2 (7/7): el detalle de un día de «Resultados» con Meta y con fuentes mezcladas (spec 2026-10-09 A3,
R6, R7). Una tienda de Triple Whale en Noruega (USD) y una cuenta de Meta en Suecia (SEK, 0,1 USD por corona): un día
de Meta sola va en coronas, «Todas» en dólares con la tasa de ese día (sin tasa, 400: nunca una inventada), los 5
anuncios que más vendieron salen de las dos fuentes por ventas en USD, «nuevo» es su primer día con gasto + 13, el
alcance solo Triple Whale sigue en `triple_whale.panel.contexto_dia` y las consultas no crecen con los anuncios."""
import re
from datetime import date, timedelta

import pytest

import db
import idiomas
import triple_whale_tiendas
from meta_rendimiento import cuentas as mcuentas
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import panel as rend_panel
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_meta_rendimiento import _ad, _dia, _tasa
from triple_whale import datos as twdatos

TOKEN = "t-llave-de-prueba"   # llave-de-prueba
SE, DK = "act_se", "act_dk"
HOY = date.today()


@pytest.fixture(autouse=True)
def _llave_de_cifrado(monkeypatch):
    # `triple_whale_tiendas.agregar` cifra la llave de la tienda con la clave de la app.
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")


@pytest.fixture()
def meta_on(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": TOKEN, "page_id": None})
    return app


def _hace(n):
    return (HOY - timedelta(days=n)).isoformat()


def _sembrar(dias=30, con_tasa=True):
    """`dias` días hasta hoy: la tienda gasta 50 USD y vende 150 con 3 pedidos; la cuenta de Suecia gasta 1 000 SEK y
    reporta 2 000 de valor con 4 compras (en USD: 100 y 200)."""
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=db.ahora())
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"}])
    for n in range(dias):
        f = _hace(n)
        twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 50, "ingresos": 150, "pedidos": 3}])
        mdatos.reemplazar_cuenta_dias("acme", SE, f, f, [_dia(f, 1000, 2000, compras=4)])
        if con_tasa:
            _tasa(f, 0.1, "SEK")
    return tid


def _anuncios_tw(tid, por_dia):
    """`por_dia` = {n (días atrás): [(ad_id, gasto, ingresos)]}: reemplaza la copia de anuncios de la tienda."""
    canal, pixel = [], []
    for n, lista in por_dia.items():
        f = _hace(n)
        for ad, gasto, ingresos in lista:
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "anuncio": f"Anuncio {ad}", "gasto": gasto,
                          "impresiones": 1000})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": f, "pedidos": 1, "ingresos": ingresos})
    desde, hasta = _hace(max(por_dia)), _hace(min(por_dia))
    twdatos.reemplazar_anuncios_canal("acme", tid, desde, hasta, canal)
    twdatos.reemplazar_anuncios_pixel("acme", tid, desde, hasta, pixel)


def _anuncios_meta(por_dia, act=SE, nombres=True):
    """Lo mismo para una cuenta de Meta (`valor` = ingresos), con el nombre de cada anuncio en meta_objeto."""
    filas, ids = [], set()
    for n, lista in por_dia.items():
        f = _hace(n)
        for ad, gasto, valor in lista:
            filas.append(_ad(f, ad, gasto, valor, compras=1))
            ids.add(ad)
    mdatos.reemplazar_anuncio_dias("acme", act, _hace(max(por_dia)), _hace(min(por_dia)), filas)
    if nombres:
        mdatos.guardar_objetos("acme", act, [{"nivel": "anuncio", "objeto_id": ad, "nombre": f"Video {ad}",
                                              "estado": "ACTIVE"} for ad in sorted(ids)])


def _dia_ctx(app, entrada, fecha, **k):  # noqa: F811
    with app["dashboard"].app.test_request_context(), idiomas.en_idioma("es"):
        return rend_panel.dia("acme", date.fromisoformat(fecha), entrada, **k)


def _get(app, q):  # noqa: F811
    return app["c"].get("/cliente/acme/rendimiento/dia?" + q)


# ------------------------------------------------------------------------------------ Meta sola ---

def test_un_dia_de_meta_sola_va_en_su_moneda_con_sus_anuncios(meta_on):
    _sembrar()
    _anuncios_meta({1: [("m1", 100, 300), ("m2", 200, 500), ("m3", 50, 0)], 8: [("m1", 100, 300)]})
    d, motivo = _dia_ctx(meta_on, "SE", _hace(1))
    assert motivo is None and d["fuente"] == "meta"
    stats = {s["etiqueta"]: s["texto"] for s in d["stats"]}
    assert set(stats) == {"Ventas según Meta", "Compras según Meta", "Gasto", "ROAS según Meta"}
    assert "SEK" in stats["Gasto"] and "1000" in stats["Gasto"].replace(".", "").replace(",", "").replace("\xa0", "")
    assert [a["nombre"] for a in d["anuncios"]] == ["Video m2", "Video m1", "Video m3"]      # por valor de compras
    assert all("SEK" in a["ingresos_texto"] for a in d["anuncios"]) and d["canales"] == []
    assert d["comparado"] and d["anterior"] == _hace(2) and d["siguiente"] is None          # hoy va a medias
    r = _get(meta_on, f"entrada=SE&fecha={_hace(1)}")
    html = r.data.decode()
    assert r.status_code == 200 and "Video m2" in html and "Valor de compras según Meta" in html
    assert 'data-twr-ir="tw-galeria"' in html and "tw-cada-anuncio" not in html


def test_a_lo_sumo_cinco_anuncios(meta_on):
    _sembrar()
    _anuncios_meta({1: [(f"m{i}", 10 + i, 100 + i) for i in range(8)]})
    d, _ = _dia_ctx(meta_on, "SE", _hace(1))
    assert [a["nombre"] for a in d["anuncios"]] == [f"Video m{i}" for i in (7, 6, 5, 4, 3)]


# ---------------------------------------------------------------------------------------- mezcla ---

def test_un_dia_mezclado_va_en_usd_con_la_tasa_de_ese_dia(meta_on):
    _sembrar()
    with db.conectar() as con:                                 # ese día la corona vale 0,2 USD (los demás, 0,1)
        con.execute(db.tasa_cambio.update().where(db.tasa_cambio.c.fecha == _hace(1)).values(usd_por_unidad=0.2))
    d, motivo = _dia_ctx(meta_on, "", _hace(1))
    assert motivo is None and d["fuente"] == "mixta"
    stats = {s["etiqueta"]: s for s in d["stats"]}
    # Tienda 50 USD de gasto y 150 de ventas; Suecia 1 000 SEK × 0,2 = 200 USD de gasto y 2 000 × 0,2 = 400 de valor.
    assert stats["Gasto en anuncios"]["texto"].startswith("250") and stats["Ventas"]["texto"].startswith("550")
    assert "USD" in stats["Ventas"]["texto"] and stats["Pedidos"]["texto"] == "7"
    # El mismo día de la semana anterior (tasa 0,1): 50 + 100 de gasto → +66,7 %.
    assert stats["Gasto en anuncios"]["variacion_texto"].startswith("▲")


def test_los_cinco_que_mas_vendieron_salen_de_las_dos_fuentes_por_usd(meta_on):
    tid = _sembrar()
    _anuncios_tw(tid, {1: [("t1", 10, 40), ("t2", 10, 25), ("t3", 10, 5)]})
    _anuncios_meta({1: [("m1", 100, 300), ("m2", 100, 500), ("m3", 100, 100)]})
    d, _ = _dia_ctx(meta_on, "", _hace(1))
    # En USD: m2 50, t1 40, m1 30, t2 25, m3 10, t3 5. Por monto nominal serían m2, m1, m3, t1, t2.
    assert [a["nombre"] for a in d["anuncios"]] == ["Video m2", "Anuncio t1", "Video m1", "Anuncio t2", "Video m3"]
    monedas = [a["ingresos_texto"].split()[-1] for a in d["anuncios"]]
    assert monedas == ["SEK", "USD", "SEK", "USD", "SEK"]                        # cada uno en su moneda
    assert [a["fuente"] for a in d["anuncios"]] == ["meta", "tw", "meta", "tw", "meta"]
    html = _get(meta_on, f"fecha={_hace(1)}").data.decode()
    assert "según Triple Whale" in html and "según Meta" in html and "en la moneda de arriba" in html


def test_varias_cuentas_en_monedas_distintas_no_pierden_un_anuncio_por_su_moneda(meta_on):
    """El tope de la consulta de Meta es por cuenta: seis anuncios en coronas con más valor nominal no dejan fuera al de
    la cuenta en euros, que vale más en dólares."""
    _sembrar()
    mcuentas.elegir("acme", [{"id": SE, "name": "HappyFlops Sweden", "currency": "SEK", "pais": "SE"},
                             {"id": DK, "name": "HappyFlops Denmark", "currency": "EUR", "pais": "DK"}])
    for n in range(30):
        mdatos.reemplazar_cuenta_dias("acme", DK, _hace(n), _hace(n), [_dia(_hace(n), 10, 20, compras=1)])
        _tasa(_hace(n), 1.1, "EUR")
    _anuncios_meta({1: [(f"s{i}", 10, 300 + i) for i in range(6)]})
    _anuncios_meta({1: [("e1", 10, 100)]}, act=DK)
    assert "e1" in [a["ad_id"] for a in mdatos.anuncios_del_dia("acme", [SE, DK], _hace(1), limite=5)]
    d, _ = _dia_ctx(meta_on, "", _hace(1))
    assert d["anuncios"][0]["nombre"] == "Video e1" and d["anuncios"][0]["ingresos_texto"].endswith("EUR")


def test_sin_tasa_ese_dia_es_400_y_no_inventa_usd(meta_on):
    _sembrar()
    with db.conectar() as con:
        con.execute(db.tasa_cambio.delete())
    d, motivo = _dia_ctx(meta_on, "", _hace(1))
    assert d is None and "USD no disponible ese día" in motivo
    r = _get(meta_on, f"fecha={_hace(1)}")
    assert r.status_code == 400 and "USD no disponible ese día" in r.data.decode()
    # Meta sola no necesita USD: va en coronas.
    assert _get(meta_on, f"entrada=SE&fecha={_hace(1)}").status_code == 200


def test_el_dia_anterior_sin_tasa_no_se_compara(meta_on):
    _sembrar()
    with db.conectar() as con:                  # solo ayer tiene tasa: hace 8 días queda a más de 4 días de una
        con.execute(db.tasa_cambio.delete().where(db.tasa_cambio.c.fecha != _hace(1)))
    d, motivo = _dia_ctx(meta_on, "", _hace(1))
    assert motivo is None and d["comparado"] is None and all(not s["variacion_texto"] for s in d["stats"])


# ------------------------------------------------------------------------------------- el rango ---

@pytest.mark.parametrize("entrada", ["SE", ""])
def test_un_dia_fuera_del_rango_es_400(meta_on, entrada):
    _sembrar(dias=10)
    q = f"entrada={entrada}&fecha="
    assert _get(meta_on, q + _hace(0)).status_code == 400                  # hoy, a medias
    assert _get(meta_on, q + _hace(-1)).status_code == 400                 # mañana
    assert _get(meta_on, q + _hace(10)).status_code == 400                 # antes de la copia
    assert _get(meta_on, q + _hace(9)).status_code == 200                  # el primer día
    assert _get(meta_on, q + "ayer").status_code == 400
    assert _get(meta_on, f"entrada={entrada}").status_code == 400


def test_la_mezcla_arranca_en_el_inicio_comun(meta_on):
    """R7: con la tienda desde hace 30 días y la cuenta desde hace 10, un día de hace 20 en «Todas» sumaría solo la
    tienda: 400. En Noruega sola (solo Triple Whale) sí existe."""
    tid = _sembrar(dias=30)
    with db.conectar() as con:
        con.execute(db.meta_cuenta_dia.delete().where(db.meta_cuenta_dia.c.fecha < _hace(9)))
    assert _get(meta_on, f"fecha={_hace(20)}").status_code == 400
    assert _get(meta_on, f"fecha={_hace(9)}").status_code == 200
    assert _get(meta_on, f"entrada=NO&fecha={_hace(20)}").status_code == 200
    assert tid


def test_un_dia_que_una_fuente_todavia_no_trae_es_400(meta_on):
    """La cuenta de Meta se atrasó: su última fila y su última copia son de hace 3 días. La gráfica no abre esos días
    (van «sin copia») y la ruta tampoco: sumar solo la tienda daría una caída que no existe."""
    _sembrar()
    with db.conectar() as con:
        con.execute(db.meta_cuenta_dia.delete().where(db.meta_cuenta_dia.c.fecha > _hace(3)))
    assert _get(meta_on, f"fecha={_hace(1)}").status_code == 400
    d, motivo = _dia_ctx(meta_on, "", _hace(3))
    assert motivo is None and d["siguiente"] is None


# --------------------------------------------------------------------------------------- nuevo ---

def test_nuevo_es_hasta_el_primer_dia_con_gasto_mas_13(meta_on):
    """La copia de anuncios arranca hace 29 días con un anuncio viejo; `m_nuevo` gasta por primera vez hace 15 días:
    es nuevo hasta hace 2 días (15 − 13) y ya no hace 1."""
    _sembrar()
    _anuncios_meta({n: [("viejo", 10, 10)] + ([("m_nuevo", 10, 50)] if n <= 15 else []) for n in range(1, 30)})
    nuevo = {n: {a["nombre"]: a["nuevo"] for a in _dia_ctx(meta_on, "SE", _hace(n))[0]["anuncios"]} for n in (2, 1)}
    assert nuevo[2] == {"Video m_nuevo": True, "Video viejo": False}
    assert nuevo[1] == {"Video m_nuevo": False, "Video viejo": False}
    assert _dia_ctx(meta_on, "SE", _hace(15))[0]["arrancaron"] == 1
    assert _dia_ctx(meta_on, "SE", _hace(14))[0]["arrancaron"] == 0


def test_en_los_primeros_14_dias_de_la_copia_no_hay_nuevos_ni_arranques(meta_on):
    _sembrar()
    _anuncios_meta({n: [("a", 10, 50)] for n in range(1, 11)})          # la copia de anuncios: hace 10 días
    d, _ = _dia_ctx(meta_on, "SE", _hace(10))
    assert d["arrancaron"] is None and not any(a["nuevo"] for a in d["anuncios"])
    assert "arrancó" not in _get(meta_on, f"entrada=SE&fecha={_hace(10)}").data.decode()


def test_en_la_mezcla_cada_anuncio_toma_la_antiguedad_de_su_copia(meta_on):
    """La copia de la tienda tiene 30 días (antigüedad conocida) y la de Meta 10 (no): el anuncio nuevo de Triple Whale
    se marca y el de Meta no; cuántos arrancaron no se sabe (una de las dos copias no lo sabe)."""
    tid = _sembrar()
    _anuncios_tw(tid, {n: [("t_viejo", 10, 10)] + ([("t_nuevo", 10, 40)] if n <= 2 else []) for n in range(1, 30)})
    _anuncios_meta({n: [("m_nuevo", 10, 300)] for n in range(1, 11)})
    d, _ = _dia_ctx(meta_on, "", _hace(1))
    nuevo = {a["nombre"]: a["nuevo"] for a in d["anuncios"]}
    assert nuevo == {"Anuncio t_nuevo": True, "Video m_nuevo": False, "Anuncio t_viejo": False}
    assert d["arrancaron"] is None


def test_un_dia_sin_anuncios_en_la_copia_no_dice_que_ninguno_gasto(meta_on):
    """La cuenta gastó ese día pero la copia de anuncios (90 días) ya no lo tiene."""
    _sembrar()
    d, _ = _dia_ctx(meta_on, "SE", _hace(20))
    assert d["anuncios"] == [] and d["anuncios_fuera"] is True
    html = _get(meta_on, f"entrada=SE&fecha={_hace(20)}").data.decode()
    assert "ya no están en la copia" in html and "ningún anuncio tuvo gasto" not in html


# ------------------------------------------------------------------------------ solo Triple Whale ---

def test_solo_triple_whale_es_el_detalle_de_siempre(meta_on):
    tid = _sembrar()
    _anuncios_tw(tid, {1: [("t1", 10, 40)]})
    nuevo = _get(meta_on, f"entrada=NO&fecha={_hace(1)}")
    viejo = meta_on["c"].get(f"/cliente/acme/triple-whale/dia?tienda={tid}&fecha={_hace(1)}")
    assert nuevo.status_code == viejo.status_code == 200 and nuevo.data == viejo.data
    assert "tw-cada-anuncio" in nuevo.data.decode()
    # El panel de una entrada solo Triple Whale sigue pidiendo el día a la ruta de Triple Whale.
    html = meta_on["c"].get("/cliente/acme/rendimiento/panel?entrada=NO").data.decode()
    assert f"/cliente/acme/triple-whale/dia?tienda={tid}" in html


def test_el_panel_con_meta_y_mezcla_ofrece_abrir_dias(meta_on):
    _sembrar()
    for entrada in ("SE", ""):
        html = meta_on["c"].get(f"/cliente/acme/rendimiento/panel?entrada={entrada}").data.decode()
        datos = re.search(r'id="tw-resultados-datos">(.*?)</script>', html, re.S).group(1)
        assert f'"url_dia": "/cliente/acme/rendimiento/dia?entrada={entrada}"' in datos.replace("\\u0026", "&")
        assert 'class="twr-dia" data-twr-dia' in html and "Ver qué pasó" in html


# ---------------------------------------------------------------------------- consultas y seguridad ---

def _contar(fn):
    from tests.test_escala import _Consultas
    with _Consultas() as c:
        fn()
    return c.n


@pytest.mark.parametrize("entrada", ["SE", ""])
def test_las_consultas_no_crecen_con_los_anuncios(meta_on, entrada):
    tid = _sembrar()
    url = f"/cliente/acme/rendimiento/dia?entrada={entrada}&fecha={_hace(1)}"

    def pedir():
        assert meta_on["c"].get(url).status_code == 200

    _anuncios_tw(tid, {1: [(f"t{i}", 10, i) for i in range(3)]})
    _anuncios_meta({1: [(f"m{i}", 10, i) for i in range(3)]})
    pedir()                                  # la primera petición llena cachés del proceso
    pocos = _contar(pedir)
    _anuncios_tw(tid, {1: [(f"t{i}", 10, i) for i in range(40)]})
    _anuncios_meta({1: [(f"m{i}", 10, i) for i in range(40)]})
    muchos = _contar(pedir)
    assert pocos == muchos, (pocos, muchos)


def test_una_entrada_ajena_no_lee_nada(meta_on):
    """La cuenta de otro proyecto (y su entrada) no existen para acme: 400 y ni una cifra suya."""
    _sembrar()
    mcuentas.elegir("otro", [{"id": "act_otro", "name": "Cuenta ajena", "currency": "SEK", "pais": "FI"}])
    mdatos.reemplazar_cuenta_dias("otro", "act_otro", _hace(1), _hace(1), [_dia(_hace(1), 777, 999)])
    mdatos.reemplazar_anuncio_dias("otro", "act_otro", _hace(1), _hace(1), [_ad(_hace(1), "ajeno", 777, 999)])
    for entrada in ("FI", "cuenta:act_otro", "<script>"):
        r = _get(meta_on, f"entrada={entrada}&fecha={_hace(1)}")
        assert r.status_code == 400 and "777" not in r.data.decode() and "ajeno" not in r.data.decode()
    d, _ = _dia_ctx(meta_on, "", _hace(1))
    assert "ajeno" not in [a["ad_id"] for a in d["anuncios"]]
    # Y el día de otro proyecto no se pide desde una sesión de acme.
    from tests.test_rutas_meta_rendimiento import _como_cliente
    r = _como_cliente(meta_on).get(f"/cliente/otro/rendimiento/dia?entrada=FI&fecha={_hace(1)}")
    assert r.status_code in (302, 403, 404)


def test_el_dia_es_solo_get(meta_on):
    _sembrar()
    r = meta_on["c"].post(f"/cliente/acme/rendimiento/dia?entrada=SE&fecha={_hace(1)}",
                          headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 405


def test_sin_nada_conectado_es_400(app):  # noqa: F811
    assert _get(app, f"fecha={_hace(1)}").status_code == 400
