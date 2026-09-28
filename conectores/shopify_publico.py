"""
Conector `shopify_publico` (spec 2026-09-28 §6): el catálogo PÚBLICO de una
tienda Shopify, sin llaves. Toda tienda Shopify abierta al público responde
`/meta.json` (nombre, moneda) y `/products.json?limit=250&page=N` (productos
con opciones, variantes, `featured_image` por variante e imágenes con
`variant_ids`), que es exactamente lo que hace falta para un producto con
colores: por cada valor de la opción de color, su foto de estudio y las fotos
ligadas a sus variantes; las imágenes sin variante son fotos generales.

Credenciales: `{"dominio": "www.happyflops.com"}` (se guarda cifrado como
cualquier tienda; no hay secreto). `fuente = "shopify"`: las filas `producto`
son las mismas que dejaría el conector con Admin API (`fuente_id` = id
numérico del producto), así que pasar de uno a otro no duplica nada.

Seguridad: el dominio se valida con `host_permitido` (SSRF) y las
redirecciones se siguen A MANO (máximo 3) validando cada salto; una tienda
`.myshopify.com` que redirige a su dominio real se sigue y `probar()` devuelve
ese dominio para guardarlo. Una tienda con contraseña (HTML en vez de JSON)
sale como ErrorConector con un mensaje claro. Nunca se registran cuerpos.
"""
import collections
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from . import registrar
from ._http import TIMEOUT_PROBAR, error_generico, pedir, sesion
from .base import Conector, ErrorConector, limpiar_html, normalizar_producto, normalizar_variante, parsear_precio, slug
from .url import host_permitido

NOMBRE = "Shopify (sin llaves)"
LIMITE_PAGINA = 250
MAX_PAGINAS = 40
MAX_FOTOS = 6
MAX_FOTOS_GENERALES = 6
ANCHO_FOTO = 1000
MAX_REDIRECCIONES = 3
_CODIGOS_REDIRECCION = (301, 302, 303, 307, 308)
OPCIONES_COLOR = {"colour", "color", "colores", "colors", "pattern", "patterns", "estampado", "estampados",
                  "diseno", "design", "print", "estilo", "style", "acabado", "finish", "modelo"}
OPCIONES_TALLA = {"size", "sizes", "talla", "tallas", "tamano", "tamanos"}
PALABRAS_SERVICIO = ("shipping protection", "package protection", "route protection", "upcart", "insurance",
                     "seguro de envio", "proteccion de envio", "gift card", "tarjeta de regalo", "tarjeta regalo",
                     "donation", "donacion", "propina")
_CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}
_RE_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_MSG_NO_SHOPIFY = ("No encontré un catálogo público de Shopify en %s. ¿Es una tienda Shopify y está "
                   "abierta al público, sin contraseña?")


# --- puras -------------------------------------------------------------------

def _sin_acentos(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").casefold().strip()


def normalizar_dominio(texto):
    """'https://www.HappyFlops.com/es?x' -> 'www.happyflops.com'. ErrorConector
    si no queda un nombre de dominio público (con punto, sin espacios)."""
    t = str(texto or "").strip().lower()
    t = re.sub(r"^[a-z]+://", "", t)
    t = t.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip().rstrip(".")
    if not t or not _RE_HOST.match(t) or t == "localhost":
        raise ErrorConector("Escribe el dominio de tu tienda, por ejemplo mitienda.com o mitienda.myshopify.com.")
    return t


def es_servicio(p):
    """True para lo que no es un producto real (protección de envío, tarjeta de regalo…)."""
    texto = f"{_sin_acentos(p.get('product_type'))} {_sin_acentos(p.get('title'))}"
    return any(palabra in texto for palabra in PALABRAS_SERVICIO)


def _posicion(opcion, indice):
    try:
        return int(opcion.get("position") or (indice + 1))
    except (TypeError, ValueError):
        return indice + 1


def opcion_color(p):
    """(posición 1–3, nombre) de la opción de color del producto, o None si es
    plano. Primero por nombre (OPCIONES_COLOR); si no, la primera opción con
    ≥ 2 valores cuyas variantes tengan fotos destacadas distintas por valor."""
    opciones = [o for o in (p.get("options") or []) if isinstance(o, dict)]
    variantes = [v for v in (p.get("variants") or []) if isinstance(v, dict)]
    for i, o in enumerate(opciones):
        if _sin_acentos(o.get("name")) in OPCIONES_COLOR:
            return _posicion(o, i), o.get("name")
    for i, o in enumerate(opciones):
        if len(o.get("values") or []) < 2:
            continue
        pos = _posicion(o, i)
        por_valor = {}
        for v in variantes:
            valor, fi = v.get(f"option{pos}"), v.get("featured_image")
            if valor and isinstance(fi, dict) and valor not in por_valor:
                por_valor[valor] = fi.get("id")
        if len(set(por_valor.values())) >= 2:
            return pos, o.get("name")
    return None


def foto_url(src):
    """Las fotos del CDN de Shopify se piden a ANCHO_FOTO px (`width=`), que
    baja un PNG de estudio de ~1 MB a ~0,7 MB sin perder la fidelidad que el
    modelo necesita; otras URLs van tal cual."""
    if not src:
        return src
    partes = urlsplit(src)
    if not partes.hostname or not partes.hostname.endswith("cdn.shopify.com"):
        return src
    query = parse_qsl(partes.query, keep_blank_values=True)
    if any(k == "width" for k, _ in query):
        return src
    query.append(("width", str(ANCHO_FOTO)))
    return urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(query), partes.fragment))


def precio_moda(variantes):
    """El precio más repetido entre las variantes disponibles (todas si ninguna
    lo está); empate → el menor. None sin precios."""
    disponibles = [v for v in variantes if v.get("available")] or list(variantes)
    precios = [parsear_precio(v.get("price")) for v in disponibles]
    precios = [x for x in precios if x is not None]
    if not precios:
        return None
    conteo = collections.Counter(precios)
    return sorted(conteo, key=lambda x: (-conteo[x], x))[0]


def _rango(variantes):
    precios = [parsear_precio(v.get("price")) for v in variantes]
    precios = [x for x in precios if x is not None]
    if len(set(precios)) < 2:
        return None
    return {"min": min(precios), "max": max(precios)}


# --- conector ----------------------------------------------------------------

@registrar
class ShopifyPublico(Conector):
    tipo = "shopify_publico"
    fuente = "shopify"
    tiene_pedidos = False
    soporta_utm = False

    def __init__(self, credenciales):
        super().__init__(credenciales)
        self.dominio = normalizar_dominio(self.credenciales.get("dominio"))
        self.omitidos = []

    # --- HTTP ---------------------------------------------------------------

    def _get(self, ruta, params=None, timeout=None, reintentar=True):
        """GET JSON siguiendo redirecciones a mano y validando cada host.
        Devuelve (json, host_final). ErrorConector con el mensaje de «no es
        Shopify» ante HTML/4xx; error_generico ante 5xx."""
        url = f"https://{self.dominio}{ruta}"
        nombre = f"la tienda {self.dominio}"
        s = sesion()
        kw = {"headers": _CABECERAS, "allow_redirects": False}
        if params:
            kw["params"] = params
        if timeout:
            kw["timeout"] = timeout
        saltos = 0
        while True:
            if not host_permitido(url):
                raise ErrorConector("Ese dominio no está permitido (apunta a una red interna o local).")
            r = pedir(s, "GET", url, nombre=nombre, reintentar=reintentar, **kw)
            if r.status_code in _CODIGOS_REDIRECCION:
                ubicacion = (getattr(r, "headers", None) or {}).get("Location")
                if not ubicacion or saltos >= MAX_REDIRECCIONES:
                    raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
                saltos += 1
                url = urljoin(url, ubicacion)
                kw.pop("params", None)       # la Location ya trae la query
                continue
            break
        if 400 <= r.status_code < 500:
            raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        if r.status_code >= 500:
            raise error_generico(r, nombre)
        try:
            datos = r.json()
        except ValueError:
            raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        return datos, (urlsplit(url).hostname or self.dominio)

    def _meta(self, **kw_http):
        try:
            datos, host = self._get("/meta.json", **kw_http)
        except ErrorConector:
            return {}, None
        return (datos if isinstance(datos, dict) else {}), host

    # --- API pública ---------------------------------------------------------

    def probar(self):
        meta, host = self._meta(timeout=TIMEOUT_PROBAR, reintentar=False)
        if not meta:
            datos, host = self._get("/products.json", params={"limit": 1}, timeout=TIMEOUT_PROBAR, reintentar=False)
            if not isinstance(datos, dict) or not isinstance(datos.get("products"), list):
                raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        nombre = str(meta.get("name") or "").strip()
        moneda = str(meta.get("currency") or "").upper()
        n = meta.get("published_products_count")
        partes = ["Tienda pública leída"]
        if n is not None:
            partes.append(f"{n} productos")
        if moneda:
            partes.append(f"moneda {moneda}")
        return {"ok": True, "nombre": nombre, "detalle": ": ".join([partes[0], ", ".join(partes[1:])]) + "." if len(partes) > 1 else partes[0] + ".",
                "dominio": host or self.dominio}

    def listar_productos(self):
        meta, _host = self._meta()
        moneda = str(meta.get("currency") or "").upper() or None
        productos, pagina = [], 1
        self.omitidos = []
        while pagina <= MAX_PAGINAS:
            datos, _host = self._get("/products.json", params={"limit": LIMITE_PAGINA, "page": pagina})
            lote = datos.get("products") if isinstance(datos, dict) else None
            if not isinstance(lote, list):
                raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
            for p in lote:
                if not isinstance(p, dict) or not p.get("published_at"):
                    continue
                if es_servicio(p):
                    self.omitidos.append(str(p.get("title") or ""))
                    continue
                productos.append(self._producto(p, moneda))
            if len(lote) < LIMITE_PAGINA:
                break
            pagina += 1
        return productos

    # --- armado de un producto ------------------------------------------------

    def _producto(self, p, moneda):
        handle = p.get("handle") or slug(p.get("title"))
        url_producto = f"https://{self.dominio}/products/{handle}"
        variantes = [v for v in (p.get("variants") or []) if isinstance(v, dict)]
        imagenes = [i for i in (p.get("images") or []) if isinstance(i, dict) and i.get("src")]
        opcion = opcion_color(p)
        colores = []
        if opcion:
            pos = opcion[0]
            grupos = collections.OrderedDict()
            for v in variantes:
                valor = str(v.get(f"option{pos}") or "").strip()
                if valor:
                    grupos.setdefault(valor, []).append(v)
            for valor, vs in grupos.items():
                ids = {v.get("id") for v in vs}
                fotos = []
                destacada = next((v["featured_image"] for v in vs
                                  if isinstance(v.get("featured_image"), dict) and v["featured_image"].get("src")), None)
                if destacada:
                    fotos.append(destacada["src"])
                for i in imagenes:
                    if ids & set(i.get("variant_ids") or []):
                        fotos.append(i["src"])
                colores.append(normalizar_variante({
                    "id": valor, "nombre": valor, "fuente_id": vs[0].get("id"),
                    "url_compra": f"{url_producto}?variant={vs[0].get('id')}",
                    "fotos": [foto_url(f) for f in fotos][:MAX_FOTOS],
                    "disponible": any(v.get("available") for v in vs)}))
            fotos_producto = [foto_url(i["src"]) for i in imagenes if not i.get("variant_ids")][:MAX_FOTOS_GENERALES]
        else:
            fotos_producto = [foto_url(i["src"]) for i in imagenes][:MAX_FOTOS]
        tallas = []
        for i, o in enumerate(o for o in (p.get("options") or []) if isinstance(o, dict)):
            if _sin_acentos(o.get("name")) in OPCIONES_TALLA:
                tallas = [str(x) for x in (o.get("values") or [])]
                break
        extra = {"handle": handle, "tags": list(p.get("tags") or []) if isinstance(p.get("tags"), list) else [],
                 "tallas": tallas, "variantes": colores, "publico": True}
        rango = _rango(variantes)
        if rango:
            extra["precios"] = rango
        return normalizar_producto({
            "fuente_id": str(p.get("id") or handle),
            "nombre": p.get("title"),
            "descripcion": limpiar_html(p.get("body_html")),
            "precio": precio_moda(variantes),
            "moneda": moneda,
            "url_compra": url_producto,
            "fotos": fotos_producto,
            "categoria": p.get("product_type") or None,
            "url_imagen_principal": foto_url(imagenes[0]["src"]) if imagenes else None,
            "extra": extra,
        })
