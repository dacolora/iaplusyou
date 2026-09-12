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


DEFAULTS_FLOWPLUS = {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"}


def preferencias_flowplus(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_FLOWPLUS, **datos.get("preferencias_flowplus", {})}


def guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen):
    datos = cargar(cliente)
    datos["preferencias_flowplus"] = {"modelo_video": modelo_video, "modelo_imagen": modelo_imagen}
    _json_store.guardar(_path(cliente), datos)


# Modelo por defecto para FlowClone (cambiar calzado): antes se elegía cada
# vez desde un selector en la propia pantalla de generar — eso mezclaba una
# decisión de configuración (qué modelo usar) con el flujo de uso diario.
# Ahora vive acá, uno por cliente, editable solo desde FlowSettings.
DEFAULTS_PREFERENCIAS = {
    "proveedor_foto": "nano_banana",
    "proveedor_video": "seedance25_edit",
    "mejorar_calidad": True,
}


def preferencias(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_PREFERENCIAS, **datos.get("preferencias_swap", {})}


def guardar_preferencias(cliente, proveedor_foto, proveedor_video, mejorar_calidad):
    datos = cargar(cliente)
    datos["preferencias_swap"] = {
        "proveedor_foto": proveedor_foto,
        "proveedor_video": proveedor_video,
        "mejorar_calidad": bool(mejorar_calidad),
    }
    _json_store.guardar(_path(cliente), datos)
