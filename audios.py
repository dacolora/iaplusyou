"""Audios en Crear (spec docs/superpowers/specs/2026-09-28-crear-audios-design.md):
una locución de ElevenLabs (vía fal) con la voz que la persona elige, sola o
sobre una canción de Mi música, como mp3 para escuchar y descargar.

Único escritor de las filas `material` con origen `locucion` (el audio final) y
de las voces crudas con hash `locucion_voz` (origen `voz`, como las de las
finales pero con su propio hash, que incluye la velocidad). Las muestras de
voz viven en el cliente interno `_creatv` y las paga Creatv. No importa
final_edition.musica al cargar (esa importa mi_musica; la tarea la usa).

Desde el 2026-09-30 habla once idiomas y decide el motor por voz e idioma
(`motor_de`): ElevenLabs Multilingual v2, Turbo v2.5 para el noruego y
MiniMax para las voces propias (`voces_propias.py`)."""
import os
import shutil
import tempfile
import time

import sqlalchemy as sa
from flask_babel import gettext

import db
import gastos
import idiomas
import materiales
import mi_musica
from final_edition import cortes, mezcla
from providers import fal_audio
from storage import r2_uploader

ORIGEN = "locucion"
ORIGEN_VOZ = "voz"
CLIENTE_MUESTRAS = "_creatv"
VERSION_MUESTRA = 1
IDIOMAS = ("es", "en", "pt", "de", "fr", "it", "fi", "sv", "no", "cs", "nl")
# Cada idioma en su propia lengua (así lo reconoce quien lo habla).
NOMBRES_IDIOMA = {"es": "Español", "en": "English", "pt": "Português", "de": "Deutsch", "fr": "Français",
                  "it": "Italiano", "fi": "Suomi", "sv": "Svenska", "no": "Norsk", "cs": "Čeština", "nl": "Nederlands"}
# Idiomas que Multilingual v2 no habla: la galería los lee con Turbo v2.5 y
# el idioma forzado (spec 2026-09-30 §2). Vive en fal_audio para que las
# finales usen la misma tupla (`fal_audio.tts_galeria`).
IDIOMAS_TURBO = fal_audio.IDIOMAS_TURBO
PREFIJO_VOZ_PROPIA = "vp:"
MOTOR_ELEVENLABS = "elevenlabs"
MOTOR_TURBO = "elevenlabs_turbo"
MOTOR_MINIMAX = "minimax"
ETIQUETAS_MOTOR = {MOTOR_ELEVENLABS: "ElevenLabs", MOTOR_TURBO: "ElevenLabs Turbo", MOTOR_MINIMAX: "MiniMax"}
VELOCIDADES = {"lenta": 0.85, "normal": 1.0, "rapida": 1.15}
NOMBRES_VELOCIDAD = {"lenta": idiomas.N_("Lenta"), "normal": idiomas.N_("Normal"), "rapida": idiomas.N_("Rápida")}
VOLUMENES = {"baja": 0.2, "media": 0.35, "alta": 0.5}
NOMBRES_VOLUMEN = {"baja": idiomas.N_("Baja"), "media": idiomas.N_("Media"), "alta": idiomas.N_("Alta")}
VOLUMEN_DEFECTO = "media"
MAX_CARACTERES = 3000
# Con música: la música arranca INTRO_MS antes de la voz, sigue COLA_MS
# después y se desvanece en FUNDIDO_MS (spec §2).
INTRO_MS = 600
COLA_MS = 1500
FUNDIDO_MS = 1500
FRASES_MUESTRA = {
    "es": "Hola, soy {voz}. Así suena mi voz en tu anuncio.",
    "en": "Hi, I'm {voz}. This is how my voice sounds in your ad.",
    "pt": "Olá, eu sou {voz}. É assim que a minha voz soa no seu anúncio.",
    "de": "Hallo, ich bin {voz}. So klingt meine Stimme in deiner Anzeige.",
    "fr": "Bonjour, je suis {voz}. Voici comment sonne ma voix dans votre publicité.",
    "it": "Ciao, sono {voz}. Ecco come suona la mia voce nel tuo annuncio.",
    "fi": "Hei, olen {voz}. Tältä ääneni kuulostaa mainoksessasi.",
    "sv": "Hej, jag heter {voz}. Så här låter min röst i din annons.",
    "no": "Hei, jeg heter {voz}. Slik høres stemmen min ut i annonsen din.",
    "cs": "Dobrý den, jsem {voz}. Takhle zní můj hlas ve vaší reklamě.",
    "nl": "Hallo, ik ben {voz}. Zo klinkt mijn stem in jouw advertentie.",
}
# msgids: la ruta los traduce con idiomas.traducir al responder.
MENSAJES = {
    "texto": idiomas.N_("Escribe el texto que quieres que lea la voz."),
    "largo": idiomas.N_("El texto pasa de 3 000 caracteres."),
    "voz": idiomas.N_("Elige una voz de la lista."),
    "idioma": idiomas.N_("Elige un idioma de la lista."),
    "velocidad": idiomas.N_("Elige una velocidad de la lista."),
    "volumen": idiomas.N_("Elige un volumen de la lista."),
    "musica": idiomas.N_("Esa canción ya no está en Mi música."),
    "en_curso": idiomas.N_("Ya se está creando un audio — espera a que termine."),
    "voz_borrada": idiomas.N_("Esa voz ya no está en Mis voces."),
}


class EntradaInvalida(ValueError):
    """`str(e)` es un msgid de MENSAJES: traducir al mostrar."""


def voces():
    return list(fal_audio.VOCES["es"])


def es_propia(voz):
    return isinstance(voz, str) and voz.startswith(PREFIJO_VOZ_PROPIA)


def motor_de(voz, idioma):
    """Qué motor lee esa voz en ese idioma (spec 2026-09-30 §2): las voces
    propias van por MiniMax; las de la galería por Multilingual v2, salvo en
    los idiomas que v2 no habla (IDIOMAS_TURBO), que van por Turbo v2.5."""
    if es_propia(voz):
        return MOTOR_MINIMAX
    if idioma in IDIOMAS_TURBO:
        return MOTOR_TURBO
    return MOTOR_ELEVENLABS


# Género y tono de cada voz premade de ElevenLabs según su biblioteca por defecto
# (2026-09-29): solo orientan la galería de Audios, la persona decide por el
# oído. El tono concuerda con «voz» (femenino). Una voz que salga de
# fal_audio.VOCES debe salir de aquí también (tests/test_audios.py lo vigila).
GENEROS = {"mujer": idiomas.N_("Mujer"), "hombre": idiomas.N_("Hombre"), "neutra": idiomas.N_("Neutra")}
VOCES_INFO = {
    "Rachel": ("mujer", idiomas.N_("calmada")),
    "Adam": ("hombre", idiomas.N_("grave")),
    "Charlotte": ("mujer", idiomas.N_("seductora")),
    "Matilda": ("mujer", idiomas.N_("amable")),
    "Daniel": ("hombre", idiomas.N_("autoritaria, británica")),
    "Aria": ("mujer", idiomas.N_("expresiva")),
    "Roger": ("hombre", idiomas.N_("segura")),
    "Sarah": ("mujer", idiomas.N_("suave")),
    "Laura": ("mujer", idiomas.N_("animada")),
    "Charlie": ("hombre", idiomas.N_("natural, australiana")),
    "George": ("hombre", idiomas.N_("cálida, británica")),
    "Callum": ("hombre", idiomas.N_("intensa")),
    "River": ("neutra", idiomas.N_("segura")),
    "Liam": ("hombre", idiomas.N_("articulada")),
    "Alice": ("mujer", idiomas.N_("segura, británica")),
    "Jessica": ("mujer", idiomas.N_("expresiva")),
    "Eric": ("hombre", idiomas.N_("amigable")),
    "Chris": ("hombre", idiomas.N_("casual")),
    "Brian": ("hombre", idiomas.N_("profunda")),
    "Lily": ("mujer", idiomas.N_("cálida, británica")),
    "Bill": ("hombre", idiomas.N_("confiable")),
    "Will": ("hombre", idiomas.N_("amigable")),
}


def fichas_voces():
    """Una ficha por voz, en el orden de VOCES: {nombre, genero, genero_nombre
    (msgid), tono (msgid)} para la galería de la plantilla."""
    fichas = []
    for v in voces():
        genero, tono = VOCES_INFO.get(v, ("neutra", ""))
        fichas.append({"nombre": v, "genero": genero, "genero_nombre": GENEROS[genero], "tono": tono})
    return fichas


def idioma_defecto(cliente):
    i = idiomas.de_proyecto(cliente)
    return i if i in IDIOMAS else "es"


def nombre_de(texto):
    t = " ".join((texto or "").split())
    return t if len(t) <= 60 else t[:59].rstrip() + "…"


def validar(cliente, form):
    """`form`: request.form o un dict. Devuelve el payload de la tarea o lanza
    EntradaInvalida (msgid)."""
    texto = " ".join((form.get("texto") or "").split())
    if not texto:
        raise EntradaInvalida(MENSAJES["texto"])
    if len(texto) > MAX_CARACTERES:
        raise EntradaInvalida(MENSAJES["largo"])
    voz = (form.get("voz") or "").strip()
    if es_propia(voz):
        import voces_propias   # importa este módulo: se importa aquí, no arriba
        if not voces_propias.resolver(cliente, voz):
            raise EntradaInvalida(MENSAJES["voz"])
    elif voz not in voces():
        raise EntradaInvalida(MENSAJES["voz"])
    idioma = (form.get("idioma") or "").strip()
    if idioma not in IDIOMAS:
        raise EntradaInvalida(MENSAJES["idioma"])
    velocidad = (form.get("velocidad") or "normal").strip()
    if velocidad not in VELOCIDADES:
        raise EntradaInvalida(MENSAJES["velocidad"])
    volumen = (form.get("volumen") or VOLUMEN_DEFECTO).strip()
    if volumen not in VOLUMENES:
        raise EntradaInvalida(MENSAJES["volumen"])
    musica_id, inicio_s = None, 0
    valor = (form.get("musica") or "").strip()
    if valor:
        m = mi_musica.resolver(cliente, valor)
        if not m:
            raise EntradaInvalida(MENSAJES["musica"])
        musica_id = m["id"]
        inicio_s = mi_musica.inicio_valido(m, form.get("inicio_s"))
    return {"texto": texto, "voz": voz, "idioma": idioma, "velocidad": velocidad,
            "musica_id": musica_id, "inicio_s": inicio_s, "volumen": volumen}


# ------------------------------------------------------------- hashes ---

def hash_voz(texto, voz, idioma, velocidad):
    """Mismo texto + voz + velocidad → la voz cruda no se paga dos veces. Con
    Multilingual v2 el idioma no entra (el modelo lo detecta del texto) y la
    fórmula es la de siempre, para no invalidar lo ya cacheado; con Turbo y
    MiniMax el idioma sí cambia lo que suena, así que entran el motor y el
    idioma."""
    motor = motor_de(voz, idioma)
    vel = f"{VELOCIDADES[velocidad]:.2f}"
    if motor == MOTOR_ELEVENLABS:
        return materiales.hash_clave("locucion_voz", texto, voz, vel)
    return materiales.hash_clave("locucion_voz", motor, texto, voz, idioma, vel)


def hash_audio(h_voz, musica_id, inicio_s, volumen):
    """Misma voz + misma canción, inicio y volumen → el mismo audio (sin
    música, el volumen no cuenta)."""
    if not musica_id:
        return materiales.hash_clave("locucion", h_voz, "", 0, "")
    return materiales.hash_clave("locucion", h_voz, int(musica_id), int(inicio_s or 0), volumen)


# ---------------------------------------------------------- sintetizar ---

def sintetizar(cliente, voz, texto, idioma, velocidad):
    """Lee `texto` con `voz` en `idioma` por el motor que toca (motor_de).
    Devuelve {"url", "costo_usd", "proveedor", "etiqueta", "voz_nombre"}. No
    registra gasto: lo hace quien llama, apenas vuelve (ya pagado)."""
    v = VELOCIDADES[velocidad]
    motor = motor_de(voz, idioma)
    if motor == MOTOR_MINIMAX:
        import voces_propias
        vp = voces_propias.resolver(cliente, voz)
        if not vp:
            raise ValueError(MENSAJES["voz_borrada"])
        r = voces_propias.sintetizar(cliente, vp, texto, idioma, velocidad=v)
        return {"url": r["url"], "costo_usd": r["costo_usd"], "proveedor": "fal/minimax",
                "etiqueta": ETIQUETAS_MOTOR[motor], "voz_nombre": vp["nombre"]}
    if motor == MOTOR_TURBO:
        r = fal_audio.tts(texto, voz, idioma, velocidad=v, modelo=fal_audio.MODELO_TTS_TURBO, language_code=idioma)
    else:
        r = fal_audio.tts(texto, voz, idioma, velocidad=v)
    return {"url": r["url"], "costo_usd": r["costo_usd"], "proveedor": "fal/elevenlabs",
            "etiqueta": ETIQUETAS_MOTOR[motor], "voz_nombre": voz}


def voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo, carpeta=None):
    """La voz cruda de `texto` (fila `material` tipo audio, origen `voz`, hash
    `hash_voz`). Si ya existe en este proyecto — también si se hizo en Audios
    o en el anuncio hablado — sale de la caché sin pagar. Si no, la sintetiza
    (`sintetizar`, el motor que toca), registra el gasto `locucion`
    (`locucion:<hash12><ref_sufijo>`) apenas el proveedor cobra — ANTES de
    bajarla y subirla, así un fallo después no pierde lo pagado —, la sube a R2
    (`clientes/<c>/materiales/voz_<h16>.mp3`) y crea la fila. Devuelve
    `(material, creado)`. `carpeta`: donde bajar el mp3 (Audios la pasa y lo
    anota en `extra.local` para mezclarlo sin volver a bajarlo); sin carpeta,
    un temporal que se borra apenas se sube."""
    h_voz = hash_voz(texto, voz, idioma, velocidad)
    referencia = f"locucion:{h_voz[:12]}{ref_sufijo}"

    def _producir():
        r = sintetizar(cliente, voz, texto, idioma, velocidad)
        usd = float(r.get("costo_usd") or 0.0)
        # El proveedor ya cobró: el gasto queda aunque lo que sigue falle.
        gastos.registrar_seguro(cliente, "locucion", usd, referencia,
                                detalle=gettext("%(motor)s · %(n)s caracteres · %(voz)s", motor=r["etiqueta"],
                                                n=len(texto), voz=r["voz_nombre"]),
                                proveedor=r["proveedor"])
        destino = carpeta or tempfile.mkdtemp(prefix="voz_cruda_")
        try:
            local = descargar_url(r["url"], os.path.join(destino, f"voz_{h_voz[:16]}.mp3"))
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h_voz[:16]}.mp3", "audio/mpeg")
            extra = {"texto": texto, "voz": r["voz_nombre"], "voz_ref": voz, "idioma": idioma, "velocidad": velocidad,
                     "nombre": nombre_de(texto)}   # el editor la lista por su nombre (capa 5a)
            if carpeta:
                extra["local"] = local
            return {"tipo": "audio", "origen": ORIGEN_VOZ, "url": url, "bytes": os.path.getsize(local),
                    "duracion_ms": int(round(cortes.duracion(local) * 1000)), "costo_usd": usd, "extra": extra}
        finally:
            if not carpeta:
                shutil.rmtree(destino, ignore_errors=True)
    return materiales.obtener_o_crear(cliente, h_voz, _producir)


# ------------------------------------------------------------- mezcla ---

def duracion_total_ms(voz_ms, con_musica):
    return int(voz_ms) + (INTRO_MS + COLA_MS if con_musica else 0)


def filtro_locucion(con_musica, volumen, total_ms):
    """Filtergraph puro (spec §2). Voz en `[0:a]`; música en `[1:a]` (el
    llamador la mete con -stream_loop -1 y cierra con -t total). El fundido
    va DESPUÉS del loudnorm: la normalización de una pasada levantaría la cola."""
    if not con_musica:
        return f"[0:a]{mezcla.NORM},{mezcla.LOUDNORM}[aout]"
    v = VOLUMENES[volumen]
    inicio_fundido = max(0, int(total_ms) - FUNDIDO_MS) / 1000.0
    return ";".join([
        f"[0:a]{mezcla.NORM},adelay={INTRO_MS}|{INTRO_MS},apad,asplit=2[voz_mix][voz_sc]",
        f"[1:a]{mezcla.NORM},volume={v}[mus]",
        f"[mus][voz_sc]sidechaincompress={mezcla.DUCKING_VOZ_SOBRE_MUSICA}[mus_d]",
        f"[voz_mix][mus_d]amix=inputs=2:duration=first:normalize=0,{mezcla.LOUDNORM},"
        f"afade=t=out:st={inicio_fundido:.3f}:d={FUNDIDO_MS / 1000.0:.3f}[aout]",
    ])


def mezclar(voz_path, musica_path, salida_mp3, voz_ms, volumen):
    """Voz (+ música en bucle) → mp3 192 kbps 44,1 kHz estéreo. Devuelve
    {"archivo", "duracion_ms"} (medida con ffprobe)."""
    con_musica = bool(musica_path)
    total_ms = duracion_total_ms(voz_ms, con_musica)
    args = ["-i", voz_path]
    if con_musica:
        args += ["-stream_loop", "-1", "-i", musica_path]
    args += ["-filter_complex", filtro_locucion(con_musica, volumen, total_ms), "-map", "[aout]",
             "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2",
             "-t", f"{total_ms / 1000.0:.3f}", salida_mp3]
    cortes.ffmpeg(args, timeout=max(120, int(total_ms / 1000.0 * 5)))
    return {"archivo": salida_mp3, "duracion_ms": int(round(cortes.duracion(salida_mp3) * 1000))}


# --------------------------------------------------------------- datos ---

def _como_audio(m):
    extra = m.get("extra") or {}
    return {"id": m["id"], "nombre": extra.get("nombre") or f"Audio {m['id']}", "texto": extra.get("texto") or "",
            "duracion_s": round((m.get("duracion_ms") or 0) / 1000.0, 1), "url": m["url"],
            "voz": extra.get("voz") or "", "idioma": extra.get("idioma") or "",
            "velocidad": extra.get("velocidad") or "normal", "volumen": extra.get("volumen") or VOLUMEN_DEFECTO,
            "musica": extra.get("musica") or None, "creado_en": m.get("creado_en")}


def listar(cliente):
    """Los audios del proyecto, más reciente primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen == ORIGEN).order_by(db.material.c.id.desc())).all()
    return [_como_audio(dict(f._mapping)) for f in filas]


def obtener(cliente, audio_id):
    m = materiales.obtener(cliente, audio_id)
    if not m or m["tipo"] != "audio" or m["origen"] != ORIGEN:
        return None
    return _como_audio(m)


def borrar(cliente, audio_id):
    """Solo audios de este cliente. `materiales.MaterialEnUso` se propaga."""
    a = obtener(cliente, audio_id)
    if not a:
        return False
    return materiales.borrar(cliente, a["id"])


# ------------------------------------------------------------ muestras ---

def descargar_url(url, destino):
    import requests
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return destino


def hash_muestra(voz, idioma):
    return materiales.hash_clave("muestra_voz", voz, idioma, VERSION_MUESTRA)


def muestra(voz, idioma):
    """URL de la muestra de esa voz en ese idioma. Se sintetiza una sola vez
    para toda la plataforma (cliente `_creatv`, gasto de `_creatv`), con un
    timeout corto (45 s: es una frase de una línea, nunca un guion largo) para
    que un fal lento no cuelgue el clic de «Escuchar». El gasto se registra
    apenas fal cobra, ANTES de bajar/subir el archivo: si algo de eso falla
    después, el dinero ya pagado queda anotado — la referencia lleva un sello
    de tiempo por llamada (nunca la misma entre reintentos), así que un
    reintento tras un pago fallido registra su propio gasto en vez de pisar el
    de un intento anterior que también pagó (revisión final F5) — y el hash no
    queda cacheado, así que el siguiente intento vuelve a sintetizar.
    ValueError si la voz o el idioma no existen; los errores de fal/R2 se
    propagan."""
    if voz not in voces() or idioma not in IDIOMAS:
        raise ValueError(gettext("voz o idioma desconocidos"))
    h = hash_muestra(voz, idioma)
    frase = FRASES_MUESTRA[idioma].format(voz=voz)

    def _producir():
        if idioma in IDIOMAS_TURBO:
            r = fal_audio.tts(frase, voz, idioma, timeout=45, modelo=fal_audio.MODELO_TTS_TURBO, language_code=idioma)
        else:
            r = fal_audio.tts(frase, voz, idioma, timeout=45)
        usd = float(r.get("costo_usd") or 0.0)
        # fal ya cobró: el gasto queda aunque lo que sigue falle. El sello de
        # tiempo hace la referencia única por llamada: sin él, dos intentos
        # (uno fallido tras pagar, y su reintento) pisaban la misma fila de
        # gasto y solo uno de los dos pagos quedaba anotado.
        ref = f"muestra_voz:{voz}:{idioma}:v{VERSION_MUESTRA}:{int(time.time() * 1000)}"
        # El detalle se GUARDA: va en el idioma de `_creatv` (el de defecto),
        # no en el de quien escucha la muestra ni en el msgid crudo que da
        # gettext fuera de toda app (precalentar_muestras.py corre sin app).
        with idiomas.en_idioma(idiomas.de_tarea({"cliente": CLIENTE_MUESTRAS})):
            detalle = gettext("muestra de voz · %(voz)s · %(idioma)s", voz=voz, idioma=idioma)
        gastos.registrar_seguro(CLIENTE_MUESTRAS, "locucion", usd, ref, detalle=detalle, proveedor="fal/elevenlabs")
        with tempfile.TemporaryDirectory() as tmp:
            local = descargar_url(r["url"], os.path.join(tmp, "muestra.mp3"))
            key = f"clientes/{CLIENTE_MUESTRAS}/materiales/muestra_{voz}_{idioma}_v{VERSION_MUESTRA}.mp3"
            campos = {"tipo": "audio", "origen": ORIGEN_VOZ, "url": r2_uploader.upload_file(local, key, "audio/mpeg"),
                      "bytes": os.path.getsize(local), "duracion_ms": int(round(cortes.duracion(local) * 1000)),
                      "costo_usd": usd, "extra": {"texto": frase, "voz": voz, "idioma": idioma, "muestra": True}}
        return campos
    m, _ = materiales.obtener_o_crear(CLIENTE_MUESTRAS, h, _producir)
    return m["url"]
