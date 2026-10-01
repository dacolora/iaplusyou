"""Anuncio hablado en Crear (spec 2026-10-01 §3): «Escuchar la voz» paga la
voz cruda con `audios.voz_cruda` — la misma caché que Audios: el mismo texto
con la misma voz, idioma y velocidad no se paga dos veces —. Paga: se encola
con max_intentos=1 y el gasto `locucion` se registra apenas el proveedor
cobra. Va en el carril de Crear (worker.CARRIL_CREAR): no espera detrás de
renders. Un trabajo a la vez por proyecto (`<cliente>__hablado_voz`)."""
import logging

from flask_babel import gettext

import audios
import cola
import idiomas
import trabajos
import voces_propias
from tareas import ref_sufijo, registrar

log = logging.getLogger(__name__)

ETAPAS = ((idiomas.N_("Sintetizando la voz"), 100),)
# msgids: estado_trabajo (dashboard.py) los traduce al responder. La ruta
# /trabajo/<job_id>/estado no tiene auth y el job_id se adivina: el mensaje
# nunca lleva el guion de la persona, solo estas constantes fijas.
MENSAJES = {"lista": idiomas.N_("Voz lista: escúchala y genera el video.")}
MSGIDS_FIJOS = frozenset(audios.MENSAJES.values()) | frozenset(voces_propias.MENSAJES.values())


def job_id(cliente):
    return f"{cliente}__hablado_voz"


def _error_publico(e, tarea):
    """Como en Audios: el cuerpo de un error de fal repite el input (el guion),
    así que solo un msgid fijo pasa, traducido; cualquier otro error va al log
    con su traza y sale como un mensaje fijo con su tipo. El gasto ya quedó
    registrado en audios.voz_cruda, apenas el proveedor cobró."""
    if isinstance(e, ValueError) and str(e) in MSGIDS_FIJOS:
        return ValueError(gettext(str(e)))
    log.exception("hablado_voz (tarea %s) falló: %s", tarea.get("id"), cola.sin_token(e))
    return RuntimeError(gettext("No pude crear la voz; intenta de nuevo (%(tipo)s).", tipo=type(e).__name__))


@registrar("hablado_voz")
def ejecutar(tarea):
    try:
        return _generar(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por _error_publico
        raise _error_publico(e, tarea) from e


def _generar(tarea):
    p = tarea["payload"]
    trabajos.reportar(tarea.get("job_id") or job_id(p["cliente"]), etapa=ETAPAS[0][0])
    audios.voz_cruda(p["cliente"], p["texto"], p["voz"], p["idioma"], p.get("velocidad") or "normal",
                     ref_sufijo(tarea))
    return MENSAJES["lista"]
