"""Voces propias de Audios (spec 2026-09-30 §3): crear una voz con MiniMax vía
fal (clonar o diseñar), estrenarla y dejarla en Mis voces. Paga: se encola con
max_intentos=1 y voces_propias.crear registra el gasto en cuanto fal responde.
Los mensajes son msgids fijos: /trabajo/<job_id>/estado no tiene auth, así que
nunca llevan el nombre que escribió la persona — y un error tampoco lleva lo
que respondió el proveedor (ver _error_publico)."""
import logging

from flask_babel import gettext

import audios
import cola
import idiomas
import trabajos
import voces_propias
from tareas import ref_sufijo, registrar

log = logging.getLogger(__name__)

ETAPAS = ((idiomas.N_("Creando la voz"), 70), (idiomas.N_("Estrenando la voz"), 20), (idiomas.N_("Guardando"), 10))
MENSAJES = {
    "clonada": idiomas.N_("Voz clonada: ya está en Mis voces."),
    "disenada": idiomas.N_("Voz diseñada: ya está en Mis voces."),
    "sin_estrenar": idiomas.N_("Voz creada, pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda."),
}
# Los únicos errores que llegan tal cual (traducidos) al estado del trabajo:
# los msgids fijos de Audios y de Mis voces, que no llevan nada de la persona.
MSGIDS_FIJOS = frozenset(audios.MENSAJES.values()) | frozenset(voces_propias.MENSAJES.values())


def job_id(cliente):
    return f"{cliente}__voz_propia"


def _error_publico(e, tarea):
    """Lo que la tarea deja como error: el worker lo guarda y
    /trabajo/<job_id>/estado (sin auth, job_id adivinable) lo muestra. El
    cuerpo de un error de fal repite el input — la URL de la grabación, la
    descripción de la voz —, así que solo un msgid fijo pasa, traducido;
    cualquier otro error va al log con su traza y sale como un mensaje fijo
    con su tipo (revisión final de Audios Europa, F1). El gasto ya quedó
    registrado adentro de voces_propias.crear, antes de cualquier falla."""
    if isinstance(e, ValueError) and str(e) in MSGIDS_FIJOS:
        return ValueError(gettext(str(e)))
    log.exception("voz_propia_crear (tarea %s) falló: %s", tarea.get("id"), cola.sin_token(e))
    return RuntimeError(gettext("No pude crear la voz; intenta de nuevo (%(tipo)s).", tipo=type(e).__name__))


@registrar("voz_propia_crear")
def ejecutar(tarea):
    try:
        return _crear(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por _error_publico
        raise _error_publico(e, tarea) from e


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
