"""Blueprint de la pestaña «Rendimiento» (spec 2026-10-09 §4–§5, A5), bajo `/cliente/<cliente>/rendimiento`.
`dashboard._guard_por_cliente` protege todo porque la URL lleva `<cliente>`; cada POST además exige el mismo origen
(Sec-Fetch-Site, la barrera CSRF del resto de la app) y correo verificado (el admin está exento), como las rutas de
Triple Whale y de Meta.

- `panel` (GET): el fragmento que la pestaña pide por fetch (solo lee la copia local). `entrada` = la clave de una
  entrada del selector; vacía, ajena o rara = «Todas». `tienda`/`cuenta` son los parámetros de las pestañas viejas.
- `conjuntos` (GET): «Ver más» de la tabla de conjuntos; devuelve solo filas `<tr>`.
- `anuncios-meta` (GET): «Ver más» de los anuncios cuya fuente es Meta; devuelve solo tarjetas.
- `actualizar` (POST): «Actualizar ahora» encola las copias de Triple Whale y de Meta del alcance (una `entrada` que
  no existe no encola nada: solo la vacía es «Todas») con sus `job_id` de siempre y las reglas de cada una (`triple_whale.rutas.pedir_copia`, `meta_rendimiento.rutas.pedir_copia`: la
  pausa compartida de Meta y la espera de 30 minutos de quien no es admin). Leer no cobra.

Las rutas que cobran («Cómo mejorarlo», «Analizar los N», «Evaluar con IA») siguen en `triple_whale/rutas.py` (R13):
esta pestaña solo les pasa el alcance de Triple Whale de la entrada."""
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext

import usuarios
from meta_rendimiento import rutas as meta_rutas
from pestana_rendimiento import panel
from triple_whale import rutas as tw_rutas

bp = Blueprint("rendimiento", __name__, url_prefix="/cliente/<cliente>/rendimiento")


@bp.before_request
def _mismo_origen():
    if request.method == "POST":
        sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sitio and sitio not in ("same-origin", "none"):
            abort(403)


@bp.before_request
def _correo_verificado():
    """Sin correo verificado una persona con rol cliente no pide copias desde aquí (el mismo criterio que
    `meta_rendimiento.rutas._correo_verificado`; este Blueprint no puede importar `dashboard`). El admin pasa."""
    if request.method != "POST" or meta_rutas.es_admin():
        return None
    entry = usuarios.obtener(session.get("usuario") or "")
    if entry and entry.get("correo_verificado"):
        return None
    flash(gettext("Confirma tu correo primero (Configuración › Cuenta)."), "error")
    return redirect(url_for("ver_cliente", cliente=request.view_args["cliente"], _anchor="settings"))


def _volver(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="rendimiento"))


def _entero(valor):
    """Un número de la URL (periodo, página): entero, o 0 si llega otra cosa."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _texto(nombre):
    return (request.args.get(nombre) or "").strip()


@bp.get("/panel")
def ver_panel(cliente):
    ctx = panel.contexto(cliente, _entero(request.args.get("dias")), entrada=_texto("entrada"),
                         canal=_texto("canal") or None, tienda=_texto("tienda") or None,
                         cuenta=_texto("cuenta") or None)
    tw = ctx["tw"]
    if tw and tw.get("resultados"):
        tienda = tw["tienda_actual"]["id"] if tw.get("tienda_actual") else ""
        tw["resultados"]["datos"]["url_dia"] = url_for("triple_whale.ver_dia", cliente=cliente, tienda=tienda,
                                                       canal=ctx["canal"] or "")
    return render_template("_rend_panel.html", cliente=cliente, r=ctx, es_admin=meta_rutas.es_admin())


@bp.get("/conjuntos")
def ver_conjuntos(cliente):
    ctx = panel.conjuntos_pagina(cliente, _entero(request.args.get("dias")), _texto("entrada"),
                                 _entero(request.args.get("pagina")))
    return render_template("_meta_conjuntos_filas.html", cliente=cliente, mr=ctx)


@bp.get("/anuncios-meta")
def ver_anuncios_meta(cliente):
    ctx = panel.anuncios_meta_pagina(cliente, _entero(request.args.get("dias")), _texto("entrada"),
                                     _entero(request.args.get("pagina")))
    return render_template("_rend_anuncios_meta.html", cliente=cliente, r=ctx)


@bp.post("/actualizar")
def actualizar(cliente):
    """«Actualizar ahora»: las copias de la entrada del formulario. Triple Whale: la tienda de la entrada, o todas
    (`None`) en «Todas». Meta: cada cuenta del alcance, o todas (`None`) cuando el alcance las tiene todas; en
    «Todas» sin cuentas elegidas, `pedir_copia` dice que falta elegirlas. Cada mensaje distinto se dice una vez.
    «Todas» es solo la entrada vacía: una entrada que no existe no encola nada y pide recargar."""
    valor = (request.form.get("entrada") or "").strip()
    s = panel.alcance_para_copias(cliente, valor)
    alc = s["alcance"]
    if not s["tw_cfg"] and not s["meta_ok"]:
        flash(gettext("Conecta Triple Whale o Meta para ver tu rendimiento."), "warn")
        return _volver(cliente)
    # Solo una `entrada` VACÍA es «Todas». Una que ya no es la clave de ninguna entrada (una pestaña vieja, un país que
    # se quitó, la de otro proyecto) no encola nada: ensanchada a «Todas» copiaría todas las cuentas y gastaría el
    # límite de uso de Meta por usuario y app, el mismo que necesitan los lanzamientos (revisión de la tarea 8, R22).
    if valor and (s["actual"] is None or s["actual"]["clave"] != valor):
        flash(gettext("Esa vista ya no existe: recarga la pestaña."), "warn")
        return _volver(cliente)
    mensajes = []
    if s["tw_cfg"] and alc["tw"]:
        mensajes.append(tw_rutas.pedir_copia(cliente, alc["tw"]["tienda_id"]))
    if s["meta_ok"]:
        ids = list(alc["meta_estructura"])
        if set(ids) == set(s["ids_cuentas"]) and (ids or s["actual"] is None):
            mensajes.append(meta_rutas.pedir_copia(cliente, None))
        else:
            mensajes.extend(meta_rutas.pedir_copia(cliente, act) for act in ids)
    for texto, categoria in dict.fromkeys(mensajes):
        flash(texto, categoria)
    return _volver(cliente)
