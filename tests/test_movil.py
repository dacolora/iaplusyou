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


def test_css_del_celular():
    css = open("static/style.css", encoding="utf-8").read()
    i = css.index("Celular (spec 2026-09-26-movil)")
    bloque = css[i:i + 4000]
    assert "@media (max-width: 760px)" in bloque
    assert "translateX(-100%)" in bloque
    assert "body.menu-abierto .sidebar" in bloque
    assert "--sb: 0px" in bloque
