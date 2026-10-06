"""Conector `shopify_publico` (spec 2026-09-28 §6): catálogo público de una
tienda Shopify sin llaves. HTTP simulado como en test_conectores_tiendas."""
import json
import os

import pytest
import requests

import conectores
from conectores import ErrorConector, base
from conectores import _http

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nombre):
    with open(os.path.join(FIXTURES, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_conector_base_tiene_fuente_none_y_tipos_conectables():
    assert base.Conector.fuente is None
    assert conectores.TIPOS_CONECTABLES == ("shopify_publico",) + conectores.TIPOS_API
    assert "shopify_publico" not in conectores.TIPOS_API


def test_normalizar_variante():
    v = base.normalizar_variante({"id": "Sand Mini", "nombre": " Sand Mini ", "fuente_id": 123,
                                  "url_compra": "https://t/p?variant=123",
                                  "fotos": ["https://c/a.png", "https://c/a.png", "ftp://no", "https://c/b.png"],
                                  "disponible": 0})
    assert v == {"id": "sand-mini", "nombre": "Sand Mini", "fuente_id": "123", "url_compra": "https://t/p?variant=123",
                 "fotos": ["https://c/a.png", "https://c/b.png"], "disponible": False}
    assert base.normalizar_variante({"nombre": "Rojo"})["id"] == "rojo"
    assert base.normalizar_variante({"nombre": "Rojo"})["disponible"] is True
    with pytest.raises(ErrorConector):
        base.normalizar_variante({"nombre": "  "})


from tests.test_conectores_tiendas import Respuesta, SesionFalsa   # sesión falsa compartida


@pytest.fixture
def sesion(monkeypatch):
    def instalar(manejador):
        s = SesionFalsa(manejador)
        monkeypatch.setattr(requests, "Session", lambda: s)
        return s
    monkeypatch.setattr(_http.time, "sleep", lambda *_: None)
    return instalar


@pytest.fixture(autouse=True)
def hosts_publicos(monkeypatch):
    from conectores import shopify_publico
    monkeypatch.setattr(shopify_publico, "host_permitido", lambda url: "interna" not in url)


_SIN_META = object()   # distingue "no se pasó meta" (usar el fixture) de meta=None ("sin meta.json": 404)


def _manejador(productos=None, meta=_SIN_META, html=False):
    productos = fixture("shopify_publico_products.json") if productos is None else productos
    meta = fixture("shopify_publico_meta.json") if meta is _SIN_META else meta

    def manejador(metodo, url, kw):
        assert metodo == "GET" and kw["headers"]["Accept"] == "application/json"
        if html:
            return Respuesta(200, None, texto="<html>password</html>")
        if url.endswith("/meta.json"):
            return Respuesta(200, meta) if meta is not None else Respuesta(404, None, texto="no")
        if url.endswith("/products.json"):
            pagina = int(kw["params"].get("page") or 1)
            return Respuesta(200, productos if pagina == 1 else {"products": []})
        return Respuesta(404, None, texto="no")
    return manejador


def _conector(dominio="www.happyflops.com"):
    from conectores import shopify_publico
    return shopify_publico.ShopifyPublico({"dominio": dominio})


def test_registro_y_atributos():
    from conectores import shopify_publico
    assert conectores.por_tipo("shopify_publico") is shopify_publico.ShopifyPublico
    assert shopify_publico.ShopifyPublico.fuente == "shopify" and not shopify_publico.ShopifyPublico.tiene_pedidos


@pytest.mark.parametrize("texto, esperado", [
    ("www.happyflops.com", "www.happyflops.com"), ("https://www.happyflops.com/es?x=1", "www.happyflops.com"),
    (" HappyFlops.com/ ", "happyflops.com"), ("njd4pz-ab.myshopify.com.", "njd4pz-ab.myshopify.com"),
])
def test_normalizar_dominio(texto, esperado):
    from conectores.shopify_publico import normalizar_dominio
    assert normalizar_dominio(texto) == esperado


@pytest.mark.parametrize("malo", ["", "   ", "sin espacios no", "localhost", "a b.com", "http://", "-x.com"])
def test_normalizar_dominio_rechaza(malo):
    from conectores.shopify_publico import normalizar_dominio
    with pytest.raises(ErrorConector):
        normalizar_dominio(malo)


def test_es_servicio_y_opcion_color():
    from conectores.shopify_publico import es_servicio, opcion_color
    prods = fixture("shopify_publico_products.json")["products"]
    por = {p["handle"]: p for p in prods}
    assert es_servicio(por["shipping-protection"]) and not es_servicio(por["happyflops-polkadots"])
    assert es_servicio({"title": "Tarjeta de regalo", "product_type": ""})
    assert es_servicio({"title": "Seguro de envío", "product_type": ""}) and es_servicio({"title": "x", "product_type": "Route Protection"})
    assert opcion_color(por["happyflops-polkadots"]) == (1, "Colour")
    assert opcion_color(por["happyblanket"]) is None
    # nombre raro (no está en OPCIONES_COLOR) pero variantes con fotos distintas por valor: se toma como color
    p = {"options": [{"name": "Tono", "position": 1, "values": ["A", "B"]}],
         "variants": [{"option1": "A", "featured_image": {"id": 1}}, {"option1": "B", "featured_image": {"id": 2}}]}
    assert opcion_color(p) == (1, "Tono")
    p["variants"][1]["featured_image"] = {"id": 1}
    assert opcion_color(p) is None
    assert opcion_color({"options": [{"name": "Estampado", "position": 2, "values": ["x"]}], "variants": []}) == (2, "Estampado")


def test_foto_url_y_precio_moda():
    from conectores.shopify_publico import foto_url, precio_moda
    assert foto_url("https://cdn.shopify.com/s/files/1/x/a.png?v=17") == "https://cdn.shopify.com/s/files/1/x/a.png?v=17&width=1000"
    assert foto_url("https://cdn.shopify.com/s/files/1/x/a.png") == "https://cdn.shopify.com/s/files/1/x/a.png?width=1000"
    assert foto_url("https://otro.cdn/a.png?v=1") == "https://otro.cdn/a.png?v=1"
    assert foto_url("https://cdn.shopify.com/a.png?width=500") == "https://cdn.shopify.com/a.png?width=500"
    vs = [{"price": "34.95", "available": True}] * 3 + [{"price": "19.95", "available": True}] * 2
    assert precio_moda(vs) == 34.95
    assert precio_moda([{"price": "20", "available": True}, {"price": "10", "available": True}]) == 10.0   # empate: el menor
    assert precio_moda([{"price": "20", "available": False}, {"price": "10", "available": False}]) == 10.0
    assert precio_moda([]) is None


def test_listar_productos_con_colores_generales_precio_y_moneda(sesion):
    s = sesion(_manejador())
    con = _conector()
    productos = con.listar_productos()
    assert con.omitidos == ["Shipping protection"]
    assert [p["nombre"] for p in productos] == ["HappyFlops Polkadots", "HappySandals Helsinki", "HappyBlanket"]
    polka = productos[0]
    assert polka["fuente_id"].isdigit() and polka["moneda"] == "EUR" and polka["precio"] == 39.95
    assert polka["url_compra"] == "https://www.happyflops.com/products/happyflops-polkadots"
    assert polka["descripcion"] == ""   # body_html de Polkadots es "<p></p>" en el fixture
    v = polka["extra"]["variantes"]
    assert [x["nombre"] for x in v] == ["Sand Mini", "Black Pop", "Midnight Mini", "Berry Pop", "Snow Pop", "Snow Mini"]
    assert all(len(x["fotos"]) == 1 and "width=1000" in x["fotos"][0] for x in v)
    assert all(x["url_compra"].startswith(polka["url_compra"] + "?variant=") and x["fuente_id"].isdigit() for x in v)
    assert all(x["disponible"] for x in v)
    assert len(polka["fotos"]) == 4 and all("width=1000" in f for f in polka["fotos"])   # generales: las no ligadas
    assert polka["url_imagen_principal"] and polka["extra"]["handle"] == "happyflops-polkadots"
    assert polka["extra"]["tallas"] and polka["extra"]["publico"] is True and "precios" not in polka["extra"]
    blanket = productos[2]
    assert blanket["extra"]["variantes"] == [] and len(blanket["fotos"]) == 3 and blanket["precio"] == 49.95
    assert blanket["extra"]["precios"] == {"min": 49.95, "max": 69.95} and blanket["categoria"] == "Textil"
    urls = [c["url"] for c in s.llamadas]
    assert urls[0].endswith("/meta.json") and urls[1].endswith("/products.json") and len(urls) == 2   # 5 < 250: una página


def test_listar_productos_pagina_hasta_que_una_trae_menos_del_limite(sesion):
    from conectores import shopify_publico
    base_p = fixture("shopify_publico_products.json")["products"][0]
    llenas = {"products": [dict(base_p, id=1000 + i, handle=f"p{i}", title=f"P{i}") for i in range(shopify_publico.LIMITE_PAGINA)]}

    def manejador(metodo, url, kw):
        if url.endswith("/meta.json"):
            return Respuesta(200, fixture("shopify_publico_meta.json"))
        pagina = int(kw["params"]["page"])
        return Respuesta(200, llenas if pagina == 1 else {"products": [base_p]})
    s = sesion(manejador)
    productos = _conector().listar_productos()
    assert len(productos) == shopify_publico.LIMITE_PAGINA + 1
    assert [c["params"].get("page") for c in s.llamadas[1:]] == [1, 2]


def test_probar_ok_html_y_404(sesion):
    sesion(_manejador())
    r = _conector().probar()
    assert r["ok"] and r["nombre"] == "HappyFlops WW" and "EUR" in r["detalle"] and r["dominio"] == "www.happyflops.com"
    sesion(_manejador(html=True))
    with pytest.raises(ErrorConector) as e:
        _conector().probar()
    assert "catálogo público de Shopify" in str(e.value)
    sesion(_manejador(meta=None))          # sin meta.json pero con products.json: ok, sin moneda
    r = _conector().probar()
    assert r["ok"] and r["nombre"] == "" and r["dominio"] == "www.happyflops.com"


def test_probar_sigue_redireccion_al_dominio_real_y_lo_devuelve(sesion):
    def manejador(metodo, url, kw):
        assert kw.get("allow_redirects") is False
        if "njd4pz-ab.myshopify.com" in url:
            return Respuesta(301, None, headers={"Location": url.replace("njd4pz-ab.myshopify.com", "www.happyflops.com")})
        if url.endswith("/meta.json"):
            return Respuesta(200, fixture("shopify_publico_meta.json"))
        return Respuesta(200, fixture("shopify_publico_products.json"))
    sesion(manejador)
    r = _conector("njd4pz-ab.myshopify.com").probar()
    assert r["ok"] and r["dominio"] == "www.happyflops.com"


def test_redireccion_a_host_interno_se_rechaza(sesion):
    sesion(lambda m, url, kw: Respuesta(302, None, headers={"Location": "https://interna.local/meta.json"}))
    with pytest.raises(ErrorConector):
        _conector().probar()


def test_listar_sin_json_valido_es_error_claro(sesion):
    sesion(lambda m, url, kw: Respuesta(200, {"products": "no-es-lista"}) if url.endswith("/products.json") else Respuesta(404, None, texto="x"))
    with pytest.raises(ErrorConector) as e:
        _conector().listar_productos()
    assert "catálogo público de Shopify" in str(e.value)


def test_un_429_que_sobrevive_al_reintento_dice_que_la_tienda_limito_las_peticiones(sesion):
    """Revisión final: un 429 no es «no es una tienda Shopify»: es la tienda
    frenando las peticiones (`_http.error_generico`)."""
    s = sesion(lambda m, url, kw: Respuesta(429, None, texto="Too Many Requests", headers={"Retry-After": "1"}))
    with pytest.raises(ErrorConector) as e:
        _conector().listar_productos()
    assert "limitó las peticiones (HTTP 429)" in str(e.value) and "catálogo público" not in str(e.value)
    assert len(s.llamadas) == 4          # meta.json y products.json, cada una con su único reintento
    with pytest.raises(ErrorConector) as e:
        _conector().probar()
    assert "limitó las peticiones (HTTP 429)" in str(e.value)


def test_dominio_interno_no_se_consulta(sesion):
    s = sesion(_manejador())
    with pytest.raises(ErrorConector):
        _conector("interna.example").probar()
    assert s.llamadas == []


@pytest.mark.parametrize('longitud', [None, '1', '1000'])
def test_pnd056_corta_stream_al_superar_tope_y_cierra(monkeypatch, longitud):
    from conectores import shopify_publico as sp
    monkeypatch.setattr(sp,'MAX_RESPUESTA_BYTES',16,raising=False)
    class Streaming:
        status_code = 200
        headers = {} if longitud is None else {'Content-Length':longitud}
        leidos = 0
        cerrado = False
        def iter_content(self, chunk_size):
            for trozo in [b'x'*8,b'x'*8,b'x',b'no debe leerse']:
                self.leidos += 1
                yield trozo
        def json(self):
            return {'products':[]}
        def close(self):
            self.cerrado = True
    resp = Streaming()
    llamadas = []
    def pedir(*a,**kw):
        llamadas.append(kw)
        return resp
    monkeypatch.setattr(sp,'pedir',pedir)
    with pytest.raises(ErrorConector, match='pesa más'):
        _conector()._get('/products.json')
    assert llamadas[0]['stream'] is True
    assert resp.leidos == (0 if longitud == '1000' else 3)
    assert resp.cerrado


def test_pnd056_acepta_json_justo_en_el_tope_y_cierra(monkeypatch):
    from conectores import shopify_publico as sp
    cuerpo = b'{"products": []}'
    monkeypatch.setattr(sp,'MAX_RESPUESTA_BYTES',len(cuerpo),raising=False)
    class Streaming:
        status_code = 200
        headers = {}
        cerrado = False
        def iter_content(self, chunk_size):
            yield cuerpo[:4]
            yield b''
            yield cuerpo[4:]
        def close(self):
            self.cerrado = True
    resp = Streaming()
    monkeypatch.setattr(sp,'pedir',lambda *a,**kw:resp)
    assert _conector()._get('/products.json')[0] == {'products':[]}
    assert resp.cerrado


def test_pnd056_pagina_real_grande_se_importa_en_lotes_menores(sesion):
    import copy
    productos = []
    semilla = fixture("shopify_publico_products.json")["products"][0]
    for i in range(250):
        p = copy.deepcopy(semilla)
        p["id"] = 1000 + i
        p["variants"] = [dict(semilla["variants"][0], id=i * 36 + j, sku="x" * 900) for j in range(36)]
        productos.append(p)
    assert len(json.dumps({"products": productos}).encode()) > 8 * 1024 * 1024
    def pagina(m, url, kw):
        if url.endswith("/meta.json"):
            return Respuesta(200, {"currency": "USD"})
        limit, page = kw["params"]["limit"], kw["params"]["page"]
        desde = (page - 1) * limit
        return Respuesta(200, {"products": productos[desde:desde + limit]})
    sesion(pagina)
    r = _conector().listar_productos()
    assert len(r) == 250
    assert {p["fuente_id"] for p in r} == {str(1000 + i) for i in range(250)}


def test_pnd056_lotes_menores_conservan_alcance_y_posicion(sesion, monkeypatch):
    from conectores import shopify_publico as sp
    # La segunda página de 250 pesa de más: debe seguir en el producto 250.
    pedidos = []
    def pagina(m, url, kw):
        if url.endswith("/meta.json"):
            return Respuesta(200, {"currency": "USD"})
        limit, page = kw["params"]["limit"], kw["params"]["page"]
        desde = (page - 1) * limit
        pedidos.append((desde, limit))
        if desde == 250 and limit == 250:
            return Respuesta(200, {"products": [], "relleno": "x" * sp.MAX_RESPUESTA_BYTES})
        return Respuesta(200, {"products": [dict(id=i, published_at="2026-01-01", title="Producto")
                                          for i in range(desde, min(desde + limit, 10000))]})
    sesion(pagina)
    monkeypatch.setattr(sp.ShopifyPublico, "_producto", lambda self, p, moneda: p["id"])
    assert _conector().listar_productos() == list(range(10000))
    assert pedidos[:3] == [(0, 250), (250, 250), (250, 125)]


@pytest.mark.parametrize("codigo", [500, 429])
def test_pnd056_reintento_http_cierra_respuesta(monkeypatch, codigo):
    primera = Respuesta(codigo, {}, headers={"Retry-After": "0"})
    ultima = Respuesta(200, {})
    primera.cerrada = False
    primera.close = lambda: setattr(primera, "cerrada", True)
    respuestas = iter([primera, ultima])
    llamadas = []
    def responder(*a):
        if llamadas:
            assert primera.cerrada, "la respuesta debe cerrarse antes del siguiente request"
        llamadas.append(1)
        return next(respuestas)
    s = SesionFalsa(responder)
    monkeypatch.setattr(_http.time, "sleep", lambda *a: None)
    assert _http.pedir(s, "GET", "https://tienda.example/products.json", stream=True) is ultima
    assert primera.cerrada
