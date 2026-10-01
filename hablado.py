"""Anuncio hablado en Crear (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md):
una foto del proyecto + un guion leído por una voz de Audios → un video donde
la persona de la foto dice el guion (P-Video-Avatar, `flowplus_modelos.HABLADO`).

Solo lógica, sin Flask: validar la voz con las reglas de Audios, describir una
voz ya hecha con el precio de su video, listar y resolver las fotos (siempre
por ficha `cf:`/`mat:`/`cat:` de ESTE proyecto, nunca una URL que mande el
navegador) y crear la sesión de Crear que el worker genera con la misma tarea
`flowplus_video`. Las rutas viven en `hablado_rutas.py`; la voz la paga la
tarea `hablado_voz` (`tareas/hablado.py`) con `audios.voz_cruda`."""
import os
import re

import sqlalchemy as sa
from flask_babel import gettext

import audios
import catalogo_productos
import creative_flow
import db
import idiomas
import materiales
from idiomas import N_
from providers import flowplus_modelos
from storage import r2_uploader

MAX_CARACTERES = 500
MAX_MOVIMIENTO = 500
MAX_SEGUNDOS = flowplus_modelos.HABLADO[flowplus_modelos.HABLADO_POR_DEFECTO]["max_segundos"]
MAX_FOTOS = 60
EXTENSIONES_FOTO = (".jpg", ".jpeg", ".png", ".webp")
ORIGENES_FOTO = {"crear": N_("Crear"), "catalogo": N_("Catálogo"), "subida": N_("Subida")}
# msgids: la ruta los traduce al responder (EntradaInvalida.texto).
MENSAJES = {
    "largo": N_("El guion pasa de 500 caracteres."),
    "foto": N_("Elige una foto de este proyecto."),
    "foto_tipo": N_("Sube una foto jpg, png o webp."),
    "foto_subir": N_("No pude preparar esa foto; intenta de nuevo."),
    "voz_otra_vez": N_("Escucha la voz otra vez."),
    "voz_no_quedo": N_("La voz no quedó guardada: toca «Escuchar la voz» otra vez."),
    "larga": N_("Esta voz dura %(n)s s; el anuncio hablado llega a 30 s. Pártelo en tomas de unos 10 s y "
                "júntalas en el editor."),
    "movimiento": N_("«Cómo se mueve» pasa de 500 caracteres."),
    "precio": N_("El precio cambió: revísalo y vuelve a generar."),
    "en_curso": N_("Ya se está creando una voz — espera a que termine."),
}
_HASH = re.compile(r"^[0-9a-f]{64}$")


class EntradaInvalida(ValueError):
    """`msgid` (de MENSAJES o de audios.MENSAJES) y sus parámetros: `texto()`
    lo traduce en el idioma de quien mira, al responder."""

    def __init__(self, msgid, **params):
        super().__init__(msgid)
        self.msgid, self.params = msgid, params

    def texto(self):
        if self.params:
            return gettext(self.msgid, **self.params)
        return idiomas.traducir(self.msgid)


class PrecioCambio(EntradaInvalida):
    """El precio que vio la persona ya no es el que se cobraría: la ruta
    responde 409 y no se crea nada."""


def _es_url(u):
    return isinstance(u, str) and u.startswith(("https://", "http://"))


# --------------------------------------------------------------- la voz ---

def validar_voz(cliente, form):
    """`form`: request.form o un dict con texto, voz, idioma y velocidad. Las
    reglas de Audios (`audios.validar`: voz de la galería o propia de este
    proyecto, idioma y velocidad de la lista) más el tope del guion. Devuelve
    {"texto" (espacios normalizados), "voz", "idioma", "velocidad"} o lanza
    EntradaInvalida."""
    texto = " ".join((form.get("texto") or "").split())
    if len(texto) > MAX_CARACTERES:
        raise EntradaInvalida(MENSAJES["largo"])
    try:
        p = audios.validar(cliente, {"texto": texto, "voz": form.get("voz"), "idioma": form.get("idioma"),
                                     "velocidad": form.get("velocidad")})
    except audios.EntradaInvalida as e:
        raise EntradaInvalida(str(e)) from e
    return {"texto": p["texto"], "voz": p["voz"], "idioma": p["idioma"], "velocidad": p["velocidad"]}


def voz_existente(cliente, h):
    """La voz cruda de ese hash en ESTE proyecto (fila `material` tipo audio,
    origen `voz`, con duración y URL pública), o None."""
    if not isinstance(h, str) or not _HASH.match(h):
        return None
    m = materiales.buscar_hash(cliente, h)
    if (not m or m["tipo"] != "audio" or m["origen"] != audios.ORIGEN_VOZ or not m.get("duracion_ms")
            or not _es_url(m.get("url"))):
        return None
    return m


def voz_info(m):
    """Lo que la página necesita de una voz ya hecha. `precio_video`: US$ del
    video a 720p (segundos de la voz hacia arriba × tarifa), o None si la voz
    pasa de MAX_SEGUNDOS — entonces `aviso` dice cuánto dura y qué hacer.
    `duracion_s` se redondea para mostrar; el precio sale de los ms exactos."""
    segundos = int(m["duracion_ms"]) / 1000.0
    info = {"material_id": m["id"], "url": m["url"], "duracion_s": round(segundos, 2), "hash": m["hash"],
            "precio_video": None, "aviso": None}
    if segundos > MAX_SEGUNDOS:
        info["aviso"] = gettext(MENSAJES["larga"], n=flowplus_modelos.segundos_facturables(segundos))
    else:
        info["precio_video"] = flowplus_modelos.estimate_hablado(
            flowplus_modelos.HABLADO_POR_DEFECTO, segundos, flowplus_modelos.RESOLUCION_HABLADO)["usd"]
    return info


# ------------------------------------------------------------- las fotos ---

def _foto(ficha, origen, nombre, miniatura, activo_id=None):
    return {"ficha": ficha, "origen": origen, "origen_nombre": ORIGENES_FOTO[origen], "nombre": (nombre or "")[:80],
            "miniatura": miniatura, "activo_id": activo_id}


def foto_de_material(m):
    """La ficha de una foto subida: sirve una fila `material` (nombre en
    `extra`) o lo que devuelve `vista_previa.material_para` (`nombre` arriba)."""
    nombre = m.get("nombre") or (m.get("extra") or {}).get("nombre") or ""
    return _foto(f"mat:{m['id']}", "subida", nombre, m["url"])


def fotos(cliente, limite=MAX_FOTOS):
    """Las fotos que se pueden animar, todas de ESTE proyecto: las imágenes
    listas de Crear (más nuevas primero), los personajes del Catálogo (la ruta
    les pone la miniatura con url_for: aquí `miniatura` va en None) y las fotos
    subidas (`material` imagen origen `subida`, más nuevas primero)."""
    salida = []
    imagenes = [(cf_id, e) for cf_id, e in creative_flow.cargar(cliente).items()
                if e.get("tipo") == "imagen" and e.get("estado") == "video_listo" and _es_url(e.get("video_url"))]
    imagenes.sort(key=lambda par: par[1].get("creado_en") or "", reverse=True)
    for cf_id, e in imagenes[:limite]:
        salida.append(_foto(f"cf:{cf_id}", "crear", e.get("accion_central") or cf_id, e["video_url"]))
    for a in catalogo_productos.listar(cliente, "personaje"):
        salida.append(_foto(f"cat:{a['id']}", "catalogo", a.get("nombre") or a["id"], None, activo_id=a["id"]))
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "imagen", db.material.c.origen == "subida",
        ).order_by(db.material.c.id.desc()).limit(int(limite))).fetchall()
    for f in filas:
        m = dict(f._mapping)
        if _es_url(m.get("url")):
            salida.append(foto_de_material(m))
    return salida


def resolver_foto(cliente, ficha):
    """URL pública de la foto elegida, solo si es de ESTE proyecto:
    `cf:<cf_id>` (imagen lista de Crear), `mat:<id>` (foto subida) o
    `cat:<activo_id>` (personaje del Catálogo, que se sube a R2 en este
    momento, como en Crear). Cualquier otra cosa — una URL cruda, un id de
    otro proyecto — lanza EntradaInvalida."""
    tipo, _, valor = str(ficha or "").partition(":")
    if valor and tipo == "cf":
        e = creative_flow.cargar(cliente).get(valor) or {}
        if e.get("tipo") == "imagen" and e.get("estado") == "video_listo" and _es_url(e.get("video_url")):
            return e["video_url"]
    elif valor and tipo == "mat":
        try:
            m = materiales.obtener(cliente, int(valor))
        except (ValueError, OverflowError):      # un id descomunal: SQLite lanza OverflowError
            m = None
        if m and m["tipo"] == "imagen" and m["origen"] == "subida" and _es_url(m.get("url")):
            return m["url"]
    elif valor and tipo == "cat":
        a = catalogo_productos.encontrar(cliente, valor, categoria="personaje")
        if a and a.get("referencias"):
            ruta = a["referencias"][0]
            carpeta = catalogo_productos.CATEGORIAS["personaje"]["carpeta"]
            try:
                return r2_uploader.upload_image(ruta, f"clientes/{cliente}/{carpeta}/{a['id']}/{os.path.basename(ruta)}")
            except Exception as e:  # noqa: BLE001 — R2 o el archivo: nada se creó ni se cobró
                raise EntradaInvalida(MENSAJES["foto_subir"]) from e
    raise EntradaInvalida(MENSAJES["foto"])


# ------------------------------------------------------------- la pieza ---

def crear_pieza(cliente, foto_ficha, voz_hash, movimiento, precio_visto):
    """Crea la sesión de Crear del anuncio hablado y devuelve su cf_id. Antes de
    crear nada valida la foto (ficha de este proyecto), la voz (ya hecha, de
    este proyecto, ≤ MAX_SEGUNDOS), «Cómo se mueve» (≤ MAX_MOVIMIENTO) y que
    `precio_visto` sea el precio que se cobraría (si no, PrecioCambio). La
    sesión queda en `prompt_pendiente`: la lanza la ruta con
    `flowplus_lanzar.lanzar`. El guion es el texto guardado en la voz."""
    foto_url = resolver_foto(cliente, foto_ficha)
    m = voz_existente(cliente, voz_hash)
    if not m:
        raise EntradaInvalida(MENSAJES["voz_otra_vez"])
    info = voz_info(m)
    segundos = int(m["duracion_ms"]) / 1000.0
    if info["precio_video"] is None:
        raise EntradaInvalida(MENSAJES["larga"], n=flowplus_modelos.segundos_facturables(segundos))
    movimiento = (movimiento or "").strip()
    if len(movimiento) > MAX_MOVIMIENTO:
        raise EntradaInvalida(MENSAJES["movimiento"])
    try:
        visto = float(precio_visto)
    except (TypeError, ValueError):
        visto = None
    if visto is None or abs(visto - info["precio_video"]) > 0.0005:
        raise PrecioCambio(MENSAJES["precio"])
    extra = m.get("extra") or {}
    guion = extra.get("texto") or ""
    cf_id = creative_flow.crear(cliente, [], [], [], guion, flowplus_modelos.segundos_facturables(segundos), "", "A",
                                referencias_urls=[foto_url], platforms=[])
    creative_flow.actualizar(
        cliente, cf_id, tipo="video", modelo=flowplus_modelos.HABLADO_POR_DEFECTO, modo_crear="hablado",
        con_sonido=True, musica_estilo="", enfoque="persona", enfoque_nombre=N_("Anuncio hablado"),
        con_persona=True, prompt_fuente=guion, aspect_ratio=None,
        hablado={"foto_url": foto_url, "foto_ficha": foto_ficha, "voz_material_id": m["id"], "voz_url": m["url"],
                 "voz_duracion_s": info["duracion_s"], "voz": extra.get("voz_ref") or extra.get("voz") or "",
                 "idioma": extra.get("idioma") or "", "velocidad": extra.get("velocidad") or "normal",
                 "movimiento": movimiento, "resolucion": flowplus_modelos.RESOLUCION_HABLADO})
    return cf_id
