"""
Sube cada video generado a Cloudflare R2, para tener una copia propia y permanente
(independiente de que la URL que entrega Higgsfield siga viva o no) y una URL pública
propia para publicar en redes que la requieren (Instagram).

Requiere en el .env:
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET_NAME
    R2_PUBLIC_BASE_URL   -> el dominio público del bucket (r2.dev o dominio propio),
                             sin barra final. Ej: https://pub-xxxxxxxx.r2.dev

Ver SETUP.md para cómo crear el bucket, el token de API y activar el acceso público.
"""
import os
import boto3


def _client():
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not all([account_id, access_key, secret_key]):
        raise RuntimeError(
            "Faltan R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY en tu .env. "
            "Ver SETUP.md, sección Cloudflare R2."
        )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def upload_file(local_path, key, content_type):
    """Sube local_path al bucket bajo `key`. Devuelve la URL pública permanente."""
    bucket = os.environ.get("R2_BUCKET_NAME")
    public_base = os.environ.get("R2_PUBLIC_BASE_URL")
    if not bucket or not public_base:
        raise RuntimeError(
            "Faltan R2_BUCKET_NAME / R2_PUBLIC_BASE_URL en tu .env. Ver SETUP.md."
        )

    client = _client()
    with open(local_path, "rb") as f:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType=content_type,
        )

    return f"{public_base.rstrip('/')}/{key}"


def upload_video(local_path, key):
    """Sube un video local al bucket bajo `key` (ej: 'video_2026-08-13_01.mp4').

    Devuelve la URL pública permanente del video.
    """
    public_url = upload_file(local_path, key, content_type="video/mp4")
    print(f"  Guardado en storage propio (R2): {public_url}")
    return public_url


IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def upload_image(local_path, key):
    """Sube una imagen de referencia (personaje) al bucket bajo `key`.

    Devuelve la URL pública permanente de la imagen, lista para usar como
    `image_url` en un brief.
    """
    ext = os.path.splitext(local_path)[1].lower()
    content_type = IMAGE_CONTENT_TYPES.get(ext, "application/octet-stream")
    public_url = upload_file(local_path, key, content_type=content_type)
    print(f"  Imagen guardada en storage propio (R2): {public_url}")
    return public_url
