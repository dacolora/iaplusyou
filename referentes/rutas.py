"""
Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Solo lectura en el
bloque 1: fragmentos HTML para el grid (filtros + paginación) y la ficha.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
`<cliente>`; la visibilidad (global + propios) la aplica referentes.datos.
"""
from uuid import uuid4

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import catalogo_productos
import creative_flow
import flowplus_lanzar
import gastos
import marca as marca_mod
import proyectos
from nicho.avatares import costo_real, modelo_actual
from providers import flowplus_modelos
from referentes import datos, recrear

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
    return render_template("_referentes_grid.html", cliente=cliente, pagina=pagina, filtros=filtros, por_pagina=por_pagina,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)


def _producto_para(cliente, request_args_o_form):
    productos = catalogo_productos.listar(cliente, "producto")
    pid = request_args_o_form.get("producto_id") or (productos[0]["id"] if productos else None)
    producto = catalogo_productos.encontrar(cliente, pid, categoria="producto") if pid else None
    return productos, producto


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
        resultado, ent, sal = recrear.adaptar(r, familia, producto, str(cuerpo.get("titular") or ""))
    except recrear.AdaptacionInvalida as e:
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
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)
