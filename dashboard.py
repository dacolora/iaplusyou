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
import unicodedata
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
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, send_file, abort, session, Response, stream_with_context
from flask_babel import Babel, format_decimal, get_locale, gettext, ngettext
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from datetime import date, datetime

import estado as estado_mod
import prompts as prompts_mod
import marca as marca_mod
import conceptos_imagen
import catalogo_productos
import catalogo_vista
import swaps as swaps_mod
import bitacora
import informe
import mapa_corporal
import prompt_swap
import proyectos
import trabajos
import usuarios
import idiomas
import cuentas
import meta_conexion
import meta_agencia
import meta_errores
import flowplus_prompt
import plantillas_anuncio
import referencias_flowplus
import saldo
import materiales
import ediciones
import mi_musica
import audios
import referencias_link
import generador_prompts
from providers import image_provider
from providers import video_provider, wan3_client, flowplus_modelos
from providers import aspect_ratio as aspect_ratio_mod
import ads as ads_mod
from meta_ads import auth as meta_auth
from meta_ads import campaign as meta_campaign
import creative_flow
import doctrina
from doctrina import aprendizajes as doctrina_aprendizajes
from doctrina import revisor as doctrina_revisor
import flowplus_lanzar
import cola
import db
import derivaciones
import experimentos
import lanzador
import acciones
import decisor
import modos
import notificaciones
import organico
import propuestas
import cifrado
import conectores
import tiendas
import triple_whale
import triple_whale_tiendas
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
from tareas import doctrina as tareas_doctrina
from tareas import musica as tareas_musica
from tareas import audios as tareas_audios
from tareas import edicion as tareas_edicion
from tareas import triple_whale as tareas_tw
from final_edition import ETAPAS_FINAL, cortes as fe_cortes, mezcla as fe_mezcla, tipos as fe_tipos
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
# Vocabulario de la doctrina en palabras simples para los selectores de
# persona y producto (bloque 2 de la doctrina).
app.jinja_env.globals.update(doctrina.globales_plantilla())

# Idioma (spec 2026-09-26-idioma-y-modo-oscuro §B1): el español es la fuente;
# el inglés sale de translations/ (catalogo_i18n.py). idiomas.de_peticion elige.
app.config["BABEL_DEFAULT_LOCALE"] = "es"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = idiomas.DIR_TRADUCCIONES
Babel(app, locale_selector=idiomas.de_peticion)
app.jinja_env.filters["traducir"] = idiomas.traducir
# Errores de Meta: el JSON crudo de la Graph API se muestra en palabras de persona
# (`{{ e.error|error_meta(modo_meta) }}`); el crudo sigue en el detalle técnico.
app.jinja_env.filters["error_meta"] = meta_errores.explicar
# Selector de Crear y panel de Sprints agrupan los colores de un producto
# (spec 2026-09-28 §10.5) con esto en vez de `|groupby('producto_id')`: ver
# el docstring de la función para por qué.
app.jinja_env.filters["agrupar_por_producto"] = catalogo_productos.agrupar_por_producto


@app.url_defaults
def _version_estaticos(endpoint, values):
    """Cache-busting: url_for('static', filename=…) lleva ?v=<mtime del
    archivo>, así el navegador pide el CSS nuevo tras cada despliegue (Flask
    no manda max-age y el navegador reutiliza el viejo por heurística sobre
    Last-Modified). Un archivo que no existe se enlaza sin versión."""
    if endpoint != "static" or "v" in values or not values.get("filename"):
        return
    try:
        ruta = os.path.join(app.static_folder, values["filename"])
        values["v"] = int(os.stat(ruta).st_mtime)
    except OSError:
        pass


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

from referentes import rutas as referentes_rutas  # noqa: E402  (Blueprint de la pestaña Referentes)
app.register_blueprint(referentes_rutas.bp)

from triple_whale import rutas as triple_whale_rutas  # noqa: E402  (Blueprint de la pestaña Triple Whale)
from triple_whale import panel as triple_whale_panel  # noqa: E402  (la tienda según Triple Whale, en el Tablero)
from triple_whale import puente as triple_whale_puente  # noqa: E402  (una pieza de Crear nacida de una idea)
app.register_blueprint(triple_whale_rutas.bp)

from guiones import rutas as guiones_rutas  # noqa: E402  (Blueprint JSON del chat de Flow Plus en Crear)
app.register_blueprint(guiones_rutas.bp)

from guiones import rutas_pipeline as guiones_pipeline  # noqa: E402  (panel de guiones de Flow Plus)
app.register_blueprint(guiones_pipeline.bp)

from final_edition import rutas_editor  # noqa: E402  (vista previa del editor, capa 3)
app.register_blueprint(rutas_editor.bp)

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
            flash(gettext("Esa página es solo para el administrador."), "error")
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
    "cambiar_idioma",
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
        flash(gettext("Tu sesión se cerró; entra de nuevo."), "error")
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
            flash(gettext("Inicia sesión para entrar a este proyecto."), "error")
            return redirect(url_for("login"))
        flash(gettext("No tienes acceso a ese proyecto."), "error")
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


@app.context_processor
def _idioma_en_plantillas():
    """Idioma para las plantillas (spec 2026-09-26 §B3): `idioma_ui` (el de la
    petición, para <html lang> y el selector), `idioma_proyecto` en las páginas
    de un proyecto, y si se muestran el selector de Configuración y los enlaces
    «English · Español» antes del login (fases 2-5: solo el admin)."""
    sesion = _sesion()
    cliente = request.view_args.get("cliente") if request.view_args else None
    datos = {
        "idioma_ui": str(get_locale() or idiomas.DEFECTO),
        "idiomas_nombres": idiomas.NOMBRES,
        "idioma_selector_visible": bool(sesion) and (idiomas.ACTIVO_PARA_TODOS or sesion["rol"] == "admin"),
        "idioma_enlaces_publicos": idiomas.ACTIVO_PARA_TODOS and not sesion,
    }
    if cliente:
        datos["idioma_proyecto"] = idiomas.de_proyecto(cliente)
    return datos


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
    flash(gettext("Confirma tu correo primero (Configuración › Cuenta)."), "error")
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
    # Módulos ES del editor: se importan entre sí por ruta relativa, sin el
    # ?v= de _version_estaticos; sin revalidar, un despliegue dejaría módulos
    # viejos mezclados con nuevos. `no-cache` = siempre pregunta (304 barato).
    if request.path.startswith("/static/editor/"):
        resp.headers["Cache-Control"] = "no-cache"
    elif request.path.startswith("/static/") and request.args.get("v") and resp.status_code in (200, 304):
        # Con ?v=<mtime> (_version_estaticos) la URL cambia en cada despliegue,
        # así que el navegador puede guardar el archivo un año sin volver a
        # preguntar (antes revalidaba style.css, 150 KB, en cada página;
        # auditoría de rendimiento 2026-09-28).
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
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
    # etapa/mensaje/detalle son constantes N_(...) (tareas/flowplus.py,
    # tareas/director.py) o texto libre que no está en el catálogo — gettext
    # devuelve el msgid tal cual cuando no encuentra traducción, así que esto
    # nunca rompe un texto que no se tradujo. idiomas.traducir (no gettext
    # directo, revisión final fase 3 finding 3a): un campo en "" es habitual
    # (mensaje/detalle vacíos) y gettext("") devuelve la cabecera del .po, no
    # "" — traducir() deja vacío/None tal cual antes de llamar a gettext.
    salida = dict(info)
    for campo in ("etapa", "mensaje", "detalle"):
        if isinstance(salida.get(campo), str):
            salida[campo] = idiomas.traducir(salida[campo])
    return jsonify(salida)


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
        return False, gettext("No elegiste ningún archivo.")

    nombre = secure_filename(archivo.filename)
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        return False, gettext("Formato no soportado. Usa jpg, jpeg, png, webp, mp4, mov o webm.")

    carpeta = os.path.join(_client_dir(cliente), subcarpeta)
    os.makedirs(carpeta, exist_ok=True)
    local_path = os.path.join(carpeta, nombre)
    archivo.save(local_path)

    if ext in VIDEO_EXTS:
        try:
            r2_uploader.upload_video(local_path, f"clientes/{cliente}/{subcarpeta}/{nombre}")
        except Exception as e:
            return False, gettext("Se guardó localmente pero falló la subida del video a R2: %(error)s", error=e)

        frame_name = nombre + FRAME_SUFFIX
        frame_path = os.path.join(carpeta, frame_name)
        try:
            _extraer_frame(local_path, frame_path)
            r2_uploader.upload_image(frame_path, f"clientes/{cliente}/{subcarpeta}/{frame_name}")
            return True, gettext("Video subido y fotograma de referencia extraído: %(nombre)s", nombre=nombre)
        except Exception as e:
            return False, gettext(
                "El video %(nombre)s se subió, pero no pude extraer su fotograma de referencia "
                "(no se puede usar hasta resolver esto): %(error)s", nombre=nombre, error=e)
    else:
        try:
            r2_uploader.upload_image(local_path, f"clientes/{cliente}/{subcarpeta}/{nombre}")
            return True, gettext("Subido: %(nombre)s", nombre=nombre)
        except Exception as e:
            return False, gettext("Se guardó localmente pero falló la subida a R2: %(error)s", error=e)


def _eliminar_asset(cliente, subcarpeta, nombre):
    """Borra un archivo ya subido (imagen o video, más su .frame.jpg si aplica)
    local y de R2. No falla si alguna de las dos copias ya no existía.
    Devuelve (ok, mensaje) — solo `eliminar_logo` usa el mensaje; los demás
    llamadores flashean el suyo propio y lo ignoran."""
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
    return True, gettext("Eliminado: %(nombre)s", nombre=nombre)


@app.route("/cliente/<cliente>/personaje/subir", methods=["POST"])
def subir_personaje(cliente):
    ok, mensaje = _subir_asset(cliente, "personajes", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/personaje/<nombre>/eliminar", methods=["POST"])
def eliminar_personaje(cliente, nombre):
    _eliminar_asset(cliente, "personajes", secure_filename(nombre))
    flash(gettext("Eliminado: %(nombre)s", nombre=nombre), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/escena/subir", methods=["POST"])
def subir_escena(cliente):
    ok, mensaje = _subir_asset(cliente, "escenas", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/escena/<nombre>/eliminar", methods=["POST"])
def eliminar_escena(cliente, nombre):
    _eliminar_asset(cliente, "escenas", secure_filename(nombre))
    flash(gettext("Eliminado: %(nombre)s", nombre=nombre), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/producto_referencia/subir", methods=["POST"])
def subir_producto_referencia(cliente):
    ok, mensaje = _subir_asset(cliente, "productos_referencia", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/producto_referencia/<nombre>/eliminar", methods=["POST"])
def eliminar_producto_referencia(cliente, nombre):
    _eliminar_asset(cliente, "productos_referencia", secure_filename(nombre))
    flash(gettext("Eliminado: %(nombre)s", nombre=nombre), "ok")
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
        flash(gettext("%(n)s logo(s) guardado(s). Se usan como referencia en cada generación de FlowPlus.", n=ok_n), "ok")
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
        flash(gettext("Sube al menos una referencia de marca (imagen o video) primero."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    job_id = _job_id_marca(cliente)

    def trabajo():
        guia = generador_prompts.analizar_marca(urls, idioma=idiomas.de_proyecto(cliente))
        data = marca_mod.cargar(cliente)
        data["guia_estilo"] = guia
        marca_mod.guardar(cliente, data)
        return idiomas.N_("Guía de estilo generada.")

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=15):
        flash(gettext("Analizando referencias de marca…"), "ok")
    else:
        flash(gettext("Ya se está analizando — espera a que termine."), "warn")
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
    flash(gettext("Identidad de marca guardada."), "ok")
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


# Documentos legales completos en los dos idiomas (spec 2026-09-26 §Task 4):
# textos largos, no van al catálogo de catalogo_i18n.py — cada ruta elige con
# str(get_locale()). El español es idéntico al que había antes de esta tarea.
_PRIVACIDAD_HTML = {
    "es": """
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
""",
    "en": """
<p>Creatv Machine (creatvmachine.com) is a platform for businesses to create content with artificial
intelligence and publish or advertise it on their own social media accounts. This policy explains what data we
process when you connect your Meta account (Facebook and Instagram) and how we protect it.</p>
<h3>Data controller</h3>
<p>Daniel Alejandro Colorado Gaviria — Creatv Machine, Envigado, Colombia. Contact: dacoloradog@gmail.com.</p>
<h3>What data we receive from Meta</h3>
<ul>
<li>Your name and your Facebook user identifier (to know who authorized the connection).</li>
<li>The list of ad accounts, Facebook Pages and Instagram accounts you manage, so you can
choose which one to connect to the project.</li>
<li>A system access token for the chosen ad account and Page.</li>
<li>Data about your ads and their results (impressions, reach, clicks, spend, conversions) and, when you
publish organic content, confirmation of the publication.</li>
</ul>
<h3>What we use it for</h3>
<ul>
<li>Creating and managing campaigns, ad sets and ads in <strong>your</strong> ad account,
always at your request from the platform: no ad is created or activated unless you ask for it.</li>
<li>Showing you your ads' results inside the platform.</li>
<li>Publishing the content you approve to your Facebook Page and your Instagram.</li>
</ul>
<p>We don't use your data for our own advertising, we don't sell it or share it with third parties, and we
don't use it to train artificial intelligence models.</p>
<h3>Where and how it's stored</h3>
<p>Tokens and the identifiers of your assets are stored encrypted in transit (HTTPS) and with restricted
permissions on our server in the European Union (Hetzner, Nuremberg). Only the platform's process
can read them; they're never shown on screen or logged.</p>
<h3>How long</h3>
<p>As long as the project has Meta connected. Clicking “Disconnect” on the platform immediately deletes
the token and the identifiers. You can also revoke access from Facebook: Settings › Business Integrations,
or Settings › Apps and Websites.</p>
<h3>Data deletion</h3>
<p>For us to delete all the data associated with your Meta account, write to us at dacoloradog@gmail.com
stating the project's name; we do it within a maximum of 7 days and confirm it by email.</p>
<h3>Your rights</h3>
<p>You can request access, correction or deletion of your data at any time at the same email address.
We comply with Colombia's Law 1581 of 2012 on personal data protection and Meta's platform
policies.</p>
""",
}

_TERMINOS_HTML = {
    "es": """
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
""",
    "en": """
<p>By using Creatv Machine you accept these terms.</p>
<h3>The service</h3>
<p>Creatv Machine generates images and videos with artificial intelligence from the references you upload,
and lets you publish or advertise them on your own social media accounts. You decide what gets generated,
what gets published and what gets advertised: every action with a cost or a public effect requires your
confirmation.</p>
<h3>Your content</h3>
<p>The references you upload and the generated content are yours. You declare that you have the right to use
the images, videos, brands and products you upload. Don't upload third-party content without authorization.</p>
<h3>Meta accounts and other platforms</h3>
<p>By connecting a Meta account you act on behalf of that account and are responsible for the ads and
posts you order from the platform, including their budget. Comply with Meta's advertising
policies.</p>
<h3>Costs</h3>
<p>AI generations have a cost that's shown before generating. Ads are paid
directly to Meta from your ad account.</p>
<h3>Liability</h3>
<p>The service is provided “as is”. We don't guarantee advertising results or that an AI model will always
produce the expected result. We're not responsible for ads rejected by Meta or for changes to
third-party platforms.</p>
<h3>Contact</h3>
<p>Daniel Alejandro Colorado Gaviria — Creatv Machine, Envigado, Colombia. dacoloradog@gmail.com.</p>
""",
}


@app.route("/privacidad")
def privacidad():
    """Pública. Es la URL que exige Meta (App Review) y que cualquiera puede leer."""
    return render_template("legal.html", titulo=gettext("Política de privacidad"),
                           actualizado=gettext("12 de septiembre de 2026"),
                           cuerpo=_PRIVACIDAD_HTML[str(get_locale())])


@app.route("/terminos")
def terminos():
    return render_template("legal.html", titulo=gettext("Términos del servicio"),
                           actualizado=gettext("12 de septiembre de 2026"),
                           cuerpo=_TERMINOS_HTML[str(get_locale())])


@app.route("/eliminar-datos")
def eliminar_datos():
    """URL de instrucciones de eliminación de datos que pide Meta."""
    cuerpo = {
        "es": """<p>Para eliminar los datos que Creatv Machine guarda de tu cuenta de Meta:</p>
<ol><li>Entra a tu proyecto en app.creatvmachine.com › FlowMarketing › <strong>Desconectar</strong>: se borran el token
y los identificadores de tu cuenta publicitaria, Página e Instagram al instante.</li>
<li>Si prefieres, escribe a dacoloradog@gmail.com con el nombre de tu proyecto y lo eliminamos en máximo 7 días,
con confirmación por correo.</li></ol>
<p>También puedes revocar el acceso desde Facebook: Configuración › Apps y sitios web › Creatv Machine › Eliminar.</p>""",
        "en": """<p>To delete the data Creatv Machine stores about your Meta account:</p>
<ol><li>Go to your project at app.creatvmachine.com › FlowMarketing › <strong>Disconnect</strong>: the token
and the identifiers of your ad account, Page and Instagram are deleted instantly.</li>
<li>If you prefer, write to dacoloradog@gmail.com with your project's name and we'll delete it within 7 days,
confirmed by email.</li></ol>
<p>You can also revoke access from Facebook: Settings › Apps and Websites › Creatv Machine › Remove.</p>""",
    }[str(get_locale())]
    return render_template("legal.html", titulo=gettext("Eliminación de datos"),
                           actualizado=gettext("12 de septiembre de 2026"), cuerpo=cuerpo)


@app.route("/l/<cliente>")
def landing_cliente(cliente):
    """Página pública de destino de un proyecto (clientes/<c>/landing.json).
    Sirve de landing para anuncios cuando el cliente no tiene web propia —
    p. ej. una app, porque Meta no acepta el link a la tienda con Tráfico.
    Sale en el idioma DEL PROYECTO (`idiomas.de_proyecto`), no en el de quien
    la abre: es la única página pública que un cliente ve, y sus visitantes
    esperan el idioma del anuncio que la trajo, no el de su navegador."""
    ruta = os.path.join(BASE_DIR, "clientes", secure_filename(cliente), "landing.json")
    if not os.path.isfile(ruta):
        abort(404)
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    idioma = idiomas.de_proyecto(secure_filename(cliente))
    with idiomas.en_idioma(idioma):
        return render_template("landing_cliente.html", l=datos, idioma_landing=idioma)


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
    está verificado. Sin contraseña (usuarios.obtener la quita).
    `confirmar_verificado_msg` viaja ya traducido (gettext de Python, no el
    `_()` de Jinja) para que la plantilla solo lo pase por `|tojson`: el
    `_()` de Jinja escapa HTML en las variables interpoladas (autoescape +
    newstyle gettext), y ese escape sobrevive dentro de la cadena JS que arma
    tojson — un usuario con una comilla (ver test_rutas_cuentas.py) rompía el
    confirm() con la entidad &#39; en vez de la comilla escapada por JSON."""
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
            "confirmar_verificado_msg": gettext(
                "¿Marcar a %(usuario)s como verificado sin que abra el enlace del correo?", usuario=nombre),
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
        flash(gettext("Usuario o contraseña incorrectos."), "error")
        return render_template("login.html"), 401

    _abrir_sesion(usuario, entry)
    if entry["rol"] == "admin":
        return redirect(url_for("panel"))
    return redirect(url_for("ver_cliente", cliente=entry["cliente"]))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash(gettext("Sesión cerrada."), "ok")
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
        return _error(gettext("Ponle un nombre a la empresa."))
    if not usuario or not password:
        return _error(gettext("Elige un usuario y una contraseña para entrar a tu proyecto."))
    error_usuario = usuarios.validar_usuario(usuario)
    if error_usuario:
        return _error(error_usuario)
    correo = usuarios.validar_correo(correo_crudo)
    if not correo:
        return _error(gettext("Escribe un correo válido: ahí te llega el enlace para confirmar la cuenta y recuperar la contraseña."))
    error_password = usuarios.validar_password(password)
    if error_password:
        return _error(error_password)
    if usuarios.existe(usuario):
        return _error(gettext("Ya existe un usuario '%(usuario)s' — elige otro.", usuario=usuario))
    if usuarios.por_correo(correo):
        return _error(gettext("Ese correo ya tiene una cuenta. Entra con ella o recupera la contraseña."))

    cid = secure_filename(nombre.lower().replace(" ", "_"))
    if not cid:
        return _error(gettext("Ese nombre no genera un identificador de proyecto válido."))
    if cid in estado_mod.listar_clientes():
        return _error(gettext("Ya existe un proyecto con el identificador '%(cid)s' — elige otro nombre.", cid=cid))

    # Tope por IP al alta en sí (5 por hora): sin él, un script crea cuentas y
    # carpetas sin fin y manda un correo de verificación por cada una.
    if not cuentas.limite_ok(f"alta:ip:{_ip_cliente() or 'desconocida'}"):
        flash(gettext("Demasiados registros seguidos desde esta conexión. Espera un rato e inténtalo de nuevo."), "error")
        return render_template("index.html", form=form), 429

    try:
        usuarios.crear(usuario, password, "cliente", cliente=cid, correo=correo)
    except ValueError as e:
        return _error(str(e))
    os.makedirs(os.path.join(BASE_DIR, "clientes", cid), exist_ok=True)
    proyectos.guardar_nombre(cid, nombre)

    if idiomas.ACTIVO_PARA_TODOS:
        elegido = idiomas.normalizar(request.cookies.get(idiomas.COOKIE)) or idiomas.DEFECTO
        idiomas.guardar_de_usuario(usuario, elegido)
        idiomas.guardar_de_proyecto(cid, elegido)

    # Alta con sesión inmediata: quien crea el proyecto queda logueado en su
    # propio proyecto de una vez, sin tener que ir a /login aparte.
    _abrir_sesion(usuario, usuarios.obtener(usuario) or {"rol": "cliente", "cliente": cid})

    if not cuentas.smtp_configurado():
        flash(gettext("Proyecto '%(nombre)s' creado. El servidor no tiene correo configurado, así que no pudimos "
                      "enviarte el enlace de confirmación: avisa al administrador.", nombre=nombre), "warn")
    elif not _limite_correo("verif", correo):
        flash(gettext("Proyecto '%(nombre)s' creado. Espera un momento y pide el correo de confirmación desde "
                      "el aviso de arriba.", nombre=nombre), "warn")
    elif cuentas.enviar_verificacion(usuario, correo, _url_base(), ip=_ip_cliente()):
        flash(gettext("Proyecto '%(nombre)s' creado. Te mandamos un correo a %(correo)s para confirmar tu cuenta.",
                      nombre=nombre, correo=correo), "ok")
    else:
        flash(gettext("Proyecto '%(nombre)s' creado, pero no pudimos enviar el correo de confirmación. "
                      "Reenvíalo desde el aviso de arriba en un momento.", nombre=nombre), "warn")
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
        flash(gettext("Ese enlace de verificación no sirve: ya se usó o venció. Pide uno nuevo desde tu cuenta."), "error")
        return _volver_cuenta() if sesion else redirect(url_for("login"))
    usuario = resultado["usuario"]
    try:
        usuarios.actualizar(usuario, correo=resultado["correo"], correo_verificado=True)
    except ValueError as e:
        flash(gettext("No pude confirmar el correo: %(error)s", error=str(e)), "error")
        return _volver_cuenta() if sesion else redirect(url_for("login"))
    flash(gettext("Correo confirmado. ¡Gracias!"), "ok")
    # Con sesión abierta (la suya o la de otro usuario en este navegador) se
    # vuelve a su cuenta; sin sesión, al login.
    return _volver_cuenta() if sesion else redirect(url_for("login"))


@app.route("/reenviar-verificacion", methods=["POST"])
def reenviar_verificacion():
    if not _mismo_origen():
        abort(403)
    sesion = _sesion()
    if not sesion:
        flash(gettext("Inicia sesión para reenviar la verificación."), "error")
        return redirect(url_for("login"))
    entry = usuarios.obtener(sesion["usuario"])
    if not entry or not entry.get("correo"):
        flash(gettext("Primero escribe tu correo en Configuración › Cuenta."), "error")
        return _volver_cuenta()
    if entry.get("correo_verificado"):
        flash(gettext("Tu correo ya está confirmado."), "ok")
        return _volver_cuenta()
    if not cuentas.smtp_configurado():
        flash(gettext("El servidor no tiene correo configurado; avisa al administrador para que confirme tu cuenta."), "warn")
        return _volver_cuenta()
    if not _limite_correo("verif", entry["correo"]):
        flash(gettext("Espera un momento antes de pedir otro correo de verificación."), "warn")
        return _volver_cuenta()
    cuentas.enviar_verificacion(sesion["usuario"], entry["correo"], _url_base(), ip=_ip_cliente())
    flash(gettext("Si %(correo)s es correcto, te llega el enlace en unos minutos (revisa también el spam).",
                  correo=entry["correo"]), "ok")
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
    flash(gettext("Si ese correo está registrado, te llegará un enlace para restablecer la contraseña "
                  "(vence en 1 hora; revisa también el spam)."), "ok")
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
        error = gettext("Las dos contraseñas no coinciden.")
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
    flash(gettext("Contraseña cambiada. Entra con la nueva."), "ok")
    return redirect(url_for("login"))


@app.route("/cuenta/correo", methods=["POST"])
def cuenta_correo():
    """Pone o cambia el correo de la cuenta (pide la contraseña actual). El
    correo nuevo queda sin verificar hasta abrir el enlace."""
    sesion = _sesion()
    if not sesion:
        flash(gettext("Inicia sesión para cambiar tu correo."), "error")
        return redirect(url_for("login"))
    usuario = sesion["usuario"]
    if not usuarios.verificar(usuario, request.form.get("password") or ""):
        flash(gettext("La contraseña actual no es correcta."), "error")
        return _volver_cuenta()
    correo = usuarios.validar_correo(request.form.get("correo") or "")
    if not correo:
        flash(gettext("Escribe un correo válido."), "error")
        return _volver_cuenta()
    actual = usuarios.obtener(usuario) or {}
    if actual.get("correo") == correo and actual.get("correo_verificado"):
        flash(gettext("Ese ya es tu correo y está confirmado."), "ok")
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
        flash(gettext("Correo guardado: %(correo)s. El servidor no tiene correo configurado, así que no pudimos "
                      "enviarte el enlace de confirmación: avisa al administrador.", correo=correo), "warn")
    elif not _limite_correo("verif", correo):
        flash(gettext("Correo guardado: %(correo)s. Espera un momento antes de pedir el enlace de confirmación.",
                      correo=correo), "warn")
    else:
        cuentas.enviar_verificacion(usuario, correo, _url_base(), ip=_ip_cliente())
        flash(gettext("Correo guardado. Si %(correo)s es correcto, te llega el enlace de confirmación en unos minutos.",
                      correo=correo), "ok")
    return _volver_cuenta()


@app.route("/cuenta/password", methods=["POST"])
def cuenta_password():
    """Cambia la contraseña con la actual + nueva + confirmación. Sube
    session_version (las demás sesiones se cierran) y refresca la de este
    navegador para que siga abierta."""
    sesion = _sesion()
    if not sesion:
        flash(gettext("Inicia sesión para cambiar tu contraseña."), "error")
        return redirect(url_for("login"))
    usuario = sesion["usuario"]
    if not usuarios.verificar(usuario, request.form.get("password_actual") or ""):
        flash(gettext("La contraseña actual no es correcta."), "error")
        return _volver_cuenta()
    nueva = request.form.get("password") or ""
    error = usuarios.validar_password(nueva)
    if not error and nueva != (request.form.get("confirmacion") or ""):
        error = gettext("Las dos contraseñas no coinciden.")
    if error:
        flash(error, "error")
        return _volver_cuenta()
    try:
        session["sv"] = usuarios.cambiar_password(usuario, nueva)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_cuenta()
    flash(gettext("Contraseña cambiada. Las demás sesiones abiertas con la anterior se cerraron."), "ok")
    return _volver_cuenta()


@app.route("/cliente/<cliente>/cfg_idioma", methods=["POST"])
def cfg_idioma(cliente):
    """Selector de idioma (spec 2026-09-26 §B3). alcance=cuenta: el idioma de
    quien está en sesión y, si es un cliente, también el de su proyecto (para él
    son una sola cosa). alcance=proyecto: solo admin. Mientras
    idiomas.ACTIVO_PARA_TODOS sea False, solo el admin puede usarlo."""
    if not _mismo_origen():
        abort(403)
    sesion = _sesion()
    es_admin = sesion["rol"] == "admin"
    if not es_admin and not idiomas.ACTIVO_PARA_TODOS:
        abort(403)
    idioma = idiomas.normalizar(request.form.get("idioma"))
    alcance = request.form.get("alcance") or "cuenta"
    if idioma is None or alcance not in ("cuenta", "proyecto") or (alcance == "proyecto" and not es_admin):
        abort(400)
    if alcance == "proyecto":
        idiomas.guardar_de_proyecto(cliente, idioma)
        flash(gettext("Idioma del proyecto guardado."), "ok")
    else:
        idiomas.guardar_de_usuario(sesion["usuario"], idioma)
        if not es_admin:
            idiomas.guardar_de_proyecto(cliente, idioma)
        with idiomas.en_idioma(idioma):
            flash(gettext("Idioma guardado."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/idioma/<codigo>")
def cambiar_idioma(codigo):
    """Enlaces «English · Español» antes del login: guarda la cookie y vuelve a
    `next` solo si es una ruta de este sitio (nunca a otro dominio)."""
    idioma = idiomas.normalizar(codigo)
    if idioma is None:
        abort(404)
    destino = request.args.get("next") or ""
    partes = urlsplit(destino)
    if (not destino.startswith("/") or destino.startswith("//") or "\\" in destino
            or any(ord(c) < 0x20 or ord(c) == 0x7f for c in destino)
            or partes.scheme or partes.netloc):
        destino = url_for("index")
    resp = redirect(destino)
    resp.set_cookie(idiomas.COOKIE, idioma, max_age=365 * 24 * 3600, samesite="Lax", httponly=True,
                    secure=bool(app.config.get("SESSION_COOKIE_SECURE")))
    return resp


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
    flash(gettext("Usuario '%(usuario)s' marcado como verificado.", usuario=usuario), "ok")
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
@trabajos.con_vivos_precargados
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
    # de _meta_conectar.html (en Experimentos) es «Gestionado por Creatv», sin
    # app ni botón de conectar.
    datos_meta = meta_conexion.cargar(cliente) or {}
    modo_meta = meta_conexion.MODO_AGENCIA if datos_meta.get("modo") == meta_conexion.MODO_AGENCIA else "propia"
    agencia_conectada = meta_agencia.conectada() if modo_meta == meta_conexion.MODO_AGENCIA else False
    meta_detalle = meta_conexion._detalle(datos_meta)
    # El cliente elige cómo conectar (spec 2026-09-20): forma = intención,
    # modo = estado real. Con conexión y sin forma, la forma es el modo.
    meta_forma = proyectos.meta_forma(cliente)
    if modo_meta == meta_conexion.MODO_AGENCIA:
        meta_forma = "agencia"
    elif meta_forma is None and (datos_meta.get("token") or meta_app):
        # Conectado o con app registrada antes de que existiera la elección: propia.
        meta_forma = "propia"
    agencia_disponible = meta_agencia.conectada()
    agencia_publica = meta_agencia.publica() if agencia_disponible else None  # id y nombre del Business, nunca token
    agencia_pendiente = meta_forma == "agencia" and modo_meta != meta_conexion.MODO_AGENCIA
    agencia_solicitud = meta_agencia.solicitud(cliente) if agencia_pendiente else None
    agencia_portafolio = agencia_activos = agencia_activos_error = None
    if agencia_pendiente and agencia_disponible:
        agencia_portafolio = _portafolio_valido(request.args.get("agencia_portafolio"))
        if agencia_portafolio:
            try:
                agencia_activos = meta_agencia.activos_de_portafolio(
                    agencia_portafolio, cliente=cliente, forzar=request.args.get("refrescar") == "1")
            except meta_conexion.MetaConexionError as e:
                agencia_activos_error = cola.sin_token(str(e))
    motivo_bloqueo_forma = None
    if meta_conectado or modo_meta == meta_conexion.MODO_AGENCIA:
        motivo_bloqueo_forma = _bloqueo_cambio_forma(cliente, experimentos_lista=experimentos_exp)
    estado_pixel = meta_conexion.estado_pixel(cliente, solo_cache=True) if meta_conectado else None
    tiendas_cliente = tiendas.listar(cliente)
    triple_whale_conectado = triple_whale_tiendas.obtener(cliente)
    # Catálogo (spec 2026-09-28): la galería y la ficha llegan por fragmento;
    # la página solo trae contadores por categoría y lo que Crear necesita.
    activos_producto = _productos_con_uso(cliente)
    productos_catalogo = catalogo_productos.listar_productos(cliente, "producto")
    _asegurar_filas_producto(cliente, productos_catalogo)
    n_por_categoria = {cid: (len(productos_catalogo) if cid == "producto" else len(catalogo_productos.listar_productos(cliente, cid)))
                       for cid in catalogo_productos.CATEGORIAS}
    # Una sola consulta (solo caché) para atribución y objetivo sugeridos.
    atribucion_sug = experimentos.atribucion_sugerida(cliente)
    # Bloque 7: canales orgánicos del proyecto, publicaciones por pieza (UNA
    # consulta) y qué piezas tienen una publicación orgánica corriendo en el
    # worker (UNA consulta a la cola, como _trabajos_productos).
    # Gasto real (Task 3): el tablero se calcula UNA vez (cacheado) y de ahí
    # sale la pauta por moneda; la generación viene de la tabla `gasto`.
    tablero_ctx = _contexto_tablero(cliente)
    gasto_ctx = _contexto_gasto(cliente, tablero_ctx)

    cf_items = _creative_flow_items(cliente)
    # `precios` ya viene en gasto_ctx (el mismo _precios_pagina()): sin quitarlo
    # render_template lo recibiría dos veces.
    fe_ctx = _contexto_final_edition(cliente)
    fe_ctx.pop("precios", None)
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
        # Solo el admin ve el informe (Configuración › Puesta a punto) y armarlo
        # corre git y lee todo el repo (~100 ms): a un cliente no se le cobra.
        informe=informe.completo(cliente) if session.get("rol") == "admin" else None,
        productos=activos_producto,
        categorias=catalogo_productos.CATEGORIAS,
        activos_por_categoria={cid: (activos_producto if cid == "producto" else catalogo_productos.listar(cliente, cid)) for cid in catalogo_productos.CATEGORIAS},
        n_por_categoria=n_por_categoria,
        monedas_catalogo=sorted(PRESUPUESTO_MINIMO_DIARIO),
        moneda_catalogo=_moneda_por_defecto(cliente),
        etiquetas_fuente=ETIQUETAS_FUENTE,
        tipos_producto=prompt_swap.TIPOS,
        zonas_cuerpo=mapa_corporal.ZONAS,
        presets_cuerpo=mapa_corporal.PRESETS,
        etiquetas_presets=mapa_corporal.ETIQUETAS_PRESETS,
        nombre_proyecto=proyectos.nombre_visible(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
        creative_flow_items=cf_items,
        **_listas_crear_final(cf_items),
        preferencias_flowplus=proyectos.preferencias_flowplus(cliente),
        preferencias_sonido=proyectos.preferencias_sonido(cliente),
        aviso_saldo=saldo.vigente("wavespeed"),
        fp_prefill=_prefill_para(cliente),
        logos=_logos(cliente),
        referencias_bandeja=referencias_flowplus.listar(cliente),
        trabajo_link={"job_id": _job_id_link(cliente)} if trabajos.en_curso(_job_id_link(cliente)) else None,
        modelos_flowplus_video=flowplus_modelos.VIDEO,
        duraciones_crear=flowplus_modelos.DURACIONES_CREAR,
        formatos_nombres=flowplus_modelos.FORMATOS_NOMBRES,
        plantillas_anuncio=plantillas_anuncio.PLANTILLAS,
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
        meta_forma=meta_forma,
        agencia_disponible=agencia_disponible,
        agencia_publica=agencia_publica,
        agencia_solicitud=agencia_solicitud,
        agencia_portafolio=agencia_portafolio,
        agencia_activos=agencia_activos,
        agencia_activos_error=agencia_activos_error,
        motivo_bloqueo_forma=motivo_bloqueo_forma,
        meta_redirect_uri=os.environ.get("META_REDIRECT_URI", ""),
        **fe_ctx,
        **_contexto_audios(cliente),
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
        aprendizajes_exp=proyectos.aprendizajes(cliente),
        precio_diagnostico=gastos.estimar("diagnostico_pieza")["texto"],
        modos_exp=modos.MODOS,
        nombres_exp={e["id"]: e["nombre"] for e in experimentos_exp},
        etiquetas_exp={
            "estado": experimentos.ETIQUETAS_ESTADO, "pieza": experimentos.ETIQUETAS_ESTADO_PIEZA,
            "veredicto": experimentos.ETIQUETAS_VEREDICTO, "tipo": experimentos.ETIQUETAS_TIPO_PIEZA,
            "derivacion": derivaciones.ETIQUETAS_ESTADO, "clase": derivaciones.ETIQUETAS_CLASE,
            "variante": derivaciones.ETIQUETAS_VARIANTE, "atribucion": experimentos.ETIQUETAS_ATRIBUCION,
            "accion": acciones.ETIQUETAS_ACCION, "tipo_derivacion": derivaciones.ETIQUETAS_TIPO,
            "evento": experimentos.ETIQUETAS_EVENTO,
        },
        meses_cortos=idiomas.meses_cortos(),
        tiendas_cliente=tiendas_cliente,
        triple_whale_conectado=triple_whale_conectado,
        tw_modelos=triple_whale.MODELOS, tw_ventanas=triple_whale.VENTANAS, tw_monedas=triple_whale.MONEDAS,
        trabajos_prod=_trabajos_productos(cliente, tiendas_cliente),
        precio_pedidos=gastos.estimar("pedidos_producto")["texto"],
        estado_pixel=estado_pixel,
        meta_conectado=meta_conectado,
        atribucion_sugerida=atribucion_sug,
        atribuciones_exp=experimentos.ATRIBUCIONES,
        pedidos_por_exp=tiendas.pedidos_por_experimento(cliente),
        cifrado_ok=cifrado.disponible(),
        meli_configurado=bool((os.environ.get("MELI_APP_ID") or "").strip()),
        tipos_tienda=conectores.TIPOS_CONECTABLES,
        llaves=_llaves_visibles(_estado_llaves(url_for("meli_callback", _external=True)), session.get("rol")),
        columnas_csv=conector_csv.COLUMNAS_AYUDA,
        tablero=tablero_ctx,
        **gasto_ctx,
        **sprints_rutas.contexto(cliente),
        **nicho_rutas.contexto(cliente),
        **referentes_rutas.contexto(cliente),
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
        "nombre": idiomas.N_("Anthropic (guiones y prompts)"),
        "para_que": idiomas.N_("Escribe los 5 prompts por idea y los guiones de las finales."),
        "costo": idiomas.N_("Se paga por uso: centavos por guion."),
        "url": "https://console.anthropic.com/settings/keys",
        "url_texto": "console.anthropic.com › API keys",
        "variables": ["ANTHROPIC_API_KEY"],
        "nota": idiomas.N_("Sin ella no hay prompts ni guiones."),
        "pasos": [
            idiomas.N_("Entra a console.anthropic.com e inicia sesión (o crea la cuenta de la empresa)."),
            idiomas.N_("En «Billing» carga saldo o pon una tarjeta: sin saldo la llave existe pero no responde."),
            idiomas.N_("Ve a «API keys» › «Create key», ponle un nombre (por ejemplo «creatv») y cópiala: solo se muestra una vez."),
            idiomas.N_("Pégala como ANTHROPIC_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "fal",
        "nombre": idiomas.N_("fal.ai (voz y música)"),
        "para_que": idiomas.N_("Voz en off (ElevenLabs), subtítulos por palabra (Whisper) y música (Stable Audio) de las finales."),
        "costo": idiomas.N_("Se paga por uso: alrededor de $0.05 por final."),
        "url": "https://fal.ai/dashboard/keys",
        "url_texto": "fal.ai › Dashboard › Keys",
        "variables": ["FAL_KEY"],
        "nota": idiomas.N_("Sin ella las finales salen sin voz ni música."),
        "pasos": [
            idiomas.N_("Regístrate en fal.ai (con Google o GitHub; no pide verificación de negocio)."),
            idiomas.N_("En «Billing» agrega una tarjeta o saldo prepago."),
            idiomas.N_("Ve a «Keys» › «Add key», elige alcance «API» y copia la llave."),
            idiomas.N_("Pégala como FAL_KEY en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "higgsfield",
        "nombre": idiomas.N_("Higgsfield (video e imagen)"),
        "para_que": idiomas.N_("Genera la imagen candidata y el video de cada pieza."),
        "costo": idiomas.N_("Por créditos: ~1.5 por imagen y ~8 por video; se compran por paquetes."),
        "url": "https://higgsfield.ai/",
        "url_texto": "higgsfield.ai › API",
        "variables": ["HF_API_KEY_ID", "HF_API_KEY_SECRET"],
        "nota": idiomas.N_("Sin ella no se generan piezas."),
        "pasos": [
            idiomas.N_("Inicia sesión en higgsfield.ai y compra un paquete de créditos en «Billing»."),
            idiomas.N_("Abre la sección «API» (o «Developers») de tu cuenta y crea una llave nueva."),
            idiomas.N_("Copia los dos valores: el Key ID y el Key Secret (el secreto solo se muestra una vez)."),
            idiomas.N_("Pégalos como HF_API_KEY_ID y HF_API_KEY_SECRET en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "r2",
        "nombre": idiomas.N_("Cloudflare R2 (almacenamiento)"),
        "para_que": idiomas.N_("Guarda cada imagen y video generado y les da una URL pública permanente."),
        "costo": idiomas.N_("Casi gratis: 10 GB al mes sin costo y sin cobro por descarga."),
        "url": "https://dash.cloudflare.com/?to=/:account/r2",
        "url_texto": "dash.cloudflare.com › R2 › Manage API tokens",
        "variables": ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL"],
        "nota": idiomas.N_("Sin ella los videos no tienen URL pública y Meta no puede usarlos."),
        "pasos": [
            idiomas.N_("En dash.cloudflare.com entra a «R2» y crea un bucket (ese nombre es R2_BUCKET_NAME)."),
            idiomas.N_("En «Settings» del bucket activa «Public access» (r2.dev o un dominio propio): esa URL es R2_PUBLIC_BASE_URL."),
            idiomas.N_("Vuelve a R2 › «Manage R2 API tokens» › «Create API token» con permiso «Object Read & Write»."),
            idiomas.N_("Copia el Access Key ID y el Secret Access Key; el Account ID está en la barra lateral de R2."),
            idiomas.N_("Pega las cinco variables en el .env del servidor y reinicia."),
        ],
    },
    {
        "id": "smtp",
        "nombre": idiomas.N_("Correo de la plataforma (cuentas y avisos)"),
        "para_que": idiomas.N_("Manda el enlace para confirmar el correo de cada cuenta y el de recuperar la contraseña; "
                    "también los avisos (propuestas pendientes, ganadores, rechazos de Meta, lanzamientos fallidos)."),
        "costo": idiomas.N_("Depende del proveedor de correo; con una cuenta normal no cuesta."),
        "url": "https://support.google.com/accounts/answer/185833",
        "url_texto": idiomas.N_("Google › Contraseñas de aplicación"),
        "variables": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL"],
        "nota": idiomas.N_("Sin esto nadie puede confirmar su correo ni recuperar la contraseña solo (el administrador "
                "tiene que marcar las cuentas a mano en el panel) y los avisos solo quedan en la bitácora."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Elige la cuenta que va a enviar (Gmail, Outlook o el correo del dominio)."),
            idiomas.N_("Si es Gmail: en myaccount.google.com › Seguridad activa la «Verificación en dos pasos» y luego, "
            "en «Contraseñas de aplicación», crea una para «Creatv»: los 16 caracteres que te da son SMTP_PASS "
            "(no la contraseña normal de la cuenta). SMTP_USER es la dirección completa y SMTP_FROM la misma."),
            idiomas.N_("Anota el servidor y el puerto (Gmail: smtp.gmail.com y 587, STARTTLS)."),
            idiomas.N_("Pega SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS y SMTP_FROM en el .env del servidor, junto con "
            "PLATAFORMA_URL (la dirección pública del sitio, p. ej. https://app.creatvmachine.com: es la base de "
            "los enlaces que van en los correos), y reinicia los dos servicios."),
            idiomas.N_("Prueba con «Reenviar» en Configuración › Cuenta: debe llegar el correo de confirmación. "
            "Abajo, en «Correo de avisos», escribe a qué dirección llegan los avisos de este proyecto."),
        ],
    },
    {
        "id": "meli",
        "nombre": idiomas.N_("MercadoLibre (opcional)"),
        "para_que": idiomas.N_("Trae las publicaciones activas de una tienda de MercadoLibre al catálogo."),
        "costo": idiomas.N_("Gratis: solo lectura de tus publicaciones."),
        "url": "https://developers.mercadolibre.com/",
        "url_texto": "developers.mercadolibre.com",
        "variables": ["MELI_APP_ID", "MELI_SECRET"],
        "nota": idiomas.N_("Sin esto no aparece el botón «Conectar con MercadoLibre» en Tienda."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En developers.mercadolibre.com entra con la cuenta de la tienda y ve a «Mis aplicaciones» › «Crear nueva aplicación»."),
            idiomas.N_("Marca los permisos de lectura y «offline_access» (para renovar el token solo)."),
            idiomas.N_("En «URI de redirect» pon exactamente {callback_meli}."),
            idiomas.N_("Copia el App ID y la Secret Key y pégalos como MELI_APP_ID y MELI_SECRET en el .env del servidor; reinicia."),
            idiomas.N_("Luego, en «Conectar tu tienda» › MercadoLibre, pulsa «Conectar con MercadoLibre»."),
        ],
    },
    {
        "id": "reddit",
        "nombre": idiomas.N_("Reddit (Nicho: comentarios reales)"),
        "para_que": idiomas.N_("Trae posts y comentarios de Reddit a un estudio de Nicho para armar avatares con evidencia."),
        "costo": idiomas.N_("Gratis para uso propio (100 llamadas por minuto). Si el producto se vende, Reddit pide permiso comercial."),
        "url": "https://www.reddit.com/prefs/apps",
        "url_texto": "reddit.com › preferences › apps",
        "variables": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"],
        "nota": idiomas.N_("Sin ellas la tarjeta Reddit de cada estudio queda apagada; el resto de Nicho funciona."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Entra a reddit.com/prefs/apps con la cuenta de la empresa y pulsa «create another app…»."),
            idiomas.N_("Tipo «script», nombre «creatv-machine», redirect uri http://localhost:8080 (no se usa) y crea la app."),
            idiomas.N_("Copia el id (bajo el nombre de la app) como REDDIT_CLIENT_ID y el «secret» como REDDIT_CLIENT_SECRET."),
            idiomas.N_("Pon REDDIT_USER_AGENT con la forma «creatv-machine/1.0 (by u/tu_usuario)» y reinicia los dos servicios."),
        ],
    },
    {
        "id": "youtube_api",
        "nombre": idiomas.N_("YouTube Data API (Nicho: comentarios de videos)"),
        "para_que": idiomas.N_("Busca videos por palabras clave y trae sus comentarios a un estudio de Nicho. Es una llave distinta del OAuth de publicación."),
        "costo": idiomas.N_("Gratis: 100 búsquedas por día por proyecto de Google y 10 000 unidades para leer comentarios."),
        "url": "https://console.cloud.google.com/apis/credentials",
        "url_texto": idiomas.N_("console.cloud.google.com › APIs y servicios › Credenciales"),
        "variables": ["YOUTUBE_API_KEY"],
        "nota": idiomas.N_("Sin ella la tarjeta YouTube de cada estudio queda apagada."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En el proyecto de Google Cloud donde ya está habilitada «YouTube Data API v3» (SETUP.md §2), ve a «Credenciales»."),
            idiomas.N_("«Crear credenciales» › «Clave de API»; en «Restricciones de API» limítala a YouTube Data API v3."),
            idiomas.N_("Cópiala como YOUTUBE_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "apify",
        "nombre": idiomas.N_("Apify (Nicho: reseñas/comentarios · Referentes: Ad Library)"),
        "para_que": idiomas.N_("Corre los actores de Apify: en Nicho trae reseñas de Amazon o comentarios de TikTok; en la biblioteca de referentes trae anuncios de la Ad Library de Meta (alternativa a Atria, sí cubre Latinoamérica)."),
        "costo": idiomas.N_("Se paga por resultado (Amazon ≈ US$ 3 por 1 000 reseñas; TikTok ≈ US$ 0,50 por 1 000 comentarios) más cómputo; el estimado se muestra antes de cada clic."),
        "url": "https://console.apify.com/account/integrations",
        "url_texto": "console.apify.com › Settings › Integrations",
        "variables": ["APIFY_TOKEN"],
        "nota": idiomas.N_("Sin él la tarjeta Amazon / TikTok de cada estudio queda apagada. Zona gris de términos de uso de esas plataformas: es responsabilidad de quien pone el token."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Crea la cuenta en apify.com (trae crédito gratis mensual) y agrega una tarjeta si vas a pasar de ese crédito."),
            idiomas.N_("En «Settings» › «Integrations» copia el «Personal API token»."),
            idiomas.N_("Pégalo como APIFY_TOKEN en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "atria",
        "nombre": idiomas.N_("Atria (biblioteca de referentes: Ad Library de Meta)"),
        "para_que": idiomas.N_("Trae anuncios reales de la Ad Library de Meta para la biblioteca de referentes -- la fuente cubre la Unión Europea."),
        "costo": idiomas.N_("Incluido en el plan mensual de Atria (1 200 llamadas/mes); no cobra por resultado. El contador de uso está en Referentes (admin)."),
        "url": "https://tryatria.com",
        "url_texto": "tryatria.com",
        "variables": ["ATRIA_API_KEY"],
        "nota": idiomas.N_("Sin ella la fuente Atria queda apagada en «Traer referentes» (por proyecto y en el panel admin); Apify sigue disponible si tiene su propio token."),
        "opcional": True,
        "pasos": [
            idiomas.N_("Crea la cuenta en tryatria.com y elige un plan."),
            idiomas.N_("Copia la API key desde el panel de Atria."),
            idiomas.N_("Pégala como ATRIA_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
    {
        "id": "trendtrack",
        "nombre": idiomas.N_("TrendTrack (biblioteca de referentes: anuncios de Meta)"),
        "para_que": idiomas.N_("Trae anuncios reales de Meta que TrendTrack ha registrado para la biblioteca de referentes; busca por palabra clave."),
        "costo": idiomas.N_("Un crédito de TrendTrack por anuncio revisado (US$ 1 = 1 000 créditos); el plan Pro incluye 20 000 créditos al mes. El uso está en Referentes (admin)."),
        "url": "https://www.trendtrack.io",
        "url_texto": "trendtrack.io",
        "variables": ["TRENDTRACK_API_KEY"],
        "nota": idiomas.N_("Sin ella la fuente TrendTrack queda apagada en «Traer referentes». La API pide el plan Pro o superior: el Starter no la incluye."),
        "opcional": True,
        "pasos": [
            idiomas.N_("En trendtrack.io elige el plan Pro o superior (incluye la API y 20 000 créditos al mes)."),
            idiomas.N_("Crea una API key en tu workspace de TrendTrack (guía: docs.trendtrack.io › Getting Started)."),
            idiomas.N_("Pégala como TRENDTRACK_API_KEY en el .env del servidor y reinicia los dos servicios."),
        ],
    },
)


def _estado_llaves(callback_meli=None):
    """Tarjetas de Configuración › Puesta a punto (solo admin). Devuelve una
    lista de dicts {id, nombre, para_que, costo, estado, url, url_texto,
    variables, faltan, nota, pasos, opcional} donde `estado` es «configurada»
    (todas las variables presentes), «falta» (ninguna) o «parcial» (algunas).
    Solo mira bool(os.environ.get(var)): ningún valor sale de aquí.
    `callback_meli` es la URL real del callback de MercadoLibre para el paso
    de la app (fuera de un request se deja el texto genérico). La conexión
    con Meta no es una llave del servidor: vive en Experimentos
    (_meta_conectar.html)."""
    callback = callback_meli or "<url del sitio>/meli/callback"
    tarjetas = []
    for s in SERVICIOS_LLAVES:
        nota, pasos = s["nota"], s["pasos"]
        presentes = [v for v in s["variables"] if bool((os.environ.get(v) or "").strip())]
        faltan = [v for v in s["variables"] if v not in presentes]
        if not faltan:
            estado = "configurada"
        elif not presentes:
            estado = "falta"
        else:
            estado = "parcial"
        # Ojo: gettext(s["nombre"]) confunde al extractor de Babel (agarra el
        # literal "nombre" del subíndice como si fuera el mensaje) — por eso
        # cada valor pasa primero por una variable antes de traducirse.
        nombre_valor, para_que_valor, costo_valor = s["nombre"], s["para_que"], s["costo"]
        url_texto_valor = s["url_texto"]
        tarjetas.append({
            "id": s["id"],
            "nombre": gettext(nombre_valor),
            "para_que": gettext(para_que_valor),
            "costo": gettext(costo_valor),
            "estado": estado,
            "url": s["url"],
            "url_texto": gettext(url_texto_valor),
            "variables": list(s["variables"]),
            "faltan": faltan,
            "nota": gettext(nota),
            "opcional": bool(s.get("opcional")),
            "pasos": [gettext(p).replace("{callback_meli}", callback) for p in pasos],
        })
    return tarjetas


def _llaves_visibles(tarjetas, rol):
    """Las llaves son del servidor: solo el admin ve las tarjetas. Un cliente
    no ve ninguna (la conexión con Meta, que era la única por proyecto, vive
    en Experimentos)."""
    return tarjetas if rol == "admin" else []


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
        flash(gettext("Escribe la idea y elige un personaje."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    guia_estilo = marca_mod.guia_efectiva(cliente)
    try:
        textos = generador_prompts.generar_prompts(idea_texto, n=5, guia_estilo=guia_estilo,
                                                    idioma=idiomas.de_proyecto(cliente))
    except Exception as e:
        flash(gettext("No pude generar los prompts: %(error)s", error=e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    aspect_ratio = _aspect_ratio_para_plataformas(platforms)
    items = [
        {"prompt": t, "image_url": image_url, "platforms": platforms, "aspect_ratio": aspect_ratio}
        for t in textos
    ]
    prompts_mod.agregar_idea(cliente, idea_texto, items)

    flash(gettext("Generé %(n)s prompts para la idea. Revísalos y apruébalos abajo.", n=len(items)), "ok")
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
            return idiomas.N_("Imagen lista.")
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
        flash(gettext("Escribe la idea y elige un personaje."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    guia_estilo = marca_mod.guia_efectiva(cliente)
    try:
        escenas = generador_prompts.generar_conceptos_imagen(idea_texto, n=5, guia_estilo=guia_estilo,
                                                              idioma=idiomas.de_proyecto(cliente))
    except Exception as e:
        flash(gettext("No pude generar las escenas: %(error)s", error=e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    idea_id = conceptos_imagen.crear_idea(cliente, idea_texto, escenas)

    data = conceptos_imagen.cargar(cliente)
    data[idea_id]["platforms"] = platforms
    conceptos_imagen.guardar(cliente, data)

    for concepto_id, concepto in data[idea_id]["conceptos"].items():
        for proveedor in conceptos_imagen.PROVEEDORES:
            _lanzar_generacion_concepto(cliente, idea_id, concepto_id, proveedor, concepto["texto"], image_url)

    flash(gettext("Generando %(n)s escenas x 2 proveedores (10 imágenes)…", n=len(escenas)), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/aprobar", methods=["POST"])
def aprobar_concepto_imagen(cliente, idea_id, concepto_id, proveedor):
    """Esta imagen sí sirve: genera 5 propuestas de animación (texto, gratis) para
    ella específicamente. Se puede aprobar más de una imagen por idea."""
    data = conceptos_imagen.cargar(cliente)
    concepto = conceptos_imagen.encontrar_concepto(data, idea_id, concepto_id)
    if not concepto or proveedor not in concepto or not concepto[proveedor].get("url"):
        flash(gettext("No encontré esa imagen para aprobar."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    guia_estilo = marca_mod.guia_efectiva(cliente)
    idea_texto = data[idea_id]["idea"]
    try:
        animaciones = generador_prompts.generar_prompts(idea_texto, n=5, guia_estilo=guia_estilo,
                                                         idioma=idiomas.de_proyecto(cliente))
    except Exception as e:
        flash(gettext("No pude generar las propuestas de animación: %(error)s", error=e), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="aprobado")
    conceptos_imagen.agregar_animaciones(cliente, idea_id, concepto_id, proveedor, animaciones)

    flash(gettext("Imagen aprobada — elige cómo animarla abajo."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/idea/<idea_id>/concepto/<concepto_id>/<proveedor>/descartar", methods=["POST"])
def descartar_concepto_imagen(cliente, idea_id, concepto_id, proveedor):
    conceptos_imagen.marcar_imagen(cliente, idea_id, concepto_id, proveedor, estado="descartado")
    flash(gettext("Imagen descartada."), "ok")
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
        flash(gettext("No encontré esa animación."), "error")
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

        registro = {
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
        # Con candado (estado.modificar): el worker también escribe este archivo.
        estado_mod.modificar(cliente, lambda estado: {**estado, video_id: registro})

        data2 = conceptos_imagen.cargar(cliente)
        animacion2 = conceptos_imagen.encontrar_animacion(data2, idea_id, concepto_id, proveedor, anim_id)
        if animacion2:
            animacion2["estado"] = "video_generado"
            conceptos_imagen.guardar(cliente, data2)
        return idiomas.N_("Video listo, pendiente de revisión.")

    # ETAPAS_VIDEO sin ETAPA_DESCARGAR: el provider descarga por su cuenta dentro
    # de generar_video, así que ese paso no se puede anunciar por separado.
    if trabajos.iniciar(
        job_id, trabajo, duracion_estimada=130,
        etapas=[(ETAPA_MODELO, 90), (ETAPA_GUARDAR_VIDEO, 10)],
    ):
        flash(gettext("Generando video…"), "ok")
    else:
        flash(gettext("Ya se está generando ese video — espera a que termine."), "warn")
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
        flash(gettext("Idea eliminada."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


# ---------- flujo "cambiar calzado": una foto real + un producto del catálogo ->
# la misma foto, con el calzado reemplazado. Nada más cambia. ----------

def _cat(valor):
    """Categoría del catálogo pedida por la ruta (query o form); 'producto' por defecto."""
    return catalogo_productos.categoria_valida(valor or catalogo_productos.CATEGORIA_POR_DEFECTO)


@app.route("/cliente/<cliente>/productos/<path:producto_id>/imagen")
def imagen_producto(cliente, producto_id):
    """Sirve la foto representativa de un activo (`pid` o `pid/color`) directo
    del disco. `<path:>` porque los ids de color llevan «/» (antes daban 404)."""
    categoria = _cat(request.args.get("categoria") or request.form.get("categoria"))
    producto = catalogo_productos.encontrar(cliente, producto_id, categoria=categoria)
    if not producto and "/" not in producto_id:
        entrada = catalogo_productos.encontrar_producto(cliente, producto_id, categoria)
        producto = {"representativa": entrada["representativa"]} if entrada else None
    if not producto:
        flash(gettext("No encontré el producto %(id)s", id=producto_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))
    return _foto_o_miniatura(producto["representativa"])


def _foto_o_miniatura(ruta):
    """`?w=320` sirve la miniatura (catalogo_productos.miniatura); sin `w`, el
    original. Ambas con ETag: el navegador revalida y recibe 304 si no cambió."""
    w = request.args.get("w")
    if w and w.isdigit() and int(w) in catalogo_productos.ANCHOS_MINIATURA:
        return send_file(catalogo_productos.miniatura(ruta, int(w)))
    return send_file(ruta)


@app.route("/cliente/<cliente>/productos/<path:producto_id>/imagen/<nombre>")
def imagen_producto_archivo(cliente, producto_id, nombre):
    """Sirve UNA foto concreta: del producto (`pid`), de un color (`pid/color`,
    o `pid` + `?variante=`). 404 ante cualquier id o color inválido. El
    nombre se valida contra las imágenes que de verdad hay en esa carpeta
    (no con `secure_filename`, que cambia «HOriginal - Beige_5.png» por
    «HOriginal_-_Beige_5.png» y dejaba sin foto a los nombres con espacios)."""
    try:
        carpeta = catalogo_productos.carpeta_de(
            cliente, producto_id, categoria=_cat(request.args.get("categoria") or request.form.get("categoria")),
            variante=(request.args.get("variante") or "").strip() or None)
    except ValueError:
        abort(404)
    if nombre != os.path.basename(nombre) or nombre not in catalogo_productos._imagenes_en(carpeta):
        abort(404)
    return _foto_o_miniatura(os.path.join(carpeta, nombre))


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
    flash(gettext("Nombre del proyecto actualizado."), "ok")
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
        flash(gettext("Modelo de foto inválido."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    if proveedor_video not in PROVEEDORES_SWAP_VIDEO:
        flash(gettext("Modelo de video inválido."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))

    proyectos.guardar_preferencias(cliente, proveedor_foto, proveedor_video, mejorar_calidad)
    flash(gettext("Modelos por defecto actualizados."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/preferencias_flowplus/guardar", methods=["POST"])
def guardar_preferencias_flowplus(cliente):
    modelo_video = request.form.get("modelo_video", "").strip()
    modelo_imagen = request.form.get("modelo_imagen", "").strip()
    if modelo_video not in flowplus_modelos.VIDEO or modelo_imagen not in flowplus_modelos.IMAGEN:
        flash(gettext("Modelo inválido."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    proyectos.guardar_preferencias_flowplus(
        cliente, modelo_video, modelo_imagen,
        duracion_defecto=request.form.get("duracion_defecto") or 8)
    flash(gettext("Modelos por defecto de FlowPlus actualizados."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/cliente/<cliente>/preferencias_sonido/guardar", methods=["POST"])
def guardar_preferencias_sonido(cliente):
    con_sonido = request.form.get("con_sonido") == "si"
    estilo = (request.form.get("musica_al_crear") or "").strip()
    if estilo not in fe_tipos.ESTILOS_MUSICA:
        estilo = ""
    proyectos.guardar_preferencias_sonido(cliente, con_sonido, estilo)
    flash(gettext("Preferencias de sonido guardadas."), "ok")
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
            flash(gettext("El precio tiene que ser un número positivo (ej. 89900 o 25,50); no lo guardé."), "error")
    if "prioridad" in form:
        try:
            prioridad = int(form.get("prioridad") or 0)
            if not (0 <= prioridad <= 100):
                raise ValueError
            campos["prioridad"] = prioridad
        except ValueError:
            flash(gettext("La prioridad va de 0 a 100; no la guardé."), "error")
    if "moneda" in form:
        moneda = (form.get("moneda") or "").strip().upper()
        if moneda and not _MONEDA_RE.match(moneda):
            flash(gettext("La moneda va en código de 3 letras (COP, MXN, USD…); no la guardé."), "error")
        else:
            campos["moneda"] = moneda or None
    if "url_compra" in form:
        url = (form.get("url_compra") or "").strip()
        if url.lower().startswith("wa.me/"):
            url = "https://" + url
        if url and not url.startswith(("http://", "https://")):
            flash(gettext("La URL de compra tiene que empezar por http:// o https:// (o ser wa.me/…); no la guardé."), "error")
        else:
            campos["url_compra"] = url or None
    return campos


_SIN_CAMBIO = object()


def _sofisticacion_form(form):
    """1–5 del selector «Cuántas promesas parecidas vio ya tu cliente»;
    None = «Que Claude lo decida»; `_SIN_CAMBIO` si el formulario no trae
    el campo (un formulario viejo no debe borrar lo elegido)."""
    if "sofisticacion" not in form:
        return _SIN_CAMBIO
    try:
        valor = int(form.get("sofisticacion") or 0)
    except ValueError:
        return None
    return valor if valor in doctrina.SOFISTICACIONES else None


def _guardar_fila_producto(cliente, producto_id, nombre, descripcion, campos, desarchivar=False,
                          sofisticacion=_SIN_CAMBIO):
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
    if sofisticacion is not _SIN_CAMBIO:
        tiendas.anotar_extra(cliente, pid, sofisticacion=sofisticacion)
    return pid


@app.route("/cliente/<cliente>/doctrina")
def doctrina_pagina(cliente):
    """«Cómo escribe Creatv» (doctrina, bloque 2, §6): las nueve rebanadas de
    `doctrina/textos/*.md`, de solo lectura, para cualquier usuario con acceso
    al proyecto (lo exige `_guard_por_cliente`). Lee los mismos archivos que
    recibe Claude: la página nunca se desincroniza de lo que está en uso."""
    from doctrina import pagina as doctrina_pagina_mod
    return render_template("doctrina.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           secciones=doctrina_pagina_mod.secciones())


@app.route("/cliente/<cliente>/productos/crear", methods=["POST"])
def crear_producto(cliente):
    # "volver": pestaña que abrió el alta rápida (FlowClone, FlowPlus o FlowCatálogo).
    volver = request.form.get("volver") or "cambiar"
    nombre = (request.form.get("nombre") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    categoria = _cat(request.form.get("categoria"))
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not nombre:
        flash(gettext("Ponle un nombre."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))
    if not archivos:
        flash(gettext("Sube al menos una foto."), "error")
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
        flash(gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))
    if categoria == "producto":
        # Solo lo que se vende tiene fila comercial (precio, url de compra,
        # en prueba): un personaje o un entorno no van a un experimento.
        _guardar_fila_producto(cliente, producto_id, nombre, descripcion,
                               _campos_comerciales(request.form), desarchivar=True,
                               sofisticacion=_sofisticacion_form(request.form))
    flash(gettext("Producto creado: %(nombre)s (%(n)s foto(s)).", nombre=nombre, n=guardadas), "ok")
    if volver == "catalogo":
        # Desde el catálogo, el alta abre directo la ficha del producto nuevo.
        return _volver_catalogo(cliente, categoria, producto_id)
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=volver))


def _guardar_fotos_producto(cliente, producto_id, archivos, categoria="producto", variante=None):
    """Guarda las fotos en la carpeta del producto (o de uno de sus colores,
    con `variante`) y devuelve cuántas entraron. Quedan SOLO en disco a
    propósito: catalogo_productos las lee de ahí y el swap las sube a R2
    recién cuando se va a generar."""
    carpeta = catalogo_productos.carpeta_de(cliente, producto_id, categoria, variante=variante)
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
        return _volver_catalogo(cliente, categoria, producto_id)
    if categoria == "producto":
        # La fila comercial se crea aquí si el activo es anterior a que
        # existiera (no hay migración: se enlaza al primer uso).
        _guardar_fila_producto(cliente, producto_id, request.form.get("nombre"),
                               request.form.get("descripcion"), _campos_comerciales(request.form),
                               sofisticacion=_sofisticacion_form(request.form))
    flash(gettext("Producto actualizado."), "ok")
    return _volver_catalogo(cliente, categoria, producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/subir", methods=["POST"])
def subir_imagen_producto(cliente, producto_id):
    categoria = _cat(request.form.get("categoria"))
    variante = (request.form.get("variante") or "").strip() or None
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not archivos:
        flash(gettext("No elegiste ninguna foto."), "error")
        return _volver_catalogo(cliente, categoria, producto_id)
    try:
        guardadas = _guardar_fotos_producto(cliente, producto_id, archivos, categoria=categoria, variante=variante)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_catalogo(cliente, categoria, producto_id)
    if guardadas:
        flash(gettext("%(n)s foto(s) agregada(s).", n=guardadas), "ok")
    else:
        flash(gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."), "error")
    return _volver_catalogo(cliente, categoria, producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/imagenes/<nombre>/eliminar", methods=["POST"])
def eliminar_imagen_producto(cliente, producto_id, nombre):
    categoria = _cat(request.form.get("categoria"))
    try:
        ok, mensaje = catalogo_productos.eliminar_imagen(
            cliente, producto_id, nombre, categoria=categoria,
            variante=(request.form.get("variante") or "").strip() or None)
    except ValueError as e:
        ok, mensaje = False, str(e)
    flash(mensaje, "ok" if ok else "error")
    return _volver_catalogo(cliente, categoria, producto_id)


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
        return _volver_catalogo(cliente)
    if categoria == "producto":
        # La fila comercial NO se borra: se archiva (a mano, como en
        # prod_archivar) para que un experimento que ya la use no se quede
        # sin producto y para no perder precio/url si se vuelve a crear.
        fila = tiendas.por_activo(cliente).get(catalogo_productos.producto_base(producto_id))
        if fila and not fila["archivado"]:
            tiendas.marcar_producto(cliente, fila["id"], archivado=True)
    flash(gettext("Producto eliminado: %(nombre)s", nombre=nombre), "ok")
    return _volver_catalogo(cliente)


@app.route("/cliente/<cliente>/productos/<producto_id>/colores", methods=["POST"])
def catalogo_color_agregar(cliente, producto_id):
    """«+ Color» de la ficha (spec §10.3): crea el color y guarda sus fotos;
    en un producto plano con fotos exige el nombre del color actual."""
    nombre = (request.form.get("nombre") or "").strip()
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not nombre:
        flash(gettext("Ponle un nombre al color."), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    try:
        color_id = catalogo_productos.agregar_color(
            cliente, producto_id, nombre, descripcion=request.form.get("descripcion") or "",
            convertir_actual=(request.form.get("convertir_actual") or "").strip() or None)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    guardadas = _guardar_fotos_producto(cliente, producto_id, archivos, variante=color_id) if archivos else 0
    if archivos and not guardadas:
        flash(gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."), "error")
    flash(gettext("Color «%(nombre)s» agregado (%(n)s foto(s)).", nombre=nombre, n=guardadas), "ok")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/colores/<color_id>/quitar", methods=["POST"])
def catalogo_color_quitar(cliente, producto_id, color_id):
    try:
        catalogo_productos.quitar_color(cliente, producto_id, color_id)
        flash(gettext("Color quitado."), "ok")
    except ValueError as e:
        flash(str(e), "error")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/fotos/<nombre>/mover", methods=["POST"])
def catalogo_foto_mover(cliente, producto_id, nombre):
    """Una foto de ambiente pasa a ser referencia del color `variante`."""
    try:
        final = catalogo_productos.mover_foto_a_color(cliente, producto_id, nombre, (request.form.get("variante") or "").strip())
        flash(gettext("Foto asignada al color (%(nombre)s).", nombre=final), "ok")
    except ValueError as e:
        flash(str(e), "error")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/catalogo/producto/<producto_id>/crear-con", methods=["POST"])
def catalogo_crear_con(cliente, producto_id):
    """«Crear con este producto» (spec §10.5): deja el color elegido (o el
    primero con fotos) marcado en el diálogo del catálogo de Crear."""
    variante = (request.form.get("variante") or "").strip()
    activo_id = f"{producto_id}/{variante}" if variante else producto_id
    activo = catalogo_productos.encontrar(cliente, activo_id, categoria="producto")
    if not activo:
        flash(gettext("Ese producto no tiene fotos de referencia todavía."), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    # La precarga vale una vez y solo en este proyecto (_prefill_para).
    session["fp_prefill"] = {"cliente": cliente, "productos_catalogo": [f"producto:{activo['id']}"]}
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


def _pagina(valor):
    try:
        return max(1, int(valor or 1))
    except (TypeError, ValueError):
        return 1


def _usos_por_producto(cliente, productos, experimentos_exp=None, sesiones_cf=None, por_clave=None):
    """{pid: catalogo_vista.contar_usos(...)} en UNA pasada por las sesiones
    de Crear, una por los experimentos y una consulta a `campana`.
    `sesiones_cf` (`creative_flow.cargar(cliente)`) y `por_clave`
    (`_experimentos_por_activo(...)`) se leen aquí solo si el llamador no los
    trae ya calculados — así un request que pide galería + usos no repite la
    misma lectura de Crear/experimentos por cada helper (auditoría 2026-09-28)."""
    if sesiones_cf is None:
        sesiones_cf = creative_flow.cargar(cliente)
    sesiones = [{str(x).casefold() for x in (e.get("productos_ids") or []) if x}
                for e in sesiones_cf.values()]
    if por_clave is None:
        por_clave = _experimentos_por_activo(cliente, experimentos_exp, sesiones_cf)
    with db.conectar() as con:
        filas = con.execute(sa.select(db.campana.c.catalogo_id, sa.func.count())
                            .where(db.campana.c.cliente == cliente).group_by(db.campana.c.catalogo_id)).all()
    campanas = {str(k or "").casefold(): int(n) for k, n in filas}
    return {p["id"]: catalogo_vista.contar_usos(catalogo_productos.claves_de(p), sesiones, por_clave, campanas)
            for p in productos}


_TRABAJOS_VACIOS = {"vincular": {}, "pedidos": {}, "tiendas": {}, "importar": None}


@app.route("/cliente/<cliente>/catalogo/grid")
def catalogo_grid(cliente):
    """Galería del catálogo (spec §10.2): fragmento con filtros, orden y páginas de 60."""
    cat = _cat(request.args.get("cat"))
    q = (request.args.get("q") or "").strip()
    filtro = request.args.get("filtro") or "todos"
    orden = request.args.get("orden") if request.args.get("orden") in catalogo_vista.ORDENES else "prioridad"
    pagina = _pagina(request.args.get("pagina"))
    productos = catalogo_productos.listar_productos(cliente, cat)
    filas, sin_activo, usos, trabajos_grid = {}, [], {}, dict(_TRABAJOS_VACIOS)
    if cat == "producto":
        _asegurar_filas_producto(cliente, productos)
        # Una sola lectura de Crear y de experimentos para todo el request
        # (auditoría 2026-09-28): _productos_tienda_contexto y
        # _usos_por_producto reciben por_clave/sesiones_cf ya calculados en
        # vez de volver a pedirlos cada uno.
        experimentos_exp = experimentos.cargar(cliente)
        sesiones_cf = creative_flow.cargar(cliente)
        por_clave = _experimentos_por_activo(cliente, experimentos_exp, sesiones_cf)
        filas_tienda = _productos_tienda_contexto(cliente, experimentos_exp, por_clave)
        filas = _producto_comercial_contexto(filas_tienda)
        sin_activo = [f for f in filas_tienda if not f["activo_ok"]]
        usos = _usos_por_producto(cliente, productos, experimentos_exp, sesiones_cf, por_clave)
        trabajos_grid = _trabajos_productos(cliente, [], sin_activo)
    todas = catalogo_vista.tarjetas(productos, filas, usos, sin_activo)
    lista = catalogo_vista.ordenar(catalogo_vista.filtrar(todas, q, filtro), orden)
    trozo, hay_mas = catalogo_vista.paginar(lista, pagina, catalogo_vista.POR_PAGINA)
    return render_template("_catalogo_grid.html", cliente=cliente, cat=cat, tarjetas=trozo, hay_mas=hay_mas,
                           pagina=pagina, contadores=catalogo_vista.contadores(todas), filtro=filtro, q=q, orden=orden,
                           etiquetas_fuente=ETIQUETAS_FUENTE, trabajos_prod=trabajos_grid,
                           categorias=catalogo_productos.CATEGORIAS)


@app.route("/cliente/<cliente>/catalogo/<cat>/<path:activo_id>/ficha")
def catalogo_ficha(cliente, cat, activo_id):
    """Ficha de un activo (spec §10.3): fragmento para el panel lateral. Un id
    de color abre la ficha de su producto con ese color elegido."""
    cat = _cat(cat)
    pid = catalogo_productos.producto_base(activo_id)
    p = catalogo_productos.encontrar_producto(cliente, pid, cat)
    if not p:
        abort(404)
    comercial = usos = None
    trabajos_ficha = dict(_TRABAJOS_VACIOS)
    swaps_usos = 0
    if cat == "producto":
        tiendas.asegurar_manual(cliente, pid, p["nombre"], p.get("descripcion") or "")
        comercial = tiendas.por_activo(cliente).get(pid)
        # Una sola lectura de Crear y de experimentos para este request
        # (auditoría 2026-09-28), igual que en catalogo_grid.
        experimentos_exp = experimentos.cargar(cliente)
        sesiones_cf = creative_flow.cargar(cliente)
        usos = _usos_por_producto(cliente, [p], experimentos_exp, sesiones_cf).get(pid)
        if comercial:
            trabajos_ficha = _trabajos_productos(cliente, [], [comercial])
        swaps_usos = sum(1 for e in swaps_mod.cargar(cliente).values()
                         if catalogo_productos.producto_base(e.get("producto_id")) == pid)
    variante = activo_id.split("/", 1)[1] if "/" in activo_id else ""
    ids_colores = [c["color_id"] for c in p["colores"]]
    color_inicial = variante if variante in ids_colores else next(
        (c["color_id"] for c in p["colores"] if not c["sin_fotos"]), ids_colores[0] if ids_colores else None)
    return render_template(
        "_catalogo_ficha.html", cliente=cliente, cat=cat, p=p, comercial=comercial, usos=usos,
        color_inicial=color_inicial, trabajos_prod=trabajos_ficha,
        precio_pedidos=gastos.estimar("pedidos_producto")["texto"],
        monedas_catalogo=sorted(PRESUPUESTO_MINIMO_DIARIO), moneda_catalogo=_moneda_por_defecto(cliente),
        etiquetas_fuente=ETIQUETAS_FUENTE, tipos_producto=prompt_swap.TIPOS,
        zonas_cuerpo=mapa_corporal.ZONAS, presets_cuerpo=mapa_corporal.PRESETS,
        etiquetas_presets=mapa_corporal.ETIQUETAS_PRESETS, categorias=catalogo_productos.CATEGORIAS,
        con_mapa=catalogo_productos.CATEGORIAS[cat]["con_mapa"], swaps_usos=swaps_usos)


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


TARJETAS_POR_PAGINA = 24


def _pagina_desde(valor):
    """`?desde=` de las listas paginadas: entero >= 0; cualquier otra cosa es 0."""
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _ctx_items_cf(cliente):
    """Lecturas por proyecto que necesita cada item de Crear: una consulta cada
    una (auditoría 2026-09-28), compartidas entre las piezas de una lista."""
    # Doctrina, bloque 3: leer la guía una sola vez (no por pieza).
    try:
        guia_marca = marca_mod.guia_efectiva(cliente) or ""
    except Exception:  # noqa: BLE001 — es informativa, nunca bloquea
        guia_marca = ""
    return {
        # Id numérico de la pieza por sesión: la tarjeta enlaza «Probar en Meta»
        # a la galería de Experimentos (#experimentos?piezas=<pieza_id>).
        "pieza_ids": creative_flow.piezas_ids_por_legado(cliente),
        "guiones": creative_flow.guiones_base(cliente),
        "finales_por_cf": creative_flow.finales_por_sesion(cliente),
        "captions": doctrina_revisor.ultimos_captions(cliente),
        "guia_marca": guia_marca,
        # Doctrina, bloque 3, revisión final (I1): `final_edition._producto`
        # escanea el catálogo; memo por tupla de `productos_ids`, una sola
        # resolución por producto distinto en toda la lista, no por pieza.
        "productos_por_ids": {},
    }


def _armar_item_cf(cliente, cf_id, entry, data, ctx):
    """El dict de UNA sesión de Crear (lo que leen la tarjeta y el detalle).
    `data` es creative_flow.cargar(cliente) entero (para `tiene_hija_b`);
    `ctx` viene de _ctx_items_cf."""
    import final_edition
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
        "pieza_id": ctx["pieza_ids"].get(cf_id),
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
            # Con videos de referencia (Wan 3.0, 2026-09-30): la duración que de
            # verdad se pedirá y los segundos de entrada que WaveSpeed factura.
            refs_sesion = entry.get("referencias") or []
            segundos_ref = flowplus_modelos.segundos_videos(mid, refs_sesion)
            item["costo_estimado"] = flowplus_modelos.estimate_video(
                mid, flowplus_modelos.duracion_con_videos(mid, refs_sesion, entry["duracion_objetivo"]),
                con_sonido=entry.get("con_sonido", True) is not False,
                calidad=entry.get("calidad") or "final", **({"videos_ref_s": segundos_ref} if segundos_ref else {}))
    item["modelo_nombre"] = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre", "Wan 3.0")
    # Final edition: solo tiene sentido sobre un video ya listo. Cada final
    # y el guion llevan su propio trabajo del worker para la barra de la UI.
    item["guion_base"] = None
    item["finales"] = []
    item["trabajo_guion"] = None
    item["trabajo_editor"] = None
    if entry.get("estado") == "video_listo" and (entry.get("tipo") or "video") != "imagen":
        item["guion_base"] = ctx["guiones"].get(cf_id)
        jid_guion = tareas_fe.job_id_guion(cliente, cf_id)
        item["trabajo_guion"] = {"job_id": jid_guion} if trabajos.en_curso(jid_guion) else None
        jid_editor = tareas_edicion.job_id_desde_clon(cliente, cf_id)
        item["trabajo_editor"] = {"job_id": jid_editor} if trabajos.en_curso(jid_editor) else None
        for f in ctx["finales_por_cf"].get(cf_id, []):
            jid = tareas_fe.job_id_final(cliente, cf_id, f["idioma"], f["pais"], variante=f.get("variante"))
            f["trabajo"] = {"job_id": jid} if f.get("estado") == "generando" and trabajos.en_curso(jid) else None
            item["finales"].append(f)
    # Doctrina, bloque 3: revisión de la pieza terminada (video o imagen).
    # Las reglas son gratis y se calculan al renderizar; la revisión de
    # Claude es la guardada. Sin ninguna de las dos, la sección no pesa.
    item["revision"], item["revision_estado"], item["reglas"], item["trabajo_revision"] = None, None, [], None
    item["revision_error"] = None
    if entry.get("estado") == "video_listo" and entry.get("video_url"):
        item["revision"] = entry.get("revision_doctrina")
        item["revision_error"] = entry.get("revision_doctrina_error")
        item["revision_estado"] = doctrina_revisor.estado_revision(item["revision"], entry.get("video_url"))
        item["revision_n"] = doctrina_revisor.contar(item["revision"])
        try:
            clave = tuple(entry.get("productos_ids") or ())
            if clave:
                producto = ctx["productos_por_ids"].get(clave)
                if producto is None:
                    try:
                        producto = final_edition._producto(cliente, entry, None) or {}
                    except Exception:  # noqa: BLE001 — sin producto la revisión rápida sigue
                        producto = {}
                    # Solo se recuerda lo que resolvió el catálogo (trae «pruebas»): el
                    # producto de respaldo sale de los datos de ESTA pieza y no sirve a otra.
                    if "pruebas" in producto or not producto:
                        ctx["productos_por_ids"][clave] = producto
                d = doctrina_revisor.reunir(cliente, cf_id, entry=entry, guion=item["guion_base"],
                                            guia=ctx["guia_marca"], producto=producto, caption=ctx["captions"].get(cf_id, ""))
            else:
                d = doctrina_revisor.reunir(cliente, cf_id, entry=entry, guion=item["guion_base"], guia=ctx["guia_marca"],
                                            caption=ctx["captions"].get(cf_id, ""))
            item["reglas"] = doctrina_revisor.reglas(d)
        except Exception:  # noqa: BLE001 — la revisión rápida es informativa: nunca tumba la lista de Crear
            item["reglas"] = []
        jid_rev = tareas_doctrina.job_id_revisar(cliente, cf_id)
        item["trabajo_revision"] = {"job_id": jid_rev} if trabajos.en_curso(jid_rev) else None
        item["precio_revision"] = gastos.estimar("revision_pieza")["texto"]
    return item


def _creative_flow_items(cliente):
    data = creative_flow.cargar(cliente)
    ctx = _ctx_items_cf(cliente)
    return [_armar_item_cf(cliente, cf_id, entry, data, ctx)
            for cf_id, entry in sorted(data.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True)]


def _creative_flow_item(cliente, cf_id):
    """El mismo dict que _creative_flow_items produce para esa sesión, o None
    si no existe en ese proyecto (las rutas de detalle responden 404)."""
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        return None
    return _armar_item_cf(cliente, cf_id, entry, data, _ctx_items_cf(cliente))


def _listas_crear_final(items, n=TARJETAS_POR_PAGINA):
    """Lo que pintan Crear y Final edition (spec 2026-09-28 «tarjetas
    ligeras»): las primeras `n` de cada lista y los totales para los
    contadores de cabecera. `n=None` devuelve las listas completas (las rutas
    de «Ver más» recortan ellas)."""
    videos = [i for i in items if i.get("estado") == "video_listo" and (i.get("tipo") or "video") != "imagen"]
    finales = [(i, f) for i in items for f in (i.get("finales") or [])]
    corte = slice(0, n) if n else slice(None)
    return {"crear": items[corte], "crear_total": len(items),
            "final_videos": videos[corte], "final_videos_total": len(videos),
            "finales": finales[corte], "finales_total": len(finales)}


def _contexto_organico(cliente):
    """Lo que necesita el bloque «Publicar orgánico» (_organico_publicar.html),
    que va en el detalle de una final y en Experimentos."""
    publicaciones_por_pieza = organico.por_pieza(cliente)
    return {
        "canales_org": organico.canales(cliente),
        "plataformas_org": organico.PLATAFORMAS,
        "publicaciones_por_pieza": publicaciones_por_pieza,
        "trabajos_org": _trabajos_organico(cliente, publicaciones_por_pieza),
    }


def _contexto_final_edition(cliente):
    """Contexto que leen los detalles de Final edition: la página y las rutas
    de detalle (fe_detalle_video / fe_detalle_final) lo reciben igual."""
    return {
        **_contexto_organico(cliente),
        "paises_fe": fe_tipos.PAISES,
        "voces_fe": fal_audio.VOCES,
        "estilos_fe": list(fe_tipos.ESTILOS_MUSICA),
        "nombres_estilos_musica": fe_tipos.NOMBRES_ESTILOS_MUSICA,
        "nombres_estilo_musica": fe_tipos.NOMBRES_ESTILO_MUSICA,
        "presets_mezcla": list(fe_mezcla.PRESETS),
        "precios": _precios_pagina(),
        "ediciones_por_cf": _ediciones_por_cf(cliente),
        **_contexto_mi_musica(cliente),
    }


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
# Rótulos del objetivo de Meta en «Probar en Meta › Avanzado» (Bloque 6). El
# valor sigue siendo el enum de Meta; solo cambia lo que se lee (marcado con
# N_, traducido donde se muestra con |traducir).
NOMBRES_OBJETIVO_EXP = {"OUTCOME_SALES": idiomas.N_("Compras (requiere Pixel)"),
                        "OUTCOME_TRAFFIC": idiomas.N_("Tráfico (clics al enlace)"),
                        "OUTCOME_ENGAGEMENT": idiomas.N_("Interacción"),
                        "OUTCOME_LEADS": idiomas.N_("Clientes potenciales")}

PROVEEDORES_SWAP_IMAGEN = ("nano_banana", "nano_banana_fal", "qwen_edit", "nano_banana_pro_ultra", "seedream_v5_pro")
PROVEEDORES_SWAP_VIDEO = (
    "kling_o1", "luma_modify", "wan_animate_replace", "wan27_edit",
    "seedance25_edit", "kling_o3_pro_edit", "luma_ray32_edit",
)

# Nombres mostrados en el selector de modelo (Configuración > Generación y
# Crear > Cambiar producto): constante de módulo que se muestra, marcada con
# N_ y traducida donde se usa ({{ valor|traducir }} en las plantillas).
NOMBRES_PROVEEDOR_SWAP = {
    "nano_banana": idiomas.N_("Nano Banana"),
    "nano_banana_fal": idiomas.N_("Nano Banana (vía fal)"),
    "qwen_edit": idiomas.N_("Qwen Image Edit Plus"),
    "nano_banana_pro_ultra": idiomas.N_("Nano Banana Pro Ultra (4k)"),
    "seedream_v5_pro": idiomas.N_("Seedream V5.0 Pro Edit (2k)"),
    "kling_o1": idiomas.N_("Kling O1"),
    "luma_modify": idiomas.N_("Luma Ray3 Modify"),
    "wan_animate_replace": idiomas.N_("Wan-2.2 Animate Replace"),
    "wan27_edit": idiomas.N_("Wan 2.7 Video Edit"),
    "seedance25_edit": idiomas.N_("Seedance 2.5 Video Edit"),
    "kling_o3_pro_edit": idiomas.N_("Kling Omni O3 Pro Video Edit"),
    "luma_ray32_edit": idiomas.N_("Luma Ray 3.2 Video Edit"),
    # ya no seleccionables, pero se mantienen para mostrar el nombre en swaps viejos:
    "flux_kontext": idiomas.N_("Flux Kontext Pro"),
    "higgsfield": idiomas.N_("Higgsfield"),
    "gemini_omni_edit": idiomas.N_("Gemini Omni Flash Edit"),
    "wan3_reference": idiomas.N_("Wan 3.0 (referencia, no edición)"),
}


# Etapas reales de los trabajos. Los nombres se usan en DOS lados (al declararlas
# en trabajos.iniciar y al anunciarlas con trabajos.reportar), así que van en
# constantes para que no puedan desincronizarse por un typo. Los pesos son
# "qué fracción del tiempo se lleva más o menos cada paso" — la llamada al
# modelo es de lejos la más larga.
ETAPA_MODELO = idiomas.N_("Generando con el modelo")
ETAPA_DESCARGAR = idiomas.N_("Descargando el resultado")
ETAPA_MEZCLA = idiomas.N_("Mezclando sonido")
ETAPA_GUARDAR_VIDEO = idiomas.N_("Guardando el video")
ETAPA_GUARDAR_IMAGEN = idiomas.N_("Guardando la imagen")
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
    "IN_QUEUE": idiomas.N_("en cola"),
    "IN_PROGRESS": idiomas.N_("el modelo está trabajando"),
    "created": idiomas.N_("en cola"),
    "processing": idiomas.N_("el modelo está trabajando"),
    "queued": idiomas.N_("en cola"),
    "starting": idiomas.N_("arrancando"),
    "running": idiomas.N_("el modelo está trabajando"),
    "in_progress": idiomas.N_("el modelo está trabajando"),
    "pending": idiomas.N_("en cola"),
}

# Estados terminales: el poll también los emite en su última vuelta, pero mostrar
# "completed" como detalle no le dice nada al usuario — la etapa siguiente ya se
# encarga de contar qué sigue.
_FASES_TERMINALES = ("COMPLETED", "completed", "succeeded", "success", "done")


def _texto_fase(info, cliente):
    """Traduce el estado crudo que reporta un proveedor durante el poll, en el
    idioma del PROYECTO (mensaje de fondo, spec §B8; mismo patrón que
    tareas/flowplus.py): con el puesto en cola compuesto, estado_trabajo ya no
    podría traducirlo al responder. Con fallback: si aparece una fase que no
    conocemos se muestra tal cual en vez de tragarse la información (los
    proveedores agregan estados sin avisar)."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = _FASES_PROVEEDOR.get(fase, fase)
    if not texto:
        return None
    posicion = info.get("queue_position")
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        fase_traducida = gettext(texto)
        if posicion is not None:
            return gettext("%(fase)s (puesto %(n)s)", fase=fase_traducida, n=posicion)
        return fase_traducida


def _avisar_fase_de(job_id, cliente):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Envuelto en try/except porque un fallo REPORTANDO
    jamás puede tumbar una generación que ya gastó créditos."""
    def avisar_fase(info):
        try:
            texto = _texto_fase(info, cliente)
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
        flash(gettext("Sube al menos una foto o video primero."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    producto = catalogo_productos.encontrar(cliente, producto_id)
    if not producto:
        flash(gettext("Elige un producto del catálogo."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    lanzados = 0
    for archivo in archivos:
        if _lanzar_swap(cliente, archivo, producto, producto_id, proveedor_foto, proveedor_video, mejorar_calidad):
            lanzados += 1

    if lanzados == 1:
        flash(gettext("Generando el swap…"), "ok")
    elif lanzados > 1:
        flash(gettext("Generando %(n)s swaps…", n=lanzados), "ok")
    else:
        flash(gettext("Ya se estaban generando esos swaps — espera a que terminen."), "warn")
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
        flash(gettext("No encontré la foto original."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))
    return send_file(entry["foto_original_local"])


@app.route("/cliente/<cliente>/swap/<swap_id>/eliminar", methods=["POST"])
def eliminar_swap(cliente, swap_id):
    swaps_mod.eliminar(cliente, swap_id)
    flash(gettext("Eliminado."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/ads/nueva_campana", methods=["POST"])
def nueva_campana(cliente):
    """Campañas ya no existe como pestaña (se fundió en Experimentos). La ruta
    se conserva para enlaces/formularios viejos, pero no crea nada: avisa y
    manda a Experimentos, donde una pieza se mete en un experimento."""
    flash(gettext("Campañas ya no existe: crea un experimento con esa pieza."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad", methods=["POST"])
def enviar_swap_a_publicidad(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    if not entry or not entry.get("resultado_url"):
        flash(gettext("Ese swap todavía no tiene un resultado listo."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))

    producto = catalogo_productos.encontrar(cliente, entry.get("producto_id"))
    nombre = producto["nombre"] if producto else entry.get("producto_id", "Swap")
    ads_mod.crear(cliente, "swap", swap_id, entry["resultado_url"], entry.get("tipo", "foto"), nombre)
    flash(gettext("Quedó en Experimentos › Anuncios sueltos — crea un experimento con esa pieza."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="cambiar"))


@app.route("/cliente/<cliente>/video/<brief_id>/enviar_a_publicidad", methods=["POST"])
def enviar_video_a_publicidad(cliente, brief_id):
    data = estado_mod.cargar(cliente)
    entry = data.get(brief_id)
    if not entry or not entry.get("video_url"):
        flash(gettext("Ese video todavía no tiene una URL pública lista."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))

    nombre = entry.get("title") or brief_id
    ads_mod.crear(cliente, "idea_visual", brief_id, entry["video_url"], "video", nombre)
    flash(gettext("Quedó en Experimentos › Anuncios sueltos — crea un experimento con esa pieza."), "ok")
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


MENSAJE_MODO_AGENCIA = idiomas.N_("Este proyecto lo gestiona Creatv en Meta. Para volver a tu propia app usa «Cambiar de forma» "
                        "en Experimentos › Meta (con nada en marcha).")


def _bloqueo_modo_agencia(cliente):
    """Redirect con aviso si el proyecto está en modo agencia: las rutas de la
    app propia (registrar app, conectar, elegir, desconectar) no le aplican —
    la cuenta y la Página se las asigna el admin desde /admin/meta. Va ANTES
    del guard de correo verificado: un cliente en modo agencia no conecta
    nada, así que no tiene sentido pedirle que confirme el correo para
    decirle que no puede. None si el proyecto está en modo propia."""
    if meta_conexion.modo(cliente) != meta_conexion.MODO_AGENCIA:
        return None
    flash(gettext(MENSAJE_MODO_AGENCIA), "error")
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
        flash(gettext(MENSAJE_MODO_AGENCIA), "error")
        return _ir_a_flowmarketing(cliente)
    except meta_conexion.MetaConexionError as e:
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)
    bitacora.registrar(cliente, "meta", "app", "ok", f"app {request.form.get('app_id', '').strip()} registrada")
    flash(gettext("App de Meta registrada para este proyecto. Ahora sí: Conectar con Meta."), "ok")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/app/borrar", methods=["POST"])
def meta_app_borrar(cliente):
    bloqueo = _bloqueo_modo_agencia(cliente)
    if bloqueo:
        return bloqueo
    meta_conexion.borrar_app(cliente)
    bitacora.registrar(cliente, "meta", "app", "ok", "app de Meta quitada")
    flash(gettext("App de Meta quitada de este proyecto. La conexión existente sigue hasta que la desconectes."), "ok")
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
        flash(gettext(MENSAJE_MODO_AGENCIA), "error")
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
        flash(gettext("La autorización con Meta no coincide con esta sesión — vuelve a intentarlo desde FlowMarketing."),
              "error")
        return _ir_a_flowmarketing(cliente) if cliente else redirect(url_for("index"))
    if not usuarios.puede_acceder(_sesion(), cliente):
        flash(gettext("No tienes acceso a ese proyecto."), "error")
        return redirect(url_for("index"))

    if request.args.get("error"):
        detalle = request.args.get("error_description") or request.args.get("error")
        bitacora.registrar(cliente, "meta", "conexion", "error", f"cancelado o denegado: {detalle}")
        flash(gettext("Meta no autorizó la conexión: %(detalle)s", detalle=detalle), "error")
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
        flash(gettext("No hay una autorización de Meta en curso — empieza de nuevo con \"Conectar con Meta\"."), "error")
        return _ir_a_flowmarketing(cliente)
    activos = pendiente.get("activos") or {}
    cuentas = activos.get("ad_accounts") or []
    paginas = activos.get("pages") or []
    if not cuentas and not paginas:
        flash(gettext("No hay una autorización de Meta en curso — empieza de nuevo con \"Conectar con Meta\"."), "error")
        return _ir_a_flowmarketing(cliente)

    if request.method == "GET":
        return render_template(
            "meta_elegir.html", cliente=cliente, cuentas=cuentas, paginas=paginas,
            usuario_meta=pendiente.get("usuario_meta"), nombre_proyecto=proyectos.nombre_visible(cliente),
        )

    cuenta = next((a for a in cuentas if a["id"] == request.form.get("ad_account_id")), None)
    pagina = next((p for p in paginas if p["id"] == request.form.get("page_id")), None)
    if not cuenta or not pagina:
        flash(gettext("Elige una cuenta publicitaria y una Página de la lista."), "error")
        return redirect(url_for("meta_elegir", cliente=cliente))

    try:
        _guardar_conexion_propia(cliente, pendiente, cuenta, pagina)
    except meta_conexion.ModoAgenciaError:
        # Un admin asignó el proyecto a la agencia mientras el cliente elegía:
        # la asignación manda; la autorización a medias se descarta.
        meta_conexion.borrar_pendiente(cliente)
        flash(gettext(MENSAJE_MODO_AGENCIA), "error")
        return _ir_a_flowmarketing(cliente)
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", f"{cuenta.get('name')} · {pagina.get('name')}")
    aviso = "" if pagina.get("ig_user_id") else " " + gettext(
        "Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincules en Facebook.")
    flash(gettext("Meta conectado: %(cuenta)s · %(pagina)s.%(aviso)s",
                  cuenta=cuenta.get("name"), pagina=pagina.get("name"), aviso=aviso), "ok")
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
    flash(gettext("Conexión con Meta cancelada. Si ya tenías Meta conectado, sigue igual."), "ok")
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
        flash(gettext(MENSAJE_MODO_AGENCIA), "error")
        return _ir_a_flowmarketing(cliente)
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", "desconectado" + (" y revocado en Meta" if revocado else ""))
    if revocado:
        flash(gettext("Meta desconectado de este proyecto y acceso revocado en Meta."), "ok")
    else:
        flash(gettext("Meta desconectado de este proyecto. La app sigue autorizada en tu Facebook hasta que la quites en Configuración › Integraciones de negocio."), "ok")
    return _ir_a_flowmarketing(cliente)


# ---------- Meta: el cliente elige cómo conectar (spec 2026-09-20) ----------
# «forma» (proyectos.meta_forma) es lo que el cliente eligió; «modo»
# (meta_conexion.modo) es el estado real. Autoservicio del modo agencia: el
# cliente comparte sus activos con el Business de Creatv, pega su id de
# portafolio, ve SOLO los activos de ese portafolio y conecta; si no los ve,
# deja una solicitud para el admin. Ningún token pasa por acá.

_RE_PORTAFOLIO = re.compile(r"^\d{5,20}$")


def _ir_a_meta(cliente):
    # La elección de forma y las guías viven en Experimentos (_meta_conectar.html).
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


def _portafolio_valido(texto):
    texto = (texto or "").strip()
    return texto if _RE_PORTAFOLIO.match(texto) else None


def _bloqueo_cambio_forma(cliente, experimentos_lista=None):
    """None si el proyecto puede cambiar de forma; si no, el motivo (spec §4):
    experimentos vivos o publicaciones orgánicas en curso. Cada pieza pasa por
    ngettext/gettext con %(num)s / %(partes)s para que el inglés salga sin
    perder la concordancia singular/plural — el español (locale por defecto,
    sin catálogo) sale idéntico a como salía con los f-strings de antes."""
    lista = experimentos.cargar(cliente) if experimentos_lista is None else experimentos_lista
    vivos = sum(1 for e in lista if e.get("estado") in experimentos.ESTADOS_VIVOS)
    en_curso = sum(1 for p in organico.listar(cliente) if p.get("estado") in ("en_cola", "publicando"))
    if not vivos and not en_curso:
        return None
    partes = []
    if vivos:
        partes.append(ngettext("%(num)s experimento vivo", "%(num)s experimentos vivos", vivos))
    if en_curso:
        partes.append(ngettext("%(num)s publicación en curso", "%(num)s publicaciones en curso", en_curso))
    return gettext("Termina o cierra primero: %(partes)s", partes=" · ".join(partes))


@app.route("/cliente/<cliente>/meta/forma", methods=["POST"])
def meta_forma(cliente):
    """El cliente elige cómo conectar Meta. Solo la preferencia: no toca Meta
    ni meta.json. Con una conexión propia viva, cambiar exige nada en marcha."""
    if not _mismo_origen():
        abort(403)
    forma = (request.form.get("forma") or "").strip()
    if forma not in proyectos.FORMAS_META:
        flash(gettext("Elige una de las dos formas de conectar."), "error")
        return _ir_a_meta(cliente)
    if forma == "agencia" and not meta_agencia.conectada():
        flash(gettext("Esa opción todavía no está disponible: Creatv está terminando de activarla."), "error")
        return _ir_a_meta(cliente)
    if meta_conexion.modo(cliente) == meta_conexion.MODO_AGENCIA:
        flash(gettext(MENSAJE_MODO_AGENCIA), "error")
        return _ir_a_meta(cliente)
    if (meta_conexion.cargar(cliente) or {}).get("token") and forma != proyectos.meta_forma(cliente):
        motivo = _bloqueo_cambio_forma(cliente)
        if motivo:
            flash(motivo, "error")
            return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, forma)
    bitacora.registrar(cliente, "meta", "forma", "ok", f"forma elegida: {forma} (por {session.get('usuario')})")
    if forma == "agencia":
        flash(gettext("Que Creatv lo gestione: sigue los pasos de la tarjeta de Meta."), "ok")
    else:
        flash(gettext("Con tu propia app: sigue los pasos de la tarjeta de Meta."), "ok")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/buscar", methods=["POST"])
def meta_agencia_buscar(cliente):
    """Valida el id del portafolio y manda a la página del proyecto con
    ?agencia_portafolio= (ver_cliente hace la consulta; «Volver a buscar»
    agrega refrescar=1 para saltar el caché de 10 min)."""
    if not _mismo_origen():
        abort(403)
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    if not portafolio:
        flash(gettext("Escribe el id de tu portafolio comercial (solo números)."), "error")
        return _ir_a_meta(cliente)
    extra = {"refrescar": "1"} if request.form.get("refrescar") == "1" else {}
    return redirect(url_for("ver_cliente", cliente=cliente, agencia_portafolio=portafolio, _anchor="settings", **extra))


@app.route("/cliente/<cliente>/meta/agencia/conectar", methods=["POST"])
def meta_agencia_conectar(cliente):
    """Autoservicio: el cliente eligió cuenta y Página entre los activos de SU
    portafolio y queda conectado sin esperar al admin. Los ids se revalidan
    acá contra lo que Meta devuelve (nunca se confía en el navegador)."""
    if not _mismo_origen():
        abort(403)
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not meta_agencia.conectada():
        flash(gettext("Creatv todavía no activó esta opción; inténtalo más tarde."), "error")
        return _ir_a_meta(cliente)
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    ad_account_id = (request.form.get("ad_account_id") or "").strip()
    page_id = (request.form.get("page_id") or "").strip() or None
    page_id_manual = (request.form.get("page_id_manual") or "").strip() or None
    if not portafolio or not ad_account_id:
        flash(gettext("Falta el id de tu portafolio o la cuenta publicitaria."), "error")
        return _ir_a_meta(cliente)
    try:
        activos = meta_agencia.activos_de_portafolio(portafolio, cliente=cliente)
    except meta_conexion.MetaConexionError as e:
        flash(gettext("No pude leer tus activos: %(error)s", error=cola.sin_token(str(e))), "error")
        return _ir_a_meta(cliente)
    if ad_account_id not in {a["id"] for a in activos["ad_accounts"]}:
        flash(gettext("Esa cuenta publicitaria no aparece entre las de tu portafolio; vuelve a buscar."), "error")
        return _ir_a_meta(cliente)
    if page_id and page_id not in {p["id"] for p in activos["pages"]}:
        flash(gettext("Esa Página no aparece entre las de tu portafolio; vuelve a buscar."), "error")
        return _ir_a_meta(cliente)
    if not page_id and page_id_manual:
        if not activos["paginas_sin_dueno"] or not meta_agencia.pagina_de_socio(page_id_manual):
            flash(gettext("Esa Página no está compartida con Creatv; revisa el paso 2 de la guía."), "error")
            return _ir_a_meta(cliente)
        page_id = page_id_manual
    try:
        detalle = meta_agencia.asignar(cliente, ad_account_id, page_id,
                                       asignado_por=f"cliente:{session.get('usuario')}", portafolio_id=portafolio)
    except meta_conexion.MetaConexionError as e:
        flash(gettext("No pude conectar: %(error)s", error=cola.sin_token(str(e))), "error")
        return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, "agencia")
    nombre = proyectos.nombre_visible(cliente)
    cuenta = detalle.get("ad_account_nombre") or detalle.get("ad_account_id")
    id_cuenta = detalle.get("ad_account_id")
    pagina_real = detalle.get("page_nombre") or detalle.get("page_id")
    bitacora.registrar(cliente, "meta", "agencia", "ok",
                       f"conectado por el cliente {session.get('usuario')}: {cuenta} · {pagina_real or 'sin Página'}")

    def _cuerpo_conexion():   # en el idioma de cada admin (notificaciones.avisar_admin)
        sin_pagina = gettext("sin Página")
        return gettext("El proyecto %(nombre)s (%(cliente)s) conectó por su cuenta: cuenta %(cuenta)s (%(id_cuenta)s) · "
                       "Página %(pagina)s · portafolio %(portafolio)s.\n"
                       "Revísalo en el panel de administración › Meta (agencia).",
                       nombre=nombre, cliente=cliente, cuenta=cuenta, id_cuenta=id_cuenta,
                       pagina=pagina_real or sin_pagina, portafolio=portafolio)
    notificaciones.avisar_admin(
        "meta_conexion_cliente", lambda: gettext("%(nombre)s se conectó a Meta (agencia)", nombre=nombre),
        _cuerpo_conexion, cliente=cliente)
    pagina = pagina_real or gettext("sin Página")
    flash(gettext("Listo: Creatv ya gestiona tu Meta con %(cuenta)s · %(pagina)s.", cuenta=cuenta, pagina=pagina), "ok")
    if detalle.get("cambio_cuenta"):
        flash(gettext("La cuenta publicitaria cambió: los experimentos anteriores dejan de refrescarse."), "warn")
    if page_id and not detalle.get("ig_username"):
        flash(gettext("Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincules en Facebook."), "warn")
    if not page_id:
        flash(gettext("Sin Página solo se pueden pautar anuncios; la publicación orgánica queda apagada."), "warn")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/avisar", methods=["POST"])
def meta_agencia_avisar(cliente):
    """Respaldo: el cliente no vio sus activos y pide que Creatv termine la
    conexión a mano. Deja la solicitud y avisa a los admins."""
    if not _mismo_origen():
        abort(403)
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    if not portafolio:
        flash(gettext("Escribe el id de tu portafolio comercial (solo números)."), "error")
        return _ir_a_meta(cliente)
    try:
        sol = meta_agencia.solicitar(cliente, portafolio, ad_account_id=request.form.get("ad_account_id"),
                                     page_id=request.form.get("page_id"), nota=request.form.get("nota"),
                                     usuario=session.get("usuario"))
    except meta_conexion.MetaConexionError as e:
        flash(str(e), "error")
        return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, "agencia")
    nombre = proyectos.nombre_visible(cliente)
    bitacora.registrar(cliente, "meta", "agencia", "solicitud",
                       f"portafolio {portafolio} · cuenta {sol['ad_account_id'] or '?'} · Página {sol['page_id'] or '?'}")
    cuenta_sol, pagina_sol, nota_sol = sol["ad_account_id"], sol["page_id"], sol["nota"]

    def _cuerpo_solicitud():   # en el idioma de cada admin (notificaciones.avisar_admin)
        no_indicada = gettext("no indicada")
        return gettext("El proyecto %(nombre)s (%(cliente)s) compartió sus activos pero no los vio desde Configuración.\n"
                       "Portafolio %(portafolio)s · cuenta %(cuenta)s · Página %(pagina)s.\n"
                       "Nota: %(nota)s\nAsígnalo en el panel de administración › Meta (agencia).",
                       nombre=nombre, cliente=cliente, portafolio=portafolio, cuenta=cuenta_sol or no_indicada,
                       pagina=pagina_sol or no_indicada, nota=nota_sol or "—")
    notificaciones.avisar_admin(
        "meta_solicitud", lambda: gettext("%(nombre)s pide conectar Meta (agencia)", nombre=nombre),
        _cuerpo_solicitud, cliente=cliente)
    flash(gettext("Listo: Creatv recibió tu solicitud y te avisa por correo cuando quede conectado."), "ok")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/avisar/cancelar", methods=["POST"])
def meta_agencia_avisar_cancelar(cliente):
    if not _mismo_origen():
        abort(403)
    if meta_agencia.borrar_solicitud(cliente):
        bitacora.registrar(cliente, "meta", "agencia", "ok", f"solicitud cancelada por {session.get('usuario')}")
        flash(gettext("Solicitud cancelada."), "ok")
    else:
        flash(gettext("No había ninguna solicitud pendiente."), "warn")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/salir", methods=["POST"])
def meta_agencia_salir(cliente):
    """Agencia → propia por decisión del cliente (spec §4): solo con nada en
    marcha; desasigna (restaura su conexión propia si la tenía) y avisa."""
    if not _mismo_origen():
        abort(403)
    if meta_conexion.modo(cliente) != meta_conexion.MODO_AGENCIA:
        flash(gettext("Este proyecto no está en modo agencia."), "warn")
        return _ir_a_meta(cliente)
    motivo = _bloqueo_cambio_forma(cliente)
    if motivo:
        flash(motivo, "error")
        return _ir_a_meta(cliente)
    meta_agencia.desasignar(cliente)
    restaurada = bool((meta_conexion.cargar(cliente) or {}).get("token"))
    proyectos.guardar_meta_forma(cliente, "propia")
    nombre = proyectos.nombre_visible(cliente)
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"vuelve a modo propia (por el cliente {session.get('usuario')})")

    def _cuerpo_salida():   # en el idioma de cada admin (notificaciones.avisar_admin)
        if restaurada:
            return gettext("El proyecto %(nombre)s (%(cliente)s) volvió a usar su propia app de Meta "
                           "(su conexión anterior se restauró).", nombre=nombre, cliente=cliente)
        return gettext("El proyecto %(nombre)s (%(cliente)s) volvió a usar su propia app de Meta "
                       "(sin conexión todavía).", nombre=nombre, cliente=cliente)
    notificaciones.avisar_admin("meta_cambio_forma", lambda: gettext("%(nombre)s dejó el modo agencia", nombre=nombre),
                                _cuerpo_salida, cliente=cliente)
    detalle_restaurada = gettext("Tu conexión anterior se restauró.") if restaurada else gettext("Sigue los pasos para registrar tu app y conectar.")
    flash(gettext("Listo: este proyecto vuelve a usar su propia app de Meta. %(detalle)s", detalle=detalle_restaurada), "ok")
    return _ir_a_meta(cliente)


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
    # Solicitudes de clientes en forma «agencia» que no vieron sus activos (spec 2026-09-20 §2.4).
    solicitudes = meta_agencia.solicitudes()
    for s in solicitudes:
        s["nombre"] = proyectos.nombre_visible(s["cliente"])
    return render_template(
        "admin_meta.html",
        agencia=estado_ag, conectada=conectada, activos=activos, error_activos=error_activos,
        solicitudes=solicitudes, solicitudes_por_cliente={s["cliente"]: s for s in solicitudes},
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
        flash(gettext("No pude conectar la agencia: %(error)s", error=cola.sin_token(str(e))), "error")
        return _volver_admin_meta()
    bitacora.registrar("", "meta", "agencia", "ok", f"Business {registro.get('business_id')} conectado por {session.get('usuario')}")
    sin_nombre = gettext("sin nombre")
    flash(gettext("Agencia conectada: %(business)s (usuario del sistema %(usuario)s). "
                  "Ahora asigna cuenta y Página a cada proyecto.",
                  business=registro.get("business_nombre"), usuario=registro.get("usuario_nombre") or sin_nombre), "ok")
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
        flash(gettext("La agencia no estaba conectada."), "warn")
    elif n:
        flash(ngettext("Agencia desconectada. %(num)s proyecto volvió a modo propia y se quedan sin conexión con "
                       "Meta hasta que registren su app o vuelvas a asignarlos.",
                       "Agencia desconectada. %(num)s proyectos volvieron a modo propia y se quedan sin conexión con "
                       "Meta hasta que registren su app o vuelvas a asignarlos.", n), "ok")
    else:
        flash(gettext("Agencia desconectada. Ningún proyecto estaba asignado."), "ok")
    return _volver_admin_meta()


@app.route("/admin/meta/activos/actualizar", methods=["POST"])
@requiere_admin
def admin_meta_activos_actualizar():
    if not _mismo_origen():
        abort(403)
    try:
        activos = meta_agencia.listar_activos(forzar=True)
    except meta_conexion.MetaConexionError as e:
        flash(gettext("No pude leer los activos del Business: %(error)s", error=cola.sin_token(str(e))), "error")
        return _volver_admin_meta()
    flash(gettext("Activos actualizados: %(cuentas)s cuenta(s) publicitaria(s) y %(paginas)s Página(s).",
                  cuentas=len(activos["ad_accounts"]), paginas=len(activos["pages"])), "ok")
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
        flash(gettext("Elige una cuenta publicitaria para asignar."), "error")
        return _volver_admin_meta()
    try:
        detalle = meta_agencia.asignar(cliente, ad_account_id, page_id, asignado_por=session.get("usuario"))
    except meta_conexion.MetaConexionError as e:
        flash(gettext("No pude asignar %(proyecto)s: %(error)s",
                      proyecto=proyectos.nombre_visible(cliente), error=cola.sin_token(str(e))), "error")
        return _volver_admin_meta()
    cuenta = detalle.get("ad_account_nombre") or detalle.get("ad_account_id")
    pagina_real = detalle.get("page_nombre") or detalle.get("page_id")
    nombre = proyectos.nombre_visible(cliente)
    bitacora.registrar(cliente, "meta", "agencia", "ok",
                       f"asignado por {session.get('usuario')}: {cuenta} · {pagina_real or 'sin Página'}")
    meta_agencia.borrar_solicitud(cliente)  # asignar() ya la borra; acá también por si asignar fue reemplazado o falló a medias
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):   # el correo va en el idioma del proyecto
        sin_pagina = gettext("sin Página")
        asunto = gettext("Meta quedó conectado en Creatv")
        cuerpo = gettext("Tu proyecto %(nombre)s ya está conectado a Meta: cuenta %(cuenta)s · Página %(pagina)s. "
                         "Ya puedes probar piezas en Experimentos y publicar contenido.",
                         nombre=nombre, cuenta=cuenta, pagina=pagina_real or sin_pagina)
    notificaciones.avisar(cliente, "meta_conectado", asunto, cuerpo)
    ig = f" · Instagram @{detalle['ig_username']}" if detalle.get("ig_username") else ""
    pagina = pagina_real or gettext("sin Página")
    flash(gettext("%(proyecto)s ahora lo gestiona Creatv en Meta: %(cuenta)s · %(pagina)s%(ig)s.",
                  proyecto=nombre, cuenta=cuenta, pagina=pagina, ig=ig), "ok")
    if detalle.get("cambio_cuenta"):
        flash(gettext("La cuenta publicitaria cambió: los experimentos anteriores de ese proyecto dejan de refrescarse."),
              "warn")
    if page_id and not detalle.get("ig_username"):
        flash(gettext("Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincule en "
                      "Facebook."), "warn")
    if not page_id:
        flash(gettext("Sin Página asignada solo se pueden pautar anuncios; la publicación orgánica queda apagada para "
                      "ese proyecto."), "warn")
    return _volver_admin_meta()


@app.route("/admin/meta/desasignar/<cliente>", methods=["POST"])
@requiere_admin
def admin_meta_desasignar(cliente):
    if not _mismo_origen():
        abort(403)
    _cliente_o_404(cliente)
    if not meta_agencia.desasignar(cliente):
        flash(gettext("%(proyecto)s no estaba en modo agencia.", proyecto=proyectos.nombre_visible(cliente)), "warn")
        return _volver_admin_meta()
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"vuelve a modo propia (por {session.get('usuario')})")
    flash(gettext("%(proyecto)s volvió a modo propia: si tenía su propia conexión se restauró; "
                  "si no, tendrá que registrar su app y conectar con Meta.", proyecto=proyectos.nombre_visible(cliente)),
          "ok")
    return _volver_admin_meta()


@app.route("/admin/meta/solicitud/<cliente>/descartar", methods=["POST"])
@requiere_admin
def admin_meta_solicitud_descartar(cliente):
    if not _mismo_origen():
        abort(403)
    _cliente_o_404(cliente)
    if meta_agencia.borrar_solicitud(cliente):
        bitacora.registrar(cliente, "meta", "agencia", "ok", f"solicitud descartada por {session.get('usuario')}")
        flash(gettext("Solicitud descartada. %(proyecto)s no recibe aviso.", proyecto=proyectos.nombre_visible(cliente)),
              "ok")
    else:
        flash(gettext("Ese proyecto no tenía solicitud pendiente."), "warn")
    return _volver_admin_meta()


# ---------------------------------------------------- admin: referentes ---

@app.route("/admin/referentes")
@requiere_admin
def admin_referentes():
    """Biblioteca de referentes (spec 2026-09-23 §7-§8): importar copycoders,
    traer un barrido global (cliente=NULL) de Atria/Apify, y ver totales."""
    from referentes import datos as ref_datos, fuentes
    from referentes.fuentes.atria import limite_mensual, llamadas_este_mes
    from referentes.fuentes import trendtrack
    from referentes.rutas import _consulta_desde, _entero
    import gastos
    from tareas import referentes as tareas_ref

    historial = ref_datos.barridos(None, "copycoders")

    fuente = request.args.get("fuente") if request.args.get("fuente") in fuentes.tipos() else (fuentes.tipos()[0] if fuentes.tipos() else None)
    tope_traer = min(max(1, _entero(request.args.get("tope"), 200)), 2000)
    consulta_traer = _consulta_desde(request.args)
    fuente_llaves_faltantes = {t: fuentes.llaves_faltantes(t) for t in fuentes.tipos()}
    llaves_faltantes = fuentes.llaves_faltantes(fuente) if fuente else []
    precio_traer = None
    if (fuente and not llaves_faltantes and consulta_traer["modo"] in fuentes.modos(fuente)
            and (consulta_traer.get("pagina_id") or consulta_traer.get("palabra"))):
        modulo = fuentes.por_tipo(fuente)
        try:
            est_fuente = modulo.estimar(consulta_traer, tope_traer)
        except Exception:  # noqa: BLE001 — el precio es informativo, nunca bloquea la página
            est_fuente = None
        if est_fuente:
            est_clasificacion = gastos.estimar("clasificacion", n=tope_traer, bilingue=True)
            precio_traer = {"fuente": est_fuente, "clasificacion": est_clasificacion,
                            "total_usd": est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)}

    # Mismo cálculo por fila que `referentes.rutas.barridos` (per-cliente
    # «Mis barridos»): `trabajo` para la barra de progreso, `imagenes_error`
    # para ofrecer «Reintentar imágenes» solo cuando de verdad hay algo que
    # reintentar, `precio_clasificar` porque «Clasificar pendientes»
    # re-factura (spec §11) igual que en el panel por-cliente.
    barridos_otras_fuentes = [b for b in ref_datos.barridos(None) if b["fuente"] != "copycoders"]
    for b in barridos_otras_fuentes:
        b["trabajo"] = tareas_ref.trabajo_barrer(b["id"])
        b["imagenes_error"] = ref_datos.contar_imagenes_de_barrido(b["id"])[2]
        b["precio_clasificar"] = gastos.estimar("clasificacion", n=b["pendientes"], bilingue=True)["texto"] if b["pendientes"] else None

    familias_sin_en = ref_datos.familias_sin_descripcion_en()
    precio_familias_en = (gastos.formatear(tareas_ref.copycoders.estimar_describir_familias(
        [(f["nombre"], [f["descripcion"]]) for f in familias_sin_en], por_llamada=tareas_ref.FAMILIAS_POR_LLAMADA))
        if familias_sin_en else None)

    info_familias_en = trabajos.consultar(tareas_ref.JOB_FAMILIAS_EN)
    familias_en_error = ((info_familias_en.get("mensaje") or info_familias_en.get("error") or "")
                         if info_familias_en and info_familias_en.get("estado") == "error" else None)

    return render_template("admin_referentes.html", url_swipe=tareas_ref.copycoders.URL_SWIPE,
                           trabajo=({"job_id": tareas_ref.trabajo_importacion()} if tareas_ref.trabajo_importacion() else None),
                           ultimo=(historial[0] if historial else None), historial=historial[:10],
                           imagenes=ref_datos.contar_imagenes("copycoders"), total=ref_datos.opciones(None)["total"],
                           familias=ref_datos.familias(),
                           fuentes_tipos=fuentes.tipos(), fuentes_nombres=fuentes.NOMBRES,
                           fuente=fuente, consulta_traer=consulta_traer, tope_traer=tope_traer,
                           precio_traer=precio_traer, fuente_llaves_faltantes=fuente_llaves_faltantes,
                           atria_llamadas=llamadas_este_mes(), atria_limite=limite_mensual(),
                           trendtrack_creditos=trendtrack.creditos_este_mes(),
                           trendtrack_saldo=trendtrack.creditos_restantes(),
                           fuentes_totales=ref_datos.opciones(None)["fuentes"],
                           barridos_otras_fuentes=barridos_otras_fuentes,
                           familias_sin_en=familias_sin_en, precio_familias_en=precio_familias_en,
                           familias_en_en_curso=trabajos.en_curso(tareas_ref.JOB_FAMILIAS_EN),
                           familias_en_error=familias_en_error,
                           etiquetas_barrido=ref_datos.ETIQUETAS_ESTADO_BARRIDO)


@app.route("/admin/referentes/importar", methods=["POST"])
@requiere_admin
def admin_referentes_importar():
    if not _mismo_origen():
        abort(403)
    from tareas import referentes as tareas_ref
    url = (request.form.get("url") or "").strip() or tareas_ref.copycoders.URL_SWIPE
    if not url.startswith("https://go.copycoders.ai/"):
        flash(gettext("Solo se importa desde go.copycoders.ai."), "error")
        return redirect(url_for("admin_referentes"))
    if tareas_ref.encolar_importar_copycoders(url, pedido_por=_sesion().get("usuario")):
        flash(gettext("Importando el swipe file; la página se recarga sola cuando termine cada fase."), "ok")
    else:
        flash(gettext("Ya hay una importación en curso."), "error")
    return redirect(url_for("admin_referentes"))


@app.route("/admin/referentes/traer", methods=["POST"])
@requiere_admin
def admin_referentes_traer():
    if not _mismo_origen():
        abort(403)
    from referentes import fuentes
    from referentes.fuentes.base import ErrorFuente
    from referentes.rutas import _consulta_desde, _entero
    import gastos
    from tareas import referentes as tareas_ref

    fuente = request.form.get("fuente")
    if fuente not in fuentes.tipos():
        flash(gettext("Elige una fuente."), "error")
        return redirect(url_for("admin_referentes"))
    if fuentes.llaves_faltantes(fuente):
        flash(gettext("Esa fuente no está configurada."), "error")
        return redirect(url_for("admin_referentes"))
    consulta = _consulta_desde(request.form)
    if consulta["modo"] not in fuentes.modos(fuente):
        flash(gettext("Esa fuente no admite este tipo de búsqueda; busca por palabra clave o cambia de fuente."), "error")
        return redirect(url_for("admin_referentes"))
    if consulta["modo"] == "marca" and not consulta["pagina_id"]:
        flash(gettext("Pega un link del Ad Library o el id de la página."), "error")
        return redirect(url_for("admin_referentes"))
    if consulta["modo"] == "palabra" and not consulta["palabra"]:
        flash(gettext("Escribe una palabra clave."), "error")
        return redirect(url_for("admin_referentes"))
    from referentes import traducir
    try:
        consulta = traducir.preparar_consulta(consulta, None)     # palabra → inglés, idioma en (gasto a _creatv)
    except traducir.TraduccionInvalida as e:
        flash(str(e), "error")
        return redirect(url_for("admin_referentes"))
    tope = min(max(1, _entero(request.form.get("tope"), 200)), 2000)
    modulo = fuentes.por_tipo(fuente)
    try:
        est_fuente = modulo.estimar(consulta, tope)
    except ErrorFuente as e:
        flash(e.usuario, "error")
        return redirect(url_for("admin_referentes"))
    est_clasificacion = gastos.estimar("clasificacion", n=tope, bilingue=True)
    usd_estimado = est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)
    tareas_ref.encolar_barrer(None, fuente, consulta, tope, usd_estimado, pedido_por=_sesion().get("usuario"))
    flash(gettext("Trayendo referentes globales; aparecerán en la tabla de barridos a medida que avanza."), "ok")
    return redirect(url_for("admin_referentes"))


@app.route("/admin/referentes/familias/<int:familia_id>", methods=["POST"])
@requiere_admin
def admin_referentes_familia(familia_id):
    if not _mismo_origen():
        abort(403)
    from referentes import datos as ref_datos
    ref_datos.familia_actualizar(familia_id, request.form.get("descripcion") or "",
                                 descripcion_en=request.form.get("descripcion_en"))
    return redirect(url_for("admin_referentes"))


@app.route("/admin/referentes/familias/ingles", methods=["POST"])
@requiere_admin
def admin_referentes_familias_en():
    """Descripciones en inglés de las familias que faltan (spec 2026-09-26 §B7):
    una llamada a Claude por tanda de 40, precio junto al botón, gasto `otro`
    bajo `_creatv`."""
    if not _mismo_origen():
        abort(403)
    from tareas import referentes as tareas_ref
    if tareas_ref.encolar_familias_en(pedido_por=_sesion().get("usuario")):
        flash(gettext("Escribiendo en inglés las descripciones de las familias; recarga en un minuto."), "ok")
    else:
        flash(gettext("Ya se están escribiendo las descripciones en inglés."), "warn")
    return redirect(url_for("admin_referentes"))


def _barrido_global_o_404(ref_datos, barrido_id):
    """Igual que `referentes.rutas._barrido_del_cliente_o_404`, pero para el
    lado admin: un barrido GLOBAL (`cliente is None`) en vez de uno de un
    proyecto puntual. Nunca deja pasar un barrido con dueño real -- estas
    rutas admin no son una puerta trasera al barrido de un cliente."""
    b = ref_datos.barrido(barrido_id)
    if not b or b.get("cliente") is not None:
        abort(404)
    return b


@app.route("/admin/referentes/barridos/<int:barrido_id>/clasificar", methods=["POST"])
@requiere_admin
def admin_referentes_clasificar(barrido_id):
    """Reparo del hueco de Bloque 6: un barrido GLOBAL «parcial» (lanzado
    desde «Traer referentes globales») no tenía ningún botón para reintentar
    su clasificación -- su propio aviso invita a «Clasificar pendientes»,
    pero esa ruta es `referentes.rutas.clasificar_pendientes`, que exige
    `b.cliente == cliente` y por lo tanto siempre 404 para un barrido con
    `cliente=None`. Mismo comportamiento que la versión por-cliente, solo que
    gateada por "es global" en vez de "es de este proyecto"."""
    if not _mismo_origen():
        abort(403)
    from referentes import datos as ref_datos
    from tareas import referentes as tareas_ref
    _barrido_global_o_404(ref_datos, barrido_id)
    if tareas_ref.encolar_clasificar_pendientes(None, barrido_id):
        flash(gettext("Clasificando lo pendiente; la tabla se actualiza sola."), "ok")
    else:
        flash(gettext("Ya hay algo en curso para este barrido."), "error")
    return redirect(url_for("admin_referentes"))


@app.route("/admin/referentes/barridos/<int:barrido_id>/reintentar-imagenes", methods=["POST"])
@requiere_admin
def admin_referentes_reintentar_imagenes(barrido_id):
    """Mismo reparo que `admin_referentes_clasificar`, para «Reintentar
    imágenes» de un barrido global."""
    if not _mismo_origen():
        abort(403)
    from referentes import datos as ref_datos
    from tareas import referentes as tareas_ref
    _barrido_global_o_404(ref_datos, barrido_id)
    if tareas_ref.encolar_reintentar_imagenes(None, barrido_id):
        flash(gettext("Reintentando las imágenes que fallaron."), "ok")
    else:
        flash(gettext("Ya hay algo en curso para este barrido."), "error")
    return redirect(url_for("admin_referentes"))


@app.route("/cliente/<cliente>/ads/publicar", methods=["POST"])
def publicar_ad(cliente):
    """Publicar un anuncio suelto ya no tiene UI: Campañas se fundió en
    Experimentos y publicar es lanzar un experimento (exp_lanzar). La ruta se
    conserva para formularios viejos, pero no toca el anuncio ni encola nada
    (la tarea del worker `meta_publicar` sigue existiendo en tareas/meta.py)."""
    flash(gettext("Campañas ya no existe: crea un experimento con esa pieza."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/actualizar", methods=["POST"])
def actualizar_resultados_ad(cliente, ad_id):
    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry or not entry.get("meta_ids", {}).get("ad_id"):
        flash(gettext("Ese anuncio todavía no está publicado en Meta."), "error")
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
        flash(gettext("Actualizando resultados…"), "ok")
    else:
        flash(gettext("Ya se están actualizando."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/estado", methods=["POST"])
def cambiar_estado_ad(cliente, ad_id):
    """Pausar/activar la campaña real en Meta — la única acción de este
    módulo que puede hacer que empiece a gastarse presupuesto de verdad."""
    nuevo_estado = request.form.get("estado", "").strip()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        flash(gettext("Estado inválido."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    campaign_id = (entry or {}).get("meta_ids", {}).get("campaign_id")
    if not campaign_id:
        flash(gettext("Ese anuncio todavía no está publicado en Meta."), "error")
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
            flash(gettext("Listo.") if nuevo_estado == "ACTIVE" else gettext("Pausado."), "ok")
        except Exception as e:
            flash(gettext("No pude cambiar el estado: %(error)s", error=e), "error")
        finally:
            meta_auth.limpiar()
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/reintentar", methods=["POST"])
def reintentar_ad(cliente, ad_id):
    """Un anuncio que falló al publicar vuelve a "Listos para publicar" con su
    formulario, sin tener que quitarlo y agregarlo de nuevo."""
    entry = ads_mod.cargar(cliente).get(ad_id)
    if not entry or entry.get("estado") != "error":
        flash(gettext("Ese anuncio no está en error."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    ads_mod.actualizar(cliente, ad_id, estado="en_cola", error=None)
    flash(gettext("Listo para volver a publicar."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/ads/<ad_id>/eliminar", methods=["POST"])
def eliminar_ad(cliente, ad_id):
    """Solo borra la fila local — NO borra la campaña en Meta si ya se
    publicó (eso se hace desde Meta Ads Manager, a propósito: esta app nunca
    borra algo que ya está corriendo en la plataforma de otro)."""
    ads_mod.eliminar(cliente, ad_id)
    flash(gettext("Eliminado de la lista."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


# ---------- Tablero (Bloque 6) ----------

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
    """Etiqueta corta para el eje: 1,2 M / 250 k / 12 en español; 1.2 M / 250 k /
    12 en inglés (idiomas.separador_decimal — el recorte de ceros es a medida,
    así que no usa `idiomas.numero` completo)."""
    v = float(valor or 0)
    if v >= 1_000_000:
        t = f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".") + " M"
    elif v >= 1_000:
        t = f"{v / 1_000:.1f}".rstrip("0").rstrip(".") + " k"
    elif v == int(v):
        t = str(int(v))
    else:
        t = f"{v:.2f}".rstrip("0").rstrip(".")   # 0,5 y 0,25, no 0,50
    return t.replace(".", idiomas.separador_decimal())


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
        fecha_dia = date(int(d["dia"][0:4]), int(mm), int(dd))
        x = m["izq"] + i * paso
        gasto, ingresos = float(d["gasto"] or 0), float(d["ingresos"] or 0)
        salida.append({
            "dia": d["dia"], "gasto": gasto, "ingresos": ingresos, "compras": int(d.get("compras") or 0),
            "x": round(x, 2), "x_centro": round(x + paso / 2, 2), "ancho": round(ancho_barra, 2),
            "gasto_y": y_de(gasto), "ingresos_y": y_de(ingresos),
            "etiqueta": idiomas.dia_mes(fecha_dia) if i % 5 == 0 else "",
            "titulo": gettext("%(dd)s/%(mm)s · gasto %(gasto)s · ingresos %(ingresos)s",
                              dd=dd, mm=mm, gasto=tablero.dinero(gasto, moneda),
                              ingresos=tablero.dinero(ingresos, moneda)),
        })
    marcas = [{"valor": maximo * k / 4, "y": y_de(maximo * k / 4), "texto": _compacto(maximo * k / 4)} for k in range(5)]
    puntos = " ".join(f"{d['x_centro']},{d['ingresos_y']}" for d in salida)
    return {"ancho": _TB_ANCHO, "alto": _TB_ALTO, "margen": m, "base_y": base_y, "maximo": maximo, "moneda": moneda,
            "marcas": marcas, "dias": salida, "puntos_linea": puntos}


# La pestaña Triple Whale (Blueprint) pinta el mismo gráfico que el Tablero.
app.extensions["grafico_tablero"] = _grafico_tablero


@app.template_filter("dinero")
def _filtro_dinero(valor, moneda):
    """«1.250.000 COP» / «12,50 USD» (la misma regla que las alertas)."""
    return tablero.dinero(valor, moneda)


@app.template_filter("roas")
def _filtro_roas(valor):
    """ROAS con un decimal: 28,0 en español, 28.0 en inglés (idiomas.numero)."""
    return idiomas.numero(float(valor or 0), 1)


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
    out = {"ahora": ahora, "mes": idiomas.mes_largo(int(ahora[5:7])), "anio": ahora[:4], "errores": []}
    try:
        datos = tablero.cargar_datos(cliente, ahora)
    except Exception as e:  # noqa: BLE001 — sin carga compartida cada parte se las arregla sola
        datos = None
        print(f"[aviso] Tablero de {cliente}: no pude cargar los datos de una vez: {type(e).__name__}")
    partes = {
        "resumen": lambda: tablero.resumen_mes(cliente, ahora, datos=datos),
        "resumen_triple_whale": lambda: tablero.resumen_mes_triple_whale(cliente, ahora, datos=datos),
        # La tienda según Triple Whale (copia local, spec 2026-09-28 §13): sin conexión es None.
        "tienda_tw": lambda: triple_whale_panel.resumen_mes_tienda(cliente),
        "serie": lambda: tablero.serie_diaria(cliente, tablero.DIAS_SERIE, ahora, datos=datos),
        "serie_triple_whale": lambda: tablero.serie_diaria_triple_whale(cliente, tablero.DIAS_SERIE, ahora, datos=datos),
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
        out["grafico_triple_whale"] = _grafico_tablero(out["serie_triple_whale"]) if out["serie_triple_whale"] else None
    except Exception as e:  # noqa: BLE001 — el gráfico es una parte más: si falla, se muestra el resto
        out["grafico"] = None
        out["grafico_triple_whale"] = None
        out["errores"].append(f"grafico: {type(e).__name__}")
        print(f"[aviso] Tablero de {cliente}: no pude dibujar el gráfico: {type(e).__name__}")
    return out


# Caché en proceso del tablero: ver_cliente lo calcula en cada pestaña y en
# cada redirect tras un POST, así que se guarda 60 s por proyecto. La clave
# lleva además el estado que cambia lo que se ve (último snapshot, propuestas
# pendientes, experimentos) para que un refresco del worker o una acción del
# dueño lo invaliden al instante sin esperar el TTL. La clave del diccionario
# es (cliente, idiomas.activo()): dos personas viendo el mismo proyecto en
# idiomas distintos (o la misma cambiando el suyo) nunca comparten entrada, así
# que ninguna recibe el tablero calculado para el idioma de la otra. Con
# gunicorn multi-worker es por proceso: aceptable.
TABLERO_TTL_S = 60
_TABLERO_CACHE = {}          # (cliente, idioma) -> (monotonic, clave, contexto)
_TABLERO_LOCK = threading.Lock()


def _clave_tablero(cliente):
    """(último id de metrica_snapshot, propuestas pendientes, nº de
    experimentos y su último actualizado_en, último actualizado_en de pieza,
    nº y último actualizado_en de publicación orgánica) del proyecto: cinco
    consultas baratas con índice. Cualquier cambio que
    el tablero pinte (snapshot del worker, propuesta del motor, estado o
    veredicto tocado por el dueño, publicación orgánica) mueve la clave."""
    ms, ep, pr, ex, pub = db.metrica_snapshot, db.experimento_pieza, db.propuesta, db.experimento, db.publicacion
    tw = db.triple_whale
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
        # La tienda según Triple Whale (spec 2026-09-28 §13): conectar,
        # desconectar o una copia nueva mueven sus tiles.
        triple = con.execute(sa.select(sa.func.max(tw.c.actualizado_en)).where(tw.c.cliente == cliente)).scalar()
    return (ultimo_snap, propuestas_n, exps[0], exps[1], piezas, publicaciones[0], publicaciones[1], triple)


def invalidar_tablero(cliente=None):
    """Olvida el tablero cacheado de un proyecto, en todos los idiomas (o de
    todos los proyectos)."""
    with _TABLERO_LOCK:
        if cliente is None:
            _TABLERO_CACHE.clear()
        else:
            for clave_cache in [k for k in _TABLERO_CACHE if k[0] == cliente]:
                _TABLERO_CACHE.pop(clave_cache, None)


def _contexto_tablero(cliente):
    """`_calcular_tablero` con caché de `TABLERO_TTL_S` por proyecto e
    idioma, invalidada antes si cambia `_clave_tablero`. Si la clave no se
    puede consultar, se calcula sin caché."""
    try:
        clave = _clave_tablero(cliente)
    except Exception as e:  # noqa: BLE001 — sin clave no hay caché, pero sí tablero
        print(f"[aviso] Tablero de {cliente}: no pude leer la clave de caché: {type(e).__name__}")
        return _calcular_tablero(cliente)
    clave_cache = (cliente, idiomas.activo())
    ahora = time.monotonic()
    with _TABLERO_LOCK:
        entrada = _TABLERO_CACHE.get(clave_cache)
        if entrada and entrada[1] == clave and ahora - entrada[0] < TABLERO_TTL_S:
            return entrada[2]
    ctx = _calcular_tablero(cliente)
    with _TABLERO_LOCK:
        _TABLERO_CACHE[clave_cache] = (ahora, clave, ctx)
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

# Rótulos de cada `tipo` de la tabla `gasto` (gastos.TIPOS): constante de
# módulo que se muestra, marcada con N_ y traducida donde se usa
# ({{ valor|traducir }} en las plantillas) — nunca acá mismo (idiomas.py).
NOMBRES_TIPO_GASTO = {
    "video": idiomas.N_("Videos"), "imagen": idiomas.N_("Imágenes"), "swap": idiomas.N_("Cambios de producto"),
    "guion": idiomas.N_("Guiones"), "final": idiomas.N_("Finales"), "regla_producto": idiomas.N_("Reglas de producto (IA)"),
    "caption_organico": idiomas.N_("Textos orgánicos (IA)"), "musica": idiomas.N_("Música"),
    "locucion": idiomas.N_("Locuciones (audios)"),
    "refinar_prompt": idiomas.N_("Correcciones de prompt (Flow Plus)"), "guion_clips": idiomas.N_("Guiones a clips (Flow Plus)"),
    "ideas": idiomas.N_("Ideas de sprint (IA)"), "pedidos": idiomas.N_("Pedidos al cliente (IA)"),
    "revision": idiomas.N_("Revisión de la doctrina (IA)"),
    "evaluacion": idiomas.N_("Evaluación de anuncios (IA)"), "otro": idiomas.N_("Otros"),
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
    pauta» (la pauta solo si hay; la generación siempre, aunque sea 0).
    Traducido acá (no en la plantilla, que solo recibe el texto ya armado
    con `_('Este mes: %(gasto)s', ...)`, ver _sidebar.html)."""
    partes = [gettext("%(monto)s generación", monto=gastos.formatear((gasto_mes or {}).get('total') or 0))]
    for p in pauta_mes or []:
        partes.append(gettext("%(monto)s pauta", monto=tablero.dinero(p['gasto'], p['moneda'])))
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
        flash(gettext("Conecta Meta en Experimentos antes de crear un experimento."), "error")
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
        flash(gettext("Revisa los números del formulario."), "error")
        return volver
    # float("nan")/float("inf") no disparan ValueError arriba, y nan<=0 y
    # nan<minimo son ambos False — sin este chequeo un tope o presupuesto
    # NaN/inf crea el experimento y falla después en lanzador.centavos
    # (int(nan) -> ValueError), gastando el único intento del job.
    if not math.isfinite(tope) or any(not math.isfinite(p["presupuesto_dia"]) for p in paises):
        flash(gettext("Revisa los números del formulario."), "error")
        return volver
    if (not nombre or objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos
            or not destino.startswith(("http://", "https://")) or not (1 <= dias <= 90) or tope <= 0
            or not (13 <= edad_min <= edad_max <= 65)):
        flash(gettext("Faltan datos: nombre, objetivo, al menos un país, días (1–90), tope, edades (13–65) "
                      "y una URL de destino http(s)."), "error")
        return volver
    # Meta interpreta daily_budget en la moneda de FACTURACIÓN de la cuenta
    # publicitaria, sin importar qué país apunte ese adset (una cuenta en COP
    # que le pega a México sigue fijando el presupuesto de ese adset en COP).
    # Por eso el mínimo se valida contra la moneda de la cuenta, no la del país.
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(gettext("El presupuesto diario no alcanza el mínimo de Meta (%(minimo)s %(moneda)s) en: %(paises)s.",
                      minimo=minimo, moneda=moneda, paises=", ".join(bajos)), "error")
        return volver
    modo = request.form.get("modo") or "manual"
    if modo not in modos.MODOS:
        modo = "manual"   # nunca se sube de puerta por un valor raro en el form
    # Atribución opcional en el form; sin ella, experimentos.crear usa la
    # sugerida (Pixel vivo → pixel, tienda conectada → tienda, si no ninguna).
    atribucion = request.form.get("atribucion") or None
    if atribucion is not None and atribucion not in experimentos.ATRIBUCIONES:
        flash(gettext("La atribución tiene que ser pixel, tienda o ninguna."), "error")
        return volver
    # Bloque 6: optimizar por compras exige que Meta vea las compras, o sea
    # el Pixel disparando y atribución pixel. El objetivo no se puede cambiar
    # después de lanzar (Meta no lo permite), así que se corta acá y no en
    # el lanzador, donde ya sería un experimento armado que no puede salir.
    if objetivo == "OUTCOME_SALES" and (atribucion or experimentos.atribucion_sugerida(cliente)) != "pixel":
        flash(gettext("Optimizar por compras requiere el Pixel activo y atribución pixel: pulsa «Comprobar Pixel» en "
                      "Configuración, o elige el objetivo de tráfico."), "error")
        return volver
    eid = experimentos.crear(cliente, nombre, paises, objetivo, dias, tope, destino, moneda, edad_min, edad_max,
                             modo=modo, atribucion=atribucion)
    ex = experimentos.obtener(cliente, eid)
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        # Texto guardado (bitácora): en el idioma del proyecto (spec 2026-09-26
        # §B3). `modo` (manual/semi/auto) no se traduce, como en el <select>;
        # `atribucion` sí tiene rótulo (experimentos.ETIQUETAS_ATRIBUCION).
        experimentos.registrar_evento(
            cliente, eid, "creado",
            gettext("Experimento creado con %(n)s países (modo %(modo)s, atribución %(atribucion)s)",
                    n=len(paises), modo=modo,
                    atribucion=idiomas.traducir(experimentos.ETIQUETAS_ATRIBUCION.get(ex["atribucion"], ex["atribucion"]))))
    flash(gettext("Experimento «%(nombre)s» creado. Agrega piezas y lánzalo cuando esté listo.", nombre=nombre), "ok")
    return volver


def nombre_experimento_automatico(n_piezas, paises, cuando=None):
    """«Prueba 20 sept · 3 piezas · CO, MX» — el nombre que la galería propone,
    en el idioma de quien lo crea (fecha de CLDR, spec 2026-09-26 §B1)."""
    cuando = cuando or datetime.now().date()
    return gettext("Prueba %(fecha)s · %(piezas)s · %(paises)s", fecha=idiomas.fecha_corta(cuando),
                   piezas=ngettext("%(num)s pieza", "%(num)s piezas", n_piezas), paises=", ".join(sorted(paises)))


@app.route("/cliente/<cliente>/experimentos/probar", methods=["POST"])
def exp_probar(cliente):
    """La galería primero: un solo POST crea el experimento, reparte las
    piezas por país y encola el lanzamiento (todo PAUSED en Meta). Valida lo
    mismo que exp_crear; si algo falla no queda nada creado. Activar sigue
    siendo un clic aparte."""
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if meta_conexion.estado(cliente).get("estado") != "conectado":
        flash(gettext("Conecta Meta en Experimentos antes de probar piezas."), "error")
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
        flash(gettext("Revisa los números del formulario."), "error")
        return volver
    if not math.isfinite(tope) or any(not math.isfinite(p["presupuesto_dia"]) for p in paises):
        flash(gettext("Revisa los números del formulario."), "error")
        return volver
    if not piezas_ids:
        flash(gettext("Marca al menos una pieza en la galería."), "error")
        return volver
    if not codigos:
        # Antes de filtrar las combinaciones por país: sin país quedarían
        # vacías y el aviso hablaría de la cuadrícula, no del país.
        flash(gettext("Marca al menos un país."), "error")
        return volver
    combinaciones = [(pid, pais) for pid, pais in combinaciones if pid in piezas_ids and pais in codigos]
    if not combinaciones:
        flash(gettext("Marca al menos una combinación pieza × país en el paso de revisar."), "error")
        return volver
    if (objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos
            or not destino.startswith(("http://", "https://")) or not (1 <= dias <= 90) or tope <= 0
            or not (13 <= edad_min <= edad_max <= 65)):
        flash(gettext("Faltan datos: objetivo, al menos un país, días (1–90), tope, edades (13–65) y una URL de destino http(s)."), "error")
        return volver
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(gettext("El presupuesto diario no alcanza el mínimo de Meta (%(minimo)s %(moneda)s) en: %(paises)s.",
                      minimo=minimo, moneda=moneda, paises=", ".join(bajos)), "error")
        return volver
    modo = request.form.get("modo") or "manual"
    if modo not in modos.MODOS:
        modo = "manual"
    atribucion = request.form.get("atribucion") or None
    if atribucion is not None and atribucion not in experimentos.ATRIBUCIONES:
        flash(gettext("La atribución tiene que ser pixel, tienda o ninguna."), "error")
        return volver
    if objetivo == "OUTCOME_SALES" and (atribucion or experimentos.atribucion_sugerida(cliente)) != "pixel":
        flash(gettext("Optimizar por compras requiere el Pixel activo y atribución pixel: pulsa «Comprobar Pixel» en "
                      "Configuración, o elige el objetivo de tráfico."), "error")
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
        flash(gettext("«%(nombre)s»: lanzando a Meta en pausa. Cuando termine, actívalo desde su tarjeta.", nombre=nombre), "ok")
    else:
        flash(gettext("«%(nombre)s» quedó creado; ya se estaba lanzando.", nombre=nombre), "warn")
    return volver


def _agregar_pieza_validada(cliente, experimento_id, pieza_id, pais):
    """Valida y agrega una pieza (final o clon) a un experimento en armado.
    Devuelve un mensaje de error en español, o None si quedó agregada.
    Compartida por exp_agregar_pieza y exp_meter_pieza (Crear -> Experimentos)."""
    ex = experimentos.obtener(cliente, experimento_id)
    if not ex:
        return gettext("Ese experimento no existe.")
    if ex["estado"] not in ("armando", "error") or ex["meta_campaign_id"]:
        return gettext("Ese experimento ya no acepta piezas nuevas.")
    candidata = next((p for p in experimentos.elegibles(cliente) if p["pieza_id"] == pieza_id), None)
    if not candidata:
        return gettext("Esa pieza no está disponible (o no está lista).")
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
        flash(gettext("No encontré esa pieza."), "error")
    else:
        error = _agregar_pieza_validada(cliente, eid, pieza_id, pais)
        flash(error, "error") if error else flash(gettext("Pieza agregada."), "ok")
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
        flash(gettext("Ese experimento ya no acepta cambios de piezas."), "error")
    elif experimentos.quitar_pieza(cliente, eid, ep_id):
        flash(gettext("Pieza quitada."), "ok")
    else:
        flash(gettext("No pude quitar esa pieza (¿ya está en Meta?)."), "error")
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
        flash(gettext("No encontré esa pieza o ese experimento."), "error")
    else:
        error = _agregar_pieza_validada(cliente, experimento_id, pieza_id, pais)
        flash(error, "error") if error else flash(gettext("Pieza enviada al experimento."), "ok")
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
        flash(gettext("Ese experimento no existe."), "error")
        return volver
    if ex["estado"] not in ("armando", "error"):
        flash(gettext("Ese experimento ya fue lanzado."), "error")
        return volver
    if not ex["piezas"]:
        flash(gettext("El experimento no tiene piezas: agrega al menos una antes de lanzar."), "error")
        return volver
    paises_con_piezas = {p["pais"] for p in ex["piezas"]}
    faltan = [p["pais"] for p in ex["paises"] if p["pais"] not in paises_con_piezas]
    if faltan:
        flash(gettext("Sin piezas para: %(paises)s. Agrega una pieza por país o quita el país.",
                      paises=", ".join(faltan)), "error")
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
        flash(gettext("Lanzando el experimento a Meta (queda en pausa)…"), "ok")
    else:
        flash(gettext("Ya se está lanzando ese experimento."), "warn")
    return volver


@app.route("/cliente/<cliente>/experimentos/<int:eid>/estado", methods=["POST"])
def exp_estado(cliente, eid):
    estado = (request.form.get("estado") or "").strip()
    pais = (request.form.get("pais") or "").strip() or None
    if estado not in ("ACTIVE", "PAUSED"):
        flash(gettext("Estado inválido."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    with _ENV_LOCK:
        try:
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                lanzador.cambiar_estado(cliente, eid, estado, pais=pais)
            flash(gettext("Listo.") if estado == "ACTIVE" else gettext("Pausado."), "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(gettext("No pude cambiar el estado: %(error)s", error=cola.sin_token(str(e))), "error")
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
        flash(gettext("El presupuesto debe ser un número."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if not math.isfinite(presupuesto_dia) or presupuesto_dia < minimo:
        flash(gettext("El presupuesto diario mínimo es %(minimo)s %(moneda)s.", minimo=minimo, moneda=moneda), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    with _ENV_LOCK:
        try:
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                lanzador.cambiar_presupuesto_pais(cliente, eid, pais, presupuesto_dia)
            flash(gettext("Presupuesto actualizado."), "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(gettext("No pude cambiar el presupuesto: %(error)s", error=cola.sin_token(str(e))), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/refrescar", methods=["POST"])
def exp_refrescar(cliente, eid):
    ex = experimentos.obtener(cliente, eid)
    if not ex or not ex["meta_campaign_id"]:
        flash(gettext("Ese experimento todavía no está en Meta."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    job_id = tareas_exp.job_id_refrescar(cliente, eid)
    # M10: max_intentos=2 como la periódica (tareas/experimentos.py) — refrescar
    # nunca gasta, así que no hay razón para ser más estricto acá que allá.
    arranco = trabajos.encolar(job_id, "exp_refrescar", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=30, max_intentos=2)
    if arranco:
        flash(gettext("Actualizando resultados…"), "ok")
    else:
        flash(gettext("Ya se están actualizando."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/experimentos/<int:eid>/cerrar", methods=["POST"])
def exp_cerrar(cliente, eid):
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash(gettext("Ese experimento no existe."), "error")
        return volver
    if ex["estado"] == "cerrado":
        flash(gettext("Ese experimento ya estaba cerrado."), "ok")
        return volver
    # "lanzando" nunca se cierra desde acá: el worker está a mitad de crear
    # campaña/adsets/anuncios en Meta y, al terminar, vuelve a escribir
    # "pausado" (lanzador.lanzar) — un "cerrado" acá se perdería y dejaría
    # los objetos ya creados en Meta sin que el experimento se entere. Solo
    # se puede cerrar desde armando/error (nunca se lanzó) o pausado/corriendo
    # (ya está en Meta).
    if ex["estado"] not in ("pausado", "corriendo", "armando", "error"):
        flash(gettext("Espera a que termine el lanzamiento antes de cerrar."), "error")
        return volver
    with _ENV_LOCK:
        try:
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                lanzador.cerrar(cliente, eid)
            flash(gettext("Experimento cerrado."), "ok")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(gettext("No pude cerrar el experimento: %(error)s", error=cola.sin_token(str(e))), "error")
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
        flash(gettext("Ese experimento no existe."), "error")
        return _volver_exp(cliente)
    if modo not in modos.MODOS:
        flash(gettext("Modo inválido."), "error")
        return _volver_exp(cliente)
    if ex["estado"] == "cerrado":
        flash(gettext("Un experimento cerrado no cambia de modo."), "error")
        return _volver_exp(cliente)
    if modo != ex["modo"]:
        experimentos.actualizar(cliente, eid, modo=modo)
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            experimentos.registrar_evento(cliente, eid, "modo",
                                          gettext("Modo cambiado de %(antes)s a %(despues)s.",
                                                  antes=ex["modo"], despues=modo),
                                          {"antes": ex["modo"], "despues": modo})
    flash(gettext("Modo: %(modo)s.", modo=modo), "ok")
    return _volver_exp(cliente)


def _flash_reglas_invalidas(errores):
    nombres = ", ".join(errores)
    flash(gettext("Revisa estos valores, deben ser números: %(nombres)s. No se guardó nada.", nombres=nombres), "error")


@app.route("/cliente/<cliente>/experimentos/<int:eid>/reglas", methods=["POST"])
def exp_reglas(cliente, eid):
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash(gettext("Ese experimento no existe."), "error")
        return _volver_exp(cliente)
    reglas, errores = decisor.reglas_desde_formulario(request.form)
    if errores:
        _flash_reglas_invalidas(errores)
        return _volver_exp(cliente)
    experimentos.actualizar(cliente, eid, reglas=reglas)
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        experimentos.registrar_evento(cliente, eid, "reglas", gettext("Reglas del experimento actualizadas."),
                                      {"reglas": reglas})
    flash(gettext("Reglas guardadas. Lo vacío hereda de Configuración."), "ok")
    return _volver_exp(cliente)


@app.route("/cliente/<cliente>/experimentos/<int:eid>/decidir", methods=["POST"])
def exp_decidir_ahora(cliente, eid):
    """Encola una pasada del decisor. Evaluar no gasta por sí mismo: lo que
    gasta pasa por la puerta del modo (acciones.pedir) y en manual/semi queda
    como propuesta."""
    ex = experimentos.obtener(cliente, eid)
    if not ex or ex["estado"] != "corriendo":
        flash(gettext("Solo se evalúa un experimento que está corriendo."), "error")
        return _volver_exp(cliente)
    job_id = tareas_exp.job_id_decidir(cliente, eid)
    arranco = trabajos.encolar(job_id, "exp_decidir", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=60, max_intentos=1)
    flash(gettext("Evaluando…") if arranco else gettext("Ya se está evaluando."), "ok" if arranco else "warn")
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
    Va bajo _ENV_LOCK porque acciones.ejecutar puede tocar Meta. El mensaje
    que se devuelve (para el flash) sale en el idioma de quien mira —
    acciones.ejecutar ya deja, en el idioma del proyecto, el evento que
    queda en la bitácora (spec 2026-09-26 §B3: lo que se guarda sigue al
    proyecto, lo que responde una ruta sigue a quien mira)."""
    with _ENV_LOCK:
        try:
            mensaje = acciones.ejecutar(cliente, pr["experimento_id"], pr["accion"], pr["payload"],
                                        propuesta_id=pr["id"], ep_id_evento=_ep_id_evento(cliente, pr))
        except ValueError as e:
            propuestas.reabrir(cliente, pr["id"])
            return str(e)
        except Exception as e:  # noqa: BLE001
            propuestas.reabrir(cliente, pr["id"])
            return gettext("No pude ejecutar «%(accion)s»: %(error)s", accion=pr["accion"], error=cola.sin_token(str(e)))
    propuestas.marcar_ejecutada(cliente, pr["id"])
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
        return payload, gettext("Marca al menos una plataforma para publicar.")
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
        flash(gettext("Esa propuesta no existe o ya estaba resuelta."), "error")
        return _volver_exp(cliente)
    payload, error = (_overrides_organico(cliente, request.form, pr["payload"]) if pr["accion"] == "publicar_organico"
                      else (pr["payload"], None))
    if error:
        flash(error, "error")
        return _volver_exp(cliente)
    pr = propuestas.resolver(cliente, pid, "aprobada")
    if not pr:
        flash(gettext("Esa propuesta no existe o ya estaba resuelta."), "error")
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
        flash(gettext("Esa propuesta no existe o ya estaba resuelta."), "error")
        return _volver_exp(cliente)
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        experimentos.registrar_evento(
            cliente, pr["experimento_id"], "propuesta",
            gettext("Propuesta #%(id)s (%(accion)s) rechazada a mano.", id=pr["id"],
                    accion=idiomas.traducir(acciones.ETIQUETAS_ACCION.get(pr["accion"], pr["accion"]))),
            {"accion": pr["accion"], "payload": pr["payload"], "propuesta_id": pr["id"]},
            ep_id=_ep_id_evento(cliente, pr))
    flash(gettext("Propuesta rechazada."), "ok")
    return _volver_exp(cliente)


@app.route("/cliente/<cliente>/experimentos/<int:eid>/propuestas/aprobar_todas", methods=["POST"])
def prop_aprobar_todas(cliente, eid):
    """Aprueba y ejecuta en orden de creación; en el primer error se detiene:
    esa propuesta vuelve a pendiente y las que siguen se quedan pendientes
    (no se aprueban), para que la persona decida con el error a la vista."""
    ex = experimentos.obtener(cliente, eid)
    if not ex:
        flash(gettext("Ese experimento no existe."), "error")
        return _volver_exp(cliente)
    pendientes = propuestas.pendientes(cliente, eid)
    if not pendientes:
        flash(gettext("No había propuestas pendientes."), "ok")
        return _volver_exp(cliente)
    hechas = 0
    for pr in pendientes:
        aprobada = propuestas.resolver(cliente, pr["id"], "aprobada")
        if not aprobada:
            continue   # alguien la resolvió entre medio
        error = _ejecutar_propuesta(cliente, aprobada)
        if error:
            flash(gettext("Me detuve en la propuesta #%(id)s (%(accion)s): %(error)s",
                          id=pr["id"], accion=pr["accion"], error=error), "error")
            break
        hechas += 1
    if hechas:
        flash(gettext("%(hechas)s propuesta(s) ejecutada(s).", hechas=hechas), "ok")
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
    Final edition (final; desde 2026-09-27 las finales viven ahí), Crear
    (creativeflowplus: formularios pintados antes de la mudanza) o
    Experimentos (por defecto)."""
    volver = request.form.get("volver")
    anchor = volver if volver in ("final", "creativeflowplus") else "experimentos"
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
    return ", ".join(idiomas.traducir(organico.PLATAFORMAS.get(p, {}).get("nombre", p)) for p in plataformas)


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
        # Se GUARDA en la fila: idioma del proyecto, no el de quien mira.
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            error = gettext("Ya había una publicación de esta pieza en curso; reintenta cuando termine.")
        for pub_id in pub_ids:
            organico.actualizar(cliente, pub_id, estado="error", error=error)
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
        return jsonify({"error": gettext("Elige la pieza y al menos una plataforma.")}), 400
    try:
        textos = organico.redactar(cliente, pieza_id, plataformas)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — el error vuelve al form, nunca un token
        return jsonify({"error": gettext("No pude redactar el texto: %(error)s", error=cola.sin_token(str(e)))}), 500
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
        flash(gettext("No encontré esa pieza."), "error")
        return _volver_org(cliente)
    pedidas = [p for p in organico.ORDEN if p in request.form.getlist("plataformas")]
    if not pedidas:
        flash(gettext("Marca al menos una plataforma para publicar."), "error")
        return _volver_org(cliente)
    canales = {c["plataforma"]: c for c in organico.canales(cliente)}
    sin_canal = [p for p in pedidas if not canales[p]["disponible"]]
    if sin_canal:
        flash(gettext("Sin canal conectado: %(canales)s. Actívalo en Configuración › Canales orgánicos. No se publicó nada.",
                      canales="; ".join(f"{idiomas.traducir(canales[p]['nombre'])} ({idiomas.traducir(canales[p]['motivo'])})"
                                       for p in sin_canal)), "error")
        return _volver_org(cliente)
    textos = {p: {"caption": (request.form.get(f"caption_{p}") or "").strip(),
                  "titulo": (request.form.get(f"titulo_{p}") or "").strip() or None} for p in pedidas}
    sin_texto = [p for p in pedidas if not textos[p]["caption"]]
    if sin_texto:
        flash(gettext("Falta el texto para %(plataformas)s: escríbelo o pulsa «Escribir texto con IA». "
                      "No se publicó nada.", plataformas=_nombres_org(sin_texto)), "error")
        return _volver_org(cliente)
    try:
        textos = organico.normalizar_captions(cliente, pieza_id, textos)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_org(cliente)
    if trabajos.en_curso(tareas_org.job_id_publicar(cliente, pieza_id)):
        flash(gettext("Ya hay una publicación orgánica de esta pieza en curso; espera a que termine."), "warn")
        return _volver_org(cliente)

    pub_ids, creadas, saltadas = [], [], []
    for p in pedidas:
        try:
            pub_ids.append(organico.crear(cliente, pieza_id, p, textos[p]["caption"], titulo=textos[p]["titulo"],
                                          origen="manual", ep_id=ep_id))
            creadas.append(p)
        except organico.YaPublicada:
            saltadas.append(p)
            continue
        except ValueError as e:
            # Creación parcial: lo ya creado no puede quedar `en_cola` sin tarea
            # (bloquearía la plataforma por unicidad); en `error` se reintenta.
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):     # se guarda: idioma del proyecto
                error = gettext("No se creó la publicación en %(plataformas)s: %(error)s",
                                plataformas=_nombres_org([p]), error=e)
            for pub_id in pub_ids:
                organico.actualizar(cliente, pub_id, estado="error", error=error)
            flash(gettext("%(error)s No se publicó nada.", error=e), "error")
            return _volver_org(cliente)
    if saltadas:
        flash(gettext("Ya estaba publicada (o en cola) en %(plataformas)s: no se publica dos veces.",
                      plataformas=_nombres_org(saltadas)), "warn")
    if not pub_ids:
        return _volver_org(cliente)
    if not _encolar_organico(cliente, pieza_id, pub_ids):
        flash(gettext("Ya había una publicación de esta pieza en curso; las nuevas quedaron para reintentar."), "error")
        return _volver_org(cliente)
    if ep_id:
        eid = experimentos.experimento_de_pieza(cliente, ep_id)
        if eid:
            experimentos.marcar_pieza(cliente, ep_id, publicado_organico=True)
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                experimentos.registrar_evento(
                    cliente, eid, "accion",
                    gettext("Publicación orgánica en cola a mano: %(plataformas)s.", plataformas=_nombres_org(creadas)),
                    {"accion": "publicar_organico", "plataformas": creadas, "publicaciones": pub_ids}, ep_id=ep_id)
    flash(gettext("Publicación orgánica en cola: %(plataformas)s. Te avisamos cuando salga.",
                  plataformas=_nombres_org(creadas)), "ok")
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
        flash(gettext("Esa publicación no existe."), "error")
        return _volver_org(cliente)
    if pub["estado"] != "error":
        flash(gettext("Solo se reintenta una publicación que falló."), "error")
        return _volver_org(cliente)
    if pub["id_externo"]:
        flash(gettext("Esa publicación ya se subió a %(plataforma)s (id %(id)s); "
                      "revisa la plataforma antes de volver a publicarla.",
                      plataforma=idiomas.traducir(pub["nombre_plataforma"]), id=pub["id_externo"]), "warn")
        return _volver_org(cliente)
    vivas = {p["plataforma"] for p in organico.listar(cliente, pieza_id=pub["pieza_id"])
             if p["estado"] in organico.ESTADOS_VIVOS}
    if pub["plataforma"] in vivas:
        flash(gettext("Ya hay una publicación en curso o publicada para %(plataforma)s; no se reintenta.",
                      plataforma=idiomas.traducir(pub["nombre_plataforma"])), "warn")
        return _volver_org(cliente)
    if trabajos.en_curso(tareas_org.job_id_publicar(cliente, pub["pieza_id"])):
        flash(gettext("Ya hay una publicación orgánica de esta pieza en curso; espera a que termine."), "warn")
        return _volver_org(cliente)
    try:
        organico.actualizar(cliente, pub_id, estado="en_cola", error=None)
    except ValueError as e:
        # Carrera con otra creación entre el chequeo y el UPDATE: gana el índice.
        flash(str(e), "warn")
        return _volver_org(cliente)
    if not _encolar_organico(cliente, pub["pieza_id"], [pub_id]):
        flash(gettext("Ya había una publicación de esta pieza en curso; vuelve a intentarlo cuando termine."), "error")
        return _volver_org(cliente)
    flash(gettext("Reintentando en %(plataforma)s.", plataforma=idiomas.traducir(pub["nombre_plataforma"])), "ok")
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
    flash(gettext("Reglas por defecto guardadas."), "ok")
    return volver


_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/cliente/<cliente>/config/correo", methods=["POST"])
def cfg_correo(cliente):
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))
    correo = (request.form.get("correo") or "").strip()
    if correo and not _CORREO_RE.match(correo):
        flash(gettext("Ese correo no parece válido."), "error")
        return volver
    proyectos.guardar_correo_notificaciones(cliente, correo)
    flash(gettext("Correo guardado.") if correo else gettext("Avisos por correo desactivados."), "ok")
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
    return _volver_catalogo(cliente)


def _volver_catalogo(cliente, cat=None, activo_id=None):
    """Volver a la pestaña Catálogo; con `cat` + `activo_id`, con la ficha de
    ese producto abierta (`#catalogo?ficha=<cat>:<pid>`, spec §10.3)."""
    ancla = "catalogo"
    if cat and activo_id:
        ancla = f"catalogo?ficha={cat}:{catalogo_productos.producto_base(activo_id)}"
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=ancla))


def _volver_fila(cliente, pid):
    """Las rutas prod_* (fila `producto` por id numérico) vuelven a la ficha
    del activo de esa fila si lo tiene; si no, a la galería."""
    fila = tiendas.producto(cliente, pid) if pid else None
    activo = (fila or {}).get("activo_catalogo_id")
    if activo and catalogo_productos.existe(cliente, activo, "producto"):
        return _volver_catalogo(cliente, "producto", activo)
    return _volver_catalogo(cliente)


def _volver_config(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


def _experimentos_por_activo(cliente, experimentos_exp=None, sesiones_cf=None):
    """{clave en minúsculas (casefold): {experimento_id, ...}} donde clave es
    el NOMBRE visible del activo (lo que Crear guarda en `productos_ids`) o
    su id — en minúsculas para que un color («Original — Pink») case con el
    nombre de cualquiera de sus claves. Una pasada por las sesiones de Crear y
    otra por las piezas de cada experimento — nunca una consulta por
    producto. La pieza de un experimento apunta a su sesión de Crear por el
    prefijo de `legado_id` (`<cf_id>` o `<cf_id>__<idioma>_<pais>`).
    `experimentos_exp`/`sesiones_cf` (`creative_flow.cargar(cliente)`, ya con
    su cf_id) se leen aquí solo si el llamador no los trae: quien ya cargó
    esas dos fuentes para otra cosa en el mismo request las pasa y esta
    función no vuelve a pedirlas (auditoría 2026-09-28)."""
    if experimentos_exp is None:
        experimentos_exp = experimentos.cargar(cliente)
    if sesiones_cf is None:
        sesiones_cf = creative_flow.cargar(cliente)
    claves_por_cf = {}
    for cf_id, entry in sesiones_cf.items():
        claves = {str(x).casefold() for x in (entry.get("productos_ids") or []) if x}
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


def _productos_tienda_contexto(cliente, experimentos_exp=None, por_clave=None):
    """Productos (con archivados: el filtro es de la galería) enriquecidos
    con `activo_ok` (su activo existe en el catálogo) y `n_experimentos`
    (experimentos con piezas hechas con ese producto o cualquiera de sus
    colores, por id o por nombre). `por_clave` (_experimentos_por_activo(...))
    se calcula aquí solo si no lo trae ya el llamador."""
    if por_clave is None:
        por_clave = _experimentos_por_activo(cliente, experimentos_exp)
    claves_por_pid = {p["id"]: catalogo_productos.claves_de(p)
                      for p in catalogo_productos.listar_productos(cliente, "producto")}
    lista = tiendas.productos(cliente, incluir_archivados=True)
    for prod in lista:
        activo_id = prod.get("activo_catalogo_id")
        prod["activo_ok"] = bool(activo_id) and catalogo_productos.existe(cliente, activo_id, "producto")
        claves = claves_por_pid.get(activo_id) or {"ids": {str(activo_id or "").casefold()} - {""}, "nombres": set()}
        ids_exp = set()
        for k in claves["ids"] | claves["nombres"] | ({str(prod.get("nombre") or "").casefold()} - {""}):
            ids_exp |= por_clave.get(k, set())
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
# «Sincronizado de …»). Los que no son "manual" son nombres de marca (no se
# traducen; se marcan igual con N_ para que el diccionario sea parejo — su
# msgstr es el mismo texto).
ETIQUETAS_FUENTE = {"manual": idiomas.N_("manual"), "csv": idiomas.N_("CSV/Excel"), "url": idiomas.N_("URL"),
                    "shopify": idiomas.N_("Shopify"), "woo": idiomas.N_("WooCommerce"), "meli": idiomas.N_("MercadoLibre")}


def _trabajos_productos(cliente, tiendas_cliente, productos=()):
    """{"importar": {"job_id"} | None, "tiendas": {tid: {"job_id"}},
    "vincular": {pid: {"job_id"}}}: qué importación, sincronización o
    «Crear activo» está corriendo, para pintar la barra. Los `vincular` salen
    de UNA consulta a la cola (cola.job_ids_vivos), no de una por producto."""
    vivos = cola.job_ids_vivos(cliente, "producto_vincular") if productos else set()
    # «Actualizar lo que Claude necesita» (doctrina, bloque 2), también en una sola consulta.
    vivos_pedidos = cola.job_ids_vivos(cliente, tareas_doctrina.TIPO_PEDIDOS) if productos else set()
    pedidos = {prod["id"]: {"job_id": tareas_doctrina.job_id_pedidos(cliente, prod["id"])} for prod in productos
               if tareas_doctrina.job_id_pedidos(cliente, prod["id"]) in vivos_pedidos}
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
    return {"importar": importar, "tiendas": por_tienda, "vincular": vincular, "pedidos": pedidos}


@app.route("/cliente/<cliente>/productos/importar/archivo", methods=["POST"])
def prod_importar_archivo(cliente):
    """Tope de 5 MB por ruta, no `MAX_CONTENT_LENGTH` global: personajes y
    marca suben videos de referencia (mp4/mov) que pasan de largo cualquier
    tope razonable para un CSV. El `Content-Length` se mira antes de leer el
    archivo para no copiar un upload enorme que se va a rechazar igual."""
    if request.content_length and request.content_length > IMPORTAR_MAX_BYTES * 2:
        # x2: el multipart trae cabeceras y el resto del formulario; el tope
        # exacto lo aplica la lectura de abajo.
        flash(gettext("El archivo pesa más de 5 MB. Divídelo o quita columnas que no usamos."), "error")
        return _volver_productos(cliente)
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash(gettext("Elige un archivo .csv o .xlsx."), "error")
        return _volver_productos(cliente)
    nombre = secure_filename(archivo.filename) or "catalogo"
    if os.path.splitext(nombre.lower())[1] not in IMPORTAR_EXTENSIONES:
        flash(gettext("Solo se aceptan archivos .csv o .xlsx."), "error")
        return _volver_productos(cliente)
    datos = archivo.read(IMPORTAR_MAX_BYTES + 1)
    if not datos:
        flash(gettext("El archivo está vacío."), "error")
        return _volver_productos(cliente)
    if len(datos) > IMPORTAR_MAX_BYTES:
        flash(gettext("El archivo pesa más de 5 MB. Divídelo o quita columnas que no usamos."), "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_importar_archivo(cliente)
    if trabajos.en_curso(job_id):
        flash(gettext("Ya hay una importación de archivo en curso — espera a que termine."), "warn")
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
        flash(gettext("Importando «%(nombre)s»… Los productos aparecen aquí cuando termine.", nombre=nombre), "ok")
    else:
        try:
            os.remove(ruta)
        except OSError:
            pass
        flash(gettext("Ya hay una importación de archivo en curso — espera a que termine."), "warn")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/importar/url", methods=["POST"])
def prod_importar_url(cliente):
    url = (request.form.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        flash(gettext("Pega la URL completa de la página del producto (empieza por http:// o https://)."), "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_importar_url(cliente)
    arranco = trabajos.encolar(
        job_id, "catalogo_importar", {"cliente": cliente, "url": url},
        cliente=cliente, duracion_estimada=90, etapas=tareas_tiendas.ETAPAS_IMPORTAR, max_intentos=1)
    if arranco:
        flash(gettext("Leyendo la página del producto… aparece aquí cuando termine."), "ok")
    else:
        flash(gettext("Ya hay una importación desde URL en curso — espera a que termine."), "warn")
    return _volver_productos(cliente)


@app.route("/cliente/<cliente>/productos/<int:pid>/pruebas", methods=["POST"])
def prod_prueba_agregar(cliente, pid):
    """Doctrina, bloque 2 (§5.4): agrega una prueba real al producto."""
    from doctrina import producto as doctrina_producto
    if not tiendas.producto(cliente, pid):
        flash(gettext("No encontré ese producto."), "error")
        return _volver_productos(cliente)
    try:
        doctrina_producto.agregar_prueba(cliente, pid, request.form.get("texto"), request.form.get("fuente"))
        flash(gettext("Prueba guardada: Claude ya la puede usar con este producto."), "ok")
    except doctrina_producto.ErrorPrueba as e:
        flash(str(e), "error")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/pruebas/<prueba_id>/borrar", methods=["POST"])
def prod_prueba_borrar(cliente, pid, prueba_id):
    from doctrina import producto as doctrina_producto
    if not tiendas.producto(cliente, pid) or not doctrina_producto.borrar_prueba(cliente, pid, prueba_id):
        flash(gettext("No encontré ese producto."), "error")
    else:
        flash(gettext("Prueba borrada."), "ok")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/pedidos/actualizar", methods=["POST"])
def prod_pedidos_actualizar(cliente, pid):
    """«Actualizar lo que Claude necesita» (doctrina, bloque 2, §5.3): encola la
    tarea pagada; el precio ya está en el botón. Sin faltantes no encola."""
    from doctrina import pedidos as doctrina_pedidos
    fila = tiendas.producto(cliente, pid)
    if not fila:
        flash(gettext("No encontré ese producto."), "error")
    elif not doctrina_pedidos.faltantes_del_producto(cliente, fila):
        flash(gettext("Claude no ha pedido nada para este producto todavía: aparece cuando escribe ideas o guiones con él."), "ok")
    elif tareas_doctrina.encolar_pedidos(cliente, pid):
        flash(gettext("Armando lo que Claude necesita… la lista se actualiza sola."), "ok")
    else:
        flash(gettext("Ya se está armando la lista de este producto."), "error")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/pedidos/<pedido_id>/responder", methods=["POST"])
def prod_pedido_responder(cliente, pid, pedido_id):
    """La respuesta queda como prueba del producto y el pedido se cierra."""
    from doctrina import producto as doctrina_producto
    if not tiendas.producto(cliente, pid):
        flash(gettext("No encontré ese producto."), "error")
        return _volver_productos(cliente)
    try:
        doctrina_producto.responder(cliente, pid, pedido_id, request.form.get("texto"), request.form.get("fuente"))
        flash(gettext("Gracias: quedó como prueba del producto y Claude ya la puede usar."), "ok")
    except doctrina_producto.ErrorPrueba as e:
        flash(str(e), "error")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/pedidos/<pedido_id>/descartar", methods=["POST"])
def prod_pedido_descartar(cliente, pid, pedido_id):
    from doctrina import producto as doctrina_producto
    if not tiendas.producto(cliente, pid) or not doctrina_producto.descartar(cliente, pid, pedido_id):
        flash(gettext("Ese pedido ya no está abierto."), "error")
    else:
        flash(gettext("Listo: Claude no lo volverá a pedir."), "ok")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/marcar", methods=["POST"])
def prod_marcar(cliente, pid):
    """Banderas del loop: en prueba, prioridad (0–100), URL de compra, precio
    y moneda. Solo toca los campos que vienen en el formulario; `en_prueba`
    siempre viene (un checkbox sin marcar = apagado)."""
    if not tiendas.producto(cliente, pid):
        flash(gettext("No encontré ese producto."), "error")
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
        flash(gettext("Revisa los números: prioridad entre 0 y 100, precio positivo."), "error")
        return _volver_fila(cliente, pid)
    if "url_compra" in form:
        url = (form.get("url_compra") or "").strip()
        if url and not url.startswith(("http://", "https://")):
            flash(gettext("La URL de compra tiene que empezar por http:// o https://."), "error")
            return _volver_fila(cliente, pid)
        campos["url_compra"] = url or None
    if "moneda" in form:
        moneda = (form.get("moneda") or "").strip().upper()
        if moneda and not _MONEDA_RE.match(moneda):
            flash(gettext("La moneda va en código de 3 letras (COP, MXN, USD…)."), "error")
            return _volver_fila(cliente, pid)
        campos["moneda"] = moneda or None
    tiendas.marcar_producto(cliente, pid, **campos)
    flash(gettext("Producto actualizado."), "ok")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/archivar", methods=["POST"])
def prod_archivar(cliente, pid):
    """Archiva (o, con archivado=0, recupera) un producto. No borra nada: un
    producto archivado sigue ligado a su activo y a sus experimentos. Es un
    archivado MANUAL (`tiendas.marcar_producto` deja `extra.archivado_por =
    "manual"`): la sync de la tienda no lo desarchiva aunque el producto
    siga allá; solo «Recuperar» (archivado=0) lo devuelve a la lista."""
    if not tiendas.producto(cliente, pid):
        flash(gettext("No encontré ese producto."), "error")
        return _volver_productos(cliente)
    archivar = (request.form.get("archivado") or "1") not in ("0", "false", "off")
    tiendas.marcar_producto(cliente, pid, archivado=archivar)
    flash(gettext("Producto archivado.") if archivar else gettext("Producto recuperado."), "ok")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/vincular", methods=["POST"])
def prod_vincular(cliente, pid):
    """Encola `producto_vincular` (worker): crea o completa el activo del
    catálogo bajando las fotos otra vez y pidiendo la regla a Claude. No va
    inline: hasta 6 fotos × 30 s + Claude pasan de largo el timeout de
    gunicorn. max_intentos=1 porque llama a Claude."""
    prod = tiendas.producto(cliente, pid)
    if not prod:
        flash(gettext("No encontré ese producto."), "error")
        return _volver_productos(cliente)
    job_id = tareas_tiendas.job_id_vincular(cliente, pid)
    arranco = trabajos.encolar(
        job_id, "producto_vincular", {"cliente": cliente, "producto_id": pid},
        cliente=cliente, duracion_estimada=90, etapas=tareas_tiendas.ETAPAS_VINCULAR, max_intentos=1)
    if arranco:
        flash(gettext("Creando el activo de «%(nombre)s»… aparece en el Catálogo cuando termine.",
                      nombre=prod.get("nombre") or pid), "ok")
    else:
        flash(gettext("Ya se está creando el activo de ese producto — espera a que termine."), "warn")
    return _volver_fila(cliente, pid)


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
        flash(gettext("No encontré ese producto."), "error")
        return _volver_productos(cliente)
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not archivos:
        flash(gettext("No elegiste ninguna foto."), "error")
        return _volver_fila(cliente, pid)
    nombre = (prod.get("nombre") or "").strip() or gettext("Producto %(pid)s", pid=pid)
    enlazado = prod.get("activo_catalogo_id")
    if enlazado and catalogo_productos.existe(cliente, enlazado, "producto"):
        # Página vieja o doble envío: el activo ya existe. Las fotos van a
        # ese, no a un segundo activo con el mismo nombre.
        guardadas = _guardar_fotos_producto(cliente, enlazado, archivos)
        flash(gettext("%(n)s foto(s) añadida(s) a «%(nombre)s».", n=guardadas, nombre=nombre) if guardadas
              else gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."),
              "ok" if guardadas else "error")
        return _volver_fila(cliente, pid)
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
        return _volver_fila(cliente, pid)
    guardadas = _guardar_fotos_producto(cliente, activo_id, archivos)
    if not guardadas:
        # Sin foto válida el activo no aparecería en el catálogo y la fila
        # quedaría enlazada a algo invisible: mejor deshacer.
        catalogo_productos.eliminar(cliente, activo_id, categoria="producto")
        flash(gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."), "error")
        return _volver_fila(cliente, pid)
    tiendas.marcar_producto(cliente, pid, activo_catalogo_id=activo_id)
    flash(gettext("«%(nombre)s» ya está en el catálogo con %(n)s foto(s).", nombre=nombre, n=guardadas), "ok")
    return _volver_fila(cliente, pid)


@app.route("/cliente/<cliente>/productos/<int:pid>/experimento", methods=["POST"])
def prod_experimento(cliente, pid):
    """Manda a Experimentos (la galería) con el nombre y la URL de destino del
    producto ya puestos en el paso 3 de «Probar en Meta» — la plantilla los
    lee de request.args (exp_nombre, exp_destino)."""
    prod = tiendas.producto(cliente, pid)
    if not prod:
        flash(gettext("No encontré ese producto."), "error")
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
    flash(gettext("Falta FLASK_SECRET_KEY en el .env del servidor: sin ella no se pueden guardar las "
          "credenciales de una tienda."), "error")


@app.route("/cliente/<cliente>/config/tienda/conectar", methods=["POST"])
def tienda_conectar(cliente):
    """Shopify (con o sin llaves)/WooCommerce: prueba las credenciales contra
    la tienda (inline, una llamada corta), las guarda cifradas y encola la
    primera sync. `volver=catalogo` regresa a la pestaña Catálogo (el botón
    «Traer de mi tienda» vive ahí); cualquier otro valor va a Configuración.
    La Shopify sin llaves y la Admin API conviven: la sin llaves es la fuente
    del catálogo (trae los colores) y la Admin API suma pedidos y atribución
    (`tareas.tiendas.catalogo_desde_tienda_publica`; ruling final-5)."""
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not cifrado.disponible():
        _flash_sin_cifrado()
        return _volver_config(cliente)
    tipo = (request.form.get("tipo") or "").strip()
    volver = request.form.get("volver") or "config"

    def _volver():
        return _volver_catalogo(cliente) if volver == "catalogo" else _volver_config(cliente)

    if tipo == "shopify_publico":
        dominio = (request.form.get("dominio") or "").strip()
        creds = {"dominio": dominio}
    elif tipo == "shopify":
        dominio = (request.form.get("dominio") or "").strip()
        creds = {"dominio": dominio, "token": (request.form.get("token") or "").strip()}
    elif tipo == "woo":
        url = (request.form.get("url") or "").strip()
        dominio = re.sub(r"^https?://", "", url).strip("/").split("/")[0]
        creds = {"url": url, "ck": (request.form.get("ck") or "").strip(), "cs": (request.form.get("cs") or "").strip()}
    else:
        flash(gettext("Ese tipo de tienda no se conecta desde aquí (Shopify, Shopify sin llaves o WooCommerce; MercadoLibre va por su botón)."), "error")
        return _volver()
    try:
        cls = conectores.por_tipo(tipo)
        resultado = cls(creds).probar()
    except (ErrorConector, ValueError) as e:
        flash(gettext("No pude conectar la tienda: %(error)s", error=cola.sin_token(str(e))), "error")
        return _volver()
    except Exception as e:  # noqa: BLE001 — un fallo de red/parseo también se muestra, nunca se guarda a ciegas
        flash(gettext("No pude conectar la tienda: %(error)s", error=cola.sin_token(str(e) or type(e).__name__)), "error")
        return _volver()
    nombre = str((resultado or {}).get("nombre") or "").strip() or None
    dominio = str((resultado or {}).get("dominio") or dominio or "").strip() or None
    if tipo == "shopify_publico":
        creds = {"dominio": dominio}
    tid = tiendas.conectar(cliente, tipo, creds, nombre=nombre, dominio=dominio)
    n = _encolar_sync_tienda(cliente, tid, tipo, con_pedidos=bool(getattr(cls, "tiene_pedidos", True)))
    detalle = str((resultado or {}).get("detalle") or "").strip()
    if tareas_tiendas.catalogo_desde_tienda_publica(cliente, {"tipo": tipo}):
        # La sync de productos de la Admin API no tocará el catálogo (no trae colores).
        extra = gettext("El catálogo sigue llegando desde la conexión sin llaves; la Admin API agrega pedidos y atribución.")
    else:
        extra = gettext("Sincronizando el catálogo…") if n else gettext("Ya había una sincronización en curso.")
    flash(gettext("Tienda %(nombre)s conectada. %(detalle)s %(extra)s", nombre=(nombre or dominio), detalle=detalle, extra=extra), "ok")
    return _volver()


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
        flash(gettext("Falta configurar %(vars)s en el .env del servidor (app de developers.mercadolibre.com).",
                      vars=" y ".join(faltan)), "error")
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
        flash(gettext("La autorización con MercadoLibre no coincide con esta sesión — vuelve a intentarlo desde Configuración."), "error")
        return _volver_config(cliente) if cliente else redirect(url_for("index"))
    if not usuarios.puede_acceder(_sesion(), cliente):
        flash(gettext("No tienes acceso a ese proyecto."), "error")
        return redirect(url_for("index"))
    if request.args.get("error"):
        detalle = request.args.get("error_description") or request.args.get("error")
        flash(gettext("MercadoLibre no autorizó la conexión: %(detalle)s", detalle=detalle), "error")
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
    extra = gettext("Sincronizando las publicaciones…") if n else gettext("Ya había una sincronización en curso.")
    sufijo_nombre = f" ({nombre})" if nombre else ""
    flash(gettext("MercadoLibre conectado%(sufijo)s. %(extra)s", sufijo=sufijo_nombre, extra=extra), "ok")
    return _volver_config(cliente)


@app.route("/cliente/<cliente>/config/tienda/<int:tid>/sincronizar", methods=["POST"])
def tienda_sync(cliente, tid):
    """Encola productos + pedidos. También para una tienda `rota`: volver a
    sincronizar es como la persona comprueba que ya se arregló. `volver=catalogo`
    regresa a la pestaña Catálogo (el botón «Sincronizar ahora» vive ahí)."""
    volver = request.form.get("volver")
    t = tiendas.obtener(cliente, tid)
    if not t:
        flash(gettext("Esa tienda no existe."), "error")
        return _volver_config(cliente)
    n = _encolar_sync_tienda(cliente, tid, t["tipo"])
    flash(gettext("Sincronizando…") if n else gettext("Ya se está sincronizando esa tienda."), "ok" if n else "warn")
    return _volver_catalogo(cliente) if volver == "catalogo" else _volver_config(cliente)


def _fuente_de_tipo(tipo):
    """La `fuente` con que el conector de ese tipo guarda sus productos
    (`shopify_publico` y `shopify` comparten «shopify»); el tipo si no se sabe."""
    try:
        return getattr(conectores.por_tipo(tipo), "fuente", None) or tipo
    except ValueError:
        return tipo


@app.route("/cliente/<cliente>/config/tienda/<int:tid>/desconectar", methods=["POST"])
def tienda_desconectar(cliente, tid):
    """Borra la tienda y archiva sus productos — salvo que OTRA tienda del
    proyecto con la misma fuente (la Shopify sin llaves y la Admin API
    conviven) los siga trayendo: entonces quedan como están."""
    t = tiendas.obtener(cliente, tid)
    if not t:
        flash(gettext("Esa tienda no existe."), "error")
        return _volver_config(cliente)
    fuente = _fuente_de_tipo(t["tipo"])
    sigue = any(o["id"] != tid and _fuente_de_tipo(o["tipo"]) == fuente for o in tiendas.listar(cliente))
    if not tiendas.desconectar(cliente, tid, archivar=not sigue):
        flash(gettext("Esa tienda no existe."), "error")
    elif sigue:
        flash(gettext("Tienda desconectada. Sus productos siguen activos porque la otra conexión de la misma tienda "
                      "los sigue trayendo; sus pedidos se conservan (no se borró nada)."), "ok")
    else:
        flash(gettext("Tienda desconectada. Sus productos quedaron archivados y sus pedidos se conservan (no se borró nada)."), "ok")
    return _volver_config(cliente)


PIXEL_ESTADOS_TEXTO = {
    "ok": idiomas.N_("El Pixel está disparando."),
    "sin_datos": idiomas.N_("El Pixel existe pero no ha disparado en los últimos días."),
    "sin_pixel": idiomas.N_("La cuenta publicitaria no tiene ningún Pixel."),
    "sin_conexion": idiomas.N_("Meta no está conectado."),
    "error": idiomas.N_("No pude consultar el Pixel."),
}


@app.route("/cliente/<cliente>/config/pixel/refrescar", methods=["POST"])
def cfg_pixel_refrescar(cliente):
    meta_conexion.invalidar_pixel(cliente)
    r = meta_conexion.estado_pixel(cliente) or {}
    estado = r.get("estado") or "error"
    texto = gettext(PIXEL_ESTADOS_TEXTO.get(estado, estado))
    if estado == "error" and r.get("detalle"):
        texto += f" {r['detalle']}"
    flash(texto, "ok" if estado == "ok" else "warn")
    return _volver_config(cliente)


@app.route("/cliente/<cliente>/prompt/<prompt_id>/guardar", methods=["POST"])
def guardar_prompt(cliente, prompt_id):
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(gettext("No encontré el prompt %(prompt)s", prompt=prompt_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)
    flash(gettext("Cambios guardados en %(prompt)s.", prompt=prompt_id), "ok")
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
            raise RuntimeError(idiomas.N_("El prompt ya no existe (¿se descartó mientras generaba?)."))
        ok, error = _generar_imagen_candidata(
            cliente, prompt_id, item, job_id=job_id,
            on_progreso=_avisar_fase_de(job_id, cliente),
        )
        prompts_mod.guardar(cliente, data)
        if not ok:
            raise RuntimeError(error)
        return idiomas.N_("Imagen candidata lista.")

    return trabajos.iniciar(job_id, trabajo, duracion_estimada=45, etapas=ETAPAS_IMAGEN)


@app.route("/cliente/<cliente>/prompt/<prompt_id>/aprobar", methods=["POST"])
def aprobar_prompt(cliente, prompt_id):
    """Aprueba el texto del prompt y lanza en segundo plano la generación de una
    imagen de referencia candidata (barata, ~1.5cr) — todavía NO genera el video."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(gettext("No encontré el prompt %(prompt)s", prompt=prompt_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    if _lanzar_generacion_imagen(cliente, prompt_id):
        flash(gettext("Generando imagen candidata para %(prompt)s…", prompt=prompt_id), "ok")
    else:
        flash(gettext("Ya se está generando la imagen de %(prompt)s — espera a que termine.", prompt=prompt_id), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/regenerar_imagen", methods=["POST"])
def regenerar_imagen(cliente, prompt_id):
    """La imagen candidata no gustó: lanza otra en segundo plano (gasta créditos de nuevo)."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item:
        flash(gettext("No encontré el prompt %(prompt)s", prompt=prompt_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    if _lanzar_generacion_imagen(cliente, prompt_id):
        flash(gettext("Regenerando imagen candidata para %(prompt)s…", prompt=prompt_id), "ok")
    else:
        flash(gettext("Ya se está generando una imagen para %(prompt)s — espera a que termine.", prompt=prompt_id), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/aprobar_imagen", methods=["POST"])
def aprobar_imagen(cliente, prompt_id):
    """La imagen candidata sí gustó: lanza en segundo plano el video real a
    partir de ella (aquí sí se gasta el crédito grande, ~8cr)."""
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if not item or not item.get("imagen_url"):
        flash(gettext("No encontré una imagen candidata para %(prompt)s", prompt=prompt_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    _aplicar_edicion(item, request.form)
    prompts_mod.guardar(cliente, data)

    job_id = _job_id_video(cliente, prompt_id)

    def trabajo():
        data2 = prompts_mod.cargar(cliente)
        idea_id2, item2 = prompts_mod.encontrar_prompt(data2, prompt_id)
        if not item2:
            raise RuntimeError(idiomas.N_("El prompt ya no existe (¿se descartó mientras generaba?)."))

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
        result = poll_until_done(launch["status_url"], on_progreso=_avisar_fase_de(job_id, cliente))
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

        registro = {
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
        # Con candado (estado.modificar): el worker también escribe este archivo.
        estado_mod.modificar(cliente, lambda estado: {**estado, prompt_id: registro})

        del data2[idea_id2]["prompts"][prompt_id]
        prompts_mod.guardar(cliente, data2)
        return idiomas.N_("Video listo, pendiente de revisión.")

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=130, etapas=ETAPAS_VIDEO):
        flash(gettext("Generando el video de %(prompt)s…", prompt=prompt_id), "ok")
    else:
        flash(gettext("Ya se está generando el video de %(prompt)s — espera a que termine.", prompt=prompt_id), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/prompt/<prompt_id>/rechazar", methods=["POST"])
def rechazar_prompt(cliente, prompt_id):
    data = prompts_mod.cargar(cliente)
    idea_id, item = prompts_mod.encontrar_prompt(data, prompt_id)
    if item:
        del data[idea_id]["prompts"][prompt_id]
        prompts_mod.guardar(cliente, data)
        flash(gettext("Prompt %(prompt)s descartado, no se generó video (no gastó créditos).", prompt=prompt_id), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/idea/<idea_id>/eliminar", methods=["POST"])
def eliminar_idea(cliente, idea_id):
    data = prompts_mod.cargar(cliente)
    if idea_id in data:
        del data[idea_id]
        prompts_mod.guardar(cliente, data)
        flash(gettext("Idea eliminada junto con sus prompts."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/aprobar/<brief_id>", methods=["POST"])
def aprobar(cliente, brief_id):
    estado = estado_mod.cargar(cliente)
    entry = estado.get(brief_id)
    if not entry:
        flash(gettext("No encontré %(video)s", video=brief_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    job_id = _job_id_publicar(cliente, brief_id)

    def trabajo():
        # Serializado: cargar el .env del cliente muta variables globales del
        # proceso, así que dos publicaciones de clientes distintos no pueden
        # hacer esa parte al mismo tiempo sin arriesgarse a mezclar credenciales.
        with _ENV_LOCK:
            _cargar_entorno_cliente(cliente)
            ok = publicar_brief(brief_id, entry, cliente, _token_paths(cliente))

        def _publicado(estado2):
            estado2[brief_id]["estado"] = "publicado"
            estado2[brief_id]["publicado_en"] = datetime.now().isoformat()
            return estado2
        estado_mod.modificar(cliente, _publicado)

        if not ok:
            raise RuntimeError(idiomas.N_("Se publicó, pero alguna plataforma falló — revisa la bitácora."))
        return idiomas.N_("Publicado en todas las plataformas.")

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=90):
        flash(gettext("Publicando %(video)s…", video=brief_id), "ok")
    else:
        flash(gettext("Ya se está publicando %(video)s — espera a que termine.", video=brief_id), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/rechazar/<brief_id>", methods=["POST"])
def rechazar(cliente, brief_id):
    def _rechazar(estado):
        if brief_id not in estado:
            return None
        estado[brief_id]["estado"] = "rechazado"
        return estado
    if estado_mod.modificar(cliente, _rechazar) is None:
        flash(gettext("No encontré %(video)s", video=brief_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))

    flash(gettext("%(video)s rechazado, no se publica.", video=brief_id), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/crear/tarjetas")
def crear_tarjetas(cliente):
    """«Ver más» de Crear: las TARJETAS_POR_PAGINA siguientes (fragmento HTML;
    spec 2026-09-28 «tarjetas ligeras»)."""
    desde = _pagina_desde(request.args.get("desde"))
    items = _creative_flow_items(cliente)
    return render_template("_crear_tarjetas_respuesta.html", cliente=cliente,
                           items=items[desde:desde + TARJETAS_POR_PAGINA], desde=desde, total=len(items))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/detalle")
def cf_detalle(cliente, cf_id):
    """El detalle de una pieza (lo que antes iba embebido en un <template>
    por tarjeta); el modal lo pide al abrir. 404 si no es de este proyecto."""
    item = _creative_flow_item(cliente, cf_id)
    if item is None:
        abort(404)
    return render_template("_crear_detalle_respuesta.html", cliente=cliente, item=item)


@app.route("/cliente/<cliente>/final/tarjetas")
def final_tarjetas(cliente):
    """«Ver más» de Final edition: `lista=videos` (videos listos) o
    `lista=finales`; las TARJETAS_POR_PAGINA siguientes desde `desde`."""
    lista = request.args.get("lista")
    if lista not in ("videos", "finales"):
        abort(400)
    desde = _pagina_desde(request.args.get("desde"))
    completas = _listas_crear_final(_creative_flow_items(cliente), n=None)
    todos = completas["final_videos"] if lista == "videos" else completas["finales"]
    return render_template("_final_tarjetas_respuesta.html", cliente=cliente, lista=lista,
                           items=todos[desde:desde + TARJETAS_POR_PAGINA], desde=desde, total=len(todos),
                           **_contexto_final_edition(cliente))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/detalle")
def fe_detalle_video(cliente, cf_id):
    """Detalle de un video listo en Final edition (guion, «Producir finales»,
    editor). 404 si no es un video listo de este proyecto."""
    item = _creative_flow_item(cliente, cf_id)
    if item is None or item.get("estado") != "video_listo" or (item.get("tipo") or "video") == "imagen":
        abort(404)
    return render_template("_final_detalle_respuesta.html", cliente=cliente, item=item, f=None,
                           **_contexto_final_edition(cliente))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/detalle")
def fe_detalle_final(cliente, cf_id, final_id):
    """Detalle de una final (capas, descargar, descartar, publicación orgánica)."""
    item = _creative_flow_item(cliente, cf_id)
    f = next((x for x in ((item or {}).get("finales") or []) if x["id"] == final_id), None)
    if item is None or f is None:
        abort(404)
    return render_template("_final_detalle_respuesta.html", cliente=cliente, item=item, f=f,
                           **_contexto_final_edition(cliente))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/descartar", methods=["POST"])
def cf_descartar(cliente, cf_id):
    creative_flow.eliminar(cliente, cf_id)
    flash(gettext("Sesión de CreativeFlowPlus descartada."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


# ---------------------------------------------------------- Final edition ---

IDIOMAS_FE = ("es", "en", "pt")


def _volver_final(cliente):
    """Las rutas de final edition vuelven a su pestaña (desde 2026-09-27 ya no
    viven en Crear)."""
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="final"))


def _ediciones_por_cf(cliente):
    """{cf_id: [ediciones de esa pieza]} para la pestaña Final edition (filas
    sin el documento): las de la persona primero, la más reciente primero, y
    después los borradores automáticos (`ediciones.para_editar`: la primera es
    la que abre «Editar», capa 4c), cada una con su `nombre_visible`."""
    out = {}
    for e in ediciones.listar(cliente):
        if e.get("cf_id"):
            out.setdefault(e["cf_id"], []).append({**e, "nombre_visible": ediciones.nombre_visible(e)})
    return {cf: ediciones.para_editar(eds) for cf, eds in out.items()}


def _precio_form(valor):
    """Precio opcional del formulario -> float o None (vacío o basura = None)."""
    valor = (valor or "").strip().replace(",", ".")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/angulo", methods=["POST"])
def cf_angulo(cliente, cf_id):
    """Doctrina, bloque 2 (§3.3): guarda el ángulo editado a mano de una
    pieza de Crear (`concepto.extra.angulo`, el que usan el guion, las
    variantes y los captions). JSON {angulo} → {ok, angulo, avisos, resumen}.
    Los avisos no bloquean: se guarda igual."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        return jsonify({"ok": False, "error": gettext("Esa pieza ya no existe.")}), 404
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("angulo"), dict):
        return jsonify({"ok": False, "error": gettext("Formato inválido.")}), 400
    previo = entry.get("angulo") if isinstance(entry.get("angulo"), dict) else {}
    limpio, avisos = doctrina.angulo_desde_formulario(dict(cuerpo["angulo"], origen=previo.get("origen")),
                                                      previo.get("faltantes"), ahora=db.ahora())
    creative_flow.actualizar(cliente, cf_id, angulo=limpio)
    return jsonify({"ok": True, "angulo": limpio, "avisos": avisos, "resumen": doctrina.resumen_angulo(limpio)})


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/revisar", methods=["POST"])
def cf_revisar(cliente, cf_id):
    """Doctrina, bloque 3: encola «Revisar con la doctrina» de una pieza
    terminada (pagada: el precio va en el botón; un clic repetido no lanza
    dos porque el `job_id` es determinista). Solo informa, nunca bloquea."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or not entry.get("video_url"):
        flash(gettext("Solo se puede revisar una pieza terminada."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    tareas_doctrina.encolar_revisar(cliente, cf_id)
    flash(gettext("Revisando la pieza con la doctrina: la página se recarga sola cuando esté lista."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/aprendizajes", methods=["POST"])
def apr_agregar(cliente):
    """Doctrina, bloque 4 (§5): un aprendizaje escrito a mano."""
    try:
        proyectos.agregar_aprendizaje(cliente, doctrina_aprendizajes.manual(request.form.get("texto")))
        flash(gettext("Aprendizaje guardado."), "ok")
    except ValueError as e:
        flash(str(e), "error")
    except OSError:
        # proyecto.json existe pero no se pudo leer: no se sobrescribe (proyectos._cargar_para_escribir).
        flash(gettext("No se pudo leer el proyecto; no se guardó."), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


@app.route("/cliente/<cliente>/aprendizajes/<aid>/quitar", methods=["POST"])
def apr_quitar(cliente, aid):
    try:
        if not proyectos.quitar_aprendizaje(cliente, aid):
            flash(gettext("Ese aprendizaje ya no existe."), "error")
    except OSError:
        flash(gettext("No se pudo leer el proyecto; no se guardó."), "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))


def _sesion_con_video(cliente, cf_id):
    """Sesión de Crear con video listo, o None (con flash) si no aplica."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        flash(gettext("Esa sesión de Crear ya no existe."), "error")
        return None
    if entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        flash(gettext("Final edition necesita un video listo (no una imagen ni una sesión sin generar)."), "error")
        return None
    return entry


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/preparar", methods=["POST"])
def fe_preparar(cliente, cf_id):
    """Encola la escritura del guion base (capa 0, Anthropic). No produce nada."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_final(cliente)
    # Decisión B (2026-09-28): el guion base no es por destino. La elección
    # explícita del selector gana; sin ella (o con una que no vale), el idioma
    # del proyecto.
    idioma_base = request.form.get("idioma_base")
    if idioma_base not in IDIOMAS_FE:
        idioma_base = idiomas.de_proyecto(cliente)
    opciones = {"precio": _precio_form(request.form.get("precio")), "idioma_base": idioma_base}
    encolado = trabajos.encolar(
        tareas_fe.job_id_guion(cliente, cf_id), "final_guion",
        {"cliente": cliente, "cf_id": cf_id, "opciones": opciones},
        cliente=cliente, duracion_estimada=25, max_intentos=2,
    )
    flash(gettext("Escribiendo el guion con IA… en unos segundos aparece aquí para que lo revises.") if encolado
          else gettext("Ya se estaba escribiendo el guion de esta pieza."), "ok")
    return _volver_final(cliente)


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/guion", methods=["POST"])
def fe_guardar_guion(cliente, cf_id):
    """Guarda la edición del guion base: solo cambian los textos (pantalla y
    voz) de cada bloque; tiempos, roles, idioma y país se conservan."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_final(cliente)
    base = creative_flow.guion_base(cliente, cf_id)
    if not base or not base.get("bloques"):
        flash(gettext("Primero prepara el guion con IA; después lo editas."), "error")
        return _volver_final(cliente)
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
        flash(gettext("No se guardó el guion: %(errores)s", errores=" ".join(errores)), "error")
        return _volver_final(cliente)
    creative_flow.guardar_guion_base(cliente, cf_id, guion)
    flash(gettext("Guion guardado. Ahora elige los destinos y produce las finales."), "ok")
    return _volver_final(cliente)


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
        return _volver_final(cliente)
    base = creative_flow.guion_base(cliente, cf_id)
    if not base:
        flash(gettext("Primero prepara el guion con IA y revísalo; sin guion no se produce nada."), "error")
        return _volver_final(cliente)
    destinos = _destinos_form(request.form.getlist("destinos"))
    if not destinos:
        flash(gettext("Marca al menos un destino (idioma y país) válido para producir."), "error")
        return _volver_final(cliente)

    idioma_base = base.get("idioma") if base.get("idioma") in IDIOMAS_FE else "es"
    voces_validas = {v for lista in fal_audio.VOCES.values() for v in lista}
    voz = request.form.get("voz") or ""
    if voz not in voces_validas:
        voz = (fal_audio.VOCES.get(idioma_base) or fal_audio.VOCES["es"])[0]
    estilo = request.form.get("estilo_musica") or ""
    cancion = mi_musica.resolver(cliente, estilo)
    if not cancion and estilo not in fe_tipos.ESTILOS_MUSICA:
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
    if cancion:
        opciones["musica_inicio_s"] = mi_musica.inicio_valido(cancion, request.form.get("musica_inicio_s"))
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
        flash(gettext("Produciendo %(n)s finales… cada una aparece aquí, en Finales, cuando termina.", n=encolados), "ok")
    else:
        flash(gettext("Ya se estaban produciendo esas finales."), "ok")
    return _volver_final(cliente)


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/descartar", methods=["POST"])
def fe_descartar(cliente, cf_id, final_id):
    final = creative_flow.final_por_legado(cliente, final_id) if final_id.startswith(cf_id + "__") else None
    if final and trabajos.en_curso(tareas_fe.job_id_final(cliente, cf_id, final["idioma"], final["pais"],
                                                          variante=final.get("variante"))):
        # Borrar la fila mientras el worker la escribe la dejaría resucitar a
        # medias (actualizar_final sobre una pieza que ya no existe).
        flash(gettext("Esa final se está produciendo; espera a que termine."), "error")
        return _volver_final(cliente)
    if not final or not creative_flow.eliminar_final(cliente, final_id):
        flash(gettext("Esa final ya no existe."), "error")
    else:
        flash(gettext("Final descartada."), "ok")
    return _volver_final(cliente)


def _lanzar_video_cf(cliente, cf_id, entry):
    """Encola la generación de una sesión de FlowPlus (video o imagen). Lo usan
    cf_crear_video y cf_generar_video. El cuerpo vive en flowplus_lanzar.py
    (compartido con los lotes de Sprints)."""
    return flowplus_lanzar.lanzar(cliente, cf_id, entry)


def _consumir_bandeja(cliente, usadas):
    """Tras crear en Crear: quita de la bandeja solo lo que se usó (`usadas`,
    los `ref_ids` que el formulario mostraba). None = formulario sin
    `bandeja_vista`: toda la bandeja, como antes."""
    if usadas is None:
        referencias_flowplus.vaciar(cliente)
    else:
        referencias_flowplus.quitar_varios(cliente, usadas)


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
        referencias_flowplus.agregar(cliente, "video", url, frame_url=frame_url, origen="archivo", ruta_local=local_path,
                                     titulo=nombre, duracion_s=_duracion_video(local_path))
    else:
        url = r2_uploader.upload_image(local_path, f"clientes/{cliente}/referencias_flowplus/{unico}")
        referencias_flowplus.agregar(cliente, "imagen", url, origen="archivo", ruta_local=local_path, titulo=nombre)
    return True


def _duracion_video(ruta):
    """Segundos de un video de referencia (ffprobe), a centésimas; None si no
    se pudo medir. Nunca lanza: una medida que falla no frena la subida
    (2026-09-30: Crear la usa para el límite de Wan 3.0 y su precio)."""
    try:
        return round(fe_cortes.duracion(ruta), 2) if ruta else None
    except Exception:  # noqa: BLE001
        return None


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
            errores.append(gettext("No pude subir %(archivo)s: %(error)s", archivo=a.filename, error=e))
    mensaje = gettext("%(n)s referencia(s) agregada(s).", n=ok) if ok else None
    error = "; ".join(errores) if errores else (None if archivos else gettext("No elegiste ningún archivo."))
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
        flash(gettext("Pega un link primero."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    job_id = _job_id_link(cliente)

    def trabajo():
        # Un hilo de trabajos.iniciar no tiene petición: sin esto un LinkError
        # saldría en el msgid (español). Lo que se arma adentro va en el idioma
        # del proyecto; el return fijo lo traduce estado_trabajo para quien mira.
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            carpeta = os.path.join(_client_dir(cliente), "referencias_flowplus")
            base = f"link_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            try:
                local_path, meta = referencias_link.descargar(url, carpeta, base)
                r2_url = r2_uploader.upload_video(local_path, f"clientes/{cliente}/referencias_flowplus/{base}.mp4")
                frame_path = local_path + FRAME_SUFFIX
                _extraer_frame(local_path, frame_path)
                frame_url = r2_uploader.upload_image(frame_path,
                                                     f"clientes/{cliente}/referencias_flowplus/{base}{FRAME_SUFFIX}")
                referencias_flowplus.agregar(cliente, "video", r2_url, frame_url=frame_url,
                                             origen=meta.get("fuente", "link"),
                                             ruta_local=local_path, titulo=meta.get("titulo") or url,
                                             duracion_s=_duracion_video(local_path))
                bitacora.registrar(cliente, base, "flowplus_link", "ok", url)
            except Exception as e:
                bitacora.registrar(cliente, base, "flowplus_link", "error", str(e))
                raise
        return idiomas.N_("Video del link agregado a las referencias.")

    arranco = trabajos.iniciar(job_id, trabajo, duracion_estimada=40)
    if _quiere_json():
        return _respuesta_bandeja(cliente, mensaje=gettext("Descargando el video del link…") if arranco else None,
                                  error=None if arranco else gettext("Ya se está descargando un link — espera a que termine."))
    if arranco:
        flash(gettext("Descargando el video del link… en unos segundos aparece entre las referencias."), "ok")
    else:
        flash(gettext("Ya se está descargando un link — espera a que termine."), "warn")
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


# --- Mi música (spec 2026-09-25): canciones propias y creadas con ElevenLabs ---

def _contexto_mi_musica(cliente):
    jid = tareas_musica.job_id(cliente)
    return {"mi_musica": mi_musica.listar(cliente),
            "trabajo_musica": {"job_id": jid} if trabajos.en_curso(jid) else None,
            "precio_musica_ia": gastos.estimar("musica_elevenlabs")}


def _respuesta_mi_musica(cliente, error=None, mensaje=None, nuevo_id=None, job_id=None):
    ctx = _contexto_mi_musica(cliente)
    html = render_template("_mi_musica.html", cliente=cliente, **ctx)
    return jsonify({"ok": error is None, "html": html, "canciones": ctx["mi_musica"], "error": error,
                    "mensaje": mensaje, "nuevo_id": nuevo_id, "job_id": job_id}), (400 if error else 200)


@app.route("/cliente/<cliente>/musica/subir", methods=["POST"])
def mm_subir(cliente):
    archivo = request.files.get("cancion")
    if not archivo or not archivo.filename:
        return _respuesta_mi_musica(cliente, error=gettext("Elige un archivo de audio."))
    try:
        c = mi_musica.subir(cliente, archivo, os.path.join(_client_dir(cliente), "tmp_musica"))
    except mi_musica.SubidaInvalida as e:
        return _respuesta_mi_musica(cliente, error=str(e))
    except Exception as e:
        bitacora.registrar(cliente, archivo.filename, "mi_musica", "error", str(e))
        return _respuesta_mi_musica(cliente, error=gettext("No pude subir la canción (%(tipo)s).", tipo=type(e).__name__))
    return _respuesta_mi_musica(cliente, mensaje=gettext("«%(nombre)s» quedó en Mi música.", nombre=c["nombre"]), nuevo_id=c["id"])


@app.route("/cliente/<cliente>/musica/<int:mid>/borrar", methods=["POST"])
def mm_borrar(cliente, mid):
    try:
        mi_musica.borrar(cliente, mid)
    except materiales.MaterialEnUso as e:
        return _respuesta_mi_musica(cliente, error=str(e))
    except Exception as e:
        bitacora.registrar(cliente, str(mid), "mi_musica", "error", str(e))
        return _respuesta_mi_musica(cliente, error=gettext("No pude borrarla (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__))
    return _respuesta_mi_musica(cliente)


@app.route("/cliente/<cliente>/musica/crear", methods=["POST"])
def mm_crear(cliente):
    prompt = " ".join((request.form.get("prompt") or "").split())[:400]
    if not prompt:
        return _respuesta_mi_musica(cliente, error=gettext("Describe la música que quieres."))
    jid = tareas_musica.job_id(cliente)
    encolado = trabajos.encolar(jid, "musica_generar",
                                {"cliente": cliente, "prompt": prompt, "instrumental": request.form.get("instrumental") == "si"},
                                duracion_estimada=90, etapas=list(tareas_musica.ETAPAS), cliente=cliente, max_intentos=1)
    if not encolado:
        return _respuesta_mi_musica(cliente, error=gettext("Ya se está creando una canción — espera a que termine."))
    return _respuesta_mi_musica(cliente, mensaje=gettext("Creando la canción con ElevenLabs…"), job_id=jid)


@app.route("/cliente/<cliente>/musica/lista")
def mm_lista(cliente):
    return _respuesta_mi_musica(cliente)


# ---------------------------------------------------------- Audios en Crear ---
# (spec 2026-09-28) Mismo patrón que Mi música: JSON con la lista ya pintada.

def _contexto_audios(cliente):
    jid = tareas_audios.job_id(cliente)
    return {"audios": audios.listar(cliente),
            "trabajo_audio": {"job_id": jid} if trabajos.en_curso(jid) else None,
            "voces_audio": audios.voces(), "fichas_voces": audios.fichas_voces(),
            "idiomas_audio": audios.IDIOMAS, "nombres_idioma_audio": audios.NOMBRES_IDIOMA,
            "velocidades_audio": audios.NOMBRES_VELOCIDAD, "volumenes_audio": audios.NOMBRES_VOLUMEN,
            "volumen_audio_defecto": audios.VOLUMEN_DEFECTO, "idioma_audio_defecto": audios.idioma_defecto(cliente),
            "max_caracteres_audio": audios.MAX_CARACTERES, "usd_por_caracter": fal_audio.COSTO_USD_POR_CARACTER}


def _respuesta_audios(cliente, error=None, mensaje=None, job_id=None):
    ctx = _contexto_audios(cliente)
    html = render_template("_audios_lista.html", cliente=cliente, **ctx)
    return jsonify({"ok": error is None, "html": html, "audios": ctx["audios"], "trabajo": ctx["trabajo_audio"],
                    "error": error, "mensaje": mensaje, "job_id": job_id}), (400 if error else 200)


@app.route("/cliente/<cliente>/audios/lista")
def au_lista(cliente):
    return _respuesta_audios(cliente)


@app.route("/cliente/<cliente>/audios/crear", methods=["POST"])
def au_crear(cliente):
    if not _mismo_origen():
        abort(403)
    try:
        payload = audios.validar(cliente, request.form)
    except audios.EntradaInvalida as e:
        return _respuesta_audios(cliente, error=idiomas.traducir(str(e)))
    jid = tareas_audios.job_id(cliente)
    encolado = trabajos.encolar(jid, "audio_generar", {"cliente": cliente, **payload}, duracion_estimada=60,
                                etapas=list(tareas_audios.ETAPAS), cliente=cliente, max_intentos=1)
    if not encolado:
        return _respuesta_audios(cliente, error=idiomas.traducir(audios.MENSAJES["en_curso"]))
    return _respuesta_audios(cliente, mensaje=gettext("Creando el audio…"), job_id=jid)


@app.route("/cliente/<cliente>/audios/<int:aid>/borrar", methods=["POST"])
def au_borrar(cliente, aid):
    if not _mismo_origen():
        abort(403)
    try:
        audios.borrar(cliente, aid)
    except materiales.MaterialEnUso as e:
        return _respuesta_audios(cliente, error=str(e))
    except Exception as e:
        bitacora.registrar(cliente, str(aid), "audios", "error", str(e))
        return _respuesta_audios(cliente, error=gettext("No pude borrarlo (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__))
    return _respuesta_audios(cliente)


@app.route("/cliente/<cliente>/audios/muestra", methods=["POST"])
def au_muestra(cliente):
    """Muestra corta de una voz (se sintetiza una vez para toda la plataforma,
    la paga Creatv). En línea: fal tarda 2–4 s."""
    if not _mismo_origen():
        abort(403)
    voz, idioma = (request.form.get("voz") or "").strip(), (request.form.get("idioma") or "").strip()
    if voz not in audios.voces() or idioma not in audios.IDIOMAS:
        return jsonify({"ok": False, "error": gettext("Elige una voz y un idioma de la lista.")}), 400
    try:
        url = audios.muestra(voz, idioma)
    except Exception as e:
        bitacora.registrar(cliente, voz, "audios", "muestra_error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude generar la muestra (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__)}), 502
    return jsonify({"ok": True, "url": url})


@app.route("/cliente/<cliente>/audios/<int:aid>/descargar")
def au_descargar(cliente, aid):
    """El mp3 como adjunto con nombre legible: el atributo `download` no
    funciona con otro origen y R2 no tiene CORS."""
    a = audios.obtener(cliente, aid)
    if not a:
        abort(404)
    try:
        r = requests.get(a["url"], stream=True, timeout=120)
    except requests.RequestException:
        abort(502)
    if r.status_code != 200:
        r.close()
        abort(502)
    base = unicodedata.normalize("NFKD", a["nombre"].replace("…", "")).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^A-Za-z0-9 _-]+", "", base).strip()[:60] or f"audio-{aid}"
    resp = Response(stream_with_context(r.iter_content(1 << 16)), mimetype="audio/mpeg")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}.mp3"'
    if r.headers.get("Content-Length"):
        resp.headers["Content-Length"] = r.headers["Content-Length"]
    return resp


@app.route("/cliente/<cliente>/flowplus/reusar/<cf_id>", methods=["POST"])
def fp_reusar(cliente, cf_id):
    """"Editar y crear otra a partir de esta": las referencias de esa pieza (sin
    los logos, que se adjuntan solos) vuelven a la bandeja y el texto, tipo,
    modelo, duración, formato, sonido, música y calidad quedan precargados en
    el formulario de Crear. Si la pieza es una imagen generada, ella misma
    puede entrar como referencia."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        flash(gettext("No encontré esa pieza."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Sin variables quemadas (pedido de Daniel, 2026-09-28): la bandeja queda
    # SOLO con las referencias de esta pieza — antes se sumaban a lo que
    # hubiera y las referencias «del pasado» se colaban en la pieza nueva.
    referencias_flowplus.vaciar(cliente)
    ya = set()
    for r in entry.get("referencias") or []:
        if r.get("logo") or r.get("url") in ya:
            continue
        referencias_flowplus.agregar(
            cliente, r.get("tipo") or "imagen", r["url"], frame_url=r.get("frame_url"),
            origen="reutilizada", titulo=r.get("activo") or r.get("etiqueta"), producto=r.get("producto"),
            duracion_s=r.get("duracion_s"),
        )
        ya.add(r["url"])
    if request.form.get("incluir_resultado") == "si" and entry.get("tipo") == "imagen" and entry.get("video_url") not in ya:
        referencias_flowplus.agregar(cliente, "imagen", entry["video_url"], origen="generada", titulo=gettext("Imagen generada"))
    if request.form.get("solo_referencias") == "si":
        # Para pasar al clip siguiente con los mismos personajes: solo las
        # imágenes; el texto y los ajustes arrancan en blanco.
        session.pop("fp_prefill", None)
        flash(gettext("Referencias cargadas; el texto y los ajustes quedan en blanco."), "ok")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    session["fp_prefill"] = {
        # La precarga vale una vez y solo en este proyecto (_prefill_para).
        "cliente": cliente,
        "texto": entry.get("prompt_fuente") or entry.get("accion_central") or "",
        "tipo": entry.get("tipo") or "video",
        "modelo": entry.get("modelo") or "",
        "duracion": entry.get("duracion_objetivo") or proyectos.preferencias_flowplus(cliente)["duracion_defecto"],
        "aspect_ratio": entry.get("aspect_ratio") or "9:16",
        "enfoque": entry.get("enfoque") or "",
        "con_sonido": entry.get("con_sonido", True) is not False,
        "sonido_texto": entry.get("sonido_texto") or "",
        "musica_estilo": entry.get("musica_estilo") or "",
        "musica_inicio_s": entry.get("musica_inicio_s") or 0,
        "calidad": entry.get("calidad") or "final",
        "mejorar_prompt": bool(entry.get("mejorar_prompt")),
        "preset_camara": entry.get("preset_camara"),
        "plantilla": entry.get("plantilla"),
    }
    flash(gettext("Referencias y texto cargados — ajusta lo que quieras y genera."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


def _prefill_para(cliente):
    """La precarga de «Editar y crear otra a partir de esta» vale UNA vez y
    solo en el proyecto donde se pidió (sin variables quemadas, 2026-09-28):
    pedida en un proyecto y abierto otro, se descarta. Las precargas viejas
    (sin `cliente`) siguen valiendo una vez."""
    pre = session.pop("fp_prefill", None)
    if pre and pre.get("cliente") not in (None, cliente):
        return None
    return pre


@app.route("/cliente/<cliente>/flowplus/describir", methods=["POST"])
def fp_describir(cliente):
    """Claude mira las referencias de la bandeja y propone el texto del video.
    Devuelve JSON para rellenar el cuadro sin recargar."""
    refs = referencias_flowplus.listar(cliente)
    if not refs:
        return jsonify({"ok": False, "error": gettext("Agrega primero una imagen, un video o un link.")}), 400
    try:
        texto = referencias_link.describir(refs, cliente_hint=proyectos.nombre_visible(cliente),
                                           idioma=idiomas.de_proyecto(cliente))
    except Exception as e:
        bitacora.registrar(cliente, "flowplus", "describir", "error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude describir las referencias (%(tipo)s).", tipo=type(e).__name__)}), 502
    bitacora.registrar(cliente, "flowplus", "describir", "ok", texto[:120])
    return jsonify({"ok": True, "texto": texto})


@app.route("/cliente/<cliente>/creative_flow/crear", methods=["POST"])
def cf_crear_video(cliente):
    """Crear: referencias + activos + texto de la persona → video.

    Camino por defecto (la generación tradicional): el texto de la persona
    manda, se arma el prompt determinista de siempre (flowplus_prompt.armar) y
    se genera de una, con el costo que ya vio en el botón. Con
    `modo_prompt=director` («Armar prompt con IA», opcional, para quien no sabe
    qué escribir) la sesión queda en prompt_pendiente, el worker corre
    flowplus_director (gratis) y la persona genera desde la tarjeta con
    cf_generar_video (spec director §1). Desde 2026-09-21: el director dejó de
    ser el único camino porque los clientes perdieron la generación directa."""
    accion_central = (request.form.get("accion_central") or "").strip()
    tipo = "imagen" if request.form.get("tipo") == "imagen" else "video"
    # Sonido de la escena y música al crear (spec estudio S1): solo para videos.
    con_sonido = tipo == "video" and request.form.get("con_sonido") == "si"
    sonido_texto = " ".join((request.form.get("sonido") or "").split())[:200] if tipo == "video" else ""
    musica_estilo = (request.form.get("musica_estilo") or "").strip() if tipo == "video" else ""
    # Mi música: `mat:<id>` de una canción de este proyecto, desde su segundo de inicio.
    musica_inicio_s = 0
    cancion = mi_musica.resolver(cliente, musica_estilo)
    if cancion:
        musica_inicio_s = mi_musica.inicio_valido(cancion, request.form.get("musica_inicio_s"))
    elif musica_estilo not in fe_tipos.ESTILOS_MUSICA:
        musica_estilo = ""
    prefs = proyectos.preferencias_flowplus(cliente)
    # Idioma del proyecto (spec 2026-09-26 §B4): reemplaza la vieja preferencia
    # `idioma_prompt` de FlowPlus — es lo que reciben el director y los prompts.
    idioma = idiomas.de_proyecto(cliente)
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
    # «Que Wan mejore mi prompt»: opcional y apagado por defecto (el prompt va tal
    # cual salvo que la persona lo pida); solo existe en Wan 3.0 para video.
    mejorar_prompt = request.form.get("mejorar_prompt") == "si" and modelo == "wan3" and tipo == "video"

    # Las referencias vienen de la bandeja (archivos subidos y links ya
    # descargados), en el orden en que se agregaron, con sus etiquetas.
    bandeja = referencias_flowplus.listar(cliente)
    usadas = None      # sin `bandeja_vista` (scripts/tests viejos): toda la bandeja, como antes
    if request.form.get("bandeja_vista"):
        # Lo que ves es lo que se usa: la bandeja es del proyecto y la comparten
        # todas sus personas (incidente 2026-09-25: un «solo texto» se llevó las
        # referencias que otra acababa de cargar). Solo cuentan los `ref_ids`
        # que el formulario mostraba; si alguno ya no está, no se genera nada.
        usadas = request.form.getlist("ref_ids")
        en_bandeja = {r["id"] for r in bandeja}
        if any(rid not in en_bandeja for rid in usadas):
            flash(gettext("Tu bandeja de referencias cambió (alguien más del proyecto la usó o la vació). "
                          "Revisa las referencias y vuelve a generar — no se cobró nada."), "error")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
        bandeja = [r for r in bandeja if r["id"] in set(usadas)]
    referencias = []
    for r in bandeja:
        ref = {"tipo": r["tipo"], "url": r["url"], "frame_url": r.get("frame_url") or r["url"],
               "etiqueta": r["etiqueta"], "origen": r.get("origen")}
        if r["tipo"] == "video":
            # Lo que dura el video (2026-09-30): lo medido al subirlo; las
            # referencias anteriores se miden acá si el archivo sigue en disco
            # (sin tocar la red en la petición: si no, lo mide el worker).
            dur = r.get("duracion_s")
            if dur is None and r.get("ruta_local") and os.path.exists(r["ruta_local"]):
                dur = _duracion_video(r["ruta_local"])
            ref["duracion_s"] = dur
        referencias.append(ref)
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

    # Referencias y catálogo son opcionales (2026-09-25): sin nada adjunto la
    # pieza es de solo texto (enfoque `libre`) — el texto tal cual, sin logos
    # ni marca, por la ruta text-to-video/-image del mismo modelo.
    solo_texto = not referencias
    # Incidente 2026-09-26: nada se agrega de fondo (tampoco los logos del
    # proyecto): el modelo recibe solo lo que la persona adjuntó y escribió.
    referencias = referencias[:15]
    if tipo == "video":
        flowplus_prompt.asignar_tokens(referencias, modelo)
        if solo_texto:
            # Sin imagen de arranque Seedance sí elige formato (formatos_texto).
            aspect_ratio = flowplus_modelos.ajustar_formato(modelo, request.form.get("aspect_ratio") or "", solo_texto=True)
    # referencias_urls sigue siendo la lista plana de IMÁGENES (los videos van por
    # su fotograma) — es lo que consumen los modelos que no aceptan video.
    referencias_urls = [r["frame_url"] for r in referencias][:10]
    if not accion_central:
        flash(gettext("Escribe qué tiene que pasar en el video."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Incidente 2026-09-28: una mención sin referencia (un mapa de cuatro
    # imágenes pegado con dos en la bandeja) llegaba al modelo, que inventaba o
    # duplicaba personajes. Se avisa antes de crear la sesión: no se cobra nada.
    faltan = flowplus_prompt.menciones_sin_referencia(accion_central, referencias)
    if faltan:
        disponibles = ", ".join(r["etiqueta"] for r in referencias if str(r.get("etiqueta") or "").startswith("@"))
        flash(gettext("Tu texto menciona %(menciones)s, pero en la bandeja solo hay: %(disponibles)s. "
                      "Sube lo que falta o quita esas menciones y vuelve a generar — no se cobró nada.",
                      menciones=", ".join(faltan), disponibles=disponibles or gettext("nada")), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Incidente 2026-09-28 («mira lo que sacó»): Seedance 2.5 recibe UNA imagen
    # y las otras referencias se descartaban en silencio mientras la tarjeta las
    # mostraba como usadas y se cobraba el modelo más caro. Si el modelo elegido
    # no usa todas las referencias, se avisa y no se genera: nada se cobra.
    sobran = flowplus_modelos.referencias_de_mas(modelo, referencias, tipo=tipo)
    if sobran:
        info_modelo = (flowplus_modelos.IMAGEN if tipo == "imagen" else flowplus_modelos.VIDEO)[modelo]
        nombre_modelo = gettext(info_modelo["nombre"])
        if int(info_modelo.get("max_referencias") or 0) == 1:
            primera = next((r["etiqueta"] for r in referencias if r["etiqueta"] not in sobran), "")
            flash(gettext("%(modelo)s solo usa la primera referencia (%(primera)s): no usaría %(sobran)s. "
                          "Elige Wan 3.0 o Kling O3 Pro para usarlas todas, o deja solo una — no se cobró nada.",
                          modelo=nombre_modelo, primera=primera, sobran=", ".join(sobran)), "error")
        else:
            flash(gettext("%(modelo)s usa hasta %(n)s referencias: no usaría %(sobran)s. "
                          "Quita las que sobran o cambia de modelo — no se cobró nada.",
                          modelo=nombre_modelo, n=info_modelo.get("max_referencias"), sobran=", ".join(sobran)), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Incidente 2026-09-30 (Forja): un video de referencia de 14,9 s y 20 s
    # pedidos → WaveSpeed 1405 «exceeds 30s limit». Wan 3.0 no admite más de
    # 15 s de videos de referencia ni más de 30 s entre entrada y salida: se
    # avisa y no se genera. Nada se cobra.
    problema = flowplus_modelos.problema_duracion(modelo, referencias, duracion_objetivo) if tipo == "video" else None
    if problema:
        info_modelo = flowplus_modelos.VIDEO[modelo]
        segundos = format_decimal(problema["videos_s"], format="#,##0.#")
        if problema["motivo"] == "videos_largos":
            flash(gettext("Tus videos de referencia duran %(s)s s en total y %(modelo)s admite hasta %(max)s s. "
                          "Recórtalos o quita alguno — no se cobró nada.",
                          s=segundos, modelo=gettext(info_modelo["nombre"]), max=problema["maxima_videos"]), "error")
        else:
            flash(gettext("%(modelo)s no pasa de %(total)s s sumando tus videos de referencia (%(s)s s): el resultado "
                          "puede durar hasta %(max)s s. Baja la duración o usa un video más corto — no se cobró nada.",
                          modelo=gettext(info_modelo["nombre"]), total=info_modelo["max_total_con_videos"], s=segundos,
                          max=problema["maxima"]), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    # Receta de tomas (Etapa 3 del director, 2026-09-30): solo cuenta con
    # «Crear super prompt»; «Generar video» manda el texto tal cual y la ignora.
    plantilla = None
    if tipo == "video" and request.form.get("modo_prompt") == "director":
        plantilla = plantillas_anuncio.por_id(request.form.get("plantilla"))
    if plantilla and plantilla["requiere_video"] and not any(
            str(r.get("token") or "").startswith("Video ") for r in referencias):
        nombre_receta = plantilla["nombre"]
        flash(gettext("La receta «%(receta)s» necesita un video de referencia en la bandeja y el modelo Wan 3.0. "
                      "Agrégalo o elige otra receta.", receta=gettext(nombre_receta)), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    if solo_texto:
        enfoque = "libre"
    else:
        enfoque = "persona" if any(r.get("categoria") == "personaje" for r in referencias) else "producto"
        if plantilla and plantilla["enfoque"]:
            # Con receta el enfoque lo fija la receta (spec §9); sin referencias sigue «libre».
            enfoque = plantilla["enfoque"]
    info = flowplus_prompt.ENFOQUES[enfoque]
    cf_id = creative_flow.crear(
        cliente, [], productos_sel, [],
        accion_central, duracion_objetivo, "", "A",
        referencias_urls=referencias_urls, platforms=[],
    )
    campos = dict(
        aspect_ratio=aspect_ratio, tipo=tipo, modelo=modelo, referencias=referencias,
        con_persona=info["con_persona"], enfoque=enfoque, enfoque_nombre=info["nombre"],
        con_sonido=con_sonido, sonido_texto=sonido_texto, musica_estilo=musica_estilo, musica_inicio_s=musica_inicio_s,
        prompt_fuente=accion_central, calidad=calidad, idioma_prompt=idioma, mejorar_prompt=mejorar_prompt,
        preset_camara=None, plantilla=plantilla["id"] if plantilla else None,
    )
    # Triple Whale: si el texto vino de «Llevar a Crear», la sesión recuerda de
    # qué idea salió (la pestaña enlaza idea → pieza → anuncio). Un valor raro
    # se ignora y la pieza se crea igual.
    origen_tw = triple_whale_puente.origen_desde_formulario(cliente, request.form.get("origen_tw"))
    if origen_tw:
        campos["tw_idea"] = origen_tw
    directo = dict(campos, enfoque_nombre=info["nombre"] if solo_texto else idiomas.N_("Tu texto, tal cual"))
    if tipo == "imagen":
        # La imagen no pasa por el director (spec §2.2): va el texto tal cual.
        prompt_final = flowplus_prompt.tal_cual(accion_central, referencias, idioma=idioma)
        creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_final, **directo)
        entry = creative_flow.cargar(cliente)[cf_id]
        lanzado = _lanzar_video_cf(cliente, cf_id, entry)
        _consumir_bandeja(cliente, usadas)
        nombre_modelo = flowplus_modelos.IMAGEN[modelo]["nombre"]
        if lanzado:
            detalle_flash = " · " + aspect_ratio if aspect_ratio else ""
            flash(gettext("Generando la imagen con %(modelo)s%(detalle)s…", modelo=nombre_modelo, detalle=detalle_flash), "ok")
        else:
            flash(gettext("Ya se estaba generando eso — espera a que termine."), "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    if request.form.get("modo_prompt") != "director":
        # Generación directa: el texto de la persona tal cual; el sonido solo si
        # ella lo escribió (el check sigue pidiendo el audio nativo del modelo).
        prompt_final = flowplus_prompt.tal_cual(
            accion_central, referencias, sonido=(sonido_texto or None) if con_sonido else None, idioma=idioma)
        creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_final, **directo)
        entry = creative_flow.cargar(cliente)[cf_id]
        lanzado = _lanzar_video_cf(cliente, cf_id, entry)
        _consumir_bandeja(cliente, usadas)
        nombre_modelo = flowplus_modelos.VIDEO[modelo]["nombre"]
        if lanzado:
            detalle = f" · {aspect_ratio}" if aspect_ratio else ""
            flash(gettext("Generando el video con %(modelo)s%(detalle)s · %(duracion)s s…",
                          modelo=nombre_modelo, detalle=detalle, duracion=duracion_objetivo), "ok")
            if aviso_duracion is not None:
                flash(gettext("%(modelo)s llega a %(aviso)s s: se generará de %(aviso)s s.",
                              modelo=nombre_modelo, aviso=aviso_duracion), "warn")
        else:
            flash(gettext("Ya se estaba generando eso — espera a que termine."), "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", **campos)
    encolado = _encolar_director(cliente, cf_id)
    _consumir_bandeja(cliente, usadas)
    if encolado:
        flash(gettext("Armando el prompt con IA… en unos segundos aparece aquí para que lo revises y generes."), "ok")
        if aviso_duracion is not None:
            flash(gettext("%(modelo)s llega a %(aviso)s s: se armará para %(aviso)s s.",
                          modelo=flowplus_modelos.VIDEO[modelo]["nombre"], aviso=aviso_duracion), "warn")
    else:
        flash(gettext("Ya se estaba armando ese prompt — espera a que termine."), "warn")
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
        flash(gettext("Ese prompt no se puede editar ahora."), "error")
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
        flash(gettext("Prompt guardado. Ahora sí: genera cuando quieras."), "ok")
    else:
        flash(gettext("No había cambios que guardar."), "warn")
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
        flash(gettext("Esa sesión no se puede rearmar ahora."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    estado = entry.get("estado")
    puede_rearmar = estado in ("prompt_listo", "error") or (
        estado == "prompt_pendiente" and not trabajos.en_curso(tareas_director.job_id(cliente, cf_id)))
    if not puede_rearmar:
        flash(gettext("Esa sesión no se puede rearmar ahora."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", error=None)
    if _encolar_director(cliente, cf_id):
        flash(gettext("Rearmando el prompt con IA…"), "ok")
    else:
        flash(gettext("Ya se estaba rearmando."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/recuperar", methods=["POST"])
def cf_recuperar(cliente, cf_id):
    """«Recuperar el video» (incidente 2026-09-28): la sesión quedó en error
    porque el worker dejó de esperar a WaveSpeed, pero guardó el id de la
    predicción (`prediccion`); el worker vuelve a preguntar por ese id y, si
    terminó, cierra la pieza. No genera ni paga de nuevo (max_intentos=1)."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    pred = (entry or {}).get("prediccion") or {}
    if not entry or entry.get("estado") != "error" or not pred.get("id") or (entry.get("tipo") or "video") == "imagen":
        flash(gettext("Esa pieza no tiene nada que recuperar."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Mismo orden que flowplus_lanzar.lanzar: el estado va ANTES de encolar.
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    encolado = trabajos.encolar(
        _job_id_creative_flow(cliente, cf_id), "flowplus_recuperar", {"cliente": cliente, "cf_id": cf_id},
        cliente=cliente, duracion_estimada=120, etapas=flowplus_lanzar.ETAPAS_CREATIVE_FLOW,
        max_intentos=1, prioridad=flowplus_lanzar.PRIORIDAD_NORMAL,
    )
    if encolado:
        flash(gettext("Preguntando a WaveSpeed por el video… si ya terminó, aparece aquí sin pagar de nuevo."), "ok")
    else:
        flash(gettext("Ya se estaba recuperando — espera a que termine."), "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/sugerir_sonido", methods=["POST"])
def fp_sugerir_sonido(cliente):
    """Claude sugiere qué se oye en la escena (centavos). Solo texto: no genera nada."""
    from final_edition import sonido as sonido_mod
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"error": gettext("Cuerpo inválido.")}), 400
    escena = " ".join(str(cuerpo.get("escena") or "").split())
    if not escena:
        return jsonify({"error": gettext("Escribe primero qué tiene que pasar en el video.")}), 400
    e = cuerpo.get("enfoque")
    enfoque = e if isinstance(e, str) and e in flowplus_prompt.ENFOQUES else "producto"
    try:
        texto = sonido_mod.sugerir_descripcion(escena, enfoque, idioma=idiomas.de_proyecto(cliente))
    except Exception as e:
        return jsonify({"error": gettext("No se pudo sugerir (%(tipo)s).", tipo=type(e).__name__)}), 502
    return jsonify({"sonido": texto})


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/generar_video", methods=["POST"])
def cf_generar_video(cliente, cf_id):
    """Reintento tras error, o sesiones viejas que quedaron en prompt_listo.
    Con `version_b=si` (solo video, y solo si el director dejó `prompt_b`) crea
    una sesión hija con esa versión (`creative_flow.duplicar`) y encola las dos."""
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        flash(gettext("No encontré esa sesión."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    # Guardia anti-reenvío: nunca disparar una segunda generación paga de un
    # video que ya se generó o se está generando.
    if entry.get("estado") not in ("prompt_listo", "error"):
        flash(gettext("Este video ya se generó o se está generando — no se puede volver a disparar."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not (entry.get("referencias_urls") or []) and entry.get("enfoque") != "libre":
        flash(gettext("Esta sesión no tiene imágenes de referencia — descártala y crea una nueva."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    nombre_modelo = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre") or gettext("el modelo")
    es_imagen = (entry.get("tipo") or "video") == "imagen"
    que = gettext("la imagen") if es_imagen else gettext("el video")
    prompt_b = (entry.get("director") or {}).get("prompt_b")
    # Si ya existe una hija B (de un clic anterior, o de un lote), no se crea
    # otra aunque la casilla venga marcada.
    tiene_hija_b = any(e.get("derivado_de") == cf_id and e.get("variante") == "B" for e in data.values())
    quiere_b = request.form.get("version_b") == "si" and bool(prompt_b) and not es_imagen and not tiene_hija_b
    hija = None
    if quiere_b:
        # Dos clics casi simultáneos pueden leer el mismo entry.estado
        # "prompt_listo" antes de que el primero termine de escribir: este
        # chequeo, justo antes de crear la hija, es la segunda barrera (la
        # primera es el estado de arriba) para no duplicar la generación paga.
        if trabajos.en_curso(_job_id_creative_flow(cliente, cf_id)):
            flash(gettext("Ya se está generando %(que)s — espera a que termine.", que=que), "warn")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
        try:
            hija = creative_flow.duplicar(cliente, cf_id, prompt_relleno=prompt_b, variante="B")
        except Exception as e:
            flash(gettext("No se pudo crear la versión B: %(error)s. No se generó nada.", error=e), "error")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not _lanzar_video_cf(cliente, cf_id, entry):
        flash(gettext("Ya se está generando %(que)s — espera a que termine.", que=que), "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if hija:
        _lanzar_video_cf(cliente, hija, creative_flow.cargar(cliente)[hija])
        flash(gettext("Generando las versiones A y B con %(modelo)s…", modelo=nombre_modelo), "ok")
    else:
        flash(gettext("Generando %(que)s con %(modelo)s…", que=que, modelo=nombre_modelo), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

# Se guarda como `error` de swaps, sesiones de Crear y conceptos de imagen, en
# el idioma de cada proyecto (_reconciliar_huerfanos corre al arrancar, sin petición).
_MENSAJE_INTERRUMPIDO = idiomas.N_(
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
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                interrumpido = gettext(_MENSAJE_INTERRUMPIDO)
            swaps_data = swaps_mod.cargar(cliente)
            tocado = False
            for swap_id, entry in swaps_data.items():
                if entry.get("estado") == "generando":
                    if trabajos.en_curso(f"{cliente}__{swap_id}__swap"):
                        continue
                    entry["estado"] = "error"
                    entry["error"] = interrumpido
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
                    entry["error"] = interrumpido
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
                            img["error"] = interrumpido
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
            with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
                experimentos.actualizar(cliente, eid, estado="error",
                                         error=gettext("Se interrumpió el lanzamiento; revisa Ads Manager y vuelve a intentar."))
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



# ---- Triple Whale (atribución y rendimiento; spec 2026-09-28) ----

def _volver_tw(cliente):
    # La conexión vive en la pestaña Triple Whale (2026-09-28), ya no en Configuración.
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="triplewhale"))


def _probar_triple_whale(llave, dominio, moneda):
    """None si la llave ve la tienda y puede consultar; si no, el motivo para
    la persona (sin la llave) SIN traducir: un msgid (N_) o el texto del
    proveedor. Quien lo muestra o lo guarda lo pasa por idiomas.traducir en su
    idioma (la respuesta, quien mira; el `error` guardado, el proyecto) sin
    volver a llamar a Triple Whale."""
    if not triple_whale.validar_llave(llave):
        return idiomas.N_("Triple Whale no reconoce esa llave (revocada o mal copiada).")
    try:
        triple_whale.probar(llave, dominio, moneda)
    except triple_whale.ErrorTripleWhale as e:
        return cola.sin_token(str(e))
    return None


@app.route("/cliente/<cliente>/cfg_triple_whale/conectar", methods=["POST"])
def cfg_triple_whale_conectar(cliente):
    """Prueba la llave contra la tienda (una consulta corta), la guarda
    cifrada y encola la primera copia: los últimos 90 días de métricas."""
    if not _mismo_origen():
        abort(403)
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not cifrado.disponible():
        flash(gettext("Falta FLASK_SECRET_KEY en el .env del servidor: sin ella no se pueden guardar credenciales "
                      "de Triple Whale."), "error")
        return _volver_tw(cliente)
    llave = (request.form.get("llave_api") or "").strip()
    dominio = triple_whale.normalizar_dominio(request.form.get("dominio_tienda"))
    if not llave or not dominio:
        flash(gettext("Faltan la llave o el dominio de la tienda (por ejemplo mitienda.myshopify.com)."), "error")
        return _volver_tw(cliente)
    moneda = triple_whale.normalizar_moneda(request.form.get("moneda"))
    problema = _probar_triple_whale(llave, dominio, moneda)
    if problema:
        flash(gettext("No pude conectar Triple Whale: %(error)s", error=idiomas.traducir(problema)), "error")
        return _volver_tw(cliente)
    triple_whale_tiendas.conectar(cliente, llave, dominio, moneda=moneda,
                                  modelo_atribucion=request.form.get("modelo_atribucion"),
                                  ventana_atribucion=request.form.get("ventana_atribucion"))
    tareas_tw.encolar_sync(cliente)
    flash(gettext("Triple Whale conectado. Estamos trayendo los últimos 90 días de métricas; mira la pestaña "
                  "Triple Whale en unos minutos."), "ok")
    return _volver_tw(cliente)


@app.route("/cliente/<cliente>/cfg_triple_whale/probar", methods=["POST"])
def cfg_triple_whale_probar(cliente):
    """Vuelve a probar la llave guardada contra la tienda y deja el resultado
    en el estado de la conexión."""
    if not _mismo_origen():
        abort(403)
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        flash(gettext("Triple Whale no está conectado en este proyecto."), "error")
        return _volver_tw(cliente)
    try:
        llave = triple_whale_tiendas.obtener_llave(cliente)
    except cifrado.ErrorCifrado:
        llave = None
    problema = (_probar_triple_whale(llave, config["dominio_tienda"], config["moneda"]) if llave
                else idiomas.N_("No se pudo leer la llave guardada: vuelve a conectar Triple Whale."))
    if problema:
        # El `error` guardado lo ve cualquiera que abra la pestaña después: idioma
        # del proyecto. El flash es para quien tocó el botón: su idioma.
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            guardado = idiomas.traducir(problema)
        triple_whale_tiendas.actualizar(cliente, estado="error", error=guardado)
        flash(gettext("La conexión con Triple Whale falló: %(error)s", error=idiomas.traducir(problema)), "error")
    else:
        triple_whale_tiendas.actualizar(cliente, estado="conectada", error=None)
        flash(gettext("Conexión con Triple Whale correcta."), "ok")
    return _volver_tw(cliente)


@app.route("/cliente/<cliente>/cfg_triple_whale/ajustes", methods=["POST"])
def cfg_triple_whale_ajustes(cliente):
    """Cambia moneda, modelo o ventana de atribución sin volver a pegar la
    llave. Si algo cambió, lo copiado se borra y se vuelve a traer."""
    if not _mismo_origen():
        abort(403)
    if not triple_whale_tiendas.obtener(cliente):
        flash(gettext("Triple Whale no está conectado en este proyecto."), "error")
        return _volver_tw(cliente)
    if triple_whale_tiendas.cambiar_ajustes(cliente, moneda=request.form.get("moneda"),
                                            modelo_atribucion=request.form.get("modelo_atribucion"),
                                            ventana_atribucion=request.form.get("ventana_atribucion")):
        tareas_tw.encolar_sync(cliente)
        flash(gettext("Ajustes guardados. Volvemos a traer las métricas con la nueva atribución."), "ok")
    else:
        flash(gettext("No cambiaste nada."), "ok")
    return _volver_tw(cliente)


@app.route("/cliente/<cliente>/cfg_triple_whale/desconectar", methods=["POST"])
def cfg_triple_whale_desconectar(cliente):
    """Quita la conexión y las métricas copiadas (las evaluaciones con IA ya
    pagadas se conservan)."""
    if not _mismo_origen():
        abort(403)
    triple_whale_tiendas.desconectar(cliente)
    flash(gettext("Triple Whale desconectado. Se borraron las métricas copiadas; las evaluaciones con IA se "
                  "conservan."), "ok")
    return _volver_tw(cliente)


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
