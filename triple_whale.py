"""Triple Whale API client para métricas y atribución de anuncios.

API: POST /orcabase/api/sql (Data Out)
Autenticación: x-api-key (por usuario, todas sus tiendas)
Tienda: shopId en cada petición (ej: example.myshopify.com)
Tablas: ads_table (Meta channel-reported), pixel_joined_tvf (atribuido por Pixel)
Límites: 100 req/s, 600 req/min; Retry-After en 429
"""
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

API_BASE = "https://api.triplewhale.com/api/v2"
TIMEOUT_SEGUNDOS = 30
REINTENTOS_MAX = 3
DELAY_REINTENTO = 1.0  # segundos


class ErrorTripleWhale(Exception):
    """Error en la API de Triple Whale."""
    pass


class ErrorCifrado(Exception):
    """No se pudo descifrar la llave."""
    pass


def sql_query(llave_api: str, shop_id: str, consulta: str, parametros: Optional[Dict] = None) -> List[Dict]:
    """Ejecuta una consulta SQL contra Triple Whale (ads_table, pixel_joined_tvf, etc).
    
    Args:
        llave_api: x-api-key del usuario.
        shop_id: Dominio de la tienda (ej: example.myshopify.com).
        consulta: SQL sabor ClickHouse.
        parametros: Dict de @nombre -> valor (ej: {"@startDate": "2026-01-01"}).
    
    Returns:
        Lista de dicts (filas).
    
    Raises:
        ErrorTripleWhale: Si falla la consulta.
    """
    payload = {"shopId": shop_id, "query": consulta}
    if parametros:
        payload["parameters"] = parametros
    
    for intento in range(REINTENTOS_MAX):
        try:
            resp = requests.post(
                f"{API_BASE}/orcabase/api/sql",
                headers={"x-api-key": llave_api, "Content-Type": "application/json"},
                json=payload,
                timeout=TIMEOUT_SEGUNDOS,
            )
            if resp.status_code == 200:
                return resp.json().get("rows", [])
            elif resp.status_code == 429:
                wait_secs = float(resp.headers.get("Retry-After", DELAY_REINTENTO * (2 ** intento)))
                if intento < REINTENTOS_MAX - 1:
                    time.sleep(wait_secs)
                    continue
                raise ErrorTripleWhale(f"Límite de tasa: espera {wait_secs}s")
            elif resp.status_code == 401:
                raise ErrorTripleWhale("Llave inválida, revocada o sin scope Data Out")
            elif resp.status_code == 403:
                raise ErrorTripleWhale(f"Acceso denegado: tienda no accesible o shopId mal formado ({shop_id})")
            elif resp.status_code == 500 and "Unrecognized shop identifier" in resp.text:
                raise ErrorTripleWhale(f"Tienda no reconocida: {shop_id}")
            else:
                raise ErrorTripleWhale(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.Timeout:
            if intento < REINTENTOS_MAX - 1:
                time.sleep(DELAY_REINTENTO * (2 ** intento))
                continue
            raise ErrorTripleWhale(f"Timeout tras {REINTENTOS_MAX} intentos")
        except requests.RequestException as e:
            raise ErrorTripleWhale(f"Error de red: {e}")


def metricas_por_anuncio(llave_api: str, shop_id: str, fecha_desde: str, fecha_hasta: str,
                         modelo: str = "Triple Attribution", ventana: str = "lifetime") -> List[Dict]:
    """Métricas de anuncios Meta por día (ads_table + pixel_joined_tvf).
    
    Retorna filas con: channel, ad_id, event_date, account_id, account_name, campaign_name,
    adset_name, ad_name, spend, impressions, clicks, thruplay, conversions, conversion_value,
    (pixel) pixel_roas, pixel_cpa, new_customer_orders, [country si aplica].
    
    Args:
        llave_api, shop_id, fecha_desde, fecha_hasta (ISO: YYYY-MM-DD).
        modelo: atribución (ej: "Triple Attribution", "Last Click 7d", "Linear Paid 7d").
        ventana: "lifetime" o periodo fijo.
    """
    consulta = """
    SELECT
        ads.channel,
        ads.ad_id,
        ads.event_date,
        ads.account_id,
        ads.account_name,
        ads.campaign_name,
        ads.adset_name,
        ads.ad_name,
        ads.spend,
        ads.impressions,
        ads.clicks,
        ads.thruplay,
        ads.conversions,
        ads.conversion_value,
        coalesce(pixel.pixel_roas, 0) AS pixel_roas,
        coalesce(pixel.pixel_cpa, 0) AS pixel_cpa,
        coalesce(pixel.new_customer_orders, 0) AS new_customer_orders,
        ads.country
    FROM ads_table AS ads
    LEFT JOIN pixel_joined_tvf AS pixel
        ON ads.ad_id = pixel.ad_id
        AND ads.event_date = pixel.event_date
        AND pixel.model = @modelo
        AND pixel.attribution_window = @ventana
    WHERE ads.channel = 'facebook-ads'
        AND ads.event_date BETWEEN @startDate AND @endDate
    ORDER BY ads.event_date DESC, ads.ad_id
    """
    
    parametros = {
        "@startDate": fecha_desde,
        "@endDate": fecha_hasta,
        "@modelo": modelo,
        "@ventana": ventana,
    }
    
    return sql_query(llave_api, shop_id, consulta, parametros)


def validar_llave(llave_api: str) -> bool:
    """Comprueba que la llave es válida (GET /users/api-keys/me).
    
    Returns True si es válida; False si es inválida/revocada.
    """
    try:
        resp = requests.get(
            f"{API_BASE}/users/api-keys/me",
            headers={"x-api-key": llave_api},
            timeout=TIMEOUT_SEGUNDOS,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False
