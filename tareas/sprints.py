"""
Tareas del worker para Sprints: analizar una referencia con Claude, sugerir
personas, traer una referencia desde un link (Parte 1, baratas — centavos, sin
generación de video, por eso llevan reintentos), proponer ideas por campaña
con el prompt maestro (Parte 2, también solo texto) y el control de calidad
automático de una pieza ya generada (también Parte 2, centavos de visión).

Ids de trabajo (los mismos que usan las rutas para encolar y consultar):
  sprint_analizar_referencia -> f"{cliente}__ref{referencia_id}__analizar"   (max_intentos=3)
  sprint_sugerir_personas    -> f"{cliente}__sprints__sugerir_personas"      (max_intentos=2)
  sprint_referencia_link     -> f"{cliente}__campana{campana_id}__link"      (max_intentos=2)
  sprint_proponer_ideas      -> f"{cliente}__campana{campana_id}__ideas"     (max_intentos=2)
  sprint_qa_pieza            -> f"{cliente}__cp{cp_id}__qa"                  (max_intentos=3)

`sprint_qa_pendientes` es la periódica (worker.PERIODICAS, cada 300 s) que
encola sprint_qa_pieza para toda pieza lista sin qa, y avisa (notificaciones)
cuando un lote de producción (sprints/produccion.py) termina.
"""
import os
from datetime import datetime

import sqlalchemy as sa

import bitacora
import cola
import creative_flow
import db
import notificaciones
import proyectos
import referencias_link
import trabajos
from sprints import analisis, archivos, datos, entrega, estado, ideas, produccion, qa, sugerencias
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


def job_id_qa(cliente, cp_id):
    return f"{cliente}__cp{cp_id}__qa"


def encolar_qa(cliente, cp_id):
    """El mismo trabajo que encola la periódica; lo usa «Repetir QA» desde la
    bandeja. Solo QA (centavos de visión), nunca generación."""
    return trabajos.encolar(job_id_qa(cliente, cp_id), "sprint_qa_pieza", {"cliente": cliente, "cp_id": cp_id},
                            cliente=cliente, duracion_estimada=30, max_intentos=3)


@registrar("sprint_qa_pieza")
def ejecutar_qa_pieza(tarea):
    """QA de una pieza lista. Si falla, la tarea reintenta sola (max 3): el QA
    no gasta en generación, solo centavos de visión. El resultado se guarda
    con `datos.guardar_qa` contra la sesión (`cf_id`) que se evaluó: si la
    pieza se regeneró mientras tanto, el veredicto viejo se descarta y la
    periódica evaluará la sesión nueva. Un fallo (descarga, ffprobe, visión)
    deja el marcador terminal `veredicto="error"` antes de subir la
    excepción: la cola agota sus intentos, pero la periódica ya no la vuelve
    a encolar cada 5 min; «Repetir QA» (rutas.pieza_qa) limpia el marcador."""
    p = tarea["payload"]
    cliente, cp_id = p["cliente"], int(p["cp_id"])
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        return "La pieza ya no existe."
    cf_id = i["cf_id"]
    entry = creative_flow.cargar(cliente).get(cf_id)
    campana = datos.campana(cliente, i["campana_id"])
    if not entry or not campana:
        return "La pieza ya no existe."
    sp = datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}
    umbral = (sp.get("extra") or {}).get("qa_umbral") or qa.UMBRAL_DEFECTO
    campana["marca"] = proyectos.nombre_visible(cliente)
    try:
        resultado = dict(qa.evaluar(cliente, i, entry, campana, umbral=umbral))
    except Exception as e:
        datos.guardar_qa(cliente, cp_id, cf_id, {"veredicto": "error", "score": None, "checks": {}, "nota": str(e)[:300],
                                                 "cf_id": cf_id})
        raise
    resultado["cf_id"] = cf_id
    if not datos.guardar_qa(cliente, cp_id, cf_id, resultado):
        bitacora.registrar(cliente, cf_id, "sprint_qa", "descartado", "QA descartado: la pieza fue regenerada")
        return "QA descartado: la pieza fue regenerada mientras se evaluaba."
    datos.registrar_evento(cliente, i["sprint_id"], "qa_evaluada",
                           f"QA de «{i['titulo']}»: {resultado['veredicto']} ({resultado['score']})",
                           {"cp_id": cp_id, "score": resultado["score"], "veredicto": resultado["veredicto"]},
                           campana_id=i["campana_id"])
    return f"QA: {resultado['veredicto']} ({resultado['score']}/100)."


def _piezas_listas_sin_qa():
    """(cliente, cp_id) de ideas con sesión lista/degradada y qa NULL.
    `qa` es una columna JSON: SQLAlchemy guarda un `None` de Python como el
    valor JSON `null` (texto), no como SQL NULL (`JSON.none_as_null` es False
    por defecto) — así que `IS NULL` sola no alcanza, hace falta cubrir
    también el `null` JSON con `json_type`."""
    cp, pz = db.campana_pieza, db.pieza
    sin_qa = sa.or_(cp.c.qa.is_(None), sa.func.json_type(cp.c.qa) == "null")
    with db.conectar() as con:
        filas = con.execute(sa.select(cp.c.cliente, cp.c.id).select_from(
            cp.join(pz, sa.and_(pz.c.legado_id == cp.c.cf_id, pz.c.cliente == cp.c.cliente, pz.c.tipo.in_(datos.TIPOS_PIEZA))))
            .where(sin_qa, cp.c.estado_idea != "descartada", pz.c.estado.in_(("listo", "degradada")))
            .order_by(cp.c.id)).all()
    return [(f.cliente, f.id) for f in filas]


def _sprints_con_lote():
    """Sprints con `extra.lote_en_curso`. Se filtra en Python: son pocos y el
    JSON de SQLite no garantiza el tipo del booleano."""
    s = db.sprint
    with db.conectar() as con:
        filas = con.execute(sa.select(s.c.cliente, s.c.id, s.c.nombre, s.c.extra).where(s.c.archivado.is_(False))).all()
    return [(f.cliente, f.id, f.nombre) for f in filas if (f.extra or {}).get("lote_en_curso")]


@registrar("sprint_qa_pendientes")
def ejecutar_qa_pendientes(tarea):
    """Periódica (5 min): encola el QA de las piezas listas sin evaluar y avisa
    cuando un lote termina (ninguna pieza pendiente ni generando)."""
    n = 0
    for cliente, cp_id in _piezas_listas_sin_qa():
        if cola.encolar("sprint_qa_pieza", {"cliente": cliente, "cp_id": cp_id}, cliente=cliente,
                        job_id=job_id_qa(cliente, cp_id), duracion_estimada=30, max_intentos=3):
            n += 1
    terminados = 0
    for cliente, sid, nombre in _sprints_con_lote():
        sp = estado.recalcular(cliente, sid)
        if not sp:
            continue
        # Viva = pendiente/generando o una reserva viva (placeholder
        # "reservando_*" sin fila en `pieza` todavía, estado None). Una
        # reserva vencida (el proceso murió entre reservar y crear la sesión)
        # ya no es pieza: `produccion.pieza_viva` la ignora y el lote puede
        # cerrarse en vez de quedar colgado para siempre.
        vivas = [p for c in sp["campanas"] for p in c["piezas"] if produccion.pieza_viva(p)]
        if vivas:
            continue
        piezas = [p for c in sp["campanas"] for p in c["piezas"]]
        listas = sum(1 for p in piezas if p.get("estado") in ("listo", "degradada"))
        errores = sum(1 for p in piezas if p.get("estado") == "error")
        datos.actualizar_extra_sprint(cliente, sid, lambda e: {**e, "lote_en_curso": False})
        datos.registrar_evento(cliente, sid, "lote_terminado", f"Lote terminado: {listas} lista(s), {errores} con error",
                               {"listas": listas, "errores": errores})
        notificaciones.avisar(cliente, "sprint_lote", f"Lote terminado: {nombre}",
                              f"El lote del sprint «{nombre}» terminó: {listas} pieza(s) lista(s) y {errores} con error. "
                              "Entra a la bandeja de revisión para aprobar o rechazar.")
        terminados += 1
    return f"{n} pieza(s) a QA; {terminados} lote(s) terminado(s)."


def job_id_zip(cliente, sprint_id):
    return f"{cliente}__sprint{sprint_id}__zip"


def encolar_zip(cliente, sprint_id):
    return trabajos.encolar(job_id_zip(cliente, sprint_id), "sprint_empaquetar",
                            {"cliente": cliente, "sprint_id": sprint_id}, cliente=cliente,
                            duracion_estimada=120, max_intentos=2)


@registrar("sprint_empaquetar")
def ejecutar_empaquetar(tarea):
    p = tarea["payload"]
    info = entrega.empaquetar(p["cliente"], int(p["sprint_id"]))
    return f"Zip listo con {info['n']} pieza(s)."
