"""Transcripción automática para subtítulos del editor (capa 5a, spec D5): se
paga una vez por material y el resultado queda cacheado en
`material.extra.palabras` (`[{t_ms, dur_ms, texto}]`, tiempo del MATERIAL —
no de ninguna línea de tiempo de la edición: eso lo deriva
`subtitulos_fuente.aplicar` al resolver cada destino).

- Audio: Whisper recibe `mat["url"]` tal cual.
- Video: Whisper nunca recibe el video entero — se baja el original (o se
  copia `extra.local`), se extrae una pista mono de 16 kHz con ffmpeg, se
  sube a una clave TEMPORAL de R2 (`clientes/<c>/materiales/stt_<id>.mp3`) y
  esa clave se borra al terminar, salga bien o mal (un fallo al borrar se
  anota y no tumba la transcripción: el archivo es chico).

El gasto se registra en cuanto fal cobró — ANTES de guardar nada — para que
un fallo posterior (al bajar el video, al subir, al guardar `extra`) nunca
pierda lo que ya se pagó."""
import logging
import os

from flask_babel import gettext

import gastos
import materiales
from final_edition import cortes
from providers import fal_audio
from storage import r2_uploader

log = logging.getLogger(__name__)

# Tope de audio por pedido (10 min, spec §2.4) y de archivos por pedido (la
# ruta `editor.transcribir` los aplica antes de encolar nada).
LIMITE_MS = 600000
MAX_ARCHIVOS = 20


def necesita(mat):
    """Un video o audio sin `extra.palabras` todavía (D5): una transcripción
    vacía (`[]`) ya cuenta como hecha. Un video sin pista de audio
    (`extra.tiene_audio is False`, lo mide `edicion_proxy`) nunca la
    necesita — Whisper no tiene nada que escuchar. Cualquier otro tipo
    (imagen, png_texto…) tampoco."""
    if not mat or mat.get("tipo") not in ("video", "audio"):
        return False
    extra = mat.get("extra") or {}
    if mat["tipo"] == "video" and extra.get("tiene_audio") is False:
        return False
    return not isinstance(extra.get("palabras"), list)


def a_ms(palabras_whisper):
    """[{"inicio", "fin", "texto"}] (segundos, de `fal_audio.transcribir_palabras`)
    -> [{t_ms, dur_ms, texto}] (ms enteros, `dur_ms` nunca negativo, texto
    recortado de espacios)."""
    salida = []
    for p in palabras_whisper or []:
        ini = int(round(float(p.get("inicio") or 0.0) * 1000))
        fin = int(round(float(p.get("fin") or 0.0) * 1000))
        fin = max(ini, fin)
        salida.append({"t_ms": ini, "dur_ms": fin - ini, "texto": (p.get("texto") or "").strip()})
    return salida


def _clave_audio_temporal(cliente, material_id):
    clave = f"clientes/{cliente}/materiales/stt_{material_id}.mp3"
    return clave


def _audio_de_video(cliente, mat, carpeta):
    """Baja (o copia) el video, extrae su audio a mono/16 kHz y lo sube a una
    clave temporal de R2. Devuelve (url, clave) — la clave la borra quien
    llama, en un `finally`."""
    original = materiales.descargar(mat, os.path.join(carpeta, f"{mat['id']}.mp4"))
    audio_local = os.path.join(carpeta, f"{mat['id']}.mp3")
    cortes.ffmpeg(["-i", original, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", audio_local])
    clave = _clave_audio_temporal(cliente, mat["id"])
    url = r2_uploader.upload_file(audio_local, clave, "audio/mpeg")
    return url, clave


def transcribir(cliente, mat, idioma, carpeta, referencia):
    """Transcribe `mat` (video o audio de ESTE proyecto) con Whisper. Registra
    el gasto (`costo_whisper` sobre `mat["duracion_ms"]`, la misma fórmula del
    botón) apenas fal cobró, y solo DESPUÉS guarda `extra.palabras` — si ese
    guardado revienta, el gasto ya quedó. Devuelve la fila de material
    actualizada."""
    os.makedirs(carpeta, exist_ok=True)
    clave_temporal = None
    try:
        if mat["tipo"] == "audio":
            url = mat["url"]
        else:
            url, clave_temporal = _audio_de_video(cliente, mat, carpeta)
        duracion_ms = int(mat.get("duracion_ms") or 0)
        # la espera crece con el audio (10 min no caben en 180 s con la cola de fal)
        r = fal_audio.transcribir_palabras(url, idioma, duracion_ms=duracion_ms or None)
        palabras = a_ms(r.get("palabras"))
        usd = fal_audio.costo_whisper(duracion_ms)
        gastos.registrar_seguro(cliente, "transcripcion", usd, referencia,
                                detalle=gettext("Whisper · %(s)s s de audio", s=round(duracion_ms / 1000.0, 1)),
                                proveedor="fal/whisper")
        return materiales.actualizar_extra(cliente, mat["id"], palabras=palabras,
                                           palabras_idioma=idioma, palabras_fuente="whisper")
    finally:
        if clave_temporal:
            try:
                r2_uploader.delete_file(clave_temporal)
            except Exception:  # noqa: BLE001 — el archivo es chico; un fallo al borrar no debe tumbar la transcripción
                log.warning("No se pudo borrar el audio temporal %s", clave_temporal, exc_info=True)
