"""La copia de una foto que entra al render como clip de la pista principal
(editor capa 5b, spec D2). La prepara `tareas.edicion.preparar_rutas` una
vez por material, en `rutas["foto:<material_id>"]` (aparte de
`rutas[<material_id>]`: la misma imagen puede estar a la vez como foto y
como capa encima, que necesita su alfa).

- orientación EXIF aplicada (una foto de celular viene acostada con una
  marca, como un video: D6);
- lo transparente sobre negro (la vista previa pinta el lienzo de negro
  antes de dibujarla, así que se ve igual en los dos motores);
- RGB, lado largo ≤ `LADO_MAX` (un cuadro de 12 MP decodificado y escalado
  en cada render no aporta nada a un 1080×1920 y cuesta memoria);
- JPEG calidad `CALIDAD`.

Sin red ni base: Pillow y disco."""
import os

from flask_babel import gettext
from PIL import Image, ImageOps

LADO_MAX = 4096
CALIDAD = 92


def _sobre_negro(im):
    """`im` en RGB, con lo transparente (canal alfa, o el color
    transparente de una paleta) sobre negro."""
    if im.mode == "P" or "transparency" in im.info:
        im = im.convert("RGBA")
    if "A" in im.getbands() or "a" in im.getbands():
        im = im.convert("RGBA")
        fondo = Image.new("RGBA", im.size, (0, 0, 0, 255))
        fondo.alpha_composite(im)
        return fondo.convert("RGB")
    return im.convert("RGB")


def preparar(origen, destino):
    """Escribe en `destino` la copia preparada de la foto `origen` y
    devuelve sus medidas `(ancho, alto)` — las que se VEN (ya derecha), las
    que usa el encuadre. RuntimeError (en el idioma del proyecto) si Pillow
    no la puede leer."""
    try:
        with Image.open(origen) as original:
            original.load()
            im = _sobre_negro(ImageOps.exif_transpose(original))
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise RuntimeError(gettext("No pude leer la foto %(archivo)s.", archivo=os.path.basename(origen))) from e
    if max(im.size) > LADO_MAX:
        im.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    carpeta = os.path.dirname(destino)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    im.save(destino, "JPEG", quality=CALIDAD)
    return im.size
