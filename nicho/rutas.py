# nicho/rutas.py
"""
Rutas de la pestaña Nicho (Blueprint `nicho`, prefijo /cliente/<cliente>/nicho).
Solo validan, delegan a nicho.datos / nicho.avatares / nicho.exportar /
tareas.nicho y redirigen; la lógica vive en esos módulos.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
<cliente>. `contexto(cliente)` es lo que `ver_cliente` agrega al render de
cliente.html para la pestaña; el estudio abre en su propia página
(`nicho_estudio.html`, como `sprint_detalle.html`).
"""
import io

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

import catalogo_productos
import gastos
import proyectos
import trabajos
from nicho import avatares, datos, exportar, investigacion
from nicho import fuentes as fuentes_registro
from nicho.fuentes import apify as fuente_apify
from nicho.fuentes import apify_actores
from nicho.fuentes import archivo as fuente_archivo
from nicho.fuentes import reddit as fuente_reddit
from nicho.fuentes import texto as fuente_texto
from nicho.fuentes import youtube as fuente_youtube
from nicho.fuentes.base import ErrorFuente
from tareas import nicho as tareas_nicho

bp = Blueprint("nicho", __name__, url_prefix="/cliente/<cliente>/nicho")
POR_PAGINA = 50


# ------------------------------------------------------------ helpers ---

def _volver(cliente, eid=None):
    if eid is not None:
        return redirect(url_for("nicho.ver", cliente=cliente, eid=eid))
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="nicho"))


def _estudio_o_404(cliente, eid):
    e = datos.estudio(cliente, eid)
    if not e:
        abort(404)
    return e


def _avatar_o_404(cliente, aid):
    a = datos.avatar(cliente, aid)
    if not a:
        abort(404)
    return a


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _lineas(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def _productos(cliente):
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion") or ""}
            for p in catalogo_productos.listar(cliente, "producto")]


_NORMALIZAR = {"reddit": fuente_reddit.normalizar_params, "youtube": fuente_youtube.normalizar_params,
               "apify": fuente_apify.normalizar_params}


def _entero(campo, defecto):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(f"«{campo}» debe ser un número entero.")


def _fuentes_conectadas(cliente, eid):
    """Tarjetas de Reddit, YouTube y Apify: qué llave falta y si hay una recolección viva."""
    salida = []
    for tipo in fuentes_registro.CONECTADAS:
        job = datos.job_id_recolectar(cliente, eid, tipo)
        salida.append({"tipo": tipo, "nombre": fuentes_registro.NOMBRES[tipo], "faltan": fuentes_registro.llaves_faltantes(tipo),
                       "job_id": job, "en_curso": trabajos.en_curso(job)})
    return salida


def _params_desde_form(fuente, est, cliente):
    f = request.form
    if fuente == "reddit":
        return {"palabras_clave": f.get("palabras_clave") or "", "subreddits": _partir(f.get("subreddits")), "links": _lineas(f.get("links")),
                "max_posts": _entero("max_posts", 10), "max_comentarios_por_post": _entero("max_comentarios_por_post", 50),
                "periodo": f.get("periodo") or "year"}
    if fuente == "youtube":
        return {"palabras_clave": f.get("palabras_clave") or "", "links": _lineas(f.get("links")), "max_videos": _entero("max_videos", 5),
                "max_comentarios_por_video": _entero("max_comentarios_por_video", 100),
                "idioma": f.get("idioma") or est.get("idioma") or "es", "region": f.get("region") or proyectos.pais(cliente) or ""}
    return {"actor": f.get("actor") or "", "links": _lineas(f.get("links")), "max_resultados": _entero("max_resultados", 200)}


def contexto(cliente):
    """Lo que necesita _tab_nicho.html. Se llama desde dashboard.ver_cliente."""
    return {"estudios_nicho": datos.estudios(cliente), "productos_nicho": _productos(cliente),
            "idiomas_nicho": avatares.IDIOMAS, "min_comentarios_nicho": avatares.MIN_COMENTARIOS}


# ----------------------------------------------------------- estudios ---

@bp.post("/estudios")
def crear(cliente):
    try:
        eid = datos.crear_estudio(cliente, request.form.get("nombre"), producto=request.form.get("producto"),
                                  tema=request.form.get("tema"), idioma=request.form.get("idioma") or "es",
                                  catalogo_id=request.form.get("catalogo_id") or None)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash("Estudio creado. Ahora agrégale comentarios.", "ok")
    return _volver(cliente, eid)


@bp.get("/<int:eid>")
def ver(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    est["estado"] = datos.recalcular(cliente, eid) or est["estado"]
    fuente = request.args.get("fuente") or None
    try:
        pagina = int(request.args.get("pagina") or 1)
    except ValueError:
        pagina = 1
    lista = datos.comentarios_para_generar(cliente, eid)
    estimado = avatares.estimar_costo(lista)
    job = datos.job_id_generar(cliente, eid)
    return render_template(
        "nicho_estudio.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente), estudio=est,
        conteos=datos.contar_por_fuente(cliente, eid), fuente_filtro=fuente,
        pagina_comentarios=datos.comentarios(cliente, eid, fuente=fuente, pagina=pagina, por_pagina=POR_PAGINA),
        nucleos=datos.avatares(cliente, eid), urls_comentarios=datos.urls_comentarios(cliente, eid),
        estimado=estimado, precio_texto=gastos.formatear(estimado["usd"]), min_comentarios=avatares.MIN_COMENTARIOS,
        trabajo_generar=({"job_id": job} if trabajos.en_curso(job) else None),
        modos_texto=fuente_texto.NOMBRES_MODO, fuentes_nombre=fuentes_registro.NOMBRES, idiomas=avatares.IDIOMAS,
        niveles_conciencia=datos.NIVELES_CONCIENCIA, bases=datos.BASES, productos_nicho=_productos(cliente),
        fuentes_conectadas=_fuentes_conectadas(cliente, eid),
        actores_apify=[{"clave": k, "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "ayuda": a["ayuda"]}
                       for k, a in apify_actores.ACTORES.items()],
        recolecciones=list(reversed((est["extra"].get("recolecciones") or [])[-5:])),
        periodos_reddit=fuente_reddit.PERIODOS, max_apify=apify_actores.MAX_RESULTADOS, region_defecto=proyectos.pais(cliente) or "")


@bp.post("/<int:eid>/editar")
def editar(cliente, eid):
    _estudio_o_404(cliente, eid)
    try:
        campos = {k: request.form.get(k) for k in ("nombre", "producto", "tema", "idioma") if request.form.get(k) is not None}
        if request.form.get("catalogo_id") is not None:
            campos["catalogo_id"] = request.form.get("catalogo_id") or None
        datos.actualizar_estudio(cliente, eid, **campos)
        flash("Estudio guardado.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/archivar")
def archivar(cliente, eid):
    _estudio_o_404(cliente, eid)
    datos.archivar_estudio(cliente, eid, archivado=request.form.get("desarchivar") is None)
    return _volver(cliente, eid)


@bp.post("/<int:eid>/eliminar")
def eliminar(cliente, eid):
    _estudio_o_404(cliente, eid)
    if datos.eliminar_estudio(cliente, eid):
        flash("Estudio eliminado permanentemente.", "ok")
    return _volver(cliente)


# -------------------------------------------------------- comentarios ---

def _agregar(cliente, eid, fuente, lista):
    r = datos.agregar_comentarios(cliente, eid, fuente, lista)
    datos.registrar_recoleccion(cliente, eid, {"fuente": fuente, "nuevos": r["nuevos"], "repetidos": r["repetidos"], "aviso": ""})
    datos.recalcular(cliente, eid)
    flash(f"Entraron {r['nuevos']} comentario(s); {r['repetidos']} repetido(s).", "ok")


@bp.post("/<int:eid>/comentarios/texto")
def comentarios_texto(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("texto")().recolectar(
            {"texto": request.form.get("texto"), "modo": request.form.get("modo") or "lineas"}))
        if not lista:
            flash("No encontré comentarios en el texto (mínimo 3 caracteres cada uno).", "error")
        else:
            _agregar(cliente, eid, "texto", lista)
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/comentarios/archivo")
def comentarios_archivo(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    f = request.files.get("archivo")
    if not f or not f.filename:
        flash("Elige un archivo .csv o .xlsx.", "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("csv")().recolectar(
            {"nombre": f.filename, "contenido": f.read(fuente_archivo.MAX_BYTES + 1)}))
        if not lista:
            flash("El archivo no trajo comentarios.", "error")
        else:
            _agregar(cliente, eid, "csv", lista)
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/comentario/<int:cid>/excluir")
def comentario_excluir(cliente, cid):
    c = datos.comentario(cliente, cid)
    if not c:
        abort(404)
    datos.excluir_comentario(cliente, cid, excluido=request.form.get("incluir") is None)
    return _volver(cliente, c["estudio_id"])


@bp.post("/<int:eid>/comentarios/borrar/<fuente>")
def comentarios_borrar(cliente, eid, fuente):
    _estudio_o_404(cliente, eid)
    if fuente not in datos.FUENTES:
        abort(404)
    n = datos.borrar_fuente(cliente, eid, fuente)
    datos.recalcular(cliente, eid)
    flash(f"Se quitaron {n} comentario(s) de {fuentes_registro.NOMBRES.get(fuente, fuente)}.", "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/recolectar/<fuente>")
def recolectar(cliente, eid, fuente):
    est = _estudio_o_404(cliente, eid)
    if fuente not in fuentes_registro.CONECTADAS:
        abort(404)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    faltan = fuentes_registro.llaves_faltantes(fuente)
    if faltan:
        flash(f"Falta {', '.join(faltan)} en el .env del servidor (Configuración › Puesta a punto).", "error")
        return _volver(cliente, eid)
    try:
        params = _params_desde_form(fuente, est, cliente)
        _NORMALIZAR[fuente](params)                     # valida el formulario sin tocar la red
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
        return _volver(cliente, eid)
    if tareas_nicho.encolar_recolectar(cliente, eid, fuente, params):
        flash(f"Recolectando de {fuentes_registro.NOMBRES[fuente]}; la página se recarga sola al terminar.", "ok")
    else:
        flash(f"Ya hay una recolección de {fuentes_registro.NOMBRES[fuente]} en curso.", "error")
    return _volver(cliente, eid)


@bp.get("/<int:eid>/recolectar/apify/estimar")
def apify_estimar(cliente, eid):
    _estudio_o_404(cliente, eid)
    try:
        est = apify_actores.estimar(request.args.get("actor") or "", request.args.get("max") or 1)
    except ErrorFuente as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({**est, "texto": gastos.formatear(est["usd"])})


# ----------------------------------------------------------- avatares ---

@bp.post("/<int:eid>/generar")
def generar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    lista = datos.comentarios_para_generar(cliente, eid)
    if len(lista) < avatares.MIN_COMENTARIOS:
        flash(f"Hacen falta al menos {avatares.MIN_COMENTARIOS} comentarios no excluidos (hay {len(lista)}).", "error")
        return _volver(cliente, eid)
    if tareas_nicho.encolar_generar(cliente, eid):
        flash("Claude está armando los avatares; la página se recarga sola al terminar.", "ok")
    else:
        flash("Ya hay una generación en curso para este estudio.", "error")
    return _volver(cliente, eid)


def _soluciones_desde_texto(texto):
    """Una solución por línea: «qué usó :: problema; problema»."""
    salida = []
    for linea in _lineas(texto):
        que, _, fallas = linea.partition("::")
        salida.append({"que": que.strip(), "por_que_fallo": [x.strip() for x in fallas.split(";") if x.strip()]})
    return salida


@bp.app_template_filter("soluciones_texto")
def soluciones_texto(soluciones):
    """Inverso de _soluciones_desde_texto, para pintar el textarea."""
    return "\n".join(f"{s.get('que', '')} :: " + "; ".join(s.get("por_que_fallo") or []) for s in (soluciones or []))


def _campos_avatar_desde_form():
    f = request.form
    campos = {}
    for k in ("nombre", "deseo", "base", "demografia", "edad_rango", "emocion", "comportamiento", "encaje_producto", "tono"):
        if f.get(k) is not None:
            campos[k] = f.get(k)
    if any(f.get(f"identidad_{k}") is not None for k in datos.CLAVES_IDENTIDAD):
        campos["identidad"] = {k: f.get(f"identidad_{k}") or "" for k in datos.CLAVES_IDENTIDAD}
    if f.get("soluciones_previas") is not None:
        campos["soluciones_previas"] = _soluciones_desde_texto(f.get("soluciones_previas"))
    if f.get("situaciones") is not None:
        campos["situaciones"] = _lineas(f.get("situaciones"))
    if f.get("conciencia_nivel") is not None or f.get("conciencia_detalle") is not None:
        campos["conciencia"] = {"nivel": f.get("conciencia_nivel") or "", "detalle": f.get("conciencia_detalle") or ""}
    if f.get("palabras_clave") is not None:
        campos["palabras_clave"] = _partir(f.get("palabras_clave"))
    return campos


@bp.post("/avatar/<int:aid>/editar")
def avatar_editar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.actualizar_avatar(cliente, aid, **_campos_avatar_desde_form())
        flash("Avatar guardado. Si ya estaba aprobado, vuelve a aprobarlo para actualizar la persona.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, a["estudio_id"])


@bp.post("/avatar/<int:aid>/aprobar")
def avatar_aprobar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.aprobar_avatar(cliente, aid)
        flash("Avatar aprobado: ya es una persona de Sprints.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, a["estudio_id"])


@bp.post("/avatar/<int:aid>/descartar")
def avatar_descartar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    if datos.descartar_avatar(cliente, aid):
        flash("Avatar descartado.", "ok")
    else:
        flash("Solo se descartan los sub-avatares; el núcleo es una agrupación.", "error")
    return _volver(cliente, a["estudio_id"])


# ----------------------------------------------------------- exportar ---

@bp.get("/<int:eid>/exportar.md")
def exportar_md(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    md = exportar.markdown(est, datos.avatares(cliente, eid), urls=datos.urls_comentarios(cliente, eid))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{exportar.nombre_archivo(est, "md")}"'})


@bp.get("/<int:eid>/exportar.xlsx")
def exportar_xlsx(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    contenido = exportar.excel(est, datos.avatares(cliente, eid), urls=datos.urls_comentarios(cliente, eid))
    return send_file(io.BytesIO(contenido), as_attachment=True, download_name=exportar.nombre_archivo(est, "xlsx"),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------ Investigación (Parte 3) ------

@bp.get("/<int:eid>/investigacion/estimar")
def investigacion_estimar(cliente, eid):
    """Estimar el costo de una investigación (GET con parámetros)."""
    est = _estudio_o_404(cliente, eid)
    
    try:
        pais = request.args.get("pais") or est.get("pais") or "CO"
        plataformas = [p.strip() for p in (request.args.get("plataformas") or "").split(",") if p.strip()]
        redes = [r.strip() for r in (request.args.get("redes") or "").split(",") if r.strip()]
        
        estimado = investigacion.estimar(est, pais, plataformas, redes, investigacion.TOPES_DEFECTO)
        return jsonify({
            **estimado,
            "texto": gastos.formatear(estimado["total_usd"])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/<int:eid>/investigacion")
def investigacion_iniciar(cliente, eid):
    """Iniciar una investigación nueva (aprobando el presupuesto)."""
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    
    inv_actual = datos.investigacion(cliente, eid)
    if inv_actual.get("estado") and inv_actual["estado"] not in ("lista", "detenida", "interrumpida"):
        flash("Ya hay una investigación en curso.", "error")
        return _volver(cliente, eid)
    
    try:
        pais = request.form.get("pais") or est.get("pais") or "CO"
        plataformas = [p.strip() for p in (request.form.get("plataformas") or "").split(",") if p.strip()]
        redes = [r.strip() for r in (request.form.get("redes") or "").split(",") if r.strip()]
        presupuesto_usd = float(request.form.get("presupuesto_usd") or 0)
        
        if presupuesto_usd <= 0:
            flash("El presupuesto debe ser mayor a 0.", "error")
            return _volver(cliente, eid)
        
        # Validar país
        if pais not in investigacion.IDIOMAS:
            flash(f"País {pais} no soportado.", "error")
            return _volver(cliente, eid)
        
        # Actualizar estudio con país si no lo tiene
        if not est.get("pais"):
            datos.actualizar_estudio(cliente, eid, pais=pais)
        
        # Inicializar investigación
        inv_nueva = investigacion.crear_inicial(est.get("tema", ""), pais, plataformas, redes,
                                               investigacion.TOPES_DEFECTO)
        inv_nueva["aprobado_usd"] = presupuesto_usd
        
        # Guardar en BD
        datos.actualizar_investigacion(cliente, eid, lambda x: inv_nueva)
        
        # Encolatr tarea: nicho_inv_consultas
        job_id = f"nicho:{cliente}:{int(eid)}:inv:consultas"
        trabajos.encolar(job_id, "nicho_inv_consultas",
                        {"cliente": cliente, "estudio_id": int(eid)},
                        cliente=cliente, duracion_estimada=60, max_intentos=2)
        
        flash("Investigación iniciada; Claude está generando consultas.", "ok")
    except (ValueError, datos.ErrorDatos) as e:
        flash(f"Error: {str(e)}", "error")
    
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/reanudar")
def investigacion_reanudar(cliente, eid):
    """Reanudar una investigación detenida o interrumpida."""
    est = _estudio_o_404(cliente, eid)
    inv_actual = datos.investigacion(cliente, eid)
    
    estado = inv_actual.get("estado", "")
    if not investigacion.puede_reanudar(estado):
        flash(f"No se puede reanudar un estudio con estado '{estado}'.", "error")
        return _volver(cliente, eid)
    
    try:
        # Reanudar el siguiente paso
        paso = investigacion.siguiente_paso(inv_actual)
        if paso is None:
            flash("La investigación ya está completa.", "ok")
            return _volver(cliente, eid)
        
        # Cambiar estado a activo
        datos.actualizar_investigacion(cliente, eid, lambda inv: {
            **inv, "estado": "consultas", "ultimo_error": None
        })
        
        flash("Investigación reanudada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/cancelar")
def investigacion_cancelar(cliente, eid):
    """Marcar una investigación como interrumpida (cancelar)."""
    est = _estudio_o_404(cliente, eid)
    inv_actual = datos.investigacion(cliente, eid)
    
    estado = inv_actual.get("estado", "")
    if not estado or estado in ("lista", "interrumpida"):
        flash("No hay investigación en curso para cancelar.", "error")
        return _volver(cliente, eid)
    
    # Marcar como interrumpida
    datos.actualizar_investigacion(cliente, eid, lambda inv: {
        **inv, "estado": "interrumpida", "detenida_por": "usuario"
    })
    
    flash("Investigación cancelada.", "ok")
    return _volver(cliente, eid)
