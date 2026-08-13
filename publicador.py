"""
Publica un video ya aprobado en las plataformas que indique su brief.

Esto solo lo llama revisar.py, y solo para un brief que el admin/cliente acaba de
aprobar — nunca se dispara automáticamente al generar.
"""
from bitacora import registrar


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
            _publicar_una(platform, entry, token_paths)
            registrar(cliente, brief_id, platform, "ok", "")
        except Exception as e:
            ok_total = False
            print(f"    ERROR publicando en {platform}: {e}")
            registrar(cliente, brief_id, platform, "error", str(e))
    return ok_total


def _publicar_una(platform, entry, token_paths):
    video_path = entry["video_local"]
    video_url = entry["video_url"]
    title = entry.get("title", "")
    caption = entry.get("caption", "")

    if platform == "youtube":
        from uploaders import youtube_uploader

        youtube_uploader.upload_video(
            video_path, title=title, description=caption, token_path=token_paths.get("youtube")
        )
    elif platform == "facebook":
        from uploaders import meta_uploader

        meta_uploader.upload_to_facebook_page(video_path, description=caption, title=title)
    elif platform == "instagram":
        from uploaders import meta_uploader

        meta_uploader.upload_to_instagram_reel(video_url, caption=caption)
    elif platform == "tiktok":
        from uploaders import tiktok_uploader

        tiktok_uploader.upload_video(video_path, title=title, token_path=token_paths.get("tiktok"))
    else:
        raise ValueError(f"Plataforma desconocida: {platform}")
