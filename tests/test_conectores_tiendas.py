"""Conectores con API: Shopify (GraphQL), WooCommerce (REST) y MercadoLibre
(OAuth). Sin red: `requests.Session` se reemplaza por una sesión falsa que
despacha por método/URL/cuerpo y anota cada llamada."""
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import conectores
from conectores import _http, base, meli, shopify, woo
from conectores.base import ErrorConector

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nombre):
    with open(os.path.join(FIXTURES, nombre), encoding="utf-8") as f:
        return json.load(f)


# --- sesión falsa ------------------------------------------------------------

class Respuesta:
    def __init__(self, status=200, cuerpo=None, headers=None, texto=None):
        self.status_code = status
        self._cuerpo = cuerpo
        self.headers = dict(headers or {})
        self.text = texto if texto is not None else (json.dumps(cuerpo) if cuerpo is not None else "")

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin JSON")
        return self._cuerpo


class SesionFalsa:
    """`manejador(metodo, url, kw) -> Respuesta | Exception`. Guarda cada
    llamada en `llamadas` (lista de dicts con metodo, url, params, json,
    data, headers, auth, timeout)."""

    def __init__(self, manejador):
        self.manejador = manejador
        self.llamadas = []

    def request(self, metodo, url, **kw):
        llamada = {"metodo": metodo.upper(), "url": url, "params": kw.get("params") or {},
                   "json": kw.get("json"), "data": kw.get("data"), "headers": kw.get("headers") or {},
                   "auth": kw.get("auth"), "timeout": kw.get("timeout")}
        self.llamadas.append(llamada)
        resultado = self.manejador(llamada["metodo"], url, llamada)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def close(self):
        pass


@pytest.fixture
def sesion(monkeypatch):
    """`sesion(manejador) -> SesionFalsa` instalada como `requests.Session`."""
    creadas = []

    def instalar(manejador):
        s = SesionFalsa(manejador)
        creadas.append(s)
        monkeypatch.setattr(requests, "Session", lambda: s)
        return s

    monkeypatch.setattr(_http.time, "sleep", lambda *_: None)
    return instalar


# --- registro ---------------------------------------------------------------

def test_por_tipo_devuelve_las_clases():
    assert conectores.por_tipo("shopify") is shopify.Shopify
    assert conectores.por_tipo("woo") is woo.Woo
    assert conectores.por_tipo("meli") is meli.Meli
    assert shopify.Shopify.tiene_pedidos and shopify.Shopify.soporta_utm
    assert woo.Woo.tiene_pedidos and woo.Woo.soporta_utm
    assert meli.Meli.tiene_pedidos and not meli.Meli.soporta_utm


def test_limpiar_html():
    assert base.limpiar_html("<p>Espejo <b>biselado</b> de 60&nbsp;cm.<br>Marco</p>") == "Espejo biselado de 60 cm. Marco"
    assert base.limpiar_html(None) == ""


# =============================================================================
# Shopify
# =============================================================================

TOKEN_SHOPIFY = "shpat_secreto_de_prueba_123"
CRED_SHOPIFY = {"dominio": "vidrios-demo.myshopify.com", "token": TOKEN_SHOPIFY}
URL_GRAPHQL = "https://vidrios-demo.myshopify.com/admin/api/2025-07/graphql.json"


def manejador_shopify(metodo, url, kw):
    assert metodo == "POST" and url == URL_GRAPHQL
    assert kw["headers"]["X-Shopify-Access-Token"] == TOKEN_SHOPIFY
    query = kw["json"]["query"]
    variables = kw["json"].get("variables") or {}
    if "shop {" in query:
        return Respuesta(200, fixture("shopify_shop.json"))
    if "products(" in query:
        assert variables["first"] == 50
        if variables.get("after"):
            return Respuesta(200, fixture("shopify_products_p2.json"))
        return Respuesta(200, fixture("shopify_products_p1.json"))
    if "orders(" in query:
        assert variables["query"] == "created_at:>=2026-09-01"
        return Respuesta(200, fixture("shopify_orders.json"))
    raise AssertionError("query inesperada")


def test_shopify_valida_credenciales():
    with pytest.raises(ValueError) as ei:
        shopify.Shopify({"dominio": "x.myshopify.com"})
    assert "token" in str(ei.value)
    with pytest.raises(ValueError):
        shopify.Shopify({"token": "a"})
    c = shopify.Shopify({"dominio": "https://Tienda.myshopify.com/", "token": "a"})
    assert c.dominio == "tienda.myshopify.com"


def test_shopify_lista_productos_pagina_y_moneda_una_vez(sesion):
    s = sesion(manejador_shopify)
    productos = shopify.Shopify(CRED_SHOPIFY).listar_productos()
    assert [p["fuente_id"] for p in productos] == ["8811", "8812", "8813"]
    queries = [c["json"]["query"] for c in s.llamadas]
    assert sum("shop {" in q for q in queries) == 1
    assert sum("products(" in q for q in queries) == 2
    assert s.llamadas[2]["json"]["variables"]["after"] == "eyJsYXN0X2lkIjo4ODEyfQ=="
    assert all(c["timeout"] == 30 for c in s.llamadas)
    p = productos[0]
    assert tuple(p.keys()) == base.CLAVES_PRODUCTO
    assert p["nombre"] == "Espejo redondo 60cm"
    assert p["descripcion"] == "Espejo biselado de 60 cm. Marco negro."
    assert p["precio"] == 189900.0 and p["moneda"] == "COP"
    assert p["url_compra"] == "https://vidriosdemo.com/products/espejo-redondo-60cm"
    assert p["fotos"] == ["https://cdn.shopify.com/s/files/espejo-1.jpg", "https://cdn.shopify.com/s/files/espejo-2.jpg"]
    assert p["url_imagen_principal"] == "https://cdn.shopify.com/s/files/espejo-1.jpg"
    assert p["categoria"] == "Espejos"
    assert p["extra"]["sku"] == "ESP-60" and p["extra"]["handle"] == "espejo-redondo-60cm"
    # sin onlineStoreUrl -> url armada con el handle; sin imágenes -> listas vacías
    p2 = productos[1]
    assert p2["url_compra"] == "https://vidrios-demo.myshopify.com/products/vidrio-templado-8mm"
    assert p2["fotos"] == [] and p2["url_imagen_principal"] is None and p2["categoria"] is None
    assert p2["descripcion"] == "" and p2["precio"] == 95000.0


def test_shopify_pedidos_desde_parsea_utm(sesion):
    sesion(manejador_shopify)
    pedidos = shopify.Shopify(CRED_SHOPIFY).pedidos_desde("2026-09-01T00:00:00")
    assert [p["fuente_id"] for p in pedidos] == ["5501", "5502"]
    p = pedidos[0]
    assert tuple(p.keys()) == base.CLAVES_PEDIDO
    assert p["fecha"] == "2026-09-10T14:22:05"
    assert p["total"] == 189900.0 and p["moneda"] == "COP"
    assert p["utm_content"] == "pieza-7"
    assert p["items"] == [{"sku": "ESP-60", "nombre": "Espejo redondo 60cm", "cantidad": 1, "precio": 189900.0}]
    assert pedidos[1]["utm_content"] is None
    assert pedidos[1]["items"][0]["sku"] is None and pedidos[1]["items"][0]["cantidad"] == 2


@pytest.mark.parametrize("landing, esperado", [
    ("/products/x?utm_content=pieza-3", "pieza-3"),
    ("https://t.com/?a=1&utm_content=abc%20d", "abc d"),
    ("https://t.com/products/x", None),
    ("", None), (None, None),
    ("/x?utm_content=", None),
])
def test_shopify_utm_content_de(landing, esperado):
    assert shopify.utm_content_de(landing) == esperado


def test_shopify_probar(sesion):
    sesion(manejador_shopify)
    r = shopify.Shopify(CRED_SHOPIFY).probar()
    assert r["ok"] is True and r["nombre"] == "Vidrios Demo"
    assert "COP" in r["detalle"]


def test_shopify_401_error_sin_token(sesion):
    sesion(lambda m, u, kw: Respuesta(401, {"errors": "[API] Invalid API key or access token"}))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).listar_productos()
    assert "read_products/read_orders" in ei.value.usuario
    assert TOKEN_SHOPIFY not in ei.value.usuario
    assert "Invalid API key" not in ei.value.usuario


def test_shopify_errores_graphql(sesion):
    sesion(lambda m, u, kw: Respuesta(200, {"errors": [{"message": "Field 'foo' doesn't exist on type 'Product'",
                                                        "extensions": {"code": "undefinedField"}}]}))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).probar()
    assert "Shopify devolvió un error" in ei.value.usuario
    assert TOKEN_SHOPIFY not in ei.value.usuario
    sesion(lambda m, u, kw: Respuesta(200, {"errors": [{"message": "Access denied for orders field.",
                                                        "extensions": {"code": "ACCESS_DENIED"}}]}))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).pedidos_desde("2026-09-01")
    assert "read_products/read_orders" in ei.value.usuario
    sesion(lambda m, u, kw: Respuesta(200, {"data": {"shop": None, "x": {"userErrors": [{"message": "no"}]}}}))
    with pytest.raises(ErrorConector):
        shopify.Shopify(CRED_SHOPIFY).probar()


def test_shopify_429_reintenta_una_vez(sesion, monkeypatch):
    esperas = []
    monkeypatch.setattr(_http.time, "sleep", esperas.append)
    contador = {"n": 0}

    def manejador(m, u, kw):
        contador["n"] += 1
        if contador["n"] == 1:
            return Respuesta(429, {"errors": "Throttled"}, headers={"Retry-After": "2.0"})
        return Respuesta(200, fixture("shopify_shop.json"))

    s = sesion(manejador)
    assert shopify.Shopify(CRED_SHOPIFY).probar()["nombre"] == "Vidrios Demo"
    assert len(s.llamadas) == 2 and esperas == [2.0]


def test_429_dos_veces_es_error_y_espera_tope_5s(sesion, monkeypatch):
    esperas = []
    monkeypatch.setattr(_http.time, "sleep", esperas.append)
    s = sesion(lambda m, u, kw: Respuesta(429, {"errors": "Throttled"}, headers={"Retry-After": "120"}))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).probar()
    assert "429" in ei.value.usuario and len(s.llamadas) == 2 and esperas == [5.0]


def test_5xx_y_timeout_reintentan_una_vez(sesion):
    contador = {"n": 0}

    def manejador(m, u, kw):
        contador["n"] += 1
        if contador["n"] == 1:
            return Respuesta(503, None, texto="<html>bad gateway</html>")
        return Respuesta(200, fixture("shopify_shop.json"))

    s = sesion(manejador)
    assert shopify.Shopify(CRED_SHOPIFY).probar()["ok"]
    assert len(s.llamadas) == 2

    s = sesion(lambda m, u, kw: Respuesta(502, None, texto="<html>bad gateway</html>"))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).probar()
    assert "502" in ei.value.usuario and "<html>" not in ei.value.usuario and len(s.llamadas) == 2

    contador["n"] = 0

    def con_timeout(m, u, kw):
        contador["n"] += 1
        if contador["n"] == 1:
            return requests.exceptions.Timeout("lento")
        return Respuesta(200, fixture("shopify_shop.json"))

    s = sesion(con_timeout)
    assert shopify.Shopify(CRED_SHOPIFY).probar()["ok"] and len(s.llamadas) == 2

    s = sesion(lambda m, u, kw: requests.exceptions.Timeout("lento"))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).probar()
    assert "no respondió a tiempo" in ei.value.usuario and len(s.llamadas) == 2

    sesion(lambda m, u, kw: requests.exceptions.ConnectionError("dns"))
    with pytest.raises(ErrorConector) as ei:
        shopify.Shopify(CRED_SHOPIFY).probar()
    assert "No se pudo conectar" in ei.value.usuario


# =============================================================================
# WooCommerce
# =============================================================================

CRED_WOO = {"url": "https://tienda.ejemplo.com/", "ck": "ck_prueba_111", "cs": "cs_prueba_secreto_222"}
API_WOO = "https://tienda.ejemplo.com/wp-json/wc/v3/"


def manejador_woo(metodo, url, kw):
    assert metodo == "GET" and url.startswith(API_WOO)
    assert kw["auth"] == ("ck_prueba_111", "cs_prueba_secreto_222")
    ruta = url[len(API_WOO):]
    params = kw["params"]
    if ruta == "settings/general":
        return Respuesta(200, fixture("woo_settings.json"))
    if ruta == "products":
        assert params["status"] == "publish" and params["per_page"] == 50
        pagina = params["page"]
        nombre = "woo_products_p1.json" if pagina == 1 else "woo_products_p2.json"
        return Respuesta(200, fixture(nombre), headers={"X-WP-TotalPages": "2", "X-WP-Total": "3"})
    if ruta == "orders":
        assert params["after"] == "2026-09-01T00:00:00" and params["status"] == "processing,completed"
        return Respuesta(200, fixture("woo_orders.json"), headers={"X-WP-TotalPages": "1"})
    raise AssertionError(f"ruta inesperada {ruta}")


def test_woo_valida_credenciales():
    with pytest.raises(ValueError) as ei:
        woo.Woo({"url": "http://tienda.com", "ck": "a", "cs": "b"})
    assert "https" in str(ei.value)
    with pytest.raises(ValueError):
        woo.Woo({"url": "https://tienda.com", "ck": "a"})
    with pytest.raises(ValueError):
        woo.Woo({"ck": "a", "cs": "b"})
    assert woo.Woo(CRED_WOO).url == "https://tienda.ejemplo.com"


def test_woo_lista_productos_pagina_moneda_y_strip_html(sesion):
    s = sesion(manejador_woo)
    productos = woo.Woo(CRED_WOO).listar_productos()
    assert [p["fuente_id"] for p in productos] == ["301", "302", "303"]
    rutas = [c["url"][len(API_WOO):] for c in s.llamadas]
    assert rutas.count("settings/general") == 1 and rutas.count("products") == 2
    assert [c["params"]["page"] for c in s.llamadas if c["params"].get("page")] == [1, 2]
    p = productos[0]
    assert tuple(p.keys()) == base.CLAVES_PRODUCTO
    assert p["descripcion"] == "Espejo biselado de 60 cm. Marco negro."
    assert p["precio"] == 189900.0 and p["moneda"] == "COP"
    assert p["categoria"] == "Espejos"
    assert p["url_compra"] == "https://tienda.ejemplo.com/producto/espejo-redondo-60cm/"
    assert p["fotos"] == ["https://tienda.ejemplo.com/wp-content/uploads/espejo-1.jpg",
                          "https://tienda.ejemplo.com/wp-content/uploads/espejo-2.jpg"]
    assert p["url_imagen_principal"] == p["fotos"][0]
    assert productos[1]["categoria"] is None and productos[1]["fotos"] == []
    assert productos[2]["nombre"] == "Repisa flotante de vidrio"


def test_woo_una_sola_pagina_sin_cabecera(sesion):
    s = sesion(lambda m, u, kw: Respuesta(200, fixture("woo_settings.json") if "settings" in u
                                          else fixture("woo_products_p2.json")))
    assert len(woo.Woo(CRED_WOO).listar_productos()) == 1
    assert sum("products" in c["url"] for c in s.llamadas) == 1


def test_woo_pedidos_desde_utm_de_meta_data(sesion):
    sesion(manejador_woo)
    pedidos = woo.Woo(CRED_WOO).pedidos_desde("2026-09-01")
    assert [p["fuente_id"] for p in pedidos] == ["7101", "7102"]
    assert tuple(pedidos[0].keys()) == base.CLAVES_PEDIDO
    assert pedidos[0]["utm_content"] == "pieza-7"
    assert pedidos[0]["fecha"] == "2026-09-10T14:22:05" and pedidos[0]["total"] == 189900.0
    assert pedidos[0]["moneda"] == "COP"
    assert pedidos[0]["items"] == [{"sku": "ESP-60", "nombre": "Espejo redondo 60cm", "cantidad": 1, "precio": 189900.0}]
    assert pedidos[1]["utm_content"] is None
    assert pedidos[1]["items"][0]["sku"] is None


def test_woo_probar_y_errores(sesion):
    sesion(manejador_woo)
    r = woo.Woo(CRED_WOO).probar()
    assert r["ok"] and r["nombre"] == "tienda.ejemplo.com" and "COP" in r["detalle"]

    sesion(lambda m, u, kw: Respuesta(401, {"code": "woocommerce_rest_cannot_view",
                                            "message": "Sorry, you cannot list resources."}))
    with pytest.raises(ErrorConector) as ei:
        woo.Woo(CRED_WOO).listar_productos()
    assert "Consumer key/secret" in ei.value.usuario
    assert "cs_prueba_secreto_222" not in ei.value.usuario and "ck_prueba_111" not in ei.value.usuario
    assert "Sorry" not in ei.value.usuario

    sesion(lambda m, u, kw: Respuesta(404, None, texto="<html>not found</html>"))
    with pytest.raises(ErrorConector) as ei:
        woo.Woo(CRED_WOO).probar()
    assert "404" in ei.value.usuario and "<html>" not in ei.value.usuario


# =============================================================================
# MercadoLibre
# =============================================================================

TOKEN_MELI = "APP_USR-token-viejo-secreto"
API_MELI = "https://api.mercadolibre.com/"


def cred_meli(minutos_para_vencer=120):
    vence = datetime.now(timezone.utc) + timedelta(minutes=minutos_para_vencer)
    return {"access_token": TOKEN_MELI, "refresh_token": "TG-refresh-viejo", "user_id": "123456",
            "expira_en": vence.isoformat(timespec="seconds"), "site_id": "MCO"}


def manejador_meli(metodo, url, kw):
    ruta = url[len(API_MELI):]
    if ruta == "oauth/token":
        assert metodo == "POST"
        assert kw["data"]["client_id"] == "app-id-prueba" and kw["data"]["client_secret"] == "secreto-prueba"
        return Respuesta(200, fixture("meli_token.json"))
    assert metodo == "GET"
    assert kw["headers"]["Authorization"].startswith("Bearer ")
    params = kw["params"]
    if ruta == "users/me":
        return Respuesta(200, {"id": 123456, "nickname": "VIDRIOSDEMO", "site_id": "MCO"})
    if ruta == "users/123456/items/search":
        assert params["status"] == "active" and params["limit"] == 50
        return Respuesta(200, fixture("meli_items_search.json"))
    if ruta == "items":
        pedidos = params["ids"].split(",")
        assert len(pedidos) <= 20 and params["attributes"] == meli.ATRIBUTOS_ITEM
        por_id = {}
        for e in fixture("meli_items_batch.json"):
            cuerpo = e["body"]
            clave = cuerpo.get("id") or cuerpo["message"].split("id ")[1].split(" ")[0]
            por_id[clave] = e
        return Respuesta(200, [por_id[i] for i in pedidos])
    if ruta.startswith("items/") and ruta.endswith("/description"):
        return Respuesta(200, {"plain_text": "Descripción larga de " + ruta.split("/")[1], "text": ""})
    if ruta == "orders/search":
        assert params["seller"] == "123456" and params["sort"] == "date_desc"
        assert params["order.date_created.from"] == "2026-09-01T00:00:00.000-00:00"
        return Respuesta(200, fixture("meli_orders.json"))
    raise AssertionError(f"ruta inesperada {ruta}")


@pytest.fixture
def env_meli(monkeypatch):
    monkeypatch.setenv("MELI_APP_ID", "app-id-prueba")
    monkeypatch.setenv("MELI_SECRET", "secreto-prueba")
    monkeypatch.delenv("MELI_AUTH_HOST", raising=False)


def test_meli_valida_credenciales():
    with pytest.raises(ValueError) as ei:
        meli.Meli({"access_token": "a", "user_id": "1"})
    assert "refresh_token" in str(ei.value)
    c = meli.Meli(cred_meli())
    assert c.credenciales_actualizadas is None and c.cargar_descripciones is False


def test_meli_lista_productos_en_lotes_de_20_sin_descripciones(sesion, env_meli):
    s = sesion(manejador_meli)
    c = meli.Meli(cred_meli())
    productos = c.listar_productos()
    assert len(productos) == 24  # 25 ids, uno responde 404
    rutas = [c_["url"][len(API_MELI):] for c_ in s.llamadas]
    assert rutas.count("users/123456/items/search") == 1
    assert rutas.count("items") == 2
    lotes = [c_["params"]["ids"].split(",") for c_ in s.llamadas if c_["url"].endswith("/items")]
    assert [len(l) for l in lotes] == [20, 5]
    assert not any("/description" in r for r in rutas)
    assert "oauth/token" not in rutas and c.credenciales_actualizadas is None
    p = productos[0]
    assert tuple(p.keys()) == base.CLAVES_PRODUCTO
    assert p["fuente_id"] == "MCO1001" and p["nombre"] == "Espejo redondo 60cm #1"
    assert p["precio"] == 95000.0 and p["moneda"] == "COP"
    assert p["url_compra"] == "https://articulo.mercadolibre.com.co/MCO1001-producto-1"
    assert p["fotos"] == ["https://http2.mlstatic.com/D_0a-O.jpg", "https://http2.mlstatic.com/D_0b-O.jpg"]
    assert p["descripcion"] == "" and p["extra"]["descripcion_cargada"] is False
    assert p["extra"]["available_quantity"] == 5 and p["categoria"] == "MCO1234"
    assert "MCO1013" not in [q["fuente_id"] for q in productos]


def test_meli_carga_descripciones_solo_si_se_pide(sesion, env_meli):
    s = sesion(manejador_meli)
    productos = meli.Meli(cred_meli(), cargar_descripciones=True).listar_productos()
    assert sum("/description" in c["url"] for c in s.llamadas) == 24
    assert productos[0]["descripcion"] == "Descripción larga de MCO1001"
    assert productos[0]["extra"]["descripcion_cargada"] is True


def test_meli_pagina_ids_por_offset(sesion, env_meli):
    def manejador(metodo, url, kw):
        ruta = url[len(API_MELI):]
        if ruta == "users/123456/items/search":
            offset = kw["params"]["offset"]
            ids = [f"MCO9{n:03d}" for n in range(offset, min(offset + 50, 60))]
            return Respuesta(200, {"results": ids, "paging": {"total": 60, "offset": offset, "limit": 50}})
        if ruta == "items":
            return Respuesta(200, [{"code": 200, "body": {"id": i, "title": "Item " + i, "price": 10,
                                                         "currency_id": "COP", "permalink": "https://m/" + i,
                                                         "pictures": [], "category_id": "X", "available_quantity": 1}}
                                   for i in kw["params"]["ids"].split(",")])
        raise AssertionError(ruta)

    s = sesion(manejador)
    productos = meli.Meli(cred_meli()).listar_productos()
    assert len(productos) == 60
    offsets = [c["params"]["offset"] for c in s.llamadas if c["url"].endswith("/items/search")]
    assert offsets == [0, 50]
    assert sum(c["url"].endswith("/items") for c in s.llamadas) == 3


def test_meli_pedidos_desde_sin_utm(sesion, env_meli):
    sesion(manejador_meli)
    pedidos = meli.Meli(cred_meli()).pedidos_desde("2026-09-01")
    assert [p["fuente_id"] for p in pedidos] == ["2000009001", "2000009000"]
    p = pedidos[1]
    assert tuple(p.keys()) == base.CLAVES_PEDIDO
    assert p["fecha"] == "2026-09-10T14:22:05" and p["total"] == 189900.0 and p["moneda"] == "COP"
    assert p["items"] == [{"sku": "ESP-60", "nombre": "Espejo redondo 60cm", "cantidad": 1, "precio": 189900.0}]
    assert all(q["utm_content"] is None for q in pedidos)
    assert pedidos[0]["items"][0]["sku"] == "MCO1002"


def test_meli_refresca_token_si_vence_pronto(sesion, env_meli):
    s = sesion(manejador_meli)
    c = meli.Meli(cred_meli(minutos_para_vencer=3))
    r = c.probar()
    assert r["ok"] and r["nombre"] == "VIDRIOSDEMO"
    assert s.llamadas[0]["url"].endswith("/oauth/token")
    assert s.llamadas[0]["data"]["grant_type"] == "refresh_token"
    assert s.llamadas[0]["data"]["refresh_token"] == "TG-refresh-viejo"
    assert s.llamadas[1]["headers"]["Authorization"] == "Bearer APP_USR-nuevo-token-de-prueba"
    nuevas = c.credenciales_actualizadas
    assert nuevas is not None and nuevas == c.credenciales
    assert nuevas["access_token"] == "APP_USR-nuevo-token-de-prueba"
    assert nuevas["refresh_token"] == "TG-nuevo-refresh-de-prueba"
    assert nuevas["user_id"] == "123456" and nuevas["site_id"] == "MCO"
    vence = datetime.fromisoformat(nuevas["expira_en"])
    assert timedelta(hours=5, minutes=50) < vence - datetime.now(timezone.utc) < timedelta(hours=6, minutes=1)


def test_meli_no_refresca_si_el_token_sigue_vigente(sesion, env_meli):
    s = sesion(manejador_meli)
    c = meli.Meli(cred_meli(minutos_para_vencer=60))
    c.probar()
    assert not any(l["url"].endswith("/oauth/token") for l in s.llamadas)
    assert s.llamadas[0]["headers"]["Authorization"] == f"Bearer {TOKEN_MELI}"
    assert c.credenciales_actualizadas is None


def test_meli_sin_expira_en_refresca(sesion, env_meli):
    s = sesion(manejador_meli)
    cred = cred_meli()
    del cred["expira_en"]
    meli.Meli(cred).probar()
    assert s.llamadas[0]["url"].endswith("/oauth/token")


def test_meli_sin_env_es_error_que_nombra_las_variables(sesion, monkeypatch):
    monkeypatch.delenv("MELI_APP_ID", raising=False)
    monkeypatch.delenv("MELI_SECRET", raising=False)
    s = sesion(manejador_meli)
    with pytest.raises(ErrorConector) as ei:
        meli.Meli(cred_meli(minutos_para_vencer=1)).listar_productos()
    assert "MELI_APP_ID" in ei.value.usuario and "MELI_SECRET" in ei.value.usuario
    assert s.llamadas == []
    with pytest.raises(ErrorConector) as ei:
        meli.url_autorizacion("abc", "https://app.creatvmachine.com/meli/callback")
    assert "MELI_APP_ID" in ei.value.usuario


def test_meli_401_error_sin_token(sesion, env_meli):
    sesion(lambda m, u, kw: Respuesta(401, {"message": "invalid_token", "error": "not_found", "status": 401}))
    with pytest.raises(ErrorConector) as ei:
        meli.Meli(cred_meli()).listar_productos()
    assert "MercadoLibre" in ei.value.usuario and TOKEN_MELI not in ei.value.usuario
    assert "invalid_token" not in ei.value.usuario


def test_meli_refresh_rechazado(sesion, env_meli):
    sesion(lambda m, u, kw: Respuesta(400, {"message": "Error validating grant", "error": "invalid_grant"}))
    c = meli.Meli(cred_meli(minutos_para_vencer=0))
    with pytest.raises(ErrorConector) as ei:
        c.probar()
    assert "Vuelve a conectar" in ei.value.usuario and "TG-refresh-viejo" not in ei.value.usuario
    assert c.credenciales_actualizadas is None


def test_meli_url_autorizacion(env_meli, monkeypatch):
    url = meli.url_autorizacion("estado-xyz", "https://app.creatvmachine.com/meli/callback")
    partes = urlparse(url)
    assert partes.scheme == "https" and partes.netloc == "auth.mercadolibre.com.co"
    assert partes.path == "/authorization"
    q = parse_qs(partes.query)
    assert q == {"response_type": ["code"], "client_id": ["app-id-prueba"], "state": ["estado-xyz"],
                 "redirect_uri": ["https://app.creatvmachine.com/meli/callback"]}
    monkeypatch.setenv("MELI_AUTH_HOST", "auth.mercadolibre.com.ar")
    assert urlparse(meli.url_autorizacion("s", "https://x/cb")).netloc == "auth.mercadolibre.com.ar"


def test_meli_cambiar_code(sesion, env_meli):
    s = sesion(manejador_meli)
    cred = meli.cambiar_code("TG-code-123", "https://app.creatvmachine.com/meli/callback")
    assert s.llamadas[0]["metodo"] == "POST" and s.llamadas[0]["url"].endswith("/oauth/token")
    assert s.llamadas[0]["data"] == {"grant_type": "authorization_code", "client_id": "app-id-prueba",
                                     "client_secret": "secreto-prueba", "code": "TG-code-123",
                                     "redirect_uri": "https://app.creatvmachine.com/meli/callback"}
    assert s.llamadas[1]["url"].endswith("/users/me")
    assert s.llamadas[1]["headers"]["Authorization"] == "Bearer APP_USR-nuevo-token-de-prueba"
    assert cred["access_token"] == "APP_USR-nuevo-token-de-prueba"
    assert cred["refresh_token"] == "TG-nuevo-refresh-de-prueba"
    assert cred["user_id"] == "123456" and cred["site_id"] == "MCO" and cred["nickname"] == "VIDRIOSDEMO"
    assert datetime.fromisoformat(cred["expira_en"]) > datetime.now(timezone.utc) + timedelta(hours=5)
    # con esas credenciales el conector arranca sin refrescar
    c = meli.Meli(cred)
    c.probar()
    assert c.credenciales_actualizadas is None
    with pytest.raises(ErrorConector):
        meli.cambiar_code("", "https://x/cb")
