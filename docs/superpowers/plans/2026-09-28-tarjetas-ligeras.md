# Tarjetas ligeras y detalle bajo demanda — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La página del proyecto deja de embeber el detalle de cada tarjeta de Crear y Final edition (1,86 MB de 3,03 MB) y pinta 24 tarjetas por lista; el detalle llega por fetch al abrir la tarjeta y «Ver más» trae las siguientes.

**Architecture:** Las tarjetas y los detalles salen a macros Jinja compartidas por la página y por rutas GET nuevas que devuelven fragmentos HTML. Un helper en `base.html` (`abrirDetalleRemoto`) llena el modal por fetch; un observador (`arrancarSondeos`) arranca el sondeo de cualquier `[data-poll-job]` que aparezca, y las tarjetas dejan de traer `<script>` propio. Los clics pasan a delegación sobre las cuadrículas para que las tarjetas agregadas funcionen igual.

**Tech Stack:** Flask + Jinja2 (macros `with context`), JS sin librerías (fetch, MutationObserver), pytest con el test client de Flask, Flask-Babel para los textos nuevos.

**Spec:** `docs/superpowers/specs/2026-09-28-tarjetas-ligeras-detalle-bajo-demanda-design.md`

## Global Constraints

- 24 tarjetas por lista (`TARJETAS_POR_PAGINA = 24`); contadores de cabecera con el total.
- El detalle nunca se cachea en el navegador; cada apertura lo pide de nuevo.
- Las pestañas y los enlaces `#creativeflowplus`, `#final?cf=<id>`, `#experimentos?piezas=<id>` no cambian.
- Ninguna barra de progreso lleva `<script>`: todas usan `data-poll-job` sobre el `div.barra-progreso` con `id="trabajo-<job_id>"`.
- Sondeo: 1.500 ms antes de 60 s, 3.000 ms antes de 300 s, 5.000 ms después; sin consultas con `document.hidden`.
- Todo texto nuevo visible pasa por `{{ _('…') }}` (o `|tojson` dentro de `<script>`) y al catálogo: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir en `translations/en/LC_MESSAGES/messages.po`, `compilar`.
- No se tocan las rutas POST ni sus redirects; el HTML del detalle es el mismo de hoy.
- Pruebas: `venv/bin/python3 -m pytest -q -m "not slow"` en verde; `python3 -m py_compile dashboard.py`.
- Trabajar en el worktree `.claude/worktrees/tarjetas-ligeras` (rama `tarjetas-ligeras`), `venv` enlazado desde la carpeta principal.

---

### Task 1: Servidor — una pieza por id, contexto de Final edition y paginación

**Files:**
- Modify: `dashboard.py` — `_creative_flow_items` (línea ~2739), `ver_cliente` (línea ~1534; `render_template("cliente.html", …)` ~1650-1760)
- Test: `tests/test_tarjetas_ligeras.py` (crear)

**Interfaces:**
- Produces: `TARJETAS_POR_PAGINA = 24`; `_pagina_desde(valor) -> int` (entero ≥ 0, 0 si no lo es); `_creative_flow_item(cliente, cf_id) -> dict | None` (el mismo dict que produce `_creative_flow_items` para esa sesión); `_contexto_final_edition(cliente) -> dict` con claves `paises_fe, voces_fe, estilos_fe, nombres_estilos_musica, nombres_estilo_musica, presets_mezcla, precios, ediciones_por_cf` + las de `_contexto_mi_musica(cliente)`; `_listas_crear_final(items) -> dict` con `crear` (items[:24]), `crear_total`, `final_videos` (video_listo y no imagen, [:24]), `final_videos_total`, `finales` (lista de `(item, f)` [:24]), `finales_total`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_tarjetas_ligeras.py
"""Tarjetas ligeras y detalle bajo demanda (spec 2026-09-28)."""
import re

import pytest


def _admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _admin(dashboard)}


def _sembrar(n, cliente="acme", desde=0, tipo="video", estado="video_listo", con_final=False, guion=False):
    """n sesiones; ids crecientes en el tiempo (la lista va de la más nueva a la más vieja)."""
    import creative_flow
    ids = []
    for i in range(desde, desde + n):
        cf_id = creative_flow.crear(cliente, [], ["prod"], [], f"acción {i}", 8, "tono", "A",
                                    legado_id=f"cf_20260901_000000_{i:06d}", creado_en=f"2026-09-01T00:{i // 60:02d}:{i % 60:02d}")
        campos = {"estado": estado, "tipo": tipo}
        if estado == "video_listo":
            campos["video_url"] = f"https://r2/videos/{cf_id}.mp4"
        if guion:
            campos["guion_base"] = {"idioma": "es", "pais": "CO", "precio_base": None,
                                    "bloques": [{"rol": "gancho", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "Hola", "texto_voz": "Hola"}]}
        creative_flow.actualizar(cliente, cf_id, **campos)
        if con_final:
            fid = creative_flow.crear_final(cliente, cf_id, "es", "CO")
            creative_flow.actualizar_final(cliente, fid, estado="listo", url_video=f"https://r2/finales/{fid}.mp4",
                                           capas={"voz": {"proveedor": "fal", "estado": "ok"}})
        ids.append(cf_id)
    return ids


def test_creative_flow_item_devuelve_lo_mismo_que_la_lista(app):
    dashboard = app["dashboard"]
    ids = _sembrar(3, con_final=True, guion=True)
    lista = {i["id"]: i for i in dashboard._creative_flow_items("acme")}
    for cf in ids:
        assert dashboard._creative_flow_item("acme", cf) == lista[cf]
    assert dashboard._creative_flow_item("acme", "cf_no_existe") is None
    assert dashboard._creative_flow_item("otro", ids[0]) is None


def test_pagina_desde_y_listas(app):
    dashboard = app["dashboard"]
    assert dashboard._pagina_desde("24") == 24 and dashboard._pagina_desde("abc") == 0
    assert dashboard._pagina_desde("-5") == 0 and dashboard._pagina_desde(None) == 0
    _sembrar(30, con_final=True)
    _sembrar(2, desde=30, tipo="imagen")
    items = dashboard._creative_flow_items("acme")
    listas = dashboard._listas_crear_final(items)
    assert len(listas["crear"]) == 24 and listas["crear_total"] == 32
    assert listas["crear"][0]["id"] == "cf_20260901_000000_000031"          # la más nueva primero
    assert len(listas["final_videos"]) == 24 and listas["final_videos_total"] == 30
    assert all(i["tipo"] == "video" for i in listas["final_videos"])
    assert len(listas["finales"]) == 24 and listas["finales_total"] == 30
    assert listas["finales"][0][1]["idioma"] == "es"


def test_contexto_final_edition_tiene_lo_que_usan_los_detalles(app):
    ctx = app["dashboard"]._contexto_final_edition("acme")
    for clave in ("paises_fe", "voces_fe", "estilos_fe", "presets_mezcla", "precios", "ediciones_por_cf", "mi_musica"):
        assert clave in ctx
    assert "guion" in ctx["precios"] and "final_por_pais" in ctx["precios"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py`
Expected: FAIL con `AttributeError: module 'dashboard' has no attribute '_creative_flow_item'` (y `_pagina_desde`, `_listas_crear_final`, `_contexto_final_edition`).

- [ ] **Step 3: Refactorizar `_creative_flow_items` en `_armar_item_cf` + `_creative_flow_item`**

En `dashboard.py`, reemplazar la función `_creative_flow_items` por estas tres (el cuerpo del bucle es el actual, sin cambios de contenido; solo se saca a `_armar_item_cf` y las lecturas por proyecto a `_ctx_items_cf`):

```python
TARJETAS_POR_PAGINA = 24


def _pagina_desde(valor):
    """`?desde=` de las listas paginadas: entero >= 0; cualquier otra cosa es 0."""
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _ctx_items_cf(cliente):
    """Lecturas por proyecto que necesita cada item (una consulta cada una)."""
    try:
        guia_marca = marca_mod.guia_efectiva(cliente) or ""
    except Exception:  # noqa: BLE001 — es informativa, nunca bloquea
        guia_marca = ""
    return {
        "pieza_ids": creative_flow.piezas_ids_por_legado(cliente),
        "guiones": creative_flow.guiones_base(cliente),
        "finales_por_cf": creative_flow.finales_por_sesion(cliente),
        "captions": doctrina_revisor.ultimos_captions(cliente),
        "guia_marca": guia_marca,
        "productos_por_ids": {},
    }


def _armar_item_cf(cliente, cf_id, entry, data, ctx):
    """El dict de UNA sesión de Crear (tarjeta + detalle). `data` es
    creative_flow.cargar(cliente) entero (para `tiene_hija_b`); `ctx` viene de
    _ctx_items_cf y se comparte entre las piezas de una misma lista."""
    import final_edition
    job_id = _job_id_creative_flow(cliente, cf_id)
    jid_director = tareas_director.job_id(cliente, cf_id)
    trabajo_director = (
        {"job_id": jid_director} if entry.get("estado") == "prompt_pendiente" and trabajos.en_curso(jid_director) else None)
    item = {
        "id": cf_id,
        **entry,
        "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        "trabajo_director": trabajo_director,
        "pieza_id": ctx["pieza_ids"].get(cf_id),
    }
    # … (desde aquí, el cuerpo actual del bucle tal cual: tiene_hija_b,
    # costo_estimado, modelo_nombre, guion_base/finales/trabajo_guion/
    # trabajo_editor, revisión y reglas de la doctrina) con estos reemplazos:
    #   creative_flow.guion_base(...)      -> ctx["guiones"].get(cf_id)
    #   creative_flow.finales(...)         -> ctx["finales_por_cf"].get(cf_id, [])
    #   captions.get(cf_id, "")            -> ctx["captions"].get(cf_id, "")
    #   guia_marca                         -> ctx["guia_marca"]
    #   productos_por_ids                  -> ctx["productos_por_ids"]
    return item


def _creative_flow_items(cliente):
    data = creative_flow.cargar(cliente)
    ctx = _ctx_items_cf(cliente)
    return [_armar_item_cf(cliente, cf_id, entry, data, ctx)
            for cf_id, entry in sorted(data.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True)]


def _creative_flow_item(cliente, cf_id):
    """El mismo dict que _creative_flow_items produce para esa sesión, o None
    si no existe en ese proyecto (las rutas de detalle responden 404)."""
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        return None
    return _armar_item_cf(cliente, cf_id, entry, data, _ctx_items_cf(cliente))


def _listas_crear_final(items):
    """Lo que pinta la página: las primeras TARJETAS_POR_PAGINA de cada lista y
    los totales (los contadores de cabecera muestran el total)."""
    videos = [i for i in items if i.get("estado") == "video_listo" and (i.get("tipo") or "video") != "imagen"]
    finales = [(i, f) for i in items for f in i.get("finales") or []]
    n = TARJETAS_POR_PAGINA
    return {"crear": items[:n], "crear_total": len(items),
            "final_videos": videos[:n], "final_videos_total": len(videos),
            "finales": finales[:n], "finales_total": len(finales)}


def _contexto_final_edition(cliente):
    """Contexto que leen los detalles de Final edition (la página y las rutas
    de detalle lo reciben igual)."""
    return {
        "paises_fe": fe_tipos.PAISES,
        "voces_fe": fal_audio.VOCES,
        "estilos_fe": list(fe_tipos.ESTILOS_MUSICA),
        "nombres_estilos_musica": fe_tipos.NOMBRES_ESTILOS_MUSICA,
        "nombres_estilo_musica": fe_tipos.NOMBRES_ESTILO_MUSICA,
        "presets_mezcla": list(fe_mezcla.PRESETS),
        "precios": _precios_pagina(),
        "ediciones_por_cf": _ediciones_por_cf(cliente),
        **_contexto_mi_musica(cliente),
    }
```

Nota: al mover el cuerpo, `productos_por_ids` deja de ser una variable local y pasa a `ctx["productos_por_ids"]` (sigue memorizando por tupla de `productos_ids` dentro de una misma lista). `_creative_flow_item` arma un `ctx` nuevo por llamada (una consulta por función; para un solo detalle es barato).

- [ ] **Step 4: Usar el contexto y las listas en `ver_cliente`**

En `render_template("cliente.html", …)`: quitar las líneas `ediciones_por_cf=…`, `paises_fe=…`, `voces_fe=…`, `estilos_fe=…`, `nombres_estilos_musica=…`, `nombres_estilo_musica=…`, `**_contexto_mi_musica(cliente),`, `presets_mezcla=…` y poner `**_contexto_final_edition(cliente),`. Reemplazar `creative_flow_items=_creative_flow_items(cliente),` por:

```python
        creative_flow_items=cf_items,
        **_listas_crear_final(cf_items),
```

con `cf_items = _creative_flow_items(cliente)` calculado antes de la llamada. `gasto_ctx` sigue aportando `precios` para el resto de la página: confirmar que no queda `precios=` duplicado (si `gasto_ctx` ya trae `precios`, `_contexto_final_edition` lo pisa con el mismo valor — es el mismo `_precios_pagina()`).

- [ ] **Step 5: Correr las pruebas nuevas y las de la página**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py tests/test_perf_pagina_proyecto.py tests/test_tab_final.py tests/test_rutas_final_edition.py tests/test_rutas_crear_director.py`
Expected: PASS (la página todavía pinta todo: solo cambió de dónde sale el contexto).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py tests/test_tarjetas_ligeras.py
git commit -m "Tarjetas ligeras (1/6): una pieza por id, contexto de Final edition y listas paginadas en el servidor"
```

---

### Task 2: `base.html` — sondeos por `data-poll-job`, ritmo del sondeo y modal por fetch

**Files:**
- Modify: `templates/base.html` — `iniciarPolling` (~138-258), el observador de `video[data-precarga]` (~296-333)
- Test: `tests/test_tarjetas_ligeras.py` (agregar)

**Interfaces:**
- Produces (JS global en `base.html`): `arrancarSondeos(raiz)`; `intervaloSondeo(inicioMs)` → 1500 | 3000 | 5000; `abrirDetalleRemoto(modal, cuerpo, url, alInsertar)`; el observador de mutaciones también llama `arrancarSondeos` sobre cada nodo insertado.
- Consumes: `iniciarPolling(jobId, contenedorId)` existente; `T_BASE` (textos traducidos del sondeo).

- [ ] **Step 1: Prueba de contrato del JS**

```python
# tests/test_tarjetas_ligeras.py (agregar)
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _plantilla(nombre):
    return open(os.path.join(RAIZ, "templates", nombre), encoding="utf-8").read()


def test_base_trae_sondeos_por_atributo_ritmo_y_modal_remoto():
    base = _plantilla("base.html")
    assert "function arrancarSondeos(raiz)" in base
    assert "function intervaloSondeo(" in base and "document.hidden" in base and "visibilitychange" in base
    assert "function abrirDetalleRemoto(modal, cuerpo, url, alInsertar)" in base
    assert "'X-Requested-With': 'fetch'" in base
    # El observador de nodos insertados arranca sondeos además de videos.
    assert "arrancarSondeos(n)" in base
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py::test_base_trae_sondeos_por_atributo_ritmo_y_modal_remoto`
Expected: FAIL (`arrancarSondeos` no existe).

- [ ] **Step 3: Ritmo y pausa en `iniciarPolling`**

Dentro del `<script>` de `base.html` donde vive `iniciarPolling`, ANTES de `function iniciarPolling`:

```js
    // Ritmo del sondeo (auditoría 2026-09-28): 1,5 s el primer minuto, 3 s
    // hasta los cinco minutos, 5 s después. Un render de 10 min ya no cuesta
    // 400 consultas.
    function intervaloSondeo(inicioMs) {
      var t = Date.now() - inicioMs;
      if (t < 60000) return 1500;
      if (t < 300000) return 3000;
      return 5000;
    }
```

Dentro de `iniciarPolling`, después de `var reintentos = 0;`:

```js
      var inicio = Date.now();
      var pausado = false;
      // Con la pestaña del navegador oculta no se consulta nada; al volver,
      // un tick inmediato pone la barra al día.
      document.addEventListener('visibilitychange', function () {
        if (!document.hidden && pausado) { pausado = false; tick(); }
      });
```

Al comienzo de `function tick()`:

```js
        if (document.hidden) { pausado = true; return; }
```

Y reemplazar `setTimeout(tick, 1500);` (la rama `en_progreso`) por `setTimeout(tick, intervaloSondeo(inicio));`. Los `setTimeout(tick, 1200)` y `2000` de los reintentos no cambian.

- [ ] **Step 4: `arrancarSondeos` y el observador**

Después de `function iniciarPolling(...) { … }` (mismo `<script>`, así ve `iniciarPolling`):

```js
    // Toda barra de progreso lleva data-poll-job (spec 2026-09-28): una sola
    // función arranca el sondeo de las que haya bajo `raiz`, al cargar la
    // página, al agregar tarjetas («Ver más») y al llenar un modal por fetch.
    // Las tarjetas ya no traen <script>iniciarPolling(...)</script>, que en un
    // fragmento insertado con innerHTML nunca corre.
    function arrancarSondeos(raiz) {
      if (!raiz || !raiz.querySelectorAll) return;
      var lista = (raiz.matches && raiz.matches('[data-poll-job]')) ? [raiz] : [];
      raiz.querySelectorAll('[data-poll-job]').forEach(function (el) { lista.push(el); });
      lista.forEach(function (el) {
        if (el.dataset.sondeando || !el.id) return;
        el.dataset.sondeando = '1';
        iniciarPolling(el.dataset.pollJob, el.id);
      });
    }
    window.arrancarSondeos = arrancarSondeos;
    document.addEventListener('DOMContentLoaded', function () { arrancarSondeos(document); });

    // Modal de detalle por fetch (Crear y Final edition): abre al instante con
    // «Cargando…», pide el HTML y solo lo pinta si sigue siendo el último
    // pedido (dos clics rápidos no se pisan). Nada se cachea: el detalle trae
    // formularios con estado vivo.
    function abrirDetalleRemoto(modal, cuerpo, url, alInsertar) {
      var n = (modal._pedidoDetalle = (modal._pedidoDetalle || 0) + 1);
      cuerpo.innerHTML = '<p class="vacio">' + T_BASE.cargando + '</p>';
      if (!modal.open) modal.showModal();
      fetch(url, { headers: { 'X-Requested-With': 'fetch' }, cache: 'no-store' })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(new Error(String(r.status))); })
        .then(function (html) {
          if (n !== modal._pedidoDetalle || !modal.open) return;
          cuerpo.innerHTML = html;
          arrancarSondeos(cuerpo);
          if (alInsertar) alInsertar(cuerpo);
        })
        .catch(function () {
          if (n !== modal._pedidoDetalle || !modal.open) return;
          cuerpo.innerHTML = '<p class="vacio">' + T_BASE.detalleNoCargo + '</p>';
        });
    }
    window.abrirDetalleRemoto = abrirDetalleRemoto;
```

Agregar a `T_BASE` (el objeto de textos del sondeo, en el mismo script): `cargando: {{ _('Cargando…')|tojson }}, detalleNoCargo: {{ _('No se pudo cargar el detalle. Recarga la página.')|tojson }}`.

En el observador de videos (bloque «Videos de las listas (incidente 2026-09-28)»), dentro del `MutationObserver`, junto a `observar(n)`: agregar `if (window.arrancarSondeos) arrancarSondeos(n);` para cada nodo insertado (`n.nodeType === 1`).

- [ ] **Step 5: Correr la prueba de contrato**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/base.html tests/test_tarjetas_ligeras.py
git commit -m "Tarjetas ligeras (2/6): sondeos por data-poll-job, ritmo del sondeo y modal por fetch en base.html"
```

---

### Task 3: Crear — tarjetas y detalle en macros, rutas de fragmento, JS delegado

**Files:**
- Create: `templates/_crear_tarjetas.html`, `templates/_crear_detalle.html`
- Modify: `templates/_tab_creativeflowplus.html` (bloque `#creativeflowplus-resultados` ~220-405 y el script del modal ~418-445), `dashboard.py` (rutas nuevas junto a `cf_descartar`, ~6064)
- Test: `tests/test_tarjetas_ligeras.py` (agregar)

**Interfaces:**
- Produces: rutas `crear_tarjetas` (`GET /cliente/<cliente>/crear/tarjetas`), `cf_detalle` (`GET /cliente/<cliente>/creative_flow/<cf_id>/detalle`); macros `tarjeta_crear(item)`, `lista_crear(items, desde, total)` en `_crear_tarjetas.html`; `detalle_crear(item)` en `_crear_detalle.html`. Cada tarjeta lleva `data-detalle="{{ url_for('cf_detalle', cliente=cliente, cf_id=item.id) }}"`.
- Consumes: `_creative_flow_item`, `_creative_flow_items`, `_pagina_desde`, `TARJETAS_POR_PAGINA` (Task 1); `abrirDetalleRemoto`, `arrancarSondeos` (Task 2); macro `revision_doctrina` (`_revision_doctrina.html`).

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_tarjetas_ligeras.py (agregar)
def test_crear_pinta_24_tarjetas_sin_detalle_embebido(app):
    _sembrar(30)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = html.split('id="tab-creativeflowplus"')[1].split('id="tab-final"')[0]
    assert '<template class="generado-detalle">' not in crear
    assert "iniciarPolling(" not in crear.split('id="generado-modal"')[0]      # ninguna tarjeta trae <script>
    assert crear.count('class="generado"') == 24
    assert 'data-siguiente="24"' in crear and "Generados (30)" in crear
    assert crear.count('data-detalle="/cliente/acme/creative_flow/') == 24


def test_crear_ver_mas_y_desde_raro(app):
    _sembrar(30)
    c = app["c"]
    r = c.get("/cliente/acme/crear/tarjetas?desde=24")
    assert r.status_code == 200 and r.mimetype == "text/html"
    html = r.get_data(as_text=True)
    assert html.count('class="generado"') == 6 and "data-siguiente" not in html
    assert c.get("/cliente/acme/crear/tarjetas?desde=abc").get_data(as_text=True).count('class="generado"') == 24


def test_detalle_de_crear(app):
    (cf,) = _sembrar(1)
    c = app["c"]
    r = c.get(f"/cliente/acme/creative_flow/{cf}/detalle")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Descargar" in html and "fp_reusar" not in html and f"/creative_flow/{cf}/reusar" in html or "reusar" in html
    assert "detalle-acciones" in html and "<template" not in html
    assert c.get("/cliente/acme/creative_flow/cf_nada/detalle").status_code == 404
    assert c.get(f"/cliente/otro/creative_flow/{cf}/detalle").status_code == 404


def test_tarjeta_con_trabajo_vivo_usa_data_poll_job(app):
    import cola
    (cf,) = _sembrar(1, estado="video_generando")
    dashboard = app["dashboard"]
    cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cf}, job_id=dashboard._job_id_creative_flow("acme", cf), cliente="acme")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = html.split('id="tab-creativeflowplus"')[1].split('id="tab-final"')[0]
    assert f'data-poll-job="{dashboard._job_id_creative_flow("acme", cf)}"' in crear
    assert "<script>iniciarPolling" not in crear
```

(En `test_detalle_de_crear`, la afirmación sobre `reusar` se simplifica a `assert url_for-like "/reusar" in html` — comprobar el nombre real de la ruta `fp_reusar` con `grep -n "def fp_reusar" -B2 dashboard.py` y usar su path.)

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py -k "crear or detalle_de_crear or poll_job"`
Expected: FAIL (hay `<template>`, 30 tarjetas, rutas 404).

- [ ] **Step 3: Crear `_crear_tarjetas.html`**

Mover la tarjeta (el `<div class="generado" …>` de `_tab_creativeflowplus.html` desde `{% for item in creative_flow_items %}` hasta el cierre del `.generado-pie`, líneas ~230-297) a una macro. Cambios dentro del bloque movido: quitar los tres `<script>iniciarPolling(...)</script>` y poner `data-poll-job="{{ … }}"` en su `div.barra-progreso`; agregar `data-detalle` a la tarjeta.

```jinja
{# Tarjetas de Crear (spec 2026-09-28 «tarjetas ligeras»): la página y
   /crear/tarjetas pintan lo mismo. Sin <template> de detalle (lo trae
   /creative_flow/<id>/detalle al abrir) y sin <script>: las barras llevan
   data-poll-job y base.html arranca el sondeo. #}
{% macro tarjeta_crear(item) %}
    <div class="generado" data-cf="{{ item.id }}" data-detalle="{{ url_for('cf_detalle', cliente=cliente, cf_id=item.id) }}" tabindex="0" role="button">
      … (el contenido actual de la tarjeta, líneas ~231-297, con:)
          <div class="barra-progreso" id="trabajo-{{ item.trabajo.job_id }}" data-poll-job="{{ item.trabajo.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div></div>
          <div class="progreso-texto">{{ _('Generando… 0%% · 0s') }}</div>
      … (igual para item.trabajo_director e item.trabajo_revision; sin los <script>)
    </div>
{% endmacro %}

{% macro lista_crear(items, desde, total) %}
    {% for item in items %}{{ tarjeta_crear(item) }}{% endfor %}
    {% if desde + (items | length) < total %}
    <button type="button" class="btn-sm generados-mas" data-siguiente="{{ desde + (items | length) }}">{{ _('Ver más (quedan %(n)s)', n=total - desde - (items | length)) }}</button>
    {% endif %}
{% endmacro %}
```

- [ ] **Step 4: Crear `_crear_detalle.html`**

Mover el contenido del `<template class="generado-detalle">` (líneas ~298-403: `div.detalle-media` + `div.detalle-info`) a:

```jinja
{% from "_revision_doctrina.html" import revision_doctrina %}
{# Detalle de una pieza de Crear: lo que antes iba en el <template> de la
   tarjeta. Lo pide el modal por fetch (/creative_flow/<id>/detalle). #}
{% macro detalle_crear(item) %}
        <div class="detalle-media">
          … (contenido actual, tal cual)
        </div>
        <div class="detalle-info">
          … (contenido actual, tal cual)
        </div>
{% endmacro %}
```

Y crear la plantilla de respuesta `templates/_crear_detalle_respuesta.html` con una sola línea: `{% from "_crear_detalle.html" import detalle_crear with context %}{{ detalle_crear(item) }}` (la ruta la renderiza con `item` y `cliente`). Lo mismo para las tarjetas: `templates/_crear_tarjetas_respuesta.html` = `{% from "_crear_tarjetas.html" import lista_crear with context %}{{ lista_crear(items, desde, total) }}`.

- [ ] **Step 5: La página usa las macros**

En `_tab_creativeflowplus.html`, arriba: `{% from "_crear_tarjetas.html" import lista_crear with context %}`. El bloque `#creativeflowplus-resultados` queda:

```jinja
<div id="creativeflowplus-resultados" style="margin-top:2rem;">
  <div style="display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap;">
    <h3 style="margin:0;">{{ _('Generados (%(n)s)', n=crear_total) }}</h3>
    <span class="vacio" style="padding:0;font-size:.78rem;">{{ _('Toca una pieza para ver el detalle, descargarla o crear otra a partir de ella.') }}</span>
  </div>
  {% if not crear_total %}
  <p class="vacio">{{ _('Todavía no has generado nada en Crear.') }}</p>
  {% endif %}
  <div class="generados-grid" id="crear-generados" data-tarjetas="{{ url_for('crear_tarjetas', cliente=cliente) }}">
    {{ lista_crear(crear, 0, crear_total) }}
  </div>
</div>
```

Quitar el `{% from "_revision_doctrina.html" import revision_doctrina %}` de la línea 1 si ya no se usa en esa plantilla (buscar `revision_doctrina(` fuera del detalle).

- [ ] **Step 6: Rutas**

En `dashboard.py`, junto a `cf_descartar`:

```python
@app.route("/cliente/<cliente>/crear/tarjetas")
def crear_tarjetas(cliente):
    """«Ver más» de Crear: las TARJETAS_POR_PAGINA siguientes (fragmento HTML)."""
    desde = _pagina_desde(request.args.get("desde"))
    items = _creative_flow_items(cliente)
    return render_template("_crear_tarjetas_respuesta.html", cliente=cliente,
                           items=items[desde:desde + TARJETAS_POR_PAGINA], desde=desde, total=len(items))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/detalle")
def cf_detalle(cliente, cf_id):
    """El detalle de una pieza (lo que antes iba embebido en un <template>);
    el modal lo pide al abrir la tarjeta. 404 si no es de este proyecto."""
    item = _creative_flow_item(cliente, cf_id)
    if item is None:
        abort(404)
    return render_template("_crear_detalle_respuesta.html", cliente=cliente, item=item)
```

- [ ] **Step 7: JS del modal de Crear, delegado**

Reemplazar el script del modal (`var modal = document.getElementById('generado-modal'); … document.querySelectorAll('#creativeflowplus-resultados .generado').forEach(...)`) por:

```js
  (function () {
    var modal = document.getElementById('generado-modal');
    var cuerpo = document.getElementById('generado-modal-cuerpo');
    var zona = document.getElementById('creativeflowplus-resultados');
    if (!modal || !zona) return;
    function abrir(card) {
      if (!card.dataset.detalle) return;
      abrirDetalleRemoto(modal, cuerpo, card.dataset.detalle, null);
    }
    // Delegado sobre la zona: las tarjetas que agrega «Ver más» funcionan igual.
    zona.addEventListener('click', function (e) {
      var mas = e.target.closest('[data-siguiente]');
      if (mas) { cargarMas(mas); return; }
      var card = e.target.closest('.generado');
      if (card && !e.target.closest('form, a, button')) abrir(card);
    });
    zona.addEventListener('keydown', function (e) {
      var card = e.target.closest('.generado');
      if (!card || e.target !== card) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(card); }
    });
    // Reproducir al pasar el mouse; relatedTarget evita repetir al moverse
    // dentro de la misma tarjeta.
    zona.addEventListener('mouseover', function (e) {
      var card = e.target.closest('.generado');
      if (!card || card.contains(e.relatedTarget)) return;
      var v = card.querySelector('.generado-media video');
      if (v) v.play().catch(function () {});
    });
    zona.addEventListener('mouseout', function (e) {
      var card = e.target.closest('.generado');
      if (!card || card.contains(e.relatedTarget)) return;
      var v = card.querySelector('.generado-media video');
      if (v) { v.pause(); v.currentTime = 0; }
    });
    function cargarMas(boton) {
      var grid = boton.closest('.generados-grid');
      boton.disabled = true;
      fetch(grid.dataset.tarjetas + '?desde=' + encodeURIComponent(boton.dataset.siguiente), { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (html) { boton.remove(); grid.insertAdjacentHTML('beforeend', html); })
        .catch(function () { boton.disabled = false; });
    }
    // (el listener 'change' del costo A+B sobre `cuerpo`, el botón cerrar, el
    //  clic en el fondo y el 'close' que vacía el cuerpo quedan como están)
  })();
```

- [ ] **Step 8: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py tests/test_rutas_crear_director.py tests/test_rutas_mi_musica.py tests/test_tareas_doctrina.py`
Expected: PASS las nuevas; las viejas que buscaban el detalle en la página fallan — se arreglan en Task 5 (anotar cuáles).

- [ ] **Step 9: Commit**

```bash
git add templates/_crear_tarjetas.html templates/_crear_detalle.html templates/_crear_tarjetas_respuesta.html templates/_crear_detalle_respuesta.html templates/_tab_creativeflowplus.html dashboard.py tests/test_tarjetas_ligeras.py
git commit -m "Tarjetas ligeras (3/6): Crear pinta 24 tarjetas, el detalle llega por fetch y «Ver más» trae el resto"
```

---

### Task 4: Final edition — igual que Crear, con el enlace directo `#final?cf=`

**Files:**
- Create: `templates/_final_tarjetas.html`, `templates/_final_detalle.html`, `templates/_final_tarjetas_respuesta.html`, `templates/_final_detalle_respuesta.html`
- Modify: `templates/_tab_final.html` (todo el cuerpo), `dashboard.py` (rutas junto a `cf_detalle`)
- Test: `tests/test_tarjetas_ligeras.py` (agregar)

**Interfaces:**
- Produces: rutas `final_tarjetas` (`GET /cliente/<cliente>/final/tarjetas?lista=videos|finales&desde=N`, 400 con otra `lista`), `fe_detalle_video` (`GET /cliente/<cliente>/creative_flow/<cf_id>/final/detalle`), `fe_detalle_final` (`GET /cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/detalle`); macros `tarjeta_video_fe(item)`, `tarjeta_final_fe(item, f)`, `lista_videos_fe(items, desde, total)`, `lista_finales_fe(pares, desde, total)`, `detalle_video_fe(item)`, `detalle_final_fe(item, f)`.
- Consumes: Task 1 (`_creative_flow_item`, `_listas_crear_final`, `_contexto_final_edition`), Task 2 (`abrirDetalleRemoto`), `editor_angulo`, `bloque_organico`, `window.iniciarEditoresAngulo`.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_tarjetas_ligeras.py (agregar)
def test_final_pinta_24_videos_y_finales_sin_detalle_embebido(app):
    _sembrar(30, con_final=True, guion=True)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    final = html.split('id="tab-final"')[1].split('id="tab-experimentos"')[0]
    assert "<template" not in final and "<script>iniciarPolling" not in final
    videos = final.split('id="fe-videos"')[1].split('id="fe-finales"')[0]
    finales = final.split('id="fe-finales"')[1].split('id="fe-modal"')[0]
    assert videos.count('class="generado"') == 24 and 'data-siguiente="24"' in videos
    assert finales.count('class="generado generado-final"') == 24 and 'data-siguiente="24"' in finales
    assert "Videos listos (30)" in final and "Finales (30)" in final
    assert final.count("/final/detalle\"") == 24 and final.count("/final/cf_20260901_000000_") == 24


def test_final_ver_mas_y_lista_invalida(app):
    _sembrar(26, con_final=True)
    c = app["c"]
    assert c.get("/cliente/acme/final/tarjetas?lista=videos&desde=24").get_data(as_text=True).count('class="generado"') == 2
    assert c.get("/cliente/acme/final/tarjetas?lista=finales&desde=24").get_data(as_text=True).count('generado-final') == 2
    assert c.get("/cliente/acme/final/tarjetas?lista=x").status_code == 400


def test_detalle_de_video_y_de_final(app):
    (con_guion,) = _sembrar(1, con_final=True, guion=True)
    (sin_guion,) = _sembrar(1, desde=1)
    (imagen,) = _sembrar(1, desde=2, tipo="imagen")
    c = app["c"]
    html = c.get(f"/cliente/acme/creative_flow/{con_guion}/final/detalle").get_data(as_text=True)
    assert "Producir finales" in html and "Guardar guion" in html and "angulo-editor" in html
    html = c.get(f"/cliente/acme/creative_flow/{sin_guion}/final/detalle").get_data(as_text=True)
    assert "Preparar guion" in html and "Producir finales" not in html
    assert c.get(f"/cliente/acme/creative_flow/{imagen}/final/detalle").status_code == 404
    assert c.get(f"/cliente/otro/creative_flow/{con_guion}/final/detalle").status_code == 404
    fid = f"{con_guion}__es_CO"
    html = c.get(f"/cliente/acme/creative_flow/{con_guion}/final/{fid}/detalle").get_data(as_text=True)
    assert "Capas" in html and "Descartar" in html
    assert c.get(f"/cliente/acme/creative_flow/{sin_guion}/final/{fid}/detalle").status_code == 404


def test_final_js_abre_por_enlace_aunque_la_tarjeta_no_este(app):
    js = _plantilla("_tab_final.html")
    assert "template.generado-detalle" not in js and "data-detalle" in js
    assert "/final/detalle" in js and "abrirDetalleRemoto(" in js and "iniciarEditoresAngulo" in js
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py -k "final"`
Expected: FAIL.

- [ ] **Step 3: `_final_tarjetas.html`**

Mover las dos tarjetas de `_tab_final.html` (video: líneas ~32-73; final: ~240-262) a macros, sin `<template>`, con `data-detalle` y con `data-poll-job` en vez de `<script>` (el contenedor oculto del trabajo del editor se conserva con `data-poll-job`):

```jinja
{% macro tarjeta_video_fe(item) %}
    <div class="generado" data-cf="{{ item.id }}" data-detalle="{{ url_for('fe_detalle_video', cliente=cliente, cf_id=item.id) }}" tabindex="0" role="button">
      … (contenido actual; cada div.barra-progreso con data-poll-job="{{ …job_id }}"; sin <script>)
    </div>
{% endmacro %}

{% macro tarjeta_final_fe(item, f) %}
    {% set _bandera = paises_fe[f.pais].bandera if f.pais in paises_fe else "" %}
    <div class="generado generado-final" data-cf="{{ f.id }}" data-detalle="{{ url_for('fe_detalle_final', cliente=cliente, cf_id=item.id, final_id=f.id) }}" tabindex="0" role="button">
      … (contenido actual; la barra de f.trabajo con data-poll-job; sin <script>)
    </div>
{% endmacro %}

{% macro lista_videos_fe(items, desde, total) %}
    {% for item in items %}{{ tarjeta_video_fe(item) }}{% endfor %}
    {% if desde + (items | length) < total %}
    <button type="button" class="btn-sm generados-mas" data-siguiente="{{ desde + (items | length) }}">{{ _('Ver más (quedan %(n)s)', n=total - desde - (items | length)) }}</button>
    {% endif %}
{% endmacro %}

{% macro lista_finales_fe(pares, desde, total) %}
    {% for item, f in pares %}{{ tarjeta_final_fe(item, f) }}{% endfor %}
    {% if desde + (pares | length) < total %}
    <button type="button" class="btn-sm generados-mas" data-siguiente="{{ desde + (pares | length) }}">{{ _('Ver más (quedan %(n)s)', n=total - desde - (pares | length)) }}</button>
    {% endif %}
{% endmacro %}
```

- [ ] **Step 4: `_final_detalle.html`**

```jinja
{% from "_organico_publicar.html" import bloque_organico with context %}
{% from "_angulo_editor.html" import editor_angulo %}
{% macro detalle_video_fe(item) %}
        … (el contenido actual del <template> de un video: detalle-media + detalle-info, líneas ~74-233)
{% endmacro %}
{% macro detalle_final_fe(item, f) %}
        {% set _bandera = paises_fe[f.pais].bandera if f.pais in paises_fe else "" %}
        … (el contenido actual del <template> de una final, líneas ~263-320)
{% endmacro %}
```

Respuestas: `_final_detalle_respuesta.html` = `{% from "_final_detalle.html" import detalle_video_fe, detalle_final_fe with context %}{% if f is defined and f %}{{ detalle_final_fe(item, f) }}{% else %}{{ detalle_video_fe(item) }}{% endif %}`; `_final_tarjetas_respuesta.html` = `{% from "_final_tarjetas.html" import lista_videos_fe, lista_finales_fe with context %}{% if lista == "videos" %}{{ lista_videos_fe(items, desde, total) }}{% else %}{{ lista_finales_fe(items, desde, total) }}{% endif %}`.

- [ ] **Step 5: `_tab_final.html` usa las macros**

Quitar los `{% set _videos … %}` / `{% set _n … %}` y las dos secciones pasan a:

```jinja
{% from "_final_tarjetas.html" import lista_videos_fe, lista_finales_fe with context %}
…
  <h3>Videos listos ({{ final_videos_total }})</h3>
  {% if not final_videos_total %}<div class="estado-vacio">…</div>{% endif %}
  <div class="generados-grid" id="fe-videos" data-tarjetas="{{ url_for('final_tarjetas', cliente=cliente, lista='videos') }}">
    {{ lista_videos_fe(final_videos, 0, final_videos_total) }}
  </div>
…
  <h3>Finales ({{ finales_total }})</h3>
  {% if not finales_total %}<p class="vacio">…</p>{% endif %}
  <div class="generados-grid" id="fe-finales" data-tarjetas="{{ url_for('final_tarjetas', cliente=cliente, lista='finales') }}">
    {{ lista_finales_fe(finales, 0, finales_total) }}
  </div>
```

- [ ] **Step 6: Rutas**

```python
@app.route("/cliente/<cliente>/final/tarjetas")
def final_tarjetas(cliente):
    lista = request.args.get("lista")
    if lista not in ("videos", "finales"):
        abort(400)
    desde = _pagina_desde(request.args.get("desde"))
    listas = _listas_crear_final(_creative_flow_items(cliente))
    if lista == "videos":
        todos = [i for i in _creative_flow_items(cliente) if i.get("estado") == "video_listo" and (i.get("tipo") or "video") != "imagen"]
    …
```

Mejor sin recalcular dos veces: `_listas_crear_final` recibe `n=None` para devolver las listas completas:

```python
def _listas_crear_final(items, n=TARJETAS_POR_PAGINA):
    videos = [...]; finales = [...]
    corte = slice(0, n) if n else slice(None)
    return {"crear": items[corte], ..., "final_videos": videos[corte], ..., "finales": finales[corte], ...}
```

y la ruta:

```python
    completas = _listas_crear_final(_creative_flow_items(cliente), n=None)
    todos = completas["final_videos"] if lista == "videos" else completas["finales"]
    return render_template("_final_tarjetas_respuesta.html", cliente=cliente, lista=lista,
                           items=todos[desde:desde + TARJETAS_POR_PAGINA], desde=desde, total=len(todos),
                           **_contexto_final_edition(cliente))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/detalle")
def fe_detalle_video(cliente, cf_id):
    item = _creative_flow_item(cliente, cf_id)
    if item is None or item.get("estado") != "video_listo" or (item.get("tipo") or "video") == "imagen":
        abort(404)
    return render_template("_final_detalle_respuesta.html", cliente=cliente, item=item, f=None, **_contexto_final_edition(cliente))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/final/<final_id>/detalle")
def fe_detalle_final(cliente, cf_id, final_id):
    item = _creative_flow_item(cliente, cf_id)
    f = next((x for x in (item or {}).get("finales") or [] if x["id"] == final_id), None)
    if item is None or f is None:
        abort(404)
    return render_template("_final_detalle_respuesta.html", cliente=cliente, item=item, f=f, **_contexto_final_edition(cliente))
```

(Actualizar la prueba de Task 1 `test_pagina_desde_y_listas` si cambia la firma: con `n=None` devuelve todo.)

- [ ] **Step 7: JS de Final, delegado, con enlace directo**

En el script del modal de `_tab_final.html`, reemplazar `abrir`, el `panel.querySelectorAll('.generado')` y `desdeHash` por:

```js
    function alInsertar(c) { if (window.iniciarEditoresAngulo) window.iniciarEditoresAngulo(c); }
    function abrir(card) {
      if (!card.dataset.detalle) return;
      abrirDetalleRemoto(modal, cuerpo, card.dataset.detalle, alInsertar);
    }
    panel.addEventListener('click', function (e) {
      var mas = e.target.closest('[data-siguiente]');
      if (mas) { cargarMas(mas); return; }
      var card = e.target.closest('.generado');
      if (card && !e.target.closest('form, a, button')) abrir(card);
    });
    panel.addEventListener('keydown', function (e) {
      var card = e.target.closest('.generado');
      if (!card || e.target !== card) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(card); }
    });
    panel.addEventListener('mouseover', function (e) {
      var card = e.target.closest('.generado');
      if (!card || card.contains(e.relatedTarget)) return;
      var v = card.querySelector('.generado-media video');
      if (v) v.play().catch(function () {});
    });
    panel.addEventListener('mouseout', function (e) {
      var card = e.target.closest('.generado');
      if (!card || card.contains(e.relatedTarget)) return;
      var v = card.querySelector('.generado-media video');
      if (v) { v.pause(); v.currentTime = 0; }
    });
    function cargarMas(boton) {
      var grid = boton.closest('.generados-grid');
      boton.disabled = true;
      fetch(grid.dataset.tarjetas + '&desde=' + encodeURIComponent(boton.dataset.siguiente), { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (html) { boton.remove(); grid.insertAdjacentHTML('beforeend', html); })
        .catch(function () { boton.disabled = false; });
    }
    // #final?cf=<id>: abre esa pieza aunque su tarjeta no esté entre las pintadas.
    var URL_DETALLE = {{ url_for('fe_detalle_video', cliente=cliente, cf_id='__CF__')|tojson }};
    function desdeHash() {
      var m = /^#final\?cf=([^&]+)/.exec(location.hash);
      if (!m) return;
      var cf;
      try { cf = decodeURIComponent(m[1]); } catch (e) { return; }
      var card = panel.querySelector('#fe-videos .generado[data-cf="' + CSS.escape(cf) + '"]');
      if (card) { abrir(card); return; }
      abrirDetalleRemoto(modal, cuerpo, URL_DETALLE.replace('__CF__', encodeURIComponent(cf)), alInsertar);
    }
```

Nota: `data-tarjetas` de Final ya trae `?lista=…`, por eso `cargarMas` concatena `&desde=`.

- [ ] **Step 8: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tarjetas_ligeras.py tests/test_tab_final.py tests/test_rutas_final_edition.py`
Expected: nuevas PASS; anotar las viejas que fallan para Task 5.

- [ ] **Step 9: Commit**

```bash
git add templates/_final_*.html templates/_tab_final.html dashboard.py tests/test_tarjetas_ligeras.py
git commit -m "Tarjetas ligeras (4/6): Final edition pinta 24 videos y 24 finales, detalle por fetch y #final?cf= sin tarjeta"
```

---

### Task 5: Pruebas existentes, prueba de peso, catálogo de traducciones

**Files:**
- Modify: `tests/test_tab_final.py`, `tests/test_rutas_final_edition.py`, `tests/test_rutas_crear_director.py`, `tests/test_rutas_mi_musica.py`, `tests/test_tareas_doctrina.py`, `tests/test_rutas_configuracion.py`, `tests/test_perf_pagina_proyecto.py`, `translations/en/LC_MESSAGES/messages.po` (+ `.mo`)

- [ ] **Step 1: Prueba de peso**

```python
# tests/test_perf_pagina_proyecto.py (agregar)
def test_la_pagina_no_embebe_detalles_ni_pasa_de_24_tarjetas(app):
    _sembrar(40)
    html = app["c"].get("/cliente/acme").data.decode()
    assert '<template class="generado-detalle">' not in html
    for grid in ("crear-generados", "fe-videos", "fe-finales"):
        seg = html.split(f'id="{grid}"')[1].split("</div>\n</div>")[0] if f'id="{grid}"' in html else ""
        assert seg.count('class="generado') <= 24, grid
```

- [ ] **Step 2: Correr la suite completa y anotar los fallos**

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider 2>&1 | grep -E "^FAILED|passed|failed"`

- [ ] **Step 3: Arreglar cada prueba vieja: el mismo assert, HTML desde la ruta de detalle**

Regla para cada fallo: si la prueba partía la página en `<template class="generado-detalle">` o buscaba texto del detalle («Producir finales», «Preparar guion», «Llevar a final edition», «Revisar con la doctrina», el formulario del guion) en `/cliente/acme`, pedir `GET /cliente/acme/creative_flow/<cf>/detalle` (Crear) o `…/final/detalle` (Final) y afirmar sobre esa respuesta. Ejemplo (test_tab_final.py ~409):

```python
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    tarjeta = html.split('id="fe-videos"')[1].split('id="fe-finales"')[0]
    detalle = app["c"].get(f"/cliente/acme/creative_flow/{cf}/final/detalle").get_data(as_text=True)
```

Las pruebas de contrato del JS (`test_tab_final.py` ~527-541, «generado-detalle in js») pasan a afirmar `"data-detalle" in js and "abrirDetalleRemoto(" in js and "iniciarEditoresAngulo" in js`.

- [ ] **Step 4: Catálogo de traducciones**

Run: `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py pendientes`
Traducir en el `.po` (solo esas `msgstr`, editando las líneas; no reescribir el archivo):
- «Ver más (quedan %(n)s)» → «Show more (%(n)s left)»
- «Cargando…» → «Loading…»
- «No se pudo cargar el detalle. Recarga la página.» → «The detail could not be loaded. Reload the page.»
Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 5: Suite completa en verde**

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider 2>&1 | tail -3`
Expected: `N passed`, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add tests/ translations/
git commit -m "Tarjetas ligeras (5/6): las pruebas piden el detalle a su ruta; prueba de peso; traducciones"
```

---

### Task 6: Prueba real, despliegue y documentación

**Files:**
- Modify: `CLAUDE.md` (párrafo «Rendimiento y almacenamiento»), memoria del proyecto

- [ ] **Step 1: Medir en el VPS con la base real (test client como admin, sin contraseña)**

Script en el scratchpad ejecutado con `TZ=America/Bogota PYTHONPATH=. venv/bin/python3` sobre un worktree del VPS en la rama (o tras el despliegue): tamaño de `/cliente/happyflops` (meta: < 700 KB), tiempo y tamaño de `…/creative_flow/<cf real>/detalle` y `…/final/detalle` (meta: < 0,3 s), `…/crear/tarjetas?desde=24` (94 tarjetas restantes en 4 páginas), `…/final/tarjetas?lista=videos&desde=24`.

- [ ] **Step 2: Desplegar**

`git push origin tarjetas-ligeras:main` (fast-forward), en el VPS `git pull --ff-only`, respaldo de la base, `systemctl restart iaplusyou` (solo web: no cambia nada del worker), `curl /login` 200, journal sin errores.

- [ ] **Step 3: Verificar en el navegador integrado (prueba visual sin contraseña, memoria `verificar-ui-sin-contrasena`)**

Abrir una tarjeta de Crear y una de Final (el modal se llena), «Ver más» agrega tarjetas, `#final?cf=<id de una pieza fuera de las 24>` abre su detalle.

- [ ] **Step 4: Documentar**

En CLAUDE.md, párrafo «Rendimiento y almacenamiento»: las tarjetas de Crear/Final van en macros (`_crear_tarjetas.html`, `_final_tarjetas.html`), el detalle se pide a `…/detalle` al abrir (`abrirDetalleRemoto` en base.html), 24 por lista con «Ver más» (`crear_tarjetas`, `final_tarjetas`), y la regla: ninguna barra lleva `<script>`, todas `data-poll-job` (`arrancarSondeos`). Actualizar la memoria de la auditoría y la de producción.

- [ ] **Step 5: Commit final**

```bash
git add CLAUDE.md
git commit -m "Tarjetas ligeras (6/6): CLAUDE.md"
```
