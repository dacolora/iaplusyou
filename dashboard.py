"""
Dashboard web local: clientes, personajes, briefs/prompts, videos, aprobación y
estado de publicación por plataforma — todo en una página.

Uso:
    python dashboard.py
    (abre http://127.0.0.1:5050 en tu navegador)

Solo corre en tu máquina (127.0.0.1), no queda expuesto a internet.
"""
import json
import logging
import math
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from functools import wraps
from urllib.parse import urlsplit

import requests
import sqlalchemy as sa

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file, abort, session, Response
from werkzeug.middleware.proxy_fix import ProxyFix
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
import usuarios
import cuentas
import meta_conexion
import meta_agencia
import flowplus_prompt
import referencias_flowplus
import referencias_link
import generador_prompts
from providers import image_provider
from providers import video_provider, wan3_client, flowplus_modelos
from providers import aspect_ratio as aspect_ratio_mod
import ads as ads_mod
from meta_ads import auth as meta_auth
from meta_ads import campaign as meta_campaign
import creative_flow
import flowplus_lanzar
import cola
import db
import experimentos
import lanzador
import acciones
import decisor
import modos
import organico
import propuestas
import cifrado
import conectores
import tiendas
import tablero
import admin
import gastos
from conectores import ErrorConector
from conectores import csv_excel as conector_csv
from conectores import meli as conector_meli
from tareas.flowplus import ETAPAS_CREATIVE_FLOW
from tareas import final_edition as tareas_fe
from tareas import director as tareas_director
from tareas import experimentos as tareas_exp
from tareas import organico as tareas_org
from tareas import tiendas as tareas_tiendas
from final_edition import ETAPAS_FINAL, mezcla as fe_mezcla, tipos as fe_tipos
from providers import fal_audio
from tareas.swap import ETAPAS_SWAP_VIDEO, ETAPAS_SWAP_FOTO, ETAPAS_SWAP_FOTO_MEJORADA
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
# Real y aleatoria: con login de por medio, un secret_key adivinable permite
# falsificar la cookie de sesión y hacerse pasar por cualquier usuario — el
# literal fijo de antes ("solo-local-no-hace-falta-secreto-real") deja de ser
# aceptable en el momento en que existe una sesión que proteger. FLASK_SECRET_KEY
# fija la clave entre reinicios (necesario en el VPS); sin ella, cada arranque
# genera una nueva y todas las sesiones activas se invalidan — aceptable en
# desarrollo local, no en producción.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

log = logging.getLogger(__name__)


def _plataforma_url():
    """PLATAFORMA_URL del .env (sin barra final) o "". Es la URL pública fija
    del sitio: base de los enlaces que van por correo y host que se acepta."""
    return (os.environ.get("PLATAFORMA_URL") or "").strip().rstrip("/")


def _config_sesion(plataforma_url):
    """Flags de la cookie de sesión: HttpOnly siempre, SameSite=Lax (los POST
    desde otro sitio no la llevan → primera barrera contra CSRF) y Secure
    cuando el sitio público es https (en local http seguiría funcionando)."""
    return {
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": plataforma_url.lower().startswith("https://"),
    }


app.config.update(_config_sesion(_plataforma_url()))


def _detras_de_proxy():
    """DETRAS_DE_PROXY=1: nginx está delante y es el único que llega a
    gunicorn, así que X-Forwarded-For/-Proto son de fiar (el último valor,
    el que nginx añade). Sin la variable, esas cabeceras se ignoran: cualquier
    cliente podría inventarlas y saltarse el límite por IP."""
    return (os.environ.get("DETRAS_DE_PROXY") or "").strip() == "1"


if _detras_de_proxy():
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)

from sprints import rutas as sprints_rutas  # noqa: E402  (Blueprint de la pestaña Sprints)
app.register_blueprint(sprints_rutas.bp)

from nicho import rutas as nicho_rutas  # noqa: E402  (Blueprint de la pestaña Nicho)
app.register_blueprint(nicho_rutas.bp)

# Cargar el .env de un cliente muta os.environ (variables globales del proceso).
# Como publicar ahora corre en un hilo de fondo, dos publicaciones de clientes
# distintos podrían solaparse y pisarse las credenciales una a la otra — este
# lock serializa esa sección crítica (cargar credenciales + usarlas) para que
# eso no pase.
_ENV_LOCK = threading.Lock()


def _sesion():
    """dict de la sesión actual (usuario/rol/cliente) o None si no hay login."""
    if "usuario" not in session:
        return None
    return {"usuario": session["usuario"], "rol": session["rol"], "cliente": session.get("cliente")}


def requiere_admin(fn):
    @wraps(fn)
    def envuelta(*args, **kwargs):
        sesion = _sesion()
        if not sesion or sesion["rol"] != "admin":
            flash("Esa página es solo para el administrador.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return envuelta


HOSTS_LOCALES = frozenset(("localhost", "127.0.0.1", "::1"))


def _host_plataforma():
    """Host (sin puerto) de PLATAFORMA_URL, o None si no está definida."""
    fijo = _plataforma_url()
    if not fijo:
        return None
    return (urlsplit(fijo).hostname or "").lower() or None


@app.before_request
def _verificar_host():
    """Con PLATAFORMA_URL definida, solo se atiende ese host (y localhost para
    probar en la propia máquina): una petición con otra cabecera Host —la que
    un atacante usaría para que un enlace por correo apunte a su dominio— es
    un 404. Va primero que los demás guards. Se salta con app.testing."""
    esperado = _host_plataforma()
    if esperado is None or app.testing:
        return None
    host = (urlsplit(f"//{request.host}").hostname or "").lower()
    if host == esperado or host in HOSTS_LOCALES:
        return None
    abort(404)


# Rutas de cuentas que deben funcionar aunque la sesión esté vencida o el
# usuario ya no exista (verificar el correo o restablecer la contraseña se
# abren desde un enlace, muchas veces sin sesión): el guard de sesión no las
# cierra.
ENDPOINTS_SIN_GUARD_SESION = frozenset((
    "static", "login", "logout", "index", "crear_proyecto", "verificar_correo",
    "recuperar", "restablecer", "privacidad", "terminos", "eliminar_datos",
))


def _abrir_sesion(usuario, entry):
    """Escribe la sesión de Flask tras un login o un alta. `sv` es la
    session_version del usuario: cambiar la contraseña la sube y el guard
    (_verificar_sesion) cierra cualquier sesión que traiga otra."""
    session["usuario"] = usuario
    session["rol"] = entry["rol"]
    session["cliente"] = entry.get("cliente")
    session["sv"] = int(entry.get("session_version") or 1)


@app.before_request
def _verificar_sesion():
    """Toda sesión tiene que corresponder a un usuario que siga en
    usuarios.json: si ya no existe (borrado) o su session_version cambió
    (restableció la contraseña), la sesión se cierra y se pide entrar de
    nuevo. Una sesión sin `sv` (cookie anterior a esta versión) se sella con
    la versión actual del usuario la primera vez que se ve, para que desde
    ahí también cuente. Va registrado antes que _guard_por_cliente para que
    una sesión muerta se cierre aunque pida un proyecto ajeno."""
    if request.endpoint in ENDPOINTS_SIN_GUARD_SESION or "usuario" not in session:
        return None
    entry = usuarios.obtener(session["usuario"])
    vigente = entry is not None and (
        "sv" not in session or int(entry.get("session_version") or 1) == int(session.get("sv") or 0))
    if not vigente:
        session.clear()
        flash("Tu sesión se cerró; entra de nuevo.", "error")
        return redirect(url_for("login"))
    if "sv" not in session:
        session["sv"] = int(entry.get("session_version") or 1)
    return None


@app.before_request
def _guard_por_cliente():
    """Cualquier ruta cuya URL incluya <cliente> exige sesión con permiso
    real sobre ESE cliente — nunca solo ocultar un botón en la plantilla.
    rol 'admin' pasa siempre; rol 'cliente' solo si coincide con el suyo.
    Rutas sin <cliente> en la URL (login, /, /proyectos/nuevo, estáticos)
    no pasan por acá."""
    cliente = request.view_args.get("cliente") if request.view_args else None
    if cliente is None or request.endpoint in ("landing_cliente", "meli_callback"):
        # la landing pública de un proyecto es, justamente, pública; el
        # callback de MercadoLibre no lleva <cliente> en la URL (una sola
        # dirección registrada) y resuelve el proyecto desde la sesión, con
        # su propio chequeo de acceso (ver meli_callback).
        return None
    sesion = _sesion()
    if not usuarios.puede_acceder(sesion, cliente):
        if not sesion:
            flash("Inicia sesión para entrar a este proyecto.", "error")
            return redirect(url_for("login"))
        flash("No tienes acceso a ese proyecto.", "error")
        return redirect(url_for("ver_cliente", cliente=sesion["cliente"])) if sesion["rol"] == "cliente" else redirect(url_for("index"))
    return None


@app.context_processor
def _cuenta_en_plantillas():
    """`cuenta_actual` (registro del usuario de la sesión, sin contraseña) y
    `smtp_ok` para el banner de base.html y Configuración › Cuenta. Lectura
    de un JSON pequeño; los parciales por fetch no lo necesitan."""
    if "usuario" not in session or _quiere_json():
        return {}
    return {"cuenta_actual": usuarios.obtener(session["usuario"]), "smtp_ok": cuentas.smtp_configurado()}


URL_BASE_LOCAL = "http://127.0.0.1:5050"
_aviso_url_base_dado = False


def _url_base():
    """Base pública de los enlaces que van por correo. NUNCA sale de la
    petición (la cabecera Host la manda el cliente: con ella un atacante haría
    que el enlace de restablecer de la víctima apuntara a su dominio y se
    quedara con el token). PLATAFORMA_URL manda; sin ella, el esquema+host de
    META_REDIRECT_URI (la otra URL pública que ya tiene el .env) y, si tampoco,
    la de desarrollo local. Los dos últimos avisan una vez en el log."""
    global _aviso_url_base_dado
    fijo = _plataforma_url()
    if fijo:
        return fijo
    partes = urlsplit((os.environ.get("META_REDIRECT_URI") or "").strip())
    if partes.scheme in ("http", "https") and partes.netloc:
        base = f"{partes.scheme}://{partes.netloc}"
    else:
        base = URL_BASE_LOCAL
    if not _aviso_url_base_dado:
        _aviso_url_base_dado = True
        log.warning("PLATAFORMA_URL no está en el .env: los enlaces por correo usan %s", base)
    return base


def _ip_cliente():
    """IP de quien pide: request.remote_addr. Detrás de nginx solo es la real
    con DETRAS_DE_PROXY=1 (ProxyFix, ver arriba); las cabeceras X-Forwarded-*
    nunca se leen a mano porque el primer valor lo pone el cliente."""
    return request.remote_addr or None


def _mismo_origen():
    """False solo cuando el navegador declara (Sec-Fetch-Site) que el POST
    viene de otro sitio: los formularios propios mandan same-origin (o none al
    escribir la URL). Es la barrera CSRF de los POST que no piden contraseña ni
    token; los navegadores sin esa cabecera ya no llevan la cookie (SameSite)."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


def _limite_correo(prefijo, correo):
    """True si todavía cabe otro correo de ese tipo para ese correo Y desde
    esta IP (5 por hora cada uno, cuentas.limite_ok)."""
    ip = _ip_cliente() or "desconocida"
    return cuentas.limite_ok(f"{prefijo}:{correo}") and cuentas.limite_ok(f"{prefijo}:ip:{ip}")


def _requiere_correo_verificado():
    """None si la sesión puede seguir (admin, o cliente con correo
    verificado); si no, un redirect a Configuración › Cuenta con el aviso.
    Se aplica en lo que conecta cuentas de terceros (Meta, tiendas)."""
    sesion = _sesion()
    if not sesion or sesion["rol"] == "admin":
        return None
    entry = usuarios.obtener(sesion["usuario"])
    if entry and entry.get("correo_verificado"):
        return None
    flash("Confirma tu correo primero (Configuración › Cuenta).", "error")
    if sesion.get("cliente"):
        return redirect(url_for("ver_cliente", cliente=sesion["cliente"], _anchor="settings"))
    return redirect(url_for("index"))


def _volver_cuenta():
    """Adónde vuelve un formulario de cuenta: la Configuración del proyecto
    (rol cliente) o el panel (admin)."""
    sesion = _sesion()
    if sesion and sesion["rol"] == "cliente" and sesion.get("cliente"):
        return redirect(url_for("ver_cliente", cliente=sesion["cliente"], _anchor="settings"))
    if sesion and sesion["rol"] == "admin":
        return redirect(url_for("panel"))
    return redirect(url_for("login"))


@app.after_request
def _sin_cache(resp):
    """Ni el HTML ni el JSON de estado deben cachearse: son estado vivo que cambia
    solo (una generación que termina, una barra de progreso). Flask no mandaba
    ningún header de caché, y ya hubo un caso de navegador sirviendo HTML viejo
    que obligó a un recarga dura."""
    if resp.mimetype in ("text/html", "application/json"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        # El token de restablecer/verificar va en la URL: que no viaje en el
        # Referer a las fuentes externas (Google Fonts) ni a ningún enlace.
        resp.headers["Referrer-Policy"] = (
            "no-referrer" if request.endpoint in ("restablecer", "verificar_correo") else "strict-origin-when-cross-origin")
    # Los recursos de marca (ícono de la app, logo) son públicos: otros sitios
    # (p. ej. el panel de Meta) pueden cargarlos por fetch.
    if request.path.startswith("/static/img/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
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


def _logos(cliente):
    """Logos oficiales del proyecto (FlowSettings): van como referencia extra en
    cada generación de FlowPlus para que el modelo no invente la marca."""
    return [l for l in _listar_assets(cliente, "logos") if l.get("url")]


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


@app.route("/cliente/<cliente>/logos/subir", methods=["POST"])
def subir_logo(cliente):
    archivos = [a for a in request.files.getlist("imagen") if a and a.filename]
    ok_n = 0
    for a in archivos:
        ok, mensaje = _subir_asset(cliente, "logos", a)
        if ok:
            ok_n += 1
        else:
            flash(mensaje, "error")
    if ok_n:
        flash(f"{ok_n} logo(s) guardado(s). Se usan como referencia en cada generación de FlowPlus.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/logos/<nombre>/eliminar", methods=["POST"])
def eliminar_logo(cliente, nombre):
    ok, mensaje = _eliminar_asset(cliente, "logos", nombre)
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


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
    # Con sesión abierta, la portada no tiene sentido: se va derecho al
    # proyecto (o al panel si es admin). Solo se vuelve a ver al cerrar sesión.
    sesion = _sesion()
    if sesion:
        if sesion["rol"] == "admin":
            return redirect(url_for("panel"))
        if sesion.get("cliente"):
            return redirect(url_for("ver_cliente", cliente=sesion["cliente"]))
    # Pública, sin login: explica qué hace la plataforma y ofrece crear un
    # proyecto nuevo o entrar a uno que ya existe. Nunca lista los proyectos
    # existentes acá — eso filtraría qué clientes hay a cualquiera que abra
    # el link. El listado completo vive en /panel, solo para el admin.
    return render_template("index.html")


_PRIVACIDAD_HTML = """
<p>Creatv Machine (creatvmachine.com) es una plataforma para que empresas creen contenido con inteligencia
artificial y lo publiquen o anuncien en sus propias redes sociales. Esta política explica qué datos tratamos
cuando conectas tu cuenta de Meta (Facebook e Instagram) y cómo los protegemos.</p>
<h3>Responsable</h3>
<p>Daniel Alejandro Colorado Gaviria — Creatv Machine, Envigado, Colombia. Contacto: dacoloradog@gmail.com.</p>
<h3>Qué datos recibimos de Meta</h3>
<ul>
<li>Tu nombre y el identificador de tu usuario de Facebook (para saber quién autorizó la conexión).</li>
<li>La lista de cuentas publicitarias, Páginas de Facebook y cuentas de Instagram que administras, para que
elijas cuál conectar al proyecto.</li>
<li>Un token de acceso de sistema para la cuenta publicitaria y la Página elegidas.</li>
<li>Datos de tus anuncios y sus resultados (impresiones, alcance, clics, gasto, conversiones) y, cuando
publiques contenido orgánico, la confirmación de la publicación.</li>
</ul>
<h3>Para qué los usamos</h3>
<ul>
<li>Crear y administrar campañas, conjuntos de anuncios y anuncios en <strong>tu</strong> cuenta publicitaria,
siempre a petición tuya desde la plataforma: ningún anuncio se crea ni se activa sin que lo pidas.</li>
<li>Mostrarte los resultados de tus anuncios dentro de la plataforma.</li>
<li>Publicar en tu Página de Facebook y tu Instagram el contenido que apruebes.</li>
</ul>
<p>No usamos tus datos para publicidad propia, no los vendemos ni los compartimos con terceros, y no los
usamos para entrenar modelos de inteligencia artificial.</p>
<h3>Dónde y cómo se guardan</h3>
<p>Los tokens y los identificadores de tus activos se guardan cifrados en tránsito (HTTPS) y con permisos
restringidos en nuestro servidor en la Unión Europea (Hetzner, Núremberg). Solo el proceso de la plataforma
puede leerlos; nunca se muestran en pantalla ni se registran en logs.</p>
<h3>Cuánto tiempo</h3>
<p>Mientras el proyecto tenga Meta conectado. Al pulsar «Desconectar» en la plataforma se borran de inmediato
el token y los identificadores. También puedes revocar el acceso desde Facebook: Configuración › Integraciones
de negocio, o Configuración › Apps y sitios web.</p>
<h3>Eliminación de datos</h3>
<p>Para que eliminemos todos los datos asociados a tu cuenta de Meta escríbenos a dacoloradog@gmail.com
indicando el nombre del proyecto; lo hacemos en un plazo máximo de 7 días y te confirmamos por correo.</p>
<h3>Tus derechos</h3>
<p>Puedes pedir acceso, corrección o eliminación de tus datos en cualquier momento al mismo correo.
Cumplimos la Ley 1581 de 2012 de protección de datos personales de Colombia y las políticas de la plataforma
de Meta.</p>
"""

_TERMINOS_HTML = """
<p>Al usar Creatv Machine aceptas estas condiciones.</p>
<h3>El servicio</h3>
<p>Creatv Machine genera imágenes y videos con inteligencia artificial a partir de las referencias que subes,
y te permite publicarlos o anunciarlos en tus propias cuentas de redes sociales. Tú decides qué se genera,
qué se publica y qué se anuncia: cada acción con costo o efecto público requiere tu confirmación.</p>
<h3>Tu contenido</h3>
<p>Las referencias que subes y el contenido generado son tuyos. Declaras que tienes derecho a usar las
imágenes, videos, marcas y productos que subes. No subas contenido de terceros sin autorización.</p>
<h3>Cuentas de Meta y otras plataformas</h3>
<p>Al conectar una cuenta de Meta actúas en nombre de esa cuenta y eres responsable de los anuncios y
publicaciones que ordenes desde la plataforma, incluido su presupuesto. Cumple las políticas de publicidad
de Meta.</p>
<h3>Costos</h3>
<p>Las generaciones con IA tienen un costo que se muestra antes de generar. Los anuncios se pagan
directamente a Meta desde tu cuenta publicitaria.</p>
<h3>Responsabilidad</h3>
<p>El servicio se presta «tal cual». No garantizamos resultados publicitarios ni que un modelo de IA produzca
siempre el resultado esperado. No respondemos por rechazos de anuncios por parte de Meta ni por cambios en
las plataformas de terceros.</p>
<h3>Contacto</h3>
<p>Daniel Alejandro Colorado Gaviria — Creatv Machine, Envigado, Colombia. dacoloradog@gmail.com.</p>
"""


@app.route("/privacidad")
def privacidad():
    """Pública. Es la URL que exige Meta (App Review) y que cualquiera puede leer."""
    return render_template("legal.html", titulo="Política de privacidad", actualizado="12 de septiembre de 2026", cuerpo=_PRIVACIDAD_HTML)


@app.route("/terminos")
def terminos():
    return render_template("legal.html", titulo="Términos del servicio", actualizado="12 de septiembre de 2026", cuerpo=_TERMINOS_HTML)


@app.route("/eliminar-datos")
def eliminar_datos():
    """URL de instrucciones de eliminación de datos que pide Meta."""
    cuerpo = """<p>Para eliminar los datos que Creatv Machine guarda de tu cuenta de Meta:</p>
<ol><li>Entra a tu proyecto en app.creatvmachine.com › FlowMarketing › <strong>Desconectar</strong>: se borran el token
y los identificadores de tu cuenta publicitaria, Página e Instagram al instante.</li>
<li>Si prefieres, escribe a dacoloradog@gmail.com con el nombre de tu proyecto y lo eliminamos en máximo 7 días,
con confirmación por correo.</li></ol>
<p>También puedes revocar el acceso desde Facebook: Configuración › Apps y sitios web › Creatv Machine › Eliminar.</p>"""
    return render_template("legal.html", titulo="Eliminación de datos", actualizado="12 de septiembre de 2026", cuerpo=cuerpo)


@app.route("/l/<cliente>")
def landing_cliente(cliente):
    """Página pública de destino de un proyecto (clientes/<c>/landing.json).
    Sirve de landing para anuncios cuando el cliente no tiene web propia —
    p. ej. una app, porque Meta no acepta el link a la tienda con Tráfico."""
    ruta = os.path.join(BASE_DIR, "clientes", secure_filename(cliente), "landing.json")
    if not os.path.isfile(ruta):
        abort(404)
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    return render_template("landing_cliente.html", l=datos)


@app.route("/panel")
@requiere_admin
def panel():
    """Tablero de operación del admin: todos los proyectos con su gasto del
    mes (generación y pauta), piezas, aprobaciones, experimentos y
    conexiones; salud del worker; historial y CSV. Cálculos en admin.py."""
    ids = estado_mod.listar_clientes()
    nombres = {cid: proyectos.nombre_visible(cid) for cid in ids}
    try:
        datos = admin.resumen(ids, nombres)
    except Exception as e:  # noqa: BLE001 — el panel se pinta igual, sin números, y avisa
        print(f"[aviso] Panel: no pude calcular el resumen: {type(e).__name__}: {e}")
        datos = None
    return render_template("panel.html", datos=datos, nombres=nombres, nombres_tipo=NOMBRES_TIPO_GASTO,
                           usuarios_lista=_usuarios_panel(), smtp_ok=cuentas.smtp_configurado())


@app.route("/panel/gasto.csv")
@requiere_admin
def panel_gasto_csv():
    """CSV del mes con los cobros de generación de TODOS los proyectos (admin.csv_mes)."""
    ids = estado_mod.listar_clientes()
    resp = app.response_class(admin.csv_mes(ids), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="gasto-{db.ahora()[:7]}.csv"'
    return resp


def _usuarios_panel():
    """Usuarios para la tabla del panel: nombre, rol, proyecto, correo y si
    está verificado. Sin contraseña (usuarios.obtener la quita)."""
    lista = []
    for nombre in sorted(usuarios.cargar(), key=str.lower):
        entry = usuarios.obtener(nombre) or {}
        lista.append({
            "usuario": nombre,
            "rol": entry.get("rol"),
            "cliente": entry.get("cliente"),
            "correo": entry.get("correo"),
            "correo_verificado": bool(entry.get("correo_verificado")),
            "creado_en": entry.get("creado_en"),
        })
    return lista


@app.route("/mapa")
@requiere_admin
def mapa_codigo():
    """Mapa conceptual del código: la versión interactiva de ESTRUCTURA.md
    (diagrama web/worker, recorrido de un clic, inventario con buscador,
    llaves por nombre, riesgos del repo). Solo admin: es documentación
    interna de la plataforma, no algo que un proyecto deba ver."""
    return render_template("mapa_codigo.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if _sesion():
            return redirect(url_for("index"))
        return render_template("login.html")

    usuario = (request.form.get("usuario") or "").strip()
    password = request.form.get("password") or ""
    entry = usuarios.verificar(usuario, password)
    if not entry:
        flash("Usuario o contraseña incorrectos.", "error")
        return render_template("login.html"), 401

    _abrir_sesion(usuario, entry)
    if entry["rol"] == "admin":
        return redirect(url_for("panel"))
    return redirect(url_for("ver_cliente", cliente=entry["cliente"]))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("index"))


@app.route("/proyectos/nuevo", methods=["POST"])
def crear_proyecto():
    nombre = (request.form.get("nombre") or "").strip()
    usuario = (request.form.get("usuario") or "").strip()
    correo_crudo = (request.form.get("correo") or "").strip()
    password = request.form.get("password") or ""
    form = {"nombre": nombre, "usuario": usuario, "correo": correo_crudo}

    def _error(mensaje):
        # Se vuelve a pintar la portada con lo escrito (menos la contraseña)
        # para que no haya que llenar todo otra vez.
        flash(mensaje, "error")
        return render_template("index.html", form=form), 400

    if not nombre:
        return _error("Ponle un nombre a la empresa.")
    if not usuario or not password:
        return _error("Elige un usuario y una contraseña para entrar a tu proyecto.")
    error_usuario = usuarios.validar_usuario(usuario)
    if error_usuario:
        return _error(error_usuario)
    correo = usuarios.validar_correo(correo_crudo)
    if not correo:
        return _error("Escribe un correo válido: ahí te llega el enlace para confirmar la cuenta y recuperar la contraseña.")
    error_password = usuarios.validar_password(password)
    if error_password:
        return _error(error_password)
    if usuarios.existe(usuario):
        return _error(f"Ya existe un usuario '{usuario}' — elige otro.")
    if usuarios.por_correo(correo):
        return _error("Ese correo ya tiene una cuenta. Entra con ella o recupera la contraseña.")

    cid = secure_filename(nombre.lower().replace(" ", "_"))
    if not cid:
        return _error("Ese nombre no genera un identificador de proyecto válido.")
    if cid in estado_mod.listar_clientes():
        return _error(f"Ya existe un proyecto con el identificador '{cid}' — elige otro nombre.")

    # Tope por IP al alta en sí (5 por hora): sin él, un script crea cuentas y
    # carpetas sin fin y manda un correo de verificación por cada una.
    if not cuentas.limite_ok(f"alta:ip:{_ip_cliente() or 'desconocida'}"):
        flash("Demasiados registros seguidos desde esta conexión. Espera un rato e inténtalo de nuevo.", "error")
        return render_template("index.html", form=form), 429

    try:
        usuarios.crear(usuario, password, "cliente", cliente=cid, correo=correo)
    except ValueError as e:
        return _error(str(e))
    os.makedirs(os.path.join(BASE_DIR, "clientes", cid), exist_ok=True)
    proyectos.guardar_nombre(cid, nombre)

    # Alta con sesión inmediata: quien crea el proyecto queda logueado en su
    # propio proyecto de una vez, sin tener que ir a /login aparte.
    _abrir_sesion(usuario, usuarios.obtener(usuario) or {"rol": "cliente", "cliente": cid})

    if not cuentas.smtp_configurado():
        flash(f"Proyecto '{nombre}' creado. El servidor no tiene correo configurado, así que no pudimos "
              "enviarte el enlace de confirmación: avisa al administrador.", "warn")
    elif not _limite_correo("verif", correo):
        flash(f"Proyecto '{nombre}' creado. Espera un momento y pide el correo de confirmación desde "
              "el aviso de arriba.", "warn")
    elif cuentas.enviar_verificacion(usuario, correo, _url_base(), ip=_ip_cliente()):
        flash(f"Proyecto '{nombre}' creado. Te mandamos un correo a {correo} para confirmar tu cuenta.", "ok")
    else:
        flash(f"Proyecto '{nombre}' creado, pero no pudimos enviar el correo de confirmación. "
              "Reenvíalo desde el aviso de arriba en un momento.", "warn")
    return redirect(url_for("ver_cliente", cliente=cid))


# --- Cuentas: verificar correo, recuperar y restablecer contraseña, cuenta ---
# Plan: docs/superpowers/plans/2026-09-19-cuentas-correo-verificado.md. Los
# tokens y los correos viven en cuentas.py; acá solo las rutas. Ninguna de
# estas respuestas dice si un correo o usuario existe.

@app.route("/verificar/<token>")
def verificar_correo(token):
    """Enlace del correo de verificación. Funciona con o sin sesión: consume
    el token (un solo uso) y marca el correo como verificado; si el token
    trae un correo distinto al actual (cambio de correo), lo actualiza."""
    resultado = cuentas.consumir("verificacion", token)
    sesion = _sesion()
    if resultado is None:
        flash("Ese enlace de verificación no sirve: ya se usó o venció. Pide uno nuevo desde tu cuenta.", "error")
        return _volver_cuenta() if sesion else redirect(url_for("login"))
    usuario = resultado["usuario"]
    try:
        usuarios.actualizar(usuario, correo=resultado["correo"], correo_verificado=True)
    except ValueError as e:
        flash(f"No pude confirmar el correo: {e}", "error")
        return _volver_cuenta() if sesion else redirect(url_for("login"))
    flash("Correo confirmado. ¡Gracias!", "ok")
    # Con sesión abierta (la suya o la de otro usuario en este navegador) se
    # vuelve a su cuenta; sin sesión, al login.
    return _volver_cuenta() if sesion else redirect(url_for("login"))


@app.route("/reenviar-verificacion", methods=["POST"])
def reenviar_verificacion():
    if not _mismo_origen():
        abort(403)
    sesion = _sesion()
    if not sesion:
        flash("Inicia sesión para reenviar la verificación.", "error")
        return redirect(url_for("login"))
    entry = usuarios.obtener(sesion["usuario"])
    if not entry or not entry.get("correo"):
        flash("Primero escribe tu correo en Configuración › Cuenta.", "error")
        return _volver_cuenta()
    if entry.get("correo_verificado"):
        flash("Tu correo ya está confirmado.", "ok")
        return _volver_cuenta()
    if not cuentas.smtp_configurado():
        flash("El servidor no tiene correo configurado; avisa al administrador para que confirme tu cuenta.", "warn")
        return _volver_cuenta()
    if not _limite_correo("verif", entry["correo"]):
        flash("Espera un momento antes de pedir otro correo de verificación.", "warn")
        return _volver_cuenta()
    cuentas.enviar_verificacion(sesion["usuario"], entry["correo"], _url_base(), ip=_ip_cliente())
    flash(f"Si {entry['correo']} es correcto, te llega el enlace en unos minutos (revisa también el spam).", "ok")
    return _volver_cuenta()


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """Pide el correo y, si corresponde a un usuario, manda el enlace de
    restablecimiento. La respuesta es la misma exista o no el correo."""
    if request.method == "GET":
        return render_template("recuperar.html")
    correo = usuarios.validar_correo(request.form.get("correo") or "")
    encontrado = usuarios.por_correo(correo) if correo else None
    if encontrado and cuentas.smtp_configurado() and _limite_correo("reset", correo):
        usuario, _entry = encontrado
        cuentas.enviar_restablecer(usuario, correo, _url_base(), ip=_ip_cliente())
    flash("Si ese correo está registrado, te llegará un enlace para restablecer la contraseña "
          "(vence en 1 hora; revisa también el spam).", "ok")
    return redirect(url_for("login"))


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    """GET: valida el token sin gastarlo y muestra el formulario (o «enlace
    vencido»). POST: valida la contraseña nueva, consume el token, la cambia
    (sube session_version → se cierran las demás sesiones) y manda al login."""
    if request.method == "GET":
        if cuentas.validar("restablecer", token) is None:
            return render_template("restablecer.html", vencido=True), 400
        return render_template("restablecer.html", vencido=False, token=token)
    nueva = request.form.get("password") or ""
    confirmacion = request.form.get("confirmacion") or ""
    error = usuarios.validar_password(nueva)
    if not error and nueva != confirmacion:
        error = "Las dos contraseñas no coinciden."
    if error:
        if cuentas.validar("restablecer", token) is None:
            return render_template("restablecer.html", vencido=True), 400
        flash(error, "error")
        return render_template("restablecer.html", vencido=False, token=token), 400
    resultado = cuentas.consumir("restablecer", token)
    if resultado is None:
        return render_template("restablecer.html", vencido=True), 400
    usuario = resultado["usuario"]
    try:
        usuarios.cambiar_password(usuario, nueva)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("login"))
    # Abrir el enlace que llegó a ese correo demuestra que es suyo: si sigue
    # siendo el correo de la cuenta, queda confirmado de paso.
    entry = usuarios.obtener(usuario) or {}
    if entry.get("correo") == resultado["correo"] and not entry.get("correo_verificado"):
        usuarios.actualizar(usuario, correo_verificado=True)
    session.clear()
    flash("Contraseña cambiada. Entra con la nueva.", "ok")
    return redirect(url_for("login"))


@app.route("/cuenta/correo", methods=["POST"])
def cuenta_correo():
    """Pone o cambia el correo de la cuenta (pide la contraseña actual). El
    correo nuevo queda sin verificar hasta abrir el enlace."""
    sesion = _sesion()
    if not sesion:
        flash("Inicia sesión para cambiar tu correo.", "error")
        return redirect(url_for("login"))
    usuario = sesion["usuario"]
    if not usuarios.verificar(usuario, request.form.get("password") or ""):
        flash("La contraseña actual no es correcta.", "error")
        return _volver_cuenta()
    correo = usuarios.validar_correo(request.form.get("correo") or "")
    if not correo:
        flash("Escribe un correo válido.", "error")
        return _volver_cuenta()
    actual = usuarios.obtener(usuario) or {}
    if actual.get("correo") == correo and actual.get("correo_verificado"):
        flash("Ese ya es tu correo y está confirmado.", "ok")
        return _volver_cuenta()
    try:
        usuarios.actualizar(usuario, correo=correo, correo_verificado=False)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_cuenta()
    # El enlace del correo anterior no puede seguir sirviendo: al abrirlo
    # devolvería la cuenta al correo viejo (y verificado) aunque no se llegue
    # a emitir uno nuevo (sin SMTP o con el límite alcanzado).
    cuentas.invalidar("verificacion", usuario)
    if not cuentas.smtp_configurado():
        flash(f"Correo guardado: {correo}. El servidor no tiene correo configurado, así que no pudimos "
              "enviarte el enlace de confirmación: avisa al administrador.", "warn")
    elif not _limite_correo("verif", correo):
        flash(f"Correo guardado: {correo}. Espera un momento antes de pedir el enlace de confirmación.", "warn")
    else:
        cuentas.enviar_verificacion(usuario, correo, _url_base(), ip=_ip_cliente())
        flash(f"Correo guardado. Si {correo} es correcto, te llega el enlace de confirmación en unos minutos.", "ok")
    return _volver_cuenta()


@app.route("/cuenta/password", methods=["POST"])
def cuenta_password():
    """Cambia la contraseña con la actual + nueva + confirmación. Sube
    session_version (las demás sesiones se cierran) y refresca la de este
    navegador para que siga abierta."""
    sesion = _sesion()
    if not sesion:
        flash("Inicia sesión para cambiar tu contraseña.", "error")
        return redirect(url_for("login"))
    usuario = sesion["usuario"]
    if not usuarios.verificar(usuario, request.form.get("password_actual") or ""):
        flash("La contraseña actual no es correcta.", "error")
        return _volver_cuenta()
    nueva = request.form.get("password") or ""
    error = usuarios.validar_password(nueva)
    if not error and nueva != (request.form.get("confirmacion") or ""):
        error = "Las dos contraseñas no coinciden."
    if error:
        flash(error, "error")
        return _volver_cuenta()
    try:
        session["sv"] = usuarios.cambiar_password(usuario, nueva)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_cuenta()
    flash("Contraseña cambiada. Las demás sesiones abiertas con la anterior se cerraron.", "ok")
    return _volver_cuenta()


@app.route("/admin/usuarios/<usuario>/verificar", methods=["POST"])
@requiere_admin
def admin_usuario_verificar(usuario):
    """El admin confirma a mano un correo (cuando no hay SMTP o el correo no
    llega). Solo marca; no cambia el correo. Sin contraseña ni token de por
    medio, el POST tiene que venir de nuestra propia página (403 si no)."""
    if not _mismo_origen():
        abort(403)
    try:
        usuarios.actualizar(usuario, correo_verificado=True)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("panel"))
    flash(f"Usuario '{usuario}' marcado como verificado.", "ok")
    return redirect(url_for("panel"))


def _job_id_imagen(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__imagen"


def _job_id_video(cliente, prompt_id):
    return f"{cliente}__{prompt_id}__video"


def _job_id_publicar(cliente, brief_id):
    return f"{cliente}__{brief_id}__publicar"


def _job_id_creative_flow(cliente, cf_id):
    return flowplus_lanzar.job_id(cliente, cf_id)


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

    # Anuncios sueltos (lo que quedó de Campañas, dentro de Experimentos): qué
    # tarjetas tienen un trabajo del worker en curso (publicar o refrescar
    # métricas), para que la tarjeta muestre la barra y se recargue sola.
    ads_dict = ads_mod.cargar(cliente)
    trabajos_ads = {}
    for ad_id in ads_dict:
        for jid in (f"{cliente}__{ad_id}__metricas", f"{cliente}__{ad_id}__ads_publicar"):
            if trabajos.en_curso(jid):
                trabajos_ads[ad_id] = {"job_id": jid}
                break

    # Experimentos: solo se consulta trabajos.en_curso para los experimentos
    # que de verdad podrían tener un job vivo (lanzando, o corriendo/pausado
    # con campaña ya creada en Meta) — evita 2 queries por cada experimento
    # ya cerrado/armando.
    experimentos_exp = experimentos.cargar(cliente)
    trabajos_exp = {}
    for e in experimentos_exp:
        if e["estado"] == "lanzando":
            jid = tareas_exp.job_id_lanzar(cliente, e["id"])
            if trabajos.en_curso(jid):
                trabajos_exp[e["id"]] = {"job_id": jid}
        elif e["meta_campaign_id"]:
            jid = tareas_exp.job_id_refrescar(cliente, e["id"])
            if trabajos.en_curso(jid):
                trabajos_exp[e["id"]] = {"job_id": jid}
    moneda_exp = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    # Bloque 4: propuestas pendientes por experimento (una consulta por
    # experimento con contador > 0), reglas y modos para los formularios.
    propuestas_exp = {e["id"]: propuestas.pendientes(cliente, e["id"]) for e in experimentos_exp if e["propuestas_pendientes"]}
    reglas_cliente = proyectos.reglas_defecto(cliente)
    # Bloque 5: productos importados/sincronizados, tiendas conectadas y el
    # estado del Pixel. El Pixel se lee SOLO del caché (`solo_cache=True`):
    # la página del proyecto nunca espera una ida a Graph (hasta 30 s bajo el
    # lock de Meta = un worker de gunicorn ocupado y un 502 en la página
    # principal). Quien llena el caché es el botón «Comprobar Pixel»
    # (cfg_pixel_refrescar, POST); con Meta conectado y caché vacío la
    # plantilla muestra «sin comprobar» + el botón. atribucion_sugerida
    # (más abajo) también mira solo caché, así que coincide con Configuración.
    capacidades_meta = meta_conexion.estado(cliente)
    meta_app = meta_conexion.app_publica(cliente)
    meta_conectado = capacidades_meta.get("estado") == "conectado"
    # Modo de la conexión con Meta (propia / agencia): en agencia la tarjeta
    # de _meta_conectar.html es «Gestionado por Creatv» (sin app ni botón de
    # conectar) y Puesta a punto mira que la agencia esté conectada, no la app.
    datos_meta = meta_conexion.cargar(cliente) or {}
    modo_meta = meta_conexion.MODO_AGENCIA if datos_meta.get("modo") == meta_conexion.MODO_AGENCIA else "propia"
    agencia_conectada = meta_agencia.conectada() if modo_meta == meta_conexion.MODO_AGENCIA else False
    meta_detalle = meta_conexion._detalle(datos_meta)
    estado_pixel = meta_conexion.estado_pixel(cliente, solo_cache=True) if meta_conectado else None
    tiendas_cliente = tiendas.listar(cliente)
    # Catálogo › Productos: cada activo tiene su fila comercial (se crea al
    # vuelo si falta) y la fila se pinta en la tarjeta del activo.
    activos_producto = _productos_con_uso(cliente)
    _asegurar_filas_producto(cliente, activos_producto)
    productos_tienda = _productos_tienda_contexto(cliente, experimentos_exp)
    producto_comercial = _producto_comercial_contexto(productos_tienda)
    # Una sola consulta (solo caché) para atribución y objetivo sugeridos.
    atribucion_sug = experimentos.atribucion_sugerida(cliente)
    # Bloque 7: canales orgánicos del proyecto, publicaciones por pieza (UNA
    # consulta) y qué piezas tienen una publicación orgánica corriendo en el
    # worker (UNA consulta a la cola, como _trabajos_productos).
    canales_org = organico.canales(cliente)
    publicaciones_por_pieza = organico.por_pieza(cliente)
    trabajos_org = _trabajos_organico(cliente, publicaciones_por_pieza)
    # Gasto real (Task 3): el tablero se calcula UNA vez (cacheado) y de ahí
    # sale la pauta por moneda; la generación viene de la tabla `gasto`.
    tablero_ctx = _contexto_tablero(cliente)
    gasto_ctx = _contexto_gasto(cliente, tablero_ctx)

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
        productos=activos_producto,
        categorias=catalogo_productos.CATEGORIAS,
        activos_por_categoria={cid: (activos_producto if cid == "producto" else catalogo_productos.listar(cliente, cid)) for cid in catalogo_productos.CATEGORIAS},
        producto_comercial=producto_comercial,
        productos_sin_activo=[p for p in productos_tienda if not p["activo_ok"]],
        monedas_catalogo=sorted(PRESUPUESTO_MINIMO_DIARIO),
        moneda_catalogo=_moneda_por_defecto(cliente),
        etiquetas_fuente=ETIQUETAS_FUENTE,
        tipos_producto=prompt_swap.TIPOS,
        zonas_cuerpo=mapa_corporal.ZONAS,
        presets_cuerpo=mapa_corporal.PRESETS,
        etiquetas_presets=mapa_corporal.ETIQUETAS_PRESETS,
        banco_prompts=banco_prompts.listar(),
        nombre_proyecto=proyectos.nombre_visible(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
        creative_flow_items=_creative_flow_items(cliente),
        preferencias_flowplus=proyectos.preferencias_flowplus(cliente),
        preferencias_sonido=proyectos.preferencias_sonido(cliente),
        fp_prefill=session.pop("fp_prefill", None),
        logos=_logos(cliente),
        referencias_bandeja=referencias_flowplus.listar(cliente),
        trabajo_link={"job_id": _job_id_link(cliente)} if trabajos.en_curso(_job_id_link(cliente)) else None,
        modelos_flowplus_video=flowplus_modelos.VIDEO,
        duraciones_crear=flowplus_modelos.DURACIONES_CREAR,
        formatos_nombres=flowplus_modelos.FORMATOS_NOMBRES,
        modelos_flowplus_imagen=flowplus_modelos.IMAGEN,
        ads=ads_dict,
        trabajos_ads=trabajos_ads,
        preferencias_swap=proyectos.preferencias(cliente),
        proveedores_swap_imagen=PROVEEDORES_SWAP_IMAGEN,
        proveedores_swap_video=PROVEEDORES_SWAP_VIDEO,
        nombres_proveedor_swap=NOMBRES_PROVEEDOR_SWAP,
        capacidades_meta=capacidades_meta,
        meta_app=meta_app,
        modo_meta=modo_meta,
        agencia_conectada=agencia_conectada,
        meta_detalle=meta_detalle,
        meta_redirect_uri=os.environ.get("META_REDIRECT_URI", ""),
        paises_fe=fe_tipos.PAISES,
        voces_fe=fal_audio.VOCES,
        estilos_fe=list(fe_tipos.ESTILOS_MUSICA),
        presets_mezcla=list(fe_mezcla.PRESETS),
        experimentos=experimentos_exp,
        experimentos_armando=[e for e in experimentos_exp if e["estado"] in ("armando", "error") and not e["meta_campaign_id"]],
        elegibles_exp=experimentos.elegibles(cliente),
        trabajos_exp=trabajos_exp,
        objetivos_exp=meta_campaign.OBJETIVOS_VALIDOS_FASE1,
        objetivo_exp_sugerido=experimentos.objetivo_sugerido(cliente, atribucion_sug),
        nombres_objetivo_exp=NOMBRES_OBJETIVO_EXP,
        minimo_diario_exp=PRESUPUESTO_MINIMO_DIARIO.get(moneda_exp, 1),
        moneda_exp=moneda_exp,
        propuestas_exp=propuestas_exp,
        reglas_defecto_exp=decisor.REGLAS_DEFECTO,
        reglas_enteras_exp=decisor.ENTEROS,
        reglas_desactivables_exp=decisor.UMBRALES_DESACTIVABLES,
        etiquetas_reglas_exp=decisor.ETIQUETAS,
        reglas_cliente=reglas_cliente,
        reglas_efectivas_exp={e["id"]: decisor.reglas_efectivas(reglas_cliente, e["reglas"]) for e in experimentos_exp},
        correo_notificaciones=proyectos.correo_notificaciones(cliente) or "",
        modos_exp=modos.MODOS,
        nombres_exp={e["id"]: e["nombre"] for e in experimentos_exp},
        productos_tienda=productos_tienda,
        tiendas_cliente=tiendas_cliente,
        trabajos_prod=_trabajos_productos(cliente, tiendas_cliente, productos_tienda),
        estado_pixel=estado_pixel,
        meta_conectado=meta_conectado,
        atribucion_sugerida=atribucion_sug,
        atribuciones_exp=experimentos.ATRIBUCIONES,
        pedidos_por_exp=tiendas.pedidos_por_experimento(cliente),
        cifrado_ok=cifrado.disponible(),
        meli_configurado=bool((os.environ.get("MELI_APP_ID") or "").strip()),
        tipos_tienda=conectores.TIPOS_API,
        llaves=_estado_llaves(url_for("meli_callback", _external=True), meta_app_registrada=bool(meta_app),
                              modo_meta=modo_meta, agencia_conectada=agencia_conectada),
        columnas_csv=conector_csv.COLUMNAS_AYUDA,
        tablero=tablero_ctx,
        canales_org=canales_org,
        **gasto_ctx,
        plataformas_org=organico.PLATAFORMAS,
        publicaciones_por_pieza=publicaciones_por_pieza,
        trabajos_org=trabajos_org,
        **sprints_rutas.contexto(cliente),
        **nicho_rutas.contexto(cliente),
    )


# Configuración › Puesta a punto: una tarjeta por servicio externo. Cada
# entrada dice para qué sirve, cómo se paga, dónde se consigue y qué variables
# van en el .env del servidor. El estado se calcula SOLO con
# bool(os.environ.get(var)) — el valor de una llave nunca sale de aquí ni
# llega a la plantilla. `{callback_meli}` en un paso se reemplaza por la URL
# real del callback cuando hay request (ver _estado_llaves).
SERVICIOS_LLAVES = (
    {
        "id": "anthropic",
        "nombre": "Anthropic (guiones y prompts)",
        "para_que": "Escribe los 5 prompts por idea y los guiones de las finales.",
        "costo": "Se paga por uso: centavos por guion.",
        "url": "https://console.anthropic.com/settings/keys",
        "url_texto": "console.anthropic.com › API keys",
        "variables": ["ANTHROPIC_API_KEY"],
        "nota": "Sin ella no hay prompts ni guiones.",
        "pasos": [
            "Entra a console.anthropic.com e inicia sesión (o crea la cuenta de la empresa).",
            "En «Billing» carga saldo o pon una tarjeta: sin saldo la llave existe pero no responde.",
            "Ve a «API keys» › «Create key», ponle un nombre (por ejemplo «creatv») y cópiala: solo se muestra una vez.",
            "Pégala como ANTHROPIC_API_KEY en el .env del servidor y reinicia los dos servicios.",
        ],
    },
    {
        "id": "fal",
        "nombre": "fal.ai (voz y música)",
        "para_que": "Voz en off (ElevenLabs), subtítulos por palabra (Whisper) y música (Stable Audio) de las finales.",
        "costo": "Se paga por uso: alrededor de $0.05 por final.",
        "url": "https://fal.ai/dashboard/keys",
        "url_texto": "fal.ai › Dashboard › Keys",
        "variables": ["FAL_KEY"],
        "nota": "Sin ella las finales salen sin voz ni música.",
        "pasos": [
            "Regístrate en fal.ai (con Google o GitHub; no pide verificación de negocio).",
            "En «Billing» agrega una tarjeta o saldo prepago.",
            "Ve a «Keys» › «Add key», elige alcance «API» y copia la llave.",
            "Pégala como FAL_KEY en el .env del servidor y reinicia.",
        ],
    },
    {
        "id": "higgsfield",
        "nombre": "Higgsfield (video e imagen)",
        "para_que": "Genera la imagen candidata y el video de cada pieza.",
        "costo": "Por créditos: ~1.5 por imagen y ~8 por video; se compran por paquetes.",
        "url": "https://higgsfield.ai/",
        "url_texto": "higgsfield.ai › API",
        "variables": ["HF_API_KEY_ID", "HF_API_KEY_SECRET"],
        "nota": "Sin ella no se generan piezas.",
        "pasos": [
            "Inicia sesión en higgsfield.ai y compra un paquete de créditos en «Billing».",
            "Abre la sección «API» (o «Developers») de tu cuenta y crea una llave nueva.",
            "Copia los dos valores: el Key ID y el Key Secret (el secreto solo se muestra una vez).",
            "Pégalos como HF_API_KEY_ID y HF_API_KEY_SECRET en el .env del servidor y reinicia.",
        ],
    },
    {
        "id": "r2",
        "nombre": "Cloudflare R2 (almacenamiento)",
        "para_que": "Guarda cada imagen y video generado y les da una URL pública permanente.",
        "costo": "Casi gratis: 10 GB al mes sin costo y sin cobro por descarga.",
        "url": "https://dash.cloudflare.com/?to=/:account/r2",
        "url_texto": "dash.cloudflare.com › R2 › Manage API tokens",
        "variables": ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL"],
        "nota": "Sin ella los videos no tienen URL pública y Meta no puede usarlos.",
        "pasos": [
            "En dash.cloudflare.com entra a «R2» y crea un bucket (ese nombre es R2_BUCKET_NAME).",
            "En «Settings» del bucket activa «Public access» (r2.dev o un dominio propio): esa URL es R2_PUBLIC_BASE_URL.",
            "Vuelve a R2 › «Manage R2 API tokens» › «Create API token» con permiso «Object Read & Write».",
            "Copia el Access Key ID y el Secret Access Key; el Account ID está en la barra lateral de R2.",
            "Pega las cinco variables en el .env del servidor y reinicia.",
        ],
    },
    {
        "id": "meta",
        "nombre": "Meta (anuncios)",
        "para_que": "Crea las campañas, conjuntos y anuncios de cada experimento y lee sus métricas.",
        "costo": "La pauta se cobra en tu cuenta publicitaria; la API no cuesta.",
        "url": "https://business.facebook.com/settings/payment-methods",
        "url_texto": "business.facebook.com › Facturación",
        "variables": [],
        "por_proyecto": True,
        "nota": "No va en el .env: cada proyecto registra su propia app de Meta (id, secret y configuración de Facebook Login) en el bloque «Conecta tu cuenta de Meta» de abajo, y ahí mismo pulsa «Conectar con Meta».",
        "pasos": [
            "En developers.facebook.com crea una app tipo Business con «Facebook Login for Business» y «Marketing API»; anota el App ID, el App Secret y el id de la configuración de Login.",
            "Pégalos en «Conecta tu cuenta de Meta» (abajo, o en Experimentos): el secret se guarda en el servidor y nunca vuelve a pantalla.",
            "En business.facebook.com › Configuración › Facturación agrega un método de pago a la cuenta publicitaria: sin él Meta no activa ningún anuncio.",
            "Pulsa «Conectar con Meta» aquí abajo, inicia sesión con tu Facebook y elige la cuenta publicitaria y la Página.",
            "Si Meta muestra un error de permisos, pide que agreguen tu Facebook como probador de la app.",
        ],
    },
    {
        "id": "smtp",
        "nombre": "Correo de la plataforma (cuentas y avisos)",
        "para_que": "Manda el enlace para confirmar el correo de cada cuenta y el de recuperar la contraseña; "
                    "también los avisos (propuestas pendientes, ganadores, rechazos de Meta, lanzamientos fallidos).",
        "costo": "Depende del proveedor de correo; con una cuenta normal no cuesta.",
        "url": "https://support.google.com/accounts/answer/185833",
        "url_texto": "Google › Contraseñas de aplicación",
        "variables": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL"],
        "nota": "Sin esto nadie puede confirmar su correo ni recuperar la contraseña solo (el administrador "
                "tiene que marcar las cuentas a mano en el panel) y los avisos solo quedan en la bitácora.",
        "opcional": True,
        "pasos": [
            "Elige la cuenta que va a enviar (Gmail, Outlook o el correo del dominio).",
            "Si es Gmail: en myaccount.google.com › Seguridad activa la «Verificación en dos pasos» y luego, "
            "en «Contraseñas de aplicación», crea una para «Creatv»: los 16 caracteres que te da son SMTP_PASS "
            "(no la contraseña normal de la cuenta). SMTP_USER es la dirección completa y SMTP_FROM la misma.",
            "Anota el servidor y el puerto (Gmail: smtp.gmail.com y 587, STARTTLS).",
            "Pega SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS y SMTP_FROM en el .env del servidor, junto con "
            "PLATAFORMA_URL (la dirección pública del sitio, p. ej. https://app.creatvmachine.com: es la base de "
            "los enlaces que van en los correos), y reinicia los dos servicios.",
            "Prueba con «Reenviar» en Configuración › Cuenta: debe llegar el correo de confirmación. "
            "Abajo, en «Correo de avisos», escribe a qué dirección llegan los avisos de este proyecto.",
        ],
    },
    {
        "id": "meli",
        "nombre": "MercadoLibre (opcional)",
        "para_que": "Trae las publicaciones activas de una tienda de MercadoLibre al catálogo.",
        "costo": "Gratis: solo lectura de tus publicaciones.",
        "url": "https://developers.mercadolibre.com/",
        "url_texto": "developers.mercadolibre.com",
        "variables": ["MELI_APP_ID", "MELI_SECRET"],
        "nota": "Sin esto no aparece el botón «Conectar con MercadoLibre» en Tienda.",
        "opcional": True,
        "pasos": [
            "En developers.mercadolibre.com entra con la cuenta de la tienda y ve a «Mis aplicaciones» › «Crear nueva aplicación».",
            "Marca los permisos de lectura y «offline_access» (para renovar el token solo).",
            "En «URI de redirect» pon exactamente {callback_meli}.",
            "Copia el App ID y la Secret Key y pégalos como MELI_APP_ID y MELI_SECRET en el .env del servidor; reinicia.",
            "Luego, en «Conectar tu tienda» › MercadoLibre, pulsa «Conectar con MercadoLibre».",
        ],
    },
)


# Tarjeta Meta cuando el proyecto está en modo agencia: no hay app ni llave
# que conseguir; lo único que cuenta es que la agencia esté conectada.
NOTA_META_AGENCIA = ("Este proyecto lo gestiona Creatv en Meta (modo agencia): no registra una app ni conecta "
                     "nada aquí. La cuenta publicitaria y la Página se las asigna el administrador desde el "
                     "panel; pídele a él cualquier cambio.")
PASOS_META_AGENCIA = [
    "No tienes que conseguir ninguna llave: Creatv conecta su Business Manager una sola vez y te asigna la cuenta y la Página.",
    "Si quieres cambiar de cuenta publicitaria o de Página, o volver a usar tu propia app de Meta, pídeselo al administrador.",
    "Agrega un método de pago a la cuenta publicitaria en business.facebook.com › Configuración › Facturación: sin él Meta no activa ningún anuncio.",
]


def _estado_llaves(callback_meli=None, meta_app_registrada=False, modo_meta="propia", agencia_conectada=False):
    """Tarjetas de Configuración › Puesta a punto. Devuelve una lista de dicts
    {id, nombre, para_que, costo, estado, url, url_texto, variables, faltan,
    nota, pasos, opcional} donde `estado` es «configurada» (todas las
    variables presentes), «falta» (ninguna) o «parcial» (algunas). Solo mira
    bool(os.environ.get(var)): ningún valor sale de aquí. `callback_meli` es
    la URL real del callback de MercadoLibre para el paso de la app (fuera de
    un request se deja el texto genérico). La tarjeta Meta depende del modo
    del proyecto: en «propia» cuenta la app registrada; en «agencia» cuenta
    que la agencia esté conectada (`agencia_conectada`), y nota/pasos cambian."""
    callback = callback_meli or "<url del sitio>/meli/callback"
    tarjetas = []
    for s in SERVICIOS_LLAVES:
        nota, pasos = s["nota"], s["pasos"]
        if s.get("por_proyecto") and modo_meta == meta_conexion.MODO_AGENCIA:
            # Meta en modo agencia: la conexión es de Creatv, no del proyecto.
            presentes = ["conexión de agencia de Creatv"] if agencia_conectada else []
            faltan = [] if agencia_conectada else ["conexión de agencia de Creatv (la conecta el administrador)"]
            nota, pasos = NOTA_META_AGENCIA, PASOS_META_AGENCIA
        elif s.get("por_proyecto"):
            # Meta: la app es del proyecto (clientes/<c>/meta_app.json), no del .env.
            presentes = ["app de Meta del proyecto"] if meta_app_registrada else []
            faltan = [] if meta_app_registrada else ["app de Meta del proyecto"]
        else:
            presentes = [v for v in s["variables"] if bool((os.environ.get(v) or "").strip())]
            faltan = [v for v in s["variables"] if v not in presentes]
        if not faltan:
            estado = "configurada"
        elif not presentes:
            estado = "falta"
        else:
            estado = "parcial"
        tarjetas.append({
            "id": s["id"],
            "nombre": s["nombre"],
            "para_que": s["para_que"],
            "costo": s["costo"],
            "estado": estado,
            "url": s["url"],
            "url_texto": s["url_texto"],
            "variables": list(s["variables"]),
            "faltan": faltan,
            "nota": nota,
            "opcional": bool(s.get("opcional")),
            "pasos": [p.replace("{callback_meli}", callback) for p in pasos],
        })
    return tarjetas


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

def _cat(valor):
    """Categoría del catálogo pedida por la ruta (query o form); 'producto' por defecto."""
    return catalogo_productos.categoria_valida(valor or catalogo_productos.CATEGORIA_POR_DEFECTO)


@app.route("/cliente/<cliente>/productos/<producto_id>/imagen")
def imagen_producto(cliente, producto_id):
    """Sirve la foto representativa de un producto del catálogo directo del disco
    (son fijas, no hace falta subirlas a R2)."""
    producto = catalogo_productos.encontrar(cliente, producto_id, categoria=_cat(request.args.get("categoria") or request.form.get("categoria")))
    if not producto:
        flash(f"No encontré el producto {producto_id}", "error")
        return redirect(url_for("ver_cliente", cliente=cliente))
    return send_file(producto["representativa"])


@app.route("/cliente/<cliente>/productos/<producto_id>/imagen/<nombre>")
def imagen_producto_archivo(cliente, producto_id, nombre):
    """Sirve UNA foto concreta del producto — la pantalla de gestión muestra
    todas las referencias, no solo la representativa."""
    try:
        carpeta = catalogo_productos.carpeta_de(cliente, producto_id, categoria=_cat(request.args.get("categoria") or request.form.get("categoria")))
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


@app.route("/cliente/<cliente>/preferencias/guardar", methods=["POST"])
def guardar_preferencias_swap(cliente):
    """Modelo por defecto de FlowClone (foto/video) + si la mejora de calidad
    va marcada por defecto — antes se elegía en cada generación, ahora es
    configuración de cliente."""
    proveedor_foto = request.form.get("proveedor_foto", "").strip()
    proveedor_video = request.form.get("proveedor_video", "").strip()
    mejorar_calidad = bool(request.form.get("mejorar_calidad"))

    if proveedor_foto not in PROVEEDORES_SWAP_IMAGEN:
        flash("Modelo de foto inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    if proveedor_video not in PROVEEDORES_SWAP_VIDEO:
        flash("Modelo de video inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))

    proyectos.guardar_preferencias(cliente, proveedor_foto, proveedor_video, mejorar_calidad)
    flash("Modelos por defecto actualizados.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/preferencias_flowplus/guardar", methods=["POST"])
def guardar_preferencias_flowplus(cliente):
    modelo_video = request.form.get("modelo_video", "").strip()
    modelo_imagen = request.form.get("modelo_imagen", "").strip()
    if modelo_video not in flowplus_modelos.VIDEO or modelo_imagen not in flowplus_modelos.IMAGEN:
        flash("Modelo inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    proyectos.guardar_preferencias_flowplus(
        cliente, modelo_video, modelo_imagen,
        idioma_prompt=(request.form.get("idioma_prompt") or "es").strip(),
        duracion_defecto=request.form.get("duracion_defecto") or 8)
    flash("Modelos por defecto de FlowPlus actualizados.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/preferencias_sonido/guardar", methods=["POST"])
def guardar_preferencias_sonido(cliente):
    con_sonido = request.form.get("con_sonido") == "si"
    estilo = (request.form.get("musica_al_crear") or "").strip()
    if estilo not in fe_tipos.ESTILOS_MUSICA:
        estilo = ""
    proyectos.guardar_preferencias_sonido(cliente, con_sonido, estilo)
    flash("Preferencias de sonido guardadas.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


_MONEDA_RE = re.compile(r"^[A-Z]{3}$")


def _moneda_por_defecto(cliente):
    """La moneda de la cuenta publicitaria de Meta del proyecto, o COP si
    todavía no conectó Meta — es la que hereda un producto del catálogo al
    que no se le escribió moneda."""
    return ((meta_conexion.cargar(cliente) or {}).get("moneda") or "COP").upper()


def _campos_comerciales(form):
    """Lee del formulario de Catálogo lo comercial de un producto (precio,
    moneda, url_compra, en_prueba, prioridad) para `tiendas.marcar_producto`.
    Solo devuelve las claves que venían en el formulario, salvo `en_prueba`
    (un checkbox sin marcar no viaja: siempre se resuelve). Un valor
    inválido NO frena el alta ni la edición del activo: se avisa con flash
    y esa clave se omite (queda como estaba, o vacía si es nueva).
    `wa.me/…` se normaliza a `https://wa.me/…` — es la URL de compra más
    común de quien vende por WhatsApp y nadie la escribe con https."""
    campos = {"en_prueba": form.get("en_prueba") in ("on", "1", "true")}
    if "precio" in form:
        precio_txt = (form.get("precio") or "").strip().replace(",", ".")
        try:
            precio = float(precio_txt) if precio_txt else None
            if precio is not None and (not math.isfinite(precio) or precio < 0):
                raise ValueError
            campos["precio"] = precio
        except ValueError:
            flash("El precio tiene que ser un número positivo (ej. 89900 o 25,50); no lo guardé.", "error")
    if "prioridad" in form:
        try:
            prioridad = int(form.get("prioridad") or 0)
            if not (0 <= prioridad <= 100):
                raise ValueError
            campos["prioridad"] = prioridad
        except ValueError:
            flash("La prioridad va de 0 a 100; no la guardé.", "error")
    if "moneda" in form:
        moneda = (form.get("moneda") or "").strip().upper()
        if moneda and not _MONEDA_RE.match(moneda):
            flash("La moneda va en código de 3 letras (COP, MXN, USD…); no la guardé.", "error")
        else:
            campos["moneda"] = moneda or None
    if "url_compra" in form:
        url = (form.get("url_compra") or "").strip()
        if url.lower().startswith("wa.me/"):
            url = "https://" + url
        if url and not url.startswith(("http://", "https://")):
            flash("La URL de compra tiene que empezar por http:// o https:// (o ser wa.me/…); no la guardé.", "error")
        else:
            campos["url_compra"] = url or None
    return campos


def _guardar_fila_producto(cliente, producto_id, nombre, descripcion, campos, desarchivar=False):
    """Escribe lo comercial del activo `producto_id` en su fila `producto`
    (`tiendas.asegurar_manual` la crea si no existe). Una fila sin moneda
    hereda la de la cuenta de Meta (o COP). `desarchivar`: al CREAR el
    activo, si su fila estaba archivada (se eliminó y se volvió a crear con
    el mismo nombre) vuelve a la lista."""
    nombre = (nombre or "").strip()
    if not nombre:
        # Editar sin nombre (el formulario no lo trae) no debe dejar una
        # fila nueva sin nombre: el del activo, o su id.
        nombre = (catalogo_productos.cargar_meta(cliente).get(producto_id) or {}).get("nombre") or producto_id
    pid = tiendas.asegurar_manual(cliente, producto_id, nombre, descripcion)
    fila = tiendas.producto(cliente, pid)
    valores = dict(campos)
    if nombre:
        valores["nombre"] = nombre
    if descripcion is not None:
        valores["descripcion"] = descripcion.strip()
    if not valores.get("moneda") and not (fila or {}).get("moneda"):
        valores["moneda"] = _moneda_por_defecto(cliente)
    if desarchivar and (fila or {}).get("archivado"):
        valores["archivado"] = False
    tiendas.marcar_producto(cliente, pid, **valores)
    return pid


@app.route("/cliente/<cliente>/productos/crear", methods=["POST"])
def crear_producto(cliente):
    # "volver": pestaña que abrió el alta rápida (FlowClone, FlowPlus o FlowCatálogo).
    volver = request.form.get("volver") or "cambiar"
    nombre = (request.form.get("nombre") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    categoria = _cat(request.form.get("categoria"))
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not nombre:
        flash("Ponle un nombre.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))
    if not archivos:
        flash("Sube al menos una foto.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))
    try:
        producto_id = catalogo_productos.crear(
            cliente, nombre, descripcion, tipo=request.form.get("tipo"),
            zonas=request.form.getlist("zonas"), categoria=categoria,
            regla=request.form.get("regla", ""))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))

    guardadas = _guardar_fotos_producto(cliente, producto_id, archivos, categoria=categoria)
    if not guardadas:
        # Sin ninguna foto válida el producto no aparecería en el catálogo:
        # mejor deshacer que dejar una carpeta fantasma.
        catalogo_productos.eliminar(cliente, producto_id, categoria=categoria)
        flash("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))
    if categoria == "producto":
        # Solo lo que se vende tiene fila comercial (precio, url de compra,
        # en prueba): un personaje o un entorno no van a un experimento.
        _guardar_fila_producto(cliente, producto_id, nombre, descripcion,
                               _campos_comerciales(request.form), desarchivar=True)
    flash(f"Producto creado: {nombre} ({guardadas} foto(s)).", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))


def _guardar_fotos_producto(cliente, producto_id, archivos, categoria="producto"):
    """Guarda las fotos en la carpeta del producto y devuelve cuántas entraron.
    Quedan SOLO en disco a propósito: catalogo_productos las lee de ahí y el
    swap las sube a R2 recién cuando se va a generar."""
    carpeta = catalogo_productos.carpeta_de(cliente, producto_id, categoria)
    os.makedirs(carpeta, exist_ok=True)
    guardadas = 0
    for archivo in archivos:
        nombre = secure_filename(archivo.filename)
        if not nombre.lower().endswith(catalogo_productos.IMAGE_EXTS):
            continue
        # Varias fotos con el mismo nombre (desde el celular todas llegan como
        # "image.jpeg") no se pisan: se numeran.
        base, ext = os.path.splitext(nombre)
        destino = os.path.join(carpeta, nombre)
        n = 2
        while os.path.exists(destino):
            destino = os.path.join(carpeta, f"{base}_{n}{ext}")
            n += 1
        archivo.save(destino)
        guardadas += 1
    return guardadas


@app.route("/cliente/<cliente>/productos/<producto_id>/actualizar", methods=["POST"])
def actualizar_producto(cliente, producto_id):
    categoria = _cat(request.form.get("categoria"))
    try:
        catalogo_productos.actualizar(
            cliente, producto_id,
            nombre=request.form.get("nombre"),
            descripcion=request.form.get("descripcion"),
            tipo=request.form.get("tipo"),
            zonas=request.form.getlist("zonas"),
            categoria=categoria, regla=request.form.get("regla"),
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    if categoria == "producto":
        # La fila comercial se crea aquí si el activo es anterior a que
        # existiera (no hay migración: se enlaza al primer uso).
        _guardar_fila_producto(cliente, producto_id, request.form.get("nombre"),
                               request.form.get("descripcion"), _campos_comerciales(request.form))
    flash("Producto actualizado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/subir", methods=["POST"])
def subir_imagen_producto(cliente, producto_id):
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not archivos:
        flash("No elegiste ninguna foto.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    try:
        guardadas = _guardar_fotos_producto(cliente, producto_id, archivos, categoria=_cat(request.form.get("categoria")))
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    if guardadas:
        flash(f"{guardadas} foto(s) agregada(s).", "ok")
    else:
        flash("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/<nombre>/eliminar", methods=["POST"])
def eliminar_imagen_producto(cliente, producto_id, nombre):
    try:
        ok, mensaje = catalogo_productos.eliminar_imagen(cliente, producto_id, nombre, categoria=_cat(request.form.get("categoria")))
    except ValueError as e:
        ok, mensaje = False, str(e)
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/productos/<producto_id>/eliminar", methods=["POST"])
def eliminar_producto(cliente, producto_id):
    """Borra el producto y TODAS sus fotos del disco. Irreversible — por eso la
    plantilla lo pide con un modal que nombra el producto y avisa cuántos swaps
    ya generados lo referencian."""
    categoria = _cat(request.form.get("categoria"))
    producto = catalogo_productos.encontrar(cliente, producto_id, categoria=_cat(request.args.get("categoria") or request.form.get("categoria")))
    nombre = producto["nombre"] if producto else producto_id
    try:
        catalogo_productos.eliminar(cliente, producto_id, categoria=categoria)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    if categoria == "producto":
        # La fila comercial NO se borra: se archiva (a mano, como en
        # prod_archivar) para que un experimento que ya la use no se quede
        # sin producto y para no perder precio/url si se vuelve a crear.
        fila = tiendas.por_activo(cliente).get(producto_id)
        if fila and not fila["archivado"]:
            tiendas.marcar_producto(cliente, fila["id"], archivado=True)
    flash(f"Producto eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


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
    # Id numérico de la pieza por sesión, UNA consulta para toda la pestaña:
    # la tarjeta enlaza «Probar en Meta» a la galería de Experimentos
    # (#experimentos?piezas=<pieza_id>). Las finales ya traen su pieza_id.
    pieza_ids = creative_flow.piezas_ids_por_legado(cliente)
    items = []
    for cf_id, entry in sorted(
        data.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True
    ):
        job_id = _job_id_creative_flow(cliente, cf_id)
        # trabajo_director solo tiene sentido (y solo se consulta la cola) en
        # prompt_pendiente: es el único estado donde la tarjeta muestra su
        # barra de progreso — una consulta menos por tarjeta en cualquier otro
        # estado.
        jid_director = tareas_director.job_id(cliente, cf_id)
        trabajo_director = (
            {"job_id": jid_director} if entry.get("estado") == "prompt_pendiente" and trabajos.en_curso(jid_director) else None)
        item = {
            "id": cf_id,
            **entry,
            "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
            "trabajo_director": trabajo_director,
            "pieza_id": pieza_ids.get(cf_id),
        }
        # Si ya existe una hija de versión B (creative_flow.duplicar la crea con
        # derivado_de=cf_id, variante="B"), no tiene sentido ofrecer generarla de
        # nuevo desde la tarjeta del padre: la plantilla oculta la casilla.
        item["tiene_hija_b"] = any(e.get("derivado_de") == cf_id and e.get("variante") == "B" for e in data.values())
        # Estimado real vía wan3_client.estimate_video() en vez de un número
        # calculado a mano en la plantilla (duracion * 0.10) — usa la misma
        # tabla de precios (COSTO_USD_POR_SEGUNDO) que generar_video() real,
        # así el botón nunca muestra un costo distinto al que se cobra.
        if entry.get("estado") in ("prompt_listo", "error"):
            if entry.get("tipo") == "imagen":
                item["costo_estimado"] = flowplus_modelos.estimate_imagen(
                    entry.get("modelo") or flowplus_modelos.IMAGEN_POR_DEFECTO,
                    n_referencias=len(entry.get("referencias_urls") or []))
            else:
                mid = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
                item["costo_estimado"] = flowplus_modelos.estimate_video(
                    mid, entry["duracion_objetivo"], con_sonido=entry.get("con_sonido", True) is not False,
                    calidad=entry.get("calidad") or "final")
        item["modelo_nombre"] = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre", "Wan 3.0")
        # Final edition: solo tiene sentido sobre un video ya listo. Cada final
        # y el guion llevan su propio trabajo del worker para la barra de la UI.
        item["guion_base"] = None
        item["finales"] = []
        item["trabajo_guion"] = None
        if entry.get("estado") == "video_listo" and (entry.get("tipo") or "video") != "imagen":
            item["guion_base"] = creative_flow.guion_base(cliente, cf_id)
            jid_guion = tareas_fe.job_id_guion(cliente, cf_id)
            item["trabajo_guion"] = {"job_id": jid_guion} if trabajos.en_curso(jid_guion) else None
            for f in creative_flow.finales(cliente, cf_id):
                jid = tareas_fe.job_id_final(cliente, cf_id, f["idioma"], f["pais"], variante=f.get("variante"))
                f["trabajo"] = {"job_id": jid} if f.get("estado") == "generando" and trabajos.en_curso(jid) else None
                item["finales"].append(f)
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
# Mínimo diario que Meta acepta por divisa (aprox., para avisar antes de fallar).
PRESUPUESTO_MINIMO_DIARIO = {"USD": 1, "COP": 4000, "MXN": 20, "EUR": 1, "BRL": 5, "PEN": 4, "CLP": 1000, "ARS": 1000}
# Rótulos en español del objetivo de Meta en «Probar en Meta › Avanzado» (Bloque 6).
# El valor sigue siendo el enum de Meta; solo cambia lo que se lee.
NOMBRES_OBJETIVO_EXP = {"OUTCOME_SALES": "Compras (requiere Pixel)", "OUTCOME_TRAFFIC": "Tráfico (clics al enlace)",
                        "OUTCOME_ENGAGEMENT": "Interacción", "OUTCOME_LEADS": "Clientes potenciales"}

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


# Etapas reales de los trabajos. Los nombres se usan en DOS lados (al declararlas
# en trabajos.iniciar y al anunciarlas con trabajos.reportar), así que van en
# constantes para que no puedan desincronizarse por un typo. Los pesos son
# "qué fracción del tiempo se lleva más o menos cada paso" — la llamada al
# modelo es de lejos la más larga.
ETAPA_MODELO = "Generando con el modelo"
ETAPA_DESCARGAR = "Descargando el resultado"
ETAPA_MEZCLA = "Mezclando sonido"
ETAPA_GUARDAR_VIDEO = "Guardando el video"
ETAPA_GUARDAR_IMAGEN = "Guardando la imagen"
# Las etapas propias del swap (subir original, preparar foto, mejorar, guardar
# y evaluar) viven en tareas/swap.py junto con ETAPAS_SWAP_*.

# ETAPAS_SWAP_* viven en tareas/swap.py (se importan arriba).
# ETAPAS_CREATIVE_FLOW vive en tareas/flowplus.py (se importa arriba).

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


@app.route("/cliente/<cliente>/swap/generar", methods=["POST"])
def generar_swap(cliente):
    """Sube una o más fotos/videos del usuario y lanza un swap por cada uno en
    segundo plano, todos contra el mismo producto elegido — antes solo
    aceptaba un archivo a la vez."""
    archivos = [a for a in request.files.getlist("foto") if a and a.filename]
    producto_id = request.form.get("producto_id", "").strip()
    # El modelo ya no se elige por generación — es una preferencia de
    # configuración por cliente (FlowSettings), no del flujo de uso diario.
    prefs = proyectos.preferencias(cliente)
    # El modelo se elige en Crear › Cambiar producto (viene en el formulario);
    # si no viene, manda el que está por defecto en FlowSettings.
    proveedor_foto = (request.form.get("proveedor_foto") or "").strip() or prefs["proveedor_foto"]
    proveedor_video = (request.form.get("proveedor_video") or "").strip() or prefs["proveedor_video"]
    # Segunda pasada opcional de calidad. Solo aplica a FOTO: el upscaler de
    # Bria es de imagen, no de video.
    mejorar_calidad = bool(prefs["mejorar_calidad"])
    if proveedor_foto not in PROVEEDORES_SWAP_IMAGEN:
        proveedor_foto = "nano_banana"
    if proveedor_video not in PROVEEDORES_SWAP_VIDEO:
        proveedor_video = "seedance25_edit"

    if not archivos:
        flash("Sube al menos una foto o video primero.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    producto = catalogo_productos.encontrar(cliente, producto_id)
    if not producto:
        flash("Elige un producto del catálogo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    lanzados = 0
    for archivo in archivos:
        if _lanzar_swap(cliente, archivo, producto, producto_id, proveedor_foto, proveedor_video, mejorar_calidad):
            lanzados += 1

    if lanzados == 1:
        flash("Generando el swap…", "ok")
    elif lanzados > 1:
        flash(f"Generando {lanzados} swaps…", "ok")
    else:
        flash("Ya se estaban generando esos swaps — espera a que terminen.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


def _lanzar_swap(cliente, archivo, producto, producto_id, proveedor_foto, proveedor_video, mejorar_calidad):
    """Un solo archivo -> un solo swap, en su propio job de fondo. Extraído de
    generar_swap para poder subir varios archivos a la vez, cada uno con su
    propia barra de progreso independiente."""
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
    # La generación corre en el worker (sobrevive reinicios). Sin reintento
    # automático: es generación pagada, un segundo intento gastaría créditos
    # otra vez sobre un fallo que ya se le mostró a la persona.
    return trabajos.encolar(job_id, "swap_generar", {
        "cliente": cliente, "swap_id": swap_id, "producto_id": producto_id,
        "proveedor": proveedor, "tipo": tipo, "mejorar_calidad": bool(mejorar_calidad),
    }, cliente=cliente, duracion_estimada=duracion_estimada, etapas=etapas, max_intentos=1)


@app.route("/cliente/<cliente>/swap/<swap_id>/original")
def imagen_swap_original(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    # Las entradas reconstruidas desde la bitácora no tienen foto original: la
    # bitácora guarda el resultado, no la entrada. Sin este guardia,
    # os.path.exists(None) revienta con TypeError y devuelve un 500.
    if not entry or not entry.get("foto_original_local") or not os.path.exists(entry["foto_original_local"]):
        flash("No encontré la foto original.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    return send_file(entry["foto_original_local"])


@app.route("/cliente/<cliente>/swap/<swap_id>/eliminar", methods=["POST"])
def eliminar_swap(cliente, swap_id):
    swaps_mod.eliminar(cliente, swap_id)
    flash("Eliminado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/ads/nueva_campana", methods=["POST"])
def nueva_campana(cliente):
    """Campañas ya no existe como pestaña (se fundió en Experimentos). La ruta
    se conserva para enlaces/formularios viejos, pero no crea nada: avisa y
    manda a Experimentos, donde una pieza se mete en un experimento."""
    flash("Campañas ya no existe: crea un experimento con esa pieza.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad", methods=["POST"])
def enviar_swap_a_publicidad(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    if not entry or not entry.get("resultado_url"):
        flash("Ese swap todavía no tiene un resultado listo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    producto = catalogo_productos.encontrar(cliente, entry.get("producto_id"))
    nombre = producto["nombre"] if producto else entry.get("producto_id", "Swap")
    ads_mod.crear(cliente, "swap", swap_id, entry["resultado_url"], entry.get("tipo", "foto"), nombre)
    flash("Quedó en Experimentos › Anuncios sueltos — crea un experimento con esa pieza.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/video/<brief_id>/enviar_a_publicidad", methods=["POST"])
def enviar_video_a_publicidad(cliente, brief_id):
    data = estado_mod.cargar(cliente)
    entry = data.get(brief_id)
    if not entry or not entry.get("video_url"):
        flash("Ese video todavía no tiene una URL pública lista.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))

    nombre = entry.get("title") or brief_id
    ads_mod.crear(cliente, "idea_visual", brief_id, entry["video_url"], "video", nombre)
    flash("Quedó en Experimentos › Anuncios sueltos — crea un experimento con esa pieza.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


# ---------- Anuncios sueltos (Meta Ads, lo que quedó de Campañas; se ven dentro
# de Experimentos) — actualizar resultados, pausar/activar, eliminar de la lista
# local. Nunca borra una campaña real de Meta: eso queda para Meta Ads Manager a
# propósito (ver eliminar_ad más abajo). ----------

# ---------- Conexión con Meta (Facebook Login for Business) ----------
# La autorización es una ruta de la app (ya no un script de terminal), así
# que funciona en el VPS y desde el celular. Las credenciales quedan en
# clientes/<cliente>/meta.json (meta_conexion.py).

def _ir_a_flowmarketing(cliente):
    # La conexión con Meta se muestra en Experimentos (_meta_conectar.html).
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


MENSAJE_MODO_AGENCIA = "Este proyecto lo gestiona Creatv en Meta; pídele al administrador cualquier cambio."


def _bloqueo_modo_agencia(cliente):
    """Redirect con aviso si el proyecto está en modo agencia: las rutas de la
    app propia (registrar app, conectar, elegir, desconectar) no le aplican —
    la cuenta y la Página se las asigna el admin desde /admin/meta. Va ANTES
    del guard de correo verificado: un cliente en modo agencia no conecta
    nada, así que no tiene sentido pedirle que confirme el correo para
    decirle que no puede. None si el proyecto está en modo propia."""
    if meta_conexion.modo(cliente) != meta_conexion.MODO_AGENCIA:
        return None
    flash(MENSAJE_MODO_AGENCIA, "error")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/app", methods=["POST"])
def meta_app_guardar(cliente):
    """El proyecto registra SU app de Meta (id, secret, config de login).
    El secret va a disco (meta_app.json, 0600) y nunca vuelve a pantalla."""
    bloqueo = _bloqueo_modo_agencia(cliente) or _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    try:
        meta_conexion.guardar_app(cliente, {
            "app_id": request.form.get("app_id"),
            "app_secret": request.form.get("app_secret"),
            "login_config_id": request.form.get("login_config_id"),
        })
    except meta_conexion.ModoAgenciaError:
        flash(MENSAJE_MODO_AGENCIA, "error")
        return _ir_a_flowmarketing(cliente)
    except meta_conexion.MetaConexionError as e:
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)
    bitacora.registrar(cliente, "meta", "app", "ok", f"app {request.form.get('app_id', '').strip()} registrada")
    flash("App de Meta registrada para este proyecto. Ahora sí: Conectar con Meta.", "ok")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/app/borrar", methods=["POST"])
def meta_app_borrar(cliente):
    bloqueo = _bloqueo_modo_agencia(cliente)
    if bloqueo:
        return bloqueo
    meta_conexion.borrar_app(cliente)
    bitacora.registrar(cliente, "meta", "app", "ok", "app de Meta quitada")
    flash("App de Meta quitada de este proyecto. La conexión existente sigue hasta que la desconectes.", "ok")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/conectar")
def meta_conectar(cliente):
    bloqueo = _bloqueo_modo_agencia(cliente) or _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    state = meta_conexion.nuevo_state()
    session["meta_oauth"] = {"state": state, "cliente": cliente}
    try:
        return redirect(meta_conexion.url_dialogo(cliente, state))
    except meta_conexion.ModoAgenciaError:
        session.pop("meta_oauth", None)
        flash(MENSAJE_MODO_AGENCIA, "error")
        return _ir_a_flowmarketing(cliente)
    except meta_conexion.MetaConexionError as e:
        session.pop("meta_oauth", None)
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)


@app.route("/meta/callback")
def meta_callback():
    """Única ruta nueva SIN <cliente> en la URL (Meta redirige a una sola
    dirección registrada), así que el guard general no la cubre: el cliente
    sale de la sesión, nunca de la query, y el state es de un solo uso."""
    pendiente = session.pop("meta_oauth", None) or {}
    cliente = pendiente.get("cliente")
    state_ok = bool(pendiente.get("state")) and request.args.get("state") == pendiente.get("state")
    if not cliente or not state_ok:
        flash("La autorización con Meta no coincide con esta sesión — vuelve a intentarlo desde FlowMarketing.", "error")
        return _ir_a_flowmarketing(cliente) if cliente else redirect(url_for("index"))
    if not usuarios.puede_acceder(_sesion(), cliente):
        flash("No tienes acceso a ese proyecto.", "error")
        return redirect(url_for("index"))

    if request.args.get("error"):
        detalle = request.args.get("error_description") or request.args.get("error")
        bitacora.registrar(cliente, "meta", "conexion", "error", f"cancelado o denegado: {detalle}")
        flash(f"Meta no autorizó la conexión: {detalle}", "error")
        return _ir_a_flowmarketing(cliente)

    code = request.args.get("code", "")
    try:
        token_info = meta_conexion.cambiar_code_por_token(cliente, code)
        perfil = meta_conexion.obtener_perfil(token_info["token"])
        activos = meta_conexion.listar_activos(token_info["token"])
    except meta_conexion.MetaConexionError as e:
        bitacora.registrar(cliente, "meta", "conexion", "error", str(e))
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)

    # Va a disco (0600, ignorado por git) y no a la sesión: la cookie de Flask
    # tiene un tope de ~4 KB y los tokens de Página no caben.
    meta_conexion.guardar_pendiente(cliente, {
        **token_info,
        "business_id": perfil.get("client_business_id"),
        "usuario_meta": perfil.get("name"),
        "activos": activos,
    })
    return redirect(url_for("meta_elegir", cliente=cliente))


@app.route("/cliente/<cliente>/meta/elegir", methods=["GET", "POST"])
def meta_elegir(cliente):
    bloqueo = _bloqueo_modo_agencia(cliente)
    if bloqueo:
        return bloqueo
    pendiente = meta_conexion.cargar_pendiente(cliente)
    if not pendiente:
        flash("No hay una autorización de Meta en curso — empieza de nuevo con \"Conectar con Meta\".", "error")
        return _ir_a_flowmarketing(cliente)
    activos = pendiente.get("activos") or {}
    cuentas = activos.get("ad_accounts") or []
    paginas = activos.get("pages") or []
    if not cuentas and not paginas:
        flash("No hay una autorización de Meta en curso — empieza de nuevo con \"Conectar con Meta\".", "error")
        return _ir_a_flowmarketing(cliente)

    if request.method == "GET":
        return render_template(
            "meta_elegir.html", cliente=cliente, cuentas=cuentas, paginas=paginas,
            usuario_meta=pendiente.get("usuario_meta"), nombre_proyecto=proyectos.nombre_visible(cliente),
        )

    cuenta = next((a for a in cuentas if a["id"] == request.form.get("ad_account_id")), None)
    pagina = next((p for p in paginas if p["id"] == request.form.get("page_id")), None)
    if not cuenta or not pagina:
        flash("Elige una cuenta publicitaria y una Página de la lista.", "error")
        return redirect(url_for("meta_elegir", cliente=cliente))

    try:
        _guardar_conexion_propia(cliente, pendiente, cuenta, pagina)
    except meta_conexion.ModoAgenciaError:
        # Un admin asignó el proyecto a la agencia mientras el cliente elegía:
        # la asignación manda; la autorización a medias se descarta.
        meta_conexion.borrar_pendiente(cliente)
        flash(MENSAJE_MODO_AGENCIA, "error")
        return _ir_a_flowmarketing(cliente)
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", f"{cuenta.get('name')} · {pagina.get('name')}")
    aviso = "" if pagina.get("ig_user_id") else " Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincules en Facebook."
    flash(f"Meta conectado: {cuenta.get('name')} · {pagina.get('name')}.{aviso}", "ok")
    return _ir_a_flowmarketing(cliente)


def _guardar_conexion_propia(cliente, pendiente, cuenta, pagina):
    meta_conexion.guardar(cliente, {
        "token": pendiente["token"],
        "tipo_token": pendiente.get("tipo_token", ""),
        "expira_en": pendiente.get("expira_en"),
        "business_id": pendiente.get("business_id"),
        "ad_account_id": cuenta["id"],
        "ad_account_nombre": cuenta.get("name"),
        "moneda": cuenta.get("currency"),
        "page_id": pagina["id"],
        "page_nombre": pagina.get("name"),
        "page_access_token": pagina.get("access_token"),
        "ig_user_id": pagina.get("ig_user_id"),
        "ig_username": pagina.get("ig_username"),
        "conectado_en": datetime.now().isoformat(timespec="seconds"),
        "conectado_por": session.get("usuario"),
        "graph_version": meta_conexion.GRAPH_VERSION,
    })


@app.route("/cliente/<cliente>/meta/cancelar", methods=["POST"])
def meta_cancelar(cliente):
    """Aborta una autorización a medias (borra solo meta.pendiente.json).
    No toca meta.json: si el proyecto ya estaba conectado, sigue conectado."""
    meta_conexion.borrar_pendiente(cliente)
    flash("Conexión con Meta cancelada. Si ya tenías Meta conectado, sigue igual.", "ok")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/desconectar", methods=["POST"])
def meta_desconectar(cliente):
    bloqueo = _bloqueo_modo_agencia(cliente)
    if bloqueo:
        return bloqueo
    # Revocar la autorización en Meta invalida el token (y los de Página que
    # derivan de él); si falla, igual se borra localmente.
    revocado = meta_conexion.revocar(cliente)
    try:
        meta_conexion.borrar(cliente)
    except meta_conexion.ModoAgenciaError:
        flash(MENSAJE_MODO_AGENCIA, "error")
        return _ir_a_flowmarketing(cliente)
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", "desconectado" + (" y revocado en Meta" if revocado else ""))
    if revocado:
        flash("Meta desconectado de este proyecto y acceso revocado en Meta.", "ok")
    else:
        flash("Meta desconectado de este proyecto. La app sigue autorizada en tu Facebook hasta que la quites en Configuración › Integraciones de negocio.", "ok")
    return _ir_a_flowmarketing(cliente)


# ---------- Meta en modo agencia: panel del admin (/admin/meta) ----------
# El admin conecta UNA vez el Business Manager de Creatv con un token de
# usuario del sistema (meta_agencia lo guarda cifrado en kv) y a cada proyecto
# le asigna una cuenta publicitaria y una Página de las que ese Business ve.
# Todo es @requiere_admin; los POST exigen _mismo_origen (403 si no). El
# token solo viaja en el POST de conectar (campo type=password) y jamás
# vuelve a pantalla: ni en flashes (cola.sin_token por si Meta lo mete en un
# mensaje), ni en la plantilla (meta_agencia.publica()/estado() no lo traen).

PERMISOS_AGENCIA = ("ads_management", "ads_read", "business_management", "pages_show_list",
                    "pages_read_engagement", "pages_manage_posts", "pages_manage_ads",
                    "instagram_basic", "instagram_content_publish")


def _proyectos_meta_admin(conectada):
    """Una fila por proyecto para la tabla de /admin/meta: modo, asignación
    actual (nunca tokens) y, en modo propia, si tiene su propia conexión."""
    filas = []
    for cid in estado_mod.listar_clientes():
        crudo = meta_conexion._cargar_crudo(cid) or {}
        modo = meta_conexion.MODO_AGENCIA if crudo.get("modo") == meta_conexion.MODO_AGENCIA else "propia"
        filas.append({
            "id": cid,
            "nombre": proyectos.nombre_visible(cid),
            "modo": modo,
            "detalle": meta_conexion._detalle(crudo) if crudo else None,
            "propia_conectada": modo == "propia" and bool(crudo.get("token")),
            "app_propia": bool(meta_conexion.cargar_app(cid)),
        })
    return filas


@app.route("/admin/meta")
@requiere_admin
def admin_meta():
    """Estado de la agencia, formulario para conectar (o reconectar), activos
    del Business y la tabla de proyectos con su modo y asignación."""
    estado_ag = meta_agencia.estado()
    conectada = estado_ag["estado"] != "sin_conectar"
    activos = {"ad_accounts": [], "pages": []}
    error_activos = None
    if conectada:
        try:
            activos = meta_agencia.listar_activos()
        except meta_conexion.MetaConexionError as e:
            error_activos = cola.sin_token(str(e))
    filas = _proyectos_meta_admin(conectada)
    return render_template(
        "admin_meta.html",
        agencia=estado_ag, conectada=conectada, activos=activos, error_activos=error_activos,
        proyectos_meta=filas, asignados=sum(1 for f in filas if f["modo"] == meta_conexion.MODO_AGENCIA),
        cifrado_ok=cifrado.disponible(), permisos_agencia=", ".join(PERMISOS_AGENCIA),
        registro_ilegible=meta_agencia._registro_ilegible() if not conectada else False,
    )


def _volver_admin_meta():
    return redirect(url_for("admin_meta"))


@app.route("/admin/meta/conectar", methods=["POST"])
@requiere_admin
def admin_meta_conectar():
    if not _mismo_origen():
        abort(403)
    token = request.form.get("token", "")
    business_id = request.form.get("business_id", "")
    try:
        registro = meta_agencia.conectar(token, business_id)
    except meta_conexion.MetaConexionError as e:
        flash(f"No pude conectar la agencia: {cola.sin_token(str(e))}", "error")
        return _volver_admin_meta()
    bitacora.registrar("", "meta", "agencia", "ok", f"Business {registro.get('business_id')} conectado por {session.get('usuario')}")
    flash(f"Agencia conectada: {registro.get('business_nombre')} (usuario del sistema "
          f"{registro.get('usuario_nombre') or 'sin nombre'}). Ahora asigna cuenta y Página a cada proyecto.", "ok")
    return _volver_admin_meta()


@app.route("/admin/meta/desconectar", methods=["POST"])
@requiere_admin
def admin_meta_desconectar():
    if not _mismo_origen():
        abort(403)
    asignados = list(meta_agencia.proyectos_asignados())
    resultado = meta_agencia.desconectar()
    for cid in asignados:
        bitacora.registrar(cid, "meta", "agencia", "ok", "vuelve a modo propia: la agencia se desconectó")
    n = resultado.get("desasignados", 0)
    if not resultado.get("habia") and not n:
        flash("La agencia no estaba conectada.", "warn")
    elif n:
        flash(f"Agencia desconectada. {n} proyecto{'s' if n != 1 else ''} volvi{'eron' if n != 1 else 'ó'} a modo propia "
              "y se quedan sin conexión con Meta hasta que registren su app o vuelvas a asignarlos.", "ok")
    else:
        flash("Agencia desconectada. Ningún proyecto estaba asignado.", "ok")
    return _volver_admin_meta()


@app.route("/admin/meta/activos/actualizar", methods=["POST"])
@requiere_admin
def admin_meta_activos_actualizar():
    if not _mismo_origen():
        abort(403)
    try:
        activos = meta_agencia.listar_activos(forzar=True)
    except meta_conexion.MetaConexionError as e:
        flash(f"No pude leer los activos del Business: {cola.sin_token(str(e))}", "error")
        return _volver_admin_meta()
    flash(f"Activos actualizados: {len(activos['ad_accounts'])} cuenta(s) publicitaria(s) y {len(activos['pages'])} Página(s).", "ok")
    return _volver_admin_meta()


def _cliente_o_404(cliente):
    if cliente not in estado_mod.listar_clientes():
        abort(404)


@app.route("/admin/meta/asignar/<cliente>", methods=["POST"])
@requiere_admin
def admin_meta_asignar(cliente):
    if not _mismo_origen():
        abort(403)
    _cliente_o_404(cliente)
    ad_account_id = (request.form.get("ad_account_id") or "").strip()
    page_id = (request.form.get("page_id") or "").strip() or None
    if not ad_account_id:
        flash("Elige una cuenta publicitaria para asignar.", "error")
        return _volver_admin_meta()
    try:
        detalle = meta_agencia.asignar(cliente, ad_account_id, page_id, asignado_por=session.get("usuario"))
    except meta_conexion.MetaConexionError as e:
        flash(f"No pude asignar {proyectos.nombre_visible(cliente)}: {cola.sin_token(str(e))}", "error")
        return _volver_admin_meta()
    cuenta = detalle.get("ad_account_nombre") or detalle.get("ad_account_id")
    pagina = detalle.get("page_nombre") or detalle.get("page_id") or "sin Página"
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"asignado por {session.get('usuario')}: {cuenta} · {pagina}")
    ig = f" · Instagram @{detalle['ig_username']}" if detalle.get("ig_username") else ""
    flash(f"{proyectos.nombre_visible(cliente)} ahora lo gestiona Creatv en Meta: {cuenta} · {pagina}{ig}.", "ok")
    if detalle.get("cambio_cuenta"):
        flash("La cuenta publicitaria cambió: los experimentos anteriores de ese proyecto dejan de refrescarse.", "warn")
    if page_id and not detalle.get("ig_username"):
        flash("Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincule en Facebook.", "warn")
    if not page_id:
        flash("Sin Página asignada solo se pueden pautar anuncios; la publicación orgánica queda apagada para ese proyecto.", "warn")
    return _volver_admin_meta()


@app.route("/admin/meta/desasignar/<cliente>", methods=["POST"])
@requiere_admin
def admin_meta_desasignar(cliente):
    if not _mismo_origen():
        abort(403)
    _cliente_o_404(cliente)
    if not meta_agencia.desasignar(cliente):
        flash(f"{proyectos.nombre_visible(cliente)} no estaba en modo agencia.", "warn")
        return _volver_admin_meta()
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"vuelve a modo propia (por {session.get('usuario')})")
    flash(f"{proyectos.nombre_visible(cliente)} volvió a modo propia: si tenía su propia conexión se restauró; "
          "si no, tendrá que registrar su app y conectar con Meta.", "ok")
    return _volver_admin_meta()


@app.route("/cliente/<cliente>/ads/publicar", methods=["POST"])
def publicar_ad(cliente):
    """Publicar un anuncio suelto ya no tiene UI: Campañas se fundió en
    Experimentos y publicar es lanzar un experimento (exp_lanzar). La ruta se
    conserva para formularios viejos, pero no toca el anuncio ni encola nada
    (la tarea del worker `meta_publicar` sigue existiendo en tareas/meta.py)."""
    flash("Campañas ya no existe: crea un experimento con esa pieza.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/actualizar", methods=["POST"])
def actualizar_resultados_ad(cliente, ad_id):
    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry or not entry.get("meta_ids", {}).get("ad_id"):
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    # El snapshot lo trae el worker (tareas/meta.py, meta_refrescar); la
    # tarjeta se recarga sola por el polling.
    # max_intentos=1: si Meta falla, la persona tiene que ver el error ya, no
    # después de 30 min de reintentos con espera exponencial.
    arranco = trabajos.encolar(
        f"{cliente}__{ad_id}__metricas", "meta_refrescar", {"cliente": cliente, "ad_id": ad_id},
        cliente=cliente, duracion_estimada=10, max_intentos=1,
    )
    if arranco:
        flash("Actualizando resultados…", "ok")
    else:
        flash("Ya se están actualizando.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/estado", methods=["POST"])
def cambiar_estado_ad(cliente, ad_id):
    """Pausar/activar la campaña real en Meta — la única acción de este
    módulo que puede hacer que empiece a gastarse presupuesto de verdad."""
    nuevo_estado = request.form.get("estado", "").strip()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        flash("Estado inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    campaign_id = (entry or {}).get("meta_ids", {}).get("campaign_id")
    if not campaign_id:
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))

    # Serializado: meta_auth.configurar() escribe credenciales globales del
    # proceso (meta_ads/auth._CREDENCIALES); el lock cubre configurar ->
    # llamadas a Meta -> limpiar() para que dos proyectos nunca se mezclen.
    with _ENV_LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            # Activar/pausar los tres niveles: Meta solo entrega si campaña,
            # conjunto Y anuncio están ACTIVE (se crean todos en pausa).
            ids = entry.get("meta_ids") or {}
            for oid in (campaign_id, ids.get("adset_id"), ids.get("ad_id")):
                if oid:
                    meta_campaign.actualizar_estado(oid, nuevo_estado)
            ads_mod.actualizar(cliente, ad_id, estado="activo" if nuevo_estado == "ACTIVE" else "pausado")
            flash("Listo." if nuevo_estado == "ACTIVE" else "Pausado.", "ok")
        except Exception as e:
            flash(f"No pude cambiar el estado: {e}", "error")
        finally:
            meta_auth.limpiar()
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/reintentar", methods=["POST"])
def reintentar_ad(cliente, ad_id):
    """Un anuncio que falló al publicar vuelve a "Listos para publicar" con su
    formulario, sin tener que quitarlo y agregarlo de nuevo."""
    entry = ads_mod.cargar(cliente).get(ad_id)
    if not entry or entry.get("estado") != "error":
        flash("Ese anuncio no está en error.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    ads_mod.actualizar(cliente, ad_id, estado="en_cola", error=None)
    flash("Listo para volver a publicar.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/eliminar", methods=["POST"])
def eliminar_ad(cliente, ad_id):
    """Solo borra la fila local — NO borra la campaña en Meta si ya se
    publicó (eso se hace desde Meta Ads Manager, a propósito: esta app nunca
    borra algo que ya está corriendo en la plataforma de otro)."""
    ads_mod.eliminar(cliente, ad_id)
    flash("Eliminado de la lista.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


# ---------- Tablero (Bloque 6) ----------

MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
            "noviembre", "diciembre")
# Geometría del gráfico de 30 días (viewBox fija; el SVG escala al ancho).
_TB_ANCHO, _TB_ALTO = 720, 220
_TB_MARGEN = {"izq": 60, "der": 12, "arriba": 12, "abajo": 26}


def _nice_max(valor):
    """Máximo «bonito» para el eje: el primer 1/2/2,5/5/10 × 10^n que cubre
    el valor, para que las 4 marcas queden en números redondos."""
    if valor <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(valor))
    for f in (1, 2, 2.5, 5, 10):
        if f * exp >= valor:
            return float(f * exp)
    return float(10 * exp)


def _compacto(valor):
    """Etiqueta corta para el eje: 1,2 M / 250 k / 12."""
    v = float(valor or 0)
    if v >= 1_000_000:
        t = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".") + " M"
    elif v >= 1_000:
        t = f"{v / 1_000:.1f}".rstrip("0").rstrip(".") + " k"
    elif v == int(v):
        t = str(int(v))
    else:
        t = f"{v:.2f}".rstrip("0").rstrip(".")   # 0,5 y 0,25, no 0,50
    return t.replace(".", ",")


def _grafico_tablero(serie):
    """Coordenadas listas para pintar la serie de 30 días como SVG inline:
    barras de gasto y línea de ingresos sobre UN solo eje (las dos son dinero
    en `serie.moneda`, así que comparten escala), 4 marcas + máximo redondeado,
    etiqueta de fecha cada 5 días y un `titulo` por día para el tooltip nativo.
    None si no hay días o todo es cero (la plantilla muestra el estado vacío
    en vez de un gráfico en blanco)."""
    dias = (serie or {}).get("dias") or []
    moneda = (serie or {}).get("moneda") or tablero.MONEDA_POR_DEFECTO
    if not dias:
        return None
    tope = max(max(float(d["gasto"] or 0), float(d["ingresos"] or 0)) for d in dias)
    if tope <= 0:
        return None
    maximo = _nice_max(tope)
    m = _TB_MARGEN
    ancho_plot = _TB_ANCHO - m["izq"] - m["der"]
    alto_plot = _TB_ALTO - m["arriba"] - m["abajo"]
    base_y = m["arriba"] + alto_plot
    paso = ancho_plot / len(dias)
    ancho_barra = max(2.0, paso - 2)   # 2px de aire entre barras

    def y_de(v):
        return round(base_y - (float(v or 0) / maximo) * alto_plot, 2)

    salida = []
    for i, d in enumerate(dias):
        dd, mm = d["dia"][8:10], d["dia"][5:7]
        x = m["izq"] + i * paso
        gasto, ingresos = float(d["gasto"] or 0), float(d["ingresos"] or 0)
        salida.append({
            "dia": d["dia"], "gasto": gasto, "ingresos": ingresos, "compras": int(d.get("compras") or 0),
            "x": round(x, 2), "x_centro": round(x + paso / 2, 2), "ancho": round(ancho_barra, 2),
            "gasto_y": y_de(gasto), "ingresos_y": y_de(ingresos),
            "etiqueta": f"{dd}/{mm}" if i % 5 == 0 else "",
            "titulo": f"{dd}/{mm} · gasto {tablero.dinero(gasto, moneda)} · ingresos {tablero.dinero(ingresos, moneda)}",
        })
    marcas = [{"valor": maximo * k / 4, "y": y_de(maximo * k / 4), "texto": _compacto(maximo * k / 4)} for k in range(5)]
    puntos = " ".join(f"{d['x_centro']},{d['ingresos_y']}" for d in salida)
    return {"ancho": _TB_ANCHO, "alto": _TB_ALTO, "margen": m, "base_y": base_y, "maximo": maximo, "moneda": moneda,
            "marcas": marcas, "dias": salida, "puntos_linea": puntos}


@app.template_filter("dinero")
def _filtro_dinero(valor, moneda):
    """«1.250.000 COP» / «12,50 USD» (la misma regla que las alertas)."""
    return tablero.dinero(valor, moneda)


@app.template_filter("roas")
def _filtro_roas(valor):
    """ROAS con un decimal y coma: 28,0."""
    return f"{float(valor or 0):.1f}".replace(".", ",")


def _calcular_tablero(cliente):
    """Todo lo que pinta la pestaña Tablero, de UNA carga de la base
    (`tablero.cargar_datos`). Cada parte (resumen del mes, serie de 30 días,
    top de ganadoras, alertas, CSV, gráfico) va en su propio try/except: si
    una explota (Meta caída, tienda rota) llega como None con el nombre y la
    clase del error en `errores` — nunca el mensaje, que podría arrastrar un
    token — y la plantilla muestra «No se pudo calcular X» para esa parte y
    pinta el resto. Si la carga misma falla, cada parte carga por su cuenta
    (más lento, mismo resultado)."""
    ahora = db.ahora()
    out = {"ahora": ahora, "mes": MESES_ES[int(ahora[5:7]) - 1], "anio": ahora[:4], "errores": []}
    try:
        datos = tablero.cargar_datos(cliente, ahora)
    except Exception as e:  # noqa: BLE001 — sin carga compartida cada parte se las arregla sola
        datos = None
        print(f"[aviso] Tablero de {cliente}: no pude cargar los datos de una vez: {type(e).__name__}")
    partes = {
        "resumen": lambda: tablero.resumen_mes(cliente, ahora, datos=datos),
        "serie": lambda: tablero.serie_diaria(cliente, tablero.DIAS_SERIE, ahora, datos=datos),
        "top": lambda: tablero.top_ganadoras(cliente, datos=datos),
        "alertas": lambda: tablero.alertas(cliente, ahora, datos=datos),
        "csv": lambda: tablero.csv_mes(cliente, ahora, datos=datos),
    }
    for nombre, fn in partes.items():
        try:
            out[nombre] = fn()
        except Exception as e:  # noqa: BLE001 — una parte rota no tumba la página del proyecto
            out[nombre] = None
            out["errores"].append(f"{nombre}: {type(e).__name__}")
            print(f"[aviso] Tablero de {cliente}: no pude calcular {nombre}: {type(e).__name__}")
    try:
        out["grafico"] = _grafico_tablero(out["serie"]) if out["serie"] else None
    except Exception as e:  # noqa: BLE001 — el gráfico es una parte más: si falla, se muestra el resto
        out["grafico"] = None
        out["errores"].append(f"grafico: {type(e).__name__}")
        print(f"[aviso] Tablero de {cliente}: no pude dibujar el gráfico: {type(e).__name__}")
    return out


# Caché en proceso del tablero: ver_cliente lo calcula en cada pestaña y en
# cada redirect tras un POST, así que se guarda 60 s por proyecto. La clave
# lleva además el estado que cambia lo que se ve (último snapshot, propuestas
# pendientes, experimentos) para que un refresco del worker o una acción del
# dueño lo invaliden al instante sin esperar el TTL. Con gunicorn multi-worker
# es por proceso: aceptable.
TABLERO_TTL_S = 60
_TABLERO_CACHE = {}          # cliente -> (monotonic, clave, contexto)
_TABLERO_LOCK = threading.Lock()


def _clave_tablero(cliente):
    """(último id de metrica_snapshot, propuestas pendientes, nº de
    experimentos y su último actualizado_en, último actualizado_en de pieza,
    nº y último actualizado_en de publicación orgánica) del proyecto: cinco
    consultas baratas con índice. Cualquier cambio que
    el tablero pinte (snapshot del worker, propuesta del motor, estado o
    veredicto tocado por el dueño, publicación orgánica) mueve la clave."""
    ms, ep, pr, ex, pub = db.metrica_snapshot, db.experimento_pieza, db.propuesta, db.experimento, db.publicacion
    with db.conectar() as con:
        ultimo_snap = con.execute(sa.select(sa.func.max(ms.c.id)).select_from(
            ms.join(ep, ep.c.id == ms.c.experimento_pieza_id)).where(ep.c.cliente == cliente)).scalar()
        propuestas_n = con.execute(sa.select(sa.func.count()).select_from(pr).where(
            pr.c.cliente == cliente, pr.c.estado == "pendiente")).scalar()
        exps = con.execute(sa.select(sa.func.count(), sa.func.max(ex.c.actualizado_en)).select_from(ex).where(
            ex.c.cliente == cliente, ex.c.legado.is_(False))).first()
        piezas = con.execute(sa.select(sa.func.max(ep.c.actualizado_en)).where(ep.c.cliente == cliente)).scalar()
        # Bloque 7: una publicación orgánica nueva o que cambió de estado
        # mueve el tile «Ganadoras publicadas» y la alerta de ganadora sin publicar.
        publicaciones = con.execute(sa.select(sa.func.count(), sa.func.max(pub.c.actualizado_en)).where(pub.c.cliente == cliente)).first()
    return (ultimo_snap, propuestas_n, exps[0], exps[1], piezas, publicaciones[0], publicaciones[1])


def invalidar_tablero(cliente=None):
    """Olvida el tablero cacheado de un proyecto (o de todos)."""
    with _TABLERO_LOCK:
        if cliente is None:
            _TABLERO_CACHE.clear()
        else:
            _TABLERO_CACHE.pop(cliente, None)


def _contexto_tablero(cliente):
    """`_calcular_tablero` con caché de `TABLERO_TTL_S` por proyecto,
    invalidada antes si cambia `_clave_tablero`. Si la clave no se puede
    consultar, se calcula sin caché."""
    try:
        clave = _clave_tablero(cliente)
    except Exception as e:  # noqa: BLE001 — sin clave no hay caché, pero sí tablero
        print(f"[aviso] Tablero de {cliente}: no pude leer la clave de caché: {type(e).__name__}")
        return _calcular_tablero(cliente)
    ahora = time.monotonic()
    with _TABLERO_LOCK:
        entrada = _TABLERO_CACHE.get(cliente)
        if entrada and entrada[1] == clave and ahora - entrada[0] < TABLERO_TTL_S:
            return entrada[2]
    ctx = _calcular_tablero(cliente)
    with _TABLERO_LOCK:
        _TABLERO_CACHE[cliente] = (ahora, clave, ctx)
    return ctx


@app.route("/cliente/<cliente>/tablero/mes.csv")
def tab_descargar_csv(cliente):
    """CSV del mes en curso (una fila por pieza, `;`, BOM) para abrir en
    Excel. Sale del mismo contexto cacheado que la pestaña; si esa parte
    falló, se vuelve a intentar sola para que el error llegue al navegador."""
    ctx = _contexto_tablero(cliente)
    ahora = ctx["ahora"]
    texto = ctx.get("csv")
    if texto is None:
        texto = tablero.csv_mes(cliente, ahora)
    resp = Response(texto, content_type="text/csv; charset=utf-8")
    nombre = secure_filename(f"tablero_{cliente}_{ahora[:7]}.csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


# ---------- Gasto real (Task 3): precio antes y después ----------

# Rótulos en español de cada `tipo` de la tabla `gasto` (gastos.TIPOS).
NOMBRES_TIPO_GASTO = {
    "video": "Videos", "imagen": "Imágenes", "swap": "Cambios de producto", "guion": "Guiones",
    "final": "Finales", "regla_producto": "Reglas de producto (IA)", "caption_organico": "Textos orgánicos (IA)",
    "musica": "Música", "otro": "Otros",
}


@app.template_filter("usd")
def _filtro_usd(valor):
    """«US$ 0,07» (gastos.formatear): coma decimal, dos decimales, «—» si no hay."""
    return gastos.formatear(valor)


def _pauta_mes(tablero_ctx):
    """[{"moneda", "gasto"}] con la pauta del mes por moneda (solo > 0), del
    resumen ya calculado por el tablero. Sin resumen (parte rota) → []."""
    resumen = (tablero_ctx or {}).get("resumen") or {}
    salida = []
    for moneda, g in sorted((resumen.get("por_moneda") or {}).items()):
        gasto = float((g or {}).get("gasto") or 0)
        if gasto > 0:
            salida.append({"moneda": moneda, "gasto": gasto})
    return salida


def _precios_pagina():
    """Estimados fijos para los botones de la página (guion, final por país,
    regla de producto, texto orgánico). Video/imagen los calcula Crear con
    las tarifas del modelo elegido (data-usd-* en el formulario)."""
    return {
        "guion": gastos.estimar("guion"),
        "final_por_pais": gastos.estimar("final", paises=1),
        "regla_producto": gastos.estimar("regla_producto"),
        "caption_organico": gastos.estimar("caption_organico"),
    }


def _chip_gasto(gasto_mes, pauta_mes):
    """Texto del chip del sidebar: «US$ 12,40 generación · 1.405.157 COP
    pauta» (la pauta solo si hay; la generación siempre, aunque sea 0)."""
    partes = [f"{gastos.formatear((gasto_mes or {}).get('total') or 0)} generación"]
    for p in pauta_mes or []:
        partes.append(f"{tablero.dinero(p['gasto'], p['moneda'])} pauta")
    return " · ".join(partes)


def _contexto_gasto(cliente, tablero_ctx):
    """gasto_mes (gastos.resumen_mes), pauta_mes (por moneda, del tablero),
    precios (estimados de los botones), gastos_historial (200 últimos),
    gastos_por_tipo (tabla) y gasto_chip (sidebar). Cada parte en su
    try/except: el gasto informa, nunca tumba la página."""
    try:
        gasto_mes = gastos.resumen_mes(cliente)
    except Exception as e:  # noqa: BLE001 — informativo
        print(f"[aviso] Gasto de {cliente}: no pude leer el resumen del mes: {type(e).__name__}")
        gasto_mes = {"desde": None, "hasta": None, "total": 0.0, "por_tipo": {}, "n": 0, "error": True}
    try:
        historial = gastos.historial(cliente, limite=200)
    except Exception as e:  # noqa: BLE001 — informativo
        print(f"[aviso] Gasto de {cliente}: no pude leer el historial: {type(e).__name__}")
        historial = []
    pauta = _pauta_mes(tablero_ctx)
    por_tipo = [{"tipo": t, "nombre": NOMBRES_TIPO_GASTO.get(t, t), "n": v["n"], "usd": v["usd"]}
                for t, v in sorted(gasto_mes["por_tipo"].items(), key=lambda kv: -kv[1]["usd"])]
    return {
        "gasto_mes": gasto_mes,
        "pauta_mes": pauta,
        "precios": _precios_pagina(),
        "gastos_historial": historial,
        "gastos_por_tipo": por_tipo,
        "nombres_tipo_gasto": NOMBRES_TIPO_GASTO,
        "gasto_chip": _chip_gasto(gasto_mes, pauta),
    }


@app.context_processor
def _chip_gasto_sidebar():
    """El sidebar (base.html) se pinta en toda página con <cliente> en la URL
    — también las de Sprints, que no pasan por ver_cliente. Acá se calcula
    el chip para esas; ver_cliente ya lo trae en su contexto (y lo explícito
    gana sobre el context processor), así que no se repite el trabajo.
    M1: los parciales JSON (`_respuesta_bandeja` y similares, sin sidebar)
    no lo necesitan — salir temprano evita recalcular el tablero entero
    (1 + 5 consultas) solo para un chip que nadie va a ver."""
    cliente = request.view_args.get("cliente") if request.view_args else None
    if not cliente or request.endpoint == "ver_cliente" or _quiere_json():
        return {}
    try:
        return {"gasto_chip": _chip_gasto(gastos.resumen_mes(cliente), _pauta_mes(_contexto_tablero(cliente)))}
    except Exception as e:  # noqa: BLE001 — sin chip, pero con página
        print(f"[aviso] Gasto de {cliente}: no pude calcular el chip del sidebar: {type(e).__name__}")
        return {}


@app.route("/cliente/<cliente>/gasto/mes.csv")
def gasto_csv(cliente):
    """CSV del gasto de generación del mes en curso (una fila por cobro,
    `;`, BOM) para abrir en Excel. Mismos headers que tab_descargar_csv."""
    ahora = db.ahora()
    texto = gastos.csv_mes(cliente, ahora)
    resp = Response(texto, content_type="text/csv; charset=utf-8")
    nombre = secure_filename(f"gasto_{cliente}_{ahora[:7]}.csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp


@app.route("/cliente/<cliente>/experimentos/nuevo", methods=["POST"])
def exp_crear(cliente):
    """Crea un experimento en 'armando' — sin piezas ni objetos en Meta
    todavía. Nunca gasta: eso solo ocurre en exp_lanzar y solo si la persona
    lo pide."""
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if meta_conexion.estado(cliente).get("estado") != "conectado":
        flash("Conecta Meta en Configuración antes de crear un experimento.", "error")
        return volver
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    nombre = (request.form.get("nombre") or "").strip()[:200]
    objetivo = request.form.get("objetivo") or ""
    codigos = [p for p in request.form.getlist("paises") if p in fe_tipos.PAISES]
    destino = (request.form.get("destino_url") or "").strip()
    try:
        dias = int(request.form.get("dias") or 7)
        tope = float(request.form.get("tope_total") or 0)
        edad_min = int(request.form.get("edad_min") or 18)
        edad_max = int(request.form.get("edad_max") or 65)
        paises = [{"pais": p, "idioma": fe_tipos.PAISES[p]["idioma"],
                   "presupuesto_dia": float(request.form.get(f"presupuesto_{p}") or 0)} for p in codigos]
    except ValueError:
        flash("Revisa los números del formulario.", "error")
        return volver
    # float("nan")/float("inf") no disparan ValueError arriba, y nan<=0 y
    # nan<minimo son ambos False — sin este chequeo un tope o presupuesto
    # NaN/inf crea el experimento y falla después en lanzador.centavos
    # (int(nan) -> ValueError), gastando el único intento del job.
    if not math.isfinite(tope) or any(not math.isfinite(p["presupuesto_dia"]) for p in paises):
        flash("Revisa los números del formulario.", "error")
        return volver
    if (not nombre or objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos
            or not destino.startswith(("http://", "https://")) or not (1 <= dias <= 90) or tope <= 0
            or not (13 <= edad_min <= edad_max <= 65)):
        flash("Faltan datos: nombre, objetivo, al menos un país, días (1–90), tope, edades (13–65) "
              "y una URL de destino http(s).", "error")
        return volver
    # Meta interpreta daily_budget en la moneda de FACTURACIÓN de la cuenta
    # publicitaria, sin importar qué país apunte ese adset (una cuenta en COP
    # que le pega a México sigue fijando el presupuesto de ese adset en COP).
    # Por eso el mínimo se valida contra la moneda de la cuenta, no la del país.
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(f"El presupuesto diario no alcanza el mínimo de Meta ({minimo} {moneda}) en: {', '.join(bajos)}.", "error")
        return volver
    modo = request.form.get("modo") or "manual"
    if modo not in modos.MODOS:
        modo = "manual"   # nunca se sube de puerta por un valor raro en el form
    # Atribución opcional en el form; sin ella, experimentos.crear usa la
    # sugerida (Pixel vivo → pixel, tienda conectada → tienda, si no ninguna).
    atribucion = request.form.get("atribucion") or None
    if atribucion is not None and atribucion not in experimentos.ATRIBUCIONES:
        flash("La atribución tiene que ser pixel, tienda o ninguna.", "error")
        return volver
    # Bloque 6: optimizar por compras exige que Meta vea las compras, o sea
    # el Pixel disparando y atribución pixel. El objetivo no se puede cambiar
    # después de lanzar (Meta no lo permite), así que se corta acá y no en
    # el lanzador, donde ya sería un experimento armado que no puede salir.
    if objetivo == "OUTCOME_SALES" and (atribucion or experimentos.atribucion_sugerida(cliente)) != "pixel":
        flash("Optimizar por compras requiere el Pixel activo y atribución pixel: pulsa «Comprobar Pixel» en "
              "Configuración, o elige el objetivo de tráfico.", "error")
        return volver
    eid = experimentos.crear(cliente, nombre, paises, objetivo, dias, tope, destino, moneda, edad_min, edad_max,
                             modo=modo, atribucion=atribucion)
    ex = experimentos.obtener(cliente, eid)
    experimentos.registrar_evento(
        cliente, eid, "creado",
        f"Experimento creado con {len(paises)} países (modo {modo}, atribución {ex['atribucion']})")
    flash(f"Experimento «{nombre}» creado. Agrega piezas y lánzalo cuando esté listo.", "ok")
    return volver


_MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def nombre_experimento_automatico(n_piezas, paises, cuando=None):
    """«Prueba 20 sep · 3 piezas · CO, MX» — el nombre que la galería propone."""
    cuando = cuando or datetime.now().date()
    piezas = "1 pieza" if n_piezas == 1 else f"{n_piezas} piezas"
    return f"Prueba {cuando.day} {_MESES_CORTOS[cuando.month - 1]} · {piezas} · {', '.join(sorted(paises))}"


@app.route("/cliente/<cliente>/experimentos/probar", methods=["POST"])
def exp_probar(cliente):
    """La galería primero: un solo POST crea el experimento, reparte las
    piezas por país y encola el lanzamiento (todo PAUSED en Meta). Valida lo
    mismo que exp_crear; si algo falla no queda nada creado. Activar sigue
    siendo un clic aparte."""
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if meta_conexion.estado(cliente).get("estado") != "conectado":
        flash("Conecta Meta en Configuración antes de probar piezas.", "error")
        return volver
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    objetivo = request.form.get("objetivo") or ""
    codigos = [p for p in request.form.getlist("paises") if p in fe_tipos.PAISES]
    destino = (request.form.get("destino_url") or "").strip()
    try:
        piezas_ids = [int(x) for x in request.form.getlist("piezas")]
        combinaciones = []
        for c in request.form.getlist("combinaciones"):
            pid, _, pais = c.partition(":")
            combinaciones.append((int(pid), pais))
        dias = int(request.form.get("dias") or 7)
        tope = float(request.form.get("tope_total") or 0)
        edad_min = int(request.form.get("edad_min") or 18)
        edad_max = int(request.form.get("edad_max") or 65)
        paises = [{"pais": p, "idioma": fe_tipos.PAISES[p]["idioma"],
                   "presupuesto_dia": float(request.form.get(f"presupuesto_{p}") or 0)} for p in codigos]
    except ValueError:
        flash("Revisa los números del formulario.", "error")
        return volver
    if not math.isfinite(tope) or any(not math.isfinite(p["presupuesto_dia"]) for p in paises):
        flash("Revisa los números del formulario.", "error")
        return volver
    if not piezas_ids:
        flash("Marca al menos una pieza en la galería.", "error")
        return volver
    if not codigos:
        # Antes de filtrar las combinaciones por país: sin país quedarían
        # vacías y el aviso hablaría de la cuadrícula, no del país.
        flash("Marca al menos un país.", "error")
        return volver
    combinaciones = [(pid, pais) for pid, pais in combinaciones if pid in piezas_ids and pais in codigos]
    if not combinaciones:
        flash("Marca al menos una combinación pieza × país en el paso de revisar.", "error")
        return volver
    if (objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos
            or not destino.startswith(("http://", "https://")) or not (1 <= dias <= 90) or tope <= 0
            or not (13 <= edad_min <= edad_max <= 65)):
        flash("Faltan datos: objetivo, al menos un país, días (1–90), tope, edades (13–65) y una URL de destino http(s).", "error")
        return volver
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(f"El presupuesto diario no alcanza el mínimo de Meta ({minimo} {moneda}) en: {', '.join(bajos)}.", "error")
        return volver
    modo = request.form.get("modo") or "manual"
    if modo not in modos.MODOS:
        modo = "manual"
    atribucion = request.form.get("atribucion") or None
    if atribucion is not None and atribucion not in experimentos.ATRIBUCIONES:
        flash("La atribución tiene que ser pixel, tienda o ninguna.", "error")
        return volver
    if objetivo == "OUTCOME_SALES" and (atribucion or experimentos.atribucion_sugerida(cliente)) != "pixel":
        flash("Optimizar por compras requiere el Pixel activo y atribución pixel: pulsa «Comprobar Pixel» en "
              "Configuración, o elige el objetivo de tráfico.", "error")
        return volver
    n_piezas = len({pid for pid, _ in combinaciones})
    nombre = (request.form.get("nombre") or "").strip()[:200] or nombre_experimento_automatico(n_piezas, codigos)
    datos = dict(nombre=nombre, paises=paises, objetivo_meta=objetivo, dias=dias, tope_total=tope, destino_url=destino,
                 moneda=moneda, edad_min=edad_min, edad_max=edad_max, modo=modo, atribucion=atribucion)
    try:
        eid = experimentos.crear_con_piezas(cliente, datos, combinaciones)
    except experimentos.ErrorCombinacion as e:
        flash(str(e), "error")
        return volver
    job_id = tareas_exp.job_id_lanzar(cliente, eid)
    arranco = trabajos.encolar(job_id, "exp_lanzar", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=120, etapas=lanzador.ETAPAS_LANZAR, max_intentos=1)
    if arranco:
        experimentos.actualizar(cliente, eid, estado="lanzando", error=None)
        flash(f"«{nombre}»: lanzando a Meta en pausa. Cuando termine, actívalo desde su tarjeta.", "ok")
    else:
        flash(f"«{nombre}» quedó creado; ya se estaba lanzando.", "warn")
    return volver


def _agregar_pieza_validada(cliente, experimento_id, pieza_id, pais):
    """Valida y agrega una pieza (final o clon) a un experimento en armado.
    Devuelve un mensaje de error en español, o None si quedó agregada.
    Compartida por exp_agregar_pieza y exp_meter_pieza (Crear -> Experimentos)."""
    ex = experimentos.obtener(cliente, experimento_id)
    if not ex:
        return "Ese experimento no existe."
    if ex["estado"] not in ("armando", "error") or ex["meta_campaign_id"]:
        return "Ese experimento ya no acepta piezas nuevas."
    candidata = next((p for p in experimentos.elegibles(cliente) if p["pieza_id"] == pieza_id), None)
    if not candidata:
        return "Esa pieza no está disponible (o no está lista)."
    pais, error = experimentos.validar_combinacion(candidata, {p["pais"] for p in ex["paises"]}, pais)
    if error:
        return error
    experimentos.agregar_pieza(cliente, experimento_id, pieza_id, pais)
    return None


@app.route("/cliente/<cliente>/experimentos/<int:eid>/piezas", methods=["POST"])
def exp_agregar_pieza(cliente, eid):
    try:
        pieza_id = int(request.form.get("pieza_id") or request.form.get("legado_id") or 0)
    except ValueError:
        pieza_id = 0
    if not pieza_id:
        legado_id = (request.form.get("legado_id") or "").strip()
        pieza_id = creative_flow.pieza_id_por_legado(cliente, legado_id) if legado_id else None
    pais = (request.form.get("pais") or "").strip() or None
    if not pieza_id:
        flash("No encontré esa pieza.", "error")
    else:
        error = _agregar_pieza_validada(cliente, eid, pieza_id, pais)
        flash(error, "error") if error else flash("Pieza agregada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/piezas/<int:ep_id>/quitar", methods=["POST"])
def exp_quitar_pieza(cliente, eid, ep_id):
    # Misma guardia que _agregar_pieza_validada: mientras el experimento está
    # "lanzando", las piezas que el worker todavía no procesó siguen en
    # "en_cola" (que es lo único que exige experimentos.quitar_pieza), así que
    # sin esto se podían borrar piezas que lanzador.lanzar ya cargó en memoria
    # y está a punto de publicar en Meta — el anuncio queda huérfano allá.
    ex = experimentos.obtener(cliente, eid)
    if not ex or ex["estado"] not in ("armando", "error") or ex["meta_campaign_id"]:
        flash("Ese experimento ya no acepta cambios de piezas.", "error")
    elif experimentos.quitar_pieza(cliente, eid, ep_id):
        flash("Pieza quitada.", "ok")
    else:
        flash("No pude quitar esa pieza (¿ya está en Meta?).", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/meter", methods=["POST"])
def exp_meter_pieza(cliente):
    """Desde la pestaña Crear: manda una pieza recién generada directo a un
    experimento existente, sin tener que ir a la pestaña Experimentos. Los
    anuncios sueltos en cola (Experimentos › Anuncios sueltos) usan el mismo
    formulario con volver=experimentos para quedarse en esa pestaña."""
    legado_id = (request.form.get("legado_id") or "").strip()
    volver = "experimentos" if request.form.get("volver") == "experimentos" else "creativeflowplus"
    try:
        experimento_id = int(request.form.get("experimento_id") or 0)
    except ValueError:
        experimento_id = 0
    pais = (request.form.get("pais") or "").strip() or None
    pieza_id = creative_flow.pieza_id_por_legado(cliente, legado_id) if legado_id else None
    if not pieza_id or not experimento_id:
        flash("No encontré esa pieza o ese experimento.", "error")
    else:
        error = _agregar_pieza_validada(cliente, experimento_id, pieza_id, pais)
        flash(error, "error") if error else flash("Pieza enviada al experimento.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/lanzar", methods=["POST"])
def exp_lanzar(cliente, eid):
    """Encola el lanzamiento a Meta (campaña + conjuntos por país + anuncios,
    todo PAUSED). Valida acá lo mismo que lanzador.lanzar para poder avisar
    por flash sin gastar un intento de la cola (max_intentos=1: un reintento
    automático a mitad de la cadena crearía objetos huérfanos en Meta)."""
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash("Ese experimento no existe.", "error")
        return volver
    if ex["estado"] not in ("armando", "error"):
        flash("Ese experimento ya fue lanzado.", "error")
        return volver
    if not ex["piezas"]:
        flash("El experimento no tiene piezas: agrega al menos una antes de lanzar.", "error")
        return volver
    paises_con_piezas = {p["pais"] for p in ex["piezas"]}
    faltan = [p["pais"] for p in ex["paises"] if p["pais"] not in paises_con_piezas]
    if faltan:
        flash(f"Sin piezas para: {', '.join(faltan)}. Agrega una pieza por país o quita el país.", "error")
        return volver
    job_id = tareas_exp.job_id_lanzar(cliente, eid)
    # M2: encolar primero y solo marcar "lanzando" si de verdad arrancó — si
    # se pusiera "lanzando" antes y trabajos.encolar fallara (ej. "database is
    # locked"), el experimento quedaría colgado ahí sin tarea que lo saque
    # (_reconciliar_huerfanos no corre bajo gunicorn).
    arranco = trabajos.encolar(job_id, "exp_lanzar", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=120, etapas=lanzador.ETAPAS_LANZAR, max_intentos=1)
    if arranco:
        experimentos.actualizar(cliente, eid, estado="lanzando", error=None)
        flash("Lanzando el experimento a Meta (queda en pausa)…", "ok")
    else:
        flash("Ya se está lanzando ese experimento.", "warn")
    return volver


@app.route("/cliente/<cliente>/experimentos/<int:eid>/estado", methods=["POST"])
def exp_estado(cliente, eid):
    estado = (request.form.get("estado") or "").strip()
    pais = (request.form.get("pais") or "").strip() or None
    if estado not in ("ACTIVE", "PAUSED"):
        flash("Estado inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    with _ENV_LOCK:
        try:
            lanzador.cambiar_estado(cliente, eid, estado, pais=pais)
            flash("Listo." if estado == "ACTIVE" else "Pausado.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"No pude cambiar el estado: {cola.sin_token(str(e))}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/presupuesto", methods=["POST"])
def exp_presupuesto(cliente, eid):
    pais = (request.form.get("pais") or "").strip()
    # Igual que en exp_crear: el presupuesto se valida en la moneda de la
    # cuenta publicitaria de Meta, no en la moneda local de la audiencia. Y
    # es la misma moneda con la que lanzador.cambiar_presupuesto_pais convierte
    # a centavos (ex["moneda"], guardada al crear el experimento con la moneda
    # de la cuenta de ese momento) — si esa cuenta cambió de moneda entre crear
    # y ajustar, cambiar_presupuesto_pais ya cae al fallback ex["moneda"] or
    # "USD", así que valida y convierte con el mismo número salvo ese caso raro.
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    try:
        presupuesto_dia = float(request.form.get("presupuesto_dia") or 0)
    except ValueError:
        flash("El presupuesto debe ser un número.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if not math.isfinite(presupuesto_dia) or presupuesto_dia < minimo:
        flash(f"El presupuesto diario mínimo es {minimo} {moneda}.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    with _ENV_LOCK:
        try:
            lanzador.cambiar_presupuesto_pais(cliente, eid, pais, presupuesto_dia)
            flash("Presupuesto actualizado.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"No pude cambiar el presupuesto: {cola.sin_token(str(e))}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/refrescar", methods=["POST"])
def exp_refrescar(cliente, eid):
    ex = experimentos.obtener(cliente, eid)
    if not ex or not ex["meta_campaign_id"]:
        flash("Ese experimento todavía no está en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    job_id = tareas_exp.job_id_refrescar(cliente, eid)
    # M10: max_intentos=2 como la periódica (tareas/experimentos.py) — refrescar
    # nunca gasta, así que no hay razón para ser más estricto acá que allá.
    arranco = trabajos.encolar(job_id, "exp_refrescar", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=30, max_intentos=2)
    if arranco:
        flash("Actualizando resultados…", "ok")
    else:
        flash("Ya se están actualizando.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/cerrar", methods=["POST"])
def exp_cerrar(cliente, eid):
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash("Ese experimento no existe.", "error")
        return volver
    if ex["estado"] == "cerrado":
        flash("Ese experimento ya estaba cerrado.", "ok")
        return volver
    # "lanzando" nunca se cierra desde acá: el worker está a mitad de crear
    # campaña/adsets/anuncios en Meta y, al terminar, vuelve a escribir
    # "pausado" (lanzador.lanzar) — un "cerrado" acá se perdería y dejaría
    # los objetos ya creados en Meta sin que el experimento se entere. Solo
    # se puede cerrar desde armando/error (nunca se lanzó) o pausado/corriendo
    # (ya está en Meta).
    if ex["estado"] not in ("pausado", "corriendo", "armando", "error"):
        flash("Espera a que termine el lanzamiento antes de cerrar.", "error")
        return volver
    with _ENV_LOCK:
        try:
            lanzador.cerrar(cliente, eid)
            flash("Experimento cerrado.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"No pude cerrar el experimento: {cola.sin_token(str(e))}", "error")
    return volver


# ---- Bloque 4: modo, reglas, propuestas, evaluar ahora ---------------------

def _volver_exp(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/modo", methods=["POST"])
def exp_modo(cliente, eid):
    """Cambia la puerta del experimento (manual/semi/auto). Solo cambia lo que
    el decisor hará DESPUÉS: no ejecuta ninguna propuesta ya pendiente."""
    modo = (request.form.get("modo") or "").strip()
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash("Ese experimento no existe.", "error")
        return _volver_exp(cliente)
    if modo not in modos.MODOS:
        flash("Modo inválido.", "error")
        return _volver_exp(cliente)
    if ex["estado"] == "cerrado":
        flash("Un experimento cerrado no cambia de modo.", "error")
        return _volver_exp(cliente)
    if modo != ex["modo"]:
        experimentos.actualizar(cliente, eid, modo=modo)
        experimentos.registrar_evento(cliente, eid, "modo", f"Modo cambiado de {ex['modo']} a {modo}.",
                                      {"antes": ex["modo"], "despues": modo})
    flash(f"Modo: {modo}.", "ok")
    return _volver_exp(cliente)


def _flash_reglas_invalidas(errores):
    nombres = ", ".join(errores)
    flash(f"Revisa estos valores, deben ser números: {nombres}. No se guardó nada.", "error")


@app.route("/cliente/<cliente>/experimentos/<int:eid>/reglas", methods=["POST"])
def exp_reglas(cliente, eid):
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash("Ese experimento no existe.", "error")
        return _volver_exp(cliente)
    reglas, errores = decisor.reglas_desde_formulario(request.form)
    if errores:
        _flash_reglas_invalidas(errores)
        return _volver_exp(cliente)
    experimentos.actualizar(cliente, eid, reglas=reglas)
    experimentos.registrar_evento(cliente, eid, "reglas", "Reglas del experimento actualizadas.", {"reglas": reglas})
    flash("Reglas guardadas. Lo vacío hereda de Configuración.", "ok")
    return _volver_exp(cliente)


@app.route("/cliente/<cliente>/experimentos/<int:eid>/decidir", methods=["POST"])
def exp_decidir_ahora(cliente, eid):
    """Encola una pasada del decisor. Evaluar no gasta por sí mismo: lo que
    gasta pasa por la puerta del modo (acciones.pedir) y en manual/semi queda
    como propuesta."""
    ex = experimentos.obtener(cliente, eid)
    if not ex or ex["estado"] != "corriendo":
        flash("Solo se evalúa un experimento que está corriendo.", "error")
        return _volver_exp(cliente)
    job_id = tareas_exp.job_id_decidir(cliente, eid)
    arranco = trabajos.encolar(job_id, "exp_decidir", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=60, max_intentos=1)
    flash("Evaluando…" if arranco else "Ya se está evaluando.", "ok" if arranco else "warn")
    return _volver_exp(cliente)


def _ep_id_evento(cliente, pr):
    """ep_id del payload solo si la pieza sigue existiendo (el evento tiene
    FK a experimento_pieza; una propuesta vieja no debe tumbar la ruta)."""
    ep_id = (pr.get("payload") or {}).get("ep_id")
    if ep_id is None:
        return None
    return ep_id if experimentos.experimento_de_pieza(cliente, ep_id) == pr["experimento_id"] else None


def _ejecutar_propuesta(cliente, pr):
    """Ejecuta una propuesta ya aprobada y la marca ejecutada. Si falla, la
    devuelve a pendiente y devuelve el mensaje de error (None si fue bien).
    Va bajo _ENV_LOCK porque acciones.ejecutar puede tocar Meta."""
    with _ENV_LOCK:
        try:
            mensaje = acciones.ejecutar(cliente, pr["experimento_id"], pr["accion"], pr["payload"])
        except ValueError as e:
            propuestas.reabrir(cliente, pr["id"])
            return str(e)
        except Exception as e:  # noqa: BLE001
            propuestas.reabrir(cliente, pr["id"])
            return f"No pude ejecutar «{pr['accion']}»: {cola.sin_token(str(e))}"
    propuestas.marcar_ejecutada(cliente, pr["id"])
    experimentos.registrar_evento(cliente, pr["experimento_id"], "accion",
                                  f"{mensaje} (propuesta #{pr['id']} aprobada a mano)",
                                  {"accion": pr["accion"], "payload": pr["payload"], "propuesta_id": pr["id"]},
                                  ep_id=_ep_id_evento(cliente, pr))
    flash(mensaje, "ok")
    return None


def _overrides_organico(cliente, form, payload):
    """Bloque 7: lo que la persona editó en la propuesta `publicar_organico`
    antes de aprobar (`caption_<p>`/`titulo_<p>` y las plataformas que dejó
    marcadas) pisa el `payload["captions"]`/`["plataformas"]` redactados por
    el motor. Solo cuando el form trae `org_form` (la propuesta se pintó con
    los textos); aprobar todo o un POST sin campos deja el payload tal cual.
    El texto editado pasa por `organico.normalizar_captions` (máximos, sin
    enlaces en IG/TikTok, hashtags): `maxlength` del textarea es solo cliente.
    Devuelve (payload, error): error si no quedó ninguna plataforma marcada —
    con lista vacía acciones publicaría en TODAS las disponibles."""
    if not form.get("org_form"):
        return payload, None
    payload = dict(payload)
    plataformas = [p for p in form.getlist("plataformas") if p in organico.PLATAFORMAS]
    if not plataformas:
        return payload, "Marca al menos una plataforma para publicar."
    captions = {p: dict(v) for p, v in (payload.get("captions") or {}).items() if isinstance(v, dict)}
    for p in plataformas:
        caption = (form.get(f"caption_{p}") or "").strip()
        if caption:
            captions.setdefault(p, {})["caption"] = caption
        if f"titulo_{p}" in form:
            captions.setdefault(p, {})["titulo"] = (form.get(f"titulo_{p}") or "").strip()
    captions = {p: captions[p] for p in plataformas if p in captions}
    pieza_id = _pieza_de_ep(cliente, payload.get("ep_id")) if payload.get("ep_id") else None
    if captions and pieza_id:
        try:
            captions = organico.normalizar_captions(cliente, pieza_id, captions)
        except ValueError as e:
            return payload, str(e)
    payload["plataformas"] = plataformas
    payload["captions"] = captions
    return payload, None


@app.route("/cliente/<cliente>/propuestas/<int:pid>/aprobar", methods=["POST"])
def prop_aprobar(cliente, pid):
    # propuestas.obtener/resolver filtran por cliente: una propuesta de otro
    # proyecto devuelve None y no se ejecuta nada.
    pr = propuestas.obtener(cliente, pid)
    if not pr or pr["estado"] != "pendiente":
        flash("Esa propuesta no existe o ya estaba resuelta.", "error")
        return _volver_exp(cliente)
    payload, error = (_overrides_organico(cliente, request.form, pr["payload"]) if pr["accion"] == "publicar_organico"
                      else (pr["payload"], None))
    if error:
        flash(error, "error")
        return _volver_exp(cliente)
    pr = propuestas.resolver(cliente, pid, "aprobada")
    if not pr:
        flash("Esa propuesta no existe o ya estaba resuelta.", "error")
        return _volver_exp(cliente)
    pr = dict(pr, payload=payload)
    error = _ejecutar_propuesta(cliente, pr)
    if error:
        flash(error, "error")
    return _volver_exp(cliente)


@app.route("/cliente/<cliente>/propuestas/<int:pid>/rechazar", methods=["POST"])
def prop_rechazar(cliente, pid):
    pr = propuestas.resolver(cliente, pid, "rechazada")
    if not pr:
        flash("Esa propuesta no existe o ya estaba resuelta.", "error")
        return _volver_exp(cliente)
    experimentos.registrar_evento(cliente, pr["experimento_id"], "propuesta",
                                  f"Propuesta #{pr['id']} ({pr['accion']}) rechazada a mano.",
                                  {"accion": pr["accion"], "payload": pr["payload"], "propuesta_id": pr["id"]},
                                  ep_id=_ep_id_evento(cliente, pr))
    flash("Propuesta rechazada.", "ok")
    return _volver_exp(cliente)


@app.route("/cliente/<cliente>/experimentos/<int:eid>/propuestas/aprobar_todas", methods=["POST"])
def prop_aprobar_todas(cliente, eid):
    """Aprueba y ejecuta en orden de creación; en el primer error se detiene:
    esa propuesta vuelve a pendiente y las que siguen se quedan pendientes
    (no se aprueban), para que la persona decida con el error a la vista."""
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash("Ese experimento no existe.", "error")
        return _volver_exp(cliente)
    pendientes = propuestas.pendientes(cliente, eid)
    if not pendientes:
        flash("No había propuestas pendientes.", "ok")
        return _volver_exp(cliente)
    hechas = 0
    for pr in pendientes:
        aprobada = propuestas.resolver(cliente, pr["id"], "aprobada")
        if not aprobada:
            continue   # alguien la resolvió entre medio
        error = _ejecutar_propuesta(cliente, aprobada)
        if error:
            flash(f"Me detuve en la propuesta #{pr['id']} ({pr['accion']}): {error}", "error")
            break
        hechas += 1
    if hechas:
        flash(f"{hechas} propuesta(s) ejecutada(s).", "ok")
    return _volver_exp(cliente)


# ---------- Bloque 7: publicación orgánica ----------
# Publicar es público e irreversible: ninguna de estas rutas publica sola —
# org_publicar/org_reintentar solo dejan filas `en_cola` y encolan la tarea
# organico_publicar (max_intentos=1) con el clic de la persona; org_redactar
# es de solo lectura (texto con Claude para que lo vea antes).

def _trabajos_organico(cliente, publicaciones_por_pieza):
    """{pieza_id: {"job_id"}} de las publicaciones orgánicas que el worker
    tiene pendientes o en curso — UNA consulta a la cola (cola.job_ids_vivos)
    y no una por pieza. Solo piezas con alguna fila `publicacion`: la tarea
    se encola siempre después de crearlas."""
    if not publicaciones_por_pieza:
        return {}
    vivos = cola.job_ids_vivos(cliente, "organico_publicar")
    out = {}
    for pieza_id in publicaciones_por_pieza:
        jid = tareas_org.job_id_publicar(cliente, pieza_id)
        if jid in vivos:
            out[pieza_id] = {"job_id": jid}
    return out


def _volver_org(cliente):
    """Vuelve a la pestaña de donde salió el clic (`volver` en el form):
    Crear (creativeflowplus) o Experimentos (por defecto)."""
    anchor = "creativeflowplus" if request.form.get("volver") == "creativeflowplus" else "experimentos"
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=anchor))


def _int_form(nombre):
    try:
        return int(request.form.get(nombre) or 0) or None
    except ValueError:
        return None


def _pieza_de_ep(cliente, ep_id):
    ep = db.experimento_pieza
    with db.conectar() as con:
        return con.execute(sa.select(ep.c.pieza_id).where(ep.c.id == ep_id, ep.c.cliente == cliente)).scalar()


def _nombres_org(plataformas):
    return ", ".join(organico.PLATAFORMAS.get(p, {}).get("nombre", p) for p in plataformas)


def _encolar_organico(cliente, pieza_id, pub_ids):
    """Encola organico_publicar para esas filas. Si la cola ya tenía un
    trabajo vivo de la pieza (carrera entre en_curso y encolar), las filas
    quedan en `error` con mensaje para reintentar desde el panel (mismo
    criterio que acciones._publicar_organico). Devuelve True si se encoló."""
    job_id = tareas_org.job_id_publicar(cliente, pieza_id)
    encolada = trabajos.encolar(job_id, "organico_publicar", {"cliente": cliente, "pub_ids": pub_ids},
                                cliente=cliente, duracion_estimada=tareas_org.DURACION_PUBLICAR,
                                etapas=tareas_org.ETAPAS_PUBLICAR, max_intentos=1)
    if not encolada:
        for pub_id in pub_ids:
            organico.actualizar(cliente, pub_id, estado="error",
                                error="Ya había una publicación de esta pieza en curso; reintenta cuando termine.")
    return encolada


@app.route("/cliente/<cliente>/organico/redactar", methods=["POST"])
def org_redactar(cliente):
    """JSON {plataforma: {titulo, caption, fallback}} para la pieza y las
    plataformas del form. Solo lectura: el texto vuelve al formulario para
    que la persona lo lea y edite antes de publicar. Sin Claude igual hay
    texto (organico.redactar usa el fallback y lo marca)."""
    pieza_id = _int_form("pieza_id")
    plataformas = [p for p in request.form.getlist("plataformas") if p in organico.PLATAFORMAS]
    if not pieza_id or not plataformas:
        return jsonify({"error": "Elige la pieza y al menos una plataforma."}), 400
    try:
        textos = organico.redactar(cliente, pieza_id, plataformas)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — el error vuelve al form, nunca un token
        return jsonify({"error": f"No pude redactar el texto: {cola.sin_token(str(e))}"}), 500
    return jsonify({p: {"titulo": t.get("titulo") or "", "caption": t.get("caption") or "",
                        "fallback": bool((t.get("extra") or {}).get("fallback"))} for p, t in textos.items()})


@app.route("/cliente/<cliente>/organico/publicar", methods=["POST"])
def org_publicar(cliente):
    """Con el clic de la persona: crea una `publicacion` (origen manual, con
    `ep_id` si vino de un experimento) por plataforma marcada y encola UNA
    tarea organico_publicar (max_intentos=1). Valida TODO antes de crear
    nada: plataformas sin canal disponible o sin texto → flash y nada se
    publica (publicar a medias sin avisar sería peor). El texto pasa por
    `organico.normalizar_captions` en servidor (máximos, sin enlaces en
    IG/TikTok, hashtags): el `maxlength` del textarea no es garantía. Las
    plataformas con publicación viva se saltan con aviso (unicidad: nunca
    dos veces). Si aun así `crear` falla a mitad, las filas ya creadas
    quedan en `error` (nunca `en_cola` sin tarea bloqueando la plataforma)."""
    ep_id = _int_form("ep_id")
    pieza_id = _int_form("pieza_id") or (_pieza_de_ep(cliente, ep_id) if ep_id else None)
    if not pieza_id:
        flash("No encontré esa pieza.", "error")
        return _volver_org(cliente)
    pedidas = [p for p in organico.ORDEN if p in request.form.getlist("plataformas")]
    if not pedidas:
        flash("Marca al menos una plataforma para publicar.", "error")
        return _volver_org(cliente)
    canales = {c["plataforma"]: c for c in organico.canales(cliente)}
    sin_canal = [p for p in pedidas if not canales[p]["disponible"]]
    if sin_canal:
        flash("Sin canal conectado: " + "; ".join(f"{canales[p]['nombre']} ({canales[p]['motivo']})" for p in sin_canal)
              + ". Actívalo en Configuración › Canales orgánicos. No se publicó nada.", "error")
        return _volver_org(cliente)
    textos = {p: {"caption": (request.form.get(f"caption_{p}") or "").strip(),
                  "titulo": (request.form.get(f"titulo_{p}") or "").strip() or None} for p in pedidas}
    sin_texto = [p for p in pedidas if not textos[p]["caption"]]
    if sin_texto:
        flash(f"Falta el texto para {_nombres_org(sin_texto)}: escríbelo o pulsa «Escribir texto con IA». "
              "No se publicó nada.", "error")
        return _volver_org(cliente)
    try:
        textos = organico.normalizar_captions(cliente, pieza_id, textos)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_org(cliente)
    if trabajos.en_curso(tareas_org.job_id_publicar(cliente, pieza_id)):
        flash("Ya hay una publicación orgánica de esta pieza en curso; espera a que termine.", "warn")
        return _volver_org(cliente)

    pub_ids, creadas, saltadas = [], [], []
    for p in pedidas:
        try:
            pub_ids.append(organico.crear(cliente, pieza_id, p, textos[p]["caption"], titulo=textos[p]["titulo"],
                                          origen="manual", ep_id=ep_id))
            creadas.append(p)
        except ValueError as e:
            if "ya está publicada" in str(e):
                saltadas.append(p)
                continue
            # Creación parcial: lo ya creado no puede quedar `en_cola` sin tarea
            # (bloquearía la plataforma por unicidad); en `error` se reintenta.
            for pub_id in pub_ids:
                organico.actualizar(cliente, pub_id, estado="error",
                                    error=f"No se creó la publicación en {_nombres_org([p])}: {e}")
            flash(f"{e} No se publicó nada.", "error")
            return _volver_org(cliente)
    if saltadas:
        flash(f"Ya estaba publicada (o en cola) en {_nombres_org(saltadas)}: no se publica dos veces.", "warn")
    if not pub_ids:
        return _volver_org(cliente)
    if not _encolar_organico(cliente, pieza_id, pub_ids):
        flash("Ya había una publicación de esta pieza en curso; las nuevas quedaron para reintentar.", "error")
        return _volver_org(cliente)
    if ep_id:
        eid = experimentos.experimento_de_pieza(cliente, ep_id)
        if eid:
            experimentos.marcar_pieza(cliente, ep_id, publicado_organico=True)
            experimentos.registrar_evento(cliente, eid, "accion",
                                          f"Publicación orgánica en cola a mano: {_nombres_org(creadas)}.",
                                          {"accion": "publicar_organico", "plataformas": creadas,
                                           "publicaciones": pub_ids}, ep_id=ep_id)
    flash(f"Publicación orgánica en cola: {_nombres_org(creadas)}. Te avisamos cuando salga.", "ok")
    return _volver_org(cliente)


@app.route("/cliente/<cliente>/organico/<int:pub_id>/reintentar", methods=["POST"])
def org_reintentar(cliente, pub_id):
    """Solo una publicación en `error` SIN id_externo (con id ya subió: un
    reintento sería un segundo upload) y sin otra fila viva de la misma
    (pieza, plataforma): vuelve a `en_cola` (misma fila, así la unicidad viva
    sigue bloqueando un duplicado) y se encola de nuevo con el clic. Nada
    automático: max_intentos=1 en la tarea."""
    pub = organico.obtener(cliente, pub_id)
    if not pub:
        flash("Esa publicación no existe.", "error")
        return _volver_org(cliente)
    if pub["estado"] != "error":
        flash("Solo se reintenta una publicación que falló.", "error")
        return _volver_org(cliente)
    if pub["id_externo"]:
        flash(f"Esa publicación ya se subió a {pub['nombre_plataforma']} (id {pub['id_externo']}); "
              "revisa la plataforma antes de volver a publicarla.", "warn")
        return _volver_org(cliente)
    vivas = {p["plataforma"] for p in organico.listar(cliente, pieza_id=pub["pieza_id"])
             if p["estado"] in organico.ESTADOS_VIVOS}
    if pub["plataforma"] in vivas:
        flash(f"Ya hay una publicación en curso o publicada para {pub['nombre_plataforma']}; no se reintenta.", "warn")
        return _volver_org(cliente)
    if trabajos.en_curso(tareas_org.job_id_publicar(cliente, pub["pieza_id"])):
        flash("Ya hay una publicación orgánica de esta pieza en curso; espera a que termine.", "warn")
        return _volver_org(cliente)
    try:
        organico.actualizar(cliente, pub_id, estado="en_cola", error=None)
    except ValueError as e:
        # Carrera con otra creación entre el chequeo y el UPDATE: gana el índice.
        flash(str(e), "warn")
        return _volver_org(cliente)
    if not _encolar_organico(cliente, pub["pieza_id"], [pub_id]):
        flash("Ya había una publicación de esta pieza en curso; vuelve a intentarlo cuando termine.", "error")
        return _volver_org(cliente)
    flash(f"Reintentando en {pub['nombre_plataforma']}.", "ok")
    return _volver_org(cliente)


@app.route("/cliente/<cliente>/config/reglas", methods=["POST"])
def cfg_reglas(cliente):
    # Las reglas del motor viven en Experimentos, no en Configuración.
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    reglas, errores = decisor.reglas_desde_formulario(request.form)
    if errores:
        _flash_reglas_invalidas(errores)
        return volver
    proyectos.guardar_reglas_defecto(cliente, reglas)
    flash("Reglas por defecto guardadas.", "ok")
    return volver


_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/cliente/<cliente>/config/correo", methods=["POST"])
def cfg_correo(cliente):
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    correo = (request.form.get("correo") or "").strip()
    if correo and not _CORREO_RE.match(correo):
        flash("Ese correo no parece válido.", "error")
        return volver
    proyectos.guardar_correo_notificaciones(cliente, correo)
    flash("Correo guardado." if correo else "Avisos por correo desactivados.", "ok")
    return volver


# ---------- Productos (Bloque 5): importar, marcar, vincular; tiendas y Pixel ----------
# Todo lo que sincroniza o importa corre en el worker (trabajos.encolar): la
# ruta solo valida, guarda el archivo si lo hay y encola. Lo único inline es
# `probar()` de un conector (una llamada corta a la API de la tienda) y
# `vincular_activo` (descarga unas pocas fotos).

IMPORTAR_EXTENSIONES = (".csv", ".xlsx")
IMPORTAR_MAX_BYTES = 5 * 1024 * 1024


def _volver_productos(cliente):
    """Las rutas `prod_*` vuelven al Catálogo: la pestaña Productos ya no
    existe (los productos importados viven en Catálogo › Productos)."""
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="catalogo"))


def _volver_config(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


def _experimentos_por_activo(cliente, experimentos_exp=None):
    """{clave: {experimento_id, ...}} donde clave es el NOMBRE visible del
    activo (lo que Crear guarda en `productos_ids`) o su id. Una pasada por
    las sesiones de Crear y otra por las piezas de cada experimento — nunca
    una consulta por producto. La pieza de un experimento apunta a su sesión
    de Crear por el prefijo de `legado_id` (`<cf_id>` o `<cf_id>__<idioma>_<pais>`)."""
    if experimentos_exp is None:
        experimentos_exp = experimentos.cargar(cliente)
    claves_por_cf = {}
    for cf_id, entry in creative_flow.cargar(cliente).items():
        claves = {str(x) for x in (entry.get("productos_ids") or []) if x}
        if claves:
            claves_por_cf[cf_id] = claves
    por_clave = {}
    for e in experimentos_exp:
        for pz in e.get("piezas") or []:
            legado = str(pz.get("legado_id") or "")
            if not legado:
                continue
            for clave in claves_por_cf.get(legado.split("__")[0], ()):
                por_clave.setdefault(clave, set()).add(e["id"])
    return por_clave


def _productos_tienda_contexto(cliente, experimentos_exp=None):
    """Productos (con archivados: el filtro «mostrar archivados» es de la
    plantilla) enriquecidos con `activo_ok` (su activo existe en el
    catálogo) y `n_experimentos` (cuántos experimentos tienen piezas hechas
    con ese activo)."""
    por_clave = _experimentos_por_activo(cliente, experimentos_exp)
    nombre_de_activo = {a["id"]: a["nombre"] for a in catalogo_productos.listar(cliente, "producto")}
    lista = tiendas.productos(cliente, incluir_archivados=True)
    for prod in lista:
        activo_id = prod.get("activo_catalogo_id")
        prod["activo_ok"] = bool(activo_id) and catalogo_productos.existe(cliente, activo_id, "producto")
        ids_exp = set()
        if activo_id:
            ids_exp |= por_clave.get(activo_id, set())
            ids_exp |= por_clave.get(nombre_de_activo.get(activo_id, ""), set())
        ids_exp |= por_clave.get(prod.get("nombre") or "", set())
        prod["n_experimentos"] = len(ids_exp)
    return lista


def _asegurar_filas_producto(cliente, activos):
    """Todo activo de categoría `producto` tiene su fila comercial (fuente
    `manual`): los anteriores a esta versión la reciben aquí, al listar
    (`tiendas.asegurar_manual` es idempotente y nunca duplica una fila
    importada ya enlazada). Una sola consulta para saber cuáles faltan."""
    con_fila = tiendas.por_activo(cliente)
    for a in activos:
        if a["id"] not in con_fila:
            tiendas.asegurar_manual(cliente, a["id"], a["nombre"], a.get("descripcion") or "")


def _producto_comercial_contexto(productos_tienda):
    """{activo_id: fila producto} para las tarjetas del Catálogo, a partir de
    la lista ya enriquecida (`n_experimentos`, `activo_ok`). Si dos filas
    apuntan al mismo activo (una archivada), gana la viva."""
    mapa = {}
    for p in productos_tienda:
        activo_id = p.get("activo_catalogo_id")
        if not activo_id:
            continue
        previa = mapa.get(activo_id)
        if previa is None or (previa["archivado"] and not p["archivado"]):
            mapa[activo_id] = p
    return mapa


# Nombre visible de cada `producto.fuente` (badge de la tarjeta y nota
# «Sincronizado de …»).
ETIQUETAS_FUENTE = {"manual": "manual", "csv": "CSV/Excel", "url": "URL", "shopify": "Shopify",
                    "woo": "WooCommerce", "meli": "MercadoLibre"}


def _trabajos_productos(cliente, tiendas_cliente, productos=()):
    """{"importar": {"job_id"} | None, "tiendas": {tid: {"job_id"}},
    "vincular": {pid: {"job_id"}}}: qué importación, sincronización o
    «Crear activo» está corriendo, para pintar la barra. Los `vincular` salen
    de UNA consulta a la cola (cola.job_ids_vivos), no de una por producto."""
    vivos = cola.job_ids_vivos(cliente, "producto_vincular") if productos else set()
    vincular = {}
    for prod in productos:
        jid = tareas_tiendas.job_id_vincular(cliente, prod["id"])
        if jid in vivos:
            vincular[prod["id"]] = {"job_id": jid}
    importar = None
    for jid in (tareas_tiendas.job_id_importar_archivo(cliente), tareas_tiendas.job_id_importar_url(cliente)):
        if trabajos.en_curso(jid):
            importar = {"job_id": jid}
            break
    por_tienda = {}
    for t in tiendas_cliente:
        for jid in (tareas_tiendas.job_id_sync_productos(cliente, t["id"]),
                    tareas_tiendas.job_id_sync_pedidos(cliente, t["id"])):
            if trabajos.en_curso(jid):
                por_tienda[t["id"]] = {"job_id": jid}
                break
    return {"importar": importar, "tiendas": por_tienda, "vincular": vincular}


@app.route("/cliente/<cliente>/productos/importar/archivo", methods=["POST"])
def prod_importar_archivo(cliente):
    """Tope de 5 MB por ruta, no `MAX_CONTENT_LENGTH` global: personajes y
    marca suben videos de referencia (mp4/mov) que pasan de largo cualquier
    tope razonable para un CSV. El `Content-Length` se mira antes de leer el
    archivo para no copiar un upload enorme que se va a rechazar igual."""
    if request.content_length and request.content_length > IMPORTAR_MAX_BYTES * 2:
        # x2: el multipart trae cabeceras y el resto del formulario; el tope
        # exacto lo aplica la lectura de abajo.
        flash("El archivo pesa más de 5 MB. Divídelo o quita columnas que no usamos.", "error")
        return _volver_productos(cliente)
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Elige un archivo .csv o .xlsx.", "error")
        return _volver_productos(cliente)
    nombre = secure_filename(archivo.filename) or "catalogo"
    if os.path.splitext(nombre.lower())[1] not in IMPORTAR_EXTENSIONES:
        flash("Solo se aceptan archivos .csv o .xlsx.", "error")
        return _volver_productos(cliente)
    datos = archivo.read(IMPORTAR_MAX_BYTES + 1)
    if not datos:
        flash("El archivo está vacío.", "error")
        return _volver_productos(cliente)
    if len(datos) > IMPORTAR_MAX_BYTES:
        flash("El archivo pesa más de 5 MB. Divídelo o quita columnas que no usamos.", "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_importar_archivo(cliente)
    if trabajos.en_curso(job_id):
        flash("Ya hay una importación de archivo en curso — espera a que termine.", "warn")
        return _volver_productos(cliente)
    carpeta = os.path.join(_client_dir(cliente), "importaciones")
    os.makedirs(carpeta, exist_ok=True)
    # <ts>_<micro>_<nombre>: dos subidas del mismo archivo en el mismo segundo
    # (doble clic) no se pisan la ruta que la tarea va a leer.
    ruta = os.path.join(carpeta, f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{nombre}")
    with open(ruta, "wb") as f:
        f.write(datos)
    # max_intentos=1: crea activos y llama a Claude por cada uno; un reintento
    # a ciegas duplicaría trabajo. La tarea borra el archivo al terminar.
    arranco = trabajos.encolar(
        job_id, "catalogo_importar",
        {"cliente": cliente, "ruta": ruta, "nombre_archivo": nombre, "borrar_al_terminar": True},
        cliente=cliente, duracion_estimada=120, etapas=tareas_tiendas.ETAPAS_IMPORTAR, max_intentos=1)
    if arranco:
        flash(f"Importando «{nombre}»… Los productos aparecen aquí cuando termine.", "ok")
    else:
        try:
            os.remove(ruta)
        except OSError:
            pass
        flash("Ya hay una importación de archivo en curso — espera a que termine.", "warn")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/importar/url", methods=["POST"])
def prod_importar_url(cliente):
    url = (request.form.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        flash("Pega la URL completa de la página del producto (empieza por http:// o https://).", "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_importar_url(cliente)
    arranco = trabajos.encolar(
        job_id, "catalogo_importar", {"cliente": cliente, "url": url},
        cliente=cliente, duracion_estimada=90, etapas=tareas_tiendas.ETAPAS_IMPORTAR, max_intentos=1)
    if arranco:
        flash("Leyendo la página del producto… aparece aquí cuando termine.", "ok")
    else:
        flash("Ya hay una importación desde URL en curso — espera a que termine.", "warn")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/marcar", methods=["POST"])
def prod_marcar(cliente, pid):
    """Banderas del loop: en prueba, prioridad (0–100), URL de compra, precio
    y moneda. Solo toca los campos que vienen en el formulario; `en_prueba`
    siempre viene (un checkbox sin marcar = apagado)."""
    if not tiendas.producto(cliente, pid):
        flash("No encontré ese producto.", "error")
        return _volver_productos(cliente)
    form = request.form
    campos = {"en_prueba": form.get("en_prueba") in ("on", "1", "true")}
    try:
        if "prioridad" in form:
            prioridad = int(form.get("prioridad") or 0)
            if not (0 <= prioridad <= 100):
                raise ValueError
            campos["prioridad"] = prioridad
        if "precio" in form:
            precio_txt = (form.get("precio") or "").strip().replace(",", ".")
            precio = float(precio_txt) if precio_txt else None
            if precio is not None and (not math.isfinite(precio) or precio < 0):
                raise ValueError
            campos["precio"] = precio
    except ValueError:
        flash("Revisa los números: prioridad entre 0 y 100, precio positivo.", "error")
        return _volver_productos(cliente)
    if "url_compra" in form:
        url = (form.get("url_compra") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            flash("La URL de compra tiene que empezar por http:// o https://.", "error")
            return _volver_productos(cliente)
        campos["url_compra"] = url or None
    if "moneda" in form:
        moneda = (form.get("moneda") or "").strip().upper()
        if moneda and not _MONEDA_RE.match(moneda):
            flash("La moneda va en código de 3 letras (COP, MXN, USD…).", "error")
            return _volver_productos(cliente)
        campos["moneda"] = moneda or None
    tiendas.marcar_producto(cliente, pid, **campos)
    flash("Producto actualizado.", "ok")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/archivar", methods=["POST"])
def prod_archivar(cliente, pid):
    """Archiva (o, con archivado=0, recupera) un producto. No borra nada: un
    producto archivado sigue ligado a su activo y a sus experimentos. Es un
    archivado MANUAL (`tiendas.marcar_producto` deja `extra.archivado_por =
    "manual"`): la sync de la tienda no lo desarchiva aunque el producto
    siga allá; solo «Recuperar» (archivado=0) lo devuelve a la lista."""
    if not tiendas.producto(cliente, pid):
        flash("No encontré ese producto.", "error")
        return _volver_productos(cliente)
    archivar = (request.form.get("archivado") or "1") not in ("0", "false", "off")
    tiendas.marcar_producto(cliente, pid, archivado=archivar)
    flash("Producto archivado." if archivar else "Producto recuperado.", "ok")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/vincular", methods=["POST"])
def prod_vincular(cliente, pid):
    """Encola `producto_vincular` (worker): crea o completa el activo del
    catálogo bajando las fotos otra vez y pidiendo la regla a Claude. No va
    inline: hasta 6 fotos × 30 s + Claude pasan de largo el timeout de
    gunicorn. max_intentos=1 porque llama a Claude."""
    prod = tiendas.producto(cliente, pid)
    if not prod:
        flash("No encontré ese producto.", "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_vincular(cliente, pid)
    arranco = trabajos.encolar(
        job_id, "producto_vincular", {"cliente": cliente, "producto_id": pid},
        cliente=cliente, duracion_estimada=90, etapas=tareas_tiendas.ETAPAS_VINCULAR, max_intentos=1)
    if arranco:
        flash(f"Creando el activo de «{prod.get('nombre') or pid}»… aparece en el Catálogo cuando termine.", "ok")
    else:
        flash("Ya se está creando el activo de ese producto — espera a que termine.", "warn")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/fotos", methods=["POST"])
def prod_fotos_subir(cliente, pid):
    """«Subir fotos» de un producto importado sin fotos (o cuyo activo ya no
    existe): crea el activo del catálogo con el nombre y la descripción del
    producto, guarda las fotos y enlaza la fila (`activo_catalogo_id`). Va
    inline porque no baja nada de la red ni llama a Claude: son las fotos
    que la persona acaba de elegir. Si ya hay un activo con ese id (otro
    producto con el mismo nombre) se desambigua con `-2`, `-3`…, igual que
    el importador, en vez de pisarle las fotos al otro."""
    prod = tiendas.producto(cliente, pid)
    if not prod:
        flash("No encontré ese producto.", "error")
        return _volver_productos(cliente)
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not archivos:
        flash("No elegiste ninguna foto.", "error")
        return _volver_productos(cliente)
    nombre = (prod.get("nombre") or "").strip() or f"Producto {pid}"
    enlazado = prod.get("activo_catalogo_id")
    if enlazado and catalogo_productos.existe(cliente, enlazado, "producto"):
        # Página vieja o doble envío: el activo ya existe. Las fotos van a
        # ese, no a un segundo activo con el mismo nombre.
        guardadas = _guardar_fotos_producto(cliente, enlazado, archivos)
        flash(f"{guardadas} foto(s) añadida(s) a «{nombre}»." if guardadas
              else "Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).",
              "ok" if guardadas else "error")
        return _volver_productos(cliente)
    base = catalogo_productos.id_desde_nombre(nombre)
    activo_id, sufijo = base, 2
    while catalogo_productos.existe(cliente, activo_id, "producto"):
        activo_id = f"{base}-{sufijo}"
        sufijo += 1
    try:
        catalogo_productos.crear(cliente, nombre, prod.get("descripcion") or "", categoria="producto",
                                 producto_id=activo_id)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_productos(cliente)
    guardadas = _guardar_fotos_producto(cliente, activo_id, archivos)
    if not guardadas:
        # Sin foto válida el activo no aparecería en el catálogo y la fila
        # quedaría enlazada a algo invisible: mejor deshacer.
        catalogo_productos.eliminar(cliente, activo_id, categoria="producto")
        flash("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp).", "error")
        return _volver_productos(cliente)
    tiendas.marcar_producto(cliente, pid, activo_catalogo_id=activo_id)
    flash(f"«{nombre}» ya está en el catálogo con {guardadas} foto(s).", "ok")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/experimento", methods=["POST"])
def prod_experimento(cliente, pid):
    """Manda a Experimentos (la galería) con el nombre y la URL de destino del
    producto ya puestos en el paso 3 de «Probar en Meta» — la plantilla los
    lee de request.args (exp_nombre, exp_destino)."""
    prod = tiendas.producto(cliente, pid)
    if not prod:
        flash("No encontré ese producto.", "error")
        return _volver_productos(cliente)
    return redirect(url_for("ver_cliente", cliente=cliente, exp_nombre=prod["nombre"] or "",
                            exp_destino=prod.get("url_compra") or "", _anchor="experimentos"))


def _encolar_sync_tienda(cliente, tienda_id, tipo, con_pedidos=True):
    """Encola la sync de productos y, si el conector sabe leer ventas, la de
    pedidos. Devuelve cuántas tareas arrancaron."""
    n = 0
    if trabajos.encolar(tareas_tiendas.job_id_sync_productos(cliente, tienda_id), "tienda_sync_productos",
                        {"cliente": cliente, "tienda_id": tienda_id}, cliente=cliente, duracion_estimada=120,
                        etapas=tareas_tiendas.ETAPAS_IMPORTAR, max_intentos=tareas_tiendas.MAX_INTENTOS_SYNC):
        n += 1
    if con_pedidos:
        try:
            tiene_pedidos = bool(getattr(conectores.por_tipo(tipo), "tiene_pedidos", False))
        except ValueError:
            tiene_pedidos = False
        if tiene_pedidos and trabajos.encolar(
                tareas_tiendas.job_id_sync_pedidos(cliente, tienda_id), "tienda_sync_pedidos",
                {"cliente": cliente, "tienda_id": tienda_id}, cliente=cliente, duracion_estimada=60,
                max_intentos=tareas_tiendas.MAX_INTENTOS_SYNC):
            n += 1
    return n


def _flash_sin_cifrado():
    flash("Falta FLASK_SECRET_KEY en el .env del servidor: sin ella no se pueden guardar las "
          "credenciales de una tienda.", "error")


@app.route("/cliente/<cliente>/config/tienda/conectar", methods=["POST"])
def tienda_conectar(cliente):
    """Shopify/WooCommerce: prueba las credenciales contra la tienda (inline,
    una llamada corta), las guarda cifradas y encola la primera sync."""
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not cifrado.disponible():
        _flash_sin_cifrado()
        return _volver_config(cliente)
    tipo = (request.form.get("tipo") or "").strip()
    if tipo == "shopify":
        dominio = (request.form.get("dominio") or "").strip()
        creds = {"dominio": dominio, "token": (request.form.get("token") or "").strip()}
    elif tipo == "woo":
        url = (request.form.get("url") or "").strip()
        dominio = re.sub(r"^https?://", "", url).strip("/").split("/")[0]
        creds = {"url": url, "ck": (request.form.get("ck") or "").strip(), "cs": (request.form.get("cs") or "").strip()}
    else:
        flash("Ese tipo de tienda no se conecta desde aquí (Shopify o WooCommerce; MercadoLibre va por su botón).", "error")
        return _volver_config(cliente)
    try:
        resultado = conectores.por_tipo(tipo)(creds).probar()
    except (ErrorConector, ValueError) as e:
        flash(f"No pude conectar la tienda: {cola.sin_token(str(e))}", "error")
        return _volver_config(cliente)
    except Exception as e:  # noqa: BLE001 — un fallo de red/parseo también se muestra, nunca se guarda a ciegas
        flash(f"No pude conectar la tienda: {cola.sin_token(str(e) or type(e).__name__)}", "error")
        return _volver_config(cliente)
    nombre = str((resultado or {}).get("nombre") or "").strip() or None
    tid = tiendas.conectar(cliente, tipo, creds, nombre=nombre, dominio=dominio or None)
    n = _encolar_sync_tienda(cliente, tid, tipo)
    detalle = str((resultado or {}).get("detalle") or "").strip()
    flash(f"Tienda {nombre or dominio} conectada. {detalle} "
          + ("Sincronizando el catálogo…" if n else "Ya había una sincronización en curso."), "ok")
    return _volver_config(cliente)


@app.route("/cliente/<cliente>/config/tienda/meli/iniciar")
def tienda_meli_iniciar(cliente):
    """Arranca el OAuth de MercadoLibre. El `state` queda en la sesión junto
    con el cliente: el callback (global, sin <cliente>) lo resuelve de ahí."""
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not cifrado.disponible():
        _flash_sin_cifrado()
        return _volver_config(cliente)
    faltan = [v for v in ("MELI_APP_ID", "MELI_SECRET") if not (os.environ.get(v) or "").strip()]
    if faltan:
        flash("Falta configurar " + " y ".join(faltan) + " en el .env del servidor "
              "(app de developers.mercadolibre.com).", "error")
        return _volver_config(cliente)
    state = secrets.token_urlsafe(32)
    session["meli_oauth"] = {"state": state, "cliente": cliente}
    try:
        return redirect(conector_meli.url_autorizacion(state, url_for("meli_callback", _external=True)))
    except ErrorConector as e:
        session.pop("meli_oauth", None)
        flash(str(e), "error")
        return _volver_config(cliente)


@app.route("/meli/callback")
def meli_callback():
    """Ruta SIN <cliente> (MercadoLibre redirige a una sola dirección
    registrada): el cliente sale de la sesión, nunca de la query, y el state
    es de un solo uso. Mismo patrón que meta_callback."""
    pendiente = session.pop("meli_oauth", None) or {}
    cliente = pendiente.get("cliente")
    state_ok = bool(pendiente.get("state")) and request.args.get("state") == pendiente.get("state")
    if not cliente or not state_ok:
        flash("La autorización con MercadoLibre no coincide con esta sesión — vuelve a intentarlo desde Configuración.", "error")
        return _volver_config(cliente) if cliente else redirect(url_for("index"))
    if not usuarios.puede_acceder(_sesion(), cliente):
        flash("No tienes acceso a ese proyecto.", "error")
        return redirect(url_for("index"))
    if request.args.get("error"):
        detalle = request.args.get("error_description") or request.args.get("error")
        flash(f"MercadoLibre no autorizó la conexión: {detalle}", "error")
        return _volver_config(cliente)
    if not cifrado.disponible():
        _flash_sin_cifrado()
        return _volver_config(cliente)
    try:
        creds = conector_meli.cambiar_code(request.args.get("code", ""), url_for("meli_callback", _external=True))
    except ErrorConector as e:
        flash(str(e), "error")
        return _volver_config(cliente)
    nombre = str(creds.get("nickname") or "").strip() or None
    tid = tiendas.conectar(cliente, "meli", creds, nombre=nombre, dominio=None)
    n = _encolar_sync_tienda(cliente, tid, "meli")
    flash(f"MercadoLibre conectado{(' (' + nombre + ')') if nombre else ''}. "
          + ("Sincronizando las publicaciones…" if n else "Ya había una sincronización en curso."), "ok")
    return _volver_config(cliente)


@app.route("/cliente/<cliente>/config/tienda/<int:tid>/sincronizar", methods=["POST"])
def tienda_sync(cliente, tid):
    """Encola productos + pedidos. También para una tienda `rota`: volver a
    sincronizar es como la persona comprueba que ya se arregló."""
    t = tiendas.obtener(cliente, tid)
    if not t:
        flash("Esa tienda no existe.", "error")
        return _volver_config(cliente)
    n = _encolar_sync_tienda(cliente, tid, t["tipo"])
    flash("Sincronizando…" if n else "Ya se está sincronizando esa tienda.", "ok" if n else "warn")
    return _volver_config(cliente)


@app.route("/cliente/<cliente>/config/tienda/<int:tid>/desconectar", methods=["POST"])
def tienda_desconectar(cliente, tid):
    if tiendas.desconectar(cliente, tid):
        flash("Tienda desconectada. Sus productos quedaron archivados y sus pedidos se conservan (no se borró nada).", "ok")
    else:
        flash("Esa tienda no existe.", "error")
    return _volver_config(cliente)


PIXEL_ESTADOS_TEXTO = {
    "ok": "El Pixel está disparando.",
    "sin_datos": "El Pixel existe pero no ha disparado en los últimos días.",
    "sin_pixel": "La cuenta publicitaria no tiene ningún Pixel.",
    "sin_conexion": "Meta no está conectado.",
    "error": "No pude consultar el Pixel.",
}


@app.route("/cliente/<cliente>/config/pixel/refrescar", methods=["POST"])
def cfg_pixel_refrescar(cliente):
    meta_conexion.invalidar_pixel(cliente)
    r = meta_conexion.estado_pixel(cliente) or {}
    estado = r.get("estado") or "error"
    texto = PIXEL_ESTADOS_TEXTO.get(estado, estado)
    if estado == "error" and r.get("detalle"):
        texto += f" {r['detalle']}"
    flash(texto, "ok" if estado == "ok" else "warn")
    return _volver_config(cliente)


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


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/descartar", methods=["POST"])
def cf_descartar(cliente, cf_id):
    creative_flow.eliminar(cliente, cf_id)
    flash("Sesión de CreativeFlowPlus descartada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


# ---------------------------------------------------------- Final edition ---

IDIOMAS_FE = ("es", "en", "pt")


def _volver_crear(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


def _precio_form(valor):
    """Precio opcional del formulario -> float o None (vacío o basura = None)."""
    valor = (valor or "").strip().replace(",", ".")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _sesion_con_video(cliente, cf_id):
    """Sesión de Crear con video listo, o None (con flash) si no aplica."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        flash("Esa sesión de Crear ya no existe.", "error")
        return None
    if entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        flash("Final edition necesita un video listo (no una imagen ni una sesión sin generar).", "error")
        return None
    return entry


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/preparar", methods=["POST"])
def fe_preparar(cliente, cf_id):
    """Encola la escritura del guion base (capa 0, Anthropic). No produce nada."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_crear(cliente)
    idioma_base = request.form.get("idioma_base") or "es"
    if idioma_base not in IDIOMAS_FE:
        idioma_base = "es"
    opciones = {"precio": _precio_form(request.form.get("precio")), "idioma_base": idioma_base}
    encolado = trabajos.encolar(
        tareas_fe.job_id_guion(cliente, cf_id), "final_guion",
        {"cliente": cliente, "cf_id": cf_id, "opciones": opciones},
        cliente=cliente, duracion_estimada=25, max_intentos=2,
    )
    flash("Escribiendo el guion con IA… en unos segundos aparece aquí para que lo revises." if encolado
          else "Ya se estaba escribiendo el guion de esta pieza.", "ok")
    return _volver_crear(cliente)


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/guion", methods=["POST"])
def fe_guardar_guion(cliente, cf_id):
    """Guarda la edición del guion base: solo cambian los textos (pantalla y
    voz) de cada bloque; tiempos, roles, idioma y país se conservan."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_crear(cliente)
    base = creative_flow.guion_base(cliente, cf_id)
    if not base or not base.get("bloques"):
        flash("Primero prepara el guion con IA; después lo editas.", "error")
        return _volver_crear(cliente)
    guion = dict(base)
    guion["bloques"] = []
    for i, bloque in enumerate(base["bloques"]):
        b = dict(bloque)
        b["texto_pantalla"] = (request.form.get(f"bloque_{i}_pantalla") or "").strip()
        b["texto_voz"] = (request.form.get(f"bloque_{i}_voz") or "").strip()
        guion["bloques"].append(b)
    duracion = float(base["bloques"][-1].get("fin_s") or 0) + 0.05
    errores = fe_tipos.validar_guion(guion, duracion)
    if errores:
        flash("No se guardó el guion: " + " ".join(errores), "error")
        return _volver_crear(cliente)
    creative_flow.guardar_guion_base(cliente, cf_id, guion)
    flash("Guion guardado. Ahora elige los destinos y produce las finales.", "ok")
    return _volver_crear(cliente)


def _destinos_form(valores):
    """["es_CO", "en_US", ...] -> [("es", "CO"), ...]; None si alguno no vale."""
    destinos = []
    for v in valores:
        partes = (v or "").split("_")
        if len(partes) != 2 or partes[0] not in IDIOMAS_FE or partes[1] not in fe_tipos.PAISES:
            return None
        if (partes[0], partes[1]) not in destinos:
            destinos.append((partes[0], partes[1]))
    return destinos


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/producir", methods=["POST"])
def fe_producir(cliente, cf_id):
    """Encola una tarea `final_producir` por cada destino marcado. Exige guion
    base ya preparado (y revisado): sin él no se gasta nada."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_crear(cliente)
    base = creative_flow.guion_base(cliente, cf_id)
    if not base:
        flash("Primero prepara el guion con IA y revísalo; sin guion no se produce nada.", "error")
        return _volver_crear(cliente)
    destinos = _destinos_form(request.form.getlist("destinos"))
    if not destinos:
        flash("Marca al menos un destino (idioma y país) válido para producir.", "error")
        return _volver_crear(cliente)

    idioma_base = base.get("idioma") if base.get("idioma") in IDIOMAS_FE else "es"
    voces_validas = {v for lista in fal_audio.VOCES.values() for v in lista}
    voz = request.form.get("voz") or ""
    if voz not in voces_validas:
        voz = (fal_audio.VOCES.get(idioma_base) or fal_audio.VOCES["es"])[0]
    estilo = request.form.get("estilo_musica") or ""
    if estilo not in fe_tipos.ESTILOS_MUSICA:
        estilo = "energetico"
    # Solo los destinos con precio escrito: un campo vacío no debe tapar el
    # precio base del país base (lo resuelve final_edition.producir).
    precios = {}
    for idioma, pais in destinos:
        valor = _precio_form(request.form.get(f"precio_{idioma}_{pais}"))
        if valor is not None:
            precios[f"{idioma}_{pais}"] = valor
    opciones = {
        "voz": voz,
        "estilo_musica": estilo,
        "con_voz": bool(request.form.get("con_voz")),
        "con_musica": bool(request.form.get("con_musica")),
        "precio": _precio_form(request.form.get("precio")),
        "precios": precios,
        "idioma_base": idioma_base,
        # Capa sonido (S2): el audio nativo del clon crudo; un preset de mezcla
        # que no existe cae al de defecto en vez de tumbar la tarea.
        "con_sonido": bool(request.form.get("con_sonido")),
        "sonido": "nativo",
        "mezcla": request.form.get("mezcla") if request.form.get("mezcla") in fe_mezcla.PRESETS else fe_mezcla.PRESET_DEFECTO,
    }
    encolados = 0
    for idioma, pais in destinos:
        job_id = tareas_fe.job_id_final(cliente, cf_id, idioma, pais)
        if trabajos.en_curso(job_id):
            # Ya hay una viva: no se toca la fila (el worker la está escribiendo).
            continue
        # La fila final existe en `generando` desde que se encola, así la
        # cuadrícula la muestra con su barra sin esperar a que el worker arranque.
        creative_flow.crear_final(cliente, cf_id, idioma, pais)
        if trabajos.encolar(
            job_id, "final_producir",
            {"cliente": cliente, "cf_id": cf_id, "idioma": idioma, "pais": pais, "opciones": dict(opciones)},
            cliente=cliente, duracion_estimada=150, etapas=ETAPAS_FINAL, max_intentos=1,
        ):
            encolados += 1
    if encolados:
        flash(f"Produciendo {encolados} finales… cada una aparece en Generados cuando termina.", "ok")
    else:
        flash("Ya se estaban produciendo esas finales.", "ok")
    return _volver_crear(cliente)


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/descartar", methods=["POST"])
def fe_descartar(cliente, cf_id, final_id):
    final = creative_flow.final_por_legado(cliente, final_id) if final_id.startswith(cf_id + "__") else None
    if final and trabajos.en_curso(tareas_fe.job_id_final(cliente, cf_id, final["idioma"], final["pais"],
                                                          variante=final.get("variante"))):
        # Borrar la fila mientras el worker la escribe la dejaría resucitar a
        # medias (actualizar_final sobre una pieza que ya no existe).
        flash("Esa final se está produciendo; espera a que termine.", "error")
        return _volver_crear(cliente)
    if not final or not creative_flow.eliminar_final(cliente, final_id):
        flash("Esa final ya no existe.", "error")
    else:
        flash("Final descartada.", "ok")
    return _volver_crear(cliente)


def _lanzar_video_cf(cliente, cf_id, entry):
    """Encola la generación de una sesión de FlowPlus (video o imagen). Lo usan
    cf_crear_video y cf_generar_video. El cuerpo vive en flowplus_lanzar.py
    (compartido con los lotes de Sprints)."""
    return flowplus_lanzar.lanzar(cliente, cf_id, entry)


def _job_id_link(cliente):
    return f"{cliente}__flowplus_link"


def _guardar_referencia_archivo(cliente, archivo, i):
    """Sube un archivo (imagen o video) a R2 con nombre único y lo mete en la
    bandeja. A los videos se les extrae un fotograma (miniatura + referencia
    para los modelos que no aceptan video). Devuelve True si entró."""
    nombre = secure_filename(archivo.filename)
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        return False
    carpeta = os.path.join(_client_dir(cliente), "referencias_flowplus")
    os.makedirs(carpeta, exist_ok=True)
    unico = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{i}{ext}"
    local_path = os.path.join(carpeta, unico)
    archivo.save(local_path)
    if ext in VIDEO_EXTS:
        url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/referencias_flowplus/{unico}")
        frame_path = local_path + FRAME_SUFFIX
        _extraer_frame(local_path, frame_path)
        frame_url = r2_uploader.upload_image(frame_path, f"clientes/{cliente}/referencias_flowplus/{unico}{FRAME_SUFFIX}")
        referencias_flowplus.agregar(cliente, "video", url, frame_url=frame_url, origen="archivo", ruta_local=local_path, titulo=nombre)
    else:
        url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/referencias_flowplus/{unico}")
        referencias_flowplus.agregar(cliente, "imagen", url, origen="archivo", ruta_local=local_path, titulo=nombre)
    return True


def _quiere_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _respuesta_bandeja(cliente, mensaje=None, error=None):
    """Para las llamadas por fetch: devuelve la bandeja ya renderizada (HTML del
    parcial) para reemplazar solo ese trozo de la página, sin recargar."""
    refs = referencias_flowplus.listar(cliente)
    html = render_template("_flowplus_bandeja.html", cliente=cliente, referencias_bandeja=refs,
                           trabajo_link={"job_id": _job_id_link(cliente)} if trabajos.en_curso(_job_id_link(cliente)) else None)
    return jsonify({"ok": error is None, "html": html, "mensaje": mensaje, "error": error,
                    "etiquetas": [r["etiqueta"] for r in refs]})


@app.route("/cliente/<cliente>/flowplus/referencias/subir", methods=["POST"])
def fp_subir_referencias(cliente):
    archivos = [a for a in request.files.getlist("referencias") if a and a.filename][:15]
    ok = 0
    errores = []
    for i, a in enumerate(archivos):
        try:
            ok += 1 if _guardar_referencia_archivo(cliente, a, i) else 0
        except Exception as e:
            bitacora.registrar(cliente, a.filename, "flowplus_referencia", "error", str(e))
            errores.append(f"No pude subir {a.filename}: {e}")
    mensaje = f"{ok} referencia(s) agregada(s)." if ok else None
    error = "; ".join(errores) if errores else (None if archivos else "No elegiste ningún archivo.")
    if _quiere_json():
        return _respuesta_bandeja(cliente, mensaje=mensaje, error=error)
    if mensaje:
        flash(mensaje, "ok")
    if error:
        flash(error, "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/flowplus/referencias/bandeja")
def fp_bandeja(cliente):
    """Estado actual de la bandeja (para refrescar tras la descarga de un link)."""
    return _respuesta_bandeja(cliente)


@app.route("/cliente/<cliente>/flowplus/referencias/link", methods=["POST"])
def fp_agregar_link(cliente):
    """Descarga el video del link en segundo plano (TrendTrack directo; el resto
    con yt-dlp), lo recorta a 15 s, lo sube a R2 y lo deja en la bandeja."""
    url = (request.form.get("link") or "").strip()
    if not url:
        flash("Pega un link primero.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    job_id = _job_id_link(cliente)

    def trabajo():
        carpeta = os.path.join(_client_dir(cliente), "referencias_flowplus")
        base = f"link_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        try:
            local_path, meta = referencias_link.descargar(url, carpeta, base)
            r2_url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/referencias_flowplus/{base}.mp4")
            frame_path = local_path + FRAME_SUFFIX
            _extraer_frame(local_path, frame_path)
            frame_url = r2_uploader.upload_image(frame_path, f"clientes/{cliente}/referencias_flowplus/{base}{FRAME_SUFFIX}")
            referencias_flowplus.agregar(cliente, "video", r2_url, frame_url=frame_url, origen=meta.get("fuente", "link"),
                                         ruta_local=local_path, titulo=meta.get("titulo") or url)
            bitacora.registrar(cliente, base, "flowplus_link", "ok", url)
        except Exception as e:
            bitacora.registrar(cliente, base, "flowplus_link", "error", str(e))
            raise
        return "Video del link agregado a las referencias."

    arranco = trabajos.iniciar(job_id, trabajo, duracion_estimada=40)
    if _quiere_json():
        return _respuesta_bandeja(cliente, mensaje="Descargando el video del link…" if arranco else None,
                                  error=None if arranco else "Ya se está descargando un link — espera a que termine.")
    if arranco:
        flash("Descargando el video del link… en unos segundos aparece entre las referencias.", "ok")
    else:
        flash("Ya se está descargando un link — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/flowplus/referencias/<rid>/quitar", methods=["POST"])
def fp_quitar_referencia(cliente, rid):
    referencias_flowplus.quitar(cliente, rid)
    if _quiere_json():
        return _respuesta_bandeja(cliente)
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/flowplus/referencias/vaciar", methods=["POST"])
def fp_vaciar_referencias(cliente):
    referencias_flowplus.vaciar(cliente)
    if _quiere_json():
        return _respuesta_bandeja(cliente)
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/flowplus/reusar/<cf_id>", methods=["POST"])
def fp_reusar(cliente, cf_id):
    """"Editar y crear otra a partir de esta": las referencias de esa pieza (sin
    los logos, que se adjuntan solos) vuelven a la bandeja y el texto, tipo,
    modelo, duración, formato, sonido, música y calidad quedan precargados en
    el formulario de Crear. Si la pieza es una imagen generada, ella misma
    puede entrar como referencia."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        flash("No encontré esa pieza.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    ya = {r["url"] for r in referencias_flowplus.listar(cliente)}
    for r in entry.get("referencias") or []:
        if r.get("logo") or r.get("url") in ya:
            continue
        referencias_flowplus.agregar(
            cliente, r.get("tipo") or "imagen", r["url"], frame_url=r.get("frame_url"),
            origen="reutilizada", titulo=r.get("activo") or r.get("etiqueta"), producto=r.get("producto"),
        )
        ya.add(r["url"])
    if request.form.get("incluir_resultado") == "si" and entry.get("tipo") == "imagen" and entry.get("video_url") not in ya:
        referencias_flowplus.agregar(cliente, "imagen", entry["video_url"], origen="generada", titulo="Imagen generada")
    session["fp_prefill"] = {
        "texto": entry.get("prompt_fuente") or entry.get("accion_central") or "",
        "tipo": entry.get("tipo") or "video",
        "modelo": entry.get("modelo") or "",
        "duracion": entry.get("duracion_objetivo") or proyectos.preferencias_flowplus(cliente)["duracion_defecto"],
        "aspect_ratio": entry.get("aspect_ratio") or "9:16",
        "enfoque": entry.get("enfoque") or "",
        "con_sonido": entry.get("con_sonido", True) is not False,
        "sonido_texto": entry.get("sonido_texto") or "",
        "musica_estilo": entry.get("musica_estilo") or "",
        "calidad": entry.get("calidad") or "final",
        "preset_camara": entry.get("preset_camara"),
        "plantilla": entry.get("plantilla"),
    }
    flash("Referencias y texto cargados — ajusta lo que quieras y genera.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/flowplus/describir", methods=["POST"])
def fp_describir(cliente):
    """Claude mira las referencias de la bandeja y propone el texto del video.
    Devuelve JSON para rellenar el cuadro sin recargar."""
    refs = referencias_flowplus.listar(cliente)
    if not refs:
        return jsonify({"ok": False, "error": "Agrega primero una imagen, un video o un link."}), 400
    try:
        texto = referencias_link.describir(refs, cliente_hint=proyectos.nombre_visible(cliente))
    except Exception as e:
        bitacora.registrar(cliente, "flowplus", "describir", "error", str(e))
        return jsonify({"ok": False, "error": f"No pude describir las referencias ({type(e).__name__})."}), 502
    bitacora.registrar(cliente, "flowplus", "describir", "ok", texto[:120])
    return jsonify({"ok": True, "texto": texto})


@app.route("/cliente/<cliente>/creative_flow/crear", methods=["POST"])
def cf_crear_video(cliente):
    """Crear: referencias + activos + idea corta → sesión en prompt_pendiente y
    tarea flowplus_director (gratis). La generación (paga) la dispara la
    persona desde la tarjeta con cf_generar_video (spec director §1)."""
    accion_central = (request.form.get("accion_central") or "").strip()
    tipo = "imagen" if request.form.get("tipo") == "imagen" else "video"
    # Sonido de la escena y música al crear (spec estudio S1): solo para videos.
    con_sonido = tipo == "video" and request.form.get("con_sonido") == "si"
    sonido_texto = " ".join((request.form.get("sonido") or "").split())[:200] if tipo == "video" else ""
    musica_estilo = (request.form.get("musica_estilo") or "").strip() if tipo == "video" else ""
    if musica_estilo not in fe_tipos.ESTILOS_MUSICA:
        musica_estilo = ""
    prefs = proyectos.preferencias_flowplus(cliente)
    modelo = (request.form.get("modelo") or "").strip()
    if tipo == "imagen":
        if modelo not in flowplus_modelos.IMAGEN:
            modelo = prefs["modelo_imagen"]
    else:
        if modelo not in flowplus_modelos.VIDEO:
            modelo = prefs["modelo_video"]
    # Duración y formato: lo que el modelo admite manda (Kling llega a 15 s;
    # Seedance no elige formato; la imagen tiene su propio selector).
    duracion_objetivo = 0
    aviso_duracion = None
    if tipo == "imagen":
        aspect_ratio = flowplus_modelos.ajustar_formato(modelo, request.form.get("aspect_ratio_imagen") or "", tipo="imagen")
    else:
        pedida = request.form.get("duracion_objetivo")
        duracion_objetivo = flowplus_modelos.ajustar_duracion(modelo, pedida)
        try:
            if int(float(pedida)) != duracion_objetivo:
                aviso_duracion = duracion_objetivo
        except (TypeError, ValueError):
            pass
        aspect_ratio = flowplus_modelos.ajustar_formato(modelo, request.form.get("aspect_ratio") or "")

    calidad = (request.form.get("calidad") or "final").strip()
    if calidad not in flowplus_modelos.CALIDADES or modelo != "wan3" or tipo == "imagen":
        calidad = "final"

    # Las referencias vienen de la bandeja (archivos subidos y links ya
    # descargados), en el orden en que se agregaron, con sus etiquetas.
    referencias = []
    for r in referencias_flowplus.listar(cliente):
        referencias.append({"tipo": r["tipo"], "url": r["url"], "frame_url": r.get("frame_url") or r["url"],
                            "etiqueta": r["etiqueta"], "origen": r.get("origen")})
    n_img = sum(1 for r in referencias if r["tipo"] == "imagen")

    # Activos del catálogo (productos, personajes, entornos). El valor del
    # checkbox es "categoria:id"; los productos viejos pueden venir como "id" a
    # secas. Un personaje entra con hasta 3 fotos (frente/perfil/cuerpo) para
    # que el modelo mantenga la identidad; producto y entorno con la principal.
    productos_sel = []
    contadores = {}
    for valor in request.form.getlist("productos_catalogo"):
        cat, _, pid = valor.partition(":") if ":" in valor else ("producto", "", valor)
        activo = catalogo_productos.encontrar(cliente, pid, categoria=cat)
        if not activo:
            continue
        info_cat = catalogo_productos.CATEGORIAS[activo["categoria"]]
        n_fotos = 3 if activo["categoria"] == "personaje" else 1
        contadores[activo["categoria"]] = contadores.get(activo["categoria"], 0) + 1
        etiqueta = f"{info_cat['etiqueta']} {contadores[activo['categoria']]}"
        for j, ruta in enumerate(activo["referencias"][:n_fotos]):
            try:
                url = r2_uploader.upload_image(
                    ruta, f"clientes/{cliente}/{info_cat['carpeta']}/{pid}/{os.path.basename(ruta)}")
            except Exception as e:
                bitacora.registrar(cliente, pid, "flowplus_activo", "error", str(e))
                continue
            referencias.append({
                "tipo": "imagen", "url": url, "frame_url": url,
                "etiqueta": etiqueta if j == 0 else f"{etiqueta} (vista {j + 1})",
                "categoria": activo["categoria"], "activo": activo["nombre"], "regla": activo["regla"],
                "producto": activo["nombre"] if activo["categoria"] == "producto" else None,
            })
        productos_sel.append(activo["nombre"])

    # Logos oficiales del proyecto: referencia extra, siempre, para que la marca
    # salga como es y no inventada. Cuentan para el tope de imágenes del modelo.
    logos = []
    for i, l in enumerate(_logos(cliente)[:2], start=1):
        logos.append({"tipo": "imagen", "url": l["url"], "frame_url": l["url"], "etiqueta": f"@Logo {i}", "logo": True})
    referencias = (referencias + logos)[:15]
    if tipo == "video":
        flowplus_prompt.asignar_tokens(referencias, modelo)
    # referencias_urls sigue siendo la lista plana de IMÁGENES (los videos van por
    # su fotograma) — es lo que consumen los modelos que no aceptan video.
    referencias_urls = [r["frame_url"] for r in referencias][:10]
    if not referencias:
        flash("Sube al menos una imagen o un video, o elige un producto del catálogo: el modelo necesita una referencia.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not accion_central:
        flash("Escribe qué tiene que pasar en el video.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    enfoque = "persona" if any(r.get("categoria") == "personaje" for r in referencias) else "producto"
    info = flowplus_prompt.ENFOQUES[enfoque]
    cf_id = creative_flow.crear(
        cliente, [], productos_sel, [],
        accion_central, duracion_objetivo, "", "A",
        referencias_urls=referencias_urls, platforms=[],
    )
    campos = dict(
        aspect_ratio=aspect_ratio, tipo=tipo, modelo=modelo, referencias=referencias,
        con_persona=info["con_persona"], enfoque=enfoque, enfoque_nombre=info["nombre"],
        con_sonido=con_sonido, sonido_texto=sonido_texto, musica_estilo=musica_estilo,
        prompt_fuente=accion_central, calidad=calidad, idioma_prompt=prefs["idioma_prompt"],
        preset_camara=None, plantilla=None,
    )
    if tipo == "imagen":
        # La imagen no pasa por el director (spec §2.2): el prompt es el de siempre.
        prompt_final = flowplus_prompt.armar(
            accion_central, referencias, con_persona=info["con_persona"],
            guia_marca=marca_mod.guia_efectiva(cliente), negative_marca=marca_mod.negative_prompt_efectivo(cliente),
            logos=[r for r in referencias if r.get("logo")], enfoque=enfoque, sonido=None, con_sonido=False,
        )
        creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_final, **campos)
        entry = creative_flow.cargar(cliente)[cf_id]
        lanzado = _lanzar_video_cf(cliente, cf_id, entry)
        referencias_flowplus.vaciar(cliente)
        nombre_modelo = flowplus_modelos.IMAGEN[modelo]["nombre"]
        flash(f"Generando la imagen con {nombre_modelo}{' · ' + aspect_ratio if aspect_ratio else ''}…" if lanzado
              else "Ya se estaba generando eso — espera a que termine.", "ok" if lanzado else "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", **campos)
    encolado = _encolar_director(cliente, cf_id)
    referencias_flowplus.vaciar(cliente)
    if encolado:
        flash("Armando el prompt con IA… en unos segundos aparece aquí para que lo revises y generes.", "ok")
        if aviso_duracion is not None:
            flash(f"{flowplus_modelos.VIDEO[modelo]['nombre']} llega a {aviso_duracion} s: se armará para {aviso_duracion} s.", "warn")
    else:
        flash("Ya se estaba armando ese prompt — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


def _encolar_director(cliente, cf_id, auto_lanzar=False, prioridad=flowplus_lanzar.PRIORIDAD_NORMAL):
    """Encola la compilación del prompt (gratis, idempotente: max_intentos=2)."""
    return trabajos.encolar(
        tareas_director.job_id(cliente, cf_id), "flowplus_director",
        {"cliente": cliente, "cf_id": cf_id, "auto_lanzar": bool(auto_lanzar), "prioridad": int(prioridad)},
        cliente=cliente, duracion_estimada=tareas_director.DURACION_ESTIMADA, etapas=tareas_director.ETAPAS_DIRECTOR,
        max_intentos=2, prioridad=prioridad,
    )


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/prompt", methods=["POST"])
def cf_guardar_prompt(cliente, cf_id):
    """Guarda las ediciones de la persona sobre el prompt A (lo que se manda)
    y el B. Solo en prompt_listo; un texto vacío no pisa nada. No llama a Claude."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "prompt_listo":
        flash("Ese prompt no se puede editar ahora.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    campos = {}
    a = (request.form.get("prompt_a") or "").strip()
    if a:
        campos["prompt_relleno"] = a
    b = (request.form.get("prompt_b") or "").strip()
    director_datos = dict(entry.get("director") or {})
    if b:
        director_datos["prompt_b"] = b
    if campos or b:
        director_datos["editado_en"] = datetime.now().isoformat(timespec="seconds")
        campos["director"] = director_datos
        creative_flow.actualizar(cliente, cf_id, **campos)
        flash("Prompt guardado. Ahora sí: genera cuando quieras.", "ok")
    else:
        flash("No había cambios que guardar.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/rearmar", methods=["POST"])
def cf_rearmar(cliente, cf_id):
    """Vuelve a pedirle los planos a Claude (gratis). Sobrescribe A y B.

    También rescata una sesión que quedó en prompt_pendiente sin trabajo vivo
    (el worker murió antes de que `tareas.director.interrumpida` la pasara a
    prompt_listo con el fallback) — mientras el director siga corriendo para
    ella, se sigue rechazando para no encolar una segunda compilación encima."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or (entry.get("tipo") or "video") == "imagen":
        flash("Esa sesión no se puede rearmar ahora.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    estado = entry.get("estado")
    puede_rearmar = estado in ("prompt_listo", "error") or (
        estado == "prompt_pendiente" and not trabajos.en_curso(tareas_director.job_id(cliente, cf_id)))
    if not puede_rearmar:
        flash("Esa sesión no se puede rearmar ahora.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", error=None)
    if _encolar_director(cliente, cf_id):
        flash("Rearmando el prompt con IA…", "ok")
    else:
        flash("Ya se estaba rearmando.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/sugerir_sonido", methods=["POST"])
def fp_sugerir_sonido(cliente):
    """Claude sugiere qué se oye en la escena (centavos). Solo texto: no genera nada."""
    from final_edition import sonido as sonido_mod
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": "Cuerpo inválido."}), 400
    escena = " ".join(str(cuerpo.get("escena") or "").split())
    if not escena:
        return jsonify({"error": "Escribe primero qué tiene que pasar en el video."}), 400
    e = cuerpo.get("enfoque")
    enfoque = e if isinstance(e, str) and e in flowplus_prompt.ENFOQUES else "producto"
    try:
        texto = sonido_mod.sugerir_descripcion(escena, enfoque)
    except Exception as e:
        return jsonify({"error": f"No se pudo sugerir ({type(e).__name__})."}), 502
    return jsonify({"sonido": texto})


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/generar_video", methods=["POST"])
def cf_generar_video(cliente, cf_id):
    """Reintento tras error, o sesiones viejas que quedaron en prompt_listo.
    Con `version_b=si` (solo video, y solo si el director dejó `prompt_b`) crea
    una sesión hija con esa versión (`creative_flow.duplicar`) y encola las dos."""
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        flash("No encontré esa sesión.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Guardia anti-reenvío: nunca disparar una segunda generación paga de un
    # video que ya se generó o se está generando.
    if entry.get("estado") not in ("prompt_listo", "error"):
        flash("Este video ya se generó o se está generando — no se puede volver a disparar.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not (entry.get("referencias_urls") or []):
        flash("Esta sesión no tiene imágenes de referencia — descártala y crea una nueva.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    nombre_modelo = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre", "el modelo")
    que = "la imagen" if (entry.get("tipo") or "video") == "imagen" else "el video"
    prompt_b = (entry.get("director") or {}).get("prompt_b")
    # Si ya existe una hija B (de un clic anterior, o de un lote), no se crea
    # otra aunque la casilla venga marcada.
    tiene_hija_b = any(e.get("derivado_de") == cf_id and e.get("variante") == "B" for e in data.values())
    quiere_b = request.form.get("version_b") == "si" and bool(prompt_b) and que == "el video" and not tiene_hija_b
    hija = None
    if quiere_b:
        # Dos clics casi simultáneos pueden leer el mismo entry.estado
        # "prompt_listo" antes de que el primero termine de escribir: este
        # chequeo, justo antes de crear la hija, es la segunda barrera (la
        # primera es el estado de arriba) para no duplicar la generación paga.
        if trabajos.en_curso(_job_id_creative_flow(cliente, cf_id)):
            flash(f"Ya se está generando {que} — espera a que termine.", "warn")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
        try:
            hija = creative_flow.duplicar(cliente, cf_id, prompt_relleno=prompt_b, variante="B")
        except Exception as e:
            flash(f"No se pudo crear la versión B: {e}. No se generó nada.", "error")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not _lanzar_video_cf(cliente, cf_id, entry):
        flash(f"Ya se está generando {que} — espera a que termine.", "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if hija:
        _lanzar_video_cf(cliente, hija, creative_flow.cargar(cliente)[hija])
        flash(f"Generando las versiones A y B con {nombre_modelo}…", "ok")
    else:
        flash(f"Generando {que} con {nombre_modelo}…", "ok")
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

    Excepción: los swaps y las piezas de CreativeFlowPlus ya corren en el worker
    (cola persistente). Si su job sigue vivo en la cola (trabajos.en_curso), no
    es huérfano — el worker puede estar generándolo — y se deja como está.
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
            for swap_id, entry in swaps_data.items():
                if entry.get("estado") == "generando":
                    if trabajos.en_curso(f"{cliente}__{swap_id}__swap"):
                        continue
                    entry["estado"] = "error"
                    entry["error"] = _MENSAJE_INTERRUMPIDO
                    tocado = True
            if tocado:
                swaps_mod.guardar(cliente, swaps_data)

            cf_data = creative_flow.cargar(cliente)
            tocado = False
            for cf_id, entry in cf_data.items():
                if entry.get("estado") == "video_generando":
                    if trabajos.en_curso(f"{cliente}__{cf_id}__creative_flow"):
                        continue
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

    # Experimentos "lanzando" viven en la base (no en JSON): si el proceso se
    # reinició a mitad de un lanzamiento y el job ya no está en la cola, el
    # experimento quedó pidiendo un trabajo que no va a volver — se marca en
    # error para que la persona pueda revisar Ads Manager y reintentar.
    try:
        with db.conectar() as con:
            filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
                db.experimento.c.legado.is_(False), db.experimento.c.estado == "lanzando")).all()
        for eid, cliente in filas:
            if trabajos.en_curso(tareas_exp.job_id_lanzar(cliente, eid)):
                continue
            experimentos.actualizar(cliente, eid, estado="error",
                                     error="Se interrumpió el lanzamiento; revisa Ads Manager y vuelve a intentar.")
    except Exception as e:
        print(f"[aviso] No pude reconciliar experimentos lanzando: {e}")


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
    # debug=True por defecto era aceptable mientras esto SOLO corría en
    # localhost — el debugger interactivo de Werkzeug permite ejecutar código
    # arbitrario a quien lo alcance, así que en cualquier servidor accesible
    # desde fuera tiene que estar apagado. FLASK_DEBUG=true en el .env lo
    # reactiva para seguir depurando en la laptop; el VPS nunca define esa
    # variable, así que ahí queda en False sin que nadie tenga que acordarse.
    debug = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
    app.run(host=HOST, port=PUERTO, debug=debug, use_reloader=False)
