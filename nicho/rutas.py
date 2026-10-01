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

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_babel import gettext

import catalogo_productos
import doctrina
import gastos
import idiomas
import proyectos
import trabajos
from nicho import avatares, calidad, datos, exportar, investigacion
from nicho import fuentes as fuentes_registro
from nicho.fuentes import apify as fuente_apify
from nicho.fuentes import apify_actores
from nicho.fuentes import archivo as fuente_archivo
from nicho.fuentes import plataformas
from nicho.fuentes import reddit as fuente_reddit
from nicho.fuentes import texto as fuente_texto
from nicho.fuentes import youtube as fuente_youtube
from nicho.fuentes.base import ErrorFuente
from idiomas import N_
from sprints import datos as sprints_datos
from tareas import investigacion as tareas_investigacion
from tareas import nicho as tareas_nicho

bp = Blueprint("nicho", __name__, url_prefix="/cliente/<cliente>/nicho")
POR_PAGINA = 50


def _mismo_origen():
    """Mismo criterio que `dashboard._mismo_origen`. No se importa de ahí
    porque con `python dashboard.py` ese módulo es __main__ y se cargaría dos veces."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


@bp.before_request
def _solo_mismo_origen():
    """Barrera CSRF (como Flow Plus, Sprints, Triple Whale y el editor): este
    Blueprint también gasta dinero por POST y no la tenía (Ruling 18)."""
    if request.method == "POST" and not _mismo_origen():
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
        abort(403)
    return None


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


def _destino_avatar(cliente, a):
    """Tras una acción sobre un avatar: a la lista del proyecto si se pidió
    (`volver=lista`) o si es escrito a mano; si no, a su estudio."""
    if request.form.get("volver") == "lista" or datos.es_manual(datos.estudio(cliente, a["estudio_id"])):
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, _anchor=f"avatar-a{a['id']}"))
    return _volver(cliente, a["estudio_id"])


def _faltantes_de(cliente, a):
    return calidad.faltantes(a, con_evidencia=not datos.es_manual(datos.estudio(cliente, a["estudio_id"])))


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _lineas(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def _productos(cliente):
    """Uno por PRODUCTO (id = pid), no uno por color: un estudio investiga el
    producto. `catalogo_productos.encontrar(pid)` resuelve a su primer color."""
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion") or ""}
            for p in catalogo_productos.listar_productos(cliente, "producto")]


_NORMALIZAR = {"reddit": fuente_reddit.normalizar_params, "youtube": fuente_youtube.normalizar_params,
               "apify": fuente_apify.normalizar_params}


def _entero(campo, defecto):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(gettext("«%(campo)s» debe ser un número entero.", campo=campo))


def _es_admin():
    return session.get("rol") == "admin"


def _investigacion_viva(cliente, eid):
    """True mientras la investigación automática del estudio está corriendo
    (Ruling 13, lado rutas): con esto vivo, los botones manuales que
    encolarían con el MISMO job_id que un paso de la cadena (`resenas:*`,
    `redes:*`, `generar`) deben esperar -- si se dejaran encolar, el paso de
    la cadena no podría encolarse y la cadena quedaría `interrumpida`
    (arreglo del lado worker en Task 5)."""
    estado = datos.investigacion(cliente, eid).get("estado")
    return bool(estado) and estado not in ("lista", "detenida", "interrumpida")


def _fuentes_conectadas(cliente, eid):
    """Tarjetas de Reddit, YouTube y Apify: qué llave falta y si hay una
    recolección viva. Las llaves son de Creatv (el admin las pone en el .env):
    una fuente sin llave solo la ve el admin, apagada; al cliente no se le
    muestra (2026-09-27)."""
    salida = []
    for tipo in fuentes_registro.CONECTADAS:
        faltan = fuentes_registro.llaves_faltantes(tipo)
        if faltan and not _es_admin():
            continue
        job = datos.job_id_recolectar(cliente, eid, tipo)
        salida.append({"tipo": tipo, "nombre": fuentes_registro.NOMBRES[tipo], "faltan": faltan,
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
            "min_comentarios_nicho": avatares.MIN_COMENTARIOS,
            "etiquetas_estudio": datos.ETIQUETAS_ESTADO_ESTUDIO, "etiquetas_inv": investigacion.ETIQUETAS_ESTADO,
            "paises_estudio": [(c, datos.NOMBRES_PAIS.get(c, c)) for c in datos.PAISES_ESTUDIO],
            "pais_proyecto": proyectos.pais(cliente), "avatares_resumen": datos.resumen_avatares(cliente)}


# ----------------------------------------------------------- estudios ---

@bp.post("/estudios")
def crear(cliente):
    try:
        eid = datos.crear_estudio(cliente, request.form.get("nombre"), producto=request.form.get("producto"),
                                  tema=request.form.get("tema"), idioma=idiomas.de_proyecto(cliente),
                                  catalogo_id=request.form.get("catalogo_id") or None,
                                  pais=request.form.get("pais") or proyectos.pais(cliente))
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Estudio creado. Ahora agrégale comentarios."), "ok")
    return _volver(cliente, eid)


@bp.get("/<int:eid>")
def ver(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if datos.es_manual(est):
        # Ruling 26: el estudio oculto de los avatares escritos a mano nunca
        # se abre como estudio (no tiene comentarios que revisar ni acciones
        # de estudio que apliquen) -- a la lista del proyecto, que es donde
        # esos avatares sí se ven y se editan.
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente))
    est["estado"] = datos.recalcular(cliente, eid) or est["estado"]
    fuente = request.args.get("fuente") or None
    try:
        pagina = int(request.args.get("pagina") or 1)
    except ValueError:
        pagina = 1
    lista = datos.comentarios_para_generar(cliente, eid)
    estimado = avatares.estimar_costo(lista)
    job = datos.job_id_generar(cliente, eid)
    inv_actual = datos.investigacion(cliente, eid)
    paso_vivo = investigacion.siguiente_paso(inv_actual)
    job_inv = investigacion.job_de_paso(cliente, eid, paso_vivo) if paso_vivo else None
    nucleos = datos.avatares(cliente, eid)
    for n in nucleos:
        for s in n["subs"]:
            s["faltantes"] = calidad.faltantes(s, con_evidencia=not datos.es_manual(est))
    completar_e = avatares.estimar_completar(cliente, eid)
    job_comp = datos.job_id_completar(cliente, eid)
    return render_template(
        "nicho_estudio.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente), estudio=est,
        conteos=datos.contar_por_fuente(cliente, eid), fuente_filtro=fuente,
        pagina_comentarios=datos.comentarios(cliente, eid, fuente=fuente, pagina=pagina, por_pagina=POR_PAGINA),
        nucleos=nucleos, urls_comentarios=datos.urls_comentarios(cliente, eid),
        estimado=estimado, precio_texto=gastos.formatear(estimado["usd"]), min_comentarios=avatares.MIN_COMENTARIOS,
        trabajo_generar=({"job_id": job} if trabajos.en_curso(job) else None),
        completar_estimado={**completar_e, "texto": gastos.formatear(completar_e["usd"])},
        trabajo_completar=({"job_id": job_comp} if trabajos.en_curso(job_comp) else None),
        modos_texto=fuente_texto.NOMBRES_MODO, fuentes_nombre=fuentes_registro.NOMBRES, idiomas=avatares.IDIOMAS,
        niveles_conciencia=datos.NIVELES_CONCIENCIA, bases=datos.BASES, productos_nicho=_productos(cliente),
        fuentes_conectadas=_fuentes_conectadas(cliente, eid),
        actores_apify=[{"clave": k, "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "ayuda": a["ayuda"]}
                       for k, a in apify_actores.ACTORES.items()],
        recolecciones=list(reversed((est["extra"].get("recolecciones") or [])[-5:])),
        periodos_reddit=fuente_reddit.PERIODOS, max_apify=apify_actores.MAX_RESULTADOS, region_defecto=proyectos.pais(cliente) or "",
        # El idioma de BÚSQUEDA de YouTube sale del país del proyecto (spec §B5: no es el idioma
        # de salida; con inglés por defecto, `estudio.idioma` haría buscar en inglés a un cliente LatAm).
        idioma_busqueda=plataformas.idioma(proyectos.pais(cliente) or ""),
        investigacion=investigacion.resumen(inv_actual),
        trabajo_inv=({"job_id": job_inv, "paso": paso_vivo} if job_inv and trabajos.en_curso(job_inv) else None),
        productos_investigados=(datos.productos_nicho(cliente, eid) if inv_actual else []),
        paises_estudio=[(c, datos.NOMBRES_PAIS.get(c, c)) for c in datos.PAISES_ESTUDIO],
        plataformas_inv=_plataformas_visibles(), redes_inv=_redes_visibles(), topes_inv=investigacion.TOPES_DEFECTO,
        limites_inv=investigacion.LIMITES, pais_inv=est.get("pais") or proyectos.pais(cliente),
        etiquetas_estudio=datos.ETIQUETAS_ESTADO_ESTUDIO, etiquetas_avatar=datos.ETIQUETAS_ESTADO_AVATAR,
        etiquetas_inv=investigacion.ETIQUETAS_ESTADO, etiquetas_paso_estado=investigacion.ETIQUETAS_ESTADO_PASO,
        etiquetas_paso=investigacion.ETIQUETAS_PASO, consciencias_nombre=doctrina.CONSCIENCIAS_NOMBRE,
        investigacion_viva=_investigacion_viva(cliente, eid))


@bp.post("/<int:eid>/editar")
def editar(cliente, eid):
    _estudio_o_404(cliente, eid)
    try:
        campos = {k: request.form.get(k) for k in ("nombre", "producto", "tema", "pais") if request.form.get(k) is not None}
        if request.form.get("catalogo_id") is not None:
            campos["catalogo_id"] = request.form.get("catalogo_id") or None
        datos.actualizar_estudio(cliente, eid, **campos)
        flash(gettext("Estudio guardado."), "ok")
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
        flash(gettext("Estudio eliminado permanentemente."), "ok")
    return _volver(cliente)


# -------------------------------------------------------- comentarios ---

def _agregar(cliente, eid, fuente, lista):
    r = datos.agregar_comentarios(cliente, eid, fuente, lista)
    datos.registrar_recoleccion(cliente, eid, {"fuente": fuente, "nuevos": r["nuevos"], "repetidos": r["repetidos"], "aviso": ""})
    datos.recalcular(cliente, eid)
    flash(gettext("Entraron %(nuevos)s comentario(s); %(repetidos)s repetido(s).", nuevos=r["nuevos"],
                  repetidos=r["repetidos"]), "ok")


@bp.post("/<int:eid>/comentarios/texto")
def comentarios_texto(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("texto")().recolectar(
            {"texto": request.form.get("texto"), "modo": request.form.get("modo") or "lineas"}))
        if not lista:
            flash(gettext("No encontré comentarios en el texto (mínimo 3 caracteres cada uno)."), "error")
        else:
            _agregar(cliente, eid, "texto", lista)
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/comentarios/archivo")
def comentarios_archivo(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    f = request.files.get("archivo")
    if not f or not f.filename:
        flash(gettext("Elige un archivo .csv o .xlsx."), "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("csv")().recolectar(
            {"nombre": f.filename, "contenido": f.read(fuente_archivo.MAX_BYTES + 1)}))
        if not lista:
            flash(gettext("El archivo no trajo comentarios."), "error")
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
    nombre_fuente = idiomas.traducir(fuentes_registro.NOMBRES.get(fuente, fuente))
    flash(gettext("Se quitaron %(n)s comentario(s) de %(fuente)s.", n=n, fuente=nombre_fuente), "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/recolectar/<fuente>")
def recolectar(cliente, eid, fuente):
    est = _estudio_o_404(cliente, eid)
    if fuente not in fuentes_registro.CONECTADAS:
        abort(404)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    if fuente in fuentes_registro.EN_WORKER and _investigacion_viva(cliente, eid):
        flash(gettext("Hay una investigación en curso en este estudio: espera a que termine o cancélala."), "error")
        return _volver(cliente, eid)
    faltan = fuentes_registro.llaves_faltantes(fuente)
    if faltan:
        flash(gettext("Falta %(llaves)s en el .env del servidor (Configuración › Puesta a punto).", llaves=", ".join(faltan))
              if _es_admin() else gettext("Esa fuente no está disponible todavía."), "error")
        return _volver(cliente, eid)
    try:
        params = _params_desde_form(fuente, est, cliente)
        _NORMALIZAR[fuente](params)                     # valida el formulario sin tocar la red
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
        return _volver(cliente, eid)
    nombre_fuente = idiomas.traducir(fuentes_registro.NOMBRES[fuente])
    if tareas_nicho.encolar_recolectar(cliente, eid, fuente, params):
        flash(gettext("Recolectando de %(fuente)s; la página se recarga sola al terminar.", fuente=nombre_fuente), "ok")
    else:
        flash(gettext("Ya hay una recolección de %(fuente)s en curso.", fuente=nombre_fuente), "error")
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
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    if _investigacion_viva(cliente, eid):
        flash(gettext("Hay una investigación en curso en este estudio: espera a que termine o cancélala."), "error")
        return _volver(cliente, eid)
    lista = datos.comentarios_para_generar(cliente, eid)
    if len(lista) < avatares.MIN_COMENTARIOS:
        flash(gettext("Hacen falta al menos %(minimo)s comentarios no excluidos (hay %(hay)s).",
                      minimo=avatares.MIN_COMENTARIOS, hay=len(lista)), "error")
        return _volver(cliente, eid)
    if tareas_nicho.encolar_generar(cliente, eid):
        flash(gettext("Claude está armando los avatares; la página se recarga sola al terminar."), "ok")
    else:
        flash(gettext("Ya hay una generación en curso para este estudio."), "error")
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


@bp.app_template_filter("faltantes_texto")
def faltantes_texto(faltantes):
    """['demografia', 'tono'] -> «demografía, tono» en el idioma de quien mira."""
    return ", ".join(idiomas.traducir(calidad.ETIQUETAS.get(k, k)) for k in faltantes or [])


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
        if datos.avatar(cliente, aid)["estado"] == "aprobado":
            datos.aprobar_avatar(cliente, aid)                          # la persona que usa la app queda igual que la ficha
            flash(gettext("Avatar guardado; la persona que usa la app se actualizó."), "ok")
        else:
            flash(gettext("Avatar guardado."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _destino_avatar(cliente, a)


@bp.post("/avatar/<int:aid>/aprobar")
def avatar_aprobar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.aprobar_avatar(cliente, aid)
        falta = _faltantes_de(cliente, datos.avatar(cliente, aid))
        if falta:
            flash(gettext("Avatar aprobado: ya es una persona de Sprints. Ojo, le falta: %(faltan)s.", faltan=faltantes_texto(falta)), "error")
        else:
            flash(gettext("Avatar aprobado: ya es una persona de Sprints."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _destino_avatar(cliente, a)


@bp.post("/avatar/<int:aid>/descartar")
def avatar_descartar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    if datos.descartar_avatar(cliente, aid):
        flash(gettext("Avatar descartado."), "ok")
    else:
        flash(gettext("Solo se descartan los sub-avatares; el núcleo es una agrupación."), "error")
    return _destino_avatar(cliente, a)


# ---------------------------------------------- avatares del proyecto ---

@bp.get("/avatares")
def avatares_proyecto(cliente):
    """Todos los avatares del proyecto (spec 2026-09-29 §3)."""
    grupos = datos.lista_avatares(cliente)
    ids = [e.get("comentario_id") for g in grupos.values() for x in g if x["avatar"] for e in (x["avatar"].get("evidencia") or [])]
    completables = avatares.completables_por_estudio(cliente)
    for c in completables:
        job = datos.job_id_completar(cliente, c["estudio_id"])
        c.update(texto=gastos.formatear(c["usd"]), job_id=job, en_curso=trabajos.en_curso(job))
    return render_template("nicho_avatares_proyecto.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           estudio=None, grupos=grupos, completables=completables, nuevo=request.args.get("nuevo") == "1",
                           abrir=request.args.get("abrir") or "", urls_comentarios=datos.urls_de_comentarios(cliente, ids),
                           niveles_conciencia=datos.NIVELES_CONCIENCIA, bases=datos.BASES, consciencias_nombre=doctrina.CONSCIENCIAS_NOMBRE)


@bp.post("/avatares/nuevo")
def avatar_crear(cliente):
    try:
        aid = datos.crear_avatar_manual(cliente, _campos_avatar_desde_form())
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, nuevo=1, _anchor="nuevo-avatar"))
    falta = calidad.faltantes(datos.avatar(cliente, aid), con_evidencia=False)
    if falta:
        flash(gettext("Avatar creado y aprobado: ya lo usa toda la app. Ojo, le falta: %(faltan)s.", faltan=faltantes_texto(falta)), "error")
    else:
        flash(gettext("Avatar creado y aprobado: ya lo usa toda la app."), "ok")
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, abrir=f"a{aid}", _anchor=f"avatar-a{aid}"))


@bp.post("/persona/<int:pid>/ficha")
def persona_ficha(cliente, pid):
    """«Editar ficha» de una persona sin avatar: le crea (una vez) su avatar y lo abre."""
    try:
        aid = datos.avatar_desde_persona(cliente, pid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente))
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, abrir=f"a{aid}", _anchor=f"avatar-a{aid}"))


@bp.post("/persona/<int:pid>/archivar")
def persona_archivar(cliente, pid):
    p = sprints_datos.persona(cliente, pid)
    if not p:
        abort(404)
    if (p.get("extra") or {}).get("avatar_id"):
        # Ruling 21: con un avatar detrás (cualquiera -- incluido el que crea
        # «Editar ficha»), esta persona ya no se archiva por esta ruta: se
        # aprueba/descarta desde SU ficha (acciones_avatar), que es lo único
        # que la plantilla ofrece para ella (tarjeta_avatar solo muestra
        # Archivar/Desarchivar cuando no hay avatar). Sin este candado, un
        # POST directo dejaría el avatar aprobado y la persona archivada a la
        # vez -- un estado que la UI no sabe mostrar de forma consistente.
        flash(gettext("Esta persona ya tiene un avatar: apruébalo o descártalo desde su ficha."), "error")
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente))
    sprints_datos.archivar_persona(cliente, pid, archivada=request.form.get("desarchivar") is None)
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, _anchor=f"avatar-p{pid}"))


@bp.post("/<int:eid>/completar")
def completar(cliente, eid):
    """«Completar N incompletos» con la cifra que la persona vio (la recalcula el servidor)."""
    est = _estudio_o_404(cliente, eid)
    volver = (redirect(url_for("nicho.avatares_proyecto", cliente=cliente)) if request.form.get("volver") == "lista"
              else _volver(cliente, eid))
    if est["archivado"] or datos.es_manual(est):
        flash(gettext("Ese estudio no se puede completar."), "error")
        return volver
    e = avatares.estimar_completar(cliente, eid)
    if not e["avatares"]:
        flash(gettext("No hay avatares incompletos que completar."), "ok")
        return volver
    try:
        visto = float(request.form.get("total_visto") or 0)
    except ValueError:
        visto = 0.0
    if e["usd"] > visto + 0.005:
        flash(gettext("El costo es %(costo)s y el que viste era otro: revísalo y vuelve a confirmar.", costo=gastos.formatear(e["usd"])), "error")
        return volver
    if tareas_nicho.encolar_completar(cliente, eid):
        flash(gettext("Completando %(n)s avatar(es); la página se recarga sola al terminar.", n=e["avatares"]), "ok")
    else:
        flash(gettext("Ya se están completando los avatares de este estudio."), "error")
    return volver


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


# ------ Investigación automática (Parte 3) ------

def _lista_param(fuente, nombre):
    """Checkboxes repetidos (`getlist`) o una lista con comas (el fetch del estimado)."""
    salida = []
    for v in fuente.getlist(nombre):
        salida.extend(x.strip() for x in (v or "").split(",") if x.strip())
    return list(dict.fromkeys(salida))


def _plataformas_visibles():
    """Las plataformas del registro; sin APIFY_TOKEN el admin las ve apagadas y el cliente no las ve."""
    salida = []
    for clave in plataformas.claves():
        faltan = fuentes_registro.llaves_faltantes(clave)
        if faltan and not _es_admin():
            continue
        paises = plataformas.PLATAFORMAS[clave]["paises"]
        salida.append({"clave": clave, "nombre": plataformas.nombre(clave), "faltan": faltan,
                       "paises": "*" if paises == plataformas.TODOS else " ".join(sorted(paises))})
    return salida


def _redes_visibles():
    salida = []
    for red in investigacion.REDES:
        faltan = fuentes_registro.llaves_faltantes(red)
        if faltan and not _es_admin():
            continue
        salida.append({"clave": red, "nombre": fuentes_registro.NOMBRES[red], "faltan": faltan})
    return salida


def _pedido_investigacion(fuente, est, cliente):
    """(pais, plataformas, redes, topes) validados. ErrorDatos o ValueError con
    un mensaje para la persona."""
    pais = (fuente.get("pais") or est.get("pais") or proyectos.pais(cliente) or "").strip().upper()
    if pais not in datos.PAISES_ESTUDIO:
        raise datos.ErrorDatos(gettext("País no soportado: %(pais)s", pais=pais or "—"))
    plats = [p for p in _lista_param(fuente, "plataformas") if p in plataformas.PLATAFORMAS]
    redes = [r for r in _lista_param(fuente, "redes") if r in investigacion.REDES]
    if not plats and not redes:
        raise datos.ErrorDatos(gettext("Elige al menos una plataforma o una red."))
    fuera = [p for p in plats if not plataformas.cubre(p, pais)]
    if fuera:
        raise datos.ErrorDatos(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=plataformas.nombre(fuera[0]), pais=pais))
    faltan = sorted({v for x in plats + redes for v in fuentes_registro.llaves_faltantes(x)})
    if faltan:
        raise datos.ErrorDatos(gettext("Falta %(llaves)s en el .env del servidor (Configuración › Puesta a punto).", llaves=", ".join(faltan))
                               if _es_admin() else gettext("Esa fuente no está disponible todavía."))
    topes = investigacion.normalizar_topes({k: fuente.get(k) for k in investigacion.TOPES_DEFECTO})
    return pais, plats, redes, topes


@bp.get("/<int:eid>/investigacion/estimar")
def investigacion_estimar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    try:
        pais, plats, redes, topes = _pedido_investigacion(request.args, est, cliente)
        e = investigacion.estimar(est, pais, plats, redes, topes)
    except (datos.ErrorDatos, ErrorFuente, ValueError) as ex:
        return jsonify({"error": str(ex)}), 400
    filas = [{**f, "busqueda_texto": gastos.formatear(f["busqueda_usd"]), "resenas_texto": gastos.formatear(f["resenas_usd"]),
              "nombre": f["nombre"]} for f in e["filas"]]
    return jsonify({**e, "filas": filas, "claude_texto": gastos.formatear(e["claude_usd"]), "avatares_texto": gastos.formatear(e["avatares_usd"]),
                    "texto": gastos.formatear(e["total_usd"]), "pais": pais, "plataformas": plats, "redes": redes, "topes": topes})


@bp.post("/<int:eid>/investigacion")
def investigacion_iniciar(cliente, eid):
    """Aprueba la cifra y arranca la cadena. La cifra la recalcula el servidor:
    si supera lo que la persona vio en el botón (`total_visto`), no arranca."""
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    if not (est.get("tema") or "").strip():
        flash(gettext("Escribe primero qué investigar (Editar estudio › Qué investigar)."), "error")
        return _volver(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if actual.get("estado") and actual["estado"] not in ("lista", "detenida", "interrumpida"):
        flash(gettext("Ya hay una investigación en curso."), "error")
        return _volver(cliente, eid)
    try:
        pais, plats, redes, topes = _pedido_investigacion(request.form, est, cliente)
        estimado = investigacion.estimar(est, pais, plats, redes, topes)
        visto = float(request.form.get("total_visto") or 0)
    except (datos.ErrorDatos, ErrorFuente, ValueError) as ex:
        flash(str(ex), "error")
        return _volver(cliente, eid)
    if estimado["total_usd"] > visto + 0.005:
        flash(gettext("El costo es %(costo)s y el que viste era otro: revísalo y vuelve a confirmar.",
                      costo=gastos.formatear(estimado["total_usd"])), "error")
        return _volver(cliente, eid)
    if est.get("pais") != pais:
        datos.actualizar_estudio(cliente, eid, pais=pais)
    datos.iniciar_investigacion(cliente, eid, investigacion.crear_inicial(est["tema"], pais, plats, redes, topes, estimado=estimado))
    tareas_investigacion.avanzar(cliente, eid)
    flash(gettext("Investigación en marcha con un tope de %(tope)s; la página muestra cada paso.",
                  tope=gastos.formatear(estimado["total_usd"])), "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/reanudar")
def investigacion_reanudar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if not investigacion.puede_reanudar(actual.get("estado")):
        flash(gettext("No hay una investigación detenida para reanudar."), "error")
        return _volver(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    datos.actualizar_investigacion(cliente, eid, investigacion.reanudar)
    if tareas_investigacion.avanzar(cliente, eid):
        flash(gettext("Investigación reanudada."), "ok")
    else:
        despues = datos.investigacion(cliente, eid)
        if despues.get("estado") == "detenida":
            flash(gettext("La investigación sigue detenida: %(motivo)s", motivo=idiomas.traducir(despues.get("detenida_por") or "")), "error")
        else:
            flash(gettext("La investigación terminó."), "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/cancelar")
def investigacion_cancelar(cliente, eid):
    _estudio_o_404(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if not actual.get("estado") or actual["estado"] in ("lista", "detenida", "interrumpida"):
        flash(gettext("No hay investigación en curso para cancelar."), "error")
        return _volver(cliente, eid)
    datos.actualizar_investigacion(cliente, eid, lambda i: investigacion.detener(i, N_("cancelada")))
    flash(gettext("Investigación cancelada: el paso que está corriendo termina y no se lanza el siguiente."), "ok")
    return _volver(cliente, eid)
