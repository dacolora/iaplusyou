"""USD por unidad de cada moneda, por día (spec §7). Fuente: el BCE vía
frankfurter (gratis, sin llave). Único escritor de `tasa_cambio`.

Un día sin publicación (fin de semana, festivo) usa el último publicado
anterior. Sin tasa conocida el valor es None: la pantalla dice «USD no
disponible», nunca una tasa inventada."""
import logging
import re
from datetime import date, timedelta
from time import monotonic

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from conectores import url as url_conector

log = logging.getLogger("creatv.meta_rendimiento.tasas")
URL_BASE = "https://api.frankfurter.dev/v1"
_HOLGURA_DIAS = 7   # para encontrar la tasa anterior a un lunes o a un festivo
_ESPERA_S = 6 * 3600  # no re-fetch same (moneda, objetivo) for 6 hours
_intentos = {}  # {(moneda, objetivo): monotonic_time}


def _reiniciar_cache():
    """Limpia el caché negativo (para pruebas)."""
    global _intentos
    _intentos = {}


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


def asegurar(monedas, desde, hasta, hoy=None):
    """Pide al BCE lo que falte del rango. Nunca lanza (las métricas se ven igual, sin USD)."""
    hoy = hoy or date.today()
    inicio = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()

    for m in sorted({(s or "").upper() for s in monedas} - {"", "USD"}):
        # Validar moneda
        if not re.fullmatch(r"[A-Z]{3}", m):
            continue

        # Determinar objetivo (última fecha laboral que necesitamos)
        hasta_d = date.fromisoformat(hasta)
        check_date = hasta_d if hasta_d < hoy else hoy - timedelta(days=1)
        if check_date.weekday() < 5:
            objetivo = check_date
        else:
            objetivo = check_date - timedelta(days=check_date.weekday() - 4)

        # Determinar primer día laboral ≥ desde
        primero = None
        for d in _dias(desde, hasta):
            if date.fromisoformat(d).weekday() < 5:
                primero = d
                break

        # Si no hay labor days, nada que traer
        if not primero or date.fromisoformat(primero) > objetivo:
            continue

        # Verificar caché negativo
        clave = (m, objetivo)
        if clave in _intentos and monotonic() - _intentos[clave] < _ESPERA_S:
            continue

        # Verificar si ya tenemos datos suficientes
        ya = _guardadas(m, inicio, hasta)
        if ya:
            ya_keys = sorted(ya.keys())
            tiene_antes_primero = any(f <= primero for f in ya_keys)
            tiene_objetivo_o_despues = max(ya_keys) >= objetivo
            if tiene_antes_primero and tiene_objetivo_o_despues:
                continue

        # Intentar fetch
        try:
            resp = url_conector.abrir(f"{URL_BASE}/{inicio}..{hasta}?from={m}&to=USD")
            try:
                datos = resp.json() if resp.status_code == 200 else {}
            finally:
                getattr(resp, "close", lambda: None)()

            if resp.status_code != 200:
                log.warning("tasas %s: %s", m, resp.status_code)
                _intentos[clave] = monotonic()
                continue

            # Parsear y guardar (DENTRO del try para capturar errores de JSON)
            filas = []
            for f, v in ((datos or {}).get("rates") or {}).items():
                if isinstance(v, dict) and "USD" in v:
                    try:
                        usd_val = float(v["USD"])
                        filas.append({"fecha": f, "moneda": m, "usd_por_unidad": usd_val, "fuente": "bce",
                                    "creado_en": db.ahora()})
                    except (ValueError, TypeError):
                        # Tasa no-numérica, skip this date
                        continue

            if not filas:
                _intentos[clave] = monotonic()
                continue

            # Guardar
            with db.conectar() as con:
                for fila in filas:
                    con.execute(insert_sqlite(db.tasa_cambio).values(**fila).on_conflict_do_update(
                        index_elements=["fecha", "moneda"], set_={"usd_por_unidad": fila["usd_por_unidad"]}))

            # Verificar si alcanzamos objetivo
            if filas:
                max_fecha = max(f["fecha"] for f in filas)
                if max_fecha < objetivo:
                    _intentos[clave] = monotonic()

        except Exception as e:
            log.warning("tasas %s: %s", m, type(e).__name__)
            _intentos[clave] = monotonic()
            continue


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
