"""Biblioteca del editor (spec editor capa 4b, Task 1): subir un archivo del
proyecto a `material` (video/imagen/audio, gratis), listar lo subido junto
con las piezas de Crear listas para arrastrar al lienzo, y materializar una
pieza de Crear como material bajo pedido — la misma preparación que
`final_edition.edicion_clon.crear` hace con el clon, sin crear ninguna
edición. Único módulo que decide esto: la ruta (`final_edition/rutas_editor.py`)
solo traduce multipart/JSON y el worker (`tareas/edicion.py`) solo valida
`cf_id` y llama a `materializar_pieza`.

Idioma (fase 6): `subir` corre en la ruta, así que sus mensajes salen en el
idioma de quien sube; `materializar_pieza` corre en el worker, en el del
proyecto (`worker.ejecutar`). El nombre de respaldo de un archivo sin
nombre se guarda en el idioma del proyecto."""
import math
import os
import re
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from flask_babel import gettext
from PIL import Image, ImageOps, JpegImagePlugin

import creative_flow
import db
import ediciones
import final_edition
import idiomas
import materiales
import trabajos
from final_edition import cortes, insumos, mezcla, vista_previa
from tareas import edicion as tareas_edicion

# video/imagen/audio (spec §11): extensión -> (tipo de material, content-type
# para R2). Las mismas familias que `materiales.LIMITES` ya soporta.
EXTENSIONES = {
    ".mp4": ("video", "video/mp4"), ".mov": ("video", "video/quicktime"),
    ".webm": ("video", "video/webm"), ".m4v": ("video", "video/x-m4v"),
    ".jpg": ("imagen", "image/jpeg"), ".jpeg": ("imagen", "image/jpeg"),
    ".png": ("imagen", "image/png"), ".webp": ("imagen", "image/webp"),
    ".mp3": ("audio", "audio/mpeg"), ".wav": ("audio", "audio/wav"),
    ".m4a": ("audio", "audio/mp4"), ".aac": ("audio", "audio/aac"), ".ogg": ("audio", "audio/ogg"),
}
# Materiales que la persona puede arrastrar al lienzo: nunca los efímeros
# (png_texto, proxy, tira, forma_onda — `materiales.EFIMEROS`) ni una voz
# sintetizada de un guion que no le pertenece a ella todavía. El logo del
# proyecto se guarda con origen «marca» (`insumos.logo`). Capa 5a (Task 6):
# «grabacion» (el micrófono del editor) y «locucion» (los audios terminados
# de Crear › Audios, voz + música) se suman a la lista.
ORIGENES_BIBLIOTECA = ("subida", "crear", "musica", "voz", "marca", "grabacion", "locucion")
TOPE_MATERIALES = 200


class SubidaInvalida(ValueError):
    """El mensaje va tal cual a la persona."""


# Lo que «Borrar» de la biblioteca puede quitar (capa 4c): lo que la persona
# subió y los videos de Crear ya preparados como material. Nunca una voz de
# guion, el logo (marca) ni una canción de Mi música — creada (origen musica)
# o subida (origen subida con `extra.fuente`, `vista_previa.es_de_mi_musica`):
# esas se borran en Crear › Mi música. Capa 5a (Task 6): una grabación del
# micrófono SÍ se borra desde aquí (es solo suya, como una subida).
ORIGENES_BORRABLES = ("subida", "crear", "grabacion")


class NoSePuedeBorrar(ValueError):
    """El mensaje va tal cual a la persona; `codigo` es el HTTP de la ruta."""

    def __init__(self, mensaje, codigo):
        super().__init__(mensaje)
        self.codigo = codigo


def borrar(cliente, material_id):
    """Borra un material de la biblioteca (gratis): su fila y, si son de este
    proyecto (`materiales.borrar` solo toca claves bajo
    clientes/<c>/materiales/), su archivo, su copia liviana y su tira en R2
    — la fila deja de contar para la cuota. Solo `ORIGENES_BORRABLES`, y solo
    si ninguna edición (viva o congelada) lo usa; si una lo usa, se dice
    cuál. Un fallo de R2 se propaga (la fila queda, para reintentar)."""
    mat = materiales.obtener(cliente, int(material_id))
    if not mat:
        raise NoSePuedeBorrar(gettext("Ese archivo ya no existe."), 404)
    if vista_previa.es_de_mi_musica(mat):
        raise NoSePuedeBorrar(gettext("Esa canción es de Mi música: bórrala en Crear › Mi música."), 400)
    if mat["origen"] not in ORIGENES_BORRABLES:
        raise NoSePuedeBorrar(gettext("Ese archivo no se borra desde aquí."), 400)
    ed = materiales.edicion_que_lo_usa(cliente, mat["id"])
    if ed:
        raise NoSePuedeBorrar(gettext("Está en uso en la edición «%(nombre)s»: quítalo de ahí primero.",
                                      nombre=ediciones.nombre_visible(ed)), 409)
    try:
        materiales.borrar(cliente, mat["id"])
    except materiales.MaterialEnUso:                       # una edición lo tomó recién
        raise NoSePuedeBorrar(gettext("Está en uso en una edición: quítalo de ahí primero."), 409)
    return {"id": mat["id"], "bytes": int(mat.get("bytes") or 0)}


def _carpeta_tmp(cliente):
    carpeta = os.path.join(final_edition.BASE_DIR, "clientes", cliente, "tmp_editor")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


_ORIENTACION = 0x0112     # etiqueta EXIF «Orientation»


def _enderezar(local, ext):
    """Una foto de celular guarda los píxeles de lado y dice en su EXIF cómo
    girarlos (orientación ≠ 1). El editor, el lienzo y el render usan los
    píxeles tal cual, así que se sube una copia YA girada: mismo formato (un
    JPEG conserva sus tablas de calidad; un WebP, calidad 95), sin EXIF (ni la
    orientación, que la volvería a girar, ni la ubicación). Devuelve la ruta de
    esa copia, al lado del temporal, o None si la foto ya está derecha."""
    try:
        with Image.open(local) as im:
            orientacion = im.getexif().get(_ORIENTACION, 1)
            if orientacion in (None, 1):
                return None
            formato = im.format
            opciones = {}
            if im.info.get("icc_profile"):
                opciones["icc_profile"] = im.info["icc_profile"]
            if formato == "JPEG":
                if getattr(im, "quantization", None):
                    opciones["qtables"] = im.quantization
                muestreo = JpegImagePlugin.get_sampling(im)
                if muestreo != -1:
                    opciones["subsampling"] = muestreo
            elif formato == "WEBP":
                opciones["quality"] = 95
            derecha = ImageOps.exif_transpose(im)
            destino = os.path.splitext(local)[0] + f"_derecha{ext}"
            derecha.save(destino, format=formato, **opciones)
        return destino
    except (OSError, ValueError, SyntaxError) as e:
        raise SubidaInvalida(gettext("No pude leer esa imagen.")) from e


def _medir(tipo, local):
    """(duracion_ms, ancho, alto, tiene_audio) según el tipo; `SubidaInvalida`
    si el archivo no se puede leer con ffprobe/Pillow."""
    if tipo == "imagen":
        try:
            with Image.open(local) as im:
                ancho, alto = im.size
                im.verify()
            if ancho <= 0 or alto <= 0:
                raise ValueError(gettext("dimensiones inválidas"))
        except (OSError, ValueError):
            raise SubidaInvalida(gettext("No pude leer esa imagen."))
        return None, ancho, alto, None
    mensaje = gettext("No pude leer ese video.") if tipo == "video" else gettext("No pude leer ese archivo de audio.")
    try:
        info = cortes.ffprobe_json(local)
        streams = info.get("streams") or []
        if tipo == "video":
            v = next((s for s in streams if s.get("codec_type") == "video"
                      and not (s.get("disposition") or {}).get("attached_pic")), None)
            if not v or int(v.get("width") or 0) <= 0 or int(v.get("height") or 0) <= 0:
                raise ValueError(gettext("falta video con dimensiones válidas"))
        elif not any(s.get("codec_type") == "audio" for s in streams):
            raise ValueError(gettext("falta audio"))
        dur_s = cortes.duracion(local)
        if not math.isfinite(dur_s) or dur_s <= 0:
            raise ValueError(gettext("duración inválida"))
        dur_ms = int(round(dur_s * 1000))
        if tipo == "video":
            return dur_ms, int(v["width"]), int(v["height"]), mezcla.tiene_audio(local)
        return dur_ms, None, None, None
    except Exception as e:
        raise SubidaInvalida(mensaje) from e


def subir(cliente, archivo):
    """`archivo`: FileStorage de Flask (o algo con `.filename` y `.save`).
    Sube el material (gratis) y devuelve `vista_previa.material_para` del
    resultado; encola `edicion_proxy` para video/audio. `SubidaInvalida` con
    el mensaje para la persona en cualquier rechazo (tipo, tamaño/duración,
    cuota)."""
    nombre_archivo = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre_archivo)[1].lower()
    info = EXTENSIONES.get(ext)
    if not info:
        raise SubidaInvalida(gettext("Sube un video, una imagen o un audio."))
    tipo, content_type = info
    carpeta = _carpeta_tmp(cliente)
    local = os.path.join(carpeta, f"subida_{uuid.uuid4().hex}{ext}")
    archivo.save(local)
    try:
        return _procesar(cliente, local, ext, tipo, content_type, nombre_archivo)
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _procesar(cliente, local, ext, tipo, content_type, nombre_archivo):
    """Una foto girada por EXIF se mide y se sube ya derecha (`_enderezar`);
    esa copia se borra al terminar, como el temporal."""
    derecha = _enderezar(local, ext) if tipo == "imagen" else None
    try:
        return _guardar(cliente, derecha or local, ext, tipo, content_type, nombre_archivo)
    finally:
        if derecha:
            try:
                os.remove(derecha)
            except OSError:
                pass


def _guardar(cliente, local, ext, tipo, content_type, nombre_archivo):
    tam = os.path.getsize(local)
    duracion_ms, ancho, alto, tiene_audio = _medir(tipo, local)
    try:
        materiales.validar_subida(tipo, tam, duracion_ms)
    except materiales.SubidaInvalida as e:
        raise SubidaInvalida(str(e))
    if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
        raise SubidaInvalida(gettext("El proyecto llegó a su límite de espacio (2 GB): borra en «Tus archivos» lo que ya no uses antes de subir más."))
    h = materiales.hash_archivo(local)
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):      # se guarda: el idioma del proyecto
        respaldo = gettext("Archivo")
    nombre = os.path.splitext(nombre_archivo)[0].strip()[:80] or respaldo
    extra = {"nombre": nombre}
    if tipo == "video":
        extra["tiene_audio"] = tiene_audio
    m = materiales.subir(cliente, local, f"clientes/{cliente}/materiales/{h}{ext}", content_type,
                         tipo=tipo, origen="subida", duracion_ms=duracion_ms, ancho=ancho, alto=alto, extra=extra)
    if tipo in ("video", "audio"):
        # Gratis, max_intentos=3, prioridad 1 (nunca por delante de un lote de
        # Sprints ni de una pieza suelta de Crear): mismo job_id que
        # `vista_previa.encolar_proxies`/`insumos.clon` usan para este
        # material, así una subida y un reintento posterior nunca lo encolan
        # dos veces con ids distintos.
        trabajos.encolar(tareas_edicion.job_id_proxy(cliente, m["id"]), "edicion_proxy",
                         {"cliente": cliente, "material_id": m["id"]}, duracion_estimada=60,
                         cliente=cliente, max_intentos=3, prioridad=1)
    return vista_previa.material_para(m)


# --- Grabación del micrófono (editor capa 5a, D8/Task 6): gratis, siempre a mp3 ---

# Lo que el navegador puede mandar (D8): `audio/webm;codecs=opus` (Chrome,
# Edge, Firefox) -> .webm, `audio/mp4` (Safari) -> .m4a/.mp4, `audio/ogg` ->
# .ogg. Nunca .mp3: el micrófono no lo produce directamente.
EXTENSIONES_GRABACION = {".webm", ".m4a", ".mp4", ".ogg", ".wav"}
MAX_GRABACION_MS = 300000   # 5 min
_HORA_RE = re.compile(r"^\d{2}:\d{2}$")


def _hora_de_grabacion(hora):
    """La hora HH:MM que manda el navegador (hora local de quien graba); sin
    ella, o mal formada, la hora UTC del servidor."""
    if isinstance(hora, str) and _HORA_RE.fullmatch(hora):
        return hora
    return datetime.now(timezone.utc).strftime("%H:%M")


def guardar_grabacion(cliente, archivo, hora=None):
    """Grabación del micrófono del editor (D8, gratis): se sube SIEMPRE
    pasada a mp3 (`-vn -ac 1 -ar 44100 -c:a libmp3lame -b:a 128k`) — el
    .webm de Chrome no trae duración y Safari viejo no decodifica opus con
    `decodeAudioData` —, con tope de 5 minutos, 20 MB y la cuota del
    proyecto. `archivo`: FileStorage de Flask (o algo con `.filename` y
    `.save`). Encola el proxy (picos) como cualquier audio nuevo. Los
    temporales (el original y el mp3) se borran en un `finally`."""
    nombre_archivo = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre_archivo)[1].lower()
    if ext not in EXTENSIONES_GRABACION:
        raise SubidaInvalida(gettext("Sube una grabación .webm, .m4a, .mp4, .ogg o .wav."))
    carpeta = _carpeta_tmp(cliente)
    local = os.path.join(carpeta, f"grabacion_{uuid.uuid4().hex}{ext}")
    mp3 = local + ".mp3"
    archivo.save(local)
    try:
        try:
            info = cortes.ffprobe_json(local)
            tiene_audio = any((s or {}).get("codec_type") == "audio" for s in info.get("streams") or [])
        except Exception:
            tiene_audio = False
        if not tiene_audio:
            raise SubidaInvalida(gettext("No pude leer esa grabación."))
        try:
            cortes.ffmpeg(["-i", local, "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", mp3])
        except SubidaInvalida:
            raise
        except Exception:
            raise SubidaInvalida(gettext("No pude leer esa grabación."))
        try:
            dur_ms = int(round(cortes.duracion(mp3) * 1000))
        except Exception:
            raise SubidaInvalida(gettext("No pude leer esa grabación."))
        if dur_ms > MAX_GRABACION_MS:
            raise SubidaInvalida(gettext("La grabación dura más de 5 minutos."))
        tam = os.path.getsize(mp3)
        try:
            materiales.validar_subida("audio", tam)
        except materiales.SubidaInvalida as e:
            raise SubidaInvalida(str(e))
        if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
            raise SubidaInvalida(gettext("El proyecto llegó a su límite de espacio (2 GB): borra en «Tus archivos» lo que ya no uses antes de subir más."))
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):   # se guarda: el idioma del proyecto
            nombre = gettext("Grabación %(hora)s", hora=_hora_de_grabacion(hora))
        h = materiales.hash_archivo(mp3)
        m = materiales.subir(cliente, mp3, f"clientes/{cliente}/materiales/grabacion_{h[:16]}.mp3", "audio/mpeg",
                             tipo="audio", origen="grabacion", duracion_ms=dur_ms, extra={"nombre": nombre})
        trabajos.encolar(tareas_edicion.job_id_proxy(cliente, m["id"]), "edicion_proxy",
                         {"cliente": cliente, "material_id": m["id"]}, duracion_estimada=60,
                         cliente=cliente, max_intentos=3, prioridad=1)
        return vista_previa.material_para(m)
    finally:
        for ruta in (local, mp3):
            try:
                os.remove(ruta)
            except OSError:
                pass


def _materiales_de_piezas(cliente):
    """{cf_id: fila material} de las piezas de Crear que ya son un material
    de este proyecto. La deduplicación puede conservar origen subida;
    cf_id es el enlace legado y cf_ids permite compartir los mismos bytes."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "video")).fetchall()
    out = {}
    for f in filas:
        m = dict(f._mapping)
        extra = m.get("extra") or {}
        for cf_id in [extra.get("cf_id"), *(extra.get("cf_ids") or [])]:
            if cf_id:
                out[cf_id] = m
    return out


def material_de_pieza(cliente, cf_id):
    """La fila `material` de esa pieza si ya se materializó (bloque
    `agregar_pieza` de la ruta), o None."""
    return _materiales_de_piezas(cliente).get(cf_id)


def listar(cliente):
    """{"materiales": [...], "piezas": [...]} para el panel de biblioteca:
    los materiales del proyecto que se pueden arrastrar al lienzo (más
    recientes primero, tope 200) y las piezas de Crear con video listo, cada
    una con su `material_id` si ya se materializó y `preparando` si su
    tarea `material_de_pieza` está en curso."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente,
            db.material.c.tipo.in_(("video", "imagen", "audio")),
            db.material.c.origen.in_(ORIGENES_BIBLIOTECA),
        ).order_by(db.material.c.id.desc()).limit(TOPE_MATERIALES)).fetchall()
    materiales_out = [vista_previa.material_para(dict(f._mapping)) for f in filas]

    de_pieza = _materiales_de_piezas(cliente)
    piezas_out = []
    for cf_id, entry in creative_flow.cargar(cliente).items():
        if entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") != "video":
            continue
        mat = de_pieza.get(cf_id)
        piezas_out.append({
            "cf_id": cf_id,
            "nombre": (entry.get("accion_central") or cf_id)[:120],
            "tipo": "video",
            "formato": entry.get("aspect_ratio"),
            "video_url": entry.get("video_url"),
            "material_id": mat["id"] if mat else None,
            "preparando": trabajos.en_curso(tareas_edicion.job_id_material_de_pieza(cliente, cf_id)),
        })
    return {"materiales": materiales_out, "piezas": piezas_out}


def materializar_pieza(cliente, cf_id, carpeta):
    """La misma preparación que `final_edition.edicion_clon.crear` hace con
    el clon (`insumos.clon` sobre el crudo, reusando `video_local_crudo` si
    está en disco) pero sin crear ninguna edición: solo el material, listo
    para que la biblioteca lo ofrezca. Guarda `extra.nombre` = el nombre
    visible de la pieza."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") != "video":
        raise ValueError(gettext("La pieza %(cf)s no tiene un video listo para el editor.", cf=cf_id))
    local = entry.get("video_local_crudo")
    if not (local and os.path.isfile(local)):
        os.makedirs(carpeta, exist_ok=True)
        local = insumos._descargar(entry.get("video_url_crudo") or entry.get("video_url"), os.path.join(carpeta, "clon.mp4"))
    mat, _creado = insumos.clon(cliente, cf_id, entry, local)
    nombre = (entry.get("accion_central") or cf_id)[:120]
    return _asociar_pieza(cliente, mat["id"], cf_id, nombre)


def _asociar_pieza(cliente, material_id, cf_id, nombre):
    """Añade una asociación sin cambiar el origen ni los metadatos previos.

    El UPDATE toma el lock de escritura ANTES de leer extra (igual que
    materiales.actualizar_extra): dos preparaciones de los mismos bytes
    no pueden perder asociaciones al guardar la lista.
    """
    condicion = (db.material.c.cliente == cliente, db.material.c.id == material_id)
    with db.conectar() as con:
        con.execute(db.material.update().where(*condicion)
                    .values(actualizado_en=db.material.c.actualizado_en))
        extra = dict(con.execute(sa.select(db.material.c.extra).where(*condicion)).scalar_one() or {})
        ids = list(dict.fromkeys([x for x in [extra.get("cf_id"), *(extra.get("cf_ids") or []), cf_id] if x]))
        extra["cf_ids"] = ids
        extra.setdefault("cf_id", cf_id)
        extra.setdefault("nombre", nombre)
        con.execute(db.material.update().where(*condicion).values(extra=extra, actualizado_en=db.ahora()))
    return materiales.obtener(cliente, material_id)
