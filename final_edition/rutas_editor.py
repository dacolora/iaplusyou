"""Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo
/cliente/<cliente>/ediciones: `dashboard._guard_por_cliente` exige sesión con
acceso al proyecto (admin a todo; un cliente solo al suyo) — decisión de
Daniel del 2026-09-27: el editor es para todos, sin esperar a la capa 7.
`ediciones.cargar` filtra por cliente: una edición de otro proyecto es 404."""
from flask import Blueprint, abort, jsonify, render_template, request, url_for

import ediciones
import materiales
from final_edition import documento as documento_mod
from final_edition import vista_previa
from final_edition.documento import DocumentoInvalido

bp = Blueprint("editor", __name__, url_prefix="/cliente/<cliente>/ediciones")


def _cargar(cliente, edicion_id):
    try:
        return ediciones.cargar(cliente, edicion_id)
    except DocumentoInvalido:
        return None


@bp.get("/<int:edicion_id>")
def ver(cliente, edicion_id):
    ed = _cargar(cliente, edicion_id)
    if not ed:
        abort(404)
    datos = vista_previa.datos_pagina(cliente, ed, url_for("editor.materiales_json", cliente=cliente, edicion_id=edicion_id))
    vista_previa.encolar_proxies(cliente, datos["pendientes"])
    return render_template("editor.html", cliente=cliente, edicion=ed, datos=datos)


@bp.get("/<int:edicion_id>/materiales")
def materiales_json(cliente, edicion_id):
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": "No existe esa edición."}), 404
    mats = vista_previa.materiales_para(cliente, ed["documento"])
    return jsonify({"materiales": {str(k): v for k, v in mats.items()}, "pendientes": vista_previa.pendientes(mats)})


def _mismo_origen():
    """Mismo criterio que `dashboard._mismo_origen` (no se importa de ahí: con
    `python dashboard.py` ese módulo es __main__ y se cargaría dos veces)."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


def _materiales_ajenos(cliente, doc):
    """Ids de `doc["materiales"]` (ya derivados por validar) que no son de
    este proyecto: un documento no puede apuntar a archivos de otro cliente."""
    return [m for m in doc.get("materiales") or [] if not materiales.obtener(cliente, int(m))]


@bp.put("/<int:edicion_id>")
def guardar(cliente, edicion_id):
    """Autoguardado (spec §5): CAS por `version_n`; 409 si otra pestaña guardó antes."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("documento"), dict) \
            or not isinstance(cuerpo.get("version_n"), int) or isinstance(cuerpo.get("version_n"), bool):
        return jsonify({"error": "Pedido inválido: se esperaba {documento, version_n}."}), 400
    try:
        doc = documento_mod.validar(cuerpo["documento"])
        ajenos = _materiales_ajenos(cliente, doc)
        if ajenos:
            return jsonify({"error": "La edición usa archivos que no son de este proyecto."}), 400
        nuevo = ediciones.guardar(cliente, edicion_id, doc, cuerpo["version_n"])
    except DocumentoInvalido as e:
        return jsonify({"error": str(e)}), 400
    except ediciones.Conflicto as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"version_n": nuevo})
