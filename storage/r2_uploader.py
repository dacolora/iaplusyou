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
import re
from urllib.parse import quote

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
    # Una sesión por llamada: boto3.client() usa la sesión por defecto, que no es
    # segura entre hilos (gunicorn con 8 hilos; el worker con varias generaciones).
    return boto3.session.Session().client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


# Claves que NUNCA se reescriben con otro contenido (spec 2026-10-01-escala-y-
# monitoreo §5): la final de una versión congelada (`__v<id>`) y los materiales
# nombrados por el hash de lo que contienen. Esas salen con caché de un año: el
# navegador y el CDN de Cloudflare (con un dominio propio en R2_PUBLIC_BASE_URL)
# las guardan y no vuelven a pedirlas. El resto no lleva Cache-Control (como
# siempre): un video de Crear regenerado reusa su clave.
INMUTABLE = "public, max-age=31536000, immutable"
_CLAVES_INMUTABLES = (
    re.compile(r"/finales/[^/]+__v\d+\.(mp4|png)$"),
    re.compile(r"/materiales/(voz|locucion|grabacion)_[0-9a-f]{16}\.[a-z0-9]+$"),
    re.compile(r"/materiales/[0-9a-f]{64}\.[a-z0-9]+$"),
)


def cache_control(key):
    """INMUTABLE si la clave es de las que nunca cambian de contenido; None si no."""
    return INMUTABLE if any(p.search(key or "") for p in _CLAVES_INMUTABLES) else None


def upload_file(local_path, key, content_type):
    """Sube local_path al bucket bajo `key`. Devuelve la URL pública permanente."""
    bucket = os.environ.get("R2_BUCKET_NAME")
    public_base = os.environ.get("R2_PUBLIC_BASE_URL")
    if not bucket or not public_base:
        raise RuntimeError(
            "Faltan R2_BUCKET_NAME / R2_PUBLIC_BASE_URL en tu .env. Ver SETUP.md."
        )

    client = _client()
    extra = {"CacheControl": cache_control(key)} if cache_control(key) else {}
    with open(local_path, "rb") as f:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType=content_type,
            **extra,
        )

    # El nombre de archivo puede traer espacios u otros caracteres que una URL
    # cruda no tolera (algunos modelos de fal.ai validan estrictamente que sea
    # una HTTPS URL válida y rechazan espacios sin codificar) — la Key de S3/R2
    # se sube tal cual, pero la URL pública sí se codifica.
    return f"{public_base.rstrip('/')}/{quote(key, safe='/')}"


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


def delete_file(key):
    """Borra `key` del bucket. No falla si ya no existe (delete_object es idempotente)."""
    bucket = os.environ.get("R2_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("Falta R2_BUCKET_NAME en tu .env. Ver SETUP.md.")
    _client().delete_object(Bucket=bucket, Key=key)
