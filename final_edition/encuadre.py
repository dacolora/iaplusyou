"""El encuadre de un clip de la pista principal (editor, capa 5b, spec D4-D7):
qué parte del cuadro se ve y cómo se compone cuando no coincide con el
lienzo. Puro: sin base, sin ffmpeg, sin red. Espejo exacto de
`static/editor/encuadre.js` (`tests/fixtures/encuadre_casos.json` es la
tabla de paridad que corren los dos motores) — las mismas operaciones de
coma flotante, en el mismo orden, dan los mismos números enteros en Python
y en el navegador.

`caja` (D4) es la fórmula que usan a la vez `documento.validar` (para saber
si un encuadre guardado queda igual al por defecto), el compilador (D4
cuadro en «llenar»/primer plano en «ajustar») y la vista previa. `w×h` es el
tamaño del cuadro que se VE (D6, `medidas_visibles`); `W×H`, el lienzo.
`fondo` (D5) es el lienzo chico del fondo desenfocado de «ajustar».
`ajuste_automatico` (D7) es el encuadre que se pone SOLO al agregar un clip
cuya proporción difiere mucho de la del lienzo — nunca al abrir ni al
editar algo que ya tenía su encuadre (o la falta de uno)."""
import math

MODOS = ("llenar", "ajustar")
ZOOM_MIN = 1.0
ZOOM_MAX = 4.0
DEFECTO = {"modo": "llenar", "zoom": 1.0, "x": 0.5, "y": 0.5}
FONDO_DIVISOR = 10      # D5: el lienzo del fondo desenfocado es 1/10 del lienzo real
FONDO_RADIO = 6         # boxblur=luma_radius=6
FONDO_PASADAS = 2       # boxblur=...:luma_power=2
# D7: la proporción del clip difiere de la del lienzo en más de un 25 %
# (5/4) cuando `UMBRAL_AJUSTE[1]·w·H > UMBRAL_AJUSTE[0]·h·W` o
# `UMBRAL_AJUSTE[0]·w·H < UMBRAL_AJUSTE[1]·h·W` — enteros, sin error de
# coma flotante.
UMBRAL_AJUSTE = [5, 4]


def par(v):
    """El entero PAR más cercano a `v` (yuv420p: medidas y desplazamientos
    pares); un `v` a mitad de camino entre dos pares (un entero impar)
    redondea hacia arriba. `2·⌊v/2 + 0,5⌋` — la misma cuenta, en el mismo
    orden, que `static/editor/encuadre.js::par`."""
    return 2 * math.floor(v / 2 + 0.5)


def completo(enc):
    """El encuadre con sus valores por defecto rellenados (D4); `None` o
    `{}` dan `DEFECTO` tal cual."""
    return {**DEFECTO, **(enc or {})}


def caja(ancho, alto, lienzo_w, lienzo_h, enc):
    """La caja del cuadro escalado dentro del lienzo (D4): `sw`/`sh` su
    tamaño en píxeles, `px`/`py` dónde queda su esquina superior izquierda
    (pueden ser negativos o, en «ajustar», positivos — `overlay`/`crop` los
    usan tal cual). `ancho`/`alto` son las medidas que se VEN del clip
    (`medidas_visibles`); `lienzo_w`/`lienzo_h`, el formato de la edición."""
    c = completo(enc)
    modo, zoom, x, y = c["modo"], c["zoom"], c["x"], c["y"]
    w, h, w_lienzo, h_lienzo = ancho, alto, lienzo_w, lienzo_h
    manda_el_alto = (w * h_lienzo >= h * w_lienzo) == (modo == "llenar")
    if manda_el_alto:
        sh = par(h_lienzo * zoom)
        sw = par(w * sh / h)
    else:
        sw = par(w_lienzo * zoom)
        sh = par(h * sw / w)
    px = 0 - par((sw - w_lienzo) * x)
    py = 0 - par((sh - h_lienzo) * y)
    return {"sw": sw, "sh": sh, "px": px, "py": py}


def fondo(lienzo_w, lienzo_h):
    """El lienzo chico del fondo desenfocado de «ajustar» (D5): par(W/10),
    par(H/10)."""
    return [par(lienzo_w / FONDO_DIVISOR), par(lienzo_h / FONDO_DIVISOR)]


def ajuste_automatico(ancho, alto, lienzo_w, lienzo_h):
    """`{"modo": "ajustar"}` si la proporción de `ancho×alto` difiere de la
    del lienzo en más de un 25 % (D7); si no, `None` (sin encuadre: llena
    igual). Frontera incluida en «no hace falta» (exactamente 25 % no
    ajusta)."""
    mayor, menor = UMBRAL_AJUSTE
    w, h, w_lienzo, h_lienzo = ancho, alto, lienzo_w, lienzo_h
    if menor * w * h_lienzo > mayor * h * w_lienzo or mayor * w * h_lienzo < menor * h * w_lienzo:
        return {"modo": "ajustar"}
    return None


def _rotacion_de(stream):
    """Los grados de rotación de `stream` (ffprobe): primero
    `side_data_list[].rotation` (el primer elemento que lo trae); si no,
    `tags.rotate` (un ffprobe viejo); si no hay ninguno, 0."""
    for sd in (stream or {}).get("side_data_list") or []:
        if isinstance(sd, dict) and "rotation" in sd:
            try:
                return int(sd["rotation"])
            except (TypeError, ValueError):
                return 0
    rotate = ((stream or {}).get("tags") or {}).get("rotate")
    if rotate is not None:
        try:
            return int(rotate)
        except (TypeError, ValueError):
            return 0
    return 0


def medidas_visibles(stream):
    """El ancho y el alto que se VEN de `stream` (D6): lo codificado
    (`width`/`height`) intercambiado si la rotación es ±90 o ±270 (un
    video grabado de pie con el celular viene codificado acostado, con una
    marca de rotación)."""
    ancho = int((stream or {}).get("width") or 0)
    alto = int((stream or {}).get("height") or 0)
    if abs(_rotacion_de(stream)) % 180 == 90:
        return (alto, ancho)
    return (ancho, alto)
