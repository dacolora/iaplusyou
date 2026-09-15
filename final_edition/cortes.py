"""Final Edition, capa 1: detección de cortes de escena con ffmpeg (`scdet`) y
plan de segmentos del video final. Si el clip fuente tiene cortes naturales se
respetan; si no, se fabrican 3–4 segmentos iguales con zoom alternado (ken
burns) para que el montaje tenga ritmo. También expone los helpers comunes
`ffmpeg`/`ffprobe_json`/`duracion` que usan las capas siguientes.
"""
import json
import os
import re
import subprocess

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

# Cortes a menos de esto de los extremos del clip se ignoran (ruido del inicio/fin).
_BORDE_S = 0.3

# Lo que imprime scdet (ffmpeg 8/9) por cada cambio de escena detectado:
#   [Parsed_scdet_0 @ 0x...] lavfi.scd.score: 15.625, lavfi.scd.time: 4
# El tiempo puede venir sin decimales (4) o con ellos (4.04).
_RE_SCDET = re.compile(r"lavfi\.scd\.time:\s*([0-9]+(?:\.[0-9]+)?)")


def ffmpeg(args, timeout=300):
    """Ejecuta `ffmpeg -hide_banner -loglevel error -y <args>`. Devuelve el
    `CompletedProcess`; si ffmpeg falla lanza `RuntimeError` con el stderr
    recortado (las últimas líneas, que es donde está la causa)."""
    return _ejecutar([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + list(args), timeout)


def ffprobe_json(path):
    """`ffprobe -print_format json -show_streams -show_format` como dict."""
    salida = _ejecutar([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", path,
    ], timeout=60)
    return json.loads(salida.stdout or "{}")


def duracion(path):
    """Duración del archivo en segundos (float), según su `format`."""
    info = ffprobe_json(path)
    valor = (info.get("format") or {}).get("duration")
    if valor is None:
        # Algunos contenedores solo la reportan en el stream de video.
        for s in info.get("streams") or []:
            if s.get("codec_type") == "video" and s.get("duration"):
                valor = s["duration"]
                break
    if valor is None:
        raise RuntimeError(f"ffprobe no reporta duración para {path}")
    return float(valor)


def detectar_cortes(video_path, umbral=10.0):
    """Tiempos (s) de los cambios de escena del clip, ordenados y sin
    duplicados, ignorando los que caen a menos de 0.3 s de los extremos.
    `umbral` es el parámetro `t` de scdet (0–100; 10 es lo razonable para
    cortes duros; a menor valor, más sensible)."""
    total = duracion(video_path)
    # Sin `-loglevel error`: los tiempos los imprime scdet a nivel info, así
    # que no pasa por `ffmpeg()`.
    proc = _ejecutar([
        FFMPEG, "-hide_banner", "-nostats", "-i", video_path,
        "-vf", f"scdet=t={umbral}:s=1", "-an", "-f", "null", "-",
    ], timeout=300)
    return _parsear_scdet(proc.stderr, total)


def _parsear_scdet(stderr, duracion_s):
    tiempos = set()
    for m in _RE_SCDET.finditer(stderr or ""):
        t = round(float(m.group(1)), 2)
        if _BORDE_S < t < duracion_s - _BORDE_S:
            tiempos.add(t)
    return sorted(tiempos)


def planificar_segmentos(duracion_s, cortes, objetivo_s, min_seg=1.5, max_seg=4.0):
    """Lista de `{"inicio", "fin", "zoom"}` que cubre `[0, min(duracion_s,
    objetivo_s)]` de forma contigua. Usa los cortes naturales cuando todos
    los trozos que definen miden ≥ `min_seg` (los mayores que `max_seg` se
    parten en partes iguales); si no hay cortes utilizables fabrica
    `clamp(round(objetivo/2.5), 3, 4)` segmentos iguales. `zoom` alterna
    "in"/"out" empezando por "in"."""
    total = round(min(float(duracion_s), float(objetivo_s)), 3)
    if total <= 0:
        return []

    limites = _limites_por_cortes(total, cortes, min_seg, max_seg)
    if limites is None:
        n = max(3, min(4, int(round(total / 2.5))))
        paso = total / n
        limites = [round(i * paso, 3) for i in range(n)] + [total]

    plan = []
    for i, (a, b) in enumerate(zip(limites, limites[1:])):
        plan.append({"inicio": a, "fin": b, "zoom": "in" if i % 2 == 0 else "out"})
    return plan


def _limites_por_cortes(total, cortes, min_seg, max_seg):
    """Fronteras [0, ..., total] derivadas de los cortes, o None si los cortes
    no sirven (no hay, o dejan algún trozo más corto que `min_seg`)."""
    internos = sorted({round(float(c), 3) for c in cortes or [] if 0 < c < total})
    # Una cola más corta que `min_seg` (típico al recortar a `objetivo_s`) se
    # funde con el trozo anterior en vez de invalidar los cortes reales.
    while internos and total - internos[-1] < min_seg - 1e-6:
        internos.pop()
    if not internos:
        return None

    bordes = [0.0] + internos + [total]
    limites = [0.0]
    for a, b in zip(bordes, bordes[1:]):
        largo = b - a
        if largo < min_seg - 1e-6:
            # Un corte demasiado pegado a otro o al final: el plan por cortes
            # no vale y se cae a ken burns fabricado.
            return None
        partes = max(1, int(-(-largo // max_seg)))  # ceil
        paso = largo / partes
        limites += [round(a + paso * k, 3) for k in range(1, partes)] + [b]
    return limites


def _ejecutar(cmd, timeout):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError(f"No se encontró {cmd[0]!r}; instala ffmpeg o define FFMPEG/FFPROBE")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{os.path.basename(cmd[0])} superó {timeout}s: {' '.join(cmd[:6])}...")
    if proc.returncode != 0:
        detalle = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
        raise RuntimeError(f"{os.path.basename(cmd[0])} falló (código {proc.returncode}): {detalle}")
    return proc
