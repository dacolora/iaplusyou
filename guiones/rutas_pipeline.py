"""
Blueprint del pipeline de Flow Plus (spec 2026-09-25 §10): el panel de
guiones como fragmento HTML que arma el servidor (Jinja escapa todo) y las
acciones como POST JSON. Mismo prefijo y mismas reglas que guiones/rutas.py
(el chat): mismo origen en todo POST, cuerpo JSON obligatorio, errores en
español, 404 para lo de otro proyecto.
"""
from flask import Blueprint, jsonify, render_template, request

import gastos
import trabajos
from guiones import datos, lectura
from guiones.refinador import ErrorRefinador, NoExiste
from guiones.rutas import _cuerpo, _entero, _error, _sin_cuerpo, _solo_mismo_origen

bp = Blueprint("guiones_pipeline", __name__, url_prefix="/cliente/<cliente>/guiones")
bp.before_request(_solo_mismo_origen)


def _costo(paso, palabras=0):
    return gastos.estimar("guion_clips", paso=paso, palabras=palabras)["texto"]


def _contexto(cliente, guion_id=None, video_id=None):
    g = datos.guion(cliente, guion_id) if guion_id else None
    return {"cliente": cliente, "lotes": datos.lotes(cliente), "guion": g, "video": None,
            "costos": {"leer": _costo("leer", 750)}}


@bp.get("/panel")
def panel(cliente):
    ctx = _contexto(cliente, _entero(request.args.get("guion") or ""), _entero(request.args.get("video") or ""))
    return render_template("_gpg_panel.html", **ctx)


def _lanzar_lectura(lote_id):
    trabajos.iniciar(f"guion_leer_{lote_id}", lambda: lectura.leer_lote(lote_id), duracion_estimada=60)


@bp.post("/lotes")
def lote_crear(cliente):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        lote_id = datos.crear_lote(cliente, cuerpo.get("texto"))
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(lote_id)
    return jsonify({"lote_id": lote_id}), 202


@bp.post("/lotes/<int:lid>/reintentar")
def lote_reintentar(cliente, lid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.reintentar_lote(cliente, lid)
    except ErrorRefinador as e:
        return _error(e)
    _lanzar_lectura(lid)
    return jsonify({"lote_id": lid}), 202


def _guion_o_404(cliente, gid):
    g = datos.guion(cliente, gid)
    if g is None:
        raise NoExiste("Ese guion no existe.")
    return g


@bp.post("/guiones/<int:gid>/lectura")
def guion_lectura(cliente, gid):
    cuerpo = _cuerpo()
    if cuerpo is None:
        return _sin_cuerpo()
    try:
        g = _guion_o_404(cliente, gid)
        datos.guardar_lectura(cliente, gid, lectura.desde_formulario(cuerpo, g["lectura"], g["texto_crudo"]))
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": gid})


@bp.post("/guiones/<int:gid>/confirmar")
def guion_confirmar(cliente, gid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        datos.confirmar(cliente, gid)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": gid})


@bp.post("/guiones/<int:gid>/duplicar")
def guion_duplicar(cliente, gid):
    if _cuerpo() is None:
        return _sin_cuerpo()
    try:
        nuevo = datos.duplicar(cliente, gid)
    except ErrorRefinador as e:
        return _error(e)
    return jsonify({"guion_id": nuevo}), 201
