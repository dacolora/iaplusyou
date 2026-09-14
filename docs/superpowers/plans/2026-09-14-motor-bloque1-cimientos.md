# Motor de ecommerce — Bloque 1: cimientos (SQLite + worker + migración) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las generaciones y publicaciones de Creatv Flow vivan en una base SQLite y corran en un worker aparte, de modo que sobrevivan reinicios de gunicorn, y que Crear y Campañas lean de esa base sin que el cliente note ningún cambio.

**Architecture:** Una base `data/creatv.db` (SQLite WAL, SQLAlchemy Core, Alembic) con las tablas del §2 del spec. Una cola persistente `tarea` que un proceso separado (`worker.py`, servicio systemd `creatv-worker`) reclama atómicamente y ejecuta por tipo desde un registro `tareas/`. `trabajos.py` conserva su API (`iniciar/reportar/en_curso/consultar`) y gana `encolar(...)`: los trabajos viejos siguen en memoria, los migrados van a la base, y el polling `/trabajo/<job_id>/estado` no distingue. `creative_flow.py` y `ads.py` conservan su API de dicts pero guardan en la base; los JSON quedan como respaldo de solo lectura tras una migración idempotente.

**Tech Stack:** Python 3.9 (venv del repo), Flask 3.1, SQLAlchemy 2.x Core, Alembic, SQLite 3 (WAL), pytest (se introduce en este bloque), systemd en el VPS (Ubuntu, usuario `deploy`, unidad existente `iaplusyou`).

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` (§2 modelo de datos, §8 infraestructura, §9 orden de construcción — este plan es el bloque 1).

## Global Constraints

- Base única `data/creatv.db` con `PRAGMA journal_mode=WAL`; ruta configurable por `CREATV_DB_URL` (default `sqlite:///<repo>/data/creatv.db`). `data/` va en `.gitignore`.
- Worker: reclamo atómico con `UPDATE tarea SET estado='en_curso' ... WHERE id=? AND estado='pendiente'`; reintentos con espera exponencial (`2**intentos` minutos, máx. 5 intentos); una tarea `en_curso` con `iniciada_en` > 30 min vuelve a `pendiente`; un solo render/generación a la vez (worker de un hilo).
- El contrato de polling `/trabajo/<job_id>/estado` no cambia: claves `estado, progreso, elapsed, mensaje, etapa, detalle, progreso_real`, estados `en_progreso|completado|error|desconocido`.
- Las APIs públicas de `creative_flow.py` (`cargar, guardar, crear, actualizar, eliminar`) y `ads.py` (`cargar, crear, actualizar, eliminar`) conservan firmas y devuelven/aceptan los mismos dicts que hoy; `dashboard.py` no cambia por ese motivo.
- Migración idempotente: correrla dos veces no duplica filas (clave `legado_id`).
- Copy de la UI en español. Tokens nunca en logs ni en `evento`/`tarea.error` (truncar mensajes de error de Meta a 500 caracteres y pasar por `_sin_token()` que reemplaza `access_token=...` por `access_token=***`).
- No tocar el pipeline viejo (Higgsfield: imagen/video/publicar brief, marca, conceptos, animaciones, `estado_videos.json`, `prompts_pendientes.json`): esos siguen en `trabajos` en memoria.
- Verificación mínima antes de cada commit: `venv/bin/python3 -m py_compile <archivos>` y `venv/bin/python3 -m pytest -q`.
- Deploy: `git pull --ff-only && venv/bin/pip install -r requirements.txt && venv/bin/alembic upgrade head && systemctl restart iaplusyou creatv-worker` (ver memoria `produccion-vps-creatvmachine`).

---

## Estructura de archivos

- Create: `db.py` — engine/conexión SQLite, `metadata`, definición de tablas (Core), helper `conectar()`.
- Create: `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_tablas_motor.py` — migración inicial.
- Create: `cola.py` — cola persistente sobre la tabla `tarea`: encolar, reclamar, reportar, terminar, fallar, recuperar_colgadas, consultar_por_job.
- Create: `tareas/__init__.py` — registro `REGISTRO = {tipo: fn}` y `registrar(tipo)`.
- Create: `tareas/flowplus.py` — `generar_clon_video`, `generar_clon_imagen` (cuerpos movidos de `_lanzar_video_cf`).
- Create: `tareas/meta.py` — `publicar_ad`, `refrescar_metricas` (cuerpos movidos de `publicar_ad` y `actualizar_resultados_ad`).
- Create: `tareas/swap.py` — `generar_swap` (cuerpo movido de `_lanzar_swap`).
- Create: `worker.py` — bucle del worker + planificador de periódicas + `ciclo()` testeable.
- Create: `deploy/creatv-worker.service` — unidad systemd.
- Create: `migrar_json_a_db.py` — importa `ads.json` y `creative_flow_pendientes.json` de todos los clientes.
- Create: `tests/conftest.py`, `tests/test_db.py`, `tests/test_cola.py`, `tests/test_worker.py`, `tests/test_trabajos_adaptador.py`, `tests/test_migracion.py`, `tests/test_creative_flow_db.py`, `tests/test_ads_db.py`, `tests/test_tareas_flowplus.py`, `tests/test_tareas_meta.py`.
- Modify: `trabajos.py` — extraer `_progreso_de()`, añadir `encolar()`, fallback a `cola` en `reportar/en_curso/consultar`.
- Modify: `creative_flow.py`, `ads.py` — misma API, almacenamiento en tablas `concepto`/`pieza` y `experimento`/`experimento_pieza`/`metrica_snapshot`.
- Modify: `dashboard.py` — `_lanzar_video_cf`, `_lanzar_swap`, `publicar_ad`, `actualizar_resultados_ad` pasan a encolar.
- Modify: `requirements.txt`, `.gitignore`, `CLAUDE.md`, `SETUP.md`.

---

### Task 1: Base de datos, tablas y Alembic

**Files:**
- Create: `db.py`
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_tablas_motor.py`
- Create: `tests/conftest.py`, `tests/test_db.py`
- Modify: `requirements.txt`, `.gitignore`

**Interfaces:**
- Produces: `db.engine()` → `sqlalchemy.Engine` (singleton por proceso, WAL, `busy_timeout=5000`, `check_same_thread=False`); `db.conectar()` → context manager que devuelve una `Connection` con transacción (`with db.conectar() as con:`); `db.metadata` y las tablas como atributos de módulo: `db.producto, db.concepto, db.pieza, db.experimento, db.experimento_pieza, db.metrica_snapshot, db.evento, db.propuesta, db.tarea, db.tienda, db.pedido, db.kv`; `db.ahora()` → `str` ISO sin microsegundos; `db.crear_todo()` (solo tests) crea todas las tablas sin Alembic.
- Consumed by: todas las tareas siguientes.

- [ ] **Step 1: Dependencias y gitignore**

Añadir al final de `requirements.txt`:

```
SQLAlchemy>=2.0,<3
alembic>=1.13,<2
pytest>=8,<9
```

Añadir a `.gitignore`:

```
data/
```

Run: `venv/bin/pip install -r requirements.txt`
Expected: instala sin error; `venv/bin/python3 -c "import sqlalchemy, alembic, pytest; print(sqlalchemy.__version__)"` imprime `2.x`.

- [ ] **Step 2: Test de la base (falla)**

`tests/conftest.py`:

```python
import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


@pytest.fixture()
def base_temporal(monkeypatch):
    """Base SQLite nueva por test, en archivo (WAL necesita archivo, no :memory:)."""
    carpeta = tempfile.mkdtemp(prefix="creatv_test_")
    ruta = os.path.join(carpeta, "creatv.db")
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{ruta}")
    import db
    db._reset_para_tests()
    db.crear_todo()
    yield db
    db._reset_para_tests()
```

`tests/test_db.py`:

```python
import sqlalchemy as sa


def test_crea_todas_las_tablas(base_temporal):
    db = base_temporal
    nombres = set(sa.inspect(db.engine()).get_table_names())
    esperadas = {"producto", "concepto", "pieza", "experimento", "experimento_pieza",
                 "metrica_snapshot", "evento", "propuesta", "tarea", "tienda", "pedido", "kv"}
    assert esperadas <= nombres


def test_wal_activado(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        modo = con.execute(sa.text("PRAGMA journal_mode")).scalar()
    assert modo == "wal"


def test_conectar_hace_commit(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        con.execute(db.kv.insert().values(clave="a", valor="1", actualizado_en=db.ahora()))
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "a")).scalar()
    assert valor == "1"
```

- [ ] **Step 3: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_db.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'db'`.

- [ ] **Step 4: Implementar `db.py`**

```python
"""
Base de datos del motor (SQLite + SQLAlchemy Core). Una sola base por servidor
en data/creatv.db (WAL), compartida por gunicorn y el worker. Las tablas siguen
el §2 de docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md.

Los JSON por cliente (clientes/<c>/*.json) NO desaparecen: los módulos que ya
existían (creative_flow.py, ads.py) cambian su almacenamiento a estas tablas
manteniendo la misma API de dicts.
"""
import contextlib
import os
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Float, Integer, JSON, MetaData, String, Table, Text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINE = None


def url():
    return os.environ.get("CREATV_DB_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'data', 'creatv.db')}"


def engine():
    """Engine singleton del proceso. SQLite con WAL para que gunicorn (hilos) y
    el worker (otro proceso) lean y escriban a la vez sin 'database is locked'."""
    global _ENGINE
    if _ENGINE is None:
        u = url()
        if u.startswith("sqlite:///") and not u.endswith(":memory:"):
            os.makedirs(os.path.dirname(u.replace("sqlite:///", "")) or ".", exist_ok=True)
        _ENGINE = sa.create_engine(u, connect_args={"check_same_thread": False, "timeout": 5}, future=True)

        @sa.event.listens_for(_ENGINE, "connect")
        def _pragmas(dbapi_con, _):
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return _ENGINE


def _reset_para_tests():
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None


@contextlib.contextmanager
def conectar():
    """`with db.conectar() as con:` — una transacción; commit al salir sin error."""
    with engine().begin() as con:
        yield con


def ahora():
    return datetime.now().isoformat(timespec="seconds")


metadata = MetaData()


def _comunes():
    return [
        Column("cliente", String(80), nullable=False, index=True),
        Column("creado_en", String(19), nullable=False),
        Column("actualizado_en", String(19), nullable=False),
    ]


producto = Table("producto", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("fuente", String(20), nullable=False),          # shopify|woo|meli|csv|url|manual
    Column("fuente_id", String(120)),
    Column("nombre", String(200), nullable=False),
    Column("descripcion", Text),
    Column("precio", Float),
    Column("moneda", String(3)),
    Column("url_compra", Text),
    Column("fotos", JSON, default=list),
    Column("categoria", String(120)),
    Column("activo_catalogo_id", String(120)),
    Column("prioridad", Integer, default=0),
    Column("en_prueba", Boolean, default=False),
    Column("archivado", Boolean, default=False),
    sa.UniqueConstraint("cliente", "fuente", "fuente_id", name="uq_producto_fuente"),
)

concepto = Table("concepto", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),
    Column("origen", String(20), nullable=False),          # referente_link|ganador_derivado|rescate|manual
    Column("referencia_url", Text),
    Column("referencia_frames", JSON, default=list),
    Column("referencia_transcripcion", Text),
    Column("enfoque", String(20)),                          # producto|persona|unboxing
    Column("guion_base", JSON),
    Column("idioma_base", String(5), default="es"),
    Column("padre_concepto_id", Integer, sa.ForeignKey("concepto.id")),
    Column("motivo_archivo", Text),
    Column("archivado", Boolean, default=False),
    Column("legado_id", String(60), index=True),           # cf_... de creative_flow_pendientes.json
    Column("extra", JSON, default=dict),                    # campos legado que no tienen columna
)

pieza = Table("pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("concepto_id", Integer, sa.ForeignKey("concepto.id"), nullable=False, index=True),
    Column("tipo", String(12), nullable=False),             # clon_limpio|final
    Column("idioma", String(5)),
    Column("pais", String(2)),
    Column("modelo", String(40)),
    Column("url_video", Text),
    Column("url_miniatura", Text),
    Column("url_local", Text),
    Column("duracion_s", Float),
    Column("aspect_ratio", String(6)),
    Column("capas", JSON, default=dict),
    Column("costo_usd", Float),
    Column("estado", String(16), nullable=False, default="pendiente"),  # pendiente|generando|listo|error|degradada
    Column("error", Text),
    Column("padre_pieza_id", Integer, sa.ForeignKey("pieza.id")),
    Column("guion", JSON),
    Column("legado_id", String(60), index=True),
    Column("extra", JSON, default=dict),
)

experimento = Table("experimento", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),
    Column("nombre", String(200), nullable=False),
    Column("modo", String(8), nullable=False, default="manual"),  # manual|semi|auto
    Column("reglas", JSON, default=dict),
    Column("paises", JSON, default=list),
    Column("moneda", String(3)),
    Column("tope_total", Float),
    Column("dias", Integer),
    Column("objetivo_meta", String(30)),
    Column("atribucion", String(10), default="ninguna"),   # pixel|tienda|ninguna
    Column("estado", String(22), nullable=False, default="armando"),
    Column("meta_campaign_id", String(40)),
    Column("gasto_acumulado", Float, default=0.0),
    Column("legado", Boolean, default=False),               # True = importado de ads.json
)

experimento_pieza = Table("experimento_pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), nullable=False, index=True),
    Column("pieza_id", Integer, sa.ForeignKey("pieza.id")),
    Column("pais", String(2)),
    Column("meta_adset_id", String(40)),
    Column("meta_ad_id", String(40)),
    Column("meta_creative_id", String(40)),
    Column("estado_meta", String(30)),
    Column("veredicto", String(12), default="pendiente"),
    Column("veredicto_motivo", Text),
    Column("veredicto_en", String(19)),
    Column("escalon_rescate", Integer, default=0),
    Column("presupuesto_dia_actual", Float),
    Column("estado", String(16), nullable=False, default="en_cola"),  # en_cola|publicando|pausado|activo|error
    Column("error", Text),
    Column("legado_id", String(60), index=True),           # ad_... de ads.json
    Column("extra", JSON, default=dict),                    # nombre, fuente, contenido_url, objetivo, etc.
)

metrica_snapshot = Table("metrica_snapshot", metadata,
    Column("id", Integer, primary_key=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False, index=True),
    Column("tomado_en", String(19), nullable=False),
    Column("impresiones", Integer, default=0), Column("alcance", Integer, default=0),
    Column("frecuencia", Float, default=0.0), Column("clics", Integer, default=0),
    Column("clics_enlace", Integer, default=0), Column("ctr", Float, default=0.0),
    Column("cpc", Float, default=0.0), Column("cpm", Float, default=0.0),
    Column("thruplay", Integer, default=0), Column("thruplay_rate", Float, default=0.0),
    Column("gasto", Float, default=0.0), Column("compras", Integer, default=0),
    Column("ingresos", Float, default=0.0), Column("roas", Float, default=0.0),
    Column("cpa", Float, default=0.0),
    Column("fuente_ventas", String(8), default="ninguna"),
    Column("extra", JSON, default=dict),                    # resultado_nombre, estado_meta_texto, motivo_rechazo
)

evento = Table("evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), index=True),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id")),
    Column("tipo", String(30), nullable=False),
    Column("mensaje", Text, nullable=False),
    Column("datos", JSON, default=dict),
    Column("creado_en", String(19), nullable=False),
)

propuesta = Table("propuesta", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("experimento_id", Integer, sa.ForeignKey("experimento.id"), nullable=False, index=True),
    Column("accion", String(12), nullable=False),           # publicar|activar|escalar|derivar|rescatar|pausar
    Column("payload", JSON, default=dict),
    Column("estado", String(10), nullable=False, default="pendiente"),
    Column("resuelta_en", String(19)),
)

tarea = Table("tarea", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),
    Column("job_id", String(200), index=True),              # el id que ya usa el polling del navegador
    Column("tipo", String(40), nullable=False),
    Column("payload", JSON, default=dict),
    Column("estado", String(10), nullable=False, default="pendiente", index=True),
    Column("intentos", Integer, default=0),
    Column("max_intentos", Integer, default=5),
    Column("ejecutar_desde", String(19), nullable=False),
    Column("creada_en", String(19), nullable=False),
    Column("iniciada_en", String(19)),
    Column("terminada_en", String(19)),
    Column("mensaje", Text),
    Column("error", Text),
    # progreso para la barra del navegador (mismo modelo que trabajos.py)
    Column("duracion_estimada", Float, default=60.0),
    Column("etapas", JSON, default=list),                   # [[nombre, peso], ...]
    Column("etapa_actual", String(120)),
    Column("indice_etapa", Integer, default=0),
    Column("inicio_etapa", Float),                          # time.time()
    Column("inicio", Float),                                # time.time()
    Column("progreso_etapa", Float),
    Column("progreso_visto", Float, default=0.0),
    Column("detalle", Text),
)

tienda = Table("tienda", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("tipo", String(10), nullable=False),
    Column("credenciales", Text),                           # cifrado (bloque 5)
    Column("ultima_sync_productos", String(19)),
    Column("ultima_sync_pedidos", String(19)),
    Column("estado", String(20), default="conectada"),
)

pedido = Table("pedido", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("tienda_id", Integer, sa.ForeignKey("tienda.id")),
    Column("fuente_id", String(120), nullable=False),
    Column("fecha", String(19), nullable=False),
    Column("total", Float), Column("moneda", String(3)),
    Column("items", JSON, default=list),
    Column("utm_content", String(120)),
    Column("experimento_pieza_id", Integer, sa.ForeignKey("experimento_pieza.id")),
    sa.UniqueConstraint("cliente", "fuente_id", name="uq_pedido_fuente"),
)

kv = Table("kv", metadata,
    Column("clave", String(120), primary_key=True),
    Column("valor", Text),
    Column("actualizado_en", String(19), nullable=False),
)


def crear_todo():
    """Solo para tests y scripts locales. En producción manda Alembic."""
    metadata.create_all(engine())
```

- [ ] **Step 5: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_db.py -q`
Expected: `3 passed`.

- [ ] **Step 6: Alembic**

Run: `venv/bin/alembic init migrations`

Editar `alembic.ini`: dejar `sqlalchemy.url =` vacío (se inyecta desde `db.url()`).

Reemplazar `migrations/env.py` por:

```python
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", db.url())
target_metadata = db.metadata


def run_migrations_offline():
    context.configure(url=db.url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Run: `CREATV_DB_URL=sqlite:////tmp/creatv_alembic.db venv/bin/alembic revision --autogenerate -m "tablas motor" --rev-id 0001`
Expected: crea `migrations/versions/0001_tablas_motor.py` con `op.create_table` para las 12 tablas. Abrirlo y confirmar que aparecen las 12 (`grep -c create_table` → 12).

Run: `CREATV_DB_URL=sqlite:////tmp/creatv_alembic.db venv/bin/alembic upgrade head && CREATV_DB_URL=sqlite:////tmp/creatv_alembic.db venv/bin/python3 -c "import db, sqlalchemy as sa; print(sorted(sa.inspect(db.engine()).get_table_names()))"`
Expected: lista con las 12 tablas + `alembic_version`.

- [ ] **Step 7: Commit**

```bash
git add db.py alembic.ini migrations requirements.txt .gitignore tests/conftest.py tests/test_db.py
git commit -m "Motor: base SQLite (WAL) con las tablas del §2 y Alembic; pytest entra al repo"
```

---

### Task 2: Cola persistente (`cola.py`)

**Files:**
- Create: `cola.py`
- Test: `tests/test_cola.py`

**Interfaces:**
- Consumes: `db.tarea`, `db.conectar()`, `db.ahora()`.
- Produces:
  - `cola.encolar(tipo, payload, *, cliente=None, job_id=None, duracion_estimada=60, etapas=None, ejecutar_desde=None, max_intentos=5) -> int | None` — devuelve el id; **None** si ya existe una tarea `pendiente|en_curso` con el mismo `job_id` (anti doble clic, mismo contrato que `trabajos.iniciar`).
  - `cola.reclamar() -> dict | None` — la siguiente `pendiente` con `ejecutar_desde <= ahora`, pasada a `en_curso` atómicamente; dict con todas las columnas.
  - `cola.terminar(id, mensaje)`; `cola.fallar(id, error)` → si `intentos < max_intentos` vuelve a `pendiente` con `ejecutar_desde = ahora + 2**intentos min`, si no queda `error`.
  - `cola.recuperar_colgadas(minutos=30) -> int` — `en_curso` más viejas que N min → `pendiente`.
  - `cola.reportar(job_id, etapa=None, progreso=None, detalle=None)` — actualiza las columnas de progreso de la tarea `en_curso` con ese `job_id` (misma semántica que `trabajos.reportar`).
  - `cola.consultar_por_job(job_id) -> dict | None` — la fila más reciente con ese `job_id` (para el polling).
  - `cola.sin_token(texto) -> str`.

- [ ] **Step 1: Tests (fallan)**

`tests/test_cola.py`:

```python
import time
from datetime import datetime, timedelta

import sqlalchemy as sa


def test_encolar_y_reclamar(base_temporal):
    import cola
    tid = cola.encolar("prueba", {"x": 1}, cliente="c1", job_id="c1__j1")
    assert isinstance(tid, int)
    t = cola.reclamar()
    assert t["id"] == tid and t["estado"] == "en_curso" and t["payload"] == {"x": 1}
    assert t["intentos"] == 1 and t["iniciada_en"] and t["inicio"]
    assert cola.reclamar() is None


def test_encolar_dedupe_por_job_id(base_temporal):
    import cola
    assert cola.encolar("prueba", {}, job_id="j") is not None
    assert cola.encolar("prueba", {}, job_id="j") is None
    t = cola.reclamar()
    cola.terminar(t["id"], "ok")
    assert cola.encolar("prueba", {}, job_id="j") is not None  # terminada -> se puede repetir


def test_fallar_reintenta_con_espera_exponencial(base_temporal):
    import cola
    tid = cola.encolar("prueba", {}, max_intentos=3)
    t = cola.reclamar(); cola.fallar(t["id"], "boom 1")
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "pendiente" and fila["error"] == "boom 1"
    espera = datetime.fromisoformat(fila["ejecutar_desde"]) - datetime.now()
    assert timedelta(minutes=1, seconds=-5) < espera <= timedelta(minutes=2)
    assert cola.reclamar() is None  # todavía no toca


def test_fallar_agota_intentos(base_temporal):
    import cola
    tid = cola.encolar("prueba", {}, max_intentos=1)
    t = cola.reclamar(); cola.fallar(t["id"], "boom")
    assert cola.consultar_por_id(tid)["estado"] == "error"


def test_recuperar_colgadas(base_temporal):
    import cola, db
    tid = cola.encolar("prueba", {})
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    assert cola.recuperar_colgadas(30) == 1
    assert cola.consultar_por_id(tid)["estado"] == "pendiente"


def test_reportar_y_consultar_por_job(base_temporal):
    import cola
    cola.encolar("prueba", {}, job_id="j2", etapas=[["Subir", 10], ["Modelo", 90]], duracion_estimada=100)
    cola.reclamar()
    cola.reportar("j2", etapa="Modelo", detalle="en cola, puesto 2")
    fila = cola.consultar_por_job("j2")
    assert fila["etapa_actual"] == "Modelo" and fila["indice_etapa"] == 1 and fila["detalle"] == "en cola, puesto 2"
    cola.reportar("j2", progreso=50)
    assert cola.consultar_por_job("j2")["progreso_etapa"] == 50.0


def test_sin_token():
    import cola
    assert cola.sin_token("x?access_token=EAAB123&y=1") == "x?access_token=***&y=1"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_cola.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'cola'`.

- [ ] **Step 3: Implementar `cola.py`**

```python
"""
Cola persistente sobre la tabla `tarea` (db.py). La consumen el worker
(worker.py) y, del lado de gunicorn, trabajos.py para encolar y para leer el
progreso que el navegador consulta. SQLite no tiene SELECT ... FOR UPDATE: el
reclamo es un UPDATE condicionado (WHERE id=? AND estado='pendiente') que solo
gana un proceso.
"""
import re
import time
from datetime import datetime, timedelta

import sqlalchemy as sa

import db

_RE_TOKEN = re.compile(r"(access_token=)[^&\s\"']+")


def sin_token(texto):
    """Nunca guardar tokens: Meta los mete en paging.next y en mensajes."""
    return _RE_TOKEN.sub(r"\1***", str(texto or ""))[:500]


def _fila(r):
    return dict(r._mapping) if r is not None else None


def encolar(tipo, payload, *, cliente=None, job_id=None, duracion_estimada=60, etapas=None,
            ejecutar_desde=None, max_intentos=5):
    ahora = db.ahora()
    with db.conectar() as con:
        if job_id:
            viva = con.execute(sa.select(db.tarea.c.id).where(
                db.tarea.c.job_id == job_id, db.tarea.c.estado.in_(("pendiente", "en_curso")))).first()
            if viva:
                return None
        r = con.execute(db.tarea.insert().values(
            cliente=cliente, job_id=job_id, tipo=tipo, payload=payload or {}, estado="pendiente",
            intentos=0, max_intentos=max_intentos, ejecutar_desde=ejecutar_desde or ahora, creada_en=ahora,
            duracion_estimada=float(duracion_estimada), etapas=[list(e) for e in (etapas or [])],
        ))
        return int(r.inserted_primary_key[0])


def reclamar():
    ahora = db.ahora()
    with db.conectar() as con:
        cand = con.execute(sa.select(db.tarea.c.id).where(
            db.tarea.c.estado == "pendiente", db.tarea.c.ejecutar_desde <= ahora
        ).order_by(db.tarea.c.ejecutar_desde, db.tarea.c.id).limit(1)).first()
        if not cand:
            return None
        t0 = time.time()
        r = con.execute(db.tarea.update().where(
            db.tarea.c.id == cand.id, db.tarea.c.estado == "pendiente"
        ).values(estado="en_curso", iniciada_en=ahora, inicio=t0, inicio_etapa=t0,
                 intentos=db.tarea.c.intentos + 1, error=None, indice_etapa=0,
                 progreso_etapa=None, progreso_visto=0.0, detalle=None, etapa_actual=None))
        if r.rowcount != 1:
            return None  # otro proceso ganó; el bucle del worker vuelve a intentar
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.id == cand.id)).first())


def terminar(tarea_id, mensaje=None):
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
            estado="hecha", terminada_en=db.ahora(), mensaje=mensaje or "Listo."))


def fallar(tarea_id, error):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea.c.intentos, db.tarea.c.max_intentos).where(db.tarea.c.id == tarea_id)).first()
        if not fila:
            return
        if fila.intentos < fila.max_intentos:
            espera = timedelta(minutes=2 ** fila.intentos)
            con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
                estado="pendiente", error=sin_token(error),
                ejecutar_desde=(datetime.now() + espera).isoformat(timespec="seconds")))
        else:
            con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id).values(
                estado="error", error=sin_token(error), terminada_en=db.ahora(), mensaje=sin_token(error)))


def recuperar_colgadas(minutos=30):
    limite = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
    with db.conectar() as con:
        r = con.execute(db.tarea.update().where(
            db.tarea.c.estado == "en_curso", db.tarea.c.iniciada_en < limite
        ).values(estado="pendiente", ejecutar_desde=db.ahora(), error="recuperada: llevaba más de %d min en curso" % minutos))
        return r.rowcount


def reportar(job_id, etapa=None, progreso=None, detalle=None):
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea).where(
            db.tarea.c.job_id == job_id, db.tarea.c.estado == "en_curso").order_by(db.tarea.c.id.desc()).limit(1)).first()
        if not fila:
            return
        valores = {}
        if etapa is not None:
            valores["etapa_actual"] = etapa
            nombres = [e[0] for e in (fila.etapas or [])]
            if etapa in nombres and nombres.index(etapa) != (fila.indice_etapa or 0):
                valores.update(indice_etapa=nombres.index(etapa), inicio_etapa=time.time(),
                               progreso_etapa=None, detalle=None)
        if progreso is not None:
            valores["progreso_etapa"] = max(0.0, min(100.0, float(progreso)))
        if detalle is not None:
            valores["detalle"] = detalle
        if valores:
            con.execute(db.tarea.update().where(db.tarea.c.id == fila.id).values(**valores))


def consultar_por_job(job_id):
    with db.conectar() as con:
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.job_id == job_id)
                                 .order_by(db.tarea.c.id.desc()).limit(1)).first())


def consultar_por_id(tarea_id):
    with db.conectar() as con:
        return _fila(con.execute(sa.select(db.tarea).where(db.tarea.c.id == tarea_id)).first())


def actualizar_progreso_visto(tarea_id, valor):
    """La barra nunca retrocede: quien calcula el % (trabajos.consultar) guarda el máximo visto."""
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tarea_id, db.tarea.c.progreso_visto < valor)
                    .values(progreso_visto=valor))
```

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_cola.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add cola.py tests/test_cola.py
git commit -m "Motor: cola persistente sobre la tabla tarea (reclamo atómico, reintentos exponenciales, colgadas, progreso)"
```

---

### Task 3: Registro de tareas y worker

**Files:**
- Create: `tareas/__init__.py`, `worker.py`, `deploy/creatv-worker.service`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `cola.*`.
- Produces:
  - `tareas.REGISTRO: dict[str, callable]`; decorador `tareas.registrar(tipo)`; cada función de tarea tiene firma `fn(tarea: dict) -> str | None` (el string es el mensaje final para el polling) y puede lanzar excepción (→ `cola.fallar`).
  - `worker.ciclo() -> bool` — un paso: recupera colgadas, encola periódicas vencidas, reclama y ejecuta **una** tarea; devuelve True si ejecutó algo.
  - `worker.PERIODICAS = [(tipo, cada_segundos)]` y `worker.encolar_periodicas()` usando la tabla `kv` (`ultimo_<tipo>`).
  - `worker.main()` — bucle infinito con `time.sleep(2)` cuando no hay nada.

- [ ] **Step 1: Tests (fallan)**

`tests/test_worker.py`:

```python
def test_ciclo_ejecuta_y_termina(base_temporal):
    import cola, tareas, worker
    hecho = {}

    @tareas.registrar("prueba_ok")
    def _ok(t):
        hecho["payload"] = t["payload"]
        return "listo!"

    tid = cola.encolar("prueba_ok", {"a": 1})
    assert worker.ciclo() is True
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "hecha" and fila["mensaje"] == "listo!" and hecho["payload"] == {"a": 1}
    assert worker.ciclo() is False


def test_ciclo_falla_y_reprograma(base_temporal):
    import cola, tareas, worker

    @tareas.registrar("prueba_falla")
    def _f(t):
        raise RuntimeError("se rompió access_token=SECRETO fin")

    tid = cola.encolar("prueba_falla", {}, max_intentos=2)
    worker.ciclo()
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "pendiente" and "SECRETO" not in fila["error"] and "***" in fila["error"]


def test_tipo_desconocido_queda_en_error(base_temporal):
    import cola, worker
    tid = cola.encolar("no_existe", {}, max_intentos=1)
    worker.ciclo()
    assert cola.consultar_por_id(tid)["estado"] == "error"


def test_periodicas_se_encolan_una_vez_por_ventana(base_temporal, monkeypatch):
    import cola, tareas, worker
    monkeypatch.setattr(worker, "PERIODICAS", [("tick", 3600)])

    @tareas.registrar("tick")
    def _t(t):
        return "tick"

    worker.encolar_periodicas()
    worker.encolar_periodicas()
    assert cola.reclamar() is not None
    assert cola.reclamar() is None  # solo una en la ventana
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_worker.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'tareas'`.

- [ ] **Step 3: Implementar `tareas/__init__.py`**

```python
"""
Registro de tipos de tarea que ejecuta el worker. Cada módulo de tareas/ se
importa acá para que sus @registrar corran al arrancar el worker.
"""
REGISTRO = {}


def registrar(tipo):
    def _dec(fn):
        REGISTRO[tipo] = fn
        return fn
    return _dec


def cargar_todas():
    """Importa los módulos con tareas reales. Se llama desde worker.main(), no
    al importar el paquete, para que los tests puedan registrar tareas falsas
    sin arrastrar proveedores externos."""
    from tareas import flowplus, meta, swap  # noqa: F401
```

- [ ] **Step 4: Implementar `worker.py`**

```python
"""
Worker de Creatv Machine: proceso aparte de gunicorn (servicio systemd
creatv-worker) que ejecuta las tareas de la cola persistente (cola.py) una a la
vez. Si el proceso muere a mitad de una tarea, esa tarea vuelve a `pendiente`
a los 30 min (recuperar_colgadas) y se reintenta — a diferencia de los hilos
en memoria de trabajos.py, nada se pierde con un reinicio.

Uso: `python worker.py` (carga .env como dashboard.py).
"""
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

import sqlalchemy as sa
from dotenv import load_dotenv

import cola
import db
import tareas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("creatv.worker")

# (tipo, cada_segundos). Los tipos se registran en tareas/ (bloques siguientes
# agregan refrescar_metricas_todos, sincronizar_tiendas, decidir_experimentos).
PERIODICAS = []


def encolar_periodicas():
    """Encola cada periódica cuando pasó su ventana desde la última vez (kv)."""
    ahora = datetime.now()
    with db.conectar() as con:
        for tipo, cada in PERIODICAS:
            clave = f"ultimo_{tipo}"
            ultimo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
            if ultimo and datetime.fromisoformat(ultimo) + timedelta(seconds=cada) > ahora:
                continue
            con.execute(sa.dialects.sqlite.insert(db.kv).values(
                clave=clave, valor=ahora.isoformat(timespec="seconds"), actualizado_en=db.ahora()
            ).on_conflict_do_update(index_elements=["clave"], set_={"valor": ahora.isoformat(timespec="seconds"), "actualizado_en": db.ahora()}))
    for tipo, _ in PERIODICAS:
        if _recien_marcada(tipo, ahora):
            cola.encolar(tipo, {}, job_id=f"periodica__{tipo}")


def _recien_marcada(tipo, ahora):
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == f"ultimo_{tipo}")).scalar()
    return valor == ahora.isoformat(timespec="seconds")


def ejecutar(tarea):
    fn = tareas.REGISTRO.get(tarea["tipo"])
    if fn is None:
        raise RuntimeError(f"tipo de tarea desconocido: {tarea['tipo']}")
    return fn(tarea)


def ciclo():
    cola.recuperar_colgadas(30)
    encolar_periodicas()
    tarea = cola.reclamar()
    if tarea is None:
        return False
    log.info("tarea %s %s (intento %s) job=%s", tarea["id"], tarea["tipo"], tarea["intentos"], tarea["job_id"])
    try:
        mensaje = ejecutar(tarea)
        cola.terminar(tarea["id"], mensaje)
        log.info("tarea %s hecha", tarea["id"])
    except Exception as e:  # noqa: BLE001 — el worker nunca muere por una tarea
        log.error("tarea %s falló: %s\n%s", tarea["id"], cola.sin_token(e), cola.sin_token(traceback.format_exc()))
        cola.fallar(tarea["id"], f"{type(e).__name__}: {e}")
    return True


def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    tareas.cargar_todas()
    log.info("worker arriba · base %s · tipos %s", db.url(), sorted(tareas.REGISTRO))
    while True:
        try:
            if not ciclo():
                time.sleep(2)
        except Exception as e:  # noqa: BLE001
            log.error("ciclo falló: %s", cola.sin_token(e))
            time.sleep(5)


if __name__ == "__main__":
    main()
```

Nota para el implementador: `encolar_periodicas` marca primero en `kv` y luego encola solo las que acaba de marcar en este mismo segundo; con `job_id=periodica__<tipo>` la cola además deduplica si la anterior sigue viva.

- [ ] **Step 5: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_worker.py -q`
Expected: `4 passed`. (`tareas.cargar_todas()` importa módulos que todavía no existen; los tests no lo llaman. Crear `tareas/flowplus.py`, `tareas/meta.py`, `tareas/swap.py` vacíos con solo un docstring para que `python -c "import tareas; tareas.cargar_todas()"` no reviente hasta las tareas 7-9.)

- [ ] **Step 6: Unidad systemd**

`deploy/creatv-worker.service`:

```ini
[Unit]
Description=Creatv Machine worker (cola persistente)
After=network.target

[Service]
User=deploy
WorkingDirectory=/home/deploy/iaplusyou
EnvironmentFile=/home/deploy/iaplusyou/.env
ExecStart=/home/deploy/iaplusyou/venv/bin/python3 worker.py
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=600

[Install]
WantedBy=multi-user.target
```

`TimeoutStopSec=600`: un render/generación en curso puede tardar minutos; si systemd lo mata antes, la tarea vuelve sola a `pendiente` por `recuperar_colgadas`.

- [ ] **Step 7: Commit**

```bash
git add tareas/__init__.py tareas/flowplus.py tareas/meta.py tareas/swap.py worker.py deploy/creatv-worker.service tests/test_worker.py
git commit -m "Motor: worker con registro de tareas, periódicas por kv y unidad systemd creatv-worker"
```

---

### Task 4: `trabajos.py` como adaptador (memoria + cola)

**Files:**
- Modify: `trabajos.py`
- Test: `tests/test_trabajos_adaptador.py`

**Interfaces:**
- Consumes: `cola.encolar/reportar/consultar_por_job/actualizar_progreso_visto`.
- Produces:
  - `trabajos.encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None) -> bool` — True si encoló, False si ya había una viva (mismo contrato que `iniciar`).
  - `trabajos.reportar(...)`: si `job_id` no está en memoria → `cola.reportar`.
  - `trabajos.en_curso(job_id)`: memoria **o** tarea `pendiente|en_curso` en la base.
  - `trabajos.consultar(job_id)`: memoria; si no, construye el mismo dict desde la fila de `tarea` (`pendiente` se muestra como `en_progreso` con etapa "En cola" y `hecha` → `completado`, `error` → `error`).
  - `trabajos._progreso_de(t, ahora) -> float` — la curva asintótica extraída de `consultar`, reutilizable para filas de la base.

- [ ] **Step 1: Tests (fallan)**

`tests/test_trabajos_adaptador.py`:

```python
import time


def test_encolar_y_consultar_pendiente(base_temporal):
    import trabajos
    assert trabajos.encolar("c__j", "prueba", {"k": 1}, duracion_estimada=100, etapas=[("Subir", 10), ("Modelo", 90)]) is True
    assert trabajos.encolar("c__j", "prueba", {}) is False
    assert trabajos.en_curso("c__j") is True
    info = trabajos.consultar("c__j")
    assert info["estado"] == "en_progreso" and info["etapa"] == "En cola" and info["progreso"] == 0


def test_consultar_en_curso_usa_la_curva_y_no_retrocede(base_temporal):
    import cola, trabajos
    trabajos.encolar("c__j2", "prueba", {}, duracion_estimada=10, etapas=[("Subir", 10), ("Modelo", 90)])
    cola.reclamar()
    trabajos.reportar("c__j2", etapa="Modelo", detalle="poll 3")
    a = trabajos.consultar("c__j2")
    assert a["estado"] == "en_progreso" and a["etapa"] == "Modelo" and a["detalle"] == "poll 3"
    assert a["progreso"] >= 10  # piso de la etapa Modelo
    time.sleep(0.2)
    b = trabajos.consultar("c__j2")
    assert b["progreso"] >= a["progreso"]
    trabajos.reportar("c__j2", progreso=50)
    assert trabajos.consultar("c__j2")["progreso_real"] is True


def test_consultar_terminada(base_temporal):
    import cola, trabajos
    trabajos.encolar("c__j3", "prueba", {})
    t = cola.reclamar(); cola.terminar(t["id"], "Video listo.")
    info = trabajos.consultar("c__j3")
    assert info["estado"] == "completado" and info["progreso"] == 100 and info["mensaje"] == "Video listo."
    assert trabajos.en_curso("c__j3") is False


def test_memoria_sigue_funcionando(base_temporal):
    import trabajos
    assert trabajos.iniciar("mem__1", lambda: "ok", duracion_estimada=1) is True
    time.sleep(0.1)
    assert trabajos.consultar("mem__1")["estado"] == "completado"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_trabajos_adaptador.py -q`
Expected: FAIL con `AttributeError: module 'trabajos' has no attribute 'encolar'`.

- [ ] **Step 3: Modificar `trabajos.py`**

Añadir tras los imports:

```python
import cola  # cola persistente (db.py); los trabajos migrados al worker viven ahí
```

Extraer de `consultar()` el cálculo de progreso a una función de módulo (reemplazar el bloque `if t["estado"] == "en_progreso": ... progreso = round(min(99.0, p), 1)` por `progreso = _progreso_de(t, ahora)`):

```python
def _progreso_de(t, ahora):
    """% de la barra para un trabajo en progreso: progreso real de la etapa si
    lo hay, si no la curva asintótica contra el reloj. Nunca retrocede
    (progreso_visto). Sirve igual para un dict en memoria que para una fila
    de la tabla tarea (mismas claves)."""
    etapa = t["etapas"][t["indice_etapa"]]
    piso, techo = etapa["piso"], etapa["techo"]
    if t["progreso_etapa"] is not None:
        p = piso + (techo - piso) * t["progreso_etapa"] / 100.0
    else:
        transcurrido_etapa = ahora - t["inicio_etapa"]
        frac = 1.0 - math.exp(-transcurrido_etapa / _dur_efectiva(etapa["dur"], transcurrido_etapa))
        p = piso + (techo - piso) * frac
    p = max(t["progreso_visto"], min(techo, p))
    t["progreso_visto"] = p
    return round(min(99.0, p), 1)
```

Añadir al final del archivo:

```python
# ---------- Trabajos persistentes (worker) ----------

def encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None):
    """Igual que iniciar(), pero la tarea la ejecuta el worker (worker.py) y
    sobrevive reinicios. Devuelve False si ya hay una viva con ese job_id."""
    tid = cola.encolar(tipo, payload, cliente=cliente, job_id=job_id,
                       duracion_estimada=duracion_estimada, etapas=etapas or [])
    return tid is not None


def _desde_fila(fila):
    """Fila de la tabla tarea -> el mismo dict que devuelve consultar()."""
    ahora = time.time()
    if fila["estado"] == "pendiente":
        return {"estado": "en_progreso", "progreso": 0, "elapsed": 0, "mensaje": None,
                "etapa": "En cola", "detalle": fila.get("error"), "progreso_real": False}
    if fila["estado"] == "en_curso":
        etapas = _preparar_etapas([tuple(e) for e in (fila.get("etapas") or [])], fila.get("duracion_estimada") or 60)
        t = {
            "etapas": etapas,
            "indice_etapa": min(fila.get("indice_etapa") or 0, len(etapas) - 1),
            "progreso_etapa": fila.get("progreso_etapa"),
            "inicio_etapa": fila.get("inicio_etapa") or fila.get("inicio") or ahora,
            "progreso_visto": fila.get("progreso_visto") or 0.0,
        }
        progreso = _progreso_de(t, ahora)
        cola.actualizar_progreso_visto(fila["id"], t["progreso_visto"])
        return {"estado": "en_progreso", "progreso": progreso,
                "elapsed": int(ahora - (fila.get("inicio") or ahora)), "mensaje": None,
                "etapa": fila.get("etapa_actual"), "detalle": fila.get("detalle"),
                "progreso_real": fila.get("progreso_etapa") is not None}
    estado = "completado" if fila["estado"] == "hecha" else "error"
    inicio = fila.get("inicio") or ahora
    fin = ahora
    try:
        from datetime import datetime as _dt
        fin = _dt.fromisoformat(fila["terminada_en"]).timestamp() if fila.get("terminada_en") else ahora
    except (TypeError, ValueError):
        pass
    return {"estado": estado, "progreso": 100, "elapsed": int(max(0, fin - inicio)),
            "mensaje": fila.get("mensaje"), "etapa": None, "detalle": None, "progreso_real": False}
```

Modificar `reportar`, `en_curso` y `consultar` para que caigan a la cola cuando el job no está en memoria:

```python
def reportar(job_id, etapa=None, progreso=None, detalle=None):
    with _LOCK:
        t = _TRABAJOS.get(job_id)
    if not t:
        cola.reportar(job_id, etapa=etapa, progreso=progreso, detalle=detalle)
        return
    with _LOCK:
        ...  # el cuerpo actual, sin cambios
```

```python
def en_curso(job_id):
    with _LOCK:
        t = _TRABAJOS.get(job_id)
        if t:
            return t["estado"] == "en_progreso"
    fila = cola.consultar_por_job(job_id)
    return bool(fila and fila["estado"] in ("pendiente", "en_curso"))
```

En `consultar`, al principio: si no está en memoria, `fila = cola.consultar_por_job(job_id)`; `return _desde_fila(fila) if fila else None`.

- [ ] **Step 4: Correr todos los tests**

Run: `venv/bin/python3 -m pytest -q`
Expected: todo en verde (db 3, cola 7, worker 4, adaptador 4).

- [ ] **Step 5: Verificar el endpoint sin cambios**

Run: `venv/bin/python3 -m py_compile trabajos.py dashboard.py && grep -n "trabajos.consultar" dashboard.py`
Expected: compila; `estado_trabajo` sigue llamando a `trabajos.consultar(job_id)` — no se toca.

- [ ] **Step 6: Commit**

```bash
git add trabajos.py tests/test_trabajos_adaptador.py
git commit -m "trabajos.py: adaptador — encolar() al worker y polling transparente sobre la tabla tarea"
```

---

### Task 5: `creative_flow.py` sobre la base (misma API)

**Files:**
- Modify: `creative_flow.py`
- Test: `tests/test_creative_flow_db.py`

**Interfaces:**
- Consumes: `db.concepto`, `db.pieza`.
- Produces: misma API — `cargar(cliente) -> {cf_id: dict}`, `crear(...) -> cf_id`, `actualizar(cliente, cf_id, **campos) -> bool`, `eliminar(cliente, cf_id) -> bool`, `guardar(cliente, data)` (reescribe: actualiza cada entrada existente y crea las nuevas). Mapeo fijo entre el dict legado y las columnas (ver `_A_FILAS`/`_A_DICT` abajo). `cf_id` sigue siendo `cf_<timestamp>` y se guarda en `pieza.legado_id` y `concepto.legado_id`.

- [ ] **Step 1: Tests (fallan)**

`tests/test_creative_flow_db.py`:

```python
def test_crear_actualizar_cargar_eliminar(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina", 10, "", "A",
                   referencias_urls=["https://x/1.png"], platforms=[])
    assert cid.startswith("cf_")
    data = cf.cargar("acme")
    e = data[cid]
    assert e["accion_central"] == "la persona camina" and e["estado"] == "prompt_pendiente"
    assert e["referencias_urls"] == ["https://x/1.png"] and e["productos_ids"] == ["Chancla Rose"]
    assert e["duracion_objetivo"] == 10 and e["video_url"] is None and e["creado_en"]

    assert cf.actualizar("acme", cid, estado="video_listo", video_url="https://r2/v.mp4", usd=1.2,
                         prompt_relleno="PROMPT", tipo="video", modelo="wan3", enfoque="producto",
                         enfoque_nombre="Solo producto", con_persona=False, aspect_ratio="9:16",
                         referencias=[{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/v.mp4" and e["usd"] == 1.2
    assert e["prompt_relleno"] == "PROMPT" and e["modelo"] == "wan3" and e["enfoque_nombre"] == "Solo producto"
    assert e["referencias"][0]["etiqueta"] == "@Imagen 1" and e["aspect_ratio"] == "9:16"

    assert cf.eliminar("acme", cid) is True
    assert cid not in cf.cargar("acme")
    assert cf.actualizar("acme", cid, estado="x") is False


def test_cargar_ordena_por_creado_y_aisla_clientes(base_temporal):
    import creative_flow as cf
    a = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    b = cf.crear("acme", [], [], [], "dos", 5, "", "A")
    cf.crear("otro", [], [], [], "ajeno", 5, "", "A")
    data = cf.cargar("acme")
    assert list(data.keys()) == [a, b] and "ajeno" not in [v["accion_central"] for v in data.values()]


def test_guardar_dict_completo(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "uno", 5, "", "A")
    data = cf.cargar("acme")
    data[cid]["estado"] = "error"; data[cid]["error"] = "boom"
    cf.guardar("acme", data)
    assert cf.cargar("acme")[cid]["error"] == "boom"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_creative_flow_db.py -q`
Expected: FAIL (`cargar` devuelve `{}` leído del JSON, `KeyError`).

- [ ] **Step 3: Reescribir `creative_flow.py`**

```python
"""
Estado de Crear (FlowPlus). Misma API de dicts de siempre (cargar/crear/
actualizar/eliminar/guardar por cliente) pero guardada en la base del motor:
una sesión cf_... = un `concepto` (idea + referencias) con una `pieza` tipo
clon_limpio (el video/imagen generado). Los campos legado sin columna propia
viven en `extra` de cada tabla. El JSON creative_flow_pendientes.json ya no se
escribe: queda como respaldo de solo lectura (ver migrar_json_a_db.py).
"""
from datetime import datetime

import sqlalchemy as sa

import db

MODOS_VALIDOS = ("A", "B")

# Campos del dict legado que van a columnas propias
_CONCEPTO_COLS = {"enfoque": "enfoque"}
_PIEZA_COLS = {"modelo": "modelo", "video_url": "url_video", "video_local": "url_local",
               "aspect_ratio": "aspect_ratio", "usd": "costo_usd", "error": "error", "tipo": "tipo"}
_ESTADO_A_PIEZA = {"prompt_pendiente": "pendiente", "prompt_listo": "pendiente",
                   "video_generando": "generando", "video_listo": "listo", "error": "error"}
_PIEZA_A_ESTADO = {v: k for k, v in _ESTADO_A_PIEZA.items()}
_PIEZA_A_ESTADO["pendiente"] = "prompt_listo"


def _a_dict(c, p):
    e = dict(c.extra or {})
    e.update(p.extra or {})
    e.update({
        "accion_central": e.get("accion_central"),
        "enfoque": c.enfoque,
        "referencias_urls": e.get("referencias_urls"),
        "referencias": e.get("referencias"),
        "estado": e.get("estado_legado") or _PIEZA_A_ESTADO.get(p.estado, p.estado),
        "modelo": p.modelo, "video_url": p.url_video, "video_local": p.url_local,
        "aspect_ratio": p.aspect_ratio, "usd": p.costo_usd, "error": p.error,
        "tipo": p.tipo if p.tipo in ("video", "imagen") else e.get("tipo", "video"),
        "duracion_objetivo": e.get("duracion_objetivo", int(p.duracion_s or 0) or None),
        "creado_en": c.creado_en,
    })
    return e


def _separar(campos):
    """dict legado -> (valores concepto, valores pieza, extra)."""
    vc, vp, extra = {}, {}, {}
    for k, v in campos.items():
        if k in _CONCEPTO_COLS:
            vc[_CONCEPTO_COLS[k]] = v
        elif k == "tipo":
            vp["extra_tipo"] = v
        elif k in _PIEZA_COLS:
            vp[_PIEZA_COLS[k]] = v
        elif k == "estado":
            vp["estado"] = _ESTADO_A_PIEZA.get(v, "pendiente"); extra["estado_legado"] = v
        elif k == "duracion_objetivo":
            vp["duracion_s"] = float(v or 0); extra[k] = v
        else:
            extra[k] = v
    return vc, vp, extra


def cargar(cliente):
    q = (sa.select(db.concepto, db.pieza)
         .join(db.pieza, db.pieza.c.concepto_id == db.concepto.c.id)
         .where(db.concepto.c.cliente == cliente, db.pieza.c.tipo != "final",
                db.concepto.c.legado_id.isnot(None))
         .order_by(db.concepto.c.id))
    with db.conectar() as con:
        filas = con.execute(q).fetchall()
    return {f._mapping[db.concepto.c.legado_id]: _a_dict(_Cols(f, db.concepto), _Cols(f, db.pieza)) for f in filas}


class _Cols:
    """Acceso por nombre a las columnas de UNA tabla dentro de una fila de join."""
    def __init__(self, fila, tabla):
        self._m = fila._mapping; self._t = tabla
    def __getattr__(self, nombre):
        return self._m[getattr(self._t.c, nombre)]


def crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central,
          duracion_objetivo, tono, modo, referencias_urls=None, platforms=None):
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"Modo inválido: {modo}. Opciones: {MODOS_VALIDOS}")
    cf_id = "cf_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ahora = db.ahora()
    extra = {"personajes_ids": personajes_ids, "productos_ids": productos_ids, "escenas_ids": escenas_ids,
             "accion_central": accion_central, "duracion_objetivo": duracion_objetivo, "tono": tono, "modo": modo,
             "platforms": platforms or [], "prompt_relleno": None, "referencias_urls": referencias_urls,
             "credits": None, "estado_legado": "prompt_pendiente"}
    with db.conectar() as con:
        cid = con.execute(db.concepto.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, origen="manual",
            legado_id=cf_id, extra=extra)).inserted_primary_key[0]
        con.execute(db.pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="video",
            estado="pendiente", duracion_s=float(duracion_objetivo or 0), legado_id=cf_id, extra={}))
    return cf_id


def _ids(con, cliente, cf_id):
    f = con.execute(sa.select(db.concepto.c.id, db.pieza.c.id, db.concepto.c.extra, db.pieza.c.extra)
                    .join(db.pieza, db.pieza.c.concepto_id == db.concepto.c.id)
                    .where(db.concepto.c.cliente == cliente, db.concepto.c.legado_id == cf_id)).first()
    return f


def actualizar(cliente, cf_id, **campos):
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        cid, pid, extra_c, extra_p = f
        vc, vp, extra = _separar(campos)
        tipo_extra = vp.pop("extra_tipo", None)
        if tipo_extra:
            vp["tipo"] = tipo_extra
        nuevo_extra = dict(extra_c or {}); nuevo_extra.update(extra)
        ahora = db.ahora()
        con.execute(db.concepto.update().where(db.concepto.c.id == cid).values(actualizado_en=ahora, extra=nuevo_extra, **vc))
        con.execute(db.pieza.update().where(db.pieza.c.id == pid).values(actualizado_en=ahora, **vp))
    return True


def eliminar(cliente, cf_id):
    with db.conectar() as con:
        f = _ids(con, cliente, cf_id)
        if not f:
            return False
        cid, pid = f[0], f[1]
        con.execute(db.pieza.delete().where(db.pieza.c.concepto_id == cid))
        con.execute(db.concepto.delete().where(db.concepto.c.id == cid))
    return True


def guardar(cliente, data):
    """Compatibilidad: quien cargó el dict completo y lo modificó. Actualiza
    cada entrada; las que no existan se crean con lo mínimo."""
    actuales = cargar(cliente)
    for cf_id, entry in data.items():
        if cf_id in actuales:
            actualizar(cliente, cf_id, **entry)
        else:
            nuevo = crear(cliente, entry.get("personajes_ids", []), entry.get("productos_ids", []),
                          entry.get("escenas_ids", []), entry.get("accion_central", ""),
                          entry.get("duracion_objetivo", 10), entry.get("tono", ""), entry.get("modo", "A"),
                          referencias_urls=entry.get("referencias_urls"), platforms=entry.get("platforms"))
            with db.conectar() as con:
                con.execute(db.concepto.update().where(db.concepto.c.legado_id == nuevo).values(legado_id=cf_id))
                con.execute(db.pieza.update().where(db.pieza.c.legado_id == nuevo).values(legado_id=cf_id))
            actualizar(cliente, cf_id, **entry)
    for cf_id in set(actuales) - set(data):
        eliminar(cliente, cf_id)
```

Notas: `tipo` en el dict legado es `video|imagen` y en `pieza.tipo` el spec usa `clon_limpio|final`; en este bloque `pieza.tipo` guarda `video|imagen` para las piezas legado (el bloque 2 introduce `final` y el filtro `tipo != "final"` ya lo excluye). `dashboard._piezas_generadas` y `_creative_flow_items` siguen leyendo `estado == "video_listo"`, que `_a_dict` reconstruye desde `estado_legado`.

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_creative_flow_db.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Comprobar que dashboard sigue compilando y que la vista carga en local**

Run: `venv/bin/python3 -m py_compile creative_flow.py dashboard.py && venv/bin/alembic upgrade head && venv/bin/python3 -c "import creative_flow as cf; print(len(cf.cargar('happyflops')))"`
Expected: compila; imprime `0` (la base local está vacía hasta la migración de la Task 7).

- [ ] **Step 6: Commit**

```bash
git add creative_flow.py tests/test_creative_flow_db.py
git commit -m "creative_flow.py: misma API, almacenamiento en concepto+pieza de la base del motor"
```

---

### Task 6: `ads.py` sobre la base (misma API)

**Files:**
- Modify: `ads.py`
- Test: `tests/test_ads_db.py`

**Interfaces:**
- Consumes: `db.experimento`, `db.experimento_pieza`, `db.metrica_snapshot`.
- Produces: misma API — `cargar(cliente) -> {ad_id: dict}`, `crear(cliente, fuente, fuente_id, contenido_url, contenido_tipo, nombre) -> ad_id`, `actualizar(cliente, ad_id, **campos)` (KeyError si no existe), `eliminar(cliente, ad_id)`. Cada `ad_...` es una fila de `experimento_pieza` colgada del experimento "legado" del cliente (uno por cliente, `nombre="Anuncios sueltos"`, `legado=True`, creado a demanda). `meta_ids` ↔ columnas `meta_*`; `metricas` ↔ última fila de `metrica_snapshot` (+ `extra`); `estado` ↔ `experimento_pieza.estado`; el resto (`fuente, fuente_id, contenido_url, contenido_tipo, nombre, objetivo, presupuesto_diario_usd, dias, audiencia, creado_en`) en `extra`.

- [ ] **Step 1: Tests (fallan)**

`tests/test_ads_db.py`:

```python
import pytest


def test_crear_y_cargar(base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/v.mp4", "video", "Lanzamiento — Video")
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "en_cola" and e["nombre"] == "Lanzamiento — Video" and e["fuente"] == "flowplus"
    assert e["meta_ids"] == {"campaign_id": None, "adset_id": None, "ad_id": None, "creative_id": None}
    assert e["metricas"]["impresiones"] == 0 and e["metricas"]["actualizado_en"] is None
    assert e["creado_en"]


def test_actualizar_meta_ids_metricas_y_estado(base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, estado="publicando", objetivo="OUTCOME_TRAFFIC", presupuesto_diario_usd=20000, dias=3,
                   audiencia={"pais": "CO"}, meta_ids={"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"})
    ads.actualizar("acme", aid, estado="pausado", metricas={"impresiones": 10, "clics": 2, "gasto_usd": 5.5, "ctr": 20.0,
                   "reach": 8, "resultado": 2, "resultado_nombre": "Clics al enlace", "estado_meta": "PAUSED",
                   "estado_meta_texto": "Pausado", "actualizado_en": "2026-09-14T10:00:00"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "pausado" and e["meta_ids"]["ad_id"] == "3" and e["objetivo"] == "OUTCOME_TRAFFIC"
    assert e["metricas"]["impresiones"] == 10 and e["metricas"]["gasto_usd"] == 5.5 and e["metricas"]["estado_meta_texto"] == "Pausado"
    assert e["presupuesto_diario_usd"] == 20000 and e["audiencia"] == {"pais": "CO"}


def test_error_y_eliminar(base_temporal):
    import ads
    aid = ads.crear("acme", "swap", "s1", "https://r2/i.png", "imagen", "N")
    ads.actualizar("acme", aid, estado="error", error="Meta dijo no")
    assert ads.cargar("acme")[aid]["error"] == "Meta dijo no"
    ads.actualizar("acme", aid, estado="en_cola", error=None)
    assert ads.cargar("acme")[aid]["error"] is None
    ads.eliminar("acme", aid)
    assert aid not in ads.cargar("acme")
    with pytest.raises(KeyError):
        ads.actualizar("acme", aid, estado="x")


def test_orden_y_aislamiento(base_temporal):
    import ads
    a = ads.crear("acme", "f", "1", "u", "video", "a"); b = ads.crear("acme", "f", "2", "u", "video", "b")
    ads.crear("otro", "f", "3", "u", "video", "c")
    assert list(ads.cargar("acme").keys()) == [a, b]
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_ads_db.py -q`
Expected: FAIL (`KeyError` al leer del JSON vacío).

- [ ] **Step 3: Reescribir `ads.py`**

```python
"""
Estado de Campañas (anuncios en Meta). Misma API de dicts de siempre — el
"contrato Enviar a Publicidad" (crear/cargar/actualizar/eliminar) — guardada en
la base del motor: cada ad_... es una fila de `experimento_pieza` dentro del
experimento legado del cliente ("Anuncios sueltos"); las métricas son filas de
`metrica_snapshot` (se conserva historial; el dict devuelve la última).
ads.json queda como respaldo de solo lectura.
"""
from datetime import datetime

import sqlalchemy as sa

import db

_METRICAS_VACIAS = {"impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0, "actualizado_en": None}
_SNAP_COLS = {"impresiones": "impresiones", "reach": "alcance", "frecuencia": "frecuencia", "clics": "clics",
              "clics_enlace": "clics_enlace", "ctr": "ctr", "cpc": "cpc", "cpm": "cpm", "gasto_usd": "gasto",
              "compras": "compras", "ingresos": "ingresos", "roas": "roas", "costo_por_resultado": "cpa"}
_SNAP_INV = {v: k for k, v in _SNAP_COLS.items()}
_META_IDS = ("campaign_id", "adset_id", "ad_id", "creative_id")


def _experimento_legado(con, cliente):
    eid = con.execute(sa.select(db.experimento.c.id).where(
        db.experimento.c.cliente == cliente, db.experimento.c.legado.is_(True))).scalar()
    if eid:
        return eid
    ahora = db.ahora()
    return con.execute(db.experimento.insert().values(
        cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre="Anuncios sueltos",
        modo="manual", estado="corriendo", legado=True)).inserted_primary_key[0]


def _ultima_metrica(con, epid):
    f = con.execute(sa.select(db.metrica_snapshot).where(db.metrica_snapshot.c.experimento_pieza_id == epid)
                    .order_by(db.metrica_snapshot.c.id.desc()).limit(1)).first()
    if not f:
        return dict(_METRICAS_VACIAS)
    m = f._mapping
    out = {k: m[db.metrica_snapshot.c[col]] for col, k in _SNAP_INV.items()}
    out.update(m[db.metrica_snapshot.c.extra] or {})
    out["actualizado_en"] = m[db.metrica_snapshot.c.tomado_en]
    return out


def _a_dict(con, f):
    m = f._mapping
    e = dict(m[db.experimento_pieza.c.extra] or {})
    e.update({
        "estado": m[db.experimento_pieza.c.estado],
        "error": m[db.experimento_pieza.c.error],
        "meta_ids": {"campaign_id": m[db.experimento_pieza.c.extra].get("campaign_id") if False else None,
                     "adset_id": m[db.experimento_pieza.c.meta_adset_id], "ad_id": m[db.experimento_pieza.c.meta_ad_id],
                     "creative_id": m[db.experimento_pieza.c.meta_creative_id]},
        "metricas": _ultima_metrica(con, m[db.experimento_pieza.c.id]),
        "creado_en": m[db.experimento_pieza.c.creado_en],
    })
    e["meta_ids"]["campaign_id"] = e.pop("campaign_id", None)
    return e


def cargar(cliente):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento_pieza).where(
            db.experimento_pieza.c.cliente == cliente, db.experimento_pieza.c.legado_id.isnot(None)
        ).order_by(db.experimento_pieza.c.id)).fetchall()
        return {f._mapping[db.experimento_pieza.c.legado_id]: _a_dict(con, f) for f in filas}


def crear(cliente, fuente, fuente_id, contenido_url, contenido_tipo, nombre):
    ad_id = "ad_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ahora = db.ahora()
    extra = {"fuente": fuente, "fuente_id": fuente_id, "contenido_url": contenido_url, "contenido_tipo": contenido_tipo,
             "nombre": nombre, "objetivo": None, "presupuesto_diario_usd": None, "dias": None, "audiencia": None,
             "campaign_id": None}
    with db.conectar() as con:
        eid = _experimento_legado(con, cliente)
        con.execute(db.experimento_pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=eid, estado="en_cola",
            legado_id=ad_id, extra=extra))
    return ad_id


def _fila(con, cliente, ad_id):
    f = con.execute(sa.select(db.experimento_pieza).where(
        db.experimento_pieza.c.cliente == cliente, db.experimento_pieza.c.legado_id == ad_id)).first()
    if not f:
        raise KeyError(f"No existe el anuncio {ad_id} para {cliente}")
    return f


def actualizar(cliente, ad_id, **campos):
    with db.conectar() as con:
        f = _fila(con, cliente, ad_id)
        epid = f._mapping[db.experimento_pieza.c.id]
        extra = dict(f._mapping[db.experimento_pieza.c.extra] or {})
        valores = {"actualizado_en": db.ahora()}
        for k, v in campos.items():
            if k == "estado":
                valores["estado"] = v
            elif k == "error":
                valores["error"] = v
            elif k == "meta_ids":
                v = v or {}
                extra["campaign_id"] = v.get("campaign_id")
                valores.update(meta_adset_id=v.get("adset_id"), meta_ad_id=v.get("ad_id"), meta_creative_id=v.get("creative_id"))
            elif k == "metricas":
                m = dict(v or {})
                snap = {col: m.pop(k2, 0) or 0 for k2, col in _SNAP_COLS.items()}
                tomado = m.pop("actualizado_en", None) or db.ahora()
                con.execute(db.metrica_snapshot.insert().values(experimento_pieza_id=epid, tomado_en=tomado, extra=m, **snap))
                if m.get("estado_meta"):
                    valores["estado_meta"] = m["estado_meta"]
            else:
                extra[k] = v
        valores["extra"] = extra
        con.execute(db.experimento_pieza.update().where(db.experimento_pieza.c.id == epid).values(**valores))


def eliminar(cliente, ad_id):
    with db.conectar() as con:
        try:
            f = _fila(con, cliente, ad_id)
        except KeyError:
            return
        epid = f._mapping[db.experimento_pieza.c.id]
        con.execute(db.metrica_snapshot.delete().where(db.metrica_snapshot.c.experimento_pieza_id == epid))
        con.execute(db.experimento_pieza.delete().where(db.experimento_pieza.c.id == epid))
```

Nota para el implementador: en `_a_dict` la línea de `campaign_id` está escrita para dejar claro que `campaign_id` NO tiene columna en `experimento_pieza` (vive en `experimento.meta_campaign_id` en experimentos reales); para las filas legado se guarda en `extra["campaign_id"]`. Simplificar a `"campaign_id": None` y el `pop` posterior lo rellena.

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_ads_db.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Comprobar que `dashboard.py` no necesita cambios**

Run: `grep -n "ads_mod\.\(cargar\|crear\|actualizar\|eliminar\)" dashboard.py | wc -l && venv/bin/python3 -m py_compile ads.py dashboard.py`
Expected: solo esas cuatro funciones se usan; compila.

- [ ] **Step 6: Commit**

```bash
git add ads.py tests/test_ads_db.py
git commit -m "ads.py: misma API, almacenamiento en experimento_pieza + metrica_snapshot (historial de métricas)"
```

---

### Task 7: Migración idempotente de los JSON

**Files:**
- Create: `migrar_json_a_db.py`
- Test: `tests/test_migracion.py`

**Interfaces:**
- Consumes: `creative_flow.crear/actualizar/cargar`, `ads.crear/actualizar/cargar`, `_json_store.cargar`, `db`.
- Produces: `migrar_json_a_db.migrar_cliente(cliente, base_dir) -> dict(conceptos=int, anuncios=int, saltados=int)`; `migrar_json_a_db.migrar_todos(base_dir) -> list`; CLI `python migrar_json_a_db.py [cliente]`.

- [ ] **Step 1: Tests (fallan)**

`tests/test_migracion.py`:

```python
import json
import os
import tempfile


def _cliente_con_json():
    base = tempfile.mkdtemp(prefix="creatv_mig_")
    c = os.path.join(base, "clientes", "acme"); os.makedirs(c)
    cf = {"cf_20260912_160550_108303": {
        "personajes_ids": [], "productos_ids": ["Rose"], "escenas_ids": [], "accion_central": "camina",
        "duracion_objetivo": 10, "tono": "", "modo": "A", "platforms": [], "estado": "video_listo",
        "prompt_relleno": "PROMPT", "referencias_urls": ["https://x/1.png"], "video_url": "https://r2/v.mp4",
        "video_local": "/tmp/v.mp4", "credits": None, "usd": 1.0, "error": None, "creado_en": "2026-09-12T16:05:50",
        "tipo": "video", "modelo": "wan3", "enfoque": "producto", "enfoque_nombre": "Solo producto", "aspect_ratio": "9:16",
        "referencias": [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}]}}
    ads = {"ad_20260913_193256_500057": {
        "fuente": "flowplus", "fuente_id": "cf_20260912_160550_108303", "contenido_url": "https://r2/v.mp4",
        "contenido_tipo": "video", "nombre": "Lanzamiento — Video", "estado": "activo", "objetivo": "OUTCOME_TRAFFIC",
        "presupuesto_diario_usd": 20000, "dias": 3, "audiencia": {"pais": "CO"},
        "meta_ids": {"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"},
        "metricas": {"impresiones": 5, "clics": 1, "gasto_usd": 100.0, "ctr": 20.0, "reach": 4, "estado_meta": "ACTIVE",
                     "estado_meta_texto": "Activo", "actualizado_en": "2026-09-13T19:36:00"},
        "error": None, "creado_en": "2026-09-13T19:32:56"}}
    json.dump(cf, open(os.path.join(c, "creative_flow_pendientes.json"), "w"))
    json.dump(ads, open(os.path.join(c, "ads.json"), "w"))
    return base


def test_migra_y_es_idempotente(base_temporal):
    import ads, creative_flow as cf, migrar_json_a_db as mig
    base = _cliente_con_json()
    r1 = mig.migrar_cliente("acme", base)
    assert r1 == {"conceptos": 1, "anuncios": 1, "saltados": 0}
    e = cf.cargar("acme")["cf_20260912_160550_108303"]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/v.mp4" and e["creado_en"] == "2026-09-12T16:05:50"
    assert e["referencias"][0]["etiqueta"] == "@Imagen 1" and e["prompt_relleno"] == "PROMPT"
    a = ads.cargar("acme")["ad_20260913_193256_500057"]
    assert a["estado"] == "activo" and a["meta_ids"]["ad_id"] == "3" and a["metricas"]["impresiones"] == 5
    assert a["metricas"]["estado_meta_texto"] == "Activo" and a["creado_en"] == "2026-09-13T19:32:56"
    r2 = mig.migrar_cliente("acme", base)
    assert r2 == {"conceptos": 0, "anuncios": 0, "saltados": 2}
    assert len(cf.cargar("acme")) == 1 and len(ads.cargar("acme")) == 1


def test_cliente_sin_json(base_temporal):
    import migrar_json_a_db as mig
    base = tempfile.mkdtemp(); os.makedirs(os.path.join(base, "clientes", "vacio"))
    assert mig.migrar_cliente("vacio", base) == {"conceptos": 0, "anuncios": 0, "saltados": 0}
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_migracion.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'migrar_json_a_db'`.

- [ ] **Step 3: Implementar `migrar_json_a_db.py`**

```python
"""
Importa a la base del motor lo que hoy vive en JSON por cliente:
  clientes/<c>/creative_flow_pendientes.json -> concepto + pieza (via creative_flow)
  clientes/<c>/ads.json                      -> experimento legado + experimento_pieza + metrica_snapshot (via ads)
Idempotente: una entrada cuyo id (cf_.../ad_...) ya está en la base se salta.
Los JSON no se borran ni se modifican: quedan como respaldo de solo lectura.

Uso: venv/bin/python3 migrar_json_a_db.py            # todos los clientes
     venv/bin/python3 migrar_json_a_db.py happyflops # uno
"""
import os
import sys

import sqlalchemy as sa

import _json_store
import ads
import creative_flow
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _fijar_id_y_fecha(tabla, nuevo_id, legado_id, creado_en):
    with db.conectar() as con:
        con.execute(tabla.update().where(tabla.c.legado_id == nuevo_id).values(
            legado_id=legado_id, creado_en=creado_en or db.ahora()))


def migrar_cliente(cliente, base_dir=BASE_DIR):
    carpeta = os.path.join(base_dir, "clientes", cliente)
    res = {"conceptos": 0, "anuncios": 0, "saltados": 0}

    cf = _json_store.cargar(os.path.join(carpeta, "creative_flow_pendientes.json"), {})
    existentes = set(creative_flow.cargar(cliente))
    for cf_id, e in cf.items():
        if cf_id in existentes:
            res["saltados"] += 1
            continue
        nuevo = creative_flow.crear(cliente, e.get("personajes_ids", []), e.get("productos_ids", []),
                                    e.get("escenas_ids", []), e.get("accion_central", ""), e.get("duracion_objetivo", 10),
                                    e.get("tono", ""), e.get("modo", "A"), referencias_urls=e.get("referencias_urls"),
                                    platforms=e.get("platforms"))
        _fijar_id_y_fecha(db.concepto, nuevo, cf_id, e.get("creado_en"))
        _fijar_id_y_fecha(db.pieza, nuevo, cf_id, e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("creado_en",)}
        creative_flow.actualizar(cliente, cf_id, **campos)
        res["conceptos"] += 1

    an = _json_store.cargar(os.path.join(carpeta, "ads.json"), {})
    existentes = set(ads.cargar(cliente))
    for ad_id, e in an.items():
        if ad_id in existentes:
            res["saltados"] += 1
            continue
        nuevo = ads.crear(cliente, e.get("fuente"), e.get("fuente_id"), e.get("contenido_url"),
                          e.get("contenido_tipo"), e.get("nombre"))
        _fijar_id_y_fecha(db.experimento_pieza, nuevo, ad_id, e.get("creado_en"))
        campos = {k: v for k, v in e.items() if k not in ("fuente", "fuente_id", "contenido_url", "contenido_tipo", "nombre", "creado_en")}
        metricas = campos.pop("metricas", None)
        ads.actualizar(cliente, ad_id, **campos)
        if metricas and (metricas.get("actualizado_en") or metricas.get("impresiones")):
            ads.actualizar(cliente, ad_id, metricas=metricas)
        res["anuncios"] += 1
    return res


def migrar_todos(base_dir=BASE_DIR):
    raiz = os.path.join(base_dir, "clientes")
    salida = []
    for cliente in sorted(os.listdir(raiz)):
        if os.path.isdir(os.path.join(raiz, cliente)):
            salida.append((cliente, migrar_cliente(cliente, base_dir)))
    return salida


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(sys.argv[1], migrar_cliente(sys.argv[1]))
    else:
        for cliente, r in migrar_todos():
            print(cliente, r)
```

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python3 -m pytest tests/test_migracion.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Migrar la base local y ver Crear/Campañas**

Run: `venv/bin/alembic upgrade head && venv/bin/python3 migrar_json_a_db.py`
Expected: una línea por cliente con los conteos (happyflops ≈ 19 conceptos, N anuncios).

Levantar el servidor local (preview) y abrir `/cliente/happyflops` → Crear muestra la cuadrícula "Generados" con las mismas piezas que antes; Campañas muestra los mismos anuncios. Correr `venv/bin/python3 migrar_json_a_db.py` otra vez → todo `saltados`.

- [ ] **Step 6: Commit**

```bash
git add migrar_json_a_db.py tests/test_migracion.py
git commit -m "Migración idempotente de creative_flow_pendientes.json y ads.json a la base del motor"
```

---

### Task 8: FlowPlus (video/imagen) al worker

**Files:**
- Create: `tareas/flowplus.py`
- Modify: `dashboard.py` (`_lanzar_video_cf`, líneas ~2650-2790)
- Test: `tests/test_tareas_flowplus.py`

**Interfaces:**
- Consumes: `trabajos.encolar`, `creative_flow`, `flowplus_modelos`, `r2_uploader`, `bitacora`, `estado` (estado_videos), `trabajos.reportar`.
- Produces: tipos de tarea `flowplus_video` y `flowplus_imagen` con payload `{cliente, cf_id}`; `tareas.flowplus.ejecutar_video(tarea)` y `ejecutar_imagen(tarea)`; `dashboard._lanzar_video_cf(cliente, cf_id, entry)` ahora encola y devuelve el bool de `trabajos.encolar`. Las constantes de etapas se mueven a `tareas/flowplus.py` (`ETAPA_MODELO, ETAPA_DESCARGAR, ETAPA_GUARDAR_VIDEO, ETAPAS_CREATIVE_FLOW`) y `dashboard.py` las importa de ahí (mantener los nombres).

- [ ] **Step 1: Tests (fallan)**

`tests/test_tareas_flowplus.py`:

```python
def test_ejecutar_video_guarda_resultado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")

    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d: {"credits": None, "usd": 0.5})
    class R:  # respuesta falsa de requests.get
        content = b"00"; status_code = 200
        def raise_for_status(self): pass
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    guardado = {}
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: guardado.update(d))

    msg = fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "acme__cf__creative_flow"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/clientes/acme/videos/%s.mp4" % cid and e["usd"] == 0.5
    assert cid in guardado and "listo" in msg


def test_ejecutar_video_marca_error(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3")
    def _boom(*a, **k): raise RuntimeError("proveedor caído")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _boom)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    import pytest
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["estado"] == "error"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_tareas_flowplus.py -q`
Expected: FAIL con `AttributeError: module 'tareas.flowplus' has no attribute 'ejecutar_video'`.

- [ ] **Step 3: Implementar `tareas/flowplus.py`**

Mover a este módulo, **sin cambiar la lógica**, los cuerpos de `trabajo_imagen()` y `trabajo()` de `dashboard._lanzar_video_cf`, con estas sustituciones: las variables que la closure tomaba del scope (`referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, tipo, modelo, job_id, entry`) se recalculan al inicio desde `entry = creative_flow.cargar(cliente)[cf_id]` con exactamente el mismo código que hoy está antes de `def trabajo_imagen()` (el bloque que empieza en `referencias = entry.get("referencias_urls") or []` y termina en `job_id = _job_id_creative_flow(cliente, cf_id)`). `_aspect_ratio_para_plataformas` y `_texto_fase`/`_avisar_fase_de` se copian tal cual a este módulo (son funciones puras; dejar las de `dashboard.py` donde están para el pipeline viejo).

```python
"""
Tareas del worker para Crear (FlowPlus): generar el video o la imagen de una
sesión cf_... Cuerpos movidos de dashboard._lanzar_video_cf; dashboard ahora
solo encola. Todo lo que la closure tomaba del request se relee de la base.
"""
import os
from datetime import datetime

import requests

import bitacora
import creative_flow
import estado as estado_mod
import flowplus_modelos
import trabajos
from providers import flowplus_modelos as _pm  # noqa: F401  (mismo módulo; alias explícito si el import de arriba es distinto)
from storage import r2_uploader
from tareas import registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ETAPA_MODELO = "Generando con el modelo"
ETAPA_DESCARGAR = "Descargando el resultado"
ETAPA_GUARDAR_VIDEO = "Guardando el video"
ETAPAS_CREATIVE_FLOW = [(ETAPA_MODELO, 85), (ETAPA_DESCARGAR, 5), (ETAPA_GUARDAR_VIDEO, 10)]


def _job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


def _avisar_fase_de(job_id):
    def avisar_fase(info):
        try:
            texto = _texto_fase(info)
            if texto:
                trabajos.reportar(job_id, detalle=texto)
        except Exception:
            pass
    return avisar_fase


# _texto_fase y _aspect_ratio_para_plataformas: copiar tal cual desde dashboard.py


def _preparar(cliente, cf_id):
    entry = creative_flow.cargar(cliente)[cf_id]
    # --- bloque idéntico al inicio de dashboard._lanzar_video_cf ---
    referencias = entry.get("referencias_urls") or []
    videos_ref = [r["url"] for r in (entry.get("referencias") or []) if r.get("tipo") == "video"]
    if videos_ref and (entry.get("modelo") or "wan3") == "wan3":
        frames_video = {r["frame_url"] for r in entry["referencias"] if r.get("tipo") == "video"}
        referencias = [u for u in referencias if u not in frames_video]
    duracion = entry["duracion_objetivo"]
    prompt_texto = entry.get("prompt_relleno") or entry.get("accion_central") or ""
    platforms = entry.get("platforms", [])
    aspect_ratio = entry.get("aspect_ratio") or _aspect_ratio_para_plataformas(platforms)
    tipo = entry.get("tipo") or "video"
    if tipo == "imagen":
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.IMAGEN else flowplus_modelos.IMAGEN_POR_DEFECTO
    else:
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
    return entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo


@registrar("flowplus_imagen")
def ejecutar_imagen(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    entry, referencias, _, _, prompt_texto, _, _, modelo = _preparar(cliente, cf_id)
    # ... cuerpo de trabajo_imagen() tal cual, usando estas variables ...
    return "Imagen de FlowPlus lista."


@registrar("flowplus_video")
def ejecutar_video(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo = _preparar(cliente, cf_id)
    # ... cuerpo de trabajo() tal cual, usando estas variables ...
    return "Video de FlowPlus listo, pendiente de revisión."
```

Verificar el import real de `flowplus_modelos` en `dashboard.py` (`from providers import flowplus_modelos` o `import flowplus_modelos`) y usar el mismo; borrar la línea del alias si no aplica.

- [ ] **Step 4: `dashboard._lanzar_video_cf` pasa a encolar**

Reemplazar el cuerpo completo de `_lanzar_video_cf` por:

```python
def _lanzar_video_cf(cliente, cf_id, entry):
    """Encola en el worker la generación de una sesión de FlowPlus (video o
    imagen). Devuelve True si encoló, False si ya había una en curso."""
    tipo = entry.get("tipo") or "video"
    job_id = _job_id_creative_flow(cliente, cf_id)
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    return trabajos.encolar(
        job_id, "flowplus_imagen" if tipo == "imagen" else "flowplus_video",
        {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
        duracion_estimada=60 if tipo == "imagen" else 180, etapas=ETAPAS_CREATIVE_FLOW,
    )
```

Y arriba, junto a los otros imports: `from tareas.flowplus import ETAPAS_CREATIVE_FLOW` (borrar la definición local `ETAPAS_CREATIVE_FLOW = [...]` de `dashboard.py`; las demás constantes `ETAPA_*` de dashboard se quedan porque las usa el pipeline viejo).

- [ ] **Step 5: Correr todo**

Run: `venv/bin/python3 -m pytest -q && venv/bin/python3 -m py_compile dashboard.py tareas/flowplus.py && venv/bin/python3 -c "import tareas; tareas.cargar_todas(); print(sorted(tareas.REGISTRO))"`
Expected: tests verdes; imprime `['flowplus_imagen', 'flowplus_video']`.

- [ ] **Step 6: Prueba manual local de punta a punta**

En una terminal: `venv/bin/python3 worker.py`. En otra, el servidor. En Crear (happyflops), generar una imagen con Seedream (barata). Esperado: la tarjeta muestra la barra ("En cola" → "Generando con el modelo" → …), el worker loguea `tarea N flowplus_imagen … hecha`, la tarjeta pasa a lista. Matar el worker (Ctrl-C) a mitad de otra generación y volver a lanzarlo: tras `recuperar_colgadas` (para probar rápido, llamar `cola.recuperar_colgadas(0)` con `python -c`) la tarea se reintenta y termina.

- [ ] **Step 7: Commit**

```bash
git add tareas/flowplus.py dashboard.py tests/test_tareas_flowplus.py
git commit -m "Crear: la generación de FlowPlus corre en el worker (sobrevive reinicios); dashboard solo encola"
```

---

### Task 9: Publicar anuncio y refrescar métricas al worker

**Files:**
- Create: `tareas/meta.py`
- Modify: `dashboard.py` (`publicar_ad` ~línea 2160, `actualizar_resultados_ad` ~línea 2306)
- Test: `tests/test_tareas_meta.py`

**Interfaces:**
- Consumes: `ads`, `meta_conexion`, `meta_ads.auth/campaign/adset/targeting/creative/ad/insights`, `bitacora`, `trabajos.reportar`.
- Produces: tipos `meta_publicar` (payload `{cliente, ad_id, objetivo, presupuesto_diario, dias, pais, edad_min, edad_max, destino_url}`) y `meta_refrescar` (payload `{cliente, ad_id}`); `dashboard.publicar_ad` valida el formulario como hoy, deja el anuncio en `publicando` y encola; `dashboard.actualizar_resultados_ad` encola `meta_refrescar` con `job_id=f"{cliente}__{ad_id}__metricas"` y muestra flash "Actualizando resultados…" (la tarjeta se recarga sola por el polling existente: añadir `iniciarPolling` a la tarjeta cuando `trabajos.en_curso(job_id)`, igual que hace la cola de publicar hoy).

- [ ] **Step 1: Tests (fallan)**

`tests/test_tareas_meta.py`:

```python
def test_refrescar_guarda_snapshot(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "u", "video", "N")
    ads.actualizar("acme", aid, estado="activo", objetivo="OUTCOME_TRAFFIC",
                   meta_ids={"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"})
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", lambda c: {"token": "T", "ad_account_id": "act_1", "page_id": "p"})
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: None)
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: None)
    monkeypatch.setattr(tm.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: {
        "impresiones": 120, "clics": 9, "gasto_usd": 4000.0, "ctr": 7.5, "reach": 100, "resultado": 8,
        "resultado_nombre": "Clics al enlace", "estado_meta": "ACTIVE", "estado_meta_texto": "Activo"})
    msg = tm.refrescar({"payload": {"cliente": "acme", "ad_id": aid}, "job_id": "j"})
    m = ads.cargar("acme")[aid]["metricas"]
    assert m["impresiones"] == 120 and m["resultado"] == 8 and m["actualizado_en"] and "actualizados" in msg.lower()


def test_publicar_sin_conexion_marca_error(base_temporal, monkeypatch):
    import ads, pytest
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, estado="publicando")
    def _sin(c): raise tm.meta_conexion.ErrorConexion("no conectado")
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _sin)
    monkeypatch.setattr(tm.bitacora, "registrar", lambda *a, **k: None)
    with pytest.raises(Exception):
        tm.publicar({"payload": {"cliente": "acme", "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": 20000,
                                 "dias": 3, "pais": "CO", "edad_min": 18, "edad_max": 45,
                                 "destino_url": "https://app.creatvmachine.com/l/acme"}, "job_id": "j"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "error" and "no conectado" in (e["error"] or "")
```

Comprobar el nombre real de la excepción de `meta_conexion` (la clase con `__init__(self, mensaje, codigo=None)` en la línea ~52) y usarlo en el test.

- [ ] **Step 2: Correr y ver fallar**

Run: `venv/bin/python3 -m pytest tests/test_tareas_meta.py -q`
Expected: FAIL (`no attribute 'refrescar'`).

- [ ] **Step 3: Implementar `tareas/meta.py`**

Mover el cuerpo de `trabajo()` de `dashboard.publicar_ad` (todo lo que está dentro de `with _ENV_LOCK:` — configurar credenciales, crear campaña/adset/creative/ad, mapear errores 1359188 / 1885183 / capability, `ads_mod.actualizar(... estado="pausado", meta_ids=...)`, `bitacora`, `finally: meta_auth.limpiar()`) a `publicar(tarea)`, leyendo `objetivo, presupuesto_diario, dias, pais, edad_min, edad_max, destino_url` del payload en vez de `request.form`, y `entry = ads.cargar(cliente)[ad_id]`. El cálculo de `moneda`, `minimo`, `centavos` que hoy está en la ruta antes de lanzar el trabajo se mueve también aquí (usa `meta_conexion.cargar(cliente)`). `_miniatura_para_ad` se copia a este módulo tal cual (usa ffmpeg + R2).

```python
"""
Tareas del worker para Campañas: publicar un anuncio en Meta y refrescar sus
métricas. Cuerpos movidos de dashboard.publicar_ad / actualizar_resultados_ad.
El worker es de un hilo, pero se conserva el lock por si se ejecuta dentro de
gunicorn en tests.
"""
import threading

import ads
import bitacora
import meta_conexion
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights, targeting as meta_targeting
from tareas import registrar

_LOCK = threading.Lock()


@registrar("meta_publicar")
def publicar(tarea):
    p = tarea["payload"]; cliente, ad_id = p["cliente"], p["ad_id"]
    entry = ads.cargar(cliente)[ad_id]
    with _LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            # ... cuerpo actual de trabajo() de publicar_ad ...
            return "Anuncio creado en Meta (pausado)."
        except Exception as e:
            msg = str(e)
            # ... mismo mapeo de mensajes (1359188, 1885183/capability) ...
            ads.actualizar(cliente, ad_id, estado="error", error=msg)
            bitacora.registrar(cliente, ad_id, "ads_publicar", "error", str(e)[:500])
            raise
        finally:
            meta_auth.limpiar()


@registrar("meta_refrescar")
def refrescar(tarea):
    p = tarea["payload"]; cliente, ad_id = p["cliente"], p["ad_id"]
    entry = ads.cargar(cliente)[ad_id]
    if not entry.get("meta_ids", {}).get("ad_id"):
        return "Ese anuncio todavía no está publicado en Meta."
    with _LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"], objetivo=entry.get("objetivo"))
            resultados["actualizado_en"] = __import__("db").ahora()
            ads.actualizar(cliente, ad_id, metricas=resultados)
            return "Resultados actualizados."
        finally:
            meta_auth.limpiar()
```

Importante: `max_intentos=1` al encolar `meta_publicar` (reintentar solo crearía campañas huérfanas en Meta; el usuario reintenta con "Volver a intentar"); `meta_refrescar` puede reintentar (idempotente).

- [ ] **Step 4: Rutas de `dashboard.py`**

`publicar_ad`: conservar validación del formulario; luego:

```python
    ads_mod.actualizar(cliente, ad_id, estado="publicando", error=None)
    arranco = trabajos.encolar(job_id, "meta_publicar", {
        "cliente": cliente, "ad_id": ad_id, "objetivo": objetivo, "presupuesto_diario": presupuesto_diario,
        "dias": dias, "pais": pais, "edad_min": edad_min, "edad_max": edad_max, "destino_url": destino_url,
    }, cliente=cliente, duracion_estimada=90)
```

(con `cola.encolar(..., max_intentos=1)` — añadir el parámetro `max_intentos=5` a `trabajos.encolar` y pasarlo). `actualizar_resultados_ad`: reemplazar el bloque `with _ENV_LOCK:` por `trabajos.encolar(f"{cliente}__{ad_id}__metricas", "meta_refrescar", {"cliente": cliente, "ad_id": ad_id}, cliente=cliente, duracion_estimada=10)` y flash `"Actualizando resultados…"`. En `_tab_ads.html`, dentro de la tarjeta de publicados, añadir el mismo bloque de barra + `iniciarPolling` que usan las tarjetas de Crear cuando `entry.trabajo` existe; en `ver_cliente` calcular `trabajo` para cada ad con `trabajos.en_curso(f"{cliente}__{ad_id}__metricas") or trabajos.en_curso(_job_id_publicar_ad(cliente, ad_id))`.

- [ ] **Step 5: Correr todo y prueba manual**

Run: `venv/bin/python3 -m pytest -q && venv/bin/python3 -m py_compile dashboard.py tareas/meta.py`
Expected: verde. Manual (con el worker corriendo y `colorado_forja`): "Actualizar resultados" → barra breve → cifras nuevas; "Volver a intentar" + "Publicar" sobre una pieza de prueba → el worker crea el anuncio (pausado) y la tarjeta cambia sola.

- [ ] **Step 6: Commit**

```bash
git add tareas/meta.py dashboard.py templates/_tab_ads.html tests/test_tareas_meta.py
git commit -m "Campañas: publicar y refrescar métricas corren en el worker"
```

---

### Task 10: Cambiar producto (swap) al worker

**Files:**
- Create: `tareas/swap.py`
- Modify: `dashboard.py` (`_lanzar_swap`, líneas ~1620-1903)

**Interfaces:**
- Consumes: `swaps_mod`, proveedores de swap, `r2_uploader`, `bitacora`, `catalogo_productos`, `aspect_ratio_mod`, `marca_mod`, `trabajos.reportar`.
- Produces: tipo `swap_generar`, payload `{cliente, swap_id, producto_id, proveedor, tipo, mejorar_calidad}`; `dashboard._lanzar_swap` guarda el archivo, crea el swap (como hoy) y encola.

- [ ] **Step 1: Mover el cuerpo**

Crear `tareas/swap.py` con `@registrar("swap_generar") def ejecutar(tarea)`: reconstruir las variables locales al inicio — `entry = swaps_mod.cargar(cliente)[swap_id]`, `foto_local = entry["foto_original_local"]` (verificar el nombre real de la clave en `swaps.py`), `producto = catalogo_productos.encontrar(cliente, producto_id)`, `es_video = tipo == "video"`, `job_id = tarea["job_id"]`, `avisar_fase = _avisar_fase_de(job_id)` — y pegar **verbatim** el cuerpo de `def trabajo():` de `_lanzar_swap` (desde `try:` hasta el `return` final). Todo lo que ese cuerpo llama (`_extraer_frame`, `_texto_fase`, `ETAPAS_SWAP_FOTO/VIDEO`, `ETAPA_*`, `PROVEEDORES_SWAP_*`, `NOMBRES_PROVEEDOR_SWAP`, `_evaluar_contra_matriz` o similar) se mueve/copia al módulo; las constantes `ETAPAS_SWAP_*` y `ETAPA_*` de swap salen de `dashboard.py` y se importan desde `tareas.swap` donde el dashboard aún las use.

- [ ] **Step 2: `_lanzar_swap` encola**

Conservar hasta `swap_id = swaps_mod.crear(...)` y `job_id = ...`; reemplazar el resto por:

```python
    return trabajos.encolar(job_id, "swap_generar", {
        "cliente": cliente, "swap_id": swap_id, "producto_id": producto_id,
        "proveedor": proveedor, "tipo": tipo, "mejorar_calidad": bool(mejorar_calidad),
    }, cliente=cliente, duracion_estimada=duracion_estimada, etapas=etapas)
```

(`duracion_estimada` y `etapas` son las que hoy se pasan a `trabajos.iniciar` en la línea ~1903).

- [ ] **Step 3: Verificar**

Run: `venv/bin/python3 -m pytest -q && venv/bin/python3 -m py_compile dashboard.py tareas/swap.py && venv/bin/python3 -c "import tareas; tareas.cargar_todas(); print(sorted(tareas.REGISTRO))"`
Expected: verde; `['flowplus_imagen', 'flowplus_video', 'meta_publicar', 'meta_refrescar', 'swap_generar']`.

Manual: Crear › Cambiar producto con una foto (Nano Banana) → barra → resultado con evaluación de marca, igual que antes.

- [ ] **Step 4: Commit**

```bash
git add tareas/swap.py dashboard.py
git commit -m "Cambiar producto: la generación corre en el worker"
```

---

### Task 11: Documentación y despliegue

**Files:**
- Modify: `CLAUDE.md` (sección "Background jobs" y "State machine modules"), `SETUP.md`
- Memoria: actualizar `produccion-vps-creatvmachine.md` con el segundo servicio.

- [ ] **Step 1: CLAUDE.md**

En "Background jobs" añadir: los trabajos migrados (`flowplus_*`, `meta_*`, `swap_generar`) se encolan con `trabajos.encolar(...)` en la tabla `tarea` (`data/creatv.db`) y los ejecuta `worker.py` (servicio `creatv-worker`); el resto sigue en memoria. Cómo correr local: `venv/bin/alembic upgrade head` y `venv/bin/python3 worker.py` en otra terminal. Tests: `venv/bin/python3 -m pytest -q`. En "State machine modules": `creative_flow.py` y `ads.py` guardan en la base (misma API); los JSON son respaldo; `migrar_json_a_db.py` los importa.

- [ ] **Step 2: Desplegar**

```bash
git push origin main
ssh deploy@116.203.20.147 'cd /home/deploy/iaplusyou && git pull --ff-only origin main && venv/bin/pip install -r requirements.txt && venv/bin/alembic upgrade head && venv/bin/python3 migrar_json_a_db.py'
ssh root@116.203.20.147 'cp /home/deploy/iaplusyou/deploy/creatv-worker.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now creatv-worker && systemctl restart iaplusyou && sleep 3 && systemctl is-active iaplusyou creatv-worker && journalctl -u creatv-worker -n 5 --no-pager'
```

Expected: ambos `active`; el log del worker muestra `worker arriba · tipos [...]`.

Añadir `data/` al `rsync` de respaldo (ver memoria) y verificar en prod: Crear muestra las piezas de siempre, Campañas los anuncios de Forja con sus métricas, "Actualizar resultados" funciona vía worker.

- [ ] **Step 3: Commit final**

```bash
git add CLAUDE.md SETUP.md
git commit -m "Docs: base del motor, worker y migración"
git push origin main
```

---

## Autorevisión

**Cobertura del spec (§2, §8, §9 bloque 1):** las 12 tablas → Task 1; cola con reclamo atómico, reintentos exponenciales, colgadas > 30 min, planificador y progreso → Tasks 2-4; `trabajos.py` adaptador y polling sin cambios → Task 4; `creative_flow`/`ads` sobre la base con JSON como respaldo → Tasks 5-6; migración sin corte e idempotente → Task 7; jobs migrados (FlowPlus, publicar, métricas, swap) → Tasks 8-10; systemd + deploy → Tasks 3 y 11. Fuera de bloque (y del plan): tienda/pedido/propuesta solo se crean como tablas (los usan los bloques 4-5).

**Consistencia de nombres:** `cola.encolar(..., max_intentos)` ↔ `trabajos.encolar(..., max_intentos=5)` (añadido en Task 9); `tareas.registrar`/`REGISTRO`/`cargar_todas` iguales en Tasks 3, 8, 9, 10; tipos de tarea `flowplus_video|flowplus_imagen|meta_publicar|meta_refrescar|swap_generar`; `ETAPAS_CREATIVE_FLOW` vive en `tareas/flowplus.py` y `dashboard.py` lo importa.

**Riesgo señalado:** Tasks 8 y 10 mueven cuerpos largos "verbatim"; el revisor de cada tarea debe diffear el cuerpo movido contra el original (`git show HEAD~1:dashboard.py`) para confirmar que no se alteró la lógica.
