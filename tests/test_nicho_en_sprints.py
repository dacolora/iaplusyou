"""Nicho vive dentro de Sprints como sub-pestaña (spec 2026-10-13-nicho-dentro-de-sprints-design.md)."""
import json
import re
import subprocess

from tests.test_rutas_nicho import _con_avatares, app  # noqa: F401  (fixture)


def _pagina(app):  # noqa: F811
    return app["c"].get("/cliente/acme").data.decode()


def _sprints(html):
    """La sección de la pestaña Sprints (hasta la siguiente, Catálogo)."""
    return html[html.index('<section id="tab-sprints"'):html.index('<section id="tab-catalogo"')]


def test_el_menu_ya_no_tiene_nicho_y_sprints_trae_las_dos_subpestanas(app):  # noqa: F811
    html = _pagina(app)
    menu = html[html.index('<nav class="sidebar-nav"'):html.index("</nav>", html.index('<nav class="sidebar-nav"'))]
    assert 'data-tab="nicho"' not in menu and 'data-tab="sprints"' in menu
    assert 'id="tab-nicho"' not in html
    sp = _sprints(html)
    assert 'class="cat-tabs sprints-subs"' in sp
    assert 'data-sub="sprints"' in sp and 'data-sub="nicho"' in sp
    nicho = sp[sp.index('id="sprints-sub-nicho"'):]
    assert "Nuevo estudio" in nicho and "Avatares" in nicho and "Nuevo sprint" not in nicho
    lista = sp[sp.index('id="sprints-sub-sprints"'):sp.index('id="sprints-sub-nicho"')]
    assert "Nuevo sprint" in lista and "Nuevo estudio" not in lista
    # Review Focus 5: con un id igual al hash, el navegador saltaría a ese elemento al abrir #nicho o #sprints.
    assert 'id="nicho"' not in html and 'id="sprints"' not in html


def test_la_subpestana_nicho_cuenta_los_avatares_nuevos(app):  # noqa: F811
    from nicho import datos
    boton = lambda h: re.search(r'<button[^>]*data-sub="nicho"[^>]*>(.*?)</button>', _sprints(h), re.S).group(1)
    assert "cat-n" not in boton(_pagina(app))
    _con_avatares(datos)                                     # un sub-avatar propuesto = uno nuevo por revisar
    assert re.search(r'<span class="cat-n">\s*1\s*</span>', boton(_pagina(app)))


def _cliente_en_node(html, casos):
    """Corre en Node el script de pestañas de `cliente.html` (hash, pestaña guardada) y devuelve, por caso, los
    paneles activos y la sub-pestaña que quedó guardada en `sprints-sub-acme`."""
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
      salida.push({activas: Object.keys(elementos).filter(id => id.startsWith('tab-') && elementos[id].classList.contains('activo')),
                   sub: store['sprints-sub-acme'] || null});
    }
    console.log(JSON.stringify(salida));
    """.replace("CASOS", json.dumps(casos)).replace("SCRIPT", script)
    r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_nicho_en_el_hash_o_guardado_abre_sprints_en_nicho(app):  # noqa: F811
    """`#nicho` (la vuelta de nicho.rutas._volver, la miga, un enlace guardado) y un localStorage de antes del cambio
    con `nicho` como última pestaña (Review Focus 3) abren Sprints y dejan guardada la sub-pestaña Nicho."""
    salida = _cliente_en_node(_pagina(app), [["#nicho", None], ["", "nicho"], ["#sprints", None]])
    assert salida == [{"activas": ["tab-sprints"], "sub": "nicho"},
                      {"activas": ["tab-sprints"], "sub": "nicho"},
                      {"activas": ["tab-sprints"], "sub": None}]


def _subpestanas_en_node(html, casos):
    """Corre en Node el script de las sub-pestañas de `_tab_sprints.html` con un DOM de mentira. Cada caso es un dict
    {hash, guardada, lanza, eventos}; `eventos`: ["hashchange", hash] | ["click", sub] | ["cr:tab", pestaña_activa].
    Devuelve por caso {visible, seleccionado, hash, guardada}."""
    script = next(s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S) if "var CLAVE = 'sprints-sub-" in s)
    codigo = """
    const salida = [];
    for (const caso of CASOS) {
      const store = caso.guardada ? {'sprints-sub-acme': caso.guardada} : {};
      const oyentes = {};
      const clases = () => { const s = new Set(); return {
        toggle(c, on) { if (on) s.add(c); else s.delete(c); }, contains: c => s.has(c), add: c => s.add(c) }; };
      const boton = sub => ({dataset: {sub}, classList: clases(), attrs: {}, clic: null,
        setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(t, f) { if (t === 'click') this.clic = f; }});
      const botones = [boton('sprints'), boton('nicho')];
      const subs = [{dataset: {sub: 'sprints'}, hidden: false}, {dataset: {sub: 'nicho'}, hidden: true}];
      const raiz = {classList: clases(), querySelectorAll: sel => (sel.indexOf('.sprints-subs') === 0 ? botones : subs)};
      raiz.classList.add('activo');
      global.document = {readyState: 'complete', addEventListener() {},
                         getElementById: id => (id === 'tab-sprints' ? raiz : null)};
      global.window = {addEventListener(t, f) { oyentes[t] = f; }};
      global.localStorage = caso.lanza
        ? {getItem() { throw new Error('privado'); }, setItem() { throw new Error('privado'); }}
        : {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }};
      global.location = {hash: caso.hash || ''};
      global.history = {replaceState(a, b, url) { location.hash = url; }};
      SCRIPT
      for (const [tipo, valor] of (caso.eventos || [])) {
        if (tipo === 'hashchange') { location.hash = valor; if (oyentes.hashchange) oyentes.hashchange(); }
        if (tipo === 'click') botones.find(b => b.dataset.sub === valor).clic();
        if (tipo === 'cr:tab') { location.hash = '#sprints'; raiz.classList.toggle('activo', valor);
                                 if (oyentes['cr:tab']) oyentes['cr:tab'](); }
      }
      salida.push({visible: subs.filter(s => !s.hidden).map(s => s.dataset.sub),
                   seleccionado: botones.filter(b => b.classList.contains('activo') && b.attrs['aria-selected'] === 'true').map(b => b.dataset.sub),
                   hash: location.hash, guardada: store['sprints-sub-acme'] || null});
    }
    console.log(JSON.stringify(salida));
    """.replace("CASOS", json.dumps(casos)).replace("SCRIPT", script)
    r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_la_subpestana_que_se_ve_al_entrar(app):  # noqa: F811
    """Spec §1: el hash explícito manda (ruling 3), si no la guardada, si no Sprints; sin localStorage no se rompe."""
    casos = [{"hash": "#nicho"}, {"hash": "#sprints", "guardada": "nicho"}, {"hash": "", "guardada": "nicho"},
             {"hash": ""}, {"hash": "#nicho", "lanza": True}, {"hash": "", "lanza": True},
             {"hash": "#creativeflowplus", "guardada": "nicho"}, {"hash": "", "guardada": "basura"}]
    vistas = [(s["visible"], s["seleccionado"]) for s in _subpestanas_en_node(_pagina(app), casos)]
    n, s = (["nicho"], ["nicho"]), (["sprints"], ["sprints"])
    assert vistas == [n, s, n, s, n, s, n, s]


def test_cambiar_de_subpestana_mueve_la_direccion_y_se_recuerda(app):  # noqa: F811
    casos = [
        {"hash": "#sprints", "eventos": [["click", "nicho"]]},
        {"hash": "#nicho", "eventos": [["click", "sprints"]]},
        {"hash": "#sprints", "eventos": [["hashchange", "#nicho"]]},
        {"hash": "#nicho", "eventos": [["hashchange", "#experimentos"]]},       # Review Focus 4: otro hash no la mueve
        {"hash": "#nicho", "eventos": [["hashchange", "#alta-sprint"]]},
        {"hash": "", "lanza": True, "eventos": [["click", "nicho"]]},            # Review Focus 2: privado, igual cambia
    ]
    salida = _subpestanas_en_node(_pagina(app), casos)
    assert [(x["visible"], x["hash"], x["guardada"]) for x in salida] == [
        (["nicho"], "#nicho", "nicho"), (["sprints"], "#sprints", "sprints"), (["nicho"], "#nicho", "nicho"),
        (["nicho"], "#experimentos", "nicho"), (["nicho"], "#alta-sprint", "nicho"), (["nicho"], "#nicho", None)]


def test_volver_a_sprints_desde_la_barra_lateral_no_pierde_nicho_en_la_direccion(app):  # noqa: F811
    """Review Focus 1: cliente.html deja `#sprints` al hacer clic en la barra lateral y dispara `cr:tab`; con Nicho a
    la vista la dirección vuelve a `#nicho` (recargar deja Nicho). Con otra pestaña activa no se toca."""
    casos = [{"hash": "#nicho", "eventos": [["cr:tab", True]]},
             {"hash": "#sprints", "eventos": [["cr:tab", True]]},
             {"hash": "#nicho", "eventos": [["cr:tab", False]]}]
    assert [x["hash"] for x in _subpestanas_en_node(_pagina(app), casos)] == ["#nicho", "#sprints", "#sprints"]


def test_crear_un_estudio_con_error_vuelve_a_nicho(app):  # noqa: F811
    r = app["c"].post("/cliente/acme/nicho/estudios", data={"nombre": ""})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#nicho")


def test_la_miga_de_las_paginas_de_nicho_lleva_a_sprints_y_a_nicho(app):  # noqa: F811
    from nicho import datos
    from tests.test_rutas_nicho import _estudio
    eid = _estudio(datos)
    for url in (f"/cliente/acme/nicho/{eid}", "/cliente/acme/nicho/avatares"):
        html = app["c"].get(url).data.decode()
        miga = html[html.index('<p class="sprint-migas">'):html.index("</p>", html.index('<p class="sprint-migas">'))]
        assert 'href="/cliente/acme#sprints"' in miga and 'href="/cliente/acme#nicho"' in miga, url
        assert miga.index("#sprints") < miga.index("#nicho") and "›" in miga, url
