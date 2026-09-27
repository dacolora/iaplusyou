# Sprints como tablero con panel de campaña — Implementation Plan (entrega 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sprint wizard and the loose per-campaign pages with a board: a short «+ Nuevo sprint» form, a sprint page with one card per campaign, and a side panel that edits a campaign field by field (persona, producto, etapa, consciencia, dolor, familias, mercado, marcas, piezas) and picks its referentes from the library.

**Architecture:** Migration 0021 adds market/brands/moment to `sprint` and focus fields to `campana`, and drops the persona+producto+temporada uniqueness. `sprints/datos.py` stays the only writer and validates every new field; `sprints/tablero.py` (new, pure) computes what cards and panel show; `referentes/sugerir.py` gains a campaign-aware free suggester that loosens filters in a fixed order. Routes in `sprints/rutas.py` serve the board, the panel and the suggestions as fetch fragments and save one field per JSON POST; all JS lives in `sprint_detalle.html` with delegated listeners (scripts inside fetched fragments never run).

**Tech Stack:** Flask Blueprint + Jinja2, SQLAlchemy Core on SQLite + Alembic (batch mode), pytest, vanilla JS, `static/style.css`.

**Spec:** `docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`

## Global Constraints

- Work in the worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/base-visual`, branch `sprints-tablero`. Never `cd` to the main checkout. Tests: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider <paths>` run from the worktree.
- `sprints/datos.py` is the only writer of `sprint`/`campana`; routes validate shape and delegate.
- Idiomas: exactly `es, en, pt, fr, it, de` (the same list as «Traer referentes»). País: ISO 2 uppercase letters. Consciencia: keys of `doctrina.CONSCIENCIAS`. Etapa: `sprints.datos.FUNNELS` (`tof|mof|bof`). Familias: names that exist in `referente_familia`.
- Campaign `pais`/`idioma`/`marcas` NULL (or empty) = inherits from the sprint.
- Repeating persona+producto in a sprint is allowed; identical campaigns (persona, producto, etapa, consciencia, familias) only get a soft warning.
- The three generic personas (Melissa, Marijke, Sophia) are never inserted again; existing rows are never deleted.
- Opening the panel and the free suggestions never spend money; «Sugerir con IA» and «Traer nuevos de Meta» show the price before the click and nothing launches on its own.
- UI copy in Spanish, informal «tú». Colors only through `:root` variables (`var(--…)`), except `#fff` text on `var(--accent-grad)` exactly like `.btn-generar` and the translucent backdrop `rgba(10, 10, 25, .35)` like the other modal backdrops; nothing may scroll the page sideways at 375 px.
- Scripts inside fetched fragments do not run: every listener for the panel lives in `sprint_detalle.html`, delegated on `#tablero-panel`.
- Commit after each task with a Spanish message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

- Create `migrations/versions/0021_sprints_tablero.py` — new columns, drop `uq_campana_combinacion`.
- Modify `db.py` — `sprint` and `campana` tables mirror 0021.
- Modify `sprints/datos.py` — validation of new fields, `normalizar_marcas`, `consciencia_de_persona`, `efectivos`/`efectivos_de`, `campanas_identicas`; remove generic personas and `CampanaDuplicada`.
- Create `sprints/tablero.py` — pure helpers: `siguiente_paso`, `sugerencias_dolor`, `mes_siguiente`, `resumen`, `linea_sprint`, `marcas_texto`.
- Modify `referentes/datos.py` — `familias_frecuentes`.
- Modify `referentes/sugerir.py` — `candidatos(familia=)`, `preferencia`, `sugerir_campana`, `candidatos_aflojando`, `sugerir_ia(enfoque_texto=)`.
- Modify `tareas/sprints.py` — `referentes_sugerir_ia` uses the campaign focus.
- Modify `sprints/ideas.py` — prompt gets enfoque, mercado, marcas and momento (or old temporada).
- Modify `sprints/rutas.py` — short create, board, panel, suggestions, per-field saves, JSON variants; remove `-ajax` routes.
- Modify `templates/_tab_sprints.html` — short form, no wizard.
- Rewrite `templates/sprint_detalle.html` — the board (+ all board/panel JS).
- Create `templates/_sprint_tarjeta.html`, `templates/_sprint_panel.html`, `templates/_sprint_sugeridos.html`; add macro `sugerido` to `templates/_sprint_macros.html`.
- Modify `templates/_tab_referentes.html` — forward `idioma`, `modo`, `pagina_id` from the hash to «Traer referentes».
- Delete `templates/_sprint_referencias_ajax.html`, `templates/_sprint_ideas_ajax.html`, `templates/_sprint_revision_ajax.html`.
- Modify `static/style.css` — block «Tablero de Sprints (2026-09-26)» at the end.
- Tests: create `tests/test_sprints_tablero_migracion.py`, `tests/test_sprints_tablero_datos.py`, `tests/test_sprints_tablero.py`, `tests/test_sprints_tablero_rutas.py`; modify `tests/test_sprints_db.py`, `tests/test_sprints_datos.py`, `tests/test_sprints_temporada_opcional.py`, `tests/test_rutas_sprints.py`, `tests/test_referentes_sugerir.py`, `tests/test_referentes_datos.py`, `tests/test_tareas_sprints.py`, `tests/test_sprints_ideas.py`.
- Modify `CLAUDE.md` (Sprints paragraph).

---

### Task 1: Migración 0021 y tablas

**Files:**
- Create: `migrations/versions/0021_sprints_tablero.py`
- Modify: `db.py` (tables `sprint` ~line 512 and `campana` ~line 526)
- Create: `tests/test_sprints_tablero_migracion.py`
- Modify: `tests/test_sprints_db.py` (`test_campana_unica_por_combinacion`, `test_migracion_0006_crea_las_tablas`), `tests/test_sprints_temporada_opcional.py` (`test_migracion_deja_la_temporada_opcional`)

**Interfaces:**
- Produces: columns `sprint.pais String(2)`, `sprint.idioma String(5)`, `sprint.marcas JSON`, `sprint.momento JSON`, `campana.consciencia String(24)`, `campana.dolor Text`, `campana.familias JSON`, `campana.pais String(2)`, `campana.idioma String(5)`, `campana.marcas JSON`; no unique constraint on `campana`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sprints_tablero_migracion.py`:

```python
"""Migración 0021 (tablero de Sprints, spec 2026-09-26): mercado, marcas y
momento en el sprint; enfoque en la campaña; sin la unicidad persona +
producto + temporada."""
import os

import sqlalchemy as sa


def _config():
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Config(os.path.join(raiz, "alembic.ini"))


def test_migracion_0021_agrega_columnas_y_quita_la_unicidad(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "head")
    insp = sa.inspect(db.engine())
    assert {"pais", "idioma", "marcas", "momento"} <= {c["name"] for c in insp.get_columns("sprint")}
    assert {"consciencia", "dolor", "familias", "pais", "idioma", "marcas"} <= {c["name"] for c in insp.get_columns("campana")}
    assert "uq_campana_combinacion" not in {u["name"] for u in insp.get_unique_constraints("campana")}
    assert {"sprint", "persona", "temporada", "producto"} <= {f["referred_table"] for f in insp.get_foreign_keys("campana")}
    db._reset_para_tests()


def test_migracion_0021_conserva_las_campanas_existentes(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "0020")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO persona (cliente, creado_en, actualizado_en, nombre, origen, archivada) "
                            "VALUES ('acme', 'x', 'x', 'Premium', 'manual', 0)"))
        con.execute(sa.text("INSERT INTO sprint (cliente, creado_en, actualizado_en, nombre, inicio, fin, estado) "
                            "VALUES ('acme', 'x', 'x', 'Octubre', '2026-10-01', '2026-10-31', 'planeando')"))
        con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, catalogo_id, "
                            "n_videos, n_imagenes, estado) VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada')"))
    command.upgrade(_config(), "head")
    with db.engine().begin() as con:
        fila = con.execute(sa.text("SELECT catalogo_id, n_videos, consciencia, familias, pais FROM campana")).one()
        # La misma combinación entra otra vez: ya no hay UNIQUE.
        con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, catalogo_id, "
                            "n_videos, n_imagenes, estado) VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada')"))
    assert tuple(fila) == ("espejo_led", 2, None, None, None)
    db._reset_para_tests()
```

In `tests/test_sprints_db.py`, replace the whole `test_campana_unica_por_combinacion` with:

```python
def test_campana_admite_la_misma_combinacion(base_temporal):
    """Desde 0021 una persona y un producto pueden tener varias campañas en el
    mismo sprint (TOF, MOF y BOF, o dos TOF con distinto formato)."""
    db = base_temporal
    pid, tid, sid = _sprint_basico(db)
    ahora = db.ahora()
    fila = dict(cliente="acme", creado_en=ahora, actualizado_en=ahora, sprint_id=sid, persona_id=pid,
                catalogo_id="espejo_led", temporada_id=tid, n_videos=10, n_imagenes=5, estado="planeada")
    with db.conectar() as con:
        con.execute(db.campana.insert().values(**fila))
        con.execute(db.campana.insert().values(**fila))
        assert con.execute(sa.select(sa.func.count()).select_from(db.campana)).scalar() == 2
```

In `test_migracion_0006_crea_las_tablas` replace `assert "uq_campana_combinacion" in indices` with:

```python
    assert "uq_campana_combinacion" not in indices          # quitada en 0021
```

In `tests/test_sprints_temporada_opcional.py::test_migracion_deja_la_temporada_opcional` replace the two lines under the comment `# Recrear la tabla (batch) …` with:

```python
    # Recrear la tabla (batch) no puede perder las llaves foráneas; la unicidad se quitó en 0021.
    assert "uq_campana_combinacion" not in {u["name"] for u in insp.get_unique_constraints("campana")}
    assert {"sprint", "persona", "temporada"} <= {f["referred_table"] for f in insp.get_foreign_keys("campana")}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_migracion.py tests/test_sprints_db.py tests/test_sprints_temporada_opcional.py`
Expected: FAIL — columns missing, `uq_campana_combinacion` still present, duplicate insert raises `IntegrityError`.

- [ ] **Step 3: Write the migration**

Create `migrations/versions/0021_sprints_tablero.py`:

```python
"""sprints: tablero — mercado, marcas y momento en el sprint; enfoque en la campaña

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-26 00:00:00.000000

Spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md. El sprint
guarda país, idioma, marcas a imitar y el «momento del mes»; la campaña guarda
consciencia, dolor, familias de formato y, solo si cambian, su propio país,
idioma y marcas (NULL = hereda del sprint). Se quita uq_campana_combinacion:
una persona y un producto pueden tener TOF, MOF y BOF en el mismo sprint.
El downgrade vuelve a crear la unicidad y falla si ya hay campañas repetidas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sprint') as t:
        t.add_column(sa.Column('pais', sa.String(2), nullable=True))
        t.add_column(sa.Column('idioma', sa.String(5), nullable=True))
        t.add_column(sa.Column('marcas', sa.JSON(), nullable=True))
        t.add_column(sa.Column('momento', sa.JSON(), nullable=True))
    with op.batch_alter_table('campana') as t:
        t.add_column(sa.Column('consciencia', sa.String(24), nullable=True))
        t.add_column(sa.Column('dolor', sa.Text(), nullable=True))
        t.add_column(sa.Column('familias', sa.JSON(), nullable=True))
        t.add_column(sa.Column('pais', sa.String(2), nullable=True))
        t.add_column(sa.Column('idioma', sa.String(5), nullable=True))
        t.add_column(sa.Column('marcas', sa.JSON(), nullable=True))
        t.drop_constraint('uq_campana_combinacion', type_='unique')


def downgrade() -> None:
    with op.batch_alter_table('campana') as t:
        t.create_unique_constraint('uq_campana_combinacion', ['sprint_id', 'persona_id', 'catalogo_id', 'temporada_id'])
        for columna in ('marcas', 'idioma', 'pais', 'familias', 'dolor', 'consciencia'):
            t.drop_column(columna)
    with op.batch_alter_table('sprint') as t:
        for columna in ('momento', 'marcas', 'idioma', 'pais'):
            t.drop_column(columna)
```

- [ ] **Step 4: Mirror it in `db.py`**

In the `sprint` table, after `Column("extra", JSON, default=dict), …`, add:

```python
    Column("pais", String(2)),                                          # mercado del sprint (0021)
    Column("idioma", String(5)),
    Column("marcas", JSON),                                             # [{nombre, pagina_id?}] a imitar
    Column("momento", JSON),                                            # {clave?, nombre, contexto?, inicio?, fin?, mood_visual?}
```

In the `campana` table, after `Column("funnel", String(3), default="tof"), …`, add the six columns and DELETE the line `sa.UniqueConstraint("sprint_id", "persona_id", "catalogo_id", "temporada_id", name="uq_campana_combinacion"),`:

```python
    Column("consciencia", String(24)),                                  # clave de doctrina.CONSCIENCIAS (0021)
    Column("dolor", Text),
    Column("familias", JSON),                                           # nombres de referente_familia
    Column("pais", String(2)),                                          # NULL = hereda del sprint
    Column("idioma", String(5)),
    Column("marcas", JSON),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_migracion.py tests/test_sprints_db.py tests/test_sprints_temporada_opcional.py`
Expected: PASS (`sprints.datos` still refuses repeated campaigns on its own until Task 2).

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0021_sprints_tablero.py db.py tests/test_sprints_tablero_migracion.py tests/test_sprints_db.py tests/test_sprints_temporada_opcional.py
git commit -m "Sprints tablero: migración 0021 (mercado, marcas y momento; enfoque de la campaña; sin unicidad)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `sprints.datos` — campos nuevos, herencia y campañas repetidas

**Files:**
- Modify: `sprints/datos.py`
- Modify: `sprints/rutas.py` (remove the two `datos.asegurar_personajes_predeterminados(cliente)` calls in `contexto` and `ver`; remove the duplicate check in `_validar_campanas`)
- Create: `tests/test_sprints_tablero_datos.py`
- Modify: `tests/test_sprints_datos.py` (`test_campana_unicidad_y_cantidades`), `tests/test_sprints_temporada_opcional.py` (`test_campana_sin_temporada_no_se_repite`), `tests/test_rutas_sprints.py` (`test_contexto_trae_lo_que_usa_la_pestana`, `test_detalle_progreso_listo_y_campanas`, `test_crear_sprint_rechaza_duplicados_y_productos_ajenos`)

**Interfaces:**
- Consumes: Task 1 columns.
- Produces (all in `sprints.datos`):
  - constants `IDIOMAS = ("es","en","pt","fr","it","de")`, `IDIOMAS_NOMBRE: dict[str,str]`, `MAX_MARCAS = 10`, `MAX_FAMILIAS = 8`, `LARGO_DOLOR = 300`.
  - `normalizar_marcas(v) -> list[dict]` (`{"nombre"}` or `{"nombre","pagina_id"}`), raises `ErrorDatos`.
  - `consciencia_de_persona(persona: dict|None) -> str|None` (key of `doctrina.CONSCIENCIAS`).
  - `crear_sprint(cliente, nombre, inicio, fin, destinos=None, referencias_objetivo_defecto=5, notas="", pais=None, idioma="es", marcas=None, momento=None) -> int`; `momento` is `None`, a string (own text) or a dict `{clave?, nombre, contexto?, inicio?, fin?, mood_visual?}`.
  - `actualizar_sprint(..., nombre|pais|idioma|marcas|momento=...)` validates them.
  - `agregar_campana(cliente, sprint_id, persona_id, catalogo_id, temporada_id=None, n_videos=5, n_imagenes=5, referencias_objetivo=None, funnel="tof", consciencia=None, dolor="", familias=None) -> int` — never raises for repeated combinations; `consciencia=None` precarga from the persona.
  - `actualizar_campana(cliente, cid, **campos)` accepts `persona_id, catalogo_id, funnel, consciencia, dolor, familias, pais, idioma, marcas` besides the old ones.
  - `efectivos(sprint: dict, campana: dict) -> {"pais","idioma","marcas","momento","hereda": {"pais","idioma","marcas"}}`; `efectivos_de(cliente, campana) -> same`.
  - `campanas_identicas(cliente, campana_id) -> list[int]` (1-based numbers of other identical campaigns).
  - Every campaign dict inside `sprint(...)["campanas"]` / `sprints(...)` carries `"efectivos"`.
  - Removed: `CampanaDuplicada`, `PERSONAJES_PREDETERMINADOS`, `asegurar_personajes_predeterminados`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sprints_tablero_datos.py`:

```python
"""sprints.datos para el tablero (spec 2026-09-26): mercado, marcas y momento
del sprint; enfoque de la campaña; herencia sprint → campaña; campañas
repetidas permitidas con aviso."""
import pytest


def _persona(datos, **kw):
    return datos.crear_persona("acme", "Premium", resumen="Busca calidad", **kw)


def _familia(nombre="Antes y después"):
    from referentes import datos as rdatos
    rdatos.familia_asegurar(nombre, "Muestra el cambio")
    return nombre


def test_crear_sprint_guarda_mercado_marcas_y_momento(base_temporal):
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", pais="mx", idioma="es",
                             marcas="Crocs\nSkechers https://www.facebook.com/ads/library/?view_all_page_id=123456",
                             momento={"clave": "dia_madre", "nombre": "Día de la madre", "contexto": "regalos",
                                      "inicio": "2026-05-01", "fin": "2026-05-10",
                                      "mood_visual": {"paleta": ["#fff", "rojo"]}})
    s = datos.sprint("acme", sid)
    assert s["pais"] == "MX" and s["idioma"] == "es"
    assert s["marcas"] == [{"nombre": "Crocs"}, {"nombre": "Skechers", "pagina_id": "123456"}]
    assert s["momento"]["nombre"] == "Día de la madre" and s["momento"]["clave"] == "dia_madre"
    assert s["momento"]["mood_visual"]["paleta"] == ["#fff"]


def test_crear_sprint_sin_mercado_queda_en_espanol(base_temporal):
    from sprints import datos
    s = datos.sprint("acme", datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31"))
    assert s["pais"] is None and s["idioma"] == "es" and s["marcas"] == [] and s["momento"] is None


@pytest.mark.parametrize("campos", [dict(pais="Colombia"), dict(idioma="xx"), dict(marcas=5),
                                    dict(marcas=[{"nombre": "X", "pagina_id": "abc"}]),
                                    dict(momento={"nombre": "X", "inicio": "mañana"})])
def test_crear_sprint_valida_los_campos_nuevos(base_temporal, campos):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", **campos)
    assert datos.sprints("acme") == []


def test_normalizar_marcas_acepta_texto_links_e_ids(base_temporal):
    from sprints import datos
    texto = ("Crocs, crocs\nhttps://www.facebook.com/ads/library/?active_status=all&view_all_page_id=987654\n"
             "Hoka 1234567")
    assert datos.normalizar_marcas(texto) == [{"nombre": "Crocs"},
                                             {"nombre": "Página 987654", "pagina_id": "987654"},
                                             {"nombre": "Hoka", "pagina_id": "1234567"}]
    assert datos.normalizar_marcas("") == [] and datos.normalizar_marcas(None) == []
    with pytest.raises(datos.ErrorDatos):
        datos.normalizar_marcas(",".join(f"Marca{i}" for i in range(datos.MAX_MARCAS + 1)))


def test_actualizar_sprint_valida_nombre_y_campos_nuevos(base_temporal):
    from sprints import datos
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    datos.actualizar_sprint("acme", sid, pais="co", idioma="en", marcas="Nike", momento="Hot Sale")
    s = datos.sprint("acme", sid)
    assert (s["pais"], s["idioma"], s["marcas"], s["momento"]) == ("CO", "en", [{"nombre": "Nike"}], {"nombre": "Hot Sale"})
    datos.actualizar_sprint("acme", sid, momento="")
    assert datos.sprint("acme", sid)["momento"] is None
    for malo in (dict(nombre="  "), dict(pais="COL"), dict(idioma="klingon")):
        with pytest.raises(datos.ErrorDatos):
            datos.actualizar_sprint("acme", sid, **malo)


def test_agregar_campana_con_enfoque(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    fam = _familia()
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1, funnel="mof",
                                consciencia="consciente del problema", dolor="pies fríos", familias=[fam, fam])
    c = datos.campana("acme", cid)
    assert (c["funnel"], c["consciencia"], c["dolor"], c["familias"]) == ("mof", "consciente_del_problema", "pies fríos", [fam])
    assert c["pais"] is None and c["idioma"] is None and c["marcas"] is None


def test_agregar_campana_precarga_la_consciencia_de_la_persona_de_nicho(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa", origen="investigada",
                              extra={"conciencia": {"nivel": "Consciente del problema", "detalle": "lo sufre"}})
    otra = datos.crear_persona("acme", "Manual")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    datos.actualizar_campana("acme", cid, consciencia=None)
    datos.actualizar_campana("acme", cid, persona_id=pid)          # vacía: vuelve a precargar
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    datos.actualizar_campana("acme", cid, persona_id=otra)         # la que ya tiene se respeta
    assert datos.campana("acme", cid)["consciencia"] == "consciente_del_problema"
    assert datos.campana("acme", cid)["persona_id"] == otra


@pytest.mark.parametrize("campos", [dict(consciencia="despistado"), dict(dolor="x" * 301),
                                    dict(familias=["No existe"]), dict(familias="Antes y después"),
                                    dict(pais="Colombia"), dict(idioma="xx"), dict(funnel="tofu"),
                                    dict(persona_id=999), dict(persona_id="abc"), dict(catalogo_id="  "),
                                    dict(marcas=[{"nombre": "X", "pagina_id": "abc"}])])
def test_actualizar_campana_valida_cada_campo(base_temporal, campos):
    from sprints import datos
    pid = _persona(datos)
    _familia()
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_campana("acme", cid, **campos)


def test_efectivos_hereda_del_sprint_y_cambia_solo_aqui(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", pais="CO", marcas="Crocs",
                             momento="Hot Sale")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert (ef["pais"], ef["idioma"], ef["marcas"], ef["momento"]) == ("CO", "es", [{"nombre": "Crocs"}], {"nombre": "Hot Sale"})
    assert ef["hereda"] == {"pais": True, "idioma": True, "marcas": True}
    datos.actualizar_campana("acme", cid, pais="us", idioma="en", marcas="Hoka")
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert (ef["pais"], ef["idioma"], ef["marcas"]) == ("US", "en", [{"nombre": "Hoka"}])
    assert ef["hereda"] == {"pais": False, "idioma": False, "marcas": False}
    datos.actualizar_campana("acme", cid, pais="", idioma="", marcas="")        # vacío = vuelve a heredar
    ef = datos.efectivos_de("acme", datos.campana("acme", cid))
    assert ef["pais"] == "CO" and ef["marcas"] == [{"nombre": "Crocs"}] and all(ef["hereda"].values())
    assert datos.sprint("acme", sid)["campanas"][0]["efectivos"]["pais"] == "CO"


def test_campanas_identicas_se_permiten_con_aviso(base_temporal):
    from sprints import datos
    pid = _persona(datos)
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    c1 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    c2 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    c3 = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0, funnel="bof")
    assert datos.campanas_identicas("acme", c2) == [1]
    assert datos.campanas_identicas("acme", c1) == [2]
    assert datos.campanas_identicas("acme", c3) == []
    assert len(datos.campanas("acme", sid)) == 3


def test_ya_no_hay_personas_genericas(base_temporal):
    from sprints import datos
    assert not hasattr(datos, "asegurar_personajes_predeterminados")
    assert not hasattr(datos, "CampanaDuplicada")
```

Update `tests/test_sprints_datos.py`: replace `test_campana_unicidad_y_cantidades` entirely with:

```python
def test_campana_repetida_y_cantidades(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    c = datos.campana("acme", cid)
    assert c["persona_nombre"] == "Premium" and c["temporada_nombre"] == "Verano" and c["estado"] == "planeada"
    assert c["referencias_objetivo"] == 5 and c["referencias_total"] == 0 and c["sprint_id"] == sid
    repetida = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)      # permitida desde 0021
    assert datos.campanas_identicas("acme", repetida) == [1]
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 0, 3, referencias_objetivo=8)
    assert datos.campana("acme", cid2)["orden"] == 2 and datos.campana("acme", cid2)["referencias_objetivo"] == 8
    for malo in [dict(n_videos=0, n_imagenes=0), dict(n_videos=-1, n_imagenes=2), dict(n_videos="x", n_imagenes=1)]:
        with pytest.raises(datos.ErrorDatos):
            datos.agregar_campana("acme", sid, pid, "otro", tid, **malo)
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, 999, "otro", tid, 1, 1)        # persona ajena
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, pid, "", tid, 1, 1)           # sin producto
```

Keep any lines that followed the old test body inside it only if they are not about duplicates or `combinaciones` (check the file: the old test ended at the «sin producto» assertion).

In `tests/test_sprints_temporada_opcional.py` replace `test_campana_sin_temporada_no_se_repite` with:

```python
def test_campana_sin_temporada_puede_repetirse(base_temporal):
    from sprints import datos
    pid, sid = _sprint(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    otra = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    assert datos.campanas_identicas("acme", otra) == [1]
```

In `tests/test_rutas_sprints.py`:
- `test_contexto_trae_lo_que_usa_la_pestana`: replace the line `assert {"Melissa", "Marijke", "Sophia"} <= set(nombres) …` with `assert not {"Melissa", "Marijke", "Sophia"} & set(nombres)          # ya no se crean solas (2026-09-26)`.
- `test_detalle_progreso_listo_y_campanas`: after the «duplicada» post change `assert len(datos.campanas("acme", sid)) == 2` to `== 3` (and its comment to `# repetida: se permite con aviso`), and after the `…/campanas/{cid}/eliminar` post change `== 1` to `== 2`.
- `test_crear_sprint_rechaza_duplicados_y_productos_ajenos`: rename to `test_crear_sprint_rechaza_productos_ajenos_y_cantidades_cero` and replace its first three lines (the `dup` post and its assertion) with nothing — keep the `ajeno`, `"[]"` and `cero` parts for now (Task 6 revisits `"[]"`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_datos.py tests/test_sprints_datos.py tests/test_sprints_temporada_opcional.py tests/test_rutas_sprints.py`
Expected: FAIL — `crear_sprint() got an unexpected keyword argument 'pais'`, `CampanaDuplicada` raised on repeats, Melissa created, etc.

- [ ] **Step 3: Implement in `sprints/datos.py`**

1. Imports: add `import doctrina` next to `import db`.

2. Constants: after `FUNNELS_NOMBRE = …` add

```python
IDIOMAS = ("es", "en", "pt", "fr", "it", "de")        # los mismos de «Traer referentes»
IDIOMAS_NOMBRE = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "it": "italiano",
                  "de": "alemán"}
PAIS_ISO = re.compile(r"^[A-Z]{2}$")
_RE_PAGINA_META = re.compile(r"view_all_page_id=(\d+)")
MAX_MARCAS = 10
MAX_FAMILIAS = 8
LARGO_DOLOR = 300
```

3. Delete `PERSONAJES_PREDETERMINADOS = [...]` (the whole list) and the function `asegurar_personajes_predeterminados`. Delete the class `CampanaDuplicada`.

4. Column tuples:

```python
_SPRINT_COLS = ("nombre", "inicio", "fin", "estado", "destinos", "referencias_objetivo_defecto", "notas",
                "archivado", "extra", "pais", "idioma", "marcas", "momento")
_CAMPANA_COLS = ("n_videos", "n_imagenes", "referencias_objetivo", "estado", "orden", "extra", "producto_id", "funnel",
                 "persona_id", "catalogo_id", "consciencia", "dolor", "familias", "pais", "idioma", "marcas")
```

5. Make `_texto` tolerate non-strings (JSON may send numbers):

```python
def _texto(v, largo=None):
    v = v if isinstance(v, str) else ("" if v is None else str(v))
    v = v.strip()
    return v[:largo] if largo else v
```

6. New validators, right after `_mood`:

```python
def _pais(v):
    """None/"" -> None; «co» -> «CO»; lo que no sean 2 letras -> ErrorDatos."""
    v = _texto(v).upper()
    if not v:
        return None
    if not PAIS_ISO.match(v):
        raise ErrorDatos("El país debe ser un código de 2 letras, como CO.")
    return v


def _idioma(v):
    v = _texto(v).lower()
    if not v:
        return None
    if v not in IDIOMAS:
        raise ErrorDatos(f"Idioma no disponible: {v}. Opciones: {', '.join(IDIOMAS)}.")
    return v


def _marca_de_texto(x):
    """«Crocs», «Crocs https://…view_all_page_id=123», «Crocs 1234567» o solo el link o el id."""
    m = _RE_PAGINA_META.search(x)
    if m:
        nombre = x[:x.find("http")] if "http" in x else _RE_PAGINA_META.sub("", x)
        return {"nombre": nombre.strip(), "pagina_id": m.group(1)}
    partes = x.split()
    if partes and partes[-1].isdigit() and len(partes[-1]) >= 5:
        return {"nombre": " ".join(partes[:-1]), "pagina_id": partes[-1]}
    return {"nombre": x}


def normalizar_marcas(v):
    """Marcas a imitar como lista de {nombre, pagina_id?}. Acepta la lista ya
    armada o el texto del formulario: una por línea (o separadas por coma),
    cada una con el link del Ad Library o el id de su página si se tiene. Sin
    repetidas (por nombre, sin importar mayúsculas); máximo MAX_MARCAS."""
    if v is None:
        return []
    if isinstance(v, str):
        items = [_marca_de_texto(x.strip()) for x in re.split(r"[\n,]", v) if x.strip()]
    elif isinstance(v, list):
        items = v
    else:
        raise ErrorDatos("Las marcas deben ser una lista.")
    salida, vistas = [], set()
    for it in items:
        if isinstance(it, str):
            it = _marca_de_texto(it.strip())
        if not isinstance(it, dict):
            raise ErrorDatos("Cada marca necesita un nombre.")
        pagina = _texto(it.get("pagina_id")) or None
        if pagina and not pagina.isdigit():
            raise ErrorDatos("El id de página de Meta son solo dígitos.")
        nombre = _texto(it.get("nombre"), 80) or (f"Página {pagina}" if pagina else "")
        if not nombre or nombre.lower() in vistas:
            continue
        vistas.add(nombre.lower())
        salida.append({"nombre": nombre, "pagina_id": pagina} if pagina else {"nombre": nombre})
    if len(salida) > MAX_MARCAS:
        raise ErrorDatos(f"Máximo {MAX_MARCAS} marcas a imitar.")
    return salida


def _momento(v):
    """None/""/{} -> None. Texto propio -> {"nombre": texto}. Dict (un preset del
    calendario ya resuelto por la ruta) -> copia limpia."""
    if v in (None, "", {}):
        return None
    if isinstance(v, str):
        v = {"nombre": v}
    if not isinstance(v, dict):
        raise ErrorDatos("El momento del mes no es válido.")
    nombre = _texto(v.get("nombre"), 120)
    if not nombre:
        return None
    m = {"nombre": nombre}
    if v.get("clave"):
        m["clave"] = _texto(v["clave"], 40)
    if v.get("contexto"):
        m["contexto"] = _texto(v["contexto"], 500)
    for k in ("inicio", "fin"):
        if v.get(k):
            m[k] = _fecha(v[k], k).isoformat()
    if v.get("mood_visual"):
        m["mood_visual"] = _mood(v["mood_visual"])
    return m


def _consciencia(v):
    if v in (None, ""):
        return None
    n = doctrina.normalizar_consciencia(v)
    if not n:
        raise ErrorDatos("Ese nivel de consciencia no existe.")
    return n


def _dolor(v):
    v = _texto(v)
    if len(v) > LARGO_DOLOR:
        raise ErrorDatos(f"El dolor o deseo va en una frase corta (máximo {LARGO_DOLOR} caracteres).")
    return v


def _familias(cliente, v):
    """Lista de nombres de `referente_familia` (sin repetir, máximo MAX_FAMILIAS)."""
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise ErrorDatos("Las familias deben ser una lista.")
    nombres = []
    for x in v:
        x = _texto(x, 120)
        if x and x not in nombres:
            nombres.append(x)
    if len(nombres) > MAX_FAMILIAS:
        raise ErrorDatos(f"Máximo {MAX_FAMILIAS} familias de formato por campaña.")
    if nombres:
        existentes = {f["nombre"] for f in referentes_datos.familias(cliente)}
        for x in nombres:
            if x not in existentes:
                raise ErrorDatos(f"«{x}» no es una familia de la biblioteca.")
    return nombres


def consciencia_de_persona(p):
    """Nivel de consciencia que Nicho le dejó a una persona
    (`extra.conciencia.nivel`) como clave de `doctrina.CONSCIENCIAS`; None si no tiene."""
    conc = ((p or {}).get("extra") or {}).get("conciencia")
    return doctrina.normalizar_consciencia(conc.get("nivel") if isinstance(conc, dict) else conc)
```

7. `crear_sprint`: new signature `def crear_sprint(cliente, nombre, inicio, fin, destinos=None, referencias_objetivo_defecto=5, notas="", pais=None, idioma="es", marcas=None, momento=None):`. Before `ahora = db.ahora()` add

```python
    pais, idioma = _pais(pais), _idioma(idioma) or "es"
    marcas, momento = normalizar_marcas(marcas), _momento(momento)
```

and add `pais=pais, idioma=idioma, marcas=marcas, momento=momento` to the `db.sprint.insert().values(...)`.

8. `actualizar_sprint`: at the top of the function add

```python
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 200)
        if not campos["nombre"]:
            raise ErrorDatos("El sprint necesita un nombre.")
    if "pais" in campos:
        campos["pais"] = _pais(campos["pais"])
    if "idioma" in campos:
        campos["idioma"] = _idioma(campos["idioma"]) or "es"
    if "marcas" in campos:
        campos["marcas"] = normalizar_marcas(campos["marcas"])
    if "momento" in campos:
        campos["momento"] = _momento(campos["momento"])
```

9. `_sprint_dict`: after `d["campanas"] = _campanas(...)` add

```python
    d["marcas"] = d.get("marcas") or []
    d["idioma"] = d.get("idioma") or "es"
    for c in d["campanas"]:
        c["efectivos"] = efectivos(d, c)
```

10. Replace `agregar_campana` with:

```python
def agregar_campana(cliente, sprint_id, persona_id, catalogo_id, temporada_id=None, n_videos=5, n_imagenes=5,
                    referencias_objetivo=None, funnel="tof", consciencia=None, dolor="", familias=None):
    """Crea una campaña. Repetir persona y producto se permite desde 0021 (TOF,
    MOF y BOF del mismo producto, o dos TOF con distinto formato):
    `campanas_identicas` solo sirve para avisar. Sin `consciencia`, toma la
    que Nicho le dejó a la persona."""
    n_videos, n_imagenes = _cantidades(n_videos, n_imagenes)
    temporada_id = temporada_id or None          # la temporada es opcional (migración 0020)
    catalogo_id = _texto(catalogo_id, 120)
    if not catalogo_id:
        raise ErrorDatos("Elige un producto.")
    if funnel not in FUNNELS:
        raise ErrorDatos(f"Funnel inválido: {funnel}. Opciones: {FUNNELS}")
    dolor, familias = _dolor(dolor), _familias(cliente, familias)
    consciencia = _consciencia(consciencia)
    ahora = db.ahora()
    with db.conectar() as con:
        sp = _fila(con, db.sprint, sprint_id, cliente)
        if not sp:
            raise ErrorDatos("Ese sprint no existe.")
        p = _fila(con, db.persona, persona_id, cliente)
        if not p:
            raise ErrorDatos("Esa persona no existe en este proyecto.")
        if consciencia is None:
            consciencia = consciencia_de_persona(_a_dict(p))
        if temporada_id and not _fila(con, db.temporada, temporada_id, cliente):
            raise ErrorDatos("Esa temporada no existe en este proyecto.")
        c = db.campana
        # max+1 y no count: si se borró una campaña intermedia, count repetiría un número ya usado.
        orden = con.execute(sa.select(sa.func.coalesce(sa.func.max(c.c.orden), -1) + 1)
                            .where(c.c.sprint_id == sprint_id)).scalar()
        try:
            objetivo = int(referencias_objetivo or sp.referencias_objetivo_defecto or 5)
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
        cid = con.execute(c.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, sprint_id=sprint_id, persona_id=persona_id,
            catalogo_id=catalogo_id, producto_id=None, temporada_id=temporada_id, n_videos=n_videos,
            n_imagenes=n_imagenes, referencias_objetivo=max(1, objetivo), estado="planeada", orden=orden,
            funnel=funnel, consciencia=consciencia, dolor=dolor, familias=familias, extra={})).inserted_primary_key[0]
        _evento(con, cliente, sprint_id, cid, "campana_agregada", "Campaña agregada",
                {"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id,
                 "n_videos": n_videos, "n_imagenes": n_imagenes, "funnel": funnel, "consciencia": consciencia})
        con.execute(db.sprint.update().where(db.sprint.c.id == sprint_id).values(actualizado_en=ahora))
    return cid
```

11. Replace `actualizar_campana` with:

```python
def actualizar_campana(cliente, campana_id, /, **campos):
    actual = {}

    def _actual():
        if not actual:
            actual.update(campana(cliente, campana_id) or {})
        return actual

    if "n_videos" in campos or "n_imagenes" in campos:
        campos["n_videos"], campos["n_imagenes"] = _cantidades(campos.get("n_videos", _actual().get("n_videos")),
                                                               campos.get("n_imagenes", _actual().get("n_imagenes")))
    if "estado" in campos and campos["estado"] not in ESTADOS_CAMPANA:
        raise ErrorDatos(f"Estado de campaña inválido: {campos['estado']}")
    if "referencias_objetivo" in campos:
        try:
            campos["referencias_objetivo"] = max(1, int(campos["referencias_objetivo"]))
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
    if "funnel" in campos and campos["funnel"] not in FUNNELS:
        raise ErrorDatos("La etapa debe ser TOF, MOF o BOF.")
    if "consciencia" in campos:
        campos["consciencia"] = _consciencia(campos["consciencia"])
    if "dolor" in campos:
        campos["dolor"] = _dolor(campos["dolor"])
    if "familias" in campos:
        campos["familias"] = _familias(cliente, campos["familias"])
    if "pais" in campos:
        campos["pais"] = _pais(campos["pais"])
    if "idioma" in campos:
        campos["idioma"] = _idioma(campos["idioma"])
    if "marcas" in campos:
        campos["marcas"] = normalizar_marcas(campos["marcas"]) or None      # vacío = hereda del sprint
    if "catalogo_id" in campos:
        campos["catalogo_id"] = _texto(campos["catalogo_id"], 120)
        if not campos["catalogo_id"]:
            raise ErrorDatos("Elige un producto.")
    if "persona_id" in campos:
        try:
            campos["persona_id"] = int(campos["persona_id"])
        except (TypeError, ValueError):
            raise ErrorDatos("Esa persona no existe en este proyecto.")
        p = persona(cliente, campos["persona_id"])
        if not p:
            raise ErrorDatos("Esa persona no existe en este proyecto.")
        if "consciencia" not in campos and not _actual().get("consciencia"):
            campos["consciencia"] = consciencia_de_persona(p)
    with db.conectar() as con:
        return _actualizar(con, db.campana, campana_id, cliente, _CAMPANA_COLS, campos)
```

12. After `campanas(cliente, sprint_id)` add:

```python
def efectivos(sprint_, campana_):
    """País, idioma, marcas y momento que valen para una campaña: los suyos si
    los cambió «solo aquí», si no los del sprint. `hereda` dice cuáles vienen
    del sprint (el panel lo muestra)."""
    s, c = sprint_ or {}, campana_ or {}
    marcas_propias = c.get("marcas")
    return {"pais": c.get("pais") or s.get("pais"),
            "idioma": c.get("idioma") or s.get("idioma") or "es",
            "marcas": list(marcas_propias if marcas_propias is not None else (s.get("marcas") or [])),
            "momento": s.get("momento"),
            "hereda": {"pais": not c.get("pais"), "idioma": not c.get("idioma"), "marcas": marcas_propias is None}}


def efectivos_de(cliente, campana_):
    """`efectivos` leyendo solo la fila del sprint (sin sus campañas ni ideas)."""
    with db.conectar() as con:
        f = _fila(con, db.sprint, campana_["sprint_id"], cliente)
    return efectivos(_a_dict(f) if f else {}, campana_)


def _clave_identica(c):
    return (c["persona_id"], c["catalogo_id"], c.get("funnel") or "tof", c.get("consciencia") or None,
            tuple(sorted(c.get("familias") or [])))


def campanas_identicas(cliente, campana_id):
    """Números (1, 2, …) de las OTRAS campañas del sprint con la misma persona,
    producto, etapa, consciencia y familias. Solo para avisar: repetir se permite."""
    c = campana(cliente, campana_id)
    if not c:
        return []
    clave = _clave_identica(c)
    return [int(o["orden"]) + 1 for o in campanas(cliente, c["sprint_id"])
            if o["id"] != c["id"] and _clave_identica(o) == clave]
```

- [ ] **Step 4: Adjust `sprints/rutas.py`**

- In `contexto(cliente)` delete the first line `datos.asegurar_personajes_predeterminados(cliente)`.
- In `ver(cliente, sid)` delete the first line `datos.asegurar_personajes_predeterminados(cliente)`.
- In `_validar_campanas` delete `vistas, ` from `vistas, limpias = set(), []` (leave `limpias = []`) and delete the four lines starting at `clave = (persona_id, catalogo_id, temporada_id)` through `vistas.add(clave)`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_datos.py tests/test_sprints_datos.py tests/test_sprints_temporada_opcional.py tests/test_rutas_sprints.py tests/test_sprints_ideas.py tests/test_tareas_sprints.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sprints/datos.py sprints/rutas.py tests/test_sprints_tablero_datos.py tests/test_sprints_datos.py tests/test_sprints_temporada_opcional.py tests/test_rutas_sprints.py
git commit -m "Sprints tablero: datos del mercado, enfoque de la campaña y herencia; sin personas genéricas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Referentes sugeridos según el enfoque de la campaña

**Files:**
- Modify: `referentes/datos.py` (add `familias_frecuentes` after `listar`)
- Modify: `referentes/sugerir.py`
- Modify: `tareas/sprints.py` (`ejecutar_sugerir_biblioteca`)
- Test: `tests/test_referentes_sugerir.py`, `tests/test_referentes_datos.py`, `tests/test_tareas_sprints.py`

**Interfaces:**
- Consumes: `sprints.datos.efectivos_de`, `sprints.datos.consciencia_de_persona`, `sprints.datos.IDIOMAS_NOMBRE` (Task 2).
- Produces:
  - `referentes.datos.familias_frecuentes(cliente, etapa=None, consciencia=None, limite=6) -> list[str]` (`etapa` TOF|MOF|BOF, `consciencia` in English).
  - `referentes.sugerir.candidatos(cliente, etapa, excluir_ids=None, limite=200, consciencia=None, familia=None)`.
  - `referentes.sugerir.consciencia_en(clave) -> str|None` (doctrina key → English).
  - `referentes.sugerir.preferencia(c, marcas=(), idioma=None) -> tuple`.
  - `referentes.sugerir.sugerir_campana(cliente, enfoque, excluir_ids, objetivo, limite=200) -> {"items": list[dict], "aflojado": list[str]}` where `enfoque = {"etapa": "TOF"|"MOF"|"BOF"|None, "consciencia": doctrina key|None, "familias": list[str], "idioma": str|None, "marcas": list[dict]}` and `aflojado ⊆ ["familias", "consciencia"]` in that order.
  - `referentes.sugerir.candidatos_aflojando(cliente, enfoque, excluir_ids, minimo=20, limite=200) -> (list[dict], list[str])`.
  - `referentes.sugerir.sugerir_ia(candidatos_, persona_texto, producto_texto, temporada_texto, objetivo, enfoque_texto="")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_referentes_sugerir.py`:

```python
# ------------------------------------------------ tablero de Sprints (2026-09-26) ---

def _r(id, familia, consciencia="problem-aware", etapa="TOF", marca="", idioma="en", dias=1, variantes=1,
       pagina_id=None):
    return {"id": id, "familia": familia, "consciencia": consciencia, "etapa": etapa, "marca": marca,
            "idioma": idioma, "dias": dias, "variantes": variantes, "pagina_id": pagina_id, "clasificacion": "claude",
            "dolor": "", "firma": "", "titular": "", "imagen_url": ""}


def _biblioteca(monkeypatch, filas):
    """`referentes.datos.listar` falso que aplica los mismos filtros exactos que el real."""
    import referentes.datos as referentes_datos

    def listar(cliente, filtros, pagina, por_pagina):
        f = filtros or {}
        items = [r for r in filas if all(r.get(k) == f[k] for k in ("etapa", "consciencia", "familia") if f.get(k))]
        return {"items": items[:por_pagina]}
    monkeypatch.setattr(referentes_datos, "listar", listar)


def test_sugerir_campana_respeta_consciencia_y_familias(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A"), _r(2, "B"), _r(3, "A", consciencia="unaware")])
    r = sugerir.sugerir_campana("acme", {"etapa": "TOF", "consciencia": "consciente_del_problema", "familias": ["A"]},
                                set(), 1)
    assert [c["id"] for c in r["items"]] == [1] and r["aflojado"] == []


def test_sugerir_campana_afloja_familias_y_despues_consciencia(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A"), _r(2, "B"), _r(3, "A", consciencia="unaware")])
    r = sugerir.sugerir_campana("acme", {"etapa": "TOF", "consciencia": "consciente_del_problema", "familias": ["A"]},
                                set(), 3)
    assert [c["id"] for c in r["items"]] == [1, 2, 3]
    assert r["aflojado"] == ["familias", "consciencia"]


def test_sugerir_campana_sin_familias_toma_una_por_familia(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A", dias=5), _r(2, "A", dias=9), _r(3, "B")])
    r = sugerir.sugerir_campana("acme", {"etapa": "TOF"}, set(), 3)
    assert [c["id"] for c in r["items"]] == [2, 3] and r["aflojado"] == []


def test_sugerir_campana_ordena_marca_idioma_y_rendimiento(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A", dias=100, variantes=10), _r(2, "B", idioma="es"),
                              _r(3, "C", marca="Crocs"), _r(4, "D", pagina_id="555")])
    r = sugerir.sugerir_campana("acme", {"etapa": "TOF", "idioma": "es",
                                         "marcas": [{"nombre": "crocs"}, {"nombre": "Hoka", "pagina_id": "555"}]},
                                set(), 4)
    assert [c["id"] for c in r["items"]] == [4, 3, 2, 1] or [c["id"] for c in r["items"]] == [3, 4, 2, 1]
    assert [c["id"] for c in r["items"]][2:] == [2, 1]


def test_sugerir_campana_excluye_los_ya_elegidos_y_sin_etapa_busca_en_todas(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A"), _r(2, "B", etapa="MOF")])
    assert [c["id"] for c in sugerir.sugerir_campana("acme", {"etapa": "TOF"}, {1}, 2)["items"]] == []
    assert [c["id"] for c in sugerir.sugerir_campana("acme", {"etapa": None}, {1}, 2)["items"]] == [2]


def test_candidatos_aflojando_llega_al_minimo(monkeypatch):
    _biblioteca(monkeypatch, [_r(1, "A"), _r(2, "B"), _r(3, "A", consciencia="unaware")])
    lista, aflojado = sugerir.candidatos_aflojando(
        "acme", {"etapa": "TOF", "consciencia": "consciente_del_problema", "familias": ["A"]}, set(), minimo=3)
    assert [c["id"] for c in lista] == [1, 2, 3] and aflojado == ["familias", "consciencia"]
    lista, aflojado = sugerir.candidatos_aflojando("acme", {"etapa": "TOF", "familias": ["A"]}, set(), minimo=1)
    assert [c["id"] for c in lista] == [1, 3] and aflojado == []


def test_consciencia_en_traduce_claves_de_doctrina():
    assert sugerir.consciencia_en("consciente_del_problema") == "problem-aware"
    assert sugerir.consciencia_en(None) is None and sugerir.consciencia_en("nada") is None


def test_sugerir_ia_manda_el_enfoque(monkeypatch):
    pedidos = []
    _cliente_que_responde(monkeypatch, _RespuestaFalsa('{"elegidos": []}'), pedidos)
    sugerir.sugerir_ia([_cand(1, "A")], "p", "pr", "t", 1, enfoque_texto="marcas a imitar: Crocs")
    texto = pedidos[0]["messages"][0]["content"]
    assert "<enfoque>marcas a imitar: Crocs</enfoque>" in texto
```

(`_cliente_que_responde`, `_RespuestaFalsa` and `_cand` already exist in that file; the fake client records the kwargs of `messages.create`.)

Append to `tests/test_referentes_datos.py`:

```python
def test_familias_frecuentes_por_etapa_y_consciencia(base_temporal):
    from referentes import datos as rdatos

    def ref(n, familia, etapa="TOF", consciencia="problem-aware"):
        rid, _ = rdatos.guardar_referente({"anuncio_id": f"f{n}", "fuente": "atria", "imagen_origen": "https://o/x.jpg"})
        rdatos.marcar_imagen(rid, "ok", f"https://r2/{n}.jpg")
        rdatos.actualizar_referente(rid, etapa=etapa, consciencia=consciencia, familia=familia, clasificacion="claude")

    for n, fam in enumerate(["A", "A", "B"]):
        ref(n, fam)
    ref(10, "C", etapa="MOF")
    ref(11, "D", consciencia="unaware")
    assert rdatos.familias_frecuentes("acme", etapa="TOF", consciencia="problem-aware") == ["A", "B"]
    assert rdatos.familias_frecuentes("acme", etapa="TOF") == ["A", "B", "D"]
    assert rdatos.familias_frecuentes("acme", etapa="TOF", limite=1) == ["A"]
```

In `tests/test_tareas_sprints.py`:
- In `test_ejecutar_sugerir_biblioteca_guarda_sugerencias` replace the two `monkeypatch.setattr(referentes_sugerir, …)` calls with:

```python
    enfoques = []
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        enfoques.append(enfoque) or [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    textos = []
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="": (
        textos.append((p, t, enfoque_texto)) or ([{"referente_id": 5, "razon": "encaja"}], 100, 20)))
```

and at the end of that test add:

```python
    assert enfoques[0]["etapa"] == "TOF" and enfoques[0]["idioma"] == "es"
    assert "idioma de la audiencia: español" in textos[0][2]
```

- In `test_ejecutar_sugerir_biblioteca_sin_candidatos` replace the `candidatos` monkeypatch with `monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: ([], []))`.
- Search the rest of the file for other `monkeypatch.setattr(referentes_sugerir, "candidatos"` or `"sugerir_ia"` lambdas in `referentes_sugerir_ia` tests and apply the same two replacements (lambda signatures above).
- Add:

```python
def test_sugerir_biblioteca_usa_el_enfoque_de_la_campana(base_temporal, monkeypatch):
    import tareas
    import referentes.sugerir as referentes_sugerir
    from referentes import datos as rdatos
    from sprints import datos
    sid, cid, rid = _referencia(datos)
    rdatos.familia_asegurar("UGC", "")
    datos.actualizar_sprint("acme", sid, idioma="en", marcas="Crocs", momento="Hot Sale")
    datos.actualizar_campana("acme", cid, consciencia="consciente_del_problema", dolor="pies fríos", familias=["UGC"])
    vistos = {}
    monkeypatch.setattr(referentes_sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        vistos.update(enfoque=enfoque) or [{"id": 5, "familia": "UGC"}], []))
    monkeypatch.setattr(referentes_sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="": (
        vistos.update(persona=p, temporada=t, enfoque_texto=enfoque_texto) or ([], 10, 5)))
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 1, "payload": {"cliente": "acme", "campana_id": cid}})
    e = vistos["enfoque"]
    assert (e["consciencia"], e["familias"], e["idioma"], e["marcas"]) == ("consciente_del_problema", ["UGC"], "en", [{"nombre": "Crocs"}])
    assert "pies fríos" in vistos["persona"] and "consciente del problema" in vistos["persona"]
    assert vistos["temporada"] == "Hot Sale"
    assert "UGC" in vistos["enfoque_texto"] and "Crocs" in vistos["enfoque_texto"] and "inglés" in vistos["enfoque_texto"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_referentes_sugerir.py tests/test_referentes_datos.py tests/test_tareas_sprints.py`
Expected: FAIL — `AttributeError: module 'referentes.sugerir' has no attribute 'sugerir_campana'`, `familias_frecuentes` missing.

- [ ] **Step 3: Implement**

In `referentes/datos.py`, after `listar(...)`:

```python
def familias_frecuentes(cliente, etapa=None, consciencia=None, limite=6):
    """Las familias con más anuncios visibles para esa etapa (TOF|MOF|BOF) y
    consciencia (el inglés de `CONSCIENCIAS`), de más a menos: las «sugeridas
    para esta etapa» del panel de una campaña de Sprints."""
    t = db.referente
    cond = _condiciones(cliente, {"etapa": etapa, "consciencia": consciencia})
    q = (sa.select(t.c.familia, sa.func.count().label("n"))
         .where(*cond, t.c.familia.isnot(None), t.c.familia != "")
         .group_by(t.c.familia).order_by(sa.desc("n"), t.c.familia).limit(max(1, int(limite))))
    with db.conectar() as con:
        return [r[0] for r in con.execute(q)]
```

In `referentes/sugerir.py`:

1. `candidatos` gets `familia=None`:

```python
def candidatos(cliente, etapa, excluir_ids=None, limite=200, consciencia=None, familia=None):
    """Referentes visibles de esa etapa, ya clasificados (`fuente`/`claude`) y
    fuera de `excluir_ids`, en el orden que ya usa `referentes.datos.listar`
    (más días primero). Cuando `consciencia` es uno de
    `referentes.datos.CONSCIENCIAS` también filtra por ese nivel, y `familia`
    por esa familia exacta. No aplica el desempate por familia — eso es `elegir`."""
    excluir = set(excluir_ids or ())
    filtros = {"etapa": etapa}
    if consciencia in referentes_datos.CONSCIENCIAS:
        filtros["consciencia"] = consciencia
    if familia:
        filtros["familia"] = familia
    filas = referentes_datos.listar(cliente, filtros, pagina=1, por_pagina=limite)["items"]
    return [r for r in filas if r["id"] not in excluir and r.get("clasificacion") in CLASIFICACIONES_USABLES]
```

2. Add after `sugerir(...)`:

```python
# ------------------------------------------- campañas del tablero (2026-09-26) ---

def consciencia_en(clave):
    """Clave de `doctrina.CONSCIENCIAS` (o cualquier forma que entienda
    `normalizar_consciencia`) -> el inglés con que la biblioteca clasifica."""
    return NIVEL_A_CONSCIENCIA.get(doctrina.normalizar_consciencia(clave)) if clave else None


def preferencia(c, marcas=(), idioma=None):
    """Clave de orden de un candidato para una campaña: primero las marcas a
    imitar (por nombre o por id de página), luego el idioma de la campaña,
    luego `variantes × max(días, 1)` (más tiempo y más versiones al aire)."""
    nombres = {(m.get("nombre") or "").strip().lower() for m in marcas or ()} - {""}
    paginas = {str(m["pagina_id"]) for m in marcas or () if m.get("pagina_id")}
    de_marca = (c.get("marca") or "").strip().lower() in nombres or str(c.get("pagina_id") or "") in paginas
    return (int(bool(de_marca)), int(bool(idioma) and c.get("idioma") == idioma),
            (c.get("variantes") or 0) * max(c.get("dias") or 0, 1))


def _candidatos_con(cliente, etapa, consciencia, familias, excluir, limite):
    if not familias:
        return candidatos(cliente, etapa, excluir, limite=limite, consciencia=consciencia)
    vistos, salida = set(), []
    for f in familias:
        for c in candidatos(cliente, etapa, excluir, limite=limite, consciencia=consciencia, familia=f):
            if c["id"] not in vistos:
                vistos.add(c["id"])
                salida.append(c)
    return salida


def _pasos(enfoque):
    """Filtros de más a menos estrictos, con lo que aflojó cada paso: todo;
    sin familias; sin consciencia. La etapa nunca se afloja aquí (el panel
    ofrece «todas las etapas» aparte, con `etapa=None`)."""
    etapa = (enfoque.get("etapa") or "").upper() or None
    cons = consciencia_en(enfoque.get("consciencia"))
    fams = list(enfoque.get("familias") or [])
    pasos = [(etapa, cons, fams, None)]
    if fams:
        pasos.append((etapa, cons, [], "familias"))
    if cons:
        pasos.append((etapa, None, [], "consciencia"))
    return pasos


def sugerir_campana(cliente, enfoque, excluir_ids, objetivo, limite=200):
    """Sugeridos gratis para el panel de una campaña (spec 2026-09-26).
    `enfoque`: {etapa: TOF|MOF|BOF|None, consciencia: clave de doctrina|None,
    familias: [...], idioma, marcas: [{nombre, pagina_id?}]}. Filtra por etapa,
    consciencia y familias; si no alcanza `objetivo` afloja primero las
    familias y después la consciencia. Ordena con `preferencia` y toma una
    por familia salvo que la campaña haya elegido familias. Devuelve
    {"items": [...], "aflojado": [...]}."""
    objetivo = max(1, int(objetivo))
    marcas, idioma = enfoque.get("marcas") or [], enfoque.get("idioma")
    una_por_familia = not enfoque.get("familias")
    excluir = set(excluir_ids or ())
    elegidos, aflojado, usadas = [], [], set()
    for etapa, cons, fams, afloja in _pasos(enfoque):
        if len(elegidos) >= objetivo:
            break
        if afloja:
            aflojado.append(afloja)
        ya = excluir | {e["id"] for e in elegidos}
        orden = sorted(_candidatos_con(cliente, etapa, cons, fams, ya, limite),
                       key=lambda c: preferencia(c, marcas, idioma), reverse=True)
        for c in orden:
            if len(elegidos) >= objetivo:
                break
            if una_por_familia and c.get("familia") and c["familia"] in usadas:
                continue
            elegidos.append(c)
            if c.get("familia"):
                usadas.add(c["familia"])
    return {"items": elegidos, "aflojado": aflojado}


def candidatos_aflojando(cliente, enfoque, excluir_ids, minimo=20, limite=200):
    """Los candidatos que ve «Sugerir con IA»: los mismos filtros que
    `sugerir_campana`, aflojando igual mientras haya menos de `minimo`, en el
    orden de `preferencia`. Devuelve (lista, aflojado)."""
    marcas, idioma = enfoque.get("marcas") or [], enfoque.get("idioma")
    excluir = set(excluir_ids or ())
    salida, aflojado = [], []
    for etapa, cons, fams, afloja in _pasos(enfoque):
        if len(salida) >= minimo:
            break
        if afloja:
            aflojado.append(afloja)
        ya = excluir | {c["id"] for c in salida}
        salida += sorted(_candidatos_con(cliente, etapa, cons, fams, ya, limite),
                         key=lambda c: preferencia(c, marcas, idioma), reverse=True)
    return salida, aflojado
```

3. `PROMPT_SUGERIR`: after the line `Temporada: <temporada>{temporada}</temporada>` add a new line `Enfoque de la campaña: <enfoque>{enfoque}</enfoque>`, and in the paragraph that starts `Elige hasta {objetivo} candidatos` replace «que mejor encajen con esta persona, producto y temporada» with «que mejor encajen con esta persona, producto, temporada y enfoque (formatos y marcas a imitar primero)».

4. `sugerir_ia`: signature `def sugerir_ia(candidatos_, persona_texto, producto_texto, temporada_texto, objetivo, enfoque_texto=""):` and add to the `PROMPT_SUGERIR.format(...)` call `enfoque=_sin_cierre(enfoque_texto or "(sin enfoque definido)", "enfoque"),`.

In `tareas/sprints.py`, replace the body of `ejecutar_sugerir_biblioteca` from `persona = datos.persona(...)` down to (and including) the `try: elegidos, ent, sal = referentes_sugerir.sugerir_ia(...)` call's arguments with:

```python
    persona = datos.persona(cliente, c["persona_id"]) or {}
    producto = catalogo_productos.encontrar(cliente, c["catalogo_id"], categoria="producto") or {}
    temporada = datos.temporada(cliente, c["temporada_id"]) or {}
    ef = datos.efectivos_de(cliente, c)
    refs_actuales = datos.referencias(cliente, cid)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in refs_actuales} - {None}
    enfoque = {"etapa": (c.get("funnel") or "tof").upper(),
               "consciencia": c.get("consciencia") or datos.consciencia_de_persona(persona),
               "familias": c.get("familias") or [], "idioma": ef["idioma"], "marcas": ef["marcas"]}
    candidatos, _ = referentes_sugerir.candidatos_aflojando(cliente, enfoque, ya_ids, minimo=20)
    if not candidatos:
        return "No hay candidatos nuevos en la biblioteca para esta etapa."
    objetivo = max(1, (c.get("referencias_objetivo") or 1) - len(refs_actuales))
    nivel = doctrina.normalizar_consciencia(enfoque["consciencia"])
    persona_texto = ". ".join(x for x in (persona.get("resumen"), persona.get("descripcion"), persona.get("tono"),
                                          f"nivel de consciencia: {doctrina.CONSCIENCIAS_NOMBRE[nivel]}" if nivel else None,
                                          f"dolor o deseo: {c['dolor']}" if c.get("dolor") else None)
                              if x)
    producto_texto = ". ".join(x for x in (producto.get("nombre"), producto.get("descripcion")) if x)
    momento = ef.get("momento") or {}
    temporada_texto = (". ".join(x for x in (momento.get("nombre"), momento.get("contexto")) if x)
                       or ". ".join(x for x in (temporada.get("nombre"), temporada.get("contexto")) if x))
    enfoque_texto = "; ".join(x for x in (
        ("formatos buscados: " + ", ".join(enfoque["familias"])) if enfoque["familias"] else None,
        ("marcas a imitar: " + ", ".join(m["nombre"] for m in enfoque["marcas"])) if enfoque["marcas"] else None,
        f"idioma de la audiencia: {datos.IDIOMAS_NOMBRE.get(enfoque['idioma'], enfoque['idioma'])}") if x)
    try:
        elegidos, ent, sal = referentes_sugerir.sugerir_ia(candidatos[:60], persona_texto, producto_texto,
                                                            temporada_texto, objetivo, enfoque_texto=enfoque_texto)
```

(The `except referentes_sugerir.SugerenciaInvalida` block and everything after stay as they are. Update the docstring's first sentence to say «candidatos con los filtros de la campaña (etapa, consciencia, familias, aflojando si faltan)».)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_referentes_sugerir.py tests/test_referentes_datos.py tests/test_tareas_sprints.py tests/test_rutas_sprints.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add referentes/datos.py referentes/sugerir.py tareas/sprints.py tests/test_referentes_sugerir.py tests/test_referentes_datos.py tests/test_tareas_sprints.py
git commit -m "Sprints tablero: referentes sugeridos por etapa, consciencia, familias, marcas e idioma (y la IA con el mismo enfoque)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Ideas con enfoque, mercado, marcas y momento

**Files:**
- Modify: `sprints/ideas.py`
- Test: `tests/test_sprints_ideas.py`

**Interfaces:**
- Consumes: `sprints.datos.efectivos_de`, `IDIOMAS_NOMBRE` (Task 2); `referentes.datos.familias(cliente)`.
- Produces: `contexto_campana(...)` also returns `consciencia`, `dolor`, `familias: [{"nombre","descripcion"}]`, `mercado: {"pais","idioma"}`, `marcas`, `momento`; `armar_prompt` prints them; `instrucciones(ctx)` asks for the gancho in the market language when it is not Spanish.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_ideas.py`:

```python
def test_armar_prompt_lleva_enfoque_mercado_marcas_y_momento(base_temporal, monkeypatch):
    from referentes import datos as rdatos
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    rdatos.familia_asegurar("Antes y después", "Muestra el cambio en dos cuadros")
    datos.actualizar_sprint("acme", sid, pais="US", idioma="en", marcas="Crocs", momento="Hot Sale")
    datos.actualizar_campana("acme", cid, consciencia="consciente_del_problema", dolor="pies fríos",
                             familias=["Antes y después"])
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    for frag in ("consciente del problema", "pies fríos", "Antes y después", "Muestra el cambio en dos cuadros",
                 "Estados Unidos", "inglés", "Crocs", "Hot Sale"):
        assert frag in p, frag
    assert "Navidad" not in p                        # el momento del sprint gana a la temporada vieja
    assert "inglés" in ideas.instrucciones(ctx) and "Todo en español." not in ideas.instrucciones(ctx)


def test_sin_momento_sigue_la_temporada_y_sin_enfoque_lo_dice(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    assert "Navidad" in p and "regalos" in p and "(sin enfoque definido" in p and "MARCAS A IMITAR" in p
    assert ideas.instrucciones(ctx).endswith("Todo en español.")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_ideas.py`
Expected: FAIL — «consciente del problema» not in prompt.

- [ ] **Step 3: Implement in `sprints/ideas.py`**

1. Imports: add `from final_edition import tipos as fe_tipos` and `from referentes import datos as referentes_datos` (alphabetical with the others).

2. In `INSTRUCCIONES_IDEAS` replace the final `Todo en español."""` with `{idioma_textos}"""`.

3. In `DATOS_IDEAS` replace

```
AUDIENCIA (persona): {persona}
ETAPA DEL EMBUDO DE LA CAMPAÑA: {funnel}
PRODUCTO: {producto}
TEMPORADA: {temporada}
```

with

```
AUDIENCIA (persona): {persona}
ENFOQUE DE LA CAMPAÑA: {enfoque}
ETAPA DEL EMBUDO DE LA CAMPAÑA: {funnel}
MERCADO: {mercado}
PRODUCTO: {producto}
MARCAS A IMITAR (su manera de anunciar, nunca su nombre ni su logo): {marcas}
TEMPORADA: {temporada}
```

4. `_temporada_texto`: only print dates when both exist (a «momento» may have none). Replace its second line with:

```python
    partes = [t.get("nombre") or ""]
    if t.get("inicio") and t.get("fin"):
        partes.append(f"{t['inicio']} → {t['fin']}")
```

5. New helpers after `_temporada_texto`:

```python
def _enfoque_texto(ctx):
    partes = []
    if ctx.get("consciencia") in doctrina.CONSCIENCIAS:
        partes.append(f"consciencia de la audiencia: {doctrina.CONSCIENCIAS_NOMBRE[ctx['consciencia']]}")
    if ctx.get("dolor"):
        partes.append(f"dolor o deseo a atacar: {ctx['dolor']}")
    familias = [f["nombre"] + (f" ({f['descripcion']})" if f.get("descripcion") else "")
                for f in ctx.get("familias") or []]
    if familias:
        partes.append("formatos de anuncio a seguir: " + "; ".join(familias))
    return "; ".join(partes) or "(sin enfoque definido: decídelo a partir de la persona)"


def _mercado_texto(ctx):
    m = ctx.get("mercado") or {}
    pais = (fe_tipos.PAISES.get(m.get("pais") or "") or {}).get("nombre") or m.get("pais")
    idioma = datos.IDIOMAS_NOMBRE.get(m.get("idioma") or "es", m.get("idioma"))
    return (f"{pais} · " if pais else "") + f"el gancho y los textos en pantalla van en {idioma}"
```

6. `contexto_campana`: before `return {` add

```python
    ef = datos.efectivos_de(cliente, campana)
    nombres_familias = campana.get("familias") or []
    descripciones = ({f["nombre"]: f.get("descripcion") or "" for f in referentes_datos.familias(cliente)}
                     if nombres_familias else {})
```

and add to the returned dict:

```python
        "consciencia": campana.get("consciencia"),
        "dolor": campana.get("dolor") or "",
        "familias": [{"nombre": f, "descripcion": descripciones.get(f, "")} for f in nombres_familias],
        "mercado": {"pais": ef["pais"], "idioma": ef["idioma"]},
        "marcas": ef["marcas"],
        "momento": ef["momento"],
```

7. `armar_prompt`: in the `DATOS_IDEAS.format(...)` call change `temporada=_temporada_texto(ctx.get("temporada"))` to `temporada=_temporada_texto(ctx.get("momento") or ctx.get("temporada"))` and add

```python
        enfoque=_enfoque_texto(ctx), mercado=_mercado_texto(ctx),
        marcas=", ".join(m["nombre"] for m in ctx.get("marcas") or []) or "ninguna",
```

8. `instrucciones(ctx)`: compute before the `return` and pass it to `.format(...)`:

```python
    idioma = (ctx.get("mercado") or {}).get("idioma") or "es"
    idioma_textos = ("Todo en español." if idioma == "es" else
                     f"Todo en español salvo el gancho (el texto en pantalla), que va en "
                     f"{datos.IDIOMAS_NOMBRE.get(idioma, idioma)}, el idioma del MERCADO.")
```

(add `idioma_textos=idioma_textos` to the `INSTRUCCIONES_IDEAS.format(...)` arguments).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_ideas.py tests/test_tareas_sprints.py tests/test_rutas_sprints.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sprints/ideas.py tests/test_sprints_ideas.py
git commit -m "Sprints tablero: las ideas reciben consciencia, dolor, formatos, mercado, marcas y el momento del mes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `sprints/tablero.py` — lo que muestran tarjetas y cabecera

**Files:**
- Create: `sprints/tablero.py`
- Test: `tests/test_sprints_tablero.py`

**Interfaces:**
- Consumes: campaign dicts from `sprints.datos` (keys `referencias_objetivo`, `referencias_listas`, `n_videos`, `n_imagenes`, `ideas` [with `estado_idea`, `sin_sesion`], `piezas` [with `estado`, `revision`]); `sprints.datos.IDIOMAS_NOMBRE`, `sprints.datos._PIEZA_TERMINADA`.
- Produces:
  - `siguiente_paso(c) -> {"clave": "referentes"|"aprobar"|"ideas"|"generar"|"generando"|"errores"|"revisar"|"lista", "texto": str}`.
  - `sugerencias_dolor(persona: dict|None) -> list[str]` (≤ 4).
  - `mes_siguiente(hoy: date) -> (inicio_iso, fin_iso)`.
  - `resumen(sprint: dict) -> str` «N campañas · M piezas planeadas · X/Y referentes elegidos».
  - `linea_sprint(sprint: dict, paises: dict) -> str` «1–31 oct · 🇨🇴 español · Hot Sale · imita: Crocs».
  - `marcas_texto(marcas: list|None) -> str` (one per line, `Nombre 123456` when it has a page id).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sprints_tablero.py`:

```python
"""sprints.tablero: funciones puras de las tarjetas y la cabecera del tablero."""
from datetime import date

from sprints import tablero


def _c(**kw):
    base = {"referencias_objetivo": 5, "referencias_listas": 5, "n_videos": 1, "n_imagenes": 1, "ideas": [], "piezas": []}
    base.update(kw)
    return base


def _idea(estado_idea="aprobada", sin_sesion=False, estado=None, revision="pendiente"):
    return {"estado_idea": estado_idea, "sin_sesion": sin_sesion, "estado": estado, "revision": revision}


def test_siguiente_paso_sigue_el_orden_del_trabajo():
    assert tablero.siguiente_paso(_c(referencias_listas=3)) == {"clave": "referentes", "texto": "elegir 2 referentes"}
    assert tablero.siguiente_paso(_c(referencias_listas=4))["texto"] == "elegir 1 referente"
    assert tablero.siguiente_paso(_c())["clave"] == "ideas"
    propuestas = [_idea("propuesta", True), _idea("propuesta", True)]
    assert tablero.siguiente_paso(_c(ideas=propuestas))["texto"] == "aprobar 2 ideas"
    aprobadas = [_idea(sin_sesion=True), _idea(sin_sesion=True)]
    assert tablero.siguiente_paso(_c(ideas=aprobadas))["texto"] == "generar 2 piezas"
    en_curso = [_idea(estado="generando"), _idea(estado="listo")]
    assert tablero.siguiente_paso(_c(ideas=en_curso, piezas=en_curso))["clave"] == "generando"
    con_error = [_idea(estado="error"), _idea(estado="listo", revision="aprobada")]
    assert tablero.siguiente_paso(_c(ideas=con_error, piezas=con_error))["clave"] == "errores"
    listas = [_idea(estado="listo"), _idea(estado="degradada", revision="aprobada")]
    assert tablero.siguiente_paso(_c(ideas=listas, piezas=listas))["texto"] == "revisar 1 pieza"
    hechas = [_idea(estado="listo", revision="aprobada"), _idea(estado="listo", revision="rechazada")]
    assert tablero.siguiente_paso(_c(ideas=hechas, piezas=hechas)) == {"clave": "lista", "texto": "campaña lista"}


def test_las_descartadas_no_cuentan():
    ideas = [_idea("descartada", True), _idea("aprobada", True)]
    assert tablero.siguiente_paso(_c(n_videos=1, n_imagenes=0, ideas=ideas))["texto"] == "generar 1 pieza"


def test_sugerencias_dolor_salen_de_la_persona():
    p = {"resumen": "Comodidad al llegar", "senales_visuales": ["pisos helados", "sofá", "tercera"],
         "extra": {"encaje_producto": "Abriga sin sudar", "evidencia": [{"cita": "mis pies son hielo"}, {"cita": "x"}]}}
    assert tablero.sugerencias_dolor(p) == ["Comodidad al llegar", "Abriga sin sudar", "pisos helados", "sofá"]
    assert tablero.sugerencias_dolor(None) == [] and tablero.sugerencias_dolor({"nombre": "X"}) == []


def test_mes_siguiente():
    assert tablero.mes_siguiente(date(2026, 9, 26)) == ("2026-10-01", "2026-10-31")
    assert tablero.mes_siguiente(date(2026, 12, 3)) == ("2027-01-01", "2027-01-31")
    assert tablero.mes_siguiente(date(2027, 1, 30)) == ("2027-02-01", "2027-02-28")


def test_resumen_y_linea_del_sprint():
    sp = {"inicio": "2026-10-01", "fin": "2026-10-31", "pais": "CO", "idioma": "es",
          "momento": {"nombre": "Hot Sale"}, "marcas": [{"nombre": "Crocs"}, {"nombre": "Hoka", "pagina_id": "555555"}],
          "campanas": [_c(referencias_listas=3, n_videos=5, n_imagenes=5), _c(referencias_listas=7, n_videos=3, n_imagenes=0)]}
    assert tablero.resumen(sp) == "2 campañas · 13 piezas planeadas · 8/10 referentes elegidos"
    assert tablero.resumen({"campanas": []}) == "0 campañas · 0 piezas planeadas · 0/0 referentes elegidos"
    paises = {"CO": {"nombre": "Colombia", "bandera": "🇨🇴"}}
    assert tablero.linea_sprint(sp, paises) == "1–31 oct · 🇨🇴 español · Hot Sale · imita: Crocs, Hoka"
    otro = {"inicio": "2026-10-20", "fin": "2026-11-10", "pais": None, "idioma": "en", "momento": None, "marcas": []}
    assert tablero.linea_sprint(otro, paises) == "20 oct – 10 nov · inglés"


def test_marcas_texto():
    assert tablero.marcas_texto([{"nombre": "Crocs"}, {"nombre": "Hoka", "pagina_id": "555555"}]) == "Crocs\nHoka 555555"
    assert tablero.marcas_texto(None) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero.py`
Expected: FAIL — `ImportError: cannot import name 'tablero'`.

- [ ] **Step 3: Implement `sprints/tablero.py`**

```python
"""
El tablero de un sprint (spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md):
lo que muestran las tarjetas de campaña, la cabecera y el panel, calculado sin
Flask ni base de datos a partir de los dicts de sprints.datos.
"""
from datetime import date, timedelta

from sprints import datos

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _plural(n, singular, plural=None):
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def siguiente_paso(c):
    """Lo próximo que hay que hacer en una campaña según su estado real:
    elegir referentes → aprobar/proponer ideas → generar → revisar."""
    faltan = int(c.get("referencias_objetivo") or 1) - int(c.get("referencias_listas") or 0)
    if faltan > 0:
        return {"clave": "referentes", "texto": f"elegir {_plural(faltan, 'referente')}"}
    vivas = [i for i in c.get("ideas") or [] if i.get("estado_idea") != "descartada"]
    propuestas = [i for i in vivas if i.get("estado_idea") == "propuesta"]
    if propuestas:
        return {"clave": "aprobar", "texto": f"aprobar {_plural(len(propuestas), 'idea')}"}
    if len(vivas) < int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0):
        return {"clave": "ideas", "texto": "proponer ideas"}
    por_generar = [i for i in vivas if i.get("estado_idea") == "aprobada" and i.get("sin_sesion")]
    if por_generar:
        return {"clave": "generar", "texto": f"generar {_plural(len(por_generar), 'pieza')}"}
    piezas = c.get("piezas") or []
    en_curso = [p for p in piezas if p.get("estado") not in datos._PIEZA_TERMINADA and p.get("estado") != "error"]
    if en_curso:
        return {"clave": "generando", "texto": f"esperar {_plural(len(en_curso), 'pieza')} en producción"}
    errores = [p for p in piezas if p.get("estado") == "error"]
    if errores:
        return {"clave": "errores", "texto": f"reintentar {_plural(len(errores), 'pieza')} con error"}
    por_revisar = [p for p in piezas if p.get("estado") in datos._PIEZA_TERMINADA
                   and p.get("revision") in (None, "", "pendiente")]
    if por_revisar:
        return {"clave": "revisar", "texto": f"revisar {_plural(len(por_revisar), 'pieza')}"}
    return {"clave": "lista", "texto": "campaña lista"}


def sugerencias_dolor(persona):
    """Hasta 4 frases de la persona para el campo «dolor o deseo»: su deseo
    (resumen), cómo le sirve el producto, sus situaciones y lo que dijo."""
    if not persona:
        return []
    ex = persona.get("extra") or {}
    candidatas = [persona.get("resumen"), ex.get("encaje_producto")]
    candidatas += list(persona.get("senales_visuales") or [])[:2]
    candidatas += [e.get("cita") for e in ex.get("evidencia") or [] if isinstance(e, dict)][:2]
    salida = []
    for x in candidatas:
        x = (x or "").strip()[:120] if isinstance(x, str) else ""
        if x and x not in salida:
            salida.append(x)
    return salida[:4]


def mes_siguiente(hoy):
    """(inicio, fin) ISO del mes que viene: lo que «+ Nuevo sprint» propone."""
    primero = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1)
    ultimo = (primero + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return primero.isoformat(), ultimo.isoformat()


def resumen(sp):
    cs = sp.get("campanas") or []
    planeadas = sum(int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0) for c in cs)
    objetivo = sum(int(c.get("referencias_objetivo") or 0) for c in cs)
    elegidos = sum(min(int(c.get("referencias_listas") or 0), int(c.get("referencias_objetivo") or 0)) for c in cs)
    return f"{_plural(len(cs), 'campaña')} · {planeadas} piezas planeadas · {elegidos}/{objetivo} referentes elegidos"


def _fechas_cortas(inicio, fin):
    i, f = date.fromisoformat(inicio), date.fromisoformat(fin)
    if (i.year, i.month) == (f.year, f.month):
        return f"{i.day}–{f.day} {MESES[i.month - 1]}"
    return f"{i.day} {MESES[i.month - 1]} – {f.day} {MESES[f.month - 1]}"


def linea_sprint(sp, paises):
    """«1–31 oct · 🇨🇴 español · Hot Sale · imita: Crocs, Hoka» (cabecera del tablero)."""
    partes = [_fechas_cortas(sp["inicio"], sp["fin"])]
    bandera = ((paises or {}).get(sp.get("pais") or "") or {}).get("bandera") or (sp.get("pais") or "")
    idioma = datos.IDIOMAS_NOMBRE.get(sp.get("idioma") or "es", sp.get("idioma"))
    partes.append(f"{bandera} {idioma}".strip())
    if (sp.get("momento") or {}).get("nombre"):
        partes.append(sp["momento"]["nombre"])
    if sp.get("marcas"):
        partes.append("imita: " + ", ".join(m["nombre"] for m in sp["marcas"]))
    return " · ".join(partes)


def marcas_texto(marcas):
    """Lista de marcas -> el texto que las vuelve a producir en `normalizar_marcas`."""
    return "\n".join(m["nombre"] + (f" {m['pagina_id']}" if m.get("pagina_id") else "") for m in marcas or [])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sprints/tablero.py tests/test_sprints_tablero.py
git commit -m "Sprints tablero: siguiente paso, resumen y cabecera (funciones puras)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: «+ Nuevo sprint» corto

**Files:**
- Modify: `sprints/rutas.py` (`contexto`, `crear`, delete `_sprint_recien_creado`; new helpers `_paises`, `_momento_desde`)
- Rewrite: `templates/_tab_sprints.html`
- Test: `tests/test_sprints_tablero_rutas.py` (create), `tests/test_rutas_sprints.py` (adapt)

**Interfaces:**
- Consumes: `datos.crear_sprint(..., pais, idioma, marcas, momento)` (Task 2), `tablero.mes_siguiente` (Task 5), `calendario.presets(pais, anio)`, `fe_tipos.PAISES`.
- Produces:
  - `rutas._paises() -> list[{"codigo","nombre","bandera","idioma"}]`.
  - `rutas._momento_desde(cliente, valor, pais, inicio) -> dict|None` — `valor`: `""` (none), `"propio:<texto>"`, or a preset `clave`; raises `datos.ErrorDatos` for an unknown clave.
  - `contexto(cliente)` keys: `sprints_lista, pais_calendario, presets_temporadas, calendario_fallback, paises_sprint, idiomas_sprint, inicio_defecto, fin_defecto, hoy`.
  - `POST /cliente/<c>/sprints/nuevo` accepts `nombre, inicio, fin, pais, idioma, momento, momento_texto, marcas` (+ optional legacy `campanas_json`), allows zero campaigns, redirects to the board `sprints.ver`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sprints_tablero_rutas.py`:

```python
"""Rutas del tablero de Sprints (spec 2026-09-26). Fixture `app` de
test_rutas_sprints: sesión admin, catálogo falso con espejo_led y
division_bano, encolar monkeypatcheado."""
import json

import pytest

from tests.test_rutas_sprints import app  # noqa: F401


def _sprint(datos, **kw):
    return datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", **kw)


# ------------------------------------------------------ «+ Nuevo sprint» ---

def test_contexto_de_la_pestana(app):
    from datetime import date
    from sprints import datos, rutas, tablero
    ctx = rutas.contexto("acme")
    assert ctx["pais_calendario"] == "CO" and any(p["clave"] == "navidad" for p in ctx["presets_temporadas"])
    assert "CO" in [p["codigo"] for p in ctx["paises_sprint"]] and ctx["idiomas_sprint"]["en"] == "inglés"
    assert (ctx["inicio_defecto"], ctx["fin_defecto"]) == tablero.mes_siguiente(date.today())
    assert datos.personas("acme") == []                     # ya no se crean personas genéricas


def test_pestana_muestra_el_formulario_corto(app):
    html = app["c"].get("/cliente/acme").data.decode()
    tab = html[html.index('id="tab-sprints"'):]
    for frag in ('name="nombre"', 'name="inicio"', 'name="pais"', 'name="idioma"', 'name="momento"',
                 'name="marcas"', "Crear y armar campañas"):
        assert frag in tab, frag
    for viejo in ("campanas_json", "modal-agregar-campana", "sprint-paso", "Siguiente: la matriz"):
        assert viejo not in html, viejo


def test_crear_sprint_corto_abre_su_tablero(app):
    from sprints import calendario, datos
    clave = calendario.presets("MX", 2026)[0]["clave"]
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={
        "nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31", "pais": "MX", "idioma": "es",
        "momento": clave, "marcas": "Crocs\nSkechers 1234567"})
    s = datos.sprints("acme")[0]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{s['id']}")
    assert s["pais"] == "MX" and s["campanas_total"] == 0 and s["momento"]["clave"] == clave
    assert s["marcas"] == [{"nombre": "Crocs"}, {"nombre": "Skechers", "pagina_id": "1234567"}]


def test_crear_sprint_con_momento_propio(app):
    from sprints import datos
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                        "momento": "propio", "momento_texto": "Lanzamiento"})
    s = datos.sprints("acme")[0]
    assert s["momento"] == {"nombre": "Lanzamiento"} and s["pais"] == "CO" and s["idioma"] == "es"


@pytest.mark.parametrize("malo", [{"pais": "Colombia"}, {"momento": "no_existe"}, {"fin": "2026-09-01"}])
def test_crear_sprint_invalido_no_crea_nada(app, malo):
    from sprints import datos
    datos_form = {"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31", **malo}
    r = app["c"].post("/cliente/acme/sprints/nuevo", data=datos_form)
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    assert datos.sprints("acme", incluir_archivados=True) == []
```

In `tests/test_rutas_sprints.py`:
- Replace `test_contexto_trae_lo_que_usa_la_pestana` with:

```python
def test_contexto_trae_lo_que_usa_la_pestana(app):
    from sprints import datos, rutas
    datos.crear_persona("acme", "Premium")
    ctx = rutas.contexto("acme")
    assert ctx["sprints_lista"] == [] and ctx["pais_calendario"] == "CO"
    assert any(p["clave"] == "navidad" for p in ctx["presets_temporadas"])
    assert [p["nombre"] for p in datos.personas("acme")] == ["Premium"]      # sin genéricas (2026-09-26)
```

- Replace `test_contexto_fuera_de_una_peticion_no_revienta` body with `from sprints import rutas` / `assert rutas.contexto("acme")["inicio_defecto"]`.
- Delete `test_crear_sprint_limpia_el_borrador_del_asistente_una_sola_vez` and `test_crear_sprint_fallido_no_limpia_el_borrador` (the wizard draft no longer exists).
- In `test_crear_sprint_rechaza_productos_ajenos_y_cantidades_cero` (renamed in Task 2) delete the `"[]"` post and its assertion (zero campaigns is now valid).
- Replace `test_pestana_sprints_se_renderiza` with:

```python
def test_pestana_sprints_se_renderiza(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'id="tab-sprints"' in html and 'data-tab="sprints"' in html
    assert "Octubre" in html and "Nuevo sprint" in html and "Crear y armar campañas" in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_base_visual.py`
Expected: FAIL — `KeyError: 'paises_sprint'`, wizard markup still present.

- [ ] **Step 3: Implement the routes**

In `sprints/rutas.py`:

1. Imports: add `tablero` to `from sprints import archivos, calendario, datos, …` (keep alphabetical: `…, revision as revision_mod, tablero`).

2. Delete `_sprint_recien_creado` and, in `contexto`, everything the old wizard used. New `contexto`:

```python
def _paises():
    return [{"codigo": codigo, "nombre": p["nombre"], "bandera": p["bandera"], "idioma": p["idioma"]}
            for codigo, p in fe_tipos.PAISES.items()]


def contexto(cliente):
    """Lo que necesita _tab_sprints.html. Se llama desde dashboard.ver_cliente."""
    lista = []
    for sp in datos.sprints(cliente):
        sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
        lista.append(sp)
    pais = proyectos.pais(cliente)
    inicio, fin = tablero.mes_siguiente(date.today())
    return {
        "sprints_lista": lista,
        "pais_calendario": pais,
        "presets_temporadas": calendario.presets(pais, int(inicio[:4])),
        "calendario_fallback": not calendario.tiene_calendario(pais),
        "paises_sprint": _paises(),
        "idiomas_sprint": datos.IDIOMAS_NOMBRE,
        "inicio_defecto": inicio,
        "fin_defecto": fin,
        "hoy": date.today().isoformat(),
    }
```

Remove now-unused names only if nothing else in the file uses them (`DURACION_ESTIMADO_S`, `N_REFERENCIAS_ESTIMADO`, `flowplus_modelos`, `has_request_context`, `session`): grep the file before deleting each one.

3. Add after `_campana_o_404`:

```python
def _momento_desde(cliente, valor, pais, inicio):
    """Valor del selector «Momento del mes» -> lo que guarda `datos`: "" es
    ninguno, "propio:<texto>" es uno escrito a mano y cualquier otra cosa es
    la clave de un preset del calendario del país (año del inicio del sprint)."""
    valor = (valor or "").strip() if isinstance(valor, str) else ""
    if not valor:
        return None
    if valor.startswith("propio:"):
        return valor[len("propio:"):]
    try:
        anio = int(str(inicio)[:4])
    except ValueError:
        anio = date.today().year
    p = next((x for x in calendario.presets(pais or proyectos.pais(cliente), anio) if x["clave"] == valor), None)
    if not p:
        raise datos.ErrorDatos("Ese momento del calendario no existe.")
    return {k: p[k] for k in ("clave", "nombre", "contexto", "inicio", "fin", "mood_visual")}
```

4. Replace `crear` with:

```python
@bp.post("/nuevo")
def crear(cliente):
    """Formulario corto de la pestaña: el sprint se arma después en su tablero.
    `campanas_json` sigue aceptándose (scripts y pruebas) pero ya no es obligatorio."""
    try:
        campanas = _validar_campanas(cliente, _campanas_desde_form())
        pais = request.form.get("pais") or proyectos.pais(cliente)
        inicio = request.form.get("inicio")
        momento = request.form.get("momento") or ""
        if momento == "propio":
            momento = "propio:" + (request.form.get("momento_texto") or "")
        sid = datos.crear_sprint(cliente, request.form.get("nombre"), inicio, request.form.get("fin"),
                                 destinos=[d for d in request.form.getlist("destinos") if d],
                                 referencias_objetivo_defecto=request.form.get("referencias_objetivo") or 5,
                                 notas=request.form.get("notas"), pais=pais,
                                 idioma=request.form.get("idioma") or "es", marcas=request.form.get("marcas") or "",
                                 momento=_momento_desde(cliente, momento, pais, inicio))
        try:
            for c in campanas:
                datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                      c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        except datos.ErrorDatos:
            datos.archivar_sprint(cliente, sid)
            raise
        estado.recalcular(cliente, sid)
        flash(f"Sprint creado con {len(campanas)} campaña(s)." if campanas
              else "Sprint creado. Ahora arma sus campañas con «+ Campaña».", "ok")
        return _volver(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)
```

- [ ] **Step 4: Rewrite `templates/_tab_sprints.html`**

Replace the whole file with:

```html
{% from "_sprint_macros.html" import anillo, chip_estado %}
{# Pestaña Sprints. Contexto de sprints.rutas.contexto(cliente): sprints_lista,
   pais_calendario, presets_temporadas, paises_sprint, idiomas_sprint,
   inicio_defecto, fin_defecto. Aquí solo se crea el sprint con lo mínimo; las
   campañas se arman en su tablero (sprint_detalle.html). #}
<div class="panel-cabecera">
  <div>
    <h2>Sprints</h2>
    <p class="panel-cabecera-desc">Un sprint es el plan de contenido de un mes: pones el mes y el mercado, y en su tablero armas una campaña por persona y producto con los anuncios que va a seguir. Nada se genera sin tu aprobación y sin ver el costo antes.</p>
  </div>
  <div class="panel-cabecera-acciones">
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-sprint">+ Nuevo sprint</button>
  </div>
</div>

<details class="swap-card sprint-nuevo" id="nuevo-sprint">
  <summary class="swap-card-resumen">Nuevo sprint</summary>
  <form method="post" action="{{ url_for('sprints.crear', cliente=cliente) }}" class="sprint-nuevo-form">
    <label>Nombre
      <input name="nombre" required maxlength="200" placeholder="Octubre"></label>
    <label>Inicio
      <input type="date" name="inicio" required value="{{ inicio_defecto }}"></label>
    <label>Fin
      <input type="date" name="fin" required value="{{ fin_defecto }}"></label>
    <label>País
      <select name="pais">
        {% for p in paises_sprint %}<option value="{{ p.codigo }}" {% if p.codigo == pais_calendario %}selected{% endif %}>{{ p.bandera }} {{ p.nombre }}</option>{% endfor %}
      </select></label>
    <label>Idioma de los textos
      <select name="idioma">
        {% for cod, nombre in idiomas_sprint.items() %}<option value="{{ cod }}" {% if cod == 'es' %}selected{% endif %}>{{ nombre }}</option>{% endfor %}
      </select></label>
    <label>Momento del mes <small class="vacio">(opcional)</small>
      <select name="momento" data-momento>
        <option value="">Ninguno</option>
        {% for p in presets_temporadas %}<option value="{{ p.clave }}">{{ p.nombre }} ({{ p.inicio[5:] }} → {{ p.fin[5:] }})</option>{% endfor %}
        <option value="propio">Otro (escríbelo)…</option>
      </select></label>
    <label data-momento-propio hidden>Tu momento
      <input name="momento_texto" maxlength="120" placeholder="Lanzamiento de la colección"></label>
    <label class="sprint-nuevo-ancho">Marcas a imitar <small class="vacio">(opcional: una por línea; si tienes el link de su Ad Library, pégalo al lado)</small>
      <textarea name="marcas" rows="2" placeholder="Crocs&#10;Skechers https://www.facebook.com/ads/library/?view_all_page_id=…"></textarea></label>
    <div class="sprint-nuevo-ancho"><button type="submit" class="btn-generar">Crear y armar campañas →</button></div>
  </form>
</details>

<div class="sprints-lista">
  {% for sp in sprints_lista %}
  <a class="swap-card sprint-card" href="{{ url_for('sprints.ver', cliente=cliente, sid=sp.id) }}">
    {{ anillo(sp.progreso.porcentaje) }}
    <div>
      <strong>{{ sp.nombre }}</strong> {{ chip_estado(sp.estado) }}
      <br><small class="vacio">{{ sp.inicio }} → {{ sp.fin }} · {{ sp.campanas_total }} campaña(s) · {{ sp.piezas_planeadas }} piezas · {{ sp.progreso.texto }}</small>
    </div>
  </a>
  {% else %}
  <div class="estado-vacio">
    <p class="estado-vacio-titulo">Todavía no hay sprints</p>
    <p class="estado-vacio-texto">Crea el primero con «+ Nuevo sprint»: pones el mes y el mercado, y agregas sus campañas en el tablero.</p>
  </div>
  {% endfor %}
</div>

<script>
  (function () {
    // «Otro (escríbelo)…» muestra el campo del momento propio.
    var sel = document.querySelector('#nuevo-sprint [data-momento]');
    var propio = document.querySelector('#nuevo-sprint [data-momento-propio]');
    if (!sel || !propio) return;
    function mostrar() { propio.hidden = sel.value !== 'propio'; }
    sel.addEventListener('change', mostrar);
    mostrar();
  })();
</script>
```

- [ ] **Step 5: Add the CSS for the form**

At the very END of `static/style.css` append (Task 7 and Task 8 append to this same block):

```css
/* =====================================================================
   Tablero de Sprints (2026-09-26) — spec
   docs/superpowers/specs/2026-09-26-sprints-tablero-design.md.
   Solo variables de :root (el modo oscuro las redefine).
   ===================================================================== */
.sprint-nuevo-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); gap: .8rem 1rem; margin-top: .8rem; }
.sprint-nuevo-ancho { grid-column: 1 / -1; }
.sprint-nuevo-form label[hidden] { display: none; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_base_visual.py tests/test_movil.py tests/test_sprints_temporada_opcional.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add sprints/rutas.py templates/_tab_sprints.html static/style.css tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py
git commit -m "Sprints tablero: «+ Nuevo sprint» es un formulario corto (mes, mercado, momento y marcas)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: El tablero del sprint

**Files:**
- Modify: `sprints/rutas.py` (`ver`, `campana_agregar`, `persona_crear`; new `sprint_campo`, `campana_tarjeta`, helpers `_productos_planos`, `_campana_tablero`, `_aviso_identica`, `_nueva_desde_json`)
- Modify: `sprints/datos.py` (delete `combinaciones`)
- Rewrite: `templates/sprint_detalle.html`
- Create: `templates/_sprint_tarjeta.html`
- Modify: `static/style.css` (append to the Tablero block)
- Test: `tests/test_sprints_tablero_rutas.py`, `tests/test_rutas_sprints.py` (`test_detalle_progreso_listo_y_campanas`), `tests/test_sprints_temporada_opcional.py` (`test_pagina_del_sprint_muestra_sin_temporada_y_no_la_exige`)

**Interfaces:**
- Consumes: Tasks 2, 5, 6.
- Produces:
  - `rutas._productos_planos(cliente) -> list[dict]` (= `catalogo_productos.listar(cliente, "producto")`: one entry per variant, `id` like `horiginal/beige`, `nombre` like «HOriginal — Beige», `representativa_url`).
  - `rutas._campana_tablero(cliente, sp, c, productos_por_id) -> c` adds `progreso`, `siguiente`, `efectivos`, `producto`, `referencias_lista`, `consciencia_nombre`.
  - `rutas._aviso_identica(cliente, cid) -> str|None`.
  - `GET /cliente/<c>/sprints/<sid>` (board; `?panel=<cid>` sets `data-panel-inicial`).
  - `POST /cliente/<c>/sprints/<sid>/campo` JSON `{campo, valor}` for `nombre|inicio|fin|pais|idioma|marcas|momento` → `{ok, linea, resumen}` or `{ok: false, error}` 400.
  - `POST /cliente/<c>/sprints/<sid>/campanas` JSON `{persona_id, catalogo_id}` → `{ok, cid, aviso, url}`; the old form post still works and redirects to `?panel=<cid>`.
  - `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/tarjeta` → `_sprint_tarjeta.html` fragment.
  - `POST /cliente/<c>/sprints/personas` answers JSON `{ok, id, nombre}` to fetch requests.
  - Template contract of `_sprint_tarjeta.html`: variables `cliente`, `sprint`, `c` (after `_campana_tablero`); root `<article class="tablero-tarjeta" id="campana-<cid>" data-cid="<cid>">`.
  - Board DOM contract used by Task 8: `#tablero-grid`, `#tablero-panel` (`data-panel-inicial`, `data-url-base` = board URL), `#tablero-panel-cuerpo`, `#tablero-fondo`, `<template id="tablero-nueva">`, global JS helpers inside the board script: `abrir(cid)`, `abrirNueva()`, `cerrar()`, `refrescarTarjeta(cid)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_tablero_rutas.py`:

```python
# ------------------------------------------------------------- tablero ---

def _campana(datos, sid, **kw):
    pid = kw.pop("persona_id", None) or datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    return datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1, **kw)


def test_tablero_muestra_tarjetas_resumen_y_siguiente_paso(app):
    from sprints import datos
    sid = _sprint(datos, pais="CO", marcas="Crocs", momento="Hot Sale")
    cid = _campana(datos, sid, consciencia="consciente_del_problema", dolor="pies fríos")
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    for frag in (f'id="campana-{cid}"', "Campaña 1", "Premium", "Espejo LED", "consciente del problema",
                 "«pies fríos»", "Siguiente: elegir 5 referentes", "1 campaña · 3 piezas planeadas · 0/5 referentes elegidos",
                 "1–31 oct · 🇨🇴 español · Hot Sale · imita: Crocs", 'id="tablero-panel"', 'id="tablero-nueva"'):
        assert frag in html, frag
    assert "-ajax" not in html and 'name="temporada_id"' not in html


def test_tablero_de_un_sprint_viejo_abre(app):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = _sprint(datos)
    datos.agregar_campana("acme", sid, datos.crear_persona("acme", "Premium"), "espejo_led", tid, 2, 1)
    r = app["c"].get(f"/cliente/acme/sprints/{sid}")
    assert r.status_code == 200 and ">None<" not in r.data.decode()


def test_tablero_sin_campanas_invita_a_crear_una(app):
    from sprints import datos
    html = app["c"].get(f"/cliente/acme/sprints/{_sprint(datos)}").data.decode()
    assert "Este sprint todavía no tiene campañas" in html and "data-nueva-campana" in html


def test_tablero_abre_el_panel_pedido(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}?panel={cid}").data.decode()
    assert f'data-panel-inicial="{cid}"' in html


def _json(c, url, cuerpo):
    return c.post(url, data=json.dumps(cuerpo), content_type="application/json",
                  headers={"X-Requested-With": "fetch"})


def test_campo_del_sprint_guarda_y_valida(app):
    from sprints import datos
    sid = _sprint(datos)
    url = f"/cliente/acme/sprints/{sid}/campo"
    j = _json(app["c"], url, {"campo": "pais", "valor": "MX"}).get_json()
    assert j["ok"] and "🇲🇽" in j["linea"] and datos.sprint("acme", sid)["pais"] == "MX"
    assert _json(app["c"], url, {"campo": "momento", "valor": "propio:Hot Sale"}).get_json()["ok"]
    assert datos.sprint("acme", sid)["momento"] == {"nombre": "Hot Sale"}
    assert _json(app["c"], url, {"campo": "momento", "valor": "navidad"}).get_json()["ok"]
    assert datos.sprint("acme", sid)["momento"]["clave"] == "navidad"
    assert _json(app["c"], url, {"campo": "marcas", "valor": "Crocs"}).get_json()["ok"]
    for malo in ({"campo": "idioma", "valor": "xx"}, {"campo": "nombre", "valor": ""}, {"campo": "estado", "valor": "x"},
                 {"campo": "pais", "valor": {"x": 1}}, {"campo": "fin", "valor": "2026-09-01"}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert _json(app["c"], "/cliente/acme/sprints/999/campo", {"campo": "pais", "valor": "CO"}).status_code == 404


def test_agregar_campana_json_crea_con_valores_por_defecto_y_avisa_repetida(app):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    url = f"/cliente/acme/sprints/{sid}/campanas"
    j = _json(app["c"], url, {"persona_id": pid, "catalogo_id": "espejo_led"}).get_json()
    c = datos.campana("acme", j["cid"])
    assert j["ok"] and j["aviso"] is None and j["url"].endswith(f"/sprints/{sid}?panel={j['cid']}")
    assert (c["n_videos"], c["n_imagenes"], c["funnel"]) == (5, 5, "tof")
    j2 = _json(app["c"], url, {"persona_id": pid, "catalogo_id": "espejo_led"}).get_json()
    assert j2["ok"] and "campaña 1" in j2["aviso"]


@pytest.mark.parametrize("cuerpo,error", [({"catalogo_id": "espejo_led"}, "Elige una persona"),
                                          ({"persona_id": "PID", "catalogo_id": "no_existe"}, "Elige un producto")])
def test_agregar_campana_json_valida(app, cuerpo, error):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    cuerpo = {k: (pid if v == "PID" else v) for k, v in cuerpo.items()}
    r = _json(app["c"], f"/cliente/acme/sprints/{sid}/campanas", cuerpo)
    assert r.status_code == 400 and error in r.get_json()["error"] and datos.campanas("acme", sid) == []


def test_persona_rapida_responde_json(app):
    from sprints import datos
    r = app["c"].post("/cliente/acme/sprints/personas", data={"nombre": "Mamá práctica", "resumen": "Quiere ahorrar tiempo"},
                      headers={"X-Requested-With": "fetch"})
    j = r.get_json()
    p = datos.persona("acme", j["id"])
    assert j["ok"] and j["nombre"] == "Mamá práctica" and p["origen"] == "manual" and p["resumen"] == "Quiere ahorrar tiempo"
    r = app["c"].post("/cliente/acme/sprints/personas", data={"nombre": ""}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and not r.get_json()["ok"]


def test_tarjeta_de_una_campana(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/tarjeta").data.decode()
    assert html.lstrip().startswith("<article") and f'id="campana-{cid}"' in html
    otro = _sprint(datos)
    assert app["c"].get(f"/cliente/acme/sprints/{otro}/campanas/{cid}/tarjeta").status_code == 404
```

In `tests/test_rutas_sprints.py::test_detalle_progreso_listo_y_campanas` change the first assertion line to
`assert r.status_code == 200 and b"Espejo LED" in r.data and b"Premium" in r.data` (the board no longer shows the old temporada).

In `tests/test_sprints_temporada_opcional.py` replace `test_pagina_del_sprint_muestra_sin_temporada_y_no_la_exige` with:

```python
def test_tablero_con_campana_sin_temporada(app):
    from sprints import datos
    pid, sid = _sprint(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}").data.decode()
    assert "Campaña 1" in html and ">None<" not in html and 'name="temporada_id"' not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py`
Expected: FAIL — old template, missing routes.

- [ ] **Step 3: Implement the routes**

In `sprints/rutas.py`:

1. After `_momento_desde` add:

```python
# ------------------------------------------------------------ tablero ---

CAMPOS_SPRINT = ("nombre", "inicio", "fin", "pais", "idioma", "marcas", "momento")


def _productos_planos(cliente):
    """Una opción por variante («HOriginal — Beige»): la lista del catálogo tal cual."""
    return catalogo_productos.listar(cliente, "producto")


def _campana_tablero(cliente, sp, c, productos_por_id):
    """Lo que la tarjeta y el panel muestran de una campaña."""
    c["progreso"] = progreso.progreso_campana(c)
    c["siguiente"] = tablero.siguiente_paso(c)
    c["efectivos"] = datos.efectivos(sp, c)
    c["producto"] = productos_por_id.get(c["catalogo_id"])
    c["referencias_lista"] = datos.referencias(cliente, c["id"])
    c["consciencia_nombre"] = doctrina.CONSCIENCIAS_NOMBRE.get(c.get("consciencia") or "")
    return c


def _aviso_identica(cliente, cid):
    iguales = datos.campanas_identicas(cliente, cid)
    if not iguales:
        return None
    numeros = ", ".join(str(n) for n in iguales)
    return (f"Ojo: la campaña {numeros} tiene la misma persona, producto, etapa, consciencia y formato. "
            "Si es a propósito, cambia algo para que no salgan piezas repetidas.")


def _json_cuerpo():
    cuerpo = request.get_json(silent=True)
    return cuerpo if isinstance(cuerpo, dict) else None


def _valor_simple(valor):
    """Lo que puede llegar como valor de un campo: texto, número, lista o nada."""
    return valor is None or (isinstance(valor, (str, int, list)) and not isinstance(valor, bool))
```

2. Replace `ver` with:

```python
@bp.get("/<int:sid>")
def ver(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    productos = _productos_planos(cliente)
    por_id = {p["id"]: p for p in productos}
    for c in sp["campanas"]:
        _campana_tablero(cliente, sp, c, por_id)
    sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
    pais = sp.get("pais") or proyectos.pais(cliente)
    momento = sp.get("momento") or {}
    return render_template("sprint_detalle.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, linea=tablero.linea_sprint(sp, fe_tipos.PAISES), resumen=tablero.resumen(sp),
                           productos_sprint=productos, personas_sprint=datos.personas(cliente), paises=_paises(),
                           idiomas=datos.IDIOMAS_NOMBRE, presets=calendario.presets(pais, int(sp["inicio"][:4])),
                           momento_valor=momento.get("clave") or ("propio" if momento else ""),
                           marcas_texto=tablero.marcas_texto(sp.get("marcas")),
                           panel_inicial=request.args.get("panel", type=int),
                           lote=produccion.progreso(cliente, sid)["sprint"], **_contexto_lote(cliente))
```

3. New routes (after `progreso_json`):

```python
@bp.post("/<int:sid>/campo")
def sprint_campo(cliente, sid):
    """Autoguardado de un dato de la cabecera del tablero."""
    sp = _sprint_o_404(cliente, sid)
    cuerpo = _json_cuerpo()
    if not cuerpo or cuerpo.get("campo") not in CAMPOS_SPRINT or not _valor_simple(cuerpo.get("valor")):
        return jsonify({"ok": False, "error": "Ese dato no se puede editar aquí."}), 400
    campo, valor = cuerpo["campo"], cuerpo.get("valor")
    try:
        if campo == "momento":
            valor = _momento_desde(cliente, valor, sp.get("pais"), sp["inicio"])
        datos.actualizar_sprint(cliente, sid, **{campo: valor})
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    nuevo = datos.sprint(cliente, sid, con_eventos=False)
    return jsonify({"ok": True, "linea": tablero.linea_sprint(nuevo, fe_tipos.PAISES), "resumen": tablero.resumen(nuevo)})


@bp.get("/<int:sid>/campanas/<int:cid>/tarjeta")
def campana_tarjeta(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = next((x for x in sp["campanas"] if x["id"] == cid), None)
    if not c:
        abort(404)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in _productos_planos(cliente)})
    return render_template("_sprint_tarjeta.html", cliente=cliente, sprint=sp, c=c)
```

4. Replace `campana_agregar` with:

```python
def _nueva_desde_json(cliente, cuerpo):
    try:
        persona_id = int(cuerpo.get("persona_id") or 0)
    except (TypeError, ValueError):
        persona_id = 0
    if not persona_id or not datos.persona(cliente, persona_id):
        raise datos.ErrorDatos("Elige una persona (o crea una rápida).")
    catalogo_id = str(cuerpo.get("catalogo_id") or "").strip()
    if catalogo_id not in {p["id"] for p in _productos_planos(cliente)}:
        raise datos.ErrorDatos("Elige un producto del catálogo.")
    return {"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": None, "n_videos": 5,
            "n_imagenes": 5, "referencias_objetivo": None, "funnel": "tof"}


@bp.post("/<int:sid>/campanas")
def campana_agregar(cliente, sid):
    """«+ Campaña» del tablero (JSON: persona y producto; lo demás con valores
    por defecto que se cambian en el panel) o el formulario clásico."""
    _sprint_o_404(cliente, sid)
    cuerpo = _json_cuerpo()
    es_json = cuerpo is not None or _quiere_json()
    try:
        if cuerpo is not None:
            c = _nueva_desde_json(cliente, cuerpo)
        else:
            lista = _validar_campanas(cliente, _campanas_desde_form())
            if not lista:
                raise datos.ErrorDatos("Faltan los datos de la campaña.")
            c = lista[0]
        cid = datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                    c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"], funnel=c["funnel"])
        estado.recalcular(cliente, sid)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, sid)
    aviso = _aviso_identica(cliente, cid)
    url = url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid)
    if es_json:
        return jsonify({"ok": True, "cid": cid, "aviso": aviso, "url": url})
    flash("Campaña agregada." + (f" {aviso}" if aviso else ""), "ok")
    return redirect(url)
```

5. Replace `persona_crear` with:

```python
@bp.post("/personas")
def persona_crear(cliente):
    """Crea una persona manual. Desde el panel («Crear persona rápida») llega
    por fetch con nombre y una línea, y responde JSON."""
    try:
        pid = datos.crear_persona(cliente, request.form.get("nombre"), **_campos_persona())
    except datos.ErrorDatos as e:
        if _quiere_json():
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente)
    if _quiere_json():
        return jsonify({"ok": True, "id": pid, "nombre": datos.persona(cliente, pid)["nombre"]})
    flash("Persona creada.", "ok")
    return _volver(cliente)
```

6. In `sprints/datos.py` delete the function `combinaciones` (its only user was the old `ver`). Grep the repo (`grep -rn "combinaciones(" --include="*.py" .` excluding `.claude/worktrees`) to confirm no other user.

- [ ] **Step 4: Create `templates/_sprint_tarjeta.html`**

```html
{# Tarjeta de una campaña en el tablero (sprint_detalle.html). Contexto: cliente,
   sprint y c ya pasado por rutas._campana_tablero (progreso, siguiente,
   efectivos, producto, referencias_lista, consciencia_nombre). La tarjeta
   entera abre el panel (JS de sprint_detalle.html). #}
{% set objetivo = c.referencias_objetivo or 1 %}
{% set mini = c.referencias_lista[:objetivo] %}
<article class="tablero-tarjeta" id="campana-{{ c.id }}" data-cid="{{ c.id }}" tabindex="0" role="button"
         aria-label="Abrir la campaña {{ c.orden + 1 }}">
  <div class="tablero-tarjeta-cab">
    <span class="chip-etapa">{{ (c.funnel or 'tof') | upper }}</span>
    <small class="vacio">Campaña {{ c.orden + 1 }}</small>
  </div>
  <p class="tablero-tarjeta-quien"><strong>{{ c.persona_nombre }}</strong> · {{ c.producto.nombre if c.producto else c.catalogo_id }}</p>
  <p class="tablero-tarjeta-enfoque vacio">{{ c.consciencia_nombre or "consciencia sin definir" }}{% if c.dolor %} · «{{ c.dolor }}»{% endif %}</p>
  <div class="tablero-miniaturas" aria-hidden="true">
    {% for r in mini %}<img src="{{ r.frame_url or r.url }}" alt="" loading="lazy">{% endfor %}
    {% for _ in range(objetivo - (mini | length)) %}<span class="tablero-miniatura-vacia"></span>{% endfor %}
  </div>
  <p class="tablero-tarjeta-cantidades">{{ c.referencias_listas }}/{{ c.referencias_objetivo }} referentes · {{ c.n_videos }} videos · {{ c.n_imagenes }} imágenes</p>
  <p class="tablero-siguiente">Siguiente: {{ c.siguiente.texto }} →</p>
</article>
```

- [ ] **Step 5: Rewrite `templates/sprint_detalle.html`**

Replace the whole file with:

```html
{% extends "base.html" %}
{% from "_sprint_macros.html" import chip_estado %}
{% block title %}{{ sprint.nombre }} · Sprints{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}
{# Tablero del sprint (spec 2026-09-26): cabecera editable, una tarjeta por
   campaña y el panel lateral de la campaña (fragmento de
   sprints.campana_panel, cargado por fetch). Todo el JS del panel vive aquí:
   los <script> de un fragmento cargado por fetch nunca corren. #}

{% set pendientes_sprint = sprint.campanas | map(attribute='ideas') | sum(start=[]) | rejectattr('estado_idea', 'equalto', 'descartada') | selectattr('estado_idea', 'equalto', 'aprobada') | selectattr('sin_sesion') | list %}
<div class="panel-cabecera tablero-cabecera">
  <div>
    <h1 class="tablero-titulo">{{ sprint.nombre }} {{ chip_estado(sprint.estado) }}</h1>
    <p class="panel-cabecera-desc" id="tablero-linea">{{ linea }}</p>
    <p class="tablero-resumen" id="tablero-resumen">{{ resumen }}</p>
  </div>
  <div class="panel-cabecera-acciones">
    <button type="button" class="btn-generar btn-sm" data-nueva-campana>+ Campaña</button>
    {% if pendientes_sprint %}
    <button type="button" class="btn-sm" onclick="abrirLote('')">Generar lote ({{ pendientes_sprint | length }})</button>
    {% endif %}
    {% if lote and (lote.listas or lote.error or lote.generando or lote.encoladas) %}
    <a class="btn-sm" href="{{ url_for('sprints.revision', cliente=cliente, sid=sprint.id) }}">Revisar ({{ lote.aprobadas }}/{{ lote.listas }} listas)</a>
    {% endif %}
    <details class="tablero-mas">
      <summary class="btn-sm">Más</summary>
      <div class="tablero-mas-menu">
        {% if sprint.estado in ("planeando", "referencias") and sprint.campanas %}
        <form method="post" action="{{ url_for('sprints.marcar_listo', cliente=cliente, sid=sprint.id) }}"
              onsubmit="return confirm('¿Marcar el sprint como listo para generar aunque falten referentes?');">
          <button type="submit" class="btn-sm">Marcar listo para generar</button>
        </form>
        {% endif %}
        <form method="post" action="{{ url_for('sprints.archivar', cliente=cliente, sid=sprint.id) }}"
              onsubmit="return confirm('¿Archivar este sprint? Se puede desarchivar después.');">
          <button type="submit" class="btn-sm">Archivar</button>
        </form>
        <form method="post" action="{{ url_for('sprints.eliminar', cliente=cliente, sid=sprint.id) }}"
              onsubmit="return confirm('¿Eliminar este sprint PERMANENTEMENTE? Se borran sus campañas, ideas y referencias. No se puede deshacer.');">
          <button type="submit" class="btn-sm btn-rechazar">Eliminar permanentemente</button>
        </form>
      </div>
    </details>
  </div>
</div>

<details class="swap-card tablero-editar" id="tablero-editar">
  <summary class="swap-card-resumen">✎ Datos del sprint (se guardan solos)</summary>
  <div class="tablero-editar-campos" data-sprint-campos
       data-url="{{ url_for('sprints.sprint_campo', cliente=cliente, sid=sprint.id) }}">
    <label>Nombre <input data-campo="nombre" value="{{ sprint.nombre }}" maxlength="200">
      <small class="campo-error" hidden></small></label>
    <label>Inicio <input type="date" data-campo="inicio" value="{{ sprint.inicio }}">
      <small class="campo-error" hidden></small></label>
    <label>Fin <input type="date" data-campo="fin" value="{{ sprint.fin }}">
      <small class="campo-error" hidden></small></label>
    <label>País <select data-campo="pais">
        <option value="">Sin país</option>
        {% for p in paises %}<option value="{{ p.codigo }}" {% if p.codigo == sprint.pais %}selected{% endif %}>{{ p.bandera }} {{ p.nombre }}</option>{% endfor %}
      </select><small class="campo-error" hidden></small></label>
    <label>Idioma de los textos <select data-campo="idioma">
        {% for cod, nombre in idiomas.items() %}<option value="{{ cod }}" {% if cod == sprint.idioma %}selected{% endif %}>{{ nombre }}</option>{% endfor %}
      </select><small class="campo-error" hidden></small></label>
    <label>Momento del mes <select data-campo="momento">
        <option value="">Ninguno</option>
        {% for p in presets %}<option value="{{ p.clave }}" {% if p.clave == momento_valor %}selected{% endif %}>{{ p.nombre }} ({{ p.inicio[5:] }} → {{ p.fin[5:] }})</option>{% endfor %}
        <option value="propio" {% if momento_valor == 'propio' %}selected{% endif %}>Otro (escríbelo)…</option>
      </select>
      <input data-momento-texto maxlength="120" placeholder="Tu momento" value="{{ sprint.momento.nombre if momento_valor == 'propio' else '' }}" {% if momento_valor != 'propio' %}hidden{% endif %}>
      <small class="campo-error" hidden></small></label>
    <label class="ancho">Marcas a imitar <small class="vacio">(una por línea; con el link de su Ad Library si lo tienes)</small>
      <textarea data-campo="marcas" rows="2">{{ marcas_texto }}</textarea><small class="campo-error" hidden></small></label>
  </div>
</details>

{% if lote and lote.planeadas %}
<p class="vacio sprint-lote-resumen" id="sprint-lote-resumen">
  {{ lote.listas }} listas · {{ lote.generando }} generando · {{ lote.encoladas }} en cola · {{ lote.error }} con error · {{ lote.aprobadas }} aprobadas · USD {{ '%.2f' % lote.costo_usd }} gastado
</p>
{% endif %}

{% if not sprint.campanas %}
<div class="estado-vacio">
  <p class="estado-vacio-titulo">Este sprint todavía no tiene campañas</p>
  <p class="estado-vacio-texto">Cada campaña es una persona con un producto y los anuncios que va a seguir. Empieza con «+ Campaña».</p>
</div>
{% endif %}
<div class="tablero-grid" id="tablero-grid">
  {% for c in sprint.campanas %}{% include "_sprint_tarjeta.html" %}{% endfor %}
  <button type="button" class="tablero-tarjeta tablero-tarjeta-nueva" data-nueva-campana>
    <strong>+ Campaña</strong><small class="vacio">eliges persona y producto; lo demás en el panel</small>
  </button>
</div>

<div class="tablero-fondo" id="tablero-fondo" hidden></div>
<aside class="tablero-panel" id="tablero-panel" hidden aria-label="Campaña"
       data-url-base="{{ url_for('sprints.ver', cliente=cliente, sid=sprint.id) }}"
       data-panel-inicial="{{ panel_inicial or '' }}">
  <div id="tablero-panel-cuerpo"></div>
</aside>

<template id="tablero-nueva">
  <div class="panel-campana panel-nueva">
    <header class="panel-campana-cab">
      <div><h2>Nueva campaña</h2><small class="vacio">Primero la persona y el producto; lo demás lo ajustas después.</small></div>
      <button type="button" class="btn-xs" data-panel-cerrar aria-label="Cerrar">✕</button>
    </header>
    <form data-nueva action="{{ url_for('sprints.campana_agregar', cliente=cliente, sid=sprint.id) }}" class="panel-seccion">
      <label>Persona
        <select name="persona_id" data-nueva-persona required>
          <option value="">Elige una persona</option>
          {% for p in personas_sprint %}<option value="{{ p.id }}">{{ p.nombre }}{% if p.origen == 'investigada' %} · del Nicho{% endif %}</option>{% endfor %}
        </select></label>
      <label>Producto
        <select name="catalogo_id" required>
          <option value="">Elige un producto</option>
          {% for p in productos_sprint %}<option value="{{ p.id }}">{{ p.nombre }}</option>{% endfor %}
        </select></label>
      <p class="campo-error" data-error hidden></p>
      <button type="submit" class="btn-generar">Crear campaña</button>
    </form>
    <details class="panel-persona-rapida">
      <summary class="btn-xs">+ Crear persona rápida</summary>
      <form data-persona-rapida action="{{ url_for('sprints.persona_crear', cliente=cliente) }}">
        <input name="nombre" required maxlength="120" placeholder="Nombre (p. ej. Mamá práctica)">
        <input name="resumen" maxlength="200" placeholder="Una línea: qué quiere o qué le duele">
        <button type="submit" class="btn-sm">Crear y usar</button>
        <small class="campo-error" hidden></small>
      </form>
    </details>
    {% if not productos_sprint %}<p class="vacio">No hay productos en el catálogo: agrégalos en Catálogo › Productos.</p>{% endif %}
  </div>
</template>

{% include "_sprint_lote_modal.html" %}

<script>
  (function () {
    var panel = document.getElementById('tablero-panel');
    var cuerpo = document.getElementById('tablero-panel-cuerpo');
    var fondo = document.getElementById('tablero-fondo');
    var grid = document.getElementById('tablero-grid');
    var base = panel.dataset.urlBase;
    var H = {'X-Requested-With': 'fetch'};
    var HJ = {'X-Requested-With': 'fetch', 'Content-Type': 'application/json'};

    function json(r) { return r.json().then(function (j) { if (!r.ok || !j.ok) throw new Error(j.error || 'No se pudo guardar.'); return j; }); }
    function mensaje(e) { return e instanceof TypeError ? 'Sin conexión: no se guardó. Intenta de nuevo.' : e.message; }
    function marcarUrl(cid) {
      var u = new URL(location.href);
      if (cid) u.searchParams.set('panel', cid); else u.searchParams.delete('panel');
      history.replaceState(null, '', u);
    }
    function marcarActiva(cid) {
      grid.querySelectorAll('.tablero-tarjeta.activa').forEach(function (t) { t.classList.remove('activa'); });
      var t = cid && document.getElementById('campana-' + cid);
      if (t) t.classList.add('activa');
    }
    function mostrar() { panel.hidden = false; fondo.hidden = false; document.body.classList.add('panel-abierto'); }
    function cerrar() {
      panel.hidden = true; fondo.hidden = true; cuerpo.innerHTML = '';
      document.body.classList.remove('panel-abierto'); marcarUrl(null); marcarActiva(null);
    }
    function noExiste() {
      cuerpo.innerHTML = '<div class="estado-vacio"><p class="estado-vacio-titulo">Esta campaña ya no existe</p>' +
        '<p class="estado-vacio-texto">Pudo borrarse en otra pestaña.</p><a class="btn-sm" href="' + base + '">Volver al tablero</a></div>';
    }
    function refrescarTarjeta(cid) {
      return fetch(base + '/campanas/' + cid + '/tarjeta', {headers: H})
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          var t = document.getElementById('campana-' + cid);
          if (html && t) { t.outerHTML = html; marcarActiva(cid); }
        }).catch(function () {});
    }
    function abrir(cid) {
      mostrar(); marcarUrl(cid); marcarActiva(cid);
      cuerpo.innerHTML = '<p class="vacio">Cargando la campaña…</p>';
      return fetch(base + '/campanas/' + cid + '/panel', {headers: H})
        .then(function (r) {
          if (r.status === 404) { noExiste(); return null; }
          if (!r.ok) throw new Error();
          return r.text();
        })
        .then(function (html) {
          if (html === null) return;
          cuerpo.innerHTML = html;
          if (typeof window.tableroPanelListo === 'function') window.tableroPanelListo();
        })
        .catch(function () { cuerpo.innerHTML = '<p class="campo-error">No se pudo abrir la campaña. Revisa tu conexión e intenta de nuevo.</p>'; });
    }
    function abrirNueva() {
      mostrar(); marcarUrl(null); marcarActiva(null);
      cuerpo.innerHTML = document.getElementById('tablero-nueva').innerHTML;
    }
    window.tablero = {abrir: abrir, abrirNueva: abrirNueva, cerrar: cerrar, refrescarTarjeta: refrescarTarjeta,
                      json: json, mensaje: mensaje, cuerpo: cuerpo, panel: panel, base: base};

    document.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-nueva-campana]')) { abrirNueva(); return; }
      if (ev.target.closest('[data-panel-cerrar]')) { cerrar(); return; }
      var t = ev.target.closest('.tablero-tarjeta[data-cid]');
      if (t && grid.contains(t)) abrir(t.dataset.cid);
    });
    grid.addEventListener('keydown', function (ev) {
      var t = ev.target.closest('.tablero-tarjeta[data-cid]');
      if (t && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrir(t.dataset.cid); }
    });
    fondo.addEventListener('click', cerrar);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !panel.hidden) cerrar(); });

    // Nueva campaña y persona rápida (en el modo «nueva» y en el panel completo).
    panel.addEventListener('submit', function (ev) {
      var f = ev.target;
      if (f.matches('[data-nueva]')) {
        ev.preventDefault();
        var err = f.querySelector('[data-error]');
        err.hidden = true;
        fetch(f.action, {method: 'POST', headers: HJ,
                         body: JSON.stringify({persona_id: f.persona_id.value, catalogo_id: f.catalogo_id.value})})
          .then(json).then(function (j) { location.href = j.url; })
          .catch(function (e) { err.textContent = mensaje(e); err.hidden = false; });
      } else if (f.matches('[data-persona-rapida]')) {
        ev.preventDefault();
        var errP = f.querySelector('.campo-error');
        errP.hidden = true;
        fetch(f.action, {method: 'POST', headers: H, body: new FormData(f)})
          .then(json).then(function (j) {
            var sel = cuerpo.querySelector('[data-nueva-persona], [data-campo="persona_id"]');
            if (sel) {
              sel.add(new Option(j.nombre, j.id, true, true));
              sel.dispatchEvent(new Event('change', {bubbles: true}));
            }
            f.reset();
            var d = f.closest('details'); if (d) d.open = false;
          })
          .catch(function (e) { errP.textContent = mensaje(e); errP.hidden = false; });
      }
    });

    // Cabecera del sprint: cada dato se guarda solo.
    var campos = document.querySelector('[data-sprint-campos]');
    campos.querySelectorAll('[data-campo]').forEach(function (el) { el.dataset.guardado = el.value; });
    function guardarSprint(el, valor) {
      var err = el.closest('label').querySelector('.campo-error');
      err.hidden = true;
      fetch(campos.dataset.url, {method: 'POST', headers: HJ, body: JSON.stringify({campo: el.dataset.campo, valor: valor})})
        .then(json).then(function (j) {
          el.dataset.guardado = el.value;
          document.getElementById('tablero-linea').textContent = j.linea;
          document.getElementById('tablero-resumen').textContent = j.resumen;
        })
        .catch(function (e) { el.value = el.dataset.guardado || ''; err.textContent = mensaje(e); err.hidden = false; });
    }
    campos.addEventListener('change', function (ev) {
      var texto = campos.querySelector('[data-momento-texto]');
      var momento = campos.querySelector('[data-campo="momento"]');
      if (ev.target === texto) {
        if (texto.value.trim()) guardarSprint(momento, 'propio:' + texto.value.trim());
        return;
      }
      var el = ev.target.closest('[data-campo]');
      if (!el) return;
      if (el === momento) {
        texto.hidden = momento.value !== 'propio';
        if (momento.value === 'propio') { if (texto.value.trim()) guardarSprint(momento, 'propio:' + texto.value.trim()); else texto.focus(); return; }
      }
      guardarSprint(el, el.value);
    });

    // Mientras el sprint genera, el resumen del lote se actualiza solo.
    if ({{ sprint.estado | tojson }} === 'generando') {
      setInterval(function () {
        fetch({{ url_for('sprints.progreso_json', cliente=cliente, sid=sprint.id) | tojson }}, {headers: H})
          .then(function (r) { return r.json(); })
          .then(function (j) {
            var res = document.getElementById('sprint-lote-resumen');
            if (res && j.lote) res.textContent = j.lote.listas + ' listas · ' + j.lote.generando + ' generando · ' + j.lote.encoladas + ' en cola · ' + j.lote.error + ' con error · ' + j.lote.aprobadas + ' aprobadas · USD ' + j.lote.costo_usd.toFixed(2) + ' gastado';
            if (j.estado !== 'generando') location.reload();
          }).catch(function () {});
      }, 10000);
    }

    if (panel.dataset.panelInicial) abrir(panel.dataset.panelInicial);
  })();
</script>
{% endblock %}
```

- [ ] **Step 6: Append the board CSS**

Append to the «Tablero de Sprints» block at the end of `static/style.css`:

```css
.tablero-titulo { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; margin: 0; }
.tablero-resumen { margin: .3rem 0 0; font-weight: 600; }
.tablero-mas { position: relative; }
.tablero-mas-menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; display: grid; gap: .4rem; min-width: 220px;
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: var(--shadow); padding: .6rem; }
.tablero-mas-menu button { width: 100%; }
.tablero-editar-campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: .8rem 1rem; margin-top: .8rem; }
.tablero-editar-campos .ancho { grid-column: 1 / -1; }
.tablero-editar-campos input[hidden] { display: none; }
.tablero-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: .9rem; margin-top: 1rem; }
.tablero-tarjeta { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: .9rem 1rem;
  cursor: pointer; text-align: left; color: var(--text); font: inherit; display: flex; flex-direction: column; gap: .35rem;
  min-width: 0; transition: border-color .15s, box-shadow .15s; }
.tablero-tarjeta:hover, .tablero-tarjeta:focus-visible { border-color: var(--accent); box-shadow: var(--shadow-soft); outline: none; }
.tablero-tarjeta.activa { border-color: var(--accent); box-shadow: var(--shadow-glow); }
.tablero-tarjeta p { margin: 0; overflow-wrap: anywhere; }
.tablero-tarjeta-cab { display: flex; align-items: center; gap: .5rem; }
.tablero-tarjeta-nueva { border-style: dashed; align-items: center; justify-content: center; min-height: 160px; gap: .2rem; text-align: center; }
.chip-etapa { display: inline-block; border-radius: 999px; padding: .05rem .55rem; font-size: .75rem; font-weight: 700;
  background: var(--accent-grad); color: #fff; }
.tablero-miniaturas { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; margin: .2rem 0; }
.tablero-miniaturas img, .tablero-miniatura-vacia { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px;
  background: var(--panel-2); border: 1px dashed var(--border); display: block; }
.tablero-miniaturas img { border-style: solid; }
.tablero-tarjeta-cantidades { font-size: .85rem; color: var(--muted); }
.tablero-siguiente { color: var(--accent); font-weight: 600; font-size: .9rem; }
.tablero-fondo { position: fixed; inset: 0; background: rgba(10, 10, 25, .35); z-index: 60; }
.tablero-panel { position: fixed; top: 0; right: 0; bottom: 0; width: min(560px, 100%); background: var(--panel);
  border-left: 1px solid var(--border); box-shadow: var(--shadow); z-index: 61; overflow-y: auto; padding: 1rem 1.2rem 2rem; }
.tablero-panel[hidden], .tablero-fondo[hidden] { display: none; }
body.panel-abierto { overflow: hidden; }
.panel-campana-cab { display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; }
.panel-campana-cab h2 { margin: 0; font-size: 1.15rem; }
.panel-seccion { border-top: 1px solid var(--border); padding-top: .8rem; margin-top: .8rem; display: grid; gap: .6rem; }
.panel-persona-rapida { margin-top: .6rem; }
.panel-persona-rapida form { display: grid; gap: .5rem; margin-top: .5rem; }
@media (max-width: 760px) {
  .tablero-panel { width: 100%; border-left: 0; padding: .8rem 16px 2rem; }
  .tablero-mas-menu { position: static; margin-top: .4rem; box-shadow: none; }
}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_sprints_temporada_opcional.py tests/test_sprints_datos.py`
Expected: PASS except the three `test_referencias_ajax_*`/panel-dependent tests that Task 8 replaces — if any fail only because `sprint_detalle.html` no longer links them, leave them for Task 8 and note them in the report. (`test_referencias_ajax_*` call the `-ajax` routes directly and should still pass here.)

- [ ] **Step 8: Commit**

```bash
git add sprints/rutas.py sprints/datos.py templates/sprint_detalle.html templates/_sprint_tarjeta.html static/style.css tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_sprints_temporada_opcional.py
git commit -m "Sprints tablero: la página del sprint es un tablero de tarjetas con cabecera que se guarda sola

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: El panel de la campaña y sus referentes

**Files:**
- Modify: `sprints/rutas.py` (new `campana_panel`, `campana_sugeridos`, `campana_campo`, helpers `_campana_del_sprint`, `_enlaces`, `_volver_campana`; JSON answers in `campana_referencias_biblioteca` and `campana_sugerir_ia`; `referencias_subir`/`referencias_catalogo` honor `volver=tablero`; delete `referencias_ajax`, `ideas_ajax`, `revision_ajax`)
- Create: `templates/_sprint_panel.html`, `templates/_sprint_sugeridos.html`
- Modify: `templates/_sprint_macros.html` (macro `sugerido`), `templates/sprint_detalle.html` (second `<script>`: panel behaviour), `templates/_tab_referentes.html` (forward `idioma`, `modo`, `pagina_id`), `static/style.css`
- Delete: `templates/_sprint_referencias_ajax.html`, `templates/_sprint_ideas_ajax.html`, `templates/_sprint_revision_ajax.html`
- Test: `tests/test_sprints_tablero_rutas.py`, `tests/test_rutas_sprints.py`

**Interfaces:**
- Consumes: Tasks 2–7 (`window.tablero` = `{abrir, abrirNueva, cerrar, refrescarTarjeta, json, mensaje, cuerpo, panel, base}` and the hook `window.tableroPanelListo()` called after the panel HTML is inserted).
- Produces:
  - `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/panel` → `_sprint_panel.html` (404 if the campaign is not in that sprint).
  - `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/sugeridos[?todas=1]` → `_sprint_sugeridos.html`.
  - `POST /cliente/<c>/sprints/<sid>/campanas/<cid>/campo` JSON `{campo, valor}` (`campo` ∈ `persona_id, catalogo_id, funnel, consciencia, dolor, familias, pais, idioma, marcas, n_videos, n_imagenes, referencias_objetivo`) → `{ok, aviso, resumen, tarjeta, recargar_panel}` or 400 `{ok: false, error}`.
  - `POST …/campanas/<cid>/referencias_biblioteca` with `X-Requested-With: fetch` → `{ok, agregados, error}`; without it → redirect `sprints.ver?panel=<cid>`.
  - `POST …/campanas/<cid>/sugerir_ia` with fetch → `{ok, job_id, error}`; without it → redirect `sprints.ver?panel=<cid>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sprints_tablero_rutas.py`:

```python
# --------------------------------------------------------------- panel ---

def _referente(n, familia, etapa="TOF", consciencia="problem-aware", marca="", idioma="en"):
    from referentes import datos as rdatos
    rdatos.familia_asegurar(familia, "")
    rid, _ = rdatos.guardar_referente({"anuncio_id": f"p{n}", "fuente": "atria", "imagen_origen": "https://o/x.jpg",
                                       "marca": marca, "idioma": idioma})
    rdatos.marcar_imagen(rid, "ok", f"https://r2/ref{n}.jpg")
    rdatos.actualizar_referente(rid, etapa=etapa, consciencia=consciencia, familia=familia, clasificacion="claude")
    return rid


def test_panel_muestra_las_siete_secciones(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    r = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel")
    html = r.data.decode()
    assert r.status_code == 200
    for frag in ("Audiencia y producto", "Enfoque", "Formato de los anuncios", "Mercado y marcas", "Piezas",
                 "Referentes · 0 de 5 elegidos", 'data-campo="persona_id"', 'data-campo="catalogo_id"',
                 'data-campo="funnel"', 'data-campo="consciencia"', 'data-campo="dolor"', 'data-campo="familias"',
                 'data-campo="pais"', 'data-campo="idioma"', 'data-campo="marcas"', 'data-campo="n_videos"',
                 'data-campo="n_imagenes"', 'data-campo="referencias_objetivo"', "Sugerir con IA",
                 "Buscar en la biblioteca", "Traer nuevos de Meta", 'name="volver" value="tablero"',
                 "Eliminar campaña", f"/sprints/{sid}/campanas/{cid}/ideas", "Crear persona rápida", "data-sugeridos"):
        assert frag in html, frag
    assert "<script" not in html                      # el JS vive en sprint_detalle.html


def test_panel_de_otra_campana_o_sprint_da_404(app):
    from sprints import datos
    sid, otro = _sprint(datos), _sprint(datos)
    cid = _campana(datos, sid)
    assert app["c"].get(f"/cliente/acme/sprints/{otro}/campanas/{cid}/panel").status_code == 404
    assert app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/999/panel").status_code == 404


def test_panel_trae_lo_de_nicho_y_lo_heredado(app):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa", resumen="Comodidad al llegar", origen="investigada",
                              extra={"conciencia": {"nivel": "consciente del problema"},
                                     "encaje_producto": "Abriga sin sudar"})
    sid = _sprint(datos, pais="MX", marcas="Crocs")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 2, 1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'value="consciente_del_problema" checked' in html
    assert 'data-valor="Abriga sin sudar"' in html and "Melissa · del Nicho" in html
    assert "Del sprint (🇲🇽 México)" in html and "Del sprint: Crocs" in html
    assert "#referentes?" in html and "etapa=TOF" in html and "consciencia=problem-aware" in html
    assert "pais=MX" in html and "palabra=Espejo+LED" in html


def test_panel_muestra_referencias_viejas_sin_frame(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/vieja.png", frame_url=None, titulo="vieja.png")
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel").data.decode()
    assert 'src="https://r2/vieja.png"' in html and "falta describir" in html


def test_guardar_un_campo_de_la_campana(app):
    from referentes import datos as rdatos
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    rdatos.familia_asegurar("UGC", "")
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo"
    j = _json(app["c"], url, {"campo": "dolor", "valor": "pies fríos"}).get_json()
    assert j["ok"] and "«pies fríos»" in j["tarjeta"] and j["recargar_panel"] is False
    j = _json(app["c"], url, {"campo": "familias", "valor": ["UGC"]}).get_json()
    assert j["ok"] and j["recargar_panel"] is True and datos.campana("acme", cid)["familias"] == ["UGC"]
    j = _json(app["c"], url, {"campo": "n_videos", "valor": "7"}).get_json()
    assert j["ok"] and "7 videos" in j["tarjeta"] and "8 piezas planeadas" in j["resumen"]
    for malo in ({"campo": "consciencia", "valor": "x"}, {"campo": "familias", "valor": ["No existe"]},
                 {"campo": "n_videos", "valor": -1}, {"campo": "catalogo_id", "valor": "no_existe"},
                 {"campo": "estado", "valor": "x"}, {"campo": "dolor", "valor": {"a": 1}},
                 {"campo": "funnel", "valor": True}):
        r = _json(app["c"], url, malo)
        assert r.status_code == 400 and r.get_json()["error"], malo
    assert datos.campana("acme", cid)["n_videos"] == 7


def test_guardar_repetida_devuelve_el_aviso(app):
    from sprints import datos
    sid = _sprint(datos)
    pid = datos.crear_persona("acme", "Premium")
    datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0, funnel="mof")
    j = _json(app["c"], f"/cliente/acme/sprints/{sid}/campanas/{cid}/campo", {"campo": "funnel", "valor": "tof"}).get_json()
    assert j["ok"] and "campaña 1" in j["aviso"]


def test_sugeridos_siguen_el_enfoque_y_avisan_lo_aflojado(app):
    from sprints import datos
    uno = _referente(1, "UGC")
    dos = _referente(2, "Antes y después")
    _referente(3, "Lista", consciencia="unaware")
    _referente(4, "Otra etapa", etapa="MOF")
    sid = _sprint(datos)
    cid = _campana(datos, sid, consciencia="consciente_del_problema", familias=["UGC"])
    datos.actualizar_campana("acme", cid, referencias_objetivo=1)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    assert f'data-sumar-ref="{uno}"' in html and "ya no filtran por" not in html
    datos.actualizar_campana("acme", cid, referencias_objetivo=5)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    assert f'data-sumar-ref="{dos}"' in html and "ya no filtran por" in html and "las familias de formato" in html
    assert "Otra etapa" not in html


def test_sugeridos_vacios_ofrecen_tres_salidas(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos").data.decode()
    for frag in ("No hay referentes para sugerir", "data-aflojar", "data-sugerir-ia", "Traer nuevos de Meta"):
        assert frag in html, frag
    html = app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/sugeridos?todas=1").data.decode()
    assert "data-aflojar" not in html


def test_agregar_de_la_biblioteca_por_fetch_y_por_formulario(app):
    from sprints import datos
    uno, dos = _referente(1, "UGC"), _referente(2, "Lista")
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/campanas/{cid}/referencias_biblioteca"
    r = app["c"].post(url, data={"referente_ids": [str(uno)]}, headers={"X-Requested-With": "fetch"})
    assert r.get_json() == {"ok": True, "agregados": 1, "error": None}
    r = app["c"].post(url, data={"referente_ids": [str(dos)]})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")
    assert len(datos.referencias("acme", cid)) == 2
    j = app["c"].post(url, data={"referente_ids": ["999"]}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] is False and j["error"]


def test_sugerir_ia_por_fetch(app, monkeypatch):
    from sprints import datos, rutas
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/campanas/{cid}/sugerir_ia"
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_sugerir_biblioteca", lambda cliente_, cid_: True)
    j = app["c"].post(url, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] and j["job_id"] == f"acme__campana{cid}__sugerir_biblioteca"
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_sugerir_biblioteca", lambda cliente_, cid_: False)
    j = app["c"].post(url, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] is False and "en curso" in j["error"]


def test_fotos_del_producto_vuelven_al_panel(app, monkeypatch):
    import catalogo_productos
    from sprints import datos, rutas
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, cat=None: {"id": "espejo_led", "nombre": "Espejo LED", "imagenes": ["a.jpg"]})
    monkeypatch.setattr(rutas.tareas_sprints, "encolar_analisis", lambda cliente_, rid: True)
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    url = f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo"
    r = app["c"].post(url, data={"volver": "tablero"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")
    r = app["c"].post(url)
    assert r.headers["Location"].endswith(f"/sprints/{sid}/campanas/{cid}")


def test_las_mini_pantallas_viejas_ya_no_existen(app):
    from sprints import datos
    sid = _sprint(datos)
    cid = _campana(datos, sid)
    for tipo in ("referencias", "ideas", "revision"):
        assert app["c"].get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/{tipo}-ajax").status_code == 404
```

In `tests/test_rutas_sprints.py`:
- `test_campana_referencias_biblioteca_agrega_y_redirige`: change the Location assertion to `assert r.headers["Location"].endswith(f"/sprints/{sid}?panel={cid}")`.
- `test_campana_sugerir_ia_encola_tarea`: same change.
- Delete `test_referencias_ajax_muestra_imagenes_y_videos` and `test_referencias_ajax_muestra_los_avisos_de_cobertura_como_texto` (routes removed; the panel test above covers the old-image case).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py`
Expected: FAIL — panel/sugeridos/campo routes missing (404), redirects still go to `campana_ver`.

- [ ] **Step 3: Implement the routes**

In `sprints/rutas.py`:

1. Import `from urllib.parse import urlencode` (stdlib block at the top).

2. After `_aviso_identica` (Task 7) add:

```python
CAMPOS_CAMPANA = ("persona_id", "catalogo_id", "funnel", "consciencia", "dolor", "familias", "pais", "idioma",
                  "marcas", "n_videos", "n_imagenes", "referencias_objetivo")
# Cambiar estos datos cambia más que la tarjeta (familias sugeridas, lo heredado,
# los sugeridos, los enlaces): el panel se vuelve a cargar entero.
CAMPOS_RECARGAN_PANEL = ("persona_id", "catalogo_id", "funnel", "consciencia", "familias", "pais", "idioma", "marcas",
                         "referencias_objetivo")


def _campana_del_sprint(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = next((x for x in sp["campanas"] if x["id"] == cid), None)
    if not c:
        abort(404)
    return sp, c


def _enlaces(cliente, sp, c):
    """«Buscar en la biblioteca» (grid en modo selección, ya filtrado por etapa
    y consciencia) y «Traer nuevos de Meta» (formulario prellenado con país,
    idioma y la primera marca con página, o el producto como palabra clave)."""
    ef = c.get("efectivos") or datos.efectivos(sp, c)
    filtros = {"etapa": (c.get("funnel") or "tof").upper(), "campana": c["id"]}
    cons = referentes_sugerir.consciencia_en(c.get("consciencia"))
    if cons:
        filtros["consciencia"] = cons
    traer = {"campana": c["id"], "pais": ef["pais"] or proyectos.pais(cliente), "idioma": ef["idioma"]}
    con_pagina = next((m for m in ef["marcas"] if m.get("pagina_id")), None)
    if con_pagina:
        traer.update(modo="marca", pagina_id=con_pagina["pagina_id"])
    else:
        producto = (c.get("producto") or {}).get("nombre") or c["catalogo_id"]
        traer.update(modo="palabra", palabra=producto.split(" — ")[0])
    base = url_for("ver_cliente", cliente=cliente)
    return {"biblioteca": f"{base}#referentes?{urlencode(filtros)}", "traer": f"{base}#referentes?{urlencode(traer)}"}


def _volver_campana(cliente, sid, cid):
    """Las acciones de referencias vuelven al panel del tablero cuando se
    pidieron desde ahí (`volver=tablero`), si no a la página de la campaña."""
    if request.form.get("volver") == "tablero":
        return redirect(url_for("sprints.ver", cliente=cliente, sid=sid, panel=cid))
    return _volver(cliente, sid, cid)


@bp.get("/<int:sid>/campanas/<int:cid>/panel")
def campana_panel(cliente, sid, cid):
    """Panel lateral de una campaña (fragmento por fetch). Abrirlo no gasta nada."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    productos = _productos_planos(cliente)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in productos})
    personas_ = datos.personas(cliente)
    if c["persona_id"] not in {p["id"] for p in personas_}:
        archivada = datos.persona(cliente, c["persona_id"])
        if archivada:
            personas_.append(archivada)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in c["referencias_lista"]} - {None}
    candidatos_ia = []
    for item in (c.get("extra") or {}).get("sugerencias_ia") or []:
        ref = referentes_datos.referente(cliente, item.get("referente_id"))
        if ref and ref["id"] not in ya_ids:
            candidatos_ia.append({**ref, "razon": item.get("razon") or ""})
    familias = sorted(referentes_datos.familias(cliente), key=lambda f: (-int(f.get("n") or 0), f["nombre"]))
    sugeridas = referentes_datos.familias_frecuentes(cliente, etapa=(c.get("funnel") or "tof").upper(),
                                                    consciencia=referentes_sugerir.consciencia_en(c.get("consciencia")))
    job = tareas_sprints.job_id_sugerir_biblioteca(cliente, cid)
    pais_sprint = fe_tipos.PAISES.get(sp.get("pais") or "") or {}
    return render_template(
        "_sprint_panel.html", cliente=cliente, sprint=sp, c=c, personas=personas_, productos=productos,
        consciencias=doctrina.CONSCIENCIAS_NOMBRE, funnels=datos.FUNNELS_NOMBRE,
        sugerencias_dolor=tablero.sugerencias_dolor(datos.persona(cliente, c["persona_id"])),
        familias=familias, familias_sugeridas=[f for f in sugeridas if f not in (c.get("familias") or [])],
        paises=_paises(), idiomas=datos.IDIOMAS_NOMBRE,
        pais_sprint=" ".join(x for x in (pais_sprint.get("bandera"), pais_sprint.get("nombre")) if x) or "sin país",
        marcas_texto=tablero.marcas_texto(c.get("marcas")), candidatos_ia=candidatos_ia,
        trabajo_sugerir_ia={"job_id": job} if trabajos.en_curso(job) else None,
        precio_sugerir_ia=gastos.estimar("sugerir_ia"), aviso=_aviso_identica(cliente, cid),
        enlaces=_enlaces(cliente, sp, c))


@bp.get("/<int:sid>/campanas/<int:cid>/sugeridos")
def campana_sugeridos(cliente, sid, cid):
    """Sugeridos gratis (sin Claude) según el enfoque de la campaña.
    `?todas=1` deja de filtrar por etapa (el «aflojar filtros» del estado vacío)."""
    sp, c = _campana_del_sprint(cliente, sid, cid)
    refs = datos.referencias(cliente, cid)
    ya_ids = {(r.get("extra") or {}).get("referente_id") for r in refs} - {None}
    ef = c["efectivos"]
    todas = request.args.get("todas") == "1"
    enfoque = {"etapa": None if todas else (c.get("funnel") or "tof").upper(), "consciencia": c.get("consciencia"),
               "familias": c.get("familias") or [], "idioma": ef["idioma"], "marcas": ef["marcas"]}
    faltan = int(c.get("referencias_objetivo") or 1) - len(refs)
    r = referentes_sugerir.sugerir_campana(cliente, enfoque, ya_ids, min(8, faltan) if faltan > 0 else 4)
    c["producto"] = next((p for p in _productos_planos(cliente) if p["id"] == c["catalogo_id"]), None)
    return render_template("_sprint_sugeridos.html", cliente=cliente, sprint=sp, c=c, sugeridos=r["items"],
                           aflojado=r["aflojado"] + (["etapa"] if todas else []), todas=todas,
                           precio_sugerir_ia=gastos.estimar("sugerir_ia"), enlaces=_enlaces(cliente, sp, c))


@bp.post("/<int:sid>/campanas/<int:cid>/campo")
def campana_campo(cliente, sid, cid):
    """Autoguardado de un dato del panel: `datos` valida, y se devuelve la
    tarjeta ya actualizada y si el panel debe recargarse."""
    _campana_o_404(cliente, sid, cid)
    cuerpo = _json_cuerpo()
    if not cuerpo or cuerpo.get("campo") not in CAMPOS_CAMPANA or not _valor_simple(cuerpo.get("valor")):
        return jsonify({"ok": False, "error": "Ese dato no se puede editar aquí."}), 400
    campo, valor = cuerpo["campo"], cuerpo.get("valor")
    try:
        if campo == "catalogo_id" and valor not in {p["id"] for p in _productos_planos(cliente)}:
            raise datos.ErrorDatos("Ese producto no está en el catálogo.")
        datos.actualizar_campana(cliente, cid, **{campo: valor})
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    sp = estado.recalcular(cliente, sid)
    c = next(x for x in sp["campanas"] if x["id"] == cid)
    _campana_tablero(cliente, sp, c, {p["id"]: p for p in _productos_planos(cliente)})
    return jsonify({"ok": True, "aviso": _aviso_identica(cliente, cid), "resumen": tablero.resumen(sp),
                    "tarjeta": render_template("_sprint_tarjeta.html", cliente=cliente, sprint=sp, c=c),
                    "recargar_panel": campo in CAMPOS_RECARGAN_PANEL})
```

3. `campana_referencias_biblioteca`: replace its ending (from `estado.recalcular(...)` on) with:

```python
    estado.recalcular(cliente, c["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": n > 0, "agregados": n, "error": None if n else "No se pudo agregar ese referente."})
    if n:
        flash(f"{n} referente(s) agregado(s) desde la biblioteca.", "ok")
    else:
        flash("No se agregó ningún referente.", "error")
    return redirect(url_for("sprints.ver", cliente=cliente, sid=c["sprint_id"], panel=cid))
```

and update its docstring's last sentence: it now returns to the board with the campaign's panel open.

4. `campana_sugerir_ia`: replace its body after `if not c: abort(404)` with:

```python
    ok = tareas_sprints.encolar_sugerir_biblioteca(cliente, cid)
    if _quiere_json():
        return jsonify({"ok": bool(ok), "job_id": tareas_sprints.job_id_sugerir_biblioteca(cliente, cid),
                        "error": None if ok else "Ya hay una sugerencia en curso para esta campaña."})
    if ok:
        flash("Claude está buscando referentes de la biblioteca; aparecerán aquí en unos segundos.", "ok")
    else:
        flash("Ya hay una sugerencia en curso para esta campaña.", "error")
    return redirect(url_for("sprints.ver", cliente=cliente, sid=c["sprint_id"], panel=cid))
```

5. In `referencias_subir` replace the final `return _volver(cliente, sid, cid)` with `return _volver_campana(cliente, sid, cid)`. In `referencias_catalogo` replace BOTH `return _volver(cliente, sid, cid)` with `return _volver_campana(cliente, sid, cid)`.

6. Delete the section `# --------------------------------------------------- desplegables ajax ---` with `referencias_ajax`, `ideas_ajax`, `revision_ajax`. Keep `flowplus_prompt_enfoques` if `campana_ideas` still uses it (grep first). Delete `templates/_sprint_referencias_ajax.html`, `templates/_sprint_ideas_ajax.html`, `templates/_sprint_revision_ajax.html` with `git rm`.

- [ ] **Step 4: Templates**

Add to the end of `templates/_sprint_macros.html`:

```html
{% macro sugerido(s, cliente, campana_id, razon=None) -%}
<figure class="panel-sugerido">
  <img src="{{ s.imagen_url }}" alt="" loading="lazy">
  <figcaption>{{ s.familia or 'sin familia' }}{% if s.marca %} · {{ s.marca }}{% endif %}{% if razon %}<br><small class="vacio">{{ razon }}</small>{% endif %}</figcaption>
  <button type="button" class="panel-sumar" data-sumar-ref="{{ s.id }}"
          data-url="{{ url_for('sprints.campana_referencias_biblioteca', cliente=cliente, cid=campana_id) }}"
          aria-label="Agregar este referente a la campaña" title="Agregar a la campaña">+</button>
</figure>
{%- endmacro %}
```

Create `templates/_sprint_sugeridos.html`:

```html
{% from "_sprint_macros.html" import sugerido %}
{# Sugeridos gratis de una campaña (sprints.campana_sugeridos →
   referentes.sugerir.sugerir_campana). Fragmento por fetch, sin <script>. #}
{% set nombres = {"familias": "las familias de formato", "consciencia": "la consciencia", "etapa": "la etapa"} %}
{% if sugeridos %}
<p class="panel-sub">Sugeridos para esta campaña{% if aflojado %} <span class="vacio">— con todos los filtros no alcanzaban, así que ya no filtran por {% for a in aflojado %}{{ nombres[a] }}{% if not loop.last %} y {% endif %}{% endfor %}</span>{% endif %}</p>
<div class="panel-sugeridos-grid">{% for s in sugeridos %}{{ sugerido(s, cliente, c.id) }}{% endfor %}</div>
{% else %}
<div class="estado-vacio">
  <p class="estado-vacio-titulo">No hay referentes para sugerir</p>
  <p class="estado-vacio-texto">La biblioteca no tiene anuncios nuevos que encajen{% if not todas %} con esta etapa{% endif %}.</p>
  <div class="panel-acciones">
    {% if not todas %}<button type="button" class="btn-sm" data-aflojar>Aflojar filtros (todas las etapas)</button>{% endif %}
    <button type="button" class="btn-sm" data-sugerir-ia="{{ url_for('sprints.campana_sugerir_ia', cliente=cliente, cid=c.id) }}">✨ Sugerir con IA ({{ precio_sugerir_ia.texto }})</button>
    <a class="btn-sm" href="{{ enlaces.traer }}">Traer nuevos de Meta</a>
  </div>
</div>
{% endif %}
```

Create `templates/_sprint_panel.html`:

```html
{% from "_sprint_macros.html" import sugerido %}
{# Panel de una campaña (spec 2026-09-26 §Panel). Fragmento por fetch
   (sprints.campana_panel): sus <script> no correrían, así que todo el JS vive
   en sprint_detalle.html. Cada [data-campo] se guarda solo en
   sprints.campana_campo; lo heredado del sprint se ve y se cambia «solo aquí». #}
{% set ef = c.efectivos %}
<div class="panel-campana" data-cid="{{ c.id }}"
     data-url-campo="{{ url_for('sprints.campana_campo', cliente=cliente, sid=sprint.id, cid=c.id) }}"
     data-url-sugeridos="{{ url_for('sprints.campana_sugeridos', cliente=cliente, sid=sprint.id, cid=c.id) }}">
  <header class="panel-campana-cab">
    <div>
      <h2>Campaña {{ c.orden + 1 }} · {{ (c.funnel or 'tof') | upper }}</h2>
      <small class="vacio">Todo se guarda solo</small>
    </div>
    <button type="button" class="btn-xs" data-panel-cerrar aria-label="Cerrar">✕</button>
  </header>
  <p class="panel-campana-aviso" data-aviso {% if not aviso %}hidden{% endif %}>{{ aviso or '' }}</p>

  <section class="panel-seccion">
    <h3>Audiencia y producto</h3>
    <div class="panel-fila">
      <label>Persona
        <select data-campo="persona_id">
          {% for p in personas %}<option value="{{ p.id }}" {% if p.id == c.persona_id %}selected{% endif %}>{{ p.nombre }}{% if p.origen == 'investigada' %} · del Nicho{% endif %}</option>{% endfor %}
        </select>
        <small class="campo-error" hidden></small></label>
      <label>Producto
        <select data-campo="catalogo_id">
          {% if not c.producto %}<option value="{{ c.catalogo_id }}" selected>{{ c.catalogo_id }} (ya no está en el catálogo)</option>{% endif %}
          {% for p in productos %}<option value="{{ p.id }}" {% if p.id == c.catalogo_id %}selected{% endif %}>{{ p.nombre }}</option>{% endfor %}
        </select>
        <small class="campo-error" hidden></small></label>
    </div>
    <details class="panel-persona-rapida">
      <summary class="btn-xs">+ Crear persona rápida</summary>
      <form data-persona-rapida action="{{ url_for('sprints.persona_crear', cliente=cliente) }}">
        <input name="nombre" required maxlength="120" placeholder="Nombre (p. ej. Mamá práctica)">
        <input name="resumen" maxlength="200" placeholder="Una línea: qué quiere o qué le duele">
        <button type="submit" class="btn-sm">Crear y usar</button>
        <small class="campo-error" hidden></small>
      </form>
    </details>
  </section>

  <section class="panel-seccion">
    <h3>Enfoque</h3>
    <div data-campo-caja>
      <span class="campo-label">Etapa</span>
      <div class="panel-opciones" role="radiogroup" aria-label="Etapa" data-campo="funnel" data-tipo="radio">
        {% for k, nombre in funnels.items() %}
        <label title="{{ nombre }}"><input type="radio" name="funnel-{{ c.id }}" value="{{ k }}" {% if k == c.funnel %}checked{% endif %}> {{ k | upper }}</label>
        {% endfor %}
      </div>
      <small class="campo-error" hidden></small>
    </div>
    <div data-campo-caja>
      <span class="campo-label">Qué tanto sabe la audiencia</span>
      <div class="panel-opciones" role="radiogroup" aria-label="Consciencia" data-campo="consciencia" data-tipo="radio">
        <label><input type="radio" name="consciencia-{{ c.id }}" value="" {% if not c.consciencia %}checked{% endif %}> sin definir</label>
        {% for k, nombre in consciencias.items() %}
        <label><input type="radio" name="consciencia-{{ c.id }}" value="{{ k }}" {% if k == c.consciencia %}checked{% endif %}> {{ nombre }}</label>
        {% endfor %}
      </div>
      <small class="campo-error" hidden></small>
    </div>
    <label>Dolor o deseo
      <input data-campo="dolor" value="{{ c.dolor or '' }}" maxlength="300" placeholder="pies fríos en casa">
      <small class="campo-error" hidden></small></label>
    {% if sugerencias_dolor %}
    <p class="panel-sugerencias">De {{ c.persona_nombre }}:
      {% for s in sugerencias_dolor %}<button type="button" class="chip-sugerencia" data-poner="dolor" data-valor="{{ s }}">{{ s }}</button>{% endfor %}</p>
    {% endif %}
  </section>

  <section class="panel-seccion">
    <h3>Formato de los anuncios</h3>
    <div data-campo-caja>
      <div class="panel-familias" data-campo="familias" data-tipo="familias">
        {% for f in c.familias or [] %}<span class="chip-familia" data-familia="{{ f }}">{{ f }} <button type="button" data-quitar-familia aria-label="Quitar {{ f }}">✕</button></span>{% endfor %}
        <input class="panel-familia-buscar" list="familias-biblioteca" data-agregar-familia
               placeholder="+ familia (busca entre {{ familias | length }})" aria-label="Agregar una familia de formato">
      </div>
      <small class="campo-error" hidden></small>
    </div>
    <datalist id="familias-biblioteca">{% for f in familias %}<option value="{{ f.nombre }}">{{ f.n }} anuncios</option>{% endfor %}</datalist>
    {% if familias_sugeridas %}
    <p class="panel-sugerencias">Sugeridas para {{ (c.funnel or 'tof') | upper }}{% if c.consciencia_nombre %} · {{ c.consciencia_nombre }}{% endif %}:
      {% for f in familias_sugeridas %}<button type="button" class="chip-sugerencia" data-sumar-familia="{{ f }}">{{ f }}</button>{% endfor %}</p>
    {% endif %}
  </section>

  <section class="panel-seccion">
    <h3>Mercado y marcas</h3>
    <div class="panel-fila">
      <label>País
        <select data-campo="pais">
          <option value="">Del sprint ({{ pais_sprint }})</option>
          {% for p in paises %}<option value="{{ p.codigo }}" {% if p.codigo == c.pais %}selected{% endif %}>{{ p.bandera }} {{ p.nombre }} (solo aquí)</option>{% endfor %}
        </select>
        <small class="campo-error" hidden></small></label>
      <label>Idioma de los textos
        <select data-campo="idioma">
          <option value="">Del sprint ({{ idiomas.get(sprint.idioma or 'es') }})</option>
          {% for cod, nombre in idiomas.items() %}<option value="{{ cod }}" {% if cod == c.idioma %}selected{% endif %}>{{ nombre }} (solo aquí)</option>{% endfor %}
        </select>
        <small class="campo-error" hidden></small></label>
    </div>
    <label>Marcas a imitar
      <small class="vacio">{% if ef.hereda.marcas %}Del sprint: {{ (ef.marcas | map(attribute='nombre') | join(', ')) or 'ninguna' }}. Escribe aquí para cambiarlas solo en esta campaña.{% else %}Solo esta campaña (bórralas para volver a las del sprint).{% endif %}</small>
      <textarea data-campo="marcas" rows="2" placeholder="Una por línea">{{ marcas_texto }}</textarea>
      <small class="campo-error" hidden></small></label>
  </section>

  <section class="panel-seccion">
    <h3>Piezas</h3>
    <div class="panel-fila panel-fila-3">
      <label>Videos <input type="number" min="0" max="50" data-campo="n_videos" value="{{ c.n_videos }}">
        <small class="campo-error" hidden></small></label>
      <label>Imágenes <input type="number" min="0" max="50" data-campo="n_imagenes" value="{{ c.n_imagenes }}">
        <small class="campo-error" hidden></small></label>
      <label>Referentes <input type="number" min="1" max="20" data-campo="referencias_objetivo" value="{{ c.referencias_objetivo }}">
        <small class="campo-error" hidden></small></label>
    </div>
  </section>

  <section class="panel-seccion">
    <h3>Referentes · {{ c.referencias_listas }} de {{ c.referencias_objetivo }} elegidos</h3>
    <div class="panel-elegidos">
      {% for r in c.referencias_lista %}
      <figure class="panel-elegido">
        <img src="{{ r.frame_url or r.url }}" alt="" loading="lazy">
        <button type="button" class="panel-quitar" data-quitar-ref="{{ url_for('sprints.referencia_quitar', cliente=cliente, rid=r.id) }}"
                aria-label="Quitar este referente" title="Quitar">✕</button>
        {% if r.estado != 'lista' %}<figcaption>falta describir</figcaption>{% endif %}
      </figure>
      {% endfor %}
      {% for _ in range([0, (c.referencias_objetivo or 1) - (c.referencias_lista | length)] | max) %}<span class="panel-elegido panel-elegido-vacio"></span>{% endfor %}
    </div>
    {% if c.referencias_lista | rejectattr('estado', 'equalto', 'lista') | list %}
    <p class="vacio">Los que dicen «falta describir» no cuentan todavía: <a href="{{ url_for('sprints.campana_ver', cliente=cliente, sid=sprint.id, cid=c.id) }}">descríbelos aquí</a>.</p>
    {% endif %}

    {% if candidatos_ia %}
    <p class="panel-sub">Elegidos por la IA</p>
    <div class="panel-sugeridos-grid">{% for s in candidatos_ia %}{{ sugerido(s, cliente, c.id, s.razon) }}{% endfor %}</div>
    {% endif %}
    {% if trabajo_sugerir_ia %}
    <div class="barra-progreso" id="trabajo-{{ trabajo_sugerir_ia.job_id }}" data-poll-job="{{ trabajo_sugerir_ia.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
    {% endif %}
    <div class="panel-sugeridos" data-sugeridos><p class="vacio">Buscando referentes para esta campaña…</p></div>

    <div class="panel-acciones">
      <button type="button" class="btn-sm" data-sugerir-ia="{{ url_for('sprints.campana_sugerir_ia', cliente=cliente, cid=c.id) }}">✨ Sugerir con IA ({{ precio_sugerir_ia.texto }})</button>
      <a class="btn-sm" href="{{ enlaces.biblioteca }}">Buscar en la biblioteca</a>
      <a class="btn-sm" href="{{ enlaces.traer }}">Traer nuevos de Meta</a>
    </div>
    <details class="panel-subir">
      <summary class="btn-sm">Subir · link · fotos del producto</summary>
      <form method="post" enctype="multipart/form-data" action="{{ url_for('sprints.referencias_subir', cliente=cliente, sid=sprint.id, cid=c.id) }}">
        <input type="hidden" name="volver" value="tablero">
        <label>Archivos (jpg, png, webp, mp4, mov, webm) <input type="file" name="archivos" multiple accept="image/*,video/*"></label>
        <label>O un link (Instagram, TikTok, YouTube…) <input type="url" name="link" placeholder="https://"></label>
        <button type="submit" class="btn-sm">Agregar</button>
      </form>
      <form method="post" action="{{ url_for('sprints.referencias_catalogo', cliente=cliente, sid=sprint.id, cid=c.id) }}">
        <input type="hidden" name="volver" value="tablero">
        <button type="submit" class="btn-sm">Traer las fotos del producto</button>
      </form>
    </details>
  </section>

  <footer class="panel-campana-pie">
    <form method="post" action="{{ url_for('sprints.campana_eliminar', cliente=cliente, sid=sprint.id, cid=c.id) }}"
          onsubmit="return confirm('¿Eliminar esta campaña y sus referentes?');">
      <button type="submit" class="btn-xs btn-rechazar">Eliminar campaña</button>
    </form>
    <a href="{{ url_for('sprints.campana_ideas', cliente=cliente, sid=sprint.id, cid=c.id) }}">Ideas de esta campaña →</a>
  </footer>
</div>
```

In `templates/_tab_referentes.html`, in the block that forwards hash keys to «Traer referentes», change `['palabra', 'pais'].forEach(` to `['palabra', 'pais', 'idioma', 'modo', 'pagina_id'].forEach(` and update the comment above it: «…manda `palabra`/`pais` (y `idioma`, `modo`, `pagina_id`) en el hash…».

- [ ] **Step 5: Panel behaviour (second script in `sprint_detalle.html`)**

In `templates/sprint_detalle.html`, right after the existing board `<script>…</script>` and before `{% endblock %}`, add:

```html
<script>
  // Panel de la campaña: autoguardado campo por campo, familias, referentes
  // (agregar/quitar), sugeridos gratis y «Sugerir con IA». Usa window.tablero.
  (function () {
    var T = window.tablero, panel = T.panel, cuerpo = T.cuerpo;
    var H = {'X-Requested-With': 'fetch'};
    var HJ = {'X-Requested-With': 'fetch', 'Content-Type': 'application/json'};

    function raiz() { return cuerpo.querySelector('.panel-campana[data-cid]'); }
    function valorDe(el) {
      if (el.dataset.tipo === 'radio') { var x = el.querySelector('input:checked'); return x ? x.value : ''; }
      if (el.dataset.tipo === 'familias') {
        return Array.prototype.map.call(el.querySelectorAll('[data-familia]'), function (s) { return s.dataset.familia; });
      }
      return el.value;
    }
    function ponerValor(el, v) {
      if (el.dataset.tipo === 'radio') { el.querySelectorAll('input').forEach(function (i) { i.checked = i.value === v; }); return; }
      if (el.dataset.tipo !== 'familias') el.value = v == null ? '' : v;
    }
    function errorDe(el) {
      var caja = el.closest('[data-campo-caja]') || el.closest('label') || el.parentElement;
      return caja ? caja.querySelector('.campo-error') : null;
    }
    function avisar(texto) {
      var a = cuerpo.querySelector('[data-aviso]');
      if (a) { a.textContent = texto; a.hidden = !texto; }
    }
    function cargarSugeridos(extra) {
      var r = raiz(), caja = cuerpo.querySelector('[data-sugeridos]');
      if (!r || !caja) return;
      caja.innerHTML = '<p class="vacio">Buscando referentes para esta campaña…</p>';
      fetch(r.dataset.urlSugeridos + (extra || ''), {headers: H})
        .then(function (x) { return x.ok ? x.text() : Promise.reject(); })
        .then(function (html) { caja.innerHTML = html; })
        .catch(function () { caja.innerHTML = '<p class="campo-error">No se pudieron cargar los sugeridos.</p>'; });
    }
    window.tableroPanelListo = function () {
      cuerpo.querySelectorAll('[data-campo]').forEach(function (el) { el.dataset.guardado = JSON.stringify(valorDe(el)); });
      cargarSugeridos();
      cuerpo.querySelectorAll('[data-poll-job]').forEach(function (el) {
        if (typeof iniciarPolling === 'function') iniciarPolling(el.dataset.pollJob, el.id);
      });
    };
    function guardar(el, valor) {
      var r = raiz();
      if (!r) return Promise.resolve();
      var err = errorDe(el);
      if (err) { err.hidden = true; err.textContent = ''; }
      return fetch(r.dataset.urlCampo, {method: 'POST', headers: HJ, body: JSON.stringify({campo: el.dataset.campo, valor: valor})})
        .then(T.json)
        .then(function (j) {
          el.dataset.guardado = JSON.stringify(valor);
          var t = document.getElementById('campana-' + r.dataset.cid);
          if (t && j.tarjeta) {
            t.outerHTML = j.tarjeta;
            var nueva = document.getElementById('campana-' + r.dataset.cid);
            if (nueva) nueva.classList.add('activa');
          }
          var resumen = document.getElementById('tablero-resumen');
          if (resumen && j.resumen) resumen.textContent = j.resumen;
          if (j.recargar_panel) return T.abrir(r.dataset.cid);
          avisar(j.aviso || '');
        })
        .catch(function (e) {
          ponerValor(el, JSON.parse(el.dataset.guardado || 'null'));
          if (err) { err.textContent = T.mensaje(e); err.hidden = false; }
        });
    }
    function cajaFamilias() { return cuerpo.querySelector('[data-campo="familias"]'); }
    function familias() { return valorDe(cajaFamilias()); }

    panel.addEventListener('change', function (ev) {
      var t = ev.target;
      if (!raiz() || t.closest('form')) return;
      if (t.matches('[data-agregar-familia]')) {
        var v = t.value.trim();
        if (!v) return;
        var existe = Array.prototype.some.call(cuerpo.querySelectorAll('#familias-biblioteca option'),
                                               function (o) { return o.value === v; });
        if (!existe) {
          var err = errorDe(cajaFamilias());
          if (err) { err.textContent = 'Elige una familia de la lista.'; err.hidden = false; }
          return;
        }
        t.value = '';
        if (familias().indexOf(v) < 0) guardar(cajaFamilias(), familias().concat([v]));
        return;
      }
      var el = t.closest('[data-campo]');
      if (el) guardar(el, valorDe(el));
    });

    function recargarTodo() {
      var cid = raiz().dataset.cid;
      T.refrescarTarjeta(cid);
      return T.abrir(cid);
    }
    panel.addEventListener('click', function (ev) {
      if (!raiz()) return;
      var b;
      if ((b = ev.target.closest('[data-quitar-familia]'))) {
        var f = b.closest('[data-familia]').dataset.familia;
        guardar(cajaFamilias(), familias().filter(function (x) { return x !== f; }));
      } else if ((b = ev.target.closest('[data-sumar-familia]'))) {
        if (familias().indexOf(b.dataset.sumarFamilia) < 0) guardar(cajaFamilias(), familias().concat([b.dataset.sumarFamilia]));
      } else if ((b = ev.target.closest('[data-poner]'))) {
        var campo = cuerpo.querySelector('[data-campo="' + b.dataset.poner + '"]');
        campo.value = b.dataset.valor;
        guardar(campo, campo.value);
      } else if ((b = ev.target.closest('[data-sumar-ref]'))) {
        b.disabled = true;
        var fd = new FormData();
        fd.append('referente_ids', b.dataset.sumarRef);
        fetch(b.dataset.url, {method: 'POST', headers: H, body: fd}).then(T.json).then(recargarTodo)
          .catch(function (e) { b.disabled = false; avisar(T.mensaje(e)); });
      } else if ((b = ev.target.closest('[data-quitar-ref]'))) {
        b.disabled = true;
        fetch(b.dataset.quitarRef, {method: 'POST', headers: H}).then(T.json).then(recargarTodo)
          .catch(function (e) { b.disabled = false; avisar(T.mensaje(e)); });
      } else if ((b = ev.target.closest('[data-sugerir-ia]'))) {
        b.disabled = true;
        fetch(b.dataset.sugerirIa, {method: 'POST', headers: H}).then(T.json)
          .then(function () { return T.abrir(raiz().dataset.cid); })
          .catch(function (e) { b.disabled = false; avisar(T.mensaje(e)); });
      } else if (ev.target.closest('[data-aflojar]')) {
        cargarSugeridos('?todas=1');
      }
    });
  })();
</script>
```

- [ ] **Step 6: Append the panel CSS**

Append to the «Tablero de Sprints» block of `static/style.css`:

```css
.panel-seccion h3 { margin: 0; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.panel-fila { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); gap: .6rem; }
.panel-fila-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.panel-opciones { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .3rem; }
.panel-opciones label { display: inline-flex; align-items: center; border: 1px solid var(--border); border-radius: 999px;
  padding: .2rem .7rem; cursor: pointer; font-size: .85rem; margin: 0; position: relative; }
.panel-opciones input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.panel-opciones label:has(input:checked) { background: var(--accent-grad); color: #fff; border-color: transparent; }
.panel-opciones label:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.panel-sugerencias { margin: 0; font-size: .85rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: .3rem; align-items: center; }
.chip-sugerencia { border: 1px dashed var(--border); background: var(--panel-2); color: var(--text); border-radius: 999px;
  padding: .1rem .6rem; font-size: .8rem; cursor: pointer; max-width: 100%; overflow-wrap: anywhere; text-align: left; }
.panel-familias { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.chip-familia { display: inline-flex; gap: .3rem; align-items: center; border: 1px solid var(--accent); border-radius: 999px;
  padding: .1rem .6rem; font-size: .8rem; background: var(--panel-2); }
.chip-familia button { background: none; border: 0; padding: 0; color: var(--muted); cursor: pointer; min-height: 0; }
.panel-familia-buscar { flex: 1 1 180px; min-width: 0; }
.panel-elegidos { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .4rem; }
.panel-elegido { position: relative; margin: 0; aspect-ratio: 1; border-radius: 8px; overflow: hidden; background: var(--panel-2);
  border: 1px solid var(--border); }
.panel-elegido img { width: 100%; height: 100%; object-fit: cover; display: block; }
.panel-elegido-vacio { border-style: dashed; }
.panel-elegido figcaption { position: absolute; left: 0; right: 0; bottom: 0; font-size: .7rem; background: var(--panel); padding: .1rem .3rem; }
.panel-quitar, .panel-sumar { position: absolute; top: 4px; right: 4px; width: 28px; height: 28px; min-height: 0; border-radius: 999px;
  border: 1px solid var(--border); background: var(--panel); color: var(--text); cursor: pointer; line-height: 1; padding: 0; }
.panel-sugeridos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 110px), 1fr)); gap: .5rem; }
.panel-sugerido { position: relative; margin: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--panel-2); }
.panel-sugerido img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
.panel-sugerido figcaption { font-size: .72rem; padding: .25rem .35rem; overflow-wrap: anywhere; }
.panel-acciones { display: flex; flex-wrap: wrap; gap: .4rem; }
.panel-sub { margin: 0; font-size: .85rem; }
.panel-campana-aviso { background: var(--panel-2); border-left: 3px solid var(--warn); padding: .4rem .6rem; margin: .6rem 0 0; font-size: .85rem; }
.panel-campana-aviso[hidden] { display: none; }
.panel-subir form { display: grid; gap: .5rem; margin-top: .5rem; }
.panel-campana-pie { display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap;
  border-top: 1px solid var(--border); margin-top: 1rem; padding-top: .8rem; }
@media (max-width: 760px) {
  .panel-elegidos { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py tests/test_sprints_temporada_opcional.py tests/test_base_visual.py tests/test_movil.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A sprints/rutas.py templates/ static/style.css tests/test_sprints_tablero_rutas.py tests/test_rutas_sprints.py
git commit -m "Sprints tablero: panel de la campaña (se guarda solo), sugeridos por enfoque y sin las mini-pantallas viejas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(`git add -A templates/` records the three deleted `_sprint_*_ajax.html`.)

---

### Task 9: Documentación, suite completa, verificación en pantalla, ensayo de la migración y despliegue

This task is run by the controller (not a subagent): it touches the local preview, the production DB copy and the VPS.

**Files:**
- Modify: `CLAUDE.md` (the «Sprints de contenido» paragraph)

- [ ] **Step 1: CLAUDE.md**

In the «**Sprints de contenido**» paragraph: replace «as a matrix persona × producto × temporada. Tables `persona`, `temporada`, `sprint`, `campana` (UNIQUE `uq_campana_combinacion` on sprint + persona + catalogo_id + temporada), …» with «as a board (spec `docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`): «+ Nuevo sprint» is a short form (month, país/idioma, optional «momento del mes» from `sprints.calendario.presets` or free text, brands to imitate) and the sprint page is a board with one card per campaign plus a side panel (`_sprint_panel.html`, fetched; all its JS lives in `sprint_detalle.html`) that saves field by field (`sprints.campana_campo` / `sprints.sprint_campo`). Tables `persona`, `temporada`, `sprint` (`pais`, `idioma`, `marcas`, `momento` since 0021), `campana` (`consciencia`, `dolor`, `familias`, and `pais`/`idioma`/`marcas` that override the sprint's — NULL inherits, read through `sprints.datos.efectivos`; no uniqueness since 0021, `campanas_identicas` only warns), …». Also add: «Free suggestions for a campaign come from `referentes.sugerir.sugerir_campana` (filters etapa + consciencia + familias, loosens familias then consciencia, ranks brands → language → variantes × días); «Sugerir con IA» uses the same candidates (`candidatos_aflojando`). Generic personas are no longer auto-created.» Keep the rest of the paragraph.

- [ ] **Step 2: Full suite**

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -p no:cacheprovider`
Expected: all pass (report the count; slow tests included).

- [ ] **Step 3: Local visual check (no real keys)**

Upgrade the worktree's local copy of the DB (`data/creatv.db`, untracked) with `CREATV_DB_URL=sqlite:///<worktree>/data/creatv.db venv/bin/alembic upgrade head`, start the local launcher on port 5072 (entry «ui-base-visual» in the main checkout's `.claude/launch.json`, restored with `git -C /Users/colorado/Documents/GitHub/iaplusyou checkout -- .claude/launch.json` afterwards), confirm Configuración › Puesta a punto shows every key as «falta», then at 1280×800 and 375×812: create a sprint from the tab, add a campaign, open the panel, change etapa/consciencia/dolor/familias/país/marcas/piezas, add and remove a sugerido, reload with `?panel=`, and check `document.documentElement.scrollWidth <= window.innerWidth` on the tab, the board and with the panel open. Screenshot the board and the panel for the user.

- [ ] **Step 4: Rehearse 0021 on a production copy**

Back up the production DB on the VPS with `sqlite3.Connection.backup()` to `/home/deploy/respaldos/creatv-<fecha>-pre0021.db`, copy it to the scratchpad, run `alembic upgrade head` against the copy, and compare `SELECT COUNT(*)` of `sprint`, `campana`, `referencia`, `campana_pieza` before/after (must match) plus `PRAGMA foreign_key_check` (empty).

- [ ] **Step 5: Merge and deploy**

`git fetch origin && git rebase origin/main` (resolve conflicts; re-run the suite), `git push origin sprints-tablero:main`. On the VPS: `cd iaplusyou && git pull --ff-only && venv/bin/alembic upgrade head`; check no `tarea` is `en_curso`/`pendiente` before restarting `creatv-worker`; `systemctl restart iaplusyou creatv-worker`; `curl -s -o /dev/null -w "%{http_code}" https://app.creatvmachine.com/login` → 200 and the served `style.css` contains «Tablero de Sprints (2026-09-26)».

- [ ] **Step 6: Memory**

Update the memory file `sprints-contenido-estado.md` (tablero entrega 1 in production, date, migration 0021, what entrega 2 covers) and the MEMORY.md line.
