"""Rasterizador de texto del servidor (Pillow) — spec §2.1 punto 3 y §5
(«render.py y texto.py quedan como base del compilador y del borrador»).

Los textos libres del editor llegan como PNG del navegador (`pngs`); todo lo
que se produce SIN navegador (el borrador automático, las derivaciones, un
«Producir» lanzado por una tarea) necesita el mismo PNG hecho aquí, con las
mismas TTF de `static/fonts/`. Cuando el navegador manda su PNG, ese gana:
`tareas.edicion.preparar_rutas` solo rasteriza los clips sin entrada en
`pngs`. Estos PNG no son materiales: se regeneran en milisegundos.

Medidas en fracción del lienzo (spec §1.1): `estilo.tamano`,
`contorno.grosor`, `sombra.dx/dy`, `fondo.radio`, `fondo.relleno_x/y` son
fracción de la ALTURA; `estilo.ancho_max` y `fondo.ancho`, del ANCHO. El PNG
mide exactamente su caja (texto + relleno del fondo + margen para contorno y
sombra) y NO se recorta al contenido: esa caja es la que `geometria.caja`
coloca con el `transform` del clip, así que su tamaño tiene que ser
predecible para navegador y servidor por igual."""
import os
import re

from PIL import Image, ImageDraw, ImageFont

from final_edition import tipos
from final_edition.documento import FORMATOS

FONTS_DIR = os.path.join(tipos.BASE_DIR, "static", "fonts")
_FUENTE_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
MARGEN_PX = 4          # aire mínimo alrededor de la caja (el contorno se sale del bbox)
TAMANO_MIN_PX = 8
_ALINEAR = {"izquierda": "left", "centro": "center", "derecha": "right"}


class FuenteNoDisponible(ValueError):
    """La fuente pedida no existe en static/fonts (o el nombre trae rutas)."""


def ruta_fuente(nombre):
    """static/fonts/<nombre>.ttf; el nombre se valida ANTES de armar la ruta
    (un `../x` no debe ni mirarse en el disco)."""
    if not isinstance(nombre, str) or not _FUENTE_RE.match(nombre):
        raise FuenteNoDisponible(f"Nombre de fuente inválido: {nombre!r}.")
    ruta = os.path.join(FONTS_DIR, f"{nombre}.ttf")
    if not os.path.isfile(ruta):
        raise FuenteNoDisponible(f"La fuente {nombre} no está en static/fonts.")
    return ruta


def color(valor, opacidad=None):
    """'#RRGGBB' | '#RRGGBBAA' -> (r, g, b, a). `opacidad` (0–1) multiplica el alfa."""
    v = str(valor or "#FFFFFF").lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    a = int(v[6:8], 16) if len(v) == 8 else 255
    if opacidad is not None:
        a = int(round(a * max(0.0, min(1.0, float(opacidad)))))
    return (r, g, b, a)


def _px(fraccion, base):
    return int(round(float(fraccion or 0) * base))


def ajustar_lineas(medidor, texto, fuente, ancho_max_px):
    """Ajuste voraz por palabras (como texto._ajustar): línea nueva cuando la
    medida superaría `ancho_max_px`; una palabra más ancha que el límite va
    sola. Sin límite (None) cada párrafo va en una línea; los saltos
    explícitos se respetan."""
    lineas = []
    for parrafo in str(texto or "").split("\n"):
        actual = ""
        for palabra in parrafo.split():
            candidata = f"{actual} {palabra}".strip()
            if actual and ancho_max_px and medidor.textlength(candidata, font=fuente) > ancho_max_px:
                lineas.append(actual)
                actual = palabra
            else:
                actual = candidata
        lineas.append(actual)
    return lineas or [""]


def png_texto(texto, estilo, formato, ruta):
    """Escribe el PNG (RGBA) de `texto` con `estilo` (ya normalizado por
    documento.validar) para un lienzo `formato` y devuelve
    {"ancho_px", "alto_px"}: el tamaño natural de la capa."""
    ancho_l, alto_l = FORMATOS[formato]
    tam = max(TAMANO_MIN_PX, _px(estilo.get("tamano", 0.04), alto_l))
    fuente = ImageFont.truetype(ruta_fuente(estilo.get("fuente")), tam)
    espaciado = _px(float(estilo.get("interlineado") or 1.1) - 1.0, tam)
    alinear = _ALINEAR[estilo.get("alineacion") or "centro"]
    contorno = estilo.get("contorno") or None
    grosor = _px(contorno["grosor"], alto_l) if contorno else 0
    sombra = estilo.get("sombra") or None
    sdx = _px(sombra["dx"], alto_l) if sombra else 0
    sdy = _px(sombra["dy"], alto_l) if sombra else 0
    fondo = estilo.get("fondo") or None
    pad_x = _px(fondo["relleno_x"], alto_l) if fondo else 0
    pad_y = _px(fondo["relleno_y"], alto_l) if fondo else 0

    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ancho_max_px = _px(estilo["ancho_max"], ancho_l) if estilo.get("ancho_max") else None
    bloque = "\n".join(ajustar_lineas(medidor, texto, fuente, ancho_max_px))
    bbox = medidor.multiline_textbbox((0, 0), bloque, font=fuente, spacing=espaciado, align=alinear, stroke_width=grosor)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    caja_w = tw + 2 * pad_x
    if fondo and fondo.get("ancho"):
        caja_w = max(caja_w, _px(fondo["ancho"], ancho_l))
    caja_h = th + 2 * pad_y
    margen = MARGEN_PX + max(abs(sdx), abs(sdy))
    im = Image.new("RGBA", (int(caja_w + 2 * margen), int(caja_h + 2 * margen)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if fondo:
        radio = min(_px(fondo["radio"], alto_l), caja_h // 2, caja_w // 2)
        d.rounded_rectangle([margen, margen, margen + caja_w, margen + caja_h], radius=radio,
                            fill=color(fondo["color"], fondo.get("opacidad")))
    if alinear == "left":
        x0 = margen + pad_x - bbox[0]
    elif alinear == "right":
        x0 = margen + caja_w - pad_x - tw - bbox[0]
    else:
        x0 = margen + (caja_w - tw) // 2 - bbox[0]
    y0 = margen + pad_y - bbox[1]
    if sombra:
        d.multiline_text((x0 + sdx, y0 + sdy), bloque, font=fuente, fill=color(sombra["color"]), spacing=espaciado,
                         align=alinear, stroke_width=grosor, stroke_fill=color(sombra["color"]))
    d.multiline_text((x0, y0), bloque, font=fuente, fill=color(estilo.get("color")), spacing=espaciado, align=alinear,
                     stroke_width=grosor, stroke_fill=color(contorno["color"]) if contorno else None)
    im.save(ruta)
    return {"ancho_px": im.width, "alto_px": im.height}
