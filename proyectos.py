"""
Nombre visible de un proyecto, separado de su identificador.

El identificador es el nombre de la carpeta (clientes/<id>/) y NO se toca: es la
clave de las rutas en R2 (clientes/<id>/swaps/...), de los archivos de estado, de
los tokens de publicación y de cada entrada del historial ya generada.
Renombrar la carpeta rompería todo eso de golpe.

Por eso el nombre que se ve en pantalla vive aparte, en
clientes/<id>/proyecto.json, y se puede cambiar cuantas veces se quiera sin
consecuencias. Si no hay nombre guardado, se usa el id capitalizado, que es lo
que se mostraba antes de que esto existiera.
"""
import os

import _json_store

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "proyecto.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente), {})


def nombre_visible(cliente):
    return (cargar(cliente).get("nombre") or "").strip() or cliente.capitalize()


def guardar_nombre(cliente, nombre):
    datos = cargar(cliente)
    datos["nombre"] = (nombre or "").strip()
    _json_store.guardar(_path(cliente), datos)
