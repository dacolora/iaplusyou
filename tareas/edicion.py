"""Tareas del worker para el editor (spec §2.4):
  edicion_producir  {cliente, edicion_id, version_id, final_id, idioma, pais}  max_intentos=1
  edicion_proxy     {cliente, material_id}                                     max_intentos=3
  materiales_limpiar {}                                                         periódica diaria
`edicion_producir` renderiza el documento CONGELADO en la versión (no el
vivo), así lo que se produjo siempre se puede volver a ver."""
import os
import re
import subprocess

import creative_flow
import ediciones
import materiales
import trabajos
from final_edition import cortes, motor
from final_edition import documento as documento_mod
from storage import r2_uploader
from tareas import al_interrumpir, registrar

ETAPAS_EDICION = (("Preparando materiales", 15), ("Renderizando", 70), ("Subiendo", 15))
_EXT = {"video": "mp4", "imagen": "png", "audio": "wav", "png_texto": "png", "proxy": "mp4"}


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
    rutas = {"ass": os.path.join(carpeta, "subtitulos.ass")}
    ids = set(int(x) for x in doc.get("materiales") or [])
    for p in doc.get("pistas") or []:
        for cl in p.get("clips") or []:
            if cl.get("material_id"):
                ids.add(int(cl["material_id"]))
    for mid in sorted(ids):
        mat = materiales.obtener(cliente, mid)
        if not mat:
            raise RuntimeError(f"Falta el material {mid} de este proyecto.")
        destino = os.path.join(carpeta, f"{mid}.{_EXT.get(mat['tipo'], 'bin')}")
        rutas[mid] = materiales.descargar(mat, destino)
    for clip_id, mid in (doc.get("pngs") or {}).items():
        mat = materiales.obtener(cliente, mid)
        if mat:
            rutas[f"png:{clip_id}"] = materiales.descargar(mat, os.path.join(carpeta, f"png_{clip_id}.png"))
    return rutas


@registrar("edicion_producir")
def ejecutar_producir(tarea):
    p = tarea["payload"]
    cliente, final_id = p["cliente"], p["final_id"]
    job_id = tarea.get("job_id") or job_id_producir(cliente, p["edicion_id"], p["idioma"], p["pais"])
    avisar = lambda n: trabajos.reportar(job_id, etapa=n)
    # Sin gasto: los materiales ya existen; la capa 2 registra voz/música nuevas.
    try:
        avisar(ETAPAS_EDICION[0][0])
        v = ediciones.version(cliente, p["version_id"])
        if not v:
            raise RuntimeError("No existe esa versión de la edición.")
        doc = documento_mod.resolver(documento_mod.validar(documento_mod.migrar(v["documento"])), p["idioma"], p["pais"])
        carpeta = _carpeta(cliente, f"{p['edicion_id']}_{p['idioma']}_{p['pais']}")
        rutas = preparar_rutas(cliente, doc, carpeta)
        avisar(ETAPAS_EDICION[1][0])
        es_imagen = documento_mod.duracion_ms(doc) == 0
        salida = os.path.join(carpeta, f"{final_id}.{'png' if es_imagen else 'mp4'}")
        res = motor.renderizar(doc, rutas, salida, on_etapa=avisar, nucleos=int(os.environ.get("RENDER_NUCLEOS", "1")))
        avisar(ETAPAS_EDICION[2][0])
        if es_imagen:
            url = r2_uploader.upload_image(res["archivo"], f"clientes/{cliente}/finales/{final_id}.png")
            url_mini = url
        else:
            url = r2_uploader.upload_video(res["archivo"], f"clientes/{cliente}/finales/{final_id}.mp4")
            url_mini = r2_uploader.upload_image(res["miniatura"], f"clientes/{cliente}/finales/{final_id}.png")
        creative_flow.actualizar_final(cliente, final_id, estado="listo", url_video=url, url_miniatura=url_mini,
                                       duracion_s=res["duracion_s"],
                                       capas={"render": {"edicion_version_id": v["id"], "tramos": res["tramos"], "con_ass": res["con_ass"]}})
        ediciones.apuntar_final(cliente, final_id, v["id"])
        return f"Final {p['idioma']}/{p['pais']} lista."
    except Exception as e:
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=cortes_recortar(str(e)))
        raise


def cortes_recortar(texto, n=500):
    return re.sub(r"\s+", " ", texto)[:n]


@al_interrumpir("edicion_producir")
def _interrumpido(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("final_id"):
        creative_flow.actualizar_final(p["cliente"], p["final_id"], estado="error", error=f"interrumpido: {mensaje}")


def _picos(ruta, ventana_ms=50):
    """Envolvente de energía por ventanas con `astats` (sin numpy)."""
    args = [cortes.FFMPEG, "-hide_banner", "-i", ruta, "-af",
            f"asetnsamples=n={int(48000 * ventana_ms / 1000)},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-",
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
    carpeta = _carpeta(cliente, f"proxy_{mid}")
    original = materiales.descargar(mat, os.path.join(carpeta, f"orig.{_EXT.get(mat['tipo'], 'bin')}"))
    extra = dict(mat.get("extra") or {})
    campos = {}
    if mat["tipo"] == "video":
        info = cortes.ffprobe_json(original)
        v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
        campos.update(ancho=v.get("width"), alto=v.get("height"), duracion_ms=int(round(cortes.duracion(original) * 1000)))
        proxy = os.path.join(carpeta, "proxy.mp4")
        cortes.ffmpeg(["-i", original, "-vf", "scale=-2:540", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1M",
                       "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", proxy], timeout=900)
        tira = os.path.join(carpeta, "tira.jpg")
        cortes.ffmpeg(["-i", original, "-vf", "fps=1,scale=160:-2,tile=60x1", "-frames:v", "1", "-q:v", "6", tira], timeout=600)
        campos["url_proxy"] = r2_uploader.upload_file(proxy, f"clientes/{cliente}/materiales/{mid}_proxy.mp4", "video/mp4")
        extra["tira_url"] = r2_uploader.upload_file(tira, f"clientes/{cliente}/materiales/{mid}_tira.jpg", "image/jpeg")
        extra["cortes_ms"] = [int(round(c * 1000)) for c in cortes.detectar_cortes(original)]
    elif mat["tipo"] == "audio":
        campos["duracion_ms"] = int(round(cortes.duracion(original) * 1000))
        extra["picos"] = _picos(original)
    else:
        return "Sin proxy para este tipo."
    import db, sqlalchemy as sa
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id == mid).values(extra=extra, actualizado_en=db.ahora(), **campos))
    return "Proxy listo."


@registrar("materiales_limpiar")
def ejecutar_limpiar(tarea):
    n = materiales.limpiar_sin_uso(dias=30)
    return f"{n} materiales efímeros borrados."
