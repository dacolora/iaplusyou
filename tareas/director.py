"""
Tarea del worker `flowplus_director` (spec director §4): compila el prompt por
planos de una sesión de Crear con Claude y lo deja en `prompt_relleno`
(versión A) y `extra["director"]` (planos, versión B, estado). Si el director
falla por lo que sea, la sesión igual queda en `prompt_listo` con el prompt
determinista de `flowplus_prompt.armar` y un aviso: el fallo de Claude nunca
es un fallo del trabajo ni bloquea a la persona. Con `auto_lanzar` (lotes de
Sprints, cuyo costo ya se aprobó) encola además la generación.
"""
import creative_flow
import director
import flowplus_lanzar
import flowplus_prompt
import proyectos
import trabajos
from providers import flowplus_modelos
from tareas import al_interrumpir, registrar

ETAPA_LEER = "Leyendo referencias"
ETAPA_PLANOS = "Escribiendo planos"
ETAPA_LISTO = "Listo"
ETAPAS_DIRECTOR = [(ETAPA_LEER, 10), (ETAPA_PLANOS, 80), (ETAPA_LISTO, 10)]
DURACION_ESTIMADA = 25


def job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__director"


def _fallback(cliente, entry, motivo):
    sesion = creative_flow.datos_para_director(cliente, entry)
    refs = sesion["referencias"]
    info = flowplus_prompt.ENFOQUES.get(sesion["enfoque"]) or flowplus_prompt.ENFOQUES["producto"]
    modelo = sesion["modelo"] if sesion["modelo"] in flowplus_modelos.VIDEO else None
    prompt = flowplus_prompt.armar(
        sesion["accion_central"], refs, con_persona=info["con_persona"], guia_marca=sesion["guia_marca"],
        negative_marca=sesion["negative_marca"], logos=[r for r in refs if r.get("logo")], enfoque=sesion["enfoque"],
        contexto=sesion["contexto"], sonido=(sesion["sonido_texto"] or None) if sesion["con_sonido"] else None,
        con_sonido=sesion["con_sonido"], cierre_sonido=flowplus_modelos.cierre_sonido(modelo) if modelo else None,
    )
    return prompt, {"estado": "fallback", "aviso": motivo, "planos": None, "planos_b": None, "prompt_b": None,
                    "diferencia_b": None, "modelo_claude": None, "version": director.VERSION, "usd": 0.0}


@registrar("flowplus_director")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente, cf_id = p["cliente"], p["cf_id"]
    jid = tarea.get("job_id") or job_id(cliente, cf_id)
    trabajos.reportar(jid, etapa=ETAPA_LEER)
    entry = creative_flow.cargar(cliente)[cf_id]
    idioma = proyectos.preferencias_flowplus(cliente).get("idioma_prompt") or "es"
    trabajos.reportar(jid, etapa=ETAPA_PLANOS)
    try:
        r = director.compilar(cliente, creative_flow.datos_para_director(cliente, entry), idioma=idioma)
        prompt = r["prompt_a"]
        datos = {"estado": "ok", "aviso": None, "planos": r["planos"], "planos_b": r["planos_b"], "prompt_b": r["prompt_b"],
                 "diferencia_b": r["diferencia_b"], "modelo_claude": r["modelo_claude"], "version": r["version"], "usd": r["usd"]}
        mensaje = "Prompt listo — revísalo y genera."
    except director.DirectorError as e:
        prompt, datos = _fallback(cliente, entry, e.motivo)
        mensaje = "La IA no pudo armar los planos; quedó el prompt básico para que lo edites o rearmes."
    except Exception as e:  # red, SDK, lo que sea: nunca deja la sesión colgada
        prompt, datos = _fallback(cliente, entry, str(e)[:300])
        mensaje = "La IA no pudo armar los planos; quedó el prompt básico para que lo edites o rearmes."
    trabajos.reportar(jid, etapa=ETAPA_LISTO)
    creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt, director=datos)
    if p.get("auto_lanzar"):
        entry = creative_flow.cargar(cliente)[cf_id]
        flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=int(p.get("prioridad") or flowplus_lanzar.PRIORIDAD_NORMAL))
    return mensaje


@al_interrumpir("flowplus_director")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de la compilación (dos veces: max_intentos=2).
    La sesión quedaría en `prompt_pendiente` sin trabajo y sin botón: se le
    deja el prompt determinista con el aviso, en `prompt_listo`, para que la
    persona lo edite, rearme o genere. Si ya salió de `prompt_pendiente` por
    otro camino, no se pisa."""
    p = tarea["payload"]
    cliente, cf_id = p["cliente"], p["cf_id"]
    entry = creative_flow.cargar(cliente).get(cf_id)
    if entry is None or entry.get("estado") != "prompt_pendiente":
        return
    prompt, datos = _fallback(cliente, entry, mensaje)
    creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt, director=datos)
