"""Insumos del borrador (spec §1 «Material», §2.3 «caché»): lo que el
pipeline de final edition dejaba en una carpeta de trabajo pasa a ser un
`material` del proyecto con caché por hash — se produce una vez y se
reutiliza siempre. Solo materiales: el documento lo arma `borrador.py` y el
flujo lo decide `produccion.py`.

- clon: el video crudo de Crear, con la URL que YA tiene en R2 (no se
  vuelve a subir); `extra.local` para que `materiales.descargar` copie el
  archivo en vez de bajarlo; `extra.cortes_ms` y `extra.tiene_audio` se
  miden una sola vez.
- voz por bloque: hash(texto_voz, voz, idioma) → mp3 crudo de ElevenLabs
  (lo que cuesta). Si no cabe en la ventana del bloque se acelera hasta
  1.35× y se recorta a ventana + 0.4 s (como voz._sintetizar_bloque) en un
  material DERIVADO (`padre_id`, gratis). Las palabras de Whisper quedan en
  `extra.palabras` (ms relativos al inicio del audio) del material que
  suena — se transcribe una sola vez.
- música: la pista de `musica.obtener_pista` (caché global data/musica +
  R2 `musica/<estilo>_<seg>.wav`) registrada como material del proyecto.
- logo: el primer logo de clientes/<c>/logos/ subido a materiales/.

Las carpetas de trabajo no se borran: `extra.local` ahorra la descarga al
renderizar y salidas/ es efímero por diseño."""
import os

import requests
from PIL import Image

import final_edition
import materiales
import trabajos
from final_edition import cortes, mezcla, musica as musica_mod
from providers import fal_audio
from storage import r2_uploader

FACTOR_MAX = 1.35        # aceleración máxima (voz.FACTOR_MAX)
SOLAPE_MAX_MS = 400      # invasión máxima del bloque siguiente (voz.SOLAPE_MAX_S)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def ms(segundos):
    return int(round(float(segundos) * 1000))


def job_id_proxy(cliente, material_id):
    # Mismo formato que tareas.edicion.job_id_proxy (no se importa `tareas`
    # desde final_edition: la dependencia va al revés). test_fe_insumos los
    # compara.
    return f"{cliente}__mat{int(material_id)}__proxy"


def _descargar(url, destino):
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for trozo in resp.iter_content(chunk_size=65536):
            if trozo:
                f.write(trozo)
    return destino


def clon(cliente, cf_id, entry, ruta_local):
    """(material, creado) del clon crudo. Encola `edicion_proxy` (gratis,
    max_intentos=3, prioridad 1: la capa 3 necesita los proxies para que el
    editor abra al instante las finales existentes, pero sin adelantarse
    nunca a un lote de Sprints (3) ni a una pieza suelta de Crear (5)) si el
    material aún no tiene proxy."""
    url = entry.get("video_url_crudo") or entry.get("video_url")
    if not url:
        raise ValueError(f"La sesión {cf_id} no tiene video listo para producir.")
    h = materiales.hash_archivo(ruta_local)

    def _medir():
        info = cortes.ffprobe_json(ruta_local)
        v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
        return {"tipo": "video", "origen": "crear", "url": url, "bytes": os.path.getsize(ruta_local),
                "duracion_ms": ms(cortes.duracion(ruta_local)), "ancho": v.get("width"), "alto": v.get("height"),
                "extra": {"cf_id": cf_id, "local": ruta_local, "tiene_audio": mezcla.tiene_audio(ruta_local),
                          "cortes_ms": [ms(t) for t in cortes.detectar_cortes(ruta_local)]}}
    mat, creado = materiales.obtener_o_crear(cliente, h, _medir)
    extra = mat.get("extra") or {}
    if extra.get("local") != ruta_local or "tiene_audio" not in extra or "cortes_ms" not in extra:
        # El mismo archivo pudo entrar por otra vía (una subida del editor):
        # completar lo que el borrador necesita sin volver a medir lo medido.
        mat = materiales.actualizar_extra(
            cliente, mat["id"], local=ruta_local,
            tiene_audio=extra["tiene_audio"] if "tiene_audio" in extra else mezcla.tiene_audio(ruta_local),
            cortes_ms=extra["cortes_ms"] if "cortes_ms" in extra else [ms(t) for t in cortes.detectar_cortes(ruta_local)])
    if not mat.get("url_proxy"):
        # Prioridad 1 (mínima, decisión 4 capa 2): nunca por delante de un lote
        # de Sprints (3) ni de una pieza suelta de Crear (5) — el proxy es
        # gratis y puede esperar a lo que ya se está pagando.
        trabajos.encolar(job_id_proxy(cliente, mat["id"]), "edicion_proxy", {"cliente": cliente, "material_id": mat["id"]},
                         cliente=cliente, duracion_estimada=120, max_intentos=3, prioridad=1)
    return mat, creado


def logo(cliente):
    """Primer logo de clientes/<c>/logos/ (misma convención que
    final_edition._logo_local) como material `imagen`/`marca` con
    ancho/alto, o None si no hay."""
    origen = os.path.join(final_edition.BASE_DIR, "clientes", cliente, "logos")
    if not os.path.isdir(origen):
        return None
    for nombre in sorted(os.listdir(origen)):
        low = nombre.lower()
        if low.endswith(".frame.jpg") or not low.endswith(IMAGE_EXTS):
            continue
        ruta = os.path.join(origen, nombre)
        ext = os.path.splitext(low)[1]
        try:
            with Image.open(ruta) as im:
                ancho, alto = im.size
        except OSError:
            continue
        h = materiales.hash_archivo(ruta)
        return materiales.subir(cliente, ruta, f"clientes/{cliente}/materiales/logo_{h[:16]}{ext}", _MIME[ext],
                                tipo="imagen", origen="marca", ancho=ancho, alto=alto, extra={"nombre": nombre})
    return None


def musica(cliente, estilo, segundos):
    """(material, costo_usd_nuevo): la pista cacheada de
    `musica.obtener_pista` como material `audio`/`musica` del proyecto. La
    URL es la de la caché global en R2 (`musica/...`): no se resube."""
    pista, costo = musica_mod.obtener_pista(estilo, segundos)
    h = materiales.hash_clave("musica", estilo, os.path.basename(pista["archivo"]))

    def _registrar():
        return {"tipo": "audio", "origen": "musica", "url": pista["url"], "bytes": os.path.getsize(pista["archivo"]),
                "duracion_ms": ms(cortes.duracion(pista["archivo"])), "costo_usd": float(costo or 0.0),
                "extra": {"estilo": estilo, "local": pista["archivo"]}}
    mat, _ = materiales.obtener_o_crear(cliente, h, _registrar)
    return mat, round(float(costo or 0.0), 4)


def voz_bloque(cliente, texto_voz, voz, idioma, ventana_ms, carpeta):
    """(material, costo_usd_nuevo) de la locución de un bloque, lista para
    sonar en `ventana_ms`: la cruda si cabe; si no, un material derivado
    acelerado (≤ 1.35×) y recortado a ventana + 400 ms. `extra.palabras`
    siempre presente al volver (Whisper una sola vez por material)."""
    if not (texto_voz or "").strip():
        raise ValueError("voz_bloque: el bloque no tiene texto de voz.")
    os.makedirs(carpeta, exist_ok=True)
    h = materiales.hash_clave("voz", texto_voz, voz, idioma)

    def _tts():
        r = fal_audio.tts(texto_voz, voz, idioma)
        local = _descargar(r["url"], os.path.join(carpeta, f"voz_{h[:16]}.mp3"))
        url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": "voz", "url": url, "bytes": os.path.getsize(local),
                "duracion_ms": ms(cortes.duracion(local)), "costo_usd": float(r.get("costo_usd") or 0.0),
                "extra": {"texto": texto_voz, "voz": voz, "idioma": idioma, "local": local}}
    cruda, creada = materiales.obtener_o_crear(cliente, h, _tts)
    costo = float(cruda.get("costo_usd") or 0.0) if creada else 0.0

    dur = int(cruda["duracion_ms"] or 0)
    ventana_ms = max(1, int(ventana_ms))
    factor = min(FACTOR_MAX, dur / ventana_ms) if dur > ventana_ms else 1.0
    tope = ventana_ms + SOLAPE_MAX_MS
    recortado = factor > 1.0 and dur / factor > tope
    mat = cruda
    if factor > 1.0:
        h2 = materiales.hash_clave("voz_ajustada", cruda["id"], f"{factor:.4f}", tope if recortado else 0)

        def _ajustar():
            crudo_local = materiales.descargar(cruda, os.path.join(carpeta, f"voz_{h[:16]}_crudo.mp3"))
            local = os.path.join(carpeta, f"voz_{h2[:16]}.mp3")
            args = ["-i", crudo_local, "-filter:a", f"atempo={factor:.4f}"]
            if recortado:
                args += ["-t", f"{tope / 1000.0:.3f}"]
            cortes.ffmpeg(args + [local], timeout=120)
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h2[:16]}.mp3", "audio/mpeg")
            return {"tipo": "audio", "origen": "voz", "url": url, "bytes": os.path.getsize(local),
                    "duracion_ms": ms(cortes.duracion(local)), "padre_id": cruda["id"],
                    "extra": {"texto": texto_voz, "voz": voz, "idioma": idioma, "factor": round(factor, 3),
                              "recortado": recortado, "local": local}}
        mat, _ = materiales.obtener_o_crear(cliente, h2, _ajustar)

    if "palabras" not in (mat.get("extra") or {}):
        t = fal_audio.transcribir_palabras(mat["url"], idioma)
        palabras = []
        for p in t.get("palabras") or []:
            ini = ms(p.get("inicio") or 0.0)
            fin = max(ini, ms(p.get("fin") or 0.0))
            palabras.append({"t_ms": ini, "dur_ms": fin - ini, "texto": p.get("texto", "")})
        mat = materiales.actualizar_extra(cliente, mat["id"], palabras=palabras)
        costo += float(t.get("costo_usd") or 0.0)
    return mat, round(costo, 4)
