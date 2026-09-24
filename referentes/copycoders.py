"""
Importación del swipe file de copycoders (spec 2026-09-23 §2.1 y §7). La
página es un solo HTML con `const DATA=[...]` adentro; acá se baja, se
extrae ese array y cada fila se normaliza al anuncio que entiende
`referentes.datos.guardar_referente`. La traducción de firmas y la
descripción de familias van por Claude (`_llamar` es la costura de pruebas).
"""
import json
import re
from urllib.parse import urljoin

import requests

from referentes import datos

URL_SWIPE = "https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/"
MAX_HTML = 20 * 1024 * 1024
CLAVES = ("img", "brand", "headline", "aw", "stage", "family", "days", "variants", "lib", "blib", "door", "sig", "sweep")
DOLOR_ESPECIAL = {"none-offer": "ninguno-oferta", "none-brand": "ninguno-marca"}
_RE_ID = re.compile(r"[?&]id=(\d+)")
_RE_PAGINA = re.compile(r"view_all_page_id=(\d+)")


class FormatoInvalido(RuntimeError):
    """La página no trae el dataset como lo conocemos; no se toca nada."""


def descargar_html(url):
    r = requests.get(url, timeout=60, headers={"User-Agent": "CreatvMachine/1.0"}, stream=True)
    r.raise_for_status()
    trozos, total = [], 0
    for parte in r.iter_content(65536):
        total += len(parte)
        if total > MAX_HTML:
            raise FormatoInvalido("La página pesa más de 20 MB; no parece el swipe file.")
        trozos.append(parte)
    return b"".join(trozos).decode("utf-8", errors="replace")


def extraer_datos(html):
    marca = "const DATA="
    i = html.find(marca)
    if i < 0:
        raise FormatoInvalido("No encontré `const DATA=` en la página.")
    inicio = html.find("[", i)
    if inicio < 0:
        raise FormatoInvalido("El dataset no empieza con un arreglo.")
    profundidad, fin = 0, -1
    for j in range(inicio, len(html)):
        c = html[j]
        if c == "[":
            profundidad += 1
        elif c == "]":
            profundidad -= 1
            if profundidad == 0:
                fin = j
                break
    if fin < 0:
        raise FormatoInvalido("El arreglo del dataset no cierra.")
    try:
        filas = json.loads(html[inicio:fin + 1])
    except ValueError as e:
        raise FormatoInvalido(f"El dataset no es JSON válido: {e}") from e
    if not isinstance(filas, list) or not filas or not isinstance(filas[0], dict):
        raise FormatoInvalido("El dataset está vacío o no es una lista de anuncios.")
    faltan = [k for k in CLAVES if k not in filas[0]]
    if faltan:
        raise FormatoInvalido(f"Al dataset le faltan claves: {', '.join(faltan)}")
    return filas


def _dolor(v):
    v = datos._texto(v, 120)
    if not v:
        return None
    return DOLOR_ESPECIAL.get(v, v)


def normalizar(fila, base_url):
    m = _RE_ID.search(fila.get("lib") or "")
    img = datos._texto(fila.get("img"))
    if not m or not img:
        return None
    pagina = _RE_PAGINA.search(fila.get("blib") or "")
    firma = datos._texto(fila.get("sig")) or None
    etapa = fila.get("stage") if fila.get("stage") in datos.ETAPAS else None
    consciencia = fila.get("aw") if fila.get("aw") in datos.CONSCIENCIAS else None
    return {
        "anuncio_id": m.group(1), "pagina_id": pagina.group(1) if pagina else None, "fuente": "copycoders",
        "marca": datos._texto(fila.get("brand"), 160), "url_anuncio": datos._texto(fila.get("lib")),
        "url_marca": datos._texto(fila.get("blib")) or None, "titular": datos._texto(fila.get("headline")),
        "cuerpo": "", "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": urljoin(base_url, img),
        "dias": datos._entero(fila.get("days")), "variantes": datos._entero(fila.get("variants")),
        "primera_vez": None, "ultima_vez": None, "activo": not bool(fila.get("retired")),
        "etiquetas_fuente": {}, "etapa": etapa, "consciencia": consciencia,
        "familia": datos._texto(fila.get("family"), 120) or None, "dolor": _dolor(fila.get("door")), "firma": firma,
        "clasificacion": "fuente",
        "extra": {"sweep": datos._texto(fila.get("sweep"), 12), "firma_original": firma or "", "traducida": firma is None},
    }
