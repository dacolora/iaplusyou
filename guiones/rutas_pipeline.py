"""
Blueprint del pipeline de Flow Plus (spec 2026-09-25 §10): el panel de
guiones como fragmento HTML que arma el servidor (Jinja escapa todo) y las
acciones como POST JSON. Mismo prefijo y mismas reglas que guiones/rutas.py
(el chat): mismo origen en todo POST, cuerpo JSON obligatorio, errores en
español, 404 para lo de otro proyecto.
"""
import os

from flask import Blueprint, Response, flash, jsonify, render_template, request, session, url_for
from flask_babel import gettext

import catalogo_productos
import db
import gastos
import proyectos
import referencias_flowplus
import tiendas
import trabajos
import usuarios
from cobros import SaldoInsuficiente, libro
from final_edition import biblioteca
from guiones import cadena, clips, config, datos, duracion, escenas, imagenes, lectura, medios, notion, plantillas, recorte, refinador
from guiones.refinador import Conflicto, DatoInvalido, ErrorRefinador, NoExiste
from guiones.rutas import _cuerpo, _entero, _error, _sin_cuerpo, _solo_mismo_origen
from providers import flowplus_modelos
from storage import r2_uploader
from tareas.cadena import PRIORIDAD_CADENA, fallar_cadena, job_id as job_cadena

bp = Blueprint("guiones_pipeline", __name__, url_prefix="/cliente/<cliente>/guiones")
bp.before_request(_solo_mismo_origen)


def _costo(paso, palabras=0):
    return gastos.estimar("guion_clips", paso=paso, palabras=palabras)["texto"]


def _exigir(cliente, paso, palabras=0):
    """Cobros (spec 2026-10-08 §5.2): los pasos con Claude corren en un hilo de
    esta misma petición (`trabajos.iniciar`), no en el worker: el saldo se pide
    aquí, antes de cambiar el estado y de lanzar el hilo. Sin saldo,
    SaldoInsuficiente y el manejador común responde 402."""
    libro.exigir(cliente, gastos.estimar("guion_clips", paso=paso, palabras=palabras)["usd"])


def _palabras(v):
    """Palabras que se le mandan a Claude al armar (las mismas del precio del botón)."""
    textos = duracion.textos_efectivos(v["guion"]["lectura"], v["config"].get("hook", "original"))
    return sum(duracion.palabras(t) for _, t in duracion.conservadas(textos, v["recorte"].get("quitadas", [])))


def _catalogo_para_elegir(cliente, en_uso):
    """{tipo: activos del Catálogo} para las referencias de la configuración y
    las fotos del Catálogo de las escenas: sin productos archivados
    (2026-10-01), salvo los que las referencias `en_uso` ({tipo, activo_id})
    ya nombran — si no, la versión perdería su producto al guardarse."""
    catalogo = {t: catalogo_productos.listar(cliente, t) for t in config.TIPOS_REF}
    if catalogo.get("producto"):
        usados = [r.get("activo_id") for r in en_uso or () if isinstance(r, dict) and r.get("tipo") == "producto"]
        catalogo["producto"] = catalogo_productos.sin_archivados(catalogo["producto"],
                                                                 tiendas.activos_archivados(cliente), usados)
    return catalogo


def _contexto(cliente, guion_id=None, video_id=None):
    g = datos.guion(cliente, guion_id) if guion_id else None
    v = datos.video(cliente, video_id) if (g and video_id) else None
    if v is not None and v["guion_id"] != g["id"]:
        v = None
    if g is not None:
        # `nombre` (guardado) queda tal cual en la base; `etiqueta` es la
        # misma versión traducida para quien mira, calculada acá porque la
        # ruta siempre corre dentro de una petición (nunca se guarda).
        for x in g["videos"]:
            x["etiqueta"] = datos.etiqueta_version(x.get("config"), x["version_n"])
    if v is not None:
        v["etiqueta"] = datos.etiqueta_version(v["config"], v["version_n"])
    ctx = {"cliente": cliente, "lotes": datos.lotes(cliente), "guion": g, "video": v,
           "notion_conectado": notion.conectado(cliente),
           "costos": {"leer": _costo("leer", 750), "recorte": _costo("recorte")}}
    catalogo = {}
    if g and g["estado"] == "confirmado":
        defecto = config.defecto(cliente)
        en_uso = list(defecto.get("referencias") or []) + list(((v or {}).get("config") or {}).get("referencias") or [])
        catalogo = _catalogo_para_elegir(cliente, en_uso)
        ctx["activos"] = {t: [{"id": a["id"], "nombre": a["nombre"]} for a in lista] for t, lista in catalogo.items()}
        ctx["formatos"] = flowplus_modelos.FORMATOS_NOMBRES
        ctx["config_defecto"] = defecto
    if v is not None:
        ctx["recorte_info"] = recorte.resumen(v)
    if g and g["estado"] == "confirmado":
        propio = proyectos.bloque_global_flowplus(cliente)
        ctx["bloque_global"] = {"texto": propio or plantillas.BLOQUE_GLOBAL_FABRICA, "propio": bool(propio)}
    if v is not None:
        ctx["costos"]["armar"] = _costo("armar", _palabras(v))
        ctx["prompts"] = {f"{(p['extra'] or {}).get('variante')}:{(p['extra'] or {}).get('clip_index')}":
                          {"id": p["id"], "estado": p["estado"]}
                          for p in datos.prompts_de_video(v["id"]) if p["tipo"] == "clip"}
        ctx["costos"]["imagenes"] = _costo("imagenes")
        todos = datos.prompts_de_video(v["id"])
        ctx["prompts_img"] = {(p["extra"] or {}).get("imagen_id"): {"id": p["id"], "estado": p["estado"]}
                              for p in todos if p["tipo"] == "imagen"}
        ctx["checklist"] = imagenes.checklist(v["config"], (v["imagenes"] or {}).get("lista", []), todos,
                                              escenas.refs_con_imagen(v))
        if v["estado"] == "armado":
            ctx["escenas"] = _vista_escenas(cliente, v, catalogo)
            ctx["cadena_vista"] = _vista_cadena(v, ctx["prompts"])
    return ctx


def _vista_cadena(v, prompts):
    """Lo que muestra «Generar todas las escenas»: revisión, precio, estado de cada escena y desde dónde rehacer."""
    est = cadena.estado(v)
    ks = cadena.indices(v)
    conocidos = list(((est or {}).get("elementos") or {}).keys())
    corriendo = bool(est and est["estado"] == "corriendo")
    vista = {"estado": est, "corriendo": corriendo, "revision": [], "avisos": cadena.avisos(v), "precio": None,
             "filas": [], "total": len(ks)}
    if not corriendo:
        vista["revision"] = cadena.revisar(v, prompts)
        if not vista["revision"]:
            vista["precio"] = cadena.precio(v, ks[0], conocidos) if ks else None
    for c in v["clips"]:
        k = c["indice"]
        e = ((est or {}).get("escenas") or {}).get(str(k)) or {}
        fila = {"indice": k, "titulo": c.get("titulo") or "", "estado": e.get("estado") or ("espera" if est else None),
                "error": e.get("error"), "rehacer_precio": None}
        if est and not corriendo and k != ks[0] and cadena.puede_rehacer(est, k, ks[0]) \
                and not cadena.revisar(v, prompts, desde=k):
            fila["rehacer_precio"] = cadena.precio(v, k, conocidos)
        vista["filas"].append(fila)
    return vista


def _src(cliente, img):
    """Miniatura de una imagen de escena: la foto del Catálogo por la ruta de
    siempre (?w=320) o la URL pública de lo subido."""
    if not img:
        return None
    if img.get("activo_id"):
        return url_for("imagen_producto", cliente=cliente, producto_id=img["activo_id"],
                       categoria=img["categoria"], w=320)
    return img.get("url")


def _vista_escenas(cliente, v, catalogo):
    pool = [dict(x, src=_src(cliente, x["imagen"])) for x in escenas.pool(v)]
    fotos = [{"id": a["id"], "nombre": a["nombre"], "categoria": t,
              "src": _src(cliente, {"activo_id": a["id"], "categoria": t})}
             for t, lista in catalogo.items() for a in lista]
    falta = {x["clave"]: f"Image {x['numero']}" for x in pool if x["origen"] == "falta"}
    etiqueta = {x["clave"]: f"Image {x['numero']}" + (f" · {x['nombre']}" if x["nombre"] else "") for x in pool}
    filas = [dict(f, faltan=[falta[c] for c in f["claves"] if c in falta], etiquetas=[etiqueta[c] for c in f["claves"]])
             for f in escenas.por_escena(v)]
    return {"pool": pool, "filas": filas, "catalogo": fotos}


def _url_publica(cliente, img):
    """Para los documentos .md: la URL que se abre fuera de Creatv (R2), o None."""
    if img.get("activo_id"):
        a = catalogo_productos.encontrar(cliente, img["activo_id"], categoria=img["categoria"])
        return (a or {}).get("representativa_url")
    return img.get("url")


@bp.get("/panel")
def panel(cliente):
    ctx = _contexto(cliente, _entero(request.args.get("guion") or ""), _entero(request.args.get("video") or ""))
    return render_template("_gpg_panel.html", **ctx)


def _lanzar_lectura(cliente, lote_id):
    trabajos.iniciar(f"guion_leer_{lote_id}", lambda: lectura.leer_lote(lote_id), duracion_estimada=60, cliente=cliente)


@bp.post("/lotes")
def lote_crear(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    _exigir(cliente, "leer", 750)
    try:
        if str(cuerpo.get("notion_url") or "").strip():
            if not notion.conectado(cliente):
                raise Conflicto(gettext("Conecta Notion primero."))
            page_id = notion.extraer_id(cuerpo["notion_url"])
            if not page_id:
                raise DatoInvalido(gettext("Ese link no parece de una página de Notion."))
            lote_id = datos.crear_lote(cliente, "", fuente="notion", notion_page_id=page_id)
        else:
            lote_id = datos.crear_lote(cliente, cuerpo.get("texto"))
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(cliente, lote_id)
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
        return jsonify({"error": gettext("Confirma tu correo primero (Configuración › Cuenta).")}), 403
    llave = str(cuerpo.get("llave") or "").strip()
    if not llave or len(llave) > 200:
        return jsonify({"error": gettext("Pega la llave de tu integración de Notion.")}), 400
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
    _exigir(cliente, "leer", 750)
    try:
        datos.reintentar_lote(cliente, lid)
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(cliente, lid)
    return jsonify({"lote_id": lid}), 202


def _guion_o_404(cliente, gid):
    g = datos.guion(cliente, gid)
    if g is None:
        raise NoExiste(gettext("Ese guion no existe."))
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
        raise NoExiste(gettext("Esa versión no existe."))
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
            raise Conflicto(gettext("Pon una duración objetivo para poder recortar."))
        _exigir(cliente, "recorte")
        datos.empezar(cliente, vid, "recortando", ("configurando",))
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_recorte_{vid}", lambda: recorte.proponer(vid), duracion_estimada=40, cliente=cliente)
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
        _exigir(cliente, "armar", _palabras(_video_o_404(cliente, vid)))
        datos.empezar(cliente, vid, "armando", ("configurando", "invalido", "error"))
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_armar_{vid}", lambda: clips.armar(vid), duracion_estimada=300, cliente=cliente)
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
        return jsonify({"error": gettext("Esa versión no existe.")}), 404
    prompts = [{k: p[k] for k in ("id", "titulo", "tipo", "estado", "extra")} for p in datos.prompts_de_video(vid)]
    return jsonify({"video": v, "prompts": prompts})


@bp.get("/videos/<int:vid>/documento.md")
def video_documento(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        return jsonify({"error": gettext("Esa versión no existe.")}), 404
    if v["estado"] != "armado":
        return jsonify({"error": gettext("El documento sale cuando la versión está armada.")}), 409
    md = plantillas.documento_md(v, datos.prompts_de_video(vid),
                                 escenas.texto_por_clip(v, lambda img: _url_publica(cliente, img)))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{plantillas.nombre_documento(v)}"'})


@bp.post("/videos/<int:vid>/imagenes")
def video_imagenes(cliente, vid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        _video_o_404(cliente, vid)
        _exigir(cliente, "imagenes")
        datos.empezar_imagenes(cliente, vid)
    except ErrorRefinador as e:
        return _error(e)
    trabajos.iniciar(f"guion_imagenes_{vid}", lambda: imagenes.escribir(vid), duracion_estimada=60, cliente=cliente)
    return jsonify({"video_id": vid}), 202


@bp.get("/videos/<int:vid>/imagenes.md")
def video_imagenes_md(cliente, vid):
    v = datos.video(cliente, vid)
    if v is None:
        return jsonify({"error": gettext("Esa versión no existe.")}), 404
    if v["estado_imagenes"] != "listo":
        return jsonify({"error": gettext("Primero escribe los prompts de imágenes.")}), 409
    md = imagenes.documento_md(v, datos.prompts_de_video(vid),
                               escenas.texto_por_clip(v, lambda img: _url_publica(cliente, img)))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{imagenes.nombre_documento(v)}"'})


# ------------------------------------------------ imágenes de cada escena ---
# (spec 2026-09-30) Gratis: subir usa la biblioteca del editor (material
# `subida` en R2) y nada llama a Claude. Todo exige la versión armada.

EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp")


@bp.post("/videos/<int:vid>/escenas/<int:indice>")
def escena_imagenes(cliente, vid, indice):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    clave, usar = str(cuerpo.get("clave") or ""), bool(cuerpo.get("usar"))
    try:
        if cuerpo.get("sugeridas"):
            datos.modificar_imagenes_escenas(cliente, vid, lambda est, v: escenas.sugeridas_de_nuevo(est, indice))
        else:
            datos.modificar_imagenes_escenas(cliente, vid, lambda est, v: escenas.usar(est, v, indice, clave, usar))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


@bp.post("/videos/<int:vid>/imagenes/subir")
def escena_subir(cliente, vid):
    """Multipart: `archivo` + `ref` (la imagen de Image n, por crear) o `escena`
    (una extra que entra en esa escena), o ninguno (extra del video)."""
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"error": gettext("Elige una imagen.")}), 400
    if os.path.splitext(archivo.filename)[1].lower() not in EXT_IMAGEN:
        return jsonify({"error": gettext("Sube una imagen JPG, PNG o WEBP.")}), 400
    ref, escena = _entero(request.form.get("ref") or ""), _entero(request.form.get("escena") or "")
    if ref is not None:
        def aplicar(est, v, img):
            return escenas.poner_ref(est, v, ref, img)
    else:
        def aplicar(est, v, img):
            return escenas.agregar_extra(est, v, img, escena)
    try:
        # Primero se prueba con una imagen de mentira (sin guardar): si no se
        # podría guardar, no se sube nada a R2.
        v = _video_o_404(cliente, vid)
        if v["estado"] != "armado":
            raise Conflicto(gettext("Primero arma los clips de esta versión."))
        aplicar(escenas.estado(v), v, {"url": "https://prueba.invalid/x.jpg", "material_id": -1})
    except ErrorRefinador as e:
        return _error(e)
    try:
        m = biblioteca.subir(cliente, archivo)
    except biblioteca.SubidaInvalida as e:
        return jsonify({"error": str(e)}), 400
    img = {"url": m["url"], "material_id": m["id"], "nombre": m.get("nombre") or ""}
    try:
        datos.modificar_imagenes_escenas(cliente, vid, lambda est, v: aplicar(est, v, img))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid}), 201


@bp.post("/videos/<int:vid>/imagenes/catalogo")
def escena_catalogo(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    categoria, activo_id = str(cuerpo.get("categoria") or ""), str(cuerpo.get("activo_id") or "")
    escena = _entero(cuerpo.get("escena"))
    if categoria not in config.TIPOS_REF:
        return jsonify({"error": gettext("Elige una foto del Catálogo.")}), 400
    activo = catalogo_productos.encontrar(cliente, activo_id, categoria=categoria) if activo_id else None
    if activo is None:
        return jsonify({"error": gettext("Esa foto ya no está en el Catálogo.")}), 400
    img = {"activo_id": activo["id"], "categoria": categoria, "nombre": activo.get("nombre") or activo["id"]}
    try:
        datos.modificar_imagenes_escenas(cliente, vid, lambda est, v: escenas.agregar_extra(est, v, img, escena))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


@bp.post("/videos/<int:vid>/imagenes/quitar")
def escena_quitar(cliente, vid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    clave = str(cuerpo.get("clave") or "")
    try:
        datos.modificar_imagenes_escenas(cliente, vid, lambda est, v: escenas.quitar(est, v, clave))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


@bp.post("/videos/<int:vid>/escenas/<int:indice>/crear")
def escena_a_crear(cliente, vid, indice):
    """«Llevar a Crear» (spec 2026-09-30): la bandeja de Crear se REEMPLAZA con
    las imágenes de la escena (como «Editar y crear otra») y el formulario queda
    precargado con su prompt (`escenas.prompt_para_crear`), la duración del clip
    y el formato. Nada se genera: la persona revisa y pulsa «Generar» en Crear."""
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
        if v["estado"] != "armado":
            raise Conflicto(gettext("Primero arma los clips de esta versión."))
        clip = next((c for c in v["clips"] if c["indice"] == indice), None)
        if clip is None:
            raise DatoInvalido(gettext("Esa escena no existe en esta versión."))
        prompt = next((p for p in datos.prompts_de_video(vid) if p["tipo"] == "clip"
                       and (p["extra"] or {}).get("variante") == "principal"
                       and (p["extra"] or {}).get("clip_index") == indice), None)
        if prompt is None:
            raise Conflicto(gettext("Esta escena todavía no tiene su prompt en el chat."))
        imagenes = escenas.imagenes_para_crear(v, indice)
        urls = [medios.url_publica(cliente, x["imagen"]) for x in imagenes]
    except ErrorRefinador as e:
        return _error(e)
    except Exception:  # noqa: BLE001 — subir una foto del Catálogo a R2 puede fallar
        return jsonify({"error": gettext("No se pudieron preparar las imágenes de la escena. Vuelve a intentarlo.")}), 502
    referencias_flowplus.vaciar(cliente)
    for x, url in zip(imagenes, urls):
        referencias_flowplus.agregar(cliente, "imagen", url, origen="flowplus",
                                     titulo=f"Image {x['numero']}" + (f" · {x['nombre']}" if x["nombre"] else ""))
    session["fp_prefill"] = {
        "cliente": cliente,
        "texto": escenas.prompt_para_crear(prompt["texto_vigente"], v, imagenes),
        "tipo": "video",
        # Crear ofrece duraciones fijas: la primera que alcanza para la escena
        # (13 s → 15 s), así el diálogo nunca queda cortado.
        "duracion": next((d for d in flowplus_modelos.DURACIONES_CREAR if d >= clip["duracion"]),
                         flowplus_modelos.DURACIONES_CREAR[-1]),
        "aspect_ratio": v["config"].get("formato") or "9:16",
    }
    flash(gettext("Escena %(n)s cargada en Crear: revisa el texto y las referencias, y genera.", n=indice), "ok")
    return jsonify({"video_id": vid, "ir": url_for("ver_cliente", cliente=cliente, desde="flowplus") + "#referencias"})


# ------------------------------------------------------------ cadena de escenas ---
# (spec 2026-09-30) Una sola aprobación con el precio a la vista; el worker
# (`tareas/cadena.py`) genera escena tras escena y frena si una falla.

def _prompts_clip(vid):
    return {f"principal:{(p['extra'] or {}).get('clip_index')}": {"id": p["id"], "estado": p["estado"]}
            for p in datos.prompts_de_video(vid)
            if p["tipo"] == "clip" and (p["extra"] or {}).get("variante") == "principal"}


@bp.post("/videos/<int:vid>/cadena")
def cadena_aprobar(cliente, vid):
    """`{desde, total_visto}`: aprueba la cadena desde esa escena (la primera o,
    para «Rehacer desde», una con el último cuadro de la anterior) si el precio
    recalculado coincide con el que la persona vio."""
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        v = _video_o_404(cliente, vid)
        ks = cadena.indices(v)
        if v["estado"] != "armado" or not ks:
            raise Conflicto(gettext("Primero arma los clips de esta versión."))
        desde = _entero(cuerpo.get("desde")) if cuerpo.get("desde") is not None else ks[0]
        if desde not in ks:
            raise DatoInvalido(gettext("Esa escena no existe en esta versión."))
        problemas = cadena.revisar(v, _prompts_clip(vid), desde=desde)
        if problemas:
            return jsonify({"error": gettext("Antes de generar falta resolver esto:"),
                            "problemas": [(gettext("Escena %(n)s: ", n=p["indice"]) if p["indice"] else "") + p["motivo"]
                                          for p in problemas]}), 409
        est = cadena.estado(v)
        if desde != ks[0] and not cadena.puede_rehacer(est, desde, ks[0]):
            raise Conflicto(gettext("Para rehacer desde esa escena hace falta el último cuadro de la anterior."))
        precio = cadena.precio(v, desde, list(((est or {}).get("elementos") or {}).keys()))
        # `total_visto` es lo que la persona vio (precio, con margen si el
        # proyecto cobra; cobros, spec 2026-10-08 §6): vuelve a costo una sola vez.
        visto = gastos.costo_de_precio(cuerpo.get("total_visto"))
        if visto is None or abs(visto - precio) > 0.005:
            return jsonify({"error": gettext("El precio cambió: ahora es ≈ US$ %(precio)s. Revisa y vuelve a aprobar.",
                                             precio=f"{gastos.precio(precio):.2f}"), "precio": gastos.precio(precio)}), 409
        # Cobros (spec 2026-10-08 §5): la cadena entera se pide antes de
        # aprobarla; cada escena vuelve a pedir y reservar lo suyo al encolarse.
        libro.exigir(cliente, precio)
        usuario = session.get("usuario")

        def aprobar(e, video):
            if e and e.get("estado") == "corriendo":
                raise Conflicto(gettext("La cadena ya está corriendo."))
            return cadena.aprobar(video, desde, precio, usuario, db.ahora(), previo=e or {})
        datos.modificar_cadena(cliente, vid, aprobar)
    except ErrorRefinador as e:
        return _error(e)
    try:
        trabajos.encolar(job_cadena(cliente, vid, "elementos"), "cadena_elementos", {"cliente": cliente, "video_id": vid},
                         duracion_estimada=60, cliente=cliente, max_intentos=1, prioridad=PRIORIDAD_CADENA,
                         costo_estimado=precio)
    except SaldoInsuficiente as e:
        # Otro clic gastó el saldo entre la revisión y el encolado: la cadena
        # aprobada no queda «corriendo» sin trabajo detrás.
        fallar_cadena(cliente, vid, desde, e.frase_proyecto())
        raise
    return jsonify({"video_id": vid}), 202


@bp.post("/videos/<int:vid>/cadena/detener")
def cadena_detener(cliente, vid):
    if _cuerpo() is None:
        return _sin_cuerpo()

    def detener(e, _video):
        if not e or e.get("estado") != "corriendo":
            raise Conflicto(gettext("La cadena no está corriendo."))
        return cadena.pedir_detener(e)
    try:
        datos.modificar_cadena(cliente, vid, detener)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"video_id": vid})


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
            return jsonify({"error": gettext("El bloque global rompe reglas que no se negocian."),
                            "problemas": problemas}), 422
    proyectos.guardar_bloque_global_flowplus(cliente, texto)
    return jsonify({"ok": True})
