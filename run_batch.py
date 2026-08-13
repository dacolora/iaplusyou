"""
Genera en lote los videos definidos en un archivo de briefs (JSON) usando la API de
Higgsfield. Los descarga, los sube a tu storage propio (Cloudflare R2), y los deja
PENDIENTES DE REVISIÓN — no publica nada en ninguna red todavía.

Uso:
    python run_batch.py briefs_example.json
    python run_batch.py clientes/empresa_a/briefs/lote1.json --cliente empresa_a

Cuando quieras revisar lo que salió y publicar lo que apruebes:
    python revisar.py --cliente empresa_a

Cada brief puede traer:
    id            (obligatorio) identificador único, se usa para el nombre de archivo
    image_url     (obligatorio) URL pública de la imagen de referencia (ver subir_personaje.py)
    prompt        (obligatorio) instrucción de movimiento/cámara para Higgsfield
    model         (opcional) modelo de Higgsfield, default "kling-2.1-pro"
    title         (opcional) título para YouTube/TikTok, default = id
    caption       (opcional) descripción/caption para todas las redes, default = prompt
    platforms     (opcional) lista entre "youtube", "facebook", "instagram", "tiktok".
                  Si no se especifica, se usan todas las que estén habilitadas en .env.
                  Esta lista es la que se usa cuando se apruebe el video en revisar.py.

--- Multi-cliente ---
Sin --cliente, todo usa las rutas compartidas en la raíz del proyecto (modo de un solo
cliente). Con --cliente <empresa>, se cargan primero las variables del .env de la raíz
(compartidas: Higgsfield, apps de Meta/TikTok, bucket R2) y luego las de
clientes/<empresa>/.env; los videos y el manifiesto de estado quedan bajo
salidas/<empresa>/ y clientes/<empresa>/estado_videos.json.
"""
import argparse
import json
import os
from datetime import datetime

from dotenv import load_dotenv

from higgsfield_client import generate_video, poll_until_done, download_result, extract_video_url
from storage import r2_uploader
from bitacora import registrar
import estado as estado_mod

BASE_DIR = os.path.dirname(__file__)
ALL_PLATFORMS = ["youtube", "facebook", "instagram", "tiktok"]


def _enabled_platforms():
    enabled = []
    for platform in ALL_PLATFORMS:
        flag = os.environ.get(f"ENABLE_{platform.upper()}", "true").strip().lower()
        if flag in ("1", "true", "yes", "si", "sí"):
            enabled.append(platform)
    return enabled


def main(briefs_path, cliente=None):
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    if cliente:
        client_dir = os.path.join(BASE_DIR, "clientes", cliente)
        client_env = os.path.join(client_dir, ".env")
        if os.path.exists(client_env):
            load_dotenv(client_env, override=True)
        out_dir = os.path.join(BASE_DIR, "salidas", cliente)
        r2_prefix = f"clientes/{cliente}/videos/"
    else:
        out_dir = os.path.join(BASE_DIR, "salidas")
        r2_prefix = ""

    with open(briefs_path, "r", encoding="utf-8") as f:
        briefs = json.load(f)

    os.makedirs(out_dir, exist_ok=True)
    default_platforms = _enabled_platforms()
    estado = estado_mod.cargar(cliente)
    generados = []

    for brief in briefs:
        brief_id = brief.get("id", "sin_id")
        print(f"\n=== Generando: {brief_id} ===" + (f" (cliente: {cliente})" if cliente else ""))
        try:
            launch = generate_video(
                image_url=brief["image_url"],
                prompt=brief["prompt"],
                model=brief.get("model", "kling-2.1-pro"),
            )
            print("Lanzado, request_id:", launch.get("request_id"))
            result = poll_until_done(launch["status_url"])

            higgsfield_video_url = extract_video_url(result)
            out_path = os.path.join(out_dir, f"{brief_id}.mp4")
            download_result(result, out_path)
            print(f"Video listo: {out_path}")
            registrar(cliente, brief_id, "generacion", "ok", out_path)
        except Exception as e:
            print(f"ERROR generando {brief_id}: {e}")
            registrar(cliente, brief_id, "generacion", "error", str(e))
            continue

        try:
            video_url = r2_uploader.upload_video(out_path, f"{r2_prefix}{brief_id}.mp4")
            registrar(cliente, brief_id, "storage", "ok", video_url)
        except Exception as e:
            print(f"  ERROR subiendo a storage propio (R2): {e}")
            print("  Guardo la URL temporal de Higgsfield para que igual se pueda revisar.")
            video_url = higgsfield_video_url
            registrar(cliente, brief_id, "storage", "error", str(e))

        estado[brief_id] = {
            "prompt": brief["prompt"],
            "image_url": brief["image_url"],
            "title": brief.get("title", brief_id),
            "caption": brief.get("caption", brief.get("prompt", "")),
            "platforms": brief.get("platforms", default_platforms),
            "video_local": out_path,
            "video_url": video_url,
            "estado": "pendiente",
            "generado_en": datetime.now().isoformat(),
            "publicado_en": None,
        }
        generados.append(brief_id)

    estado_mod.guardar(cliente, estado)

    print(f"\nListo. {len(generados)} video(s) generado(s) y guardado(s), pendientes de revisión.")
    cmd = "python revisar.py" + (f" --cliente {cliente}" if cliente else "")
    print(f"Para verlos y publicar los que apruebes: {cmd}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("briefs", nargs="?", default="briefs_example.json")
    parser.add_argument("--cliente", help="Nombre de carpeta bajo clientes/, si aplica")
    args = parser.parse_args()
    main(args.briefs, cliente=args.cliente)
