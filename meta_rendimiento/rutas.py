"""Blueprint de la pestaña «Meta» (spec 2026-10-08 meta rendimiento §5 y §8), bajo
`/cliente/<cliente>/meta-rendimiento`. `dashboard._guard_por_cliente` protege todo porque la URL lleva `<cliente>`;
cada POST además exige el mismo origen (Sec-Fetch-Site), la barrera CSRF del resto de la app.

- `panel`: el fragmento que la pestaña pide por fetch (solo lee la copia local: nunca Meta). `cuenta` = una cuenta del
  proyecto; ajena o inválida = «Todas».
- `anuncios` / `conjuntos`: «Ver más» por fetch; devuelven solo filas `<tr>` (y la fila del botón si quedan más).
- `cuentas` (GET): el selector «Elegir cuentas». Es la ÚNICA ruta que llama a Meta al abrirse
  (`meta_conexion.listar_activos`), y solo cuando la persona abre el selector.
- `cuentas` (POST): deja en el proyecto las cuentas marcadas. Una cuenta nueva solo entra si el token la ve
  (`listar_activos` otra vez: un id escrito a mano no sirve); una que ya estaba y sigue marcada se queda aunque el token
  ya no la vea. Encola la copia de las agregadas (gratis: leer de Meta no cobra). Tope: 20 cuentas por proyecto.
- `cuentas/<act>/pais`: cambia el país de una cuenta del proyecto (404 si es ajena, 400 si el código no es un país).
- `sincronizar`: «Actualizar ahora»; sin `act`, la copia de todas; con `act`, la de esa (ajena → 404). Quien no es
  admin espera 30 minutos desde la última copia (de esa cuenta o, sin `act`, de cualquiera del proyecto): el límite de
  Meta es por usuario y app, lo comparten todos los proyectos que usan el mismo token y un clic repetido lo agotaría
  (ruling R22, revisión final 2026-10-08). El admin no espera.
- `evaluar` (spec E2 §8): «Evaluar con IA», que COBRA. Cualquier persona del proyecto la puede pedir (paga su saldo,
  como en Triple Whale). Arma la muestra y los DATOS con el alcance pedido (`dias`, `cuenta`, como el panel), calcula
  el precio con `gastos.estimar("evaluacion_meta", n=)` y, si el formulario dice cuántos anuncios vio (`n`) y ya no
  son esos, no cobra y lo dice con el precio nuevo; pide saldo ANTES de crear la fila (`libro.exigir`) y la encola con
  `costo_estimado` (reserva). `SaldoInsuficiente` la responde el manejador único de dashboard (402 a un fetch, aviso a
  un formulario). Una viva por proyecto (`<cliente>__meta_eval`).
- `evaluacion/<id>` (GET): el fragmento de una evaluación (404 si es de otro proyecto).
- `evaluacion/<id>/idea/<i>/crear`: «Llevar a Crear» de una idea: deja el prefill con el origen «meta:<id>:<i>» y
  no genera nada (generar sigue siendo el botón de Crear con su precio).

AISLAMIENTO (ruling R20, revisión final 2026-10-08): elegir cuentas (GET y POST) y cambiar el país son SOLO del admin
(403 al resto). El token de un proyecto puede ver cuentas de otros clientes, y quien las elige las lee: por eso lo
decide una persona de Creatv. Una cuenta con la que LANZA otro proyecto (`meta.json`) cuenta como «En otro proyecto»
igual que una que otro ya lee: no se lista habilitada ni se acepta. Todo POST de la pestaña exige además correo
verificado (como las rutas que conectan Meta); el admin está exento.

En modo agencia el selector dice «Todavía no disponible» (spec §2.10). Ningún token llega a una respuesta: los
errores de Meta pasan por `cola.sin_token` y además se tacha el valor exacto del token."""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext, ngettext

import cola
import db
import gastos
import idiomas
import meta_conexion
import usuarios
from cobros import libro
from idiomas import N_
from meta_rendimiento import analisis, cuentas, datos, grafico, panel, pausa
from tareas import meta_rendimiento as tareas_mr
from triple_whale import paises, puente

bp = Blueprint("meta_rendimiento", __name__, url_prefix="/cliente/<cliente>/meta-rendimiento")

# account_status de una cuenta publicitaria (Graph /me/adaccounts); otro código se muestra como «Otro estado».
ESTADOS_CUENTA = {1: N_("Activa"), 2: N_("Desactivada"), 3: N_("Con pagos pendientes"), 7: N_("En revisión de Meta"),
                  8: N_("Con pagos pendientes"), 9: N_("En período de gracia"), 100: N_("Por cerrarse"),
                  101: N_("Cerrada")}
OTRO_ESTADO = N_("Otro estado")
ESPERA_ACTUALIZAR = timedelta(minutes=30)      # entre dos «Actualizar ahora» de quien no es admin (ruling R22)
ID_MAX = 2 ** 63 - 1     # el mayor entero de SQLite: un id más grande es 404, no un OverflowError (como Triple Whale)


@bp.before_request
def _mismo_origen():
    if request.method == "POST":
        sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sitio and sitio not in ("same-origin", "none"):
            abort(403)


def es_admin():
    """Mismo criterio que el resto de la app (`session["rol"] == "admin"`; así lo leen las plantillas y la ruta de
    descartar alertas). No se importa `dashboard` aquí: el Blueprint lo importa a él."""
    return session.get("rol") == "admin"


def solo_admin(fn):
    """403 (nada se escribe y nada se lista) a quien no es admin. Nunca solo ocultar el botón (skill `seguridad`)."""
    @wraps(fn)
    def envuelta(*args, **kwargs):
        if not es_admin():
            abort(403)
        return fn(*args, **kwargs)
    return envuelta


@bp.before_request
def _correo_verificado():
    """Sin correo verificado una persona con rol cliente no escribe nada aquí (como las rutas que conectan Meta o
    una tienda: `dashboard._requiere_correo_verificado`, que este Blueprint no puede importar). El admin pasa."""
    if request.method != "POST" or es_admin():
        return None
    entry = usuarios.obtener(session.get("usuario") or "")
    if entry and entry.get("correo_verificado"):
        return None
    flash(gettext("Confirma tu correo primero (Configuración › Cuenta)."), "error")
    return redirect(url_for("ver_cliente", cliente=request.view_args["cliente"], _anchor="settings"))


def _volver(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="meta"))


def _token(cliente):
    return (meta_conexion.cargar(cliente) or {}).get("token")


def _sin_token(e, token):
    """El motivo de un error de Meta en palabras y sin token: de `MetaConexionError` su texto (ya traducido); de
    cualquier otra excepción solo su tipo, porque su `str` puede traer la URL con el token."""
    texto = str(e) if isinstance(e, meta_conexion.MetaConexionError) else type(e).__name__
    if token:
        texto = texto.replace(token, "***")
    return cola.recortar(cola.sin_token(texto or type(e).__name__), 300)


def _agencia(cliente):
    return meta_conexion.modo(cliente) == meta_conexion.MODO_AGENCIA


def _pais(valor):
    """Código ISO-2 válido en mayúsculas, "" si no se eligió, o None si llegó algo que no es un país."""
    v = (valor or "").strip().upper()
    if not v:
        return ""
    return v if paises.es_pais(v) else None


# ------------------------------------------------------------------- lectura ---

@bp.get("/panel")
def ver_panel(cliente):
    ctx = panel.contexto(cliente, request.args.get("dias"), request.args.get("cuenta"))
    dibujo = grafico.armar(ctx["serie"]) if ctx.get("serie") else None
    return render_template("_meta_panel.html", cliente=cliente, mr=ctx, grafico=dibujo, es_admin=es_admin())


@bp.get("/anuncios")
def ver_anuncios(cliente):
    ctx = panel.anuncios_pagina(cliente, request.args.get("dias"), request.args.get("cuenta"),
                                request.args.get("pagina"))
    return render_template("_meta_anuncios_filas.html", cliente=cliente, mr=ctx)


@bp.get("/conjuntos")
def ver_conjuntos(cliente):
    ctx = panel.conjuntos_pagina(cliente, request.args.get("dias"), request.args.get("cuenta"),
                                 request.args.get("pagina"))
    return render_template("_meta_conjuntos_filas.html", cliente=cliente, mr=ctx)


# -------------------------------------------------------------- elegir cuentas ---

def _filas_selector(cliente, activos):
    """Las casillas del selector: las cuentas que ve el token (con su país guardado o adivinado y si están en otro
    proyecto) y, al final, las del proyecto que el token ya no ve."""
    propias = {c["ad_account_id"]: c for c in cuentas.listar(cliente)}
    dueno_de = {act: cli for cli, act in cuentas.todas()}
    lanzamiento = meta_conexion.cuentas_de_lanzamiento()
    filas, vistas = [], set()
    for a in activos:
        if not a.get("id"):
            continue
        act = cuentas.normalizar_id(a["id"])
        if act in vistas:
            continue
        vistas.add(act)
        propia = propias.get(act)
        estado = ESTADOS_CUENTA.get(a.get("account_status"), OTRO_ESTADO)
        # «En otro proyecto»: otro la lee o es la cuenta con la que LANZA otro proyecto (ruling R20).
        en_otro = dueno_de.get(act) not in (None, cliente) or lanzamiento.get(act) not in (None, cliente)
        filas.append({"id": act, "nombre": a.get("name") or act, "moneda": a.get("currency"), "estado": estado,
                      "elegida": bool(propia) and not en_otro, "en_otro": en_otro,
                      "pais": propia["pais"] if propia else cuentas.adivinar_pais(a.get("name")),
                      "no_visible": False})
    filas.sort(key=lambda f: (f["en_otro"], not f["elegida"], (f["nombre"] or "").lower(), f["id"]))
    for act, c in propias.items():
        if act not in vistas:
            filas.append({"id": act, "nombre": c.get("nombre") or act, "moneda": c.get("moneda"), "estado": None,
                          "elegida": True, "en_otro": False, "pais": c.get("pais"), "no_visible": True})
    return filas


@bp.get("/cuentas")
@solo_admin
def ver_cuentas(cliente):
    token = _token(cliente)
    ctx = {"conectado": bool(token), "agencia": False, "error": None, "filas": [], "paises": []}
    if token and _agencia(cliente):
        ctx["agencia"] = True
    elif token:
        try:
            activos = meta_conexion.listar_activos(token).get("ad_accounts") or []
        except Exception as e:  # noqa: BLE001 — Meta caída o token roto: se dice sin el token
            ctx["error"] = _sin_token(e, token)
        else:
            ctx["filas"] = _filas_selector(cliente, activos)
            ctx["paises"] = paises.paises_opciones(idiomas.activo())
    return render_template("_meta_cuentas.html", cliente=cliente, sel=ctx)


@bp.post("/cuentas")
@solo_admin
def guardar_cuentas(cliente):
    token = _token(cliente)
    if not token:
        flash(gettext("Meta no está conectado en este proyecto."), "error")
        return _volver(cliente)
    if _agencia(cliente):
        flash(gettext("Todavía no disponible en modo agencia."), "error")
        return _volver(cliente)
    try:
        activos = meta_conexion.listar_activos(token).get("ad_accounts") or []
    except Exception as e:  # noqa: BLE001
        flash(gettext("Meta no devolvió tus cuentas: %(error)s", error=_sin_token(e, token)), "error")
        return _volver(cliente)
    visibles = {cuentas.normalizar_id(a["id"]): a for a in activos if a.get("id")}
    propias = {c["ad_account_id"]: c for c in cuentas.listar(cliente)}
    lanzamiento = meta_conexion.cuentas_de_lanzamiento()
    existentes, nuevas, cambios_pais, ajenas = [], [], [], 0
    for valor in dict.fromkeys(request.form.getlist("cuenta")):
        act = cuentas.normalizar_id(valor)
        # Un campo que no llegó deja el país guardado; solo uno enviado vacío lo borra (y uno inválido no cambia nada).
        crudo = request.form.get(f"pais_{act}")
        pais = None if crudo is None else _pais(crudo)
        if lanzamiento.get(act) not in (None, cliente):
            ajenas += 1      # la cuenta con la que lanza otro proyecto no se lee desde este (ruling R20)
        elif act in propias:
            # Ya estaba: se queda aunque el token ya no la vea (quitarla borraría sus copias sin que nadie lo pidiera).
            c = propias[act]
            existentes.append({"id": act, "name": c.get("nombre"), "currency": c.get("moneda"), "pais": c.get("pais")})
            if pais is not None and (pais or None) != c.get("pais"):
                cambios_pais.append((act, pais or None))
        elif act in visibles:
            a = visibles[act]
            nuevas.append({"id": act, "name": a.get("name"), "currency": a.get("currency"), "pais": pais or None})
        # Lo que el token no ve y no estaba en el proyecto se ignora: nunca se agrega una cuenta escrita a mano.
    # Tope por proyecto: las que ya estaban van primero y las nuevas entran hasta llenar el cupo.
    cupo = max(0, cuentas.MAX_POR_PROYECTO - len(existentes))
    sobran = max(0, len(nuevas) - cupo)
    elegidas = existentes + nuevas[:cupo]
    antes = set(propias)
    try:
        r = cuentas.elegir(cliente, elegidas, usuario=session.get("usuario"))
    except Exception as e:  # noqa: BLE001 — borrar las copias de una quitada falló: esa cuenta sigue en el proyecto
        for act in sorted(set(cuentas.ids(cliente)) - antes):
            tareas_mr.encolar_sync(cliente, act)
        flash(gettext("No se pudo quitar una cuenta (%(tipo)s): sigue en el proyecto, inténtalo de nuevo.",
                      tipo=type(e).__name__), "error")
        return _volver(cliente)
    for act, pais in cambios_pais:
        cuentas.cambiar_pais(cliente, act, pais)
    for act in r["agregadas"]:
        tareas_mr.encolar_sync(cliente, act)
    mensajes = []
    if r["agregadas"]:
        mensajes.append(ngettext("%(num)s cuenta agregada: trayendo sus métricas…",
                                 "%(num)s cuentas agregadas: trayendo sus métricas…", len(r["agregadas"])))
    if r["quitadas"]:
        mensajes.append(ngettext("%(num)s cuenta quitada (se borraron sus métricas copiadas).",
                                 "%(num)s cuentas quitadas (se borraron sus métricas copiadas).", len(r["quitadas"])))
    ajenas += len(r["rechazadas"])
    if ajenas:
        mensajes.append(ngettext("%(num)s cuenta ya está en otro proyecto y no se agregó.",
                                 "%(num)s cuentas ya están en otro proyecto y no se agregaron.", ajenas))
    if sobran:
        mensajes.append(ngettext("Un proyecto lee como máximo %(tope)s cuentas: %(num)s cuenta no se agregó.",
                                 "Un proyecto lee como máximo %(tope)s cuentas: %(num)s cuentas no se agregaron.",
                                 sobran, tope=cuentas.MAX_POR_PROYECTO))
    if cambios_pais:
        mensajes.append(gettext("País actualizado."))
    flash(" ".join(mensajes) if mensajes else gettext("Sin cambios en las cuentas."),
          "warn" if ajenas or sobran else "ok")
    return _volver(cliente)


@bp.post("/cuentas/<act>/pais")
@solo_admin
def cambiar_pais(cliente, act):
    if not cuentas.cuenta(cliente, act):
        abort(404)
    pais = _pais(request.form.get("pais"))
    if pais is None:
        abort(400)
    cuentas.cambiar_pais(cliente, act, pais or None)
    flash(gettext("País actualizado."), "ok")
    return _volver(cliente)


# ------------------------------------------------------------- actualizar ahora ---

def _copiada_hace_poco(cliente, act):
    """True si la copia de la cuenta `act` (o, sin `act`, de alguna cuenta del proyecto) terminó hace menos de
    `ESPERA_ACTUALIZAR`. `ultima_copia` se guarda con `db.ahora()` (hora local, sin zona)."""
    ahora = datetime.fromisoformat(db.ahora())
    for c in cuentas.listar(cliente):
        if act and c["ad_account_id"] != cuentas.normalizar_id(act):
            continue
        try:
            copia = datetime.fromisoformat(str(c.get("ultima_copia"))[:19])
        except ValueError:
            continue         # sin copia (None) o una marca ilegible: no frena
        if ahora - copia < ESPERA_ACTUALIZAR:
            return True
    return False


@bp.post("/sincronizar")
def sincronizar(cliente):
    act = (request.form.get("act") or "").strip() or None
    if act and not cuentas.cuenta(cliente, act):
        abort(404)
    if not _token(cliente):
        flash(gettext("Meta no está conectado en este proyecto."), "error")
    elif not cuentas.ids(cliente):
        flash(gettext("Elige primero qué cuentas publicitarias quieres ver."), "warn")
    elif (hasta := pausa.pausada_hasta()):
        # Meta pidió esperar (ruling R22): una copia encolada ahora no correría; se dice la hora en vez de «Trayendo…».
        flash(gettext("Meta pidió esperar: la copia sigue a las %(hora)s.", hora=hasta[11:16]), "warn")
    elif not es_admin() and _copiada_hace_poco(cliente, act):
        flash(gettext("Las métricas de Meta se acaban de actualizar: espera %(minutos)s minutos para volver a pedirlo.",
                      minutos=int(ESPERA_ACTUALIZAR.total_seconds() // 60)), "warn")
    elif tareas_mr.encolar_sync(cliente, act):
        flash(gettext("Trayendo las métricas de Meta…"), "ok")
    else:
        flash(gettext("Ya se están trayendo las métricas de Meta."), "warn")
    return _volver(cliente)


# ------------------------------------------------------------- evaluar con IA ---

def _entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


@bp.post("/evaluar")
def evaluar(cliente):
    if not _token(cliente):
        flash(gettext("Meta no está conectado en este proyecto."), "error")
        return _volver(cliente)
    if tareas_mr.evaluacion_en_curso(cliente):
        flash(gettext("Ya hay una evaluación con IA en curso."), "warn")
        return _volver(cliente)
    prep = analisis.preparar(cliente, request.form.get("dias"), request.form.get("cuenta"))
    if prep is None:
        flash(gettext("Elige primero qué cuentas publicitarias quieres ver."), "warn")
        return _volver(cliente)
    n = len(prep["muestra"])
    if not n:
        flash(gettext("Todavía no hay anuncios con datos suficientes para evaluar con IA."), "error")
        return _volver(cliente)
    precio = gastos.estimar("evaluacion_meta", n=n)
    visto = request.form.get("n")
    if visto is not None and _entero(visto) != n:
        # Primero el precio, después el cobro: si la copia cambió la muestra desde que la persona vio el botón, el
        # precio es otro y no se cobra uno que no vio.
        flash(gettext("La muestra cambió desde que abriste la pestaña: ahora son %(n)s anuncio(s) por %(precio)s. "
                      "Revisa y vuelve a confirmar.", n=n, precio=precio["texto"]), "warn")
        return _volver(cliente)
    usd = precio["usd"]
    # Cobros: sin saldo no se crea la fila (el manejador único responde); la reserva la hace el encolado.
    libro.exigir(cliente, usd)
    eid = datos.crear_evaluacion(cliente, prep["cuentas"], prep["desde"], prep["hasta"], prep["moneda"],
                                 prep["muestra"], prep["recomendaciones"], pedido_por=session.get("usuario"),
                                 extra=prep["extra"])
    try:
        encolada = tareas_mr.encolar_evaluacion(cliente, eid, costo_estimado=usd)
    except Exception:          # SaldoInsuficiente incluida: la fila se borra y la excepción sigue su camino
        datos.borrar_evaluacion(cliente, eid)
        raise
    if not encolada:
        datos.borrar_evaluacion(cliente, eid)
        flash(gettext("Ya hay una evaluación con IA en curso."), "warn")
        return _volver(cliente)
    flash(gettext("Evaluando %(n)s anuncio(s) con IA…", n=n), "ok")
    return _volver(cliente)


@bp.get(f"/evaluacion/<int(max={ID_MAX}):eid>")
def ver_evaluacion(cliente, eid):
    fila = datos.evaluacion(cliente, eid)
    if not fila:
        abort(404)
    return render_template("_meta_evaluacion.html", cliente=cliente, ev=fila)


@bp.post(f"/evaluacion/<int(max={ID_MAX}):eid>/idea/<int(max=1000):indice>/crear")
def idea_crear(cliente, eid, indice):
    fila = datos.evaluacion(cliente, eid)
    if not fila or fila["estado"] != "lista":
        abort(404)
    ideas = (fila["resultado"] or {}).get("ideas") or []
    if not 0 <= indice < len(ideas):
        abort(404)
    try:
        session["fp_prefill"] = puente.prefill_crear(cliente, ideas[indice], origen=analisis.origen(eid, indice))
    except puente.PuenteError as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Idea cargada en Crear: ajusta lo que quieras y genera."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
