"""
Tareas del worker para Sprints: analizar una referencia con Claude, sugerir
personas, traer una referencia desde un link (Parte 1, baratas — centavos, sin
generación de video, por eso llevan reintentos) y proponer ideas por campaña
con el prompt maestro (Parte 2, también solo texto).

Ids de trabajo (los mismos que usan las rutas para encolar y consultar):
  sprint_analizar_referencia -> f"{cliente}__ref{referencia_id}__analizar"   (max_intentos=3)
  sprint_sugerir_personas    -> f"{cliente}__sprints__sugerir_personas"      (max_intentos=2)
  sprint_referencia_link     -> f"{cliente}__campana{campana_id}__link"      (max_intentos=2)
  sprint_proponer_ideas      -> f"{cliente}__campana{campana_id}__ideas"     (max_intentos=2)
"""
import os
from datetime import datetime

import proyectos
import referencias_link
import trabajos
from sprints import analisis, archivos, datos, estado, ideas, sugerencias
from tareas import al_interrumpir, registrar


def job_id_analizar(cliente, referencia_id):
    return f"{cliente}__ref{referencia_id}__analizar"


def job_id_sugerir(cliente):
    return f"{cliente}__sprints__sugerir_personas"


def job_id_link(cliente, campana_id):
    return f"{cliente}__campana{campana_id}__link"


def encolar_analisis(cliente, referencia_id):
    return trabajos.encolar(job_id_analizar(cliente, referencia_id), "sprint_analizar_referencia",
                            {"cliente": cliente, "referencia_id": referencia_id}, cliente=cliente,
                            duracion_estimada=20, max_intentos=3)


def encolar_sugerir(cliente, cuantas=3):
    return trabajos.encolar(job_id_sugerir(cliente), "sprint_sugerir_personas",
                            {"cliente": cliente, "cuantas": int(cuantas)}, cliente=cliente,
                            duracion_estimada=25, max_intentos=2)


def encolar_link(cliente, campana_id, url):
    return trabajos.encolar(job_id_link(cliente, campana_id), "sprint_referencia_link",
                            {"cliente": cliente, "campana_id": campana_id, "url": url}, cliente=cliente,
                            duracion_estimada=60, max_intentos=2)


@registrar("sprint_analizar_referencia")
def ejecutar_analizar(tarea):
    p = tarea["payload"]
    cliente, rid = p["cliente"], int(p["referencia_id"])
    ref = datos.referencia(cliente, rid)
    if not ref:
        return "La referencia ya no existe."
    try:
        resultado = analisis.analizar(ref, marca=proyectos.nombre_visible(cliente))
    except Exception as e:
        datos.actualizar_referencia(cliente, rid, analisis_estado="error", analisis={"error": str(e)})
        raise
    datos.actualizar_referencia(cliente, rid, analisis=resultado, analisis_estado="listo")
    return "Referencia analizada."


@al_interrumpir("sprint_analizar_referencia")
def interrumpida_analizar(tarea, mensaje):
    p = tarea["payload"]
    datos.actualizar_referencia(p["cliente"], int(p["referencia_id"]), analisis_estado="error",
                                analisis={"error": mensaje})


@registrar("sprint_sugerir_personas")
def ejecutar_sugerir(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    propuestas = sugerencias.sugerir_personas(cliente, cuantas=int(p.get("cuantas") or 3))
    for persona in propuestas:
        datos.crear_persona(cliente, persona["nombre"], resumen=persona.get("resumen", ""),
                            descripcion=persona.get("descripcion", ""), edad_rango=persona.get("edad_rango", ""),
                            tono=persona.get("tono", ""), senales_visuales=persona.get("senales_visuales"),
                            palabras_clave=persona.get("palabras_clave"), color=persona.get("color"),
                            origen="sugerida_ia")
    return f"{len(propuestas)} personas sugeridas — revísalas y edítalas."


@registrar("sprint_referencia_link")
def ejecutar_link(tarea):
    p = tarea["payload"]
    cliente, campana_id, url = p["cliente"], int(p["campana_id"]), p["url"]
    carpeta = archivos.carpeta(cliente)
    os.makedirs(carpeta, exist_ok=True)
    nombre_base = f"link_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    ruta, meta = referencias_link.descargar(url, carpeta, nombre_base)
    info = archivos.registrar_local(cliente, ruta, (meta or {}).get("titulo") or url)
    rid = datos.agregar_referencia(cliente, campana_id, info["tipo"], info["url"], frame_url=info["frame_url"],
                                   ruta_local=info["ruta_local"], origen="link", titulo=info["titulo"])
    encolar_analisis(cliente, rid)
    return "Referencia agregada desde el link."


def job_id_ideas(cliente, campana_id):
    return f"{cliente}__campana{campana_id}__ideas"


def encolar_ideas(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None):
    return trabajos.encolar(job_id_ideas(cliente, campana_id), "sprint_proponer_ideas",
                            {"cliente": cliente, "campana_id": campana_id, "n_videos": n_videos, "n_imagenes": n_imagenes,
                             "reemplaza": reemplaza}, cliente=cliente, duracion_estimada=40, max_intentos=2)


@registrar("sprint_proponer_ideas")
def ejecutar_proponer_ideas(tarea):
    p = tarea["payload"]
    cliente, campana_id = p["cliente"], int(p["campana_id"])
    creadas = ideas.proponer(cliente, campana_id, n_videos=p.get("n_videos"), n_imagenes=p.get("n_imagenes"),
                             reemplaza=p.get("reemplaza"))
    c = datos.campana(cliente, campana_id)
    if c:
        estado.recalcular(cliente, c["sprint_id"])
    return f"{len(creadas)} ideas propuestas — revísalas y aprueba las que sirvan."
