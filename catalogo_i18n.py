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
            "providers", "referentes", "sprints", "storage", "tareas", "triple_whale", "uploaders")
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
        # update_creation_date=False: si no, cada corrida reescribe
        # POT-Creation-Date aunque no cambie ningún texto, y el .po (y su
        # .mo) quedan con un diff de puro ruido en cada commit.
        cat.update(plantilla, no_fuzzy_matching=True, update_creation_date=False)
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
    cat = _leer_po()
    # `cat or Catalog(...)` sería incorrecto acá: Catalog.__len__ cuenta solo
    # los mensajes (no la cabecera), así que un catálogo sin nada traducido
    # todavía da falsy y el `or` lo cambiaría por uno nuevo — perdiendo su
    # creation_date real y volviendo esto no determinístico (mo_al_dia()
    # dependería de la hora exacta de cada corrida).
    if cat is None:
        cat = Catalog(locale="en")
    write_mo(salida, cat, use_fuzzy=False)
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
