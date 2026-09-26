"""
Blueprint del pipeline de Flow Plus (spec 2026-09-25 §10): el panel de
guiones como fragmento HTML que arma el servidor (Jinja escapa todo) y las
acciones como POST JSON. Mismo prefijo y mismas reglas que guiones/rutas.py
(el chat): mismo origen en todo POST, cuerpo JSON obligatorio, errores en
español, 404 para lo de otro proyecto.
"""
from flask import Blueprint, Response, jsonify, render_template, request, session

import catalogo_productos
import gastos
import proyectos
import trabajos
import usuarios
from guiones import clips, config, datos, duracion, imagenes, lectura, notion, plantillas, recorte, refinador
from guiones.refinador import Conflicto, DatoInvalido, ErrorRefinador, NoExiste
from guiones.rutas import _cuerpo, _entero, _error, _sin_cuerpo, _solo_mismo_origen
from providers import flowplus_modelos

bp = Blueprint("guiones_pipeline", __name__, url_prefix="/cliente/<cliente>/guiones")
bp.before_request(_solo_mismo_origen)


def _costo(paso, palabras=0):
    return gastos.estimar("guion_clips", paso=paso, palabras=palabras)["texto"]


def _contexto(cliente, guion_id=None, video_id=None):
    g = datos.guion(cliente, guion_id) if guion_id else None
    v = datos.video(cliente, video_id) if (g and video_id) else None
    if v is not None and v["guion_id"] != g["id"]:
        v = None
    ctx = {"cliente": cliente, "lotes": datos.lotes(cliente), "guion": g, "video": v,
           "notion_conectado": notion.conectado(cliente),
           "costos": {"leer": _costo("leer", 750), "recorte": _costo("recorte")}}
    if g and g["estado"] == "confirmado":
        ctx["activos"] = {t: [{"id": a["id"], "nombre": a["nombre"]} for a in catalogo_productos.listar(cliente, t)]
                          for t in config.TIPOS_REF}
        ctx["formatos"] = flowplus_modelos.FORMATOS_NOMBRES
        ctx["config_defecto"] = config.defecto(cliente)
    if v is not None:
        ctx["recorte_info"] = recorte.resumen(v)
    if g and g["estado"] == "confirmado":
        propio = proyectos.bloque_global_flowplus(cliente)
        ctx["bloque_global"] = {"texto": propio or plantillas.BLOQUE_GLOBAL_FABRICA, "propio": bool(propio)}
    if v is not None:
        textos = duracion.textos_efectivos(v["guion"]["lectura"], v["config"].get("hook", "original"))
        palabras = sum(duracion.palabras(t) for _, t in duracion.conservadas(textos, v["recorte"].get("quitadas", [])))
        ctx["costos"]["armar"] = _costo("armar", palabras)
        ctx["prompts"] = {f"{(p['extra'] or {}).get('variante')}:{(p['extra'] or {}).get('clip_index')}":
                          {"id": p["id"], "estado": p["estado"]}
                          for p in datos.prompts_de_video(v["id"]) if p["tipo"] == "clip"}
        ctx["costos"]["imagenes"] = _costo("imagenes")
        todos = datos.prompts_de_video(v["id"])
        ctx["prompts_img"] = {(p["extra"] or {}).get("imagen_id"): {"id": p["id"], "estado": p["estado"]}
                              for p in todos if p["tipo"] == "imagen"}
        ctx["checklist"] = imagenes.checklist(v["config"], (v["imagenes"] or {}).get("lista", []), todos)
    return ctx


@bp.get("/panel")
def panel(cliente):
    ctx = _contexto(cliente, _entero(request.args.get("guion") or ""), _entero(request.args.get("video") or ""))
    return render_template("_gpg_panel.html", **ctx)


def _lanzar_lectura(lote_id):
    trabajos.iniciar(f"guion_leer_{lote_id}", lambda: lectura.leer_lote(lote_id), duracion_estimada=60)


@bp.post("/lotes")
def lote_crear(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        if str(cuerpo.get("notion_url") or "").strip():
            if not notion.conectado(cliente):
                raise Conflicto("Conecta Notion primero.")
            page_id = notion.extraer_id(cuerpo["notion_url"])
            if not page_id:
                raise DatoInvalido("Ese link no parece de una página de Notion.")
            lote_id = datos.crear_lote(cliente, "", fuente="notion", notion_page_id=page_id)
        else:
            lote_id = datos.crear_lote(cliente, cuerpo.get("texto"))
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(lote_id)
    return jsonify({"lote_id": lote_id}), 202


def _correo_verificado():
    """Mismo criterio que dashboard._requiere_correo_verificado: admin, o cliente con correo verificado."""
    if session.get("rol") == "admin":
        return True
    entry = usuarios.obtener(session.get("usuario") or "")
    return bool(entry and entry.get("correo_verificado"))


@bp.get("/notion")
def notion_estado(cliente):
    return jsonify({"conectado": notion.conectado(cliente)})


@bp.post("/notion")
def notion_conectar(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    if not _correo_verificado():
        return jsonify({"error": "Confirma tu correo primero (Configuración › Cuenta)."}), 403
    llave = str(cuerpo.get("llave") or "").strip()
    if not llave or len(llave) > 200:
        return jsonify({"error": "Pega la llave de tu integración de Notion."}), 400
    try:
        notion.probar(llave)
    except notion.ErrorNotion as e:
        return jsonify({"error": str(e)}), 400
    notion.guardar_llave(cliente, llave)
    return jsonify({"ok": True})


@bp.post("/notion/borrar")
def notion_borrar(cliente):
    if _cuerpo() is None:
        return _sin_cuerpo()
    notion.borrar(cliente)
    return jsonify({"ok": True})


@bp.post("/lotes/<int:lid>/reintentar")
def lote_reintentar(cliente, lid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.reintentar_lote(cliente, lid)
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(lid)
    return jsonify({"lote_id": lid}), 202


def _guion_o_404(cliente, gid):
    g = datos.guion(cliente, gid)
    if g is None:
        raise NoExiste("Ese guion no existe.")
    return g


@bp.post("/guiones/<int:gid>/lectura")
def guion_lectura(cliente, gid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        g = _guion_o_404(cliente, gid)
        datos.guardar_lectura(cliente, gid, lectura.desde_formulario(cuerpo, g["lectura"], g["texto_crudo"]))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": gid})


@bp.post("/guiones/<int:gid>/confirmar")
def guion_confirmar(cliente, gid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.confirmar(cliente, gid)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": gid})


@bp.post("/guiones/<int:gid>/duplicar")
def guion_duplicar(cliente, gid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        nuevo = datos.duplicar(cliente, gid)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": nuevo}), 201


def _video_o_404(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        raise NoExiste("Esa versión no existe.")
    return v


@bp.post("/guiones/<int:gid>/videos")
def video_crear(cliente, gid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        g = _guion_o_404(cliente, gid)
        vid = datos.crear_video(cliente, gid, config.desde_formulario(cliente, cuerpo, g["lectura"]))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": gid, "video_id": vid}), 201


@bp.post("/videos/<int:vid>/config")
def video_config(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
        datos.guardar_config(cliente, vid, config.desde_formulario(cliente, cuerpo, v["guion"]["lectura"]))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


@bp.post("/videos/<int:vid>/calcular")
def video_calcular(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
    except ErrorRefinador as e:
        return _error(e)
    quitadas = cuerpo.get("quitadas") if isinstance(cuerpo.get("quitadas"), list) else []
    return jsonify(recorte.resumen(v, quitadas=quitadas))


@bp.post("/videos/<int:vid>/recorte/proponer")
def video_recorte_proponer(cliente, vid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
        if not v["config"].get("duracion_objetivo"):
            raise Conflicto("Pon una duración objetivo para poder recortar.")
        datos.empezar(cliente, vid, "recortando", ("configurando",))
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_recorte_{vid}", lambda: recorte.proponer(vid), duracion_estimada=40)
    return jsonify({"video_id": vid}), 202


@bp.post("/videos/<int:vid>/recorte")
def video_recorte(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    quitadas = cuerpo.get("quitadas") if isinstance(cuerpo.get("quitadas"), list) else []
    try:
        datos.guardar_quitadas(cliente, vid, quitadas)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


@bp.post("/videos/<int:vid>/armar")
def video_armar(cliente, vid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.empezar(cliente, vid, "armando", ("configurando", "invalido", "error"))
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_armar_{vid}", lambda: clips.armar(vid), duracion_estimada=120)
    return jsonify({"video_id": vid}), 202


@bp.post("/videos/<int:vid>/nueva-version")
def video_nueva_version(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
        if cuerpo.get("tipo") == "bloque":
            bloque = {k: cuerpo.get(f"bloque_{k}") for k in clips.DEFECTOS_BLOQUE}
            nuevo = clips.version_con_bloque(cliente, vid, bloque)
        else:
            nuevo = datos.nueva_version(cliente, vid, config=config.desde_formulario(cliente, cuerpo, v["guion"]["lectura"]))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": v["guion_id"], "video_id": nuevo}), 201


@bp.get("/videos/<int:vid>")
def video_ver(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        return jsonify({"error": "Esa versión no existe."}), 404
    prompts = [{k: p[k] for k in ("id", "titulo", "tipo", "estado", "extra")} for p in datos.prompts_de_video(vid)]
    return jsonify({"video": v, "prompts": prompts})


@bp.get("/videos/<int:vid>/documento.md")
def video_documento(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        return jsonify({"error": "Esa versión no existe."}), 404
    if v["estado"] != "armado":
        return jsonify({"error": "El documento sale cuando la versión está armada."}), 409
    md = plantillas.documento_md(v, datos.prompts_de_video(vid))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{plantillas.nombre_documento(v)}"'})


@bp.post("/videos/<int:vid>/imagenes")
def video_imagenes(cliente, vid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.empezar_imagenes(cliente, vid)
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_imagenes_{vid}", lambda: imagenes.escribir(vid), duracion_estimada=60)
    return jsonify({"video_id": vid}), 202


@bp.get("/videos/<int:vid>/imagenes.md")
def video_imagenes_md(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        return jsonify({"error": "Esa versión no existe."}), 404
    if v["estado_imagenes"] != "listo":
        return jsonify({"error": "Primero escribe los prompts de imágenes."}), 409
    md = imagenes.documento_md(v, datos.prompts_de_video(vid))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{imagenes.nombre_documento(v)}"'})


@bp.get("/bloque-global")
def bloque_global_ver(cliente):
    propio = proyectos.bloque_global_flowplus(cliente)
    return jsonify({"texto": propio or plantillas.BLOQUE_GLOBAL_FABRICA, "propio": bool(propio)})


@bp.post("/bloque-global")
def bloque_global_guardar(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    texto = str(cuerpo.get("texto") or "").strip()[:8000]
    if texto:
        problemas = refinador.validar(texto, (), "clip")
        if problemas:
            return jsonify({"error": "El bloque global rompe reglas que no se negocian.", "problemas": problemas}), 422
    proyectos.guardar_bloque_global_flowplus(cliente, texto)
    return jsonify({"ok": True})
