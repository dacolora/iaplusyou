# sprints/archivos.py
"""
Referencias subidas a una campaña: se guardan en
clientes/<cliente>/sprints/referencias/ y en R2 (misma clave), y a los videos
se les saca un fotograma (miniatura y referencia para los modelos que no
aceptan video). Mismo criterio que `_guardar_referencia_archivo` de
dashboard.py, pero sin depender de Flask.
"""
import os
import subprocess
from datetime import datetime

from werkzeug.utils import secure_filename

from storage import r2_uploader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm")
FRAME_SUFFIX = ".frame.jpg"


def carpeta(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "sprints", "referencias")


def extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
                   check=True, capture_output=True)


def registrar_local(cliente, local_path, titulo):
    """Sube un archivo ya guardado en disco a R2 y devuelve la ficha de la
    referencia (tipo, url, frame_url, ruta_local, titulo)."""
    nombre = os.path.basename(local_path)
    ext = os.path.splitext(nombre)[1].lower()
    key = f"clientes/{cliente}/sprints/referencias/{nombre}"
    if ext in VIDEO_EXTS:
        url = r2_uploader.upload_video(local_path, key)
        frame_path = local_path + FRAME_SUFFIX
        extraer_frame(local_path, frame_path)
        frame_url = r2_uploader.upload_image(frame_path, key + FRAME_SUFFIX)
        return {"tipo": "video", "url": url, "frame_url": frame_url, "ruta_local": local_path, "titulo": titulo}
    url = r2_uploader.upload_image(local_path, key)
    return {"tipo": "imagen", "url": url, "frame_url": url, "ruta_local": local_path, "titulo": titulo}


def guardar_subida(cliente, archivo):
    """`archivo` es un FileStorage de Flask. Devuelve la ficha o None si la
    extensión no es imagen ni video."""
    nombre = secure_filename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        return None
    destino = carpeta(cliente)
    os.makedirs(destino, exist_ok=True)
    unico = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    local_path = os.path.join(destino, unico)
    archivo.save(local_path)
    return registrar_local(cliente, local_path, nombre)
