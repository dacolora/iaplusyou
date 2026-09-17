"""
Conector Shopify — Admin GraphQL (`/admin/api/2025-07/graphql.json`, header
`X-Shopify-Access-Token`; scopes `read_products` y `read_orders`).

Credenciales: `dominio` (`tienda.myshopify.com`) y `token` (`shpat_…`).
`listar_productos` pagina `products(first: 50)` por `pageInfo` y pide
`shop { currencyCode }` UNA vez para la moneda; `pedidos_desde` pagina
`orders` filtrando `created_at:>=YYYY-MM-DD` y saca `utm_content` del
query string de `customerJourneySummary.lastVisit.landingPage`.
Todo error sale como `ErrorConector` con el código HTTP o el mensaje corto
de GraphQL — nunca el token ni el cuerpo completo.
"""
import re
from urllib.parse import parse_qs, urlparse

from . import registrar
from ._http import error_generico, json_de, pedir, sesion
from .base import Conector, ErrorConector, limpiar_html, normalizar_pedido, normalizar_producto

VERSION_API = "2025-07"
TAMANO_PAGINA = 50
NOMBRE = "Shopify"
_MSG_CREDENCIALES = ("Shopify rechazó las credenciales: token inválido o sin permisos "
                     "read_products/read_orders.")

_RE_GID = re.compile(r"(\d+)(?:\?.*)?$")

_Q_SHOP = "{ shop { name currencyCode myshopifyDomain } }"

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

_Q_PEDIDOS = """
query($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id name createdAt
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      customerJourneySummary { lastVisit { landingPage referrerUrl } }
      lineItems(first: 20) { nodes { sku title quantity originalUnitPriceSet { shopMoney { amount } } } }
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


def _errores_usuario(data):
    """Primer mensaje de `userErrors` no vacío en el primer nivel de `data`."""
    for valor in (data or {}).values():
        if isinstance(valor, dict):
            errores = valor.get("userErrors")
            if errores:
                return str((errores[0] or {}).get("message") or "error")
    return None


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
            if codigo == "ACCESS_DENIED" or "access denied" in mensaje.lower():
                raise ErrorConector(_MSG_CREDENCIALES)
            raise ErrorConector(f"Shopify devolvió un error: {mensaje}")
        data = cuerpo.get("data") or {}
        usuario = _errores_usuario(data)
        if usuario:
            raise ErrorConector(f"Shopify devolvió un error: {usuario[:160]}")
        return data

    def _paginar(self, query, clave, variables=None):
        after = None
        while True:
            vars_ = dict(variables or {}, first=TAMANO_PAGINA, after=after)
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
        for n in self._paginar(_Q_PRODUCTOS, "products"):
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
        for n in self._paginar(_Q_PEDIDOS, "orders", {"query": f"created_at:>={dia}"}):
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
