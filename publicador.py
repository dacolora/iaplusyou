"""
Publica un video ya aprobado en las plataformas que indique su brief.

Esto solo lo llama revisar.py, y solo para un brief que el admin/cliente acaba de
aprobar — nunca se dispara automáticamente al generar.
"""
import os
from urllib.parse import urlparse

import requests

from bitacora import registrar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _carpeta_salidas():
    return os.environ.get("CREATV_SALIDAS") or os.path.join(BASE_DIR, "salidas")


def archivo_local(entry, cliente):
    """El archivo del video para subirlo a una plataforma: el local si sigue
    en disco; si no (salidas_limpiar borra las copias de trabajo con más de
    14 días), se baja de `video_url` a salidas/<cliente>/publicar/ y se
    reutiliza en la siguiente plataforma."""
    ruta = entry.get("video_local")
    if ruta and os.path.exists(ruta):
        return ruta
    url = entry.get("video_url")
    if not url:
        raise ValueError("El video no tiene archivo local ni URL de dónde bajarlo.")
    nombre = os.path.basename(urlparse(url).path) or "video.mp4"
    destino = os.path.join(_carpeta_salidas(), cliente, "publicar", nombre)
    if os.path.exists(destino):
        return destino
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    tmp = destino + ".parcial"
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1024 * 256):
            f.write(chunk)
    os.replace(tmp, destino)
    return destino


def publicar_brief(brief_id, entry, cliente, token_paths):
    """Publica entry en cada plataforma de entry['platforms'].

    entry: dict con video_local, video_url, title, caption, platforms.
    Devuelve True si todas las plataformas salieron bien, False si alguna falló
    (las que sí funcionaron quedan publicadas igual; revisa el log para ver cuál falló).
    """
    ok_total = True
    for platform in entry.get("platforms", []):
        print(f"  --- Publicando en {platform} ---")
        try:
            _publicar_una(platform, entry, cliente, token_paths)
            registrar(cliente, brief_id, platform, "ok", "")
        except Exception as e:
            ok_total = False
            print(f"    ERROR publicando en {platform}: {e}")
            registrar(cliente, brief_id, platform, "error", str(e))
    return ok_total


def _publicar_una(platform, entry, cliente, token_paths):
    """Publica en UNA plataforma y devuelve el id que devolvió el uploader
    (video_id de Facebook/YouTube, media_id de Instagram, publish_id de
    TikTok) — organico.py lo guarda para armar la URL pública. publicar_brief
    lo ignora."""
    video_path = archivo_local(entry, cliente)
    video_url = entry["video_url"]
    title = entry.get("title", "")
    caption = entry.get("caption", "")

    if platform == "youtube":
        from uploaders import youtube_uploader

        return youtube_uploader.upload_video(
            video_path, title=title, description=caption, token_path=token_paths.get("youtube")
        )
    elif platform == "facebook":
        from uploaders import meta_uploader

        return meta_uploader.upload_to_facebook_page(video_path, cliente, description=caption, title=title)
    elif platform == "instagram":
        from uploaders import meta_uploader

        return meta_uploader.upload_to_instagram_reel(video_url, cliente, caption=caption)
    elif platform == "tiktok":
        from uploaders import tiktok_uploader

        return tiktok_uploader.upload_video(video_path, title=title, token_path=token_paths.get("tiktok"))
    else:
        raise ValueError(f"Plataforma desconocida: {platform}")
