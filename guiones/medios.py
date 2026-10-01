"""URL pública de una imagen de escena de Flow Plus: lo subido ya está en R2;
una foto del Catálogo se sube con la misma clave que usa Crear al generar
(`cf_crear_video`), así que no se duplica. La usan «Llevar a Crear» y la
cadena de escenas (referencias de la escena 1 y elementos de Kling)."""
import os

from flask_babel import gettext

import catalogo_productos
from guiones.refinador import Conflicto
from storage import r2_uploader


def url_publica(cliente, img):
    if not img.get("activo_id"):
        return img["url"]
    activo = catalogo_productos.encontrar(cliente, img["activo_id"], categoria=img["categoria"])
    if activo is None:
        raise Conflicto(gettext("«%(nombre)s» ya no está en el Catálogo.", nombre=img.get("nombre") or img["activo_id"]))
    carpeta = catalogo_productos.CATEGORIAS[activo["categoria"]]["carpeta"]
    ruta = activo["representativa"]
    return r2_uploader.upload_image(ruta, f"clientes/{cliente}/{carpeta}/{activo['id']}/{os.path.basename(ruta)}")
