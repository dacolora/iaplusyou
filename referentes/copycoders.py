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
    """La página no trae el dataset como lo conocemos, o Claude no devolvió
    algo usable; no se toca nada. Cuando Claude ya cobró la llamada, los
    tokens van puestos para que el llamador registre el gasto igual."""
    tokens_entrada = 0
    tokens_salida = 0


def _con_tokens(e, entrada, salida):
    e.tokens_entrada, e.tokens_salida = entrada, salida
    return e


# Tope de salida por llamada: Claude Sonnet 5 piensa antes de responder aunque
# no se le pida, y lo que piensa sale del mismo max_tokens. Medido en
# producción (2026-09-25): ~64 tokens por firma entre texto y pensamiento; con
# 60 por firma, 100 firmas se cortaron en la 92. Por encima de 16 000 el SDK
# exige streaming.
_TOPE_SALIDA = 16000


def _tope(n, por_item):
    return min(_TOPE_SALIDA, 2000 + por_item * n)


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
    decoder = json.JSONDecoder()
    try:
        filas, _ = decoder.raw_decode(html, inicio)
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


def _url_segura(v):
    """Solo http(s): la página de origen no está controlada y esto termina
    directo en un <a href> — sin esto, un `javascript:...?id=` que igual
    matchee _RE_ID quedaría guardado y clicable."""
    v = datos._texto(v)
    return v if v.startswith(("http://", "https://")) else None


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
        "marca": datos._texto(fila.get("brand"), 160), "url_anuncio": _url_segura(fila.get("lib")),
        "url_marca": _url_segura(fila.get("blib")), "titular": datos._texto(fila.get("headline")),
        "cuerpo": "", "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": urljoin(base_url, img),
        "dias": datos._entero(fila.get("days")), "variantes": datos._entero(fila.get("variants")),
        "primera_vez": None, "ultima_vez": None, "activo": not bool(fila.get("retired")),
        "etiquetas_fuente": {}, "etapa": etapa, "consciencia": consciencia,
        "familia": datos._texto(fila.get("family"), 120) or None, "dolor": _dolor(fila.get("door")), "firma": firma,
        "clasificacion": "fuente",
        "extra": {"sweep": datos._texto(fila.get("sweep"), 12), "firma_original": firma or "", "traducida": firma is None},
    }


# ------------------------------------------------------------ Claude ---

PROMPT_TRADUCIR = """Traduce al español neutro (Latinoamérica) estas descripciones de por qué funciona un anuncio estático. Son frases cortas de marketing; conserva el sentido, los nombres de marca y los términos técnicos (GLP-1, ROAS). Máximo 40 palabras cada una.

Responde SOLO con un objeto JSON: la misma clave (el número) y la traducción como valor. Sin texto antes ni después.

{entrada}"""

PROMPT_FAMILIAS = """Eres director creativo de anuncios estáticos. Cada "familia" es un formato de anuncio recurrente. Para cada una escribe UNA línea en español (máximo 25 palabras) que explique en qué consiste el formato, a partir de su nombre y de las descripciones de ejemplo.

Responde SOLO con un objeto JSON: el nombre exacto de la familia como clave y la descripción como valor. Sin texto antes ni después.

{entrada}"""


def _llamar(texto, max_tokens=4000):
    """Una llamada de texto a Claude; devuelve (texto, tokens_entrada, tokens_salida)."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": texto}])
    uso = getattr(resp, "usage", None)
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    salida = int(getattr(uso, "output_tokens", 0) or 0)
    if resp.stop_reason == "refusal":
        raise _con_tokens(FormatoInvalido("Claude rechazó la solicitud."), entrada, salida)
    if resp.stop_reason == "max_tokens":
        raise _con_tokens(FormatoInvalido("La respuesta de Claude se cortó por largo (max_tokens)."), entrada, salida)
    return "".join(b.text for b in resp.content if b.type == "text").strip(), entrada, salida


def _parsear_json(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        data = json.loads(t)
    except ValueError:
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise FormatoInvalido("Claude no devolvió JSON.")
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError:
            raise FormatoInvalido("Claude no devolvió JSON válido.")
    if not isinstance(data, dict):
        raise FormatoInvalido("Claude no devolvió un objeto JSON.")
    return data


def traducir_firmas(pares):
    if not pares:
        return {}, 0, 0
    entrada = json.dumps({str(rid): firma for rid, firma in pares}, ensure_ascii=False, indent=0)
    texto, ent, sal = _llamar(PROMPT_TRADUCIR.format(entrada=entrada), max_tokens=_tope(len(pares), 100))
    try:
        data = _parsear_json(texto)
    except FormatoInvalido as e:
        raise _con_tokens(e, ent, sal)
    validos = {rid for rid, _ in pares}
    resultado = {}
    for k, v in data.items():
        rid = datos._entero(k)
        v = datos._texto(v)
        if rid in validos and v:
            resultado[rid] = " ".join(v.split()[:40])
    return resultado, ent, sal


def describir_familias(familias):
    if not familias:
        return {}, 0, 0
    entrada = json.dumps({nombre: list(ejemplos)[:3] for nombre, ejemplos in familias}, ensure_ascii=False, indent=0)
    texto, ent, sal = _llamar(PROMPT_FAMILIAS.format(entrada=entrada), max_tokens=_tope(len(familias), 120))
    try:
        data = _parsear_json(texto)
    except FormatoInvalido as e:
        raise _con_tokens(e, ent, sal)
    nombres = {nombre for nombre, _ in familias}
    return {k: datos._texto(v) for k, v in data.items() if k in nombres and datos._texto(v)}, ent, sal
