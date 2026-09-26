# Base visual común — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un solo aspecto para campos, botones, encabezado de pestaña y estado vacío en las 8 pestañas del proyecto, sin el nombre grande del proyecto arriba y con pestañas que responden al `#`.

**Architecture:** Un bloque nuevo al FINAL de `static/style.css` es la fuente de verdad (pisa reglas viejas por orden, sin tocarlas una por una). Las plantillas de pestaña adoptan un marcado común (`.panel-cabecera` con `.panel-cabecera-desc` y `.panel-cabecera-acciones`; `.estado-vacio`). `cliente.html` deja el `<h1>` y gana `hashchange`, subir arriba y `data-abrir-detalle`.

**Tech Stack:** Flask/Jinja2, CSS plano, JS sin dependencias, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-base-visual-comun-design.md`

## Global Constraints

- Se mantiene la identidad: `--accent`, `--accent-grad`, Space Grotesk (`--font-display`) + Inter.
- Textos, rutas y funciones no cambian; «Todavía no hay referentes» debe seguir en el HTML (lo busca `tests/test_rutas_referentes.py`).
- El botón principal lleva letra `#fff`.
- Pruebas: `venv/bin/python3 -m pytest -q -m "not slow"` (desde el worktree, con el venv del checkout principal: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).

---

### Task 1: Pestañas — sin título grande, responden al `#`, vuelven arriba

**Files:**
- Modify: `templates/cliente.html:4-6` (quitar `.pagina-cabecera`) y el primer `<script>` (función `activar`, listeners)
- Test: `tests/test_base_visual.py` (nuevo)

**Interfaces:**
- Produces: atributo `data-abrir-detalle="<id de un <details>>"` en cualquier botón de la página abre ese `details` y lo trae a la vista (lo usan las Tasks 3 y 4).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Base visual común (spec 2026-09-25): marcado de la página del proyecto."""
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
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py`
Expected: 2 FAIL (`titulo-seccion` presente; no hay `hashchange`).

- [ ] **Step 3: Implementar**

En `templates/cliente.html` borrar:

```html
<div class="pagina-cabecera">
  <h1 id="titulo-seccion">{{ nombre_proyecto }}</h1>
</div>
```

En el primer `<script>` reemplazar `activar` y el listener de botones:

```js
    function activar(tab, subir) {
      botones.forEach(function (b) { b.classList.toggle('activo', b.dataset.tab === tab); });
      Object.keys(paneles).forEach(function (t) { paneles[t].classList.toggle('activo', t === tab); });
      try { localStorage.setItem(STORAGE_KEY, tab); } catch (e) {}
      // Al cambiar de pestaña se empieza arriba (antes quedaba a la altura
      // de la pestaña anterior); la carga inicial no se toca.
      if (subir) window.scrollTo(0, 0);
    }

    botones.forEach(function (b) {
      b.addEventListener('click', function () {
        activar(b.dataset.tab, true);
        history.replaceState(null, '', '#' + b.dataset.tab);
      });
    });
```

Y después de la línea `activar(paneles[inicial] ? inicial : 'tablero');` (antes de `})();`):

```js
    // Un enlace a «#settings» (alertas del Tablero, «Ir a Configuración →»,
    // Crear → «#experimentos?piezas=…») cambia solo el hash: sin esto la
    // pestaña no cambiaba estando ya en la página. Un hash que no es
    // pestaña (#nuevo-sprint…) se ignora.
    window.addEventListener('hashchange', function () {
      var t = resolver(location.hash.replace('#', '').split('?')[0]);
      if (paneles[t]) activar(t, true);
    });

    // Botón que abre un <details> de la página (estado vacío / encabezado:
    // «+ Nuevo sprint», «+ Nuevo estudio») y lo trae a la vista.
    document.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-abrir-detalle]');
      if (!b) return;
      var d = document.getElementById(b.dataset.abrirDetalle);
      if (!d) return;
      d.open = true;
      d.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add templates/cliente.html tests/test_base_visual.py
git commit -m "Base visual: sin título grande del proyecto; pestañas responden al # y vuelven arriba"
```

### Task 2: CSS — campos, botones, desplegables, encabezado y estado vacío

**Files:**
- Modify: `static/style.css` (bloque nuevo al final)
- Test: `tests/test_base_visual.py`

**Interfaces:**
- Produces: clases `.panel-cabecera` (fila), `.panel-cabecera-desc`, `.panel-cabecera-acciones`, `.estado-vacio`, `.estado-vacio-titulo`, `.estado-vacio-texto` (las usan las Tasks 3 y 4).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
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
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py -k "estilo or boton or clases"`
Expected: 3 FAIL («falta el bloque…»).

- [ ] **Step 3: Implementar** — agregar al final de `static/style.css`:

```css
/* ============================================================
   Base visual común (2026-09-25) — spec:
   docs/superpowers/specs/2026-09-25-base-visual-comun-design.md
   Va al final a propósito: es la fuente de verdad de campos, botones,
   encabezado de pestaña y estado vacío, y pisa reglas viejas por orden
   sin tocarlas una por una.
   ============================================================ */

/* Campos: todo lo que se escribe o se elige se ve igual (el estilo de
   arriba solo cubría text/number/password: 42 campos quedaban nativos). */
input:not([type]), input[type="email"], input[type="url"], input[type="search"], input[type="tel"],
input[type="date"], input[type="time"], input[type="datetime-local"], input[type="month"] {
  width: 100%; background: var(--panel-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text); padding: .6rem .75rem; font: inherit; font-size: .87rem;
  transition: border-color .15s, box-shadow .15s;
}
input[type="file"] { width: auto; max-width: 100%; }
.campo-label { text-transform: none; letter-spacing: 0; font-size: .82rem; color: var(--text); }
fieldset { border: 1px solid var(--border); border-radius: var(--radius); padding: .9rem 1.1rem 1.1rem; margin: 0 0 1rem; min-width: 0; }
legend { font-family: var(--font-display); font-size: .95rem; font-weight: 600; color: var(--text); padding: 0 .4rem; }

/* Botones: secundario por defecto; las variantes van DESPUÉS con la misma
   especificidad para ganarle. */
button:not([class]), .btn, .btn-secondary, .btn-sm, .btn-xs {
  background: var(--panel); color: var(--text); border: 1px solid var(--border);
}
button:not([class]):hover:not(:disabled), .btn:hover:not(:disabled), .btn-secondary:hover:not(:disabled),
.btn-sm:hover:not(:disabled), .btn-xs:hover:not(:disabled) { border-color: var(--muted-2); }
a.btn, a.btn-sm, a.btn-xs, a.btn-generar, a.btn-guardar, a.btn-secondary, a.btn-primary {
  display: inline-flex; align-items: center; text-decoration: none;
}
.btn-generar, .btn-aprobar, .btn-primary, .btn.primario {
  background: var(--accent-grad); color: #fff; border: 1px solid transparent; box-shadow: var(--shadow-soft);
}
.btn-generar:hover:not(:disabled), .btn-aprobar:hover:not(:disabled), .btn-primary:hover:not(:disabled),
.btn.primario:hover:not(:disabled) { filter: brightness(1.08); box-shadow: var(--shadow-glow); border-color: transparent; }
.btn-guardar { background: var(--panel); color: var(--text); border: 1px solid var(--border); }
.btn-rechazar { background: transparent; color: var(--error); border: 1px solid rgba(196, 63, 90, .35); }
.btn-rechazar:hover:not(:disabled) { background: rgba(196, 63, 90, .1); border-color: rgba(196, 63, 90, .35); }
.btn-peligro, .btn-eliminar-producto { background: rgba(196, 63, 90, .1); color: var(--error); border: 1px solid rgba(196, 63, 90, .4); }
.btn-peligro:hover:not(:disabled), .btn-eliminar-producto:hover:not(:disabled) { background: rgba(196, 63, 90, .2); border-color: rgba(196, 63, 90, .4); }

/* Desplegables: fila clicable con flecha (antes «+ Nuevo sprint» parecía
   una caja de texto). Los que ya traen .idea-chevron no llevan otra. */
summary { cursor: pointer; }
.swap-card-resumen { font-weight: 600; }
.swap-card-resumen:hover { color: var(--accent); }
.swap-card-resumen:not(:has(.idea-chevron))::after {
  content: ""; margin-left: auto; flex: none; width: .45rem; height: .45rem;
  border-right: 2px solid var(--muted-2); border-bottom: 2px solid var(--muted-2);
  transform: rotate(-45deg); transition: transform .15s;
}
.swap-card[open] > .swap-card-resumen:not(:has(.idea-chevron))::after { transform: rotate(45deg); }
#nuevo-sprint > summary, #nuevo-estudio > summary { color: var(--accent); }

/* Encabezado de pestaña: título grande, una línea, acciones a la derecha. */
.panel-cabecera {
  display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: .8rem 1.5rem;
  margin: 0 0 1.6rem; padding-bottom: 1.2rem; border-bottom: 1px solid var(--border);
}
.panel-cabecera > :first-child { flex: 1 1 24rem; min-width: 0; }
.panel-cabecera h2 {
  display: block; margin: 0 0 .35rem; font-size: 1.6rem; font-weight: 700; color: var(--text);
  text-transform: none; letter-spacing: -0.015em;
}
.panel-cabecera h2::before { display: none; }
.panel-cabecera-desc { margin: 0; color: var(--muted); font-size: .9rem; line-height: 1.55; max-width: 72ch; }
.panel-cabecera-desc + .panel-cabecera-desc { margin-top: .4rem; }
.panel-cabecera-acciones { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; flex: 0 0 auto; }

/* Estado vacío: un título, una línea y (si aplica) el botón para empezar. */
.estado-vacio {
  display: flex; flex-direction: column; align-items: center; gap: .5rem; text-align: center;
  margin: .5rem 0 1.2rem; padding: 2rem 1.5rem; border: 1px dashed var(--border); border-radius: var(--radius);
  background: var(--bg);
}
.estado-vacio-titulo { margin: 0; font-family: var(--font-display); font-size: 1.05rem; font-weight: 600; color: var(--text); }
.estado-vacio-texto { margin: 0; max-width: 52ch; color: var(--muted); font-size: .88rem; line-height: 1.5; }
.estado-vacio .btn-generar, .estado-vacio .btn-sm { margin-top: .5rem; }
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add static/style.css tests/test_base_visual.py
git commit -m "Base visual: campos, botones, desplegables, encabezado de pestaña y estado vacío en un solo bloque de CSS"
```

### Task 3: Encabezado común en las 8 pestañas

**Files:**
- Modify: `templates/_tab_tablero.html`, `_tab_nicho.html`, `_tab_referentes.html`, `_tab_experimentos.html`, `_tab_sprints.html` (ya tienen `.panel-cabecera`), `_tab_flowplus.html`, `_tab_catalogo.html`, `_tab_settings.html` (no lo tienen)
- Test: `tests/test_base_visual.py`

**Interfaces:**
- Consumes: `.panel-cabecera`, `.panel-cabecera-desc`, `.panel-cabecera-acciones` (Task 2); `data-abrir-detalle` (Task 1).

- [ ] **Step 1: Escribir la prueba que falla**

```python
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
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py -k encabezado`
Expected: FAIL en `creativeflowplus` o `panel-cabecera-desc`.

- [ ] **Step 3: Implementar** — marcado por pestaña (el texto de cada descripción se conserva tal cual):

`_tab_tablero.html`: dentro del bloque `tb-cabecera`, `<p class="vacio">` → `<p class="panel-cabecera-desc">`, y el enlace CSV dentro de `<div class="panel-cabecera-acciones">…</div>`.

`_tab_nicho.html`:
```html
<div class="panel-cabecera">
  <div>
    <h2>Nicho</h2>
    <p class="panel-cabecera-desc">Un estudio recoge comentarios reales … (texto actual)</p>
  </div>
  <div class="panel-cabecera-acciones">
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-estudio">+ Nuevo estudio</button>
  </div>
</div>
```

`_tab_referentes.html`: envolver `h2` + descripción en `<div>`, `vacio` → `panel-cabecera-desc`, y mover los dos botones de `<p class="acciones">` a `<div class="panel-cabecera-acciones">` dentro de la cabecera (mismos `id`, clases y `data-recrear-abrir`); borrar el `<p class="acciones">` vacío.

`_tab_experimentos.html`: envolver en `<div>`, las dos `<p class="vacio">` → `panel-cabecera-desc`.

`_tab_sprints.html`: como Nicho, con `<button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-sprint">+ Nuevo sprint</button>`.

`_tab_flowplus.html` (arriba de `.crear-modos`):
```html
<div class="panel-cabecera">
  <div>
    <h2>Crear</h2>
    <p class="panel-cabecera-desc">Videos e imágenes desde tus referencias, o cambia el producto de una foto o video. Nada se cobra hasta que pulses «Generar».</p>
  </div>
</div>
```

`_tab_catalogo.html`: el párrafo inicial pasa a ser la descripción:
```html
<div class="panel-cabecera">
  <div>
    <h2>Catálogo</h2>
    <p class="panel-cabecera-desc">Todo lo que la IA debe reproducir <strong>exacto</strong>: … (texto actual)</p>
  </div>
</div>
```

`_tab_settings.html` (arriba de `<h2 id="config-puesta-a-punto">`):
```html
<div class="panel-cabecera">
  <div>
    <h2>Configuración</h2>
    <p class="panel-cabecera-desc">Llaves y conexiones del proyecto, tu cuenta, tiendas, canales y gasto.</p>
  </div>
</div>
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py tests/test_rutas_referentes.py`
Expected: todo passed.

- [ ] **Step 5: Commit**

```bash
git add templates/_tab_*.html tests/test_base_visual.py
git commit -m "Base visual: encabezado común (título, descripción, acciones) en las 8 pestañas"
```

### Task 4: Estados vacíos con acción

**Files:**
- Modify: `templates/_tab_nicho.html`, `_tab_referentes.html`, `_tab_sprints.html`, `_tab_experimentos.html`
- Test: `tests/test_base_visual.py`

**Interfaces:**
- Consumes: `.estado-vacio*` (Task 2), `data-abrir-detalle` y `hashchange` (Task 1).

- [ ] **Step 1: Escribir la prueba que falla**

```python
def test_estados_vacios_con_accion(app):
    html = _pagina(app)
    sp, ni, rf, ex = (_pestana(html, t) for t in ("sprints", "nicho", "referentes", "experimentos"))
    assert 'class="estado-vacio"' in sp and sp.count('data-abrir-detalle="nuevo-sprint"') == 2
    assert 'class="estado-vacio"' in ni and ni.count('data-abrir-detalle="nuevo-estudio"') == 2
    assert 'class="estado-vacio"' in rf and "Todavía no hay referentes" in rf
    assert 'class="estado-vacio"' in ex and 'href="#creativeflowplus"' in ex
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py -k vacios`
Expected: FAIL (no hay `estado-vacio`).

- [ ] **Step 3: Implementar**

`_tab_sprints.html` — el `{% else %}` del `for`:
```html
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay sprints</p>
    <p class="estado-vacio-texto">Necesitas al menos una persona, un producto en el catálogo y una temporada.</p>
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-sprint">+ Nuevo sprint</button>
  </div>
```

`_tab_nicho.html` — el `{% else %}` del `for`:
```html
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay estudios</p>
    <p class="estado-vacio-texto">Con {{ min_comentarios_nicho }} comentarios pegados a mano ya salen avatares.</p>
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-estudio">+ Nuevo estudio</button>
  </div>
```

`_tab_referentes.html` — el `{% if not ref_opciones.total %}`:
```html
<div class="estado-vacio">
  <p class="estado-vacio-titulo">Todavía no hay referentes</p>
  <p class="estado-vacio-texto">Creatv importa la biblioteca inicial desde el panel de administrador; también puedes traer anuncios de una marca o palabra clave.</p>
  <button type="button" class="btn-generar btn-sm" data-recrear-abrir="{{ url_for('referentes.traer_form', cliente=cliente) }}">Traer referentes</button>
</div>
```

`_tab_experimentos.html` — el `{% if not elegibles_exp %}`:
```html
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay piezas para probar</p>
    <p class="estado-vacio-texto">Genera un video o una imagen en Crear o en un sprint y vuelve aquí para probarlo en Meta.</p>
    <a class="btn-generar btn-sm" href="#creativeflowplus">Ir a Crear</a>
  </div>
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `venv/bin/python3 -m pytest -q tests/test_base_visual.py tests/test_rutas_referentes.py tests/test_rutas_nicho*.py tests/test_rutas_sprints*.py`
Expected: todo passed.

- [ ] **Step 5: Commit**

```bash
git add templates/_tab_*.html tests/test_base_visual.py
git commit -m "Base visual: estados vacíos con título, una línea y botón para empezar"
```

### Task 5: Verificación visual, suite completa, subir y desplegar

- [ ] **Step 1:** Suite completa: `venv/bin/python3 -m pytest -q -m "not slow"` → todo passed.
- [ ] **Step 2:** Lanzador local SIN llaves (nota «verificar-ui-sin-contrasena»: `app.run(..., load_dotenv=False)`, `dotenv.load_dotenv` parcheado, entorno sin llaves; comprobar en Configuración que todas digan «falta») apuntando a ESTE worktree. Recorrer las 8 pestañas a 1280×800 y 375×812: encabezados, campos (Nicho «Nombre», fechas de Sprints, link de Crear), botones (principal con letra blanca), «+ Nuevo sprint» desde el estado vacío, un `#settings` desde el Tablero, volver arriba al cambiar de pestaña, «Mis barridos»/«Traer referentes». Arreglar lo que se vea mal y volver a correr la suite.
- [ ] **Step 3:** Commit de ajustes; `git fetch origin` y, si `main` se movió, `git rebase origin/main`; `git push origin HEAD:main`.
- [ ] **Step 4:** Desplegar SOLO la web (plantillas + CSS): respaldo de la base, `git pull --ff-only`, `systemctl restart iaplusyou` (como root), `curl` a `/login` = 200 y `?v=` nuevo en `style.css`.
