"""Rutas de las recargas del saldo (Blueprint `cobros`, spec 2026-10-08 §9 y
§11). Solo traducen HTTP ⇄ `cobros.recargas`.

- Las de /cliente/<cliente>/saldo/… las protegen los guards de la app: la
  sesión (`_verificar_sesion`), el proyecto de la URL (`_guard_por_cliente`) y
  la barrera CSRF (`_solo_mismo_origen`) en los POST.
- `POST /pagos/bold/webhook` es el ÚNICO POST de la app que acepta otro origen
  y no lleva sesión: dashboard lo exime por nombre de endpoint
  (`ENDPOINTS_OTRO_ORIGEN`, `ENDPOINTS_SIN_GUARD_SESION`). Lo protege la firma
  HMAC de Bold (`recargas.procesar_webhook`) y responde sin cuerpo."""
import threading
import time

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext

import cola
import cuentas
import gastos
import usuarios
from cobros import bold, libro, recargas

bp = Blueprint("cobros", __name__)

TOPE_RECARGAS_HORA = 10
ESPERA_VERIFICAR = 3        # segundos entre dos consultas a Bold por la misma recarga
_ULTIMA_VERIFICACION = {}   # recarga_id -> time.monotonic() de la última consulta (por proceso)
_CANDADO = threading.Lock()


def _volver(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente) + "#config-ap-saldo")


def _toca_verificar(recarga_id):
    """True como mucho una vez cada ESPERA_VERIFICAR s por recarga: la página de
    vuelta sondea cada 3 s y varias pestañas no deben multiplicar las consultas."""
    ahora = time.monotonic()
    with _CANDADO:
        ultima = _ULTIMA_VERIFICACION.get(recarga_id)
        if ultima is not None and ahora - ultima < ESPERA_VERIFICAR:
            return False
        if len(_ULTIMA_VERIFICACION) > 1000:
            for rid, t in list(_ULTIMA_VERIFICACION.items()):
                if ahora - t > 60:
                    del _ULTIMA_VERIFICACION[rid]
        _ULTIMA_VERIFICACION[recarga_id] = ahora
        return True


def _verificar_si_toca(recarga):
    if recarga["medio"] == "bold" and recarga["estado"] == "pendiente" and _toca_verificar(recarga["id"]):
        recargas.verificar(recarga["id"])
        return recargas.obtener(recarga["cliente"], recarga["id"])
    return recarga


def texto_estado(recarga):
    """La frase de la página de vuelta (spec §9.4), en el idioma de quien mira."""
    estado = recarga["estado"]
    if estado == "aprobada":
        return gettext("Listo: sumamos %(monto)s a tu saldo.", monto=gastos.formatear(recarga["milesimas"] / 1000))
    if estado == "rechazada":
        return gettext("Bold rechazó el pago. No se te cobró nada.")
    if estado == "expirada":
        return gettext("El link de pago venció sin pagarse.")
    if estado == "anulada":
        return gettext("Bold anuló este pago y lo descontamos de tu saldo.")
    return gettext("Verificando tu pago…")


@bp.post("/cliente/<cliente>/saldo/recargar")
def recargar(cliente):
    """Crea la recarga y manda a la persona al checkout de Bold. El monto lo
    valida el servidor; nada se acredita aquí."""
    if not (libro.cobra(cliente) or session.get("rol") == "admin"):
        flash(gettext("Este proyecto no usa saldo prepagado."), "error")
        return _volver(cliente)
    if not bold.configurado():
        flash(gettext("Las recargas en línea todavía no están disponibles; escríbenos para recargar."), "error")
        return _volver(cliente)
    if not cuentas.limite_ok(f"recarga:{cliente}", TOPE_RECARGAS_HORA, 3600):
        flash(gettext("Ya abriste muchas recargas en la última hora. Espera un rato o escríbenos."), "error")
        return _volver(cliente)
    usuario = session.get("usuario")
    cuenta = usuarios.obtener(usuario) or {}
    correo = (cuenta.get("correo") or "").strip() if cuenta.get("correo_verificado") else ""
    try:
        r = recargas.crear(cliente, request.form.get("usd", ""), usuario, correo=correo or None)
    except ValueError as e:
        flash(str(e), "error")
        return _volver(cliente)
    except bold.ErrorBold as e:
        flash(gettext("Bold no pudo abrir el pago: %(motivo)s. Intenta de nuevo en un rato.",
                      motivo=cola.sin_token(str(e))), "error")
        return _volver(cliente)
    return redirect(r["url"])   # checkout.bold.co (bold.crear_link lo comprueba)


@bp.get("/cliente/<cliente>/saldo/recarga/<int:rid>")
def recarga_vuelta(cliente, rid):
    """La vuelta del checkout. Nunca acredita, ni lee los parámetros que Bold
    agrega a la URL (bold-tx-status…): el estado lo da el servidor de Bold."""
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    return render_template("saldo_recarga.html", cliente=cliente, recarga=recarga, texto=texto_estado(recarga))


@bp.get("/cliente/<cliente>/saldo/recarga/<int:rid>/estado")
def recarga_estado(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    recarga = _verificar_si_toca(recarga)
    return jsonify({"estado": recarga["estado"], "texto": texto_estado(recarga),
                    "saldo_texto": gastos.formatear(libro.saldo(cliente) / 1000)})


@bp.post("/cliente/<cliente>/saldo/recarga/<int:rid>/verificar")
def recarga_verificar(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    recarga = _verificar_si_toca(recarga)
    flash(texto_estado(recarga), "ok" if recarga["estado"] in ("aprobada", "pendiente") else "error")
    return _volver(cliente)


@bp.post("/pagos/bold/webhook")
def bold_webhook():
    """Bold avisa un pago. Cuerpo crudo con tope de 64 KB (también si llega sin
    Content-Length), firma verificada en recargas, respuesta sin cuerpo."""
    if (request.content_length or 0) > recargas.MAX_CUERPO:
        return "", 413
    cuerpo = request.stream.read(recargas.MAX_CUERPO + 1)
    if len(cuerpo) > recargas.MAX_CUERPO:
        return "", 413
    status, _resultado = recargas.procesar_webhook(cuerpo, request.headers.get("x-bold-signature"))
    return "", status
