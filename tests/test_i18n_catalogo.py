"""Catálogo de traducciones (spec 2026-09-26 §B1, §Pruebas): todo texto marcado
tiene su inglés, el .mo versionado está al día con el .po, y nada pisa `_`."""
import glob
import os
import re
import tokenize

from babel.messages.pofile import read_po

import catalogo_i18n

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCADOR = re.compile(r"%\((\w+)\)[sd]")
PORCENTAJE_SUELTO = re.compile(r"%(?!%|\(\w+\)[sd])")
# Llamada de traducción dentro de las llaves {…} de un f-string: en Python 3.9
# el extractor de Babel ve el f-string como un único token STRING y nunca
# entra a mirar dentro de sus llaves (cuentas.py:237 era así).
GETTEXT_EN_LLAVES_FSTRING = re.compile(r"\{[^{}]*\b(?:gettext|ngettext|N_)\s*\(")


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


def test_gettext_no_dentro_de_llaves_de_fstring():
    """Babel extrae de un .py sin ejecutarlo; en Python 3.9 un f-string es un
    único token STRING, así que gettext(...)/ngettext(...)/N_(...) escrito
    dentro de sus {…} nunca llega al catálogo (queda mudo en producción)."""
    malos = []
    for ruta in catalogo_i18n.archivos_py():
        with open(ruta, "rb") as f:
            try:
                tokens = list(tokenize.tokenize(f.readline))
            except (tokenize.TokenizeError, SyntaxError, IndentationError):
                continue
        for tok in tokens:
            if tok.type != tokenize.STRING:
                continue
            prefijo = tok.string[:2].lower()
            if "f" not in prefijo:
                continue
            if GETTEXT_EN_LLAVES_FSTRING.search(tok.string):
                malos.append(f"{os.path.relpath(ruta, RAIZ)}:{tok.start[0]}: {tok.string[:100]!r}")
    assert not malos, ("gettext/ngettext/N_ dentro de las llaves de un f-string (Babel no lo ve, "
                        "calcúlalo en una variable antes): \n" + "\n".join(malos))
