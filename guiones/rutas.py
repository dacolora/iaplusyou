"""
Blueprint JSON del chat de Flow Plus (prefijo /cliente/<cliente>/guiones):
crear y listar prompts, conversar con Claude para corregirlos, usar una
versión, editar a mano, aprobar y reabrir. Solo valida y traduce errores a
códigos HTTP; la lógica vive en `guiones.refinador`. `dashboard._guard_por_cliente`
protege estas rutas porque la URL lleva <cliente>.
"""
from flask import Blueprint, jsonify, request, session

import gastos
import trabajos
from guiones import refinador

bp = Blueprint("guiones", __name__, url_prefix="/cliente/<cliente>/guiones")

_ESTADO_HTTP = {refinador.DatoInvalido: 400, refinador.NoExiste: 404, refinador.Conflicto: 409,
                refinador.Incumple: 409}


def _mismo_origen():
    """Mismo criterio que `dashboard._mismo_origen`. No se importa de ahí
    porque con `python dashboard.py` ese módulo es __main__ y se cargaría dos veces."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


@bp.before_request
def _solo_mismo_origen():
    if request.method == "POST" and not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    return None


def _cuerpo():
    cuerpo = request.get_json(silent=True)
    return cuerpo if isinstance(cuerpo, dict) else None


def _sin_cuerpo():
    return jsonify({"error": "Cuerpo inválido: se esperaba un objeto JSON."}), 400


def _entero(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _error(e, incumple=409):
    cuerpo = {"error": str(e)}
    if e.problemas:
        cuerpo["problemas"] = e.problemas
    estado = incumple if isinstance(e, refinador.Incumple) else _ESTADO_HTTP.get(type(e), 409)
    return jsonify(cuerpo), estado


def _respuesta(detalle, estado=200):
    """{"prompt": <detalle>} más el hilo al día, para no obligar a otro GET."""
    mensajes = detalle.pop("mensajes", [])
    pendiente = detalle.pop("pendiente", False)
    return jsonify({"prompt": detalle, "mensajes": mensajes, "pendiente": pendiente}), estado


@bp.get("/prompts")
def prompts(cliente):
    return jsonify({"prompts": refinador.listar(cliente), "costo_mensaje": gastos.estimar("refinar_prompt")["texto"]})


@bp.post("/prompts")
def prompt_crear(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    texto_fijo = cuerpo.get("texto_fijo")
    if not isinstance(texto_fijo, (list, str)):
        texto_fijo = ()
    try:
        detalle = refinador.crear(cliente, cuerpo.get("texto"), titulo=str(cuerpo.get("titulo") or ""),
                                  tipo=cuerpo.get("tipo") or "libre", contexto=str(cuerpo.get("contexto") or ""),
                                  texto_fijo=texto_fijo)
    except refinador.ErrorRefinador as e:
        return _error(e)
    return _respuesta(detalle, 201)


@bp.get("/prompts/<int:pid>")
def prompt_ver(cliente, pid):
    detalle = refinador.obtener(cliente, pid)
    if detalle is None:
        return jsonify({"error": "Ese prompt no existe."}), 404
    return _respuesta(detalle)


@bp.post("/prompts/<int:pid>/mensajes")
def prompt_mensaje(cliente, pid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        mensaje_id = refinador.pedir_cambio(cliente, pid, cuerpo.get("mensaje"), usuario=session.get("usuario"))
    except refinador.ErrorRefinador as e:
        return _error(e)
    job_id = f"guion_refinar_{mensaje_id}"
    trabajos.iniciar(job_id, lambda: refinador.responder(mensaje_id), duracion_estimada=40)
    return jsonify({"mensaje_id": mensaje_id, "job_id": job_id}), 202


@bp.post("/prompts/<int:pid>/usar")
def prompt_usar(cliente, pid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    version_n = _entero(cuerpo.get("version_n"))
    mensaje_id = cuerpo.get("mensaje_id")
    if mensaje_id is not None:
        mensaje_id = _entero(mensaje_id)
        if mensaje_id is None:
            return jsonify({"error": "mensaje_id inválido."}), 400
    if version_n is None:
        return jsonify({"error": "Falta la versión del prompt (version_n)."}), 400
    try:
        return _respuesta(refinador.usar_version(cliente, pid, mensaje_id, version_n))
    except refinador.ErrorRefinador as e:
        return _error(e)


@bp.post("/prompts/<int:pid>/editar")
def prompt_editar(cliente, pid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    version_n = _entero(cuerpo.get("version_n"))
    if version_n is None:
        return jsonify({"error": "Falta la versión del prompt (version_n)."}), 400
    try:
        return _respuesta(refinador.editar(cliente, pid, cuerpo.get("texto"), version_n))
    except refinador.ErrorRefinador as e:
        return _error(e, incumple=422)


@bp.post("/prompts/<int:pid>/aprobar")
def prompt_aprobar(cliente, pid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    version_n = None
    if cuerpo.get("version_n") is not None:
        version_n = _entero(cuerpo.get("version_n"))
        if version_n is None:
            return jsonify({"error": "version_n inválido."}), 400
    try:
        return _respuesta(refinador.aprobar(cliente, pid, version_n=version_n))
    except refinador.ErrorRefinador as e:
        return _error(e)


@bp.post("/prompts/<int:pid>/reabrir")
def prompt_reabrir(cliente, pid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        return _respuesta(refinador.reabrir(cliente, pid))
    except refinador.ErrorRefinador as e:
        return _error(e)
