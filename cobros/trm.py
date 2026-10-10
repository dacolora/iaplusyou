"""TRM oficial (pesos por dólar) para cobrar en COP lo que se precia en USD
(spec planes 2026-10-09 §6; fuente en docs/pagos/wompi-api.md §12): el
dataset 32sa-8pi3 de datos.gov.co (la TRM de la Superfinanciera), sin llave.

Host fijo, sin seguir redirecciones, 10 s. Se guarda en `kv` (`cobros:trm`,
único escritor este módulo) y se reusa 6 h. Si la lectura falla se usa la
última guardada si se leyó hace ≤ 3 días; si no, `SinTasa` y no se cobra.
Una fila cuya vigencia terminó hace más de 3 días tampoco sirve (el dataset
dejó de actualizarse), ni una tasa fuera de 2 500–7 000 COP/USD (una tasa 0
regalaría los planes; una fila mala de 14 800 cobraría 3,7 veces).

Banda (revisión final 2026-10-10, ruling; re-revisión N3): una tasa leída que
se mueve más de ±8 % frente a la última ACEPTADA (la guardada, sea de cuando
sea) no se usa y no se cobra (`SinTasa`): puede ser una fila mala dentro del
rango o un salto real del peso, y eso lo decide una persona. Nunca se acepta
sola. La rechazada se guarda en `kv` `cobros:trm_rechazada` (con la anterior) y
durante 1 h no se vuelve a pedir; el admin la ve en /admin/cobros y la acepta
con «Aceptar la tasa de hoy» (`aceptar`). Sin tasa válida se avisa al admin una
vez por día, y el día se da por avisado solo si el correo salió."""
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
MINIMO, MAXIMO = 2500.0, 7000.0    # COP por USD: fuera de esto la fila está mal (ruling 2026-10-10)
BANDA = 0.08                        # ±8 % frente a la última guardada (de ≤ 3 días): más que eso no se cobra
CLAVE_AVISO = "cobros:aviso_trm:{dia}"
CLAVE_RECHAZADA = "cobros:trm_rechazada"   # la última leída fuera de la banda (único escritor: este módulo)
RECHAZADA_S = 3600                          # durante 1 h no se vuelve a pedir a datos.gov.co


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


def _avisado_hoy(clave):
    try:
        with db.conectar() as con:
            return con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == clave)).first() is not None
    except Exception:  # noqa: BLE001
        return False


def _avisar_admin(motivo):
    """Al admin, una vez por día: no hay una tasa válida y no se está cobrando nada en pesos. El día queda
    avisado solo si salió al menos un correo (N3): si falla, se intenta en la próxima lectura. Fuera de toda
    transacción; nunca lanza."""
    try:
        from cobros import avisos  # noqa: PLC0415
        clave = CLAVE_AVISO.format(dia=_hoy().isoformat())
        if _avisado_hoy(clave):
            return False
        enviados = avisos.admin(
            "trm_sin_tasa",
            lambda: gettext("No hay una tasa de cambio válida: los cobros en pesos están frenados"),
            lambda: gettext("La TRM de datos.gov.co no sirve hoy (%(motivo)s). Mientras tanto no se cobra ninguna "
                            "recarga ni plan en pesos. Si es un salto real del peso, acéptala en /admin/cobros "
                            "(«Aceptar la tasa de hoy»).", motivo=motivo))
        if enviados:
            avisos._marcar_una_vez(clave)
        return bool(enviados)
    except Exception:  # noqa: BLE001
        log.exception("TRM: no se pudo avisar al admin")
        return False


def _guardar_rechazada(valor, desde, hasta, anterior):
    texto = json.dumps({"valor": valor, "leida_en": _ahora(), "vigencia_desde": desde, "vigencia_hasta": hasta,
                        "anterior": anterior})
    try:
        with db.conectar() as con:
            con.execute(insert_sqlite(db.kv).values(clave=CLAVE_RECHAZADA, valor=texto, actualizado_en=db.ahora())
                        .on_conflict_do_update(index_elements=["clave"],
                                               set_={"valor": texto, "actualizado_en": db.ahora()}))
    except Exception:  # noqa: BLE001 — sin guardarla se vuelve a pedir: igual no se cobra
        log.exception("TRM: no se pudo guardar la tasa rechazada")


def _borrar_rechazada():
    with db.conectar() as con:
        con.execute(db.kv.delete().where(db.kv.c.clave == CLAVE_RECHAZADA))


def rechazada():
    """La última tasa leída que se rechazó por la banda (para /admin/cobros), o None:
    {valor, anterior, vigencia_desde, vigencia_hasta, leida_en}. Solo lee; nunca lanza."""
    try:
        with db.conectar() as con:
            crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_RECHAZADA)).scalar()
        r = json.loads(crudo) if crudo else None
        if not isinstance(r, dict):
            return None
        r["valor"], r["leida_en"] = float(r["valor"]), float(r["leida_en"])
        return r
    except (ValueError, TypeError, KeyError):
        return None


def aceptar(valor, usuario):
    """El admin acepta la tasa rechazada (un salto real del peso): queda como la guardada y se vuelve a cobrar.
    `valor` tiene que ser exactamente la rechazada que vio en la pantalla y estar en el rango. Lanza
    ValueError en palabras."""
    r = rechazada()
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        raise ValueError(gettext("No hay una tasa rechazada para aceptar.")) from None
    if r is None or valor != r["valor"]:
        raise ValueError(gettext("No hay una tasa rechazada para aceptar."))
    if not (MINIMO <= valor <= MAXIMO):
        raise ValueError(gettext("Esa tasa está fuera del rango posible y no se puede aceptar."))
    _guardar(valor, str(r.get("vigencia_desde") or "")[:30], str(r.get("vigencia_hasta") or "")[:30])
    _borrar_rechazada()
    log.info("TRM %s aceptada a mano por %s (la anterior era %s)", valor, usuario, r.get("anterior"))
    return valor


def _sin_tasa(motivo):
    _avisar_admin(motivo)
    return SinTasa(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos"))


def actual():
    """La TRM (COP por USD) para cobrar ahora. Lanza `SinTasa`."""
    guardada = _leer_guardada()
    ahora = _ahora()
    if guardada and 0 <= ahora - guardada["leida_en"] < CACHE_S and _vigente(guardada["vigencia_hasta"]):
        return guardada["valor"]
    reciente = bool(guardada and 0 <= ahora - guardada["leida_en"] <= RESPALDO_S)
    previa = rechazada()
    if previa and 0 <= ahora - previa["leida_en"] < RECHAZADA_S:
        # Se rechazó hace menos de 1 h: no se vuelve a pedir y no se usa la vieja (N3).
        raise SinTasa(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos"))
    try:
        valor, desde, hasta = _pedir()
    except _Falla as e:
        if previa:
            # Hay una tasa de hoy rechazada por la banda sin resolver (R2): la aceptada vieja no vale como
            # respaldo; no se cobra hasta que el admin la acepte o una lectura nueva pase la banda.
            log.warning("TRM: datos.gov.co falló (%s) y hay una tasa rechazada sin aceptar; no se cobra", e)
            raise SinTasa(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos")) from None
        if reciente and _vigente(guardada["vigencia_hasta"]):
            log.warning("TRM: datos.gov.co falló (%s); uso la guardada", e)
            return guardada["valor"]
        log.warning("TRM: datos.gov.co falló (%s) y no hay una guardada de ≤ 3 días", e)
        raise _sin_tasa(str(e)) from None
    if guardada and abs(valor / guardada["valor"] - 1) > BANDA:
        # Ni la nueva ni la vieja: una de las dos está mal por más de 8 % y eso lo decide una persona, sin
        # importar cuánto hace que se aceptó la vieja (N3: nunca se acepta sola).
        log.warning("TRM: la tasa leída (%s) se mueve más de ±8 %% frente a la aceptada (%s); no se cobra",
                    valor, guardada["valor"])
        _guardar_rechazada(valor, desde, hasta, guardada["valor"])
        raise _sin_tasa(f"{valor} frente a {guardada['valor']}")
    if previa:
        try:
            _borrar_rechazada()   # la de hoy volvió a la banda: ya no hay nada que aceptar
        except Exception:  # noqa: BLE001
            log.exception("TRM: no se pudo borrar la tasa rechazada")
    try:
        _guardar(valor, desde, hasta)
    except Exception:  # noqa: BLE001 — no poder guardarla no quita una tasa buena recién leída
        log.exception("TRM: no se pudo guardar la tasa leída; se usa igual")
    return valor
