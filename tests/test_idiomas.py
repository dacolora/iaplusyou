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


def test_de_peticion_sin_contexto_de_peticion_no_lanza(app_prueba):
    # Un app_context sin request (un gettext() suelto en el worker o en un
    # test) no tiene sesión ni cookies: de_peticion debe devolver DEFECTO en
    # vez de que Flask lance RuntimeError al leer session/request.
    with app_prueba.app_context():
        assert idiomas.de_peticion() == idiomas.DEFECTO
        assert gettext("Hola") == "Hola"


def test_nombre_para_claude():
    assert idiomas.nombre_para_claude("en") == "inglés"
    assert idiomas.nombre_para_claude("es") == "español"
    assert idiomas.nombre_para_claude("pt") == "español"      # inválido -> DEFECTO (fijo en "es" en tests)


def test_orden_idioma():
    en = idiomas.orden_idioma("en")
    assert "inglés" in en and "English" in en
    assert "español" in idiomas.orden_idioma("es")


def test_formatos_de_fecha_y_numero():
    import datetime
    d = datetime.date(2026, 9, 20)
    t = datetime.datetime(2026, 9, 25, 15, 4)
    assert idiomas.mes_largo(9, "es") == "septiembre" and idiomas.mes_largo(9, "en") == "September"
    assert idiomas.meses_cortos("es")[0] == "ene" and idiomas.meses_cortos("en")[8] == "Sep"
    assert len(idiomas.meses_cortos("es")) == 12
    assert idiomas.fecha_corta(d, idioma="es") == "20 sept" and idiomas.fecha_corta(d, idioma="en") == "20 Sep"
    assert idiomas.fecha_corta(t, con_hora=True, idioma="es") == "25 sept · 15:04"
    assert idiomas.fecha_corta(t, con_hora=True, idioma="en") == "25 Sep · 15:04"
    assert idiomas.dia_mes(d, "es") == "20/09" and idiomas.dia_mes(d, "en") == "09/20"
    assert idiomas.numero(1250000, idioma="es") == "1.250.000" and idiomas.numero(1250000, idioma="en") == "1,250,000"
    assert idiomas.numero(4000, idioma="es") == "4.000"
    assert idiomas.numero(12.5, 2, idioma="es") == "12,50" and idiomas.numero(12.5, 2, idioma="en") == "12.50"
    assert idiomas.separador_decimal("es") == "," and idiomas.separador_decimal("en") == "."


def test_numero_redondea_igual_que_main():
    """El redondeo half-even de Babel sobre el valor exacto difiere del de
    `f"{v:.2f}"` (lo que usaba main) en el último dígito para 12.345 (Babel:
    12,34) y 0.015 (Babel: 0,02) — `numero` pre-redondea con `format()` antes
    de pasarle el valor a Babel para que el español (y el inglés, con el
    mismo valor ya redondeado) coincida con main byte a byte (revisión final
    fase 4, hallazgo M2)."""
    import idiomas
    assert idiomas.numero(12.345, 2, idioma="es") == "12,35" and idiomas.numero(12.345, 2, idioma="en") == "12.35"
    assert idiomas.numero(0.015, 2, idioma="es") == "0,01" and idiomas.numero(0.015, 2, idioma="en") == "0.01"


def test_activo_sigue_al_contexto(app_prueba):
    assert idiomas.activo() == "es"                      # sin contexto: DEFECTO (fijo en "es" en tests)
    with idiomas.en_idioma("en"):
        assert idiomas.activo() == "en"
        assert idiomas.mes_largo(1) == "January"          # sin idioma explícito: el del contexto
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        assert idiomas.activo() == "en"
