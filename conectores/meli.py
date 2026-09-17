"""
Conector MercadoLibre — API pública con OAuth de usuario
(`https://api.mercadolibre.com`, header `Authorization: Bearer …`).

Credenciales: `access_token`, `refresh_token`, `user_id`, `expira_en`
(ISO, cuándo vence el access token) y `site_id` (`MCO`, `MLA`…). Como el
access token dura 6 h, antes de cualquier llamada `_asegurar_token` mira
`expira_en`: si vence en menos de 5 min pide uno nuevo con
`grant_type=refresh_token` (necesita `MELI_APP_ID`/`MELI_SECRET` del
entorno), actualiza `self.credenciales` y deja la copia en
`self.credenciales_actualizadas` para que el sincronizador la guarde —
si no hubo refresh queda en None. El refresh token es de UN solo uso: si
no se guarda el nuevo, la próxima vez no hay forma de renovar. Por lo
mismo el POST a `/oauth/token` NUNCA se reintenta (`reintentar=False`):
un timeout ahí pide reconectar la tienda en vez de reenviar el token.

`listar_productos`: `/users/{user_id}/items/search?status=active` (ids,
paginado por offset) y `/items?ids=…` en lotes de 20 con `attributes`
recortados. La descripción (`/items/{id}/description`, una llamada por
ítem) solo se pide con `cargar_descripciones=True` (primera importación)
para no gastar cuota; `extra["descripcion_cargada"]` lo deja anotado
(un 404 ahí significa "sin descripción": queda `""` y se sigue).
`pedidos_desde`: `/orders/search?seller=…&order.date_created.from=…`.
MELI no expone utm de origen: `soporta_utm=False`, `utm_content` siempre None.

Alta (rutas del dashboard): `url_autorizacion(state, redirect_uri)` arma
el enlace a `auth.mercadolibre.com.co` (`MELI_AUTH_HOST` para otro país) y
`cambiar_code(code, redirect_uri)` cambia el `code` por credenciales
completas (incluye `site_id` y `nickname` leídos de `/users/me`).
"""
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from . import registrar
from ._http import ErrorTiempo, error_generico, json_de, pedir, sesion
from .base import Conector, ErrorConector, normalizar_pedido, normalizar_producto

API = "https://api.mercadolibre.com"
AUTH_HOST_DEFECTO = "auth.mercadolibre.com.co"
TAMANO_PAGINA = 50
LOTE_ITEMS = 20
MARGEN_REFRESH = timedelta(minutes=5)
ATRIBUTOS_ITEM = "id,title,price,currency_id,permalink,pictures,category_id,available_quantity"
NOMBRE = "MercadoLibre"
_MSG_CREDENCIALES = ("MercadoLibre rechazó el token (inválido o vencido). "
                     "Vuelve a conectar la tienda.")


def _ahora():
    return datetime.now(timezone.utc)


def _app():
    """(MELI_APP_ID, MELI_SECRET) del entorno o ErrorConector nombrándolas."""
    app_id = (os.environ.get("MELI_APP_ID") or "").strip()
    secreto = (os.environ.get("MELI_SECRET") or "").strip()
    faltan = [n for n, v in (("MELI_APP_ID", app_id), ("MELI_SECRET", secreto)) if not v]
    if faltan:
        raise ErrorConector("Falta configurar " + " y ".join(faltan) + " en el .env del servidor "
                            "(app de developers.mercadolibre.com).")
    return app_id, secreto


def _parsear_fecha(valor):
    """ISO (con o sin zona) -> datetime aware en UTC; None si no se entiende."""
    t = str(valor or "").strip().replace(" ", "T", 1)
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fecha_meli(fecha_iso):
    """'2026-09-01' / '2026-09-01T10:00:00' -> '2026-09-01T10:00:00.000-00:00'."""
    dt = _parsear_fecha(fecha_iso)
    if dt is None:
        raise ValueError("pedidos_desde necesita una fecha ISO (YYYY-MM-DD…).")
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000-00:00")


def _credenciales_de_token(cuerpo, anteriores=None):
    """Respuesta de /oauth/token -> dict de credenciales (calcula expira_en)."""
    if not isinstance(cuerpo, dict) or not cuerpo.get("access_token"):
        raise ErrorConector("MercadoLibre no devolvió un token de acceso.")
    try:
        segundos = int(cuerpo.get("expires_in") or 21600)
    except (TypeError, ValueError):
        segundos = 21600
    base = dict(anteriores or {})
    base.update({
        "access_token": str(cuerpo["access_token"]),
        "refresh_token": str(cuerpo.get("refresh_token") or base.get("refresh_token") or ""),
        "user_id": str(cuerpo.get("user_id") or base.get("user_id") or ""),
        "expira_en": (_ahora() + timedelta(seconds=segundos)).isoformat(timespec="seconds"),
    })
    return base


def _post_token(datos):
    # Sin reintentos: el refresh token (y el code) son de un solo uso, así
    # que reenviar el POST tras un timeout/5xx solo produciría invalid_grant.
    try:
        r = pedir(sesion(), "POST", f"{API}/oauth/token", nombre=NOMBRE, reintentar=False,
                  data=datos, headers={"Accept": "application/json"})
    except ErrorTiempo:
        raise ErrorConector("MercadoLibre no respondió a tiempo al renovar el token (es de un "
                            "solo uso y pudo quedar consumido). Vuelve a conectar la tienda.")
    if r.status_code in (400, 401, 403):
        raise ErrorConector("MercadoLibre rechazó la autorización (código o refresh token inválido "
                            "o vencido). Vuelve a conectar la tienda.")
    if r.status_code != 200:
        raise error_generico(r, NOMBRE)
    return json_de(r, NOMBRE)


def _get_users_me(access_token):
    r = pedir(sesion(), "GET", f"{API}/users/me", nombre=NOMBRE,
              headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise ErrorConector(_MSG_CREDENCIALES)
    if r.status_code != 200:
        raise error_generico(r, NOMBRE)
    return json_de(r, NOMBRE)


# --- OAuth de alta (las rutas del dashboard las llaman) ------------------------

def url_autorizacion(state, redirect_uri):
    app_id, _ = _app()
    host = (os.environ.get("MELI_AUTH_HOST") or AUTH_HOST_DEFECTO).strip()
    host = re.sub(r"^https?://", "", host).strip("/") or AUTH_HOST_DEFECTO
    params = urlencode({"response_type": "code", "client_id": app_id, "state": str(state or ""),
                        "redirect_uri": redirect_uri})
    return f"https://{host}/authorization?{params}"


def cambiar_code(code, redirect_uri):
    """Cambia el `code` del callback por credenciales completas (con
    `site_id` y `nickname` de /users/me). Lanza ErrorConector si falla."""
    app_id, secreto = _app()
    if not str(code or "").strip():
        raise ErrorConector("MercadoLibre no devolvió el código de autorización.")
    cuerpo = _post_token({"grant_type": "authorization_code", "client_id": app_id,
                          "client_secret": secreto, "code": str(code).strip(),
                          "redirect_uri": redirect_uri})
    credenciales = _credenciales_de_token(cuerpo)
    if not credenciales["refresh_token"]:
        raise ErrorConector("MercadoLibre no devolvió refresh token: la app necesita el permiso "
                            "offline_access (developers.mercadolibre.com). Revisa la app y vuelve "
                            "a conectar la tienda.")
    yo = _get_users_me(credenciales["access_token"])
    credenciales["site_id"] = str(yo.get("site_id") or "")
    credenciales["nickname"] = str(yo.get("nickname") or "")
    if not credenciales["user_id"]:
        credenciales["user_id"] = str(yo.get("id") or "")
    return credenciales


@registrar
class Meli(Conector):
    tipo = "meli"
    tiene_pedidos = True
    soporta_utm = False

    def __init__(self, credenciales, cargar_descripciones=False):
        super().__init__(credenciales)
        faltan = [c for c in ("access_token", "refresh_token", "user_id")
                  if not str(self.credenciales.get(c) or "").strip()]
        if faltan:
            raise ValueError("Faltan credenciales de MercadoLibre: " + ", ".join(faltan)
                             + ". Vuelve a conectar la tienda.")
        self.user_id = str(self.credenciales["user_id"]).strip()
        self.cargar_descripciones = bool(cargar_descripciones)
        self.credenciales_actualizadas = None
        self._s = None

    # --- token ---------------------------------------------------------------

    def _asegurar_token(self):
        vence = _parsear_fecha(self.credenciales.get("expira_en"))
        if vence is not None and vence > _ahora() + MARGEN_REFRESH:
            return
        app_id, secreto = _app()
        cuerpo = _post_token({"grant_type": "refresh_token", "client_id": app_id,
                              "client_secret": secreto,
                              "refresh_token": str(self.credenciales["refresh_token"])})
        self.credenciales = _credenciales_de_token(cuerpo, self.credenciales)
        self.credenciales_actualizadas = dict(self.credenciales)

    # --- transporte ----------------------------------------------------------

    def _get(self, ruta, params=None, tolerar_404=False):
        """GET con el bearer; con `tolerar_404=True` un 404 devuelve None
        en vez de ErrorConector (p. ej. ítem sin descripción)."""
        if self._s is None:
            self._s = sesion()
        r = pedir(self._s, "GET", f"{API}/{ruta.lstrip('/')}", nombre=NOMBRE, params=params or {},
                  headers={"Authorization": f"Bearer {self.credenciales['access_token']}",
                           "Accept": "application/json"})
        if r.status_code in (401, 403):
            raise ErrorConector(_MSG_CREDENCIALES)
        if r.status_code == 404:
            if tolerar_404:
                return None
            raise ErrorConector("MercadoLibre no encontró el recurso pedido (HTTP 404).")
        if r.status_code != 200:
            raise error_generico(r, NOMBRE)
        return json_de(r, NOMBRE)

    def _paginar(self, ruta, params):
        offset = 0
        while True:
            cuerpo = self._get(ruta, dict(params, offset=offset, limit=TAMANO_PAGINA))
            filas = cuerpo.get("results") or [] if isinstance(cuerpo, dict) else []
            for fila in filas:
                yield fila
            paging = (cuerpo.get("paging") or {}) if isinstance(cuerpo, dict) else {}
            offset += len(filas)
            try:
                total = int(paging.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if not filas or len(filas) < TAMANO_PAGINA or offset >= total:
                return

    # --- API pública ---------------------------------------------------------

    def listar_productos(self):
        self._asegurar_token()
        ids = [str(i) for i in self._paginar(f"users/{self.user_id}/items/search", {"status": "active"})
               if i]
        productos = []
        for inicio in range(0, len(ids), LOTE_ITEMS):
            lote = ids[inicio:inicio + LOTE_ITEMS]
            respuesta = self._get("items", {"ids": ",".join(lote), "attributes": ATRIBUTOS_ITEM})
            for entrada in respuesta if isinstance(respuesta, list) else []:
                if not isinstance(entrada, dict) or entrada.get("code") != 200:
                    continue
                item = entrada.get("body") or {}
                if not item.get("id"):
                    continue
                descripcion, cargada = "", False
                if self.cargar_descripciones:
                    # MELI responde 404 cuando el ítem simplemente no tiene descripción.
                    desc = self._get(f"items/{item['id']}/description", tolerar_404=True)
                    descripcion = str((desc or {}).get("plain_text") or "") if isinstance(desc, dict) else ""
                    cargada = True
                fotos = [f.get("secure_url") or f.get("url") for f in item.get("pictures") or []
                         if isinstance(f, dict)]
                productos.append(normalizar_producto({
                    "fuente_id": item["id"],
                    "nombre": item.get("title"),
                    "descripcion": descripcion,
                    "precio": item.get("price"),
                    "moneda": item.get("currency_id"),
                    "url_compra": item.get("permalink"),
                    "fotos": fotos,
                    "categoria": item.get("category_id"),
                    "extra": {"descripcion_cargada": cargada, "category_id": item.get("category_id"),
                              "available_quantity": item.get("available_quantity")},
                }))
        return productos

    def pedidos_desde(self, fecha_iso):
        desde = _fecha_meli(fecha_iso)
        self._asegurar_token()
        pedidos = []
        for o in self._paginar("orders/search", {"seller": self.user_id,
                                                 "order.date_created.from": desde,
                                                 "sort": "date_desc"}):
            if not isinstance(o, dict):
                continue
            items = []
            for oi in o.get("order_items") or []:
                if not isinstance(oi, dict):
                    continue
                item = oi.get("item") or {}
                items.append({"sku": item.get("seller_sku") or item.get("id"), "nombre": item.get("title"),
                              "cantidad": oi.get("quantity"), "precio": oi.get("unit_price")})
            pedidos.append(normalizar_pedido({
                "fuente_id": o.get("id"),
                "fecha": o.get("date_created"),
                "total": o.get("total_amount"),
                "moneda": o.get("currency_id"),
                "items": items,
                "utm_content": None,
            }))
        return pedidos

    def probar(self):
        self._asegurar_token()
        yo = self._get("users/me")
        return {"ok": True, "nombre": str(yo.get("nickname") or ""),
                "detalle": f"Conectado como {yo.get('nickname') or self.user_id} "
                           f"({yo.get('site_id') or self.credenciales.get('site_id') or '?'})."}
