"""La maqueta del texto (spec editor capa 5c, D5): dado un texto, su estilo y la
tabla tipográfica (`fuentes.cargar_tabla()`), decide qué caracteres salen, dónde
se parte cada línea, qué tan grande es la caja y dónde va cada letra.

Es la REFERENCIA de `static/editor/tipografia.js`, que hace lo mismo en el
navegador con los mismos números: el render del servidor (Pillow) y la vista
previa dibujan los dos desde esta maqueta, y `tests/fixtures/tipografia_casos.json`
exige que den lo MISMO, sin tolerancia. Por eso:

- las operaciones de coma flotante van en el mismo orden en los dos motores y
  se acumulan letra por letra (ni `sum()`, que desde Python 3.12 compensa los
  errores de redondeo y JS no, ni `max()` sobre listas armadas de otra forma);
- se recorren puntos de código (`for ch in texto`; en JS `for (const ch of
  texto)`) y las palabras se separan SOLO por U+0020: ni `split()` ni `\\s`,
  que no cubren los mismos caracteres en Python y en JS;
- el redondeo de orígenes es «medio hacia arriba» (`floor(v + 0.5)`);
- los espacios que cuentan como tales son `ESPACIOS`, escritos enteros en los
  dos motores (el `isspace` de Python y el `\\s` de JS no coinciden).

La tabla que se recibe es compartida (`cargar_tabla` la guarda): no se modifica.
Se indexa una vez por objeto, perezosamente por fuente. No hace falta Pillow ni
red: es aritmética sobre la tabla."""
import collections
import math
import threading

from final_edition.documento import FORMATOS

SEPARADOR = " "
FACTOR_MAX = 4                 # el lienzo del texto se dibuja a lo más a 4× (D8)
LADO_MAX_PNG = 4096            # y ningún lado pasa de 4096 px
SELECTORES = (0xFE0E, 0xFE0F)  # selectores de variante: los dos valores, no un rango
TONOS = (0x1F3FB, 0x1F3FF)     # modificadores de tono de piel
KEYCAP = 0x20E3
ZWJ = 0x200D
ETIQUETAS = (0xE0020, 0xE007F)
REGIONALES = (0x1F1E6, 0x1F1FF)

# Desde aquí un código es «pictograma» (D5.1: tras una unión se quita el siguiente) y la fuente
# de emojis va primero (D5.3). Los espacios no son pictogramas.
DESDE_PICTOGRAMA = 0x2190

# Los caracteres que `str.isspace()` da por espacio: la lista entera, para que JS use la misma
# (`test_la_lista_de_espacios_es_la_de_isspace` la compara con Python).
ESPACIOS = (9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199,
            8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288)
_ESPACIOS = frozenset(ESPACIOS)

# Las medidas de la caja son las de `rasterizar` (que importará a este módulo, no al revés):
# `test_las_medidas_de_la_caja_son_las_del_rasterizador` las compara.
MARGEN_PX = 4
TAMANO_MIN_PX = 8

# La unión (ZWJ), los selectores de variante y el tecla-encerrada: lo que `sin_glifos_v1`
# quita junto con el carácter quitado que los precede.
_UNIONES_V1 = frozenset((ZWJ, SELECTORES[0], SELECTORES[1], KEYCAP))


def es_v2(estilo):
    return (estilo or {}).get("version") == 2


def redondear(v):
    """Medio hacia arriba (`geometria._redondear`, el `Math.round` del navegador)."""
    return int(math.floor(v + 0.5))


# --- la tabla, indexada una vez ----------------------------------------------------

_INDICES = collections.OrderedDict()   # id(tabla) -> (tabla, {clave: {código: avance}})
_MAX_INDICES = 8
_CANDADO = threading.Lock()


def _avances(tabla, clave, ficha):
    """{código: avance} de `ficha`, armado una vez por (tabla, clave). La entrada
    guarda la tabla misma, así su `id()` no se reusa mientras el índice viva."""
    with _CANDADO:
        entrada = _INDICES.get(id(tabla))
        if entrada is None or entrada[0] is not tabla:
            entrada = (tabla, {})
            _INDICES[id(tabla)] = entrada
            while len(_INDICES) > _MAX_INDICES:
                _INDICES.popitem(last=False)
        else:
            _INDICES.move_to_end(id(tabla))
        indice = entrada[1].get(clave)
        if indice is None:
            indice = {}
            for inicio, lista in ficha["avances"]:
                for i, a in enumerate(lista):
                    indice[inicio + i] = a
            entrada[1][clave] = indice
        return indice


class _Contexto:
    """Lo que hace falta para medir con una fuente de texto y, si la hay, la de emojis."""
    __slots__ = ("upem", "asc", "desc", "av_t", "upem_e", "av_e")

    def __init__(self, tabla, fuente):
        ficha = (tabla.get("fuentes") or {}).get(fuente)
        if ficha is None:
            raise ValueError(f"La fuente {fuente!r} no está en la tabla tipográfica.")
        self.upem, self.asc, self.desc = ficha["upem"], ficha["asc"], ficha["desc"]
        self.av_t = _avances(tabla, ("t", fuente), ficha)
        emoji = tabla.get("emoji")
        self.upem_e = emoji["upem"] if emoji else None
        self.av_e = _avances(tabla, ("e",), emoji) if emoji else None

    def fuente_de(self, cp):
        # espacio, espacio duro y salto: siempre la del texto (la de emojis no se usa para ellos)
        if cp == 0x20 or cp == 0xA0 or cp == 0x0A:
            return "texto"
        if self.av_e is not None and cp >= DESDE_PICTOGRAMA and cp in self.av_e:
            return "emoji"
        if cp in self.av_t:
            return "texto"
        if self.av_e is not None and cp in self.av_e:
            return "emoji"
        return None

    def avance(self, cp, fuente, tam):
        """Lo que mide el carácter, en px, con la tabla de su fuente (0 si ninguna lo cubre)."""
        if fuente == "texto":
            a = self.av_t.get(cp)
            if a is None and cp == 0xA0:
                a = self.av_t.get(0x20)         # un espacio duro sin avance propio mide como el espacio
            return 0 if a is None else a * tam / self.upem
        if fuente == "emoji":
            return self.av_e[cp] * tam / self.upem_e
        return 0


def fuente_de(cp, fuente, tabla):
    """De qué fuente sale el código `cp` (D5.3): `"emoji"` si es de U+2190 en adelante
    y la fuente de emojis lo tiene (así «❤», que Inter trae como dibujo de un color,
    sale como el emoji rojo; «→», «★» o «✓» siguen en la del texto, porque la de
    emojis no los trae); si no `"texto"` si la fuente del texto lo tiene; si no
    `"emoji"` si la de emojis lo tiene; si no `None` (`limpiar` lo quita). Espacio,
    espacio duro y salto de línea son siempre `"texto"`."""
    return _Contexto(tabla, fuente).fuente_de(cp)


# --- qué sale -----------------------------------------------------------------------

def _es_pictograma(cp):
    return cp >= DESDE_PICTOGRAMA and cp not in _ESPACIOS


def simplificar(texto):
    """(texto, simplificado) (D5.1). Quita los selectores de variante (sin contar como
    cambio: «❤️» pasa a «❤» sin aviso), los tonos de piel, el «keycap», las etiquetas y
    los indicadores regionales (las banderas), y en una secuencia unida con ZWJ se
    queda con el primer pictograma: quita la unión y el pictograma que sigue.
    `simplificado` es verdadero si quitó algo visible. Una unión suelta se quita en
    silencio. Recorre puntos de código."""
    salida = []
    simplificado = False
    unido = False
    for ch in texto:
        cp = ord(ch)
        if cp == SELECTORES[0] or cp == SELECTORES[1]:
            continue
        if cp == ZWJ:
            unido = True
            continue
        if (TONOS[0] <= cp <= TONOS[1] or cp == KEYCAP or ETIQUETAS[0] <= cp <= ETIQUETAS[1]
                or REGIONALES[0] <= cp <= REGIONALES[1]):
            simplificado = True
            continue
        if unido:
            unido = False
            if _es_pictograma(cp):
                simplificado = True
                continue
        salida.append(ch)
    return "".join(salida), simplificado


def _juntar(linea):
    """Los espacios repetidos de una línea en uno y ninguno en los bordes (solo U+0020: el
    espacio duro es intencional)."""
    return SEPARADOR.join(p for p in linea.split(SEPARADOR) if p)


def limpiar(texto, fuente, tabla):
    """{"texto", "quitados", "simplificado"} (D5.2): el tabulador pasa a espacio, `\\r\\n` y
    `\\r` a `\\n`, se simplifican los emojis (`simplificar`), se quita todo carácter que ni la
    fuente del texto ni la de emojis cubren (menos el espacio, el espacio duro y `\\n`) y, en
    cada línea, se juntan los espacios repetidos y se quitan los de los bordes. `quitados`
    son los caracteres quitados por falta de cobertura, sin repetir y en orden de aparición
    (para el aviso de la página)."""
    ctx = _Contexto(tabla, fuente)
    t = str(texto or "").replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n")
    t, simplificado = simplificar(t)
    quedan, quitados = [], []
    for ch in t:
        if ctx.fuente_de(ord(ch)) is None:
            if ch not in quitados:
                quitados.append(ch)
        else:
            quedan.append(ch)
    texto_limpio = "\n".join(_juntar(linea) for linea in "".join(quedan).split("\n"))
    return {"texto": texto_limpio, "quitados": quitados, "simplificado": simplificado}


def _recortar(s):
    """`s.strip()` con `ESPACIOS` (el mismo recorte en los dos motores)."""
    a, b = 0, len(s)
    while a < b and ord(s[a]) in _ESPACIOS:
        a += 1
    while b > a and ord(s[b - 1]) in _ESPACIOS:
        b -= 1
    return s[a:b]


def _juntar_v1(linea):
    """`re.sub(r"[ \\t]{2,}", " ", linea).strip()` de `rasterizar.sin_glifos_faltantes`: una
    corrida de dos o más espacios o tabuladores pasa a un espacio; uno solo se queda como está."""
    salida = []
    i, n = 0, len(linea)
    while i < n:
        if linea[i] == " " or linea[i] == "\t":
            j = i
            while j < n and (linea[j] == " " or linea[j] == "\t"):
                j += 1
            if j - i >= 2:
                salida.append(" ")
            else:
                salida.append(linea[i])
            i = j
        else:
            salida.append(linea[i])
            i += 1
    return _recortar("".join(salida))


def sin_glifos_v1(texto, fuente, tabla):
    """`texto` sin los caracteres que la fuente del texto no trae, igual que
    `rasterizar.sin_glifos_faltantes` pero con la cobertura de la tabla (el navegador no
    tiene Pillow): v1 no conoce la fuente de emojis. La unión, los selectores y el
    «keycap» se quitan junto con el carácter quitado que los precede (👨‍👩‍👧 se va entero);
    si quitó algo, sin los espacios dobles ni los de los bordes de cada línea; si no, el
    texto tal cual. Un carácter fuera del repertorio de la tabla cuenta como no cubierto
    (Pillow sí dibujaría uno de otro bloque que la fuente tenga: v1 solo lo usa para
    textos en español, inglés y portugués)."""
    texto = str(texto or "")
    av = _Contexto(tabla, fuente).av_t
    quedan, quitado = [], False
    for ch in texto:
        cp = ord(ch)
        conservar = (not quitado if cp in _UNIONES_V1 else True) and (cp in _ESPACIOS or cp in av)
        if conservar:
            quedan.append(ch)
        quitado = not conservar
    if len(quedan) == len(texto):
        return texto
    return "\n".join(_juntar_v1(linea) for linea in "".join(quedan).split("\n"))


# --- cuánto mide y dónde se parte ----------------------------------------------------

def _ancho(texto, ctx, tam):
    total = 0.0
    for ch in texto:
        cp = ord(ch)
        total += ctx.avance(cp, ctx.fuente_de(cp), tam)
    return total


def ancho(texto, fuente, tam, tabla):
    """Lo que mide `texto` a `tam` px (D5.4): la suma, en orden, de `avance × tam / upem` de
    cada carácter con la tabla de su fuente (la del texto o la de emojis). Sin kerning ni
    ligaduras en ningún motor. Un carácter sin cobertura cuenta 0 (`limpiar` ya lo quitó)."""
    return _ancho(texto, _Contexto(tabla, fuente), tam)


def _ajustar(texto, ctx, tam, ancho_max_px):
    lineas = []
    for parrafo in str(texto or "").split("\n"):
        actual = ""
        for palabra in parrafo.split(SEPARADOR):
            if not palabra:
                continue
            candidata = actual + SEPARADOR + palabra if actual else palabra
            if actual and ancho_max_px and _ancho(candidata, ctx, tam) > ancho_max_px:
                lineas.append(actual)
                actual = palabra
            else:
                actual = candidata
        lineas.append(actual)
    return lineas or [""]


def ajustar(texto, fuente, tam, ancho_max_px, tabla):
    """Las líneas de `texto` (D5.5): ajuste voraz por palabras (como `rasterizar.ajustar_lineas`)
    pero las palabras se separan SOLO por U+0020 (el espacio duro no parte) y la medida es
    `ancho`. Línea nueva cuando la candidata mediría MÁS que `ancho_max_px`; una palabra más
    ancha que el límite va sola; sin límite cada párrafo (`\\n`) es una línea; `[""]` si no
    hay nada."""
    return _ajustar(texto, _Contexto(tabla, fuente), tam, ancho_max_px)


# --- las medidas de la caja (las fórmulas de texto.js, redondeo al par) ----------------

def _px(fraccion, base):
    return int(round(float(fraccion or 0) * base))


def medidas_texto(estilo, formato):
    """Las medidas del texto en px para un lienzo `formato` (las de `rasterizar.png_texto` y
    `texto.js::medidasTexto`): tamaño, interlineado extra, grosor del contorno, sombra, relleno
    del fondo, ancho máximo, ancho mínimo del fondo y radio, con el redondeo de `round()`."""
    ancho_l, alto_l = FORMATOS[formato]
    tam = max(TAMANO_MIN_PX, _px(estilo.get("tamano", 0.04), alto_l))
    contorno = estilo.get("contorno") or None
    sombra = estilo.get("sombra") or None
    fondo = estilo.get("fondo") or None
    return {
        "tam": tam,
        "espaciado": _px(float(estilo.get("interlineado") or 1.1) - 1.0, tam),
        "grosor": _px(contorno.get("grosor"), alto_l) if contorno else 0,
        "sdx": _px(sombra.get("dx"), alto_l) if sombra else 0,
        "sdy": _px(sombra.get("dy"), alto_l) if sombra else 0,
        "pad_x": _px(fondo.get("relleno_x"), alto_l) if fondo else 0,
        "pad_y": _px(fondo.get("relleno_y"), alto_l) if fondo else 0,
        "ancho_max_px": _px(estilo["ancho_max"], ancho_l) if estilo.get("ancho_max") else None,
        "fondo_ancho_px": _px(fondo["ancho"], ancho_l) if fondo and fondo.get("ancho") else 0,
        "radio": _px(fondo.get("radio"), alto_l) if fondo else 0,
    }


def caja_texto(m, tw, th):
    """La caja del PNG a partir del bloque medido (`tw` × `th`, ya con el grosor del
    contorno): relleno del fondo, ancho mínimo del fondo y margen para contorno y sombra."""
    caja_w = tw + 2 * m["pad_x"]
    if m["fondo_ancho_px"]:
        caja_w = max(caja_w, m["fondo_ancho_px"])
    caja_h = th + 2 * m["pad_y"]
    margen = MARGEN_PX + max(abs(m["sdx"]), abs(m["sdy"]))
    radio = min(m["radio"], caja_h // 2, caja_w // 2)
    return {"caja_w": caja_w, "caja_h": caja_h, "margen": margen, "radio": radio,
            "ancho": int(caja_w + 2 * margen), "alto": int(caja_h + 2 * margen)}


# --- la maqueta ----------------------------------------------------------------------

def maquetar(texto, estilo, formato, tabla, factor=1):
    """La maqueta de `texto` con `estilo` para un lienzo `formato` (D5.6), a escala 1: el
    `factor` (D8) solo se anota, lo aplica el dibujo.

    {"texto", "quitados", "simplificado": lo que dio `limpiar`,
     "tam", "ancho_px", "alto_px": enteros (lo que `preparar_rutas` estampa y `geometria.caja` coloca),
     "factor", "margen", "caja_w", "caja_h", "radio",
     "lineas": [{"texto", "x", "base", "ancho"}],
     "letras": [{"cp", "x", "base", "fuente": "texto" | "emoji"}]}

    `x` es la esquina izquierda de la línea o de la letra y `base` la línea de base, en px de
    la caja. Las letras no llevan espacios (no se dibujan) y cada `x` acumula los avances
    desde la `x` de su línea."""
    estilo = estilo or {}
    fuente = estilo.get("fuente")
    limpio = limpiar(texto, fuente, tabla)
    ctx = _Contexto(tabla, fuente)
    m = medidas_texto(estilo, formato)
    tam, grosor = m["tam"], m["grosor"]
    textos = _ajustar(limpio["texto"], ctx, tam, m["ancho_max_px"])
    anchos = [_ancho(t, ctx, tam) for t in textos]
    asc_px = ctx.asc * tam / ctx.upem
    desc_px = ctx.desc * tam / ctx.upem
    paso = tam + m["espaciado"]
    mayor = 0.0
    for w in anchos:
        if w > mayor:
            mayor = w
    tw = math.ceil(mayor) + 2 * grosor
    th = math.ceil(asc_px + desc_px + (len(textos) - 1) * paso) + 2 * grosor
    caja = caja_texto(m, tw, th)
    margen, caja_w = caja["margen"], caja["caja_w"]
    alineacion = estilo.get("alineacion") or "centro"
    lineas, letras = [], []
    for i, t in enumerate(textos):
        w = anchos[i]
        if alineacion == "izquierda":
            x = margen + m["pad_x"] + grosor
        elif alineacion == "derecha":
            x = margen + caja_w - m["pad_x"] - grosor - w
        else:
            x = margen + (caja_w - w) / 2
        base = margen + m["pad_y"] + grosor + asc_px + i * paso
        lineas.append({"texto": t, "x": x, "base": base, "ancho": w})
        for ch in t:
            cp = ord(ch)
            f = ctx.fuente_de(cp)
            if cp != 0x20 and cp != 0xA0:
                letras.append({"cp": cp, "x": x, "base": base, "fuente": f})
            x += ctx.avance(cp, f, tam)
    return {"texto": limpio["texto"], "quitados": limpio["quitados"], "simplificado": limpio["simplificado"],
            "tam": tam, "ancho_px": caja["ancho"], "alto_px": caja["alto"], "factor": factor, "margen": margen,
            "caja_w": caja_w, "caja_h": caja["caja_h"], "radio": caja["radio"], "lineas": lineas, "letras": letras}


# --- la nitidez (D8) -----------------------------------------------------------------

def escala_max(clip):
    """La mayor escala que toma el clip: la de `transform.escala` (1.0 si no la trae) y la de
    cada `keyframes[k].transform.escala` que la trae (los demás keyframes heredan la base)."""
    clip = clip or {}

    def _escala(transform):
        v = (transform or {}).get("escala")
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    mayor = _escala(clip.get("transform"))
    if mayor is None:
        mayor = 1.0
    for kf in clip.get("keyframes") or []:
        v = _escala(kf.get("transform"))
        if v is not None and v > mayor:
            mayor = v
    return mayor


def factor_nitidez(escala, ancho_px, alto_px):
    """A cuántas veces su tamaño natural se dibuja el texto para que no se vea borroso cuando
    el clip se agranda: `min(FACTOR_MAX, max(1, ceil(escala)))`, bajado de a 1 mientras el
    lado mayor del PNG pase de `LADO_MAX_PNG` (nunca menos de 1)."""
    if not escala > 0:
        return 1
    f = FACTOR_MAX if escala >= FACTOR_MAX else min(FACTOR_MAX, max(1, math.ceil(escala)))
    while f > 1 and max(ancho_px, alto_px) * f > LADO_MAX_PNG:
        f -= 1
    return f
