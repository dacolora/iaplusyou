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
import os
from datetime import date

from flask import (Blueprint, abort, flash, has_request_context, jsonify, redirect, render_template, request,
                   session, url_for)

import catalogo_productos
import proyectos
import trabajos
from final_edition import tipos as fe_tipos
from providers import flowplus_modelos
from sprints import archivos, calendario, datos, entrega, estado, ideas, produccion, progreso, revision as revision_mod
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


def _sprint_recien_creado():
    """True una sola vez, en la primera página después de que `crear` tuvo
    éxito: la pestaña lo usa para descartar el borrador del asistente guardado
    en sessionStorage. Fuera de una petición (pruebas, scripts) es False."""
    if not has_request_context():
        return False
    return bool(session.pop("sprint_creado", False))


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
        "calendario_fallback": not calendario.tiene_calendario(pais),
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
        "sprint_recien_creado": _sprint_recien_creado(),
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
    try:
        cuantas = min(5, max(1, _entero("cuantas", 3)))
        if tareas_sprints.encolar_sugerir(cliente, cuantas):
            flash("Claude está proponiendo personas; aparecerán aquí en unos segundos.", "ok")
        else:
            flash("Ya hay una sugerencia en curso.", "error")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
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


# ------------------------------------------------------------ sprints ---

def _sprint_o_404(cliente, sid):
    sp = estado.recalcular(cliente, sid)
    if not sp:
        abort(404)
    return sp


def _campana_o_404(cliente, sid, cid):
    c = datos.campana(cliente, cid)
    if not c or c["sprint_id"] != sid:
        abort(404)
    return c


def _campanas_desde_form():
    """El asistente manda las campañas como JSON en `campanas_json`:
    [{persona_id, catalogo_id, temporada_id, n_videos, n_imagenes, funnel}]. El
    formulario simple manda una sola con los campos sueltos."""
    crudo = request.form.get("campanas_json")
    if crudo:
        try:
            lista = json.loads(crudo)
        except ValueError:
            raise datos.ErrorDatos("Las campañas del asistente no se pudieron leer.")
        if not isinstance(lista, list):
            raise datos.ErrorDatos("Las campañas del asistente no se pudieron leer.")
        return lista
    if request.form.get("persona_id"):
        return [{"persona_id": request.form.get("persona_id"), "catalogo_id": request.form.get("catalogo_id"),
                 "temporada_id": request.form.get("temporada_id"), "n_videos": request.form.get("n_videos"),
                 "n_imagenes": request.form.get("n_imagenes"),
                 "referencias_objetivo": request.form.get("referencias_objetivo"),
                 "funnel": request.form.get("funnel", "tof")}]
    return []


def _validar_campanas(cliente, lista):
    """Producto en el catálogo, cantidades válidas y sin combinaciones
    repetidas dentro del mismo envío. Devuelve la lista normalizada."""
    ids = {p["id"] for p in catalogo_productos.listar(cliente, "producto")}
    vistas, limpias = set(), []
    for i, c in enumerate(lista, 1):
        if not isinstance(c, dict):
            raise datos.ErrorDatos(f"Campaña {i}: formato inválido.")
        try:
            persona_id = int(c.get("persona_id") or 0)
            temporada_id = int(c.get("temporada_id") or 0) if c.get("temporada_id") else 0
        except (TypeError, ValueError):
            raise datos.ErrorDatos(f"Campaña {i}: persona o temporada inválida.")
        if not datos.persona(cliente, persona_id):
            raise datos.ErrorDatos(f"Campaña {i}: esa persona no existe en este proyecto.")
        if temporada_id and not datos.temporada(cliente, temporada_id):
            raise datos.ErrorDatos(f"Campaña {i}: esa temporada no existe en este proyecto.")
        catalogo_id = (c.get("catalogo_id") or "").strip()
        if catalogo_id not in ids:
            raise datos.ErrorDatos(f"Campaña {i}: el producto «{catalogo_id}» no está en el catálogo.")
        try:
            n_videos, n_imagenes = datos.validar_cantidades(c.get("n_videos"), c.get("n_imagenes"))
        except datos.ErrorDatos as e:
            raise datos.ErrorDatos(f"Campaña {i}: {e}")
        funnel = c.get("funnel", "tof")
        if funnel not in datos.FUNNELS:
            raise datos.ErrorDatos(f"Campaña {i}: funnel inválido ({funnel}).")
        clave = (persona_id, catalogo_id, temporada_id)
        if clave in vistas:
            raise datos.ErrorDatos(f"Campaña {i}: esa combinación de persona, producto y temporada está repetida.")
        vistas.add(clave)
        limpias.append({"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id or None,
                        "n_videos": n_videos, "n_imagenes": n_imagenes,
                        "referencias_objetivo": c.get("referencias_objetivo") or None, "funnel": funnel})
    return limpias


@bp.post("/nuevo")
def crear(cliente):
    try:
        campanas = _validar_campanas(cliente, _campanas_desde_form())
        if not campanas:
            raise datos.ErrorDatos("Un sprint necesita al menos una campaña.")
        sid = datos.crear_sprint(cliente, request.form.get("nombre"), request.form.get("inicio"),
                                 request.form.get("fin"), destinos=[d for d in request.form.getlist("destinos") if d],
                                 referencias_objetivo_defecto=request.form.get("referencias_objetivo") or 5,
                                 notas=request.form.get("notas"))
        try:
            for c in campanas:
                datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                      c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        except datos.ErrorDatos:
            datos.archivar_sprint(cliente, sid)
            raise
        estado.recalcular(cliente, sid)
        session["sprint_creado"] = True     # la pestaña descarta el borrador del asistente al volver (contexto)
        flash(f"Sprint creado con {len(campanas)} campaña(s). Ahora sube referencias a cada campaña.", "ok")
        return _volver(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)


@bp.get("/<int:sid>")
def ver(cliente, sid):
    datos.asegurar_personajes_predeterminados(cliente)
    sp = _sprint_o_404(cliente, sid)
    for c in sp["campanas"]:
        c["progreso"] = progreso.progreso_campana(c)
    sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
    productos = _productos(cliente)
    return render_template("sprint_detalle.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, productos_por_id={p["id"]: p for p in productos}, productos_sprint=productos,
                           personas_sprint=datos.personas(cliente), temporadas_sprint=datos.temporadas(cliente),
                           combinaciones=[list(x) for x in datos.combinaciones(cliente, sid)],
                           lote=produccion.progreso(cliente, sid)["sprint"], **_contexto_lote(cliente))


@bp.get("/<int:sid>/progreso")
def progreso_json(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    lote = produccion.progreso(cliente, sid)
    por_campana = {c["id"]: c for c in lote["campanas"]}
    return jsonify({"estado": sp["estado"], "sprint": progreso.progreso_sprint(sp["campanas"]), "lote": lote["sprint"],
                    "campanas": [{"id": c["id"], "estado": c["estado"], **progreso.progreso_campana(c),
                                  "lote": por_campana.get(c["id"], {})} for c in sp["campanas"]]})


@bp.post("/<int:sid>/listo")
def marcar_listo(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    if sp["estado"] in ("generando", "revision", "completado"):
        flash("El sprint ya pasó de la planificación.", "error")
        return _volver(cliente, sid)
    extra = dict(sp.get("extra") or {})
    extra["listo_manual"] = True
    datos.actualizar_sprint(cliente, sid, extra=extra)
    faltantes = [c["id"] for c in sp["campanas"] if c["referencias_listas"] < int(c["referencias_objetivo"] or 1)]
    datos.registrar_evento(cliente, sid, "marcado_listo", "Marcado listo para generar a mano",
                           {"campanas_con_referencias_incompletas": faltantes})
    estado.recalcular(cliente, sid)
    aviso = f" Ojo: {len(faltantes)} campaña(s) no llegan al objetivo de referencias." if faltantes else ""
    flash("Sprint marcado como listo para generar." + aviso, "ok")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/archivar")
def archivar(cliente, sid):
    desarchivar = request.form.get("desarchivar") is not None
    if not datos.archivar_sprint(cliente, sid, archivado=not desarchivar):
        abort(404)
    flash("Sprint desarchivado." if desarchivar else "Sprint archivado.", "ok")
    return _volver(cliente)


@bp.post("/<int:sid>/campanas")
def campana_agregar(cliente, sid):
    _sprint_o_404(cliente, sid)
    try:
        lista = _validar_campanas(cliente, _campanas_desde_form())
        if not lista:
            raise datos.ErrorDatos("Faltan los datos de la campaña.")
        c = lista[0]
        datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                              c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        estado.recalcular(cliente, sid)
        flash("Campaña agregada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/campanas/<int:cid>")
def campana_editar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        campos = {k: request.form.get(k) for k in ("n_videos", "n_imagenes", "referencias_objetivo")
                  if request.form.get(k) is not None}
        datos.actualizar_campana(cliente, cid, **campos)
        estado.recalcular(cliente, sid)
        flash("Campaña guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/campanas/<int:cid>/eliminar")
def campana_eliminar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    datos.eliminar_campana(cliente, cid)
    estado.recalcular(cliente, sid)
    flash("Campaña eliminada.", "ok")
    return _volver(cliente, sid)


# -------------------------------------------------------- referencias ---

def _referencia_o_404(cliente, rid):
    r = datos.referencia(cliente, rid)
    if not r:
        abort(404)
    return r


@bp.get("/<int:sid>/campanas/<int:cid>")
def campana_ver(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = _campana_o_404(cliente, sid, cid)
    refs = datos.referencias(cliente, cid)
    c["progreso"] = progreso.progreso_campana(c)
    otras = [{"campana": oc, "referencias": datos.referencias(cliente, oc["id"])}
             for oc in sp["campanas"] if oc["id"] != cid]
    producto = next((p for p in _productos(cliente) if p["id"] == c["catalogo_id"]), None)
    job_link = tareas_sprints.job_id_link(cliente, cid)
    return render_template("campana_referencias.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, campana=c, referencias=refs, producto=producto, otras_campanas=otras,
                           intenciones_sprint=datos.INTENCIONES_NOMBRE, cobertura=progreso.cobertura(c, refs),
                           trabajo_link={"job_id": job_link} if trabajos.en_curso(job_link) else None)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias")
def referencias_subir(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    link = (request.form.get("link") or "").strip()
    intencion = request.form.getlist("intencion")
    subidas, rechazadas, fallidas = 0, 0, 0
    for archivo in request.files.getlist("archivos"):
        if not archivo or not archivo.filename:
            continue
        try:
            info = archivos.guardar_subida(cliente, archivo)
        except Exception:
            fallidas += 1
            continue
        if not info:
            rechazadas += 1
            continue
        try:
            rid = datos.agregar_referencia(cliente, cid, info["tipo"], info["url"], frame_url=info["frame_url"],
                                           ruta_local=info["ruta_local"], origen="archivo", titulo=info["titulo"],
                                           intencion=intencion)
        except datos.ErrorDatos as e:
            flash(str(e), "error")
            continue
        tareas_sprints.encolar_analisis(cliente, rid)
        subidas += 1
    if link:
        if tareas_sprints.encolar_link(cliente, cid, link):
            flash("Descargando el link; la referencia aparecerá en unos segundos.", "ok")
        else:
            flash("Ya hay un link descargándose para esta campaña.", "error")
    if subidas:
        flash(f"{subidas} referencia(s) subida(s). Cuéntanos qué reutilizar de cada una.", "ok")
    if rechazadas:
        flash(f"{rechazadas} archivo(s) no son imagen ni video (jpg, png, webp, mp4, mov, webm).", "error")
    if fallidas:
        flash(f"{fallidas} archivo(s) no se pudieron guardar.", "error")
    estado.recalcular(cliente, sid)
    if _quiere_json():
        return jsonify({"ok": True, "subidas": subidas, "rechazadas": rechazadas})
    return _volver(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/catalogo")
def referencias_catalogo(cliente, sid, cid):
    """Trae las fotos reales del producto de la campaña como referencias
    (origen catalogo), con intención ángulo de producto y descripción
    automática — cuentan como listas desde el primer momento."""
    c = _campana_o_404(cliente, sid, cid)
    producto = catalogo_productos.encontrar(cliente, c["catalogo_id"], "producto")
    if not producto:
        flash("El producto de la campaña ya no está en el catálogo.", "error")
        return _volver(cliente, sid, cid)
    existentes = {r["url"] for r in datos.referencias(cliente, cid)}
    base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    carpeta = catalogo_productos.CATEGORIAS["producto"]["carpeta"]
    nuevas = 0
    for nombre in producto.get("imagenes") or []:
        url = f"{base}/clientes/{cliente}/{carpeta}/{producto['id']}/{nombre}"
        if url in existentes:
            continue
        rid = datos.agregar_referencia(cliente, cid, "imagen", url, origen="catalogo", titulo=nombre,
                                       intencion=["angulo_producto"],
                                       descripcion=f"Foto real del producto {producto['nombre']}, tal como es.")
        tareas_sprints.encolar_analisis(cliente, rid)
        nuevas += 1
    flash(f"{nuevas} foto(s) del producto traídas del catálogo." if nuevas else "Las fotos del producto ya estaban.", "ok")
    estado.recalcular(cliente, sid)
    return _volver(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/reutilizar")
def referencias_reutilizar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        datos.reutilizar_referencia(cliente, _entero("referencia_id"), cid)
        flash("Referencia reutilizada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    estado.recalcular(cliente, sid)
    return _volver(cliente, sid, cid)


@bp.get("/<int:sid>/campanas/<int:cid>/referencias/estado")
def referencias_estado(cliente, sid, cid):
    c = _campana_o_404(cliente, sid, cid)
    return jsonify({"listas": c["referencias_listas"], "objetivo": c["referencias_objetivo"],
                    "referencias": [{"id": r["id"], "analisis_estado": r["analisis_estado"], "analisis": r["analisis"],
                                     "estado": r["estado"]} for r in datos.referencias(cliente, cid)]})


@bp.post("/referencias/<int:rid>")
def referencia_editar(cliente, rid):
    """Autoguardado de la tarjeta (JSON por fetch) o formulario clásico."""
    r = _referencia_o_404(cliente, rid)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": "El cuerpo debe ser un objeto JSON."}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {}
    if "descripcion" in fuente:
        campos["descripcion"] = fuente.get("descripcion")
    if "intencion" in fuente:
        campos["intencion"] = fuente.get("intencion") if cuerpo is not None else request.form.getlist("intencion")
    if "intencion_otro" in fuente:
        campos["intencion_otro"] = fuente.get("intencion_otro")
    if "titulo" in fuente:
        campos["titulo"] = fuente.get("titulo")
    # Un JSON con el tipo equivocado (número donde va texto, texto donde va lista)
    # es un error de formato, no un dato inválido: se corta antes de tocar datos.
    if (any(campos.get(k) is not None and not isinstance(campos[k], str)
            for k in ("descripcion", "intencion_otro", "titulo") if k in campos)
            or ("intencion" in campos and not isinstance(campos["intencion"], list))):
        if es_json:
            return jsonify({"ok": False, "error": "Formato inválido."}), 400
        flash("Formato inválido.", "error")
        return _volver(cliente, r["sprint_id"], r["campana_id"])
    try:
        datos.actualizar_referencia(cliente, rid, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, r["sprint_id"], r["campana_id"])
    sp = estado.recalcular(cliente, r["sprint_id"])
    c = next((x for x in sp["campanas"] if x["id"] == r["campana_id"]), None)
    if es_json:
        nueva = datos.referencia(cliente, rid)
        return jsonify({"ok": True, "estado": nueva["estado"],
                        "referencias_listas": c["referencias_listas"] if c else 0,
                        "referencias_objetivo": c["referencias_objetivo"] if c else 0,
                        "estado_sprint": sp["estado"]})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/quitar")
def referencia_quitar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    datos.quitar_referencia(cliente, rid)
    estado.recalcular(cliente, r["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/reanalizar")
def referencia_reanalizar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    datos.actualizar_referencia(cliente, rid, analisis_estado="pendiente")
    tareas_sprints.encolar_analisis(cliente, rid)
    if _quiere_json():
        return jsonify({"ok": True})
    flash("Analizando de nuevo.", "ok")
    return _volver(cliente, r["sprint_id"], r["campana_id"])


# -------------------------------------------------------------- ideas ---

def _idea_o_404(cliente, cp_id, sid=None):
    i = datos.idea(cliente, cp_id)
    if not i or (sid is not None and i["sprint_id"] != sid):
        abort(404)
    return i


def _contexto_lote(cliente):
    mv, mi = produccion.modelos(cliente)
    return {"modelos_video": flowplus_modelos.VIDEO, "modelos_imagen": flowplus_modelos.IMAGEN,
            "modelo_video_defecto": mv, "modelo_imagen_defecto": mi}


@bp.get("/<int:sid>/campanas/<int:cid>/ideas")
def campana_ideas(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = _campana_o_404(cliente, sid, cid)
    refs = {r["id"]: r for r in datos.referencias(cliente, cid)}
    lista = datos.ideas(cliente, cid)
    vivas = [i for i in lista if i["estado_idea"] != "descartada"]
    faltan_v, faltan_i = ideas.faltantes(c)
    conteo = {"videos_aprobados": sum(1 for i in vivas if i["tipo"] == "video" and i["estado_idea"] == "aprobada"),
              "imagenes_aprobadas": sum(1 for i in vivas if i["tipo"] == "imagen" and i["estado_idea"] == "aprobada"),
              "faltan_videos": faltan_v, "faltan_imagenes": faltan_i,
              "pendientes_lote": sum(1 for i in vivas if i["estado_idea"] == "aprobada" and i["sin_sesion"])}
    job = tareas_sprints.job_id_ideas(cliente, cid)
    return render_template("campana_ideas.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, campana=c, ideas=lista, referencias_por_id=refs, conteo=conteo,
                           enfoques=flowplus_prompt_enfoques(), trabajo_ideas={"job_id": job} if trabajos.en_curso(job) else None,
                           **_contexto_lote(cliente))


def flowplus_prompt_enfoques():
    import flowplus_prompt
    return {k: v["nombre"] for k, v in flowplus_prompt.ENFOQUES.items()}


@bp.post("/<int:sid>/campanas/<int:cid>/ideas/proponer")
def ideas_proponer(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        if request.form.get("mas"):
            n_v, n_i = _entero("mas", 3), 0
            if request.form.get("tipo") == "imagen":
                n_v, n_i = 0, _entero("mas", 3)
        else:
            n_v = _entero("n_videos") if request.form.get("n_videos") else None
            n_i = _entero("n_imagenes") if request.form.get("n_imagenes") else None
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))
    if tareas_sprints.encolar_ideas(cliente, cid, n_videos=n_v, n_imagenes=n_i):
        flash("Claude está proponiendo ideas; aparecerán aquí en unos segundos.", "ok")
    else:
        flash("Ya hay una propuesta de ideas en curso para esta campaña.", "error")
    return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))


@bp.post("/<int:sid>/campanas/<int:cid>/ideas/aprobar_todas")
def ideas_aprobar_todas(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    n = 0
    for i in datos.ideas(cliente, cid, incluir_descartadas=False):
        if i["estado_idea"] == "propuesta":
            datos.actualizar_idea(cliente, i["id"], estado_idea="aprobada")
            n += 1
    estado.recalcular(cliente, sid)
    flash(f"{n} idea(s) aprobada(s).", "ok")
    return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))


def _volver_ideas(i):
    return redirect(url_for("sprints.campana_ideas", cliente=i["cliente"], sid=i["sprint_id"], cid=i["campana_id"]))


@bp.post("/ideas/<int:cp_id>")
def idea_editar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": "El cuerpo debe ser un objeto JSON."}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {k: fuente.get(k) for k in ("titulo", "escena", "sonido", "gancho") if k in fuente}
    if any(v is not None and not isinstance(v, str) for v in campos.values()):
        if es_json:
            return jsonify({"ok": False, "error": "Formato inválido."}), 400
        flash("Formato inválido.", "error")
        return _volver_ideas(i)
    try:
        if "titulo" in campos and not (campos["titulo"] or "").strip():
            raise datos.ErrorDatos("Una idea necesita título.")
        if "escena" in campos and not (campos["escena"] or "").strip():
            raise datos.ErrorDatos("Una idea necesita escena.")
        datos.actualizar_idea(cliente, cp_id, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver_ideas(i)
    if es_json:
        return jsonify({"ok": True})
    flash("Idea guardada.", "ok")
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/aprobar")
def idea_aprobar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    datos.actualizar_idea(cliente, cp_id, estado_idea="aprobada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


MENSAJE_IDEA_CON_PIEZA = "Esa idea ya tiene una pieza generada; usa Regenerar desde la revisión."


@bp.post("/ideas/<int:cp_id>/descartar")
def idea_descartar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    # E3: con sesión (o reserva viva) la pieza está en marcha y descartar la
    # idea la sacaría de los conteos; el botón está oculto, pero la petición
    # puede fabricarse. Una reserva vencida no es sesión (`sin_sesion`).
    if not i["sin_sesion"]:
        if _quiere_json():
            return jsonify({"ok": False, "error": MENSAJE_IDEA_CON_PIEZA}), 400
        flash(MENSAJE_IDEA_CON_PIEZA, "error")
        return _volver_ideas(i)
    datos.actualizar_idea(cliente, cp_id, estado_idea="descartada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/otra")
def idea_otra(cliente, cp_id):
    """Pide otra idea del mismo tipo en lugar de esta (una sola). Descartar
    la vieja lo hace la tarea (`ideas.proponer(reemplaza=)`) al reemplazarla:
    si no se puede encolar (ya hay una propuesta en curso para la campaña),
    la idea no se toca — antes se descartaba primero y quedaba sin
    reemplazo."""
    i = _idea_o_404(cliente, cp_id)
    if not i["sin_sesion"]:
        flash(MENSAJE_IDEA_CON_PIEZA, "error")
        return _volver_ideas(i)
    if tareas_sprints.encolar_ideas(cliente, i["campana_id"], reemplaza=cp_id):
        flash("Pidiendo otra idea…", "ok")
    else:
        flash("Ya hay una propuesta en curso; espera a que termine.", "error")
    return _volver_ideas(i)


# --------------------------------------------------------------- lote ---

@bp.get("/<int:sid>/lote/estimar")
def lote_estimar(cliente, sid):
    _sprint_o_404(cliente, sid)
    cid = request.args.get("campana_id", type=int)
    try:
        return jsonify(produccion.estimar(cliente, sid, campana_id=cid, modelo_video=request.args.get("modelo_video"),
                                          modelo_imagen=request.args.get("modelo_imagen")))
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.post("/<int:sid>/lote")
def lote(cliente, sid):
    """Puerta de gasto: el modal ya mostró el costo; aquí se encola."""
    _sprint_o_404(cliente, sid)
    cid = request.form.get("campana_id", type=int)
    try:
        r = produccion.lanzar_lote(cliente, sid, campana_id=cid, modelo_video=request.form.get("modelo_video"),
                                   modelo_imagen=request.form.get("modelo_imagen"))
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, sid)
    if r["encoladas"]:
        flash(f"Lote encolado: {r['encoladas']} pieza(s), USD {r['usd']:.2f} estimado. Te avisamos por correo al terminar si está configurado.", "ok")
    else:
        flash("No había ideas aprobadas sin generar." if not r["omitidas"] else "Esas piezas ya se estaban generando.", "warn")
    return _volver(cliente, sid)


def _volver_pieza(cliente, i):
    """A la bandeja si el formulario vino de ahí (`volver=revision`); si no,
    al sprint."""
    if request.form.get("volver") == "revision":
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    return _volver(cliente, i["sprint_id"])


@bp.post("/ideas/<int:cp_id>/reintentar")
def pieza_reintentar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        ok = produccion.reintentar(cliente, cp_id)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    flash("Reintentando la pieza." if ok else "Esa pieza no está en error o ya se está generando.", "ok" if ok else "warn")
    return _volver_pieza(cliente, i)


@bp.post("/ideas/<int:cp_id>/regenerar")
def pieza_regenerar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        produccion.regenerar(cliente, cp_id)
    except (datos.ErrorDatos, ValueError) as e:
        # ValueError: `creative_flow.duplicar` con una sesión que no existe
        # (cf_id colgado o placeholder) — se muestra como un ErrorDatos.
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    flash("Regenerando la pieza (sesión nueva, misma idea).", "ok")
    return _volver_pieza(cliente, i)


# ----------------------------------------------------------- revisión ---

CHECKS_QA = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")


def _piezas_revision(cliente, sp):
    """Piezas con sesión de todas las campañas, con su costo de regeneración
    (estimado gratis, el mismo que muestra el botón antes de gastar)."""
    mv, mi = produccion.modelos(cliente)
    salida = []
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p["tipo"] == "video":
                costo = (flowplus_modelos.estimate_video(mv, produccion._duracion(p)) or {}).get("usd") or 0.0
            else:
                costo = (flowplus_modelos.estimate_imagen(mi, n_referencias=produccion._n_referencias(cliente, c)) or {}).get("usd") or 0.0
            salida.append({**p, "campana_n": int(c["orden"]) + 1, "persona_nombre": c["persona_nombre"],
                           "temporada_nombre": c["temporada_nombre"], "catalogo_id": c["catalogo_id"],
                           "costo_regenerar": round(float(costo), 3)})
    return salida


@bp.get("/<int:sid>/revision")
def revision(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    piezas = _piezas_revision(cliente, sp)
    return render_template("sprint_revision.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, piezas=piezas, resumen=revision_mod.resumen(cliente, sid), checks=CHECKS_QA)


@bp.post("/ideas/<int:cp_id>/revision")
def pieza_revision(cliente, cp_id):
    """Aprobar o rechazar una pieza (JSON por fetch desde la bandeja, o
    formulario clásico). Rechazar exige motivo."""
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": "El cuerpo debe ser un objeto JSON."}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    accion, motivo = fuente.get("accion"), fuente.get("motivo")
    try:
        if accion == "aprobar":
            ok = revision_mod.aprobar(cliente, cp_id)
        elif accion == "rechazar":
            ok = revision_mod.rechazar(cliente, cp_id, motivo if isinstance(motivo, str) else "")
        else:
            raise datos.ErrorDatos("Acción desconocida.")
        if not ok:
            raise datos.ErrorDatos("Esa pieza todavía no está terminada.")
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    nueva = datos.idea(cliente, cp_id)
    if es_json:
        return jsonify({"ok": True, "revision": nueva["revision"],
                        "estado_sprint": (datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}).get("estado")})
    flash("Pieza aprobada." if accion == "aprobar" else "Pieza rechazada.", "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))


@bp.post("/ideas/<int:cp_id>/qa")
def pieza_qa(cliente, cp_id):
    """«Repetir QA»: limpia el marcador (`qa=None`) y encola un solo
    `sprint_qa_pieza` para la sesión actual. Solo visión (centavos), nunca
    generación: sin puerta de costo."""
    i = _idea_o_404(cliente, cp_id)
    destino = redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    if not i.get("cf_id") or i.get("estado") not in revision_mod.TERMINADAS:
        flash("Esa pieza todavía no está lista para el QA.", "error")
        return destino
    datos.actualizar_idea(cliente, cp_id, qa=None)
    if tareas_sprints.encolar_qa(cliente, cp_id):
        flash("Repitiendo el QA de la pieza; el resultado aparecerá aquí en unos segundos.", "ok")
    else:
        flash("Ya hay un QA en curso para esa pieza.", "warn")
    return destino


@bp.post("/<int:sid>/revision/aprobar_qa")
def revision_aprobar_qa(cliente, sid):
    _sprint_o_404(cliente, sid)
    n = revision_mod.aprobar_pasaron_qa(cliente, sid)
    flash(f"{n} pieza(s) aprobada(s) por haber pasado el QA.", "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/cerrar")
def cerrar(cliente, sid):
    _sprint_o_404(cliente, sid)
    try:
        r = revision_mod.cerrar(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, sid)
    flash(f"Sprint cerrado: {r['aprobadas']} aprobadas, {r['rechazadas']} rechazadas, USD {r['costo_usd']:.2f}.", "ok")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/reabrir")
def reabrir(cliente, sid):
    _sprint_o_404(cliente, sid)
    if revision_mod.reabrir(cliente, sid):
        flash("Sprint reabierto a revisión.", "ok")
    else:
        flash("Solo se reabre un sprint completado.", "error")
    return _volver(cliente, sid)


# ------------------------------------------------------------ entrega ---

def entrega_ver(cliente, sid):
    """Se llama `entrega_ver` para no pisar el módulo `entrega` importado
    arriba; el endpoint sigue siendo `sprints.entrega` (add_url_rule)."""
    sp = _sprint_o_404(cliente, sid)
    job = tareas_sprints.job_id_zip(cliente, sid)
    return render_template("sprint_entrega.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, enlaces=entrega.enlaces(cliente, sid), resumen=revision_mod.resumen(cliente, sid),
                           zip_info=(sp.get("extra") or {}).get("zip"),
                           trabajo_zip={"job_id": job} if trabajos.en_curso(job) else None)


bp.add_url_rule("/<int:sid>/entrega", endpoint="entrega", view_func=entrega_ver, methods=["GET"])


@bp.post("/<int:sid>/entrega/zip")
def entrega_zip(cliente, sid):
    _sprint_o_404(cliente, sid)
    if not entrega.enlaces(cliente, sid):
        flash("No hay piezas aprobadas que entregar.", "error")
    elif tareas_sprints.encolar_zip(cliente, sid):
        flash("Armando el zip; el enlace aparecerá aquí al terminar.", "ok")
    else:
        flash("Ya se está armando el zip.", "warn")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))
