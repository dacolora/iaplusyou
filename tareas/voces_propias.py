"""Voces propias de Audios (spec 2026-09-30 §3): crear una voz con MiniMax vía
fal (clonar o diseñar), estrenarla y dejarla en Mis voces. Paga: se encola con
max_intentos=1 y voces_propias.crear registra el gasto en cuanto fal responde.
Los mensajes son msgids fijos: /trabajo/<job_id>/estado no tiene auth, así que
nunca llevan el nombre que escribió la persona — y un error tampoco lleva lo
que respondió el proveedor (ver tareas/errores_voz.py)."""
import idiomas
import trabajos
import voces_propias
from tareas import errores_voz, ref_sufijo, registrar

ETAPAS = ((idiomas.N_("Creando la voz"), 70), (idiomas.N_("Estrenando la voz"), 20), (idiomas.N_("Guardando"), 10))
MENSAJES = {
    "clonada": idiomas.N_("Voz clonada: ya está en Mis voces."),
    "disenada": idiomas.N_("Voz diseñada: ya está en Mis voces."),
    "sin_estrenar": idiomas.N_("Voz creada, pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda."),
}
# Cualquier otro error (ver errores_voz.publico): el gasto ya quedó registrado
# adentro de voces_propias.crear, antes de cualquier falla.
MENSAJE_ERROR = idiomas.N_("No pude crear la voz; intenta de nuevo (%(tipo)s).")


def job_id(cliente):
    return f"{cliente}__voz_propia"


@registrar("voz_propia_crear")
def ejecutar(tarea):
    try:
        return _crear(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por errores_voz.publico
        raise errores_voz.publico(e, tarea, "voz_propia_crear", MENSAJE_ERROR) from e


def _crear(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    jid = tarea.get("job_id") or job_id(cliente)
    trabajos.reportar(jid, etapa=ETAPAS[0][0])

    def _reportar(i):
        trabajos.reportar(jid, etapa=ETAPAS[i][0])
    voz, estrenada = voces_propias.crear(cliente, p, ref_sufijo=ref_sufijo(tarea), reportar=_reportar)
    if not estrenada:
        return MENSAJES["sin_estrenar"]
    return MENSAJES["clonada"] if voz.get("forma") == "clonada" else MENSAJES["disenada"]
