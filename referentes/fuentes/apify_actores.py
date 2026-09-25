"""
El actor de Apify que usa `apify_adlibrary.py` para la biblioteca de
referentes (spec bloque 5, 2026-09-23 §4.2): el oficial de Apify para la Ad
Library de Meta. Verificado EN VIVO 2026-09-25 en apify.com:

  apify/facebook-ads-scraper — Ad Library de Meta y páginas de Facebook.
    Entrada real (input schema de la tienda, NO el resumen del README):
      startUrls: [{"url": "..."}]  -- REQUERIDO. Una URL completa del Ad
        Library o de una página de Facebook, tal cual se pega del navegador
        (con TODOS sus parámetros de búsqueda ya adentro: país, idioma,
        formato, activo/inactivo, view_all_page_id o q=). Apify no tiene
        campos separados para esos filtros -- son de Meta, van en la URL.
      resultsLimit: int -- opcional, tope de resultados POR URL. Vacío =
        "todos los que haya" (nunca se deja vacío acá: siempre se manda el
        tope que la persona aprobó).
    Precio verificado (apify.com/apify/facebook-ads-scraper/pricing,
    2026-09-25): plan Free US$5.80/1000 anuncios -- el más caro de los
    cuatro (Starter US$5.00, Scale US$4.20, Business US$3.40) y por eso el
    que se usa acá como estimado: nunca prometer un precio más barato que
    el que la cuenta real podría pagar.
    Salida real (muestra del README, camelCase -- NUNCA snake_case):
    adArchiveId (duplicado como adArchiveID), pageId (duplicado como
    pageID), startDateFormatted (ISO), collationCount, isActive, y dentro
    de snapshot: pageName, body.text (anuncio de una sola pieza) o
    cards[].title/cards[].body (carrusel/DCO), images[].originalImageUrl.
"""
import math

ACTOR = "apify/facebook-ads-scraper"
USD_POR_RESULTADO = 0.0058          # plan Free, US$5.80/1000 -- ver docstring
MAX_RESULTADOS = 2000                # mismo tope que ya ofrece el formulario de Traer referentes


def _tope(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_RESULTADOS, n))


def estimar(tope):
    n = _tope(tope)
    # round() antes de ceil(): mismo motivo que nicho/fuentes/apify_actores.py
    # (30 × 0.0058 × 100 puede dar un binario como 17.400000000000002).
    usd = math.ceil(round(n * USD_POR_RESULTADO * 100, 6)) / 100
    return {"usd_fuente": usd, "resultados": n,
            "detalle": f"≈ US$ {usd:.2f} en Apify ({n} anuncio{'s' if n != 1 else ''} × US$ {USD_POR_RESULTADO:.4f})"}
