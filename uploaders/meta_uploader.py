"""
Subida de video a Facebook (Página) e Instagram (cuenta Business/Creator) vía Graph API.

Las credenciales son POR PROYECTO y salen de clientes/<cliente>/meta.json
(meta_conexion.py), donde las dejó el cliente al conectar su cuenta desde
FlowMarketing: page_access_token, page_id, ig_user_id. Ya no se lee nada del
entorno (variables de ambiente).

Notas importantes:
- Facebook admite subir el archivo de video local directamente.
- Instagram (Reels) exige una URL PÚBLICA del video, no un archivo local.
"""
import time
import requests

import meta_conexion

GRAPH_VERSION = meta_conexion.GRAPH_VERSION
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
GRAPH_VIDEO_URL = f"https://graph-video.facebook.com/{GRAPH_VERSION}"


def _credenciales(cliente):
    datos = meta_conexion.cargar(cliente)
    if not datos or not datos.get("page_access_token") or not datos.get("page_id"):
        raise RuntimeError("Este proyecto no tiene Meta conectado — conéctalo en FlowMarketing.")
    return {
        "page_access_token": datos["page_access_token"],
        "page_id": datos["page_id"],
        "ig_user_id": datos.get("ig_user_id"),
    }


def upload_to_facebook_page(video_path, cliente, description="", title=None):
    """Sube un video local al feed de la Página de Facebook. Devuelve el video_id."""
    creds = _credenciales(cliente)
    url = f"{GRAPH_VIDEO_URL}/{creds['page_id']}/videos"
    data = {"access_token": creds["page_access_token"], "description": description}
    if title:
        data["title"] = title

    with open(video_path, "rb") as f:
        resp = requests.post(url, data=data, files={"source": f}, timeout=300)
    resp.raise_for_status()
    result = resp.json()
    video_id = result.get("id")
    print(f"  Facebook listo: https://www.facebook.com/{video_id}")
    return video_id


def upload_to_instagram_reel(video_url, cliente, caption="", poll_interval=5, timeout_seconds=300):
    """Publica un Reel en Instagram a partir de una URL pública de video.

    Flujo de dos pasos de la Graph API: crear contenedor -> esperar a que procese -> publicar.
    """
    creds = _credenciales(cliente)
    ig_user_id = creds["ig_user_id"]
    if not ig_user_id:
        raise RuntimeError("La Página conectada no tiene Instagram vinculado: no se puede publicar el Reel.")
    token = creds["page_access_token"]

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
