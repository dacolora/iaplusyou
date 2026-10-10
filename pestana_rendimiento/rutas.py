"""Blueprint de la pestaña «Rendimiento» (spec 2026-10-09 §4–§5, A5), bajo `/cliente/<cliente>/rendimiento`.
`dashboard._guard_por_cliente` protege todo porque la URL lleva `<cliente>`; cada POST además exige el mismo origen
(Sec-Fetch-Site, la barrera CSRF del resto de la app), y «Actualizar ahora» correo verificado (el admin está exento),
como la vieja ruta de Meta. Las que cobran no lo exigen, como en producción (S2 de la revisión final; PND-292).

- `panel` (GET): el fragmento que la pestaña pide por fetch (solo lee la copia local). `entrada` = la clave de una
  entrada del selector; vacía, ajena o rara = «Todas». `tienda`/`cuenta` son los parámetros de las pestañas viejas.
- `dia` (GET, E2 tarea 7): el detalle de un día de «Resultados» con Meta o mezcla (`panel.dia` → `resumen.dia`); con
  alcance solo Triple Whale, `triple_whale.panel.contexto_dia` como siempre. Una `entrada` ajena no lee nada (400).
- `conjuntos` (GET): «Ver más» de la tabla de conjuntos; devuelve solo filas `<tr>`.
- `actualizar` (POST): «Actualizar ahora» encola las copias de Triple Whale y de Meta del alcance (una `entrada` que
  no existe no encola nada: solo la vacía es «Todas») con sus `job_id` de siempre y las reglas de cada una (`triple_whale.rutas.pedir_copia`, `meta_rendimiento.rutas.pedir_copia`: la
  pausa compartida de Meta y la espera de 30 minutos de quien no es admin). Leer no cobra.

«Tus anuncios», UNA galería con los anuncios de las dos fuentes (E2 tarea 4, 2026-10-10; `pestana_rendimiento.galeria`).
Todas resuelven el alcance con `entrada`, `dias` y `canal` (este solo si el alcance es solo Triple Whale) por
`panel.alcances`, la misma resolución que el panel; `<fuente>` es "tw" o "meta" y `<canal>`/`<ad_id>` pasan por
`tareas.triple_whale.id_valido` (si no, 404, antes de leer nada):

- `galeria` (GET): con `entera=1`, el bloque entero de un filtro (chips, formulario del lote con sus claves y su precio,
  y la rejilla, página 1); sin ella («Ver más»), solo las tarjetas de `pagina`.
- `tarjeta/<fuente>/<canal>/<ad_id>` (GET): una tarjeta sola, para repintarla cuando termina su análisis; un anuncio
  que no está en el alcance de esa fuente es 404.
- `anuncio/<fuente>/<canal>/<ad_id>/analizar` (POST): «Cómo mejorarlo» con `triple_whale.pedidos.pedir_analisis` y el
  alcance de SU fuente (precio a la vista, Cobros, `max_intentos=1`, nunca dos veces lo mismo). Con
  `Accept: application/json` responde JSON con la tarjeta ya en curso (también sin alcance: el JS de la tarjeta espera
  JSON); sin saldo, el 402 de `dashboard._saldo_insuficiente`.
- `analizar-lote` (POST): «Analizar los N que más gastaron». Cobra solo las claves `<fuente>:<canal>:<ad_id>` que
  mostró el formulario, recortadas a N entre las dos fuentes y aún elegibles, cada una con su fuente
  (`galeria.pedir_lote`); un segundo envío no cobra nada y la primera fuente sin saldo para todo.

- `evaluar` (POST, E2 tarea 5): «Evaluar con IA» de la parte Triple Whale del alcance (`fuente` "tw"; otra, 404), con
  `triple_whale.pedidos.pedir_evaluacion` (la muestra, el precio de su botón, Cobros, `max_intentos=1`, una por
  proyecto). La de las cuentas de Meta es la de Meta rendimiento E2 (`meta_rendimiento.rutas.evaluar` con `entrada`):
  la rama Meta de E2 tarea 5 se jubiló en la integración con main (INT-2, 2026-10-10).

Hasta el 2026-10-10 la galería, la tarjeta, «Cómo mejorarlo», el lote y «Evaluar con IA» vivían en
`triple_whale/rutas.py` (solo Triple Whale) y los anuncios de Meta tenían su bloque aparte (`anuncios-meta`, sin IA): se
jubilaron con la galería única y con esta ruta. «Guardar en Referentes», el detalle de un
análisis, «Llevar a Crear» (también de una idea de la evaluación) y Pausar/Activar siguen allá."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext, ngettext

import usuarios
from cobros import SaldoInsuficiente
from meta_rendimiento import rutas as meta_rutas
from pestana_rendimiento import galeria, panel
from tareas import triple_whale as tareas_tw
from triple_whale import pedidos
from triple_whale import rutas as tw_rutas

bp = Blueprint("rendimiento", __name__, url_prefix="/cliente/<cliente>/rendimiento")
FECHA_MINIMA, FECHA_MAXIMA = date(2000, 1, 1), date(2100, 1, 1)     # el detalle de un día (`ver_dia`), fuera: 400


@bp.before_request
def _mismo_origen():
    if request.method == "POST":
        sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sitio and sitio not in ("same-origin", "none"):
            abort(403)


# Las rutas que exigen correo verificado: solo «Actualizar ahora», como la vieja ruta de Meta (`meta_rendimiento.rutas`).
CON_CORREO_VERIFICADO = ("rendimiento.actualizar",)


@bp.before_request
def _correo_verificado():
    """Sin correo verificado una persona con rol cliente no pide copias desde aquí (el mismo criterio que
    `meta_rendimiento.rutas._correo_verificado`; este Blueprint no puede importar `dashboard`). El admin pasa.

    Solo para `CON_CORREO_VERIFICADO`. S2 (revisión final de Rendimiento E2, 2026-10-10): producción no tiene SMTP y 2
    de 4 usuarios cliente no pueden verificar su correo; «Cómo mejorarlo», el lote y «Evaluar con IA» de Triple Whale no
    lo exigían cuando vivían en `triple_whale/rutas.py` y siguen sin exigirlo (el mismo origen sí, `_mismo_origen`).
    Exigirlo en las rutas que cobran cuando el VPS tenga SMTP: PND-292."""
    if request.method != "POST" or request.endpoint not in CON_CORREO_VERIFICADO or meta_rutas.es_admin():
        return None
    entry = usuarios.obtener(session.get("usuario") or "")
    if entry and entry.get("correo_verificado"):
        return None
    flash(gettext("Confirma tu correo primero (Configuración › Cuenta)."), "error")
    return redirect(url_for("ver_cliente", cliente=request.view_args["cliente"], _anchor="settings"))


def _quiere_json():
    return "application/json" in (request.headers.get("Accept") or "")


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
    # Con Meta o mezcla el detalle del día es de esta pestaña (E2 tarea 7, A3): la entrada que se está mirando.
    if ctx["resumen"]["resultados"]:
        ctx["resumen"]["resultados"]["datos"]["url_dia"] = url_for("rendimiento.ver_dia", cliente=cliente,
                                                                   entrada=ctx["params"]["entrada"])
    return render_template("_rend_panel.html", cliente=cliente, r=ctx, es_admin=meta_rutas.es_admin())


@bp.get("/dia")
def ver_dia(cliente):
    """«Qué pasó el …» de «Resultados» (fragmento `_tw_dia.html` que pide static/tw_resultados.js; E2 tarea 7, spec
    A3). Solo lectura y solo GET: `entrada` es la de la pestaña (una ajena no lee nada: 400) y `fecha` un día del
    primero del alcance a ayer; con alcance solo Triple Whale, el detalle de `triple_whale.panel.contexto_dia` tal cual
    (con su `canal`). Cualquier otra cosa, 400 con el motivo en palabras."""
    try:
        fecha = date.fromisoformat(_texto("fecha")[:10])
    except ValueError:
        return gettext("Fecha no válida."), 400
    if not FECHA_MINIMA <= fecha <= FECHA_MAXIMA:
        # Ninguna copia llega tan atrás ni tan adelante, y restar días a una fecha así revienta (0001-01-02 daba 500).
        return gettext("Fecha no válida."), 400
    ctx, motivo = panel.dia(cliente, fecha, _texto("entrada"), canal=_texto("canal") or None)
    if ctx is None:
        return motivo, 400
    return render_template("_tw_dia.html", cliente=cliente, d=ctx)


@bp.get("/conjuntos")
def ver_conjuntos(cliente):
    ctx = panel.conjuntos_pagina(cliente, _entero(request.args.get("dias")), _texto("entrada"),
                                 _entero(request.args.get("pagina")))
    return render_template("_meta_conjuntos_filas.html", cliente=cliente, mr=ctx)


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


# ------------------------------------------------ «Tus anuncios»: la galería y lo que cobra (E2 tarea 4) ---

def _alcances(cliente, datos):
    return panel.alcances(cliente, _entero(datos.get("dias")), (datos.get("entrada") or "").strip(),
                          (datos.get("canal") or "").strip() or None)


def _render_galeria(cliente, al, **ctx):
    """El fragmento de la galería (`_tw_galeria_fragmento.html`) con lo que piden sus macros fuera del panel."""
    return render_template("_tw_galeria_fragmento.html", cliente=cliente, params=al["params"],
                           params_tw=al["params_tw"], textos=panel.etiquetas(), **ctx)


def _anuncio_valido(fuente, canal, ad_id):
    """404 antes de leer nada si la fuente no es "tw"/"meta" o un id no puede ir en una URL ni en un job_id."""
    if fuente not in galeria.FUENTES or not (tareas_tw.id_valido(canal) and tareas_tw.id_valido(ad_id)):
        abort(404)


@bp.get("/galeria")
def ver_galeria(cliente):
    al = _alcances(cliente, request.args)
    if not (al["tw"] or al["meta"]):
        abort(404)
    # `entera=1` (un filtro nuevo): el bloque entero de ese filtro, página 1, para que el JS lo reemplace y el lote
    # (sus claves y su precio) sea siempre el del filtro que se ve. Sin ella («Ver más»): solo las tarjetas.
    entera = request.args.get("entera") == "1"
    g = galeria.armar(cliente, al["tw"], al["meta"], request.args.get("veredicto") or "",
                      1 if entera else request.args.get("pagina"))
    return _render_galeria(cliente, al, modo="entera" if entera else "pagina", g=g)


@bp.get("/tarjeta/<fuente>/<canal>/<ad_id>")
def ver_tarjeta(cliente, fuente, canal, ad_id):
    _anuncio_valido(fuente, canal, ad_id)
    al = _alcances(cliente, request.args)
    a = pedidos.anuncio_del_alcance(al[fuente], canal, ad_id) if al[fuente] else None
    if a is None:
        abort(404)
    galeria.tarjeta(cliente, fuente, al[fuente], a)
    return _render_galeria(cliente, al, modo="tarjeta", a=a)


def _sin_alcance(al, fuente):
    """Por qué no hay alcance de esa fuente (nada se cobra): Triple Whale desconectado, o una vista que ya no existe
    (una pestaña vieja, Meta desconectado después de pintar, una entrada sin esa fuente)."""
    if fuente == galeria.TW and al["existe"] and not al["hay_tw"]:
        return gettext("Triple Whale no está conectado en este proyecto.")
    return gettext("Esa vista ya no existe: recarga la pestaña.")


@bp.post("/anuncio/<fuente>/<canal>/<ad_id>/analizar")
def analizar_anuncio(cliente, fuente, canal, ad_id):
    _anuncio_valido(fuente, canal, ad_id)
    al = _alcances(cliente, request.form)
    alc = al[fuente]
    if not alc:
        # Sin el alcance de esa fuente no se cobra: una pestaña vieja, Triple Whale o Meta desconectados después de
        # pintar. El JS de la tarjeta espera JSON: un redirect no lo sabría leer.
        mensaje = _sin_alcance(al, fuente)
        if _quiere_json():
            return {"ok": False, "mensaje": mensaje, "html": ""}
        flash(mensaje, "error")
        return _volver(cliente)
    a = pedidos.anuncio_del_alcance(alc, canal, ad_id)
    if a is None:
        abort(404)
    ok, mensaje = pedidos.pedir_analisis(cliente, alc, a, session.get("usuario"))
    if _quiere_json():
        galeria.tarjeta(cliente, fuente, alc, a)
        return {"ok": ok, "mensaje": mensaje, "html": _render_galeria(cliente, al, modo="tarjeta", a=a)}
    flash(mensaje, "ok" if ok else "warn")
    return _volver(cliente)


def _avisos_lote(n, fallos):
    if n:
        flash(ngettext("Analizando %(num)s anuncio con IA…", "Analizando %(num)s anuncios con IA…", n), "ok")
    if fallos:
        flash(ngettext("No se pudo encolar %(num)s anuncio: vuelve a intentarlo.",
                       "No se pudieron encolar %(num)s anuncios: vuelve a intentarlo.", fallos), "warn")


@bp.post("/analizar-lote")
def analizar_lote(cliente):
    al = _alcances(cliente, request.form)
    if not (al["tw"] or al["meta"]):
        flash(gettext("Esa vista ya no existe: recarga la pestaña.") if not al["existe"]
              else gettext("Conecta Triple Whale o Meta para ver tu rendimiento."), "warn")
        return _volver(cliente)
    # Lo confirmado, a lo sumo N entre las dos fuentes (recortado ANTES de separarlas); cada fuente cobra solo lo suyo
    # aún elegible con el filtro que lo mostró y la primera sin saldo para todo (`galeria.pedir_lote`).
    claves = galeria.claves_confirmadas(request.form.getlist("clave"))
    try:
        n, fallos = galeria.pedir_lote(cliente, al, claves, session.get("usuario"),
                                       veredicto=request.form.get("veredicto") or "")
    except SaldoInsuficiente as e:
        _avisos_lote(*getattr(e, "lote", (0, 0)))   # los que sí salieron; el manejador común dice el resto
        raise
    _avisos_lote(n, fallos)
    if not n and not fallos:
        flash(gettext("No quedó ningún anuncio por analizar."), "warn")
    return _volver(cliente)


# ------------------------------------------------ «Lo que hace ganar en tu cuenta»: Evaluar con IA (E2 tarea 5) ---

def _alc_eval(alc):
    """Lo que guarda la evaluación de Triple Whale (`pedidos.pedir_evaluacion`): {"ev", "desde", "hasta", "moneda",
    "extra"}, el mismo `extra` de siempre."""
    ev, config = alc["ev"], alc["config"]
    extra = {"modelo": config["modelo_atribucion"], "ventana": config["ventana_atribucion"],
             "benchmarks": ev["benchmarks"], "meta_roas": ev["meta_roas"], "tienda_id": alc["tienda_id"],
             "canal": alc["canal"], "pais": alc["tienda"]["pais"] if alc["tienda"] else None}
    return {"ev": ev, "desde": alc["desde"], "hasta": alc["hasta"], "moneda": config["moneda"], "extra": extra}


@bp.post("/evaluar")
def evaluar(cliente):
    """«Evaluar con IA» de la parte Triple Whale del alcance: su muestra, el precio que mostró su botón (el formulario
    manda `n` y `precio_visto` y si no coinciden no se cobra: G3), Cobros, la fila y la tarea
    (`triple_whale.pedidos.pedir_evaluacion`, `max_intentos=1`). Una evaluación en curso (un `job_id`
    por proyecto) bloquea otra, y una vista que ya no tiene Triple Whale no cobra nada. `fuente` distinta de "tw" es
    404: la de Meta es `meta_rendimiento.rutas.evaluar` (INT-2)."""
    fuente = (request.form.get("fuente") or galeria.TW).strip()
    if fuente != galeria.TW:
        abort(404)
    if tareas_tw.evaluacion_en_curso(cliente):
        flash(gettext("Ya hay una evaluación con IA en curso."), "warn")
        return _volver(cliente)
    al = _alcances(cliente, request.form)
    alc = al[fuente]
    if not alc:
        flash(_sin_alcance(al, fuente), "error")
        return _volver(cliente)
    # Sin muestra el aviso es un error (ok None); con otra en curso (carrera con el encolado) o si el botón mostró otro
    # número o precio (G3, la guarda E2-R6), una advertencia: nada se crea ni se cobra.
    ok, mensaje = pedidos.pedir_evaluacion(cliente, _alc_eval(alc), session.get("usuario"),
                                           n_visto=request.form.get("n"), precio_visto=request.form.get("precio_visto"))
    flash(mensaje, "ok" if ok else ("error" if ok is None else "warn"))
    return _volver(cliente)
