"""Ejecución del plan con ffmpeg (spec §2.1 punto 6 y §2.2): un proceso por
tramo, filtergraph a archivo (`-/filter_complex`), validación con ffprobe y
miniatura. `tiene_libass()` decide si los subtítulos van por ASS (VPS) o se
omiten (máquinas sin libass, como la Mac de desarrollo)."""
import functools
import os
import subprocess

from final_edition import cortes

OPCIONES_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
OPCIONES_AUDIO = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
TOLERANCIA_S = 0.2


@functools.lru_cache(maxsize=1)
def tiene_libass():
    try:
        out = subprocess.run([cortes.FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return False
    return any(l.split()[1:2] == ["subtitles"] for l in out.splitlines() if l.strip())


def _escribir_filtergraph(plan, salida):
    ruta = salida + ".filtergraph.txt"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(plan.filtergraph)
    return ruta


def ejecutar(plan, salida, ass_ruta=None, timeout=None):
    if plan.ass_texto and ass_ruta:
        from final_edition.motor import subtitulos
        subtitulos.escribir_ass(plan.ass_texto, ass_ruta)
    args = []
    for e in plan.entradas:
        args += list(e.get("opciones") or []) + ["-i", e["ruta"]]
    fg = _escribir_filtergraph(plan, salida)
    args += ["-/filter_complex", fg, "-map", "[vout]"]
    es_imagen = plan.duracion_ms == 0
    if es_imagen:
        args += ["-frames:v", "1", salida]
        t = 120
    else:
        args += ["-r", "30"] + OPCIONES_VIDEO
        if plan.salida_audio:
            args += ["-map", "[aout]"] + OPCIONES_AUDIO
        args += ["-t", f"{plan.duracion_ms / 1000.0:.3f}", salida]
        t = timeout or max(600, int(plan.duracion_ms / 1000.0 * 40))
    cortes.ffmpeg(args, timeout=t)
    if os.path.exists(fg):
        os.remove(fg)
    return salida


def concatenar(rutas_tramos, salida):
    lista = salida + ".tramos.txt"
    with open(lista, "w", encoding="utf-8") as f:
        for ruta in rutas_tramos:
            f.write(f"file '{ruta}'\n")
    cortes.ffmpeg(["-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", "-movflags", "+faststart", salida], timeout=600)
    os.remove(lista)
    return salida


def validar(salida, plan, tolerancia_s=TOLERANCIA_S):
    info = cortes.ffprobe_json(salida)
    streams = {s.get("codec_type"): s for s in info.get("streams") or []}
    video = streams.get("video")
    if not video:
        raise RuntimeError(f"render: {os.path.basename(salida)} no tiene stream de video")
    if (video.get("width"), video.get("height")) != (plan.ancho, plan.alto):
        raise RuntimeError(f"render: tamaño {video.get('width')}x{video.get('height')}, esperado {plan.ancho}x{plan.alto}")
    if plan.duracion_ms > 0:
        dur = float((info.get("format") or {}).get("duration") or 0)
        if abs(dur - plan.duracion_ms / 1000.0) > tolerancia_s:
            raise RuntimeError(f"render: duración {dur:.2f}s, esperada {plan.duracion_ms / 1000.0:.2f}s")
        if bool(streams.get("audio")) != bool(plan.salida_audio):
            raise RuntimeError("render: la salida no coincide en audio con el plan")
        return dur
    return 0.0


def miniatura(video, salida_png, t_ms):
    cortes.ffmpeg(["-ss", f"{max(0, t_ms) / 1000.0:.3f}", "-i", video, "-frames:v", "1", salida_png], timeout=120)
    return salida_png
