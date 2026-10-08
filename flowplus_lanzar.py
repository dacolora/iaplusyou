"""
Encolar en el worker la generación de una sesión de Crear (FlowPlus): imagen o
video. Lo usan el dashboard (Crear: formulario y reintento) y los sprints
(lotes, reintento y regeneración). El cuerpo real vive en tareas/flowplus.py.

`prioridad`: 5 es lo normal; los lotes de sprint pasan 3 para que una pieza
suelta pedida desde Crear se atienda antes que las treinta de un lote.
"""
import creative_flow
import gastos
import trabajos
from cobros import SaldoInsuficiente
from providers import flowplus_modelos
from tareas.flowplus import ETAPAS_CREATIVE_FLOW

PRIORIDAD_NORMAL = 5


def job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


def costo_estimado(entry):
    """USD que costaría generar la sesión (sin margen), con las mismas reglas
    que aplica la tarea antes de gastar (modelo por defecto, duración dentro
    del rango, segundos de videos de referencia que Wan factura, música de fal).
    None si no hay tarifa: el freno pide entonces solo saldo positivo. Nunca lanza."""
    e = entry or {}
    try:
        modelo = e.get("modelo")
        if (e.get("tipo") or "video") == "imagen":
            modelo = modelo if modelo in flowplus_modelos.IMAGEN else flowplus_modelos.IMAGEN_POR_DEFECTO
            return gastos.estimar("imagen", modelo=modelo, n_referencias=len(e.get("referencias_urls") or []))["usd"]
        if flowplus_modelos.es_hablado(modelo):
            return flowplus_modelos.estimate_hablado(modelo, float(e.get("duracion_objetivo") or 0))["usd"]
        modelo = modelo if modelo in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
        duracion = flowplus_modelos.ajustar_duracion(modelo, e.get("duracion_objetivo"))
        calidad = e.get("calidad") if e.get("calidad") in flowplus_modelos.CALIDADES else "final"
        segundos = flowplus_modelos.segundos_videos(modelo, e.get("referencias") or [])
        usd = flowplus_modelos.estimate_video(modelo, duracion, con_sonido=e.get("con_sonido", True) is not False,
                                              calidad=calidad, videos_ref_s=segundos or ())["usd"]
        return None if usd is None else round(usd + gastos.costo_musica_estimada(e.get("musica_estilo")), 4)
    except Exception:  # noqa: BLE001 — sin precio, el freno igual pide saldo positivo
        return None


def lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_NORMAL):
    """Devuelve True si encoló, False si ya había una tarea viva para esa sesión.
    Escribe estado="video_generando" ANTES de encolar: si el worker fallara
    instantáneo, podría escribir "error" y el principal pisarlo. max_intentos=1:
    si la generación falla ya pudo haberse cobrado el crédito; la persona
    decide con "Reintentar".

    Sin saldo (cobros, spec 2026-10-08 §5) no se encola: la sesión vuelve a
    «prompt listo» si venía de ahí y si no queda en error con la frase (en el
    idioma del proyecto), así no se queda «generando» para siempre; después se
    relanza SaldoInsuficiente para que la ruta lo muestre o el encolador del
    worker lo anote."""
    tipo = entry.get("tipo") or "video"
    previo = entry.get("estado")
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    try:
        return trabajos.encolar(
            job_id(cliente, cf_id), "flowplus_imagen" if tipo == "imagen" else "flowplus_video",
            {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
            duracion_estimada=60 if tipo == "imagen" else 180, etapas=ETAPAS_CREATIVE_FLOW,
            max_intentos=1, prioridad=prioridad, costo_estimado=costo_estimado(entry),
        )
    except SaldoInsuficiente as e:
        if previo == "prompt_listo":
            creative_flow.actualizar(cliente, cf_id, estado="prompt_listo")
        else:
            creative_flow.actualizar(cliente, cf_id, estado="error", error=e.frase_proyecto())
        raise

