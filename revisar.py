"""
Revisa los videos pendientes (generados por run_batch.py) uno por uno. Abre cada
video en el navegador para verlo, y apenas apruebas uno se publica AL INSTANTE en
todas las plataformas que traía su brief. Lo que rechaces no se publica en ninguna red.

Uso:
    python revisar.py
    python revisar.py --cliente empresa_a
"""
import argparse
import os
import webbrowser
from datetime import datetime

from dotenv import load_dotenv

import estado as estado_mod
from publicador import publicar_brief

BASE_DIR = os.path.dirname(__file__)


def main(cliente=None):
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    if cliente:
        client_dir = os.path.join(BASE_DIR, "clientes", cliente)
        client_env = os.path.join(client_dir, ".env")
        if os.path.exists(client_env):
            load_dotenv(client_env, override=True)
        token_paths = {
            "youtube": os.path.join(client_dir, "token_youtube.json"),
            "tiktok": os.path.join(client_dir, "token_tiktok.json"),
        }
    else:
        token_paths = {"youtube": None, "tiktok": None}

    estado = estado_mod.cargar(cliente)
    pendientes = [(bid, e) for bid, e in estado.items() if e.get("estado") == "pendiente"]

    if not pendientes:
        print("No hay videos pendientes de revisión.")
        return

    print(f"{len(pendientes)} video(s) pendiente(s) de revisión.\n")

    for brief_id, entry in pendientes:
        print("=" * 60)
        print(f"ID: {brief_id}")
        print(f"Título: {entry.get('title')}")
        print(f"Prompt: {entry.get('prompt')}")
        print(f"Plataformas a publicar si apruebas: {', '.join(entry.get('platforms', []))}")
        print(f"Video: {entry.get('video_url')}")

        try:
            webbrowser.open(entry["video_url"])
        except Exception:
            pass

        respuesta = input(
            "¿Aprobar y publicar ahora? [s = sí / n = rechazar / Enter = decidir después]: "
        ).strip().lower()

        if respuesta == "s":
            print("Publicando...")
            publicar_brief(brief_id, entry, cliente, token_paths)
            entry["estado"] = "publicado"
            entry["publicado_en"] = datetime.now().isoformat()
            estado_mod.guardar(cliente, estado)
            print("Publicado.")
        elif respuesta == "n":
            entry["estado"] = "rechazado"
            estado_mod.guardar(cliente, estado)
            print("Rechazado, no se publica.")
        else:
            print("Lo dejo pendiente para la próxima revisión.")

    print("\nRevisión terminada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", help="Nombre de carpeta bajo clientes/, si aplica")
    args = parser.parse_args()
    main(cliente=args.cliente)
