# Motor — Bloque 3: experimento manual (lanzador multi-país, snapshots y árbol) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un experimento creado a mano (nombre, países con presupuesto diario, tope, días, destino) que agrupa piezas (finales por país o clones), se lanza a Meta como 1 campaña → 1 conjunto por país → 1 anuncio por pieza (todo en pausa), se activa/pausa por experimento o por país, refresca métricas cada 2 h en `metrica_snapshot`, y se ve como árbol en una pestaña nueva "Experimentos".

**Architecture:** Módulo de datos `experimentos.py` (SQLAlchemy Core sobre `experimento`/`experimento_pieza`/`metrica_snapshot`/`evento`) + `lanzador.py` (traduce el experimento a llamadas del submódulo `meta_ads`, idempotente por ids guardados) + tareas del worker `exp_lanzar` (gasta: `max_intentos=1`), `exp_refrescar`, `exp_refrescar_todos` (periódica 2 h) + rutas `exp_*` en `dashboard.py` + `_tab_experimentos.html`. Campañas (anuncios sueltos, `ads.py`) queda intacta.

**Tech Stack:** Flask 3.1/Jinja, SQLAlchemy Core + Alembic (SQLite WAL), worker `worker.py` + `cola.py`, submódulo `meta_ads` (Graph v25.0), pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §2 (experimento, experimento_pieza, metrica_snapshot, evento), §4 (lanzador y atribución), §7 (UI Experimentos), §9 punto 3.

## Global Constraints

- Nada gasta dinero sin clic: lanzar (crea objetos en Meta, en PAUSA) y activar (empieza a gastar) son dos clics distintos. Ningún código de este bloque activa anuncios solo. Todo anuncio nace `PAUSED`.
- Tareas que crean objetos en Meta: `max_intentos=1`, hook `al_interrumpir` que deja la entidad en `error`; el reintento lo pide la persona y **retoma** (ids guardados), nunca duplica campañas.
- Tokens/secretos jamás en logs, errores ni respuestas; `meta_auth.configurar → llamadas → limpiar()` siempre bajo el lock (`tareas.meta._LOCK` en el worker, `dashboard._ENV_LOCK` en rutas).
- Presupuestos en la **moneda de la cuenta** (`meta_conexion.cargar(cliente)["moneda"]`); a Meta van en unidad menor (`×100` salvo `MONEDAS_SIN_DECIMALES`). Mínimo diario `PRESUPUESTO_MINIMO_DIARIO[moneda]` (dashboard.py).
- Un conjunto por país (`Targeting().edad(a,b).paises([pais])`), un anuncio por pieza. `spend_cap` de campaña = tope total del experimento.
- URL de destino con `utm_source=creatv&utm_medium=meta&utm_content=<pieza_id>` (id numérico de `pieza`).
- Copy en español. `creado_en`/`actualizado_en` con `db.ahora()`.
- Campañas (`ads.py`, `_tab_ads.html`, `meta_publicar`/`meta_refrescar`) no cambian de comportamiento.
- Estados de `experimento` en este bloque: `armando` (sin lanzar) → `lanzando` (tarea en curso) → `pausado` (todo en Meta, en pausa) ↔ `corriendo` (campaña activa) → `cerrado`; `error` si el lanzamiento falló (se retoma con "Reintentar"). `esperando_aprobacion`/`decidido` los usa el bloque 4.
- Estados de `experimento_pieza`: `en_cola` → `publicando` → `pausado` ↔ `activo`; `error`.
- Piezas elegibles: `pieza.tipo == "final"` con estado `listo`/`degradada` solo para **su** país; `pieza.tipo in ("video","clon_limpio")` con estado `listo` y `url_video` para cualquier país. Imágenes no (los experimentos son de video).
- Solo experimentos en `armando` (o `error` sin campaña creada) aceptan agregar/quitar piezas y editar países. Derivar/rescatar sobre uno corriendo es bloque 4.
- Tests: `venv/bin/python -m pytest -q` verde; sin red (los módulos `meta_ads.*` se sustituyen con fakes por monkeypatch). Sin `-m slow`.

---

## Estructura de archivos

- Create: `migrations/versions/0004_experimento_extra.py` — columnas `experimento.destino_url`, `edad_min`, `edad_max`, `error`, `extra`.
- Modify: `db.py` — mismas columnas en la tabla `experimento`.
- Create: `experimentos.py` — CRUD del experimento y sus piezas, snapshots, eventos, elegibles, vista para la UI.
- Modify (submódulo) `meta_ads/campaign.py`, `meta_ads/adset.py`, `meta_ads/ad.py`, `meta_ads/insights.py` — `spend_cap`, presupuesto/estado del adset, estado del ad, thruplay/compras/ingresos/roas.
- Create: `lanzador.py` — `lanzar(cliente, experimento_id, on_etapa)`, `cambiar_estado(...)`, `cambiar_presupuesto_pais(...)`, `refrescar(cliente, experimento_id)`.
- Create: `tareas/experimentos.py` — `exp_lanzar`, `exp_refrescar`, `exp_refrescar_todos`. Modify `tareas/__init__.py`, `worker.py` (PERIODICAS).
- Modify: `dashboard.py` — rutas `exp_*`, contexto de `ver_cliente`, `_reconciliar_huerfanos`.
- Create: `templates/_tab_experimentos.html`. Modify `templates/_sidebar.html`, `templates/cliente.html`, `templates/_tab_creativeflowplus.html` (botón "Meter en experimento"), `static/style.css`.
- Tests: `tests/test_experimentos_db.py`, `tests/test_meta_ads_bloque3.py`, `tests/test_lanzador.py`, `tests/test_tareas_experimentos.py`, `tests/test_rutas_experimentos.py`.

---

### Task 1: Migración 0004 + módulo `experimentos.py`

**Files:**
- Create: `migrations/versions/0004_experimento_extra.py`
- Modify: `db.py` (tabla `experimento`, después de `legado`)
- Create: `experimentos.py`
- Modify: `creative_flow.py` (helper `pieza_id_por_legado`)
- Test: `tests/test_experimentos_db.py`

**Interfaces:**
- Consumes: `db.conectar()`, `db.ahora()`, tablas `db.experimento`, `db.experimento_pieza`, `db.metrica_snapshot`, `db.evento`, `db.pieza`, `db.concepto`.
- Produces (usadas por Tasks 3–5):
  - `experimentos.crear(cliente, nombre, paises, objetivo_meta, dias, tope_total, destino_url, moneda, edad_min=18, edad_max=65, modo="manual") -> int`. `paises` = `[{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0}, ...]`.
  - `experimentos.cargar(cliente) -> list[dict]` (no legado, más nuevo primero) con `id, nombre, estado, modo, paises (con meta_adset_id/estado/presupuesto_dia), moneda, tope_total, dias, objetivo_meta, destino_url, edad_min, edad_max, meta_campaign_id, gasto_acumulado, error, extra, creado_en, piezas (list, ver abajo), eventos (últimos 30), resumen {gasto, mejor_cpc, mejor_ctr, activos, total}`.
  - `experimentos.obtener(cliente, experimento_id) -> dict|None` (misma forma, sin límite de eventos).
  - `experimentos.actualizar(cliente, experimento_id, **campos)` — columnas: `estado, error, meta_campaign_id, gasto_acumulado, paises, nombre, tope_total, dias, destino_url, edad_min, edad_max, extra, modo`.
  - `experimentos.actualizar_pais(cliente, experimento_id, pais, **campos)` — mezcla campos en la entrada de `paises` con ese código (`meta_adset_id`, `estado`, `presupuesto_dia`).
  - `experimentos.agregar_pieza(cliente, experimento_id, pieza_id, pais) -> int` (id de experimento_pieza; `IntegrityError`→ devuelve el existente: unicidad lógica (experimento_id, pieza_id, pais) chequeada con SELECT previo).
  - `experimentos.quitar_pieza(cliente, experimento_id, ep_id) -> bool` (solo si `estado == "en_cola"` y sin `meta_ad_id`).
  - `experimentos.actualizar_pieza(cliente, ep_id, **campos)` — `estado, error, meta_adset_id, meta_ad_id, meta_creative_id, estado_meta, presupuesto_dia_actual, extra`.
  - `experimentos.piezas(cliente, experimento_id) -> list[dict]`: `id, pieza_id, pais, estado, error, meta_adset_id, meta_ad_id, meta_creative_id, estado_meta, presupuesto_dia_actual, veredicto, nombre, url_video, url_miniatura, tipo, idioma, legado_id, metricas (última o vacía), creado_en`.
  - `experimentos.snapshot(ep_id, metricas: dict) -> int` — inserta fila en `metrica_snapshot`; claves aceptadas: `impresiones, alcance, frecuencia, clics, clics_enlace, ctr, cpc, cpm, thruplay, thruplay_rate, gasto, compras, ingresos, roas, cpa, fuente_ventas`; el resto va a `extra`.
  - `experimentos.ultima_metrica(ep_id) -> dict` (`{}` si no hay; incluye `tomado_en`).
  - `experimentos.registrar_evento(cliente, experimento_id, tipo, mensaje, datos=None, ep_id=None) -> int`.
  - `experimentos.eventos(cliente, experimento_id, limite=None) -> list[dict]` (más nuevo primero).
  - `experimentos.elegibles(cliente) -> list[dict]`: `pieza_id, legado_id, tipo ("final"|"clon"), nombre, url_video, url_miniatura, idioma, pais (None para clon), duracion_s`.
  - `creative_flow.pieza_id_por_legado(cliente, legado_id) -> int|None`.

- [ ] **Step 1: Migración y columnas en `db.py`**

En `db.py`, dentro de `experimento = Table(...)`, después de `Column("legado", ...)` y antes del `sa.Index(...)`:

```python
    Column("destino_url", String(500)),
    Column("edad_min", Integer, default=18),
    Column("edad_max", Integer, default=65),
    Column("error", Text),
    Column("extra", JSON, default=dict),                    # lanzamiento: etapa, ids parciales
```

`migrations/versions/0004_experimento_extra.py`:

```python
"""experimento: destino_url, edades, error, extra

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15 00:00:00.000000

Bloque 3: el experimento real (no legado) necesita el destino del anuncio, el
rango de edad del targeting, el último error de lanzamiento y un extra JSON.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("experimento") as b:
        b.add_column(sa.Column("destino_url", sa.String(500)))
        b.add_column(sa.Column("edad_min", sa.Integer(), server_default="18"))
        b.add_column(sa.Column("edad_max", sa.Integer(), server_default="65"))
        b.add_column(sa.Column("error", sa.Text()))
        b.add_column(sa.Column("extra", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("experimento") as b:
        b.drop_column("extra")
        b.drop_column("error")
        b.drop_column("edad_max")
        b.drop_column("edad_min")
        b.drop_column("destino_url")
```

Verificar: `venv/bin/alembic upgrade head` sobre una copia de `data/creatv.db` (`cp data/creatv.db /tmp/creatv_prueba.db && CREATV_DB_URL=sqlite:////tmp/creatv_prueba.db venv/bin/alembic upgrade head`) y `venv/bin/alembic downgrade 0003` sobre la misma copia.

- [ ] **Step 2: Test que falla — `tests/test_experimentos_db.py`**

```python
import pytest

PAISES = [{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0},
          {"pais": "MX", "idioma": "es", "presupuesto_dia": 150.0}]


def _pieza(db, cliente="acme", tipo="final", estado="listo", pais="CO", idioma="es", legado="cf_1__es_CO", url="https://r2/f.mp4"):
    with db.conectar() as con:
        ahora = db.ahora()
        cid = con.execute(db.concepto.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id="cf_1", extra={})).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo=tipo, estado=estado,
            pais=pais, idioma=idioma, url_video=url, legado_id=legado, extra={})).inserted_primary_key[0]


def test_crear_y_cargar_experimento(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "Cojín abrazable", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://tienda.co/p", "COP")
    lista = ex.cargar("acme")
    assert [e["id"] for e in lista] == [eid]
    e = lista[0]
    assert e["estado"] == "armando" and e["modo"] == "manual" and e["moneda"] == "COP"
    assert e["paises"][0] == {"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0, "meta_adset_id": None, "estado": "en_cola"}
    assert e["edad_min"] == 18 and e["edad_max"] == 65 and e["piezas"] == [] and e["resumen"]["total"] == 0
    assert ex.cargar("otro") == []
    assert ex.obtener("acme", 999) is None


def test_cargar_excluye_legado(base_temporal):
    import ads
    import experimentos as ex
    ads.crear("acme", "creative_flow", "cf_9", "https://r2/v.mp4", "video", "suelto")
    assert ex.cargar("acme") == []


def test_agregar_quitar_piezas_y_unicidad(base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep1 = ex.agregar_pieza("acme", eid, pid, "CO")
    assert ex.agregar_pieza("acme", eid, pid, "CO") == ep1
    ep2 = ex.agregar_pieza("acme", eid, pid, "MX")
    assert ep1 != ep2
    piezas = ex.piezas("acme", eid)
    assert [p["pais"] for p in piezas] == ["CO", "MX"]
    assert piezas[0]["url_video"] == "https://r2/f.mp4" and piezas[0]["metricas"] == {} and piezas[0]["estado"] == "en_cola"
    assert ex.quitar_pieza("acme", eid, ep2) is True
    ex.actualizar_pieza("acme", ep1, meta_ad_id="120", estado="pausado")
    assert ex.quitar_pieza("acme", eid, ep1) is False  # ya está en Meta
    assert ex.quitar_pieza("otro", eid, ep1) is False


def test_actualizar_pais_y_experimento(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar_pais("acme", eid, "MX", meta_adset_id="777", estado="pausado")
    ex.actualizar("acme", eid, estado="pausado", meta_campaign_id="555", gasto_acumulado=12.5)
    e = ex.obtener("acme", eid)
    assert e["paises"][1]["meta_adset_id"] == "777" and e["paises"][1]["estado"] == "pausado"
    assert e["paises"][0]["meta_adset_id"] is None
    assert e["estado"] == "pausado" and e["meta_campaign_id"] == "555" and e["gasto_acumulado"] == 12.5
    with pytest.raises(ValueError):
        ex.actualizar("acme", eid, legado=True)


def test_snapshot_y_ultima_metrica(base_temporal):
    import experimentos as ex
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    assert ex.ultima_metrica(ep) == {}
    ex.snapshot(ep, {"impresiones": 100, "clics_enlace": 5, "gasto": 3.5, "ctr": 5.0, "estado_meta_texto": "Activo"})
    ex.snapshot(ep, {"impresiones": 250, "clics_enlace": 9, "gasto": 8.0, "ctr": 3.6, "cpc": 0.9, "thruplay": 40})
    m = ex.ultima_metrica(ep)
    assert m["impresiones"] == 250 and m["cpc"] == 0.9 and m["thruplay"] == 40 and m["tomado_en"]
    assert "estado_meta_texto" not in m  # la segunda no lo trajo
    p = ex.piezas("acme", eid)[0]
    assert p["metricas"]["gasto"] == 8.0
    e = ex.obtener("acme", eid)
    assert e["resumen"]["gasto"] == 8.0 and e["resumen"]["mejor_cpc"] == 0.9


def test_eventos(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.registrar_evento("acme", eid, "lanzamiento", "Campaña creada", {"campaign_id": "1"})
    ex.registrar_evento("acme", eid, "estado", "Activado")
    evs = ex.eventos("acme", eid)
    assert [e["tipo"] for e in evs] == ["estado", "lanzamiento"]
    assert evs[1]["datos"] == {"campaign_id": "1"} and evs[0]["creado_en"]
    assert len(ex.eventos("acme", eid, limite=1)) == 1
    assert ex.obtener("acme", eid)["eventos"][0]["mensaje"] == "Activado"


def test_elegibles(base_temporal):
    import experimentos as ex
    db = base_temporal
    f_ok = _pieza(db)                                                   # final lista CO
    _pieza(db, estado="generando", legado="cf_1__es_MX", pais="MX")     # final generando: no
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_2")   # imagen: no
    _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_3", url=None)  # sin url: no
    _pieza(db, cliente="otro", legado="cf_7__es_CO")
    el = ex.elegibles("acme")
    assert {(p["pieza_id"], p["tipo"], p["pais"]) for p in el} == {(f_ok, "final", "CO"), (clon, "clon", None)}
    assert all(p["nombre"] for p in el)


def test_pieza_id_por_legado(base_temporal):
    import creative_flow as cf
    pid = _pieza(base_temporal)
    assert cf.pieza_id_por_legado("acme", "cf_1__es_CO") == pid
    assert cf.pieza_id_por_legado("acme", "nada") is None
    assert cf.pieza_id_por_legado("otro", "cf_1__es_CO") is None
```

Run: `venv/bin/python -m pytest tests/test_experimentos_db.py -q` → FAIL (`ModuleNotFoundError: experimentos`).

- [ ] **Step 3: Implementar `experimentos.py`**

```python
"""
Experimentos del motor (no legado): un experimento agrupa piezas (finales por
país o clones) y se lanza a Meta como 1 campaña → 1 conjunto por país → 1
anuncio por pieza. Este módulo es solo datos (SQLAlchemy Core); las llamadas a
Meta viven en lanzador.py. Campañas (ads.py) sigue usando el experimento legado
"Anuncios sueltos" y no pasa por aquí.
"""
import sqlalchemy as sa

import db

ESTADOS_EXPERIMENTO = ("armando", "lanzando", "pausado", "corriendo", "cerrado", "error",
                       "esperando_aprobacion", "decidido")
ESTADOS_PIEZA = ("en_cola", "publicando", "pausado", "activo", "error")
_EXP_COLS = ("estado", "error", "meta_campaign_id", "gasto_acumulado", "paises", "nombre", "tope_total",
             "dias", "destino_url", "edad_min", "edad_max", "extra", "modo", "reglas", "atribucion", "objetivo_meta")
_EP_COLS = ("estado", "error", "meta_adset_id", "meta_ad_id", "meta_creative_id", "estado_meta",
            "presupuesto_dia_actual", "extra", "veredicto", "veredicto_motivo", "veredicto_en", "escalon_rescate")
_SNAP_COLS = ("impresiones", "alcance", "frecuencia", "clics", "clics_enlace", "ctr", "cpc", "cpm", "thruplay",
              "thruplay_rate", "gasto", "compras", "ingresos", "roas", "cpa", "fuente_ventas")
_SNAP_INT = {"impresiones", "alcance", "clics", "clics_enlace", "thruplay", "compras"}
_TIPOS_CLON = ("video", "clon_limpio")


def _pais_nuevo(p):
    return {"pais": p["pais"], "idioma": p.get("idioma") or "es",
            "presupuesto_dia": float(p.get("presupuesto_dia") or 0), "meta_adset_id": None, "estado": "en_cola"}


def crear(cliente, nombre, paises, objetivo_meta, dias, tope_total, destino_url, moneda,
          edad_min=18, edad_max=65, modo="manual"):
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.experimento.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, modo=modo, reglas={},
            paises=[_pais_nuevo(p) for p in paises], moneda=moneda, tope_total=float(tope_total), dias=int(dias),
            objetivo_meta=objetivo_meta, atribucion="ninguna", estado="armando", gasto_acumulado=0.0,
            legado=False, destino_url=destino_url, edad_min=int(edad_min), edad_max=int(edad_max),
            extra={})).inserted_primary_key[0]


def _fila_experimento(con, cliente, experimento_id):
    return con.execute(sa.select(db.experimento).where(
        db.experimento.c.id == experimento_id, db.experimento.c.cliente == cliente,
        db.experimento.c.legado.is_(False))).first()


def actualizar(cliente, experimento_id, **campos):
    malos = set(campos) - set(_EXP_COLS)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    with db.conectar() as con:
        con.execute(db.experimento.update().where(
            db.experimento.c.id == experimento_id, db.experimento.c.cliente == cliente,
            db.experimento.c.legado.is_(False)).values(actualizado_en=db.ahora(), **campos))


def actualizar_pais(cliente, experimento_id, pais, **campos):
    with db.conectar() as con:
        f = _fila_experimento(con, cliente, experimento_id)
        if not f:
            return
        paises = [dict(p) for p in (f._mapping[db.experimento.c.paises] or [])]
        for p in paises:
            if p["pais"] == pais:
                p.update(campos)
        con.execute(db.experimento.update().where(db.experimento.c.id == experimento_id)
                    .values(paises=paises, actualizado_en=db.ahora()))


def agregar_pieza(cliente, experimento_id, pieza_id, pais):
    with db.conectar() as con:
        existente = con.execute(sa.select(db.experimento_pieza.c.id).where(
            db.experimento_pieza.c.experimento_id == experimento_id, db.experimento_pieza.c.pieza_id == pieza_id,
            db.experimento_pieza.c.pais == pais, db.experimento_pieza.c.cliente == cliente)).scalar()
        if existente:
            return existente
        ahora = db.ahora()
        return con.execute(db.experimento_pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=experimento_id,
            pieza_id=pieza_id, pais=pais, estado="en_cola", veredicto="pendiente", escalon_rescate=0,
            extra={})).inserted_primary_key[0]


def quitar_pieza(cliente, experimento_id, ep_id):
    with db.conectar() as con:
        f = con.execute(sa.select(db.experimento_pieza).where(
            db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente,
            db.experimento_pieza.c.experimento_id == experimento_id)).first()
        if not f or f._mapping[db.experimento_pieza.c.estado] != "en_cola" or f._mapping[db.experimento_pieza.c.meta_ad_id]:
            return False
        con.execute(db.metrica_snapshot.delete().where(db.metrica_snapshot.c.experimento_pieza_id == ep_id))
        con.execute(db.experimento_pieza.delete().where(db.experimento_pieza.c.id == ep_id))
        return True


def actualizar_pieza(cliente, ep_id, **campos):
    malos = set(campos) - set(_EP_COLS)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    with db.conectar() as con:
        con.execute(db.experimento_pieza.update().where(
            db.experimento_pieza.c.id == ep_id, db.experimento_pieza.c.cliente == cliente)
            .values(actualizado_en=db.ahora(), **campos))


def _ultima_metrica(con, ep_id):
    f = con.execute(sa.select(db.metrica_snapshot).where(db.metrica_snapshot.c.experimento_pieza_id == ep_id)
                    .order_by(db.metrica_snapshot.c.id.desc()).limit(1)).first()
    if not f:
        return {}
    m = f._mapping
    out = {c: m[db.metrica_snapshot.c[c]] for c in _SNAP_COLS}
    out.update(m[db.metrica_snapshot.c.extra] or {})
    out["tomado_en"] = m[db.metrica_snapshot.c.tomado_en]
    return out


def ultima_metrica(ep_id):
    with db.conectar() as con:
        return _ultima_metrica(con, ep_id)


def snapshot(ep_id, metricas):
    valores, extra = {}, {}
    for k, v in (metricas or {}).items():
        if k in _SNAP_COLS:
            if k == "fuente_ventas":
                valores[k] = v or "ninguna"
            else:
                valores[k] = int(float(v or 0)) if k in _SNAP_INT else float(v or 0)
        else:
            extra[k] = v
    with db.conectar() as con:
        return con.execute(db.metrica_snapshot.insert().values(
            experimento_pieza_id=ep_id, tomado_en=db.ahora(), extra=extra, **valores)).inserted_primary_key[0]


def _nombre_pieza(p, c):
    if p.tipo == "final":
        return f"Final {p.idioma}_{p.pais} · {p.legado_id or ''}".strip(" ·")
    return (c.extra or {}).get("accion_central") or p.legado_id or f"Pieza {p.id}"


def _piezas(con, cliente, experimento_id):
    ep, pz, cp = db.experimento_pieza, db.pieza, db.concepto
    q = (sa.select(ep, pz.c.tipo, pz.c.idioma.label("p_idioma"), pz.c.url_video, pz.c.url_miniatura, pz.c.legado_id.label("p_legado"),
                   pz.c.pais.label("p_pais"), pz.c.duracion_s, cp.c.extra.label("c_extra"))
         .select_from(ep.outerjoin(pz, pz.c.id == ep.c.pieza_id).outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(ep.c.experimento_id == experimento_id, ep.c.cliente == cliente).order_by(ep.c.id))
    out = []
    for f in con.execute(q):
        m = f._mapping
        tipo = "final" if m["tipo"] == "final" else "clon"
        nombre = (f"Final {m['p_idioma']}_{m['p_pais']}" if tipo == "final"
                  else ((m["c_extra"] or {}).get("accion_central") or m["p_legado"] or f"Pieza {m[ep.c.pieza_id]}"))
        out.append({
            "id": m[ep.c.id], "pieza_id": m[ep.c.pieza_id], "pais": m[ep.c.pais], "estado": m[ep.c.estado],
            "error": m[ep.c.error], "meta_adset_id": m[ep.c.meta_adset_id], "meta_ad_id": m[ep.c.meta_ad_id],
            "meta_creative_id": m[ep.c.meta_creative_id], "estado_meta": m[ep.c.estado_meta],
            "presupuesto_dia_actual": m[ep.c.presupuesto_dia_actual], "veredicto": m[ep.c.veredicto],
            "nombre": nombre[:80], "url_video": m["url_video"], "url_miniatura": m["url_miniatura"], "tipo": tipo,
            "idioma": m["p_idioma"], "legado_id": m["p_legado"], "duracion_s": m["duracion_s"],
            "metricas": _ultima_metrica(con, m[ep.c.id]), "creado_en": m[ep.c.creado_en],
        })
    return out


def piezas(cliente, experimento_id):
    with db.conectar() as con:
        return _piezas(con, cliente, experimento_id)


def _resumen(piezas_):
    con_m = [p["metricas"] for p in piezas_ if p["metricas"]]
    cpcs = [m["cpc"] for m in con_m if (m.get("cpc") or 0) > 0]
    ctrs = [m["ctr"] for m in con_m if (m.get("ctr") or 0) > 0]
    return {"gasto": round(sum(float(m.get("gasto") or 0) for m in con_m), 2),
            "mejor_cpc": min(cpcs) if cpcs else None, "mejor_ctr": max(ctrs) if ctrs else None,
            "activos": sum(1 for p in piezas_ if p["estado"] == "activo"), "total": len(piezas_)}


def _eventos(con, cliente, experimento_id, limite):
    q = (sa.select(db.evento).where(db.evento.c.experimento_id == experimento_id, db.evento.c.cliente == cliente)
         .order_by(db.evento.c.id.desc()))
    if limite:
        q = q.limit(limite)
    return [{"id": f._mapping[db.evento.c.id], "tipo": f._mapping[db.evento.c.tipo], "mensaje": f._mapping[db.evento.c.mensaje],
             "datos": f._mapping[db.evento.c.datos] or {}, "ep_id": f._mapping[db.evento.c.experimento_pieza_id],
             "creado_en": f._mapping[db.evento.c.creado_en]} for f in con.execute(q)]


def _a_dict(con, f, limite_eventos):
    m = f._mapping
    e = db.experimento
    pzs = _piezas(con, m[e.c.cliente], m[e.c.id])
    return {
        "id": m[e.c.id], "nombre": m[e.c.nombre], "estado": m[e.c.estado], "modo": m[e.c.modo],
        "paises": [dict(p) for p in (m[e.c.paises] or [])], "moneda": m[e.c.moneda], "tope_total": m[e.c.tope_total],
        "dias": m[e.c.dias], "objetivo_meta": m[e.c.objetivo_meta], "destino_url": m[e.c.destino_url],
        "edad_min": m[e.c.edad_min], "edad_max": m[e.c.edad_max], "meta_campaign_id": m[e.c.meta_campaign_id],
        "gasto_acumulado": m[e.c.gasto_acumulado] or 0.0, "error": m[e.c.error], "extra": m[e.c.extra] or {},
        "reglas": m[e.c.reglas] or {}, "creado_en": m[e.c.creado_en], "piezas": pzs, "resumen": _resumen(pzs),
        "eventos": _eventos(con, m[e.c.cliente], m[e.c.id], limite_eventos),
    }


def cargar(cliente):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento).where(
            db.experimento.c.cliente == cliente, db.experimento.c.legado.is_(False))
            .order_by(db.experimento.c.id.desc()))
        return [_a_dict(con, f, 30) for f in filas]


def obtener(cliente, experimento_id):
    with db.conectar() as con:
        f = _fila_experimento(con, cliente, experimento_id)
        return _a_dict(con, f, None) if f else None


def registrar_evento(cliente, experimento_id, tipo, mensaje, datos=None, ep_id=None):
    with db.conectar() as con:
        return con.execute(db.evento.insert().values(
            cliente=cliente, experimento_id=experimento_id, experimento_pieza_id=ep_id, tipo=tipo,
            mensaje=mensaje, datos=datos or {}, creado_en=db.ahora())).inserted_primary_key[0]


def eventos(cliente, experimento_id, limite=None):
    with db.conectar() as con:
        return _eventos(con, cliente, experimento_id, limite)


def elegibles(cliente):
    """Finales listas/degradadas (para su país) y clones de video listos (para
    cualquier país). Imágenes y piezas sin url_video no entran."""
    pz, cp = db.pieza, db.concepto
    q = (sa.select(pz, cp.c.extra.label("c_extra"))
         .select_from(pz.outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(pz.c.cliente == cliente, pz.c.url_video.isnot(None),
                sa.or_(sa.and_(pz.c.tipo == "final", pz.c.estado.in_(("listo", "degradada"))),
                       sa.and_(pz.c.tipo.in_(_TIPOS_CLON), pz.c.estado == "listo")))
         .order_by(pz.c.id.desc()))
    out = []
    with db.conectar() as con:
        for f in con.execute(q):
            m = f._mapping
            tipo = "final" if m[pz.c.tipo] == "final" else "clon"
            nombre = (f"Final {m[pz.c.idioma]}_{m[pz.c.pais]} · {m[pz.c.legado_id] or ''}" if tipo == "final"
                      else ((m["c_extra"] or {}).get("accion_central") or m[pz.c.legado_id] or f"Pieza {m[pz.c.id]}"))
            out.append({"pieza_id": m[pz.c.id], "legado_id": m[pz.c.legado_id], "tipo": tipo, "nombre": nombre[:80],
                        "url_video": m[pz.c.url_video], "url_miniatura": m[pz.c.url_miniatura],
                        "idioma": m[pz.c.idioma], "pais": m[pz.c.pais] if tipo == "final" else None,
                        "duracion_s": m[pz.c.duracion_s]})
    return out
```

Nota: si `concepto.extra` no guarda `accion_central` (revisar `creative_flow.py` `_a_dict`/`guardar` para ver dónde queda el texto de la sesión — puede estar en `pieza.extra`), ajustar `_nombre` para leer de donde esté; el test solo exige que `nombre` no sea vacío.

`creative_flow.py`, al final:

```python
def pieza_id_por_legado(cliente, legado_id):
    """Id numérico de la fila `pieza` (clon o final) a partir de su id legado
    (cf_... o cf_...__idioma_pais). Lo usa Experimentos para enlazar piezas."""
    with db.conectar() as con:
        return con.execute(sa.select(db.pieza.c.id).where(
            db.pieza.c.cliente == cliente, db.pieza.c.legado_id == legado_id)).scalar()
```

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python -m pytest tests/test_experimentos_db.py tests/test_creative_flow_db.py tests/test_ads_db.py -q` → PASS (si `test_ads_db.py` no existe con ese nombre, correr la suite completa).

- [ ] **Step 5: Commit**

```bash
git add db.py migrations/versions/0004_experimento_extra.py experimentos.py creative_flow.py tests/test_experimentos_db.py
git commit -m "Motor: experimentos.py (experimento real, piezas, snapshots, eventos) + migración 0004"
```

---

### Task 2: Submódulo `meta_ads`: spend_cap, presupuesto/estado de adset y ad, thruplay y ventas en insights

**Files:**
- Modify: `meta_ads/campaign.py`, `meta_ads/adset.py`, `meta_ads/ad.py`, `meta_ads/insights.py`
- Test: `tests/test_meta_ads_bloque3.py`

**Interfaces:**
- Produces:
  - `campaign.crear_campaign(nombre, objetivo, dry_run=False, spend_cap_centavos=None)` — si viene, agrega `spend_cap` (unidad menor de la divisa; Meta exige ≥ 100 USD equivalente, si es menor **no se manda** y se anota en el payload de vuelta `spend_cap_omitido=True`).
  - `adset.actualizar_presupuesto(adset_id, presupuesto_diario_centavos, dry_run=False)` → POST `{adset_id}` `{"daily_budget": n}`.
  - `adset.actualizar_estado(adset_id, status, dry_run=False)`; `ad.actualizar_estado(ad_id, status, dry_run=False)` (ACTIVE|PAUSED).
  - `insights.obtener_resultados(ad_id, objetivo=None)` devuelve además `thruplay` (int, de `video_thruplay_watched_actions`), `thruplay_rate` (thruplay/impresiones, 0 si no hay), `compras` (int, action `purchase` u `omni_purchase`), `ingresos` (float, `action_values` purchase), `roas` (float, `purchase_roas[0].value` o 0), `alcance` (= reach).

- [ ] **Step 1: Test que falla — `tests/test_meta_ads_bloque3.py`**

```python
import pytest


@pytest.fixture()
def auth_falsa(monkeypatch):
    from meta_ads import auth
    llamadas = []

    def llamar(metodo, edge, payload=None, params=None, dry_run=False):
        llamadas.append((metodo, edge, payload, params))
        if edge.endswith("/insights"):
            return {"data": [{"impressions": "1000", "reach": "800", "frequency": "1.25", "clicks": "40",
                              "inline_link_clicks": "30", "ctr": "4.0", "cpc": "0.5", "cpm": "15", "spend": "15",
                              "actions": [{"action_type": "link_click", "value": "30"}, {"action_type": "purchase", "value": "2"}],
                              "action_values": [{"action_type": "purchase", "value": "90.5"}],
                              "purchase_roas": [{"action_type": "omni_purchase", "value": "6.03"}],
                              "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "120"}],
                              "cost_per_action_type": [{"action_type": "link_click", "value": "0.5"}]}]}
        if metodo == "GET":
            return {"effective_status": "ACTIVE"}
        return {"id": "999"}

    monkeypatch.setattr(auth, "llamar", llamar)
    monkeypatch.setattr(auth, "ad_account_id", lambda: "123")
    return llamadas


def test_campaign_spend_cap(auth_falsa):
    from meta_ads import campaign
    campaign.crear_campaign("X", "OUTCOME_TRAFFIC", spend_cap_centavos=50_000_00)
    assert auth_falsa[-1][2]["spend_cap"] == 50_000_00
    campaign.crear_campaign("X", "OUTCOME_TRAFFIC")
    assert "spend_cap" not in auth_falsa[-1][2]


def test_adset_y_ad_actualizaciones(auth_falsa):
    from meta_ads import ad, adset
    adset.actualizar_presupuesto("77", 2500)
    assert auth_falsa[-1][:3] == ("POST", "77", {"daily_budget": 2500})
    adset.actualizar_estado("77", "ACTIVE")
    assert auth_falsa[-1][:3] == ("POST", "77", {"status": "ACTIVE"})
    ad.actualizar_estado("88", "PAUSED")
    assert auth_falsa[-1][:3] == ("POST", "88", {"status": "PAUSED"})
    with pytest.raises(ValueError):
        adset.actualizar_estado("77", "DELETED")


def test_insights_thruplay_y_ventas(auth_falsa):
    from meta_ads import insights
    r = insights.obtener_resultados("88", objetivo="OUTCOME_TRAFFIC")
    assert r["thruplay"] == 120 and r["thruplay_rate"] == pytest.approx(0.12)
    assert r["compras"] == 2 and r["ingresos"] == 90.5 and r["roas"] == 6.03 and r["alcance"] == 800
    assert r["resultado"] == 30 and r["gasto_usd"] == 15.0 and r["estado_meta"] == "ACTIVE"
    assert "video_thruplay_watched_actions" in auth_falsa[0][3]["fields"]
```

Run: `venv/bin/python -m pytest tests/test_meta_ads_bloque3.py -q` → FAIL.

- [ ] **Step 2: Implementar en el submódulo**

`campaign.py`:

```python
def crear_campaign(nombre, objetivo, dry_run=False, spend_cap_centavos=None):
    ...
    if spend_cap_centavos:
        # Tope total de la campaña (unidad menor de la divisa). Meta lo aplica
        # de por vida; el experimento lo usa como su tope_total.
        payload["spend_cap"] = int(spend_cap_centavos)
    return auth.llamar(...)
```

`adset.py`, al final:

```python
ESTADOS_EDITABLES = ("ACTIVE", "PAUSED")


def actualizar_presupuesto(adset_id, presupuesto_diario_centavos, dry_run=False):
    """Cambia el presupuesto diario del conjunto (unidad menor de la divisa)."""
    return auth.llamar("POST", adset_id, payload={"daily_budget": int(presupuesto_diario_centavos)}, dry_run=dry_run)


def actualizar_estado(adset_id, status, dry_run=False):
    if status not in ESTADOS_EDITABLES:
        raise ValueError(f"Estado no permitido: {status}")
    return auth.llamar("POST", adset_id, payload={"status": status}, dry_run=dry_run)
```

`ad.py`, al final: `actualizar_estado(ad_id, status, dry_run=False)` idéntico (misma validación).

`insights.py`: `CAMPOS_BASICOS += ",video_thruplay_watched_actions,action_values,purchase_roas"`; en `obtener_resultados`, tras calcular `resultado`:

```python
    impresiones = int(float(fila.get("impressions", 0) or 0))
    thruplay = int(_accion(fila.get("video_thruplay_watched_actions"), "video_view"))
    compras = int(_accion(fila.get("actions"), "purchase") or _accion(fila.get("actions"), "omni_purchase"))
    ingresos = _accion(fila.get("action_values"), "purchase") or _accion(fila.get("action_values"), "omni_purchase")
    roas = _accion(fila.get("purchase_roas"), "omni_purchase") or _accion(fila.get("purchase_roas"), "purchase")
```

y en el dict devuelto: `"alcance": <reach>`, `"thruplay": thruplay`, `"thruplay_rate": (thruplay / impresiones) if impresiones else 0.0`, `"compras": compras`, `"ingresos": ingresos`, `"roas": roas`. Conservar todas las claves existentes (`ads.py` las consume).

- [ ] **Step 3: Tests** — `venv/bin/python -m pytest tests/test_meta_ads_bloque3.py tests/test_tareas_meta.py -q` → PASS.

- [ ] **Step 4: Commit en el submódulo y puntero**

```bash
git -C meta_ads add campaign.py adset.py ad.py insights.py
git -C meta_ads commit -m "spend_cap en campaign, presupuesto/estado de adset y ad, thruplay y ventas en insights"
git add meta_ads tests/test_meta_ads_bloque3.py
git commit -m "Actualizar puntero de CreaTvMetaAds: spend_cap, presupuesto por adset, thruplay/ventas"
```

(El push del submódulo lo hace el controlador desde la Mac por HTTPS: `git -C meta_ads push origin HEAD:main`.)

---

### Task 3: `lanzador.py` + tareas del worker (`exp_lanzar`, `exp_refrescar`, periódica)

**Files:**
- Create: `lanzador.py`
- Create: `tareas/experimentos.py`
- Modify: `tareas/__init__.py` (`cargar_todas`), `worker.py` (`PERIODICAS`)
- Test: `tests/test_lanzador.py`, `tests/test_tareas_experimentos.py`

**Interfaces:**
- Consumes: Task 1 (`experimentos.*`), Task 2 (`meta_ads.*`), `meta_conexion.credenciales_ads/cargar`, `tareas.meta._LOCK`, `tareas.meta._miniatura_para_ad`, `tareas.meta.MONEDAS_SIN_DECIMALES`, `trabajos.reportar`, `cola.encolar`.
- Produces:
  - `lanzador.centavos(monto, moneda) -> int`.
  - `lanzador.url_destino(base, pieza_id) -> str` (agrega los utm respetando `?`/`&`).
  - `lanzador.ETAPAS_LANZAR = ["Campaña", "Conjuntos por país", "Anuncios"]`.
  - `lanzador.lanzar(cliente, experimento_id, on_etapa=None) -> str` — crea lo que falte (idempotente), deja `experimento.estado="pausado"`, piezas `pausado`; si falla: `experimento.estado="error"`, `error=<mensaje>`, y relanza. Registra eventos.
  - `lanzador.cambiar_estado(cliente, experimento_id, status, pais=None) -> None` — `status` ACTIVE|PAUSED; sin `pais`: campaña (+ todos los conjuntos y anuncios ya creados); con `pais`: solo ese conjunto y sus anuncios. Actualiza estados locales y evento. Levanta `ValueError` si el experimento no está lanzado.
  - `lanzador.cambiar_presupuesto_pais(cliente, experimento_id, pais, presupuesto_dia) -> None`.
  - `lanzador.refrescar(cliente, experimento_id) -> int` (nº de piezas refrescadas): por cada pieza con `meta_ad_id` trae insights → `experimentos.snapshot`; `estado_meta`; `gasto_acumulado` = suma de la última métrica de cada pieza.
  - `lanzador.cerrar(cliente, experimento_id)` — pausa todo en Meta y `estado="cerrado"`.
  - `tareas.experimentos.job_id_lanzar(cliente, experimento_id) = f"{cliente}__exp{experimento_id}__lanzar"`; `job_id_refrescar(cliente, experimento_id) = f"{cliente}__exp{experimento_id}__refrescar"`.
  - Tipos de tarea: `exp_lanzar` (payload `{cliente, experimento_id}`), `exp_refrescar` (igual), `exp_refrescar_todos` (payload `{}`; periódica cada 7200 s: encola `exp_refrescar` para cada experimento no legado en `corriendo`).

- [ ] **Step 1: Test que falla — `tests/test_lanzador.py`**

```python
import types

import pytest

from tests.test_experimentos_db import PAISES, _pieza


class MetaFalsa:
    """Sustituye los módulos meta_ads.* usados por lanzador con contadores."""
    def __init__(self, fallar_en=None):
        self.llamadas = []
        self.fallar_en = fallar_en
        self.n = 0

    def _id(self, tipo, **kw):
        self.llamadas.append((tipo, kw))
        if self.fallar_en == tipo:
            raise RuntimeError(f"Meta falló en {tipo}")
        self.n += 1
        return {"id": f"{tipo}_{self.n}"}

    def modulos(self):
        campaign = types.SimpleNamespace(crear_campaign=lambda nombre, objetivo, dry_run=False, spend_cap_centavos=None:
                                         self._id("campaign", nombre=nombre, spend_cap=spend_cap_centavos),
                                         actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        adset = types.SimpleNamespace(crear_adset=lambda nombre, cid, obj, targeting, centavos, dias, dry_run=False:
                                      self._id("adset", nombre=nombre, targeting=targeting, centavos=centavos, dias=dias),
                                      actualizar_presupuesto=lambda oid, c, dry_run=False: self._id("presupuesto", oid=oid, centavos=c),
                                      actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        creative = types.SimpleNamespace(subir_video=lambda url, titulo="", dry_run=False, esperar_seg=180: "vid_1",
                                         crear_creative_video=lambda nombre, vid, mini, msg, link, cta_type="LEARN_MORE", instagram_user_id=None, dry_run=False:
                                         self._id("creative", link=link))
        ad = types.SimpleNamespace(crear_ad=lambda nombre, adset_id, creative_id, dry_run=False: self._id("ad", adset_id=adset_id),
                                   actualizar_estado=lambda oid, status, dry_run=False: self._id("estado", oid=oid, status=status))
        insights = types.SimpleNamespace(obtener_resultados=lambda ad_id, objetivo=None:
                                         {"impresiones": 100, "reach": 90, "alcance": 90, "clics_enlace": 4, "ctr": 4.0, "cpc": 0.5,
                                          "gasto_usd": 2.0, "thruplay": 10, "thruplay_rate": 0.1, "compras": 0, "ingresos": 0.0,
                                          "roas": 0.0, "estado_meta": "ACTIVE", "estado_meta_texto": "Activo", "motivo_rechazo": None})
        auth = types.SimpleNamespace(configurar=lambda *a, **k: None, limpiar=lambda: None)
        return campaign, adset, creative, ad, insights, auth


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import experimentos as ex
    import lanzador
    meta = MetaFalsa()
    campaign, adset, creative, ad, insights, auth = meta.modulos()
    monkeypatch.setattr(lanzador, "meta_campaign", campaign)
    monkeypatch.setattr(lanzador, "meta_adset", adset)
    monkeypatch.setattr(lanzador, "meta_creative", creative)
    monkeypatch.setattr(lanzador, "meta_ad", ad)
    monkeypatch.setattr(lanzador, "meta_insights", insights)
    monkeypatch.setattr(lanzador, "meta_auth", auth)
    monkeypatch.setattr(lanzador.meta_conexion, "credenciales_ads", lambda c: {"token": "t", "ad_account_id": "1", "page_id": "2", "ig_user_id": None})
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(lanzador, "_miniatura_para_ad", lambda cliente, ad_id, url: "https://r2/mini.jpg")
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://tienda.co/p?x=1", "COP")
    ex.agregar_pieza("acme", eid, f_co, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ex.agregar_pieza("acme", eid, clon, "MX")
    return {"ex": ex, "lanzador": lanzador, "meta": meta, "eid": eid, "monkeypatch": monkeypatch}


def test_centavos_y_url(base_temporal):
    import lanzador
    assert lanzador.centavos(20000, "COP") == 2000000 and lanzador.centavos(1000, "CLP") == 1000
    assert lanzador.url_destino("https://t.co/p", 7) == "https://t.co/p?utm_source=creatv&utm_medium=meta&utm_content=7"
    assert lanzador.url_destino("https://t.co/p?x=1", 7).startswith("https://t.co/p?x=1&utm_source=creatv")


def test_lanzar_crea_campana_conjuntos_y_anuncios(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    etapas = []
    lz.lanzar("acme", eid, on_etapa=etapas.append)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("campaign") == 1 and tipos.count("adset") == 2 and tipos.count("ad") == 3
    assert meta.llamadas[0][1]["spend_cap"] == 50000000
    adsets = [kw for t, kw in meta.llamadas if t == "adset"]
    assert adsets[0]["targeting"]["geo_locations"]["countries"] == ["CO"] and adsets[0]["centavos"] == 2000000
    assert adsets[1]["targeting"]["geo_locations"]["countries"] == ["MX"] and adsets[1]["centavos"] == 15000
    creativos = [kw for t, kw in meta.llamadas if t == "creative"]
    assert all("utm_content=" in c["link"] for c in creativos)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "pausado" and e["meta_campaign_id"] == "campaign_1"
    assert {p["pais"]: p["meta_adset_id"] for p in e["paises"]} == {"CO": "adset_2", "MX": "adset_3"}
    assert all(p["estado"] == "pausado" and p["meta_ad_id"] for p in e["piezas"])
    assert etapas == lz.ETAPAS_LANZAR
    assert any(ev["tipo"] == "lanzamiento" for ev in e["eventos"])


def test_lanzar_retoma_sin_duplicar(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    meta.fallar_en = "ad"
    with pytest.raises(RuntimeError):
        lz.lanzar("acme", eid)
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "Meta falló" in e["error"] and e["meta_campaign_id"]
    assert all(p["meta_adset_id"] for p in e["paises"])
    meta.fallar_en = None
    meta.llamadas.clear()
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert "campaign" not in tipos and "adset" not in tipos and tipos.count("ad") == 3
    assert ex.obtener("acme", eid)["estado"] == "pausado"


def test_lanzar_exige_piezas_y_estado(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    e2 = ex.crear("acme", "Vacío", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    with pytest.raises(ValueError):
        lz.lanzar("acme", e2)
    ex.actualizar("acme", eid, estado="cerrado")
    with pytest.raises(ValueError):
        lz.lanzar("acme", eid)


def test_cambiar_estado_y_presupuesto(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    with pytest.raises(ValueError):
        lz.cambiar_estado("acme", eid, "ACTIVE")
    lz.lanzar("acme", eid)
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ids = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert ids[0] == "campaign_1" and len(ids) == 1 + 2 + 3
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and all(p["estado"] == "activo" for p in e["piezas"]) and all(p["estado"] == "activo" for p in e["paises"])
    meta.llamadas.clear()
    lz.cambiar_estado("acme", eid, "PAUSED", pais="MX")
    ids = [kw["oid"] for t, kw in meta.llamadas if t == "estado"]
    assert ids == ["adset_3", "ad_6"]
    e = ex.obtener("acme", eid)
    assert e["estado"] == "corriendo" and [p["estado"] for p in e["paises"]] == ["activo", "pausado"]
    assert [p["estado"] for p in e["piezas"]] == ["activo", "activo", "pausado"]
    lz.cambiar_presupuesto_pais("acme", eid, "MX", 300)
    assert meta.llamadas[-1] == ("presupuesto", {"oid": "adset_3", "centavos": 30000})
    e = ex.obtener("acme", eid)
    assert e["paises"][1]["presupuesto_dia"] == 300.0 and e["piezas"][2]["presupuesto_dia_actual"] == 300.0
    lz.cerrar("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "cerrado"


def test_refrescar_guarda_snapshots(entorno):
    ex, lz, eid = entorno["ex"], entorno["lanzador"], entorno["eid"]
    assert lz.refrescar("acme", eid) == 0
    lz.lanzar("acme", eid)
    assert lz.refrescar("acme", eid) == 3
    e = ex.obtener("acme", eid)
    assert e["gasto_acumulado"] == 6.0
    m = e["piezas"][0]["metricas"]
    assert m["impresiones"] == 100 and m["alcance"] == 90 and m["gasto"] == 2.0 and m["thruplay"] == 10
    assert m["estado_meta_texto"] == "Activo" and e["piezas"][0]["estado_meta"] == "ACTIVE"
```

Run → FAIL (`ModuleNotFoundError: lanzador`).

- [ ] **Step 2: Implementar `lanzador.py`**

```python
"""
Lanzador multi-país (spec §4): traduce un experimento a objetos de Meta —
1 campaña (spend_cap = tope total) → 1 conjunto por país (presupuesto diario
propio, targeting país + edad) → 1 anuncio por pieza — y guarda cada id apenas
Meta lo devuelve, así un reintento retoma donde quedó sin duplicar nada. Todo
nace PAUSED: activar es otro clic (cambiar_estado). Las credenciales se cargan
y limpian bajo el lock de tareas.meta (mismo motivo que allá).
"""
import experimentos
import meta_conexion
from meta_ads import ad as meta_ad, adset as meta_adset, auth as meta_auth, campaign as meta_campaign
from meta_ads import creative as meta_creative, insights as meta_insights
from meta_ads.targeting import Targeting
from tareas.meta import MONEDAS_SIN_DECIMALES, _LOCK, _miniatura_para_ad

ETAPAS_LANZAR = ["Campaña", "Conjuntos por país", "Anuncios"]
# Meta rechaza spend_cap por debajo de ~100 USD; por debajo no se manda.
SPEND_CAP_MINIMO_USD = 100.0
_MIN_POR_MONEDA = {"COP": 400000.0, "MXN": 2000.0, "BRL": 600.0, "EUR": 100.0, "PEN": 400.0, "CLP": 100000.0, "ARS": 100000.0, "USD": 100.0}
_SNAP_DESDE_INSIGHTS = {"impresiones": "impresiones", "alcance": "alcance", "frecuencia": "frecuencia", "clics": "clics",
                        "clics_enlace": "clics_enlace", "ctr": "ctr", "cpc": "cpc", "cpm": "cpm", "thruplay": "thruplay",
                        "thruplay_rate": "thruplay_rate", "gasto_usd": "gasto", "compras": "compras", "ingresos": "ingresos", "roas": "roas",
                        "costo_por_resultado": "cpa"}


def centavos(monto, moneda):
    return int(round(float(monto) * (1 if moneda in MONEDAS_SIN_DECIMALES else 100)))


def url_destino(base, pieza_id):
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}utm_source=creatv&utm_medium=meta&utm_content={pieza_id}"


def _con_credenciales(cliente, fn):
    with _LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            return fn(creds)
        finally:
            meta_auth.limpiar()


def lanzar(cliente, experimento_id, on_etapa=None):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None:
        raise ValueError("Ese experimento no existe.")
    if ex["estado"] not in ("armando", "error", "lanzando"):
        raise ValueError("Ese experimento ya fue lanzado.")
    if not ex["piezas"]:
        raise ValueError("El experimento no tiene piezas: agrega al menos una antes de lanzar.")
    paises_con_piezas = {p["pais"] for p in ex["piezas"]}
    faltan = [p["pais"] for p in ex["paises"] if p["pais"] not in paises_con_piezas]
    if faltan:
        raise ValueError(f"Sin piezas para: {', '.join(faltan)}. Agrega una pieza por país o quita el país.")
    moneda = ex["moneda"] or (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    etapa = on_etapa or (lambda n: None)
    experimentos.actualizar(cliente, experimento_id, estado="lanzando", error=None)

    def _correr(creds):
        etapa(ETAPAS_LANZAR[0])
        campaign_id = ex["meta_campaign_id"]
        if not campaign_id:
            cap = centavos(ex["tope_total"], moneda) if float(ex["tope_total"] or 0) >= _MIN_POR_MONEDA.get(moneda, SPEND_CAP_MINIMO_USD) else None
            campaign_id = meta_campaign.crear_campaign(ex["nombre"], ex["objetivo_meta"], spend_cap_centavos=cap)["id"]
            experimentos.actualizar(cliente, experimento_id, meta_campaign_id=campaign_id)
            experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", "Campaña creada en Meta (en pausa)",
                                          {"campaign_id": campaign_id, "spend_cap": cap})
        etapa(ETAPAS_LANZAR[1])
        adsets = {}
        for p in ex["paises"]:
            adset_id = p.get("meta_adset_id")
            if not adset_id:
                targeting = Targeting().edad(int(ex["edad_min"] or 18), int(ex["edad_max"] or 65)).paises([p["pais"]]).to_dict()
                adset_id = meta_adset.crear_adset(f"{ex['nombre']} — {p['pais']}", campaign_id, ex["objetivo_meta"], targeting,
                                                  centavos(p["presupuesto_dia"], moneda), int(ex["dias"] or 7))["id"]
                experimentos.actualizar_pais(cliente, experimento_id, p["pais"], meta_adset_id=adset_id, estado="pausado")
                experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", f"Conjunto {p['pais']} creado",
                                              {"adset_id": adset_id, "presupuesto_dia": p["presupuesto_dia"]})
            adsets[p["pais"]] = adset_id
        etapa(ETAPAS_LANZAR[2])
        for pz in ex["piezas"]:
            if pz["meta_ad_id"]:
                continue
            experimentos.actualizar_pieza(cliente, pz["id"], estado="publicando", meta_adset_id=adsets[pz["pais"]])
            creative_id = pz["meta_creative_id"]
            if not creative_id:
                video_id = meta_creative.subir_video(pz["url_video"], titulo=pz["nombre"])
                mini = pz["url_miniatura"] or _miniatura_para_ad(cliente, f"exp{experimento_id}_{pz['id']}", pz["url_video"])
                creative_id = meta_creative.crear_creative_video(
                    f"{pz['nombre']} — {pz['pais']}", video_id, mini, ex["nombre"],
                    url_destino(ex["destino_url"], pz["pieza_id"]), instagram_user_id=creds.get("ig_user_id"))["id"]
                experimentos.actualizar_pieza(cliente, pz["id"], meta_creative_id=creative_id)
            ad_id = meta_ad.crear_ad(f"{pz['nombre']} — {pz['pais']}", adsets[pz["pais"]], creative_id)["id"]
            experimentos.actualizar_pieza(cliente, pz["id"], meta_ad_id=ad_id, estado="pausado",
                                          presupuesto_dia_actual=next(p["presupuesto_dia"] for p in ex["paises"] if p["pais"] == pz["pais"]))
            experimentos.registrar_evento(cliente, experimento_id, "lanzamiento", f"Anuncio creado: {pz['nombre']} ({pz['pais']})",
                                          {"ad_id": ad_id}, ep_id=pz["id"])

    try:
        _con_credenciales(cliente, _correr)
    except Exception as e:
        experimentos.actualizar(cliente, experimento_id, estado="error", error=str(e))
        experimentos.registrar_evento(cliente, experimento_id, "error", f"Falló el lanzamiento: {e}")
        raise
    experimentos.actualizar(cliente, experimento_id, estado="pausado", error=None)
    return "Experimento en Meta, en pausa. Actívalo cuando quieras empezar a gastar."


def _piezas_de(ex, pais=None):
    return [p for p in ex["piezas"] if p["meta_ad_id"] and (pais is None or p["pais"] == pais)]


def cambiar_estado(cliente, experimento_id, status, pais=None):
    if status not in ("ACTIVE", "PAUSED"):
        raise ValueError("Estado no permitido.")
    ex = experimentos.obtener(cliente, experimento_id)
    if ex is None or not ex["meta_campaign_id"] or ex["estado"] in ("armando", "lanzando", "error"):
        raise ValueError("Ese experimento todavía no está en Meta.")
    local = "activo" if status == "ACTIVE" else "pausado"

    def _correr(_creds):
        if pais is None:
            meta_campaign.actualizar_estado(ex["meta_campaign_id"], status)
            for p in ex["paises"]:
                if p.get("meta_adset_id"):
                    meta_adset.actualizar_estado(p["meta_adset_id"], status)
                    experimentos.actualizar_pais(cliente, experimento_id, p["pais"], estado=local)
        else:
            p = next((p for p in ex["paises"] if p["pais"] == pais), None)
            if not p or not p.get("meta_adset_id"):
                raise ValueError("Ese país no tiene conjunto en Meta.")
            meta_adset.actualizar_estado(p["meta_adset_id"], status)
            experimentos.actualizar_pais(cliente, experimento_id, pais, estado=local)
        for pz in _piezas_de(ex, pais):
            meta_ad.actualizar_estado(pz["meta_ad_id"], status)
            experimentos.actualizar_pieza(cliente, pz["id"], estado=local)

    _con_credenciales(cliente, _correr)
    if pais is None:
        experimentos.actualizar(cliente, experimento_id, estado="corriendo" if status == "ACTIVE" else "pausado")
    elif status == "ACTIVE" and ex["estado"] != "corriendo":
        experimentos.actualizar(cliente, experimento_id, estado="corriendo")
    experimentos.registrar_evento(cliente, experimento_id, "estado",
                                  f"{'Activado' if status == 'ACTIVE' else 'Pausado'}{' ' + pais if pais else ' todo el experimento'}")


def cambiar_presupuesto_pais(cliente, experimento_id, pais, presupuesto_dia):
    ex = experimentos.obtener(cliente, experimento_id)
    p = next((p for p in (ex or {}).get("paises", []) if p["pais"] == pais), None)
    if not p or not p.get("meta_adset_id"):
        raise ValueError("Ese país no tiene conjunto en Meta.")
    moneda = ex["moneda"] or "USD"
    _con_credenciales(cliente, lambda _c: meta_adset.actualizar_presupuesto(p["meta_adset_id"], centavos(presupuesto_dia, moneda)))
    experimentos.actualizar_pais(cliente, experimento_id, pais, presupuesto_dia=float(presupuesto_dia))
    for pz in _piezas_de(ex, pais):
        experimentos.actualizar_pieza(cliente, pz["id"], presupuesto_dia_actual=float(presupuesto_dia))
    experimentos.registrar_evento(cliente, experimento_id, "presupuesto", f"Presupuesto diario de {pais}: {presupuesto_dia} {moneda}",
                                  {"anterior": p["presupuesto_dia"], "nuevo": float(presupuesto_dia)})


def refrescar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    piezas = _piezas_de(ex) if ex else []
    if not piezas:
        return 0

    def _correr(_creds):
        n = 0
        for pz in piezas:
            r = meta_insights.obtener_resultados(pz["meta_ad_id"], objetivo=ex["objetivo_meta"])
            snap = {dest: r.get(src) for src, dest in _SNAP_DESDE_INSIGHTS.items() if src in r}
            snap["fuente_ventas"] = "meta" if (r.get("compras") or 0) > 0 else "ninguna"
            for k in ("resultado_nombre", "resultado", "estado_meta_texto", "motivo_rechazo"):
                snap[k] = r.get(k)
            experimentos.snapshot(pz["id"], snap)
            experimentos.actualizar_pieza(cliente, pz["id"], estado_meta=r.get("estado_meta"))
            n += 1
        return n

    n = _con_credenciales(cliente, _correr)
    gasto = sum(float((p["metricas"] or {}).get("gasto") or 0) for p in experimentos.piezas(cliente, experimento_id))
    experimentos.actualizar(cliente, experimento_id, gasto_acumulado=round(gasto, 2))
    return n


def cerrar(cliente, experimento_id):
    ex = experimentos.obtener(cliente, experimento_id)
    if ex and ex["meta_campaign_id"] and ex["estado"] in ("corriendo", "pausado"):
        cambiar_estado(cliente, experimento_id, "PAUSED")
    experimentos.actualizar(cliente, experimento_id, estado="cerrado")
    experimentos.registrar_evento(cliente, experimento_id, "estado", "Experimento cerrado")
```

- [ ] **Step 3: Test que falla — `tests/test_tareas_experimentos.py`**

```python
import pytest

from tests.test_experimentos_db import PAISES


def test_job_ids():
    from tareas import experimentos as te
    assert te.job_id_lanzar("acme", 3) == "acme__exp3__lanzar"
    assert te.job_id_refrescar("acme", 3) == "acme__exp3__refrescar"


def test_exp_lanzar_llama_lanzador_y_reporta(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from tareas import experimentos as te
    llamadas = []
    monkeypatch.setattr(te.lanzador, "lanzar", lambda c, e, on_etapa=None: (on_etapa("Campaña"), llamadas.append((c, e)), "ok")[-1])
    reportes = []
    monkeypatch.setattr(trabajos, "reportar", lambda job_id, **kw: reportes.append((job_id, kw)))
    tareas.cargar_todas()
    fn = tareas.REGISTRO["exp_lanzar"]
    assert fn({"payload": {"cliente": "acme", "experimento_id": 3}, "job_id": "acme__exp3__lanzar"}) == "ok"
    assert llamadas == [("acme", 3)] and reportes[0][1]["etapa"] == "Campaña"


def test_exp_lanzar_interrumpida_marca_error(base_temporal):
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    tareas.AL_INTERRUMPIR["exp_lanzar"]({"payload": {"cliente": "acme", "experimento_id": eid}}, "se cayó")
    e = ex.obtener("acme", eid)
    assert e["estado"] == "error" and "se cayó" in e["error"]
    ex.actualizar("acme", eid, estado="pausado", error=None)
    tareas.AL_INTERRUMPIR["exp_lanzar"]({"payload": {"cliente": "acme", "experimento_id": eid}}, "otra")
    assert ex.obtener("acme", eid)["estado"] == "pausado"  # no pisa estados finales


def test_exp_refrescar_todos_encola_los_corriendo(base_temporal, monkeypatch):
    import cola
    import experimentos as ex
    import tareas
    tareas.cargar_todas()
    e1 = ex.crear("acme", "A", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e2 = ex.crear("acme", "B", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    e3 = ex.crear("otro", "C", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", e1, estado="corriendo")
    ex.actualizar("otro", e3, estado="corriendo")
    encolados = []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw.get("job_id"))))
    tareas.REGISTRO["exp_refrescar_todos"]({"payload": {}})
    assert sorted(x[1]["experimento_id"] for x in encolados) == sorted([e1, e3])
    assert all(x[0] == "exp_refrescar" for x in encolados)


def test_periodica_registrada():
    import worker
    assert ("exp_refrescar_todos", 7200) in worker.PERIODICAS
```

Comprobar los nombres reales del registro en `tareas/__init__.py` (`REGISTRO`, `AL_INTERRUMPIR` o como se llamen — leer el archivo y ajustar el test al nombre real; no cambiar el registro).

- [ ] **Step 4: Implementar `tareas/experimentos.py`, registrar y periódica**

```python
"""
Tareas del worker para Experimentos: lanzar (crea objetos en Meta, en pausa;
max_intentos=1 y hook de interrupción como meta_publicar), refrescar métricas
de un experimento y la periódica que refresca todos los que corren.
"""
import sqlalchemy as sa

import cola
import db
import experimentos
import lanzador
import trabajos
from tareas import al_interrumpir, registrar


def job_id_lanzar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__lanzar"


def job_id_refrescar(cliente, experimento_id):
    return f"{cliente}__exp{experimento_id}__refrescar"


@al_interrumpir("exp_lanzar")
def interrumpida(tarea, mensaje):
    p = tarea["payload"]
    ex = experimentos.obtener(p["cliente"], p["experimento_id"])
    if ex and ex["estado"] == "lanzando":
        experimentos.actualizar(p["cliente"], p["experimento_id"], estado="error", error=mensaje)


@registrar("exp_lanzar")
def exp_lanzar(tarea):
    p = tarea["payload"]
    job_id = tarea.get("job_id")
    return lanzador.lanzar(p["cliente"], p["experimento_id"],
                           on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))


@registrar("exp_refrescar")
def exp_refrescar(tarea):
    p = tarea["payload"]
    n = lanzador.refrescar(p["cliente"], p["experimento_id"])
    return f"Métricas actualizadas ({n} anuncios)."


@registrar("exp_refrescar_todos")
def exp_refrescar_todos(tarea):
    with db.conectar() as con:
        filas = con.execute(sa.select(db.experimento.c.id, db.experimento.c.cliente).where(
            db.experimento.c.legado.is_(False), db.experimento.c.estado == "corriendo")).all()
    for eid, cliente in filas:
        cola.encolar("exp_refrescar", {"cliente": cliente, "experimento_id": eid}, cliente=cliente,
                     job_id=job_id_refrescar(cliente, eid), duracion_estimada=30, max_intentos=2)
    return f"{len(filas)} experimentos en cola."
```

`tareas/__init__.py`: agregar `tareas.experimentos` a la lista de `cargar_todas`. `worker.py`: `PERIODICAS = [("exp_refrescar_todos", 7200)]`. Revisar cómo `worker.ejecutar` pasa la tarea a la función (¿incluye `job_id` en el dict? — leer `worker.py`/`cola.reclamar` y, si no, tomar el job_id de `tarea["job_id"]` como hacen `tareas/final_edition.py`; copiar ese patrón exacto).

- [ ] **Step 5: Tests** — `venv/bin/python -m pytest tests/test_lanzador.py tests/test_tareas_experimentos.py tests/test_worker*.py -q` → PASS; luego suite completa.

- [ ] **Step 6: Commit**

```bash
git add lanzador.py tareas/experimentos.py tareas/__init__.py worker.py tests/test_lanzador.py tests/test_tareas_experimentos.py
git commit -m "Motor: lanzador multi-país (campaña → conjunto por país → anuncio por pieza) + tareas exp_lanzar/exp_refrescar + periódica 2 h"
```

---

### Task 4: Rutas `exp_*` en `dashboard.py`

**Files:**
- Modify: `dashboard.py`
- Test: `tests/test_rutas_experimentos.py`

**Interfaces:**
- Consumes: Tasks 1 y 3; `PRESUPUESTO_MINIMO_DIARIO`, `_ENV_LOCK`, `trabajos.encolar/en_curso`, `meta_conexion.estado/cargar`, `fe_tipos.PAISES`.
- Produces (todas bajo `/cliente/<cliente>/experimentos...`, POST salvo que se diga, redirigen a `ver_cliente` con `_anchor="experimentos"` y `flash`):
  - `exp_crear` `/experimentos/nuevo`: form `nombre`, `objetivo` (∈ `OBJETIVOS_VALIDOS_FASE1`), `paises[]` (códigos de `PAISES`), `presupuesto_<pais>` (≥ mínimo diario de la moneda de la cuenta), `dias` (1–90), `tope_total` (> 0), `destino_url` (http), `edad_min`/`edad_max` (13–65). Moneda = `meta_conexion.cargar(cliente)["moneda"]` o "USD". Si Meta no está conectado: flash error, no crea.
  - `exp_agregar_pieza` `/experimentos/<int:eid>/piezas`: form `pieza_id` (o `legado_id`) + `pais`; valida elegibilidad (`experimentos.elegibles`: final solo a su país; clon a cualquiera de los del experimento) y estado `armando|error` sin campaña.
  - `exp_quitar_pieza` `/experimentos/<int:eid>/piezas/<int:ep_id>/quitar`.
  - `exp_lanzar` `/experimentos/<int:eid>/lanzar`: valida estado + piezas por país (mismas reglas que `lanzador.lanzar`, para mostrar el error en flash sin encolar), `experimentos.actualizar(estado="lanzando")`, `trabajos.encolar(job_id_lanzar, "exp_lanzar", {cliente, experimento_id}, cliente=, duracion_estimada=120, etapas=ETAPAS_LANZAR, max_intentos=1)`.
  - `exp_estado` `/experimentos/<int:eid>/estado`: form `estado` (ACTIVE|PAUSED), `pais` opcional → `lanzador.cambiar_estado` inline bajo `_ENV_LOCK` (como `cambiar_estado_ad`); ValueError → flash.
  - `exp_presupuesto` `/experimentos/<int:eid>/presupuesto`: form `pais`, `presupuesto_dia` (≥ mínimo) → `lanzador.cambiar_presupuesto_pais` inline.
  - `exp_refrescar` `/experimentos/<int:eid>/refrescar`: encola `exp_refrescar` (job `job_id_refrescar`, `max_intentos=1`, duración 30).
  - `exp_cerrar` `/experimentos/<int:eid>/cerrar`: `lanzador.cerrar` inline.
  - `exp_meter_pieza` `/experimentos/meter`: desde Crear — form `legado_id`, `experimento_id`, `pais` (para clones; las finales usan su país) → resuelve `creative_flow.pieza_id_por_legado` y llama la misma lógica de `exp_agregar_pieza`; redirige con `_anchor="creativeflowplus"`.
  - Contexto de `ver_cliente`: `experimentos=experimentos.cargar(cliente)`, `experimentos_armando=[e for e in experimentos if e["estado"] in ("armando","error") and not e["meta_campaign_id"]]`, `elegibles_exp=experimentos.elegibles(cliente)`, `trabajos_exp={eid: {"job_id": ...}}` para jobs `job_id_lanzar`/`job_id_refrescar` en curso, `objetivos_exp=OBJETIVOS_VALIDOS_FASE1`, `minimo_diario_exp=PRESUPUESTO_MINIMO_DIARIO.get(moneda)`, `moneda_exp`.
  - `_reconciliar_huerfanos`: experimentos `lanzando` sin job en curso → `estado="error", error="Se interrumpió el lanzamiento; revisa Ads Manager y vuelve a intentar."`.

- [ ] **Step 1: Tests que fallan — `tests/test_rutas_experimentos.py`** (patrón `_cliente_admin` y captura de `encolar` como en `tests/test_rutas_final_edition.py`; monkeypatch `dashboard.meta_conexion.cargar` → `{"moneda": "COP"}` y `dashboard.meta_conexion.estado` → `{"estado": "conectado", "verificado": True, "detalle": {}}`):

```python
import pytest

from tests.test_experimentos_db import PAISES, _pieza


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


FORM = {"nombre": "Cojín", "objetivo": "OUTCOME_TRAFFIC", "paises": ["CO", "MX"], "presupuesto_CO": "20000",
        "presupuesto_MX": "150", "dias": "7", "tope_total": "500000", "destino_url": "https://tienda.co/p",
        "edad_min": "18", "edad_max": "55"}


def test_crear_experimento(app):
    import experimentos as ex
    r = app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert r.status_code == 302 and "experimentos" in r.headers["Location"]
    e = ex.cargar("acme")[0]
    assert e["nombre"] == "Cojín" and e["moneda"] == "COP" and e["edad_max"] == 55
    assert [(p["pais"], p["presupuesto_dia"]) for p in e["paises"]] == [("CO", 20000.0), ("MX", 150.0)]


def test_crear_valida_minimo_y_destino(app):
    import experimentos as ex
    malo = dict(FORM, presupuesto_CO="100")   # < 4000 COP
    app["c"].post("/cliente/acme/experimentos/nuevo", data=malo)
    assert ex.cargar("acme") == []
    malo = dict(FORM, destino_url="tienda.co")
    app["c"].post("/cliente/acme/experimentos/nuevo", data=malo)
    assert ex.cargar("acme") == []


def test_crear_exige_meta_conectado(app, monkeypatch):
    import experimentos as ex
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert ex.cargar("acme") == []


def test_agregar_pieza_respeta_pais_de_la_final(app, base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": f_co, "pais": "MX"})   # final CO a MX: no
    assert ex.piezas("acme", eid) == []
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": f_co, "pais": "CO"})
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "MX"})
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "US"})   # país fuera del experimento: no
    assert [(p["pieza_id"], p["pais"]) for p in ex.piezas("acme", eid)] == [(f_co, "CO"), (clon, "MX")]
    ep = ex.piezas("acme", eid)[0]["id"]
    c.post(f"/cliente/acme/experimentos/{eid}/piezas/{ep}/quitar")
    assert len(ex.piezas("acme", eid)) == 1


def test_meter_desde_crear(app, base_temporal):
    import experimentos as ex
    _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    r = app["c"].post("/cliente/acme/experimentos/meter", data={"legado_id": "cf_1__es_CO", "experimento_id": eid})
    assert "creativeflowplus" in r.headers["Location"]
    assert [p["pais"] for p in ex.piezas("acme", eid)] == ["CO"]


def test_lanzar_encola_una_sola_vez_y_valida(app, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert app["encolados"] == [] and ex.obtener("acme", eid)["estado"] == "armando"   # sin piezas
    ex.agregar_pieza("acme", eid, clon, "CO")
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert app["encolados"] == []   # falta MX
    ex.agregar_pieza("acme", eid, clon, "MX")
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert len(app["encolados"]) == 1
    t = app["encolados"][0]
    assert t["tipo"] == "exp_lanzar" and t["max_intentos"] == 1 and t["job_id"] == f"acme__exp{eid}__lanzar"
    assert ex.obtener("acme", eid)["estado"] == "lanzando"
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "CO"})   # ya no acepta piezas
    assert len(ex.piezas("acme", eid)) == 2


def test_estado_presupuesto_refrescar_cerrar(app, base_temporal, monkeypatch):
    import experimentos as ex
    d = app["dashboard"]
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    llamadas = []
    monkeypatch.setattr(d.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", s, pais)))
    monkeypatch.setattr(d.lanzador, "cambiar_presupuesto_pais", lambda c, e, p, v: llamadas.append(("presupuesto", p, v)))
    monkeypatch.setattr(d.lanzador, "cerrar", lambda c, e: llamadas.append(("cerrar",)))
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "ACTIVE"})
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "PAUSED", "pais": "MX"})
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "DELETED"})
    c.post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "MX", "presupuesto_dia": "300"})
    c.post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "MX", "presupuesto_dia": "10"})   # < mínimo COP
    c.post(f"/cliente/acme/experimentos/{eid}/refrescar")
    c.post(f"/cliente/acme/experimentos/{eid}/cerrar")
    assert llamadas == [("estado", "ACTIVE", None), ("estado", "PAUSED", "MX"), ("presupuesto", "MX", 300.0), ("cerrar",)]
    assert app["encolados"][-1]["tipo"] == "exp_refrescar" and app["encolados"][-1]["max_intentos"] == 1


def test_ver_cliente_incluye_experimentos(app, base_temporal):
    import experimentos as ex
    ex.crear("acme", "Visible", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200 and b"Visible" in r.data and b"Experimentos" in r.data


def test_reconciliar_lanzando_huerfano(app, base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    app["dashboard"]._reconciliar_huerfanos()
    assert ex.obtener("acme", eid)["estado"] == "error"
```

`test_ver_cliente_incluye_experimentos` pasa solo con la Task 5 (template); dejarlo escrito y marcarlo `@pytest.mark.xfail(reason="template en Task 5", strict=True)` hasta entonces; la Task 5 quita el xfail. Si `GET /cliente/acme` exige que exista la carpeta `clientes/acme`, crear una carpeta temporal en el fixture (ver cómo lo hace `tests/test_rutas_final_edition.py`).

- [ ] **Step 2: Implementar rutas** — seguir el estilo de `publicar_ad`/`cambiar_estado_ad`/`fe_producir` (imports arriba: `import experimentos`, `import lanzador`, `from tareas import experimentos as tareas_exp`). Validación de `exp_crear`:

```python
@app.route("/cliente/<cliente>/experimentos/nuevo", methods=["POST"])
def exp_crear(cliente):
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if meta_conexion.estado(cliente).get("estado") != "conectado":
        flash("Conecta Meta en Configuración antes de crear un experimento.", "error"); return volver
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    nombre = (request.form.get("nombre") or "").strip()[:200]
    objetivo = request.form.get("objetivo") or ""
    codigos = [p for p in request.form.getlist("paises") if p in fe_tipos.PAISES]
    destino = (request.form.get("destino_url") or "").strip()
    try:
        dias = int(request.form.get("dias") or 7); tope = float(request.form.get("tope_total") or 0)
        edad_min = int(request.form.get("edad_min") or 18); edad_max = int(request.form.get("edad_max") or 65)
        paises = [{"pais": p, "idioma": fe_tipos.PAISES[p]["idioma"], "presupuesto_dia": float(request.form.get(f"presupuesto_{p}") or 0)} for p in codigos]
    except ValueError:
        flash("Revisa los números del formulario.", "error"); return volver
    if not nombre or objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos or not destino.startswith("http") \
            or not (1 <= dias <= 90) or tope <= 0 or not (13 <= edad_min <= edad_max <= 65):
        flash("Faltan datos: nombre, objetivo, al menos un país, días (1–90), tope, edades (13–65) y una URL de destino http(s).", "error"); return volver
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(f"El presupuesto diario mínimo es {minimo} {moneda} (revisa {', '.join(bajos)}).", "error"); return volver
    eid = experimentos.crear(cliente, nombre, paises, objetivo, dias, tope, destino, moneda, edad_min, edad_max)
    experimentos.registrar_evento(cliente, eid, "creado", f"Experimento creado con {len(paises)} países")
    flash(f"Experimento «{nombre}» creado. Agrega piezas y lánzalo cuando esté listo.")
    return volver
```

`_agregar_pieza_validada(cliente, eid, pieza_id, pais)` compartido por `exp_agregar_pieza` y `exp_meter_pieza`: busca en `experimentos.elegibles(cliente)` por `pieza_id`; si `tipo == "final"` usa `p["pais"]` (ignora el del form); si clon exige `pais` ∈ países del experimento; experimento en `armando|error` sin `meta_campaign_id`; devuelve mensaje de error o None. Las rutas inline a Meta (`exp_estado`, `exp_presupuesto`, `exp_cerrar`) van dentro de `with _ENV_LOCK:` y capturan `ValueError`/`Exception` → flash. `_reconciliar_huerfanos`: añadir bloque que recorre `experimentos` con `estado == "lanzando"` de todos los clientes (query directa a `db.experimento`) y no `trabajos.en_curso(job_id_lanzar)` → `actualizar(estado="error", ...)`.

- [ ] **Step 3: Tests** — `venv/bin/python -m pytest tests/test_rutas_experimentos.py -q` → PASS (salvo el xfail). Suite completa verde.

- [ ] **Step 4: Commit** — `git add dashboard.py tests/test_rutas_experimentos.py && git commit -m "Experimentos: rutas crear/piezas/lanzar/estado/presupuesto/refrescar/cerrar + meter desde Crear"`.

---

### Task 5: UI — pestaña Experimentos (árbol), sidebar, "Meter en experimento" en Crear, CSS

**Files:**
- Create: `templates/_tab_experimentos.html`
- Modify: `templates/_sidebar.html`, `templates/cliente.html`, `templates/_tab_creativeflowplus.html`, `static/style.css`
- Test: quitar el `xfail` en `tests/test_rutas_experimentos.py::test_ver_cliente_incluye_experimentos`; verificación manual en navegador (controlador).

**Interfaces:**
- Consumes: contexto de Task 4 (`experimentos`, `experimentos_armando`, `elegibles_exp`, `trabajos_exp`, `objetivos_exp`, `minimo_diario_exp`, `moneda_exp`, `paises_fe`, `capacidades_meta`), `iniciarPolling(jobId, contenedorId)` de `base.html`.

- [ ] **Step 1: Sidebar y sección** — en `_sidebar.html`, entre Crear y Campañas, botón `data-tab="experimentos"` con título "Experimentos" (ícono: tres nodos en árbol, SVG simple `<circle cx="12" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="19" r="2"/><path d="M12 7v4M12 11l-6 6M12 11l6 6"/>`). En `cliente.html`, después de la sección `tab-creativeflowplus`: `<section id="tab-experimentos" class="tab-panel" role="tabpanel">{% include "_tab_experimentos.html" %}</section>`. Actualizar el comentario de `_sidebar.html` (lista de claves).

- [ ] **Step 2: `_tab_experimentos.html`** — estructura:

```jinja
<div class="panel-cabecera">
  <h2>Experimentos</h2>
  <p class="vacio">Cada experimento es 1 campaña en Meta → 1 conjunto por país → 1 anuncio por pieza. Todo nace en pausa: lanzar crea los anuncios, activar empieza a gastar.</p>
</div>

{% if capacidades_meta.estado != "conectado" %}
<p class="tag-error">Conecta Meta en Configuración para crear experimentos.</p>
{% else %}
<details class="swap-card" id="nuevo-experimento">
  <summary class="swap-card-resumen">+ Nuevo experimento</summary>
  <form method="post" action="{{ url_for('exp_crear', cliente=cliente) }}" class="form-experimento">
    <label>Nombre <input name="nombre" required maxlength="200"></label>
    <label>Objetivo
      <select name="objetivo">{% for o in objetivos_exp %}<option value="{{ o }}">{{ o }}</option>{% endfor %}</select>
    </label>
    <fieldset class="exp-paises">
      <legend>Países y presupuesto diario ({{ moneda_exp }}, mínimo {{ minimo_diario_exp }})</legend>
      {% for codigo, p in paises_fe.items() %}
      <label class="fe-destino">
        <input type="checkbox" name="paises" value="{{ codigo }}"> {{ p.bandera }} {{ p.nombre }}
        <input type="number" name="presupuesto_{{ codigo }}" min="0" step="any" placeholder="{{ minimo_diario_exp }}" style="width:8rem;">
      </label>
      {% endfor %}
    </fieldset>
    <div class="fe-opciones">
      <label>Días <input type="number" name="dias" value="7" min="1" max="90"></label>
      <label>Tope total ({{ moneda_exp }}) <input type="number" name="tope_total" min="0" step="any" required></label>
      <label>Edad <input type="number" name="edad_min" value="18" min="13" max="65" style="width:4rem;"> – <input type="number" name="edad_max" value="65" min="13" max="65" style="width:4rem;"></label>
      <label>URL de destino <input type="url" name="destino_url" value="{{ url_for('landing_cliente', cliente=cliente, _external=True) }}" required></label>
    </div>
    <button type="submit" class="btn-generar btn-sm">Crear experimento</button>
  </form>
</details>
{% endif %}

{% for e in experimentos %}
<details class="swap-card experimento experimento-{{ e.estado }}" {% if loop.first %}open{% endif %}>
  <summary class="swap-card-resumen">
    <span class="semaforo semaforo-{{ e.estado }}"></span>
    <strong>{{ e.nombre }}</strong>
    <span class="tag-estado">{{ e.estado }}</span>
    <small>{{ e.resumen.activos }}/{{ e.resumen.total }} activos · gasto {{ "%.2f"|format(e.gasto_acumulado) }} / {{ e.tope_total }} {{ e.moneda }}
      {% if e.resumen.mejor_cpc %}· mejor CPC {{ "%.2f"|format(e.resumen.mejor_cpc) }}{% endif %}</small>
  </summary>
  {% if e.error %}<p class="tag-error">{{ e.error }}</p>{% endif %}
  {% set trabajo = trabajos_exp.get(e.id) %}
  {% if trabajo %}
  <div class="barra-progreso" id="trabajo-{{ trabajo.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <script>iniciarPolling({{ trabajo.job_id | tojson }}, {{ ("trabajo-" ~ trabajo.job_id) | tojson }});</script>
  {% endif %}

  <div class="exp-acciones">
    {% if e.estado in ("armando", "error") and not e.meta_campaign_id %}
      <form method="post" action="{{ url_for('exp_lanzar', cliente=cliente, eid=e.id) }}" onsubmit="return confirm('Se crean la campaña, los conjuntos y los anuncios en Meta, en pausa. ¿Seguimos?');"><button class="btn-generar btn-sm">Lanzar a Meta (en pausa)</button></form>
    {% elif e.estado == "error" %}
      <form method="post" action="{{ url_for('exp_lanzar', cliente=cliente, eid=e.id) }}"><button class="btn-generar btn-sm">Reintentar lanzamiento</button></form>
    {% elif e.estado == "pausado" %}
      <form method="post" action="{{ url_for('exp_estado', cliente=cliente, eid=e.id) }}" onsubmit="return confirm('Activar empieza a gastar en Meta. ¿Seguimos?');"><input type="hidden" name="estado" value="ACTIVE"><button class="btn-aprobar btn-sm">Activar todo</button></form>
    {% elif e.estado == "corriendo" %}
      <form method="post" action="{{ url_for('exp_estado', cliente=cliente, eid=e.id) }}"><input type="hidden" name="estado" value="PAUSED"><button class="btn-rechazar btn-sm">Pausar todo</button></form>
    {% endif %}
    {% if e.meta_campaign_id and e.estado != "cerrado" %}
      <form method="post" action="{{ url_for('exp_refrescar', cliente=cliente, eid=e.id) }}"><button class="btn-guardar btn-sm">Actualizar métricas</button></form>
      <form method="post" action="{{ url_for('exp_cerrar', cliente=cliente, eid=e.id) }}" onsubmit="return confirm('Se pausa todo en Meta y el experimento queda cerrado.');"><button class="btn-rechazar btn-sm">Cerrar</button></form>
    {% endif %}
  </div>

  {# Árbol: experimento → países → piezas #}
  <ul class="exp-arbol">
    {% for p in e.paises %}
    {% set info = paises_fe.get(p.pais, {}) %}
    <li class="exp-pais">
      <div class="exp-pais-cab">
        <span>{{ info.bandera }} <strong>{{ info.nombre or p.pais }}</strong> · {{ p.presupuesto_dia }} {{ e.moneda }}/día <span class="tag-estado">{{ p.estado }}</span></span>
        {% if p.meta_adset_id and e.estado in ("pausado", "corriendo") %}
        <form method="post" action="{{ url_for('exp_estado', cliente=cliente, eid=e.id) }}" class="inline">
          <input type="hidden" name="pais" value="{{ p.pais }}">
          {% if p.estado == "activo" %}<input type="hidden" name="estado" value="PAUSED"><button class="btn-rechazar btn-xs">Pausar país</button>
          {% else %}<input type="hidden" name="estado" value="ACTIVE"><button class="btn-aprobar btn-xs" onclick="return confirm('Activar {{ p.pais }} empieza a gastar.');">Activar país</button>{% endif %}
        </form>
        <form method="post" action="{{ url_for('exp_presupuesto', cliente=cliente, eid=e.id) }}" class="inline">
          <input type="hidden" name="pais" value="{{ p.pais }}">
          <input type="number" name="presupuesto_dia" value="{{ p.presupuesto_dia }}" min="0" step="any" style="width:7rem;">
          <button class="btn-guardar btn-xs">Cambiar presupuesto</button>
        </form>
        {% endif %}
      </div>
      <ul class="exp-piezas">
        {% for pz in e.piezas if pz.pais == p.pais %}
        <li class="exp-pieza exp-pieza-{{ pz.estado }}">
          <span class="exp-pieza-mini">{% if pz.url_miniatura %}<img src="{{ pz.url_miniatura }}" alt="">{% endif %}</span>
          <span class="exp-pieza-nombre">{{ pz.nombre }} <small>({{ pz.tipo }})</small> <span class="tag-estado">{{ pz.estado }}</span>
            {% if pz.metricas.estado_meta_texto %}<small>· {{ pz.metricas.estado_meta_texto }}</small>{% endif %}
            {% if pz.error %}<span class="tag-error">{{ pz.error }}</span>{% endif %}</span>
          {% if pz.metricas %}
          <span class="kpis kpis-mini">
            <span class="kpi"><b>{{ pz.metricas.impresiones }}</b> impr.</span>
            <span class="kpi"><b>{{ pz.metricas.clics_enlace }}</b> clics</span>
            <span class="kpi"><b>{{ "%.2f"|format(pz.metricas.ctr or 0) }}%</b> CTR</span>
            <span class="kpi"><b>{{ "%.2f"|format(pz.metricas.cpc or 0) }}</b> CPC</span>
            <span class="kpi"><b>{{ "%.0f"|format((pz.metricas.thruplay_rate or 0) * 100) }}%</b> ThruPlay</span>
            <span class="kpi"><b>{{ "%.2f"|format(pz.metricas.gasto or 0) }}</b> gasto</span>
            {% if pz.metricas.compras %}<span class="kpi"><b>{{ pz.metricas.compras }}</b> compras · ROAS {{ "%.1f"|format(pz.metricas.roas or 0) }}</span>{% endif %}
            {% if pz.metricas.motivo_rechazo %}<span class="tag-error">{{ pz.metricas.motivo_rechazo }}</span>{% endif %}
          </span>
          {% endif %}
          {% if pz.estado == "en_cola" and not e.meta_campaign_id %}
          <form method="post" action="{{ url_for('exp_quitar_pieza', cliente=cliente, eid=e.id, ep_id=pz.id) }}" class="inline"><button class="btn-rechazar btn-xs">Quitar</button></form>
          {% endif %}
        </li>
        {% else %}
        <li class="vacio">Sin piezas para este país todavía.</li>
        {% endfor %}
      </ul>
    </li>
    {% endfor %}
  </ul>

  {% if e.estado in ("armando", "error") and not e.meta_campaign_id %}
  <form method="post" action="{{ url_for('exp_agregar_pieza', cliente=cliente, eid=e.id) }}" class="exp-agregar">
    <label>Agregar pieza
      <select name="pieza_id">
        {% for el in elegibles_exp %}<option value="{{ el.pieza_id }}" data-pais="{{ el.pais or '' }}">{{ el.nombre }}{% if el.pais %} · {{ el.pais }}{% endif %}</option>{% endfor %}
      </select>
    </label>
    <label>País <select name="pais">{% for p in e.paises %}<option value="{{ p.pais }}">{{ p.pais }}</option>{% endfor %}</select></label>
    <button class="btn-guardar btn-sm">Agregar</button>
    <small class="vacio">Las finales van a su propio país; los clones sin texto a cualquiera.</small>
  </form>
  {% endif %}

  <details class="exp-eventos"><summary>Bitácora ({{ e.eventos|length }})</summary>
    <ul>{% for ev in e.eventos %}<li><small>{{ ev.creado_en }}</small> <span class="tag-estado">{{ ev.tipo }}</span> {{ ev.mensaje }}</li>{% endfor %}</ul>
  </details>
</details>
{% else %}
<p class="vacio">Todavía no hay experimentos. Crea uno, agrega piezas desde Crear («Meter en experimento») y lánzalo.</p>
{% endfor %}
```

- [ ] **Step 3: "Meter en experimento" en Crear** — en `_tab_creativeflowplus.html`, dentro de `<div class="detalle-acciones">` de la tarjeta de la pieza (clon con `item.estado == "video_listo" and item.tipo != "imagen"`) y de la tarjeta de cada final (`f.estado in ("listo","degradada")`), un formulario compacto:

```jinja
{% if experimentos_armando %}
<form method="post" action="{{ url_for('exp_meter_pieza', cliente=cliente) }}" class="inline exp-meter">
  <input type="hidden" name="legado_id" value="{{ f.id if f is defined else item.id }}">
  <select name="experimento_id">{% for e in experimentos_armando %}<option value="{{ e.id }}">{{ e.nombre }}</option>{% endfor %}</select>
  {% if f is not defined %}<select name="pais">{% for codigo in paises_fe %}<option value="{{ codigo }}">{{ codigo }}</option>{% endfor %}</select>{% endif %}
  <button class="btn-guardar btn-sm">Meter en experimento</button>
</form>
{% endif %}
```

(usar dos bloques separados en vez del `f is defined` si el template lo hace confuso — el de la final sin selector de país, el del clon con él).

- [ ] **Step 4: CSS** — en `static/style.css`, sección nueva "Experimentos": `.semaforo` (círculo 10px; `-armando` gris, `-lanzando` ámbar animado, `-pausado` ámbar, `-corriendo` verde, `-cerrado` gris oscuro, `-error` rojo), `.exp-acciones` (flex, gap .5rem, wrap), `.exp-arbol` (lista sin viñetas, borde izquierdo 2px `var(--border)` con padding-left 1rem para leerse como árbol), `.exp-pais-cab` (flex space-between, wrap), `.exp-piezas` (margen izquierdo 1.2rem, misma línea guía), `.exp-pieza` (grid `48px 1fr auto`, gap .6rem, align center, padding .35rem 0), `.exp-pieza-mini img` (48×85 object-fit cover, radius 6px), `.kpis-mini .kpi` (font-size .72rem), `.btn-xs` (padding .15rem .5rem, font-size .72rem), `.exp-agregar`/`.exp-meter` (flex, gap .4rem, align-items end), `.exp-eventos ul` (font-size .76rem, max-height 14rem, overflow auto).

- [ ] **Step 5: Test y suite** — quitar el xfail; `venv/bin/python -m pytest -q` → verde. Verificación manual (controlador): levantar dashboard + worker locales con `meta_ads` en `dry_run` no aplica (rutas reales) — verificar solo UI: crear experimento, meter una final y un clon, ver árbol, lanzar contra Meta real con presupuesto mínimo y tope bajo, verificar en pausa, activar un país, actualizar métricas, pausar, cerrar.

- [ ] **Step 6: Commit** — `git add templates static tests && git commit -m "Experimentos: pestaña con árbol experimento → país → pieza, nuevo experimento, meter en experimento desde Crear"`.

---

### Task 6: Docs y despliegue

- [ ] **Step 1:** `CLAUDE.md`: párrafo "Experimentos" (módulos `experimentos.py`, `lanzador.py`, tareas `exp_*`, periódica 2 h, estados, un conjunto por país, spend_cap, utm). `SETUP.md`: nada nuevo de claves; anotar que la periódica corre en `creatv-worker`.
- [ ] **Step 2 (controlador):** push del submódulo (`git -C meta_ads push origin HEAD:main`), merge a main, deploy (`git pull`, `git submodule update --init --recursive`, `pip install`, `alembic upgrade head` → 0004, restart ambos servicios), prueba real: un experimento con 1 país (CO) y 1 pieza, presupuesto mínimo, lanzar, ver en pausa en Ads Manager, actualizar métricas.
- [ ] **Step 3:** Commit `"Docs: experimentos"`.

---

## Autorevisión

**Cobertura del spec:** §2 experimento/experimento_pieza/metrica_snapshot/evento (T1); §4 estructura 1 campaña → conjunto por país → anuncio por pieza, spend_cap = tope, utm_content, todo en pausa, refresco cada 2 h (T2, T3); atribución: nivel 1 (`actions.purchase`/`action_values`/`purchase_roas`) queda en el snapshot cuando Meta lo devuelve, `fuente_ventas=meta`; niveles 2–3 (tienda / ninguna) son bloque 5; chequeo de Pixel en Configuración → bloque 5/6 (anotar en ledger); §7 UI Experimentos (lista con semáforo, gasto vs tope, mejor CPC; detalle con árbol, bitácora, subir/bajar presupuesto, pausar/activar por país; "Meter en experimento" en Crear) (T5). Propuestas/modos semi-auto: bloque 4 (el campo `modo` se guarda ya como "manual").

**Consistencia de nombres:** `experimentos.crear/cargar/obtener/actualizar/actualizar_pais/agregar_pieza/quitar_pieza/actualizar_pieza/piezas/snapshot/ultima_metrica/registrar_evento/eventos/elegibles` (T1) ↔ T3/T4/T5; `lanzador.lanzar/cambiar_estado/cambiar_presupuesto_pais/refrescar/cerrar/ETAPAS_LANZAR/centavos/url_destino` (T3) ↔ T4; `tareas.experimentos.job_id_lanzar/job_id_refrescar` (T3) ↔ T4; contexto `experimentos/experimentos_armando/elegibles_exp/trabajos_exp/objetivos_exp/minimo_diario_exp/moneda_exp` (T4) ↔ T5; rutas `exp_crear/exp_agregar_pieza/exp_quitar_pieza/exp_lanzar/exp_estado/exp_presupuesto/exp_refrescar/exp_cerrar/exp_meter_pieza` (T4) ↔ T5; `meta_adset.actualizar_presupuesto/actualizar_estado`, `meta_ad.actualizar_estado`, `crear_campaign(spend_cap_centavos=)` (T2) ↔ T3.

**Riesgos:** `spend_cap` mínimo de Meta (≈100 USD equivalente) — por debajo no se manda y el tope se hace cumplir en bloque 4 (decisor pausa al llegar al tope); la app de Meta sigue "restringida" (API access blocked) — la prueba real de la Task 6 puede fallar por eso, no por el código: en ese caso verificar con `dry_run` y dejar la prueba real anotada como pendiente.
