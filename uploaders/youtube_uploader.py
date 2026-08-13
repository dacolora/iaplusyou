"""
Subida de video a YouTube usando la YouTube Data API v3.

Requiere haber corrido antes `python auth/auth_youtube.py` una vez para generar
el archivo `token_youtube.json` (credenciales OAuth ya autorizadas por el usuario).
"""
import os
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DEFAULT_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "token_youtube.json")


def _get_credentials(token_path):
    if not os.path.exists(token_path):
        raise RuntimeError(
            f"No encontré {token_path}. Corre primero: python auth/auth_youtube.py"
            + (" --cliente <empresa>" if token_path != DEFAULT_TOKEN_PATH else "")
        )
    creds = Credentials.from_authorized_user_file(token_path)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def upload_video(
    video_path,
    title,
    description="",
    tags=None,
    privacy_status="public",
    category_id="22",
    token_path=None,
):
    """Sube un video local a YouTube. Devuelve el video_id publicado.

    token_path: ruta al token OAuth ya autorizado (por defecto, el compartido en la
    raíz del proyecto). Para multi-cliente, pasa clientes/<empresa>/token_youtube.json.
    """
    creds = _get_credentials(token_path or DEFAULT_TOKEN_PATH)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Subiendo a YouTube... {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"  YouTube listo: https://youtu.be/{video_id}")
    return video_id
