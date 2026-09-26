# Fase 2 — Base del idioma (Flask-Babel) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Montar la traducción inglés/español con Flask-Babel (idioma por persona y por proyecto, selector, cookie antes del login, catálogo y guardias) y traducir el esqueleto de la app: barra lateral, encabezado, login/registro/recuperar/restablecer, portada, páginas legales, panel del admin, toda Configuración y los correos de la cuenta.

**Architecture:** `idiomas.py` es el único módulo que decide idioma (persona en `usuarios.json`, proyecto en `proyecto.json`, cookie antes del login) y le da a Flask-Babel el `locale_selector`. El texto en español es el `msgid`; el inglés vive en `translations/en/LC_MESSAGES/messages.po` y su `.mo` compilado va en git. `catalogo_i18n.py` extrae, actualiza y compila con la API de Babel, y lo usan tanto las personas como los tests. Tres guardias: catálogo completo y `.mo` al día; plantillas traducidas sin texto en español fuera de `_()` (análisis estático, todas las ramas); pantallas pedidas en inglés sin español visible (render real, incluye textos que vienen de Python).

**Tech Stack:** Flask 3.1, Flask-Babel 4 (Babel), Jinja2 3.1 (extensión i18n, gettext "newstyle"), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B1, §B2, §B3, §B8 correos de cuenta, §B10, §Fases fase 2, §Pruebas).

## Global Constraints

- `idiomas.DEFECTO = "es"` e `idiomas.ACTIVO_PARA_TODOS = False` durante toda esta fase: **para los clientes nada cambia**. El selector y el enlace «English · Español» antes del login solo aparecen para el admin; la ruta `cfg_idioma` rechaza (403) a un cliente mientras la bandera esté apagada.
- **El español que se ve no cambia ni una letra.** Envolver un texto nunca cambia su versión en español; los ~160 archivos de tests actuales (que comparan español) pasan sin tocarlos.
- Plantillas: `{{ _('texto') }}`; variables `{{ _('Quedan %(n)s piezas', n=total) }}`; plurales `{{ ngettext('%(num)d pieza', '%(num)d piezas', n) }}`; **todo `%` literal se escribe `%%`** (Jinja "newstyle" siempre aplica `%` al texto, haya variables o no; en el `msgstr` también va `%%`); dentro de `<script>`: `{{ _('texto')|tojson }}`; las etiquetas HTML de una frase van dentro del `msgid` (la frase entera, nunca partida); **prohibido `{% set _ = … %}`**.
- Python: `from flask_babel import gettext, ngettext` — **nunca `gettext as _`** (`dashboard.py` y otros usan `_` como variable descartable dentro de funciones: `pid, _, pais = …`). Texto con variables: `gettext("Proyecto «%(nombre)s» creado.", nombre=nombre)` (en Python `%` solo se aplica si hay variables).
- Constantes de módulo que se muestran (diccionarios de nombres, notas de modelos, nombres de países): se marcan con `N_("texto")` (identidad, de `idiomas`) y se traducen donde se muestran: en plantillas `{{ valor|traducir }}`, en Python `gettext(valor)`. Nunca `lazy_gettext` (un `LazyString` rompe `tojson`/JSON).
- Traducción: glosario `docs/i18n/glosario.md` (Task 1). Tuteo → "you"; mayúscula solo al inicio (como el español); emojis, `·`, números y marcadores `%(x)s` y etiquetas HTML intactos; comillas « » → “ ”.
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar` (extrae y suma al `.po`), `… pendientes` (lista sin inglés), `… compilar` (`.po` → `.mo`). Tests: `venv/bin/python3 -m pytest -q`.
- El ajuste `idioma_prompt` del director NO se toca en esta fase (se une al idioma del proyecto en la fase 3, con Crear): esta fase no cambia nada de lo que genera Claude.

## File Structure

- Create: `idiomas.py` — constantes (`IDIOMAS`, `DEFECTO`, `ACTIVO_PARA_TODOS`, `COOKIE`, `NOMBRES`, `DIR_TRADUCCIONES`), `normalizar`, `de_usuario`/`guardar_de_usuario`, `de_proyecto`/`guardar_de_proyecto`, `de_peticion` (locale selector), `traducir` (filtro), `N_`, `en_idioma` (context manager).
- Create: `catalogo_i18n.py` — `archivos_py`, `archivos_html`, `extraer`, `actualizar`, `pendientes`, `compilar`, `mo_al_dia`, CLI.
- Create: `translations/en/LC_MESSAGES/messages.po` y `messages.mo`.
- Create: `docs/i18n/glosario.md`.
- Create: `tests/i18n_util.py` — `espanol_visible(html, ids=None)`, `espanol_en_plantilla(ruta)`.
- Create: `tests/test_idiomas.py`, `tests/test_i18n_catalogo.py`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_rutas_idioma.py`.
- Modify: `requirements.txt`, `tests/conftest.py`, `dashboard.py` (Babel, context processor, rutas `cfg_idioma`/`cambiar_idioma`, registro, textos de rutas), `usuarios.py` (`idioma` actualizable; mensajes), `cuentas.py` (correos traducidos en el idioma de la persona), `templates/base.html`, `templates/_sidebar.html`, `templates/login.html`, `templates/recuperar.html`, `templates/restablecer.html`, `templates/index.html`, `templates/legal.html`, `templates/panel.html`, `templates/_tab_settings.html`, `templates/_llave_tarjeta.html`, `templates/_meta_conectar.html`, `templates/_meta_elegir_forma.html`, `templates/_meta_agencia_cliente.html`, `templates/_meta_propia_guia.html`, `templates/_tab_creativeflowplus.html` (solo el `{% set _ %}`), `static/style.css` (una regla para los enlaces de idioma), `CLAUDE.md`.

---

### Task 1: Flask-Babel, `idiomas.py`, catálogo y guardias de base

**Files:**
- Create: `idiomas.py`, `catalogo_i18n.py`, `docs/i18n/glosario.md`, `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`, `tests/test_idiomas.py`, `tests/test_i18n_catalogo.py`
- Modify: `requirements.txt`, `tests/conftest.py`, `dashboard.py:116-140` (tras `app = Flask(__name__)`), `usuarios.py:46` y `usuarios.py:198-228`, `templates/_tab_creativeflowplus.html` (los `{% set _ = … %}`), `CLAUDE.md`

**Interfaces:**
- Consumes: `usuarios.obtener`, `usuarios.actualizar`, `proyectos.cargar`, `proyectos._path`, `_json_store.guardar`.
- Produces:
  - `idiomas.IDIOMAS: tuple[str, ...] = ("en", "es")`, `idiomas.DEFECTO: str = "es"`, `idiomas.ACTIVO_PARA_TODOS: bool = False`, `idiomas.COOKIE = "idioma"`, `idiomas.NOMBRES = {"en": "English", "es": "Español"}`, `idiomas.DIR_TRADUCCIONES: str` (ruta absoluta a `translations/`).
  - `idiomas.normalizar(valor) -> str | None`; `idiomas.de_usuario(usuario) -> str`; `idiomas.guardar_de_usuario(usuario, idioma) -> None` (ValueError si no es válido); `idiomas.de_proyecto(cliente) -> str`; `idiomas.guardar_de_proyecto(cliente, idioma) -> None`; `idiomas.de_peticion() -> str`; `idiomas.traducir(texto) -> str`; `idiomas.N_(texto) -> str`; `idiomas.en_idioma(idioma)` (context manager).
  - `catalogo_i18n.extraer() -> babel.messages.catalog.Catalog`; `actualizar() -> None`; `pendientes() -> list[str]`; `compilar() -> None`; `mo_al_dia() -> bool`.
  - En `dashboard`: Babel inicializado con `locale_selector=idiomas.de_peticion`; filtro Jinja `traducir`; `gettext`/`ngettext` importados de `flask_babel`.
  - Fixture autouse en `tests/conftest.py` que fija `idiomas.DEFECTO = "es"` e `idiomas.ACTIVO_PARA_TODOS = False`.

- [ ] **Step 1: Dependencia**

Agregar a `requirements.txt` (debajo de `Flask`): `Flask-Babel>=4,<5`. Correr `venv/bin/pip install -r requirements.txt` y `venv/bin/python3 -c "import flask_babel, babel; print(flask_babel.__version__, babel.__version__)"`.

- [ ] **Step 2: Tests de `idiomas` (fallan)**

Crear `tests/test_idiomas.py`:

```python
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
```

- [ ] **Step 3: Correrlos (fallan)**

Run: `venv/bin/python3 -m pytest tests/test_idiomas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'idiomas'`.

- [ ] **Step 4: `idiomas.py`**

```python
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
```

- [ ] **Step 5: `usuarios.actualizar` acepta `idioma`**

En `usuarios.py`, `CAMPOS_ACTUALIZABLES` pasa a `("correo", "correo_verificado", "session_version", "idioma")`, el docstring del módulo suma la línea `- "idioma": "en" | "es", o ausente (= idiomas.DEFECTO; lo valida idiomas.guardar_de_usuario).`, y en `actualizar`, antes de `guardar(data)`:

```python
    if "idioma" in campos:
        entry["idioma"] = campos.pop("idioma")
```

(`_completar` NO rellena `idioma`: sin campo = `idiomas.DEFECTO`.)

- [ ] **Step 6: Fixture de tests en español**

Al final de `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def idioma_de_tests(monkeypatch):
    """Los tests existentes comparan textos en español: el idioma por defecto
    queda fijo en "es" aunque idiomas.DEFECTO cambie a "en" (fase 6). Un test
    de inglés lo pide explícitamente (usuario con idioma "en" o cookie)."""
    import idiomas
    monkeypatch.setattr(idiomas, "DEFECTO", "es")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", False)
```

- [ ] **Step 7: Correr `tests/test_idiomas.py`**

Run: `venv/bin/python3 -m pytest tests/test_idiomas.py -q`
Expected: PASS. Si `test_en_idioma_fuera_de_toda_app` o `test_gettext_sin_contexto_devuelve_el_espanol` fallan por cómo Flask-Babel 4 maneja el contexto, ajustar `en_idioma` (no el test): el comportamiento pedido es el del test.

- [ ] **Step 8: Babel en `dashboard.py`**

Tras `app = Flask(__name__)` (línea ~116) y antes de `@app.url_defaults`:

```python
# Idioma (spec 2026-09-26-idioma-y-modo-oscuro §B1): el español es la fuente;
# el inglés sale de translations/ (catalogo_i18n.py). idiomas.de_peticion elige.
app.config["BABEL_DEFAULT_LOCALE"] = "es"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = idiomas.DIR_TRADUCCIONES
Babel(app, locale_selector=idiomas.de_peticion)
app.jinja_env.filters["traducir"] = idiomas.traducir
```

e importar arriba: `from flask_babel import Babel, gettext, ngettext` (junto a los imports de flask) e `import idiomas` (junto a `import usuarios`).

- [ ] **Step 9: `catalogo_i18n.py`**

```python
"""Catálogo de traducciones (Flask-Babel; spec 2026-09-26-idioma-y-modo-oscuro §B1).

    venv/bin/python3 catalogo_i18n.py actualizar   # extrae y suma los textos nuevos al .po
    venv/bin/python3 catalogo_i18n.py pendientes   # lista los que no tienen inglés
    venv/bin/python3 catalogo_i18n.py compilar     # .po -> .mo (el .mo va en git)

El msgid es el texto en español tal como está en el código; el msgstr, el
inglés (docs/i18n/glosario.md). Solo recorre archivos de la app: los .py de la
raíz, los paquetes de PAQUETES y templates/ (nunca venv/, tests/, migrations/).
Los tests (tests/test_i18n_catalogo.py) usan estas mismas funciones."""
import glob
import io
import os
import sys

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_file
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

import idiomas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PO = os.path.join(idiomas.DIR_TRADUCCIONES, "en", "LC_MESSAGES", "messages.po")
MO = os.path.join(idiomas.DIR_TRADUCCIONES, "en", "LC_MESSAGES", "messages.mo")
PAQUETES = ("auth", "conectores", "doctrina", "final_edition", "guiones", "meta_ads", "nicho",
            "providers", "referentes", "sprints", "storage", "tareas", "uploaders")
PALABRAS = {"_": None, "gettext": None, "ngettext": (1, 2), "N_": None}


def archivos_py():
    rutas = glob.glob(os.path.join(BASE_DIR, "*.py"))
    for paquete in PAQUETES:
        rutas += glob.glob(os.path.join(BASE_DIR, paquete, "**", "*.py"), recursive=True)
    return sorted(r for r in rutas if os.path.basename(r) != "catalogo_i18n.py")


def archivos_html():
    return sorted(glob.glob(os.path.join(BASE_DIR, "templates", "**", "*.html"), recursive=True))


def extraer():
    """Catalog con cada texto marcado en el código (sin traducir)."""
    cat = Catalog(locale="en", project="Creatv", charset="utf-8")
    fuentes = [("python", r) for r in archivos_py()]
    fuentes += [("jinja2.ext:babel_extract", r) for r in archivos_html()]
    for metodo, ruta in fuentes:
        for linea, mensaje, _comentarios, contexto in extract_from_file(metodo, ruta, keywords=PALABRAS):
            cat.add(mensaje, None, [(os.path.relpath(ruta, BASE_DIR), linea)], context=contexto)
    return cat


def _leer_po():
    if not os.path.exists(PO):
        return None
    with open(PO, "rb") as f:
        return read_po(f, locale="en")


def actualizar():
    plantilla = extraer()
    cat = _leer_po()
    if cat is None:
        cat = plantilla
    else:
        cat.update(plantilla, no_fuzzy_matching=True)
    os.makedirs(os.path.dirname(PO), exist_ok=True)
    with open(PO, "wb") as f:
        write_po(f, cat, width=0, no_location=True, sort_output=True, ignore_obsolete=True, include_previous=False)


def _vacio(cadena):
    if isinstance(cadena, (tuple, list)):
        return not cadena or not all(cadena)
    return not cadena


def pendientes():
    """msgid (singular) de cada texto marcado sin inglés en el .po (o fuzzy)."""
    cat = _leer_po()
    faltan = []
    for m in extraer():
        if not m.id:
            continue
        t = cat.get(m.id, context=m.context) if cat is not None else None
        if t is None or t.fuzzy or _vacio(t.string):
            faltan.append(m.id if isinstance(m.id, str) else m.id[0])
    return faltan


def _mo_bytes():
    salida = io.BytesIO()
    write_mo(salida, _leer_po() or Catalog(locale="en"), use_fuzzy=False)
    return salida.getvalue()


def compilar():
    with open(MO, "wb") as f:
        f.write(_mo_bytes())


def mo_al_dia():
    if not os.path.exists(MO):
        return False
    with open(MO, "rb") as f:
        return f.read() == _mo_bytes()


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "actualizar":
        actualizar()
        print(f"{PO} actualizado; faltan {len(pendientes())} por traducir.")
    elif orden == "pendientes":
        for texto in pendientes():
            print(texto)
    elif orden == "compilar":
        compilar()
        print(f"{MO} compilado.")
    else:
        print(__doc__)
        sys.exit(1)
```

Crear el catálogo vacío: `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py compilar` (genera `messages.po` con solo la cabecera y su `.mo`). Si `extract_from_file`, `Catalog.update(no_fuzzy_matching=)` o `write_po(no_location=)` no aceptan esos argumentos en la versión instalada de Babel, ajustar la llamada a la firma instalada manteniendo el mismo efecto.

- [ ] **Step 10: Guardias del catálogo (y quitar `{% set _ %}`)**

Crear `tests/test_i18n_catalogo.py`:

```python
"""Catálogo de traducciones (spec 2026-09-26 §B1, §Pruebas): todo texto marcado
tiene su inglés, el .mo versionado está al día con el .po, y nada pisa `_`."""
import glob
import os
import re

from babel.messages.pofile import read_po

import catalogo_i18n

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCADOR = re.compile(r"%\((\w+)\)[sd]")
PORCENTAJE_SUELTO = re.compile(r"%(?!%|\(\w+\)[sd])")


def _po():
    with open(catalogo_i18n.PO, "rb") as f:
        return read_po(f, locale="en")


def test_todo_texto_marcado_tiene_ingles():
    faltan = catalogo_i18n.pendientes()
    assert not faltan, ("Sin traducción (venv/bin/python3 catalogo_i18n.py actualizar, traducir en el .po "
                        "y compilar):\n" + "\n".join(faltan[:40]))


def test_mo_al_dia():
    assert catalogo_i18n.mo_al_dia(), "messages.mo viejo: venv/bin/python3 catalogo_i18n.py compilar"


def test_traducciones_conservan_marcadores():
    malos = []
    for m in _po():
        if not m.id or not m.string:
            continue
        ids = m.id if isinstance(m.id, tuple) else (m.id,)
        cadenas = m.string if isinstance(m.string, tuple) else (m.string,)
        esperados = set(MARCADOR.findall(" ".join(ids)))
        # Cada forma usa solo marcadores del español; la última (el plural, o
        # la única) los usa todos: «one piece» puede omitir %(num)d.
        if any(not set(MARCADOR.findall(c)) <= esperados for c in cadenas) \
                or set(MARCADOR.findall(cadenas[-1])) != esperados:
            malos.append(f"{ids[0]!r} -> {cadenas!r}")
    assert not malos, "Marcadores %(x)s distintos entre español e inglés:\n" + "\n".join(malos)


def test_porcentajes_escapados_en_plantillas():
    malos = []
    for ruta in catalogo_i18n.archivos_html():
        for m in re.finditer(r"""(?:\b_|\bngettext)\(\s*(['"])(.*?)(?<!\\)\1""", open(ruta, encoding="utf-8").read(), re.S):
            if PORCENTAJE_SUELTO.search(m.group(2)):
                malos.append(f"{os.path.relpath(ruta, RAIZ)}: {m.group(2)[:80]!r}")
    assert not malos, "Un % literal dentro de _() en una plantilla va como %%:\n" + "\n".join(malos)


def test_ninguna_plantilla_pisa_el_guion_bajo():
    malos = [os.path.relpath(r, RAIZ) for r in glob.glob(os.path.join(RAIZ, "templates", "**", "*.html"), recursive=True)
             if re.search(r"\{%-?\s*set\s+_\s*=", open(r, encoding="utf-8").read())]
    assert not malos, "{% set _ = … %} tapa la función de traducción _(): " + ", ".join(malos)


def test_python_no_importa_gettext_como_guion_bajo():
    malos = [os.path.relpath(r, RAIZ) for r in catalogo_i18n.archivos_py()
             if re.search(r"import\s+.*\bgettext\s+as\s+_\b", open(r, encoding="utf-8").read())]
    assert not malos, "Usa gettext/ngettext con su nombre (el _ se usa como variable descartable): " + ", ".join(malos)
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_catalogo.py -q`
Expected: FAIL solo `test_ninguna_plantilla_pisa_el_guion_bajo` (`_tab_creativeflowplus.html`). Arreglar: en `templates/_tab_creativeflowplus.html` cambiar cada `{% set _ = ` por `{% set _nada = ` (buscar con `grep -n "set _ =" templates/*.html`). Volver a correr: PASS.

- [ ] **Step 11: Glosario y CLAUDE.md**

Crear `docs/i18n/glosario.md` con: (1) la tabla de términos del spec §B10 tal cual; (2) las reglas de estilo de los Global Constraints de este plan (tuteo → "you", mayúscula inicial, emojis/`·`/marcadores/HTML intactos, « » → “ ”, `%%`); (3) "no se traduce": nombres de marca y de modelos (Creatv, Flow Plus, Wan, Kling, Seedance, Seedream, WaveSpeed, Meta, Shopify…), códigos (TOF/MOF/BOF), unidades (`s`, `US$`).

En `CLAUDE.md`, después del párrafo **UI base**, agregar:

```markdown
**Idioma** (`idiomas.py`, `catalogo_i18n.py`, spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md`):
Flask-Babel; el español es el msgid y el inglés vive en `translations/en/LC_MESSAGES/messages.po` (+ `.mo` en
git). **Todo texto nuevo que vea una persona pasa por el catálogo**: plantillas `{{ _('…') }}` (`%` literal =
`%%`, variables `%(x)s`, dentro de `<script>` con `|tojson`, nunca `{% set _ = %}`); Python
`gettext`/`ngettext` de `flask_babel` (nunca `as _`); constantes de módulo con `idiomas.N_` + `|traducir`.
Luego `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar`
(`tests/test_i18n_catalogo.py` falla si falta). Idioma de la persona en `usuarios.json`, del proyecto en
`proyecto.json`, cookie `idioma` antes del login; `idiomas.en_idioma(x)` para correos y worker.
`idiomas.DEFECTO`/`ACTIVO_PARA_TODOS` cambian al cerrar la fase 6; los tests fijan español (`conftest`).
```

- [ ] **Step 12: Suite completa y commit**

Run: `venv/bin/python3 -m pytest -q`
Expected: PASS.

```bash
git add requirements.txt idiomas.py catalogo_i18n.py translations/ docs/i18n/glosario.md tests/test_idiomas.py tests/test_i18n_catalogo.py tests/conftest.py dashboard.py usuarios.py templates/_tab_creativeflowplus.html CLAUDE.md
git commit -m "$(cat <<'EOF'
Idioma (1/6 de la fase 2): Flask-Babel, idiomas.py, catálogo y guardias

El español es el msgid; el inglés vive en translations/ (.mo en git).
idiomas.py decide el idioma (persona, proyecto, cookie) y catalogo_i18n.py
extrae/actualiza/compila. DEFECTO sigue en "es": nada cambia para nadie.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Guardias de plantillas y de pantallas

**Files:**
- Create: `tests/i18n_util.py`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: `idiomas.guardar_de_usuario`, `idiomas.COOKIE`, fixtures de `tests/conftest.py` (`base_temporal`, `usuarios_tmp`).
- Produces:
  - `tests.i18n_util.espanol_visible(html: str, ids: tuple[str, ...] | None = None) -> list[str]` — trozos de texto visible (nodos de texto y atributos `placeholder`/`title`/`aria-label`/`alt`/`value` de botones) con marcas de español, dentro de los elementos con esos `id` (o de toda la página).
  - `tests.i18n_util.espanol_en_plantilla(ruta: str) -> list[str]` — lo mismo sobre el FUENTE de una plantilla, quitando antes `{# #}`, `{% %}` y `{{ }}` (cubre todas las ramas), más los literales de texto dentro de `<script>`.
  - `tests/test_i18n_plantillas.py::PLANTILLAS_TRADUCIDAS: list[str]` y `tests/test_i18n_fugas.py` con sus fixtures `app_i18n`, `cliente_en`, `admin_en`, `publico_en` — las Tasks 4-6 (y las fases siguientes) SOLO agregan entradas.

- [ ] **Step 1: `tests/i18n_util.py`**

```python
"""Detección de español en HTML (spec 2026-09-26 §Pruebas). Heurística: acentos,
ñ, ¿ ¡ y palabras muy frecuentes del español que no existen sueltas en inglés.
EXCEPCIONES son palabras que pueden quedar a propósito (el nombre del idioma en
el selector bilingüe)."""
import re
from html.parser import HTMLParser

MARCAS = re.compile(
    r"[¿¡ñÑáéíóúÁÉÍÓÚ]"
    r"|\b(?:el|la|los|las|de|del|en|para|con|una|que|por|tu|tus|sin|está|aquí|más|también|nuevo|nueva|"
    r"guardar|entrar|cuenta|correo|contraseña|proyecto|usuario|conectar|todavía|ahora)\b",
    re.I)
EXCEPCIONES = ("Español", "Idioma")
VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ATRIBUTOS = ("placeholder", "title", "aria-label", "alt")


def _con_marca(texto):
    for palabra in EXCEPCIONES:
        texto = texto.replace(palabra, " ")
    return bool(MARCAS.search(texto))


class _Visible(HTMLParser):
    def __init__(self, ids=None):
        super().__init__(convert_charrefs=True)
        self.ids = set(ids or ())
        self.pila = []
        self.region = 0 if self.ids else 1
        self.oculto = 0
        self.trozos = []

    def handle_starttag(self, tag, attrs):
        a = {k: v for k, v in attrs if v is not None}
        abre = bool(self.ids) and a.get("id") in self.ids
        if tag not in VACIOS:
            self.pila.append((tag, abre))
            self.region += abre
            self.oculto += tag in ("script", "style", "template")
        if self.region and not self.oculto:
            self.trozos += [a[k] for k in ATRIBUTOS if a.get(k)]
            if tag in ("input", "button") and a.get("type") in ("submit", "button") and a.get("value"):
                self.trozos.append(a["value"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VACIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in [t for t, _abre in self.pila]:
            return
        while self.pila:
            t, abre = self.pila.pop()
            self.region -= abre
            self.oculto -= t in ("script", "style", "template")
            if t == tag:
                break

    def handle_data(self, data):
        if self.region and not self.oculto and data.strip():
            self.trozos.append(" ".join(data.split()))


def espanol_visible(html, ids=None):
    p = _Visible(ids)
    p.feed(html)
    if ids:
        assert p.region == 0 or p.trozos, f"no encontré los elementos {ids}"
    return [t for t in p.trozos if _con_marca(t)]


_LITERAL_JS = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`")


def espanol_en_plantilla(ruta):
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r"\{#.*?#\}", " ", src, flags=re.S)
    src = re.sub(r"\{%.*?%\}", " ", src, flags=re.S)
    src = re.sub(r"\{\{.*?\}\}", " ", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    hallazgos = espanol_visible(src)
    for bloque in re.findall(r"<script\b[^>]*>(.*?)</script>", src, flags=re.S | re.I):
        bloque = re.sub(r"/\*.*?\*/", " ", bloque, flags=re.S)
        bloque = re.sub(r"(?<![:'\"\\])//[^\n]*", " ", bloque)
        hallazgos += [lit for lit in _LITERAL_JS.findall(bloque) if _con_marca(lit)]
    return hallazgos
```

- [ ] **Step 2: `tests/test_i18n_plantillas.py` (lista vacía por ahora)**

```python
"""Plantillas ya traducidas (spec 2026-09-26 §Pruebas): en su FUENTE no queda
texto visible en español fuera de _() — en ninguna rama de un {% if %} — ni
literales en español dentro de <script>. Cada tarea que traduce una plantilla
la agrega a PLANTILLAS_TRADUCIDAS."""
import os

import pytest

from tests.i18n_util import espanol_en_plantilla

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_TRADUCIDAS = [
]


def test_la_deteccion_funciona(tmp_path):
    ruta = tmp_path / "x.html"
    ruta.write_text("<p>{{ _('Guardar') }}</p><p>Guardar cambios</p>"
                    "<script>var a = {{ _('Sí')|tojson }}; var b = '¿Seguro?'; // comentario en español</script>",
                    encoding="utf-8")
    assert espanol_en_plantilla(str(ruta)) == ["Guardar cambios", "'¿Seguro?'"]


@pytest.mark.parametrize("nombre", PLANTILLAS_TRADUCIDAS)
def test_plantilla_sin_espanol_suelto(nombre):
    hallazgos = espanol_en_plantilla(os.path.join(RAIZ, "templates", nombre))
    assert not hallazgos, f"{nombre}: texto en español fuera de _():\n" + "\n".join(hallazgos[:30])
```

- [ ] **Step 3: `tests/test_i18n_fugas.py` (fixtures + detección)**

```python
"""Pantallas en inglés sin español visible (spec 2026-09-26 §Pruebas). Render
real: atrapa también los textos que vienen de Python (flash, nombres de
constantes, tarjetas de llaves). Cada tarea que traduce una pantalla agrega su
test aquí."""
import pytest

import idiomas
from tests.i18n_util import espanol_visible

CLAVES = [
    "ANTHROPIC_API_KEY", "FAL_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL", "META_APP_ID", "META_APP_SECRET", "SMTP_HOST",
    "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL", "MELI_APP_ID", "MELI_SECRET", "ATRIA_API_KEY",
]


@pytest.fixture()
def app_i18n(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import dashboard
    import proyectos
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    for v in CLAVES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(dashboard.estado_mod, "listar_clientes", lambda: ["acme"])
    dashboard.app.config["TESTING"] = True
    return dashboard


def _cliente(dashboard, usuario, rol, cliente):
    idiomas.guardar_de_usuario(usuario, "en")
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


@pytest.fixture()
def admin_en(app_i18n):
    return _cliente(app_i18n, "admin", "admin", None)


@pytest.fixture()
def cliente_en(app_i18n):
    return _cliente(app_i18n, "user_acme", "cliente", "acme")


@pytest.fixture()
def publico_en(app_i18n):
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "en")
    return c


def html_de(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def test_la_deteccion_funciona():
    html = '<div id="a"><p>Hello</p><input placeholder="Escribe aquí"></div><div id="b"><p>Guardar</p></div>'
    assert espanol_visible(html, ("a",)) == ["Escribe aquí"]
    assert espanol_visible(html) == ["Escribe aquí", "Guardar"]
```

- [ ] **Step 4: Correr y commit**

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q`
Expected: PASS (2 tests de detección; la parametrización vacía no genera casos).

```bash
git add tests/i18n_util.py tests/test_i18n_plantillas.py tests/test_i18n_fugas.py
git commit -m "$(cat <<'EOF'
Idioma (2/6 de la fase 2): guardias de español en plantillas y en pantallas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Selector de idioma, cookie antes del login y registro

**Files:**
- Create: `tests/test_rutas_idioma.py`
- Modify: `dashboard.py` (context processor nuevo junto a `_cuenta_en_plantillas` ~l.311; `ENDPOINTS_SIN_GUARD_SESION` ~l.243; rutas nuevas junto a las de cuenta ~l.1111; `crear_proyecto` ~l.935), `templates/_tab_settings.html` (apartado `cuenta` ~l.523 y `generacion` ~l.424), `templates/base.html` (`<html lang>` l.2 y enlaces de idioma en el `<header>` l.282), `static/style.css` (bloque «Base visual común», al final)

**Interfaces:**
- Consumes: todo lo de la Task 1 (`idiomas.*`, `gettext`).
- Produces: endpoints `cfg_idioma` (`POST /cliente/<cliente>/cfg_idioma`, campos `idioma`, `alcance` ∈ `cuenta|proyecto`) y `cambiar_idioma` (`GET /idioma/<codigo>?next=`); variables de plantilla `idioma_ui`, `idioma_proyecto` (solo con `<cliente>` en la URL), `idiomas_nombres`, `idioma_selector_visible`, `idioma_enlaces_publicos`; `<header id="barra-superior">` en `base.html` (lo usa la Task 4).

- [ ] **Step 1: Tests (fallan)**

Crear `tests/test_rutas_idioma.py`:

```python
"""Selector de idioma (spec 2026-09-26 §B3): cfg_idioma (cuenta / proyecto),
/idioma/<codigo> con cookie, registro con el idioma de la cookie, y la bandera
ACTIVO_PARA_TODOS que esconde todo a los clientes durante las fases 2-5."""
import pytest

import idiomas
from tests.test_i18n_fugas import app_i18n  # noqa: F401  (fixture)

ORIGEN = {"Sec-Fetch-Site": "same-origin"}     # dashboard._mismo_origen mira Sec-Fetch-Site


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


def test_admin_cambia_su_idioma_sin_tocar_el_proyecto(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert r.status_code == 302
    assert idiomas.de_usuario("admin") == "en"
    assert idiomas.de_proyecto("acme") == "es"


def test_admin_cambia_el_idioma_del_proyecto(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "proyecto"}, headers=ORIGEN)
    assert idiomas.de_proyecto("acme") == "en"
    assert idiomas.de_usuario("admin") == "es"


def test_cliente_bloqueado_mientras_no_este_activo(app_i18n):
    c = _sesion(app_i18n, "user_acme", "cliente", "acme")
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert r.status_code == 403
    assert idiomas.de_usuario("user_acme") == "es"


def test_cliente_activo_cambia_su_idioma_y_el_de_su_proyecto(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    c = _sesion(app_i18n, "user_acme", "cliente", "acme")
    c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"}, headers=ORIGEN)
    assert idiomas.de_usuario("user_acme") == "en" and idiomas.de_proyecto("acme") == "en"
    r = c.post("/cliente/acme/cfg_idioma", data={"idioma": "es", "alcance": "proyecto"}, headers=ORIGEN)
    assert r.status_code == 400                     # un cliente no elige el alcance "proyecto"


def test_idioma_invalido_y_origen_ajeno(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    assert c.post("/cliente/acme/cfg_idioma", data={"idioma": "pt", "alcance": "cuenta"}, headers=ORIGEN).status_code == 400
    assert c.post("/cliente/acme/cfg_idioma", data={"idioma": "en", "alcance": "cuenta"},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_selector_solo_admin_mientras_no_este_activo(app_i18n):
    html_admin = _sesion(app_i18n, "admin", "admin", None).get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' in html_admin and 'id="config-idioma-proyecto"' in html_admin
    html_cli = _sesion(app_i18n, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' not in html_cli and 'id="config-idioma-proyecto"' not in html_cli


def test_selector_del_cliente_cuando_esta_activo(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    html_cli = _sesion(app_i18n, "user_acme", "cliente", "acme").get("/cliente/acme").get_data(as_text=True)
    assert 'id="config-idioma"' in html_cli and 'id="config-idioma-proyecto"' not in html_cli


def test_html_lang_sigue_al_idioma(app_i18n):
    c = _sesion(app_i18n, "admin", "admin", None)
    assert '<html lang="es">' in c.get("/cliente/acme").get_data(as_text=True)
    idiomas.guardar_de_usuario("admin", "en")
    assert '<html lang="en">' in c.get("/cliente/acme").get_data(as_text=True)


def test_cookie_de_idioma_y_next_seguro(app_i18n):
    c = app_i18n.app.test_client()
    r = c.get("/idioma/en?next=/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert "idioma=en" in r.headers["Set-Cookie"]
    for malo in ("https://malo.example/x", "//malo.example/x", "/\\malo.example"):
        r = c.get("/idioma/es", query_string={"next": malo})
        assert r.headers["Location"].endswith("/"), malo
    assert c.get("/idioma/pt").status_code == 404


def test_enlaces_publicos_solo_si_esta_activo(app_i18n, monkeypatch):
    c = app_i18n.app.test_client()
    assert 'class="idioma-enlaces"' not in c.get("/login").get_data(as_text=True)
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    assert 'class="idioma-enlaces"' in c.get("/login").get_data(as_text=True)


@pytest.mark.parametrize("activo, esperado", [(False, "es"), (True, "en")])
def test_registro_toma_la_cookie_solo_si_esta_activo(app_i18n, monkeypatch, activo, esperado):
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", activo)
    monkeypatch.setattr(app_i18n, "BASE_DIR", str(app_i18n.proyectos.BASE_DIR))
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "en")
    r = c.post("/proyectos/nuevo", data={"nombre": "Nueva Marca", "usuario": "nueva", "correo": "nueva@prueba.local",
                                          "password": "una-clave-larga-123"})
    assert r.status_code == 302
    assert idiomas.de_usuario("nueva") == esperado
    assert idiomas.de_proyecto("nueva_marca") == esperado
```

Run: `venv/bin/python3 -m pytest tests/test_rutas_idioma.py -q`
Expected: FAIL (404 en `/cliente/acme/cfg_idioma` y `/idioma/en`, sin `id="config-idioma"`, `lang` fijo en "es").

- [ ] **Step 2: Context processor**

En `dashboard.py`, debajo de `_cuenta_en_plantillas`:

```python
@app.context_processor
def _idioma_en_plantillas():
    """Idioma para las plantillas (spec 2026-09-26 §B3): `idioma_ui` (el de la
    petición, para <html lang> y el selector), `idioma_proyecto` en las páginas
    de un proyecto, y si se muestran el selector de Configuración y los enlaces
    «English · Español» antes del login (fases 2-5: solo el admin)."""
    sesion = _sesion()
    cliente = request.view_args.get("cliente") if request.view_args else None
    datos = {
        "idioma_ui": str(get_locale() or idiomas.DEFECTO),
        "idiomas_nombres": idiomas.NOMBRES,
        "idioma_selector_visible": bool(sesion) and (idiomas.ACTIVO_PARA_TODOS or sesion["rol"] == "admin"),
        "idioma_enlaces_publicos": idiomas.ACTIVO_PARA_TODOS and not sesion,
    }
    if cliente:
        datos["idioma_proyecto"] = idiomas.de_proyecto(cliente)
    return datos
```

(importar `get_locale` de `flask_babel` junto a `Babel, gettext, ngettext`).

- [ ] **Step 3: Rutas `cfg_idioma` y `cambiar_idioma`**

Agregar `"cambiar_idioma"` a `ENDPOINTS_SIN_GUARD_SESION`. Junto a `cuenta_password`:

```python
@app.route("/cliente/<cliente>/cfg_idioma", methods=["POST"])
def cfg_idioma(cliente):
    """Selector de idioma (spec 2026-09-26 §B3). alcance=cuenta: el idioma de
    quien está en sesión y, si es un cliente, también el de su proyecto (para él
    son una sola cosa). alcance=proyecto: solo admin. Mientras
    idiomas.ACTIVO_PARA_TODOS sea False, solo el admin puede usarlo."""
    if not _mismo_origen():
        abort(403)
    sesion = _sesion()
    es_admin = sesion["rol"] == "admin"
    if not es_admin and not idiomas.ACTIVO_PARA_TODOS:
        abort(403)
    idioma = idiomas.normalizar(request.form.get("idioma"))
    alcance = request.form.get("alcance") or "cuenta"
    if idioma is None or alcance not in ("cuenta", "proyecto") or (alcance == "proyecto" and not es_admin):
        abort(400)
    if alcance == "proyecto":
        idiomas.guardar_de_proyecto(cliente, idioma)
        flash(gettext("Idioma del proyecto guardado."), "ok")
    else:
        idiomas.guardar_de_usuario(sesion["usuario"], idioma)
        if not es_admin:
            idiomas.guardar_de_proyecto(cliente, idioma)
        with idiomas.en_idioma(idioma):
            flash(gettext("Idioma guardado."), "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


@app.route("/idioma/<codigo>")
def cambiar_idioma(codigo):
    """Enlaces «English · Español» antes del login: guarda la cookie y vuelve a
    `next` solo si es una ruta de este sitio (nunca a otro dominio)."""
    idioma = idiomas.normalizar(codigo)
    if idioma is None:
        abort(404)
    destino = request.args.get("next") or ""
    if not destino.startswith("/") or destino.startswith("//") or "\\" in destino:
        destino = url_for("index")
    resp = redirect(destino)
    resp.set_cookie(idiomas.COOKIE, idioma, max_age=365 * 24 * 3600, samesite="Lax", httponly=True,
                    secure=bool(app.config.get("SESSION_COOKIE_SECURE")))
    return resp
```

- [ ] **Step 4: Registro con el idioma de la cookie**

En `crear_proyecto`, justo después de `proyectos.guardar_nombre(cid, nombre)`:

```python
    if idiomas.ACTIVO_PARA_TODOS:
        elegido = idiomas.normalizar(request.cookies.get(idiomas.COOKIE)) or idiomas.DEFECTO
        idiomas.guardar_de_usuario(usuario, elegido)
        idiomas.guardar_de_proyecto(cid, elegido)
```

- [ ] **Step 5: Plantillas**

`templates/base.html`: línea 2 → `<html lang="{{ idioma_ui }}">`; el `<header>` de la línea 282 → `<header id="barra-superior">`; dentro de ese `<header>`, al final:

```html
    {% if idioma_enlaces_publicos %}
    <nav class="idioma-enlaces" aria-label="Language / Idioma">
      <a href="{{ url_for('cambiar_idioma', codigo='en', next=request.path) }}">English</a> ·
      <a href="{{ url_for('cambiar_idioma', codigo='es', next=request.path) }}">Español</a>
    </nav>
    {% endif %}
```

Hacer lo mismo (`lang` y enlaces) en cualquier plantilla de las rutas públicas que NO extienda `base.html` (revisar con `grep -L "extends" templates/login.html templates/index.html templates/recuperar.html templates/restablecer.html templates/legal.html`).

`templates/_tab_settings.html`, al principio del apartado `cuenta` (después de `<h2 id="config-cuenta">…</h2>`):

```html
{% if idioma_selector_visible %}
<form method="post" action="{{ url_for('cfg_idioma', cliente=cliente) }}" id="config-idioma" class="fila-campos-idea">
  <input type="hidden" name="alcance" value="cuenta">
  <div>
    <label class="campo-label" for="idioma-cuenta">Language / Idioma</label>
    <select id="idioma-cuenta" name="idioma">
      {% for codigo, nombre in idiomas_nombres.items() %}<option value="{{ codigo }}" {% if codigo == idioma_ui %}selected{% endif %}>{{ nombre }}</option>{% endfor %}
    </select>
    <button class="btn-guardar btn-sm" type="submit">{{ _('Guardar idioma') }}</button>
    <p class="vacio" style="padding:0;font-size:.76rem;">{% if es_admin %}{{ _('Cambia solo tu idioma. El del proyecto está en Generación.') }}{% else %}{{ _('Cambia el idioma de las pantallas y de todo lo que se genera en tu proyecto.') }}{% endif %}</p>
  </div>
</form>
{% endif %}
```

En el apartado `generacion`, **después** del `</form>` de «Guardar modelos de FlowPlus» (fuera de ese form):

```html
{% if es_admin %}
<form method="post" action="{{ url_for('cfg_idioma', cliente=cliente) }}" id="config-idioma-proyecto" class="fila-campos-idea" style="margin-top:.8rem;">
  <input type="hidden" name="alcance" value="proyecto">
  <div>
    <label class="campo-label" for="idioma-proyecto">{{ _('Idioma del proyecto') }}</label>
    <select id="idioma-proyecto" name="idioma">
      {% for codigo, nombre in idiomas_nombres.items() %}<option value="{{ codigo }}" {% if codigo == idioma_proyecto %}selected{% endif %}>{{ nombre }}</option>{% endfor %}
    </select>
    <button class="btn-guardar btn-sm" type="submit">{{ _('Guardar') }}</button>
    <p class="vacio" style="padding:0;font-size:.76rem;">{{ _('Lo que escribe la IA y los anuncios de este proyecto salen en este idioma.') }}</p>
  </div>
</form>
{% endif %}
```

`static/style.css`, al final del bloque «Base visual común»:

```css
.idioma-enlaces { margin-left: auto; font-size: .8rem; color: var(--muted); white-space: nowrap; }
.idioma-enlaces a { color: var(--accent-texto); text-decoration: none; }
```

- [ ] **Step 6: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar` y traducir en `translations/en/LC_MESSAGES/messages.po` los 7 textos nuevos:

| msgid | msgstr |
|---|---|
| Idioma del proyecto guardado. | Project language saved. |
| Idioma guardado. | Language saved. |
| Guardar idioma | Save language |
| Cambia solo tu idioma. El del proyecto está en Generación. | Changes only your language. The project's is under Generation. |
| Cambia el idioma de las pantallas y de todo lo que se genera en tu proyecto. | Changes the language of the screens and of everything generated in your project. |
| Idioma del proyecto | Project language |
| Guardar | Save |
| Lo que escribe la IA y los anuncios de este proyecto salen en este idioma. | What the AI writes and this project's ads come out in this language. |

Luego `venv/bin/python3 catalogo_i18n.py compilar`.

- [ ] **Step 7: Tests y commit**

Run: `venv/bin/python3 -m pytest tests/test_rutas_idioma.py tests/test_i18n_catalogo.py tests/test_modo_oscuro.py -q` → PASS. Luego `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add dashboard.py templates/base.html templates/_tab_settings.html static/style.css translations/ tests/test_rutas_idioma.py
git commit -m "$(cat <<'EOF'
Idioma (3/6 de la fase 2): selector en Configuración, cookie antes del login y registro

cfg_idioma (cuenta / proyecto), /idioma/<codigo> con next seguro, <html lang>
según el idioma. Mientras ACTIVO_PARA_TODOS esté apagado solo el admin lo ve.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Esqueleto, páginas públicas, panel y correos de la cuenta

**Files:**
- Modify: `templates/base.html` (textos y JS), `templates/_sidebar.html`, `templates/login.html`, `templates/recuperar.html`, `templates/restablecer.html`, `templates/index.html`, `templates/legal.html`, `templates/panel.html`; `dashboard.py` (textos de `requiere_admin`, `_verificar_sesion`, `_guard_por_cliente`, `index`, `privacidad`, `terminos`, `eliminar_datos`, `panel`, `login`, `logout`, `crear_proyecto`, `verificar_correo`, `reenviar_verificacion`, `recuperar`, `restablecer`, `cuenta_correo`, `cuenta_password`, la ruta de `/admin/usuarios/<usuario>/verificar`, y los HTML legales `_PRIVACIDAD_HTML`/`_TERMINOS_HTML`); `usuarios.py` (mensajes de `validar_*`, `crear`, `actualizar`, `cambiar_password`); `cuentas.py` (`_horas_texto`, `_armar_correo`, `_enviar`); `translations/`; `tests/test_i18n_plantillas.py`; `tests/test_i18n_fugas.py`
- Test: `tests/test_cuentas_idioma.py` (nuevo)

**Interfaces:**
- Consumes: Tasks 1-3 (`gettext`, `ngettext`, `idiomas.en_idioma`, `idiomas.de_usuario`, fixtures `admin_en`/`publico_en`, `espanol_visible`, `PLANTILLAS_TRADUCIDAS`).
- Produces: `cuentas._armar_correo(tipo, usuario, enlace)` traducido según el locale activo y `cuentas._enviar` que lo arma dentro de `idiomas.en_idioma(idiomas.de_usuario(usuario))`; `legal.html` recibe `cuerpo` en el idioma de la petición.

- [ ] **Step 1: Registrar las guardias (fallan)**

En `tests/test_i18n_plantillas.py`, `PLANTILLAS_TRADUCIDAS` pasa a:

```python
PLANTILLAS_TRADUCIDAS = [
    "base.html", "_sidebar.html", "login.html", "recuperar.html", "restablecer.html",
    "index.html", "legal.html", "panel.html",
]
```

Al final de `tests/test_i18n_fugas.py`:

```python
@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_publicas_en_ingles(publico_en, url):
    fugas = espanol_visible(html_de(publico_en, url))
    assert not fugas, f"{url}: {fugas[:15]}"


def test_restablecer_en_ingles(publico_en):
    import cuentas
    token = cuentas.emitir("restablecer", "admin", "admin@prueba.local")
    fugas = espanol_visible(html_de(publico_en, f"/restablecer/{token}"))
    assert not fugas, fugas[:15]


def test_panel_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/panel"))
    assert not fugas, fugas[:15]


def test_esqueleto_del_proyecto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("sidebar", "barra-superior"))
    assert not fugas, fugas[:15]
```

Crear `tests/test_cuentas_idioma.py`:

```python
"""Correos de la cuenta (spec 2026-09-26 §B8): salen en el idioma de la persona
a la que van, no en el de quien hace la petición."""
import cuentas
import idiomas


def test_correo_en_el_idioma_de_la_persona(base_temporal, monkeypatch):
    enviados = []
    monkeypatch.setattr(cuentas, "smtp_configurado", lambda: True)
    monkeypatch.setattr(cuentas.notificaciones, "enviar",
                        lambda correo, asunto, cuerpo, html=None: enviados.append((asunto, cuerpo, html)) or True)
    idiomas.guardar_de_usuario("admin", "en")
    assert cuentas.enviar_restablecer("admin", "admin@prueba.local", "http://localhost")
    idiomas.guardar_de_usuario("admin", "es")
    assert cuentas.enviar_restablecer("admin", "admin@prueba.local", "http://localhost")
    (asunto_en, cuerpo_en, html_en), (asunto_es, cuerpo_es, html_es) = enviados
    assert "password" in asunto_en.lower() and "contraseña" in asunto_es.lower()
    assert '<html lang="en">' in html_en and '<html lang="es">' in html_es
    assert "1 hour" in cuerpo_en and "1 hora" in cuerpo_es
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_cuentas_idioma.py -q`
Expected: FAIL con la lista de textos en español de cada plantilla y pantalla.

- [ ] **Step 2: Envolver las plantillas**

En cada plantilla de la lista, envolver cada texto visible y cada atributo visible (`placeholder`, `title`, `aria-label`, `alt`, `value` de botones) con `_()` siguiendo los Global Constraints. Ejemplos del patrón:

```html
<button type="submit">Entrar</button>
→ <button type="submit">{{ _('Entrar') }}</button>

<input name="usuario" placeholder="Tu usuario">
→ <input name="usuario" placeholder="{{ _('Tu usuario') }}">

<p>Te mandamos un correo a <strong>{{ correo }}</strong>.</p>
→ <p>{{ _('Te mandamos un correo a <strong>%(correo)s</strong>.', correo=correo) }}</p>

{% block title %}Entrar{% endblock %}
→ {% block title %}{{ _('Entrar') }}{% endblock %}

// en <script>
alert('No pude guardar.');
→ alert({{ _('No pude guardar.')|tojson }});
```

En `base.html` incluye el banner de cuenta, la barra superior, el `<title>` y los textos del JS de `iniciarPolling()` y demás funciones compartidas. En `legal.html` solo lo fijo de la plantilla (el cuerpo viene de la ruta, Step 3).

- [ ] **Step 3: Textos de Python del esqueleto**

- `dashboard.py`: cada `flash("…")` / `flash(f"…")` y cada `_error("…")` de las rutas listadas en **Files** pasa a `flash(gettext("…"))`, con `%(x)s` en vez de `{x}`:
  ```python
  flash(f"Ya existe un usuario '{usuario}' — elige otro.")
  → return _error(gettext("Ya existe un usuario '%(usuario)s' — elige otro.", usuario=usuario))
  ```
  Los `titulo=`/`actualizado=` de `privacidad`, `terminos` y `eliminar_datos` pasan por `gettext`. `_PRIVACIDAD_HTML` y `_TERMINOS_HTML` pasan a diccionarios `{"es": """…""", "en": """…"""}` (el español idéntico al de hoy; el inglés, traducción fiel) y el cuerpo de `eliminar_datos` igual; las rutas eligen con `str(get_locale())`. Los HTML legales NO van al catálogo (son documentos largos: se mantienen como dos textos completos).
- `usuarios.py`: los mensajes que llegan a la persona (`validar_usuario`, `validar_password`, `crear`, `actualizar`, `cambiar_password`) pasan por `gettext` (`from flask_babel import gettext` arriba del módulo; fuera de una petición devuelve el español).
- `cuentas.py`: `_horas_texto` → `ngettext("%(num)d hora", "%(num)d horas", horas)`; en `_armar_correo` cada texto (asunto, intro, cierre, botón, «Si el botón no funciona…») por `gettext` con `%(usuario)s`, `%(plataforma)s`, `%(vence)s`, y `lang=\"{idioma}\"` con `idioma = str(get_locale() or idiomas.DEFECTO)`; en `_enviar`, la línea `asunto, cuerpo, html = _armar_correo(tipo, usuario, enlace)` queda dentro de `with idiomas.en_idioma(idiomas.de_usuario(usuario)):`.

- [ ] **Step 4: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar`, luego `venv/bin/python3 catalogo_i18n.py pendientes` para ver la lista. Traducir cada `msgstr` en `messages.po` con el glosario (conservar `%(x)s`, `%%` y etiquetas HTML), y `venv/bin/python3 catalogo_i18n.py compilar`.

- [ ] **Step 5: Guardias en verde**

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_cuentas_idioma.py tests/test_i18n_catalogo.py -q`
Expected: PASS. Una fuga que venga de datos de prueba (no de la app) se resuelve cambiando el dato sembrado, nunca agregando palabras a `EXCEPCIONES`.

- [ ] **Step 6: Suite completa y commit**

Run: `venv/bin/python3 -m pytest -q` → PASS (el español no cambió: los tests viejos de login, registro, cuentas y panel siguen iguales).

```bash
git add templates/ dashboard.py usuarios.py cuentas.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/6 de la fase 2): esqueleto, páginas públicas, panel y correos de cuenta en inglés

Barra lateral, encabezado, login/registro/recuperar/restablecer, portada,
legales (texto completo en los dos idiomas), panel del admin y los correos de
verificar/restablecer, que salen en el idioma de la persona.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Configuración › Puesta a punto y Conexiones

**Files:**
- Modify: `templates/_tab_settings.html` (nav de apartados l.45-52, apartados `puesta` l.55-69 y `conexiones` l.70-384), `templates/_llave_tarjeta.html`, `templates/_meta_conectar.html`, `templates/_meta_elegir_forma.html`, `templates/_meta_agencia_cliente.html`, `templates/_meta_propia_guia.html`; `dashboard.py` (`_estado_llaves` y `_llaves_visibles` ~l.1761-1820, y los `flash` de `meta_conectar`, `meta_desconectar`, `meta_forma`, `meta_app_guardar`, `meta_app_borrar`, `meta_agencia_buscar`, `meta_agencia_conectar`, `meta_agencia_salir`, `meta_agencia_avisar`, `meta_agencia_avisar_cancelar`, `tienda_conectar`, `tienda_desconectar`, `tienda_sync`, `tienda_meli_iniciar`, `meli_callback`, `cfg_pixel_refrescar`, `cfg_triple_whale_conectar`, `cfg_triple_whale_probar`, `cfg_triple_whale_desconectar`); `translations/`; `tests/test_i18n_plantillas.py`; `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: apartados `config-ap-puesta` y `config-ap-conexiones` en inglés para admin y cliente.

- [ ] **Step 1: Registrar las guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma: `"_llave_tarjeta.html", "_meta_conectar.html", "_meta_elegir_forma.html", "_meta_agencia_cliente.html", "_meta_propia_guia.html"` (`_tab_settings.html` entra entero en la Task 6, cuando están todos sus apartados). Al final de `tests/test_i18n_fugas.py`:

```python
def test_config_puesta_y_conexiones_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("config-ap-puesta", "config-ap-conexiones"))
    assert not fugas, fugas[:15]


def test_config_conexiones_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("config-ap-conexiones",))
    assert not fugas, fugas[:15]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "meta or llave or puesta or conexiones"` → FAIL.

- [ ] **Step 2: Envolver**

- Plantillas: mismo patrón de la Task 4 Step 2, incluido el texto de los botones de la nav de apartados (l.45-52) y el JS de conexiones si lo hay.
- `_estado_llaves`: se arma en cada petición, así que sus textos (nombre de la tarjeta, descripción, pasos de «Cómo conseguirla», `cliente_hace`) van con `gettext(...)` directo. Los nombres propios (Anthropic, fal, Higgsfield, Cloudflare R2, Meta, SMTP, MercadoLibre) no se traducen y quedan fuera de `gettext`.
- Los `flash` de las rutas listadas: `flash(gettext("…"))` como en la Task 4 Step 3. Los mensajes de error que vienen de `meta_conexion`/`meta_agencia`/`conectores` y se muestran con `str(e)` se dejan como están en esta fase (salen del motor; su barrido es la fase 6), salvo que la guardia de fugas los muestre en la pantalla de prueba.

- [ ] **Step 3: Catálogo, guardias y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir los pendientes → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ dashboard.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (5/6 de la fase 2): Configuración › Puesta a punto y Conexiones en inglés

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Configuración › Marca, Generación, Cuenta y avisos, Gasto (y la pestaña entera)

**Files:**
- Modify: `templates/_tab_settings.html` (apartados `marca` l.385, `generacion` l.424, `cuenta` l.523, `gasto` l.586 y el `<script>` final l.~760), `dashboard.py` (`NOMBRES_TIPO_GASTO` l.~3915 y los `flash` de `guardar_nombre_proyecto`, `subir_logo`, `eliminar_logo`, `guardar_preferencias_flowplus`, `guardar_preferencias_sonido`, `guardar_preferencias_swap`, `cfg_correo`, `cuenta_correo`, `cuenta_password`, `gasto_csv`), `providers/flowplus_modelos.py` (`nombre`/`nota` de `VIDEO`/`IMAGEN`), `final_edition/tipos.py` (`PAISES[...]["nombre"]`, etiquetas de `ESTILOS_MUSICA` si se muestran), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-5; `idiomas.N_`, filtro `traducir`.
- Produces: `#tab-settings` completo en inglés; `_tab_settings.html` en `PLANTILLAS_TRADUCIDAS`.

- [ ] **Step 1: Registrar las guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"_tab_settings.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
def test_configuracion_entera_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]


def test_configuracion_entera_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-settings",))
    assert not fugas, fugas[:15]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "settings or configuracion"` → FAIL.

- [ ] **Step 2: Envolver**

- `_tab_settings.html`: mismo patrón; el `<script>` final con `|tojson`. El selector de `idioma_prompt` (Generación) se traduce tal cual (sus textos) — se reemplaza en la fase 3.
- Constantes de módulo que se muestran en esta pestaña: marcar con `N_` y mostrar con `|traducir`:
  ```python
  # dashboard.py
  NOMBRES_TIPO_GASTO = {"video": N_("Videos"), "imagen": N_("Imágenes"), ...}
  # providers/flowplus_modelos.py (from idiomas import N_)
  "nota": N_("Hasta 10 imágenes y 5 videos de referencia (1-15 s), ..."),
  ```
  ```html
  {{ nombres_tipo[t]|traducir }}   {{ m.nota|traducir }}   {{ p.nombre|traducir }}
  ```
  En el CSV (`gasto_csv`) los nombres de tipo pasan por `gettext(...)` al escribir la fila.
- Los `flash` de las rutas listadas: `flash(gettext("…"))`.

- [ ] **Step 3: Catálogo, guardias y suite**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

- [ ] **Step 4: Verificación visual en inglés**

Con el camino de la memoria «Ver la UI sin contraseña» (render con el test client + `http.server` temporal): sesión admin con `idiomas.guardar_de_usuario("admin", "en")` en el usuarios.json temporal; renderizar `/cliente/acme`, `/panel`, `/login` (con cookie `idioma=en` y con `ACTIVO_PARA_TODOS=True` para ver los enlaces), `/privacidad`. Recorrer barra lateral y los 6 apartados de Configuración a 1280×800 y a 375×812: nada en español, nada cortado ni desbordado (el inglés a veces es más corto, a veces más largo en botones). Capturas a Daniel con `SendUserFile`. `git checkout -- .claude/launch.json` al terminar.

- [ ] **Step 5: Commit**

```bash
git add templates/ dashboard.py providers/flowplus_modelos.py final_edition/tipos.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (6/6 de la fase 2): Configuración completa en inglés

Marca, Generación, Cuenta y avisos y Gasto; constantes mostradas marcadas con
N_ y traducidas con |traducir. Con esto el esqueleto y Configuración quedan en
los dos idiomas; el selector sigue visible solo para el admin.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Despliegue (con permiso de Daniel)**

Preguntar antes. En el VPS: `venv/bin/pip install -r requirements.txt` (Flask-Babel) ANTES de reiniciar, y reiniciar **los dos servicios** (el worker importa `providers/flowplus_modelos.py`, que ahora importa `idiomas`). Comprobar en producción que un cliente sigue viendo todo en español y sin selector, y que el admin ve el selector.
