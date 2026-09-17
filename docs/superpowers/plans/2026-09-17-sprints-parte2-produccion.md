# Sprints — Parte 2: producción (ideas, lote, QA, revisión, entrega) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una campaña de un sprint pase de referencias a piezas terminadas: Claude propone ideas (prompt maestro), la persona las aprueba, "Generar lote" muestra el costo y encola una sesión de Crear por idea con prioridad baja, el worker evalúa cada pieza con un QA automático que nunca gasta, la bandeja de revisión aprueba o rechaza con atajos, y el sprint se cierra con una entrega (enlaces y zip).

**Architecture:** Cada pieza planeada es una fila de `campana_pieza` que, al generarse, apunta (`cf_id`) a una sesión de Crear creada por `sprints/produccion.py` con `creative_flow.crear(..., extra_sprint=...)`, un prompt armado por `flowplus_prompt.armar(..., contexto=...)` y encolada por el nuevo helper compartido `flowplus_lanzar.py` (que también usa `dashboard.py`). `sprints/datos.py` gana el CRUD de ideas y une `campana_pieza` con `pieza` por `legado_id` para que progreso y estados salgan de la base. Módulos nuevos, cada uno con una responsabilidad: `sprints/ideas.py` (Claude → ideas validadas), `sprints/produccion.py` (estimado, sesiones, lote, reintento, regeneración, progreso), `sprints/qa.py` (Claude visión + ffprobe → veredicto puro), `sprints/revision.py` (aprobar/rechazar/cerrar/reabrir), `sprints/entrega.py` (enlaces y zip). Tareas del worker en `tareas/sprints.py`; la cola gana `prioridad`.

**Tech Stack:** Flask 3.1/Jinja, SQLAlchemy Core (SQLite WAL) + Alembic, worker/cola, Anthropic (texto y visión), proveedores de FlowPlus ya integrados (`providers/flowplus_modelos`), ffprobe, Cloudflare R2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-sprints-design.md` — Parte 2 (§2.1 ideas y prompt maestro, §2.2 lote, §2.3 interrupciones, §2.4 QA, §2.5 revisión, §2.6 cierre y entrega, §2.7 cambios mínimos, §2.8 módulos y pruebas). La Parte 1 ya está en `main` (tablas, `sprints/datos.py`, `estado.py`, `progreso.py`, `rutas.py`, plantillas).

## Global Constraints

- **Nada gasta crédito sin un clic con el costo a la vista.** Proponer ideas y el QA llaman a Claude (centavos) tras una acción explícita o como periódica barata; generar (imágenes/videos) solo desde "Generar lote", "Reintentar" o "Regenerar", siempre con `max_intentos=1` y el estimado mostrado antes. El QA nunca genera.
- Prioridad de cola: `tarea.prioridad` (int, defecto 5); `cola.reclamar` ordena `prioridad DESC, ejecutar_desde, id`; los lotes encolan con `PRIORIDAD_LOTE = 3`.
- Cada pieza del sprint es una sesión de Crear normal: aparece en Crear con el distintivo "Sprint · Campaña N", entra a experimentos y a la cola de publicación como hoy. `creative_flow.crear` gana `extra_sprint` (se guarda en `extra["sprint"]`); `flowplus_prompt.armar` gana `contexto` (con `None` el prompt es idéntico al actual: prueba de regresión).
- `ETAPAS_CREATIVE_FLOW` ya vive en `tareas/flowplus.py`; el helper de lanzamiento se mueve a `flowplus_lanzar.py` (`job_id`, `lanzar(cliente, cf_id, entry, prioridad=5)`) y `dashboard.py` delega en él sin cambiar el comportamiento de Crear.
- Migración nueva `0008_tarea_prioridad.py` con `down_revision='0007'` (una sola cabeza; la prueba `test_alembic_tiene_una_sola_cabeza` lo vigila).
- Estados: los de la Parte 1 (`sprints/estado.py`) ya contemplan ideas y piezas; aquí solo se alimentan de verdad. Las ideas `descartada` no cuentan para el estado ni para el progreso.
- Multi-tenant: toda consulta y actualización filtra por `cliente`; las rutas resuelven ideas por `(cp_id, cliente)` y verifican que pertenezcan al sprint de la URL.
- Sin red en las pruebas (Claude, R2, ffprobe, `requests` y `trabajos.encolar` se reemplazan con `monkeypatch`). Suite verde: `venv/bin/python -m pytest -q`. `python3 -m py_compile` de cada archivo tocado antes de cada commit. Copy en español.
- Git local: `/opt/homebrew/bin/git`. Commits pequeños, uno por tarea, mensaje en español, con la línea `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- No tocar: `experimentos.py`, `lanzador.py`, `decisor.py`, `derivaciones.py`, `final_edition/`, `conectores/`, `tiendas.py`. Cambios a `dashboard.py`, `creative_flow.py`, `flowplus_prompt.py`, `cola.py`, `trabajos.py`, `worker.py`, `notificaciones.py`, `tareas/__init__.py`, plantillas y CSS: aditivos y mínimos.

---

## Estructura de archivos

- Create: `migrations/versions/0008_tarea_prioridad.py`; Modify: `db.py` (columna `prioridad` en `tarea`), `cola.py` (`encolar(prioridad=)`, `reclamar` por prioridad), `trabajos.py` (`encolar(prioridad=)`).
- Create: `flowplus_lanzar.py`; Modify: `dashboard.py` (delegar `_job_id_creative_flow` y `_lanzar_video_cf`), `flowplus_prompt.py` (`armar(contexto=)`), `creative_flow.py` (`crear(extra_sprint=)`).
- Modify: `sprints/datos.py` (ideas: `_IDEA_COLS`, `crear_idea`, `actualizar_idea`, `idea`, `ideas`, `eliminar_idea`, `_ideas`; `_campanas` une piezas), `sprints/estado.py` (`recalcular` ignora descartadas).
- Create: `sprints/ideas.py`, `sprints/produccion.py`, `sprints/qa.py`, `sprints/revision.py`, `sprints/entrega.py`.
- Modify: `tareas/sprints.py` (+ `sprint_proponer_ideas`, `sprint_qa_pieza`, `sprint_qa_pendientes`, `sprint_empaquetar`), `worker.py` (`PERIODICAS`), `notificaciones.py` (`TIPOS` + `"sprint_lote"`).
- Modify: `sprints/rutas.py` (rutas de ideas, lote, progreso, revisión, cierre, entrega), `templates/sprint_detalle.html`, `templates/_tab_creativeflowplus.html` (distintivo), `static/style.css`; Create: `templates/campana_ideas.html`, `templates/_sprint_lote_modal.html`, `templates/sprint_revision.html`, `templates/sprint_entrega.html`.
- Modify: `CLAUDE.md`.
- Tests: `tests/test_cola.py` (+), `tests/test_flowplus_lanzar.py`, `tests/test_flowplus_prompt_contexto.py`, `tests/test_sprints_datos.py` (+), `tests/test_sprints_ideas.py`, `tests/test_sprints_produccion.py`, `tests/test_sprints_qa.py`, `tests/test_sprints_revision_entrega.py`, `tests/test_tareas_sprints.py` (+), `tests/test_rutas_sprints.py` (+), `tests/test_sprints_db.py` (+).

---

### Task 1: Prioridad en la cola (`tarea.prioridad`, migración 0008, `cola.reclamar`, `trabajos.encolar`)

**Files:**
- Modify: `db.py` (tabla `tarea`), `cola.py`, `trabajos.py`
- Create: `migrations/versions/0008_tarea_prioridad.py`
- Test: `tests/test_cola.py` (agregar), `tests/test_sprints_db.py` (agregar)

**Interfaces:**
- Produces: `cola.encolar(..., prioridad=5)`, `trabajos.encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None, max_intentos=5, prioridad=5)`; `cola.reclamar()` toma primero la mayor `prioridad`, luego `ejecutar_desde`, luego `id`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_cola.py`:

```python
def test_reclamar_respeta_prioridad_y_luego_orden_de_llegada(base_temporal):
    import cola
    a = cola.encolar("prueba", {"n": "lote1"}, prioridad=3)
    b = cola.encolar("prueba", {"n": "suelta"})            # prioridad 5 por defecto
    c = cola.encolar("prueba", {"n": "lote2"}, prioridad=3)
    assert [cola.reclamar()["payload"]["n"] for _ in range(3)] == ["suelta", "lote1", "lote2"]
    assert cola.consultar_por_id(a)["prioridad"] == 3 and cola.consultar_por_id(b)["prioridad"] == 5


def test_trabajos_encolar_pasa_prioridad(base_temporal):
    import cola
    import trabajos
    assert trabajos.encolar("j1", "prueba", {}, prioridad=3) is True
    assert cola.consultar_por_job("j1")["prioridad"] == 3
    assert trabajos.encolar("j2", "prueba", {}) is True
    assert cola.consultar_por_job("j2")["prioridad"] == 5
```

Agregar a `tests/test_sprints_db.py`:

```python
def test_migracion_0008_agrega_prioridad(tmp_path, monkeypatch):
    import os
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig8.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    cols = {c["name"] for c in sa.inspect(db.engine()).get_columns("tarea")}
    assert "prioridad" in cols
    db._reset_para_tests()
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_cola.py tests/test_sprints_db.py -q`
Expected: FAIL (`encolar() got an unexpected keyword argument 'prioridad'`; columna ausente).

- [ ] **Step 3: `db.py`** — en la tabla `tarea`, después de `Column("max_intentos", Integer, default=5),`:

```python
    Column("prioridad", Integer, default=5),                # mayor = antes; los lotes de sprint van con 3
```

- [ ] **Step 4: `cola.py`**

Firma y `values` de `encolar`:

```python
def encolar(tipo, payload, *, cliente=None, job_id=None, duracion_estimada=60, etapas=None,
            ejecutar_desde=None, max_intentos=5, prioridad=5):
```

y dentro del `insert().values(...)` agregar `prioridad=int(prioridad),` después de `max_intentos=max_intentos,`.

En `reclamar`, cambiar el `order_by`:

```python
        ).order_by(db.tarea.c.prioridad.desc(), db.tarea.c.ejecutar_desde, db.tarea.c.id).limit(1)).first()
```

- [ ] **Step 5: `trabajos.py`**

```python
def encolar(job_id, tipo, payload, duracion_estimada=60, etapas=None, cliente=None, max_intentos=5, prioridad=5):
    """Igual que iniciar(), pero la tarea la ejecuta el worker (worker.py) y
    sobrevive reinicios. Devuelve False si ya hay una viva con ese job_id.
    `prioridad`: mayor se atiende antes (5 = normal; los lotes de sprint usan 3
    para no bloquear a quien genera una pieza suelta desde Crear)."""
    tid = cola.encolar(tipo, payload, cliente=cliente, job_id=job_id,
                       duracion_estimada=duracion_estimada, etapas=etapas or [],
                       max_intentos=max_intentos, prioridad=prioridad)
    return tid is not None
```

- [ ] **Step 6: Migración `migrations/versions/0008_tarea_prioridad.py`**

```python
"""tarea: prioridad (mayor se atiende antes; lotes de sprint = 3)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17 00:00:00.000000

Parte 2 del spec docs/superpowers/specs/2026-09-16-sprints-design.md (§2.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tarea") as b:
        b.add_column(sa.Column("prioridad", sa.Integer(), server_default="5"))


def downgrade() -> None:
    with op.batch_alter_table("tarea") as b:
        b.drop_column("prioridad")
```

- [ ] **Step 7: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_cola.py tests/test_sprints_db.py tests/test_worker.py tests/test_trabajos_adaptador.py -q`
Expected: PASS. Luego `venv/bin/alembic upgrade head` y `venv/bin/alembic heads` → `0008 (head)`.

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile db.py cola.py trabajos.py migrations/versions/0008_tarea_prioridad.py
/opt/homebrew/bin/git add db.py cola.py trabajos.py migrations/versions/0008_tarea_prioridad.py tests/test_cola.py tests/test_sprints_db.py
/opt/homebrew/bin/git commit -m "Cola: prioridad por tarea (los lotes de sprint no bloquean a Crear), migración 0008

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `flowplus_lanzar.py`, `flowplus_prompt.armar(contexto=)`, `creative_flow.crear(extra_sprint=)`

**Files:**
- Create: `flowplus_lanzar.py`
- Modify: `dashboard.py` (`_job_id_creative_flow`, `_lanzar_video_cf`), `flowplus_prompt.py` (`armar`), `creative_flow.py` (`crear`)
- Test: `tests/test_flowplus_lanzar.py`, `tests/test_flowplus_prompt_contexto.py`, `tests/test_creative_flow_db.py` (agregar)

**Interfaces:**
- Produces: `flowplus_lanzar.job_id(cliente, cf_id) -> str` (`f"{cliente}__{cf_id}__creative_flow"`), `flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=5) -> bool`; `flowplus_prompt.armar(texto, referencias, con_persona=False, guia_marca="", negative_marca=None, logos=None, enfoque=None, contexto=None)` donde `contexto = {"persona": {resumen, descripcion, tono, senales_visuales}, "temporada": {nombre, contexto, mood_visual}}` (claves opcionales); `creative_flow.crear(..., legado_id=None, creado_en=None, extra_sprint=None)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_flowplus_lanzar.py`:

```python
def test_job_id_y_lanzar_encolan_con_prioridad(base_temporal, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import trabajos
    cf_id = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A", referencias_urls=["https://r2/a.jpg"])
    creative_flow.actualizar("acme", cf_id, prompt_relleno="P", tipo="imagen", modelo="seedream_v5_pro")
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    entry = creative_flow.cargar("acme")[cf_id]
    assert flowplus_lanzar.job_id("acme", cf_id) == f"acme__{cf_id}__creative_flow"
    assert flowplus_lanzar.lanzar("acme", cf_id, entry, prioridad=3) is True
    job_id, tipo, payload, kw = encolados[0]
    assert tipo == "flowplus_imagen" and payload == {"cliente": "acme", "cf_id": cf_id}
    assert kw["max_intentos"] == 1 and kw["prioridad"] == 3 and kw["duracion_estimada"] == 60 and kw["cliente"] == "acme"
    assert creative_flow.cargar("acme")[cf_id]["estado"] == "video_generando"
    creative_flow.actualizar("acme", cf_id, tipo="video")
    flowplus_lanzar.lanzar("acme", cf_id, creative_flow.cargar("acme")[cf_id])
    assert encolados[1][1] == "flowplus_video" and encolados[1][3]["prioridad"] == 5 and encolados[1][3]["duracion_estimada"] == 180


def test_dashboard_delega_en_flowplus_lanzar(base_temporal, monkeypatch):
    import dashboard
    import flowplus_lanzar
    llamadas = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: llamadas.append((c, cf, prioridad)) or True)
    assert dashboard._job_id_creative_flow("acme", "cf_1") == flowplus_lanzar.job_id("acme", "cf_1")
    assert dashboard._lanzar_video_cf("acme", "cf_1", {"tipo": "video"}) is True
    assert llamadas == [("acme", "cf_1", 5)]
```

`tests/test_flowplus_prompt_contexto.py`:

```python
import flowplus_prompt

REFS = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo LED",
         "regla": "Idéntico.", "producto": "Espejo LED"}]


def test_sin_contexto_el_prompt_es_identico():
    base = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto")
    assert flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto", contexto=None) == base
    assert "AUDIENCIA" not in base and "TEMPORADA" not in base


def test_contexto_agrega_audiencia_y_temporada_al_principio():
    ctx = {"persona": {"resumen": "Busca calidad", "descripcion": "Renueva su casa.", "tono": "cercano",
                       "senales_visuales": ["cocina moderna", "luz natural"]},
           "temporada": {"nombre": "Navidad", "contexto": "Regalos y reuniones.",
                         "mood_visual": {"paleta": ["#B3001B", "#0B6E4F"], "luz": "cálida", "elementos": ["luces", "mesa"]}}}
    p = flowplus_prompt.armar("gira despacio", REFS, guia_marca="Luz natural.", enfoque="producto", contexto=ctx)
    lineas = p.split("\n")
    i_aud = next(i for i, l in enumerate(lineas) if l.startswith("AUDIENCIA: "))
    i_tem = next(i for i, l in enumerate(lineas) if l.startswith("TEMPORADA: "))
    i_prod = next(i for i, l in enumerate(lineas) if l.startswith("PRODUCTO EXACTO"))
    assert i_aud < i_tem < i_prod
    assert "Busca calidad" in lineas[i_aud] and "cocina moderna, luz natural" in lineas[i_aud] and "cercano" in lineas[i_aud]
    assert "Navidad" in lineas[i_tem] and "#B3001B" in lineas[i_tem] and "luces, mesa" in lineas[i_tem]
    assert p.endswith("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")


def test_contexto_parcial_no_rompe():
    p = flowplus_prompt.armar("x", REFS, contexto={"persona": {"resumen": "Joven"}})
    assert "AUDIENCIA: Joven." in p and "TEMPORADA" not in p
    assert flowplus_prompt.armar("x", REFS, contexto={}) == flowplus_prompt.armar("x", REFS)
```

Agregar a `tests/test_creative_flow_db.py`:

```python
def test_crear_guarda_extra_sprint(base_temporal):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], ["P"], [], "acción", 8, "", "A", extra_sprint={"sprint_id": 1, "campana_id": 2, "cp_id": 3})
    e = cf.cargar("acme")[cf_id]
    assert e["sprint"] == {"sprint_id": 1, "campana_id": 2, "cp_id": 3}
    otro = cf.crear("acme", [], ["P"], [], "acción", 8, "", "A")
    assert "sprint" not in cf.cargar("acme")[otro]
    copia = cf.duplicar("acme", cf_id)
    assert cf.cargar("acme")[copia]["sprint"]["cp_id"] == 3    # la regeneración conserva el vínculo
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_flowplus_lanzar.py tests/test_flowplus_prompt_contexto.py tests/test_creative_flow_db.py -q`
Expected: FAIL (módulo ausente, kwargs desconocidos).

- [ ] **Step 3: `flowplus_lanzar.py`**

```python
"""
Encolar en el worker la generación de una sesión de Crear (FlowPlus): imagen o
video. Lo usan el dashboard (Crear: formulario y reintento) y los sprints
(lotes, reintento y regeneración). El cuerpo real vive en tareas/flowplus.py.

`prioridad`: 5 es lo normal; los lotes de sprint pasan 3 para que una pieza
suelta pedida desde Crear se atienda antes que las treinta de un lote.
"""
import creative_flow
import trabajos
from tareas.flowplus import ETAPAS_CREATIVE_FLOW

PRIORIDAD_NORMAL = 5


def job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


def lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_NORMAL):
    """Devuelve True si encoló, False si ya había una tarea viva para esa sesión.
    Escribe estado="video_generando" ANTES de encolar: si el worker fallara
    instantáneo, podría escribir "error" y el principal pisarlo. max_intentos=1:
    si la generación falla ya pudo haberse cobrado el crédito; la persona
    decide con "Reintentar"."""
    tipo = entry.get("tipo") or "video"
    creative_flow.actualizar(cliente, cf_id, estado="video_generando")
    return trabajos.encolar(
        job_id(cliente, cf_id), "flowplus_imagen" if tipo == "imagen" else "flowplus_video",
        {"cliente": cliente, "cf_id": cf_id}, cliente=cliente,
        duracion_estimada=60 if tipo == "imagen" else 180, etapas=ETAPAS_CREATIVE_FLOW,
        max_intentos=1, prioridad=prioridad,
    )
```

- [ ] **Step 4: `dashboard.py`** — agregar `import flowplus_lanzar` junto a los imports de módulos propios (donde está `import creative_flow`), y reemplazar los cuerpos:

```python
def _job_id_creative_flow(cliente, cf_id):
    return flowplus_lanzar.job_id(cliente, cf_id)
```

```python
def _lanzar_video_cf(cliente, cf_id, entry):
    """Encola la generación de una sesión de FlowPlus (video o imagen). Lo usan
    cf_crear_video y cf_generar_video. El cuerpo vive en flowplus_lanzar.py
    (compartido con los lotes de Sprints)."""
    return flowplus_lanzar.lanzar(cliente, cf_id, entry)
```

Dejar el resto de `dashboard.py` igual (el `from tareas.flowplus import ETAPAS_CREATIVE_FLOW` puede quedarse aunque ya no se use aquí, para no tocar otras referencias).

- [ ] **Step 5: `flowplus_prompt.py`** — firma y bloque nuevo

```python
def armar(texto, referencias, con_persona=False, guia_marca="", negative_marca=None, logos=None, enfoque=None,
          contexto=None):
    """texto: lo que escribió la persona (se respeta íntegro).
    referencias: [{tipo, etiqueta, producto?}] ya numeradas.
    logos: [{etiqueta}] referencias de logo agregadas por el proyecto.
    enfoque: clave de ENFOQUES (manda sobre con_persona) o None.
    contexto: opcional (Sprints): {"persona": {resumen, descripcion, tono,
    senales_visuales}, "temporada": {nombre, contexto, mood_visual}}; agrega
    las líneas AUDIENCIA y TEMPORADA. Con None el prompt es idéntico.
    Devuelve el prompt completo (str)."""
```

Justo después del bloque `if not con_persona: partes.append("VIDEO DE PRODUCTO SOLO...")` y antes de `productos = [...]`, insertar:

```python
    # --- Contexto de campaña (Sprints): audiencia y temporada ---
    partes.extend(_lineas_contexto(contexto))
```

Y agregar, antes de `def armar`, la función:

```python
def _lineas_contexto(contexto):
    """Líneas AUDIENCIA/TEMPORADA a partir del contexto de una campaña de
    sprint. Solo emite lo que viene; sin contexto no emite nada."""
    if not contexto:
        return []
    lineas = []
    p = contexto.get("persona") or {}
    partes_p = [str(p[k]).strip().rstrip(".") for k in ("resumen", "descripcion") if p.get(k)]
    if p.get("senales_visuales"):
        partes_p.append("Señales visuales: " + ", ".join(str(s) for s in p["senales_visuales"]))
    if p.get("tono"):
        partes_p.append(f"Tono: {str(p['tono']).strip().rstrip('.')}")
    if partes_p:
        lineas.append("AUDIENCIA: " + ". ".join(partes_p) + ".")
    t = contexto.get("temporada") or {}
    partes_t = [str(t[k]).strip().rstrip(".") for k in ("nombre", "contexto") if t.get(k)]
    mood = t.get("mood_visual") or {}
    if mood.get("paleta"):
        partes_t.append("Paleta: " + ", ".join(str(c) for c in mood["paleta"]))
    if mood.get("luz"):
        partes_t.append(f"Luz: {str(mood['luz']).strip().rstrip('.')}")
    if mood.get("elementos"):
        partes_t.append("Elementos: " + ", ".join(str(e) for e in mood["elementos"]))
    if partes_t:
        lineas.append("TEMPORADA: " + ". ".join(partes_t) + ".")
    return lineas
```

- [ ] **Step 6: `creative_flow.py`** — `crear` gana `extra_sprint=None`:

```python
def crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central,
          duracion_objetivo, tono, modo, referencias_urls=None, platforms=None,
          legado_id=None, creado_en=None, extra_sprint=None):
```

y después de construir `extra = {...}`:

```python
    if extra_sprint:
        # Vínculo con la campaña del sprint que pidió esta pieza (Sprints, Parte 2).
        extra["sprint"] = dict(extra_sprint)
```

- [ ] **Step 7: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_flowplus_lanzar.py tests/test_flowplus_prompt_contexto.py tests/test_creative_flow_db.py tests/test_rutas_experimentos.py tests/test_derivaciones.py -q`
Expected: PASS (Crear y derivaciones siguen igual).

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile flowplus_lanzar.py dashboard.py flowplus_prompt.py creative_flow.py
/opt/homebrew/bin/git add flowplus_lanzar.py dashboard.py flowplus_prompt.py creative_flow.py tests/test_flowplus_lanzar.py tests/test_flowplus_prompt_contexto.py tests/test_creative_flow_db.py
/opt/homebrew/bin/git commit -m "FlowPlus: lanzador compartido con prioridad, contexto de campaña en el prompt y vínculo con el sprint en la sesión

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Ideas en `sprints/datos.py` y unión con las piezas de Crear

**Files:**
- Modify: `sprints/datos.py` (agregar al final; tocar `_campanas`), `sprints/estado.py` (`recalcular`)
- Test: `tests/test_sprints_datos.py` (agregar), `tests/test_sprints_progreso_estado.py` (agregar)

**Interfaces:**
- Produces: `TIPOS_PIEZA = ("video", "imagen")`, `ESTADOS_IDEA = ("propuesta", "aprobada", "descartada")`, `REVISIONES = ("pendiente", "aprobada", "rechazada")`, `PLATAFORMAS = ("instagram", "tiktok", "facebook", "youtube")`; `crear_idea(cliente, campana_id, tipo, titulo, escena, sonido="", enfoque=None, gancho="", referencias_ids=None, duracion_s=None, plataformas=None, estado_idea="propuesta") -> int`; `actualizar_idea(cliente, cp_id, /, **campos) -> bool` (campos permitidos `_IDEA_COLS`; valida `estado_idea`, `revision`, `tipo`); `idea(cliente, cp_id) -> dict|None`; `ideas(cliente, campana_id, incluir_descartadas=True) -> list[dict]`; `eliminar_idea(cliente, cp_id) -> bool` (solo sin `cf_id`). Cada dict de idea trae las columnas de `campana_pieza` más `sprint_id`, `campana_orden` y, si hay sesión, `estado` (de `pieza.estado`: pendiente|generando|listo|error|degradada), `url_video`, `url_miniatura`, `url_local`, `costo_usd`, `pieza_error`, `modelo`; sin sesión `estado` es `None`.
- Cada dict de campaña (`datos.campanas`, `datos.sprint`) ahora trae `ideas` (todas, con descartadas), `piezas` (las ideas no descartadas con `cf_id`), `piezas_listas` (estado en listo|degradada) y `piezas_aprobadas` (`revision == "aprobada"`). `estado.recalcular` pasa a `estado_campana` solo las ideas no descartadas.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_sprints_datos.py`:

```python
def _campana(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    return sid, datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)


def test_ideas_crud_y_validaciones(base_temporal):
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "Espejo al amanecer", "La cámara rodea el espejo...", sonido="pájaros",
                          enfoque="producto", gancho="Luz que despierta", referencias_ids=[], duracion_s=8,
                          plataformas=["instagram", "tiktok"])
    i2 = datos.crear_idea("acme", cid, "imagen", "Detalle del marco", "Primer plano del marco...")
    a = datos.idea("acme", i1)
    assert a["estado_idea"] == "propuesta" and a["revision"] == "pendiente" and a["estado"] is None
    assert a["sprint_id"] == sid and a["campana_orden"] == 0 and a["plataformas"] == ["instagram", "tiktok"]
    assert [i["id"] for i in datos.ideas("acme", cid)] == [i1, i2]
    assert datos.actualizar_idea("acme", i1, estado_idea="aprobada", escena="Nueva escena")
    assert datos.idea("acme", i1)["escena"] == "Nueva escena"
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", cid, "audio", "x", "y")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", cid, "video", "", "y")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_idea("acme", i1, estado_idea="rara")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_idea("acme", i1, revision="quizas")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_idea("acme", 999, "video", "x", "y")
    assert datos.idea("otro", i1) is None
    datos.actualizar_idea("acme", i2, estado_idea="descartada")
    assert [i["id"] for i in datos.ideas("acme", cid, incluir_descartadas=False)] == [i1]
    assert datos.eliminar_idea("acme", i2) and datos.idea("acme", i2) is None
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert "idea_creada" in tipos and "idea_eliminada" in tipos


def test_ideas_se_unen_con_la_sesion_de_crear(base_temporal):
    import creative_flow
    from sprints import datos
    sid, cid = _campana(datos)
    i1 = datos.crear_idea("acme", cid, "video", "A", "a", estado_idea="aprobada")
    i2 = datos.crear_idea("acme", cid, "imagen", "B", "b", estado_idea="aprobada")
    i3 = datos.crear_idea("acme", cid, "video", "C", "c", estado_idea="descartada")
    cf1 = creative_flow.crear("acme", [], ["Espejo"], [], "a", 8, "", "A")
    cf2 = creative_flow.crear("acme", [], ["Espejo"], [], "b", 0, "", "A")
    creative_flow.actualizar("acme", cf2, tipo="imagen")
    datos.actualizar_idea("acme", i1, cf_id=cf1)
    datos.actualizar_idea("acme", i2, cf_id=cf2)
    datos.actualizar_idea("acme", i3, cf_id=cf1)
    creative_flow.actualizar("acme", cf1, estado="video_listo", video_url="https://r2/v.mp4", usd=0.8)
    creative_flow.actualizar("acme", cf2, estado="video_generando")
    c = datos.campana("acme", cid)
    assert len(c["ideas"]) == 3 and [p["id"] for p in c["piezas"]] == [i1, i2]
    assert c["piezas_listas"] == 1 and c["piezas_aprobadas"] == 0
    p1 = next(p for p in c["piezas"] if p["id"] == i1)
    assert p1["estado"] == "listo" and p1["url_video"] == "https://r2/v.mp4" and p1["costo_usd"] == 0.8
    assert next(p for p in c["piezas"] if p["id"] == i2)["estado"] == "generando"
    datos.actualizar_idea("acme", i1, revision="aprobada")
    assert datos.campana("acme", cid)["piezas_aprobadas"] == 1
    # Una final de la misma sesión (legado_id cf__es_CO) NO se confunde con el clon.
    creative_flow.crear_final("acme", cf1, "es", "CO")
    assert datos.idea("acme", i1)["estado"] == "listo"
    with pytest.raises(datos.ErrorDatos):
        datos.eliminar_idea("acme", i1)     # ya tiene sesión
```

Agregar a `tests/test_sprints_progreso_estado.py`:

```python
def test_recalcular_con_ideas_y_piezas_reales(base_temporal):
    import creative_flow
    from sprints import datos, estado
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=1)
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 0)
    datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz")
    i_desc = datos.crear_idea("acme", cid, "video", "X", "x", estado_idea="descartada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "referencias"   # descartadas no cuentan
    i1 = datos.crear_idea("acme", cid, "video", "A", "a")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "ideas_propuestas"
    datos.actualizar_idea("acme", i1, estado_idea="aprobada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "ideas_aprobadas"
    cf = creative_flow.crear("acme", [], ["Espejo"], [], "a", 8, "", "A")
    datos.actualizar_idea("acme", i1, cf_id=cf)
    creative_flow.actualizar("acme", cf, estado="video_generando")
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "generando" and sp["estado"] == "generando"
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    sp = estado.recalcular("acme", sid)
    assert sp["campanas"][0]["estado"] == "revision" and sp["estado"] == "revision"
    datos.actualizar_idea("acme", i1, revision="aprobada")
    assert estado.recalcular("acme", sid)["campanas"][0]["estado"] == "completada"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py tests/test_sprints_progreso_estado.py -q`
Expected: FAIL (`crear_idea` ausente).

- [ ] **Step 3: `sprints/datos.py`** — constantes (junto a las demás, arriba):

```python
TIPOS_PIEZA = ("video", "imagen")
ESTADOS_IDEA = ("propuesta", "aprobada", "descartada")
REVISIONES = ("pendiente", "aprobada", "rechazada")
PLATAFORMAS = ("instagram", "tiktok", "facebook", "youtube")
_IDEA_COLS = ("titulo", "escena", "sonido", "enfoque", "gancho", "referencias_ids", "duracion_s", "plataformas",
              "estado_idea", "cf_id", "qa", "revision", "revision_motivo", "textos", "orden", "extra")
_PIEZA_TERMINADA = ("listo", "degradada")
```

Al final del archivo:

```python
# -------------------------------------------------------------- ideas ---

def _ideas(con, cliente, campana_id=None, cp_id=None):
    """Ideas de una campaña unidas (LEFT JOIN) con la sesión de Crear que las
    generó: `pieza.legado_id == campana_pieza.cf_id`. Las finales tienen otro
    legado_id (`cf__idioma_pais`) y otro tipo, así que nunca se confunden."""
    cp, pz, c = db.campana_pieza, db.pieza, db.campana
    q = (sa.select(cp, c.c.sprint_id.label("sprint_id"), c.c.orden.label("campana_orden"),
                   pz.c.estado.label("estado"), pz.c.url_video, pz.c.url_miniatura, pz.c.url_local,
                   pz.c.costo_usd, pz.c.error.label("pieza_error"), pz.c.modelo)
         .select_from(cp.join(c, c.c.id == cp.c.campana_id)
                      .outerjoin(pz, sa.and_(pz.c.legado_id == cp.c.cf_id, pz.c.cliente == cp.c.cliente,
                                             pz.c.tipo.in_(TIPOS_PIEZA))))
         .where(cp.c.cliente == cliente))
    if campana_id is not None:
        q = q.where(cp.c.campana_id == campana_id)
    if cp_id is not None:
        q = q.where(cp.c.id == cp_id)
    salida = []
    for f in con.execute(q.order_by(cp.c.orden, cp.c.id)):
        d = _a_dict(f)
        d["referencias_ids"] = list(d.get("referencias_ids") or [])
        d["plataformas"] = list(d.get("plataformas") or [])
        d["extra"] = d.get("extra") or {}
        salida.append(d)
    return salida


def _validar_idea(campos):
    if "tipo" in campos and campos["tipo"] not in TIPOS_PIEZA:
        raise ErrorDatos(f"Tipo de pieza inválido: {campos['tipo']}")
    if "estado_idea" in campos and campos["estado_idea"] not in ESTADOS_IDEA:
        raise ErrorDatos(f"Estado de idea inválido: {campos['estado_idea']}")
    if "revision" in campos and campos["revision"] not in REVISIONES:
        raise ErrorDatos(f"Revisión inválida: {campos['revision']}")
    if "plataformas" in campos:
        campos["plataformas"] = [p for p in (campos["plataformas"] or []) if p in PLATAFORMAS]
    if "referencias_ids" in campos:
        campos["referencias_ids"] = [int(x) for x in (campos["referencias_ids"] or [])]
    if "duracion_s" in campos and campos["duracion_s"] is not None:
        try:
            campos["duracion_s"] = float(campos["duracion_s"])
        except (TypeError, ValueError):
            raise ErrorDatos("La duración debe ser un número.")
    for k in ("titulo", "escena", "sonido", "gancho", "revision_motivo"):
        if k in campos and campos[k] is not None:
            campos[k] = _texto(campos[k], 200 if k in ("titulo", "gancho") else None)
    return campos


def crear_idea(cliente, campana_id, tipo, titulo, escena, sonido="", enfoque=None, gancho="", referencias_ids=None,
               duracion_s=None, plataformas=None, estado_idea="propuesta"):
    campos = _validar_idea({"tipo": tipo, "titulo": titulo, "escena": escena, "sonido": sonido, "gancho": gancho,
                            "referencias_ids": referencias_ids, "duracion_s": duracion_s, "plataformas": plataformas,
                            "estado_idea": estado_idea})
    if not campos["titulo"] or not campos["escena"]:
        raise ErrorDatos("Una idea necesita título y escena.")
    ahora = db.ahora()
    with db.conectar() as con:
        c = _fila(con, db.campana, campana_id, cliente)
        if not c:
            raise ErrorDatos("Esa campaña no existe.")
        cp = db.campana_pieza
        orden = con.execute(sa.select(sa.func.coalesce(sa.func.max(cp.c.orden), -1)).where(cp.c.campana_id == campana_id)).scalar() + 1
        cp_id = con.execute(cp.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, campana_id=campana_id, tipo=campos["tipo"],
            titulo=campos["titulo"], escena=campos["escena"], sonido=campos["sonido"] or None, enfoque=enfoque,
            gancho=campos["gancho"] or None, referencias_ids=campos["referencias_ids"], duracion_s=campos["duracion_s"],
            plataformas=campos["plataformas"], estado_idea=campos["estado_idea"], cf_id=None, qa=None,
            revision="pendiente", revision_motivo=None, textos=None, orden=orden, extra={})).inserted_primary_key[0]
        _evento(con, cliente, c.sprint_id, campana_id, "idea_creada", f"Idea «{campos['titulo']}» ({campos['tipo']})",
                {"cp_id": cp_id})
    return cp_id


def actualizar_idea(cliente, cp_id, /, **campos):
    campos = _validar_idea(campos)
    with db.conectar() as con:
        return _actualizar(con, db.campana_pieza, cp_id, cliente, _IDEA_COLS, campos)


def idea(cliente, cp_id):
    with db.conectar() as con:
        lista = _ideas(con, cliente, cp_id=cp_id)
    return lista[0] if lista else None


def ideas(cliente, campana_id, incluir_descartadas=True):
    with db.conectar() as con:
        lista = _ideas(con, cliente, campana_id=campana_id)
    return lista if incluir_descartadas else [i for i in lista if i["estado_idea"] != "descartada"]


def eliminar_idea(cliente, cp_id):
    with db.conectar() as con:
        f = _fila(con, db.campana_pieza, cp_id, cliente)
        if not f:
            return False
        if f.cf_id:
            raise ErrorDatos("Esa idea ya tiene una pieza generada; descártala en vez de borrarla.")
        c = con.execute(sa.select(db.campana.c.sprint_id).where(db.campana.c.id == f.campana_id)).first()
        con.execute(db.campana_pieza.delete().where(db.campana_pieza.c.id == cp_id))
        if c:
            _evento(con, cliente, c.sprint_id, f.campana_id, "idea_eliminada", f"Idea «{f.titulo}» eliminada", {"cp_id": cp_id})
    return True
```

Y en `_campanas`, reemplazar el `d.update({"ideas": [], "piezas": [], "piezas_listas": 0, "piezas_aprobadas": 0, ...})` por:

```python
        todas = _ideas(con, cliente, campana_id=d["id"])
        piezas_ = [i for i in todas if i["cf_id"] and i["estado_idea"] != "descartada"]
        d.update({"ideas": todas, "piezas": piezas_,
                  "piezas_listas": sum(1 for i in piezas_ if i["estado"] in _PIEZA_TERMINADA),
                  "piezas_aprobadas": sum(1 for i in piezas_ if i["revision"] == "aprobada"),
                  "referencias_total": int(d["referencias_total"] or 0),
                  "referencias_listas": int(d["referencias_listas"] or 0)})
```

- [ ] **Step 4: `sprints/estado.py`** — en `recalcular`, la llamada a `estado_campana` pasa a:

```python
        ideas_vivas = [i for i in (c.get("ideas") or []) if i.get("estado_idea") != "descartada"]
        nuevo = estado_campana(c["referencias_total"], total, ideas=ideas_vivas, piezas=c.get("piezas") or [])
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py tests/test_sprints_progreso_estado.py tests/test_rutas_sprints.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/datos.py sprints/estado.py
/opt/homebrew/bin/git add sprints/datos.py sprints/estado.py tests/test_sprints_datos.py tests/test_sprints_progreso_estado.py
/opt/homebrew/bin/git commit -m "Sprints: ideas (campana_pieza) unidas con la sesión de Crear; estados y progreso con piezas reales

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 4: `sprints/ideas.py` — prompt maestro y tarea `sprint_proponer_ideas`

**Files:**
- Create: `sprints/ideas.py`
- Modify: `tareas/sprints.py` (agregar)
- Test: `tests/test_sprints_ideas.py`, `tests/test_tareas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `analisis._llamar`, `analisis.AnalisisInvalido`, `datos.campana/ideas/crear_idea/actualizar_idea/referencias/persona/temporada/registrar_evento`, `catalogo_productos.encontrar`, `marca.guia_efectiva`, `banco_prompts.listar`, `flowplus_prompt.ENFOQUES`, `flowplus_modelos.VIDEO`, `proyectos.preferencias_flowplus/nombre_visible`.
- Produces: `ideas.PROMPT_IDEAS`, `ideas.faltantes(campana) -> (n_videos, n_imagenes)`, `ideas.contexto_campana(cliente, campana) -> dict` (`persona`, `producto`, `temporada`, `referencias`, `guia`, `marca`, `duraciones`, `ideas_existentes`, `descartadas`), `ideas.armar_prompt(ctx, n_videos, n_imagenes) -> str`, `ideas.parsear(texto, referencias_ids_validos, duraciones) -> list[dict]`, `ideas.proponer(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None) -> list[int]` (ids creados; con `reemplaza` descarta esa idea y propone una del mismo tipo); tarea `sprint_proponer_ideas` (`payload {cliente, campana_id, n_videos, n_imagenes, reemplaza}`, `job_id_ideas(cliente, campana_id) = f"{cliente}__campana{campana_id}__ideas"`, `encolar_ideas(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None) -> bool`, `max_intentos=2`).

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_sprints_ideas.py`:

```python
import json

import pytest

IDEA_V = {"titulo": "Espejo al amanecer", "tipo": "video", "escena": "La cámara rodea el espejo redondo mientras la luz del amanecer entra por la ventana.",
          "sonido": "pájaros lejanos, brisa", "enfoque": "producto", "gancho": "Luz que despierta", "referencias_ids": [1, 999],
          "duracion_s": 9, "plataformas": ["instagram", "tiktok", "otra"]}
IDEA_I = {"titulo": "Detalle del marco", "tipo": "imagen", "escena": "Primer plano del marco metálico con reflejo cálido.",
          "sonido": "", "enfoque": "rarísimo", "gancho": "Detalle que enamora", "referencias_ids": [], "duracion_s": None,
          "plataformas": ["instagram"]}


def test_parsear_valida_y_normaliza():
    from sprints import ideas
    salida = ideas.parsear(json.dumps({"ideas": [IDEA_V, IDEA_I, {"titulo": "sin escena", "tipo": "video"}]}),
                           referencias_ids_validos={1, 2}, duraciones=(5, 8, 10, 12))
    assert len(salida) == 2
    v, i = salida
    assert v["referencias_ids"] == [1] and v["duracion_s"] == 8 and v["plataformas"] == ["instagram", "tiktok"]
    assert i["enfoque"] == "producto" and i["duracion_s"] is None and i["sonido"] == ""
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear("nada", set(), (8,))
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear(json.dumps({"ideas": []}), set(), (8,))


def test_faltantes_descuenta_vivas():
    from sprints import ideas
    c = {"n_videos": 3, "n_imagenes": 2, "ideas": [
        {"tipo": "video", "estado_idea": "aprobada"}, {"tipo": "video", "estado_idea": "propuesta"},
        {"tipo": "video", "estado_idea": "descartada"}, {"tipo": "imagen", "estado_idea": "aprobada"}]}
    assert ideas.faltantes(c) == (1, 1)
    assert ideas.faltantes({"n_videos": 0, "n_imagenes": 1, "ideas": [{"tipo": "imagen", "estado_idea": "aprobada"}] * 3}) == (0, 0)


def _ctx(monkeypatch, datos, con_ref=True):
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural, sin saturar.")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo con luz", "regla": "Idéntico."})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", descripcion="Renueva su casa", tono="cercano",
                              senales_visuales=["cocina moderna"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", mood_visual={"paleta": ["#B3001B"], "luz": "cálida"})
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    rid = None
    if con_ref:
        rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz lateral", intencion=["iluminacion"])
        datos.actualizar_referencia("acme", rid, analisis={"resumen": "Espejo con luz lateral cálida", "paleta": ["#F2E9E4"], "movimiento": "sin movimiento"}, analisis_estado="listo")
    return sid, cid, rid


def test_armar_prompt_incluye_todo_el_contexto(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    datos.crear_idea("acme", cid, "video", "Ya existe", "x")
    datos.crear_idea("acme", cid, "video", "Descartada fea", "y", estado_idea="descartada")
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    for frag in ("Vidrios Sol", "Cliente Premium", "Busca calidad", "cocina moderna", "Espejo LED", "redondo con luz", "Navidad",
                 "regalos", "#B3001B", "Luz natural", f"ref {rid}", "Espejo con luz lateral cálida", "Ya existe", "Descartada fea",
                 "1 ideas de VIDEO", "1 ideas de IMAGEN"):
        assert frag in p, frag
    assert "Producto en primer plano" in p     # banco de prompts como ejemplos de estilo


def test_proponer_crea_ideas_y_reemplaza(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    respuestas = [json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})]
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: respuestas.pop(0))
    creadas = ideas.proponer("acme", cid)          # faltantes: 2 videos, 1 imagen → pide 2 y 1; Claude devuelve 1 y 1
    assert len(creadas) == 2
    lista = datos.ideas("acme", cid)
    assert lista[0]["titulo"] == "Espejo al amanecer" and lista[0]["referencias_ids"] == [rid] and lista[0]["duracion_s"] == 8.0
    assert lista[1]["tipo"] == "imagen" and lista[1]["enfoque"] == "producto"
    respuestas.append(json.dumps({"ideas": [dict(IDEA_V, titulo="Otra versión")]}))
    nuevas = ideas.proponer("acme", cid, reemplaza=lista[0]["id"])
    assert len(nuevas) == 1
    assert datos.idea("acme", lista[0]["id"])["estado_idea"] == "descartada"
    assert datos.idea("acme", nuevas[0])["titulo"] == "Otra versión" and datos.idea("acme", nuevas[0])["tipo"] == "video"
    assert any(e["tipo"] == "ideas_propuestas" for e in datos.eventos("acme", sid))


def test_proponer_sin_faltantes_no_llama(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    for _ in range(2):
        datos.crear_idea("acme", cid, "video", "V", "v", estado_idea="aprobada")
    datos.crear_idea("acme", cid, "imagen", "I", "i", estado_idea="aprobada")
    monkeypatch.setattr(analisis, "_llamar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    assert ideas.proponer("acme", cid) == []
    with pytest.raises(datos.ErrorDatos):
        ideas.proponer("acme", 999)
```

Agregar a `tests/test_tareas_sprints.py`:

```python
def test_proponer_ideas_tarea_y_encolar(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from sprints import datos, ideas
    from tareas import sprints as ts
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(ideas, "proponer", lambda c, cid_, n_videos=None, n_imagenes=None, reemplaza=None: [1, 2])
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_proponer_ideas"]({"payload": {"cliente": "acme", "campana_id": cid, "n_videos": 2, "n_imagenes": 0}})
    assert "2 ideas" in msg
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_ideas("acme", cid, n_videos=3, reemplaza=7) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == f"acme__campana{cid}__ideas" and tipo == "sprint_proponer_ideas"
    assert payload == {"cliente": "acme", "campana_id": cid, "n_videos": 3, "n_imagenes": None, "reemplaza": 7} and kw["max_intentos"] == 2
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_ideas.py tests/test_tareas_sprints.py -q`
Expected: FAIL (`No module named 'sprints.ideas'`).

- [ ] **Step 3: `sprints/ideas.py`**

```python
"""
Ideas por campaña (spec §2.1): el prompt maestro combina persona, producto,
temporada, análisis de las referencias, guía de marca y el banco de prompts, y
Claude devuelve N ideas de video y M de imagen que se guardan como
`campana_pieza` en estado `propuesta`. Solo texto: aquí no se genera nada.
"""
import json

import banco_prompts
import catalogo_productos
import flowplus_prompt
import marca
import proyectos
from providers import flowplus_modelos
from sprints import analisis, datos
from sprints.analisis import AnalisisInvalido

CLAVES_IDEA = ("titulo", "tipo", "escena", "sonido", "enfoque", "gancho", "referencias_ids", "duracion_s", "plataformas")

PROMPT_IDEAS = """Eres director creativo de anuncios cortos para redes sociales de la marca {marca}.

AUDIENCIA (persona): {persona}
PRODUCTO: {producto}
TEMPORADA: {temporada}
GUÍA DE ESTILO DE LA MARCA: {guia}
REFERENCIAS QUE INSPIRAN ESTA CAMPAÑA (id: qué se ve y qué reutilizar):
{referencias}
EJEMPLOS DEL TIPO DE ESCENA QUE FUNCIONA (inspiración de estilo, no los copies):
{banco}
IDEAS QUE YA EXISTEN EN ESTA CAMPAÑA (no las repitas): {existentes}
IDEAS DESCARTADAS (evita ese camino): {descartadas}

Propón {n_videos} ideas de VIDEO y {n_imagenes} ideas de IMAGEN, distintas entre sí, pensadas para esta audiencia y esta temporada, con el producto como protagonista. Responde SOLO con un objeto JSON {{"ideas": [...]}} donde cada idea tiene exactamente estas claves:
- "titulo": 3 a 6 palabras.
- "tipo": "video" o "imagen".
- "escena": instrucción para el generador, en segunda persona, 40 a 90 palabras: qué se ve, qué hace el producto o la persona, cámara, luz y ambiente. Sin marcas ni textos inventados.
- "sonido": para video, una línea con los sonidos de la escena (pasos, risas, ambiente); para imagen, "".
- "enfoque": una de {enfoques}.
- "gancho": frase de máximo 8 palabras para texto en pantalla.
- "referencias_ids": lista de ids de las referencias en las que se apoya (puede ir vacía).
- "duracion_s": para video, uno de {duraciones}; para imagen, null.
- "plataformas": lista con algunas de {plataformas}.
Todo en español."""


def faltantes(campana):
    """Cuántas ideas de video e imagen faltan para cubrir lo planeado, sin
    contar las descartadas."""
    vivas = [i for i in (campana.get("ideas") or []) if i.get("estado_idea") != "descartada"]
    nv = max(0, int(campana.get("n_videos") or 0) - sum(1 for i in vivas if i.get("tipo") == "video"))
    ni = max(0, int(campana.get("n_imagenes") or 0) - sum(1 for i in vivas if i.get("tipo") == "imagen"))
    return nv, ni


def _persona_texto(p):
    if not p:
        return "(sin persona)"
    partes = [p.get("nombre") or ""]
    for k in ("resumen", "descripcion"):
        if p.get(k):
            partes.append(str(p[k]).strip().rstrip("."))
    if p.get("edad_rango"):
        partes.append(f"edad {p['edad_rango']}")
    if p.get("tono"):
        partes.append(f"tono: {p['tono']}")
    if p.get("senales_visuales"):
        partes.append("señales visuales: " + ", ".join(p["senales_visuales"]))
    return ". ".join(x for x in partes if x)


def _temporada_texto(t):
    if not t:
        return "(sin temporada)"
    partes = [t.get("nombre") or "", f"{t.get('inicio')} → {t.get('fin')}"]
    if t.get("contexto"):
        partes.append(str(t["contexto"]).strip().rstrip("."))
    mood = t.get("mood_visual") or {}
    if mood.get("paleta"):
        partes.append("paleta: " + ", ".join(mood["paleta"]))
    if mood.get("luz"):
        partes.append(f"luz: {mood['luz']}")
    if mood.get("elementos"):
        partes.append("elementos: " + ", ".join(mood["elementos"]))
    return ". ".join(x for x in partes if x)


def _referencias_texto(refs):
    lineas = []
    for r in refs:
        a = r.get("analisis") or {}
        que = a.get("resumen") or r.get("descripcion") or r.get("titulo") or ""
        extra = []
        if a.get("movimiento") and a["movimiento"] != "sin movimiento":
            extra.append(f"movimiento: {a['movimiento']}")
        if a.get("paleta"):
            extra.append("paleta: " + ", ".join(a["paleta"]))
        intencion = ", ".join(datos.INTENCIONES_NOMBRE.get(i, i) for i in (r.get("intencion") or []))
        lineas.append(f"- ref {r['id']} ({r['tipo']}): {que}" + (f"; {'; '.join(extra)}" if extra else "")
                      + (f". Reutilizar: {intencion}" if intencion else "") + (f". Nota: {r['descripcion']}" if r.get("descripcion") else ""))
    return "\n".join(lineas) or "- (sin referencias todavía)"


def contexto_campana(cliente, campana):
    producto = catalogo_productos.encontrar(cliente, campana["catalogo_id"], "producto") or {}
    prefs = proyectos.preferencias_flowplus(cliente)
    modelo_video = prefs["modelo_video"] if prefs["modelo_video"] in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
    refs = datos.referencias(cliente, campana["id"])
    vivas = [i for i in (campana.get("ideas") or []) if i.get("estado_idea") != "descartada"]
    return {
        "marca": proyectos.nombre_visible(cliente),
        "persona": datos.persona(cliente, campana["persona_id"]),
        "producto": producto,
        "temporada": datos.temporada(cliente, campana["temporada_id"]),
        "referencias": refs,
        "guia": (marca.guia_efectiva(cliente) or "").strip() or "(sin guía de estilo todavía)",
        "duraciones": tuple(flowplus_modelos.VIDEO[modelo_video]["duraciones"]),
        "ideas_existentes": [i["titulo"] for i in vivas],
        "descartadas": [i["titulo"] for i in (campana.get("ideas") or []) if i.get("estado_idea") == "descartada"],
    }


def armar_prompt(ctx, n_videos, n_imagenes):
    prod = ctx.get("producto") or {}
    producto = (prod.get("nombre") or "(producto)") + (f": {prod['descripcion']}" if prod.get("descripcion") else "")
    if prod.get("regla"):
        producto += f". Regla de fidelidad: {prod['regla']}"
    banco = "\n".join(f"- {b['etiqueta']}: {b['texto']}" for b in banco_prompts.listar())
    return PROMPT_IDEAS.format(
        marca=ctx.get("marca") or "la marca", persona=_persona_texto(ctx.get("persona")), producto=producto,
        temporada=_temporada_texto(ctx.get("temporada")), guia=ctx.get("guia") or "", referencias=_referencias_texto(ctx.get("referencias") or []),
        banco=banco, existentes=", ".join(ctx.get("ideas_existentes") or []) or "ninguna",
        descartadas=", ".join(ctx.get("descartadas") or []) or "ninguna", n_videos=int(n_videos), n_imagenes=int(n_imagenes),
        enfoques=", ".join(f'"{e}"' for e in flowplus_prompt.ENFOQUES), duraciones=list(ctx.get("duraciones") or (8,)),
        plataformas=", ".join(f'"{p}"' for p in datos.PLATAFORMAS))


def _mas_cercana(valor, duraciones):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return float(duraciones[0])
    return float(min(duraciones, key=lambda d: abs(d - v)))


def parsear(texto, referencias_ids_validos, duraciones):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise AnalisisInvalido(f"JSON inválido: {e}")
    crudas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(crudas, list):
        raise AnalisisInvalido("El JSON no trae la lista «ideas».")
    limpias = []
    for c in crudas:
        if not isinstance(c, dict):
            continue
        titulo = str(c.get("titulo") or "").strip()
        escena = str(c.get("escena") or "").strip()
        tipo = c.get("tipo")
        if not titulo or not escena or tipo not in datos.TIPOS_PIEZA:
            continue
        enfoque = c.get("enfoque") if c.get("enfoque") in flowplus_prompt.ENFOQUES else "producto"
        refs = [int(x) for x in (c.get("referencias_ids") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()]
        refs = [r for r in refs if r in referencias_ids_validos]
        limpias.append({
            "titulo": titulo[:200], "tipo": tipo, "escena": escena, "sonido": str(c.get("sonido") or "").strip() if tipo == "video" else "",
            "enfoque": enfoque, "gancho": str(c.get("gancho") or "").strip()[:200], "referencias_ids": refs,
            "duracion_s": _mas_cercana(c.get("duracion_s"), duraciones) if tipo == "video" else None,
            "plataformas": [p for p in (c.get("plataformas") or []) if p in datos.PLATAFORMAS],
        })
    if not limpias:
        raise AnalisisInvalido("Ninguna idea venía completa.")
    return limpias


def proponer(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None):
    """Pide ideas a Claude y las guarda. Sin cantidades, propone lo que falta.
    `reemplaza`: descarta esa idea y propone UNA del mismo tipo. Devuelve los
    ids creados ([] si no hacía falta nada)."""
    campana = datos.campana(cliente, campana_id)
    if not campana:
        raise datos.ErrorDatos("Esa campaña no existe.")
    if reemplaza is not None:
        vieja = datos.idea(cliente, reemplaza)
        if not vieja or vieja["campana_id"] != campana_id:
            raise datos.ErrorDatos("Esa idea no existe en esta campaña.")
        datos.actualizar_idea(cliente, reemplaza, estado_idea="descartada")
        campana = datos.campana(cliente, campana_id)
        n_videos, n_imagenes = (1, 0) if vieja["tipo"] == "video" else (0, 1)
    if n_videos is None and n_imagenes is None:
        n_videos, n_imagenes = faltantes(campana)
    n_videos, n_imagenes = max(0, int(n_videos or 0)), max(0, int(n_imagenes or 0))
    if n_videos + n_imagenes == 0:
        return []
    ctx = contexto_campana(cliente, campana)
    validos = {r["id"] for r in ctx["referencias"]}
    texto = armar_prompt(ctx, n_videos, n_imagenes)
    content = [{"type": "text", "text": texto}]
    try:
        lista = parsear(analisis._llamar(content, max_tokens=3000), validos, ctx["duraciones"])
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        lista = parsear(analisis._llamar(content, max_tokens=3000), validos, ctx["duraciones"])
    videos = [i for i in lista if i["tipo"] == "video"][:n_videos]
    imagenes = [i for i in lista if i["tipo"] == "imagen"][:n_imagenes]
    creadas = []
    for i in videos + imagenes:
        creadas.append(datos.crear_idea(cliente, campana_id, i["tipo"], i["titulo"], i["escena"], sonido=i["sonido"],
                                        enfoque=i["enfoque"], gancho=i["gancho"], referencias_ids=i["referencias_ids"],
                                        duracion_s=i["duracion_s"], plataformas=i["plataformas"]))
    datos.registrar_evento(cliente, campana["sprint_id"], "ideas_propuestas",
                           f"{len(creadas)} idea(s) propuesta(s) para la campaña {campana['orden'] + 1}",
                           {"campana_id": campana_id, "cp_ids": creadas, "reemplaza": reemplaza}, campana_id=campana_id)
    return creadas
```

- [ ] **Step 4: `tareas/sprints.py`** — imports: agregar `from sprints import analisis, archivos, datos, estado, ideas, sugerencias` (sustituye la línea de import de `sprints`) y al final:

```python
def job_id_ideas(cliente, campana_id):
    return f"{cliente}__campana{campana_id}__ideas"


def encolar_ideas(cliente, campana_id, n_videos=None, n_imagenes=None, reemplaza=None):
    return trabajos.encolar(job_id_ideas(cliente, campana_id), "sprint_proponer_ideas",
                            {"cliente": cliente, "campana_id": campana_id, "n_videos": n_videos, "n_imagenes": n_imagenes,
                             "reemplaza": reemplaza}, cliente=cliente, duracion_estimada=40, max_intentos=2)


@registrar("sprint_proponer_ideas")
def ejecutar_proponer_ideas(tarea):
    p = tarea["payload"]
    cliente, campana_id = p["cliente"], int(p["campana_id"])
    creadas = ideas.proponer(cliente, campana_id, n_videos=p.get("n_videos"), n_imagenes=p.get("n_imagenes"),
                             reemplaza=p.get("reemplaza"))
    c = datos.campana(cliente, campana_id)
    if c:
        estado.recalcular(cliente, c["sprint_id"])
    return f"{len(creadas)} ideas propuestas — revísalas y aprueba las que sirvan."
```

Actualizar el docstring del módulo con la línea `sprint_proponer_ideas -> f"{cliente}__campana{campana_id}__ideas" (max_intentos=2)`.

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_ideas.py tests/test_tareas_sprints.py tests/test_worker.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/ideas.py tareas/sprints.py
/opt/homebrew/bin/git add sprints/ideas.py tareas/sprints.py tests/test_sprints_ideas.py tests/test_tareas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: ideas por campaña con el prompt maestro (persona, producto, temporada, referencias, marca)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `sprints/produccion.py` — estimado, sesiones de Crear, lote, reintento, regeneración y progreso

**Files:**
- Create: `sprints/produccion.py`
- Modify: `notificaciones.py` (`TIPOS` + `"sprint_lote"`)
- Test: `tests/test_sprints_produccion.py`

**Interfaces:**
- Consumes: `creative_flow.crear/actualizar/cargar/duplicar`, `flowplus_prompt.armar/ENFOQUES`, `flowplus_lanzar.lanzar/job_id`, `flowplus_modelos.VIDEO/IMAGEN/estimate_video/estimate_imagen`, `proyectos.preferencias_flowplus`, `catalogo_productos.encontrar/CATEGORIAS`, `marca.guia_efectiva/negative_prompt_efectivo`, `storage.r2_uploader.upload_image`, `cola.consultar_por_job`, `datos.*`, `estado.recalcular`.
- Produces: `PRIORIDAD_LOTE = 3`, `DURACION_DEFECTO_S = 8`, `SEGUNDOS_VIDEO = 180`, `SEGUNDOS_IMAGEN = 60`; `modelos(cliente, modelo_video=None, modelo_imagen=None) -> (mv, mi)`; `pendientes(cliente, sprint_id, campana_id=None) -> list[(campana, idea)]` (aprobadas sin `cf_id`); `estimar(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None) -> dict{videos, imagenes, usd, segundos, modelo_video, modelo_imagen, modelo_video_nombre, modelo_imagen_nombre, acumulado_usd, texto}`; `referencias_sesion(cliente, campana, idea) -> (referencias, referencias_urls, productos_sel)`; `crear_sesion(cliente, sprint, campana, idea, mv, mi) -> cf_id`; `lanzar_lote(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None) -> dict{encoladas, omitidas, cf_ids, usd}`; `reintentar(cliente, cp_id) -> bool`; `regenerar(cliente, cp_id) -> str` (nuevo cf_id); `progreso(cliente, sprint_id) -> dict{sprint: {...}, campanas: [{id, ...}]}` con `planeadas, encoladas, generando, listas, error, aprobadas, costo_usd, segundos_restantes`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_produccion.py
import pytest


@pytest.fixture()
def escenario(base_temporal, monkeypatch):
    import catalogo_productos, marca, proyectos
    from sprints import datos
    from storage import r2_uploader
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: None)
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {
        "id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "regla": "Idéntico.", "categoria": "producto",
        "referencias": ["/tmp/espejo/1.jpg", "/tmp/espejo/2.jpg"], "imagenes": ["1.jpg", "2.jpg"]})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad", tono="cercano", senales_visuales=["cocina"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos")
    sid = datos.crear_sprint("acme", "Sprint octubre", "2026-10-01", "2026-10-31", destinos=["es_CO", "en_US"])
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/ref1.jpg", descripcion="luz")
    r2 = datos.agregar_referencia("acme", cid, "video", "https://r2/ref2.mp4", frame_url="https://r2/ref2.frame.jpg", descripcion="mov")
    iv = datos.crear_idea("acme", cid, "video", "Amanecer", "Rodea el espejo", sonido="pájaros", enfoque="producto",
                          gancho="Luz", referencias_ids=[r2], duracion_s=8, plataformas=["instagram"], estado_idea="aprobada")
    ii = datos.crear_idea("acme", cid, "imagen", "Marco", "Primer plano", enfoque="producto", estado_idea="aprobada")
    ip = datos.crear_idea("acme", cid, "video", "Sin aprobar", "x", estado_idea="propuesta")
    return {"sid": sid, "cid": cid, "iv": iv, "ii": ii, "ip": ip, "r1": r1, "r2": r2}


def test_estimar_cuenta_aprobadas_sin_sesion(escenario):
    from sprints import produccion
    from providers import flowplus_modelos
    e = produccion.estimar("acme", escenario["sid"])
    assert e["videos"] == 1 and e["imagenes"] == 1 and e["segundos"] == 180 + 60
    esperado = flowplus_modelos.estimate_video("wan3", 8)["usd"] + flowplus_modelos.estimate_imagen("seedream_v5_pro", 3)["usd"]
    assert abs(e["usd"] - esperado) < 1e-6 and e["modelo_video"] == "wan3" and "USD" in e["texto"]
    e2 = produccion.estimar("acme", escenario["sid"], modelo_video="kling_o3_pro")
    assert e2["modelo_video"] == "kling_o3_pro" and e2["usd"] > e["usd"]
    assert produccion.estimar("acme", escenario["sid"], modelo_video="inventado")["modelo_video"] == "wan3"


def test_crear_sesion_arma_referencias_prompt_y_vinculo(escenario):
    import creative_flow
    from sprints import datos, produccion
    sp = datos.sprint("acme", escenario["sid"])
    c = sp["campanas"][0]
    idea = datos.idea("acme", escenario["iv"])
    refs, urls, productos = produccion.referencias_sesion("acme", c, idea)
    assert productos == ["Espejo LED"]
    assert refs[0]["etiqueta"] == "@Producto 1" and refs[0]["producto"] == "Espejo LED" and refs[0]["regla"] == "Idéntico."
    # la referencia de la idea (r2, video) va antes que la otra (r1)
    assert [r["url"] for r in refs[1:3]] == ["https://r2/ref2.mp4", "https://r2/ref1.jpg"]
    assert refs[1]["tipo"] == "video" and refs[1]["frame_url"] == "https://r2/ref2.frame.jpg" and refs[1]["etiqueta"] == "@Video 1"
    assert refs[2]["etiqueta"] == "@Imagen 1" and urls[1] == "https://r2/ref2.frame.jpg"
    cf_id = produccion.crear_sesion("acme", sp, c, idea, "wan3", "seedream_v5_pro")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["sprint"] == {"sprint_id": sp["id"], "sprint_nombre": "Sprint octubre", "campana_id": c["id"], "campana_n": 1, "cp_id": idea["id"]}
    assert e["tipo"] == "video" and e["modelo"] == "wan3" and e["duracion_objetivo"] == 8 and e["tono"] == "cercano"
    assert e["platforms"] == ["instagram"] and e["aspect_ratio"] == "9:16" and e["enfoque"] == "producto"
    assert "AUDIENCIA: Busca calidad" in e["prompt_relleno"] and "TEMPORADA: Navidad" in e["prompt_relleno"]
    assert "SONIDO: pájaros" in e["prompt_relleno"] and "ESCENA: Rodea el espejo" in e["prompt_relleno"]
    assert datos.idea("acme", escenario["iv"])["cf_id"] == cf_id
    idea_img = datos.idea("acme", escenario["ii"])
    cf2 = produccion.crear_sesion("acme", sp, c, idea_img, "wan3", "seedream_v5_pro")
    e2 = creative_flow.cargar("acme")[cf2]
    assert e2["tipo"] == "imagen" and e2["modelo"] == "seedream_v5_pro" and "SONIDO" not in e2["prompt_relleno"]


def test_lanzar_lote_encola_con_prioridad_y_registra(escenario, monkeypatch):
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append((cf, e["tipo"], prioridad)) or True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2 and r["omitidas"] == 0 and len(r["cf_ids"]) == 2 and r["usd"] > 0
    assert sorted(t for _, t, _ in lanzados) == ["imagen", "video"] and all(p == 3 for _, _, p in lanzados)
    sp = datos.sprint("acme", escenario["sid"])
    assert sp["extra"]["lote_en_curso"] is True and abs(sp["extra"]["costo_estimado_usd"] - r["usd"]) < 1e-6
    assert sp["eventos"][0]["tipo"] == "lote_encolado" and sp["eventos"][0]["datos"]["encoladas"] == 2
    assert datos.idea("acme", escenario["ip"])["cf_id"] is None      # la propuesta no se genera
    r2 = produccion.lanzar_lote("acme", escenario["sid"])
    assert r2["encoladas"] == 0                                        # idempotente: ya tienen sesión
    with pytest.raises(datos.ErrorDatos):
        produccion.lanzar_lote("acme", 999)


def test_reintentar_y_regenerar(escenario, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append(cf) or True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    cf = datos.idea("acme", escenario["iv"])["cf_id"]
    assert produccion.reintentar("acme", escenario["iv"]) is False       # no está en error
    creative_flow.actualizar("acme", cf, estado="error", error="timeout")
    assert produccion.reintentar("acme", escenario["iv"]) is True and lanzados[-1] == cf
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    datos.actualizar_idea("acme", escenario["iv"], qa={"score": 40}, revision="rechazada", revision_motivo="feo")
    nuevo = produccion.regenerar("acme", escenario["iv"])
    assert nuevo != cf and lanzados[-1] == nuevo
    i = datos.idea("acme", escenario["iv"])
    assert i["cf_id"] == nuevo and i["qa"] is None and i["revision"] == "pendiente" and i["revision_motivo"] is None
    assert creative_flow.cargar("acme")[nuevo]["sprint"]["cp_id"] == escenario["iv"]
    assert i["extra"]["cf_anteriores"] == [cf]


def test_progreso_agregado(escenario, monkeypatch):
    import cola
    import creative_flow
    import flowplus_lanzar
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    produccion.lanzar_lote("acme", escenario["sid"])
    cfv, cfi = datos.idea("acme", escenario["iv"])["cf_id"], datos.idea("acme", escenario["ii"])["cf_id"]
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: {"estado": "pendiente"} if cfv in job_id else {"estado": "en_curso"})
    p = produccion.progreso("acme", escenario["sid"])
    s = p["sprint"]
    assert s["planeadas"] == 3 and s["encoladas"] == 1 and s["generando"] == 1 and s["listas"] == 0 and s["error"] == 0
    assert s["segundos_restantes"] == 180 + 60 and p["campanas"][0]["id"] == escenario["cid"]
    creative_flow.actualizar("acme", cfv, estado="video_listo", video_url="https://r2/v.mp4", usd=0.8)
    creative_flow.actualizar("acme", cfi, estado="error", error="x")
    datos.actualizar_idea("acme", escenario["iv"], revision="aprobada")
    s = produccion.progreso("acme", escenario["sid"])["sprint"]
    assert s["listas"] == 1 and s["error"] == 1 and s["aprobadas"] == 1 and abs(s["costo_usd"] - 0.8) < 1e-6 and s["segundos_restantes"] == 0
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_produccion.py -q`
Expected: FAIL (`No module named 'sprints.produccion'`).

- [ ] **Step 3: `sprints/produccion.py`**

```python
"""
Producción por lotes (spec §2.2): de cada idea aprobada a una sesión de Crear
(FlowPlus), con el costo estimado antes de encolar y prioridad baja para no
bloquear a quien genera una pieza suelta. Reintento (misma sesión) y
regeneración (sesión nueva con `creative_flow.duplicar`) también pasan por aquí,
siempre con `max_intentos=1` (vía flowplus_lanzar). `progreso` agrega el
estado de todas las piezas de un sprint para el tablero.
"""
import os

import catalogo_productos
import cola
import creative_flow
import flowplus_lanzar
import flowplus_prompt
import marca
import proyectos
from providers import flowplus_modelos
from sprints import datos, estado
from storage import r2_uploader

PRIORIDAD_LOTE = 3
DURACION_DEFECTO_S = 8
SEGUNDOS_VIDEO = 180
SEGUNDOS_IMAGEN = 60
MAX_REFERENCIAS = 15
MAX_IMAGENES_MODELO = 10
PLATAFORMAS_VERTICALES = {"instagram", "tiktok"}


# ---------------------------------------------------------------- lote ---

def modelos(cliente, modelo_video=None, modelo_imagen=None):
    prefs = proyectos.preferencias_flowplus(cliente)
    mv = modelo_video if modelo_video in flowplus_modelos.VIDEO else prefs.get("modelo_video")
    mi = modelo_imagen if modelo_imagen in flowplus_modelos.IMAGEN else prefs.get("modelo_imagen")
    if mv not in flowplus_modelos.VIDEO:
        mv = flowplus_modelos.VIDEO_POR_DEFECTO
    if mi not in flowplus_modelos.IMAGEN:
        mi = flowplus_modelos.IMAGEN_POR_DEFECTO
    return mv, mi


def _sprint(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    return sp


def pendientes(cliente, sprint_id, campana_id=None):
    """[(campana, idea)] aprobadas y todavía sin sesión de Crear."""
    sp = _sprint(cliente, sprint_id)
    salida = []
    for c in sp["campanas"]:
        if campana_id is not None and c["id"] != campana_id:
            continue
        for i in c["ideas"]:
            if i["estado_idea"] == "aprobada" and not i["cf_id"]:
                salida.append((c, i))
    return salida


def _duracion(idea):
    try:
        return int(float(idea.get("duracion_s") or DURACION_DEFECTO_S))
    except (TypeError, ValueError):
        return DURACION_DEFECTO_S


def _n_referencias(campana):
    return max(1, min(MAX_IMAGENES_MODELO, 1 + int(campana.get("referencias_total") or 0)))


def _texto_tiempo(segundos):
    h, m = divmod(int(round(segundos / 60.0)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def estimar(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None):
    sp = _sprint(cliente, sprint_id)
    mv, mi = modelos(cliente, modelo_video, modelo_imagen)
    videos = imagenes = 0
    usd = 0.0
    for c, i in pendientes(cliente, sprint_id, campana_id):
        if i["tipo"] == "video":
            videos += 1
            usd += float((flowplus_modelos.estimate_video(mv, _duracion(i)) or {}).get("usd") or 0.0)
        else:
            imagenes += 1
            usd += float((flowplus_modelos.estimate_imagen(mi, n_referencias=_n_referencias(c)) or {}).get("usd") or 0.0)
    segundos = videos * SEGUNDOS_VIDEO + imagenes * SEGUNDOS_IMAGEN
    acumulado = float((sp.get("extra") or {}).get("costo_estimado_usd") or 0.0)
    nombre_v, nombre_i = flowplus_modelos.VIDEO[mv]["nombre"], flowplus_modelos.IMAGEN[mi]["nombre"]
    texto = (f"{videos} video(s) ({nombre_v}) y {imagenes} imagen(es) ({nombre_i}): USD {usd:.2f} estimado · "
             f"acumulado del sprint USD {acumulado:.2f} · tiempo estimado {_texto_tiempo(segundos)}")
    return {"videos": videos, "imagenes": imagenes, "usd": round(usd, 4), "segundos": segundos, "modelo_video": mv,
            "modelo_imagen": mi, "modelo_video_nombre": nombre_v, "modelo_imagen_nombre": nombre_i,
            "acumulado_usd": round(acumulado, 4), "texto": texto}


# ------------------------------------------------------------ sesiones ---

def _logos(cliente):
    """Igual que dashboard._logos: los archivos de clientes/<c>/logos/ por su URL pública."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    carpeta = os.path.join(base, "clientes", cliente, "logos")
    public_base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    if not os.path.isdir(carpeta) or not public_base:
        return []
    salida = []
    for f in sorted(os.listdir(carpeta)):
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            salida.append({"url": f"{public_base}/clientes/{cliente}/logos/{f}"})
    return salida


def referencias_sesion(cliente, campana, idea):
    """Referencias de la sesión como las arma Crear: el producto del catálogo
    (con regla de fidelidad), luego las referencias de la campaña (primero las
    que inspiran la idea) y los logos del proyecto. Devuelve
    (referencias, referencias_urls, productos_sel)."""
    referencias, productos_sel = [], []
    activo = catalogo_productos.encontrar(cliente, campana["catalogo_id"], categoria="producto")
    if activo:
        info_cat = catalogo_productos.CATEGORIAS["producto"]
        ruta = (activo.get("referencias") or [None])[0]
        if ruta:
            try:
                url = r2_uploader.upload_image(ruta, f"clientes/{cliente}/{info_cat['carpeta']}/{activo['id']}/{os.path.basename(ruta)}")
                referencias.append({"tipo": "imagen", "url": url, "frame_url": url, "etiqueta": "@Producto 1",
                                    "categoria": "producto", "activo": activo["nombre"], "regla": activo.get("regla") or "",
                                    "producto": activo["nombre"]})
            except Exception:
                pass
        productos_sel.append(activo["nombre"])
    refs = datos.referencias(cliente, campana["id"])
    primero = [int(x) for x in (idea.get("referencias_ids") or [])]
    ordenadas = [r for r in refs if r["id"] in primero] + [r for r in refs if r["id"] not in primero]
    n_img = n_vid = 0
    for r in ordenadas:
        if r["tipo"] == "video":
            n_vid += 1
            referencias.append({"tipo": "video", "url": r["url"], "frame_url": r.get("frame_url") or r["url"],
                                "etiqueta": f"@Video {n_vid}", "origen": r.get("origen")})
        else:
            n_img += 1
            referencias.append({"tipo": "imagen", "url": r["url"], "frame_url": r["url"], "etiqueta": f"@Imagen {n_img}",
                                "origen": r.get("origen")})
    logos = [{"tipo": "imagen", "url": l["url"], "frame_url": l["url"], "etiqueta": f"@Logo {i}", "logo": True}
             for i, l in enumerate(_logos(cliente)[:2], start=1)]
    referencias = (referencias + logos)[:MAX_REFERENCIAS]
    referencias_urls = [r["frame_url"] for r in referencias][:MAX_IMAGENES_MODELO]
    return referencias, referencias_urls, productos_sel


def _aspect_ratio(plataformas):
    if any(p in PLATAFORMAS_VERTICALES for p in plataformas):
        return "9:16"
    if plataformas == ["youtube"]:
        return "16:9"
    return "9:16"


def _contexto(cliente, campana):
    p = datos.persona(cliente, campana["persona_id"]) or {}
    t = datos.temporada(cliente, campana["temporada_id"]) or {}
    return {"persona": {k: p.get(k) for k in ("resumen", "descripcion", "tono", "senales_visuales")},
            "temporada": {k: t.get(k) for k in ("nombre", "contexto", "mood_visual")}}, p


def crear_sesion(cliente, sprint, campana, idea, modelo_video, modelo_imagen):
    """Crea la sesión de Crear de una idea aprobada, arma su prompt y la
    vincula (idea.cf_id y extra["sprint"]). No encola nada."""
    referencias, referencias_urls, productos_sel = referencias_sesion(cliente, campana, idea)
    contexto, persona = _contexto(cliente, campana)
    enfoque = idea.get("enfoque") if idea.get("enfoque") in flowplus_prompt.ENFOQUES else "producto"
    info = flowplus_prompt.ENFOQUES[enfoque]
    escena = idea["escena"]
    if idea["tipo"] == "video" and idea.get("sonido"):
        escena = f"{escena}\nSONIDO: {idea['sonido']}. Sin diálogo hablado ni música de fondo."
    prompt = flowplus_prompt.armar(escena, referencias, con_persona=info["con_persona"],
                                   guia_marca=marca.guia_efectiva(cliente), negative_marca=marca.negative_prompt_efectivo(cliente),
                                   logos=[r for r in referencias if r.get("logo")], enfoque=enfoque, contexto=contexto)
    plataformas = list(idea.get("plataformas") or [])
    cf_id = creative_flow.crear(
        cliente, [], productos_sel, [], idea["escena"], _duracion(idea) if idea["tipo"] == "video" else 0,
        persona.get("tono") or "", "A", referencias_urls=referencias_urls, platforms=plataformas,
        extra_sprint={"sprint_id": sprint["id"], "sprint_nombre": sprint["nombre"], "campana_id": campana["id"],
                      "campana_n": int(campana["orden"]) + 1, "cp_id": idea["id"]})
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt, aspect_ratio=_aspect_ratio(plataformas), tipo=idea["tipo"],
                             modelo=modelo_video if idea["tipo"] == "video" else modelo_imagen, referencias=referencias,
                             con_persona=info["con_persona"], enfoque=enfoque, enfoque_nombre=info["nombre"])
    datos.actualizar_idea(cliente, idea["id"], cf_id=cf_id)
    return cf_id


def lanzar_lote(cliente, sprint_id, campana_id=None, modelo_video=None, modelo_imagen=None):
    """Crea y encola una sesión por idea aprobada sin sesión. Devuelve
    {encoladas, omitidas, cf_ids, usd}. La puerta de costo es de la ruta: aquí
    ya se decidió gastar."""
    sp = _sprint(cliente, sprint_id)
    mv, mi = modelos(cliente, modelo_video, modelo_imagen)
    est = estimar(cliente, sprint_id, campana_id, mv, mi)
    encoladas, omitidas, cf_ids = 0, 0, []
    for c, i in pendientes(cliente, sprint_id, campana_id):
        cf_id = crear_sesion(cliente, sp, c, i, mv, mi)
        entry = creative_flow.cargar(cliente)[cf_id]
        if flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_LOTE):
            encoladas += 1
            cf_ids.append(cf_id)
        else:
            omitidas += 1
    if encoladas:
        extra = dict(sp.get("extra") or {})
        extra["costo_estimado_usd"] = round(float(extra.get("costo_estimado_usd") or 0.0) + est["usd"], 4)
        extra["lote_en_curso"] = True
        extra["modelos_lote"] = {"video": mv, "imagen": mi}
        datos.actualizar_sprint(cliente, sprint_id, extra=extra)
        datos.registrar_evento(cliente, sprint_id, "lote_encolado",
                               f"Lote de {encoladas} pieza(s) encolado: {est['videos']} video(s), {est['imagenes']} imagen(es), USD {est['usd']:.2f} estimado",
                               {"encoladas": encoladas, "omitidas": omitidas, "usd": est["usd"], "campana_id": campana_id,
                                "modelo_video": mv, "modelo_imagen": mi}, campana_id=campana_id)
        estado.recalcular(cliente, sprint_id)
    return {"encoladas": encoladas, "omitidas": omitidas, "cf_ids": cf_ids, "usd": est["usd"]}


def _idea_con_sesion(cliente, cp_id):
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        raise datos.ErrorDatos("Esa pieza no tiene una sesión generada.")
    return i


def reintentar(cliente, cp_id):
    """Vuelve a encolar la misma sesión (solo si quedó en error). Gasta."""
    i = _idea_con_sesion(cliente, cp_id)
    entry = creative_flow.cargar(cliente).get(i["cf_id"])
    if not entry or entry.get("estado") != "error":
        return False
    ok = flowplus_lanzar.lanzar(cliente, i["cf_id"], entry, prioridad=PRIORIDAD_LOTE)
    if ok:
        datos.registrar_evento(cliente, i["sprint_id"], "pieza_reintentada", f"Reintento de «{i['titulo']}»",
                               {"cp_id": cp_id, "cf_id": i["cf_id"]}, campana_id=i["campana_id"])
        estado.recalcular(cliente, i["sprint_id"])
    return ok


def regenerar(cliente, cp_id):
    """Sesión nueva a partir de la actual (misma idea y prompt), QA y revisión
    en blanco; la sesión anterior queda en `extra.cf_anteriores`. Gasta."""
    i = _idea_con_sesion(cliente, cp_id)
    nuevo = creative_flow.duplicar(cliente, i["cf_id"])
    extra = dict(i.get("extra") or {})
    extra["cf_anteriores"] = list(extra.get("cf_anteriores") or []) + [i["cf_id"]]
    datos.actualizar_idea(cliente, cp_id, cf_id=nuevo, qa=None, revision="pendiente", revision_motivo=None, extra=extra)
    entry = creative_flow.cargar(cliente)[nuevo]
    flowplus_lanzar.lanzar(cliente, nuevo, entry, prioridad=PRIORIDAD_LOTE)
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_regenerada", f"Regeneración de «{i['titulo']}»",
                           {"cp_id": cp_id, "cf_id": nuevo, "anterior": i["cf_id"]}, campana_id=i["campana_id"])
    sp = datos.sprint(cliente, i["sprint_id"], con_eventos=False)
    if sp:
        extra_sp = dict(sp.get("extra") or {})
        extra_sp["lote_en_curso"] = True
        datos.actualizar_sprint(cliente, i["sprint_id"], extra=extra_sp)
    estado.recalcular(cliente, i["sprint_id"])
    return nuevo


# ------------------------------------------------------------ progreso ---

def _resumen(piezas, planeadas):
    r = {"planeadas": planeadas, "encoladas": 0, "generando": 0, "listas": 0, "error": 0, "aprobadas": 0,
         "costo_usd": 0.0, "segundos_restantes": 0}
    for p in piezas:
        r["costo_usd"] += float(p.get("costo_usd") or 0.0)
        if p.get("revision") == "aprobada":
            r["aprobadas"] += 1
        est = p.get("estado")
        if est in ("listo", "degradada"):
            r["listas"] += 1
        elif est == "error":
            r["error"] += 1
        elif est in ("pendiente", "generando"):
            tarea = cola.consultar_por_job(flowplus_lanzar.job_id(p["cliente"], p["cf_id"])) or {}
            if tarea.get("estado") == "en_curso":
                r["generando"] += 1
            else:
                r["encoladas"] += 1
            r["segundos_restantes"] += SEGUNDOS_VIDEO if p.get("tipo") == "video" else SEGUNDOS_IMAGEN
    r["costo_usd"] = round(r["costo_usd"], 4)
    return r


def progreso(cliente, sprint_id):
    sp = estado.recalcular(cliente, sprint_id)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    campanas = []
    todas = []
    for c in sp["campanas"]:
        planeadas = int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0)
        campanas.append({"id": c["id"], "estado": c["estado"], **_resumen(c["piezas"], planeadas)})
        todas.extend(c["piezas"])
    total = sum(int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0) for c in sp["campanas"])
    return {"estado": sp["estado"], "sprint": _resumen(todas, total), "campanas": campanas}
```

- [ ] **Step 4: `notificaciones.py`** — `TIPOS` pasa a incluir `"sprint_lote"`:

```python
TIPOS = ("propuesta", "ganador", "rechazo_meta", "error_lanzamiento", "tope", "tienda", "sprint_lote")
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_produccion.py tests/test_notificaciones.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/produccion.py notificaciones.py
/opt/homebrew/bin/git add sprints/produccion.py notificaciones.py tests/test_sprints_produccion.py
/opt/homebrew/bin/git commit -m "Sprints: producción por lotes (estimado, sesiones de Crear con contexto, prioridad 3, reintento, regeneración, progreso)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 6: `sprints/qa.py` — control de calidad automático y periódica `sprint_qa_pendientes`

**Files:**
- Create: `sprints/qa.py`
- Modify: `tareas/sprints.py` (agregar), `worker.py` (`PERIODICAS`)
- Test: `tests/test_sprints_qa.py`, `tests/test_tareas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `analisis._llamar`, `referencias_link.fotogramas`, `final_edition.cortes.ffprobe_json`, `datos.*`, `marca.guia_efectiva`, `notificaciones.avisar`, `requests`.
- Produces: `qa.CHECKS = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")`, `qa.UMBRAL_DEFECTO = 70`, `qa.PROMPT_QA`, `qa.veredicto(score, checks, umbral) -> "pasa"|"revisar"|"falla"` (pura), `qa.formato(ruta_local, tipo, duracion_objetivo, aspect_ratio) -> (ok, nota)` (ffprobe; sin archivo → `(True, "sin archivo local; formato no verificado")`), `qa.parsear(texto) -> {score, checks(4)}`, `qa.evaluar(cliente, idea, entry, campana, umbral=None) -> dict{score, checks, veredicto, modelo, costo_usd, evaluado_en}`, `qa.archivo_local(entry) -> str|None` (descarga a temp si `video_local` no existe); tareas `sprint_qa_pieza` (`payload {cliente, cp_id}`, `job_id_qa = f"{cliente}__cp{cp_id}__qa"`, `max_intentos=3`), `sprint_qa_pendientes` (periódica 300 s: encola QA para piezas listas sin `qa`; y para cada sprint con `extra.lote_en_curso` sin piezas pendientes/generando, avisa `sprint_lote`, registra `lote_terminado` y apaga la bandera); `worker.PERIODICAS += ("sprint_qa_pendientes", 300)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_qa.py
import json

import pytest

CHECKS_OK = {"consistencia_visual": {"ok": True, "nota": "coherente"}, "presencia_marca": {"ok": True, "nota": "logo visible"},
             "compatibilidad_campana": {"ok": True, "nota": "espejo en escena"}, "calidad_minima": {"ok": True, "nota": "limpio"}}


def test_veredicto_puro():
    from sprints import qa
    todos = {k: {"ok": True, "nota": ""} for k in qa.CHECKS}
    assert qa.veredicto(85, todos, 70) == "pasa"
    assert qa.veredicto(60, todos, 70) == "revisar"
    assert qa.veredicto(90, dict(todos, presencia_marca={"ok": False, "nota": "sin logo"}), 70) == "revisar"
    assert qa.veredicto(95, dict(todos, calidad_minima={"ok": False, "nota": "manos"}), 70) == "falla"
    assert qa.veredicto(95, dict(todos, formato={"ok": False, "nota": "16:9"}), 70) == "falla"


def test_parsear_exige_score_y_cuatro_checks():
    from sprints import qa
    r = qa.parsear(json.dumps({"score": 82, "checks": CHECKS_OK}))
    assert r["score"] == 82 and set(r["checks"]) == set(qa.CHECKS) - {"formato"}
    r = qa.parsear(json.dumps({"score": 150, "checks": dict(CHECKS_OK, calidad_minima={"ok": "sí", "nota": 5})}))
    assert r["score"] == 100 and r["checks"]["calidad_minima"] == {"ok": True, "nota": "5"}
    with pytest.raises(qa.AnalisisInvalido):
        qa.parsear(json.dumps({"score": 80, "checks": {"consistencia_visual": {"ok": True}}}))
    with pytest.raises(qa.AnalisisInvalido):
        qa.parsear("nada")


def test_formato_con_ffprobe_falso(monkeypatch, tmp_path):
    from final_edition import cortes
    from sprints import qa
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.2"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    assert qa.formato(str(v), "video", 8, "9:16") == (True, "9:16, 8.2 s")
    ok, nota = qa.formato(str(v), "video", 12, "9:16")
    assert ok is False and "duración" in nota
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {}, "streams": [{"codec_type": "video", "width": 1280, "height": 720}]})
    ok, nota = qa.formato(str(v), "imagen", None, "9:16")
    assert ok is False and "16:9" in nota
    assert qa.formato(None, "video", 8, "9:16") == (True, "sin archivo local; formato no verificado")


def test_evaluar_arma_prompt_y_mezcla_formato(base_temporal, monkeypatch, tmp_path):
    import marca
    import referencias_link
    from final_edition import cortes
    from sprints import analisis, datos, qa
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    pid = datos.crear_persona("acme", "Premium", resumen="Busca calidad")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz")
    datos.actualizar_referencia("acme", rid, analisis={"resumen": "luz lateral cálida", "paleta": ["#FFF"]}, analisis_estado="listo")
    cp = datos.crear_idea("acme", cid, "video", "Amanecer", "rodea", estado_idea="aprobada", duracion_s=8)
    v = tmp_path / "v.mp4"; v.write_bytes(b"x")
    monkeypatch.setattr(referencias_link, "fotogramas", lambda ruta, n=4: [b"f1", b"f2", b"f3"])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.0"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps({"score": 88, "checks": CHECKS_OK}))
    entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16", "duracion_objetivo": 8, "modelo": "wan3"}
    r = qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
    assert r["veredicto"] == "pasa" and r["score"] == 88 and r["checks"]["formato"] == {"ok": True, "nota": "9:16, 8.0 s"}
    assert r["modelo"] and r["evaluado_en"] and r["costo_usd"] > 0
    texto = capturado["c"][0]["text"]
    for frag in ("Premium", "Busca calidad", "Navidad", "Luz natural", "luz lateral cálida", "Amanecer", "rodea"):
        assert frag in texto, frag
    assert len([b for b in capturado["c"] if b["type"] == "image"]) == 3
    # Imagen sin archivo local: usa la URL y formato no verificado.
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps({"score": 50, "checks": CHECKS_OK}))
    r2 = qa.evaluar("acme", datos.idea("acme", cp), {"tipo": "imagen", "video_url": "https://r2/i.png", "video_local": "/no/existe.png"}, datos.campana("acme", cid))
    assert r2["veredicto"] == "revisar" and r2["checks"]["formato"]["ok"] is True
    assert [b for b in capturado["c"] if b["type"] == "image"][0]["source"] == {"type": "url", "url": "https://r2/i.png"}
```

Agregar a `tests/test_tareas_sprints.py`:

```python
def _pieza_lista(datos, creative_flow, cliente="acme", estado_pieza="video_listo"):
    pid = datos.crear_persona(cliente, "P")
    tid = datos.crear_temporada(cliente, "T", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint(cliente, "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana(cliente, sid, pid, "espejo", tid, 1, 0)
    cp = datos.crear_idea(cliente, cid, "video", "A", "a", estado_idea="aprobada")
    cf = creative_flow.crear(cliente, [], ["E"], [], "a", 8, "", "A")
    datos.actualizar_idea(cliente, cp, cf_id=cf)
    creative_flow.actualizar(cliente, cf, estado=estado_pieza, video_url="https://r2/v.mp4")
    return sid, cid, cp, cf


def test_qa_pieza_guarda_resultado_y_error(base_temporal, monkeypatch):
    import creative_flow
    import tareas
    from sprints import datos, qa
    from tareas import sprints as ts
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {"score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x"})
    tareas.cargar_todas()
    assert ts.job_id_qa("acme", cp) == f"acme__cp{cp}__qa"
    msg = tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"]["veredicto"] == "pasa" and "pasa" in msg
    assert any(e["tipo"] == "qa_evaluada" for e in datos.eventos("acme", sid))
    def rompe(*a, **k):
        raise RuntimeError("visión caída")
    monkeypatch.setattr(qa, "evaluar", rompe)
    datos.actualizar_idea("acme", cp, qa=None)
    with pytest.raises(RuntimeError):
        tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": cp}})
    assert datos.idea("acme", cp)["qa"] is None       # queda pendiente para el reintento de la cola
    assert tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": 999}}) == "La pieza ya no existe."


def test_qa_pendientes_encola_y_avisa_fin_de_lote(base_temporal, monkeypatch):
    import cola
    import creative_flow
    import notificaciones
    import tareas
    from sprints import datos
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    datos.actualizar_sprint("acme", sid, extra={"lote_en_curso": True})
    sid2, cid2, cp2, cf2 = _pieza_lista(datos, creative_flow, cliente="otro", estado_pieza="video_generando")
    datos.actualizar_sprint("otro", sid2, extra={"lote_en_curso": True})
    encolados, avisos = [], []
    monkeypatch.setattr(cola, "encolar", lambda tipo, payload, **kw: encolados.append((tipo, payload, kw.get("job_id"))) or 1)
    monkeypatch.setattr(notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo, asunto)) or False)
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert [(t, p["cp_id"]) for t, p, _ in encolados] == [("sprint_qa_pieza", cp)]
    assert avisos == [("acme", "sprint_lote", "Lote terminado: S")] and "1 pieza" in msg
    assert datos.sprint("acme", sid)["extra"]["lote_en_curso"] is False
    assert datos.sprint("otro", sid2)["extra"]["lote_en_curso"] is True
    assert datos.sprint("acme", sid)["eventos"][0]["tipo"] == "lote_terminado"
    datos.actualizar_idea("acme", cp, qa={"veredicto": "pasa"})
    encolados.clear()
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    assert encolados == []


def test_periodica_qa_registrada():
    import worker
    assert ("sprint_qa_pendientes", 300) in worker.PERIODICAS
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_qa.py tests/test_tareas_sprints.py -q`
Expected: FAIL (`No module named 'sprints.qa'`).

- [ ] **Step 3: `sprints/qa.py`**

```python
"""
Control de calidad automático de una pieza generada (spec §2.4): Claude con
visión (imagen, o tres fotogramas del video) juzga cuatro cosas y ffprobe
verifica el formato. El resultado se guarda en `campana_pieza.qa`; el QA nunca
genera ni gasta en proveedores de video: marca, explica y la persona decide.
"""
import base64
import json
import os
import tempfile
from datetime import datetime

import requests

import marca
from final_edition import cortes
from sprints import analisis, datos
from sprints.analisis import AnalisisInvalido

CHECKS = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")
CHECKS_IA = CHECKS[:4]
UMBRAL_DEFECTO = 70
COSTO_USD_ESTIMADO = 0.02
TOLERANCIA_DURACION = 0.2

PROMPT_QA = """Eres el control de calidad de anuncios cortos para redes sociales de la marca {marca}. Vas a ver una pieza generada con IA (una imagen, o fotogramas en orden de un video de {duracion}).

CAMPAÑA: persona «{persona}»; producto «{producto}»; temporada «{temporada}».
IDEA QUE DEBÍA CUMPLIR: «{titulo}»: {escena}
GUÍA DE ESTILO DE LA MARCA: {guia}
REFERENCIAS QUE INSPIRARON LA CAMPAÑA: {referencias}

Evalúa y responde SOLO con un objeto JSON con esta forma:
{{"score": <entero 0-100, calidad general para publicar>,
 "checks": {{
   "consistencia_visual": {{"ok": true|false, "nota": "..."}},   ¿coincide con la guía de estilo y con la estética de las referencias?
   "presencia_marca": {{"ok": true|false, "nota": "..."}},       ¿la marca o el producto se reconocen como suyos (sin logos inventados)?
   "compatibilidad_campana": {{"ok": true|false, "nota": "..."}}, ¿se ve el producto y encaja con la persona y la temporada?
   "calidad_minima": {{"ok": true|false, "nota": "..."}}         ¿sin artefactos, texto quemado, manos o productos deformados, ni cortes raros?
 }}}}
Notas de máximo 20 palabras, en español, concretas (qué está mal y dónde)."""


def veredicto(score, checks, umbral):
    """pasa: score >= umbral y todos ok. falla: calidad_minima o formato mal.
    revisar: el resto."""
    for clave in ("calidad_minima", "formato"):
        if not (checks.get(clave) or {}).get("ok", True):
            return "falla"
    if int(score) >= int(umbral) and all((checks.get(k) or {}).get("ok", False) for k in CHECKS):
        return "pasa"
    return "revisar"


def _aspecto(ancho, alto):
    if not ancho or not alto:
        return None
    r = ancho / alto
    for nombre, valor in (("9:16", 9 / 16), ("16:9", 16 / 9), ("1:1", 1.0), ("4:5", 0.8)):
        if abs(r - valor) < 0.03:
            return nombre
    return f"{ancho}x{alto}"


def formato(ruta_local, tipo, duracion_objetivo, aspect_ratio):
    """(ok, nota) con ffprobe sobre el archivo local. Sin archivo, no se verifica."""
    if not ruta_local or not os.path.exists(ruta_local):
        return True, "sin archivo local; formato no verificado"
    try:
        info = cortes.ffprobe_json(ruta_local)
    except Exception as e:
        return True, f"ffprobe falló ({e}); formato no verificado"
    video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    aspecto = _aspecto(video.get("width"), video.get("height"))
    problemas = []
    if aspect_ratio and aspecto and aspecto != aspect_ratio:
        problemas.append(f"aspecto {aspecto}, se pedía {aspect_ratio}")
    dur = None
    if tipo == "video":
        try:
            dur = float((info.get("format") or {}).get("duration") or 0) or None
        except (TypeError, ValueError):
            dur = None
        if dur and duracion_objetivo:
            obj = float(duracion_objetivo)
            if abs(dur - obj) > obj * TOLERANCIA_DURACION:
                problemas.append(f"duración {dur:.1f} s, se pedían {obj:.0f} s")
    if problemas:
        return False, "; ".join(problemas)
    return True, (aspecto or "?") + (f", {dur:.1f} s" if dur else "")


def parsear(texto):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise AnalisisInvalido(f"JSON inválido: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("checks"), dict):
        raise AnalisisInvalido("El JSON no trae score y checks.")
    try:
        score = max(0, min(100, int(round(float(data.get("score"))))))
    except (TypeError, ValueError):
        raise AnalisisInvalido("score inválido.")
    checks = {}
    for k in CHECKS_IA:
        c = data["checks"].get(k)
        if not isinstance(c, dict) or "ok" not in c:
            raise AnalisisInvalido(f"Falta el check {k}.")
        ok = c["ok"] if isinstance(c["ok"], bool) else str(c["ok"]).strip().lower() in ("true", "sí", "si", "ok", "1")
        checks[k] = {"ok": ok, "nota": str(c.get("nota") or "").strip()[:200]}
    return {"score": score, "checks": checks}


def archivo_local(entry):
    """Ruta local de la pieza (la que dejó el worker) o, para videos, una
    descarga temporal (hacen falta fotogramas y ffprobe). Las imágenes van a
    Claude por URL, así que sin archivo local no se descarga nada."""
    ruta = entry.get("video_local")
    if ruta and os.path.exists(ruta):
        return ruta
    url = entry.get("video_url")
    if not url or (entry.get("tipo") or "video") != "video":
        return None
    ext = ".mp4"
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except Exception:
        return None
    fd, tmp = tempfile.mkstemp(prefix="qa_", suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return tmp


def _bloques_imagen(entry, ruta):
    tipo = entry.get("tipo") or "video"
    if tipo == "video" and ruta and os.path.exists(ruta):
        from referencias_link import fotogramas
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b).decode()}}
                for b in fotogramas(ruta, n=3)]
    url = entry.get("video_url") if tipo == "imagen" else (entry.get("url_miniatura") or entry.get("video_url"))
    return [{"type": "image", "source": {"type": "url", "url": url}}] if url else []


def evaluar(cliente, idea, entry, campana, umbral=None):
    umbral = int(umbral or UMBRAL_DEFECTO)
    persona = datos.persona(cliente, campana["persona_id"]) or {}
    temporada = datos.temporada(cliente, campana["temporada_id"]) or {}
    refs = [r for r in datos.referencias(cliente, campana["id"]) if (r.get("analisis") or {}).get("resumen")]
    ruta = archivo_local(entry)
    texto = PROMPT_QA.format(
        marca=campana.get("marca") or cliente, duracion=f"{entry.get('duracion_objetivo') or '?'} s",
        persona=f"{persona.get('nombre', '')}: {persona.get('resumen') or persona.get('descripcion') or ''}".strip(": "),
        producto=campana.get("catalogo_id"), temporada=f"{temporada.get('nombre', '')}: {temporada.get('contexto') or ''}".strip(": "),
        titulo=idea.get("titulo") or "", escena=idea.get("escena") or "", guia=(marca.guia_efectiva(cliente) or "").strip() or "(sin guía)",
        referencias="; ".join(r["analisis"]["resumen"] for r in refs) or "(sin referencias analizadas)")
    imagenes = _bloques_imagen(entry, ruta)
    if not imagenes:
        raise AnalisisInvalido("La pieza no tiene imagen ni fotograma que evaluar.")
    content = [{"type": "text", "text": texto}] + imagenes
    try:
        r = parsear(analisis._llamar(content, max_tokens=600))
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        r = parsear(analisis._llamar(content, max_tokens=600))
    ok, nota = formato(ruta, entry.get("tipo") or "video", entry.get("duracion_objetivo"), entry.get("aspect_ratio") or "9:16")
    r["checks"]["formato"] = {"ok": ok, "nota": nota}
    if ruta and ruta != entry.get("video_local"):
        try:
            os.remove(ruta)
        except OSError:
            pass
    from generador_prompts import MODEL
    return {"score": r["score"], "checks": r["checks"], "veredicto": veredicto(r["score"], r["checks"], umbral),
            "modelo": MODEL, "costo_usd": COSTO_USD_ESTIMADO, "evaluado_en": datetime.now().isoformat(timespec="seconds"),
            "umbral": umbral}
```

- [ ] **Step 4: `tareas/sprints.py`** — imports: `import cola`, `import creative_flow`, `import notificaciones`, `import sqlalchemy as sa`, `import db`, y `from sprints import analisis, archivos, datos, estado, ideas, qa, sugerencias`. Al final:

```python
def job_id_qa(cliente, cp_id):
    return f"{cliente}__cp{cp_id}__qa"


@registrar("sprint_qa_pieza")
def ejecutar_qa_pieza(tarea):
    """QA de una pieza lista. Si falla, la tarea reintenta sola (max 3): el QA
    no gasta en generación, solo centavos de visión."""
    p = tarea["payload"]
    cliente, cp_id = p["cliente"], int(p["cp_id"])
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        return "La pieza ya no existe."
    entry = creative_flow.cargar(cliente).get(i["cf_id"])
    campana = datos.campana(cliente, i["campana_id"])
    if not entry or not campana:
        return "La pieza ya no existe."
    sp = datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}
    umbral = (sp.get("extra") or {}).get("qa_umbral") or qa.UMBRAL_DEFECTO
    campana["marca"] = proyectos.nombre_visible(cliente)
    resultado = qa.evaluar(cliente, i, entry, campana, umbral=umbral)
    datos.actualizar_idea(cliente, cp_id, qa=resultado)
    datos.registrar_evento(cliente, i["sprint_id"], "qa_evaluada",
                           f"QA de «{i['titulo']}»: {resultado['veredicto']} ({resultado['score']})",
                           {"cp_id": cp_id, "score": resultado["score"], "veredicto": resultado["veredicto"]},
                           campana_id=i["campana_id"])
    return f"QA: {resultado['veredicto']} ({resultado['score']}/100)."


def _piezas_listas_sin_qa():
    """(cliente, cp_id) de ideas con sesión lista/degradada y qa NULL."""
    cp, pz = db.campana_pieza, db.pieza
    with db.conectar() as con:
        filas = con.execute(sa.select(cp.c.cliente, cp.c.id).select_from(
            cp.join(pz, sa.and_(pz.c.legado_id == cp.c.cf_id, pz.c.cliente == cp.c.cliente, pz.c.tipo.in_(datos.TIPOS_PIEZA))))
            .where(cp.c.qa.is_(None), cp.c.estado_idea != "descartada", pz.c.estado.in_(("listo", "degradada")))
            .order_by(cp.c.id)).all()
    return [(f.cliente, f.id) for f in filas]


def _sprints_con_lote():
    """Sprints con `extra.lote_en_curso`. Se filtra en Python: son pocos y el
    JSON de SQLite no garantiza el tipo del booleano."""
    s = db.sprint
    with db.conectar() as con:
        filas = con.execute(sa.select(s.c.cliente, s.c.id, s.c.nombre, s.c.extra).where(s.c.archivado.is_(False))).all()
    return [(f.cliente, f.id, f.nombre) for f in filas if (f.extra or {}).get("lote_en_curso")]


@registrar("sprint_qa_pendientes")
def ejecutar_qa_pendientes(tarea):
    """Periódica (5 min): encola el QA de las piezas listas sin evaluar y avisa
    cuando un lote termina (ninguna pieza pendiente ni generando)."""
    n = 0
    for cliente, cp_id in _piezas_listas_sin_qa():
        if cola.encolar("sprint_qa_pieza", {"cliente": cliente, "cp_id": cp_id}, cliente=cliente,
                        job_id=job_id_qa(cliente, cp_id), duracion_estimada=30, max_intentos=3):
            n += 1
    terminados = 0
    for cliente, sid, nombre in _sprints_con_lote():
        sp = estado.recalcular(cliente, sid)
        if not sp:
            continue
        vivas = [p for c in sp["campanas"] for p in c["piezas"] if p.get("estado") in ("pendiente", "generando")]
        if vivas:
            continue
        piezas = [p for c in sp["campanas"] for p in c["piezas"]]
        listas = sum(1 for p in piezas if p.get("estado") in ("listo", "degradada"))
        errores = sum(1 for p in piezas if p.get("estado") == "error")
        extra = dict(sp.get("extra") or {})
        extra["lote_en_curso"] = False
        datos.actualizar_sprint(cliente, sid, extra=extra)
        datos.registrar_evento(cliente, sid, "lote_terminado", f"Lote terminado: {listas} lista(s), {errores} con error",
                               {"listas": listas, "errores": errores})
        notificaciones.avisar(cliente, "sprint_lote", f"Lote terminado: {nombre}",
                              f"El lote del sprint «{nombre}» terminó: {listas} pieza(s) lista(s) y {errores} con error. "
                              "Entra a la bandeja de revisión para aprobar o rechazar.")
        terminados += 1
    return f"{n} pieza(s) a QA; {terminados} lote(s) terminado(s)."
```

`worker.py`: agregar `("sprint_qa_pendientes", 300)` al final de `PERIODICAS`.

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_qa.py tests/test_tareas_sprints.py tests/test_worker.py tests/test_tareas_swap.py -q`
Expected: PASS (si `test_tareas_swap.py` lista los tipos registrados de forma exhaustiva, agregar `sprint_proponer_ideas`, `sprint_qa_pendientes`, `sprint_qa_pieza` en orden alfabético).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/qa.py tareas/sprints.py worker.py
/opt/homebrew/bin/git add sprints/qa.py tareas/sprints.py worker.py tests/test_sprints_qa.py tests/test_tareas_sprints.py tests/test_tareas_swap.py
/opt/homebrew/bin/git commit -m "Sprints: QA automático con visión y ffprobe (nunca gasta), periódica que encola el QA y avisa el fin del lote

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `sprints/revision.py` y `sprints/entrega.py` (+ tarea `sprint_empaquetar`)

**Files:**
- Create: `sprints/revision.py`, `sprints/entrega.py`
- Modify: `tareas/sprints.py` (agregar)
- Test: `tests/test_sprints_revision_entrega.py`, `tests/test_tareas_sprints.py` (agregar)

**Interfaces:**
- Produces (revision): `aprobar(cliente, cp_id) -> bool`, `rechazar(cliente, cp_id, motivo) -> bool` (motivo obligatorio; retira la sesión de `estado_videos.json`), `aprobar_pasaron_qa(cliente, sprint_id) -> int`, `resumen(cliente, sprint_id) -> dict{planeadas, terminadas, aprobadas, rechazadas, sin_revisar, error, costo_usd, costo_estimado_usd, dias}`, `cerrar(cliente, sprint_id) -> dict` (estado `completado`, evento `sprint_cerrado`; solo desde `revision`), `reabrir(cliente, sprint_id) -> bool` (evento `sprint_reabierto`).
- Produces (entrega): `enlaces(cliente, sprint_id) -> list[dict{campana_n, persona, producto, temporada, titulo, tipo, url, cp_id}]` (aprobadas con url), `nombre_archivo(cp, ext) -> str`, `empaquetar(cliente, sprint_id, descargar=None) -> dict{url, n, creado_en}` (zip en `salidas/<cliente>/sprints/sprint_<id>_<AAAAMMDD_HHMM>.zip`, subido a R2 con `upload_file(..., "application/zip")`, guardado en `sprint.extra["zip"]`); tarea `sprint_empaquetar` (`payload {cliente, sprint_id}`, `job_id_zip = f"{cliente}__sprint{sid}__zip"`, `max_intentos=2`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_revision_entrega.py
import io
import os
import zipfile

import pytest


def _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path):
    import estado as estado_videos
    monkeypatch.setattr(estado_videos, "_path", lambda c: str(tmp_path / f"{c}_videos.json"))
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    sid = datos.crear_sprint("acme", "Sprint octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    piezas = []
    for n, (tipo, est, qa) in enumerate([("video", "video_listo", {"veredicto": "pasa", "score": 90}),
                                         ("video", "video_listo", {"veredicto": "revisar", "score": 60}),
                                         ("imagen", "error", None)]):
        cp = datos.crear_idea("acme", cid, tipo, f"Pieza {n}", "x", estado_idea="aprobada")
        cf = creative_flow.crear("acme", [], ["E"], [], "x", 8, "", "A")
        creative_flow.actualizar("acme", cf, tipo=tipo, estado=est, video_url=f"https://r2/{n}.{'mp4' if tipo == 'video' else 'png'}", usd=0.5)
        datos.actualizar_idea("acme", cp, cf_id=cf, qa=qa)
        if est == "video_listo":
            ev = estado_videos.cargar("acme"); ev[cf] = {"estado": "pendiente"}; estado_videos.guardar("acme", ev)
        piezas.append((cp, cf))
    return sid, cid, piezas


def test_aprobar_rechazar_y_aprobar_qa(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    import estado as estado_videos
    from sprints import datos, estado, revision
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    (cp0, cf0), (cp1, cf1), (cp2, cf2) = piezas
    assert revision.aprobar("acme", cp0) is True and datos.idea("acme", cp0)["revision"] == "aprobada"
    with pytest.raises(datos.ErrorDatos):
        revision.rechazar("acme", cp1, "")
    assert revision.rechazar("acme", cp1, "mal encuadre") is True
    i1 = datos.idea("acme", cp1)
    assert i1["revision"] == "rechazada" and i1["revision_motivo"] == "mal encuadre"
    assert cf1 not in estado_videos.cargar("acme") and cf0 in estado_videos.cargar("acme")
    assert revision.aprobar("acme", cp2) is False        # en error, no se puede aprobar
    datos.actualizar_idea("acme", cp1, revision="pendiente")
    assert revision.aprobar_pasaron_qa("acme", sid) == 0   # cp0 ya aprobada, cp1 es "revisar"
    datos.actualizar_idea("acme", cp1, qa={"veredicto": "pasa", "score": 80})
    assert revision.aprobar_pasaron_qa("acme", sid) == 1
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert "pieza_aprobada" in tipos and "pieza_rechazada" in tipos


def test_resumen_cerrar_reabrir(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    from sprints import datos, estado, revision
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    datos.actualizar_sprint("acme", sid, extra={"costo_estimado_usd": 1.2})
    # Con una pieza todavía generando, el sprint NO está en revisión y no se puede cerrar:
    creative_flow.actualizar("acme", piezas[2][1], estado="video_generando")
    assert estado.recalcular("acme", sid)["estado"] == "generando"
    with pytest.raises(datos.ErrorDatos):
        revision.cerrar("acme", sid)
    creative_flow.actualizar("acme", piezas[2][1], estado="error", error="x")
    # Con todas las piezas terminadas (listo/error) el sprint está en revisión:
    assert estado.recalcular("acme", sid)["estado"] == "revision"
    revision.aprobar("acme", piezas[0][0]); revision.rechazar("acme", piezas[1][0], "no")
    r = revision.resumen("acme", sid)
    assert r == {"planeadas": 3, "terminadas": 2, "aprobadas": 1, "rechazadas": 1, "sin_revisar": 0, "error": 1,
                 "costo_usd": 1.5, "costo_estimado_usd": 1.2, "dias": 30}
    r2 = revision.cerrar("acme", sid)
    assert r2["aprobadas"] == 1 and datos.sprint("acme", sid)["estado"] == "completado"
    assert estado.recalcular("acme", sid)["estado"] == "completado"
    assert revision.reabrir("acme", sid) is True and estado.recalcular("acme", sid)["estado"] == "revision"
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert tipos[0] == "sprint_reabierto" and "sprint_cerrado" in tipos


def test_enlaces_y_empaquetar(base_temporal, monkeypatch, tmp_path):
    import creative_flow
    from sprints import datos, entrega, revision
    from storage import r2_uploader
    sid, cid, piezas = _sprint_en_revision(datos, creative_flow, monkeypatch, tmp_path)
    revision.aprobar("acme", piezas[0][0])
    lista = entrega.enlaces("acme", sid)
    assert len(lista) == 1 and lista[0]["url"] == "https://r2/0.mp4" and lista[0]["campana_n"] == 1 and lista[0]["persona"] == "Premium"
    assert entrega.nombre_archivo(lista[0], ".mp4") == "campana1_video_Pieza-0.mp4"
    subidas = []
    monkeypatch.setattr(r2_uploader, "upload_file", lambda ruta, key, ct: subidas.append((ruta, key, ct)) or f"https://r2/{key}")
    monkeypatch.setattr(entrega, "BASE_DIR", str(tmp_path))
    r = entrega.empaquetar("acme", sid, descargar=lambda url: b"contenido-" + url.encode())
    assert r["n"] == 1 and r["url"].startswith("https://r2/clientes/acme/sprints/") and r["url"].endswith(".zip")
    ruta, key, ct = subidas[0]
    assert ct == "application/zip" and os.path.exists(ruta)
    with zipfile.ZipFile(ruta) as z:
        assert z.namelist() == ["campana1_video_Pieza-0.mp4"] and z.read("campana1_video_Pieza-0.mp4") == b"contenido-https://r2/0.mp4"
    assert datos.sprint("acme", sid)["extra"]["zip"]["url"] == r["url"]
    with pytest.raises(datos.ErrorDatos):
        entrega.empaquetar("acme", 999)
```

Agregar a `tests/test_tareas_sprints.py`:

```python
def test_empaquetar_tarea(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from sprints import entrega
    from tareas import sprints as ts
    monkeypatch.setattr(entrega, "empaquetar", lambda c, sid, descargar=None: {"url": "https://r2/z.zip", "n": 3, "creado_en": "x"})
    tareas.cargar_todas()
    assert "3 pieza" in tareas.REGISTRO["sprint_empaquetar"]({"payload": {"cliente": "acme", "sprint_id": 1}})
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_zip("acme", 4) is True and encolados[0][0] == "acme__sprint4__zip" and encolados[0][3]["max_intentos"] == 2
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_revision_entrega.py tests/test_tareas_sprints.py -q`
Expected: FAIL (módulos ausentes).

- [ ] **Step 3: `sprints/revision.py`**

```python
"""
Bandeja de revisión y cierre del sprint (spec §2.5, §2.6). Aprobar y rechazar
escriben `campana_pieza.revision` y un evento; rechazar también retira la
sesión de la cola de publicación (estado_videos.json). Cerrar deja el sprint
`completado` con un resumen; reabrir lo devuelve a `revision`.
"""
from datetime import date

import estado as estado_videos
from sprints import datos, estado

TERMINADAS = ("listo", "degradada")


def _pieza(cliente, cp_id):
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        raise datos.ErrorDatos("Esa pieza no tiene una sesión generada.")
    return i


def aprobar(cliente, cp_id):
    i = _pieza(cliente, cp_id)
    if i.get("estado") not in TERMINADAS:
        return False
    datos.actualizar_idea(cliente, cp_id, revision="aprobada", revision_motivo=None)
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_aprobada", f"Aprobada «{i['titulo']}»", {"cp_id": cp_id},
                           campana_id=i["campana_id"])
    estado.recalcular(cliente, i["sprint_id"])
    return True


def rechazar(cliente, cp_id, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise datos.ErrorDatos("Escribe el motivo del rechazo.")
    i = _pieza(cliente, cp_id)
    if i.get("estado") not in TERMINADAS:
        return False
    datos.actualizar_idea(cliente, cp_id, revision="rechazada", revision_motivo=motivo)
    # Fuera de la cola de publicación: una rechazada no se publica.
    cola = estado_videos.cargar(cliente)
    if i["cf_id"] in cola:
        cola.pop(i["cf_id"], None)
        estado_videos.guardar(cliente, cola)
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_rechazada", f"Rechazada «{i['titulo']}»: {motivo}",
                           {"cp_id": cp_id, "motivo": motivo}, campana_id=i["campana_id"])
    estado.recalcular(cliente, i["sprint_id"])
    return True


def aprobar_pasaron_qa(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    n = 0
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p.get("revision") == "pendiente" and p.get("estado") in TERMINADAS and (p.get("qa") or {}).get("veredicto") == "pasa":
                if aprobar(cliente, p["id"]):
                    n += 1
    return n


def resumen(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    piezas = [p for c in sp["campanas"] for p in c["piezas"]]
    terminadas = [p for p in piezas if p.get("estado") in TERMINADAS]
    try:
        dias = (date.fromisoformat(sp["fin"]) - date.fromisoformat(sp["inicio"])).days
    except (TypeError, ValueError):
        dias = None
    return {
        "planeadas": sp["piezas_planeadas"], "terminadas": len(terminadas),
        "aprobadas": sum(1 for p in terminadas if p.get("revision") == "aprobada"),
        "rechazadas": sum(1 for p in terminadas if p.get("revision") == "rechazada"),
        "sin_revisar": sum(1 for p in terminadas if p.get("revision") == "pendiente"),
        "error": sum(1 for p in piezas if p.get("estado") == "error"),
        "costo_usd": round(sum(float(p.get("costo_usd") or 0.0) for p in piezas), 4),
        "costo_estimado_usd": round(float((sp.get("extra") or {}).get("costo_estimado_usd") or 0.0), 4),
        "dias": dias,
    }


def cerrar(cliente, sprint_id):
    sp = estado.recalcular(cliente, sprint_id)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    if sp["estado"] != "revision":
        raise datos.ErrorDatos("Solo se cierra un sprint que está en revisión.")
    r = resumen(cliente, sprint_id)
    datos.actualizar_sprint(cliente, sprint_id, estado="completado")
    datos.registrar_evento(cliente, sprint_id, "sprint_cerrado",
                           f"Sprint cerrado: {r['aprobadas']} aprobadas, {r['rechazadas']} rechazadas, USD {r['costo_usd']:.2f}", r)
    return r


def reabrir(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp or sp["estado"] != "completado":
        return False
    datos.actualizar_sprint(cliente, sprint_id, estado="revision")
    datos.registrar_evento(cliente, sprint_id, "sprint_reabierto", "Sprint reabierto a revisión", {})
    estado.recalcular(cliente, sprint_id)
    return True
```

- [ ] **Step 4: `sprints/entrega.py`**

```python
"""
Entrega del sprint (spec §2.6): enlaces de las piezas aprobadas y un zip con
todas, subido a R2 y guardado en `sprint.extra["zip"]`.
"""
import os
import re
import zipfile
from datetime import datetime

import requests

from sprints import datos
from storage import r2_uploader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def enlaces(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    salida = []
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p.get("revision") == "aprobada" and p.get("url_video"):
                salida.append({"cp_id": p["id"], "campana_n": int(c["orden"]) + 1, "persona": c["persona_nombre"],
                               "producto": c["catalogo_id"], "temporada": c["temporada_nombre"], "titulo": p.get("titulo") or "",
                               "tipo": p.get("tipo"), "url": p["url_video"]})
    return salida


def _slug(texto):
    s = re.sub(r"[^A-Za-z0-9]+", "-", (texto or "").strip()).strip("-")
    return s[:40] or "pieza"


def nombre_archivo(enlace, ext):
    return f"campana{enlace['campana_n']}_{enlace['tipo']}_{_slug(enlace['titulo'])}{ext}"


def _descargar(url):
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    return resp.content


def empaquetar(cliente, sprint_id, descargar=None):
    """Baja las aprobadas, arma el zip, lo sube a R2 y guarda el enlace."""
    descargar = descargar or _descargar
    lista = enlaces(cliente, sprint_id)
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "sprints")
    os.makedirs(carpeta, exist_ok=True)
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M")
    nombre = f"sprint_{sprint_id}_{marca_tiempo}.zip"
    ruta = os.path.join(carpeta, nombre)
    usados = set()
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for e in lista:
            ext = ".mp4" if e["tipo"] == "video" else os.path.splitext(e["url"].split("?")[0])[1] or ".png"
            archivo = nombre_archivo(e, ext)
            if archivo in usados:
                archivo = f"{os.path.splitext(archivo)[0]}_{e['cp_id']}{ext}"
            usados.add(archivo)
            z.writestr(archivo, descargar(e["url"]))
    url = r2_uploader.upload_file(ruta, f"clientes/{cliente}/sprints/{nombre}", "application/zip")
    info = {"url": url, "n": len(lista), "creado_en": datetime.now().isoformat(timespec="seconds")}
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    extra = dict((sp or {}).get("extra") or {})
    extra["zip"] = info
    datos.actualizar_sprint(cliente, sprint_id, extra=extra)
    datos.registrar_evento(cliente, sprint_id, "zip_listo", f"Zip de entrega con {len(lista)} pieza(s)", info)
    return info
```

- [ ] **Step 5: `tareas/sprints.py`** — agregar `entrega` al import de `sprints` y al final:

```python
def job_id_zip(cliente, sprint_id):
    return f"{cliente}__sprint{sprint_id}__zip"


def encolar_zip(cliente, sprint_id):
    return trabajos.encolar(job_id_zip(cliente, sprint_id), "sprint_empaquetar",
                            {"cliente": cliente, "sprint_id": sprint_id}, cliente=cliente,
                            duracion_estimada=120, max_intentos=2)


@registrar("sprint_empaquetar")
def ejecutar_empaquetar(tarea):
    p = tarea["payload"]
    info = entrega.empaquetar(p["cliente"], int(p["sprint_id"]))
    return f"Zip listo con {info['n']} pieza(s)."
```

- [ ] **Step 6: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_revision_entrega.py tests/test_tareas_sprints.py tests/test_tareas_swap.py -q`
Expected: PASS (agregar `sprint_empaquetar` a la lista exhaustiva de `test_tareas_swap.py` si existe).

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile sprints/revision.py sprints/entrega.py tareas/sprints.py
/opt/homebrew/bin/git add sprints/revision.py sprints/entrega.py tareas/sprints.py tests/test_sprints_revision_entrega.py tests/test_tareas_sprints.py tests/test_tareas_swap.py
/opt/homebrew/bin/git commit -m "Sprints: revisión (aprobar, rechazar, aprobar las que pasaron QA), cierre/reapertura y entrega (enlaces y zip)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 8: Rutas y pantallas de ideas y lote (página de ideas, modal de costo, tablero, distintivo en Crear)

**Files:**
- Modify: `sprints/rutas.py` (imports + rutas al final; `progreso_json` ampliado), `templates/sprint_detalle.html`, `templates/_tab_creativeflowplus.html`
- Create: `templates/campana_ideas.html`, `templates/_sprint_lote_modal.html`
- Test: `tests/test_rutas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `ideas.faltantes/proponer`, `produccion.estimar/lanzar_lote/reintentar/regenerar/progreso/modelos`, `tareas_sprints.encolar_ideas/job_id_ideas`, `datos.ideas/idea/actualizar_idea/eliminar_idea/referencias`, `flowplus_modelos.VIDEO/IMAGEN`.
- Produces endpoints: `sprints.campana_ideas` (GET `/<sid>/campanas/<cid>/ideas`), `sprints.ideas_proponer` (POST `.../ideas/proponer`, form `n_videos`, `n_imagenes` opcionales o `mas`), `sprints.ideas_aprobar_todas` (POST `.../ideas/aprobar_todas`), `sprints.idea_editar` (POST `/ideas/<cp_id>`, JSON o form: `titulo`, `escena`, `sonido`, `gancho`), `sprints.idea_aprobar`/`idea_descartar`/`idea_otra` (POST `/ideas/<cp_id>/aprobar|descartar|otra`), `sprints.lote_estimar` (GET `/<sid>/lote/estimar?campana_id=&modelo_video=&modelo_imagen=`, JSON), `sprints.lote` (POST `/<sid>/lote`, form `campana_id`, `modelo_video`, `modelo_imagen`), `sprints.pieza_reintentar`/`pieza_regenerar` (POST `/ideas/<cp_id>/reintentar|regenerar`); `progreso_json` devuelve además `lote` (resumen del sprint) y `lote` por campaña. Helper `_idea_o_404(cliente, cp_id, sid=None)`. Función Jinja global `abrirLote(cid)` en el modal (JS).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_rutas_sprints.py`)

```python
@pytest.fixture()
def con_ideas(app, monkeypatch):
    import catalogo_productos, marca, proyectos
    from sprints import datos
    from storage import r2_uploader
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: None)
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {
        "id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "regla": "Idéntico.", "categoria": "producto",
        "referencias": ["/tmp/e/1.jpg"], "imagenes": ["1.jpg"]})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: f"https://r2/{key}")
    monkeypatch.setattr(proyectos, "preferencias_flowplus", lambda c: {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)                      # 2 videos, 1 imagen
    iv = datos.crear_idea("acme", cid, "video", "Amanecer", "rodea el espejo", sonido="pájaros", gancho="Luz", duracion_s=8, estado_idea="aprobada")
    ii = datos.crear_idea("acme", cid, "imagen", "Marco", "primer plano")
    return dict(app, sid=sid, cid=cid, iv=iv, ii=ii)


def test_pagina_de_ideas_y_acciones(con_ideas):
    from sprints import datos
    c, sid, cid, iv, ii = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    r = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas")
    assert r.status_code == 200 and b"Amanecer" in r.data and b"Marco" in r.data and "1 de 2 videos".encode() in r.data
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer", data={})
    assert con_ideas["encolados"][-1]["tipo"] == "sprint_proponer_ideas" and con_ideas["encolados"][-1]["payload"]["n_videos"] is None
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/proponer", data={"mas": "3"})
    assert con_ideas["encolados"][-1]["payload"] == {"cliente": "acme", "campana_id": cid, "n_videos": 3, "n_imagenes": 0, "reemplaza": None}
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}", json={"titulo": "Marco cálido", "escena": "primer plano con luz", "gancho": "Detalle"})
    assert r.get_json()["ok"] and datos.idea("acme", ii)["titulo"] == "Marco cálido"
    c.post(f"/cliente/acme/sprints/ideas/{ii}/aprobar")
    assert datos.idea("acme", ii)["estado_idea"] == "aprobada"
    c.post(f"/cliente/acme/sprints/ideas/{ii}/otra")
    assert con_ideas["encolados"][-1]["payload"]["reemplaza"] == ii and datos.idea("acme", ii)["estado_idea"] == "descartada"
    i3 = datos.crear_idea("acme", cid, "video", "Tercera", "x")
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas/aprobar_todas")
    assert datos.idea("acme", i3)["estado_idea"] == "aprobada"
    c.post(f"/cliente/acme/sprints/ideas/{i3}/descartar")
    assert datos.idea("acme", i3)["estado_idea"] == "descartada"
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999/ideas").status_code == 404
    assert c.post("/cliente/acme/sprints/ideas/999/aprobar").status_code == 404


def test_estimar_y_lanzar_lote(con_ideas, monkeypatch):
    import flowplus_lanzar
    from sprints import datos
    c, sid, cid, iv = con_ideas["c"], con_ideas["sid"], con_ideas["cid"], con_ideas["iv"]
    j = c.get(f"/cliente/acme/sprints/{sid}/lote/estimar?campana_id={cid}").get_json()
    assert j["videos"] == 1 and j["imagenes"] == 0 and j["usd"] > 0 and "USD" in j["texto"] and j["modelo_video"] == "wan3"
    j2 = c.get(f"/cliente/acme/sprints/{sid}/lote/estimar?modelo_video=kling_o3_pro").get_json()
    assert j2["modelo_video"] == "kling_o3_pro" and j2["usd"] > j["usd"]
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cl, cf, e, prioridad=5: lanzados.append((cf, prioridad)) or True)
    r = c.post(f"/cliente/acme/sprints/{sid}/lote", data={"campana_id": cid, "modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/sprints/{sid}")
    assert len(lanzados) == 1 and lanzados[0][1] == 3
    i = datos.idea("acme", iv)
    assert i["cf_id"] == lanzados[0][0]
    j = c.get(f"/cliente/acme/sprints/{sid}/progreso").get_json()
    assert j["lote"]["planeadas"] == 3 and j["lote"]["encoladas"] + j["lote"]["generando"] == 1 and j["campanas"][0]["lote"]["planeadas"] == 3
    import creative_flow
    creative_flow.actualizar("acme", i["cf_id"], estado="error", error="x")
    c.post(f"/cliente/acme/sprints/ideas/{iv}/reintentar")
    assert lanzados[-1][0] == i["cf_id"] and len(lanzados) == 2
    creative_flow.actualizar("acme", i["cf_id"], estado="video_listo", video_url="https://r2/v.mp4")
    c.post(f"/cliente/acme/sprints/ideas/{iv}/regenerar")
    assert len(lanzados) == 3 and datos.idea("acme", iv)["cf_id"] == lanzados[-1][0]
    r = c.get("/cliente/acme")
    assert "Sprint · Campaña 1".encode() in r.data      # distintivo en la tarjeta de Crear
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: FAIL (404 en las rutas nuevas).

- [ ] **Step 3: `sprints/rutas.py`** — imports: `from providers import flowplus_modelos` ya está; agregar `from sprints import archivos, calendario, datos, estado, ideas, produccion, progreso`. Reemplazar `progreso_json` por:

```python
@bp.get("/<int:sid>/progreso")
def progreso_json(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    lote = produccion.progreso(cliente, sid)
    por_campana = {c["id"]: c for c in lote["campanas"]}
    return jsonify({"estado": sp["estado"], "sprint": progreso.progreso_sprint(sp["campanas"]), "lote": lote["sprint"],
                    "campanas": [{"id": c["id"], "estado": c["estado"], **progreso.progreso_campana(c),
                                  "lote": por_campana.get(c["id"], {})} for c in sp["campanas"]]})
```

Al final del archivo:

```python
# -------------------------------------------------------------- ideas ---

def _idea_o_404(cliente, cp_id, sid=None):
    i = datos.idea(cliente, cp_id)
    if not i or (sid is not None and i["sprint_id"] != sid):
        abort(404)
    return i


def _contexto_lote(cliente):
    mv, mi = produccion.modelos(cliente)
    return {"modelos_video": flowplus_modelos.VIDEO, "modelos_imagen": flowplus_modelos.IMAGEN,
            "modelo_video_defecto": mv, "modelo_imagen_defecto": mi}


@bp.get("/<int:sid>/campanas/<int:cid>/ideas")
def campana_ideas(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = _campana_o_404(cliente, sid, cid)
    refs = {r["id"]: r for r in datos.referencias(cliente, cid)}
    lista = datos.ideas(cliente, cid)
    vivas = [i for i in lista if i["estado_idea"] != "descartada"]
    faltan_v, faltan_i = ideas.faltantes(c)
    conteo = {"videos_aprobados": sum(1 for i in vivas if i["tipo"] == "video" and i["estado_idea"] == "aprobada"),
              "imagenes_aprobadas": sum(1 for i in vivas if i["tipo"] == "imagen" and i["estado_idea"] == "aprobada"),
              "faltan_videos": faltan_v, "faltan_imagenes": faltan_i,
              "pendientes_lote": sum(1 for i in vivas if i["estado_idea"] == "aprobada" and not i["cf_id"])}
    job = tareas_sprints.job_id_ideas(cliente, cid)
    return render_template("campana_ideas.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, campana=c, ideas=lista, referencias_por_id=refs, conteo=conteo,
                           enfoques=flowplus_prompt_enfoques(), trabajo_ideas={"job_id": job} if trabajos.en_curso(job) else None,
                           **_contexto_lote(cliente))


def flowplus_prompt_enfoques():
    import flowplus_prompt
    return {k: v["nombre"] for k, v in flowplus_prompt.ENFOQUES.items()}


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
        flash(str(e), "error")
        return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))
    if tareas_sprints.encolar_ideas(cliente, cid, n_videos=n_v, n_imagenes=n_i):
        flash("Claude está proponiendo ideas; aparecerán aquí en unos segundos.", "ok")
    else:
        flash("Ya hay una propuesta de ideas en curso para esta campaña.", "error")
    return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))


@bp.post("/<int:sid>/campanas/<int:cid>/ideas/aprobar_todas")
def ideas_aprobar_todas(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    n = 0
    for i in datos.ideas(cliente, cid, incluir_descartadas=False):
        if i["estado_idea"] == "propuesta":
            datos.actualizar_idea(cliente, i["id"], estado_idea="aprobada")
            n += 1
    estado.recalcular(cliente, sid)
    flash(f"{n} idea(s) aprobada(s).", "ok")
    return redirect(url_for("sprints.campana_ideas", cliente=cliente, sid=sid, cid=cid))


def _volver_ideas(i):
    return redirect(url_for("sprints.campana_ideas", cliente=i["cliente"], sid=i["sprint_id"], cid=i["campana_id"]))


@bp.post("/ideas/<int:cp_id>")
def idea_editar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": "El cuerpo debe ser un objeto JSON."}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {k: fuente.get(k) for k in ("titulo", "escena", "sonido", "gancho") if k in fuente}
    if any(v is not None and not isinstance(v, str) for v in campos.values()):
        if es_json:
            return jsonify({"ok": False, "error": "Formato inválido."}), 400
        flash("Formato inválido.", "error")
        return _volver_ideas(i)
    try:
        if "titulo" in campos and not (campos["titulo"] or "").strip():
            raise datos.ErrorDatos("Una idea necesita título.")
        if "escena" in campos and not (campos["escena"] or "").strip():
            raise datos.ErrorDatos("Una idea necesita escena.")
        datos.actualizar_idea(cliente, cp_id, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver_ideas(i)
    if es_json:
        return jsonify({"ok": True})
    flash("Idea guardada.", "ok")
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/aprobar")
def idea_aprobar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    datos.actualizar_idea(cliente, cp_id, estado_idea="aprobada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/descartar")
def idea_descartar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    datos.actualizar_idea(cliente, cp_id, estado_idea="descartada")
    estado.recalcular(cliente, i["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver_ideas(i)


@bp.post("/ideas/<int:cp_id>/otra")
def idea_otra(cliente, cp_id):
    """Descarta esta idea y pide otra del mismo tipo (una sola)."""
    i = _idea_o_404(cliente, cp_id)
    if i.get("cf_id"):
        flash("Esa idea ya tiene una pieza generada; usa Regenerar desde la revisión.", "error")
        return _volver_ideas(i)
    datos.actualizar_idea(cliente, cp_id, estado_idea="descartada")
    if tareas_sprints.encolar_ideas(cliente, i["campana_id"], reemplaza=cp_id):
        flash("Pidiendo otra idea en su lugar.", "ok")
    else:
        flash("Ya hay una propuesta de ideas en curso para esta campaña.", "error")
    estado.recalcular(cliente, i["sprint_id"])
    return _volver_ideas(i)


# --------------------------------------------------------------- lote ---

@bp.get("/<int:sid>/lote/estimar")
def lote_estimar(cliente, sid):
    _sprint_o_404(cliente, sid)
    cid = request.args.get("campana_id", type=int)
    try:
        return jsonify(produccion.estimar(cliente, sid, campana_id=cid, modelo_video=request.args.get("modelo_video"),
                                          modelo_imagen=request.args.get("modelo_imagen")))
    except datos.ErrorDatos as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.post("/<int:sid>/lote")
def lote(cliente, sid):
    """Puerta de gasto: el modal ya mostró el costo; aquí se encola."""
    _sprint_o_404(cliente, sid)
    cid = request.form.get("campana_id", type=int)
    try:
        r = produccion.lanzar_lote(cliente, sid, campana_id=cid, modelo_video=request.form.get("modelo_video"),
                                   modelo_imagen=request.form.get("modelo_imagen"))
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, sid)
    if r["encoladas"]:
        flash(f"Lote encolado: {r['encoladas']} pieza(s), USD {r['usd']:.2f} estimado. Te avisamos por correo al terminar si está configurado.", "ok")
    else:
        flash("No había ideas aprobadas sin generar." if not r["omitidas"] else "Esas piezas ya se estaban generando.", "warn")
    return _volver(cliente, sid)


@bp.post("/ideas/<int:cp_id>/reintentar")
def pieza_reintentar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        ok = produccion.reintentar(cliente, cp_id)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    flash("Reintentando la pieza." if ok else "Esa pieza no está en error o ya se está generando.", "ok" if ok else "warn")
    return _volver(cliente, i["sprint_id"])


@bp.post("/ideas/<int:cp_id>/regenerar")
def pieza_regenerar(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    try:
        produccion.regenerar(cliente, cp_id)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, i["sprint_id"])
    flash("Regenerando la pieza (sesión nueva, misma idea).", "ok")
    destino = request.form.get("volver")
    if destino == "revision":
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    return _volver(cliente, i["sprint_id"])
```

Nota: `sprints.revision` (Task 9) aún no existe; el `if destino == "revision"` solo se ejecuta cuando el formulario manda `volver=revision`, que agrega la Task 9. Si `url_for` fallara en pruebas antes de la Task 9, no se ejercita esa rama.

Y en `ver` (detalle), agregar al `render_template("sprint_detalle.html", ...)` los kwargs `**_contexto_lote(cliente)` y `lote=produccion.progreso(cliente, sid)["sprint"]`.

- [ ] **Step 4: `templates/_sprint_lote_modal.html`**

```jinja
{# Puerta de costo del lote (spec §2.2). Se incluye en sprint_detalle.html y en
   campana_ideas.html. `abrirLote(campanaId)` pide el estimado, lo muestra y
   habilita el botón; nada se encola sin este clic. Contexto: sprint,
   modelos_video, modelos_imagen, modelo_video_defecto, modelo_imagen_defecto. #}
<dialog id="lote-modal" class="modal-caja sprint-lote-modal">
  <form method="post" action="{{ url_for('sprints.lote', cliente=cliente, sid=sprint.id) }}" id="form-lote">
    <h3>Generar lote</h3>
    <input type="hidden" name="campana_id" id="lote-campana" value="">
    <div class="fe-opciones">
      <label>Modelo de video
        <select name="modelo_video" id="lote-modelo-video">
          {% for k, m in modelos_video.items() %}<option value="{{ k }}" {% if k == modelo_video_defecto %}selected{% endif %}>{{ m.nombre }} (USD {{ '%.3f' % m.usd_por_segundo }}/s)</option>{% endfor %}
        </select>
      </label>
      <label>Modelo de imagen
        <select name="modelo_imagen" id="lote-modelo-imagen">
          {% for k, m in modelos_imagen.items() %}<option value="{{ k }}" {% if k == modelo_imagen_defecto %}selected{% endif %}>{{ m.nombre }}</option>{% endfor %}
        </select>
      </label>
    </div>
    <p class="sprint-lote-estimado" id="lote-estimado">Calculando el costo…</p>
    <p class="vacio">Se crea una sesión de Crear por idea aprobada. Ninguna se reintenta sola si falla.</p>
    <div class="modal-acciones">
      <button type="button" class="btn-sm" onclick="document.getElementById('lote-modal').close()">Cancelar</button>
      <button type="submit" class="btn-generar btn-sm" id="lote-confirmar" disabled>Generar</button>
    </div>
  </form>
</dialog>
<script>
  function abrirLote(campanaId) {
    var modal = document.getElementById('lote-modal');
    document.getElementById('lote-campana').value = campanaId || '';
    modal.showModal();
    estimarLote();
  }
  function estimarLote() {
    var cid = document.getElementById('lote-campana').value;
    var mv = document.getElementById('lote-modelo-video').value, mi = document.getElementById('lote-modelo-imagen').value;
    var texto = document.getElementById('lote-estimado'), btn = document.getElementById('lote-confirmar');
    btn.disabled = true; texto.textContent = 'Calculando el costo…';
    var url = {{ url_for('sprints.lote_estimar', cliente=cliente, sid=sprint.id) | tojson }} + '?modelo_video=' + encodeURIComponent(mv) + '&modelo_imagen=' + encodeURIComponent(mi) + (cid ? '&campana_id=' + encodeURIComponent(cid) : '');
    fetch(url, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) { return r.json(); }).then(function (j) {
      if (j.error) { texto.textContent = j.error; return; }
      texto.textContent = j.texto;
      var n = j.videos + j.imagenes;
      btn.textContent = n ? 'Generar ' + n + ' pieza(s) — USD ' + j.usd.toFixed(2) : 'Nada que generar';
      btn.disabled = !n;
    }).catch(function () { texto.textContent = 'No se pudo calcular el costo.'; });
  }
  document.getElementById('lote-modelo-video').addEventListener('change', estimarLote);
  document.getElementById('lote-modelo-imagen').addEventListener('change', estimarLote);
</script>
```

- [ ] **Step 5: `templates/campana_ideas.html`**

```jinja
{% extends "base.html" %}
{% from "_sprint_macros.html" import chip_estado %}
{% block title %}Ideas · {{ sprint.nombre }}{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}

<div class="pagina-cabecera sprint-cabecera">
  <div>
    <h1>Ideas de la campaña {{ campana.orden + 1 }}</h1>
    <p class="vacio">{{ campana.persona_nombre }} · {{ campana.catalogo_id }} · {{ campana.temporada_nombre }} · {{ chip_estado(campana.estado) }}</p>
  </div>
</div>

<section class="sprint-refs-progreso">
  <strong>{{ conteo.videos_aprobados }} de {{ campana.n_videos }} videos · {{ conteo.imagenes_aprobadas }} de {{ campana.n_imagenes }} imágenes aprobadas</strong>
  <p class="vacio">Claude propone ideas con la persona, el producto, la temporada, tus referencias y la guía de marca. Aprueba las que sirvan; solo esas se generan, y solo cuando pulses «Generar lote» con el costo a la vista.</p>
</section>

<div class="acciones">
  <form method="post" action="{{ url_for('sprints.ideas_proponer', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
    <button type="submit" class="btn-generar btn-sm" {% if trabajo_ideas or (conteo.faltan_videos + conteo.faltan_imagenes) == 0 %}disabled{% endif %}>
      Proponer las que faltan ({{ conteo.faltan_videos }} videos, {{ conteo.faltan_imagenes }} imágenes)
    </button>
  </form>
  <form method="post" action="{{ url_for('sprints.ideas_proponer', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
    <input type="hidden" name="mas" value="3"><button type="submit" class="btn-sm" {% if trabajo_ideas %}disabled{% endif %}>Proponer 3 videos más</button>
  </form>
  <form method="post" action="{{ url_for('sprints.ideas_proponer', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
    <input type="hidden" name="mas" value="3"><input type="hidden" name="tipo" value="imagen"><button type="submit" class="btn-sm" {% if trabajo_ideas %}disabled{% endif %}>Proponer 3 imágenes más</button>
  </form>
  <form method="post" action="{{ url_for('sprints.ideas_aprobar_todas', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
    <button type="submit" class="btn-sm">Aprobar todas las propuestas</button>
  </form>
  {% if conteo.pendientes_lote %}
  <button type="button" class="btn-generar btn-sm" onclick="abrirLote({{ campana.id }})">Generar lote de esta campaña ({{ conteo.pendientes_lote }})</button>
  {% endif %}
  {% if trabajo_ideas %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_ideas.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <script>iniciarPolling({{ trabajo_ideas.job_id | tojson }}, {{ ("trabajo-" ~ trabajo_ideas.job_id) | tojson }});</script>
  {% endif %}
</div>

<div class="sprint-ideas">
  {% for i in ideas %}
  <article class="swap-card sprint-idea sprint-idea-{{ i.estado_idea }}" data-url="{{ url_for('sprints.idea_editar', cliente=cliente, cp_id=i.id) }}">
    <header class="sprint-idea-cab">
      <span class="tag-estado">{{ i.tipo }}</span>
      <input class="sprint-idea-titulo" name="titulo" value="{{ i.titulo }}" {% if i.cf_id %}readonly{% endif %}>
      <span class="tag-estado estado-sprint estado-sprint-{{ 'ideas_aprobadas' if i.estado_idea == 'aprobada' else ('completada' if i.cf_id else 'planeada') }}">{{ i.estado_idea }}{% if i.cf_id %} · generada{% endif %}</span>
      {% if i.enfoque %}<span class="sprint-chip">{{ enfoques.get(i.enfoque, i.enfoque) }}</span>{% endif %}
      {% if i.duracion_s %}<small class="vacio">{{ i.duracion_s | int }} s</small>{% endif %}
      <span class="sprint-guardado" hidden>Guardado</span>
    </header>
    <textarea name="escena" rows="3" {% if i.cf_id %}readonly{% endif %}>{{ i.escena }}</textarea>
    <div class="fe-opciones">
      {% if i.tipo == "video" %}<label>Sonido <input name="sonido" value="{{ i.sonido or '' }}" {% if i.cf_id %}readonly{% endif %}></label>{% endif %}
      <label>Gancho <input name="gancho" value="{{ i.gancho or '' }}" {% if i.cf_id %}readonly{% endif %}></label>
      {% if i.plataformas %}<small class="vacio">{{ i.plataformas | join(', ') }}</small>{% endif %}
    </div>
    {% if i.referencias_ids %}
    <div class="sprint-idea-refs">
      {% for rid in i.referencias_ids %}{% set r = referencias_por_id.get(rid) %}{% if r %}<img class="sprint-mini" src="{{ r.frame_url or r.url }}" alt="" title="{{ r.titulo }}">{% endif %}{% endfor %}
    </div>
    {% endif %}
    <div class="sprint-idea-acciones">
      {% if not i.cf_id %}
        {% if i.estado_idea != "aprobada" %}
        <form method="post" action="{{ url_for('sprints.idea_aprobar', cliente=cliente, cp_id=i.id) }}" class="inline"><button type="submit" class="btn-generar btn-xs">Aprobar</button></form>
        {% endif %}
        {% if i.estado_idea != "descartada" %}
        <form method="post" action="{{ url_for('sprints.idea_otra', cliente=cliente, cp_id=i.id) }}" class="inline"><button type="submit" class="btn-xs">Otra idea</button></form>
        <form method="post" action="{{ url_for('sprints.idea_descartar', cliente=cliente, cp_id=i.id) }}" class="inline"><button type="submit" class="btn-xs btn-peligro">Descartar</button></form>
        {% endif %}
      {% else %}
        <small class="vacio">Pieza {{ i.estado or 'en cola' }}{% if i.revision != 'pendiente' %} · {{ i.revision }}{% endif %}</small>
      {% endif %}
    </div>
  </article>
  {% else %}
  <p class="vacio">Todavía no hay ideas. Pulsa «Proponer las que faltan».</p>
  {% endfor %}
</div>

{% include "_sprint_lote_modal.html" %}

<script>
  (function () {
    document.querySelectorAll('.sprint-idea').forEach(function (card) {
      var t = null;
      function guardar() {
        var cuerpo = {};
        card.querySelectorAll('input[name], textarea[name]').forEach(function (el) { if (!el.readOnly) cuerpo[el.name] = el.value; });
        fetch(card.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'}, body: JSON.stringify(cuerpo)})
          .then(function (r) { return r.json(); })
          .then(function (j) { if (!j.ok) { alert(j.error); return; } var ok = card.querySelector('.sprint-guardado'); ok.hidden = false; setTimeout(function () { ok.hidden = true; }, 1500); })
          .catch(function () {});
      }
      card.querySelectorAll('input[name], textarea[name]').forEach(function (el) {
        if (el.readOnly) return;
        el.addEventListener('input', function () { el.dataset.sucio = '1'; clearTimeout(t); t = setTimeout(guardar, 800); });
        el.addEventListener('blur', function () { delete el.dataset.sucio; });
      });
    });
  })();
</script>
{% endblock %}
```

- [ ] **Step 6: `templates/sprint_detalle.html`**

Reemplazar el bloque `<div class="sprint-campana-acciones"> … </div>` de cada campaña por:

```jinja
      {% set vivas = c.ideas | rejectattr('estado_idea', 'equalto', 'descartada') | list %}
      {% set aprobadas = vivas | selectattr('estado_idea', 'equalto', 'aprobada') | list %}
      {% set pendientes_lote = aprobadas | rejectattr('cf_id') | list %}
      <div class="sprint-campana-acciones">
        <a class="btn-sm" href="{{ url_for('sprints.campana_ver', cliente=cliente, sid=sprint.id, cid=c.id) }}">
          {% if c.referencias_total == 0 %}Subir referencias{% else %}Referencias ({{ c.referencias_listas }}/{{ c.referencias_objetivo }}){% endif %}
        </a>
        <a class="btn-sm {% if c.referencias_total and not aprobadas %}btn-generar{% endif %}" href="{{ url_for('sprints.campana_ideas', cliente=cliente, sid=sprint.id, cid=c.id) }}">
          Ideas ({{ aprobadas | length }}/{{ c.n_videos + c.n_imagenes }})
        </a>
        {% if pendientes_lote %}
        <button type="button" class="btn-generar btn-sm" onclick="abrirLote({{ c.id }})">Generar lote ({{ pendientes_lote | length }})</button>
        {% endif %}
        {% if c.piezas %}
        <a class="btn-sm" href="{{ url_for('sprints.revision', cliente=cliente, sid=sprint.id) }}#campana-{{ c.id }}">Revisar ({{ c.piezas_aprobadas }}/{{ c.piezas | length }})</a>
        {% endif %}
        <form method="post" action="{{ url_for('sprints.campana_eliminar', cliente=cliente, sid=sprint.id, cid=c.id) }}" class="inline"
              onsubmit="return confirm('¿Eliminar esta campaña y sus referencias?');">
          <button type="submit" class="btn-xs btn-peligro">Eliminar</button>
        </form>
      </div>
```

(Como `sprints.revision` llega en la Task 9, en esta tarea el enlace "Revisar" se deja envuelto en `{% if c.piezas and false %}`… NO: para que el detalle renderice ya, agregar en la Task 8 una ruta mínima `revision` que redirija al detalle, que la Task 9 reemplaza:

```python
@bp.get("/<int:sid>/revision")
def revision(cliente, sid):
    _sprint_o_404(cliente, sid)
    return _volver(cliente, sid)   # la Task 9 renderiza sprint_revision.html
```
)

En el bloque `sprint-acciones` de la cabecera, agregar antes del formulario de archivar:

```jinja
  {% set pendientes_sprint = sprint.campanas | map(attribute='ideas') | sum(start=[]) | rejectattr('estado_idea', 'equalto', 'descartada') | selectattr('estado_idea', 'equalto', 'aprobada') | rejectattr('cf_id') | list %}
  {% if pendientes_sprint %}
  <button type="button" class="btn-generar btn-sm" onclick="abrirLote('')">Generar lote del sprint ({{ pendientes_sprint | length }})</button>
  {% endif %}
  {% if lote and (lote.listas or lote.error or lote.generando or lote.encoladas) %}
  <a class="btn-sm" href="{{ url_for('sprints.revision', cliente=cliente, sid=sprint.id) }}">Revisar ({{ lote.aprobadas }}/{{ lote.listas }} listas)</a>
  {% endif %}
```

Debajo de la cabecera (antes de `<h2>Campañas</h2>`), el resumen del lote:

```jinja
{% if lote and lote.planeadas %}
<p class="vacio sprint-lote-resumen" id="sprint-lote-resumen">
  {{ lote.listas }} listas · {{ lote.generando }} generando · {{ lote.encoladas }} en cola · {{ lote.error }} con error · {{ lote.aprobadas }} aprobadas · USD {{ '%.2f' % lote.costo_usd }} gastado
</p>
{% endif %}
```

Incluir el modal antes del `<script>` final: `{% include "_sprint_lote_modal.html" %}`.

En el script del poller, reemplazar el cuerpo del `.then(function (j) {...})` por:

```javascript
            document.getElementById('sprint-progreso-texto').textContent = j.sprint.texto;
            var res = document.getElementById('sprint-lote-resumen');
            if (res && j.lote) res.textContent = j.lote.listas + ' listas · ' + j.lote.generando + ' generando · ' + j.lote.encoladas + ' en cola · ' + j.lote.error + ' con error · ' + j.lote.aprobadas + ' aprobadas · USD ' + j.lote.costo_usd.toFixed(2) + ' gastado';
            j.campanas.forEach(function (c) {
              var caja = document.querySelector('.sprint-campana-progreso[data-cid="' + c.id + '"]');
              if (!caja) return;
              caja.querySelector('.sprint-barra-fill').style.width = c.porcentaje + '%';
              caja.querySelector('span').textContent = c.texto;
            });
            if (j.estado !== 'generando') location.reload();
```

- [ ] **Step 7: `templates/_tab_creativeflowplus.html`** — después de la línea `<strong>{{ item.enfoque_nombre or ("Con persona" if item.con_persona else "Solo producto") }}</strong>` dentro de `.generado-pie`, agregar:

```jinja
        {% if item.sprint %}<a class="generado-badge generado-sprint" href="{{ url_for('sprints.campana_ideas', cliente=cliente, sid=item.sprint.sprint_id, cid=item.sprint.campana_id) }}" title="{{ item.sprint.sprint_nombre }}">Sprint · Campaña {{ item.sprint.campana_n }}</a>{% endif %}
```

- [ ] **Step 8: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py tests/test_rutas_experimentos.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
python3 -m py_compile sprints/rutas.py
/opt/homebrew/bin/git add sprints/rutas.py templates/campana_ideas.html templates/_sprint_lote_modal.html templates/sprint_detalle.html templates/_tab_creativeflowplus.html tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: pantalla de ideas, puerta de costo del lote, progreso del lote en el tablero y distintivo en Crear

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 9: Bandeja de revisión, cierre y entrega (rutas, plantillas, CSS)

**Files:**
- Modify: `sprints/rutas.py` (reemplazar el esqueleto `revision`; agregar rutas), `static/style.css` (bloque `/* Sprints — producción */` al final)
- Create: `templates/sprint_revision.html`, `templates/sprint_entrega.html`
- Test: `tests/test_rutas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `revision.aprobar/rechazar/aprobar_pasaron_qa/resumen/cerrar/reabrir`, `entrega.enlaces`, `tareas_sprints.encolar_zip/job_id_zip`, `produccion.modelos`, `flowplus_modelos.estimate_video/estimate_imagen`.
- Produces endpoints: `sprints.revision` (GET `/<sid>/revision`), `sprints.pieza_revision` (POST `/ideas/<cp_id>/revision`, `accion=aprobar|rechazar`, `motivo`; JSON o form), `sprints.revision_aprobar_qa` (POST `/<sid>/revision/aprobar_qa`), `sprints.cerrar` (POST `/<sid>/cerrar`), `sprints.reabrir` (POST `/<sid>/reabrir`), `sprints.entrega` (GET `/<sid>/entrega`), `sprints.entrega_zip` (POST `/<sid>/entrega/zip`).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_rutas_sprints.py`)

```python
def _con_piezas(con_ideas, monkeypatch, tmp_path):
    import creative_flow
    import estado as estado_videos
    from sprints import datos
    monkeypatch.setattr(estado_videos, "_path", lambda c: str(tmp_path / f"{c}_videos.json"))
    sid, cid, iv, ii = con_ideas["sid"], con_ideas["cid"], con_ideas["iv"], con_ideas["ii"]
    datos.actualizar_idea("acme", ii, estado_idea="aprobada")
    cfs = {}
    for cp, tipo, est, qa in ((iv, "video", "video_listo", {"veredicto": "pasa", "score": 90, "checks": {"formato": {"ok": True, "nota": "9:16"}}}),
                              (ii, "imagen", "video_listo", {"veredicto": "revisar", "score": 55, "checks": {}})):
        cf = creative_flow.crear("acme", [], ["E"], [], "x", 8, "", "A")
        creative_flow.actualizar("acme", cf, tipo=tipo, estado=est, video_url=f"https://r2/{cp}.{'mp4' if tipo == 'video' else 'png'}", usd=0.4)
        datos.actualizar_idea("acme", cp, cf_id=cf, qa=qa)
        cfs[cp] = cf
    return sid, cid, iv, ii, cfs


def test_revision_pagina_y_acciones(con_ideas, monkeypatch, tmp_path):
    from sprints import datos
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    r = c.get(f"/cliente/acme/sprints/{sid}/revision")
    assert r.status_code == 200 and b"Amanecer" in r.data and b"Marco" in r.data and b"90" in r.data and "Aprobar todas las que pasaron QA".encode() in r.data
    r = c.post(f"/cliente/acme/sprints/ideas/{iv}/revision", json={"accion": "aprobar"})
    assert r.get_json()["ok"] and r.get_json()["revision"] == "aprobada"
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "rechazar", "motivo": ""})
    assert r.status_code == 400 and not r.get_json()["ok"]
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "rechazar", "motivo": "encuadre"})
    assert r.get_json()["ok"] and datos.idea("acme", ii)["revision_motivo"] == "encuadre"
    r = c.post(f"/cliente/acme/sprints/ideas/{ii}/revision", json={"accion": "volar"})
    assert r.status_code == 400
    datos.actualizar_idea("acme", iv, revision="pendiente")
    c.post(f"/cliente/acme/sprints/{sid}/revision/aprobar_qa")
    assert datos.idea("acme", iv)["revision"] == "aprobada"


def test_cerrar_reabrir_y_entrega(con_ideas, monkeypatch, tmp_path):
    from sprints import datos, revision
    sid, cid, iv, ii, cfs = _con_piezas(con_ideas, monkeypatch, tmp_path)
    c = con_ideas["c"]
    # La campaña planea 3 piezas y solo 2 tienen sesión: el sprint sigue en "generando"? No: no hay piezas pendientes/generando,
    # y las dos terminaron → la campaña está en revisión (estado_campana mira las piezas existentes).
    r = c.post(f"/cliente/acme/sprints/{sid}/cerrar")
    assert r.status_code == 302 and datos.sprint("acme", sid)["estado"] in ("completado", "revision")
    if datos.sprint("acme", sid)["estado"] != "completado":
        revision.aprobar("acme", iv)
        c.post(f"/cliente/acme/sprints/{sid}/cerrar")
    assert datos.sprint("acme", sid)["estado"] == "completado"
    revision.aprobar("acme", iv)
    r = c.get(f"/cliente/acme/sprints/{sid}/entrega")
    assert r.status_code == 200 and b"https://r2/" in r.data and "Descargar aprobadas".encode() in r.data
    c.post(f"/cliente/acme/sprints/{sid}/entrega/zip")
    assert con_ideas["encolados"][-1]["tipo"] == "sprint_empaquetar" and con_ideas["encolados"][-1]["payload"]["sprint_id"] == sid
    c.post(f"/cliente/acme/sprints/{sid}/reabrir")
    assert datos.sprint("acme", sid)["estado"] == "revision"
    assert c.get("/cliente/acme/sprints/999/revision").status_code == 404
    assert c.get("/cliente/acme/sprints/999/entrega").status_code == 404
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: FAIL (esqueleto de `revision` redirige; rutas nuevas 404).

- [ ] **Step 3: `sprints/rutas.py`** — import `from sprints import archivos, calendario, datos, entrega, estado, ideas, produccion, progreso, revision as revision_mod` (el módulo se importa con alias porque hay una ruta llamada `revision`). Reemplazar el esqueleto de `revision` y agregar:

```python
# ----------------------------------------------------------- revisión ---

def _piezas_revision(cliente, sp):
    """Piezas con sesión de todas las campañas, con su costo de regeneración."""
    mv, mi = produccion.modelos(cliente)
    salida = []
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p["tipo"] == "video":
                costo = (flowplus_modelos.estimate_video(mv, produccion._duracion(p)) or {}).get("usd") or 0.0
            else:
                costo = (flowplus_modelos.estimate_imagen(mi, n_referencias=produccion._n_referencias(c)) or {}).get("usd") or 0.0
            salida.append({**p, "campana_n": int(c["orden"]) + 1, "persona_nombre": c["persona_nombre"],
                           "temporada_nombre": c["temporada_nombre"], "catalogo_id": c["catalogo_id"],
                           "costo_regenerar": round(float(costo), 3)})
    return salida


@bp.get("/<int:sid>/revision")
def revision(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    piezas = _piezas_revision(cliente, sp)
    return render_template("sprint_revision.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, piezas=piezas, resumen=revision_mod.resumen(cliente, sid), checks=("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato"))


@bp.post("/ideas/<int:cp_id>/revision")
def pieza_revision(cliente, cp_id):
    i = _idea_o_404(cliente, cp_id)
    cuerpo = request.get_json(silent=True)
    if cuerpo is not None and not isinstance(cuerpo, dict):
        return jsonify({"ok": False, "error": "El cuerpo debe ser un objeto JSON."}), 400
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    accion, motivo = fuente.get("accion"), fuente.get("motivo")
    try:
        if accion == "aprobar":
            ok = revision_mod.aprobar(cliente, cp_id)
        elif accion == "rechazar":
            ok = revision_mod.rechazar(cliente, cp_id, motivo if isinstance(motivo, str) else "")
        else:
            raise datos.ErrorDatos("Acción desconocida.")
        if not ok:
            raise datos.ErrorDatos("Esa pieza todavía no está terminada.")
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))
    nueva = datos.idea(cliente, cp_id)
    if es_json:
        return jsonify({"ok": True, "revision": nueva["revision"], "estado_sprint": (datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}).get("estado")})
    flash("Pieza aprobada." if accion == "aprobar" else "Pieza rechazada.", "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=i["sprint_id"]))


@bp.post("/<int:sid>/revision/aprobar_qa")
def revision_aprobar_qa(cliente, sid):
    _sprint_o_404(cliente, sid)
    n = revision_mod.aprobar_pasaron_qa(cliente, sid)
    flash(f"{n} pieza(s) aprobada(s) por haber pasado el QA.", "ok")
    return redirect(url_for("sprints.revision", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/cerrar")
def cerrar(cliente, sid):
    _sprint_o_404(cliente, sid)
    try:
        r = revision_mod.cerrar(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente, sid)
    flash(f"Sprint cerrado: {r['aprobadas']} aprobadas, {r['rechazadas']} rechazadas, USD {r['costo_usd']:.2f}.", "ok")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))


@bp.post("/<int:sid>/reabrir")
def reabrir(cliente, sid):
    _sprint_o_404(cliente, sid)
    if revision_mod.reabrir(cliente, sid):
        flash("Sprint reabierto a revisión.", "ok")
    else:
        flash("Solo se reabre un sprint completado.", "error")
    return _volver(cliente, sid)


# ------------------------------------------------------------ entrega ---

def entrega_ver(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    job = tareas_sprints.job_id_zip(cliente, sid)
    return render_template("sprint_entrega.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, enlaces=entrega.enlaces(cliente, sid), resumen=revision_mod.resumen(cliente, sid),
                           zip_info=(sp.get("extra") or {}).get("zip"),
                           trabajo_zip={"job_id": job} if trabajos.en_curso(job) else None)


bp.add_url_rule("/<int:sid>/entrega", endpoint="entrega", view_func=entrega_ver)


@bp.post("/<int:sid>/entrega/zip")
def entrega_zip(cliente, sid):
    _sprint_o_404(cliente, sid)
    if not entrega.enlaces(cliente, sid):
        flash("No hay piezas aprobadas que entregar.", "error")
    elif tareas_sprints.encolar_zip(cliente, sid):
        flash("Armando el zip; el enlace aparecerá aquí al terminar.", "ok")
    else:
        flash("Ya se está armando el zip.", "warn")
    return redirect(url_for("sprints.entrega", cliente=cliente, sid=sid))
```

Nota sobre el endpoint `entrega`: la función se llama `entrega_ver` para no pisar el módulo `entrega` importado; se registra SOLO con `bp.add_url_rule(..., endpoint="entrega", view_func=entrega_ver)` (sin decorador), que es el nombre que usan las plantillas (`url_for('sprints.entrega', ...)`).

- [ ] **Step 4: `templates/sprint_revision.html`**

```jinja
{% extends "base.html" %}
{% from "_sprint_macros.html" import chip_estado %}
{% block title %}Revisión · {{ sprint.nombre }}{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}

<div class="pagina-cabecera sprint-cabecera">
  <div>
    <h1>Revisión de {{ sprint.nombre }}</h1>
    <p class="vacio">{{ chip_estado(sprint.estado) }} · {{ resumen.terminadas }} terminadas de {{ resumen.planeadas }} · {{ resumen.aprobadas }} aprobadas · {{ resumen.rechazadas }} rechazadas · {{ resumen.sin_revisar }} sin revisar · {{ resumen.error }} con error · USD {{ '%.2f' % resumen.costo_usd }}</p>
    <p class="vacio">Atajos: <kbd>A</kbd> aprobar · <kbd>R</kbd> rechazar · <kbd>←</kbd> <kbd>→</kbd> moverse. Cada tarjeta muestra el QA: ✓ pasa, ✗ falla; pasa el cursor para leer la nota.</p>
  </div>
</div>

<div class="acciones sprint-acciones">
  <form method="post" action="{{ url_for('sprints.revision_aprobar_qa', cliente=cliente, sid=sprint.id) }}" class="inline">
    <button type="submit" class="btn-generar btn-sm">Aprobar todas las que pasaron QA</button>
  </form>
  {% if sprint.estado == "revision" %}
  <form method="post" action="{{ url_for('sprints.cerrar', cliente=cliente, sid=sprint.id) }}" class="inline"
        onsubmit="return confirm('¿Cerrar el sprint? {{ resumen.aprobadas }} aprobadas, {{ resumen.rechazadas }} rechazadas, {{ resumen.sin_revisar }} sin revisar.');">
    <button type="submit" class="btn-sm">Cerrar sprint</button>
  </form>
  {% endif %}
  {% if sprint.estado == "completado" %}
  <a class="btn-generar btn-sm" href="{{ url_for('sprints.entrega', cliente=cliente, sid=sprint.id) }}">Entrega</a>
  {% endif %}
  <label class="fe-check">Campaña
    <select id="filtro-campana"><option value="">todas</option>{% for c in sprint.campanas %}<option value="{{ c.id }}">{{ c.orden + 1 }} · {{ c.persona_nombre }} · {{ c.temporada_nombre }}</option>{% endfor %}</select>
  </label>
  <label class="fe-check">Tipo <select id="filtro-tipo"><option value="">todos</option><option value="video">video</option><option value="imagen">imagen</option></select></label>
  <label class="fe-check">QA <select id="filtro-qa"><option value="">todos</option><option value="pasa">pasa</option><option value="revisar">revisar</option><option value="falla">falla</option><option value="sin">sin evaluar</option></select></label>
</div>

<div class="sprint-revision-grid" id="revision-grid">
  {% for p in piezas %}
  <article class="swap-card sprint-pieza sprint-pieza-{{ p.revision }}" id="pieza-{{ p.id }}" data-cp="{{ p.id }}" data-campana="{{ p.campana_id }}" data-tipo="{{ p.tipo }}"
           data-qa="{{ (p.qa or {}).get('veredicto', 'sin') }}" data-url="{{ url_for('sprints.pieza_revision', cliente=cliente, cp_id=p.id) }}" tabindex="0">
    <div class="sprint-ref-media">
      {% if p.estado in ("listo", "degradada") and p.url_video %}
        {% if p.tipo == "video" %}<video src="{{ p.url_video }}" {% if p.url_miniatura %}poster="{{ p.url_miniatura }}"{% endif %} controls muted preload="none"></video>
        {% else %}<img src="{{ p.url_video }}" alt="{{ p.titulo or '' }}">{% endif %}
      {% elif p.estado == "error" %}<p class="tag-error sprint-pieza-error">Error: {{ p.pieza_error or 'sin detalle' }}</p>
      {% else %}<p class="vacio sprint-analizando">{{ p.estado or 'en cola' }}…</p>{% endif %}
      <span class="tag-estado sprint-ref-estado sprint-revision-chip">{{ p.revision }}</span>
    </div>
    <div class="sprint-ref-cuerpo">
      <strong>{{ p.titulo }}</strong>
      <small class="vacio">Campaña {{ p.campana_n }} · {{ p.persona_nombre }} · {{ p.temporada_nombre }} · {{ p.tipo }}{% if p.costo_usd %} · USD {{ '%.2f' % p.costo_usd }}{% endif %}</small>
      {% if p.qa %}
      <div class="sprint-qa">
        <span class="sprint-qa-score sprint-qa-{{ p.qa.veredicto }}">{{ p.qa.score }}</span>
        {% for k in checks %}{% set ch = (p.qa.checks or {}).get(k) %}{% if ch %}<span class="qa-check {{ 'ok' if ch.ok else 'mal' }}" title="{{ k | replace('_', ' ') }}: {{ ch.nota }}">{{ '✓' if ch.ok else '✗' }}</span>{% endif %}{% endfor %}
        <small class="vacio">{{ p.qa.veredicto }}</small>
      </div>
      {% elif p.estado in ("listo", "degradada") %}<small class="vacio sprint-analizando">QA pendiente…</small>{% endif %}
      {% if p.revision == "rechazada" and p.revision_motivo %}<small class="tag-error">Motivo: {{ p.revision_motivo }}</small>{% endif %}
      <div class="sprint-ref-acciones">
        {% if p.estado in ("listo", "degradada") %}
        <button type="button" class="btn-generar btn-xs js-aprobar">Aprobar</button>
        <button type="button" class="btn-xs btn-peligro js-rechazar">Rechazar</button>
        <a class="btn-xs" href="{{ url_for('ver_cliente', cliente=cliente, _anchor='creativeflowplus') }}" title="Abrir en Crear (final edition, experimentos)">Final edition</a>
        {% endif %}
        {% if p.estado == "error" %}
        <form method="post" action="{{ url_for('sprints.pieza_reintentar', cliente=cliente, cp_id=p.id) }}" class="inline" onsubmit="return confirm('Reintentar gasta de nuevo (USD {{ p.costo_regenerar }}). ¿Seguir?');"><button type="submit" class="btn-xs">Reintentar (USD {{ p.costo_regenerar }})</button></form>
        {% endif %}
        {% if p.estado in ("listo", "degradada", "error") %}
        <form method="post" action="{{ url_for('sprints.pieza_regenerar', cliente=cliente, cp_id=p.id) }}" class="inline" onsubmit="return confirm('Regenerar crea una pieza nueva con la misma idea (USD {{ p.costo_regenerar }}). ¿Seguir?');">
          <input type="hidden" name="volver" value="revision"><button type="submit" class="btn-xs">Regenerar (USD {{ p.costo_regenerar }})</button>
        </form>
        {% endif %}
      </div>
    </div>
  </article>
  {% else %}
  <p class="vacio">Todavía no hay piezas generadas en este sprint.</p>
  {% endfor %}
</div>

<script>
  (function () {
    var grid = document.getElementById('revision-grid');
    var tarjetas = Array.prototype.slice.call(grid.querySelectorAll('.sprint-pieza'));
    var idx = -1;
    function seleccionar(i) {
      var visibles = tarjetas.filter(function (t) { return !t.hidden; });
      if (!visibles.length) return;
      idx = Math.max(0, Math.min(visibles.length - 1, i));
      tarjetas.forEach(function (t) { t.classList.remove('seleccionada'); });
      visibles[idx].classList.add('seleccionada'); visibles[idx].focus({preventScroll: false});
    }
    function enviar(card, accion, motivo) {
      fetch(card.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'},
                               body: JSON.stringify({accion: accion, motivo: motivo || ''})})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (!j.ok) { alert(j.error); return; }
          card.className = card.className.replace(/sprint-pieza-(pendiente|aprobada|rechazada)/, 'sprint-pieza-' + j.revision);
          card.querySelector('.sprint-revision-chip').textContent = j.revision;
        }).catch(function () {});
    }
    function accionSeleccionada(accion) {
      var card = grid.querySelector('.sprint-pieza.seleccionada');
      if (!card || !card.querySelector('.js-aprobar')) return;
      if (accion === 'rechazar') { var m = prompt('Motivo del rechazo:'); if (!m) return; enviar(card, 'rechazar', m); }
      else enviar(card, 'aprobar');
    }
    tarjetas.forEach(function (card, i) {
      card.addEventListener('focus', function () { tarjetas.forEach(function (t) { t.classList.remove('seleccionada'); }); card.classList.add('seleccionada'); idx = tarjetas.filter(function (t) { return !t.hidden; }).indexOf(card); });
      var a = card.querySelector('.js-aprobar'), r = card.querySelector('.js-rechazar');
      if (a) a.addEventListener('click', function () { enviar(card, 'aprobar'); });
      if (r) r.addEventListener('click', function () { var m = prompt('Motivo del rechazo:'); if (m) enviar(card, 'rechazar', m); });
    });
    document.addEventListener('keydown', function (e) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].indexOf(document.activeElement.tagName) >= 0) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); seleccionar(idx + 1); }
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); seleccionar(idx - 1); }
      else if (e.key === 'a' || e.key === 'A') accionSeleccionada('aprobar');
      else if (e.key === 'r' || e.key === 'R') accionSeleccionada('rechazar');
    });
    function filtrar() {
      var c = document.getElementById('filtro-campana').value, t = document.getElementById('filtro-tipo').value, q = document.getElementById('filtro-qa').value;
      tarjetas.forEach(function (card) {
        card.hidden = (c && card.dataset.campana !== c) || (t && card.dataset.tipo !== t) || (q && card.dataset.qa !== q);
      });
    }
    ['filtro-campana', 'filtro-tipo', 'filtro-qa'].forEach(function (id) { document.getElementById(id).addEventListener('change', filtrar); });
    if (location.hash.indexOf('#campana-') === 0) { document.getElementById('filtro-campana').value = location.hash.replace('#campana-', ''); filtrar(); }
    seleccionar(0);
  })();
</script>
{% endblock %}
```

- [ ] **Step 5: `templates/sprint_entrega.html`**

```jinja
{% extends "base.html" %}
{% from "_sprint_macros.html" import chip_estado %}
{% block title %}Entrega · {{ sprint.nombre }}{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}

<div class="pagina-cabecera sprint-cabecera">
  <div>
    <h1>Entrega de {{ sprint.nombre }}</h1>
    <p class="vacio">{{ chip_estado(sprint.estado) }} · {{ resumen.aprobadas }} aprobadas · {{ resumen.rechazadas }} rechazadas · {{ resumen.sin_revisar }} sin revisar · USD {{ '%.2f' % resumen.costo_usd }} gastado (estimado USD {{ '%.2f' % resumen.costo_estimado_usd }}){% if resumen.dias %} · {{ resumen.dias }} días{% endif %}</p>
  </div>
</div>

<div class="acciones sprint-acciones">
  <button type="button" class="btn-sm" id="copiar-enlaces" {% if not enlaces %}disabled{% endif %}>Copiar enlaces</button>
  <form method="post" action="{{ url_for('sprints.entrega_zip', cliente=cliente, sid=sprint.id) }}" class="inline">
    <button type="submit" class="btn-generar btn-sm" {% if not enlaces or trabajo_zip %}disabled{% endif %}>Descargar aprobadas (zip)</button>
  </form>
  {% if zip_info %}<a class="btn-sm" href="{{ zip_info.url }}">Zip del {{ zip_info.creado_en | replace('T', ' ') }} ({{ zip_info.n }} piezas)</a>{% endif %}
  {% if sprint.estado == "completado" %}
  <form method="post" action="{{ url_for('sprints.reabrir', cliente=cliente, sid=sprint.id) }}" class="inline"><button type="submit" class="btn-sm">Reabrir a revisión</button></form>
  {% endif %}
  {% if trabajo_zip %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_zip.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <script>iniciarPolling({{ trabajo_zip.job_id | tojson }}, {{ ("trabajo-" ~ trabajo_zip.job_id) | tojson }});</script>
  {% endif %}
</div>

<table class="sprint-entrega" id="tabla-entrega">
  <thead><tr><th>Campaña</th><th>Pieza</th><th>Tipo</th><th>Enlace</th></tr></thead>
  <tbody>
    {% for e in enlaces %}
    <tr><td>{{ e.campana_n }} · {{ e.persona }} · {{ e.temporada }}</td><td>{{ e.titulo }}</td><td>{{ e.tipo }}</td><td><a href="{{ e.url }}" class="js-enlace">{{ e.url }}</a></td></tr>
    {% else %}
    <tr><td colspan="4" class="vacio">Sin piezas aprobadas todavía.</td></tr>
    {% endfor %}
  </tbody>
</table>

<script>
  document.getElementById('copiar-enlaces').addEventListener('click', function () {
    var texto = Array.prototype.map.call(document.querySelectorAll('.js-enlace'), function (a) { return a.href; }).join('\n');
    (navigator.clipboard ? navigator.clipboard.writeText(texto) : Promise.reject()).then(function () { alert('Enlaces copiados.'); }).catch(function () { prompt('Copia los enlaces:', texto); });
  });
</script>
{% endblock %}
```

- [ ] **Step 6: CSS** — al final de `static/style.css`:

```css
/* Sprints — producción */
.sprint-ideas { display: grid; gap: .7rem; }
.sprint-idea { padding: .8rem 1rem; display: grid; gap: .5rem; }
.sprint-idea-descartada { opacity: .55; }
.sprint-idea-cab { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
.sprint-idea-titulo { flex: 1; min-width: 12rem; font-weight: 700; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: .2rem .4rem; }
.sprint-idea-titulo:focus { border-color: var(--border); background: var(--panel-2); }
.sprint-idea textarea { width: 100%; }
.sprint-idea-refs { display: flex; gap: .3rem; }
.sprint-idea-acciones { display: flex; gap: .4rem; align-items: center; justify-content: flex-end; }
.sprint-lote-modal { max-width: 34rem; }
.sprint-lote-estimado { font-weight: 700; }
.sprint-lote-resumen { margin: -.4rem 0 1rem; }
.sprint-revision-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: .8rem; }
.sprint-pieza { padding: 0; overflow: hidden; outline: 2px solid transparent; }
.sprint-pieza.seleccionada { outline-color: var(--accent); }
.sprint-pieza-aprobada .sprint-revision-chip { border-color: var(--ok); color: var(--ok); }
.sprint-pieza-rechazada .sprint-revision-chip { border-color: var(--error); color: var(--error); }
.sprint-pieza-error { margin: 1rem; }
.sprint-qa { display: flex; gap: .3rem; align-items: center; }
.sprint-qa-score { font-weight: 700; min-width: 2.2rem; text-align: center; border-radius: 6px; padding: .1rem .3rem; background: var(--panel-2); }
.sprint-qa-pasa { color: var(--ok); }
.sprint-qa-revisar { color: var(--warn); }
.sprint-qa-falla { color: var(--error); }
.qa-check { font-size: .8rem; cursor: help; }
.qa-check.ok { color: var(--ok); }
.qa-check.mal { color: var(--error); }
.sprint-entrega { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: .9rem; }
.sprint-entrega th, .sprint-entrega td { border-bottom: 1px solid var(--border); padding: .45rem .5rem; text-align: left; vertical-align: top; word-break: break-all; }
.generado-sprint { text-decoration: none; margin-left: .4rem; }
kbd { border: 1px solid var(--border); border-radius: 4px; padding: 0 .3rem; font-size: .8em; }
```

- [ ] **Step 7: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile sprints/rutas.py
/opt/homebrew/bin/git add sprints/rutas.py templates/sprint_revision.html templates/sprint_entrega.html static/style.css tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: bandeja de revisión con atajos y QA visible, cierre/reapertura y entrega (enlaces y zip)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Documentación y verificación final

**Files:**
- Modify: `CLAUDE.md` (ampliar la sección "Sprints de contenido")
- Test: suite completa

- [ ] **Step 1: `CLAUDE.md`** — reemplazar la última frase de la sección Sprints ("Nothing in Parte 1 generates images or videos.") por:

```markdown
Parte 2 (producción): `sprints/ideas.py` asks Claude for ideas per campaign
(prompt maestro: persona + producto + temporada + reference analyses + brand
guide + banco de prompts) stored as `campana_pieza` rows; "Generar lote"
(`sprints/produccion.py`) shows the estimated cost first, then creates one
Crear session per approved idea (`creative_flow.crear(..., extra_sprint=)`,
prompt via `flowplus_prompt.armar(..., contexto=)`) and enqueues it through
`flowplus_lanzar.lanzar(..., prioridad=3)` — `tarea.prioridad` makes single
pieces from Crear (5) jump ahead of batches. `campana_pieza.cf_id` joins
`pieza.legado_id`, so progress and states come from the real sessions. The
worker periodic `sprint_qa_pendientes` (5 min) queues `sprint_qa_pieza`
(`sprints/qa.py`: Claude vision + ffprobe → `campana_pieza.qa`, never
generates) and emails when a batch finishes. `sprints/revision.py` approves or
rejects (a rejected piece leaves `estado_videos.json`), closes and reopens the
sprint; `sprints/entrega.py` lists approved links and builds the zip
(`sprint_empaquetar`). Retries and regenerations always go through the cost
gate and `max_intentos=1`.
```

- [ ] **Step 2: Suite completa y compilación**

Run: `venv/bin/python -m pytest -q`
Expected: todo verde.

Run: `for f in db.py cola.py trabajos.py flowplus_lanzar.py dashboard.py flowplus_prompt.py creative_flow.py notificaciones.py worker.py sprints/*.py tareas/sprints.py migrations/versions/0008_tarea_prioridad.py; do python3 -m py_compile "$f" || echo "FALLA $f"; done`
Expected: sin salida. `venv/bin/alembic heads` → `0008 (head)`.

- [ ] **Step 3: Commit**

```bash
/opt/homebrew/bin/git add CLAUDE.md
/opt/homebrew/bin/git commit -m "Docs: sprints de contenido, Parte 2 (producción) en CLAUDE.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Autorrevisión del plan contra el spec (Parte 2)

- §2.1 ideas y prompt maestro (persona, producto, temporada, análisis de referencias, guía de marca, banco de prompts; `sonido`; JSON validado con reintento; tarjetas, aprobar/descartar/otra/3 más/todas; encabezado "N de M") → Tasks 3, 4, 8.
- §2.2 lote (`crear(extra_sprint)`, referencias del producto + campaña + logos, `armar(contexto)` con AUDIENCIA/TEMPORADA y regresión, `flowplus_video|imagen` con `max_intentos=1` y prioridad 3, puerta de costo con modelos cambiables y tiempo estimado, evento, aviso por correo al terminar, `tarea.prioridad` + `reclamar`, progreso agregado cada 5 s, Reintentar/Reemplazar) → Tasks 1, 2, 5, 6 (aviso), 8. "Reemplazar idea" = descartar + "Otra idea" desde la pantalla de ideas (Task 8) y "Regenerar" desde revisión (Task 9).
- §2.3 interrupciones → los estados salen del `JOIN` con `pieza` (Task 3) y `recalcular` corre en `progreso` (Task 5).
- §2.4 QA (periódica 300 s, visión + ffprobe, cinco chequeos, score/veredicto/umbral `extra.qa_umbral`, nunca gasta, "Regenerar (USD X)") → Tasks 6, 9.
- §2.5 revisión (grid, filtros, score con iconos y nota, aprobar/rechazar con motivo/regenerar/final edition, atajos A/R/flechas, "aprobar todas las que pasaron QA", eventos, rechazada fuera de la cola de publicación) → Tasks 7, 9.
- §2.6 cierre y entrega (resumen, `completado`, enlaces, copiar, zip en `salidas/<c>/sprints/`, subida a R2, reabrir) → Tasks 7, 9.
- §2.7 cambios mínimos → Tasks 1, 2, 6 (`PERIODICAS`).
- §2.8 módulos y pruebas → cada tarea trae las suyas; suite completa en Task 10.
- Fuera de esta parte: plantillas de texto y final edition de imágenes (Parte 3); el distintivo en Crear enlaza a la pantalla de ideas de la campaña.
