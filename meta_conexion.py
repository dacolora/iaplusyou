"""
Conexión de un proyecto con Meta (Facebook Login for Business) y sus
credenciales en clientes/<cliente>/meta.json.

Reemplaza a auth/auth_meta.py y auth/auth_meta_ads.py: la autorización ya no
es un script de terminal con callback en localhost, es una ruta de la app —
así funciona en el VPS y desde el celular. Un solo permiso cubre anuncios
(meta_ads/) y publicación orgánica (uploaders/meta_uploader.py).

Reglas que este módulo hace cumplir por sí mismo:
  - El token nunca entra a un mensaje de excepción, log ni dry_run.
  - META_APP_SECRET solo se lee en cambiar_code_por_token().
  - meta.json se escribe atómico (tmp + os.replace) y con permisos 0600.

Ver docs/superpowers/specs/2026-09-11-conexion-meta-design.md.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Una sola versión para todo lo de Meta. meta_ads/auth.py y
# uploaders/meta_uploader.py llevan el MISMO valor (no se importa entre repos:
# meta_ads es un submódulo que no debe depender del anfitrión).
GRAPH_VERSION = "v25.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
DIALOG_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

# Códigos de error de Graph que significan "esta conexión ya no sirve"
# (token inválido/expirado, permiso retirado). Cualquier otro error NO cambia
# el estado guardado: un timeout no es una desconexión.
CODIGOS_CONEXION_ROTA = {190, 10, 200}

_TTL_ESTADO_SEG = 600
_cache_estado = {}


class MetaConexionError(RuntimeError):
    """Error legible para el usuario. Nunca contiene un token."""

    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------- configuración de la app (viene del .env raíz) ----------

def _env_obligatoria(clave, para_que):
    valor = os.environ.get(clave, "").strip()
    if not valor:
        raise MetaConexionError(f"Falta {clave} en el .env — hace falta para {para_que}.")
    return valor


def redirect_uri():
    return os.environ.get("META_REDIRECT_URI", "").strip() or "http://localhost:5050/meta/callback"


def nuevo_state():
    return secrets.token_urlsafe(32)


def url_dialogo(state):
    """URL del diálogo de Facebook Login for Business. config_id reemplaza a
    scope: la configuración (creada en el panel de la app) define el tipo de
    token y los permisos. override_default_response_type va por si la
    configuración pide token de usuario del sistema — se confirma contra
    Meta en la Task 7 del plan."""
    params = {
        "client_id": _env_obligatoria("META_APP_ID", "abrir el diálogo de Meta"),
        "config_id": _env_obligatoria("META_LOGIN_CONFIG_ID", "abrir el diálogo de Meta"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "response_type": "code",
        "override_default_response_type": "true",
    }
    return f"{DIALOG_URL}?{urlencode(params)}"


# ---------- meta.json por cliente ----------

def _dir(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente)


def _path(cliente):
    return os.path.join(_dir(cliente), "meta.json")


def _path_pendiente(cliente):
    return os.path.join(_dir(cliente), "meta.pendiente.json")


def _escribir_atomico(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, ruta)


def _leer(ruta):
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (ValueError, OSError):
        # Corrupto: se trata como "sin conectar" (nunca como excepción en una
        # ruta) y se deja rastro. Import tardío para no acoplar el módulo.
        try:
            import bitacora
            cliente = os.path.basename(os.path.dirname(ruta))
            bitacora.registrar(cliente, "meta", "conexion", "error", f"{os.path.basename(ruta)} ilegible")
        except Exception:
            pass
        return None
    return datos if isinstance(datos, dict) else None


def _borrar(ruta):
    if not os.path.exists(ruta):
        return False
    os.remove(ruta)
    return True


def cargar(cliente):
    return _leer(_path(cliente))


def guardar(cliente, datos):
    _escribir_atomico(_path(cliente), datos)
    _cache_estado.pop(cliente, None)


def borrar(cliente):
    _cache_estado.pop(cliente, None)
    return _borrar(_path(cliente))


def cargar_pendiente(cliente):
    return _leer(_path_pendiente(cliente))


def guardar_pendiente(cliente, datos):
    _escribir_atomico(_path_pendiente(cliente), datos)


def borrar_pendiente(cliente):
    return _borrar(_path_pendiente(cliente))


def credenciales_ads(cliente):
    """Lo que meta_ads/auth.configurar() necesita, o MetaConexionError si el
    proyecto no está conectado. ad_account_id se guarda tal cual lo devuelve
    Meta (con el prefijo act_); meta_ads/auth lo normaliza."""
    datos = cargar(cliente)
    if not datos or not datos.get("token") or not datos.get("ad_account_id"):
        raise MetaConexionError("Este proyecto no tiene Meta conectado — conéctalo en FlowMarketing.")
    return {
        "token": datos["token"],
        "ad_account_id": datos["ad_account_id"],
        "page_id": datos.get("page_id"),
        "ig_user_id": datos.get("ig_user_id"),
    }
