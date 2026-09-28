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
from final_edition import biblioteca
from final_edition import documento as documento_mod
from final_edition import estimar, vista_previa
from final_edition.documento import DocumentoInvalido
from final_edition.motor import compilador
from tareas import edicion as tareas_edicion
from tareas import final_edition as tareas_fe

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
    base = url_for("ver_cliente", cliente=cliente)
    urls = {"materiales": url_for("editor.materiales_json", cliente=cliente, edicion_id=edicion_id),
            "guardar": url_for("editor.guardar", cliente=cliente, edicion_id=edicion_id),
            "producir": url_for("editor.producir", cliente=cliente, edicion_id=edicion_id),
            "final": base + "#final" + (f"?cf={ed['cf_id']}" if ed.get("cf_id") else ""),
            # capa 4b: la biblioteca del proyecto; `agregar_pieza` lleva `__CF__`
            # donde el navegador pone el id de la pieza de Crear
            "biblioteca": url_for("editor.biblioteca", cliente=cliente),
            "subir": url_for("editor.subir", cliente=cliente),
            "agregar_pieza": url_for("editor.agregar_pieza", cliente=cliente, cf_id="__CF__"),
            "materiales_por_id": url_for("editor.materiales_por_id", cliente=cliente)}
    datos = vista_previa.datos_pagina(cliente, ed, urls)
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
        try:
            doc = documento_mod.validar(cuerpo["documento"])
        except (TypeError, AttributeError):
            # un tipo que validar no espera (p. ej. "pistas": [1]) revienta al
            # recorrerlo: es un documento mal armado, no un error del servidor
            return jsonify({"error": "El documento no tiene la forma esperada."}), 400
        ajenos = _materiales_ajenos(cliente, doc)
        if ajenos:
            return jsonify({"error": "La edición usa archivos que no son de este proyecto."}), 400
        nuevo = ediciones.guardar(cliente, edicion_id, doc, cuerpo["version_n"])
    except DocumentoInvalido as e:
        return jsonify({"error": str(e)}), 400
    except ediciones.Conflicto as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"version_n": nuevo})


def _duraciones(cliente, doc):
    """{material_id: duracion_ms} de los materiales del documento que son de
    ESTE proyecto y tienen duración medida (los demás no se juzgan)."""
    out = {}
    for mid in doc.get("materiales") or []:
        m = materiales.obtener(cliente, int(mid))
        if m and m.get("duracion_ms"):
            out[int(mid)] = int(m["duracion_ms"])
    return out


@bp.post("/<int:edicion_id>/producir")
def producir(cliente, edicion_id):
    """Producir desde el editor (spec §6): congela la versión guardada y encola
    un render por destino. Gratis: se produce con lo que ya hay en la edición
    (materiales ya pagados), sin pedir nada nuevo a ningún proveedor.

    Antes de congelar nada, por destino: los textos resuelven, ningún clip
    pide más material del que hay (`compilador.verificar_recortes`, el mismo
    chequeo que haría el render en el worker), no hay una final con voz
    (`final_producir`) produciéndose, y si ya existe una final con video que
    NO salió de esta edición (la vía automática, otra edición) se pide
    confirmación — 409 con `reemplazos` — salvo que el cuerpo traiga
    `reemplazar: true`. Cualquier respuesta que no sea 200 no crea ni encola nada."""
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
    problemas, recortes = [], []
    for d in destinos:
        idioma, pais = d.split("_")
        try:
            resuelto = documento_mod.resolver(doc, idioma, pais)
        except DocumentoInvalido as e:
            problemas.append(f"{d}: {e}")
            continue
        try:
            compilador.verificar_recortes(resuelto, _duraciones(cliente, resuelto))
        except ValueError as e:
            recortes.append(f"{d}: {e}")
    if problemas:
        return jsonify({"error": "Hay textos sin traducir para algún destino.", "problemas": problemas}), 400
    if recortes:
        return jsonify({"error": "Esta edición no se puede producir así:", "problemas": recortes}), 400
    for d in destinos:
        idioma, pais = d.split("_")
        if trabajos.en_curso(tareas_fe.job_id_final(cliente, ed["cf_id"], idioma, pais)):
            return jsonify({"error": "Esa final se está produciendo con voz; espera a que termine."}), 409
    if cuerpo.get("reemplazar") is not True:
        reemplazos = []
        for d in destinos:
            final = creative_flow.final_por_legado(cliente, f"{ed['cf_id']}__{d}")
            if final and final.get("video_url") \
                    and ediciones.edicion_de_final(cliente, f"{ed['cf_id']}__{d}") != edicion_id:
                reemplazos.append(d)
        if reemplazos:
            error = ("Ya hay una final de ese destino hecha por otro camino (puede tener voz); si produces, esta la reemplaza."
                     if len(reemplazos) == 1 else
                     "Ya hay finales de esos destinos hechas por otro camino (pueden tener voz); si produces, estas las reemplazan.")
            return jsonify({"error": error, "reemplazos": reemplazos}), 409
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
    """«Editar» (gratis): encola la preparación y vuelve a la pieza en Final
    edition, donde la barra muestra el avance. El `&abrir=editor` del destino
    es lo que le dice al script de la pestaña que, cuando la recarga
    automática de iniciarPolling() vea la edición lista, entre directo al
    editor en vez de quedarse en el detalle (Editor capa 4b, tarea 9)."""
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
    flash("Preparando el video para el editor… se abre solo en cuanto esté listo." if encolado
          else "Ya se estaba preparando ese video.", "ok")
    return redirect(volver + f"#final?cf={cf_id}&abrir=editor")


# --- Biblioteca del editor (capa 4b, Task 1): subir, listar y preparar piezas ---

@bp.post("/materiales/subir", endpoint="subir")
def subir_material(cliente):
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return jsonify({"error": "Elige un archivo."}), 400
    try:
        material = biblioteca.subir(cliente, archivo)
    except biblioteca.SubidaInvalida as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"material": material})


@bp.get("/biblioteca", endpoint="biblioteca")
def ver_biblioteca(cliente):
    return jsonify(biblioteca.listar(cliente))


@bp.post("/biblioteca/pieza/<cf_id>", endpoint="agregar_pieza")
def agregar_pieza(cliente, cf_id):
    """Añade una pieza de Crear a la biblioteca (gratis): si ya es un
    material, lo devuelve tal cual; si no, encola su preparación
    (`material_de_pieza`) y responde 202 mientras tanto."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    if not tareas_edicion._CF_RE.fullmatch(cf_id or ""):
        return jsonify({"error": "No existe esa pieza."}), 404
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") != "video":
        return jsonify({"error": "No existe esa pieza."}), 404
    existente = biblioteca.material_de_pieza(cliente, cf_id)
    if existente:
        return jsonify({"material": vista_previa.material_para(existente)})
    trabajos.encolar(tareas_edicion.job_id_material_de_pieza(cliente, cf_id), "material_de_pieza",
                     {"cliente": cliente, "cf_id": cf_id}, duracion_estimada=30, cliente=cliente, max_intentos=2)
    return jsonify({"preparando": True}), 202


@bp.get("/materiales", endpoint="materiales_por_id")
def materiales_por_id(cliente):
    """`?ids=1,2,3` -> {materiales: {id: material_para(m)}} solo de este
    proyecto (un id ajeno o inexistente simplemente no aparece)."""
    ids = []
    for parte in (request.args.get("ids") or "").split(","):
        parte = parte.strip()
        if parte.isdigit():
            ids.append(int(parte))
    out = {}
    for mid in ids:
        m = materiales.obtener(cliente, mid)
        if m:
            out[str(mid)] = vista_previa.material_para(m)
    return jsonify({"materiales": out})
