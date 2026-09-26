"""Base visual común (spec 2026-09-25): marcado de la página del proyecto y
bloque de CSS que es la fuente de verdad de campos, botones, encabezado de
pestaña y estado vacío."""
import re

from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _pagina(app):
    return app["c"].get("/cliente/acme").data.decode()


def _pestana(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    sig = html.find('<section id="tab-', ini + 10)
    return html[ini:sig if sig > 0 else len(html)]


def test_pagina_de_proyecto_sin_titulo_grande(app):
    html = _pagina(app)
    assert 'id="titulo-seccion"' not in html and 'class="pagina-cabecera"' not in html


def test_pestanas_escuchan_el_hash_suben_y_abren_detalles(app):
    html = _pagina(app)
    assert "addEventListener('hashchange'" in html
    assert "window.scrollTo(0, 0)" in html
    assert "[data-abrir-detalle]" in html
