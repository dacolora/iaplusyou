"""Lo que cobra cada modelo de swap de video según la duración REAL del video que se sube (PND-312, pedido de
Daniel 2026-10-13). Antes todos se cobraban como 5 s y solo la salida: happyflops tenía 12 swaps de Seedance
anotados en US$ 12,80 que costaron ≈ US$ 38.

Una sola tabla para el precio que se ve antes de generar (la pantalla «Cambiar producto» la recibe con el margen),
la reserva al encolar y lo que anota la tarea al terminar. Reglas leídas en la página de cada modelo el 2026-10-13:

- Seedance 2.5 Video Edit (WaveSpeed): «combined duration of input + output», la entrada se cuenta entre 4 y 30 s;
  US$ 0,22/s en 720p (5 s de entrada → 10 s → US$ 2,20).
- Wan 2.7 Video Edit (WaveSpeed): US$ 0,10/s de entrada + US$ 0,10/s de salida en 720p, «input video duration,
  rounded up to a whole second and limited to 2–10 seconds» (5 s → US$ 1,00).
- Kling O3 Pro Video Edit (WaveSpeed): US$ 0,168/s de salida, «clamped between 3 and 10 seconds».
- Kling O1 Edit (fal): US$ 0,126/s de salida (bajó desde los 0,168 del 29 ago); acepta videos de 3 a 10 s.
- Luma Ray 2 Modify (fal): US$ 0,35/s.
- Wan 2.2 Animate Replace (fal, 480p por defecto): US$ 0,04 por «video second» de 16 cuadros: cuenta los cuadros
  del video (duración × fps / 16).
- Luma Ray 3.2 Video Edit (WaveSpeed): precio fijo por la salida que se pide; la app no la cambia (540p, 5 s):
  US$ 0,72.

La salida de un swap dura lo que la entrada (editan, no generan), así que todo se calcula con la entrada."""
import json
import math
import subprocess

FPS_SUPUESTO = 30.0  # el navegador no sabe los cuadros por segundo; el servidor los mide

# usd_s: por segundo facturado · factor: 2 si cobra entrada + salida · min_s/max_s: segundos que se facturan ·
# redondear: sube al segundo entero · por_cuadros: cuenta «segundos de video» de 16 cuadros · fijo: precio fijo.
# recorte_s: lo que el modelo procesa como máximo (lo demás se corta; la pantalla avisa) · salida_s: lo que dura la
# salida si el modelo no sigue al video.
TARIFAS = {
    "seedance25_edit": {"usd_s": 0.22, "factor": 2, "min_s": 4, "max_s": 30, "redondear": False, "recorte_s": 30},
    "wan27_edit": {"usd_s": 0.10, "factor": 2, "min_s": 2, "max_s": 10, "redondear": True, "recorte_s": 10},
    "kling_o3_pro_edit": {"usd_s": 0.168, "factor": 1, "min_s": 3, "max_s": 10, "redondear": False, "recorte_s": 10},
    "kling_o1": {"usd_s": 0.126, "factor": 1, "min_s": 3, "max_s": 10, "redondear": False, "recorte_s": 10},
    "luma_modify": {"usd_s": 0.35, "factor": 1, "min_s": 0, "max_s": None, "redondear": False},
    "wan_animate_replace": {"usd_s": 0.04, "factor": 1, "min_s": 0, "max_s": None, "redondear": False,
                            "por_cuadros": 16},
    "luma_ray32_edit": {"fijo": 0.72, "salida_s": 5},
}
NECESITA_FPS = tuple(k for k, t in TARIFAS.items() if t.get("por_cuadros"))


def segundos_facturados(proveedor, duracion_s, fps=None):
    """Los segundos que cobra el proveedor por un video de `duracion_s` (None si no hay tarifa o duración)."""
    t = TARIFAS.get(proveedor)
    if t is None or "fijo" in t or duracion_s is None:
        return None
    d = max(0.0, float(duracion_s))
    if t.get("por_cuadros"):
        d = d * float(fps or FPS_SUPUESTO) / t["por_cuadros"]
    if t["redondear"]:
        d = math.ceil(round(d, 6))
    d = max(d, t["min_s"])
    if t["max_s"] is not None:
        d = min(d, t["max_s"])
    return d * t["factor"]


def costo(proveedor, duracion_s, fps=None):
    """USD (costo, sin margen) de un swap de video; None si el modelo no tiene tarifa o falta la duración."""
    t = TARIFAS.get(proveedor)
    if t is None:
        return None
    if "fijo" in t:
        return t["fijo"]
    seg = segundos_facturados(proveedor, duracion_s, fps)
    return None if seg is None else round(seg * t["usd_s"], 4)


def medir(ruta):
    """(duración en segundos, cuadros por segundo) de un video en disco, con ffprobe; (None, None) si no se puede
    leer. Nunca lanza: quien llama decide qué hacer sin duración."""
    try:
        salida = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", ruta],
            capture_output=True, text=True, timeout=60)
        info = json.loads(salida.stdout or "{}")
    except Exception:  # noqa: BLE001 — sin ffprobe o archivo roto: sin medida
        return None, None
    video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), None)
    if video is None:
        return None, None
    try:
        duracion = float((info.get("format") or {}).get("duration") or video.get("duration"))
    except (TypeError, ValueError):
        return None, None
    fps = None
    num, _, den = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "").partition("/")
    try:
        fps = float(num) / float(den or 1) if float(den or 1) else None
    except ValueError:
        fps = None
    if not duracion or duracion <= 0:
        return None, None
    return round(duracion, 3), (round(fps, 3) if fps else None)
