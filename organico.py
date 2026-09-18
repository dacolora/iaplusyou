"""
Publicación orgánica de una pieza (bloque 7): la ganadora de un experimento,
o cualquier final que la persona elija, sale como contenido orgánico en
Instagram Reels, Facebook (Página), TikTok y YouTube Shorts.

Una fila de `publicacion` por (pieza, plataforma), con el texto que se
publicó, el id que devolvió la plataforma, la URL pública y el estado
(`en_cola` -> `publicando` -> `publicada` | `error`). Nunca dos veces la
misma pieza en la misma plataforma mientras haya una publicación viva
(índice único parcial `uq_publicacion_viva`, migración 0009).

Publicar es público e irreversible: este módulo NO decide cuándo publicar.
Solo `publicar(cliente, pub_ids)` — llamado por la tarea del worker
`organico_publicar`, que a su vez solo se encola con un clic o en modo
`auto` — toca las plataformas. `redactar` (texto con Claude, con fallback
determinista) y `canales` (qué plataformas tiene conectadas el proyecto)
son de solo lectura.

Reutiliza `publicador._publicar_una` + `uploaders/` tal cual: una falla en
una plataforma no frena las demás y nunca se guarda un token en `error` ni
en eventos (`cola.sin_token`).
"""
import logging
import os
import re

import requests
import sqlalchemy as sa

import cola
import db
import experimentos
import meta_conexion
import publicador
import tiendas

log = logging.getLogger("creatv.organico")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PLATAFORMAS = {
    "instagram": {"nombre": "Instagram Reels", "links": False, "max_caption": 2200},
    "facebook": {"nombre": "Facebook (Página)", "links": True, "max_caption": 5000},
    "tiktok": {"nombre": "TikTok", "links": False, "max_caption": 2200, "max_titulo": 150},
    "youtube": {"nombre": "YouTube Shorts", "links": True, "max_caption": 5000, "max_titulo": 100},
}
ORDEN = ("instagram", "facebook", "tiktok", "youtube")
ESTADOS = ("en_cola", "publicando", "publicada", "error")
ESTADOS_VIVOS = ("en_cola", "publicando", "publicada")
ORIGENES = ("manual", "ganador")
HASHTAGS_MIN, HASHTAGS_MAX = 3, 8
MAX_TITULO_COLUMNA = 150

_COLS_ACTUALIZABLES = ("estado", "caption", "titulo", "id_externo", "url", "error", "publicado_en",
                       "origen", "extra", "experimento_pieza_id")
_RE_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_RE_HASHTAG = re.compile(r"#[\wÀ-ɏ]+")
_RE_COLA_HASHTAGS = re.compile(r"(?:\s*#[\wÀ-ɏ]+)+\s*$")
_RE_SHORTCODE_IG = re.compile(r"^[A-Za-z0-9_-]{5,20}$")
_RE_PALABRA = re.compile(r"[A-Za-zÀ-ɏ0-9]+")
_STOPWORDS = {"de", "del", "la", "el", "los", "las", "con", "para", "por", "sin", "the", "and", "of", "for",
              "un", "una", "unos", "unas", "en", "y", "o", "a", "al", "lo", "que", "se", "su", "sus"}

# Copy fija que `fallback`/`ajustar` inyectan, en el idioma de la pieza
# (`contexto["idioma"]`); español por defecto si no hay traducción.
_COPY = {
    "es": {"link_bio": "Link en bio.", "cta": "Consíguelo aquí"},
    "en": {"link_bio": "Link in bio.", "cta": "Get it here"},
    "pt": {"link_bio": "Link na bio.", "cta": "Garanta o seu"},
}


def _copy(idioma):
    return _COPY.get((idioma or "es").strip().lower(), _COPY["es"])


# ---------- carpetas del proyecto ----------

def _dir_cliente(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente)


def _token_paths(cliente):
    d = _dir_cliente(cliente)
    return {"youtube": os.path.join(d, "token_youtube.json"), "tiktok": os.path.join(d, "token_tiktok.json")}


def _dir_salidas(cliente):
    return os.path.join(BASE_DIR, "salidas", cliente, "organico")


# ---------- canales ----------

def canales(cliente):
    """[{"plataforma", "nombre", "disponible", "motivo"}] en el orden de
    ORDEN. `motivo` (español) explica cómo activar el canal cuando no está
    disponible; "" cuando sí lo está."""
    meta = meta_conexion.cargar(cliente) or {}
    tiene_pagina = bool(meta.get("page_access_token") and meta.get("page_id"))
    tokens = _token_paths(cliente)
    out = []
    for p in ORDEN:
        disponible, motivo = True, ""
        if p == "facebook" and not tiene_pagina:
            disponible, motivo = False, "Conecta Meta con una Página"
        elif p == "instagram":
            if not tiene_pagina:
                disponible, motivo = False, "Conecta Meta con una Página"
            elif not meta.get("ig_user_id"):
                disponible, motivo = False, "La cuenta de Instagram no está vinculada a la Página"
        elif p == "youtube" and not os.path.exists(tokens["youtube"]):
            disponible, motivo = False, "Falta token_youtube.json (autoriza desde tu Mac con auth/auth_youtube.py)"
        elif p == "tiktok" and not os.path.exists(tokens["tiktok"]):
            disponible, motivo = False, "Falta token_tiktok.json (autoriza desde tu Mac con auth/auth_tiktok.py)"
        out.append({"plataforma": p, "nombre": PLATAFORMAS[p]["nombre"], "disponible": disponible, "motivo": motivo})
    return out


def disponibles(cliente):
    """Solo las claves de plataforma con canal disponible."""
    return [c["plataforma"] for c in canales(cliente) if c["disponible"]]


# ---------- filas ----------

def _a_dict(f):
    m = f._mapping
    p = db.publicacion
    d = {c: m[p.c[c]] for c in ("id", "cliente", "creado_en", "actualizado_en", "pieza_id", "experimento_pieza_id",
                                  "plataforma", "estado", "caption", "titulo", "id_externo", "url", "error",
                                  "publicado_en", "origen")}
    d["extra"] = m[p.c.extra] or {}
    d["nombre_plataforma"] = PLATAFORMAS.get(d["plataforma"], {}).get("nombre", d["plataforma"])
    return d


def _fila_pieza(con, cliente, pieza_id):
    return con.execute(sa.select(db.pieza).where(db.pieza.c.id == pieza_id, db.pieza.c.cliente == cliente)).first()


def crear(cliente, pieza_id, plataforma, caption, titulo=None, origen="manual", ep_id=None):
    """Una publicación `en_cola` para (pieza, plataforma). ValueError si la
    plataforma no existe, la pieza no es del cliente, el `ep_id` no es de
    ese cliente/pieza, o ya hay una publicación viva (en cola, publicándose
    o publicada) de esa pieza en esa plataforma. Devuelve el id."""
    if plataforma not in PLATAFORMAS:
        raise ValueError(f"Plataforma desconocida: {plataforma}")
    if origen not in ORIGENES:
        raise ValueError(f"Origen desconocido: {origen}")
    caption = (caption or "").strip()
    if not caption:
        raise ValueError("El texto de la publicación no puede estar vacío.")
    titulo = (titulo or "").strip()[:MAX_TITULO_COLUMNA] or None
    nombre = PLATAFORMAS[plataforma]["nombre"]
    p = db.publicacion
    with db.conectar() as con:
        if _fila_pieza(con, cliente, pieza_id) is None:
            raise ValueError("Esa pieza no existe en este proyecto.")
        if ep_id is not None:
            ep = con.execute(sa.select(db.experimento_pieza.c.pieza_id).where(
                db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente)).first()
            if ep is None or ep[0] != pieza_id:
                raise ValueError("Esa pieza no está en el experimento.")
        viva = con.execute(sa.select(p.c.id).where(
            p.c.cliente == cliente, p.c.pieza_id == pieza_id, p.c.plataforma == plataforma,
            p.c.estado.in_(ESTADOS_VIVOS))).first()
        if viva:
            raise ValueError(f"Esa pieza ya está publicada (o en cola) en {nombre}.")
        ahora = db.ahora()
        try:
            return con.execute(p.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, pieza_id=pieza_id,
                experimento_pieza_id=ep_id, plataforma=plataforma, estado="en_cola", caption=caption,
                titulo=titulo, origen=origen, extra={})).inserted_primary_key[0]
        except sa.exc.IntegrityError:
            # Dos procesos crearon a la vez: gana el índice único parcial.
            raise ValueError(f"Esa pieza ya está publicada (o en cola) en {nombre}.") from None


def actualizar(cliente, pub_id, **campos):
    """Actualiza columnas de una publicación del cliente. False si no existe."""
    malos = set(campos) - set(_COLS_ACTUALIZABLES)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    if "estado" in campos and campos["estado"] not in ESTADOS:
        raise ValueError(f"Estado desconocido: {campos['estado']}")
    if "titulo" in campos and campos["titulo"] is not None:
        campos["titulo"] = str(campos["titulo"])[:MAX_TITULO_COLUMNA]
    if "error" in campos and campos["error"] is not None:
        campos["error"] = cola.recortar(cola.sin_token(campos["error"]), 1000)
    p = db.publicacion
    with db.conectar() as con:
        r = con.execute(p.update().where(p.c.id == pub_id, p.c.cliente == cliente)
                        .values(actualizado_en=db.ahora(), **campos))
        return r.rowcount > 0


def obtener(cliente, pub_id):
    p = db.publicacion
    with db.conectar() as con:
        f = con.execute(sa.select(p).where(p.c.id == pub_id, p.c.cliente == cliente)).first()
    return _a_dict(f) if f else None


def listar(cliente, pieza_id=None, ep_id=None):
    """Publicaciones del cliente (todas, o de una pieza / de una pieza de
    experimento), en orden de creación."""
    p = db.publicacion
    cond = [p.c.cliente == cliente]
    if pieza_id is not None:
        cond.append(p.c.pieza_id == pieza_id)
    if ep_id is not None:
        cond.append(p.c.experimento_pieza_id == ep_id)
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(sa.select(p).where(*cond).order_by(p.c.id))]


def por_pieza(cliente):
    """{pieza_id: [publicaciones]} de todo el cliente, en UNA consulta —
    lo que Experimentos y Crear necesitan para pintar el estado al lado de
    cada pieza."""
    out = {}
    for pub in listar(cliente):
        out.setdefault(pub["pieza_id"], []).append(pub)
    return out


def ganadoras_sin_publicar(cliente):
    """Piezas con veredicto `ganador` en experimentos no cerrados que no
    tienen publicación viva (en cola, publicándose o publicada) en NINGUNA
    plataforma disponible. Devuelve los dicts de pieza de experimentos.piezas
    más `experimento_id`/`experimento_nombre`. Si el proyecto no tiene
    ningún canal disponible devuelve [] (no hay dónde publicar)."""
    disp = set(disponibles(cliente))
    if not disp:
        return []
    pubs = por_pieza(cliente)
    out = []
    for ex in experimentos.cargar(cliente):
        if ex["estado"] == "cerrado":
            continue
        for pz in ex["piezas"]:
            if pz.get("veredicto") != "ganador" or not pz.get("pieza_id"):
                continue
            vivas = {pub["plataforma"] for pub in pubs.get(pz["pieza_id"], []) if pub["estado"] in ESTADOS_VIVOS}
            if vivas & disp:
                continue
            out.append(dict(pz, experimento_id=ex["id"], experimento_nombre=ex["nombre"]))
    return out


# ---------- redacción ----------

def _guion_texto(guion):
    """Líneas `rol: texto` del guion de una final ({bloques: [{rol,
    texto_pantalla, texto_voz}]}); "" si no hay."""
    if not isinstance(guion, dict):
        return ""
    lineas = []
    for b in guion.get("bloques") or []:
        if not isinstance(b, dict):
            continue
        texto = (b.get("texto_pantalla") or b.get("texto_voz") or "").strip()
        if texto:
            lineas.append(f"{b.get('rol') or 'bloque'}: {texto}")
    return "\n".join(lineas)


def _hashtags_de(nombre, n=HASHTAGS_MIN):
    """Hasta n hashtags a partir de las palabras del nombre del producto
    (sin stopwords, sin acentos ni espacios, en minúscula) + uno con el
    nombre completo pegado si tiene más de una palabra."""
    palabras = [w for w in _RE_PALABRA.findall(nombre or "")
                if w.lower() not in _STOPWORDS and len(w) >= 3 and not w.isdigit()]
    tags = []
    for w in palabras:
        t = "#" + _sin_acentos(w).lower()
        if t not in tags:
            tags.append(t)
    if len(palabras) > 1:
        t = "#" + "".join(_sin_acentos(w).lower() for w in palabras)
        if t not in tags and len(t) <= 40:
            tags.append(t)
    return tags[:n]


def _sin_acentos(texto):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def contexto_pieza(cliente, pieza_id):
    """Lo que redactar necesita: guion de la pieza (final: `pieza.guion`;
    clon: `concepto.extra.accion_central`), producto (tiendas.por_activo
    por el primer `productos_ids` del concepto, o el nombre del catálogo),
    `url_compra` (del producto, o `destino_url` del último experimento que
    contiene la pieza), idioma y hashtags base."""
    with db.conectar() as con:
        pz = _fila_pieza(con, cliente, pieza_id)
        if pz is None:
            raise ValueError("Esa pieza no existe en este proyecto.")
        cp = con.execute(sa.select(db.concepto).where(db.concepto.c.id == pz._mapping[db.pieza.c.concepto_id])).first()
        ex = con.execute(sa.select(db.experimento.c.destino_url, db.experimento.c.producto_id)
                         .select_from(db.experimento_pieza.join(db.experimento, db.experimento.c.id == db.experimento_pieza.c.experimento_id))
                         .where(db.experimento_pieza.c.pieza_id == pieza_id, db.experimento_pieza.c.cliente == cliente)
                         .order_by(db.experimento_pieza.c.id.desc())).first()
    pm = pz._mapping
    c_extra = (cp._mapping[db.concepto.c.extra] or {}) if cp else {}
    accion = (c_extra.get("accion_central") or "").strip()
    guion_texto = _guion_texto(pm[db.pieza.c.guion]) or (f"hook: {accion}" if accion else "")

    producto = None
    activos = [a for a in (c_extra.get("productos_ids") or []) if a]
    if activos:
        mapa = tiendas.por_activo(cliente)
        for a in activos:
            if a in mapa:
                producto = mapa[a]
                break
    if producto is None and ex and ex[1]:
        producto = tiendas.producto(cliente, ex[1])
    nombre, descripcion, url_compra = "", "", None
    if producto:
        nombre = producto.get("nombre") or ""
        descripcion = producto.get("descripcion") or ""
        url_compra = producto.get("url_compra") or None
    elif activos:
        try:
            import catalogo_productos
            act = catalogo_productos.encontrar(cliente, activos[0])
            if act:
                nombre, descripcion = act.get("nombre") or "", act.get("descripcion") or ""
        except Exception:  # noqa: BLE001 — el catálogo en disco es opcional para redactar
            pass
    if not nombre:
        nombre = accion or f"Pieza {pieza_id}"
    if not url_compra and ex and ex[0]:
        url_compra = ex[0]
    idioma = pm[db.pieza.c.idioma] or (cp._mapping[db.concepto.c.idioma_base] if cp else None) or "es"
    return {"nombre_producto": nombre, "descripcion": descripcion, "url_compra": url_compra, "idioma": idioma,
            "guion_texto": guion_texto, "hashtags_base": _hashtags_de(nombre)}


def _hook(contexto):
    for linea in (contexto.get("guion_texto") or "").splitlines():
        _, _, texto = linea.partition(":")
        if texto.strip():
            return texto.strip()
    return contexto.get("nombre_producto") or ""


def fallback(contexto, plataforma):
    """Texto determinista sin Claude: gancho del guion + CTA + hashtags
    del nombre del producto."""
    conf = PLATAFORMAS[plataforma]
    copy = _copy(contexto.get("idioma"))
    nombre = contexto.get("nombre_producto") or ""
    hook = _hook(contexto) or nombre
    if conf["links"] and contexto.get("url_compra"):
        cta = f"{copy['cta']}: {contexto['url_compra']}"
    elif conf["links"]:
        cta = "Escríbenos para conseguirlo."
    else:
        cta = copy["link_bio"]
    tags = " ".join(_hashtags_de(nombre) or ["#reels", "#tiktok", "#shorts"][:HASHTAGS_MIN])
    caption = f"{hook}\n\n{cta}\n\n{tags}"
    return {"titulo": (nombre or hook), "caption": caption}


def _separar_cola(caption):
    """(cuerpo, [hashtags del bloque final]) — los hashtags que cierran el
    texto se tratan aparte para que los recortes no se los coman."""
    m = _RE_COLA_HASHTAGS.search(caption)
    if not m or not m.group(0).strip():
        return caption.strip(), []
    return caption[:m.start()].rstrip(), _RE_HASHTAG.findall(m.group(0))


def _sin_repetidos(tags, ya=()):
    vistos = {t.lower() for t in ya}
    out = []
    for t in tags:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            out.append(t)
    return out


def _recortar_en_palabra(texto, tope):
    """Corta `texto` a lo sumo `tope` caracteres, nunca a mitad de palabra ni
    de #hashtag: si el corte cae dentro de una palabra (o un hashtag), esa
    palabra/hashtag parcial se descarta entera en vez de quedar truncada."""
    if len(texto) <= tope:
        return texto
    corte = texto[:tope]
    if tope < len(texto) and texto[tope] not in (" ", "\n") and (" " in corte or "\n" in corte):
        ultimo = max(corte.rfind(" "), corte.rfind("\n"))
        corte = corte[:ultimo]
    return corte.rstrip()


def ajustar(plataforma, titulo, caption, contexto):
    """Reglas duras por plataforma sobre un texto (de Claude o de la
    persona): sin URLs donde `links=False` (+ "Link en bio."), con
    `url_compra` donde `links=True` si existe y no está, hashtags entre 3 y
    8, recortes a los máximos (el cuerpo, nunca el bloque de hashtags)."""
    conf = PLATAFORMAS[plataforma]
    copy = _copy(contexto.get("idioma"))
    caption = (caption or "").strip()
    titulo = (titulo or "").strip()
    habia_url = False
    if not conf["links"]:
        habia_url = bool(_RE_URL.search(caption))
        caption = _RE_URL.sub("", caption)
        caption = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", caption)).strip()
    cuerpo, cola_tags = _separar_cola(caption)
    if not conf["links"]:
        if (habia_url or contexto.get("url_compra")) and copy["link_bio"].lower() not in cuerpo.lower():
            cuerpo = f"{cuerpo}\n\n{copy['link_bio']}" if cuerpo else copy["link_bio"]
    elif contexto.get("url_compra") and contexto["url_compra"] not in cuerpo:
        cuerpo = f"{cuerpo}\n\n{contexto['url_compra']}" if cuerpo else contexto["url_compra"]

    en_cuerpo = _sin_repetidos(_RE_HASHTAG.findall(cuerpo))
    cola_tags = _sin_repetidos(cola_tags, ya=en_cuerpo)
    total = len(en_cuerpo) + len(cola_tags)
    if total < HASHTAGS_MIN:
        nuevos = _sin_repetidos(_hashtags_de(contexto.get("nombre_producto") or "", HASHTAGS_MAX), ya=en_cuerpo + cola_tags)
        cola_tags += nuevos[:HASHTAGS_MIN - total]
    elif total > HASHTAGS_MAX:
        cola_tags = cola_tags[:max(HASHTAGS_MAX - len(en_cuerpo), 0)]
        for t in en_cuerpo[HASHTAGS_MAX:]:
            cuerpo = re.sub(r"\s*" + re.escape(t) + r"(?![\wÀ-ɏ])", "", cuerpo)

    tags_str = " ".join(cola_tags)
    tope = conf["max_caption"]
    if tags_str and len(cuerpo) + len(tags_str) + 2 > tope:
        cuerpo = _recortar_en_palabra(cuerpo, max(tope - len(tags_str) - 2, 0))
    elif not tags_str and len(cuerpo) > tope:
        cuerpo = _recortar_en_palabra(cuerpo, tope)
    caption = f"{cuerpo}\n\n{tags_str}" if (cuerpo and tags_str) else (cuerpo or tags_str)
    caption = _recortar_en_palabra(caption.strip(), tope)

    if not titulo:
        titulo = _hook(contexto) or contexto.get("nombre_producto") or ""
    titulo = titulo[:conf.get("max_titulo", MAX_TITULO_COLUMNA)].strip()
    return {"titulo": titulo, "caption": caption}


def redactar(cliente, pieza_id, plataformas):
    """{plataforma: {"titulo", "caption", "extra": {"fallback": bool}}} para
    la pieza: UNA llamada a Claude (generador_prompts.caption_organico) y,
    ante cualquier fallo (se registra con logging, nunca se traga en
    silencio) o plataforma que Claude no devolvió, el fallback determinista
    — marcado con `extra.fallback=True` en esa plataforma. Todo pasa por
    `ajustar` (URLs, hashtags, máximos). No escribe nada."""
    plataformas = [p for p in plataformas if p in PLATAFORMAS]
    if not plataformas:
        raise ValueError("Elige al menos una plataforma.")
    contexto = contexto_pieza(cliente, pieza_id)
    try:
        import generador_prompts
        textos = generador_prompts.caption_organico(contexto, plataformas)
        if not isinstance(textos, dict):
            textos = {}
    except Exception as e:  # noqa: BLE001 — sin Claude igual hay texto (fallback)
        log.warning("redactar %s/%s: Claude falló, uso el fallback determinista: %s",
                    cliente, pieza_id, e, exc_info=True)
        textos = {}
    out = {}
    for p in plataformas:
        t = textos.get(p) if isinstance(textos.get(p), dict) else None
        uso_fallback = not t or not (t.get("caption") or "").strip()
        if uso_fallback:
            t = fallback(contexto, p)
        ajustado = ajustar(p, t.get("titulo"), t.get("caption"), contexto)
        ajustado["extra"] = {"fallback": uso_fallback}
        out[p] = ajustado
    return out


# ---------- publicación ----------

def _descargar(url, destino):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    return destino


def url_publica(plataforma, id_externo):
    """(id_externo, url) a partir de lo que devolvió el uploader. Instagram
    solo tiene URL si el id parece un shortcode (media_id numérico no
    sirve para armarla); TikTok devuelve un publish_id sin URL."""
    id_externo = str(id_externo or "").strip() or None
    if not id_externo:
        return None, None
    if plataforma == "facebook":
        return id_externo, f"https://www.facebook.com/{id_externo}"
    if plataforma == "youtube":
        return id_externo, f"https://youtu.be/{id_externo}"
    if plataforma == "instagram" and _RE_SHORTCODE_IG.match(id_externo) and not id_externo.isdigit():
        return id_externo, f"https://www.instagram.com/p/{id_externo}"
    return id_externo, None


def _evento(cliente, pub, tipo, mensaje, datos=None):
    ep_id = pub.get("experimento_pieza_id")
    if not ep_id:
        return
    eid = experimentos.experimento_de_pieza(cliente, ep_id)
    if eid:
        experimentos.registrar_evento(cliente, eid, tipo, cola.sin_token(mensaje), datos or {}, ep_id=ep_id)


def publicar(cliente, pub_ids, on_etapa=None):
    """Publica las publicaciones `en_cola`/`error` indicadas (ids del
    cliente), agrupadas por pieza: descarga el mp4 UNA vez por pieza a
    salidas/<c>/organico/<pieza_id>.mp4, llama a publicador._publicar_una
    por plataforma, guarda id_externo/url y borra el mp4 al terminar. Una
    falla en una plataforma no frena las demás. Devuelve {"ok": [ids],
    "error": [ids]}. `on_etapa(nombre)` se llama al descargar y antes de
    cada plataforma (nombres "Descargando" y "Publicando", los mismos que las
    etapas de la tarea del worker)."""
    avisar = on_etapa or (lambda nombre: None)
    pubs = [obtener(cliente, i) for i in pub_ids]
    pubs = [p for p in pubs if p and p["estado"] != "publicada"]
    resultado = {"ok": [], "error": []}
    if not pubs:
        return resultado
    grupos = {}
    for pub in pubs:
        grupos.setdefault(pub["pieza_id"], []).append(pub)
    token_paths = _token_paths(cliente)

    for pieza_id, grupo in grupos.items():
        with db.conectar() as con:
            pz = _fila_pieza(con, cliente, pieza_id)
        video_url = pz._mapping[db.pieza.c.url_video] if pz is not None else None
        local = os.path.join(_dir_salidas(cliente), f"{pieza_id}.mp4")
        try:
            avisar("Descargando")
            try:
                if not video_url:
                    raise RuntimeError("La pieza no tiene video.")
                _descargar(video_url, local)
            except Exception as e:  # noqa: BLE001 — sin video no hay nada que publicar en ninguna plataforma
                for pub in grupo:
                    _fallar(cliente, pub, f"No pude descargar el video: {e}", resultado)
                continue
            for pub in grupo:
                p = pub["plataforma"]
                nombre = PLATAFORMAS.get(p, {}).get("nombre", p)
                avisar("Publicando")
                actualizar(cliente, pub["id"], estado="publicando", error=None)
                # TikTok no tiene un campo de caption separado: `title` ES el
                # texto de la publicación (post_info.title), así que ahí va
                # el caption completo (gancho + Link en bio. + hashtags), no
                # el `titulo` corto que sí usan YouTube/Facebook.
                titulo_envio = pub["caption"] if p == "tiktok" else (pub["titulo"] or "")
                entry = {"video_local": local, "video_url": video_url, "title": titulo_envio,
                         "caption": pub["caption"] or "", "platforms": [p]}
                try:
                    devuelto = publicador._publicar_una(p, entry, cliente, token_paths)
                    id_externo, url = url_publica(p, devuelto)
                    actualizar(cliente, pub["id"], estado="publicada", id_externo=id_externo, url=url,
                               error=None, publicado_en=db.ahora())
                    resultado["ok"].append(pub["id"])
                    _evento(cliente, pub, "publicacion", f"Publicada en {nombre}" + (f": {url}" if url else ""),
                            {"plataforma": p, "id_externo": id_externo, "url": url, "publicacion_id": pub["id"]})
                except Exception as e:  # noqa: BLE001 — una plataforma no frena a las demás
                    _fallar(cliente, pub, str(e), resultado)
        finally:
            if os.path.exists(local):
                try:
                    os.remove(local)
                except OSError:
                    pass
    return resultado


def _fallar(cliente, pub, error, resultado):
    texto = cola.recortar(cola.sin_token(error), 1000)
    actualizar(cliente, pub["id"], estado="error", error=texto)
    resultado["error"].append(pub["id"])
    nombre = PLATAFORMAS.get(pub["plataforma"], {}).get("nombre", pub["plataforma"])
    _evento(cliente, pub, "error", f"No se pudo publicar en {nombre}: {texto}",
            {"plataforma": pub["plataforma"], "publicacion_id": pub["id"]})


def interrumpir(cliente, pub_ids):
    """Hook `al_interrumpir` de la tarea del worker: lo que quedó
    `publicando` pasa a `error` (no sabemos si la plataforma lo recibió)."""
    p = db.publicacion
    with db.conectar() as con:
        con.execute(p.update().where(p.c.cliente == cliente, p.c.id.in_(list(pub_ids)), p.c.estado == "publicando")
                    .values(actualizado_en=db.ahora(), estado="error",
                            error="La publicación se interrumpió antes de terminar; revisa la plataforma antes de reintentar."))
