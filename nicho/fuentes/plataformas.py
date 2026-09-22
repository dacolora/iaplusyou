"""
Registro de plataformas para investigación de nicho (spec §3).

Una entrada por plataforma con actor names, precios, y funciones puras
para armar entradas de Apify y leer resultados normalizados.
"""
import math
from urllib.parse import quote
from datetime import datetime
from typing import List, Dict, Any, Optional

# Diccionario principal de plataformas
PLATAFORMAS = {
    "amazon": {
        "nombre": "Amazon",
        "paises": {"US": "com", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it",
                   "ES": "es", "NL": "nl", "SE": "se", "CA": "ca", "MX": "com.mx",
                   "BR": "com.br", "AU": "com.au", "IN": "in", "JP": "co.jp", "AE": "ae"},
        "busqueda": {
            "actor": "junglee~amazon-crawler",
            "usd_por_resultado": 0.003,  # $3 per 1000
            "modelo": "ppe"
        },
        "resenas": {
            "actor": "axesso_data~amazon-reviews-scraper",
            "usd_por_resultado": 0.0009,  # $0.90 per 1000
            "modelo": "ppe",
            "por_producto": True
        }
    },
    "meli": {
        "nombre": "Mercado Libre",
        "paises": {"AR": "com.ar", "BR": "com.br", "CL": "cl", "CO": "com.co",
                   "MX": "com.mx", "PE": "com.pe", "UY": "com.uy"},
        "busqueda": {
            "actor": "karamelo~mercado-libre-listings-scraper",
            "usd_por_resultado": 0.002,  # $2 per 1000
            "modelo": "ppe"
        },
        "resenas": {
            "actor": "karamelo~mercadolibre-review-scraper",
            "usd_por_resultado": 0.0007,  # $0.70 per 1000
            "modelo": "ppe",
            "por_producto": False
        }
    },
    "tiktok_shop": {
        "nombre": "TikTok Shop",
        "paises": {"*": None},  # worldwide
        "busqueda": {
            "actor": "unseenuser~tiktok-shop-scraper",
            "usd_por_resultado": 0.0045,  # $4.50 per 1000
            "modelo": "ppe"
        },
        "resenas": {
            "actor": "unseenuser~tiktok-shop-scraper",
            "usd_por_resultado": 0.0045,
            "modelo": "ppe",
            "por_producto": False
        }
    }
}

IDIOMAS = {
    "SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es",
    "PE": "es", "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en",
    "BR": "pt", "DE": "de", "FR": "fr", "IT": "it", "NL": "nl", "JP": "ja", "AE": "en"
}

def disponibles(pais: str) -> list:
    """Plataformas que cubren ese país."""
    resultado = []
    for clave, info in PLATAFORMAS.items():
        if pais in info["paises"] or "*" in info["paises"]:
            resultado.append(clave)
    return resultado

def dominio(clave: str, pais: str) -> str:
    """Dominio de Amazon para un país. MELI y TikTok no lo usan."""
    if clave != "amazon":
        return ""
    return PLATAFORMAS["amazon"]["paises"].get(pais, "com")

def idioma(pais: str) -> str:
    """Idioma de consultas para un país."""
    return IDIOMAS.get(pais, "en")

def estimar_busqueda(clave: str, n_consultas: int, productos_por_consulta: int) -> float:
    """Costo estimado de búsqueda: ceil(round(n × precio × 100, 6)) / 100"""
    if clave not in PLATAFORMAS:
        return 0.0
    plat = PLATAFORMAS[clave]
    n_resultados = n_consultas * productos_por_consulta
    usd_por_resultado = plat["busqueda"]["usd_por_resultado"]
    return math.ceil(round(n_resultados * usd_por_resultado * 100, 6)) / 100

def estimar_resenas(clave: str, n_productos: int, resenas_por_producto: int) -> float:
    """Costo estimado de reseñas."""
    if clave not in PLATAFORMAS:
        return 0.0
    plat = PLATAFORMAS[clave]
    if plat["resenas"].get("por_producto"):
        # One run per product
        n_resultados = n_productos * resenas_por_producto
    else:
        # One run for all products, max resenas_por_producto per product
        n_resultados = min(n_productos * resenas_por_producto, n_productos * 100)
    usd_por_resultado = plat["resenas"]["usd_por_resultado"]
    return math.ceil(round(n_resultados * usd_por_resultado * 100, 6)) / 100

def entradas_busqueda(clave: str, consultas: list, pais: str, max_items: int) -> list:
    """Armar entradas de Apify para búsqueda. Una por consulta (MELI) o una batch (Amazon)."""
    if clave == "amazon":
        dom = dominio("amazon", pais)
        urls = [f"https://www.amazon.{dom}/s?k={quote(q)}" for q in consultas]
        return [{
            "categoryOrProductUrls": [{"url": url} for url in urls],
            "maxItemsPerStartUrl": max_items,
            "maxSearchPagesPerStartUrl": 2,
            "proxyCountry": pais
        }]
    elif clave == "meli":
        sitio_meli = {
            "AR": "https://listado.mercadolibre.com.ar/",
            "BR": "https://lista.mercadolivre.com.br/",
            "CL": "https://listado.mercadolibre.cl/",
            "CO": "https://listado.mercadolibre.com.co/",
            "MX": "https://listado.mercadolibre.com.mx/",
            "PE": "https://listado.mercadolibre.com.pe/",
            "UY": "https://listado.mercadolibre.com.uy/"
        }
        url_pais = sitio_meli.get(pais, sitio_meli.get("CO"))
        return [
            {
                "keyword": q,
                "country": url_pais,
                "maxPages": 1,
                "extractProductDetails": False
            }
            for q in consultas
        ]
    elif clave == "tiktok_shop":
        return [{
            "mode": "shop_search",
            "searchKeywords": consultas,
            "maxResults": max_items
        }]
    return []

def leer_producto(clave: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalizar un item de búsqueda a {fuente_id, titulo, marca, precio, moneda, estrellas, n_resenas, url, imagen}."""
    if clave == "amazon":
        if not item.get("asin") or not item.get("title"):
            return None
        # Parsear precio como "USD 19.99"
        precio_str = item.get("price") or ""
        precio = float(precio_str.replace("USD ", "").replace(",", "")) if "USD" in precio_str else 0
        return {
            "fuente_id": item["asin"],
            "titulo": item["title"][:300],
            "marca": item.get("brand", "")[:120],
            "precio": precio,
            "moneda": "USD",
            "estrellas": float(item.get("stars") or 0),
            "n_resenas": int(item.get("reviewsCount") or 0),
            "url": item.get("url", ""),
            "imagen": item.get("image", ""),
            "extra": {}
        }
    elif clave == "meli":
        if not item.get("productId") or not item.get("title"):
            return None
        return {
            "fuente_id": item["productId"],
            "titulo": item["title"][:300],
            "marca": item.get("brand", "")[:120],
            "precio": float(item.get("price") or 0),
            "moneda": "ARS" if "argentina" in item.get("currency", "").lower() else "AUD",  # Fake; real: parse item
            "estrellas": float(item.get("rating") or 0),
            "n_resenas": int(item.get("reviews_count") or 0),
            "url": item.get("url", ""),
            "imagen": item.get("image_url", ""),
            "extra": item.get("extra_data", {})
        }
    elif clave == "tiktok_shop":
        if not item.get("productId") or not item.get("title"):
            return None
        return {
            "fuente_id": item["productId"],
            "titulo": item["title"][:300],
            "marca": "",
            "precio": float(item.get("price") or 0),
            "moneda": "USD",  # TikTok Shop reports in local currency; fake for now
            "estrellas": float(item.get("rating") or 0),
            "n_resenas": int(item.get("soldCount") or 0),  # proxy; real reseñas vienen aparte
            "url": item.get("product_url", ""),
            "imagen": item.get("image_url", ""),
            "extra": {"soldCount": item.get("soldCount"), "isSponsored": item.get("isSponsored")}
        }
    return None

def entradas_resenas(clave: str, productos: list, max_por_producto: int) -> list:
    """Armar entradas de Apify para reseñas.
    
    Recibe: productos = [{fuente_id, url, titulo}, ...]
    Retorna: lista de entradas Apify (una por producto si por_producto, una batch si no)
    """
    if clave == "amazon":
        # Una entrada por ASIN
        return [
            {
                "asin": p["fuente_id"],
                "domainCode": "US",  # Debería venir de pais; fake por ahora
                "maxPages": min((max_por_producto // 10) + 1, 10)  # ~10 reseñas por página
            }
            for p in productos
        ]
    elif clave == "meli":
        # Una entrada con todos los URLs
        return [{
            "productUrls": [p["url"] for p in productos],
            "maxReviewsPerProduct": max_por_producto
        }]
    elif clave == "tiktok_shop":
        return [{
            "mode": "product_reviews",
            "productUrls": [p["url"] for p in productos],
            "maxReviewsPerProduct": max_por_producto
        }]
    return []

def leer_resena(clave: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalizar una reseña a {fuente_id, texto, puntuacion, fecha, url, contexto}."""
    if clave == "amazon":
        if not item.get("text") or not item.get("reviewId"):
            return None
        return {
            "fuente_id": item["reviewId"],
            "texto": item["text"],
            "puntuacion": int(item.get("rating") or 0),
            "fecha": item.get("date", ""),
            "url": "",  # Viene en el producto, no en la reseña
            "extra": {"verified": item.get("verified")}
        }
    elif clave == "meli":
        if not item.get("reviewText") or not item.get("reviewId"):
            return None
        return {
            "fuente_id": item["reviewId"],
            "texto": item["reviewText"],
            "puntuacion": int(item.get("reviewRating") or 0),
            "fecha": item.get("reviewDate", ""),
            "url": "",
            "extra": {"productId": item.get("productId")}
        }
    elif clave == "tiktok_shop":
        if not item.get("text") or not item.get("reviewId"):
            return None
        return {
            "fuente_id": item["reviewId"],
            "texto": item["text"],
            "puntuacion": int(item.get("rating") or 0),
            "fecha": item.get("postedAt", ""),
            "url": "",
            "extra": {"verifiedPurchase": item.get("verifiedPurchase")}
        }
    return None
