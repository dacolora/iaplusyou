"""Tareas de los planes (spec planes 2026-10-09 §7).

  planes_renovar {}   periódica cada 30 min — cierra los periodos vencidos,
                      abre los ya pagados, cobra en Wompi las renovaciones que
                      tocan (con gracia de tres intentos) y avisa. Cobra a
                      Wompi pero es ingreso, no gasto de un proveedor: no pasa
                      por el saldo (está en TIPOS_EXENTOS_DE_COBRO). Se puede
                      reintentar sin miedo: cada renovación tiene su referencia
                      y nunca hay dos cobros pendientes o aprobados de ella."""
from flask_babel import gettext

from cobros import planes
from tareas import registrar


@registrar("planes_renovar")
def renovar(tarea):
    r = planes.renovar_todo()
    return gettext("%(cerrados)s periodos cerrados, %(abiertos)s abiertos, %(cobros)s cobros revisados",
                   cerrados=r["cerrados"], abiertos=r["abiertos"], cobros=sum(r["cobros"].values()))
