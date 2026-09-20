"""
Actores de Apify permitidos (spec §3.5), mismo patrón que
providers/flowplus_modelos: solo entran actores con precio POR RESULTADO (los
que cobran por cómputo no se pueden estimar antes del clic). Verificado
2026-09-20 en la tienda de Apify:

  junglee~amazon-reviews-scraper — US$ 3.00 por 1 000 reseñas. Entrada
    `productUrls` (lista de {url}), `maxReviews`, `includeGdprSensitive`.
    Salida `reviewTitle`, `reviewDescription`, `ratingScore`, `reviewedIn`
    ("Reviewed in the United States on February 3, 2022"), `reviewUrl`
    (…/customer-reviews/<id>/), `productAsin`.
  clockworks~tiktok-comments-scraper — US$ 0.50 por 1 000 comentarios.
    Entrada `postURLs` (lista de urls), `commentsPerPost`,
    `maxRepliesPerComment`. Salida `text`, `diggCount`, `createTimeISO`,
    `cid`, `videoWebUrl`.

Si Apify cambia la forma de la entrada, `armar_entrada` de cada actor es el
único sitio que tocar: un 400 de Apify llega al usuario con su mensaje.
El estimado es max_resultados × precio (Apify suma cómputo: "aprox.").
"""
import math
import re
from datetime import datetime

from nicho.fuentes.base import ErrorFuente

MAX_RESULTADOS = 1000
_RE_AMAZON = re.compile(r"^https?://(www\.)?amazon\.[a-z.]+/.*(/dp/|gp/product/)[A-Z0-9]{10}", re.IGNORECASE)
_RE_TIKTOK = re.compile(r"^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/", re.IGNORECASE)
_RE_ID_RESENA = re.compile(r"/customer-reviews/([A-Z0-9]+)", re.IGNORECASE)
_RE_FECHA_RESENA = re.compile(r" on ([A-Za-z]+ \d{1,2}, \d{4})$")


def _fecha_resena(texto):
    """'Reviewed in the United States on February 3, 2022' -> '2022-02-03T00:00:00' (solo inglés; otro idioma -> None)."""
    m = _RE_FECHA_RESENA.search((texto or "").strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return None


def _entrada_amazon(links, max_resultados):
    return {"productUrls": [{"url": u} for u in links], "maxReviews": max_resultados, "includeGdprSensitive": False}


def _item_amazon(item):
    texto = ". ".join(x.strip() for x in ((item.get("reviewTitle") or ""), (item.get("reviewDescription") or "")) if x and x.strip())
    if not texto:
        return None
    url = item.get("reviewUrl") or None
    m = _RE_ID_RESENA.search(url or "")
    asin = item.get("productAsin") or None
    return {"fuente_id": m.group(1) if m else None, "texto": texto, "url": url, "contexto": f"ASIN {asin}" if asin else None,
            "puntuacion": item.get("ratingScore"), "fecha": _fecha_resena(item.get("reviewedIn")), "extra": {"asin": asin}}


def _entrada_tiktok(links, max_resultados):
    por_post = max(1, math.ceil(max_resultados / max(1, len(links))))
    return {"postURLs": list(links), "commentsPerPost": por_post, "maxRepliesPerComment": 0}


def _item_tiktok(item):
    if not (item.get("text") or "").strip():
        return None
    video = item.get("videoWebUrl") or None
    return {"fuente_id": str(item.get("cid") or "") or None, "texto": item["text"], "url": video, "contexto": None,
            "puntuacion": item.get("diggCount"), "fecha": item.get("createTimeISO"), "extra": {"video": video}}


ACTORES = {
    "amazon_resenas": {
        "actor": "junglee~amazon-reviews-scraper", "nombre": "Reseñas de Amazon", "usd_por_resultado": 0.003,
        "ayuda": "Links de producto de Amazon (con /dp/ o /gp/product/), uno por línea.",
        "patron_link": _RE_AMAZON, "armar_entrada": _entrada_amazon, "leer_item": _item_amazon,
    },
    "tiktok_comentarios": {
        "actor": "clockworks~tiktok-comments-scraper", "nombre": "Comentarios de TikTok", "usd_por_resultado": 0.0005,
        "ayuda": "Links de videos de TikTok, uno por línea.",
        "patron_link": _RE_TIKTOK, "armar_entrada": _entrada_tiktok, "leer_item": _item_tiktok,
    },
}


def _actor(clave):
    if clave not in ACTORES:
        raise ErrorFuente(f"Actor de Apify desconocido: {clave}")
    return ACTORES[clave]


def _tope(max_resultados):
    try:
        n = int(max_resultados)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_RESULTADOS, n))


def estimar(clave, max_resultados):
    a = _actor(clave)
    n = _tope(max_resultados)
    # round() antes de ceil(): 30 × 0.003 × 100 da 9.000000000000002 en binario y ceil lo subiría a 10.
    return {"actor": a["actor"], "max_resultados": n, "usd": math.ceil(round(n * a["usd_por_resultado"] * 100, 6)) / 100}


def validar_links(clave, links):
    a = _actor(clave)
    limpios = [(l or "").strip() for l in (links or []) if (l or "").strip()]
    if not limpios:
        raise ErrorFuente(f"{a['nombre']}: pega al menos un link.")
    malos = [l for l in limpios if not a["patron_link"].match(l)]
    if malos:
        raise ErrorFuente(f"{a['nombre']}: este link no sirve: {malos[0][:80]} — {a['ayuda']}")
    return limpios


def entrada(clave, links, max_resultados):
    return _actor(clave)["armar_entrada"](list(links), _tope(max_resultados))


def leer_item(clave, item):
    return _actor(clave)["leer_item"](item or {})
