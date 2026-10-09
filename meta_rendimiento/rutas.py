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

AISLAMIENTO (ruling R20, revisión final 2026-10-08): elegir cuentas (GET y POST) y cambiar el país son SOLO del admin
(403 al resto). El token de un proyecto puede ver cuentas de otros clientes, y quien las elige las lee: por eso lo
decide una persona de Creatv. Una cuenta con la que LANZA otro proyecto (`meta.json`) cuenta como «En otro proyecto»
igual que una que otro ya lee: no se lista habilitada ni se acepta.

En modo agencia el selector dice «Todavía no disponible» (spec §2.10). Ningún token llega a una respuesta: los
errores de Meta pasan por `cola.sin_token` y además se tacha el valor exacto del token."""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext, ngettext

import cola
import db
import idiomas
import meta_conexion
from idiomas import N_
from meta_rendimiento import cuentas, grafico, panel
from tareas import meta_rendimiento as tareas_mr
from triple_whale import paises

bp = Blueprint("meta_rendimiento", __name__, url_prefix="/cliente/<cliente>/meta-rendimiento")

# account_status de una cuenta publicitaria (Graph /me/adaccounts); otro código se muestra como «Otro estado».
ESTADOS_CUENTA = {1: N_("Activa"), 2: N_("Desactivada"), 3: N_("Con pagos pendientes"), 7: N_("En revisión de Meta"),
                  8: N_("Con pagos pendientes"), 9: N_("En período de gracia"), 100: N_("Por cerrarse"),
                  101: N_("Cerrada")}
OTRO_ESTADO = N_("Otro estado")
ESPERA_ACTUALIZAR = timedelta(minutes=30)      # entre dos «Actualizar ahora» de quien no es admin (ruling R22)


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
        pais = _pais(request.form.get(f"pais_{act}"))
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
    elif not es_admin() and _copiada_hace_poco(cliente, act):
        flash(gettext("Las métricas de Meta se acaban de actualizar: espera %(minutos)s minutos para volver a pedirlo.",
                      minutos=int(ESPERA_ACTUALIZAR.total_seconds() // 60)), "warn")
    elif tareas_mr.encolar_sync(cliente, act):
        flash(gettext("Trayendo las métricas de Meta…"), "ok")
    else:
        flash(gettext("Ya se están trayendo las métricas de Meta."), "warn")
    return _volver(cliente)
