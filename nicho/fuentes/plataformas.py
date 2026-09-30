"""
Registro de plataformas para la investigación automática del nicho (spec
Parte 3 §3): por plataforma, los países que cubre y cómo se arma su dominio,
el actor de Apify que BUSCA productos por palabra clave y el que trae
RESEÑAS por producto, con precio por resultado (verificado 2026-09-20 en la
tienda de Apify; ver docs/nicho/apify-inventario-2026-09-20.md), cómo se
arman las entradas y cómo se lee un producto o una reseña de su salida.

Solo datos y funciones puras: nada de red ni de base. Los lectores son
tolerantes (varias claves candidatas por campo) porque la forma exacta de
salida de cada actor se confirma con la corrida de centavos; un ítem sin id o
sin texto se descarta (None). Nunca se lee el nombre del autor.

  amazon      búsqueda `junglee~amazon-crawler` (US$ 3 / 1 000): no acepta
              palabras sueltas, así que la entrada lleva la URL de búsqueda
              del dominio del país (`https://www.amazon.<tld>/s?k=…`).
              reseñas `axesso_data~amazon-reviews-scraper` (US$ 0,90 / 1 000,
              15 marketplaces): UN `asin` + `domainCode` por corrida, 10
              reseñas por página, `maxPages` ≤ 10 → una corrida por producto.
  meli        búsqueda `karamelo~mercado-libre-listings-scraper` (US$ 2 /
              1 000, 18 países): UN `keyword` + `country` (URL del sitio) por
              corrida. reseñas `karamelo~mercadolibre-review-scraper` (US$
              0,70 / 1 000): `productUrls` + `maxReviewsPerProduct`.
  tiktok_shop `unseenuser~tiktok-shop-scraper` (US$ 4,50 / 1 000) en modo
              `shop_search` y `product_reviews`; sin lista de países.
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
IDIOMA_POR_PAIS = {"SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es", "PE": "es", "UY": "es", "EC": "es", "BO": "es",
                   "PY": "es", "VE": "es", "CR": "es", "PA": "es", "DO": "es", "GT": "es", "HN": "es", "NI": "es", "SV": "es",
                   "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en", "AE": "en", "BR": "pt", "DE": "de", "FR": "fr",
                   "IT": "it", "NL": "nl", "JP": "ja"}
IDIOMAS = IDIOMA_POR_PAIS          # nombre viejo, lo importan nicho.investigacion y nicho.rutas
RESENAS_POR_PAGINA_AMAZON = 10
MAX_PAGINAS_AMAZON = 10
_MONEDA_POR_SIMBOLO = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "kr": "SEK", "R$": "BRL", "¥": "JPY", "₹": "INR", "C$": "CAD",
                       "A$": "AUD", "MX$": "MXN"}
_RE_HTTP = re.compile(r"^https?://", re.IGNORECASE)      # la misma regla que base.normalizar_comentario
# «$» a secas en la tienda de estos países es la moneda local (prueba real 2026-09-30:
# Amazon México devuelve {"value": 149.99, "currency": "$"} y son pesos)
_DOLAR_LOCAL = {"MX": "MXN", "CO": "COP", "AR": "ARS", "CL": "CLP", "UY": "UYU", "DO": "DOP", "CA": "CAD", "AU": "AUD",
                "US": "USD", "EC": "USD", "SV": "USD", "PA": "USD"}


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


# ------------------------------------------------------------- amazon ---

def _busqueda_amazon(consultas, pais, productos_por_consulta):
    tld = PAISES_AMAZON[pais]
    return [{"entrada": {"categoryOrProductUrls": [{"url": f"https://www.amazon.{tld}/s?k={quote_plus(c)}"} for c in consultas],
                         "maxItemsPerStartUrl": productos_por_consulta, "maxSearchPagesPerStartUrl": 2, "proxyCountry": pais},
             "max_items": len(consultas) * productos_por_consulta, "etiqueta": "búsqueda"}]


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
    return {"fuente_id": _texto(_primero(item, "asin"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda,
            "estrellas": _flotante(_primero(item, "stars", "rating")), "n_resenas": _entero(_primero(item, "reviewsCount", "reviewCount")),
            "url": _url(_primero(item, "url")), "imagen": _url(_primero(item, "thumbnailImage", "image")),
            "extra": extra}


def _resenas_amazon(productos, pais, resenas_por_producto):
    tld = PAISES_AMAZON[pais]
    paginas = max(1, min(MAX_PAGINAS_AMAZON, math.ceil(resenas_por_producto / RESENAS_POR_PAGINA_AMAZON)))
    return [{"entrada": {"asin": p["fuente_id"], "domainCode": tld, "maxPages": paginas, "sortBy": "recent"},
             "max_items": resenas_por_producto, "etiqueta": p["fuente_id"]} for p in productos]


def _resena_amazon(item):
    partes = [_texto(item.get("title"), 300), _texto(item.get("text"), 2000)]
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": ". ".join(x for x in partes if x),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _primero(item, "date"), "url": None,
            "producto": _texto(_primero(item, "asin"), 120) or None}


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


# ----------------------------------------------------------- registro ---

PLATAFORMAS = {
    "amazon": {
        "nombre": "Amazon", "paises": PAISES_AMAZON,
        "busqueda": {"actor": "junglee~amazon-crawler", "nombre": N_("Búsqueda en Amazon"), "usd_por_resultado": 0.003,
                     "armar_entradas": _busqueda_amazon, "leer_producto": _producto_amazon},
        "resenas": {"actor": "axesso_data~amazon-reviews-scraper", "nombre": N_("Reseñas de Amazon"), "usd_por_resultado": 0.0009,
                    "por_producto": True, "armar_entradas": _resenas_amazon, "leer_resena": _resena_amazon},
    },
    "meli": {
        "nombre": "Mercado Libre", "paises": PAISES_MELI,
        "busqueda": {"actor": "karamelo~mercado-libre-listings-scraper", "nombre": N_("Búsqueda en Mercado Libre"), "usd_por_resultado": 0.002,
                     "armar_entradas": _busqueda_meli, "leer_producto": _producto_meli},
        "resenas": {"actor": "karamelo~mercadolibre-review-scraper", "nombre": N_("Opiniones de Mercado Libre"), "usd_por_resultado": 0.0007,
                    "por_producto": False, "armar_entradas": _resenas_meli, "leer_resena": _resena_meli},
    },
    "tiktok_shop": {
        "nombre": "TikTok Shop", "paises": TODOS,
        "busqueda": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": N_("Búsqueda en TikTok Shop"), "usd_por_resultado": 0.0045,
                     "armar_entradas": _busqueda_tiktok_shop, "leer_producto": _producto_tiktok_shop},
        "resenas": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": N_("Reseñas de TikTok Shop"), "usd_por_resultado": 0.0045,
                    "por_producto": False, "armar_entradas": _resenas_tiktok_shop, "leer_resena": _resena_tiktok_shop},
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


def actor_busqueda(clave):
    a = _plataforma(clave)["busqueda"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"]}


def actor_resenas(clave):
    a = _plataforma(clave)["resenas"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"]}


def estimar_busqueda(clave, n_consultas, productos_por_consulta):
    return usd(int(n_consultas) * int(productos_por_consulta), _plataforma(clave)["busqueda"]["usd_por_resultado"])


def estimar_resenas(clave, n_productos, resenas_por_producto):
    return usd(int(n_productos) * int(resenas_por_producto), _plataforma(clave)["resenas"]["usd_por_resultado"])


def _con_tope(entradas, precio):
    return [{**e, "max_usd": usd(e["max_items"], precio)} for e in entradas]


def entradas_busqueda(clave, consultas, pais, productos_por_consulta):
    """Lista de corridas: `{"entrada", "max_items", "max_usd", "etiqueta"}`."""
    p = _plataforma(clave)
    consultas = [c.strip() for c in (consultas or []) if (c or "").strip()]
    if not consultas:
        raise ErrorFuente(gettext("%(plataforma)s: no hay consultas para buscar.", plataforma=p["nombre"]))
    if not cubre(clave, pais):
        raise ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=p["nombre"], pais=pais))
    return _con_tope(p["busqueda"]["armar_entradas"](consultas, (pais or "").upper(), max(1, int(productos_por_consulta))),
                     p["busqueda"]["usd_por_resultado"])


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
    if not p["resenas"]["por_producto"]:
        # Estas tiendas piden las reseñas por link: un producto sin link (o con uno
        # que no es http(s)) se salta; solo se para si ninguno lo tiene.
        productos = [x for x in productos if x.get("url")]
        if not productos:
            raise ErrorFuente(gettext("%(plataforma)s: un producto elegido no tiene link.", plataforma=p["nombre"]))
    if not cubre(clave, pais):
        raise ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=p["nombre"], pais=pais))
    return _con_tope(p["resenas"]["armar_entradas"](productos, (pais or "").upper(), max(1, int(resenas_por_producto))),
                     p["resenas"]["usd_por_resultado"])


def leer_resena(clave, item):
    """`{fuente_id, texto, puntuacion, fecha, url, producto}` o None sin id o sin
    texto. `producto` es el id del producto en la plataforma (para el título y
    el link); el autor nunca se lee."""
    d = _plataforma(clave)["resenas"]["leer_resena"](item if isinstance(item, dict) else {})
    return d if d["fuente_id"] and d["texto"] else None
