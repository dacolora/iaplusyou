"""
Encolar en el worker la generación de una sesión de Crear (FlowPlus): imagen o
video. Lo usan el dashboard (Crear: formulario y reintento) y los sprints
(lotes, reintento y regeneración). El cuerpo real vive en tareas/flowplus.py.

`prioridad`: 5 es lo normal; los lotes de sprint pasan 3 para que una pieza
suelta pedida desde Crear se atienda antes que las treinta de un lote.
"""
import creative_flow
import trabajos
from tareas.flowplus import ETAPAS_CREATIVE_FLOW

PRIORIDAD_NORMAL = 5


def job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


def lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_NORMAL):
    """Devuelve True si encoló, False si ya había una tarea viva para esa sesión.
    Escribe estado="video_generando" ANTES de encolar: si el worker fallara
    instantáneo, podría escribir "error" y el principal pisarlo. max_intentos=1:
    si la generación falla ya pudo haberse cobrado el crédito; la persona
    decide con "Reintentar"."""
    tipo = entry.get("tipo") or "video"
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    return trabajos.encolar(
        job_id(cliente, cf_id), "flowplus_imagen" if tipo == "imagen" else "flowplus_video",
        {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
        duracion_estimada=60 if tipo == "imagen" else 180, etapas=ETAPAS_CREATIVE_FLOW,
        max_intentos=1, prioridad=prioridad,
    )
