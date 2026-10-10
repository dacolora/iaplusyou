# sprints/rutas.py
"""
Rutas de la pestaña Sprints (Blueprint `sprints`, prefijo
/cliente/<cliente>/sprints). Solo validan, delegan a sprints.datos /
sprints.estado / tareas.sprints y redirigen; la lógica vive en esos módulos.
`dashboard._guard_por_cliente` protege estas rutas igual que las demás porque
la URL lleva <cliente>. `contexto(cliente)` es lo que `ver_cliente` agrega
al render de cliente.html para la pestaña.
"""
import json
import os
from datetime import date
from urllib.parse import urlencode

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext

import catalogo_productos
from cobros import libro
import creative_flow
import db
import doctrina
import gastos
import idiomas
import proyectos
import tiendas
import trabajos
from doctrina import revisor as doctrina_revisor
from idiomas import N_
from providers import flowplus_modelos
from referentes import datos as referentes_datos
from referentes import sugerir as referentes_sugerir
from sprints import (analisis, archivos, calendario, datos, entrega, estado, ideas, produccion, progreso,
                     revision as revision_mod, tablero)
from tareas import sprints as tareas_sprints

bp = Blueprint("sprints", __name__, url_prefix="/cliente/<cliente>/sprints")


@bp.before_request
def _solo_mismo_origen():
    """Barrera CSRF (como la de Flow Plus y el editor): un POST que el navegador
    declara de otro sitio (Sec-Fetch-Site) no toca nada."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if request.method == "POST" and sitio and sitio not in ("same-origin", "none"):
        if _quiere_json() or request.is_json:
            return jsonify({"ok": False, "error": gettext("Pedido rechazado: no viene de esta página.")}), 403
        abort(403)


# ------------------------------------------------------------ helpers ---

def _volver(cliente, sid=None, cid=None):
    if cid is not None:
        return redirect(url_for("sprints.campana_ver", cliente=cliente, sid=sid, cid=cid))
    if sid is not None:
        return redirect(url_for("sprints.ver", cliente=cliente, sid=sid))
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="sprints"))


def _quiere_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _entero(campo, defecto=0):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(gettext("«%(campo)s» debe ser un número entero.", campo=campo))


def _mood_desde_form():
    return {"paleta": _partir(request.form.get("paleta")), "luz": (request.form.get("luz") or "").strip(),
            "elementos": _partir(request.form.get("elementos"))}


def _productos(cliente):
    """Retorna productos con estructura de variantes si aplica."""
    productos_planos = catalogo_productos.listar(cliente, "producto")
    productos_dict = {}

    for p in productos_planos:
        pid = p["id"]
        if "/" in pid:
            # Producto con variante: "horiginal/beige"
            base, variante = pid.split("/", 1)
            if base not in productos_dict:
                productos_dict[base] = {
                    "id": base,
                    "nombre": p["nombre"].rsplit(" — ", 1)[0] if " — " in p["nombre"] else p["nombre"],
                    "descripcion": p.get("descripcion") or "",
                    "variantes": {}
                }
            productos_dict[base]["variantes"][variante] = {
                "id": pid,
                "nombre": p["nombre"],
                "descripcion": p.get("descripcion") or "",
                "representativa_url": p.get("representativa_url")
            }
        else:
            # Producto sin variantes (estructura antigua)
            if pid not in productos_dict:
                productos_dict[pid] = {
                    "id": pid,
                    "nombre": p["nombre"],
                    "descripcion": p.get("descripcion") or "",
                    "representativa_url": p.get("representativa_url")
                }

    return list(productos_dict.values())


@bp.context_processor
def _precios_sprints():
    return {"precio_analisis_sprint": gastos.estimar("analizar_referencia")["texto"],
            "error_analisis_sprint": analisis.error_visible}


def contexto(cliente):
    """Lo que necesita _tab_sprints.html. Se llama desde dashboard.ver_cliente."""
    lista = []
    for sp in datos.sprints(cliente):
        sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
        lista.append(sp)
    # El sprint no lleva país (es para todos): el «Momento del mes» sale del
    # calendario del proyecto (el país de Temporadas).
    pais = proyectos.pais(cliente)
    inicio, fin = tablero.mes_siguiente(date.today())
    anio = int(inicio[:4])
    return {
        **_precios_sprints(),
        "sprints_lista": lista,
        "pais_calendario": pais,
        "presets_temporadas": calendario.presets(pais, anio),
        "calendario_fallback": not calendario.tiene_calendario(pais),
        "inicio_defecto": inicio,
        "fin_defecto": fin,
        "hoy": date.today().isoformat(),
    }


# ----------------------------------------------------------- personas ---

def _campos_persona():
    return dict(resumen=request.form.get("resumen"), descripcion=request.form.get("descripcion"),
                edad_rango=request.form.get("edad_rango"), tono=request.form.get("tono"),
                senales_visuales=_partir(request.form.get("senales_visuales")),
                palabras_clave=_partir(request.form.get("palabras_clave")), color=request.form.get("color") or None)


@bp.post("/personas")
def persona_crear(cliente):
    """Crea una persona manual. Desde el panel («Crear persona rápida») llega
    por fetch con nombre y una línea, y responde JSON."""
    try:
        pid = datos.crear_persona(cliente, request.form.get("nombre"), **_campos_persona())
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente)
    if _quiere_json():
        return jsonify({"ok": True, "id": pid, "nombre": datos.persona(cliente, pid)["nombre"]})
    flash(gettext("Persona creada."), "ok")
    return _volver(cliente)


@bp.post("/personas/<int:pid>")
def persona_editar(cliente, pid):
    try:
        campos = {k: v for k, v in _campos_persona().items() if request.form.get(k) is not None}
        if request.form.get("nombre") is not None:
            campos["nombre"] = request.form.get("nombre")
        if not datos.actualizar_persona(cliente, pid, **campos):
            flash(gettext("Esa persona no existe."), "error")
        else:
            flash(gettext("Persona guardada."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/personas/<int:pid>/conciencia")
def persona_conciencia(cliente, pid):
    """Doctrina, bloque 2 (§4.1): «Qué tanto sabe» de la persona, elegido a
    mano en la página de ideas de una campaña. Guarda
    `persona.extra.conciencia.nivel` (conserva el `detalle` que traiga de
    Nicho); un nivel vacío («Que Claude lo decida») lo quita. JSON."""
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": gettext("El cuerpo debe ser un objeto JSON.")}), 400
    p = datos.persona(cliente, pid)
    if not p:
        return jsonify({"ok": False, "error": gettext("Esa persona no existe.")}), 404
    crudo = cuerpo.get("nivel")
    nivel = doctrina.normalizar_consciencia(crudo)
    if crudo and not nivel:
        return jsonify({"ok": False, "error": gettext("Ese nivel no existe.")}), 400
    extra = dict(p.get("extra") or {})
    conciencia = dict(extra.get("conciencia") or {}) if isinstance(extra.get("conciencia"), dict) else {}
    if nivel:
        conciencia.update(nivel=nivel, origen="manual")
    else:
        conciencia.pop("nivel", None)
        conciencia.pop("origen", None)
    if conciencia:
        extra["conciencia"] = conciencia
    else:
        extra.pop("conciencia", None)
    datos.actualizar_persona(cliente, pid, extra=extra)
    return jsonify({"ok": True, "nivel": nivel})


@bp.post("/personas/<int:pid>/archivar")
def persona_archivar(cliente, pid):
    datos.archivar_persona(cliente, pid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/personas/sugerir")
def personas_sugerir(cliente):
    try:
        cuantas = min(5, max(1, _entero("cuantas", 3)))
        if tareas_sprints.encolar_sugerir(cliente, cuantas):
            flash(gettext("Claude está proponiendo personas; aparecerán aquí en unos segundos."), "ok")
        else:
            flash(gettext("Ya hay una sugerencia en curso."), "error")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


# --------------------------------------------------------- temporadas ---

@bp.post("/temporadas")
def temporada_crear(cliente):
    try:
        datos.crear_temporada(cliente, request.form.get("nombre"), request.form.get("inicio"), request.form.get("fin"),
                              contexto=request.form.get("contexto"), mood_visual=_mood_desde_form(),
                              tipo=request.form.get("tipo") or "propia")
        flash(gettext("Temporada creada."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>")
def temporada_editar(cliente, tid):
    try:
        campos = {}
        for k in ("nombre", "inicio", "fin", "contexto", "tipo"):
            if request.form.get(k) is not None:
                campos[k] = request.form.get(k)
        if any(request.form.get(k) is not None for k in ("paleta", "luz", "elementos")):
            campos["mood_visual"] = _mood_desde_form()
        if not datos.actualizar_temporada(cliente, tid, **campos):
            flash(gettext("Esa temporada no existe."), "error")
        else:
            flash(gettext("Temporada guardada."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>/archivar")
def temporada_archivar(cliente, tid):
    datos.archivar_temporada(cliente, tid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/temporadas/adoptar")
def temporada_adoptar(cliente):
    try:
        calendario.adoptar(cliente, request.form.get("clave") or "", pais=proyectos.pais(cliente),
                           anio=request.form.get("anio") or None)
        flash(gettext("Temporada agregada desde el calendario."), "ok")
    except (datos.ErrorDatos, ValueError) as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/pais")
def calendario_pais(cliente):
    try:
        proyectos.guardar_pais(cliente, request.form.get("pais"))
    except ValueError as e:
        flash(str(e), "error")
    return _volver(cliente)


# ------------------------------------------------------------ sprints ---

def _sprint_o_404(cliente, sid):
    sp = estado.recalcular(cliente, sid)
    if not sp:
        abort(404)
    return sp


def _campana_o_404(cliente, sid, cid):
    c = datos.campana(cliente, cid)
    if not c or c["sprint_id"] != sid:
        abort(404)
    return c


def _momento_desde(cliente, valor, pais, inicio):
    """Valor del selector «Momento del mes» -> lo que guarda `datos`: "" es
    ninguno, "propio:<texto>" es uno escrito a mano y cualquier otra cosa es
    la clave de un preset del calendario del país (año del inicio del sprint)."""
    valor = (valor or "").strip() if isinstance(valor, str) else ""
    if not valor:
        return None
    if valor.startswith("propio:"):
        return valor[len("propio:"):]
    try:
        anio = int(str(inicio)[:4])
    except ValueError:
        anio = date.today().year
    p = next((x for x in calendario.presets(pais or proyectos.pais(cliente), anio) if x["clave"] == valor), None)
    if not p:
        raise datos.ErrorDatos(gettext("Ese momento del calendario no existe."))
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        p = calendario.traducido(p)
    return {k: p[k] for k in ("clave", "nombre", "contexto", "inicio", "fin", "mood_visual")}


# ------------------------------------------------------------ tablero ---

# Sin «pais» ni «idioma» desde 2026-09-27: el sprint es para todos los países.
CAMPOS_SPRINT = ("nombre", "inicio", "fin", "marcas", "momento")


def _productos_planos(cliente):
    """Una opción por variante («HOriginal — Beige»): la lista del catálogo tal cual."""
    return catalogo_productos.listar(cliente, "producto")


def _fotos_catalogo_pendientes(cliente, producto, refs):
    existentes = {r["url"] for r in refs}
    base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    carpeta = catalogo_productos.CATEGORIAS["producto"]["carpeta"]
    nuevas = []
    for nombre in (producto or {}).get("imagenes") or []:
        url = f"{base}/clientes/{cliente}/{carpeta}/{producto['id']}/{nombre}"
        if url not in existentes:
            nuevas.append((nombre, url))
            existentes.add(url)
    return nuevas


def _precio_fotos(cliente, producto, refs):
    n = len(_fotos_catalogo_pendientes(cliente, producto, refs))
    costo = gastos.estimar("analizar_referencia")["usd"]
    return {"n": n, "texto": gastos.texto_precio(costo * n if costo is not None else None)}


def _campana_tablero(cliente, sp, c, productos_por_id):
    """Lo que la tarjeta y el panel muestran de una campaña."""
    c["progreso"] = progreso.progreso_campana(c)
    c["siguiente"] = tablero.siguiente_paso(c)
    c["efectivos"] = datos.efectivos(sp, c)
    c["producto"] = productos_por_id.get(c["catalogo_id"])
    c["referencias_lista"] = datos.referencias(cliente, c["id"])
    c["fotos_catalogo"] = _precio_fotos(cliente, c["producto"], c["referencias_lista"])
    c["consciencia_nombre"] = doctrina.CONSCIENCIAS_NOMBRE.get(c.get("consciencia") or "")
    return c


def _aviso_identica(cliente, cid):
    iguales = datos.campanas_identicas(cliente, cid)
    if not iguales:
        return None
    numeros = ", ".join(str(n) for n in iguales)
    return gettext("Ojo: la campaña %(numeros)s tiene la misma persona, producto, etapa, consciencia y formato. "
                   "Si es a propósito, cambia algo para que no salgan piezas repetidas.", numeros=numeros)


CAMPOS_CAMPANA = ("persona_id", "catalogo_id", "funnel", "consciencia", "dolor", "familias",
                  "marcas", "n_videos", "n_imagenes", "referencias_objetivo")
# Cambiar estos datos cambia más que la tarjeta (familias sugeridas, lo heredado,
# los sugeridos, los enlaces): el panel se vuelve a cargar entero.
CAMPOS_RECARGAN_PANEL = ("persona_id", "catalogo_id", "funnel", "consciencia", "familias", "marcas",
                         "referencias_objetivo")


def _campana_del_sprint(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = next((x for x in sp["campanas"] if x["id"] == cid), None)
    if not c:
        abort(404)
    return sp, c


def _enlaces(cliente, sp, c):
    """«Buscar en la biblioteca» (grid en modo selección, ya filtrado por etapa
    y consciencia) y «Traer nuevos de Meta» (formulario prellenado con país,
    idioma y la primera marca con página, o el producto como palabra clave)."""
    ef = c.get("efectivos") or datos.efectivos(sp, c)
    filtros = {"etapa": (c.get("funnel") or "tof").upper(), "campana": c["id"]}
    cons = referentes_sugerir.consciencia_en(c.get("consciencia"))
    if cons:
        filtros["consciencia"] = cons
    # Un sprint sin país (todos) no manda país: «Traer referentes» queda en «Todos los países».
    traer = {"campana": c["id"], "idioma": ef["idioma"]}
    if ef["pais"]:
        traer["pais"] = ef["pais"]
    con_pagina = next((m for m in ef["marcas"] if m.get("pagina_id")), None)
    if con_pagina:
        traer.update(modo="marca", pagina_id=con_pagina["pagina_id"])
    else:
        producto = (c.get("producto") or {}).get("nombre") or c["catalogo_id"]
        traer.update(modo="palabra", palabra=producto.split(" — ")[0])
    base = url_for("ver_cliente", cliente=cliente)
    return {"biblioteca": f"{base}#referentes?{urlencode(filtros)}", "traer": f"{base}#referentes?{urlencode(traer)}"}


def _volver_campana(cliente, sid, cid):
    """Las acciones de referencias vuelven al panel del tablero cuando se
    pidieron desde ahí (`volver=tablero`), si no a la página de la campaña."""
    if request.form.get("volver") == "tablero":
        return redirect(url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid))
    return _volver(cliente, sid, cid)


def _volver_panel(cliente, sid, cid, paso):
    """Vuelve al tablero con el panel de esa campaña abierto en esa pestaña."""
    return redirect(url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid, paso=paso))


def _contexto_ideas(cliente, c):
    """Lo que muestra la pestaña Ideas del panel (entrega 2 del tablero)."""
    vivas = [i for i in c["ideas"] if i["estado_idea"] != "descartada"]
    faltan_v, faltan_i = ideas.faltantes(c)
    por_generar = [i for i in vivas if i["estado_idea"] == "aprobada" and i["sin_sesion"]]
    conteo = {"planeadas": int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0),
              "aprobadas": sum(1 for i in vivas if i["estado_idea"] == "aprobada"),
              "videos_aprobados": sum(1 for i in vivas if i["tipo"] == "video" and i["estado_idea"] == "aprobada"),
              "imagenes_aprobadas": sum(1 for i in vivas if i["tipo"] == "imagen" and i["estado_idea"] == "aprobada"),
              "propuestas": sum(1 for i in vivas if i["estado_idea"] == "propuesta"),
              "faltan_videos": faltan_v, "faltan_imagenes": faltan_i,
              "por_generar": len(por_generar),
              "por_generar_videos": sum(1 for i in por_generar if i["tipo"] == "video"),
              "por_generar_imagenes": sum(1 for i in por_generar if i["tipo"] == "imagen")}
    job = tareas_sprints.job_id_ideas(cliente, c["id"])
    return {
        "ideas_vivas": vivas,
        "ideas_descartadas": [i for i in c["ideas"] if i["estado_idea"] == "descartada"],
        "conteo_ideas": conteo,
        "precios_ideas": {"faltan": gastos.estimar("proponer_ideas", n=faltan_v + faltan_i)["texto"],
                          "mas": gastos.estimar("proponer_ideas", n=3)["texto"],
                          "otra": gastos.estimar("proponer_ideas", n=1)["texto"],
                          "reescribir": gastos.estimar("reescribir_idea")["texto"]},
        "trabajo_ideas": {"job_id": job} if trabajos.en_curso(job) else None,
        "reescribiendo": {i["id"]: tareas_sprints.job_id_reescribir(cliente, i["id"]) for i in vivas
                          if trabajos.en_curso(tareas_sprints.job_id_reescribir(cliente, i["id"]))},
        "enfoques": flowplus_prompt_enfoques(),
        "referencias_por_id": {r["id"]: r for r in (c.get("referencias_lista") or datos.referencias(cliente, c["id"]))},
        **_contexto_lote(cliente),
    }


def _costo_regenerar(cliente, c, p, modelo_video, modelo_imagen, musica_estilo=""):
    """Lo que cuesta reintentar o regenerar la pieza: con SU modelo (reintentar
    relanza su sesión y regenerar la duplica con el mismo modelo), con la
    duración recortada al rango de ese modelo. Si el modelo de la pieza ya no
    está en el registro, el del proyecto. None si no hay estimado: el botón
    dice «precio no disponible», nunca «US$ 0»."""
    es_video = p["tipo"] == "video"
    registro = flowplus_modelos.VIDEO if es_video else flowplus_modelos.IMAGEN
    modelo = p.get("modelo") if p.get("modelo") in registro else (modelo_video if es_video else modelo_imagen)
    try:
        if es_video:
            # Con el sonido que eligió la sesión (Kling cobra aparte el audio nativo).
            con_sonido = True if p.get("con_sonido") is None else bool(p["con_sonido"])
            est = gastos.estimar("video", modelo=modelo, duracion=produccion._duracion(p, modelo),
                                 con_sonido=con_sonido, musica_estilo=musica_estilo)
        else:
            est = flowplus_modelos.estimate_imagen(modelo, n_referencias=produccion._n_referencias(cliente, c))
        usd = float((est or {}).get("usd") or 0.0)
    except Exception:  # noqa: BLE001 — sin estimado no se inventa un precio
        return None
    return round(usd, 4) if usd > 0 else None


def _piezas_de(cliente, c, modelo_video, modelo_imagen, sesiones=None):
    """Piezas con sesión de una campaña, con su costo de regeneración
    (estimado gratis, el mismo que muestra el botón antes de gastar) y el
    estado de la revisión de la doctrina de su sesión (bloque 3). `sesiones`:
    las de Crear ya cargadas, para no recargarlas por campaña."""
    if sesiones is None:
        sesiones = creative_flow.cargar(cliente)
    salida = []
    for p in c["piezas"]:
        entry = sesiones.get(p.get("cf_id")) or {}
        salida.append({**p, "campana_n": int(c["orden"]) + 1, "persona_nombre": c["persona_nombre"],
                       "temporada_nombre": c["temporada_nombre"], "catalogo_id": c["catalogo_id"],
                       "funnel": c.get("funnel") or "tof",
                       "costo_regenerar": _costo_regenerar(cliente, c, p, modelo_video, modelo_imagen,
                                                            entry.get("musica_estilo") or ""),
                       "doctrina": doctrina_revisor.resumen_galeria(entry.get("revision_doctrina"),
                                                                    entry.get("video_url"))})
    return salida


def _piezas_revision(cliente, sp):
    """Piezas con sesión de todas las campañas del sprint."""
    mv, mi = produccion.modelos(cliente)
    sesiones = creative_flow.cargar(cliente)
    return [p for c in sp["campanas"] for p in _piezas_de(cliente, c, mv, mi, sesiones=sesiones)]


def _contexto_piezas(cliente, sp, c):
    """Lo que muestra la pestaña Piezas del panel (entrega 2 del tablero)."""
    mv, mi = produccion.modelos(cliente)
    piezas = _piezas_de(cliente, c, mv, mi)
    resumen = next((x for x in produccion.progreso(cliente, sp["id"])["campanas"] if x["id"] == c["id"]), {})
    vivas = any(produccion.pieza_viva(p) or (p.get("estado") in revision_mod.TERMINADAS and not p.get("qa"))
                for p in piezas)
    pasaron_qa = sum(1 for p in piezas if p.get("revision") == "pendiente" and p.get("estado") in revision_mod.TERMINADAS
                     and (p.get("qa") or {}).get("veredicto") == "pasa")
    return {"piezas": piezas, "resumen_piezas": resumen, "piezas_vivas": vivas, "pasaron_qa": pasaron_qa,
            "checks": CHECKS_QA}


@bp.get("/<int:sid>/campanas/<int:cid>/panel")
def campana_panel(cliente, sid, cid):
    """Panel lateral de una campaña (fragmento por fetch). Abrirlo no gasta nada."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    productos = _productos_planos(cliente)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in productos})
    # El selector no ofrece productos archivados, salvo el de esta campaña.
    productos = catalogo_productos.sin_archivados(productos, tiendas.activos_archivados(cliente),
                                                  conservar=[c["catalogo_id"]])
    personas_ = datos.personas(cliente)
    if c["persona_id"] not in {p["id"] for p in personas_}:
        archivada = datos.persona(cliente, c["persona_id"])
        if archivada:
            personas_.append(archivada)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in c["referencias_lista"]} - {None}
    sugerencias_ia = (c.get("extra") or {}).get("sugerencias_ia") or []
    referentes_ia = referentes_datos.por_ids(cliente, [s.get("referente_id") for s in sugerencias_ia])
    candidatos_ia = []
    for item in sugerencias_ia:
        ref = referentes_ia.get(item.get("referente_id"))
        if ref and ref["id"] not in ya_ids:
            candidatos_ia.append({**ref, "razon": item.get("razon") or ""})
    familias = sorted(referentes_datos.familias(cliente), key=lambda f: (-int(f.get("n") or 0), f["nombre"]))
    sugeridas = referentes_datos.familias_frecuentes(cliente, etapa=(c.get("funnel") or "tof").upper(),
                                                    consciencia=referentes_sugerir.consciencia_en(c.get("consciencia")))
    job = tareas_sprints.job_id_sugerir_biblioteca(cliente, cid)
    fila_producto = tiendas.por_activo(cliente).get(catalogo_productos.producto_base(c["catalogo_id"])) or {}
    sof = (fila_producto.get("extra") or {}).get("sofisticacion")
    return render_template(
        "_sprint_panel.html", cliente=cliente, sprint=sp, c=c, personas=personas_, productos=productos,
        consciencias=doctrina.CONSCIENCIAS_NOMBRE, funnels=datos.FUNNELS_NOMBRE,
        sugerencias_dolor=tablero.sugerencias_dolor(datos.persona(cliente, c["persona_id"])),
        familias=familias, familias_sugeridas=[f for f in sugeridas if f not in (c.get("familias") or [])],
        marcas_texto=tablero.marcas_texto(c.get("marcas")), candidatos_ia=candidatos_ia,
        trabajo_sugerir_ia={"job_id": job} if trabajos.en_curso(job) else None,
        precio_sugerir_ia=gastos.estimar("sugerir_ia"), aviso=_aviso_identica(cliente, cid),
        enlaces=_enlaces(cliente, sp, c),
        paso=tablero.resolver_paso(request.args.get("paso"), c), pestanas=tablero.pestanas(c),
        sof_producto=sof if sof in doctrina.SOFISTICACIONES else None, intenciones=datos.INTENCIONES_NOMBRE,
        **_contexto_ideas(cliente, c), **_contexto_piezas(cliente, sp, c))


@bp.get("/<int:sid>/campanas/<int:cid>/piezas")
def campana_piezas(cliente, sid, cid):
    """Solo la pestaña Piezas: el panel la vuelve a pedir cada 8 s mientras
    algo se genera o espera QA. No gasta nada."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    return render_template("_sprint_panel_piezas.html", cliente=cliente, sprint=sp, c=c,
                           **_contexto_piezas(cliente, sp, c))


@bp.get("/<int:sid>/campanas/<int:cid>/sugeridos")
def campana_sugeridos(cliente, sid, cid):
    """Sugeridos gratis (sin Claude) según el enfoque de la campaña.
    `?todas=1` deja de filtrar por etapa (el «aflojar filtros» del estado vacío)."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    refs = datos.referencias(cliente, cid)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in refs} - {None}
    ef = c["efectivos"]
    todas = request.args.get("todas") == "1"
    # Igual que la tarea de «Sugerir con IA» (tareas/sprints.py): sin
    # consciencia propia, cae a la del Nicho de la persona (F9, ronda final) --
    # una campaña creada antes de que Nicho investigara a su persona no debe
    # quedarse sin ese filtro para siempre.
    persona_c = datos.persona(cliente, c["persona_id"]) or {}
    enfoque = {"etapa": None if todas else (c.get("funnel") or "tof").upper(),
               "consciencia": c.get("consciencia") or datos.consciencia_de_persona(persona_c),
               "familias": c.get("familias") or [], "idioma": ef["idioma"], "marcas": ef["marcas"]}
    faltan = int(c.get("referencias_objetivo") or 1) - len(refs)
    r = referentes_sugerir.sugerir_campana(cliente, enfoque, ya_ids, min(8, faltan) if faltan > 0 else 4)
    c["producto"] = next((p for p in _productos_planos(cliente) if p["id"] == c["catalogo_id"]), None)
    return render_template("_sprint_sugeridos.html", cliente=cliente, sprint=sp, c=c, sugeridos=r["items"],
                           aflojado=r["aflojado"] + (["etapa"] if todas else []), todas=todas,
                           precio_sugerir_ia=gastos.estimar("sugerir_ia"), enlaces=_enlaces(cliente, sp, c))


@bp.post("/<int:sid>/campanas/<int:cid>/campo")
def campana_campo(cliente, sid, cid):
    """Autoguardado de un dato del panel: `datos` valida, y se devuelve la
    tarjeta ya actualizada y si el panel debe recargarse."""
    _campana_o_404(cliente, sid, cid)
    cuerpo = _json_cuerpo()
    if not cuerpo or cuerpo.get("campo") not in CAMPOS_CAMPANA:
        return jsonify({"ok": False, "error": gettext("Ese dato no se puede editar aquí.")}), 400
    campo, valor = cuerpo["campo"], cuerpo.get("valor")
    if not _valor_simple(campo, valor):
        return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
    try:
        if campo == "catalogo_id" and valor not in {p["id"] for p in _productos_planos(cliente)}:
            raise datos.ErrorDatos(gettext("Ese producto no está en el catálogo."))
        datos.actualizar_campana(cliente, cid, **{campo: valor})
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    sp = estado.recalcular(cliente, sid)
    c = next(x for x in sp["campanas"] if x["id"] == cid)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in _productos_planos(cliente)})
    return jsonify({"ok": True, "aviso": _aviso_identica(cliente, cid), "resumen": tablero.resumen(sp),
                    "tarjeta": render_template("_sprint_tarjeta.html", cliente=cliente, sprint=sp, c=c),
                    "recargar_panel": campo in CAMPOS_RECARGAN_PANEL})


def _json_cuerpo():
    cuerpo = request.get_json(silent=True)
    return cuerpo if isinstance(cuerpo, dict) else None


# F5 (ronda final): `_valor_simple` aceptaba una lista para CUALQUIER campo --
# `{"campo": "catalogo_id", "valor": []}` tiraba un TypeError sin atrapar
# (unhashable type: 'list' contra el set de ids, 500 real); un `dolor`/`nombre`
# con lista se guardaba stringificado ("['a', 'b']", `sprints.datos._texto`); un
# `n_videos`/`n_imagenes` con lista se guardaba como 0 (`[] or 0`, sin avisar).
# Ahora el tipo depende del campo: lista solo donde el panel de verdad la manda
# (familias, marcas); número o texto donde vienen de un <input type="number">
# o de un formulario (persona_id y las cantidades); texto para todo lo demás.
_CAMPOS_LISTA = ("familias", "marcas")
_CAMPOS_NUMERICOS = ("n_videos", "n_imagenes", "referencias_objetivo", "persona_id")


def _valor_simple(campo, valor):
    """Si el TIPO de `valor` es válido para `campo` (el contenido lo valida
    `sprints.datos`). `None` solo se acepta fuera de listas/numéricos, donde
    significa «bórralo»."""
    if isinstance(valor, bool):
        return False
    if campo in _CAMPOS_LISTA:
        return valor is None or isinstance(valor, (str, list))
    if campo in _CAMPOS_NUMERICOS:
        return isinstance(valor, (str, int))
    return valor is None or isinstance(valor, str)


def _campanas_desde_form():
    """El asistente manda las campañas como JSON en `campanas_json`:
    [{persona_id, catalogo_id, temporada_id, n_videos, n_imagenes, funnel}]. El
    formulario simple manda una sola con los campos sueltos."""
    crudo = request.form.get("campanas_json")
    if crudo:
        try:
            lista = json.loads(crudo)
        except ValueError:
            raise datos.ErrorDatos(gettext("Las campañas del asistente no se pudieron leer."))
        if not isinstance(lista, list):
            raise datos.ErrorDatos(gettext("Las campañas del asistente no se pudieron leer."))
        return lista
    if request.form.get("persona_id"):
        return [{"persona_id": request.form.get("persona_id"), "catalogo_id": request.form.get("catalogo_id"),
                 "temporada_id": request.form.get("temporada_id"), "n_videos": request.form.get("n_videos"),
                 "n_imagenes": request.form.get("n_imagenes"),
                 "referencias_objetivo": request.form.get("referencias_objetivo"),
                 "funnel": request.form.get("funnel", "tof")}]
    return []


def _validar_campanas(cliente, lista):
    """Producto en el catálogo, cantidades válidas y sin combinaciones
    repetidas dentro del mismo envío. Devuelve la lista normalizada."""
    ids = {p["id"] for p in catalogo_productos.listar(cliente, "producto")}
    limpias = []
    for i, c in enumerate(lista, 1):
        if not isinstance(c, dict):
            raise datos.ErrorDatos(gettext("Campaña %(i)s: formato inválido.", i=i))
        try:
            persona_id = int(c.get("persona_id") or 0)
            temporada_id = int(c.get("temporada_id") or 0) if c.get("temporada_id") else 0
        except (TypeError, ValueError):
            raise datos.ErrorDatos(gettext("Campaña %(i)s: persona o temporada inválida.", i=i))
        if not datos.persona(cliente, persona_id):
            raise datos.ErrorDatos(gettext("Campaña %(i)s: esa persona no existe en este proyecto.", i=i))
        if temporada_id and not datos.temporada(cliente, temporada_id):
            raise datos.ErrorDatos(gettext("Campaña %(i)s: esa temporada no existe en este proyecto.", i=i))
        catalogo_id = (c.get("catalogo_id") or "").strip()
        if catalogo_id not in ids:
            raise datos.ErrorDatos(gettext("Campaña %(i)s: el producto «%(catalogo_id)s» no está en el catálogo.",
                                           i=i, catalogo_id=catalogo_id))
        try:
            n_videos, n_imagenes = datos.validar_cantidades(c.get("n_videos"), c.get("n_imagenes"))
        except datos.ErrorDatos as e:
            raise datos.ErrorDatos(gettext("Campaña %(i)s: %(e)s", i=i, e=str(e)))
        funnel = c.get("funnel", "tof")
        if funnel not in datos.FUNNELS:
            raise datos.ErrorDatos(gettext("Campaña %(i)s: funnel inválido (%(funnel)s).", i=i, funnel=funnel))
        limpias.append({"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id or None,
                        "n_videos": n_videos, "n_imagenes": n_imagenes,
                        "referencias_objetivo": c.get("referencias_objetivo") or None, "funnel": funnel})
    return limpias


@bp.post("/nuevo")
def crear(cliente):
    """Formulario corto de la pestaña: el sprint se arma después en su tablero.
    `campanas_json` sigue aceptándose (scripts y pruebas) pero ya no es obligatorio."""
    try:
        campanas = _validar_campanas(cliente, _campanas_desde_form())
        inicio = request.form.get("inicio")
        momento = request.form.get("momento") or ""
        if momento == "propio":
            momento = "propio:" + (request.form.get("momento_texto") or "")
        sid = datos.crear_sprint(cliente, request.form.get("nombre"), inicio, request.form.get("fin"),
                                 destinos=[d for d in request.form.getlist("destinos") if d],
                                 referencias_objetivo_defecto=request.form.get("referencias_objetivo") or 5,
                                 notas=request.form.get("notas"), pais=None, idioma=datos.IDIOMA_BASE,
                                 marcas=request.form.get("marcas") or "",
                                 momento=_momento_desde(cliente, momento, None, inicio))
        try:
            for c in campanas:
                datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                      c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        except datos.ErrorDatos:
            datos.archivar_sprint(cliente, sid)
            raise
        estado.recalcular(cliente, sid)
        if campanas:
            flash(gettext("Sprint creado con %(n)s campaña(s).", n=len(campanas)), "ok")
        else:
            flash(gettext("Sprint creado. Ahora arma sus campañas con «+ Campaña»."), "ok")
        return _volver(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)


@bp.get("/<int:sid>")
def ver(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    productos = _productos_planos(cliente)
    por_id = {p["id"]: p for p in productos}
    for c in sp["campanas"]:
        _campana_tablero(cliente, sp, c, por_id)
    sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
    pais = sp.get("pais") or proyectos.pais(cliente)
    momento = sp.get("momento") or {}
    return render_template("sprint_detalle.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, linea=tablero.linea_sprint(sp), resumen=tablero.resumen(sp),
                           # Una campaña nueva no se arma con un producto archivado.
                           productos_sprint=catalogo_productos.sin_archivados(productos,
                                                                              tiendas.activos_archivados(cliente)),
                           personas_sprint=datos.personas(cliente),
                           presets=calendario.presets(pais, int(sp["inicio"][:4])),
                           momento_valor=momento.get("clave") or ("propio" if momento else ""),
                           marcas_texto=tablero.marcas_texto(sp.get("marcas")),
                           panel_inicial=request.args.get("panel", type=int),
                           paso_inicial=request.args.get("paso") if request.args.get("paso") in tablero.PASOS else "",
                           lote=produccion.progreso(cliente, sid)["sprint"], **_contexto_lote(cliente))


@bp.get("/<int:sid>/progreso")
def progreso_json(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    lote = produccion.progreso(cliente, sid)
    por_campana = {c["id"]: c for c in lote["campanas"]}
    return jsonify({"estado": sp["estado"], "sprint": progreso.progreso_sprint(sp["campanas"]), "lote": lote["sprint"],
                    "campanas": [{"id": c["id"], "estado": c["estado"], **progreso.progreso_campana(c),
                                  "lote": por_campana.get(c["id"], {})} for c in sp["campanas"]]})


@bp.post("/<int:sid>/campo")
def sprint_campo(cliente, sid):
    """Autoguardado de un dato de la cabecera del tablero."""
    sp = _sprint_o_404(cliente, sid)
    cuerpo = _json_cuerpo()
    if not cuerpo or cuerpo.get("campo") not in CAMPOS_SPRINT:
        return jsonify({"ok": False, "error": gettext("Ese dato no se puede editar aquí.")}), 400
    campo, valor = cuerpo["campo"], cuerpo.get("valor")
    if not _valor_simple(campo, valor):
        return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
    try:
        if campo == "momento":
            valor = _momento_desde(cliente, valor, sp.get("pais"), sp["inicio"])
        datos.actualizar_sprint(cliente, sid, **{campo: valor})
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    nuevo = datos.sprint(cliente, sid, con_eventos=False)
    return jsonify({"ok": True, "linea": tablero.linea_sprint(nuevo), "resumen": tablero.resumen(nuevo)})


@bp.get("/<int:sid>/campanas/<int:cid>/tarjeta")
def campana_tarjeta(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = next((x for x in sp["campanas"] if x["id"] == cid), None)
    if not c:
        abort(404)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in _productos_planos(cliente)})
    return render_template("_sprint_tarjeta.html", cliente=cliente, sprint=sp, c=c)


@bp.post("/<int:sid>/listo")
def marcar_listo(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    if sp["estado"] in ("generando", "revision", "completado"):
        flash(gettext("El sprint ya pasó de la planificación."), "error")
        return _volver(cliente, sid)
    extra = dict(sp.get("extra") or {})
    extra["listo_manual"] = True
    datos.actualizar_sprint(cliente, sid, extra=extra)
    faltantes = [c["id"] for c in sp["campanas"] if c["referencias_listas"] < int(c["referencias_objetivo"] or 1)]
    datos.registrar_evento(cliente, sid, "marcado_listo",
                           datos.texto_guardado(cliente, N_("Marcado listo para generar a mano")),
                           {"campanas_con_referencias_incompletas": faltantes})
    estado.recalcular(cliente, sid)
    if faltantes:
        aviso = gettext(" Ojo: %(n)s campaña(s) no llegan al objetivo de referencias.", n=len(faltantes))
    else:
        aviso = ""
    flash(gettext("Sprint marcado como listo para generar.") + aviso, "ok")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/archivar")
def archivar(cliente, sid):
    desarchivar = request.form.get("desarchivar") is not None
    if not datos.archivar_sprint(cliente, sid, archivado=not desarchivar):
        abort(404)
    flash(gettext("Sprint desarchivado.") if desarchivar else gettext("Sprint archivado."), "ok")
    return _volver(cliente)


@bp.post("/<int:sid>/eliminar")
def eliminar(cliente, sid):
    _sprint_o_404(cliente, sid)
    if datos.eliminar_sprint(cliente, sid):
        flash(gettext("Sprint eliminado permanentemente."), "ok")
    return _volver(cliente)


def _nueva_desde_json(cliente, cuerpo):
    try:
        persona_id = int(cuerpo.get("persona_id") or 0)
    except (TypeError, ValueError):
        persona_id = 0
    if not persona_id or not datos.persona(cliente, persona_id):
        raise datos.ErrorDatos(gettext("Elige una persona (o crea una rápida)."))
    catalogo_id = str(cuerpo.get("catalogo_id") or "").strip()
    if catalogo_id not in {p["id"] for p in _productos_planos(cliente)}:
        raise datos.ErrorDatos(gettext("Elige un producto del catálogo."))
    return {"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": None, "n_videos": 5,
            "n_imagenes": 5, "referencias_objetivo": None, "funnel": "tof"}


@bp.post("/<int:sid>/campanas")
def campana_agregar(cliente, sid):
    """«+ Campaña» del tablero (JSON: persona y producto; lo demás con valores
    por defecto que se cambian en el panel) o el formulario clásico."""
    _sprint_o_404(cliente, sid)
    cuerpo = _json_cuerpo()
    es_json = cuerpo is not None or _quiere_json()
    try:
        if cuerpo is not None:
            c = _nueva_desde_json(cliente, cuerpo)
        else:
            lista = _validar_campanas(cliente, _campanas_desde_form())
            if not lista:
                raise datos.ErrorDatos(gettext("Faltan los datos de la campaña."))
            c = lista[0]
        cid = datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                    c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        estado.recalcular(cliente, sid)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, sid)
    aviso = _aviso_identica(cliente, cid)
    url = url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid)
    if es_json:
        return jsonify({"ok": True, "cid": cid, "aviso": aviso, "url": url})
    flash(gettext("Campaña agregada.") + (f" {aviso}" if aviso else ""), "ok")
    return redirect(url)


@bp.post("/<int:sid>/campanas/<int:cid>")
def campana_editar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        campos = {k: request.form.get(k) for k in ("n_videos", "n_imagenes", "referencias_objetivo")
                  if request.form.get(k) is not None}
        datos.actualizar_campana(cliente, cid, **campos)
        estado.recalcular(cliente, sid)
        flash(gettext("Campaña guardada."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/campanas/<int:cid>/eliminar")
def campana_eliminar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    datos.eliminar_campana(cliente, cid)
    estado.recalcular(cliente, sid)
    flash(gettext("Campaña eliminada."), "ok")
    return _volver(cliente, sid)


# -------------------------------------------------------- referencias ---

def _referencia_o_404(cliente, rid):
    r = datos.referencia(cliente, rid)
    if not r:
        abort(404)
    return r


@bp.get("/<int:sid>/campanas/<int:cid>")
def campana_ver(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = _campana_o_404(cliente, sid, cid)
    refs = datos.referencias(cliente, cid)
    c["progreso"] = progreso.progreso_campana(c)
    otras = [{"campana": oc, "referencias": datos.referencias(cliente, oc["id"])}
             for oc in sp["campanas"] if oc["id"] != cid]
    producto = next((p for p in _productos_planos(cliente) if p["id"] == c["catalogo_id"]), None)
    job_link = tareas_sprints.job_id_link(cliente, cid)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in refs} - {None}
    objetivo_restante = max(1, (c.get("referencias_objetivo") or 1) - len(refs))
    persona_ = datos.persona(cliente, c["persona_id"]) if c.get("persona_id") else None
    nivel_conciencia = ((persona_ or {}).get("extra") or {}).get("conciencia") or {}
    if isinstance(nivel_conciencia, dict):
        nivel_conciencia = nivel_conciencia.get("nivel")
    consciencia = referentes_sugerir.NIVEL_A_CONSCIENCIA.get(doctrina.normalizar_consciencia(nivel_conciencia))
    candidatos_gratis = referentes_sugerir.sugerir(cliente, c["funnel"].upper(), ya_ids, objetivo_restante,
                                                    consciencia=consciencia)
    palabra_sugerida = (producto or {}).get("nombre") or ""
    pais_sugerido = proyectos.pais(cliente)
    sugerencias_ia_crudas = (c.get("extra") or {}).get("sugerencias_ia") or []
    referentes_ia = referentes_datos.por_ids(cliente, [s.get("referente_id") for s in sugerencias_ia_crudas])
    candidatos_ia = []
    for item in sugerencias_ia_crudas:
        ref = referentes_ia.get(item.get("referente_id"))
        if ref and ref["id"] not in ya_ids:
            candidatos_ia.append({**ref, "razon": item.get("razon") or ""})
    job_sugerir_ia = tareas_sprints.job_id_sugerir_biblioteca(cliente, cid)
    return render_template("campana_referencias.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, campana=c, referencias=refs, producto=producto, otras_campanas=otras,
                           fotos_catalogo=_precio_fotos(cliente, producto, refs),
                           intenciones_sprint=datos.INTENCIONES_NOMBRE, cobertura=progreso.cobertura(c, refs),
                           trabajo_link={"job_id": job_link} if trabajos.en_curso(job_link) else None,
                           candidatos_gratis=candidatos_gratis, candidatos_ia=candidatos_ia,
                           trabajo_sugerir_ia={"job_id": job_sugerir_ia} if trabajos.en_curso(job_sugerir_ia) else None,
                           precio_sugerir_ia=gastos.estimar("sugerir_ia"),
                           palabra_sugerida=palabra_sugerida, pais_sugerido=pais_sugerido)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias")
def referencias_subir(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    link = (request.form.get("link") or "").strip()
    intencion = request.form.getlist("intencion")
    subidas, rechazadas, fallidas = 0, 0, 0
    for archivo in request.files.getlist("archivos"):
        if not archivo or not archivo.filename:
            continue
        try:
            info = archivos.guardar_subida(cliente, archivo)
        except Exception:
            fallidas += 1
            continue
        if not info:
            rechazadas += 1
            continue
        try:
            rid = datos.agregar_referencia(cliente, cid, info["tipo"], info["url"], frame_url=info["frame_url"],
                                           ruta_local=info["ruta_local"], origen="archivo", titulo=info["titulo"],
                                           intencion=intencion)
        except datos.ErrorDatos as e:
            flash(str(e), "error")
            continue
        tareas_sprints.encolar_analisis(cliente, rid)
        subidas += 1
    if link:
        if tareas_sprints.encolar_link(cliente, cid, link):
            flash(gettext("Descargando el link; la referencia aparecerá en unos segundos."), "ok")
        else:
            flash(gettext("Ya hay un link descargándose para esta campaña."), "error")
    if subidas:
        flash(gettext("%(n)s referencia(s) subida(s). Cuéntanos qué reutilizar de cada una.", n=subidas), "ok")
    if rechazadas:
        flash(gettext("%(n)s archivo(s) no son imagen ni video (jpg, png, webp, mp4, mov, webm).", n=rechazadas),
              "error")
    if fallidas:
        flash(gettext("%(n)s archivo(s) no se pudieron guardar.", n=fallidas), "error")
    estado.recalcular(cliente, sid)
    if _quiere_json():
        return jsonify({"ok": True, "subidas": subidas, "rechazadas": rechazadas})
    return _volver_campana(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/catalogo")
def referencias_catalogo(cliente, sid, cid):
    """Trae las fotos reales del producto de la campaña como referencias
    (origen catalogo), con intención ángulo de producto y descripción
    automática — cuentan como listas desde el primer momento."""
    c = _campana_o_404(cliente, sid, cid)
    producto = catalogo_productos.encontrar(cliente, c["catalogo_id"], "producto")
    if not producto:
        flash(gettext("El producto de la campaña ya no está en el catálogo."), "error")
        return _volver_campana(cliente, sid, cid)
    faltantes = _fotos_catalogo_pendientes(cliente, producto, datos.referencias(cliente, cid))
    pedido = request.get_json(silent=True) if request.is_json else request.form
    try:
        n_visto = int(str((pedido or {}).get("n_visto", "")))
    except (ValueError, TypeError):
        n_visto = None
    if n_visto != len(faltantes):
        mensaje = gettext("La cantidad de fotos cambió; revisa el precio antes de traerlas.")
        if _quiere_json() or request.is_json:
            return jsonify({"ok": False, "error": mensaje, "n_actual": len(faltantes)}), 409
        flash(mensaje, "warn")
        return _volver_campana(cliente, sid, cid)
    nuevas = 0
    for nombre, url in faltantes:
        descripcion = datos.texto_guardado(cliente, N_("Foto real del producto %(nombre)s, tal como es."),
                                           nombre=producto['nombre'])
        rid = datos.agregar_referencia(cliente, cid, "imagen", url, origen="catalogo", titulo=nombre,
                                       intencion=["angulo_producto"], descripcion=descripcion)
        tareas_sprints.encolar_analisis(cliente, rid)
        nuevas += 1
    if nuevas:
        flash(gettext("%(n)s foto(s) del producto traídas del catálogo.", n=nuevas), "ok")
    else:
        flash(gettext("Las fotos del producto ya estaban."), "ok")
    estado.recalcular(cliente, sid)
    return _volver_campana(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/reutilizar")
def referencias_reutilizar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        datos.reutilizar_referencia(cliente, _entero("referencia_id"), cid)
        flash(gettext("Referencia reutilizada."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    estado.recalcular(cliente, sid)
    return _volver(cliente, sid, cid)


@bp.post("/campanas/<int:cid>/referencias_biblioteca")
def campana_referencias_biblioteca(cliente, cid):
    """Trae uno o más referentes de la biblioteca (`referentes.datos`) como
    referencias ya analizadas de la campaña — sin `sid` en la URL porque
    también se llama desde la ficha de un referente, donde no se navegó
    pasando por el sprint. Vuelve al tablero con el panel de la campaña
    abierto."""
    c = datos.campana(cliente, cid)
    if not c:
        abort(404)
    ids = []
    for x in request.form.getlist("referente_ids"):
        try:
            ids.append(int(x))
        except ValueError:
            continue
    n = 0
    for rid in ids:
        try:
            datos.agregar_referencia_biblioteca(cliente, cid, rid)
            n += 1
        except datos.ErrorDatos:
            continue
    estado.recalcular(cliente, c["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": n > 0, "agregados": n,
                        "error": None if n else gettext("No se pudo agregar ese referente.")})
    if n:
        flash(gettext("%(n)s referente(s) agregado(s) desde la biblioteca.", n=n), "ok")
    else:
        flash(gettext("No se agregó ningún referente."), "error")
    return redirect(url_for("sprints.ver", cliente=cliente, sid=c["sprint_id"], panel=cid))


@bp.post("/campanas/<int:cid>/sugerir_ia")
def campana_sugerir_ia(cliente, cid):
    """Encola `referentes_sugerir_ia` (Task 7): Claude propone candidatos de
    la biblioteca para esta campaña, escritos luego en
    `campana.extra['sugerencias_ia']`. Sin `sid` en la URL por la misma
    razón que `campana_referencias_biblioteca`."""
    c = datos.campana(cliente, cid)
    if not c:
        abort(404)
    ok = tareas_sprints.encolar_sugerir_biblioteca(cliente, cid)
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_sugerir_biblioteca(cliente, cid),
                        "error": None if ok else gettext("Ya hay una sugerencia en curso para esta campaña.")})
    if ok:
        flash(gettext("Claude está buscando referentes de la biblioteca; aparecerán aquí en unos segundos."), "ok")
    else:
        flash(gettext("Ya hay una sugerencia en curso para esta campaña."), "error")
    return redirect(url_for("sprints.ver", cliente=cliente, sid=c["sprint_id"], panel=cid))


@bp.get("/<int:sid>/campanas/<int:cid>/referencias/estado")
def referencias_estado(cliente, sid, cid):
    c = _campana_o_404(cliente, sid, cid)
    return jsonify({"listas": c["referencias_listas"], "objetivo": c["referencias_objetivo"],
                    "referencias": [{"id": r["id"], "analisis_estado": r["analisis_estado"], "analisis": r["analisis"],
                                     "estado": r["estado"]} for r in datos.referencias(cliente, cid)]})


@bp.post("/referencias/<int:rid>")
def referencia_editar(cliente, rid):
    """Autoguardado de la tarjeta (JSON por fetch) o formulario clásico."""
    r = _referencia_o_404(cliente, rid)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": gettext("El cuerpo debe ser un objeto JSON.")}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {}
    if "descripcion" in fuente:
        campos["descripcion"] = fuente.get("descripcion")
    if "intencion" in fuente:
        campos["intencion"] = fuente.get("intencion") if cuerpo is not None else request.form.getlist("intencion")
    if "intencion_otro" in fuente:
        campos["intencion_otro"] = fuente.get("intencion_otro")
    if "titulo" in fuente:
        campos["titulo"] = fuente.get("titulo")
    # Un JSON con el tipo equivocado (número donde va texto, texto donde va lista)
    # es un error de formato, no un dato inválido: se corta antes de tocar datos.
    if (any(campos.get(k) is not None and not isinstance(campos[k], str)
            for k in ("descripcion", "intencion_otro", "titulo") if k in campos)
            or ("intencion" in campos and not isinstance(campos["intencion"], list))):
        if es_json:
            return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
        flash(gettext("Formato inválido."), "error")
        return _volver(cliente, r["sprint_id"], r["campana_id"])
    try:
        datos.actualizar_referencia(cliente, rid, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, r["sprint_id"], r["campana_id"])
    sp = estado.recalcular(cliente, r["sprint_id"])
    c = next((x for x in sp["campanas"] if x["id"] == r["campana_id"]), None)
    if es_json:
        nueva = datos.referencia(cliente, rid)
        return jsonify({"ok": True, "estado": nueva["estado"],
                        "referencias_listas": c["referencias_listas"] if c else 0,
                        "referencias_objetivo": c["referencias_objetivo"] if c else 0,
                        "estado_sprint": sp["estado"]})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/quitar")
def referencia_quitar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    datos.quitar_referencia(cliente, rid)
    estado.recalcular(cliente, r["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/reanalizar")
def referencia_reanalizar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    if trabajos.en_curso(tareas_sprints.job_id_analizar(cliente, rid)):
        return jsonify({"ok": True}) if _quiere_json() else _volver_campana(cliente, r["sprint_id"], r["campana_id"])
    libro.exigir(cliente, gastos.estimar("analizar_referencia")["usd"])
    datos.actualizar_referencia(cliente, rid, analisis_estado="pendiente")
    tareas_sprints.encolar_analisis(cliente, rid)
    if _quiere_json():
        return jsonify({"ok": True})
    flash(gettext("Analizando de nuevo."), "ok")
    return _volver_campana(cliente, r["sprint_id"], r["campana_id"])


# -------------------------------------------------------------- ideas ---

def _idea_o_404(cliente, cp_id, sid=None):
    i = datos.idea(cliente, cp_id)
    if not i or (sid is not None and i["sprint_id"] != sid):
        abort(404)
    return i


def _contexto_lote(cliente):
    mv, mi = produccion.modelos(cliente)
    return {"modelos_video": flowplus_modelos.VIDEO, "modelos_imagen": flowplus_modelos.IMAGEN,
            "modelo_video_defecto": mv, "modelo_imagen_defecto": mi}


@bp.get("/<int:sid>/campanas/<int:cid>/ideas")
def campana_ideas(cliente, sid, cid):
    """Desde la entrega 2 del tablero las ideas viven en la pestaña Ideas del
    panel de la campaña: la página vieja redirige ahí (sus enlaces siguen vivos)."""
    _campana_o_404(cliente, sid, cid)
    return _volver_panel(cliente, sid, cid, "ideas")


def flowplus_prompt_enfoques():
    import flowplus_prompt
    return {k: flowplus_prompt.ENFOQUES[k]["nombre"] for k in flowplus_prompt.ORDEN_ENFOQUES}


@bp.post("/<int:sid>/campanas/<int:cid>/ideas/proponer")
def ideas_proponer(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        if request.form.get("mas"):
            n_v, n_i = _entero("mas", 3), 0
            if request.form.get("tipo") == "imagen":
                n_v, n_i = 0, _entero("mas", 3)
        else:
            n_v = _entero("n_videos") if request.form.get("n_videos") else None
            n_i = _entero("n_imagenes") if request.form.get("n_imagenes") else None
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver_panel(cliente, sid, cid, "ideas")
    ok = tareas_sprints.encolar_ideas(cliente, cid, n_videos=n_v, n_imagenes=n_i)
    error = None if ok else gettext("Ya hay una propuesta de ideas en curso para esta campaña.")
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_ideas(cliente, cid), "error": error}), \
            (200 if ok else 409)
    flash(gettext("Claude está proponiendo ideas; aparecerán aquí en unos segundos.") if ok else error,
          "ok" if ok else "error")
    return _volver_panel(cliente, sid, cid, "ideas")


@bp.post("/<int:sid>/campanas/<int:cid>/ideas/aprobar_todas")
def ideas_aprobar_todas(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    n = 0
    for i in datos.ideas(cliente, cid, incluir_descartadas=False):
        if i["estado_idea"] == "propuesta":
            datos.actualizar_idea(cliente, i["id"], estado_idea="aprobada")
            n += 1
    estado.recalcular(cliente, sid)
    if _quiere_json():
        return jsonify({"ok": True, "aprobadas": n})
    flash(gettext("%(n)s idea(s) aprobada(s).", n=n), "ok")
    return _volver_panel(cliente, sid, cid, "ideas")


def _volver_ideas(i):
    return _volver_panel(i["cliente"], i["sprint_id"], i["campana_id"], "ideas")


@bp.post("/ideas/<int:cp_id>")
def idea_editar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": gettext("El cuerpo debe ser un objeto JSON.")}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {k: fuente.get(k) for k in ("titulo", "escena", "sonido", "gancho") if k in fuente}
    if any(v is not None and not isinstance(v, str) for v in campos.values()):
        if es_json:
            return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
        flash(gettext("Formato inválido."), "error")
        return _volver_ideas(i)
    if "gancho" in campos and isinstance((i.get("extra") or {}).get("angulo"), dict):
        # El gancho de la tarjeta y el del ángulo son el mismo (doctrina, bloque 2).
        extra = dict(i["extra"])
        extra["angulo"] = dict(extra["angulo"], gancho=" ".join((campos["gancho"] or "").split())[:200])
        campos["extra"] = extra
    try:
        if "titulo" in campos and not (campos["titulo"] or "").strip():
            raise datos.ErrorDatos(gettext("Una idea necesita título."))
        if "escena" in campos and not (campos["escena"] or "").strip():
            raise datos.ErrorDatos(gettext("Una idea necesita escena."))
        datos.actualizar_idea(cliente, cp_id, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver_ideas(i)
    if es_json:
        return jsonify({"ok": True})
    flash(gettext("Idea guardada."), "ok")
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/aprobar")
def idea_aprobar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    datos.actualizar_idea(cliente, cp_id, estado_idea="aprobada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


MENSAJE_IDEA_CON_PIEZA = N_("Esa idea ya tiene una pieza generada; usa Regenerar desde la revisión.")


@bp.post("/ideas/<int:cp_id>/reescribir")
def idea_reescribir(cliente, cp_id):
    """«Reescribir la idea con este ángulo» (doctrina, bloque 2, §3.5): encola
    la tarea pagada; el precio ya está en el botón."""
    i = _idea_o_404(cliente, cp_id)
    angulo = (i.get("extra") or {}).get("angulo")
    error = (gettext(MENSAJE_IDEA_CON_PIEZA) if not i["sin_sesion"] else
             None if isinstance(angulo, dict) and angulo.get("promesa") else
             gettext("Esta idea todavía no tiene un ángulo con promesa."))
    if error:
        if _quiere_json():
            return jsonify({"ok": False, "error": error}), 400
        flash(error, "error")
        return _volver_ideas(i)
    ok = tareas_sprints.encolar_reescribir(cliente, cp_id)
    error = None if ok else gettext("Ya se está reescribiendo esta idea.")
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_reescribir(cliente, cp_id), "error": error}), \
            (200 if ok else 409)
    flash(gettext("Reescribiendo la idea desde su ángulo…") if ok else error, "ok" if ok else "error")
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/angulo")
def idea_angulo(cliente, cp_id):
    """Doctrina, bloque 2 (§3.3): guarda el ángulo editado a mano de una idea
    y su gancho (el de la tarjeta y el del ángulo son el mismo). JSON {angulo}
    → {ok, angulo, avisos, resumen}; los avisos no bloquean. 409 si la idea ya
    tiene pieza: desde ahí el ángulo vivo es el de la sesión de Crear."""
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("angulo"), dict):
        return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
    if not i["sin_sesion"]:
        return jsonify({"ok": False, "error": gettext(MENSAJE_IDEA_CON_PIEZA)}), 409
    extra = dict(i.get("extra") or {})
    previo = extra.get("angulo") if isinstance(extra.get("angulo"), dict) else {}
    limpio, avisos = doctrina.angulo_desde_formulario(dict(cuerpo["angulo"], origen=previo.get("origen")),
                                                      previo.get("faltantes"), ahora=db.ahora())
    extra["angulo"] = limpio
    datos.actualizar_idea(cliente, cp_id, extra=extra, gancho=limpio["gancho"])
    return jsonify({"ok": True, "angulo": limpio, "avisos": avisos, "resumen": doctrina.resumen_angulo(limpio)})


@bp.post("/ideas/<int:cp_id>/descartar")
def idea_descartar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    # E3: con sesión (o reserva viva) la pieza está en marcha y descartar la
    # idea la sacaría de los conteos; el botón está oculto, pero la petición
    # puede fabricarse. Una reserva vencida no es sesión (`sin_sesion`).
    if not i["sin_sesion"]:
        if _quiere_json():
            return jsonify({"ok": False, "error": gettext(MENSAJE_IDEA_CON_PIEZA)}), 400
        flash(gettext(MENSAJE_IDEA_CON_PIEZA), "error")
        return _volver_ideas(i)
    datos.actualizar_idea(cliente, cp_id, estado_idea="descartada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/otra")
def idea_otra(cliente, cp_id):
    """Pide otra idea del mismo tipo en lugar de esta (una sola). Descartar
    la vieja lo hace la tarea (`ideas.proponer(reemplaza=)`) al reemplazarla:
    si no se puede encolar (ya hay una propuesta en curso para la campaña),
    la idea no se toca — antes se descartaba primero y quedaba sin
    reemplazo."""
    i = _idea_o_404(cliente, cp_id)
    if not i["sin_sesion"]:
        if _quiere_json():
            return jsonify({"ok": False, "error": gettext(MENSAJE_IDEA_CON_PIEZA)}), 400
        flash(gettext(MENSAJE_IDEA_CON_PIEZA), "error")
        return _volver_ideas(i)
    ok = tareas_sprints.encolar_ideas(cliente, i["campana_id"], reemplaza=cp_id)
    error = None if ok else gettext("Ya hay una propuesta en curso; espera a que termine.")
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_ideas(cliente, i["campana_id"]),
                        "error": error}), (200 if ok else 409)
    flash(gettext("Pidiendo otra idea…") if ok else error, "ok" if ok else "error")
    return _volver_ideas(i)


# --------------------------------------------------------------- lote ---

@bp.get("/<int:sid>/lote/estimar")
def lote_estimar(cliente, sid):
    _sprint_o_404(cliente, sid)
    cid = request.args.get("campana_id", type=int)
    try:
        e = produccion.estimar(cliente, sid, campana_id=cid, modelo_video=request.args.get("modelo_video"),
                               modelo_imagen=request.args.get("modelo_imagen"))
    except datos.ErrorDatos as ex:
        return jsonify({"ok": False, "error": str(ex)}), 400
    # El botón pinta `usd` y `texto`: lo que ve la persona (cobros, spec 2026-10-08 §6).
    return jsonify({**e, "usd": gastos.precio(e["usd"]), "acumulado_usd": gastos.precio(e["acumulado_usd"]),
                    "qa_usd": gastos.precio(e["qa_usd"])})


@bp.post("/<int:sid>/lote")
def lote(cliente, sid):
    """Puerta de gasto: el modal del tablero o la caja «Generar» del panel ya
    mostraron el costo; aquí se encola."""
    _sprint_o_404(cliente, sid)
    cid = request.form.get("campana_id", type=int)
    try:
        r = produccion.lanzar_lote(cliente, sid, campana_id=cid, modelo_video=request.form.get("modelo_video"),
                                   modelo_imagen=request.form.get("modelo_imagen"))
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, sid)
    if not r["encoladas"]:
        error = (gettext("No había ideas aprobadas sin generar.") if not r["omitidas"]
                 else gettext("Esas piezas ya se estaban generando."))
        if _quiere_json():
            return jsonify({"ok": False, "error": error, "encoladas": 0, "omitidas": r["omitidas"]}), 409
        flash(error, "warn")
        return _volver(cliente, sid)
    texto = gettext("Lote encolado: %(n)s pieza(s), USD %(usd)s estimado. "
                    "Te avisamos por correo al terminar si está configurado.",
                    n=r['encoladas'], usd=f"{gastos.precio(r['usd']):.2f}")
    if _quiere_json():
        return jsonify({"ok": True, "encoladas": r["encoladas"], "omitidas": r["omitidas"], "usd": gastos.precio(r["usd"]),
                        "mensaje": texto})
    flash(texto, "ok")
    return _volver(cliente, sid)


def _volver_pieza(cliente, i):
    """A la bandeja si el formulario vino de ahí (`volver=revision`), a la
    pestaña Piezas del panel (`volver=panel`); si no, al sprint."""
    if request.form.get("volver") == "revision":
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    if request.form.get("volver") == "panel":
        return _volver_panel(cliente, i["sprint_id"], i["campana_id"], "piezas")
    return _volver(cliente, i["sprint_id"])


@bp.post("/ideas/<int:cp_id>/reintentar")
def pieza_reintentar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        ok = produccion.reintentar(cliente, cp_id)
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    error = None if ok else gettext("Esa pieza no está en error o ya se está generando.")
    if _quiere_json():
        return jsonify({"ok": bool(ok), "error": error}), (200 if ok else 409)
    flash(gettext("Reintentando la pieza.") if ok else error, "ok" if ok else "warn")
    return _volver_pieza(cliente, i)


@bp.post("/ideas/<int:cp_id>/regenerar")
def pieza_regenerar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        produccion.regenerar(cliente, cp_id)
    except (datos.ErrorDatos, ValueError) as e:
        # ValueError: `creative_flow.duplicar` con una sesión que no existe
        # (cf_id colgado o placeholder) — se muestra como un ErrorDatos.
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True, "error": None})
    flash(gettext("Regenerando la pieza (sesión nueva, misma idea)."), "ok")
    return _volver_pieza(cliente, i)


# ----------------------------------------------------------- revisión ---

CHECKS_QA = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")


@bp.get("/<int:sid>/revision")
def revision(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    piezas = _piezas_revision(cliente, sp)
    return render_template("sprint_revision.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, piezas=piezas, resumen=revision_mod.resumen(cliente, sid), checks=CHECKS_QA,
                           productos_por_id={p["id"]: p for p in _productos_planos(cliente)})


@bp.post("/ideas/<int:cp_id>/revision")
def pieza_revision(cliente, cp_id):
    """Aprobar o rechazar una pieza (JSON por fetch desde la bandeja, o
    formulario clásico). Rechazar exige motivo."""
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": gettext("El cuerpo debe ser un objeto JSON.")}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    accion, motivo = fuente.get("accion"), fuente.get("motivo")
    try:
        if accion == "aprobar":
            ok = revision_mod.aprobar(cliente, cp_id)
        elif accion == "rechazar":
            ok = revision_mod.rechazar(cliente, cp_id, motivo if isinstance(motivo, str) else "")
        else:
            raise datos.ErrorDatos(gettext("Acción desconocida."))
        if not ok:
            raise datos.ErrorDatos(gettext("Esa pieza todavía no está terminada."))
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    nueva = datos.idea(cliente, cp_id)
    if es_json:
        return jsonify({"ok": True, "revision": nueva["revision"],
                        "estado_sprint": (datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}).get("estado")})
    flash(gettext("Pieza aprobada.") if accion == "aprobar" else gettext("Pieza rechazada."), "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))


@bp.post("/ideas/<int:cp_id>/qa")
def pieza_qa(cliente, cp_id):
    """«Repetir QA»: limpia el marcador (`qa=None`) y encola un solo
    `sprint_qa_pieza` para la sesión actual. Solo visión (centavos), nunca
    generación: sin puerta de costo."""
    i = _idea_o_404(cliente, cp_id)
    destino = redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    if not i.get("cf_id") or i.get("estado") not in revision_mod.TERMINADAS:
        if _quiere_json():
            return jsonify({"ok": False, "error": gettext("Esa pieza todavía no está lista para el QA.")}), 400
        flash(gettext("Esa pieza todavía no está lista para el QA."), "error")
        return destino
    # Cobros (spec 2026-10-08 §5): sin saldo no se borra el QA anterior; el
    # manejador común responde. Pide lo mismo que `encolar_qa` va a reservar
    # (revisión final 2026-10-08), para no borrar el QA y quedarse sin encolar.
    libro.exigir(cliente, gastos.TARIFAS["revision_pieza"])
    if not datos.limpiar_qa_no_aprobada(cliente, cp_id, i["cf_id"]):
        if _quiere_json():
            return jsonify({"ok": False, "error": gettext("Esa pieza ya pasó el QA o está aprobada.")}), 409
        flash(gettext("Esa pieza ya pasó el QA o está aprobada."), "warn")
        return destino
    ok = tareas_sprints.encolar_qa(cliente, cp_id)
    if _quiere_json():
        return jsonify({"ok": bool(ok), "error": None if ok else gettext("Ya hay un QA en curso para esa pieza.")}), \
            (200 if ok else 409)
    if ok:
        flash(gettext("Repitiendo el QA de la pieza; el resultado aparecerá aquí en unos segundos."), "ok")
    else:
        flash(gettext("Ya hay un QA en curso para esa pieza."), "warn")
    return destino


@bp.post("/<int:sid>/revision/aprobar_qa")
def revision_aprobar_qa(cliente, sid):
    _sprint_o_404(cliente, sid)
    n = revision_mod.aprobar_pasaron_qa(cliente, sid, campana_id=request.form.get("campana_id", type=int))
    if _quiere_json():
        return jsonify({"ok": True, "aprobadas": n})
    flash(gettext("%(n)s pieza(s) aprobada(s) por haber pasado el QA.", n=n), "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/cerrar")
def cerrar(cliente, sid):
    _sprint_o_404(cliente, sid)
    try:
        r = revision_mod.cerrar(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, sid)
    flash(gettext("Sprint cerrado: %(aprobadas)s aprobadas, %(rechazadas)s rechazadas, USD %(usd)s.",
                 aprobadas=r['aprobadas'], rechazadas=r['rechazadas'], usd=f"{r['costo_usd']:.2f}"), "ok")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/reabrir")
def reabrir(cliente, sid):
    _sprint_o_404(cliente, sid)
    if revision_mod.reabrir(cliente, sid):
        flash(gettext("Sprint reabierto a revisión."), "ok")
    else:
        flash(gettext("Solo se reabre un sprint completado."), "error")
    return _volver(cliente, sid)


# ------------------------------------------------------------ entrega ---

def entrega_ver(cliente, sid):
    """Se llama `entrega_ver` para no pisar el módulo `entrega` importado
    arriba; el endpoint sigue siendo `sprints.entrega` (add_url_rule)."""
    sp = _sprint_o_404(cliente, sid)
    job = tareas_sprints.job_id_zip(cliente, sid)
    return render_template("sprint_entrega.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, enlaces=entrega.enlaces(cliente, sid), resumen=revision_mod.resumen(cliente, sid),
                           zip_info=(sp.get("extra") or {}).get("zip"),
                           trabajo_zip={"job_id": job} if trabajos.en_curso(job) else None)


bp.add_url_rule("/<int:sid>/entrega", endpoint="entrega", view_func=entrega_ver, methods=["GET"])


@bp.post("/<int:sid>/entrega/zip")
def entrega_zip(cliente, sid):
    _sprint_o_404(cliente, sid)
    if not entrega.enlaces(cliente, sid):
        flash(gettext("No hay piezas aprobadas que entregar."), "error")
    elif tareas_sprints.encolar_zip(cliente, sid):
        flash(gettext("Armando el zip; el enlace aparecerá aquí al terminar."), "ok")
    else:
        flash(gettext("Ya se está armando el zip."), "warn")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))
