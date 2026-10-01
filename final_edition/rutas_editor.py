"""Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo
/cliente/<cliente>/ediciones: `dashboard._guard_por_cliente` exige sesión con
acceso al proyecto (admin a todo; un cliente solo al suyo) — decisión de
Daniel del 2026-09-27: el editor es para todos, sin esperar a la capa 7.
`ediciones.cargar` filtra por cliente: una edición de otro proyecto es 404."""
import re

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext

import audios
import creative_flow
import ediciones
import gastos
import idiomas
import materiales
import trabajos
from final_edition import biblioteca
from final_edition import documento as documento_mod
from final_edition import estimar, textos_editor, transcripcion, vista_previa
from final_edition.documento import DocumentoInvalido
from final_edition.motor import compilador
from tareas import edicion as tareas_edicion
from tareas import final_edition as tareas_fe

bp = Blueprint("editor", __name__, url_prefix="/cliente/<cliente>/ediciones")

_DESTINO_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")
ERROR_GUARDAR = idiomas.N_("No se pudo guardar este cambio; deshazlo y vuelve a intentar.")


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
            "materiales_por_id": url_for("editor.materiales_por_id", cliente=cliente),
            # capa 4c: «Borrar» en la biblioteca; el navegador pone el id en `__ID__`
            "borrar_material": url_for("editor.borrar_material", cliente=cliente, material_id="__ID__"),
            # capa 5a: subtítulos automáticos (Task 5); `estado_trabajo` es la
            # misma ruta de siempre para la barra de progreso (`__JOB__` lo
            # pone el navegador con el job_id que toque).
            "subtitulos_estimar": url_for("editor.subtitulos_estimar", cliente=cliente, edicion_id=edicion_id),
            "transcribir": url_for("editor.transcribir", cliente=cliente, edicion_id=edicion_id),
            # capa 5a (Task 6): voz con IA (caché compartida con Crear › Audios,
            # `voz_material` con `__CLAVE__` = hash_voz) y grabación del micrófono.
            "voz_estimar": url_for("editor.voz_estimar", cliente=cliente, edicion_id=edicion_id),
            "voz": url_for("editor.voz", cliente=cliente, edicion_id=edicion_id),
            "voz_material": url_for("editor.voz_material", cliente=cliente, clave="__CLAVE__"),
            "grabacion": url_for("editor.grabacion", cliente=cliente),
            "muestra_voz": url_for("au_muestra", cliente=cliente),
            "estado_trabajo": url_for("estado_trabajo", job_id="__JOB__")}
    datos = vista_previa.datos_pagina(cliente, ed, urls)
    # Los textos de static/editor/*.js en el idioma de quien mira (textos.js
    # los pone con ponerTextos antes de construir nada).
    datos["textos"] = textos_editor.textos()
    datos["idioma_ui"] = idiomas.activo()
    vista_previa.encolar_proxies(cliente, datos["pendientes"])
    # capa 4c: el borrador de la vía automática se nombra «Borrador automático · …»
    return render_template("editor.html", cliente=cliente, edicion=ed, datos=datos,
                           nombre_edicion=ediciones.nombre_visible(ed))


@bp.get("/<int:edicion_id>/materiales")
def materiales_json(cliente, edicion_id):
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    mats = vista_previa.materiales_para(cliente, ed["documento"])
    return jsonify({"materiales": {str(k): v for k, v in mats.items()}, "pendientes": vista_previa.pendientes(mats)})


def _mismo_origen():
    """Mismo criterio que `dashboard._mismo_origen` (no se importa de ahí: con
    `python dashboard.py` ese módulo es __main__ y se cargaría dos veces)."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


def _materiales_ajenos(cliente, doc):
    """Ids de `doc["materiales"]` (ya derivados por validar) y de las fuentes
    de subtítulos (`subtitulos.fuentes`, que `materiales` no incluye) que no
    son de este proyecto: un documento no puede apuntar a archivos de otro
    cliente."""
    ids = {int(m) for m in doc.get("materiales") or []}
    for lista in ((doc.get("subtitulos") or {}).get("fuentes") or {}).values():
        ids.update(int(f["material_id"]) for f in lista or [] if f.get("material_id") is not None)
    return [m for m in sorted(ids) if not materiales.obtener(cliente, m)]


@bp.put("/<int:edicion_id>")
def guardar(cliente, edicion_id):
    """Autoguardado (spec §5): CAS por `version_n`; 409 si otra pestaña guardó antes."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("documento"), dict) \
            or not isinstance(cuerpo.get("version_n"), int) or isinstance(cuerpo.get("version_n"), bool):
        return jsonify({"error": gettext("Pedido inválido: se esperaba {documento, version_n}.")}), 400
    try:
        try:
            doc = documento_mod.validar(cuerpo["documento"])
        except (TypeError, AttributeError):
            # un tipo que validar no espera (p. ej. "pistas": [1]) revienta al
            # recorrerlo: es un documento mal armado, no un error del servidor
            return jsonify({"error": gettext("El documento no tiene la forma esperada.")}), 400
        ajenos = _materiales_ajenos(cliente, doc)
        if ajenos:
            return jsonify({"error": gettext("La edición usa archivos que no son de este proyecto.")}), 400
        nuevo = ediciones.guardar(cliente, edicion_id, doc, cuerpo["version_n"])
    except DocumentoInvalido as e:
        # capa 4c: la persona lee una frase llana; la ruta del validador
        # («pistas[p_texto].clips[0]…») va aparte, para soporte (el editor la
        # pone en el `title` del estado del guardado)
        return jsonify({"error": idiomas.traducir(ERROR_GUARDAR), "detalle": str(e)}), 400
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
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    if not ed.get("cf_id"):
        return jsonify({"error": gettext("Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí.")}), 400
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("version_n"), int) \
            or isinstance(cuerpo.get("version_n"), bool) or not isinstance(cuerpo.get("destinos"), list) \
            or not all(isinstance(d, str) for d in cuerpo.get("destinos")):
        return jsonify({"error": gettext("Pedido inválido: se esperaba {version_n, destinos}.")}), 400
    # Chequeo rápido en memoria: un 409 inmediato sin tocar la base cuando la
    # versión ya se ve distinta a simple vista. No reemplaza el CAS de abajo
    # (fix round 1, Important): entre esta lectura y `ediciones.versionar` un
    # autoguardado de otra pestaña puede colarse, así que `versionar` vuelve a
    # comparar `version_n` dentro de la misma transacción que congela.
    if cuerpo["version_n"] != ed["version_n"]:
        return jsonify({"error": gettext("La edición cambió: espera a que termine de guardarse y vuelve a intentar.")}), 409
    doc = ed["documento"]
    validos = set(vista_previa.destinos(doc))
    destinos = cuerpo["destinos"]
    if not destinos or any(not _DESTINO_RE.match(d) or d not in validos for d in destinos):
        return jsonify({"error": gettext("Elige al menos un destino de esta edición.")}), 400
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
        return jsonify({"error": gettext("Hay textos sin traducir para algún destino."), "problemas": problemas}), 400
    if recortes:
        return jsonify({"error": gettext("Esta edición no se puede producir así:"), "problemas": recortes}), 400
    for d in destinos:
        idioma, pais = d.split("_")
        if trabajos.en_curso(tareas_fe.job_id_final(cliente, ed["cf_id"], idioma, pais)):
            return jsonify({"error": gettext("Esa final se está produciendo con voz; espera a que termine.")}), 409
    if cuerpo.get("reemplazar") is not True:
        reemplazos = []
        for d in destinos:
            final = creative_flow.final_por_legado(cliente, f"{ed['cf_id']}__{d}")
            if final and final.get("video_url") \
                    and ediciones.edicion_de_final(cliente, f"{ed['cf_id']}__{d}") != edicion_id:
                reemplazos.append(d)
        if reemplazos:
            error = (gettext("Ya hay una final de ese destino hecha por otro camino (puede tener voz); si produces, esta la reemplaza.")
                     if len(reemplazos) == 1 else
                     gettext("Ya hay finales de esos destinos hechas por otro camino (pueden tener voz); si produces, estas las reemplazan."))
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


# --- Subtítulos automáticos (editor capa 5a, Task 5): estimar y transcribir ---

def _materiales_propios_de(cliente, ids):
    """[material] de `ids` (en el mismo orden), o None si alguno no existe o
    no es de este proyecto, o no es video/audio (lo único que se transcribe)."""
    salida = []
    for mid in ids:
        if not isinstance(mid, int) or isinstance(mid, bool):
            return None
        mat = materiales.obtener(cliente, mid)
        if not mat or mat.get("tipo") not in ("video", "audio"):
            return None
        salida.append(mat)
    return salida


# Tope de ids de UN pedido, antes de tocar la base (revisión final): el panel
# manda todos los archivos de la fuente; los topes de `transcripcion`
# (20 archivos, 10 min) se aplican a lo que de verdad falta transcribir.
MAX_IDS_PEDIDO = 200


def _ids_unicos(ids):
    """Los ids de la lista, sin repetir y en el mismo orden (un id repetido no
    cuenta dos veces para los topes ni para el precio). Compara tipo y valor:
    `True` no es el id 1 (y sigue siendo inválido). Hasta MAX_IDS_PEDIDO."""
    salida = []
    for mid in ids:
        if not any(type(m) is type(mid) and m == mid for m in salida):
            salida.append(mid)
    return salida


def _sin_duracion(mat):
    """Sin `duracion_ms` (o 0: «desconocida», como en la vista previa) no hay
    precio: nunca se transcribe gratis ni se salta el tope de 10 min."""
    return not mat.get("duracion_ms")


@bp.post("/<int:edicion_id>/subtitulos/estimar", endpoint="subtitulos_estimar")
def subtitulos_estimar(cliente, edicion_id):
    """Precio de transcribir con Whisper lo que todavía falta de
    `material_ids` (D6): `gratis` cuando ya todos tienen palabras — no hay
    nada que cobrar ni que encolar. Si alguno de lo que falta no sabe cuánto
    dura, el precio no está disponible (`usd` None): el botón queda apagado."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": gettext("Elige qué transcribir.")}), 400
    ids = cuerpo.get("material_ids")
    ids = ids if isinstance(ids, list) else []
    if len(ids) > MAX_IDS_PEDIDO:
        return jsonify({"error": gettext("Son demasiados archivos en un solo pedido.")}), 400
    faltan, segundos, sin_duracion = [], 0.0, False
    for mid in _ids_unicos(ids):
        if not isinstance(mid, int) or isinstance(mid, bool):
            continue
        mat = materiales.obtener(cliente, mid)
        if mat and transcripcion.necesita(mat):
            faltan.append(mid)
            sin_duracion = sin_duracion or _sin_duracion(mat)
            segundos += (mat.get("duracion_ms") or 0) / 1000.0
    if not faltan:
        return jsonify({"faltan": [], "segundos": 0, "usd": 0, "precio": "", "gratis": True})
    estimado = gastos.estimar("transcripcion", segundos=segundos, sin_duracion=sin_duracion)
    return jsonify({"faltan": faltan, "segundos": None if sin_duracion else round(segundos, 1),
                    "usd": estimado["usd"], "precio": estimado["texto"], "gratis": False})


@bp.post("/<int:edicion_id>/subtitulos/transcribir", endpoint="transcribir")
def transcribir_subtitulos(cliente, edicion_id):
    """Encola `material_transcribir` con lo que de `material_ids` todavía no
    tiene palabras (spec §2.4): nada se paga sin pasar por aquí, y nada se
    transcribe dos veces. Límites: hasta `MAX_IDS_PEDIDO` ids en el pedido
    (antes de tocar la base) y un idioma de `audios.IDIOMAS`; de lo que FALTA
    transcribir, hasta `transcripcion.MAX_ARCHIVOS` archivos, todos con su
    duración conocida, y no más de `transcripcion.LIMITE_MS`."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    ids = cuerpo.get("material_ids")
    idioma = cuerpo.get("idioma")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": gettext("Elige qué transcribir.")}), 400
    if len(ids) > MAX_IDS_PEDIDO:
        return jsonify({"error": gettext("Son demasiados archivos en un solo pedido.")}), 400
    if idioma not in audios.IDIOMAS:
        return jsonify({"error": gettext("Ese idioma no está disponible.")}), 400
    materiales_ = _materiales_propios_de(cliente, _ids_unicos(ids))
    if materiales_ is None:
        return jsonify({"error": gettext("Ese archivo no es de este proyecto.")}), 404
    por_transcribir = [mat for mat in materiales_ if transcripcion.necesita(mat)]
    if len(por_transcribir) > transcripcion.MAX_ARCHIVOS:
        return jsonify({"error": gettext("Son demasiados archivos para una vez: hasta 20.")}), 400
    if any(_sin_duracion(mat) for mat in por_transcribir):
        aviso = gettext("Todavía no se sabe cuánto dura uno de los archivos: espera un momento y vuelve a intentarlo.")
        return jsonify({"error": aviso}), 400
    faltan = [mat["id"] for mat in por_transcribir]
    segundos = sum(mat["duracion_ms"] for mat in por_transcribir) / 1000.0
    if segundos * 1000 > transcripcion.LIMITE_MS:
        return jsonify({"error": gettext("Es demasiado audio para una sola vez: hasta 10 minutos.")}), 400
    if not faltan:
        return jsonify({"listo": True})
    job_id = tareas_edicion.job_id_transcribir(cliente, edicion_id)
    if trabajos.en_curso(job_id):
        return jsonify({"error": gettext("Ya se están generando subtítulos en esta edición: espera a que terminen.")}), 409
    trabajos.encolar(job_id, "material_transcribir",
                     {"cliente": cliente, "edicion_id": edicion_id, "material_ids": faltan, "idioma": idioma},
                     duracion_estimada=20 + int(segundos // 4), etapas=list(tareas_edicion.ETAPAS_TRANSCRIBIR),
                     cliente=cliente, max_intentos=1)
    return jsonify({"job_id": job_id}), 202


# --- Voz con IA y grabación (editor capa 5a, Task 6) ---

_CLAVE_VOZ_RE = re.compile(r"^[0-9a-f]{64}$")


def _tiene_palabras(mat):
    return isinstance((mat.get("extra") or {}).get("palabras"), list)


@bp.post("/<int:edicion_id>/voz/estimar", endpoint="voz_estimar")
def voz_estimar(cliente, edicion_id):
    """Precio de «Voz con IA» (D6/D9): la locución completa más sus
    subtítulos (Whisper), en un solo botón. `ya_existe` dice si esa voz
    exacta (mismo texto/voz/idioma/velocidad) ya está pagada y transcrita —
    el botón pasa a «(gratis)» y no encola nada."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    if not _cargar(cliente, edicion_id):
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": idiomas.traducir(audios.MENSAJES["texto"])}), 400
    voz, idioma, velocidad = cuerpo.get("voz"), cuerpo.get("idioma"), cuerpo.get("velocidad")
    if audios.es_propia(voz):
        return jsonify({"error": gettext("Esa voz no está disponible en el editor.")}), 400
    texto = cuerpo.get("texto")
    texto = " ".join(texto.split()) if isinstance(texto, str) else ""
    # Esa voz exacta ya existe: con sus palabras no se paga nada (el botón dice
    # «gratis»); sin ellas, solo Whisper sobre ella (revisión final).
    existente = None
    if (texto and isinstance(voz, str) and voz and isinstance(idioma, str)
            and isinstance(velocidad, str) and velocidad in audios.VELOCIDADES):
        existente = materiales.buscar_hash(cliente, audios.hash_voz(texto, voz, idioma, velocidad))
    ya_existe = bool(existente and _tiene_palabras(existente))
    solo_subtitulos = bool(existente) and not ya_existe
    estimado = gastos.estimar("voz_editor", caracteres=len(texto), solo_subtitulos=solo_subtitulos,
                              duracion_ms=existente.get("duracion_ms") if existente else None)
    return jsonify({"caracteres": len(texto), "usd": estimado["usd"], "precio": estimado["texto"],
                    "ya_existe": ya_existe, "solo_subtitulos": solo_subtitulos})


@bp.post("/<int:edicion_id>/voz", endpoint="voz")
def voz(cliente, edicion_id):
    """Crea (o reutiliza) una voz con IA (D9): si ya existe con sus palabras,
    la devuelve sin encolar nada (gratis); si no, encola `editor_voz`. Un
    segundo clic mientras esa edición ya está generando una voz es 409 — el
    `job_id` es uno por edición, nunca por texto."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    if not _cargar(cliente, edicion_id):
        return jsonify({"error": gettext("No existe esa edición.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    if audios.es_propia(cuerpo.get("voz")):
        # el editor solo ofrece la galería (las voces propias van por otro
        # motor y no tienen el caché de Crear › Audios que usa `editor_voz`)
        return jsonify({"error": gettext("Esa voz no está disponible en el editor.")}), 400
    try:
        payload = audios.validar(cliente, cuerpo)
    except audios.EntradaInvalida as e:
        return jsonify({"error": idiomas.traducir(str(e))}), 400
    texto, voz_, idioma, velocidad = payload["texto"], payload["voz"], payload["idioma"], payload["velocidad"]
    clave = audios.hash_voz(texto, voz_, idioma, velocidad)
    existente = materiales.buscar_hash(cliente, clave)
    if existente and _tiene_palabras(existente):
        materiales.marcar_uso([existente["id"]])
        return jsonify({"material": vista_previa.material_para(existente, con_palabras=True)})
    job_id = tareas_edicion.job_id_voz(cliente, edicion_id)
    if trabajos.en_curso(job_id):
        return jsonify({"error": gettext("Ya se está creando una voz en esta edición: espera a que termine.")}), 409
    trabajos.encolar(job_id, "editor_voz",
                     {"cliente": cliente, "edicion_id": edicion_id, "texto": texto, "voz": voz_, "idioma": idioma,
                      "velocidad": velocidad}, duracion_estimada=40, etapas=list(tareas_edicion.ETAPAS_VOZ),
                     cliente=cliente, max_intentos=1)
    return jsonify({"job_id": job_id, "clave": clave}), 202


@bp.get("/voz/<clave>", endpoint="voz_material")
def voz_material(cliente, clave):
    """La voz cruda (con sus palabras, si ya las tiene) por su `hash_voz`:
    lo que `editor_voz` pide el navegador cuando termina. No depende de
    ninguna edición en particular — la caché es por proyecto (D9)."""
    if not _CLAVE_VOZ_RE.fullmatch(clave or ""):
        return jsonify({"error": gettext("Esa voz ya no existe.")}), 404
    mat = materiales.buscar_hash(cliente, clave)
    if not mat or mat.get("origen") != audios.ORIGEN_VOZ:
        return jsonify({"error": gettext("Esa voz ya no existe.")}), 404
    return jsonify({"material": vista_previa.material_para(mat, con_palabras=True)})


@bp.post("/materiales/grabacion", endpoint="grabacion")
def grabacion(cliente):
    """Sube una grabación del micrófono (D8, gratis): el servidor la pasa a
    mp3 y la deja lista para el cabezal."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return jsonify({"error": gettext("Elige un archivo.")}), 400
    try:
        material = biblioteca.guardar_grabacion(cliente, archivo, hora=request.form.get("hora"))
    except biblioteca.SubidaInvalida as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"material": material})


@bp.post("/desde/<cf_id>")
def desde_clon(cliente, cf_id):
    """«Editar» (gratis): encola la preparación y vuelve a la pieza en Final
    edition, donde la barra muestra el avance. El `&abrir=editor` del destino
    es lo que le dice al script de la pestaña que, cuando la recarga
    automática de iniciarPolling() vea la edición lista, entre directo al
    editor en vez de quedarse en el detalle (Editor capa 4b, tarea 9)."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    entry = creative_flow.cargar(cliente).get(cf_id)
    volver = url_for("ver_cliente", cliente=cliente)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        flash(gettext("Esa pieza no tiene un video listo para editar."), "error")
        return redirect(volver + "#final")
    encolado = trabajos.encolar(tareas_edicion.job_id_desde_clon(cliente, cf_id), "edicion_desde_clon",
                                {"cliente": cliente, "cf_id": cf_id}, duracion_estimada=40,
                                etapas=[(idiomas.N_("Preparando el video"), 100)], cliente=cliente, max_intentos=2)
    flash(gettext("Preparando el video para el editor… se abre solo en cuanto esté listo.") if encolado
          else gettext("Ya se estaba preparando ese video."), "ok")
    return redirect(volver + f"#final?cf={cf_id}&abrir=editor")


# --- Biblioteca del editor (capa 4b, Task 1): subir, listar y preparar piezas ---

@bp.post("/materiales/subir", endpoint="subir")
def subir_material(cliente):
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return jsonify({"error": gettext("Elige un archivo.")}), 400
    try:
        material = biblioteca.subir(cliente, archivo)
    except biblioteca.SubidaInvalida as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"material": material})


@bp.post("/materiales/<material_id>/borrar", endpoint="borrar_material")
def borrar_material(cliente, material_id):
    """«Borrar» en la biblioteca (capa 4c, gratis): lo que la persona subió o
    un video de Crear preparado, solo si ninguna edición ni versión lo usa
    (409 con el nombre de la que lo usa). La decisión es de
    `biblioteca.borrar`; aquí solo se traduce a HTTP."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    if not str(material_id).isdigit():
        return jsonify({"error": gettext("Ese archivo ya no existe.")}), 404
    try:
        borrado = biblioteca.borrar(cliente, int(material_id))
    except biblioteca.NoSePuedeBorrar as e:
        return jsonify({"error": str(e)}), e.codigo
    except Exception:
        return jsonify({"error": gettext("No se pudo borrar el archivo. Vuelve a intentar.")}), 502
    return jsonify({"ok": True, "material_id": borrado["id"]})


@bp.get("/biblioteca", endpoint="biblioteca")
def ver_biblioteca(cliente):
    return jsonify(biblioteca.listar(cliente))


@bp.post("/biblioteca/pieza/<cf_id>", endpoint="agregar_pieza")
def agregar_pieza(cliente, cf_id):
    """Añade una pieza de Crear a la biblioteca (gratis): si ya es un
    material, lo devuelve tal cual; si no, encola su preparación
    (`material_de_pieza`) y responde 202 mientras tanto."""
    if not _mismo_origen():
        return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    if not tareas_edicion._CF_RE.fullmatch(cf_id or ""):
        return jsonify({"error": gettext("No existe esa pieza.")}), 404
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") != "video":
        return jsonify({"error": gettext("No existe esa pieza.")}), 404
    existente = biblioteca.material_de_pieza(cliente, cf_id)
    if existente:
        return jsonify({"material": vista_previa.material_para(existente)})
    trabajos.encolar(tareas_edicion.job_id_material_de_pieza(cliente, cf_id), "material_de_pieza",
                     {"cliente": cliente, "cf_id": cf_id}, duracion_estimada=30, cliente=cliente, max_intentos=2)
    return jsonify({"preparando": True}), 202


def _ids_de(texto):
    return [int(p.strip()) for p in (texto or "").split(",") if p.strip().isdigit()]


@bp.get("/materiales", endpoint="materiales_por_id")
def materiales_por_id(cliente):
    """`?ids=1,2,3` -> {materiales: {id: material_para(m)}} solo de este
    proyecto (un id ajeno o inexistente simplemente no aparece).

    `&preparar=1,2`: de esos ids (de este proyecto), encola lo que todavía
    falta — la copia liviana de un video, los picos de un audio (una canción
    de Mi música nunca los tuvo) — con la misma tarea gratis e idempotente que
    `ver` (`vista_previa.encolar_proxies`). La biblioteca lo pide UNA vez por
    material, al empezar a esperarlo; las preguntas siguientes solo leen (un
    archivo que falla no se vuelve a encolar cada 3 s).

    `&palabras=1` (capa 5a): manda también `palabras` de cada material (la
    pestaña Subtítulos las pide cuando una transcripción recién terminó, sin
    recargar toda la página)."""
    con_palabras = request.args.get("palabras") == "1"
    out = {}
    for mid in _ids_de(request.args.get("ids")):
        m = materiales.obtener(cliente, mid)
        if m:
            out[str(mid)] = vista_previa.material_para(m, con_palabras=con_palabras)
    preparar = {str(mid) for mid in _ids_de(request.args.get("preparar"))}
    if preparar:
        vista_previa.encolar_proxies(cliente, vista_previa.pendientes(
            {int(k): v for k, v in out.items() if k in preparar}))
    return jsonify({"materiales": out})
