"""Anuncio hablado en Crear (spec 2026-10-01 §3): «Escuchar la voz» paga la
voz cruda con `audios.voz_cruda` — la misma caché que Audios: el mismo texto
con la misma voz, idioma y velocidad no se paga dos veces —. Paga: se encola
con max_intentos=1 y el gasto `locucion` se registra apenas el proveedor
cobra. Va en el carril de Crear (worker.CARRIL_CREAR): no espera detrás de
renders. Un trabajo a la vez por proyecto (`<cliente>__hablado_voz`)."""
import audios
import idiomas
import trabajos
from tareas import errores_voz, ref_sufijo, registrar

ETAPAS = ((idiomas.N_("Sintetizando la voz"), 100),)
# msgids: estado_trabajo (dashboard.py) los traduce al responder. La ruta
# /trabajo/<job_id>/estado no tiene auth y el job_id se adivina: el mensaje
# nunca lleva el guion de la persona, solo estas constantes fijas.
MENSAJES = {"lista": idiomas.N_("Voz lista: escúchala y genera el video.")}
# Cualquier otro error (ver errores_voz.publico): el gasto ya quedó registrado
# en audios.voz_cruda, apenas el proveedor cobró.
MENSAJE_ERROR = idiomas.N_("No pude crear la voz; intenta de nuevo (%(tipo)s).")


def job_id(cliente):
    return f"{cliente}__hablado_voz"


@registrar("hablado_voz")
def ejecutar(tarea):
    try:
        return _generar(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por errores_voz.publico
        raise errores_voz.publico(e, tarea, "hablado_voz", MENSAJE_ERROR) from e


def _generar(tarea):
    p = tarea["payload"]
    trabajos.reportar(tarea.get("job_id") or job_id(p["cliente"]), etapa=ETAPAS[0][0])
    audios.voz_cruda(p["cliente"], p["texto"], p["voz"], p["idioma"], p.get("velocidad") or "normal",
                     ref_sufijo(tarea))
    return MENSAJES["lista"]
