"""Voces propias de Audios (spec 2026-09-30 §3): crear una voz con MiniMax vía
fal (clonar o diseñar), estrenarla y dejarla en Mis voces. Paga: se encola con
max_intentos=1 y voces_propias.crear registra el gasto en cuanto fal responde.
Los mensajes son msgids fijos: /trabajo/<job_id>/estado no tiene auth, así que
nunca llevan el nombre que escribió la persona."""
import idiomas
import trabajos
import voces_propias
from tareas import ref_sufijo, registrar

ETAPAS = ((idiomas.N_("Creando la voz"), 70), (idiomas.N_("Estrenando la voz"), 20), (idiomas.N_("Guardando"), 10))
MENSAJES = {
    "clonada": idiomas.N_("Voz clonada: ya está en Mis voces."),
    "disenada": idiomas.N_("Voz diseñada: ya está en Mis voces."),
    "sin_estrenar": idiomas.N_("Voz creada, pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda."),
}


def job_id(cliente):
    return f"{cliente}__voz_propia"


@registrar("voz_propia_crear")
def ejecutar(tarea):
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
