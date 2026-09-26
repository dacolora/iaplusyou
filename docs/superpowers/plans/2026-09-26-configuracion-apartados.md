# Configuración en apartados + quitar «Nueva idea» — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configuración muestra un apartado a la vez (Puesta a punto*, Conexiones, Marca, Generación, Cuenta y avisos, Gasto) con Meta a todo el ancho en Conexiones; Crear deja de mostrar «Nueva idea».

**Architecture:** `_tab_settings.html` se reordena en `<section class="config-apartado">` sin cambiar el HTML de adentro; la tarjeta de llave pasa a un macro usado en Puesta a punto (sin Meta) y en Conexiones (solo Meta). Un script chico en la misma plantilla muestra/oculta y expone `window.irAConfig(id)`.

**Tech Stack:** Jinja2, CSS, JS sin dependencias, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-configuracion-apartados-design.md`

## Global Constraints

- Ids, formularios y textos de adentro no cambian (`#llave-<id>`, `#config-gasto`, `#config-tienda`, `#config-pixel`, `#config-canales-organicos`, `#config-correo`, `#config-cuenta`, `#config-puesta-a-punto`).
- El cliente nunca ve nombres de variables, `.env`, «no se escriben desde aquí», «Cómo conseguirla» ni valores de llaves.
- Pruebas: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -m "not slow"`.

---

### Task 1: Crear sin «Nueva idea»

**Files:** Modify `templates/_tab_flowplus.html`; Test `tests/test_configuracion_apartados.py` (nuevo)

- [ ] **Step 1: Prueba que falla**

```python
"""Parte 3a de la mejora visual (spec 2026-09-26): Configuración en apartados y Crear sin «Nueva idea»."""
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _pestana(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    sig = html.find('<section id="tab-', ini + 10)
    return html[ini:sig if sig > 0 else len(html)]


def test_crear_ya_no_muestra_nueva_idea(app):
    crear = _pestana(app["c"].get("/cliente/acme").data.decode(), "creativeflowplus")
    assert "<h2>Nueva idea</h2>" not in crear and "nueva_idea" not in crear
```

- [ ] **Step 2:** correr → FAIL.
- [ ] **Step 3:** en `_tab_flowplus.html` borrar

```html

  <hr style="margin:2.5rem 0 1rem; border:0; border-top:1px solid var(--border);">

  {% include "_seccion_ideas.html" %}
```

- [ ] **Step 4:** correr → PASS. **Step 5:** commit «Crear: fuera el flujo viejo «Nueva idea» (Higgsfield)».

### Task 2: Configuración en apartados

**Files:** Modify `templates/_tab_settings.html`, `templates/_sidebar.html` (onclick de «Este mes»), `static/style.css`; Test `tests/test_configuracion_apartados.py`, `tests/test_rutas_configuracion.py` (la prueba del cliente mira Conexiones)

**Interfaces:**
- Produces: `window.irAConfig(id)`; secciones `#config-ap-puesta|conexiones|marca|generacion|cuenta|gasto`.

- [ ] **Step 1: Pruebas que fallan**

```python
from tests.test_rutas_configuracion import _cliente_rol_cliente  # noqa: E402


def _config(html):
    return _pestana(html, "settings")


def _apartado(cfg, clave):
    ini = cfg.index(f'id="config-ap-{clave}"')
    fin = cfg.find('class="config-apartado"', ini + 10)
    return cfg[ini:fin if fin > 0 else len(cfg)]


def test_admin_ve_seis_apartados_y_meta_en_conexiones(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    for clave in ("puesta", "conexiones", "marca", "generacion", "cuenta", "gasto"):
        assert f'data-apartado="{clave}"' in cfg, clave
        assert f'id="config-ap-{clave}"' in cfg, clave
    assert 'id="llave-meta"' in _apartado(cfg, "conexiones")
    assert 'id="llave-meta"' not in _apartado(cfg, "puesta")
    assert 'id="llave-anthropic"' in _apartado(cfg, "puesta")
    assert 'id="config-gasto"' in _apartado(cfg, "gasto")
    assert 'id="config-tienda"' in _apartado(cfg, "conexiones")
    assert "window.irAConfig" in cfg


def test_cliente_no_ve_puesta_a_punto(app):
    cfg = _config(_cliente_rol_cliente(app["dashboard"]).get("/cliente/acme").data.decode())
    assert 'id="config-ap-puesta"' not in cfg and 'data-apartado="puesta"' not in cfg
    assert 'id="llave-meta"' in _apartado(cfg, "conexiones")


def test_este_mes_de_la_barra_lateral_abre_gasto(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert "irAConfig('config-gasto')" in html
```

y en `tests/test_rutas_configuracion.py`, `_puesta_a_punto` y la prueba del cliente miran Conexiones:

```python
def _puesta_a_punto(cfg):
    """Lo que el cliente ve de las llaves: desde 2026-09-26 (Configuración en
    apartados) la tarjeta de Meta vive en «Conexiones»; el cliente no tiene
    «Puesta a punto»."""
    ini = cfg.index('id="config-ap-conexiones"')
    return cfg[ini:cfg.index('id="config-tienda"', ini)]
```

(y en la prueba, `puesta.split('class="llaves-tarjetas"')[0]` sigue siendo la intro de Conexiones).

- [ ] **Step 2:** correr → FAIL.
- [ ] **Step 3: Implementar**

Al principio de `_tab_settings.html` (después de `{% set es_admin … %}`), el macro con el `<article class="llave-tarjeta …">…</article>` actual tal cual:

```jinja
{% macro tarjeta_llave(l, es_admin) %}
  <article class="llave-tarjeta llave-{{ l.estado }}" id="llave-{{ l.id }}"> … (cuerpo actual sin cambios) … </article>
{% endmacro %}
```

Después del encabezado, las pastillas:

```html
<nav class="cat-tabs config-apartados" role="tablist" aria-label="Apartados de Configuración">
  {% if es_admin %}<button type="button" class="cat-tab" data-apartado="puesta">Puesta a punto</button>{% endif %}
  <button type="button" class="cat-tab" data-apartado="conexiones">Conexiones</button>
  <button type="button" class="cat-tab" data-apartado="marca">Marca</button>
  <button type="button" class="cat-tab" data-apartado="generacion">Generación</button>
  <button type="button" class="cat-tab" data-apartado="cuenta">Cuenta y avisos</button>
  <button type="button" class="cat-tab" data-apartado="gasto">Gasto</button>
</nav>
```

Y los bloques actuales, sin tocar su contenido, dentro de:

```html
{% if es_admin %}
<section class="config-apartado" id="config-ap-puesta" data-apartado="puesta">
  <h2 id="config-puesta-a-punto">Puesta a punto</h2>
  <p class="vacio" style="padding-top:0;">(párrafo del admin actual)</p>
  <div class="llaves-tarjetas">
    {% for l in llaves if l.id != "meta" %}{{ tarjeta_llave(l, es_admin) }}{% endfor %}
  </div>
</section>
{% endif %}
<section class="config-apartado" id="config-ap-conexiones" data-apartado="conexiones">
  <h2 id="config-meta">Meta</h2>
  <p class="vacio" style="padding-top:0;">Para lanzar anuncios y publicar en tu Página de Facebook e Instagram. El resto de los servicios (guiones, imagen y video, voz y música, almacenamiento, correo) los pone Creatv en el servidor.</p>
  <div class="llaves-tarjetas llaves-tarjetas-ancha">
    {% for l in llaves if l.id == "meta" %}{{ tarjeta_llave(l, es_admin) }}{% endfor %}
  </div>
  … bloque «Conectar tu tienda» … bloque «Pixel de Meta» … bloque «Canales orgánicos» (con el enlace a las reglas) …
</section>
<section class="config-apartado" id="config-ap-marca" data-apartado="marca"> … «Nombre del proyecto» … «Logos oficiales» … {% include "_seccion_marca.html" %} </section>
<section class="config-apartado" id="config-ap-generacion" data-apartado="generacion"> … «Modelos por defecto — Cambiar producto» … «— FlowPlus» … «Sonido al crear» … {% include "_comparacion_modelos.html" %} </section>
<section class="config-apartado" id="config-ap-cuenta" data-apartado="cuenta"> … «Cuenta» … «Correo de avisos» … </section>
<section class="config-apartado" id="config-ap-gasto" data-apartado="gasto"> … «Gasto» (#config-gasto, por tipo, historial) … {% if admin %} informe {% endif %} </section>
```

(los `<hr>` que separaban secciones se quitan: ahora las separa el apartado).

Script al final de la plantilla:

```html
<script>
  (function () {
    var raiz = document.getElementById('tab-settings');
    if (!raiz) return;
    var botones = raiz.querySelectorAll('.config-apartados [data-apartado]');
    var apartados = raiz.querySelectorAll('section.config-apartado');
    var CLAVE = 'config-apartado-{{ cliente }}';
    function mostrar(ap) {
      var existe = Array.prototype.some.call(apartados, function (s) { return s.dataset.apartado === ap; });
      if (!existe) return false;
      apartados.forEach(function (s) { s.hidden = s.dataset.apartado !== ap; });
      botones.forEach(function (b) { b.classList.toggle('activo', b.dataset.apartado === ap); });
      try { localStorage.setItem(CLAVE, ap); } catch (e) {}
      return true;
    }
    // Abre el apartado que contiene `id` y lo trae a la vista (barra lateral
    // «Este mes», enlaces #llave-meta, #config-tienda…).
    window.irAConfig = function (id) {
      var el = document.getElementById(id);
      var ap = el && el.closest('section.config-apartado');
      if (!ap) return;
      mostrar(ap.dataset.apartado);
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    botones.forEach(function (b) { b.addEventListener('click', function () { mostrar(b.dataset.apartado); }); });
    var guardado = null;
    try { guardado = localStorage.getItem(CLAVE); } catch (e) {}
    if (!mostrar(guardado)) mostrar('{{ "puesta" if es_admin else "conexiones" }}');
    var destino = location.hash.slice(1).split('?')[0];
    if (destino && destino !== 'settings') {
      var el = document.getElementById(destino);
      if (el && el.closest('section.config-apartado')) window.irAConfig(destino);
    }
    window.addEventListener('hashchange', function () {
      var d = location.hash.slice(1).split('?')[0];
      var e = d && document.getElementById(d);
      if (e && e.closest('section.config-apartado')) window.irAConfig(d);
    });
  })();
</script>
```

`_sidebar.html` (enlace «Este mes»): `onclick="var b = document.querySelector('.sidebar-item[data-tab=settings]'); if (b) { b.click(); if (window.irAConfig) irAConfig('config-gasto'); return false; }"`.

CSS (al final del bloque base visual):

```css
/* Configuración en apartados (spec 2026-09-26-configuracion-apartados). */
.config-apartados { margin: 0 0 1.4rem; }
.config-apartado > h2:first-child { margin-top: .4rem; }
.llaves-tarjetas-ancha { grid-template-columns: minmax(0, 1fr); }
```

- [ ] **Step 4:** correr `tests/test_configuracion_apartados.py tests/test_rutas_configuracion.py` → todo passed.
- [ ] **Step 5:** commit «Configuración: un apartado a la vez (Conexiones con Meta a todo el ancho, Marca, Generación, Cuenta y avisos, Gasto; Puesta a punto solo admin)».

### Task 3: Verificación, subir y desplegar

- [ ] Suite completa en verde.
- [ ] App local sin llaves, admin y cliente, 1280×800 y 375×812: cada apartado; el recordado; `#llave-meta` desde Pixel; «Este mes» de la barra lateral abre Gasto; guardar «Nombre del proyecto» vuelve a Marca; Crear sin «Nueva idea».
- [ ] `git fetch`/rebase, `git push origin HEAD:main`, desplegar solo la web.
