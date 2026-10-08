"""
Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Bloque 1: fragmentos
HTML para el grid (filtros + paginación) y la ficha, solo lectura.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
`<cliente>`; la visibilidad (global + propios) la aplica referentes.datos.
Bloque 2 agrega `recrear_form`/`recrear_adaptar`/`recrear_generar` («Recrear
con mi producto»); los créditos de generación se gastan a través del pipeline
de Crear que ya existe (`creative_flow` + `flowplus_lanzar`), no se reimplementan aquí.
"""
import json
import re
from datetime import datetime
from uuid import uuid4

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext

import catalogo_productos
from cobros import libro
from cobros import vista as vista_cobros
import creative_flow
import doctrina
from doctrina import producto as doctrina_producto
import flowplus_lanzar
import gastos
import idiomas
import marca as marca_mod
import proyectos
import tiendas
from nicho.avatares import costo_real, modelo_actual
from providers import flowplus_modelos
from referentes import datos, fuentes, lectura, recrear, traducir
from referentes.fuentes.base import ErrorFuente
from sprints import datos as sprints_datos
from tareas import referentes as tareas_referentes

bp = Blueprint("referentes", __name__, url_prefix="/cliente/<cliente>/referentes")


@bp.before_request
def _solo_mismo_origen():
    """Barrera CSRF (como Sprints, Nicho y Flow Plus): un POST que el navegador
    declara de otro sitio (Sec-Fetch-Site) no toca nada — leer, adaptar,
    generar y traer gastan (spec 2026-09-30-recrear-fiel §7)."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if request.method == "POST" and sitio and sitio not in ("same-origin", "none"):
        if request.is_json or request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"error": gettext("Pedido rechazado: no viene de esta página.")}), 403
        abort(403)
_FILTROS = ("etapa", "consciencia", "familia", "dolor", "marca", "fuente", "q")
# El placeholder del campo "Marca / link del Ad Library" invita a pegar la URL
# completa (spec §4.1 idem UI), pero solo el id numérico sirve para armar la
# ruta de Atria (`/brand-library/m<id>/ads`) — sin extraer esto, una URL
# pegada tal cual produce una ruta rota (`/brand-library/mhttps://...`) que
# igual gasta una llamada real contra Atria antes de fallar (Important 2).
_RE_VIEW_ALL_PAGE_ID = re.compile(r"view_all_page_id=(\d+)")

# Los filtros de «dolor» solo muestran los más frecuentes: con la biblioteca de
# copycoders son casi 3 000 distintos y el menú entero pesaba en cada carga de
# la página del proyecto (incidente 2026-09-28). El resto se encuentra con el
# buscador, que también mira el dolor.
MAX_DOLORES_FILTRO = 50


def contexto(cliente):
    """Lo que necesita _tab_referentes.html. Se llama desde dashboard.ver_cliente."""
    opciones = datos.opciones(cliente)
    opciones["dolores"] = opciones["dolores"][:MAX_DOLORES_FILTRO]
    return {"ref_opciones": opciones, "ref_etapas": datos.ETAPAS, "ref_consciencias": datos.CONSCIENCIAS,
            "ref_etiquetas_etapa": datos.ETIQUETAS_ETAPA, "ref_etiquetas_consciencia": datos.ETIQUETAS_CONSCIENCIA,
            "ref_etiquetas_dolor": datos.ETIQUETAS_DOLOR,
            "ref_fuentes": datos.FUENTES, "ref_copycoders_activa": proyectos.referentes_copycoders(cliente),
            "ref_copycoders_total": datos.total_copycoders()}


@bp.post("/copycoders")
def copycoders(cliente):
    """Trae (o quita) la biblioteca global de copycoders para ESTE proyecto.
    No copia ni borra nada: solo decide si se lista en Referentes y en los
    sugeridos de Sprints."""
    activa = request.form.get("activa") == "1"
    proyectos.guardar_referentes_copycoders(cliente, activa)
    if activa:
        flash(gettext("Listo: la biblioteca de copycoders ya aparece en Referentes."), "ok")
    else:
        flash(gettext("Quitamos la biblioteca de copycoders de este proyecto. Puedes volver a traerla cuando quieras."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


def filtros_desde(args):
    return {k: (args.get(k) or "").strip() for k in _FILTROS if (args.get(k) or "").strip()}


def _entero(v, defecto):
    try:
        return int(v)
    except (TypeError, ValueError):
        return defecto


@bp.get("/grid")
def grid(cliente):
    filtros = filtros_desde(request.args)
    por_pagina = min(max(1, _entero(request.args.get("por_pagina"), datos.POR_PAGINA)), 120)
    pagina = datos.listar(cliente, filtros, pagina=_entero(request.args.get("pagina"), 1), por_pagina=por_pagina)
    campana = (request.args.get("campana") or "").strip() or None
    return render_template("_referentes_grid.html", cliente=cliente, pagina=pagina, filtros=filtros, por_pagina=por_pagina,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA,
                           etiquetas_dolor=datos.ETIQUETAS_DOLOR, campana=campana)


def _producto_para(cliente, request_args_o_form):
    """El selector de «Recrear con mi producto» y el producto elegido: sin los
    archivados (2026-10-01), salvo el que se pidió por `producto_id`."""
    pedido = request_args_o_form.get("producto_id")
    productos = catalogo_productos.sin_archivados(catalogo_productos.listar(cliente, "producto"),
                                                  tiendas.activos_archivados(cliente), conservar=[pedido])
    pid = pedido or (productos[0]["id"] if productos else None)
    producto = catalogo_productos.encontrar(cliente, pid, categoria="producto") if pid else None
    return productos, producto


def _pagina_id_desde(v):
    """Acepta un id de página tal cual (solo dígitos) o un link del Ad
    Library con `view_all_page_id=<dígitos>` -- lo primero que alguien
    probablemente pegue, dado el placeholder del campo. Cualquier otro texto
    no es ni lo uno ni lo otro: se descarta a `None` para que la validación
    ya existente ("Pega un link del Ad Library o el id de la página") dispare
    sola, en vez de mandarle ese texto tal cual a Atria como si fuera un id."""
    v = (v or "").strip()
    if not v:
        return None
    m = _RE_VIEW_ALL_PAGE_ID.search(v)
    if m:
        return m.group(1)
    return v if v.isdigit() else None


def _consulta_desde(args):
    return {
        "modo": args.get("modo") if args.get("modo") in ("marca", "palabra") else "palabra",
        "pagina_id": _pagina_id_desde(args.get("pagina_id")),
        "palabra": (args.get("palabra") or "").strip() or None,
        "idioma": (args.get("idioma") or "es").strip()[:5],
        "pais": (args.get("pais") or "ALL").strip().upper()[:5],
        "formato": args.get("formato") if args.get("formato") in ("imagen", "video") else "imagen",
        "solo_activos": args.get("solo_activos") not in (None, "", "0", "false"),
        "min_dias": _entero(args.get("min_dias"), None),
        "min_variantes": _entero(args.get("min_variantes"), None),
    }


@bp.get("/traer")
def traer_form(cliente):
    fuente = request.args.get("fuente") if request.args.get("fuente") in fuentes.tipos() else (fuentes.tipos()[0] if fuentes.tipos() else None)
    tope = min(max(1, _entero(request.args.get("tope"), 200)), 2000)
    consulta = _consulta_desde(request.args)
    precio = None
    llaves_faltantes = fuentes.llaves_faltantes(fuente) if fuente else []
    modo_no_admitido = bool(fuente) and consulta["modo"] not in fuentes.modos(fuente)
    if fuente and not llaves_faltantes and not modo_no_admitido and (consulta.get("pagina_id") or consulta.get("palabra")):
        modulo = fuentes.por_tipo(fuente)
        est_fuente = modulo.estimar(consulta, tope)
        est_clasificacion = gastos.estimar("clasificacion", n=tope)
        precio = {"fuente": est_fuente, "clasificacion": est_clasificacion,
                  "total_usd": est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)}
    return render_template("_referentes_traer.html", cliente=cliente, fuentes_tipos=fuentes.tipos(),
                           fuentes_nombres=fuentes.NOMBRES, fuente=fuente, consulta=consulta, tope=tope,
                           precio=precio, llaves_faltantes=llaves_faltantes, modo_no_admitido=modo_no_admitido,
                           fuente_llaves_faltantes={t: fuentes.llaves_faltantes(t) for t in fuentes.tipos()})


@bp.post("/traer")
def traer_post(cliente):
    fuente = request.form.get("fuente")
    if fuente not in fuentes.tipos():
        flash(gettext("Elige una fuente."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    if fuentes.llaves_faltantes(fuente):
        flash(gettext("Esa fuente no está configurada."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    consulta = _consulta_desde(request.form)
    if consulta["modo"] not in fuentes.modos(fuente):
        flash(gettext("Esa fuente no admite este tipo de búsqueda; busca por palabra clave o cambia de fuente."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    if consulta["modo"] == "marca" and not consulta["pagina_id"]:
        flash(gettext("Pega un link del Ad Library o el id de la página."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    if consulta["modo"] == "palabra" and not consulta["palabra"]:
        flash(gettext("Escribe una palabra clave."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    tope = min(max(1, _entero(request.form.get("tope"), 200)), 2000)
    modulo = fuentes.por_tipo(fuente)
    try:
        est_fuente = modulo.estimar(consulta, tope)
    except ErrorFuente as e:
        flash(e.usuario, "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    est_clasificacion = gastos.estimar("clasificacion", n=tope)
    usd_estimado = est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)
    # Cobros (spec 2026-10-08 §5.2): el saldo se pide ANTES de traducir la
    # palabra (esa llamada a Claude ya se cobra al proyecto). El estimado no
    # depende de la palabra, solo del tope.
    libro.exigir(cliente, usd_estimado)
    try:
        consulta = traducir.preparar_consulta(consulta, cliente)     # palabra → inglés, idioma en
    except traducir.TraduccionInvalida as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    tareas_referentes.encolar_barrer(cliente, fuente, consulta, tope, usd_estimado, pedido_por=session.get("usuario"))
    flash(gettext("Trayendo referentes; aparecerán en «Mis barridos» a medida que avanza."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


MODOS_RECREAR = ("fiel", "libre")
# Como video (spec §12): con qué se anima la imagen fiel. Seedance 2.5 primero:
# es el único que usa la imagen como primer fotograma.
MODELOS_ANIMAR = ("seedance25", "wan3")


def _familia_de(cliente, r, idioma):
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    return dict(familia, descripcion=datos.descripcion_familia(familia, idioma)) if familia else None


def _contexto_recrear(cliente, r, producto, formato, tipo, campos, idioma, libre_como_video=False):
    """Lectura, textos y los dos prompts (fiel y variación/video) armados con
    los campos del formulario: lo mismo al pintarlo y al generar (spec
    2026-09-30-recrear-fiel §4-§5). Sin `campos_vista=1` (primera vez) los
    textos son los leídos y la casilla «traer» va prendida.
    En video la variación también pasa primero por una imagen (spec §12), así
    que su prompt es el de imagen; solo el formulario viejo de video
    (`libre_como_video`) sigue pidiendo el prompt de video con cámara y sonido."""
    lec = lectura.de(r)
    con_campos = campos.get("campos_vista") == "1"
    traer = campos.get("traer_textos") == "1" if con_campos else True
    textos = lectura.valores_de(campos, lec) if con_campos else lectura.valores_iniciales(lec)
    linea = recrear.instruccion_textos(lec, textos, traer, idioma)
    prefs_sonido = proyectos.preferencias_sonido(cliente)
    libre = recrear.armar_prompt(datos.localizado(r, idioma), _familia_de(cliente, r, idioma), producto,
                                 marca_mod.guia_efectiva(cliente), "", formato,
                                 tipo="video" if libre_como_video else "imagen",
                                 con_sonido=prefs_sonido["con_sonido"], idioma=idioma, linea_textos=linea)
    fiel = recrear.armar_prompt_fiel(lec, producto, linea, formato, idioma=idioma)
    animar = recrear.armar_prompt_animar(producto, con_sonido=prefs_sonido["con_sonido"], idioma=idioma)
    return {"lectura": lec, "traer": traer, "textos": textos, "prompt": libre, "prompt_fiel": fiel,
            "prompt_animar": animar}


def _modelo_animar(campos):
    m = campos.get("modelo_animar")
    return m if m in MODELOS_ANIMAR else MODELOS_ANIMAR[0]


def _formato_video(modelo, formato_pedido):
    """El formato de video más parecido al pedido (spec §12): Wan 3.0 no tiene
    4:5 y `ajustar_formato` caería al de por defecto (9:16, que recorta mucho);
    aquí va al más cercano (3:4). Seedance sigue a la imagen (None)."""
    formatos = flowplus_modelos.VIDEO[modelo].get("formatos") or ()
    if not formatos or formato_pedido in formatos:
        return flowplus_modelos.ajustar_formato(modelo, formato_pedido)
    try:
        ancho, alto = (int(x) for x in str(formato_pedido).split(":"))
    except ValueError:
        return flowplus_modelos.ajustar_formato(modelo, formato_pedido)
    return lectura.formato_cercano(ancho, alto, formatos) or flowplus_modelos.ajustar_formato(modelo, formato_pedido)


def _duracion_video(cliente, modelo):
    return flowplus_modelos.ajustar_duracion(modelo, proyectos.preferencias_flowplus(cliente)["duracion_defecto"])


def _precios_video(cliente, n_refs_imagen):
    """Lo que cuesta cada video de «Como video» (spec §12): una imagen (la fiel o
    la variación) más su animación con cada modelo, con la duración del proyecto."""
    con_sonido = proyectos.preferencias_sonido(cliente)["con_sonido"]

    def video(modelo):
        return gastos.estimar("video", modelo=modelo, duracion=_duracion_video(cliente, modelo), con_sonido=con_sonido)
    return {"imagen": gastos.estimar("imagen", modelo=flowplus_modelos.IMAGEN_POR_DEFECTO, n_referencias=n_refs_imagen),
            "animar": {m: video(m) for m in MODELOS_ANIMAR},
            "duracion": {m: _duracion_video(cliente, m) for m in MODELOS_ANIMAR}}


def _modos_de(campos):
    """Las imágenes marcadas («igual» y/o «variación»); sin `modos_vista=1`
    (primera vez, o un formulario de video) van las dos."""
    if campos.get("modos_vista") != "1":
        return list(MODOS_RECREAR)
    pedidos = campos.getlist("modo")
    return [m for m in MODOS_RECREAR if m in pedidos]


@bp.get("/<int:rid>/recrear")
def recrear_form(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    productos, producto = _producto_para(cliente, request.args)
    tipo = request.args.get("tipo") if request.args.get("tipo") in ("imagen", "video") else "imagen"
    formatos = flowplus_modelos.IMAGEN[flowplus_modelos.IMAGEN_POR_DEFECTO]["formatos"]
    lec = lectura.de(r)
    formato = (request.args.get("formato")
               or (lectura.formato_cercano(lec.get("ancho"), lec.get("alto"), formatos) if lec else None)
               or flowplus_modelos.FORMATO_DEFECTO)
    idioma = idiomas.de_proyecto(cliente)
    ctx = {"lectura": lec, "traer": True, "textos": lectura.valores_iniciales(lec), "prompt": "", "prompt_fiel": "",
           "prompt_animar": ""}
    precio = precios_video = None
    if producto:
        ctx = _contexto_recrear(cliente, r, producto, formato, tipo, request.args, idioma)
        n_refs = 1 + max(1, min(2, len(producto.get("referencias") or [1])))
        if tipo == "imagen":
            precio = gastos.estimar("imagen", modelo=flowplus_modelos.IMAGEN_POR_DEFECTO, n_referencias=n_refs)
        else:
            precios_video = _precios_video(cliente, n_refs)
    return render_template(
        "_referente_recrear.html", cliente=cliente, r=r, productos=productos, producto=producto, tipo=tipo,
        formato=formato, formatos=formatos, formato_elegido=request.args.get("formato_elegido") == "1",
        lectura=ctx["lectura"], traer_textos=ctx["traer"], textos=ctx["textos"], prompt=ctx["prompt"],
        prompt_fiel=ctx["prompt_fiel"], prompt_animar=ctx["prompt_animar"], modos=_modos_de(request.args),
        etiquetas_rol=lectura.ETIQUETAS_ROL, modelos_animar=MODELOS_ANIMAR, modelo_animar=_modelo_animar(request.args),
        nombres_video={m: flowplus_modelos.VIDEO[m]["nombre"] for m in flowplus_modelos.VIDEO},
        precio=precio, precios_video=precios_video, precio_adaptar=gastos.estimar("adaptar_referente"),
        precio_leer=gastos.estimar("leer_referente"))


def _registrar_lectura(cliente, rid, r, ent, sal, fallo=False):
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):     # el detalle se GUARDA: idioma del proyecto
        if fallo:
            detalle = gettext("lectura · %(familia)s · respuesta inválida", familia=r.get("familia") or "")
        else:
            detalle = gettext("lectura · %(familia)s", familia=r.get("familia") or "")
    gastos.registrar_seguro(cliente, "adaptar_referente", costo_real(ent, sal), f"referentes:leer:{rid}:{uuid4().hex[:12]}",
                            detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})


@bp.post("/<int:rid>/recrear/leer")
def recrear_leer(cliente, rid):
    """La lectura de la referencia (spec 2026-09-30-recrear-fiel §3): la pide
    el formulario al abrirse; una vez guardada, no se vuelve a pagar."""
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        return jsonify({"error": gettext("Ese referente no existe.")}), 404
    if lectura.de(r):
        return jsonify({"ok": True, "cobrado": False})
    libro.exigir(cliente, gastos.estimar("leer_referente")["usd"])     # cobros §5.2: antes de llamar a Claude
    try:
        lec, ent, sal = lectura.leer(r)
    except lectura.LecturaInvalida as e:
        if e.tokens_entrada or e.tokens_salida:
            _registrar_lectura(cliente, rid, r, e.tokens_entrada, e.tokens_salida, fallo=True)
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": gettext("No se pudo leer la referencia (%(tipo)s).", tipo=type(e).__name__)}), 502
    _registrar_lectura(cliente, rid, r, ent, sal)
    lec["ancho"], lec["alto"] = lectura.medir(r["imagen_url"])
    datos.guardar_lectura(rid, lec)
    return jsonify({"ok": True, "cobrado": True})


@bp.post("/<int:rid>/recrear/adaptar")
def recrear_adaptar(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        return jsonify({"error": gettext("Ese referente no existe.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": gettext("Cuerpo inválido.")}), 400
    producto = catalogo_productos.encontrar(cliente, cuerpo.get("producto_id"), categoria="producto") if cuerpo.get("producto_id") else None
    if not producto:
        return jsonify({"error": gettext("Elige un producto primero.")}), 400
    # Doctrina, bloque 2: la sofisticación elegida en Catálogo manda en el ángulo.
    # Revisión final #6: descartada si no es 1-5 (dato corrupto), como ideas y el guion.
    fila = tiendas.por_activo(cliente).get(catalogo_productos.producto_base(producto.get("id"))) or {}
    sof = (fila.get("extra") or {}).get("sofisticacion")
    producto = dict(producto, sofisticacion=sof if sof in doctrina.SOFISTICACIONES else None,
                    pruebas=doctrina_producto.pruebas(fila))
    idioma = idiomas.de_proyecto(cliente)
    familia = _familia_de(cliente, r, idioma)
    lec = lectura.de(r)
    crudos = cuerpo.get("textos")
    campos = {f"texto_{i}": str(v or "") for i, v in enumerate(crudos)} if isinstance(crudos, list) else {}
    libro.exigir(cliente, gastos.estimar("adaptar_referente")["usd"])     # cobros §5.2: antes de llamar a Claude
    try:
        resultado, ent, sal = recrear.adaptar(datos.localizado(r, idioma), familia, producto,
                                              str(cuerpo.get("titular") or ""), marca_mod.guia_efectiva(cliente),
                                              idioma=idioma, textos=lectura.valores_de(campos, lec),
                                              traer=cuerpo.get("traer_textos") is not False, lectura=lec)
    except recrear.AdaptacionInvalida as e:
        ent = getattr(e, "tokens_entrada", 0) or 0
        sal = getattr(e, "tokens_salida", 0) or 0
        if ent or sal:
            usd = costo_real(ent, sal)
            nombre_producto = producto["nombre"]
            with idiomas.en_idioma(idioma):     # el detalle se GUARDA: idioma del proyecto
                detalle = gettext("%(producto)s · %(familia)s · respuesta inválida",
                                  producto=nombre_producto, familia=r.get("familia") or "")
            gastos.registrar_seguro(cliente, "adaptar_referente", usd, f"referentes:adaptar:{rid}:{uuid4().hex[:12]}",
                                    detalle=detalle, proveedor="anthropic",
                                    extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": gettext("No se pudo adaptar (%(tipo)s).", tipo=type(e).__name__)}), 502
    usd = costo_real(ent, sal)
    gastos.registrar_seguro(cliente, "adaptar_referente", usd, f"referentes:adaptar:{rid}:{uuid4().hex[:12]}",
                            detalle=f"{producto['nombre']} · {r.get('familia') or ''}", proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
    return jsonify(resultado)


def _costo_recrear(cliente, tipo, legado_video, modos, referencias_urls, modelo, duracion, con_sonido, campos):
    """USD de un clic de «Recrear» (sin margen): una pieza por modo; en video
    cada una es imagen + animación (spec §12). None si algo no tiene tarifa."""
    if tipo == "video" and legado_video:
        uno = flowplus_lanzar.costo_estimado({"tipo": "video", "modelo": modelo, "duracion_objetivo": duracion,
                                              "con_sonido": con_sonido})
    else:
        uno = flowplus_lanzar.costo_estimado({"tipo": "imagen", "modelo": flowplus_modelos.IMAGEN_POR_DEFECTO,
                                              "referencias_urls": referencias_urls})
        if tipo == "video" and uno is not None:
            animar_con = _modelo_animar(campos)
            video = gastos.estimar("video", modelo=animar_con, duracion=_duracion_video(cliente, animar_con),
                                   con_sonido=con_sonido)["usd"]
            uno = None if video is None else uno + video
    return None if uno is None else round(uno * len(modos), 4)


@bp.post("/<int:rid>/recrear/generar")
def recrear_generar(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        flash(gettext("Ese referente no existe."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    tipo = request.form.get("tipo") if request.form.get("tipo") in ("imagen", "video") else "imagen"
    producto = catalogo_productos.encontrar(cliente, request.form.get("producto_id"), categoria="producto") \
        if request.form.get("producto_id") else None
    if not producto:
        flash(gettext("Elige un producto con fotos."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    titular = (request.form.get("titular") or "").strip()[:200]
    formato_pedido = request.form.get("formato") or flowplus_modelos.FORMATO_DEFECTO
    prefs_sonido = proyectos.preferencias_sonido(cliente)
    if tipo == "imagen":
        modelo = flowplus_modelos.IMAGEN_POR_DEFECTO
        formato = flowplus_modelos.ajustar_formato(modelo, formato_pedido, tipo="imagen")
        duracion_objetivo = 0
    else:
        modelo = flowplus_modelos.VIDEO_POR_DEFECTO
        duracion_objetivo = flowplus_modelos.ajustar_duracion(
            modelo, proyectos.preferencias_flowplus(cliente)["duracion_defecto"])
        formato = _formato_video(modelo, formato_pedido)
    idioma = idiomas.de_proyecto(cliente)
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))
    # Spec 2026-09-30-recrear-fiel §5: el formulario nuevo manda `campos_vista=1`
    # y el servidor arma cada prompt con lo que trae, salvo el que la persona
    # editó a mano. Sin esa marca (scripts, pruebas viejas) se usa `prompt` tal cual.
    nuevo = request.form.get("campos_vista") == "1"
    if nuevo:
        # En video, solo el formulario que muestra las casillas (`modos_vista`)
        # pide imagen + animación: uno abierto antes de §12 sigue haciendo un
        # solo video con su prompt de video.
        legado_video = tipo == "video" and request.form.get("modos_vista") != "1"
        ctx = _contexto_recrear(cliente, r, producto, formato, tipo, request.form, idioma,
                                libre_como_video=legado_video)
        modos = ["libre"] if legado_video else _modos_de(request.form)
        if not modos:
            flash(gettext("Elige al menos una imagen."), "error")
            return volver
        prompts = {}
        for m in modos:
            campo = "prompt_fiel" if m == "fiel" else "prompt"
            if request.form.get(f"{campo}_editado") == "1":
                prompts[m] = (request.form.get(campo) or "").strip()
                if not prompts[m]:
                    flash(gettext("El prompt no puede quedar vacío."), "error")
                    return volver
            else:
                prompts[m] = ctx[campo]
        prompt_animar = ctx["prompt_animar"]
        if tipo == "video" and not legado_video and request.form.get("prompt_animar_editado") == "1":
            prompt_animar = (request.form.get("prompt_animar") or "").strip()
            if not prompt_animar:
                flash(gettext("El prompt no puede quedar vacío."), "error")
                return volver
        textos = ctx["textos"] if ctx["traer"] else []
    else:
        prompt = (request.form.get("prompt") or "").strip()
        if not prompt:
            flash(gettext("El prompt no puede quedar vacío."), "error")
            return volver
        modos, prompts, textos, legado_video = ["libre"], {"libre": prompt}, [], tipo == "video"
    try:
        referencias_urls = recrear.referencias_para(cliente, r, producto)
    except Exception as e:
        flash(gettext("No se pudieron preparar las referencias (%(tipo)s).", tipo=type(e).__name__), "error")
        return volver
    angulo = None
    try:
        crudo = json.loads(request.form.get("angulo") or "null")
    except ValueError:
        crudo = None
    if isinstance(crudo, dict):
        angulo, _errores = doctrina.validar_angulo(crudo)
        angulo["origen"] = "recrear"
    with idiomas.en_idioma(idioma):     # el título se GUARDA: idioma del proyecto
        if nuevo:
            base = next((x for x in textos if x), "") or r.get("titular") or r["id"]
            titulo = gettext("Recrear: %(titular)s", titular=base)
            sufijos = {"fiel": gettext("igual"), "libre": gettext("variación")}
        else:
            titulo = titular or gettext("Recrear: %(titular)s", titular=r.get("titular") or r["id"])
            sufijos = {}
    # Cobros (spec 2026-10-08 §5): todo lo que este clic va a generar (cada
    # imagen y, en video, su animación) se pide junto ANTES de crear la primera
    # sesión; cada lanzamiento reserva lo suyo al encolar.
    libro.exigir(cliente, _costo_recrear(cliente, tipo, legado_video, modos, referencias_urls, modelo,
                                         duracion_objetivo, prefs_sonido["con_sonido"], request.form))
    lanzados = 0
    for m in modos:
        nombre = f"{titulo} · {sufijos[m]}" if nuevo and not legado_video else titulo
        tipo_m, modelo_m, formato_m, duracion_m = tipo, modelo, formato, duracion_objetivo
        animar = tipo == "video" and not legado_video
        if animar:
            # En video (spec §12) cada pieza es primero una imagen (la fiel o la
            # variación); el worker la anima en cuanto queda lista
            # (`recrear.lanzar_animacion`).
            tipo_m, modelo_m, duracion_m = "imagen", flowplus_modelos.IMAGEN_POR_DEFECTO, 0
            formato_m = flowplus_modelos.ajustar_formato(modelo_m, formato_pedido, tipo="imagen")
        cf_id = creative_flow.crear(cliente, [], [producto["nombre"]], [], nombre,
                                    duracion_m, "", "A", referencias_urls=referencias_urls, platforms=[])
        campos = dict(prompt_relleno=prompts[m], aspect_ratio=formato_m, tipo=tipo_m, modelo=modelo_m,
                      con_sonido=prefs_sonido["con_sonido"], sonido_texto="", musica_estilo="",
                      calidad="final", referente_id=rid)
        if animar:
            animar_con = _modelo_animar(request.form)
            with idiomas.en_idioma(idioma):     # el título se GUARDA: idioma del proyecto
                palabra_video = gettext("video")
            titulo_video = f"{nombre} · {palabra_video}"
            campos["animar_despues"] = {
                "modelo": animar_con, "duracion": _duracion_video(cliente, animar_con),
                "formato": _formato_video(animar_con, formato_pedido),
                "prompt": prompt_animar, "con_sonido": prefs_sonido["con_sonido"], "titulo": titulo_video}
        if nuevo:
            campos["recrear_modo"] = m
        if angulo:
            campos["angulo"] = dict(angulo)
        creative_flow.actualizar(cliente, cf_id, **campos)
        entry = creative_flow.cargar(cliente)[cf_id]
        if flowplus_lanzar.lanzar(cliente, cf_id, entry):
            lanzados += 1
    if lanzados == len(modos):
        if tipo == "video" and not legado_video:
            flash(gettext("Generando desde el referente… cada video arranca solo cuando su imagen esté lista."), "ok")
        elif tipo == "imagen" and len(modos) > 1:
            flash(gettext("Generando %(n)s imágenes desde el referente…", n=len(modos)), "ok")
        else:
            flash(gettext("Generando desde el referente…"), "ok")
    else:
        flash(gettext("Ya había algo generándose para esta sesión."), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@bp.get("/<int:rid>/ficha")
def ficha(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    idioma = idiomas.activo()
    r = datos.localizado(r, idioma)
    if familia:
        familia = dict(familia, descripcion=datos.descripcion_familia(familia, idioma))
    return render_template("_referente_ficha.html", cliente=cliente, r=r, familia=familia,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA,
                           etiquetas_dolor=datos.ETIQUETAS_DOLOR, usos=recrear.usos(cliente, rid))


def _vista_barrido(b):
    """Lo que «Mis barridos» muestra de un barrido, en texto normal (nada de
    `en_cola`, fechas ISO ni `12/50`). La fecha es la hora local del servidor
    (`db.ahora`, TZ=America/Bogota en el VPS)."""
    creado = b.get("creado_en") or ""
    try:
        fecha = idiomas.fecha_corta(datetime.fromisoformat(creado[:16]), con_hora=True)
    except (ValueError, IndexError):
        fecha = creado
    estado, tono = datos.ETIQUETAS_ESTADO_BARRIDO.get(b.get("estado"), (b.get("estado") or "", "en-curso"))
    estado = idiomas.traducir(estado)
    consulta = b.get("consulta") or {}
    nombre_fuente = idiomas.traducir(fuentes.NOMBRES.get(b.get("fuente"), b.get("fuente") or ""))
    detalle = [nombre_fuente.split(" (")[0].capitalize(),
               gettext("Video") if consulta.get("formato") == "video" else gettext("Imagen")]
    if consulta.get("pais") and consulta.get("pais") != "ALL":
        detalle.append(consulta["pais"])
    if consulta.get("modo") == "marca":
        busqueda, enlace = gettext("Una marca"), ("https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
                                                 f"&view_all_page_id={consulta.get('pagina_id') or ''}")
    else:
        palabra = consulta.get("palabra") or ""
        busqueda, enlace = gettext("«%(palabra)s»", palabra=palabra), None
        original = consulta.get("palabra_original")
        if original and original.strip().lower() != palabra.strip().lower():
            # lo escrito → lo buscado en inglés
            busqueda = gettext("«%(original)s» → «%(buscado)s»", original=original, buscado=palabra)
    return {"fecha": fecha, "estado": estado, "tono": tono, "busqueda": busqueda, "enlace": enlace,
            "detalle": " · ".join(d for d in detalle if d)}


@bp.get("/barridos")
def barridos(cliente):
    lista = datos.barridos(cliente=cliente)
    for b in lista:
        b["vista"] = _vista_barrido(b)
        b["trabajo"] = tareas_referentes.trabajo_barrer(b["id"])
        # «Reintentar imágenes» solo tiene sentido -- y solo se ofrece -- si
        # de verdad hay algo en error que reintentar (mismo criterio que
        # «Clasificar pendientes» con b.pendientes, Important 6.3): antes se
        # mostraba siempre que no hubiera trabajo en curso, y un clic sin
        # nada que reintentar igual reseteaba el barrido a un estado que no
        # es error, borrando su aviso.
        b["imagenes_error"] = datos.contar_imagenes_de_barrido(b["id"])[2]
        # «Clasificar pendientes» re-factura (spec §11): el precio va en el
        # botón igual que en cualquier otro click pagado del panel (Critical 1).
        b["precio_clasificar"] = gastos.estimar("clasificacion", n=b["pendientes"])["texto"] if b["pendientes"] else None
        if vista_cobros.ver_cobrado_aqui(cliente):
            # «lo que costó»: a un cliente de un proyecto que cobra, lo cobrado por los trabajos de este
            # barrido (traer y clasificar comparten job_id, base o base + SUFIJO_CONT; cobros §7).
            base = tareas_referentes.job_id_barrer(b["id"])
            b["usd_real"] = vista_cobros.cobrado_donde(cliente, jobs=(base, base + tareas_referentes.SUFIJO_CONT))
    return render_template("_referentes_barridos.html", cliente=cliente, barridos=lista)


def _barrido_del_cliente_o_404(cliente, bid):
    b = datos.barrido(bid)
    if not b or b.get("cliente") != cliente:
        abort(404)
    return b


@bp.post("/<int:bid>/clasificar_pendientes")
def clasificar_pendientes(cliente, bid):
    _barrido_del_cliente_o_404(cliente, bid)
    if tareas_referentes.encolar_clasificar_pendientes(cliente, bid):
        flash(gettext("Clasificando lo pendiente; la lista se actualiza sola."), "ok")
    else:
        flash(gettext("Ya hay algo en curso para este barrido."), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


@bp.post("/<int:bid>/reintentar_imagenes")
def reintentar_imagenes(cliente, bid):
    _barrido_del_cliente_o_404(cliente, bid)
    if tareas_referentes.encolar_reintentar_imagenes(cliente, bid):
        flash(gettext("Reintentando las imágenes que fallaron."), "ok")
    else:
        flash(gettext("Ya hay algo en curso para este barrido."), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="referentes"))


@bp.get("/<int:rid>/usar_en_sprint")
def usar_en_sprint(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    elegibles = []
    for sp in sprints_datos.sprints(cliente):
        if sp["estado"] not in ("planeando", "referencias"):
            continue
        for c in sp["campanas"]:
            elegibles.append({"sprint_nombre": sp["nombre"], "campana_id": c["id"],
                              "campana_n": int(c["orden"]) + 1, "funnel": c["funnel"],
                              "persona_nombre": c.get("persona_nombre")})
    return render_template("_referente_usar_en_sprint.html", cliente=cliente, r=r, elegibles=elegibles,
                           etiquetas_funnel=sprints_datos.FUNNELS_NOMBRE)
