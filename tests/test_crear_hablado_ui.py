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
    assert "hablado: document.getElementById('crear-modo-hablado')" in html
    assert "if (t === 'hablado')" in html and "localStorage.setItem('crear-modo-acme', 'hablado')" in html


def _script_modos(html):
    """El <script> de _tab_flowplus.html que cambia de modo en Crear."""
    for m in re.finditer(r"<script>(.*?)</script>", _crear(html), re.S):
        if "var KEY = 'crear-modo-" in m.group(1):
            return m.group(1)
    raise AssertionError("no encontré el script de los modos de Crear")


# Un DOM mínimo para correr el script de los modos en Node: pastillas y paneles
# con classList, el hash, localStorage y los eventos que despacha. `pasos` es
# una lista de hashes: el primero es el de la carga; cada uno de los demás
# cambia location.hash y dispara hashchange. Imprime el modo activo tras cada paso.
_DOM_MODOS = r"""
const MODOS = ['referencias', 'cambiar', 'flowplus', 'audios', 'hablado'];
function clases(ini) { const s = new Set(ini); return {
  toggle(c, si) { si ? s.add(c) : s.delete(c); }, contains(c) { return s.has(c); } }; }
const botones = MODOS.map(m => ({ dataset: { modo: m }, classList: clases(m === 'referencias' ? ['activo'] : []),
  addEventListener() {} }));
const paneles = {}; MODOS.forEach(m => { paneles['crear-modo-' + m] = { classList: clases([]) }; });
const oyentes = {}; const avisados = [];
const almacen = { 'crear-modo-acme': GUARDADO };
global.window = { addEventListener(t, f) { (oyentes[t] = oyentes[t] || []).push(f); } };
global.location = { hash: PASOS[0] };
global.localStorage = { getItem(k) { return k in almacen ? almacen[k] : null; }, setItem(k, v) { almacen[k] = v; } };
global.CustomEvent = function (t, o) { this.type = t; this.detail = o.detail; };
global.document = { querySelectorAll() { return botones; }, getElementById(id) { return paneles[id] || null; },
  dispatchEvent(e) { avisados.push(e.detail.modo); } };
function activo() {
  const p = MODOS.filter(m => paneles['crear-modo-' + m].classList.contains('activo'));
  const b = botones.filter(x => x.classList.contains('activo')).map(x => x.dataset.modo);
  return p.length === 1 && b.length === 1 && p[0] === b[0] ? p[0] : 'roto:' + p + '|' + b;
}
const vistos = [];
SCRIPT
vistos.push(activo());
for (const h of PASOS.slice(1)) {
  location.hash = h; (oyentes.hashchange || []).forEach(f => f());
  vistos.push(activo());
}
console.log(JSON.stringify({ vistos, avisados, guardado: almacen['crear-modo-acme'] }));
"""


def _correr_modos(script, pasos, guardado=None):
    js = (_DOM_MODOS.replace("GUARDADO", json.dumps(guardado)).replace("PASOS", json.dumps(pasos))
          .replace("SCRIPT", script))
    r = subprocess.run([shutil.which("node"), "-e", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_el_hash_de_un_modo_lo_abre_al_cargar_y_estando_ya_en_la_pagina(app):
    script = _script_modos(app["c"].get("/cliente/acme").data.decode())
    # Al cargar: el hash manda; sin hash de modo, el recordado; sin nada, «Desde referencias».
    assert _correr_modos(script, ["#hablado"], guardado="audios")["vistos"] == ["hablado"]
    assert _correr_modos(script, ["#creativeflowplus"], guardado="audios")["vistos"] == ["audios"]
    assert _correr_modos(script, [""])["vistos"] == ["referencias"]
    # Ya en la página (deuda del anuncio hablado: antes solo funcionaba al cargar).
    r = _correr_modos(script, ["#creativeflowplus", "#audios", "#hablado", "#calzado", "#referencias"])
    assert r["vistos"] == ["referencias", "audios", "hablado", "cambiar", "referencias"]
    assert r["avisados"] == ["referencias", "audios", "hablado", "cambiar", "referencias"]
    assert r["guardado"] == "referencias"
    # Un hash que no es un modo (otra pestaña, o un nombre de Object.prototype) no lo cambia.
    r = _correr_modos(script, ["#audios", "#experimentos", "#constructor", "#flowplus?x=1"])
    assert r["vistos"] == ["audios", "audios", "audios", "flowplus"]


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
