# Experimentos E1 · Datos completos de Meta — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guardar, por anuncio de cada experimento, las métricas día a día de Meta (con embudo y retención de video), los desgloses por ubicación/edad-género/dispositivo/región y los rankings de calidad, sin tocar el refresco de siempre ni el decisor.

**Architecture:** un módulo nuevo del lado de Creatv, `meta_detalle.py`, es el único escritor de dos tablas nuevas (`metrica_dia`, `metrica_desglose`, migración 0028) y de `experimento_pieza.extra["rankings_meta"]`. Pide a Meta a nivel campaña con `level=ad` (una llamada por experimento, no por anuncio) usando `meta_ads.auth.llamar` y las credenciales de `lanzador._con_credenciales`; nunca toca el submódulo `meta_ads`. Corre dentro de `exp_refrescar` (después del refresco de siempre, en su propio `try`) y como tarea propia `exp_detalle` para la carga inicial.

**Tech Stack:** Python 3, SQLAlchemy Core sobre SQLite (WAL), Alembic, Flask-Babel (`gettext`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-experimentos-centro-de-resultados-design.md` (§1, §3, §6, §7).

## Global Constraints

- Leer de Meta no cuesta: ninguna tarea de este plan cobra ni llama `gastos.registrar_seguro`.
- Un fallo del detalle **nunca** tumba `lanzador.refrescar`, el decisor ni la tarea `exp_refrescar`.
- Todo texto de error que se guarde o se registre pasa antes por `cola.sin_token` (regla 6 de CLAUDE.md).
- Aislamiento: solo se guardan filas de anuncios (`ad_id`) que pertenecen a una `experimento_pieza` del experimento pedido; lo demás se ignora.
- Único escritor de `metrica_dia` y `metrica_desglose`: `meta_detalle.py`. `experimento_pieza.extra` solo con `experimentos.marcar_pieza`; `experimento.extra` solo con `experimentos.actualizar_extra` (regla 5).
- Todo texto visible nuevo pasa por `gettext` y el catálogo (`venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md`, `compilar`).
- No se edita nada dentro de `meta_ads/` (submódulo de otro repo).
- Trabajar en el worktree `.claude/worktrees/exp-resultados` (rama `exp-resultados`). Pruebas: `venv/bin/python3 -m pytest -q` (el venv del checkout principal: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).

## Archivos

| Archivo | Qué |
|---|---|
| `db.py` | declara `metrica_dia` y `metrica_desglose` (igual que la migración) |
| `migrations/versions/0028_metricas_detalle.py` | crea las dos tablas con sus índices únicos |
| `meta_detalle.py` (nuevo) | traducir filas de Meta, pedir con paginación, guardar, `refrescar_detalle`, `encolar_todos` |
| `tareas/experimentos.py` | `exp_refrescar` llama al detalle; tarea nueva `exp_detalle` |
| `tests/test_meta_detalle.py` (nuevo) | todo lo de `meta_detalle` |
| `tests/test_migracion_0028.py` (nuevo) | la migración sube/baja y coincide con `db.py` |
| `tests/test_lanzador.py` | se agrega la prueba de que el detalle no tumba `exp_refrescar` |
| `translations/en/LC_MESSAGES/messages.po` | textos nuevos |
| `.claude/skills/experimentos/SKILL.md`, `docs/pendientes.md`, el spec | documentación |

---

### Task 1: Tablas `metrica_dia` y `metrica_desglose` (migración 0028)

**Files:**
- Modify: `db.py` (después de `metrica_snapshot`, ~línea 296)
- Create: `migrations/versions/0028_metricas_detalle.py`
- Test: `tests/test_migracion_0028.py`

**Interfaces:**
- Produces: `db.metrica_dia`, `db.metrica_desglose` (tablas SQLAlchemy). Columnas exactas en el código de abajo; las usan las tareas 4 y 5 y, en E2, `resultados.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migracion_0028.py
"""Migración 0028 (spec 2026-10-02 §3.1): metrica_dia y metrica_desglose suben,
bajan y db.py declara exactamente las mismas columnas e índices únicos."""
import os

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLS_DIA = {"id", "experimento_pieza_id", "fecha", "impresiones", "alcance", "frecuencia", "clics", "clics_enlace",
            "gasto", "cpm", "vistas_3s", "reproducciones", "p25", "p50", "p75", "p95", "p100", "thruplay",
            "tiempo_medio_s", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta", "ingresos_meta",
            "actualizado_en"}
COLS_DESGLOSE = {"id", "experimento_pieza_id", "dimension", "clave", "impresiones", "clics_enlace", "gasto",
                 "vistas_3s", "thruplay", "compras_meta", "ingresos_meta", "actualizado_en"}


def _cols(engine, tabla):
    return {c["name"] for c in sa.inspect(engine).get_columns(tabla)}


def _unicos(engine, tabla):
    insp = sa.inspect(engine)
    nombres = {u["name"] for u in insp.get_unique_constraints(tabla)}
    nombres |= {i["name"] for i in insp.get_indexes(tabla) if i.get("unique")}
    return nombres


def test_0028_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'm.db'}")
    db._reset_para_tests()
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    command.upgrade(cfg, "head")
    assert _cols(db.engine(), "metrica_dia") == COLS_DIA
    assert _cols(db.engine(), "metrica_desglose") == COLS_DESGLOSE
    assert "uq_metrica_dia_pieza_fecha" in _unicos(db.engine(), "metrica_dia")
    assert "uq_metrica_desglose_pieza_dim_clave" in _unicos(db.engine(), "metrica_desglose")
    db._reset_para_tests()
    command.downgrade(cfg, "0027")
    tablas = sa.inspect(db.engine()).get_table_names()
    assert "metrica_dia" not in tablas and "metrica_desglose" not in tablas
    db._reset_para_tests()


def test_db_py_declara_lo_mismo(base_temporal):
    db = base_temporal
    assert _cols(db.engine(), "metrica_dia") == COLS_DIA
    assert _cols(db.engine(), "metrica_desglose") == COLS_DESGLOSE
    assert "uq_metrica_dia_pieza_fecha" in _unicos(db.engine(), "metrica_dia")
    assert "uq_metrica_desglose_pieza_dim_clave" in _unicos(db.engine(), "metrica_desglose")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_migracion_0028.py -q`
Expected: FAIL (`NoSuchTableError` / columnas vacías: las tablas no existen).

- [ ] **Step 3: Declarar las tablas en `db.py`** (justo después de la definición de `metrica_snapshot`)

```python
# Detalle diario de Meta por anuncio (spec 2026-10-02 §3.1). Único escritor:
# meta_detalle.py. Una fila por anuncio y día de la cuenta de Meta; se reemplaza
# al volver a pedir el día (Meta corrige los últimos días).
metrica_dia = Table("metrica_dia", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
    Column("fecha", String(10), nullable=False),
    Column("impresiones", Integer, default=0), Column("alcance", Integer, default=0),
    Column("frecuencia", Float, default=0.0), Column("clics", Integer, default=0),
    Column("clics_enlace", Integer, default=0), Column("gasto", Float, default=0.0),
    Column("cpm", Float, default=0.0), Column("vistas_3s", Integer, default=0),
    Column("reproducciones", Integer, default=0), Column("p25", Integer, default=0),
    Column("p50", Integer, default=0), Column("p75", Integer, default=0),
    Column("p95", Integer, default=0), Column("p100", Integer, default=0),
    Column("thruplay", Integer, default=0), Column("tiempo_medio_s", Float, default=0.0),
    Column("visitas_pagina", Integer, default=0), Column("carrito", Integer, default=0),
    Column("pago_iniciado", Integer, default=0), Column("compras_meta", Integer, default=0),
    Column("ingresos_meta", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("experimento_pieza_id", "fecha", name="uq_metrica_dia_pieza_fecha"),
    sa.Index("ix_metrica_dia_fecha", "fecha"),
)

# Totales desde el inicio por anuncio y valor de una dimensión (ubicacion,
# edad_genero, dispositivo, region). Único escritor: meta_detalle.py; se
# reemplaza el juego completo de (anuncio, dimensión) en cada pasada.
metrica_desglose = Table("metrica_desglose", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
    Column("dimension", String(20), nullable=False),
    Column("clave", String(120), nullable=False),
    Column("impresiones", Integer, default=0), Column("clics_enlace", Integer, default=0),
    Column("gasto", Float, default=0.0), Column("vistas_3s", Integer, default=0),
    Column("thruplay", Integer, default=0), Column("compras_meta", Integer, default=0),
    Column("ingresos_meta", Float, default=0.0),
    Column("actualizado_en", String(19), nullable=False),
    sa.UniqueConstraint("experimento_pieza_id", "dimension", "clave", name="uq_metrica_desglose_pieza_dim_clave"),
)
```

- [ ] **Step 4: Crear la migración `migrations/versions/0028_metricas_detalle.py`**

```python
"""detalle diario y desgloses de Meta por anuncio

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-02 00:00:00.000000

Spec 2026-10-02-experimentos-centro-de-resultados §3.1: metrica_dia (una fila por
anuncio y día, con embudo y retención de video) y metrica_desglose (totales
desde el inicio por anuncio y valor de una dimensión). Las escribe solo
meta_detalle.py y las lee el centro de resultados.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT = ("impresiones", "alcance", "clics", "clics_enlace", "vistas_3s", "reproducciones", "p25", "p50", "p75",
        "p95", "p100", "thruplay", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta")
_FLOAT = ("frecuencia", "gasto", "cpm", "tiempo_medio_s", "ingresos_meta")


def upgrade() -> None:
    op.create_table(
        "metrica_dia",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experimento_pieza_id", sa.Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
        sa.Column("fecha", sa.String(10), nullable=False),
        *[sa.Column(c, sa.Integer) for c in _INT],
        *[sa.Column(c, sa.Float) for c in _FLOAT],
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("experimento_pieza_id", "fecha", name="uq_metrica_dia_pieza_fecha"),
    )
    op.create_index("ix_metrica_dia_fecha", "metrica_dia", ["fecha"])
    op.create_table(
        "metrica_desglose",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experimento_pieza_id", sa.Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("clave", sa.String(120), nullable=False),
        *[sa.Column(c, sa.Integer) for c in ("impresiones", "clics_enlace", "vistas_3s", "thruplay", "compras_meta")],
        *[sa.Column(c, sa.Float) for c in ("gasto", "ingresos_meta")],
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("experimento_pieza_id", "dimension", "clave", name="uq_metrica_desglose_pieza_dim_clave"),
    )


def downgrade() -> None:
    op.drop_table("metrica_desglose")
    op.drop_index("ix_metrica_dia_fecha", table_name="metrica_dia")
    op.drop_table("metrica_dia")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_migracion_0028.py tests/test_indices_escala.py tests/test_db.py -q`
Expected: PASS (las tres; `test_indices_escala` sigue bajando a 0025 sin problema).

- [ ] **Step 6: Commit**

```bash
git add db.py migrations/versions/0028_metricas_detalle.py tests/test_migracion_0028.py
git commit -m "E1: tablas metrica_dia y metrica_desglose (migración 0028)"
```

---

### Task 2: Traducir las filas de Meta (funciones puras)

**Files:**
- Create: `meta_detalle.py`
- Test: `tests/test_meta_detalle.py`

**Interfaces:**
- Produces:
  - `meta_detalle.fila_diaria(fila: dict) -> dict` — columnas de `metrica_dia` sin `experimento_pieza_id`, `id` ni `actualizado_en`, con `fecha` (de `date_start`).
  - `meta_detalle.fila_desglose(fila: dict, dimension: str) -> tuple[str, dict]` — `(clave, valores)` con las columnas numéricas de `metrica_desglose`.
  - `meta_detalle.rankings_de(fila: dict) -> dict` — `{"calidad", "interaccion", "conversion"}` (texto de Meta o `None`).
  - `meta_detalle.DIMENSIONES: dict[str, str]` — `{"ubicacion": "publisher_platform,platform_position", "edad_genero": "age,gender", "dispositivo": "device_platform", "region": "region"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_meta_detalle.py
"""meta_detalle (spec 2026-10-02 §3): traducir filas de Meta, pedir con
paginación, guardar sin cruzar proyectos y refrescar sin tumbar nada."""
import pytest

FILA_DIA = {
    "ad_id": "ad_1", "date_start": "2026-09-30", "date_stop": "2026-09-30",
    "impressions": "1000", "reach": "800", "frequency": "1.25", "clicks": "40", "inline_link_clicks": "25",
    "spend": "12.5", "cpm": "12.5",
    "actions": [{"action_type": "video_view", "value": "300"}, {"action_type": "landing_page_view", "value": "18"},
                {"action_type": "omni_add_to_cart", "value": "4"}, {"action_type": "add_to_cart", "value": "4"},
                {"action_type": "omni_initiated_checkout", "value": "2"}, {"action_type": "purchase", "value": "1"}],
    "action_values": [{"action_type": "purchase", "value": "59.9"}],
    "video_play_actions": [{"action_type": "video_view", "value": "900"}],
    "video_p25_watched_actions": [{"action_type": "video_view", "value": "220"}],
    "video_p50_watched_actions": [{"action_type": "video_view", "value": "150"}],
    "video_p75_watched_actions": [{"action_type": "video_view", "value": "90"}],
    "video_p95_watched_actions": [{"action_type": "video_view", "value": "60"}],
    "video_p100_watched_actions": [{"action_type": "video_view", "value": "50"}],
    "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "70"}],
    "video_avg_time_watched_actions": [{"action_type": "video_view", "value": "4.2"}],
}


def test_fila_diaria_traduce_campos_y_acciones():
    import meta_detalle as md
    f = md.fila_diaria(FILA_DIA)
    assert f["fecha"] == "2026-09-30"
    assert (f["impresiones"], f["alcance"], f["clics"], f["clics_enlace"]) == (1000, 800, 40, 25)
    assert f["frecuencia"] == 1.25 and f["gasto"] == 12.5 and f["cpm"] == 12.5
    assert f["vistas_3s"] == 300 and f["reproducciones"] == 900
    assert (f["p25"], f["p50"], f["p75"], f["p95"], f["p100"]) == (220, 150, 90, 60, 50)
    assert f["thruplay"] == 70 and f["tiempo_medio_s"] == 4.2
    # carrito: omni_ primero y sin sumar el duplicado add_to_cart
    assert f["visitas_pagina"] == 18 and f["carrito"] == 4 and f["pago_iniciado"] == 2
    assert f["compras_meta"] == 1 and f["ingresos_meta"] == 59.9


def test_fila_diaria_sin_video_ni_acciones_da_ceros():
    import meta_detalle as md
    f = md.fila_diaria({"date_start": "2026-10-01", "impressions": "10", "spend": "1"})
    assert f["impresiones"] == 10 and f["gasto"] == 1.0
    assert f["vistas_3s"] == f["p25"] == f["carrito"] == f["compras_meta"] == 0 and f["ingresos_meta"] == 0.0


@pytest.mark.parametrize("dimension, extra, clave", [
    ("ubicacion", {"publisher_platform": "instagram", "platform_position": "instagram_reels"}, "instagram|instagram_reels"),
    ("edad_genero", {"age": "25-34", "gender": "female"}, "25-34|female"),
    ("dispositivo", {"device_platform": "mobile_app"}, "mobile_app"),
    ("region", {"region": "Antioquia"}, "Antioquia"),
])
def test_fila_desglose_arma_la_clave(dimension, extra, clave):
    import meta_detalle as md
    fila = {**FILA_DIA, **extra}
    k, v = md.fila_desglose(fila, dimension)
    assert k == clave
    assert v == {"impresiones": 1000, "clics_enlace": 25, "gasto": 12.5, "vistas_3s": 300, "thruplay": 70,
                 "compras_meta": 1, "ingresos_meta": 59.9}


def test_rankings_de():
    import meta_detalle as md
    r = md.rankings_de({"quality_ranking": "ABOVE_AVERAGE", "engagement_rate_ranking": "AVERAGE",
                        "conversion_rate_ranking": "UNKNOWN"})
    assert r == {"calidad": "ABOVE_AVERAGE", "interaccion": "AVERAGE", "conversion": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'meta_detalle'`.

- [ ] **Step 3: Write minimal implementation (`meta_detalle.py`)**

```python
"""
Detalle de Meta por anuncio para el centro de resultados (spec
2026-10-02-experimentos-centro-de-resultados §3): día a día (con embudo y
retención de video), desgloses desde el inicio (ubicación, edad y género,
dispositivo, región) y los rankings de calidad de Meta.

Único escritor de `metrica_dia` y `metrica_desglose`, y de
`experimento_pieza.extra["rankings_meta"]` (vía experimentos.marcar_pieza).
Pide a nivel campaña con level=ad (una llamada por experimento, no por
anuncio) usando meta_ads.auth.llamar; no toca el submódulo meta_ads. Leer de
Meta no cuesta: nada de aquí registra gasto. Un fallo de aquí nunca debe
tumbar lanzador.refrescar ni el decisor.
"""
import logging

log = logging.getLogger("creatv.meta_detalle")

# Dimensión -> breakdowns de la Graph API (la clave guardada une sus valores con «|»).
DIMENSIONES = {"ubicacion": "publisher_platform,platform_position", "edad_genero": "age,gender",
               "dispositivo": "device_platform", "region": "region"}

# Tipos de acción por paso del embudo, en orden de preferencia: Meta repite el
# mismo evento con y sin «omni_»; se toma el primero que exista (sumarlos
# contaría doble).
_CARRITO = ("omni_add_to_cart", "add_to_cart", "offsite_conversion.fb_pixel_add_to_cart")
_PAGO = ("omni_initiated_checkout", "initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout")
_COMPRA = ("purchase", "omni_purchase")   # mismo orden que meta_ads/insights.obtener_resultados


def _num(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _accion(lista, tipo):
    for a in lista or []:
        if a.get("action_type") == tipo:
            return _num(a.get("value"))
    return 0.0


def _primera(lista, tipos):
    """Valor del primer tipo de acción presente (aunque valga 0)."""
    presentes = {a.get("action_type") for a in lista or []}
    for t in tipos:
        if t in presentes:
            return _accion(lista, t)
    return 0.0


def _video(fila, campo):
    return _accion(fila.get(campo), "video_view")


def fila_diaria(fila):
    """Fila de insights (level=ad, time_increment=1) -> columnas de metrica_dia."""
    acciones = fila.get("actions")
    return {
        "fecha": fila.get("date_start"),
        "impresiones": int(_num(fila.get("impressions"))), "alcance": int(_num(fila.get("reach"))),
        "frecuencia": _num(fila.get("frequency")), "clics": int(_num(fila.get("clicks"))),
        "clics_enlace": int(_num(fila.get("inline_link_clicks"))), "gasto": _num(fila.get("spend")),
        "cpm": _num(fila.get("cpm")),
        "vistas_3s": int(_accion(acciones, "video_view")),
        "reproducciones": int(_video(fila, "video_play_actions")),
        "p25": int(_video(fila, "video_p25_watched_actions")), "p50": int(_video(fila, "video_p50_watched_actions")),
        "p75": int(_video(fila, "video_p75_watched_actions")), "p95": int(_video(fila, "video_p95_watched_actions")),
        "p100": int(_video(fila, "video_p100_watched_actions")),
        "thruplay": int(_video(fila, "video_thruplay_watched_actions")),
        "tiempo_medio_s": _video(fila, "video_avg_time_watched_actions"),
        "visitas_pagina": int(_accion(acciones, "landing_page_view")),
        "carrito": int(_primera(acciones, _CARRITO)), "pago_iniciado": int(_primera(acciones, _PAGO)),
        "compras_meta": int(_primera(acciones, _COMPRA)),
        "ingresos_meta": _primera(fila.get("action_values"), _COMPRA),
    }


def fila_desglose(fila, dimension):
    """Fila de insights con breakdowns -> (clave, columnas de metrica_desglose)."""
    clave = "|".join(str(fila.get(c) or "") for c in DIMENSIONES[dimension].split(","))
    d = fila_diaria(fila)
    return clave, {k: d[k] for k in ("impresiones", "clics_enlace", "gasto", "vistas_3s", "thruplay",
                                     "compras_meta", "ingresos_meta")}


def _ranking(valor):
    return None if not valor or valor == "UNKNOWN" else valor


def rankings_de(fila):
    return {"calidad": _ranking(fila.get("quality_ranking")),
            "interaccion": _ranking(fila.get("engagement_rate_ranking")),
            "conversion": _ranking(fila.get("conversion_rate_ranking"))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q`
Expected: PASS (7 pruebas).

- [ ] **Step 5: Commit**

```bash
git add meta_detalle.py tests/test_meta_detalle.py
git commit -m "E1: meta_detalle traduce filas diarias, desgloses y rankings de Meta"
```

---

### Task 3: Pedir a Meta con paginación

**Files:**
- Modify: `meta_detalle.py`
- Test: `tests/test_meta_detalle.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar(metodo, edge, payload=None, params=None)`, `meta_ads.auth.ad_account_id()`.
- Produces:
  - `meta_detalle.pedir_diario(campaign_id: str, desde: str, hasta: str) -> list[dict]` (filas crudas, fechas `YYYY-MM-DD`).
  - `meta_detalle.pedir_desglose(campaign_id: str, dimension: str) -> list[dict]`.
  - `meta_detalle.pedir_rankings(campaign_id: str) -> list[dict]`.
  - `meta_detalle.MAX_PAGINAS = 20`.

- [ ] **Step 1: Write the failing test** (agregar a `tests/test_meta_detalle.py`)

```python
import json


class LlamarFalso:
    """Reemplaza meta_ads.auth.llamar: responde por edge/params y anota las llamadas."""
    def __init__(self, paginas):
        self.paginas = list(paginas)   # cada una: {"data": [...], "paging": {...}}
        self.llamadas = []

    def __call__(self, metodo, edge, payload=None, params=None, dry_run=False):
        self.llamadas.append((metodo, edge, dict(params or {})))
        return self.paginas.pop(0)


def _con_llamar(monkeypatch, paginas):
    import meta_detalle as md
    falso = LlamarFalso(paginas)
    monkeypatch.setattr(md.auth, "llamar", falso)
    monkeypatch.setattr(md.auth, "ad_account_id", lambda: "123")
    return md, falso


def test_pedir_diario_arma_la_consulta_y_sigue_paginas(monkeypatch):
    md, falso = _con_llamar(monkeypatch, [
        {"data": [{"ad_id": "a"}], "paging": {"cursors": {"after": "C1"}, "next": "https://graph/next"}},
        {"data": [{"ad_id": "b"}], "paging": {"cursors": {"after": "C2"}}},
    ])
    filas = md.pedir_diario("cmp_9", "2026-09-01", "2026-09-30")
    assert [f["ad_id"] for f in filas] == ["a", "b"]
    metodo, edge, params = falso.llamadas[0]
    assert metodo == "GET" and edge == "act_123/insights"
    assert params["level"] == "ad" and params["time_increment"] == 1
    assert json.loads(params["time_range"]) == {"since": "2026-09-01", "until": "2026-09-30"}
    assert json.loads(params["filtering"]) == [{"field": "campaign.id", "operator": "EQUAL", "value": "cmp_9"}]
    assert "video_p25_watched_actions" in params["fields"] and "ad_id" in params["fields"]
    assert "after" not in params and falso.llamadas[1][2]["after"] == "C1"


def test_pedir_para_en_max_paginas(monkeypatch):
    import meta_detalle as md
    pagina = {"data": [{"ad_id": "x"}], "paging": {"cursors": {"after": "C"}, "next": "https://graph/next"}}
    md2, falso = _con_llamar(monkeypatch, [dict(pagina) for _ in range(md.MAX_PAGINAS + 5)])
    assert len(md2.pedir_rankings("cmp")) == md.MAX_PAGINAS
    assert len(falso.llamadas) == md.MAX_PAGINAS


def test_pedir_desglose_y_rankings(monkeypatch):
    md, falso = _con_llamar(monkeypatch, [{"data": [{"ad_id": "a", "age": "25-34", "gender": "female"}]},
                                          {"data": [{"ad_id": "a", "quality_ranking": "AVERAGE"}]}])
    assert md.pedir_desglose("cmp", "edad_genero")[0]["age"] == "25-34"
    _, _, p1 = falso.llamadas[0]
    assert p1["breakdowns"] == "age,gender" and p1["date_preset"] == "maximum" and "time_increment" not in p1
    assert "video_p25_watched_actions" not in p1["fields"]   # sin campos de video en desgloses
    md.pedir_rankings("cmp")
    _, _, p2 = falso.llamadas[1]
    assert "quality_ranking" in p2["fields"] and p2["date_preset"] == "maximum"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q -k pedir`
Expected: FAIL con `AttributeError: module 'meta_detalle' has no attribute 'auth'`.

- [ ] **Step 3: Implement** (agregar a `meta_detalle.py`; el import va arriba, junto a `logging`)

```python
import json

from meta_ads import auth

MAX_PAGINAS = 20
_BASE = "ad_id,impressions,reach,frequency,clicks,inline_link_clicks,spend,cpm,actions,action_values"
CAMPOS_DIA = (_BASE + ",video_play_actions,video_p25_watched_actions,video_p50_watched_actions"
              ",video_p75_watched_actions,video_p95_watched_actions,video_p100_watched_actions"
              ",video_thruplay_watched_actions,video_avg_time_watched_actions")
# Desgloses: sin los campos de retención (Meta rechaza algunas combinaciones de
# video con desgloses); el gancho sale de actions[video_view].
CAMPOS_DESGLOSE = _BASE + ",video_thruplay_watched_actions"
CAMPOS_RANKINGS = "ad_id,impressions,quality_ranking,engagement_rate_ranking,conversion_rate_ranking"


def _filtro_campana(campaign_id):
    return json.dumps([{"field": "campaign.id", "operator": "EQUAL", "value": str(campaign_id)}])


def _paginas(params):
    """GET act_<cuenta>/insights siguiendo el cursor `after` hasta MAX_PAGINAS."""
    filas, after = [], None
    for _ in range(MAX_PAGINAS):
        p = dict(params, limit=500)
        if after:
            p["after"] = after
        data = auth.llamar("GET", f"act_{auth.ad_account_id()}/insights", params=p) or {}
        filas.extend(data.get("data") or [])
        paging = data.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            return filas
    log.warning("Detalle de Meta: se cortó en %s páginas", MAX_PAGINAS)
    return filas


def pedir_diario(campaign_id, desde, hasta):
    return _paginas({"level": "ad", "fields": CAMPOS_DIA, "filtering": _filtro_campana(campaign_id),
                     "time_increment": 1, "time_range": json.dumps({"since": desde, "until": hasta})})


def pedir_desglose(campaign_id, dimension):
    return _paginas({"level": "ad", "fields": CAMPOS_DESGLOSE, "filtering": _filtro_campana(campaign_id),
                     "date_preset": "maximum", "breakdowns": DIMENSIONES[dimension]})


def pedir_rankings(campaign_id):
    return _paginas({"level": "ad", "fields": CAMPOS_RANKINGS, "filtering": _filtro_campana(campaign_id),
                     "date_preset": "maximum"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meta_detalle.py tests/test_meta_detalle.py
git commit -m "E1: meta_detalle pide día a día, desgloses y rankings a nivel campaña con paginación"
```

---

### Task 4: Guardar sin cruzar proyectos

**Files:**
- Modify: `meta_detalle.py`
- Test: `tests/test_meta_detalle.py`

**Interfaces:**
- Consumes: `db.metrica_dia`, `db.metrica_desglose` (Task 1), `fila_diaria`, `fila_desglose`, `rankings_de` (Task 2), `experimentos.marcar_pieza(cliente, ep_id, **flags)`.
- Produces:
  - `meta_detalle.guardar_dias(ep_por_ad: dict[str, int], filas: list[dict]) -> int` (filas escritas).
  - `meta_detalle.guardar_desglose(ep_por_ad: dict[str, int], dimension: str, filas: list[dict]) -> int`.
  - `meta_detalle.guardar_rankings(cliente: str, ep_por_ad: dict[str, int], filas: list[dict]) -> int`.
  - `meta_detalle.desde_para(ep_ids: list[int], creado_en: str, hoy: datetime.date) -> str` (`YYYY-MM-DD`).

- [ ] **Step 1: Write the failing test** (agregar a `tests/test_meta_detalle.py`)

```python
from datetime import date

import sqlalchemy as sa


@pytest.fixture()
def dos_piezas(base_temporal):
    """Experimento de acme con dos anuncios (ad_1 en CO, ad_2 en MX)."""
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    ep1 = ex.agregar_pieza("acme", eid, clon, "CO")
    ep2 = ex.agregar_pieza("acme", eid, clon, "MX")
    ex.actualizar_pieza("acme", ep1, meta_ad_id="ad_1")
    ex.actualizar_pieza("acme", ep2, meta_ad_id="ad_2")
    ex.actualizar("acme", eid, meta_campaign_id="cmp_1")
    return {"db": base_temporal, "ex": ex, "eid": eid, "ep1": ep1, "ep2": ep2}


def _filas(db, tabla):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(tabla).order_by(tabla.c.id))]


def test_guardar_dias_reemplaza_el_dia_e_ignora_anuncios_ajenos(dos_piezas):
    import meta_detalle as md
    db, ep1 = dos_piezas["db"], dos_piezas["ep1"]
    mapa = {"ad_1": ep1, "ad_2": dos_piezas["ep2"]}
    n = md.guardar_dias(mapa, [{**FILA_DIA, "ad_id": "ad_1"}, {**FILA_DIA, "ad_id": "ad_de_otro_proyecto"}])
    assert n == 1
    md.guardar_dias(mapa, [{**FILA_DIA, "ad_id": "ad_1", "impressions": "1500"}])   # Meta corrigió el día
    filas = _filas(db, db.metrica_dia)
    assert len(filas) == 1 and filas[0]["experimento_pieza_id"] == ep1 and filas[0]["impresiones"] == 1500
    assert filas[0]["fecha"] == "2026-09-30" and filas[0]["actualizado_en"]


def test_guardar_desglose_reemplaza_el_juego_completo(dos_piezas):
    import meta_detalle as md
    db, ep1 = dos_piezas["db"], dos_piezas["ep1"]
    mapa = {"ad_1": ep1}
    md.guardar_desglose(mapa, "edad_genero", [{**FILA_DIA, "ad_id": "ad_1", "age": "18-24", "gender": "male"},
                                             {**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female"}])
    md.guardar_desglose(mapa, "dispositivo", [{**FILA_DIA, "ad_id": "ad_1", "device_platform": "mobile_app"}])
    md.guardar_desglose(mapa, "edad_genero", [{**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female"}])
    claves = sorted((f["dimension"], f["clave"]) for f in _filas(db, db.metrica_desglose))
    assert claves == [("dispositivo", "mobile_app"), ("edad_genero", "25-34|female")]


def test_guardar_rankings_en_extra_de_la_pieza(dos_piezas):
    import meta_detalle as md
    ex, ep1 = dos_piezas["ex"], dos_piezas["ep1"]
    ex.marcar_pieza("acme", ep1, archivado=False)   # lo que ya había en extra se conserva
    md.guardar_rankings("acme", {"ad_1": ep1}, [{"ad_id": "ad_1", "quality_ranking": "ABOVE_AVERAGE"},
                                                {"ad_id": "ajeno", "quality_ranking": "BELOW_AVERAGE_10"}])
    extra = [p for p in ex.obtener("acme", dos_piezas["eid"])["piezas"] if p["id"] == ep1][0]["extra"]
    assert extra["rankings_meta"]["calidad"] == "ABOVE_AVERAGE" and extra["archivado"] is False


def test_desde_para_sin_datos_y_con_datos(dos_piezas):
    import meta_detalle as md
    ep1 = dos_piezas["ep1"]
    assert md.desde_para([ep1], "2026-09-10T08:00:00", date(2026, 10, 2)) == "2026-09-10"
    md.guardar_dias({"ad_1": ep1}, [{**FILA_DIA, "ad_id": "ad_1"}])   # último día guardado: 30 sep
    assert md.desde_para([ep1], "2026-09-10T08:00:00", date(2026, 10, 2)) == "2026-09-28"
    # nunca después de hoy
    assert md.desde_para([ep1], "2026-12-01T00:00:00", date(2026, 10, 2)) == "2026-09-28"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q -k "guardar or desde_para"`
Expected: FAIL con `AttributeError: ... 'guardar_dias'`.

- [ ] **Step 3: Implement** (agregar a `meta_detalle.py`; imports arriba)

```python
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
import experimentos

# Días hacia atrás que se vuelven a pedir aunque ya estén: Meta corrige los últimos días.
DIAS_REPASO = 2


def guardar_dias(ep_por_ad, filas):
    """Upsert por (anuncio, fecha). Filas de anuncios fuera de `ep_por_ad` se ignoran."""
    n = 0
    ahora = db.ahora()
    with db.conectar() as con:
        for fila in filas:
            ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
            valores = fila_diaria(fila)
            if not ep_id or not valores["fecha"]:
                continue
            valores.update(experimento_pieza_id=ep_id, actualizado_en=ahora)
            stmt = insert_sqlite(db.metrica_dia).values(**valores)
            con.execute(stmt.on_conflict_do_update(
                index_elements=["experimento_pieza_id", "fecha"],
                set_={k: v for k, v in valores.items() if k not in ("experimento_pieza_id", "fecha")}))
            n += 1
    return n


def guardar_desglose(ep_por_ad, dimension, filas):
    """Reemplaza, en una transacción, el juego (anuncio, dimensión) de cada anuncio que vino en `filas`."""
    por_ep = {}
    for fila in filas:
        ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
        if ep_id:
            clave, valores = fila_desglose(fila, dimension)
            por_ep.setdefault(ep_id, {})[clave] = valores
    ahora = db.ahora()
    t = db.metrica_desglose
    with db.conectar() as con:
        for ep_id, por_clave in por_ep.items():
            con.execute(t.delete().where(t.c.experimento_pieza_id == ep_id, t.c.dimension == dimension))
            for clave, valores in por_clave.items():
                con.execute(t.insert().values(experimento_pieza_id=ep_id, dimension=dimension, clave=clave[:120],
                                              actualizado_en=ahora, **valores))
    return sum(len(v) for v in por_ep.values())


def guardar_rankings(cliente, ep_por_ad, filas):
    n = 0
    for fila in filas:
        ep_id = ep_por_ad.get(str(fila.get("ad_id") or ""))
        if ep_id:
            experimentos.marcar_pieza(cliente, ep_id, rankings_meta=rankings_de(fila))
            n += 1
    return n


def desde_para(ep_ids, creado_en, hoy):
    """Desde qué día pedir: el último guardado menos DIAS_REPASO (se cura solo si
    el worker estuvo parado), o el día en que se creó el experimento. Nunca
    después de hoy."""
    with db.conectar() as con:
        ultimo = con.execute(sa.select(sa.func.max(db.metrica_dia.c.fecha))
                             .where(db.metrica_dia.c.experimento_pieza_id.in_(list(ep_ids) or [-1]))).scalar()
    if ultimo:
        desde = date.fromisoformat(ultimo) - timedelta(days=DIAS_REPASO)
    else:
        desde = date.fromisoformat((creado_en or hoy.isoformat())[:10])
    return min(desde, hoy).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meta_detalle.py tests/test_meta_detalle.py
git commit -m "E1: meta_detalle guarda día a día, desgloses y rankings solo de los anuncios del experimento"
```

---

### Task 5: `refrescar_detalle` (orquesta, nunca revienta)

**Files:**
- Modify: `meta_detalle.py`
- Test: `tests/test_meta_detalle.py`

**Interfaces:**
- Consumes: `lanzador._con_credenciales(cliente, fn)`, `experimentos.obtener`, `experimentos.actualizar_extra(cliente, eid, fn)`, `cola.sin_token`, `meta_errores._numero(texto, "code")`, `meta_errores._LIMITE`.
- Produces:
  - `meta_detalle.refrescar_detalle(cliente: str, experimento_id: int, hoy: datetime.date | None = None) -> dict` con claves `dias`, `desgloses`, `rankings` (int), `limite` (bool), `errores` (`{parte: texto}`). Nunca lanza.
  - `experimento.extra["detalle_meta"] = {"actualizado_en": iso, "desde": "YYYY-MM-DD", "errores": {parte: texto}, "limite": bool}` — lo leerá E2 para decir «detalle al día hace N h» o mostrar el error.
  - `meta_detalle.es_limite(texto: str) -> bool`.

- [ ] **Step 1: Write the failing test** (agregar a `tests/test_meta_detalle.py`)

```python
@pytest.fixture()
def con_meta(dos_piezas, monkeypatch):
    """Credenciales de mentira y un auth.llamar que responde por tipo de consulta."""
    import lanzador
    import meta_detalle as md
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "TOKEN-SECRETO", "ad_account_id": "123", "page_id": "2"})
    respuestas = {"diario": {"data": [{**FILA_DIA, "ad_id": "ad_1"}, {**FILA_DIA, "ad_id": "ad_2"}]},
                  "rankings": {"data": [{"ad_id": "ad_1", "quality_ranking": "AVERAGE"}]}}
    fallar = {}
    llamadas = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        params = params or {}
        parte = (params.get("breakdowns") and [k for k, v in md.DIMENSIONES.items() if v == params["breakdowns"]][0]
                 or ("diario" if "time_increment" in params else "rankings"))
        llamadas.append(parte)
        if parte in fallar:
            raise RuntimeError(fallar[parte])
        if parte in md.DIMENSIONES:
            return {"data": [{**FILA_DIA, "ad_id": "ad_1", "age": "25-34", "gender": "female",
                              "publisher_platform": "instagram", "platform_position": "feed",
                              "device_platform": "mobile_app", "region": "Antioquia"}]}
        return respuestas[parte]

    monkeypatch.setattr(md.auth, "llamar", llamar)
    return {**dos_piezas, "md": md, "fallar": fallar, "llamadas": llamadas}


def test_refrescar_detalle_guarda_todo_y_anota_en_extra(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["dias"] == 2 and r["desgloses"] == 4 and r["rankings"] == 1 and r["errores"] == {} and not r["limite"]
    assert con_meta["llamadas"] == ["diario", "ubicacion", "edad_genero", "dispositivo", "region", "rankings"]
    det = ex.obtener("acme", eid)["extra"]["detalle_meta"]
    assert det["errores"] == {} and det["limite"] is False and det["actualizado_en"]


def test_un_desglose_que_falla_no_tumba_los_otros_ni_filtra_el_token(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    con_meta["fallar"]["region"] = 'Meta Ads (act_123/insights) respondió 400: {"error":{"code":100,"message":"bad access_token=TOKEN-SECRETO"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["desgloses"] == 3 and r["rankings"] == 1 and "region" in r["errores"]
    det = ex.obtener("acme", eid)["extra"]["detalle_meta"]
    assert "TOKEN-SECRETO" not in json.dumps(det) and "region" in det["errores"]


def test_limite_de_meta_para_la_pasada(con_meta):
    md, eid = con_meta["md"], con_meta["eid"]
    con_meta["fallar"]["ubicacion"] = 'Meta Ads (act_123/insights) respondió 400: {"error":{"code":17,"message":"User request limit reached"}}'
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert r["limite"] is True and r["dias"] == 2
    assert con_meta["llamadas"] == ["diario", "ubicacion"]   # no sigue golpeando a Meta


def test_falla_el_diario_no_lanza(con_meta):
    md, eid = con_meta["md"], con_meta["eid"]
    con_meta["fallar"]["diario"] = "Meta Ads (act_123/insights) falló en red: ConnectionError"
    r = md.refrescar_detalle("acme", eid, hoy=date(2026, 10, 2))
    assert "diario" in r["errores"] and r["dias"] == 0


def test_sin_campana_o_de_otro_proyecto_no_llama(con_meta):
    md, ex, eid = con_meta["md"], con_meta["ex"], con_meta["eid"]
    assert md.refrescar_detalle("otro", eid)["dias"] == 0
    ex.actualizar("acme", eid, meta_campaign_id=None)
    assert md.refrescar_detalle("acme", eid)["dias"] == 0
    assert con_meta["llamadas"] == []


def test_es_limite():
    import meta_detalle as md
    assert md.es_limite('respondió 400: {"error":{"code":613}}')
    assert not md.es_limite('respondió 400: {"error":{"code":100}}') and not md.es_limite("")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q -k "refrescar or limite"`
Expected: FAIL con `AttributeError: ... 'refrescar_detalle'`.

- [ ] **Step 3: Implement** (agregar a `meta_detalle.py`; imports arriba)

```python
import cola
import lanzador
import meta_errores


class _Limite(Exception):
    """Meta pidió esperar (códigos de límite): se corta la pasada entera."""


def es_limite(texto):
    return meta_errores._numero(str(texto or ""), "code") in meta_errores._LIMITE


def _con_detalle(resultado):
    def fn(extra):
        return {**extra, "detalle_meta": {"actualizado_en": db.ahora(), "desde": resultado.get("desde"),
                                           "errores": resultado["errores"], "limite": resultado["limite"]}}
    return fn


def refrescar_detalle(cliente, experimento_id, hoy=None):
    """Pide y guarda el detalle de un experimento. Nunca lanza: los errores
    (sin token) quedan en el resultado y en experimento.extra["detalle_meta"]."""
    r = {"dias": 0, "desgloses": 0, "rankings": 0, "limite": False, "errores": {}}
    ex = experimentos.obtener(cliente, experimento_id)
    if not ex or not ex.get("meta_campaign_id"):
        return r
    ep_por_ad = {str(p["meta_ad_id"]): p["id"] for p in ex["piezas"] if p.get("meta_ad_id")}
    if not ep_por_ad:
        return r
    hoy = hoy or date.today()
    r["desde"] = desde_para(list(ep_por_ad.values()), ex.get("creado_en"), hoy)
    campana = ex["meta_campaign_id"]

    def _parte(nombre, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — una parte no tumba las otras
            texto = cola.sin_token(str(e))
            r["errores"][nombre] = cola.recortar(texto)
            log.warning("Detalle de Meta (%s, exp %s, %s): %s", cliente, experimento_id, nombre, texto)
            if es_limite(texto):
                raise _Limite() from None

    def _correr(_creds):
        _parte("diario", lambda: r.__setitem__("dias", guardar_dias(ep_por_ad, pedir_diario(campana, r["desde"], hoy.isoformat()))))
        for dim in DIMENSIONES:
            _parte(dim, lambda dim=dim: r.__setitem__("desgloses", r["desgloses"] + guardar_desglose(ep_por_ad, dim, pedir_desglose(campana, dim))))
        _parte("rankings", lambda: r.__setitem__("rankings", guardar_rankings(cliente, ep_por_ad, pedir_rankings(campana))))

    try:
        lanzador._con_credenciales(cliente, _correr)
    except _Limite:
        r["limite"] = True
    except Exception as e:  # noqa: BLE001 — p. ej. Meta sin conectar
        r["errores"]["credenciales"] = cola.recortar(cola.sin_token(str(e)))
    experimentos.actualizar_extra(cliente, experimento_id, _con_detalle(r))
    return r
```

> Nota para quien implementa: confirma que `cola.recortar` existe (lo usa `lanzador.lanzar`); si no, usa `texto[:500]`. `lanzador._con_credenciales` llama `meta_conexion.credenciales_ads` y `meta_auth.configurar`; en las pruebas `credenciales_ads` está reemplazado y `meta_auth` es el real, que solo guarda el token en memoria.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py -q`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add meta_detalle.py tests/test_meta_detalle.py
git commit -m "E1: refrescar_detalle pide todo, para ante el límite de Meta y nunca tumba al llamador"
```

---

### Task 6: Tareas del worker (`exp_refrescar` + `exp_detalle`) y la carga inicial

**Files:**
- Modify: `tareas/experimentos.py:52-75` (job ids, `exp_refrescar`, tarea nueva)
- Modify: `meta_detalle.py` (`encolar_todos`)
- Test: `tests/test_meta_detalle.py`, `tests/test_lanzador.py`

**Interfaces:**
- Consumes: `meta_detalle.refrescar_detalle` (Task 5), `cola.encolar(tipo, payload, *, cliente, job_id, duracion_estimada, max_intentos)`.
- Produces:
  - `tareas.experimentos.job_id_detalle(cliente, experimento_id) -> str` = `f"{cliente}__exp{experimento_id}__detalle"`.
  - Tarea `exp_detalle` (payload `{"cliente", "experimento_id"}`, `max_intentos=2`, no cobra).
  - `meta_detalle.encolar_todos() -> int` (encola `exp_detalle` para cada experimento no legado con `meta_campaign_id`).

- [ ] **Step 1: Write the failing tests**

En `tests/test_meta_detalle.py`:

```python
def test_tarea_exp_detalle_y_encolar_todos(con_meta, monkeypatch):
    import cola
    import tareas
    from tareas import experimentos as t_exp
    md, eid = con_meta["md"], con_meta["eid"]
    encoladas = []
    monkeypatch.setattr(md.cola, "encolar", lambda tipo, payload, **kw: encoladas.append((tipo, payload, kw)) or 1)
    assert md.encolar_todos() == 1
    tipo, payload, kw = encoladas[0]
    assert tipo == "exp_detalle" and payload == {"cliente": "acme", "experimento_id": eid}
    assert kw["job_id"] == t_exp.job_id_detalle("acme", eid) and kw["max_intentos"] == 2 and kw["cliente"] == "acme"
    texto = tareas.REGISTRO["exp_detalle"]({"payload": payload, "job_id": kw["job_id"]})
    assert "2" in texto   # «Detalle de Meta al día (2 días de anuncios…)»
```

En `tests/test_lanzador.py` (al final):

```python
def test_exp_refrescar_sigue_aunque_el_detalle_reviente(entorno, monkeypatch):
    import meta_detalle
    import tareas
    from tareas import experimentos as _t_exp  # noqa: F401 — registra las tareas de experimentos
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    llamado = []

    def explota(cliente, experimento_id, hoy=None):
        llamado.append(experimento_id)
        raise RuntimeError("no debería pasar, pero si pasa no tumba nada")

    monkeypatch.setattr(meta_detalle, "refrescar_detalle", explota)
    texto = tareas.REGISTRO["exp_refrescar"]({"payload": {"cliente": "acme", "experimento_id": eid}, "job_id": "j"})
    assert llamado == [eid] and "3" in texto
    assert ex.obtener("acme", eid)["gasto_acumulado"] == 6.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py tests/test_lanzador.py -q -k "exp_detalle or detalle_reviente"`
Expected: FAIL (`KeyError: 'exp_detalle'` y `llamado == []`).

- [ ] **Step 3: Implement**

En `tareas/experimentos.py`, agregar `import meta_detalle` a los imports y, junto a los otros `job_id_*`:

```python
def job_id_detalle(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__detalle"
```

Reemplazar `exp_refrescar` y agregar `exp_detalle` debajo:

```python
@registrar("exp_refrescar")
def exp_refrescar(tarea):
    p = tarea["payload"]
    n = lanzador.refrescar(p["cliente"], p["experimento_id"])
    # Detalle para el centro de resultados (spec 2026-10-02 §3.3): después del
    # refresco de siempre y en su propio try — el decisor depende de lo de arriba,
    # no de esto, y un fallo aquí nunca debe tumbar la tarea.
    try:
        meta_detalle.refrescar_detalle(p["cliente"], p["experimento_id"])
    except Exception:  # noqa: BLE001
        log.exception("Detalle de Meta falló en exp_refrescar (%s, exp %s)", p["cliente"], p["experimento_id"])
    return gettext("Métricas actualizadas (%(n)s anuncios).", n=n)


@registrar("exp_detalle")
def exp_detalle(tarea):
    """Solo el detalle de Meta (carga inicial al desplegar E1, o de un
    experimento que ya no corre). Lectura: no cobra."""
    p = tarea["payload"]
    r = meta_detalle.refrescar_detalle(p["cliente"], p["experimento_id"])
    if r["limite"]:
        return gettext("Meta pidió esperar; el detalle se completa en la próxima pasada.")
    return gettext("Detalle de Meta al día (%(dias)s días de anuncios, %(desgloses)s filas de desglose).",
                   dias=r["dias"], desgloses=r["desgloses"])
```

En `meta_detalle.py`:

```python
def encolar_todos():
    """Carga inicial (al desplegar E1): una tarea exp_detalle por experimento
    con campaña en Meta. Idempotente por job_id. En el VPS correr con
    TZ=America/Bogota (nota de despliegue)."""
    from tareas.experimentos import job_id_detalle
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
            db.experimento.c.legado.is_(False), db.experimento.c.meta_campaign_id.isnot(None))).all()
    for eid, cliente in filas:
        cola.encolar("exp_detalle", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_detalle(cliente, eid), duracion_estimada=60, max_intentos=2)
    return len(filas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_meta_detalle.py tests/test_lanzador.py tests/test_tareas_experimentos*.py -q`
Expected: PASS (si `tests/test_tareas_experimentos*.py` no existe, pytest solo corre los otros dos).

- [ ] **Step 5: Commit**

```bash
git add tareas/experimentos.py meta_detalle.py tests/test_meta_detalle.py tests/test_lanzador.py
git commit -m "E1: exp_refrescar pide el detalle de Meta sin arriesgar el refresco; tarea exp_detalle y carga inicial"
```

---

### Task 7: Idioma, documentación y suite completa

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po` (y el `.mo` compilado, si el repo lo versiona)
- Modify: `.claude/skills/experimentos/SKILL.md`
- Modify: `docs/pendientes.md`
- Modify: `docs/superpowers/specs/2026-10-02-experimentos-centro-de-resultados-design.md` (§3.2/§3.3 al día con el plan)

**Interfaces:**
- Consumes: todo lo anterior.

- [ ] **Step 1: Cargar la skill `idioma`** y actualizar el catálogo

Run: `venv/bin/python3 catalogo_i18n.py actualizar`
Luego traducir en `messages.po` (glosario `docs/i18n/glosario.md`), sin dejar `fuzzy`:
- «Meta pidió esperar; el detalle se completa en la próxima pasada.» → "Meta asked us to wait; the detail will finish on the next pass."
- «Detalle de Meta al día (%(dias)s días de anuncios, %(desgloses)s filas de desglose).» → "Meta detail up to date (%(dias)s ad-days, %(desgloses)s breakdown rows)."

Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 2: Skill `experimentos`** — agregar un párrafo «Detalle de Meta (E1, 2026-10-02)» al final de `.claude/skills/experimentos/SKILL.md`:

```markdown
**Detalle de Meta** (`meta_detalle.py`, spec `2026-10-02-experimentos-centro-de-resultados` §3): único escritor de
`metrica_dia` (una fila por anuncio y día: tráfico, embudo `visitas_pagina`/`carrito`/`pago_iniciado`/`compras_meta`,
retención `vistas_3s`/`p25…p100`/`thruplay`/`tiempo_medio_s`) y `metrica_desglose` (desde el inicio por
`ubicacion`/`edad_genero`/`dispositivo`/`region`), y de `experimento_pieza.extra["rankings_meta"]`. Pide a nivel
campaña con `level=ad` (1 diario + 4 desgloses + 1 rankings por experimento) con `meta_ads.auth.llamar`, sin tocar
el submódulo. Corre al final de `exp_refrescar` en su propio `try` (el decisor no depende de esto) y como tarea
`exp_detalle` (`max_intentos=2`, no cobra; `meta_detalle.encolar_todos()` hace la carga inicial). El rango se cura
solo: desde el último día guardado menos 2 (Meta corrige días recientes) o desde la creación del experimento. Un
desglose que Meta rechaza no tumba los otros; un código de límite (4/17/32/613/80004) corta la pasada. El estado
queda en `experimento.extra["detalle_meta"]` (`actualizado_en`, `errores` sin token, `limite`).
```

- [ ] **Step 3: Pendiente nuevo en `docs/pendientes.md`** (el siguiente `PND-NNN` libre; mirar el último número con `grep -o "PND-[0-9]*" docs/pendientes.md | sort -t- -k2 -n | tail -1`), en «Abiertos»:

```markdown
### PND-NNN · Un conjunto de Meta termina a los N días desde el lanzamiento, no desde la activación
- **Estado**: sin empezar · **Severidad**: lo que ve el cliente · **Afecta hoy**: clientes en producción · **Desde**: 2026-10-02
- `meta_ads/adset.crear_adset` pone `end_time = ahora + dias` al lanzar (en pausa). Si la persona activa días después,
  el experimento corre menos días de los que eligió (gasta menos, no más). Arreglo posible: al activar, mover
  `end_time` a `ahora + días restantes`. Origen: spec `2026-10-02-experimentos-centro-de-resultados` §5.3.
```

- [ ] **Step 4: Spec al día** — en §3.2 reemplazar «Por defecto pide los últimos 3 días; con `desde` (carga histórica) desde esa fecha.» por «El rango se cura solo: desde el último día guardado menos 2, o desde la creación del experimento.»; en §3.2 y §3.3 cambiar «se registra como evento `error`» por «queda en `experimento.extra["detalle_meta"]["errores"]` (sin inundar la bitácora cada 2 h)» y `exp_detalle_historico` por `exp_detalle` (job `…__exp<id>__detalle`, carga inicial con `meta_detalle.encolar_todos()`).

- [ ] **Step 5: Suite completa**

Run: `venv/bin/python3 -m pytest -q -m "not slow"` y luego `venv/bin/python3 -m pytest -q`
Expected: todo en verde (salvo fallos que ya fallaban en `main`; si hay alguno, comprobar con `git stash`-libre: correr la misma prueba en el checkout principal antes de culpar al cambio).

- [ ] **Step 6: Revisión de seguridad** — despachar el subagente `auditor-seguridad` sobre `git diff main...HEAD` (aislamiento por `ad_id`, tokens fuera de `extra` y logs, nada de SSRF: la URL la arma el código con el id de la cuenta del proyecto).

- [ ] **Step 7: Commit**

```bash
git add translations/ .claude/skills/experimentos/SKILL.md docs/pendientes.md docs/superpowers/specs/2026-10-02-experimentos-centro-de-resultados-design.md
git commit -m "E1: textos en el catálogo, skill de experimentos, pendiente del end_time y spec al día"
```

---

## Despliegue de E1 (después de que Daniel lo apruebe; skill `despliegue`)

1. Mezclar `exp-resultados` a `main` (sin `git add -A` en el checkout principal; `git submodule update` antes de commitear el merge y comparar el puntero de `meta_ads` con `origin/main`).
2. Cola vacía comprobada en su propio `ssh` (`deploy/cola_vacia.py`), respaldo de la base, `alembic upgrade head` ensayado en una copia, pull, reinicio de **worker y Flask** (encadenado con `&&`).
3. Carga inicial: `ssh … 'cd /srv/… && TZ=America/Bogota venv/bin/python3 -c "import meta_detalle; print(meta_detalle.encolar_todos())"'`.
4. Humo: en una hora, `metrica_dia` tiene filas de los experimentos con anuncios y `extra.detalle_meta.errores` está vacío (o con un desglose explicado).
