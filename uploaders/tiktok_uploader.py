"""
Subida de video a TikTok usando la Content Posting API (v2).

Requiere haber corrido antes `python auth/auth_tiktok.py` una vez para generar
`token_tiktok.json` (access_token + refresh_token).

IMPORTANTE - limitación de TikTok mientras tu app no esté auditada/aprobada:
las apps sin auditar solo pueden publicar como "Solo yo" (SELF_ONLY) en la cuenta
de TikTok del propio desarrollador, no directo y público a cualquier cuenta.
Para publicar público necesitas pasar la revisión de la Content Posting API
("audit") en TikTok for Developers. Ver SETUP.md.
"""
import os
import json
import math
import time

import requests

DEFAULT_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "token_tiktok.json")
API_BASE = "https://open.tiktokapis.com/v2"
MIN_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB


def _load_token(token_path):
    if not os.path.exists(token_path):
        raise RuntimeError(
            f"No encontré {token_path}. Corre primero: python auth/auth_tiktok.py"
            + (" --cliente <empresa>" if token_path != DEFAULT_TOKEN_PATH else "")
        )
    with open(token_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _refresh_token(token_data, token_path):
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    resp = requests.post(
        f"{API_BASE}/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    new_token = resp.json()
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(new_token, f)
    return new_token


def _access_token(token_path):
    token_data = _load_token(token_path)
    # El endpoint de status/init también sirve para validar; si falla por token
    # expirado, refrescamos una vez.
    return token_data["access_token"], token_data


def _headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _pick_privacy_level(access_token):
    """Consulta qué niveles de privacidad admite esta app/cuenta y elige el mejor disponible."""
    resp = requests.post(
        f"{API_BASE}/post/publish/creator_info/query/",
        headers=_headers(access_token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    options = data.get("privacy_level_options", ["SELF_ONLY"])
    for preferred in ("PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"):
        if preferred in options:
            return preferred
    return options[0]


def upload_video(video_path, title="", privacy_level=None, token_path=None):
    """Publica un video en TikTok mediante subida directa de archivo (FILE_UPLOAD).

    Devuelve el publish_id. TikTok procesa la publicación de forma asíncrona;
    usa check_status() para confirmar que terminó.

    token_path: ruta al token OAuth ya autorizado (por defecto, el compartido en la
    raíz del proyecto). Para multi-cliente, pasa clientes/<empresa>/token_tiktok.json.
    """
    token_path = token_path or DEFAULT_TOKEN_PATH
    access_token, _ = _access_token(token_path)

    if privacy_level is None:
        privacy_level = _pick_privacy_level(access_token)
        print(f"  TikTok: usando privacy_level={privacy_level} (según lo que permite tu app)")

    video_size = os.path.getsize(video_path)
    if video_size <= MIN_CHUNK_SIZE:
        chunk_size = video_size
        total_chunk_count = 1
    else:
        chunk_size = MIN_CHUNK_SIZE
        total_chunk_count = math.ceil(video_size / chunk_size)

    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        },
    }
    init_resp = requests.post(
        f"{API_BASE}/post/publish/video/init/",
        headers=_headers(access_token),
        data=json.dumps(init_body),
        timeout=30,
    )
    init_resp.raise_for_status()
    init_data = init_resp.json()["data"]
    upload_url = init_data["upload_url"]
    publish_id = init_data["publish_id"]

    with open(video_path, "rb") as f:
        for chunk_index in range(total_chunk_count):
            start = chunk_index * chunk_size
            end = min(start + chunk_size, video_size) - 1
            f.seek(start)
            chunk_bytes = f.read(end - start + 1)
            put_resp = requests.put(
                upload_url,
                data=chunk_bytes,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Type": "video/mp4",
                },
                timeout=300,
            )
            put_resp.raise_for_status()

    print(f"  TikTok subido, publish_id: {publish_id} (procesando de forma asíncrona)")
    return publish_id


def check_status(publish_id, poll_interval=5, timeout_seconds=300, token_path=None):
    access_token, _ = _access_token(token_path or DEFAULT_TOKEN_PATH)
    start = time.time()
    while time.time() - start < timeout_seconds:
        resp = requests.post(
            f"{API_BASE}/post/publish/status/fetch/",
            headers=_headers(access_token),
            data=json.dumps({"publish_id": publish_id}),
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json()["data"]["status"]
        if status in ("PUBLISH_COMPLETE",):
            return status
        if status in ("FAILED",):
            raise RuntimeError(f"La publicación en TikTok falló: {resp.json()}")
        time.sleep(poll_interval)
    raise TimeoutError("TikTok no confirmó la publicación a tiempo.")
