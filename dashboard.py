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
from flask import Flask, render_template, redirect, url_for, flash, request
from datetime import datetime

import estado as estado_mod
import prompts as prompts_mod
import bitacora
import generador_prompts
from publicador import publicar_brief
from higgsfield_client import (
    generate_video,
    poll_until_done,
    download_result,
    extract_video_url,
    estimate_video,
)
from storage import r2_uploader

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


def _ideas_pendientes(cliente):
    """Ideas con al menos un prompt pendiente, cada prompt con su costo estimado."""
    data = prompts_mod.cargar(cliente)
    ideas = []
    for idea_id, idea in data.items():
        prompts_pendientes = []
        for pid, item in idea.get("prompts", {}).items():
            if item.get("estado") != "pendiente":
                continue
            entry = {"id": pid, **item}
            try:
                est = estimate_video(
                    item["image_url"],
                    item["prompt"],
                    item.get("model", "kling-2.1-pro"),
                    extra_params=_extra_params(item),
                )
                entry["credits"] = est["credits"]
                entry["usd"] = est["usd"]
            except Exception:
                entry["credits"] = None
                entry["usd"] = None
            prompts_pendientes.append(entry)

        if prompts_pendientes:
            prompts_pendientes.sort(key=lambda e: e.get("creado_en", ""))
            ideas.append({
                "id": idea_id,
                "idea": idea.get("idea"),
                "creado_en": idea.get("creado_en"),
                "prompts": prompts_pendientes,
            })

    return sorted(ideas, key=lambda i: i.get("creado_en", ""), reverse=True)


def _extra_params(item):
    """Solo kling-2.1-pro acepta duration/cfg_scale; dop-standard no los declara."""
    if item.get("model") != "kling-2.1-pro":
        return None
    return {"duration": int(item.get("duration", 5)), "cfg_scale": float(item.get("cfg_scale", 0.5))}


def _aplicar_edicion(item, form):
    """Aplica los campos editables del formulario (si vinieron) sobre el prompt."""
    if "prompt" in form and form["prompt"].strip():
        item["prompt"] = form["prompt"].strip()
    if "model" in form and form["model"] in prompts_mod.MODELOS_VALIDOS:
        item["model"] = form["model"]
    if "duration" in form:
        try:
            item["duration"] = int(form["duration"])
        except ValueError:
            pass
    if "cfg_scale" in form:
        try:
            item["cfg_scale"] = float(form["cfg_scale"])
        except ValueError:
            pass
    return item


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
        ideas=_ideas_pendientes(cliente),
        modelos=prompts_mod.MODELOS_VALIDOS,
        videos=videos,
        log=log,
    )


@app.route("/cliente/<cliente>/idea/nueva", methods=["POST"])
def nueva_idea(cliente):
    """Recibe una idea del formulario, genera 5 prompts con Claude, y los deja
    listos para revisar/editar/aprobar (no gasta créditos de Higgsfield todavía)."""
    idea_texto = request.form.get("idea", "").strip()
    image_url = request.form.get("image_url", "").strip()
    platforms = request.form.getlist("platforms")

    if not idea_texto or not image_url:
        flash("Escribe la idea y elige un personaje.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    try:
        textos = generador_prompts.generar_prompts(idea_texto, n=5)
    except Exception as e:
        flash(f"No pude generar los prompts: {e}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    items = [{"prompt": t, "image_url": image_url, "platforms": platforms} for t in textos]
    prompts_mod.agregar_idea(cliente, idea_texto, items)

    flash(f"Generé {len(items)} prompts para la idea. Revísalos y apruébalos abajo.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/guardar", methods=["POST"])
def guardar_prompt(cliente, prompt_id):
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(f"No encontré el prompt {prompt_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)
    flash(f"Cambios guardados en {prompt_id}.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/aprobar", methods=["POST"])
def aprobar_prompt(cliente, prompt_id):
    """Genera el video real a partir de un prompt ya aprobado (aquí sí se gastan créditos)."""
    _cargar_entorno_cliente(cliente)
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(f"No encontré el prompt {prompt_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    out_dir = os.path.join(BASE_DIR, "salidas", cliente)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{prompt_id}.mp4")

    try:
        launch = generate_video(
            image_url=item["image_url"],
            prompt=item["prompt"],
            model=item.get("model", "kling-2.1-pro"),
            extra_params=_extra_params(item),
        )
        result = poll_until_done(launch["status_url"])
        higgsfield_url = extract_video_url(result)
        download_result(result, out_path)
        bitacora.registrar(cliente, prompt_id, "generacion", "ok", out_path)
    except Exception as e:
        bitacora.registrar(cliente, prompt_id, "generacion", "error", str(e))
        flash(f"Error generando {prompt_id}: {e}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    try:
        video_url = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{prompt_id}.mp4")
        bitacora.registrar(cliente, prompt_id, "storage", "ok", video_url)
    except Exception as e:
        video_url = higgsfield_url
        bitacora.registrar(cliente, prompt_id, "storage", "error", str(e))

    estado = estado_mod.cargar(cliente)
    estado[prompt_id] = {
        "prompt": item["prompt"],
        "image_url": item["image_url"],
        "title": item.get("title", prompt_id),
        "caption": item.get("caption", item["prompt"]),
        "platforms": item.get("platforms", []),
        "video_local": out_path,
        "video_url": video_url,
        "estado": "pendiente",
        "generado_en": datetime.now().isoformat(),
        "publicado_en": None,
    }
    estado_mod.guardar(cliente, estado)

    del data[idea_id]["prompts"][prompt_id]
    prompts_mod.guardar(cliente, data)

    flash(f"Video generado para {prompt_id} — queda pendiente de revisión más abajo.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/rechazar", methods=["POST"])
def rechazar_prompt(cliente, prompt_id):
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if item:
        del data[idea_id]["prompts"][prompt_id]
        prompts_mod.guardar(cliente, data)
        flash(f"Prompt {prompt_id} descartado, no se generó video (no gastó créditos).", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


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
