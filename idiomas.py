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
de las funciones): providers/ y otros módulos del worker importan N_ de acá."""
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


def de_peticion():
    """locale_selector de Flask-Babel: la persona en sesión, si no la cookie,
    si no DEFECTO."""
    from flask import request, session
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
