"""
Actores de Apify permitidos (spec §3.5), mismo patrón que
providers/flowplus_modelos: solo entran actores con precio POR RESULTADO (los
que cobran por cómputo no se pueden estimar antes del clic). Forma de la
entrada/salida verificada 2026-09-20 en la tienda de Apify; precios del plan
FREE de Creatv reverificados el 2026-10-01 contra `GET /v2/acts/<actor>` (los
de antes estaban por debajo de lo real: con `maxTotalChargeUsd` de ese tamaño
Apify cortaba la corrida antes de lo pedido y el gasto registrado quedaba por
debajo del real, el mismo problema que las reseñas de Amazon de la
investigación automática):

  junglee~amazon-reviews-scraper — US$ 6.00 por 1 000 reseñas (antes se creía
    US$ 3.00). Entrada `productUrls` (lista de {url}), `maxReviews`,
    `includeGdprSensitive`. Salida `reviewTitle`, `reviewDescription`,
    `ratingScore`, `reviewedIn` ("Reviewed in the United States on February
    3, 2022"), `reviewUrl` (…/customer-reviews/<id>/), `productAsin`. Apify
    rechaza el POST de la corrida (400 `max-total-charge-usd-below-minimum`)
    si `maxTotalChargeUsd` < US$ 0.50: ese es el techo mínimo de CUALQUIER
    corrida de este actor, aunque se pidan pocas reseñas. Prueba real en
    producción (2026-10-01, run `wpny9jQYLztteag8Z`): en el plan FREE de
    Apify el actor solo lee 1 link y entrega 10 reseñas POR CORRIDA (el aviso
    del run lo dice; Starter sube ese tope a 40) -- con varios links en una
    corrida, solo el primero se lee. Por eso `una_corrida_por_link` (`corridas()`)
    manda UN link por corrida, a 2048 MB (`memoria_mb`) para que quepan 5 a la
    vez dentro del límite de RAM de la cuenta. Actor, precio, techo mínimo,
    memoria y reseñas por corrida NO se escriben aquí: salen del registro de
    la investigación automática (`_junglee()` lee `nicho/fuentes/plataformas.py`),
    así un cambio de plan de Apify se hace en un solo sitio.
  clockworks~tiktok-comments-scraper — US$ 1.25 por 1 000 comentarios (antes
    se creía US$ 0.50). Entrada `postURLs` (lista de urls), `commentsPerPost`,
    `maxRepliesPerComment`. Salida `text`, `diggCount`, `createTimeISO`,
    `cid`, `videoWebUrl`. Sin techo mínimo.

Los dos topes de entrada (`maxReviews`, `commentsPerPost`) son POR LINK, no
por corrida: se reparten con `_por_link` para que 4 links no cobren cuatro
veces el tope aprobado en la puerta.

Si Apify cambia la forma de la entrada, `armar_entrada` de cada actor es el
único sitio que tocar: un 400 de Apify llega al usuario con su mensaje.
El estimado (`estimar()`) es max_resultados × precio, el PEOR CASO REAL que
se le muestra a la persona antes de aprobar -- nunca con el techo mínimo de
un actor (enmienda 2026-10-01: mostrar el mínimo ahí exageraba el costo de
una corrida chica que nunca lo iba a cobrar). El mínimo solo entra al armar
las corridas de verdad (`corridas()`, `max_usd` de cada una) porque Apify
exige que `maxTotalChargeUsd` lo alcance para aceptar el POST
(`nicho.fuentes.apify.FuenteApify.recolectar`); el gasto REAL que se registra
(`tareas.nicho._gasto_recoleccion`) tampoco lo usa nunca — sale de
`usd_por_resultado` × los resultados que realmente llegaron, sin piso.
"""
import math
import re
from datetime import datetime

from flask_babel import gettext

import idiomas
from idiomas import N_
from nicho.fuentes import plataformas
from nicho.fuentes.base import ErrorFuente

MAX_RESULTADOS = 1000
# Cualquier TLD de Amazon, cero o más segmentos antes de /dp/ o /gp/product/, ASIN de 10
# caracteres y luego fin, «/», «?» o «#». Rechaza búsquedas y categorías (amazon.com/s?k=…).
_RE_AMAZON = re.compile(r"^https?://(www\.)?amazon\.[a-z.]+/(?:[^?#]*/)?(?:dp|gp/product)/[A-Z0-9]{10}(?:[/?#]|$)", re.IGNORECASE)
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


def _por_link(links, max_resultados):
    """Reparte el tope aprobado entre los links: el tope de los dos actores es
    por URL de producto/video, así que mandarlo entero multiplicaría el cobro
    por la cantidad de links (y el estimado de la puerta sería mentira)."""
    return max(1, math.ceil(max_resultados / max(1, len(links))))


def _entrada_amazon(links, max_resultados):
    return {"productUrls": [{"url": u} for u in links], "maxReviews": _por_link(links, max_resultados), "includeGdprSensitive": False}


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
    return {"postURLs": list(links), "commentsPerPost": _por_link(links, max_resultados), "maxRepliesPerComment": 0}


def _item_tiktok(item):
    if not (item.get("text") or "").strip():
        return None
    video = item.get("videoWebUrl") or None
    return {"fuente_id": str(item.get("cid") or "") or None, "texto": item["text"], "url": video, "contexto": None,
            "puntuacion": item.get("diggCount"), "fecha": item.get("createTimeISO"), "extra": {"video": video}}


def _junglee():
    """junglee es el mismo actor que usan las reseñas de Amazon de la investigación automática: actor, precio,
    techo mínimo (Apify rechaza la corrida si se manda menos), memoria (5 corridas a la vez en el límite de RAM
    del plan) y reseñas por corrida (el plan FREE: 1 link y 10 reseñas) salen de ESE registro, para que un
    cambio de plan de Apify se haga en un solo sitio."""
    r = plataformas.PLATAFORMAS["amazon"]["resenas"]
    return {"actor": r["actor"], "usd_por_resultado": r["usd_por_resultado"], "tope_minimo_usd": r["tope_minimo_usd"],
            "memoria_mb": r["memoria_mb"], "max_por_link": r["max_resenas_por_producto"]}


ACTORES = {
    "amazon_resenas": {
        **_junglee(), "nombre": N_("Reseñas de Amazon"), "una_corrida_por_link": True,
        "ayuda": N_("Links de producto de Amazon (con /dp/ o /gp/product/), uno por línea."),
        "patron_link": _RE_AMAZON, "armar_entrada": _entrada_amazon, "leer_item": _item_amazon,
    },
    "tiktok_comentarios": {
        "actor": "clockworks~tiktok-comments-scraper", "nombre": N_("Comentarios de TikTok"), "usd_por_resultado": 0.00125,
        "ayuda": N_("Links de videos de TikTok, uno por línea."),
        "patron_link": _RE_TIKTOK, "armar_entrada": _entrada_tiktok, "leer_item": _item_tiktok,
    },
}


def _actor(clave):
    if clave not in ACTORES:
        raise ErrorFuente(gettext("Actor de Apify desconocido: %(clave)s", clave=clave))
    return ACTORES[clave]


def _tope(max_resultados):
    try:
        n = int(max_resultados)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_RESULTADOS, n))


def _centavos(x):
    # round() antes de ceil(): 30 × 0.003 × 100 da 9.000000000000002 en binario y ceil lo subiría a 10.
    return math.ceil(round(x * 100, 6)) / 100


def estimar(clave, max_resultados):
    """Peor caso REAL (resultados × precio, SIN ningún mínimo): lo que se le
    muestra a la persona antes del clic. Hasta el 2026-09-30 esto también le
    sumaba el techo mínimo de junglee (reseñas de Amazon) para que coincidiera
    con lo que se manda a Apify -- exageraba el costo de una corrida chica que
    nunca lo iba a cobrar. Desde el 2026-10-01 el mínimo solo entra al armar
    la corrida de verdad (`corridas()`), nunca acá (ruling 3,
    `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`)."""
    a = _actor(clave)
    n = _tope(max_resultados)
    usd = _centavos(n * a["usd_por_resultado"])
    return {"actor": a["actor"], "max_resultados": n, "usd": usd}


def corridas(clave, links, max_resultados):
    """Lista de corridas `{"entrada", "max_items", "max_usd", "etiqueta"[, "memoria_mb"]}`
    para `providers.apify.correr_lote`. Un actor `una_corrida_por_link` (junglee:
    el plan FREE solo lee 1 link y entrega `max_por_link` reseñas por corrida,
    docstring del módulo) manda UNA corrida POR LINK, con el tope aprobado
    repartido entre ellos (`_por_link`) y recortado al máximo del actor; los
    demás actores (TikTok) siguen con una sola corrida para todos los links,
    como siempre. `max_usd` de cada corrida SÍ lleva el mínimo del actor
    (Apify lo exige para aceptar el POST, `max-total-charge-usd-below-minimum`)
    -- a diferencia de `estimar()`, que muestra el peor caso real sin él."""
    a = _actor(clave)
    links = list(links)
    n = _tope(max_resultados)
    minimo = float(a.get("tope_minimo_usd") or 0)
    if a.get("una_corrida_por_link"):
        por_link = min(_por_link(links, n), a["max_por_link"])
        extra = {"memoria_mb": a["memoria_mb"]} if a.get("memoria_mb") else {}
        return [{"entrada": a["armar_entrada"]([link], por_link), "max_items": por_link,
                 "max_usd": max(_centavos(por_link * a["usd_por_resultado"]), minimo),
                 "etiqueta": link, **extra}
                for link in links]
    return [{"entrada": a["armar_entrada"](links, n), "max_items": n,
             "max_usd": max(estimar(clave, n)["usd"], minimo), "etiqueta": clave}]


def validar_links(clave, links):
    a = _actor(clave)
    limpios = [(l or "").strip() for l in (links or []) if (l or "").strip()]
    if not limpios:
        raise ErrorFuente(gettext("%(actor)s: pega al menos un link.", actor=idiomas.traducir(a["nombre"])))
    malos = [l for l in limpios if not a["patron_link"].match(l)]
    if malos:
        raise ErrorFuente(gettext("%(actor)s: este link no sirve: %(link)s — %(ayuda)s", actor=idiomas.traducir(a["nombre"]),
                                  link=malos[0][:80], ayuda=idiomas.traducir(a["ayuda"])))
    return limpios


def entrada(clave, links, max_resultados):
    return _actor(clave)["armar_entrada"](list(links), _tope(max_resultados))


def leer_item(clave, item):
    return _actor(clave)["leer_item"](item or {})
