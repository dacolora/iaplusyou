"""Celular (spec 2026-09-26): menú que abre la barra lateral encima de la página."""
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def test_pagina_de_proyecto_trae_el_menu_del_celular(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'id="menu-movil"' in html and 'aria-controls="sidebar"' in html
    assert 'id="sidebar-fondo"' in html and 'id="sidebar-cerrar"' in html
    assert 'id="header-pestana"' in html
    assert "classList.toggle('menu-abierto'" in html


def test_pagina_sin_barra_lateral_no_trae_menu(app):
    html = app["c"].get("/panel").data.decode()
    assert 'id="menu-movil"' not in html
