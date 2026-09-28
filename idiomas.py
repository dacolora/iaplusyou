"""Idioma de la interfaz y del proyecto (spec docs/superpowers/specs/
2026-09-26-idioma-y-modo-oscuro-design.md §B1-§B3). Único módulo que decide
idioma:

  - de la persona (usuarios.json, campo "idioma"): en qué idioma ve las pantallas;
  - del proyecto (clientes/<c>/proyecto.json, campo "idioma"): en qué idioma
    escribe Claude y salen los anuncios de ese proyecto (fases 3-6);
  - antes del login, la cookie `idioma`.

Sin campo = DEFECTO. DEFECTO pasa a "en" y ACTIVO_PARA_TODOS a True al cerrar
la fase 6: ese día todos los usuarios y proyectos que no eligieron pasan a
inglés. Mientras tanto el selector solo lo ve el admin.

El texto en español es la fuente (msgid); el inglés vive en
translations/en/LC_MESSAGES/messages.po (catalogo_i18n.py lo extrae y compila).
Import liviano a propósito (flask_babel, usuarios y proyectos se importan dentro
de las funciones): providers/ y otros módulos del worker importan N_ de acá.
Formatos de fecha y número por idioma: activo, mes_largo, meses_cortos,
fecha_corta, dia_mes, numero (Babel/CLDR)."""
import os
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIR_TRADUCCIONES = os.path.join(BASE_DIR, "translations")
IDIOMAS = ("en", "es")
NOMBRES = {"en": "English", "es": "Español"}
DEFECTO = "es"
ACTIVO_PARA_TODOS = False
COOKIE = "idioma"

_app_fuera = None


def N_(texto):
    """Marca un texto de una constante de módulo para el catálogo sin
    traducirlo todavía; se traduce donde se muestra (`|traducir` o gettext)."""
    return texto


def normalizar(valor):
    v = str(valor or "").strip().lower()
    return v if v in IDIOMAS else None


def _validar(idioma):
    v = normalizar(idioma)
    if v is None:
        raise ValueError(f"Idioma inválido: {idioma!r}. Opciones: {IDIOMAS}")
    return v


_NOMBRES_PARA_CLAUDE = {"en": "inglés", "es": "español"}
# Revisión final fase 3 (finding 1): sin el «salvo…» estas órdenes contradecían
# a los sitios que SIEMPRE piden partes en inglés (los tokens Image N/Video N —
# director.py regla 8 — y el prompt para el modelo de video/imagen en
# guiones/refinador.py e imagenes.py): con un proyecto en español, la orden
# pisaba esa instrucción y el modelo podía devolver "Imagen 1" en vez de
# "Image 1", rompiendo la referencia. El «salvo» dentro de cada orden nombra
# esa única excepción sin abrir la puerta a nada más.
_ORDENES = {
    "en": ("IDIOMA: escribe en inglés (English) todo el texto que devuelvas, aunque estas instrucciones estén en "
           "español; los tokens Image N / Video N van siempre así."),
    "es": ("IDIOMA: escribe en español todo el texto que devuelvas, salvo lo que estas instrucciones pidan "
           "expresamente en inglés (los tokens Image N / Video N y los prompts para los modelos de video o "
           "imagen)."),
}


def nombre_para_claude(idioma):
    """Nombre del idioma para meterlo en instrucciones a Claude (que están en español)."""
    return _NOMBRES_PARA_CLAUDE[normalizar(idioma) or DEFECTO]


def orden_idioma(idioma):
    """La línea que va al inicio y al final de las instrucciones de cada sitio
    (doctrina.bloque_system(idioma=)): sin ella el español de las instrucciones
    arrastra la salida."""
    return _ORDENES[normalizar(idioma) or DEFECTO]


def de_usuario(usuario):
    import usuarios
    entry = usuarios.obtener(usuario) if usuario else None
    return normalizar((entry or {}).get("idioma")) or DEFECTO


def guardar_de_usuario(usuario, idioma):
    import usuarios
    usuarios.actualizar(usuario, idioma=_validar(idioma))


def de_proyecto(cliente):
    import proyectos
    return normalizar(proyectos.cargar(cliente).get("idioma")) or DEFECTO


def guardar_de_proyecto(cliente, idioma):
    import _json_store
    import proyectos
    datos = proyectos.cargar(cliente)
    datos["idioma"] = _validar(idioma)
    _json_store.guardar(proyectos._path(cliente), datos)


def de_tarea(tarea):
    """Idioma del proyecto de una fila `tarea` (columna `cliente`, o
    `payload.cliente`). Sin proyecto, uno interno («_creatv») o si leerlo
    falla: DEFECTO."""
    cliente = tarea.get("cliente") or (tarea.get("payload") or {}).get("cliente")
    if not cliente or str(cliente).startswith("_"):
        return DEFECTO
    try:
        return de_proyecto(cliente)
    except Exception:  # noqa: BLE001 — leer el idioma nunca tumba una tarea
        return DEFECTO


def de_peticion():
    """locale_selector de Flask-Babel: la persona en sesión, si no la cookie,
    si no DEFECTO. Sin contexto de petición (un gettext() suelto en un
    app_context de worker/test) no hay ni sesión ni cookies que mirar: DEFECTO
    tal cual, en vez de que Flask lance RuntimeError."""
    from flask import has_request_context, request, session
    if not has_request_context():
        return DEFECTO
    usuario = session.get("usuario")
    if usuario:
        return de_usuario(usuario)
    return normalizar(request.cookies.get(COOKIE)) or DEFECTO


def traducir(texto):
    """Filtro Jinja `|traducir` para valores marcados con N_ (y cualquier
    texto que ya esté en el catálogo). Vacío o None vuelven tal cual."""
    if not texto:
        return texto
    from flask_babel import gettext
    return gettext(texto)


def activo():
    """Idioma del contexto actual: el forzado con en_idioma, el de la
    petición (Flask-Babel), o DEFECTO fuera de toda app."""
    try:
        from flask_babel import get_locale
        loc = get_locale()
    except Exception:  # noqa: BLE001 — fuera de toda app no hay locale
        loc = None
    return (normalizar(str(loc)) if loc else None) or DEFECTO


def _loc(idioma):
    return normalizar(idioma) or activo()


def mes_largo(numero, idioma=None):
    """«septiembre» / «September» (CLDR, forma suelta)."""
    from babel.dates import get_month_names
    return get_month_names("wide", context="stand-alone", locale=_loc(idioma))[int(numero)]


def meses_cortos(idioma=None):
    """Los 12 meses abreviados de CLDR («ene», …, «sept», …, «dic» / «Jan», …)."""
    from babel.dates import get_month_names
    nombres = get_month_names("abbreviated", context="format", locale=_loc(idioma))
    return [nombres[i] for i in range(1, 13)]


def fecha_corta(fecha, con_hora=False, idioma=None):
    """«20 sept» / «20 Sep»; con hora, «25 sept · 15:04». `fecha` es date o
    datetime (un datetime sin zona se toma tal cual, sin convertir)."""
    from babel.dates import format_date, format_datetime
    loc = _loc(idioma)
    if con_hora:
        return format_datetime(fecha, "d MMM · HH:mm", locale=loc)
    return format_date(fecha, "d MMM", locale=loc)


_PATRON_DIA_MES = {"es": "dd/MM", "en": "MM/dd"}


def dia_mes(fecha, idioma=None):
    """Día y mes en números: «20/09» en español, «09/20» en inglés."""
    from babel.dates import format_date
    loc = _loc(idioma)
    return format_date(fecha, _PATRON_DIA_MES[loc], locale=loc)


def numero(valor, decimales=0, idioma=None):
    """Miles y decimales del idioma: «1.250.000» / «1,250,000»; con
    decimales=2, «12,50» / «12.50». El patrón explícito agrupa también los
    números de 4 cifras («4.000»), como el código de antes. Redondea con
    `f"{valor:.{decimales}f}"` ANTES de pasarlo a Babel — el redondeo de
    Babel es half-even sobre el valor exacto y difiere del de `format()` en
    el último dígito para casos como 12.345 o 0.015 (revisión final fase 4,
    hallazgo M2): sin este paso el español dejaba de coincidir con lo que
    mostraba main antes de esta rama."""
    from babel.numbers import format_decimal
    patron = "#,##0" + ("." + "0" * int(decimales) if decimales else "")
    valor = float(f"{float(valor):.{int(decimales)}f}")
    return format_decimal(valor, patron, locale=_loc(idioma))


def separador_decimal(idioma=None):
    """«,» en español, «.» en inglés (CLDR): el símbolo que usa `numero`,
    para un formato a medida (como el eje compacto del gráfico del Tablero,
    con su propio recorte de ceros) que solo necesita cambiar el símbolo,
    no recalcular todo con `numero`."""
    from babel.numbers import get_decimal_symbol
    return get_decimal_symbol(_loc(idioma))


def _app_fuera_de_peticion():
    global _app_fuera
    if _app_fuera is None:
        from flask import Flask
        from flask_babel import Babel
        app = Flask("idiomas", root_path=BASE_DIR)
        app.config["BABEL_DEFAULT_LOCALE"] = "es"
        app.config["BABEL_TRANSLATION_DIRECTORIES"] = DIR_TRADUCCIONES
        Babel(app, locale_selector=lambda: DEFECTO)
        _app_fuera = app
    return _app_fuera


@contextmanager
def en_idioma(idioma):
    """Traduce en `idioma` lo que se arme adentro: un correo para otra persona,
    un mensaje del worker. Dentro de una petición usa force_locale; fuera de
    toda app (worker) arma una app mínima con el mismo catálogo."""
    from flask import has_app_context
    from flask_babel import force_locale
    idioma = normalizar(idioma) or DEFECTO
    if has_app_context():
        with force_locale(idioma):
            yield
        return
    with _app_fuera_de_peticion().app_context(), force_locale(idioma):
        yield
