"""Crear como compositor (spec docs/superpowers/specs/2026-09-27-crear-compositor-design.md):
el formulario cambia de forma, no de contrato — el servidor recibe los mismos
campos — y Enter en un campo de una línea ya no genera (ni cobra) un video."""
import re

from tests.test_rutas_crear_director import app  # noqa: F401  (fixture: admin en /cliente/acme)

CAMPOS = ["bandeja_vista", "accion_central", "tipo", "modelo_video", "modelo_imagen", "modelo",
          "duracion_objetivo", "aspect_ratio", "aspect_ratio_imagen", "con_sonido", "sonido",
          "musica_estilo", "musica_inicio_s", "calidad", "modo_prompt"]


def _html(app):
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def _crear(html):
    return html[html.index('id="tab-creativeflowplus"'):html.index('id="tab-sprints"')]


def _form(crear):
    ini = crear.rindex("<form", 0, crear.index('id="form-flowplus"'))
    return crear[ini:crear.index("</form>", ini)]


def test_el_formulario_manda_los_mismos_campos(app):
    form = _form(_crear(_html(app)))
    for campo in CAMPOS:
        assert f'name="{campo}"' in form, campo


def test_enter_en_un_campo_no_envia_el_formulario_de_crear(app):
    """Antes, Enter en «Sonido de la escena» hacía el envío implícito con el
    primer botón (#fp-generar, modo_prompt=directo): generaba y cobraba."""
    html = _html(app)
    js = html[html.index("form.addEventListener('keydown'"):]
    assert "e.key !== 'Enter'" in js[:300]
    assert "e.target.form === form" in js[:400] and "e.preventDefault()" in js[:400]
