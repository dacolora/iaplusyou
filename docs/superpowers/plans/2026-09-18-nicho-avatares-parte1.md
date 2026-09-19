# Nicho y avatares — Parte 1 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un proyecto pueda crear un **estudio** de nicho, meterle comentarios reales (texto pegado, CSV o Excel), generar con Claude avatares **núcleo** por deseo y **sub-avatares** con evidencia textual verificada, revisarlos, aprobarlos como **personas** de Sprints (origen `investigada`) y exportarlos en `.md` y en Excel con la plantilla de la hoja "Personas".

**Architecture:** módulo nuevo `nicho/` calcado de `sprints/`: `nicho/datos.py` es el único escritor de tres tablas nuevas (`estudio`, `comentario`, `avatar`, migración `0011`); las fuentes de comentarios entran por un contrato común (`nicho/fuentes/base.py`, registro perezoso como `conectores`); `nicho/avatares.py` hace dos pasadas con Claude (núcleos, luego sub-avatares por núcleo) y verifica cada cita contra el comentario real; la generación corre en el worker (`tareas/nicho.py`, `max_intentos=1`, gasto real anotado con `gastos.registrar_seguro`); el Blueprint `nicho/rutas.py` pone la pestaña **Nicho** y la página del estudio. La Parte 2 (Reddit, YouTube, Apify) solo agrega archivos en `nicho/fuentes/` y una tarea `nicho_recolectar`: nada de esta parte cambia.

**Tech Stack:** Python 3, Flask, SQLAlchemy Core + Alembic (SQLite WAL), `anthropic` (modelo `generador_prompts.MODEL`, hoy `claude-sonnet-5`), `openpyxl`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (todas las secciones salvo §3.3–§3.6 y la tarea `nicho_recolectar` de §8, que son Parte 2: fuentes conectadas y sus llaves).

## Global Constraints

- Nada gasta crédito sin un clic con el costo a la vista: el botón "Generar avatares" muestra `≈ US$` y el número de comentarios; la tarea se encola con `max_intentos=1`; un doble clic no lanza dos veces (`trabajos.encolar` devuelve `False` si el `job_id` ya está vivo).
- `nicho/datos.py` es el ÚNICO escritor de `estudio`, `comentario` y `avatar`; `sprints/datos.py` sigue siendo el único escritor de `persona`.
- Toda lectura-modificación-escritura de `estudio.extra` toma el lock de escritura ANTES de leer (`_bloquear`, semántica `BEGIN IMMEDIATE`, igual que `experimentos._bloquear`).
- Un comentario nunca guarda el nombre del autor. Texto limpio (sin caracteres de control, espacios colapsados) y recortado a 2 000 caracteres; único por `(estudio_id, fuente, fuente_id)`.
- Una cita de evidencia vale solo si es un fragmento literal (sin importar mayúsculas ni espacios múltiples, mínimo 12 caracteres) del comentario que dice; la que no aparece se descarta; un sub-avatar sin citas queda `sin_evidencia=True`, no se borra.
- Regenerar borra los sub-avatares `propuesto`/`descartado` de corridas anteriores y los núcleos que quedan sin ningún `aprobado`; nunca toca un `aprobado`.
- Precios de Claude por millón de tokens, verificados contra la referencia de Anthropic (tabla del 2026-06-24): `claude-sonnet-5` 2.00 / 10.00, `claude-opus-5` 5.00 / 25.00, `claude-haiku-4-5` 1.00 / 5.00. Modelo desconocido → se estima con el más caro de la tabla y se dice "estimado con precio de referencia". El modelo NO se cambia: sigue siendo `generador_prompts.MODEL`.
- Mensajes de error en español, sin llaves ni HTML ajeno (`cola.sin_token` antes de guardar). Copy de la UI en español.
- Suite verde sin red: Claude se sustituye por `nicho.avatares._llamar` falso; `trabajos.encolar` se monkeypatchea en las pruebas de rutas.
- `python3 -m py_compile <archivo>` en cada archivo Python tocado antes de cada commit. Commits pequeños en español, terminados con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `migrations/versions/0011_nicho.py` (crear) | Tablas `estudio`, `comentario`, `avatar` |
| `db.py` (modificar) | Las mismas tres tablas declaradas en `metadata` |
| `sprints/datos.py` (modificar) | `ORIGENES_PERSONA` gana `investigada`; `crear_persona(..., extra=None)` |
| `gastos.py` (modificar) | `TIPOS` gana `avatares` |
| `nicho/__init__.py` (crear) | Paquete |
| `nicho/datos.py` (crear) | Escritor único: estudios, comentarios, avatares, aprobar → persona, `recalcular` |
| `nicho/fuentes/__init__.py` (crear) | Registro por tipo, carga perezosa |
| `nicho/fuentes/base.py` (crear) | Contrato `Fuente`, `normalizar_comentario`, `ErrorFuente`, `hash_texto` |
| `nicho/fuentes/texto.py` (crear) | Texto pegado (`partir_texto`) |
| `nicho/fuentes/archivo.py` (crear) | CSV / Excel (`leer_archivo`, detección de columnas) |
| `nicho/avatares.py` (crear) | Selección, estimado, prompts, parseo, evidencia, `generar` |
| `nicho/exportar.py` (crear) | `.md` y `.xlsx` con la plantilla de la hoja |
| `nicho/rutas.py` (crear) | Blueprint `nicho`, `contexto(cliente)` |
| `tareas/nicho.py` (crear) + `tareas/__init__.py` (modificar) | Tarea `nicho_generar_avatares` |
| `templates/_tab_nicho.html`, `templates/nicho_estudio.html`, `templates/_nicho_nav.html`, `templates/_nicho_comentarios.html`, `templates/_nicho_avatares.html` (crear) | Pestaña y página del estudio |
| `templates/_sidebar.html`, `templates/cliente.html`, `static/style.css`, `dashboard.py` (modificar) | Pestaña Nicho, registro del Blueprint, contexto, estilos |
| `tests/test_nicho_db.py`, `tests/test_nicho_datos.py`, `tests/test_nicho_fuentes.py`, `tests/test_nicho_avatares.py`, `tests/test_nicho_export.py`, `tests/test_tareas_nicho.py`, `tests/test_rutas_nicho.py` (crear) | Pruebas |
| `CLAUDE.md`, `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (modificar) | Docs: párrafo del módulo; el spec pasa la migración a `0011` y la página propia del estudio |

Cómo se corre la suite: `venv/bin/python3 -m pytest -q` (o un archivo: `venv/bin/python3 -m pytest tests/test_nicho_datos.py -q`).

---

### Task 1: Migración 0011, tablas en `db.py`, origen `investigada` y tipo de gasto

**Files:**
- Create: `migrations/versions/0011_nicho.py`
- Modify: `db.py` (después de `sprint_evento`, antes de `def crear_todo`)
- Modify: `sprints/datos.py:33` (`ORIGENES_PERSONA`) y `sprints/datos.py:163-176` (`crear_persona`)
- Modify: `gastos.py:33` (`TIPOS`)
- Test: `tests/test_nicho_db.py`, `tests/test_sprints_datos.py` (una prueba nueva), `tests/test_gastos.py` (una prueba nueva)

**Interfaces:**
- Produces: tablas `db.estudio`, `db.comentario`, `db.avatar` con las columnas del spec §2; `sprints.datos.ORIGENES_PERSONA == ("manual", "sugerida_ia", "investigada")`; `sprints.datos.crear_persona(cliente, nombre, ..., origen="manual", extra=None) -> int`; `gastos.TIPOS` incluye `"avatares"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_db.py`:

```python
import os

import sqlalchemy as sa


def test_migracion_0011_crea_las_tablas(tmp_path, monkeypatch):
    """La migración real (no metadata.create_all) deja las tres tablas y la unicidad."""
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig11.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    insp = sa.inspect(db.engine())
    assert {"estudio", "comentario", "avatar"} <= set(insp.get_table_names())
    unicos = {u["name"] for u in insp.get_unique_constraints("comentario")} | {i["name"] for i in insp.get_indexes("comentario")}
    assert "uq_comentario_fuente" in unicos
    cols = {c["name"] for c in insp.get_columns("avatar")}
    assert {"padre_id", "tipo", "base", "identidad", "soluciones_previas", "conciencia", "evidencia", "sin_evidencia",
            "persona_id", "generacion"} <= cols
    db._reset_para_tests()


def test_crear_todo_incluye_las_tablas(base_temporal):
    insp = sa.inspect(base_temporal.engine())
    assert {"estudio", "comentario", "avatar"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("estudio")} >= {"nombre", "producto", "catalogo_id", "tema", "idioma",
                                                                  "estado", "archivado", "generacion", "extra"}
```

Agregar al final de `tests/test_sprints_datos.py`:

```python
def test_persona_investigada_con_extra(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Melissa / La que regala", origen="investigada", extra={"avatar_id": 7})
    p = datos.persona("acme", pid)
    assert p["origen"] == "investigada" and p["extra"] == {"avatar_id": 7}
    assert datos.crear_persona("acme", "Sin extra") and datos.persona("acme", pid + 1)["extra"] == {}
```

Agregar al final de `tests/test_gastos.py`:

```python
def test_tipo_avatares_es_conocido(base_temporal):
    import gastos
    gid = gastos.registrar("acme", "avatares", 0.12, "avatares:3:1", detalle="2 núcleos", proveedor="anthropic")
    fila = gastos.historial("acme")[0]
    assert fila["id"] == gid and fila["tipo"] == "avatares" and fila["usd"] == 0.12
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_db.py tests/test_sprints_datos.py::test_persona_investigada_con_extra tests/test_gastos.py::test_tipo_avatares_es_conocido -q`
Expected: FAIL (`estudio` no está entre las tablas; `ErrorDatos: Origen de persona inválido`; `tipo == "otro"`).

- [ ] **Step 3: Escribir la migración**

`migrations/versions/0011_nicho.py`:

```python
"""nicho: estudio, comentario y avatar (comentarios reales -> avatares -> personas)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-18 00:00:00.000000

Parte 1 del spec docs/superpowers/specs/2026-09-18-nicho-avatares-design.md (§2).
`comentario` es único por (estudio_id, fuente, fuente_id): una recolección
repetida no duplica y reintentar una tarea es seguro. `avatar` guarda núcleos
(padre_id NULL) y sub-avatares (padre_id = id del núcleo) en la misma tabla.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _comunes():
    return [
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
    ]


def upgrade() -> None:
    op.create_table('estudio',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('producto', sa.Text()),
        sa.Column('catalogo_id', sa.String(length=80)),
        sa.Column('tema', sa.Text()),
        sa.Column('idioma', sa.String(length=5), nullable=False, server_default='es'),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='armando'),
        sa.Column('archivado', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('generacion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_estudio_cliente', 'estudio', ['cliente'])

    op.create_table('comentario',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('estudio_id', sa.Integer(), sa.ForeignKey('estudio.id'), nullable=False),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('fuente_id', sa.String(length=120), nullable=False),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('url', sa.String(length=500)),
        sa.Column('contexto', sa.String(length=300)),
        sa.Column('puntuacion', sa.Integer()),
        sa.Column('fecha', sa.String(length=19)),
        sa.Column('excluido', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estudio_id', 'fuente', 'fuente_id', name='uq_comentario_fuente'))
    op.create_index('ix_comentario_cliente', 'comentario', ['cliente'])
    op.create_index('ix_comentario_estudio', 'comentario', ['estudio_id'])

    op.create_table('avatar',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('estudio_id', sa.Integer(), sa.ForeignKey('estudio.id'), nullable=False),
        sa.Column('padre_id', sa.Integer(), sa.ForeignKey('avatar.id')),
        sa.Column('tipo', sa.String(length=8), nullable=False),
        sa.Column('base', sa.String(length=24)),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generacion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('deseo', sa.String(length=300)),
        sa.Column('resumen', sa.Text()),
        sa.Column('demografia', sa.Text()),
        sa.Column('edad_rango', sa.String(length=20)),
        sa.Column('emocion', sa.Text()),
        sa.Column('identidad', sa.JSON()),
        sa.Column('soluciones_previas', sa.JSON()),
        sa.Column('situaciones', sa.JSON()),
        sa.Column('comportamiento', sa.Text()),
        sa.Column('conciencia', sa.JSON()),
        sa.Column('encaje_producto', sa.Text()),
        sa.Column('tono', sa.Text()),
        sa.Column('palabras_clave', sa.JSON()),
        sa.Column('evidencia', sa.JSON()),
        sa.Column('sin_evidencia', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='propuesto'),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('persona.id')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_avatar_cliente', 'avatar', ['cliente'])
    op.create_index('ix_avatar_estudio', 'avatar', ['estudio_id'])


def downgrade() -> None:
    for tabla in ('avatar', 'comentario', 'estudio'):
        op.drop_table(tabla)
```

- [ ] **Step 4: Declarar las tablas en `db.py`** (justo antes de `def crear_todo():`)

```python
# --- Nicho y avatares (docs/superpowers/specs/2026-09-18-nicho-avatares-design.md §2, migración 0011) ---

estudio = Table("estudio", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("producto", Text),                                   # qué vendemos (texto libre, prellenado desde el catálogo)
    Column("catalogo_id", String(80)),
    Column("tema", Text),                                       # qué investigar: nicho, mercado, dolores
    Column("idioma", String(5), nullable=False, default="es"),  # idioma de salida de los avatares
    Column("estado", String(12), nullable=False, default="armando"),   # armando|generando|revisando
    Column("archivado", Boolean, default=False),
    Column("generacion", Integer, nullable=False, default=0),   # corridas de Claude
    Column("extra", JSON, default=dict),                        # recolecciones, ultima_generacion, ultimo_error
)

comentario = Table("comentario", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("fuente", String(12), nullable=False),               # texto|csv|reddit|youtube|apify
    Column("fuente_id", String(120), nullable=False),           # id en la fuente; hash del texto para texto/csv
    Column("texto", Text, nullable=False),
    Column("url", String(500)),
    Column("contexto", String(300)),                            # título del post / video / producto
    Column("puntuacion", Integer),                              # votos, likes o estrellas
    Column("fecha", String(19)),
    Column("excluido", Boolean, default=False),                 # nunca entra a la generación
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("estudio_id", "fuente", "fuente_id", name="uq_comentario_fuente"),
)

avatar = Table("avatar", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("padre_id", Integer, sa.ForeignKey("avatar.id")),    # NULL = núcleo; id del núcleo = sub-avatar
    Column("tipo", String(8), nullable=False),                  # nucleo|sub
    Column("base", String(24)),                                 # emocion|experiencia_producto (solo sub)
    Column("orden", Integer, nullable=False, default=0),
    Column("generacion", Integer, nullable=False, default=0),
    Column("nombre", String(120), nullable=False),
    Column("deseo", String(300)),
    Column("resumen", Text),                                    # solo núcleo
    Column("demografia", Text),
    Column("edad_rango", String(20)),
    Column("emocion", Text),
    Column("identidad", JSON, default=dict),                    # {quiere_que_vean, cree_de_si, quiere_lograr}
    Column("soluciones_previas", JSON, default=list),           # [{que, por_que_fallo: [..]}]
    Column("situaciones", JSON, default=list),
    Column("comportamiento", Text),
    Column("conciencia", JSON, default=dict),                   # {nivel, detalle}
    Column("encaje_producto", Text),
    Column("tono", Text),
    Column("palabras_clave", JSON, default=list),
    Column("evidencia", JSON, default=list),                    # [{comentario_id, cita}] verificadas
    Column("sin_evidencia", Boolean, default=False),
    Column("estado", String(12), nullable=False, default="propuesto"),   # propuesto|aprobado|descartado
    Column("persona_id", Integer, sa.ForeignKey("persona.id")),
    Column("extra", JSON, default=dict),
)
```

- [ ] **Step 5: `ORIGENES_PERSONA` y `crear_persona(extra=)` en `sprints/datos.py`**

Línea 33:

```python
ORIGENES_PERSONA = ("manual", "sugerida_ia", "investigada")
```

`crear_persona` (reemplazar la firma y el `extra={}` del insert):

```python
def crear_persona(cliente, nombre, resumen="", descripcion="", edad_rango="", tono="", senales_visuales=None,
                  palabras_clave=None, color=None, origen="manual", extra=None):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La persona necesita un nombre.")
    if origen not in ORIGENES_PERSONA:
        raise ErrorDatos(f"Origen de persona inválido: {origen}. Opciones: {ORIGENES_PERSONA}")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.persona.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, resumen=_texto(resumen, 200),
            descripcion=_texto(descripcion), edad_rango=_texto(edad_rango, 20), tono=_texto(tono),
            senales_visuales=list(senales_visuales or []), palabras_clave=list(palabras_clave or []),
            color=_color(color), origen=origen, archivada=False,
            extra=dict(extra) if isinstance(extra, dict) else {})).inserted_primary_key[0]
```

- [ ] **Step 6: `gastos.TIPOS`** (línea 33)

```python
TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "otro")
```

Y en el comentario de `TARIFAS` agregar una línea: `#  - avatares (Claude, dos pasadas): el estimado lo calcula nicho/avatares.estimar_costo por tokens; el real sale de usage.`

- [ ] **Step 7: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_db.py tests/test_sprints_datos.py tests/test_gastos.py tests/test_sprints_db.py -q`
Expected: PASS (incluida `test_alembic_tiene_una_sola_cabeza`).

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile migrations/versions/0011_nicho.py db.py sprints/datos.py gastos.py
git add migrations/versions/0011_nicho.py db.py sprints/datos.py gastos.py tests/test_nicho_db.py tests/test_sprints_datos.py tests/test_gastos.py
git commit -m "Nicho: migración 0011 (estudio, comentario, avatar), origen de persona investigada y tipo de gasto avatares

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 2: `nicho/datos.py` — estudios y comentarios

**Files:**
- Create: `nicho/__init__.py`, `nicho/datos.py`
- Test: `tests/test_nicho_datos.py`

**Interfaces:**
- Consumes: `db.estudio`, `db.comentario`, `db.avatar` (Task 1); `cola.consultar_por_job(job_id)`.
- Produces (todo en `nicho.datos`):
  - Constantes `ESTADOS_ESTUDIO = ("armando", "generando", "revisando")`, `FUENTES = ("texto", "csv", "reddit", "youtube", "apify")`, `TIPOS_AVATAR`, `BASES = ("emocion", "experiencia_producto")`, `ESTADOS_AVATAR = ("propuesto", "aprobado", "descartado")`, `NIVELES_CONCIENCIA`, `CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")`, `MAX_RECOLECCIONES = 20`.
  - `class ErrorDatos(ValueError)`.
  - `job_id_generar(cliente, estudio_id) -> "nicho:<cliente>:<estudio_id>:generar"`.
  - `crear_estudio(cliente, nombre, producto="", tema="", idioma="es", catalogo_id=None) -> int`; `actualizar_estudio(cliente, estudio_id, /, **campos) -> bool`; `archivar_estudio(cliente, estudio_id, archivado=True) -> bool`; `actualizar_extra_estudio(cliente, estudio_id, fn) -> dict|None`; `registrar_recoleccion(cliente, estudio_id, registro) -> dict|None`; `estudios(cliente, incluir_archivados=False) -> list[dict]`; `estudio(cliente, estudio_id) -> dict|None`; `recalcular(cliente, estudio_id, tarea_viva=None) -> str|None`.
  - Cada dict de estudio trae además `comentarios_total`, `comentarios_activos`, `fuentes` (`{fuente: {"total", "excluidos"}}`), `avatares_aprobados`, `avatares_total`.
  - `agregar_comentarios(cliente, estudio_id, fuente, lista) -> {"nuevos": int, "repetidos": int}`; `comentarios(cliente, estudio_id, fuente=None, pagina=1, por_pagina=50) -> {"items", "total", "pagina", "paginas"}`; `comentario(cliente, comentario_id) -> dict|None`; `comentarios_para_generar(cliente, estudio_id) -> list[dict]` (no excluidos, por id); `contar_por_fuente(cliente, estudio_id) -> dict`; `excluir_comentario(cliente, comentario_id, excluido=True) -> bool`; `borrar_fuente(cliente, estudio_id, fuente) -> int`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_datos.py`:

```python
import pytest


def _c(i, texto=None, **extra):
    """Comentario normalizado mínimo (lo que produce nicho.fuentes.base.normalizar_comentario)."""
    return {"fuente_id": f"c{i}", "texto": texto or f"Comentario número {i}: la garrafa pesa demasiado y gotea.",
            "url": None, "contexto": None, "puntuacion": None, "fecha": None, "extra": {}, **extra}


def test_estudio_crear_listar_editar_archivar(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "Detergente Suecia", producto="Cápsulas sin plástico", tema="lavar sin cargar",
                              idioma="sv", catalogo_id="capsulas")
    e = datos.estudio("acme", eid)
    assert e["nombre"] == "Detergente Suecia" and e["idioma"] == "sv" and e["estado"] == "armando"
    assert e["generacion"] == 0 and e["archivado"] is False and e["catalogo_id"] == "capsulas"
    assert e["comentarios_total"] == 0 and e["fuentes"] == {} and e["avatares_aprobados"] == 0
    assert datos.actualizar_estudio("acme", eid, tema="otro tema") and datos.estudio("acme", eid)["tema"] == "otro tema"
    assert datos.estudio("otro", eid) is None and datos.estudios("otro") == []
    datos.archivar_estudio("acme", eid)
    assert datos.estudios("acme") == [] and len(datos.estudios("acme", incluir_archivados=True)) == 1


def test_estudio_valida(base_temporal):
    from nicho import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_estudio("acme", "   ")
    eid = datos.crear_estudio("acme", "X", idioma="ZZZZZZZ")
    assert datos.estudio("acme", eid)["idioma"] == "es"          # idioma raro -> español
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, cliente="otro")     # campo no editable
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, estado="volando")


def test_comentarios_agregar_dedup_paginar_excluir_borrar(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    r = datos.agregar_comentarios("acme", eid, "texto", [_c(1), _c(2), _c(1)])
    assert r == {"nuevos": 2, "repetidos": 1}
    assert datos.agregar_comentarios("acme", eid, "texto", [_c(2)]) == {"nuevos": 0, "repetidos": 1}
    assert datos.agregar_comentarios("acme", eid, "csv", [_c(2), _c(3, puntuacion=5, url="https://x/y")]) == {"nuevos": 2, "repetidos": 0}
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 4 and e["fuentes"] == {"texto": {"total": 2, "excluidos": 0}, "csv": {"total": 2, "excluidos": 0}}
    pagina = datos.comentarios("acme", eid, por_pagina=3)
    assert pagina["total"] == 4 and pagina["paginas"] == 2 and len(pagina["items"]) == 3
    assert pagina["items"][0]["fuente"] == "csv" and pagina["items"][0]["puntuacion"] == 5    # más nuevo primero
    assert datos.comentarios("acme", eid, fuente="texto")["total"] == 2
    cid = pagina["items"][0]["id"]
    assert datos.excluir_comentario("acme", cid) and datos.comentario("acme", cid)["excluido"] is True
    assert datos.contar_por_fuente("acme", eid)["csv"] == {"total": 2, "excluidos": 1}
    assert [c["id"] for c in datos.comentarios_para_generar("acme", eid)] == sorted(c["id"] for c in datos.comentarios("acme", eid)["items"] if c["id"] != cid)
    assert datos.estudio("acme", eid)["comentarios_activos"] == 3
    assert datos.excluir_comentario("acme", cid, excluido=False) and datos.comentario("acme", cid)["excluido"] is False
    assert datos.borrar_fuente("acme", eid, "csv") == 2 and datos.estudio("acme", eid)["comentarios_total"] == 2
    assert datos.comentario("otro", cid) is None and datos.excluir_comentario("otro", cid) is False


def test_comentarios_valida_fuente_y_estudio(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_comentarios("acme", eid, "magia", [_c(1)])
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_comentarios("acme", 999, "texto", [_c(1)])
    assert datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": "", "texto": "x"}, {"fuente_id": "a", "texto": "  "}]) == {"nuevos": 0, "repetidos": 0}


def test_extra_y_recolecciones(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    assert datos.actualizar_extra_estudio("acme", eid, lambda x: {**x, "ultimo_error": "falló"})["ultimo_error"] == "falló"
    assert datos.actualizar_extra_estudio("acme", 999, lambda x: x) is None
    for i in range(datos.MAX_RECOLECCIONES + 3):
        datos.registrar_recoleccion("acme", eid, {"fuente": "texto", "nuevos": i, "repetidos": 0})
    rec = datos.estudio("acme", eid)["extra"]["recolecciones"]
    assert len(rec) == datos.MAX_RECOLECCIONES and rec[-1]["nuevos"] == datos.MAX_RECOLECCIONES + 2 and rec[-1]["fecha"]


def test_recalcular(base_temporal, monkeypatch):
    from nicho import datos
    import cola
    eid = datos.crear_estudio("acme", "X")
    assert datos.recalcular("acme", eid) == "armando"
    monkeypatch.setattr(cola, "consultar_por_job", lambda job_id: {"estado": "en_curso"} if job_id == datos.job_id_generar("acme", eid) else None)
    assert datos.recalcular("acme", eid) == "generando" and datos.estudio("acme", eid)["estado"] == "generando"
    assert datos.recalcular("acme", eid, tarea_viva=False) == "armando"
    assert datos.recalcular("acme", 999) is None
    assert datos.job_id_generar("acme", eid) == f"nicho:acme:{eid}:generar"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho'`.

- [ ] **Step 3: Escribir `nicho/__init__.py` y `nicho/datos.py`**

`nicho/__init__.py`:

```python
"""
Nicho y avatares: comentarios reales de la gente -> avatares por deseo (núcleo)
y sub-avatares con evidencia -> personas de Sprints con origen `investigada`.
Spec: docs/superpowers/specs/2026-09-18-nicho-avatares-design.md.
"""
```

`nicho/datos.py` (esta tarea deja los estudios y comentarios; la Task 3 agrega la sección de avatares al mismo archivo):

```python
"""
Datos del módulo Nicho (spec §2): estudios, comentarios y avatares. ÚNICO
escritor de las tres tablas. Solo SQLAlchemy Core sobre data/creatv.db; nada
de Flask ni de proveedores. Aprobar un sub-avatar crea o actualiza una persona
de Sprints (origen `investigada`) a través de `sprints.datos`, que sigue siendo
el único escritor de `persona`.
"""
import re

import sqlalchemy as sa

import cola
import db
from sprints import datos as sprints_datos
from sprints.sugerencias import COLORES

ESTADOS_ESTUDIO = ("armando", "generando", "revisando")
FUENTES = ("texto", "csv", "reddit", "youtube", "apify")
TIPOS_AVATAR = ("nucleo", "sub")
BASES = ("emocion", "experiencia_producto")
ESTADOS_AVATAR = ("propuesto", "aprobado", "descartado")
NIVELES_CONCIENCIA = ("inconsciente", "consciente_del_problema", "consciente_de_la_solucion",
                      "consciente_del_producto", "muy_consciente")
CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")
MAX_RECOLECCIONES = 20          # registros que se conservan en estudio.extra["recolecciones"]

_ESTUDIO_COLS = ("nombre", "producto", "catalogo_id", "tema", "idioma", "estado", "archivado", "generacion", "extra")
_AVATAR_COLS = ("nombre", "deseo", "resumen", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave", "evidencia",
                "sin_evidencia", "estado", "persona_id", "orden", "base", "extra")
# Lo que el formulario de revisión puede tocar (estado/persona_id van por aprobar/descartar).
AVATAR_EDITABLES = ("nombre", "deseo", "base", "demografia", "edad_rango", "emocion", "identidad", "soluciones_previas",
                    "situaciones", "comportamiento", "conciencia", "encaje_producto", "tono", "palabras_clave")
_RE_IDIOMA = re.compile(r"^[a-z]{2,5}$")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


def job_id_generar(cliente, estudio_id):
    """Un solo trabajo de generación vivo por estudio (spec §7): la ruta y la
    tarea usan este mismo id, y `recalcular` lo consulta en la cola."""
    return f"nicho:{cliente}:{int(estudio_id)}:generar"


# ------------------------------------------------------------ helpers ---

def _a_dict(fila):
    return dict(fila._mapping)


def _fila(con, tabla, fila_id, cliente):
    return con.execute(sa.select(tabla).where(tabla.c.id == fila_id, tabla.c.cliente == cliente)).first()


def _actualizar(con, tabla, fila_id, cliente, permitidas, campos):
    malos = set(campos) - set(permitidas)
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=db.ahora(), **campos))
    return r.rowcount == 1


def _bloquear(con, tabla, fila_id, cliente):
    """Toma el lock de escritura de SQLite ANTES de leer (semántica de
    `BEGIN IMMEDIATE`), igual que `experimentos._bloquear`: un UPDATE sin
    efecto obliga al driver a abrir la transacción ya, así el SELECT que sigue
    ve lo que dejó el último escritor (gunicorn y el worker escriben `extra`
    a la vez). Devuelve True si la fila existe."""
    r = con.execute(tabla.update().where(tabla.c.id == fila_id, tabla.c.cliente == cliente)
                    .values(actualizado_en=tabla.c.actualizado_en))
    return r.rowcount == 1


def _texto(v, largo=None):
    v = (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())
    return v[:largo] if largo else v


def _idioma(v):
    v = (v or "").strip().lower()
    return v if _RE_IDIOMA.match(v) else "es"


# ----------------------------------------------------------- estudios ---

def crear_estudio(cliente, nombre, producto="", tema="", idioma="es", catalogo_id=None):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("El estudio necesita un nombre.")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.estudio.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, producto=_texto(producto),
            catalogo_id=_texto(catalogo_id, 80) or None, tema=_texto(tema), idioma=_idioma(idioma), estado="armando",
            archivado=False, generacion=0, extra={})).inserted_primary_key[0]


def actualizar_estudio(cliente, estudio_id, /, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("El estudio necesita un nombre.")
    if "idioma" in campos:
        campos["idioma"] = _idioma(campos["idioma"])
    if "estado" in campos and campos["estado"] not in ESTADOS_ESTUDIO:
        raise ErrorDatos(f"Estado de estudio inválido: {campos['estado']}")
    for k in ("producto", "tema"):
        if k in campos:
            campos[k] = _texto(campos[k])
    if "catalogo_id" in campos:
        campos["catalogo_id"] = _texto(campos["catalogo_id"], 80) or None
    with db.conectar() as con:
        return _actualizar(con, db.estudio, estudio_id, cliente, _ESTUDIO_COLS, campos)


def archivar_estudio(cliente, estudio_id, archivado=True):
    return actualizar_estudio(cliente, estudio_id, archivado=bool(archivado))


def actualizar_extra_estudio(cliente, estudio_id, fn):
    """Read-modify-write atómico de `estudio.extra` (lock antes de leer, una
    transacción). `fn(extra) -> extra`. Devuelve el extra escrito o None."""
    with db.conectar() as con:
        if not _bloquear(con, db.estudio, estudio_id, cliente):
            return None
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        extra = fn(dict(f.extra or {}))
        con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                    .values(actualizado_en=db.ahora(), extra=extra))
        return extra


def registrar_recoleccion(cliente, estudio_id, registro):
    """Anota una recolección (fuente, nuevos, repetidos, aviso) con fecha en
    `extra.recolecciones`; conserva las últimas MAX_RECOLECCIONES."""
    entrada = {**dict(registro or {}), "fecha": db.ahora()}

    def _fn(extra):
        lista = list(extra.get("recolecciones") or []) + [entrada]
        return {**extra, "recolecciones": lista[-MAX_RECOLECCIONES:]}
    return actualizar_extra_estudio(cliente, estudio_id, _fn)


def _conteos(con, cliente, ids):
    """Por estudio: comentarios por fuente (con excluidos) y sub-avatares por estado."""
    c, a = db.comentario, db.avatar
    fuentes, aprobados, subs = {}, {}, {}
    if not ids:
        return fuentes, aprobados, subs
    excluidos = sa.func.sum(sa.case((c.c.excluido.is_(True), 1), else_=0))
    for eid, fuente, n, exc in con.execute(
            sa.select(c.c.estudio_id, c.c.fuente, sa.func.count(), excluidos)
            .where(c.c.cliente == cliente, c.c.estudio_id.in_(ids)).group_by(c.c.estudio_id, c.c.fuente)):
        fuentes.setdefault(eid, {})[fuente] = {"total": int(n), "excluidos": int(exc or 0)}
    for eid, estado, n in con.execute(
            sa.select(a.c.estudio_id, a.c.estado, sa.func.count())
            .where(a.c.cliente == cliente, a.c.estudio_id.in_(ids), a.c.tipo == "sub").group_by(a.c.estudio_id, a.c.estado)):
        if estado == "aprobado":
            aprobados[eid] = int(n)
        if estado != "descartado":
            subs[eid] = subs.get(eid, 0) + int(n)
    return fuentes, aprobados, subs


def _decorar(e, fuentes, aprobados, subs):
    por_fuente = fuentes.get(e["id"], {})
    total = sum(v["total"] for v in por_fuente.values())
    e["comentarios_total"] = total
    e["comentarios_activos"] = total - sum(v["excluidos"] for v in por_fuente.values())
    e["fuentes"] = por_fuente
    e["avatares_aprobados"] = aprobados.get(e["id"], 0)
    e["avatares_total"] = subs.get(e["id"], 0)
    e["extra"] = dict(e.get("extra") or {})
    return e


def estudios(cliente, incluir_archivados=False):
    t = db.estudio
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivados:
        q = q.where(t.c.archivado.is_(False))
    with db.conectar() as con:
        lista = [_a_dict(f) for f in con.execute(q.order_by(t.c.id.desc()))]
        fuentes, aprobados, subs = _conteos(con, cliente, [e["id"] for e in lista])
    return [_decorar(e, fuentes, aprobados, subs) for e in lista]


def estudio(cliente, estudio_id):
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        fuentes, aprobados, subs = _conteos(con, cliente, [f.id])
    return _decorar(_a_dict(f), fuentes, aprobados, subs)


def recalcular(cliente, estudio_id, tarea_viva=None):
    """Re-deriva `estudio.estado` (spec §1): `generando` si hay una tarea viva
    con el job_id de generación (consultado en la cola salvo que el llamador
    ya lo sepa: la tarea misma pasa `tarea_viva=False` al terminar, porque
    desde adentro su fila sigue `en_curso`); si no, `revisando` cuando el
    estudio tiene algún avatar; si no, `armando`. Devuelve el estado o None."""
    if tarea_viva is None:
        fila = cola.consultar_por_job(job_id_generar(cliente, estudio_id))
        tarea_viva = bool(fila and fila["estado"] in ("pendiente", "en_curso"))
    with db.conectar() as con:
        f = _fila(con, db.estudio, estudio_id, cliente)
        if not f:
            return None
        n = con.execute(sa.select(sa.func.count()).select_from(db.avatar).where(
            db.avatar.c.estudio_id == estudio_id, db.avatar.c.cliente == cliente)).scalar() or 0
        nuevo = "generando" if tarea_viva else ("revisando" if n else "armando")
        if nuevo != f.estado:
            con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                        .values(actualizado_en=db.ahora(), estado=nuevo))
    return nuevo


# -------------------------------------------------------- comentarios ---

def agregar_comentarios(cliente, estudio_id, fuente, lista):
    """Inserta comentarios ya normalizados (`nicho.fuentes.base.normalizar_comentario`)
    en UNA transacción con `INSERT OR IGNORE` sobre `uq_comentario_fuente`:
    los repetidos no duplican. Un dict sin texto o sin fuente_id se salta."""
    if fuente not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {fuente}")
    ahora = db.ahora()
    nuevos = repetidos = 0
    with db.conectar() as con:
        if not _fila(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos("Ese estudio no existe.")
        for c in lista or []:
            texto = _texto((c or {}).get("texto"))
            fuente_id = _texto((c or {}).get("fuente_id"), 120)
            if not texto or not fuente_id:
                continue
            r = con.execute(db.comentario.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, fuente=fuente,
                fuente_id=fuente_id, texto=texto[:2000], url=_texto(c.get("url"), 500) or None,
                contexto=_texto(c.get("contexto"), 300) or None, puntuacion=c.get("puntuacion"),
                fecha=_texto(c.get("fecha"), 19) or None, excluido=False,
                extra=dict(c.get("extra")) if isinstance(c.get("extra"), dict) else {}))
            if r.rowcount == 1:
                nuevos += 1
            else:
                repetidos += 1
    return {"nuevos": nuevos, "repetidos": repetidos}


def comentarios(cliente, estudio_id, fuente=None, pagina=1, por_pagina=50):
    """Página de comentarios, más nuevo primero (incluye excluidos, con su bandera)."""
    c = db.comentario
    cond = [c.c.cliente == cliente, c.c.estudio_id == estudio_id]
    if fuente:
        cond.append(c.c.fuente == fuente)
    pagina = max(1, int(pagina or 1))
    por_pagina = max(1, min(200, int(por_pagina or 50)))
    with db.conectar() as con:
        total = int(con.execute(sa.select(sa.func.count()).select_from(c).where(*cond)).scalar() or 0)
        filas = con.execute(sa.select(c).where(*cond).order_by(c.c.id.desc())
                            .limit(por_pagina).offset((pagina - 1) * por_pagina)).all()
    return {"items": [_a_dict(f) for f in filas], "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // por_pagina))}


def comentario(cliente, comentario_id):
    with db.conectar() as con:
        f = _fila(con, db.comentario, comentario_id, cliente)
    return _a_dict(f) if f else None


def comentarios_para_generar(cliente, estudio_id):
    """Los que entran a Claude: no excluidos, en orden de id."""
    c = db.comentario
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(sa.select(c).where(
            c.c.cliente == cliente, c.c.estudio_id == estudio_id, c.c.excluido.is_(False)).order_by(c.c.id))]


def contar_por_fuente(cliente, estudio_id):
    with db.conectar() as con:
        fuentes, _, _ = _conteos(con, cliente, [estudio_id])
    return fuentes.get(estudio_id, {})


def excluir_comentario(cliente, comentario_id, excluido=True):
    with db.conectar() as con:
        r = con.execute(db.comentario.update().where(
            db.comentario.c.id == comentario_id, db.comentario.c.cliente == cliente)
            .values(actualizado_en=db.ahora(), excluido=bool(excluido)))
    return r.rowcount == 1


def borrar_fuente(cliente, estudio_id, fuente):
    """Borra todos los comentarios de una fuente en el estudio; devuelve cuántos."""
    with db.conectar() as con:
        r = con.execute(db.comentario.delete().where(
            db.comentario.c.cliente == cliente, db.comentario.c.estudio_id == estudio_id, db.comentario.c.fuente == fuente))
    return int(r.rowcount or 0)
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos.py -q`
Expected: PASS (6 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/__init__.py nicho/datos.py
git add nicho/__init__.py nicho/datos.py tests/test_nicho_datos.py
git commit -m "Nicho: datos de estudios y comentarios (dedup por fuente, paginación, recolecciones, recalcular)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 3: `nicho/datos.py` — avatares, aprobar → persona, descartar

**Files:**
- Modify: `nicho/datos.py` (agregar la sección `avatares` al final)
- Test: `tests/test_nicho_datos.py` (agregar pruebas)

**Interfaces:**
- Consumes: `sprints.datos.crear_persona(..., origen="investigada", extra=)`, `actualizar_persona`, `archivar_persona`, `persona`, `personas`; `sprints.sugerencias.COLORES`.
- Produces (en `nicho.datos`):
  - `guardar_generacion(cliente, estudio_id, nucleos, resumen=None) -> {"generacion", "nucleos", "subs"}`. `nucleos` es una lista de dicts `{"nombre", "deseo", "resumen", "sub_avatares": [sub...], "error": str|None}`; cada `sub` trae las claves de `AVATAR_EDITABLES` más `evidencia` y `sin_evidencia` (la forma que devuelve `nicho.avatares.parsear_subs` + `verificar_evidencia`).
  - `avatares(cliente, estudio_id) -> list[dict núcleo con "subs": [dict]]` (orden: generación, orden, id).
  - `avatar(cliente, avatar_id) -> dict|None`; `actualizar_avatar(cliente, avatar_id, /, **campos) -> bool` (solo `AVATAR_EDITABLES`, validados con `validar_campos_avatar`).
  - `validar_campos_avatar(campos) -> dict` (público: lo reutiliza `nicho.avatares` para no repetir reglas).
  - `persona_desde_avatar(a) -> dict` con `nombre, resumen, descripcion, edad_rango, tono, senales_visuales, palabras_clave`.
  - `aprobar_avatar(cliente, avatar_id) -> int` (persona_id); `descartar_avatar(cliente, avatar_id) -> bool`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_datos.py`)

```python
SUB = {
    "base": "emocion", "nombre": "Melissa / La que regala con cabeza", "deseo": "Quiero regalar algo útil y personal",
    "demografia": "Mujer de 30 a 50, ciudad", "edad_rango": "30-50", "emocion": "Presión por no quedar mal",
    "identidad": {"quiere_que_vean": "detallista", "cree_de_si": "generosa", "quiere_lograr": "ser la que acierta"},
    "soluciones_previas": [{"que": "Tarjetas de regalo", "por_que_fallo": ["impersonales", "sin valor duradero"]}],
    "situaciones": ["Comprando a última hora", "Buscando en el centro comercial"],
    "comportamiento": "Compra lo seguro aunque no emocione",
    "conciencia": {"nivel": "inconsciente", "detalle": "No sabe que existe algo mejor"},
    "encaje_producto": "Pantuflas con soporte: útil y personal", "tono": "Cálido, con culpa leve",
    "palabras_clave": ["regalo", "detalle"], "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}],
    "sin_evidencia": False,
}


def _estudio_con_generacion(datos, n_subs=2):
    eid = datos.crear_estudio("acme", "X", producto="Pantuflas")
    datos.agregar_comentarios("acme", eid, "texto", [_c(i) for i in range(1, 4)])
    nucleos = [{"nombre": "Regalo con cabeza", "deseo": "Quiero regalar bien", "resumen": "Quienes regalan",
                "sub_avatares": [dict(SUB, nombre=f"Sub {i}") for i in range(n_subs)]},
               {"nombre": "Pies cansados", "deseo": "Quiero descansar los pies", "resumen": "", "sub_avatares": [], "error": "JSON inválido"}]
    return eid, datos.guardar_generacion("acme", eid, nucleos, {"comentarios": 3, "usd": 0.04})


def test_guardar_generacion_y_listar(base_temporal):
    from nicho import datos
    eid, r = _estudio_con_generacion(datos)
    assert r == {"generacion": 1, "nucleos": 2, "subs": 2}
    e = datos.estudio("acme", eid)
    assert e["estado"] == "revisando" and e["generacion"] == 1 and e["extra"]["ultima_generacion"]["usd"] == 0.04
    assert e["extra"]["ultima_generacion"]["generacion"] == 1 and e["avatares_total"] == 2 and e["avatares_aprobados"] == 0
    nucleos = datos.avatares("acme", eid)
    assert [n["nombre"] for n in nucleos] == ["Regalo con cabeza", "Pies cansados"]
    assert nucleos[1]["extra"] == {"error": "JSON inválido"} and nucleos[1]["subs"] == []
    s = nucleos[0]["subs"][0]
    assert s["tipo"] == "sub" and s["padre_id"] == nucleos[0]["id"] and s["estado"] == "propuesto" and s["generacion"] == 1
    assert s["identidad"]["cree_de_si"] == "generosa" and s["soluciones_previas"][0]["por_que_fallo"] == ["impersonales", "sin valor duradero"]
    assert s["conciencia"] == {"nivel": "inconsciente", "detalle": "No sabe que existe algo mejor"} and s["sin_evidencia"] is False
    assert datos.avatar("acme", s["id"])["nombre"] == "Sub 0" and datos.avatar("otro", s["id"]) is None
    assert datos.avatares("otro", eid) == []


def test_regenerar_conserva_aprobados(base_temporal):
    from nicho import datos
    eid, _ = _estudio_con_generacion(datos)
    nucleos = datos.avatares("acme", eid)
    aprobado = nucleos[0]["subs"][0]
    pid = datos.aprobar_avatar("acme", aprobado["id"])
    datos.descartar_avatar("acme", nucleos[0]["subs"][1]["id"])
    r = datos.guardar_generacion("acme", eid, [{"nombre": "Nuevo", "deseo": "Quiero lo nuevo", "resumen": "", "sub_avatares": [SUB]}])
    assert r["generacion"] == 2
    lista = datos.avatares("acme", eid)
    assert [n["nombre"] for n in lista] == ["Regalo con cabeza", "Nuevo"]            # "Pies cansados" (sin aprobados) se fue
    assert [s["estado"] for s in lista[0]["subs"]] == ["aprobado"] and lista[0]["subs"][0]["persona_id"] == pid
    assert lista[1]["subs"][0]["generacion"] == 2 and lista[1]["generacion"] == 2
    assert datos.estudio("acme", eid)["generacion"] == 2


def test_aprobar_crea_actualiza_y_descartar_archiva(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, _ = _estudio_con_generacion(datos)
    sub = datos.avatares("acme", eid)[0]["subs"][0]
    pid = datos.aprobar_avatar("acme", sub["id"])
    p = sd.persona("acme", pid)
    assert p["origen"] == "investigada" and p["nombre"] == "Sub 0" and p["resumen"] == "Quiero regalar algo útil y personal"
    assert p["edad_rango"] == "30-50" and p["tono"] == "Cálido, con culpa leve" and p["senales_visuales"] == SUB["situaciones"]
    assert p["palabras_clave"] == ["regalo", "detalle"] and p["color"] in datos.COLORES
    assert "Mujer de 30 a 50" in p["descripcion"] and "Usó Tarjetas de regalo: impersonales, sin valor duradero" in p["descripcion"]
    assert p["extra"]["avatar_id"] == sub["id"] and p["extra"]["conciencia"]["nivel"] == "inconsciente" and p["extra"]["identidad"]["quiere_lograr"] == "ser la que acierta"
    a = datos.avatar("acme", sub["id"])
    assert a["estado"] == "aprobado" and a["persona_id"] == pid
    datos.actualizar_avatar("acme", sub["id"], nombre="Melissa", tono="Directo")
    assert sd.persona("acme", pid)["nombre"] == "Sub 0"                 # editar no toca la persona...
    assert datos.aprobar_avatar("acme", sub["id"]) == pid               # ...hasta volver a aprobar: misma persona
    assert sd.persona("acme", pid)["nombre"] == "Melissa" and sd.persona("acme", pid)["tono"] == "Directo"
    assert len(sd.personas("acme", incluir_archivadas=True)) == 1
    assert datos.descartar_avatar("acme", sub["id"]) and datos.avatar("acme", sub["id"])["estado"] == "descartado"
    assert sd.persona("acme", pid)["archivada"] is True
    assert datos.aprobar_avatar("acme", sub["id"]) == pid and sd.persona("acme", pid)["archivada"] is False
    nucleo = datos.avatares("acme", eid)[0]
    with pytest.raises(datos.ErrorDatos):
        datos.aprobar_avatar("acme", nucleo["id"])                      # el núcleo no se aprueba
    with pytest.raises(datos.ErrorDatos):
        datos.aprobar_avatar("acme", 999)


def test_actualizar_avatar_valida(base_temporal):
    from nicho import datos
    eid, _ = _estudio_con_generacion(datos)
    sid = datos.avatares("acme", eid)[0]["subs"][0]["id"]
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_avatar("acme", sid, estado="aprobado")          # no editable por acá
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_avatar("acme", sid, nombre="  ")
    assert datos.actualizar_avatar("acme", sid, base="rara", conciencia={"nivel": "x", "detalle": "d"},
                                   soluciones_previas=[{"que": "", "por_que_fallo": ["a"]}, {"que": "Pods", "por_que_fallo": "no lista"}],
                                   identidad={"cree_de_si": "fuerte", "otra": "x"}, palabras_clave="no lista")
    a = datos.avatar("acme", sid)
    assert a["base"] == "emocion" and a["conciencia"] == {"nivel": "", "detalle": "d"}
    assert a["soluciones_previas"] == [{"que": "Pods", "por_que_fallo": []}]
    assert a["identidad"] == {"quiere_que_vean": "", "cree_de_si": "fuerte", "quiere_lograr": ""} and a["palabras_clave"] == []
    assert datos.actualizar_avatar("otro", sid, nombre="X") is False
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos.py -q`
Expected: FAIL con `AttributeError: module 'nicho.datos' has no attribute 'guardar_generacion'`.

- [ ] **Step 3: Agregar la sección de avatares a `nicho/datos.py`**

```python
# ----------------------------------------------------------- avatares ---

def _lista_textos(v, n=8, largo=300):
    """Solo listas: un texto suelto (formulario mal armado, Claude) se ignora."""
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:largo] for x in v if str(x).strip()][:n]


def validar_campos_avatar(campos):
    """Normaliza los campos editables de un sub-avatar (formulario o Claude):
    recorta largos, castea listas, deja `base` en BASES, `conciencia.nivel`
    en NIVELES_CONCIENCIA o vacío (no se inventa), `identidad` con sus tres
    claves. Solo acepta claves de AVATAR_EDITABLES + evidencia/sin_evidencia."""
    permitidas = set(AVATAR_EDITABLES) | {"evidencia", "sin_evidencia"}
    malos = set(campos) - permitidas
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    c = dict(campos)
    if "nombre" in c:
        c["nombre"] = _texto(c["nombre"], 120)
        if not c["nombre"]:
            raise ErrorDatos("El avatar necesita un nombre.")
    if "deseo" in c:
        c["deseo"] = _texto(c["deseo"], 300)
    for k in ("demografia", "emocion", "comportamiento", "encaje_producto", "tono"):
        if k in c:
            c[k] = _texto(c[k], 1500)
    if "edad_rango" in c:
        c["edad_rango"] = _texto(c["edad_rango"], 20)
    if "base" in c:
        c["base"] = c["base"] if c["base"] in BASES else "emocion"
    if "identidad" in c:
        ident = c["identidad"] if isinstance(c["identidad"], dict) else {}
        c["identidad"] = {k: _texto(ident.get(k), 1500) for k in CLAVES_IDENTIDAD}
    if "soluciones_previas" in c:
        limpias = []
        for s in (c["soluciones_previas"] if isinstance(c["soluciones_previas"], list) else [])[:8]:
            if isinstance(s, dict) and _texto(s.get("que")):
                limpias.append({"que": _texto(s.get("que"), 300), "por_que_fallo": _lista_textos(s.get("por_que_fallo"))})
        c["soluciones_previas"] = limpias
    if "situaciones" in c:
        c["situaciones"] = _lista_textos(c["situaciones"])
    if "palabras_clave" in c:
        c["palabras_clave"] = _lista_textos(c["palabras_clave"], n=8, largo=60)
    if "conciencia" in c:
        con_ = c["conciencia"] if isinstance(c["conciencia"], dict) else {}
        nivel = con_.get("nivel") if con_.get("nivel") in NIVELES_CONCIENCIA else ""
        c["conciencia"] = {"nivel": nivel, "detalle": _texto(con_.get("detalle"), 1500)}
    if "evidencia" in c:
        ev = []
        for e in (c["evidencia"] if isinstance(c["evidencia"], list) else [])[:8]:
            if isinstance(e, dict) and _texto(e.get("cita")):
                try:
                    ev.append({"comentario_id": int(e.get("comentario_id")), "cita": _texto(e.get("cita"), 500)})
                except (TypeError, ValueError):
                    continue
        c["evidencia"] = ev
    if "sin_evidencia" in c:
        c["sin_evidencia"] = bool(c["sin_evidencia"])
    return c


_SUB_VACIO = {"demografia": "", "edad_rango": "", "emocion": "", "identidad": {}, "soluciones_previas": [],
              "situaciones": [], "comportamiento": "", "conciencia": {}, "encaje_producto": "", "tono": "",
              "palabras_clave": [], "evidencia": [], "sin_evidencia": False}


def guardar_generacion(cliente, estudio_id, nucleos, resumen=None):
    """Una sola transacción (spec §4.6): sube `generacion`, borra los
    sub-avatares propuesto/descartado de corridas anteriores y los núcleos que
    quedan sin ningún aprobado, inserta lo nuevo con la generación actual,
    deja el estudio en `revisando` y guarda el resumen en extra."""
    ahora = db.ahora()
    a = db.avatar
    with db.conectar() as con:
        if not _bloquear(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos("Ese estudio no existe.")
        f = _fila(con, db.estudio, estudio_id, cliente)
        g = int(f.generacion or 0) + 1
        con.execute(a.delete().where(a.c.estudio_id == estudio_id, a.c.cliente == cliente, a.c.tipo == "sub",
                                     a.c.estado.in_(("propuesto", "descartado"))))
        con_hijos = sa.select(a.c.padre_id).where(a.c.estudio_id == estudio_id, a.c.padre_id.isnot(None))
        con.execute(a.delete().where(a.c.estudio_id == estudio_id, a.c.cliente == cliente, a.c.tipo == "nucleo",
                                     a.c.id.notin_(con_hijos)))
        n_subs = 0
        for i, n in enumerate(nucleos or []):
            nid = con.execute(a.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, padre_id=None,
                tipo="nucleo", base=None, orden=i, generacion=g, nombre=_texto(n.get("nombre"), 120) or "Sin nombre",
                deseo=_texto(n.get("deseo"), 300), resumen=_texto(n.get("resumen")), estado="propuesto", persona_id=None,
                extra={"error": _texto(n.get("error"), 500)} if n.get("error") else {}, **_SUB_VACIO)).inserted_primary_key[0]
            for j, s in enumerate(n.get("sub_avatares") or []):
                campos = {**_SUB_VACIO, "base": "emocion", **validar_campos_avatar(
                    {k: v for k, v in dict(s).items() if k in AVATAR_EDITABLES or k in ("evidencia", "sin_evidencia")})}
                campos["resumen"] = ""
                con.execute(a.insert().values(cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id,
                                              padre_id=nid, tipo="sub", orden=j, generacion=g, estado="propuesto",
                                              persona_id=None, extra={}, **campos))
                n_subs += 1
        extra = dict(f.extra or {})
        extra["ultima_generacion"] = {**dict(resumen or {}), "generacion": g, "fecha": ahora}
        extra.pop("ultimo_error", None)
        con.execute(db.estudio.update().where(db.estudio.c.id == estudio_id)
                    .values(actualizado_en=ahora, generacion=g, estado="revisando", extra=extra))
    return {"generacion": g, "nucleos": len(nucleos or []), "subs": n_subs}


def avatares(cliente, estudio_id):
    """Núcleos con sus `subs` anidados, en orden (generación, orden, id)."""
    a = db.avatar
    with db.conectar() as con:
        filas = [_a_dict(f) for f in con.execute(sa.select(a).where(
            a.c.estudio_id == estudio_id, a.c.cliente == cliente).order_by(a.c.generacion, a.c.orden, a.c.id))]
    nucleos = [dict(f, subs=[]) for f in filas if f["tipo"] == "nucleo"]
    por_id = {n["id"]: n for n in nucleos}
    for f in filas:
        if f["tipo"] == "sub" and f["padre_id"] in por_id:
            por_id[f["padre_id"]]["subs"].append(f)
    return nucleos


def avatar(cliente, avatar_id):
    with db.conectar() as con:
        f = _fila(con, db.avatar, avatar_id, cliente)
    return _a_dict(f) if f else None


def actualizar_avatar(cliente, avatar_id, /, **campos):
    campos = validar_campos_avatar({k: v for k, v in campos.items()})
    if "evidencia" in campos or "sin_evidencia" in campos:
        raise ErrorDatos("La evidencia no se edita a mano.")
    with db.conectar() as con:
        return _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, campos)


def persona_desde_avatar(a):
    """Mapeo del spec §5: nombre, resumen ← deseo, descripción ← demografía +
    emoción + comportamiento + soluciones previas, edad, tono, señales
    visuales ← situaciones, palabras clave."""
    soluciones = []
    for s in a.get("soluciones_previas") or []:
        que = (s.get("que") or "").strip()
        if not que:
            continue
        fallas = ", ".join(x for x in (s.get("por_que_fallo") or []) if x)
        soluciones.append(f"Usó {que}" + (f": {fallas}" if fallas else ""))
    partes = [a.get("demografia"), a.get("emocion"), a.get("comportamiento"), ". ".join(soluciones)]
    descripcion = ". ".join(p.strip().rstrip(".") for p in partes if p and p.strip())
    return {"nombre": a["nombre"], "resumen": (a.get("deseo") or "")[:200], "descripcion": descripcion,
            "edad_rango": a.get("edad_rango") or "", "tono": a.get("tono") or "",
            "senales_visuales": list(a.get("situaciones") or []), "palabras_clave": list(a.get("palabras_clave") or [])}


def aprobar_avatar(cliente, avatar_id):
    """Crea la persona (origen `investigada`) o, si el avatar ya tiene una,
    la actualiza y la desarchiva. Solo sub-avatares. Devuelve persona_id."""
    a = avatar(cliente, avatar_id)
    if not a:
        raise ErrorDatos("Ese avatar no existe.")
    if a["tipo"] != "sub":
        raise ErrorDatos("Solo se aprueban los sub-avatares; el núcleo es una agrupación.")
    campos = persona_desde_avatar(a)
    extra = {"avatar_id": a["id"], "estudio_id": a["estudio_id"], "identidad": dict(a.get("identidad") or {}),
             "conciencia": dict(a.get("conciencia") or {}), "encaje_producto": a.get("encaje_producto") or "",
             "evidencia": list(a.get("evidencia") or [])}
    pid = a.get("persona_id")
    if pid and sprints_datos.persona(cliente, pid):
        sprints_datos.actualizar_persona(cliente, pid, archivada=False, extra=extra, **campos)
    else:
        n = len(sprints_datos.personas(cliente, incluir_archivadas=True))
        pid = sprints_datos.crear_persona(cliente, origen="investigada", color=COLORES[n % len(COLORES)], extra=extra, **campos)
    with db.conectar() as con:
        _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, {"estado": "aprobado", "persona_id": pid})
    return pid


def descartar_avatar(cliente, avatar_id):
    """Marca `descartado`; si ya tenía persona, la archiva (reversible)."""
    a = avatar(cliente, avatar_id)
    if not a or a["tipo"] != "sub":
        return False
    if a.get("persona_id"):
        sprints_datos.archivar_persona(cliente, a["persona_id"])
    with db.conectar() as con:
        return _actualizar(con, db.avatar, avatar_id, cliente, _AVATAR_COLS, {"estado": "descartado"})
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos.py tests/test_sprints_datos.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/datos.py
git add nicho/datos.py tests/test_nicho_datos.py
git commit -m "Nicho: avatares en datos (guardar generación conservando aprobados, aprobar crea persona investigada, descartar archiva)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 4: `nicho/fuentes/base.py` — contrato, normalización y registro

**Files:**
- Create: `nicho/fuentes/__init__.py`, `nicho/fuentes/base.py`
- Test: `tests/test_nicho_fuentes.py`

**Interfaces:**
- Produces (en `nicho.fuentes.base`): `CLAVES_COMENTARIO = ("fuente_id", "texto", "url", "contexto", "puntuacion", "fecha", "extra")`, `MAX_TEXTO = 2000`, `MIN_TEXTO = 3`, `MIN_CITA = 12`; `class ErrorFuente(Exception)` con `.usuario`; `limpiar_texto(texto) -> str`; `hash_texto(texto) -> str` (16 hex); `normalizar_comentario(d) -> dict|None`; `class Fuente` con `tipo`, `de_pago`, `probar()`, `estimar(params)`, `recolectar(params, avanzar=None)`.
- Produces (en `nicho.fuentes`): `REGISTRO = {"texto": ("nicho.fuentes.texto", "FuenteTexto"), "csv": ("nicho.fuentes.archivo", "FuenteArchivo")}`, `por_tipo(tipo) -> clase`, `tipos() -> tuple`, `NOMBRES = {"texto": "Texto pegado", "csv": "CSV o Excel", "reddit": "Reddit", "youtube": "YouTube", "apify": "Amazon / TikTok (Apify)"}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_fuentes.py`:

```python
from datetime import datetime

import pytest


def test_limpiar_y_hash():
    from nicho.fuentes import base
    assert base.limpiar_texto("  Hola\x00 \n\n mundo\t ya  ") == "Hola mundo ya"
    assert len(base.limpiar_texto("x" * 5000)) == base.MAX_TEXTO
    assert base.hash_texto("Hola   Mundo") == base.hash_texto("hola mundo") and len(base.hash_texto("a")) == 16


def test_normalizar_comentario():
    from nicho.fuentes import base
    c = base.normalizar_comentario({"texto": " La garrafa <b>pesa</b> ", "url": "https://r.com/x", "contexto": "Post: garrafas",
                                    "puntuacion": "12", "fecha": "2026-03-04T10:20:30Z", "extra": {"sub": "sweden"}})
    assert tuple(c) == base.CLAVES_COMENTARIO
    assert c["texto"] == "La garrafa <b>pesa</b>" and c["fuente_id"] == base.hash_texto("La garrafa <b>pesa</b>")
    assert c["url"] == "https://r.com/x" and c["puntuacion"] == 12 and c["fecha"] == "2026-03-04T10:20:30" and c["extra"] == {"sub": "sweden"}
    assert base.normalizar_comentario({"texto": "ab"}) is None
    assert base.normalizar_comentario({"texto": None}) is None
    c2 = base.normalizar_comentario({"fuente_id": " t1_abc ", "texto": "vale", "url": "javascript:x", "puntuacion": "muchos",
                                     "fecha": 1700000000, "extra": "no dict"})
    assert c2["fuente_id"] == "t1_abc" and c2["url"] is None and c2["puntuacion"] is None and c2["extra"] == {}
    assert c2["fecha"] == datetime.fromtimestamp(1700000000).strftime("%Y-%m-%dT%H:%M:%S")
    assert base.normalizar_comentario({"texto": "vale", "fecha": "2026-01-02"})["fecha"] == "2026-01-02T00:00:00"
    assert base.normalizar_comentario({"texto": "vale", "fecha": "ayer"})["fecha"] is None
    assert base.normalizar_comentario({"texto": "vale", "puntuacion": True})["puntuacion"] is None


def test_error_fuente_y_fuente_base():
    from nicho.fuentes import base
    e = base.ErrorFuente("Reddit no aceptó las llaves.")
    assert e.usuario == str(e) == "Reddit no aceptó las llaves."
    f = base.Fuente()
    assert f.probar()["ok"] is True and f.estimar({}) is None
    with pytest.raises(NotImplementedError):
        list(f.recolectar({}))


def test_registro_por_tipo():
    from nicho import fuentes
    assert fuentes.tipos() == ("texto", "csv")
    assert fuentes.por_tipo("texto").tipo == "texto" and fuentes.por_tipo("csv").tipo == "csv"
    with pytest.raises(KeyError):
        fuentes.por_tipo("magia")
    assert fuentes.NOMBRES["apify"].startswith("Amazon")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes'`.

- [ ] **Step 3: Escribir `nicho/fuentes/base.py`**

```python
"""
Contrato común de las fuentes de comentarios (spec §3.1). Toda fuente
(texto pegado, CSV/Excel, Reddit, YouTube, Apify) entrega dicts con las
MISMAS claves — `CLAVES_COMENTARIO` — y `normalizar_comentario` es el único
camino para construirlos: limpia el texto (sin caracteres de control,
espacios colapsados, máximo MAX_TEXTO), descarta textos de menos de
MIN_TEXTO caracteres, cae al hash del texto como `fuente_id`, valida la url,
castea puntuación y fecha. Nunca guarda el autor.

`ErrorFuente` es el único error que una fuente deja escapar hacia el
dashboard o el worker: `.usuario` (== `str(e)`) es un mensaje en español
apto para mostrar tal cual y NUNCA lleva llaves ni HTML ajeno.
"""
import hashlib
import re
from datetime import datetime

CLAVES_COMENTARIO = ("fuente_id", "texto", "url", "contexto", "puntuacion", "fecha", "extra")
MAX_TEXTO = 2000
MIN_TEXTO = 3
MIN_CITA = 12          # largo mínimo de una cita de evidencia (spec §4.3)

_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_RE_ESPACIOS = re.compile(r"\s+")
_RE_URL_HTTP = re.compile(r"^https?://", re.IGNORECASE)


class ErrorFuente(Exception):
    """Error mostrable al usuario. `usuario` es el mensaje en español (sin
    llaves, sin HTML) y `str(e)` devuelve exactamente lo mismo."""

    def __init__(self, usuario):
        self.usuario = str(usuario)
        super().__init__(self.usuario)


def limpiar_texto(texto):
    """Sin caracteres de control, espacios (incluidos saltos) colapsados a
    uno, recortado a MAX_TEXTO."""
    t = _RE_CONTROL.sub("", "" if texto is None else str(texto))
    return _RE_ESPACIOS.sub(" ", t).strip()[:MAX_TEXTO]


def hash_texto(texto):
    """Identidad de un comentario pegado: SHA-1 del texto en minúsculas con
    espacios colapsados, 16 hex. El mismo comentario pegado dos veces no duplica."""
    plano = _RE_ESPACIOS.sub(" ", "" if texto is None else str(texto)).strip().lower()
    return hashlib.sha1(plano.encode("utf-8")).hexdigest()[:16]


def _entero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(float(str(valor).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _fecha_iso(valor):
    """datetime, epoch (int/float) o texto ISO / 'YYYY-MM-DD' -> 'YYYY-MM-DDTHH:MM:SS'.
    Nunca lanza: una fecha ilegible es None (el comentario no se pierde por eso)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(float(valor)).strftime("%Y-%m-%dT%H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    t = str(valor).strip().replace(" ", "T", 1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def normalizar_comentario(d):
    """dict cualquiera -> dict con exactamente CLAVES_COMENTARIO, o None si el
    texto no alcanza MIN_TEXTO."""
    d = dict(d or {})
    texto = limpiar_texto(d.get("texto"))
    if len(texto) < MIN_TEXTO:
        return None
    url = ("" if d.get("url") is None else str(d.get("url"))).strip()
    if not _RE_URL_HTTP.match(url):
        url = None
    fuente_id = ("" if d.get("fuente_id") is None else str(d.get("fuente_id"))).strip() or hash_texto(texto)
    extra = d.get("extra")
    return {
        "fuente_id": fuente_id[:120],
        "texto": texto,
        "url": url[:500] if url else None,
        "contexto": limpiar_texto(d.get("contexto"))[:300] or None,
        "puntuacion": _entero(d.get("puntuacion")),
        "fecha": _fecha_iso(d.get("fecha")),
        "extra": dict(extra) if isinstance(extra, dict) else {},
    }


class Fuente:
    """Base de toda fuente. Las subclases fijan `tipo` (clave del registro en
    `nicho.fuentes.REGISTRO`) y `de_pago` (True muestra la puerta de costo).
    `recolectar(params, avanzar)` ITERA dicts ya normalizados; `avanzar(etapa,
    detalle)` es el callback de progreso que el worker traduce a `cola.reportar`."""
    tipo = None
    de_pago = False

    def probar(self):
        """Verifica llaves sin gastar. {"ok", "detalle"}."""
        return {"ok": True, "detalle": f"Fuente {self.tipo or 'base'} lista."}

    def estimar(self, params):
        """Solo las de pago: {"max_resultados", "usd"}. Las gratis devuelven None."""
        return None

    def recolectar(self, params, avanzar=None):
        raise NotImplementedError
```

- [ ] **Step 4: Escribir `nicho/fuentes/__init__.py`**

```python
"""
Registro de fuentes de comentarios por `tipo`, con carga perezosa (como
`conectores.por_tipo`): la Parte 2 agrega reddit, youtube y apify acá mismo.
"""
import importlib

REGISTRO = {
    "texto": ("nicho.fuentes.texto", "FuenteTexto"),
    "csv": ("nicho.fuentes.archivo", "FuenteArchivo"),
}
NOMBRES = {"texto": "Texto pegado", "csv": "CSV o Excel", "reddit": "Reddit", "youtube": "YouTube",
           "apify": "Amazon / TikTok (Apify)"}


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> la clase de la fuente. KeyError si el tipo no está registrado."""
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)
```

- [ ] **Step 5: Correr las pruebas de base y registro** (las de `por_tipo` fallan hasta las Tasks 5 y 6: correr solo las tres primeras)

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q -k "limpiar or normalizar or error_fuente"`
Expected: PASS (3 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile nicho/fuentes/__init__.py nicho/fuentes/base.py
git add nicho/fuentes/__init__.py nicho/fuentes/base.py tests/test_nicho_fuentes.py
git commit -m "Nicho: contrato de fuentes de comentarios (normalización, ErrorFuente, registro)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `nicho/fuentes/texto.py` — texto pegado

**Files:**
- Create: `nicho/fuentes/texto.py`
- Test: `tests/test_nicho_fuentes.py` (agregar)

**Interfaces:**
- Produces: `MODOS = ("lineas", "parrafos")`, `NOMBRES_MODO`, `partir_texto(texto, modo="lineas") -> list[str]`, `class FuenteTexto(Fuente)` con `tipo = "texto"` y `recolectar(params={"texto", "modo"})`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_fuentes.py`)

```python
def test_partir_texto_modos():
    from nicho.fuentes import texto
    pegado = "Primer comentario\n\nSegundo, que sigue\nen dos líneas\n\n\n  \nTercero"
    assert texto.partir_texto(pegado, "lineas") == ["Primer comentario", "Segundo, que sigue", "en dos líneas", "Tercero"]
    assert texto.partir_texto(pegado, "parrafos") == ["Primer comentario", "Segundo, que sigue en dos líneas", "Tercero"]
    assert texto.partir_texto("", "lineas") == [] and texto.partir_texto(None, "parrafos") == []
    assert texto.partir_texto("a\nb", "modo raro") == ["a", "b"]         # modo desconocido -> lineas


def test_fuente_texto_recolecta_normalizado():
    from nicho import fuentes
    lista = list(fuentes.por_tipo("texto")().recolectar({"texto": "Muy pesada la garrafa\nok\n\nGotea en el estante", "modo": "lineas"}))
    assert [c["texto"] for c in lista] == ["Muy pesada la garrafa", "Gotea en el estante"]     # "ok" no llega a MIN_TEXTO
    assert lista[0]["fuente_id"] and lista[0]["url"] is None and lista[0]["extra"] == {}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q -k "texto"`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.texto'`.

- [ ] **Step 3: Escribir `nicho/fuentes/texto.py`**

```python
"""
Fuente `texto` (spec §3.2): comentarios pegados a mano en un cuadro de texto.
`modo` = "lineas" (una línea por comentario) o "parrafos" (separados por una
línea en blanco; los saltos internos se vuelven espacios). Corre en la ruta,
sin worker. `fuente_id` = hash del texto (lo pone normalizar_comentario).
"""
import re

from nicho.fuentes.base import Fuente, normalizar_comentario

MODOS = ("lineas", "parrafos")
NOMBRES_MODO = {"lineas": "Una línea por comentario", "parrafos": "Separados por una línea en blanco"}
_RE_PARRAFO = re.compile(r"\n\s*\n")


def partir_texto(texto, modo="lineas"):
    t = "" if texto is None else str(texto).replace("\r\n", "\n").replace("\r", "\n")
    if modo == "parrafos":
        trozos = [" ".join(p.split()) for p in _RE_PARRAFO.split(t)]
    else:
        trozos = [l.strip() for l in t.split("\n")]
    return [x for x in trozos if x]


class FuenteTexto(Fuente):
    tipo = "texto"

    def recolectar(self, params, avanzar=None):
        params = dict(params or {})
        for trozo in partir_texto(params.get("texto"), params.get("modo") or "lineas"):
            c = normalizar_comentario({"texto": trozo})
            if c:
                yield c
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q -k "texto or registro"`
Expected: PASS salvo `test_registro_por_tipo` (falta `csv`, Task 6).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/fuentes/texto.py
git add nicho/fuentes/texto.py tests/test_nicho_fuentes.py
git commit -m "Nicho: fuente de texto pegado (líneas o párrafos)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `nicho/fuentes/archivo.py` — CSV y Excel

**Files:**
- Create: `nicho/fuentes/archivo.py`
- Test: `tests/test_nicho_fuentes.py` (agregar)

**Interfaces:**
- Produces: `MAX_BYTES = 5 * 1024 * 1024`, `MAX_FILAS = 5000`, `COLUMNAS_TEXTO`, `COLUMNAS_URL`, `COLUMNAS_PUNTUACION`, `COLUMNAS_FECHA`, `detectar_columnas(encabezados, filas) -> {"texto": int, "url": int|None, "puntuacion": int|None, "fecha": int|None}`, `leer_archivo(nombre, contenido: bytes) -> list[dict]` (lanza `ErrorFuente`), `class FuenteArchivo(Fuente)` con `tipo = "csv"` y `recolectar(params={"nombre", "contenido"})`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_fuentes.py`)

```python
def _xlsx(filas):
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_leer_csv_detecta_columnas():
    from nicho.fuentes import archivo
    csv = "Review;Rating;Date;Link\nLa garrafa pesa y gotea;4;2026-01-02;https://a.com/1\nab;5;;\nSe pega la tapa;;;\n"
    lista = archivo.leer_archivo("resenas.csv", csv.encode("utf-8"))
    assert [c["texto"] for c in lista] == ["La garrafa pesa y gotea", "Se pega la tapa"]
    assert lista[0]["puntuacion"] == 4 and lista[0]["fecha"] == "2026-01-02T00:00:00" and lista[0]["url"] == "https://a.com/1"
    assert lista[1]["puntuacion"] is None and lista[1]["url"] is None


def test_leer_csv_sin_encabezado_conocido_usa_columna_mas_larga():
    from nicho.fuentes import archivo
    csv = "id,cosa,otra\n1,Un comentario bastante largo sobre la garrafa que pesa,x\n2,Otro comentario igual de largo sobre la tapa pegajosa,y\n"
    assert [c["texto"] for c in archivo.leer_archivo("x.csv", csv.encode())] == [
        "Un comentario bastante largo sobre la garrafa que pesa", "Otro comentario igual de largo sobre la tapa pegajosa"]


def test_leer_xlsx():
    from nicho.fuentes import archivo
    contenido = _xlsx([["texto", "likes"], ["Muy pesada, no la vuelvo a comprar", 12], [None, 3], ["Gotea en el estante", "7"]])
    lista = archivo.leer_archivo("r.xlsx", contenido)
    assert [(c["texto"], c["puntuacion"]) for c in lista] == [("Muy pesada, no la vuelvo a comprar", 12), ("Gotea en el estante", 7)]


def test_leer_archivo_errores():
    from nicho.fuentes import archivo, base
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.txt", b"hola")
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"a" * (archivo.MAX_BYTES + 1))
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"")
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"a,b\n1,2\n3,4\n")            # sin columna de texto
    muchas = "texto\n" + "\n".join(f"comentario {i} largo de verdad" for i in range(archivo.MAX_FILAS + 1))
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", muchas.encode())
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.xlsx", b"no es un excel")


def test_fuente_archivo_recolecta():
    from nicho import fuentes
    lista = list(fuentes.por_tipo("csv")().recolectar({"nombre": "r.csv", "contenido": b"comentario\nLa tapa se pega siempre\n"}))
    assert lista[0]["texto"] == "La tapa se pega siempre"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q -k "archivo or xlsx or csv or registro"`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.archivo'`.

- [ ] **Step 3: Escribir `nicho/fuentes/archivo.py`**

```python
"""
Fuente `csv` (spec §3.2): un archivo .csv (delimitador detectado con
csv.Sniffer) o .xlsx (primera hoja, openpyxl) con fila de encabezados. La
columna de texto se reconoce por nombre (COLUMNAS_TEXTO) o, si no hay, es la
de mayor largo medio; url, puntuación y fecha son opcionales por nombre.
Máximo MAX_BYTES y MAX_FILAS. Corre en la ruta, sin worker.
"""
import csv
import io
import os

from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

MAX_BYTES = 5 * 1024 * 1024
MAX_FILAS = 5000
COLUMNAS_TEXTO = ("texto", "comentario", "comment", "review", "body", "content", "text", "reseña", "resena",
                  "mensaje", "opinion", "opinión")
COLUMNAS_URL = ("url", "link", "enlace")
COLUMNAS_PUNTUACION = ("score", "likes", "votos", "puntuacion", "puntuación", "rating", "upvotes")
COLUMNAS_FECHA = ("fecha", "date", "created", "published")
_MIN_LARGO_MEDIO = 10        # menos que esto no parece una columna de comentarios


def _decodificar(contenido):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ErrorFuente("No pude leer el archivo como texto (¿es un CSV?).")


def _sin_vacias(filas):
    return [f for f in filas if any(str(c or "").strip() for c in f)]


def _filas_csv(contenido):
    texto = _decodificar(contenido)
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    filas = _sin_vacias(list(csv.reader(io.StringIO(texto), dialecto)))
    if not filas:
        raise ErrorFuente("El archivo está vacío.")
    return [str(c or "").strip() for c in filas[0]], filas[1:]


def _filas_xlsx(contenido):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — openpyxl lanza de todo con un archivo dañado
        raise ErrorFuente("No pude abrir el Excel (¿está dañado o protegido?).") from None
    hoja = wb.worksheets[0]
    filas = _sin_vacias([["" if v is None else str(v) for v in fila] for fila in hoja.iter_rows(values_only=True)])
    if not filas:
        raise ErrorFuente("El Excel está vacío.")
    return [c.strip() for c in filas[0]], filas[1:]


def _indice_por_nombre(encabezados, nombres):
    bajos = [e.strip().lower() for e in encabezados]
    for n in nombres:
        if n in bajos:
            return bajos.index(n)
    return None


def detectar_columnas(encabezados, filas):
    texto = _indice_por_nombre(encabezados, COLUMNAS_TEXTO)
    if texto is None:
        mejor, mejor_largo = None, 0.0
        for i in range(len(encabezados)):
            largos = [len(str(f[i])) for f in filas[:200] if i < len(f) and str(f[i] or "").strip()]
            media = sum(largos) / len(largos) if largos else 0.0
            if media > mejor_largo:
                mejor, mejor_largo = i, media
        if mejor is None or mejor_largo < _MIN_LARGO_MEDIO:
            raise ErrorFuente("No encontré una columna con comentarios (ponle «texto» o «comentario» de encabezado).")
        texto = mejor
    return {"texto": texto, "url": _indice_por_nombre(encabezados, COLUMNAS_URL),
            "puntuacion": _indice_por_nombre(encabezados, COLUMNAS_PUNTUACION),
            "fecha": _indice_por_nombre(encabezados, COLUMNAS_FECHA)}


def leer_archivo(nombre, contenido):
    """-> comentarios normalizados. ErrorFuente si el archivo no sirve."""
    contenido = contenido or b""
    if len(contenido) > MAX_BYTES:
        raise ErrorFuente("El archivo pesa más de 5 MB; pártelo.")
    ext = os.path.splitext(nombre or "")[1].lower()
    if ext == ".csv":
        encabezados, filas = _filas_csv(contenido)
    elif ext in (".xlsx", ".xlsm"):
        encabezados, filas = _filas_xlsx(contenido)
    else:
        raise ErrorFuente("Solo acepto archivos .csv o .xlsx.")
    if len(filas) > MAX_FILAS:
        raise ErrorFuente(f"El archivo tiene más de {MAX_FILAS} filas; pártelo.")
    cols = detectar_columnas(encabezados, filas)

    def celda(f, i):
        return f[i] if i is not None and i < len(f) else None

    salida = []
    for f in filas:
        c = normalizar_comentario({"texto": celda(f, cols["texto"]), "url": celda(f, cols["url"]),
                                   "puntuacion": celda(f, cols["puntuacion"]), "fecha": celda(f, cols["fecha"])})
        if c:
            salida.append(c)
    return salida


class FuenteArchivo(Fuente):
    tipo = "csv"

    def recolectar(self, params, avanzar=None):
        params = dict(params or {})
        yield from leer_archivo(params.get("nombre"), params.get("contenido"))
```

- [ ] **Step 4: Correr todas las pruebas de fuentes**

Run: `venv/bin/python3 -m pytest tests/test_nicho_fuentes.py -q`
Expected: PASS (todas, incluida `test_registro_por_tipo`).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/fuentes/archivo.py
git add nicho/fuentes/archivo.py tests/test_nicho_fuentes.py
git commit -m "Nicho: fuente CSV/Excel con detección de columnas y límites

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 7: `nicho/avatares.py` — selección de comentarios y estimado de costo

**Files:**
- Create: `nicho/avatares.py` (esta tarea deja constantes, `seleccionar`, precios, `estimar_costo`, `costo_real`; las Tasks 8 y 9 agregan el resto al mismo archivo)
- Test: `tests/test_nicho_avatares.py`

**Interfaces:**
- Produces (en `nicho.avatares`): `MIN_COMENTARIOS = 20`, `MAX_COMENTARIOS = 600`, `MAX_CARACTERES = 250_000`, `MAX_NUCLEOS = 5`, `TOKENS_POR_CARACTER = 1 / 3.5`, `TOKENS_PROMPT = 800`, `TOKENS_SALIDA_ESTIMADO_NUCLEOS = 1500`, `TOKENS_SALIDA_ESTIMADO_SUBS = 3000`, `MAX_TOKENS_NUCLEOS = 4000`, `MAX_TOKENS_SUBS = 8000`, `PRECIOS_USD_POR_MILLON`, `IDIOMAS`; `seleccionar(comentarios, max_n=MAX_COMENTARIOS, max_caracteres=MAX_CARACTERES) -> list[dict]`; `estimar_costo(comentarios, modelo=None) -> {"comentarios", "tokens_entrada", "tokens_salida", "usd", "referencia", "modelo", "suficientes"}`; `costo_real(tokens_entrada, tokens_salida, modelo=None) -> float`; `modelo_actual() -> str`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_avatares.py`:

```python
import json

import pytest


def _c(i, fuente="texto", puntuacion=None, fecha=None, texto=None, excluido=False):
    return {"id": i, "fuente": fuente, "puntuacion": puntuacion, "fecha": fecha, "excluido": excluido,
            "contexto": None, "texto": texto or f"Comentario {i} sobre la garrafa que pesa y gotea en el estante."}


def test_seleccionar_excluye_ordena_y_alterna_fuentes():
    from nicho import avatares
    lista = [_c(1, "texto", puntuacion=1), _c(2, "texto", puntuacion=9), _c(3, "reddit", puntuacion=5),
             _c(4, "reddit", puntuacion=5, fecha="2026-02-01"), _c(5, "youtube", excluido=True), _c(6, "youtube")]
    sel = avatares.seleccionar(lista)
    assert [c["id"] for c in sel] == [4, 2, 6, 3, 1]      # ronda reddit/texto/youtube; dentro: puntuación desc, fecha desc, id
    assert [c["id"] for c in avatares.seleccionar(lista, max_n=2)] == [4, 2]
    corto = avatares.seleccionar(lista, max_caracteres=len(lista[0]["texto"]) * 2 + 1)
    assert len(corto) == 2
    assert avatares.seleccionar([]) == []


def test_estimar_costo_y_costo_real(monkeypatch):
    from nicho import avatares
    lista = [_c(i, texto="x" * 350) for i in range(1, 21)]           # 20 comentarios × 350 caracteres = 7 000 chars
    e = avatares.estimar_costo(lista, modelo="claude-sonnet-5")
    tokens_texto = int(7000 * avatares.TOKENS_POR_CARACTER)
    assert e["comentarios"] == 20 and e["suficientes"] is True and e["referencia"] is False and e["modelo"] == "claude-sonnet-5"
    assert e["tokens_entrada"] == tokens_texto * 2 + avatares.TOKENS_PROMPT * (1 + avatares.MAX_NUCLEOS)
    assert e["tokens_salida"] == avatares.TOKENS_SALIDA_ESTIMADO_NUCLEOS + avatares.TOKENS_SALIDA_ESTIMADO_SUBS * avatares.MAX_NUCLEOS
    esperado = (e["tokens_entrada"] * 2.0 + e["tokens_salida"] * 10.0) / 1e6
    assert e["usd"] >= esperado and e["usd"] - esperado < 0.01           # redondeado hacia arriba al centavo
    assert avatares.estimar_costo(lista[:5], modelo="claude-sonnet-5")["suficientes"] is False
    raro = avatares.estimar_costo(lista, modelo="claude-desconocido-9")
    assert raro["referencia"] is True and raro["usd"] >= e["usd"]         # precio de referencia = el más caro
    assert avatares.costo_real(1_000_000, 100_000, modelo="claude-sonnet-5") == pytest.approx(3.0)
    monkeypatch.setattr(avatares, "modelo_actual", lambda: "claude-haiku-4-5")
    assert avatares.costo_real(1_000_000, 0) == pytest.approx(1.0) and avatares.estimar_costo(lista)["modelo"] == "claude-haiku-4-5"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.avatares'`.

- [ ] **Step 3: Escribir `nicho/avatares.py` (primera parte)**

```python
"""
Generación de avatares con Claude (spec §4): dos pasadas — núcleos por deseo
y, por cada núcleo, sub-avatares con los campos de las dos plantillas del
cliente (doc "Desire-Based Core Avatar" y hoja "Personas") — con citas
verificadas contra el comentario real. `_llamar` es la única función que
toca la API: las pruebas la reemplazan. El modelo es el del proyecto
(`generador_prompts.MODEL`); los precios de PRECIOS_USD_POR_MILLON están
verificados contra la referencia de Anthropic (tabla del 2026-06-24).
"""
import json
import math
import re

import marca
import proyectos
from nicho import datos
from nicho.fuentes.base import MIN_CITA

MIN_COMENTARIOS = 20
MAX_COMENTARIOS = 600
MAX_CARACTERES = 250_000
MAX_NUCLEOS = 5
MAX_SUBS_POR_NUCLEO = 4
TOKENS_POR_CARACTER = 1 / 3.5          # conservador para español
TOKENS_PROMPT = 800                    # instrucciones por llamada
TOKENS_SALIDA_ESTIMADO_NUCLEOS = 1500  # lo que suele ocupar la pasada 1
TOKENS_SALIDA_ESTIMADO_SUBS = 3000     # por núcleo, pasada 2
MAX_TOKENS_NUCLEOS = 4000              # tope de salida real (no es costo: es el corte)
MAX_TOKENS_SUBS = 8000

# USD por millón de tokens (entrada, salida). Referencia de Anthropic, 2026-06-24.
PRECIOS_USD_POR_MILLON = {
    "claude-sonnet-5": {"entrada": 2.0, "salida": 10.0},
    "claude-opus-5": {"entrada": 5.0, "salida": 25.0},
    "claude-haiku-4-5": {"entrada": 1.0, "salida": 5.0},
}
IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués", "sv": "sueco", "fr": "francés", "de": "alemán",
           "it": "italiano"}


class AnalisisInvalido(RuntimeError):
    """Claude no devolvió lo pedido (JSON roto, claves faltantes, corte)."""


def modelo_actual():
    from generador_prompts import MODEL
    return MODEL


# ----------------------------------------------------------- selección ---

def seleccionar(comentarios, max_n=MAX_COMENTARIOS, max_caracteres=MAX_CARACTERES):
    """Los que entran a Claude (spec §4.1): fuera los excluidos; dentro de
    cada fuente por puntuación desc, fecha desc, id asc; se toman en ronda
    entre fuentes hasta llenar el primer tope. Un comentario que no cabe en
    los caracteres se salta (no corta la ronda)."""
    por_fuente = {}
    for c in comentarios or []:
        if c.get("excluido"):
            continue
        por_fuente.setdefault(c.get("fuente") or "texto", []).append(c)
    for lista in por_fuente.values():
        # tres ordenamientos estables = (puntuación desc, fecha desc, id asc)
        lista.sort(key=lambda c: int(c.get("id") or 0))
        lista.sort(key=lambda c: c.get("fecha") or "", reverse=True)
        lista.sort(key=lambda c: -(c.get("puntuacion") or 0))
    colas = [iter(l) for _, l in sorted(por_fuente.items())]
    salida, caracteres = [], 0
    while colas and len(salida) < max_n:
        siguientes = []
        for it in colas:
            if len(salida) >= max_n:
                break
            c = next(it, None)
            if c is None:
                continue
            siguientes.append(it)
            largo = len(c.get("texto") or "")
            if caracteres + largo > max_caracteres:
                continue
            salida.append(c)
            caracteres += largo
        colas = siguientes
    return salida


# -------------------------------------------------------------- costo ---

def _precios(modelo):
    """(precios, es_referencia). Modelo desconocido -> el más caro de la tabla."""
    if modelo in PRECIOS_USD_POR_MILLON:
        return PRECIOS_USD_POR_MILLON[modelo], False
    caro = max(PRECIOS_USD_POR_MILLON.values(), key=lambda p: p["entrada"] + p["salida"])
    return caro, True


def costo_real(tokens_entrada, tokens_salida, modelo=None):
    precios, _ = _precios(modelo or modelo_actual())
    return round((tokens_entrada * precios["entrada"] + tokens_salida * precios["salida"]) / 1e6, 4)


def estimar_costo(comentarios, modelo=None):
    """Precio ANTES de gastar (spec §4.4): la entrada se cuenta dos veces
    (pasada 1 y repartida en la pasada 2) más el prompt por llamada; la
    salida es lo esperado, con MAX_NUCLEOS en la pasada 2. Redondeado hacia
    arriba al centavo."""
    modelo = modelo or modelo_actual()
    sel = seleccionar(comentarios)
    caracteres = sum(len(c.get("texto") or "") for c in sel)
    tokens_texto = int(caracteres * TOKENS_POR_CARACTER)
    entrada = tokens_texto * 2 + TOKENS_PROMPT * (1 + MAX_NUCLEOS)
    salida = TOKENS_SALIDA_ESTIMADO_NUCLEOS + TOKENS_SALIDA_ESTIMADO_SUBS * MAX_NUCLEOS
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100
    return {"comentarios": len(sel), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd,
            "referencia": referencia, "modelo": modelo, "suficientes": len(sel) >= MIN_COMENTARIOS}
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q`
Expected: PASS (2 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/avatares.py
git add nicho/avatares.py tests/test_nicho_avatares.py
git commit -m "Nicho: selección de comentarios en ronda por fuente y estimado de costo por tokens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `nicho/avatares.py` — prompts, parseo y verificación de evidencia

**Files:**
- Modify: `nicho/avatares.py` (agregar)
- Test: `tests/test_nicho_avatares.py` (agregar)

**Interfaces:**
- Consumes: `datos.NIVELES_CONCIENCIA`, `datos.BASES`, `datos.CLAVES_IDENTIDAD`, `datos.validar_campos_avatar`, `MIN_CITA`.
- Produces: `PROMPT_NUCLEOS`, `PROMPT_SUBS` (plantillas `str.format`), `nombre_idioma(codigo) -> str`, `lineas_comentarios(comentarios) -> str`, `armar_prompt_nucleos(estudio, comentarios, marca_nombre="") -> str`, `armar_prompt_subs(estudio, nucleo, comentarios, guia="", marca_nombre="") -> str`, `parsear_nucleos(texto, ids_validos) -> list[dict]` (cada uno `{"nombre", "deseo", "resumen", "comentarios": [ids]}`), `parsear_subs(texto) -> list[dict]` (claves de `AVATAR_EDITABLES` + `evidencia`), `verificar_evidencia(sub, comentarios_por_id) -> dict` (agrega `sin_evidencia`).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_avatares.py`)

```python
NUCLEOS_JSON = {"nucleos": [
    {"nombre": "Lavar sin cargar peso", "deseo": "Quiero que lavar sea fácil y que limpie bien", "resumen": "Gente cansada de garrafas", "comentarios": [1, 2, 2, 99, "3"]},
    {"nombre": "Repetido", "deseo": "Quiero lo mismo", "resumen": "", "comentarios": [1]},
    {"nombre": "", "deseo": "sin nombre", "comentarios": [4]},
    {"nombre": "Sin comentarios válidos", "deseo": "Quiero", "comentarios": [77]},
]}
SUB_JSON = {"sub_avatares": [
    {"base": "experiencia_producto", "nombre": "Ana / La que carga la garrafa", "deseo": "Quiero lavar sin cargar",
     "demografia": "", "edad_rango": "", "emocion": "Frustración cada semana",
     "identidad": {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "una casa que funcione"},
     "soluciones_previas": [{"que": "Detergente líquido de marca", "por_que_fallo": ["Pesado de cargar", "Gotea en el estante"]}],
     "situaciones": ["Cargando garrafas de 2 litros desde el súper"], "comportamiento": "Sigue comprando líquido porque es lo probado",
     "conciencia": {"nivel": "consciente_del_problema", "detalle": "Sabe que pesa, no sabe que hay otra cosa"},
     "encaje_producto": "Cápsulas: nada que cargar", "tono": "Directo, con humor cansado", "palabras_clave": ["garrafa", "peso"],
     "evidencia": [{"comentario_id": 1, "cita": "la garrafa PESA demasiado"}, {"comentario_id": 2, "cita": "esto no lo dijo nadie"},
                   {"comentario_id": 1, "cita": "corta"}, {"comentario_id": 5, "cita": "la garrafa pesa demasiado"}]},
    {"base": "otra", "nombre": "Sin deseo", "deseo": ""},
    {"base": "emocion", "nombre": "Sin evidencia", "deseo": "Quiero algo", "conciencia": {"nivel": "inventado"}, "evidencia": []},
]}


def test_parsear_nucleos():
    from nicho import avatares
    n = avatares.parsear_nucleos("```json\n" + json.dumps(NUCLEOS_JSON) + "\n```", ids_validos={1, 2, 3, 4})
    assert [x["nombre"] for x in n] == ["Lavar sin cargar peso"]
    assert n[0]["comentarios"] == [1, 2, 3] and n[0]["resumen"] == "Gente cansada de garrafas"
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos("no es json", {1})
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos(json.dumps({"nucleos": []}), {1})
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos(json.dumps({"otra": 1}), {1})
    assert len(avatares.parsear_nucleos(json.dumps({"nucleos": [{"nombre": f"N{i}", "deseo": "Q", "comentarios": [i]} for i in range(9)]}), set(range(9)))) == avatares.MAX_NUCLEOS


def test_parsear_subs_y_verificar_evidencia():
    from nicho import avatares
    subs = avatares.parsear_subs(json.dumps(SUB_JSON))
    assert [s["nombre"] for s in subs] == ["Ana / La que carga la garrafa", "Sin evidencia"]
    s = subs[0]
    assert s["base"] == "experiencia_producto" and s["conciencia"]["nivel"] == "consciente_del_problema"
    assert s["soluciones_previas"][0]["por_que_fallo"] == ["Pesado de cargar", "Gotea en el estante"] and s["palabras_clave"] == ["garrafa", "peso"]
    assert len(s["evidencia"]) == 4
    assert subs[1]["base"] == "emocion" and subs[1]["conciencia"] == {"nivel": "", "detalle": ""} and subs[1]["identidad"] == {"quiere_que_vean": "", "cree_de_si": "", "quiere_lograr": ""}
    por_id = {1: _c(1, texto="Sí, la garrafa   pesa demasiado, gotea y la tapa se pega."), 2: _c(2, texto="Otro comentario cualquiera.")}
    v = avatares.verificar_evidencia(s, por_id)
    assert v["evidencia"] == [{"comentario_id": 1, "cita": "la garrafa PESA demasiado"}] and v["sin_evidencia"] is False
    v2 = avatares.verificar_evidencia(subs[1], por_id)
    assert v2["evidencia"] == [] and v2["sin_evidencia"] is True
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_subs(json.dumps({"sub_avatares": [{"nombre": "", "deseo": ""}]}))


def test_prompts_incluyen_contexto():
    from nicho import avatares
    estudio = {"nombre": "Detergente", "producto": "Cápsulas sin plástico", "tema": "lavar en casa, Suecia", "idioma": "sv"}
    comentarios = [_c(1, "reddit", puntuacion=34, texto="La garrafa pesa demasiado"), _c(2, texto="Gotea")]
    comentarios[0]["contexto"] = "Foot pains thread"
    p1 = avatares.armar_prompt_nucleos(estudio, comentarios, marca_nombre="Happy Wash")
    for frag in ("Happy Wash", "Cápsulas sin plástico", "lavar en casa, Suecia", "[1] (reddit · 34 · Foot pains thread) La garrafa pesa demasiado",
                 "[2] (texto) Gotea", "sueco", str(avatares.MAX_NUCLEOS), '"nucleos"'):
        assert frag in p1, frag
    nucleo = {"nombre": "Lavar sin cargar", "deseo": "Quiero lavar sin cargar", "resumen": "Gente cansada"}
    p2 = avatares.armar_prompt_subs(estudio, nucleo, comentarios[:1], guia="Luz natural, tono cercano", marca_nombre="Happy Wash")
    for frag in ("Lavar sin cargar", "Quiero lavar sin cargar", "Gente cansada", "Luz natural, tono cercano", "Beliefs about self",
                 "consciente_del_problema", '"sub_avatares"', "[1] (reddit · 34 · Foot pains thread) La garrafa pesa demasiado", "sueco"):
        assert frag in p2, frag
    assert "[2]" not in p2
    assert avatares.nombre_idioma("xx") == "xx" and avatares.nombre_idioma("es") == "español"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q`
Expected: FAIL con `AttributeError: module 'nicho.avatares' has no attribute 'parsear_nucleos'`.

- [ ] **Step 3: Agregar prompts, parseo y evidencia a `nicho/avatares.py`**

```python
# ------------------------------------------------------------- prompts ---

PROMPT_NUCLEOS = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Nicho o tema investigado: {tema}

Abajo hay {n} comentarios reales de personas (reseñas, foros y redes), cada uno con su número entre corchetes, la fuente y, si la hay, su puntuación y el título de donde salió. Agrúpalos por el DESEO de fondo que expresan: qué quieren lograr o evitar, más allá del producto concreto. Devuelve de 2 a {max_nucleos} avatares núcleo, distintos entre sí.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"nucleos": [{{"nombre": "2 a 5 palabras", "deseo": "una frase en primera persona que empiece por «Quiero»", "resumen": "quiénes son y qué comparten, 30 a 60 palabras", "comentarios": [números de los comentarios que pertenecen a este núcleo]}}]}}

Reglas: cada comentario va en un solo núcleo, o en ninguno si no aporta; no inventes nada que los comentarios no digan; escribe todo en {idioma}.

COMENTARIOS:
{comentarios}"""

PROMPT_SUBS = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Guía de la marca: {guia}
Nicho o tema investigado: {tema}

Avatar núcleo: {nucleo_nombre} — deseo: «{nucleo_deseo}». {nucleo_resumen}

Abajo están los comentarios reales de este núcleo, numerados. Describe de 2 a {max_subs} sub-avatares: personas concretas y distintas entre sí dentro de este deseo. Al menos uno con base "emocion" (lo que más lo define es lo que siente) y al menos uno con base "experiencia_producto" (lo que más lo define es lo que ya usó y le falló), si los comentarios lo permiten.

Responde SOLO con un objeto JSON, sin texto antes ni después, con esta forma:
{{"sub_avatares": [{{
  "base": "emocion" o "experiencia_producto",
  "nombre": "Nombre / arquetipo, por ejemplo «Melissa / La que regala con cabeza»",
  "deseo": "en primera persona",
  "demografia": "Demographics (ASL): edad, género, dónde vive, momento de vida. SOLO si los comentarios dan señales; si no, cadena vacía",
  "edad_rango": "por ejemplo 30-45, o cadena vacía si no hay señales",
  "emocion": "la emoción dominante, una línea",
  "identidad": {{"quiere_que_vean": "What are some of the characteristics your prospect wants others to see in them?", "cree_de_si": "Beliefs about self", "quiere_lograr": "What does the prospect want to achieve in society?"}},
  "soluciones_previas": [{{"que": "What are other solutions they have tried and failed at? (una por elemento)", "por_que_fallo": ["Reason for failure with those solutions: 3 a 5 problemas concretos"]}}],
  "situaciones": ["2 a 4 escenas concretas de su día a día"],
  "comportamiento": "qué hace hoy y por qué",
  "conciencia": {{"nivel": "uno de: {niveles}", "detalle": "una línea que lo justifica"}},
  "encaje_producto": "How does your product help them achieve that status/characteristics?",
  "tono": "cómo habla esta gente, una línea",
  "palabras_clave": ["3 a 6 palabras"],
  "evidencia": [{{"comentario_id": número, "cita": "fragmento LITERAL copiado del comentario; 2 a 5 citas por sub-avatar"}}]
}}]}}

Reglas: escribe en {idioma}, salvo las citas, que se copian tal cual en el idioma en que la gente escribió; no inventes datos; cada cita debe aparecer palabra por palabra en el comentario indicado.

COMENTARIOS:
{comentarios}"""


def nombre_idioma(codigo):
    return IDIOMAS.get((codigo or "").lower(), codigo or "es")


def _linea(c):
    partes = [c.get("fuente") or "texto"]
    if c.get("puntuacion") is not None:
        partes.append(str(c["puntuacion"]))
    if c.get("contexto"):
        partes.append(str(c["contexto"])[:80])
    return f"[{c['id']}] ({' · '.join(partes)}) {c.get('texto') or ''}"


def lineas_comentarios(comentarios):
    return "\n".join(_linea(c) for c in comentarios)


def armar_prompt_nucleos(estudio, comentarios, marca_nombre=""):
    return PROMPT_NUCLEOS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        tema=(estudio.get("tema") or "").strip() or "(sin describir)", n=len(comentarios), max_nucleos=MAX_NUCLEOS,
        idioma=nombre_idioma(estudio.get("idioma")), comentarios=lineas_comentarios(comentarios))


def armar_prompt_subs(estudio, nucleo, comentarios, guia="", marca_nombre=""):
    return PROMPT_SUBS.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        guia=(guia or "").strip() or "(sin guía de estilo todavía)", tema=(estudio.get("tema") or "").strip() or "(sin describir)",
        nucleo_nombre=nucleo.get("nombre") or "", nucleo_deseo=nucleo.get("deseo") or "", nucleo_resumen=nucleo.get("resumen") or "",
        max_subs=MAX_SUBS_POR_NUCLEO, niveles=", ".join(datos.NIVELES_CONCIENCIA), idioma=nombre_idioma(estudio.get("idioma")),
        comentarios=lineas_comentarios(comentarios))


# -------------------------------------------------------------- parseo ---

def _json_objeto(texto):
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        data = json.loads(t)
    except ValueError:
        ini, fin = t.find("{"), t.rfind("}")
        if ini < 0 or fin <= ini:
            raise AnalisisInvalido("Claude no devolvió JSON.")
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError as e:
            raise AnalisisInvalido(f"JSON inválido: {e}")
    if not isinstance(data, dict):
        raise AnalisisInvalido("El JSON no es un objeto.")
    return data


def _str(v, largo=None):
    s = "" if v is None else str(v).strip()
    return s[:largo] if largo else s


def parsear_nucleos(texto, ids_validos):
    """-> hasta MAX_NUCLEOS núcleos con nombre, deseo, resumen y sus ids de
    comentario (solo válidos; un id repetido se queda en el primer núcleo).
    Un núcleo sin nombre, sin deseo o sin comentarios válidos se descarta."""
    data = _json_objeto(texto)
    crudos = data.get("nucleos")
    if not isinstance(crudos, list):
        raise AnalisisInvalido("El JSON no trae la lista «nucleos».")
    ids_validos = set(ids_validos)
    usados, limpios = set(), []
    for c in crudos:
        if len(limpios) >= MAX_NUCLEOS:
            break
        if not isinstance(c, dict):
            continue
        nombre, deseo = _str(c.get("nombre"), 120), _str(c.get("deseo"), 300)
        if not nombre or not deseo:
            continue
        ids = []
        for x in c.get("comentarios") or []:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i in ids_validos and i not in usados:
                usados.add(i)
                ids.append(i)
        if not ids:
            continue
        limpios.append({"nombre": nombre, "deseo": deseo, "resumen": _str(c.get("resumen"), 1500), "comentarios": ids})
    if not limpios:
        raise AnalisisInvalido("Ningún núcleo venía completo.")
    return limpios


def parsear_subs(texto):
    """-> sub-avatares con las claves de datos.AVATAR_EDITABLES + evidencia
    (sin verificar todavía). Sin nombre o sin deseo se descarta; el resto lo
    normaliza datos.validar_campos_avatar (base, conciencia, listas, largos)."""
    data = _json_objeto(texto)
    crudos = data.get("sub_avatares")
    if not isinstance(crudos, list):
        raise AnalisisInvalido("El JSON no trae la lista «sub_avatares».")
    limpios = []
    for c in crudos[:MAX_SUBS_POR_NUCLEO + 2]:
        if not isinstance(c, dict):
            continue
        if not _str(c.get("nombre")) or not _str(c.get("deseo")):
            continue
        campos = {k: c.get(k) for k in datos.AVATAR_EDITABLES}
        campos["evidencia"] = c.get("evidencia")
        limpios.append(datos.validar_campos_avatar(campos))
    if not limpios:
        raise AnalisisInvalido("Ningún sub-avatar venía completo.")
    return limpios


# ----------------------------------------------------------- evidencia ---

_RE_BLANCOS = re.compile(r"\s+")


def _plano(t):
    return _RE_BLANCOS.sub(" ", (t or "")).strip().lower()


def verificar_evidencia(sub, comentarios_por_id):
    """Una cita vale si es fragmento literal (sin mayúsculas ni espacios
    múltiples, mínimo MIN_CITA caracteres) del comentario que dice. Las que
    no aparecen se descartan; sin ninguna, `sin_evidencia=True` (no se borra)."""
    validas = []
    for e in sub.get("evidencia") or []:
        c = comentarios_por_id.get(e.get("comentario_id"))
        cita = _plano(e.get("cita"))
        if c and len(cita) >= MIN_CITA and cita in _plano(c.get("texto")):
            validas.append({"comentario_id": c["id"], "cita": _str(e.get("cita"), 500)})
    return {**sub, "evidencia": validas, "sin_evidencia": not validas}
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q`
Expected: PASS (5 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/avatares.py
git add nicho/avatares.py tests/test_nicho_avatares.py
git commit -m "Nicho: prompts de las dos pasadas, parseo del JSON y verificación literal de las citas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 9: `nicho/avatares.py` — `generar` (las dos pasadas, orquestadas)

**Files:**
- Modify: `nicho/avatares.py` (agregar `_llamar` y `generar`)
- Test: `tests/test_nicho_avatares.py` (agregar)

**Interfaces:**
- Consumes: `datos.estudio`, `datos.comentarios_para_generar`, `marca.guia_efectiva(cliente)`, `proyectos.nombre_visible(cliente)`; la SDK `anthropic` (solo dentro de `_llamar`).
- Produces: `ETAPA_NUCLEOS = "Agrupando deseos"`, `ETAPA_SUBS = "Armando sub-avatares"`; `_llamar(texto, max_tokens) -> (texto_respuesta, tokens_entrada, tokens_salida)`; `generar(cliente, estudio_id, avanzar=None) -> {"nucleos": [dict con "sub_avatares" y opcional "error"], "resumen": {...}}` donde `resumen` trae `comentarios, nucleos, subs, con_evidencia, sin_evidencia, errores, tokens_entrada, tokens_salida, usd, modelo`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_avatares.py`)

```python
def _estudio_listo(datos, n=25):
    eid = datos.crear_estudio("acme", "Detergente", producto="Cápsulas", tema="lavar sin cargar", idioma="es")
    datos.agregar_comentarios("acme", eid, "texto", [
        {"fuente_id": f"c{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado y gotea en el estante."} for i in range(1, n + 1)])
    return eid


def test_generar_dos_pasadas_con_fallo_parcial(base_temporal, monkeypatch):
    from nicho import avatares, datos
    import marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Tono cercano")
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Happy Wash")
    eid = _estudio_listo(datos)
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    nucleos = {"nucleos": [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "comentarios": ids[:10]},
                           {"nombre": "Sin goteo", "deseo": "Quiero que no gotee", "resumen": "r2", "comentarios": ids[10:20]}]}
    sub = dict(SUB_JSON["sub_avatares"][0], evidencia=[{"comentario_id": ids[0], "cita": "la garrafa pesa demasiado"}])
    respuestas = [(json.dumps(nucleos), 1000, 200), (json.dumps({"sub_avatares": [sub]}), 700, 300), ("esto no es json", 500, 10)]
    prompts, etapas = [], []
    def _llamar_falso(texto, max_tokens):
        prompts.append((texto, max_tokens))
        return respuestas.pop(0)
    monkeypatch.setattr(avatares, "_llamar", _llamar_falso)
    r = avatares.generar("acme", eid, avanzar=lambda etapa, detalle=None: etapas.append((etapa, detalle)))
    assert [n["nombre"] for n in r["nucleos"]] == ["Sin peso", "Sin goteo"]
    assert len(r["nucleos"][0]["sub_avatares"]) == 1 and r["nucleos"][0]["sub_avatares"][0]["sin_evidencia"] is False
    assert r["nucleos"][0]["sub_avatares"][0]["evidencia"][0]["comentario_id"] == ids[0]
    assert r["nucleos"][1]["sub_avatares"] == [] and "JSON" in r["nucleos"][1]["error"]
    res = r["resumen"]
    assert res["comentarios"] == 25 and res["nucleos"] == 2 and res["subs"] == 1 and res["errores"] == 1
    assert res["con_evidencia"] == 1 and res["sin_evidencia"] == 0
    assert res["tokens_entrada"] == 2200 and res["tokens_salida"] == 510 and res["usd"] == avatares.costo_real(2200, 510)
    assert prompts[0][1] == avatares.MAX_TOKENS_NUCLEOS and prompts[1][1] == avatares.MAX_TOKENS_SUBS
    assert "Happy Wash" in prompts[0][0] and "Tono cercano" in prompts[1][0] and f"[{ids[10]}]" in prompts[2][0] and f"[{ids[0]}]" not in prompts[2][0]
    assert etapas[0] == (avatares.ETAPA_NUCLEOS, None) and etapas[1][0] == avatares.ETAPA_SUBS and "1/2" in etapas[1][1]


def test_generar_falla_limpio(base_temporal, monkeypatch):
    from nicho import avatares, datos
    eid = _estudio_listo(datos, n=5)
    with pytest.raises(datos.ErrorDatos):
        avatares.generar("acme", eid)                                     # menos de MIN_COMENTARIOS
    with pytest.raises(datos.ErrorDatos):
        avatares.generar("acme", 999)
    eid = _estudio_listo(datos)
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: ("{}", 10, 10))
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.generar("acme", eid)                                     # pasada 1 inválida: sube tal cual
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    respuestas = [(json.dumps({"nucleos": [{"nombre": "N", "deseo": "Quiero", "comentarios": ids[:3]}]}), 10, 10), ("roto", 1, 1)]
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: respuestas.pop(0))
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.generar("acme", eid)                                     # TODOS los núcleos fallaron en la pasada 2
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q -k generar`
Expected: FAIL con `AttributeError: module 'nicho.avatares' has no attribute 'generar'`.

- [ ] **Step 3: Agregar `_llamar` y `generar` a `nicho/avatares.py`**

```python
# ------------------------------------------------------------ generar ---

ETAPA_NUCLEOS = "Agrupando deseos"
ETAPA_SUBS = "Armando sub-avatares"


def _llamar(texto, max_tokens):
    """Una llamada a Claude (modelo del proyecto). Devuelve (texto, tokens de
    entrada, tokens de salida) — los tokens alimentan el gasto real. Las
    pruebas reemplazan esta función."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": texto}])
    if resp.stop_reason == "refusal":
        raise AnalisisInvalido("Claude rechazó la solicitud.")
    salida = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        raise AnalisisInvalido("La respuesta de Claude se cortó por largo (max_tokens).")
    uso = getattr(resp, "usage", None)
    return salida, int(getattr(uso, "input_tokens", 0) or 0), int(getattr(uso, "output_tokens", 0) or 0)


def generar(cliente, estudio_id, avanzar=None):
    """Las dos pasadas (spec §4.2, §4.5). Pasada 1 inválida: sube la excepción
    y no se guarda nada. Pasada 2: un núcleo que falla queda con `error` y sin
    sub-avatares; si TODOS fallan, sube AnalisisInvalido. No escribe en la
    base: el llamador (la tarea) guarda con datos.guardar_generacion."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    est = datos.estudio(cliente, estudio_id)
    if not est:
        raise datos.ErrorDatos("Ese estudio no existe.")
    todos = datos.comentarios_para_generar(cliente, estudio_id)
    if len(todos) < MIN_COMENTARIOS:
        raise datos.ErrorDatos(f"Hacen falta al menos {MIN_COMENTARIOS} comentarios no excluidos (hay {len(todos)}).")
    seleccion = seleccionar(todos)
    por_id = {c["id"]: c for c in seleccion}
    marca_nombre = proyectos.nombre_visible(cliente)
    avanzar(ETAPA_NUCLEOS)
    texto, entrada, salida = _llamar(armar_prompt_nucleos(est, seleccion, marca_nombre), MAX_TOKENS_NUCLEOS)
    tokens = [entrada, salida]
    nucleos = parsear_nucleos(texto, set(por_id))
    guia = marca.guia_efectiva(cliente) or ""
    resultado, errores = [], []
    for i, n in enumerate(nucleos):
        avanzar(ETAPA_SUBS, f"{i + 1}/{len(nucleos)}: {n['nombre']}")
        propios = [por_id[cid] for cid in n["comentarios"]]
        try:
            t2, e2, s2 = _llamar(armar_prompt_subs(est, n, propios, guia, marca_nombre), MAX_TOKENS_SUBS)
            tokens[0] += e2
            tokens[1] += s2
            subs = [verificar_evidencia(s, por_id) for s in parsear_subs(t2)]
            resultado.append({**n, "sub_avatares": subs})
        except AnalisisInvalido as e:
            errores.append(f"{n['nombre']}: {e}")
            resultado.append({**n, "sub_avatares": [], "error": str(e)[:300]})
    if errores and len(errores) == len(nucleos):
        raise AnalisisInvalido("Ningún núcleo produjo sub-avatares: " + " | ".join(errores)[:400])
    subs_todos = [s for n in resultado for s in n["sub_avatares"]]
    resumen = {
        "comentarios": len(seleccion), "nucleos": len(resultado), "subs": len(subs_todos),
        "con_evidencia": sum(1 for s in subs_todos if not s.get("sin_evidencia")),
        "sin_evidencia": sum(1 for s in subs_todos if s.get("sin_evidencia")),
        "errores": len(errores), "tokens_entrada": tokens[0], "tokens_salida": tokens[1],
        "usd": costo_real(tokens[0], tokens[1]), "modelo": modelo_actual(),
    }
    return {"nucleos": resultado, "resumen": resumen}
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py -q`
Expected: PASS (7 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/avatares.py
git add nicho/avatares.py tests/test_nicho_avatares.py
git commit -m "Nicho: generar en dos pasadas con fallo parcial por núcleo y gasto real por tokens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: `tareas/nicho.py` — tarea `nicho_generar_avatares`

**Files:**
- Create: `tareas/nicho.py`
- Modify: `tareas/__init__.py:33` (`cargar_todas` importa `nicho`)
- Test: `tests/test_tareas_nicho.py`

**Interfaces:**
- Consumes: `trabajos.encolar`, `cola.reportar`, `cola.sin_token`, `gastos.registrar_seguro`, `datos.job_id_generar`, `datos.recalcular`, `datos.guardar_generacion`, `datos.actualizar_extra_estudio`, `avatares.generar`.
- Produces: `ETAPA_GUARDAR = "Guardando"`, `ETAPAS_GENERAR = [(avatares.ETAPA_NUCLEOS, 45), (avatares.ETAPA_SUBS, 150), (ETAPA_GUARDAR, 5)]`, `encolar_generar(cliente, estudio_id) -> bool`, `ejecutar_generar(tarea) -> str` (registrada como `nicho_generar_avatares`), `interrumpida_generar(tarea, mensaje)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_tareas_nicho.py`:

```python
import pytest

SUB = {"base": "emocion", "nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "", "edad_rango": "",
       "emocion": "Cansancio", "identidad": {"quiere_que_vean": "a", "cree_de_si": "b", "quiere_lograr": "c"},
       "soluciones_previas": [], "situaciones": ["Cargando garrafas"], "comportamiento": "Sigue igual",
       "conciencia": {"nivel": "consciente_del_problema", "detalle": "d"}, "encaje_producto": "Cápsulas", "tono": "Directo",
       "palabras_clave": ["garrafa"], "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}], "sin_evidencia": False}


def _estudio(datos):
    eid = datos.crear_estudio("acme", "Detergente")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado."} for i in range(25)])
    return eid


def test_encolar_generar(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    eid = _estudio(datos)
    assert tareas_nicho.encolar_generar("acme", eid) is True
    t = encolados[0]
    assert t["job_id"] == datos.job_id_generar("acme", eid) and t["tipo"] == "nicho_generar_avatares"
    assert t["payload"] == {"cliente": "acme", "estudio_id": eid} and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert [e[0] for e in t["etapas"]] == ["Agrupando deseos", "Armando sub-avatares", "Guardando"]


def test_ejecutar_generar_guarda_registra_gasto_y_recalcula(base_temporal, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    import gastos
    eid = _estudio(datos)
    resultado = {"nucleos": [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "comentarios": [1], "sub_avatares": [SUB]}],
                 "resumen": {"comentarios": 25, "nucleos": 1, "subs": 1, "con_evidencia": 1, "sin_evidencia": 0, "errores": 0,
                             "tokens_entrada": 3000, "tokens_salida": 900, "usd": 0.015, "modelo": "claude-sonnet-5"}}
    llamadas = []
    monkeypatch.setattr(avatares, "generar", lambda cliente, estudio_id, avanzar=None: llamadas.append((cliente, estudio_id)) or resultado)
    msg = tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)})
    assert "1 núcleo" in msg and "1 sub-avatar" in msg and llamadas == [("acme", eid)]
    e = datos.estudio("acme", eid)
    assert e["estado"] == "revisando" and e["generacion"] == 1 and e["avatares_total"] == 1
    assert e["extra"]["ultima_generacion"]["usd"] == 0.015 and "ultimo_error" not in e["extra"]
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "avatares" and g["usd"] == 0.015 and g["referencia"] == f"avatares:{eid}:1" and g["proveedor"] == "anthropic"
    assert g["extra"]["tokens_entrada"] == 3000


def test_ejecutar_generar_falla_deja_error_y_estado(base_temporal, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tareas_nicho
    eid = _estudio(datos)
    monkeypatch.setattr(avatares, "generar", lambda *a, **k: (_ for _ in ()).throw(avatares.AnalisisInvalido("Claude no devolvió JSON.")))
    with pytest.raises(avatares.AnalisisInvalido):
        tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_generar("acme", eid)})
    e = datos.estudio("acme", eid)
    assert e["estado"] == "armando" and "Claude no devolvió JSON" in e["extra"]["ultimo_error"] and "cobró" in e["extra"]["ultimo_error"]
    assert tareas_nicho.ejecutar_generar({"payload": {"cliente": "acme", "estudio_id": 999}, "job_id": "x"}) == "El estudio ya no existe."


def test_interrumpida_generar(base_temporal):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = _estudio(datos)
    datos.actualizar_estudio("acme", eid, estado="generando")
    tareas_nicho.interrumpida_generar({"payload": {"cliente": "acme", "estudio_id": eid}}, "Se interrumpió por un reinicio.")
    e = datos.estudio("acme", eid)
    assert e["estado"] == "armando" and e["extra"]["ultimo_error"] == "Se interrumpió por un reinicio."


def test_worker_registra_la_tarea():
    import tareas
    from tareas import nicho  # noqa: F401 — el import corre los @registrar
    assert "nicho_generar_avatares" in tareas.REGISTRO and "nicho_generar_avatares" in tareas.AL_INTERRUMPIR
    import inspect
    assert "nicho" in inspect.getsource(tareas.cargar_todas)      # el worker real también lo importa
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_tareas_nicho.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'tareas.nicho'`.

- [ ] **Step 3: Escribir `tareas/nicho.py`**

```python
"""
Tareas del worker para Nicho (spec §8). Parte 1: solo la generación de
avatares con Claude; la Parte 2 agrega `nicho_recolectar` (Reddit, YouTube,
Apify) en este mismo módulo.

  nicho_generar_avatares -> nicho.datos.job_id_generar(cliente, estudio_id)
                            = "nicho:<cliente>:<estudio_id>:generar"   (max_intentos=1: gasta)

Gasta dinero (dos pasadas de Claude), por eso nunca se reintenta sola y al
terminar anota el gasto real con `gastos.registrar_seguro` (tokens × precio,
referencia `avatares:<estudio_id>:<generacion>`).
"""
import cola
import gastos
import trabajos
from nicho import avatares, datos
from tareas import al_interrumpir, registrar

ETAPA_GUARDAR = "Guardando"
ETAPAS_GENERAR = [(avatares.ETAPA_NUCLEOS, 45), (avatares.ETAPA_SUBS, 150), (ETAPA_GUARDAR, 5)]


def encolar_generar(cliente, estudio_id):
    """False si ya hay una generación viva para ese estudio."""
    ok = trabajos.encolar(datos.job_id_generar(cliente, estudio_id), "nicho_generar_avatares",
                          {"cliente": cliente, "estudio_id": int(estudio_id)}, cliente=cliente,
                          duracion_estimada=200, etapas=ETAPAS_GENERAR, max_intentos=1)
    if ok:
        datos.recalcular(cliente, estudio_id, tarea_viva=True)
    return ok


def _anotar_error(cliente, estudio_id, mensaje):
    datos.actualizar_extra_estudio(cliente, estudio_id, lambda x: {**x, "ultimo_error": cola.recortar(mensaje, 500)})
    datos.recalcular(cliente, estudio_id, tarea_viva=False)


@registrar("nicho_generar_avatares")
def ejecutar_generar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    if not datos.estudio(cliente, eid):
        return "El estudio ya no existe."
    job = tarea.get("job_id") or datos.job_id_generar(cliente, eid)

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    datos.recalcular(cliente, eid, tarea_viva=True)
    try:
        r = avatares.generar(cliente, eid, avanzar)
    except Exception as e:
        # Si Claude alcanzó a responder, ese intento ya se cobró: se dice tal cual.
        _anotar_error(cliente, eid, f"{cola.sin_token(e)} (si Claude alcanzó a responder, este intento sí se cobró)")
        raise
    avanzar(ETAPA_GUARDAR)
    res = datos.guardar_generacion(cliente, eid, r["nucleos"], r["resumen"])
    resumen = r["resumen"]
    gastos.registrar_seguro(cliente, "avatares", resumen.get("usd"), f"avatares:{eid}:{res['generacion']}",
                            detalle=f"{res['nucleos']} núcleo(s), {res['subs']} sub-avatar(es), {resumen.get('comentarios')} comentarios",
                            proveedor="anthropic",
                            extra={"tokens_entrada": resumen.get("tokens_entrada"), "tokens_salida": resumen.get("tokens_salida"),
                                   "modelo": resumen.get("modelo")})
    datos.recalcular(cliente, eid, tarea_viva=False)
    aviso = f" · {resumen['errores']} núcleo(s) sin sub-avatares" if resumen.get("errores") else ""
    return (f"{res['nucleos']} núcleo(s) y {res['subs']} sub-avatar(es) propuestos — revísalos y aprueba los que sirvan{aviso}.")


@al_interrumpir("nicho_generar_avatares")
def interrumpida_generar(tarea, mensaje):
    p = tarea["payload"]
    _anotar_error(p["cliente"], int(p["estudio_id"]), mensaje)
```

- [ ] **Step 4: Registrar el módulo en `tareas/__init__.py`** (línea 33)

```python
    from tareas import experimentos, final_edition, flowplus, meta, nicho, organico, sprints, swap, tiendas  # noqa: F401
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_tareas_nicho.py tests/test_cola.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile tareas/nicho.py tareas/__init__.py
git add tareas/nicho.py tareas/__init__.py tests/test_tareas_nicho.py
git commit -m "Nicho: tarea del worker nicho_generar_avatares (max_intentos=1, gasto real, estado del estudio)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 11: `nicho/exportar.py` — `.md` y Excel con la plantilla de la hoja

**Files:**
- Create: `nicho/exportar.py`
- Modify: `nicho/datos.py` (agregar `urls_comentarios`)
- Test: `tests/test_nicho_export.py`

**Interfaces:**
- Consumes: `openpyxl.Workbook`.
- Produces (en `nicho.exportar`): `FILAS_HOJA` (lista de `(clave, rótulo)`), `subs_exportables(nucleos) -> list[(nucleo, sub)]` (sin descartados), `valor(sub, clave, urls=None) -> str`, `markdown(estudio, nucleos, urls=None) -> str`, `excel(estudio, nucleos, urls=None) -> bytes`, `nombre_archivo(estudio, ext) -> str`.
- Produces (en `nicho.datos`): `urls_comentarios(cliente, estudio_id) -> {comentario_id: url|None}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_export.py`:

```python
import io


SUB_A = {"id": 11, "nombre": "Melissa / La que regala", "deseo": "Quiero regalar bien", "base": "emocion", "estado": "aprobado",
         "demografia": "Mujer 30-50", "edad_rango": "30-50", "emocion": "Presión",
         "identidad": {"quiere_que_vean": "detallista", "cree_de_si": "generosa", "quiere_lograr": "acertar"},
         "soluciones_previas": [{"que": "Tarjetas", "por_que_fallo": ["impersonal", "sin valor"]}, {"que": "Medias", "por_que_fallo": ["genéricas"]}],
         "situaciones": ["Compra a última hora", "Centro comercial"], "comportamiento": "Va a lo seguro",
         "conciencia": {"nivel": "consciente_del_problema", "detalle": "Sabe que falla"}, "encaje_producto": "Pantuflas con soporte",
         "tono": "Cálido", "palabras_clave": ["regalo"], "evidencia": [{"comentario_id": 1, "cita": "nunca sé qué regalar"}], "sin_evidencia": False}
SUB_B = dict(SUB_A, id=12, nombre="Descartado", estado="descartado")
NUCLEOS = [{"id": 1, "nombre": "Regalo con cabeza", "deseo": "Quiero regalar bien", "resumen": "Quienes regalan", "subs": [SUB_A, SUB_B]},
           {"id": 2, "nombre": "Vacío", "deseo": "Quiero x", "resumen": "", "subs": []}]
ESTUDIO = {"id": 5, "nombre": "Pantuflas / regalo", "producto": "HappyFlops", "tema": "regalos", "idioma": "es", "generacion": 2,
           "extra": {"ultima_generacion": {"fecha": "2026-09-18T10:00:00"}}}


def test_valor_y_subs_exportables():
    from nicho import exportar
    assert [(n["id"], s["id"]) for n, s in exportar.subs_exportables(NUCLEOS)] == [(1, 11)]
    assert exportar.valor(SUB_A, "identidad.cree_de_si") == "generosa"
    assert exportar.valor(SUB_A, "soluciones_previas.que") == "1. Tarjetas\n2. Medias"
    assert exportar.valor(SUB_A, "soluciones_previas.por_que_fallo") == "1. impersonal; sin valor\n2. genéricas"
    assert exportar.valor(SUB_A, "situaciones") == "Compra a última hora\nCentro comercial"
    assert exportar.valor(SUB_A, "conciencia") == "consciente del problema — Sabe que falla"
    assert exportar.valor(SUB_A, "evidencia", urls={1: "https://r.com/1"}) == "«nunca sé qué regalar» (https://r.com/1)"
    assert exportar.valor(SUB_A, "evidencia") == "«nunca sé qué regalar»"
    assert exportar.valor({}, "tono") == ""
    assert [r for _, r in exportar.FILAS_HOJA][:3] == ["Personas", "Deseo (frase de cabecera)", "Demographics (ASL)"]


def test_markdown():
    from nicho import exportar
    md = exportar.markdown(ESTUDIO, NUCLEOS, urls={1: "https://r.com/1"})
    for frag in ("# Avatares: Pantuflas / regalo", "HappyFlops", "## Núcleo 1: Regalo con cabeza", "**Deseo:** Quiero regalar bien",
                 "### Sub-avatar 1.1: Melissa / La que regala", "emoción · aprobado", "**Beliefs about self:** generosa",
                 "1. Tarjetas", "«nunca sé qué regalar» (https://r.com/1)", "## Núcleo 2: Vacío"):
        assert frag in md, frag
    assert "Descartado" not in md
    assert exportar.nombre_archivo(ESTUDIO, "md") == "avatares_pantuflas-regalo_5.md"


def test_excel():
    from openpyxl import load_workbook
    from nicho import exportar
    wb = load_workbook(io.BytesIO(exportar.excel(ESTUDIO, NUCLEOS)))
    ws = wb["Personas"]
    assert ws["A1"].value == "Personas" and ws["B1"].value == "Melissa / La que regala" and ws["C1"].value is None
    assert ws["A3"].value == "Demographics (ASL)" and ws["B3"].value == "Mujer 30-50"
    assert ws["A5"].value == "Beliefs about self" and ws["B5"].value == "generosa"
    assert ws["A8"].value.startswith("What are other solutions") and ws["B8"].value == "1. Tarjetas\n2. Medias"
    assert ws["B16"].value == "«nunca sé qué regalar»" and ws.freeze_panes == "B2"


def test_urls_comentarios(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": "a", "texto": "con link", "url": "https://r.com/1"},
                                                     {"fuente_id": "b", "texto": "sin link"}])
    urls = datos.urls_comentarios("acme", eid)
    assert sorted(urls.values(), key=str) == ["None", "https://r.com/1"] or set(urls.values()) == {None, "https://r.com/1"}
    assert datos.urls_comentarios("otro", eid) == {}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_export.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.exportar'`.

- [ ] **Step 3: Agregar `urls_comentarios` a `nicho/datos.py`** (sección comentarios)

```python
def urls_comentarios(cliente, estudio_id):
    """{id: url} de todos los comentarios del estudio (para enlazar las citas
    en la revisión y en las exportaciones), incluidos los excluidos."""
    c = db.comentario
    with db.conectar() as con:
        return {int(f.id): f.url for f in con.execute(sa.select(c.c.id, c.c.url).where(
            c.c.cliente == cliente, c.c.estudio_id == estudio_id))}
```

- [ ] **Step 4: Escribir `nicho/exportar.py`**

```python
"""
Exportación de un estudio (spec §6): `.md` como el doc "Desire-Based Core
Avatar" y `.xlsx` con la plantilla de la hoja "Personas" del cliente
(columna A los rótulos tal cual la hoja, una columna por sub-avatar; los
descartados no salen). Solo openpyxl; nada de Flask ni de base de datos.
"""
import io
import re
import unicodedata

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

# (clave, rótulo). Las primeras filas son la hoja "Personas" con sus rótulos
# exactos; después van los campos del doc del detergente que la hoja no tiene.
FILAS_HOJA = [
    ("nombre", "Personas"),
    ("deseo", "Deseo (frase de cabecera)"),
    ("demografia", "Demographics (ASL)"),
    ("identidad.quiere_que_vean", "What are some of the characteristics your prospect wants others to see in them?"),
    ("identidad.cree_de_si", "Beliefs about self"),
    ("identidad.quiere_lograr", "What does the prospect want to achieve in society?"),
    ("encaje_producto", "How does your product help them achieve that status/characteristics?"),
    ("soluciones_previas.que", "What are other solutions they have tried and failed at?"),
    ("soluciones_previas.por_que_fallo", "Reason for failure with those solutions"),
    ("situaciones", "Su día a día (situaciones)"),
    ("conciencia", "Nivel de conciencia"),
    ("emocion", "Emoción"),
    ("comportamiento", "Comportamiento"),
    ("tono", "Tono de voz"),
    ("palabras_clave", "Palabras clave"),
    ("evidencia", "Citas textuales"),
]
BASES_NOMBRE = {"emocion": "emoción", "experiencia_producto": "experiencia con el producto"}


def subs_exportables(nucleos):
    return [(n, s) for n in (nucleos or []) for s in (n.get("subs") or []) if s.get("estado") != "descartado"]


def _cita(e, urls):
    url = (urls or {}).get(e.get("comentario_id"))
    return f"«{e.get('cita', '')}»" + (f" ({url})" if url else "")


def valor(sub, clave, urls=None):
    """Texto plano de una fila de la hoja para un sub-avatar."""
    sub = sub or {}
    if clave == "conciencia":
        c = sub.get("conciencia") or {}
        nivel = (c.get("nivel") or "").replace("_", " ")
        return " — ".join(x for x in (nivel, c.get("detalle") or "") if x)
    if clave == "evidencia":
        return "\n".join(_cita(e, urls) for e in sub.get("evidencia") or [])
    if clave == "soluciones_previas.que":
        return "\n".join(f"{i + 1}. {s.get('que') or ''}" for i, s in enumerate(sub.get("soluciones_previas") or []))
    if clave == "soluciones_previas.por_que_fallo":
        return "\n".join(f"{i + 1}. " + "; ".join(s.get("por_que_fallo") or [])
                         for i, s in enumerate(sub.get("soluciones_previas") or []))
    if clave.startswith("identidad."):
        return (sub.get("identidad") or {}).get(clave.split(".", 1)[1]) or ""
    v = sub.get(clave)
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    return "" if v is None else str(v)


def _slug(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", texto.strip()).strip("-").lower()[:40] or "estudio"


def nombre_archivo(estudio, ext):
    return f"avatares_{_slug(estudio.get('nombre'))}_{estudio.get('id')}.{ext}"


def markdown(estudio, nucleos, urls=None):
    fecha = ((estudio.get("extra") or {}).get("ultima_generacion") or {}).get("fecha") or ""
    lineas = [f"# Avatares: {estudio.get('nombre') or ''}", "",
              f"Producto: {estudio.get('producto') or '—'} · Tema: {estudio.get('tema') or '—'} · Idioma: {estudio.get('idioma') or 'es'}"
              f" · Generación {estudio.get('generacion') or 0}" + (f" · {fecha}" if fecha else ""), ""]
    for i, n in enumerate(nucleos or [], start=1):
        lineas += [f"## Núcleo {i}: {n.get('nombre') or ''}", "", f"**Deseo:** {n.get('deseo') or ''}", ""]
        if n.get("resumen"):
            lineas += [n["resumen"], ""]
        subs = [s for s in (n.get("subs") or []) if s.get("estado") != "descartado"]
        for j, s in enumerate(subs, start=1):
            lineas += [f"### Sub-avatar {i}.{j}: {s.get('nombre') or ''} "
                       f"({BASES_NOMBRE.get(s.get('base'), s.get('base') or '')} · {s.get('estado') or 'propuesto'})", ""]
            for clave, rotulo in FILAS_HOJA[1:]:
                v = valor(s, clave, urls)
                if not v:
                    continue
                if "\n" in v:
                    lineas.append(f"- **{rotulo}:**")
                    lineas += [f"  - {x}" for x in v.split("\n")]
                else:
                    lineas.append(f"- **{rotulo}:** {v}")
            lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def excel(estudio, nucleos, urls=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Personas"
    negrita = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="3B6FD9")
    ajuste = Alignment(wrap_text=True, vertical="top")
    for fila, (_, rotulo) in enumerate(FILAS_HOJA, start=1):
        celda = ws.cell(row=fila, column=1, value=rotulo)
        celda.font, celda.fill, celda.alignment = negrita, relleno, ajuste
    for col, (_, s) in enumerate(subs_exportables(nucleos), start=2):
        for fila, (clave, _) in enumerate(FILAS_HOJA, start=1):
            celda = ws.cell(row=fila, column=col, value=valor(s, clave, urls) or None)
            celda.alignment = ajuste
            if fila == 1:
                celda.font = Font(bold=True)
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 45
    ws.column_dimensions["A"].width = 38
    ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_export.py -q`
Expected: PASS (4 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile nicho/exportar.py nicho/datos.py
git add nicho/exportar.py nicho/datos.py tests/test_nicho_export.py
git commit -m "Nicho: exportar el estudio a .md y a Excel con la plantilla de la hoja Personas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: `nicho/rutas.py`, pestaña Nicho y registro en el dashboard

**Files:**
- Create: `nicho/rutas.py`, `templates/_tab_nicho.html`
- Modify: `dashboard.py:114-115` (import y `register_blueprint`), `dashboard.py:1028` (`**nicho_rutas.contexto(cliente)`), `templates/_sidebar.html` (botón después de Tablero), `templates/cliente.html` (sección y panel)
- Test: `tests/test_rutas_nicho.py`

**Interfaces:**
- Consumes: todo `nicho.datos`, `nicho.avatares.estimar_costo/MIN_COMENTARIOS/IDIOMAS`, `nicho.exportar`, `nicho.fuentes.por_tipo/NOMBRES`, `nicho.fuentes.texto.NOMBRES_MODO`, `nicho.fuentes.archivo.MAX_BYTES`, `tareas.nicho.encolar_generar`, `trabajos.en_curso`, `gastos.formatear`, `catalogo_productos.listar`, `proyectos.nombre_visible`.
- Produces: `bp` (`Blueprint("nicho", url_prefix="/cliente/<cliente>/nicho")`), `contexto(cliente) -> {"estudios_nicho", "productos_nicho", "idiomas_nicho", "min_comentarios_nicho"}`, filtro Jinja `soluciones_texto`, y las rutas de la tabla del spec §7 (`crear`, `ver`, `editar`, `archivar`, `comentarios_texto`, `comentarios_archivo`, `comentario_excluir`, `comentarios_borrar`, `generar`, `avatar_editar`, `avatar_aprobar`, `avatar_descartar`, `exportar_md`, `exportar_xlsx`). La página `nicho_estudio.html` la escribe la Task 13: en esta tarea `ver` ya existe pero solo se prueba por su redirección.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_rutas_nicho.py`:

```python
"""Rutas del Blueprint nicho: validan y delegan a nicho.datos / tareas.nicho;
encolar se monkeypatchea. Sesión admin como en test_rutas_sprints."""
import io

import pytest

SUB = {"base": "emocion", "nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "", "edad_rango": "",
       "emocion": "Cansancio", "identidad": {"quiere_que_vean": "a", "cree_de_si": "b", "quiere_lograr": "c"},
       "soluciones_previas": [{"que": "Líquido", "por_que_fallo": ["pesa"]}], "situaciones": ["Cargando garrafas"],
       "comportamiento": "Sigue igual", "conciencia": {"nivel": "consciente_del_problema", "detalle": "d"},
       "encaje_producto": "Cápsulas", "tono": "Directo", "palabras_clave": ["garrafa"],
       "evidencia": [{"comentario_id": 1, "cita": "la garrafa pesa demasiado"}], "sin_evidencia": False}


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import catalogo_productos
    import proyectos
    from nicho import rutas
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [
        {"id": "capsulas", "nombre": "Cápsulas", "descripcion": "sin plástico", "representativa_url": None}])
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _estudio(datos, n=25):
    eid = datos.crear_estudio("acme", "Detergente", producto="Cápsulas", tema="lavar")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado."} for i in range(n)])
    return eid


def _con_avatares(datos):
    eid = _estudio(datos)
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "sub_avatares": [SUB]}])
    return eid, datos.avatares("acme", eid)[0]["subs"][0]["id"]


def test_crear_estudio_y_pestana(app):
    from nicho import datos
    c = app["c"]
    r = c.post("/cliente/acme/nicho/estudios", data={"nombre": "Detergente", "producto": "Cápsulas", "tema": "lavar", "idioma": "sv", "catalogo_id": "capsulas"})
    e = datos.estudios("acme")[0]
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/cliente/acme/nicho/{e['id']}")
    assert e["idioma"] == "sv" and e["catalogo_id"] == "capsulas"
    r = c.post("/cliente/acme/nicho/estudios", data={"nombre": ""})
    assert r.status_code == 302 and r.headers["Location"].endswith("#nicho") and len(datos.estudios("acme")) == 1
    html = c.get("/cliente/acme").data.decode()
    assert 'data-tab="nicho"' in html and "Detergente" in html and "Nuevo estudio" in html


def test_contexto(app):
    from nicho import datos, rutas
    _estudio(datos)
    ctx = rutas.contexto("acme")
    assert ctx["estudios_nicho"][0]["comentarios_total"] == 25 and ctx["productos_nicho"][0]["id"] == "capsulas"
    assert ctx["min_comentarios_nicho"] == 20 and "es" in ctx["idiomas_nicho"]


def test_editar_y_archivar(app):
    from nicho import datos
    eid = _estudio(datos)
    app["c"].post(f"/cliente/acme/nicho/{eid}/editar", data={"nombre": "Otro", "idioma": "en", "catalogo_id": ""})
    e = datos.estudio("acme", eid)
    assert e["nombre"] == "Otro" and e["idioma"] == "en" and e["catalogo_id"] is None
    app["c"].post(f"/cliente/acme/nicho/{eid}/archivar")
    assert datos.estudio("acme", eid)["archivado"] is True
    app["c"].post(f"/cliente/acme/nicho/{eid}/archivar", data={"desarchivar": "1"})
    assert datos.estudio("acme", eid)["archivado"] is False
    assert app["c"].post("/cliente/otro/nicho/999/editar", data={"nombre": "x"}).status_code == 404


def test_comentarios_texto_archivo_excluir_borrar(app):
    from nicho import datos
    c = app["c"]
    eid = datos.crear_estudio("acme", "X")
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/texto", data={"texto": "Pesa mucho la garrafa\nok\n\nGotea en el estante", "modo": "lineas"})
    assert datos.estudio("acme", eid)["comentarios_total"] == 2
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/archivo", data={"archivo": (io.BytesIO(b"review;rating\nSe pega la tapa;4\nPesa mucho la garrafa;5\n"), "r.csv")},
           content_type="multipart/form-data")
    e = datos.estudio("acme", eid)
    assert e["fuentes"] == {"texto": {"total": 2, "excluidos": 0}, "csv": {"total": 2, "excluidos": 0}}   # el repetido no duplica dentro de su fuente
    r = c.post(f"/cliente/acme/nicho/{eid}/comentarios/archivo", data={"archivo": (io.BytesIO(b"hola"), "r.txt")}, content_type="multipart/form-data")
    assert r.status_code == 302 and datos.estudio("acme", eid)["comentarios_total"] == 4
    cid = datos.comentarios("acme", eid)["items"][0]["id"]
    c.post(f"/cliente/acme/nicho/comentario/{cid}/excluir")
    assert datos.comentario("acme", cid)["excluido"] is True and datos.estudio("acme", eid)["comentarios_activos"] == 3
    c.post(f"/cliente/acme/nicho/comentario/{cid}/excluir", data={"incluir": "1"})
    assert datos.comentario("acme", cid)["excluido"] is False
    c.post(f"/cliente/acme/nicho/{eid}/comentarios/borrar/csv")
    assert datos.estudio("acme", eid)["fuentes"] == {"texto": {"total": 2, "excluidos": 0}}
    assert c.post(f"/cliente/acme/nicho/{eid}/comentarios/borrar/magia").status_code == 404
    assert len(datos.estudio("acme", eid)["extra"]["recolecciones"]) == 2


def test_generar_encola_con_puerta(app):
    from nicho import datos
    eid = _estudio(datos, n=5)
    app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert app["encolados"] == []                                          # menos de 20 comentarios: no encola
    eid = _estudio(datos)
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    t = app["encolados"][0]
    assert t["tipo"] == "nicho_generar_avatares" and t["payload"] == {"cliente": "acme", "estudio_id": eid} and t["max_intentos"] == 1
    assert datos.estudio("acme", eid)["estado"] == "generando"
    datos.archivar_estudio("acme", eid)
    app["c"].post(f"/cliente/acme/nicho/{eid}/generar")
    assert len(app["encolados"]) == 1                                      # archivado: no encola


def test_avatar_editar_aprobar_descartar(app):
    from nicho import datos
    from sprints import datos as sd
    c = app["c"]
    eid, sid = _con_avatares(datos)
    c.post(f"/cliente/acme/nicho/avatar/{sid}/editar", data={
        "nombre": "Ana", "deseo": "Quiero lavar sin cargar", "base": "experiencia_producto", "demografia": "Mujer 30-45", "edad_rango": "30-45",
        "emocion": "Cansancio", "identidad_quiere_que_vean": "x", "identidad_cree_de_si": "y", "identidad_quiere_lograr": "z",
        "soluciones_previas": "Líquido :: pesa; gotea\nPods :: caros", "situaciones": "Cargando\nEn el súper", "comportamiento": "c",
        "conciencia_nivel": "muy_consciente", "conciencia_detalle": "d", "encaje_producto": "e", "tono": "t", "palabras_clave": "a, b"})
    a = datos.avatar("acme", sid)
    assert a["nombre"] == "Ana" and a["base"] == "experiencia_producto" and a["identidad"]["cree_de_si"] == "y"
    assert a["soluciones_previas"] == [{"que": "Líquido", "por_que_fallo": ["pesa", "gotea"]}, {"que": "Pods", "por_que_fallo": ["caros"]}]
    assert a["situaciones"] == ["Cargando", "En el súper"] and a["conciencia"]["nivel"] == "muy_consciente" and a["palabras_clave"] == ["a", "b"]
    assert a["evidencia"] == SUB["evidencia"]                              # la evidencia no se toca
    r = c.post(f"/cliente/acme/nicho/avatar/{sid}/aprobar")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    a = datos.avatar("acme", sid)
    assert a["estado"] == "aprobado" and sd.persona("acme", a["persona_id"])["nombre"] == "Ana"
    c.post(f"/cliente/acme/nicho/avatar/{sid}/descartar")
    assert datos.avatar("acme", sid)["estado"] == "descartado" and sd.persona("acme", a["persona_id"])["archivada"] is True
    nucleo_id = datos.avatares("acme", eid)[0]["id"]
    c.post(f"/cliente/acme/nicho/avatar/{nucleo_id}/aprobar")              # flash de error, no revienta
    assert datos.avatar("acme", nucleo_id)["estado"] == "propuesto"
    assert c.post("/cliente/otro/nicho/avatar/999/aprobar").status_code == 404
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.rutas'`.

- [ ] **Step 3: Escribir `nicho/rutas.py`**

```python
# nicho/rutas.py
"""
Rutas de la pestaña Nicho (Blueprint `nicho`, prefijo /cliente/<cliente>/nicho).
Solo validan, delegan a nicho.datos / nicho.avatares / nicho.exportar /
tareas.nicho y redirigen; la lógica vive en esos módulos.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
<cliente>. `contexto(cliente)` es lo que `ver_cliente` agrega al render de
cliente.html para la pestaña; el estudio abre en su propia página
(`nicho_estudio.html`, como `sprint_detalle.html`).
"""
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, send_file, url_for

import catalogo_productos
import gastos
import proyectos
import trabajos
from nicho import avatares, datos, exportar
from nicho import fuentes as fuentes_registro
from nicho.fuentes import archivo as fuente_archivo
from nicho.fuentes import texto as fuente_texto
from nicho.fuentes.base import ErrorFuente
from tareas import nicho as tareas_nicho

bp = Blueprint("nicho", __name__, url_prefix="/cliente/<cliente>/nicho")
POR_PAGINA = 50


# ------------------------------------------------------------ helpers ---

def _volver(cliente, eid=None):
    if eid is not None:
        return redirect(url_for("nicho.ver", cliente=cliente, eid=eid))
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="nicho"))


def _estudio_o_404(cliente, eid):
    e = datos.estudio(cliente, eid)
    if not e:
        abort(404)
    return e


def _avatar_o_404(cliente, aid):
    a = datos.avatar(cliente, aid)
    if not a:
        abort(404)
    return a


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _lineas(texto):
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def _productos(cliente):
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion") or ""}
            for p in catalogo_productos.listar(cliente, "producto")]


def contexto(cliente):
    """Lo que necesita _tab_nicho.html. Se llama desde dashboard.ver_cliente."""
    return {"estudios_nicho": datos.estudios(cliente), "productos_nicho": _productos(cliente),
            "idiomas_nicho": avatares.IDIOMAS, "min_comentarios_nicho": avatares.MIN_COMENTARIOS}


# ----------------------------------------------------------- estudios ---

@bp.post("/estudios")
def crear(cliente):
    try:
        eid = datos.crear_estudio(cliente, request.form.get("nombre"), producto=request.form.get("producto"),
                                  tema=request.form.get("tema"), idioma=request.form.get("idioma") or "es",
                                  catalogo_id=request.form.get("catalogo_id") or None)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)
    flash("Estudio creado. Ahora agrégale comentarios.", "ok")
    return _volver(cliente, eid)


@bp.get("/<int:eid>")
def ver(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    est["estado"] = datos.recalcular(cliente, eid) or est["estado"]
    fuente = request.args.get("fuente") or None
    try:
        pagina = int(request.args.get("pagina") or 1)
    except ValueError:
        pagina = 1
    lista = datos.comentarios_para_generar(cliente, eid)
    estimado = avatares.estimar_costo(lista)
    job = datos.job_id_generar(cliente, eid)
    return render_template(
        "nicho_estudio.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente), estudio=est,
        conteos=datos.contar_por_fuente(cliente, eid), fuente_filtro=fuente,
        pagina_comentarios=datos.comentarios(cliente, eid, fuente=fuente, pagina=pagina, por_pagina=POR_PAGINA),
        nucleos=datos.avatares(cliente, eid), urls_comentarios=datos.urls_comentarios(cliente, eid),
        estimado=estimado, precio_texto=gastos.formatear(estimado["usd"]), min_comentarios=avatares.MIN_COMENTARIOS,
        trabajo_generar=({"job_id": job} if trabajos.en_curso(job) else None),
        modos_texto=fuente_texto.NOMBRES_MODO, fuentes_nombre=fuentes_registro.NOMBRES, idiomas=avatares.IDIOMAS,
        niveles_conciencia=datos.NIVELES_CONCIENCIA, bases=datos.BASES, productos_nicho=_productos(cliente))


@bp.post("/<int:eid>/editar")
def editar(cliente, eid):
    _estudio_o_404(cliente, eid)
    try:
        campos = {k: request.form.get(k) for k in ("nombre", "producto", "tema", "idioma") if request.form.get(k) is not None}
        if request.form.get("catalogo_id") is not None:
            campos["catalogo_id"] = request.form.get("catalogo_id") or None
        datos.actualizar_estudio(cliente, eid, **campos)
        flash("Estudio guardado.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/archivar")
def archivar(cliente, eid):
    _estudio_o_404(cliente, eid)
    datos.archivar_estudio(cliente, eid, archivado=request.form.get("desarchivar") is None)
    return _volver(cliente, eid)


# -------------------------------------------------------- comentarios ---

def _agregar(cliente, eid, fuente, lista):
    r = datos.agregar_comentarios(cliente, eid, fuente, lista)
    datos.registrar_recoleccion(cliente, eid, {"fuente": fuente, "nuevos": r["nuevos"], "repetidos": r["repetidos"], "aviso": ""})
    datos.recalcular(cliente, eid)
    flash(f"Entraron {r['nuevos']} comentario(s); {r['repetidos']} repetido(s).", "ok")


@bp.post("/<int:eid>/comentarios/texto")
def comentarios_texto(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("texto")().recolectar(
            {"texto": request.form.get("texto"), "modo": request.form.get("modo") or "lineas"}))
        if not lista:
            flash("No encontré comentarios en el texto (mínimo 3 caracteres cada uno).", "error")
        else:
            _agregar(cliente, eid, "texto", lista)
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/comentarios/archivo")
def comentarios_archivo(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    f = request.files.get("archivo")
    if not f or not f.filename:
        flash("Elige un archivo .csv o .xlsx.", "error")
        return _volver(cliente, eid)
    try:
        lista = list(fuentes_registro.por_tipo("csv")().recolectar(
            {"nombre": f.filename, "contenido": f.read(fuente_archivo.MAX_BYTES + 1)}))
        if not lista:
            flash("El archivo no trajo comentarios.", "error")
        else:
            _agregar(cliente, eid, "csv", lista)
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
    return _volver(cliente, eid)


@bp.post("/comentario/<int:cid>/excluir")
def comentario_excluir(cliente, cid):
    c = datos.comentario(cliente, cid)
    if not c:
        abort(404)
    datos.excluir_comentario(cliente, cid, excluido=request.form.get("incluir") is None)
    return _volver(cliente, c["estudio_id"])


@bp.post("/<int:eid>/comentarios/borrar/<fuente>")
def comentarios_borrar(cliente, eid, fuente):
    _estudio_o_404(cliente, eid)
    if fuente not in datos.FUENTES:
        abort(404)
    n = datos.borrar_fuente(cliente, eid, fuente)
    datos.recalcular(cliente, eid)
    flash(f"Se quitaron {n} comentario(s) de {fuentes_registro.NOMBRES.get(fuente, fuente)}.", "ok")
    return _volver(cliente, eid)


# ----------------------------------------------------------- avatares ---

@bp.post("/<int:eid>/generar")
def generar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    lista = datos.comentarios_para_generar(cliente, eid)
    if len(lista) < avatares.MIN_COMENTARIOS:
        flash(f"Hacen falta al menos {avatares.MIN_COMENTARIOS} comentarios no excluidos (hay {len(lista)}).", "error")
        return _volver(cliente, eid)
    if tareas_nicho.encolar_generar(cliente, eid):
        flash("Claude está armando los avatares; la página se recarga sola al terminar.", "ok")
    else:
        flash("Ya hay una generación en curso para este estudio.", "error")
    return _volver(cliente, eid)


def _soluciones_desde_texto(texto):
    """Una solución por línea: «qué usó :: problema; problema»."""
    salida = []
    for linea in _lineas(texto):
        que, _, fallas = linea.partition("::")
        salida.append({"que": que.strip(), "por_que_fallo": [x.strip() for x in fallas.split(";") if x.strip()]})
    return salida


@bp.app_template_filter("soluciones_texto")
def soluciones_texto(soluciones):
    """Inverso de _soluciones_desde_texto, para pintar el textarea."""
    return "\n".join(f"{s.get('que', '')} :: " + "; ".join(s.get("por_que_fallo") or []) for s in (soluciones or []))


def _campos_avatar_desde_form():
    f = request.form
    campos = {}
    for k in ("nombre", "deseo", "base", "demografia", "edad_rango", "emocion", "comportamiento", "encaje_producto", "tono"):
        if f.get(k) is not None:
            campos[k] = f.get(k)
    if any(f.get(f"identidad_{k}") is not None for k in datos.CLAVES_IDENTIDAD):
        campos["identidad"] = {k: f.get(f"identidad_{k}") or "" for k in datos.CLAVES_IDENTIDAD}
    if f.get("soluciones_previas") is not None:
        campos["soluciones_previas"] = _soluciones_desde_texto(f.get("soluciones_previas"))
    if f.get("situaciones") is not None:
        campos["situaciones"] = _lineas(f.get("situaciones"))
    if f.get("conciencia_nivel") is not None or f.get("conciencia_detalle") is not None:
        campos["conciencia"] = {"nivel": f.get("conciencia_nivel") or "", "detalle": f.get("conciencia_detalle") or ""}
    if f.get("palabras_clave") is not None:
        campos["palabras_clave"] = _partir(f.get("palabras_clave"))
    return campos


@bp.post("/avatar/<int:aid>/editar")
def avatar_editar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.actualizar_avatar(cliente, aid, **_campos_avatar_desde_form())
        flash("Avatar guardado. Si ya estaba aprobado, vuelve a aprobarlo para actualizar la persona.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, a["estudio_id"])


@bp.post("/avatar/<int:aid>/aprobar")
def avatar_aprobar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.aprobar_avatar(cliente, aid)
        flash("Avatar aprobado: ya es una persona de Sprints.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, a["estudio_id"])


@bp.post("/avatar/<int:aid>/descartar")
def avatar_descartar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    datos.descartar_avatar(cliente, aid)
    flash("Avatar descartado.", "ok")
    return _volver(cliente, a["estudio_id"])


# ----------------------------------------------------------- exportar ---

@bp.get("/<int:eid>/exportar.md")
def exportar_md(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    md = exportar.markdown(est, datos.avatares(cliente, eid), urls=datos.urls_comentarios(cliente, eid))
    return Response(md, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{exportar.nombre_archivo(est, "md")}"'})


@bp.get("/<int:eid>/exportar.xlsx")
def exportar_xlsx(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    contenido = exportar.excel(est, datos.avatares(cliente, eid), urls=datos.urls_comentarios(cliente, eid))
    return send_file(io.BytesIO(contenido), as_attachment=True, download_name=exportar.nombre_archivo(est, "xlsx"),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

- [ ] **Step 4: Registrar el Blueprint y el contexto en `dashboard.py`**

Debajo de las líneas 114-115 (`from sprints import rutas as sprints_rutas` / `app.register_blueprint(sprints_rutas.bp)`):

```python
from nicho import rutas as nicho_rutas  # noqa: E402  (Blueprint de la pestaña Nicho)
app.register_blueprint(nicho_rutas.bp)
```

En `ver_cliente` (línea ~1028), después de `**sprints_rutas.contexto(cliente),`:

```python
        **nicho_rutas.contexto(cliente),
```

- [ ] **Step 5: Pestaña en `templates/_sidebar.html`** (después del botón `tablero`)

```html
    <button type="button" class="sidebar-item" data-tab="nicho" role="tab" title="Nicho">
      <svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6" stroke="currentColor" stroke-width="2" fill="none"/><path d="M15 15l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M8 10.5h5M10.5 8v5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
      <span class="sidebar-texto">Nicho</span>
    </button>
```

- [ ] **Step 6: Sección y panel en `templates/cliente.html`**

Después de `<section id="tab-tablero" ...>...</section>` (antes de `tab-creativeflowplus`):

```html
<section id="tab-nicho" class="tab-panel" role="tabpanel">
  {% include "_tab_nicho.html" %}
</section>
```

En el objeto `paneles` del script, agregar la línea `nicho: document.getElementById('tab-nicho'),` después de `tablero: ...`.

- [ ] **Step 7: Escribir `templates/_tab_nicho.html`**

```html
{# Pestaña Nicho. Contexto de nicho.rutas.contexto(cliente): estudios_nicho,
   productos_nicho, idiomas_nicho, min_comentarios_nicho. #}
<div class="panel-cabecera">
  <h2>Nicho</h2>
  <p class="vacio">Un estudio recoge comentarios reales de la gente sobre un producto o nicho y Claude los convierte en avatares con evidencia. Aprobar un sub-avatar crea una persona para Sprints y Crear. Nada se genera sin ver el costo antes.</p>
</div>

<div class="sprints-lista">
  {% for e in estudios_nicho %}
  <a class="swap-card sprint-card" href="{{ url_for('nicho.ver', cliente=cliente, eid=e.id) }}">
    <div>
      <strong>{{ e.nombre }}</strong> <span class="tag-estado estado-nicho estado-nicho-{{ e.estado }}">{{ e.estado }}</span>
      <br><small class="vacio">{{ e.producto or 'sin producto' }} · {{ e.comentarios_total }} comentario(s) de {{ e.fuentes | length }} fuente(s) · {{ e.avatares_aprobados }} de {{ e.avatares_total }} avatar(es) aprobado(s)</small>
    </div>
  </a>
  {% else %}
  <p class="vacio">Todavía no hay estudios. Crea el primero abajo: con {{ min_comentarios_nicho }} comentarios pegados a mano ya salen avatares.</p>
  {% endfor %}
</div>

<details class="swap-card" id="nuevo-estudio" {% if not estudios_nicho %}open{% endif %}>
  <summary class="swap-card-resumen">+ Nuevo estudio</summary>
  <form method="post" action="{{ url_for('nicho.crear', cliente=cliente) }}" class="form-experimento" id="form-estudio">
    <div class="fe-opciones">
      <label>Nombre <input name="nombre" required maxlength="120" placeholder="Detergente en cápsulas · Suecia"></label>
      <label>Producto del catálogo
        <select name="catalogo_id" id="estudio-catalogo">
          <option value="">(escribir a mano)</option>
          {% for p in productos_nicho %}<option value="{{ p.id }}" data-descripcion="{{ p.nombre }}{% if p.descripcion %}: {{ p.descripcion }}{% endif %}">{{ p.nombre }}</option>{% endfor %}
        </select>
      </label>
      <label>Idioma de los avatares
        <select name="idioma">{% for codigo, nombre in idiomas_nicho.items() %}<option value="{{ codigo }}">{{ nombre }}</option>{% endfor %}</select>
      </label>
    </div>
    <label>Qué vendemos <textarea name="producto" id="estudio-producto" rows="2" placeholder="Cápsulas de detergente sin plástico, dosis exacta, olor suave"></textarea></label>
    <label>Qué investigar (nicho, mercado, dolores, palabras clave) <textarea name="tema" rows="3" placeholder="Gente que lava en casa y odia cargar garrafas; mercado sueco; reseñas de Via, Ariel y pods"></textarea></label>
    <button type="submit" class="btn-generar btn-sm">Crear estudio</button>
  </form>
</details>
<script>
  (function () {
    var sel = document.getElementById('estudio-catalogo'), prod = document.getElementById('estudio-producto');
    if (!sel || !prod) return;
    sel.addEventListener('change', function () {
      var op = sel.options[sel.selectedIndex];
      if (op && op.dataset.descripcion && !prod.value.trim()) prod.value = op.dataset.descripcion;
    });
  })();
</script>
```

- [ ] **Step 8: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py tests/test_rutas_sprints.py -q`
Expected: PASS (las de nicho no piden la página del estudio: solo redirecciones y la pestaña).

- [ ] **Step 9: Commit**

```bash
python3 -m py_compile nicho/rutas.py dashboard.py
git add nicho/rutas.py templates/_tab_nicho.html templates/_sidebar.html templates/cliente.html dashboard.py tests/test_rutas_nicho.py
git commit -m "Nicho: Blueprint de rutas, pestaña Nicho en el proyecto y registro en el dashboard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 13: Página del estudio — comentarios, avatares, progreso y exportación

**Files:**
- Create: `templates/nicho_estudio.html`, `templates/_nicho_nav.html`, `templates/_nicho_comentarios.html`, `templates/_nicho_avatares.html`
- Modify: `static/style.css` (al final)
- Test: `tests/test_rutas_nicho.py` (agregar)

**Interfaces:**
- Consumes: el contexto que `nicho.rutas.ver` pasa a `nicho_estudio.html` (Task 12): `estudio, conteos, fuente_filtro, pagina_comentarios, nucleos, urls_comentarios, estimado, precio_texto, min_comentarios, trabajo_generar, modos_texto, fuentes_nombre, idiomas, niveles_conciencia, bases, productos_nicho`; el filtro Jinja `soluciones_texto`; `iniciarPolling()` de `base.html`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_rutas_nicho.py`)

```python
def test_pagina_del_estudio(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    for frag in ("Detergente", "Regenerar avatares", "US$", "25 comentario(s)", "Núcleo 1: Sin peso", "Ana / La que carga",
                 "«la garrafa pesa demasiado»", "Aprobar → persona", "Exportar Excel", "Pegar texto", "Subir CSV o Excel", "Excluir",
                 "Beliefs about self"):
        assert frag in html, frag
    assert app["c"].get("/cliente/acme/nicho/999").status_code == 404
    assert app["c"].get(f"/cliente/acme/nicho/{eid}?fuente=texto&pagina=abc").status_code == 200


def test_pagina_sin_comentarios_apaga_el_boton(app):
    from nicho import datos
    eid = _estudio(datos, n=3)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Hacen falta al menos 20" in html and "disabled" in html and "Todavía no hay avatares" in html


def test_pagina_con_trabajo_en_curso_muestra_progreso(app, monkeypatch):
    from nicho import datos, rutas
    eid = _estudio(datos)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: job_id == datos.job_id_generar("acme", eid))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "iniciarPolling" in html and datos.job_id_generar("acme", eid) in html


def test_exportar(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/exportar.md")
    assert r.status_code == 200 and "text/markdown" in r.content_type and "## Núcleo 1: Sin peso" in r.data.decode()
    assert "attachment" in r.headers["Content-Disposition"] and ".md" in r.headers["Content-Disposition"]
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/exportar.xlsx")
    assert r.status_code == 200 and "spreadsheetml" in r.content_type and r.data[:2] == b"PK"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -k "pagina or exportar"`
Expected: FAIL con `TemplateNotFound: nicho_estudio.html`.

- [ ] **Step 3: Escribir `templates/_nicho_nav.html`**

```html
{# Migas y comportamiento de la barra lateral fuera de cliente.html (igual que
   _sprint_nav.html): los botones de pestaña no tienen paneles en esta página,
   así que llevan de vuelta al proyecto con el hash de la pestaña. #}
<p class="sprint-migas">
  <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='nicho') }}">← Nicho</a>
  {% if estudio %} · {{ estudio.nombre }}{% endif %}
</p>
<script>
  document.querySelectorAll('.sidebar-item[data-tab]').forEach(function (b) {
    b.addEventListener('click', function () {
      location.href = {{ url_for('ver_cliente', cliente=cliente) | tojson }} + '#' + b.dataset.tab;
    });
  });
</script>
```

- [ ] **Step 4: Escribir `templates/nicho_estudio.html`**

```html
{% extends "base.html" %}
{% block title %}{{ estudio.nombre }} · Nicho{% endblock %}
{% block content %}
{% include "_nicho_nav.html" %}

<div class="pagina-cabecera">
  <div>
    <h1>{{ estudio.nombre }}</h1>
    <p class="vacio"><span class="tag-estado estado-nicho estado-nicho-{{ estudio.estado }}">{{ estudio.estado }}</span>
      · {{ estudio.producto or 'sin producto' }} · avatares en {{ idiomas.get(estudio.idioma, estudio.idioma) }}
      · generación {{ estudio.generacion }}{% if estudio.archivado %} · archivado{% endif %}</p>
    {% if estudio.extra.ultimo_error %}<p class="tag-estado sprint-aviso">Último error: {{ estudio.extra.ultimo_error }}</p>{% endif %}
  </div>
</div>

<details class="swap-card">
  <summary class="swap-card-resumen">Editar estudio</summary>
  <form method="post" action="{{ url_for('nicho.editar', cliente=cliente, eid=estudio.id) }}" class="form-experimento">
    <div class="fe-opciones">
      <label>Nombre <input name="nombre" value="{{ estudio.nombre }}" required maxlength="120"></label>
      <label>Producto del catálogo
        <select name="catalogo_id"><option value="">(escribir a mano)</option>
          {% for p in productos_nicho %}<option value="{{ p.id }}" {% if p.id == estudio.catalogo_id %}selected{% endif %}>{{ p.nombre }}</option>{% endfor %}
        </select></label>
      <label>Idioma <select name="idioma">{% for codigo, nombre in idiomas.items() %}<option value="{{ codigo }}" {% if codigo == estudio.idioma %}selected{% endif %}>{{ nombre }}</option>{% endfor %}</select></label>
    </div>
    <label>Qué vendemos <textarea name="producto" rows="2">{{ estudio.producto or '' }}</textarea></label>
    <label>Qué investigar <textarea name="tema" rows="3">{{ estudio.tema or '' }}</textarea></label>
    <div class="acciones"><button type="submit" class="btn-generar btn-sm">Guardar</button></div>
  </form>
  <form method="post" action="{{ url_for('nicho.archivar', cliente=cliente, eid=estudio.id) }}" class="inline"
        onsubmit="return confirm('{{ '¿Desarchivar este estudio?' if estudio.archivado else '¿Archivar este estudio? Se puede desarchivar después.' }}');">
    {% if estudio.archivado %}<input type="hidden" name="desarchivar" value="1">{% endif %}
    <button type="submit" class="btn-sm btn-peligro">{{ 'Desarchivar' if estudio.archivado else 'Archivar' }}</button>
  </form>
</details>

{% include "_nicho_comentarios.html" %}
{% include "_nicho_avatares.html" %}
{% endblock %}
```

- [ ] **Step 5: Escribir `templates/_nicho_comentarios.html`**

```html
{# Sección Comentarios de la página del estudio. Contexto: estudio, conteos,
   fuente_filtro, pagina_comentarios, modos_texto, fuentes_nombre. La Parte 2
   agrega aquí las tarjetas de Reddit, YouTube y Apify. #}
<h3 class="sprint-subtitulo">Comentarios</h3>
<div class="nicho-fuentes">
  <details class="swap-card" {% if not estudio.comentarios_total %}open{% endif %}>
    <summary class="swap-card-resumen">Pegar texto</summary>
    <form method="post" action="{{ url_for('nicho.comentarios_texto', cliente=cliente, eid=estudio.id) }}" class="form-experimento">
      <label>Comentarios <textarea name="texto" rows="8" required placeholder="Pega aquí los comentarios copiados de Amazon, Facebook, reseñas…"></textarea></label>
      <div class="fe-opciones">
        {% for codigo, nombre in modos_texto.items() %}
        <label class="fe-destino"><input type="radio" name="modo" value="{{ codigo }}" {% if loop.first %}checked{% endif %}> {{ nombre }}</label>
        {% endfor %}
      </div>
      <button type="submit" class="btn-generar btn-sm" {% if estudio.archivado %}disabled{% endif %}>Agregar comentarios</button>
    </form>
  </details>
  <details class="swap-card">
    <summary class="swap-card-resumen">Subir CSV o Excel</summary>
    <form method="post" action="{{ url_for('nicho.comentarios_archivo', cliente=cliente, eid=estudio.id) }}" enctype="multipart/form-data" class="form-experimento">
      <label>Archivo .csv o .xlsx (primera fila con encabezados; columna «texto» o «comentario»; opcionales «url», «likes», «fecha») <input type="file" name="archivo" accept=".csv,.xlsx" required></label>
      <button type="submit" class="btn-generar btn-sm" {% if estudio.archivado %}disabled{% endif %}>Subir</button>
    </form>
  </details>
</div>

{% if conteos %}
<p class="nicho-conteos">
  {% for fuente, n in conteos.items() %}
  <a class="tag-estado" href="{{ url_for('nicho.ver', cliente=cliente, eid=estudio.id, fuente=fuente) }}">{{ fuentes_nombre.get(fuente, fuente) }}: {{ n.total }}{% if n.excluidos %} ({{ n.excluidos }} excluidos){% endif %}</a>
  <form method="post" action="{{ url_for('nicho.comentarios_borrar', cliente=cliente, eid=estudio.id, fuente=fuente) }}" class="inline"
        onsubmit="return confirm('¿Quitar los {{ n.total }} comentarios de {{ fuentes_nombre.get(fuente, fuente) }}?');">
    <button type="submit" class="btn-sm btn-peligro" title="Quitar todos los de esta fuente">×</button>
  </form>
  {% endfor %}
  {% if fuente_filtro %}<a class="btn-sm" href="{{ url_for('nicho.ver', cliente=cliente, eid=estudio.id) }}">Ver todas las fuentes</a>{% endif %}
</p>
{% endif %}

<div class="nicho-comentarios">
  {% for c in pagina_comentarios["items"] %}
  <div class="nicho-comentario{% if c.excluido %} excluido{% endif %}">
    <small class="vacio">{{ fuentes_nombre.get(c.fuente, c.fuente) }}{% if c.puntuacion is not none %} · {{ c.puntuacion }}{% endif %}{% if c.contexto %} · {{ c.contexto }}{% endif %}{% if c.url %} · <a href="{{ c.url }}" target="_blank" rel="noopener">ver original</a>{% endif %}</small>
    <p>{{ c.texto }}</p>
    <form method="post" action="{{ url_for('nicho.comentario_excluir', cliente=cliente, cid=c.id) }}" class="inline">
      {% if c.excluido %}<input type="hidden" name="incluir" value="1">{% endif %}
      <button type="submit" class="btn-sm">{{ 'Incluir' if c.excluido else 'Excluir' }}</button>
    </form>
  </div>
  {% else %}
  <p class="vacio">Todavía no hay comentarios. Pega texto o sube un archivo arriba.</p>
  {% endfor %}
</div>
{% if pagina_comentarios.paginas > 1 %}
<p class="nicho-paginas">
  {% for p in range(1, pagina_comentarios.paginas + 1) %}
  {% if p == pagina_comentarios.pagina %}<strong>{{ p }}</strong>{% else %}<a href="{{ url_for('nicho.ver', cliente=cliente, eid=estudio.id, pagina=p, fuente=fuente_filtro) }}">{{ p }}</a>{% endif %}
  {% endfor %}
</p>
{% endif %}
```

- [ ] **Step 6: Escribir `templates/_nicho_avatares.html`**

```html
{# Sección Avatares. Contexto: estudio, nucleos, urls_comentarios, estimado,
   precio_texto, min_comentarios, trabajo_generar, niveles_conciencia, bases. #}
<h3 class="sprint-subtitulo">Avatares</h3>
<div class="acciones sprint-acciones">
  <form method="post" action="{{ url_for('nicho.generar', cliente=cliente, eid=estudio.id) }}" class="inline"
        onsubmit="return confirm('Generar avatares con Claude cuesta aprox. {{ precio_texto }} ({{ estimado.comentarios }} comentarios). ¿Seguimos?');">
    <button type="submit" class="btn-generar btn-sm" {% if not estimado.suficientes or trabajo_generar or estudio.archivado %}disabled{% endif %}>
      {{ 'Regenerar avatares' if nucleos else 'Generar avatares' }} · ≈ {{ precio_texto }} · {{ estimado.comentarios }} comentario(s)
    </button>
  </form>
  {% if not estimado.suficientes %}<small class="vacio">Hacen falta al menos {{ min_comentarios }} comentarios no excluidos.</small>{% endif %}
  {% if estimado.referencia %}<small class="vacio">Estimado con precio de referencia: el modelo {{ estimado.modelo }} no está en la tabla de precios.</small>{% endif %}
  {% if nucleos %}
  <a class="btn-sm" href="{{ url_for('nicho.exportar_md', cliente=cliente, eid=estudio.id) }}">Exportar .md</a>
  <a class="btn-sm" href="{{ url_for('nicho.exportar_xlsx', cliente=cliente, eid=estudio.id) }}">Exportar Excel</a>
  {% endif %}
</div>
{% if trabajo_generar %}
<div class="barra-progreso" id="trabajo-{{ trabajo_generar.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto">Agrupando deseos… 0% · 0s</span></div>
<script>iniciarPolling({{ trabajo_generar.job_id | tojson }}, {{ ("trabajo-" ~ trabajo_generar.job_id) | tojson }});</script>
{% endif %}
{% if estudio.extra.ultima_generacion %}
{% set ug = estudio.extra.ultima_generacion %}
<p class="vacio">Última generación: {{ ug.nucleos }} núcleo(s), {{ ug.subs }} sub-avatar(es), {{ ug.con_evidencia }} con evidencia y {{ ug.sin_evidencia }} sin evidencia, {{ ug.comentarios }} comentarios · {{ ug.fecha }}{% if ug.errores %} · {{ ug.errores }} núcleo(s) con error{% endif %}</p>
{% endif %}

{% for n in nucleos %}
<div class="swap-card nicho-nucleo">
  <h4>Núcleo {{ loop.index }}: {{ n.nombre }}</h4>
  <p><strong>Deseo:</strong> {{ n.deseo }}</p>
  {% if n.resumen %}<p class="vacio">{{ n.resumen }}</p>{% endif %}
  {% if n.extra.error %}<p class="tag-estado sprint-aviso">Este núcleo quedó sin sub-avatares: {{ n.extra.error }}</p>{% endif %}
  {% for s in n.subs %}
  <details class="nicho-sub estado-{{ s.estado }}">
    <summary>
      <strong>{{ s.nombre }}</strong>
      <span class="tag-estado">{{ 'emoción' if s.base == 'emocion' else 'experiencia con el producto' }}</span>
      <span class="tag-estado estado-nicho estado-nicho-{{ s.estado }}">{{ s.estado }}</span>
      {% if s.sin_evidencia %}<span class="tag-estado sprint-aviso">sin evidencia</span>{% endif %}
      {% if s.persona_id %}<small class="vacio">Persona #{{ s.persona_id }} · <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='sprints') }}">ver en Sprints</a></small>{% endif %}
      <br><small class="vacio">{{ s.deseo }}</small>
    </summary>
    <form method="post" action="{{ url_for('nicho.avatar_editar', cliente=cliente, aid=s.id) }}" class="form-experimento">
      <div class="fe-opciones">
        <label>Nombre / arquetipo <input name="nombre" value="{{ s.nombre }}" required></label>
        <label>Base <select name="base">{% for b in bases %}<option value="{{ b }}" {% if b == s.base %}selected{% endif %}>{{ 'emoción' if b == 'emocion' else 'experiencia con el producto' }}</option>{% endfor %}</select></label>
        <label>Edad <input name="edad_rango" value="{{ s.edad_rango or '' }}" placeholder="30-45" class="mini-input"></label>
      </div>
      <label>Deseo (frase de cabecera) <input name="deseo" value="{{ s.deseo or '' }}" maxlength="300"></label>
      <label>Demographics (ASL) <textarea name="demografia" rows="2">{{ s.demografia or '' }}</textarea></label>
      <label>Emoción <input name="emocion" value="{{ s.emocion or '' }}"></label>
      <label>Qué quiere que los demás vean en ella <textarea name="identidad_quiere_que_vean" rows="2">{{ s.identidad.quiere_que_vean or '' }}</textarea></label>
      <label>Beliefs about self <textarea name="identidad_cree_de_si" rows="2">{{ s.identidad.cree_de_si or '' }}</textarea></label>
      <label>Qué quiere lograr en la sociedad <textarea name="identidad_quiere_lograr" rows="2">{{ s.identidad.quiere_lograr or '' }}</textarea></label>
      <label>Cómo nuestro producto la ayuda a lograrlo <textarea name="encaje_producto" rows="2">{{ s.encaje_producto or '' }}</textarea></label>
      <label>Soluciones que probó y por qué fallaron (una por línea: «qué usó :: problema; problema») <textarea name="soluciones_previas" rows="3">{{ s.soluciones_previas | soluciones_texto }}</textarea></label>
      <label>Su día a día (una situación por línea) <textarea name="situaciones" rows="3">{{ (s.situaciones or []) | join('\n') }}</textarea></label>
      <label>Comportamiento <textarea name="comportamiento" rows="2">{{ s.comportamiento or '' }}</textarea></label>
      <div class="fe-opciones">
        <label>Nivel de conciencia <select name="conciencia_nivel"><option value="">(sin señales)</option>{% for niv in niveles_conciencia %}<option value="{{ niv }}" {% if niv == s.conciencia.nivel %}selected{% endif %}>{{ niv | replace('_', ' ') }}</option>{% endfor %}</select></label>
        <label>Por qué <input name="conciencia_detalle" value="{{ s.conciencia.detalle or '' }}"></label>
      </div>
      <label>Tono de voz <input name="tono" value="{{ s.tono or '' }}"></label>
      <label>Palabras clave (coma) <input name="palabras_clave" value="{{ (s.palabras_clave or []) | join(', ') }}"></label>
      <div class="acciones"><button type="submit" class="btn-generar btn-sm">Guardar</button></div>
    </form>
    <div class="nicho-evidencia">
      <strong>Citas textuales</strong>
      {% for e in s.evidencia %}
      <blockquote class="nicho-cita">«{{ e.cita }}»{% if urls_comentarios.get(e.comentario_id) %} <a href="{{ urls_comentarios.get(e.comentario_id) }}" target="_blank" rel="noopener">ver original</a>{% endif %}</blockquote>
      {% else %}
      <p class="vacio">Ninguna cita sobrevivió a la verificación: decide tú si este avatar vale.</p>
      {% endfor %}
    </div>
    <div class="acciones">
      {% if s.estado != 'aprobado' %}
      <form method="post" action="{{ url_for('nicho.avatar_aprobar', cliente=cliente, aid=s.id) }}" class="inline"><button type="submit" class="btn-generar btn-sm">Aprobar → persona</button></form>
      {% else %}
      <form method="post" action="{{ url_for('nicho.avatar_aprobar', cliente=cliente, aid=s.id) }}" class="inline"><button type="submit" class="btn-sm">Volver a aprobar (actualiza la persona)</button></form>
      {% endif %}
      {% if s.estado != 'descartado' %}
      <form method="post" action="{{ url_for('nicho.avatar_descartar', cliente=cliente, aid=s.id) }}" class="inline"><button type="submit" class="btn-sm btn-peligro">Descartar</button></form>
      {% endif %}
    </div>
  </details>
  {% else %}
  <p class="vacio">Sin sub-avatares en este núcleo.</p>
  {% endfor %}
</div>
{% else %}
{% if not trabajo_generar %}<p class="vacio">Todavía no hay avatares. Con {{ min_comentarios }} comentarios o más, el botón de arriba los genera.</p>{% endif %}
{% endfor %}
```

- [ ] **Step 7: Estilos al final de `static/style.css`**

```css
/* --- Nicho y avatares (docs/superpowers/plans/2026-09-18-nicho-avatares-parte1.md) --- */
.nicho-fuentes { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: .8rem; margin-bottom: .8rem; }
.nicho-conteos { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.nicho-comentarios { display: flex; flex-direction: column; gap: .4rem; }
.nicho-comentario { padding: .5rem .8rem; border: 1px solid var(--border); border-radius: 8px; }
.nicho-comentario.excluido { opacity: .5; }
.nicho-comentario p { margin: .2rem 0; }
.nicho-paginas { display: flex; gap: .5rem; }
.nicho-nucleo { margin-top: .8rem; padding: .8rem 1rem; }
.nicho-sub { margin: .5rem 0; padding: .5rem .8rem; border: 1px solid var(--border); border-radius: 8px; }
.nicho-sub.estado-aprobado { border-color: var(--accent); }
.nicho-sub.estado-descartado { opacity: .55; }
.nicho-cita { margin: .3rem 0; padding-left: .8rem; border-left: 3px solid var(--border); font-style: italic; }
.estado-nicho-armando { background: rgba(77, 141, 255, .15); }
.estado-nicho-generando { background: rgba(232, 179, 57, .15); }
.estado-nicho-revisando, .estado-nicho-aprobado { background: rgba(62, 207, 142, .2); }
.estado-nicho-propuesto { background: rgba(124, 92, 255, .15); }
.estado-nicho-descartado { background: rgba(255, 95, 122, .15); }
```

- [ ] **Step 8: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q`
Expected: PASS (todas).

- [ ] **Step 9: Commit**

```bash
git add templates/nicho_estudio.html templates/_nicho_nav.html templates/_nicho_comentarios.html templates/_nicho_avatares.html static/style.css tests/test_rutas_nicho.py
git commit -m "Nicho: página del estudio (comentarios, generar con costo a la vista, revisión de avatares, exportar)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Verificación final y documentación

**Files:**
- Modify: `CLAUDE.md` (sección Architecture, después del párrafo de Sprints), `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (§2, §3.1, §4.2, §7)

- [ ] **Step 1: Suite completa y compilación**

Run: `venv/bin/python3 -m pytest -q`
Expected: todo PASS (incluida `tests/test_sprints_db.py::test_alembic_tiene_una_sola_cabeza`).

Run: `for f in nicho/*.py nicho/fuentes/*.py tareas/nicho.py db.py dashboard.py gastos.py sprints/datos.py migrations/versions/0011_nicho.py; do python3 -m py_compile "$f" || echo "FALLA $f"; done`
Expected: sin salida.

- [ ] **Step 2: Migración sobre la base real de desarrollo**

Run: `venv/bin/alembic upgrade head && venv/bin/alembic current`
Expected: `0011 (head)`.

- [ ] **Step 3: Párrafo en `CLAUDE.md`** (después del párrafo **Sprints de contenido**, antes de **Crear (FlowPlus)**)

```markdown
**Nicho y avatares** (`nicho/` + `tareas/nicho.py`, spec
`docs/superpowers/specs/2026-09-18-nicho-avatares-design.md`): personas nacidas de
comentarios reales. Tablas `estudio`, `comentario` (única por estudio + fuente +
fuente_id, nunca guarda el autor) y `avatar` (núcleos por deseo con `padre_id`
NULL; sub-avatares colgando de ellos con los campos de las dos plantillas del
cliente: identidad, soluciones previas, situaciones, conciencia, encaje del
producto, evidencia). `nicho/datos.py` es el único escritor; `recalcular` deriva
`armando | generando | revisando`. Las fuentes entran por `nicho/fuentes/base.py`
(`normalizar_comentario`, `ErrorFuente.usuario`) y el registro perezoso
`nicho.fuentes.por_tipo`; Parte 1 trae `texto` y `csv` (corren en la ruta), Parte 2
agrega Reddit, YouTube y Apify con la tarea `nicho_recolectar`.
`nicho/avatares.py` hace dos pasadas con Claude (`generador_prompts.MODEL`):
núcleos, luego sub-avatares por núcleo; cada cita se verifica literal contra el
comentario (`verificar_evidencia`) y la que no aparece se descarta — un
sub-avatar sin citas queda `sin_evidencia`, no se borra. `estimar_costo` (tokens ×
`PRECIOS_USD_POR_MILLON`) se muestra en el botón antes de encolar
`nicho_generar_avatares` (`max_intentos=1`; el gasto real va a `gastos` como tipo
`avatares`). Regenerar borra `propuesto`/`descartado` y conserva los `aprobado`.
Aprobar un sub-avatar crea (o actualiza) una `persona` con origen `investigada`
(`persona_desde_avatar`); descartar la archiva. Exportación `.md` y `.xlsx` con la
plantilla de la hoja "Personas" (`nicho/exportar.py`). UI: pestaña **Nicho**
(`_tab_nicho.html`) y página propia del estudio (`nicho_estudio.html`), Blueprint
`nicho/rutas.py` bajo `/cliente/<cliente>/nicho/...`.
```

- [ ] **Step 4: Ajustes al spec** (lo que la implementación afinó)

En §2: `Migración 0009_nicho (down_revision = '0008')` → `Migración 0011_nicho (down_revision = '0010')`, y en §13/encabezado donde diga `0009` para esta migración. En §3.1: "exige `fuente_id`" → "cae al hash del texto como `fuente_id` cuando la fuente no trae uno". En §4.2: "`max_tokens` 2 000 en la pasada 1, 4 000 en la 2" → "`max_tokens` 4 000 en la pasada 1 y 8 000 en la 2 (tope de corte, no de costo; el estimado usa 1 500 y 3 000 por núcleo de salida esperada)" y en §4.4 la misma corrección de la salida estimada. En §7: "elige el estudio abierto con `?nicho=<estudio_id>`" → "la pestaña lista los estudios; cada estudio abre en su propia página `nicho_estudio.html` (`GET /cliente/<cliente>/nicho/<id>`), como `sprint_detalle.html`".

- [ ] **Step 5: Prueba manual (opcional; gasta centavos de Claude, pedir el visto bueno antes)**

Con `.env` completo: `python dashboard.py` en una terminal y `venv/bin/python3 worker.py` en otra. En un proyecto: pestaña Nicho → Nuevo estudio → Pegar texto con 20+ comentarios reales → el botón muestra `≈ US$ 0,0x · N comentario(s)` → Generar → la barra avanza por "Agrupando deseos" y "Armando sub-avatares" → la página se recarga con núcleos y sub-avatares, citas con «…» → Aprobar uno → aparece en Sprints › Personas con "investigada" → Exportar Excel abre con la hoja "Personas". Configuración › Gasto muestra una fila `avatares`.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-18-nicho-avatares-design.md
git commit -m "Docs: Nicho y avatares en CLAUDE.md; spec ajustado a la migración 0011 y a la página propia del estudio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
