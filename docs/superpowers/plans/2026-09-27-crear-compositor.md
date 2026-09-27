# Crear como compositor — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rehacer el formulario «Desde referencias» de Crear como compositor (tarjeta con referencias + texto, y una barra de pastillas con menús), sin cambiar lo que el servidor recibe, y cerrar el envío accidental con Enter.

**Architecture:** Solo plantillas, JavaScript en la página y CSS. La tarjeta se dibuja en dos mitades: arriba la bandeja (fuera de `#form-flowplus`, porque lleva sus propios `<form>`) y abajo el formulario. Los radios y selects de siempre viven dentro de los menús de cada pastilla (los selects, ocultos, siguen siendo la fuente de verdad), y el JavaScript existente sigue leyéndolos. Subir y pegar un link usan formularios vacíos de afuera, con el atributo `form=`.

**Tech Stack:** Jinja2 (Flask), JavaScript ES5 en línea (mismo estilo que el archivo: `var`, `function`), CSS con los tokens de `:root`, pytest sobre el HTML servido.

**Spec:** `docs/superpowers/specs/2026-09-27-crear-compositor-design.md`

## Global Constraints

- Cero cambios en Python (`dashboard.py`, rutas, precios, modelos). El POST a `cf_crear_video` recibe los mismos `name`: `bandeja_vista`, `ref_ids`, `productos_catalogo`, `accion_central`, `tipo`, `modelo_video`, `modelo_imagen`, `modelo`, `duracion_objetivo`, `aspect_ratio`, `aspect_ratio_imagen`, `con_sonido`, `sonido`, `musica_estilo`, `musica_inicio_s`, `calidad`, `modo_prompt`.
- El texto de la persona va tal cual. «Crear super prompt con IA (gratis)» (`modo_prompt=director`) sigue siendo opcional y va DESPUÉS de «Generar» (`modo_prompt=directo`) en el HTML.
- La fórmula del precio no cambia (la de `refrescar()`).
- Nada genera sin el clic en «Generar». Enter en un `INPUT` cuyo dueño es `#form-flowplus` no envía.
- HTML nuevo sin `style=""`. CSS solo con tokens de `:root`, sin colores claros escritos a mano (`tests/test_modo_oscuro.py`).
- Se conservan los ids y textos que miran las pruebas: `fp-calidad`, `name="calidad" value="borrador"`, `<option value="8" selected>8 s</option>`, `fp-duracion-larga`, «sus segundos más los del resultado no pueden pasar de 30», los `data-formatos`/`data-max-duracion`/`data-recargo` de los radios, `fp-con-sonido`, `fp-sugerir-sonido`, `<option value="lujo" selected>`, `mm-panel`, `fp-musica-inicio`, `name="musica_inicio_s"`, `name="ref_ids" value="…" form="form-flowplus"`, `'Generar imagen'` en el JS y «Crear super prompt con IA (gratis)».
- En la rama `crear-compositor` (worktree `.claude/worktrees/crear-compositor`). Pruebas: `venv/bin/python3 -m pytest -q` desde la carpeta principal del venv (`/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).

---

### Task 1: Contrato del formulario y guardián de Enter

**Files:**
- Create: `tests/test_crear_compositor.py`
- Modify: `templates/_tab_creativeflowplus.html` (tercer `<script>`, antes de `engancharBandeja();`)

**Interfaces:**
- Produces: `_html(app)`, `_crear(html)`, `_form(crear)` (helpers del archivo de pruebas, los usan las Tareas 2 y 3).

- [ ] **Step 1: Pruebas que fallan (contrato + Enter)**

```python
"""Crear como compositor (spec docs/superpowers/specs/2026-09-27-crear-compositor-design.md):
el formulario cambia de forma, no de contrato — el servidor recibe los mismos
campos — y Enter en un campo de una línea ya no genera (ni cobra) un video."""
import re

from tests.test_rutas_crear_director import app  # noqa: F401  (fixture: admin en /cliente/acme)

CAMPOS = ["bandeja_vista", "accion_central", "tipo", "modelo_video", "modelo_imagen", "modelo",
          "duracion_objetivo", "aspect_ratio", "aspect_ratio_imagen", "con_sonido", "sonido",
          "musica_estilo", "musica_inicio_s", "calidad", "modo_prompt"]


def _html(app):
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def _crear(html):
    return html[html.index('id="tab-creativeflowplus"'):html.index('id="tab-sprints"')]


def _form(crear):
    ini = crear.rindex("<form", 0, crear.index('id="form-flowplus"'))
    return crear[ini:crear.index("</form>", ini)]


def test_el_formulario_manda_los_mismos_campos(app):
    form = _form(_crear(_html(app)))
    for campo in CAMPOS:
        assert f'name="{campo}"' in form, campo


def test_enter_en_un_campo_no_envia_el_formulario_de_crear(app):
    """Antes, Enter en «Sonido de la escena» hacía el envío implícito con el
    primer botón (#fp-generar, modo_prompt=directo): generaba y cobraba."""
    html = _html(app)
    js = html[html.index("form.addEventListener('keydown'"):]
    assert "e.key !== 'Enter'" in js[:300]
    assert "e.target.form === form" in js[:400] and "e.preventDefault()" in js[:400]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_crear_compositor.py`
Expected: `test_el_formulario_manda_los_mismos_campos` PASA (el contrato ya se cumple hoy: sirve de red para las Tareas 2 y 3) y `test_enter_…` FALLA con `ValueError: substring not found`.

- [ ] **Step 3: El guardián, en el tercer `<script>`, justo antes de `engancharBandeja();`**

```javascript
    // Enter en un campo de una línea NO envía: «Generar» cobra y solo se lanza
    // con su botón (antes, Enter en «Sonido de la escena» generaba el video).
    // El link (#fp-form-link) sí se agrega con Enter: su dueño es otro
    // formulario y no gasta.
    form.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing) return;
      if (e.target.tagName === 'INPUT' && e.target.form === form) e.preventDefault();
    });
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_crear_compositor.py`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_crear_compositor.py templates/_tab_creativeflowplus.html
git commit -m "Crear: Enter en un campo ya no genera el video (y red del contrato del formulario)"
```

---

### Task 2: El compositor (marcado, selector en diálogo y bandeja)

**Files:**
- Modify: `templates/_tab_creativeflowplus.html:5-160` (intro + referencias + `#form-flowplus`; se conserva el include de `_selector_productos_nuevo.html` de después)
- Modify: `templates/_flowplus_bandeja.html` (todo)
- Modify: `templates/_selector_productos.html:16-19` y cierre (modo `sel_dialogo`)
- Modify: `templates/_selector_productos_nuevo.html` (script: resumen y «+ Nuevo producto» en modo diálogo)
- Modify: `tests/test_rutas_crear_director.py::test_formulario_ofrece_generar_y_armar_prompt` (la intro se quita a propósito)
- Modify: `tests/test_rutas_crear_sonido.py::test_formulario_de_crear_trae_sonido_musica_y_sugerir` (el interruptor pone el texto después de un `<span>`)
- Test: `tests/test_crear_compositor.py`

**Interfaces:**
- Produces (ids que usa la Tarea 3): `#crear-comp`, `#fp-catalogo-elegidos`, `#fp-subida` (con `hidden`), `#fp-pill-tipo|modelo|duracion|formato|sonido|musica`, `[data-menu="<id>"]` + `.crear-menu#<id>`, `#fp-menu-mas`, `#fp-abrir-link`, `#fp-link-caja`, `#fp-abrir-catalogo`, `dialog#fp-catalogo` con `[data-cerrar-catalogo]`, `[data-fichas-de="<id del select>"]`, `#fp-musica-opciones`, `#fp-precio`, `#fp-pie-logos`, `#fp-calidad-wrap`, `[data-solo-video]` / `[data-solo-imagen]`, `#crear-velo`. Los radios de modelo llevan `data-nombre`.

- [ ] **Step 1: Pruebas de estructura que fallan** (agregar a `tests/test_crear_compositor.py`)

```python
def test_nada_anidado_y_subir_link_con_sus_formularios_de_afuera(app):
    crear = _crear(_html(app))
    form = _form(crear)
    assert form.count("<form") == 1
    assert 'id="fp-input-archivos" form="fp-form-subir"' in form
    assert 'name="link" form="fp-form-link"' in form
    antes = crear[:crear.index('id="form-flowplus"')]
    assert 'id="fp-form-subir"' in antes and 'id="fp-form-link"' in antes and 'id="fp-bandeja-wrap"' in antes


def test_seis_pastillas_el_mas_y_el_catalogo_en_dialogo(app):
    form = _form(_crear(_html(app)))
    for menu in ("fp-menu-mas", "fp-menu-tipo", "fp-menu-modelo", "fp-menu-duracion",
                 "fp-menu-formato", "fp-menu-sonido", "fp-menu-musica"):
        assert f'data-menu="{menu}"' in form and f'id="{menu}"' in form, menu
    assert '<dialog class="generado-modal crear-catalogo" id="fp-catalogo">' in form
    assert 'id="fp-precio"' in form


def test_generar_primero_y_super_prompt_como_ayuda(app):
    form = _form(_crear(_html(app)))
    assert form.index('id="fp-generar"') < form.index('id="fp-armar"')
    assert re.search(r'<button type="submit" class="crear-enlace" id="fp-armar" name="modo_prompt" value="director"', form)


def test_los_avisos_viven_en_su_menu_o_en_el_pie(app):
    crear = _crear(_html(app))
    assert "Dos caminos:" not in crear and "Una pieza por clic." not in crear
    duracion = crear[crear.index('id="fp-menu-duracion"'):crear.index('data-menu="fp-menu-formato"')]
    assert "sus segundos más los del resultado no pueden pasar de 30" in duracion and 'id="fp-duracion-larga"' in duracion
    modelo = crear[crear.index('id="fp-menu-modelo"'):crear.index('data-menu="fp-menu-duracion"')]
    assert 'id="fp-calidad"' in modelo and "Borrador a 480p" in modelo
    assert "Tu texto va tal cual al modelo" in crear


def test_cambiar_producto_sigue_con_su_desplegable(app):
    crear = _crear(_html(app))
    assert '<details class="comparacion-modelos selector-productos" id="sel-clone"' in crear
    assert '<div class="selector-productos selector-en-dialogo" id="sel-plus"' in crear
```

Run: `venv/bin/python3 -m pytest -q tests/test_crear_compositor.py` → las 5 nuevas FALLAN.

- [ ] **Step 2: Reemplazar las líneas 5-160 de `_tab_creativeflowplus.html`** (desde `<p class="vacio" style="padding-top:0;">` hasta el `</form>` de `#form-flowplus` inclusive) por:

```jinja
{# Formulario de Crear como compositor (spec 2026-09-27-crear-compositor-design.md).
   Una tarjeta en dos mitades: arriba la bandeja de referencias (FUERA de
   #form-flowplus porque lleva sus propios <form> de quitar/vaciar — los
   formularios no se anidan) y abajo el formulario: el texto y la barra de
   «pastillas». Cada pastilla abre un menú con los controles REALES (radios y
   selects de siempre), así que el servidor recibe los mismos campos. Subir y
   pegar un link usan los formularios vacíos de aquí abajo vía el atributo form=. #}
{% set total_catalogo = namespace(n=0) %}{% for cid, lista in activos_por_categoria.items() %}{% set total_catalogo.n = total_catalogo.n + (lista | length) %}{% endfor %}
<form method="post" action="{{ url_for('fp_subir_referencias', cliente=cliente) }}" enctype="multipart/form-data" id="fp-form-subir" hidden></form>
<form method="post" action="{{ url_for('fp_agregar_link', cliente=cliente) }}" id="fp-form-link" hidden></form>

<div class="crear-comp" id="crear-comp">
  <div class="crear-comp-arriba">
    <div id="fp-bandeja-wrap">
      {% include "_flowplus_bandeja.html" %}
    </div>
    <div class="crear-refs" id="fp-catalogo-elegidos" hidden></div>
    <div class="crear-subida" id="fp-subida" hidden>
      <div class="barra-progreso"><div class="barra-progreso-fill" id="fp-subida-barra"></div></div>
      <span id="fp-subida-texto">Subiendo…</span>
    </div>
  </div>

  <form method="post" action="{{ url_for('cf_crear_video', cliente=cliente) }}" id="form-flowplus" class="crear-comp-form">
    {# Con esto el servidor usa solo los `ref_ids` de la bandeja que ves (ver _flowplus_bandeja.html). #}
    <input type="hidden" name="bandeja_vista" value="1">
    <input type="hidden" name="modelo" id="fp-modelo">
    <div class="crear-comp-abajo">
      <div class="banco-prompts crear-etiquetas" id="fp-etiquetas"></div>
      <label class="crear-oculto-lector" for="fp-texto">Qué tiene que pasar</label>
      <textarea name="accion_central" id="fp-texto" rows="4" placeholder="Describe qué tiene que pasar. Ej.: @Imagen 1 es el producto; una niña lo descubre y salta de alegría, la cámara la sigue como en @Video 1"></textarea>
      <p class="campo-error" id="fp-texto-error" hidden>Escribe qué tiene que pasar en el video.</p>

      <div class="crear-barra">
        <div class="crear-pills">
          <div class="crear-pill-zona">
            <button type="button" class="crear-pill crear-mas" data-menu="fp-menu-mas" aria-expanded="false" aria-label="Agregar referencias">+</button>
            <div class="crear-menu" id="fp-menu-mas" hidden>
              <label class="crear-menu-item">
                <span class="crear-menu-ico" aria-hidden="true">⬆</span>
                <span><strong>Subir imágenes o videos</strong><small>JPG, PNG, WEBP, MP4 o MOV; también puedes arrastrarlos a la caja. Cada uno queda como @Imagen N / @Video N para nombrarlo en el texto.</small></span>
                <input type="file" name="referencias" id="fp-input-archivos" form="fp-form-subir" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm" multiple hidden>
              </label>
              <button type="button" class="crear-menu-item" id="fp-abrir-link">
                <span class="crear-menu-ico" aria-hidden="true">🔗</span>
                <span><strong>Pegar un link</strong><small>TikTok, Instagram, YouTube o TrendTrack: sirve de referencia de movimiento y estructura; no se publica ni se copia tal cual.</small></span>
              </button>
              <div class="crear-menu-fila" id="fp-link-caja" hidden>
                <input type="url" name="link" form="fp-form-link" placeholder="https://…" required>
                <button type="submit" class="btn-sm" form="fp-form-link">Agregar</button>
              </div>
              <button type="button" class="crear-menu-item" id="fp-abrir-catalogo">
                <span class="crear-menu-ico" aria-hidden="true">▦</span>
                <span><strong>Del catálogo</strong><small>{{ total_catalogo.n }} productos, personajes y entornos, con buscador.</small></span>
              </button>
            </div>
          </div>

          <div class="crear-pill-zona">
            <button type="button" class="crear-pill" data-menu="fp-menu-tipo" aria-expanded="false" id="fp-pill-tipo">🎬 Video</button>
            <div class="crear-menu" id="fp-menu-tipo" hidden>
              <div class="crear-opciones" id="fp-tipo">
                <label class="crear-opcion"><input type="radio" name="tipo" value="video" checked><span><strong>Video</strong><small>Con el sonido de la escena, hasta 30 s</small></span></label>
                <label class="crear-opcion"><input type="radio" name="tipo" value="imagen"><span><strong>Imagen</strong><small>Una imagen fija en 2k</small></span></label>
              </div>
            </div>
          </div>

          <div class="crear-pill-zona">
            <button type="button" class="crear-pill" data-menu="fp-menu-modelo" aria-expanded="false" id="fp-pill-modelo">Modelo</button>
            <div class="crear-menu crear-menu-ancho" id="fp-menu-modelo" hidden>
              <div class="crear-opciones" data-solo-video>
                {% for id, m in modelos_flowplus_video.items() %}
                <label class="crear-opcion crear-modelo" title="{{ m.nota }}"><input type="radio" name="modelo_video" value="{{ id }}" data-nombre="{{ m.nombre }}" data-usd-seg="{{ m.usd_por_segundo_efectivo }}" data-recargo="{{ m.audio_nativo.recargo_usd_s }}" data-max="{{ m.max_referencias }}" data-min-duracion="{{ m.min_duracion }}" data-max-duracion="{{ m.max_duracion }}" data-formatos="{{ m.formatos | join(',') }}" data-formatos-texto="{{ (m.formatos_texto or m.formatos) | join(',') }}" {% if preferencias_flowplus.modelo_video == id %}checked{% endif %}><span><strong>{{ m.nombre }}</strong><small>hasta {{ m.max_referencias }} referencia{{ '' if m.max_referencias == 1 else 's' }} · {{ m.min_duracion }}–{{ m.max_duracion }} s</small></span><em>${{ "%.3f"|format(m.usd_por_segundo_efectivo) }}/s</em></label>
                {% endfor %}
              </div>
              <div class="crear-opciones" data-solo-imagen hidden>
                {% for id, m in modelos_flowplus_imagen.items() %}
                <label class="crear-opcion crear-modelo" title="{{ m.nota }}"><input type="radio" name="modelo_imagen" value="{{ id }}" data-nombre="{{ m.nombre }}" data-usd="{{ m.usd }}" data-max="{{ m.max_referencias }}" data-formatos="{{ m.formatos | join(',') }}" {% if preferencias_flowplus.modelo_imagen == id %}checked{% endif %}><span><strong>{{ m.nombre }}</strong><small>hasta {{ m.max_referencias }} referencias · 2k</small></span><em>${{ "%.3f"|format(m.usd) }}</em></label>
                {% endfor %}
              </div>
              <label class="crear-interruptor" id="fp-calidad-wrap" data-solo-video>
                <input type="checkbox" name="calidad" value="borrador" id="fp-calidad">
                <span><strong>Borrador a 480p</strong><small>Solo Wan 3.0, mitad de precio: para probar el prompt antes de la versión final.</small></span>
              </label>
              <p class="crear-nota" data-solo-video>Precios con el sonido de la escena incluido.</p>
            </div>
          </div>

          <div class="crear-pill-zona" data-solo-video>
            <button type="button" class="crear-pill" data-menu="fp-menu-duracion" aria-expanded="false" id="fp-pill-duracion">⏱ Duración</button>
            <div class="crear-menu" id="fp-menu-duracion" hidden>
              <p class="crear-menu-titulo">Duración</p>
              <div class="crear-fichas" data-fichas-de="fp-duracion"></div>
              <select name="duracion_objetivo" id="fp-duracion" hidden>
                {% for d in duraciones_crear %}
                <option value="{{ d }}"{% if d == preferencias_flowplus.duracion_defecto %} selected{% endif %}>{{ d }} s</option>
                {% endfor %}
              </select>
              <p class="crear-nota crear-nota-aviso" id="fp-duracion-larga" hidden>Los modelos rinden mejor hasta 15 s; para algo más largo, genera dos piezas y únelas después en la edición final.</p>
              <p class="crear-nota" id="fp-duracion-nota">Con videos de referencia (Wan 3.0), sus segundos más los del resultado no pueden pasar de 30.</p>
            </div>
          </div>

          <div class="crear-pill-zona">
            <button type="button" class="crear-pill" data-menu="fp-menu-formato" aria-expanded="false" id="fp-pill-formato">▯ Formato</button>
            <div class="crear-menu" id="fp-menu-formato" hidden>
              <p class="crear-menu-titulo">Formato</p>
              <div data-solo-video>
                <div class="crear-fichas" data-fichas-de="fp-formato-video"></div>
                <select name="aspect_ratio" id="fp-formato-video" hidden>
                  {% for f, nombre in formatos_nombres.items() %}
                  <option value="{{ f }}"{% if f == "9:16" %} selected{% endif %}>{{ nombre }}</option>
                  {% endfor %}
                </select>
                <p class="crear-nota" id="fp-formato-nota" hidden>Con una imagen de referencia este modelo no elige formato: sigue el de esa imagen.</p>
              </div>
              <div data-solo-imagen hidden>
                <div class="crear-fichas" data-fichas-de="fp-formato-imagen"></div>
                <select name="aspect_ratio_imagen" id="fp-formato-imagen" hidden>
                  {% for f, nombre in formatos_nombres.items() %}
                  <option value="{{ f }}"{% if f == "9:16" %} selected{% endif %}>{{ nombre }}</option>
                  {% endfor %}
                </select>
              </div>
            </div>
          </div>

          <div class="crear-pill-zona" data-solo-video>
            <button type="button" class="crear-pill" data-menu="fp-menu-sonido" aria-expanded="false" id="fp-pill-sonido">🔊 Sonido</button>
            <div class="crear-menu crear-menu-ancho" id="fp-menu-sonido" hidden>
              <label class="crear-interruptor">
                <input type="checkbox" name="con_sonido" value="si" id="fp-con-sonido" {% if preferencias_sonido.con_sonido %}checked{% endif %}>
                <span><strong>Sonido de la escena</strong><small>Audio nativo del modelo, sin diálogo ni música.</small></span>
              </label>
              <div class="crear-menu-fila">
                <input type="text" name="sonido" id="fp-sonido" maxlength="200" placeholder="ej. risas de niños, pasos sobre baldosa, respiración agitada al final">
                <button type="button" class="btn-sm" id="fp-sugerir-sonido" data-url="{{ url_for('fp_sugerir_sonido', cliente=cliente) }}">Sugerir</button>
              </div>
              <p class="crear-nota">Vacío = ambiente natural de la escena.</p>
            </div>
          </div>

          <div class="crear-pill-zona" data-solo-video>
            <button type="button" class="crear-pill" data-menu="fp-menu-musica" aria-expanded="false" id="fp-pill-musica">🎵 Música</button>
            <div class="crear-menu crear-menu-ancho crear-menu-der" id="fp-menu-musica" hidden>
              <select name="musica_estilo" id="fp-musica" hidden>
                <option value="" {% if not preferencias_sonido.musica_al_crear %}selected{% endif %}>ninguna</option>
                <optgroup label="Estilos IA">
                  {% for e in estilos_fe %}<option value="{{ e }}" {% if preferencias_sonido.musica_al_crear == e %}selected{% endif %}>{{ e }}</option>{% endfor %}
                </optgroup>
                <optgroup label="Mi música" class="mm-opciones"{% if not mi_musica %} hidden{% endif %}>
                  {% for c in mi_musica %}<option value="mat:{{ c.id }}" data-url="{{ c.url }}" data-duracion="{{ c.duracion_s }}">{{ c.nombre }}</option>{% endfor %}
                </optgroup>
              </select>
              <div class="crear-musica" id="fp-musica-opciones"></div>
              <div class="crear-musica-inicio" id="fp-musica-inicio-wrap" hidden>
                <audio id="fp-musica-audio" controls preload="none"></audio>
                <div class="crear-menu-fila">
                  <label class="crear-inicio">Empieza en el segundo <input type="number" name="musica_inicio_s" id="fp-musica-inicio" min="0" step="1" value="0"></label>
                  <button type="button" class="btn-sm" id="fp-musica-usar">Usar donde va el reproductor</button>
                </div>
              </div>
              <div class="crear-menu-sep"></div>
              <div id="mm-wrap">{% include "_mi_musica.html" %}</div>
            </div>
          </div>
        </div>

        <div class="crear-generar">
          <span class="crear-precio" id="fp-precio"></span>
          <button class="btn-generar" type="submit" id="fp-generar" name="modo_prompt" value="directo">Generar video</button>
        </div>
      </div>
    </div>

    <div class="crear-pie">
      {% set n_logos = logos | length %}
      <span id="fp-ayuda-boton">Tu texto va tal cual al modelo<span id="fp-pie-logos" hidden> · {% if n_logos > 1 %}se adjuntan tus {{ n_logos }} logos oficiales{% elif n_logos == 1 %}se adjunta tu logo oficial{% else %}sin logo oficial: súbelo en FlowSettings › Logos{% endif %}</span> · se cobra al generar.</span>
      {# Dos caminos (2026-09-21): «Generar» manda el texto de la persona tal cual y
         cobra al generar; «Crear super prompt» (director, gratis) es la ayuda para
         quien tiene una idea pero quiere que la IA arme los planos. Nunca obligatorio. #}
      <button type="submit" class="crear-enlace" id="fp-armar" name="modo_prompt" value="director" data-solo-video title="La IA arma el prompt por planos desde tu idea y las referencias. Revisas, editas y puedes regenerar antes de generar. No cuesta nada.">¿No sabes qué escribir? <strong>Crear super prompt con IA (gratis)</strong></button>
    </div>

    <dialog class="generado-modal crear-catalogo" id="fp-catalogo">
      <button type="button" class="generado-cerrar" data-cerrar-catalogo aria-label="Cerrar">×</button>
      <div class="modal-form ancho">
        <header class="modal-form-cab">
          <h3>Del catálogo</h3>
          <p>Marca lo que debe salir en la pieza: productos, personajes o entornos. Es opcional; si eliges un personaje, la escena lo lleva a él.</p>
        </header>
        {% with sel_id="plus", sel_campo="productos_catalogo", sel_modo="checkbox", sel_volver="creativeflowplus", sel_dialogo=True %}
        {% include "_selector_productos.html" %}
        {% endwith %}
        <footer class="modal-form-pie"><span></span><button type="button" class="btn-generar" data-cerrar-catalogo>Listo</button></footer>
      </div>
    </dialog>
  </form>
  <div class="crear-velo" id="crear-velo"></div>
</div>
```

- [ ] **Step 3: `_flowplus_bandeja.html` completo**

```jinja
{# Contenido dinámico de la bandeja de referencias de Crear. Se renderiza
   dentro de #fp-bandeja-wrap (mitad de arriba de la tarjeta del compositor,
   FUERA de #form-flowplus porque lleva sus propios <form> de quitar/vaciar) y
   se reemplaza por fetch tras subir/quitar/link, sin recargar la página. #}
{% if trabajo_link %}
<p class="crear-ref-aviso fp-link-descargando" data-job="{{ trabajo_link.job_id }}">⏳ Descargando el video del link… aparece aquí solo cuando termine.</p>
{% endif %}
{% if referencias_bandeja %}
<div class="crear-refs" id="fp-bandeja">
  {% for r in referencias_bandeja %}
  <figure class="crear-ref{% if r.tipo == 'video' %} es-video{% endif %}">
    <img src="{{ r.frame_url }}" alt="" title="{{ r.titulo or '' }}">
    <figcaption>{{ r.etiqueta }}{% if r.origen not in ('archivo', None) %} · {{ r.origen }}{% endif %}</figcaption>
    {# Lo que ves es lo que se usa: viaja con el formulario de Crear (la bandeja es del proyecto). #}
    <input type="hidden" name="ref_ids" value="{{ r.id }}" form="form-flowplus">
    <form method="post" action="{{ url_for('fp_quitar_referencia', cliente=cliente, rid=r.id) }}" data-fp="quitar"><button type="submit" class="crear-ref-quitar" title="Quitar" aria-label="Quitar {{ r.etiqueta }}">×</button></form>
  </figure>
  {% endfor %}
  <div class="crear-refs-acciones">
    <button type="button" class="crear-enlace" id="fp-describir">Describir con IA</button>
    <form method="post" action="{{ url_for('fp_vaciar_referencias', cliente=cliente) }}" data-fp="vaciar" data-confirm="¿Quitar todas las referencias?"><button type="submit" class="crear-enlace crear-enlace-gris">Quitar todas</button></form>
    <span class="crear-nota" id="fp-describir-estado"></span>
  </div>
</div>
{% else %}
<p class="crear-refs-vacio">Arrastra aquí imágenes o videos, o toca <strong>+</strong> para sumar referencias o elegir del catálogo. Son opcionales: sin nada, se genera solo con tu texto.</p>
{% endif %}
```

- [ ] **Step 4: `_selector_productos.html` en modo diálogo.** Reemplazar la apertura:

```jinja
{% if sel_dialogo %}
{# En un <dialog> (Crear › «+» › Del catálogo): sin <summary>; el resumen es un párrafo. #}
<div class="selector-productos selector-en-dialogo" id="sel-{{ sel_id }}" data-modo="{{ _modo }}">
  <p class="selector-resumen" id="sel-{{ sel_id }}-resumen">Nada elegido todavía.</p>
{% else %}
<details class="comparacion-modelos selector-productos" id="sel-{{ sel_id }}" data-modo="{{ _modo }}">
  <summary class="btn-guardar btn-sm" id="sel-{{ sel_id }}-resumen">
    {% if _modo == "radio" %}Elegir producto ({{ productos | length }}) →{% else %}Del catálogo (opcional, {{ _total.n }}) →{% endif %}
  </summary>
{% endif %}
```

y el cierre final `</details>` por `{% if sel_dialogo %}</div>{% else %}</details>{% endif %}`.

- [ ] **Step 5: `_selector_productos_nuevo.html`: el script sabe si está en un diálogo**

Después de `var textoInicial = resumen.textContent;`:

```javascript
    // Crear abre el catálogo en un <dialog> (sel_dialogo): el resumen no es un
    // <summary> y «+ Nuevo producto» (su formulario vive fuera del diálogo)
    // cierra el diálogo para que el formulario se vea.
    var enDialogo = detalle.tagName !== "DETAILS";
```

En `actualizarResumen`, la rama de checkbox queda:

```javascript
        var nombres = marcados.map(function (l) { return l.querySelector("input").dataset.nombre; });
        var lista = nombres.length <= 3 ? nombres.join(", ") : nombres.length + " productos";
        resumen.textContent = enDialogo ? "Elegidos: " + lista : lista + " — cambiar →";
```

y el botón nuevo:

```javascript
    nuevoBtn.addEventListener("click", function () {
      if (enDialogo && detalle.closest("dialog")) detalle.closest("dialog").close();
      nuevo.hidden = false;
      if (enDialogo) nuevo.scrollIntoView({block: "center"});
      nuevo.querySelector("input[name=nombre]").focus();
    });
```

- [ ] **Step 6: Ajustar las dos pruebas viejas que miraban marcado quitado a propósito**

En `tests/test_rutas_crear_director.py::test_formulario_ofrece_generar_y_armar_prompt`, reemplazar
`assert "<strong>Generar video</strong>" in crear      # la intro explica primero el camino directo`
por
`assert "Tu texto va tal cual al modelo" in crear      # el pie explica el camino directo (compositor 2026-09-27)`.

En `tests/test_rutas_crear_sonido.py::test_formulario_de_crear_trae_sonido_musica_y_sugerir`, reemplazar
`assert 'id="fp-con-sonido"' in html and ' checked> Sonido de la escena' in html`
por
`assert 'id="fp-con-sonido" checked>' in html and "<strong>Sonido de la escena</strong>" in html`.

- [ ] **Step 7: Correr las pruebas del formulario**

Run: `venv/bin/python3 -m pytest -q tests/test_crear_compositor.py tests/test_rutas_crear_director.py tests/test_rutas_crear_sonido.py tests/test_rutas_crear_formatos.py tests/test_rutas_mi_musica.py tests/test_bandeja_lo_que_ves.py tests/test_crear_solo_texto.py`
Expected: todo en verde.

- [ ] **Step 8: Commit**

```bash
git add templates/_tab_creativeflowplus.html templates/_flowplus_bandeja.html templates/_selector_productos.html templates/_selector_productos_nuevo.html tests/
git commit -m "Crear: el formulario como compositor (marcado: tarjeta, pastillas, menús y catálogo en diálogo)"
```

---

### Task 3: El comportamiento (menús, fichas, pastillas, catálogo, arrastrar)

**Files:**
- Modify: `templates/_tab_creativeflowplus.html` (tercer `<script>`)
- Test: `tests/test_crear_compositor.py`

**Interfaces:**
- Consumes: los ids de la Tarea 2.
- Produces: `cerrarMenus()`, `pintarFichas()`, `pintarMusica()`, `pintarPastillas()`, `pintarCatalogo()` (internas del script).

- [ ] **Step 1: Prueba que falla**

```python
def test_el_script_maneja_menus_fichas_y_pastillas(app):
    html = _html(app)
    for pieza in ("function cerrarMenus()", "function pintarFichas()", "function pintarMusica()",
                  "function pintarPastillas()", "function pintarCatalogo()", "e.dataTransfer.files"):
        assert pieza in html, pieza
    assert "bloqueVideo" not in html          # los bloques viejos se reemplazan por [data-solo-video]
```

Run → FALLA.

- [ ] **Step 2: Cabecera del script.** Reemplazar las variables `bloqueVideo`/`bloqueImagen` por:

```javascript
    var comp = document.getElementById('crear-comp');
    var precio = document.getElementById('fp-precio');
    var calidadWrap = document.getElementById('fp-calidad-wrap');
    var pieLogos = document.getElementById('fp-pie-logos');
```

- [ ] **Step 3: `ajustarSegunModelo`**: en la rama de video, después de `if (calidad) { … }`, agregar `if (calidadWrap) calidadWrap.hidden = m.value !== 'wan3';`.

- [ ] **Step 4: `refrescar()`**: las dos primeras líneas pasan a

```javascript
      var esImagen = tipoActual() === 'imagen';
      comp.querySelectorAll('[data-solo-video]').forEach(function (el) { el.hidden = esImagen; });
      comp.querySelectorAll('[data-solo-imagen]').forEach(function (el) { el.hidden = !esImagen; });
```

y el final (desde `var btnArmar` hasta el cierre de la función) pasa a

```javascript
      // «Generar» (video o imagen) cobra al generar con el texto de la persona;
      // el precio va al lado, con el formato de gastos.formatear: «≈ US$ 1,00».
      botonGenerar.textContent = esImagen ? 'Generar imagen' : 'Generar video';
      precio.textContent = usd ? '≈ ' + formatearUSD(usd) : '';
      if (pieLogos) pieLogos.hidden = sinAdjuntos();
      pintarFichas(); pintarMusica(); pintarPastillas();
    }
```

Listeners nuevos junto a los de `refrescar`:

```javascript
    [formatoVideo, formatoImagen].forEach(function (s) { if (s) s.addEventListener('change', refrescar); });
    document.getElementById('fp-sonido').addEventListener('input', function () { pintarPastillas(); });
```

- [ ] **Step 5: Fichas, música, pastillas y menús** (antes de la primera llamada a `refrescar();`):

```javascript
    // Duración y formato: los <select> de siempre son la fuente de verdad (el
    // servidor y limitarSelect los leen); el menú dibuja una ficha por opción y
    // la deshabilitada sale tachada.
    function pintarFichas() {
      comp.querySelectorAll('[data-fichas-de]').forEach(function (caja) {
        var sel = document.getElementById(caja.dataset.fichasDe);
        caja.innerHTML = '';
        Array.prototype.forEach.call(sel.options, function (o) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'crear-ficha';
          b.textContent = o.textContent.split(' (')[0]; b.title = o.textContent;
          b.dataset.valor = o.value;
          b.disabled = o.disabled || sel.disabled;
          b.setAttribute('aria-pressed', (!sel.disabled && o.value === sel.value) ? 'true' : 'false');
          caja.appendChild(b);
        });
      });
    }
    comp.addEventListener('click', function (e) {
      var ficha = e.target.closest('[data-fichas-de] .crear-ficha');
      if (!ficha || ficha.disabled) return;
      var sel = document.getElementById(ficha.closest('[data-fichas-de]').dataset.fichasDe);
      sel.value = ficha.dataset.valor;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      cerrarMenus();
    });

    // Música: el <select> #fp-musica sigue siendo la fuente de verdad (lo leen
    // el servidor y mostrarInicio); el menú lo dibuja como «Sin música», fichas
    // de estilos IA y la lista de Mi música.
    function pintarMusica() {
      var caja = document.getElementById('fp-musica-opciones');
      if (!caja) return;
      caja.innerHTML = '';
      function boton(valor, texto, clase) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = clase; b.dataset.musica = valor; b.textContent = texto;
        b.setAttribute('aria-pressed', musicaSel.value === valor ? 'true' : 'false');
        return b;
      }
      caja.appendChild(boton('', 'Sin música', 'crear-opcion-simple'));
      Array.prototype.forEach.call(musicaSel.querySelectorAll('optgroup'), function (g) {
        var opciones = g.querySelectorAll('option');
        if (g.hidden || !opciones.length) return;
        var propia = g.classList.contains('mm-opciones');
        var t = document.createElement('p');
        t.className = 'crear-menu-titulo';
        t.textContent = propia ? 'Mi música · gratis' : 'Estilos IA · US$ 0,02 la primera vez por estilo y duración';
        caja.appendChild(t);
        var lista = document.createElement('div');
        lista.className = propia ? 'crear-opciones' : 'crear-fichas';
        Array.prototype.forEach.call(opciones, function (o) {
          lista.appendChild(boton(o.value, (propia ? '▶ ' : '') + o.textContent, propia ? 'crear-opcion-simple' : 'crear-ficha'));
        });
        caja.appendChild(lista);
      });
    }
    comp.addEventListener('click', function (e) {
      var b = e.target.closest('[data-musica]');
      if (!b) return;
      musicaSel.value = b.dataset.musica;
      musicaSel.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Cada pastilla dice lo elegido.
    function recortar(t, n) { return t.length > n ? t.slice(0, n - 1) + '…' : t; }
    function pill(id, texto, aviso) {
      var b = document.getElementById(id);
      if (!b) return;
      b.textContent = texto;
      b.classList.toggle('con-aviso', !!aviso);
    }
    function pintarPastillas() {
      var esImagen = tipoActual() === 'imagen';
      var m = modeloActual();
      var cal = document.getElementById('fp-calidad');
      pill('fp-pill-tipo', esImagen ? '🖼 Imagen' : '🎬 Video');
      pill('fp-pill-modelo', m ? m.dataset.nombre + (!esImagen && cal && cal.checked ? ' · borrador' : '') : 'Modelo');
      pill('fp-pill-duracion', '⏱ ' + duracion.value + ' s', parseInt(duracion.value, 10) > 15);
      var selFormato = esImagen ? formatoImagen : formatoVideo;
      pill('fp-pill-formato', (!esImagen && formatoVideo.disabled) ? '▯ Formato de la imagen' : '▯ ' + selFormato.value);
      var cs = document.getElementById('fp-con-sonido');
      var desc = document.getElementById('fp-sonido').value.trim();
      pill('fp-pill-sonido', !cs.checked ? '🔇 Sin sonido' : '🔊 ' + (desc ? recortar(desc, 22) : 'Sonido'));
      var o = musicaSel.selectedOptions[0];
      pill('fp-pill-musica', '🎵 ' + (!musicaSel.value ? 'Sin música' : recortar(o ? o.textContent : musicaSel.value, 22)));
    }

    // Menús de las pastillas: uno abierto a la vez; se cierran con clic fuera,
    // con Escape o al elegir en los de una sola opción. En el celular suben
    // como hoja desde abajo (CSS) y #crear-velo oscurece el fondo.
    function cerrarMenus() {
      comp.querySelectorAll('.crear-menu').forEach(function (mn) { mn.hidden = true; });
      comp.querySelectorAll('[data-menu]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
      document.body.classList.remove('crear-menu-abierto');
    }
    comp.addEventListener('click', function (e) {
      var b = e.target.closest('[data-menu]');
      if (!b) return;
      var menu = document.getElementById(b.dataset.menu);
      var abrir = menu.hidden;
      cerrarMenus();
      if (!abrir) return;
      menu.hidden = false;
      b.setAttribute('aria-expanded', 'true');
      document.body.classList.add('crear-menu-abierto');
    });
    document.addEventListener('click', function (e) {
      // Un clic que redibujó su propio menú (p. ej. elegir música) deja el
      // target fuera del DOM: eso no es un clic fuera.
      if (!e.target.isConnected || e.target.closest('.crear-pill-zona')) return;
      cerrarMenus();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarMenus(); });
    form.addEventListener('change', function (e) {
      if (e.target.name === 'tipo' || e.target.name === 'modelo_video' || e.target.name === 'modelo_imagen') cerrarMenus();
    });

    // «+»: pegar link y catálogo.
    document.getElementById('fp-abrir-link').addEventListener('click', function () {
      var caja = document.getElementById('fp-link-caja');
      caja.hidden = !caja.hidden;
      if (!caja.hidden) caja.querySelector('input').focus();
    });
    var dlgCatalogo = document.getElementById('fp-catalogo');
    var catElegidos = document.getElementById('fp-catalogo-elegidos');
    document.getElementById('fp-abrir-catalogo').addEventListener('click', function () {
      cerrarMenus();
      dlgCatalogo.showModal();
    });
    var presionEnFondo = false;
    dlgCatalogo.addEventListener('mousedown', function (e) { presionEnFondo = e.target === dlgCatalogo; });
    dlgCatalogo.addEventListener('click', function (e) {
      if (e.target.closest('[data-cerrar-catalogo]') || (e.target === dlgCatalogo && presionEnFondo)) dlgCatalogo.close();
      presionEnFondo = false;
    });
    dlgCatalogo.addEventListener('close', function () { pintarCatalogo(); refrescar(); });
    // Lo marcado en el catálogo se ve en la tarjeta como las referencias
    // subidas; la × lo desmarca.
    function pintarCatalogo() {
      var marcados = form.querySelectorAll('input[name=productos_catalogo]:checked');
      catElegidos.innerHTML = '';
      marcados.forEach(function (cb) {
        var fig = document.createElement('figure');
        fig.className = 'crear-ref';
        var foto = cb.parentElement.querySelector('img');
        var img = document.createElement('img');
        img.src = foto ? foto.src : ''; img.alt = '';
        var cap = document.createElement('figcaption');
        cap.textContent = cb.dataset.nombre;
        var x = document.createElement('button');
        x.type = 'button'; x.className = 'crear-ref-quitar'; x.textContent = '×';
        x.setAttribute('aria-label', 'Quitar ' + cb.dataset.nombre);
        x.addEventListener('click', function () {
          cb.checked = false;
          cb.dispatchEvent(new Event('change', { bubbles: true }));
          pintarCatalogo();
        });
        fig.appendChild(img); fig.appendChild(cap); fig.appendChild(x);
        catElegidos.appendChild(fig);
      });
      catElegidos.hidden = !marcados.length;
    }
    pintarCatalogo();
```

- [ ] **Step 6: Subida y link con los formularios de afuera.** En el bloque de la bandeja:
  - todo `subida.style.display = 'block'` → `subida.hidden = false`; `subida.style.display = d.error ? 'block' : 'none'` → `subida.hidden = !d.error`;
  - en `formLink` submit: `formLink.querySelector('input[name=link]').value = ''` → `formLink.elements.link.value = ''`, y agregar `document.getElementById('fp-link-caja').hidden = true; cerrarMenus();`;
  - al inicio del `change` de `inputArchivos`: `cerrarMenus();`;
  - arrastrar y soltar, después del handler de `inputArchivos`:

```javascript
    // Arrastrar archivos sobre la tarjeta = «Subir imágenes o videos».
    function traeArchivos(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') !== -1; }
    ['dragenter', 'dragover'].forEach(function (t) {
      comp.addEventListener(t, function (e) {
        if (!traeArchivos(e)) return;
        e.preventDefault();
        comp.classList.add('soltando');
      });
    });
    comp.addEventListener('dragleave', function (e) {
      if (!comp.contains(e.relatedTarget)) comp.classList.remove('soltando');
    });
    comp.addEventListener('drop', function (e) {
      comp.classList.remove('soltando');
      if (!traeArchivos(e) || !e.dataTransfer.files.length) return;
      e.preventDefault();
      inputArchivos.files = e.dataTransfer.files;
      inputArchivos.dispatchEvent(new Event('change'));
    });
```

  - en «Sugerir» sonido, después de asignar `document.getElementById('fp-sonido').value = res.j.sonido;` llamar `pintarPastillas();`.

- [ ] **Step 7: Correr las pruebas del formulario** (mismo comando de la Tarea 2, Step 7) → verde.

- [ ] **Step 8: Commit** — `git commit -am "Crear: menús, fichas, pastillas, catálogo y arrastrar en el compositor"`

---

### Task 4: Estilo (escritorio y celular) + verificación en el navegador

**Files:**
- Modify: `static/style.css` (bloque nuevo al final)
- Test: `tests/test_crear_compositor.py`

- [ ] **Step 1: Prueba que falla**

```python
def test_css_del_compositor():
    css = open("static/style.css", encoding="utf-8").read()
    i = css.index("Crear: compositor (2026-09-27)")
    bloque = css[i:]
    for sel in (".crear-comp", ".crear-pill", ".crear-menu", ".crear-ficha:disabled", ".crear-interruptor input",
                "@media (max-width: 760px)", "body.crear-menu-abierto .crear-velo"):
        assert sel in bloque, sel
```

- [ ] **Step 2: El bloque CSS** (al final de `static/style.css`):

```css
/* ============================================================
   Crear: compositor (2026-09-27) — spec:
   docs/superpowers/specs/2026-09-27-crear-compositor-design.md
   Una tarjeta en dos mitades (bandeja arriba, formulario abajo) y una barra
   de pastillas con menús. Solo tokens de :root (modo oscuro único).
   ============================================================ */
.crear-comp { max-width: 920px; margin-top: 1rem; position: relative; }
.crear-comp [hidden] { display: none !important; }
.crear-comp-arriba { background: var(--panel); border: 1px solid var(--border); border-bottom: 0;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0; padding: 1rem 1.1rem .3rem; }
.crear-comp-abajo { background: var(--panel); border: 1px solid var(--border); border-top: 0;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg); padding: .1rem 1.1rem 1rem; }
.crear-comp.soltando .crear-comp-arriba, .crear-comp.soltando .crear-comp-abajo { border-color: var(--accent-2); background: var(--panel-hover); }

/* Referencias (bandeja + lo elegido del catálogo) */
.crear-refs { display: flex; flex-wrap: wrap; gap: .6rem; align-items: flex-start; }
.crear-refs + .crear-refs, #fp-bandeja-wrap + .crear-refs { margin-top: .6rem; }
.crear-ref { position: relative; margin: 0; width: 76px; }
.crear-ref img { width: 76px; height: 76px; object-fit: cover; display: block; border-radius: 10px; background: var(--panel-2); border: 1px solid var(--border); }
.crear-ref.es-video img { border: 2px solid var(--accent-2); }
.crear-ref figcaption { margin-top: .25rem; font-size: .68rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.crear-ref form { margin: 0; }
.crear-ref-quitar { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; min-height: 0; padding: 0; border-radius: 999px;
  border: 1px solid var(--border); background: var(--panel); color: var(--text); font-size: .8rem; line-height: 1; cursor: pointer; }
.crear-refs-acciones { display: flex; flex-wrap: wrap; gap: .2rem .9rem; align-items: center; align-self: center; }
.crear-refs-acciones form { margin: 0; }
.crear-refs-vacio { margin: 0 0 .4rem; font-size: .82rem; color: var(--muted); line-height: 1.5; }
.crear-ref-aviso { margin: 0 0 .5rem; font-size: .8rem; color: var(--muted); }
.crear-subida { margin-top: .6rem; font-size: .78rem; color: var(--muted); }

/* Botones con forma de enlace (Describir con IA, Quitar todas, super prompt) */
.crear-enlace { background: none; border: 0; padding: 0; min-height: 0; box-shadow: none; color: var(--accent-texto);
  font-family: var(--font-body); font-size: .8rem; font-weight: 600; cursor: pointer; text-align: left; }
.crear-enlace:hover:not(:disabled) { text-decoration: underline; filter: none; box-shadow: none; }
.crear-enlace-gris { color: var(--muted); font-weight: 500; }

/* Texto */
.crear-etiquetas { margin: .7rem 0 .1rem; }
.crear-etiquetas:empty { display: none; }
.crear-comp-abajo textarea { width: 100%; min-height: 6.5rem; resize: vertical; background: transparent; border: 0; box-shadow: none;
  padding: .7rem .1rem .5rem; font-size: 1rem; line-height: 1.55; color: var(--text); }
.crear-comp-abajo textarea:focus { outline: none; box-shadow: none; border: 0; }
.crear-comp-abajo textarea.con-error { box-shadow: inset 0 0 0 1px var(--error); border-radius: var(--radius-sm); }
.crear-oculto-lector { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* Barra: pastillas a la izquierda; precio y Generar a la derecha */
.crear-barra { display: flex; justify-content: space-between; align-items: center; gap: .8rem; flex-wrap: wrap;
  border-top: 1px solid var(--border); padding-top: .8rem; margin-top: .3rem; }
.crear-pills { display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; min-width: 0; }
.crear-pill-zona { position: relative; }
.crear-pill { display: inline-flex; align-items: center; gap: .3rem; min-height: 0; padding: .45rem .85rem; border-radius: 999px;
  background: var(--panel-2); border: 1px solid var(--border); color: var(--text); box-shadow: none;
  font-family: var(--font-body); font-size: .8rem; font-weight: 500; white-space: nowrap; cursor: pointer; }
.crear-pill:hover { background: var(--panel-hover); }
.crear-pill[aria-expanded="true"] { border-color: var(--accent-2); background: var(--panel-hover); }
.crear-pill.con-aviso { border-color: var(--warn); }
.crear-mas { width: 2.2rem; height: 2.2rem; padding: 0; justify-content: center; font-size: 1.2rem; }
.crear-generar { display: flex; align-items: center; gap: .8rem; margin-left: auto; }
.crear-precio { font-family: var(--font-display); font-weight: 700; font-size: 1.1rem; white-space: nowrap; }
.crear-generar .btn-generar { border-radius: 999px; padding: .65rem 1.35rem; margin: 0; }

/* Menús */
.crear-menu { position: absolute; top: calc(100% + .5rem); left: 0; z-index: 30; width: 320px; max-width: calc(100vw - 2rem);
  display: flex; flex-direction: column; gap: .3rem; padding: .5rem; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); }
.crear-menu-ancho { width: 370px; }
.crear-menu-der { left: auto; right: 0; }
.crear-menu-titulo { margin: .35rem .45rem .1rem; font-size: .68rem; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.crear-menu-item { display: flex; flex-direction: row; gap: .7rem; align-items: flex-start; width: 100%; min-height: 0; padding: .55rem .6rem;
  text-align: left; background: none; border: 0; border-radius: var(--radius-sm); box-shadow: none; color: var(--text);
  font-family: var(--font-body); font-size: .85rem; font-weight: 400; cursor: pointer; }
.crear-menu-item:hover { background: var(--panel-hover); }
.crear-menu-item strong, .crear-opcion strong, .crear-interruptor strong { display: block; font-size: .85rem; font-weight: 600; color: var(--text); }
.crear-menu-item small, .crear-opcion small, .crear-interruptor small { display: block; margin-top: .1rem; font-size: .74rem; font-weight: 400; line-height: 1.4; color: var(--muted); }
.crear-menu-ico { flex: none; width: 1.9rem; height: 1.9rem; display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--radius-sm); background: var(--panel); }
.crear-menu-fila { display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; padding: .15rem .45rem; }
.crear-menu-fila input[type="text"], .crear-menu-fila input[type="url"] { flex: 1 1 10rem; margin: 0; }
.crear-menu-sep { height: 1px; background: var(--border); margin: .25rem .3rem; }
.crear-nota { margin: .1rem .45rem; font-size: .74rem; line-height: 1.45; color: var(--muted); }
.crear-nota-aviso { color: var(--warn); }

/* Listas de una opción (tipo, modelo, Mi música) */
.crear-opciones { display: flex; flex-direction: column; gap: .2rem; }
.crear-opcion { position: relative; display: flex; align-items: center; gap: .7rem; padding: .55rem .6rem;
  border: 1px solid transparent; border-radius: var(--radius-sm); cursor: pointer; }
.crear-opcion:hover { background: var(--panel-hover); }
.crear-opcion input { position: absolute; opacity: 0; pointer-events: none; }
.crear-opcion:has(input:checked) { border-color: var(--accent-2); background: var(--panel-hover); }
.crear-opcion:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 1px; }
.crear-opcion > span { flex: 1; min-width: 0; }
.crear-modelo em { font-style: normal; font-size: .78rem; font-weight: 600; color: var(--accent-texto); white-space: nowrap; }
.crear-opcion-simple { width: 100%; min-height: 0; padding: .5rem .6rem; text-align: left; background: none; box-shadow: none;
  border: 1px solid transparent; border-radius: var(--radius-sm); color: var(--text); font-family: var(--font-body); font-size: .85rem; font-weight: 500; cursor: pointer; }
.crear-opcion-simple:hover { background: var(--panel-hover); }
.crear-opcion-simple[aria-pressed="true"] { border-color: var(--accent-2); background: var(--panel-hover); }

/* Fichas (duración, formato, estilos de música) */
.crear-fichas { display: flex; flex-wrap: wrap; gap: .35rem; padding: .1rem .35rem; }
.crear-ficha { min-height: 0; padding: .35rem .75rem; border-radius: 999px; background: var(--panel); border: 1px solid var(--border);
  box-shadow: none; color: var(--text); font-family: var(--font-body); font-size: .78rem; font-weight: 500; cursor: pointer; }
.crear-ficha:hover:not(:disabled) { background: var(--panel-hover); }
.crear-ficha[aria-pressed="true"] { border-color: var(--accent-2); background: var(--panel-hover); }
.crear-ficha:disabled { opacity: .4; text-decoration: line-through; cursor: not-allowed; }

/* Interruptores (borrador, sonido de la escena) */
.crear-interruptor { display: flex; align-items: center; gap: .7rem; padding: .55rem .6rem; border-radius: var(--radius-sm); cursor: pointer; }
.crear-interruptor > span { flex: 1; min-width: 0; }
.crear-interruptor input { order: 2; flex: none; appearance: none; -webkit-appearance: none; position: relative; width: 2.2rem; height: 1.3rem;
  margin: 0; border-radius: 999px; background: var(--panel-hover); border: 1px solid var(--border); cursor: pointer; transition: background .15s ease; }
.crear-interruptor input::after { content: ""; position: absolute; top: 2px; left: 2px; width: calc(1.3rem - 6px); height: calc(1.3rem - 6px);
  border-radius: 50%; background: var(--muted); transition: transform .15s ease, background .15s ease; }
.crear-interruptor input:checked { background: var(--accent-grad); border-color: transparent; }
.crear-interruptor input:checked::after { transform: translateX(.9rem); background: var(--text); }
.crear-interruptor input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.crear-interruptor input:disabled { opacity: .45; cursor: not-allowed; }

/* Música */
.crear-musica { display: flex; flex-direction: column; gap: .2rem; }
.crear-musica-inicio { display: flex; flex-direction: column; gap: .3rem; padding: .2rem .45rem; }
.crear-musica-inicio audio { width: 100%; height: 32px; }
.crear-inicio { display: inline-flex; flex-direction: row; align-items: center; gap: .4rem; font-size: .78rem; color: var(--muted); }
.crear-inicio input { width: 4.5rem; margin: 0; }
#mm-wrap .mm-panel { padding: 0 .45rem .2rem; }

/* Pie y catálogo */
.crear-pie { max-width: 920px; display: flex; justify-content: space-between; align-items: center; gap: .4rem 1rem; flex-wrap: wrap;
  margin: .6rem .2rem 0; font-size: .78rem; color: var(--muted); }
.crear-pie .crear-enlace { color: var(--muted); font-weight: 500; }
.crear-pie .crear-enlace strong { color: var(--accent-texto); font-weight: 600; }
.selector-en-dialogo .comparacion-contenido { padding: 0; border: 0; background: none; }
.selector-resumen { margin: 0 0 .8rem; font-size: .82rem; color: var(--muted); }

.crear-velo { display: none; }
@media (max-width: 760px) {
  .crear-comp-arriba { padding: .8rem .8rem .3rem; }
  .crear-comp-abajo { padding: .1rem .8rem .8rem; }
  .crear-barra { flex-direction: column; align-items: stretch; }
  .crear-pills { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding-bottom: .2rem; }
  .crear-pills::-webkit-scrollbar { display: none; }
  .crear-pill-zona { position: static; flex: none; }
  .crear-menu, .crear-menu-ancho, .crear-menu-der { position: fixed; left: 0; right: 0; top: auto; bottom: 0; width: auto; max-width: none;
    max-height: 75vh; overflow-y: auto; z-index: 60; padding: .9rem .8rem 1.2rem; border-radius: var(--radius-lg) var(--radius-lg) 0 0; }
  body.crear-menu-abierto .crear-velo { display: block; position: fixed; inset: 0; z-index: 55; background: rgba(0, 0, 0, .55); }
  .crear-generar { margin-left: 0; }
  .crear-generar .btn-generar { flex: 1; }
}
```

- [ ] **Step 3: Pruebas** — `venv/bin/python3 -m pytest -q tests/test_crear_compositor.py tests/test_modo_oscuro.py tests/test_base_visual.py tests/test_movil.py` → verde.

- [ ] **Step 4: Verificación en el navegador** (app local sin llaves: base temporal, sesión de admin sembrada, `ATRIA`/R2/etc. vacías; lanzador en el scratchpad como en la reproducción del modal). En la pestaña Crear, comprobar y anotar:
  1. se ve la tarjeta con «+» y las seis pastillas; el precio aparece junto a «Generar video»;
  2. cada menú abre, cierra con clic fuera y con Escape, y solo uno a la vez;
  3. Kling O3 Pro → 20/25/30 s y 4:3/3:4 tachados; la pastilla salta a un valor válido; el precio = segundos × 0,14 (con sonido);
  4. Seedance con una referencia → «▯ Formato de la imagen» y fichas de formato tachadas;
  5. borrador visible solo con Wan; con borrador la pastilla dice «Wan 3.0 · borrador» y el precio baja;
  6. Imagen → desaparecen duración, sonido, música y el super prompt; el botón dice «Generar imagen»;
  7. catálogo → diálogo, marcar uno → «Listo» → miniatura en la tarjeta; su × la quita;
  8. texto vacío + «Generar» → no envía y se ve el error;
  9. Enter en el campo de sonido → no hay POST (log del servidor);
  10. música: elegir un estilo cambia la pastilla y suma 0,02 al precio;
  11. a 375 px: la página no se desliza de lado (`document.documentElement.scrollWidth <= innerWidth`), las pastillas se deslizan y el menú sube como hoja;
  12. captura final y comparación con la maqueta aprobada.
  Todo lo que falle se arregla en su plantilla o CSS y se vuelve a comprobar.

- [ ] **Step 5: Commit** — `git add static/style.css tests/test_crear_compositor.py templates/ && git commit -m "Crear: estilo del compositor (escritorio y celular)"`

---

### Task 5: Documentación, suite completa, mezcla y despliegue

**Files:**
- Modify: `CLAUDE.md` (párrafo «UI base»: una frase sobre el compositor de Crear)
- Modify: `docs/superpowers/specs/2026-09-27-crear-compositor-design.md` (el nombre del botón: «Crear super prompt con IA (gratis)»; en el celular el precio va al lado del botón a todo lo ancho)

- [ ] **Step 1:** Agregar al final del párrafo **UI base** de `CLAUDE.md`: «Crear's «Desde referencias» form is a composer (spec `2026-09-27-crear-compositor`): a card (bandeja above, OUTSIDE `#form-flowplus`; the form below) with a bar of pills whose menus hold the real radios/selects (the selects stay the source of truth, hidden, and the menus draw chips from them), so the POST to `cf_crear_video` is unchanged; Enter in a one-line input never submits it.»
- [ ] **Step 2:** Ajustar el spec (§4.1, §4.5) al nombre real del botón y a la fila de precio + botón en el celular.
- [ ] **Step 3:** Suite completa: `venv/bin/python3 -m pytest -q` → todo verde (salvo omitidas conocidas).
- [ ] **Step 4:** Commit de docs; `git fetch origin`; rebase de la rama sobre `origin/main`; suite otra vez si entró algo.
- [ ] **Step 5:** Subir: `git push origin crear-compositor:main` (fast-forward). En el VPS: `git pull --ff-only`, reiniciar solo `iaplusyou` (solo plantillas y CSS), `/login` en 200 y humo de solo lectura con el test client: `/cliente/happyflops` en 200 con `id="crear-comp"` y `fp-menu-modelo`.
- [ ] **Step 6:** Actualizar la memoria (`mejora-visual-estado.md`, `produccion-vps-creatvmachine.md`).
