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
import fcntl
from functools import wraps

import _json_store
from final_edition.tipos import PAISES

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "proyecto.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente), {})


def nombre_visible(cliente):
    return (cargar(cliente).get("nombre") or "").strip() or cliente.capitalize()


def _con_candado(fn):
    @wraps(fn)
    def escribir(cliente, *args, **kwargs):
        ruta = _path(cliente)
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        with open(ruta + ".lock", "a+") as candado:
            fcntl.flock(candado.fileno(), fcntl.LOCK_EX)
            try:
                return fn(cliente, *args, **kwargs)
            finally:
                fcntl.flock(candado.fileno(), fcntl.LOCK_UN)
    return escribir


@_con_candado
def actualizar_campos(cliente, **campos):
    datos = _cargar_para_escribir(cliente)
    datos.update(campos)
    _json_store.guardar(_path(cliente), datos)


@_con_candado
def guardar_nombre(cliente, nombre):
    datos = _cargar_para_escribir(cliente)
    datos["nombre"] = (nombre or "").strip()
    _json_store.guardar(_path(cliente), datos)


# Modelos por defecto de Crear y la duración que sale marcada (8 s: los
# modelos rinden mejor hasta 15 s). El idioma del prompt del director ya no se
# elige acá: lo reemplaza el idioma del proyecto (`idiomas.de_proyecto`, spec
# 2026-09-26 §B4).
DEFAULTS_FLOWPLUS = {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "duracion_defecto": 8}


def preferencias_flowplus(cliente):
    datos = cargar(cliente)
    prefs = {**DEFAULTS_FLOWPLUS, **datos.get("preferencias_flowplus", {})}
    # Un proyecto.json de antes de la fase 3 puede traer un `idioma_prompt`
    # guardado en `preferencias_flowplus`: se filtra de la copia, nunca del
    # archivo (no se reescribe nada acá).
    prefs.pop("idioma_prompt", None)
    return prefs


@_con_candado
def guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, duracion_defecto=8):
    from providers import flowplus_modelos
    datos = _cargar_para_escribir(cliente)
    try:
        dur = int(duracion_defecto)
    except (TypeError, ValueError):
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    if dur not in flowplus_modelos.DURACIONES_CREAR:
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    datos["preferencias_flowplus"] = {"modelo_video": modelo_video, "modelo_imagen": modelo_imagen,
                                      "duracion_defecto": dur}
    _json_store.guardar(_path(cliente), datos)


# Sonido al crear (spec estudio S1): si los videos de Crear piden el sonido de
# la escena y qué música se mezcla al crear ("" = ninguna). El estilo lo
# valida la ruta contra final_edition.tipos.ESTILOS_MUSICA (este módulo no
# importa final_edition: final_edition importa proyectos).
DEFAULTS_SONIDO = {"con_sonido": True, "musica_al_crear": ""}


def preferencias_sonido(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_SONIDO, **datos.get("preferencias_sonido", {})}


@_con_candado
def guardar_preferencias_sonido(cliente, con_sonido, musica_al_crear):
    datos = _cargar_para_escribir(cliente)
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


@_con_candado
def guardar_preferencias(cliente, proveedor_foto, proveedor_video, mejorar_calidad):
    datos = _cargar_para_escribir(cliente)
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


@_con_candado
def guardar_reglas_defecto(cliente, reglas):
    import decisor
    data = _cargar_para_escribir(cliente)
    data["reglas_experimentos"] = {k: v for k, v in (reglas or {}).items() if k in decisor.REGLAS_DEFECTO}
    _json_store.guardar(_path(cliente), data)


def correo_notificaciones(cliente):
    """Correo al que el motor manda avisos (propuestas, ganadores, rechazos
    de Meta). None si el proyecto no configuró uno."""
    correo = (cargar(cliente).get("correo_notificaciones") or "").strip()
    return correo or None


@_con_candado
def guardar_correo_notificaciones(cliente, correo):
    datos = _cargar_para_escribir(cliente)
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


@_con_candado
def guardar_meta_forma(cliente, forma):
    """Guarda (o borra, con None) la forma elegida. No toca Meta ni meta.json."""
    if forma is not None and forma not in FORMAS_META:
        raise ValueError(f"Forma no soportada: {forma}")
    datos = _cargar_para_escribir(cliente)
    if forma is None:
        datos.pop("meta_forma", None)
    else:
        datos["meta_forma"] = forma
    _json_store.guardar(_path(cliente), datos)


def referentes_copycoders(cliente):
    """¿Este proyecto quiere ver la biblioteca global de copycoders (miles de
    anuncios) en Referentes y en las sugerencias de Sprints? Nace apagada: la
    persona la trae si la va a usar (incidente 2026-09-28)."""
    return bool(cargar(cliente).get("referentes_copycoders"))


@_con_candado
def guardar_referentes_copycoders(cliente, activa):
    datos = _cargar_para_escribir(cliente)
    datos["referentes_copycoders"] = bool(activa)
    _json_store.guardar(_path(cliente), datos)


PAISES_CALENDARIO = tuple(PAISES)


def pais(cliente):
    """País del proyecto para el calendario comercial de Sprints (ISO-3166-1
    alfa-2). Sin dato, Colombia."""
    return (cargar(cliente).get("pais") or "CO").upper()


@_con_candado
def guardar_pais(cliente, pais_nuevo):
    pais_nuevo = (pais_nuevo or "").upper()
    if pais_nuevo not in PAISES_CALENDARIO:
        raise ValueError(f"País no soportado: {pais_nuevo}")
    datos = _cargar_para_escribir(cliente)
    datos["pais"] = pais_nuevo
    _json_store.guardar(_path(cliente), datos)


# Bloque global de los prompts de Flow Plus (spec 2026-09-25 §7.3): vacío =
# el de fábrica de guiones/plantillas.py.
def bloque_global_flowplus(cliente):
    return (cargar(cliente).get("flowplus_bloque_global") or "").strip()


@_con_candado
def guardar_bloque_global_flowplus(cliente, texto):
    datos = _cargar_para_escribir(cliente)
    datos["flowplus_bloque_global"] = (texto or "").strip()
    _json_store.guardar(_path(cliente), datos)


# Doctrina, bloque 4 (§5): aprendizajes por proyecto — una línea por veredicto
# del motor («Ganó en CO: …») o escrita a mano. Los más nuevos primero.
MAX_APRENDIZAJES = 40


def aprendizajes(cliente):
    lista = cargar(cliente).get("aprendizajes") or []
    return [x for x in lista if isinstance(x, dict) and x.get("texto") and x.get("id")]


def _cargar_para_escribir(cliente):
    """`cargar` devuelve {} también cuando el archivo existe y no se pudo leer;
    escribir encima dejaría el proyecto solo con aprendizajes (reglas, idioma,
    correo… perdidos). Con un archivo no vacío que se lee como {}, se
    prefiere no escribir."""
    ruta = _path(cliente)
    data = cargar(cliente)
    if not data and os.path.exists(ruta) and os.path.getsize(ruta) > 2:
        raise OSError(f"{ruta} no se pudo leer: no se sobrescribe")
    return data


@_con_candado
def agregar_aprendizaje(cliente, item):
    """Guarda `item` (dict de doctrina.aprendizajes) al frente; corta a
    MAX_APRENDIZAJES. Le pone `en` si no lo trae."""
    from datetime import datetime
    item = dict(item)
    if not item.get("en"):
        item["en"] = datetime.now().isoformat(timespec="seconds")
    data = _cargar_para_escribir(cliente)
    data["aprendizajes"] = [item] + [x for x in aprendizajes(cliente) if x.get("id") != item.get("id")][:MAX_APRENDIZAJES - 1]
    _json_store.guardar(_path(cliente), data)
    return item


@_con_candado
def quitar_aprendizaje(cliente, aid):
    """True si existía y se quitó."""
    data = _cargar_para_escribir(cliente)
    lista = aprendizajes(cliente)
    nueva = [x for x in lista if x.get("id") != aid]
    if len(nueva) == len(lista):
        return False
    data["aprendizajes"] = nueva
    _json_store.guardar(_path(cliente), data)
    return True
