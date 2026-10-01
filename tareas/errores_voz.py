"""El error que dejan las tareas de voz (Audios, Mis voces y Anuncio hablado):
el worker lo guarda y /trabajo/<job_id>/estado (sin auth, job_id adivinable:
`<proyecto>__audio_generar`, `__voz_propia`, `__hablado_voz`) lo muestra. El
cuerpo de un error de fal repite el input — el texto del anuncio, el guion, la
URL de la grabación, la descripción de la voz —, así que solo un msgid fijo de
Audios o de Mis voces pasa, traducido; cualquier otro error va al log con su
traza y sale como el mensaje fijo de la tarea con su tipo (revisión final de
Audios Europa, F1). El gasto ya quedó registrado antes de cualquier falla, en
la tarea o en lo que llama."""
import logging

from flask_babel import gettext

import audios
import cola
import voces_propias

log = logging.getLogger(__name__)

# Los únicos errores que llegan tal cual (traducidos) al estado del trabajo:
# no llevan nada de la persona (p. ej. la voz propia que se borró entre el
# clic y el worker).
MSGIDS_FIJOS = frozenset(audios.MENSAJES.values()) | frozenset(voces_propias.MENSAJES.values())


def publico(e, tarea, tipo, mensaje):
    """La excepción que la tarea `tipo` debe lanzar en lugar de `e`. `mensaje`
    es un msgid (`idiomas.N_`) con `%(tipo)s`. Se llama dentro del `except`,
    para que el log lleve la traza."""
    if isinstance(e, ValueError) and str(e) in MSGIDS_FIJOS:
        return ValueError(gettext(str(e)))
    log.exception("%s (tarea %s) falló: %s", tipo, tarea.get("id"), cola.sin_token(e))
    return RuntimeError(gettext(mensaje, tipo=type(e).__name__))
