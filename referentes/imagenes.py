"""
Copia de la imagen de un referente a nuestro R2 (spec 2026-09-23 §6.2): la
biblioteca nunca muestra una URL ajena. `_bajar` es la costura de pruebas.
"""
import io
import os

import requests
from PIL import Image, UnidentifiedImageError

from conectores import url as conector_url
from storage import r2_uploader

MAX_BYTES = 8 * 1024 * 1024
LADO_MAX = 1600
TIMEOUT = 20


class ImagenInvalida(RuntimeError):
    """No se pudo bajar o no es una imagen; la fila queda en estado_imagen=error."""


def clave_r2(anuncio_id, cliente=None):
    prefijo = f"clientes/{cliente}/" if cliente else ""
    return f"{prefijo}referentes/{anuncio_id}.jpg"


def _bajar(url):
    # imagen_origen viene de la página externa (y en bloques futuros, de
    # Atria/Apify): mismo riesgo de SSRF que conectores/url.py, misma guarda
    # — también en cada redirección (`abrir`), no solo en la primera URL.
    try:
        r = conector_url.abrir(url, cabeceras={"User-Agent": "CreatvMachine/1.0"}, timeout=TIMEOUT)
    except conector_url.ErrorConector as e:
        raise ImagenInvalida(str(e)) from e
    try:
        r.raise_for_status()
        trozos, total = [], 0
        for parte in r.iter_content(65536):
            total += len(parte)
            if total > MAX_BYTES:
                raise ImagenInvalida("La imagen pesa más de 8 MB.")
            trozos.append(parte)
        return b"".join(trozos)
    except requests.RequestException as e:
        raise ImagenInvalida(f"No se pudo bajar la imagen: {e.__class__.__name__}") from e
    finally:
        cerrar = getattr(r, "close", None)
        if cerrar:
            cerrar()


def guardar_en_r2(anuncio_id, url_origen, carpeta, cliente=None):
    return copiar_a_r2(url_origen, clave_r2(anuncio_id, cliente=cliente), carpeta)[0]


def medir(url_origen):
    """(ancho, alto) de una imagen, bajada con la guarda de SSRF y validada por su contenido; no sube nada.
    ImagenInvalida si no se puede."""
    crudo = _bajar(url_origen)
    try:
        with Image.open(io.BytesIO(crudo)) as im:
            im.load()
            return im.size
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as e:
        raise ImagenInvalida(f"No es una imagen válida: {e.__class__.__name__}") from e


def copiar_a_r2(url_origen, clave, carpeta):
    """(URL pública en R2, (ancho, alto) de la imagen original). La baja con la guarda de SSRF (`_bajar`), la valida
    por su contenido con Pillow y la sube como JPEG de hasta LADO_MAX px bajo `clave`. ImagenInvalida si no se puede.
    También la usa «Llevar a Crear» de un anuncio de imagen (`triple_whale.puente.imagen_a_bandeja`, 2026-10-13)."""
    crudo = _bajar(url_origen)
    try:
        with Image.open(io.BytesIO(crudo)) as im:
            im.load()
            tamano = im.size
            im = im.convert("RGB")
            im.thumbnail((LADO_MAX, LADO_MAX))
            os.makedirs(carpeta, exist_ok=True)
            local = os.path.join(carpeta, os.path.basename(clave))
            im.save(local, format="JPEG", quality=88)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as e:
        raise ImagenInvalida(f"No es una imagen válida: {e.__class__.__name__}") from e
    try:
        return r2_uploader.upload_image(local, clave), tamano
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
