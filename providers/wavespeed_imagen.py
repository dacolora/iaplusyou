"""
Edición de IMAGEN vía WaveSpeed AI, y mejora de calidad como segunda pasada.

Dos cosas distintas que suelen confundirse:

1. `nano-banana-pro/edit-ultra` EDITA (pone el producto) y además saca la imagen
   directo en 4k/8k. Es un solo paso, más caro.
2. `bria/increase-resolution` NO edita: solo agranda una imagen ya hecha. Se usa
   como segunda pasada sobre el resultado de CUALQUIER modelo de swap.

La distinción importa para elegir el upscaler: casi todos los del catálogo de
WaveSpeed son generativos (inventan detalle, y los Clarity hasta exponen un
parámetro `creativity` para eso). Acá no sirve ninguno de esos: la foto tiene
que seguir siendo la misma persona, misma pose, mismo fondo. Bria es el único
cuya documentación oficial afirma que preserva el contenido "without
regeneration" — por eso es el que se conecta.

Esquemas verificados contra la documentación oficial de WaveSpeed el 4 sep 2026
(ver docs/investigacion/2026-09-04-wavespeed-calidad-realismo.md). Si algo
falla, vuelve a verificar ahí antes de asumir que el código está mal.
"""
import requests

from providers import wavespeed_common

MODELO_EDICION = "google/nano-banana-pro/edit-ultra"
MODELO_UPSCALE = "bria/increase-resolution"

# Precios oficiales por corrida (wavespeed.ai, 4 sep 2026).
COSTO_USD_EDICION = {"4k": 0.15, "8k": 0.18}
COSTO_USD_UPSCALE = 0.04

# Límite duro documentado del upscaler: el ÁREA total de salida no puede pasar
# de 8192x8192. Con factor 4 eso deja la entrada en ~2048x2048; una foto de
# celular vertical ya se pasa, así que el default es 2.
FACTOR_UPSCALE_POR_DEFECTO = 2
AREA_MAXIMA_SALIDA = 8192 * 8192

MAX_IMAGENES = 14


def _lanzar(model_path, payload):
    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{model_path}",
        json=payload,
        headers=wavespeed_common.headers(),
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({model_path}) respondió {resp.status_code}: {resp.text[:500]}")
    data = resp.json().get("data") or {}
    prediction_id = data.get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed ({model_path}) no devolvió un id de predicción: {resp.text[:500]}")
    return prediction_id


def _primera_salida(data, nombre_modelo):
    salidas = data.get("outputs") or []
    if not salidas:
        raise RuntimeError(f"{nombre_modelo} no devolvió ninguna imagen: {data}")
    return salidas[0]


def editar_imagen(foto_url, prompt, referencias_urls=None, resolution="4k",
                  aspect_ratio=None, on_progreso=None):
    """Pone el producto en la foto y devuelve la URL del resultado en 4k/8k.

    `images` es una lista PLANA (no hay slots separados para "foto a editar" y
    "referencias"): el orden lo define el prompt, que ya nombra a la Imagen 1
    como la foto base y a las siguientes como referencias del producto. Por eso
    la foto original va primero, siempre."""
    referencias_urls = referencias_urls or []
    # -1 porque la foto a editar ocupa el primer lugar de las 14.
    imagenes = [foto_url] + list(referencias_urls[:MAX_IMAGENES - 1])

    payload = {"prompt": prompt, "images": imagenes, "resolution": resolution}
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio

    prediction_id = _lanzar(MODELO_EDICION, payload)
    data = wavespeed_common.poll_hasta_listo(
        prediction_id, "Nano Banana Pro Ultra", on_progreso=on_progreso,
    )
    return _primera_salida(data, "Nano Banana Pro Ultra")


def mejorar_calidad(imagen_url, factor=FACTOR_UPSCALE_POR_DEFECTO, on_progreso=None):
    """Segunda pasada: agranda la imagen SIN regenerar su contenido. Devuelve la
    URL del resultado. Pensado para correr sobre la salida de cualquier modelo de
    swap — la documentación oficial advierte que este modelo espera una imagen
    "already reasonably sharp and clean", que es justo lo que sale de un editor."""
    if factor not in (2, 4):
        raise ValueError(f"desired_increase solo acepta 2 o 4, no {factor!r}")

    prediction_id = _lanzar(MODELO_UPSCALE, {"image": imagen_url, "desired_increase": factor})
    data = wavespeed_common.poll_hasta_listo(
        prediction_id, "Bria Increase Resolution", on_progreso=on_progreso,
    )
    return _primera_salida(data, "Bria Increase Resolution")


def factor_seguro(ancho, alto):
    """Elige 4 solo si la imagen cabe en el límite de área de salida; si no, 2.
    Sin esto, una foto grande con factor 4 se rechaza del lado del proveedor
    después de haber cobrado la corrida."""
    if ancho and alto and (ancho * 4) * (alto * 4) <= AREA_MAXIMA_SALIDA:
        return 4
    return FACTOR_UPSCALE_POR_DEFECTO


def estimate_image(resolution="4k", con_mejora=False):
    total = COSTO_USD_EDICION.get(resolution, COSTO_USD_EDICION["4k"])
    if con_mejora:
        total += COSTO_USD_UPSCALE
    return {"credits": None, "usd": round(total, 3)}


def estimate_mejora():
    return {"credits": None, "usd": COSTO_USD_UPSCALE}
