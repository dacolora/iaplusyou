# Sprints tablero — entrega 2: ideas, generar y piezas dentro del panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the campaign's ideas, the generation cost gate and the review of its pieces into the board's side panel as three tabs (Armar · Ideas · Piezas), register the real spend of «Proponer ideas», and keep a renewed sprint-wide review page.

**Architecture:** The panel fragment (`sprints.campana_panel`) renders the three tabs at once (`_sprint_panel.html` shell + `_sprint_panel_armar.html`, `_sprint_panel_ideas.html`, `_sprint_panel_piezas.html`); the client only toggles which one is visible and remembers it in the URL (`?panel=<cid>&paso=…`). Existing idea/lote/piece routes gain JSON answers for the panel and redirect their form posts back to the panel. Pure helpers in `sprints/tablero.py` decide the default tab and the tab counters; `tareas/sprints.py` registers the spend of each ideas proposal with the tokens `sprints/ideas.py` now counts.

**Tech Stack:** Flask Blueprint + Jinja2, vanilla JS (delegated listeners in `templates/sprint_detalle.html`), SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-sprints-tablero-entrega2-design.md`

## Global Constraints

- Work only in the worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/base-visual`, branch `sprints-tablero-2` (based on `main` 093f10e, which already contains doctrina bloque 2). Never `cd` into `/Users/colorado/Documents/GitHub/iaplusyou` itself. Tests: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider <paths>` from the worktree (fast suite: add `-m "not slow"`).
- No migrations.
- Tabs are exactly `armar`, `ideas`, `piezas` (labels «Armar», «Ideas», «Piezas»); URL `?panel=<cid>&paso=armar|ideas|piezas`; an invalid `paso` falls back to the default tab.
- Default tab from `tablero.siguiente_paso(c)["clave"]`: `referentes` → armar; `aprobar`, `ideas`, `generar` → ideas; `generando`, `errores`, `revisar`, `lista` → piezas.
- Consciencia rule (already in `sprints.ideas.fijos_de`): the campaign's wins, else the persona's. The persona selector «Qué tanto sabe <persona>» is NOT shown in the panel.
- Every paid action shows its price before the click; nothing is relaunched automatically (`max_intentos=1`); proposing ideas registers its real spend with `gastos.registrar_seguro(..., "ideas", ...)`, also when the answer was unusable.
- Scripts inside fetched fragments never run: all panel JS lives in `templates/sprint_detalle.html` (delegated on `#tablero-panel`). After inserting a panel fragment, call `window.iniciarEditoresAngulo(cuerpo)` (from `static/angulo.js`).
- After any successful autosave, delete `data-sucio` from the saved fields (base.html marks edited fields; a leftover mark blocks the auto-reload when a background job finishes).
- UI copy in Spanish, informal «tú». CSS colors only through `var(--…)` (exceptions already allowed: `#fff` on `var(--accent-grad)`; the existing translucent backdrop); never `color: var(--accent)` for text (use `var(--accent-texto)`, enforced by `tests/test_modo_oscuro.py`). Nothing may scroll the page sideways at 375 px.
- Commit after each task with a Spanish message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never use `git stash`.

## File Structure

- Modify `sprints/tablero.py` — `PASOS`, `paso_por_defecto`, `resolver_paso`, `pestanas`.
- Modify `gastos.py` — estimator `proponer_ideas`.
- Modify `sprints/ideas.py` — `proponer(..., uso=None)` counts tokens with `analisis._llamar_contando`.
- Modify `tareas/sprints.py` — `encolar_ideas` with `max_intentos=1`; `ejecutar_proponer_ideas` registers spend.
- Modify `sprints/revision.py` — `aprobar_pasaron_qa(..., campana_id=None)`.
- Modify `sprints/rutas.py` — panel tabs context, `campana_piezas`, JSON answers, redirects to the panel, `campana_ideas` redirect, revision page context.
- Rewrite `templates/_sprint_panel.html` as the tab shell; create `templates/_sprint_panel_armar.html`, `templates/_sprint_panel_ideas.html`, `templates/_sprint_panel_piezas.html`.
- Delete `templates/campana_ideas.html`.
- Modify `templates/sprint_detalle.html` (load `angulo.js`, tab JS, ideas/generar/piezas JS), `templates/sprint_revision.html`, `templates/_sprint_lote_modal.html` (comment), `static/style.css` (append to the «Tablero de Sprints (2026-09-26)» block).
- Tests: create `tests/test_sprints_tablero_entrega2.py`; modify `tests/test_sprints_tablero.py`, `tests/test_sprints_ideas.py`, `tests/test_tareas_sprints.py`, `tests/test_gastos.py`, `tests/test_rutas_sprints.py`, `tests/test_sprints_tablero_rutas.py`.

---

### Task 1: Pestañas (puro), precio y gasto real de «Proponer ideas»

**Files:**
- Modify: `sprints/tablero.py`, `gastos.py`, `sprints/ideas.py` (`proponer`), `tareas/sprints.py` (`encolar_ideas`, `ejecutar_proponer_ideas`)
- Test: `tests/test_sprints_tablero.py`, `tests/test_gastos.py`, `tests/test_sprints_ideas.py`, `tests/test_tareas_sprints.py`

**Interfaces:**
- Produces:
  - `sprints.tablero.PASOS = ("armar", "ideas", "piezas")`
  - `sprints.tablero.paso_por_defecto(c) -> str`, `sprints.tablero.resolver_paso(pedido, c) -> str`
  - `sprints.tablero.pestanas(c) -> {"armar": "✓"|"L/O", "ideas": "A/P", "piezas": "T/P"}`
  - `gastos.estimar("proponer_ideas", n=N)` → `{"usd", "texto", "detalle"}` with usd = `gastos.IDEAS_BASE_USD + gastos.IDEAS_POR_IDEA_USD * max(1, N)`
  - `sprints.ideas.proponer(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None, uso=None)`: when `uso` is a dict, adds `uso["entrada"]`/`uso["salida"]` tokens of every Claude call it makes (also before raising).
  - Task `sprint_proponer_ideas`: `max_intentos=1`; registers gasto tipo `"ideas"`, referencia `f"idea:proponer:{campana_id}{ref_sufijo(tarea)}"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_tablero.py`:

```python
def test_paso_por_defecto_sigue_el_siguiente_paso():
    assert tablero.paso_por_defecto(_c(referencias_listas=3)) == "armar"
    assert tablero.paso_por_defecto(_c()) == "ideas"                                   # proponer ideas
    assert tablero.paso_por_defecto(_c(ideas=[_idea("propuesta", True)])) == "ideas"  # aprobar
    assert tablero.paso_por_defecto(_c(ideas=[_idea(sin_sesion=True), _idea(sin_sesion=True)])) == "ideas"  # generar
    en_curso = [_idea(estado="generando"), _idea(estado="listo")]
    assert tablero.paso_por_defecto(_c(ideas=en_curso, piezas=en_curso)) == "piezas"
    listas = [_idea(estado="listo"), _idea(estado="listo", revision="aprobada")]
    assert tablero.paso_por_defecto(_c(ideas=listas, piezas=listas)) == "piezas"


def test_resolver_paso():
    assert tablero.resolver_paso("piezas", _c(referencias_listas=0)) == "piezas"
    assert tablero.resolver_paso("otra", _c(referencias_listas=0)) == "armar"
    assert tablero.resolver_paso(None, _c()) == "ideas"
    assert tablero.PASOS == ("armar", "ideas", "piezas")


def test_pestanas_cuentan_lo_de_cada_paso():
    ideas = [_idea("aprobada", estado="listo"), _idea("propuesta", True), _idea("descartada", True)]
    piezas = [ideas[0]]
    assert tablero.pestanas(_c(referencias_listas=3, ideas=ideas, piezas=piezas)) == \
        {"armar": "3/5", "ideas": "1/2", "piezas": "1/2"}
    assert tablero.pestanas(_c())["armar"] == "✓"
```

Append to `tests/test_gastos.py`:

```python
def test_estimar_proponer_ideas_por_numero_de_ideas():
    import gastos
    tres = gastos.estimar("proponer_ideas", n=3)
    assert tres["usd"] == round(gastos.IDEAS_BASE_USD + 3 * gastos.IDEAS_POR_IDEA_USD, 4)
    assert "aprox" in tres["texto"] and tres["detalle"] == "3 idea(s) con Claude"
    assert gastos.estimar("proponer_ideas", n=0)["usd"] == gastos.estimar("proponer_ideas", n=1)["usd"]
```

In `tests/test_sprints_ideas.py`:
- Add this helper near the top (after the imports):

```python
def _contando(falso):
    """Adapta un `_llamar` falso (devuelve texto) a `_llamar_contando`
    (texto, tokens_entrada, tokens_salida): `ideas.proponer` cuenta tokens
    para registrar el gasto real desde la entrega 2 de Sprints."""
    return lambda content, max_tokens=700, system=None: (falso(content, max_tokens=max_tokens, system=system), 100, 50)
```

- Every test that feeds `ideas.proponer` through `monkeypatch.setattr(analisis, "_llamar", X)` must patch `_llamar_contando` instead: `monkeypatch.setattr(analisis, "_llamar_contando", _contando(X))`. For the test that asserts proponer does NOT call Claude (`… throw(AssertionError("no debía llamar"))`), patch `_llamar_contando` with the same thrower. Grep the file for `"_llamar"` and decide each case by what the test calls (`proponer`/`otra idea` → change; `analisis.analizar`, `reescribir` or anything else → leave). Also grep the other test files (`grep -rn "ideas.proponer\|_llamar\"" tests/`) for the same pattern.
- Append:

```python
def test_proponer_cuenta_los_tokens_de_todas_las_llamadas(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    respuestas = ["esto no es json", json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})]
    monkeypatch.setattr(analisis, "_llamar_contando",
                        lambda content, max_tokens=700, system=None: (respuestas.pop(0), 1000, 300))
    uso = {"entrada": 0, "salida": 0}
    ideas.proponer("acme", cid, 1, 1, uso=uso)
    assert uso == {"entrada": 2000, "salida": 600}          # la respuesta inválida y el reintento


def test_proponer_cuenta_los_tokens_aunque_falle(base_temporal, monkeypatch):
    import pytest
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: ("nada", 800, 200))
    uso = {"entrada": 0, "salida": 0}
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.proponer("acme", cid, 1, 1, uso=uso)
    assert uso == {"entrada": 1600, "salida": 400}
```

(`IDEA_V`, `IDEA_I` and `_ctx` already exist in that file.)

In `tests/test_tareas_sprints.py`:
- In `test_proponer_ideas_tarea_y_encolar`, change the `ideas.proponer` lambda to accept `uso=None`: `lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None: [1, 2]`, and if it checks `max_intentos` of the enqueued task, expect `1`.
- Append:

```python
def test_proponer_ideas_registra_el_gasto_real(base_temporal, monkeypatch):
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)

    def proponer(c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None):
        uso["entrada"] += 5000
        uso["salida"] += 2000
        return [11, 12]
    monkeypatch.setattr(ideas, "proponer", proponer)
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_proponer_ideas"]({"id": 7, "payload": {"cliente": "acme", "campana_id": cid}})
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]
    assert len(filas) == 1 and filas[0]["usd"] > 0 and filas[0]["referencia"] == f"idea:proponer:{cid}:t7"


def test_proponer_ideas_registra_lo_pagado_si_falla(base_temporal, monkeypatch):
    import pytest
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)

    def proponer(c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None):
        uso["entrada"] += 3000
        raise ideas.AnalisisInvalido("Claude no devolvió JSON.")
    monkeypatch.setattr(ideas, "proponer", proponer)
    tareas.cargar_todas()
    with pytest.raises(ideas.AnalisisInvalido):
        tareas.REGISTRO["sprint_proponer_ideas"]({"id": 8, "payload": {"cliente": "acme", "campana_id": cid}})
    filas = [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]
    assert len(filas) == 1 and "no sirvió" in filas[0]["detalle"]


def test_proponer_ideas_sin_llamadas_no_registra_gasto(base_temporal, monkeypatch):
    import gastos
    import tareas
    from sprints import datos, ideas
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(ideas, "proponer", lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None, uso=None: [])
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_proponer_ideas"]({"id": 9, "payload": {"cliente": "acme", "campana_id": cid}})
    assert not [f for f in gastos.historial("acme") if f["tipo"] == "ideas"]


def test_encolar_ideas_no_se_reintenta_sola(base_temporal, monkeypatch):
    from tareas import sprints as ts
    vistos = []
    monkeypatch.setattr(ts.trabajos, "encolar", lambda job_id, tipo, payload, **kw: vistos.append(kw) or True)
    ts.encolar_ideas("acme", 5)
    assert vistos[0]["max_intentos"] == 1
```

Check before writing: `gastos.historial(cliente)` returns rows with `tipo`, `usd`, `referencia`, `detalle` (read `gastos.py`; if the function or keys differ, use the real ones and keep the same assertions). `ideas.AnalisisInvalido` is re-exported in `sprints/ideas.py` (`from sprints.analisis import AnalisisInvalido`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero.py tests/test_gastos.py tests/test_sprints_ideas.py tests/test_tareas_sprints.py`
Expected: FAIL — `AttributeError: module 'sprints.tablero' has no attribute 'paso_por_defecto'`, unknown estimator, `unexpected keyword argument 'uso'`.

- [ ] **Step 3: Implement**

`sprints/tablero.py` — append:

```python
PASOS = ("armar", "ideas", "piezas")
_PASO_POR_CLAVE = {"referentes": "armar", "aprobar": "ideas", "ideas": "ideas", "generar": "ideas",
                   "generando": "piezas", "errores": "piezas", "revisar": "piezas", "lista": "piezas"}


def paso_por_defecto(c):
    """La pestaña del panel que toca según el siguiente paso de la campaña."""
    return _PASO_POR_CLAVE.get(siguiente_paso(c)["clave"], "armar")


def resolver_paso(pedido, c):
    """La pestaña pedida si existe; si no, la que toca."""
    return pedido if pedido in PASOS else paso_por_defecto(c)


def pestanas(c):
    """Lo que dice cada pestaña del panel: «✓» o «listos/objetivo» en Armar,
    aprobadas/planeadas en Ideas y terminadas/planeadas en Piezas."""
    objetivo = int(c.get("referencias_objetivo") or 1)
    listas = int(c.get("referencias_listas") or 0)
    planeadas = int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0)
    vivas = [i for i in c.get("ideas") or [] if i.get("estado_idea") != "descartada"]
    aprobadas = sum(1 for i in vivas if i.get("estado_idea") == "aprobada")
    terminadas = sum(1 for p in c.get("piezas") or [] if p.get("estado") in datos._PIEZA_TERMINADA)
    return {"armar": "✓" if listas >= objetivo else f"{listas}/{objetivo}",
            "ideas": f"{aprobadas}/{planeadas}", "piezas": f"{terminadas}/{planeadas}"}
```

`gastos.py` — next to `TARIFAS` add:

```python
# «Proponer ideas» de Sprints (entrega 2 del tablero): una llamada a Claude con
# la doctrina en el system (caché) y hasta ~1 200 tokens de salida por idea
# (`sprints.ideas.max_tokens_para`). El gasto REAL se registra con los tokens
# medidos (tipo "ideas"); estas dos cifras solo dan el «≈» del botón.
IDEAS_BASE_USD = 0.015
IDEAS_POR_IDEA_USD = 0.012
```

and in `_ESTIMADORES` add:

```python
    "proponer_ideas": lambda n=1, **_: (IDEAS_BASE_USD + IDEAS_POR_IDEA_USD * max(1, int(n or 0)),
                                        f"{max(1, int(n or 0))} idea(s) con Claude"),
```

`sprints/ideas.py` — `proponer` signature gains `uso=None` (last keyword) and its docstring one sentence («`uso`: dict donde se suman los tokens de cada llamada a Claude, para registrar el gasto real incluso si falla.»). Inside `pedir`, replace the line `crudo = analisis._llamar(contenido, max_tokens=tokens, system=system)` with:

```python
        crudo, entrada, salida = analisis._llamar_contando(contenido, max_tokens=tokens, system=system)
        if uso is not None:
            uso["entrada"] = uso.get("entrada", 0) + entrada
            uso["salida"] = uso.get("salida", 0) + salida
```

`tareas/sprints.py`:
- `encolar_ideas`: change `max_intentos=2` to `max_intentos=1` and add the comment `# pagada: nunca se reintenta sola`.
- Replace `ejecutar_proponer_ideas` with:

```python
@registrar("sprint_proponer_ideas")
def ejecutar_proponer_ideas(tarea):
    """Propone ideas con Claude y registra su gasto real (tokens de todas las
    llamadas, incluida la corrección), también cuando la respuesta no sirvió
    — en ese caso la excepción sigue subiendo para que la cola marque error."""
    p = tarea["payload"]
    cliente, campana_id = p["cliente"], int(p["campana_id"])
    uso = {"entrada": 0, "salida": 0}
    referencia = f"idea:proponer:{campana_id}{ref_sufijo(tarea)}"

    def _registrar(detalle):
        if uso["entrada"] or uso["salida"]:
            gastos.registrar_seguro(cliente, "ideas", costo_real(uso["entrada"], uso["salida"]), referencia,
                                    proveedor="anthropic", detalle=detalle,
                                    extra={"tokens_entrada": uso["entrada"], "tokens_salida": uso["salida"],
                                           "modelo": modelo_actual()})
    try:
        creadas = ideas.proponer(cliente, campana_id, n_videos=p.get("n_videos"), n_imagenes=p.get("n_imagenes"),
                                 reemplaza=p.get("reemplaza"), uso=uso)
    except Exception:
        _registrar("proponer ideas · la respuesta no sirvió")
        raise
    _registrar(f"proponer {len(creadas)} idea(s)")
    c = datos.campana(cliente, campana_id)
    if c:
        estado.recalcular(cliente, c["sprint_id"])
    return f"{len(creadas)} ideas propuestas — revísalas y aprueba las que sirvan."
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero.py tests/test_gastos.py tests/test_sprints_ideas.py tests/test_tareas_sprints.py tests/test_rutas_sprints.py`
Expected: PASS. Then the fast suite once (`-m "not slow"`).

- [ ] **Step 5: Commit**

```bash
git add sprints/tablero.py gastos.py sprints/ideas.py tareas/sprints.py tests/test_sprints_tablero.py tests/test_gastos.py tests/test_sprints_ideas.py tests/test_tareas_sprints.py
git commit -m "Sprints tablero 2: pestañas del panel (puro) y gasto real de «Proponer ideas» con su precio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Pestañas del panel y pestaña «Armar»

**Files:**
- Modify: `sprints/rutas.py` (`campana_panel`, `ver`)
- Rewrite: `templates/_sprint_panel.html` (tab shell)
- Create: `templates/_sprint_panel_armar.html`, `templates/_sprint_panel_ideas.html` (placeholder, Task 3 replaces it), `templates/_sprint_panel_piezas.html` (placeholder, Task 4 replaces it)
- Modify: `templates/sprint_detalle.html` (tab JS, describe-reference JS, `data-paso-inicial`), `static/style.css`
- Test: `tests/test_sprints_tablero_entrega2.py` (create)

**Interfaces:**
- Consumes: `tablero.resolver_paso`, `tablero.pestanas`, `tablero.PASOS` (Task 1).
- Produces:
  - Panel fragment root `<div class="panel-campana" data-cid data-paso="armar|ideas|piezas" data-url-campo data-url-sugeridos>`; tab buttons `[data-ir-paso="<paso>"]` (role tab, `aria-selected`); tab bodies `<div data-pestana="<paso>" role="tabpanel" [hidden]>`.
  - `GET …/campanas/<cid>/panel?paso=<paso>` (invalid/absent → default tab).
  - Board: `#tablero-panel[data-paso-inicial]`; `window.tablero` gains `irAPaso(paso)` and `paso()`; `window.tablero.abrir(cid, paso)` (second argument optional: absent keeps the current tab when reopening the same campaign, else the server decides); DOM events `tablero:paso` (detail `{paso}`) and `tablero:cerrado` on `document`.
  - Template contexts used by the next tasks: `_sprint_panel_ideas.html` and `_sprint_panel_piezas.html` are included by the shell with the full panel context.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sprints_tablero_entrega2.py`:

```python
"""Entrega 2 del tablero de Sprints (spec 2026-09-27): pestañas del panel,
ideas, generar y piezas dentro del panel. Fixtures de test_rutas_sprints:
`app` (sesión admin, catálogo falso con espejo_led «Espejo LED»),
`con_ideas` (campaña 2 videos + 1 imagen con una idea de video aprobada y
una de imagen propuesta) y `_con_piezas` (les da sesión de Crear)."""
import json

import pytest

from tests.test_rutas_sprints import _con_piezas, app, con_ideas  # noqa: F401


def _sprint(datos):
    return datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")


def _campana(datos, sid, n_refs=0):
    pid = datos.crear_persona("acme", "Premium")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    for n in range(n_refs):
        datos.agregar_referencia("acme", cid, "imagen", f"https://r2/r{n}.jpg", descripcion="luz lateral")
    return cid


def _panel(c, sid, cid, paso=None):
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel" + (f"?paso={paso}" if paso else "")
    return c.get(url).data.decode()


# ------------------------------------------------------------- pestañas ---

def test_panel_abre_en_la_pestana_que_toca(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = _panel(app["c"], sid, cid)
    assert 'data-paso="armar"' in html and '<div data-pestana="ideas" role="tabpanel" hidden>' in html
    for n in range(5):
        datos.agregar_referencia("acme", cid, "imagen", f"https://r2/r{n}.jpg", descripcion="luz")
    html = _panel(app["c"], sid, cid)
    assert 'data-paso="ideas"' in html and "Armar <span>✓</span>" in html and "Ideas <span>0/3</span>" in html
    assert 'data-paso="piezas"' in _panel(app["c"], sid, cid, "piezas")
    assert 'data-paso="ideas"' in _panel(app["c"], sid, cid, "cualquiera")


def test_tablero_pasa_la_pestana_pedida(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}&paso=piezas").data.decode()
    assert f'data-panel-inicial="{cid}"' in html and 'data-paso-inicial="piezas"' in html
    assert "irAPaso" in html and "tablero:paso" in html and "tablero:cerrado" in html
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}&paso=raro").data.decode()
    assert 'data-paso-inicial=""' in html


def test_armar_muestra_la_sofisticacion_y_describe_referencias(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/sin.jpg")      # borrador: sin descripción
    html = _panel(app["c"], sid, cid, "armar")
    assert "Promesas parecidas que ya vio el cliente de Espejo LED: Claude lo decide" in html
    assert f'data-describir="{rid}"' in html and f"/cliente/acme/sprints/referencias/{rid}" in html
    assert f'data-abrir-describir="{rid}"' in html and "Más opciones de referencias" in html
    assert "descríbelos aquí" not in html and "Qué tanto sabe" not in html
    r = app["c"].post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "luz lateral", "intencion": ["iluminacion"]})
    assert r.get_json()["ok"] and r.get_json()["estado"] == "lista"
    assert "<script" not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py`
Expected: FAIL — no `data-paso` in the panel.

- [ ] **Step 3: Routes**

In `sprints/rutas.py`:

1. `campana_panel`: before `return render_template(...)` add

```python
    fila_producto = tiendas.por_activo(cliente).get(c["catalogo_id"]) or {}
    sof = (fila_producto.get("extra") or {}).get("sofisticacion")
```

and add these keyword arguments to its `render_template("_sprint_panel.html", ...)` call:

```python
        paso=tablero.resolver_paso(request.args.get("paso"), c), pestanas=tablero.pestanas(c),
        sof_producto=sof if sof in doctrina.SOFISTICACIONES else None, intenciones=datos.INTENCIONES_NOMBRE,
```

(`tiendas` is already imported in this module — `campana_ideas` uses `tiendas.por_activo`; if not, import it.)

2. `ver`: add to its `render_template(...)` call

```python
                           paso_inicial=request.args.get("paso") if request.args.get("paso") in tablero.PASOS else "",
```

- [ ] **Step 4: Templates**

Create `templates/_sprint_panel_armar.html` by MOVING (cut, not copy) from the current `templates/_sprint_panel.html` everything from the first `<section class="panel-seccion">` («Audiencia y producto») through the closing `</section>` of the «Referentes · …» section, and put at its top:

```html
{% from "_sprint_macros.html" import sugerido %}
{# Pestaña «Armar» del panel de una campaña (entrega 1 del tablero): audiencia,
   enfoque, formato, mercado, piezas y referentes. Incluida por _sprint_panel.html
   con todo su contexto; sin <script>. #}
{% set ef = c.efectivos %}
```

Then, inside that moved content:

a) In the «Enfoque» section, right after the `{% endif %}` that closes the `sugerencias_dolor` block, add:

```html
    <p class="panel-sofisticacion vacio">Promesas parecidas que ya vio el cliente de {{ c.producto.nombre if c.producto else c.catalogo_id }}:
      {% if sof_producto %}{{ sof_producto }} · {{ SOFISTICACIONES_CLIENTE[sof_producto] }}{% else %}Claude lo decide{% endif %} (se cambia en Catálogo).</p>
```

b) In the chosen-referentes grid, replace `{% if r.estado != 'lista' %}<figcaption>falta describir</figcaption>{% endif %}` with:

```html
        {% if r.estado != 'lista' %}<figcaption><button type="button" class="enlace-describir" data-abrir-describir="{{ r.id }}">Falta describir ✎</button></figcaption>{% endif %}
```

c) Replace the whole `{% if c.referencias_lista | rejectattr('estado', 'equalto', 'lista') | list %} <p class="vacio">Los que dicen «falta describir» … descríbelos aquí</a>.</p> {% endif %}` block with:

```html
    {% for r in c.referencias_lista if r.estado != 'lista' %}
    <div class="panel-describir" data-describir="{{ r.id }}" data-url="{{ url_for('sprints.referencia_editar', cliente=cliente, rid=r.id) }}" hidden>
      <div class="panel-describir-cab"><img src="{{ r.frame_url or r.url }}" alt="" loading="lazy">
        <p class="panel-sub">Qué tomar de este referente (cuenta cuando tenga descripción)</p></div>
      <div class="panel-opciones">
        {% for k, nombre in intenciones.items() %}<label><input type="checkbox" value="{{ k }}" data-intencion {% if k in (r.intencion or []) %}checked{% endif %}> {{ nombre }}</label>{% endfor %}
      </div>
      <label>Descripción
        <textarea rows="2" data-descripcion maxlength="500" placeholder="Qué se ve y qué quieres copiar">{{ r.descripcion or '' }}</textarea></label>
      <small class="campo-error" hidden></small>
    </div>
    {% endfor %}
    <p class="vacio"><a href="{{ url_for('sprints.campana_ver', cliente=cliente, sid=sprint.id, cid=c.id) }}">Más opciones de referencias →</a> (reutilizar de otra campaña, links en descarga)</p>
```

Create `templates/_sprint_panel_ideas.html` (placeholder until Task 3):

```html
{# Pestaña «Ideas» del panel (la completa la tarea 3 de la entrega 2). #}
<section class="panel-seccion">
  <p class="vacio">Las ideas de esta campaña: <a href="{{ url_for('sprints.campana_ideas', cliente=cliente, sid=sprint.id, cid=c.id) }}">abrir la página de ideas →</a></p>
</section>
```

Create `templates/_sprint_panel_piezas.html` (placeholder until Task 4):

```html
{# Pestaña «Piezas» del panel (la completa la tarea 4 de la entrega 2). #}
<section class="panel-seccion">
  <p class="vacio">Las piezas se revisan en <a href="{{ url_for('sprints.revision', cliente=cliente, sid=sprint.id) }}">la revisión del sprint →</a></p>
</section>
```

Replace what remains of `templates/_sprint_panel.html` with the shell:

```html
{# Panel de una campaña (specs 2026-09-26 §Panel y 2026-09-27 entrega 2): fragmento
   por fetch (sprints.campana_panel) con tres pestañas — Armar · Ideas · Piezas —
   que se muestran u ocultan en el navegador (`data-pestana`); `paso` es la que
   abre. Sus <script> no correrían: todo el JS vive en sprint_detalle.html. #}
<div class="panel-campana" data-cid="{{ c.id }}" data-paso="{{ paso }}"
     data-url-campo="{{ url_for('sprints.campana_campo', cliente=cliente, sid=sprint.id, cid=c.id) }}"
     data-url-sugeridos="{{ url_for('sprints.campana_sugeridos', cliente=cliente, sid=sprint.id, cid=c.id) }}">
  <header class="panel-campana-cab">
    <div>
      <h2>Campaña {{ c.orden + 1 }} · {{ (c.funnel or 'tof') | upper }}</h2>
      <small class="vacio">{{ c.persona_nombre }} · {{ c.producto.nombre if c.producto else c.catalogo_id }} · Todo se guarda solo</small>
    </div>
    <button type="button" class="btn-xs" data-panel-cerrar aria-label="Cerrar">✕</button>
  </header>
  <nav class="panel-pestanas" role="tablist" aria-label="Pasos de la campaña">
    {% for clave, nombre in (("armar", "Armar"), ("ideas", "Ideas"), ("piezas", "Piezas")) %}
    <button type="button" role="tab" class="panel-pestana" data-ir-paso="{{ clave }}"
            aria-selected="{{ 'true' if paso == clave else 'false' }}">{{ nombre }} <span>{{ pestanas[clave] }}</span></button>
    {% endfor %}
  </nav>
  <p class="panel-campana-aviso" data-aviso {% if not aviso %}hidden{% endif %}>{{ aviso or '' }}</p>
  <div data-pestana="armar" role="tabpanel" {% if paso != 'armar' %}hidden{% endif %}>{% include "_sprint_panel_armar.html" %}</div>
  <div data-pestana="ideas" role="tabpanel" {% if paso != 'ideas' %}hidden{% endif %}>{% include "_sprint_panel_ideas.html" %}</div>
  <div data-pestana="piezas" role="tabpanel" {% if paso != 'piezas' %}hidden{% endif %}>{% include "_sprint_panel_piezas.html" %}</div>
  <footer class="panel-campana-pie">
    <form method="post" action="{{ url_for('sprints.campana_eliminar', cliente=cliente, sid=sprint.id, cid=c.id) }}"
          onsubmit="return confirm('¿Eliminar esta campaña y sus referentes?');">
      <button type="submit" class="btn-xs btn-rechazar">Eliminar campaña</button>
    </form>
  </footer>
</div>
```

(The old footer link «Ideas de esta campaña →» goes away: the Ideas tab replaces it.)

In `templates/sprint_detalle.html`, on the `<aside class="tablero-panel" id="tablero-panel" …>` add the attribute `data-paso-inicial="{{ paso_inicial }}"`.

- [ ] **Step 5: Board JS (first `<script>` of `sprint_detalle.html`)**

1. Replace `function marcarUrl(cid) { … }` with:

```js
    var pasoActual = null;
    function marcarUrl(cid, paso) {
      var u = new URL(location.href);
      if (cid) u.searchParams.set('panel', cid); else u.searchParams.delete('panel');
      if (cid && paso) u.searchParams.set('paso', paso); else u.searchParams.delete('paso');
      history.replaceState(null, '', u);
    }
    // Pestañas del panel (entrega 2): todas vienen en el fragmento; aquí solo se
    // muestra una, se recuerda en la URL y se avisa con `tablero:paso` (la
    // pestaña Piezas arranca o para su actualización automática con eso).
    function irAPaso(paso) {
      var r = cuerpo.querySelector('.panel-campana[data-cid]');
      if (!r) return;
      cuerpo.querySelectorAll('[data-pestana]').forEach(function (s) { s.hidden = s.dataset.pestana !== paso; });
      cuerpo.querySelectorAll('[data-ir-paso]').forEach(function (b) {
        if (b.getAttribute('role') === 'tab') b.setAttribute('aria-selected', b.dataset.irPaso === paso ? 'true' : 'false');
      });
      panel.classList.toggle('panel-ancho', paso === 'piezas');
      pasoActual = paso;
      marcarUrl(r.dataset.cid, paso);
      document.dispatchEvent(new CustomEvent('tablero:paso', {detail: {paso: paso}}));
    }
```

2. In `cerrar()`, after `panelActualCid = null;` add:

```js
      pasoActual = null;
      panel.classList.remove('panel-ancho');
      document.dispatchEvent(new CustomEvent('tablero:cerrado'));
```

3. Replace `function abrir(cid) { … }` with:

```js
    function abrir(cid, paso) {
      var mismo = panelActualCid === cid;
      if (!paso && mismo) paso = pasoActual;
      mostrar(); marcarUrl(cid, paso); marcarActiva(cid);
      var scroll = mismo ? panel.scrollTop : 0;
      if (!mismo) cuerpo.innerHTML = '<p class="vacio">Cargando la campaña…</p>';
      panelActualCid = cid;
      var miPeticion = ++peticionPanel;
      return fetch(base + '/campanas/' + cid + '/panel' + (paso ? '?paso=' + encodeURIComponent(paso) : ''), {headers: H})
        .then(function (r) {
          if (r.status === 404) { if (miPeticion === peticionPanel) noExiste(); return null; }
          if (!r.ok) throw new Error();
          return r.text();
        })
        .then(function (html) {
          if (html === null || miPeticion !== peticionPanel) return;
          cuerpo.innerHTML = html;
          var r = cuerpo.querySelector('.panel-campana[data-cid]');
          if (r) irAPaso(r.dataset.paso);
          if (mismo) panel.scrollTop = scroll;
          if (typeof window.tableroPanelListo === 'function') window.tableroPanelListo();
        })
        .catch(function () {
          if (miPeticion !== peticionPanel) return;
          cuerpo.innerHTML = '<p class="campo-error">No se pudo abrir la campaña. Revisa tu conexión e intenta de nuevo.</p>';
        });
    }
```

4. In `abrirNueva()`, after `panelActualCid = null;` add `pasoActual = null; panel.classList.remove('panel-ancho');` (its `marcarUrl(null)` already clears both params).

5. Extend `window.tablero`: add `irAPaso: irAPaso, paso: function () { return pasoActual; }`.

6. In the document `click` listener, as its first line add:

```js
      var pestana = ev.target.closest('[data-ir-paso]');
      if (pestana && panel.contains(pestana)) { irAPaso(pestana.dataset.irPaso); return; }
```

7. Replace the initial open `if (panel.dataset.panelInicial) abrir(panel.dataset.panelInicial);` with:

```js
    if (panel.dataset.panelInicial) abrir(panel.dataset.panelInicial, panel.dataset.pasoInicial || null);
```

- [ ] **Step 6: Describe-reference JS (second `<script>`, the panel one)**

1. Inside the existing `panel.addEventListener('change', …)`, right after its first line `if (!raiz() || t.closest('form')) return;`, add:

```js
      var cajaDescribir = t.closest('[data-describir]');
      if (cajaDescribir) { guardarDescripcion(cajaDescribir); return; }
```

2. After `function recargarTodo() { … }` add:

```js
    // Describir un referente subido («Falta describir ✎») sin salir del panel
    // (entrega 2): intención + descripción van a `sprints.referencia_editar`;
    // cuando queda «lista», la tarjeta y el panel se actualizan.
    function guardarDescripcion(caja) {
      var err = caja.querySelector('.campo-error');
      err.hidden = true;
      var cuerpoJson = {descripcion: caja.querySelector('[data-descripcion]').value,
                        intencion: Array.prototype.map.call(caja.querySelectorAll('[data-intencion]:checked'),
                                                            function (x) { return x.value; })};
      fetch(caja.dataset.url, {method: 'POST', headers: HJ, body: JSON.stringify(cuerpoJson)})
        .then(T.json)
        .then(function (j) {
          caja.querySelectorAll('[data-sucio]').forEach(function (el) { delete el.dataset.sucio; });
          if (j.estado === 'lista') { var cid = raiz().dataset.cid; T.refrescarTarjeta(cid); return T.abrir(cid, 'armar'); }
        })
        .catch(function (e) { err.textContent = T.mensaje(e); err.hidden = false; });
    }
```

3. In the panel `click` listener, add a branch before the others:

```js
      var abreDescribir = ev.target.closest('[data-abrir-describir]');
      if (abreDescribir) {
        var cajaD = cuerpo.querySelector('[data-describir="' + abreDescribir.dataset.abrirDescribir + '"]');
        if (cajaD) {
          cajaD.hidden = !cajaD.hidden;
          if (!cajaD.hidden) cajaD.querySelector('[data-descripcion]').focus();
        }
        return;
      }
```

(The listener starts with `if (!raiz()) return; var b;` — put the new branch right after that line.)

- [ ] **Step 7: CSS**

Append to the «Tablero de Sprints (2026-09-26)» block at the end of `static/style.css`:

```css
/* Entrega 2 (2026-09-27): pestañas del panel y describir referentes */
.panel-pestanas { display: flex; gap: .4rem; flex-wrap: wrap; margin: .8rem 0 .2rem; }
.panel-pestana { border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 999px;
  padding: .25rem .8rem; font: inherit; font-size: .9rem; cursor: pointer; min-height: 0; }
.panel-pestana span { color: var(--muted); margin-left: .2rem; }
.panel-pestana[aria-selected="true"] { background: var(--accent-grad); color: #fff; border-color: transparent; }
.panel-pestana[aria-selected="true"] span { color: #fff; }
.tablero-panel.panel-ancho { width: min(960px, 100%); }
.panel-describir { display: grid; gap: .5rem; padding: .6rem; border: 1px dashed var(--border); border-radius: var(--radius-sm); }
.panel-describir[hidden] { display: none; }
.panel-describir-cab { display: flex; gap: .5rem; align-items: center; }
.panel-describir-cab img { width: 48px; height: 48px; object-fit: cover; border-radius: 6px; }
.enlace-describir { background: none; border: 0; padding: 0; min-height: 0; font: inherit; font-size: .7rem;
  color: var(--accent-texto); cursor: pointer; }
.panel-sofisticacion { margin: 0; font-size: .85rem; }
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_modo_oscuro.py tests/test_base_visual.py tests/test_movil.py`
Expected: PASS. Then the fast suite once.

- [ ] **Step 9: Commit**

```bash
git add sprints/rutas.py templates/_sprint_panel.html templates/_sprint_panel_armar.html templates/_sprint_panel_ideas.html templates/_sprint_panel_piezas.html templates/sprint_detalle.html static/style.css tests/test_sprints_tablero_entrega2.py
git commit -m "Sprints tablero 2: el panel tiene pestañas Armar · Ideas · Piezas y los referentes se describen ahí mismo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pestaña «Ideas» con la caja «Generar»

**Files:**
- Modify: `sprints/rutas.py` (`_volver_panel`, `_contexto_ideas`, `campana_panel`, `campana_ideas`, `ideas_proponer`, `ideas_aprobar_todas`, `_volver_ideas`, `idea_otra`, `idea_reescribir`, `lote`)
- Rewrite: `templates/_sprint_panel_ideas.html`
- Delete: `templates/campana_ideas.html`
- Modify: `templates/sprint_detalle.html` (load `angulo.js`; ideas/generar JS), `templates/_sprint_lote_modal.html` (comment), `static/style.css`
- Test: `tests/test_sprints_tablero_entrega2.py`, `tests/test_rutas_sprints.py`, `tests/test_sprints_tablero_rutas.py`

**Interfaces:**
- Consumes: Task 1 (`gastos.estimar("proponer_ideas", n=)`), Task 2 (tab shell, `window.tablero.abrir(cid, paso)`, `irAPaso`).
- Produces:
  - `rutas._volver_panel(cliente, sid, cid, paso)` → redirect to `sprints.ver` with `panel=cid&paso=paso`.
  - `GET …/campanas/<cid>/ideas` → 302 to the board with `?panel=<cid>&paso=ideas`.
  - JSON (with `X-Requested-With: fetch`): `ideas_proponer` → `{ok, job_id, error}` (409 when already running); `ideas_aprobar_todas` → `{ok: true, aprobadas}`; `idea_otra`/`idea_reescribir` → `{ok, job_id, error}` (400 with a piece / without promesa, 409 when running); `lote` → `{ok: true, encoladas, omitidas, usd, mensaje}` or `{ok: false, error}` (409 nothing to launch, 400 invalid).
  - Ideas tab DOM: `.panel-idea.sprint-idea[data-url][data-cp]` cards with `input|textarea[name=titulo|escena|sonido|gancho]`, `[data-idea-accion][data-url]` buttons, `[data-proponer][data-url][data-mas][data-tipo]`, `.panel-generar[data-generar][data-campana][data-url-estimar][data-url-lote]` with `[data-lote-modelo="video|imagen"]`, `[data-lote-texto]`, `[data-generar-lote]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_tablero_entrega2.py`:

```python
# ---------------------------------------------------------------- ideas ---

def test_la_pagina_de_ideas_redirige_al_panel(con_ideas):
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    r = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999/ideas").status_code == 404


def test_pestana_ideas_muestra_conteo_ideas_y_generar(con_ideas):
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    html = _panel(c, sid, cid, "ideas")
    assert "1 de 3 aprobadas · videos 1/2 · imágenes 0/1" in html
    assert "Proponer las que faltan (1 videos, 0 imágenes) (" in html and "aprox." in html
    assert "Aprobar todas las propuestas (1)" in html
    assert f'data-url="/cliente/acme/sprints/ideas/{ii}"' in html and 'class="sprint-idea panel-idea' in html
    assert "Otra idea (" in html and "Amanecer" in html and "Marco" in html
    assert "data-generar-lote" in html and "1 aprobada(s) sin generar (1 videos, 0 imágenes)" in html
    assert 'data-lote-modelo="video"' in html and "<script" not in html


def test_el_tablero_carga_el_editor_del_angulo(con_ideas):
    html = con_ideas["c"].get(f"/cliente/acme/sprints/{con_ideas['sid']}").data.decode()
    assert "/static/angulo.js" in html and "iniciarEditoresAngulo(cuerpo)" in html
    assert '[data-angulo-campo="gancho"]' in html


def test_proponer_ideas_por_fetch(con_ideas, monkeypatch):
    from sprints import rutas
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer"
    j = c.post(url, data={"mas": "3", "tipo": "imagen"}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] and j["job_id"] == f"acme__campana{cid}__ideas"
    assert con_ideas["encolados"][-1]["payload"]["n_imagenes"] == 3
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_ideas", lambda *a, **k: False)
    r = c.post(url, data={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 409 and "en curso" in r.get_json()["error"]
    r = c.post(url, data={})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")


def test_acciones_de_idea_por_fetch(con_ideas):
    from sprints import datos
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    H = {"X-Requested-With": "fetch"}
    assert c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/aprobar_todas", headers=H).get_json() == \
        {"ok": True, "aprobadas": 1}
    j = c.post(f"/cliente/acme/sprints/ideas/{ii}/otra", headers=H).get_json()
    assert j["ok"] and con_ideas["encolados"][-1]["payload"]["reemplaza"] == ii
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/reescribir", headers=H)
    assert r.status_code == 400 and "promesa" in r.get_json()["error"]
    assert c.post(f"/cliente/acme/sprints/ideas/{ii}/descartar", headers=H).get_json()["ok"]
    assert datos.idea("acme", ii)["estado_idea"] == "descartada"
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/aprobar")
    assert r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=ideas")


def test_generar_por_fetch(con_ideas, monkeypatch):
    from sprints import rutas
    c, sid, cid = con_ideas["c"], con_ideas["sid"], con_ideas["cid"]
    H = {"X-Requested-With": "fetch"}
    monkeypatch.setattr(rutas.produccion, "lanzar_lote",
                        lambda cliente, sid_, campana_id=None, modelo_video=None, modelo_imagen=None:
                        {"encoladas": 1, "omitidas": 0, "cf_ids": ["x"], "usd": 0.8})
    j = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid}, headers=H).get_json()
    assert j["ok"] and j["encoladas"] == 1 and "Lote encolado" in j["mensaje"]
    monkeypatch.setattr(rutas.produccion, "lanzar_lote",
                        lambda cliente, sid_, campana_id=None, modelo_video=None, modelo_imagen=None:
                        {"encoladas": 0, "omitidas": 0, "cf_ids": [], "usd": 0.0})
    r = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid}, headers=H)
    assert r.status_code == 409 and r.get_json()["error"] == "No había ideas aprobadas sin generar."
```

In `tests/test_rutas_sprints.py`:
- Add near `con_ideas`:

```python
def _ideas_html(c, sid, cid):
    """Desde la entrega 2 del tablero las ideas viven en la pestaña Ideas del panel."""
    return c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel?paso=ideas").data.decode()
```

- Replace every `c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas").data.decode()` with `_ideas_html(c, sid, cid)`.
- `test_pagina_de_ideas_y_acciones`: replace its first two lines (`r = c.get(…/ideas)` and the assertion) with

```python
    html = _ideas_html(c, sid, cid)
    assert "Amanecer" in html and "Marco" in html and "videos 1/2" in html
```

  (keep the `…/campanas/999/ideas` → 404 assertion).
- The reserva test («con una reserva colgada…»): replace `"Generar lote de esta campaña" not in c.get(…/ideas)…` with `"data-generar-lote" not in _ideas_html(c, sid, cid)` and `"Generar lote de esta campaña (1)" in html` with `"data-generar-lote" in html`.
- `test_consciencia_de_la_persona_se_elige_en_la_pagina_de_ideas`: remove the two HTML assertions about «Qué tanto sabe Premium» / `value="inconsciente" selected` (the selector is not in the panel; the JSON route `persona_conciencia` is still tested by the rest of the test); change `"Promesas parecidas que ya vio el cliente de espejo_led:"` to `"Promesas parecidas que ya vio el cliente de Espejo LED:"`.
- Delete `test_la_pagina_de_ideas_dice_cuando_manda_la_consciencia_de_la_campana` (that notice lived next to the persona selector, which the panel does not show; the campaign's consciencia is visible in Armar).
- `test_editar_el_angulo_de_una_idea`: the assertion `"/static/angulo.js" in html` moves to the board page — replace it with `assert "/static/angulo.js" in c.get(f"/cliente/acme/sprints/{sid}").data.decode()`; keep the rest.
- `test_gancho_sync_wiring`: take the `[data-angulo-campo="gancho"]` assertion from the board page (`c.get(f"/cliente/acme/sprints/{sid}").data.decode()`) instead of the ideas page.

In `tests/test_sprints_tablero_rutas.py::test_panel_muestra_las_siete_secciones` remove `f"/sprints/{sid}/campanas/{cid}/ideas"` from the list of expected fragments (the Ideas tab replaces the footer link).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py`
Expected: FAIL — ideas page still renders; no JSON on proponer; placeholder ideas tab.

- [ ] **Step 3: Routes**

In `sprints/rutas.py`:

1. After `_volver_campana` add:

```python
def _volver_panel(cliente, sid, cid, paso):
    """Vuelve al tablero con el panel de esa campaña abierto en esa pestaña."""
    return redirect(url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid, paso=paso))


def _contexto_ideas(cliente, c):
    """Lo que muestra la pestaña Ideas del panel (entrega 2 del tablero)."""
    vivas = [i for i in c["ideas"] if i["estado_idea"] != "descartada"]
    faltan_v, faltan_i = ideas.faltantes(c)
    por_generar = [i for i in vivas if i["estado_idea"] == "aprobada" and i["sin_sesion"]]
    conteo = {"planeadas": int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0),
              "aprobadas": sum(1 for i in vivas if i["estado_idea"] == "aprobada"),
              "videos_aprobados": sum(1 for i in vivas if i["tipo"] == "video" and i["estado_idea"] == "aprobada"),
              "imagenes_aprobadas": sum(1 for i in vivas if i["tipo"] == "imagen" and i["estado_idea"] == "aprobada"),
              "propuestas": sum(1 for i in vivas if i["estado_idea"] == "propuesta"),
              "faltan_videos": faltan_v, "faltan_imagenes": faltan_i,
              "por_generar": len(por_generar),
              "por_generar_videos": sum(1 for i in por_generar if i["tipo"] == "video"),
              "por_generar_imagenes": sum(1 for i in por_generar if i["tipo"] == "imagen")}
    job = tareas_sprints.job_id_ideas(cliente, c["id"])
    return {
        "ideas_vivas": vivas,
        "ideas_descartadas": [i for i in c["ideas"] if i["estado_idea"] == "descartada"],
        "conteo_ideas": conteo,
        "precios_ideas": {"faltan": gastos.estimar("proponer_ideas", n=faltan_v + faltan_i)["texto"],
                          "mas": gastos.estimar("proponer_ideas", n=3)["texto"],
                          "otra": gastos.estimar("proponer_ideas", n=1)["texto"],
                          "reescribir": gastos.estimar("reescribir_idea")["texto"]},
        "trabajo_ideas": {"job_id": job} if trabajos.en_curso(job) else None,
        "reescribiendo": {i["id"]: tareas_sprints.job_id_reescribir(cliente, i["id"]) for i in vivas
                          if trabajos.en_curso(tareas_sprints.job_id_reescribir(cliente, i["id"]))},
        "enfoques": flowplus_prompt_enfoques(),
        "referencias_por_id": {r["id"]: r for r in (c.get("referencias_lista") or datos.referencias(cliente, c["id"]))},
        **_contexto_lote(cliente),
    }
```

2. `campana_panel`: add `**_contexto_ideas(cliente, c),` to its `render_template(...)` keyword arguments.

3. Replace `campana_ideas` with:

```python
@bp.get("/<int:sid>/campanas/<int:cid>/ideas")
def campana_ideas(cliente, sid, cid):
    """Desde la entrega 2 del tablero las ideas viven en la pestaña Ideas del
    panel de la campaña: la página vieja redirige ahí (sus enlaces siguen vivos)."""
    _campana_o_404(cliente, sid, cid)
    return _volver_panel(cliente, sid, cid, "ideas")
```

and `git rm templates/campana_ideas.html`.

4. Replace `ideas_proponer` with:

```python
@bp.post("/<int:sid>/campanas/<int:cid>/ideas/proponer")
def ideas_proponer(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        if request.form.get("mas"):
            n_v, n_i = _entero("mas", 3), 0
            if request.form.get("tipo") == "imagen":
                n_v, n_i = 0, _entero("mas", 3)
        else:
            n_v = _entero("n_videos") if request.form.get("n_videos") else None
            n_i = _entero("n_imagenes") if request.form.get("n_imagenes") else None
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver_panel(cliente, sid, cid, "ideas")
    ok = tareas_sprints.encolar_ideas(cliente, cid, n_videos=n_v, n_imagenes=n_i)
    error = None if ok else "Ya hay una propuesta de ideas en curso para esta campaña."
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_ideas(cliente, cid), "error": error}), \
            (200 if ok else 409)
    flash("Claude está proponiendo ideas; aparecerán aquí en unos segundos." if ok else error, "ok" if ok else "error")
    return _volver_panel(cliente, sid, cid, "ideas")
```

5. `ideas_aprobar_todas`: after `estado.recalcular(cliente, sid)` add `if _quiere_json(): return jsonify({"ok": True, "aprobadas": n})` and make its final redirect `return _volver_panel(cliente, sid, cid, "ideas")`.

6. `_volver_ideas(i)` becomes `return _volver_panel(i["cliente"], i["sprint_id"], i["campana_id"], "ideas")`.

7. Replace `idea_reescribir` and `idea_otra` with:

```python
@bp.post("/ideas/<int:cp_id>/reescribir")
def idea_reescribir(cliente, cp_id):
    """«Reescribir la idea con este ángulo» (doctrina, bloque 2, §3.5): encola
    la tarea pagada; el precio ya está en el botón."""
    i = _idea_o_404(cliente, cp_id)
    angulo = (i.get("extra") or {}).get("angulo")
    error = (MENSAJE_IDEA_CON_PIEZA if not i["sin_sesion"] else
             None if isinstance(angulo, dict) and angulo.get("promesa") else
             "Esta idea todavía no tiene un ángulo con promesa.")
    if error:
        if _quiere_json():
            return jsonify({"ok": False, "error": error}), 400
        flash(error, "error")
        return _volver_ideas(i)
    ok = tareas_sprints.encolar_reescribir(cliente, cp_id)
    error = None if ok else "Ya se está reescribiendo esta idea."
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_reescribir(cliente, cp_id), "error": error}), \
            (200 if ok else 409)
    flash("Reescribiendo la idea desde su ángulo…" if ok else error, "ok" if ok else "error")
    return _volver_ideas(i)
```

```python
@bp.post("/ideas/<int:cp_id>/otra")
def idea_otra(cliente, cp_id):
    """Pide otra idea del mismo tipo en lugar de esta (una sola). Descartar
    la vieja lo hace la tarea (`ideas.proponer(reemplaza=)`) al reemplazarla:
    si no se puede encolar (ya hay una propuesta en curso para la campaña),
    la idea no se toca."""
    i = _idea_o_404(cliente, cp_id)
    if not i["sin_sesion"]:
        if _quiere_json():
            return jsonify({"ok": False, "error": MENSAJE_IDEA_CON_PIEZA}), 400
        flash(MENSAJE_IDEA_CON_PIEZA, "error")
        return _volver_ideas(i)
    ok = tareas_sprints.encolar_ideas(cliente, i["campana_id"], reemplaza=cp_id)
    error = None if ok else "Ya hay una propuesta en curso; espera a que termine."
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_ideas(cliente, i["campana_id"]),
                        "error": error}), (200 if ok else 409)
    flash("Pidiendo otra idea…" if ok else error, "ok" if ok else "error")
    return _volver_ideas(i)
```

8. Replace `lote` with:

```python
@bp.post("/<int:sid>/lote")
def lote(cliente, sid):
    """Puerta de gasto: el modal del tablero o la caja «Generar» del panel ya
    mostraron el costo; aquí se encola."""
    _sprint_o_404(cliente, sid)
    cid = request.form.get("campana_id", type=int)
    try:
        r = produccion.lanzar_lote(cliente, sid, campana_id=cid, modelo_video=request.form.get("modelo_video"),
                                   modelo_imagen=request.form.get("modelo_imagen"))
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, sid)
    if not r["encoladas"]:
        error = "No había ideas aprobadas sin generar." if not r["omitidas"] else "Esas piezas ya se estaban generando."
        if _quiere_json():
            return jsonify({"ok": False, "error": error, "encoladas": 0, "omitidas": r["omitidas"]}), 409
        flash(error, "warn")
        return _volver(cliente, sid)
    texto = (f"Lote encolado: {r['encoladas']} pieza(s), USD {r['usd']:.2f} estimado. "
             "Te avisamos por correo al terminar si está configurado.")
    if _quiere_json():
        return jsonify({"ok": True, "encoladas": r["encoladas"], "omitidas": r["omitidas"], "usd": r["usd"],
                        "mensaje": texto})
    flash(texto, "ok")
    return _volver(cliente, sid)
```

- [ ] **Step 4: Template `_sprint_panel_ideas.html`**

Replace the placeholder with:

```html
{% from "_angulo_editor.html" import editor_angulo %}
{# Pestaña «Ideas» del panel (spec 2026-09-27 §Pestaña «Ideas»). Contexto de
   rutas._contexto_ideas: ideas_vivas, ideas_descartadas, conteo_ideas,
   precios_ideas, trabajo_ideas, reescribiendo, enfoques, referencias_por_id y
   los modelos del lote. Sin <script>: el JS vive en sprint_detalle.html. #}
{% macro tarjeta_idea(i) %}
{% set con_pieza = not i.sin_sesion %}
<details class="sprint-idea panel-idea panel-idea-{{ i.estado_idea }}" data-cp="{{ i.id }}"
         data-url="{{ url_for('sprints.idea_editar', cliente=cliente, cp_id=i.id) }}">
  <summary>
    <span class="chip-tipo">{{ i.tipo | upper }}</span>
    <strong>{{ i.titulo }}</strong>
    {% if i.duracion_s %}<small class="vacio">{{ i.duracion_s | int }} s</small>{% endif %}
    {% if i.enfoque %}<small class="vacio">{{ enfoques.get(i.enfoque, i.enfoque) }}</small>{% endif %}
    <span class="panel-idea-estado">{{ 'generada' if con_pieza else i.estado_idea }}</span>
  </summary>
  <div class="panel-idea-cuerpo">
    <label>Título <input name="titulo" value="{{ i.titulo }}" maxlength="200" {% if con_pieza %}readonly{% endif %}></label>
    <label>Escena <textarea name="escena" rows="3" {% if con_pieza %}readonly{% endif %}>{{ i.escena }}</textarea></label>
    {% if i.tipo == "video" %}<label>Sonido <input name="sonido" value="{{ i.sonido or '' }}" {% if con_pieza %}readonly{% endif %}></label>{% endif %}
    <label>Gancho <input name="gancho" value="{{ i.gancho or '' }}" maxlength="200" {% if con_pieza %}readonly{% endif %}></label>
    <small class="panel-idea-guardado vacio" hidden>Guardado</small>
    <small class="campo-error" data-error-idea hidden></small>
    {{ editor_angulo((i.extra or {}).get('angulo'), url_for('sprints.idea_angulo', cliente=cliente, cp_id=i.id), cliente,
                     solo_lectura=con_pieza) }}
    {% if i.referencias_ids %}
    <div class="panel-idea-refs">{% for rid in i.referencias_ids %}{% set r = referencias_por_id.get(rid) %}{% if r %}<img src="{{ r.frame_url or r.url }}" alt="" title="{{ r.titulo or '' }}" loading="lazy">{% endif %}{% endfor %}</div>
    {% endif %}
    <div class="panel-acciones">
      {% if con_pieza %}
        <button type="button" class="btn-sm" data-ir-paso="piezas">Ver su pieza →</button>
      {% else %}
        {% if i.estado_idea != "aprobada" %}<button type="button" class="btn-generar btn-xs" data-idea-accion data-url="{{ url_for('sprints.idea_aprobar', cliente=cliente, cp_id=i.id) }}">Aprobar</button>{% endif %}
        {% if ((i.extra or {}).get('angulo') or {}).get('promesa') %}
          {% if i.id in reescribiendo %}
          <div class="barra-progreso" id="trabajo-{{ reescribiendo[i.id] }}" data-poll-job="{{ reescribiendo[i.id] }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
          {% else %}
          <button type="button" class="btn-xs" data-idea-accion data-url="{{ url_for('sprints.idea_reescribir', cliente=cliente, cp_id=i.id) }}">Reescribir la idea con este ángulo ({{ precios_ideas.reescribir }})</button>
          {% endif %}
        {% endif %}
        <button type="button" class="btn-xs" data-idea-accion data-url="{{ url_for('sprints.idea_otra', cliente=cliente, cp_id=i.id) }}" {% if trabajo_ideas %}disabled{% endif %}>Otra idea ({{ precios_ideas.otra }})</button>
        <button type="button" class="btn-xs btn-rechazar" data-idea-accion data-url="{{ url_for('sprints.idea_descartar', cliente=cliente, cp_id=i.id) }}">Descartar</button>
      {% endif %}
    </div>
  </div>
</details>
{% endmacro %}
{% set ci = conteo_ideas %}
{% set faltan = ci.faltan_videos + ci.faltan_imagenes %}
{% set url_proponer = url_for('sprints.ideas_proponer', cliente=cliente, sid=sprint.id, cid=c.id) %}
<section class="panel-seccion">
  <p class="panel-ideas-conteo"><strong>{{ ci.aprobadas }} de {{ ci.planeadas }} aprobadas</strong> · videos {{ ci.videos_aprobados }}/{{ c.n_videos }} · imágenes {{ ci.imagenes_aprobadas }}/{{ c.n_imagenes }}</p>
  <div class="panel-acciones">
    <button type="button" class="btn-generar btn-sm" data-proponer data-url="{{ url_proponer }}" {% if trabajo_ideas or not faltan %}disabled{% endif %}>✨ Proponer las que faltan ({{ ci.faltan_videos }} videos, {{ ci.faltan_imagenes }} imágenes){% if faltan %} ({{ precios_ideas.faltan }}){% endif %}</button>
    <button type="button" class="btn-sm" data-proponer data-mas="3" data-url="{{ url_proponer }}" {% if trabajo_ideas %}disabled{% endif %}>+3 videos ({{ precios_ideas.mas }})</button>
    <button type="button" class="btn-sm" data-proponer data-mas="3" data-tipo="imagen" data-url="{{ url_proponer }}" {% if trabajo_ideas %}disabled{% endif %}>+3 imágenes ({{ precios_ideas.mas }})</button>
    {% if ci.propuestas %}<button type="button" class="btn-sm" data-idea-accion data-url="{{ url_for('sprints.ideas_aprobar_todas', cliente=cliente, sid=sprint.id, cid=c.id) }}">Aprobar todas las propuestas ({{ ci.propuestas }})</button>{% endif %}
  </div>
  {% if trabajo_ideas %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_ideas.job_id }}" data-poll-job="{{ trabajo_ideas.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <p class="vacio">Claude está proponiendo ideas; aparecen aquí al terminar.</p>
  {% endif %}
</section>

<section class="panel-seccion panel-ideas">
  {% for i in ideas_vivas %}{{ tarjeta_idea(i) }}{% else %}
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay ideas</p>
    <p class="estado-vacio-texto">Pulsa «Proponer las que faltan»: Claude las escribe con la persona, el producto, el enfoque y los referentes elegidos.</p>
  </div>
  {% endfor %}
  {% if ideas_descartadas %}
  <details class="panel-descartadas"><summary>{{ ideas_descartadas | length }} descartada(s)</summary>
    {% for i in ideas_descartadas %}<p class="vacio">{{ i.tipo }} · {{ i.titulo }}</p>{% endfor %}
  </details>
  {% endif %}
</section>

<section class="panel-seccion panel-generar" data-generar data-campana="{{ c.id }}"
         data-url-estimar="{{ url_for('sprints.lote_estimar', cliente=cliente, sid=sprint.id) }}"
         data-url-lote="{{ url_for('sprints.lote', cliente=cliente, sid=sprint.id) }}">
  <h3>Generar</h3>
  {% if ci.por_generar %}
  <p>{{ ci.por_generar }} aprobada(s) sin generar ({{ ci.por_generar_videos }} videos, {{ ci.por_generar_imagenes }} imágenes)</p>
  <div class="panel-fila">
    <label>Modelo de video
      <select data-lote-modelo="video">{% for k, m in modelos_video.items() %}<option value="{{ k }}" {% if k == modelo_video_defecto %}selected{% endif %}>{{ m.nombre }} (US$ {{ '%.3f' % m.usd_por_segundo_efectivo }}/s con sonido)</option>{% endfor %}</select></label>
    <label>Modelo de imagen
      <select data-lote-modelo="imagen">{% for k, m in modelos_imagen.items() %}<option value="{{ k }}" {% if k == modelo_imagen_defecto %}selected{% endif %}>{{ m.nombre }}</option>{% endfor %}</select></label>
  </div>
  <p class="vacio" data-lote-texto>Calculando el costo…</p>
  <button type="button" class="btn-generar" data-generar-lote disabled>Generar {{ ci.por_generar }} pieza(s)</button>
  <small class="vacio">Se crea una pieza de Crear por idea aprobada. Ninguna se reintenta sola si falla.</small>
  <small class="campo-error" hidden></small>
  {% else %}
  <p class="vacio">No hay ideas aprobadas sin generar. Aprueba ideas para poder generarlas.</p>
  {% endif %}
</section>
```

In `templates/_sprint_lote_modal.html` update the first comment line to: «Puerta de costo del lote de TODO el sprint (spec §2.2), incluida en sprint_detalle.html; la caja «Generar» de la pestaña Ideas del panel usa las mismas rutas para una campaña.»

In `templates/sprint_detalle.html`, right before the first board `<script>` add:

```html
<script src="{{ url_for('static', filename='angulo.js') }}"></script>
```

- [ ] **Step 5: Ideas JS (panel `<script>` of `sprint_detalle.html`)**

1. At the end of `window.tableroPanelListo = function () { … }` (inside it) add:

```js
      if (typeof window.iniciarEditoresAngulo === 'function') window.iniciarEditoresAngulo(cuerpo);
      estimarLoteCampana();
```

2. Add these functions after `guardarDescripcion`:

```js
    // ---- Pestaña Ideas (entrega 2) ----
    var esperaIdea = {};
    function guardarIdea(card) {
      var cuerpoJson = {};
      card.querySelectorAll('input[name], textarea[name]').forEach(function (el) { if (!el.readOnly) cuerpoJson[el.name] = el.value; });
      var err = card.querySelector('[data-error-idea]'), ok = card.querySelector('.panel-idea-guardado');
      err.hidden = true;
      fetch(card.dataset.url, {method: 'POST', headers: HJ, body: JSON.stringify(cuerpoJson)})
        .then(T.json)
        .then(function () {
          card.querySelectorAll('input[name], textarea[name]').forEach(function (el) { delete el.dataset.sucio; });
          // El gancho de la tarjeta y el del ángulo son el mismo (doctrina, bloque 2).
          var g = card.querySelector('input[name="gancho"]'), ga = card.querySelector('[data-angulo-campo="gancho"]');
          if (g && ga) ga.value = g.value;
          ok.hidden = false;
          setTimeout(function () { ok.hidden = true; }, 1500);
        })
        .catch(function (e) { err.textContent = T.mensaje(e); err.hidden = false; });
    }
    function estimarLoteCampana() {
      var caja = cuerpo.querySelector('[data-generar]');
      var btn = caja && caja.querySelector('[data-generar-lote]');
      if (!btn) return;
      var texto = caja.querySelector('[data-lote-texto]');
      var mv = caja.querySelector('[data-lote-modelo="video"]').value, mi = caja.querySelector('[data-lote-modelo="imagen"]').value;
      btn.disabled = true;
      texto.textContent = 'Calculando el costo…';
      fetch(caja.dataset.urlEstimar + '?campana_id=' + encodeURIComponent(caja.dataset.campana) +
            '&modelo_video=' + encodeURIComponent(mv) + '&modelo_imagen=' + encodeURIComponent(mi), {headers: H})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.error) { texto.textContent = j.error; return; }
          texto.textContent = j.texto;
          var n = j.videos + j.imagenes;
          btn.textContent = n ? 'Generar ' + n + ' pieza(s) — US$ ' + j.usd.toFixed(2) : 'Nada que generar';
          btn.disabled = !n;
        })
        .catch(function () { texto.textContent = 'No se pudo calcular el costo.'; });
    }
    panel.addEventListener('input', function (ev) {
      var el = ev.target;
      if (el.closest('.angulo-editor')) {
        // angulo.js guarda solo a los 800 ms; su marca de «sin guardar» se quita después.
        setTimeout(function () { delete el.dataset.sucio; }, 2500);
        return;
      }
      if (!el.name || el.readOnly) return;
      var card = el.closest('.panel-idea');
      if (!card) return;
      clearTimeout(esperaIdea[card.dataset.cp]);
      esperaIdea[card.dataset.cp] = setTimeout(function () { guardarIdea(card); }, 800);
    });
```

3. In the panel `change` listener, right after the `cajaDescribir` branch (Task 2) add:

```js
      if (t.matches('[data-lote-modelo]')) { estimarLoteCampana(); return; }
```

4. In the panel `click` listener, after the `abreDescribir` branch (Task 2) add:

```js
      var proponer = ev.target.closest('[data-proponer]');
      if (proponer) {
        proponer.disabled = true;
        var fdP = new FormData();
        if (proponer.dataset.mas) fdP.append('mas', proponer.dataset.mas);
        if (proponer.dataset.tipo) fdP.append('tipo', proponer.dataset.tipo);
        fetch(proponer.dataset.url, {method: 'POST', headers: H, body: fdP}).then(T.json)
          .then(function () { return T.abrir(raiz().dataset.cid, 'ideas'); })
          .catch(function (e) { proponer.disabled = false; avisar(T.mensaje(e)); });
        return;
      }
      var accionIdea = ev.target.closest('[data-idea-accion]');
      if (accionIdea) {
        accionIdea.disabled = true;
        fetch(accionIdea.dataset.url, {method: 'POST', headers: H}).then(T.json)
          .then(function () { var cid = raiz().dataset.cid; T.refrescarTarjeta(cid); return T.abrir(cid, 'ideas'); })
          .catch(function (e) { accionIdea.disabled = false; avisar(T.mensaje(e)); });
        return;
      }
      var generar = ev.target.closest('[data-generar-lote]');
      if (generar) {
        var cajaG = generar.closest('[data-generar]'), errG = cajaG.querySelector('.campo-error');
        generar.disabled = true;
        errG.hidden = true;
        var fdG = new FormData();
        fdG.append('campana_id', cajaG.dataset.campana);
        fdG.append('modelo_video', cajaG.querySelector('[data-lote-modelo="video"]').value);
        fdG.append('modelo_imagen', cajaG.querySelector('[data-lote-modelo="imagen"]').value);
        fetch(cajaG.dataset.urlLote, {method: 'POST', headers: H, body: fdG}).then(T.json)
          .then(function () { var cid = raiz().dataset.cid; T.refrescarTarjeta(cid); return T.abrir(cid, 'piezas'); })
          .catch(function (e) { generar.disabled = false; errG.textContent = T.mensaje(e); errG.hidden = false; });
        return;
      }
```

- [ ] **Step 6: CSS**

Append to the Tablero block of `static/style.css`:

```css
.panel-ideas-conteo { margin: 0; }
.panel-ideas { gap: .5rem; }
.panel-idea { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: .5rem .7rem; background: var(--panel); }
.panel-idea > summary { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; cursor: pointer; }
.panel-idea-aprobada { border-color: var(--ok); }
.panel-idea-estado { margin-left: auto; font-size: .8rem; color: var(--muted); }
.panel-idea-cuerpo { display: grid; gap: .5rem; margin-top: .6rem; }
.panel-idea-refs { display: flex; gap: 4px; flex-wrap: wrap; }
.panel-idea-refs img { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; }
.chip-tipo { font-size: .7rem; font-weight: 700; border: 1px solid var(--border); border-radius: 999px; padding: 0 .45rem; }
.panel-generar { border: 1px dashed var(--accent); border-radius: var(--radius); padding: .8rem; }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py tests/test_sprints_tablero_rutas.py tests/test_modo_oscuro.py`
Expected: PASS. Then the fast suite once.

- [ ] **Step 8: Commit**

```bash
git add -A sprints/rutas.py templates/ static/style.css tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py tests/test_sprints_tablero_rutas.py
git commit -m "Sprints tablero 2: las ideas y la caja «Generar» viven en la pestaña Ideas del panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Pestaña «Piezas» con revisión y actualización automática

**Files:**
- Modify: `sprints/revision.py` (`aprobar_pasaron_qa`), `sprints/rutas.py` (`_piezas_de`, `_piezas_revision`, `_contexto_piezas`, `campana_piezas`, `campana_panel`, `_volver_pieza`, `pieza_reintentar`, `pieza_regenerar`, `pieza_qa`, `revision_aprobar_qa`)
- Rewrite: `templates/_sprint_panel_piezas.html`
- Modify: `templates/_sprint_panel.html` (root gets `data-url-piezas`), `templates/sprint_detalle.html` (piezas JS), `static/style.css`
- Test: `tests/test_sprints_tablero_entrega2.py`

**Interfaces:**
- Consumes: Task 2 (`tablero:paso`, `tablero:cerrado` events, `window.tablero.abrir/refrescarTarjeta`), Task 3 (`_volver_panel`).
- Produces:
  - `sprints.revision.aprobar_pasaron_qa(cliente, sprint_id, campana_id=None) -> int`.
  - `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/piezas` (`sprints.campana_piezas`) → `_sprint_panel_piezas.html` alone.
  - JSON (fetch): `pieza_reintentar` → `{ok, error}` (409 when not in error / already running, 400 invalid); `pieza_regenerar` → `{ok, error}` (400 on error); `pieza_qa` → `{ok, error}` (400 not ready, 409 already running); `revision_aprobar_qa` (form field `campana_id` optional) → `{ok: true, aprobadas}`. Form posts with `volver=panel` return to the panel's Piezas tab.
  - Piezas tab DOM: root `.panel-piezas[data-piezas-vivas="1|0"]`; cards `.panel-pieza[data-cp][data-url-revision]` with `[data-pieza-accion="aprobar|rechazar|confirmar-rechazo|cancelar-rechazo"]`, `[data-rechazo]` holding `textarea[data-motivo]`, `[data-pieza-post][data-url][data-confirmar]`, `[data-error-pieza]`; `[data-aprobar-qa][data-url][data-campana]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_tablero_entrega2.py`:

```python
# --------------------------------------------------------------- piezas ---

def test_pestana_piezas_muestra_estados_qa_y_acciones(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    html = _panel(con_ideas["c"], sid, cid, "piezas")
    for frag in ("Amanecer", "Marco", 'data-piezas-vivas="0"', 'data-pieza-accion="aprobar"',
                 'data-pieza-accion="rechazar"', "data-motivo", "Regenerar (US$", "Abrir en Crear",
                 "Aprobar las que pasaron QA (1)", ">90<"):
        assert frag in html, frag
    assert "prompt(" not in html


def test_piezas_se_piden_solas(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    r = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/piezas")
    assert r.status_code == 200 and r.data.decode().lstrip().startswith('<div class="panel-piezas"')
    otro = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/campanas/999/piezas")
    assert otro.status_code == 404


def test_piezas_vivas_se_marcan(con_ideas):
    from sprints import datos
    c, sid, cid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"]
    datos.actualizar_idea("acme", iv, cf_id=datos.reserva_placeholder(iv))      # reserva viva = en marcha
    assert 'data-piezas-vivas="1"' in _panel(c, sid, cid, "piezas")


def test_aprobar_qa_solo_de_esta_campana(con_ideas, monkeypatch, tmp_path):
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    url = f"/cliente/acme/sprints/{sid}/revision/aprobar_qa"
    j = c.post(url, data={"campana_id": cid + 1000}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j == {"ok": True, "aprobadas": 0} and datos.idea("acme", iv)["revision"] == "pendiente"
    j = c.post(url, data={"campana_id": cid}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j == {"ok": True, "aprobadas": 1} and datos.idea("acme", iv)["revision"] == "aprobada"


def test_reintentar_regenerar_y_qa_por_fetch(con_ideas, monkeypatch, tmp_path):
    from sprints import datos, rutas
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    H = {"X-Requested-With": "fetch"}
    monkeypatch.setattr(rutas.produccion, "reintentar", lambda cliente, cp: False)
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/reintentar", headers=H)
    assert r.status_code == 409 and not r.get_json()["ok"]
    monkeypatch.setattr(rutas.produccion, "regenerar", lambda cliente, cp: "cf-nuevo")
    assert c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", headers=H).get_json() == {"ok": True, "error": None}
    monkeypatch.setattr(rutas.produccion, "regenerar",
                        lambda cliente, cp: (_ for _ in ()).throw(datos.ErrorDatos("No se puede.")))
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", headers=H)
    assert r.status_code == 400 and r.get_json()["error"] == "No se puede."
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_qa", lambda cliente, cp: True)
    assert c.post(f"/cliente/acme/sprints/ideas/{iv}/qa", headers=H).get_json()["ok"]
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", data={"volver": "panel"})
    assert r.headers["Location"].endswith(f"/sprints/{sid}")    # error: vuelve al tablero como antes
    monkeypatch.setattr(rutas.produccion, "regenerar", lambda cliente, cp: "cf-nuevo")
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar", data={"volver": "panel"})
    assert r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}&paso=piezas")
```

Check before writing: in `tests/test_rutas_sprints.py`, `_con_piezas` gives `iv` a QA with `veredicto: "pasa"` and score 90 and `ii` one with `revisar`, both with sessions in state `video_listo` (the pieza row's `estado` becomes `listo`); confirm the actual pieza `estado` the join yields for them and adapt `>90<` only if the score renders differently.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py -k "pieza or piezas or qa"`
Expected: FAIL — placeholder tab, no `campana_piezas` route, no JSON answers.

- [ ] **Step 3: Backend**

`sprints/revision.py` — replace `aprobar_pasaron_qa` with:

```python
def aprobar_pasaron_qa(cliente, sprint_id, campana_id=None):
    """Aprueba las piezas terminadas, pendientes, cuyo QA pasó; con
    `campana_id`, solo las de esa campaña (pestaña Piezas del panel)."""
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    n = 0
    for c in sp["campanas"]:
        if campana_id is not None and c["id"] != campana_id:
            continue
        for p in c["piezas"]:
            if p.get("revision") == "pendiente" and p.get("estado") in TERMINADAS and (p.get("qa") or {}).get("veredicto") == "pasa":
                if aprobar(cliente, p["id"]):
                    n += 1
    return n
```

`sprints/rutas.py`:

1. Replace `_piezas_revision` with:

```python
def _piezas_de(cliente, c, modelo_video, modelo_imagen):
    """Piezas con sesión de una campaña, con su costo de regeneración
    (estimado gratis, el mismo que muestra el botón antes de gastar)."""
    salida = []
    for p in c["piezas"]:
        if p["tipo"] == "video":
            costo = (flowplus_modelos.estimate_video(modelo_video, produccion._duracion(p)) or {}).get("usd") or 0.0
        else:
            costo = (flowplus_modelos.estimate_imagen(modelo_imagen, n_referencias=produccion._n_referencias(cliente, c))
                     or {}).get("usd") or 0.0
        salida.append({**p, "campana_n": int(c["orden"]) + 1, "persona_nombre": c["persona_nombre"],
                       "temporada_nombre": c["temporada_nombre"], "catalogo_id": c["catalogo_id"],
                       "funnel": c.get("funnel") or "tof", "costo_regenerar": round(float(costo), 3)})
    return salida


def _piezas_revision(cliente, sp):
    """Piezas con sesión de todas las campañas del sprint."""
    mv, mi = produccion.modelos(cliente)
    return [p for c in sp["campanas"] for p in _piezas_de(cliente, c, mv, mi)]


def _contexto_piezas(cliente, sp, c):
    """Lo que muestra la pestaña Piezas del panel (entrega 2 del tablero)."""
    mv, mi = produccion.modelos(cliente)
    piezas = _piezas_de(cliente, c, mv, mi)
    resumen = next((x for x in produccion.progreso(cliente, sp["id"])["campanas"] if x["id"] == c["id"]), {})
    vivas = any(produccion.pieza_viva(p) or (p.get("estado") in revision_mod.TERMINADAS and not p.get("qa"))
                for p in piezas)
    pasaron_qa = sum(1 for p in piezas if p.get("revision") == "pendiente" and p.get("estado") in revision_mod.TERMINADAS
                     and (p.get("qa") or {}).get("veredicto") == "pasa")
    return {"piezas": piezas, "resumen_piezas": resumen, "piezas_vivas": vivas, "pasaron_qa": pasaron_qa,
            "checks": CHECKS_QA}
```

2. `campana_panel`: add `**_contexto_piezas(cliente, sp, c),` to its `render_template(...)` arguments.

3. After `campana_panel` add:

```python
@bp.get("/<int:sid>/campanas/<int:cid>/piezas")
def campana_piezas(cliente, sid, cid):
    """Solo la pestaña Piezas: el panel la vuelve a pedir cada 8 s mientras
    algo se genera o espera QA. No gasta nada."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    return render_template("_sprint_panel_piezas.html", cliente=cliente, sprint=sp, c=c,
                           **_contexto_piezas(cliente, sp, c))
```

4. Replace `_volver_pieza` with:

```python
def _volver_pieza(cliente, i):
    """A la bandeja si el formulario vino de ahí (`volver=revision`), a la
    pestaña Piezas del panel (`volver=panel`); si no, al sprint."""
    if request.form.get("volver") == "revision":
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    if request.form.get("volver") == "panel":
        return _volver_panel(cliente, i["sprint_id"], i["campana_id"], "piezas")
    return _volver(cliente, i["sprint_id"])
```

5. Replace `pieza_reintentar`, `pieza_regenerar`, `pieza_qa` and `revision_aprobar_qa` with:

```python
@bp.post("/ideas/<int:cp_id>/reintentar")
def pieza_reintentar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        ok = produccion.reintentar(cliente, cp_id)
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    error = None if ok else "Esa pieza no está en error o ya se está generando."
    if _quiere_json():
        return jsonify({"ok": bool(ok), "error": error}), (200 if ok else 409)
    flash("Reintentando la pieza." if ok else error, "ok" if ok else "warn")
    return _volver_pieza(cliente, i)


@bp.post("/ideas/<int:cp_id>/regenerar")
def pieza_regenerar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        produccion.regenerar(cliente, cp_id)
    except (datos.ErrorDatos, ValueError) as e:
        # ValueError: `creative_flow.duplicar` con una sesión que no existe
        # (cf_id colgado o placeholder) — se muestra como un ErrorDatos.
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True, "error": None})
    flash("Regenerando la pieza (sesión nueva, misma idea).", "ok")
    return _volver_pieza(cliente, i)
```

```python
@bp.post("/ideas/<int:cp_id>/qa")
def pieza_qa(cliente, cp_id):
    """«Repetir QA»: limpia el marcador (`qa=None`) y encola un solo
    `sprint_qa_pieza` para la sesión actual. Solo visión (centavos), nunca
    generación: sin puerta de costo."""
    i = _idea_o_404(cliente, cp_id)
    destino = redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    if not i.get("cf_id") or i.get("estado") not in revision_mod.TERMINADAS:
        if _quiere_json():
            return jsonify({"ok": False, "error": "Esa pieza todavía no está lista para el QA."}), 400
        flash("Esa pieza todavía no está lista para el QA.", "error")
        return destino
    datos.actualizar_idea(cliente, cp_id, qa=None)
    ok = tareas_sprints.encolar_qa(cliente, cp_id)
    if _quiere_json():
        return jsonify({"ok": bool(ok), "error": None if ok else "Ya hay un QA en curso para esa pieza."}), \
            (200 if ok else 409)
    if ok:
        flash("Repitiendo el QA de la pieza; el resultado aparecerá aquí en unos segundos.", "ok")
    else:
        flash("Ya hay un QA en curso para esa pieza.", "warn")
    return destino
```

```python
@bp.post("/<int:sid>/revision/aprobar_qa")
def revision_aprobar_qa(cliente, sid):
    _sprint_o_404(cliente, sid)
    n = revision_mod.aprobar_pasaron_qa(cliente, sid, campana_id=request.form.get("campana_id", type=int))
    if _quiere_json():
        return jsonify({"ok": True, "aprobadas": n})
    flash(f"{n} pieza(s) aprobada(s) por haber pasado el QA.", "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=sid))
```

(`produccion.pieza_viva` and `revision_mod.TERMINADAS` exist; `CHECKS_QA` is defined further down in the module and is read at call time.)

- [ ] **Step 4: Template `_sprint_panel_piezas.html`**

Replace the placeholder with:

```html
{# Pestaña «Piezas» del panel (spec 2026-09-27 §Pestaña «Piezas»). También se
   pide sola (sprints.campana_piezas) para actualizarse mientras algo se genera o
   espera QA. Contexto de rutas._contexto_piezas: piezas, resumen_piezas,
   piezas_vivas, pasaron_qa, checks. Sin <script>. #}
{% set rp = resumen_piezas %}
<div class="panel-piezas" data-piezas-vivas="{{ '1' if piezas_vivas else '0' }}">
  <section class="panel-seccion">
    <div class="panel-piezas-cab">
      <p>{{ rp.listas or 0 }} listas · {{ rp.generando or 0 }} generando · {{ rp.encoladas or 0 }} en cola · {{ rp.error or 0 }} con error · <strong>{{ rp.aprobadas or 0 }} aprobadas</strong> · US$ {{ '%.2f' % (rp.costo_usd or 0) }} gastado</p>
      {% if pasaron_qa %}
      <button type="button" class="btn-generar btn-sm" data-aprobar-qa data-campana="{{ c.id }}"
              data-url="{{ url_for('sprints.revision_aprobar_qa', cliente=cliente, sid=sprint.id) }}">Aprobar las que pasaron QA ({{ pasaron_qa }})</button>
      {% endif %}
    </div>
  </section>
  {% if piezas %}
  <div class="panel-piezas-grid">
    {% for p in piezas %}
    <article class="panel-pieza panel-pieza-{{ p.revision }}" data-cp="{{ p.id }}"
             data-url-revision="{{ url_for('sprints.pieza_revision', cliente=cliente, cp_id=p.id) }}">
      <div class="panel-pieza-media">
        {% if p.estado in ("listo", "degradada") and p.url_video %}
          {% if p.tipo == "video" %}<video src="{{ p.url_video }}" {% if p.url_miniatura %}poster="{{ p.url_miniatura }}"{% endif %} controls muted playsinline preload="none"></video>
          {% else %}<img src="{{ p.url_video }}" alt="{{ p.titulo or '' }}" loading="lazy">{% endif %}
        {% elif p.estado == "error" %}<p class="campo-error">Error: {{ p.pieza_error or 'sin detalle' }}</p>
        {% else %}<p class="vacio">{{ 'Generando…' if p.estado == 'generando' else 'En cola…' }}</p>{% endif %}
      </div>
      <strong>{{ p.titulo }}</strong>
      <small class="vacio">{{ p.tipo }}{% if p.costo_usd %} · US$ {{ '%.2f' % p.costo_usd }}{% endif %} · {{ p.revision }}</small>
      {% if p.qa and p.qa.veredicto == "error" %}
      <p class="panel-pieza-qa"><span class="campo-error">QA falló: {{ p.qa.nota or 'sin detalle' }}</span>
        <button type="button" class="btn-xs" data-pieza-post data-url="{{ url_for('sprints.pieza_qa', cliente=cliente, cp_id=p.id) }}">Repetir QA</button></p>
      {% elif p.qa %}
      <p class="panel-pieza-qa"><span class="sprint-qa-score sprint-qa-{{ p.qa.veredicto }}">{{ p.qa.score }}</span>
        {% for k in checks %}{% set ch = (p.qa.checks or {}).get(k) %}{% if ch %}<span class="qa-check {{ 'ok' if ch.ok else 'mal' }}" title="{{ k | replace('_', ' ') }}: {{ ch.nota }}">{{ '✓' if ch.ok else '✗' }}</span>{% endif %}{% endfor %}
        <small class="vacio">{{ p.qa.veredicto }}</small></p>
      {% elif p.estado in ("listo", "degradada") %}<p class="vacio">QA pendiente…</p>{% endif %}
      {% if p.revision == "rechazada" and p.revision_motivo %}<p class="campo-error">Motivo: {{ p.revision_motivo }}</p>{% endif %}
      <div class="panel-acciones">
        {% if p.estado in ("listo", "degradada") %}
          {% if p.revision != "aprobada" %}<button type="button" class="btn-generar btn-xs" data-pieza-accion="aprobar">Aprobar</button>{% endif %}
          {% if p.revision != "rechazada" %}<button type="button" class="btn-xs btn-rechazar" data-pieza-accion="rechazar">Rechazar</button>{% endif %}
          <a class="btn-xs" href="{{ url_for('ver_cliente', cliente=cliente, _anchor='creativeflowplus') }}">Abrir en Crear</a>
        {% endif %}
        {% if p.estado == "error" %}
        <button type="button" class="btn-xs" data-pieza-post data-url="{{ url_for('sprints.pieza_reintentar', cliente=cliente, cp_id=p.id) }}"
                data-confirmar="Reintentar gasta de nuevo (US$ {{ p.costo_regenerar }}). ¿Seguir?">Reintentar (US$ {{ p.costo_regenerar }})</button>
        {% endif %}
        {% if p.estado in ("listo", "degradada", "error") %}
        <button type="button" class="btn-xs" data-pieza-post data-url="{{ url_for('sprints.pieza_regenerar', cliente=cliente, cp_id=p.id) }}"
                data-confirmar="Regenerar crea una pieza nueva con la misma idea (US$ {{ p.costo_regenerar }}). ¿Seguir?">Regenerar (US$ {{ p.costo_regenerar }})</button>
        {% endif %}
      </div>
      <div class="panel-rechazo" data-rechazo hidden>
        <label>¿Por qué no sirve? <small class="vacio">(lo usa la próxima versión)</small>
          <textarea rows="2" maxlength="300" data-motivo></textarea></label>
        <div class="panel-acciones">
          <button type="button" class="btn-xs btn-rechazar" data-pieza-accion="confirmar-rechazo">Rechazar</button>
          <button type="button" class="btn-xs" data-pieza-accion="cancelar-rechazo">Cancelar</button>
        </div>
      </div>
      <small class="campo-error" data-error-pieza hidden></small>
    </article>
    {% endfor %}
  </div>
  {% else %}
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay piezas</p>
    <p class="estado-vacio-texto">Aprueba ideas y genéralas desde la pestaña Ideas.</p>
    <button type="button" class="btn-sm" data-ir-paso="ideas">Ir a Ideas</button>
  </div>
  {% endif %}
</div>
```

In `templates/_sprint_panel.html` add to the root `<div class="panel-campana" …>` the attribute `data-url-piezas="{{ url_for('sprints.campana_piezas', cliente=cliente, sid=sprint.id, cid=c.id) }}"`.

- [ ] **Step 5: Piezas JS (panel `<script>` of `sprint_detalle.html`)**

1. Add after the Ideas functions (Task 3):

```js
    // ---- Pestaña Piezas (entrega 2): revisión y actualización cada 8 s ----
    var relojPiezas = null;
    function cajaPiezas() { return cuerpo.querySelector('[data-pestana="piezas"]'); }
    function escribiendoMotivo() {
      return Array.prototype.some.call(cuerpo.querySelectorAll('[data-motivo]'),
                                       function (t) { return t.value.trim() || document.activeElement === t; });
    }
    function programarPiezas() {
      clearTimeout(relojPiezas);
      relojPiezas = null;
      var caja = cajaPiezas();
      if (caja && !caja.hidden && caja.querySelector('[data-piezas-vivas="1"]')) relojPiezas = setTimeout(refrescarPiezas, 8000);
    }
    function refrescarPiezas() {
      var r = raiz(), caja = cajaPiezas();
      if (!r || !caja) return Promise.resolve();
      return fetch(r.dataset.urlPiezas, {headers: H})
        .then(function (x) { return x.ok ? x.text() : Promise.reject(); })
        .then(function (html) { if (!escribiendoMotivo()) caja.innerHTML = html; programarPiezas(); })
        .catch(function () { programarPiezas(); });
    }
    function trasAccionPieza() { T.refrescarTarjeta(raiz().dataset.cid); return refrescarPiezas(); }
    document.addEventListener('tablero:paso', programarPiezas);
    document.addEventListener('tablero:cerrado', function () { clearTimeout(relojPiezas); relojPiezas = null; });
```

2. At the end of `window.tableroPanelListo` (inside it) add `programarPiezas();`.

3. In the panel `click` listener, after the Ideas branches (Task 3) add:

```js
      var accionPieza = ev.target.closest('[data-pieza-accion]');
      if (accionPieza) {
        var cardP = accionPieza.closest('.panel-pieza'), errP = cardP.querySelector('[data-error-pieza]');
        var rechazo = cardP.querySelector('[data-rechazo]'), motivo = rechazo.querySelector('[data-motivo]');
        var acc = accionPieza.dataset.piezaAccion;
        errP.hidden = true;
        if (acc === 'rechazar') { rechazo.hidden = false; motivo.focus(); return; }
        if (acc === 'cancelar-rechazo') { motivo.value = ''; delete motivo.dataset.sucio; rechazo.hidden = true; return; }
        var cuerpoRev = {accion: 'aprobar'};
        if (acc === 'confirmar-rechazo') {
          if (!motivo.value.trim()) { errP.textContent = 'Escribe por qué no sirve.'; errP.hidden = false; return; }
          cuerpoRev = {accion: 'rechazar', motivo: motivo.value.trim()};
        }
        accionPieza.disabled = true;
        fetch(cardP.dataset.urlRevision, {method: 'POST', headers: HJ, body: JSON.stringify(cuerpoRev)}).then(T.json)
          .then(function () { motivo.value = ''; delete motivo.dataset.sucio; return trasAccionPieza(); })
          .catch(function (e) { accionPieza.disabled = false; errP.textContent = T.mensaje(e); errP.hidden = false; });
        return;
      }
      var postPieza = ev.target.closest('[data-pieza-post]');
      if (postPieza) {
        if (postPieza.dataset.confirmar && !confirm(postPieza.dataset.confirmar)) return;
        var errQ = postPieza.closest('.panel-pieza').querySelector('[data-error-pieza]');
        postPieza.disabled = true;
        errQ.hidden = true;
        fetch(postPieza.dataset.url, {method: 'POST', headers: H}).then(T.json).then(trasAccionPieza)
          .catch(function (e) { postPieza.disabled = false; errQ.textContent = T.mensaje(e); errQ.hidden = false; });
        return;
      }
      var aprobarQa = ev.target.closest('[data-aprobar-qa]');
      if (aprobarQa) {
        aprobarQa.disabled = true;
        var fdQ = new FormData();
        fdQ.append('campana_id', aprobarQa.dataset.campana);
        fetch(aprobarQa.dataset.url, {method: 'POST', headers: H, body: fdQ}).then(T.json).then(trasAccionPieza)
          .catch(function (e) { aprobarQa.disabled = false; avisar(T.mensaje(e)); });
        return;
      }
```

- [ ] **Step 6: CSS**

Append to the Tablero block of `static/style.css`:

```css
.panel-piezas-cab { display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap; }
.panel-piezas-cab p { margin: 0; }
.panel-piezas-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr)); gap: .8rem; margin-top: .8rem; }
.panel-pieza { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: .6rem; display: grid; gap: .4rem;
  background: var(--panel); min-width: 0; }
.panel-pieza-aprobada { border-color: var(--ok); }
.panel-pieza-rechazada { border-color: var(--error); }
.panel-pieza-media video, .panel-pieza-media img { width: 100%; max-height: 360px; object-fit: contain; display: block;
  border-radius: 6px; background: var(--panel-2); }
.panel-pieza-qa { margin: 0; display: flex; gap: .3rem; align-items: center; flex-wrap: wrap; }
.panel-rechazo { display: grid; gap: .4rem; }
.panel-rechazo[hidden] { display: none; }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py tests/test_sprints_revision.py tests/test_modo_oscuro.py`
(if `tests/test_sprints_revision.py` does not exist, drop it from the command). Expected: PASS. Then the fast suite once.

- [ ] **Step 8: Commit**

```bash
git add sprints/revision.py sprints/rutas.py templates/_sprint_panel.html templates/_sprint_panel_piezas.html templates/sprint_detalle.html static/style.css tests/test_sprints_tablero_entrega2.py
git commit -m "Sprints tablero 2: la pestaña Piezas revisa, reintenta y se actualiza sola mientras algo se genera

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Revisión de todo el sprint, renovada por encima

**Files:**
- Modify: `sprints/rutas.py` (`revision`), `templates/sprint_revision.html`
- Test: `tests/test_sprints_tablero_entrega2.py`, `tests/test_rutas_sprints.py` (only if an assertion depends on the old temporada label)

**Interfaces:**
- Consumes: Task 4 (`_piezas_de` adds `funnel`; `_volver_panel` URL shape `?panel=<cid>&paso=piezas`).
- Produces: revision page with campaign filter «<n> · <ETAPA> · <persona> · <producto>», per-piece «Abrir en el panel» link, inline rejection (`[data-rechazo]` + `textarea[data-motivo]`), no `prompt(`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sprints_tablero_entrega2.py`:

```python
# -------------------------------------------------------- revisión sprint ---

def test_revision_del_sprint_renovada(con_ideas, monkeypatch, tmp_path):
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    html = con_ideas["c"].get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
    assert f'<option value="{cid}">1 · TOF · Premium · Espejo LED</option>' in html
    assert f"/cliente/acme/sprints/{sid}?panel={cid}&amp;paso=piezas" in html and "Abrir en el panel" in html
    assert "data-motivo" in html and "data-rechazo" in html and "prompt(" not in html
    assert "if (e.metaKey || e.ctrlKey || e.altKey) return;" in html       # los atajos siguen
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py -k revision_del_sprint`
Expected: FAIL.

- [ ] **Step 3: Implement**

`sprints/rutas.py` — in `revision`, add `productos_por_id={p["id"]: p for p in _productos_planos(cliente)}` to its `render_template(...)` arguments.

`templates/sprint_revision.html`:

1. The campaign filter options become:

```html
    <select id="filtro-campana"><option value="">todas</option>{% for c in sprint.campanas %}<option value="{{ c.id }}">{{ c.orden + 1 }} · {{ (c.funnel or 'tof') | upper }} · {{ c.persona_nombre }} · {{ (productos_por_id.get(c.catalogo_id) or {}).get('nombre') or c.catalogo_id }}</option>{% endfor %}</select>
```

2. In each card, the line `<small class="vacio">Campaña {{ p.campana_n }} · {{ p.persona_nombre }} · {{ p.temporada_nombre or "sin temporada" }} · {{ p.tipo }}…` becomes:

```html
      <small class="vacio">Campaña {{ p.campana_n }} · {{ p.funnel | upper }} · {{ p.persona_nombre }} · {{ p.tipo }}{% if p.costo_usd %} · USD {{ '%.2f' % p.costo_usd }}{% endif %}</small>
```

3. In `.sprint-ref-acciones`, after the «Final edition» link add:

```html
        <a class="btn-xs" href="{{ url_for('sprints.ver', cliente=cliente, sid=sprint.id, panel=p.campana_id, paso='piezas') }}">Abrir en el panel</a>
```

(outside the `{% if p.estado in ("listo", "degradada") %}` block, so it shows for every piece).

4. After the `.sprint-ref-acciones` div, inside the card, add:

```html
      <div class="panel-rechazo" data-rechazo hidden>
        <label>¿Por qué no sirve? <small class="vacio">(lo usa la próxima versión)</small>
          <textarea rows="2" maxlength="300" data-motivo></textarea></label>
        <div class="acciones">
          <button type="button" class="btn-xs btn-rechazar js-confirmar-rechazo">Rechazar</button>
          <button type="button" class="btn-xs js-cancelar-rechazo">Cancelar</button>
        </div>
        <small class="campo-error" hidden></small>
      </div>
```

5. In the page script:
- Replace `accionSeleccionada` with:

```js
    function abrirRechazo(card) {
      var caja = card.querySelector('[data-rechazo]');
      caja.hidden = false;
      caja.querySelector('[data-motivo]').focus();
    }
    function accionSeleccionada(accion) {
      var card = grid.querySelector('.sprint-pieza.seleccionada');
      if (!card || !card.querySelector('.js-aprobar')) return;
      if (accion === 'rechazar') abrirRechazo(card);
      else enviar(card, 'aprobar');
    }
```

- In `tarjetas.forEach(function (card, i) { … })` replace the `r.addEventListener('click', …prompt…)` line with `if (r) r.addEventListener('click', function () { abrirRechazo(card); });` and add, inside the same forEach:

```js
      var caja = card.querySelector('[data-rechazo]');
      caja.querySelector('.js-cancelar-rechazo').addEventListener('click', function () {
        var m = caja.querySelector('[data-motivo]'); m.value = ''; delete m.dataset.sucio; caja.hidden = true;
      });
      caja.querySelector('.js-confirmar-rechazo').addEventListener('click', function () {
        var m = caja.querySelector('[data-motivo]'), err = caja.querySelector('.campo-error');
        if (!m.value.trim()) { err.textContent = 'Escribe por qué no sirve.'; err.hidden = false; return; }
        err.hidden = true;
        enviar(card, 'rechazar', m.value.trim());
        m.value = ''; delete m.dataset.sucio; caja.hidden = true;
      });
```

- In `enviar`, on `!j.ok` replace `alert(j.error)` with showing it in the card: `var e = card.querySelector('[data-rechazo] .campo-error'); card.querySelector('[data-rechazo]').hidden = false; e.textContent = j.error; e.hidden = false; return;`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py`
Expected: PASS. Then the fast suite once.

- [ ] **Step 5: Commit**

```bash
git add sprints/rutas.py templates/sprint_revision.html tests/test_sprints_tablero_entrega2.py tests/test_rutas_sprints.py
git commit -m "Sprints tablero 2: la revisión del sprint lleva al panel y pide el motivo dentro de la tarjeta

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentación, verificación en pantalla y despliegue (controller)

This task is run by the controller, not a subagent.

- [ ] **Step 1: CLAUDE.md** — in the «Sprints de contenido» paragraph add: «Entrega 2 (spec `docs/superpowers/specs/2026-09-27-sprints-tablero-entrega2-design.md`): the panel has three tabs — Armar · Ideas · Piezas (`_sprint_panel_armar.html`, `_sprint_panel_ideas.html`, `_sprint_panel_piezas.html`, all rendered in one fragment; `?panel=<cid>&paso=…`, default from `tablero.paso_por_defecto`). Ideas and the «Generar» cost gate live in the Ideas tab (`campana_ideas` now redirects there); the Piezas tab reviews, retries and regenerates with prices and refreshes itself every 8 s via `sprints.campana_piezas`; the sprint-wide review page stays for bulk review. «Proponer ideas» shows `gastos.estimar("proponer_ideas", n=)` and registers its real spend (tipo `ideas`, `max_intentos=1`).»
- [ ] **Step 2: Full suite** — `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider`; all green.
- [ ] **Step 3: Local visual check (no real keys)** — local launcher on port 5072 with the worktree's DB copy (`alembic upgrade head` on it first), desktop 1280×800 and mobile 375×812, dark mode: open a campaign, switch tabs (URL keeps `paso`), describe a reference, edit an idea and its angle, estimate «Generar», open Piezas with pieces in several states (seed them in the local copy), reject with a reason, check no horizontal scroll and the console free of errors.
- [ ] **Step 4: Final whole-branch review** (most capable model) and one fix wave.
- [ ] **Step 5: Deploy** — no migration: `git fetch && git rebase origin/main`, suite, `git push origin sprints-tablero-2:main`; on the VPS back up the DB, check no `tarea` is `en_curso`/`pendiente`, `git pull --ff-only`, restart both services (`tareas/sprints.py` changed), `curl /login` 200, the served `style.css` has «Entrega 2 (2026-09-27)», smoke test of every sprint's panel with `?paso=ideas` and `?paso=piezas`.
- [ ] **Step 6: Memory** — update `sprints-contenido-estado.md` and the MEMORY.md line.
