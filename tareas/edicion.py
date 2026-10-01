"""Tareas del worker para el editor (spec §2.4):
  edicion_producir  {cliente, edicion_id, version_id, final_id, idioma, pais}  max_intentos=1
  edicion_proxy     {cliente, material_id}                                     max_intentos=3
  edicion_desde_clon {cliente, cf_id}                                          max_intentos=2
  material_de_pieza {cliente, cf_id}                                           max_intentos=2
  material_transcribir {cliente, edicion_id, material_ids, idioma}             max_intentos=1
  materiales_limpiar {}                                                         periódica diaria
`edicion_producir` renderiza el documento CONGELADO en la versión (no el
vivo), así lo que se produjo siempre se puede volver a ver. Contrato con la
ruta que la encola (capa 3): `ediciones.versionar` → `creative_flow.crear_final`
(la fila final DEBE existir: si `actualizar_final`/`apuntar_final` no la
encuentran, la tarea falla y lo dice) → `trabajos.encolar(..., max_intentos=1,
duracion_estimada=estimar.segundos(doc), etapas=ETAPAS_EDICION)`. `idioma` y
`pais` se validan con forma (`[a-z]{2}` / `[A-Z]{2}`) antes de tocar el disco
porque forman parte del nombre de la carpeta de trabajo. `edicion_desde_clon`
(capa 4a, «Editar este video») hace el trabajo pesado de
`final_edition.edicion_clon.crear` (bajar el clon, medirlo) fuera del hilo de
Flask; no paga nada, así que un reintento no importa (`max_intentos=2`).
`material_transcribir` (editor capa 5a, D5/D6) paga Whisper una vez por
material (`final_edition/transcripcion.py`) y sigue con los demás si uno
falla — lo que sí se transcribió no se pierde."""
import logging
import math
import os
import re
import shutil
import subprocess

from flask_babel import gettext, ngettext

import cola
import creative_flow
import ediciones
import idiomas
import materiales
import trabajos
from final_edition import cortes, mezcla, motor, rasterizar, subtitulos_fuente, transcripcion
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from idiomas import N_
from storage import r2_uploader
from tareas import al_interrumpir, ref_sufijo, registrar

log = logging.getLogger(__name__)

# N_: se guardan en español y `estado_trabajo` las traduce para quien mira.
ETAPAS_EDICION = ((N_("Preparando materiales"), 15), (N_("Renderizando"), 70), (N_("Subiendo"), 15))
# Editor capa 5a: etapas de `material_transcribir` y mensajes finales de las
# tareas de audio del editor (también usado por `editor_voz`, Task 6).
ETAPAS_TRANSCRIBIR = ((N_("Preparando el audio"), 20), (N_("Transcribiendo"), 70), (N_("Guardando"), 10))
MENSAJES_AUDIO_EDITOR = {
    "subtitulos_listos": N_("Subtítulos listos."),
}
_EXT = {"video": "mp4", "imagen": "png", "audio": "wav", "png_texto": "png", "proxy": "mp4"}
_IDIOMA_RE = re.compile(r"[a-z]{2}")
_PAIS_RE = re.compile(r"[A-Z]{2}")
_CF_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")

# Proxy de la vista previa (spec §2.3): lado CORTO en 540 (un vertical sale
# 540x960, no 304x540), cuadro clave cada 15 cuadros (medio segundo a 30 fps)
# para que buscar un instante no decodifique segundos enteros, yuv420p para
# Safari. Subir PROXY_VERSION cuando cambie la receta: la página del editor
# rehace los proxies de versión anterior.
PROXY_VERSION = 2
_ESCALA_PROXY = "scale='if(gt(iw,ih),-2,540)':'if(gt(iw,ih),540,-2)'"


def generar_proxy(original, destino):
    cortes.ffmpeg(["-i", original, "-vf", _ESCALA_PROXY, "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1M",
                   "-g", "15", "-keyint_min", "15", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", destino], timeout=900)


def _extension(tipo):
    ext = _EXT.get(tipo)
    if not ext:
        raise RuntimeError(gettext("Tipo de material sin extensión conocida: %(tipo)s", tipo=tipo))
    return ext


def job_id_producir(cliente, edicion_id, idioma, pais):
    return f"{cliente}__ed{int(edicion_id)}__{idioma}_{pais}__producir"


def job_id_proxy(cliente, material_id):
    return f"{cliente}__mat{int(material_id)}__proxy"


def job_id_transcribir(cliente, edicion_id):
    return f"{cliente}__ed{int(edicion_id)}__subtitulos"


def job_id_desde_clon(cliente, cf_id):
    return f"{cliente}__{cf_id}__editor"


def job_id_material_de_pieza(cliente, cf_id):
    return f"{cliente}__{cf_id}__material"


def _carpeta(cliente, nombre):
    raiz = os.environ.get("CREATV_SALIDAS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "salidas")
    c = os.path.join(raiz, cliente, "ediciones", nombre)
    os.makedirs(c, exist_ok=True)
    return c


def _palabras_por_material(cliente, resuelto):
    """`{material_id: palabras}` (D1/D5, capa 5a) solo para los materiales
    del documento RESUELTO que ya tienen `extra.palabras` (una lista: una
    transcripción vacía cuenta como hecha). Lo que usa
    `subtitulos_fuente.derivar` antes de renderizar."""
    salida = {}
    for mid in resuelto.get("materiales") or []:
        mat = materiales.obtener(cliente, mid)
        palabras = (mat or {}).get("extra") or {}
        palabras = palabras.get("palabras")
        if isinstance(palabras, list):
            salida[int(mid)] = palabras
    return salida


def preparar_rutas(cliente, doc, carpeta):
    """Baja los materiales del documento a `carpeta` y devuelve `rutas`
    ({material_id: ruta, "png:<clip_id>": ruta, "ass": ruta}). De paso, con
    las filas ya en mano: estampa `ancho_px`/`alto_px` en los clips `imagen`
    que no los traen (tamaño natural medido al subir), rasteriza con Pillow
    los clips de texto sin `pngs` y pasa los recortes por
    `compilador.verificar_recortes` con las duraciones reales (`duracion_ms`
    de la fila, cuando el proxy ya la midió) — modifica `doc` en el sitio."""
    rutas = {"ass": os.path.join(carpeta, "subtitulos.ass")}
    ids = set(int(x) for x in doc.get("materiales") or [])
    for p in doc.get("pistas") or []:
        for cl in p.get("clips") or []:
            if cl.get("material_id"):
                ids.add(int(cl["material_id"]))
    filas = {}
    for mid in sorted(ids):
        mat = materiales.obtener(cliente, mid)
        if not mat:
            raise RuntimeError(gettext("Falta el material %(mid)s de este proyecto.", mid=mid))
        filas[mid] = mat
        destino = os.path.join(carpeta, f"{mid}.{_extension(mat['tipo'])}")
        rutas[mid] = materiales.descargar(mat, destino)
    for clip_id, mid in (doc.get("pngs") or {}).items():
        mat = materiales.obtener(cliente, mid)
        if mat:
            rutas[f"png:{clip_id}"] = materiales.descargar(mat, os.path.join(carpeta, f"png_{clip_id}.png"))
    # Textos sin PNG del navegador (la vía automática no tiene navegador):
    # el servidor los rasteriza con las mismas TTF. El doc ya está resuelto
    # (literal); un clip variable aquí es un error de quien llama.
    for p in doc.get("pistas") or []:
        if p.get("tipo") != "texto":
            continue
        for cl in p.get("clips") or []:
            clave = f"png:{cl['id']}"
            if clave in rutas:
                continue
            literal = (cl.get("texto") or {}).get("literal")
            if literal is None:
                raise RuntimeError(gettext("El clip de texto %(clip)s no está resuelto (¿falta documento.resolver?).",
                                           clip=cl["id"]))
            medidas = rasterizar.png_texto(literal, cl.get("estilo") or {}, doc["formato"],
                                           os.path.join(carpeta, f"png_{cl['id']}.png"))
            rutas[clave] = os.path.join(carpeta, f"png_{cl['id']}.png")
            cl["ancho_px"], cl["alto_px"] = medidas["ancho_px"], medidas["alto_px"]
    for p in doc.get("pistas") or []:
        if p.get("tipo") != "imagen":
            continue
        for cl in p.get("clips") or []:
            mat = filas.get(int(cl["material_id"])) if cl.get("material_id") else None
            if mat and not cl.get("ancho_px") and not cl.get("alto_px") and mat.get("ancho") and mat.get("alto"):
                cl["ancho_px"], cl["alto_px"] = int(mat["ancho"]), int(mat["alto"])
    duraciones = {mid: int(mat["duracion_ms"]) for mid, mat in filas.items() if mat.get("duracion_ms")}
    compilador.verificar_recortes(doc, duraciones)
    return rutas


def renderizar_final(cliente, final_id, version_id, idioma, pais, avisar=None):
    """Renderiza la versión CONGELADA `version_id` para `idioma`/`pais` y
    sube el mp4/png con clave versionada (`<final_id>__v<version_id>`;
    miniatura primero). Devuelve {url_video, url_miniatura, duracion_s,
    tramos, con_ass, version_id, es_imagen}. NO toca la fila final: eso lo
    hace quien llama (`edicion_producir` o `final_edition.produccion`).
    Lanza si algo falla y deja la carpeta de trabajo (el .filtergraph.txt es
    la evidencia); en éxito la borra. `avisar` recibe las etapas de
    ETAPAS_EDICION y las del motor ("Renderizando tramo i/n")."""
    avisar = avisar or (lambda n: None)
    # idioma/pais forman el nombre de la carpeta de trabajo: se validan
    # ANTES de tocar el disco (un `../x` no debe ni crearla).
    if not isinstance(idioma, str) or not _IDIOMA_RE.fullmatch(idioma):
        raise ValueError(gettext("idioma inválido: %(idioma)s (se esperan dos letras minúsculas).", idioma=repr(idioma)))
    if not isinstance(pais, str) or not _PAIS_RE.fullmatch(pais):
        raise ValueError(gettext("país inválido: %(pais)s (se esperan dos letras mayúsculas).", pais=repr(pais)))
    v = ediciones.version(cliente, version_id)
    if not v:
        raise RuntimeError(gettext("No existe esa versión de la edición."))
    carpeta = _carpeta(cliente, f"{v['edicion_id']}_{idioma}_{pais}")
    # Como mucho una corrida fallida por destino queda en disco: un
    # reintento arranca de carpeta limpia (vacía pero existente).
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta, exist_ok=True)
    avisar(ETAPAS_EDICION[0][0])
    doc = documento_mod.resolver(documento_mod.validar(documento_mod.migrar(v["documento"])), idioma, pais)
    # D1 (capa 5a): los subtítulos se derivan del audio AQUÍ, sobre el
    # documento ya resuelto para este destino — nunca antes (`resolver` ya
    # aplicó `por_destino` y quitó los audios de otro idioma).
    doc = subtitulos_fuente.aplicar(doc, _palabras_por_material(cliente, doc))
    rutas = preparar_rutas(cliente, doc, carpeta)
    avisar(ETAPAS_EDICION[1][0])
    es_imagen = documento_mod.duracion_ms(doc) == 0
    salida = os.path.join(carpeta, f"{final_id}.{'png' if es_imagen else 'mp4'}")
    res = motor.renderizar(doc, rutas, salida, on_etapa=avisar, nucleos=int(os.environ.get("RENDER_NUCLEOS", "1")))
    avisar(ETAPAS_EDICION[2][0])
    # Claves versionadas (I1, capa 1): un reintento nunca pisa el archivo
    # que la fila todavía enlaza. La miniatura sube ANTES que el video.
    if es_imagen:
        url = r2_uploader.upload_image(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
        url_mini = url
    else:
        url_mini = r2_uploader.upload_image(res["miniatura"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
        url = r2_uploader.upload_video(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.mp4")
    shutil.rmtree(carpeta, ignore_errors=True)
    return {"url_video": url, "url_miniatura": url_mini, "duracion_s": float(res["duracion_s"]), "tramos": res["tramos"],
            "con_ass": res["con_ass"], "version_id": v["id"], "es_imagen": es_imagen}


@registrar("edicion_producir")
def ejecutar_producir(tarea):
    p = tarea["payload"]
    cliente, final_id = p["cliente"], p["final_id"]
    job_id = tarea.get("job_id") or job_id_producir(cliente, p["edicion_id"], p["idioma"], p["pais"])
    avisar = lambda n: trabajos.reportar(job_id, etapa=n)
    # Sin gasto: los materiales ya existen (la vía automática paga en
    # final_edition.produccion, no aquí).
    try:
        res = renderizar_final(cliente, final_id, p["version_id"], p["idioma"], p["pais"], avisar)
        # La fila final la crea la ruta (creative_flow.crear_final) antes de
        # encolar: si no está, esto no puede "terminar bien" en silencio.
        if not creative_flow.actualizar_final(cliente, final_id, estado="listo", url_video=res["url_video"],
                                              url_miniatura=res["url_miniatura"], duracion_s=res["duracion_s"],
                                              capas={"render": {"edicion_version_id": res["version_id"], "tramos": res["tramos"],
                                                                "con_ass": res["con_ass"]}}):
            raise RuntimeError(gettext("La final %(final)s no existe; la ruta debe crearla con creative_flow.crear_final "
                                       "antes de encolar.", final=final_id))
        if not ediciones.apuntar_final(cliente, final_id, res["version_id"]):
            raise RuntimeError(gettext("La final %(final)s no existe en pieza; la ruta debe crearla con "
                                       "creative_flow.crear_final antes de encolar.", final=final_id))
        return gettext("Final %(destino)s lista.", destino=f"{p['idioma']}/{p['pais']}")
    except Exception as e:
        # I3 (capa 1): nunca un token crudo en la columna de error.
        creative_flow.actualizar_final(cliente, final_id, estado="error",
                                       error=cola.recortar(cola.sin_token(str(e)), 500))
        raise  # la carpeta queda: el .filtergraph.txt es la evidencia para depurar.


@al_interrumpir("edicion_producir")
def _interrumpido(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("final_id"):
        # Se guarda en la final (la pestaña Final edition lo muestra): el idioma del
        # proyecto. El hook no pasa por worker.ejecutar (como tareas/nicho.py).
        with idiomas.en_idioma(idiomas.de_proyecto(p["cliente"])):
            error = gettext("interrumpido: %(mensaje)s", mensaje=cola.recortar(cola.sin_token(str(mensaje)), 500))
        creative_flow.actualizar_final(p["cliente"], p["final_id"], estado="error", error=error)


def _picos(ruta, ventana_ms=50):
    """Envolvente de energía por ventanas con `astats` (sin numpy).
    `aresample=48000` va SIEMPRE primero (I4, review): `asetnsamples=n=...`
    asume que el stream ya está a 48000 Hz para que cada ventana dure
    `ventana_ms` de verdad; sin el resample, un archivo a otra frecuencia
    (44100 Hz es común en voz/música) da ventanas de duración distinta a la
    pedida y picos que no corresponden a nada real."""
    args = [cortes.FFMPEG, "-hide_banner", "-i", ruta, "-af",
            f"aresample=48000,asetnsamples=n={int(48000 * ventana_ms / 1000)},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-",
            "-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True, timeout=300).stdout
    picos = []
    for m in re.finditer(r"Peak_level=(-?[0-9.]+|-inf)", out):
        db_ = m.group(1)
        picos.append(0.0 if db_ == "-inf" else round(min(1.0, max(0.0, 10 ** (float(db_) / 20.0))), 3))
    return picos


@registrar("edicion_proxy")
def ejecutar_proxy(tarea):
    p = tarea["payload"]
    cliente, mid = p["cliente"], int(p["material_id"])
    mat = materiales.obtener(cliente, mid)
    if not mat:
        return gettext("Material inexistente.")
    # Cheap fix (review): el tipo se valida ANTES de bajar nada — un material
    # sin proxy (imagen, png_texto, proxy, tira, forma_onda) no debe ni
    # crear su carpeta de trabajo.
    if mat["tipo"] not in ("video", "audio"):
        return gettext("Sin proxy para este tipo.")
    carpeta = _carpeta(cliente, f"proxy_{mid}")
    try:
        original = materiales.descargar(mat, os.path.join(carpeta, f"orig.{_extension(mat['tipo'])}"))
        extra = dict(mat.get("extra") or {})
        campos = {}
        if mat["tipo"] == "video":
            info = cortes.ffprobe_json(original)
            v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
            dur_s = cortes.duracion(original)
            campos.update(ancho=v.get("width"), alto=v.get("height"), duracion_ms=int(round(dur_s * 1000)))
            extra["tiene_audio"] = mezcla.tiene_audio(original)
            proxy = os.path.join(carpeta, "proxy.mp4")
            generar_proxy(original, proxy)
            tira = os.path.join(carpeta, "tira.jpg")
            # una celda por segundo (fps=1): tantas como segundos tenga el
            # clip, no 60 fijas (que dejaban una tira casi vacía de 9600 px).
            celdas = max(1, int(math.ceil(dur_s)))
            cortes.ffmpeg(["-i", original, "-vf", f"fps=1,scale=160:-2,tile={celdas}x1", "-frames:v", "1", "-q:v", "6", tira], timeout=600)
            campos["url_proxy"] = r2_uploader.upload_file(proxy, f"clientes/{cliente}/materiales/{mid}_proxy.mp4", "video/mp4")
            extra["tira_url"] = r2_uploader.upload_file(tira, f"clientes/{cliente}/materiales/{mid}_tira.jpg", "image/jpeg")
            extra["proxy_version"] = PROXY_VERSION
            if "cortes_ms" not in extra:
                # `insumos.clon` ya los midió al crear el material (I4,
                # plan-mandated capa 2): no repetir el trabajo de `scdet`.
                extra["cortes_ms"] = [int(round(c * 1000)) for c in cortes.detectar_cortes(original)]
        else:  # audio (único otro tipo posible tras el chequeo de arriba)
            campos["duracion_ms"] = int(round(cortes.duracion(original) * 1000))
            extra["picos"] = _picos(original)
        # D5 (capa 5a): `extra` se lee al EMPEZAR y se escribe minutos después
        # (ffmpeg real de por medio) — una transcripción que haya guardado
        # `extra.palabras` mientras tanto nunca debe perderse. `actualizar_extra`
        # mezcla contra el `extra` VIVO en vez de reescribirlo entero.
        materiales.actualizar_extra(cliente, mid, **extra)
        if campos:
            import db
            with db.conectar() as con:
                con.execute(db.material.update().where(db.material.c.id == mid).values(actualizado_en=db.ahora(), **campos))
        return gettext("Proxy listo.")
    finally:
        # A diferencia de edicion_producir, acá no hay una fila "final" que
        # deje en error para depurar — la carpeta de trabajo siempre se
        # limpia, tanto si el proxy salió bien como si no.
        shutil.rmtree(carpeta, ignore_errors=True)


@registrar("material_transcribir")
def ejecutar_transcribir(tarea):
    """Transcribe cada material de `material_ids` que todavía lo necesite
    (D5): un id de otro proyecto o que ya no exista se ignora sin más, y si
    uno falla se sigue con los demás — lo que sí se transcribió (y su gasto)
    no se pierde. Al final, si alguno falló, avisa cuántos."""
    p = tarea["payload"]
    cliente, edicion_id, idioma = p["cliente"], p["edicion_id"], p["idioma"]
    jid = tarea.get("job_id") or job_id_transcribir(cliente, edicion_id)
    avisar = lambda n: trabajos.reportar(jid, etapa=n)
    carpeta = _carpeta(cliente, f"transcribir_{edicion_id}")
    avisar(ETAPAS_TRANSCRIBIR[0][0])
    fallos = 0
    try:
        for mid in p.get("material_ids") or []:
            mat = materiales.obtener(cliente, mid)
            if not mat or not transcripcion.necesita(mat):
                continue
            avisar(ETAPAS_TRANSCRIBIR[1][0])
            ref = f"transcripcion:{mid}{ref_sufijo(tarea)}"
            try:
                transcripcion.transcribir(cliente, mat, idioma, carpeta, ref)
            except Exception:  # noqa: BLE001 — sigue con los demás; el gasto de este ya quedó si alcanzó a pagar
                log.exception("material_transcribir (tarea %s): material %s falló", tarea.get("id"), mid)
                fallos += 1
        avisar(ETAPAS_TRANSCRIBIR[2][0])
        if fallos:
            raise RuntimeError(ngettext("No se pudo transcribir %(num)s archivo.",
                                        "No se pudieron transcribir %(num)s archivos.", fallos))
        # Babel 2.18 no extrae bien un gettext(dict[clave]) (confunde el `[`
        # con el paréntesis de la llamada y «ve» la clave como mensaje) — se
        # saca a una variable antes, como ya hace el resto del código con
        # ngettext(gettext(...)).
        mensaje = MENSAJES_AUDIO_EDITOR["subtitulos_listos"]
        return gettext(mensaje)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


@registrar("materiales_limpiar")
def ejecutar_limpiar(tarea):
    n = materiales.limpiar_sin_uso(dias=30)
    return gettext("%(n)s materiales efímeros borrados.", n=n)


@registrar("edicion_desde_clon")
def ejecutar_desde_clon(tarea):
    """«Editar este video»: baja y mide el clon y crea la edición (gratis).
    `cf_id` forma el nombre de la carpeta: se valida antes de tocar el disco."""
    from final_edition import edicion_clon
    p = tarea["payload"]
    if not isinstance(p.get("cf_id"), str) or not _CF_RE.fullmatch(p["cf_id"]):
        raise ValueError(gettext("cf_id inválido: %(cf)s", cf=repr(p.get("cf_id"))))
    eid = edicion_clon.crear(p["cliente"], p["cf_id"], _carpeta(p["cliente"], f"clon_{p['cf_id']}"))
    return gettext("Edición %(id)s lista para editar.", id=eid)


@registrar("material_de_pieza")
def ejecutar_material_de_pieza(tarea):
    """Biblioteca del editor (capa 4b, Task 1): materializa una pieza de
    Crear como `material` (gratis) para que se pueda arrastrar al lienzo —
    la misma preparación que `edicion_desde_clon` hace con el clon
    (`biblioteca.materializar_pieza` reusa `insumos.clon`), sin crear
    ninguna edición. `cf_id` forma el nombre de la carpeta: se valida antes
    de tocar el disco."""
    from final_edition import biblioteca
    p = tarea["payload"]
    if not isinstance(p.get("cf_id"), str) or not _CF_RE.fullmatch(p["cf_id"]):
        raise ValueError(gettext("cf_id inválido: %(cf)s", cf=repr(p.get("cf_id"))))
    mat = biblioteca.materializar_pieza(p["cliente"], p["cf_id"], _carpeta(p["cliente"], f"material_{p['cf_id']}"))
    return gettext("Material %(id)s listo.", id=mat["id"])
