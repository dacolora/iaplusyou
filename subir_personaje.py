"""
Sube la imagen de referencia de un "personaje" que te mandó un cliente a tu storage
propio (Cloudflare R2), y devuelve la URL pública para usar como `image_url` en sus briefs.

Uso:
    python subir_personaje.py --cliente empresa_a ruta/a/foto.jpg
    python subir_personaje.py --cliente empresa_a ruta/a/foto.jpg --nombre modelo_1

Si no pasas --nombre, usa el nombre del archivo original. La imagen queda guardada
en R2 bajo clientes/<empresa>/personajes/<nombre>, y también se copia localmente a
clientes/<empresa>/personajes/ para que quede un respaldo en tu máquina.
"""
import argparse
import os
import shutil

from dotenv import load_dotenv

from storage import r2_uploader

load_dotenv()

BASE_DIR = os.path.dirname(__file__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", required=True, help="Nombre de carpeta bajo clientes/")
    parser.add_argument("ruta_imagen", help="Ruta local a la imagen del personaje")
    parser.add_argument("--nombre", help="Nombre a usar en el storage (default: nombre del archivo)")
    args = parser.parse_args()

    if not os.path.exists(args.ruta_imagen):
        raise RuntimeError(f"No encontré el archivo: {args.ruta_imagen}")

    nombre = args.nombre or os.path.basename(args.ruta_imagen)
    client_dir = os.path.join(BASE_DIR, "clientes", args.cliente)
    personajes_dir = os.path.join(client_dir, "personajes")
    os.makedirs(personajes_dir, exist_ok=True)

    local_copy = os.path.join(personajes_dir, nombre)
    shutil.copy(args.ruta_imagen, local_copy)

    key = f"clientes/{args.cliente}/personajes/{nombre}"
    public_url = r2_uploader.upload_image(local_copy, key)

    print(f"\nListo. Guarda esta URL para usarla como \"image_url\" en los briefs de {args.cliente}:")
    print(public_url)


if __name__ == "__main__":
    main()
