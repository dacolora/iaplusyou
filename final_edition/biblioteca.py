"""Biblioteca del editor (spec editor capa 4b, Task 1): subir un archivo del
proyecto a `material` (video/imagen/audio, gratis), listar lo subido junto
con las piezas de Crear listas para arrastrar al lienzo, y materializar una
pieza de Crear como material bajo pedido — la misma preparación que
`final_edition.edicion_clon.crear` hace con el clon, sin crear ninguna
edición. Único módulo que decide esto: la ruta (`final_edition/rutas_editor.py`)
solo traduce multipart/JSON y el worker (`tareas/edicion.py`) solo valida
`cf_id` y llama a `materializar_pieza`."""
import math
import os
import uuid

import sqlalchemy as sa
from PIL import Image

import creative_flow
import db
import final_edition
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
# sintetizada de un guion que no le pertenece a ella todavía.
ORIGENES_BIBLIOTECA = ("subida", "crear", "musica", "voz", "logo")
TOPE_MATERIALES = 200


class SubidaInvalida(ValueError):
    """El mensaje va tal cual a la persona."""


def _carpeta_tmp(cliente):
    carpeta = os.path.join(final_edition.BASE_DIR, "clientes", cliente, "tmp_editor")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _medir(tipo, local):
    """(duracion_ms, ancho, alto, tiene_audio) según el tipo; `SubidaInvalida`
    si el archivo no se puede leer con ffprobe/Pillow."""
    if tipo == "imagen":
        try:
            with Image.open(local) as im:
                ancho, alto = im.size
                im.verify()
            if ancho <= 0 or alto <= 0:
                raise ValueError("dimensiones inválidas")
        except (OSError, ValueError):
            raise SubidaInvalida("No pude leer esa imagen.")
        return None, ancho, alto, None
    mensaje = "No pude leer ese video." if tipo == "video" else "No pude leer ese archivo de audio."
    try:
        info = cortes.ffprobe_json(local)
        streams = info.get("streams") or []
        if tipo == "video":
            v = next((s for s in streams if s.get("codec_type") == "video"
                      and not (s.get("disposition") or {}).get("attached_pic")), None)
            if not v or int(v.get("width") or 0) <= 0 or int(v.get("height") or 0) <= 0:
                raise ValueError("falta video con dimensiones válidas")
        elif not any(s.get("codec_type") == "audio" for s in streams):
            raise ValueError("falta audio")
        dur_s = cortes.duracion(local)
        if not math.isfinite(dur_s) or dur_s <= 0:
            raise ValueError("duración inválida")
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
        raise SubidaInvalida("Sube un video, una imagen o un audio.")
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
    tam = os.path.getsize(local)
    duracion_ms, ancho, alto, tiene_audio = _medir(tipo, local)
    try:
        materiales.validar_subida(tipo, tam, duracion_ms)
    except materiales.SubidaInvalida as e:
        raise SubidaInvalida(str(e))
    if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
        raise SubidaInvalida("El proyecto llegó a su límite de espacio (2 GB): borra algo antes de subir más.")
    h = materiales.hash_archivo(local)
    nombre = os.path.splitext(nombre_archivo)[0].strip()[:80] or "Archivo"
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
        raise ValueError(f"La pieza {cf_id} no tiene un video listo para el editor.")
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
