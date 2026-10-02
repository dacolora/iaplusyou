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
predecible para navegador y servidor por igual.

Dos motores (capa 5c, D3): un texto sin `estilo.version` (v1) sale EXACTAMENTE
como antes (`multiline_text`, medida de Pillow; `tests/fixtures/rasterizar_v1.json`
guarda sus huellas). Un texto v2 (`estilo.version: 2`) se dibuja sobre la
maqueta compartida con la vista previa (`tipografia.maquetar`, D5): letra por
letra, cada una en su origen, con los emojis a color capa por capa (D6.8) y a
`factor_nitidez` veces su tamaño (D8), para que no se vea borroso agrandado. El
PNG de v2 mide `natural × factor`, pero lo que se devuelve (y se estampa en el
clip) es el tamaño NATURAL: la caja que coloca `geometria.caja` no cambia y el
`scale=w:h` del compilador achica en vez de estirar."""
import functools
import io
import os
import re

from PIL import Image, ImageDraw, ImageFont

from final_edition import fuentes, tipografia, tipos
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


# Capa 4c: un carácter que la fuente no trae (un emoji: Inter y Space Grotesk
# no tienen) Pillow lo dibuja como la caja de «carácter que falta». Se
# reconoce comparando su dibujo con el de un código sin asignar en Unicode,
# que ninguna fuente trae (el mismo glifo .notdef).
_SIN_ASIGNAR = "\u0378"
_TAMANO_PRUEBA = 24
# Uni\u00f3n de ancho cero, selectores de variante y el tecla-encerrada de 1\ufe0f\u20e3.
_UNIONES_EMOJI = frozenset("\u200d\ufe0e\ufe0f\u20e3")


@functools.lru_cache(maxsize=None)
def _fuente_prueba(ruta):
    fuente = ImageFont.truetype(ruta, _TAMANO_PRUEBA)
    return fuente, bytes(fuente.getmask(_SIN_ASIGNAR))


@functools.lru_cache(maxsize=4096)
def _tiene_glifo(ruta, ch):
    fuente, falta = _fuente_prueba(ruta)
    return bytes(fuente.getmask(ch)) != falta


def sin_glifos_faltantes(texto, fuente):
    """`texto` sin los caracteres que `fuente` no puede dibujar (los emojis,
    con sus uniones y selectores de variante), en vez de una caja por cada
    uno; si quitó algo, sin los espacios dobles ni de los bordes que dejó en
    cada línea. Sin nada que quitar, el texto tal cual. El panel del editor
    avisa que los emojis no salen (propiedades_modelo.tieneEmoji)."""
    texto = str(texto or "")
    ruta = ruta_fuente(fuente)
    _f, falta = _fuente_prueba(ruta)
    if not any(falta):                # esa fuente no dibuja caja: no hay nada que arreglar
        return texto
    quedan, quitado = [], False
    for ch in texto:
        # La unión (ZWJ) y los selectores de variante no ocupan ancho: desde
        # Pillow 12.3 no salen como caja, así que se quitan junto con el
        # emoji que va antes de ellos (👨‍👩‍👧 se va entero).
        conservar = (not quitado if ch in _UNIONES_EMOJI else True) and (ch.isspace() or _tiene_glifo(ruta, ch))
        if conservar:
            quedan.append(ch)
        quitado = not conservar
    if len(quedan) == len(texto):
        return texto
    return "\n".join(re.sub(r"[ \t]{2,}", " ", linea).strip() for linea in "".join(quedan).split("\n"))


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


def png_texto(texto, estilo, formato, ruta, escala_max=1.0):
    """Escribe el PNG (RGBA) de `texto` con `estilo` (ya normalizado por
    documento.validar) para un lienzo `formato` y devuelve
    {"ancho_px", "alto_px"}: el tamaño natural de la capa. Un texto v2 se
    dibuja a `factor_nitidez(escala_max, …)` veces ese tamaño (`_png_v2`);
    uno v1, como siempre (`escala_max` no se usa)."""
    if tipografia.es_v2(estilo):
        return _png_v2(texto, estilo, formato, ruta, escala_max)
    ancho_l, alto_l = FORMATOS[formato]
    tam = max(TAMANO_MIN_PX, _px(estilo.get("tamano", 0.04), alto_l))
    fuente = ImageFont.truetype(ruta_fuente(estilo.get("fuente")), tam)
    texto = sin_glifos_faltantes(texto, estilo.get("fuente"))      # capa 4c: sin cajas de emoji
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


# --- texto v2 (capa 5c, D5.7, D6.8, D8) ------------------------------------------

_AIRE = 2                        # px transparentes alrededor de la capa de cada letra


@functools.lru_cache(maxsize=32)
def _fuente_v2(ruta, tam):
    """La fuente de texto `ruta` abierta a `tam` px, una vez por (ruta, tamaño).
    Con `Layout.BASIC` siempre: el Pillow del VPS trae Raqm, que aplica las formas
    contextuales aun a una letra sola (Pacifico salía en «forma final», 2026-10-02),
    y el lienzo dibuja el glifo base."""
    return ImageFont.truetype(ruta, tam, layout_engine=ImageFont.Layout.BASIC)


@functools.lru_cache(maxsize=8)
def _fuente_emoji_v2(tam):
    """La copia de la fuente de emojis sin color y con cada glifo en `PUA_CAPAS +
    glifo` (`fuentes.fuente_emoji_capas`) abierta a `tam` px. Caché propia y
    chica: abierta desde bytes, cada tamaño guarda su copia (≈ 1,5 MB) y el
    worker del VPS tiene 2 GB. `Layout.BASIC` por lo mismo que `_fuente_v2`
    (Raqm en el VPS, 2026-10-02)."""
    return ImageFont.truetype(io.BytesIO(fuentes.fuente_emoji_capas()), tam, layout_engine=ImageFont.Layout.BASIC)


def _componer(im, origen, ch, fuente, fill, stroke_width=0, stroke_fill=None):
    """Dibuja `ch` con `anchor="ls"` en `origen` (enteros) y lo compone ENCIMA de
    `im`, como el lienzo del navegador. `draw.text` directo sobre un RGBA no
    compone: reemplaza el alfa del lienzo por el de la tinta (la capa al 20 % de
    🎯 dejaría un agujero al 20 % en lo que tapa; una sombra translúcida, uno en
    el fondo). Por eso cada letra va en una capa propia del tamaño de su caja y
    entra con `alpha_composite`; con un origen entero la máscara es la misma
    que sobre el lienzo grande."""
    izq, arr, der, aba = fuente.getbbox(ch, anchor="ls", stroke_width=stroke_width)
    if der <= izq or aba <= arr:
        return                               # sin tinta (un espacio de ancho cero)
    izq, arr, der, aba = izq - _AIRE, arr - _AIRE, der + _AIRE, aba + _AIRE
    capa = Image.new("RGBA", (der - izq, aba - arr), (0, 0, 0, 0))
    ImageDraw.Draw(capa).text((-izq, -arr), ch, font=fuente, fill=fill, anchor="ls",
                              stroke_width=stroke_width, stroke_fill=stroke_fill)
    x, y = origen[0] + izq, origen[1] + arr
    desde_x, desde_y = max(0, -x), max(0, -y)      # `alpha_composite` no acepta destinos negativos
    if desde_x >= capa.width or desde_y >= capa.height:
        return
    im.alpha_composite(capa, dest=(max(0, x), max(0, y)), source=(desde_x, desde_y))


def _png_v2(texto, estilo, formato, ruta, escala_max):
    """El PNG de un texto v2 sobre la maqueta (D5.7): lienzo de natural × f, el
    fondo, y tres pasadas sobre las letras — sombra, contorno y relleno —, cada
    letra en `(redondear(x·f), redondear(base·f))` a `tam·f` px. Pasada por
    pasada: el contorno de una letra nunca tapa el relleno de la anterior. Los
    emojis solo en la de relleno, capa por capa en el color de cada una (`None`
    = el del texto), nunca con `embedded_color` (R1). Devuelve las medidas
    NATURALES."""
    nombre = estilo.get("fuente")
    ruta_ttf = ruta_fuente(nombre)               # nombre inválido o sin TTF: los mensajes de siempre
    tabla = fuentes.cargar_tabla()
    if nombre not in (tabla.get("fuentes") or {}):
        # `maquetar` lanzaría un ValueError pelado; quien llama espera este.
        raise FuenteNoDisponible(f"La fuente {nombre} no está en static/fonts.")
    m = tipografia.maquetar(texto, estilo, formato, tabla)
    f = tipografia.factor_nitidez(escala_max, m["ancho_px"], m["alto_px"])
    medidas = tipografia.medidas_texto(estilo, formato)
    im = Image.new("RGBA", (m["ancho_px"] * f, m["alto_px"] * f), (0, 0, 0, 0))
    fondo = estilo.get("fondo") or None
    if fondo and m["caja_w"] > 0 and m["caja_h"] > 0:
        margen = m["margen"]
        # El rectángulo de Pillow es INCLUSIVO (x1, y1 son píxeles pintados): para medir lo mismo que el
        # `fillRect` del lienzo (caja_w·f × caja_h·f) acaba un píxel antes. Solo v2: v1 sale como siempre.
        ImageDraw.Draw(im).rounded_rectangle(
            [margen * f, margen * f, (margen + m["caja_w"]) * f - 1, (margen + m["caja_h"]) * f - 1],
            radius=m["radio"] * f, fill=color(fondo["color"], fondo.get("opacidad")))
    letras = [(l, (tipografia.redondear(l["x"] * f), tipografia.redondear(l["base"] * f))) for l in m["letras"]]
    de_texto = [(chr(l["cp"]), origen) for l, origen in letras if l["fuente"] == "texto"]
    fuente_t = _fuente_v2(ruta_ttf, m["tam"] * f)
    grosor = medidas["grosor"] * f
    sombra = estilo.get("sombra") or None
    if sombra:
        c = color(sombra["color"])
        dx, dy = medidas["sdx"] * f, medidas["sdy"] * f
        for ch, (x, y) in de_texto:
            _componer(im, (x + dx, y + dy), ch, fuente_t, c, grosor, c)
    contorno = estilo.get("contorno") or None
    if contorno:
        c = color(contorno["color"])
        for ch, origen in de_texto:
            _componer(im, origen, ch, fuente_t, c, grosor, c)
    relleno = color(estilo.get("color"))
    fuente_e = None
    for l, origen in letras:
        if l["fuente"] != "emoji":
            _componer(im, origen, chr(l["cp"]), fuente_t, relleno)
            continue
        capas = fuentes.emoji_capas(l["cp"])
        if not capas:
            continue                             # no debería llegar: la maqueta solo manda lo que la tabla cubre
        if fuente_e is None:
            fuente_e = _fuente_emoji_v2(m["tam"] * f)
        for glifo, c in capas:
            _componer(im, origen, chr(fuentes.PUA_CAPAS + glifo), fuente_e, c or relleno)
    im.save(ruta)
    return {"ancho_px": m["ancho_px"], "alto_px": m["alto_px"]}
