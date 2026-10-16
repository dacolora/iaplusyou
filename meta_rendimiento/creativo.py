"""Los medios de UN anuncio de Meta para «Cómo mejorarlo» (spec 2026-10-09 §6 E2, A1 y A6; plan E2, tarea 1).

Un anuncio de una cuenta de Meta sin tienda de Triple Whale no trae su imagen, su video ni su texto en ninguna copia:
la tarea pagada (`tareas.triple_whale.tw_analizar_anuncio`) los pide aquí UNA vez, cuando la foto es de fuente Meta y
todavía no tiene creativo. Lo que devuelve tiene la forma de `triple_whale.datos.COLUMNAS_CREATIVO`, así el resto de la
tarea (visuales, voz, prompt) no distingue la fuente.

- Lectura con el token del proyecto (`meta_conexion.cargar`, funciona sin Página) y `meta_rendimiento.graph` (token
  explícito, nunca `meta_ads.auth`). Leer no cobra. Un id que no son dígitos nunca se usa como edge (el token viajaría
  a esa ruta de Graph), como el `report_run_id` de `graph.informe`.
- La imagen y el video se COPIAN a R2 (`clientes/<cliente>/rendimiento/a<analisis>_<ad>.jpg|.mp4`): las URL de Meta
  caducan y `triple_whale.medio_permitido` solo deja bajar o mandar a Claude y a fal lo que está en R2 o en Triple
  Whale. Se bajan con `conectores.url.descargar_archivo` (guarda de SSRF en cada redirección, tope de tamaño y de
  tiempo) y solo de hosts de Meta: la imagen si pasa `datos.miniatura_valida`, el video si su host termina en
  `.fbcdn.net` (`video_valido`). El video además tiene que ser mp4/mov según ffprobe (`mejorar.es_mp4`).
- Nunca lanza: lo que falla queda en None y se anota en el log solo con el tipo del error (el texto de una excepción
  de `requests` trae la URL con `access_token`). Si no llegó nada que mirar (`sin_contenido`), la tarea termina en
  error sin cobrar en vez de pagarle a Claude un análisis a ciegas. Un límite de uso de Meta tampoco toca la pausa compartida de la copia
  (`pausa.pausar`): son dos o tres lecturas por análisis pagado.
"""
import logging
import os
import tempfile
from urllib.parse import urlsplit

import meta_conexion
from conectores import url as conector_url
from meta_rendimiento import datos, graph
from storage import r2_pendientes, r2_uploader
from triple_whale import analisis, mejorar
from triple_whale import datos as tw_datos

log = logging.getLogger("creatv.meta_rendimiento.creativo")

CAMPOS_ANUNCIO = ("creative{id,body,title,thumbnail_url,image_url,video_id,object_type,call_to_action_type,"
                  "object_story_spec,asset_feed_spec}")
CAMPOS_VIDEO = "source,length"
# `thumbnail_url` sale de 64 px si no se piden medidas: cuando el creativo no trae `image_url` (anuncios con
# `image_hash`, videos, catálogos) se pide la miniatura grande al creativo, como `triple_whale.analisis.medios_meta`.
LADO_MINIATURA = 600
MAX_TITULO = 300        # como tw_creativo (`triple_whale.sync.normalizar_creativo`)
MAX_COPY = 3000
MAX_CTA = 60
MAX_BYTES_IMAGEN = 8 * 1024 * 1024
FORMATOS_IMAGEN = ("JPEG", "PNG", "WEBP", "GIF")
TIMEOUT_GRAPH = 20


CAMPOS_CONTENIDO = ("copy", "titulo", "imagen_url", "video_url")


def sin_contenido(creativo):
    """True si el creativo no trae nada que Claude pueda mirar: ni texto ni imagen ni video (`tipo`, `cta` o la duración
    solos no bastan). Con un creativo así la tarea pagada no llama a Whisper ni a Claude."""
    c = creativo if isinstance(creativo, dict) else {}
    return not any(c.get(k) for k in CAMPOS_CONTENIDO)


def clave_r2(cliente, analisis_id, ad_id, extension):
    return f"clientes/{cliente}/rendimiento/a{int(analisis_id)}_{ad_id}.{extension}"


def claves_de_analisis(cliente, filas):
    """Las claves de R2 que `traer` pudo copiar para esos análisis ([(analisis_id, ad_id)]): la imagen Y el video de
    cada uno (borrar una clave que no existe no es un error, y la tarea pudo copiar uno antes de fallar)."""
    claves = []
    for analisis_id, ad_id in filas or []:
        ad = _id(ad_id)
        if ad:
            claves += [clave_r2(cliente, analisis_id, ad, "jpg"), clave_r2(cliente, analisis_id, ad, "mp4")]
    return claves


def borrar_copias(cliente, filas):
    """Borra de R2 la imagen y el video que `traer` copió para esos análisis ([(analisis_id, ad_id)]), con un solo
    cliente de R2. S1 (revisión final de Rendimiento E2, 2026-10-10): soltar una cuenta de Meta borra lo que copió
    «Cómo mejorarlo»; se llama DESPUÉS de borrar las filas (`triple_whale.datos.borrar_analisis_meta`), como E2-R2, para
    que un R2 lento o caído nunca deje nombres ni cifras guardados. Nunca lanza: (borradas, fallos) con `fallos` = el
    tipo de cada error (nunca su texto); sin R2 configurado, todas fallan. Las claves que fallaron ya no salen de
    ninguna fila: se anotan en `r2_pendientes` y la limpieza diaria las reintenta (PND-295, 2026-10-12)."""
    claves = claves_de_analisis(cliente, filas)
    if not claves:
        return 0, []
    try:
        borradas, detalle = r2_uploader.delete_files_detalle(claves)
        fallos, pendientes = [tipo for _, tipo in detalle], [clave for clave, _ in detalle]
    except Exception as e:  # noqa: BLE001 — R2 sin configurar o caído: quien suelta la cuenta sigue y avisa
        borradas, fallos, pendientes = 0, [type(e).__name__] * len(claves), claves
    if fallos:
        log.warning("no se pudieron borrar %s copia(s) de anuncios de Meta en R2 (%s)", len(fallos),
                    ", ".join(sorted(set(fallos))))
        r2_pendientes.anotar(pendientes)       # nunca lanza
    return borradas, fallos


def video_valido(url):
    """True si `url` es un video de Meta que el servidor puede bajar: https, sin usuario ni puerto raro, host que
    termina en `.fbcdn.net` y sin `access_token` en ninguna parte."""
    if not isinstance(url, str) or not url or "access_token" in url.lower():
        return False
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    return (partes.scheme == "https" and not partes.username and not partes.password and puerto in (None, 443)
            and host.endswith(".fbcdn.net"))


def _id(valor):
    """El id tal cual si son solo dígitos ASCII (lo único que se usa como edge de Graph); si no, None."""
    texto = str(valor or "").strip()
    return texto if texto.isascii() and texto.isdigit() else None


def _leer(edge, token, params, que, ad_id):
    """GET de solo lectura; {} si falla. Al log va solo el tipo del error y el código de Meta, nunca su texto."""
    try:
        respuesta = graph.get(edge, token, params, timeout=TIMEOUT_GRAPH)
    except Exception as e:  # noqa: BLE001 — un error de Graph o de red deja esa parte en None
        log.info("Meta no dio %s del anuncio %s: %s (código %s)", que, ad_id, type(e).__name__,
                 getattr(e, "codigo", None))
        return {}
    return respuesta if isinstance(respuesta, dict) else {}


def _dic(valor):
    return valor if isinstance(valor, dict) else {}


def _texto(valor, largo):
    if not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
        return None
    return str(valor).strip()[:largo] or None


def _primero(lista):
    """El `text` del primer elemento con texto de `bodies`/`titles` de un `asset_feed_spec`."""
    for item in lista if isinstance(lista, list) else []:
        if isinstance(item, dict) and _texto(item.get("text"), 1):
            return item.get("text")
    return None


def _primer_video(feed):
    """El `video_id` (solo dígitos) del primer video de un `asset_feed_spec` (creativo dinámico: varios videos,
    imágenes y textos que Meta combina), o None. PND-293: sin esto «Cómo mejorarlo» de un anuncio dinámico juzgaba por
    la miniatura y su precio suponía 30 s de Whisper."""
    for item in feed.get("videos") if isinstance(feed.get("videos"), list) else []:
        video_id = _id(item.get("video_id")) if isinstance(item, dict) else None
        if video_id:
            return video_id
    return None


def _textos(c):
    """(título, copy): los del creativo y, si faltan, los de `object_story_spec` o el primero de `asset_feed_spec`."""
    historia = _dic(c.get("object_story_spec"))
    enlace, video = _dic(historia.get("link_data")), _dic(historia.get("video_data"))
    feed = _dic(c.get("asset_feed_spec"))
    titulo = next((t for t in (_texto(v, MAX_TITULO) for v in (
        c.get("title"), enlace.get("name"), video.get("title"), _primero(feed.get("titles")))) if t), None)
    copy = next((t for t in (_texto(v, MAX_COPY) for v in (
        c.get("body"), enlace.get("message"), video.get("message"), _primero(feed.get("bodies")))) if t), None)
    return titulo, copy


def _duracion(valor):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    return n if n > 0 and n == n and n != float("inf") else None


def _url_imagen(c, token, ad_id):
    """La imagen del creativo que se puede bajar: `image_url` si es de Meta; si no, la miniatura grande del creativo
    o, si esa no llega, la que trajo el anuncio. None si ninguna pasa `datos.miniatura_valida`."""
    if datos.miniatura_valida(c.get("image_url")):
        return c["image_url"]
    creative_id = _id(c.get("id"))
    if creative_id:
        grande = _leer(creative_id, token, {"fields": "thumbnail_url", "thumbnail_width": LADO_MINIATURA,
                                            "thumbnail_height": LADO_MINIATURA}, "la miniatura", ad_id)
        if datos.miniatura_valida(grande.get("thumbnail_url")):
            return grande["thumbnail_url"]
    return c["thumbnail_url"] if datos.miniatura_valida(c.get("thumbnail_url")) else None


def _copiar_imagen(url, clave, ad_id):
    """Baja la imagen (conector con guarda de SSRF), la achica a JPEG del lado del análisis y la sube a R2. None si
    algo falla. Los temporales se borran siempre."""
    from PIL import Image
    fd, crudo = tempfile.mkstemp(prefix="meta_img_", suffix=".img")
    os.close(fd)
    try:
        conector_url.descargar_archivo(url, crudo, max_bytes=MAX_BYTES_IMAGEN, tipos=("image/",))
        with tempfile.TemporaryDirectory(prefix="meta_img_") as carpeta:
            local = os.path.join(carpeta, "imagen.jpg")
            # S3 (revisión final de Rendimiento E2, 2026-10-10): un archivo de un tercero; Pillow abriría cualquier
            # formato que conozca. Solo los de imagen de anuncio; otro sale por el `except` (sin imagen).
            with Image.open(crudo, formats=FORMATOS_IMAGEN) as im:
                im = im.convert("RGB")
                im.thumbnail((analisis.LADO_IMAGEN, analisis.LADO_IMAGEN))
                im.save(local, format="JPEG", quality=85)
            return r2_uploader.upload_image(local, clave)
    except Exception as e:  # noqa: BLE001 — sin imagen, Claude juzga por el video, el texto y los números
        log.info("no pude copiar la imagen del anuncio %s a R2: %s", ad_id, type(e).__name__)
        return None
    finally:
        _borrar(crudo)


def _copiar_video(url, clave, ad_id):
    """Baja el video (conector: SSRF en cada redirección, 60 MB, tope de tiempo), comprueba con ffprobe que sea
    mp4/mov y lo sube a R2. None si algo falla. El temporal se borra siempre."""
    fd, ruta = tempfile.mkstemp(prefix="meta_video_", suffix=".mp4")
    os.close(fd)
    try:
        conector_url.descargar_archivo(url, ruta)
        if not mejorar.es_mp4(ruta):
            log.info("el video del anuncio %s no es mp4 ni mov: no se copia", ad_id)
            return None
        return r2_uploader.upload_video(ruta, clave)
    except Exception as e:  # noqa: BLE001 — sin video queda la imagen
        log.info("no pude copiar el video del anuncio %s a R2: %s", ad_id, type(e).__name__)
        return None
    finally:
        _borrar(ruta)


def _borrar(ruta):
    try:
        os.remove(ruta)
    except OSError:
        pass


def traer(cliente, ad_id, analisis_id):
    """{COLUMNAS_CREATIVO} del anuncio `ad_id` leído con la conexión de Meta del proyecto; `imagen_url` y `video_url`
    son copias en R2 o None. Nunca lanza: lo que no se pudo leer o copiar queda en None."""
    salida = dict.fromkeys(tw_datos.COLUMNAS_CREATIVO)
    ad = _id(ad_id)
    if not ad:
        return salida
    try:
        token = (meta_conexion.cargar(cliente) or {}).get("token")
    except Exception as e:  # noqa: BLE001 — sin conexión legible, el análisis sigue sin medios
        log.info("sin conexión de Meta legible para %s: %s", cliente, type(e).__name__)
        return salida
    if not token:
        return salida
    c = _dic(_leer(ad, token, {"fields": CAMPOS_ANUNCIO}, "el creativo", ad).get("creative"))
    if not c:
        return salida
    salida["titulo"], salida["copy"] = _textos(c)
    salida["cta"] = _texto(c.get("call_to_action_type"), MAX_CTA)
    video_id = _id(c.get("video_id")) or _primer_video(_dic(c.get("asset_feed_spec")))
    es_video = bool(video_id) or str(c.get("object_type") or "").upper() == "VIDEO"
    salida["tipo"] = "video" if es_video else "imagen"
    if video_id:
        video = _leer(video_id, token, {"fields": CAMPOS_VIDEO}, "el video", ad)
        salida["duracion_s"] = _duracion(video.get("length"))
        if video_valido(video.get("source")):
            salida["video_url"] = _copiar_video(video["source"], clave_r2(cliente, analisis_id, ad, "mp4"), ad)
        elif video.get("source"):
            log.info("el video del anuncio %s no viene de un host de Meta: no se baja", ad)
    imagen = _url_imagen(c, token, ad)
    if imagen:
        salida["imagen_url"] = _copiar_imagen(imagen, clave_r2(cliente, analisis_id, ad, "jpg"), ad)
    return salida
