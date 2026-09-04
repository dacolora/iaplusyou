"""
Cliente simple para Nano Banana (Gemini 2.5 Flash Image) — generación de imagen a
partir de una imagen de referencia + un prompt de texto. A diferencia de Higgsfield,
la API de Gemini responde la imagen directo en la misma llamada (sin lanzar+poll).

Requiere GEMINI_API_KEY en el .env (console.cloud.google.com / aistudio.google.com).
"""
import base64
import io
import os

import requests
from PIL import Image

import prompt_swap
from providers import aspect_ratio

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "gemini-2.5-flash-image"

COSTO_USD_POR_IMAGEN = 0.039

# Las fotos de producto del catálogo pesan 1-2MB cada una — mandar varias en una
# sola llamada (base64, todas juntas) es lo que causaba los timeouts de escritura.
# Achicarlas antes de mandarlas no pierde nada útil: Gemini no necesita resolución
# completa para identificar color/diseño de un calzado.
MAX_DIMENSION = 1024
CALIDAD_JPEG = 85


def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY en tu .env. Consíguela en aistudio.google.com/apikey"
        )
    return key


def _mime_type(url):
    low = url.lower()
    if low.endswith(".png"):
        return "image/png"
    if low.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _llamar(parts, timeout=150, intentos=3, aspect_ratio=None):
    """Manda las parts (texto + imágenes) a Gemini y devuelve los bytes de la
    primera imagen generada en la respuesta. Reintenta en timeouts/errores de
    conexión y en 400/500 — confirmado empíricamente que a veces la misma
    llamada con el mismo payload responde 400 una vez y 200 al reintentar sin
    cambiar nada; si el 400 es real (payload inválido) el reintento no lo
    arregla, pero al menos ahora el mensaje de error trae el detalle real de
    Google en vez de solo "400 Bad Request"."""
    url = f"{BASE_URL}/{MODEL}:generateContent?key={_api_key()}"
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio or "1:1",
            },
        },
    }
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            ultimo_error = e
            if intento == intentos:
                # Nunca incluir la excepción cruda ({e}) acá — su texto trae la
                # URL completa, con la API key como query param, y este mensaje
                # termina guardado en swaps.json (que sí se versiona en git).
                raise RuntimeError(
                    f"Nano Banana no respondió después de {intentos} intentos "
                    f"(problema de red, no del prompt): {type(e).__name__}"
                )
            continue
        except requests.exceptions.HTTPError as e:
            ultimo_error = e
            if intento == intentos:
                raise RuntimeError(
                    f"Nano Banana respondió {resp.status_code} después de {intentos} "
                    f"intentos: {resp.text[:500]}"
                )
            continue
    data = resp.json()

    candidatos = data.get("candidates") or []
    if not candidatos:
        raise RuntimeError(f"Nano Banana no devolvió candidatos: {data}")

    for part in candidatos[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])

    raise RuntimeError(f"Nano Banana no devolvió ninguna imagen en la respuesta: {data}")


def _comprimir(imagen_bytes):
    """Reescala a MAX_DIMENSION de lado más largo y reencoda como JPEG — reduce
    varios MB a unos cientos de KB sin perder lo que Gemini necesita ver."""
    img = Image.open(io.BytesIO(imagen_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    ancho, alto = img.size
    lado_mayor = max(ancho, alto)
    if lado_mayor > MAX_DIMENSION:
        factor = MAX_DIMENSION / lado_mayor
        img = img.resize((int(ancho * factor), int(alto * factor)), Image.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=CALIDAD_JPEG)
    return salida.getvalue()


def _parte_imagen_local(path):
    with open(path, "rb") as f:
        original = f.read()
    comprimida = _comprimir(original)
    data = base64.b64encode(comprimida).decode("utf-8")
    return {"inline_data": {"mime_type": "image/jpeg", "data": data}}


def generate_image(image_reference_url, prompt, negative_prompt=None, extra_params=None):
    """Descarga la imagen de referencia, se la manda a Gemini junto con el prompt, y
    devuelve los bytes de la imagen generada. Llamada síncrona — puede tardar varios
    segundos, pero no requiere polling."""
    ref = requests.get(image_reference_url, timeout=30)
    ref.raise_for_status()
    ref_b64 = base64.b64encode(_comprimir(ref.content)).decode("utf-8")

    texto = prompt
    if negative_prompt:
        texto += f"\n\nEvita explícitamente: {negative_prompt}"

    extra_params = extra_params or {}
    aspect_ratio = extra_params.get("aspect_ratio") or "9:16"

    parts = [
        {"text": texto},
        {"inline_data": {"mime_type": "image/jpeg", "data": ref_b64}},
    ]
    return _llamar(parts, aspect_ratio=aspect_ratio)


# El prompt de swap se mudó a prompt_swap.py: estaba duplicado acá, en
# providers/comparador_modelos.py y en tres ramas de dashboard.py, todos con
# la palabra "calzado" incrustada — por eso agregar una cobija obligaba a
# editar cinco textos casi iguales.


def swap_producto(foto_original_path, referencias_producto_paths, negative_prompt=None, tipo=None):
    """Reemplaza SOLO el calzado de foto_original_path por el producto mostrado en
    referencias_producto_paths (hasta 6), manteniendo todo lo demás idéntico —
    incluido el encuadre: se detecta el aspect ratio real de la foto original y
    se lo pedimos a Gemini explícitamente (si no, generaba en 1:1 por default y
    recortaba la foto). Devuelve los bytes de la imagen generada."""
    referencias = referencias_producto_paths[:2]
    referencias_lista = "\n".join(
        f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)." for i in range(len(referencias))
    )
    # El prompt lo arma prompt_swap según el TIPO de producto: un calzado y una
    # cobija no se editan con las mismas reglas (dónde va, cómo se cuenta, qué
    # significa que quede bien puesto).
    texto = prompt_swap.prompt_imagen(tipo, referencias_lista)
    if negative_prompt:
        texto += f"\n\nEvita explícitamente: {negative_prompt}"

    parts = [{"text": texto}, _parte_imagen_local(foto_original_path)]
    for ref in referencias:
        parts.append(_parte_imagen_local(ref))
    ratio = aspect_ratio.detectar_gemini(foto_original_path)
    return _llamar(parts, aspect_ratio=ratio)


def estimate_image():
    """Nano Banana no tiene endpoint de estimación — el precio por imagen es fijo y
    conocido de antemano."""
    return {"credits": None, "usd": COSTO_USD_POR_IMAGEN}
