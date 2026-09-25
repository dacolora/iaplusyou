"""
Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Bloque 1: fragmentos
HTML para el grid (filtros + paginación) y la ficha, solo lectura.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
`<cliente>`; la visibilidad (global + propios) la aplica referentes.datos.
Bloque 2 agrega `recrear_form`/`recrear_adaptar`/`recrear_generar` («Recrear
con mi producto»); los créditos de generación se gastan a través del pipeline
de Crear que ya existe (`creative_flow` + `flowplus_lanzar`), no se reimplementan aquí.
"""
from uuid import uuid4

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

import catalogo_productos
import creative_flow
import flowplus_lanzar
import gastos
import marca as marca_mod
import proyectos
from nicho.avatares import costo_real, modelo_actual
from providers import flowplus_modelos
from referentes import datos, fuentes, recrear
from referentes.fuentes.base import ErrorFuente
from sprints import datos as sprints_datos
from tareas import referentes as tareas_referentes

bp = Blueprint("referentes", __name__, url_prefix="/cliente/<cliente>/referentes")
_FILTROS = ("etapa", "consciencia", "familia", "dolor", "marca", "fuente", "q")


def contexto(cliente):
    """Lo que necesita _tab_referentes.html. Se llama desde dashboard.ver_cliente."""
    return {"ref_opciones": datos.opciones(cliente), "ref_etapas": datos.ETAPAS, "ref_consciencias": datos.CONSCIENCIAS,
            "ref_etiquetas_etapa": datos.ETIQUETAS_ETAPA, "ref_etiquetas_consciencia": datos.ETIQUETAS_CONSCIENCIA,
            "ref_fuentes": datos.FUENTES}


def filtros_desde(args):
    return {k: (args.get(k) or "").strip() for k in _FILTROS if (args.get(k) or "").strip()}


def _entero(v, defecto):
    try:
        return int(v)
    except (TypeError, ValueError):
        return defecto


@bp.get("/grid")
def grid(cliente):
    filtros = filtros_desde(request.args)
    por_pagina = min(max(1, _entero(request.args.get("por_pagina"), datos.POR_PAGINA)), 120)
    pagina = datos.listar(cliente, filtros, pagina=_entero(request.args.get("pagina"), 1), por_pagina=por_pagina)
    campana = (request.args.get("campana") or "").strip() or None
    return render_template("_referentes_grid.html", cliente=cliente, pagina=pagina, filtros=filtros, por_pagina=por_pagina,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA,
                           campana=campana)


def _producto_para(cliente, request_args_o_form):
    productos = catalogo_productos.listar(cliente, "producto")
    pid = request_args_o_form.get("producto_id") or (productos[0]["id"] if productos else None)
    producto = catalogo_productos.encontrar(cliente, pid, categoria="producto") if pid else None
    return productos, producto


def _consulta_desde(args):
    return {
        "modo": args.get("modo") if args.get("modo") in ("marca", "palabra") else "palabra",
        "pagina_id": (args.get("pagina_id") or "").strip() or None,
        "palabra": (args.get("palabra") or "").strip() or None,
        "idioma": (args.get("idioma") or "es").strip()[:5],
        "formato": args.get("formato") if args.get("formato") in ("imagen", "video") else "imagen",
        "solo_activos": args.get("solo_activos") not in (None, "", "0", "false"),
        "min_dias": _entero(args.get("min_dias"), None),
        "min_variantes": _entero(args.get("min_variantes"), None),
    }


@bp.get("/traer")
def traer_form(cliente):
    fuente = request.args.get("fuente") if request.args.get("fuente") in fuentes.tipos() else (fuentes.tipos()[0] if fuentes.tipos() else None)
    tope = min(max(1, _entero(request.args.get("tope"), 200)), 2000)
    consulta = _consulta_desde(request.args)
    precio = None
    llaves_faltantes = fuentes.llaves_faltantes(fuente) if fuente else []
    if fuente and not llaves_faltantes and (consulta.get("pagina_id") or consulta.get("palabra")):
        modulo = fuentes.por_tipo(fuente)
        est_fuente = modulo.estimar(consulta, tope)
        est_clasificacion = gastos.estimar("clasificacion", n=tope)
        precio = {"fuente": est_fuente, "clasificacion": est_clasificacion,
                  "total_usd": est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)}
    return render_template("_referentes_traer.html", cliente=cliente, fuentes_tipos=fuentes.tipos(),
                           fuentes_nombres=fuentes.NOMBRES, fuente=fuente, consulta=consulta, tope=tope,
                           precio=precio, llaves_faltantes=llaves_faltantes,
                           fuente_llaves_faltantes={t: fuentes.llaves_faltantes(t) for t in fuentes.tipos()})


@bp.post("/traer")
def traer_post(cliente):
    fuente = request.form.get("fuente")
    if fuente not in fuentes.tipos():
        flash("Elige una fuente.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    if fuentes.llaves_faltantes(fuente):
        flash("Esa fuente no está configurada.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    consulta = _consulta_desde(request.form)
    if consulta["modo"] == "marca" and not consulta["pagina_id"]:
        flash("Pega un link del Ad Library o el id de la página.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    if consulta["modo"] == "palabra" and not consulta["palabra"]:
        flash("Escribe una palabra clave.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    tope = min(max(1, _entero(request.form.get("tope"), 200)), 2000)
    modulo = fuentes.por_tipo(fuente)
    try:
        est_fuente = modulo.estimar(consulta, tope)
    except ErrorFuente as e:
        flash(e.usuario, "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    est_clasificacion = gastos.estimar("clasificacion", n=tope)
    usd_estimado = est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)
    tareas_referentes.encolar_barrer(cliente, fuente, consulta, tope, usd_estimado, pedido_por=session.get("usuario"))
    flash("Trayendo referentes; aparecerán en «Mis barridos» a medida que avanza.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


@bp.get("/<int:rid>/recrear")
def recrear_form(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    productos, producto = _producto_para(cliente, request.args)
    tipo = request.args.get("tipo") if request.args.get("tipo") in ("imagen", "video") else "imagen"
    formato = request.args.get("formato") or flowplus_modelos.FORMATO_DEFECTO
    titular = request.args.get("titular")
    if titular is None:
        titular = r.get("titular") or ""
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    prefs_sonido = proyectos.preferencias_sonido(cliente)
    prompt = precio = None
    if producto:
        guia = marca_mod.guia_efectiva(cliente)
        prompt = recrear.armar_prompt(r, familia, producto, guia, titular, formato, tipo=tipo,
                                      con_sonido=prefs_sonido["con_sonido"])
        n_refs = 1 + max(1, min(2, len(producto.get("referencias") or [1])))
        if tipo == "imagen":
            precio = gastos.estimar("imagen", modelo=flowplus_modelos.IMAGEN_POR_DEFECTO, n_referencias=n_refs)
        else:
            duracion = proyectos.preferencias_flowplus(cliente)["duracion_defecto"]
            precio = gastos.estimar("video", modelo=flowplus_modelos.VIDEO_POR_DEFECTO, duracion=duracion,
                                    con_sonido=prefs_sonido["con_sonido"])
    return render_template(
        "_referente_recrear.html", cliente=cliente, r=r, productos=productos, producto=producto, tipo=tipo,
        formato=formato, titular=titular, prompt=prompt or "", precio=precio,
        precio_adaptar=gastos.estimar("adaptar_referente"),
        formatos=flowplus_modelos.IMAGEN[flowplus_modelos.IMAGEN_POR_DEFECTO]["formatos"])


@bp.post("/<int:rid>/recrear/adaptar")
def recrear_adaptar(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        return jsonify({"error": "Ese referente no existe."}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": "Cuerpo inválido."}), 400
    producto = catalogo_productos.encontrar(cliente, cuerpo.get("producto_id"), categoria="producto") if cuerpo.get("producto_id") else None
    if not producto:
        return jsonify({"error": "Elige un producto primero."}), 400
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    try:
        resultado, ent, sal = recrear.adaptar(r, familia, producto, str(cuerpo.get("titular") or ""),
                                              marca_mod.guia_efectiva(cliente))
    except recrear.AdaptacionInvalida as e:
        ent = getattr(e, "tokens_entrada", 0) or 0
        sal = getattr(e, "tokens_salida", 0) or 0
        if ent or sal:
            usd = costo_real(ent, sal)
            gastos.registrar_seguro(cliente, "adaptar_referente", usd, f"referentes:adaptar:{rid}:{uuid4().hex[:12]}",
                                    detalle=f"{producto['nombre']} · {r.get('familia') or ''} · respuesta inválida",
                                    proveedor="anthropic",
                                    extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"No se pudo adaptar ({type(e).__name__})."}), 502
    usd = costo_real(ent, sal)
    gastos.registrar_seguro(cliente, "adaptar_referente", usd, f"referentes:adaptar:{rid}:{uuid4().hex[:12]}",
                            detalle=f"{producto['nombre']} · {r.get('familia') or ''}", proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
    return jsonify(resultado)


@bp.post("/<int:rid>/recrear/generar")
def recrear_generar(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        flash("Ese referente no existe.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    tipo = request.form.get("tipo") if request.form.get("tipo") in ("imagen", "video") else "imagen"
    producto = catalogo_productos.encontrar(cliente, request.form.get("producto_id"), categoria="producto") \
        if request.form.get("producto_id") else None
    if not producto:
        flash("Elige un producto con fotos.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    titular = (request.form.get("titular") or "").strip()[:200]
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        flash("El prompt no puede quedar vacío.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    formato_pedido = request.form.get("formato") or flowplus_modelos.FORMATO_DEFECTO
    try:
        referencias_urls = recrear.referencias_para(cliente, r, producto)
    except Exception as e:
        flash(f"No se pudieron preparar las referencias ({type(e).__name__}).", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    prefs_sonido = proyectos.preferencias_sonido(cliente)
    if tipo == "imagen":
        modelo = flowplus_modelos.IMAGEN_POR_DEFECTO
        formato = flowplus_modelos.ajustar_formato(modelo, formato_pedido, tipo="imagen")
        duracion_objetivo = 0
    else:
        modelo = flowplus_modelos.VIDEO_POR_DEFECTO
        duracion_objetivo = flowplus_modelos.ajustar_duracion(
            modelo, proyectos.preferencias_flowplus(cliente)["duracion_defecto"])
        formato = flowplus_modelos.ajustar_formato(modelo, formato_pedido)
    cf_id = creative_flow.crear(cliente, [], [producto["nombre"]], [],
                                titular or f"Recrear: {r.get('titular') or r['id']}",
                                duracion_objetivo, "", "A", referencias_urls=referencias_urls, platforms=[])
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt, aspect_ratio=formato, tipo=tipo, modelo=modelo,
                             con_sonido=prefs_sonido["con_sonido"], sonido_texto="", musica_estilo="",
                             calidad="final", referente_id=rid)
    entry = creative_flow.cargar(cliente)[cf_id]
    if flowplus_lanzar.lanzar(cliente, cf_id, entry):
        flash("Generando desde el referente…", "ok")
    else:
        flash("Ya había algo generándose para esta sesión.", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@bp.get("/<int:rid>/ficha")
def ficha(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    return render_template("_referente_ficha.html", cliente=cliente, r=r, familia=familia,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA,
                           usos=recrear.usos(cliente, rid))


@bp.get("/barridos")
def barridos(cliente):
    lista = datos.barridos(cliente=cliente)
    for b in lista:
        b["trabajo"] = tareas_referentes.trabajo_barrer(b["id"])
    return render_template("_referentes_barridos.html", cliente=cliente, barridos=lista)


def _barrido_del_cliente_o_404(cliente, bid):
    b = datos.barrido(bid)
    if not b or b.get("cliente") != cliente:
        abort(404)
    return b


@bp.post("/<int:bid>/clasificar_pendientes")
def clasificar_pendientes(cliente, bid):
    _barrido_del_cliente_o_404(cliente, bid)
    if tareas_referentes.encolar_clasificar_pendientes(cliente, bid):
        flash("Clasificando lo pendiente; la lista se actualiza sola.", "ok")
    else:
        flash("Ya hay algo en curso para este barrido.", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


@bp.post("/<int:bid>/reintentar_imagenes")
def reintentar_imagenes(cliente, bid):
    _barrido_del_cliente_o_404(cliente, bid)
    if tareas_referentes.encolar_reintentar_imagenes(cliente, bid):
        flash("Reintentando las imágenes que fallaron.", "ok")
    else:
        flash("Ya hay algo en curso para este barrido.", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


@bp.get("/<int:rid>/usar_en_sprint")
def usar_en_sprint(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    elegibles = []
    for sp in sprints_datos.sprints(cliente):
        if sp["estado"] not in ("planeando", "referencias"):
            continue
        for c in sp["campanas"]:
            elegibles.append({"sprint_nombre": sp["nombre"], "campana_id": c["id"],
                              "campana_n": int(c["orden"]) + 1, "funnel": c["funnel"],
                              "persona_nombre": c.get("persona_nombre")})
    return render_template("_referente_usar_en_sprint.html", cliente=cliente, r=r, elegibles=elegibles,
                           etiquetas_funnel=sprints_datos.FUNNELS_NOMBRE)
