"""Parte 4 de la mejora visual (2026-09-26): fotos que no cargan, miniaturas de
video negras en Safari y el pie de la barra lateral."""
import re

from tests.test_rutas_configuracion import _sembrar_gasto, app  # noqa: F401


def test_foto_que_no_carga_se_reemplaza_por_un_recuadro_neutro(app):
    html = app["c"].get("/cliente/acme").data.decode()
    cabeza = html[:html.index("</head>")]
    # El manejador va en <head> y en captura: atrapa también las fotos que
    # llegan después por fetch (grids, fichas).
    assert "addEventListener('error'" in cabeza and "img-rota" in cabeza
    css = open("static/style.css", encoding="utf-8").read()
    assert ".img-rota" in css


def test_miniaturas_de_video_piden_el_primer_cuadro():
    """Safari (iPhone) deja negra una miniatura con preload=metadata hasta
    darle play; `#t=0.1` le hace pintar ese cuadro."""
    for ruta, fragmento in (("templates/_tab_experimentos.html", "{{ el.url_video }}#t=0.1"),
                            ("templates/_tab_creativeflowplus.html", "{{ item.video_url }}#t=0.1")):
        assert fragmento in open(ruta, encoding="utf-8").read(), ruta


def test_pie_de_la_barra_lateral_con_el_gasto_en_su_propia_linea(app, monkeypatch):
    _sembrar_gasto(monkeypatch)
    html = app["c"].get("/cliente/acme").data.decode()
    pie = html[html.index('<div class="sidebar-usuario">'):html.index("</aside>")]
    datos = re.search(r'<span class="sidebar-texto sidebar-usuario-datos">(.*?)</span>', pie, re.S).group(1)
    assert "sidebar-gasto" not in datos          # ya no va apretado bajo el nombre
    assert 'class="sidebar-gasto"' in pie
    assert pie.index("sidebar-salir") < pie.index("sidebar-gasto")   # Salir arriba, a la derecha
