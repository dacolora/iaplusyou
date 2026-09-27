"""Plantillas ya traducidas (spec 2026-09-26 §Pruebas): en su FUENTE no queda
texto visible en español fuera de _() — en ninguna rama de un {% if %} — ni
literales en español dentro de <script>. Cada tarea que traduce una plantilla
la agrega a PLANTILLAS_TRADUCIDAS."""
import glob
import os
import re

import pytest

from tests.i18n_util import espanol_en_plantilla

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_TRADUCIDAS = [
    "base.html", "_sidebar.html", "login.html", "recuperar.html", "restablecer.html",
    "index.html", "legal.html", "panel.html",
    "_llave_tarjeta.html", "_meta_conectar.html", "_meta_elegir_forma.html",
    "_meta_agencia_cliente.html", "_meta_propia_guia.html",
    "_tab_settings.html", "_seccion_marca.html", "_comparacion_modelos.html",
    "_tab_flowplus.html", "_tab_creativeflowplus.html", "_flowplus_bandeja.html",
    "_selector_productos.html", "_selector_productos_nuevo.html", "_mi_musica.html",
    "_crear_flowplus.html", "_crear_flowplus_guiones.html", "_gpg_panel.html", "_gpg_notion.html",
    "_gpg_guion.html", "_gpg_video.html", "_gpg_clips.html", "_gpg_imagenes.html", "_gpg_macros.html",
]


def test_la_deteccion_funciona(tmp_path):
    ruta = tmp_path / "x.html"
    ruta.write_text("<p>{{ _('Guardar') }}</p><p>Guardar cambios</p>"
                    "<script>var a = {{ _('Sí')|tojson }}; var b = '¿Seguro?'; // comentario en español</script>",
                    encoding="utf-8")
    assert espanol_en_plantilla(str(ruta)) == ["Guardar cambios", "'¿Seguro?'"]

    # Test that strings containing // are not truncated
    ruta2 = tmp_path / "y.html"
    ruta2.write_text("<script>var m = 'Ver mas // detalles, más info'; // comentario en español</script>",
                     encoding="utf-8")
    assert espanol_en_plantilla(str(ruta2)) == ["'Ver mas // detalles, más info'"]


@pytest.mark.parametrize("nombre", PLANTILLAS_TRADUCIDAS)
def test_plantilla_sin_espanol_suelto(nombre):
    hallazgos = espanol_en_plantilla(os.path.join(RAIZ, "templates", nombre))
    assert not hallazgos, f"{nombre}: texto en español fuera de _():\n" + "\n".join(hallazgos[:30])


# Regresión (task-6 fix round 1): _tab_settings.html ~l.413 tenía
# `onsubmit="return confirm({{ _('¿Quitar este logo?')|tojson }});"` — un
# atributo HTML entre comillas DOBLES con un `|tojson` adentro. `tojson` emite
# comillas dobles (JSON), que cierran el atributo a la mitad: el `onsubmit`
# resultante («onsubmit="return confirm("¿Quitar este logo?");"») nunca
# compila como JS, así que el confirm() no sale — en ningún idioma, ni
# siquiera en español (rompe el "el español que se ve no cambia ni una
# letra": ahí deja de aparecer un diálogo que antes sí aparecía). Corre sobre
# TODAS las plantillas (no solo PLANTILLAS_TRADUCIDAS): un `|tojson` dentro
# de un atributo con comillas dobles está mal en cualquier plantilla, ya esté
# traducida o no.
PATRON_TOJSON_EN_ATRIBUTO_DOBLE = re.compile(r'=\s*"[^"]*\{\{[^}]*\|\s*tojson[^}]*\}\}[^"]*"')


def test_tojson_no_dentro_de_atributo_con_comillas_dobles():
    hallazgos = []
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "templates", "**", "*.html"), recursive=True)):
        with open(ruta, encoding="utf-8") as f:
            for i, linea in enumerate(f, 1):
                for m in PATRON_TOJSON_EN_ATRIBUTO_DOBLE.finditer(linea):
                    hallazgos.append(f"{os.path.relpath(ruta, RAIZ)}:{i}: {m.group(0)}")
    assert not hallazgos, (
        "Un `{{ ... | tojson }}` dentro de un atributo HTML con comillas dobles se rompe "
        "(tojson emite \" que cierra el atributo a la mitad) — usa comillas simples en el "
        "atributo:\n" + "\n".join(hallazgos))
