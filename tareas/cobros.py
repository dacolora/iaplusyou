"""Tareas de cobros (spec 2026-10-08 §9.3).

  cobros_verificar_recargas {}   periódica cada 10 min — respaldo del webhook:
                                 pregunta a Bold por cada recarga pendiente
                                 (cobros.recargas.verificar_pendientes) y vence
                                 las de más de 26 h. Solo consulta a Bold: no
                                 cobra (está en TIPOS_EXENTOS_DE_COBRO)."""
from flask_babel import gettext

from cobros import recargas
from tareas import registrar


@registrar("cobros_verificar_recargas")
def verificar_recargas(tarea):
    n = recargas.verificar_pendientes()
    return gettext("%(n)s recargas revisadas", n=n)
