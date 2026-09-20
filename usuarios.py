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

Cada usuario tiene además (plan 2026-09-19, cuentas con correo verificado):
  - "correo": en minúsculas y sin espacios, o None si todavía no lo puso.
  - "correo_verificado": True solo cuando abrió el enlace de verificación
    (cuentas.py) o un admin lo marcó a mano.
  - "creado_en": ISO de la creación.
  - "session_version": entero que sube al cambiar la contraseña; la sesión
    de Flask guarda el valor con el que entró y el guard cierra las que no
    coincidan (así restablecer la contraseña saca a quien la tuviera abierta).
Los registros viejos no traen esas llaves: todo lector pasa por `_completar`,
que rellena correo=None, correo_verificado=False, session_version=1.
"""
import os
import re
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import _json_store

BASE_DIR = os.path.dirname(__file__)
ROLES_VALIDOS = ("admin", "cliente")
PASSWORD_MINIMO = 8
CORREO_MAXIMO = 254
USUARIO_REGEX = re.compile(r"^[a-z0-9._-]{3,40}$")
# Lo único que actualizar() acepta tocar; el rol y el proyecto no se cambian
# por acá. La contraseña NO está acá a propósito: solo cambiar_password
# puede escribir password_hash, porque es la única que sube session_version
# (si actualizar() pudiera tocarla, una ruta podría cambiar la contraseña sin
# cerrar las sesiones abiertas con la vieja).
CAMPOS_ACTUALIZABLES = ("correo", "correo_verificado", "session_version")


def _path():
    return os.path.join(BASE_DIR, "usuarios.json")


def cargar():
    return _json_store.cargar(_path(), {})


def guardar(data):
    _json_store.guardar(_path(), data)


def existe(usuario):
    return usuario in cargar()


def _completar(entry):
    """Rellena las llaves que los registros anteriores al correo no tienen.
    Devuelve el mismo dict (mutado) para que quien lo guarde persista los
    defaults."""
    entry.setdefault("correo", None)
    entry.setdefault("correo_verificado", False)
    entry.setdefault("session_version", 1)
    entry.setdefault("creado_en", None)
    return entry


def _hash(password):
    # pbkdf2:sha256 explícito: el scrypt por defecto de werkzeug necesita
    # hashlib.scrypt, que este build de Python no tiene disponible.
    return generate_password_hash(password, method="pbkdf2:sha256")


def validar_correo(correo):
    """Devuelve el correo normalizado (minúsculas, sin espacios alrededor) o
    None si no tiene pinta de correo: exactamente una @, algo antes, un
    dominio con punto, sin espacios y de largo razonable."""
    if not isinstance(correo, str):
        return None
    c = correo.strip().lower()
    if not c or len(c) > CORREO_MAXIMO or c.count("@") != 1:
        return None
    if any(ch.isspace() for ch in c):
        return None
    local, dominio = c.split("@")
    if not local or not dominio:
        return None
    if "." not in dominio or dominio.startswith(".") or dominio.endswith(".") or ".." in dominio:
        return None
    return c


def validar_password(password):
    """None si la contraseña sirve; si no, el mensaje (en español) para el
    formulario."""
    if not isinstance(password, str) or len(password) < PASSWORD_MINIMO:
        return f"La contraseña debe tener al menos {PASSWORD_MINIMO} caracteres."
    return None


def validar_usuario(usuario):
    """None si el nombre de usuario sirve; si no, el mensaje (en español)
    para el formulario. Solo minúsculas, dígitos, punto, guion y guion bajo,
    entre 3 y 40 caracteres — así el usuario nunca puede meter texto libre
    (saltos de línea, frases) en un correo que lo cita (ver M3 de la
    revisión de la Task 1: email-body injection vía nombre de usuario).
    Solo se exige al crear: los usuarios ya existentes con otro formato
    siguen funcionando igual, esto no los toca."""
    if not isinstance(usuario, str) or not USUARIO_REGEX.match(usuario):
        return ("El usuario debe tener entre 3 y 40 caracteres: solo minúsculas, "
                "números, puntos, guiones y guiones bajos.")
    return None


def _correo_en_uso(data, correo_norm, salvo_usuario=None):
    """True si algún usuario (≠ salvo_usuario) ya tiene ese correo (ya
    normalizado)."""
    for nombre, entry in data.items():
        if nombre == salvo_usuario:
            continue
        actual = (entry.get("correo") or "").strip().lower()
        if actual and actual == correo_norm:
            return True
    return False


def crear(usuario, password, rol, cliente=None, correo=None):
    error_usuario = validar_usuario(usuario)
    if error_usuario:
        raise ValueError(error_usuario)
    if rol not in ROLES_VALIDOS:
        raise ValueError(f"Rol inválido: {rol}. Opciones: {ROLES_VALIDOS}")
    if rol == "cliente" and not cliente:
        raise ValueError("Un usuario con rol 'cliente' necesita un proyecto asignado.")
    correo_norm = None
    if correo is not None and str(correo).strip():
        correo_norm = validar_correo(correo)
        if correo_norm is None:
            raise ValueError("El correo no es válido.")
    data = cargar()
    if usuario in data:
        raise ValueError(f"Ya existe un usuario '{usuario}'.")
    if correo_norm is not None and _correo_en_uso(data, correo_norm):
        raise ValueError("Ese correo ya está en uso.")
    data[usuario] = {
        "password_hash": _hash(password),
        "rol": rol,
        "cliente": cliente,
        "correo": correo_norm,
        "correo_verificado": False,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
        "session_version": 1,
    }
    guardar(data)


def obtener(usuario):
    """Copia del registro del usuario (con defaults rellenados) SIN
    password_hash, o None. Es lo que puede llegar a session/templates sin
    riesgo; para lo que sí necesita el hash (verificar la contraseña) usa
    obtener_hash."""
    entry = cargar().get(usuario)
    if not entry:
        return None
    entry = _completar(dict(entry))
    entry.pop("password_hash", None)
    return entry


def obtener_hash(usuario):
    """Como obtener(), pero con password_hash incluido — solo para el lector
    interno que de verdad lo necesita (verificar ya lee directo de cargar()
    y no pasa por acá; esto es para otros casos internos que lo requieran)."""
    entry = cargar().get(usuario)
    if not entry:
        return None
    return _completar(dict(entry))


def verificar(usuario, password):
    """Devuelve el registro del usuario si la contraseña es correcta, o None."""
    entry = cargar().get(usuario)
    if not entry:
        return None
    if not check_password_hash(entry["password_hash"], password):
        return None
    return _completar(entry)


def actualizar(usuario, **campos):
    """Cambia campos de un usuario existente (solo CAMPOS_ACTUALIZABLES:
    correo, correo_verificado, session_version — la contraseña no se toca
    por acá, solo cambiar_password la cambia). `correo` se normaliza (None
    o "" lo borra) y se rechaza si ya lo tiene otro usuario. Devuelve el
    registro actualizado."""
    desconocidos = [k for k in campos if k not in CAMPOS_ACTUALIZABLES]
    if desconocidos:
        raise ValueError(f"Campos no actualizables: {desconocidos}")
    data = cargar()
    entry = data.get(usuario)
    if not entry:
        raise ValueError(f"No existe el usuario '{usuario}'.")
    _completar(entry)
    if "correo" in campos:
        nuevo = campos.pop("correo")
        if nuevo is None or not str(nuevo).strip():
            entry["correo"] = None
        else:
            norm = validar_correo(nuevo)
            if norm is None:
                raise ValueError("El correo no es válido.")
            if _correo_en_uso(data, norm, salvo_usuario=usuario):
                raise ValueError("Ese correo ya está en uso.")
            entry["correo"] = norm
    if "correo_verificado" in campos:
        entry["correo_verificado"] = bool(campos.pop("correo_verificado"))
    if "session_version" in campos:
        entry["session_version"] = int(campos.pop("session_version"))
    guardar(data)
    return entry


def por_correo(correo):
    """(usuario, registro) del primer usuario con ese correo (comparación en
    minúsculas) o None. Un correo que no valida nunca coincide."""
    norm = validar_correo(correo)
    if norm is None:
        return None
    for nombre, entry in cargar().items():
        actual = (entry.get("correo") or "").strip().lower()
        if actual and actual == norm:
            return nombre, _completar(entry)
    return None


def cambiar_password(usuario, nueva):
    """Guarda el hash de la nueva contraseña y sube session_version, con lo
    que cualquier otra sesión abierta con la versión vieja queda fuera.
    Devuelve la nueva session_version."""
    error = validar_password(nueva)
    if error:
        raise ValueError(error)
    data = cargar()
    entry = data.get(usuario)
    if not entry:
        raise ValueError(f"No existe el usuario '{usuario}'.")
    _completar(entry)
    entry["password_hash"] = _hash(nueva)
    entry["session_version"] = int(entry.get("session_version") or 1) + 1
    guardar(data)
    return entry["session_version"]


def puede_acceder(sesion, cliente):
    """sesion: dict con al menos 'rol' y 'cliente' (lo que se guarda en la
    sesión de Flask tras el login). True si esa sesión tiene permiso de
    tocar ese cliente."""
    if not sesion:
        return False
    if sesion.get("rol") == "admin":
        return True
    return sesion.get("cliente") == cliente
