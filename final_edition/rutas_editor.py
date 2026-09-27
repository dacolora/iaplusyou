"""Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo
/cliente/<cliente>/ediciones: `dashboard._guard_por_cliente` exige sesión con
acceso al proyecto (admin a todo; un cliente solo al suyo) — decisión de
Daniel del 2026-09-27: el editor es para todos, sin esperar a la capa 7.
`ediciones.cargar` filtra por cliente: una edición de otro proyecto es 404."""
import re

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import creative_flow
import ediciones
import materiales
import trabajos
from final_edition import documento as documento_mod
from final_edition import estimar, vista_previa
from final_edition.documento import DocumentoInvalido
from tareas import edicion as tareas_edicion

bp = Blueprint("editor", __name__, url_prefix="/cliente/<cliente>/ediciones")

_DESTINO_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")


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


@bp.post("/<int:edicion_id>/producir")
def producir(cliente, edicion_id):
    """Producir desde el editor (spec §6): congela la versión guardada y encola
    un render por destino. Gratis: voz, música y video ya son materiales."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": "No existe esa edición."}), 404
    if not ed.get("cf_id"):
        return jsonify({"error": "Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí."}), 400
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("version_n"), int) \
            or isinstance(cuerpo.get("version_n"), bool) or not isinstance(cuerpo.get("destinos"), list) \
            or not all(isinstance(d, str) for d in cuerpo.get("destinos")):
        return jsonify({"error": "Pedido inválido: se esperaba {version_n, destinos}."}), 400
    # Chequeo rápido en memoria: un 409 inmediato sin tocar la base cuando la
    # versión ya se ve distinta a simple vista. No reemplaza el CAS de abajo
    # (fix round 1, Important): entre esta lectura y `ediciones.versionar` un
    # autoguardado de otra pestaña puede colarse, así que `versionar` vuelve a
    # comparar `version_n` dentro de la misma transacción que congela.
    if cuerpo["version_n"] != ed["version_n"]:
        return jsonify({"error": "La edición cambió: espera a que termine de guardarse y vuelve a intentar."}), 409
    doc = ed["documento"]
    validos = set(vista_previa.destinos(doc))
    destinos = cuerpo["destinos"]
    if not destinos or any(not _DESTINO_RE.match(d) or d not in validos for d in destinos):
        return jsonify({"error": "Elige al menos un destino de esta edición."}), 400
    problemas = []
    for d in destinos:
        idioma, pais = d.split("_")
        try:
            documento_mod.resolver(doc, idioma, pais)
        except DocumentoInvalido as e:
            problemas.append(f"{d}: {e}")
    if problemas:
        return jsonify({"error": "Hay textos sin traducir para algún destino.", "problemas": problemas}), 400
    try:
        version = ediciones.versionar(cliente, edicion_id, motivo="producir", version_n=cuerpo["version_n"])
    except ediciones.Conflicto as e:
        return jsonify({"error": str(e)}), 409
    segundos = estimar.segundos(doc)
    producidas = []
    for d in destinos:
        idioma, pais = d.split("_")
        job_id = tareas_edicion.job_id_producir(cliente, edicion_id, idioma, pais)
        if trabajos.en_curso(job_id):
            producidas.append({"destino": d, "final_id": f"{ed['cf_id']}__{d}", "encolada": False})
            continue
        final_id = creative_flow.crear_final(cliente, ed["cf_id"], idioma, pais)
        encolada = trabajos.encolar(job_id, "edicion_producir",
                                    {"cliente": cliente, "edicion_id": edicion_id, "version_id": version["id"],
                                     "final_id": final_id, "idioma": idioma, "pais": pais},
                                    duracion_estimada=segundos, etapas=list(tareas_edicion.ETAPAS_EDICION),
                                    cliente=cliente, max_intentos=1)
        producidas.append({"destino": d, "final_id": final_id, "encolada": bool(encolada)})
    return jsonify({"producidas": producidas,
                    "url": url_for("ver_cliente", cliente=cliente) + f"#final?cf={ed['cf_id']}"})


@bp.post("/desde/<cf_id>")
def desde_clon(cliente, cf_id):
    """«Editar este video» (gratis): encola la preparación y vuelve a la pieza
    en Final edition, donde la barra muestra el avance."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    entry = creative_flow.cargar(cliente).get(cf_id)
    volver = url_for("ver_cliente", cliente=cliente)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        flash("Esa pieza no tiene un video listo para editar.", "error")
        return redirect(volver + "#final")
    encolado = trabajos.encolar(tareas_edicion.job_id_desde_clon(cliente, cf_id), "edicion_desde_clon",
                                {"cliente": cliente, "cf_id": cf_id}, duracion_estimada=40,
                                etapas=[("Preparando el video", 100)], cliente=cliente, max_intentos=2)
    flash("Preparando el video para el editor… en unos segundos aparece «Abrir en el editor»." if encolado
          else "Ya se estaba preparando ese video.", "ok")
    return redirect(volver + f"#final?cf={cf_id}")
