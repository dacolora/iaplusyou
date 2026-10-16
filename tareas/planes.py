"""Tareas de los planes (spec planes 2026-10-09 §7).

  planes_renovar {}   periódica cada 30 min — cierra los periodos vencidos,
                      abre los ya pagados, cobra en Wompi las renovaciones que
                      tocan (con gracia de tres intentos) y avisa. Cobra a
                      Wompi pero es ingreso, no gasto de un proveedor: no pasa
                      por el saldo (está en TIPOS_EXENTOS_DE_COBRO). Se puede
                      reintentar sin miedo: cada renovación tiene su referencia
                      y nunca hay dos cobros pendientes o aprobados de ella.
                      Después relee en Wompi los pagos de plan aprobados de
                      los últimos 30 días por si alguno se anuló sin que llegara
                      su evento (PND-341, `cobros.planes_revision`)."""
import logging

from flask_babel import gettext

from cobros import planes, planes_revision
from tareas import registrar

log = logging.getLogger(__name__)


@registrar("planes_renovar")
def renovar(tarea):
    r = planes.renovar_todo()
    try:
        # PND-341: relee los pagos de plan aprobados de los últimos 30 días por si Wompi los anuló y su evento no llegó.
        planes_revision.revisar_aprobados()
    except Exception:  # noqa: BLE001 — la revisión nunca frena la renovación
        log.exception("no se pudo revisar los pagos de plan aprobados")
    return gettext("%(cerrados)s periodos cerrados, %(abiertos)s abiertos, %(cobros)s cobros revisados",
                   cerrados=r["cerrados"], abiertos=r["abiertos"], cobros=sum(r["cobros"].values()))
