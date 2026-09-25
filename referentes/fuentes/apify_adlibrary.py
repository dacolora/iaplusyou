"""
Conector de barrido Apify para la biblioteca de referentes (spec bloque 5,
2026-09-23 §2.3, §4.2): la Ad Library de Meta vía el actor oficial de Apify
(apify/facebook-ads-scraper, ver `apify_actores.py`). Contrato común con las
demás fuentes (`referentes/fuentes/base.py`): estimar, probar, traer -- mismo
patrón de módulo que `atria.py`, pero SIN paginación por cursor: una corrida
de Apify entrega TODO de una vez (resultsLimit topea el tamaño desde el
lado de Apify), así que `traer()` siempre hace un solo yield y termina --
`cursor` se acepta por el contrato común pero se ignora.

A diferencia de Atria (solo consume el cupo del plan, sin costo propio por
llamada), Apify SÍ cobra por resultado real: `traer()` manda el costo real
bajo `meta["costo_real"]` en su único yield (spec bloque 5 §4.2;
`tareas/referentes.py::_fase_trayendo` lo registra en `gastos` con el tipo
"recoleccion", el mismo que usa `nicho` para sus propias corridas de Apify).

Ventaja sobre Atria (que solo cubre la UE, spec §2.2): `country=` en la URL
de la Ad Library acepta cualquier ISO-2 real -- CO, MX, AR, lo que sea --
así que esta fuente sí sirve para anuncios de Latinoamérica.
"""
import os
from urllib.parse import quote

import providers.apify as apify_api
from nicho.fuentes.base import ErrorFuente as _ErrorApify
from referentes.fuentes import apify_actores
from referentes.fuentes.base import ErrorFuente


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente("Apify no está configurado (falta APIFY_TOKEN).")
    return t


def _sesion():
    import requests
    return requests.Session()


def probar():
    resultado = apify_api.probar_token(_sesion(), _token())
    if not resultado["ok"]:
        raise ErrorFuente(resultado["detalle"])
    return None


def estimar(consulta, tope):
    return apify_actores.estimar(tope)


def _url_ad_library(consulta):
    """Arma la URL de la Ad Library de Meta que el actor de Apify recorre
    (spec §4.2): país, idioma y formato son filtros de META, no de Apify --
    van adentro de esta URL, igual que en un link copiado del navegador."""
    pais = (consulta.get("pais") or "ALL").strip().upper()[:5] or "ALL"
    formato = {"imagen": "image", "video": "video"}.get(consulta.get("formato") or "imagen", "image")
    activo = "active" if consulta.get("solo_activos", True) else "all"
    if consulta.get("modo") == "marca":
        return (f"https://www.facebook.com/ads/library/?active_status={activo}&ad_type=all"
                f"&country={pais}&media_type={formato}&search_type=page"
                f"&view_all_page_id={consulta['pagina_id']}")
    idioma = (consulta.get("idioma") or "es").strip()[:5] or "es"
    palabra = consulta.get("palabra") or ""
    return (f"https://www.facebook.com/ads/library/?active_status={activo}&ad_type=all"
            f"&content_languages[0]={idioma}&country={pais}&media_type={formato}"
            f"&q={quote(palabra)}&search_type=keyword_unordered")


def _texto_snapshot(snap):
    """El texto real vive en snapshot.body.text (pieza única) o en
    snapshot.cards[0] (carrusel/DCO) -- nunca en los dos a la vez."""
    cuerpo = snap.get("body")
    if isinstance(cuerpo, dict) and (cuerpo.get("text") or "").strip():
        return "", cuerpo["text"]
    cartas = snap.get("cards") or []
    if cartas:
        c = cartas[0] or {}
        return (c.get("title") or ""), (c.get("body") or "")
    return "", ""


def _imagen_snapshot(snap):
    imagenes = snap.get("images") or []
    if imagenes:
        return imagenes[0].get("originalImageUrl") or imagenes[0].get("resizedImageUrl")
    for c in (snap.get("cards") or []):
        if c.get("originalImageUrl"):
            return c["originalImageUrl"]
        if c.get("videoPreviewImageUrl"):
            return c["videoPreviewImageUrl"]
    videos = snap.get("videos") or []
    if videos:
        return videos[0].get("videoPreviewImageUrl")
    return None


def _normalizar(item):
    anuncio_id = str(item.get("adArchiveId") or item.get("adArchiveID") or "") or None
    if not anuncio_id:
        return None
    snap = item.get("snapshot") or {}
    imagen_origen = _imagen_snapshot(snap)
    if not imagen_origen:
        return None
    titular, cuerpo = _texto_snapshot(snap)
    pagina_id = str(item.get("pageId") or item.get("pageID") or "") or None
    fecha = (item.get("startDateFormatted") or "")[:10] or None
    return {
        "anuncio_id": anuncio_id,
        "pagina_id": pagina_id,
        "marca": snap.get("pageName") or "",
        "titular": titular,
        "cuerpo": cuerpo,
        "idioma": None,
        "pais": None,
        "tipo": "video" if (snap.get("videos") or []) else "imagen",
        "imagen_origen": imagen_origen,
        "dias": None,
        "variantes": item.get("collationCount"),
        "primera_vez": fecha,
        "ultima_vez": fecha,
        "activo": bool(item.get("isActive")),
        "url_anuncio": f"https://www.facebook.com/ads/library/?id={anuncio_id}",
        "url_marca": f"https://www.facebook.com/ads/library/?view_all_page_id={pagina_id or ''}",
        "etiquetas_fuente": {},
        "extra": {},
    }


def traer(consulta, tope, avanzar, cursor=None):
    """Una sola corrida de Apify entrega hasta `tope` anuncios de una vez
    (resultsLimit los topea del lado de Apify) -- no hay cursor que
    retomar, así que esta fuente siempre hace un único yield y termina.

    `providers.apify` reutiliza `nicho/fuentes/_http.py` y por eso levanta
    `nicho.fuentes.base.ErrorFuente` (importado acá como `_ErrorApify`), NO
    el `ErrorFuente` de este paquete -- son dos clases distintas aunque
    tengan la misma forma. `_fase_trayendo` (tareas/referentes.py) solo
    atrapa `referentes.fuentes.base.ErrorFuente`: sin traducir el tipo acá,
    un fallo de Apify se colaría hasta el `except Exception` genérico de
    `ejecutar_barrer` y el barrido perdería el manejo de entrega parcial que
    sí tiene Atria (spec bloque 5; encontrado en el escaneo previo al
    bloque, antes de tocar código)."""
    token = _token()
    sesion = _sesion()
    tope = max(1, int(tope or 0))
    url = _url_ad_library(consulta)
    entrada = {"startUrls": [{"url": url}], "resultsLimit": tope}
    estimado = apify_actores.estimar(tope)
    avanzar(etapa="Buscando en Apify", detalle="apify/facebook-ads-scraper")
    try:
        run_id, dataset_id, estado = apify_api.arrancar(
            sesion, token, apify_actores.ACTOR, entrada, tope, estimado["usd_fuente"])
        estado = apify_api.sondear(sesion, token, run_id, estado, "Leyendo anuncios", avanzar)
        crudos, motivo = apify_api.leer_dataset(sesion, token, dataset_id, tope)
    except _ErrorApify as e:
        raise ErrorFuente(e.usuario) from e
    if crudos is None:
        raise ErrorFuente(f"Apify no entregó los resultados ({motivo}); corrida {run_id}, "
                          f"dataset {dataset_id}: revísalos en console.apify.com.")
    if not crudos:
        if estado != "SUCCEEDED":
            raise ErrorFuente(f"Apify {apify_api.frase_estado(estado)} sin resultados (corrida {run_id}); "
                              "revísala en console.apify.com.")
        avanzar(etapa="Buscando en Apify", detalle="0 anuncios")
        yield [], None, {}
        return
    costo_real = round(len(crudos) * apify_actores.USD_POR_RESULTADO, 4)
    pagina = [_normalizar(it) for it in crudos if isinstance(it, dict)]
    avanzar(etapa="Buscando en Apify", detalle=f"{len(crudos)} anuncios")
    yield pagina, None, {"costo_real": costo_real}
