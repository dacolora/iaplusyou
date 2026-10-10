"""Rutas de las recargas del saldo (Blueprint `cobros`, spec 2026-10-08 §9 y
§11). Solo traducen HTTP ⇄ `cobros.recargas`.

- Las de /cliente/<cliente>/saldo/… las protegen los guards de la app: la
  sesión (`_verificar_sesion`), el proyecto de la URL (`_guard_por_cliente`) y
  la barrera CSRF (`_solo_mismo_origen`) en los POST.
- `POST /pagos/bold/webhook` y `POST /pagos/wompi/eventos` son los ÚNICOS POST
  de la app que aceptan otro origen y no llevan sesión: dashboard los exime por
  nombre de endpoint (`ENDPOINTS_OTRO_ORIGEN`, `ENDPOINTS_SIN_GUARD_SESION`).
  Los protege la firma de cada pasarela (`recargas.procesar_webhook`,
  `recargas.procesar_evento_wompi`) y responden sin cuerpo.
- Las de /admin/cobros (spec §10) son solo del admin (`_solo_admin`, la misma
  regla que `dashboard.requiere_admin`) y sus POST pasan por la barrera CSRF.
  Escriben a través de `libro.configurar`, `libro.guardar_margen_global`,
  `recargas.manual` y, los de planes y suscripciones (planes 7/8), `cobros.planes`,
  nunca directo en las tablas."""
import json
import logging
import os
import re
import threading
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps

import sqlalchemy as sa
from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext
from werkzeug.utils import secure_filename

import cola
import cuentas
import db
import gastos
import idiomas
import proyectos
import usuarios
from cobros import bold, libro, pasarela, planes, recargas, vista, wompi

bp = Blueprint("cobros", __name__)
log = logging.getLogger(__name__)

TOPE_RECARGAS_HORA = 10
ESPERA_VERIFICAR = 3        # segundos entre dos consultas a Bold por la misma recarga
_ULTIMA_VERIFICACION = {}   # recarga_id -> time.monotonic() de la última consulta (por proceso)
_CANDADO = threading.Lock()
# Con Bold colgado, cada sondeo de la página retendría un hilo de gunicorn: una
# sola consulta en vuelo por recarga y como mucho dos consultas de la web a la vez
# (sin esperar: si no hay cupo se responde el estado guardado), con espera corta
# (bold.TIEMPO_INTERACTIVO). La tarea periódica del worker usa la espera larga.
_EN_CURSO = set()
_SEMAFORO = threading.BoundedSemaphore(2)
# Los ids de las URL llevan `<int(max=9223372036854775807):…>` (el entero más grande de SQLite): uno más largo es
# 404, no un OverflowError (500) al consultarlo (revisión final 2026-10-10).


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


def _id_vuelta():
    """El `?id=` que agrega Wompi a la vuelta del checkout, solo si tiene forma
    de id de transacción (lo escribe quien sea: solo dice QUÉ consultar)."""
    valor = request.values.get("id")
    return valor if wompi.id_valido(valor) else None


_VISTO = {}   # (recarga_id, id de la vuelta) -> lo último que dijo Wompi de esa transacción (solo para mostrar)


def _verificar_si_toca(recarga, transaccion_id=None):
    """Pregunta a la pasarela si toca y hay cupo. Devuelve (recarga, visto).

    Con la transacción guardada (vino de un evento firmado de Wompi) o con Bold,
    `recargas.verificar` aplica lo que diga. El `?id=` de la vuelta de Wompi
    (lo escribe el navegador) solo se CONSULTA para mostrar cómo va
    (`recargas.consultar`, ruling 2026-10-10): `visto` es el status de Wompi de
    esa transacción si es de esta recarga, o None. Nunca acredita."""
    rid = recarga["id"]
    del_navegador = (recarga.get("medio") == "wompi" and bool(transaccion_id)
                     and transaccion_id != recarga.get("pasarela_ref"))
    clave = (rid, transaccion_id)
    visto = _VISTO.get(clave) if del_navegador else None
    if not recargas.consultable(recarga, transaccion_id):   # pendiente, o rechazada/vencida de menos de 26 h
        return recarga, visto
    with _CANDADO:
        if rid in _EN_CURSO:
            return recarga, visto
    if not _toca_verificar(rid):
        return recarga, visto
    if not _SEMAFORO.acquire(blocking=False):
        return recarga, visto
    try:
        with _CANDADO:
            if rid in _EN_CURSO:
                return recarga, visto
            _EN_CURSO.add(rid)
        try:
            tiempo = wompi.TIEMPO_INTERACTIVO if recarga.get("medio") == "wompi" else bold.TIEMPO_INTERACTIVO
            if del_navegador:
                visto = recargas.consultar(rid, transaccion_id, tiempo=tiempo) or visto
                with _CANDADO:
                    if len(_VISTO) > 1000:
                        _VISTO.clear()
                    _VISTO[clave] = visto
            else:
                recargas.verificar(rid, tiempo=tiempo)
        finally:
            with _CANDADO:
                _EN_CURSO.discard(rid)
    finally:
        _SEMAFORO.release()
    return recargas.obtener(recarga["cliente"], rid), visto


def texto_estado(recarga, tx_id=None, visto=None):
    """La frase de la página de vuelta (spec §9.4), en el idioma de quien mira.
    Una de Wompi pendiente sin transacción que consultar (volvió sin `?id=`,
    o cerró el checkout) no se queda en «Verificando…»: la acredita el evento.
    `visto`: lo que Wompi dijo de la transacción de la vuelta (solo se muestra:
    lo acredita el evento firmado, que llega en segundos)."""
    estado = recarga["estado"]
    es_wompi = recarga.get("medio") == "wompi"
    if es_wompi and estado in ("pendiente", "rechazada", "expirada"):
        if visto == "APPROVED":
            return gettext("Wompi aprobó tu pago. Lo sumamos a tu saldo apenas Wompi nos lo confirme; suele tardar "
                           "unos segundos.")
        if visto in ("DECLINED", "ERROR") and estado == "pendiente":
            return gettext("Wompi rechazó el pago. No se te cobró nada.")
    if es_wompi and estado == "pendiente" and not tx_id and not recarga.get("pasarela_ref"):
        return gettext("Si pagaste, lo acreditamos apenas Wompi lo confirme.")
    if estado == "aprobada":
        return gettext("Listo: sumamos %(monto)s a tu saldo.", monto=gastos.formatear(recarga["milesimas"] / 1000))
    if estado == "rechazada":
        if es_wompi:
            return gettext("Wompi rechazó el pago. No se te cobró nada.")
        return gettext("Bold rechazó el pago. No se te cobró nada.")
    if estado == "expirada":
        if es_wompi:
            return gettext("El pago no se completó a tiempo.")
        return gettext("El link de pago venció sin pagarse.")
    if estado == "anulada":
        if es_wompi:
            return gettext("Wompi anuló este pago y lo descontamos de tu saldo.")
        return gettext("Bold anuló este pago y lo descontamos de tu saldo.")
    return gettext("Verificando tu pago…")


def _puede_ver_saldo(cliente):
    """Configuración › Saldo: quien entra a un proyecto que cobra (el guard de
    la app ya decidió que entra) y el admin siempre. Lo demás, 404."""
    if session.get("rol") == "admin":
        return True
    return vista.cobra(cliente)


@bp.get("/cliente/<cliente>/saldo/panel")
def saldo_panel(cliente):
    """El fragmento del saldo que pide static/cobros.js al abrir el apartado
    (spec §7): saldo, recargar, movimientos (página 1) y recargas. Solo lee."""
    if not _puede_ver_saldo(cliente):
        abort(404)
    e = vista.estado(cliente, siempre=True)
    lista = recargas.de_proyecto(cliente)
    return render_template("_saldo_panel.html", cliente=cliente, e=e, tono=vista.tono(e),
                           movs=vista.movimientos(cliente), pagina=1, recargas=lista,
                           consultables={r["id"] for r in lista if recargas.consultable(r)},
                           estados_recarga=vista.ESTADOS_RECARGA, pasarela=pasarela.para_recargas(),
                           min_usd=recargas.MIN_USD, max_usd=recargas.MAX_USD, solo_filas=False,
                           bolsa=vista.bolsa_o_none(cliente) if e["cobrar"] else None)


@bp.get("/cliente/<cliente>/saldo/movimientos")
def saldo_movimientos(cliente):
    """«Ver más»: las filas (`<tr>`) de la página pedida, y al final una fila
    oculta con la URL de la siguiente si hay más."""
    if not _puede_ver_saldo(cliente):
        abort(404)
    pagina = max(1, request.args.get("pagina", 1, type=int) or 1)
    return render_template("_saldo_panel.html", cliente=cliente, movs=vista.movimientos(cliente, pagina=pagina),
                           pagina=pagina, solo_filas=True)


@bp.get("/cliente/<cliente>/saldo/movimientos.csv")
def saldo_movimientos_csv(cliente):
    """Todo el libro del proyecto en CSV (`;`, BOM), como el de gasto."""
    if not _puede_ver_saldo(cliente):
        abort(404)
    resp = Response(vista.csv_movimientos(cliente), content_type="text/csv; charset=utf-8")
    nombre = secure_filename(f"saldo_{cliente}_{db.ahora()[:10]}.csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@bp.post("/cliente/<cliente>/saldo/recargar")
def recargar(cliente):
    """Crea la recarga y manda a la persona al checkout de la pasarela (Wompi
    si tiene sus llaves, si no Bold). El monto lo valida el servidor; nada se
    acredita aquí."""
    if not (libro.cobra(cliente) or session.get("rol") == "admin"):
        flash(gettext("Este proyecto no usa saldo prepagado."), "error")
        return _volver(cliente)
    if pasarela.para_recargas() is None:
        flash(gettext("Las recargas en línea todavía no están disponibles; escríbenos para recargar."), "error")
        return _volver(cliente)
    try:
        usd = recargas.validar_usd(request.form.get("usd", ""))   # antes del tope: un monto mal escrito no lo gasta
    except ValueError as e:
        flash(str(e), "error")
        return _volver(cliente)
    if not cuentas.limite_ok(f"recarga:{cliente}", TOPE_RECARGAS_HORA, 3600):
        flash(gettext("Ya abriste muchas recargas en la última hora. Espera un rato o escríbenos."), "error")
        return _volver(cliente)
    usuario = session.get("usuario")
    cuenta = usuarios.obtener(usuario) or {}
    correo = (cuenta.get("correo") or "").strip() if cuenta.get("correo_verificado") else ""
    try:
        r = recargas.crear(cliente, usd, usuario, correo=correo or None)
    except ValueError as e:
        flash(str(e), "error")
        return _volver(cliente)
    except bold.ErrorBold as e:
        flash(gettext("Bold no pudo abrir el pago: %(motivo)s. Intenta de nuevo en un rato.",
                      motivo=cola.sin_token(str(e))), "error")
        return _volver(cliente)
    except wompi.ErrorWompi as e:
        flash(gettext("Wompi no pudo abrir el pago: %(motivo)s. Intenta de nuevo en un rato.",
                      motivo=cola.sin_token(str(e))), "error")
        return _volver(cliente)
    return redirect(r["url"])   # checkout.bold.co (bold.crear_link lo comprueba) o wompi.CHECKOUT


@bp.get("/cliente/<cliente>/saldo/recarga/<int(max=9223372036854775807):rid>")
def recarga_vuelta(cliente, rid):
    """La vuelta del checkout. Bold: nunca acredita ni lee los parámetros que
    Bold agrega a la URL (bold-tx-status…); el estado lo da su servidor (el
    sondeo de /estado). Wompi vuelve con `?id=<transacción>`: se consulta esa
    transacción en Wompi (bajo el mismo cupo y la misma consulta en vuelo que
    el sondeo) solo para MOSTRAR cómo va: lo acredita el evento firmado de
    Wompi (ruling 2026-10-10); el `id` sigue en el sondeo."""
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    visto = None
    if tx_id:
        recarga, visto = _verificar_si_toca(recarga, tx_id)
    return render_template("saldo_recarga.html", cliente=cliente, recarga=recarga,
                           texto=texto_estado(recarga, tx_id, visto),
                           consultable=recargas.consultable(recarga, tx_id), tx_id=tx_id)


@bp.get("/cliente/<cliente>/saldo/recarga/<int(max=9223372036854775807):rid>/estado")
def recarga_estado(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    recarga, visto = _verificar_si_toca(recarga, tx_id)
    return jsonify({"estado": recarga["estado"], "texto": texto_estado(recarga, tx_id, visto),
                    "saldo_texto": gastos.formatear(libro.saldo(cliente) / 1000)})


@bp.post("/cliente/<cliente>/saldo/recarga/<int(max=9223372036854775807):rid>/verificar")
def recarga_verificar(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    recarga, visto = _verificar_si_toca(recarga, tx_id)
    flash(texto_estado(recarga, tx_id, visto), "ok" if recarga["estado"] in ("aprobada", "pendiente") else "error")
    return _volver(cliente)


def _cuerpo_con_tope():
    """El cuerpo crudo leyendo como mucho MAX_CUERPO + 1 bytes del stream (revisión final 2026-10-10): con un
    envío por trozos (chunked) no hay Content-Length que mirar antes. None si pasa el tope."""
    cuerpo = request.stream.read(recargas.MAX_CUERPO + 1)
    return None if len(cuerpo) > recargas.MAX_CUERPO else cuerpo


@bp.post("/pagos/bold/webhook")
def bold_webhook():
    """Bold avisa un pago. Cuerpo crudo con tope de 64 KB (por Content-Length
    antes de leer y por lo leído después), firma verificada en recargas,
    respuesta sin cuerpo. Con un envío por trozos, el tope lo pone la lectura."""
    if (request.content_length or 0) > recargas.MAX_CUERPO:
        return "", 413
    cuerpo = _cuerpo_con_tope()
    if cuerpo is None:
        return "", 413
    status, _resultado = recargas.procesar_webhook(cuerpo, request.headers.get("x-bold-signature"))
    return "", status


@bp.post("/pagos/wompi/eventos")
def wompi_eventos():
    """Wompi avisa una transacción (spec planes §5.3). Cuerpo crudo con tope de
    64 KB (por Content-Length antes de leer y por lo leído después), firma de
    eventos verificada en recargas, respuesta sin cuerpo: exactamente 200 a
    todo evento firmado (Wompi reintenta cualquier otro código), 401 sin firma,
    400 cuerpo inválido, 413 demasiado grande."""
    if (request.content_length or 0) > recargas.MAX_CUERPO:
        return "", 413
    cuerpo = _cuerpo_con_tope()
    if cuerpo is None:
        return "", 413
    status, _resultado = recargas.procesar_evento_wompi(cuerpo, request.headers.get("X-Event-Checksum"))
    return "", status


# --------------------------------------------- Configuración › Plan (planes 6/8) ---
#
# Spec planes §5.2, §7 y §8. Las mismas puertas que el saldo: la sesión, el
# proyecto de la URL (`_guard_por_cliente`) y la barrera CSRF en los POST; además
# solo un proyecto que cobra o el admin (`_puede_ver_saldo`, si no 404). Nada se
# escribe aquí: `planes.suscribir`, `cambiar_fuente` y `cancelar`. La tarjeta la
# captura el widget de Wompi (su script solo se carga en plan_alta.html): el
# número nunca pasa por nuestra página ni por este servidor; llega un token.

TOPE_ALTAS_HORA = 10        # altas y cambios de tarjeta por proyecto y hora (cada uno crea una fuente en Wompi)
TOPE_NEQUI_HORA = 6         # pedidos a Nequi por proyecto y hora (cada uno manda una notificación al celular)
MAX_CAMPOS_FORMULARIO = 40
_TOKEN_TARJETA = re.compile(r"tok_(?:test|prod)_[A-Za-z0-9_-]{1,190}")
_SESION_NEQUI = "plan_nequi"   # los tokens de Nequi que pidió ESTA sesión (solo esos se sondean y se aceptan)


@bp.app_template_filter("fecha_larga")
def _filtro_fecha_larga(valor):
    """«15 de noviembre de 2026» de una fecha ISO guardada, en el idioma de quien mira; vacío si no se lee."""
    return vista.fecha_larga(valor) or ""


def _volver_plan(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente) + "#config-ap-plan")


def _exigir_plan(cliente):
    if not _puede_ver_saldo(cliente):
        abort(404)


def _sin_cobrar(cliente):
    """Suscribirse solo en un proyecto que cobra, también si lo pide el admin
    (mirar el apartado sí puede): sin «Cobrar», la bolsa del plan no se usaría
    y el plan se pagaría en vano. Devuelve la respuesta de vuelta, o None."""
    try:
        cobra = vista.cobra(cliente)
    except Exception:  # noqa: BLE001 — ante la duda, no se suscribe
        cobra = False
    if cobra:
        return None
    flash(gettext("Este proyecto todavía no cobra: prende «Cobrar» en el panel de cobros antes de suscribirlo a "
                  "un plan."), "error")
    return _volver_plan(cliente)


@bp.get("/cliente/<cliente>/plan/panel")
def plan_panel(cliente):
    """El fragmento de Configuración › Plan que pide static/planes.js al abrir
    el apartado: la página del proyecto no paga sus consultas. Si la lectura
    falla, «no se pudo cargar» (nunca una cifra a medias, nunca un costo)."""
    _exigir_plan(cliente)
    try:
        v = vista.plan_para_cliente(cliente)
    except Exception:  # noqa: BLE001 — falla cerrado
        log.exception("no se pudo armar el panel del plan de %s", cliente)
        return render_template("_plan_panel.html", cliente=cliente, v=None, error=True), 500
    return render_template("_plan_panel.html", cliente=cliente, v=v, error=False)


def _precio_ciclo(fila, ciclo):
    return fila.get("precio_anual_usd") if ciclo == "anual" else fila.get("precio_usd")


def _correo_sugerido(sus=None):
    if sus and sus.get("correo"):
        return sus["correo"]
    cuenta = usuarios.obtener(session.get("usuario")) or {}
    return (cuenta.get("correo") or "").strip() if cuenta.get("correo_verificado") else ""


def _formulario(cliente, modo, plan_, ciclo, precio_usd, sus=None):
    """plan_alta.html: el alta (`modo="alta"`) o el cambio de tarjeta
    (`"tarjeta"`; con la suscripción morosa, guardar COBRA en el acto y la
    página lo dice). Los contratos de Wompi salen de `wompi.aceptaciones_recientes`
    (caché de 10 min en kv, espera corta); sin Wompi, el aviso y ningún
    formulario. Del plan solo pasan id, nombre y precios."""
    llave = wompi.llave_publica()
    aceptaciones, problema = None, None
    if llave is None:
        problema = gettext("Los pagos con tarjeta no están disponibles ahora; escríbenos para activar tu plan")
    else:
        try:
            aceptaciones = wompi.aceptaciones_recientes()
        except wompi.ErrorWompi:
            problema = gettext("Wompi no responde en este momento. Intenta de nuevo en unos minutos.")
    plan_ = ({k: plan_.get(k) for k in ("id", "nombre", "precio_usd", "precio_anual_usd")} if plan_ else None)
    return render_template("plan_alta.html", cliente=cliente, modo=modo, plan=plan_, ciclo=ciclo,
                           morosa=bool(sus and sus.get("estado") == "morosa"),
                           precio_usd=precio_usd, precio_texto=vista.usd_entero(precio_usd) if precio_usd else None,
                           mensual_texto=vista.usd_entero(plan_["precio_usd"]) if plan_ else None,
                           anual_texto=(vista.usd_entero(plan_["precio_anual_usd"])
                                        if plan_ and plan_.get("precio_anual_usd") else None),
                           meses_gratis=vista.meses_gratis(plan_) if plan_ else 0,
                           llave_publica=llave, widget=wompi.WIDGET, aceptaciones=aceptaciones, problema=problema,
                           correo=_correo_sugerido(sus), tarjeta=(sus or {}).get("fuente_resumen"))


@bp.get("/cliente/<cliente>/plan/alta")
def plan_alta(cliente):
    """El formulario de alta de un plan (`?plan=<id>&ciclo=mensual|anual`):
    el precio del ciclo, el correo de cobro, las tres casillas y el medio de
    pago (el widget de Wompi para tarjeta, o Nequi)."""
    _exigir_plan(cliente)
    fuera = _sin_cobrar(cliente)
    if fuera is not None:
        return fuera
    plan_ = planes.leer_plan(request.args.get("plan"))
    if plan_ is None or not plan_["activo"]:
        flash(gettext("Ese plan no está disponible"), "error")
        return _volver_plan(cliente)
    if planes.suscripcion(cliente) is not None:
        flash(gettext("Este proyecto ya tiene un plan"), "error")
        return _volver_plan(cliente)
    ciclo = request.args.get("ciclo") if request.args.get("ciclo") in planes.CICLOS else "mensual"
    if not _precio_ciclo(plan_, ciclo):
        ciclo = "mensual"
    return _formulario(cliente, "alta", plan_, ciclo, _precio_ciclo(plan_, ciclo))


@bp.get("/cliente/<cliente>/plan/tarjeta")
def plan_tarjeta(cliente):
    """Cambiar la tarjeta (o pasar a Nequi) de un plan que se renueva solo:
    la casilla del cobro dice el precio ACEPTADO (el de la suscripción)."""
    _exigir_plan(cliente)
    sus = planes.suscripcion(cliente)
    if sus is None or sus["estado"] not in ("activa", "morosa") or not sus["renovar"]:
        flash(gettext("Este plan no se renueva con tarjeta: no hay tarjeta que cambiar."), "error")
        return _volver_plan(cliente)
    plan_ = planes.leer_plan(sus["plan_id"])
    return _formulario(cliente, "tarjeta", plan_, sus["ciclo"], _precio_ciclo(sus, sus["ciclo"]), sus=sus)


def _aceptacion(form):
    """Los dos tokens de Wompi (campos ocultos del formulario; Wompi los firma) y
    las tres casillas, cada una `True` solo si vino marcada con «1»."""
    return {"acceptance_token": (form.get("acceptance_token") or "").strip(),
            "personal_token": (form.get("personal_token") or "").strip(),
            **{c: form.get(c) == "1" for c in planes.CONSENTIMIENTOS},
            # Para la constancia (revisión final 2026-10-10): la ip ya pasó por ProxyFix; el navegador, recortado.
            "ip": (request.remote_addr or "")[:64], "user_agent": (request.headers.get("User-Agent") or "")[:300]}


def _token_en(valor):
    """Un token de tarjeta de Wompi (`tok_test_…`/`tok_prod_…`) en `valor`: el
    texto tal cual, o un JSON con ese `id`/`token` (también dentro de `data`)."""
    texto = str(valor or "").strip()
    if _TOKEN_TARJETA.fullmatch(texto):
        return texto
    if not texto.startswith("{") or len(texto) > 5000:
        return None
    try:
        d = json.loads(texto)
    except (ValueError, RecursionError):   # un JSON anidado sin fin no es un 500
        return None
    for bloque in (d, d.get("data") if isinstance(d, dict) else None):
        if isinstance(bloque, dict):
            for clave in ("id", "token"):
                v = bloque.get(clave)
                if isinstance(v, str) and _TOKEN_TARJETA.fullmatch(v.strip()):
                    return v.strip()
    return None


def _token_tarjeta(form):
    """El token que dejó el widget de Wompi en el formulario. Primero el campo
    `token`; si no, cualquier campo con forma de token de tarjeta (o un JSON con
    él): la doc de Wompi no dice con qué nombre lo pone el widget en tokenize
    (docs/pagos/wompi-api.md §13.1) y se confirma en sandbox. Wompi rechaza un
    token que no sea de nuestro comercio o ya usado."""
    campos = list(form.items(multi=True))[:MAX_CAMPOS_FORMULARIO]
    for _clave, valor in sorted(campos, key=lambda kv: kv[0] != "token"):
        token = _token_en(valor)
        if token:
            return token
    return None


def _medio(form):
    """(tipo, token): tarjeta con el token del widget, o Nequi con un token que
    pidió ESTA sesión (`plan_nequi`). Sin token válido, (tipo, None)."""
    tipo = (form.get("tipo") or "CARD").strip().upper()
    if tipo == "NEQUI":
        token = (form.get("token") or "").strip()
        return "NEQUI", token if token and token in (session.get(_SESION_NEQUI) or []) else None
    if tipo != "CARD":
        return tipo, None
    return "CARD", _token_tarjeta(form)


def _olvidar_nequi(token):
    lista = [t for t in (session.get(_SESION_NEQUI) or []) if t != token]
    session[_SESION_NEQUI] = lista


def _entero_exacto(texto):
    t = str(texto or "").strip()
    return int(t) if t.isdigit() and len(t) <= 9 else None


def _pedido_de_medio(cliente, volver):
    """Lo común del alta y del cambio de tarjeta: casillas, medio, correo y el
    tope por hora. Devuelve (aceptacion, tipo, token, correo) o una respuesta
    de vuelta al formulario con el aviso en palabras (sin hablar con Wompi)."""
    f = request.form
    aceptacion = _aceptacion(f)
    if not all(aceptacion[c] is True for c in planes.CONSENTIMIENTOS):
        flash(gettext("Para suscribirte tienes que aceptar los términos de Wompi, el tratamiento de datos "
                      "y el cobro automático"), "error")
        return volver
    tipo, token = _medio(f)
    if token is None:
        flash(gettext("No recibimos los datos de tu medio de pago. Vuelve a ingresar la tarjeta o a aprobar en "
                      "Nequi."), "error")
        return volver
    correo = wompi.correo_valido(f.get("correo"))
    if correo is None:
        flash(gettext("Escribe un correo válido para los recibos de Wompi."), "error")
        return volver
    if not cuentas.limite_ok(f"plan_alta:{cliente}", TOPE_ALTAS_HORA, 3600):
        flash(gettext("Ya intentaste muchas veces en la última hora. Espera un rato o escríbenos."), "error")
        return volver
    return aceptacion, tipo, token, correo


def _tras_cobro(cliente, estado, motivo, volver):
    """El aviso de lo que pasó con el cobro, en palabras (spec §5.2.4)."""
    if estado == "aprobado":
        flash(gettext("Listo: tu plan está activo y el saldo del plan ya está en tu cuenta."), "ok")
        return _volver_plan(cliente)
    if estado in ("rechazado", "error"):
        if motivo:
            flash(gettext("Wompi no aprobó el pago (%(motivo)s). No se activó el cobro; puedes intentar con otro "
                          "medio de pago.", motivo=cola.sin_token(str(motivo))[:200]), "error")
        else:
            flash(gettext("Wompi no aprobó el pago. No se activó el cobro; puedes intentar con otro medio de pago."),
                  "error")
        return volver
    if estado == "caida":
        flash(gettext("Wompi no respondió; lo intentamos de nuevo en unos minutos."), "warn")
        return _volver_plan(cliente)
    flash(gettext("Wompi está confirmando el pago. Te avisamos apenas llegue; mientras tanto puedes seguir usando "
                  "la app."), "warn")
    return _volver_plan(cliente)


@bp.post("/cliente/<cliente>/plan/alta")
def plan_suscribir(cliente):
    """El alta (spec §5.2): con las tres casillas marcadas, el token del medio
    de pago y el precio que la persona vio (`precio_visto_usd`, dólares
    enteros); `planes.suscribir` se niega sin hablar con Wompi si falta algo o
    si el precio cambió, crea la fuente y cobra el primer periodo."""
    _exigir_plan(cliente)
    fuera = _sin_cobrar(cliente)
    if fuera is not None:
        return fuera
    plan_id, ciclo = request.form.get("plan_id"), request.form.get("ciclo") or "mensual"
    volver = redirect(url_for("cobros.plan_alta", cliente=cliente, plan=plan_id, ciclo=ciclo))
    pedido = _pedido_de_medio(cliente, volver)
    if not isinstance(pedido, tuple):
        return pedido
    aceptacion, tipo, token, correo = pedido
    try:
        r = planes.suscribir(cliente, plan_id, ciclo, tipo, token, correo, aceptacion, session.get("usuario"),
                             _entero_exacto(request.form.get("precio_visto_usd")))
    except planes.ErrorPlan as e:
        flash(cola.sin_token(str(e)), "error")
        return volver
    if tipo == "NEQUI":
        _olvidar_nequi(token)
    return _tras_cobro(cliente, r["estado"], r.get("motivo"), volver)


@bp.post("/cliente/<cliente>/plan/tarjeta")
def plan_cambiar_tarjeta(cliente):
    """§7.5: otro medio de pago reemplaza al guardado (nunca prende la
    renovación); si el plan estaba moroso, cobra en el acto."""
    _exigir_plan(cliente)
    volver = redirect(url_for("cobros.plan_tarjeta", cliente=cliente))
    pedido = _pedido_de_medio(cliente, volver)
    if not isinstance(pedido, tuple):
        return pedido
    aceptacion, tipo, token, correo = pedido
    try:
        r = planes.cambiar_fuente(cliente, tipo, token, correo, aceptacion, session.get("usuario"))
    except planes.ErrorPlan as e:
        flash(cola.sin_token(str(e)), "error")
        return volver
    if tipo == "NEQUI":
        _olvidar_nequi(token)
    if r.get("cobro") is None:
        flash(gettext("Listo: guardamos tu nuevo medio de pago para los próximos cobros del plan."), "ok")
        return _volver_plan(cliente)
    motivo = vista.motivo_ultimo_pago(cliente) if r["cobro"] in ("rechazado", "error") else None
    return _tras_cobro(cliente, r["cobro"], motivo, volver)


@bp.post("/cliente/<cliente>/plan/cancelar")
def plan_cancelar(cliente):
    """§7.4: no se renueva más; lo pagado sigue hasta su fin y no se devuelve.
    El formulario trae `confirmo=1` (la frase se lee antes del botón)."""
    _exigir_plan(cliente)
    if request.form.get("confirmo") != "1":
        flash(gettext("Para cancelar, confirma con el botón «Sí, cancelar el plan»."), "error")
        return _volver_plan(cliente)
    try:
        r = planes.cancelar(cliente, session.get("usuario"))
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_plan(cliente)
    fecha = vista.fecha_larga(r.get("termina_el"))
    if r["estado"] == "terminada" or not fecha:
        flash(gettext("Cancelaste el plan. No se vuelve a cobrar."), "ok")
    else:
        flash(gettext("Cancelaste el plan: sigue hasta el %(fecha)s y no se vuelve a cobrar.", fecha=fecha), "ok")
    return _volver_plan(cliente)


@bp.get("/cliente/<cliente>/plan/pago/<int(max=9223372036854775807):pago_id>/estado")
def plan_pago_estado(cliente, pago_id):
    """El sondeo del panel mientras Wompi confirma un cobro: el estado guardado
    y, como mucho una vez cada 3 s por pago y con cupo, una consulta corta a
    Wompi (`planes.verificar_pago`)."""
    _exigir_plan(cliente)
    estado = vista.estado_pago_plan(cliente, pago_id)
    if estado is None:
        abort(404)
    if estado == "pendiente" and _toca_verificar(f"plan:{pago_id}") and _SEMAFORO.acquire(blocking=False):
        try:
            estado = planes.verificar_pago(cliente, pago_id) or estado
        except Exception:  # noqa: BLE001 — el sondeo informa; la periódica y el evento resuelven
            log.warning("no se pudo verificar el pago de plan %s", pago_id, exc_info=True)
        finally:
            _SEMAFORO.release()
    return jsonify({"estado": estado})


@bp.post("/cliente/<cliente>/plan/nequi")
def plan_nequi(cliente):
    """Pide a Wompi un token de Nequi para el celular escrito: la persona
    acepta la suscripción en su app y la página sondea su estado."""
    _exigir_plan(cliente)
    celular = re.sub(r"[\s-]", "", str(request.form.get("celular")
                                        or (request.get_json(silent=True) or {}).get("celular") or ""))
    if not wompi._CELULAR.fullmatch(celular):
        return jsonify({"ok": False, "error": gettext("El celular de Nequi debe tener 10 dígitos y empezar por 3")}), 400
    if not cuentas.limite_ok(f"plan_nequi:{cliente}", TOPE_NEQUI_HORA, 3600):
        return jsonify({"ok": False, "error": gettext("Ya pediste muchas veces a Nequi en la última hora. "
                                                      "Espera un rato.")}), 429
    try:
        token = wompi.token_nequi(celular, tiempo=wompi.TIEMPO_INTERACTIVO)
    except wompi.ErrorWompi as e:
        return jsonify({"ok": False, "error": cola.sin_token(str(e))}), 502
    session[_SESION_NEQUI] = ([t for t in (session.get(_SESION_NEQUI) or []) if t != token] + [token])[-5:]
    return jsonify({"ok": True, "token": token,
                    "estado_url": url_for("cobros.plan_nequi_estado", cliente=cliente, token=token)})


@bp.get("/cliente/<cliente>/plan/nequi/<token>/estado")
def plan_nequi_estado(cliente, token):
    """PENDING, APPROVED o DECLINED de un token de Nequi que pidió esta sesión
    (como mucho una consulta cada 3 s por token y con cupo; si no, PENDING)."""
    _exigir_plan(cliente)
    if token not in (session.get(_SESION_NEQUI) or []):
        abort(404)
    estado = "PENDING"
    if _toca_verificar(f"nequi:{token}") and _SEMAFORO.acquire(blocking=False):
        try:
            estado = wompi.estado_token_nequi(token)
        except wompi.ErrorWompi:
            estado = "PENDING"
        finally:
            _SEMAFORO.release()
    return jsonify({"estado": estado if estado in ("PENDING", "APPROVED", "DECLINED") else "PENDING"})


# ------------------------------------------------------------ /admin/cobros ---

MAX_UMBRAL_USD = 100_000


def _solo_admin(fn):
    """La regla de `dashboard.requiere_admin` (no se importa dashboard desde un
    Blueprint): sin sesión de admin, al login con el mismo aviso."""
    @wraps(fn)
    def envuelta(*args, **kwargs):
        if "usuario" not in session or session.get("rol") != "admin":
            flash(gettext("Esa página es solo para el administrador."), "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return envuelta


def _volver_admin(cliente=None):
    return redirect(url_for("cobros.admin_cobros") + (f"#fila-{cliente}" if cliente else ""))


def _proyectos_admin():
    import estado  # noqa: PLC0415 — el mismo origen que el panel (dashboard.panel)
    return set(estado.listar_clientes())


def _existe(cliente):
    """Un proyecto del panel o con cuenta de saldo; si no, 404 (un error de
    tipeo en la URL no crea una cuenta nueva)."""
    return cliente in _proyectos_admin() or _tiene_cuenta(cliente)


def _tiene_cuenta(cliente):
    with db.conectar() as con:
        return con.execute(sa.select(db.cuenta_saldo.c.cliente)
                           .where(db.cuenta_saldo.c.cliente == cliente)).first() is not None


def _decimal(texto):
    try:
        valor = Decimal(str(texto or "").strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return valor if valor.is_finite() else None


def _margen(texto):
    """El margen tal como se guardará: redondeado a 2 decimales (como
    `libro._validar_margen`) ANTES de mirar el rango, para que el aviso diga lo
    que quedó guardado y no lo que se escribió."""
    valor = _decimal(texto)
    # Un valor enorme («1e30») desborda la precisión de `quantize` con
    # InvalidOperation (no es un ValueError → 500): primero se descarta lo
    # que está lejos del rango, después se redondea lo cercano.
    if valor is not None and abs(valor) <= libro.MARGEN_MAX * 2:
        try:
            valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            valor = None
    elif valor is not None:
        valor = None
    if valor is None or not libro.MARGEN_MIN <= valor <= libro.MARGEN_MAX:
        raise ValueError(gettext("El margen va de %(min)s a %(max)s.", min=idiomas.numero(libro.MARGEN_MIN, 2),
                                 max=idiomas.numero(libro.MARGEN_MAX, 2)))
    return float(valor)


def _umbral(texto):
    """Dólares con hasta 2 decimales, de 0 a MAX_UMBRAL_USD → milésimas."""
    valor = _decimal(texto)
    if valor is None or valor < 0 or valor > MAX_UMBRAL_USD or valor != valor.quantize(Decimal("0.01")):
        raise ValueError(gettext("El umbral va de %(min)s a %(max)s, con hasta 2 decimales.",
                                 min=gastos.formatear(0), max=gastos.formatear(MAX_UMBRAL_USD)))
    return int(valor * 1000)


def _campo(valor, decimales=2):
    """Un número para un `<input>`: con el separador decimal de quien mira y sin
    miles (el parser acepta coma y punto, pero no «1.500,00»)."""
    separador = idiomas.numero(1.5, 1)[1]
    return f"{float(valor):.{decimales}f}".replace(".", separador)


def _avisos_bold():
    """Lo que el admin tiene que saber de la configuración de Bold, sin
    mostrar ningún valor de llave."""
    sin_secreta = not (os.environ.get("BOLD_LLAVE_SECRETA") or "").strip()
    sin_llaves = not bold.configurado() or sin_secreta
    pruebas_abiertas = bold.pruebas_activas() and sin_secreta
    return {"sin_llaves": sin_llaves, "pruebas_abiertas": pruebas_abiertas,
            "pruebas_fuera_de_local": bold.pruebas_fuera_de_local()}


def _avisos_wompi():
    """Lo que el admin tiene que saber de Wompi (planes 7/8), sin ningún valor
    de llave: sin llaves o mal puestas, llaves de pruebas en un servidor que no
    es local, o en modo de pruebas (local)."""
    fuera = wompi.pruebas_fuera_de_local()
    problema = None if fuera else wompi.problema()
    return {"problema": problema, "pruebas_fuera_de_local": fuera,
            "sandbox": problema is None and not fuera and wompi.pruebas()}


@bp.get("/admin/cobros")
@_solo_admin
def admin_cobros():
    filas = vista.resumen_admin()
    datos_planes = vista.planes_admin()
    margen = libro.margen_global()
    for f in filas:
        f["nombre"] = proyectos.nombre_visible(f["cliente"])
        f["margen_propio_texto"] = _campo(f["margen_propio"]) if f["margen_propio"] is not None else ""
        f["umbral_texto"] = _campo(f["umbral"] / 1000)
        f["margen_plan_texto"] = idiomas.numero(f["margen_plan"], 2) if f["margen_plan"] is not None else None
        f["plan"] = datos_planes["por_cliente"].get(f["cliente"]) or {"suscripcion": None, "periodo": None,
                                                                        "pendientes": []}
        sus = f["plan"]["suscripcion"]
        if sus is not None:
            sus["precio_aceptado_texto"] = (vista.usd_entero(sus["precio_aceptado_usd"])
                                            if sus["precio_aceptado_usd"] else None)
    for pl in datos_planes["planes"]:
        pl["precio_texto"] = vista.usd_entero(pl["precio_usd"])
        pl["anual_texto"] = vista.usd_entero(pl["precio_anual_usd"]) if pl["precio_anual_usd"] else None
        pl["margen_texto"] = idiomas.numero(pl["margen"], 2)
        pl["margen_campo"] = _campo(pl["margen"])
        pl["tope_campo"] = _campo(pl["tope_incluido_usd"])
        pl["descuento_pct"] = vista.descuento_miembro(pl["margen"], margen)
    eventos = vista.ultimos_eventos()
    for e in eventos:
        e["resultado_texto"] = vista.nombre_resultado(e["resultado"])
        e["proveedor_texto"] = vista.nombre_proveedor(e["proveedor"])
        e["monto_texto"] = vista.monto_evento(e)
        e["usd_texto"] = vista.usd_evento(e)
    return render_template("admin_cobros.html", filas=filas, margen_global=margen, planes=datos_planes["planes"],
                           eventos=eventos, webhook_callado=vista.webhook_callado(), avisos_bold=_avisos_bold(),
                           avisos_wompi=_avisos_wompi(),
                           margen_global_texto=idiomas.numero(margen, 2), margen_global_campo=_campo(margen),
                           margen_min_texto=idiomas.numero(libro.MARGEN_MIN, 2),
                           margen_max_texto=idiomas.numero(libro.MARGEN_MAX, 2))


@bp.post("/admin/cobros/margen")
@_solo_admin
def admin_margen():
    try:
        valor = _margen(request.form.get("margen"))
        libro.guardar_margen_global(valor, session.get("usuario"))
    except ValueError as e:
        flash(str(e), "error")
        return _volver_admin()
    flash(gettext("Margen global guardado: %(margen)s.", margen=idiomas.numero(valor, 2)), "ok")
    return _volver_admin()


@bp.post("/admin/cobros/<cliente>/cuenta")
@_solo_admin
def admin_cuenta(cliente):
    """Solo cambia lo que trae el formulario: `cobrar` (1|0, el interruptor),
    `margen` (vacío = vuelve al global) y `umbral` (en dólares)."""
    if not _existe(cliente):
        abort(404)
    cambios = {}
    try:
        if "cobrar" in request.form:
            cambios["cobrar"] = request.form.get("cobrar") == "1"
        if "margen" in request.form:
            texto = (request.form.get("margen") or "").strip()
            cambios["margen"] = _margen(texto) if texto else None
        if "umbral" in request.form:
            cambios["umbral"] = _umbral(request.form.get("umbral"))
        if cambios:
            libro.configurar(cliente, usuario=session.get("usuario"), **cambios)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_admin(cliente)
    nombre = proyectos.nombre_visible(cliente)
    if "cobrar" in cambios:
        if cambios["cobrar"]:
            flash(gettext("%(proyecto)s ahora cobra lo que genera.", proyecto=nombre), "ok")
            if libro.disponible(cliente) <= 0:
                flash(gettext("Este proyecto no tiene saldo: desde ahora no podrá generar nada que cueste "
                              "hasta que recargue."), "warn")
        else:
            flash(gettext("%(proyecto)s dejó de cobrar: genera sin tocar el saldo.", proyecto=nombre), "ok")
            if planes.apagar_renovacion(cliente, session.get("usuario")):
                flash(gettext("Su plan ya no se renueva solo: no cobraremos la tarjeta. Para volver a la "
                              "renovación automática, el proyecto tiene que suscribirse de nuevo."), "warn")
    elif cambios:
        flash(gettext("Guardado: margen y umbral de %(proyecto)s.", proyecto=nombre), "ok")
    return _volver_admin(cliente)


@bp.post("/admin/cobros/<cliente>/recarga")
@_solo_admin
def admin_recarga(cliente):
    """Recarga manual (una transferencia, un pago por fuera) o ajuste (±,
    con nota). A un proyecto que no cobra se le puede dejar saldo, y se avisa."""
    if not _existe(cliente):
        abort(404)
    tipo = request.form.get("tipo") or "recarga"
    try:
        recargas.manual(cliente, request.form.get("monto", ""), session.get("usuario"), request.form.get("nota", ""),
                        tipo=tipo)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_admin(cliente)
    nombre = proyectos.nombre_visible(cliente)
    monto = gastos.formatear(float(_decimal(request.form.get("monto")) or 0))
    if tipo == "ajuste":
        flash(gettext("Ajuste de %(monto)s anotado en %(proyecto)s.", monto=monto, proyecto=nombre), "ok")
    else:
        flash(gettext("Listo: sumamos %(monto)s al saldo de %(proyecto)s.", monto=monto, proyecto=nombre), "ok")
    if not libro.cobra(cliente):
        flash(gettext("%(proyecto)s todavía no cobra: el saldo queda guardado para cuando prendas «Cobrar».",
                      proyecto=nombre), "warn")
    return _volver_admin(cliente)


# ------------------------------------------- /admin/cobros: planes (planes 7/8) ---
# Spec planes §9. Escriben a través de `cobros.planes` (escritor único de plan, suscripcion, periodo_plan y
# pago_plan); los POST pasan por la barrera CSRF de la app como todo /admin/cobros.

def _volver_planes(ancla="cobros-planes"):
    return redirect(url_for("cobros.admin_cobros") + f"#{ancla}")


def _volver_suscripcion(cliente):
    return redirect(url_for("cobros.admin_cobros") + f"#suscripcion-{cliente}")


def _numero_form(nombre):
    """El campo tal como lo escribió el admin, con coma o punto decimal (sin miles)."""
    return (request.form.get(nombre) or "").strip().replace(",", ".")


def _campos_plan():
    return {"nombre": request.form.get("nombre") or "", "precio_usd": _numero_form("precio_usd"),
            "precio_anual_usd": _numero_form("precio_anual_usd") or None, "margen": _numero_form("margen"),
            "tope_incluido_usd": _numero_form("tope_incluido_usd"), "orden": _numero_form("orden") or 0}


@bp.post("/admin/cobros/planes")
@_solo_admin
def admin_plan_crear():
    """Un plan nuevo. Nace archivado si no se marca «Ofrecerlo»: así se revisa antes de que lo vean los clientes."""
    try:
        planes.crear_plan(**_campos_plan(), activo=request.form.get("activo") == "1", usuario=session.get("usuario"))
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_planes()
    flash(gettext("Plan creado: %(plan)s.", plan=(request.form.get("nombre") or "").strip()), "ok")
    return _volver_planes()


@bp.post("/admin/cobros/planes/<int(max=9223372036854775807):plan_id>")
@_solo_admin
def admin_plan_editar(plan_id):
    """Cambia nombre, precios, margen, tope y orden. El precio nuevo solo vale para suscripciones nuevas (cada
    suscripción renueva al precio que aceptó); margen y tope, desde el próximo periodo."""
    try:
        planes.editar_plan(plan_id, usuario=session.get("usuario"), **_campos_plan())
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_planes(f"plan-{plan_id}")
    flash(gettext("Plan guardado. Quien ya está suscrito sigue con el precio que aceptó; el margen y el tope "
                  "valen desde su próximo periodo (en un plan anual, desde su próximo pago)."), "ok")
    return _volver_planes(f"plan-{plan_id}")


@bp.post("/admin/cobros/planes/<int(max=9223372036854775807):plan_id>/activo")
@_solo_admin
def admin_plan_activo(plan_id):
    """Ofrecer (activo=1) o archivar (activo=0): archivado no se ofrece; las suscripciones siguen."""
    activo = request.form.get("activo") == "1"
    try:
        planes.archivar_plan(plan_id, session.get("usuario"), activo=activo)
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_planes()
    if activo:
        flash(gettext("El plan ya se ofrece a los proyectos que cobran."), "ok")
    else:
        flash(gettext("Plan archivado: ya no se ofrece. Las suscripciones que tiene siguen igual."), "ok")
    return _volver_planes(f"plan-{plan_id}")


def _exigir_proyecto(cliente):
    if not _existe(cliente):
        abort(404)
    return proyectos.nombre_visible(cliente)


@bp.post("/admin/cobros/<cliente>/plan/activar")
@_solo_admin
def admin_plan_activar(cliente):
    """«Activar a mano» (§7.7): un pago por transferencia abre un periodo pagado con el precio de hoy del plan
    y ciclo elegidos. Apaga siempre la renovación automática con tarjeta (la pantalla lo dice)."""
    nombre = _exigir_proyecto(cliente)
    if not libro.cobra(cliente):
        flash(gettext("%(proyecto)s no cobra: prende «Cobrar» antes de activarle un plan.", proyecto=nombre), "error")
        return _volver_suscripcion(cliente)
    ciclo = request.form.get("ciclo") or ""
    try:
        r = planes.activar_manual(cliente, request.form.get("plan_id"), ciclo, session.get("usuario"),
                                  nota=" ".join((request.form.get("nota") or "").split())[:300])
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_suscripcion(cliente)
    if r.get("periodo_id"):
        flash(gettext("Plan de %(proyecto)s activado a mano: el periodo quedó abierto y su saldo acreditado.",
                      proyecto=nombre), "ok")
    else:
        flash(gettext("Pago a mano anotado en %(proyecto)s: extiende lo pagado y su periodo se abre cuando "
                      "termine el actual.", proyecto=nombre), "ok")
    return _volver_suscripcion(cliente)


@bp.post("/admin/cobros/<cliente>/plan/cancelar")
@_solo_admin
def admin_plan_cancelar(cliente):
    """Como el cliente (§7.4): no se renueva más y sigue hasta el fin de lo pagado, sin devolución."""
    nombre = _exigir_proyecto(cliente)
    if request.form.get("confirmo") != "1":
        flash(gettext("Marca la casilla para confirmar que quieres cancelar el plan."), "error")
        return _volver_suscripcion(cliente)
    try:
        r = planes.cancelar(cliente, session.get("usuario"))
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_suscripcion(cliente)
    fecha = vista.fecha_larga(r.get("termina_el"))
    if r.get("estado") == "terminada" or not fecha:
        flash(gettext("Plan de %(proyecto)s cancelado y terminado: no tenía nada pagado vigente.", proyecto=nombre),
              "ok")
    else:
        flash(gettext("Plan de %(proyecto)s cancelado: no se renueva y sigue hasta el %(fecha)s.", proyecto=nombre,
                      fecha=fecha), "ok")
    return _volver_suscripcion(cliente)


@bp.post("/admin/cobros/<cliente>/plan/terminar")
@_solo_admin
def admin_plan_terminar(cliente):
    """«Terminar ya» (§9): corta el plan ahora, sin devolución; vence la bolsa. Nota obligatoria."""
    nombre = _exigir_proyecto(cliente)
    nota = " ".join((request.form.get("nota") or "").split())[:300]
    if not nota:
        flash(gettext("Escribe una nota con el motivo para terminar el plan ya."), "error")
        return _volver_suscripcion(cliente)
    if request.form.get("confirmo") != "1":
        flash(gettext("Marca la casilla para confirmar que quieres terminar el plan ya."), "error")
        return _volver_suscripcion(cliente)
    try:
        planes.terminar_ya(cliente, session.get("usuario"), nota=nota)
    except planes.ErrorPlan as e:
        flash(str(e), "error")
        return _volver_suscripcion(cliente)
    flash(gettext("Plan de %(proyecto)s terminado: el saldo del plan que quedaba venció y desde ahora genera a la "
                  "carta.", proyecto=nombre), "ok")
    return _volver_suscripcion(cliente)


_RESUELTO = {
    "aprobado": idiomas.N_("Wompi confirmó el cobro: el pago quedó aprobado y el plan, al día."),
    "rechazado": idiomas.N_("Wompi dice que ese cobro se rechazó: quedó como rechazado."),
    "error": idiomas.N_("Quedó como no cobrado."),
    "pendiente": idiomas.N_("Wompi todavía no resuelve esa transacción: guardamos su id y se aplica cuando responda."),
    "no_cuadra": idiomas.N_("El monto o la moneda de esa transacción no cuadran con este pago: no se aplicó nada."),
    "aprobado_sin_suscripcion": idiomas.N_("Wompi lo aprobó, pero la suscripción ya terminó: no se acreditó nada. "
                                   "Devuélvelo en Wompi o activa el plan a mano."),
    "ya_aplicada": idiomas.N_("Ese pago ya estaba resuelto: no cambió nada."),
    "aprobado_tras_final": idiomas.N_("Wompi dice que ese cobro se aprobó, pero el pago ya estaba cerrado (rechazado, "
                                      "con error o anulado): no se acreditó nada. Míralo en el panel de Wompi y "
                                      "devuélvelo si se cobró de más."),
}


@bp.post("/admin/cobros/<cliente>/plan/pago/<int(max=9223372036854775807):pago_id>/resolver")
@_solo_admin
def admin_plan_resolver(cliente, pago_id):
    """Resolver a mano un pago de plan pendiente (`planes.resolver_pendiente`): «Sí se cobró» relee la
    transacción en Wompi y aplica lo que diga; «No se cobró» (con nota) lo da por fallido. Nunca se acredita
    sin que Wompi lo confirme."""
    _exigir_proyecto(cliente)
    resultado = request.form.get("resultado")
    if resultado not in ("cobrado", "no_cobrado"):
        flash(gettext("Elige si el cobro se hizo o no."), "error")
        return _volver_suscripcion(cliente)
    try:
        r = planes.resolver_pendiente(cliente, pago_id, resultado == "cobrado", session.get("usuario"),
                                      transaccion_id=request.form.get("transaccion_id"),
                                      nota=request.form.get("nota") or "")
    except planes.ErrorPlan as e:
        flash(cola.sin_token(str(e)), "error")
        return _volver_suscripcion(cliente)
    mensaje = _RESUELTO.get(r)
    flash(gettext(mensaje) if mensaje else gettext("Resultado: %(resultado)s.", resultado=r),
          "ok" if r in ("aprobado", "error", "pendiente") else "warn")
    return _volver_suscripcion(cliente)
