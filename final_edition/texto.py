"""Final Edition, capa 4a: texto en pantalla rasterizado con Pillow.

ffmpeg local/VPS no trae `drawtext` ni `subtitles` (sin libfreetype/libass),
así que cada elemento de texto se dibuja como un PNG RGBA con fondo
transparente, **recortado a su contenido** (más PAD_RECORTE px), y el render lo
sobreimprime con `overlay=x:y:enable='gte(t,ini)*lt(t,fin)'`. Cada entrada
devuelta lleva por eso `{"png", "inicio", "fin", "x", "y"}` con `x`/`y` la
esquina superior izquierda del PNG en coordenadas del frame. Recortar los PNG
(en vez de emitirlos a tamaño de frame) es lo que mantiene bajo el consumo de
memoria/CPU de ffmpeg con decenas de overlays.

Elementos:
- hook: `texto_pantalla` del bloque hook, SpaceGrotesk-Bold 88 px, centrado en
  el tercio superior con sombra, durante todo el bloque.
- subtítulos: las `palabras` (de voz.py) agrupadas en líneas de ≤ 4 palabras
  que quepan en `ancho - 2*MARGEN_SUB` (medido con la fuente; grupo nuevo
  también si hay un hueco > 0.8 s); si una sola palabra no cabe, la fuente de
  ese grupo se reduce hasta TAM_SUB_MIN. Por cada palabra un PNG de la línea
  con esa palabra en el color de acento y el resto en blanco, Inter-Bold
  64 px sobre caja negra 60 % alpha en el tercio inferior. Cada PNG se activa
  desde el inicio de la palabra hasta el inicio de la siguiente del grupo (la
  última: hasta su fin + 0.3 s, pero nunca más allá del inicio del grupo
  siguiente, para que nunca haya dos líneas a la vez).
  Si hubiera más de MAX_OVERLAYS_SUBTITULOS palabras, se cae a un PNG por
  LÍNEA (grupos de 6 palabras, todas en blanco) para no disparar el número de
  entradas del filtergraph.
- badge: `precio_texto` en píldora de acento arriba a la derecha, desde el
  inicio del bloque producto hasta el fin del bloque prueba.
- cta: tarjeta oscura redondeada (80 % del ancho) con el logo (opcional, máx.
  240 px) y el `texto_pantalla` del cta ajustado por ancho medido, durante el
  bloque cta.
"""
import os

from PIL import Image, ImageDraw, ImageFont

from final_edition.tipos import FUENTES

COLOR_ACENTO_DEFECTO = "#7c3aed"
MAX_PALABRAS_GRUPO = 4
MAX_PALABRAS_LINEA_DENSA = 6
HUECO_NUEVO_GRUPO_S = 0.8
COLA_ULTIMA_PALABRA_S = 0.3
MAX_OVERLAYS_SUBTITULOS = 120
LOGO_MAX_PX = 240
PAD_RECORTE = 8      # px alrededor del contenido al recortar el PNG
MARGEN_SUB = 60      # margen lateral mínimo de la caja de subtítulo (a 1080)
MARGEN_HOOK = 60

TAM_HOOK = 88
TAM_SUB = 64
TAM_SUB_MIN = 48
TAM_BADGE = 56
TAM_CTA = 72


def generar_overlays(guion, palabras, marca, carpeta, ancho=1080, alto=1920):
    """Genera los PNG y devuelve `{"hook", "subtitulos", "badge", "cta"}`;
    cada entrada es `{"png", "inicio", "fin", "x", "y"}` (badge puede ser None
    y subtitulos una lista, vacía si no hay palabras)."""
    os.makedirs(carpeta, exist_ok=True)
    marca = marca or {}
    acento = _color(marca.get("color_acento") or COLOR_ACENTO_DEFECTO)
    bloques = {b["rol"]: b for b in guion.get("bloques") or []}
    escala = ancho / 1080.0  # las medidas están pensadas para 1080x1920

    hook = bloques.get("hook") or {}
    ruta_hook = os.path.join(carpeta, "hook.png")
    x, y = _png_hook(hook.get("texto_pantalla") or "", ruta_hook, ancho, alto, escala)
    salida = {
        "hook": _entrada(ruta_hook, hook.get("inicio_s", 0), hook.get("fin_s", 0), x, y),
        "subtitulos": _subtitulos(palabras or [], acento, carpeta, ancho, alto, escala),
        "badge": None,
        "cta": None,
    }

    precio = guion.get("precio_texto")
    if precio:
        ruta_badge = os.path.join(carpeta, "badge.png")
        x, y = _png_badge(str(precio), acento, ruta_badge, ancho, alto, escala)
        producto = bloques.get("producto") or {}
        prueba = bloques.get("prueba") or producto
        salida["badge"] = _entrada(ruta_badge, producto.get("inicio_s", 0),
                                   prueba.get("fin_s", producto.get("fin_s", 0)), x, y)

    cta = bloques.get("cta") or {}
    ruta_cta = os.path.join(carpeta, "cta.png")
    x, y = _png_cta(cta.get("texto_pantalla") or "", marca.get("logo_path"), ruta_cta, ancho, alto, escala)
    salida["cta"] = _entrada(ruta_cta, cta.get("inicio_s", 0), cta.get("fin_s", 0), x, y)
    return salida


def _entrada(png, inicio, fin, x, y):
    return {"png": png, "inicio": inicio, "fin": fin, "x": int(x), "y": int(y)}


# --- subtítulos -------------------------------------------------------------

def agrupar_palabras(palabras, max_por_grupo=MAX_PALABRAS_GRUPO, ancho_max=None, fuente=None):
    """Grupos consecutivos de ≤ `max_por_grupo` palabras. Se abre grupo nuevo
    también cuando el hueco entre el fin de una y el inicio de la siguiente
    supera HUECO_NUEVO_GRUPO_S o cuando, con `ancho_max`/`fuente`, añadir la
    palabra haría que la línea medida supere `ancho_max` px (una palabra que
    por sí sola no cabe va en su propio grupo)."""
    medir = None
    if ancho_max is not None and fuente is not None:
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        espacio = d.textlength(" ", font=fuente)

        def medir(textos):
            return sum(d.textlength(t, font=fuente) for t in textos) + espacio * (len(textos) - 1)

    grupos, actual = [], []
    for p in palabras:
        if actual:
            nuevo = (len(actual) >= max_por_grupo
                     or p["inicio"] - actual[-1]["fin"] > HUECO_NUEVO_GRUPO_S)
            if not nuevo and medir is not None:
                nuevo = medir([q["texto"] for q in actual] + [p["texto"]]) > ancho_max
            if nuevo:
                grupos.append(actual)
                actual = []
        actual.append(p)
    if actual:
        grupos.append(actual)
    return grupos


def _ventanas(grupo, limite=None):
    """[(inicio, fin)] por palabra del grupo: hasta el inicio de la siguiente,
    la última hasta su fin + cola, sin pasar de `limite` (inicio del grupo
    siguiente) para que nunca se dibujen dos líneas a la vez."""
    ventanas = []
    for i, p in enumerate(grupo):
        if i + 1 < len(grupo):
            fin = grupo[i + 1]["inicio"]
        else:
            fin = p["fin"] + COLA_ULTIMA_PALABRA_S
            if limite is not None:
                fin = min(fin, limite)
        ventanas.append((round(float(p["inicio"]), 3), round(float(max(fin, p["inicio"])), 3)))
    return ventanas


def _fuente_grupo(grupo, fuente_base, ancho_max, escala):
    """Fuente del grupo: la base salvo que una palabra sola no quepa, en cuyo
    caso se reduce (hasta TAM_SUB_MIN) hasta que quepa."""
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    mas_ancha = max(d.textlength(p["texto"], font=fuente_base) for p in grupo)
    if mas_ancha <= ancho_max:
        return fuente_base
    tam = TAM_SUB
    fuente = fuente_base
    while tam > TAM_SUB_MIN:
        tam -= 2
        fuente = _fuente("texto", tam * escala)
        if max(d.textlength(p["texto"], font=fuente) for p in grupo) <= ancho_max:
            break
    return fuente


def _subtitulos(palabras, acento, carpeta, ancho, alto, escala):
    palabras = [p for p in palabras if (p.get("texto") or "").strip()]
    if not palabras:
        return []
    fuente_base = _fuente("texto", TAM_SUB * escala)
    pad_x, pad_y = int(36 * escala), int(24 * escala)
    # El PNG recortado mide texto + 2*pad_x + 2*PAD_RECORTE; debe caber en
    # ancho - 2*MARGEN_SUB.
    ancho_texto_max = ancho - 2 * int(MARGEN_SUB * escala) - 2 * pad_x - 2 * PAD_RECORTE

    denso = len(palabras) > MAX_OVERLAYS_SUBTITULOS
    max_grupo = MAX_PALABRAS_LINEA_DENSA if denso else MAX_PALABRAS_GRUPO
    grupos = agrupar_palabras(palabras, max_grupo, ancho_texto_max, fuente_base)

    entradas = []  # (textos, resaltada, ini, fin, fuente)
    for g, grupo in enumerate(grupos):
        limite = grupos[g + 1][0]["inicio"] if g + 1 < len(grupos) else None
        fuente = _fuente_grupo(grupo, fuente_base, ancho_texto_max, escala)
        textos = [p["texto"] for p in grupo]
        if denso:
            # Modo denso: un PNG por línea, sin resaltar.
            ini = round(float(grupo[0]["inicio"]), 3)
            fin = float(grupo[-1]["fin"]) + COLA_ULTIMA_PALABRA_S
            if limite is not None:
                fin = min(fin, limite)
            entradas.append((textos, None, ini, round(fin, 3), fuente))
        else:
            for k, (ini, fin) in enumerate(_ventanas(grupo, limite)):
                entradas.append((textos, k, ini, fin, fuente))

    # Deduplicación: ventanas idénticas (misma línea, mismo rango) se funden.
    resultado, vistos = [], {}
    for n, (textos, k, ini, fin, fuente) in enumerate(entradas):
        clave = (tuple(textos), ini, fin)
        if clave in vistos:
            continue
        if fin <= ini:
            continue
        ruta = os.path.join(carpeta, f"sub_{n:03d}.png")
        x, y = _png_subtitulo(textos, k, acento, fuente, ruta, ancho, alto, pad_x, pad_y, escala)
        vistos[clave] = True
        resultado.append(_entrada(ruta, ini, fin, x, y))
    return resultado


def _png_subtitulo(textos, resaltada, acento, fuente, ruta, ancho, alto, pad_x, pad_y, escala):
    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    espacio = _ancho_texto(d, " ", fuente)
    anchos = [_ancho_texto(d, t, fuente) for t in textos]
    total = sum(anchos) + espacio * (len(textos) - 1)
    alto_linea = int(fuente.size * 1.25)
    x0 = (ancho - total) // 2
    y0 = int(alto * 0.78) - alto_linea // 2
    d.rounded_rectangle(
        [x0 - pad_x, y0 - pad_y, x0 + total + pad_x, y0 + alto_linea + pad_y],
        radius=int(20 * escala), fill=(0, 0, 0, 153),
    )
    x = x0
    for i, (t, w) in enumerate(zip(textos, anchos)):
        color = acento if i == resaltada else (255, 255, 255, 255)
        d.text((x, y0), t, font=fuente, fill=color)
        x += w + espacio
    return _guardar_recortado(im, ruta)


# --- hook / badge / cta -----------------------------------------------------

def _png_hook(texto_hook, ruta, ancho, alto, escala):
    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fuente = _fuente("titulo", TAM_HOOK * escala)
    lineas = _ajustar(d, texto_hook, fuente, ancho - 2 * int(MARGEN_HOOK * escala))
    bloque = "\n".join(lineas)
    espaciado = int(12 * escala)
    bbox = d.multiline_textbbox((0, 0), bloque, font=fuente, spacing=espaciado, align="center")
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (ancho - w) // 2 - bbox[0]
    y = int(alto / 6) - h // 2 - bbox[1]
    sombra = int(6 * escala)
    d.multiline_text((x + sombra, y + sombra), bloque, font=fuente, fill=(0, 0, 0, 200),
                     spacing=espaciado, align="center")
    d.multiline_text((x, y), bloque, font=fuente, fill=(255, 255, 255, 255),
                     spacing=espaciado, align="center", stroke_width=int(3 * escala),
                     stroke_fill=(0, 0, 0, 220))
    return _guardar_recortado(im, ruta)


def _png_badge(precio, acento, ruta, ancho, alto, escala):
    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fuente = _fuente("texto", TAM_BADGE * escala)
    bbox = d.textbbox((0, 0), precio, font=fuente)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = int(40 * escala), int(22 * escala)
    margen = int(48 * escala)
    x1 = ancho - margen
    y0 = int(alto * 0.30)
    x0 = x1 - (w + 2 * pad_x)
    y1 = y0 + h + 2 * pad_y
    d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=acento)
    d.text((x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]), precio, font=fuente, fill=(255, 255, 255, 255))
    return _guardar_recortado(im, ruta)


def _png_cta(texto_cta, logo_path, ruta, ancho, alto, escala):
    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fuente = _fuente("titulo", TAM_CTA * escala)
    pad = int(64 * escala)
    card_w = int(ancho * 0.8)
    lineas = _ajustar(d, texto_cta, fuente, card_w - 2 * pad)
    bloque = "\n".join(lineas)
    espaciado = int(14 * escala)
    bbox = d.multiline_textbbox((0, 0), bloque, font=fuente, spacing=espaciado, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    logo = _cargar_logo(logo_path, int(LOGO_MAX_PX * escala))
    lh = logo.size[1] if logo else 0
    sep = int(40 * escala) if logo else 0

    card_h = th + lh + sep + 2 * pad
    cx0 = (ancho - card_w) // 2
    cy0 = (alto - card_h) // 2
    d.rounded_rectangle([cx0, cy0, cx0 + card_w, cy0 + card_h], radius=int(48 * escala),
                        fill=(18, 18, 24, 235))
    y = cy0 + pad
    if logo:
        im.alpha_composite(logo, ((ancho - logo.size[0]) // 2, y))
        y += lh + sep
    d.multiline_text(((ancho - tw) // 2 - bbox[0], y - bbox[1]), bloque, font=fuente,
                     fill=(255, 255, 255, 255), spacing=espaciado, align="center")
    return _guardar_recortado(im, ruta)


def _cargar_logo(logo_path, max_px):
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        with Image.open(logo_path) as src:
            logo = src.convert("RGBA")
            logo.load()
    except OSError:
        return None
    logo.thumbnail((max_px, max_px), Image.LANCZOS)
    return logo


# --- utilidades -------------------------------------------------------------

def _guardar_recortado(im, ruta, pad=PAD_RECORTE):
    """Guarda `im` recortada a su contenido (alpha > 0) más `pad` px, sin
    salirse del frame. Devuelve (x, y) de la esquina superior izquierda del
    recorte en coordenadas del frame. Una imagen vacía se guarda como 1x1."""
    bbox = im.getbbox()
    if not bbox:
        bbox = (0, 0, 1, 1)
        pad = 0
    x0, y0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    x1, y1 = min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad)
    im.crop((x0, y0, x1, y1)).save(ruta)
    return x0, y0


def _ajustar(d, texto_libre, fuente, ancho_max):
    """Ajuste voraz por palabras: línea nueva cuando la medida con `fuente`
    superaría `ancho_max` px (una palabra más ancha que el límite va sola)."""
    lineas, actual = [], ""
    for palabra in (texto_libre or "").split():
        candidata = f"{actual} {palabra}".strip()
        if actual and d.textlength(candidata, font=fuente) > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = candidata
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _fuente(clave, tam):
    return ImageFont.truetype(FUENTES[clave], int(round(tam)))


def _ancho_texto(d, t, fuente):
    return int(d.textlength(t, font=fuente))


def _color(valor):
    """'#rrggbb' -> (r, g, b, 255); tuplas se devuelven tal cual."""
    if isinstance(valor, (tuple, list)):
        return tuple(valor) if len(valor) == 4 else tuple(valor) + (255,)
    v = str(valor).strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        v = COLOR_ACENTO_DEFECTO.lstrip("#")
        r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    return (r, g, b, 255)
