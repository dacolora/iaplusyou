"""La pestaña Rendimiento reemplaza a Triple Whale y Meta en el menú y en todos los enlaces (spec 2026-10-09 R1)."""
import json
import os
import pathlib
import re
import subprocess

from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_el_menu_tiene_rendimiento_y_no_las_viejas(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-tab="rendimiento"' in html and 'id="tab-rendimiento"' in html
    assert 'data-tab="triplewhale"' not in html and 'data-tab="meta"' not in html
    assert 'id="tab-triplewhale"' not in html and 'id="tab-meta"' not in html


def test_las_claves_viejas_abren_rendimiento(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    assert re.search(r"triplewhale['\"]?\s*:\s*['\"]rendimiento", html) or "'triplewhale': 'rendimiento'" in html
    assert re.search(r"\bmeta['\"]?\s*:\s*['\"]rendimiento", html)


# Carpetas que no son código de la app: pruebas, agentes, dependencias, datos y salidas (venv es un enlace al del
# checkout principal: recorrerlo no sirve y tarda).
NO_SE_REVISA = {"tests", "venv", ".venv", "node_modules", "__pycache__", "worktrees", "data", "clientes", "salidas",
                "migrations", "docs"}
# Toda forma en que una plantilla, una ruta o un script nombran una pestaña: el ancla, el hash entre comillas
# (simples o dobles), el «Ir a…» y la clave del menú.
ENLACES_VIEJOS = tuple(
    forma.format(clave=clave)
    for clave in ("triplewhale", "meta")
    for forma in ('_anchor="{clave}"', "_anchor='{clave}'", 'href="#{clave}"', "href='#{clave}'",
                  '"#{clave}"', "'#{clave}'", 'data-ir-tab="{clave}"', "data-ir-tab='{clave}'",
                  'data-tab="{clave}"', "data-tab='{clave}'"))


def _archivos_de_la_app():
    """Plantillas, Python y JS de la app, recorridos sin seguir enlaces y sin las carpetas de NO_SE_REVISA ni las
    ocultas (.claude, .git…). Las rutas son relativas a la raíz: en un worktree la raíz vive dentro de `.claude/`."""
    for carpeta, subcarpetas, archivos in os.walk(RAIZ):
        subcarpetas[:] = [d for d in subcarpetas if not d.startswith(".") and d not in NO_SE_REVISA]
        for nombre in archivos:
            if nombre.endswith((".py", ".html", ".js", ".mjs")):
                yield pathlib.Path(carpeta) / nombre


def test_ningun_enlace_apunta_a_las_pestanas_viejas():
    malos = []
    revisados = set()
    for ruta in _archivos_de_la_app():
        rel = ruta.relative_to(RAIZ).as_posix()
        revisados.add(rel)
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        malos += [f"{rel}: {patron}" for patron in ENLACES_VIEJOS if patron in texto]
    assert malos == []
    # El recorrido sí mira lo que tiene que mirar (si no, la prueba pasaría en vacío, como pasó en un worktree).
    for esperado in ("dashboard.py", "templates/cliente.html", "triple_whale/rutas.py", "meta_rendimiento/rutas.py",
                     "pestana_rendimiento/rutas.py", "static/tw_resultados.js", "static/exp_resultados.js"):
        assert esperado in revisados, esperado
    assert not any(r.startswith(("tests/", "venv/", ".claude/")) for r in revisados)


def test_las_rutas_viejas_del_panel_ya_no_existen(app):  # noqa: F811
    assert app["c"].get("/cliente/acme/triple-whale/panel").status_code == 404
    assert app["c"].get("/cliente/acme/meta-rendimiento/panel").status_code == 404


# ---- más allá del brief ------------------------------------------------------------------------------------------

def _activas_en_node(html, casos):
    """Corre en Node el script de pestañas de `cliente.html` con un DOM de mentira, una vez por caso
    (hash, pestaña guardada en localStorage), y devuelve los ids de los paneles que quedaron activos."""
    script = next(s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S) if "var STORAGE_KEY = 'tab-activa-" in s)
    codigo = """
    const salida = [];
    for (const [hash, guardada] of CASOS) {
      const elementos = {};
      const store = guardada ? {'tab-activa-acme': guardada} : {};
      const clases = () => { const s = new Set(); return {
        toggle(c, on) { if (on) s.add(c); else s.delete(c); }, contains: c => s.has(c), add: c => s.add(c) }; };
      global.document = {
        querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, body: {classList: clases()},
        getElementById: id => elementos[id] || (elementos[id] = {id, classList: clases(), addEventListener() {}}),
      };
      global.window = {addEventListener() {}, scrollTo() {}, dispatchEvent() {}};
      global.localStorage = {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }};
      global.location = {hash};
      global.history = {replaceState() {}};
      global.Event = function () {};
      SCRIPT
      salida.push(Object.keys(elementos).filter(id => id.startsWith('tab-') && elementos[id].classList.contains('activo')));
    }
    console.log(JSON.stringify(salida));
    """.replace("CASOS", json.dumps(casos)).replace("SCRIPT", script)
    r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_un_hash_o_un_localstorage_viejo_abre_rendimiento_de_verdad(app):  # noqa: F811
    """R1: `#triplewhale`, `#meta` y las mismas claves guardadas en el localStorage de la gente abren Rendimiento
    (como `idea` abre Crear). Se corre el script de verdad, no se busca el texto. `#nicho` abre Sprints, donde vive
    Nicho desde 2026-10-13."""
    html = app["c"].get("/cliente/acme").data.decode()
    casos = [["#triplewhale", None], ["#meta", None], ["", "triplewhale"], ["", "meta"], ["#rendimiento", None],
             ["#nicho", None]]
    assert _activas_en_node(html, casos) == [["tab-rendimiento"]] * 5 + [["tab-sprints"]]


def test_rendimiento_ocupa_el_lugar_de_triple_whale_en_el_menu(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    menu = html[html.index('<nav class="sidebar-nav"'):html.index("</nav>")]
    assert menu.index('data-tab="alertas"') < menu.index('data-tab="rendimiento"') < menu.index('data-tab="referentes"')
    assert menu.count('data-tab="rendimiento"') == 1 and 'title="Rendimiento"' in menu
    # Y la pestaña va entre Alertas y Referentes también en la página.
    assert (html.index('<section id="tab-alertas"') < html.index('<section id="tab-rendimiento"')
            < html.index('<section id="tab-referentes"'))


def test_la_pestana_trae_ajustes_y_pide_el_panel_nuevo(app):  # noqa: F811
    """`ver_cliente` arma el contexto barato de la pestaña (sin Triple Whale ni Meta: invita a conectar y no pide el
    panel) y la conexión de Triple Whale vive dentro de «Ajustes»."""
    html = app["c"].get("/cliente/acme").data.decode()
    ini = html.index('<section id="tab-rendimiento"')
    pestana = html[ini:html.index("<section", ini + 10)]
    assert 'id="rend-ajustes"' in pestana and 'id="tw-conexion"' in pestana
    assert "Conecta Meta o Triple Whale para ver tu rendimiento" in pestana
    assert "/rendimiento/panel" not in pestana and "/triple-whale/panel" not in pestana


def test_las_rutas_viejas_de_sincronizar_y_ver_mas_ya_no_existen(app):  # noqa: F811
    """A5: «Actualizar ahora» es una sola ruta (`rendimiento.actualizar`); las de las pestañas viejas se fueron con
    ellas, también sus «Ver más»."""
    c = app["c"]
    sitio = {"Sec-Fetch-Site": "same-origin"}
    assert c.post("/cliente/acme/triple-whale/sincronizar", headers=sitio).status_code == 404
    assert c.post("/cliente/acme/meta-rendimiento/sincronizar", headers=sitio).status_code == 404
    assert c.get("/cliente/acme/meta-rendimiento/anuncios").status_code == 404
    assert c.get("/cliente/acme/meta-rendimiento/conjuntos").status_code == 404


def test_las_rutas_que_se_quedan_vuelven_a_rendimiento(app):  # noqa: F811
    """Lo que sigue en los Blueprints viejos (conexión de Triple Whale, «Elegir cuentas», las acciones de las tarjetas)
    vuelve a `#rendimiento`, no a una pestaña que ya no existe."""
    import meta_rendimiento.rutas as mr
    import triple_whale.rutas as tw
    d = app["dashboard"]
    with d.app.test_request_context("/"):
        assert tw._volver("acme").headers["Location"].endswith("/cliente/acme#rendimiento")
        assert mr._volver("acme").headers["Location"].endswith("/cliente/acme#rendimiento")
        assert d._volver_tw("acme").headers["Location"].endswith("/cliente/acme#rendimiento")


def test_las_plantillas_de_las_pestanas_viejas_se_borraron():
    for nombre in ("_tab_triple_whale.html", "_tab_meta.html", "_tw_panel.html", "_meta_panel.html",
                   "_meta_anuncios_filas.html"):
        assert not (RAIZ / "templates" / nombre).exists(), nombre
