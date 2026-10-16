"""PND-341 (decisión 2026-10-15, el gemelo de PND-304 b): un pago de plan APROBADO que Wompi anula después (un
contracargo, una anulación desde su panel) solo se sabía por su evento firmado; si ese evento se perdía, la bolsa
seguía acreditada, la tarjeta seguía renovando y nadie lo notaba. La periódica `planes_renovar` llama a
`revisar_aprobados`, que relee POR ID (`transaccion_id`, que trae el comercio; la búsqueda por referencia no) los pagos
de plan de Wompi aprobados en los últimos DIAS_REVISAR días y, si Wompi dice VOIDED, lo aplica con
`planes.aplicar_transaccion` (la misma regla que el evento: bajo el candado tomado antes de leer, una sola vez, la
bolsa de ese pago vence, la suscripción queda cancelada) y el aviso al admin dice que el evento no llegó.

Escribe solo `kv` `planes:revision:<pago>` (cuándo se revisó por última vez; único escritor: este módulo, que borra
las marcas de los pagos que ya no se revisan). Lo demás lo escribe `cobros.planes`. Leer en Wompi no cobra nada."""
import logging
import time
from datetime import datetime, timedelta

import sqlalchemy as sa

import cola
import db
from cobros import planes, wompi

log = logging.getLogger(__name__)

DIAS_REVISAR = 30
REVISIONES_POR_VUELTA = 20
TOPE_VUELTA_S = 60
CLAVE_REVISION = "planes:revision:{pago}"
_reloj = time.monotonic


def _espera_revision(edad_h):
    """Horas entre dos revisiones de un pago según su edad: cada 2 h los dos primeros días (cuando una tarjeta se
    suele anular) y después una vez al día hasta DIAS_REVISAR (unas 52 consultas por pago, como las recargas)."""
    return 2 if edad_h < 48 else 24


def _marcar(pago_id):
    """Anota cuándo se revisó un pago. Nunca lanza."""
    clave, ahora = CLAVE_REVISION.format(pago=int(pago_id)), db.ahora()
    try:
        with db.conectar() as con:
            if not con.execute(db.kv.update().where(db.kv.c.clave == clave)
                               .values(valor=ahora, actualizado_en=ahora)).rowcount:
                con.execute(db.kv.insert().values(clave=clave, valor=ahora, actualizado_en=ahora))
    except Exception:  # noqa: BLE001 — sin la marca, la próxima vuelta lo vuelve a mirar: no pasa nada
        log.warning("no se pudo anotar la revisión del pago de plan %s", pago_id, exc_info=True)


def _revisar_uno(pago):
    """Relee el pago en Wompi; solo un VOIDED de ESTE pago escribe. Devuelve el ErrorWompi si Wompi no respondió, o
    None."""
    try:
        tx = wompi.transaccion(pago["transaccion_id"], tiempo=wompi.TIEMPO)
    except wompi.ErrorWompi as e:
        log.warning("no se pudo revisar el pago de plan %s en Wompi: %s", pago["id"], cola.sin_token(str(e)))
        return e
    if tx.get("status") != "VOIDED":
        return None   # sigue aprobado (o algo que no mueve plata): no se escribe nada
    if tx.get("reference") != pago["referencia"]:
        log.warning("la transacción del pago de plan %s volvió con otra referencia: no se aplica", pago["id"])
        return None
    resultado = planes.aplicar_transaccion(tx, sin_evento=True)
    log.info("pago de plan %s: Wompi lo anuló y su evento no llegó (%s)", pago["id"], resultado)
    return None


def revisar_aprobados(tope_s=TOPE_VUELTA_S):
    """Una pasada: los pagos de plan de Wompi `aprobado` con transacción, creados en los últimos DIAS_REVISAR días,
    espaciados por edad (`_espera_revision`, contando desde la última revisión o, si no hubo, desde la aprobación:
    uno recién aprobado no se relee en la misma vuelta), el que lleva más tiempo sin mirarse primero; a lo más
    REVISIONES_POR_VUELTA y `tope_s` segundos; para a la primera caída, 429 o llave rechazada (401/403). Sin Wompi
    configurado no hace nada. Devuelve cuántos revisó."""
    if not wompi.configurado():
        return 0
    pp, kv = db.pago_plan, db.kv
    ahora = datetime.now()
    desde = (ahora - timedelta(days=DIAS_REVISAR)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(sa.select(pp.c.id, pp.c.creado_en, pp.c.actualizado_en).where(
            pp.c.medio == "wompi", pp.c.estado == "aprobado", pp.c.transaccion_id.is_not(None),
            pp.c.creado_en >= desde)).all()
        marcas = dict(con.execute(sa.select(kv.c.clave, kv.c.valor).where(kv.c.clave.like("planes:revision:%"))).all())
    vivas = {CLAVE_REVISION.format(pago=f.id) for f in filas}
    sobran = [c for c in marcas if c not in vivas]
    if sobran:
        with db.conectar() as con:   # solo borra marcas de pagos que ya no se revisan
            con.execute(kv.delete().where(kv.c.clave.in_(sobran)))

    def _ultima(f):
        return max(str(marcas.get(CLAVE_REVISION.format(pago=f.id)) or ""), str(f.actualizado_en or ""))
    hechas, inicio = 0, _reloj()
    for f in sorted(filas, key=_ultima):   # el que lleva más tiempo sin mirarse, primero
        if hechas >= REVISIONES_POR_VUELTA or _reloj() - inicio > tope_s:
            log.info("revisión de pagos de plan aprobados: cupo de la vuelta; quedan para la próxima")
            break
        try:
            edad_h = (ahora - datetime.fromisoformat(str(f.creado_en)[:19])).total_seconds() / 3600
        except ValueError:
            edad_h = 0
        if _ultima(f) > (ahora - timedelta(hours=_espera_revision(edad_h))).isoformat(timespec="seconds"):
            continue
        with db.conectar() as con:
            fila = con.execute(sa.select(pp).where(pp.c.id == f.id)).first()
        if fila is None or fila.estado != "aprobado":
            continue
        try:
            error = _revisar_uno(dict(fila._mapping))
        except Exception:  # noqa: BLE001 — un pago raro no frena los demás
            log.exception("no se pudo revisar el pago de plan %s", f.id)
            continue
        hechas += 1
        _marcar(f.id)
        if error is not None and (error.caida or getattr(error, "codigo", None) in (401, 403, 429)):
            log.warning("revisión de pagos de plan aprobados: Wompi no responde o rechaza la llave; la pasada para aquí")
            break
    return hechas
