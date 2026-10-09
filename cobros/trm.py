"""TRM oficial (pesos por dólar) para cobrar en COP lo que se precia en USD
(spec planes 2026-10-09 §6; fuente en docs/pagos/wompi-api.md §12): el
dataset 32sa-8pi3 de datos.gov.co (la TRM de la Superfinanciera), sin llave.

Host fijo, sin seguir redirecciones, 10 s. Se guarda en `kv` (`cobros:trm`,
único escritor este módulo) y se reusa 6 h. Si la lectura falla se usa la
última guardada si se leyó hace ≤ 3 días; si no, `SinTasa` y no se cobra.
Una fila cuya vigencia terminó hace más de 3 días tampoco sirve (el dataset
dejó de actualizarse), ni una tasa fuera de un rango sensato (una tasa 0
regalaría los planes)."""
import datetime as dt
import json
import logging
import math
import time
from urllib.parse import quote

import requests
import sqlalchemy as sa
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

log = logging.getLogger(__name__)

URL = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC"
CLAVE = "cobros:trm"
TIEMPO = 10
CACHE_S = 6 * 3600
RESPALDO_S = 3 * 86400
DIAS_VIGENCIA = 3
MINIMO, MAXIMO = 1000.0, 20000.0   # COP por USD: fuera de esto la fila está mal


class SinTasa(Exception):
    """No hay una TRM de ≤ 3 días: no se cobra (el texto va en palabras)."""


class _Falla(Exception):
    pass


def _ahora():
    return time.time()


def _hoy():
    return dt.date.today()


def _fecha(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _vigente(hasta):
    """¿La vigencia terminó hace ≤ 3 días? (una TRM de fin de semana cubre varios días)."""
    fin = _fecha(hasta)
    return fin is not None and fin >= _hoy() - dt.timedelta(days=DIAS_VIGENCIA)


def _leer_guardada():
    try:
        with db.conectar() as con:
            crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE)).scalar()
        g = json.loads(crudo) if crudo else None
        if not isinstance(g, dict):
            return None
        valor, leida = float(g["valor"]), float(g["leida_en"])
    except (ValueError, TypeError, KeyError):
        return None
    if not (MINIMO <= valor <= MAXIMO):
        return None
    return {"valor": valor, "leida_en": leida, "vigencia_hasta": g.get("vigencia_hasta")}


def _guardar(valor, desde, hasta):
    # Un solo statement (upsert): sin leer-y-escribir no hace falta candado, y la
    # transacción no queda abierta mientras se espera a la red.
    texto = json.dumps({"valor": valor, "leida_en": _ahora(), "vigencia_desde": desde, "vigencia_hasta": hasta})
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(clave=CLAVE, valor=texto, actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"],
                                           set_={"valor": texto, "actualizado_en": db.ahora()}))


def url():
    """La consulta con `$where vigenciadesde <= hoy`: el dataset publica a veces
    la TRM de mañana (o la del lunes un viernes), y esa no es la de hoy."""
    filtro = quote(f"vigenciadesde <= '{_hoy().isoformat()}T00:00:00'", safe="")
    return f"{URL}&$where={filtro}"


def _pedir():
    try:
        r = requests.get(url(), headers={"Accept": "application/json"}, timeout=TIEMPO, allow_redirects=False)
    except requests.RequestException as e:
        raise _Falla(type(e).__name__) from None
    if r.status_code != 200:
        raise _Falla(f"HTTP {r.status_code}")
    try:
        filas = r.json()
    except ValueError:
        raise _Falla("no es JSON") from None
    fila = filas[0] if isinstance(filas, list) and filas and isinstance(filas[0], dict) else None
    if fila is None:
        raise _Falla("sin filas")
    try:
        valor = float(fila["valor"])
    except (KeyError, TypeError, ValueError):
        raise _Falla("valor ilegible") from None
    if not math.isfinite(valor) or not (MINIMO <= valor <= MAXIMO):
        raise _Falla("valor fuera de rango")
    desde, hasta = fila.get("vigenciadesde"), fila.get("vigenciahasta") or fila.get("vigenciadesde")
    inicio = _fecha(desde)
    if inicio is not None and inicio > _hoy():
        raise _Falla("tasa de un día futuro")
    if not _vigente(hasta):
        raise _Falla("tasa vieja")
    return valor, str(desde or "")[:30], str(hasta or "")[:30]


def actual():
    """La TRM (COP por USD) para cobrar ahora. Lanza `SinTasa`."""
    guardada = _leer_guardada()
    ahora = _ahora()
    if guardada and 0 <= ahora - guardada["leida_en"] < CACHE_S and _vigente(guardada["vigencia_hasta"]):
        return guardada["valor"]
    try:
        valor, desde, hasta = _pedir()
    except _Falla as e:
        if (guardada and 0 <= ahora - guardada["leida_en"] <= RESPALDO_S
                and _vigente(guardada["vigencia_hasta"])):
            log.warning("TRM: datos.gov.co falló (%s); uso la guardada", e)
            return guardada["valor"]
        log.warning("TRM: datos.gov.co falló (%s) y no hay una guardada de ≤ 3 días", e)
        raise SinTasa(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos")) from None
    try:
        _guardar(valor, desde, hasta)
    except Exception:  # noqa: BLE001 — no poder guardarla no quita una tasa buena recién leída
        log.exception("TRM: no se pudo guardar la tasa leída; se usa igual")
    return valor
