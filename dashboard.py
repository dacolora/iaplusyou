"""
Dashboard web local: clientes, personajes, briefs/prompts, videos, aprobación y
estado de publicación por plataforma — todo en una página.

Uso:
    python dashboard.py
    (abre http://127.0.0.1:5050 en tu navegador)

Solo corre en tu máquina (127.0.0.1), no queda expuesto a internet.
"""
import os
import subprocess
import threading

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime

import estado as estado_mod
import prompts as prompts_mod
import bitacora
import trabajos
import generador_prompts
from publicador import publicar_brief
from higgsfield_client import (
    generate_video,
    generate_image,
    poll_until_done,
    download_result,
    download_image_result,
    extract_video_url,
    extract_image_url,
    estimate_video,
    estimate_image,
)
from storage import r2_uploader

BASE_DIR = os.path.dirname(__file__)
ALL_PLATFORMS = ["youtube", "facebook", "instagram", "tiktok"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm")
FRAME_SUFFIX = ".frame.jpg"

load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = "solo-local-no-hace-falta-secreto-real"

# Cargar el .env de un cliente muta os.environ (variables globales del proceso).
# Como publicar ahora corre en un hilo de fondo, dos publicaciones de clientes
# distintos podrían solaparse y pisarse las credenciales una a la otra — este
# lock serializa esa sección crítica (cargar credenciales + usarlas) para que
# eso no pase.
_ENV_LOCK = threading.Lock()


@app.route("/trabajo/<path:job_id>/estado")
def estado_trabajo(job_id):
    """El navegador consulta esto cada poco tiempo para actualizar la barra de
    progreso de una generación en curso (imagen, video, o publicación)."""
    info = trabajos.consultar(job_id)
    if info is None:
        return jsonify({"estado": "desconocido", "progreso": 0, "elapsed": 0, "mensaje": None})
    return jsonify(info)


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
    """Personajes disponibles: imágenes tal cual, y videos representados por un
    fotograma extraído (eso es lo que realmente se usa como referencia en Higgsfield)."""
    personajes_dir = os.path.join(_client_dir(cliente), "personajes")
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    if not os.path.isdir(personajes_dir):
        return []

    archivos = sorted(os.listdir(personajes_dir))
    resultado = []
    for f in archivos:
        low = f.lower()
        if low.endswith(FRAME_SUFFIX):
            continue  # es un fotograma derivado, no un personaje por sí mismo
        if low.endswith(IMAGE_EXTS):
            resultado.append({
                "nombre": f,
                "url": f"{public_base}/clientes/{cliente}/personajes/{f}",
                "tipo": "imagen",
            })
        elif low.endswith(VIDEO_EXTS):
            frame_name = f + FRAME_SUFFIX
            tiene_frame = frame_name in archivos
            resultado.append({
                "nombre": f,
                "url": f"{public_base}/clientes/{cliente}/personajes/{frame_name}" if tiene_frame else None,
                "video_url": f"{public_base}/clientes/{cliente}/personajes/{f}",
                "tipo": "video",
            })
    return resultado


def _extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
        check=True, capture_output=True,
    )


@app.route("/cliente/<cliente>/personaje/subir", methods=["POST"])
def subir_personaje(cliente):
    """Sube una imagen O UN VIDEO de personaje desde el navegador: se guarda local
    y en R2 (nunca en el repositorio de git — los binarios no van ahí). Si es un
    video, además le saca un fotograma con ffmpeg — eso es lo que se usa como
    referencia de imagen al generar (Higgsfield no acepta video como referencia)."""
    archivo = request.files.get("imagen")
    if not archivo or not archivo.filename:
        flash("No elegiste ningún archivo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    nombre = secure_filename(archivo.filename)
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        flash("Formato no soportado. Usa jpg, jpeg, png, webp, mp4, mov o webm.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    personajes_dir = os.path.join(_client_dir(cliente), "personajes")
    os.makedirs(personajes_dir, exist_ok=True)
    local_path = os.path.join(personajes_dir, nombre)
    archivo.save(local_path)

    if ext in VIDEO_EXTS:
        try:
            r2_uploader.upload_video(local_path, f"clientes/{cliente}/personajes/{nombre}")
        except Exception as e:
            flash(f"Se guardó localmente pero falló la subida del video a R2: {e}", "error")
            return redirect(url_for("ver_cliente", cliente=cliente))

        frame_name = nombre + FRAME_SUFFIX
        frame_path = os.path.join(personajes_dir, frame_name)
        try:
            _extraer_frame(local_path, frame_path)
            r2_uploader.upload_image(frame_path, f"clientes/{cliente}/personajes/{frame_name}")
            flash(f"Video subido y fotograma de referencia extraído: {nombre}", "ok")
        except Exception as e:
            flash(
                f"El video {nombre} se subió, pero no pude extraer su fotograma de referencia "
                f"(no se puede usar como personaje hasta resolver esto): {e}",
                "error",
            )
    else:
        try:
            r2_uploader.upload_image(local_path, f"clientes/{cliente}/personajes/{nombre}")
            flash(f"Personaje subido: {nombre}", "ok")
        except Exception as e:
            flash(f"Se guardó localmente pero falló la subida a R2: {e}", "error")

    return redirect(url_for("ver_cliente", cliente=cliente))


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


def _job_id_imagen(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__imagen"


def _job_id_video(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__video"


def _job_id_publicar(cliente, brief_id):
    return f"{cliente}__{brief_id}__publicar"


def _trabajo_de_prompt(cliente, prompt_id, item):
    """Si hay una generación en curso para este prompt (imagen o video según su
    etapa), devuelve {"job_id": ...} para que la plantilla muestre la barra de
    progreso en vez de los botones normales."""
    if item.get("estado") == "pendiente":
        job_id = _job_id_imagen(cliente, prompt_id)
    elif item.get("estado") == "imagen_pendiente":
        job_id = _job_id_video(cliente, prompt_id)
    else:
        return None
    return {"job_id": job_id} if trabajos.en_curso(job_id) else None


def _ideas_pendientes(cliente):
    """Ideas con al menos un prompt en curso (pendiente o imagen_pendiente),
    cada una con su costo estimado según en qué etapa está."""
    data = prompts_mod.cargar(cliente)
    ideas = []
    for idea_id, idea in data.items():
        prompts_en_curso = []
        for pid, item in idea.get("prompts", {}).items():
            if item.get("estado") not in ("pendiente", "imagen_pendiente"):
                continue
            entry = {"id": pid, **item}
            entry["trabajo"] = _trabajo_de_prompt(cliente, pid, item)
            if entry["trabajo"]:
                entry["credits"] = None
                entry["usd"] = None
            else:
                try:
                    if item.get("estado") == "imagen_pendiente":
                        est = estimate_video(
                            item["imagen_url"],
                            item["prompt"],
                            item.get("model", "kling-2.1-pro"),
                            extra_params=_extra_params_video(item),
                        )
                    else:
                        est = estimate_image(
                            item["image_url"],
                            item["prompt"],
                            extra_params=_extra_params_image(item),
                        )
                    entry["credits"] = est["credits"]
                    entry["usd"] = est["usd"]
                except Exception:
                    entry["credits"] = None
                    entry["usd"] = None
            prompts_en_curso.append(entry)

        if prompts_en_curso:
            prompts_en_curso.sort(key=lambda e: e.get("creado_en", ""))
            for i, entry in enumerate(prompts_en_curso, start=1):
                entry["numero"] = i
            ideas.append({
                "id": idea_id,
                "idea": idea.get("idea"),
                "creado_en": idea.get("creado_en"),
                "prompts": prompts_en_curso,
            })

    return sorted(ideas, key=lambda i: i.get("creado_en", ""), reverse=True)


def _extra_params_video(item):
    """Solo kling-2.1-pro acepta duration/cfg_scale; dop-standard no los declara."""
    if item.get("model") != "kling-2.1-pro":
        return None
    return {"duration": int(item.get("duration", 5)), "cfg_scale": float(item.get("cfg_scale", 0.5))}


def _extra_params_image(item):
    return {"aspect_ratio": item.get("aspect_ratio", "9:16")}


def _aplicar_edicion(item, form):
    """Aplica los campos editables del formulario (si vinieron) sobre el prompt."""
    if "prompt" in form and form["prompt"].strip():
        item["prompt"] = form["prompt"].strip()
    if "model" in form and form["model"] in prompts_mod.MODELOS_VALIDOS:
        item["model"] = form["model"]
    if "aspect_ratio" in form and form["aspect_ratio"] in prompts_mod.ASPECT_RATIOS_VALIDOS:
        item["aspect_ratio"] = form["aspect_ratio"]
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
        job_id = _job_id_publicar(cliente, brief_id)
        videos.append({
            "id": brief_id,
            **entry,
            "plataformas_estado": _estado_plataformas(cliente, brief_id) if entry.get("estado") == "publicado" else {},
            "trabajo": {"job_id": job_id} if entry.get("estado") == "pendiente" and trabajos.en_curso(job_id) else None,
        })

    log = bitacora.leer(cliente=cliente, limit=100)

    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        ideas=_ideas_pendientes(cliente),
        modelos=prompts_mod.MODELOS_VALIDOS,
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
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


def _generar_imagen_candidata(cliente, prompt_id, item):
    """Genera (o regenera) la imagen candidata para un prompt vía soul/reference,
    la sube a R2 y actualiza el propio dict `item` en el sitio. Devuelve (ok, error)."""
    imagenes_dir = os.path.join(BASE_DIR, "salidas", cliente, "imagenes")
    os.makedirs(imagenes_dir, exist_ok=True)
    local_path = os.path.join(imagenes_dir, f"{prompt_id}.png")

    try:
        launch = generate_image(
            image_reference_url=item["image_url"],
            prompt=item["prompt"],
            extra_params=_extra_params_image(item),
        )
        result = poll_until_done(launch["status_url"])
        download_image_result(result, local_path)
        bitacora.registrar(cliente, prompt_id, "imagen", "ok", local_path)
    except Exception as e:
        bitacora.registrar(cliente, prompt_id, "imagen", "error", str(e))
        return False, str(e)

    try:
        imagen_url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/imagenes/{prompt_id}.png")
    except Exception as e:
        imagen_url = extract_image_url(result)
        bitacora.registrar(cliente, prompt_id, "imagen_storage", "error", str(e))

    item["imagen_url"] = imagen_url
    item["imagen_local"] = local_path
    item["estado"] = "imagen_pendiente"
    return True, None


def _lanzar_generacion_imagen(cliente, prompt_id):
    """Lanza en segundo plano la generación de la imagen candidata para un
    prompt ya editado/guardado. No hace nada (y avisa) si ya hay una corriendo
    para ese mismo prompt — así un doble clic no dispara dos llamadas."""
    job_id = _job_id_imagen(cliente, prompt_id)

    def trabajo():
        data = prompts_mod.cargar(cliente)
        _, item = prompts_mod.encontrar_prompt(data, prompt_id)
        if not item:
            raise RuntimeError("El prompt ya no existe (¿se descartó mientras generaba?).")
        ok, error = _generar_imagen_candidata(cliente, prompt_id, item)
        prompts_mod.guardar(cliente, data)
        if not ok:
            raise RuntimeError(error)
        return "Imagen candidata lista."

    return trabajos.iniciar(job_id, trabajo, duracion_estimada=45)


@app.route("/cliente/<cliente>/prompt/<prompt_id>/aprobar", methods=["POST"])
def aprobar_prompt(cliente, prompt_id):
    """Aprueba el texto del prompt y lanza en segundo plano la generación de una
    imagen de referencia candidata (barata, ~1.5cr) — todavía NO genera el video."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(f"No encontré el prompt {prompt_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    if _lanzar_generacion_imagen(cliente, prompt_id):
        flash(f"Generando imagen candidata para {prompt_id}…", "ok")
    else:
        flash(f"Ya se está generando la imagen de {prompt_id} — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/regenerar_imagen", methods=["POST"])
def regenerar_imagen(cliente, prompt_id):
    """La imagen candidata no gustó: lanza otra en segundo plano (gasta créditos de nuevo)."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(f"No encontré el prompt {prompt_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    if _lanzar_generacion_imagen(cliente, prompt_id):
        flash(f"Regenerando imagen candidata para {prompt_id}…", "ok")
    else:
        flash(f"Ya se está generando una imagen para {prompt_id} — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/aprobar_imagen", methods=["POST"])
def aprobar_imagen(cliente, prompt_id):
    """La imagen candidata sí gustó: lanza en segundo plano el video real a
    partir de ella (aquí sí se gasta el crédito grande, ~8cr)."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item or not item.get("imagen_url"):
        flash(f"No encontré una imagen candidata para {prompt_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    job_id = _job_id_video(cliente, prompt_id)

    def trabajo():
        data2 = prompts_mod.cargar(cliente)
        idea_id2, item2 = prompts_mod.encontrar_prompt(data2, prompt_id)
        if not item2:
            raise RuntimeError("El prompt ya no existe (¿se descartó mientras generaba?).")

        out_dir = os.path.join(BASE_DIR, "salidas", cliente)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{prompt_id}.mp4")

        launch = generate_video(
            image_url=item2["imagen_url"],
            prompt=item2["prompt"],
            model=item2.get("model", "kling-2.1-pro"),
            extra_params=_extra_params_video(item2),
        )
        result = poll_until_done(launch["status_url"])
        higgsfield_url = extract_video_url(result)
        try:
            download_result(result, out_path)
            bitacora.registrar(cliente, prompt_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, prompt_id, "generacion", "error", str(e))
            raise

        try:
            video_url = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{prompt_id}.mp4")
            bitacora.registrar(cliente, prompt_id, "storage", "ok", video_url)
        except Exception as e:
            video_url = higgsfield_url
            bitacora.registrar(cliente, prompt_id, "storage", "error", str(e))

        estado = estado_mod.cargar(cliente)
        estado[prompt_id] = {
            "prompt": item2["prompt"],
            "image_url": item2["imagen_url"],
            "title": item2.get("title", prompt_id),
            "caption": item2.get("caption", item2["prompt"]),
            "platforms": item2.get("platforms", []),
            "video_local": out_path,
            "video_url": video_url,
            "estado": "pendiente",
            "generado_en": datetime.now().isoformat(),
            "publicado_en": None,
        }
        estado_mod.guardar(cliente, estado)

        del data2[idea_id2]["prompts"][prompt_id]
        prompts_mod.guardar(cliente, data2)
        return "Video listo, pendiente de revisión."

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=130):
        flash(f"Generando el video de {prompt_id}…", "ok")
    else:
        flash(f"Ya se está generando el video de {prompt_id} — espera a que termine.", "warn")
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

    job_id = _job_id_publicar(cliente, brief_id)

    def trabajo():
        # Serializado: cargar el .env del cliente muta variables globales del
        # proceso, así que dos publicaciones de clientes distintos no pueden
        # hacer esa parte al mismo tiempo sin arriesgarse a mezclar credenciales.
        with _ENV_LOCK:
            _cargar_entorno_cliente(cliente)
            ok = publicar_brief(brief_id, entry, cliente, _token_paths(cliente))

        estado2 = estado_mod.cargar(cliente)
        estado2[brief_id]["estado"] = "publicado"
        estado2[brief_id]["publicado_en"] = datetime.now().isoformat()
        estado_mod.guardar(cliente, estado2)

        if not ok:
            raise RuntimeError("Se publicó, pero alguna plataforma falló — revisa la bitácora.")
        return "Publicado en todas las plataformas."

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=90):
        flash(f"Publicando {brief_id}…", "ok")
    else:
        flash(f"Ya se está publicando {brief_id} — espera a que termine.", "warn")
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
    # use_reloader=False a propósito: ahora hay generaciones corriendo en hilos
    # de fondo, y el auto-reload de Flask mata el proceso completo (y con él,
    # cualquier generación en curso) apenas detecta un cambio de archivo.
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
