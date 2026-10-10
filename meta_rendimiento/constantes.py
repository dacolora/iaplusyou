"""Constantes de Meta rendimiento que usan a la vez el blueprint (`rutas`: el selector «Elegir cuentas») y las reglas
puras (`recomendaciones`: la cuenta con problema). Viven aquí y no en `rutas` para que un módulo puro no importe un
blueprint de Flask (revisión de la tarea 6 de Rendimiento E2, 2026-10-10). Se traducen donde se muestran."""
from idiomas import N_

# account_status de una cuenta publicitaria (Graph /me/adaccounts); otro código se muestra como «Otro estado».
ESTADOS_CUENTA = {1: N_("Activa"), 2: N_("Desactivada"), 3: N_("Con pagos pendientes"), 7: N_("En revisión de Meta"),
                  8: N_("Con pagos pendientes"), 9: N_("En período de gracia"), 100: N_("Por cerrarse"),
                  101: N_("Cerrada")}
OTRO_ESTADO = N_("Otro estado")
