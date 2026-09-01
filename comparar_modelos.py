"""
Corre la MISMA foto o el MISMO video, y el MISMO producto, contra varios modelos
de edición de imagen/video (todos vía fal.ai) para comparar resultados lado a
lado. No toca prompts_pendientes.json ni estado_videos.json — es una herramienta
de investigación aparte, no parte del flujo de aprobación normal.

Uso:
    python comparar_modelos.py --cliente happyflops --foto ruta/a/foto.jpg --producto ho_sky
    python comparar_modelos.py --cliente happyflops --video ruta/a/video.mp4 --producto ho_sky

Resultados: salidas/<cliente>/comparacion/<timestamp>/<modelo_id>.<ext>, más un
resumen impreso en consola con costo y tiempo por modelo. Un modelo que falla no
detiene a los demás — su error se imprime y se sigue con el resto.
"""
import argparse
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

import catalogo_productos
from providers import comparador_modelos, kling_o1_client
from storage import r2_uploader

BASE_DIR = os.path.dirname(__file__)


def _cargar_entorno(cliente):
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    client_env = os.path.join(BASE_DIR, "clientes", cliente, ".env")
    if os.path.exists(client_env):
        load_dotenv(client_env, override=True)


def _descargar(url, local_path):
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(resp.content)


def _comparar_imagen(cliente, foto_local, producto, out_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    foto_url = r2_uploader.upload_image(foto_local, f"clientes/{cliente}/comparacion/{ts}_original{os.path.splitext(foto_local)[1]}")
    referencias_urls = [
        r2_uploader.upload_image(ref, f"clientes/{cliente}/comparacion/{ts}_ref_{os.path.basename(ref)}")
        for ref in producto["referencias"][:2]
    ]

    resultados = []
    for modelo_id, info in comparador_modelos.MODELOS_IMAGEN.items():
        print(f"\n--- {info['nombre']} ({modelo_id}) ---")
        inicio = time.time()
        try:
            url = comparador_modelos.editar_imagen(
                modelo_id, foto_url, producto["descripcion"], referencias_urls=referencias_urls,
                foto_local_path=foto_local,
            )
            local_out = os.path.join(out_dir, f"{modelo_id}.png")
            _descargar(url, local_out)
            costo = comparador_modelos.estimate_image(modelo_id)
            segundos = round(time.time() - inicio, 1)
            print(f"  OK en {segundos}s -> {local_out}  (${costo['usd']})")
            resultados.append({"modelo": info["nombre"], "estado": "ok", "segundos": segundos, "usd": costo["usd"], "archivo": local_out})
        except Exception as e:
            print(f"  ERROR: {e}")
            resultados.append({"modelo": info["nombre"], "estado": "error", "error": str(e)})
    return resultados


def _comparar_video(cliente, video_local, producto, out_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_url = r2_uploader.upload_video(video_local, f"clientes/{cliente}/comparacion/{ts}_original{os.path.splitext(video_local)[1]}")
    referencias_urls = [
        r2_uploader.upload_image(ref, f"clientes/{cliente}/comparacion/{ts}_ref_{os.path.basename(ref)}")
        for ref in producto["referencias"][:4]
    ]

    resultados = []

    print(f"\n--- Kling O1 (kling_o1) ---")
    inicio = time.time()
    try:
        citas = " ".join(f"@Image{i + 1}" for i in range(len(referencias_urls)))
        prompt = (
            f"Reemplaza el calzado que lleva puesta la persona por el que se muestra "
            f"en {citas} — mismo color, diseño y textura exactos. No cambies nada más "
            f"del video: mismo movimiento, misma persona, mismo fondo, misma iluminación."
        )
        url = kling_o1_client.editar_video(video_url, prompt, referencias_urls=referencias_urls)
        local_out = os.path.join(out_dir, "kling_o1.mp4")
        _descargar(url, local_out)
        costo = kling_o1_client.estimate_video()
        segundos = round(time.time() - inicio, 1)
        print(f"  OK en {segundos}s -> {local_out}  (${costo['usd']})")
        resultados.append({"modelo": "Kling O1", "estado": "ok", "segundos": segundos, "usd": costo["usd"], "archivo": local_out})
    except Exception as e:
        print(f"  ERROR: {e}")
        resultados.append({"modelo": "Kling O1", "estado": "error", "error": str(e)})

    for modelo_id, info in comparador_modelos.MODELOS_VIDEO.items():
        print(f"\n--- {info['nombre']} ({modelo_id}) ---")
        inicio = time.time()
        try:
            referencia = referencias_urls[0] if referencias_urls else None
            url = comparador_modelos.editar_video(modelo_id, video_url, producto["descripcion"], referencia_imagen_url=referencia)
            local_out = os.path.join(out_dir, f"{modelo_id}.mp4")
            _descargar(url, local_out)
            costo = comparador_modelos.estimate_video(modelo_id)
            segundos = round(time.time() - inicio, 1)
            print(f"  OK en {segundos}s -> {local_out}  (${costo['usd']})")
            resultados.append({"modelo": info["nombre"], "estado": "ok", "segundos": segundos, "usd": costo["usd"], "archivo": local_out})
        except Exception as e:
            print(f"  ERROR: {e}")
            resultados.append({"modelo": info["nombre"], "estado": "error", "error": str(e)})
    return resultados


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--foto")
    parser.add_argument("--video")
    parser.add_argument("--producto", required=True, help="id del producto en clientes/<cliente>/productos/")
    args = parser.parse_args()

    if not args.foto and not args.video:
        parser.error("Pasa --foto o --video.")
    if args.foto and args.video:
        parser.error("Pasa solo uno: --foto o --video, no ambos.")

    _cargar_entorno(args.cliente)

    producto = catalogo_productos.encontrar(args.cliente, args.producto)
    if not producto:
        parser.error(f"No encontré el producto '{args.producto}' en clientes/{args.cliente}/productos/")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BASE_DIR, "salidas", args.cliente, "comparacion", ts)
    os.makedirs(out_dir, exist_ok=True)

    if args.foto:
        resultados = _comparar_imagen(args.cliente, args.foto, producto, out_dir)
    else:
        resultados = _comparar_video(args.cliente, args.video, producto, out_dir)

    print(f"\n\n=== Resumen ({out_dir}) ===")
    for r in resultados:
        if r["estado"] == "ok":
            print(f"  {r['modelo']:<28} OK   {r['segundos']:>6}s   ${r['usd']}")
        else:
            print(f"  {r['modelo']:<28} ERROR  {r['error'][:80]}")


if __name__ == "__main__":
    main()
