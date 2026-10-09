"""USD por unidad de cada moneda, por día (spec §7). Fuente: el BCE vía
frankfurter (gratis, sin llave). Único escritor de `tasa_cambio`.

Un día sin publicación (fin de semana, festivo) usa el último publicado
anterior, pero solo hasta 4 días después (ruling R24 de la revisión final,
2026-10-08: un fin de semana con festivo); más allá el valor es None. Sin tasa
conocida la pantalla dice «USD no disponible», nunca una tasa inventada ni una
de hace semanas.

Lo que llega de frankfurter se trata como ajeno: se lee como mucho 1 MB, cada
fecha tiene que ser una fecha de verdad y una tasa que se aleja más de 3 veces
de la anterior guardada de esa moneda se descarta con un aviso (un error de la
fuente no debe multiplicar los montos en USD de toda la pestaña)."""
import json
import logging
import math
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
DIAS_RELLENO_MAX = 4          # un día sin tasa usa la anterior si es de hace 4 días o menos
MAX_BYTES_RESPUESTA = 1024 * 1024
SALTO_MAXIMO = 3.0            # una tasa nueva no puede ser más de 3 veces (ni menos de un tercio) la anterior


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


def _last_weekday(check_date):
    """Retorna ISO string de último día laboral ≤ check_date."""
    if check_date.weekday() < 5:
        return check_date.isoformat()
    else:
        return (check_date - timedelta(days=check_date.weekday() - 4)).isoformat()


def _leer_json(resp):
    """El cuerpo JSON de la respuesta, leído en trozos y con tope de 1 MB (ValueError si pasa)."""
    trozos, total = [], 0
    for trozo in resp.iter_content(chunk_size=65536):
        if not trozo:
            continue
        total += len(trozo)
        if total > MAX_BYTES_RESPUESTA:
            raise ValueError("respuesta de más de 1 MB")
        trozos.append(trozo)
    return json.loads(b"".join(trozos) or b"{}")


def _anterior(moneda, fecha):
    """La última tasa guardada de esa moneda ANTES de `fecha`, o None."""
    with db.conectar() as con:
        return con.execute(sa.select(db.tasa_cambio.c.usd_por_unidad).where(
            db.tasa_cambio.c.moneda == moneda, db.tasa_cambio.c.fecha < fecha).order_by(
            db.tasa_cambio.c.fecha.desc()).limit(1)).scalar()


def _filas_validas(moneda, rates):
    """Las filas a guardar de un `rates` de frankfurter: fechas de verdad, tasas finitas y positivas, y ninguna que
    salte más de 3 veces respecto de la anterior (la guardada antes del rango, o la mediana de lo que llegó si no hay
    ninguna guardada). Lo que se descarta deja un aviso en el registro."""
    por_fecha = {}
    for f, v in (rates or {}).items():
        try:
            fecha = date.fromisoformat(str(f)).isoformat()
            usd_val = float(v["USD"]) if isinstance(v, dict) and "USD" in v else None
        except (ValueError, TypeError):
            continue
        # Ni 0, ni negativas, ni NaN o infinito.
        if usd_val is not None and usd_val > 0 and math.isfinite(usd_val):
            por_fecha[fecha] = usd_val
    if not por_fecha:
        return []
    fechas = sorted(por_fecha)
    referencia = _anterior(moneda, fechas[0])
    if referencia is None:
        valores = sorted(por_fecha.values())
        referencia = valores[len(valores) // 2]
    filas = []
    for fecha in fechas:
        v = por_fecha[fecha]
        if v > referencia * SALTO_MAXIMO or v < referencia / SALTO_MAXIMO:
            log.warning("tasas %s %s: %.6g se aleja más de %sx de %.6g; no se guarda", moneda, fecha, v,
                        SALTO_MAXIMO, referencia)
            continue
        filas.append({"fecha": fecha, "moneda": moneda, "usd_por_unidad": v, "fuente": "bce", "creado_en": db.ahora()})
        referencia = v
    return filas


def asegurar(monedas, desde, hasta, hoy=None):
    """Pide al BCE lo que falte del rango. Nunca lanza (las métricas se ven igual, sin USD)."""
    hoy = hoy or date.today()

    # Wrap date parsing in try-except (catch both ValueError and TypeError)
    try:
        desde_d = date.fromisoformat(desde)
        hasta_d = date.fromisoformat(hasta)
    except (ValueError, TypeError) as e:
        log.warning("tasas parse dates: %s", type(e).__name__)
        return

    # Wrap monedas normalization in guard (monedas None o no iterable; los elementos que no son texto se ignoran)
    try:
        monedas_set = {m.strip().upper() for m in monedas if isinstance(m, str)} - {"", "USD"}
    except TypeError as e:
        log.warning("tasas monedas: %s", type(e).__name__)
        return

    desde_buffer = (desde_d - timedelta(days=_HOLGURA_DIAS)).isoformat()

    for m in sorted(monedas_set):
        # Validar moneda
        if not re.fullmatch(r"[A-Z]{3}", m):
            continue

        # Wrap entire per-currency body in try-except
        try:
            # Determinar objetivo (ISO string): último día laboral ≤ (hasta si hasta < hoy, else hoy-1)
            check_date = hasta_d if hasta_d < hoy else hoy - timedelta(days=1)
            objetivo = _last_weekday(check_date)

            # Determinar inicio (ISO string): min(último día laboral ≤ desde, objetivo)
            last_weekday_desde = _last_weekday(desde_d)
            inicio = min(last_weekday_desde, objetivo)

            # Verificar caché negativo
            clave = (m, objetivo)
            if clave in _intentos and monotonic() - _intentos[clave] < _ESPERA_S:
                continue

            # Verificar si ya tenemos datos suficientes
            ya = _guardadas(m, desde_buffer, hasta)
            if ya:
                ya_keys = sorted(ya.keys())
                tiene_antes_inicio = any(f <= inicio for f in ya_keys)
                tiene_objetivo_o_despues = max(ya_keys) >= objetivo
                if tiene_antes_inicio and tiene_objetivo_o_despues:
                    continue

            # Intentar fetch
            resp = url_conector.abrir(f"{URL_BASE}/{desde_buffer}..{hasta_d.isoformat()}?from={m}&to=USD")
            try:
                datos = _leer_json(resp) if resp.status_code == 200 else {}
            except ValueError as e:  # más de 1 MB, o no es JSON: no se insiste durante 6 horas
                log.warning("tasas %s: respuesta inválida (%s)", m, type(e).__name__)
                _intentos[clave] = monotonic()
                continue
            finally:
                getattr(resp, "close", lambda: None)()

            if resp.status_code != 200:
                log.warning("tasas %s: %s", m, resp.status_code)
                _intentos[clave] = monotonic()
                continue

            # Parsear y guardar
            rates = datos.get("rates") if isinstance(datos, dict) else None
            filas = _filas_validas(m, rates if isinstance(rates, dict) else {})

            if not filas:
                _intentos[clave] = monotonic()
                continue

            # Guardar
            with db.conectar() as con:
                for fila in filas:
                    con.execute(insert_sqlite(db.tasa_cambio).values(**fila).on_conflict_do_update(
                        index_elements=["fecha", "moneda"], set_={"usd_por_unidad": fila["usd_por_unidad"]}))

            # Verificar si alcanzamos objetivo (si nueva tasa < objetivo, set negative cache)
            max_fecha = max(f["fecha"] for f in filas)
            if max_fecha < objetivo:
                _intentos[clave] = monotonic()

        except Exception as e:
            log.warning("tasas %s: %s", m, type(e).__name__)
            continue


def mapa(moneda, desde, hasta):
    """{fecha: usd_por_unidad|None} para cada día del rango. Un día sin tasa publicada toma la última anterior si es
    de hace `DIAS_RELLENO_MAX` días o menos (fin de semana, festivo); si no, None."""
    moneda = (moneda or "").upper()
    if moneda == "USD":
        return {d: 1.0 for d in _dias(desde, hasta)}
    desde_buffer = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()
    guardadas = _guardadas(moneda, desde_buffer, hasta)
    salida, ultima, edad = {}, None, None
    for d in _dias(desde_buffer, hasta):
        if d in guardadas:
            ultima, edad = guardadas[d], 0
        elif edad is not None:
            edad += 1
        if d >= desde:
            salida[d] = ultima if edad is not None and edad <= DIAS_RELLENO_MAX else None
    return salida


def usd(moneda, fecha):
    return mapa(moneda, fecha, fecha).get(fecha)
