# Nicho dentro de Sprints — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** la pestaña Nicho deja la barra lateral y vive como sub-pestaña de Sprints («Sprints · Nicho»), sin cambiar
rutas, datos, tareas ni nada que cobre.

**Architecture:** solo plantillas Jinja + JS en línea. `_tab_sprints.html` gana una barra `cat-tabs` y dos
contenedores; el segundo incluye `_tab_nicho.html` tal cual. `cliente.html` deja de tener la sección `tab-nicho` y su
`resolver()` traduce la clave `nicho` a la pestaña `sprints` guardando la sub-pestaña. `#nicho` sigue siendo una
dirección válida (la de la sub-pestaña).

**Tech Stack:** Flask + Jinja, Flask-Babel (catálogo `translations/en/LC_MESSAGES/messages.po`), pytest, Node (para
correr el JS real de las plantillas en pruebas).

**Spec:** `docs/superpowers/specs/2026-10-13-nicho-dentro-de-sprints-design.md`

## Global Constraints

- Nada que cobre se toca: ni rutas POST, ni tareas, ni `gastos`, ni confirmaciones de costo.
- Las direcciones `/cliente/<c>/nicho/...` y `#nicho` siguen funcionando igual.
- Todo texto visible nuevo va con `{{ _('…') }}`; después `venv/bin/python3 catalogo_i18n.py actualizar`, traducir al
  inglés con `docs/i18n/glosario.md`, `venv/bin/python3 catalogo_i18n.py compilar`. Ninguna entrada `fuzzy`.
- Sin CSS nuevo salvo que la captura lo pida; si hace falta, va en `static/estilos/` y se regenera con
  `venv/bin/python3 estilos.py construir` (nunca editar `static/style.css` a mano).
- Ningún elemento con `id="nicho"` ni `id="sprints"` (el navegador saltaría a él al leer el hash).
- Los `<script>` viven en la plantilla de la pestaña (no en fragmentos por fetch). Todo `localStorage` en `try/catch`.
- Comandos desde el worktree `.claude/worktrees/nicho-en-sprints`; Python: `venv/bin/python3`.
- Commits con `git add <rutas>` explícitas (nunca `git add -A`) y la línea
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` al final del mensaje.
- El hook `verificar_edicion.py` revisa cada plantilla editada (Jinja válido, `<div>` en pareja por macro y contra
  HEAD): si se queja, se arregla la plantilla, no el hook.

## Review Focus

1. **Un clic en «Sprints» de la barra lateral con la sub-pestaña Nicho a la vista** deja `#sprints` en la dirección;
   la persona espera que recargar la deje en Nicho → la prueba del evento `cr:tab` en la Tarea 1.
2. **Un navegador privado donde `localStorage` lanza error** → la página abre en Sprints y las sub-pestañas cambian
   igual → caso `lanza` en la Tarea 1.
3. **Alguien con `nicho` guardado como última pestaña (de antes del cambio)** espera ver Nicho, no la lista de sprints
   → caso de `localStorage` viejo en la Tarea 1.
4. **Un hash que no es de esta pestaña (`#experimentos`, `#alta-sprint`)** no debe cambiar la sub-pestaña → caso
   `hashchange` a otro hash en la Tarea 1.
5. **Un elemento con `id="nicho"` o `id="sprints"`** haría saltar la página al abrir el enlace → aserción en la
   prueba de estructura de la Tarea 1.

---

### Task 1: Sub-pestañas «Sprints · Nicho» y fuera la pestaña Nicho

**Files:**
- Modify: `templates/_sidebar.html` (comentario de arriba y el botón `data-tab="nicho"`)
- Modify: `templates/cliente.html` (la `<section id="tab-nicho">`, la entrada `nicho` de `paneles`, `resolver()`)
- Modify: `templates/_tab_sprints.html` (archivo entero, contenido abajo)
- Modify: `templates/_tab_nicho.html` (solo el comentario de arriba)
- Modify: `translations/en/LC_MESSAGES/messages.po` (+ `.mo`) por `catalogo_i18n.py`
- Modify: `.claude/skills/nicho/SKILL.md`, `.claude/skills/sprints/SKILL.md`
- Modify tests: `tests/test_rutas_nicho.py`, `tests/test_rendimiento_cableado.py`, `tests/test_rutas_meta_rendimiento.py`,
  `tests/test_rutas_triple_whale.py`, `tests/test_i18n_app_entera.py`, `tests/test_i18n_fugas.py`
- Create: `tests/test_nicho_en_sprints.py`

**Interfaces:**
- Consumes: el contexto que ya arma `dashboard.ver_cliente` (`avatares_resumen` de `nicho.rutas.contexto`, el de
  `sprints.rutas.contexto`), el evento `cr:tab` que `cliente.html` dispara tras un clic en la barra lateral.
- Produces:
  - Ids `sprints-sub-sprints` y `sprints-sub-nicho` (contenedores `.sprints-sub[data-sub]`), barra
    `nav.cat-tabs.sprints-subs` con `button.cat-tab[data-sub="sprints"|"nicho"]`.
  - Clave de navegador `sprints-sub-<cliente>` con valor `sprints` | `nicho`.
  - El script de la sub-pestaña contiene el texto `var CLAVE = 'sprints-sub-` (las pruebas lo buscan así).
  - Helpers de prueba en `tests/test_nicho_en_sprints.py`: `_cliente_en_node(html, casos)` y
    `_subpestanas_en_node(html, casos)` (la Tarea 2 no los usa).

- [ ] **Step 1: Escribir las pruebas nuevas (fallan)**

Crear `tests/test_nicho_en_sprints.py`:

```python
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
```

- [ ] **Step 2: Correr las pruebas nuevas y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_en_sprints.py -q`
Expected: FAIL (la página todavía trae `data-tab="nicho"` y no hay `sprints-subs`; `test_crear_un_estudio_con_error_vuelve_a_nicho` ya pasa).

- [ ] **Step 3: Quitar el botón Nicho de la barra lateral**

En `templates/_sidebar.html`, borrar el bloque entero:

```html
    <button type="button" class="sidebar-item" data-tab="nicho" role="tab" title="{{ _('Nicho') }}">
      <svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6" stroke="currentColor" stroke-width="2" fill="none"/><path d="M15 15l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M8 10.5h5M10.5 8v5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      <span class="sidebar-texto">{{ _('Nicho') }}</span>
    </button>
```

y en el comentario de arriba, después de la línea `Las claves viejas \`triplewhale\` y \`meta\` las resuelve cliente.html.`, agregar:

```
   `nicho` (2026-10-13) ya no es pestaña: vive en Sprints › Nicho (spec
   2026-10-13-nicho-dentro-de-sprints); cliente.html resuelve la clave.
```

- [ ] **Step 4: Quitar la sección y resolver la clave en `cliente.html`**

En `templates/cliente.html`:

1. Borrar:
```html
<section id="tab-nicho" class="tab-panel" role="tabpanel">
  {% include "_tab_nicho.html" %}
</section>

```
2. En `var paneles = {…}` borrar la línea `      nicho: document.getElementById('tab-nicho'),`.
3. En el comentario que precede a `var JUBILADAS`, después de las dos líneas de `'triplewhale' y 'meta'`, agregar:
```js
    // 'nicho' (2026-10-13) es la sub-pestaña Nicho de Sprints: el hash (la vuelta
    // de nicho.rutas, la miga, los enlaces guardados) y el guardado abren Sprints
    // y dejan elegida esa sub-pestaña; _tab_sprints.html la muestra al terminar de
    // cargar la página, después de este script.
```
4. Dentro de `function resolver(t) {`, justo antes de `if (t === 'idea') return 'creativeflowplus';`, agregar:
```js
      if (t === 'nicho') {
        try { localStorage.setItem('sprints-sub-{{ cliente }}', 'nicho'); } catch (e) {}
        return 'sprints';
      }
```

- [ ] **Step 5: Reescribir `_tab_sprints.html` con las sub-pestañas**

Reemplazar el archivo entero por:

```html
{% from "_sprint_macros.html" import anillo, chip_estado %}
{# Pestaña Sprints. Contexto de sprints.rutas.contexto(cliente): sprints_lista,
   pais_calendario, presets_temporadas, inicio_defecto, fin_defecto. Aquí solo
   se crea el sprint con lo mínimo; las campañas se arman en su tablero
   (sprint_detalle.html). Desde 2026-09-27 el sprint es para todos los países:
   no pide país ni idioma (se trabaja en inglés y la edición final adapta cada
   país), y «Momento del mes» ofrece el calendario del proyecto.
   Desde 2026-10-13 (spec 2026-10-13-nicho-dentro-de-sprints) la pestaña tiene
   dos sub-pestañas: «Sprints» (lo de siempre) y «Nicho» (la pestaña Nicho de
   antes, _tab_nicho.html tal cual, con su contexto de nicho.rutas.contexto).
   Sus direcciones son #sprints y #nicho; ningún elemento lleva esos ids, o el
   navegador saltaría a él. El JS de las sub-pestañas vive aquí, al final. #}
<nav class="cat-tabs sprints-subs" role="tablist" aria-label="{{ _('Secciones de Sprints') }}">
  <button type="button" class="cat-tab activo" role="tab" aria-selected="true" data-sub="sprints">{{ _('Sprints') }}</button>
  <button type="button" class="cat-tab" role="tab" aria-selected="false" data-sub="nicho">{{ _('Nicho') }}{% if avatares_resumen and avatares_resumen.nuevos %} <span class="cat-n">{{ avatares_resumen.nuevos }}</span>{% endif %}</button>
</nav>

<div class="sprints-sub" id="sprints-sub-sprints" data-sub="sprints">
<div class="panel-cabecera">
  <div>
    <h2>Sprints</h2>
    <p class="panel-cabecera-desc">{{ _('Un sprint es el plan de contenido de un mes para todos tus países: pones el mes y en su tablero armas una campaña por persona y producto con los anuncios que va a seguir. Se trabaja en inglés; cada país e idioma se adapta después en la edición final. Nada se genera sin tu aprobación y sin ver el costo antes.') }}</p>
  </div>
  <div class="panel-cabecera-acciones">
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="alta-sprint">+ {{ _('Nuevo sprint') }}</button>
  </div>
</div>

<details class="swap-card sprint-nuevo" id="alta-sprint">
  <summary class="swap-card-resumen">{{ _('Nuevo sprint') }}</summary>
  <form method="post" action="{{ url_for('sprints.crear', cliente=cliente) }}" class="sprint-nuevo-form">
    <label>{{ _('Nombre') }}
      <input name="nombre" required maxlength="200" placeholder="Octubre"></label>
    <label>{{ _('Inicio') }}
      <input type="date" name="inicio" required value="{{ inicio_defecto }}"></label>
    <label>{{ _('Fin') }}
      <input type="date" name="fin" required value="{{ fin_defecto }}"></label>
    <label><span class="campo-titulo">{{ _('Momento del mes') }} <small class="vacio">({{ _('opcional') }})</small></span>
      <select name="momento" data-momento>
        <option value="">{{ _('Ninguno') }}</option>
        {% for p in presets_temporadas %}<option value="{{ p.clave }}">{{ p.nombre|traducir }} ({{ p.inicio[5:] }} → {{ p.fin[5:] }})</option>{% endfor %}
        <option value="propio">{{ _('Otro (escríbelo)…') }}</option>
      </select></label>
    <label data-momento-propio hidden>{{ _('Tu momento') }}
      <input name="momento_texto" maxlength="120" placeholder="{{ _('Lanzamiento de la colección') }}"></label>
    <label class="sprint-nuevo-ancho"><span class="campo-titulo">{{ _('Marcas a imitar') }} <small class="vacio">({{ _('opcional: una por línea; si tienes el link de su Ad Library, pégalo al lado') }})</small></span>
      <textarea name="marcas" rows="2" placeholder="Crocs&#10;Skechers https://www.facebook.com/ads/library/?view_all_page_id=…"></textarea></label>
    <div class="sprint-nuevo-ancho"><button type="submit" class="btn-generar">{{ _('Crear y armar campañas →') }}</button></div>
  </form>
</details>

<div class="sprints-lista">
  {% for sp in sprints_lista %}
  <a class="swap-card sprint-card" href="{{ url_for('sprints.ver', cliente=cliente, sid=sp.id) }}">
    {{ anillo(sp.progreso.porcentaje) }}
    <div>
      <strong>{{ sp.nombre }}</strong> {{ chip_estado(sp.estado) }}
      <br><small class="vacio">{{ sp.inicio }} → {{ sp.fin }} · {{ _('%(n)s campaña(s)', n=sp.campanas_total) }} · {{ ngettext('%(num)s pieza', '%(num)s piezas', sp.piezas_planeadas) }} · {{ sp.progreso.texto }}</small>
    </div>
  </a>
  {% else %}
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">{{ _('Todavía no hay sprints') }}</p>
    <p class="estado-vacio-texto">{{ _('Crea el primero con «+ Nuevo sprint»: pones el mes y agregas sus campañas en el tablero.') }}</p>
  </div>
  {% endfor %}
</div>
</div>

<div class="sprints-sub" id="sprints-sub-nicho" data-sub="nicho" hidden>
  {% include "_tab_nicho.html" %}
</div>

<script>
  (function () {
    // «Otro (escríbelo)…» muestra el campo del momento propio.
    var sel = document.querySelector('#alta-sprint [data-momento]');
    var propio = document.querySelector('#alta-sprint [data-momento-propio]');
    if (!sel || !propio) return;
    function mostrar() { propio.hidden = sel.value !== 'propio'; }
    sel.addEventListener('change', mostrar);
    mostrar();
  })();
</script>
<script>
  // Sub-pestañas «Sprints · Nicho» (spec 2026-10-13): una a la vez. Al entrar manda
  // el hash (#nicho / #sprints), si no la última que la persona dejó abierta en este
  // proyecto y si no Sprints. Se elige en DOMContentLoaded porque el script de
  // cliente.html, que corre después de este, es el que guarda «nicho» cuando resuelve
  // un #nicho o un localStorage de antes del cambio. Cambiar de sub-pestaña mueve la
  // dirección sin recargar; tras un clic en «Sprints» de la barra lateral (que deja
  // #sprints y dispara cr:tab) la dirección vuelve a #nicho si Nicho está a la vista.
  (function () {
    var raiz = document.getElementById('tab-sprints');
    if (!raiz) return;
    var botones = raiz.querySelectorAll('.sprints-subs [data-sub]');
    var subs = raiz.querySelectorAll('.sprints-sub[data-sub]');
    var CLAVE = 'sprints-sub-{{ cliente }}';
    var actual = 'sprints';
    function mostrar(sub) {
      actual = sub === 'nicho' ? 'nicho' : 'sprints';
      subs.forEach(function (s) { s.hidden = s.dataset.sub !== actual; });
      botones.forEach(function (b) {
        var esta = b.dataset.sub === actual;
        b.classList.toggle('activo', esta);
        b.setAttribute('aria-selected', esta ? 'true' : 'false');
      });
      try { localStorage.setItem(CLAVE, actual); } catch (e) {}
      return actual;
    }
    function delHash() {
      var h = location.hash.replace('#', '').split('?')[0];
      return (h === 'nicho' || h === 'sprints') ? h : null;
    }
    botones.forEach(function (b) {
      b.addEventListener('click', function () { history.replaceState(null, '', '#' + mostrar(b.dataset.sub)); });
    });
    function alEntrar() {
      var guardada = null;
      try { guardada = localStorage.getItem(CLAVE); } catch (e) {}
      mostrar(delHash() || guardada);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', alEntrar);
    else alEntrar();
    window.addEventListener('hashchange', function () { var h = delHash(); if (h) mostrar(h); });
    window.addEventListener('cr:tab', function () {
      if (raiz.classList.contains('activo') && actual === 'nicho' && delHash() !== 'nicho') {
        history.replaceState(null, '', '#nicho');
      }
    });
  })();
</script>
```

(El `<h2>Sprints</h2>` sin `_()` es el de siempre: «Sprints» es nombre propio en los dos idiomas; no se toca.)

- [ ] **Step 6: Actualizar el comentario de `_tab_nicho.html`**

Reemplazar las tres primeras líneas (el comentario `{# Pestaña Nicho. … #}`) por:

```
{# Sub-pestaña Nicho de Sprints (desde 2026-10-13 ya no es pestaña propia: la
   incluye _tab_sprints.html; spec 2026-10-13-nicho-dentro-de-sprints). Contexto
   de nicho.rutas.contexto(cliente): estudios_nicho, productos_nicho,
   min_comentarios_nicho, etiquetas_estudio, etiquetas_inv, avatares_resumen,
   paises_estudio, pais_proyecto. #}
```

Nada más de este archivo cambia.

- [ ] **Step 7: Ajustar las pruebas que suponían la pestaña propia**

`tests/test_rutas_nicho.py`, en `test_crear_estudio_y_pestana`:
- `assert 'data-tab="nicho"' in html and "Detergente" in html and "Nuevo estudio" in html` →
  `assert 'data-tab="nicho"' not in html and 'id="sprints-sub-nicho"' in html and "Detergente" in html and "Nuevo estudio" in html`
- `pestana = html[html.index('<section id="tab-nicho"'):html.index('<section id="tab-referentes"')]` →
  `pestana = html[html.index('id="sprints-sub-nicho"'):html.index('<section id="tab-catalogo"')]`

`tests/test_rendimiento_cableado.py`:
- En `test_un_hash_o_un_localstorage_viejo_abre_rendimiento_de_verdad`:
  `assert _activas_en_node(html, casos) == [["tab-rendimiento"]] * 5 + [["tab-nicho"]]` →
  `assert _activas_en_node(html, casos) == [["tab-rendimiento"]] * 5 + [["tab-sprints"]]` (y en el docstring, al final:
  `` `#nicho` abre Sprints, donde vive Nicho desde 2026-10-13.``)
- En `test_rendimiento_ocupa_el_lugar_de_triple_whale_en_el_menu`: `data-tab="nicho"` → `data-tab="referentes"`;
  `'<section id="tab-nicho"'` → `'<section id="tab-referentes"'`; el comentario `# Y la pestaña va entre Alertas y
  Nicho también en la página.` → `# Y la pestaña va entre Alertas y Referentes también en la página.`

`tests/test_rutas_meta_rendimiento.py`:
- `_pestana`: docstring `(hasta la siguiente, Nicho)` → `(hasta la siguiente, Referentes)` y
  `html.index('id="tab-nicho"')` → `html.index('id="tab-referentes"')`.
- Línea con `< html.index('data-tab="nicho"')` → `< html.index('data-tab="referentes"')`, y su comentario
  `antes de Nicho` → `antes de Referentes`.

`tests/test_rutas_triple_whale.py`, `test_sin_conectar_la_pestana_invita_a_conectar`:
`pestana = html[ini:html.index('id="tab-nicho"')]` → `pestana = html[ini:html.index('id="tab-referentes"')]`

`tests/test_i18n_app_entera.py`: en `PESTANAS` quitar `"tab-nicho", ` (Nicho queda dentro de `tab-sprints`).

`tests/test_i18n_fugas.py`, `test_pestana_nicho_en_ingles`:
- `fugas = espanol_visible(html, ("tab-nicho",))` → `fugas = espanol_visible(html, ("sprints-sub-nicho",))`
- `tab = html[html.index('id="tab-nicho"'):html.index('id="tab-referentes"')]` →
  `tab = html[html.index('id="sprints-sub-nicho"'):html.index('id="tab-catalogo"')]`

- [ ] **Step 8: Catálogo de idiomas**

Run: `venv/bin/python3 catalogo_i18n.py actualizar`
Luego en `translations/en/LC_MESSAGES/messages.po` buscar `msgid "Secciones de Sprints"` y poner
`msgstr "Sprints sections"`; si quedó marcada `#, fuzzy`, quitar la marca. Revisar que no haya otra entrada nueva
sin traducir (`grep -n -B2 'msgstr ""$' translations/en/LC_MESSAGES/messages.po | grep -A2 'Secciones'`).
Run: `venv/bin/python3 catalogo_i18n.py compilar`
Run: `grep -c "#, fuzzy" translations/en/LC_MESSAGES/messages.po` → Expected: `0`

- [ ] **Step 9: Skills del área**

En `.claude/skills/nicho/SKILL.md`, reemplazar la frase final `UI: pestaña **Nicho**
(\`_tab_nicho.html\`) y página propia del estudio (\`nicho_estudio.html\`), Blueprint
\`nicho/rutas.py\` bajo \`/cliente/<cliente>/nicho/...\`.` por:

```
UI: desde 2026-10-13 Nicho ya no es pestaña propia: es la sub-pestaña **Sprints › Nicho**
(`_tab_nicho.html`, incluida tal cual por `_tab_sprints.html`; spec
`docs/superpowers/specs/2026-10-13-nicho-dentro-de-sprints-design.md`, pedido de Daniel: la investigación es la
entrada del plan de contenido). `#nicho` sigue siendo su dirección (`_volver`, la miga, los enlaces guardados:
`cliente.html` la resuelve a la pestaña `sprints` y guarda `sprints-sub-<cliente>`); ningún elemento lleva
`id="nicho"`. Página propia del estudio (`nicho_estudio.html`), Blueprint `nicho/rutas.py` bajo
`/cliente/<cliente>/nicho/...`, sin cambios.
```

En `.claude/skills/sprints/SKILL.md`, al final del párrafo, agregar:

```
Since 2026-10-13 the Sprints tab has two sub-tabs, «Sprints · Nicho» (spec
`docs/superpowers/specs/2026-10-13-nicho-dentro-de-sprints-design.md`, Daniel's request): `_tab_sprints.html` holds a
`nav.cat-tabs.sprints-subs` bar and two `.sprints-sub[data-sub]` containers (`sprints-sub-sprints`,
`sprints-sub-nicho` with `_tab_nicho.html` included as-is). Their addresses are `#sprints` / `#nicho` (an explicit
hash wins over the remembered `sprints-sub-<cliente>`; the sub-tab JS lives at the end of `_tab_sprints.html`, picks
on DOMContentLoaded because `cliente.html`'s `resolver('nicho')` stores the choice after it runs, and puts `#nicho`
back after a sidebar click via `cr:tab`). The Nicho sub-tab shows the count of new avatars to review (`cat-n`).
Tests: `tests/test_nicho_en_sprints.py` runs both scripts in Node.
```

- [ ] **Step 10: Correr las pruebas tocadas y las de guardia**

Run: `venv/bin/python3 -m pytest tests/test_nicho_en_sprints.py tests/test_rutas_nicho.py tests/test_rendimiento_cableado.py tests/test_rutas_meta_rendimiento.py tests/test_rutas_triple_whale.py tests/test_i18n_app_entera.py tests/test_i18n_fugas.py tests/test_i18n_catalogo.py tests/test_i18n_plantillas.py tests/test_base_visual.py tests/test_movil.py tests/test_guia_agentes.py tests/test_rutas_sprints.py -q`
Expected: PASS (todas).

- [ ] **Step 11: Commit**

```bash
git add templates/_sidebar.html templates/cliente.html templates/_tab_sprints.html templates/_tab_nicho.html \
  translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo \
  .claude/skills/nicho/SKILL.md .claude/skills/sprints/SKILL.md \
  tests/test_nicho_en_sprints.py tests/test_rutas_nicho.py tests/test_rendimiento_cableado.py \
  tests/test_rutas_meta_rendimiento.py tests/test_rutas_triple_whale.py tests/test_i18n_app_entera.py tests/test_i18n_fugas.py
git commit -m "Nicho pasa a ser la sub-pestaña Sprints › Nicho; #nicho sigue abriéndolo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: La miga «← Sprints › Nicho» en las páginas de Nicho

**Files:**
- Modify: `templates/_nicho_nav.html`
- Modify: `translations/en/LC_MESSAGES/messages.po` (+ `.mo`) solo si `actualizar` encuentra algo nuevo
- Test: `tests/test_nicho_en_sprints.py` (agregar una prueba)

**Interfaces:**
- Consumes: la dirección `#nicho` de la Tarea 1 (la resuelve `cliente.html`), el fixture `app` y `_estudio` de
  `tests/test_rutas_nicho.py`.
- Produces: nada que otra tarea use.

- [ ] **Step 1: Escribir la prueba (falla)**

Agregar al final de `tests/test_nicho_en_sprints.py`:

```python
def test_la_miga_de_las_paginas_de_nicho_lleva_a_sprints_y_a_nicho(app):  # noqa: F811
    from nicho import datos
    from tests.test_rutas_nicho import _estudio
    eid = _estudio(datos)
    for url in (f"/cliente/acme/nicho/{eid}", "/cliente/acme/nicho/avatares"):
        html = app["c"].get(url).data.decode()
        miga = html[html.index('<p class="sprint-migas">'):html.index("</p>", html.index('<p class="sprint-migas">'))]
        assert 'href="/cliente/acme#sprints"' in miga and 'href="/cliente/acme#nicho"' in miga, url
        assert miga.index("#sprints") < miga.index("#nicho") and "›" in miga, url
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 -m pytest tests/test_nicho_en_sprints.py::test_la_miga_de_las_paginas_de_nicho_lleva_a_sprints_y_a_nicho -q`
Expected: FAIL (`#sprints` no está en la miga).

- [ ] **Step 3: Cambiar la miga**

En `templates/_nicho_nav.html`, reemplazar:

```html
<p class="sprint-migas">
  <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='nicho') }}">← {{ _('Nicho') }}</a>
  {% if estudio %} · {{ estudio.nombre }}{% endif %}
</p>
```

por:

```html
<p class="sprint-migas">
  <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='sprints') }}">← {{ _('Sprints') }}</a> ›
  <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='nicho') }}">{{ _('Nicho') }}</a>
  {% if estudio %} · {{ estudio.nombre }}{% endif %}
</p>
```

y en el comentario de arriba agregar al final (antes de `#}`): `Desde 2026-10-13 Nicho vive en Sprints: la miga es
«← Sprints › Nicho» (#sprints y #nicho).`

- [ ] **Step 4: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar` — «Sprints» y «Nicho» ya existen; si aparece algo nuevo, traducirlo
con `docs/i18n/glosario.md`; luego `venv/bin/python3 catalogo_i18n.py compilar` y
`grep -c "#, fuzzy" translations/en/LC_MESSAGES/messages.po` → `0`.

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_en_sprints.py tests/test_rutas_nicho.py tests/test_i18n_fugas.py tests/test_i18n_catalogo.py tests/test_i18n_plantillas.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/_nicho_nav.html tests/test_nicho_en_sprints.py
git add translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo  # solo si cambiaron
git commit -m "Nicho: la miga de sus páginas dice «← Sprints › Nicho»

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Después de las tareas (lo hace quien orquesta, no un implementador)

1. Suite completa: `venv/bin/python3 -m pytest -q` (con las lentas).
2. Captura real (memoria `verificar-ui-sin-contrasena`): escritorio y 375 px, Sprints › Sprints y Sprints › Nicho, sin
   desplazamiento lateral; `#nicho` abre Nicho; clic en las pastillas.
3. Subagente `revisor` contra este plan y el spec, con mutaciones.
4. Mezcla a main y despliegue con la skill `despliegue` (solo `iaplusyou`, el worker no se reinicia).
