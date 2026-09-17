"""
Tareas del worker para Sprints (Parte 1): analizar una referencia con Claude,
sugerir personas y traer una referencia desde un link. Las tres son baratas
(centavos, sin generación de video), por eso llevan reintentos.

Ids de trabajo (los mismos que usan las rutas para encolar y consultar):
  sprint_analizar_referencia -> f"{cliente}__ref{referencia_id}__analizar"   (max_intentos=3)
  sprint_sugerir_personas    -> f"{cliente}__sprints__sugerir_personas"      (max_intentos=2)
  sprint_referencia_link     -> f"{cliente}__campana{campana_id}__link"      (max_intentos=2)
"""
import os
from datetime import datetime

import proyectos
import referencias_link
import trabajos
from sprints import analisis, archivos, datos, sugerencias
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
