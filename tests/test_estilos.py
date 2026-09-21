"""La hoja de estilos comparte etiquetas entre la barra superior de la página
(base.html: <body><header>…) y los <header> que las plantillas usan dentro de
tarjetas (Puesta a punto en Configuración, ideas de campaña, cabecera de
campaña en Sprints). Una regla `header { … }` sin acotar pinta la barra
sticky, su fondo, su padding y el margen de la barra lateral DENTRO de cada
tarjeta — así se vio Configuración el 2026-09-20: el título empujado a la
derecha, en una columna estrecha, con la insignia debajo. Solo `body > header`
es la barra de la página; cualquier otro <header> se estila por su clase."""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _selectores(css):
    """Cada selector de cada regla `selector { … }`, sin comentarios. Las
    cabeceras `@media (…) {` se saltan; las reglas de dentro salen solas."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{", css):
        grupo = m.group(1).strip()
        if grupo.startswith("@"):
            continue
        for sel in grupo.split(","):
            yield sel.strip()


def _alcanza_header_suelto(selector):
    """True si el selector alcanza un <header> que no sea hijo directo de
    <body>: `header`, `.x header`, `header.y`, `header > .z`, `.x > header`…"""
    partes = selector.split()
    for i, parte in enumerate(partes):
        if not re.match(r"^header([.:#\[]|$)", parte):
            continue
        hijo_de_body = i >= 2 and partes[i - 1] == ">" and partes[i - 2].startswith("body")
        if not hijo_de_body:
            return True
    return False


def test_la_barra_superior_no_se_filtra_a_los_header_de_las_tarjetas():
    with open(os.path.join(RAIZ, "static", "style.css"), encoding="utf-8") as f:
        css = f.read()
    sueltos = [s for s in _selectores(css) if _alcanza_header_suelto(s)]
    assert sueltos == [], (
        "Estas reglas alcanzan cualquier <header>, incluidos los de las tarjetas; "
        f"acótalas a `body > header`: {sueltos}"
    )


def test_el_detector_distingue_la_barra_de_los_header_de_tarjeta():
    assert _alcanza_header_suelto("header")
    assert _alcanza_header_suelto(".con-sidebar header")
    assert _alcanza_header_suelto("header.llave-cabecera")
    assert _alcanza_header_suelto("article > header")
    assert not _alcanza_header_suelto("body > header")
    assert not _alcanza_header_suelto("body.con-sidebar > header .marca-header")
    assert not _alcanza_header_suelto(".idea-header")
    assert not _alcanza_header_suelto(".header-nav a")


# ---- Cache-busting de style.css --------------------------------------------
# base.html enlaza la hoja con url_for('static', …); sin una versión en la URL
# el navegador sigue usando el CSS viejo después de un despliegue (Flask no
# manda max-age, y el navegador aplica su heurística sobre Last-Modified).


@pytest.fixture()
def app_estaticos(base_temporal, tmp_path, monkeypatch):
    """La app con una carpeta static/ temporal: el test escribe su propio
    style.css y lo cambia sin tocar el del repo."""
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.setattr(dashboard.app, "static_folder", str(tmp_path))
    dashboard.app.config["TESTING"] = True
    return dashboard.app


def _enlace_style(app):
    html = app.test_client().get("/login").get_data(as_text=True)
    m = re.search(r'<link rel="stylesheet" href="([^"]+)"', html)
    assert m, "el login no enlaza la hoja de estilos"
    return m.group(1)


def test_el_enlace_a_style_css_cambia_cuando_cambia_el_archivo(app_estaticos, tmp_path):
    hoja = tmp_path / "style.css"
    hoja.write_text("body { color: red; }")
    os.utime(hoja, (1_700_000_000, 1_700_000_000))
    antes = _enlace_style(app_estaticos)
    assert antes.startswith("/static/style.css?v=") and antes != "/static/style.css?v="

    hoja.write_text("body { color: blue; }")
    os.utime(hoja, (1_700_000_100, 1_700_000_100))
    despues = _enlace_style(app_estaticos)
    assert despues != antes


def test_un_estatico_que_no_existe_se_enlaza_sin_version_y_sin_romper(app_estaticos):
    from flask import url_for
    with app_estaticos.test_request_context():
        assert url_for("static", filename="no-existe.css") == "/static/no-existe.css"
