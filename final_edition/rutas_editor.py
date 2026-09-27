"""Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo
/cliente/<cliente>/ediciones: `dashboard._guard_por_cliente` exige sesión con
acceso al proyecto (admin a todo; un cliente solo al suyo) — decisión de
Daniel del 2026-09-27: el editor es para todos, sin esperar a la capa 7.
`ediciones.cargar` filtra por cliente: una edición de otro proyecto es 404."""
from flask import Blueprint, abort, jsonify, render_template, url_for

import ediciones
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
