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

import requests

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file
from werkzeug.utils import secure_filename
from datetime import datetime

import estado as estado_mod
import prompts as prompts_mod
import marca as marca_mod
import conceptos_imagen
import catalogo_productos
import swaps as swaps_mod
import bitacora
import trabajos
import generador_prompts
from providers import image_provider
from providers import nano_banana_client, video_provider, kling_o1_client, comparador_modelos, wavespeed_client
from providers import wavespeed_video_edit, wan3_client
from providers import aspect_ratio as aspect_ratio_mod
import creative_flow
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


def _listar_assets(cliente, subcarpeta):
    """Imágenes tal cual, y videos representados por un fotograma extraído (eso es
    lo que realmente se usa como referencia en Higgsfield). Sirve tanto para
    personajes/ como para marca/."""
    carpeta = os.path.join(_client_dir(cliente), subcarpeta)
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    if not os.path.isdir(carpeta):
        return []

    archivos = sorted(os.listdir(carpeta))
    resultado = []
    for f in archivos:
        low = f.lower()
        if low.endswith(FRAME_SUFFIX):
            continue  # es un fotograma derivado, no un asset por sí mismo
        if low.endswith(IMAGE_EXTS):
            resultado.append({
                "nombre": f,
                "url": f"{public_base}/clientes/{cliente}/{subcarpeta}/{f}",
                "tipo": "imagen",
            })
        elif low.endswith(VIDEO_EXTS):
            frame_name = f + FRAME_SUFFIX
            tiene_frame = frame_name in archivos
            resultado.append({
                "nombre": f,
                "url": f"{public_base}/clientes/{cliente}/{subcarpeta}/{frame_name}" if tiene_frame else None,
                "video_url": f"{public_base}/clientes/{cliente}/{subcarpeta}/{f}",
                "tipo": "video",
            })
    return resultado


def _personajes(cliente):
    return _listar_assets(cliente, "personajes")


def _escenas(cliente):
    return _listar_assets(cliente, "escenas")


def _marca_referencias(cliente):
    return _listar_assets(cliente, "marca")


def _extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
        check=True, capture_output=True,
    )


def _subir_asset(cliente, subcarpeta, archivo):
    """Sube una imagen O UN VIDEO a clientes/<cliente>/<subcarpeta>/: se guarda
    local y en R2 (nunca en el repositorio de git). Si es video, además le saca
    un fotograma con ffmpeg (Higgsfield no acepta video como referencia).
    Devuelve (ok, mensaje)."""
    if not archivo or not archivo.filename:
        return False, "No elegiste ningún archivo."

    nombre = secure_filename(archivo.filename)
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        return False, "Formato no soportado. Usa jpg, jpeg, png, webp, mp4, mov o webm."

    carpeta = os.path.join(_client_dir(cliente), subcarpeta)
    os.makedirs(carpeta, exist_ok=True)
    local_path = os.path.join(carpeta, nombre)
    archivo.save(local_path)

    if ext in VIDEO_EXTS:
        try:
            r2_uploader.upload_video(local_path, f"clientes/{cliente}/{subcarpeta}/{nombre}")
        except Exception as e:
            return False, f"Se guardó localmente pero falló la subida del video a R2: {e}"

        frame_name = nombre + FRAME_SUFFIX
        frame_path = os.path.join(carpeta, frame_name)
        try:
            _extraer_frame(local_path, frame_path)
            r2_uploader.upload_image(frame_path, f"clientes/{cliente}/{subcarpeta}/{frame_name}")
            return True, f"Video subido y fotograma de referencia extraído: {nombre}"
        except Exception as e:
            return False, (
                f"El video {nombre} se subió, pero no pude extraer su fotograma de referencia "
                f"(no se puede usar hasta resolver esto): {e}"
            )
    else:
        try:
            r2_uploader.upload_image(local_path, f"clientes/{cliente}/{subcarpeta}/{nombre}")
            return True, f"Subido: {nombre}"
        except Exception as e:
            return False, f"Se guardó localmente pero falló la subida a R2: {e}"


def _eliminar_asset(cliente, subcarpeta, nombre):
    """Borra un archivo ya subido (imagen o video, más su .frame.jpg si aplica)
    local y de R2. No falla si alguna de las dos copias ya no existía."""
    carpeta = os.path.join(_client_dir(cliente), subcarpeta)
    nombres = [nombre, nombre + FRAME_SUFFIX]
    for n in nombres:
        local_path = os.path.join(carpeta, n)
        if os.path.exists(local_path):
            os.remove(local_path)
        try:
            r2_uploader.delete_file(f"clientes/{cliente}/{subcarpeta}/{n}")
        except Exception:
            pass  # si R2 no está configurado o el objeto ya no existe, seguimos


@app.route("/cliente/<cliente>/personaje/subir", methods=["POST"])
def subir_personaje(cliente):
    ok, mensaje = _subir_asset(cliente, "personajes", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/personaje/<nombre>/eliminar", methods=["POST"])
def eliminar_personaje(cliente, nombre):
    _eliminar_asset(cliente, "personajes", secure_filename(nombre))
    flash(f"Eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/escena/subir", methods=["POST"])
def subir_escena(cliente):
    ok, mensaje = _subir_asset(cliente, "escenas", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/escena/<nombre>/eliminar", methods=["POST"])
def eliminar_escena(cliente, nombre):
    _eliminar_asset(cliente, "escenas", secure_filename(nombre))
    flash(f"Eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/marca/subir", methods=["POST"])
def subir_marca(cliente):
    ok, mensaje = _subir_asset(cliente, "marca", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


def _job_id_marca(cliente):
    return f"{cliente}__marca__analizar"


@app.route("/cliente/<cliente>/marca/analizar", methods=["POST"])
def analizar_marca(cliente):
    """Le pide a Claude que mire las referencias de marca subidas y escriba una
    guía de estilo — se usa automáticamente en cada generación de prompts."""
    urls = [r["url"] for r in _marca_referencias(cliente) if r.get("url")]
    if not urls:
        flash("Sube al menos una referencia de marca (imagen o video) primero.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    job_id = _job_id_marca(cliente)

    def trabajo():
        guia = generador_prompts.analizar_marca(urls)
        data = marca_mod.cargar(cliente)
        data["guia_estilo"] = guia
        marca_mod.guardar(cliente, data)
        return "Guía de estilo generada."

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=15):
        flash("Analizando referencias de marca…", "ok")
    else:
        flash("Ya se está analizando — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/marca/guardar", methods=["POST"])
def guardar_marca(cliente):
    """Guarda la guía de estilo (editada a mano o generada) y, si aplica, un
    style_id de Higgsfield ya creado por el cliente en su propio panel."""
    data = marca_mod.cargar(cliente)
    data["guia_estilo"] = request.form.get("guia_estilo", "").strip()
    style_id = request.form.get("style_id", "").strip()
    data["style_id"] = style_id or None
    try:
        data["style_strength"] = float(request.form.get("style_strength", 0.5))
    except ValueError:
        pass
    marca_mod.guardar(cliente, data)
    flash("Identidad de marca guardada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


def _marca_contexto(cliente):
    data = marca_mod.cargar(cliente)
    job_id = _job_id_marca(cliente)
    root = marca_mod.cargar_root(cliente)
    root_resumen = None
    if root:
        root_resumen = {
            "nombre": root.get("brand", {}).get("name"),
            "version": root.get("version"),
            "actualizado": root.get("updated"),
            "n_invariantes": len(root.get("invariants", [])),
            "invariant_block": root.get("prompt_blocks", {}).get("invariant_block", ""),
            "negative_prompt": root.get("prompt_blocks", {}).get("negative_prompt", ""),
            "invariantes": root.get("invariants", []),
            "open_items": root.get("open_items", []),
        }
    return {
        **data,
        "referencias": _marca_referencias(cliente),
        "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        "root": root_resumen,
    }


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
    # Enfoque temporal en un solo proyecto: Happy Flops. El resto de clientes
    # sigue intacto en disco, solo no se muestra en la portada por ahora.
    return redirect(url_for("ver_cliente", cliente="happyflops"))


def _job_id_imagen(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__imagen"


def _job_id_video(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__video"


def _job_id_publicar(cliente, brief_id):
    return f"{cliente}__{brief_id}__publicar"


def _job_id_creative_flow(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


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
                            extra_params=_extra_params_video(item, cliente),
                        )
                    else:
                        est = estimate_image(
                            item["image_url"],
                            item["prompt"],
                            extra_params=_extra_params_image(item, cliente),
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


def _extra_params_video(item, cliente=None):
    """Solo kling-2.1-pro acepta duration/cfg_scale/negative_prompt; dop-standard no
    los declara. Si el cliente trae un root.json propio (ej. Happyflops), su
    negative_prompt real se adjunta tal cual."""
    if item.get("model") != "kling-2.1-pro":
        return None
    params = {"duration": int(item.get("duration", 5)), "cfg_scale": float(item.get("cfg_scale", 0.5))}
    if cliente:
        neg = marca_mod.negative_prompt_efectivo(cliente)
        if neg:
            params["negative_prompt"] = neg
    return params


def _extra_params_image(item, cliente=None):
    params = {"aspect_ratio": item.get("aspect_ratio", "9:16")}
    if cliente:
        marca = marca_mod.cargar(cliente)
        if marca.get("style_id"):
            params["style_id"] = marca["style_id"]
            params["style_strength"] = float(marca.get("style_strength", 0.5))
    return params


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
        escenas=_escenas(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        productos=catalogo_productos.listar(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
        creative_flow_items=_creative_flow_items(cliente),
    )


PLATAFORMAS_VERTICALES = {"instagram", "tiktok"}


def _aspect_ratio_para_plataformas(platforms):
    """El formato ya no lo elige la persona: si hay alguna plataforma vertical
    marcada (Instagram/Tiktok) manda esa; si no, 9:16 por defecto salvo que sea
    solo Youtube, que es horizontal."""
    if any(p in PLATAFORMAS_VERTICALES for p in platforms):
        return "9:16"
    if platforms == ["youtube"]:
        return "16:9"
    return "9:16"


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

    guia_estilo = marca_mod.guia_efectiva(cliente)
    try:
        textos = generador_prompts.generar_prompts(idea_texto, n=5, guia_estilo=guia_estilo)
    except Exception as e:
        flash(f"No pude generar los prompts: {e}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    aspect_ratio = _aspect_ratio_para_plataformas(platforms)
    items = [
        {"prompt": t, "image_url": image_url, "platforms": platforms, "aspect_ratio": aspect_ratio}
        for t in textos
    ]
    prompts_mod.agregar_idea(cliente, idea_texto, items)

    flash(f"Generé {len(items)} prompts para la idea. Revísalos y apruébalos abajo.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


# ---------- flujo imagen-primero (Happy Flops): idea -> N escenas -> cada escena se
# genera con AMBOS proveedores sin pedir aprobación de texto -> se eligen las imágenes
# que sirvan -> cada una recibe sus propias propuestas de animación -> video ----------

def _job_id_concepto(cliente, idea_id, concepto_id, proveedor):
    return f"{cliente}__{idea_id}__{concepto_id}__{proveedor}__imagen"


def _job_id_animacion(cliente, idea_id, concepto_id, proveedor, anim_id):
    return f"{cliente}__{idea_id}__{concepto_id}__{proveedor}__{anim_id}__video"


def _lanzar_generacion_concepto(cliente, idea_id, concepto_id, proveedor, prompt, referencia_url):
    job_id = _job_id_concepto(cliente, idea_id, concepto_id, proveedor)

    def trabajo():
        imagenes_dir = os.path.join(BASE_DIR, "salidas", cliente, "imagenes")
        os.makedirs(imagenes_dir, exist_ok=True)
        nombre = f"{idea_id}_{concepto_id}_{proveedor}.png"
        local_path = os.path.join(imagenes_dir, nombre)
        negative_prompt = marca_mod.negative_prompt_efectivo(cliente)
        extra_params = _extra_params_image({"aspect_ratio": "9:16"}, cliente)
        video_id = f"{idea_id}_{concepto_id}_{proveedor}"

        try:
            est = image_provider.generar_imagen(
                proveedor, referencia_url, prompt, local_path,
                negative_prompt=negative_prompt, extra_params=extra_params,
            )
            try:
                url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/imagenes/{nombre}")
            except Exception:
                url = None
            campos = {"estado": "listo", "url": url, "local": local_path, "usd": est.get("usd")}
            if proveedor == "higgsfield":
                campos["credits"] = est.get("credits")
            conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, **campos)
            bitacora.registrar(cliente, video_id, "imagen", "ok", local_path)
            return "Imagen lista."
        except Exception as e:
            conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="error", error=str(e))
            bitacora.registrar(cliente, video_id, "imagen", "error", str(e))
            raise

    return trabajos.iniciar(job_id, trabajo, duracion_estimada=45 if proveedor == "higgsfield" else 20)


@app.route("/cliente/<cliente>/idea/nueva_visual", methods=["POST"])
def nueva_idea_visual(cliente):
    """De una idea + referencia, genera 5 escenas y lanza cada una con AMBOS
    proveedores (Nano Banana e Higgsfield) — 10 imágenes en total, sin pedir
    aprobación de texto antes. El costo no se pregunta: se generan todas."""
    idea_texto = request.form.get("idea", "").strip()
    image_url = request.form.get("image_url", "").strip()
    platforms = request.form.getlist("platforms")

    if not idea_texto or not image_url:
        flash("Escribe la idea y elige un personaje.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    guia_estilo = marca_mod.guia_efectiva(cliente)
    try:
        escenas = generador_prompts.generar_conceptos_imagen(idea_texto, n=5, guia_estilo=guia_estilo)
    except Exception as e:
        flash(f"No pude generar las escenas: {e}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    idea_id = conceptos_imagen.crear_idea(cliente, idea_texto, escenas)

    data = conceptos_imagen.cargar(cliente)
    data[idea_id]["platforms"] = platforms
    conceptos_imagen.guardar(cliente, data)

    for concepto_id, concepto in data[idea_id]["conceptos"].items():
        for proveedor in conceptos_imagen.PROVEEDORES:
            _lanzar_generacion_concepto(cliente, idea_id, concepto_id, proveedor, concepto["texto"], image_url)

    flash(f"Generando {len(escenas)} escenas x 2 proveedores (10 imágenes)…", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/aprobar", methods=["POST"])
def aprobar_concepto_imagen(cliente, idea_id, concepto_id, proveedor):
    """Esta imagen sí sirve: genera 5 propuestas de animación (texto, gratis) para
    ella específicamente. Se puede aprobar más de una imagen por idea."""
    data = conceptos_imagen.cargar(cliente)
    concepto = conceptos_imagen.encontrar_concepto(data, idea_id, concepto_id)
    if not concepto or proveedor not in concepto or not concepto[proveedor].get("url"):
        flash("No encontré esa imagen para aprobar.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    guia_estilo = marca_mod.guia_efectiva(cliente)
    idea_texto = data[idea_id]["idea"]
    try:
        animaciones = generador_prompts.generar_prompts(idea_texto, n=5, guia_estilo=guia_estilo)
    except Exception as e:
        flash(f"No pude generar las propuestas de animación: {e}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="aprobado")
    conceptos_imagen.agregar_animaciones(cliente, idea_id, concepto_id, proveedor, animaciones)

    flash("Imagen aprobada — elige cómo animarla abajo.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/descartar", methods=["POST"])
def descartar_concepto_imagen(cliente, idea_id, concepto_id, proveedor):
    conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="descartado")
    flash("Imagen descartada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route(
    "/cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/animacion/<anim_id>/generar_video",
    methods=["POST"],
)
def generar_video_animacion(cliente, idea_id, concepto_id, proveedor, anim_id):
    """La imagen ya quedó fija en la ronda anterior — esto solo anima. Genera el
    video directo, sin paso intermedio de imagen candidata."""
    data = conceptos_imagen.cargar(cliente)
    animacion = conceptos_imagen.encontrar_animacion(data, idea_id, concepto_id, proveedor, anim_id)
    concepto = conceptos_imagen.encontrar_concepto(data, idea_id, concepto_id)
    if not animacion or not concepto or not concepto[proveedor].get("url"):
        flash("No encontré esa animación.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    imagen_url = concepto[proveedor]["url"]
    prompt_texto = (request.form.get("prompt") or animacion["prompt"]).strip() or animacion["prompt"]
    # Higgsfield/Kling es el default: con precio real verificado, sale ~4.7x más
    # barato que Seedance vía fal.ai ($0.49 vs ~$2.31 por 5s) — ver ROADMAP.md.
    proveedor_video = request.form.get("proveedor_video", "higgsfield")
    if proveedor_video not in video_provider.PROVEEDORES_VALIDOS:
        proveedor_video = "higgsfield"
    platforms = data[idea_id].get("platforms", [])
    aspect_ratio = _aspect_ratio_para_plataformas(platforms)
    video_id = f"{idea_id}_{concepto_id}_{proveedor}_{anim_id}"
    job_id = _job_id_animacion(cliente, idea_id, concepto_id, proveedor, anim_id)

    def trabajo():
        out_dir = os.path.join(BASE_DIR, "salidas", cliente)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{video_id}.mp4")
        negative_prompt = marca_mod.negative_prompt_efectivo(cliente)
        item2 = {"aspect_ratio": aspect_ratio, "model": "kling-2.1-pro"}

        try:
            est = video_provider.generar_video(
                proveedor_video, imagen_url, prompt_texto, out_path,
                aspect_ratio=aspect_ratio, negative_prompt=negative_prompt,
                extra_params=_extra_params_video(item2, cliente),
            )
            bitacora.registrar(cliente, video_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, video_id, "generacion", "error", str(e))
            raise

        try:
            video_url = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{video_id}.mp4")
            bitacora.registrar(cliente, video_id, "storage", "ok", video_url)
        except Exception as e:
            video_url = None
            bitacora.registrar(cliente, video_id, "storage", "error", str(e))

        estado = estado_mod.cargar(cliente)
        estado[video_id] = {
            "prompt": prompt_texto,
            "image_url": imagen_url,
            "title": video_id,
            "caption": prompt_texto,
            "platforms": platforms,
            "video_local": out_path,
            "video_url": video_url,
            "estado": "pendiente",
            "generado_en": datetime.now().isoformat(),
            "publicado_en": None,
        }
        estado_mod.guardar(cliente, estado)

        data2 = conceptos_imagen.cargar(cliente)
        animacion2 = conceptos_imagen.encontrar_animacion(data2, idea_id, concepto_id, proveedor, anim_id)
        if animacion2:
            animacion2["estado"] = "video_generado"
            conceptos_imagen.guardar(cliente, data2)
        return "Video listo, pendiente de revisión."

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=130):
        flash("Generando video…", "ok")
    else:
        flash("Ya se está generando ese video — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


def _conceptos_pendientes(cliente):
    """Estado del flujo imagen-primero, listo para el template: por idea, sus
    escenas, y por escena sus dos imágenes (con trabajo en curso si aplica) y las
    animaciones pendientes de cada imagen ya aprobada."""
    data = conceptos_imagen.cargar(cliente)
    ideas = []
    for idea_id, idea in data.items():
        conceptos = []
        for concepto_id, concepto in idea.get("conceptos", {}).items():
            imagenes = {}
            for proveedor in conceptos_imagen.PROVEEDORES:
                img = dict(concepto[proveedor])
                job_id = _job_id_concepto(cliente, idea_id, concepto_id, proveedor)
                img["trabajo"] = {"job_id": job_id} if trabajos.en_curso(job_id) else None
                animaciones = []
                for anim_id, anim in img.get("animaciones", {}).items():
                    if anim.get("estado") not in ("pendiente",):
                        continue
                    a = {"id": anim_id, **anim}
                    a_job_id = _job_id_animacion(cliente, idea_id, concepto_id, proveedor, anim_id)
                    a["trabajo"] = {"job_id": a_job_id} if trabajos.en_curso(a_job_id) else None
                    animaciones.append(a)
                img["animaciones_pendientes"] = animaciones
                imagenes[proveedor] = img
            conceptos.append({"id": concepto_id, "texto": concepto["texto"], "imagenes": imagenes})
        if conceptos:
            ideas.append({
                "id": idea_id,
                "idea": idea.get("idea"),
                "creado_en": idea.get("creado_en"),
                "conceptos": conceptos,
            })
    return sorted(ideas, key=lambda i: i.get("creado_en", ""), reverse=True)


@app.route("/cliente/<cliente>/idea/<idea_id>/eliminar_visual", methods=["POST"])
def eliminar_idea_visual(cliente, idea_id):
    data = conceptos_imagen.cargar(cliente)
    if idea_id in data:
        del data[idea_id]
        conceptos_imagen.guardar(cliente, data)
        flash("Idea eliminada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


# ---------- flujo "cambiar calzado": una foto real + un producto del catálogo ->
# la misma foto, con el calzado reemplazado. Nada más cambia. ----------

@app.route("/cliente/<cliente>/productos/<producto_id>/imagen")
def imagen_producto(cliente, producto_id):
    """Sirve la foto representativa de un producto del catálogo directo del disco
    (son fijas, no hace falta subirlas a R2)."""
    producto = catalogo_productos.encontrar(cliente, producto_id)
    if not producto:
        flash(f"No encontré el producto {producto_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))
    return send_file(producto["representativa"])


def _swap_items(cliente):
    swaps_dict = swaps_mod.cargar(cliente)
    items = []
    for swap_id, entry in sorted(
        swaps_dict.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True
    ):
        job_id = f"{cliente}__{swap_id}__swap"
        producto = catalogo_productos.encontrar(cliente, entry.get("producto_id"))
        items.append({
            "id": swap_id,
            **entry,
            "producto_nombre": producto["nombre"] if producto else entry.get("producto_id"),
            "proveedor_nombre": NOMBRES_PROVEEDOR_SWAP.get(entry.get("proveedor"), entry.get("proveedor")),
            "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        })
    return items


def _creative_flow_items(cliente):
    data = creative_flow.cargar(cliente)
    items = []
    for cf_id, entry in sorted(
        data.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True
    ):
        job_id = _job_id_creative_flow(cliente, cf_id)
        items.append({
            "id": cf_id,
            **entry,
            "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        })
    return items


@app.route("/cliente/<cliente>/swap")
def ver_swap(cliente):
    """Ruta vieja de cuando 'cambiar calzado' era una página aparte — ahora es
    la primera pestaña de ver_cliente. Se mantiene solo por si algún link viejo
    apunta acá."""
    return redirect(url_for("ver_cliente", cliente=cliente))


# Solo modelos que ven la foto de referencia del producto y clonan la foto/video
# original — nada que solo reciba una descripción en texto del calzado (eso
# perdía fidelidad de color/diseño y no garantizaba preservar la foto).
PROVEEDORES_SWAP_IMAGEN = ("nano_banana", "nano_banana_fal", "qwen_edit")
PROVEEDORES_SWAP_VIDEO = (
    "kling_o1", "luma_modify", "wan_animate_replace", "wan27_edit",
    "seedance25_edit", "kling_o3_pro_edit", "luma_ray32_edit", "wan3_reference",
)

NOMBRES_PROVEEDOR_SWAP = {
    "nano_banana": "Nano Banana",
    "nano_banana_fal": "Nano Banana (vía fal)",
    "qwen_edit": "Qwen Image Edit Plus",
    "kling_o1": "Kling O1",
    "luma_modify": "Luma Ray3 Modify",
    "wan_animate_replace": "Wan-2.2 Animate Replace",
    "wan27_edit": "Wan 2.7 Video Edit",
    "seedance25_edit": "Seedance 2.5 Video Edit",
    "kling_o3_pro_edit": "Kling Omni O3 Pro Video Edit",
    "luma_ray32_edit": "Luma Ray 3.2 Video Edit",
    "wan3_reference": "Wan 3.0 (referencia, no edición)",
    # ya no seleccionables, pero se mantienen para mostrar el nombre en swaps viejos:
    "flux_kontext": "Flux Kontext Pro",
    "higgsfield": "Higgsfield",
    "gemini_omni_edit": "Gemini Omni Flash Edit",
}


def _evaluar_swap_contra_matriz(cliente, swap_id, image_url):
    """Corre la evaluación de marca sobre una imagen (foto final, o un fotograma
    extraído de un video final) y guarda el resultado. No falla el swap si esto
    falla — es un plus, no el resultado principal."""
    try:
        root = marca_mod.cargar_root(cliente)
        invariantes = root.get("invariants", []) if root else []
        if invariantes:
            evaluacion = generador_prompts.evaluar_contra_matriz(image_url, invariantes)
            swaps_mod.actualizar(cliente, swap_id, evaluacion=evaluacion)
            bitacora.registrar(cliente, swap_id, "evaluacion", "ok", "")
    except Exception as e:
        bitacora.registrar(cliente, swap_id, "evaluacion", "error", str(e))


@app.route("/cliente/<cliente>/swap/generar", methods=["POST"])
def generar_swap(cliente):
    """Sube la foto o video del usuario, y lanza en segundo plano el reemplazo de
    calzado con el modelo elegido — uno para foto (PROVEEDORES_SWAP_IMAGEN) y otro
    para video (PROVEEDORES_SWAP_VIDEO), cada tipo con su propia lista de
    candidatos porque no todos los modelos hacen ambos."""
    archivo = request.files.get("foto")
    producto_id = request.form.get("producto_id", "").strip()
    proveedor_foto = request.form.get("proveedor_foto", "nano_banana").strip()
    proveedor_video = request.form.get("proveedor_video", "kling_o1").strip()
    if proveedor_foto not in PROVEEDORES_SWAP_IMAGEN:
        proveedor_foto = "nano_banana"
    if proveedor_video not in PROVEEDORES_SWAP_VIDEO:
        proveedor_video = "kling_o1"

    if not archivo or not archivo.filename:
        flash("Sube una foto o video primero.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))

    producto = catalogo_productos.encontrar(cliente, producto_id)
    if not producto:
        flash("Elige un producto del catálogo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))

    nombre = secure_filename(archivo.filename)
    ext = os.path.splitext(nombre)[1].lower()
    es_video = ext in VIDEO_EXTS
    tipo = "video" if es_video else "foto"
    proveedor = proveedor_video if es_video else proveedor_foto

    subidas_dir = os.path.join(BASE_DIR, "salidas", cliente, "swaps_subidas")
    os.makedirs(subidas_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    foto_local = os.path.join(subidas_dir, f"{ts}_{nombre}")
    archivo.save(foto_local)

    # El encuadre ya no lo elige la persona — se detecta de la foto/video real
    # que subió, para que el resultado mantenga esas mismas proporciones.
    aspect_ratio_detectado = aspect_ratio_mod.detectar_gemini(foto_local) if not es_video else None
    swap_id = swaps_mod.crear(cliente, foto_local, producto_id, aspect_ratio_detectado, proveedor, tipo=tipo)
    job_id = f"{cliente}__{swap_id}__swap"

    def trabajo():
        resultados_dir = os.path.join(BASE_DIR, "salidas", cliente, "swaps")
        os.makedirs(resultados_dir, exist_ok=True)
        negative_prompt = marca_mod.negative_prompt_efectivo(cliente)

        try:
            if tipo == "video":
                local_path = os.path.join(resultados_dir, f"{swap_id}.mp4")
                video_url = r2_uploader.upload_video(foto_local, f"clientes/{cliente}/swaps_subidas/{ts}_{nombre}")
                # Se suben hasta 9 (el máximo que acepta Wan 2.7 Video Edit) — cada
                # cliente recorta a su propio límite (Kling O1 usa las primeras 4).
                referencias_urls = []
                for i, ref_local in enumerate(producto["referencias"][:9]):
                    key = f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref_local)}"
                    referencias_urls.append(r2_uploader.upload_image(ref_local, key))

                if proveedor == "kling_o1":
                    citas = " ".join(f"@Image{i + 1}" for i in range(len(referencias_urls)))
                    prompt = (
                        f"Reemplaza el calzado que lleva puesta la persona por el que se "
                        f"muestra en {citas} — mismo color, diseño y textura exactos. No "
                        f"cambies nada más del video: mismo movimiento, misma persona, "
                        f"mismo fondo, misma iluminación."
                    )
                    resultado_url = kling_o1_client.editar_video(video_url, prompt, referencias_urls=referencias_urls)
                    costo = kling_o1_client.estimate_video()
                elif proveedor == "wan27_edit":
                    prompt = (
                        f"Reemplaza el calzado que lleva puesta la persona por el que se "
                        f"muestra en las imágenes de referencia — mismo color, diseño y "
                        f"textura exactos. No cambies nada más del video: mismo movimiento, "
                        f"misma persona, mismo fondo, misma iluminación."
                    )
                    resultado_url = wavespeed_client.editar_video(video_url, prompt, referencias_urls=referencias_urls)
                    costo = wavespeed_client.estimate_video()
                elif proveedor in wavespeed_video_edit.MODELOS:
                    prompt = (
                        f"Reemplaza el calzado que lleva puesta la persona por el que se "
                        f"muestra en las imágenes de referencia — mismo color, diseño y "
                        f"textura exactos. No cambies nada más del video: mismo movimiento, "
                        f"misma persona, mismo fondo, misma iluminación."
                    )
                    resultado_url = wavespeed_video_edit.editar_video(
                        proveedor, video_url, prompt, referencias_urls=referencias_urls,
                    )
                    costo = wavespeed_video_edit.estimate_video(proveedor)
                elif proveedor == "wan3_reference":
                    # No es edición: genera un video nuevo guiado solo por
                    # imágenes de referencia (el cliente actual no acepta un
                    # video de referencia) — sin garantía de clonar el original.
                    prompt = (
                        f"Video de una persona con {producto['descripcion']}, "
                        f"mismo movimiento, escena y encuadre que el video original."
                    )
                    resultado_url = wan3_client.generar_video(prompt, referencias_urls)
                    costo = wan3_client.estimate_video()
                else:
                    referencia = referencias_urls[0] if referencias_urls else None
                    resultado_url = comparador_modelos.editar_video(
                        proveedor, video_url, producto["descripcion"], referencia_imagen_url=referencia,
                    )
                    costo = comparador_modelos.estimate_video(proveedor)

                resp = requests.get(resultado_url, timeout=180)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                try:
                    url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/swaps/{swap_id}.mp4")
                except Exception:
                    url = resultado_url
            else:
                local_path = os.path.join(resultados_dir, f"{swap_id}.png")
                if proveedor == "nano_banana":
                    img_bytes = nano_banana_client.swap_producto(
                        foto_local, producto["referencias"], negative_prompt=negative_prompt,
                    )
                    with open(local_path, "wb") as f:
                        f.write(img_bytes)
                    costo = nano_banana_client.estimate_image()
                else:  # nano_banana_fal, qwen_edit
                    foto_url = r2_uploader.upload_image(foto_local, f"clientes/{cliente}/swaps_subidas/{ts}_{nombre}")
                    referencias_urls = [
                        r2_uploader.upload_image(ref, f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref)}")
                        for ref in producto["referencias"][:2]
                    ]
                    resultado_url = comparador_modelos.editar_imagen(
                        proveedor, foto_url, producto["descripcion"], referencias_urls=referencias_urls,
                        foto_local_path=foto_local,
                    )
                    resp = requests.get(resultado_url, timeout=120)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    costo = comparador_modelos.estimate_image(proveedor)

                try:
                    url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/swaps/{swap_id}.png")
                except Exception:
                    url = None

            swaps_mod.actualizar(
                cliente, swap_id, estado="listo", resultado_url=url, resultado_local=local_path,
                credits=costo.get("credits"), usd=costo.get("usd"),
            )
            bitacora.registrar(cliente, swap_id, "swap", "ok", local_path)

            if url:
                if tipo == "video":
                    frame_path = os.path.join(resultados_dir, f"{swap_id}.frame.jpg")
                    try:
                        _extraer_frame(local_path, frame_path)
                        frame_url = r2_uploader.upload_image(frame_path, f"clientes/{cliente}/swaps/{swap_id}.frame.jpg")
                        _evaluar_swap_contra_matriz(cliente, swap_id, frame_url)
                    except Exception as e:
                        bitacora.registrar(cliente, swap_id, "evaluacion", "error", str(e))
                else:
                    _evaluar_swap_contra_matriz(cliente, swap_id, url)

            return "Swap listo."
        except Exception as e:
            swaps_mod.actualizar(cliente, swap_id, estado="error", error=str(e))
            bitacora.registrar(cliente, swap_id, "swap", "error", str(e))
            raise

    if proveedor in ("nano_banana", "nano_banana_fal", "qwen_edit"):
        duracion_estimada = 20
    elif proveedor in ("wan27_edit", "seedance25_edit", "kling_o3_pro_edit", "luma_ray32_edit"):
        duracion_estimada = 380  # media reportada por WaveSpeed para estos modelos
    else:
        duracion_estimada = 90
    if trabajos.iniciar(job_id, trabajo, duracion_estimada=duracion_estimada):
        flash("Generando el swap…", "ok")
    else:
        flash("Ya se está generando ese swap — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/swap/<swap_id>/original")
def imagen_swap_original(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    if not entry or not os.path.exists(entry["foto_original_local"]):
        flash("No encontré la foto original.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    return send_file(entry["foto_original_local"])


@app.route("/cliente/<cliente>/swap/<swap_id>/eliminar", methods=["POST"])
def eliminar_swap(cliente, swap_id):
    swaps_mod.eliminar(cliente, swap_id)
    flash("Eliminado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


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
            extra_params=_extra_params_image(item, cliente),
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
            extra_params=_extra_params_video(item2, cliente),
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


@app.route("/cliente/<cliente>/idea/<idea_id>/eliminar", methods=["POST"])
def eliminar_idea(cliente, idea_id):
    data = prompts_mod.cargar(cliente)
    if idea_id in data:
        del data[idea_id]
        prompts_mod.guardar(cliente, data)
        flash("Idea eliminada junto con sus prompts.", "ok")
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


@app.route("/cliente/<cliente>/creative_flow/generar_prompt", methods=["POST"])
def cf_generar_prompt(cliente):
    personajes_sel = request.form.getlist("personajes")
    productos_sel = request.form.getlist("productos")
    escenas_sel = request.form.getlist("escenas")
    accion_central = (request.form.get("accion_central") or "").strip()
    tono = (request.form.get("tono") or "").strip()
    modo = request.form.get("modo", "A")
    platforms = request.form.getlist("platforms")
    try:
        duracion_objetivo = int(request.form.get("duracion_objetivo", 13))
    except ValueError:
        duracion_objetivo = 13
    duracion_objetivo = max(12, min(15, duracion_objetivo))

    if not personajes_sel:
        flash("Elige al menos un personaje — la plantilla necesita @Imagen 1.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not accion_central:
        flash("Describe la acción central del video.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_id = {p["id"]: p for p in catalogo_productos.listar(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}

    personajes = [personajes_por_nombre[n] for n in personajes_sel if n in personajes_por_nombre]
    productos = [productos_por_id[i] for i in productos_sel if i in productos_por_id]
    escenas = [escenas_por_nombre[n] for n in escenas_sel if n in escenas_por_nombre]

    # Lista canónica de referencias, resuelta UNA sola vez acá: personaje ->
    # producto -> escena, descartando cualquier entrada sin URL pública
    # resolvible (ej. video sin .frame.jpg extraído todavía), truncada a 10
    # (límite real de Wan 3.0). generar_prompt_creative_flow() recibe SOLO
    # las entradas que sobrevivieron el filtro, para que su numerado interno
    # de @Imagen N coincida exactamente con esta lista — y cf_generar_video
    # reusa esta misma lista tal cual, sin volver a resolverla.
    combinados = (
        [("personaje", p) for p in personajes] +
        [("producto", p) for p in productos] +
        [("escena", e) for e in escenas]
    )

    def _url_de(tipo, item):
        return item.get("representativa_url") if tipo == "producto" else item.get("url")

    combinados_validos = [(t, item) for t, item in combinados if _url_de(t, item)][:10]
    personajes_validos = [item for t, item in combinados_validos if t == "personaje"]
    productos_validos = [item for t, item in combinados_validos if t == "producto"]
    escenas_validas = [item for t, item in combinados_validos if t == "escena"]
    referencias_urls = [_url_de(t, item) for t, item in combinados_validos]

    cf_id = creative_flow.crear(
        cliente, personajes_sel, productos_sel, escenas_sel,
        accion_central, duracion_objetivo, tono, modo,
        referencias_urls=referencias_urls, platforms=platforms,
    )

    if not referencias_urls:
        creative_flow.actualizar(
            cliente, cf_id, estado="error",
            error="Ninguna de las referencias elegidas tiene una URL pública válida — revisa que las imágenes estén subidas a R2.",
        )
        flash("Ninguna de las referencias elegidas tiene una URL pública válida — revisa que las imágenes estén subidas a R2.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    try:
        guia_estilo = marca_mod.guia_efectiva(cliente)
        prompt_relleno = generador_prompts.generar_prompt_creative_flow(
            personajes_validos, productos_validos, escenas_validas, accion_central, duracion_objetivo,
            tono, modo, guia_estilo=guia_estilo,
        )
        creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt_relleno)
        flash("Prompt generado — revísalo antes de generar el video.", "ok")
    except Exception as e:
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        flash(f"No pude generar el prompt: {e}", "error")

    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/regenerar_prompt", methods=["POST"])
def cf_regenerar_prompt(cliente, cf_id):
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        flash("No encontré esa sesión de CreativeFlowPlus.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_id = {p["id"]: p for p in catalogo_productos.listar(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}
    personajes = [personajes_por_nombre[n] for n in entry["personajes_ids"] if n in personajes_por_nombre]
    productos = [productos_por_id[i] for i in entry["productos_ids"] if i in productos_por_id]
    escenas = [escenas_por_nombre[n] for n in entry["escenas_ids"] if n in escenas_por_nombre]

    try:
        guia_estilo = marca_mod.guia_efectiva(cliente)
        prompt_relleno = generador_prompts.generar_prompt_creative_flow(
            personajes, productos, escenas, entry["accion_central"], entry["duracion_objetivo"],
            entry["tono"], entry["modo"], guia_estilo=guia_estilo,
        )
        creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt_relleno, error=None)
        flash("Prompt regenerado.", "ok")
    except Exception as e:
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        flash(f"No pude regenerar el prompt: {e}", "error")

    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/guardar_prompt", methods=["POST"])
def cf_guardar_prompt(cliente, cf_id):
    prompt_editado = (request.form.get("prompt_relleno") or "").strip()
    if not prompt_editado:
        flash("El prompt no puede quedar vacío.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_editado)
    flash("Prompt guardado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/descartar", methods=["POST"])
def cf_descartar(cliente, cf_id):
    creative_flow.eliminar(cliente, cf_id)
    flash("Sesión de CreativeFlowPlus descartada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/generar_video", methods=["POST"])
def cf_generar_video(cliente, cf_id):
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry or not entry.get("prompt_relleno"):
        flash("No encontré un prompt listo para esa sesión.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    # Guardia anti-reenvío: sin esto, un segundo POST (back del navegador +
    # reenviar, una pestaña vieja) después de que el video ya se generó
    # dispara una SEGUNDA generación paga, sobreescribe el .mp4 y resetea la
    # entrada en estado_videos.json aunque ya esté aprobada/publicada.
    # Permite reintentar tras un error, pero no tras video_generando/listo.
    if entry.get("estado") not in ("prompt_listo", "error"):
        flash("Este video ya se generó o se está generando — no se puede volver a disparar.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    # Reusa TAL CUAL la lista canónica que ya se resolvió y filtró en
    # cf_generar_prompt (guardada como entry["referencias_urls"]) — nunca la
    # vuelve a resolver acá, porque un segundo cómputo podría dar un
    # resultado distinto (ej. una escena subida/borrada entre medio) y
    # desincronizar el índice @Imagen N que Claude ya usó al escribir el
    # prompt del índice real que recibe Wan 3.0.
    referencias = entry.get("referencias_urls") or []
    if not referencias:
        flash("No hay URLs públicas de referencia disponibles todavía.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    duracion = entry["duracion_objetivo"]
    prompt_texto = entry["prompt_relleno"]
    platforms = entry.get("platforms", [])
    aspect_ratio = _aspect_ratio_para_plataformas(platforms)
    job_id = _job_id_creative_flow(cliente, cf_id)

    def trabajo():
        out_dir = os.path.join(BASE_DIR, "salidas", cliente)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{cf_id}.mp4")

        try:
            video_url_wan = wan3_client.generar_video(
                prompt_texto, referencias, duration=duracion, resolution="720p",
                aspect_ratio=aspect_ratio,
            )
            costo = wan3_client.estimate_video(duration=duracion, resolution="720p")
            resp = requests.get(video_url_wan, timeout=180)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
            bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
            creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
            raise

        try:
            video_url = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{cf_id}.mp4")
        except Exception:
            video_url = video_url_wan

        creative_flow.actualizar(
            cliente, cf_id, estado="video_listo", video_url=video_url, video_local=out_path,
            credits=costo.get("credits"), usd=costo.get("usd"),
        )

        estado = estado_mod.cargar(cliente)
        estado[cf_id] = {
            "prompt": prompt_texto,
            "image_url": referencias[0],
            "title": cf_id,
            "caption": entry["accion_central"],
            "platforms": platforms,
            "video_local": out_path,
            "video_url": video_url,
            "estado": "pendiente",
            "generado_en": datetime.now().isoformat(),
            "publicado_en": None,
        }
        estado_mod.guardar(cliente, estado)
        return "Video de CreativeFlowPlus listo, pendiente de revisión."

    # Escribe estado="video_generando" ANTES de lanzar el job (no después):
    # si trabajo() falla instantáneo (ej. falta WAVESPEED_API_KEY), el hilo
    # puede escribir estado="error" antes de que el hilo principal alcance a
    # escribir "video_generando", pisando el error y dejando la sesión
    # atascada en "generando" para siempre. Mismo patrón que swaps.crear().
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    if trabajos.iniciar(job_id, trabajo, duracion_estimada=180):
        flash("Generando el video con Wan 3.0…", "ok")
    else:
        # Ya había un job corriendo — no hace falta revertir el estado, ya
        # estaba en "video_generando" legítimamente.
        flash("Ya se está generando ese video — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


if __name__ == "__main__":
    # use_reloader=False a propósito: ahora hay generaciones corriendo en hilos
    # de fondo, y el auto-reload de Flask mata el proceso completo (y con él,
    # cualquier generación en curso) apenas detecta un cambio de archivo.
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
