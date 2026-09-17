"""
Producción por lotes (spec §2.2): de cada idea aprobada a una sesión de Crear
(FlowPlus), con el costo estimado antes de encolar y prioridad baja para no
bloquear a quien genera una pieza suelta. Reintento (misma sesión) y
regeneración (sesión nueva con `creative_flow.duplicar`) también pasan por aquí,
siempre con `max_intentos=1` (vía flowplus_lanzar). `progreso` agrega el
estado de todas las piezas de un sprint para el tablero.
"""
import os

import bitacora
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

# Reserva de una idea (placeholder en cf_id) mientras se arma su sesión. El
# formato y el vencimiento viven en `datos` (dueño de `reclamar_cf`), aquí solo
# se re-exportan para que este módulo sea el punto de entrada de producción.
RESERVA_TTL_S = datos.RESERVA_TTL_S
reserva_placeholder = datos.reserva_placeholder
es_reserva = datos.es_reserva
reserva_vencida = datos.reserva_vencida


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
    """[(campana, idea)] aprobadas y todavía sin sesión de Crear: `cf_id`
    NULL o una reserva vencida (`datos.reserva_vencida`); una reserva viva es
    de otro lote y no se toca."""
    sp = _sprint(cliente, sprint_id)
    salida = []
    for c in sp["campanas"]:
        if campana_id is not None and c["id"] != campana_id:
            continue
        for i in c["ideas"]:
            if i["estado_idea"] == "aprobada" and (not i["cf_id"] or reserva_vencida(i["cf_id"])):
                salida.append((c, i))
    return salida


def _duracion(idea):
    try:
        return int(float(idea.get("duracion_s") or DURACION_DEFECTO_S))
    except (TypeError, ValueError):
        return DURACION_DEFECTO_S


def _n_referencias(cliente, campana):
    """Referencias que le llegan al modelo de imagen: el producto (1) + las de
    la campaña + los logos que `referencias_sesion` agrega (tope 2), así el
    estimado no se queda corto cuando el proyecto tiene logo."""
    return max(1, min(MAX_IMAGENES_MODELO,
                      1 + int(campana.get("referencias_total") or 0) + min(2, len(_logos(cliente)))))


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
            usd += float((flowplus_modelos.estimate_imagen(mi, n_referencias=_n_referencias(cliente, c)) or {}).get("usd") or 0.0)
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
    (referencias, referencias_urls, productos_sel).

    El producto es obligatorio: sin su foto de referencia no hay
    `PRODUCTO EXACTO` en el prompt y el modelo puede inventar cualquier cosa,
    así que ni el catálogo sin foto ni un fallo al subirla se tragan en
    silencio — ambos paran la sesión con `ErrorDatos` para que
    `lanzar_lote` la cuente como omitida en vez de generar a ciegas."""
    referencias, productos_sel = [], []
    activo = catalogo_productos.encontrar(cliente, campana["catalogo_id"], categoria="producto")
    ruta = (activo.get("referencias") or [None])[0] if activo else None
    if not activo or not ruta:
        raise datos.ErrorDatos("El producto de la campaña no está en el catálogo o no tiene foto.")
    info_cat = catalogo_productos.CATEGORIAS["producto"]
    try:
        url = r2_uploader.upload_image(ruta, f"clientes/{cliente}/{info_cat['carpeta']}/{activo['id']}/{os.path.basename(ruta)}")
    except Exception as e:
        bitacora.registrar(cliente, activo["id"], "sprint_producto", "error", str(e))
        raise datos.ErrorDatos(f"No se pudo subir la foto del producto: {e}")
    referencias.append({"tipo": "imagen", "url": url, "frame_url": url, "etiqueta": "@Producto 1",
                        "categoria": "producto", "activo": activo["nombre"], "regla": activo.get("regla") or "",
                        "producto": activo["nombre"]})
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


def crear_sesion(cliente, sprint, campana, idea, modelo_video, modelo_imagen, reserva=None):
    """Crea la sesión de Crear de una idea aprobada, arma su prompt y la
    vincula (idea.cf_id y extra["sprint"]). No encola nada. `reserva`: el
    placeholder que `lanzar_lote` puso en `cf_id`; el vínculo final solo se
    escribe si sigue ahí."""
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
    # `lanzar_lote` ya reservó cf_id con un placeholder antes de llamar acá,
    # así que el vínculo final es el mismo compare-and-swap (evita que una
    # idea tenga dos sesiones si dos lotes corrieron a la vez). Si la reserva
    # ya no está (venció y otro lote la reclamó), no se pisa lo ajeno: se
    # avisa y el lote la cuenta como omitida. Llamada directa (sin reserva
    # previa, como en las pruebas) cae al `actualizar_idea` de siempre.
    if reserva is None:
        datos.actualizar_idea(cliente, idea["id"], cf_id=cf_id)
    elif not datos.reclamar_cf(cliente, idea["id"], cf_id, esperado=reserva):
        raise datos.ErrorDatos("Otro lote tomó esta idea mientras se armaba la sesión.")
    return cf_id


def lanzar_lote(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None):
    """Crea y encola una sesión por idea aprobada sin sesión. Devuelve
    {encoladas, omitidas, cf_ids, usd}. La puerta de costo es de la ruta: aquí
    ya se decidió gastar.

    Cada idea se reserva (`datos.reclamar_cf` con el placeholder de
    `reserva_placeholder`, "reservando_<id>_<epoch>") ANTES de armar su
    sesión: si dos llamadas a `lanzar_lote` corren a la vez (dos clics, el
    worker y un cron) y las dos leyeron la misma lista de `pendientes`, solo
    la primera gana la reserva de cada idea — la segunda la ve omitida en vez
    de generar dos sesiones para la misma pieza (double spend). El swap
    espera el `cf_id` que se leyó (None o una reserva vencida), así una
    reserva colgada de un proceso muerto se recupera y una viva nunca se
    roba. Un fallo al armar la sesión (p. ej. el producto no tiene foto,
    §referencias_sesion) libera la reserva propia, nunca una ajena."""
    sp = _sprint(cliente, sprint_id)
    mv, mi = modelos(cliente, modelo_video, modelo_imagen)
    est = estimar(cliente, sprint_id, campana_id, mv, mi)
    encoladas, omitidas, cf_ids = 0, 0, []
    for c, i in pendientes(cliente, sprint_id, campana_id):
        reserva = reserva_placeholder(i["id"])
        if not datos.reclamar_cf(cliente, i["id"], reserva, esperado=i["cf_id"]):
            omitidas += 1
            continue
        try:
            cf_id = crear_sesion(cliente, sp, c, i, mv, mi, reserva=reserva)
        except Exception as e:
            datos.reclamar_cf(cliente, i["id"], None, esperado=reserva)
            omitidas += 1
            datos.registrar_evento(cliente, sprint_id, "pieza_omitida", f"«{i['titulo']}» no se pudo preparar: {e}",
                                   {"cp_id": i["id"], "error": str(e)}, campana_id=c["id"])
            continue
        entry = creative_flow.cargar(cliente)[cf_id]
        if flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_LOTE):
            encoladas += 1
            cf_ids.append(cf_id)
        else:
            omitidas += 1
    if encoladas:
        def _sumar(extra):
            extra["costo_estimado_usd"] = round(float(extra.get("costo_estimado_usd") or 0.0) + est["usd"], 4)
            extra["lote_en_curso"] = True
            extra["modelos_lote"] = {"video": mv, "imagen": mi}
            return extra
        datos.actualizar_extra_sprint(cliente, sprint_id, _sumar)
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
        # Como `regenerar`: el lote vuelve a estar en curso, así la periódica
        # avisa «lote terminado» cuando la última pieza reintentada acaba.
        datos.actualizar_extra_sprint(cliente, i["sprint_id"], lambda extra: {**extra, "lote_en_curso": True})
        estado.recalcular(cliente, i["sprint_id"])
    return ok


def regenerar(cliente, cp_id):
    """Sesión nueva a partir de la actual (misma idea y prompt), QA y revisión
    en blanco; la sesión anterior queda en `extra.cf_anteriores`. Gasta.

    El vínculo `cf_id` viejo -> nuevo es un compare-and-swap
    (`datos.reclamar_cf(..., esperado=i["cf_id"])`): si entre el `duplicar` y
    este punto otra llamada (doble clic, dos pestañas) ya regeneró la misma
    idea, el `cf_id` actual ya no es el que leímos y el swap falla — la
    sesión duplicada de acá se archiva sin encolarse nunca, en vez de dejar
    dos regeneraciones corriendo para la misma idea (double spend)."""
    i = _idea_con_sesion(cliente, cp_id)
    nuevo = creative_flow.duplicar(cliente, i["cf_id"])
    if not datos.reclamar_cf(cliente, cp_id, nuevo, esperado=i["cf_id"]):
        creative_flow.archivar_concepto(cliente, nuevo, "regeneración duplicada")
        raise datos.ErrorDatos("Esa pieza ya se está regenerando.")
    extra = dict(i.get("extra") or {})
    extra["cf_anteriores"] = list(extra.get("cf_anteriores") or []) + [i["cf_id"]]
    datos.actualizar_idea(cliente, cp_id, qa=None, revision="pendiente", revision_motivo=None, extra=extra)
    entry = creative_flow.cargar(cliente)[nuevo]
    if not flowplus_lanzar.lanzar(cliente, nuevo, entry, prioridad=PRIORIDAD_LOTE):
        raise datos.ErrorDatos("No se pudo encolar la regeneración.")
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_regenerada", f"Regeneración de «{i['titulo']}»",
                           {"cp_id": cp_id, "cf_id": nuevo, "anterior": i["cf_id"]}, campana_id=i["campana_id"])
    datos.actualizar_extra_sprint(cliente, i["sprint_id"], lambda extra: {**extra, "lote_en_curso": True})
    estado.recalcular(cliente, i["sprint_id"])
    return nuevo


# ------------------------------------------------------------ progreso ---

def pieza_viva(p):
    """True mientras la pieza no terminó: sesión pendiente/generando, o una
    reserva viva (todavía sin sesión de Crear, estado None). Una reserva
    vencida no es viva: la idea volvió a ser «aprobada sin sesión»."""
    est = p.get("estado")
    if est in ("pendiente", "generando"):
        return True
    return est is None and es_reserva(p.get("cf_id")) and not reserva_vencida(p.get("cf_id"))


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
        elif pieza_viva(p):
            tarea = {} if est is None else (cola.consultar_por_job(flowplus_lanzar.job_id(p["cliente"], p["cf_id"])) or {})
            if tarea.get("estado") == "en_curso":
                r["generando"] += 1
            else:
                r["encoladas"] += 1
            r["segundos_restantes"] += SEGUNDOS_VIDEO if p.get("tipo") == "video" else SEGUNDOS_IMAGEN
    r["costo_usd"] = round(r["costo_usd"], 4)
    r["en_curso"] = (r["encoladas"] + r["generando"]) > 0
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
