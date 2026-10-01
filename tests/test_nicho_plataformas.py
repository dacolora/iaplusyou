"""Registro de plataformas (spec Parte 3 §3): países, precios, entradas y lectores puros, sin red."""
import json
import os

import pytest

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_claves_paises_idioma_y_dominio():
    from nicho import datos
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    assert pl.claves() == ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress") and set(pl.claves()) == set(datos.FUENTES_PLATAFORMA)
    assert pl.nombre("meli") == "Mercado Libre" and pl.nombre("aliexpress") == "AliExpress"
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop", "aliexpress"] and pl.disponibles("MX") == ["amazon", "meli", "tiktok_shop", "aliexpress"]
    assert pl.disponibles("CO") == ["meli", "tiktok_shop", "aliexpress"]               # Amazon solo donde tiene tienda propia
    assert pl.disponibles("ZZ") == ["tiktok_shop", "aliexpress"] and pl.disponibles("US") == ["amazon", "tiktok_shop", "walmart", "aliexpress"]
    assert pl.dominio("walmart", "US") == "https://www.walmart.com/" and pl.dominio("walmart", "CO") is None and pl.dominio("aliexpress", "CO") is None
    assert pl.dominio("amazon", "SE") == "se" and pl.dominio("amazon", "MX") == "com.mx" and pl.dominio("amazon", "US") == "com"
    assert pl.dominio("meli", "CO") == "https://listado.mercadolibre.com.co/" and pl.dominio("meli", "BR") == "https://lista.mercadolivre.com.br/"
    assert pl.dominio("tiktok_shop", "SE") is None and pl.dominio("meli", "SE") is None
    assert pl.idioma("SE") == "sv" and pl.idioma("CO") == "es" and pl.idioma("BR") == "pt" and pl.idioma("ZZ") == "en" and pl.idioma(None) == "en"
    assert pl.IDIOMAS is pl.IDIOMA_POR_PAIS
    for clave in pl.claves():
        assert pl.actor_busqueda(clave)["actor"] and pl.actor_resenas(clave)["actor"] and pl.actor_resenas(clave)["usd_por_resultado"] > 0
    with pytest.raises(ErrorFuente):
        pl.nombre("magia")


def test_estimados_redondean_al_centavo_hacia_arriba():
    from nicho.fuentes import plataformas as pl
    assert pl.usd(30, 0.003) == 0.09 and pl.usd(1, 0.0009) == 0.01 and pl.usd(0, 0.5) == 0.0
    assert pl.estimar_busqueda("amazon", 3, 20) == 0.3            # 60 × 0.005 (plan FREE de Apify, verificado 2026-10-01)
    assert pl.estimar_resenas("amazon", 15, 100) == 1.35         # 1500 × 0.0009
    assert pl.estimar_busqueda("meli", 3, 20) == 0.12 and pl.estimar_resenas("meli", 15, 100) == 2.25   # 1500 × 0.0015
    assert pl.estimar_busqueda("tiktok_shop", 3, 20) == 0.27 and pl.estimar_resenas("tiktok_shop", 15, 100) == 6.75
    # con arranque por corrida: Walmart busca UNA consulta por corrida (20 × 0.001 + 0.001 → 0.03 cada una)
    assert pl.estimar_busqueda("walmart", 3, 20) == 0.09 and pl.estimar_resenas("walmart", 15, 100) == 1.5
    assert pl.estimar_busqueda("aliexpress", 3, 20) == 0.03 and pl.estimar_resenas("aliexpress", 15, 100) == 4.51
    actor = pl.actor_resenas("aliexpress")
    assert actor["usd_por_corrida"] == 0.01 and pl.tope(5, actor) == 0.03 and pl.costo(5, 1, actor) == 0.03
    assert pl.costo(0, 1, actor) == 0.01 and pl.costo(0, 0, actor) == 0.0 and pl.costo(1500, 1, actor) == 4.51   # el arranque cobra aunque no traiga nada
    assert pl.tope(20, {"usd_por_resultado": 0.003}) == 0.06                                                    # sin la clave = sin arranque


def test_entradas_de_busqueda():
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    consultas = ["tofflor mot fotsmärta", "ortopediska tofflor"]
    e = pl.entradas_busqueda("amazon", consultas, "SE", 20)
    assert len(e) == 1 and e[0]["max_items"] == 40 and e[0]["max_usd"] == 0.2 and e[0]["etiqueta"] == "búsqueda"
    assert e[0]["entrada"] == {"categoryOrProductUrls": [{"url": "https://www.amazon.se/s?k=tofflor+mot+fotsm%C3%A4rta"},
                                                         {"url": "https://www.amazon.se/s?k=ortopediska+tofflor"}],
                               "maxItemsPerStartUrl": 20, "maxSearchPagesPerStartUrl": 2, "proxyCountry": "SE"}
    e = pl.entradas_busqueda("meli", ["pantuflas ortopédicas", "pantuflas memory foam"], "CO", 10)
    assert [x["entrada"] for x in e] == [{"keyword": "pantuflas ortopédicas", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False},
                                         {"keyword": "pantuflas memory foam", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False}]
    assert [x["max_items"] for x in e] == [10, 10] and [x["etiqueta"] for x in e] == ["pantuflas ortopédicas", "pantuflas memory foam"]
    e = pl.entradas_busqueda("tiktok_shop", ["cloud slippers"], "US", 20)
    assert e == [{"entrada": {"mode": "shop_search", "searchKeywords": ["cloud slippers"], "maxResults": 20}, "max_items": 20, "max_usd": 0.09, "etiqueta": "búsqueda"}]
    otro = pl.entradas_busqueda("meli", ["x"], "SE", 10)              # Mercado Libre no está en Suecia: busca en su casa (México)
    assert otro[0]["entrada"]["country"] == "https://listado.mercadolibre.com.mx/"
    with pytest.raises(ErrorFuente):
        pl.entradas_busqueda("amazon", [], "SE", 10)                  # sin consultas no hay búsqueda


def test_leer_producto_por_plataforma():
    from nicho.fuentes import plataformas as pl
    a = [pl.leer_producto("amazon", i) for i in _fixture("amazon_busqueda.json")]
    assert a[2] is None
    assert a[0] == {"fuente_id": "B0AMZ00001", "titulo": "Ortopediska tofflor med fotbädd", "marca": "Fotvän", "precio": 349.0, "moneda": "SEK",
                    "estrellas": 4.4, "n_resenas": 1287, "url": "https://www.amazon.se/dp/B0AMZ00001",
                    "imagen": "https://m.media-amazon.com/images/I/1.jpg", "extra": {"vendedor": "Fotvän AB", "en_stock": True}}
    assert a[1]["precio"] == 199.5 and a[1]["moneda"] == "SEK" and a[1]["estrellas"] == 4.1 and a[1]["n_resenas"] == 58 and a[1]["marca"] is None
    m = [pl.leer_producto("meli", i) for i in _fixture("meli_busqueda.json")]
    assert m[2] is None
    assert m[0]["fuente_id"] == "MCO123456789" and m[0]["precio"] == 89900.0 and m[0]["moneda"] == "COP" and m[0]["n_resenas"] == 152
    assert m[0]["url"] == "https://articulo.mercadolibre.com.co/MCO-123456789-pantuflas" and m[0]["imagen"] == "https://http2.mlstatic.com/D_1.jpg"
    assert m[0]["extra"] == {"vendedor": "Tienda Pie Sano", "vendidos": 500}
    assert m[1]["fuente_id"] == "MCO987654321" and m[1]["precio"] == 59900.0 and m[1]["url"].endswith("-memory") and m[1]["n_resenas"] is None
    t = [pl.leer_producto("tiktok_shop", i) for i in _fixture("tiktok_shop_busqueda.json")]
    assert t[2] is None
    assert t[0]["fuente_id"] == "1729000000000000001" and t[0]["precio"] == 12.99 and t[0]["moneda"] == "USD" and t[0]["n_resenas"] == 320
    assert t[0]["extra"] == {"vendidos": 5400} and t[0]["url"] == "https://www.tiktok.com/shop/pdp/1729000000000000001"
    assert t[1]["precio"] == 19.5 and t[1]["estrellas"] == 4.5 and t[1]["extra"] == {"vendidos": 120}


def test_entradas_y_lectura_de_resenas():
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    productos = [{"fuente_id": "B0AMZ00001", "url": "https://www.amazon.se/dp/B0AMZ00001", "titulo": "Tofflor"},
                 {"fuente_id": "B0AMZ00002", "url": "https://www.amazon.se/dp/B0AMZ00002", "titulo": "Mjuka"}]
    e = pl.entradas_resenas("amazon", productos, "SE", 100)
    assert [x["entrada"] for x in e] == [{"asin": "B0AMZ00001", "domainCode": "se", "maxPages": 10, "sortBy": "recent"},
                                         {"asin": "B0AMZ00002", "domainCode": "se", "maxPages": 10, "sortBy": "recent"}]
    assert [x["max_items"] for x in e] == [100, 100] and e[0]["max_usd"] == 0.09 and e[0]["etiqueta"] == "B0AMZ00001"
    assert pl.entradas_resenas("amazon", productos[:1], "SE", 25)[0]["entrada"]["maxPages"] == 3
    r = [pl.leer_resena("amazon", i) for i in _fixture("amazon_resenas.json")]
    assert r[2] is None
    assert r[0] == {"fuente_id": "R1AMZ", "texto": "Äntligen smärtfri. Skönt stöd under hälen, går att ha hela dagen.", "puntuacion": 5,
                    "fecha": "2025-03-01", "url": None, "producto": "B0AMZ00001"}
    assert r[1]["texto"] == "För smala för mig, skickade tillbaka." and r[1]["fecha"] == "March 5, 2025"
    e = pl.entradas_resenas("meli", [{"fuente_id": "MCO123456789", "url": "https://articulo.mercadolibre.com.co/MCO-123456789-p", "titulo": "P"}], "CO", 50)
    assert e == [{"entrada": {"productUrls": ["https://articulo.mercadolibre.com.co/MCO-123456789-p"], "maxReviewsPerProduct": 50, "reviewOrder": "relevance"},
                  "max_items": 50, "max_usd": 0.08, "etiqueta": "reseñas"}]        # 50 × 0.0015 (plan FREE, verificado 2026-10-01)
    r = [pl.leer_resena("meli", i) for i in _fixture("meli_resenas.json")]
    assert r[2] is None and r[0]["fuente_id"] == "rv1" and r[0]["puntuacion"] == 5 and r[0]["producto"] == "MCO123456789"   # sin guion
    assert r[1]["producto"] == "MCO123456789" and r[1]["fecha"] == "2025-01-22"
    e = pl.entradas_resenas("tiktok_shop", [{"fuente_id": "1", "url": "https://www.tiktok.com/shop/pdp/1", "titulo": "P"}], "US", 30)
    assert e[0]["entrada"] == {"mode": "product_reviews", "productUrls": ["https://www.tiktok.com/shop/pdp/1"], "maxReviewsPerProduct": 30} and e[0]["max_items"] == 30
    r = [pl.leer_resena("tiktok_shop", i) for i in _fixture("tiktok_shop_resenas.json")]
    assert r[2] is None and r[0]["puntuacion"] == 5 and r[1]["puntuacion"] == 3 and r[0]["producto"] == "1729000000000000001"
    assert r[0]["fecha"] == "2025-01-01T10:00:00Z"
    with pytest.raises(ErrorFuente):
        pl.entradas_resenas("amazon", [], "SE", 10)
    with pytest.raises(ErrorFuente):
        pl.entradas_resenas("meli", [{"fuente_id": "x", "url": None, "titulo": "sin url"}], "CO", 10)


def test_links_de_productos_solo_http():
    """El link del producto va a un href: nada que no sea http(s) (ola final, F1)."""
    from nicho.fuentes import plataformas as pl
    base = {"asin": "B0X", "title": "Tofflor"}
    for malo in ("javascript:alert(1)", " JAVASCRIPT:alert(1)", "data:text/html,<b>x</b>", "/dp/B0X", "vbscript:x"):
        p = pl.leer_producto("amazon", {**base, "url": malo, "thumbnailImage": malo})
        assert p["url"] is None and p["imagen"] is None, malo
    p = pl.leer_producto("amazon", {**base, "url": "https://www.amazon.se/dp/B0X", "thumbnailImage": "HTTP://img.example/x.jpg"})
    assert p["url"] == "https://www.amazon.se/dp/B0X" and p["imagen"] == "HTTP://img.example/x.jpg"
    assert pl.leer_producto("meli", {"id": "MCO1", "title": "P", "permalink": "//articulo.mercadolibre.com.co/MCO-1"})["url"] == \
        "https://articulo.mercadolibre.com.co/MCO-1"
    assert pl.leer_producto("tiktok_shop", {"productId": "1", "title": "P", "productUrl": "javascript:x"})["url"] is None


def test_resenas_por_link_saltan_productos_sin_link():
    from nicho.fuentes import plataformas as pl
    e = pl.entradas_resenas("meli", [{"fuente_id": "a", "url": None, "titulo": "sin"},
                                     {"fuente_id": "b", "url": "https://articulo.mercadolibre.com.co/MCO-2", "titulo": "con"}], "CO", 20)
    assert e[0]["entrada"]["productUrls"] == ["https://articulo.mercadolibre.com.co/MCO-2"] and e[0]["max_items"] == 20


def test_lectores_con_la_forma_real_de_los_actores():
    """Ítems tal cual los devolvieron los actores en la prueba de centavos del
    2026-09-30 (México): Mercado Libre trae productUrl/currentPrice/thumbnailUrl y
    Amazon el precio con un «$» a secas que en México son pesos."""
    from nicho.fuentes import plataformas as pl
    meli = {"publicationId": "MLM2434546658", "sku": "MLM2434546658", "title": "Botella De Agua Motivacional Deportiva Azul Con Rosa 1 Lt",
            "brand": "", "currency": "MXN", "currentPrice": 185, "productUrl": "https://www.mercadolibre.com.mx/botella/up/MLMU491158340",
            "thumbnailUrl": "https://http2.mlstatic.com/D_NQ_NP_886325-O.webp", "rating": "", "reviewCount": "", "soldQuantity": None,
            "sellerName": "", "searchKeyword": "botella de agua con marcador de tiempo"}
    p = pl.leer_producto("meli", meli, "MX")
    assert p["fuente_id"] == "MLM2434546658" and p["precio"] == 185.0 and p["moneda"] == "MXN"
    assert p["url"] == "https://www.mercadolibre.com.mx/botella/up/MLMU491158340" and p["imagen"].startswith("https://http2.mlstatic.com/")
    assert p["estrellas"] is None and p["n_resenas"] is None and p["marca"] is None
    amazon = {"asin": "B0CQRG7MDY", "title": "Botella de agua Deportiva 1 litro motivacional", "brand": "COREROSE",
              "price": {"value": 149.99, "currency": "$"}, "stars": 4.2, "reviewsCount": 106, "loadedCountryCode": "MX",
              "url": "https://www.amazon.com.mx/dp/B0CQRG7MDY", "thumbnailImage": "https://m.media-amazon.com/images/I/41.jpg",
              "seller": {"name": "lanxiwl", "id": "A3TWSLEF4CDSQQ"}, "inStock": True}
    a = pl.leer_producto("amazon", amazon)
    assert a["precio"] == 149.99 and a["moneda"] == "MXN" and a["extra"] == {"vendedor": "lanxiwl", "en_stock": True}
    sin_pais = {k: v for k, v in amazon.items() if k != "loadedCountryCode"}
    assert pl.leer_producto("amazon", sin_pais, "CO")["moneda"] == "COP"          # el país de la búsqueda resuelve el «$»
    assert pl.leer_producto("amazon", sin_pais)["moneda"] == "USD"                  # sin país, «$» sigue siendo dólar
    assert pl.leer_producto("amazon", {**sin_pais, "price": {"value": 20, "currency": "US$"}}, "MX")["moneda"] == "USD"


@pytest.mark.parametrize("texto,esperado", [("1.234,56", 1234.56), ("1,234.56", 1234.56), ("12,99", 12.99), ("4,5", 4.5),
                                            ("1.234", 1234.0), ("59.900", 59900.0), ("1.234.567,89", 1234567.89), ("1,234", 1234.0),
                                            ("12.5", 12.5), ("€ 1.299,00", 1299.0), ("US$ 19.99", 19.99), ("349 kr", 349.0), ("abc", None)])
def test_precios_con_coma_o_punto(texto, esperado):
    from nicho.fuentes import plataformas as pl
    assert pl._flotante(texto) == esperado


def test_mercado_sitio_e_idioma_de_busqueda():
    """Spec Parte 4 §2: una tienda que no está en el país busca en su sitio principal, en el idioma de ese sitio."""
    from nicho.fuentes import plataformas as pl
    assert pl.mercado("amazon", "MX") == ("local", "MX") and pl.mercado("amazon", "co") == ("otro", "US")
    assert pl.mercado("meli", "US") == ("otro", "MX") and pl.mercado("walmart", "CO") == ("otro", "US") and pl.mercado("walmart", "US") == ("local", "US")
    assert pl.mercado("aliexpress", "CO") == ("local", "CO") and pl.mercado("tiktok_shop", "SE") == ("local", "SE")
    assert pl.sitio("amazon", "CO") == "US" and pl.sitio("meli", "SE") == "MX" and pl.sitio("meli", "CO") == "CO"
    assert pl.idioma_busqueda("amazon", "CO") == "en" and pl.idioma_busqueda("meli", "US") == "es" and pl.idioma_busqueda("meli", "BR") == "pt"
    assert pl.idioma_busqueda("aliexpress", "CO") == "en" and pl.idioma_busqueda("walmart", "SE") == "en"
    assert pl.idioma_busqueda("tiktok_shop", "SE") == "sv" and pl.idioma_busqueda("amazon", "SE") == "sv"
    for clave in pl.claves():
        p = pl.PLATAFORMAS[clave]
        assert p["paises"] == pl.TODOS or p["casa"] in p["paises"]          # la casa de una tienda por países es uno de sus sitios
        assert "usd_por_corrida" in p["busqueda"] and {"usd_por_corrida", "necesita_link", "por_producto"} <= set(p["resenas"])


def test_entradas_de_walmart_y_aliexpress():
    from nicho.fuentes import plataformas as pl
    e = pl.entradas_busqueda("walmart", ["water bottle time marker", "motivational water bottle"], "CO", 20)
    assert [x["entrada"] for x in e] == [{"mode": "search", "query": "water bottle time marker", "limit": 20, "fetch_prices": False},
                                         {"mode": "search", "query": "motivational water bottle", "limit": 20, "fetch_prices": False}]
    assert [x["max_items"] for x in e] == [20, 20] and [x["max_usd"] for x in e] == [0.03, 0.03] and e[0]["etiqueta"] == "water bottle time marker"
    e = pl.entradas_busqueda("aliexpress", ["water bottle time marker"], "CO", 20)
    assert e == [{"entrada": {"searchQueries": ["water bottle time marker"], "maxItems": 20, "country": "US", "currency": "USD", "language": "en_US"},
                  "max_items": 20, "max_usd": 0.01, "etiqueta": "water bottle time marker"}]
    productos = [{"fuente_id": "17345973281", "url": None, "titulo": "A"},
                 {"fuente_id": "19948220116", "url": "https://www.walmart.com/ip/x/19948220116", "titulo": "B"}]
    e = pl.entradas_resenas("walmart", productos, "CO", 50)                # sin link también: se arma con el id
    assert e == [{"entrada": {"products": ["https://www.walmart.com/ip/17345973281", "https://www.walmart.com/ip/19948220116"],
                              "maxReviewsPerProduct": 50, "includeProductSummary": False}, "max_items": 100, "max_usd": 0.1, "etiqueta": "reseñas"}]
    e = pl.entradas_resenas("aliexpress", [{"fuente_id": "3256806541493299", "url": None, "titulo": "A"}], "CO", 30)
    assert e == [{"entrada": {"productUrls": ["https://www.aliexpress.com/item/3256806541493299.html"], "maxReviewsPerProduct": 30, "language": "en_US"},
                  "max_items": 30, "max_usd": 0.1, "etiqueta": "reseñas"}]


def test_otro_mercado_busca_y_trae_resenas_en_su_casa():
    from nicho.fuentes import plataformas as pl
    e = pl.entradas_busqueda("amazon", ["botella"], "CO", 10)               # Amazon no está en Colombia: amazon.com
    assert e[0]["entrada"]["categoryOrProductUrls"] == [{"url": "https://www.amazon.com/s?k=botella"}] and e[0]["entrada"]["proxyCountry"] == "US"
    assert pl.entradas_resenas("amazon", [{"fuente_id": "B0X", "url": None, "titulo": "t"}], "CO", 10)[0]["entrada"]["domainCode"] == "com"
    e = pl.entradas_resenas("meli", [{"fuente_id": "MLM1", "url": "https://www.mercadolibre.com.mx/p/MLM1", "titulo": "t"}], "US", 10)
    assert e[0]["entrada"]["productUrls"] == ["https://www.mercadolibre.com.mx/p/MLM1"]


def test_lectores_de_walmart_y_aliexpress_con_datos_reales():
    """Salida real de la verificación con centavos del 2026-09-30 (spec Parte 4 §1.1), sin autores."""
    from nicho.fuentes import plataformas as pl
    w = [pl.leer_producto("walmart", i, "US") for i in _fixture("walmart_busqueda.json")]
    assert w[2] is None
    assert w[0]["fuente_id"] == "17345973281" and w[0]["titulo"].startswith("OFEFE 3-Piece") and w[0]["estrellas"] == 5.0 and w[0]["n_resenas"] == 1
    assert w[0]["precio"] is None and w[0]["moneda"] is None and w[0]["marca"] is None            # el buscador no trae precio (no se pide)
    assert w[0]["url"].startswith("https://www.walmart.com/ip/") and w[0]["imagen"].startswith("https://i5.walmartimages.com/")
    assert w[0]["extra"] == {"vendedor": "Bo Yue Xing", "en_stock": True} and w[1]["n_resenas"] == 17 and w[1]["estrellas"] == 4.6
    r = [pl.leer_resena("walmart", i) for i in _fixture("walmart_resenas.json")]
    assert r[2] is None
    assert r[0]["fuente_id"] == "425493703" and r[0]["texto"].startswith("Still has plastic. I bought this because") and r[0]["puntuacion"] == 3
    assert r[0]["fecha"] == "2026-05-14T00:00:00.000Z" and r[0]["producto"] == "5394318269" and r[0]["url"] is None and "pais" not in r[0]
    assert r[1]["texto"].startswith("I got it as a gift") and r[1]["puntuacion"] == 1
    assert pl.leer_resena("walmart", {**_fixture("walmart_resenas.json")[0], "rowType": "summary"}) is None     # otra fila no es reseña
    a = [pl.leer_producto("aliexpress", i) for i in _fixture("aliexpress_busqueda.json")]
    assert a[2] is None
    assert a[0] == {"fuente_id": "3256806541493299", "titulo": a[0]["titulo"], "marca": None, "precio": 4.03, "moneda": "USD", "estrellas": 4.9,
                    "n_resenas": None, "url": "https://www.aliexpress.com/item/3256806541493299.html",
                    "imagen": "https://ae-pic-a1.aliexpress-media.com/kf/Sdd3e9bee0890460997c845cd8748643db.png", "extra": {"vendidos": 4025}}
    assert a[0]["titulo"].startswith("1000ML Bottle With Time Marker") and a[1]["precio"] == 1.09 and a[1]["extra"] == {"vendidos": 1123}
    r = [pl.leer_resena("aliexpress", i) for i in _fixture("aliexpress_resenas.json")]
    assert r[2] is None
    assert r[0]["fuente_id"] == "60097578940521292" and r[0]["pais"] == "BR" and r[0]["fecha"] == "2026-06-30" and r[0]["puntuacion"] == 4
    assert r[0]["producto"] == "3256806541493299" and r[0]["texto"].startswith("É a segunda que compro")
    assert r[1]["pais"] == "ES" and r[1]["fecha"] == "2026-01-03" and r[1]["puntuacion"] == 5
    assert pl.leer_resena("aliexpress", {**_fixture("aliexpress_resenas.json")[0], "buyer_country": "Brazil"})["pais"] is None


def test_resenas_traen_el_producto_del_link_pedido():
    """Ola final F5: Walmart y AliExpress devuelven el link que les mandamos; de ahí sale el id del producto
    pedido aunque `productId` sea el de una variante."""
    from nicho.fuentes import plataformas as pl
    w = _fixture("walmart_resenas.json")[0]
    assert pl.leer_resena("walmart", w)["producto_pedido"] == "5394318269"
    sin_eco = {k: v for k, v in w.items() if k != "requestedInput"}
    assert pl.leer_resena("walmart", sin_eco)["producto_pedido"] == "5394318269"                  # cae a productUrl
    assert pl.leer_resena("walmart", {**sin_eco, "productUrl": "https://www.walmart.com/ip/Botella-Azul/17345973281?classType=VARIANT"}
                          )["producto_pedido"] == "17345973281"
    assert pl.leer_resena("walmart", {k: v for k, v in sin_eco.items() if k != "productUrl"})["producto_pedido"] is None
    a = _fixture("aliexpress_resenas.json")[0]
    assert pl.leer_resena("aliexpress", a)["producto_pedido"] == "3256806541493299"
    assert pl.leer_resena("aliexpress", {**a, "product_url": "https://es.aliexpress.com/item/1005006.html?spm=x"})["producto_pedido"] == "1005006"
    assert pl.leer_resena("aliexpress", {k: v for k, v in a.items() if k != "product_url"})["producto_pedido"] is None
    assert pl.leer_resena("aliexpress", {**a, "product_url": "javascript:alert(1)"})["producto_pedido"] is None


def test_precio_de_aliexpress_siempre_en_dolares():
    """Ola final F6: AliExpress busca con country=US y currency=USD: un «$» es dólar aunque el estudio sea de Colombia."""
    from nicho.fuentes import plataformas as pl
    base = {"productId": "3256806541493299", "title": "Botella 1L", "productUrl": "https://www.aliexpress.com/item/3256806541493299.html"}
    p = pl.leer_producto("aliexpress", {**base, "price": "$4.03"}, "CO")
    assert p["precio"] == 4.03 and p["moneda"] == "USD"
    assert pl.leer_producto("aliexpress", {**base, "price": 4.03}, "MX")["moneda"] == "USD"                # número sin moneda
    assert pl.leer_producto("aliexpress", {**base, "price": 4.03, "currency": "EUR"}, "CO")["moneda"] == "EUR"
    assert pl.leer_producto("aliexpress", base, "CO")["moneda"] is None                                   # sin precio, sin moneda


def test_pais_del_comprador_uk_es_gb():
    """Ola final F8: AliExpress llama «UK» al Reino Unido; el ISO es GB."""
    from nicho.fuentes import plataformas as pl
    assert pl._pais_iso("UK") == "GB" and pl._pais_iso("uk") == "GB" and pl._pais_iso("BR") == "BR" and pl._pais_iso("Brazil") is None
    assert pl.leer_resena("aliexpress", {**_fixture("aliexpress_resenas.json")[0], "buyer_country": "UK"})["pais"] == "GB"
