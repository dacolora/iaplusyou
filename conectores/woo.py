"""
Conector WooCommerce — REST `wc/v3` con auth básica (consumer key/secret)
sobre https (obligatorio: las claves viajan en cada petición).

Credenciales: `url` (`https://tienda.com`), `ck`, `cs`.
`listar_productos` pagina `/products?status=publish&per_page=50` con la
cabecera `X-WP-TotalPages` y pide `/settings/general` UNA vez para la
moneda (`woocommerce_currency`). `pedidos_desde` pagina `/orders?after=…`
(processing + completed) y saca `utm_content` de `meta_data`
(`_wc_order_attribution_utm_content`, lo que escribe Order Attribution).
"""
import re
from urllib.parse import urlparse

from . import registrar
from ._http import error_generico, json_de, pedir, sesion
from .base import Conector, ErrorConector, limpiar_html, normalizar_pedido, normalizar_producto

TAMANO_PAGINA = 50
NOMBRE = "WooCommerce"
META_UTM_CONTENT = "_wc_order_attribution_utm_content"


def _meta(meta_data, clave):
    for m in meta_data or []:
        if isinstance(m, dict) and m.get("key") == clave:
            valor = m.get("value")
            return str(valor).strip() if valor is not None else None
    return None


@registrar
class Woo(Conector):
    tipo = "woo"
    tiene_pedidos = True
    soporta_utm = True

    def __init__(self, credenciales):
        super().__init__(credenciales)
        url = str(self.credenciales.get("url") or "").strip().rstrip("/")
        partes = urlparse(url) if url else None
        if not url or not partes.netloc:
            raise ValueError("Falta la URL de la tienda WooCommerce (ej. https://mitienda.com).")
        if partes.scheme != "https":
            raise ValueError("La URL de la tienda WooCommerce debe empezar por https:// "
                             "(las claves viajan en cada petición).")
        ck = str(self.credenciales.get("ck") or "").strip()
        cs = str(self.credenciales.get("cs") or "").strip()
        if not ck or not cs:
            raise ValueError("Faltan las claves de la API de WooCommerce (Consumer key y Consumer secret).")
        self.url = url
        self._auth = (ck, cs)
        self._s = None

    # --- transporte --------------------------------------------------------

    def _get(self, ruta, params=None):
        if self._s is None:
            self._s = sesion()
        r = pedir(self._s, "GET", f"{self.url}/wp-json/wc/v3/{ruta.lstrip('/')}", nombre=NOMBRE,
                  params=params or {}, auth=self._auth, headers={"Accept": "application/json"})
        if r.status_code in (401, 403):
            raise ErrorConector("WooCommerce rechazó las claves: Consumer key/secret inválidos o sin "
                                "permiso de lectura.")
        if r.status_code == 404:
            raise ErrorConector("No se encontró la API REST de WooCommerce en esa URL (HTTP 404). "
                                "Revisa la URL y que el plugin esté activo.")
        if r.status_code != 200:
            raise error_generico(r, NOMBRE)
        return r

    def _paginar(self, ruta, params):
        pagina = 1
        while True:
            r = self._get(ruta, dict(params, per_page=TAMANO_PAGINA, page=pagina))
            filas = json_de(r, NOMBRE)
            if not isinstance(filas, list):
                raise ErrorConector("WooCommerce respondió con un formato inesperado.")
            for fila in filas:
                if isinstance(fila, dict):
                    yield fila
            try:
                total = int((r.headers or {}).get("X-WP-TotalPages") or 1)
            except (TypeError, ValueError):
                total = 1
            if not filas or pagina >= total:
                return
            pagina += 1

    def _moneda(self):
        ajustes = json_de(self._get("settings/general"), NOMBRE)
        for a in ajustes if isinstance(ajustes, list) else []:
            if isinstance(a, dict) and a.get("id") == "woocommerce_currency":
                return a.get("value")
        return None

    # --- API pública -------------------------------------------------------

    def listar_productos(self):
        moneda = self._moneda()
        productos = []
        for p in self._paginar("products", {"status": "publish"}):
            categorias = [c for c in p.get("categories") or [] if isinstance(c, dict)]
            productos.append(normalizar_producto({
                "fuente_id": p.get("id"),
                "nombre": p.get("name"),
                "descripcion": limpiar_html(p.get("description")),
                "precio": p.get("price"),
                "moneda": moneda,
                "url_compra": p.get("permalink"),
                "fotos": [i.get("src") for i in p.get("images") or [] if isinstance(i, dict)],
                "categoria": categorias[0].get("name") if categorias else None,
                "extra": {"sku": p.get("sku"), "tipo": p.get("type")},
            }))
        return productos

    def pedidos_desde(self, fecha_iso):
        fecha = str(fecha_iso or "").strip().replace(" ", "T", 1)
        if not re.match(r"^\d{4}-\d{2}-\d{2}", fecha):
            raise ValueError("pedidos_desde necesita una fecha ISO (YYYY-MM-DD…).")
        if len(fecha) == 10:
            fecha += "T00:00:00"
        pedidos = []
        for o in self._paginar("orders", {"after": fecha, "status": "processing,completed"}):
            items = [{"sku": li.get("sku"), "nombre": li.get("name"), "cantidad": li.get("quantity"),
                      "precio": li.get("price")}
                     for li in o.get("line_items") or [] if isinstance(li, dict)]
            pedidos.append(normalizar_pedido({
                "fuente_id": o.get("id"),
                "fecha": o.get("date_created"),
                "total": o.get("total"),
                "moneda": o.get("currency"),
                "items": items,
                "utm_content": _meta(o.get("meta_data"), META_UTM_CONTENT),
            }))
        return pedidos

    def probar(self):
        moneda = self._moneda()
        return {"ok": True, "nombre": urlparse(self.url).netloc,
                "detalle": f"Conectado a {self.url} (moneda {moneda or '?'})."}
