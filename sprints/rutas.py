# sprints/rutas.py
"""
Rutas de la pestaña Sprints (Blueprint `sprints`, prefijo
/cliente/<cliente>/sprints). Solo validan, delegan a sprints.datos /
sprints.estado / tareas.sprints y redirigen; la lógica vive en esos módulos.
`dashboard._guard_por_cliente` protege estas rutas igual que las demás porque
la URL lleva <cliente>. `contexto(cliente)` es lo que `ver_cliente` agrega
al render de cliente.html para la pestaña.
"""
import json
from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import catalogo_productos
import proyectos
import trabajos
from final_edition import tipos as fe_tipos
from providers import flowplus_modelos
from sprints import calendario, datos, estado, progreso
from tareas import sprints as tareas_sprints

bp = Blueprint("sprints", __name__, url_prefix="/cliente/<cliente>/sprints")

DURACION_ESTIMADO_S = 8      # duración típica de un video del sprint para el costo en vivo
N_REFERENCIAS_ESTIMADO = 3   # referencias por imagen para el estimado


# ------------------------------------------------------------ helpers ---

def _volver(cliente, sid=None, cid=None):
    if cid is not None:
        return redirect(url_for("sprints.campana_ver", cliente=cliente, sid=sid, cid=cid))
    if sid is not None:
        return redirect(url_for("sprints.ver", cliente=cliente, sid=sid))
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="sprints"))


def _quiere_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _entero(campo, defecto=0):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(f"«{campo}» debe ser un número entero.")


def _mood_desde_form():
    return {"paleta": _partir(request.form.get("paleta")), "luz": (request.form.get("luz") or "").strip(),
            "elementos": _partir(request.form.get("elementos"))}


def _productos(cliente):
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion") or "",
             "representativa_url": p.get("representativa_url")} for p in catalogo_productos.listar(cliente, "producto")]


def contexto(cliente):
    """Lo que necesita _tab_sprints.html. Se llama desde dashboard.ver_cliente."""
    prefs = proyectos.preferencias_flowplus(cliente)
    modelo_video, modelo_imagen = prefs["modelo_video"], prefs["modelo_imagen"]
    lista = []
    for sp in datos.sprints(cliente):
        sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
        lista.append(sp)
    pais = proyectos.pais(cliente)
    return {
        "sprints_lista": lista,
        "personas_sprint": datos.personas(cliente),
        "temporadas_sprint": datos.temporadas(cliente),
        "presets_temporadas": calendario.presets(pais),
        "pais_calendario": pais,
        "paises_calendario": proyectos.PAISES_CALENDARIO,
        "productos_sprint": _productos(cliente),
        "destinos_sprint": [{"codigo": f"{p['idioma']}_{codigo}", "nombre": p["nombre"], "bandera": p["bandera"],
                             "idioma": p["idioma"]} for codigo, p in fe_tipos.PAISES.items()],
        "estimado_sprint": {
            "video": float((flowplus_modelos.estimate_video(modelo_video, DURACION_ESTIMADO_S) or {}).get("usd") or 0.0),
            "imagen": float((flowplus_modelos.estimate_imagen(modelo_imagen, N_REFERENCIAS_ESTIMADO) or {}).get("usd") or 0.0),
            "modelo_video": flowplus_modelos.VIDEO[modelo_video]["nombre"],
            "modelo_imagen": flowplus_modelos.IMAGEN[modelo_imagen]["nombre"],
            "duracion_s": DURACION_ESTIMADO_S,
        },
        "intenciones_sprint": datos.INTENCIONES_NOMBRE,
        "tipos_temporada": datos.TIPOS_TEMPORADA,
        "trabajo_sugerir": ({"job_id": tareas_sprints.job_id_sugerir(cliente)}
                            if trabajos.en_curso(tareas_sprints.job_id_sugerir(cliente)) else None),
        "hoy": date.today().isoformat(),
    }


# ----------------------------------------------------------- personas ---

def _campos_persona():
    return dict(resumen=request.form.get("resumen"), descripcion=request.form.get("descripcion"),
                edad_rango=request.form.get("edad_rango"), tono=request.form.get("tono"),
                senales_visuales=_partir(request.form.get("senales_visuales")),
                palabras_clave=_partir(request.form.get("palabras_clave")), color=request.form.get("color") or None)


@bp.post("/personas")
def persona_crear(cliente):
    try:
        datos.crear_persona(cliente, request.form.get("nombre"), **_campos_persona())
        flash("Persona creada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/personas/<int:pid>")
def persona_editar(cliente, pid):
    try:
        campos = {k: v for k, v in _campos_persona().items() if request.form.get(k) is not None}
        if request.form.get("nombre") is not None:
            campos["nombre"] = request.form.get("nombre")
        if not datos.actualizar_persona(cliente, pid, **campos):
            flash("Esa persona no existe.", "error")
        else:
            flash("Persona guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/personas/<int:pid>/archivar")
def persona_archivar(cliente, pid):
    datos.archivar_persona(cliente, pid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/personas/sugerir")
def personas_sugerir(cliente):
    cuantas = min(5, max(1, _entero("cuantas", 3)))
    if tareas_sprints.encolar_sugerir(cliente, cuantas):
        flash("Claude está proponiendo personas; aparecerán aquí en unos segundos.", "ok")
    else:
        flash("Ya hay una sugerencia en curso.", "error")
    return _volver(cliente)


# --------------------------------------------------------- temporadas ---

@bp.post("/temporadas")
def temporada_crear(cliente):
    try:
        datos.crear_temporada(cliente, request.form.get("nombre"), request.form.get("inicio"), request.form.get("fin"),
                              contexto=request.form.get("contexto"), mood_visual=_mood_desde_form(),
                              tipo=request.form.get("tipo") or "propia")
        flash("Temporada creada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>")
def temporada_editar(cliente, tid):
    try:
        campos = {}
        for k in ("nombre", "inicio", "fin", "contexto", "tipo"):
            if request.form.get(k) is not None:
                campos[k] = request.form.get(k)
        if any(request.form.get(k) is not None for k in ("paleta", "luz", "elementos")):
            campos["mood_visual"] = _mood_desde_form()
        if not datos.actualizar_temporada(cliente, tid, **campos):
            flash("Esa temporada no existe.", "error")
        else:
            flash("Temporada guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>/archivar")
def temporada_archivar(cliente, tid):
    datos.archivar_temporada(cliente, tid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/temporadas/adoptar")
def temporada_adoptar(cliente):
    try:
        calendario.adoptar(cliente, request.form.get("clave") or "", pais=proyectos.pais(cliente),
                           anio=request.form.get("anio") or None)
        flash("Temporada agregada desde el calendario.", "ok")
    except (datos.ErrorDatos, ValueError) as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/pais")
def calendario_pais(cliente):
    try:
        proyectos.guardar_pais(cliente, request.form.get("pais"))
    except ValueError as e:
        flash(str(e), "error")
    return _volver(cliente)
