"""Tareas del worker para el editor (spec §2.4):
  edicion_producir  {cliente, edicion_id, version_id, final_id, idioma, pais}  max_intentos=1
  edicion_proxy     {cliente, material_id}                                     max_intentos=3
  materiales_limpiar {}                                                         periódica diaria
`edicion_producir` renderiza el documento CONGELADO en la versión (no el
vivo), así lo que se produjo siempre se puede volver a ver. Contrato con la
ruta que la encola (capa 3): `ediciones.versionar` → `creative_flow.crear_final`
(la fila final DEBE existir: si `actualizar_final`/`apuntar_final` no la
encuentran, la tarea falla y lo dice) → `trabajos.encolar(..., max_intentos=1,
duracion_estimada=estimar.segundos(doc), etapas=ETAPAS_EDICION)`. `idioma` y
`pais` se validan con forma (`[a-z]{2}` / `[A-Z]{2}`) antes de tocar el disco
porque forman parte del nombre de la carpeta de trabajo."""
import math
import os
import re
import shutil
import subprocess

import cola
import creative_flow
import ediciones
import materiales
import trabajos
from final_edition import cortes, motor
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from storage import r2_uploader
from tareas import al_interrumpir, registrar

ETAPAS_EDICION = (("Preparando materiales", 15), ("Renderizando", 70), ("Subiendo", 15))
_EXT = {"video": "mp4", "imagen": "png", "audio": "wav", "png_texto": "png", "proxy": "mp4"}
_IDIOMA_RE = re.compile(r"[a-z]{2}")
_PAIS_RE = re.compile(r"[A-Z]{2}")


def _extension(tipo):
    ext = _EXT.get(tipo)
    if not ext:
        raise RuntimeError(f"Tipo de material sin extensión conocida: {tipo}")
    return ext


def job_id_producir(cliente, edicion_id, idioma, pais):
    return f"{cliente}__ed{int(edicion_id)}__{idioma}_{pais}__producir"


def job_id_proxy(cliente, material_id):
    return f"{cliente}__mat{int(material_id)}__proxy"


def _carpeta(cliente, nombre):
    raiz = os.environ.get("CREATV_SALIDAS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "salidas")
    c = os.path.join(raiz, cliente, "ediciones", nombre)
    os.makedirs(c, exist_ok=True)
    return c


def preparar_rutas(cliente, doc, carpeta):
    """Baja los materiales del documento a `carpeta` y devuelve `rutas`
    ({material_id: ruta, "png:<clip_id>": ruta, "ass": ruta}). De paso, con
    las filas ya en mano: estampa `ancho_px`/`alto_px` en los clips `imagen`
    que no los traen (tamaño natural medido al subir) y pasa los recortes por
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
            raise RuntimeError(f"Falta el material {mid} de este proyecto.")
        filas[mid] = mat
        destino = os.path.join(carpeta, f"{mid}.{_extension(mat['tipo'])}")
        rutas[mid] = materiales.descargar(mat, destino)
    for clip_id, mid in (doc.get("pngs") or {}).items():
        mat = materiales.obtener(cliente, mid)
        if mat:
            rutas[f"png:{clip_id}"] = materiales.descargar(mat, os.path.join(carpeta, f"png_{clip_id}.png"))
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


@registrar("edicion_producir")
def ejecutar_producir(tarea):
    p = tarea["payload"]
    cliente, final_id = p["cliente"], p["final_id"]
    job_id = tarea.get("job_id") or job_id_producir(cliente, p["edicion_id"], p["idioma"], p["pais"])
    avisar = lambda n: trabajos.reportar(job_id, etapa=n)
    # Sin gasto: los materiales ya existen; la capa 2 registra voz/música nuevas.
    try:
        # idioma/pais forman el nombre de la carpeta de trabajo: se validan
        # ANTES de crearla (un `../x` no debe ni tocar el disco).
        if not isinstance(p.get("idioma"), str) or not _IDIOMA_RE.fullmatch(p["idioma"]):
            raise ValueError(f"idioma inválido: {p.get('idioma')!r} (se esperan dos letras minúsculas).")
        if not isinstance(p.get("pais"), str) or not _PAIS_RE.fullmatch(p["pais"]):
            raise ValueError(f"país inválido: {p.get('pais')!r} (se esperan dos letras mayúsculas).")
        carpeta = _carpeta(cliente, f"{p['edicion_id']}_{p['idioma']}_{p['pais']}")
        # Como en final_edition/__init__.py: como mucho una corrida fallida
        # por destino queda en disco — un reintento siempre arranca de
        # carpeta limpia (_carpeta ya hizo su propio os.makedirs; lo
        # repetimos después del rmtree para dejarla vacía pero existente).
        shutil.rmtree(carpeta, ignore_errors=True)
        os.makedirs(carpeta, exist_ok=True)
        avisar(ETAPAS_EDICION[0][0])
        v = ediciones.version(cliente, p["version_id"])
        if not v:
            raise RuntimeError("No existe esa versión de la edición.")
        doc = documento_mod.resolver(documento_mod.validar(documento_mod.migrar(v["documento"])), p["idioma"], p["pais"])
        rutas = preparar_rutas(cliente, doc, carpeta)
        avisar(ETAPAS_EDICION[1][0])
        es_imagen = documento_mod.duracion_ms(doc) == 0
        salida = os.path.join(carpeta, f"{final_id}.{'png' if es_imagen else 'mp4'}")
        res = motor.renderizar(doc, rutas, salida, on_etapa=avisar, nucleos=int(os.environ.get("RENDER_NUCLEOS", "1")))
        avisar(ETAPAS_EDICION[2][0])
        # I1 (review): claves versionadas por edicion_version_id — un
        # reintento (misma final, versión nueva) nunca pisa el archivo que la
        # fila todavía enlaza mientras se sube el nuevo. La miniatura sube
        # ANTES que el video para que, si el proceso muere entre ambas
        # subidas, nunca quede un video sin su miniatura.
        if es_imagen:
            url = r2_uploader.upload_image(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
            url_mini = url
        else:
            url_mini = r2_uploader.upload_image(res["miniatura"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
            url = r2_uploader.upload_video(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.mp4")
        # La fila final la crea la ruta (creative_flow.crear_final) antes de
        # encolar: si no está, esto no puede "terminar bien" en silencio.
        if not creative_flow.actualizar_final(cliente, final_id, estado="listo", url_video=url, url_miniatura=url_mini,
                                              duracion_s=res["duracion_s"],
                                              capas={"render": {"edicion_version_id": v["id"], "tramos": res["tramos"], "con_ass": res["con_ass"]}}):
            raise RuntimeError(f"La final {final_id} no existe; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
        if not ediciones.apuntar_final(cliente, final_id, v["id"]):
            raise RuntimeError(f"La final {final_id} no existe en pieza; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
        shutil.rmtree(carpeta, ignore_errors=True)
        return f"Final {p['idioma']}/{p['pais']} lista."
    except Exception as e:
        # I3 (review): nunca un token crudo en la columna de error (Meta/
        # TikTok los meten en mensajes de excepción reales). Aquí sí es
        # best-effort: si la final no existe no hay dónde anotarlo.
        creative_flow.actualizar_final(cliente, final_id, estado="error",
                                       error=cola.recortar(cola.sin_token(str(e)), 500))
        raise  # la carpeta queda: el .filtergraph.txt es la evidencia para depurar.


@al_interrumpir("edicion_producir")
def _interrumpido(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("final_id"):
        error = f"interrumpido: {cola.recortar(cola.sin_token(str(mensaje)), 500)}"
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
        return "Material inexistente."
    # Cheap fix (review): el tipo se valida ANTES de bajar nada — un material
    # sin proxy (imagen, png_texto, proxy, tira, forma_onda) no debe ni
    # crear su carpeta de trabajo.
    if mat["tipo"] not in ("video", "audio"):
        return "Sin proxy para este tipo."
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
            proxy = os.path.join(carpeta, "proxy.mp4")
            cortes.ffmpeg(["-i", original, "-vf", "scale=-2:540", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1M",
                           "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", proxy], timeout=900)
            tira = os.path.join(carpeta, "tira.jpg")
            # una celda por segundo (fps=1): tantas como segundos tenga el
            # clip, no 60 fijas (que dejaban una tira casi vacía de 9600 px).
            celdas = max(1, int(math.ceil(dur_s)))
            cortes.ffmpeg(["-i", original, "-vf", f"fps=1,scale=160:-2,tile={celdas}x1", "-frames:v", "1", "-q:v", "6", tira], timeout=600)
            campos["url_proxy"] = r2_uploader.upload_file(proxy, f"clientes/{cliente}/materiales/{mid}_proxy.mp4", "video/mp4")
            extra["tira_url"] = r2_uploader.upload_file(tira, f"clientes/{cliente}/materiales/{mid}_tira.jpg", "image/jpeg")
            extra["cortes_ms"] = [int(round(c * 1000)) for c in cortes.detectar_cortes(original)]
        else:  # audio (único otro tipo posible tras el chequeo de arriba)
            campos["duracion_ms"] = int(round(cortes.duracion(original) * 1000))
            extra["picos"] = _picos(original)
        import db
        with db.conectar() as con:
            con.execute(db.material.update().where(db.material.c.id == mid).values(extra=extra, actualizado_en=db.ahora(), **campos))
        return "Proxy listo."
    finally:
        # A diferencia de edicion_producir, acá no hay una fila "final" que
        # deje en error para depurar — la carpeta de trabajo siempre se
        # limpia, tanto si el proxy salió bien como si no.
        shutil.rmtree(carpeta, ignore_errors=True)


@registrar("materiales_limpiar")
def ejecutar_limpiar(tarea):
    n = materiales.limpiar_sin_uso(dias=30)
    return f"{n} materiales efímeros borrados."
