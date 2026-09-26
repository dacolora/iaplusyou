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


# Modelos por defecto de Crear, idioma del prompt del director ("es" para
# revisarlo cómodo; "en" para la prueba A/B del spec director §12) y la
# duración que sale marcada (8 s: los modelos rinden mejor hasta 15 s).
IDIOMAS_PROMPT = ("es", "en")
DEFAULTS_FLOWPLUS = {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "es", "duracion_defecto": 8}


def preferencias_flowplus(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_FLOWPLUS, **datos.get("preferencias_flowplus", {})}


def guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, idioma_prompt="es", duracion_defecto=8):
    from providers import flowplus_modelos
    datos = cargar(cliente)
    idioma = idioma_prompt if idioma_prompt in IDIOMAS_PROMPT else "es"
    try:
        dur = int(duracion_defecto)
    except (TypeError, ValueError):
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    if dur not in flowplus_modelos.DURACIONES_CREAR:
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    datos["preferencias_flowplus"] = {"modelo_video": modelo_video, "modelo_imagen": modelo_imagen,
                                      "idioma_prompt": idioma, "duracion_defecto": dur}
    _json_store.guardar(_path(cliente), datos)


# Sonido al crear (spec estudio S1): si los videos de Crear piden el sonido de
# la escena y qué música se mezcla al crear ("" = ninguna). El estilo lo
# valida la ruta contra final_edition.tipos.ESTILOS_MUSICA (este módulo no
# importa final_edition: final_edition importa proyectos).
DEFAULTS_SONIDO = {"con_sonido": True, "musica_al_crear": ""}


def preferencias_sonido(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_SONIDO, **datos.get("preferencias_sonido", {})}


def guardar_preferencias_sonido(cliente, con_sonido, musica_al_crear):
    datos = cargar(cliente)
    datos["preferencias_sonido"] = {"con_sonido": bool(con_sonido), "musica_al_crear": str(musica_al_crear or "")}
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


def reglas_defecto(cliente):
    """Reglas del decisor por defecto del proyecto (Configuración). Solo claves conocidas."""
    import decisor
    data = cargar(cliente).get("reglas_experimentos") or {}
    return {k: v for k, v in data.items() if k in decisor.REGLAS_DEFECTO}


def guardar_reglas_defecto(cliente, reglas):
    import decisor
    data = cargar(cliente)
    data["reglas_experimentos"] = {k: v for k, v in (reglas or {}).items() if k in decisor.REGLAS_DEFECTO}
    _json_store.guardar(_path(cliente), data)


def correo_notificaciones(cliente):
    """Correo al que el motor manda avisos (propuestas, ganadores, rechazos
    de Meta). None si el proyecto no configuró uno."""
    correo = (cargar(cliente).get("correo_notificaciones") or "").strip()
    return correo or None


def guardar_correo_notificaciones(cliente, correo):
    datos = cargar(cliente)
    datos["correo_notificaciones"] = (correo or "").strip()
    _json_store.guardar(_path(cliente), datos)


FORMAS_META = ("agencia", "propia")


def meta_forma(cliente):
    """Forma de conectar Meta que eligió el cliente ("agencia": Creatv lo
    gestiona; "propia": su app) o None si todavía no eligió. Es la intención
    antes de conectar; el estado real de la conexión sigue siendo
    meta_conexion.modo()."""
    forma = cargar(cliente).get("meta_forma")
    return forma if forma in FORMAS_META else None


def guardar_meta_forma(cliente, forma):
    """Guarda (o borra, con None) la forma elegida. No toca Meta ni meta.json."""
    if forma is not None and forma not in FORMAS_META:
        raise ValueError(f"Forma no soportada: {forma}")
    datos = cargar(cliente)
    if forma is None:
        datos.pop("meta_forma", None)
    else:
        datos["meta_forma"] = forma
    _json_store.guardar(_path(cliente), datos)


PAISES_CALENDARIO = ("CO", "MX", "US", "ES", "BR", "AR", "CL", "PE")


def pais(cliente):
    """País del proyecto para el calendario comercial de Sprints (ISO-3166-1
    alfa-2). Sin dato, Colombia."""
    return (cargar(cliente).get("pais") or "CO").upper()


def guardar_pais(cliente, pais_nuevo):
    pais_nuevo = (pais_nuevo or "").upper()
    if pais_nuevo not in PAISES_CALENDARIO:
        raise ValueError(f"País no soportado: {pais_nuevo}")
    datos = cargar(cliente)
    datos["pais"] = pais_nuevo
    _json_store.guardar(_path(cliente), datos)


# Bloque global de los prompts de Flow Plus (spec 2026-09-25 §7.3): vacío =
# el de fábrica de guiones/plantillas.py.
def bloque_global_flowplus(cliente):
    return (cargar(cliente).get("flowplus_bloque_global") or "").strip()


def guardar_bloque_global_flowplus(cliente, texto):
    datos = cargar(cliente)
    datos["flowplus_bloque_global"] = (texto or "").strip()
    _json_store.guardar(_path(cliente), datos)
