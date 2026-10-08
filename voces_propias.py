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
import logging
import os
import tempfile
import time
import uuid

import sqlalchemy as sa
from flask_babel import gettext

import audios
import db
import gastos
import idiomas
import materiales
import mi_musica
from final_edition import cortes
from providers import fal_audio
from storage import r2_uploader

log = logging.getLogger(__name__)

PREFIJO = audios.PREFIJO_VOZ_PROPIA
ORIGEN = "voz_propia"
ORIGEN_GRABACION = "grabacion"
PROVEEDOR = "fal/minimax"
NOMBRES_FORMA = {"clonada": idiomas.N_("Clonada"), "disenada": idiomas.N_("Diseñada")}
MIN_GRABACION_MS = 10 * 1000
MAX_GRABACION_MS = 5 * 60 * 1000
# MiniMax clona desde mp3, m4a o wav (su documentación): una grabación .aac u
# .ogg se guarda convertida a mp3. Lo que se acepta al subir no cambia.
CONVERTIR_A_MP3 = (".aac", ".ogg")
MAX_NOMBRE = 40
MIN_DESCRIPCION, MAX_DESCRIPCION = 10, 500
VERSION_MUESTRA = 1
TEXTO_CONSENTIMIENTO = idiomas.N_("Es mi voz o tengo permiso escrito de la persona para clonarla y usarla en anuncios.")
# msgids: la ruta los traduce con idiomas.traducir al responder.
MENSAJES = {
    "no_encontrada": idiomas.N_("Esa voz ya no está en Mis voces. Elige otra voz."),
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
    "grabacion_borrada": idiomas.N_("La grabación de esa voz ya no está."),
}


class EntradaInvalida(ValueError):
    """`str(e)` es un msgid de MENSAJES: traducir al mostrar."""


# --------------------------------------------------------------- leer ---

def _como_voz(m):
    """`forma_nombre` es un msgid: la plantilla lo traduce con `|traducir`."""
    e = m.get("extra") or {}
    forma = e.get("forma") or "disenada"
    return {"id": m["id"], "valor": f"{PREFIJO}{m['id']}", "nombre": e.get("nombre") or f"Voz {m['id']}",
            "forma": forma, "forma_nombre": NOMBRES_FORMA.get(forma, forma),
            "voice_id": e.get("voice_id") or "", "url": m.get("url") or "",
            "idioma_muestra": e.get("idioma_muestra") or "es", "estrenada": bool(e.get("estrenada")),
            "descripcion": e.get("descripcion") or "", "creado_en": m.get("creado_en")}


def listar(cliente):
    """Las voces propias del proyecto, la más reciente primero."""
    recuperar_pendientes(cliente)
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen == ORIGEN).order_by(db.material.c.id.desc())).all()
    return [_como_voz(dict(f._mapping)) for f in filas]



def _guardar_ficha(cliente, cobro):
    ficha = (cobro.get("extra") or {}).get("ficha") or {}
    if not (ficha.get("extra") or {}).get("voice_id"):
        raise ValueError(gettext("La voz todavía no tiene una respuesta del proveedor; no se vuelve a cobrar."))
    mat = materiales.buscar_hash(cliente, ficha["hash"])
    if not mat:
        if cobro["extra"].get("ficha_guardada"):
            raise ValueError(gettext("Esta voz se borró; no se vuelve a crear."))
        mat, _ = materiales.obtener_o_crear(cliente, ficha["hash"], lambda: {
            k: v for k, v in ficha.items() if k != "hash"})
    gastos.registrar_seguro(cliente, cobro["tipo"], cobro["usd"], cobro["referencia"],
                            detalle=cobro["detalle"], proveedor=cobro["proveedor"],
                            extra={**cobro["extra"], "ficha_guardada": True})
    return _como_voz(mat)


def recuperar_pendientes(cliente):
    """Recuperación gratuita al abrir Mis voces; nunca sintetiza ni descarga."""
    pendientes = gastos.fichas_pendientes(cliente, "voz_propia")
    if not pendientes:
        return
    with db.conectar() as con:
        t = db.tarea
        activas = con.execute(sa.select(t.c.id).where(t.c.cliente == cliente,
                  t.c.tipo == "voz_propia_crear", t.c.estado == "en_curso")).scalars().all()
    for cobro in pendientes:
        if any(cobro["referencia"].endswith(f":t{tid}") for tid in activas):
            continue
        if not (cobro["extra"]["ficha"].get("extra") or {}).get("voice_id"):
            continue
        try:
            _guardar_ficha(cliente, cobro)
        except Exception:
            log.warning("no pude recuperar una ficha de voz propia", exc_info=True)

def obtener(cliente, voz_id):
    m = materiales.obtener(cliente, voz_id)
    if not m or m["tipo"] != "audio" or m["origen"] != ORIGEN:
        return None
    return _como_voz(m)


def resolver(cliente, valor):
    """La voz si `valor` es `vp:<id>` de una voz propia de este proyecto; si no,
    None. Un id descomunal (más de 64 bits) hace que SQLite lance
    `OverflowError` al ligarlo, no `ValueError`: se cubren los dos."""
    if not audios.es_propia(valor):
        return None
    try:
        vid = int(valor[len(PREFIJO):])
        return obtener(cliente, vid)
    except (ValueError, OverflowError):
        return None


def marcar_estrenada(cliente, voz_id):
    materiales.actualizar_extra(cliente, voz_id, estrenada=True)


def sintetizar(cliente, vp, texto, idioma, velocidad=None, timeout=180):
    """Lee `texto` en `idioma` con la voz propia `vp` (el dict de `resolver`)
    por MiniMax y devuelve lo de `fal_audio.tts_minimax` ({"url", "costo_usd",
    "duracion_ms"}). Es una síntesis REAL: estrena la voz (MiniMax borra las que
    no se usan en 7 días). No registra gasto: lo hace quien llama apenas vuelve,
    y por eso un fallo al marcar `estrenada` (base bloqueada) no se propaga."""
    try:
        r = fal_audio.tts_minimax(texto, vp["voice_id"], idioma, velocidad=velocidad, timeout=timeout)
    except Exception as e:
        mensaje = str(e).lower().replace("_", " ")
        if any(t in mensaje for t in ("voice not found", "voice id does not exist", "invalid voice id")):
            raise EntradaInvalida(MENSAJES["no_encontrada"]) from e
        raise
    if not vp.get("estrenada"):
        try:
            marcar_estrenada(cliente, vp["id"])
        except Exception:
            log.warning("voz propia %s: no pude marcarla estrenada", vp["id"], exc_info=True)
    return r


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


def _convertir_a_mp3(origen, salida):
    """`origen` → mp3 mono 44,1 kHz 128 kbps en `salida`. Lo que ffmpeg no
    puede decodificar es «No pude leer ese archivo de audio.», como en
    _duracion_ms."""
    try:
        cortes.ffmpeg(["-i", origen, "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", salida])
    except Exception:
        log.warning("grabación %s: no pude convertirla a mp3", os.path.basename(origen), exc_info=True)
        raise EntradaInvalida(MENSAJES["leer"])


def guardar_grabacion(cliente, archivo, carpeta_tmp):
    """Sube la grabación de un clon a R2 como `material` (origen `grabacion`) y
    devuelve la fila. El hash va con prefijo propio para no devolver una canción
    idéntica de Mi música. Un .aac u .ogg se mide antes de convertirlo a mp3 y volver a
    medirlo para subirlo (CONVERTIR_A_MP3). `archivo`: FileStorage de Flask."""
    nombre = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in mi_musica.EXTENSIONES:
        raise EntradaInvalida(MENSAJES["archivo"])
    os.makedirs(carpeta_tmp, exist_ok=True)
    base = os.path.join(carpeta_tmp, f"grabacion_{uuid.uuid4().hex}")
    temporales = [base + ext]
    try:
        archivo.save(temporales[0])
        if os.path.getsize(temporales[0]) > materiales.LIMITES["audio"][0]:
            raise EntradaInvalida(MENSAJES["pesado"])
        local = temporales[0]
        if ext in CONVERTIR_A_MP3:
            dur_original = _duracion_ms(local)
            if dur_original < MIN_GRABACION_MS:
                raise EntradaInvalida(MENSAJES["corta"])
            if dur_original > MAX_GRABACION_MS:
                raise EntradaInvalida(MENSAJES["larga"])
            local, ext = base + ".mp3", ".mp3"
            temporales.append(local)
            _convertir_a_mp3(temporales[0], local)
        tam = os.path.getsize(local)
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
        for ruta in temporales:
            try:
                os.remove(ruta)
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
    muestra; si además falla subir esa muestra a R2, se guarda igual con
    `url=""` (`muestra()` la vuelve a sintetizar la próxima vez que se pida).
    `reportar(i)` avisa el paso (1 = estrenando, 2 = guardando). Devuelve
    (voz, estrenada). Sin `ref_sufijo` (dos creaciones sin tarea detrás) cada
    llamada arma el suyo con la hora, para no pisar el gasto de la otra."""
    if not ref_sufijo:
        ref_sufijo = f":{int(time.time() * 1000)}"
    forma, nombre, idioma = payload["forma"], payload["nombre"], payload["idioma"]
    frase = frase_muestra(nombre, idioma)
    ref = f"voz_propia:{forma}{ref_sufijo}"
    anterior = gastos.por_referencia(cliente, ref)
    if anterior and (anterior.get("extra") or {}).get("ficha"):
        recuperada = _guardar_ficha(cliente, anterior)
        return recuperada, recuperada["estrenada"]
    extra = {"nombre": nombre, "forma": "clonada" if forma == "clonar" else "disenada", "proveedor": "minimax",
             "voice_id": "", "idioma_muestra": idioma, "estrenada": False}
    if forma == "clonar":
        extra.update(consentimiento=payload.get("consentimiento") or {}, grabacion_id=payload.get("grabacion_id"))
    else:
        extra["descripcion"] = payload["descripcion"]
    detalle = (gettext("MiniMax · clonar voz · %(nombre)s", nombre=nombre) if forma == "clonar"
               else gettext("MiniMax · diseñar voz · %(nombre)s", nombre=nombre))
    ficha = {"tipo": "audio", "origen": ORIGEN, "url": "", "hash": "", "bytes": 0,
             "duracion_ms": None, "costo_usd": 0.0, "extra": extra}
    extra_gasto = {"voice_id": "", "ficha": ficha, "ficha_guardada": False}
    if forma == "clonar":
        extra_gasto["consentimiento"] = payload["consentimiento"]
    def reservar():
        if gastos.reservar_ficha(cliente, "voz_propia", ref, detalle=detalle,
                                 proveedor=PROVEEDOR, extra=extra_gasto) is None:
            raise ValueError(gettext("No se pudo guardar la ficha de la voz antes de cobrar."))
    grabacion = None
    if forma == "clonar":
        # Nada se paga sin el permiso: ni siquiera se llega a fal.
        if (payload.get("consentimiento") or {}).get("texto") != TEXTO_CONSENTIMIENTO:
            raise ValueError(MENSAJES["permiso"])
        grabacion = materiales.obtener(cliente, payload["grabacion_id"])
        if not grabacion or grabacion["origen"] != ORIGEN_GRABACION:
            raise ValueError(MENSAJES["grabacion_borrada"])
        reservar()
        try:
            r = fal_audio.clonar_voz_minimax(grabacion["url"], frase)
        except Exception:
            # fal no devolvió una voz (nada que registrar): la grabación de la
            # persona no se queda en R2 sin una voz que la use.
            _borrar_grabacion_si_huerfana(cliente, grabacion["id"])
            raise
    else:
        reservar()
        r = fal_audio.disenar_voz_minimax(payload["descripcion"], frase)
    usd = float(r["costo_usd"])
    extra["voice_id"] = r["voice_id"]
    ficha.update(url=r.get("url_vista_previa") or "", costo_usd=usd,
                 hash=materiales.hash_clave(ORIGEN, "minimax", r["voice_id"]))
    extra_gasto["voice_id"] = r["voice_id"]
    gastos.registrar_seguro(cliente, "voz_propia", usd, ref, detalle=detalle,
                            proveedor=PROVEEDOR, extra=extra_gasto)
    if reportar:
        reportar(1)
    h = materiales.hash_clave(ORIGEN, "minimax", r["voice_id"])
    fuente, estrenada = None, False
    try:
        t = fal_audio.tts_minimax(frase, r["voice_id"], idioma)
        gastos.registrar_seguro(cliente, "locucion", float(t["costo_usd"]), f"voz_propia_estreno{ref_sufijo}",
                                detalle=gettext("MiniMax · estreno · %(nombre)s", nombre=nombre),
                                proveedor=PROVEEDOR)
        fuente, estrenada = t["url"], True
    except Exception:
        log.warning("voz propia %s: no pude estrenarla", r["voice_id"], exc_info=True)
        fuente = r.get("url_vista_previa")
    extra["estrenada"] = estrenada
    ficha["url"] = fuente or ficha["url"]
    gastos.registrar_seguro(cliente, "voz_propia", usd, ref, detalle=detalle,
                            proveedor=PROVEEDOR, extra=extra_gasto)
    if reportar:
        reportar(2)
    url, bytes_, dur = "", 0, None
    if fuente:
        # La voz ya está pagada (y, si se estrenó, ya está en la cuenta de
        # MiniMax): que R2/la descarga fallen no puede perderla.
        try:
            url, bytes_, dur = _subir_mp3(cliente, fuente, f"clientes/{cliente}/materiales/voz_propia_{h[:16]}.mp3")
        except Exception:
            log.warning("voz propia %s: no pude subir su muestra", r["voice_id"], exc_info=True)
            url, bytes_, dur = "", 0, None
    extra["estrenada"] = estrenada
    ficha.update(url=url or fuente or "", bytes=bytes_, duracion_ms=dur)
    gastos.registrar_seguro(cliente, "voz_propia", usd, ref, detalle=detalle,
                            proveedor=PROVEEDOR, extra=extra_gasto)
    campos = {"tipo": "audio", "origen": ORIGEN, "url": url, "bytes": bytes_, "duracion_ms": dur,
              "costo_usd": usd, "extra": extra}
    m, _ = materiales.obtener_o_crear(cliente, h, lambda: campos)
    m = materiales.actualizar_ficha(cliente, h, **campos)
    gastos.registrar_seguro(cliente, "voz_propia", usd, ref, detalle=detalle,
                            proveedor=PROVEEDOR, extra={**extra_gasto, "ficha_guardada": True})
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
        raise ValueError(gettext("voz o idioma desconocidos"))
    if idioma == vp["idioma_muestra"] and vp["url"] and vp["estrenada"]:
        return vp["url"]
    h = _hash_muestra(vp["voice_id"], idioma)
    frase = frase_muestra(vp["nombre"], idioma)

    def _producir():
        t = sintetizar(cliente, vp, frase, idioma, timeout=45)
        usd = float(t["costo_usd"])
        # La pide quien mira (ruta au_muestra), pero el detalle se GUARDA: va en
        # el idioma del proyecto (spec 2026-09-26 §B8).
        with idiomas.en_idioma(idiomas.de_tarea({"cliente": cliente})):
            detalle = gettext("muestra de voz propia · %(nombre)s · %(idioma)s", nombre=vp["nombre"], idioma=idioma)
        gastos.registrar_seguro(cliente, "locucion", usd,
                                f"muestra_propia:{vp['id']}:{idioma}:{int(time.time() * 1000)}",
                                detalle=detalle, proveedor=PROVEEDOR)
        url, bytes_, dur = _subir_mp3(cliente, t["url"], f"clientes/{cliente}/materiales/muestra_propia_{h[:16]}.mp3")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": bytes_, "duracion_ms": dur,
                "costo_usd": usd, "extra": {"texto": frase, "voz": vp["valor"], "idioma": idioma, "muestra": True,
                                            "voz_propia_id": vp["id"]}}
    m, _ = materiales.obtener_o_crear(cliente, h, _producir)
    return m["url"]


# ------------------------------------------------------------- borrar ---

def _grabacion_en_uso_por_otra_voz(cliente, voz_id, gid):
    """True si OTRA voz propia del proyecto también apunta a la grabación
    `gid` (dos clones desde el mismo archivo comparten una sola fila
    `grabacion`, deduplicada por hash) — pocas filas, se compara en Python."""
    with db.conectar() as con:
        extras = con.execute(sa.select(db.material.c.extra).where(
            db.material.c.cliente == cliente, db.material.c.origen == ORIGEN,
            db.material.c.id != voz_id)).scalars().all()
    return any((e or {}).get("grabacion_id") == gid for e in extras)


def _borrar_grabacion_si_huerfana(cliente, grabacion_id):
    """Borra, con su objeto en R2, la grabación de un clon que no llegó a ser
    voz (fal falló o la tarea no se pudo encolar): la voz de una persona no se
    queda guardada sin una voz propia que la use (spec §3). Solo una fila
    `grabacion` de este proyecto que ninguna voz propia usa (dos clones del
    mismo archivo comparten la fila). Nunca lanza: quien la llama ya tiene su
    propio error que contar."""
    try:
        g = materiales.obtener(cliente, grabacion_id)
        if g and g["origen"] == ORIGEN_GRABACION and not _grabacion_en_uso_por_otra_voz(cliente, 0, g["id"]):
            materiales.borrar(cliente, g["id"])
    except Exception:
        log.warning("grabación %s de %s: no pude borrarla", grabacion_id, cliente, exc_info=True)


def borrar(cliente, voz_id):
    """Quita la voz, sus muestras por idioma y su grabación (si es un clon y
    ninguna OTRA voz propia la sigue usando), con sus objetos en R2. La voz en
    la cuenta de MiniMax de fal no se puede borrar desde fal.
    `materiales.MaterialEnUso` se propaga."""
    vp = obtener(cliente, voz_id)
    if not vp:
        return False
    fila = materiales.obtener(cliente, voz_id)
    for idioma in audios.IDIOMAS:
        mm = materiales.buscar_hash(cliente, _hash_muestra(vp["voice_id"], idioma))
        if mm:
            materiales.borrar(cliente, mm["id"])
    gid = (fila.get("extra") or {}).get("grabacion_id")
    if gid and not _grabacion_en_uso_por_otra_voz(cliente, voz_id, gid):
        g = materiales.obtener(cliente, gid)
        if g and g["origen"] == ORIGEN_GRABACION:
            materiales.borrar(cliente, gid)
    return materiales.borrar(cliente, voz_id)
