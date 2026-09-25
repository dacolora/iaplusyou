# Biblioteca de referentes — Bloque 6 (panel admin completo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish `/admin/referentes` — an admin-only "Traer referentes globales" flow (the same barrido machinery every client already gets, run with `cliente=NULL`), totals by fuente, Atria's monthly call-quota counter, an editable familias table, and `ATRIA_API_KEY`/`APIFY_TOKEN` status cards in Puesta a punto.

**Architecture:** Everything lives in the existing `/admin/referentes` surface (`dashboard.py` route + `templates/admin_referentes.html`) — this block adds sections to that one page rather than building new pages. The global "Traer referentes" form reuses the exact parsing/estimating/launching logic the per-client form already uses (`referentes.rutas._consulta_desde`, `referentes.fuentes.*`, `gastos.estimar`, `tareas.referentes.encolar_barrer`) through two new routes on `app` (matching how every other `/admin/*` route is registered), rather than trying to reach the per-client Blueprint's routes (which hard-require a non-empty `<cliente>` URL segment and can't represent `cliente=None`). The admin form is a plain page-reload form (no live JS price refresh) — that complexity belongs to the polished per-client dialog UI, not an internal admin tool.

**Tech Stack:** Python 3.9, Flask, SQLAlchemy Core, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md` (§8 "Admin", §17 orden de entrega punto 6).

## Global Constraints

- Every paid action must show its price before spending — the admin "Traer referentes globales" form must show the estimated cost before "Traer y clasificar" is clickable, exactly like the per-client form already does. This is this codebase's core rule (CLAUDE.md: "nothing generates or publishes silently") and was a Critical finding in Block 4's final review when it slipped through.
- Every `/admin/*` route is `@app.route(...)` + `@requiere_admin` (redirects to `login` with a flash if the session isn't `rol == "admin"`); every mutating `/admin/*` POST additionally checks `_mismo_origen()` and `abort(403)` if it fails — both already defined in `dashboard.py`, do not reimplement.
- `referentes/fuentes/*` fuentes are MODULES (`estimar(consulta, tope)`, `probar()`, `traer(consulta, tope, avanzar, cursor=None)`), reached via `referentes.fuentes.por_tipo(tipo)`/`.tipos()`/`.llaves_faltantes(tipo)`/`.NOMBRES` — already built (Blocks 4-5), do not modify.
- `referentes/datos.py::familia_actualizar(familia_id, descripcion)`, `barridos(cliente=None, fuente=None)`, and `opciones(cliente)` already exist and are exactly what this block needs — do not add new data-layer functions duplicating them.
- `referentes/fuentes/atria.py::llamadas_este_mes()` and `limite_mensual()` already exist (both take no arguments, both return `int`) — do not add new counting logic.
- `SERVICIOS_LLAVES` in `dashboard.py` already has an `apify` entry (`variables: ["APIFY_TOKEN"]`) for Nicho's use of Apify — this block extends its description to also mention the Ad Library connector (same env var, two features), and adds a brand-new `atria` entry (`ATRIA_API_KEY` has no card today).
- `db.gasto.c.cliente` is `nullable=False` (verified in `db.py`) — every real charge must be attributed to a real client name string, unlike `db.barrido.c.cliente`/`db.referente.c.cliente`, which explicitly allow `NULL` for "global". A global (`cliente=NULL`) barrido must NEVER pass `None` straight through to `gastos.registrar_seguro(...)` — `referentes/datos.py::CLIENTE_CREATV = "_creatv"` is the existing sentinel for this (already used by copycoders' own import, which is also global), and Task 1 must use it wherever a global barrido's real cost gets registered.

---

### Task 1: Admin "Traer referentes globales" — price preview + launch

**Files:**
- Modify: `dashboard.py` (extend `admin_referentes()`, add `admin_referentes_traer()`)
- Modify: `templates/admin_referentes.html`
- Modify: `tareas/referentes.py` (`_fase_trayendo` — fix the `cliente=NULL` gasto gap described in Global Constraints)
- Test: `tests/test_rutas_referentes.py`, `tests/test_tareas_referentes.py`

**Interfaces:**
- Consumes: `referentes.rutas._consulta_desde(args)` and `referentes.rutas._entero(v, defecto)` (private helpers, imported directly — this codebase already does this for other admin routes, e.g. `dashboard.py`'s `admin_meta()` calls `meta_agencia._registro_ilegible()`), `referentes.fuentes.tipos()/.NOMBRES/.llaves_faltantes(tipo)/.por_tipo(tipo)`, `gastos.estimar("clasificacion", n=tope)`, `tareas.referentes.encolar_barrer(cliente, fuente, consulta, tope, usd_estimado, pedido_por=None)`, `referentes.datos.CLIENTE_CREATV` (`= "_creatv"`, already defined).
- Produces: nothing new for later tasks — this task's route additions are used only by its own template section.

- [ ] **Step 1: Write the failing tests**

Read `tests/test_rutas_referentes.py`'s existing `test_admin_referentes_importar` and `test_admin_referentes_solo_admin` (around lines 112-138) first to match the file's exact fixtures (`app`, `_cliente_admin`) and conventions before adding these:

```python
def test_admin_referentes_traer_muestra_precio(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr("referentes.fuentes.atria.estimar", lambda consulta, tope: {"usd_fuente": 0.0, "llamadas": 2, "detalle": "2 llamadas del plan de Atria"})
    c = app["c"]
    html = c.get("/admin/referentes?fuente=atria&modo=palabra&palabra=zapatos&tope=100").data.decode()
    assert "US$" in html
    assert 'name="tope"' in html


def test_admin_referentes_traer_lanza_barrido_global(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    llamadas = []
    monkeypatch.setattr(tr, "encolar_barrer", lambda *a, **kw: llamadas.append((a, kw)) or True)
    c = app["c"]
    r = c.post("/admin/referentes/traer", data={"fuente": "atria", "modo": "palabra", "palabra": "zapatos", "idioma": "es", "tope": "50"},
              headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert len(llamadas) == 1
    args, kw = llamadas[0]
    assert args[0] is None            # cliente=None: barrido global
    assert args[1] == "atria"
    assert args[2]["palabra"] == "zapatos"


def test_admin_referentes_traer_sin_fuente_no_lanza(app):
    c = app["c"]
    r = c.post("/admin/referentes/traer", data={"fuente": "no-existe"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    from referentes import datos
    assert datos.barridos(None, "no-existe") == []


def test_admin_referentes_traer_solo_admin(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    assert c.get("/admin/referentes").status_code == 302
    assert c.post("/admin/referentes/traer", data={}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 302


def test_fase_trayendo_barrido_global_registra_gasto_bajo_creatv(monkeypatch, base_temporal):
    """El costo real de un barrido global (cliente=NULL, disparado desde el
    panel admin) no puede intentar registrarse con cliente=None: db.gasto.c.cliente
    es NOT NULL. Debe caer en el mismo comodín que ya usa la importación de
    copycoders (datos.CLIENTE_CREATV = "_creatv"), no perderse en silencio."""
    import sqlalchemy as sa

    import db
    from referentes import datos
    from tareas import referentes as tareas_referentes

    bid = datos.crear_barrido(None, "apify", {"modo": "palabra", "palabra": "sandalias"}, 5)

    def traer_falso(consulta, tope, avanzar, cursor=None):
        avanzar("Buscando en Apify", "1 anuncios")
        yield [{"anuncio_id": "g1", "imagen_origen": "https://x/g1.jpg", "marca": "X", "titular": "", "cuerpo": "",
                "tipo": "imagen", "pais": None, "idioma": None, "dias": None, "variantes": None,
                "primera_vez": None, "ultima_vez": None, "activo": True, "url_anuncio": "", "url_marca": "",
                "etiquetas_fuente": {}, "extra": {}, "pagina_id": None}], None, {"costo_real": 0.031}

    class _ModuloFalso:
        traer = staticmethod(traer_falso)

    monkeypatch.setattr(tareas_referentes.fuentes, "por_tipo", lambda tipo: _ModuloFalso())
    tarea = {"id": 4321, "job_id": None, "payload": {"barrido_id": bid, "cliente": None,
             "consulta": {"modo": "palabra", "palabra": "sandalias", "fuente": "apify"}, "tope": 5, "fase": "trayendo"}}
    tareas_referentes.ejecutar_barrer(tarea)

    with db.conectar() as con:
        filas = con.execute(sa.select(db.gasto).where(db.gasto.c.tipo == "recoleccion")).mappings().all()
    assert len(filas) == 1
    assert filas[0]["cliente"] == datos.CLIENTE_CREATV
    assert filas[0]["usd"] == 0.031
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k admin_referentes_traer`
Expected: FAIL — `admin_referentes_traer` route doesn't exist yet (404s), and the GET route doesn't yet read `fuente`/`modo`/etc. query params.

Also run: `venv/bin/python3 -m pytest tests/test_tareas_referentes.py -v -k barrido_global_registra_gasto`
Expected: FAIL (see Step 4 below — the `cliente_gasto` fix doesn't exist yet, so the gasto row is either missing or the insert errors).

- [ ] **Step 3: Extend `admin_referentes()` and add `admin_referentes_traer()`**

Find the existing `admin_referentes()` route in `dashboard.py` (per the plan's research: lines ~3408-3421, right before `admin_referentes_importar()`). Replace it with this extended version, and add the new POST route right after `admin_referentes_importar()`:

```python
@app.route("/admin/referentes")
@requiere_admin
def admin_referentes():
    """Biblioteca de referentes (spec 2026-09-23 §7-§8): importar copycoders,
    traer un barrido global (cliente=NULL) de Atria/Apify, y ver totales."""
    from referentes import datos as ref_datos, fuentes
    from referentes.fuentes.atria import limite_mensual, llamadas_este_mes
    from referentes.rutas import _consulta_desde, _entero
    import gastos
    from tareas import referentes as tareas_ref

    historial = ref_datos.barridos(None, "copycoders")

    fuente = request.args.get("fuente") if request.args.get("fuente") in fuentes.tipos() else (fuentes.tipos()[0] if fuentes.tipos() else None)
    tope_traer = min(max(1, _entero(request.args.get("tope"), 200)), 2000)
    consulta_traer = _consulta_desde(request.args)
    fuente_llaves_faltantes = {t: fuentes.llaves_faltantes(t) for t in fuentes.tipos()}
    llaves_faltantes = fuentes.llaves_faltantes(fuente) if fuente else []
    precio_traer = None
    if fuente and not llaves_faltantes and (consulta_traer.get("pagina_id") or consulta_traer.get("palabra")):
        modulo = fuentes.por_tipo(fuente)
        try:
            est_fuente = modulo.estimar(consulta_traer, tope_traer)
        except Exception:  # noqa: BLE001 — el precio es informativo, nunca bloquea la página
            est_fuente = None
        if est_fuente:
            est_clasificacion = gastos.estimar("clasificacion", n=tope_traer)
            precio_traer = {"fuente": est_fuente, "clasificacion": est_clasificacion,
                            "total_usd": est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)}

    return render_template("admin_referentes.html", url_swipe=tareas_ref.copycoders.URL_SWIPE,
                           trabajo=({"job_id": tareas_ref.trabajo_importacion()} if tareas_ref.trabajo_importacion() else None),
                           ultimo=(historial[0] if historial else None), historial=historial[:10],
                           imagenes=ref_datos.contar_imagenes("copycoders"), total=ref_datos.opciones(None)["total"],
                           familias=ref_datos.familias(),
                           fuentes_tipos=fuentes.tipos(), fuentes_nombres=fuentes.NOMBRES,
                           fuente=fuente, consulta_traer=consulta_traer, tope_traer=tope_traer,
                           precio_traer=precio_traer, fuente_llaves_faltantes=fuente_llaves_faltantes,
                           atria_llamadas=llamadas_este_mes(), atria_limite=limite_mensual(),
                           fuentes_totales=ref_datos.opciones(None)["fuentes"],
                           barridos_otras_fuentes=[b for b in ref_datos.barridos(None) if b["fuente"] != "copycoders"])
```

```python
@app.route("/admin/referentes/traer", methods=["POST"])
@requiere_admin
def admin_referentes_traer():
    if not _mismo_origen():
        abort(403)
    from referentes import fuentes
    from referentes.fuentes.base import ErrorFuente
    from referentes.rutas import _consulta_desde, _entero
    import gastos
    from tareas import referentes as tareas_ref

    fuente = request.form.get("fuente")
    if fuente not in fuentes.tipos():
        flash("Elige una fuente.", "error")
        return redirect(url_for("admin_referentes"))
    if fuentes.llaves_faltantes(fuente):
        flash("Esa fuente no está configurada.", "error")
        return redirect(url_for("admin_referentes"))
    consulta = _consulta_desde(request.form)
    if consulta["modo"] == "marca" and not consulta["pagina_id"]:
        flash("Pega un link del Ad Library o el id de la página.", "error")
        return redirect(url_for("admin_referentes"))
    if consulta["modo"] == "palabra" and not consulta["palabra"]:
        flash("Escribe una palabra clave.", "error")
        return redirect(url_for("admin_referentes"))
    tope = min(max(1, _entero(request.form.get("tope"), 200)), 2000)
    modulo = fuentes.por_tipo(fuente)
    try:
        est_fuente = modulo.estimar(consulta, tope)
    except ErrorFuente as e:
        flash(e.usuario, "error")
        return redirect(url_for("admin_referentes"))
    est_clasificacion = gastos.estimar("clasificacion", n=tope)
    usd_estimado = est_fuente["usd_fuente"] + (est_clasificacion["usd"] or 0.0)
    tareas_ref.encolar_barrer(None, fuente, consulta, tope, usd_estimado, pedido_por=_sesion().get("usuario"))
    flash("Trayendo referentes globales; aparecerán en la tabla de barridos a medida que avanza.", "ok")
    return redirect(url_for("admin_referentes"))
```

- [ ] **Step 4: Fix `_fase_trayendo`'s gasto registration for a global (`cliente=NULL`) barrido**

`db.gasto.c.cliente` is `nullable=False` (see Global Constraints) — `_fase_trayendo` currently passes `p["cliente"]` straight to `gastos.registrar_seguro(...)` at both places it registers a real Apify cost, which would be `None` for a barrido launched from this task's new admin route. Read `tareas/referentes.py::_fase_trayendo` in full first (it has grown across Blocks 3 and 5 — confirm the two `gastos.registrar_seguro(p["cliente"], "recoleccion", costo_real, ...)` call sites, one inside the `for` loop and one inside the `except ErrorFuente` block, still match this shape before editing).

Add one line right after `fuente_mod = fuentes.por_tipo(consulta["fuente"])` near the top of the function:

```python
    cliente_gasto = p.get("cliente") or datos.CLIENTE_CREATV
```

Then change both `gastos.registrar_seguro(p["cliente"], "recoleccion", ...)` call sites to `gastos.registrar_seguro(cliente_gasto, "recoleccion", ...)` — every other argument at both call sites stays exactly as it is. Do not change `datos.guardar_referente(a, cliente=p["cliente"], barrido_id=bid)` (a few lines above, inside the same loop) — referente rows must keep the real `cliente` value (`None` for a truly global referente, per `db.referente.c.cliente`'s own "NULL = global" design) so `_visible()` still shows them to every project; only the `gasto` row (which cannot be `NULL`) needs the substitution.

Add this test to `tests/test_tareas_referentes.py` (it was already written in Step 1 above as `test_fase_trayendo_barrido_global_registra_gasto_bajo_creatv` — this step is where it starts passing):

Run: `venv/bin/python3 -m pytest tests/test_tareas_referentes.py -v -k barrido_global_registra_gasto`
Expected: FAIL before this step's edit (`IntegrityError` or the row silently missing — `registrar_seguro` never raises, so the failure shows as `len(filas) == 0` rather than a crash); PASS after.

- [ ] **Step 5: Add the form section to `templates/admin_referentes.html`**

Read the current file in full first (54 lines, reproduced in this plan's research — confirm it still matches before editing). Insert this new `<section>` right after the closing `</section>` of the "Swipe file de copycoders" block and before the "Familias" section:

```html
<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Traer referentes globales</h2></div>
  <p class="vacio">Igual que «Traer referentes» de un proyecto, pero sin dueño: quedan visibles para todos los proyectos.</p>
  <form method="get" action="{{ url_for('admin_referentes') }}" class="agencia-form">
    <div class="fe-opciones">
      {% for t in fuentes_tipos %}
      <label class="fe-check">
        <input type="radio" name="fuente" value="{{ t }}" {% if t == fuente %}checked{% endif %} {% if fuente_llaves_faltantes.get(t) %}disabled{% endif %}>
        {{ fuentes_nombres.get(t, t) }}{% if fuente_llaves_faltantes.get(t) %} (falta {{ fuente_llaves_faltantes[t] | join(', ') }}){% endif %}
      </label>
      {% endfor %}
    </div>
    <div class="fe-opciones">
      <label><input type="radio" name="modo" value="palabra" {% if consulta_traer.modo == 'palabra' %}checked{% endif %}> Palabra clave</label>
      <label><input type="radio" name="modo" value="marca" {% if consulta_traer.modo == 'marca' %}checked{% endif %}> Marca (link del Ad Library)</label>
    </div>
    <div class="fe-opciones">
      <label>Palabra clave <input type="text" name="palabra" value="{{ consulta_traer.palabra or '' }}" maxlength="120"></label>
      <label>Idioma <input type="text" name="idioma" value="{{ consulta_traer.idioma or 'es' }}" maxlength="5" style="width:4rem"></label>
      <label>Marca / link del Ad Library <input type="text" name="pagina_id" value="{{ consulta_traer.pagina_id or '' }}" placeholder="id de página o view_all_page_id"></label>
    </div>
    <div class="fe-opciones">
      <label>País (solo Apify) <input type="text" name="pais" value="{{ consulta_traer.pais or 'ALL' }}" maxlength="5" style="width:5rem"></label>
      <label>Formato
        <select name="formato">
          <option value="imagen" {% if consulta_traer.formato != 'video' %}selected{% endif %}>Imagen</option>
          <option value="video" {% if consulta_traer.formato == 'video' %}selected{% endif %}>Video</option>
        </select>
      </label>
      <label class="fe-check"><input type="checkbox" name="solo_activos" {% if consulta_traer.solo_activos %}checked{% endif %}> Solo activos</label>
    </div>
    <div class="fe-opciones">
      <label>Mínimo de días (solo Atria) <input type="number" name="min_dias" value="{{ consulta_traer.min_dias or '' }}" min="0" style="width:5rem"></label>
      <label>Mínimo de variantes (solo Atria) <input type="number" name="min_variantes" value="{{ consulta_traer.min_variantes or '' }}" min="0" style="width:5rem"></label>
      <label>Tope <input type="number" name="tope" value="{{ tope_traer }}" min="1" max="2000" style="width:6rem"></label>
    </div>
    {% if precio_traer %}
    <p class="vacio">Fuente: {{ precio_traer.fuente.detalle }} · Clasificar {{ tope_traer }} con Claude: {{ precio_traer.clasificacion.texto }} ·
      <strong>Total ≈ US$ {{ '%.2f' | format(precio_traer.total_usd) }}</strong></p>
    {% else %}
    <p class="vacio">Completa los datos y pulsa «Ver precio» para calcular el costo antes de traer.</p>
    {% endif %}
    <button type="submit" class="btn-xs">Ver precio</button>
  </form>
  {% if precio_traer %}
  <form method="post" action="{{ url_for('admin_referentes_traer') }}" class="agencia-form">
    <input type="hidden" name="fuente" value="{{ fuente }}">
    <input type="hidden" name="modo" value="{{ consulta_traer.modo }}">
    <input type="hidden" name="palabra" value="{{ consulta_traer.palabra or '' }}">
    <input type="hidden" name="idioma" value="{{ consulta_traer.idioma or 'es' }}">
    <input type="hidden" name="pagina_id" value="{{ consulta_traer.pagina_id or '' }}">
    <input type="hidden" name="pais" value="{{ consulta_traer.pais or 'ALL' }}">
    <input type="hidden" name="formato" value="{{ consulta_traer.formato or 'imagen' }}">
    <input type="hidden" name="solo_activos" value="{{ '1' if consulta_traer.solo_activos else '' }}">
    <input type="hidden" name="min_dias" value="{{ consulta_traer.min_dias or '' }}">
    <input type="hidden" name="min_variantes" value="{{ consulta_traer.min_variantes or '' }}">
    <input type="hidden" name="tope" value="{{ tope_traer }}">
    <button type="submit" class="btn-generar btn-sm">Traer y clasificar ≈ US$ {{ '%.2f' | format(precio_traer.total_usd) }}</button>
  </form>
  {% endif %}
</section>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k admin_referentes`
Expected: PASS (existing `test_admin_referentes_importar`/`test_admin_referentes_solo_admin` plus the 4 new tests)

Also run: `venv/bin/python3 -m pytest tests/test_tareas_referentes.py -v`
Expected: PASS (full file — confirms `cliente_gasto` didn't change behavior for any existing, non-global barrido test, since `p.get("cliente") or datos.CLIENTE_CREATV` is a no-op whenever `cliente` is a real, non-empty string)

- [ ] **Step 7: Commit**

```bash
git add dashboard.py templates/admin_referentes.html tareas/referentes.py tests/test_rutas_referentes.py tests/test_tareas_referentes.py
git commit -m "$(cat <<'EOF'
Referentes: «Traer referentes globales» en el panel admin (bloque 6)

Mismo formulario que el de un proyecto (Traer referentes), pero con
cliente=NULL: el barrido queda visible para todos. Reutiliza
referentes.rutas._consulta_desde/_entero y el resto de la mecánica de
estimar/lanzar ya construida en los bloques 4-5, sin duplicar lógica.
El precio se muestra siempre antes de poder lanzar (botón «Traer y
clasificar» solo aparece con precio_traer calculado).

De paso, _fase_trayendo ya no intenta registrar un gasto con cliente=None
(db.gasto.c.cliente es NOT NULL) -- cae en el mismo comodín CLIENTE_CREATV
que ya usa la importación de copycoders.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Totales por fuente, contador de Atria, y barridos globales (todas las fuentes)

**Files:**
- Modify: `templates/admin_referentes.html`
- Test: `tests/test_rutas_referentes.py`

**Interfaces:**
- Consumes: `fuentes_totales`, `atria_llamadas`, `atria_limite`, `barridos_otras_fuentes` — all already passed into the template by Task 1's extended `admin_referentes()` route (no new route/Python code needed in this task, purely template work).

- [ ] **Step 1: Write the failing test**

```python
def test_admin_referentes_muestra_totales_y_cuota_atria(app, monkeypatch):
    from referentes.fuentes import atria as atria_mod
    monkeypatch.setattr(atria_mod, "llamadas_este_mes", lambda: 37)
    monkeypatch.setattr(atria_mod, "limite_mensual", lambda: 1200)
    html = app["c"].get("/admin/referentes").data.decode()
    assert "37" in html and "1200" in html


def test_admin_referentes_lista_barridos_de_otras_fuentes(app):
    from referentes import datos
    bid = datos.crear_barrido(None, "atria", {"modo": "palabra", "palabra": "sandalias"}, 50)
    datos.actualizar_barrido(bid, estado="listo", traidos=12, clasificados=10, usd_real=0.32)
    html = app["c"].get("/admin/referentes").data.decode()
    assert "sandalias" in html and "atria" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k "totales_y_cuota or otras_fuentes"`
Expected: FAIL — the template doesn't render these sections yet.

- [ ] **Step 3: Add the totals/quota/barridos-globales sections to the template**

Insert this new `<section>` right after the "Traer referentes globales" section added in Task 1 (before the "Familias" section):

```html
<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Totales</h2></div>
  <div class="hero-stats">
    {% for f, n in fuentes_totales %}
    <div class="stat"><span class="stat-num">{{ n }}</span><span class="stat-label">{{ fuentes_nombres.get(f, f) }}</span></div>
    {% endfor %}
  </div>
  <p class="vacio">Atria: {{ atria_llamadas }}/{{ atria_limite }} llamadas este mes.</p>
</section>

<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Barridos globales (Atria, Apify)</h2></div>
  {% if not barridos_otras_fuentes %}
  <p class="vacio">Todavía no se ha traído ningún barrido global fuera de copycoders.</p>
  {% else %}
  <div class="admin-scroll"><table class="tabla-admin">
    <tr><th>Fecha</th><th>Fuente</th><th>Consulta</th><th>Estado</th><th>Traídos</th><th>Clasificados</th><th>Costo</th></tr>
    {% for b in barridos_otras_fuentes %}
    <tr>
      <td>{{ b.creado_en }}</td>
      <td>{{ fuentes_nombres.get(b.fuente, b.fuente) }}</td>
      <td>{{ b.consulta.palabra or b.consulta.pagina_id or '' }}</td>
      <td>{{ b.estado }}{% if b.aviso %} · {{ b.aviso }}{% endif %}</td>
      <td>{{ b.traidos }}/{{ b.tope }}</td>
      <td>{{ b.clasificados }}</td>
      <td>{% if b.usd_real %}US$ {{ '%.2f' | format(b.usd_real) }}{% else %}—{% endif %}</td>
    </tr>
    {% endfor %}
  </table></div>
  {% endif %}
</section>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k "admin_referentes"`
Expected: PASS (all admin_referentes tests, Task 1's and Task 2's together)

- [ ] **Step 5: Commit**

```bash
git add templates/admin_referentes.html tests/test_rutas_referentes.py
git commit -m "$(cat <<'EOF'
Referentes: totales por fuente, cuota de Atria y barridos globales en admin

Puramente de plantilla -- Task 1 ya pasa fuentes_totales/atria_llamadas/
atria_limite/barridos_otras_fuentes al contexto. La tabla de barridos
globales excluye copycoders (que ya tiene su propia sección arriba) para
no mostrar el mismo barrido dos veces.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Familias editables

**Files:**
- Modify: `dashboard.py` (add `admin_referentes_familia()`)
- Modify: `templates/admin_referentes.html`
- Test: `tests/test_rutas_referentes.py`

**Interfaces:**
- Consumes: `referentes.datos.familia_actualizar(familia_id, descripcion) -> bool` (already exists, currently unused anywhere in the codebase — confirmed by the plan's research).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_referentes_familia_actualizar(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "vieja descripción")
    c = app["c"]
    r = c.post(f"/admin/referentes/familias/{fid}", data={"descripcion": "Escalera de precios tachados"},
              headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    familia = [f for f in datos.familias() if f["id"] == fid][0]
    assert familia["descripcion"] == "Escalera de precios tachados"


def test_admin_referentes_familia_actualizar_inexistente(app):
    c = app["c"]
    r = c.post("/admin/referentes/familias/999999", data={"descripcion": "x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302   # no revienta con un id que no existe


def test_admin_referentes_familia_actualizar_solo_admin(app):
    from referentes import datos
    fid = datos.familia_asegurar("Comic Strip", "original")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post(f"/admin/referentes/familias/{fid}", data={"descripcion": "hackeado"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302
    familia = [f for f in datos.familias() if f["id"] == fid][0]
    assert familia["descripcion"] == "original"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k admin_referentes_familia`
Expected: FAIL — `/admin/referentes/familias/<id>` doesn't exist yet (404s).

- [ ] **Step 3: Add the route**

Add right after `admin_referentes_traer()` in `dashboard.py`:

```python
@app.route("/admin/referentes/familias/<int:familia_id>", methods=["POST"])
@requiere_admin
def admin_referentes_familia(familia_id):
    if not _mismo_origen():
        abort(403)
    from referentes import datos as ref_datos
    ref_datos.familia_actualizar(familia_id, request.form.get("descripcion") or "")
    return redirect(url_for("admin_referentes"))
```

- [ ] **Step 4: Make the familias table editable in the template**

Find the existing "Familias" `<section>` in `templates/admin_referentes.html` (the last section, with the `<table class="tabla-admin">` listing `f.nombre`/`f.descripcion`/`f.n`/`f.origen`). Replace its table body row with an editable form per row:

```html
<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Familias ({{ familias | length }})</h2></div>
  <div class="admin-scroll"><table class="tabla-admin">
    <tr><th>Familia</th><th>Descripción</th><th>Referentes</th><th>Origen</th><th></th></tr>
    {% for f in familias %}
    <tr>
      <td>{{ f.nombre }}</td>
      <td>
        <form method="post" action="{{ url_for('admin_referentes_familia', familia_id=f.id) }}" class="inline">
          <input type="text" name="descripcion" value="{{ f.descripcion or '' }}" style="width:22rem">
          <button type="submit" class="btn-xs">Guardar</button>
        </form>
      </td>
      <td>{{ f.n }}</td>
      <td>{{ f.origen }}</td>
    </tr>
    {% endfor %}
  </table></div>
</section>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k admin_referentes`
Expected: PASS (all admin_referentes tests from Tasks 1-3)

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/admin_referentes.html tests/test_rutas_referentes.py
git commit -m "$(cat <<'EOF'
Referentes: familias editables desde el panel admin

datos.familia_actualizar ya existía (bloque 1) pero nada la llamaba --
un formulario en línea por fila en la tabla de familias, con su ruta
POST admin-only.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `ATRIA_API_KEY` y `APIFY_TOKEN` en Puesta a punto

**Files:**
- Modify: `dashboard.py` (`SERVICIOS_LLAVES`)
- Test: `tests/test_gastos.py` or wherever `SERVICIOS_LLAVES`/`_estado_llaves` is already tested — check first

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — `_estado_llaves()`/`_llaves_visibles()` (already built, unmodified by this task) automatically pick up the new `SERVICIOS_LLAVES` entry since that function iterates the list generically.

- [ ] **Step 1: Find the existing test file for `SERVICIOS_LLAVES`/Puesta a punto**

Run: `grep -rln "SERVICIOS_LLAVES\|_estado_llaves" tests/` — read whichever file(s) it finds in full before writing a new test, to match the exact fixture/assertion style already used there for an existing entry (e.g. however an existing test checks the `apify` or `anthropic` card's `estado`).

- [ ] **Step 2: Write the failing test**

Adapt to the real test file/style found in Step 1, but the assertion should be equivalent to:

```python
def test_atria_tiene_tarjeta_en_puesta_a_punto(monkeypatch):
    import dashboard
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    tarjetas = dashboard._estado_llaves()
    atria = [t for t in tarjetas if t["id"] == "atria"][0]
    assert atria["estado"] == "configurada"
    assert atria["variables"] == ["ATRIA_API_KEY"]
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    tarjetas = dashboard._estado_llaves()
    atria = [t for t in tarjetas if t["id"] == "atria"][0]
    assert atria["estado"] == "falta"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest <archivo encontrado en el paso 1> -v -k atria_tiene_tarjeta`
Expected: FAIL — no entry with `id == "atria"` in `SERVICIOS_LLAVES` yet, `IndexError` on the empty list comprehension.

- [ ] **Step 4: Add the `atria` entry to `SERVICIOS_LLAVES`**

Find `SERVICIOS_LLAVES` in `dashboard.py` (a tuple of dicts, confirmed by the plan's research to include an `apify` entry with this exact shape). Add a new entry — placement next to the existing `apify` entry keeps related cards together:

```python
{
    "id": "atria",
    "nombre": "Atria (biblioteca de referentes: Ad Library de Meta)",
    "para_que": "Trae anuncios reales de la Ad Library de Meta para la biblioteca de referentes -- la fuente cubre la Unión Europea.",
    "costo": "Incluido en el plan mensual de Atria (1 200 llamadas/mes); no cobra por resultado. El contador de uso está en Referentes (admin).",
    "url": "https://tryatria.com",
    "url_texto": "tryatria.com",
    "variables": ["ATRIA_API_KEY"],
    "nota": "Sin ella la fuente Atria queda apagada en «Traer referentes» (por proyecto y en el panel admin); Apify sigue disponible si tiene su propio token.",
    "opcional": True,
    "pasos": [
        "Crea la cuenta en tryatria.com y elige un plan.",
        "Copia la API key desde el panel de Atria.",
        "Pégala como ATRIA_API_KEY en el .env del servidor y reinicia los dos servicios.",
    ],
},
```

- [ ] **Step 5: Update the existing `apify` entry's description to also mention the Ad Library connector**

Find the existing `apify` entry (confirmed by the plan's research at this exact shape). Change only its `"nombre"` and `"para_que"` values — every other field (`costo`, `url`, `url_texto`, `variables`, `nota`, `opcional`, `pasos`) stays exactly as it is today:

```python
"nombre": "Apify (Nicho: reseñas/comentarios · Referentes: Ad Library)",
"para_que": "Corre los actores de Apify: en Nicho trae reseñas de Amazon o comentarios de TikTok; en la biblioteca de referentes trae anuncios de la Ad Library de Meta (alternativa a Atria, sí cubre Latinoamérica).",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest <archivo encontrado en el paso 1> -v -k atria_tiene_tarjeta`
Expected: PASS

Then run the file's full suite to confirm the `apify` description change didn't break an existing test that asserted its old exact text:

Run: `venv/bin/python3 -m pytest <archivo encontrado en el paso 1> -v`
Expected: PASS — if an existing test asserts the OLD `apify` "nombre"/"para_que" text verbatim, update that assertion to the new text (this is a deliberate, in-scope change, not an accidental break).

- [ ] **Step 7: Commit**

```bash
git add dashboard.py <archivo de test encontrado en el paso 1>
git commit -m "$(cat <<'EOF'
Puesta a punto: tarjeta de ATRIA_API_KEY, aclarar la de Apify

ATRIA_API_KEY no tenía tarjeta en absoluto. La de Apify ya existía
(Nicho) pero no mencionaba que el mismo token también prende la fuente
Apify de la biblioteca de referentes (bloque 5).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `CLAUDE.md` — close out the biblioteca de referentes blocks

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (documentation only).

- [ ] **Step 1: Update the "Biblioteca de referentes" paragraph**

In `CLAUDE.md`, find the sentence ending `"...El panel admin completo con barridos globales (bloque 6) sigue pendiente."` (added by Block 5's own CLAUDE.md task) and replace it with:

```
Bloque 6: panel admin completo (`/admin/referentes`) -- «Traer referentes
globales» (mismo formulario y mecánica que el de un proyecto, pero
`cliente=NULL`: el barrido queda visible para todos), totales por fuente,
contador «Atria: N/1200 llamadas este mes», tabla de familias editable
(`datos.familia_actualizar`, sin usar desde el bloque 1) y las tarjetas de
`ATRIA_API_KEY`/`APIFY_TOKEN` en Puesta a punto. Con esto los seis bloques
del diseño original (spec 2026-09-23 §17) están en `main`.
```

- [ ] **Step 2: Verify the file is still valid**

Run: `python3 -c "print(open('CLAUDE.md').read()[:200])"` — confirms the file still opens and reads without error.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
CLAUDE.md: panel admin completo (bloque 6) -- biblioteca de referentes completa

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:** §8's admin paragraph lists exactly five things — "importar copycoders" (already existed, untouched), "barridos globales (mismo formulario, cliente=NULL)" → Task 1, "totales por fuente" → Task 2, "«Atria: N/1200 llamadas este mes»" → Task 2, "tabla de familias (ver/editar descripción, conteo)" → Task 3 (view already existed, edit added). "En Puesta a punto: ATRIA_API_KEY y APIFY_TOKEN con su badge" → Task 4. Nothing in §8's admin paragraph is left uncovered.

**Placeholder scan:** every step has literal, complete code (route bodies, template HTML, test functions) — no "add validation"/"similar to Task N" placeholders. Task 4's test file path is deliberately left as "found in Step 1" rather than guessed, because the plan's research did not locate the exact existing `SERVICIOS_LLAVES` test file — this is a directed research step with a concrete deliverable (find and read the file), not an unresolved placeholder in the implementation itself.

**Type consistency:** `fuentes_totales` (a list of `(fuente, n)` tuples from `ref_datos.opciones(None)["fuentes"]`, confirmed shape from `referentes/datos.py`'s `_grupo` helper) is produced in Task 1 and consumed identically in Task 2's template loop (`{% for f, n in fuentes_totales %}`). `barridos_otras_fuentes` (a list of barrido dicts, same shape as `datos.barridos()` returns elsewhere in this codebase — confirmed fields `creado_en`/`fuente`/`consulta`/`estado`/`traidos`/`tope`/`clasificados`/`usd_real`/`aviso`) is produced in Task 1 and consumed identically in Task 2's table. `admin_referentes_familia_actualizar` in the Interfaces block was renamed to the shorter `admin_referentes_familia` in Task 3's actual route/template code — using the short name consistently in both places now.

**Correctness issue found and fixed during this self-review (not in the original draft):** the first draft of Task 1 launched a global barrido via `tareas.referentes.encolar_barrer(None, ...)` without accounting for `_fase_trayendo`'s two `gastos.registrar_seguro(p["cliente"], ...)` call sites, which would receive `cliente=None` for such a barrido — `db.gasto.c.cliente` is `nullable=False`, so a real Apify cost on a global barrido would have silently failed to register (`registrar_seguro` never raises; the row would simply never appear in `gasto`). Fixed by adding Task 1 Step 4, substituting `datos.CLIENTE_CREATV` (the same sentinel copycoders' own import already uses for this exact reason) whenever `p["cliente"]` is `None`, with a dedicated regression test. This does not currently affect anything in production (`APIFY_TOKEN` isn't configured yet, so no global Apify barrido can run today), but it would have been a real, silent gap the moment it was.
