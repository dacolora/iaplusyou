"""Subtítulos como un solo archivo ASS (spec §2.1 punto 5): un filtro
`subtitles` en vez de un `overlay` por palabra. Sin límite por cantidad.

Capa 5a (spec D7): en vez de `\\k` de libass (la línea entera naranja que se
vuelve blanca palabra por palabra), una función PURA decide QUÉ se ve y
CUÁNDO (`eventos`) y los dos motores (este módulo y su espejo
`static/editor/subtitulos.js`) solo dibujan esos eventos. Un evento es
`{t_ms, dur_ms, tam_px, palabras: [{texto, resaltada}]}`: en un estilo que
resalta, cada palabra de la línea tiene su propio evento (la línea completa,
con SOLO esa palabra marcada `resaltada`); en uno que no resalta, toda la
línea es un único evento sin nada resaltado.

Si el ffmpeg de la máquina no trae libass (la Mac de desarrollo), el render
omite los subtítulos y lo avisa por `on_etapa` (`motor/render.tiene_libass`);
en el VPS (ffmpeg 8 con libass) entran por el filtro `subtitles`. Este módulo
es puro y se prueba en todas partes."""
import functools
import os
import re
import struct

from final_edition import documento
from final_edition.documento import FORMATOS

ESTILOS = documento.ESTILOS_SUBTITULOS   # D7: la tupla vive en documento.py
SIN_SUBTITULOS = ""
HUECO_MAX_MS = 600

# Fuente, tamaño (px sobre PlayResY 1920; libass escala con PlayRes), colores
# ASS en &HAABBGGRR& (AA = transparencia, 00 = opaco), contorno, sombra,
# BorderStyle (1 = contorno + sombra, 3 = caja). `max_palabras`/`max_caracteres`
# van a `ventanas()`; `resalta` decide un evento por palabra o por línea;
# `mayusculas` se aplica antes de agrupar; `resaltado` es el color por
# defecto de la palabra que suena (None en los estilos que no resaltan).
# Tabla D7 — sin `secundario`: el `Style` ya no lo necesita (sin `\k`).
_ESTILOS = {
    "karaoke":        {"tam": 64,  "negrita": -1, "primario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H66000000&",
                       "borde": 3, "grosor": 0, "sombra": 0,
                       "max_palabras": 4, "max_caracteres": 22, "resalta": True, "mayusculas": False, "resaltado": "#FFD400"},
    "caja":           {"tam": 60,  "negrita": -1, "primario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H4D000000&",
                       "borde": 3, "grosor": 0, "sombra": 0,
                       "max_palabras": 4, "max_caracteres": 22, "resalta": False, "mayusculas": False, "resaltado": None},
    "palabra_grande": {"tam": 110, "negrita": -1, "primario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H80000000&",
                       "borde": 1, "grosor": 5, "sombra": 3,
                       "max_palabras": 1, "max_caracteres": 10, "resalta": True, "mayusculas": True, "resaltado": "#FFD400"},
    "minimal":        {"tam": 52,  "negrita": 0,  "primario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H00000000&",
                       "borde": 1, "grosor": 2, "sombra": 0,
                       "max_palabras": 5, "max_caracteres": 28, "resalta": False, "mayusculas": False, "resaltado": None},
}

# Público para la vista previa del editor (final_edition/vista_previa.py):
# el navegador dibuja con estos mismos valores, nunca copiados a mano.
ESTILOS_ASS = _ESTILOS
_TTF_SUBTITULOS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "static", "fonts", "Inter-Bold.ttf")


@functools.lru_cache(maxsize=8)
def escala_libass(ruta_ttf=None):
    """em del navegador por cada unidad de `Fontsize` del .ass. libass (como
    VSFilter) dimensiona la fuente para que usWinAscent + usWinDescent de la
    tabla OS/2 midan `Fontsize`; en CSS el tamaño es el em. Se lee de la TTF
    (tablas `head` y `OS/2`) para no copiar métricas a mano."""
    with open(ruta_ttf or _TTF_SUBTITULOS, "rb") as f:
        datos = f.read()
    n = struct.unpack(">H", datos[4:6])[0]
    tablas = {}
    for i in range(n):
        etiqueta, _suma, offset, _largo = struct.unpack(">4sIII", datos[12 + 16 * i: 28 + 16 * i])
        tablas[etiqueta] = offset
    upm = struct.unpack(">H", datos[tablas[b"head"] + 18: tablas[b"head"] + 20])[0]
    os2 = tablas[b"OS/2"]
    win_asc, win_desc = struct.unpack(">HH", datos[os2 + 74: os2 + 78])
    return upm / float(win_asc + win_desc)


def _tiempo_ass(ms):
    ms = max(0, int(ms))
    h, resto = divmod(ms, 3600000)
    m, resto = divmod(resto, 60000)
    s, resto = divmod(resto, 1000)
    return f"{h}:{m:02d}:{s:02d}.{resto // 10:02d}"


def _limpiar(texto):
    t = str(texto or "").replace("{", "(").replace("}", ")").replace("\\", "/")
    return re.sub(r"\s+", " ", t).strip()


def ventanas(palabras, max_palabras=4, max_ms=1800, max_caracteres=None):
    """Agrupa palabras consecutivas en ventanas de subtítulo. Una ventana
    dura estrictamente menos que `max_ms`. Con `max_caracteres`, la ventana
    también se cierra si la palabra siguiente la haría pasar de ese largo
    (las palabras ya limpias, unidas por un espacio); una palabra sola
    siempre entra, aunque por sí misma supere el tope. Sin `max_caracteres`
    se comporta como antes de esta regla."""
    out, actual = [], []
    for p in sorted(palabras, key=lambda x: int(x["t_ms"])):
        texto_p = _limpiar(p.get("texto"))
        if actual:
            fin_prev = actual[-1]["t_ms"] + actual[-1]["dur_ms"]
            dur_si_entra = p["t_ms"] + p["dur_ms"] - actual[0]["t_ms"]
            cierra_por_caracteres = (max_caracteres is not None and
                                      len(" ".join(a["texto"] for a in actual) + " " + texto_p) > max_caracteres)
            if (len(actual) >= max_palabras or p["t_ms"] - fin_prev > HUECO_MAX_MS
                    or dur_si_entra >= max_ms or cierra_por_caracteres):
                out.append(actual)
                actual = []
        actual.append({"t_ms": int(p["t_ms"]), "dur_ms": int(p["dur_ms"]), "texto": texto_p})
    if actual:
        out.append(actual)
    return [{"t_ms": v[0]["t_ms"], "dur_ms": v[-1]["t_ms"] + v[-1]["dur_ms"] - v[0]["t_ms"], "palabras": v} for v in out]


def _estilo_id_valido(subtitulos):
    estilo_id = (subtitulos or {}).get("estilo_id") or "karaoke"
    return estilo_id if estilo_id in _ESTILOS else "karaoke"


def estilo_efectivo(subtitulos):
    """Lo que un dibujante (ASS o el navegador) necesita de un estilo, ya
    resuelto contra el documento: `tam_base_px` aplica la `escala` (0.6–1.6);
    `resaltado` es el color de la palabra que suena — el del documento si lo
    hay y el estilo resalta, si no el del estilo (su color por defecto); en
    un estilo que NO resalta siempre es `None` (nada que colorear)."""
    sub = subtitulos or {}
    estilo_id = _estilo_id_valido(sub)
    e = _ESTILOS[estilo_id]
    escala = float(sub.get("escala", 1.0))
    if e["resalta"]:
        resaltado = sub.get("resaltado") or e["resaltado"]
    else:
        resaltado = None
    return {"id": estilo_id, "tam_base_px": round(e["tam"] * escala), "resaltado": resaltado,
            "negrita": e["negrita"], "borde": e["borde"], "grosor": e["grosor"], "sombra": e["sombra"],
            "primario": e["primario"], "contorno": e["contorno"], "fondo": e["fondo"], "mayusculas": e["mayusculas"]}


def eventos(subtitulos):
    """QUÉ se ve y CUÁNDO (D7 reglas 1–5), para que el ASS y el navegador
    solo dibujen. Palabras -> `ventanas()` del estilo (con su `max_palabras`/
    `max_caracteres`) -> cada ventana se estira hasta el inicio de la
    siguiente si el hueco (o el solape) es <= HUECO_MAX_MS (regla 3; la misma
    cuenta resuelve el estiramiento y el "nunca se solapan": si la siguiente
    empieza antes de que esta termine, esta termina ahí) -> en un estilo que
    resalta, un evento por palabra (la línea entera, con esa palabra
    marcada); si no, un evento por ventana, sin nada marcado (regla 4) ->
    tamaño por línea, nunca por palabra (regla 5: solo una línea más larga
    que el tope se achica)."""
    sub = subtitulos or {}
    estilo_id = _estilo_id_valido(sub)
    e = _ESTILOS[estilo_id]
    palabras = sub.get("palabras") or []
    if not palabras:
        return []
    escala = float(sub.get("escala", 1.0))
    if e["mayusculas"]:
        palabras = [{**p, "texto": _limpiar(p.get("texto")).upper()} for p in palabras]
    vents = ventanas(palabras, max_palabras=e["max_palabras"], max_caracteres=e["max_caracteres"])
    n = len(vents)
    out = []
    for i, v in enumerate(vents):
        fin_natural = v["t_ms"] + v["dur_ms"]
        if i + 1 < n:
            inicio_sig = vents[i + 1]["t_ms"]
            fin_efectivo = inicio_sig if inicio_sig - fin_natural <= HUECO_MAX_MS else fin_natural
        else:
            fin_efectivo = fin_natural
        palabras_linea = v["palabras"]
        largo_linea = len(" ".join(p["texto"] for p in palabras_linea))
        factor = min(1.0, e["max_caracteres"] / largo_linea) if (e["max_caracteres"] and largo_linea) else 1.0
        tam_px = round(e["tam"] * escala * factor)
        if e["resalta"]:
            for j, p in enumerate(palabras_linea):
                fin_j = palabras_linea[j + 1]["t_ms"] if j + 1 < len(palabras_linea) else fin_efectivo
                out.append({"t_ms": p["t_ms"], "dur_ms": fin_j - p["t_ms"], "tam_px": tam_px,
                           "palabras": [{"texto": pp["texto"], "resaltada": k == j} for k, pp in enumerate(palabras_linea)]})
        else:
            out.append({"t_ms": v["t_ms"], "dur_ms": fin_efectivo - v["t_ms"], "tam_px": tam_px,
                       "palabras": [{"texto": p["texto"], "resaltada": False} for p in palabras_linea]})
    return out


def _sin_alfa(valor_ass):
    """"&H00FFFFFF&" (AABBGGRR) -> "&HFFFFFF&" (BBGGRR, sin canal alfa): lo
    que llevan los overrides `\\1c` dentro de una línea (a diferencia del
    `Style`, que sí lleva alfa)."""
    cuerpo = valor_ass[2:-1]
    return f"&H{cuerpo[2:]}&"


def _color_resaltado_bgr(hex_rrggbb):
    """"#RRGGBB" -> "&HBBGGRR&" (sin alfa): el color de `subtitulos.resaltado`
    en la notación de ASS."""
    h = hex_rrggbb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b}{g}{r}&".upper()


def _texto_evento(evento, ef):
    primario_sin_alfa = _sin_alfa(ef["primario"])
    partes = []
    for p in evento["palabras"]:
        if p["resaltada"] and ef["resaltado"]:
            partes.append(f"{{\\1c{_color_resaltado_bgr(ef['resaltado'])}}}{p['texto']}{{\\1c{primario_sin_alfa}}}")
        else:
            partes.append(p["texto"])
    return " ".join(partes).strip()


def generar_ass(subtitulos, formato, fuente_nombre="Inter", ventana=None):
    """El documento ASS completo, o `SIN_SUBTITULOS` si no queda ningún
    evento (sin palabras, o ninguna toca la `ventana`). Con `ventana=(ini,
    fin)` los eventos se calculan sobre TODO `subtitulos.palabras` y LUEGO se
    recortan a esa ventana (desplazados `-ini`, acotados a `[0, fin-ini)`):
    una línea que cruza la unión de dos tramos sale igual que sin tramos,
    completa desde 0 en el tramo donde continúa."""
    evs = eventos(subtitulos)
    if ventana is not None:
        ini, fin = ventana
        recortados = []
        for ev in evs:
            inicio_abs = ev["t_ms"]
            fin_abs = ev["t_ms"] + ev["dur_ms"]
            if fin_abs <= ini or inicio_abs >= fin:
                continue
            nuevo_ini = max(0, inicio_abs - ini)
            nuevo_fin = min(fin - ini, fin_abs - ini)
            recortados.append({**ev, "t_ms": nuevo_ini, "dur_ms": nuevo_fin - nuevo_ini})
        evs = recortados
    if not evs:
        return SIN_SUBTITULOS
    ancho, alto = FORMATOS[formato]
    sub = subtitulos or {}
    estilo_id = _estilo_id_valido(sub)
    ef = estilo_efectivo(sub)
    y = int(round(float(sub.get("posicion", 0.78)) * alto))
    x = ancho // 2
    lineas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {ancho}", f"PlayResY: {alto}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # SecondaryColour = primario (D7: ya no hay `\k`, no se usa).
        f"Style: {estilo_id},{fuente_nombre},{ef['tam_base_px']},{ef['primario']},{ef['primario']},{ef['contorno']},{ef['fondo']},"
        f"{ef['negrita']},0,0,0,100,100,0,0,{ef['borde']},{ef['grosor']},{ef['sombra']},5,40,40,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for ev in evs:
        fs = f"{{\\fs{ev['tam_px']}}}" if ev["tam_px"] != ef["tam_base_px"] else ""
        texto = _texto_evento(ev, ef)
        lineas.append(f"Dialogue: 0,{_tiempo_ass(ev['t_ms'])},{_tiempo_ass(ev['t_ms'] + ev['dur_ms'])},{estilo_id},,0,0,0,,"
                      f"{{\\an5\\pos({x},{y})}}{fs}{texto}")
    return "\n".join(lineas) + "\n"


def escribir_ass(texto, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta
