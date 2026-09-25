"""Mi música (spec docs/superpowers/specs/2026-09-25-mi-musica-design.md): las
canciones propias de un proyecto — subidas por el cliente o creadas con
ElevenLabs — como filas de `material` (tipo audio, origen subida|musica).
Único escritor de esas filas; la mezcla las lee con
`final_edition.musica.pista_propia`. En los formularios una canción es el
valor `mat:<id>`. No importa final_edition al cargar (final_edition.musica
importa este módulo)."""
import os
import uuid

import sqlalchemy as sa

import db
import materiales

PREFIJO = "mat:"
ORIGENES = ("subida", "musica")
EXTENSIONES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg"}
MAX_DURACION_MS = 10 * 60 * 1000


class SubidaInvalida(ValueError):
    """El mensaje va tal cual a la persona."""


def es_propia(valor):
    return isinstance(valor, str) and valor.startswith(PREFIJO)


def como_cancion(m):
    extra = m.get("extra") or {}
    return {"id": m["id"], "nombre": extra.get("nombre") or f"Canción {m['id']}",
            "duracion_s": round((m.get("duracion_ms") or 0) / 1000.0, 1), "url": m["url"],
            "fuente": extra.get("fuente") or ("elevenlabs" if m["origen"] == "musica" else "subida")}


def listar(cliente):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen.in_(ORIGENES)).order_by(db.material.c.id.desc())).all()
    return [como_cancion(dict(f._mapping)) for f in filas]


def resolver(cliente, valor):
    """La fila `material` si `valor` es `mat:<id>` de una canción de este
    cliente; si no, None (otro cliente, borrada, no es audio, basura)."""
    if not es_propia(valor):
        return None
    try:
        mid = int(valor[len(PREFIJO):])
    except ValueError:
        return None
    m = materiales.obtener(cliente, mid)
    if not m or m["tipo"] != "audio" or m["origen"] not in ORIGENES:
        return None
    return m


def inicio_valido(material, inicio_s):
    """Segundo de inicio entero dentro de la canción; 0 si no aplica."""
    try:
        s = int(float(inicio_s))
    except (TypeError, ValueError):
        return 0
    return s if 0 <= s < (material.get("duracion_ms") or 0) / 1000.0 else 0


def _probar(path):
    """Duración en ms de un archivo con pista de audio (ffprobe)."""
    from final_edition import cortes
    try:
        info = cortes.ffprobe_json(path)
    except Exception:
        raise SubidaInvalida("No pude leer ese archivo de audio.")
    if not any((s or {}).get("codec_type") == "audio" for s in info.get("streams") or []):
        raise SubidaInvalida("Ese archivo no trae audio.")
    dur = (info.get("format") or {}).get("duration")
    if dur is None:
        raise SubidaInvalida("No pude medir la duración de ese audio.")
    return int(round(float(dur) * 1000))


def _guardar(cliente, local_path, ext, origen, extra, costo_usd=0.0):
    tam = os.path.getsize(local_path)
    try:
        materiales.validar_subida("audio", tam)
    except materiales.SubidaInvalida as e:
        raise SubidaInvalida(str(e))
    duracion_ms = _probar(local_path)
    if duracion_ms > MAX_DURACION_MS:
        raise SubidaInvalida("La canción dura más de 10 min.")
    if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
        raise SubidaInvalida("El proyecto llegó a su límite de espacio (2 GB): borra algo antes de subir más.")
    key = f"clientes/{cliente}/materiales/{materiales.hash_archivo(local_path)}{ext}"
    m = materiales.subir(cliente, local_path, key, EXTENSIONES[ext], tipo="audio", origen=origen,
                         duracion_ms=duracion_ms, costo_usd=costo_usd, extra=extra)
    return como_cancion(m)


def subir(cliente, archivo, carpeta_tmp):
    """`archivo`: FileStorage de Flask (o algo con `.filename` y `.save`)."""
    nombre = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in EXTENSIONES:
        raise SubidaInvalida("Sube un mp3, wav, m4a, aac u ogg.")
    os.makedirs(carpeta_tmp, exist_ok=True)
    local = os.path.join(carpeta_tmp, f"subida_{uuid.uuid4().hex}{ext}")
    archivo.save(local)
    try:
        titulo = os.path.splitext(nombre)[0].strip()[:80] or "Canción"
        return _guardar(cliente, local, ext, "subida", {"nombre": titulo, "fuente": "subida"})
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def registrar_generada(cliente, local_path, prompt, instrumental, costo_usd):
    texto = " ".join((prompt or "").split())
    ext = os.path.splitext(local_path)[1].lower()
    ext = ext if ext in EXTENSIONES else ".mp3"
    return _guardar(cliente, local_path, ext, "musica",
                    {"nombre": texto[:80] or "Canción ElevenLabs", "fuente": "elevenlabs",
                     "prompt": texto, "instrumental": bool(instrumental)}, costo_usd)


def borrar(cliente, material_id):
    """Solo canciones de Mi música de este cliente. `materiales.MaterialEnUso`
    se propaga (la canción está en una edición del editor)."""
    m = resolver(cliente, f"{PREFIJO}{material_id}")
    if not m:
        return False
    return materiales.borrar(cliente, m["id"])
