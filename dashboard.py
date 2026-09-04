"""
Dashboard web local: clientes, personajes, briefs/prompts, videos, aprobación y
estado de publicación por plataforma — todo en una página.

Uso:
    python dashboard.py
    (abre http://127.0.0.1:5050 en tu navegador)

Solo corre en tu máquina (127.0.0.1), no queda expuesto a internet.
"""
import os
import socket
import subprocess
import threading

import requests

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from datetime import datetime

import estado as estado_mod
import prompts as prompts_mod
import marca as marca_mod
import conceptos_imagen
import catalogo_productos
import swaps as swaps_mod
import banco_prompts
import bitacora
import informe
import mapa_corporal
import prompt_swap
import proyectos
import trabajos
import generador_prompts
from providers import image_provider
from providers import nano_banana_client, video_provider, kling_o1_client, comparador_modelos, wavespeed_client
from providers import wavespeed_video_edit, wan3_client, wavespeed_imagen
from providers import aspect_ratio as aspect_ratio_mod
import ads as ads_mod
from meta_ads import campaign as meta_campaign
from meta_ads import adset as meta_adset
from meta_ads import ad as meta_ad
from meta_ads import creative as meta_creative
from meta_ads import insights as meta_insights
from meta_ads.targeting import Targeting
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


@app.after_request
def _sin_cache(resp):
    """Ni el HTML ni el JSON de estado deben cachearse: son estado vivo que cambia
    solo (una generación que termina, una barra de progreso). Flask no mandaba
    ningún header de caché, y ya hubo un caso de navegador sirviendo HTML viejo
    que obligó a un recarga dura."""
    if resp.mimetype in ("text/html", "application/json"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/trabajo/<path:job_id>/estado")
def estado_trabajo(job_id):
    """El navegador consulta esto cada poco tiempo para actualizar la barra de
    progreso de una generación en curso (imagen, video, o publicación)."""
    info = trabajos.consultar(job_id)
    if info is None:
        # Mismas claves que devuelve trabajos.consultar(), para que el JS no tenga
        # que distinguir casos ni leer undefined.
        return jsonify({
            "estado": "desconocido", "progreso": 0, "elapsed": 0, "mensaje": None,
            "etapa": None, "detalle": None, "progreso_real": False,
        })
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


def _productos_referencia(cliente):
    """Imagen de referencia suelta de un producto para CreativeFlowPlus — NO es
    el catálogo de "Cambiar calzado" (catalogo_productos.py, que exige varias
    fotos por producto + nombre/descripción a mano en el código). Acá alcanza
    con una imagen, igual que personajes/escenas."""
    return _listar_assets(cliente, "productos_referencia")


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


@app.route("/cliente/<cliente>/producto_referencia/subir", methods=["POST"])
def subir_producto_referencia(cliente):
    ok, mensaje = _subir_asset(cliente, "productos_referencia", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/producto_referencia/<nombre>/eliminar", methods=["POST"])
def eliminar_producto_referencia(cliente, nombre):
    _eliminar_asset(cliente, "productos_referencia", secure_filename(nombre))
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
        productos_referencia=_productos_referencia(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        informe=informe.completo(cliente),
        productos=_productos_con_uso(cliente),
        tipos_producto=prompt_swap.TIPOS,
        zonas_cuerpo=mapa_corporal.ZONAS,
        presets_cuerpo=mapa_corporal.PRESETS,
        etiquetas_presets=mapa_corporal.ETIQUETAS_PRESETS,
        banco_prompts=banco_prompts.listar(),
        nombre_proyecto=proyectos.nombre_visible(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
        creative_flow_items=_creative_flow_items(cliente),
        ads=ads_mod.cargar(cliente),
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
            trabajos.reportar(job_id, etapa=ETAPA_MODELO)
            est = image_provider.generar_imagen(
                proveedor, referencia_url, prompt, local_path,
                negative_prompt=negative_prompt, extra_params=extra_params,
            )
            trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_IMAGEN)
            error_storage = None
            try:
                url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/imagenes/{nombre}")
            except Exception as e:
                # La imagen existe en disco; lo que falló fue R2. Se registra para
                # que la plantilla no la reporte como "generación interrumpida".
                url = None
                error_storage = str(e)
                bitacora.registrar(cliente, video_id, "imagen_storage", "error", str(e))
            campos = {
                "estado": "listo", "url": url, "local": local_path,
                "usd": est.get("usd"), "error_storage": error_storage,
            }
            if proveedor == "higgsfield":
                campos["credits"] = est.get("credits")
            conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, **campos)
            bitacora.registrar(cliente, video_id, "imagen", "ok", local_path)
            return "Imagen lista."
        except Exception as e:
            conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="error", error=str(e))
            bitacora.registrar(cliente, video_id, "imagen", "error", str(e))
            raise

    return trabajos.iniciar(
        job_id, trabajo,
        duracion_estimada=45 if proveedor == "higgsfield" else 20,
        etapas=ETAPAS_IMAGEN,
    )


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
            # video_provider.generar_video no recibe on_progreso (no tiene forma
            # de saber a qué job pertenece), así que acá la señal honesta son las
            # etapas: descarga incluida, el provider deja el .mp4 en out_path.
            trabajos.reportar(job_id, etapa=ETAPA_MODELO)
            est = video_provider.generar_video(
                proveedor_video, imagen_url, prompt_texto, out_path,
                aspect_ratio=aspect_ratio, negative_prompt=negative_prompt,
                extra_params=_extra_params_video(item2, cliente),
            )
            bitacora.registrar(cliente, video_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, video_id, "generacion", "error", str(e))
            raise

        trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
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

    # ETAPAS_VIDEO sin ETAPA_DESCARGAR: el provider descarga por su cuenta dentro
    # de generar_video, así que ese paso no se puede anunciar por separado.
    if trabajos.iniciar(
        job_id, trabajo, duracion_estimada=130,
        etapas=[(ETAPA_MODELO, 90), (ETAPA_GUARDAR_VIDEO, 10)],
    ):
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


@app.route("/cliente/<cliente>/productos/<producto_id>/imagen/<nombre>")
def imagen_producto_archivo(cliente, producto_id, nombre):
    """Sirve UNA foto concreta del producto — la pantalla de gestión muestra
    todas las referencias, no solo la representativa."""
    try:
        carpeta = catalogo_productos.carpeta_de(cliente, producto_id)
    except ValueError:
        abort(404)
    ruta = os.path.join(carpeta, secure_filename(nombre))
    if not os.path.isfile(ruta):
        abort(404)
    return send_file(ruta)


def _productos_con_uso(cliente):
    """El catálogo + cuántos swaps ya generados usa cada producto. Ese número se
    le muestra al usuario en el modal ANTES de borrar: esas tarjetas no se
    rompen (siguen mostrando el id crudo), pero pierden el nombre y la foto.
    Se cuenta de una sola pasada sobre swaps.json, no una por producto."""
    usos = {}
    for entry in swaps_mod.cargar(cliente).values():
        pid = entry.get("producto_id")
        if pid:
            usos[pid] = usos.get(pid, 0) + 1
    productos = catalogo_productos.listar(cliente)
    for p in productos:
        p["usos"] = usos.get(p["id"], 0)
    return productos


@app.route("/cliente/<cliente>/nombre", methods=["POST"])
def guardar_nombre_proyecto(cliente):
    """Cambia SOLO el nombre visible. La carpeta (el id) no se toca: es la clave
    de las rutas de R2, del historial y de los tokens de publicación."""
    proyectos.guardar_nombre(cliente, request.form.get("nombre"))
    flash("Nombre del proyecto actualizado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/productos/crear", methods=["POST"])
def crear_producto(cliente):
    nombre = (request.form.get("nombre") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not nombre:
        flash("Ponle un nombre al producto.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    if not archivos:
        flash("Sube al menos una foto del producto.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    try:
        producto_id = catalogo_productos.crear(
            cliente, nombre, descripcion, tipo=request.form.get("tipo"),
            zonas=request.form.getlist("zonas"))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))

    guardadas = _guardar_fotos_producto(cliente, producto_id, archivos)
    if not guardadas:
        # Sin ninguna foto válida el producto no aparecería en el catálogo:
        # mejor deshacer que dejar una carpeta fantasma.
        catalogo_productos.eliminar(cliente, producto_id)
        flash("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).", "error")
    else:
        flash(f"Producto creado: {nombre} ({guardadas} foto(s)).", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


def _guardar_fotos_producto(cliente, producto_id, archivos):
    """Guarda las fotos en la carpeta del producto y devuelve cuántas entraron.
    Quedan SOLO en disco a propósito: catalogo_productos las lee de ahí y el
    swap las sube a R2 recién cuando se va a generar."""
    carpeta = catalogo_productos.carpeta_de(cliente, producto_id)
    os.makedirs(carpeta, exist_ok=True)
    guardadas = 0
    for archivo in archivos:
        nombre = secure_filename(archivo.filename)
        if not nombre.lower().endswith(catalogo_productos.IMAGE_EXTS):
            continue
        archivo.save(os.path.join(carpeta, nombre))
        guardadas += 1
    return guardadas


@app.route("/cliente/<cliente>/productos/<producto_id>/actualizar", methods=["POST"])
def actualizar_producto(cliente, producto_id):
    try:
        catalogo_productos.actualizar(
            cliente, producto_id,
            nombre=request.form.get("nombre"),
            descripcion=request.form.get("descripcion"),
            tipo=request.form.get("tipo"),
            zonas=request.form.getlist("zonas"),
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    flash("Producto actualizado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/subir", methods=["POST"])
def subir_imagen_producto(cliente, producto_id):
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not archivos:
        flash("No elegiste ninguna foto.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    try:
        guardadas = _guardar_fotos_producto(cliente, producto_id, archivos)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    if guardadas:
        flash(f"{guardadas} foto(s) agregada(s).", "ok")
    else:
        flash("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/<nombre>/eliminar", methods=["POST"])
def eliminar_imagen_producto(cliente, producto_id, nombre):
    try:
        ok, mensaje = catalogo_productos.eliminar_imagen(cliente, producto_id, nombre)
    except ValueError as e:
        ok, mensaje = False, str(e)
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/productos/<producto_id>/eliminar", methods=["POST"])
def eliminar_producto(cliente, producto_id):
    """Borra el producto y TODAS sus fotos del disco. Irreversible — por eso la
    plantilla lo pide con un modal que nombra el producto y avisa cuántos swaps
    ya generados lo referencian."""
    producto = catalogo_productos.encontrar(cliente, producto_id)
    nombre = producto["nombre"] if producto else producto_id
    try:
        catalogo_productos.eliminar(cliente, producto_id)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    flash(f"Producto eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


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
        item = {
            "id": cf_id,
            **entry,
            "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        }
        # Estimado real vía wan3_client.estimate_video() en vez de un número
        # calculado a mano en la plantilla (duracion * 0.10) — usa la misma
        # tabla de precios (COSTO_USD_POR_SEGUNDO) que generar_video() real,
        # así el botón nunca muestra un costo distinto al que se cobra.
        if entry.get("estado") == "prompt_listo":
            item["costo_estimado"] = wan3_client.estimate_video(
                duration=entry["duracion_objetivo"], resolution="720p",
            )
        items.append(item)
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
PROVEEDORES_SWAP_IMAGEN = ("nano_banana", "nano_banana_fal", "qwen_edit", "nano_banana_pro_ultra", "seedream_v5_pro")
PROVEEDORES_SWAP_VIDEO = (
    "kling_o1", "luma_modify", "wan_animate_replace", "wan27_edit",
    "seedance25_edit", "kling_o3_pro_edit", "luma_ray32_edit",
)

NOMBRES_PROVEEDOR_SWAP = {
    "nano_banana": "Nano Banana",
    "nano_banana_fal": "Nano Banana (vía fal)",
    "qwen_edit": "Qwen Image Edit Plus",
    "nano_banana_pro_ultra": "Nano Banana Pro Ultra (4k)",
    "seedream_v5_pro": "Seedream V5.0 Pro Edit (2k)",
    "kling_o1": "Kling O1",
    "luma_modify": "Luma Ray3 Modify",
    "wan_animate_replace": "Wan-2.2 Animate Replace",
    "wan27_edit": "Wan 2.7 Video Edit",
    "seedance25_edit": "Seedance 2.5 Video Edit",
    "kling_o3_pro_edit": "Kling Omni O3 Pro Video Edit",
    "luma_ray32_edit": "Luma Ray 3.2 Video Edit",
    # ya no seleccionables, pero se mantienen para mostrar el nombre en swaps viejos:
    "flux_kontext": "Flux Kontext Pro",
    "higgsfield": "Higgsfield",
    "gemini_omni_edit": "Gemini Omni Flash Edit",
    "wan3_reference": "Wan 3.0 (referencia, no edición)",
}


# Etapas reales del swap. Los nombres se usan en DOS lados (al declararlas en
# trabajos.iniciar y al anunciarlas con trabajos.reportar), así que van en
# constantes para que no puedan desincronizarse por un typo. Los pesos son
# "qué fracción del tiempo se lleva más o menos cada paso" — la llamada al
# modelo es de lejos la más larga.
ETAPA_SUBIR_ORIGINAL = "Subiendo tu video original"
ETAPA_SUBIR_REFERENCIAS = "Subiendo las fotos del producto"
ETAPA_PREPARAR_FOTO = "Preparando la imagen"
ETAPA_MODELO = "Generando con el modelo"
ETAPA_DESCARGAR = "Descargando el resultado"
ETAPA_GUARDAR = "Guardando y evaluando la marca"
ETAPA_GUARDAR_VIDEO = "Guardando el video"
ETAPA_MEJORAR = "Mejorando la calidad de la imagen"
ETAPA_GUARDAR_IMAGEN = "Guardando la imagen"

ETAPAS_SWAP_VIDEO = [
    (ETAPA_SUBIR_ORIGINAL, 5),
    (ETAPA_SUBIR_REFERENCIAS, 10),
    (ETAPA_MODELO, 70),
    (ETAPA_DESCARGAR, 5),
    (ETAPA_GUARDAR, 10),
]
ETAPAS_SWAP_FOTO = [
    (ETAPA_PREPARAR_FOTO, 10),
    (ETAPA_MODELO, 70),
    (ETAPA_GUARDAR, 20),
]
# Con la mejora activada hay una llamada más al proveedor entre medio.
ETAPAS_SWAP_FOTO_MEJORADA = [
    (ETAPA_PREPARAR_FOTO, 8),
    (ETAPA_MODELO, 57),
    (ETAPA_MEJORAR, 20),
    (ETAPA_GUARDAR, 15),
]
# CreativeFlowPlus: Wan 3.0 se lleva casi todo el tiempo (timeout de 1200s).
ETAPAS_CREATIVE_FLOW = [
    (ETAPA_MODELO, 85),
    (ETAPA_DESCARGAR, 8),
    (ETAPA_GUARDAR_VIDEO, 7),
]

# Pipeline clásico (prompt -> imagen candidata -> video) y flujo imagen-primero.
# Estos trabajos iban SIN etapas y el usuario veía "Generando…" a secas durante
# minutos, justo en el camino que es el corazón del repo. El descargar/subir es
# corto comparado con el poll al modelo, de ahí los pesos.
ETAPAS_IMAGEN = [
    (ETAPA_MODELO, 78),
    (ETAPA_GUARDAR_IMAGEN, 22),
]
ETAPAS_VIDEO = [
    (ETAPA_MODELO, 85),
    (ETAPA_DESCARGAR, 8),
    (ETAPA_GUARDAR_VIDEO, 7),
]

# Los proveedores hablan en sus propios códigos de estado; esto es lo único
# honesto que se puede mostrar de ellos (ninguno da un porcentaje numérico).
_FASES_PROVEEDOR = {
    "IN_QUEUE": "en cola",
    "IN_PROGRESS": "el modelo está trabajando",
    "created": "en cola",
    "processing": "el modelo está trabajando",
    "queued": "en cola",
    "starting": "arrancando",
    "running": "el modelo está trabajando",
    "in_progress": "el modelo está trabajando",
    "pending": "en cola",
}

# Estados terminales: el poll también los emite en su última vuelta, pero mostrar
# "completed" como detalle no le dice nada al usuario — la etapa siguiente ya se
# encarga de contar qué sigue.
_FASES_TERMINALES = ("COMPLETED", "completed", "succeeded", "success", "done")


def _texto_fase(info):
    """Traduce a español el estado crudo que reporta un proveedor durante el poll.
    Con fallback: si aparece una fase que no conocemos se muestra tal cual en vez
    de tragarse la información (los proveedores agregan estados sin avisar)."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = _FASES_PROVEEDOR.get(fase, fase)
    if not texto:
        return None
    posicion = info.get("queue_position")
    if posicion is not None:
        texto = f"{texto} (puesto {posicion})"
    return texto


def _avisar_fase_de(job_id):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Envuelto en try/except porque un fallo REPORTANDO
    jamás puede tumbar una generación que ya gastó créditos."""
    def avisar_fase(info):
        try:
            texto = _texto_fase(info)
            if texto:
                trabajos.reportar(job_id, detalle=texto)
        except Exception:
            pass
    return avisar_fase


def _evaluar_swap_contra_matriz(cliente, swap_id, image_url):
    """Corre la evaluación de marca sobre una imagen (foto final, o un fotograma
    extraído de un video final) y guarda el resultado. No falla el swap si esto
    falla — es un plus, no el resultado principal."""
    # El desenlace se PERSISTE (evaluacion_estado), no solo se anota en la
    # bitácora: sin eso, un fallo silencioso dejaba la tarjeta diciendo
    # "Evaluando cumplimiento de marca…" para siempre, porque `evaluacion` se
    # quedaba en None y nada volvía a tocar esa entrada. Hoy hay 6 swaps así en
    # disco. Lo mismo cuando el cliente no tiene invariantes definidas: no es un
    # error, pero la evaluación tampoco va a llegar nunca.
    try:
        root = marca_mod.cargar_root(cliente)
        invariantes = root.get("invariants", []) if root else []
        if not invariantes:
            swaps_mod.actualizar(cliente, swap_id, evaluacion_estado="sin_matriz")
            return
        evaluacion = generador_prompts.evaluar_contra_matriz(image_url, invariantes)
        swaps_mod.actualizar(cliente, swap_id, evaluacion=evaluacion, evaluacion_estado="ok")
        bitacora.registrar(cliente, swap_id, "evaluacion", "ok", "")
    except Exception as e:
        swaps_mod.actualizar(cliente, swap_id, evaluacion_estado="error", evaluacion_error=str(e))
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
    proveedor_video = request.form.get("proveedor_video", "seedance25_edit").strip()
    # Segunda pasada opcional de calidad. Solo aplica a FOTO: el upscaler de
    # Bria es de imagen, no de video.
    mejorar_calidad = bool(request.form.get("mejorar_calidad"))
    if proveedor_foto not in PROVEEDORES_SWAP_IMAGEN:
        proveedor_foto = "nano_banana"
    if proveedor_video not in PROVEEDORES_SWAP_VIDEO:
        proveedor_video = "seedance25_edit"

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
    mejorar_calidad = mejorar_calidad and not es_video
    swap_id = swaps_mod.crear(cliente, foto_local, producto_id, aspect_ratio_detectado, proveedor, tipo=tipo)
    job_id = f"{cliente}__{swap_id}__swap"

    # Cada etapa se anuncia con trabajos.reportar(job_id, ...) para que la barra
    # deje de ser un número inventado: el usuario ve en qué paso real va.
    avisar_fase = _avisar_fase_de(job_id)

    def trabajo():
        try:
            # os.makedirs y negative_prompt_efectivo estaban FUERA del try:
            # negative_prompt_efectivo lee marca/root.json y revienta si ese
            # archivo está mal formado, dejando el job en "error" pero el swap
            # en "generando" para siempre en disco (tarjeta zombie).
            resultados_dir = os.path.join(BASE_DIR, "salidas", cliente, "swaps")
            os.makedirs(resultados_dir, exist_ok=True)
            negative_prompt = marca_mod.negative_prompt_efectivo(cliente)
            # El TIPO del producto decide qué prompt se arma: un calzado va en
            # los pies y no puede sobresalir del contorno del pie; una cobija se
            # drapea sobre la persona o el mueble y sigue sus pliegues.
            tipo_producto = producto.get("tipo")
            # Instrucción de ubicación y proporción derivada del mapa corporal.
            # None si el producto no va sobre una persona (cobija, objeto).
            mapa_producto = producto.get("mapa_texto")
            # Si la subida a R2 falla, el resultado SÍ existe en disco. Se guarda
            # el motivo para que la plantilla pueda decir la verdad ("se generó
            # pero no se pudo subir, está acá") en vez de dar por muerta una
            # generación que sí terminó y ya se pagó.
            error_storage = None

            if tipo == "video":
                local_path = os.path.join(resultados_dir, f"{swap_id}.mp4")
                trabajos.reportar(job_id, etapa=ETAPA_SUBIR_ORIGINAL)
                video_url = r2_uploader.upload_video(foto_local, f"clientes/{cliente}/swaps_subidas/{ts}_{nombre}")
                # Se suben hasta 9 (el máximo que acepta Wan 2.7 Video Edit) — cada
                # cliente recorta a su propio límite (Kling O1 usa las primeras 4).
                referencias = producto["referencias"][:9]
                trabajos.reportar(job_id, etapa=ETAPA_SUBIR_REFERENCIAS)
                referencias_urls = []
                for i, ref_local in enumerate(referencias):
                    # Son 1-2MB cada una y suben en serie: sin este detalle el
                    # tramo se percibía como una barra colgada.
                    trabajos.reportar(
                        job_id,
                        progreso=100.0 * i / len(referencias),
                        detalle=f"foto {i + 1} de {len(referencias)}",
                    )
                    key = f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref_local)}"
                    referencias_urls.append(r2_uploader.upload_image(ref_local, key))

                trabajos.reportar(job_id, etapa=ETAPA_MODELO)
                if proveedor == "kling_o1":
                    citas = " ".join(f"@Image{i + 1}" for i in range(len(referencias_urls)))
                    prompt = prompt_swap.prompt_video(tipo_producto, citas=citas, mapa=mapa_producto)
                    resultado_url = kling_o1_client.editar_video(
                        video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_fase,
                    )
                    costo = kling_o1_client.estimate_video()
                elif proveedor == "wan27_edit":
                    prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                    resultado_url = wavespeed_client.editar_video(
                        video_url, prompt, referencias_urls=referencias_urls, on_progreso=avisar_fase,
                    )
                    costo = wavespeed_client.estimate_video()
                elif proveedor in wavespeed_video_edit.MODELOS:
                    prompt = prompt_swap.prompt_video(tipo_producto, mapa=mapa_producto)
                    resultado_url = wavespeed_video_edit.editar_video(
                        proveedor, video_url, prompt, referencias_urls=referencias_urls,
                        on_progreso=avisar_fase,
                    )
                    costo = wavespeed_video_edit.estimate_video(proveedor)
                else:
                    referencia = referencias_urls[0] if referencias_urls else None
                    resultado_url = comparador_modelos.editar_video(
                        proveedor, video_url, producto["descripcion"], referencia_imagen_url=referencia,
                        on_progreso=avisar_fase, tipo=tipo_producto, mapa=mapa_producto,
                    )
                    costo = comparador_modelos.estimate_video(proveedor)

                trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
                resp = requests.get(resultado_url, timeout=180)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
                try:
                    url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/swaps/{swap_id}.mp4")
                except Exception as e:
                    # Acá sí hay plan B: la URL del proveedor sirve igual para
                    # mostrar y publicar, así que no queda "listo sin url".
                    url = resultado_url
                    error_storage = str(e)
                    bitacora.registrar(cliente, swap_id, "storage", "error", str(e))
            else:
                local_path = os.path.join(resultados_dir, f"{swap_id}.png")
                trabajos.reportar(job_id, etapa=ETAPA_PREPARAR_FOTO)
                if proveedor == "nano_banana":
                    trabajos.reportar(job_id, etapa=ETAPA_MODELO)
                    img_bytes = nano_banana_client.swap_producto(
                        foto_local, producto["referencias"], negative_prompt=negative_prompt,
                        tipo=tipo_producto, mapa=mapa_producto,
                    )
                    with open(local_path, "wb") as f:
                        f.write(img_bytes)
                    costo = nano_banana_client.estimate_image()
                else:  # nano_banana_fal, qwen_edit, nano_banana_pro_ultra
                    foto_url = r2_uploader.upload_image(foto_local, f"clientes/{cliente}/swaps_subidas/{ts}_{nombre}")
                    # Nano Banana Pro Ultra acepta hasta 14 imágenes (13 de
                    # referencia + la foto); los de fal solo 2. Se sube lo que
                    # cada uno puede aprovechar, ni una más.
                    if proveedor == "nano_banana_pro_ultra":
                        tope_refs = 13
                    elif proveedor == "seedream_v5_pro":
                        tope_refs = 9   # acepta 10 en total, una la ocupa la foto
                    else:
                        tope_refs = 2
                    referencias_urls = [
                        r2_uploader.upload_image(ref, f"clientes/{cliente}/productos/{producto_id}/{os.path.basename(ref)}")
                        for ref in producto["referencias"][:tope_refs]
                    ]
                    trabajos.reportar(job_id, etapa=ETAPA_MODELO)
                    if proveedor == "nano_banana_pro_ultra":
                        referencias_lista = "\n".join(
                            f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)."
                            for i in range(len(referencias_urls))
                        )
                        resultado_url = wavespeed_imagen.editar_imagen(
                            foto_url, prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                            referencias_urls=referencias_urls,
                            aspect_ratio=aspect_ratio_mod.detectar_wavespeed_nano_banana_pro(foto_local),
                            on_progreso=avisar_fase,
                        )
                        costo = wavespeed_imagen.estimate_image()
                    elif proveedor == "seedream_v5_pro":
                        referencias_lista = "\n".join(
                            f"Imagen {i + 2}: referencia del producto (mismo producto, otro ángulo)."
                            for i in range(len(referencias_urls))
                        )
                        resultado_url = wavespeed_imagen.editar_imagen_seedream(
                            foto_url,
                            prompt_swap.prompt_imagen(tipo_producto, referencias_lista, mapa=mapa_producto),
                            referencias_urls=referencias_urls, on_progreso=avisar_fase,
                        )
                        costo = wavespeed_imagen.estimate_seedream(n_imagenes=len(referencias_urls) + 1)
                    else:
                        resultado_url = comparador_modelos.editar_imagen(
                            proveedor, foto_url, producto["descripcion"], referencias_urls=referencias_urls,
                            foto_local_path=foto_local, on_progreso=avisar_fase, tipo=tipo_producto, mapa=mapa_producto,
                        )
                        costo = comparador_modelos.estimate_image(proveedor)
                    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
                    resp = requests.get(resultado_url, timeout=120)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        f.write(resp.content)

                if mejorar_calidad:
                    # Segunda pasada: agranda SIN regenerar (Bria). Necesita una
                    # URL pública, así que primero sube el resultado del swap a
                    # R2 y después reemplaza el archivo local por el mejorado.
                    trabajos.reportar(job_id, etapa=ETAPA_MEJORAR)
                    try:
                        url_para_mejorar = r2_uploader.upload_image(
                            local_path, f"clientes/{cliente}/swaps/{swap_id}.previo.png")
                        ancho_prev, alto_prev = aspect_ratio_mod.dimensiones(local_path)
                        mejorada_url = wavespeed_imagen.mejorar_calidad(
                            url_para_mejorar,
                            factor=wavespeed_imagen.factor_seguro(ancho_prev, alto_prev),
                            on_progreso=avisar_fase,
                        )
                        resp_mejorada = requests.get(mejorada_url, timeout=180)
                        resp_mejorada.raise_for_status()
                        with open(local_path, "wb") as f:
                            f.write(resp_mejorada.content)
                        costo = {
                            "credits": costo.get("credits"),
                            "usd": round((costo.get("usd") or 0) + wavespeed_imagen.COSTO_USD_UPSCALE, 3),
                        }
                    except Exception as e:
                        # La mejora es un extra: si falla, el swap YA está hecho y
                        # se entrega igual. Perder el resultado por el paso opcional
                        # sería tirar a la basura lo que el usuario ya pagó.
                        bitacora.registrar(cliente, swap_id, "mejora_calidad", "error", str(e))

                trabajos.reportar(job_id, etapa=ETAPA_GUARDAR)
                try:
                    url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/swaps/{swap_id}.png")
                except Exception as e:
                    # Sin plan B (nano_banana devuelve bytes, no una URL): queda
                    # "listo" sin resultado_url. La plantilla necesita saber que
                    # el archivo existe igual, si no muestra un mensaje falso.
                    url = None
                    error_storage = str(e)
                    bitacora.registrar(cliente, swap_id, "storage", "error", str(e))

            swaps_mod.actualizar(
                cliente, swap_id, estado="listo", resultado_url=url, resultado_local=local_path,
                credits=costo.get("credits"), usd=costo.get("usd"), error_storage=error_storage,
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
    elif proveedor in ("nano_banana_pro_ultra", "seedream_v5_pro"):
        duracion_estimada = 60  # sale en 4k: tarda bastante más que los de 1k
    elif proveedor in ("wan27_edit", "seedance25_edit", "kling_o3_pro_edit", "luma_ray32_edit"):
        duracion_estimada = 380  # media reportada por WaveSpeed para estos modelos
    else:
        duracion_estimada = 90
    if mejorar_calidad:
        duracion_estimada += 25  # la segunda pasada del upscaler
    if tipo == "video":
        etapas = ETAPAS_SWAP_VIDEO
    else:
        etapas = ETAPAS_SWAP_FOTO_MEJORADA if mejorar_calidad else ETAPAS_SWAP_FOTO
    if trabajos.iniciar(job_id, trabajo, duracion_estimada=duracion_estimada, etapas=etapas):
        flash("Generando el swap…", "ok")
    else:
        flash("Ya se está generando ese swap — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/swap/<swap_id>/original")
def imagen_swap_original(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    # Las entradas reconstruidas desde la bitácora no tienen foto original: la
    # bitácora guarda el resultado, no la entrada. Sin este guardia,
    # os.path.exists(None) revienta con TypeError y devuelve un 500.
    if not entry or not entry.get("foto_original_local") or not os.path.exists(entry["foto_original_local"]):
        flash("No encontré la foto original.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
    return send_file(entry["foto_original_local"])


@app.route("/cliente/<cliente>/swap/<swap_id>/eliminar", methods=["POST"])
def eliminar_swap(cliente, swap_id):
    swaps_mod.eliminar(cliente, swap_id)
    flash("Eliminado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


@app.route("/cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad", methods=["POST"])
def enviar_swap_a_publicidad(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    if not entry or not entry.get("resultado_url"):
        flash("Ese swap todavía no tiene un resultado listo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))

    producto = catalogo_productos.encontrar(cliente, entry.get("producto_id"))
    nombre = producto["nombre"] if producto else entry.get("producto_id", "Swap")
    ads_mod.crear(cliente, "swap", swap_id, entry["resultado_url"], entry.get("tipo", "foto"), nombre)
    flash("Enviado a Publicidad — revísalo en esa pestaña.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))


# ---------- Publicidad (Meta Ads) — publicar, actualizar resultados, pausar/activar,
# eliminar de la lista local. Nunca borra una campaña real de Meta: eso queda para
# Meta Ads Manager a propósito (ver eliminar_ad más abajo). ----------

@app.route("/cliente/<cliente>/ads/publicar", methods=["POST"])
def publicar_ad(cliente):
    """Toma un anuncio en cola (creado por otro módulo vía ads.crear) y lo
    publica de verdad en Meta: Campaign -> AdSet -> AdCreative -> Ad, todo
    PAUSED. Corre en un job de fondo porque encadena 4 llamadas HTTP."""
    ad_id = request.form.get("ad_id", "").strip()
    objetivo = request.form.get("objetivo", "").strip()
    presupuesto_diario_usd = float(request.form.get("presupuesto_diario_usd", "0") or 0)
    dias = int(request.form.get("dias", "0") or 0)
    pais = request.form.get("pais", "").strip()
    edad_min = int(request.form.get("edad_min", "18") or 18)
    edad_max = int(request.form.get("edad_max", "65") or 65)

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry:
        flash("No encontré ese anuncio en la cola.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))
    if not presupuesto_diario_usd or not dias or not pais:
        flash("Faltan presupuesto, días o país.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    ads_mod.actualizar(
        cliente, ad_id, estado="publicando", objetivo=objetivo,
        presupuesto_diario_usd=presupuesto_diario_usd, dias=dias,
        audiencia={"edad_min": edad_min, "edad_max": edad_max, "paises": [pais]},
    )
    job_id = f"{cliente}__{ad_id}__ads_publicar"

    def trabajo():
        _cargar_entorno_cliente(cliente)
        centavos = int(round(presupuesto_diario_usd * 100))
        try:
            campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo, centavos)
            campaign_id = campaign_resp["id"]

            targeting = Targeting().edad(edad_min, edad_max).paises([pais]).to_dict()
            adset_resp = meta_adset.crear_adset(
                f"{entry['nombre']} — adset", campaign_id, objetivo, targeting, centavos, dias,
            )
            adset_id = adset_resp["id"]

            ig_user_id = os.environ.get("META_IG_USER_ID")
            if entry["contenido_tipo"] == "foto":
                creative_resp = meta_creative.crear_creative_imagen(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["nombre"],
                    link="https://www.facebook.com/", instagram_user_id=ig_user_id,
                )
            else:
                creative_resp = meta_creative.crear_creative_video(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["contenido_url"],
                    entry["nombre"], instagram_user_id=ig_user_id,
                )
            creative_id = creative_resp["id"]

            ad_resp = meta_ad.crear_ad(entry["nombre"], adset_id, creative_id)

            ads_mod.actualizar(
                cliente, ad_id, estado="activo",
                meta_ids={
                    "campaign_id": campaign_id, "adset_id": adset_id,
                    "ad_id": ad_resp["id"], "creative_id": creative_id,
                },
            )
            bitacora.registrar(cliente, ad_id, "ads_publicar", "ok", campaign_id)
            return "Anuncio publicado (pausado, revísalo en Meta Ads Manager antes de activarlo)."
        except Exception as e:
            ads_mod.actualizar(cliente, ad_id, estado="error", error=str(e))
            bitacora.registrar(cliente, ad_id, "ads_publicar", "error", str(e))
            raise

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=30):
        flash("Publicando el anuncio…", "ok")
    else:
        flash("Ya se está publicando ese anuncio — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/actualizar", methods=["POST"])
def actualizar_resultados_ad(cliente, ad_id):
    _cargar_entorno_cliente(cliente)
    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry or not entry.get("meta_ids", {}).get("ad_id"):
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))
    try:
        resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"])
        resultados["actualizado_en"] = datetime.now().isoformat()
        ads_mod.actualizar(cliente, ad_id, metricas=resultados)
        flash("Resultados actualizados.", "ok")
    except Exception as e:
        flash(f"No pude traer los resultados: {e}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/estado", methods=["POST"])
def cambiar_estado_ad(cliente, ad_id):
    """Pausar/activar la campaña real en Meta — la única acción de este
    módulo que puede hacer que empiece a gastarse presupuesto de verdad."""
    _cargar_entorno_cliente(cliente)
    nuevo_estado = request.form.get("estado", "").strip()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        flash("Estado inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    campaign_id = (entry or {}).get("meta_ids", {}).get("campaign_id")
    if not campaign_id:
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    try:
        meta_campaign.actualizar_estado(campaign_id, nuevo_estado)
        ads_mod.actualizar(cliente, ad_id, estado="activo" if nuevo_estado == "ACTIVE" else "pausado")
        flash("Listo." if nuevo_estado == "ACTIVE" else "Pausado.", "ok")
    except Exception as e:
        flash(f"No pude cambiar el estado: {e}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/eliminar", methods=["POST"])
def eliminar_ad(cliente, ad_id):
    """Solo borra la fila local — NO borra la campaña en Meta si ya se
    publicó (eso se hace desde Meta Ads Manager, a propósito: esta app nunca
    borra algo que ya está corriendo en la plataforma de otro)."""
    ads_mod.eliminar(cliente, ad_id)
    flash("Eliminado de la lista.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


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


def _generar_imagen_candidata(cliente, prompt_id, item, job_id=None, on_progreso=None):
    """Genera (o regenera) la imagen candidata para un prompt vía soul/reference,
    la sube a R2 y actualiza el propio dict `item` en el sitio. Devuelve (ok, error).

    job_id/on_progreso son opcionales para que esta función siga sirviendo fuera
    de un trabajo en segundo plano. Con job_id=None, trabajos.reportar es un
    no-op silencioso, así que no hace falta condicionar cada llamada."""
    imagenes_dir = os.path.join(BASE_DIR, "salidas", cliente, "imagenes")
    os.makedirs(imagenes_dir, exist_ok=True)
    local_path = os.path.join(imagenes_dir, f"{prompt_id}.png")

    try:
        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        launch = generate_image(
            image_reference_url=item["image_url"],
            prompt=item["prompt"],
            extra_params=_extra_params_image(item, cliente),
        )
        # on_progreso hace que el poll de Higgsfield cuente su estado crudo
        # ("queued", "processing"): sin esto la barra sabía la etapa pero no si
        # el modelo ya había arrancado.
        result = poll_until_done(launch["status_url"], on_progreso=on_progreso)
        trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_IMAGEN)
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
        ok, error = _generar_imagen_candidata(
            cliente, prompt_id, item, job_id=job_id,
            on_progreso=_avisar_fase_de(job_id),
        )
        prompts_mod.guardar(cliente, data)
        if not ok:
            raise RuntimeError(error)
        return "Imagen candidata lista."

    return trabajos.iniciar(job_id, trabajo, duracion_estimada=45, etapas=ETAPAS_IMAGEN)


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

        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        launch = generate_video(
            image_url=item2["imagen_url"],
            prompt=item2["prompt"],
            model=item2.get("model", "kling-2.1-pro"),
            extra_params=_extra_params_video(item2, cliente),
        )
        # on_progreso: el poll de Higgsfield ya sabía contar su fase cruda, pero
        # ningún llamador se la pedía — la barra se quedaba sin el "en cola / el
        # modelo está trabajando" durante los ~2 minutos que dura esto.
        result = poll_until_done(launch["status_url"], on_progreso=_avisar_fase_de(job_id))
        higgsfield_url = extract_video_url(result)
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        try:
            download_result(result, out_path)
            bitacora.registrar(cliente, prompt_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, prompt_id, "generacion", "error", str(e))
            raise

        trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
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

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=130, etapas=ETAPAS_VIDEO):
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

    # El personaje NO es obligatorio: hay videos que son solo del producto (un
    # plano del calzado en una escena, sin nadie en cuadro). Lo que la plantilla
    # necesita es al menos UNA referencia protagonista para @Imagen 1, y tanto un
    # personaje como un producto sirven — generar_prompt_creative_flow() numera
    # las @Imagen sobre la lista real, así que con solo productos el primero pasa
    # a ser @Imagen 1 sin ningún hueco. Las escenas no cuentan: son ambiente, no
    # sujeto.
    if not personajes_sel and not productos_sel:
        flash("Elige al menos un personaje o un producto — la plantilla necesita @Imagen 1.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not accion_central:
        flash("Describe la acción central del video.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_nombre = {p["nombre"]: p for p in _productos_referencia(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}

    personajes = [personajes_por_nombre[n] for n in personajes_sel if n in personajes_por_nombre]
    productos = [productos_por_nombre[n] for n in productos_sel if n in productos_por_nombre]
    escenas = [escenas_por_nombre[n] for n in escenas_sel if n in escenas_por_nombre]

    # Unificación con el catálogo: FlowPlus ya no depende de subir el producto
    # aparte en productos_referencia — usa los mismos productos de FlowCatálogo,
    # con sus fotos, su tipo y su mapa corporal. Se sube la foto representativa a
    # R2 en el momento, porque Wan 3.0 necesita una URL pública y el catálogo
    # vive solo en disco hasta que algo la necesita.
    for pid in request.form.getlist("productos_catalogo"):
        prod = catalogo_productos.encontrar(cliente, pid)
        if not prod:
            continue
        try:
            url = r2_uploader.upload_image(
                prod["representativa"],
                f"clientes/{cliente}/productos/{pid}/{os.path.basename(prod['representativa'])}")
        except Exception as e:
            bitacora.registrar(cliente, pid, "creative_flow_producto", "error", str(e))
            continue
        productos.append({"nombre": prod["nombre"], "url": url})
        productos_sel.append(prod["nombre"])

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
        return item.get("url")

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
    productos_por_nombre = {p["nombre"]: p for p in _productos_referencia(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}
    personajes = [personajes_por_nombre[n] for n in entry["personajes_ids"] if n in personajes_por_nombre]
    productos = [productos_por_nombre[n] for n in entry["productos_ids"] if n in productos_por_nombre]
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

        avisar_fase = _avisar_fase_de(job_id)

        try:
            trabajos.reportar(job_id, etapa=ETAPA_MODELO)
            video_url_wan = wan3_client.generar_video(
                prompt_texto, referencias, duration=duracion, resolution="720p",
                aspect_ratio=aspect_ratio, on_progreso=avisar_fase,
            )
            costo = wan3_client.estimate_video(duration=duracion, resolution="720p")
            trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
            resp = requests.get(video_url_wan, timeout=180)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
            bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
            creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
            raise

        trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
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
    if trabajos.iniciar(job_id, trabajo, duracion_estimada=180, etapas=ETAPAS_CREATIVE_FLOW):
        flash("Generando el video con Wan 3.0…", "ok")
    else:
        # Ya había un job corriendo — no hace falta revertir el estado, ya
        # estaba en "video_generando" legítimamente.
        flash("Ya se está generando ese video — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


_MENSAJE_INTERRUMPIDO = (
    "La generación se interrumpió porque el servidor se reinició — vuelve a intentarlo."
)


def _reconciliar_huerfanos():
    """Los trabajos viven SOLO en memoria (_TRABAJOS), pero el estado 'generando'
    queda escrito en disco. Si el proceso se reinicia a mitad de una generación,
    esa entrada queda pidiendo un trabajo que ya no existe: sin barra, sin error y
    sin forma de avanzar (en CreativeFlowPlus ni siquiera se puede reintentar,
    porque cf_generar_video solo acepta 'prompt_listo'/'error').

    Al arrancar, _TRABAJOS está vacío por definición, así que todo lo que esté en
    'generando' es necesariamente un huérfano: se marca como error y cae en la
    rama que todas las plantillas ya saben mostrar.
    """
    clientes_dir = os.path.join(BASE_DIR, "clientes")
    if not os.path.isdir(clientes_dir):
        return
    for cliente in sorted(os.listdir(clientes_dir)):
        if not os.path.isdir(os.path.join(clientes_dir, cliente)):
            continue
        try:
            swaps_data = swaps_mod.cargar(cliente)
            tocado = False
            for entry in swaps_data.values():
                if entry.get("estado") == "generando":
                    entry["estado"] = "error"
                    entry["error"] = _MENSAJE_INTERRUMPIDO
                    tocado = True
            if tocado:
                swaps_mod.guardar(cliente, swaps_data)

            cf_data = creative_flow.cargar(cliente)
            tocado = False
            for entry in cf_data.values():
                if entry.get("estado") == "video_generando":
                    entry["estado"] = "error"
                    entry["error"] = _MENSAJE_INTERRUMPIDO
                    tocado = True
            if tocado:
                creative_flow.guardar(cliente, cf_data)

            conceptos_data = conceptos_imagen.cargar(cliente)
            tocado = False
            for idea in conceptos_data.values():
                for concepto in idea.get("conceptos", {}).values():
                    for proveedor in conceptos_imagen.PROVEEDORES:
                        img = concepto.get(proveedor)
                        if img and img.get("estado") == "generando":
                            img["estado"] = "error"
                            img["error"] = _MENSAJE_INTERRUMPIDO
                            tocado = True
            if tocado:
                conceptos_imagen.guardar(cliente, conceptos_data)
        except Exception as e:
            # Un cliente con el JSON corrupto no debe impedir que arranque el
            # dashboard entero.
            print(f"[aviso] No pude reconciliar los huérfanos de {cliente}: {e}")


HOST = "127.0.0.1"
PUERTO = 5050


def _tomar_puerto_o_none(host, puerto):
    """Intenta quedarse con el puerto ANTES de tocar nada en disco. Devuelve el
    socket si lo consiguió, o None si ya hay otro dashboard escuchando ahí.

    El porqué: _reconciliar_huerfanos() REESCRIBE swaps.json, creative_flow.json y
    conceptos_pendientes.json de TODOS los clientes marcando como "error" todo lo
    que esté "generando". Corriendo antes de app.run(), un segundo
    `python3 dashboard.py` lanzado sin matar el primero (algo que el flujo de este
    repo invita a hacer, porque hay que reiniciar tras cada cambio .py) le
    destruía al proceso VIVO el estado de generaciones de 380s que estaban
    perfectamente en curso... y recién después moría con "Address already in use".

    SO_REUSEADDR va ENCENDIDO, al revés de lo que parece intuitivo. En macOS/BSD
    esa opción NO permite bindear sobre un socket que está escuchando (eso sería
    SO_REUSEPORT): lo único que habilita es reusar un puerto que quedó en
    TIME_WAIT. Sin ella, matar el dashboard con Ctrl+C y reiniciarlo dentro de
    los ~30s siguientes fallaba el bind por las conexiones keep-alive del
    navegador, y entonces NO se reconciliaba nada mientras se imprimía un aviso
    falso ("ya hay otro dashboard corriendo") — dejando swaps en "generando"
    para siempre, que es exactamente el caso que esto vino a arreglar.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, puerto))
    except OSError as e:
        s.close()
        print(f"[aviso] {host}:{puerto} ya está ocupado ({e}). No reconcilio huérfanos "
              f"para no pisarle el estado al dashboard que ya está corriendo.")
        return None
    return s


if __name__ == "__main__":
    _candado = _tomar_puerto_o_none(HOST, PUERTO)
    if _candado is not None:
        try:
            _reconciliar_huerfanos()
        finally:
            # Se libera antes de app.run() para que Flask pueda bindear él mismo.
            # Queda una ventana de milisegundos en la que otro proceso podría
            # colarse; es aceptable, porque lo que se está evitando es el caso
            # real (dos arranques manuales con minutos de diferencia), no una
            # carrera entre dos procesos que arrancan en el mismo instante.
            _candado.close()
    # Si no se consiguió el puerto se sigue igual hasta app.run(), que va a
    # fallar solo con su mensaje de siempre — pero sin haber tocado el disco.
    # use_reloader=False a propósito: ahora hay generaciones corriendo en hilos
    # de fondo, y el auto-reload de Flask mata el proceso completo (y con él,
    # cualquier generación en curso) apenas detecta un cambio de archivo.
    app.run(host=HOST, port=PUERTO, debug=True, use_reloader=False)
