"""
Dashboard web local: clientes, personajes, briefs/prompts, videos, aprobación y
estado de publicación por plataforma — todo en una página.

Uso:
    python dashboard.py
    (abre http://127.0.0.1:5050 en tu navegador)

Solo corre en tu máquina (127.0.0.1), no queda expuesto a internet.
"""
import os

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash
from datetime import datetime

import estado as estado_mod
import bitacora
from publicador import publicar_brief

BASE_DIR = os.path.dirname(__file__)
ALL_PLATFORMS = ["youtube", "facebook", "instagram", "tiktok"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = "solo-local-no-hace-falta-secreto-real"


def _client_dir(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente)


def _cargar_entorno_cliente(cliente):
    """Capa el .env compartido con el del cliente, igual que run_batch.py/revisar.py."""
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    client_env = os.path.join(_client_dir(cliente), ".env")
    if os.path.exists(client_env):
        load_dotenv(client_env, override=True)


def _token_paths(cliente):
    client_dir = _client_dir(cliente)
    return {
        "youtube": os.path.join(client_dir, "token_youtube.json"),
        "tiktok": os.path.join(client_dir, "token_tiktok.json"),
    }


def _personajes(cliente):
    personajes_dir = os.path.join(_client_dir(cliente), "personajes")
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    if not os.path.isdir(personajes_dir):
        return []
    archivos = sorted(
        f for f in os.listdir(personajes_dir)
        if f.lower().endswith(IMAGE_EXTS)
    )
    return [
        {"nombre": f, "url": f"{public_base}/clientes/{cliente}/personajes/{f}"}
        for f in archivos
    ]


def _estado_plataformas(cliente, brief_id):
    """Última tentativa registrada por plataforma para este video (ok/error/None)."""
    filas = bitacora.leer(cliente=cliente, brief_id=brief_id, limit=1000)
    resultado = {}
    for fila in filas:
        etapa = fila.get("etapa")
        if etapa in ALL_PLATFORMS and etapa not in resultado:
            resultado[etapa] = fila.get("estado")
    return resultado


def _resumen_cliente(cliente):
    videos = estado_mod.cargar(cliente)
    conteo = {"pendiente": 0, "publicado": 0, "rechazado": 0}
    for entry in videos.values():
        conteo[entry.get("estado", "pendiente")] = conteo.get(entry.get("estado", "pendiente"), 0) + 1
    return conteo


@app.route("/")
def index():
    clientes = [
        {"nombre": c, **_resumen_cliente(c)}
        for c in estado_mod.listar_clientes()
    ]
    return render_template("index.html", clientes=clientes)


@app.route("/cliente/<cliente>")
def ver_cliente(cliente):
    videos_dict = estado_mod.cargar(cliente)
    videos = []
    for brief_id, entry in sorted(
        videos_dict.items(), key=lambda kv: kv[1].get("generado_en", ""), reverse=True
    ):
        videos.append({
            "id": brief_id,
            **entry,
            "plataformas_estado": _estado_plataformas(cliente, brief_id) if entry.get("estado") == "publicado" else {},
        })

    log = bitacora.leer(cliente=cliente, limit=100)

    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        videos=videos,
        log=log,
    )


@app.route("/cliente/<cliente>/aprobar/<brief_id>", methods=["POST"])
def aprobar(cliente, brief_id):
    estado = estado_mod.cargar(cliente)
    entry = estado.get(brief_id)
    if not entry:
        flash(f"No encontré {brief_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _cargar_entorno_cliente(cliente)
    ok = publicar_brief(brief_id, entry, cliente, _token_paths(cliente))
    entry["estado"] = "publicado"
    entry["publicado_en"] = datetime.now().isoformat()
    estado_mod.guardar(cliente, estado)

    flash(
        f"{brief_id} publicado." if ok else f"{brief_id} publicado con errores en alguna plataforma — revisa la bitácora.",
        "ok" if ok else "warn",
    )
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/rechazar/<brief_id>", methods=["POST"])
def rechazar(cliente, brief_id):
    estado = estado_mod.cargar(cliente)
    entry = estado.get(brief_id)
    if not entry:
        flash(f"No encontré {brief_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    entry["estado"] = "rechazado"
    estado_mod.guardar(cliente, estado)
    flash(f"{brief_id} rechazado, no se publica.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
