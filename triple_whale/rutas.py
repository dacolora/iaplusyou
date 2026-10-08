"""Blueprint de la pestaña Triple Whale (spec 2026-09-28 §8), bajo
`/cliente/<cliente>/triple-whale`. `dashboard._guard_por_cliente` protege
todo porque la URL lleva `<cliente>`; cada POST además exige el mismo origen
(Sec-Fetch-Site), la barrera CSRF del resto de la app.

- `panel`: el fragmento que la pestaña pide por fetch (solo lectura). Lee
  `tienda` (spec 2026-10-08 §6.2): una tienda del proyecto; ajena o inválida = «Todas».
- `sincronizar`: encola la copia de Triple Whale (gratis): sin `tienda_id`, la
  de cada tienda; con él, la de esa (ajena o inválida → 404).
- `evaluar`: encola el análisis con IA con la muestra del periodo Y la tienda
  que se están viendo (`tienda`, como en el panel); `extra` guarda `tienda_id`
  y `pais`. El precio ya estaba a la vista en el botón (y en su confirmación).
- `idea_crear`: una idea del análisis → Crear precargado (nada se genera).
- `a_referente`: un anuncio de una evaluación → Referentes del proyecto.
- `pieza_estado`: pausa o activa en Meta un anuncio hecho en Creatv (una
  pieza de experimento) desde la tabla, con confirmación; usa
  `lanzador.pausar_pieza` / `activar_pieza`, que dejan su evento.
- `galeria` (GET, spec 2026-10-08 tarjetas §5.2): una página de tarjetas
  (`dias`, `canal`, `tienda`, `veredicto`, `pagina`) para los filtros y «Ver más».
- `tarjeta` (GET, §5.3): una sola tarjeta, para repintarla cuando termina su
  análisis; un anuncio que no está en el alcance (o un id raro) es 404.
- `analizar_anuncio`, `analizar_lote`, `analisis_detalle`, `anuncio_referente`:
  esqueletos que la galería ya nombra (501/404); los llena la tarea 8 del plan.
"""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext

import idiomas
import triple_whale
import triple_whale_tiendas
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, evaluacion, panel, puente

bp = Blueprint("triple_whale", __name__, url_prefix="/cliente/<cliente>/triple-whale")


@bp.before_request
def _mismo_origen():
    if request.method == "POST":
        sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sitio and sitio not in ("same-origin", "none"):
            abort(403)


# Los nombres de los canales viven en el paquete (los usa también `mejorar`, que corre en el worker).
NOMBRES_CANAL = triple_whale.NOMBRES_CANAL


@bp.app_template_filter("tw_num")
def _tw_num(valor, decimales=0):
    """Número con los separadores del idioma; «—» si no hay dato."""
    if valor is None:
        return "—"
    return idiomas.numero(float(valor), decimales)


@bp.app_template_filter("tw_pct")
def _tw_pct(valor, decimales=1, es_fraccion=True):
    """0,123 -> «12,3 %» (o 12,3 -> «12,3 %» con es_fraccion=False)."""
    if valor is None:
        return "—"
    return idiomas.numero(float(valor) * (100 if es_fraccion else 1), decimales) + " %"


@bp.app_template_filter("tw_var")
def _tw_var(valor):
    """Variación contra el periodo anterior: «+12 %», «−8 %», "" sin dato."""
    if valor is None:
        return ""
    signo = "+" if valor >= 0 else "−"
    return f"{signo}{idiomas.numero(abs(valor) * 100)} %"


@bp.app_template_filter("tw_canal")
def _tw_canal(canal):
    return NOMBRES_CANAL.get(canal, canal or "—")


def _volver(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="triplewhale"))


def _dias(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return panel.PERIODO_DEFECTO


@bp.get("/panel")
def ver_panel(cliente):
    ctx = panel.contexto(cliente, _dias(request.args.get("dias")), (request.args.get("canal") or "").strip() or None,
                         tienda_id=request.args.get("tienda"))
    armar_grafico = current_app.extensions.get("grafico_tablero")
    grafico = armar_grafico(ctx["serie"]) if armar_grafico and ctx.get("serie") else None
    return render_template("_tw_panel.html", cliente=cliente, tw=ctx, grafico=grafico)


# ------------------------------------------------ galería de tarjetas (spec tarjetas §5) ---

def _alcance_peticion(cliente, fuente):
    return panel.alcance(cliente, _dias(fuente.get("dias")), (fuente.get("canal") or "").strip() or None,
                         fuente.get("tienda"))


def _contexto_galeria(cliente, alc):
    """Lo que necesitan las macros de la galería fuera del panel."""
    return {"cliente": cliente, "moneda": alc["config"]["moneda"], "alcance_params": alc["params"],
            "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO,
            "frases_veredicto": evaluacion.FRASES_VEREDICTO, "tendencias": evaluacion.TENDENCIAS,
            "vacios_anillo": evaluacion.VACIOS_ANILLO, "problemas": evaluacion.PROBLEMAS,
            "fortalezas": evaluacion.FORTALEZAS}


@bp.get("/galeria")
def galeria(cliente):
    alc = _alcance_peticion(cliente, request.args)
    if not alc:
        abort(404)
    g = panel.galeria(cliente, alc["ev"], request.args.get("veredicto") or "", request.args.get("pagina"))
    return render_template("_tw_galeria_fragmento.html", modo="pagina", g=g, **_contexto_galeria(cliente, alc))


@bp.get("/tarjeta/<canal>/<ad_id>")
def tarjeta(cliente, canal, ad_id):
    if not (tareas_tw.id_valido(canal) and tareas_tw.id_valido(ad_id)):
        abort(404)
    alc = _alcance_peticion(cliente, request.args)
    a = next((x for x in (alc or {}).get("ev", {}).get("anuncios", []) if x["canal"] == canal and x["ad_id"] == ad_id),
             None)
    if a is None:
        abort(404)
    panel.enriquecer(cliente, [a], alc["ev"], datos.ultimos_analisis(cliente, [(canal, ad_id)]))
    return render_template("_tw_galeria_fragmento.html", modo="tarjeta", a=a, **_contexto_galeria(cliente, alc))


# Esqueletos: la galería ya los nombra (url_for); la tarea 8 del plan los llena.
@bp.post("/anuncio/<canal>/<ad_id>/analizar")
def analizar_anuncio(cliente, canal, ad_id):
    abort(501)


@bp.post("/analizar-lote")
def analizar_lote(cliente):
    abort(501)


@bp.get("/analisis/<int:aid>")
def analisis_detalle(cliente, aid):
    abort(404)


@bp.post("/anuncio/<canal>/<ad_id>/referente")
def anuncio_referente(cliente, canal, ad_id):
    abort(501)


@bp.post("/sincronizar")
def sincronizar(cliente):
    tienda_id = None
    valor = (request.form.get("tienda_id") or "").strip()
    if valor:
        try:
            tienda_id = int(valor)
        except ValueError:
            abort(404)
        if not triple_whale_tiendas.tienda(cliente, tienda_id):
            abort(404)
    if not triple_whale_tiendas.obtener(cliente):
        flash(gettext("Triple Whale no está conectado en este proyecto."), "error")
    elif tareas_tw.encolar_sync(cliente, tienda_id):
        flash(gettext("Trayendo las métricas de Triple Whale…"), "ok")
    else:
        flash(gettext("Ya se están trayendo las métricas de Triple Whale."), "warn")
    return _volver(cliente)


@bp.post("/evaluar")
def evaluar(cliente):
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        flash(gettext("Triple Whale no está conectado en este proyecto."), "error")
        return _volver(cliente)
    if tareas_tw.evaluacion_en_curso(cliente):
        flash(gettext("Ya hay una evaluación con IA en curso."), "warn")
        return _volver(cliente)
    canal = (request.form.get("canal") or "").strip() or None
    tienda = panel.tienda_elegida(config["tiendas"], request.form.get("tienda"))
    tienda_id = tienda["id"] if tienda else None
    ev, desde, hasta = panel.evaluar_periodo(cliente, _dias(request.form.get("dias")), canal, tienda_id=tienda_id)
    muestra = analisis.muestra(ev)
    if not muestra:
        flash(gettext("Todavía no hay anuncios con datos suficientes para evaluar con IA."), "error")
        return _volver(cliente)
    eid = datos.crear_evaluacion(cliente, desde, hasta, config["moneda"], muestra,
                                 pedido_por=session.get("usuario"))
    datos.actualizar_evaluacion(eid, extra={"modelo": config["modelo_atribucion"],
                                            "ventana": config["ventana_atribucion"], "canal": canal,
                                            "tienda_id": tienda_id, "pais": tienda["pais"] if tienda else None,
                                            "benchmarks": ev["benchmarks"], "meta_roas": ev["meta_roas"]})
    if not tareas_tw.encolar_evaluacion(cliente, eid):
        datos.borrar_evaluacion(cliente, eid)
        flash(gettext("Ya hay una evaluación con IA en curso."), "warn")
        return _volver(cliente)
    flash(gettext("Evaluando %(n)s anuncio(s) con IA…", n=len(muestra)), "ok")
    return _volver(cliente)


def _evaluacion_lista(cliente, eid):
    fila = datos.evaluacion(cliente, eid)
    if not fila or fila["estado"] != "lista":
        abort(404)
    return fila


@bp.post("/evaluacion/<int:eid>/idea/<int:indice>/crear")
def idea_crear(cliente, eid, indice):
    ideas = (_evaluacion_lista(cliente, eid)["resultado"] or {}).get("ideas") or []
    if not 0 <= indice < len(ideas):
        abort(404)
    try:
        session["fp_prefill"] = puente.prefill_crear(cliente, ideas[indice], evaluacion_id=eid, indice=indice)
    except puente.PuenteError as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Idea cargada en Crear: ajusta lo que quieras y genera."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@bp.post("/evaluacion/<int:eid>/anuncio/<ref>/referente")
def a_referente(cliente, eid, ref):
    fila = _evaluacion_lista(cliente, eid)
    anuncio = next((a for a in fila["anuncios"] or [] if a.get("ref") == ref), None)
    if anuncio is None:
        abort(404)
    clasif = ((fila["resultado"] or {}).get("anuncios") or {}).get(ref)
    try:
        _, creado = puente.a_referente(cliente, anuncio, clasif)
    except puente.PuenteError as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Guardado en Referentes: desde ahí puedes recrearlo con tu producto o usarlo en un sprint.")
          if creado else gettext("Ese anuncio ya estaba en Referentes."), "ok")
    return _volver(cliente)


@bp.post("/pieza/<int:ep_id>/<accion>")
def pieza_estado(cliente, ep_id, accion):
    """Pausar o activar en Meta una pieza de experimento (un anuncio hecho en
    Creatv) desde la evaluación. Reversible y explícito: un clic con confirm."""
    import lanzador
    if accion not in ("pausar", "activar"):
        abort(404)
    try:
        if accion == "pausar":
            lanzador.pausar_pieza(cliente, ep_id)
            flash(gettext("Anuncio pausado en Meta."), "ok")
        else:
            lanzador.activar_pieza(cliente, ep_id)
            flash(gettext("Anuncio activado en Meta."), "ok")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:  # noqa: BLE001 — Meta caída o token vencido: se muestra sin el token
        import cola
        flash(gettext("Meta no aceptó el cambio: %(error)s", error=cola.sin_token(str(e) or type(e).__name__)), "error")
    return _volver(cliente)
