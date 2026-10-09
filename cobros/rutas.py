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
  Escriben a través de `libro.configurar`, `libro.guardar_margen_global` y
  `recargas.manual`, nunca directo en las tablas."""
import os
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
from cobros import bold, libro, pasarela, recargas, vista, wompi

bp = Blueprint("cobros", __name__)

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


def _verificar_si_toca(recarga, transaccion_id=None):
    """Pregunta a la pasarela si toca y hay cupo; si no, devuelve la recarga tal cual."""
    rid = recarga["id"]
    if not recargas.consultable(recarga, transaccion_id):   # pendiente, o rechazada/vencida de menos de 26 h
        return recarga
    with _CANDADO:
        if rid in _EN_CURSO:
            return recarga
    if not _toca_verificar(rid):
        return recarga
    if not _SEMAFORO.acquire(blocking=False):
        return recarga
    try:
        with _CANDADO:
            if rid in _EN_CURSO:
                return recarga
            _EN_CURSO.add(rid)
        try:
            tiempo = wompi.TIEMPO_INTERACTIVO if recarga.get("medio") == "wompi" else bold.TIEMPO_INTERACTIVO
            recargas.verificar(rid, tiempo=tiempo, transaccion_id=transaccion_id)
        finally:
            with _CANDADO:
                _EN_CURSO.discard(rid)
    finally:
        _SEMAFORO.release()
    return recargas.obtener(recarga["cliente"], rid)


def texto_estado(recarga, tx_id=None):
    """La frase de la página de vuelta (spec §9.4), en el idioma de quien mira.
    Una de Wompi pendiente sin transacción que consultar (volvió sin `?id=`,
    o cerró el checkout) no se queda en «Verificando…»: la acredita el evento."""
    estado = recarga["estado"]
    es_wompi = recarga.get("medio") == "wompi"
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
                           min_usd=recargas.MIN_USD, max_usd=recargas.MAX_USD, solo_filas=False)


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


@bp.get("/cliente/<cliente>/saldo/recarga/<int:rid>")
def recarga_vuelta(cliente, rid):
    """La vuelta del checkout. Bold: nunca acredita ni lee los parámetros que
    Bold agrega a la URL (bold-tx-status…); el estado lo da su servidor (el
    sondeo de /estado). Wompi vuelve con `?id=<transacción>`: se consulta esa
    transacción en Wompi (bajo el mismo cupo y la misma consulta en vuelo que
    el sondeo) y solo se acredita si su referencia, sus centavos y su moneda
    son los de la recarga y está APPROVED; el `id` sigue en el sondeo."""
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    if tx_id:
        recarga = _verificar_si_toca(recarga, tx_id)
    return render_template("saldo_recarga.html", cliente=cliente, recarga=recarga, texto=texto_estado(recarga, tx_id),
                           consultable=recargas.consultable(recarga, tx_id), tx_id=tx_id)


@bp.get("/cliente/<cliente>/saldo/recarga/<int:rid>/estado")
def recarga_estado(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    recarga = _verificar_si_toca(recarga, tx_id)
    return jsonify({"estado": recarga["estado"], "texto": texto_estado(recarga, tx_id),
                    "saldo_texto": gastos.formatear(libro.saldo(cliente) / 1000)})


@bp.post("/cliente/<cliente>/saldo/recarga/<int:rid>/verificar")
def recarga_verificar(cliente, rid):
    recarga = recargas.obtener(cliente, rid)
    if recarga is None:
        abort(404)
    tx_id = _id_vuelta() if recarga["medio"] == "wompi" else None
    recarga = _verificar_si_toca(recarga, tx_id)
    flash(texto_estado(recarga, tx_id), "ok" if recarga["estado"] in ("aprobada", "pendiente") else "error")
    return _volver(cliente)


@bp.post("/pagos/bold/webhook")
def bold_webhook():
    """Bold avisa un pago. Cuerpo crudo con tope de 64 KB (por Content-Length
    antes de leer y por lo leído después), firma verificada en recargas,
    respuesta sin cuerpo."""
    if (request.content_length or 0) > recargas.MAX_CUERPO:
        return "", 413
    cuerpo = request.get_data(cache=False, as_text=False)
    if len(cuerpo) > recargas.MAX_CUERPO:
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
    cuerpo = request.get_data(cache=False, as_text=False)
    if len(cuerpo) > recargas.MAX_CUERPO:
        return "", 413
    status, _resultado = recargas.procesar_evento_wompi(cuerpo, request.headers.get("X-Event-Checksum"))
    return "", status


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


@bp.get("/admin/cobros")
@_solo_admin
def admin_cobros():
    filas = vista.resumen_admin()
    for f in filas:
        f["nombre"] = proyectos.nombre_visible(f["cliente"])
        f["margen_propio_texto"] = _campo(f["margen_propio"]) if f["margen_propio"] is not None else ""
        f["umbral_texto"] = _campo(f["umbral"] / 1000)
    eventos = vista.ultimos_eventos()
    for e in eventos:
        e["resultado_texto"] = vista.nombre_resultado(e["resultado"])
    margen = libro.margen_global()
    return render_template("admin_cobros.html", filas=filas, margen_global=margen,
                           eventos=eventos, webhook_callado=vista.webhook_callado(), avisos_bold=_avisos_bold(),
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
