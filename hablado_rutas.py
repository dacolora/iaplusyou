"""Rutas de Crear › Anuncio hablado (Blueprint `hablado`, prefijo
/cliente/<cliente>/hablado; spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md).
Solo traducen HTTP ⇄ `hablado.py`: el panel (fotos + voces, por fetch al abrir
el modo), subir una foto (gratis), la voz (cacheada o la tarea `hablado_voz`,
que paga una vez) y crear el video (sesión de Crear + `flowplus_lanzar.lanzar`).
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
<cliente>; aquí se rechazan los POST que el navegador marca de otro sitio."""
import os

from flask import Blueprint, get_template_attribute, jsonify, render_template, request, url_for
from flask_babel import gettext

import audios
import bitacora
import creative_flow
import flowplus_lanzar
import gastos
import hablado
import idiomas
import trabajos
import voces_propias
from cobros import libro
from final_edition import biblioteca
from providers import fal_audio
from tareas import hablado as tareas_hablado

bp = Blueprint("hablado", __name__, url_prefix="/cliente/<cliente>/hablado")


@bp.before_request
def _solo_mismo_origen():
    """Barrera CSRF (como Sprints, Nicho y Flow Plus): un POST que el navegador
    declara de otro sitio (Sec-Fetch-Site) no toca nada."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if request.method == "POST" and sitio and sitio not in ("same-origin", "none"):
        return jsonify({"ok": False, "error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    return None


def _con_miniaturas(cliente, fotos):
    """Los personajes del catálogo se muestran con la miniatura de 320 px que
    sirve la app (las fotos originales pesan MB; auditoría 2026-09-28)."""
    for f in fotos:
        if f["origen"] == "catalogo":
            f["miniatura"] = url_for("imagen_producto", cliente=cliente, producto_id=f["activo_id"],
                                     categoria="personaje", w=320)
    return fotos


@bp.route("/panel")
def panel(cliente):
    jid = tareas_hablado.job_id(cliente)
    return render_template(
        "_hablado_panel.html", cliente=cliente, fotos=_con_miniaturas(cliente, hablado.fotos(cliente)),
        fichas_voces=audios.fichas_voces(), voces_propias=voces_propias.listar(cliente),
        idiomas_audio=audios.IDIOMAS,
        nombres_idioma_audio=audios.NOMBRES_IDIOMA, velocidades_audio=audios.NOMBRES_VELOCIDAD,
        idioma_audio_defecto=audios.idioma_defecto(cliente), max_caracteres=hablado.MAX_CARACTERES,
        max_movimiento=hablado.MAX_MOVIMIENTO, usd_por_caracter=fal_audio.COSTO_USD_POR_CARACTER,
        trabajo_voz={"job_id": jid} if trabajos.en_curso(jid) else None)


@bp.route("/foto", methods=["POST"])
def foto(cliente):
    """Sube una foto (jpg/png/webp) como `material` imagen origen `subida`
    (gratis) y devuelve su tarjeta ya pintada."""
    archivo = request.files.get("foto")
    nombre = (archivo.filename or "") if archivo else ""
    if not nombre or os.path.splitext(nombre)[1].lower() not in hablado.EXTENSIONES_FOTO:
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["foto_tipo"])}), 400
    try:
        mat = biblioteca.subir(cliente, archivo)
    except biblioteca.SubidaInvalida as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — R2 o el disco: se dice en palabras, nada se cobró
        bitacora.registrar(cliente, nombre, "hablado", "foto_error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude subir la foto (%(tipo)s); intenta de nuevo.",
                                                      tipo=type(e).__name__)}), 502
    f = hablado.foto_de_material(mat)
    html = get_template_attribute("_hablado_macros.html", "tarjeta_foto")(f)
    return jsonify({"ok": True, "foto": f, "html": str(html)})


def _voz_para_ver(m):
    """`hablado.voz_info` con `precio_video` como lo ve la persona (cobros,
    spec 2026-10-08 §6: × el margen si el proyecto cobra). hablado.js lo
    pinta y lo devuelve tal cual como `precio_visto`; `_costo_visto` lo vuelve
    costo antes de compararlo o pedir saldo."""
    info = hablado.voz_info(m)
    if info["precio_video"] is not None:
        info["precio_video"] = round(info["precio_video"] * gastos.margen_vigente(), 6)
    return info


def _costo_visto(valor):
    """El `precio_visto` del navegador (precio, con margen) → el costo que
    compara `hablado.crear_pieza` y que pide `libro.exigir`; None si no es un
    número razonable. Con margen 1 (proyecto que no cobra) es el mismo valor."""
    return gastos.costo_de_precio(valor)


@bp.route("/voz", methods=["POST"])
def voz(cliente):
    """«Escuchar la voz»: si esa voz (mismo texto, voz, idioma y velocidad) ya
    existe en el proyecto responde enseguida, sin cobrar; si no, encola la
    tarea `hablado_voz` (paga una vez, max_intentos=1). Con `solo_cache=1` (la
    página lo manda cuando la tarea terminó) nunca encola nada."""
    try:
        p = hablado.validar_voz(cliente, request.form)
    except hablado.EntradaInvalida as e:
        return jsonify({"ok": False, "error": e.texto()}), 400
    m = hablado.voz_existente(cliente, audios.hash_voz(p["texto"], p["voz"], p["idioma"], p["velocidad"]))
    if m:
        return jsonify({"ok": True, "listo": True, "voz": _voz_para_ver(m)})
    if request.form.get("solo_cache") == "1":
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["voz_no_quedo"])}), 404
    jid = tareas_hablado.job_id(cliente)
    estado_url = url_for("estado_trabajo", job_id=jid)
    if not trabajos.encolar(jid, "hablado_voz", {"cliente": cliente, **p}, duracion_estimada=20,
                            etapas=list(tareas_hablado.ETAPAS), cliente=cliente, max_intentos=1,
                            costo_estimado=gastos.estimar("locucion", caracteres=len(p["texto"]))["usd"]):
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["en_curso"]), "job_id": jid,
                        "estado_url": estado_url}), 409
    return jsonify({"ok": True, "listo": False, "job_id": jid, "estado_url": estado_url})


@bp.route("/crear", methods=["POST"])
def crear(cliente):
    """«Generar video»: valida foto, voz y precio visto (hablado.crear_pieza:
    nada se crea si algo no cuadra), crea la sesión de Crear y la lanza con
    `flowplus_lanzar.lanzar` (prioridad 5, max_intentos=1)."""
    f = request.form
    # Cobros (spec 2026-10-08 §5): el precio que la persona vio se pide antes
    # de crear la sesión (crear_pieza comprueba que sea el real; si no, el
    # lanzamiento vuelve a pedir el real al encolar).
    # El navegador ve (y devuelve) el precio con margen: aquí vuelve a ser costo.
    visto = _costo_visto(f.get("precio_visto"))
    libro.exigir(cliente, visto)
    try:
        cf_id = hablado.crear_pieza(cliente, f.get("foto"), f.get("voz_hash"), f.get("movimiento"), visto)
    except hablado.PrecioCambio as e:
        return jsonify({"ok": False, "error": e.texto()}), 409
    except hablado.EntradaInvalida as e:
        return jsonify({"ok": False, "error": e.texto()}), 400
    entry = creative_flow.cargar(cliente)[cf_id]
    if not flowplus_lanzar.lanzar(cliente, cf_id, entry):
        return jsonify({"ok": False, "error": gettext("Ya se estaba generando eso — espera a que termine.")}), 409
    return jsonify({"ok": True, "cf_id": cf_id, "ir": "#referencias"})
