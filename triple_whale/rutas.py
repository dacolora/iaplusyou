"""Blueprint de Triple Whale (spec 2026-09-28 §8), bajo `/cliente/<cliente>/triple-whale`. Desde el 2026-10-09 la
pestaña es «Rendimiento» (`pestana_rendimiento/`, spec 2026-10-09): su panel y «Actualizar ahora» viven allá, y aquí
quedan las rutas que la pestaña llama con el alcance de Triple Whale de la entrada (R13; «Cómo mejorarlo» y el lote
pasaron a la pestaña en E2, ver abajo). `dashboard._guard_por_cliente` protege todo porque la URL lleva `<cliente>`; cada POST además exige el mismo
origen (Sec-Fetch-Site), la barrera CSRF del resto de la app. Todas vuelven a `#rendimiento`.

- `dia`: el detalle de un día de «Resultados de tu tienda» (lo pide static/tw_resultados.js).
- `idea_crear`: una idea del análisis → Crear precargado (nada se genera).
- `a_referente`: un anuncio de una evaluación → Referentes del proyecto.
- `pieza_estado`: pausa o activa en Meta un anuncio hecho en Creatv (una
  pieza de experimento) desde la tabla, con confirmación; usa
  `lanzador.pausar_pieza` / `activar_pieza`, que dejan su evento.
- `analisis_detalle` (GET, §6.5): el fragmento con lo que dijo Claude; `analisis_crear` (§7.1) lleva la versión
  mejorada a Crear; `analisis_aprendizaje` (§6.3) la guarda como aprendizaje del proyecto con un clic;
  `anuncio_referente` (§7.2) guarda el anuncio en Referentes.
- `ganchos_probar` (POST, spec 2026-10-09 §4.3): «Probar los N ganchos» de un análisis: revisa, compara el precio
  visto, pide saldo, crea la tanda (`tw_gancho`) y encola su preparación (gratis; cada clip lo cobra su pieza de Crear).
  Lo pide el detalle de un análisis de la galería de «Rendimiento» (JS en `_tab_rendimiento.html`).

El pedido pagado en sí (la foto, Cobros, la fila y la tarea de «Cómo mejorarlo», del lote y de «Evaluar con IA») vive
en `triple_whale/pedidos.py` desde Rendimiento E2 (2026-10-10), para que la pestaña Rendimiento lo use también con los
anuncios de Meta; aquí quedan el alcance de la petición, los avisos y las redirecciones.

La galería, la tarjeta sola, «Cómo mejorarlo» de un anuncio y el lote («Analizar los N que más gastaron») ya no viven
aquí: desde Rendimiento E2 (tarea 4, 2026-10-10) «Tus anuncios» es UNA galería con los anuncios de Triple Whale y de
Meta y sus rutas son de la pestaña (`pestana_rendimiento/rutas.py`: `ver_galeria`, `ver_tarjeta`, `analizar_anuncio`,
`analizar_lote`), que cobran con `pedidos` y el alcance de cada fuente. «Evaluar con IA» (`evaluar`) también se fue
allá en E2 tarea 5 (`rendimiento.evaluar`, un botón por fuente del alcance); lo que se hace con una evaluación lista
(`idea_crear`, `a_referente`) sigue aquí.
"""
import logging
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext, ngettext

import cola
import creative_flow
import gastos
import idiomas
import proyectos
import triple_whale
import triple_whale_tiendas
from cobros import libro
from doctrina import aprendizajes as doctrina_aprendizajes
from meta_rendimiento import cuentas as meta_cuentas
from tareas import triple_whale as tareas_tw
from triple_whale import datos, mejorar, panel, pedidos, puente
from triple_whale import ganchos as ganchos_tw

bp = Blueprint("triple_whale", __name__, url_prefix="/cliente/<cliente>/triple-whale")
AID_MAX = 2 ** 63 - 1           # el mayor entero de SQLite: un id más grande es 404, no un OverflowError (B7)
log = logging.getLogger("creatv.triple_whale.rutas")


@bp.before_request
def _mismo_origen():
    if request.method == "POST":
        sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sitio and sitio not in ("same-origin", "none"):
            abort(403)


# Los nombres de los canales viven en el paquete (los usan también `mejorar`, que corre en el worker, y
# «Resultados de tu tienda» en sus frases).
NOMBRES_CANAL = triple_whale.NOMBRES_CANAL


@bp.app_template_filter("tw_num")
def _tw_num(valor, decimales=0):
    """Número con los separadores del idioma; «—» si no hay dato."""
    if valor is None:
        return "—"
    return idiomas.numero(float(valor), decimales)


@bp.app_template_filter("tw_ventas")
def _tw_ventas(valor):
    """Ventas: entero cuando lo es («196 ventas», no «196,0») y un decimal cuando el Pixel reparte fracciones de un
    pedido (revisión final, D2). «—» si no hay dato."""
    if valor is None:
        return "—"
    v = round(float(valor), 1)
    return idiomas.numero(v, 0 if v == int(v) else 1)


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


def _quiere_json():
    return "application/json" in (request.headers.get("Accept") or "")


def _volver(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="rendimiento"))


def _dias(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return panel.PERIODO_DEFECTO


@bp.get("/dia")
def ver_dia(cliente):
    """El detalle de un día de «Resultados de tu tienda» (fragmento que pide static/tw_resultados.js). Solo
    lectura: un día del primero copiado a ayer, en la tienda y el canal que se están mirando."""
    try:
        fecha = date.fromisoformat((request.args.get("fecha") or "").strip()[:10])
    except ValueError:
        return gettext("Fecha no válida."), 400
    ctx = panel.contexto_dia(cliente, fecha, (request.args.get("canal") or "").strip() or None,
                             tienda_id=request.args.get("tienda"))
    if ctx is None:
        return gettext("Ese día no tiene datos completos de Triple Whale."), 400
    return render_template("_tw_dia.html", cliente=cliente, d=ctx)


# ------------------------------------------------ alcance de la petición ---

def _alcance_peticion(cliente, fuente):
    """El alcance de Triple Whale de un formulario (`dias`, `canal`, `tienda`): lo usa «Guardar en Referentes»."""
    return panel.alcance(cliente, _dias(fuente.get("dias")), (fuente.get("canal") or "").strip() or None,
                         fuente.get("tienda"))


def _analisis_listo(cliente, aid):
    fila = datos.analisis_anuncio(cliente, aid)
    if not fila or fila["estado"] != "lista":
        abort(404)
    return fila


def _aprendizaje_guardado(cliente, aid):
    return any(x.get("analisis_id") == aid for x in proyectos.aprendizajes(cliente))


def _nombre_alcance(cliente, fila):
    """«Todas las tiendas» o el nombre de la tienda en que se pagó ese análisis ("" si ya no existe). Uno de fuente
    Meta (B1, revisión final de Rendimiento E2, 2026-10-10: su `tienda_id` es None porque no es de ninguna tienda, no
    porque sea de todas) dice su cuenta de Meta o, si ya no está en el proyecto, «tus cuentas de Meta»."""
    foto = fila.get("foto") or {}
    if foto.get("fuente") == "meta":
        cuenta = meta_cuentas.cuenta(cliente, foto["ad_account_id"]) if foto.get("ad_account_id") else None
        return (cuenta or {}).get("nombre") or gettext("tus cuentas de Meta")
    if fila.get("tienda_id") is None:
        return gettext("Todas las tiendas")
    tienda = triple_whale_tiendas.tienda(cliente, fila["tienda_id"])
    return panel.nombre_tienda(tienda) if tienda else ""


def _aprendizaje_de(cliente, fila):
    """El aprendizaje (dict) que guardaría «Guardar como aprendizaje», o None. Lo que se guarda va en el idioma del
    PROYECTO (regla 3), no en el de quien hace el clic; el detalle muestra este mismo texto junto al botón (B1)."""
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        return doctrina_aprendizajes.desde_analisis_tw(fila)


def _contexto_ganchos(cliente, fila):
    """Lo que el detalle pinta de los ganchos (spec 2026-10-09 §4.1 y §5) y lo que la ruta revisa antes de pedir:
    los generables, su precio, por qué no se ofrece el botón (o None) y las tandas. UNA consulta a tw_gancho, y una a
    la cola solo si hay variantes vivas: una barra se pinta solo si su trabajo sigue vivo (ruling 4)."""
    r = fila.get("resultado") or {}
    generables = ganchos_tw.ganchos_generables(r)
    filas = datos.ganchos_de_analisis(cliente, fila["id"])
    precio = gastos.estimar_ganchos_tw(len(generables))
    # Arreglo D (revisión del gasto, 2026-10-09): lo que mira el botón es el PRECIO (`usd_precio`), que es None también
    # cuando el margen no se pudo leer (`gastos._margen_fallido`): entonces el motivo es «precio no disponible», el
    # botón no se puede pedir y la ruta responde 409. `|precio` caía al costo (margen 1,0) y lo mostraba como precio.
    # Un anuncio de fuente Meta solo para un admin en colorado_forja hasta su prueba real (PND-289): la misma revisión
    # en el detalle y en la ruta que cobra, así que nadie más ve el botón ni lo pide por un POST armado.
    motivo = ganchos_tw.puede_probar(fila, generables, filas, precio["usd_precio"],
                                     mejorar._url_voz(fila.get("foto") or {}),
                                     meta_en_prueba=ganchos_tw.prueba_meta_permitida(cliente, session.get("rol")))
    tandas = ganchos_tw.tandas(filas)
    vivos = cola.job_ids_vivos_todos() if any(f["estado"] in datos.VIVOS_GANCHO for f in filas) else set()
    for t in tandas:
        for g in t["filas"]:
            g["barra"] = g["estado"] in datos.VIVOS_GANCHO and bool(g.get("job_id")) and g["job_id"] in vivos
    ultima = tandas[0]["filas"] if tandas else []
    # Arreglo C (revisión del gasto, 2026-10-09): una variante «generando» sin su trabajo vivo puede tener el clip en un
    # error que Crear recupera sin pagar de nuevo; entonces el detalle lleva a recuperarlo. Las sesiones se leen UNA
    # vez y solo si hay alguna variante así (regla 8: nada de una consulta por variante).
    sin_trabajo = {g["id"] for g in ultima if g["estado"] == "generando" and g.get("cf_id") and not g["barra"]}
    sesiones = creative_flow.cargar(cliente) if sin_trabajo else {}
    for g in ultima:
        g["recuperable"] = g["id"] in sin_trabajo and ganchos_tw.clip_recuperable(sesiones.get(g["cf_id"]))
    return {"generables": generables, "n": len(generables), "precio": precio, "motivo": motivo,
            "sin_precio": motivo == ganchos_tw.MOTIVO_SIN_PRECIO, "ultima": ultima, "anteriores": tandas[1:],
            # una recuperable espera a la persona, no al vigilante: la pestaña no vuelve a pedir el detalle por ella
            "esperan": any(g["estado"] in datos.VIVOS_GANCHO and not g["barra"] and not g["recuperable"]
                           for g in ultima)}


def _respuesta_ganchos(cliente, ok, mensaje, estado=200):
    """JSON {"ok", "mensaje"} al fetch de la pestaña (que nunca reenvía el POST); al formulario, aviso y vuelta."""
    if _quiere_json():
        return {"ok": ok, "mensaje": mensaje}, estado
    flash(mensaje, "ok" if ok else "warn")
    return _volver(cliente)


@bp.get(f"/analisis/<int(max={AID_MAX}):aid>")
def analisis_detalle(cliente, aid):
    fila = _analisis_listo(cliente, aid)
    r = fila["resultado"] or {}
    item = _aprendizaje_de(cliente, fila)
    return render_template("_tw_analisis.html", cliente=cliente, fila=fila, r=r,
                           guardado=_aprendizaje_guardado(cliente, aid), alcance_nombre=_nombre_alcance(cliente, fila),
                           aprendizaje_texto=item["texto"] if item else None,
                           cifras_aprendizaje=mejorar.cifras_del_aprendizaje(r),
                           gh=_contexto_ganchos(cliente, fila))


@bp.post(f"/analisis/<int(max={AID_MAX}):aid>/crear")
def analisis_crear(cliente, aid):
    version = (_analisis_listo(cliente, aid)["resultado"] or {}).get("version")
    if not version:
        abort(404)
    try:
        session["fp_prefill"] = puente.prefill_crear(cliente, version, analisis_id=aid)
    except puente.PuenteError as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Versión mejorada cargada en Crear: ajusta lo que quieras y genera."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@bp.post(f"/analisis/<int(max={AID_MAX}):aid>/aprendizaje")
def analisis_aprendizaje(cliente, aid):
    fila = _analisis_listo(cliente, aid)
    if _aprendizaje_guardado(cliente, aid):
        flash(gettext("Ese aprendizaje ya estaba guardado."), "ok")
        return _volver(cliente)
    # Una cifra que no está en los datos no se guarda como un hecho del proyecto (B2): ni con un formulario viejo.
    if mejorar.cifras_del_aprendizaje(fila["resultado"]):
        flash(gettext("Ese aprendizaje cita cifras que no están en los datos: no se guarda."), "warn")
        return _volver(cliente)
    item = _aprendizaje_de(cliente, fila)
    if not item:
        flash(gettext("Ese análisis no dejó un aprendizaje."), "warn")
        return _volver(cliente)
    proyectos.agregar_aprendizaje(cliente, item)
    flash(gettext("Aprendizaje guardado: las próximas ideas y guiones lo tendrán en cuenta."), "ok")
    return _volver(cliente)


@bp.post(f"/analisis/<int(max={AID_MAX}):aid>/ganchos")
def ganchos_probar(cliente, aid):
    """«Probar los N ganchos» (spec 2026-10-09 §4.3). Revisa §4.1 (409 con el motivo), compara `precio_visto` (es
    PRECIO: vuelve a costo una vez) con el recalculado ±0,005 (409 «El precio cambió…»), pide el total al libro
    (SaldoInsuficiente sube al manejador común: 402 / «Recargar saldo», sin guardar ni encolar), crea la tanda
    (TandaViva → 409; el análisis ya no es del proyecto → 404; un gancho repetido → 400) y encola su preparación con
    un job_id determinista. Si el encolado falla, la tanda queda en error con el motivo (en el idioma del proyecto) y
    el botón vuelve."""
    fila = datos.analisis_anuncio(cliente, aid)
    if fila is None:
        abort(404)
    gh = _contexto_ganchos(cliente, fila)
    if gh["motivo"]:                    # también «precio no disponible» si el margen no se pudo leer (arreglo D)
        motivo = gh["motivo"]
        return _respuesta_ganchos(cliente, False, gettext(motivo), 409)
    usd = gh["precio"]["usd"]
    visto = gastos.costo_de_precio(request.form.get("precio_visto"))
    if visto is None or abs(visto - usd) > 0.005:
        return _respuesta_ganchos(cliente, False, gettext(
            "El precio cambió: ahora es %(precio)s. Revisa y vuelve a pedirlo.",
            precio=gastos.formatear(gastos.precio(usd))), 409)
    libro.exigir(cliente, usd)                          # sin saldo: nada se guarda ni se encola (cobros §5)
    try:
        filas = datos.crear_tanda(cliente, aid, gh["generables"], pedido_por=session.get("usuario"))
    except datos.TandaViva:
        return _respuesta_ganchos(cliente, False, gettext("Ya hay una tanda de ganchos en curso para este análisis."), 409)
    except datos.AnalisisAjeno:
        abort(404)
    except ValueError:                                  # un `n` repetido: un dato malo, no se pide nada
        abort(400)
    tanda = filas[0]["tanda"]
    job_id = tareas_tw.job_id_preparar(cliente, aid, tanda)
    for g in filas:
        datos.actualizar_gancho(g["id"], job_id=job_id)
    try:
        encolada = tareas_tw.encolar_preparar(cliente, aid, tanda)
    except Exception as e:  # noqa: BLE001 — sin tarea nadie terminaría la tanda: queda en error y el botón vuelve
        log.warning("ganchos: no se pudo encolar la tanda %s del análisis %s (%s)", tanda, aid, type(e).__name__)
        encolada = False
    if not encolada:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):          # lo que se guarda, en el idioma del proyecto
            error = gettext("No se pudo poner la preparación en la cola.")
        for g in filas:
            datos.mover(g["id"], "preparando", "error", error=error)
        return _respuesta_ganchos(cliente, False, gettext("No se pudo poner la preparación en la cola: vuelve a intentarlo."), 409)
    return _respuesta_ganchos(cliente, True, ngettext("Generando %(num)s gancho…", "Generando %(num)s ganchos…", len(filas)))


@bp.post("/anuncio/<canal>/<ad_id>/referente")
def anuncio_referente(cliente, canal, ad_id):
    if not (tareas_tw.id_valido(canal) and tareas_tw.id_valido(ad_id)):
        abort(404)
    alc = _alcance_peticion(cliente, request.form)
    a = pedidos.anuncio_del_alcance(alc, canal, ad_id) if alc else None
    if a is None:
        abort(404)
    c = datos.creativos(cliente, [(canal, ad_id)]).get((canal, ad_id)) or {}
    # La miniatura es la misma que pinta la tarjeta (`panel.medio_tarjeta`): el botón sale justo cuando esto puede guardar.
    creatv = datos.piezas_creatv(cliente, [ad_id]).get(ad_id) if canal == triple_whale.CANAL_META else None
    visto = panel.medio_tarjeta(dict(a, creativo=c, creatv=creatv))
    imagen = visto.get("imagen") or visto.get("poster")
    anuncio = dict(a, medio={"imagen": imagen, "titulo": c.get("titulo") or "", "texto": c.get("copy") or "",
                             "tipo": "video" if (c.get("tipo") or "") == "video" else "imagen"})
    fila = datos.ultimos_analisis(cliente, [(canal, ad_id)]).get((canal, ad_id))
    clasif = {"por_que": (fila["resultado"] or {}).get("frase")} if fila and fila["estado"] == "lista" else None
    try:
        _, creado = puente.a_referente(cliente, anuncio, clasif)
    except puente.PuenteError as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash(gettext("Guardado en Referentes: desde ahí puedes recrearlo con tu producto o usarlo en un sprint.")
          if creado else gettext("Ese anuncio ya estaba en Referentes."), "ok")
    return _volver(cliente)


def pedir_copia(cliente, tienda_id=None):
    """(texto ya traducido, categoría de flash) de pedir la copia de Triple Whale (gratis): la de esa tienda o, sin
    `tienda_id`, la de cada tienda del proyecto. El llamador ya comprobó que la tienda es del proyecto. La usa
    «Actualizar ahora» de Rendimiento (`rendimiento.actualizar`, spec 2026-10-09 A5), que reemplazó a la ruta
    `sincronizar` de la pestaña vieja."""
    if not triple_whale_tiendas.obtener(cliente):
        return gettext("Triple Whale no está conectado en este proyecto."), "error"
    if tareas_tw.encolar_sync(cliente, tienda_id):
        return gettext("Trayendo las métricas de Triple Whale…"), "ok"
    return gettext("Ya se están trayendo las métricas de Triple Whale."), "warn"


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
