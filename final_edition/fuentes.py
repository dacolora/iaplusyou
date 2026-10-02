"""Las fuentes del editor y su tabla tipográfica (spec editor capa 5c, D4/D6).

Tres cosas, todas leídas de los archivos TTF de `static/fonts/` con `struct`
(sin dependencias; Pillow dibuja con esas mismas TTF):

1. El catálogo: qué fuentes ofrece el editor, con su nombre y su categoría.
2. La tabla tipográfica (`static/editor/tipografia.json`): por fuente, la
   unidad (`upem`), el ascendente, el descendente y el avance de cada
   carácter del repertorio. El navegador mide el texto con ella y Python
   ajusta las líneas con ella, así que ven los MISMOS números sin tener que
   cargar una fuente en el navegador para medir. Se regenera con
   `venv/bin/python3 -m final_edition.fuentes`; `test_tabla_al_dia` falla si
   una TTF cambió y la tabla quedó vieja.
3. Los emojis por capas: la fuente de emojis (Twemoji, COLRv0) trae cada
   emoji como varias capas de un color. Pillow no las compone bien (recorta a
   la caja vacía del glifo base), así que el render dibuja cada capa como un
   glifo normal, con una copia en memoria de la fuente SIN las tablas de
   color y con un `cmap` que da a cada glifo un código propio
   (`PUA_CAPAS + glifo`). Aquí se arma esa copia y se leen las capas.

Nada de esto paga ni pide red."""
import functools
import json
import os
import struct

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(_BASE_DIR, "static", "fonts")
RUTA_EMOJI = os.path.join(FONTS_DIR, "emoji", "TwemojiMozilla.ttf")
EMOJI_ID = "TwemojiMozilla"
RUTA_TABLA = os.path.join(_BASE_DIR, "static", "editor", "tipografia.json")

# Los códigos que entran a la tabla (latín con acentos, puntuación general,
# símbolos de moneda, flechas, matemáticas, formas, dingbats y los bloques de
# emojis): lo que una persona escribe en un anuncio. Lo demás (cirílico, CJK…)
# no pesa en el archivo ni lo mide el navegador.
REPERTORIO = ((0x20, 0x24F), (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2100, 0x214F), (0x2190, 0x21FF),
              (0x2200, 0x22FF), (0x2300, 0x23FF), (0x25A0, 0x25FF), (0x2600, 0x27BF), (0x2B00, 0x2BFF),
              (0x1F000, 0x1FAFF))

CATEGORIAS = ("clasicas", "impacto", "redondeadas", "manuscritas", "serifa")

# (id = nombre de la TTF sin extensión = `estilo.fuente`, nombre que ve la persona, categoría)
CATALOGO = (
    ("Inter-Bold", "Inter Bold", "clasicas"),
    ("Inter-SemiBold", "Inter SemiBold", "clasicas"),
    ("SpaceGrotesk-Bold", "Space Grotesk", "clasicas"),
    ("Poppins-ExtraBold", "Poppins", "clasicas"),
    ("ArchivoBlack-Regular", "Archivo Black", "impacto"),
    ("Anton-Regular", "Anton", "impacto"),
    ("BebasNeue-Regular", "Bebas Neue", "impacto"),
    ("LilitaOne-Regular", "Lilita One", "redondeadas"),
    ("Pacifico-Regular", "Pacifico", "manuscritas"),
    ("CaveatBrush-Regular", "Caveat Brush", "manuscritas"),
    ("DMSerifDisplay-Regular", "DM Serif Display", "serifa"),
)

# Primer código de la zona privada del plano 15: `PUA_CAPAS + glifo` es el
# código que la fuente derivada (`fuente_emoji_capas`) da a cada glifo.
PUA_CAPAS = 0xF0000

_SIN_COLOR = ("COLR", "CPAL", "cmap")
_FIRMAS_TTF = (b"\x00\x01\x00\x00", b"true", b"OTTO")


def catalogo():
    """[{"id", "nombre", "categoria"}] de las fuentes del CATALOGO que tienen
    su TTF en `FONTS_DIR`, en el orden del CATALOGO (la de emojis no entra)."""
    return [{"id": i, "nombre": n, "categoria": c} for i, n, c in CATALOGO
            if os.path.isfile(os.path.join(FONTS_DIR, i + ".ttf"))]


def hay_emoji():
    return os.path.isfile(RUTA_EMOJI)


# --- lectura de una TTF -------------------------------------------------------

def _u16(d, o):
    return struct.unpack_from(">H", d, o)[0]


def _directorio(datos):
    """{etiqueta: (desplazamiento, largo)} de las tablas de una TTF, en el
    orden del archivo. `ValueError` si no es una TTF o una tabla se sale."""
    if len(datos) < 12 or datos[:4] not in _FIRMAS_TTF:
        raise ValueError("no es una fuente TrueType")
    n = _u16(datos, 4)
    if n == 0 or 12 + 16 * n > len(datos):
        raise ValueError("el directorio de tablas está incompleto")
    tablas = {}
    for i in range(n):
        etiqueta, _suma, desde, largo = struct.unpack_from(">4sIII", datos, 12 + 16 * i)
        if desde + largo > len(datos):
            raise ValueError("una tabla se sale del archivo")
        tablas[etiqueta.decode("latin-1")] = (desde, largo)
    return tablas


def _cmap_formato_4(d, sub):
    """(código, glifo) de una subtabla formato 4 (BMP por segmentos)."""
    seg2 = _u16(d, sub + 6)
    fin = sub + 14
    ini = fin + seg2 + 2                 # tras endCode[] y reservedPad
    delta = ini + seg2
    rango = delta + seg2
    for s in range(seg2 // 2):
        fin_s, ini_s, dl, ro = (_u16(d, fin + 2 * s), _u16(d, ini + 2 * s), _u16(d, delta + 2 * s), _u16(d, rango + 2 * s))
        if ini_s > fin_s:
            continue
        for c in range(ini_s, min(fin_s, 0xFFFE) + 1):
            if ro == 0:
                g = (c + dl) & 0xFFFF
            else:
                g = _u16(d, rango + 2 * s + ro + 2 * (c - ini_s))
                if g:
                    g = (g + dl) & 0xFFFF
            if g:
                yield c, g


def _cmap_formato_12(d, sub):
    """(código, glifo) de una subtabla formato 12 (grupos de 32 bits)."""
    for i in range(struct.unpack_from(">I", d, sub + 12)[0]):
        desde, hasta, g0 = struct.unpack_from(">III", d, sub + 16 + 12 * i)
        if hasta < desde or hasta > 0x10FFFF:
            raise ValueError("un grupo del cmap se sale de Unicode")
        for c in range(desde, hasta + 1):
            g = g0 + c - desde
            if g:
                yield c, g


def _cmap(datos, tablas):
    """{código: glifo}: subtablas Unicode (plataforma 0 o 3) de formato 4 o
    12; la primera que trae un código gana y el glifo 0 es «sin glifo»."""
    base, _largo = tablas["cmap"]
    out = {}
    for i in range(_u16(datos, base + 2)):
        plataforma, _codificacion, rel = struct.unpack_from(">HHI", datos, base + 4 + 8 * i)
        if plataforma not in (0, 3):
            continue
        formato = _u16(datos, base + rel)
        if formato == 4:
            pares = _cmap_formato_4(datos, base + rel)
        elif formato == 12:
            pares = _cmap_formato_12(datos, base + rel)
        else:
            continue
        for c, g in pares:
            out.setdefault(c, g)
    return out


def _medidas(datos):
    tablas = _directorio(datos)
    for etiqueta in ("head", "hhea", "hmtx", "cmap"):
        if etiqueta not in tablas:
            raise ValueError(f"falta la tabla {etiqueta}")
    upem = _u16(datos, tablas["head"][0] + 18)
    hhea = tablas["hhea"][0]
    asc, desc = struct.unpack_from(">hh", datos, hhea + 4)
    n_metricas = _u16(datos, hhea + 34)
    hmtx, largo_hmtx = tablas["hmtx"]
    if upem == 0 or n_metricas == 0 or 4 * n_metricas > largo_hmtx:
        raise ValueError("las medidas de la fuente son inválidas")
    avances = {}
    for c, g in _cmap(datos, tablas).items():
        avances[c] = _u16(datos, hmtx + 4 * (g if g < n_metricas else n_metricas - 1))
    return {"upem": upem, "asc": asc, "desc": -desc, "avances": avances}


def leer_ttf(ruta):
    """{"upem", "asc", "desc", "avances": {código: avance}} de una TTF, en
    unidades de la fuente (`desc` positivo: −descender de `hhea`). Los glifos
    más allá de `numberOfHMetrics` heredan el último avance. Una TTF que no
    se puede leer es `ValueError` con el nombre del archivo."""
    with open(ruta, "rb") as f:
        datos = f.read()
    try:
        return _medidas(datos)
    except (ValueError, struct.error, IndexError) as e:
        raise ValueError(f"{os.path.basename(ruta)}: no se pudo leer como TTF ({e}).") from None


# --- la tabla tipográfica -----------------------------------------------------

def tramos(avances):
    """{código: avance} → [[inicio, [avance, …]], …]: los códigos consecutivos
    van juntos y los tramos salen ordenados."""
    out = []
    for c in sorted(avances):
        if out and c == out[-1][0] + len(out[-1][1]):
            out[-1][1].append(avances[c])
        else:
            out.append([c, [avances[c]]])
    return out


def _en_repertorio(c):
    return any(a <= c <= b for a, b in REPERTORIO)


def _ficha(ruta):
    t = leer_ttf(ruta)
    return {"upem": t["upem"], "asc": t["asc"], "desc": t["desc"],
            "avances": tramos({c: a for c, a in t["avances"].items() if _en_repertorio(c)})}


def generar_tabla():
    """La tabla que lee el navegador, sacada de las TTF de hoy. `emoji` es
    `None` si no está el archivo de emojis."""
    tabla = {"version": 1, "repertorio": [list(r) for r in REPERTORIO],
             "fuentes": {f["id"]: _ficha(os.path.join(FONTS_DIR, f["id"] + ".ttf")) for f in catalogo()},
             "emoji": None}
    if hay_emoji():
        tabla["emoji"] = {"id": EMOJI_ID, **_ficha(RUTA_EMOJI)}
    return tabla


def escribir_tabla():
    """Escribe `generar_tabla()` en `RUTA_TABLA` (compacta, claves ordenadas,
    estable entre corridas). Devuelve los bytes escritos."""
    texto = json.dumps(generar_tabla(), ensure_ascii=False, sort_keys=True, indent=None, separators=(",", ":")) + "\n"
    os.makedirs(os.path.dirname(RUTA_TABLA), exist_ok=True)
    with open(RUTA_TABLA, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    return len(texto.encode("utf-8"))


@functools.lru_cache(maxsize=None)
def cargar_tabla():
    """La tabla guardada, leída una vez. La copia sale con `emoji: None` con
    `EDITOR_SIN_EMOJI=1` (la válvula si la fuente de emojis diera problemas en
    el servidor) y cuando el archivo de la fuente no está (`hay_emoji()`: un
    despliegue que lo perdió): así la maqueta del render y la de la página, que
    leen la misma tabla, coinciden — los dos dejan de ofrecer emojis. Lo que
    devuelve es compartido: no se modifica. Quien parche `RUTA_EMOJI` o la
    válvula tiene que vaciar la caché (`cargar_tabla.cache_clear()`)."""
    with open(RUTA_TABLA, encoding="utf-8") as f:
        tabla = json.load(f)
    if os.environ.get("EDITOR_SIN_EMOJI") == "1" or not hay_emoji():
        tabla = {**tabla, "emoji": None}
    return tabla


# --- emojis por capas (spec 5c, D6.8; ruling R1) ------------------------------

def _derivar_sin_color(datos):
    """La fuente de emojis sin `COLR`/`CPAL` y con un `cmap` formato 12 de UN
    grupo: el código `PUA_CAPAS + g` es el glifo `g`. Así cada capa se dibuja
    como un glifo cualquiera (solo contornos). Las demás tablas pasan tal cual;
    el directorio sale en orden de etiqueta y cada tabla alineada a 4 bytes.
    Las sumas de verificación quedan en 0: FreeType no las comprueba."""
    tablas = _directorio(datos)
    n_glifos = _u16(datos, tablas["maxp"][0] + 4)
    cuerpos = {e: datos[d:d + l] for e, (d, l) in tablas.items() if e not in _SIN_COLOR}
    subtabla = struct.pack(">HHIII", 12, 0, 28, 0, 1) + struct.pack(">III", PUA_CAPAS, PUA_CAPAS + n_glifos - 1, 0)
    cuerpos["cmap"] = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 10, 12) + subtabla
    etiquetas = sorted(cuerpos)
    n = len(etiquetas)
    pot = 1
    while pot * 2 <= n:
        pot *= 2
    rango_busqueda = 16 * pot
    cabecera = datos[:4] + struct.pack(">HHHH", n, rango_busqueda, pot.bit_length() - 1, 16 * n - rango_busqueda)
    directorio, cuerpo = b"", b""
    desde = 12 + 16 * n
    for e in etiquetas:
        b = cuerpos[e]
        directorio += struct.pack(">4sIII", e.encode("latin-1"), 0, desde + len(cuerpo), len(b))
        cuerpo += b + b"\0" * (-len(b) % 4)
    return cabecera + directorio + cuerpo


@functools.lru_cache(maxsize=None)
def fuente_emoji_capas():
    """Bytes de la fuente de emojis derivada para dibujar capas (ver
    `_derivar_sin_color`); `ImageFont.truetype(io.BytesIO(...), tam)` la abre.
    Sin el archivo de emojis lanza `FileNotFoundError`: quien la pide mira
    `hay_emoji()` antes."""
    with open(RUTA_EMOJI, "rb") as f:
        return _derivar_sin_color(f.read())


def _glifos_sin_area(datos, tablas, glifos):
    """Cuáles de `glifos` no tienen tinta posible: un contorno vacío o una
    astilla con una caja de ancho o alto 0. No se ven, pero Pillow lanza
    «Bitmap missing for glyph» al dibujar algunas de ellas en ciertos tamaños
    (Twemoji trae tres: 3276, 7886 y 8180), así que `emoji_capas` no las
    devuelve. Sin `glyf`/`loca` (otra clase de fuente) no se descarta nada."""
    if "glyf" not in tablas or "loca" not in tablas:
        return set()
    largo_corto = struct.unpack_from(">h", datos, tablas["head"][0] + 50)[0] == 0
    loca, glyf = tablas["loca"][0], tablas["glyf"][0]
    sin_area = set()
    for g in glifos:
        if largo_corto:
            a, b = (2 * v for v in struct.unpack_from(">HH", datos, loca + 2 * g))
        else:
            a, b = struct.unpack_from(">II", datos, loca + 4 * g)
        if a == b:
            sin_area.add(g)
            continue
        _contornos, x0, y0, x1, y1 = struct.unpack_from(">hhhhh", datos, glyf + a)
        if x0 == x1 or y0 == y1:
            sin_area.add(g)
    return sin_area


def _leer_indice(datos):
    tablas = _directorio(datos)
    cmap = _cmap(datos, tablas)
    if "COLR" not in tablas or "CPAL" not in tablas:
        return cmap, {}
    o, l = tablas["CPAL"]
    cpal = datos[o:o + l]
    _version, n_entradas, _n_paletas, _n_colores, desde_colores = struct.unpack_from(">HHHHI", cpal, 0)
    paleta0 = _u16(cpal, 12)
    colores = []
    for i in range(n_entradas):
        b, g, r, a = struct.unpack_from(">BBBB", cpal, desde_colores + 4 * (paleta0 + i))
        colores.append((r, g, b, a))
    o, l = tablas["COLR"]
    colr = datos[o:o + l]
    _version, n_bases, desde_bases, desde_capas, _n_capas = struct.unpack_from(">HHIIH", colr, 0)
    crudas = {}
    for i in range(n_bases):
        glifo, primera, cuantas = struct.unpack_from(">HHH", colr, desde_bases + 6 * i)
        crudas[glifo] = [struct.unpack_from(">HH", colr, desde_capas + 4 * (primera + k)) for k in range(cuantas)]
    sin_area = _glifos_sin_area(datos, tablas, {g for capas in crudas.values() for g, _i in capas})
    bases = {}
    for glifo, capas in crudas.items():
        bases[glifo] = tuple((g, colores[i] if i < len(colores) else None) for g, i in capas if g not in sin_area)
    return cmap, bases


@functools.lru_cache(maxsize=None)
def _indice_capas(ruta):
    """(cmap, bases) de la fuente de emojis: `cmap` {código: glifo} y `bases`
    {glifo base: ((glifo de la capa, (r, g, b, a) | None), …)} con la tabla
    `COLR` v0 y la paleta 0 de `CPAL` (BGRA en el archivo, RGBA aquí). El
    índice de paleta 0xFFFF — «el color del texto» — queda en `None`. Las
    capas sin área (ver `_glifos_sin_area`) no entran. Se lee una vez por
    archivo."""
    with open(ruta, "rb") as f:
        datos = f.read()
    try:
        return _leer_indice(datos)
    except (ValueError, struct.error, IndexError) as e:
        raise ValueError(f"{os.path.basename(ruta)}: no se pudieron leer sus capas de color ({e}).") from None


def emoji_capas(cp):
    """Las capas de color del emoji `cp`: [(glifo de la capa, (r, g, b, a) | None)],
    de abajo hacia arriba, con el color en RGBA y `None` cuando la capa toma el
    color del texto. `None` si `cp` no es un emoji de capas o no hay archivo."""
    if not hay_emoji():
        return None
    cmap, bases = _indice_capas(RUTA_EMOJI)
    capas = bases.get(cmap.get(cp))
    return list(capas) if capas else None


if __name__ == "__main__":
    print(f"{RUTA_TABLA}: {escribir_tabla()} bytes")
