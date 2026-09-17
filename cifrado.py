"""Cifrado simétrico de credenciales de tiendas (spec §2 `tienda.credenciales`):
Fernet con clave derivada de FLASK_SECRET_KEY. Sin esa variable no se puede
conectar ninguna tienda — y rotarla deja ilegibles las credenciales guardadas
(hay que volver a conectar)."""
import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SAL = b"creatv-tiendas"


class ErrorCifrado(Exception):
    pass


def disponible():
    return bool(os.environ.get("FLASK_SECRET_KEY"))


def _fernet():
    clave = os.environ.get("FLASK_SECRET_KEY")
    if not clave:
        raise ErrorCifrado("Falta FLASK_SECRET_KEY en .env: sin ella no se pueden guardar credenciales de tiendas.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SAL, iterations=200_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(clave.encode("utf-8"))))


def cifrar(texto):
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token):
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ErrorCifrado("No se pudieron leer las credenciales guardadas (¿cambió FLASK_SECRET_KEY?). Vuelve a conectar la tienda.") from e
