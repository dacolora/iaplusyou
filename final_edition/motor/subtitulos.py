"""Subtítulos como un solo archivo ASS (spec §2.1 punto 5): un filtro
`subtitles` en vez de un `overlay` por palabra. Sin límite por cantidad.

En una máquina cuyo ffmpeg no trae libass (la Mac de desarrollo), el
compilador cae a PNG por ventana (Task 9); este módulo es puro y se prueba
en todas partes."""
import re

from final_edition.documento import FORMATOS

ESTILOS = ("karaoke", "caja", "palabra_grande", "minimal")
SIN_SUBTITULOS = ""
HUECO_MAX_MS = 600

# Fuente, tamaño (px sobre PlayResY 1920; libass escala con PlayRes), colores
# ASS en &HAABBGGRR&, contorno, sombra, BorderStyle (1 = contorno, 3 = caja).
# Naranja de resaltado RGB (237,174,124) → BGR 7CAEED.
_ESTILOS = {
    "karaoke":        {"tam": 64, "primario": "&H00FFFFFF&", "secundario": "&H007CAEED&", "contorno": "&H00000000&", "fondo": "&H99000000&", "borde": 3, "grosor": 0, "sombra": 0, "negrita": -1},
    "caja":           {"tam": 60, "primario": "&H00FFFFFF&", "secundario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&HB3000000&", "borde": 3, "grosor": 0, "sombra": 0, "negrita": -1},
    "palabra_grande": {"tam": 96, "primario": "&H00FFFFFF&", "secundario": "&H007CAEED&", "contorno": "&H00000000&", "fondo": "&H00000000&", "borde": 1, "grosor": 4, "sombra": 2, "negrita": -1},
    "minimal":        {"tam": 52, "primario": "&H00FFFFFF&", "secundario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H00000000&", "borde": 1, "grosor": 2, "sombra": 0, "negrita": 0},
}


def _tiempo_ass(ms):
    ms = max(0, int(ms))
    h, resto = divmod(ms, 3600000)
    m, resto = divmod(resto, 60000)
    s, resto = divmod(resto, 1000)
    return f"{h}:{m:02d}:{s:02d}.{resto // 10:02d}"


def _limpiar(texto):
    t = str(texto or "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", t).strip()


def ventanas(palabras, max_palabras=4, max_ms=1800):
    """Agrupa palabras consecutivas en ventanas de subtítulo.
    Una ventana dura estrictamente menos que `max_ms`."""
    out, actual = [], []
    for p in sorted(palabras, key=lambda x: int(x["t_ms"])):
        if actual:
            fin_prev = actual[-1]["t_ms"] + actual[-1]["dur_ms"]
            dur_si_entra = p["t_ms"] + p["dur_ms"] - actual[0]["t_ms"]
            if (len(actual) >= max_palabras or p["t_ms"] - fin_prev > HUECO_MAX_MS or dur_si_entra >= max_ms):
                out.append(actual); actual = []
        actual.append({"t_ms": int(p["t_ms"]), "dur_ms": int(p["dur_ms"]), "texto": _limpiar(p.get("texto"))})
    if actual:
        out.append(actual)
    return [{"t_ms": v[0]["t_ms"], "dur_ms": v[-1]["t_ms"] + v[-1]["dur_ms"] - v[0]["t_ms"], "palabras": v} for v in out]


def generar_ass(subtitulos, formato, fuente_nombre="Inter"):
    palabras = (subtitulos or {}).get("palabras") or []
    if not palabras:
        return SIN_SUBTITULOS
    ancho, alto = FORMATOS[formato]
    estilo_id = (subtitulos or {}).get("estilo_id") or "karaoke"
    if estilo_id not in _ESTILOS:
        estilo_id = "karaoke"
    e = _ESTILOS[estilo_id]
    y = int(round(float((subtitulos or {}).get("posicion", 0.78)) * alto))
    x = ancho // 2
    lineas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {ancho}", f"PlayResY: {alto}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {estilo_id},{fuente_nombre},{e['tam']},{e['primario']},{e['secundario']},{e['contorno']},{e['fondo']},"
        f"{e['negrita']},0,0,0,100,100,0,0,{e['borde']},{e['grosor']},{e['sombra']},5,40,40,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for v in ventanas(palabras):
        if estilo_id in ("karaoke", "palabra_grande"):
            texto = "".join(f"{{\\k{max(1, round(p['dur_ms'] / 10))}}}{p['texto']} " for p in v["palabras"]).strip()
        else:
            texto = " ".join(p["texto"] for p in v["palabras"])
        lineas.append(f"Dialogue: 0,{_tiempo_ass(v['t_ms'])},{_tiempo_ass(v['t_ms'] + v['dur_ms'])},{estilo_id},,0,0,0,,"
                      f"{{\\an5\\pos({x},{y})}}{texto}")
    return "\n".join(lineas) + "\n"


def escribir_ass(texto, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta
