# Meta rendimiento — E1 «Ver todo» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un proyecto de Creatv lee métricas de varias cuentas publicitarias de Meta (las 7 de HappyFlops) y las muestra en una pestaña «Meta»: cuentas, campañas, conjuntos y anuncios, «Todas» en USD, con el veredicto de cada anuncio.

**Architecture:** Paquete nuevo `meta_rendimiento/` (cuentas, graph, tasas, datos, sync, panel, rutas) + tareas del worker en `tareas/meta_rendimiento.py` + migración 0033 con seis tablas. Lectura de Graph con token explícito (sin el estado global de `meta_ads.auth`). La pestaña pinta un contenedor y pide el panel por fetch, como Triple Whale. La conexión de Meta acepta conectar sin Página («solo métricas»).

**Tech Stack:** Python 3, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (WAL), Alembic, requests, pytest, Jinja2.

**Spec:** `docs/superpowers/specs/2026-10-08-meta-rendimiento-design.md` (§1–§8, §11–§13; §9 y §10 son E2/E3, fuera de este plan).

## Global Constraints

- Directorio de trabajo: `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/meta-varias-cuentas`. Python: `../../../venv/bin/python3`. Pruebas: `../../../venv/bin/python3 -m pytest -q`.
- Todo texto visible pasa por el catálogo: `gettext` / `ngettext` de `flask_babel` en Python, `{{ _('…') }}` en plantillas, `idiomas.N_` en constantes. El español es el msgid.
- Leer de Meta no cobra: las tareas de copia van con `max_intentos=2`. Nada de este plan cobra a ningún proveedor.
- Ningún token en errores, eventos, flashes, registros ni plantillas: los textos de error se pasan por `cola.sin_token`. Un `requests` exception se resume con `type(e).__name__` (su `str` puede llevar la URL con el token). Las URL `paging.next` de Meta llevan el token: nunca se registran.
- POST de rutas nuevas: rechazar `Sec-Fetch-Site` distinto de `same-origin`/`none` (403), como `triple_whale/rutas.py::_mismo_origen`.
- Cada lista es UNA consulta agregada (nada de una consulta por fila). Las `<img>` llevan `loading="lazy"`. Las barras de progreso van con `data-poll-job`, nunca con `<script>` en el fragmento.
- Único escritor: `meta_cuenta` solo desde `meta_rendimiento/cuentas.py`; las tablas de copia (`meta_cuenta_dia`, `meta_anuncio_dia`, `meta_objeto`, `meta_alcance`) solo desde `meta_rendimiento/datos.py`; `tasa_cambio` solo desde `meta_rendimiento/tasas.py`.
- Las compras salen del primer tipo presente de `("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")`.
- Fechas en texto `AAAA-MM-DD`; marcas de tiempo con `db.ahora()`.
- Cada tarea termina con su commit (mensaje en español, cuerpo con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). Antes de commitear: `ls .git` del worktree no debe tener `MERGE_HEAD`/`REBASE_HEAD` (en un worktree, `git rev-parse --git-dir`).
- Los hooks del repo compilan cada `.py` y validan cada plantilla al editar: si un hook frena, se corrige, no se esquiva.

---

### Task 1: Tablas y migración 0033

**Files:**
- Modify: `db.py` (después de `tw_producto_dia`, antes de `crear_todo`)
- Create: `migrations/versions/0033_meta_rendimiento.py`
- Test: `tests/test_meta_rend_migracion.py`

**Interfaces:**
- Produces: `db.meta_cuenta`, `db.meta_cuenta_dia`, `db.meta_anuncio_dia`, `db.meta_objeto`, `db.meta_alcance`, `db.tasa_cambio` (SQLAlchemy `Table`), migración `revision='0033'`, `down_revision='0032'`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_meta_rend_migracion.py
"""Migración 0033 (spec 2026-10-08 meta rendimiento §4): las seis tablas existen
con sus restricciones únicas, y el downgrade las borra."""
import os
import subprocess
import sys

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLAS = ("meta_cuenta", "meta_cuenta_dia", "meta_anuncio_dia", "meta_objeto", "meta_alcance", "tasa_cambio")


def _alembic(tmp_path, *args):
    env = dict(os.environ, CREATV_DB_URL=f"sqlite:///{tmp_path / 'm.db'}")
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=RAIZ, env=env, check=True,
                   capture_output=True, text=True)
    return sa.create_engine(env["CREATV_DB_URL"])


def test_upgrade_crea_las_tablas_y_downgrade_las_borra(tmp_path):
    eng = _alembic(tmp_path, "upgrade", "head")
    nombres = set(sa.inspect(eng).get_table_names())
    assert set(TABLAS) <= nombres
    uq = {u["name"] for u in sa.inspect(eng).get_unique_constraints("meta_anuncio_dia")}
    assert "uq_meta_anuncio_dia" in uq
    indices = {i["name"]: i for i in sa.inspect(eng).get_indexes("meta_cuenta")}
    assert indices["uq_meta_cuenta_act"]["unique"]
    eng.dispose()
    eng = _alembic(tmp_path, "downgrade", "0032")
    assert not set(TABLAS) & set(sa.inspect(eng).get_table_names())


def test_db_crear_todo_coincide(base_temporal):
    nombres = set(sa.inspect(base_temporal.engine()).get_table_names())
    assert set(TABLAS) <= nombres
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../../venv/bin/python3 -m pytest tests/test_meta_rend_migracion.py -q`
Expected: FAIL (no existen las tablas).

- [ ] **Step 3: Add the tables to `db.py`**

Insertar antes de `def crear_todo():`:

```python
# --- Meta: rendimiento de varias cuentas por proyecto (spec 2026-10-08 meta rendimiento §4, migración 0033) ---
# Las cuentas publicitarias que un proyecto LEE (aparte de la única con la que lanza, en meta.json).
# Único escritor: meta_rendimiento/cuentas.py. Una cuenta solo puede estar en un proyecto.
meta_cuenta = Table("meta_cuenta", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("ad_account_id", String(40), nullable=False),     # «act_…»
    Column("nombre", Text),
    Column("moneda", String(3)),
    Column("zona_horaria", String(60)),
    Column("pais", String(2)),                               # ISO-2 o None (World Wide)
    Column("estado", String(12), default="nueva"),           # nueva|copiando|ok|error
    Column("error", Text),
    Column("ultima_copia", String(19)),
    Column("agregada_por", String(80)),
    Column("extra", JSON, default=dict),                     # backfill_hecho, cuenta{account_status,…}
    sa.Index("uq_meta_cuenta_act", "ad_account_id", unique=True),
    sqlite_autoincrement=True,
)

# La cuenta por día (level=account): 13 meses. El alcance diario sí es de ese día (no se suma entre días).
meta_cuenta_dia = Table("meta_cuenta_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("ad_account_id", String(40), nullable=False),
    Column("fecha", String(10), nullable=False),
    Column("gasto", Float, default=0.0), Column("impresiones", Integer, default=0),
    Column("alcance", Integer, default=0), Column("clics", Integer, default=0),
    Column("clics_salida", Integer, default=0), Column("compras", Float, default=0.0),
    Column("valor", Float, default=0.0), Column("vistas_3s", Integer, default=0),
    Column("thruplays", Integer, default=0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "ad_account_id", "fecha", name="uq_meta_cuenta_dia"),
)

# El anuncio por día (level=ad): 90 días (tareas/meta_rendimiento borra lo anterior). Campaña y
# conjunto van como id; los nombres viven en meta_objeto.
meta_anuncio_dia = Table("meta_anuncio_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("ad_account_id", String(40), nullable=False),
    Column("fecha", String(10), nullable=False),
    Column("campaign_id", String(40)), Column("adset_id", String(40)),
    Column("ad_id", String(40), nullable=False),
    Column("gasto", Float, default=0.0), Column("impresiones", Integer, default=0),
    Column("clics", Integer, default=0), Column("clics_salida", Integer, default=0),
    Column("compras", Float, default=0.0), Column("valor", Float, default=0.0),
    Column("vistas_3s", Integer, default=0), Column("thruplays", Integer, default=0),
    Column("p25", Integer, default=0), Column("p50", Integer, default=0),
    Column("p75", Integer, default=0), Column("p100", Integer, default=0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "ad_account_id", "ad_id", "fecha", name="uq_meta_anuncio_dia"),
    sa.Index("ix_meta_anuncio_dia_cuenta_fecha", "cliente", "ad_account_id", "fecha"),
)

# Campañas, conjuntos y anuncios: nombre, estado, presupuesto, aprendizaje, miniatura.
meta_objeto = Table("meta_objeto", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("ad_account_id", String(40), nullable=False),
    Column("nivel", String(10), nullable=False),             # campana|conjunto|anuncio
    Column("objeto_id", String(40), nullable=False),
    Column("padre_id", String(40)),                          # conjunto -> campaña, anuncio -> conjunto
    Column("campaign_id", String(40)),
    Column("nombre", Text),
    Column("estado", String(30)),                            # effective_status; None = no vino (archivado/borrado)
    Column("objetivo", String(40)), Column("optimizacion", String(40)),
    Column("presupuesto_diario", Float), Column("presupuesto_total", Float),   # en la moneda de la cuenta
    Column("estrategia_puja", String(40)),
    Column("aprendizaje", String(20)),                       # learning_stage_info.status
    Column("creative_id", String(40)), Column("miniatura_url", Text), Column("video_id", String(40)),
    Column("creado_en_meta", String(25)),
    Column("actualizado_en", String(19), nullable=False),
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("cliente", "objeto_id", name="uq_meta_objeto"),
    sa.Index("ix_meta_objeto_cuenta_nivel", "cliente", "ad_account_id", "nivel"),
)

# Alcance y frecuencia de una ventana (gente única: no se suma por días).
meta_alcance = Table("meta_alcance", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("ad_account_id", String(40), nullable=False),
    Column("nivel", String(10), nullable=False),             # cuenta|campana
    Column("objeto_id", String(40), nullable=False),         # act_… para la cuenta
    Column("ventana", Integer, nullable=False),              # 7|14|30|90
    Column("alcance", Integer, default=0),
    Column("frecuencia", Float),
    Column("calculado_en", String(19), nullable=False),
    sa.UniqueConstraint("cliente", "objeto_id", "ventana", name="uq_meta_alcance"),
)

# Tasa de cambio diaria del BCE (frankfurter): cuántos USD vale una unidad de `moneda`.
tasa_cambio = Table("tasa_cambio", metadata,
    Column("id", Integer, primary_key=True),
    Column("fecha", String(10), nullable=False),
    Column("moneda", String(3), nullable=False),
    Column("usd_por_unidad", Float, nullable=False),
    Column("fuente", String(20), default="bce"),
    Column("creado_en", String(19), nullable=False),
    sa.UniqueConstraint("fecha", "moneda", name="uq_tasa_cambio"),
)
```

- [ ] **Step 4: Write the migration** `migrations/versions/0033_meta_rendimiento.py`

```python
"""Meta: rendimiento de varias cuentas por proyecto (spec 2026-10-08 meta rendimiento §4)

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-08 12:00:00.000000

Seis tablas nuevas, sin tocar las existentes: meta_cuenta (las cuentas que un proyecto lee;
una cuenta en un solo proyecto), meta_cuenta_dia, meta_anuncio_dia, meta_objeto, meta_alcance
y tasa_cambio. El downgrade las borra (son copias de Meta y del BCE: se vuelven a traer).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _metricas_dia():
    return [sa.Column('gasto', sa.Float()), sa.Column('impresiones', sa.Integer()),
            sa.Column('clics', sa.Integer()), sa.Column('clics_salida', sa.Integer()),
            sa.Column('compras', sa.Float()), sa.Column('valor', sa.Float()),
            sa.Column('vistas_3s', sa.Integer()), sa.Column('thruplays', sa.Integer())]


def upgrade() -> None:
    op.create_table(
        'meta_cuenta',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nombre', sa.Text()), sa.Column('moneda', sa.String(3)),
        sa.Column('zona_horaria', sa.String(60)), sa.Column('pais', sa.String(2)),
        sa.Column('estado', sa.String(12)), sa.Column('error', sa.Text()),
        sa.Column('ultima_copia', sa.String(19)), sa.Column('agregada_por', sa.String(80)),
        sa.Column('extra', sa.JSON()),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_meta_cuenta_cliente', 'meta_cuenta', ['cliente'])
    op.create_index('uq_meta_cuenta_act', 'meta_cuenta', ['ad_account_id'], unique=True)

    op.create_table(
        'meta_cuenta_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        *_metricas_dia(), sa.Column('alcance', sa.Integer()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'ad_account_id', 'fecha', name='uq_meta_cuenta_dia'),
    )
    op.create_table(
        'meta_anuncio_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('campaign_id', sa.String(40)), sa.Column('adset_id', sa.String(40)),
        sa.Column('ad_id', sa.String(40), nullable=False),
        *_metricas_dia(),
        sa.Column('p25', sa.Integer()), sa.Column('p50', sa.Integer()),
        sa.Column('p75', sa.Integer()), sa.Column('p100', sa.Integer()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'ad_account_id', 'ad_id', 'fecha', name='uq_meta_anuncio_dia'),
    )
    op.create_index('ix_meta_anuncio_dia_cuenta_fecha', 'meta_anuncio_dia', ['cliente', 'ad_account_id', 'fecha'])
    op.create_table(
        'meta_objeto',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nivel', sa.String(10), nullable=False),
        sa.Column('objeto_id', sa.String(40), nullable=False),
        sa.Column('padre_id', sa.String(40)), sa.Column('campaign_id', sa.String(40)),
        sa.Column('nombre', sa.Text()), sa.Column('estado', sa.String(30)),
        sa.Column('objetivo', sa.String(40)), sa.Column('optimizacion', sa.String(40)),
        sa.Column('presupuesto_diario', sa.Float()), sa.Column('presupuesto_total', sa.Float()),
        sa.Column('estrategia_puja', sa.String(40)), sa.Column('aprendizaje', sa.String(20)),
        sa.Column('creative_id', sa.String(40)), sa.Column('miniatura_url', sa.Text()),
        sa.Column('video_id', sa.String(40)), sa.Column('creado_en_meta', sa.String(25)),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('extra', sa.JSON()),
        sa.UniqueConstraint('cliente', 'objeto_id', name='uq_meta_objeto'),
    )
    op.create_index('ix_meta_objeto_cuenta_nivel', 'meta_objeto', ['cliente', 'ad_account_id', 'nivel'])
    op.create_table(
        'meta_alcance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nivel', sa.String(10), nullable=False),
        sa.Column('objeto_id', sa.String(40), nullable=False),
        sa.Column('ventana', sa.Integer(), nullable=False),
        sa.Column('alcance', sa.Integer()), sa.Column('frecuencia', sa.Float()),
        sa.Column('calculado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'objeto_id', 'ventana', name='uq_meta_alcance'),
    )
    op.create_table(
        'tasa_cambio',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('moneda', sa.String(3), nullable=False),
        sa.Column('usd_por_unidad', sa.Float(), nullable=False),
        sa.Column('fuente', sa.String(20)),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('fecha', 'moneda', name='uq_tasa_cambio'),
    )


def downgrade() -> None:
    for tabla in ('tasa_cambio', 'meta_alcance', 'meta_objeto', 'meta_anuncio_dia', 'meta_cuenta_dia', 'meta_cuenta'):
        op.drop_table(tabla)
```

- [ ] **Step 5: Run the tests**

Run: `../../../venv/bin/python3 -m pytest tests/test_meta_rend_migracion.py tests/test_migracion_tw_tiendas.py -q`
Expected: PASS. Si alguna prueba existente compara `db.metadata` contra `alembic upgrade head` (busca `compare_metadata` en `tests/`), también debe pasar.

- [ ] **Step 6: Commit**

```bash
git add db.py migrations/versions/0033_meta_rendimiento.py tests/test_meta_rend_migracion.py
git commit -m "Meta rendimiento: tablas y migración 0033"
```

---

### Task 2: Lectura de Graph con token explícito (`meta_rendimiento/graph.py`)

**Files:**
- Create: `meta_rendimiento/__init__.py` (docstring del paquete, nada más)
- Create: `meta_rendimiento/graph.py`
- Modify: `meta_errores.py` (función pública `es_codigo_limite`)
- Test: `tests/test_meta_rend_graph.py`

**Interfaces:**
- Consumes: `meta_conexion.GRAPH_URL`, `meta_conexion.CODIGOS_CONEXION_ROTA`, `meta_errores._LIMITE` (vía la función nueva).
- Produces:
  - `class ErrorGraph(Exception)` con atributos `codigo: int|None`, `limite: bool`, `token_roto: bool`; `str(e)` ya traducido y sin token.
  - `get(edge: str, token: str, params: dict|None = None, timeout: int = 60) -> dict`
  - `post(edge: str, token: str, params: dict|None = None, timeout: int = 60) -> dict`
  - `paginar(edge: str, token: str, params: dict|None = None, max_paginas: int = 200, timeout: int = 60) -> list[dict]`
  - `informe(ad_account_id: str, token: str, params: dict, espera_max_s: int = 600, intervalo_s: float = 5, dormir=time.sleep) -> list[dict]` — insights asíncronos.
  - `acciones(lista, tipos) -> float` — suma el primer tipo presente.
  - `TIPOS_COMPRA = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")`
  - `meta_errores.es_codigo_limite(codigo) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meta_rend_graph.py
"""Lectura de Graph para el rendimiento de Meta (spec §6): paginación, informe
asíncrono, errores en palabras y nunca el token en un error."""
import pytest

from meta_rendimiento import graph

TOKEN = "EAAtoken-secreto-llave-de-prueba"


class _Resp:
    def __init__(self, datos, status=200):
        self._datos, self.status_code, self.ok = datos, status, status < 400
        self.content = b"x"

    def json(self):
        return self._datos


@pytest.fixture()
def http(monkeypatch):
    """Cola de respuestas por llamada; guarda (método, url, params)."""
    estado = {"respuestas": [], "llamadas": []}

    def _req(metodo):
        def f(url, params=None, timeout=None, data=None):
            estado["llamadas"].append((metodo, url, dict(params or data or {})))
            r = estado["respuestas"].pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return f
    monkeypatch.setattr(graph.requests, "get", _req("GET"))
    monkeypatch.setattr(graph.requests, "post", _req("POST"))
    return estado


def test_paginar_sigue_next_y_manda_el_token_solo_en_params(http):
    http["respuestas"] = [_Resp({"data": [{"id": 1}], "paging": {"next": "https://graph.facebook.com/v25.0/x?after=A&access_token=" + TOKEN}}),
                          _Resp({"data": [{"id": 2}], "paging": {}})]
    assert graph.paginar("act_1/campaigns", TOKEN, {"limit": 500}) == [{"id": 1}, {"id": 2}]
    assert http["llamadas"][0][2]["access_token"] == TOKEN
    assert TOKEN not in http["llamadas"][0][1]


def test_error_de_limite_y_de_token_en_palabras_sin_token(http):
    http["respuestas"] = [_Resp({"error": {"code": 17, "message": f"User request limit reached {TOKEN}"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.limite and not e.value.token_roto and TOKEN not in str(e.value)
    http["respuestas"] = [_Resp({"error": {"code": 190, "message": "Error validating access token"}}, 400)]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert e.value.token_roto


def test_red_caida_no_filtra_la_url(http):
    import requests
    http["respuestas"] = [requests.ConnectionError(f"https://graph.facebook.com/x?access_token={TOKEN}")]
    with pytest.raises(graph.ErrorGraph) as e:
        graph.get("act_1", TOKEN)
    assert TOKEN not in str(e.value) and "ConnectionError" in str(e.value)


def test_informe_asincrono_espera_y_pagina(http):
    http["respuestas"] = [_Resp({"report_run_id": "999"}),
                          _Resp({"async_status": "Job Running", "async_percent_completion": 40}),
                          _Resp({"async_status": "Job Completed", "async_percent_completion": 100}),
                          _Resp({"data": [{"ad_id": "a1"}], "paging": {}})]
    filas = graph.informe("act_1", TOKEN, {"level": "ad"}, dormir=lambda s: None)
    assert filas == [{"ad_id": "a1"}]
    assert http["llamadas"][0][0] == "POST" and http["llamadas"][0][1].endswith("/act_1/insights")
    assert http["llamadas"][-1][1].endswith("/999/insights")


def test_informe_fallido_o_eterno(http):
    http["respuestas"] = [_Resp({"report_run_id": "9"}), _Resp({"async_status": "Job Failed"})]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, dormir=lambda s: None)
    http["respuestas"] = [_Resp({"report_run_id": "9"})] + [_Resp({"async_status": "Job Running"}) for _ in range(5)]
    with pytest.raises(graph.ErrorGraph):
        graph.informe("act_1", TOKEN, {}, espera_max_s=3, intervalo_s=1, dormir=lambda s: None)


def test_acciones_toma_el_primer_tipo_presente():
    lista = [{"action_type": "omni_purchase", "value": "5"}, {"action_type": "purchase", "value": "4"}]
    assert graph.acciones(lista, graph.TIPOS_COMPRA) == 4.0
    assert graph.acciones([{"action_type": "omni_purchase", "value": "5"}], graph.TIPOS_COMPRA) == 5.0
    assert graph.acciones(None, graph.TIPOS_COMPRA) == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `../../../venv/bin/python3 -m pytest tests/test_meta_rend_graph.py -q`
Expected: FAIL (`ModuleNotFoundError: meta_rendimiento`).

- [ ] **Step 3: Implement**

`meta_errores.py`, debajo de `es_limite`:

```python
def es_codigo_limite(codigo):
    """True si el código numérico de Graph es un límite de uso (esperar y reintentar)."""
    try:
        return int(codigo) in _LIMITE
    except (TypeError, ValueError):
        return False
```

`meta_rendimiento/__init__.py`:

```python
"""Meta: rendimiento de varias cuentas por proyecto (spec docs/superpowers/specs/2026-10-08-meta-rendimiento-design.md).

cuentas (qué cuentas lee el proyecto) · graph (lectura con token explícito) · tasas (USD del BCE) ·
datos (copias en la base) · sync (copia de una cuenta) · panel (la pestaña) · rutas (blueprint)."""
```

`meta_rendimiento/graph.py`:

```python
"""Lectura de la Graph API con el token y la cuenta como argumentos (spec §2.6).

No usa `meta_ads.auth` (estado global con candado del lanzador): copiar siete
cuentas en un hilo del worker no debe bloquear un lanzamiento. Leer no cobra.
Ningún error lleva el token: los de red se resumen con el nombre de la
excepción (su texto puede traer la URL con `access_token`), y los de Meta pasan
por `cola.sin_token`. Las URL `paging.next` traen el token: nunca se registran."""
import time

import requests
from flask_babel import gettext

import cola
import meta_conexion
import meta_errores

TIPOS_COMPRA = ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase")


class ErrorGraph(Exception):
    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.limite = meta_errores.es_codigo_limite(codigo)
        self.token_roto = codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102


def _url(edge):
    return edge if edge.startswith("https://") else f"{meta_conexion.GRAPH_URL}/{edge.lstrip('/')}"


def _respuesta(resp):
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or (isinstance(datos, dict) and "error" in datos):
        err = (datos or {}).get("error") or {}
        codigo = err.get("code")
        if meta_errores.es_codigo_limite(codigo):
            texto = gettext("Meta pidió esperar (límite de uso de la API). La próxima copia lo reintenta sola.")
        elif codigo in meta_conexion.CODIGOS_CONEXION_ROTA or codigo == 102:
            texto = gettext("Meta rechazó el acceso: reconecta Meta en Configuración › Conexiones.")
        else:
            texto = gettext("Meta respondió: %(mensaje)s", mensaje=err.get("message") or f"HTTP {resp.status_code}")
        raise ErrorGraph(cola.recortar(cola.sin_token(texto), 500), codigo=codigo)
    return datos


def _llamar(metodo, edge, token, params, timeout):
    p = dict(params or {})
    p["access_token"] = token
    try:
        if metodo == "POST":
            resp = requests.post(_url(edge), data=p, timeout=timeout)
        else:
            resp = requests.get(_url(edge), params=p, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ErrorGraph(gettext("No pude hablar con Meta (%(error)s).", error=type(e).__name__)) from None
    return _respuesta(resp)


def get(edge, token, params=None, timeout=60):
    return _llamar("GET", edge, token, params, timeout)


def post(edge, token, params=None, timeout=60):
    return _llamar("POST", edge, token, params, timeout)


def paginar(edge, token, params=None, max_paginas=200, timeout=60):
    """Todas las filas de `data`, siguiendo el cursor `after` (no la URL `next`, que trae el token)."""
    p = dict(params or {})
    filas = []
    for _ in range(max_paginas):
        datos = get(edge, token, p, timeout)
        filas.extend(datos.get("data") or [])
        paging = datos.get("paging") or {}
        despues = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not despues:
            break
        p["after"] = despues
    return filas


def informe(ad_account_id, token, params, espera_max_s=600, intervalo_s=5, dormir=time.sleep):
    """Insights asíncronos (para level=ad con muchos días): crea el informe, espera
    a «Job Completed» y devuelve sus filas. ErrorGraph si falla o tarda más de `espera_max_s`."""
    run = post(f"{ad_account_id}/insights", token, params).get("report_run_id")
    if not run:
        raise ErrorGraph(gettext("Meta no creó el informe de métricas."))
    esperado = 0.0
    while True:
        estado = get(str(run), token, {"fields": "async_status,async_percent_completion"})
        st = estado.get("async_status")
        if st == "Job Completed":
            break
        if st in ("Job Failed", "Job Skipped"):
            raise ErrorGraph(gettext("Meta no pudo armar el informe de métricas (%(estado)s).", estado=st))
        if esperado >= espera_max_s:
            raise ErrorGraph(gettext("El informe de Meta tardó demasiado; la próxima copia lo reintenta."))
        dormir(intervalo_s)
        esperado += intervalo_s
    return paginar(f"{run}/insights", token, {"limit": 500})


def acciones(lista, tipos):
    """Valor del primer tipo de `tipos` presente en una lista `actions`/`action_values` de Meta."""
    por_tipo = {a.get("action_type"): a.get("value") for a in (lista or []) if isinstance(a, dict)}
    for t in tipos:
        if t in por_tipo:
            try:
                return float(por_tipo[t] or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0
```

Nota para la prueba de paginación: la primera respuesta del doble trae `paging.next` pero no `cursors.after`. Ajusta el doble a `{"data": [...], "paging": {"next": "…", "cursors": {"after": "A"}}}` para que `paginar` siga, y verifica que la segunda llamada lleva `params["after"] == "A"`.

- [ ] **Step 4: Run tests**

Run: `../../../venv/bin/python3 -m pytest tests/test_meta_rend_graph.py tests/test_meta_errores*.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/__init__.py meta_rendimiento/graph.py meta_errores.py tests/test_meta_rend_graph.py
git commit -m "Meta rendimiento: lectura de Graph con token explícito e informes asíncronos"
```

---

### Task 3: Tasas USD del BCE (`meta_rendimiento/tasas.py`)

**Files:**
- Create: `meta_rendimiento/tasas.py`
- Test: `tests/test_meta_rend_tasas.py`

**Interfaces:**
- Consumes: `db.tasa_cambio`, `conectores.url.abrir(url) -> respuesta` (`ErrorConector`).
- Produces:
  - `URL_BASE = "https://api.frankfurter.dev/v1"`
  - `asegurar(monedas: Iterable[str], desde: str, hasta: str) -> None` — nunca lanza; registra un warning si falla.
  - `mapa(moneda: str, desde: str, hasta: str) -> dict[str, float|None]` — un valor por día del rango (incluidos fines de semana con el último publicado anterior); USD → 1.0.
  - `usd(moneda: str, fecha: str) -> float|None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meta_rend_tasas.py
"""USD por día (spec §7): BCE por frankfurter, fines de semana con el último día
publicado, USD = 1 sin pedir nada, y sin tasa = None (nunca inventada)."""
import json

from meta_rendimiento import tasas


class _Resp:
    def __init__(self, datos, status=200):
        self.status_code, self._d = status, datos

    def json(self):
        return self._d

    def close(self):
        pass


def test_asegurar_guarda_y_mapa_rellena_fines_de_semana(base_temporal, monkeypatch):
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-02": {"USD": 0.09942}, "2026-10-05": {"USD": 0.09957}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["SEK", "USD"], "2026-10-02", "2026-10-05")
    assert len(pedidas) == 1 and "from=SEK" in pedidas[0] and "2026-10-02..2026-10-05" in pedidas[0]
    m = tasas.mapa("SEK", "2026-10-02", "2026-10-05")
    assert m == {"2026-10-02": 0.09942, "2026-10-03": 0.09942, "2026-10-04": 0.09942, "2026-10-05": 0.09957}
    assert tasas.mapa("USD", "2026-10-02", "2026-10-03") == {"2026-10-02": 1.0, "2026-10-03": 1.0}
    # Ya guardadas: no vuelve a pedir.
    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05")
    assert len(pedidas) == 1


def test_sin_tasa_es_none_y_un_fallo_no_lanza(base_temporal, monkeypatch):
    def abrir(url, **_):
        raise tasas.url_conector.ErrorConector("caído")
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["NOK"], "2026-10-01", "2026-10-02")
    assert tasas.mapa("NOK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}
    assert tasas.usd("NOK", "2026-10-01") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `../../../venv/bin/python3 -m pytest tests/test_meta_rend_tasas.py -q` → FAIL.

- [ ] **Step 3: Implement** `meta_rendimiento/tasas.py`

```python
"""USD por unidad de cada moneda, por día (spec §7). Fuente: el BCE vía
frankfurter (gratis, sin llave). Único escritor de `tasa_cambio`.

Un día sin publicación (fin de semana, festivo) usa el último publicado
anterior. Sin tasa conocida el valor es None: la pantalla dice «USD no
disponible», nunca una tasa inventada."""
import logging
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from conectores import url as url_conector

log = logging.getLogger("creatv.meta_rendimiento.tasas")
URL_BASE = "https://api.frankfurter.dev/v1"
_HOLGURA_DIAS = 7   # para encontrar la tasa anterior a un lunes o a un festivo


def _dias(desde, hasta):
    d, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    while d <= fin:
        yield d.isoformat()
        d += timedelta(days=1)


def _guardadas(moneda, desde, hasta):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.tasa_cambio.c.fecha, db.tasa_cambio.c.usd_por_unidad).where(
            db.tasa_cambio.c.moneda == moneda, db.tasa_cambio.c.fecha >= desde,
            db.tasa_cambio.c.fecha <= hasta).order_by(db.tasa_cambio.c.fecha)).all()
    return {f.fecha: f.usd_por_unidad for f in filas}


def asegurar(monedas, desde, hasta):
    """Pide al BCE lo que falte del rango. Nunca lanza (las métricas se ven igual, sin USD)."""
    inicio = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()
    for moneda in sorted({(m or "").upper() for m in monedas} - {"", "USD"}):
        ya = _guardadas(moneda, inicio, hasta)
        laborables = [d for d in _dias(desde, hasta) if date.fromisoformat(d).weekday() < 5]
        if ya and all(d in ya for d in laborables[:-1]):
            continue
        try:
            resp = url_conector.abrir(f"{URL_BASE}/{inicio}..{hasta}?from={moneda}&to=USD")
            try:
                datos = resp.json() if resp.status_code == 200 else {}
            finally:
                getattr(resp, "close", lambda: None)()
        except (url_conector.ErrorConector, ValueError) as e:
            log.warning("tasas %s: %s", moneda, type(e).__name__)
            continue
        filas = [{"fecha": f, "moneda": moneda, "usd_por_unidad": float(v["USD"]), "fuente": "bce",
                  "creado_en": db.ahora()}
                 for f, v in ((datos or {}).get("rates") or {}).items() if isinstance(v, dict) and v.get("USD")]
        if not filas:
            continue
        with db.conectar() as con:
            for fila in filas:
                con.execute(insert_sqlite(db.tasa_cambio).values(**fila).on_conflict_do_update(
                    index_elements=["fecha", "moneda"], set_={"usd_por_unidad": fila["usd_por_unidad"]}))


def mapa(moneda, desde, hasta):
    """{fecha: usd_por_unidad|None} para cada día del rango."""
    moneda = (moneda or "").upper()
    if moneda == "USD":
        return {d: 1.0 for d in _dias(desde, hasta)}
    inicio = (date.fromisoformat(desde) - timedelta(days=_HOLGURA_DIAS)).isoformat()
    guardadas = _guardadas(moneda, inicio, hasta)
    salida, ultima = {}, None
    for d in _dias(inicio, hasta):
        ultima = guardadas.get(d, ultima)
        if d >= desde:
            salida[d] = ultima
    return salida


def usd(moneda, fecha):
    return mapa(moneda, fecha, fecha).get(fecha)
```

- [ ] **Step 4: Run tests** → PASS. Si `asegurar` vuelve a pedir en la segunda llamada, revisa la condición `ya and all(...)`: con las tasas del 02 y del 05 guardadas, los laborables del rango 02..05 son 02 y 05, y `laborables[:-1]` es solo 02 (el último día puede no estar publicado aún).

- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/tasas.py tests/test_meta_rend_tasas.py
git commit -m "Meta rendimiento: tasas USD diarias del BCE"
```

---

### Task 4: Cuentas que lee el proyecto (`meta_rendimiento/cuentas.py`)

**Files:**
- Create: `meta_rendimiento/cuentas.py`
- Test: `tests/test_meta_rend_cuentas.py`

**Interfaces:**
- Consumes: `db.meta_cuenta`, `triple_whale.paises` (`_construir`, `_norm`, `es_pais`), `meta_rendimiento.datos.borrar_cuenta` (Task 5; en esta tarea se importa perezoso dentro de `elegir` y la prueba lo sustituye).
- Produces:
  - `normalizar_id(x: str) -> str` («123» → «act_123»)
  - `adivinar_pais(nombre: str) -> str|None`
  - `listar(cliente) -> list[dict]` (orden: nombre)
  - `cuenta(cliente, ad_account_id) -> dict|None`
  - `ids(cliente) -> list[str]`
  - `todas() -> list[tuple[str, str]]` (cliente, ad_account_id) de todos los proyectos
  - `dueno(ad_account_id) -> str|None`
  - `elegir(cliente, elegidas: list[dict], usuario=None) -> dict` con `{"agregadas": [ids], "quitadas": [ids], "rechazadas": [ids]}`. Cada elegida: `{"id", "name", "currency", "pais"}`; reemplaza la selección del proyecto; una cuenta de otro proyecto va a `rechazadas`.
  - `cambiar_pais(cliente, ad_account_id, pais: str|None) -> bool`
  - `actualizar(cliente, ad_account_id, **campos) -> None` (campos de la tabla)
  - `actualizar_extra(cliente, ad_account_id, cambios: dict) -> None` (mezcla en la misma transacción)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meta_rend_cuentas.py
"""Cuentas que un proyecto lee (spec §5): país adivinado por el nombre, una
cuenta en un solo proyecto, quitar borra sus copias."""
from meta_rendimiento import cuentas

HF = [{"id": "act_709406360806038", "name": "HappyFlops Norway", "currency": "SEK"},
      {"id": "act_883891256188845", "name": "HappyFlops Netherlands (Active)", "currency": "SEK"},
      {"id": "act_708698354181244", "name": "HappyFlops World Wide", "currency": "SEK"},
      {"id": "act_228061763662782", "name": "HappyFlops MX", "currency": "SEK"},
      {"id": "act_1236343913931133", "name": "HappyFlops Poland (old DK)", "currency": "SEK"},
      {"id": "act_335308812712423", "name": "HappyFlops Finland 2025", "currency": "SEK"}]


def test_adivinar_pais_por_nombre():
    esperado = ["NO", "NL", None, "MX", "PL", "FI"]
    assert [cuentas.adivinar_pais(c["name"]) for c in HF] == esperado
    assert cuentas.adivinar_pais("HappyFlops Sweden") == "SE"
    assert cuentas.adivinar_pais("") is None


def test_normalizar_id():
    assert cuentas.normalizar_id("123") == "act_123" and cuentas.normalizar_id("act_123") == "act_123"


def test_elegir_reemplaza_y_rechaza_cuentas_de_otro_proyecto(base_temporal, monkeypatch):
    borradas = []
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda c, a: borradas.append((c, a)))
    r = cuentas.elegir("happyflops", [dict(c, pais=cuentas.adivinar_pais(c["name"])) for c in HF[:3]], usuario="admin")
    assert sorted(r["agregadas"]) == sorted(c["id"] for c in HF[:3]) and not r["rechazadas"]
    assert {c["ad_account_id"]: c["pais"] for c in cuentas.listar("happyflops")}["act_709406360806038"] == "NO"
    r = cuentas.elegir("otro", [HF[0], HF[3]])
    assert r["rechazadas"] == ["act_709406360806038"] and r["agregadas"] == ["act_228061763662782"]
    assert cuentas.dueno("act_709406360806038") == "happyflops"
    r = cuentas.elegir("happyflops", [HF[0]])
    assert sorted(r["quitadas"]) == sorted(["act_883891256188845", "act_708698354181244"])
    assert ("happyflops", "act_883891256188845") in borradas
    assert cuentas.ids("happyflops") == ["act_709406360806038"]
    assert sorted(cuentas.todas()) == [("happyflops", "act_709406360806038"), ("otro", "act_228061763662782")]


def test_pais_invalido_se_guarda_vacio_y_cambiar_pais(base_temporal):
    cuentas.elegir("acme", [dict(HF[0], pais="ZZ")])
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] is None
    assert cuentas.cambiar_pais("acme", "act_709406360806038", "no")
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] == "NO"
    assert not cuentas.cambiar_pais("acme", "act_999", "NO")


def test_actualizar_extra_mezcla(base_temporal):
    cuentas.elegir("acme", [HF[0]])
    cuentas.actualizar_extra("acme", "act_709406360806038", {"a": 1})
    cuentas.actualizar_extra("acme", "act_709406360806038", {"b": 2})
    assert cuentas.cuenta("acme", "act_709406360806038")["extra"] == {"a": 1, "b": 2}
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement** `meta_rendimiento/cuentas.py`

```python
"""Las cuentas publicitarias que un proyecto LEE (spec §2.5 y §5). Único escritor de `meta_cuenta`.

Aparte de la cuenta única de `meta.json` (la que lanza experimentos). Una cuenta
solo puede estar en un proyecto: el índice único `uq_meta_cuenta_act` lo
garantiza y `elegir` la rechaza antes, así los datos de un cliente nunca
aparecen en otro."""
import re

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import db
from triple_whale import paises

_C = db.meta_cuenta.c
_CAMPOS = {"nombre", "moneda", "zona_horaria", "pais", "estado", "error", "ultima_copia"}


def normalizar_id(x):
    x = str(x or "").strip()
    return x if x.startswith("act_") else f"act_{x}"


def adivinar_pais(nombre):
    """«HappyFlops Poland (old DK)» -> «PL»: primero un nombre de país (en, es y lenguas locales), y si no hay,
    un código ISO de dos letras en mayúsculas («HappyFlops MX» -> «MX»). «World Wide» -> None."""
    mapa, validos = paises._construir()
    palabras = [p for p in re.split(r"[^A-Za-zÀ-ÿ]+", nombre or "") if p]
    for largo in (3, 2, 1):
        for i in range(len(palabras) - largo + 1):
            codigo = mapa.get(paises._norm("".join(palabras[i:i + largo])))
            if codigo:
                return codigo
    for p in palabras:
        if len(p) == 2 and p.isupper() and p in validos:
            return p
    return None


def _pais(valor):
    v = (valor or "").strip().upper()
    return v if v and paises.es_pais(v) else None


def _fila(r):
    d = dict(r._mapping)
    d["extra"] = d.get("extra") or {}
    return d


def listar(cliente):
    with db.conectar() as con:
        return [_fila(r) for r in con.execute(
            sa.select(db.meta_cuenta).where(_C.cliente == cliente).order_by(_C.nombre, _C.id))]


def cuenta(cliente, ad_account_id):
    with db.conectar() as con:
        r = con.execute(sa.select(db.meta_cuenta).where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id))).first()
    return _fila(r) if r else None


def ids(cliente):
    return [c["ad_account_id"] for c in listar(cliente)]


def todas():
    with db.conectar() as con:
        return [(r.cliente, r.ad_account_id) for r in con.execute(
            sa.select(_C.cliente, _C.ad_account_id).order_by(_C.cliente, _C.ad_account_id))]


def dueno(ad_account_id):
    with db.conectar() as con:
        return con.execute(sa.select(_C.cliente).where(_C.ad_account_id == normalizar_id(ad_account_id))).scalar()


def _borrar_copias(cliente, ad_account_id):
    from meta_rendimiento import datos  # noqa: PLC0415 — datos importa cuentas en sus pruebas
    datos.borrar_cuenta(cliente, ad_account_id)


def elegir(cliente, elegidas, usuario=None):
    """Deja en el proyecto exactamente `elegidas` (las de otro proyecto se rechazan)."""
    nuevas = {normalizar_id(c["id"]): c for c in elegidas or [] if c.get("id")}
    actuales = set(ids(cliente))
    agregadas, rechazadas = [], []
    ahora = db.ahora()
    for act, c in nuevas.items():
        if act in actuales:
            continue
        otro = dueno(act)
        if otro and otro != cliente:
            rechazadas.append(act)
            continue
        try:
            with db.conectar() as con:
                con.execute(db.meta_cuenta.insert().values(
                    cliente=cliente, creado_en=ahora, actualizado_en=ahora, ad_account_id=act,
                    nombre=c.get("name"), moneda=(c.get("currency") or "")[:3] or None,
                    pais=_pais(c.get("pais")), estado="nueva", agregada_por=usuario, extra={}))
            agregadas.append(act)
        except IntegrityError:
            rechazadas.append(act)
    quitadas = sorted(actuales - set(nuevas))
    for act in quitadas:
        with db.conectar() as con:
            con.execute(db.meta_cuenta.delete().where(_C.cliente == cliente, _C.ad_account_id == act))
        _borrar_copias(cliente, act)
    return {"agregadas": agregadas, "quitadas": quitadas, "rechazadas": rechazadas}


def cambiar_pais(cliente, ad_account_id, pais):
    with db.conectar() as con:
        r = con.execute(db.meta_cuenta.update().where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id)).values(
            pais=_pais(pais), actualizado_en=db.ahora()))
    return r.rowcount > 0


def actualizar(cliente, ad_account_id, **campos):
    valores = {k: v for k, v in campos.items() if k in _CAMPOS}
    if not valores:
        return
    with db.conectar() as con:
        con.execute(db.meta_cuenta.update().where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id)).values(
            **valores, actualizado_en=db.ahora()))


def actualizar_extra(cliente, ad_account_id, cambios):
    with db.conectar() as con:
        filtro = (_C.cliente == cliente) & (_C.ad_account_id == normalizar_id(ad_account_id))
        extra = con.execute(sa.select(_C.extra).where(filtro)).scalar()
        if extra is None and not con.execute(sa.select(_C.id).where(filtro)).first():
            return
        nuevo = dict(extra or {})
        nuevo.update(cambios or {})
        con.execute(db.meta_cuenta.update().where(filtro).values(extra=nuevo, actualizado_en=db.ahora()))
```

Si `adivinar_pais("HappyFlops Netherlands (Active)")` no da «NL» (el mapa CLDR trae «Netherlands» → NL en inglés), revisa que `_norm` reciba la palabra sola: «Netherlands» → «netherlands». «Finland 2025» → «finland» → FI.

- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/cuentas.py tests/test_meta_rend_cuentas.py
git commit -m "Meta rendimiento: las cuentas que lee cada proyecto, con país adivinado"
```

---

### Task 5: Copias en la base (`meta_rendimiento/datos.py`)

**Files:**
- Create: `meta_rendimiento/datos.py`
- Test: `tests/test_meta_rend_datos.py`

**Interfaces:**
- Consumes: tablas de la Task 1.
- Produces (escritura; cada una es UNA transacción):
  - `reemplazar_cuenta_dias(cliente, act, desde, hasta, filas: list[dict]) -> int` — borra el rango y escribe. Claves de fila: `fecha, gasto, impresiones, alcance, clics, clics_salida, compras, valor, vistas_3s, thruplays`.
  - `reemplazar_anuncio_dias(cliente, act, desde, hasta, filas) -> int` — claves: `fecha, campaign_id, adset_id, ad_id, gasto, impresiones, clics, clics_salida, compras, valor, vistas_3s, thruplays, p25, p50, p75, p100`.
  - `guardar_objetos(cliente, act, objetos: list[dict]) -> int` — upsert por `objeto_id`; claves: las columnas de `meta_objeto` salvo `id/cliente/ad_account_id/actualizado_en`. Un `None` en `nombre` no pisa un nombre guardado.
  - `marcar_sin_estado(cliente, act, nivel, vistos: set[str]) -> int` — pone `estado=None` a los objetos del nivel que no vinieron (archivados o borrados).
  - `guardar_alcance(cliente, act, filas: list[dict]) -> int` — claves `nivel, objeto_id, ventana, alcance, frecuencia`.
  - `borrar_cuenta(cliente, act) -> None` — borra las cuatro copias de esa cuenta.
  - `purgar_anuncios(antes_de: str) -> int`
- Produces (lectura; una consulta cada una):
  - `rango(cliente, cuentas: list[str]) -> {"filas": int, "desde": str|None, "hasta": str|None}` sobre `meta_cuenta_dia`.
  - `cuenta_por_dia(cliente, cuentas, desde, hasta) -> list[dict]` filas de `meta_cuenta_dia` con `ad_account_id`.
  - `totales_por_cuenta(cliente, cuentas, desde, hasta) -> dict[act, dict]` sumas de `meta_cuenta_dia`.
  - `totales_por_campana(cliente, cuentas, desde, hasta) -> list[dict]` sumas de `meta_anuncio_dia` por `campaign_id` + nombre/estado/objetivo/presupuestos de `meta_objeto` (LEFT JOIN), orden gasto desc.
  - `totales_por_conjunto(cliente, cuentas, desde, hasta, limite=24, offset=0) -> list[dict]` igual por `adset_id` (+ `aprendizaje`, nombre de campaña).
  - `totales_por_anuncio(cliente, cuentas, desde, hasta) -> list[dict]` por `ad_id` con las claves que espera `triple_whale.evaluacion.metricas`: `gasto, impresiones, clics, clics_salida, thruplays, vistas_3s, p100, pedidos (=compras), ingresos (=valor)`, más `ad_account_id, ad_id, anuncio, campana, conjunto, campaign_id, adset_id, estado, miniatura_url, primera_fecha, ultima_fecha, dias_con_gasto, canal="meta"`.
  - `alcance(cliente, cuentas, ventana, nivel="cuenta") -> dict[objeto_id, {"alcance", "frecuencia"}]`
  - `activos(cliente, cuentas) -> dict[act, {"campana": n, "conjunto": n, "anuncio": n, "aprendizaje_limitado": n}]` (estado `ACTIVE`; aprendizaje `FAIL`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meta_rend_datos.py
"""Copias de Meta en la base (spec §4 y §6): reemplazar un tramo es idempotente,
las lecturas agregan en una consulta y quitar una cuenta borra sus copias."""
from meta_rendimiento import datos

A, B = "act_1", "act_2"


def _dia(fecha, gasto, valor, compras=1, **k):
    return dict(fecha=fecha, gasto=gasto, impresiones=1000, alcance=800, clics=20, clics_salida=10,
                compras=compras, valor=valor, vistas_3s=300, thruplays=100, **k)


def _ad(fecha, ad, gasto, valor, campaign="c1", adset="s1", compras=1):
    return dict(fecha=fecha, campaign_id=campaign, adset_id=adset, ad_id=ad, gasto=gasto, impresiones=1000,
                clics=20, clics_salida=10, compras=compras, valor=valor, vistas_3s=300, thruplays=100,
                p25=90, p50=70, p75=50, p100=30)


def test_reemplazar_es_idempotente_y_totales(base_temporal):
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-01", "2026-10-02",
                                 [_dia("2026-10-01", 100, 300), _dia("2026-10-02", 50, 0, compras=0)])
    datos.reemplazar_cuenta_dias("hf", A, "2026-10-02", "2026-10-02", [_dia("2026-10-02", 60, 120)])
    datos.reemplazar_cuenta_dias("hf", B, "2026-10-01", "2026-10-01", [_dia("2026-10-01", 10, 40)])
    t = datos.totales_por_cuenta("hf", [A, B], "2026-10-01", "2026-10-02")
    assert t[A]["gasto"] == 160 and t[A]["valor"] == 420 and t[B]["gasto"] == 10
    assert datos.rango("hf", [A]) == {"filas": 2, "desde": "2026-10-01", "hasta": "2026-10-02"}
    assert len(datos.cuenta_por_dia("hf", [A, B], "2026-10-01", "2026-10-02")) == 3


def test_anuncios_campanas_y_conjuntos_con_nombres(base_temporal):
    datos.guardar_objetos("hf", A, [
        {"nivel": "campana", "objeto_id": "c1", "nombre": "Otoño", "estado": "ACTIVE", "objetivo": "OUTCOME_SALES",
         "presupuesto_diario": 500.0},
        {"nivel": "conjunto", "objeto_id": "s1", "padre_id": "c1", "campaign_id": "c1", "nombre": "Mujeres",
         "estado": "ACTIVE", "aprendizaje": "FAIL"},
        {"nivel": "anuncio", "objeto_id": "a1", "padre_id": "s1", "campaign_id": "c1", "nombre": "Video 1",
         "estado": "ACTIVE", "miniatura_url": "https://x/1.jpg"}])
    datos.reemplazar_anuncio_dias("hf", A, "2026-10-01", "2026-10-02",
                                  [_ad("2026-10-01", "a1", 30, 90), _ad("2026-10-02", "a1", 20, 0, compras=0),
                                   _ad("2026-10-02", "a2", 5, 0, compras=0)])
    camp = datos.totales_por_campana("hf", [A], "2026-10-01", "2026-10-02")
    assert camp[0]["campaign_id"] == "c1" and camp[0]["nombre"] == "Otoño" and camp[0]["gasto"] == 55
    conj = datos.totales_por_conjunto("hf", [A], "2026-10-01", "2026-10-02")
    assert conj[0]["aprendizaje"] == "FAIL" and conj[0]["campana"] == "Otoño"
    ads = {a["ad_id"]: a for a in datos.totales_por_anuncio("hf", [A], "2026-10-01", "2026-10-02")}
    assert ads["a1"]["pedidos"] == 1 and ads["a1"]["ingresos"] == 90 and ads["a1"]["anuncio"] == "Video 1"
    assert ads["a1"]["dias_con_gasto"] == 2 and ads["a1"]["canal"] == "meta"
    assert ads["a2"]["anuncio"] is None
    assert datos.activos("hf", [A])[A] == {"campana": 1, "conjunto": 1, "anuncio": 1, "aprendizaje_limitado": 1}


def test_nombre_none_no_pisa_y_marcar_sin_estado(base_temporal):
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a1", "nombre": "Video 1", "estado": "ACTIVE"}])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a1", "nombre": None, "estado": "PAUSED"}])
    datos.guardar_objetos("hf", A, [{"nivel": "anuncio", "objeto_id": "a9", "nombre": "Viejo", "estado": "ACTIVE"}])
    assert datos.marcar_sin_estado("hf", A, "anuncio", {"a1"}) == 1
    ads = {a["ad_id"]: a for a in datos.totales_por_anuncio("hf", [A], "2026-01-01", "2026-12-31")}
    assert ads == {}   # sin días no hay filas de anuncio


def test_alcance_borrar_y_purgar(base_temporal):
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 9000,
                                     "frecuencia": 2.5}])
    datos.guardar_alcance("hf", A, [{"nivel": "cuenta", "objeto_id": A, "ventana": 30, "alcance": 9500,
                                     "frecuencia": 2.6}])
    assert datos.alcance("hf", [A], 30) == {A: {"alcance": 9500, "frecuencia": 2.6}}
    datos.reemplazar_anuncio_dias("hf", A, "2026-06-01", "2026-10-01",
                                  [_ad("2026-06-01", "a1", 1, 0), _ad("2026-10-01", "a1", 1, 0)])
    assert datos.purgar_anuncios("2026-07-01") == 1
    datos.borrar_cuenta("hf", A)
    assert datos.alcance("hf", [A], 30) == {} and datos.totales_por_anuncio("hf", [A], "2026-01-01", "2026-12-31") == []
```

- [ ] **Step 2: Run to verify failure** → FAIL.

- [ ] **Step 3: Implement** `meta_rendimiento/datos.py`. Requisitos (todos cubiertos por las pruebas):
  - Escritura con `with db.conectar() as con:` (una transacción). `reemplazar_*`: `delete` del rango `fecha BETWEEN desde AND hasta` de esa cuenta y cliente, luego `insert` de las filas con `cliente`, `ad_account_id`, `actualizado_en=db.ahora()`; filas con `fecha` fuera del rango se ignoran. Devuelve cuántas escribió.
  - `guardar_objetos`: `insert_sqlite(db.meta_objeto).on_conflict_do_update(index_elements=["cliente", "objeto_id"], set_=…)`; en `set_`, `nombre=sa.func.coalesce(insert.excluded.nombre, db.meta_objeto.c.nombre)` y el resto de columnas desde `excluded`; `extra` por defecto `{}`.
  - Lecturas con `sa.select(...).group_by(...)`, `sa.func.sum`, `sa.func.count(sa.distinct(fecha))` para `dias_con_gasto` (contando solo días con `gasto > 0` vía `sa.case`), `min/max(fecha)`. Los JOIN con `meta_objeto` son `outerjoin` por (`cliente`, `objeto_id`). `cuentas` vacía → resultado vacío sin consultar.
  - `totales_por_anuncio` hace dos alias de `meta_objeto` (conjunto y campaña) para traer `conjunto` y `campana` en la misma consulta.
  - Los enteros salen como `int`, los montos como `float` (`float(x or 0)`).

```python
"""Copias de Meta en la base y sus lecturas agregadas (spec §4, §6 y §8). Único
escritor de meta_cuenta_dia, meta_anuncio_dia, meta_objeto y meta_alcance.

Cada escritura es UNA transacción. Reemplazar un tramo borra ese rango de la
cuenta y lo vuelve a escribir: Meta reatribuye compras de días pasados, así
que la copia de los últimos 7 días siempre pisa lo anterior. Cada lectura es
UNA consulta agregada (la pestaña nunca hace una consulta por fila)."""
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

METRICAS = ("gasto", "impresiones", "clics", "clics_salida", "compras", "valor", "vistas_3s", "thruplays")
METRICAS_CUENTA = METRICAS + ("alcance",)
METRICAS_ANUNCIO = METRICAS + ("p25", "p50", "p75", "p100")
_ENTEROS = {"impresiones", "alcance", "clics", "clics_salida", "vistas_3s", "thruplays", "p25", "p50", "p75", "p100"}
# ... implementa las funciones de la sección Interfaces con estas constantes.
```

- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/datos.py tests/test_meta_rend_datos.py
git commit -m "Meta rendimiento: copias por cuenta, campaña, conjunto y anuncio"
```

---

### Task 6: Copia de una cuenta (`meta_rendimiento/sync.py`)

**Files:**
- Create: `meta_rendimiento/sync.py`
- Test: `tests/test_meta_rend_sync.py`

**Interfaces:**
- Consumes: `graph.get/paginar/informe/acciones/TIPOS_COMPRA/ErrorGraph`, `datos.*` (Task 5), `cuentas.actualizar/actualizar_extra/cuenta` (Task 4), `tasas.asegurar` (Task 3).
- Produces:
  - `CAMPOS_CUENTA_DIA = "spend,impressions,reach,clicks,outbound_clicks,inline_link_clicks,actions,action_values,video_thruplay_watched_actions,date_start"`
  - `CAMPOS_ANUNCIO_DIA = "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,spend,impressions,clicks,outbound_clicks,inline_link_clicks,actions,action_values,video_thruplay_watched_actions,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p100_watched_actions,date_start"`
  - `fila_cuenta(f: dict) -> dict` y `fila_anuncio(f: dict) -> dict` (puras: Graph → columnas)
  - `objetos_de(campanas, conjuntos, anuncios) -> list[dict]` (pura: Graph → `meta_objeto`; presupuestos entre 100 salvo monedas sin decimales: `lanzador.MONEDAS_SIN_DECIMALES` si existe, si no `("CLP","COP","JPY","KRW","VND","HUF","ISK","TWD")` — revisa `lanzador.py`/`meta_ads` y usa la constante que exista)
  - `sincronizar(cliente: str, ad_account_id: str, token: str, hoy: date|None = None, on_etapa=None) -> dict` con `{"dias_cuenta": n, "filas_anuncio": n, "objetos": n, "desde": str, "hasta": str}`.
  - `DIAS_CUENTA_INICIAL = 395`, `DIAS_ANUNCIO_INICIAL = 90`, `DIAS_RECOPIA = 7`, `TRAMO_ANUNCIO = 30`, `TRAMO_CUENTA = 90`, `VENTANAS_ALCANCE = (7, 14, 30, 90)`.

Comportamiento de `sincronizar` (spec §6):
1. `info = graph.get(act, token, {"fields": "name,currency,timezone_name,account_status,disable_reason,amount_spent,spend_cap"})` → `cuentas.actualizar(nombre, moneda, zona_horaria, estado="copiando", error=None)` y `cuentas.actualizar_extra(..., {"cuenta": {account_status, disable_reason, amount_spent, spend_cap}})` (montos como texto tal cual).
2. `hoy` = la fecha local de la cuenta (`zoneinfo.ZoneInfo(timezone_name)`; si falla, `date.today()`).
3. Objetos: `paginar(f"{act}/campaigns", …)` con `fields=id,name,objective,effective_status,daily_budget,lifetime_budget,bid_strategy,created_time` y `filtering=[{"field":"effective_status","operator":"IN","value":ESTADOS}]` (json.dumps) con `ESTADOS = ["ACTIVE","PAUSED","WITH_ISSUES","IN_PROCESS","PENDING_REVIEW","DISAPPROVED","CAMPAIGN_PAUSED","ADSET_PAUSED"]`, `limit=500`; conjuntos (`adsets`) con `id,name,campaign_id,effective_status,daily_budget,lifetime_budget,optimization_goal,bid_strategy,learning_stage_info,created_time`; anuncios (`ads`) SOLO con estados `["ACTIVE","WITH_ISSUES","PENDING_REVIEW","DISAPPROVED","IN_PROCESS"]` y `id,name,adset_id,campaign_id,effective_status,created_time,creative{id,thumbnail_url,video_id}`. `datos.guardar_objetos` + `datos.marcar_sin_estado` por nivel con los ids vistos (para anuncios, solo marca los que tenían estado ACTIVE/WITH_ISSUES/PENDING_REVIEW/DISAPPROVED/IN_PROCESS y ya no vinieron).
4. Días de cuenta: primera vez (`extra.backfill_hecho` falso) desde `hoy - 395` por tramos de 90 (`time_range={"since","until"}`, `level=account`, `time_increment=1`, `paginar`); después desde `hoy - 6`. `datos.reemplazar_cuenta_dias` por tramo.
5. Días de anuncio: primera vez desde `hoy - 89` por tramos de 30 con `graph.informe(act, token, {"level":"ad","time_increment":1,"time_range":…,"fields":CAMPOS_ANUNCIO_DIA,"limit":500})`; después `hoy - 6`. Cada tramo: `datos.reemplazar_anuncio_dias` y `datos.guardar_objetos` con los nombres que trae el informe (`ad_name/adset_name/campaign_name` → objetos con `nombre` y sin `estado` → para NO pisar el estado, `guardar_objetos` debe aceptar la clave ausente: solo actualiza columnas presentes en el dict. Implementa `guardar_objetos` así en la Task 5 si no lo hiciste: `set_` solo con las claves presentes).
6. Alcance: por cada ventana `w`, `graph.get(f"{act}/insights", token, {"level":"account","date_preset":f"last_{w}d","fields":"reach,frequency"})` y `graph.paginar(…, {"level":"campaign","date_preset":…,"fields":"campaign_id,reach,frequency","limit":500})` → `datos.guardar_alcance`. `last_14d` y `last_90d` existen en Meta; si una ventana devuelve error de parámetro (código 100), se salta esa ventana sin fallar la copia.
7. `tasas.asegurar([moneda], desde_cuenta, hoy)`.
8. Al terminar: `cuentas.actualizar(estado="ok", error=None, ultima_copia=db.ahora())` y `actualizar_extra({"backfill_hecho": True})`.
9. `on_etapa(nombre, progreso)` se llama al empezar cada paso (si no es None).
10. Una `ErrorGraph` sube tal cual (la tarea la anota).

Mapeo de filas (puras):

```python
def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _salida(f):
    salida = graph.acciones(f.get("outbound_clicks"), ("outbound_click",))
    return int(salida or _n(f.get("inline_link_clicks")))


def _video(f, campo):
    return int(graph.acciones(f.get(campo), ("video_view",)))


def fila_cuenta(f):
    return {"fecha": f.get("date_start"), "gasto": _n(f.get("spend")), "impresiones": int(_n(f.get("impressions"))),
            "alcance": int(_n(f.get("reach"))), "clics": int(_n(f.get("clicks"))), "clics_salida": _salida(f),
            "compras": graph.acciones(f.get("actions"), graph.TIPOS_COMPRA),
            "valor": graph.acciones(f.get("action_values"), graph.TIPOS_COMPRA),
            "vistas_3s": int(graph.acciones(f.get("actions"), ("video_view",))),
            "thruplays": _video(f, "video_thruplay_watched_actions")}


def fila_anuncio(f):
    base = fila_cuenta(f)
    base.pop("alcance")
    return dict(base, ad_id=str(f.get("ad_id")), adset_id=f.get("adset_id"), campaign_id=f.get("campaign_id"),
                p25=_video(f, "video_p25_watched_actions"), p50=_video(f, "video_p50_watched_actions"),
                p75=_video(f, "video_p75_watched_actions"), p100=_video(f, "video_p100_watched_actions"))
```

- [ ] **Step 1: Write the failing tests** (`tests/test_meta_rend_sync.py`): un doble de `graph` (monkeypatch de `sync.graph.get`, `sync.graph.paginar`, `sync.graph.informe` con funciones que miran el `edge` y los `params`) y de `sync.tasas.asegurar`. Casos:
  1. `fila_cuenta` y `fila_anuncio` con una fila real de Meta: `{"spend":"100.5","impressions":"1000","reach":"800","clicks":"30","outbound_clicks":[{"action_type":"outbound_click","value":"12"}],"actions":[{"action_type":"omni_purchase","value":"3"},{"action_type":"purchase","value":"2"},{"action_type":"video_view","value":"400"}],"action_values":[{"action_type":"purchase","value":"250.5"}],"video_thruplay_watched_actions":[{"action_type":"video_view","value":"90"}],"date_start":"2026-10-01"}` → `compras == 2`, `valor == 250.5`, `clics_salida == 12`, `vistas_3s == 400`, `thruplays == 90`.
  2. Primera copia: pide 395 días de cuenta en 5 tramos y 90 de anuncio en 3 tramos de informe; escribe filas; deja `estado="ok"`, `backfill_hecho=True`, `moneda="SEK"`.
  3. Segunda copia: solo `hoy-6..hoy` (un tramo de cuenta, un informe de anuncio).
  4. Presupuesto `daily_budget="50000"` en SEK → `presupuesto_diario == 500.0`; `learning_stage_info={"status":"FAIL"}` → `aprendizaje == "FAIL"`; `creative.thumbnail_url` → `miniatura_url`.
  5. Un `ErrorGraph(limite)` en el informe sube y la cuenta NO queda `ok`.

- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** `meta_rendimiento/sync.py` según lo de arriba.
- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/sync.py meta_rendimiento/datos.py tests/test_meta_rend_sync.py
git commit -m "Meta rendimiento: copia de una cuenta (objetos, días de cuenta y de anuncio, alcance)"
```

---

### Task 7: Tareas del worker

**Files:**
- Create: `tareas/meta_rendimiento.py`
- Modify: `tareas/__init__.py` (agregar `meta_rendimiento` a la lista del import de la línea 57, en orden alfabético)
- Modify: `worker.py` (`PERIODICAS`: agregar `("meta_rend_sincronizar_todas", 10800)` después de `("tw_sincronizar_todas", 7200)` y `("meta_rend_limpiar", 86400)` junto a los diarios)
- Test: `tests/test_tareas_meta_rendimiento.py`

**Interfaces:**
- Consumes: `sync.sincronizar`, `cuentas.*`, `datos.purgar_anuncios`, `meta_conexion.cargar`, `meta_conexion.modo`, `trabajos.encolar/reportar`, `cola.job_ids_vivos`, `tareas.registrar`.
- Produces:
  - `TIPO_SYNC = "meta_rend_sincronizar"`, `TIPO_TODAS = "meta_rend_sincronizar_todas"`, `TIPO_LIMPIAR = "meta_rend_limpiar"`
  - `job_id_sync(cliente, act) -> f"{cliente}__meta_rend__{act}"`
  - `encolar_sync(cliente, act=None) -> int` (cuántas quedaron en cola; `max_intentos=2`, `duracion_estimada=180`, `etapas=ETAPAS_SYNC`)
  - `syncs_en_curso(cliente) -> list[str]`
  - `DIAS_ANUNCIO_GUARDADOS = 95`

```python
"""Tareas del worker para el rendimiento de Meta (spec 2026-10-08 meta rendimiento §6).

  meta_rend_sincronizar        -> f"{cliente}__meta_rend__{act}"  (max_intentos=2: leer de Meta no cobra).
                                  Una por CUENTA; el payload lleva `cliente` y `ad_account_id`.
  meta_rend_sincronizar_todas  -> periódica (worker.PERIODICAS, 3 h): encola la de cada cuenta de cada proyecto
  meta_rend_limpiar            -> periódica diaria: borra los días de anuncio de más de 95 días

Un error de Meta deja ESA cuenta en estado `error` con el motivo en palabras (sin token) y sube para que la cola
reintente; las demás cuentas del proyecto no se enteran."""
import logging
from datetime import date, timedelta

from flask_babel import gettext

import cola
import idiomas
import meta_conexion
import trabajos
from meta_rendimiento import cuentas, datos, graph, sync
from tareas import registrar

log = logging.getLogger("creatv.tareas.meta_rendimiento")

TIPO_SYNC = "meta_rend_sincronizar"
TIPO_TODAS = "meta_rend_sincronizar_todas"
TIPO_LIMPIAR = "meta_rend_limpiar"
ETAPAS_SYNC = [(idiomas.N_("Leyendo la cuenta"), 5), (idiomas.N_("Campañas, conjuntos y anuncios"), 15),
               (idiomas.N_("Métricas por día"), 70), (idiomas.N_("Alcance"), 10)]
MAX_INTENTOS_SYNC = 2
DIAS_ANUNCIO_GUARDADOS = 95


def job_id_sync(cliente, act):
    return f"{cliente}__meta_rend__{act}"


def encolar_sync(cliente, act=None):
    actuales = cuentas.ids(cliente)
    lista = [a for a in actuales if act is None or a == cuentas.normalizar_id(act)]
    return sum(1 for a in lista if trabajos.encolar(
        job_id_sync(cliente, a), TIPO_SYNC, {"cliente": cliente, "ad_account_id": a}, cliente=cliente,
        duracion_estimada=180, etapas=ETAPAS_SYNC, max_intentos=MAX_INTENTOS_SYNC))


def syncs_en_curso(cliente):
    return sorted(cola.job_ids_vivos(cliente, TIPO_SYNC))


@registrar(TIPO_SYNC)
def meta_rend_sincronizar(tarea):
    p = tarea["payload"]
    cliente, act = p["cliente"], p["ad_account_id"]
    if not cuentas.cuenta(cliente, act):
        return gettext("Esa cuenta de Meta ya no está en el proyecto.")
    token = (meta_conexion.cargar(cliente) or {}).get("token")
    if not token:
        mensaje = gettext("Meta no está conectado en este proyecto: conéctalo en Configuración › Conexiones.")
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        return mensaje
    job_id = tarea.get("job_id") or job_id_sync(cliente, act)

    def etapa(nombre, progreso=None):
        trabajos.reportar(job_id, etapa=nombre, progreso=progreso)

    try:
        r = sync.sincronizar(cliente, act, token, on_etapa=etapa)
    except graph.ErrorGraph as e:
        mensaje = cola.recortar(cola.sin_token(str(e)), 500)
        cuentas.actualizar(cliente, act, estado="error", error=mensaje)
        raise RuntimeError(mensaje) from None
    nombre = (cuentas.cuenta(cliente, act) or {}).get("nombre") or act
    return gettext("Listo (%(cuenta)s): %(dias)s día(s) de la cuenta y %(filas)s fila(s) de anuncios, del %(desde)s al %(hasta)s.",
                   cuenta=nombre, dias=r["dias_cuenta"], filas=r["filas_anuncio"], desde=r["desde"], hasta=r["hasta"])


@registrar(TIPO_TODAS)
def meta_rend_sincronizar_todas(tarea):
    n = sum(encolar_sync(cliente, act) for cliente, act in cuentas.todas())
    return gettext("%(n)s copia(s) de Meta en cola", n=n)


@registrar(TIPO_LIMPIAR)
def meta_rend_limpiar(tarea):
    n = datos.purgar_anuncios((date.today() - timedelta(days=DIAS_ANUNCIO_GUARDADOS)).isoformat())
    return gettext("%(n)s fila(s) viejas de anuncios de Meta borradas", n=n)
```

Antes de escribir, mira la firma real de `tareas.registrar` y cómo `tareas/triple_whale.py` maneja `tarea["job_id"]`; usa lo mismo. Si la cuenta está en un proyecto en modo agencia (`meta_conexion.modo(cliente) == "agencia"`), igual funciona (el token de agencia se inyecta en `cargar`): no hagas nada especial.

- [ ] **Step 1: Write the failing tests** (`tests/test_tareas_meta_rendimiento.py`, con `base_temporal`):
  1. `encolar_sync("hf")` con dos cuentas elegidas encola 2 con `job_id` `hf__meta_rend__act_1` y `max_intentos == 2`; repetir encola 0.
  2. La tarea sin token deja la cuenta en `error` con el texto de conectar y NO lanza.
  3. La tarea con `sync.sincronizar` que lanza `graph.ErrorGraph("Meta pidió esperar…", codigo=17)` deja `estado="error"` y lanza `RuntimeError`; el texto guardado no contiene el token del doble de `meta_conexion.cargar`.
  4. `meta_rend_sincronizar_todas` encola una por cuenta de cada proyecto.
  5. `"meta_rend_sincronizar_todas"` y `"meta_rend_limpiar"` están en `worker.PERIODICAS` y `worker.PERIODICAS` sigue teniendo `tw_sincronizar_todas` antes de `exp_refrescar_todos`.

  Para ejecutar una tarea registrada en la prueba, sigue el patrón de `tests/test_triple_whale_sync.py` (busca cómo llama a `tw_sincronizar` con un dict `tarea`).

- [ ] **Step 2–4:** fallar, implementar, pasar.
- [ ] **Step 5: Commit**

```bash
git add tareas/meta_rendimiento.py tareas/__init__.py worker.py tests/test_tareas_meta_rendimiento.py
git commit -m "Meta rendimiento: tareas de copia, periódica cada 3 h y limpieza diaria"
```

---

### Task 8: Conectar Meta sin Página («solo métricas»)

**Files:**
- Modify: `dashboard.py` (`meta_elegir` ~línea 3870, `_guardar_conexion_propia` ~3915)
- Modify: `templates/meta_elegir.html` (opción «Sin Página (solo métricas)»)
- Modify: `templates/_meta_conectar.html` (estado conectado sin Página: «Solo métricas» + enlace a la pestaña Meta)
- Modify: `lanzador.py` (`_validar_para_lanzar`: sin `page_id` → `ValueError` en palabras)
- Modify: `tareas/meta.py` (antes de `meta_auth.configurar` en las dos funciones que publican/crean: sin `page_id` → error en palabras, sin crear nada)
- Test: `tests/test_meta_sin_pagina.py`

**Interfaces:**
- Consumes: `meta_conexion.cargar_pendiente/guardar/credenciales_ads`.
- Produces: `meta.json` puede tener `page_id=None` (y `page_nombre`, `page_access_token`, `ig_user_id`, `ig_username` en None). Texto nuevo: «Conectado solo para métricas: sin Página no se pueden lanzar anuncios ni publicar.» y el de `lanzador`: «Este proyecto está conectado a Meta solo para métricas (sin Página): conecta una Página en Configuración › Conexiones para lanzar anuncios.»

Comportamiento:
- `meta_elegir` GET: si no hay Páginas, el formulario igual se muestra (antes también) y ofrece la opción vacía marcada; si hay Páginas, la opción «Sin Página (solo métricas)» va al final, no marcada.
- `meta_elegir` POST: falta la cuenta → error como hoy; `page_id` vacío → guarda sin Página; `page_id` que no está en la lista → error como hoy.
- `_guardar_conexion_propia(cliente, pendiente, cuenta, pagina=None)`.
- El flash de éxito sin Página: «Meta conectado: %(cuenta)s. Conectado solo para métricas: sin Página no se pueden lanzar anuncios ni publicar.»
- `bitacora.registrar(..., f"{cuenta.get('name')} · {pagina.get('name') if pagina else '—'}")`.
- `lanzador._validar_para_lanzar`: lee `meta_conexion.cargar(cliente)`; si hay token y `not datos.get("page_id")` → `ValueError(texto)`. Ojo: hay pruebas que mockean `meta_conexion.cargar` con `{"moneda": "COP"}` sin token: la condición exige token presente para no romperlas.
- `organico.py` ya revisa `tiene_pagina`: no se toca.

- [ ] **Step 1: Write the failing tests**: usa el fixture `app` de `tests/test_rutas_meta_app.py` o el de `tests/test_rutas_configuracion.py` (mira cuál siembra `meta.pendiente.json`; busca `guardar_pendiente` en `tests/`). Casos:
  1. Con pendiente que trae una cuenta y CERO Páginas, POST `ad_account_id=act_1` y `page_id=""` → 302, `meta_conexion.cargar(c)["page_id"] is None`, flash con «solo para métricas».
  2. Con pendiente con una Página, POST sin `page_id` → también guarda sin Página.
  3. POST con `page_id` que no está en la lista → error «Elige una cuenta publicitaria…» y nada guardado.
  4. `lanzador._validar_para_lanzar` con `meta_conexion.cargar` → `{"token": "t", "ad_account_id": "act_1", "page_id": None}` lanza `ValueError` con «solo para métricas».
  5. GET de `meta_elegir` con cero Páginas muestra «Sin Página (solo métricas)».

- [ ] **Step 2–4:** fallar, implementar, pasar. Corre también `../../../venv/bin/python3 -m pytest tests/test_rutas_meta*.py tests/test_lanzador*.py tests/test_tareas_meta.py -q`.
- [ ] **Step 5: Commit**

```bash
git add dashboard.py templates/meta_elegir.html templates/_meta_conectar.html lanzador.py tareas/meta.py tests/test_meta_sin_pagina.py
git commit -m "Meta: conectar sin Página para solo métricas; lanzar y publicar frenan en palabras"
```

---

### Task 9: Contexto de la pestaña (`meta_rendimiento/panel.py`)

**Files:**
- Create: `meta_rendimiento/panel.py`
- Test: `tests/test_meta_rend_panel.py`

**Interfaces:**
- Consumes: `cuentas.listar`, `datos.*`, `tasas.mapa`, `triple_whale.evaluacion.evaluar`, `triple_whale.paises.bandera/nombre_pais`, `decisor.reglas_efectivas`, `proyectos.reglas_defecto`, `meta_conexion.cargar/modo`, `tareas.meta_rendimiento.syncs_en_curso/job_id_sync`.
- Produces:
  - `PERIODOS = (7, 14, 30, 90)`, `PERIODO_DEFECTO = 30`, `POR_PAGINA = 24`
  - `periodo(dias, hoy) -> (desde, hasta, desde_prev, hasta_prev)` (igual que `triple_whale.panel.periodo`; impórtala de ahí, no la copies)
  - `cuenta_elegida(cuentas_lista, valor) -> dict|None` (id ajeno o inválido → None = «Todas»; con una sola cuenta, esa)
  - `kpis(filas_dia: list[dict], conv: dict[(act, fecha)] -> float|None | None) -> dict` con `gasto, valor, compras, impresiones, clics_salida, roas, cpa, cpm, ctr_salida`; con `conv`, los montos se convierten y `usd_ok=False` si falta alguna tasa de un día con gasto.
  - `contexto(cliente, dias=PERIODO_DEFECTO, cuenta=None, hoy=None, pagina_anuncios=0) -> dict` con estas claves (la plantilla de la Task 10 usa exactamente estas):
    `conectado` (hay token), `modo` (`propia|agencia|None`), `solo_metricas` (sin `page_id`), `cuentas` (cada una con `nombre_pais`, `bandera`), `actual` (cuenta o None), `ids` (las del alcance), `dias`, `periodos`, `desde`, `hasta`, `moneda` («USD» en «Todas» con varias cuentas; si no, la de la cuenta), `moneda_comun` (si todas las del alcance comparten moneda, esa; si no None), `usd_ok`, `kpis`, `kpis_prev`, `variacion` (dict de fracciones, como `tw_var`), `kpis_moneda_comun` (los KPIs sin convertir si hay moneda común y se está en «Todas»), `alcance` (suma de cuentas de la ventana más cercana a `dias`: 7, 14, 30 o 90), `frecuencia` (si es una sola cuenta), `serie` (`{"dias": [...], "moneda": moneda}` para `grafico_tablero`), `por_cuenta` (filas con gasto, valor, roas, compras, alcance, impresiones y `activos`), `campanas`, `conjuntos`, `anuncios` (los `POR_PAGINA` de la página pedida, ya evaluados), `hay_mas_anuncios`, `conteo` (por veredicto), `meta_roas`, `rango`, `jobs_sync` (`[{"job_id", "cuenta"}]`), `ultima_copia` (la más vieja de las del alcance).

Evaluación por anuncio: por CADA cuenta del alcance se llama `evaluacion.evaluar(totales_periodo, totales_7d, totales_7d_previos, reglas)` con las filas de esa cuenta (cada anuncio se compara con su propia cuenta), y se juntan las listas; orden final: veredicto (`evaluacion.VEREDICTOS`) y gasto desc. `reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})` como en `triple_whale.panel.evaluar_periodo`. Quita `"sin_rastreo"` de `problemas` (no aplica: no es Triple Whale).

Para «Todas» en USD: `conv[(act, fecha)] = tasas.mapa(moneda_de_act, desde, hasta)[fecha]`; KPIs, serie y `por_cuenta` («Todas») en USD; campañas, conjuntos y anuncios siempre en la moneda de su cuenta (cada fila lleva `moneda`).

- [ ] **Step 1: Write the failing tests** con `base_temporal`, sembrando con `cuentas.elegir` + `datos.reemplazar_*` + `tasa_cambio` (inserta filas directo con `tasas` haciendo `monkeypatch` de `url_conector.abrir`, o inserta en `db.tasa_cambio`). Casos:
  1. Sin token (`monkeypatch` de `panel.meta_conexion.cargar` → `{}`) → `conectado is False`.
  2. Dos cuentas SEK, «Todas»: `moneda == "USD"`, `moneda_comun == "SEK"`, `kpis["gasto"]` = suma convertida con la tasa, `kpis_moneda_comun["gasto"]` = suma en SEK.
  3. Una cuenta elegida por `cuenta="act_1"`: `moneda == "SEK"`, `actual["ad_account_id"] == "act_1"`; un id ajeno da «Todas».
  4. Sin tasa para un día con gasto → `usd_ok is False`.
  5. Anuncios: un ganador (≥3 compras, ROAS alto) y un perdedor (gasto alto, 0 compras) en la misma cuenta → veredictos `ganador` y `perdedor`; `"sin_rastreo"` nunca aparece.
  6. Paginación: 30 anuncios → `len(anuncios) == 24` y `hay_mas_anuncios`; `pagina_anuncios=1` → 6.
  7. `variacion["gasto"]` = (actual − anterior) / anterior.

- [ ] **Step 2–4:** fallar, implementar, pasar.
- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/panel.py tests/test_meta_rend_panel.py
git commit -m "Meta rendimiento: contexto de la pestaña con Todas en USD y veredicto por anuncio"
```

---

### Task 10: Rutas, pestaña y plantillas

**Files:**
- Create: `meta_rendimiento/rutas.py` (Blueprint `meta_rendimiento`, `url_prefix="/cliente/<cliente>/meta-rendimiento"`)
- Create: `templates/_tab_meta.html`, `templates/_meta_panel.html`, `templates/_meta_cuentas.html`, `templates/_meta_anuncios_filas.html`
- Modify: `dashboard.py` (registrar el blueprint junto a `triple_whale_rutas`; en `ver_cliente`, contexto barato `meta_rend = {"conectado": bool(token), "n_cuentas": len(cuentas.ids(cliente)), "modo": meta_conexion.modo(cliente)}` sin llamar a Graph)
- Modify: `templates/cliente.html` (sección `<section id="tab-meta" class="tab-panel" role="tabpanel">{% include "_tab_meta.html" %}</section>` después de `tab-triplewhale`)
- Modify: `templates/_sidebar.html` (botón `data-tab="meta"` después del de Triple Whale, con un ícono SVG simple de barras y el texto `{{ _('Meta') }}`)
- Test: `tests/test_rutas_meta_rendimiento.py`

**Interfaces:**
- Consumes: `panel.contexto`, `cuentas.*`, `tareas.meta_rendimiento.encolar_sync`, `meta_conexion.cargar/listar_activos/modo`, `app.extensions["grafico_tablero"]`, filtros `dinero`, `roas`, `tw_num`, `tw_pct`, `tw_var` (ya registrados por `triple_whale.rutas`).
- Produces (rutas):
  - `GET /panel?dias&cuenta` → `_meta_panel.html` (`ver_panel`)
  - `GET /anuncios?dias&cuenta&pagina` → `_meta_anuncios_filas.html` (solo `<tr>`s + un botón «Ver más» si quedan) (`ver_anuncios`)
  - `GET /cuentas` → `_meta_cuentas.html`: llama `meta_conexion.listar_activos(token)` (una llamada a Meta, solo al abrir el selector); marca las ya elegidas; país adivinado o el guardado; cuentas de otro proyecto aparecen deshabilitadas con «En otro proyecto». En modo agencia: mensaje «Todavía no disponible en modo agencia». Error de Meta → mensaje sin token (`cola.sin_token`). (`ver_cuentas`)
  - `POST /cuentas` → form con `cuenta` (lista de `act_…`) y `pais_<act>`; valida que cada id esté en `listar_activos` del token (lo que no está se ignora); `cuentas.elegir(...)`; encola la copia de las agregadas; flash con agregadas/quitadas/rechazadas; redirect a `ver_cliente#meta`. (`guardar_cuentas`)
  - `POST /cuentas/<act>/pais` → `cuentas.cambiar_pais`; 404 si la cuenta no es del proyecto. (`cambiar_pais`)
  - `POST /sincronizar` → `encolar_sync(cliente, act or None)`; `act` ajeno → 404. (`sincronizar`)
  - `before_request` de mismo origen para POST (copia la de `triple_whale/rutas.py`).

Plantillas (todas con la base visual común; reutiliza las clases de `_tw_panel.html`: `tw-barra`, `tw-controles`, `tw-sync`, `tb-seccion`, `tb-seccion-cab`, `tb-tiles`, `kpi-tile`, `tw-tabla-scroll`, `tw-tabla`, `estado-vacio`, `tag-en-uso`, `tag-descartado`, `tag-advertencia`, `tag-error`, `btn-sm`, `campo-label`, `barra-progreso`; no agregues CSS nuevo salvo que algo se vea roto en la captura del Step 6, y entonces va en `static/estilos/pantallas/` siguiendo `static/estilos/ORDEN` y regenerando `style.css` como diga la skill `ui`):

`_tab_meta.html` (shell, el único con `<script>`): cabecera «Meta» + descripción «Todas tus cuentas publicitarias de Meta en un solo lugar: gasto, ventas y ROAS por cuenta, campaña, conjunto y anuncio, con el veredicto de cada anuncio.»; tres estados:
1. `not meta_rend.conectado` → `estado-vacio` «Conecta Meta para ver tus cuentas» con botón `data-ir-tab="settings"` («Ir a Conexiones»).
2. conectado y `meta_rend.n_cuentas == 0` → `estado-vacio` «Elige qué cuentas publicitarias quieres ver» + contenedor `#meta-cuentas` con `data-url` de `ver_cuentas` que se carga por fetch al abrir la pestaña.
3. con cuentas → botón «Elegir cuentas» (abre `#meta-cuentas` por fetch, plegable) + `#meta-panel` con `data-url` de `ver_panel`, cargado por fetch la primera vez que se abre la pestaña (mismo JS que `_tab_triple_whale.html`: `filtros` por `select[data-meta-param]`, `iniciarPolling` para `[data-poll-job]`, botón «Ver más» que hace fetch de `ver_anuncios` con `pagina+1` y agrega las filas antes del botón).

`_meta_panel.html` (sin `<script>`): barra (selector «Cuenta»: «Todas las cuentas (N)» + cada cuenta con bandera y nombre; período «Últimos N días»; «Última copia: …»; form POST «Actualizar ahora»); una `barra-progreso` `data-poll-job` por copia en curso; errores por cuenta (`tag-error` con el nombre); si `solo_metricas`, `tag-advertencia` «Conectado solo para métricas: sin Página no se pueden lanzar anuncios desde Creatv.»; si `not usd_ok`, «USD no disponible para algunos días: los totales en USD pueden estar incompletos.»; estado vacío si `rango.filas == 0` («Trayendo los últimos 13 meses…» con copias en curso, o «Pulsa «Actualizar ahora»…»).
Secciones: (1) KPIs `tb-tiles` (gasto, valor de compras, ROAS, compras, costo por compra, alcance, CPM, CTR de salida; cada uno con `variacion|tw_var`; en «Todas» con moneda común, debajo del gasto y del valor el total en la moneda común); (2) gráfico (`grafico` del Tablero, misma macro/markup que `_tw_panel.html` usa para pintarlo: búscalo ahí y reúsalo); (3) «Por cuenta» (solo en «Todas» con 2+): tabla cuenta (bandera+nombre), gasto, ROAS, compras, alcance, activos, «aprendizaje limitado» (`n de m`), y cada nombre es un botón `data-meta-cuenta="<act>"` que el JS de la pestaña convierte en filtro; (4) «Campañas»: nombre, estado, objetivo, presupuesto diario, gasto, ROAS, compras, CPA (máximo 50 filas); (5) «Conjuntos» (24): nombre + campaña, estado, aprendizaje (`FAIL` → `tag-advertencia` «Aprendizaje limitado», `LEARNING` → «Aprendiendo»), presupuesto, gasto, ROAS, CPA; (6) «Anuncios» con conteo por veredicto (chips) y tabla: miniatura (`<img loading="lazy" width="48" height="48">` si hay `miniatura_url`), nombre + conjunto, veredicto (clases como `_tw_panel.html`), problemas (`evaluacion.PROBLEMAS[p][0]|traducir` con `title` = el consejo), gasto, ROAS, CTR, gancho, retención; filas en `_meta_anuncios_filas.html` (incluido) y botón «Ver más» `data-meta-mas="1"` si `hay_mas_anuncios`.

Estados de Meta en palabras (dict en `panel.py` con `N_`): ACTIVE «Activa/o», PAUSED «En pausa», CAMPAIGN_PAUSED «Campaña en pausa», ADSET_PAUSED «Conjunto en pausa», WITH_ISSUES «Con problemas», DISAPPROVED «Rechazado», PENDING_REVIEW «En revisión», IN_PROCESS «Procesando», None «Archivado».

- [ ] **Step 1: Write the failing tests** (`tests/test_rutas_meta_rendimiento.py`, fixture `app` de `tests/test_rutas_configuracion.py`, que mockea `meta_conexion.cargar` → `{"moneda": "COP"}`; en cada prueba sobrescribe con `monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar", lambda c: {"token": "tok-llave-de-prueba", "ad_account_id": "act_1", "page_id": None})`). Casos:
  1. La página del proyecto trae `data-tab="meta"` e `id="tab-meta"`, y con Meta sin conectar muestra «Conecta Meta para ver tus cuentas»; la página NO llama a `panel.contexto` (monkeypatch que hace `pytest.fail`).
  2. Conectado con cuentas: el HTML trae `data-url="/cliente/acme/meta-rendimiento/panel"`.
  3. `GET /panel` con datos sembrados devuelve el nombre de la cuenta, «Todas las cuentas» y un veredicto.
  4. `GET /cuentas` con `listar_activos` doble (2 cuentas, una ya en el proyecto `otro`) → la de `otro` sale deshabilitada con «En otro proyecto».
  5. `POST /cuentas` con una cuenta que no está en `listar_activos` → no se agrega; con una válida → se agrega con su país y se encola `meta_rend_sincronizar` (mira `db.tarea`).
  6. `POST /sincronizar` con `Sec-Fetch-Site: cross-site` → 403; con `act` de otro proyecto → 404.
  7. Ninguna respuesta contiene `tok-llave-de-prueba`.
  8. Un usuario de otro proyecto (`otro`) no ve `/cliente/acme/meta-rendimiento/panel` (el guard por cliente responde 403/302 como en las rutas de Triple Whale; copia la aserción de `tests/test_rutas_triple_whale.py` si existe una igual).

- [ ] **Step 2–4:** fallar, implementar, pasar. Corre además `tests/test_rutas_triple_whale.py tests/test_rutas_configuracion.py tests/test_ui*.py -q` (la navegación lateral y las plantillas compartidas).
- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/rutas.py templates/_tab_meta.html templates/_meta_panel.html templates/_meta_cuentas.html templates/_meta_anuncios_filas.html templates/cliente.html templates/_sidebar.html dashboard.py tests/test_rutas_meta_rendimiento.py
git commit -m "Meta rendimiento: pestaña Meta con selector de cuentas, Todas en USD y anuncios evaluados"
```

- [ ] **Step 6: Verificación visual.** Con la skill de la memoria «Ver la UI sin contraseña» (test client con sesión admin sembrada y datos falsos de 2 cuentas SEK, 40 anuncios), renderiza la pestaña y el panel a un HTML temporal y míralo en el navegador a 1280 px y 375 px: nada empuja la página de lado, las tablas hacen scroll dentro de `tw-tabla-scroll`, los KPIs se ven como en Triple Whale. Corrige lo que se vea mal antes de seguir.

---

### Task 11: Catálogo, skill, guía y pendientes

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po` (+ `.mo` compilado)
- Create: `.claude/skills/meta-rendimiento/SKILL.md`
- Modify: `CLAUDE.md` (fila nueva en la tabla «Qué skill cargar»: `| la pestaña Meta, varias cuentas publicitarias por proyecto, `meta_rendimiento/`, la copia de métricas de Meta, las tasas USD | [`meta-rendimiento`](.claude/skills/meta-rendimiento/SKILL.md) |`)
- Modify: `.claude/skills/meta-y-publicacion/SKILL.md` (un párrafo: la Página es opcional desde 2026-10-08; sin Página el proyecto queda «solo métricas»; lanzar y el flujo viejo frenan en palabras)
- Modify: `docs/pendientes.md` (PND-148: anotar que la lectura de varias cuentas ya existe —`meta_cuenta`— y que lanzar por país sigue pendiente; filas nuevas para E2 y E3 con su ID siguiente libre)
- Test: `tests/test_guia_agentes.py` y `tests/test_i18n_catalogo.py` (existentes)

- [ ] **Step 1:** `../../../venv/bin/python3 catalogo_i18n.py actualizar`, traducir al inglés cada msgid nuevo usando `docs/i18n/glosario.md` (sin `fuzzy`), `../../../venv/bin/python3 catalogo_i18n.py compilar`. Lee la skill `idioma` antes.
- [ ] **Step 2:** Escribir la skill (formato de las demás: encabezado, «Si cambias esta área, actualiza este archivo», y un párrafo denso en inglés como `triple-whale/SKILL.md`: módulos, tablas, tareas, job ids, ventanas de copia, «Todas» en USD con BCE, una cuenta por proyecto, Página opcional, trampas: el token nunca en errores, `paging.next` lleva el token, alcance no se suma por días, presupuestos en unidad menor, informes asíncronos para level=ad).
- [ ] **Step 3:** `../../../venv/bin/python3 -m pytest tests/test_guia_agentes.py tests/test_i18n_catalogo.py -q` → PASS; `wc -l CLAUDE.md` ≤ 250.
- [ ] **Step 4:** Suite completa: `../../../venv/bin/python3 -m pytest -q` → todo verde (anota el conteo).
- [ ] **Step 5: Commit**

```bash
git add translations .claude/skills/meta-rendimiento/SKILL.md .claude/skills/meta-y-publicacion/SKILL.md CLAUDE.md docs/pendientes.md
git commit -m "Meta rendimiento: catálogo en inglés, skill, guía y pendientes"
```
