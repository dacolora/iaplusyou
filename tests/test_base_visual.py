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


def _bloque_base():
    css = open("static/style.css", encoding="utf-8").read()
    marca = "Base visual común (2026-09-25)"
    assert marca in css, "falta el bloque de la base visual al final de style.css"
    return css[css.index(marca):]


def test_estilo_base_cubre_todos_los_campos():
    bloque = _bloque_base()
    assert "input:not([type])" in bloque
    for tipo in ("email", "url", "search", "date"):
        assert f'input[type="{tipo}"]' in bloque


def test_boton_principal_con_letra_blanca():
    bloque = _bloque_base()
    regla = re.search(r"\.btn-generar, \.btn-aprobar, \.btn-primary[^{]*\{([^}]*)\}", bloque)
    assert regla and "color: #fff" in regla.group(1)


def test_clases_de_encabezado_y_estado_vacio():
    bloque = _bloque_base()
    for clase in (".panel-cabecera-desc", ".panel-cabecera-acciones", ".estado-vacio-titulo", ".estado-vacio-texto"):
        assert clase in bloque


PESTANAS = [("tablero", "Tablero"), ("nicho", "Nicho"), ("referentes", "Referentes"),
            ("creativeflowplus", "Crear"), ("experimentos", "Experimentos"), ("sprints", "Sprints"),
            ("catalogo", "Catálogo"), ("settings", "Configuración")]


def test_cada_pestana_abre_con_su_encabezado(app):
    html = _pagina(app)
    for tab, titulo in PESTANAS:
        p = _pestana(html, tab)
        assert 'class="panel-cabecera' in p, tab
        assert p.index('class="panel-cabecera') < p.index("<h2"), tab
        assert f"<h2>{titulo}" in p, tab
        assert 'class="panel-cabecera-desc"' in p, tab
    assert 'data-abrir-detalle="nuevo-sprint"' in _pestana(html, "sprints")
    assert 'data-abrir-detalle="nuevo-estudio"' in _pestana(html, "nicho")
    rf = _pestana(html, "referentes")
    cabecera = rf[rf.index('class="panel-cabecera'):rf.index("<dialog")]
    assert 'id="btn-traer-referentes"' in cabecera and "panel-cabecera-acciones" in cabecera


def test_estados_vacios_con_accion(app):
    html = _pagina(app)
    sp, ni, rf, ex = (_pestana(html, t) for t in ("sprints", "nicho", "referentes", "experimentos"))
    # Sprints y Nicho: el botón del encabezado y el formulario de abajo bastan
    # (tres «+ Nuevo …» en la misma pantalla sobraban).
    assert 'class="estado-vacio"' in sp and sp.count('data-abrir-detalle="nuevo-sprint"') == 1
    assert 'class="estado-vacio"' in ni and ni.count('data-abrir-detalle="nuevo-estudio"') == 1
    assert 'class="estado-vacio"' in rf and "Todavía no hay referentes" in rf
    assert 'class="estado-vacio"' in ex and 'href="#creativeflowplus"' in ex
