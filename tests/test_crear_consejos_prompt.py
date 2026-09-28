"""Consejos para escribir el prompt en Crear (2026-09-27): el texto va tal cual
al modelo, así que la ayuda es solo para leer — un <details> fuera del
formulario que no agrega ningún campo ni cambia lo que se manda."""
from tests.test_crear_compositor import _crear, _form, _html
from tests.test_rutas_crear_director import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _consejos(crear):
    ini = crear.index('id="fp-consejos"')
    return crear[ini:crear.index("</details>", ini)]


def test_los_cinco_consejos_estan_debajo_del_formulario(app):
    crear = _crear(_html(app))
    consejos = _consejos(crear)
    for texto in ("cuántas personas", "segundo a segundo", "Un solo lugar",
                  "solo las fotos de quien aparece", "sin @Imagen"):
        assert texto in consejos, texto
    assert crear.index('id="fp-consejos"') > crear.index('class="crear-pie"')


def test_la_ayuda_no_agrega_campos_al_formulario(app):
    crear = _crear(_html(app))
    assert 'id="fp-consejos"' not in _form(crear)
    assert "<input" not in _consejos(crear) and "<textarea" not in _consejos(crear)
