"""
Un producto a partir de la URL de su página (sin API, sin credenciales).

`leer(url)` descarga el HTML (UA de navegador, timeout 20 s, tope 3 MB) y
saca el producto en este orden de confianza:
  1. JSON-LD `Product` (`<script type="application/ld+json">`, tolerando
     `@graph`, listas de bloques y `@type` como lista),
  2. Open Graph (`og:title`, `og:description`, `og:image`×N,
     `product:price:amount`, `product:price:currency`),
  3. `<title>` a secas.
`extra["metodo"]` dice cuál ganó. Solo regex + `html.unescape` + `json`:
sin dependencias nuevas. Cualquier problema sale como `ErrorConector` con el
código HTTP, nunca con el HTML de la página.

Antes de pedir cualquier URL (la original o una redirección) se valida con
`host_permitido`: resuelve el host por DNS y rechaza direcciones internas
(loopback, RFC1918, link-local, multicast, reservadas, `0.0.0.0`), además de
`localhost`, `*.local`, `*.internal` y `169.254.169.254` — para que este
conector no sirva de oráculo hacia metadata de nube o servicios internos
cuando la URL la escribe un usuario. Las redirecciones se siguen a mano
(`allow_redirects=False`, máximo 3 saltos) re-validando el host en cada una.
"""
import hashlib
import html
import ipaddress
import json
import re
import socket

import requests
from urllib.parse import urljoin, urlparse

from .base import ErrorConector, normalizar_producto

MAX_BYTES = 3 * 1024 * 1024
TIMEOUT = 20
MAX_REDIRECCIONES = 3
_CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "es,en",
}
_CODIGOS_REDIRECCION = (301, 302, 303, 307, 308)
_HOSTS_PROHIBIDOS = {"localhost", "169.254.169.254"}

_RE_JSONLD = re.compile(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                        re.IGNORECASE | re.DOTALL)
_RE_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_RE_ATRIBUTO = re.compile(r"\b(property|name|content)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))",
                          re.IGNORECASE)
_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_ETIQUETAS = re.compile(r"<[^>]+>")
_RE_ESPACIOS = re.compile(r"\s+")


# --- SSRF: solo hosts públicos -------------------------------------------------

def host_permitido(url):
    """True si `url` es http(s), tiene host, y ese host no resuelve (por DNS)
    a ninguna dirección loopback/privada/link-local/multicast/reservada —
    protección contra SSRF hacia metadata de nube o servicios internos.
    Lanza `ErrorConector` si el DNS no resuelve el dominio en absoluto."""
    try:
        partes = urlparse(url)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https"):
        return False
    host = partes.hostname
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host in _HOSTS_PROHIBIDOS or host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        direcciones = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ErrorConector("No se pudo resolver el dominio.")
    for direccion in direcciones:
        ip_bruta = direccion[4][0].split("%")[0]  # sin scope id de IPv6
        try:
            ip = ipaddress.ip_address(ip_bruta)
        except ValueError:
            return False
        if (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return True


# --- descarga -----------------------------------------------------------------

def _descargar(url):
    if not host_permitido(url):
        raise ErrorConector("Esa URL no está permitida (apunta a una red interna o local).")
    redirecciones = 0
    while True:
        try:
            respuesta = requests.get(url, headers=_CABECERAS, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.RequestException as e:
            raise ErrorConector(f"No se pudo abrir la URL ({type(e).__name__}). Revisa que sea pública y esté bien escrita.")
        if respuesta.status_code in _CODIGOS_REDIRECCION:
            cerrar = getattr(respuesta, "close", None)
            if cerrar:
                cerrar()
            if redirecciones >= MAX_REDIRECCIONES:
                raise ErrorConector("La página redirige demasiadas veces.")
            ubicacion = respuesta.headers.get("Location")
            if not ubicacion:
                raise ErrorConector("La página redirigió sin indicar destino.")
            redirecciones += 1
            url = urljoin(url, ubicacion)
            if not host_permitido(url):
                raise ErrorConector("Esa URL no está permitida (apunta a una red interna o local).")
            continue
        break
    try:
        if respuesta.status_code >= 400:
            raise ErrorConector(f"La página respondió con error HTTP {respuesta.status_code}.")
        trozos, total = [], 0
        for trozo in respuesta.iter_content(chunk_size=65536):
            if not trozo:
                continue
            total += len(trozo)
            if total > MAX_BYTES:
                raise ErrorConector("La página pesa más de 3 MB; pega la URL de la página del producto, no de la tienda entera.")
            trozos.append(trozo)
    except requests.RequestException as e:
        raise ErrorConector(f"Se cortó la descarga de la página ({type(e).__name__}).")
    finally:
        cerrar = getattr(respuesta, "close", None)
        if cerrar:
            cerrar()
    datos = b"".join(trozos)
    codificacion = getattr(respuesta, "encoding", None) or "utf-8"
    try:
        return datos.decode(codificacion, errors="replace")
    except LookupError:
        return datos.decode("utf-8", errors="replace")


# --- limpieza de texto --------------------------------------------------------

def _limpiar(texto):
    """Quita etiquetas, desescapa entidades y colapsa espacios."""
    if texto is None:
        return ""
    texto = html.unescape(_RE_ETIQUETAS.sub(" ", str(texto)))
    texto = html.unescape(texto)  # "&amp;quot;" doblemente escapado
    return _RE_ESPACIOS.sub(" ", texto).strip()


def _urls_imagen(valor):
    """str | list | ImageObject | list mixta -> list[str] (sin deduplicar;
    normalizar_producto lo hace)."""
    if not valor:
        return []
    if isinstance(valor, str):
        return [valor.strip()]
    if isinstance(valor, dict):
        return _urls_imagen(valor.get("url") or valor.get("contentUrl"))
    if isinstance(valor, list):
        salida = []
        for v in valor:
            salida.extend(_urls_imagen(v))
        return salida
    return []


# --- JSON-LD ------------------------------------------------------------------

def _es_producto(nodo):
    tipo = nodo.get("@type") if isinstance(nodo, dict) else None
    if isinstance(tipo, list):
        return any(str(t).lower() == "product" for t in tipo)
    return isinstance(tipo, str) and tipo.lower() == "product"


def _nodos(bloque):
    """Recorre un bloque JSON-LD (dict, lista, @graph anidado) y devuelve
    todos los dicts con @type."""
    if isinstance(bloque, list):
        for b in bloque:
            yield from _nodos(b)
    elif isinstance(bloque, dict):
        yield bloque
        for clave in ("@graph", "mainEntity", "itemListElement"):
            if clave in bloque:
                yield from _nodos(bloque[clave])


def _producto_jsonld(texto_html):
    for bruto in _RE_JSONLD.findall(texto_html):
        bruto = bruto.strip()
        if not bruto:
            continue
        try:
            bloque = json.loads(bruto, strict=False)
        except ValueError:
            continue
        for nodo in _nodos(bloque):
            if _es_producto(nodo) and _limpiar(nodo.get("name")):
                return nodo
    return None


def _oferta(nodo):
    ofertas = nodo.get("offers")
    if isinstance(ofertas, list):
        ofertas = ofertas[0] if ofertas else None
    if not isinstance(ofertas, dict):
        return {}
    # AggregateOffer trae lowPrice en vez de price
    return {
        "precio": ofertas.get("price", ofertas.get("lowPrice")),
        "moneda": ofertas.get("priceCurrency"),
        "url": ofertas.get("url"),
    }


def _desde_jsonld(nodo):
    oferta = _oferta(nodo)
    extra = {"metodo": "jsonld"}
    sku = _limpiar(nodo.get("sku") or nodo.get("mpn") or "")
    if sku:
        extra["sku"] = sku
    marca = nodo.get("brand")
    if isinstance(marca, dict):
        marca = marca.get("name")
    if isinstance(marca, str) and marca.strip():
        extra["marca"] = _limpiar(marca)
    categoria = nodo.get("category")
    return {
        "nombre": _limpiar(nodo.get("name")),
        "descripcion": _limpiar(nodo.get("description")),
        "precio": oferta.get("precio"),
        "moneda": oferta.get("moneda"),
        "fotos": [_limpiar(u) for u in _urls_imagen(nodo.get("image"))],
        "categoria": _limpiar(categoria) if isinstance(categoria, str) else None,
        "extra": extra,
    }


# --- Open Graph / title ---------------------------------------------------------

def _metas(texto_html):
    """[(propiedad, contenido)] de cada <meta property|name=... content=...>."""
    salida = []
    for etiqueta in _RE_META.findall(texto_html):
        propiedad, contenido = None, None
        for m in _RE_ATRIBUTO.finditer(etiqueta):
            nombre_attr = m.group(1).lower()
            valor = next((g for g in m.groups()[1:] if g is not None), "")
            if nombre_attr in ("property", "name") and propiedad is None:
                propiedad = valor.strip().lower()
            elif nombre_attr == "content":
                contenido = html.unescape(valor)
        if propiedad and contenido is not None:
            salida.append((propiedad, contenido))
    return salida


def _desde_og(texto_html):
    metas = _metas(texto_html)
    primero = {}
    imagenes = []
    for prop, contenido in metas:
        if prop in ("og:image", "og:image:url", "og:image:secure_url"):
            if contenido.strip():
                imagenes.append(contenido.strip())
        elif prop not in primero and contenido.strip():
            primero[prop] = contenido
    titulo = _limpiar(primero.get("og:title") or primero.get("twitter:title"))
    if not titulo:
        return None
    return {
        "nombre": titulo,
        "descripcion": _limpiar(primero.get("og:description") or primero.get("description")),
        "precio": primero.get("product:price:amount") or primero.get("og:price:amount"),
        "moneda": primero.get("product:price:currency") or primero.get("og:price:currency"),
        "fotos": imagenes,
        "extra": {"metodo": "og"},
    }


def _desde_title(texto_html):
    m = _RE_TITLE.search(texto_html)
    titulo = _limpiar(m.group(1)) if m else ""
    if not titulo:
        return None
    return {"nombre": titulo, "extra": {"metodo": "title"}}


# --- entrada ------------------------------------------------------------------

def leer(url):
    """-> dict normalizado (ver `base.CLAVES_PRODUCTO`). ErrorConector si la
    URL no responde, pesa demasiado o no tiene ni siquiera un <title>."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ErrorConector("La URL debe empezar por http:// o https://.")
    texto_html = _descargar(url)

    nodo = _producto_jsonld(texto_html)
    crudo = _desde_jsonld(nodo) if nodo else None
    if not crudo:
        crudo = _desde_og(texto_html)
    if not crudo:
        crudo = _desde_title(texto_html)
    if not crudo:
        raise ErrorConector("No encontré ningún producto en esa página (ni datos estructurados ni título).")

    crudo["fuente_id"] = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    crudo["url_compra"] = url
    return normalizar_producto(crudo)
