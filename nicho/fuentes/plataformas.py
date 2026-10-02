"""
Registro de tiendas para la investigación automática del nicho (spec Parte 3
§3 y Parte 4 `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`):
por tienda, los países donde tiene sitio y su `casa` (el sitio principal), el
actor de Apify que BUSCA productos por palabra clave y el que trae RESEÑAS por
producto, con su precio por resultado y el arranque que algunos cobran por
corrida (`usd_por_corrida`; precios verificados en Apify: Parte 3 el
2026-09-20, Walmart y AliExpress con centavos el 2026-09-30), cómo se arman
las entradas y cómo se lee un producto o una reseña de su salida.

Otro mercado (Parte 4 §2): una tienda sin sitio en el país del estudio no se
rechaza; `mercado()` dice ("otro", casa) y busca y trae reseñas de su sitio
principal (`sitio()`), en el idioma de ese sitio (`idioma_busqueda()`;
AliExpress siempre en inglés). El techo de cada corrida (`tope`) es lo que va
en `maxTotalChargeUsd` y lo que suma el estimado; `costo` es lo cobrado.

Solo datos y funciones puras: nada de red ni de base. Los lectores son
tolerantes (varias claves candidatas por campo); un ítem sin id o sin texto
se descarta (None). Nunca se lee el nombre del autor ni del comprador.

  amazon      búsqueda `junglee~amazon-crawler` (US$ 5 / 1 000): no acepta
              palabras sueltas, así que la entrada lleva la URL de búsqueda
              del dominio del país (`https://www.amazon.<tld>/s?k=…`).
              reseñas `junglee~amazon-reviews-scraper` (US$ 6 / 1 000, mismo
              publicador que la búsqueda): UNA corrida POR PRODUCTO (no una
              con todos los `productUrls`: verificado en producción el
              2026-10-01, el plan FREE de Apify solo lee 1 link y entrega 10
              reseñas por corrida -- una corrida con varios productUrls deja
              sin leer a todos menos el primero; Starter sube ese tope a 40),
              2048 MB por corrida (`memoria_mb`, para que quepan 5 a la vez
              en el límite de 16 GB de la cuenta) y techo mínimo US$ 0,50 por
              corrida -- ese mínimo solo va en lo que se MANDA a Apify
              (`maxTotalChargeUsd`, Apify lo exige); el estimado que se
              muestra es el peor caso real de cada corrida, sin el mínimo
              (axesso se dejó de usar el 2026-10-01: pide acceso completo a
              la cuenta).
  meli        búsqueda `karamelo~mercado-libre-listings-scraper` (US$ 2 /
              1 000, 18 países): UN `keyword` + `country` (URL del sitio) por
              corrida. reseñas `karamelo~mercadolibre-review-scraper` (US$
              1,50 / 1 000): `productUrls` + `maxReviewsPerProduct`.
  tiktok_shop `unseenuser~tiktok-shop-scraper` (US$ 4,50 / 1 000) en modo
              `shop_search` y `product_reviews`; sin lista de países.
  walmart     búsqueda `s-r~walmart-scraper` (US$ 1 / 1 000 + US$ 0,001 por
              corrida; UNA `query` por corrida; sin precios: `fetch_prices`
              cobra US$ 0,003 por producto y no se pide). reseñas
              `apt_marble~walmart-reviews-scraper` (US$ 1 / 1 000): links
              `walmart.com/ip/<id>`, varios por corrida. Solo EE. UU.
  aliexpress  búsqueda `dami_studio~aliexpress-products-scraper` (US$ 0,12 /
              1 000 + US$ 0,001 por corrida; trae pedidos, no número de
              reseñas). reseñas `axlymxp~aliexpress-reviews-scraper` (US$ 3 /
              1 000 + US$ 0,01 por corrida; cada reseña trae el país del
              comprador). Vende en todo el mundo; busca en inglés desde EE. UU.

Los precios por resultado son los que cobra el plan de Apify de Creatv (FREE); un plan de pago
puede bajar algunos de ellos. Amazon búsqueda y MELI reseñas se corrigieron el 2026-10-01 tras
verificarlos contra el cobro real de corridas reales (antes US$ 3 y US$ 0,70 por 1 000, por debajo
de lo que Apify cobra de verdad: un precio bajo hace que `maxTotalChargeUsd` corte la corrida antes
de lo pedido y el gasto registrado quede por debajo del real).
"""
import math
import re
from urllib.parse import quote_plus

from flask_babel import gettext

from idiomas import N_
from nicho.fuentes.base import ErrorFuente

TODOS = "*"
PAISES_AMAZON = {"US": "com", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it", "ES": "es", "NL": "nl", "SE": "se", "CA": "ca",
                 "MX": "com.mx", "BR": "com.br", "AU": "com.au", "IN": "in", "JP": "co.jp", "AE": "ae"}
PAISES_MELI = {"AR": "https://listado.mercadolibre.com.ar/", "BO": "https://listado.mercadolibre.com.bo/",
               "BR": "https://lista.mercadolivre.com.br/", "CL": "https://listado.mercadolibre.cl/",
               "CO": "https://listado.mercadolibre.com.co/", "CR": "https://listado.mercadolibre.co.cr/",
               "DO": "https://listado.mercadolibre.com.do/", "EC": "https://listado.mercadolibre.com.ec/",
               "GT": "https://listado.mercadolibre.com.gt/", "HN": "https://listado.mercadolibre.com.hn/",
               "MX": "https://listado.mercadolibre.com.mx/", "NI": "https://listado.mercadolibre.com.ni/",
               "PA": "https://listado.mercadolibre.com.pa/", "PE": "https://listado.mercadolibre.com.pe/",
               "PY": "https://listado.mercadolibre.com.py/", "SV": "https://listado.mercadolibre.com.sv/",
               "UY": "https://listado.mercadolibre.com.uy/", "VE": "https://listado.mercadolibre.com.ve/"}
PAISES_WALMART = {"US": "https://www.walmart.com/"}
IDIOMA_POR_PAIS = {"SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es", "PE": "es", "UY": "es", "EC": "es", "BO": "es",
                   "PY": "es", "VE": "es", "CR": "es", "PA": "es", "DO": "es", "GT": "es", "HN": "es", "NI": "es", "SV": "es",
                   "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en", "AE": "en", "BR": "pt", "DE": "de", "FR": "fr",
                   "IT": "it", "NL": "nl", "JP": "ja"}
IDIOMAS = IDIOMA_POR_PAIS          # nombre viejo, lo importan nicho.investigacion y nicho.rutas
_MONEDA_POR_SIMBOLO = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "kr": "SEK", "R$": "BRL", "¥": "JPY", "₹": "INR", "C$": "CAD",
                       "A$": "AUD", "MX$": "MXN"}
_RE_HTTP = re.compile(r"^https?://", re.IGNORECASE)      # la misma regla que base.normalizar_comentario
# «$» a secas en la tienda de estos países es la moneda local (prueba real 2026-09-30:
# Amazon México devuelve {"value": 149.99, "currency": "$"} y son pesos)
_DOLAR_LOCAL = {"MX": "MXN", "CO": "COP", "AR": "ARS", "CL": "CLP", "UY": "UYU", "DO": "DOP", "CA": "CAD", "AU": "AUD",
                "US": "USD", "EC": "USD", "SV": "USD", "PA": "USD"}
_MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
# El id del producto dentro del link que le mandamos al actor de reseñas (y que devuelve con cada una):
# amazon.<tld>/dp/<asin>, walmart.com/ip/<id> (o /ip/<nombre>/<id>) y aliexpress.com/item/<id>.html.
_RE_ID_AMAZON = re.compile(r"/dp/([A-Z0-9]{10})")
_RE_ID_WALMART = re.compile(r"/ip/(?:[^/?#]+/)*(\d+)/?(?:[?#]|$)")
_RE_ID_ALIEXPRESS = re.compile(r"/item/(\d+)\.html")
# Mercado Libre: la ficha de catálogo que agrupa publicaciones (`/p/MCO59691162`, sin guion) o,
# si no hay catálogo, la página de la publicación (`.../MCO-123456789-slug`, con guion) — las
# reseñas devuelven el id de catálogo, no el `fuente_id` de la publicación que buscamos (prueba
# de centavos 2026-10-01, estudio 3 de colorado_forja).
_RE_ID_MELI_CATALOGO = re.compile(r"/p/([A-Za-z]{2,4}\d+)")
_RE_ID_MELI_ITEM = re.compile(r"/([A-Za-z]{2,4})-(\d+)(?:[-/?#]|$)")
_PAIS_ALIAS = {"UK": "GB"}                  # AliExpress llama «UK» al Reino Unido


# ------------------------------------------------------------ helpers ---

def _primero(item, *claves):
    for k in claves:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def _flotante(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    for simbolo in sorted(_MONEDA_POR_SIMBOLO, key=len, reverse=True):
        s = s.replace(simbolo, "")
    if "," in s and "." in s:
        # los dos: el que va de último es el decimal ("1.234,56" europeo / "1,234.56" gringo)
        decimal, miles = (",", ".") if s.rfind(",") > s.rfind(".") else (".", ",")
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s:
        partes = s.split(",")
        # "12,99" o "4,5" es coma decimal; "1,234" o "1,234,567" son comas de miles
        s = s.replace(",", ".") if len(partes) == 2 and 1 <= len(partes[1]) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[-1]) == 3):
        s = s.replace(".", "")             # "59.900" / "1.234.567" (miles a la latina) -> 59900 / 1234567
    try:
        return float(s)
    except ValueError:
        return None


def _entero(v):
    f = _flotante(v)
    return int(f) if f is not None else None


def _moneda(v, pais=None):
    if not v:
        return None
    s = str(v).strip()
    if len(s) == 3 and s.isalpha():
        return s.upper()
    if s == "$" and pais:
        return _DOLAR_LOCAL.get(str(pais).upper(), "USD")
    return _MONEDA_POR_SIMBOLO.get(s)


def _precio_moneda(item):
    """`price`/`currentPrice` como objeto {value, currency}, número o texto con
    símbolo, más `currency` suelto. Un «$» a secas se lee con la moneda del país
    (`loadedCountryCode`; `leer_producto` lo pone con el país de la búsqueda si
    el actor no lo trae): en Amazon México son pesos, no dólares. -> (precio, moneda)."""
    pais = item.get("loadedCountryCode") or None
    p = _primero(item, "price", "currentPrice", "precio")
    if isinstance(p, dict):
        return _flotante(p.get("value")), (_moneda(p.get("currency"), pais) or _moneda(item.get("currency"), pais))
    moneda = _moneda(item.get("currency"), pais)
    if moneda is None and isinstance(p, str):
        for simbolo in sorted(_MONEDA_POR_SIMBOLO, key=len, reverse=True):
            if simbolo in p:
                moneda = _moneda(simbolo, pais) if simbolo == "$" else _MONEDA_POR_SIMBOLO[simbolo]
                break
    return _flotante(p), moneda


def usd(n, precio):
    """n resultados × precio por resultado, hacia arriba al centavo (round antes
    de ceil: 30 × 0.003 × 100 no es 9 exacto en binario)."""
    return math.ceil(round(max(0, int(n or 0)) * precio * 100, 6)) / 100


def tope(max_items, actor):
    """Techo de cobro de UNA corrida: `max_items` × precio por resultado + el
    arranque de la corrida (`usd_por_corrida`), hacia arriba al centavo. Es lo
    que va en `maxTotalChargeUsd` y lo que suma el estimado (spec Parte 4 §2)."""
    bruto = max(0, int(max_items or 0)) * actor["usd_por_resultado"] + float(actor.get("usd_por_corrida") or 0)
    return math.ceil(round(bruto * 100, 6)) / 100


def costo(n_resultados, n_corridas, actor):
    """Lo cobrado: resultados × precio + corridas lanzadas × arranque, hacia
    arriba al centavo (una corrida con arranque cobra aunque no traiga nada)."""
    bruto = (max(0, int(n_resultados or 0)) * actor["usd_por_resultado"]
             + max(0, int(n_corridas or 0)) * float(actor.get("usd_por_corrida") or 0))
    return math.ceil(round(bruto * 100, 6)) / 100


def _texto(v, largo):
    return ("" if v is None else str(v)).strip()[:largo]


def _url(v):
    """Un link que viene del dataset y termina en un `href`: solo http(s).
    `//host/…` se lee como https; cualquier otro esquema (javascript:, data:…)
    o una ruta relativa -> None."""
    s = _texto(v, 500)
    if s.startswith("//"):
        s = "https:" + s
    return s if _RE_HTTP.match(s) else None


def _sin_guion(v):
    return str(v or "").replace("-", "").strip()


def _id_de_link(v, patron):
    """El id del producto dentro de un link http(s) (el que le pedimos al actor), o None."""
    m = patron.search(_url(v) or "")
    return m.group(1) if m else None


def _id_meli_de_link(v):
    url = _url(v) or ""
    m = _RE_ID_MELI_CATALOGO.search(url)
    if m:
        return m.group(1)
    m = _RE_ID_MELI_ITEM.search(url)
    return f"{m.group(1)}{m.group(2)}" if m else None


_ID_EN_LINK = {"meli": _id_meli_de_link, "walmart": lambda v: _id_de_link(v, _RE_ID_WALMART),
               "aliexpress": lambda v: _id_de_link(v, _RE_ID_ALIEXPRESS), "amazon": lambda v: _id_de_link(v, _RE_ID_AMAZON)}


def id_en_link(clave, url):
    """El id del producto de `clave` dentro de un link SUYO (de catálogo o de
    publicación), para reconocer el producto de una reseña que no lo identifica
    por su `fuente_id` ni por el link que le pedimos (`producto_pedido`). Solo
    meli, walmart y aliexpress saben leerlo; las demás tiendas, o un link que no
    sea http(s), -> None."""
    f = _ID_EN_LINK.get(clave)
    return f(url) if f else None


# ------------------------------------------------------------- amazon ---

def _busqueda_amazon(consultas, pais, productos_por_consulta):
    tld = PAISES_AMAZON[pais]
    return [{"entrada": {"categoryOrProductUrls": [{"url": f"https://www.amazon.{tld}/s?k={quote_plus(c)}"} for c in consultas],
                         "maxItemsPerStartUrl": productos_por_consulta, "maxSearchPagesPerStartUrl": 2, "proxyCountry": pais},
             "max_items": len(consultas) * productos_por_consulta, "etiqueta": "búsqueda"}]


_RE_ASIN = re.compile(r"[A-Z0-9]{10}")
MAX_VARIANTES = 200          # un anuncio de Amazon puede tener cientos de combinaciones de color y talla


def _asin(v):
    """Un ASIN válido en mayúsculas, o None."""
    v = v.strip().upper() if isinstance(v, str) else ""
    return v if _RE_ASIN.fullmatch(v) else None


def _producto_amazon(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    vendedor = _primero(item, "seller")
    if isinstance(vendedor, dict):                       # el actor real lo manda como {name, id, url, …}
        vendedor = vendedor.get("name")
    if vendedor:
        extra["vendedor"] = _texto(vendedor, 120)
    if item.get("inStock") is not None:
        extra["en_stock"] = bool(item.get("inStock"))
    asin = _texto(_primero(item, "asin"), 120)
    # Las variantes del mismo anuncio (colores, tallas) comparten reseñas: `FuentePlataforma.buscar` e
    # `investigacion.elegir` dejan una sola (prueba real 2026-10-01: dos variantes elegidas trajeron las mismas
    # reseñas, pagadas dos veces). La lista del actor trae el ASIN propio; si no lo trae, se suma. Lo que no sea
    # una lista se ignora: la lectura de un dataset ya pagado nunca se rompe por un campo raro.
    crudas = item.get("variantAsins")
    variantes = {_asin(v) for v in crudas} - {None} if isinstance(crudas, (list, tuple)) else set()
    if variantes and _asin(asin):
        variantes.add(_asin(asin))
    if len(variantes) > 1:
        extra["variantes"] = sorted(variantes)[:MAX_VARIANTES]
    return {"fuente_id": asin, "titulo": _texto(_primero(item, "title"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda,
            "estrellas": _flotante(_primero(item, "stars", "rating")), "n_resenas": _entero(_primero(item, "reviewsCount", "reviewCount")),
            "url": _url(_primero(item, "url")), "imagen": _url(_primero(item, "thumbnailImage", "image")),
            "extra": extra}


def _resenas_amazon(productos, pais, resenas_por_producto):
    # junglee en el plan FREE de Apify solo lee 1 link y entrega 10 reseñas POR CORRIDA (verificado en
    # producción el 2026-10-01): una corrida con los productUrls de varios productos deja sin leer a
    # todos menos el primero. Por eso UNA corrida POR PRODUCTO (nunca junta varios productUrls); al
    # subir de plan (Starter) solo cambia el tope de reseñas (`max_resenas_por_producto`), no esto.
    tld = PAISES_AMAZON[pais]
    return [{"entrada": {"productUrls": [{"url": f"https://www.amazon.{tld}/dp/{p['fuente_id']}"}],
                         "maxReviews": resenas_por_producto, "sort": "recent", "includeGdprSensitive": False,
                         "scrapeProductDetails": False, "deduplicateRedirectedAsins": True},
             "max_items": resenas_por_producto, "etiqueta": p["fuente_id"]}
            for p in productos]


def _resena_amazon(item):
    partes = [_texto(item.get("reviewTitle"), 300), _texto(item.get("reviewDescription"), 2000)]
    return {"fuente_id": _texto(_primero(item, "reviewId"), 120), "texto": ". ".join(x for x in partes if x),
            "puntuacion": _entero(_primero(item, "ratingScore")), "fecha": _primero(item, "date"), "url": None,
            "producto": _texto(_primero(item, "productOriginalAsin", "productAsin"), 120) or None,
            # el link que le mandamos (`input`): identifica el producto aunque la reseña sea de una
            # variante (`productAsin`/`productOriginalAsin` distinto); el actor también manda
            # `userId`/`userProfileLink` (el comprador) — nunca se leen.
            "producto_pedido": _id_de_link(_primero(item, "input"), _RE_ID_AMAZON)}


# --------------------------------------------------------------- meli ---

def _busqueda_meli(consultas, pais, productos_por_consulta):
    sitio = PAISES_MELI[pais]
    return [{"entrada": {"keyword": c, "country": sitio, "sort": "relevance", "maxPages": 1, "extractProductDetails": False},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_meli(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    if _primero(item, "seller", "sellerName"):
        extra["vendedor"] = _texto(_primero(item, "seller", "sellerName"), 120)
    vendidos = _entero(_primero(item, "sold", "soldQuantity"))
    if vendidos is not None:
        extra["vendidos"] = vendidos
    # Claves del actor real (prueba de centavos 2026-09-30): publicationId, productUrl,
    # currentPrice + currency, thumbnailUrl, reviewCount, rating, soldQuantity, sellerName.
    return {"fuente_id": _sin_guion(_primero(item, "id", "productId", "itemId", "publicationId", "sku"))[:120],
            "titulo": _texto(_primero(item, "title", "name"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda,
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviews", "reviewsCount", "reviewCount")),
            "url": _url(_primero(item, "productUrl", "url", "link", "permalink")),
            "imagen": _url(_primero(item, "thumbnailUrl", "thumbnail", "image")), "extra": extra}


def _resenas_meli(productos, pais, resenas_por_producto):
    return [{"entrada": {"productUrls": [p["url"] for p in productos], "maxReviewsPerProduct": resenas_por_producto, "reviewOrder": "relevance"},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_meli(item):
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": _texto(_primero(item, "reviewText", "text", "content"), 2000),
            "puntuacion": _entero(_primero(item, "reviewRating", "rating")), "fecha": _primero(item, "reviewDate", "date"), "url": None,
            "producto": _sin_guion(_primero(item, "productId", "catalogProductId"))[:120] or None}


# -------------------------------------------------------- tiktok_shop ---

def _busqueda_tiktok_shop(consultas, pais, productos_por_consulta):
    return [{"entrada": {"mode": "shop_search", "searchKeywords": list(consultas), "maxResults": len(consultas) * productos_por_consulta},
             "max_items": len(consultas) * productos_por_consulta, "etiqueta": "búsqueda"}]


def _producto_tiktok_shop(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    vendidos = _entero(_primero(item, "soldCount", "sold"))
    if vendidos is not None:
        extra["vendidos"] = vendidos
    return {"fuente_id": _texto(_primero(item, "productId", "id"), 120), "titulo": _texto(_primero(item, "title", "name"), 300),
            "marca": _texto(_primero(item, "brand", "shopName"), 120) or None, "precio": precio, "moneda": moneda or ("USD" if precio is not None else None),
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviewCount", "reviewsCount")),
            "url": _url(_primero(item, "productUrl", "url")), "imagen": _url(_primero(item, "image", "thumbnail")),
            "extra": extra}


def _resenas_tiktok_shop(productos, pais, resenas_por_producto):
    return [{"entrada": {"mode": "product_reviews", "productUrls": [p["url"] for p in productos], "maxReviewsPerProduct": resenas_por_producto},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_tiktok_shop(item):
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": _texto(_primero(item, "text", "content"), 2000),
            "puntuacion": _entero(_primero(item, "rating", "ratingStars")), "fecha": _primero(item, "postedAt", "createTime", "date"), "url": None,
            "producto": _texto(_primero(item, "productId"), 120) or None}


# ------------------------------------------------------------ walmart ---

def _busqueda_walmart(consultas, pais, productos_por_consulta):
    # UNA `query` por corrida (verificado 2026-09-30); `fetch_prices` cobraría US$ 0,003 por producto: no se pide
    return [{"entrada": {"mode": "search", "query": c, "limit": productos_por_consulta, "fetch_prices": False},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_walmart(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    if _primero(item, "seller"):
        extra["vendedor"] = _texto(_primero(item, "seller"), 120)
    if item.get("availability"):
        extra["en_stock"] = str(item.get("availability")).upper() == "IN_STOCK"
    # Claves del actor real (verificación 2026-09-30): item_id, title, rating, reviews_count, url, image, seller,
    # availability, currency; sin precio (no se pide `fetch_prices`), así que tampoco moneda.
    return {"fuente_id": _texto(_primero(item, "item_id", "usItemId", "id"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda if precio is not None else None,
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviews_count", "reviewsCount")),
            "url": _url(_primero(item, "url")), "imagen": _url(_primero(item, "image", "thumbnail")), "extra": extra}


def _resenas_walmart(productos, pais, resenas_por_producto):
    # el link se arma con el id (la forma verificada), no con el que trajo la búsqueda
    return [{"entrada": {"products": [f"https://www.walmart.com/ip/{p['fuente_id']}" for p in productos],
                         "maxReviewsPerProduct": resenas_por_producto, "includeProductSummary": False},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_walmart(item):
    es_resena = item.get("rowType") in (None, "", "review")          # otra fila (p. ej. el resumen del producto) no es reseña
    partes = [_texto(item.get("title"), 300), _texto(item.get("text"), 2000)]
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120) if es_resena else "", "texto": ". ".join(x for x in partes if x),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _primero(item, "date"), "url": None,
            "producto": _texto(_primero(item, "productId"), 120) or None,
            # el link que le mandamos (`requestedInput`; `productUrl` si no lo repite): `productId` puede ser el de una variante
            "producto_pedido": _id_de_link(_primero(item, "requestedInput", "productUrl"), _RE_ID_WALMART)}


# --------------------------------------------------------- aliexpress ---

def _busqueda_aliexpress(consultas, pais, productos_por_consulta):
    # una corrida por consulta (`maxItems` es de toda la corrida); en inglés y desde EE. UU., como se verificó
    return [{"entrada": {"searchQueries": [c], "maxItems": productos_por_consulta, "country": "US", "currency": "USD", "language": "en_US"},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_aliexpress(item):
    # Siempre busca con country=US y currency=USD (`_busqueda_aliexpress`): un «$» es dólar sea cual sea el
    # país del estudio, y un precio sin moneda también.
    precio, moneda = _precio_moneda({**item, "loadedCountryCode": "US"})
    if precio is not None and not moneda:
        moneda = "USD"
    extra = {}
    vendidos = _entero(_primero(item, "orders", "sold"))
    if vendidos is not None:
        extra["vendidos"] = vendidos                  # el buscador no trae número de reseñas: desempata por pedidos
    return {"fuente_id": _texto(_primero(item, "productId", "id"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": None, "precio": precio, "moneda": moneda, "estrellas": _flotante(_primero(item, "rating")),
            "n_resenas": _entero(_primero(item, "reviewsCount", "reviewCount")),
            "url": _url(_primero(item, "productUrl", "url")), "imagen": _url(_primero(item, "imageUrl", "image")), "extra": extra}


def _resenas_aliexpress(productos, pais, resenas_por_producto):
    return [{"entrada": {"productUrls": [f"https://www.aliexpress.com/item/{p['fuente_id']}.html" for p in productos],
                         "maxReviewsPerProduct": resenas_por_producto, "language": "en_US"},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _fecha_dia_mes(v):
    """«30 Jun 2026» -> «2026-06-30» (meses en inglés, sin depender del locale);
    cualquier otra forma vuelve tal cual (normalizar_comentario la lee o la deja en None)."""
    partes = str(v or "").replace(",", " ").split()
    if len(partes) == 3 and partes[0].isdigit() and partes[2].isdigit() and partes[1][:3].lower() in _MESES_EN:
        return f"{int(partes[2]):04d}-{_MESES_EN[partes[1][:3].lower()]:02d}-{int(partes[0]):02d}"
    return v or None


def _pais_iso(v):
    s = _texto(v, 10).upper()
    s = _PAIS_ALIAS.get(s, s)
    return s if len(s) == 2 and s.isalpha() else None


def _resena_aliexpress(item):
    return {"fuente_id": _texto(_primero(item, "review_id", "reviewId", "id"), 120),
            "texto": _texto(_primero(item, "review_text", "text"), 2000),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _fecha_dia_mes(_primero(item, "review_date", "date")), "url": None,
            "producto": _texto(_primero(item, "product_id", "productId"), 120) or None,
            "producto_pedido": _id_de_link(_primero(item, "product_url", "productUrl"), _RE_ID_ALIEXPRESS),
            "pais": _pais_iso(_primero(item, "buyer_country", "country"))}


# ----------------------------------------------------------- registro ---

PLATAFORMAS = {
    "amazon": {
        "nombre": "Amazon", "paises": PAISES_AMAZON, "casa": "US",
        "busqueda": {"actor": "junglee~amazon-crawler", "nombre": N_("Búsqueda en Amazon"), "usd_por_resultado": 0.005, "usd_por_corrida": 0.0,
                     "armar_entradas": _busqueda_amazon, "leer_producto": _producto_amazon},
        "resenas": {"actor": "junglee~amazon-reviews-scraper", "nombre": N_("Reseñas de Amazon"), "usd_por_resultado": 0.006, "usd_por_corrida": 0.0,
                    "tope_minimo_usd": 0.5, "max_resenas_por_producto": 10, "por_producto": True, "necesita_link": False,
                    "memoria_mb": 2048, "armar_entradas": _resenas_amazon, "leer_resena": _resena_amazon},
    },
    "meli": {
        "nombre": "Mercado Libre", "paises": PAISES_MELI, "casa": "MX",
        "busqueda": {"actor": "karamelo~mercado-libre-listings-scraper", "nombre": N_("Búsqueda en Mercado Libre"), "usd_por_resultado": 0.002,
                     "usd_por_corrida": 0.0, "armar_entradas": _busqueda_meli, "leer_producto": _producto_meli},
        "resenas": {"actor": "karamelo~mercadolibre-review-scraper", "nombre": N_("Opiniones de Mercado Libre"), "usd_por_resultado": 0.0015,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": True, "armar_entradas": _resenas_meli,
                    "leer_resena": _resena_meli},
    },
    "tiktok_shop": {
        "nombre": "TikTok Shop", "paises": TODOS, "casa": None,
        "busqueda": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": N_("Búsqueda en TikTok Shop"), "usd_por_resultado": 0.0045,
                     "usd_por_corrida": 0.0, "armar_entradas": _busqueda_tiktok_shop, "leer_producto": _producto_tiktok_shop},
        "resenas": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": N_("Reseñas de TikTok Shop"), "usd_por_resultado": 0.0045,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": True, "armar_entradas": _resenas_tiktok_shop,
                    "leer_resena": _resena_tiktok_shop},
    },
    "walmart": {
        "nombre": "Walmart", "paises": PAISES_WALMART, "casa": "US",
        "busqueda": {"actor": "s-r~walmart-scraper", "nombre": N_("Búsqueda en Walmart"), "usd_por_resultado": 0.001, "usd_por_corrida": 0.001,
                     "armar_entradas": _busqueda_walmart, "leer_producto": _producto_walmart},
        "resenas": {"actor": "apt_marble~walmart-reviews-scraper", "nombre": N_("Reseñas de Walmart"), "usd_por_resultado": 0.001,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": False, "armar_entradas": _resenas_walmart,
                    "leer_resena": _resena_walmart},
    },
    "aliexpress": {
        "nombre": "AliExpress", "paises": TODOS, "casa": None, "idioma": "en",
        "busqueda": {"actor": "dami_studio~aliexpress-products-scraper", "nombre": N_("Búsqueda en AliExpress"), "usd_por_resultado": 0.00012,
                     "usd_por_corrida": 0.001, "armar_entradas": _busqueda_aliexpress, "leer_producto": _producto_aliexpress},
        "resenas": {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": N_("Reseñas de AliExpress"), "usd_por_resultado": 0.003,
                    "usd_por_corrida": 0.01, "por_producto": False, "necesita_link": False, "armar_entradas": _resenas_aliexpress,
                    "leer_resena": _resena_aliexpress},
    },
}


def claves():
    return tuple(PLATAFORMAS)


def _plataforma(clave):
    if clave not in PLATAFORMAS:
        raise ErrorFuente(gettext("Plataforma desconocida: %(plataforma)s", plataforma=clave))
    return PLATAFORMAS[clave]


def nombre(clave):
    return _plataforma(clave)["nombre"]


def cubre(clave, pais):
    paises = _plataforma(clave)["paises"]
    return paises == TODOS or (pais or "").upper() in paises


def disponibles(pais):
    return [c for c in PLATAFORMAS if cubre(c, pais)]


def dominio(clave, pais):
    """TLD de Amazon ('se'), URL del sitio de Mercado Libre, None si la
    plataforma no distingue país o no cubre ese país."""
    paises = _plataforma(clave)["paises"]
    if paises == TODOS:
        return None
    return paises.get((pais or "").upper())


def idioma(pais):
    return IDIOMA_POR_PAIS.get((pais or "").upper(), "en")


def mercado(clave, pais):
    """("local", PAIS) si la tienda tiene sitio en ese país o vende en todo el
    mundo; ("otro", casa) si no: busca y trae reseñas de su sitio principal
    (spec Parte 4 §2). Nunca rechaza por país."""
    pais = (pais or "").upper()
    if cubre(clave, pais):
        return "local", pais
    return "otro", _plataforma(clave)["casa"]


def sitio(clave, pais):
    """El país del sitio donde busca esa tienda para un estudio de `pais`."""
    return mercado(clave, pais)[1]


def idioma_busqueda(clave, pais):
    """El idioma de las búsquedas en esa tienda: el fijo de la tienda
    (AliExpress busca en inglés) o el del sitio donde busca."""
    return _plataforma(clave).get("idioma") or idioma(sitio(clave, pais))


def actor_busqueda(clave):
    a = _plataforma(clave)["busqueda"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "usd_por_corrida": a["usd_por_corrida"]}


def actor_resenas(clave):
    a = _plataforma(clave)["resenas"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "usd_por_corrida": a["usd_por_corrida"]}


def estimar_busqueda(clave, n_consultas, productos_por_consulta, pais=None):
    """Peor caso REAL de la búsqueda: la suma de `peor_usd` de las corridas que se
    lanzarían (resultados × precio + arranque, sin ningún mínimo), en el sitio que
    toca. El techo que de verdad se MANDA a Apify (`max_usd`) puede ser más alto
    solo por el mínimo que algún actor exige por corrida (enmienda 2026-10-01,
    ruling 3 de `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`)."""
    consultas = [f"consulta {k + 1}" for k in range(max(1, int(n_consultas)))]
    return round(sum(e["peor_usd"] for e in entradas_busqueda(clave, consultas, pais, productos_por_consulta)), 2)


def estimar_resenas(clave, n_productos, resenas_por_producto, pais=None):
    """Peor caso REAL de las reseñas de `n_productos` elegidos, igual que la búsqueda."""
    productos = [{"fuente_id": f"p{k + 1}", "url": f"https://ejemplo.invalid/p{k + 1}", "titulo": ""} for k in range(max(1, int(n_productos)))]
    return round(sum(e["peor_usd"] for e in entradas_resenas(clave, productos, pais, resenas_por_producto)), 2)


def _con_tope(entradas, actor):
    # Un actor con techo mínimo por corrida (junglee: Apify rechaza `maxTotalChargeUsd` < US$ 0,50)
    # nunca MANDA menos que ese mínimo, aunque la corrida sea tan chica que `tope()` pida menos
    # (`max_usd`). El estimado que se le muestra a la persona ANTES de aprobar es el peor caso REAL de
    # la corrida (`peor_usd`, sin el mínimo): mostrar el mínimo ahí exagera el costo de una corrida
    # chica que nunca lo va a cobrar (ruling 3, 2026-10-01). Para un actor sin mínimo los dos valen
    # igual. `memoria_mb`, si el actor lo trae, viaja también (`arrancar`/`correr_lote`).
    minimo = float(actor.get("tope_minimo_usd") or 0)
    memoria_mb = actor.get("memoria_mb")
    salida = []
    for e in entradas:
        peor = tope(e["max_items"], actor)
        extra = {"memoria_mb": memoria_mb} if memoria_mb else {}
        salida.append({**e, "max_usd": max(peor, minimo), "peor_usd": peor, **extra})
    return salida


def entradas_busqueda(clave, consultas, pais, productos_por_consulta):
    """Lista de corridas `{"entrada", "max_items", "max_usd", "etiqueta"}` en el
    sitio que toca (`sitio`: el del país o, de otro mercado, el principal)."""
    p = _plataforma(clave)
    consultas = [c.strip() for c in (consultas or []) if (c or "").strip()]
    if not consultas:
        raise ErrorFuente(gettext("%(plataforma)s: no hay consultas para buscar.", plataforma=p["nombre"]))
    return _con_tope(p["busqueda"]["armar_entradas"](consultas, sitio(clave, pais), max(1, int(productos_por_consulta))), p["busqueda"])


def leer_producto(clave, item, pais=None):
    """Producto normalizado (fuente_id, titulo, marca, precio, moneda, estrellas,
    n_resenas, url, imagen, extra) o None si no trae id o título. `pais` (el de
    la búsqueda) resuelve un «$» a secas cuando el actor no dice su país."""
    item = item if isinstance(item, dict) else {}
    if pais and not item.get("loadedCountryCode"):
        item = {**item, "loadedCountryCode": pais}
    d = _plataforma(clave)["busqueda"]["leer_producto"](item)
    return d if d["fuente_id"] and d["titulo"] else None


def entradas_resenas(clave, productos, pais, resenas_por_producto):
    p = _plataforma(clave)
    productos = [x for x in (productos or []) if (x or {}).get("fuente_id")]
    if not productos:
        raise ErrorFuente(gettext("%(plataforma)s: no hay productos de los que traer reseñas.", plataforma=p["nombre"]))
    if p["resenas"]["necesita_link"]:
        # Estas tiendas piden las reseñas por el link de la búsqueda: un producto sin
        # link (o con uno que no es http(s)) se salta; solo se para si ninguno lo tiene.
        productos = [x for x in productos if x.get("url")]
        if not productos:
            raise ErrorFuente(gettext("%(plataforma)s: un producto elegido no tiene link.", plataforma=p["nombre"]))
    resenas_por_producto = max(1, int(resenas_por_producto))
    tope_producto = p["resenas"].get("max_resenas_por_producto")
    if tope_producto:
        # Amazon (junglee): como máximo 40 reseñas por producto -- se recorta ANTES de armar la
        # corrida, para que el estimado (que arma la misma corrida con datos de relleno) y lo que
        # realmente se pide nunca se desentiendan.
        resenas_por_producto = min(resenas_por_producto, int(tope_producto))
    return _con_tope(p["resenas"]["armar_entradas"](productos, sitio(clave, pais), resenas_por_producto), p["resenas"])


def leer_resena(clave, item):
    """`{fuente_id, texto, puntuacion, fecha, url, producto[, producto_pedido][, pais]}` o
    None sin id o sin texto. `producto` es el id del producto en la plataforma
    (para el título y el link); `producto_pedido` (Walmart y AliExpress) es el id
    sacado del link que le mandamos al actor y que cada reseña devuelve: la
    atribuye a nuestro producto aunque `producto` sea el de una variante (None si
    no viene); `pais` es el ISO del comprador cuando el actor lo da (hoy solo
    AliExpress). El autor nunca se lee."""
    d = _plataforma(clave)["resenas"]["leer_resena"](item if isinstance(item, dict) else {})
    return d if d["fuente_id"] and d["texto"] else None
