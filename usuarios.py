"""
Usuarios y control de acceso por proyecto. Un solo archivo usuarios.json en la
raíz (no por cliente, porque necesita mapear usuario -> proyecto a través de
todos los clientes), con la misma convención de _json_store.py.

Dos roles:
  - "admin": ve y entra a cualquier proyecto, sin restricción.
  - "cliente": solo puede entrar al proyecto en su campo "cliente" — cualquier
    otra ruta que reciba un cliente distinto en la URL se rechaza en el
    servidor (ver el guard en dashboard.py), nunca solo ocultando un botón.

Las contraseñas nunca se guardan en texto plano — solo su hash
(werkzeug.security.generate_password_hash). usuarios.json está en
.gitignore, igual que cualquier otro archivo con credenciales de este
proyecto.
"""
import os

from werkzeug.security import check_password_hash, generate_password_hash

import _json_store

BASE_DIR = os.path.dirname(__file__)
ROLES_VALIDOS = ("admin", "cliente")


def _path():
    return os.path.join(BASE_DIR, "usuarios.json")


def cargar():
    return _json_store.cargar(_path(), {})


def guardar(data):
    _json_store.guardar(_path(), data)


def existe(usuario):
    return usuario in cargar()


def crear(usuario, password, rol, cliente=None):
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol inválido: {rol}. Opciones: {ROLES_VALIDOS}")
    if rol == "cliente" and not cliente:
        raise ValueError("Un usuario con rol 'cliente' necesita un proyecto asignado.")
    data = cargar()
    if usuario in data:
        raise ValueError(f"Ya existe un usuario '{usuario}'.")
    data[usuario] = {
        # pbkdf2:sha256 explícito: el scrypt por defecto de werkzeug necesita
        # hashlib.scrypt, que este build de Python no tiene disponible.
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "rol": rol,
        "cliente": cliente,
    }
    guardar(data)


def verificar(usuario, password):
    """Devuelve el registro del usuario si la contraseña es correcta, o None."""
    entry = cargar().get(usuario)
    if not entry:
        return None
    if not check_password_hash(entry["password_hash"], password):
        return None
    return entry


def puede_acceder(sesion, cliente):
    """sesion: dict con al menos 'rol' y 'cliente' (lo que se guarda en la
    sesión de Flask tras el login). True si esa sesión tiene permiso de
    tocar ese cliente."""
    if not sesion:
        return False
    if sesion.get("rol") == "admin":
        return True
    return sesion.get("cliente") == cliente
