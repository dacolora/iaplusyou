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
    assert pl.claves() == ("amazon", "meli", "tiktok_shop") and set(pl.claves()) == set(datos.FUENTES_PLATAFORMA)
    assert pl.nombre("meli") == "Mercado Libre"
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop"] and pl.disponibles("MX") == ["amazon", "meli", "tiktok_shop"]
    assert pl.disponibles("CO") == ["meli", "tiktok_shop"]                             # Amazon solo donde tiene tienda propia
    assert pl.disponibles("ZZ") == ["tiktok_shop"]
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
    assert pl.estimar_busqueda("amazon", 3, 20) == 0.18          # 60 × 0.003
    assert pl.estimar_resenas("amazon", 15, 100) == 1.35         # 1500 × 0.0009
    assert pl.estimar_busqueda("meli", 3, 20) == 0.12 and pl.estimar_resenas("meli", 15, 100) == 1.05
    assert pl.estimar_busqueda("tiktok_shop", 3, 20) == 0.27 and pl.estimar_resenas("tiktok_shop", 15, 100) == 6.75


def test_entradas_de_busqueda():
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    consultas = ["tofflor mot fotsmärta", "ortopediska tofflor"]
    e = pl.entradas_busqueda("amazon", consultas, "SE", 20)
    assert len(e) == 1 and e[0]["max_items"] == 40 and e[0]["max_usd"] == 0.12 and e[0]["etiqueta"] == "búsqueda"
    assert e[0]["entrada"] == {"categoryOrProductUrls": [{"url": "https://www.amazon.se/s?k=tofflor+mot+fotsm%C3%A4rta"},
                                                         {"url": "https://www.amazon.se/s?k=ortopediska+tofflor"}],
                               "maxItemsPerStartUrl": 20, "maxSearchPagesPerStartUrl": 2, "proxyCountry": "SE"}
    e = pl.entradas_busqueda("meli", ["pantuflas ortopédicas", "pantuflas memory foam"], "CO", 10)
    assert [x["entrada"] for x in e] == [{"keyword": "pantuflas ortopédicas", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False},
                                         {"keyword": "pantuflas memory foam", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False}]
    assert [x["max_items"] for x in e] == [10, 10] and [x["etiqueta"] for x in e] == ["pantuflas ortopédicas", "pantuflas memory foam"]
    e = pl.entradas_busqueda("tiktok_shop", ["cloud slippers"], "US", 20)
    assert e == [{"entrada": {"mode": "shop_search", "searchKeywords": ["cloud slippers"], "maxResults": 20}, "max_items": 20, "max_usd": 0.09, "etiqueta": "búsqueda"}]
    with pytest.raises(ErrorFuente):
        pl.entradas_busqueda("meli", ["x"], "SE", 10)                 # Mercado Libre no cubre Suecia
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
                  "max_items": 50, "max_usd": 0.04, "etiqueta": "reseñas"}]
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
