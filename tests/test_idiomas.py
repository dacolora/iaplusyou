"""idiomas.py (spec 2026-09-26-idioma-y-modo-oscuro §B1-§B2): el único módulo
que decide idioma. Se prueba con una app Flask mínima y un catálogo de prueba
compilado al vuelo, para no depender de lo que ya esté traducido."""
import io
import os

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from flask import Flask, render_template_string, session
from flask_babel import Babel, gettext, ngettext

import idiomas

TRADUCCIONES = [
    ("Hola", "Hello"),
    ("Quedan %(n)s", "%(n)s left"),
    ("100%% listo", "100%% ready"),
    (("%(num)d pieza", "%(num)d piezas"), ("%(num)d piece", "%(num)d pieces")),
]


def _catalogo(tmp_path):
    cat = Catalog(locale="en")
    for msgid, msgstr in TRADUCCIONES:
        cat.add(msgid, msgstr)
    carpeta = tmp_path / "translations" / "en" / "LC_MESSAGES"
    carpeta.mkdir(parents=True)
    with open(carpeta / "messages.mo", "wb") as f:
        write_mo(f, cat)
    return str(tmp_path / "translations")


@pytest.fixture()
def app_prueba(tmp_path, monkeypatch):
    dir_trad = _catalogo(tmp_path)
    monkeypatch.setattr(idiomas, "DIR_TRADUCCIONES", dir_trad)
    monkeypatch.setattr(idiomas, "_app_fuera", None)
    app = Flask(__name__)
    app.secret_key = "prueba"
    app.config["BABEL_DEFAULT_LOCALE"] = "es"
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = dir_trad
    Babel(app, locale_selector=idiomas.de_peticion)
    app.jinja_env.filters["traducir"] = idiomas.traducir
    return app


@pytest.fixture()
def proyectos_tmp(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    return tmp_path


def test_normalizar():
    assert idiomas.normalizar("en") == "en"
    assert idiomas.normalizar(" ES ") == "es"
    assert idiomas.normalizar("pt") is None
    assert idiomas.normalizar(None) is None


def test_usuario_sin_campo_usa_defecto_y_guardar():
    assert idiomas.de_usuario("admin") == "es"          # conftest: DEFECTO fijo en "es"
    idiomas.guardar_de_usuario("admin", "en")
    assert idiomas.de_usuario("admin") == "en"
    assert idiomas.de_usuario("no-existe") == "es"
    with pytest.raises(ValueError):
        idiomas.guardar_de_usuario("admin", "pt")


def test_defecto_manda_cuando_no_hay_campo(monkeypatch):
    monkeypatch.setattr(idiomas, "DEFECTO", "en")
    assert idiomas.de_usuario("admin") == "en"


def test_proyecto(proyectos_tmp):
    import proyectos
    assert idiomas.de_proyecto("acme") == "es"
    idiomas.guardar_de_proyecto("acme", "en")
    assert idiomas.de_proyecto("acme") == "en"
    assert proyectos.cargar("acme")["idioma"] == "en"
    with pytest.raises(ValueError):
        idiomas.guardar_de_proyecto("acme", "fr")


def test_de_peticion_usuario_luego_cookie_luego_defecto(app_prueba):
    with app_prueba.test_request_context("/"):
        assert idiomas.de_peticion() == "es"
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        assert idiomas.de_peticion() == "en"
    idiomas.guardar_de_usuario("admin", "es")
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        session["usuario"] = "admin"
        assert idiomas.de_peticion() == "es"       # la persona manda sobre la cookie


def test_plantilla_traduce_y_escapa_porcentaje(app_prueba):
    plantilla = "{{ _('Hola') }}|{{ _('Quedan %(n)s', n=3) }}|{{ _('100%% listo') }}|{{ ngettext('%(num)d pieza', '%(num)d piezas', 2) }}"
    with app_prueba.test_request_context("/"):
        assert render_template_string(plantilla) == "Hola|Quedan 3|100% listo|2 piezas"
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        assert render_template_string(plantilla) == "Hello|3 left|100% ready|2 pieces"


def test_traducir_valores_marcados(app_prueba):
    valor = idiomas.N_("Hola")
    assert valor == "Hola"
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        assert render_template_string("{{ v|traducir }}", v=valor) == "Hello"
        assert idiomas.traducir("") == "" and idiomas.traducir(None) is None


def test_en_idioma_dentro_de_una_peticion(app_prueba):
    with app_prueba.test_request_context("/"):
        assert gettext("Hola") == "Hola"
        with idiomas.en_idioma("en"):
            assert gettext("Hola") == "Hello"
            assert ngettext("%(num)d pieza", "%(num)d piezas", 1) == "1 piece"
        assert gettext("Hola") == "Hola"


def test_en_idioma_fuera_de_toda_app(app_prueba):
    # El worker no tiene app de Flask: en_idioma arma una mínima.
    with idiomas.en_idioma("en"):
        assert gettext("Hola") == "Hello"
    with idiomas.en_idioma("es"):
        assert gettext("Hola") == "Hola"


def test_gettext_sin_contexto_devuelve_el_espanol():
    assert gettext("Hola") == "Hola"
