"""Copia las métricas de Triple Whale a la base (spec 2026-09-28 §4).

Al conectar: los últimos `DIAS_BACKFILL` días. Después (periódica cada 2 h,
y antes de refrescar un experimento atribuido a Triple Whale): los últimos
`DIAS_RECIENTES` días — o desde la última sincronización si el worker estuvo
parado más tiempo —, porque Triple Whale reatribuye pedidos a clics viejos.

El rango se pide en tramos de `DIAS_TRAMO` días ("Split wide date ranges into
smaller chunks", guía de errores) y por cada tramo van tres consultas:
anuncios (lo que reporta cada plataforma), Pixel (lo atribuido con el modelo
y la ventana del proyecto) y tienda. Cada una tiene versión completa y mínima
(`triple_whale.consultar_con_respaldo`); si la mínima del Pixel o de la
tienda tampoco sirve, la sincronización sigue sin esa parte y lo avisa: los
anuncios nunca se pierden por eso. Llave, tienda, límite y red sí cortan la
sincronización (la tarea marca la conexión en error y la cola reintenta).
"""
import re
from datetime import date, datetime, timedelta

from flask_babel import gettext

import db
import triple_whale
import triple_whale_tiendas
from triple_whale import datos

DIAS_BACKFILL = 90
DIAS_RECIENTES = 7
DIAS_TRAMO = 7
MINUTOS_FRESCO = 30
_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOMBRES_CONSULTA = ("completa", "minima")


# ------------------------------------------------------- normalizar ---

def _fecha(valor):
    f = str(valor or "")[:10]
    return f if _RE_FECHA.match(f) else None


def _texto(valor, largo=None):
    t = "" if valor is None else str(valor).strip()
    return (t[:largo] if largo else t) or None


def _entero(valor):
    return int(round(triple_whale.numero(valor)))


def _real(valor):
    return round(triple_whale.numero(valor), 4)


def _booleano(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "t", "yes")
    return bool(triple_whale.numero(valor))


def _clave(fila):
    ad_id = _texto(fila.get("ad_id"), 64)
    fecha = _fecha(fila.get("event_date"))
    if not ad_id or not fecha or ad_id.lower() in ("null", "none", "0"):
        return None
    return {"canal": _texto(fila.get("channel"), 40) or "desconocido", "ad_id": ad_id, "fecha": fecha}


def normalizar_anuncio(fila):
    """Fila de ads_table -> registro de tw_anuncio_dia (None si no tiene
    anuncio o fecha: filas de canal sin desglose por anuncio)."""
    r = _clave(fila)
    if r is None:
        return None
    for destino, origen, largo in (("cuenta_id", "account_id", 64), ("campana_id", "campaign_id", 64),
                                   ("campana", "campaign_name", 300), ("conjunto_id", "adset_id", 64),
                                   ("conjunto", "adset_name", 300), ("anuncio", "ad_name", 300),
                                   ("estado_anuncio", "ad_status", 30), ("creative_id", "creative_id", 64),
                                   ("video_url", "video_url", 2000), ("destino_url", "destination_url", 2000)):
        if origen in fila:
            r[destino] = _texto(fila.get(origen), largo)
    if "is_utm_valid" in fila:
        r["utm_ok"] = _booleano(fila.get("is_utm_valid"))
    r["gasto"] = _real(fila.get("spend"))
    r["compras_canal"] = _real(fila.get("conversions"))
    r["valor_canal"] = _real(fila.get("conversion_value"))
    for destino, origen in (("impresiones", "impressions"), ("clics", "clicks"), ("clics_salida", "outbound_clicks"),
                            ("thruplays", "thruplays"), ("vistas_3s", "video_3s"), ("p25", "video_p25"),
                            ("p50", "video_p50"), ("p75", "video_p75"), ("p100", "video_p100")):
        r[destino] = _entero(fila.get(origen))
    return r


def normalizar_pixel(fila):
    r = _clave(fila)
    if r is None:
        return None
    r.update(pedidos=_real(fila.get("orders")), ingresos=_real(fila.get("revenue")),
             nc_pedidos=_real(fila.get("nc_orders")), nc_ingresos=_real(fila.get("nc_revenue")),
             sesiones=_entero(fila.get("sessions")), carritos=_entero(fila.get("add_to_carts")),
             checkouts=_entero(fila.get("checkouts")))
    return r


def normalizar_tienda(fila):
    fecha = _fecha(fila.get("event_date"))
    if not fecha:
        return None
    return {"fecha": fecha, "gasto": _real(fila.get("spend")), "ingresos": _real(fila.get("revenue")),
            "pedidos": _real(fila.get("orders")), "nc_pedidos": _real(fila.get("nc_orders")),
            "nc_ingresos": _real(fila.get("nc_revenue")), "reembolsos": _real(fila.get("refunds")),
            "cogs": _real(fila.get("cogs")), "utilidad_neta": _real(fila.get("net_profit"))}


def _sumar_por_clave(registros, claves_suma):
    """Dos filas con la misma clave (canal, anuncio, día) se suman: la
    consulta ya agrupa, pero un `ad_id` numérico y uno de texto pueden
    normalizarse al mismo."""
    salida = {}
    for r in registros:
        if r is None:
            continue
        k = (r["canal"], r["ad_id"], r["fecha"])
        if k not in salida:
            salida[k] = dict(r)
            continue
        previo = salida[k]
        for c in claves_suma:
            previo[c] = (previo.get(c) or 0) + (r.get(c) or 0)
    return list(salida.values())


# ------------------------------------------------------------ rangos ---

def tramos(desde, hasta, dias=DIAS_TRAMO):
    """[(desde, hasta)] consecutivos de `dias` días (el último puede ser más corto)."""
    d, h = date.fromisoformat(desde), date.fromisoformat(hasta)
    salida = []
    while d <= h:
        fin = min(h, d + timedelta(days=dias - 1))
        salida.append((d.isoformat(), fin.isoformat()))
        d = fin + timedelta(days=1)
    return salida


def rango_pendiente(config, hoy):
    """(desde, hasta) de la próxima sincronización: todo el backfill si nunca
    se hizo; si no, los últimos DIAS_RECIENTES días, o desde dos días antes
    de la última sincronización si fue hace más (worker parado)."""
    inicio_backfill = hoy - timedelta(days=DIAS_BACKFILL - 1)
    extra = config.get("extra") or {}
    if not extra.get("backfill_desde"):
        return inicio_backfill.isoformat(), hoy.isoformat()
    desde = hoy - timedelta(days=DIAS_RECIENTES - 1)
    ultima = _fecha(config.get("ultima_sincronizacion"))
    if ultima:
        desde = min(desde, date.fromisoformat(ultima) - timedelta(days=2))
    return max(desde, inicio_backfill).isoformat(), hoy.isoformat()


def esta_fresca(config, minutos=MINUTOS_FRESCO, ahora=None):
    ultima = (config or {}).get("ultima_sincronizacion")
    if not ultima or not (config.get("extra") or {}).get("backfill_desde"):
        return False
    try:
        return datetime.fromisoformat(ultima) + timedelta(minutes=minutos) > (ahora or datetime.now())
    except ValueError:
        return False


# -------------------------------------------------------- sincronizar ---

def sincronizar(cliente, desde=None, hasta=None, on_progreso=None, hoy=None):
    """Trae [desde, hasta] (por defecto `rango_pendiente`) y lo guarda.
    Devuelve el resumen que queda en `triple_whale.extra.ultimo_resumen`.
    Lanza ErrorTripleWhale (o subclase) si la llave, la tienda o la red fallan."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        raise triple_whale.ErrorTripleWhale(gettext("Triple Whale no está conectado en este proyecto."))
    llave = triple_whale_tiendas.obtener_llave(cliente)
    if not llave:
        raise triple_whale.ErrorLlave(gettext("No hay llave de Triple Whale guardada. Vuelve a conectarlo."))
    hoy = hoy or date.today()
    if desde is None or hasta is None:
        desde, hasta = rango_pendiente(config, hoy)
    dominio, moneda = config["dominio_tienda"], config["moneda"]
    consultas_pixel = triple_whale.consultas_pixel(config["modelo_atribucion"], config["ventana_atribucion"])
    indice = {"anuncios": 0, "pixel": 0, "tienda": 0}
    fallo = {"pixel": None, "tienda": None}
    cuenta = {"anuncios": set(), "filas_pixel": 0, "dias_tienda": 0}
    lista = tramos(desde, hasta)
    for i, (d, h) in enumerate(lista):
        if on_progreso:
            on_progreso(i, len(lista), d, h)
        filas, indice["anuncios"] = triple_whale.consultar_con_respaldo(
            llave, dominio, triple_whale.consultas_anuncios(), d, h, moneda, empezar_en=indice["anuncios"])
        registros = _sumar_por_clave((normalizar_anuncio(f) for f in filas), datos.COLUMNAS_CANAL)
        datos.reemplazar_anuncios_canal(cliente, d, h, registros)
        cuenta["anuncios"].update((r["canal"], r["ad_id"]) for r in registros)

        if fallo["pixel"] is None:
            try:
                filas, indice["pixel"] = triple_whale.consultar_con_respaldo(
                    llave, dominio, consultas_pixel, d, h, moneda, empezar_en=indice["pixel"])
                registros = _sumar_por_clave((normalizar_pixel(f) for f in filas), datos.COLUMNAS_PIXEL)
                datos.reemplazar_anuncios_pixel(cliente, d, h, registros)
                cuenta["filas_pixel"] += len(registros)
            except triple_whale.ErrorConsulta as e:
                fallo["pixel"] = str(e)

        if fallo["tienda"] is None:
            try:
                filas, indice["tienda"] = triple_whale.consultar_con_respaldo(
                    llave, dominio, triple_whale.consultas_tienda(), d, h, moneda, empezar_en=indice["tienda"])
                registros = [r for r in (normalizar_tienda(f) for f in filas) if r]
                datos.reemplazar_tienda(cliente, d, h, registros)
                cuenta["dias_tienda"] += len(registros)
            except triple_whale.ErrorConsulta as e:
                fallo["tienda"] = str(e)

    resumen = {
        "desde": desde, "hasta": hasta, "tramos": len(lista), "anuncios": len(cuenta["anuncios"]),
        "filas_pixel": cuenta["filas_pixel"], "dias_tienda": cuenta["dias_tienda"],
        "consultas": {k: ("sin_datos" if fallo.get(k) else NOMBRES_CONSULTA[v]) for k, v in indice.items()},
        "fallos": {k: v for k, v in fallo.items() if v},
    }
    previo = (config.get("extra") or {}).get("backfill_desde")
    triple_whale_tiendas.actualizar(cliente, estado="conectada", error=None, ultima_sincronizacion=db.ahora())
    triple_whale_tiendas.actualizar_extra(cliente, {"backfill_desde": min(filter(None, (previo, desde))),
                                                    "ultimo_resumen": resumen})
    return resumen


def sincronizar_si_hace_falta(cliente, minutos=MINUTOS_FRESCO):
    """Sincroniza solo si lo copiado tiene más de `minutos`. None si no hizo nada."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config or esta_fresca(config, minutos):
        return None
    return sincronizar(cliente)
