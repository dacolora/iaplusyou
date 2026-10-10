"""R9 (spec 2026-10-09: por anuncio solo cuentan los canales con gasto) y lo que ya se pagó o decide plata.

Revisión final de E1 (2026-10-10, guardián de gasto):

- G1. R9 saca de la cuenta lo que el Pixel atribuye a canales sin gasto (orgánico, Klaviyo, Direct). Eso mueve el costo
  por venta de la cuenta y, con él, el veredicto de anuncios cuyos números propios no cambiaron. Un análisis pagado
  antes de R9 se veía «viejo» («desde entonces cambió»), la tarjeta ofrecía «Analizar otra vez» y el anuncio volvía al
  lote: pagar dos veces lo mismo. Desde R9 cada análisis nuevo guarda `foto["metodo"] = 2`; en uno sin esa marca, un
  cambio de veredicto no lo vuelve viejo (solo un 50 % más de gasto).
- G2. R9 nunca llega al decisor de Experimentos: `triple_whale.datos.totales_anuncio` (lo que lee
  `lanzador._mezclar_ventas_triple_whale`) sigue contando el Pixel de un anuncio aunque su canal no tenga gasto en la
  copia.
"""
import pytest
import sqlalchemy as sa

import db
import proyectos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_triple_whale import _conectar, _hace, _tienda
from triple_whale import analisis, datos, panel


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


def _sembrar(dias=10):
    """Tres anuncios de Meta (dos que venden y uno que gasta poco sin vender) y, cada día, 20 pedidos que el Pixel
    atribuye a orgánico (sin gasto): lo que R9 deja fuera."""
    tid = _tienda()
    canal, pixel = [], []
    for d in range(dias):
        for ad, gasto, imp, ped, ing in (("g1", 20, 2000, 1, 120), ("g2", 20, 2000, 1, 100), ("p1", 3, 2000, 0, 0)):
            canal.append({"canal": "facebook-ads", "ad_id": ad, "fecha": _hace(d), "anuncio": f"Anuncio {ad}",
                          "gasto": gasto, "impresiones": imp, "clics": imp // 50})
            pixel.append({"canal": "facebook-ads", "ad_id": ad, "fecha": _hace(d), "pedidos": ped, "ingresos": ing})
        pixel.append({"canal": "organic_and_social", "ad_id": "org", "fecha": _hace(d), "pedidos": 20, "ingresos": 1000})
    datos.reemplazar_anuncios_canal("acme", tid, _hace(dias - 1), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", tid, _hace(dias - 1), _hace(0), pixel)
    return tid


def _sin_r9(cliente, tienda_id):
    """`datos._canales_pagados` de antes de R9: todos los canales de la copia."""
    t = db.tw_anuncio_dia
    return sa.select(t.c.canal).where(t.c.cliente == cliente).group_by(t.c.canal)


def _p1():
    alc = panel.alcance("acme", 0)
    return alc, next(a for a in alc["ev"]["anuncios"] if a["ad_id"] == "p1")


def _pedir(app):  # noqa: F811
    return app["c"].post("/cliente/acme/triple-whale/anuncio/facebook-ads/p1/analizar",
                         data={"dias": "0", "canal": "", "tienda": ""})


def _n_analisis():
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis)).scalar()


def _terminar():
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="hecha"))
        con.execute(db.tw_analisis.update().values(estado="lista", resultado={"frase": "x"}))


def _foto_guardada():
    with db.conectar() as con:
        return con.execute(sa.select(db.tw_analisis.c.foto)).scalar()


def test_un_analisis_nuevo_guarda_el_metodo_del_veredicto(app):  # noqa: F811
    _conectar()
    _sembrar()
    assert _pedir(app).status_code == 302
    assert _foto_guardada()["metodo"] == analisis.METODO_VEREDICTO == 2


def test_un_analisis_pagado_antes_de_r9_no_se_vuelve_a_ofrecer_por_el_veredicto(app, monkeypatch):  # noqa: F811
    """La reproducción del guardián: el anuncio p1 no cambió un solo número, pero R9 le cambia el veredicto."""
    _conectar()
    _sembrar()
    real = datos._canales_pagados
    monkeypatch.setattr(datos, "_canales_pagados", _sin_r9)          # el código de antes de R9
    _, p1 = _p1()
    antes = p1["veredicto"]
    assert _pedir(app).status_code == 302
    _terminar()
    with db.conectar() as con:                                        # la foto de antes de R9 no tenía la marca
        foto = dict(_foto_guardada())
        foto.pop("metodo", None)
        con.execute(db.tw_analisis.update().values(foto=foto))
    monkeypatch.setattr(datos, "_canales_pagados", real)             # se despliega R9
    alc, p1_r9 = _p1()
    assert p1_r9["veredicto"] != antes and p1_r9["m"]["gasto"] == p1["m"]["gasto"]   # lo que mueve R9
    filas = datos.analisis_de_anuncios("acme", [("facebook-ads", "p1")])[("facebook-ads", "p1")]
    e = panel.elegir_analisis(p1_r9, filas, alc)
    assert e["viejo"] is False and e["fresco"] is True and e["ofrecer"] is False
    assert ("facebook-ads", "p1") not in panel.galeria("acme", alc["ev"], "", alcance=alc)["lote"]["elegibles"]
    html = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/p1").data.decode()
    assert "desde entonces cambió" not in html and "Analizar otra vez" not in html
    _pedir(app)                                                       # un segundo clic (una pestaña vieja)
    assert _n_analisis() == 1                                         # no se paga otra vez


def test_sin_la_marca_un_50_por_ciento_mas_de_gasto_sigue_volviendolo_viejo():
    a = {"veredicto": "en_prueba", "m": {"gasto": 160.0}}
    assert not panel.es_viejo(a, {"foto": {"veredicto": "perdedor", "m": {"gasto": 150.0}}})
    assert panel.es_viejo(a, {"foto": {"veredicto": "perdedor", "m": {"gasto": 100.0}}})
    assert panel.es_viejo(a, {"foto": {"veredicto": "en_prueba", "m": {"gasto": 100.0}}})


def test_con_la_marca_un_veredicto_que_cambio_si_lo_vuelve_viejo():
    a = {"veredicto": "en_prueba", "m": {"gasto": 160.0}}
    assert panel.es_viejo(a, {"foto": {"metodo": 2, "veredicto": "perdedor", "m": {"gasto": 150.0}}})
    assert not panel.es_viejo(a, {"foto": {"metodo": 2, "veredicto": "en_prueba", "m": {"gasto": 150.0}}})
    # Una marca rara (texto, None) se lee como la de antes: ante la duda no se ofrece pagar otra vez.
    assert not panel.es_viejo(a, {"foto": {"metodo": "x", "veredicto": "perdedor", "m": {"gasto": 150.0}}})
    assert not panel.es_viejo(a, {"foto": {"metodo": None, "veredicto": "perdedor", "m": {"gasto": 150.0}}})


# ------------------------------------------------------------------------------------------------- G2 ---

def test_el_decisor_sigue_contando_el_pixel_de_un_canal_sin_gasto(base_temporal, monkeypatch):
    """`totales_anuncio` es la lectura del decisor de Experimentos (`lanzador._mezclar_ventas_triple_whale`): R9 no la
    toca. Un anuncio de Meta cuyas filas de canal todavía no llegaron (el canal no tiene gasto en la copia) conserva
    sus pedidos y ventas del Pixel; las lecturas de la pestaña (R9) sí lo dejan fuera."""
    import triple_whale_tiendas
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")       # agregar cifra la llave de la tienda
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme.myshopify.com", None, moneda="USD")  # llave-de-prueba
    datos.reemplazar_anuncios_pixel("acme", tid, _hace(2), _hace(0), [
        {"canal": "facebook-ads", "ad_id": "120", "fecha": _hace(d), "pedidos": 2, "ingresos": 80} for d in range(3)]
        + [{"canal": "klaviyo", "ad_id": "flujo", "fecha": _hace(1), "pedidos": 9, "ingresos": 900}])
    t = datos.totales_anuncio("acme", tid, "facebook-ads", "120", _hace(2))
    assert t is not None and (t["pedidos"], t["ingresos"], t["gasto"]) == (6, 240, 0)
    k = datos.totales_anuncio("acme", tid, "klaviyo", "flujo", _hace(2))
    assert (k["pedidos"], k["ingresos"]) == (9, 900)
    # La pestaña (R9) sí los deja fuera: sin esto la prueba no distinguiría nada.
    assert datos.totales_por_anuncio("acme", tid, _hace(2), _hace(0)) == []
