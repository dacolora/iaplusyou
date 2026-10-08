"""Cliente de la API de Triple Whale (solo lectura: Data Out por SQL).

Todo lo que dice este módulo sale de docs/triple-whale/investigacion-api-2026.md,
que cita la referencia oficial (triplewhale.readme.io):

- `POST /orcabase/api/sql` con `{"shopId", "query", "period": {"startDate",
  "endDate"}, "currency"}` — `@startDate`/`@endDate` dentro del SQL se llenan
  con `period`. La respuesta documentada es `{"success", "message", "data":
  [...]}` (una versión anterior leía `rows` y mandaba un campo `parameters`
  que la API no documenta: nunca habría traído nada).
- Llave en la cabecera `x-api-key`, de un USUARIO (sirve para todas sus
  tiendas; muere si ese usuario pierde acceso). La tienda va en cada petición
  como dominio (`example.myshopify.com`, sin https ni barras).
- Tablas: `ads_table` (lo que reporta cada plataforma, un anuncio por día),
  `pixel_joined_tvf()` (lo atribuido por el Triple Pixel, filtrando `model` y
  `attribution_window`) y `blended_stats_tvf()` (la tienda por día).
- Límites: 100 req/s y 600 req/min; 429 trae `Retry-After`. "Our schema is
  dynamic": las columnas se nombran siempre (nunca `SELECT *`) y cada consulta
  tiene una versión mínima de respaldo con las columnas de los ejemplos
  oficiales, por si una de la versión completa no existe en esa cuenta.

Ningún mensaje de error lleva la llave. Las consultas de este módulo son la
mejor lectura del "Data Dictionary"; ninguna se probó todavía contra una
tienda real (ver el spec 2026-09-28-triple-whale-rendimiento-design.md §9).
"""
import os
import posixpath
import re
import time
from datetime import date, timedelta
from urllib.parse import unquote, urlsplit

import requests
from flask_babel import gettext

API_BASE = "https://api.triplewhale.com/api/v2"
TIMEOUT_SEGUNDOS = 60
REINTENTOS_MAX = 3
DELAY_REINTENTO = 1.0  # segundos
ESPERA_MAX_429 = 30.0

# Vocabulario de la columna `model` de pixel_joined_tvf (Data Dictionary,
# "Possible values") y de `attribution_window` ("Example values").
MODELOS = ("Triple Attribution", "Triple Attribution + Views", "Clicks & Views", "Linear All", "Linear Paid",
           "First Click", "Last Click", "Total Impact")
VENTANAS = ("1_day", "7_days", "14_days", "28_days", "lifetime")
MODELO_DEFECTO = "Triple Attribution"
VENTANA_DEFECTO = "lifetime"
# El formulario viejo ofrecía valores que Triple Whale no conoce.
_MODELOS_VIEJOS = {"first touch": "First Click", "last touch": "Last Click", "last click 7d": "Last Click",
                   "linear paid 7d": "Linear Paid"}
_VENTANAS_VIEJAS = {"1": "1_day", "1d": "1_day", "7": "7_days", "7d": "7_days", "14": "14_days", "14d": "14_days",
                    "28": "28_days", "28d": "28_days", "30": "28_days", "30d": "28_days"}
# Canal estandarizado de Meta en las tablas de Triple Whale.
CANAL_META = "facebook-ads"
# Nombres de los canales estandarizados de Triple Whale ("ads-standardized-channel-ids"). Viven aquí (no en el
# blueprint) para que `mejorar`, que corre en el worker, no importe `rutas`.
NOMBRES_CANAL = {"facebook-ads": "Meta", "google-ads": "Google Ads", "tiktok-ads": "TikTok", "bing": "Microsoft Ads",
                 "pinterest-ads": "Pinterest", "snapchat-ads": "Snapchat", "twitter-ads": "X"}
# «REQUIRED TRACKING PARAMETERS» de la KB de Meta en Triple Whale: van en los
# Parámetros de URL del anuncio (url_tags del AdCreative), donde Meta resuelve
# {{site_source_name}} y {{ad.id}}. Sin ellos Triple Whale igual ve el gasto,
# pero "attribution accuracy may suffer significantly".
URL_TAGS = "tw_source={{site_source_name}}&tw_adid={{ad.id}}"

# Tarjetas de análisis (spec 2026-10-08 §8.1): solo se incrusta en la página o se baja un medio de estos hosts, por
# https. files.triplewhale.com aloja la miniatura y el mp4 de cada anuncio de Meta; el host de R2 (R2_PUBLIC_BASE_URL),
# los de Creatv. Un video de TikTok llega como página (www.tiktok.com/embed/…) y queda como enlace.
HOSTS_MEDIOS = ("files.triplewhale.com",)


def _host_r2():
    try:
        return (urlsplit(os.environ.get("R2_PUBLIC_BASE_URL") or "").hostname or "").lower() or None
    except ValueError:
        return None


def medio_permitido(url):
    """¿Se puede incrustar o bajar este medio? https, sin usuario ni puerto raro, y host exacto de HOSTS_MEDIOS o
    el de R2."""
    try:
        p = urlsplit(str(url or "").strip())
        puerto = p.port
    except ValueError:
        return False
    if p.scheme != "https" or not p.hostname or p.username or p.password or puerto not in (None, 443):
        return False
    host = p.hostname.lower()
    return host in HOSTS_MEDIOS or (host == _host_r2())


# Un video que no se puede incrustar (TikTok llega como página) se ofrece como enlace «Ver en …», pero solo a la
# plataforma del propio anuncio (su `canal`): una URL rara que venga en los datos no se pinta, ni un enlace de otra
# plataforma, ni un redirector («l.facebook.com/l.php?u=…», «youtube.com/redirect?q=…»), que mandaría a cualquier sitio.
ENLACES_POR_CANAL = {
    "tiktok-ads": ("tiktok.com",),
    "facebook-ads": ("facebook.com", "fb.watch", "instagram.com"),
    "snapchat-ads": ("snapchat.com",),
    "google-ads": ("youtube.com",),
    "pinterest-ads": ("pinterest.com",),
}
ENLACES_PLATAFORMAS = tuple(d for dominios in ENLACES_POR_CANAL.values() for d in dominios)
_HOSTS_REDIRECTOR = ("l.", "lm.")
# Redirectores de las plataformas: Facebook (/l.php, /flx/warn), TikTok (/link), Pinterest (/offsite) y los genéricos
# (/redirect). Revisión final de las tarjetas, B8 (2026-10-08): /link, /offsite y /flx/warn se colaban.
_RUTAS_REDIRECTOR = ("/l.php", "/redirect", "/link", "/offsite", "/flx/warn")


def _ruta_como_la_lee_el_servidor(ruta):
    """La ruta de una URL como la resolvería el servidor, para compararla con `_RUTAS_REDIRECTOR`: sin
    %-codificación (hasta tres vueltas: «/%252e/» también), con «\\» como «/» (así lo hacen los navegadores en
    https), con los segmentos «.» y «..» resueltos y una sola barra al principio, en minúsculas. «//l.php», «/%6C.php»,
    «/./l.php», «/a/../l.php» y «/%2e/l.php» salen todas «/l.php». Revisión final de las tarjetas, B8 (2026-10-08):
    los puntos y los `..` se colaban."""
    for _ in range(3):
        decodificada = unquote(ruta)
        if decodificada == ruta:
            break
        ruta = decodificada
    ruta = "/" + ruta.replace("\\", "/").lstrip("/")
    return posixpath.normpath(ruta).lower()


def enlace_permitido(url, canal=None):
    """¿Se puede pintar este enlace «Ver en …»? https, sin usuario ni puerto raro, host exacto o subdominio de
    la plataforma del `canal` del anuncio (canal desconocido: no; sin canal: cualquiera de las conocidas), y nunca
    un redirector de enlaces."""
    try:
        p = urlsplit(str(url or "").strip())
        puerto = p.port
    except ValueError:
        return False
    if p.scheme != "https" or not p.hostname or p.username or p.password or puerto not in (None, 443):
        return False
    host = p.hostname.lower()
    if host.startswith(_HOSTS_REDIRECTOR) or _ruta_como_la_lee_el_servidor(p.path).startswith(_RUTAS_REDIRECTOR):
        return False
    if canal is None:
        dominios = ENLACES_PLATAFORMAS
    else:
        dominios = ENLACES_POR_CANAL.get(str(canal).strip().lower(), ())
    return any(host == d or host.endswith("." + d) for d in dominios)


MONEDAS = ("USD", "EUR", "GBP", "AUD", "CAD", "MXN", "COP", "BRL", "CLP", "PEN", "ARS", "NOK", "SEK")

_RE_DOMINIO = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def tachar_llave(texto, llave):
    """`texto` con el valor exacto de `llave` tachado («***»). Ningún mensaje nuestro lleva la llave, pero
    uno de Triple Whale podría repetirla sin «key=» delante (que `cola.sin_token` no reconoce): se tacha
    antes de mostrarlo, guardarlo o dejarlo en un evento. Una llave de menos de 6 letras no se tacha (se
    comería palabras sueltas). Auditoría de seguridad, 2026-10-08."""
    texto = str(texto or "")
    return texto.replace(llave, "***") if llave and len(llave) >= 6 else texto


class ErrorTripleWhale(Exception):
    """Error en la API de Triple Whale. El mensaje se muestra a la persona."""


class ErrorLlave(ErrorTripleWhale):
    """401: llave ausente, revocada, sin el permiso de SQL o del usuario que perdió acceso."""


class ErrorTienda(ErrorTripleWhale):
    """403 / "Unrecognized shop identifier": la tienda no existe o la llave no la ve."""


class ErrorConsulta(ErrorTripleWhale):
    """La consulta no sirvió (400 o un 5xx que no se arregló reintentando):
    casi siempre una columna que esa cuenta no tiene. Quien llama prueba la
    versión mínima de la consulta."""


class ErrorCifrado(Exception):
    """No se pudo descifrar la llave."""


# ------------------------------------------------------------ vocabulario ---

def normalizar_modelo(valor):
    v = (valor or "").strip()
    if v in MODELOS:
        return v
    return _MODELOS_VIEJOS.get(v.lower(), MODELO_DEFECTO)


def normalizar_ventana(valor):
    v = (valor or "").strip()
    if v in VENTANAS:
        return v
    if v.lower() == "lifetime":
        return "lifetime"
    return _VENTANAS_VIEJAS.get(v.lower(), VENTANA_DEFECTO)


def normalizar_moneda(valor):
    v = (valor or "").strip().upper()
    return v if re.fullmatch(r"[A-Z]{3}", v) else "USD"


def normalizar_dominio(texto):
    """"https://Mi-Tienda.myshopify.com/admin" -> "mi-tienda.myshopify.com";
    None si no parece un dominio. La API pide "a plain string … No leading or
    trailing slashes, no URL wrapping"."""
    t = (texto or "").strip().lower()
    t = re.sub(r"^[a-z]+://", "", t)
    t = t.split("/")[0].split("?")[0].split("#")[0].strip(".")
    if t.startswith("www."):
        t = t[4:]
    if len(t) > 200 or not _RE_DOMINIO.match(t):
        return None
    return t


def _literal(valor, permitidos):
    """Literal SQL de un valor de lista blanca (modelo, ventana): nunca entra
    texto libre a la consulta."""
    if valor not in permitidos:
        raise ValueError(f"valor fuera de la lista: {valor!r}")
    return "'" + valor.replace("'", "''") + "'"


# ---------------------------------------------------------------- HTTP ---

def _enviar(url, headers, cuerpo):
    """Costura de pruebas: la única llamada POST a Triple Whale."""
    return requests.post(url, headers=headers, json=cuerpo, timeout=TIMEOUT_SEGUNDOS)


def _dormir(segundos):
    time.sleep(segundos)


def _espera_429(resp, intento):
    try:
        segundos = float(resp.headers.get("Retry-After"))
    except (TypeError, ValueError):
        segundos = DELAY_REINTENTO * (2 ** intento)
    return max(0.0, min(segundos, ESPERA_MAX_429))


def _filas(datos):
    """`data` es lo documentado; `rows` y una lista suelta se aceptan por si
    la API cambia de forma."""
    if isinstance(datos, list):
        return [f for f in datos if isinstance(f, dict)]
    if not isinstance(datos, dict):
        return []
    for clave in ("data", "rows"):
        valor = datos.get(clave)
        if isinstance(valor, list):
            return [f for f in valor if isinstance(f, dict)]
    return []


def sql_query(llave_api, shop_id, consulta, desde, hasta, moneda=None):
    """Corre una consulta SQL (sabor ClickHouse) para `shop_id` entre `desde` y
    `hasta` (YYYY-MM-DD, ambos incluidos). Devuelve la lista de filas.

    429 y 5xx se reintentan con espera (el 429 respeta `Retry-After`); 401
    -> ErrorLlave, 403 / tienda desconocida -> ErrorTienda, 400 o un 5xx que
    persiste -> ErrorConsulta, red -> ErrorTripleWhale."""
    cuerpo = {"shopId": shop_id, "query": consulta, "period": {"startDate": desde, "endDate": hasta}}
    if moneda:
        cuerpo["currency"] = moneda
    headers = {"x-api-key": llave_api, "Content-Type": "application/json"}
    ultimo = None
    for intento in range(REINTENTOS_MAX):
        try:
            resp = _enviar(f"{API_BASE}/orcabase/api/sql", headers, cuerpo)
        except requests.Timeout:
            ultimo = ErrorTripleWhale(gettext("Triple Whale no respondió a tiempo."))
            if intento < REINTENTOS_MAX - 1:
                _dormir(DELAY_REINTENTO * (2 ** intento))
                continue
            raise ultimo
        except requests.RequestException as e:
            raise ErrorTripleWhale(gettext("No pude hablar con Triple Whale (%(tipo)s).",
                                           tipo=type(e).__name__)) from None
        codigo = resp.status_code
        texto = (resp.text or "")[:300]
        if codigo == 200:
            try:
                return _filas(resp.json())
            except ValueError:
                raise ErrorConsulta(gettext("Triple Whale respondió algo que no es JSON.")) from None
        if codigo == 429:
            ultimo = ErrorTripleWhale(gettext("Triple Whale pidió esperar (límite de llamadas)."))
            if intento < REINTENTOS_MAX - 1:
                _dormir(_espera_429(resp, intento))
                continue
            raise ultimo
        if codigo == 401:
            raise ErrorLlave(gettext("Triple Whale rechazó la llave: está revocada, no tiene el permiso de "
                                     "consultas (Data Out / SQL) o su usuario perdió acceso a la tienda."))
        if codigo == 403 or "Unrecognized shop identifier" in texto:
            raise ErrorTienda(gettext("Triple Whale no reconoce la tienda «%(tienda)s» con esta llave. Revisa el "
                                      "dominio (el shop-id de la URL de Triple Whale).", tienda=shop_id))
        if codigo == 400:
            raise ErrorConsulta(gettext("Triple Whale no aceptó la consulta: %(detalle)s", detalle=texto[:200]))
        ultimo = ErrorConsulta(gettext("Triple Whale respondió %(codigo)s: %(detalle)s",
                                       codigo=codigo, detalle=texto[:200]))
        if codigo >= 500 and intento < REINTENTOS_MAX - 1:
            _dormir(DELAY_REINTENTO * (2 ** intento))
            continue
        raise ultimo
    raise ultimo or ErrorTripleWhale(gettext("Triple Whale no respondió."))


def consultar_con_respaldo(llave_api, shop_id, consultas, desde, hasta, moneda=None, empezar_en=0):
    """Prueba `consultas` en orden (completa, mínima…) y devuelve
    `(filas, indice_que_sirvio)`. Solo un ErrorConsulta pasa a la siguiente:
    llave, tienda, límite y red suben tal cual."""
    ultimo = None
    for i in range(empezar_en, len(consultas)):
        try:
            return sql_query(llave_api, shop_id, consultas[i], desde, hasta, moneda), i
        except ErrorConsulta as e:
            ultimo = e
    raise ultimo or ErrorConsulta(gettext("Ninguna consulta sirvió."))


# ----------------------------------------------------------- consultas ---

# Una fila por (canal, anuncio, día). Los nombres pueden venir en varias filas
# del mismo día (p. ej. un desglose): se agregan con max() y se suman medidas,
# como el ejemplo oficial `SELECT SUM(spend) AS spend, channel FROM ads_table`.
_ADS_COMPLETA = """
SELECT
    channel, ad_id, event_date,
    max(account_id) AS account_id,
    max(campaign_id) AS campaign_id, max(campaign_name) AS campaign_name,
    max(adset_id) AS adset_id, max(adset_name) AS adset_name,
    max(ad_name) AS ad_name, max(ad_status) AS ad_status,
    max(creative_id) AS creative_id, max(video_url) AS video_url, max(destination_url) AS destination_url,
    max(is_utm_valid) AS is_utm_valid,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    SUM(outbound_clicks) AS outbound_clicks,
    SUM(conversions) AS conversions, SUM(conversion_value) AS conversion_value,
    SUM(thruplays) AS thruplays, SUM(three_second_video_view) AS video_3s,
    SUM(video_p25_watched) AS video_p25, SUM(video_p50_watched) AS video_p50,
    SUM(video_p75_watched) AS video_p75, SUM(video_p100_watched) AS video_p100
FROM ads_table
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY channel, ad_id, event_date
"""

_ADS_MINIMA = """
SELECT
    channel, ad_id, event_date,
    max(campaign_name) AS campaign_name, max(adset_name) AS adset_name, max(ad_name) AS ad_name,
    SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
    SUM(conversions) AS conversions, SUM(conversion_value) AS conversion_value,
    SUM(thruplays) AS thruplays
FROM ads_table
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY channel, ad_id, event_date
"""

_PIXEL_COMPLETA = """
SELECT
    channel, ad_id, event_date,
    SUM(orders_quantity) AS orders, SUM(order_revenue) AS revenue,
    SUM(new_customer_orders) AS nc_orders, SUM(new_customer_order_revenue) AS nc_revenue,
    SUM(sessions) AS sessions, SUM(add_to_carts) AS add_to_carts, SUM(checkouts) AS checkouts
FROM pixel_joined_tvf()
WHERE event_date BETWEEN @startDate AND @endDate
    AND model = {modelo} AND attribution_window = {ventana}
GROUP BY channel, ad_id, event_date
"""

_PIXEL_MINIMA = """
SELECT
    channel, ad_id, event_date,
    SUM(orders_quantity) AS orders, SUM(order_revenue) AS revenue, SUM(new_customer_orders) AS nc_orders
FROM pixel_joined_tvf()
WHERE event_date BETWEEN @startDate AND @endDate
    AND model = {modelo} AND attribution_window = {ventana}
GROUP BY channel, ad_id, event_date
"""

_TIENDA_COMPLETA = """
SELECT
    event_date,
    SUM(spend) AS spend, SUM(order_revenue) AS revenue, SUM(orders_count) AS orders,
    SUM(new_customer_orders) AS nc_orders, SUM(new_customer_revenue) AS nc_revenue,
    SUM(refund_money) AS refunds, SUM(cogs) AS cogs
FROM blended_stats_tvf()
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY event_date
"""
# `blended_stats_tvf()` no tiene `net_profit` (comprobado contra happyflops-norge el 2026-10-08, PND-150): pedirla
# hacía caer cada copia a la versión mínima y se perdían los clientes nuevos. La utilidad neta no se pinta en ningún
# lado, así que no se pide ni se inventa con otras columnas; `utilidad_neta` queda en 0.

_TIENDA_MINIMA = """
SELECT event_date, SUM(spend) AS spend, SUM(order_revenue) AS revenue, SUM(orders_count) AS orders
FROM blended_stats_tvf()
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY event_date
"""

# Ventas por producto y día. `products_info` es un arreglo de objetos dentro de cada fila de orders_table; ARRAY JOIN
# lo abre a una fila por línea del pedido. Los nombres de sus campos se leyeron de la tienda real el 2026-10-08
# (PND-150; la versión anterior pedía `title`, `sku`, `quantity` y `price`, que no existen): `product_id`,
# `product_name`, `product_sku`, `variant_id`, `product_name_price` (precio unitario),
# `product_name_quantity_sold` y `net_discount_amount_for_product` (descuento de la línea). La suma de
# precio × cantidad cuadra con `gross_product_sales` de la tienda. La completa resta el descuento (ventas netas por
# producto); la mínima, sin descuento, por si una tienda no lo trae.
_PRODUCTOS_COMPLETA = """
SELECT
    event_date,
    p.product_id AS product_id,
    any(p.product_name) AS title,
    any(p.product_sku) AS sku,
    SUM(p.product_name_quantity_sold) AS quantity,
    SUM(p.product_name_price * p.product_name_quantity_sold - p.net_discount_amount_for_product) AS revenue,
    uniq(order_id) AS orders
FROM orders_table
ARRAY JOIN products_info AS p
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY event_date, p.product_id
"""

_PRODUCTOS_MINIMA = """
SELECT
    event_date,
    p.product_id AS product_id,
    any(p.product_name) AS title,
    any(p.product_sku) AS sku,
    SUM(p.product_name_quantity_sold) AS quantity,
    SUM(p.product_name_price * p.product_name_quantity_sold) AS revenue,
    uniq(order_id) AS orders
FROM orders_table
ARRAY JOIN products_info AS p
WHERE event_date BETWEEN @startDate AND @endDate
GROUP BY event_date, p.product_id
"""

# El anuncio tal cual (spec 2026-10-08-triple-whale-tarjetas-analisis §3.3): miniatura, video, título y copy, una
# fila por anuncio (sin fecha). Probado con la tienda real el 2026-10-08: ad_type, ad_image_url (en
# files.triplewhale.com, no caduca), video_url, ad_title, ad_copy y video_duration llegan; creative_cta_type vino
# vacío. Columnas en https://triplewhale.readme.io/docs/ads-table.md.
_CREATIVOS_COMPLETA = """
SELECT
    channel, ad_id,
    max(ad_type) AS ad_type, max(ad_image_url) AS ad_image_url, max(video_url) AS video_url,
    max(ad_title) AS ad_title, max(ad_copy) AS ad_copy, max(creative_cta_type) AS creative_cta_type,
    max(video_duration) AS video_duration
FROM ads_table
WHERE event_date BETWEEN @startDate AND @endDate AND ad_id IS NOT NULL AND ad_id != ''
GROUP BY channel, ad_id
"""

_CREATIVOS_MINIMA = """
SELECT channel, ad_id, max(ad_type) AS ad_type, max(ad_image_url) AS ad_image_url, max(video_url) AS video_url
FROM ads_table
WHERE event_date BETWEEN @startDate AND @endDate AND ad_id IS NOT NULL AND ad_id != ''
GROUP BY channel, ad_id
"""

_PRUEBA = "SELECT SUM(spend) AS spend FROM ads_table WHERE event_date BETWEEN @startDate AND @endDate"


def consultas_anuncios():
    return [_ADS_COMPLETA, _ADS_MINIMA]


def consultas_pixel(modelo, ventana):
    lit = {"modelo": _literal(normalizar_modelo(modelo), MODELOS),
           "ventana": _literal(normalizar_ventana(ventana), VENTANAS)}
    return [_PIXEL_COMPLETA.format(**lit), _PIXEL_MINIMA.format(**lit)]


def consultas_tienda():
    return [_TIENDA_COMPLETA, _TIENDA_MINIMA]


def consultas_productos():
    return [_PRODUCTOS_COMPLETA, _PRODUCTOS_MINIMA]


def consultas_creativos():
    return [_CREATIVOS_COMPLETA, _CREATIVOS_MINIMA]


# ------------------------------------------------------------ llamadas ---

def validar_llave(llave_api):
    """GET /users/api-keys/me: True si la llave existe y no está revocada."""
    try:
        resp = requests.get(f"{API_BASE}/users/api-keys/me", headers={"x-api-key": llave_api},
                            timeout=TIMEOUT_SEGUNDOS)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def probar(llave_api, shop_id, moneda=None, hoy=None):
    """Una consulta mínima de 7 días: comprueba la llave, el permiso de SQL y
    que la tienda existe para esa llave. Devuelve {"gasto_7d": float}; lanza
    ErrorTripleWhale (o una subclase) con el motivo."""
    hoy = hoy or date.today()
    desde = (hoy - timedelta(days=6)).isoformat()
    filas = sql_query(llave_api, shop_id, _PRUEBA, desde, hoy.isoformat(), moneda)
    gasto = 0.0
    for f in filas:
        gasto += numero(f.get("spend"))
    return {"gasto_7d": round(gasto, 2)}


def numero(valor):
    """ClickHouse manda enteros grandes como texto: todo pasa por aquí."""
    if valor is None or valor == "":
        return 0.0
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v and v not in (float("inf"), float("-inf")) else 0.0
