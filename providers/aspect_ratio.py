"""
Detecta el aspect ratio real de la foto/video original que el usuario subió,
para pedirle a cada modelo que genere su salida con esas mismas proporciones —
en vez de dejar que el modelo elija su propio encuadre por default, que es lo
que causaba que el resultado saliera recortado/con zoom respecto al original.

Cada proveedor de imagen soporta esto distinto:
  - Gemini directo (Nano Banana) y Nano Banana vía fal.ai: solo aceptan un
    aspect ratio de una lista fija (bucket), no dimensiones exactas.
  - Qwen Image Edit Plus (fal.ai): acepta un {width, height} exacto.
"""
from PIL import Image

# Verificado empíricamente contra el endpoint real de Gemini (31 ago 2026):
# pedir un valor fuera de esta lista responde 400 con el enum completo.
GEMINI_ASPECT_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
    "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]

# Verificado contra la documentación oficial de fal.ai (fal-ai/nano-banana/edit).
FAL_NANO_BANANA_ASPECT_RATIOS = [
    "21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16",
]


def dimensiones(path_local):
    """Ancho, alto reales del archivo en path_local."""
    with Image.open(path_local) as img:
        return img.size


def mas_cercano(ancho, alto, opciones):
    """El string 'A:B' de `opciones` cuyo ratio ancho/alto está más cerca del
    de la imagen real."""
    ratio_real = ancho / alto

    def distancia(opcion):
        a, b = opcion.split(":")
        return abs((int(a) / int(b)) - ratio_real)

    return min(opciones, key=distancia)


def detectar_gemini(path_local):
    ancho, alto = dimensiones(path_local)
    return mas_cercano(ancho, alto, GEMINI_ASPECT_RATIOS)


def detectar_fal_nano_banana(path_local):
    ancho, alto = dimensiones(path_local)
    return mas_cercano(ancho, alto, FAL_NANO_BANANA_ASPECT_RATIOS)


def dimensiones_para_qwen(path_local, max_lado=1280):
    """Ancho/alto reales, escalados para no exceder max_lado en el lado
    mayor — Qwen acepta {width, height} exactos en vez de un bucket fijo."""
    ancho, alto = dimensiones(path_local)
    lado_mayor = max(ancho, alto)
    if lado_mayor > max_lado:
        factor = max_lado / lado_mayor
        ancho, alto = round(ancho * factor), round(alto * factor)
    return ancho, alto
