# Cobros con saldo prepagado — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que cada proyecto que «cobra» pague el uso con un saldo prepagado (costo real × margen), recargable con Bold o a mano por el admin, sin cambiar nada en los proyectos que no cobran.

**Architecture:** un paquete nuevo `cobros/` con un escritor único del libro (`cobros/libro.py`), uno de recargas (`cobros/recargas.py`), el cliente HTTP de Bold (`cobros/bold.py`), las lecturas para pantallas (`cobros/vista.py`) y un Blueprint (`cobros/rutas.py`). El cobro se engancha en la única puerta del costo (`gastos.registrar`), el freno en `trabajos.encolar` + las rutas sincrónicas + un respaldo en el worker, y la reversión en el punto donde el worker marca una tarea en error definitivo.

**Tech Stack:** Python 3, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (WAL), Alembic, `requests`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-cobros-saldo-prepagado-design.md` (léelo entero antes de tu tarea; los números de sección §N de este plan son los del spec).

## Global Constraints

- Trabaja SOLO en el worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/cobros` (rama `cobros`). Nunca en el checkout principal.
- Python de pruebas: `PY=/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3` (el worktree no tiene venv propio). Pruebas: `$PY -m pytest -q <archivo>`; suite rápida: `$PY -m pytest -q -m "not slow"`.
- Lee `CLAUDE.md` y carga la skill del área antes de tocar su código: `plataforma` (gastos, cola, worker, tareas), `seguridad` (rutas POST, webhook), `ui` (pantallas), `idioma` (todo texto visible), `escala-y-salud` (consultas de listas).
- Montos del libro: **milésimas de dólar, enteros**. `precio = ceil(round(costo × margen × 1000, 6))` (el `round` evita que `0.01*1.5*1000 = 15.000000000000002` suba a 16).
- Margen por defecto **1,5**, global en `kv` clave `cobros:margen_global`, por proyecto en `cuenta_saldo.margen` (NULL = global). Rango válido 1,00 a 5,00.
- Recarga: dólares enteros, **mínimo 10, máximo 1 000**. Recarga manual o ajuste del admin: decimales con 2 cifras, nota obligatoria en un ajuste.
- Umbral de aviso por defecto **5 000 milésimas** (US$ 5).
- Proyecto que no cobra (sin fila en `cuenta_saldo` o `cobrar = 0`): **ningún** comportamiento cambia. Toda prueba existente debe seguir pasando sin tocarla.
- Escritores únicos: `cobros/libro.py` escribe `cuenta_saldo`, `movimiento_saldo`, `reserva_saldo`; `cobros/recargas.py` escribe `recarga`, `pago_evento`. Nadie más hace INSERT/UPDATE/DELETE en esas tablas.
- Todo texto visible pasa por el catálogo (`{{ _('…') }}`, `gettext`, `idiomas.N_`). Lo que se guarda o se manda va en el idioma del proyecto (`idiomas.en_idioma(idiomas.de_proyecto(cliente))`).
- `movimiento_saldo.concepto` guarda un **código** (el `tipo` del gasto: `video`, `final`…, o `recarga_bold`, `recarga_manual`, `ajuste`, `anulacion_bold`), no texto traducido; se traduce al pintar (`cobros.vista.nombre_concepto`). Ruling de implementación que reemplaza «en el idioma del proyecto al escribirlo» del §2.
- Ninguna llave de Bold en logs, flashes, eventos ni `pago_evento` (`cola.sin_token` sobre todo texto de error).
- Cada tarea cierra con su commit (mensaje en español, terminado en `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). Antes de commitear: `ls .git/MERGE_HEAD .git/REBASE_HEAD` en el directorio git del worktree no debe existir.
- Los hooks del repo compilan cada `.py` y revisan plantillas tras cada edición: si uno te frena, arregla la causa, no lo esquives.

---

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `db.py` | tablas `cuenta_saldo`, `movimiento_saldo`, `reserva_saldo`, `recarga`, `pago_evento` | 1 |
| `migrations/versions/0032_cobros.py` | crea esas tablas | 1 |
| `cobros/__init__.py` | reexporta `SaldoInsuficiente` | 2 |
| `cobros/libro.py` | cuenta, margen, saldo, reservas, cobrar, revertir, exigir, acreditar, contexto de tarea | 2 |
| `cobros/avisos.py` | correos y bitácora de cobros (pieza no cobrada, recarga, saldo bajo, admin) | 2 |
| `gastos.py` | engancha `cobrar_gasto` en `registrar`; `entregado=`; `texto_precio`, `usd_precio` | 3, 6 |
| `cola.py` | `fallar(..., definitivo=False)` devuelve el estado; `viva(job_id)` | 4 |
| `worker.py` | contexto de tarea, reversión en error definitivo, respaldo antes de correr | 4 |
| `tareas/__init__.py` | `TIPOS_QUE_COBRAN`, `TIPOS_EXENTOS_DE_COBRO` | 4 |
| `trabajos.py` | `encolar(..., costo_estimado=None)` con el freno | 5 |
| `dashboard.py` | manejador de `SaldoInsuficiente`, `g.margen_precio`, filtro `precio`, Blueprint, exenciones del webhook | 5, 6, 7 |
| rutas que encolan / cobran en la petición | pasan el estimado / llaman a `exigir` | 5 |
| `cobros/bold.py` | HTTP con Bold: crear link, estado, firma | 7 |
| `cobros/recargas.py` | crear recarga, webhook, verificar, manual | 7 |
| `cobros/rutas.py` | Blueprint: saldo, recargas, webhook, admin | 7, 8, 10 |
| `tareas/cobros.py` | periódica `cobros_verificar_recargas`; limpieza de reservas | 7 |
| `cobros/vista.py` | lecturas para pantallas (resumen cobrado, movimientos, admin) | 8, 10 |
| `templates/_config_saldo.html`, `templates/_saldo_panel.html`, `templates/saldo_recarga.html`, `templates/admin_cobros.html`, `static/cobros.js` | pantallas | 8, 10 |
| `alertas.py` | `_fuente_cobros` | 9 |
| `notificaciones.py` | tipos nuevos en `TIPOS` | 2 |
| `.claude/skills/cobros/SKILL.md`, `CLAUDE.md`, `docs/pendientes.md`, `CONTEXT.md` | documentación | 11 |
| `translations/en/LC_MESSAGES/messages.po` | catálogo | 11 |

---

### Task 1: Tablas y migración 0032

**Files:**
- Modify: `db.py` (después de la tabla `gasto`, ~línea 557)
- Create: `migrations/versions/0032_cobros.py`
- Test: `tests/test_cobros_db.py`

**Interfaces:**
- Produces: `db.cuenta_saldo`, `db.movimiento_saldo`, `db.reserva_saldo`, `db.recarga`, `db.pago_evento` (objetos `sa.Table`), con las columnas exactas del §2 del spec.

- [ ] **Step 1: prueba que falla**

```python
# tests/test_cobros_db.py
"""Cobros (spec 2026-10-08 §2): las cinco tablas nuevas y sus únicos."""
import pytest
import sqlalchemy as sa

AHORA = "2026-10-08T10:00:00"


def test_tablas_existen(base_temporal):
    db = base_temporal
    insp = sa.inspect(db.engine())
    for t in ("cuenta_saldo", "movimiento_saldo", "reserva_saldo", "recarga", "pago_evento"):
        assert t in insp.get_table_names()


def test_un_cobro_por_gasto(base_temporal):
    db = base_temporal
    fila = dict(cliente="acme", creado_en=AHORA, tipo="cobro", milesimas=-1500, gasto_id=7, concepto="video")
    with db.conectar() as con:
        con.execute(sa.insert(db.movimiento_saldo).values(**fila))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.movimiento_saldo).values(**fila))


def test_varias_recargas_sin_gasto_no_chocan(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        for rid in (1, 2):
            con.execute(sa.insert(db.movimiento_saldo).values(
                cliente="acme", creado_en=AHORA, tipo="recarga", milesimas=10000, recarga_id=rid, concepto="recarga_bold"))


def test_pago_id_unico(base_temporal):
    db = base_temporal
    base = dict(cliente="acme", creada_en=AHORA, medio="bold", estado="aprobada", milesimas=10000, usuario="u")
    with db.conectar() as con:
        con.execute(sa.insert(db.recarga).values(referencia="cv-1-1", pago_id="P1", **base))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.recarga).values(referencia="cv-2-1", pago_id="P1", **base))


def test_evento_de_bold_unico(base_temporal):
    db = base_temporal
    ev = dict(proveedor="bold", evento_id="e1", tipo="SALE_APPROVED", recibido_en=AHORA, firma_ok=True, resultado="acreditada")
    with db.conectar() as con:
        con.execute(sa.insert(db.pago_evento).values(**ev))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.pago_evento).values(**ev))
```

- [ ] **Step 2:** `$PY -m pytest -q tests/test_cobros_db.py` → FAIL (`AttributeError: module 'db' has no attribute 'movimiento_saldo'`).

- [ ] **Step 3: tablas en `db.py`** (debajo de `gasto`, con un comentario que cite el spec):

```python
# --- Cobros: saldo prepagado por proyecto (docs/superpowers/specs/2026-10-08-cobros-saldo-prepagado-design.md §2) ---
# Montos en milésimas de dólar, enteros. Escritores únicos: cobros/libro.py
# (cuenta_saldo, movimiento_saldo, reserva_saldo) y cobros/recargas.py (recarga, pago_evento).

cuenta_saldo = Table("cuenta_saldo", metadata,
    Column("cliente", String(80), primary_key=True),
    Column("cobrar", Boolean, nullable=False, default=False),
    Column("margen", Float),                                   # NULL = kv cobros:margen_global
    Column("umbral_aviso", Integer, nullable=False, default=5000),
    Column("actualizado_en", String(19)),
    Column("actualizado_por", String(80)),
)

movimiento_saldo = Table("movimiento_saldo", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False),
    Column("creado_en", String(19), nullable=False),
    Column("tipo", String(16), nullable=False),                # recarga|cobro|reverso|no_cobrado|ajuste|anulacion
    Column("milesimas", Integer, nullable=False),              # con signo
    Column("gasto_id", Integer),
    Column("recarga_id", Integer),
    Column("job_id", String(160)),
    Column("tarea_id", Integer),
    Column("concepto", String(120), nullable=False),           # código; se traduce al pintar
    Column("detalle", String(300)),
    Column("usuario", String(80)),
    Column("extra", JSON),
    sa.UniqueConstraint("tipo", "gasto_id", name="uq_movimiento_gasto"),
    sa.UniqueConstraint("tipo", "recarga_id", name="uq_movimiento_recarga"),
    sa.Index("ix_movimiento_cliente_creado", "cliente", "creado_en"),
    sa.Index("ix_movimiento_job", "job_id"),
    sqlite_autoincrement=True,
)

reserva_saldo = Table("reserva_saldo", metadata,
    Column("cliente", String(80), primary_key=True),
    Column("job_id", String(160), primary_key=True),
    Column("milesimas", Integer, nullable=False),
    Column("creada_en", String(19), nullable=False),
)

recarga = Table("recarga", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("creada_en", String(19), nullable=False),
    Column("actualizada_en", String(19)),
    Column("medio", String(12), nullable=False),               # bold|manual
    Column("estado", String(12), nullable=False),              # pendiente|aprobada|rechazada|expirada|anulada
    Column("milesimas", Integer, nullable=False),
    Column("referencia", String(60), nullable=False, unique=True),
    Column("link_id", String(40)),
    Column("pago_id", String(40), unique=True),
    Column("moneda_pago", String(3)),
    Column("total_pago", Integer),
    Column("medio_pago", String(20)),
    Column("usuario", String(80), nullable=False),
    Column("nota", String(300)),
    sqlite_autoincrement=True,
)

pago_evento = Table("pago_evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("proveedor", String(12), nullable=False),
    Column("evento_id", String(64), nullable=False),
    Column("tipo", String(24), nullable=False),
    Column("referencia", String(60)),
    Column("recibido_en", String(19), nullable=False),
    Column("firma_ok", Boolean, nullable=False),
    Column("resultado", String(40), nullable=False),
    Column("cuerpo", JSON),
    sa.UniqueConstraint("proveedor", "evento_id", name="uq_pago_evento"),
    sa.Index("ix_pago_evento_recibido", "recibido_en"),
)
```

Verifica que `Boolean` esté importado en `db.py` (si no, agrégalo al `from sqlalchemy import …`).

- [ ] **Step 4: migración** `migrations/versions/0032_cobros.py`, con el formato de `0029_alerta_descartada.py` (docstring con el motivo, `revision = '0032'`, `down_revision = '0031'`): `op.create_table` de las cinco tablas con exactamente las mismas columnas, únicos e índices (el `sqlite_autoincrement=True` va como kwarg de `op.create_table`), y `downgrade` que las borra en orden inverso.

- [ ] **Step 5: verificar**
  - `$PY -m pytest -q tests/test_cobros_db.py tests/test_db.py` → PASS.
  - Migración en una copia: `cp /Users/colorado/Documents/GitHub/iaplusyou/data/creatv.db /tmp/cobros_copia.db 2>/dev/null || true; CREATV_DB_URL=sqlite:////tmp/cobros_copia.db /Users/colorado/Documents/GitHub/iaplusyou/venv/bin/alembic upgrade head && CREATV_DB_URL=sqlite:////tmp/cobros_copia.db /Users/colorado/Documents/GitHub/iaplusyou/venv/bin/alembic downgrade 0031 && CREATV_DB_URL=sqlite:////tmp/cobros_copia.db /Users/colorado/Documents/GitHub/iaplusyou/venv/bin/alembic upgrade head` → sin errores (si no hay base local, crea una vacía con `alembic upgrade head` sobre un archivo nuevo). Si existe una prueba que compare `metadata` con las migraciones (busca `alembic` en `tests/`), debe pasar.

- [ ] **Step 6: commit** `git add db.py migrations/versions/0032_cobros.py tests/test_cobros_db.py && git commit -m "Cobros 1/11: tablas del saldo, recargas y eventos de Bold (migración 0032)…"`

---

### Task 2: El libro (`cobros/libro.py`) y sus avisos

**Files:**
- Create: `cobros/__init__.py`, `cobros/libro.py`, `cobros/avisos.py`
- Modify: `notificaciones.py` (agrega a `TIPOS`: `"pieza_no_cobrada"`, `"recarga_acreditada"`, `"saldo_bajo"`; y para admin `"cobro_no_anotado"`, `"recarga_admin"`, `"anulacion_bold"`, `"pago_sin_recarga"` si `avisar_admin` valida tipos)
- Test: `tests/test_cobros_libro.py`

**Interfaces:**
- Consumes: tablas de la Task 1; `db.conectar()`, `db.ahora()`, `db.kv`.
- Produces (firmas exactas que usan las tareas siguientes):
  - `class SaldoInsuficiente(Exception)` con atributos `cliente: str`, `precio: int`, `disponible: int` (milésimas) y método `frase() -> str` (gettext: «Saldo insuficiente: esto cuesta ≈ %(precio)s y tienes %(disponible)s disponibles. Recarga para seguir.», montos con `gastos.formatear(m/1000)`; con precio desconocido, `precio == 1` → «Saldo insuficiente: tienes %(disponible)s disponibles. Recarga para seguir.»).
  - `precio_milesimas(costo_usd: float, margen: float) -> int`
  - `margen_global() -> float`; `guardar_margen_global(valor: float, usuario: str) -> None` (valida 1.0–5.0, `ValueError` si no)
  - `cuenta(cliente: str) -> dict` → `{"cobrar": bool, "margen": float (efectivo), "margen_propio": float|None, "umbral": int}`; sin fila: `{"cobrar": False, "margen": margen_global(), "margen_propio": None, "umbral": 5000}`
  - `configurar(cliente, *, usuario, cobrar=None, margen=SIN_CAMBIO, umbral=None) -> dict` (upsert; `margen=None` vuelve al global; valida rangos; devuelve `cuenta(cliente)`)
  - `cobra(cliente) -> bool`; `margen_precio(cliente) -> float` (margen efectivo si cobra, si no 1.0)
  - `saldo(cliente) -> int`; `reservado(cliente) -> int`; `disponible(cliente) -> int`
  - `exigir(cliente, costo_usd: float|None, job_id: str|None = None) -> int` (precio reservado o 0 si no cobra; lanza `SaldoInsuficiente`)
  - `cobrar_gasto(con, gasto_id: int, cliente: str, usd: float, tipo: str, entregado: bool = True) -> str|None` (devuelve `"cobro"`, `"no_cobrado"`, `"reverso"`, `"recalculado"` o `None`)
  - `revertir_trabajo(cliente: str|None, job_id: str|None, motivo: str = "") -> list[int]` (ids de reversos nuevos; avisa)
  - `acreditar(con, cliente, tipo: str, milesimas: int, concepto: str, *, recarga_id=None, usuario=None, detalle="") -> int` (tipos válidos: `recarga`, `ajuste`, `anulacion`)
  - `en_trabajo(tarea_id, job_id)` (context manager que fija la `ContextVar`)
  - `puede_arrancar(tarea: dict, tipos_que_cobran: set) -> bool`
  - `limpiar_reservas_muertas() -> int`

- [ ] **Step 1: pruebas que fallan** — `tests/test_cobros_libro.py`:

```python
"""Libro de saldo (spec 2026-10-08 §1-§5)."""
import pytest
import sqlalchemy as sa

AHORA = "2026-10-08T10:00:00"


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro
    return libro


def _tarea(db, job_id, estado="en_curso", cliente="acme", tipo="flowplus_video"):
    with db.conectar() as con:
        return con.execute(sa.insert(db.tarea).values(
            cliente=cliente, job_id=job_id, tipo=tipo, payload={}, estado=estado, intentos=0, max_intentos=1,
            prioridad=5, ejecutar_desde=AHORA, creada_en=AHORA, duracion_estimada=60.0, etapas=[])).inserted_primary_key[0]


def _recargar(db, libro, cliente, milesimas):
    with db.conectar() as con:
        libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def test_precio_redondea_hacia_arriba_sin_ruido_de_float(libro):
    assert libro.precio_milesimas(0.01, 1.5) == 15
    assert libro.precio_milesimas(1.0, 1.5) == 1500
    assert libro.precio_milesimas(0.0101, 1.5) == 16
    assert libro.precio_milesimas(0, 1.5) == 0


def test_proyecto_sin_cuenta_no_cobra(libro, base_temporal):
    assert libro.cuenta("acme")["cobrar"] is False
    assert libro.exigir("acme", 99.0, job_id="j") == 0
    with base_temporal.conectar() as con:
        assert libro.cobrar_gasto(con, 1, "acme", 1.0, "video") is None
    assert libro.saldo("acme") == 0


def test_margen_global_y_propio(libro):
    assert libro.margen_global() == 1.5
    libro.guardar_margen_global(1.4, "admin")
    assert libro.cuenta("acme")["margen"] == 1.4
    libro.configurar("acme", usuario="admin", cobrar=True, margen=2.0)
    assert libro.cuenta("acme")["margen"] == 2.0
    libro.configurar("acme", usuario="admin", margen=None)
    assert libro.cuenta("acme")["margen"] == 1.4
    with pytest.raises(ValueError):
        libro.guardar_margen_global(0.5, "admin")


def test_exigir_sin_saldo_lanza_y_no_reserva(libro, base_temporal):
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(libro.SaldoInsuficiente) as e:
        libro.exigir("acme", 1.0, job_id="j1")
    assert e.value.precio == 1500 and e.value.disponible == 0
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(base_temporal.reserva_saldo)).scalar() == 0


def test_reserva_viva_descuenta_y_muerta_no(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 2000)
    assert libro.exigir("acme", 1.0, job_id="j1") == 1500
    _tarea(db, "j1", "pendiente")
    assert libro.disponible("acme") == 500
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", 1.0, job_id="j2")
    with db.conectar() as con:
        con.execute(sa.update(db.tarea).where(db.tarea.c.job_id == "j1").values(estado="hecha"))
    assert libro.disponible("acme") == 2000


def test_segundo_clic_del_mismo_job_no_reserva_dos_veces(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 2000)
    libro.exigir("acme", 1.0, job_id="j1")
    _tarea(db, "j1", "pendiente")
    libro.exigir("acme", 1.0, job_id="j1")
    assert libro.reservado("acme") == 1500


def test_sin_precio_basta_saldo_positivo(libro, base_temporal):
    libro.configurar("acme", usuario="admin", cobrar=True)
    with pytest.raises(libro.SaldoInsuficiente):
        libro.exigir("acme", None)
    _recargar(base_temporal, libro, "acme", 1)
    assert libro.exigir("acme", None) == 1


def test_cobro_con_margen_y_contexto(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(41, "video:9"), db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 1.0, "video") == "cobro"
    with db.conectar() as con:
        m = con.execute(sa.select(db.movimiento_saldo)).one()
    assert (m.tipo, m.milesimas, m.gasto_id, m.job_id, m.tarea_id, m.concepto) == ("cobro", -1500, 5, "video:9", 41, "video")
    assert m.extra["margen"] == 1.5
    assert libro.saldo("acme") == -1500


def test_gasto_corregido_recalcula_con_el_margen_original(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 0.20, "final")
    libro.guardar_margen_global(3.0, "admin")
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 0.40, "final") == "recalculado"
    assert libro.saldo("acme") == -600


def test_no_entregado_escribe_cero(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 1.0, "video", entregado=False) == "no_cobrado"
    with db.conectar() as con:
        m = con.execute(sa.select(db.movimiento_saldo)).one()
    assert (m.tipo, m.milesimas, m.extra["precio"]) == ("no_cobrado", 0, 1500)


def test_revertir_por_job_una_sola_vez(libro, base_temporal, monkeypatch):
    db = base_temporal
    avisos = []
    import cobros.avisos as av
    monkeypatch.setattr(av, "pieza_no_cobrada", lambda cliente, milesimas, concepto: avisos.append(milesimas))
    libro.configurar("acme", usuario="admin", cobrar=True)
    with libro.en_trabajo(1, "video:9"), db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 1.0, "video")
    with libro.en_trabajo(2, "video:9"), db.conectar() as con:
        libro.cobrar_gasto(con, 6, "acme", 0.5, "video")
    assert len(libro.revertir_trabajo("acme", "video:9", "falló")) == 2
    assert libro.revertir_trabajo("acme", "video:9", "falló") == []
    assert libro.saldo("acme") == 0
    assert avisos == [2250]


def test_cobrar_apagado_no_cobra_hacia_atras(libro, base_temporal):
    db = base_temporal
    with db.conectar() as con:
        libro.cobrar_gasto(con, 5, "acme", 1.0, "video")
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        assert libro.cobrar_gasto(con, 5, "acme", 2.0, "video") is None
    assert libro.saldo("acme") == 0


def test_puede_arrancar(libro, base_temporal):
    db = base_temporal
    tipos = {"flowplus_video"}
    t = {"id": 1, "tipo": "flowplus_video", "cliente": "acme", "job_id": "j"}
    assert libro.puede_arrancar(t, tipos) is True              # no cobra
    libro.configurar("acme", usuario="admin", cobrar=True)
    assert libro.puede_arrancar(t, tipos) is False             # saldo 0
    assert libro.puede_arrancar({**t, "tipo": "exp_decidir"}, tipos) is True
    _tarea(db, "j", "hecha")
    assert libro.puede_arrancar(t, tipos) is True              # continuación de una cadena


def test_limpiar_reservas_muertas(libro, base_temporal):
    db = base_temporal
    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(db, libro, "acme", 5000)
    libro.exigir("acme", 1.0, job_id="viva")
    libro.exigir("acme", 1.0, job_id="muerta")
    _tarea(db, "viva", "en_curso")
    assert libro.limpiar_reservas_muertas() == 1
```

- [ ] **Step 2:** `$PY -m pytest -q tests/test_cobros_libro.py` → FAIL (`ModuleNotFoundError: cobros`).

- [ ] **Step 3: implementación.** `cobros/__init__.py`:

```python
"""Cobros: saldo prepagado por proyecto (spec 2026-10-08). Ver .claude/skills/cobros/SKILL.md."""
from cobros.libro import SaldoInsuficiente  # noqa: F401
```

`cobros/libro.py` (completo; respeta el estilo del repo: docstrings en español con el porqué):

```python
"""Libro de saldo por proyecto (spec 2026-10-08 §1-§5). ÚNICO escritor de
cuenta_saldo, movimiento_saldo y reserva_saldo. Montos en milésimas de dólar.

Un proyecto sin fila en cuenta_saldo, o con cobrar = 0, no se toca: todas las
funciones devuelven «no cobra» y no escriben nada."""
import contextlib
import contextvars
import logging
import math

import sqlalchemy as sa
from flask_babel import gettext

import db

log = logging.getLogger(__name__)

MARGEN_DEFECTO = 1.5
MARGEN_MIN, MARGEN_MAX = 1.0, 5.0
UMBRAL_DEFECTO = 5000
CLAVE_MARGEN = "cobros:margen_global"
TIPOS_ACREDITAR = ("recarga", "ajuste", "anulacion")
ESTADOS_VIVOS = ("pendiente", "en_curso")
SIN_CAMBIO = object()

# (tarea_id, job_id) del trabajo del worker que corre en este hilo. Cada hilo
# empieza con el valor por defecto: dos hilos del carril de Crear no se cruzan.
_CONTEXTO = contextvars.ContextVar("cobros_trabajo", default=None)


class SaldoInsuficiente(Exception):
    """El proyecto cobra y no le alcanza el disponible. No se cobró nada."""

    def __init__(self, cliente, precio, disponible):
        super().__init__(f"saldo insuficiente en {cliente}: precio {precio}, disponible {disponible}")
        self.cliente, self.precio, self.disponible = cliente, int(precio), int(disponible)

    def frase(self):
        import gastos  # noqa: PLC0415 — gastos importa este módulo dentro de registrar
        disponible = gastos.formatear(max(self.disponible, 0) / 1000)
        if self.precio <= 1:
            return gettext("Saldo insuficiente: tienes %(disponible)s disponibles. Recarga para seguir.",
                           disponible=disponible)
        return gettext("Saldo insuficiente: esto cuesta ≈ %(precio)s y tienes %(disponible)s disponibles. "
                       "Recarga para seguir.", precio=gastos.formatear(self.precio / 1000), disponible=disponible)


def precio_milesimas(costo_usd, margen):
    """ceil a la milésima; el round(…, 6) quita el ruido del float
    (0.01 × 1.5 × 1000 = 15.000000000000002 no debe subir a 16)."""
    return int(math.ceil(round(float(costo_usd or 0) * float(margen) * 1000, 6)))


@contextlib.contextmanager
def en_trabajo(tarea_id, job_id):
    token = _CONTEXTO.set({"tarea_id": tarea_id, "job_id": job_id})
    try:
        yield
    finally:
        _CONTEXTO.reset(token)


# ------------------------------------------------------------------ cuenta ---

def _margen_global(con):
    valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_MARGEN)).scalar()
    try:
        return float(valor) if valor is not None else MARGEN_DEFECTO
    except (TypeError, ValueError):
        return MARGEN_DEFECTO


def margen_global():
    with db.conectar() as con:
        return _margen_global(con)


def _validar_margen(valor):
    valor = round(float(valor), 2)
    if not MARGEN_MIN <= valor <= MARGEN_MAX:
        raise ValueError(gettext("El margen va de %(min)s a %(max)s.", min=MARGEN_MIN, max=MARGEN_MAX))
    return valor


def guardar_margen_global(valor, usuario):
    valor = _validar_margen(valor)
    with db.conectar() as con:
        fila = {"valor": str(valor), "actualizado_en": db.ahora()}
        if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == CLAVE_MARGEN)).first():
            con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_MARGEN).values(**fila))
        else:
            con.execute(db.kv.insert().values(clave=CLAVE_MARGEN, **fila))
    log.info("margen global → %s (por %s)", valor, usuario)


def _cuenta(con, cliente):
    fila = con.execute(sa.select(db.cuenta_saldo).where(db.cuenta_saldo.c.cliente == cliente)).first()
    glob = _margen_global(con)
    if fila is None:
        return {"cobrar": False, "margen": glob, "margen_propio": None, "umbral": UMBRAL_DEFECTO}
    return {"cobrar": bool(fila.cobrar), "margen": float(fila.margen) if fila.margen is not None else glob,
            "margen_propio": fila.margen, "umbral": int(fila.umbral_aviso)}


def cuenta(cliente):
    with db.conectar() as con:
        return _cuenta(con, cliente)


def cobra(cliente):
    return bool(cliente) and cuenta(cliente)["cobrar"]


def margen_precio(cliente):
    c = cuenta(cliente) if cliente else None
    return c["margen"] if c and c["cobrar"] else 1.0


def configurar(cliente, *, usuario, cobrar=None, margen=SIN_CAMBIO, umbral=None):
    cambios = {"actualizado_en": db.ahora(), "actualizado_por": usuario}
    if cobrar is not None:
        cambios["cobrar"] = bool(cobrar)
    if margen is not SIN_CAMBIO:
        cambios["margen"] = None if margen is None else _validar_margen(margen)
    if umbral is not None:
        umbral = int(umbral)
        if umbral < 0:
            raise ValueError(gettext("El umbral no puede ser negativo."))
        cambios["umbral_aviso"] = umbral
    t = db.cuenta_saldo
    with db.conectar() as con:
        if con.execute(sa.select(t.c.cliente).where(t.c.cliente == cliente)).first():
            con.execute(t.update().where(t.c.cliente == cliente).values(**cambios))
        else:
            con.execute(t.insert().values(cliente=cliente, cobrar=cambios.pop("cobrar", False),
                                          umbral_aviso=cambios.pop("umbral_aviso", UMBRAL_DEFECTO), **cambios))
        return _cuenta(con, cliente)


# ------------------------------------------------------------------- saldo ---

def _saldo(con, cliente):
    m = db.movimiento_saldo
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0))
                           .where(m.c.cliente == cliente)).scalar())


def _vivas(con):
    """Subconsulta: job_ids con una tarea viva."""
    return sa.select(db.tarea.c.job_id).where(db.tarea.c.estado.in_(ESTADOS_VIVOS), db.tarea.c.job_id.isnot(None))


def _reservado(con, cliente):
    r = db.reserva_saldo
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(r.c.milesimas), 0))
                           .where(r.c.cliente == cliente, r.c.job_id.in_(_vivas(con)))).scalar())


def saldo(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente)


def reservado(cliente):
    with db.conectar() as con:
        return _reservado(con, cliente)


def disponible(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente) - _reservado(con, cliente)


# ------------------------------------------------------------ freno previo ---

def exigir(cliente, costo_usd, job_id=None):
    """§4. Lanza SaldoInsuficiente o devuelve lo reservado (0 si no cobra)."""
    if not cliente:
        return 0
    r = db.reserva_saldo
    with db.conectar() as con:
        c = _cuenta(con, cliente)
        if not c["cobrar"]:
            return 0
        precio = precio_milesimas(costo_usd, c["margen"]) if costo_usd is not None else 1
        precio = max(precio, 1)
        if job_id:
            previa = con.execute(sa.select(r.c.milesimas).where(
                r.c.cliente == cliente, r.c.job_id == job_id, r.c.job_id.in_(_vivas(con)))).scalar()
            if previa is not None:
                return int(previa)   # segundo clic del mismo trabajo: ya reservado
        libre = _saldo(con, cliente) - _reservado(con, cliente)
        if libre < precio:
            raise SaldoInsuficiente(cliente, precio, libre)
        if job_id:
            con.execute(r.delete().where(r.c.cliente == cliente, r.c.job_id == job_id))
            con.execute(r.insert().values(cliente=cliente, job_id=job_id, milesimas=precio, creada_en=db.ahora()))
        return precio


def puede_arrancar(tarea, tipos_que_cobran):
    """Respaldo del worker (§5.1): False solo si el tipo cobra, el proyecto
    cobra, no es continuación de una cadena y el saldo es ≤ 0."""
    if tarea.get("tipo") not in tipos_que_cobran or not tarea.get("cliente"):
        return True
    with db.conectar() as con:
        if not _cuenta(con, tarea["cliente"])["cobrar"]:
            return True
        if tarea.get("job_id") and con.execute(sa.select(db.tarea.c.id).where(
                db.tarea.c.job_id == tarea["job_id"], db.tarea.c.estado == "hecha",
                db.tarea.c.id != tarea.get("id")).limit(1)).first():
            return True
        return _saldo(con, tarea["cliente"]) > 0


# ---------------------------------------------------------------- cobrar ---

def _insertar(con, **valores):
    valores.setdefault("creado_en", db.ahora())
    return int(con.execute(db.movimiento_saldo.insert().values(**valores)).inserted_primary_key[0])


def cobrar_gasto(con, gasto_id, cliente, usd, tipo, entregado=True):
    """§3.1. Corre DENTRO de la transacción de gastos.registrar (en su propio
    savepoint, que abre gastos). Devuelve qué escribió."""
    m = db.movimiento_saldo
    previo = con.execute(sa.select(m).where(m.c.gasto_id == gasto_id, m.c.tipo.in_(("cobro", "no_cobrado")))).first()
    if previo is not None:
        if previo.tipo != "cobro":
            return None
        margen = float((previo.extra or {}).get("margen") or MARGEN_DEFECTO)
        nuevo = precio_milesimas(usd, margen)
        con.execute(m.update().where(m.c.id == previo.id).values(milesimas=-nuevo))
        reverso = con.execute(sa.select(m.c.id).where(m.c.gasto_id == gasto_id, m.c.tipo == "reverso")).first()
        if reverso is not None:
            con.execute(m.update().where(m.c.id == reverso.id).values(milesimas=nuevo))
            return "recalculado"
        if not entregado:
            _insertar(con, cliente=cliente, tipo="reverso", milesimas=nuevo, gasto_id=gasto_id, job_id=previo.job_id,
                      tarea_id=previo.tarea_id, concepto=previo.concepto, detalle="no entregado", extra={})
            return "reverso"
        return "recalculado"
    c = _cuenta(con, cliente)
    if not c["cobrar"]:
        return None
    precio = precio_milesimas(usd, c["margen"])
    ctx = _CONTEXTO.get() or {}
    comunes = dict(cliente=cliente, gasto_id=gasto_id, job_id=ctx.get("job_id"), tarea_id=ctx.get("tarea_id"),
                   concepto=str(tipo or "otro")[:120])
    if not entregado:
        _insertar(con, tipo="no_cobrado", milesimas=0, extra={"margen": c["margen"], "precio": precio}, **comunes)
        return "no_cobrado"
    _insertar(con, tipo="cobro", milesimas=-precio, extra={"margen": c["margen"]}, **comunes)
    return "cobro"


def revertir_trabajo(cliente, job_id, motivo=""):
    """§3.5: un reverso por cada cobro del job_id que no lo tenga. Avisa una
    vez con el total. Nunca lanza (lo llama el worker)."""
    if not cliente or not job_id:
        return []
    m = db.movimiento_saldo
    nuevos, total, concepto = [], 0, None
    try:
        with db.conectar() as con:
            cobros_ = con.execute(sa.select(m).where(m.c.cliente == cliente, m.c.job_id == job_id,
                                                     m.c.tipo == "cobro")).all()
            for c in cobros_:
                if con.execute(sa.select(m.c.id).where(m.c.gasto_id == c.gasto_id, m.c.tipo == "reverso")).first():
                    continue
                try:
                    with con.begin_nested():
                        nuevos.append(_insertar(con, cliente=cliente, tipo="reverso", milesimas=-c.milesimas,
                                                gasto_id=c.gasto_id, job_id=job_id, tarea_id=c.tarea_id,
                                                concepto=c.concepto, detalle=str(motivo or "")[:300], extra={}))
                        total += -c.milesimas
                        concepto = concepto or c.concepto
                except sa.exc.IntegrityError:
                    continue
    except Exception:  # noqa: BLE001 — el worker no muere por esto
        log.exception("no se pudo revertir el trabajo %s de %s", job_id, cliente)
        return nuevos
    if nuevos:
        from cobros import avisos  # noqa: PLC0415
        avisos.pieza_no_cobrada(cliente, total, concepto)
    return nuevos


def acreditar(con, cliente, tipo, milesimas, concepto, *, recarga_id=None, usuario=None, detalle=""):
    """Recarga (+), ajuste (±) o anulación (−). Lo llaman cobros.recargas y
    las pruebas, dentro de su propia transacción."""
    if tipo not in TIPOS_ACREDITAR:
        raise ValueError(f"tipo de acreditación inválido: {tipo}")
    return _insertar(con, cliente=cliente, tipo=tipo, milesimas=int(milesimas), recarga_id=recarga_id,
                     concepto=concepto, usuario=usuario, detalle=str(detalle or "")[:300], extra={})


def limpiar_reservas_muertas():
    r = db.reserva_saldo
    with db.conectar() as con:
        return con.execute(r.delete().where(r.c.job_id.notin_(_vivas(con)))).rowcount
```

`cobros/avisos.py`: funciones que nunca lanzan, cada una arma asunto y cuerpo con `gettext` dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` y llama a `notificaciones.avisar(cliente, tipo, asunto, cuerpo)` / `notificaciones.avisar_admin(tipo, asunto, cuerpo, cliente=cliente)`:
  - `pieza_no_cobrada(cliente, milesimas, concepto)` — «Una pieza falló y no se te cobró» / «%(concepto)s no llegó. No descontamos %(monto)s de tu saldo.» (`concepto` traducido con `cobros.vista.nombre_concepto` si ya existe; si no, el código tal cual — la Task 8 lo completa).
  - `recarga_acreditada(cliente, milesimas, medio)` (cliente) + `recarga_admin(cliente, milesimas, medio)` (admin).
  - `saldo_bajo(cliente, saldo_milesimas)`: solo si `kv` `cobros:aviso_bajo:<cliente>` no existe; lo crea. `limpiar_aviso_bajo(cliente)` lo borra (la llama la acreditación de una recarga).
  - `admin(tipo, asunto, cuerpo, cliente="")` genérico para `cobro_no_anotado`, `anulacion_bold`, `pago_sin_recarga`.

- [ ] **Step 4:** `$PY -m pytest -q tests/test_cobros_libro.py` → PASS.
- [ ] **Step 5: commit** «Cobros 2/11: el libro de saldo (cuenta, margen, reservas, cobro, reverso, acreditación) y sus avisos».

---

### Task 3: El cobro en la puerta del costo (`gastos.registrar`)

**Files:**
- Modify: `gastos.py` (`registrar`, `registrar_seguro`, ~líneas 353-409)
- Modify: los llamadores que anotan «pagado aunque falló» (lista abajo)
- Test: `tests/test_cobros_gastos.py`

**Interfaces:**
- Consumes: `cobros.libro.cobrar_gasto(con, gasto_id, cliente, usd, tipo, entregado)`, `cobros.avisos.pieza_no_cobrada`, `cobros.avisos.admin`, `cobros.avisos.saldo_bajo`.
- Produces: `gastos.registrar(..., entregado=True)` y `gastos.registrar_seguro(..., entregado=True)`.

- [ ] **Step 1: pruebas que fallan**

```python
# tests/test_cobros_gastos.py
"""El cobro se escribe en la misma puerta que el costo (spec §3)."""
import sqlalchemy as sa


def _movs(db):
    with db.conectar() as con:
        return con.execute(sa.select(db.movimiento_saldo).order_by(db.movimiento_saldo.c.id)).all()


def test_registrar_cobra_si_el_proyecto_cobra(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    (m,) = _movs(base_temporal)
    assert (m.tipo, m.milesimas, m.gasto_id) == ("cobro", -1500, gid)


def test_registrar_no_toca_un_proyecto_que_no_cobra(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1.0, "video:1:t1")
    assert _movs(base_temporal) == []


def test_corregir_el_monto_recalcula_el_cobro(base_temporal):
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar("acme", "final", 0.2, "final:1:t1")
    gastos.registrar("acme", "final", 0.4, "final:1:t1")
    assert [m.milesimas for m in _movs(base_temporal)] == [-600]


def test_entregado_false_no_cobra_y_avisa(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    vistos = []
    monkeypatch.setattr(avisos, "pieza_no_cobrada", lambda c, m, k: vistos.append((c, m, k)))
    libro.configurar("acme", usuario="admin", cobrar=True)
    gastos.registrar_seguro("acme", "video", 1.0, "video:1:t1", entregado=False)
    (m,) = _movs(base_temporal)
    assert (m.tipo, m.milesimas) == ("no_cobrado", 0)
    assert vistos == [("acme", 1500, "video")]


def test_si_el_cobro_falla_el_gasto_queda(base_temporal, monkeypatch):
    import gastos
    from cobros import avisos, libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(libro, "cobrar_gasto", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    admin = []
    monkeypatch.setattr(avisos, "admin", lambda *a, **k: admin.append(a))
    gid = gastos.registrar("acme", "video", 1.0, "video:1:t1")
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(base_temporal.gasto.c.usd).where(base_temporal.gasto.c.id == gid)).scalar() == 1.0
    assert admin
```

- [ ] **Step 2:** `$PY -m pytest -q tests/test_cobros_gastos.py` → FAIL.

- [ ] **Step 3: implementación en `gastos.registrar`.** Reorganiza el cuerpo para que, dentro del mismo `with db.conectar() as con:`, el upsert actual deje el id en `gasto_id` (sin `return` temprano) y después:

```python
        usd_final = con.execute(sa.select(g.c.usd).where(g.c.id == gasto_id)).scalar()
        resultado_cobro = None
        try:
            with con.begin_nested():
                from cobros import libro as _libro  # noqa: PLC0415 — evita el import circular
                resultado_cobro = _libro.cobrar_gasto(con, gasto_id, cliente, usd_final, tipo, entregado=entregado)
        except Exception:  # noqa: BLE001 — el costo no se pierde por el cobro (spec §3.1)
            log.exception("No se pudo anotar el cobro del gasto %s de %s", referencia, cliente)
            resultado_cobro = "error"
    _despues_del_cobro(cliente, resultado_cobro, usd_final, tipo, referencia)
    return gasto_id
```

y la función nueva (fuera de la transacción, nunca lanza):

```python
def _despues_del_cobro(cliente, resultado, usd, tipo, referencia):
    """Avisos del cobro, ya con la transacción confirmada (spec §3.6, §8)."""
    try:
        from cobros import avisos, libro  # noqa: PLC0415
        if resultado == "error":
            avisos.admin("cobro_no_anotado", gettext("No se pudo anotar un cobro"),
                         gettext("El gasto %(ref)s de %(cliente)s (US$ %(usd)s) quedó sin su cobro al cliente.",
                                 ref=referencia, cliente=cliente, usd=usd), cliente=cliente)
        elif resultado in ("no_cobrado", "reverso"):
            avisos.pieza_no_cobrada(cliente, libro.precio_milesimas(usd, libro.cuenta(cliente)["margen"]), tipo)
        elif resultado == "cobro":
            c = libro.cuenta(cliente)
            s = libro.saldo(cliente)
            if s < c["umbral"]:
                avisos.saldo_bajo(cliente, s)
    except Exception:  # noqa: BLE001
        log.exception("aviso del cobro de %s falló", referencia)
```

Agrega `entregado=True` a la firma de `registrar` (último parámetro con nombre) y documenta en el docstring: «`entregado=False`: el proveedor cobró pero la pieza no llegó; el costo se anota igual y al cliente no se le cobra (spec §3.4)». `registrar_seguro` ya pasa `**kw`, no cambia de firma pero su docstring lo menciona.

- [ ] **Step 4: los llamadores «pagado pero no entregado».** Busca con `grep -n "registrar_seguro\|gastos.registrar(" -r --include=*.py . | grep -v tests/` y abre cada uno. Marca `entregado=False` en los que anotan un cobro **en una rama de fallo** (la pieza no llegó a la persona): como mínimo revisa `tareas/flowplus.py` (líneas ~646 y ~692: video pagado y perdido / recuperación fallida), `tareas/cadena.py:208`, `tareas/swap.py:442`, `tareas/hablado.py`, `tareas/musica.py`, `final_edition/__init__.py` (424/448/856). No marques un cobro de la rama de éxito. Escribe en el mensaje del commit la lista de los que marcaste y por qué. Si una rama de fallo no se puede distinguir sin rediseñar, no la toques y anótala en el commit (la Task 4 cubre igual el caso «la tarea entera termina en error»).

- [ ] **Step 5:** `$PY -m pytest -q tests/test_cobros_gastos.py tests/test_cobros_libro.py tests/test_estimar.py tests/test_admin.py` y luego `$PY -m pytest -q -m "not slow"` → todo PASS (proyectos que no cobran no cambian).
- [ ] **Step 6: commit** «Cobros 3/11: el cobro al cliente en la misma puerta que el costo; pagado pero no entregado no se cobra».

---

### Task 4: Worker — contexto, reversión y respaldo; `TIPOS_QUE_COBRAN`

**Files:**
- Modify: `cola.py` (`fallar`, nueva `viva`)
- Modify: `worker.py` (`ejecutar`/`_correr`, `recuperar_interrumpidas`, `_terminar_y_encolar`)
- Modify: `tareas/__init__.py` (conjuntos nuevos)
- Test: `tests/test_cobros_worker.py`

**Interfaces:**
- Consumes: `cobros.libro.en_trabajo`, `revertir_trabajo`, `puede_arrancar`.
- Produces:
  - `cola.fallar(tarea_id, error, definitivo=False) -> str|None` (devuelve `"error"` o `"pendiente"`; `definitivo=True` marca `error` aunque queden intentos).
  - `cola.viva(job_id) -> bool`.
  - `tareas.TIPOS_QUE_COBRAN: frozenset[str]` y `tareas.TIPOS_EXENTOS_DE_COBRO: dict[str, str]` (tipo → motivo).
  - Mensaje del respaldo: `worker.MENSAJE_SIN_SALDO = idiomas.N_("Sin saldo: recarga para seguir. No se cobró nada.")`.

- [ ] **Step 1: pruebas que fallan** — `tests/test_cobros_worker.py`. Usa el patrón de `tests/test_cola.py` / `tests/test_crear_sin_cola.py` para insertar tareas y correr `worker._correr(tarea)` con un tipo falso registrado vía `monkeypatch.setitem(tareas.REGISTRO, "falsa_cobra", fn)` y `monkeypatch.setattr(tareas, "TIPOS_QUE_COBRAN", frozenset({"falsa_cobra"}))`:
  1. `test_error_definitivo_revierte_los_cobros_del_job`: una tarea `falsa_cobra` (`max_intentos=1`) cuya función llama a `gastos.registrar("acme","video",1.0,"video:1:t<id>")` y luego lanza `RuntimeError`; tras `_correr`, `libro.saldo("acme") == 0` (cobro −1500 + reverso +1500) y el reverso tiene el mismo `job_id`.
  2. `test_cadena_que_falla_al_final_revierte_toda_la_cadena`: la tarea 1 registra un gasto y devuelve `tareas.Continuar("falsa_cobra", {"paso": 2})`; la 2 (mismo job_id) lanza; tras correr ambas, saldo vuelve al de antes.
  3. `test_fallo_con_intentos_no_revierte`: `max_intentos=2`, primer fallo → la tarea vuelve a `pendiente` y el cobro sigue sin reverso.
  4. `test_respaldo_sin_saldo_no_llama_al_proveedor`: proyecto que cobra con saldo 0; la función de la tarea pone una bandera; tras `_correr`, la bandera no se puso, la tarea está en `error` con el mensaje del respaldo y el gancho `AL_INTERRUMPIR` registrado para el tipo se llamó.
  5. `test_contexto_no_se_cruza_entre_hilos`: dos hilos corren `_correr` de dos tareas de distinto job_id a la vez (cada función registra un gasto tras un `threading.Barrier(2)`); cada cobro queda con su propio `job_id` y `tarea_id`.
  6. `test_interrumpida_por_reinicio_revierte`: una tarea `en_curso` con `max_intentos` agotado y un cobro de su job_id; `worker.recuperar_interrumpidas(0)` deja el saldo en 0.
  7. `test_todo_tipo_que_registra_gasto_esta_clasificado`: para cada `tipo, fn` de `tareas.REGISTRO` (cárgalo con `tareas.cargar()` o como lo haga `worker.main`), si el código fuente del módulo de `fn` (`inspect.getsource(inspect.getmodule(fn))`) contiene `registrar_seguro` o `gastos.registrar`, el tipo debe estar en `TIPOS_QUE_COBRAN` o en `TIPOS_EXENTOS_DE_COBRO`; y ningún tipo puede estar en los dos.

- [ ] **Step 2:** `$PY -m pytest -q tests/test_cobros_worker.py` → FAIL.

- [ ] **Step 3: `cola.fallar`** devuelve el estado final y acepta `definitivo`:

```python
def fallar(tarea_id, error, definitivo=False):
    """… Devuelve "pendiente" (se reintenta), "error" (fallo definitivo) o None."""
    with db.conectar() as con:
        fila = …
        if not fila:
            return None
        if fila.intentos < fila.max_intentos and not definitivo:
            … (igual que hoy)
            return "pendiente"
        … (igual que hoy)
        return "error"


def viva(job_id):
    """True si hay una tarea pendiente o en curso con ese job_id."""
    if not job_id:
        return False
    with db.conectar() as con:
        return con.execute(sa.select(db.tarea.c.id).where(
            db.tarea.c.job_id == job_id, db.tarea.c.estado.in_(("pendiente", "en_curso"))).limit(1)).first() is not None
```

- [ ] **Step 4: `worker.py`.**
  - En `_correr`, antes de `ejecutar(tarea)`:

```python
    if not libro.puede_arrancar(tarea, tareas.TIPOS_QUE_COBRAN):
        with idiomas.en_idioma(idiomas.de_tarea(tarea)):
            mensaje = gettext(MENSAJE_SIN_SALDO)
        cola.fallar(tarea["id"], mensaje, definitivo=True)
        hook = tareas.AL_INTERRUMPIR.get(tarea["tipo"])
        if hook is not None:
            try:
                with idiomas.en_idioma(idiomas.de_tarea(tarea)):
                    hook(tarea, mensaje)
            except Exception as e:  # noqa: BLE001
                log.error("tarea %s sin saldo: el gancho de %s falló: %s", tarea["id"], tarea["tipo"], cola.sin_token(e))
        log.info("tarea %s %s: proyecto sin saldo, no corre", tarea["id"], tarea["tipo"])
        return
```

  - La llamada a `ejecutar(tarea)` va dentro de `with libro.en_trabajo(tarea["id"], tarea["job_id"]):`.
  - En la rama `except Exception` de `_correr`: `if cola.fallar(...) == "error": libro.revertir_trabajo(tarea.get("cliente"), tarea.get("job_id"), gettext-del-proyecto(«La tarea falló»))`.
  - En `recuperar_interrumpidas`: por cada `t` de `interrumpidas`, `libro.revertir_trabajo(t.get("cliente"), t.get("job_id"), …)` (aunque no tenga gancho).
  - En `_terminar_y_encolar`, después del `cola.fallar(...)`: `libro.revertir_trabajo(...)`.
  - Import `from cobros import libro` arriba.

- [ ] **Step 5: `tareas/__init__.py`.** Debajo de `REGISTRO`:

```python
# Cobros (spec 2026-10-08 §5.1): tipos que llaman a un proveedor que cobra. Si
# el proyecto cobra, trabajos.encolar exige saldo antes de encolarlos y el
# worker no los arranca con saldo ≤ 0. tests/test_cobros_worker.py falla si un
# tipo que registra gasto no está aquí ni en los exentos.
TIPOS_QUE_COBRAN = frozenset({...})
TIPOS_EXENTOS_DE_COBRO = {
    "flowplus_recuperar": "recupera un video ya pagado; no paga de nuevo",
    ...
}
```

Llénalos recorriendo cada módulo de `tareas/` (y los tipos que registra cada uno en `REGISTRO`): cobra = su ejecución puede llamar a WaveSpeed, fal, Anthropic, Apify, Atria o TrendTrack. Exento solo con motivo (periódicas de sincronización sin proveedor que cobra, `exp_decidir`, `edicion_producir`, `flowplus_recuperar`, publicadores de Meta…). La prueba 7 te dice si te falta uno.

- [ ] **Step 6:** `$PY -m pytest -q tests/test_cobros_worker.py tests/test_cola.py tests/test_crear_sin_cola.py` y la suite rápida → PASS.
- [ ] **Step 7: commit** «Cobros 4/11: el worker revierte por trabajo al fallar, no arranca sin saldo y lleva el contexto del cobro».

---

### Task 5: El freno antes de cobrar (encolar, rutas sincrónicas y el rechazo)

**Files:**
- Modify: `trabajos.py` (`encolar`)
- Modify: `dashboard.py` (manejador de error)
- Modify: cada ruta de la tabla de abajo
- Test: `tests/test_cobros_freno.py`

**Interfaces:**
- Consumes: `cobros.libro.exigir`, `cobros.SaldoInsuficiente`, `cola.viva`, `tareas.TIPOS_QUE_COBRAN`.
- Produces: `trabajos.encolar(job_id, tipo, payload, …, costo_estimado=None) -> bool`; respuesta 402 JSON `{"ok": False, "error": str, "saldo_insuficiente": True, "recargar_url": str}`.
- `recargar_url` = `url_for("ver_cliente", cliente=c) + "#config-ap-saldo"` (la sección que crea la Task 8; el ancla existe aunque la sección aún no).

- [ ] **Step 1: pruebas que fallan** — `tests/test_cobros_freno.py`:
  1. `trabajos.encolar("j1","flowplus_video",{},cliente="acme",costo_estimado=1.0, max_intentos=1)` con proyecto que cobra y saldo 0 → `pytest.raises(SaldoInsuficiente)` y **ninguna** fila en `tarea`.
  2. Con saldo 2 000: devuelve True, hay reserva de 1 500; segundo `encolar` del mismo job_id → False y la reserva sigue en 1 500.
  3. Tipo exento (`flowplus_recuperar`) con saldo 0 → encola sin error.
  4. Proyecto que no cobra, saldo 0 → encola como hoy.
  5. Con el cliente de pruebas de Flask (patrón de `tests/test_crear_sin_cola.py` o `tests/test_crear_compositor.py`, sesión `user_acme`): POST a la ruta de Crear (`cf_crear_video`) con cabecera `X-Requested-With: fetch` en un proyecto que cobra sin saldo → status 402, JSON con `saldo_insuficiente: True` y el texto «Saldo insuficiente»; no se encoló nada. Sin la cabecera (formulario) → 302 y un flash con la frase.
  6. Una ruta sincrónica (elige `referentes/rutas.py` «Adaptar» o el refinador de Flow Plus) en un proyecto sin saldo → 402/flash y el proveedor falso (monkeypatch del cliente de Anthropic que use esa ruta) **no** se llamó.

- [ ] **Step 2:** FAIL.

- [ ] **Step 3: `trabajos.encolar`:**

```python
def encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None, max_intentos=5, prioridad=5,
            costo_estimado=None):
    """… `costo_estimado` (USD, costo del proveedor sin margen; None si no se
    sabe): si el tipo cobra y el proyecto cobra, se exige y se reserva saldo
    antes de encolar (spec 2026-10-08 §4-§5); lanza cobros.SaldoInsuficiente
    sin encolar nada. Un job_id ya vivo no exige: el clic repetido no hace nada."""
    import tareas  # noqa: PLC0415
    from cobros import libro  # noqa: PLC0415
    if job_id and cola.viva(job_id):
        return False
    if tipo in tareas.TIPOS_QUE_COBRAN:
        libro.exigir(cliente, costo_estimado, job_id=job_id)
    tid = cola.encolar(…igual que hoy…)
    return tid is not None
```

(Si `import tareas` desde `trabajos` crea un ciclo, mueve `TIPOS_QUE_COBRAN` a un módulo sin dependencias, p. ej. `tareas/tipos_cobro.py`, e impórtalo desde `tareas/__init__.py` y desde aquí; ajusta la prueba 7 de la Task 4.)

- [ ] **Step 4: manejador en `dashboard.py`** (junto a los otros `errorhandler`):

```python
@app.errorhandler(cobros.SaldoInsuficiente)
def _saldo_insuficiente(e):
    """Spec 2026-10-08 §5.4: un solo lugar para el rechazo por saldo."""
    recargar = url_for("ver_cliente", cliente=e.cliente) + "#config-ap-saldo"
    frase = e.frase()
    if _quiere_json() or request.is_json or request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": False, "error": frase, "saldo_insuficiente": True, "recargar_url": recargar}), 402
    flash(frase, "error")
    destino = request.referrer if request.referrer and urlparse(request.referrer).netloc == request.host else recargar
    return redirect(destino)
```

(Usa el `_quiere_json` que ya existe; importa `urlparse` si falta.) Verifica que el JS común de los formularios fetch (busca dónde se pinta `data.error` en `static/`) muestre el `error` de una respuesta 402 igual que el de una 400; si trata solo `res.ok`, que lea el JSON también en 402.

- [ ] **Step 5: rutas que encolan.** En cada una, pasa a `trabajos.encolar(..., costo_estimado=<el usd del estimado que ya calcula para mostrar>)`. Si la ruta envuelve el encolar en `except Exception`, agrega antes `except SaldoInsuficiente: raise`. Lista (del reconocimiento; confirma cada línea):

| Ruta | archivo:línea aprox. | estimado |
|---|---|---|
| `cf_crear_video` (vía `flowplus_lanzar.lanzar`) | `dashboard.py:7788`, `flowplus_lanzar.py` | `gastos.estimar("video"/"imagen", …)["usd"]` |
| recrear de referentes | `referentes/rutas.py:405` | ídem |
| `final_guion` | `dashboard.py:7147` | `gastos.estimar("guion")` |
| `final_producir` | `dashboard.py:7186` | `gastos.estimar("final", paises=n)` |
| Mi música | `dashboard.py:7485` | `gastos.estimar("musica_elevenlabs")` |
| Audios | `dashboard.py:7530` | el que calcula la ruta |
| voces diseñar/clonar | `dashboard.py:7635/7649` | `voz_disenada` / `voz_clonada` |
| Anuncio hablado | `hablado_rutas.py:106` | `hablado_voz` + el del video |
| Experimentos lanzar | `dashboard.py:5431` | suma de sus estimados |
| editor transcribir / voz | `final_edition/rutas_editor.py:314/404` | `transcripcion` / `voz_editor` |
| Sprints sugerir / reescribir / ideas / lote / QA | `sprints/rutas.py:1060/1276` y los `tareas_sprints.encolar_*` | sus estimados |
| Referentes traer / clasificar | `referentes/rutas.py:171/607` | `recoleccion` / `clasificacion` |
| Flow Plus cadena / pipeline / imágenes | `guiones/rutas_pipeline.py:574` y vecinas | `guion_clips` / imagen |
| Nicho investigación / estudios / avatares | `nicho/rutas.py:679` y vecinas | sus estimados |
| Triple Whale evaluar | `triple_whale/rutas.py:100` | `evaluacion_tw` |

Los helpers `encolar_*` de `tareas/*.py` que llaman a `trabajos.encolar` reciben y pasan `costo_estimado`. Busca TODOS los llamadores con `grep -rn "trabajos.encolar(" --include=*.py . | grep -v tests/`; cualquier tipo de `TIPOS_QUE_COBRAN` encolado sin `costo_estimado` queda con el freno mínimo (saldo positivo), que es aceptable, pero pásalo donde la ruta ya lo tenga.

- [ ] **Step 6: rutas que cobran en la petición.** Al inicio de cada una, antes de llamar al proveedor: `libro.exigir(cliente, <costo estimado o None>)` (sin job_id). Lista del spec §5.2: `organico.py:563`, `audios.py:260/404`, `voces_propias.py:294/302/357`, `final_edition/__init__.py:424/448/856`, `referentes/rutas.py:328/392/399`, `guiones/refinador.py:519`, `importador.py:563`, el llamador de tipo `otro` en `dashboard.py` (~7986), `referentes/traducir.py:65`. Para cada uno averigua si corre en una petición o dentro del worker; si corre dentro del worker, NO pongas `exigir` (lo cubre la Task 4) y anótalo en el commit. Las que corren en la petición: el `exigir` va en la ruta (o en la función que la ruta llama, antes del proveedor), con el `cliente` real del proyecto.

- [ ] **Step 7:** pruebas nuevas + suite rápida → PASS.
- [ ] **Step 8: commit** «Cobros 5/11: sin saldo no se encola ni se llama al proveedor; un solo rechazo 402/flash».

---

### Task 6: Los precios que se ven

**Files:**
- Modify: `gastos.py` (`_estimado`, nuevas `texto_precio`, `margen_vigente`)
- Modify: `dashboard.py` (`before_request` que fija `g.margen_precio`; filtro Jinja `precio`)
- Modify: `templates/_tab_creativeflowplus.html`, `templates/_crear_audios.html`, `templates/_hablado_panel.html`, `templates/_crear_detalle.html` y toda plantilla con `data-usd*` o tarifa visible
- Test: `tests/test_cobros_precios.py`

**Interfaces:**
- Produces: `gastos.margen_vigente() -> float` (lee `flask.g.margen_precio` si hay contexto de petición; si no, 1.0); `gastos.texto_precio(usd) -> str` (el texto de hoy con `usd × margen_vigente()`); `_estimado` agrega `"usd_precio"`; filtro Jinja `precio` (`{{ x|precio }}` → float `x × g.margen_precio`, sin formatear).

- [ ] **Step 1: pruebas que fallan** — `tests/test_cobros_precios.py`:
  1. Dentro de `app.test_request_context("/cliente/acme")` con `g.margen_precio = 1.5`: `gastos.estimar("guion")["usd"] == gastos.TARIFAS["guion"]` y `["texto"]` contiene la cifra de `0.13*1.5` formateada; `["usd_precio"] == round(0.13*1.5, 4)`.
  2. Fuera de petición: `texto` sin margen.
  3. **Humo obligatorio (§6):** proyecto `acme` que cobra con margen 1,5; sesión `user_acme`; GET `/cliente/acme` → el HTML contiene `data-usd-seg="<usd_por_segundo_efectivo×1.5>"` para un modelo conocido de `flowplus_modelos` y NO contiene el valor sin margen en ese atributo; y el «≈» del guion muestra el precio. Con `acme` sin cobrar: los valores de hoy.

- [ ] **Step 2:** FAIL.

- [ ] **Step 3:** en `gastos.py`:

```python
def margen_vigente():
    """Margen de precio de la petición en curso (spec §6): lo fija un
    before_request de dashboard a partir del <cliente> de la URL. Fuera de una
    petición, o en un proyecto que no cobra, 1.0."""
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        return float(getattr(g, "margen_precio", 1.0)) if has_request_context() else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def texto_precio(usd):
    return _texto_estimado(None if usd is None else round(float(usd) * margen_vigente(), 4))


def _estimado(usd, detalle=""):
    usd = None if usd is None else round(float(usd), 4)
    margen = margen_vigente()
    return {"usd": usd, "usd_precio": None if usd is None else round(usd * margen, 4),
            "texto": texto_precio(usd), "detalle": detalle}
```

En `dashboard.py`:

```python
@app.before_request
def _margen_de_precio():
    """Spec 2026-10-08 §6: en un proyecto que cobra, todo «≈ US$» es precio."""
    cliente = request.view_args.get("cliente") if request.view_args else None
    if not cliente:
        s = _sesion()
        cliente = s["cliente"] if s and s["rol"] == "cliente" else None
    g.margen_precio = libro.margen_precio(cliente) if cliente else 1.0


@app.template_filter("precio")
def _filtro_precio(usd):
    try:
        return round(float(usd) * float(getattr(g, "margen_precio", 1.0)), 6)
    except (TypeError, ValueError):
        return usd
```

(Regístralo después de `_guard_por_cliente` para no leer la base de un pedido que va a ser rechazado; si la lectura de `cuenta` por petición pesa, memorízala con el patrón de «lecturas memorizadas por petición» de la skill `escala-y-salud`.)

- [ ] **Step 4: plantillas.** `grep -rn "data-usd\|usd_por_segundo\|\.usd }}\|\"%.3f\"|format(m.usd" templates/` y aplica `|precio` a cada valor en dólares que termine en un atributo `data-*` o en una tarifa visible (p. ej. `data-usd-seg="{{ m.usd_por_segundo_efectivo|precio }}"`, `${{ "%.3f"|format(m.usd_por_segundo_efectivo|precio) }}/s`, `data-recargo="{{ m.audio_nativo.recargo_usd_s|precio }}"`, `data-usd-borrador="{{ tarifas_flowplus_borrador[id]|precio }}"`, `data-usd-caracter="{{ usd_por_caracter|precio }}"`, `data-usd="{{ item.costo_estimado.usd|precio if item.costo_estimado else '' }}"`). Busca también en `static/*.js` cifras en dólares que no vengan de un `data-*` (constantes de tarifa quemadas) y, si las hay, pásalas a un `data-*` con `|precio`. Ningún cambio de lógica en el JS.

- [ ] **Step 5:** pruebas → PASS; suite rápida → PASS.
- [ ] **Step 6: commit** «Cobros 6/11: en un proyecto que cobra, todo precio que se ve lleva el margen».

---

### Task 7: Bold: cliente HTTP, recargas, webhook y verificación

**Files:**
- Create: `cobros/bold.py`, `cobros/recargas.py`, `cobros/rutas.py` (Blueprint `cobros`, con las rutas de recarga y el webhook), `tareas/cobros.py`
- Modify: `dashboard.py` (registrar el Blueprint; exenciones del webhook en `_solo_mismo_origen` y `ENDPOINTS_SIN_GUARD_SESION`), `worker.py` (`PERIODICAS` += `("cobros_verificar_recargas", 600)`), `tareas/__init__.py` (importa `tareas.cobros`; el tipo va a `TIPOS_EXENTOS_DE_COBRO` con motivo «consulta a Bold, no cobra»), la tarea de mantenimiento diario (`tareas/mantenimiento.py`: llama a `libro.limpiar_reservas_muertas()`), `.env.example` (`BOLD_LLAVE_IDENTIDAD=`, `BOLD_LLAVE_SECRETA=`, `BOLD_PRUEBAS=` con comentario)
- Test: `tests/test_cobros_bold.py`, `tests/test_cobros_recargas.py`

**Interfaces:**
- Consumes: `cobros.libro.acreditar`, `cobros.avisos.*`, `db.recarga`, `db.pago_evento`.
- Produces:
  - `bold.configurado() -> bool`; `bold.crear_link(*, referencia: str, usd: int, descripcion: str, callback_url: str, correo: str|None = None, horas: int = 24) -> {"link_id": str, "url": str}`; `bold.estado_link(link_id: str) -> {"status": str, "transaction_id": str|None, "total": int|None}`; `bold.firma_valida(cuerpo: bytes, firma: str|None) -> bool`; `class bold.ErrorBold(Exception)` (mensaje en palabras, sin llaves).
  - `recargas.MIN_USD = 10`, `recargas.MAX_USD = 1000`; `recargas.crear(cliente, usd, usuario, correo=None) -> {"id": int, "url": str}` (lanza `ValueError` monto inválido, `bold.ErrorBold`); `recargas.procesar_webhook(cuerpo: bytes, firma: str|None) -> tuple[int, str]` (status HTTP, resultado); `recargas.verificar(recarga_id) -> str` (estado final); `recargas.verificar_pendientes() -> int`; `recargas.manual(cliente, usd: float, usuario, nota, tipo="recarga") -> int` (id del movimiento); `recargas.obtener(cliente, recarga_id) -> dict|None`; `recargas.de_proyecto(cliente, limite=20) -> list[dict]`.
  - Rutas: `POST /cliente/<cliente>/saldo/recargar` (`cobros.recargar`), `GET /cliente/<cliente>/saldo/recarga/<int:rid>` (`cobros.recarga_vuelta`), `GET /cliente/<cliente>/saldo/recarga/<int:rid>/estado` (`cobros.recarga_estado`, JSON `{"estado": str, "texto": str, "saldo_texto": str}`), `POST /cliente/<cliente>/saldo/recarga/<int:rid>/verificar` (`cobros.recarga_verificar`), `POST /pagos/bold/webhook` (`cobros.bold_webhook`).

- [ ] **Step 1: pruebas de `bold.py`** (`tests/test_cobros_bold.py`), con `requests` falso vía `monkeypatch.setattr(bold.requests, "post"/"get", …)`:
  1. `crear_link` manda a `https://integrations.api.bold.co/online/link/v1` la cabecera `Authorization: x-api-key <llave>` y el cuerpo `{"amount_type": "CLOSE", "amount": {"currency": "USD", "total_amount": 50, "tip_amount": 0, "taxes": []}, "reference": "cv-1-1", "description": …, "callback_url": …, "expiration_date": <int nanosegundos>}` (+ `payer_email` si hay correo); devuelve `link_id`/`url` del `payload`.
  2. Respuesta 4xx/5xx → `ErrorBold` cuyo texto no contiene la llave (`llave-de-prueba` en esa línea de la prueba).
  3. Una `url` que no empiece por `https://checkout.bold.co/` → `ErrorBold`.
  4. `estado_link` acepta respuesta plana o dentro de `payload`; rechaza un `link_id` que no case `^LNK_[A-Za-z0-9]+$` sin llamar a la red.
  5. `firma_valida`: firma correcta (calcúlala en la prueba: `hmac.new(secreta, base64.b64encode(cuerpo), sha256).hexdigest()`), firma de otro cuerpo, firma vacía, secreta vacía sin `BOLD_PRUEBAS=1` → False; con `BOLD_PRUEBAS=1` y secreta vacía → valida contra la cadena vacía.

- [ ] **Step 2: `cobros/bold.py`:**

```python
"""Bold (pasarela colombiana): crear un link de pago, leer su estado y
verificar la firma del webhook (spec 2026-10-08 §9). El ÚNICO módulo que
habla con Bold. Docs: developers.bold.co (API Link de pagos, Webhook)."""
import base64
import hashlib
import hmac
import os
import re
import time

import requests

BASE = "https://integrations.api.bold.co"
CHECKOUT = "https://checkout.bold.co/"
TIEMPO = 15
_LINK = re.compile(r"LNK_[A-Za-z0-9]+")


class ErrorBold(Exception):
    """Bold no respondió lo esperado. El texto va en palabras y sin llaves."""


def _identidad():
    return (os.environ.get("BOLD_LLAVE_IDENTIDAD") or "").strip()


def configurado():
    return bool(_identidad())


def _cabeceras():
    return {"Authorization": f"x-api-key {_identidad()}", "Content-Type": "application/json"}


def _datos(respuesta):
    try:
        j = respuesta.json()
    except ValueError as e:
        raise ErrorBold("Bold respondió algo que no es JSON") from e
    return j.get("payload", j) if isinstance(j, dict) else {}


def crear_link(*, referencia, usd, descripcion, callback_url, correo=None, horas=24):
    if not configurado():
        raise ErrorBold("Faltan las llaves de Bold")
    cuerpo = {
        "amount_type": "CLOSE",
        "amount": {"currency": "USD", "total_amount": int(usd), "tip_amount": 0, "taxes": []},
        "reference": referencia,
        "description": descripcion[:100],
        "callback_url": callback_url,
        "expiration_date": int((time.time() + horas * 3600) * 1_000_000_000),
    }
    if correo:
        cuerpo["payer_email"] = correo
    try:
        r = requests.post(f"{BASE}/online/link/v1", json=cuerpo, headers=_cabeceras(), timeout=TIEMPO)
    except requests.RequestException as e:
        raise ErrorBold(f"No se pudo hablar con Bold ({type(e).__name__})") from e
    if r.status_code >= 400:
        raise ErrorBold(f"Bold no aceptó el pedido (HTTP {r.status_code})")
    d = _datos(r)
    link, url = d.get("payment_link"), d.get("url")
    if not link or not url or not str(url).startswith(CHECKOUT):
        raise ErrorBold("Bold no devolvió un link de pago válido")
    return {"link_id": str(link)[:40], "url": str(url)}


def estado_link(link_id):
    if not _LINK.fullmatch(str(link_id or "")):
        raise ErrorBold("Identificador de link inválido")
    try:
        r = requests.get(f"{BASE}/online/link/v1/{link_id}", headers=_cabeceras(), timeout=TIEMPO)
    except requests.RequestException as e:
        raise ErrorBold(f"No se pudo hablar con Bold ({type(e).__name__})") from e
    if r.status_code >= 400:
        raise ErrorBold(f"Bold no respondió el estado (HTTP {r.status_code})")
    d = _datos(r)
    total = d.get("total")
    return {"status": str(d.get("status") or "").upper(), "transaction_id": d.get("transaction_id"),
            "total": int(total) if isinstance(total, (int, float)) else None}


def firma_valida(cuerpo, firma):
    """HMAC-SHA256 (hex) del cuerpo en base64 con la llave secreta, comparado
    en tiempo constante con x-bold-signature. En pruebas Bold firma con la
    cadena vacía: solo se acepta con BOLD_PRUEBAS=1."""
    secreta = os.environ.get("BOLD_LLAVE_SECRETA") or ""
    if not secreta and os.environ.get("BOLD_PRUEBAS") != "1":
        return False
    if not firma:
        return False
    esperado = hmac.new(secreta.encode(), base64.b64encode(cuerpo or b""), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, str(firma).strip())
```

- [ ] **Step 3: pruebas de `recargas.py`** (`tests/test_cobros_recargas.py`), con `bold.crear_link` y `bold.estado_link` falsos y `BOLD_PRUEBAS=1` + secreta vacía para firmar:
  1. `crear("acme", 50, "user_acme")` → recarga `pendiente`, `milesimas == 50000`, `referencia` casa `^cv-\d+-\d+$` y ≤ 60, `link_id` guardado; montos 9, 1001, 10.5, "x" → `ValueError` sin fila.
  2. Si `crear_link` lanza `ErrorBold` → la recarga queda `rechazada` y la excepción sube.
  3. Webhook `SALE_APPROVED` con `metadata.reference` de la recarga → `(200, "acreditada")`, recarga `aprobada` con `pago_id`, `moneda_pago="COP"`, `total_pago`, `medio_pago`; saldo +50 000; `pago_evento` guardado sin `payer_email` en `cuerpo`.
  4. El mismo evento otra vez → `(200, "duplicada")`, saldo igual. Otro evento distinto con el mismo `payment_id` → no acredita de nuevo.
  5. Firma inválida → `(401, "firma_invalida")`, recarga intacta, `pago_evento` con `firma_ok=False`.
  6. Referencia desconocida → `(200, "sin_recarga")` y aviso al admin (monkeypatch de `avisos.admin`).
  7. `SALE_REJECTED` → `rechazada`, sin movimiento.
  8. `VOID_APPROVED` de una aprobada → `anulada`, movimiento `anulacion` −50 000, aviso al admin.
  9. Cuerpo que no es JSON → `(400, "invalido")`; cuerpo > 64 KB lo corta la ruta (prueba en 11).
  10. `verificar` con `estado_link` → `PAID` acredita (idempotente con el webhook: correr webhook y verificar no acredita dos veces); `ACTIVE` deja `pendiente`; `EXPIRED` → `expirada`.
  11. Rutas con el cliente de Flask: POST `/pagos/bold/webhook` **con** cabecera `Sec-Fetch-Site: cross-site` y sin sesión → no la frena la barrera CSRF ni el guard (status 200 con firma válida, 401 con inválida); POST `/cliente/acme/saldo/recargar` con `Sec-Fetch-Site: cross-site` → 403; como `user_acme` mismo origen, monto 50 → 302 a la `url` de Bold falsa; como `otro` → redirige fuera (guard por cliente); `GET /cliente/acme/saldo/recarga/<id de otro proyecto>` → 404; la vuelta con `?bold-tx-status=approved` NO acredita.
  12. `manual("acme", 25.5, "admin", "transferencia")` → movimiento `recarga` de 25 500 y recarga `manual/aprobada`; `manual(..., tipo="ajuste")` con nota vacía → `ValueError`; ajuste negativo permitido.

- [ ] **Step 4: `cobros/recargas.py`.** Reglas (el código sigue el estilo de `libro.py`):
  - `crear`: valida `usd` entero en `[MIN_USD, MAX_USD]` (acepta `int` o texto de dígitos); inserta con `referencia=f"tmp-{uuid4().hex[:20]}"`, luego `referencia=f"cv-{id}-{int(time.time())}"`; `callback_url = f"{plataforma_url}/cliente/{cliente}/saldo/recarga/{id}"` con `plataforma_url` de la misma función que usa `dashboard.py` para `PLATAFORMA_URL` (si está vacía, `ValueError(gettext("Falta PLATAFORMA_URL en el servidor"))`); `descripcion = gettext("Recarga Creatv · %(proyecto)s", proyecto=cliente)`; guarda `link_id`.
  - `procesar_webhook`: si `len(cuerpo) > 65536` → `(413, "invalido")`. `firma_ok = bold.firma_valida(...)`. JSON inválido → `(400, "invalido")` sin escribir. Extrae `evento_id = str(ev.get("id") or "")[:64]`, `tipo = str(ev.get("type") or "")[:24]`, `data = ev.get("data") or {}`, `ref = str((data.get("metadata") or {}).get("reference") or "")[:60] or None`, `pago_id = str(data.get("payment_id") or ev.get("subject") or "")[:40] or None`. Copia de `data` sin `payer_email` para `cuerpo`. Firma inválida → inserta `pago_evento(firma_ok=False, resultado="firma_invalida", cuerpo=None)` (si `evento_id` choca, ignora) y `(401, …)`. Si no: en UNA transacción inserta `pago_evento` (IntegrityError → `(200, "duplicada")`), busca la recarga por `referencia` (o por `pago_id` para `VOID_*`), y:
    - `SALE_APPROVED`: `UPDATE recarga SET estado='aprobada', pago_id, moneda_pago, total_pago, medio_pago, actualizada_en WHERE id=? AND estado='pendiente'`; si `rowcount == 1` → `libro.acreditar(con, cliente, "recarga", milesimas, "recarga_bold", recarga_id=id)` y resultado `acreditada`; si 0 → `duplicada`. Un `pago_id` que ya tiene otra recarga (IntegrityError en el UPDATE dentro de `begin_nested`) → `duplicada`.
    - `SALE_REJECTED`: `pendiente → rechazada`, resultado `rechazada`.
    - `VOID_APPROVED`: `aprobada → anulada` y `libro.acreditar(con, cliente, "anulacion", -milesimas, "anulacion_bold", recarga_id=id)`, resultado `anulada`.
    - otro tipo → `ignorada`. Sin recarga → `sin_recarga`.
    - Actualiza `pago_evento.resultado`. Después de la transacción, los avisos: acreditada → `avisos.recarga_acreditada` + `avisos.recarga_admin` + `avisos.limpiar_aviso_bajo`; anulada → `avisos.admin("anulacion_bold", …)`; sin_recarga → `avisos.admin("pago_sin_recarga", …)`. Devuelve `(200, resultado)`. Un error inesperado → `log.exception`, `(500, "error")` (Bold reintenta).
  - `verificar(recarga_id)`: solo recargas `bold/pendiente` con `link_id`; `bold.estado_link`; `PAID` → mismo `UPDATE … WHERE estado='pendiente'` + acreditar, con `pago_id = transaction_id or f"link:{link_id}"`; `EXPIRED` → `expirada`; `ErrorBold` → deja `pendiente` y lo registra en el log. Devuelve el estado.
  - `verificar_pendientes()`: las `bold/pendiente` creadas hace menos de 26 h; además pasa a `expirada` las de más de 26 h.
  - `manual(...)`: `usd` con 2 decimales (`Decimal`), distinto de 0; `tipo="recarga"` exige `usd > 0` e inserta `recarga(medio="manual", estado="aprobada", referencia=f"mn-{id}-{epoch}")` + `acreditar("recarga", …, "recarga_manual")`; `tipo="ajuste"` exige nota y solo escribe `acreditar("ajuste", …, "ajuste", usuario=…, detalle=nota)`.

- [ ] **Step 5: `cobros/rutas.py` (Blueprint `cobros`) + registro en `dashboard.py`.**
  - `recargar`: exige proyecto que cobra o admin; tope `cuentas.limite_ok(f"recarga:{cliente}", 10, 3600)`; correo verificado de la sesión (`usuarios.obtener`) como `payer_email`; `recargas.crear`; `redirect(url)` (302 a `checkout.bold.co`). `ValueError`/`ErrorBold` → flash en palabras y vuelve a `ver_cliente#config-ap-saldo`.
  - `recarga_vuelta`: 404 si la recarga no es de ese `cliente`; renderiza `saldo_recarga.html` (la plantilla y su JS van en la Task 8; aquí basta una plantilla mínima que la Task 8 reemplaza).
  - `recarga_estado`: 404 ajena; si `pendiente` y `bold`, llama a `recargas.verificar` como máximo una vez cada 3 s por recarga (`kv` o caché en memoria); devuelve el JSON.
  - `recarga_verificar`: POST, mismo efecto y redirige a `#config-ap-saldo` con flash del estado.
  - `bold_webhook`: lee `request.get_data(cache=False, as_text=False)` con tope de 64 KB (`request.content_length` > 65536 → 413), llama a `recargas.procesar_webhook(cuerpo, request.headers.get("x-bold-signature"))` y responde `("", status)` sin cuerpo.
  - En `dashboard.py`: `ENDPOINTS_OTRO_ORIGEN = frozenset(("cobros.bold_webhook",))` con un comentario (el único POST que acepta otro origen; su firma HMAC lo protege) y `_solo_mismo_origen` sale temprano si `request.endpoint in ENDPOINTS_OTRO_ORIGEN`; agrega `"cobros.bold_webhook"` a `ENDPOINTS_SIN_GUARD_SESION`. Si hay un `before_request` que exige login para rutas sin `<cliente>`, exime también el webhook.
  - `tareas/cobros.py`: `def verificar_recargas(tarea): n = recargas.verificar_pendientes(); return f"{n} recargas revisadas"`, registrada como `REGISTRO["cobros_verificar_recargas"]`.

- [ ] **Step 6:** `$PY -m pytest -q tests/test_cobros_bold.py tests/test_cobros_recargas.py` + suite rápida → PASS.
- [ ] **Step 7: commit** «Cobros 7/11: recargas con Bold (link de pago, webhook firmado, verificación de respaldo) y recarga manual».

---

### Task 8: Lo que ve el cliente — Configuración › Saldo, la vuelta del pago, el chip y el gasto cobrado

**Files:**
- Create: `cobros/vista.py`, `templates/_config_saldo.html`, `templates/_saldo_panel.html`, `templates/saldo_recarga.html` (reemplaza la mínima de la Task 7), `static/cobros.js`
- Modify: `templates/_tab_settings.html` (botón de apartado «Saldo» + `<section class="config-apartado" id="config-ap-saldo" data-apartado="saldo">` que incluye `_config_saldo.html`; visible si `cobros_cuenta.cobrar or es_admin`), `dashboard.py` (`_contexto_gasto`, `_chip_gasto`, `_chip_gasto_sidebar`, `gasto_csv`, `gasto_csv_todo`, y todo lugar que muestre cifras de `gasto` a un cliente), `templates/_sidebar.html`, `cobros/rutas.py` (`GET /cliente/<cliente>/saldo/panel` → fragmento HTML; `GET /cliente/<cliente>/saldo/movimientos.csv`), `cobros/avisos.py` (usa `vista.nombre_concepto`)
- Test: `tests/test_cobros_vista.py`

**Interfaces:**
- Consumes: `libro.cuenta/saldo/disponible`, `recargas.de_proyecto`, `bold.configurado`.
- Produces:
  - `vista.nombre_concepto(codigo: str) -> str` (traducido: los tipos de gasto con los mismos nombres que `NOMBRES_TIPO_GASTO` de `dashboard.py` — muévelos a un lugar importable sin ciclo o duplícalos con `N_`; `recarga_bold` «Recarga con Bold», `recarga_manual` «Recarga», `ajuste` «Ajuste», `anulacion_bold` «Pago anulado por Bold»; y prefijo según el tipo de movimiento: «No cobrado: …», «Devuelto: …»).
  - `vista.movimientos(cliente, pagina=1, por_pagina=50) -> {"filas": [{"creado_en", "tipo", "concepto", "milesimas", "saldo_despues", "detalle"}], "hay_mas": bool}` (saldo después calculado con una ventana `SUM() OVER (ORDER BY id)` o acumulando desde el saldo actual hacia atrás — una consulta, no una por fila).
  - `vista.resumen_mes_cobrado(cliente, ahora_iso=None)`, `vista.resumen_total_cobrado(cliente)`, `vista.por_mes_cobrado(cliente)`, `vista.historial_cobrado(cliente, limite=200)`: **misma forma** que `gastos.resumen_mes`, `gastos.resumen_total`, `gastos.por_mes`, `gastos.historial` (lee esas funciones y devuelve las mismas claves), con `usd` = (cobro + reverso) / 1000 en positivo, agrupado por el `tipo` del gasto (`concepto`).
  - `vista.gasto_para(cliente, es_admin) -> dict` con las funciones que la página debe usar: si el proyecto cobra y no es admin, las de lo cobrado; si no, las de `gastos`. `_contexto_gasto` y los CSV pasan por aquí.
  - `vista.chip(cliente, es_admin) -> {"texto": str, "tono": "normal"|"aviso"|"bloqueo", "url": str}|None` (None si no cobra).

- [ ] **Step 1: pruebas que fallan** — `tests/test_cobros_vista.py`:
  1. `movimientos` devuelve el saldo después de cada fila correcto con recarga 10 000, cobro −1 500, reverso +1 500, cobro −600 (más nuevo primero: 7 900, 8 500, 10 000…); y la paginación.
  2. `resumen_mes_cobrado` agrupa por tipo y descuenta los reversos.
  3. **Aislamiento y costo oculto:** con `acme` que cobra (margen 1,5) y un gasto de video de US$ 1,00: como `user_acme`, GET `/cliente/acme` (Configuración › Gasto) muestra «US$ 1,50» y NO «US$ 1,00»; GET `/cliente/acme/gasto/mes.csv` tiene 1,50 y no 1,00; como `admin`, la página muestra las dos cifras.
  4. Como `user_acme` GET `/cliente/acme/saldo/panel` → 200 con el saldo; como `otro` → redirige (guard); el CSV de movimientos solo trae filas de `acme`.
  5. Chip: saldo 3 000 con umbral 5 000 → tono `aviso`; 0 → `bloqueo`; 20 000 → `normal`; proyecto que no cobra → None y el chip de hoy sigue igual.
  6. Sin `BOLD_LLAVE_IDENTIDAD`, el panel muestra el texto «Las recargas en línea todavía no están disponibles; escríbenos para recargar.» y no muestra el botón «Pagar con Bold».
  7. `saldo_recarga.html` renderiza para una recarga pendiente y contiene la URL de estado en un `data-*` (sin `<script>` en línea con lógica).

- [ ] **Step 2:** FAIL.

- [ ] **Step 3: implementación.** Carga la skill `ui` y la `idioma`. Reglas: base visual común de `static/style.css` (clases existentes: `config-apartado`, tarjetas, botones, `vacio`, chips); nada empuja la página de lado en el celular (tabla de movimientos con contenedor de desplazamiento horizontal propio); la sección de Configuración solo trae un contenedor `data-saldo-panel="{{ url_for('cobros.saldo_panel', cliente=cliente) }}"` y `static/cobros.js` (cargado con `defer` desde `_config_saldo.html`) pide el fragmento cuando el apartado se abre por primera vez (o al cargar si el ancla es `#config-ap-saldo`); así abrir el proyecto no paga la consulta del libro. El fragmento tiene: saldo y disponible grandes, umbral, el formulario de recarga (botones 20/50/100/200 que llenan un campo `number` min 10 max 1000 step 1, «Pagar con Bold» y la nota de medios de pago del spec §7), la tabla de movimientos con «Ver más» (fetch de la página siguiente) y el enlace al CSV, y las últimas recargas con estado y «Verificar» en las pendientes. `saldo_recarga.html` extiende la base, muestra «Verificando tu pago…» y `cobros.js` sondea `data-estado-url` cada 3 s hasta 60 s y cambia el texto (aprobada / rechazada / expirada / sigue pendiente, frases del §9.4). El chip de `_sidebar.html`: si `cobros_chip`, pinta «Saldo: US$ X · Recargar» con la clase del tono; si no, el de hoy. En `_chip_gasto_sidebar` y `ver_cliente` calcula `cobros_chip` con `vista.chip` (una consulta; nunca en respuestas JSON). Al admin el chip agrega el costo del mes.
- [ ] **Step 4: inventario del gasto a la vista.** `grep -rn "gastos\.\(resumen_mes\|resumen_total\|por_mes\|historial\|total\)" --include=*.py . | grep -v tests/` y `grep -rn "gasto_mes\|gasto_total\|gastos_historial" templates/`: cada lugar que muestre cifras de costo a un cliente (Configuración › Gasto, CSV, ficha del Tablero, centro de resultados de Experimentos, cifra de costo de Final edition, panel) pasa por `vista.gasto_para`. El panel de admin no cambia (es del admin). Escribe la lista en el commit.
- [ ] **Step 5:** pruebas → PASS; suite rápida → PASS. Mira la pantalla de verdad: sigue la memoria del repo «verificar UI sin contraseña» (`tests` con sesión admin sembrada o el método del launch.json) o arranca `dashboard.py` con una base temporal y un usuario de prueba, y toma capturas de Configuración › Saldo, del chip y de la vuelta del pago en escritorio y en 375 px. Guárdalas en el scratchpad y menciónalas en tu informe.
- [ ] **Step 6: commit** «Cobros 8/11: Configuración › Saldo y recargas, la vuelta del pago, el chip de saldo y el gasto que ve el cliente es lo cobrado».

---

### Task 9: Alertas de cobros

**Files:**
- Modify: `alertas.py` (`_fuente_cobros` y su registro en `calcular`)
- Test: `tests/test_cobros_alertas.py`

**Interfaces:**
- Consumes: `libro.cuenta/saldo/disponible`, `db.movimiento_saldo`, `db.recarga`.
- Produces: alertas con las claves `cobros:sin_saldo`, `cobros:saldo_bajo`, `cobros:no_cobrado:<mov_id>`, `cobros:recarga_pendiente:<id>` (§8), tab `settings` y ancla `config-ap-saldo`.

- [ ] **Step 1: pruebas que fallan** (patrón de `tests/test_alertas_fuentes.py`): proyecto que no cobra → ninguna alerta `cobros:*`; disponible 0 → `cobros:sin_saldo` nivel `bloquea`; saldo 3 000 con umbral 5 000 → `cobros:saldo_bajo` nivel `atencion`; un `reverso` de hace 2 días → `cobros:no_cobrado:<id>` `info`; uno de hace 8 días → nada; recarga Bold pendiente de hace 20 min → `cobros:recarga_pendiente:<id>`; la huella de `saldo_bajo` cambia cuando cambia el saldo (para que un descarte no esconda un saldo que siguió bajando: huella = saldo redondeado a dólares).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `_fuente_cobros(cliente, ahora)` con `_alerta(...)` como las demás fuentes (lee `_fuente_saldo` de ejemplo); textos con `gettext`; una consulta por tipo de dato (no una por movimiento). Agrégala a la lista de fuentes de `calcular`.
- [ ] **Step 4:** pruebas + `tests/test_alertas.py` → PASS.
- [ ] **Step 5: commit** «Cobros 9/11: alertas de saldo bajo, sin saldo, pieza no cobrada y recarga pendiente».

---

### Task 10: /admin/cobros

**Files:**
- Modify: `cobros/rutas.py` (rutas admin), `cobros/vista.py` (`resumen_admin`)
- Create: `templates/admin_cobros.html`
- Modify: la plantilla del panel de admin (enlace a /admin/cobros junto a los de salud, meta, referentes)
- Test: `tests/test_cobros_admin.py`

**Interfaces:**
- Consumes: `libro.configurar`, `libro.guardar_margen_global`, `libro.margen_global`, `recargas.manual`.
- Produces:
  - `vista.resumen_admin(ahora_iso=None) -> list[dict]` con, por proyecto: `cliente`, `cobrar`, `margen_propio`, `margen`, `umbral`, `saldo`, `disponible`, `recargado_mes`, `cobrado_mes`, `costo_mes`, `ganancia_mes` (milésimas; `costo_mes` = costo de los gastos que tuvieron cobro este mes; `ganancia_mes = cobrado_mes − costo de lo cobrado`). Proyectos: los mismos que lista el panel de admin hoy (`admin.py`) más los que tengan `cuenta_saldo`. **Una consulta agregada por columna** (GROUP BY cliente), nunca una por proyecto.
  - Rutas (todas `requiere_admin` y POST mismo origen): `GET /admin/cobros` (`cobros.admin_cobros`), `POST /admin/cobros/margen` (`cobros.admin_margen`), `POST /admin/cobros/<cliente>/cuenta` (`cobros.admin_cuenta`: cobrar, margen propio vacío = global, umbral en dólares), `POST /admin/cobros/<cliente>/recarga` (`cobros.admin_recarga`: monto, nota, tipo recarga|ajuste).
  - `vista.ultimos_eventos(limite=20)` y `vista.webhook_callado() -> bool` (hay recargas Bold pendientes y ningún `pago_evento` en 7 días).

- [ ] **Step 1: pruebas que fallan:** como `user_acme`, GET `/admin/cobros` → redirige al login con el flash de solo admin; como `admin`: 200 y lista `acme` y `otro`; POST `/admin/cobros/acme/cuenta` con `cobrar=1` → `libro.cobra("acme")`; con `Sec-Fetch-Site: cross-site` → 403; POST margen 0.5 → flash de error y el margen sigue igual; POST recarga manual 25 → saldo 25 000; ajuste sin nota → flash de error; prender cobrar en un proyecto con saldo 0 muestra el aviso del §10; `resumen_admin` con 3 proyectos hace un número de consultas que no crece con los proyectos (cuenta las consultas con un `event.listen(engine, "before_cursor_execute", …)` como en `tests/test_escala.py` si existe ese patrón; compara 3 proyectos contra 6).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementación sobre la base visual común (la tabla con desplazamiento horizontal propio en el celular; interruptor como `<form>` con botón; recarga manual en un `<details>` por fila).
- [ ] **Step 4:** pruebas + suite rápida → PASS; captura de /admin/cobros en escritorio.
- [ ] **Step 5: commit** «Cobros 10/11: /admin/cobros (margen, interruptor por proyecto, recarga manual, ganancia del mes y eventos de Bold)».

---

### Task 11: Catálogo, skill, guía y pendientes

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po` (vía `catalogo_i18n.py`)
- Create: `.claude/skills/cobros/SKILL.md`
- Modify: `CLAUDE.md` (fila nueva en «Qué skill cargar» y la regla 1 menciona que el cobro al cliente sale solo de `gastos.registrar`), `.claude/skills/plataforma/SKILL.md` (el párrafo «Gasto real por proyecto» deja de decir «there are no credits or balances» y apunta a la skill `cobros`), `.claude/skills/seguridad/SKILL.md` (la app ahora recibe UN webhook: el de Bold, exento con firma), `docs/pendientes.md` (los puntos del §13 del spec con IDs nuevos PND-NNN, categoría y estado `bloqueado por Daniel` donde toque), `CONTEXT.md` (glosario: costo, precio, margen, saldo, disponible, reserva, recarga)
- Test: `tests/test_guia_agentes.py`, `tests/test_i18n_catalogo.py` (existentes)

- [ ] **Step 1:** `$PY catalogo_i18n.py actualizar`, traduce al inglés cada `msgid` nuevo siguiendo `docs/i18n/glosario.md` (saldo = balance, recarga = top-up, cobro = charge, margen = markup, «Cobrar» = «Charge usage»), quita toda marca `fuzzy`, `$PY catalogo_i18n.py compilar`.
- [ ] **Step 2:** escribe la skill `cobros` (formato de las demás: frontmatter `name`/`description` con cuándo cargarla; secciones: el principio, las tablas y sus escritores, el flujo de un cobro, el freno y la reserva, la reversión, Bold con sus llaves y su webhook, las pantallas, las pruebas que cuidan cada regla, y las trampas con su motivo y fecha 2026-10-08). Fila en `CLAUDE.md`: «| el saldo, el margen, las recargas, Bold, `cobros/` | [`cobros`](.claude/skills/cobros/SKILL.md) |». `CLAUDE.md` no puede pasar de 250 líneas.
- [ ] **Step 3:** `$PY -m pytest -q tests/test_guia_agentes.py tests/test_i18n_catalogo.py` y la suite completa `$PY -m pytest -q` → PASS (si una prueba lenta falla por algo ajeno a cobros, compruébalo en `origin/main` y anótalo).
- [ ] **Step 4: commit** «Cobros 11/11: catálogo en inglés, skill cobros, guía y pendientes».

---

## Después de las tareas (lo hace el orquestador)

1. Subagentes de revisión en paralelo sobre `git diff origin/main...cobros`: `guardian-gasto`, `auditor-seguridad` y `revisor` (contra el spec, con las mutaciones del §14). Arreglar lo confirmado (máximo dos rondas por problema).
2. Prueba real local: base temporal, proyecto que cobra, recarga manual, un trabajo encolado que cobra con un proveedor falso, el webhook firmado con `BOLD_PRUEBAS=1`, capturas.
3. Mezclar a `main` (sincronizando con `origin/main` antes; catálogo y submódulo según las memorias del repo), desplegar con la skill `despliegue` (migración 0033 —era 0032, renumerada al mezclar main— ensayada en una copia, cola vacía en su propio ssh, los dos servicios).
