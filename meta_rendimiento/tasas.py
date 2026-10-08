"""USD por unidad de cada moneda, por día (spec §7). Fuente: el BCE vía
frankfurter (gratis, sin llave). Único escritor de `tasa_cambio`.

Un día sin publicación (fin de semana, festivo) usa el último publicado
anterior. Sin tasa conocida el valor es None: la pantalla dice «USD no
disponible», nunca una tasa inventada."""
import logging
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from conectores import url as url_conector

log = logging.getLogger("creatv.meta_rendimiento.tasas")
URL_BASE = "https://api.frankfurter.dev/v1"
_HOLGURA_DIAS = 7   # para encontrar la tasa anterior a un lunes o a un festivo


def _dias(desde, hasta):
    d, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    while d <= fin:
        yield d.isoformat()
        d += timedelta(days=1)


def _guardadas(moneda, desde, hasta):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.tasa_cambio.c.fecha, db.tasa_cambio.c.usd_por_unidad).where(
            db.tasa_cambio.c.moneda == moneda, db.tasa_cambio.c.fecha >= desde,
            db.tasa_cambio.c.fecha <= hasta).order_by(db.tasa_cambio.c.fecha)).all()
    return {f.fecha: f.usd_por_unidad for f in filas}


def asegurar(monedas, desde, hasta):
    """Pide al BCE lo que falte del rango. Nunca lanza (las métricas se ven igual, sin USD)."""
    inicio = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()
    for moneda in sorted({(m or "").upper() for m in monedas} - {"", "USD"}):
        ya = _guardadas(moneda, inicio, hasta)
        laborables = [d for d in _dias(desde, hasta) if date.fromisoformat(d).weekday() < 5]
        if ya and all(d in ya for d in laborables[:-1]):
            continue
        try:
            resp = url_conector.abrir(f"{URL_BASE}/{inicio}..{hasta}?from={moneda}&to=USD")
            try:
                datos = resp.json() if resp.status_code == 200 else {}
            finally:
                getattr(resp, "close", lambda: None)()
        except (url_conector.ErrorConector, ValueError) as e:
            log.warning("tasas %s: %s", moneda, type(e).__name__)
            continue
        filas = [{"fecha": f, "moneda": moneda, "usd_por_unidad": float(v["USD"]), "fuente": "bce",
                  "creado_en": db.ahora()}
                 for f, v in ((datos or {}).get("rates") or {}).items() if isinstance(v, dict) and v.get("USD")]
        if not filas:
            continue
        with db.conectar() as con:
            for fila in filas:
                con.execute(insert_sqlite(db.tasa_cambio).values(**fila).on_conflict_do_update(
                    index_elements=["fecha", "moneda"], set_={"usd_por_unidad": fila["usd_por_unidad"]}))


def mapa(moneda, desde, hasta):
    """{fecha: usd_por_unidad|None} para cada día del rango."""
    moneda = (moneda or "").upper()
    if moneda == "USD":
        return {d: 1.0 for d in _dias(desde, hasta)}
    inicio = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()
    guardadas = _guardadas(moneda, inicio, hasta)
    salida, ultima = {}, None
    for d in _dias(inicio, hasta):
        ultima = guardadas.get(d, ultima)
        if d >= desde:
            salida[d] = ultima
    return salida


def usd(moneda, fecha):
    return mapa(moneda, fecha, fecha).get(fecha)
