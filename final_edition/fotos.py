"""Las copias de una foto que usa el editor (capa 5b): la que entra al
render como clip de la pista principal (`preparar`, D2) y la copia liviana
para la vista previa y las miniaturas (`ligera`, D13). La prepara
`tareas.edicion.preparar_rutas` (una vez por material, en
`rutas["foto:<material_id>"]` — aparte de `rutas[<material_id>]`: la misma
imagen puede estar a la vez como foto y como capa encima, que necesita su
alfa) y `tareas.edicion.ejecutar_proxy` (la tarea gratis `edicion_proxy`),
respectivamente.

`preparar`:
- orientación EXIF aplicada (una foto de celular viene acostada con una
  marca, como un video: D6);
- lo transparente sobre negro (la vista previa pinta el lienzo de negro
  antes de dibujarla, así que se ve igual en los dos motores);
- RGB, lado largo ≤ `LADO_MAX` (un cuadro de 12 MP decodificado y escalado
  en cada render no aporta nada a un 1080×1920 y cuesta memoria);
- JPEG calidad `CALIDAD`.

`ligera` (D13, una foto de 12 MP decodificada en el navegador pesa ~48 MB):
- orientación EXIF aplicada, igual que `preparar`;
- lo transparente se CONSERVA (una capa encima de la misma imagen necesita
  su alfa, a diferencia de un clip de la principal, que nunca la necesita):
  PNG si la foto trae un canal alfa real o es de paleta con color
  transparente, si no JPEG calidad `CALIDAD_LIGERA`;
- lado largo ≤ `LADO_LIGERA`.

Sin red ni base: Pillow y disco."""
import os

from flask_babel import gettext
from PIL import Image, ImageOps

LADO_MAX = 4096
CALIDAD = 92
LADO_LIGERA = 1920
CALIDAD_LIGERA = 85


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


def _con_transparencia(im):
    """True si `im` trae un canal alfa real (RGBA/LA) o es de paleta con un
    color transparente (`P` + `transparency` en `info`)."""
    if im.mode == "P" and "transparency" in im.info:
        return True
    return "A" in im.getbands()


def _abierta_derecha(origen):
    """La foto `origen` abierta, cargada y con la orientación EXIF ya
    aplicada; RuntimeError (en el idioma del proyecto, mensaje de `preparar`
    — las dos funciones comparten el mismo) si Pillow no la puede leer."""
    try:
        with Image.open(origen) as original:
            original.load()
            return ImageOps.exif_transpose(original)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise RuntimeError(gettext("No pude leer la foto %(archivo)s.", archivo=os.path.basename(origen))) from e


def preparar(origen, destino):
    """Escribe en `destino` la copia preparada de la foto `origen` y
    devuelve sus medidas `(ancho, alto)` — las que se VEN (ya derecha), las
    que usa el encuadre. RuntimeError (en el idioma del proyecto) si Pillow
    no la puede leer."""
    im = _sobre_negro(_abierta_derecha(origen))
    if max(im.size) > LADO_MAX:
        im.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    carpeta = os.path.dirname(destino)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    im.save(destino, "JPEG", quality=CALIDAD)
    return im.size


def ligera(origen, carpeta):
    """Escribe en `carpeta` (`ligera.jpg` o `ligera.png`) la copia liviana
    de la foto `origen` para la vista previa (D13) y devuelve
    `(ruta, content_type, ancho, alto)` — las medidas que se VEN, como
    `preparar`. RuntimeError (mismo mensaje que `preparar`) si Pillow no la
    puede leer."""
    derecha = _abierta_derecha(origen)
    if _con_transparencia(derecha):
        im, content_type, nombre = derecha.convert("RGBA"), "image/png", "ligera.png"
    else:
        im, content_type, nombre = derecha.convert("RGB"), "image/jpeg", "ligera.jpg"
    if max(im.size) > LADO_LIGERA:
        im.thumbnail((LADO_LIGERA, LADO_LIGERA), Image.LANCZOS)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    if content_type == "image/png":
        im.save(ruta, "PNG")
    else:
        im.save(ruta, "JPEG", quality=CALIDAD_LIGERA)
    ancho, alto = im.size
    return ruta, content_type, ancho, alto
