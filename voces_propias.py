"""Voces propias de Audios (spec docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md §3):
voces clonadas desde una grabación (con permiso de la persona) o diseñadas desde
una descripción, con MiniMax vía fal.

Cada voz es una fila `material` del proyecto: tipo `audio`, origen `voz_propia`,
`url` = su muestra en R2, `extra` con el `voice_id` de MiniMax. La grabación de
un clon es otra fila (origen `grabacion`) y las muestras por idioma son filas
origen `voz` con hash `muestra_propia`. Este módulo es el único escritor de las
tres. MiniMax borra una voz que no se usa en una síntesis real dentro de 7 días
(la vista previa no cuenta): `crear` la estrena en el mismo paso y cualquier
síntesis posterior la marca `estrenada`."""
import os
import tempfile
import time
import uuid

import sqlalchemy as sa

import audios
import db
import gastos
import idiomas
import materiales
import mi_musica
from final_edition import cortes
from providers import fal_audio
from storage import r2_uploader

PREFIJO = audios.PREFIJO_VOZ_PROPIA
ORIGEN = "voz_propia"
ORIGEN_GRABACION = "grabacion"
PROVEEDOR = "fal/minimax"
NOMBRES_FORMA = {"clonada": idiomas.N_("Clonada"), "disenada": idiomas.N_("Diseñada")}
MIN_GRABACION_MS = 10 * 1000
MAX_GRABACION_MS = 5 * 60 * 1000
MAX_NOMBRE = 40
MIN_DESCRIPCION, MAX_DESCRIPCION = 10, 500
VERSION_MUESTRA = 1
TEXTO_CONSENTIMIENTO = idiomas.N_("Es mi voz o tengo permiso escrito de la persona para clonarla y usarla en anuncios.")
# msgids: la ruta los traduce con idiomas.traducir al responder.
MENSAJES = {
    "nombre": idiomas.N_("Ponle un nombre a la voz (hasta 40 caracteres)."),
    "archivo": idiomas.N_("Sube un mp3, wav, m4a, aac u ogg."),
    "corta": idiomas.N_("La grabación tiene que durar al menos 10 segundos."),
    "larga": idiomas.N_("La grabación puede durar hasta 5 minutos."),
    "leer": idiomas.N_("No pude leer ese archivo de audio."),
    "sin_audio": idiomas.N_("Ese archivo no trae audio."),
    "pesado": idiomas.N_("La grabación pesa más de 20 MB."),
    "cuota": idiomas.N_("El proyecto llegó a su límite de espacio (2 GB): borra algo antes de subir más."),
    "permiso": idiomas.N_("Marca la casilla de permiso para clonar esta voz."),
    "descripcion": idiomas.N_("Describe la voz en 10 a 500 caracteres."),
    "idioma": idiomas.N_("Elige un idioma de la lista."),
    "en_curso": idiomas.N_("Ya se está creando una voz — espera a que termine."),
}


class EntradaInvalida(ValueError):
    """`str(e)` es un msgid de MENSAJES: traducir al mostrar."""


# --------------------------------------------------------------- leer ---

def _como_voz(m):
    e = m.get("extra") or {}
    return {"id": m["id"], "valor": f"{PREFIJO}{m['id']}", "nombre": e.get("nombre") or f"Voz {m['id']}",
            "forma": e.get("forma") or "disenada", "voice_id": e.get("voice_id") or "", "url": m.get("url") or "",
            "idioma_muestra": e.get("idioma_muestra") or "es", "estrenada": bool(e.get("estrenada")),
            "descripcion": e.get("descripcion") or "", "creado_en": m.get("creado_en")}


def listar(cliente):
    """Las voces propias del proyecto, la más reciente primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen == ORIGEN).order_by(db.material.c.id.desc())).all()
    return [_como_voz(dict(f._mapping)) for f in filas]


def obtener(cliente, voz_id):
    m = materiales.obtener(cliente, voz_id)
    if not m or m["tipo"] != "audio" or m["origen"] != ORIGEN:
        return None
    return _como_voz(m)


def resolver(cliente, valor):
    """La voz si `valor` es `vp:<id>` de una voz propia de este proyecto; si no, None."""
    if not audios.es_propia(valor):
        return None
    try:
        vid = int(valor[len(PREFIJO):])
    except ValueError:
        return None
    return obtener(cliente, vid)


def marcar_estrenada(cliente, voz_id):
    materiales.actualizar_extra(cliente, voz_id, estrenada=True)


# ----------------------------------------------------------- validar ---

def _nombre(form):
    n = " ".join((form.get("nombre") or "").split())
    if not n or len(n) > MAX_NOMBRE:
        raise EntradaInvalida(MENSAJES["nombre"])
    return n


def _idioma(form):
    i = (form.get("idioma") or "").strip()
    if i not in audios.IDIOMAS:
        raise EntradaInvalida(MENSAJES["idioma"])
    return i


def validar_disenar(form):
    nombre = _nombre(form)
    descripcion = " ".join((form.get("descripcion") or "").split())
    if not (MIN_DESCRIPCION <= len(descripcion) <= MAX_DESCRIPCION):
        raise EntradaInvalida(MENSAJES["descripcion"])
    return {"forma": "disenar", "nombre": nombre, "descripcion": descripcion, "idioma": _idioma(form)}


def validar_clonar(form, usuario):
    """Los campos del clon; la grabación se guarda aparte (guardar_grabacion) y
    la ruta agrega `grabacion_id`. Sin la casilla no se guarda nada."""
    nombre, idioma = _nombre(form), _idioma(form)
    if (form.get("consentimiento") or "") != "si":
        raise EntradaInvalida(MENSAJES["permiso"])
    return {"forma": "clonar", "nombre": nombre, "idioma": idioma,
            "consentimiento": {"usuario": usuario or "", "fecha": db.ahora(), "texto": TEXTO_CONSENTIMIENTO}}


def _duracion_ms(path):
    try:
        info = cortes.ffprobe_json(path)
    except Exception:
        raise EntradaInvalida(MENSAJES["leer"])
    if not any((s or {}).get("codec_type") == "audio" for s in info.get("streams") or []):
        raise EntradaInvalida(MENSAJES["sin_audio"])
    dur = (info.get("format") or {}).get("duration")
    if dur is None:
        raise EntradaInvalida(MENSAJES["leer"])
    return int(round(float(dur) * 1000))


def guardar_grabacion(cliente, archivo, carpeta_tmp):
    """Sube la grabación de un clon a R2 como `material` (origen `grabacion`) y
    devuelve la fila. El hash va con prefijo propio para no devolver una canción
    idéntica de Mi música. `archivo`: FileStorage de Flask."""
    nombre = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in mi_musica.EXTENSIONES:
        raise EntradaInvalida(MENSAJES["archivo"])
    os.makedirs(carpeta_tmp, exist_ok=True)
    local = os.path.join(carpeta_tmp, f"grabacion_{uuid.uuid4().hex}{ext}")
    archivo.save(local)
    try:
        tam = os.path.getsize(local)
        if tam > materiales.LIMITES["audio"][0]:
            raise EntradaInvalida(MENSAJES["pesado"])
        dur = _duracion_ms(local)
        if dur < MIN_GRABACION_MS:
            raise EntradaInvalida(MENSAJES["corta"])
        if dur > MAX_GRABACION_MS:
            raise EntradaInvalida(MENSAJES["larga"])
        if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
            raise EntradaInvalida(MENSAJES["cuota"])
        h = materiales.hash_clave(ORIGEN_GRABACION, materiales.hash_archivo(local))

        def _producir():
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/grabacion_{h[:16]}{ext}",
                                          mi_musica.EXTENSIONES[ext])
            return {"tipo": "audio", "origen": ORIGEN_GRABACION, "url": url, "bytes": tam, "duracion_ms": dur,
                    "extra": {"nombre": os.path.splitext(nombre)[0].strip()[:80]}}
        m, _ = materiales.obtener_o_crear(cliente, h, _producir)
        return m
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


# ------------------------------------------------------------- crear ---

def frase_muestra(nombre, idioma):
    return audios.FRASES_MUESTRA[idioma].format(voz=nombre)


def _subir_mp3(cliente, url_fuente, key):
    """Baja `url_fuente` y la sube a R2 en `key`. Devuelve (url, bytes, duracion_ms)."""
    with tempfile.TemporaryDirectory() as tmp:
        local = audios.descargar_url(url_fuente, os.path.join(tmp, "muestra.mp3"))
        url = r2_uploader.upload_file(local, key, "audio/mpeg")
        return url, os.path.getsize(local), int(round(cortes.duracion(local) * 1000))


def crear(cliente, payload, ref_sufijo="", reportar=None):
    """Lo corre la tarea `voz_propia_crear`. Crea la voz en MiniMax (clonar o
    diseñar), registra ese gasto apenas fal responde, la estrena leyendo su
    frase de muestra en `payload["idioma"]` y la guarda. Si el estreno falla, la
    voz pagada se guarda igual con `estrenada = False` y la vista previa como
    muestra. `reportar(i)` avisa el paso (1 = estrenando, 2 = guardando).
    Devuelve (voz, estrenada)."""
    forma, nombre, idioma = payload["forma"], payload["nombre"], payload["idioma"]
    frase = frase_muestra(nombre, idioma)
    grabacion = None
    if forma == "clonar":
        grabacion = materiales.obtener(cliente, payload["grabacion_id"])
        if not grabacion or grabacion["origen"] != ORIGEN_GRABACION:
            raise ValueError("La grabación ya no está.")
        r = fal_audio.clonar_voz_minimax(grabacion["url"], frase)
    else:
        r = fal_audio.disenar_voz_minimax(payload["descripcion"], frase)
    usd = float(r["costo_usd"])
    # fal ya cobró: el gasto queda aunque lo que sigue falle.
    gastos.registrar_seguro(cliente, "voz_propia", usd, f"voz_propia:{forma}{ref_sufijo}",
                            detalle=f"MiniMax · {'clonar' if forma == 'clonar' else 'diseñar'} voz · {nombre}",
                            proveedor=PROVEEDOR, extra={"voice_id": r["voice_id"]})
    if reportar:
        reportar(1)
    h = materiales.hash_clave(ORIGEN, "minimax", r["voice_id"])
    fuente, estrenada = None, False
    try:
        t = fal_audio.tts_minimax(frase, r["voice_id"], idioma)
        gastos.registrar_seguro(cliente, "locucion", float(t["costo_usd"]), f"voz_propia_estreno{ref_sufijo}",
                                detalle=f"MiniMax · estreno · {nombre}", proveedor=PROVEEDOR)
        fuente, estrenada = t["url"], True
    except Exception:
        fuente = r.get("url_vista_previa")
    if reportar:
        reportar(2)
    url, bytes_, dur = "", 0, None
    if fuente:
        url, bytes_, dur = _subir_mp3(cliente, fuente, f"clientes/{cliente}/materiales/voz_propia_{h[:16]}.mp3")
    extra = {"nombre": nombre, "forma": "clonada" if forma == "clonar" else "disenada", "proveedor": "minimax",
             "voice_id": r["voice_id"], "idioma_muestra": idioma, "estrenada": estrenada}
    if forma == "clonar":
        extra.update(consentimiento=payload.get("consentimiento") or {}, grabacion_id=grabacion["id"])
    else:
        extra["descripcion"] = payload["descripcion"]
    m = materiales.registrar(cliente, tipo="audio", origen=ORIGEN, url=url, hash=h, bytes=bytes_, duracion_ms=dur,
                             costo_usd=usd, extra=extra)
    return _como_voz(m), estrenada


# ---------------------------------------------------------- muestras ---

def _hash_muestra(voice_id, idioma):
    return materiales.hash_clave("muestra_propia", voice_id, idioma, VERSION_MUESTRA)


def muestra(cliente, valor, idioma):
    """URL de la muestra de una voz propia en `idioma`. La del idioma en que se
    creó ya existe si la voz está estrenada; las demás se sintetizan una vez y
    se cobran al proyecto (tipo `locucion`). Sintetizar estrena la voz.
    ValueError si la voz no es de este proyecto o el idioma no existe."""
    vp = resolver(cliente, valor)
    if not vp or idioma not in audios.IDIOMAS:
        raise ValueError("voz o idioma desconocidos")
    if idioma == vp["idioma_muestra"] and vp["url"] and vp["estrenada"]:
        return vp["url"]
    h = _hash_muestra(vp["voice_id"], idioma)
    frase = frase_muestra(vp["nombre"], idioma)

    def _producir():
        t = fal_audio.tts_minimax(frase, vp["voice_id"], idioma, timeout=45)
        usd = float(t["costo_usd"])
        gastos.registrar_seguro(cliente, "locucion", usd,
                                f"muestra_propia:{vp['id']}:{idioma}:{int(time.time() * 1000)}",
                                detalle=f"muestra de voz propia · {vp['nombre']} · {idioma}", proveedor=PROVEEDOR)
        marcar_estrenada(cliente, vp["id"])
        url, bytes_, dur = _subir_mp3(cliente, t["url"], f"clientes/{cliente}/materiales/muestra_propia_{h[:16]}.mp3")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": bytes_, "duracion_ms": dur,
                "costo_usd": usd, "extra": {"texto": frase, "voz": vp["valor"], "idioma": idioma, "muestra": True,
                                            "voz_propia_id": vp["id"]}}
    m, _ = materiales.obtener_o_crear(cliente, h, _producir)
    return m["url"]


# ------------------------------------------------------------- borrar ---

def borrar(cliente, voz_id):
    """Quita la voz, su grabación (si es un clon) y sus muestras por idioma, con
    sus objetos en R2. La voz en la cuenta de MiniMax de fal no se puede borrar
    desde fal. `materiales.MaterialEnUso` se propaga."""
    vp = obtener(cliente, voz_id)
    if not vp:
        return False
    fila = materiales.obtener(cliente, voz_id)
    for idioma in audios.IDIOMAS:
        mm = materiales.buscar_hash(cliente, _hash_muestra(vp["voice_id"], idioma))
        if mm:
            materiales.borrar(cliente, mm["id"])
    gid = (fila.get("extra") or {}).get("grabacion_id")
    if gid:
        g = materiales.obtener(cliente, gid)
        if g and g["origen"] == ORIGEN_GRABACION:
            materiales.borrar(cliente, gid)
    return materiales.borrar(cliente, voz_id)
