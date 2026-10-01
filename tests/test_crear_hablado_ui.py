"""Crear › Anuncio hablado en la página (spec 2026-10-01 §1): el quinto modo,
su hash, nada pesado en la carga, el JS sin textos sueltos y el celular."""
import json
import re
import shutil
import subprocess

import pytest

from tests.i18n_util import _SCRIPT_TOKEN, _con_marca
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _crear(html):
    ini = html.index('<section id="tab-creativeflowplus"')
    fin = html.find('<section id="tab-', ini + 10)
    return html[ini:fin if fin != -1 else len(html)]


def test_el_modo_hablado_esta_en_crear_sin_su_contenido_pesado(app):
    html = app["c"].get("/cliente/acme").data.decode()
    crear = _crear(html)
    assert 'data-modo="hablado"' in crear and 'id="crear-modo-hablado"' in crear and 'id="hb"' in crear
    assert 'data-url-panel="/cliente/acme/hablado/panel"' in crear and 'data-url-voz="/cliente/acme/hablado/voz"' in crear
    assert 'data-url-crear="/cliente/acme/hablado/crear"' in crear and 'data-url-foto="/cliente/acme/hablado/foto"' in crear
    assert 'data-url-muestra="/cliente/acme/audios/muestra"' in crear
    assert "static/hablado.js" in html and "window.HB_TEXTOS" in crear
    # Las fotos y la galería llegan por fetch al abrir el modo, nunca con la página.
    assert 'class="hb-foto"' not in html and 'id="hb-voces"' not in html and 'id="hb-texto"' not in html


def test_hash_hablado_abre_crear_en_ese_modo(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert "h === 'hablado' ? 'hablado'" in html and "hablado: document.getElementById('crear-modo-hablado')" in html
    assert "if (t === 'hablado')" in html and "localStorage.setItem('crear-modo-acme', 'hablado')" in html


def test_audios_sigue_pintando_su_galeria_con_la_macro(app):
    import audios
    html = app["c"].get("/cliente/acme").data.decode()
    assert html.count('class="au-voz"') == len(audios.voces()) and 'id="au-voces"' in html
    assert '{% from "_voces_galeria.html" import fichas_galeria %}' in open("templates/_crear_audios.html", encoding="utf-8").read()


def test_plantillas_del_modo_cierran_sus_div():
    for ruta in ("templates/_crear_hablado.html", "templates/_hablado_panel.html", "templates/_hablado_macros.html",
                 "templates/_voces_galeria.html"):
        texto = re.sub(r"{#.*?#}", "", open(ruta, encoding="utf-8").read(), flags=re.S)
        assert texto.count("<div") == texto.count("</div>"), ruta


def test_css_del_modo_y_del_celular():
    css = open("static/style.css", encoding="utf-8").read()
    bloque = css[css.index("Crear › Anuncio hablado (2026-10-01)"):]
    assert ".hb-layout { display: grid;" in bloque and "minmax(min(100%, 7.5rem), 1fr)" in bloque
    assert "@media (max-width: 760px) { .hb-layout { grid-template-columns: minmax(0, 1fr); }" in bloque
    assert ".hb [hidden] { display: none !important; }" in bloque


def test_hablado_js_sin_texto_en_espanol_ni_recargas_de_barra():
    js = open("static/hablado.js", encoding="utf-8").read()
    literales = [t for t in _SCRIPT_TOKEN.findall(js) if t[0] in ("'", '"', "`") and _con_marca(t)]
    assert literales == [], literales
    assert "data-poll-job" not in js and "solo_cache" in js and "IntersectionObserver" in js
    assert "location.reload()" in js and "precio_visto" in js


def test_hablado_js_no_autorreproduce_fuera_de_su_modo_ni_con_texto_viejo():
    # Fix round 1 (revisión de la tarea 7): una voz que llega tarde (la
    # persona cambió de modo, o editó texto/voz/idioma/velocidad mientras se
    # creaba) no se reproduce sola, y la que sonaba se calla al salir del modo.
    js = open("static/hablado.js", encoding="utf-8").read()
    assert "estado.activo = !!(ev.detail && ev.detail.modo === 'hablado');" in js
    assert "if (!estado.activo) {\n      var audio = $('hb-voz-audio');\n      if (audio) audio.pause();" in js
    # Revisión final (hallazgo 3): estado.activo solo sigue crear:modo, así que
    # otra pestaña del mismo proyecto puede quedar con estado.activo=true sin
    # que el panel esté realmente a la vista — se exige además que el panel
    # esté visible (offsetParent) justo antes de reproducir.
    assert "if (estado.activo && raiz.offsetParent !== null && claveVoz === clave()) audio.play().catch(function () {});" in js


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se revisa la sintaxis del JS (el VPS no lo tiene)")
def test_hablado_js_compila():
    r = subprocess.run([shutil.which("node"), "--check", "static/hablado.js"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _cuerpo_fmt_usd():
    js = open("static/hablado.js", encoding="utf-8").read()
    m = re.search(r"function fmtUsd\(v\) \{.*?\n  (?=function )", js, re.S)
    assert m, "no encontré fmtUsd en static/hablado.js"
    return m.group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_fmt_usd_muestra_tres_decimales_solo_si_el_tercero_no_es_cero():
    # Hallazgo 4: 11 s de voz cuestan US$ 0,275 (ceil(11) × 0,025) y la
    # pantalla redondeaba a «US$ 0,28». fmtUsd debe mostrar el tercer
    # decimal solo cuando no es cero; el round-trip de precio_visto sigue
    # mandando el número crudo (sin pasar por fmtUsd) — eso no cambia aquí.
    script = "function sep(){return ',';}\n" + _cuerpo_fmt_usd() + \
        "\nconsole.log(JSON.stringify([fmtUsd(0.275), fmtUsd(0.2), fmtUsd(0.75), fmtUsd(0.025)]));"
    r = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["US$ 0,275", "US$ 0,20", "US$ 0,75", "US$ 0,025"]
