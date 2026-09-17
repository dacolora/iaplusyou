"""
Producción por lotes (spec §2.2): de cada idea aprobada a una sesión de Crear
(FlowPlus), con el costo estimado antes de encolar y prioridad baja para no
bloquear a quien genera una pieza suelta. Reintento (misma sesión) y
regeneración (sesión nueva con `creative_flow.duplicar`) también pasan por aquí,
siempre con `max_intentos=1` (vía flowplus_lanzar). `progreso` agrega el
estado de todas las piezas de un sprint para el tablero.
"""
import os

import catalogo_productos
import cola
import creative_flow
import flowplus_lanzar
import flowplus_prompt
import marca
import proyectos
from providers import flowplus_modelos
from sprints import datos, estado
from storage import r2_uploader

PRIORIDAD_LOTE = 3
DURACION_DEFECTO_S = 8
SEGUNDOS_VIDEO = 180
SEGUNDOS_IMAGEN = 60
MAX_REFERENCIAS = 15
MAX_IMAGENES_MODELO = 10
PLATAFORMAS_VERTICALES = {"instagram", "tiktok"}


# ---------------------------------------------------------------- lote ---

def modelos(cliente, modelo_video=None, modelo_imagen=None):
    prefs = proyectos.preferencias_flowplus(cliente)
    mv = modelo_video if modelo_video in flowplus_modelos.VIDEO else prefs.get("modelo_video")
    mi = modelo_imagen if modelo_imagen in flowplus_modelos.IMAGEN else prefs.get("modelo_imagen")
    if mv not in flowplus_modelos.VIDEO:
        mv = flowplus_modelos.VIDEO_POR_DEFECTO
    if mi not in flowplus_modelos.IMAGEN:
        mi = flowplus_modelos.IMAGEN_POR_DEFECTO
    return mv, mi


def _sprint(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    return sp


def pendientes(cliente, sprint_id, campana_id=None):
    """[(campana, idea)] aprobadas y todavía sin sesión de Crear."""
    sp = _sprint(cliente, sprint_id)
    salida = []
    for c in sp["campanas"]:
        if campana_id is not None and c["id"] != campana_id:
            continue
        for i in c["ideas"]:
            if i["estado_idea"] == "aprobada" and not i["cf_id"]:
                salida.append((c, i))
    return salida


def _duracion(idea):
    try:
        return int(float(idea.get("duracion_s") or DURACION_DEFECTO_S))
    except (TypeError, ValueError):
        return DURACION_DEFECTO_S


def _n_referencias(campana):
    return max(1, min(MAX_IMAGENES_MODELO, 1 + int(campana.get("referencias_total") or 0)))


def _texto_tiempo(segundos):
    h, m = divmod(int(round(segundos / 60.0)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def estimar(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None):
    sp = _sprint(cliente, sprint_id)
    mv, mi = modelos(cliente, modelo_video, modelo_imagen)
    videos = imagenes = 0
    usd = 0.0
    for c, i in pendientes(cliente, sprint_id, campana_id):
        if i["tipo"] == "video":
            videos += 1
            usd += float((flowplus_modelos.estimate_video(mv, _duracion(i)) or {}).get("usd") or 0.0)
        else:
            imagenes += 1
            usd += float((flowplus_modelos.estimate_imagen(mi, n_referencias=_n_referencias(c)) or {}).get("usd") or 0.0)
    segundos = videos * SEGUNDOS_VIDEO + imagenes * SEGUNDOS_IMAGEN
    acumulado = float((sp.get("extra") or {}).get("costo_estimado_usd") or 0.0)
    nombre_v, nombre_i = flowplus_modelos.VIDEO[mv]["nombre"], flowplus_modelos.IMAGEN[mi]["nombre"]
    texto = (f"{videos} video(s) ({nombre_v}) y {imagenes} imagen(es) ({nombre_i}): USD {usd:.2f} estimado · "
             f"acumulado del sprint USD {acumulado:.2f} · tiempo estimado {_texto_tiempo(segundos)}")
    return {"videos": videos, "imagenes": imagenes, "usd": round(usd, 4), "segundos": segundos, "modelo_video": mv,
            "modelo_imagen": mi, "modelo_video_nombre": nombre_v, "modelo_imagen_nombre": nombre_i,
            "acumulado_usd": round(acumulado, 4), "texto": texto}


# ------------------------------------------------------------ sesiones ---

def _logos(cliente):
    """Igual que dashboard._logos: los archivos de clientes/<c>/logos/ por su URL pública."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    carpeta = os.path.join(base, "clientes", cliente, "logos")
    public_base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    if not os.path.isdir(carpeta) or not public_base:
        return []
    salida = []
    for f in sorted(os.listdir(carpeta)):
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            salida.append({"url": f"{public_base}/clientes/{cliente}/logos/{f}"})
    return salida


def referencias_sesion(cliente, campana, idea):
    """Referencias de la sesión como las arma Crear: el producto del catálogo
    (con regla de fidelidad), luego las referencias de la campaña (primero las
    que inspiran la idea) y los logos del proyecto. Devuelve
    (referencias, referencias_urls, productos_sel)."""
    referencias, productos_sel = [], []
    activo = catalogo_productos.encontrar(cliente, campana["catalogo_id"], categoria="producto")
    if activo:
        info_cat = catalogo_productos.CATEGORIAS["producto"]
        ruta = (activo.get("referencias") or [None])[0]
        if ruta:
            try:
                url = r2_uploader.upload_image(ruta, f"clientes/{cliente}/{info_cat['carpeta']}/{activo['id']}/{os.path.basename(ruta)}")
                referencias.append({"tipo": "imagen", "url": url, "frame_url": url, "etiqueta": "@Producto 1",
                                    "categoria": "producto", "activo": activo["nombre"], "regla": activo.get("regla") or "",
                                    "producto": activo["nombre"]})
            except Exception:
                pass
        productos_sel.append(activo["nombre"])
    refs = datos.referencias(cliente, campana["id"])
    primero = [int(x) for x in (idea.get("referencias_ids") or [])]
    ordenadas = [r for r in refs if r["id"] in primero] + [r for r in refs if r["id"] not in primero]
    n_img = n_vid = 0
    for r in ordenadas:
        if r["tipo"] == "video":
            n_vid += 1
            referencias.append({"tipo": "video", "url": r["url"], "frame_url": r.get("frame_url") or r["url"],
                                "etiqueta": f"@Video {n_vid}", "origen": r.get("origen")})
        else:
            n_img += 1
            referencias.append({"tipo": "imagen", "url": r["url"], "frame_url": r["url"], "etiqueta": f"@Imagen {n_img}",
                                "origen": r.get("origen")})
    logos = [{"tipo": "imagen", "url": l["url"], "frame_url": l["url"], "etiqueta": f"@Logo {i}", "logo": True}
             for i, l in enumerate(_logos(cliente)[:2], start=1)]
    referencias = (referencias + logos)[:MAX_REFERENCIAS]
    referencias_urls = [r["frame_url"] for r in referencias][:MAX_IMAGENES_MODELO]
    return referencias, referencias_urls, productos_sel


def _aspect_ratio(plataformas):
    if any(p in PLATAFORMAS_VERTICALES for p in plataformas):
        return "9:16"
    if plataformas == ["youtube"]:
        return "16:9"
    return "9:16"


def _contexto(cliente, campana):
    p = datos.persona(cliente, campana["persona_id"]) or {}
    t = datos.temporada(cliente, campana["temporada_id"]) or {}
    return {"persona": {k: p.get(k) for k in ("resumen", "descripcion", "tono", "senales_visuales")},
            "temporada": {k: t.get(k) for k in ("nombre", "contexto", "mood_visual")}}, p


def crear_sesion(cliente, sprint, campana, idea, modelo_video, modelo_imagen):
    """Crea la sesión de Crear de una idea aprobada, arma su prompt y la
    vincula (idea.cf_id y extra["sprint"]). No encola nada."""
    referencias, referencias_urls, productos_sel = referencias_sesion(cliente, campana, idea)
    contexto, persona = _contexto(cliente, campana)
    enfoque = idea.get("enfoque") if idea.get("enfoque") in flowplus_prompt.ENFOQUES else "producto"
    info = flowplus_prompt.ENFOQUES[enfoque]
    escena = idea["escena"]
    if idea["tipo"] == "video" and idea.get("sonido"):
        escena = f"{escena}\nSONIDO: {idea['sonido']}. Sin diálogo hablado ni música de fondo."
    prompt = flowplus_prompt.armar(escena, referencias, con_persona=info["con_persona"],
                                   guia_marca=marca.guia_efectiva(cliente), negative_marca=marca.negative_prompt_efectivo(cliente),
                                   logos=[r for r in referencias if r.get("logo")], enfoque=enfoque, contexto=contexto)
    plataformas = list(idea.get("plataformas") or [])
    cf_id = creative_flow.crear(
        cliente, [], productos_sel, [], idea["escena"], _duracion(idea) if idea["tipo"] == "video" else 0,
        persona.get("tono") or "", "A", referencias_urls=referencias_urls, platforms=plataformas,
        extra_sprint={"sprint_id": sprint["id"], "sprint_nombre": sprint["nombre"], "campana_id": campana["id"],
                      "campana_n": int(campana["orden"]) + 1, "cp_id": idea["id"]})
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt, aspect_ratio=_aspect_ratio(plataformas), tipo=idea["tipo"],
                             modelo=modelo_video if idea["tipo"] == "video" else modelo_imagen, referencias=referencias,
                             con_persona=info["con_persona"], enfoque=enfoque, enfoque_nombre=info["nombre"])
    datos.actualizar_idea(cliente, idea["id"], cf_id=cf_id)
    return cf_id


def lanzar_lote(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None):
    """Crea y encola una sesión por idea aprobada sin sesión. Devuelve
    {encoladas, omitidas, cf_ids, usd}. La puerta de costo es de la ruta: aquí
    ya se decidió gastar."""
    sp = _sprint(cliente, sprint_id)
    mv, mi = modelos(cliente, modelo_video, modelo_imagen)
    est = estimar(cliente, sprint_id, campana_id, mv, mi)
    encoladas, omitidas, cf_ids = 0, 0, []
    for c, i in pendientes(cliente, sprint_id, campana_id):
        cf_id = crear_sesion(cliente, sp, c, i, mv, mi)
        entry = creative_flow.cargar(cliente)[cf_id]
        if flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_LOTE):
            encoladas += 1
            cf_ids.append(cf_id)
        else:
            omitidas += 1
    if encoladas:
        extra = dict(sp.get("extra") or {})
        extra["costo_estimado_usd"] = round(float(extra.get("costo_estimado_usd") or 0.0) + est["usd"], 4)
        extra["lote_en_curso"] = True
        extra["modelos_lote"] = {"video": mv, "imagen": mi}
        datos.actualizar_sprint(cliente, sprint_id, extra=extra)
        datos.registrar_evento(cliente, sprint_id, "lote_encolado",
                               f"Lote de {encoladas} pieza(s) encolado: {est['videos']} video(s), {est['imagenes']} imagen(es), USD {est['usd']:.2f} estimado",
                               {"encoladas": encoladas, "omitidas": omitidas, "usd": est["usd"], "campana_id": campana_id,
                                "modelo_video": mv, "modelo_imagen": mi}, campana_id=campana_id)
        estado.recalcular(cliente, sprint_id)
    return {"encoladas": encoladas, "omitidas": omitidas, "cf_ids": cf_ids, "usd": est["usd"]}


def _idea_con_sesion(cliente, cp_id):
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        raise datos.ErrorDatos("Esa pieza no tiene una sesión generada.")
    return i


def reintentar(cliente, cp_id):
    """Vuelve a encolar la misma sesión (solo si quedó en error). Gasta."""
    i = _idea_con_sesion(cliente, cp_id)
    entry = creative_flow.cargar(cliente).get(i["cf_id"])
    if not entry or entry.get("estado") != "error":
        return False
    ok = flowplus_lanzar.lanzar(cliente, i["cf_id"], entry, prioridad=PRIORIDAD_LOTE)
    if ok:
        datos.registrar_evento(cliente, i["sprint_id"], "pieza_reintentada", f"Reintento de «{i['titulo']}»",
                               {"cp_id": cp_id, "cf_id": i["cf_id"]}, campana_id=i["campana_id"])
        estado.recalcular(cliente, i["sprint_id"])
    return ok


def regenerar(cliente, cp_id):
    """Sesión nueva a partir de la actual (misma idea y prompt), QA y revisión
    en blanco; la sesión anterior queda en `extra.cf_anteriores`. Gasta."""
    i = _idea_con_sesion(cliente, cp_id)
    nuevo = creative_flow.duplicar(cliente, i["cf_id"])
    extra = dict(i.get("extra") or {})
    extra["cf_anteriores"] = list(extra.get("cf_anteriores") or []) + [i["cf_id"]]
    datos.actualizar_idea(cliente, cp_id, cf_id=nuevo, qa=None, revision="pendiente", revision_motivo=None, extra=extra)
    entry = creative_flow.cargar(cliente)[nuevo]
    flowplus_lanzar.lanzar(cliente, nuevo, entry, prioridad=PRIORIDAD_LOTE)
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_regenerada", f"Regeneración de «{i['titulo']}»",
                           {"cp_id": cp_id, "cf_id": nuevo, "anterior": i["cf_id"]}, campana_id=i["campana_id"])
    sp = datos.sprint(cliente, i["sprint_id"], con_eventos=False)
    if sp:
        extra_sp = dict(sp.get("extra") or {})
        extra_sp["lote_en_curso"] = True
        datos.actualizar_sprint(cliente, i["sprint_id"], extra=extra_sp)
    estado.recalcular(cliente, i["sprint_id"])
    return nuevo


# ------------------------------------------------------------ progreso ---

def _resumen(piezas, planeadas):
    r = {"planeadas": planeadas, "encoladas": 0, "generando": 0, "listas": 0, "error": 0, "aprobadas": 0,
         "costo_usd": 0.0, "segundos_restantes": 0}
    for p in piezas:
        r["costo_usd"] += float(p.get("costo_usd") or 0.0)
        if p.get("revision") == "aprobada":
            r["aprobadas"] += 1
        est = p.get("estado")
        if est in ("listo", "degradada"):
            r["listas"] += 1
        elif est == "error":
            r["error"] += 1
        elif est in ("pendiente", "generando"):
            tarea = cola.consultar_por_job(flowplus_lanzar.job_id(p["cliente"], p["cf_id"])) or {}
            if tarea.get("estado") == "en_curso":
                r["generando"] += 1
            else:
                r["encoladas"] += 1
            r["segundos_restantes"] += SEGUNDOS_VIDEO if p.get("tipo") == "video" else SEGUNDOS_IMAGEN
    r["costo_usd"] = round(r["costo_usd"], 4)
    return r


def progreso(cliente, sprint_id):
    sp = estado.recalcular(cliente, sprint_id)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    campanas = []
    todas = []
    for c in sp["campanas"]:
        planeadas = int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0)
        campanas.append({"id": c["id"], "estado": c["estado"], **_resumen(c["piezas"], planeadas)})
        todas.extend(c["piezas"])
    total = sum(int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0) for c in sp["campanas"])
    return {"estado": sp["estado"], "sprint": _resumen(todas, total), "campanas": campanas}
