# Alertas (rescate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild on today's `main` the «Alertas» tab designed on 2026-09-20 (branch `worktree-alertas`, never merged):
one tab that lists everything a project needs attention for, computed on the fly, dismissable by «huella».

**Architecture:** `alertas.py` (no Flask) computes alerts from read-only sources, each in its own `try`; the only write
is the `alerta_descartada` table (migration 0028). `llaves.py` takes the Puesta a punto key list out of `dashboard.py`
so `alertas.py` never imports `dashboard`. `dashboard.py` adds two POST routes, a context processor with a 60 s cache
per `(cliente, idioma)`, the tab and the sidebar bubble; the Tablero's alert list becomes one line.

**Tech Stack:** Flask 3, SQLAlchemy Core (`db.py`), Alembic, Flask-Babel (`idiomas.py`, `catalogo_i18n.py`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-20-alertas-design.md` — §0–§11 is the original design, **§12 is what changed
when rescuing it; §12 wins where they differ.** The old code is a starting point, not a source of truth:
`git show worktree-alertas:alertas.py` (and `llaves.py`, `templates/_tab_alertas.html`, `tests/test_alertas.py`,
`tests/test_alertas_fuentes.py`, `tests/test_rutas_alertas.py`, `tests/test_llaves.py`).

## Global Constraints

- Every visible text goes through the catalog: Python `gettext`/`ngettext` from `flask_babel` (never `as _`), module
  constants with `idiomas.N_` + `|traducir` in templates, templates `{{ _('…') }}`. At the end of each task that adds
  text: `venv/bin/python3 catalogo_i18n.py actualizar`, translate the new entries in
  `translations/en/LC_MESSAGES/messages.po` (glossary `docs/i18n/glosario.md`), `venv/bin/python3 catalogo_i18n.py
  compilar`. `tests/test_i18n_catalogo.py`, `test_i18n_mensajes.py`, `test_i18n_plantillas.py` must pass.
- Nothing here charges money, enqueues a task, publishes or calls a paid provider. No key value ever leaves
  `llaves.estado` (only `bool(os.environ.get(var))`). Error texts reaching an alert go through
  `cola.recortar(cola.sin_token(texto), 200)`; a failing source reports only the exception class name.
- The venv lives in the main checkout: run tests with
  `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest <files> -q -p no:cacheprovider` from the
  worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/alertas-rescate`.
- Commit at the end of each task with explicit paths (`git add <paths>`), Spanish message, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never `git add -A`, `git stash`, `reset --hard`.
- UI: reuse the «Base visual común» classes at the end of `static/style.css` (`.panel-cabecera`, `.estado-vacio`,
  buttons); nothing may scroll sideways at 375 px (`tests/test_base_visual.py`, `tests/test_movil.py`); no `<script>`
  inside fragments that arrive by fetch.

---

### Task 1: `llaves.py`, WaveSpeed card, Higgsfield optional, `usuarios.por_cliente`

**Files:**
- Create: `llaves.py`, `tests/test_llaves.py`, `tests/test_usuarios_por_cliente.py`
- Modify: `dashboard.py` (`SERVICIOS_LLAVES` ≈:2164, `_estado_llaves` ≈:2357, keep `_llaves_visibles` ≈:2401),
  `usuarios.py`, `tests/test_rutas_configuracion.py` (WaveSpeed card present, Higgsfield optional)

**Interfaces:**
- Produces: `llaves.SERVICIOS` (tuple of dicts, same shape as today's `SERVICIOS_LLAVES` plus the WaveSpeed card),
  `llaves.estado(callback_meli=None) -> list[dict]` (same result as today's `_estado_llaves`: `id, nombre, para_que,
  costo, estado ("configurada"|"parcial"|"falta"), url, url_texto, variables, faltan, nota, opcional, pasos`), and in
  `dashboard.py` the aliases `SERVICIOS_LLAVES = llaves.SERVICIOS`, `_estado_llaves = llaves.estado` (tests and
  templates keep working). `usuarios.por_cliente(cliente) -> list[dict]` with `usuario, correo, correo_verificado` for
  every account with `rol == "cliente"` and `cliente == cliente` (never the password hash).

- [ ] **Step 1: Write the failing tests.** `tests/test_llaves.py`: with `monkeypatch.delenv("WAVESPEED_API_KEY",
  raising=False)` the card `wavespeed` is `falta` with `faltan == ["WAVESPEED_API_KEY"]`; with it set, `configurada`;
  `next(t for t in llaves.estado() if t["id"] == "higgsfield")["opcional"] is True`; `dashboard._estado_llaves is
  llaves.estado`; no card's text contains the value of a set variable (set `ANTHROPIC_API_KEY="sk-prueba-123"` and
  assert `"sk-prueba-123" not in repr(llaves.estado())`). `tests/test_usuarios_por_cliente.py`: write a
  `usuarios.json` in the temp base with one admin, two clients of `acme` (one verified) and one of `otro`; assert
  `por_cliente("acme")` returns the two of acme with their `correo_verificado` and no `hash`/`clave` key.
- [ ] **Step 2: Run them, see them fail** (`ModuleNotFoundError: llaves`, `AttributeError: por_cliente`).
- [ ] **Step 3: Implement.** Move `SERVICIOS_LLAVES`, the Meta agencia note/steps it uses and `_estado_llaves` verbatim
  to `llaves.py` (`SERVICIOS`, `estado`), leave the aliases in `dashboard.py`. Add after Anthropic the card
  `{"id": "wavespeed", "nombre": N_("WaveSpeed (videos e imágenes de Crear)"), "variables": ["WAVESPEED_API_KEY"],
  "costo": N_("Por segundo de video y por imagen: el precio se muestra antes de cada generación."),
  "url": "https://wavespeed.ai/", "nota": N_("Sin ella no se genera ningún video ni imagen en Crear ni en Sprints."),
  "pasos": [...]}` (cuenta, saldo, API Keys, pegar en el .env, reiniciar los dos servicios) — copy the shape of the
  existing cards, including how their texts are marked for the catalog. Higgsfield gets `"opcional": True` and the
  note «Solo la usa el flujo viejo «Nueva idea»; Crear no la necesita.». `usuarios.por_cliente` iterates
  `usuarios.cargar()`.
- [ ] **Step 4: Run** `tests/test_llaves.py tests/test_usuarios_por_cliente.py tests/test_rutas_configuracion.py` → pass;
  catalog update/translate/compile; `tests/test_i18n_catalogo.py` → pass.
- [ ] **Step 5: Commit** «Alertas (1/6): llaves.py con la tarjeta de WaveSpeed, Higgsfield opcional y
  usuarios.por_cliente».

### Task 2: table `alerta_descartada` (migration 0028) and the core of `alertas.py`

**Files:**
- Create: `migrations/versions/0028_alerta_descartada.py`, `alertas.py`, `tests/test_alertas.py`,
  `tests/test_migracion_0028.py`
- Modify: `db.py` (declare `alerta_descartada` next to `kv`)

**Interfaces:**
- Produces (exact names later tasks use):
  `alertas.NIVELES = ("bloquea", "atencion", "info")`, `alertas.GRUPOS = ("puesta_a_punto", "faltantes",
  "decision", "fallos")`, `alertas.NOMBRES_GRUPO`, `alertas.NOMBRES_NIVEL`, `alertas.NOMBRES_TAB` (values `N_(...)`),
  `alertas.FUENTES` (list of `(nombre, funcion(cliente, ahora_iso) -> list[dict])`),
  `alertas.huella(*partes) -> str` (sha256 hex of `"|".join(map(str, partes))`),
  `alertas._alerta(clave, huella_, nivel, grupo, titulo, detalle, tab, ancla=None, url=None, entidad=None,
  solo_admin=False) -> dict`, `alertas.calcular(cliente, ahora_iso=None) -> list[dict]` (all, ordered by
  `GRUPOS` then `NIVELES` then source order; a failing source → one `revision:<fuente>` alert, `info`,
  `puesta_a_punto`, `solo_admin=True`, detail = only the exception class name),
  `alertas.visibles(cliente, ahora_iso=None, rol="cliente", calculadas=None) -> {"visibles", "descartadas",
  "resumen"}` (filters `solo_admin` unless `rol == "admin"`; `calculadas` lets the caller pass a cached `calcular`
  result), `alertas.resumen(lista) -> {"n", "bloquea", "atencion", "info"}`,
  `alertas.descartar(cliente, clave, huella_)`, `alertas.restaurar(cliente, clave)`,
  `alertas.CLAVE_VALIDA` (regex `^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$`), `alertas.HUELLA_VALIDA` (`^[0-9a-f]{64}$`).

- [ ] **Step 1: Failing tests** in `tests/test_alertas.py` with `FUENTES` replaced by fakes
  (`monkeypatch.setattr(alertas, "FUENTES", [...])`): order by group and level; a source raising
  `KeyError("tok_secreto")` yields `revision:<nombre>` whose detail is `KeyError` and does not contain
  `tok_secreto`, and the other sources still appear; `descartar` + `visibles` hides the same clave+huella and shows
  it again with another huella; `restaurar` shows it again; orphan dismissals are pruned, but not in a pass that has a
  `revision:*` alert; `solo_admin` alerts are absent for `rol="cliente"` and counted for `rol="admin"`;
  `huella()` is deterministic and `huella()` (no parts) is a constant. `tests/test_migracion_0028.py`: after
  `alembic upgrade head` on a temp DB the table exists with PK `(cliente, clave)`, and `downgrade -1` drops it (copy
  the pattern of an existing `tests/test_migracion_*.py`).
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement** from `git show worktree-alertas:alertas.py` (core: `huella`, `_alerta`, `_minutos`,
  `_limpio`, `calcular`, `resumen`, `_descartes`, `descartar`, `restaurar`, `_borrar_descartes`, `visibles`) plus
  `solo_admin` and `calculadas`. Upsert with `sqlalchemy.dialects.sqlite.insert(...).on_conflict_do_update`. Migration
  0028: `down_revision` = the current head (`ls migrations/versions | sort | tail -1`); columns `cliente String(80)`
  PK, `clave String(200)` PK, `huella String(64)` not null, `descartada_en String(19)` not null.
- [ ] **Step 4: Run** the two test files → pass.
- [ ] **Step 5: Commit** «Alertas (2/6): tabla alerta_descartada (0028) y el núcleo de alertas.py».

### Task 3: sources «puesta a punto» and «faltantes»

**Files:**
- Modify: `alertas.py`
- Create: `tests/test_alertas_fuentes.py`

**Interfaces:**
- Consumes: `llaves.estado()`, `usuarios.por_cliente(cliente)`, `saldo.vigente("wavespeed")`, `db.kv`, `db.tarea`,
  `marca.guia_efectiva(cliente)`, `catalogo_productos.listar_productos(cliente)`,
  `catalogo_productos.listar(cliente, "personaje")`, `tiendas.listar(cliente)`, `proyectos.correo_notificaciones(cliente)`,
  `organico.disponibles(cliente)`, `bool(os.environ.get("SMTP_HOST"))`, `tablero.alertas(cliente, ahora_iso)`.
- Produces: sources `llaves`, `cuentas`, `worker`, `saldo`, `tablero`, `proyecto` in `FUENTES` (in this order, before
  the Task 4 sources).

Rules (spec §2.1, §2.2 and §12): `llave:<id>` for every card not `configurada` except Meta, `bloquea` (`info` if
`opcional`), `solo_admin=True`, ancla `llave-<id>`; `cuenta:correo:<usuario>` `bloquea`, ancla `config-cuenta`;
`worker:parado` `solo_admin=True` from the most recent of `kv` rows whose `clave` starts with `ultimo_` and
`MAX(tarea.iniciada_en)` (one query each), threshold 30 min; saldo per §12.4 as TWO alerts: `saldo:wavespeed`
(`solo_admin=False`, neutral title «La generación de videos e imágenes está en pausa», detail without the recharge
link, huella = `desde`) and `saldo:wavespeed_recarga` (`solo_admin=True`, «WaveSpeed se quedó sin saldo», detail with
since when and the recharge URL from `vigente()["recarga"]`, same huella);
`tablero:<tipo>:<exp or ->` mapping alta/media/baja → bloquea/atencion/info and the groups of §2; `sin_metricas`
with empty huella; faltantes per §2.2 (`proyecto:logo` checks `clientes/<c>/logos/` for image files directly —
do not import `dashboard`; `proyecto:producto` uses `listar_productos` and ignores archived products like the pickers
do: `catalogo_productos.sin_archivados(entradas, tiendas.activos_archivados(cliente), set())`).

- [ ] **Step 1: Failing tests** (one per rule, with `monkeypatch` on each dependency; a temp `BASE_DIR` for logos;
  `db.kv`/`db.tarea` rows inserted with `db.conectar()`): key missing/partial/optional/configured; Meta card ignored;
  account without email / unverified / verified; worker fresh (kv 5 min ago), stale (2 h), never, and fresh by
  `tarea.iniciada_en`; saldo present/absent and the admin-only recharge alert; tablero with the three severities and
  `sin_metricas` with `huella() == alertas.huella()`; each faltante present and resolved.
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement** the six sources, adapting `git show worktree-alertas:alertas.py`; every title/detail with
  `gettext` (plurals with `ngettext`; Babel 2.18 does not extract a `gettext` nested inside `ngettext`'s arguments —
  compute it into a local first).
- [ ] **Step 4: Run** `tests/test_alertas_fuentes.py tests/test_alertas.py` → pass; catalog update/translate/compile.
- [ ] **Step 5: Commit** «Alertas (3/6): fuentes de puesta a punto, saldo, tablero y faltantes del proyecto».

### Task 4: sources «decisión» and «fallos» (Crear, Sprints, Nicho, orgánico)

**Files:**
- Modify: `alertas.py`, `tests/test_alertas_fuentes.py`

**Interfaces:**
- Consumes: `db.concepto`, `db.pieza` (Crear sessions: `concepto.legado_id` = cf_id, state in
  `concepto.extra["estado_legado"]` or derived from `pieza.estado` as `creative_flow._PIEZA_A_ESTADO` does — read
  `creative_flow.py:22-60` first), `sprints.revision.resumen(cliente, sprint_id)`, `db.campana_pieza`, `db.referencia`,
  `nicho.datos.resumen_avatares(cliente)`, `db.estudio`, `db.publicacion`.
- Produces: sources `crear`, `organico`, `sprints`, `nicho` appended to `FUENTES` after Task 3's.

Rules (spec §2.3, §2.4 and §12.7–8): `crear:prompt_listo` (one alert with the count, sessions older than 60 min,
huella = sorted ids, ancla `cf-<first id>`) and `crear:error:<cf_id>` (last 30 days, huella = clean error) from ONE
bounded query — never `creative_flow.cargar`; `organico:error:<pub_id>` (last 30 days); `sprint:ideas:<sid>`,
`sprint:revision:<sid>`, `sprint:fallos:<sid>`, `sprint:referencias:<sid>` with `url` = `url_for` of the sprint page
(compute the path without Flask: build `/cliente/<c>/sprints/<sid>` the same way `sprints/rutas.py` defines the
route); `nicho:avatares` → `/cliente/<c>/nicho/avatares`; `nicho:error:<eid>` → `/cliente/<c>/nicho/<eid>`.

- [ ] **Step 1: Failing tests** with real rows in the temp DB (create sessions with `creative_flow.crear` /
  `actualizar`, sprints with `sprints.datos`, studies with `nicho.datos`, a `publicacion` row): prompt listo recent
  (no alert) vs 2 h old (alert); error 40 days old excluded; sprint with pending review, failed piece, QA `falla`,
  reference in error; study with new avatars and with an interrupted investigation; organic publication in error.
  Plus a query-count test: `calcular` for a project with 3 sessions and with 30 sessions runs the same number of SQL
  statements (count with an `sqlalchemy.event.listen(db.engine(), "before_cursor_execute", ...)` like
  `tests/test_perf_pagina_proyecto.py` does).
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement** the four sources.
- [ ] **Step 4: Run** → pass; catalog update/translate/compile.
- [ ] **Step 5: Commit** «Alertas (4/6): fuentes de decisión y de fallos de Crear, Sprints, Nicho y orgánico».

### Task 5: routes, context processor, the tab, the sidebar bubble and the Tablero line

**Files:**
- Modify: `dashboard.py` (routes, context processor, cache, `_calcular_tablero` without `alertas`),
  `templates/_sidebar.html`, `templates/cliente.html`, `templates/_tab_tablero.html`, `static/style.css`
  (block «Alertas» at the end), the Crear card macro in `templates/_crear_tarjetas.html` (`id="cf-{{ item.id }}"` on
  the card if it is not there), `templates/_seccion_marca.html` (`id="config-marca"`), the logos heading in
  `templates/_tab_settings.html` (`id="config-logos"`)
- Create: `templates/_tab_alertas.html`, `tests/test_rutas_alertas.py`
- Modify tests: `tests/test_rutas_tablero.py` (the section is now one line; `tb.alertas` is gone)

**Interfaces:**
- Consumes: Task 2's `alertas.calcular/visibles/descartar/restaurar/CLAVE_VALIDA/HUELLA_VALIDA/NOMBRES_*`.
- Produces: `dashboard.invalidar_alertas(cliente=None)`, context variable `alertas_ctx` = `alertas.visibles(...)` for
  the current user's role, `ALERTAS_TTL_S = 60`.

Rules (spec §5–§7, §12): `POST /cliente/<cliente>/alertas/descartar` (form `clave`, `huella`) and
`/alertas/restaurar` (form `clave`), 400 when the regexes fail, `_guard_por_cliente` applies as for every
`<cliente>` route, flash «Alerta descartada» / «Alerta restaurada», redirect to `ver_cliente` with
`_anchor="alertas"`, invalidate the cache. Context processor like `_chip_gasto_sidebar`: skip without `cliente`, for
`_quiere_json()` and for the public landing; cache `calcular()` per `(cliente, idiomas.activo())` for 60 s with a
lock and filter by `session.get("rol")` on read; `invalidar_tablero` also calls `invalidar_alertas`; on failure `{}`
and `print("[aviso] Alertas de <c>: <NombreError>")`. Sidebar item `data-tab="alertas"` right after Tablero with a
bell icon and `<span class="sidebar-burbuja bloquea|atencion">N</span>` when `n > 0`. `_tab_alertas.html`: header
with the summary or «Todo en orden» (`.estado-vacio`), one section per group, each alert as
`<li class="alerta alerta-{{ nivel }}">` with level chip, title, detail, «Ir a {pestaña} →» (`data-ir-tab` +
`data-ancla`, or `href=url`) and a POST «Descartar»; a `<details>` «Descartadas (N)» with «Restaurar». The navigation
script (`data-ir-tab` + optional `data-ancla` → activate tab then `scrollIntoView`, and for `settings` call
`window.irAConfig(ancla)`) lives once in `cliente.html`.

- [ ] **Step 1: Failing tests** in `tests/test_rutas_alertas.py` (admin and client test clients like
  `tests/test_rutas_final_edition.py::_cliente_admin`): the tab paints the groups, the summary and the empty state; a
  client does not see `llave:*`; POST descartar → 302 to `#alertas`, flash, the alert disappears, cache invalidated;
  POST restaurar; bad clave/huella → 400; a cross-site POST (`Sec-Fetch-Site: cross-site`) → refused; the bubble is
  red with a `bloquea`, amber otherwise, absent at 0, also on a Sprints page; the context processor does not run for a
  JSON request; the Tablero shows the one-line summary. Then run `tests/test_perf_pagina_proyecto.py` (must stay
  green), `tests/test_base_visual.py`, `tests/test_movil.py`, `tests/test_i18n_plantillas.py`.
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement**, adapting `git show worktree-alertas:templates/_tab_alertas.html` and the old routes.
- [ ] **Step 4: Run** the test files above plus `tests/test_rutas_tablero.py tests/test_rutas_configuracion.py` → pass;
  catalog update/translate/compile; `tests/test_i18n_fugas.py tests/test_i18n_app_entera.py` → pass.
- [ ] **Step 5: Commit** «Alertas (5/6): pestaña, burbuja del sidebar, rutas de descartar y la línea del Tablero».

### Task 6: documentation and full suite

**Files:**
- Create: `.claude/skills/alertas/SKILL.md` (frontmatter `name: alertas`, quoted `description` that says when to load
  it: «… Cargar antes de agregar una fuente de alertas, tocar alertas.py, llaves.py, _tab_alertas.html o la burbuja
  del sidebar.»; body: what an alert is, the sources, `solo_admin`, cache, dismissals by huella, and the rule «se
  calcula al vuelo, solo se guardan los descartes»)
- Modify: `CLAUDE.md` (one row in «Qué skill cargar»), `.claude/skills/ui/SKILL.md` and
  `.claude/skills/experimentos/SKILL.md` (one line each: the Tablero shows a one-line summary and links to Alertas),
  `docs/pendientes.md` (PND-102 and PND-075 to «Cerrados» with evidence), `templates/mapa_codigo.html` (row for
  `alertas.py` and `llaves.py`).

- [ ] **Step 1:** Write the docs.
- [ ] **Step 2:** Run `tests/test_guia_agentes.py` → pass, then the full suite
  `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider` → all green.
- [ ] **Step 3: Commit** «Alertas (6/6): skill, CLAUDE.md, pendientes y mapa».
