"""
Conector Shopify — Admin GraphQL (`/admin/api/2025-07/graphql.json`, header
`X-Shopify-Access-Token`; scopes `read_products` y `read_orders`).

Credenciales: `dominio` (`tienda.myshopify.com`) y `token` (`shpat_…`).
`listar_productos` pagina `products(first: 25)` por `pageInfo` y pide
`shop { currencyCode }` UNA vez para la moneda; `pedidos_desde` pagina
`orders(first: 10)` filtrando `created_at:>=YYYY-MM-DD` y saca `utm_content`
del query string de `customerJourneySummary.lastVisit.landingPage`.

Coste de las queries: Shopify rechaza una query cuyo coste ESTIMADO (sobre
`first`, no sobre las filas reales) supere 1000 puntos, así que el tamaño
de página es por query (ver `_Q_PRODUCTOS`/`_Q_PEDIDOS`). Y el límite de
ritmo llega como HTTP 200 con `errors[].extensions.code == "THROTTLED"`
(no como 429): `_graphql` espera lo que falte para recuperar el coste
(`extensions.cost.throttleStatus`, tope 5 s) y reintenta UNA vez.
Todo error sale como `ErrorConector` con el código HTTP o el mensaje corto
de GraphQL — nunca el token ni el cuerpo completo.
"""
import re
import time
from urllib.parse import parse_qs, urlparse

from . import registrar
from ._http import error_generico, json_de, pedir, sesion
from .base import Conector, ErrorConector, limpiar_html, normalizar_pedido, normalizar_producto

VERSION_API = "2025-07"
# Tamaño de página POR query, acotado por el coste (ver cálculo junto a cada query).
PAGINA_PRODUCTOS = 25
PAGINA_PEDIDOS = 10
MAX_ESPERA_THROTTLED = 5.0
ESPERA_THROTTLED_DEFECTO = 2.0
NOMBRE = "Shopify"
_MSG_THROTTLED = "Shopify limitó las llamadas; reintenta en un minuto."
_MSG_CREDENCIALES = ("Shopify rechazó las credenciales: token inválido o sin permisos "
                     "read_products/read_orders.")

_RE_GID = re.compile(r"(\d+)(?:\?.*)?$")

_Q_SHOP = "{ shop { name currencyCode myshopifyDomain } }"

# Coste estimado (objeto = 1, conexión = 2 + first × coste del nodo):
#   products(first: 25) -> 2 + 25 × [product 1 + featuredImage 1
#                            + images(first: 6) (2 + 6×1 = 8) + variants(first: 1) (2 + 1 = 3)]
#                        = 2 + 25 × 13 = 327 puntos  (< 1000)
_Q_PRODUCTOS = """
query($first: Int!, $after: String) {
  products(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title descriptionHtml handle onlineStoreUrl productType
      featuredImage { url }
      images(first: 6) { nodes { url } }
      variants(first: 1) { nodes { price sku } }
    }
  }
}
"""

# Coste estimado:
#   orders(first: 10) -> 2 + 10 × [order 1 + currentTotalPriceSet 1 + shopMoney 1
#                          + customerJourneySummary 1 + lastVisit 1
#                          + lineItems(first: 10) (2 + 10 × (lineItem 1 + originalUnitPriceSet 1
#                                                            + shopMoney 1) = 32)]
#                     = 2 + 10 × 37 = 372 puntos  (< 1000; con first: 50 y lineItems 20 daba 3352)
_Q_PEDIDOS = """
query($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id name createdAt
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      customerJourneySummary { lastVisit { landingPage referrerUrl } }
      lineItems(first: 10) { nodes { sku title quantity originalUnitPriceSet { shopMoney { amount } } } }
    }
  }
}
"""


def _id_de_gid(gid):
    """'gid://shopify/Product/123' -> '123' (si no hay número, el gid entero)."""
    m = _RE_GID.search(str(gid or ""))
    return m.group(1) if m else str(gid or "")


def utm_content_de(landing_page):
    """utm_content del query string de una URL o ruta ('/x?utm_content=a')."""
    if not landing_page:
        return None
    try:
        valores = parse_qs(urlparse(str(landing_page)).query).get("utm_content") or []
    except ValueError:
        return None
    if not valores:
        return None
    return valores[0].strip() or None


def _espera_throttled(extensiones):
    """Segundos a esperar según `extensions.cost.throttleStatus`:
    lo que falta para cubrir el coste pedido al ritmo de recuperación,
    mínimo 1 s, tope MAX_ESPERA_THROTTLED; sin datos, 2 s."""
    coste = (extensiones or {}).get("cost") or {}
    estado = coste.get("throttleStatus") or {}
    try:
        pedido = float(coste.get("requestedQueryCost"))
        disponible = float(estado.get("currentlyAvailable"))
        ritmo = float(estado.get("restoreRate"))
    except (TypeError, ValueError):
        return ESPERA_THROTTLED_DEFECTO
    if ritmo <= 0:
        return MAX_ESPERA_THROTTLED
    return min(MAX_ESPERA_THROTTLED, max(1.0, (pedido - disponible) / ritmo))


def _errores_usuario(data):
    """Primer mensaje de `userErrors` no vacío en el primer nivel de `data`."""
    for valor in (data or {}).values():
        if isinstance(valor, dict):
            errores = valor.get("userErrors")
            if errores:
                return str((errores[0] or {}).get("message") or "error")
    return None


class _Throttled(Exception):
    """Interno: Shopify devolvió errors[].extensions.code == THROTTLED."""

    def __init__(self, extensiones):
        super().__init__("THROTTLED")
        self.extensiones = extensiones or {}


@registrar
class Shopify(Conector):
    tipo = "shopify"
    tiene_pedidos = True
    soporta_utm = True

    def __init__(self, credenciales):
        super().__init__(credenciales)
        dominio = str(self.credenciales.get("dominio") or "").strip().lower()
        dominio = re.sub(r"^https?://", "", dominio).strip("/").split("/")[0]
        token = str(self.credenciales.get("token") or "").strip()
        if not dominio:
            raise ValueError("Falta el dominio de la tienda Shopify (ej. tienda.myshopify.com).")
        if not token:
            raise ValueError("Falta el token de acceso de Shopify (Admin API access token).")
        self.dominio = dominio
        self._token = token
        self._s = None

    # --- transporte --------------------------------------------------------

    @property
    def _url(self):
        return f"https://{self.dominio}/admin/api/{VERSION_API}/graphql.json"

    def _graphql(self, query, variables=None):
        """Una query; si Shopify contesta THROTTLED (HTTP 200) espera y
        reintenta una sola vez."""
        reintentado = False
        while True:
            try:
                return self._graphql_una_vez(query, variables)
            except _Throttled as e:
                if reintentado:
                    raise ErrorConector(_MSG_THROTTLED)
                reintentado = True
                time.sleep(_espera_throttled(e.extensiones))

    def _graphql_una_vez(self, query, variables=None):
        if self._s is None:
            self._s = sesion()
        r = pedir(self._s, "POST", self._url, nombre=NOMBRE,
                  headers={"X-Shopify-Access-Token": self._token, "Content-Type": "application/json"},
                  json={"query": query, "variables": variables or {}})
        if r.status_code in (401, 403):
            raise ErrorConector(_MSG_CREDENCIALES)
        if r.status_code == 404:
            raise ErrorConector(f"No se encontró la tienda Shopify «{self.dominio}» (HTTP 404). "
                                "Revisa el dominio.")
        if r.status_code != 200:
            raise error_generico(r, NOMBRE)
        cuerpo = json_de(r, NOMBRE)
        if not isinstance(cuerpo, dict):
            raise ErrorConector("Shopify respondió con un formato inesperado.")
        errores = cuerpo.get("errors")
        if errores:
            primero = errores[0] if isinstance(errores, list) else errores
            if not isinstance(primero, dict):
                primero = {"message": str(primero)}
            mensaje = str(primero.get("message") or "error")[:160]
            codigo = str((primero.get("extensions") or {}).get("code") or "").upper()
            if codigo == "THROTTLED":
                raise _Throttled(cuerpo.get("extensions") or primero.get("extensions"))
            if codigo == "ACCESS_DENIED" or "access denied" in mensaje.lower():
                raise ErrorConector(_MSG_CREDENCIALES)
            raise ErrorConector(f"Shopify devolvió un error: {mensaje}")
        data = cuerpo.get("data") or {}
        usuario = _errores_usuario(data)
        if usuario:
            raise ErrorConector(f"Shopify devolvió un error: {usuario[:160]}")
        return data

    def _paginar(self, query, clave, first, variables=None):
        after = None
        while True:
            vars_ = dict(variables or {}, first=first, after=after)
            conexion = self._graphql(query, vars_).get(clave) or {}
            for nodo in conexion.get("nodes") or []:
                yield nodo
            info = conexion.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                return
            after = info["endCursor"]

    # --- API pública -------------------------------------------------------

    def _shop(self):
        return self._graphql(_Q_SHOP).get("shop") or {}

    def listar_productos(self):
        moneda = self._shop().get("currencyCode")
        productos = []
        for n in self._paginar(_Q_PRODUCTOS, "products", PAGINA_PRODUCTOS):
            variantes = (n.get("variants") or {}).get("nodes") or []
            variante = variantes[0] or {} if variantes else {}
            fotos = [i.get("url") for i in ((n.get("images") or {}).get("nodes") or []) if isinstance(i, dict)]
            principal = (n.get("featuredImage") or {}).get("url")
            handle = n.get("handle") or ""
            productos.append(normalizar_producto({
                "fuente_id": _id_de_gid(n.get("id")),
                "nombre": n.get("title"),
                "descripcion": limpiar_html(n.get("descriptionHtml")),
                "precio": variante.get("price"),
                "moneda": moneda,
                "url_compra": n.get("onlineStoreUrl")
                              or (f"https://{self.dominio}/products/{handle}" if handle else None),
                "fotos": ([principal] if principal else []) + fotos,
                "categoria": n.get("productType"),
                "url_imagen_principal": principal,
                "extra": {"handle": handle, "sku": variante.get("sku"), "gid": n.get("id")},
            }))
        return productos

    def pedidos_desde(self, fecha_iso):
        dia = str(fecha_iso or "")[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", dia):
            raise ValueError("pedidos_desde necesita una fecha ISO (YYYY-MM-DD…).")
        pedidos = []
        for n in self._paginar(_Q_PEDIDOS, "orders", PAGINA_PEDIDOS, {"query": f"created_at:>={dia}"}):
            dinero = (n.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
            visita = (n.get("customerJourneySummary") or {}).get("lastVisit") or {}
            items = []
            for li in (n.get("lineItems") or {}).get("nodes") or []:
                items.append({
                    "sku": li.get("sku"), "nombre": li.get("title"), "cantidad": li.get("quantity"),
                    "precio": ((li.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get("amount"),
                })
            pedidos.append(normalizar_pedido({
                "fuente_id": _id_de_gid(n.get("id")),
                "fecha": n.get("createdAt"),
                "total": dinero.get("amount"),
                "moneda": dinero.get("currencyCode"),
                "items": items,
                "utm_content": utm_content_de(visita.get("landingPage")),
            }))
        return pedidos

    def probar(self):
        shop = self._shop()
        return {"ok": True, "nombre": str(shop.get("name") or ""),
                "detalle": f"Conectado a {shop.get('myshopifyDomain') or self.dominio} "
                           f"(moneda {shop.get('currencyCode') or '?'})."}
