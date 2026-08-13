"""
Subida de video a Facebook (Página) e Instagram (cuenta Business/Creator) vía Graph API.

Requiere en el .env:
    META_PAGE_ACCESS_TOKEN   -> token de acceso de larga duración de la Página de Facebook
    META_PAGE_ID             -> ID de la Página de Facebook
    META_IG_USER_ID          -> ID de la cuenta de Instagram Business/Creator vinculada a esa Página

Corre primero `python auth/auth_meta.py` para obtener estos valores. Ver SETUP.md.

Notas importantes:
- Facebook admite subir el archivo de video local directamente.
- Instagram (Reels) exige una URL PÚBLICA del video, no un archivo local. Por eso
  run_batch.py le pasa la URL que devuelve Higgsfield (higgsfield_client.extract_video_url),
  no la ruta del archivo descargado.
"""
import os
import time
import requests

GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
GRAPH_VIDEO_URL = f"https://graph-video.facebook.com/{GRAPH_VERSION}"


def _page_token():
    token = os.environ.get("META_PAGE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Falta META_PAGE_ACCESS_TOKEN en .env. Corre auth/auth_meta.py")
    return token


def upload_to_facebook_page(video_path, description="", title=None):
    """Sube un video local al feed de la Página de Facebook. Devuelve el video_id."""
    page_id = os.environ.get("META_PAGE_ID")
    if not page_id:
        raise RuntimeError("Falta META_PAGE_ID en .env")

    url = f"{GRAPH_VIDEO_URL}/{page_id}/videos"
    data = {"access_token": _page_token(), "description": description}
    if title:
        data["title"] = title

    with open(video_path, "rb") as f:
        resp = requests.post(url, data=data, files={"source": f}, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    video_id = result.get("id")
    print(f"  Facebook listo: https://www.facebook.com/{video_id}")
    return video_id


def upload_to_instagram_reel(video_url, caption="", poll_interval=5, timeout_seconds=300):
    """Publica un Reel en Instagram a partir de una URL pública de video.

    Flujo de dos pasos de la Graph API: crear contenedor -> esperar a que procese -> publicar.
    """
    ig_user_id = os.environ.get("META_IG_USER_ID")
    if not ig_user_id:
        raise RuntimeError("Falta META_IG_USER_ID en .env")

    token = _page_token()

    create_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=60,
    )
    create_resp.raise_for_status()
    creation_id = create_resp.json()["id"]

    start = time.time()
    while time.time() - start < timeout_seconds:
        status_resp = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram falló al procesar el video: {status_resp.json()}")
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Instagram no terminó de procesar el video a tiempo.")

    publish_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json()["id"]
    print(f"  Instagram listo, media_id: {media_id}")
    return media_id
