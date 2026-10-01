"""FuentePlataforma: buscar productos y traer reseñas sobre el registro de plataformas y correr_lote, sin red."""
import json
import os

import pytest

from tests.test_apify_lote import _Resp, _Sesion

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def _corrida(status, run_id, ds):
    return _Resp(200, {"data": {"id": run_id, "status": status, "defaultDatasetId": ds}})


@pytest.fixture()
def entorno(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto")
    monkeypatch.setattr(_http, "dormir", lambda s: None)


def test_registro_y_tarifas(entorno):
    from nicho import fuentes
    from nicho.fuentes.plataforma import FuentePlataforma
    from nicho.fuentes.base import ErrorFuente
    assert fuentes.PLATAFORMAS == ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress") and fuentes.EN_WORKER == fuentes.CONECTADAS + fuentes.PLATAFORMAS
    assert fuentes.NOMBRES["walmart"] == "Walmart" and fuentes.NOMBRES["aliexpress"] == "AliExpress" and fuentes.LLAVES["aliexpress"] == ("APIFY_TOKEN",)
    assert fuentes.por_tipo("aliexpress")().tarifa() == {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": "Reseñas de AliExpress",
                                                         "usd_por_resultado": 0.003, "usd_por_corrida": 0.01}
    f = fuentes.por_tipo("amazon")()
    assert isinstance(f, FuentePlataforma) and f.tipo == "amazon" and f.de_pago is True
    assert fuentes.NOMBRES["meli"] == "Mercado Libre" and fuentes.LLAVES["tiktok_shop"] == ("APIFY_TOKEN",) and fuentes.llaves_faltantes("amazon") == []
    assert f.tarifa()["actor"] == "axesso_data~amazon-reviews-scraper" and f.tarifa_busqueda()["usd_por_resultado"] == 0.003
    with pytest.raises(ErrorFuente):
        FuentePlataforma("magia")
    assert f.tarifa()["usd_por_corrida"] == 0.0


def test_buscar_amazon_guarda_consulta_y_dedup(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    items = _fixture("amazon_busqueda.json") + [_fixture("amazon_busqueda.json")[0]]        # el mismo ASIN dos veces
    s = _Sesion({"/actors/junglee~amazon-crawler/runs": [_corrida("SUCCEEDED", "rb", "db")], "/datasets/db/items": _Resp(200, items)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("amazon")
    etapas = []
    lista = list(f.buscar(["tofflor mot fotsmärta", "ortopediska tofflor"], "SE", 20, avanzar=lambda e, d=None: etapas.append(e)))
    assert [p["fuente_id"] for p in lista] == ["B0AMZ00001", "B0AMZ00002"] and lista[0]["consulta"] == "tofflor mot fotsmärta | ortopediska tofflor"
    assert f.resultados == 4 and f.run_id == "rb" and f.aviso == "" and etapas[0] == "Buscando"
    m, u, kw = s.llamadas[0]
    assert kw["params"] == {"timeout": 1200, "maxItems": 40, "maxTotalChargeUsd": 0.12} and kw["json"]["proxyCountry"] == "SE"


def test_buscar_meli_una_corrida_por_consulta(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/karamelo~mercado-libre-listings-scraper/runs": [_corrida("SUCCEEDED", "r1", "d1"), _corrida("SUCCEEDED", "r2", "d2")],
                 "/datasets/d1/items": _Resp(200, _fixture("meli_busqueda.json")[:1]), "/datasets/d2/items": _Resp(200, _fixture("meli_busqueda.json")[1:])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("meli")
    lista = list(f.buscar(["pantuflas ortopédicas", "pantuflas memory foam"], "CO", 10))
    assert [p["consulta"] for p in lista] == ["pantuflas ortopédicas", "pantuflas memory foam"] and len(f.corridas) == 2


def test_buscar_sin_resultados_y_corrida_fallida(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.base import ErrorFuente
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/unseenuser~tiktok-shop-scraper/runs": [_corrida("FAILED", "rf", "df")], "/datasets/df/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("tiktok_shop")
    with pytest.raises(ErrorFuente) as e:
        list(f.buscar(["cloud slippers"], "US", 5))
    assert "rf" in str(e.value) and f.resultados == 0
    s = _Sesion({"/actors/unseenuser~tiktok-shop-scraper/runs": [_corrida("SUCCEEDED", "rv", "dv")], "/datasets/dv/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert list(FuentePlataforma("tiktok_shop").buscar(["x"], "US", 5)) == []            # vacío no es error


def test_recolectar_amazon_una_corrida_por_producto(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    resenas = _fixture("amazon_resenas.json")
    s = _Sesion({"/actors/axesso_data~amazon-reviews-scraper/runs": [_corrida("SUCCEEDED", "ra", "da"), _corrida("SUCCEEDED", "rb", "db")],
                 "/datasets/da/items": _Resp(200, resenas), "/datasets/db/items": _Resp(200, [{"reviewId": "R9", "text": "Bra.", "rating": 4, "asin": "B0AMZ00002"}])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "B0AMZ00001", "url": "https://www.amazon.se/dp/B0AMZ00001", "titulo": "Ortopediska tofflor"},
                 {"fuente_id": "B0AMZ00002", "url": "https://www.amazon.se/dp/B0AMZ00002", "titulo": "Mjuka tofflor"}]
    f = FuentePlataforma("amazon")
    lista = list(f.recolectar({"productos": productos, "resenas_por_producto": 20, "pais": "SE"}))
    assert [c["fuente_id"] for c in lista] == ["R1AMZ", "R2AMZ", "R9"]
    assert lista[0]["contexto"] == "Ortopediska tofflor" and lista[0]["url"] == "https://www.amazon.se/dp/B0AMZ00001" and lista[0]["puntuacion"] == 5
    assert lista[0]["extra"] == {"producto": "B0AMZ00001", "plataforma": "amazon", "pais": "SE", "mercado": "local"}
    assert lista[2]["contexto"] == "Mjuka tofflor"
    assert f.conteo_por_producto == {"B0AMZ00001": 2, "B0AMZ00002": 1} and f.resultados == 4
    posts = [kw for m, u, kw in s.llamadas if m == "POST"]
    assert [p["json"] for p in posts] == [{"asin": "B0AMZ00001", "domainCode": "se", "maxPages": 2, "sortBy": "recent"},
                                          {"asin": "B0AMZ00002", "domainCode": "se", "maxPages": 2, "sortBy": "recent"}]
    assert posts[0]["params"]["maxItems"] == 20 and posts[0]["params"]["maxTotalChargeUsd"] == 0.02


def test_recolectar_meli_asocia_por_product_id(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/karamelo~mercadolibre-review-scraper/runs": [_corrida("FAILED", "rm", "dm")], "/datasets/dm/items": _Resp(200, _fixture("meli_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "MCO123456789", "url": "https://articulo.mercadolibre.com.co/MCO-123456789-p", "titulo": "Pantuflas"}]
    f = FuentePlataforma("meli")
    lista = list(f.recolectar({"productos": productos, "resenas_por_producto": 50, "pais": "CO"}))
    assert [c["contexto"] for c in lista] == ["Pantuflas", "Pantuflas"] and f.conteo_por_producto == {"MCO123456789": 2}
    assert "FAILED" in f.aviso and "rm" in f.aviso and f.resultados == 3                  # falló pero entregó: aviso, no error


def test_buscar_de_otro_mercado_lee_la_moneda_de_su_sitio(entorno, monkeypatch):
    """Amazon no está en Colombia: busca en amazon.com y un «$» a secas son dólares, no pesos (Parte 4, R5)."""
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    item = {"asin": "B0X", "title": "Water bottle", "price": {"value": 19.99, "currency": "$"}, "url": "https://www.amazon.com/dp/B0X"}
    s = _Sesion({"/actors/junglee~amazon-crawler/runs": [_corrida("SUCCEEDED", "rb", "db")], "/datasets/db/items": _Resp(200, [item])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(FuentePlataforma("amazon").buscar(["water bottle"], "CO", 5))
    assert lista[0]["moneda"] == "USD" and lista[0]["precio"] == 19.99
    assert s.llamadas[0][2]["json"]["categoryOrProductUrls"] == [{"url": "https://www.amazon.com/s?k=water+bottle"}]


def test_recolectar_marca_pais_y_mercado(entorno, monkeypatch):
    """Cada reseña guarda el país del comprador (o el del sitio) y si es del mercado del estudio (Parte 4 §3)."""
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/axlymxp~aliexpress-reviews-scraper/runs": [_corrida("SUCCEEDED", "ra", "da")],
                 "/datasets/da/items": _Resp(200, _fixture("aliexpress_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "3256806541493299", "url": None, "titulo": "Botella 1L"}]
    lista = list(FuentePlataforma("aliexpress").recolectar({"productos": productos, "resenas_por_producto": 5, "pais": "BR"}))
    assert [c["extra"] for c in lista] == [{"producto": "3256806541493299", "plataforma": "aliexpress", "pais": "BR", "mercado": "local"},
                                           {"producto": "3256806541493299", "plataforma": "aliexpress", "pais": "ES", "mercado": "otro"}]
    assert lista[0]["fecha"] == "2026-06-30T00:00:00" and lista[0]["contexto"] == "Botella 1L"
    post = [kw for m, u, kw in s.llamadas if m == "POST"][0]
    assert post["json"]["productUrls"] == ["https://www.aliexpress.com/item/3256806541493299.html"] and post["params"]["maxTotalChargeUsd"] == 0.03
    s = _Sesion({"/actors/apt_marble~walmart-reviews-scraper/runs": [_corrida("SUCCEEDED", "rw", "dw")],
                 "/datasets/dw/items": _Resp(200, _fixture("walmart_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(FuentePlataforma("walmart").recolectar({"productos": [{"fuente_id": "5394318269", "url": None, "titulo": "Botella"}],
                                                         "resenas_por_producto": 5, "pais": "CO"}))
    assert len(lista) == 2 and all(c["extra"]["pais"] == "US" and c["extra"]["mercado"] == "otro" for c in lista)
    assert lista[0]["fecha"] == "2026-05-14T00:00:00"
