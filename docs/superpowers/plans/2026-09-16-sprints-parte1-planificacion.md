# Sprints — Parte 1: planificación (personas, temporadas, sprint, campañas, referencias) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un proyecto pueda crear un sprint de contenido como una matriz persona × producto × temporada (campañas únicas por combinación), cargar referencias visuales de forma progresiva con intención y descripción, verlas analizadas por Claude, y seguir el progreso por campaña y por sprint desde una pestaña nueva "Sprints".

**Architecture:** Tablas nuevas en SQLite (`persona`, `temporada`, `sprint`, `campana`, `referencia`, `campana_pieza`, `sprint_evento`) con migración Alembic; un paquete `sprints/` de módulos pequeños (`datos.py` CRUD y validaciones, `estado.py` recálculo de estados, `progreso.py` funciones puras, `calendario.py` presets, `archivos.py` subidas a R2, `analisis.py` y `sugerencias.py` con Claude) y un Blueprint `sprints/rutas.py` montado en `/cliente/<cliente>/sprints/...`; tareas del worker en `tareas/sprints.py` (análisis de referencias, sugerencia de personas, referencia desde link). La pestaña Sprints vive en `cliente.html` como las demás; el detalle del sprint y las referencias de una campaña son páginas propias que extienden `base.html`.

**Tech Stack:** Flask 3.1/Jinja, SQLAlchemy Core (SQLite WAL) + Alembic, worker/cola (`trabajos.encolar`), Anthropic (visión y texto), Cloudflare R2 (`storage/r2_uploader`), ffmpeg (fotogramas), pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-sprints-design.md` — §0 (relación con el motor), Parte 1 (§1.1 modelo de datos, §1.2 validaciones, §1.3 estados, §1.4 progreso, §1.5 análisis, §1.6 experiencia, §1.7 módulos y pruebas). `campana_pieza` se crea aquí (§1.1) pero se usa en la Parte 2.

## Global Constraints

- Ninguna generación de imágenes o videos ocurre en esta parte. Las únicas llamadas pagas son a Claude (análisis de una referencia al subirla, sugerencia de personas a pedido): centavos, disparadas por una acción explícita de la persona.
- Todas las tablas nuevas llevan `cliente`, `creado_en`, `actualizado_en` (`db._comunes()`), salvo `sprint_evento` (`cliente` + `creado_en`, como `evento`). Se agregan al FINAL de `db.py`, justo antes de `crear_todo`, para minimizar conflictos con el bloque 5, que también toca `db.py`.
- Migración: archivo `migrations/versions/0006_sprints.py`, `revision = "0006"`. Antes de escribirla, correr `venv/bin/alembic heads` y usar esa cabeza como `down_revision` (hoy `0004` en main; `0005` si el bloque 5 ya se integró). Nunca reutilizar un número existente. Si al integrar la rama aparecen dos cabezas, crear una migración de merge con `venv/bin/alembic merge heads -m "merge sprints"`.
- Unicidad persona + producto + temporada por sprint: índice único `uq_campana_combinacion` en la base **y** validación con mensaje en la interfaz ("ya existe en la campaña N").
- Estados exactamente estos, en minúsculas: sprint `planeando → referencias → listo_para_generar → generando → revision → completado`; campaña `planeada → referencias → ideas_propuestas → ideas_aprobadas → generando → revision → completada`. Los estados se guardan y `sprints.estado.recalcular` los vuelve a derivar después de cada evento.
- Una referencia sin descripción se guarda en `borrador` y no suma al progreso; con descripción pasa a `lista`.
- Copy en español. Rutas en el Blueprint `sprints` (no en `dashboard.py`); `dashboard.py` solo registra el Blueprint y agrega `**sprints_rutas.contexto(cliente)` al render de `cliente.html`.
- Sin red en las pruebas: Claude, R2 y ffmpeg se reemplazan con `monkeypatch`. Suite verde: `venv/bin/python -m pytest -q`. `python3 -m py_compile` de cada archivo tocado antes de cada commit.
- Git local: usar `/opt/homebrew/bin/git` (el de Xcode pide aceptar licencia). Commits pequeños, uno por tarea, mensaje en español, con la línea `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- No tocar: `experimentos.py`, `lanzador.py`, `decisor.py`, `catalogo_productos.py`, la tabla `producto`, ni nada del bloque 5/6. Los cambios a `dashboard.py`, `db.py`, `tareas/__init__.py`, `proyectos.py`, `cliente.html`, `_sidebar.html` y `style.css` son aditivos.

---

## Estructura de archivos

- Modify: `db.py` — siete tablas nuevas al final (antes de `crear_todo`).
- Create: `migrations/versions/0006_sprints.py`.
- Create: `sprints/__init__.py` (vacío, con docstring).
- Create: `sprints/datos.py` — CRUD y validaciones de personas, temporadas, sprints, campañas, referencias y eventos.
- Create: `sprints/calendario.py` — presets del calendario comercial por país y adopción como temporada.
- Modify: `proyectos.py` — `pais(cliente)`, `guardar_pais(cliente, pais)`.
- Create: `sprints/archivos.py` — guardar subidas (imagen/video) en disco y R2, fotograma de video.
- Create: `sprints/progreso.py` — progreso por campaña y sprint, cobertura de intención (puras).
- Create: `sprints/estado.py` — `estado_campana`, `estado_sprint` (puras) y `recalcular` (escribe).
- Create: `sprints/analisis.py` — análisis de una referencia con Claude (visión), JSON validado.
- Create: `sprints/sugerencias.py` — personas sugeridas por Claude desde la guía de marca y el catálogo.
- Create: `tareas/sprints.py` — `sprint_analizar_referencia`, `sprint_sugerir_personas`, `sprint_referencia_link`; ids de trabajo y helpers `encolar_*`.
- Modify: `tareas/__init__.py` — `cargar_todas` importa `sprints`.
- Create: `sprints/rutas.py` — Blueprint con todas las rutas y `contexto(cliente)`.
- Modify: `dashboard.py` — registrar el Blueprint; `**sprints_rutas.contexto(cliente)` en `ver_cliente`.
- Create: `templates/_tab_sprints.html` (lista + asistente + personas + temporadas), `templates/sprint_detalle.html`, `templates/campana_referencias.html`, `templates/_sprint_nav.html`.
- Modify: `templates/cliente.html` (sección y panel `sprints`), `templates/_sidebar.html` (botón), `static/style.css` (bloque `/* Sprints */`).
- Modify: `CLAUDE.md` — sección "Sprints de contenido".
- Tests: `tests/test_sprints_db.py`, `tests/test_sprints_datos.py`, `tests/test_sprints_calendario.py`, `tests/test_sprints_progreso_estado.py`, `tests/test_sprints_analisis.py`, `tests/test_tareas_sprints.py`, `tests/test_rutas_sprints.py`.

---

### Task 1: Tablas nuevas en `db.py` y migración `0006_sprints`

**Files:**
- Modify: `db.py` (al final, antes de `def crear_todo`)
- Create: `migrations/versions/0006_sprints.py`
- Test: `tests/test_sprints_db.py`

**Interfaces:**
- Produces: `db.persona`, `db.temporada`, `db.sprint`, `db.campana`, `db.referencia`, `db.campana_pieza`, `db.sprint_evento` (objetos `sqlalchemy.Table`), índice único `uq_campana_combinacion`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_sprints_db.py
import sqlalchemy as sa


def test_tablas_de_sprints_existen(base_temporal):
    db = base_temporal
    nombres = set(sa.inspect(db.engine()).get_table_names())
    assert {"persona", "temporada", "sprint", "campana", "referencia", "campana_pieza", "sprint_evento"} <= nombres


def _sprint_basico(db):
    ahora = db.ahora()
    with db.conectar() as con:
        pid = con.execute(db.persona.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                     nombre="Premium", origen="manual")).inserted_primary_key[0]
        tid = con.execute(db.temporada.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                       nombre="Verano", inicio="2026-06-01", fin="2026-07-15", tipo="propia")).inserted_primary_key[0]
        sid = con.execute(db.sprint.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                    nombre="Octubre", inicio="2026-10-01", fin="2026-10-31", estado="planeando")).inserted_primary_key[0]
    return pid, tid, sid


def test_campana_unica_por_combinacion(base_temporal):
    db = base_temporal
    pid, tid, sid = _sprint_basico(db)
    ahora = db.ahora()
    fila = dict(cliente="acme", creado_en=ahora, actualizado_en=ahora, sprint_id=sid, persona_id=pid,
                catalogo_id="espejo_led", temporada_id=tid, n_videos=10, n_imagenes=5, estado="planeada")
    with db.conectar() as con:
        con.execute(db.campana.insert().values(**fila))
    import pytest
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(db.campana.insert().values(**fila))
    # Misma persona y producto en OTRA temporada sí entra.
    with db.conectar() as con:
        tid2 = con.execute(db.temporada.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                        nombre="Navidad", inicio="2026-11-15", fin="2026-12-31", tipo="comercial")).inserted_primary_key[0]
        con.execute(db.campana.insert().values(**dict(fila, temporada_id=tid2)))


def test_migracion_0006_crea_las_tablas(tmp_path, monkeypatch):
    """La migración real (no metadata.create_all) deja las mismas tablas."""
    import os
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    nombres = set(sa.inspect(db.engine()).get_table_names())
    assert {"persona", "temporada", "sprint", "campana", "referencia", "campana_pieza", "sprint_evento"} <= nombres
    indices = {i["name"] for i in sa.inspect(db.engine()).get_indexes("campana")} | \
              {u["name"] for u in sa.inspect(db.engine()).get_unique_constraints("campana")}
    assert "uq_campana_combinacion" in indices
    db._reset_para_tests()
```

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `venv/bin/python -m pytest tests/test_sprints_db.py -q`
Expected: FAIL (`AttributeError: module 'db' has no attribute 'persona'` y tablas ausentes).

- [ ] **Step 3: Agregar las tablas a `db.py`** (pegar justo antes de `def crear_todo():`)

```python
# --- Sprints de contenido (docs/superpowers/specs/2026-09-16-sprints-design.md, Parte 1) ---

persona = Table("persona", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("resumen", String(200)),
    Column("descripcion", Text),
    Column("edad_rango", String(20)),
    Column("tono", Text),
    Column("senales_visuales", JSON, default=list),
    Column("palabras_clave", JSON, default=list),
    Column("color", String(7)),
    Column("origen", String(12), nullable=False, default="manual"),      # manual|sugerida_ia
    Column("archivada", Boolean, default=False),
    Column("extra", JSON, default=dict),
)

temporada = Table("temporada", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(120), nullable=False),
    Column("inicio", String(10), nullable=False),                        # YYYY-MM-DD
    Column("fin", String(10), nullable=False),
    Column("contexto", Text),
    Column("mood_visual", JSON, default=dict),
    Column("tipo", String(12), nullable=False, default="propia"),        # comercial|estacional|propia
    Column("archivada", Boolean, default=False),
    Column("extra", JSON, default=dict),
)

sprint = Table("sprint", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("nombre", String(200), nullable=False),
    Column("inicio", String(10), nullable=False),
    Column("fin", String(10), nullable=False),
    Column("estado", String(20), nullable=False, default="planeando"),
    Column("destinos", JSON, default=list),                             # ["es_CO", ...]
    Column("referencias_objetivo_defecto", Integer, default=5),
    Column("notas", Text),
    Column("archivado", Boolean, default=False),
    Column("extra", JSON, default=dict),                                # listo_manual, qa_umbral, modelos del lote
)

campana = Table("campana", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("sprint_id", Integer, sa.ForeignKey("sprint.id"), nullable=False, index=True),
    Column("persona_id", Integer, sa.ForeignKey("persona.id"), nullable=False),
    Column("catalogo_id", String(120), nullable=False),                  # carpeta del producto en el catálogo de Crear
    Column("producto_id", Integer, sa.ForeignKey("producto.id")),        # bloque 5, cuando enlace catálogo y tabla
    Column("temporada_id", Integer, sa.ForeignKey("temporada.id"), nullable=False),
    Column("n_videos", Integer, nullable=False, default=0),
    Column("n_imagenes", Integer, nullable=False, default=0),
    Column("referencias_objetivo", Integer, default=5),
    Column("estado", String(20), nullable=False, default="planeada"),
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("sprint_id", "persona_id", "catalogo_id", "temporada_id", name="uq_campana_combinacion"),
)

referencia = Table("referencia", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("campana_id", Integer, sa.ForeignKey("campana.id"), nullable=False, index=True),
    Column("tipo", String(6), nullable=False),                          # imagen|video
    Column("url", Text, nullable=False),
    Column("frame_url", Text),
    Column("ruta_local", Text),
    Column("origen", String(12), nullable=False, default="archivo"),    # archivo|link|catalogo|reutilizada
    Column("titulo", String(200)),
    Column("intencion", JSON, default=list),                            # etiquetas de sprints.datos.INTENCIONES
    Column("intencion_otro", String(200)),
    Column("descripcion", Text),
    Column("analisis", JSON),
    Column("analisis_estado", String(10), default="pendiente"),         # pendiente|listo|error
    Column("estado", String(8), nullable=False, default="borrador"),    # borrador|lista
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
)

campana_pieza = Table("campana_pieza", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("campana_id", Integer, sa.ForeignKey("campana.id"), nullable=False, index=True),
    Column("tipo", String(6), nullable=False),                          # video|imagen
    Column("titulo", String(200)),
    Column("escena", Text),
    Column("sonido", Text),
    Column("enfoque", String(20)),
    Column("gancho", String(200)),
    Column("referencias_ids", JSON, default=list),
    Column("duracion_s", Float),
    Column("plataformas", JSON, default=list),
    Column("estado_idea", String(10), nullable=False, default="propuesta"),   # propuesta|aprobada|descartada
    Column("cf_id", String(60), index=True),                            # legado_id de la sesión de Crear
    Column("qa", JSON),
    Column("revision", String(10), nullable=False, default="pendiente"),      # pendiente|aprobada|rechazada
    Column("revision_motivo", Text),
    Column("textos", JSON),
    Column("orden", Integer, default=0),
    Column("extra", JSON, default=dict),
)

sprint_evento = Table("sprint_evento", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), nullable=False, index=True),
    Column("sprint_id", Integer, sa.ForeignKey("sprint.id"), nullable=False, index=True),
    Column("campana_id", Integer, sa.ForeignKey("campana.id")),
    Column("tipo", String(30), nullable=False),
    Column("mensaje", Text),
    Column("datos", JSON, default=dict),
    Column("creado_en", String(19), nullable=False),
)
```

- [ ] **Step 4: Escribir la migración** (`migrations/versions/0006_sprints.py`; confirmar `down_revision` con `venv/bin/alembic heads`)

```python
"""sprints de contenido: persona, temporada, sprint, campana, referencia, campana_pieza, sprint_evento

Revision ID: 0006
Revises: 0004
Create Date: 2026-09-16 00:00:00.000000

Parte 1 del spec docs/superpowers/specs/2026-09-16-sprints-design.md.
Si `alembic heads` muestra otra cabeza (p. ej. 0005 del bloque 5), poner esa en
`down_revision` antes de aplicar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _comunes():
    return [
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
    ]


def upgrade() -> None:
    op.create_table('persona',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('resumen', sa.String(length=200)),
        sa.Column('descripcion', sa.Text()),
        sa.Column('edad_rango', sa.String(length=20)),
        sa.Column('tono', sa.Text()),
        sa.Column('senales_visuales', sa.JSON()),
        sa.Column('palabras_clave', sa.JSON()),
        sa.Column('color', sa.String(length=7)),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='manual'),
        sa.Column('archivada', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_persona_cliente', 'persona', ['cliente'])

    op.create_table('temporada',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('inicio', sa.String(length=10), nullable=False),
        sa.Column('fin', sa.String(length=10), nullable=False),
        sa.Column('contexto', sa.Text()),
        sa.Column('mood_visual', sa.JSON()),
        sa.Column('tipo', sa.String(length=12), nullable=False, server_default='propia'),
        sa.Column('archivada', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_temporada_cliente', 'temporada', ['cliente'])

    op.create_table('sprint',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('inicio', sa.String(length=10), nullable=False),
        sa.Column('fin', sa.String(length=10), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='planeando'),
        sa.Column('destinos', sa.JSON()),
        sa.Column('referencias_objetivo_defecto', sa.Integer(), server_default='5'),
        sa.Column('notas', sa.Text()),
        sa.Column('archivado', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_sprint_cliente', 'sprint', ['cliente'])

    op.create_table('campana',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('sprint_id', sa.Integer(), sa.ForeignKey('sprint.id'), nullable=False),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('persona.id'), nullable=False),
        sa.Column('catalogo_id', sa.String(length=120), nullable=False),
        sa.Column('producto_id', sa.Integer(), sa.ForeignKey('producto.id')),
        sa.Column('temporada_id', sa.Integer(), sa.ForeignKey('temporada.id'), nullable=False),
        sa.Column('n_videos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('n_imagenes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('referencias_objetivo', sa.Integer(), server_default='5'),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='planeada'),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sprint_id', 'persona_id', 'catalogo_id', 'temporada_id', name='uq_campana_combinacion'))
    op.create_index('ix_campana_cliente', 'campana', ['cliente'])
    op.create_index('ix_campana_sprint_id', 'campana', ['sprint_id'])

    op.create_table('referencia',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id'), nullable=False),
        sa.Column('tipo', sa.String(length=6), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('frame_url', sa.Text()),
        sa.Column('ruta_local', sa.Text()),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='archivo'),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('intencion', sa.JSON()),
        sa.Column('intencion_otro', sa.String(length=200)),
        sa.Column('descripcion', sa.Text()),
        sa.Column('analisis', sa.JSON()),
        sa.Column('analisis_estado', sa.String(length=10), server_default='pendiente'),
        sa.Column('estado', sa.String(length=8), nullable=False, server_default='borrador'),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_referencia_cliente', 'referencia', ['cliente'])
    op.create_index('ix_referencia_campana_id', 'referencia', ['campana_id'])

    op.create_table('campana_pieza',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id'), nullable=False),
        sa.Column('tipo', sa.String(length=6), nullable=False),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('escena', sa.Text()),
        sa.Column('sonido', sa.Text()),
        sa.Column('enfoque', sa.String(length=20)),
        sa.Column('gancho', sa.String(length=200)),
        sa.Column('referencias_ids', sa.JSON()),
        sa.Column('duracion_s', sa.Float()),
        sa.Column('plataformas', sa.JSON()),
        sa.Column('estado_idea', sa.String(length=10), nullable=False, server_default='propuesta'),
        sa.Column('cf_id', sa.String(length=60)),
        sa.Column('qa', sa.JSON()),
        sa.Column('revision', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('revision_motivo', sa.Text()),
        sa.Column('textos', sa.JSON()),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_campana_pieza_cliente', 'campana_pieza', ['cliente'])
    op.create_index('ix_campana_pieza_campana_id', 'campana_pieza', ['campana_id'])
    op.create_index('ix_campana_pieza_cf_id', 'campana_pieza', ['cf_id'])

    op.create_table('sprint_evento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('sprint_id', sa.Integer(), sa.ForeignKey('sprint.id'), nullable=False),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id')),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('mensaje', sa.Text()),
        sa.Column('datos', sa.JSON()),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_sprint_evento_cliente', 'sprint_evento', ['cliente'])
    op.create_index('ix_sprint_evento_sprint_id', 'sprint_evento', ['sprint_id'])


def downgrade() -> None:
    for tabla in ('sprint_evento', 'campana_pieza', 'referencia', 'campana', 'sprint', 'temporada', 'persona'):
        op.drop_table(tabla)
```

- [ ] **Step 5: Correr las pruebas y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_db.py tests/test_db.py -q`
Expected: PASS (3 + 5 pruebas).

- [ ] **Step 6: Aplicar la migración a la base local y commitear**

```bash
venv/bin/alembic upgrade head
python3 -m py_compile db.py migrations/versions/0006_sprints.py
/opt/homebrew/bin/git add db.py migrations/versions/0006_sprints.py tests/test_sprints_db.py
/opt/homebrew/bin/git commit -m "Sprints: tablas persona, temporada, sprint, campana, referencia, campana_pieza y sprint_evento (migración 0006)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `sprints/datos.py` — personas y temporadas

**Files:**
- Create: `sprints/__init__.py`, `sprints/datos.py`
- Test: `tests/test_sprints_datos.py`

**Interfaces:**
- Produces: `ErrorDatos(ValueError)`, `CampanaDuplicada(ErrorDatos)`, constantes `INTENCIONES`, `INTENCIONES_NOMBRE`, `ESTADOS_SPRINT`, `ESTADOS_CAMPANA`, `TIPOS_TEMPORADA`, `ORIGENES_REFERENCIA`; `crear_persona(cliente, nombre, resumen="", descripcion="", edad_rango="", tono="", senales_visuales=None, palabras_clave=None, color=None, origen="manual") -> int`, `actualizar_persona(cliente, persona_id, **campos) -> bool`, `archivar_persona(cliente, persona_id, archivada=True) -> bool`, `personas(cliente, incluir_archivadas=False) -> list[dict]`, `persona(cliente, persona_id) -> dict|None`; `crear_temporada(cliente, nombre, inicio, fin, contexto="", mood_visual=None, tipo="propia") -> int`, `actualizar_temporada`, `archivar_temporada`, `temporadas(cliente, incluir_archivadas=False)`, `temporada(cliente, temporada_id)`. Helpers internos reutilizados por las Tasks 4 y 5: `_fecha`, `_rango`, `_a_dict`, `_fila`, `_actualizar`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_datos.py
import pytest


def test_persona_crear_listar_editar_archivar(base_temporal):
    from sprints import datos
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", tono="cercano y experto",
                              senales_visuales=["cocina moderna", "luz natural"], palabras_clave=["premium"])
    p = datos.persona("acme", pid)
    assert p["nombre"] == "Cliente Premium" and p["senales_visuales"] == ["cocina moderna", "luz natural"]
    assert p["origen"] == "manual" and p["archivada"] is False
    assert datos.actualizar_persona("acme", pid, tono="directo") and datos.persona("acme", pid)["tono"] == "directo"
    assert datos.personas("otro") == []            # aislamiento por cliente
    assert datos.persona("otro", pid) is None
    datos.archivar_persona("acme", pid)
    assert datos.personas("acme") == [] and len(datos.personas("acme", incluir_archivadas=True)) == 1


def test_persona_valida_nombre_y_origen(base_temporal):
    from sprints import datos
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "   ")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_persona("acme", "X", origen="magia")
    pid = datos.crear_persona("acme", "X")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, nombre="")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_persona("acme", pid, cliente="otro")   # campo no editable


def test_temporada_valida_fechas(base_temporal):
    from sprints import datos
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", tipo="comercial",
                                mood_visual={"paleta": ["#B3001B"]})
    t = datos.temporada("acme", tid)
    assert t["inicio"] == "2026-11-15" and t["mood_visual"] == {"paleta": ["#B3001B"]}
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-12-31", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "ayer", "2026-11-15")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_temporada("acme", "Mal", "2026-01-01", "2026-02-01", tipo="rara")
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["Navidad"]
    datos.archivar_temporada("acme", tid)
    assert datos.temporadas("acme") == []
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'sprints'`.

- [ ] **Step 3: Crear `sprints/__init__.py` y `sprints/datos.py`**

```python
# sprints/__init__.py
"""Sprints de contenido: planificación (persona × producto × temporada),
referencias con intención, producción por lotes y revisión. Spec:
docs/superpowers/specs/2026-09-16-sprints-design.md."""
```

```python
# sprints/datos.py
"""
Datos de los sprints de contenido (Parte 1 del spec): personas, temporadas,
sprints, campañas, referencias y eventos. Solo SQLAlchemy Core sobre
data/creatv.db; nada de proveedores ni de Flask. Las validaciones de negocio
(fechas, cantidades, unicidad) viven aquí; la validación contra el catálogo
de productos la hace la ruta, para que este módulo se pruebe sin carpetas de
clientes.
"""
from datetime import date

import sqlalchemy as sa

import db

INTENCIONES = ("estilo_visual", "composicion", "paleta", "movimiento_camara", "tipografia",
               "transiciones", "storytelling", "iluminacion", "angulo_producto", "otro")
INTENCIONES_NOMBRE = {
    "estilo_visual": "Estilo visual", "composicion": "Composición", "paleta": "Paleta de colores",
    "movimiento_camara": "Movimiento de cámara", "tipografia": "Tipografía", "transiciones": "Transiciones",
    "storytelling": "Storytelling", "iluminacion": "Iluminación", "angulo_producto": "Ángulo de producto",
    "otro": "Otro",
}
ESTADOS_SPRINT = ("planeando", "referencias", "listo_para_generar", "generando", "revision", "completado")
ESTADOS_CAMPANA = ("planeada", "referencias", "ideas_propuestas", "ideas_aprobadas", "generando", "revision", "completada")
TIPOS_TEMPORADA = ("comercial", "estacional", "propia")
ORIGENES_REFERENCIA = ("archivo", "link", "catalogo", "reutilizada")
ORIGENES_PERSONA = ("manual", "sugerida_ia")

_PERSONA_COLS = ("nombre", "resumen", "descripcion", "edad_rango", "tono", "senales_visuales", "palabras_clave",
                 "color", "origen", "archivada", "extra")
_TEMPORADA_COLS = ("nombre", "inicio", "fin", "contexto", "mood_visual", "tipo", "archivada", "extra")
_SPRINT_COLS = ("nombre", "inicio", "fin", "estado", "destinos", "referencias_objetivo_defecto", "notas",
                "archivado", "extra")
_CAMPANA_COLS = ("n_videos", "n_imagenes", "referencias_objetivo", "estado", "orden", "extra", "producto_id")
_REFERENCIA_COLS = ("titulo", "intencion", "intencion_otro", "descripcion", "analisis", "analisis_estado", "orden",
                    "extra", "frame_url", "ruta_local")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


class CampanaDuplicada(ErrorDatos):
    """Ya hay una campaña con esa persona, producto y temporada en el sprint."""


# ------------------------------------------------------------ helpers ---

def _fecha(valor, campo):
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        raise ErrorDatos(f"La fecha de {campo} no es válida (usa AAAA-MM-DD).")


def _rango(inicio, fin, que):
    i, f = _fecha(inicio, "inicio"), _fecha(fin, "fin")
    if i >= f:
        raise ErrorDatos(f"En {que}, la fecha de inicio debe ser anterior a la de fin.")
    return i.isoformat(), f.isoformat()


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


def _texto(v, largo=None):
    v = (v or "").strip()
    return v[:largo] if largo else v


# ----------------------------------------------------------- personas ---

def crear_persona(cliente, nombre, resumen="", descripcion="", edad_rango="", tono="", senales_visuales=None,
                  palabras_clave=None, color=None, origen="manual"):
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
            color=color, origen=origen, archivada=False, extra={})).inserted_primary_key[0]


def actualizar_persona(cliente, persona_id, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La persona necesita un nombre.")
    if "origen" in campos and campos["origen"] not in ORIGENES_PERSONA:
        raise ErrorDatos(f"Origen de persona inválido: {campos['origen']}")
    with db.conectar() as con:
        return _actualizar(con, db.persona, persona_id, cliente, _PERSONA_COLS, campos)


def archivar_persona(cliente, persona_id, archivada=True):
    return actualizar_persona(cliente, persona_id, archivada=bool(archivada))


def personas(cliente, incluir_archivadas=False):
    p = db.persona
    q = sa.select(p).where(p.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(p.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(p.c.nombre))]


def persona(cliente, persona_id):
    with db.conectar() as con:
        f = _fila(con, db.persona, persona_id, cliente)
    return _a_dict(f) if f else None


# --------------------------------------------------------- temporadas ---

def crear_temporada(cliente, nombre, inicio, fin, contexto="", mood_visual=None, tipo="propia"):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La temporada necesita un nombre.")
    if tipo not in TIPOS_TEMPORADA:
        raise ErrorDatos(f"Tipo de temporada inválido: {tipo}. Opciones: {TIPOS_TEMPORADA}")
    inicio, fin = _rango(inicio, fin, "la temporada")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.temporada.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, inicio=inicio, fin=fin,
            contexto=_texto(contexto), mood_visual=dict(mood_visual or {}), tipo=tipo, archivada=False,
            extra={})).inserted_primary_key[0]


def actualizar_temporada(cliente, temporada_id, **campos):
    if "nombre" in campos:
        campos["nombre"] = _texto(campos["nombre"], 120)
        if not campos["nombre"]:
            raise ErrorDatos("La temporada necesita un nombre.")
    if "tipo" in campos and campos["tipo"] not in TIPOS_TEMPORADA:
        raise ErrorDatos(f"Tipo de temporada inválido: {campos['tipo']}")
    if "inicio" in campos or "fin" in campos:
        actual = temporada(cliente, temporada_id) or {}
        campos["inicio"], campos["fin"] = _rango(campos.get("inicio", actual.get("inicio")),
                                                 campos.get("fin", actual.get("fin")), "la temporada")
    with db.conectar() as con:
        return _actualizar(con, db.temporada, temporada_id, cliente, _TEMPORADA_COLS, campos)


def archivar_temporada(cliente, temporada_id, archivada=True):
    return actualizar_temporada(cliente, temporada_id, archivada=bool(archivada))


def temporadas(cliente, incluir_archivadas=False):
    t = db.temporada
    q = sa.select(t).where(t.c.cliente == cliente)
    if not incluir_archivadas:
        q = q.where(t.c.archivada.is_(False))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q.order_by(t.c.inicio, t.c.nombre))]


def temporada(cliente, temporada_id):
    with db.conectar() as con:
        f = _fila(con, db.temporada, temporada_id, cliente)
    return _a_dict(f) if f else None
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py -q`
Expected: PASS (3 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile sprints/__init__.py sprints/datos.py
/opt/homebrew/bin/git add sprints/__init__.py sprints/datos.py tests/test_sprints_datos.py
/opt/homebrew/bin/git commit -m "Sprints: datos de personas y temporadas con validaciones

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `sprints/calendario.py` — presets del calendario comercial y país del proyecto

**Files:**
- Create: `sprints/calendario.py`
- Modify: `proyectos.py` (al final)
- Test: `tests/test_sprints_calendario.py`

**Interfaces:**
- Consumes: `datos.crear_temporada`, `datos.temporadas`.
- Produces: `calendario.PRESETS` (dict país → lista), `calendario.presets(pais, anio=None) -> list[dict]` (cada uno con `clave, nombre, tipo, inicio, fin, contexto, mood_visual`), `calendario.adoptar(cliente, clave, pais=None, anio=None) -> int` (idempotente por nombre + inicio), `proyectos.pais(cliente) -> str` (defecto `"CO"`), `proyectos.guardar_pais(cliente, pais)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_calendario.py
import pytest


def test_presets_por_pais_con_fechas_del_anio():
    from sprints import calendario
    co = calendario.presets("CO", anio=2026)
    claves = [p["clave"] for p in co]
    assert "navidad" in claves and "amor_y_amistad" in claves and "black_friday" in claves
    navidad = next(p for p in co if p["clave"] == "navidad")
    assert navidad["inicio"] == "2026-11-15" and navidad["fin"] == "2026-12-31" and navidad["tipo"] == "comercial"
    assert all(p["inicio"] < p["fin"] for p in co)
    mx = calendario.presets("MX", anio=2026)
    assert "san_valentin" in [p["clave"] for p in mx]
    assert calendario.presets("ZZ", anio=2026) == calendario.presets("CO", anio=2026)   # país sin calendario: el de Colombia


def test_adoptar_crea_temporada_una_sola_vez(base_temporal):
    from sprints import calendario, datos
    tid = calendario.adoptar("acme", "black_friday", pais="CO", anio=2026)
    t = datos.temporada("acme", tid)
    assert t["nombre"] == "Black Friday" and t["tipo"] == "comercial" and t["inicio"] == "2026-11-20"
    assert calendario.adoptar("acme", "black_friday", pais="CO", anio=2026) == tid
    assert len(datos.temporadas("acme")) == 1
    with pytest.raises(datos.ErrorDatos):
        calendario.adoptar("acme", "no_existe", pais="CO", anio=2026)


def test_pais_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    assert proyectos.pais("acme") == "CO"
    proyectos.guardar_pais("acme", "MX")
    assert proyectos.pais("acme") == "MX"
    with pytest.raises(ValueError):
        proyectos.guardar_pais("acme", "XX")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_calendario.py -q`
Expected: FAIL (`No module named 'sprints.calendario'`).

- [ ] **Step 3: Escribir `sprints/calendario.py` y las funciones de `proyectos.py`**

```python
# sprints/calendario.py
"""
Calendario comercial por país: fechas de temporadas que un proyecto adopta con
un clic como `temporada` propia (spec §1.1, §1.6). Las fechas son del año
pedido; las que dependen de un domingo (Día de la madre, del padre) se
aproximan a una ventana fija de venta. Sin calendario para un país, se usa el
de Colombia.
"""
from datetime import date

from sprints import datos

_MADRE = {"clave": "dia_de_la_madre", "nombre": "Día de la madre", "tipo": "comercial",
          "contexto": "Regalos para mamá: detalle, cuidado y hogar. Compra emocional y de última hora.",
          "mood_visual": {"paleta": ["#F4A7B9", "#FFFFFF", "#C9A227"], "luz": "suave y cálida",
                          "elementos": ["flores", "desayuno", "abrazo"]}}
_PADRE = {"clave": "dia_del_padre", "nombre": "Día del padre", "tipo": "comercial",
          "contexto": "Regalos útiles y con carácter para papá; tono cercano, algo de humor.",
          "mood_visual": {"paleta": ["#1B2A41", "#8C6D46", "#E8E4DC"], "luz": "natural, de tarde",
                          "elementos": ["taller", "asado", "reloj"]}}
_NAVIDAD = {"clave": "navidad", "nombre": "Navidad", "tipo": "comercial", "mm_dd": ("11-15", "12-31"),
            "contexto": "Regalos, reuniones familiares y decoración; mucha demanda, envíos con plazo.",
            "mood_visual": {"paleta": ["#B3001B", "#0B6E4F", "#F2C14E"], "luz": "cálida, nocturna, luces",
                            "elementos": ["regalos", "luces", "mesa familiar"]}}
_BLACK = {"clave": "black_friday", "nombre": "Black Friday", "tipo": "comercial", "mm_dd": ("11-20", "11-30"),
          "contexto": "Descuentos y urgencia: precios tachados, cupos, cuenta regresiva.",
          "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": "contrastada, de estudio",
                          "elementos": ["etiquetas de precio", "carrito", "reloj"]}}
_HALLOWEEN = {"clave": "halloween", "nombre": "Halloween", "tipo": "estacional", "mm_dd": ("10-15", "10-31"),
              "contexto": "Disfraces, fiestas y decoración; tono lúdico.",
              "mood_visual": {"paleta": ["#FF7A00", "#1A1A1A", "#7C3AED"], "luz": "nocturna, dramática",
                              "elementos": ["calabaza", "velas", "disfraz"]}}

PRESETS = {
    "CO": [
        {"clave": "regreso_a_clases", "nombre": "Regreso a clases", "tipo": "estacional", "mm_dd": ("01-15", "02-10"),
         "contexto": "Útiles, uniformes y organización del hogar para el inicio del año escolar.",
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": "mañana, fresca",
                         "elementos": ["mochila", "escritorio", "calendario"]}},
        dict(_MADRE, mm_dd=("05-01", "05-15")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "vacaciones_mitad_de_ano", "nombre": "Vacaciones de mitad de año", "tipo": "estacional",
         "mm_dd": ("06-15", "07-15"), "contexto": "Descanso, viajes y tiempo en casa; compras para el hogar.",
         "mood_visual": {"paleta": ["#00A6A6", "#F9F7F1", "#F4B942"], "luz": "sol directo, exteriores",
                         "elementos": ["terraza", "piscina", "maleta"]}},
        {"clave": "amor_y_amistad", "nombre": "Amor y amistad", "tipo": "comercial", "mm_dd": ("09-05", "09-20"),
         "contexto": "Regalos entre parejas y amigos, planes y detalles; tono afectivo.",
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": "cálida, atardecer",
                         "elementos": ["regalo", "cena", "flores"]}},
        _HALLOWEEN, _BLACK, _NAVIDAD,
    ],
    "MX": [
        {"clave": "san_valentin", "nombre": "San Valentín", "tipo": "comercial", "mm_dd": ("02-01", "02-14"),
         "contexto": "Regalos de pareja y amistad; detalles y experiencias.",
         "mood_visual": {"paleta": ["#E63946", "#FFE5EC", "#1D3557"], "luz": "cálida", "elementos": ["regalo", "cena", "flores"]}},
        dict(_MADRE, mm_dd=("05-01", "05-10")),
        dict(_PADRE, mm_dd=("06-05", "06-20")),
        {"clave": "regreso_a_clases", "nombre": "Regreso a clases", "tipo": "estacional", "mm_dd": ("08-10", "08-31"),
         "contexto": "Útiles, uniformes y organización del hogar para el inicio del ciclo escolar.",
         "mood_visual": {"paleta": ["#2F80ED", "#F2C94C", "#FFFFFF"], "luz": "mañana, fresca",
                         "elementos": ["mochila", "escritorio", "calendario"]}},
        {"clave": "buen_fin", "nombre": "El Buen Fin", "tipo": "comercial", "mm_dd": ("11-10", "11-20"),
         "contexto": "Descuentos y meses sin intereses; urgencia.",
         "mood_visual": {"paleta": ["#000000", "#FFD400", "#FFFFFF"], "luz": "contrastada", "elementos": ["etiquetas", "carrito"]}},
        _HALLOWEEN, _BLACK, _NAVIDAD,
    ],
}


def presets(pais, anio=None):
    anio = int(anio or date.today().year)
    lista = PRESETS.get((pais or "").upper()) or PRESETS["CO"]
    salida = []
    for p in lista:
        mi, mf = p["mm_dd"]
        salida.append({"clave": p["clave"], "nombre": p["nombre"], "tipo": p["tipo"],
                       "inicio": f"{anio}-{mi}", "fin": f"{anio}-{mf}", "contexto": p["contexto"],
                       "mood_visual": dict(p["mood_visual"])})
    return salida


def adoptar(cliente, clave, pais=None, anio=None):
    """Crea la temporada del preset (o devuelve la existente con el mismo
    nombre e inicio, para que el clic repetido no duplique)."""
    p = next((x for x in presets(pais, anio) if x["clave"] == clave), None)
    if not p:
        raise datos.ErrorDatos("Ese preset de temporada no existe.")
    for t in datos.temporadas(cliente, incluir_archivadas=True):
        if t["nombre"] == p["nombre"] and t["inicio"] == p["inicio"]:
            return t["id"]
    return datos.crear_temporada(cliente, p["nombre"], p["inicio"], p["fin"], contexto=p["contexto"],
                                 mood_visual=p["mood_visual"], tipo=p["tipo"])
```

Al final de `proyectos.py`:

```python
PAISES_CALENDARIO = ("CO", "MX", "US", "ES", "BR", "AR", "CL", "PE")


def pais(cliente):
    """País del proyecto para el calendario comercial de Sprints (ISO-3166-1
    alfa-2). Sin dato, Colombia."""
    return (cargar(cliente).get("pais") or "CO").upper()


def guardar_pais(cliente, pais_nuevo):
    pais_nuevo = (pais_nuevo or "").upper()
    if pais_nuevo not in PAISES_CALENDARIO:
        raise ValueError(f"País no soportado: {pais_nuevo}")
    datos = cargar(cliente)
    datos["pais"] = pais_nuevo
    _json_store.guardar(_path(cliente), datos)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_calendario.py -q`
Expected: PASS (3 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile sprints/calendario.py proyectos.py
/opt/homebrew/bin/git add sprints/calendario.py proyectos.py tests/test_sprints_calendario.py
/opt/homebrew/bin/git commit -m "Sprints: calendario comercial por país y adopción de temporadas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `sprints/datos.py` — sprints, campañas y eventos

**Files:**
- Modify: `sprints/datos.py` (agregar al final)
- Test: `tests/test_sprints_datos.py` (agregar)

**Interfaces:**
- Consumes: helpers de la Task 2.
- Produces: `crear_sprint(cliente, nombre, inicio, fin, destinos=None, referencias_objetivo_defecto=5, notas="") -> int`, `actualizar_sprint(cliente, sprint_id, **campos) -> bool`, `archivar_sprint(cliente, sprint_id, archivado=True)`, `sprints(cliente, incluir_archivados=False) -> list[dict]` (cada uno con `campanas` y `progreso` NO: el progreso lo calcula la ruta), `sprint(cliente, sprint_id, con_eventos=True) -> dict|None` (con `campanas: list[dict]` y `eventos`), `agregar_campana(cliente, sprint_id, persona_id, catalogo_id, temporada_id, n_videos, n_imagenes, referencias_objetivo=None) -> int` (lanza `CampanaDuplicada`), `actualizar_campana(cliente, campana_id, **campos)`, `eliminar_campana(cliente, campana_id) -> bool`, `campana(cliente, campana_id) -> dict|None` (con `sprint_id`, `persona_*`, `temporada_*`, `referencias_total`, `referencias_listas`), `campanas(cliente, sprint_id) -> list[dict]`, `combinaciones(cliente, sprint_id) -> set[tuple]`, `registrar_evento(cliente, sprint_id, tipo, mensaje, datos=None, campana_id=None) -> int`, `eventos(cliente, sprint_id, limite=50) -> list[dict]`.
- Cada dict de campaña trae también `ideas: []`, `piezas: []`, `piezas_listas: 0`, `piezas_aprobadas: 0` (la Parte 2 los llena; `estado.py` y `progreso.py` ya los leen).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_sprints_datos.py`)

```python
def _base(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", destinos=["es_CO"])
    return pid, tid, sid


def test_sprint_crear_y_validar(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    s = datos.sprint("acme", sid)
    assert s["estado"] == "planeando" and s["destinos"] == ["es_CO"] and s["campanas"] == []
    assert [e["tipo"] for e in s["eventos"]] == ["sprint_creado"]
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "", "2026-10-01", "2026-10-31")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-31", "2026-10-01")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_sprint("acme", "X", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=0)
    assert datos.sprint("otro", sid) is None and datos.sprints("otro") == []


def test_campana_unicidad_y_cantidades(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    c = datos.campana("acme", cid)
    assert c["persona_nombre"] == "Premium" and c["temporada_nombre"] == "Verano" and c["estado"] == "planeada"
    assert c["referencias_objetivo"] == 5 and c["referencias_total"] == 0 and c["sprint_id"] == sid
    with pytest.raises(datos.CampanaDuplicada) as e:
        datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    assert "campaña 1" in str(e.value)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 0, 3, referencias_objetivo=8)
    assert datos.campana("acme", cid2)["orden"] == 1 and datos.campana("acme", cid2)["referencias_objetivo"] == 8
    assert datos.combinaciones("acme", sid) == {(pid, "espejo_led", tid), (pid, "espejo_led", tid2)}
    for malo in [dict(n_videos=0, n_imagenes=0), dict(n_videos=-1, n_imagenes=2), dict(n_videos="x", n_imagenes=1)]:
        with pytest.raises(datos.ErrorDatos):
            datos.agregar_campana("acme", sid, pid, "otro", tid, **malo)
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, 999, "otro", tid, 1, 1)        # persona ajena
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_campana("acme", sid, pid, "", tid, 1, 1)           # sin producto
    assert [c["id"] for c in datos.campanas("acme", sid)] == [cid, cid2]
    assert datos.actualizar_campana("acme", cid, n_videos=12)
    assert datos.eliminar_campana("acme", cid2) and len(datos.campanas("acme", sid)) == 1
    tipos = [e["tipo"] for e in datos.eventos("acme", sid)]
    assert tipos[0] == "campana_eliminada" and "campana_agregada" in tipos


def test_sprints_lista_con_totales(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 10, 25)
    lista = datos.sprints("acme")
    assert len(lista) == 1 and lista[0]["piezas_planeadas"] == 35 and lista[0]["campanas_total"] == 1
    datos.archivar_sprint("acme", sid)
    assert datos.sprints("acme") == [] and len(datos.sprints("acme", incluir_archivados=True)) == 1
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'crear_sprint'`).

- [ ] **Step 3: Agregar al final de `sprints/datos.py`**

```python
# ------------------------------------------------------------ eventos ---

def _evento(con, cliente, sprint_id, campana_id, tipo, mensaje, datos_=None):
    return con.execute(db.sprint_evento.insert().values(
        cliente=cliente, sprint_id=sprint_id, campana_id=campana_id, tipo=tipo, mensaje=mensaje,
        datos=datos_ or {}, creado_en=db.ahora())).inserted_primary_key[0]


def registrar_evento(cliente, sprint_id, tipo, mensaje, datos=None, campana_id=None):
    with db.conectar() as con:
        return _evento(con, cliente, sprint_id, campana_id, tipo, mensaje, datos)


def _eventos(con, cliente, sprint_id, limite):
    e = db.sprint_evento
    q = sa.select(e).where(e.c.cliente == cliente, e.c.sprint_id == sprint_id).order_by(e.c.id.desc())
    if limite:
        q = q.limit(limite)
    return [_a_dict(f) for f in con.execute(q)]


def eventos(cliente, sprint_id, limite=50):
    with db.conectar() as con:
        return _eventos(con, cliente, sprint_id, limite)


# ------------------------------------------------------------ sprints ---

def crear_sprint(cliente, nombre, inicio, fin, destinos=None, referencias_objetivo_defecto=5, notas=""):
    nombre = _texto(nombre, 200)
    if not nombre:
        raise ErrorDatos("El sprint necesita un nombre.")
    inicio, fin = _rango(inicio, fin, "el sprint")
    try:
        objetivo = int(referencias_objetivo_defecto or 5)
    except (TypeError, ValueError):
        raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
    if objetivo < 1:
        raise ErrorDatos("El objetivo de referencias debe ser al menos 1.")
    ahora = db.ahora()
    with db.conectar() as con:
        sid = con.execute(db.sprint.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=nombre, inicio=inicio, fin=fin,
            estado="planeando", destinos=list(destinos or []), referencias_objetivo_defecto=objetivo,
            notas=_texto(notas), archivado=False, extra={})).inserted_primary_key[0]
        _evento(con, cliente, sid, None, "sprint_creado", f"Sprint «{nombre}» creado", {"inicio": inicio, "fin": fin})
    return sid


def actualizar_sprint(cliente, sprint_id, **campos):
    if "estado" in campos and campos["estado"] not in ESTADOS_SPRINT:
        raise ErrorDatos(f"Estado de sprint inválido: {campos['estado']}")
    if "inicio" in campos or "fin" in campos:
        actual = sprint(cliente, sprint_id, con_eventos=False) or {}
        campos["inicio"], campos["fin"] = _rango(campos.get("inicio", actual.get("inicio")),
                                                 campos.get("fin", actual.get("fin")), "el sprint")
    with db.conectar() as con:
        return _actualizar(con, db.sprint, sprint_id, cliente, _SPRINT_COLS, campos)


def archivar_sprint(cliente, sprint_id, archivado=True):
    return actualizar_sprint(cliente, sprint_id, archivado=bool(archivado))


def _campanas(con, cliente, sprint_id=None, campana_id=None):
    c, p, t, r = db.campana, db.persona, db.temporada, db.referencia
    conteo = (sa.select(r.c.campana_id, sa.func.count().label("total"),
                        sa.func.sum(sa.case((r.c.estado == "lista", 1), else_=0)).label("listas"))
              .where(r.c.cliente == cliente).group_by(r.c.campana_id).subquery())
    q = (sa.select(c, p.c.nombre.label("persona_nombre"), p.c.color.label("persona_color"),
                   t.c.nombre.label("temporada_nombre"), t.c.inicio.label("temporada_inicio"),
                   t.c.fin.label("temporada_fin"),
                   sa.func.coalesce(conteo.c.total, 0).label("referencias_total"),
                   sa.func.coalesce(conteo.c.listas, 0).label("referencias_listas"))
         .select_from(c.join(p, p.c.id == c.c.persona_id).join(t, t.c.id == c.c.temporada_id)
                      .outerjoin(conteo, conteo.c.campana_id == c.c.id))
         .where(c.c.cliente == cliente))
    if sprint_id is not None:
        q = q.where(c.c.sprint_id == sprint_id)
    if campana_id is not None:
        q = q.where(c.c.id == campana_id)
    salida = []
    for f in con.execute(q.order_by(c.c.orden, c.c.id)):
        d = _a_dict(f)
        d.update({"ideas": [], "piezas": [], "piezas_listas": 0, "piezas_aprobadas": 0,
                  "referencias_total": int(d["referencias_total"] or 0),
                  "referencias_listas": int(d["referencias_listas"] or 0)})
        salida.append(d)
    return salida


def _sprint_dict(con, cliente, f, con_eventos):
    d = _a_dict(f)
    d["campanas"] = _campanas(con, cliente, sprint_id=d["id"])
    d["campanas_total"] = len(d["campanas"])
    d["piezas_planeadas"] = sum(int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0) for c in d["campanas"])
    d["eventos"] = _eventos(con, cliente, d["id"], 50) if con_eventos else []
    d["extra"] = d.get("extra") or {}
    return d


def sprints(cliente, incluir_archivados=False):
    s = db.sprint
    q = sa.select(s).where(s.c.cliente == cliente)
    if not incluir_archivados:
        q = q.where(s.c.archivado.is_(False))
    with db.conectar() as con:
        return [_sprint_dict(con, cliente, f, con_eventos=False) for f in con.execute(q.order_by(s.c.inicio.desc(), s.c.id.desc()))]


def sprint(cliente, sprint_id, con_eventos=True):
    with db.conectar() as con:
        f = _fila(con, db.sprint, sprint_id, cliente)
        return _sprint_dict(con, cliente, f, con_eventos) if f else None


# ----------------------------------------------------------- campañas ---

def combinaciones(cliente, sprint_id):
    c = db.campana
    with db.conectar() as con:
        return {(f.persona_id, f.catalogo_id, f.temporada_id) for f in con.execute(
            sa.select(c.c.persona_id, c.c.catalogo_id, c.c.temporada_id)
            .where(c.c.cliente == cliente, c.c.sprint_id == sprint_id))}


def _cantidades(n_videos, n_imagenes):
    try:
        n_videos, n_imagenes = int(n_videos or 0), int(n_imagenes or 0)
    except (TypeError, ValueError):
        raise ErrorDatos("Las cantidades de videos e imágenes deben ser números enteros.")
    if n_videos < 0 or n_imagenes < 0:
        raise ErrorDatos("Las cantidades no pueden ser negativas.")
    if n_videos + n_imagenes < 1:
        raise ErrorDatos("Una campaña necesita al menos un video o una imagen.")
    return n_videos, n_imagenes


def agregar_campana(cliente, sprint_id, persona_id, catalogo_id, temporada_id, n_videos, n_imagenes,
                    referencias_objetivo=None):
    n_videos, n_imagenes = _cantidades(n_videos, n_imagenes)
    catalogo_id = _texto(catalogo_id, 120)
    if not catalogo_id:
        raise ErrorDatos("Elige un producto.")
    ahora = db.ahora()
    with db.conectar() as con:
        sp = _fila(con, db.sprint, sprint_id, cliente)
        if not sp:
            raise ErrorDatos("Ese sprint no existe.")
        if not _fila(con, db.persona, persona_id, cliente):
            raise ErrorDatos("Esa persona no existe en este proyecto.")
        if not _fila(con, db.temporada, temporada_id, cliente):
            raise ErrorDatos("Esa temporada no existe en este proyecto.")
        c = db.campana
        repetida = con.execute(sa.select(c.c.orden).where(
            c.c.sprint_id == sprint_id, c.c.persona_id == persona_id, c.c.catalogo_id == catalogo_id,
            c.c.temporada_id == temporada_id)).scalar()
        if repetida is not None:
            raise CampanaDuplicada(
                f"Esa combinación de persona, producto y temporada ya existe en la campaña {int(repetida) + 1}.")
        orden = con.execute(sa.select(sa.func.count()).select_from(c).where(c.c.sprint_id == sprint_id)).scalar() or 0
        try:
            objetivo = int(referencias_objetivo or sp.referencias_objetivo_defecto or 5)
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
        try:
            cid = con.execute(c.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, sprint_id=sprint_id, persona_id=persona_id,
                catalogo_id=catalogo_id, producto_id=None, temporada_id=temporada_id, n_videos=n_videos,
                n_imagenes=n_imagenes, referencias_objetivo=max(1, objetivo), estado="planeada", orden=orden,
                extra={})).inserted_primary_key[0]
        except sa.exc.IntegrityError:
            raise CampanaDuplicada("Esa combinación de persona, producto y temporada ya existe en este sprint.")
        _evento(con, cliente, sprint_id, cid, "campana_agregada", "Campaña agregada",
                {"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id,
                 "n_videos": n_videos, "n_imagenes": n_imagenes})
        con.execute(db.sprint.update().where(db.sprint.c.id == sprint_id).values(actualizado_en=ahora))
    return cid


def actualizar_campana(cliente, campana_id, **campos):
    if "n_videos" in campos or "n_imagenes" in campos:
        actual = campana(cliente, campana_id) or {}
        campos["n_videos"], campos["n_imagenes"] = _cantidades(campos.get("n_videos", actual.get("n_videos")),
                                                               campos.get("n_imagenes", actual.get("n_imagenes")))
    if "estado" in campos and campos["estado"] not in ESTADOS_CAMPANA:
        raise ErrorDatos(f"Estado de campaña inválido: {campos['estado']}")
    if "referencias_objetivo" in campos:
        try:
            campos["referencias_objetivo"] = max(1, int(campos["referencias_objetivo"]))
        except (TypeError, ValueError):
            raise ErrorDatos("El objetivo de referencias debe ser un número entero.")
    with db.conectar() as con:
        return _actualizar(con, db.campana, campana_id, cliente, _CAMPANA_COLS, campos)


def eliminar_campana(cliente, campana_id):
    with db.conectar() as con:
        f = _fila(con, db.campana, campana_id, cliente)
        if not f:
            return False
        con.execute(db.referencia.delete().where(db.referencia.c.campana_id == campana_id))
        con.execute(db.campana_pieza.delete().where(db.campana_pieza.c.campana_id == campana_id))
        con.execute(db.sprint_evento.update().where(db.sprint_evento.c.campana_id == campana_id).values(campana_id=None))
        con.execute(db.campana.delete().where(db.campana.c.id == campana_id))
        _evento(con, cliente, f.sprint_id, None, "campana_eliminada", "Campaña eliminada",
                {"campana_id": campana_id, "catalogo_id": f.catalogo_id})
    return True


def campana(cliente, campana_id):
    with db.conectar() as con:
        lista = _campanas(con, cliente, campana_id=campana_id)
    return lista[0] if lista else None


def campanas(cliente, sprint_id):
    with db.conectar() as con:
        return _campanas(con, cliente, sprint_id=sprint_id)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py -q`
Expected: PASS (6 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile sprints/datos.py
/opt/homebrew/bin/git add sprints/datos.py tests/test_sprints_datos.py
/opt/homebrew/bin/git commit -m "Sprints: datos de sprints, campañas (unicidad persona+producto+temporada) y eventos

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `sprints/datos.py` — referencias, y `sprints/archivos.py` — subidas a R2

**Files:**
- Modify: `sprints/datos.py` (agregar al final)
- Create: `sprints/archivos.py`
- Test: `tests/test_sprints_datos.py` (agregar), `tests/test_sprints_archivos.py`

**Interfaces:**
- Produces (datos): `agregar_referencia(cliente, campana_id, tipo, url, frame_url=None, ruta_local=None, origen="archivo", titulo="", intencion=None, descripcion="") -> int`, `actualizar_referencia(cliente, referencia_id, **campos) -> bool` (recalcula `estado` cuando cambia `descripcion`), `quitar_referencia(cliente, referencia_id) -> bool`, `referencias(cliente, campana_id) -> list[dict]`, `referencia(cliente, referencia_id) -> dict|None` (incluye `sprint_id`), `reutilizar_referencia(cliente, referencia_id, campana_destino_id) -> int`, `intencion_valida(lista) -> list`.
- Produces (archivos): `IMAGE_EXTS`, `VIDEO_EXTS`, `FRAME_SUFFIX`, `carpeta(cliente) -> str`, `extraer_frame(video_path, frame_path, segundo=1.0)`, `registrar_local(cliente, local_path, titulo) -> dict{tipo,url,frame_url,ruta_local,titulo}`, `guardar_subida(cliente, archivo) -> dict|None` (None si la extensión no sirve).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_sprints_datos.py`:

```python
def test_referencias_borrador_y_lista(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", titulo="a.jpg",
                                  intencion=["paleta", "composicion"])
    r2 = datos.agregar_referencia("acme", cid, "video", "https://r2/b.mp4", frame_url="https://r2/b.frame.jpg",
                                  origen="link", descripcion="El movimiento de cámara lento")
    a, b = datos.referencia("acme", r1), datos.referencia("acme", r2)
    assert a["estado"] == "borrador" and b["estado"] == "lista" and a["sprint_id"] == sid
    assert a["analisis_estado"] == "pendiente" and a["intencion"] == ["paleta", "composicion"]
    c = datos.campana("acme", cid)
    assert c["referencias_total"] == 2 and c["referencias_listas"] == 1
    datos.actualizar_referencia("acme", r1, descripcion="Quiero esta paleta", intencion=["paleta", "otro"],
                                intencion_otro="textura del vidrio")
    assert datos.referencia("acme", r1)["estado"] == "lista"
    datos.actualizar_referencia("acme", r1, descripcion="   ")
    assert datos.referencia("acme", r1)["estado"] == "borrador"
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "audio", "https://x")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "imagen", "https://x", intencion=["magia"])
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", cid, "imagen", "https://x", origen="marte")
    with pytest.raises(datos.ErrorDatos):
        datos.agregar_referencia("acme", 999, "imagen", "https://x")
    assert [r["id"] for r in datos.referencias("acme", cid)] == [r1, r2]
    assert datos.quitar_referencia("acme", r2) and len(datos.referencias("acme", cid)) == 1
    assert not datos.quitar_referencia("otro", r1)


def test_reutilizar_referencia_copia_con_analisis(base_temporal):
    from sprints import datos
    pid, tid, sid = _base(datos)
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 2)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 1)
    r1 = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz", intencion=["iluminacion"])
    datos.actualizar_referencia("acme", r1, analisis={"resumen": "x"}, analisis_estado="listo")
    r2 = datos.reutilizar_referencia("acme", r1, cid2)
    b = datos.referencia("acme", r2)
    assert b["campana_id"] == cid2 and b["origen"] == "reutilizada" and b["analisis"] == {"resumen": "x"}
    assert b["estado"] == "lista" and b["analisis_estado"] == "listo"
    with pytest.raises(datos.ErrorDatos):
        datos.reutilizar_referencia("acme", r1, cid)      # ya está en esa campaña
```

Crear `tests/test_sprints_archivos.py`:

```python
import io
import os

from werkzeug.datastructures import FileStorage


def _r2_falso(monkeypatch, subidas):
    from sprints import archivos
    monkeypatch.setattr(archivos.r2_uploader, "upload_image", lambda ruta, key: subidas.append(("imagen", key)) or f"https://r2/{key}")
    monkeypatch.setattr(archivos.r2_uploader, "upload_video", lambda ruta, key: subidas.append(("video", key)) or f"https://r2/{key}")


def test_guardar_subida_imagen(tmp_path, monkeypatch):
    from sprints import archivos
    monkeypatch.setattr(archivos, "BASE_DIR", str(tmp_path))
    subidas = []
    _r2_falso(monkeypatch, subidas)
    info = archivos.guardar_subida("acme", FileStorage(io.BytesIO(b"png"), filename="ref uno.PNG"))
    assert info["tipo"] == "imagen" and info["url"].startswith("https://r2/clientes/acme/sprints/referencias/")
    assert info["frame_url"] is None and info["titulo"] == "ref_uno.PNG" and os.path.exists(info["ruta_local"])
    assert subidas[0][0] == "imagen"
    assert archivos.guardar_subida("acme", FileStorage(io.BytesIO(b"x"), filename="doc.pdf")) is None


def test_registrar_local_video_extrae_fotograma(tmp_path, monkeypatch):
    from sprints import archivos
    monkeypatch.setattr(archivos, "BASE_DIR", str(tmp_path))
    subidas = []
    _r2_falso(monkeypatch, subidas)
    def frame_falso(video, frame, segundo=1.0):
        open(frame, "wb").write(b"jpg")
    monkeypatch.setattr(archivos, "extraer_frame", frame_falso)
    local = tmp_path / "clip.mp4"
    local.write_bytes(b"mp4")
    info = archivos.registrar_local("acme", str(local), "clip.mp4")
    assert info["tipo"] == "video" and info["frame_url"].endswith("clip.mp4.frame.jpg")
    assert [s[0] for s in subidas] == ["video", "imagen"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py tests/test_sprints_archivos.py -q`
Expected: FAIL (`agregar_referencia` y `sprints.archivos` no existen).

- [ ] **Step 3: Agregar al final de `sprints/datos.py`**

```python
# -------------------------------------------------------- referencias ---

def intencion_valida(lista):
    lista = [str(x) for x in (lista or []) if x]
    malas = [x for x in lista if x not in INTENCIONES]
    if malas:
        raise ErrorDatos(f"Intención desconocida: {', '.join(malas)}")
    return list(dict.fromkeys(lista))    # sin repetidos, en orden


def _estado_referencia(descripcion):
    return "lista" if (descripcion or "").strip() else "borrador"


def agregar_referencia(cliente, campana_id, tipo, url, frame_url=None, ruta_local=None, origen="archivo", titulo="",
                       intencion=None, descripcion=""):
    if tipo not in ("imagen", "video"):
        raise ErrorDatos(f"Tipo de referencia inválido: {tipo}")
    if origen not in ORIGENES_REFERENCIA:
        raise ErrorDatos(f"Origen de referencia inválido: {origen}")
    if not (url or "").strip():
        raise ErrorDatos("La referencia necesita una URL.")
    intencion = intencion_valida(intencion)
    descripcion = _texto(descripcion)
    ahora = db.ahora()
    with db.conectar() as con:
        c = _fila(con, db.campana, campana_id, cliente)
        if not c:
            raise ErrorDatos("Esa campaña no existe.")
        r = db.referencia
        orden = con.execute(sa.select(sa.func.count()).select_from(r).where(r.c.campana_id == campana_id)).scalar() or 0
        rid = con.execute(r.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, campana_id=campana_id, tipo=tipo, url=url.strip(),
            frame_url=frame_url, ruta_local=ruta_local, origen=origen, titulo=_texto(titulo, 200), intencion=intencion,
            intencion_otro=None, descripcion=descripcion, analisis=None, analisis_estado="pendiente",
            estado=_estado_referencia(descripcion), orden=orden, extra={})).inserted_primary_key[0]
        _evento(con, cliente, c.sprint_id, campana_id, "referencia_agregada", f"Referencia agregada ({tipo}, {origen})",
                {"referencia_id": rid, "titulo": _texto(titulo, 200)})
    return rid


def actualizar_referencia(cliente, referencia_id, **campos):
    if "intencion" in campos:
        campos["intencion"] = intencion_valida(campos["intencion"])
    if "descripcion" in campos:
        campos["descripcion"] = _texto(campos["descripcion"])
    if "intencion_otro" in campos:
        campos["intencion_otro"] = _texto(campos["intencion_otro"], 200) or None
    if "analisis_estado" in campos and campos["analisis_estado"] not in ("pendiente", "listo", "error"):
        raise ErrorDatos(f"Estado de análisis inválido: {campos['analisis_estado']}")
    permitidas = _REFERENCIA_COLS + ("estado",)
    if "descripcion" in campos:
        campos["estado"] = _estado_referencia(campos["descripcion"])
    with db.conectar() as con:
        return _actualizar(con, db.referencia, referencia_id, cliente, permitidas, campos)


def quitar_referencia(cliente, referencia_id):
    with db.conectar() as con:
        f = _fila(con, db.referencia, referencia_id, cliente)
        if not f:
            return False
        c = con.execute(sa.select(db.campana.c.sprint_id).where(db.campana.c.id == f.campana_id)).first()
        con.execute(db.referencia.delete().where(db.referencia.c.id == referencia_id))
        if c:
            _evento(con, cliente, c.sprint_id, f.campana_id, "referencia_quitada", "Referencia quitada",
                    {"referencia_id": referencia_id, "titulo": f.titulo})
    return True


def _referencias(con, cliente, campana_id=None, referencia_id=None):
    r, c = db.referencia, db.campana
    q = (sa.select(r, c.c.sprint_id.label("sprint_id")).select_from(r.join(c, c.c.id == r.c.campana_id))
         .where(r.c.cliente == cliente))
    if campana_id is not None:
        q = q.where(r.c.campana_id == campana_id)
    if referencia_id is not None:
        q = q.where(r.c.id == referencia_id)
    return [_a_dict(f) for f in con.execute(q.order_by(r.c.orden, r.c.id))]


def referencias(cliente, campana_id):
    with db.conectar() as con:
        return _referencias(con, cliente, campana_id=campana_id)


def referencia(cliente, referencia_id):
    with db.conectar() as con:
        lista = _referencias(con, cliente, referencia_id=referencia_id)
    return lista[0] if lista else None


def reutilizar_referencia(cliente, referencia_id, campana_destino_id):
    """Copia la referencia (con su análisis) a otra campaña, origen `reutilizada`."""
    origen = referencia(cliente, referencia_id)
    if not origen:
        raise ErrorDatos("Esa referencia no existe.")
    if origen["campana_id"] == campana_destino_id:
        raise ErrorDatos("Esa referencia ya está en esta campaña.")
    rid = agregar_referencia(cliente, campana_destino_id, origen["tipo"], origen["url"], frame_url=origen["frame_url"],
                             ruta_local=origen["ruta_local"], origen="reutilizada", titulo=origen["titulo"],
                             intencion=origen["intencion"], descripcion=origen["descripcion"])
    if origen.get("analisis"):
        actualizar_referencia(cliente, rid, analisis=origen["analisis"], analisis_estado=origen["analisis_estado"],
                              intencion_otro=origen.get("intencion_otro"))
    return rid
```

- [ ] **Step 4: Escribir `sprints/archivos.py`**

```python
# sprints/archivos.py
"""
Referencias subidas a una campaña: se guardan en
clientes/<cliente>/sprints/referencias/ y en R2 (misma clave), y a los videos
se les saca un fotograma (miniatura y referencia para los modelos que no
aceptan video). Mismo criterio que `_guardar_referencia_archivo` de
dashboard.py, pero sin depender de Flask.
"""
import os
import subprocess
from datetime import datetime

from werkzeug.utils import secure_filename

from storage import r2_uploader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm")
FRAME_SUFFIX = ".frame.jpg"


def carpeta(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "sprints", "referencias")


def extraer_frame(video_path, frame_path, segundo=1.0):
    subprocess.run(["ffmpeg", "-y", "-ss", str(segundo), "-i", video_path, "-frames:v", "1", "-q:v", "2", frame_path],
                   check=True, capture_output=True)


def registrar_local(cliente, local_path, titulo):
    """Sube un archivo ya guardado en disco a R2 y devuelve la ficha de la
    referencia (tipo, url, frame_url, ruta_local, titulo)."""
    nombre = os.path.basename(local_path)
    ext = os.path.splitext(nombre)[1].lower()
    key = f"clientes/{cliente}/sprints/referencias/{nombre}"
    if ext in VIDEO_EXTS:
        url = r2_uploader.upload_video(local_path, key)
        frame_path = local_path + FRAME_SUFFIX
        extraer_frame(local_path, frame_path)
        frame_url = r2_uploader.upload_image(frame_path, key + FRAME_SUFFIX)
        return {"tipo": "video", "url": url, "frame_url": frame_url, "ruta_local": local_path, "titulo": titulo}
    url = r2_uploader.upload_image(local_path, key)
    return {"tipo": "imagen", "url": url, "frame_url": None, "ruta_local": local_path, "titulo": titulo}


def guardar_subida(cliente, archivo):
    """`archivo` es un FileStorage de Flask. Devuelve la ficha o None si la
    extensión no es imagen ni video."""
    nombre = secure_filename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
        return None
    destino = carpeta(cliente)
    os.makedirs(destino, exist_ok=True)
    unico = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    local_path = os.path.join(destino, unico)
    archivo.save(local_path)
    return registrar_local(cliente, local_path, nombre)
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_datos.py tests/test_sprints_archivos.py -q`
Expected: PASS (8 + 2 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/datos.py sprints/archivos.py
/opt/homebrew/bin/git add sprints/datos.py sprints/archivos.py tests/test_sprints_datos.py tests/test_sprints_archivos.py
/opt/homebrew/bin/git commit -m "Sprints: referencias con intención y descripción (borrador/lista), subidas a R2 con fotograma

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 6: `sprints/progreso.py` y `sprints/estado.py`

**Files:**
- Create: `sprints/progreso.py`, `sprints/estado.py`
- Test: `tests/test_sprints_progreso_estado.py`

**Interfaces:**
- Consumes: dicts de campaña de `datos.campanas`/`datos.sprint` (`estado`, `n_videos`, `n_imagenes`, `referencias_listas`, `referencias_objetivo`, `referencias_total`, `piezas_listas`, `piezas_aprobadas`, `ideas`, `piezas`).
- Produces (progreso): `fraccion_referencias(listas, objetivo) -> float`, `planeadas(c) -> int`, `progreso_campana(c) -> {etapa, fraccion, porcentaje, texto, planeadas}`, `progreso_sprint(campanas) -> {fraccion, porcentaje, planeadas, listas, aprobadas, texto}`, `cobertura(campana, referencias) -> list[str]`.
- Produces (estado): `estado_campana(n_referencias, planeadas, ideas=(), piezas=()) -> str`, `estado_sprint(campanas, listo_manual=False, cerrado=False) -> str`, `recalcular(cliente, sprint_id) -> dict|None` (escribe los estados que cambiaron y devuelve el sprint como `datos.sprint`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_progreso_estado.py
def _c(**k):
    base = {"estado": "planeada", "n_videos": 10, "n_imagenes": 5, "referencias_listas": 0, "referencias_objetivo": 5,
            "referencias_total": 0, "piezas_listas": 0, "piezas_aprobadas": 0, "ideas": [], "piezas": []}
    base.update(k)
    return base


def test_progreso_campana_por_etapa():
    from sprints import progreso
    p = progreso.progreso_campana(_c(estado="referencias", referencias_listas=3))
    assert p == {"etapa": "referencias", "fraccion": 0.6, "porcentaje": 60, "texto": "3 / 5 referencias", "planeadas": 15}
    assert progreso.progreso_campana(_c(estado="referencias", referencias_listas=9))["fraccion"] == 1.0
    p = progreso.progreso_campana(_c(estado="generando", piezas_listas=6))
    assert p["etapa"] == "produccion" and p["porcentaje"] == 40 and p["texto"] == "6 de 15 piezas listas"
    p = progreso.progreso_campana(_c(estado="revision", piezas_aprobadas=15))
    assert p["etapa"] == "revision" and p["fraccion"] == 1.0
    assert progreso.progreso_campana(_c(n_videos=0, n_imagenes=0, estado="revision"))["fraccion"] == 0.0


def test_progreso_sprint_pondera_por_piezas():
    from sprints import progreso
    grande = _c(estado="referencias", referencias_listas=5, n_videos=20, n_imagenes=5)   # 25 piezas, 100 %
    chica = _c(estado="referencias", referencias_listas=0, n_videos=3, n_imagenes=2)     # 5 piezas, 0 %
    s = progreso.progreso_sprint([grande, chica])
    assert s["planeadas"] == 30 and s["porcentaje"] == 83 and s["texto"] == "0 de 30 piezas"
    assert progreso.progreso_sprint([]) == {"fraccion": 0.0, "porcentaje": 0, "planeadas": 0, "listas": 0, "aprobadas": 0,
                                            "texto": "sin piezas planeadas"}


def test_cobertura_sugiere_por_tipo_de_pieza():
    from sprints import progreso
    refs = [{"intencion": ["paleta"]}, {"intencion": ["composicion"]}]
    avisos = progreso.cobertura(_c(n_videos=10, n_imagenes=5), refs)
    assert len(avisos) == 1 and "movimiento de cámara" in avisos[0] and "10 videos" in avisos[0]
    assert progreso.cobertura(_c(n_videos=0, n_imagenes=5), refs) == []
    assert len(progreso.cobertura(_c(n_videos=1, n_imagenes=1), [])) == 2


def test_estado_campana_reglas():
    from sprints import estado
    assert estado.estado_campana(0, 15) == "planeada"
    assert estado.estado_campana(1, 15) == "referencias"
    ideas = [{"estado_idea": "propuesta"}] * 15
    assert estado.estado_campana(3, 15, ideas=ideas) == "ideas_propuestas"
    assert estado.estado_campana(3, 15, ideas=[{"estado_idea": "aprobada"}] * 15) == "ideas_aprobadas"
    assert estado.estado_campana(3, 15, ideas=ideas, piezas=[{"estado": "generando"}]) == "generando"
    assert estado.estado_campana(3, 2, piezas=[{"estado": "listo", "revision": "pendiente"}, {"estado": "error"}]) == "revision"
    assert estado.estado_campana(3, 2, piezas=[{"estado": "listo", "revision": "aprobada"}] * 2) == "completada"


def test_estado_sprint_reglas():
    from sprints import estado
    assert estado.estado_sprint([]) == "planeando"
    assert estado.estado_sprint([_c()]) == "planeando"
    assert estado.estado_sprint([_c(estado="referencias", referencias_listas=1)]) == "referencias"
    listas = [_c(estado="referencias", referencias_listas=5), _c(estado="referencias", referencias_listas=6)]
    assert estado.estado_sprint(listas) == "listo_para_generar"
    assert estado.estado_sprint([_c(estado="referencias", referencias_listas=1)], listo_manual=True) == "listo_para_generar"
    assert estado.estado_sprint([_c(estado="generando"), _c(estado="revision")]) == "generando"
    assert estado.estado_sprint([_c(estado="revision"), _c(estado="completada")]) == "revision"
    assert estado.estado_sprint([_c(estado="completada")], cerrado=True) == "completado"


def test_recalcular_escribe_estados(base_temporal):
    from sprints import datos, estado
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31", referencias_objetivo_defecto=1)
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 0)
    assert estado.recalcular("acme", sid)["estado"] == "planeando"
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")
    sp = estado.recalcular("acme", sid)
    assert sp["estado"] == "referencias" and sp["campanas"][0]["estado"] == "referencias"
    datos.actualizar_referencia("acme", rid, descripcion="luz")
    assert estado.recalcular("acme", sid)["estado"] == "listo_para_generar"
    assert datos.sprint("acme", sid)["estado"] == "listo_para_generar"
    assert estado.recalcular("acme", 999) is None
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_progreso_estado.py -q`
Expected: FAIL (`No module named 'sprints.progreso'`).

- [ ] **Step 3: Escribir `sprints/progreso.py`**

```python
# sprints/progreso.py
"""
Progreso de campañas y sprints (spec §1.4). Funciones puras sobre los dicts
que devuelve sprints.datos: sin base de datos, sin Flask.
"""

ETAPAS_REFERENCIAS = ("planeada", "referencias", "ideas_propuestas", "ideas_aprobadas")


def fraccion_referencias(listas, objetivo):
    objetivo = int(objetivo or 0)
    if objetivo <= 0:
        return 1.0
    return min(int(listas or 0) / objetivo, 1.0)


def planeadas(c):
    return int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0)


def _salida(etapa, fraccion, texto, total):
    fraccion = max(0.0, min(float(fraccion), 1.0))
    return {"etapa": etapa, "fraccion": round(fraccion, 3), "porcentaje": int(round(fraccion * 100)),
            "texto": texto, "planeadas": total}


def progreso_campana(c):
    total = planeadas(c)
    estado = c.get("estado") or "planeada"
    if estado in ETAPAS_REFERENCIAS:
        listas, objetivo = int(c.get("referencias_listas") or 0), int(c.get("referencias_objetivo") or 0)
        return _salida("referencias", fraccion_referencias(listas, objetivo), f"{listas} / {objetivo} referencias", total)
    if estado == "generando":
        listas = int(c.get("piezas_listas") or 0)
        return _salida("produccion", listas / total if total else 0.0, f"{listas} de {total} piezas listas", total)
    aprobadas = int(c.get("piezas_aprobadas") or 0)
    return _salida("revision", aprobadas / total if total else 0.0, f"{aprobadas} de {total} aprobadas", total)


def progreso_sprint(campanas):
    """Promedio de las campañas ponderado por piezas planeadas."""
    campanas = list(campanas or [])
    pesos = sum(planeadas(c) for c in campanas)
    listas = sum(int(c.get("piezas_listas") or 0) for c in campanas)
    aprobadas = sum(int(c.get("piezas_aprobadas") or 0) for c in campanas)
    if pesos <= 0:
        return {"fraccion": 0.0, "porcentaje": 0, "planeadas": 0, "listas": 0, "aprobadas": 0,
                "texto": "sin piezas planeadas"}
    fr = sum(progreso_campana(c)["fraccion"] * planeadas(c) for c in campanas) / pesos
    return {"fraccion": round(fr, 3), "porcentaje": int(round(fr * 100)), "planeadas": pesos, "listas": listas,
            "aprobadas": aprobadas, "texto": f"{listas} de {pesos} piezas"}


def cobertura(campana, referencias):
    """Sugerencias (no bloquean): qué intención falta según lo planeado."""
    etiquetas = {t for r in (referencias or []) for t in (r.get("intencion") or [])}
    avisos = []
    nv, ni = int(campana.get("n_videos") or 0), int(campana.get("n_imagenes") or 0)
    if nv > 0 and not etiquetas & {"movimiento_camara", "transiciones"}:
        avisos.append(f"Te faltan referencias de movimiento de cámara o transiciones y hay {nv} videos planeados.")
    if ni > 0 and not etiquetas & {"composicion", "angulo_producto"}:
        avisos.append(f"Te faltan referencias de composición o ángulo de producto y hay {ni} imágenes planeadas.")
    return avisos
```

- [ ] **Step 4: Escribir `sprints/estado.py`**

```python
# sprints/estado.py
"""
Estados de campaña y sprint (spec §1.3). Se guardan en la base, pero se
vuelven a derivar de los datos después de cada evento (subida de referencia,
ideas, lote, QA, revisión) para que la interfaz nunca mienta.
`estado_campana` y `estado_sprint` son puras; `recalcular` escribe.
"""
from sprints import datos

_TERMINADAS = ("listo", "error", "degradada")


def estado_campana(n_referencias, planeadas, ideas=(), piezas=()):
    """`ideas`: dicts con `estado_idea` (propuesta|aprobada|descartada).
    `piezas`: dicts con `estado` de la sesión de Crear
    (pendiente|generando|listo|error|degradada) y `revision`
    (pendiente|aprobada|rechazada). En la Parte 1 llegan vacíos."""
    ideas, piezas = list(ideas or []), list(piezas or [])
    if any(p.get("estado") in ("pendiente", "generando") for p in piezas):
        return "generando"
    if piezas and all(p.get("estado") in _TERMINADAS for p in piezas):
        aprobadas = sum(1 for p in piezas if p.get("revision") == "aprobada")
        return "completada" if planeadas and aprobadas >= planeadas else "revision"
    aprobadas_ideas = sum(1 for i in ideas if i.get("estado_idea") == "aprobada")
    if ideas and planeadas and aprobadas_ideas >= planeadas:
        return "ideas_aprobadas"
    if ideas:
        return "ideas_propuestas"
    if int(n_referencias or 0) >= 1:
        return "referencias"
    return "planeada"


def estado_sprint(campanas, listo_manual=False, cerrado=False):
    if cerrado:
        return "completado"
    campanas = list(campanas or [])
    if not campanas:
        return "planeando"
    estados = [c.get("estado") for c in campanas]
    if "generando" in estados:
        return "generando"
    if all(e in ("revision", "completada") for e in estados):
        return "revision"
    if listo_manual or all(int(c.get("referencias_listas") or 0) >= int(c.get("referencias_objetivo") or 1)
                           for c in campanas):
        return "listo_para_generar"
    if any(e != "planeada" for e in estados):
        return "referencias"
    return "planeando"


def recalcular(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id)
    if not sp:
        return None
    for c in sp["campanas"]:
        total = int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0)
        nuevo = estado_campana(c["referencias_total"], total, ideas=c.get("ideas") or [], piezas=c.get("piezas") or [])
        if nuevo != c["estado"]:
            datos.actualizar_campana(cliente, c["id"], estado=nuevo)
            c["estado"] = nuevo
    nuevo_sp = estado_sprint(sp["campanas"], listo_manual=bool((sp.get("extra") or {}).get("listo_manual")),
                             cerrado=sp["estado"] == "completado")
    if nuevo_sp != sp["estado"]:
        datos.actualizar_sprint(cliente, sprint_id, estado=nuevo_sp)
        sp["estado"] = nuevo_sp
    return sp
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_progreso_estado.py -q`
Expected: PASS (6 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/progreso.py sprints/estado.py
/opt/homebrew/bin/git add sprints/progreso.py sprints/estado.py tests/test_sprints_progreso_estado.py
/opt/homebrew/bin/git commit -m "Sprints: progreso ponderado, cobertura de intención y recálculo de estados

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `sprints/analisis.py` y la tarea `sprint_analizar_referencia`

**Files:**
- Create: `sprints/analisis.py`, `tareas/sprints.py`
- Modify: `tareas/__init__.py` (`cargar_todas`)
- Test: `tests/test_sprints_analisis.py`, `tests/test_tareas_sprints.py`

**Interfaces:**
- Produces (analisis): `CLAVES`, `PROMPT_ANALISIS`, `AnalisisInvalido(RuntimeError)`, `_llamar(content, max_tokens=700) -> str` (única función que toca la API; las pruebas la reemplazan), `_parsear_json(texto) -> dict`, `analizar(referencia: dict, marca="") -> dict` (claves de `CLAVES`; reintenta una vez con corrección si el JSON no sirve).
- Produces (tareas): `job_id_analizar(cliente, referencia_id) -> str`, `encolar_analisis(cliente, referencia_id) -> bool`, handler registrado `sprint_analizar_referencia` con `payload {cliente, referencia_id}` y `AL_INTERRUMPIR` que deja `analisis_estado="error"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_sprints_analisis.py
import json

import pytest

JSON_OK = {"resumen": "Espejo redondo con luz cálida", "paleta": ["#F2E9E4", "#C9A227", "#1B2A41"],
           "composicion": "producto centrado", "iluminacion": "lateral cálida", "movimiento": "sin movimiento",
           "tipografia": "ninguna", "estetica": "minimalista y cálida", "storytelling": "calma en casa",
           "elementos": ["espejo", "pared", "planta"]}


def test_parsear_json_tolera_bloques_de_codigo():
    from sprints import analisis
    texto = "```json\n" + json.dumps(JSON_OK) + "\n```"
    assert analisis._parsear_json(texto)["paleta"] == ["#F2E9E4", "#C9A227", "#1B2A41"]
    assert analisis._parsear_json("Claro: " + json.dumps(JSON_OK) + " fin")["resumen"].startswith("Espejo")
    with pytest.raises(analisis.AnalisisInvalido):
        analisis._parsear_json("no hay json")
    with pytest.raises(analisis.AnalisisInvalido):
        analisis._parsear_json(json.dumps({"resumen": "solo esto"}))
    sucio = dict(JSON_OK, paleta=["#FFF", "rojo", "#000", "#111", "#222", "#333"])
    assert analisis._parsear_json(json.dumps(sucio))["paleta"] == ["#FFF", "#000", "#111", "#222", "#333"]


def test_analizar_imagen_manda_url_y_reintenta(monkeypatch):
    from sprints import analisis
    llamadas = []
    respuestas = ["esto no es json", json.dumps(JSON_OK)]
    def llamar_falso(content, max_tokens=700):
        llamadas.append(content)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", llamar_falso)
    ref = {"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": ["paleta", "otro"], "intencion_otro": "textura",
           "descripcion": "me gusta la luz"}
    r = analisis.analizar(ref, marca="Vidrios Sol")
    assert r["resumen"].startswith("Espejo") and len(llamadas) == 2
    texto = llamadas[0][0]["text"]
    assert "Paleta de colores" in texto and "textura" in texto and "me gusta la luz" in texto and "Vidrios Sol" in texto
    assert llamadas[0][1] == {"type": "image", "source": {"type": "url", "url": "https://r2/a.jpg"}}
    assert "no sirvió" in llamadas[1][-1]["text"]


def test_analizar_video_usa_fotogramas_locales(monkeypatch, tmp_path):
    from sprints import analisis
    import referencias_link
    monkeypatch.setattr(referencias_link, "fotogramas", lambda ruta, n=4: [b"f1", b"f2", b"f3"][:n])
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps(JSON_OK))
    local = tmp_path / "v.mp4"; local.write_bytes(b"x")
    analisis.analizar({"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.frame.jpg",
                       "ruta_local": str(local), "intencion": [], "descripcion": ""})
    imagenes = [b for b in capturado["c"] if b["type"] == "image"]
    assert len(imagenes) == 3 and imagenes[0]["source"]["type"] == "base64"
    # Sin archivo local, cae al fotograma de R2.
    analisis.analizar({"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.frame.jpg",
                       "ruta_local": "/no/existe.mp4", "intencion": [], "descripcion": ""})
    imagenes = [b for b in capturado["c"] if b["type"] == "image"]
    assert imagenes == [{"type": "image", "source": {"type": "url", "url": "https://r2/v.frame.jpg"}}]
    with pytest.raises(analisis.AnalisisInvalido):
        analisis.analizar({"tipo": "imagen", "url": "", "intencion": [], "descripcion": ""})
```

```python
# tests/test_tareas_sprints.py
import pytest


def _referencia(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo", tid, 1, 1)
    return sid, cid, datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg")


def test_job_ids():
    from tareas import sprints as ts
    assert ts.job_id_analizar("acme", 7) == "acme__ref7__analizar"
    assert ts.job_id_sugerir("acme") == "acme__sprints__sugerir_personas"
    assert ts.job_id_link("acme", 3) == "acme__campana3__link"


def test_analizar_referencia_guarda_analisis(base_temporal, monkeypatch):
    import tareas
    from sprints import analisis, datos
    from tareas import sprints as ts
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(analisis, "analizar", lambda ref, marca="": {"resumen": "ok", "paleta": ["#000"]})
    tareas.cargar_todas()
    assert "sprint_analizar_referencia" in tareas.REGISTRO
    msg = tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid},
                                                         "job_id": ts.job_id_analizar("acme", rid)})
    r = datos.referencia("acme", rid)
    assert r["analisis_estado"] == "listo" and r["analisis"]["resumen"] == "ok" and "analizada" in msg.lower()
    assert tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": 999}}) == "La referencia ya no existe."


def test_analizar_referencia_error_deja_rastro(base_temporal, monkeypatch):
    import tareas
    from sprints import analisis, datos
    sid, cid, rid = _referencia(datos)
    def rompe(ref, marca=""):
        raise RuntimeError("Claude caído")
    monkeypatch.setattr(analisis, "analizar", rompe)
    tareas.cargar_todas()
    with pytest.raises(RuntimeError):
        tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}})
    r = datos.referencia("acme", rid)
    assert r["analisis_estado"] == "error" and "Claude caído" in r["analisis"]["error"]
    datos.actualizar_referencia("acme", rid, analisis_estado="pendiente")
    tareas.AL_INTERRUMPIR["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}}, "reinicio")
    assert datos.referencia("acme", rid)["analisis_estado"] == "error"


def test_encolar_analisis_usa_el_worker(base_temporal, monkeypatch):
    import trabajos
    from tareas import sprints as ts
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload, kw)) or True)
    assert ts.encolar_analisis("acme", 5) is True
    job_id, tipo, payload, kw = encolados[0]
    assert job_id == "acme__ref5__analizar" and tipo == "sprint_analizar_referencia"
    assert payload == {"cliente": "acme", "referencia_id": 5} and kw["max_intentos"] == 3 and kw["cliente"] == "acme"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_analisis.py tests/test_tareas_sprints.py -q`
Expected: FAIL (módulos ausentes).

- [ ] **Step 3: Escribir `sprints/analisis.py`**

```python
# sprints/analisis.py
"""
Análisis de una referencia con Claude (visión), persistido en
`referencia.analisis` (spec §1.5). Es lo que después alimenta el prompt
maestro de la Parte 2. `_llamar` es la única función que toca la API: las
pruebas la reemplazan.
"""
import base64
import json
import os

from sprints import datos

CLAVES = ("resumen", "paleta", "composicion", "iluminacion", "movimiento", "tipografia", "estetica",
          "storytelling", "elementos")

PROMPT_ANALISIS = """Eres director de arte de anuncios cortos para redes sociales. Vas a ver una referencia visual (una imagen, o fotogramas en orden de un video) que una persona subió para inspirar contenido de la marca {marca}.
Lo que le interesa reutilizar de esta referencia: {intencion}.
Lo que escribió sobre ella: «{descripcion}».

Responde SOLO con un objeto JSON, sin texto antes ni después, con exactamente estas claves:
- "resumen": qué se ve y por qué funciona, máximo 40 palabras.
- "paleta": lista de 3 a 5 colores dominantes en hexadecimal (#RRGGBB).
- "composicion": encuadre, distancia y dónde está el producto o el sujeto.
- "iluminacion": tipo, dirección y temperatura de la luz.
- "movimiento": movimiento de cámara y ritmo; "sin movimiento" si es una imagen.
- "tipografia": tipografía y ubicación del texto en pantalla; "ninguna" si no hay texto.
- "estetica": estilo general en 5 a 10 palabras.
- "storytelling": qué cuenta o sugiere la escena, en una frase.
- "elementos": lista de 3 a 8 sustantivos con lo que aparece.
Todo en español. No menciones "fotograma" ni "imagen": describe la escena."""


class AnalisisInvalido(RuntimeError):
    pass


def _llamar(content, max_tokens=700):
    """Una llamada a Claude con bloques de texto e imagen; devuelve el texto."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _parsear_json(texto):
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
    faltan = [k for k in CLAVES if k not in data]
    if faltan:
        raise AnalisisInvalido(f"Faltan claves: {', '.join(faltan)}")
    data["paleta"] = [str(c) for c in (data.get("paleta") or []) if str(c).startswith("#")][:5]
    data["elementos"] = [str(e) for e in (data.get("elementos") or [])][:8]
    return {k: data[k] for k in CLAVES}


def _bloques_imagen(referencia):
    """Imagen: su URL. Video: hasta 3 fotogramas del archivo local; si el
    archivo ya no está, el fotograma que quedó en R2."""
    bloques = []
    ruta = referencia.get("ruta_local")
    if referencia.get("tipo") == "video" and ruta and os.path.exists(ruta):
        from referencias_link import fotogramas
        for b in fotogramas(ruta, n=3):
            bloques.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(b).decode()}})
    if not bloques:
        url = referencia.get("frame_url") if referencia.get("tipo") == "video" else referencia.get("url")
        if url:
            bloques.append({"type": "image", "source": {"type": "url", "url": url}})
    return bloques


def analizar(referencia, marca=""):
    """Devuelve el dict con CLAVES. Reintenta una sola vez si el JSON no sirve."""
    etiquetas = [datos.INTENCIONES_NOMBRE.get(i, i) for i in (referencia.get("intencion") or [])]
    intencion = ", ".join(etiquetas) or "todo lo que valga la pena reutilizar"
    if referencia.get("intencion_otro"):
        intencion += f" ({referencia['intencion_otro']})"
    texto = PROMPT_ANALISIS.format(marca=marca or "este proyecto", intencion=intencion,
                                   descripcion=referencia.get("descripcion") or "sin descripción")
    imagenes = _bloques_imagen(referencia)
    if not imagenes:
        raise AnalisisInvalido("La referencia no tiene imagen ni fotograma que analizar.")
    content = [{"type": "text", "text": texto}] + imagenes
    try:
        return _parsear_json(_llamar(content))
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        return _parsear_json(_llamar(content))
```

- [ ] **Step 4: Escribir `tareas/sprints.py` y registrarlo en `cargar_todas`**

```python
# tareas/sprints.py
"""
Tareas del worker para Sprints (Parte 1): analizar una referencia con Claude,
sugerir personas y traer una referencia desde un link. Las tres son baratas
(centavos, sin generación de video), por eso llevan reintentos.

Ids de trabajo (los mismos que usan las rutas para encolar y consultar):
  sprint_analizar_referencia -> f"{cliente}__ref{referencia_id}__analizar"   (max_intentos=3)
  sprint_sugerir_personas    -> f"{cliente}__sprints__sugerir_personas"      (max_intentos=2)
  sprint_referencia_link     -> f"{cliente}__campana{campana_id}__link"      (max_intentos=2)
"""
import os
from datetime import datetime

import proyectos
import referencias_link
import trabajos
from sprints import analisis, archivos, datos, sugerencias
from tareas import al_interrumpir, registrar


def job_id_analizar(cliente, referencia_id):
    return f"{cliente}__ref{referencia_id}__analizar"


def job_id_sugerir(cliente):
    return f"{cliente}__sprints__sugerir_personas"


def job_id_link(cliente, campana_id):
    return f"{cliente}__campana{campana_id}__link"


def encolar_analisis(cliente, referencia_id):
    return trabajos.encolar(job_id_analizar(cliente, referencia_id), "sprint_analizar_referencia",
                            {"cliente": cliente, "referencia_id": referencia_id}, cliente=cliente,
                            duracion_estimada=20, max_intentos=3)


def encolar_sugerir(cliente, cuantas=3):
    return trabajos.encolar(job_id_sugerir(cliente), "sprint_sugerir_personas",
                            {"cliente": cliente, "cuantas": int(cuantas)}, cliente=cliente,
                            duracion_estimada=25, max_intentos=2)


def encolar_link(cliente, campana_id, url):
    return trabajos.encolar(job_id_link(cliente, campana_id), "sprint_referencia_link",
                            {"cliente": cliente, "campana_id": campana_id, "url": url}, cliente=cliente,
                            duracion_estimada=60, max_intentos=2)


@registrar("sprint_analizar_referencia")
def ejecutar_analizar(tarea):
    p = tarea["payload"]
    cliente, rid = p["cliente"], int(p["referencia_id"])
    ref = datos.referencia(cliente, rid)
    if not ref:
        return "La referencia ya no existe."
    try:
        resultado = analisis.analizar(ref, marca=proyectos.nombre_visible(cliente))
    except Exception as e:
        datos.actualizar_referencia(cliente, rid, analisis_estado="error", analisis={"error": str(e)})
        raise
    datos.actualizar_referencia(cliente, rid, analisis=resultado, analisis_estado="listo")
    return "Referencia analizada."


@al_interrumpir("sprint_analizar_referencia")
def interrumpida_analizar(tarea, mensaje):
    p = tarea["payload"]
    datos.actualizar_referencia(p["cliente"], int(p["referencia_id"]), analisis_estado="error",
                                analisis={"error": mensaje})


@registrar("sprint_sugerir_personas")
def ejecutar_sugerir(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    propuestas = sugerencias.sugerir_personas(cliente, cuantas=int(p.get("cuantas") or 3))
    for persona in propuestas:
        datos.crear_persona(cliente, persona["nombre"], resumen=persona.get("resumen", ""),
                            descripcion=persona.get("descripcion", ""), edad_rango=persona.get("edad_rango", ""),
                            tono=persona.get("tono", ""), senales_visuales=persona.get("senales_visuales"),
                            palabras_clave=persona.get("palabras_clave"), color=persona.get("color"),
                            origen="sugerida_ia")
    return f"{len(propuestas)} personas sugeridas — revísalas y edítalas."


@registrar("sprint_referencia_link")
def ejecutar_link(tarea):
    p = tarea["payload"]
    cliente, campana_id, url = p["cliente"], int(p["campana_id"]), p["url"]
    carpeta = archivos.carpeta(cliente)
    os.makedirs(carpeta, exist_ok=True)
    nombre_base = f"link_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    ruta, meta = referencias_link.descargar(url, carpeta, nombre_base)
    info = archivos.registrar_local(cliente, ruta, (meta or {}).get("titulo") or url)
    rid = datos.agregar_referencia(cliente, campana_id, info["tipo"], info["url"], frame_url=info["frame_url"],
                                   ruta_local=info["ruta_local"], origen="link", titulo=info["titulo"])
    encolar_analisis(cliente, rid)
    return "Referencia agregada desde el link."
```

En `tareas/__init__.py`, `cargar_todas` queda:

```python
def cargar_todas():
    """Importa los módulos con tareas reales. Se llama desde worker.main(), no
    al importar el paquete, para que los tests puedan registrar tareas falsas
    sin arrastrar proveedores externos."""
    from tareas import experimentos, final_edition, flowplus, meta, sprints, swap  # noqa: F401
```

`sprints/sugerencias.py` se escribe en la Task 8; para que `tareas/sprints.py` importe hoy, crear ahora un módulo mínimo que la Task 8 reemplaza:

```python
# sprints/sugerencias.py (versión mínima; la Task 8 la completa)
"""Personas sugeridas por Claude (spec §1.6). Se completa en la Task 8."""


def sugerir_personas(cliente, cuantas=3):
    raise NotImplementedError("Task 8")
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_analisis.py tests/test_tareas_sprints.py tests/test_worker.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/analisis.py sprints/sugerencias.py tareas/sprints.py tareas/__init__.py
/opt/homebrew/bin/git add sprints/analisis.py sprints/sugerencias.py tareas/sprints.py tareas/__init__.py tests/test_sprints_analisis.py tests/test_tareas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: análisis de referencias con Claude (visión) y tarea del worker

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `sprints/sugerencias.py` — personas sugeridas por Claude

**Files:**
- Modify: `sprints/sugerencias.py` (reemplazar la versión mínima)
- Test: `tests/test_sprints_analisis.py` (agregar), `tests/test_tareas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `analisis._llamar`, `marca.guia_efectiva(cliente)`, `catalogo_productos.listar(cliente, "producto")`, `proyectos.nombre_visible(cliente)`.
- Produces: `COLORES`, `PROMPT_PERSONAS`, `sugerir_personas(cliente, cuantas=3) -> list[dict]` (cada uno con `nombre, resumen, descripcion, edad_rango, tono, senales_visuales, palabras_clave, color`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_sprints_analisis.py`:

```python
def test_sugerir_personas_arma_prompt_y_colores(monkeypatch):
    from sprints import analisis, sugerencias
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural, sin saturar.")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [{"nombre": "Espejo LED", "descripcion": "redondo"}])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    capturado = {}
    salida = {"personas": [
        {"nombre": "Cliente Premium", "resumen": "r", "descripcion": "d", "edad_rango": "35-50", "tono": "t",
         "senales_visuales": ["cocina"], "palabras_clave": ["lujo"]},
        {"nombre": "Familia joven", "resumen": "r", "descripcion": "d", "edad_rango": "28-40", "tono": "t",
         "senales_visuales": ["sala"], "palabras_clave": ["hogar"]},
        {"nombre": "sin claves"}]}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps(salida))
    personas = sugerencias.sugerir_personas("acme", cuantas=2)
    texto = capturado["c"][0]["text"]
    assert "Vidrios Sol" in texto and "Luz natural" in texto and "Espejo LED: redondo" in texto and "Propón 2" in texto
    assert [p["nombre"] for p in personas] == ["Cliente Premium", "Familia joven"]
    assert personas[0]["color"] == sugerencias.COLORES[0] and personas[1]["color"] == sugerencias.COLORES[1]


def test_sugerir_personas_rechaza_json_malo(monkeypatch):
    from sprints import analisis, sugerencias
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "X")
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: "nada")
    with pytest.raises(analisis.AnalisisInvalido):
        sugerencias.sugerir_personas("acme")
```

Agregar a `tests/test_tareas_sprints.py`:

```python
def test_sugerir_personas_crea_filas(base_temporal, monkeypatch):
    import tareas
    from sprints import datos, sugerencias
    monkeypatch.setattr(sugerencias, "sugerir_personas", lambda c, cuantas=3: [
        {"nombre": "Cliente Premium", "resumen": "r", "descripcion": "d", "edad_rango": "35-50", "tono": "t",
         "senales_visuales": ["cocina"], "palabras_clave": ["lujo"], "color": "#4d8dff"}])
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_sugerir_personas"]({"payload": {"cliente": "acme", "cuantas": 1}})
    p = datos.personas("acme")
    assert len(p) == 1 and p[0]["origen"] == "sugerida_ia" and p[0]["color"] == "#4d8dff" and "1 personas" in msg
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_sprints_analisis.py tests/test_tareas_sprints.py -q`
Expected: FAIL (`NotImplementedError` / atributos ausentes).

- [ ] **Step 3: Escribir `sprints/sugerencias.py` completo**

```python
# sprints/sugerencias.py
"""
Personas (arquetipos de cliente) sugeridas por Claude a partir de la guía de
estilo y el catálogo del proyecto (spec §1.6). Nacen con origen
`sugerida_ia` y se editan o descartan desde la pestaña Sprints.
"""
import json

import catalogo_productos
import marca
import proyectos
from sprints.analisis import AnalisisInvalido, _llamar

COLORES = ("#4d8dff", "#7c5cff", "#3ecf8e", "#e8b339", "#ff5f7a", "#22b8cf")
_CLAVES = ("nombre", "resumen", "descripcion", "edad_rango", "tono", "senales_visuales", "palabras_clave")

PROMPT_PERSONAS = """Eres estratega de marketing para la marca {marca}.
Guía de estilo de la marca:
{guia}

Productos del catálogo:
{productos}

Propón {cuantas} arquetipos de cliente (personas) distintos entre sí y realistas para esta marca en Latinoamérica. Responde SOLO con un objeto JSON con la forma {{"personas": [...]}}, donde cada persona tiene exactamente estas claves: "nombre" (2 o 3 palabras, ej. "Cliente Premium"), "resumen" (una línea de máximo 15 palabras), "descripcion" (quién es, qué le importa, qué le duele; 40 a 70 palabras), "edad_rango" (ej. "30-45"), "tono" (cómo hablarle, máximo 12 palabras), "senales_visuales" (lista de 3 a 5 escenarios, estilos de vida u objetos que la rodean), "palabras_clave" (lista de 3 a 6 palabras). Todo en español, sin texto fuera del JSON."""


def _parsear(texto):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise AnalisisInvalido(f"JSON inválido: {e}")
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, list):
        raise AnalisisInvalido("El JSON no trae la lista «personas».")
    limpias = []
    for p in personas:
        if not isinstance(p, dict) or not (p.get("nombre") or "").strip() or any(k not in p for k in _CLAVES):
            continue
        limpias.append({k: p[k] for k in _CLAVES})
    if not limpias:
        raise AnalisisInvalido("Ninguna persona venía completa.")
    return limpias


def sugerir_personas(cliente, cuantas=3):
    cuantas = max(1, int(cuantas or 3))
    guia = (marca.guia_efectiva(cliente) or "").strip() or "(sin guía de estilo todavía)"
    productos = catalogo_productos.listar(cliente, "producto")
    lista = "\n".join(f"- {p['nombre']}" + (f": {p['descripcion']}" if p.get("descripcion") else "") for p in productos)
    texto = PROMPT_PERSONAS.format(marca=proyectos.nombre_visible(cliente), guia=guia,
                                   productos=lista or "- (catálogo vacío)", cuantas=cuantas)
    personas = _parsear(_llamar([{"type": "text", "text": texto}], max_tokens=1500))[:cuantas]
    for i, p in enumerate(personas):
        p["color"] = COLORES[i % len(COLORES)]
    return personas
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_sprints_analisis.py tests/test_tareas_sprints.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile sprints/sugerencias.py
/opt/homebrew/bin/git add sprints/sugerencias.py tests/test_sprints_analisis.py tests/test_tareas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: personas sugeridas por Claude desde la guía de marca y el catálogo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: tarea `sprint_referencia_link` (prueba) 

**Files:**
- Test: `tests/test_tareas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `referencias_link.descargar(url, carpeta, nombre_base) -> (ruta_mp4, meta)`, `archivos.registrar_local`, `datos.agregar_referencia`, `encolar_analisis`. El handler ya quedó escrito en la Task 7; esta tarea lo cubre con pruebas y arregla lo que falle.

- [ ] **Step 1: Escribir la prueba que falla**

```python
def test_referencia_desde_link_descarga_registra_y_encola(base_temporal, monkeypatch, tmp_path):
    import tareas
    import referencias_link
    from sprints import archivos, datos
    from tareas import sprints as ts
    sid, cid, _ = _referencia(datos)
    def descargar_falso(url, carpeta, nombre_base):
        ruta = tmp_path / f"{nombre_base}.mp4"; ruta.write_bytes(b"mp4")
        return str(ruta), {"fuente": "tiktok", "titulo": "Baile", "url_origen": url}
    monkeypatch.setattr(referencias_link, "descargar", descargar_falso)
    monkeypatch.setattr(archivos, "registrar_local", lambda c, ruta, titulo: {
        "tipo": "video", "url": "https://r2/l.mp4", "frame_url": "https://r2/l.frame.jpg", "ruta_local": ruta, "titulo": titulo})
    encolados = []
    monkeypatch.setattr(ts, "encolar_analisis", lambda c, rid: encolados.append((c, rid)) or True)
    tareas.cargar_todas()
    msg = tareas.REGISTRO["sprint_referencia_link"]({"payload": {"cliente": "acme", "campana_id": cid, "url": "https://t.t/v"}})
    refs = datos.referencias("acme", cid)
    nueva = refs[-1]
    assert nueva["origen"] == "link" and nueva["titulo"] == "Baile" and nueva["frame_url"] == "https://r2/l.frame.jpg"
    assert encolados == [("acme", nueva["id"])] and "link" in msg
```

- [ ] **Step 2: Correr**

Run: `venv/bin/python -m pytest tests/test_tareas_sprints.py -q`
Expected: PASS si la Task 7 quedó bien; si falla, corregir `ejecutar_link` en `tareas/sprints.py` hasta que pase (el contrato es el de la prueba).

- [ ] **Step 3: Commit**

```bash
/opt/homebrew/bin/git add tests/test_tareas_sprints.py tareas/sprints.py
/opt/homebrew/bin/git commit -m "Sprints: prueba de la referencia desde link (descarga, R2, análisis encolado)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Blueprint `sprints/rutas.py` — registro, contexto, personas y temporadas

**Files:**
- Create: `sprints/rutas.py`
- Modify: `dashboard.py` (import + `register_blueprint` junto a `app = Flask(__name__)`; `**sprints_rutas.contexto(cliente)` en el `render_template("cliente.html", ...)` de `ver_cliente`)
- Test: `tests/test_rutas_sprints.py`

**Interfaces:**
- Produces: `bp` (Blueprint `sprints`, prefijo `/cliente/<cliente>/sprints`), `contexto(cliente) -> dict` con las claves `sprints_lista`, `personas_sprint`, `temporadas_sprint`, `presets_temporadas`, `pais_calendario`, `paises_calendario`, `productos_sprint`, `destinos_sprint`, `estimado_sprint`, `intenciones_sprint`, `tipos_temporada`, `trabajo_sugerir`, `hoy`. Endpoints: `sprints.persona_crear`, `sprints.persona_editar`, `sprints.persona_archivar`, `sprints.personas_sugerir`, `sprints.temporada_crear`, `sprints.temporada_editar`, `sprints.temporada_archivar`, `sprints.temporada_adoptar`, `sprints.calendario_pais`. Helpers reutilizados por las Tasks 11 y 12: `_volver`, `_quiere_json`, `_partir`, `_entero`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_rutas_sprints.py
"""Rutas del Blueprint sprints: validan y delegan a sprints.datos / tareas;
encolar, R2 y ffmpeg se monkeypatchean. Sesión admin como en
test_rutas_experimentos."""
import pytest


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
    from sprints import rutas
    encolados = []
    monkeypatch.setattr(rutas.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [
        {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "representativa_url": "https://r2/e.jpg"},
        {"id": "division_bano", "nombre": "División de baño", "descripcion": "", "representativa_url": None}])
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def test_persona_crear_editar_archivar(app):
    from sprints import datos
    c = app["c"]
    r = c.post("/cliente/acme/sprints/personas", data={"nombre": "Cliente Premium", "resumen": "Busca calidad",
                                                        "senales_visuales": "cocina moderna, luz natural", "color": "#4d8dff"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#sprints")
    p = datos.personas("acme")[0]
    assert p["senales_visuales"] == ["cocina moderna", "luz natural"] and p["color"] == "#4d8dff"
    c.post(f"/cliente/acme/sprints/personas/{p['id']}", data={"nombre": "Premium", "tono": "cercano"})
    assert datos.persona("acme", p["id"])["tono"] == "cercano"
    c.post(f"/cliente/acme/sprints/personas/{p['id']}/archivar")
    assert datos.personas("acme") == []
    c.post("/cliente/acme/sprints/personas", data={"nombre": ""})      # inválida: no crea
    assert datos.personas("acme") == []


def test_personas_sugerir_encola(app):
    app["c"].post("/cliente/acme/sprints/personas/sugerir", data={"cuantas": "3"})
    assert app["encolados"][0]["tipo"] == "sprint_sugerir_personas" and app["encolados"][0]["payload"]["cuantas"] == 3


def test_temporadas_crear_adoptar_pais(app):
    from sprints import datos
    import proyectos
    c = app["c"]
    c.post("/cliente/acme/sprints/temporadas", data={"nombre": "Lanzamiento", "inicio": "2026-10-01", "fin": "2026-10-20",
                                                      "tipo": "propia", "contexto": "nueva línea", "paleta": "#000, #fff"})
    t = datos.temporadas("acme")[0]
    assert t["nombre"] == "Lanzamiento" and t["mood_visual"]["paleta"] == ["#000", "#fff"]
    c.post("/cliente/acme/sprints/temporadas", data={"nombre": "Mal", "inicio": "2026-10-20", "fin": "2026-10-01"})
    assert len(datos.temporadas("acme")) == 1
    c.post("/cliente/acme/sprints/temporadas/pais", data={"pais": "MX"})
    assert proyectos.pais("acme") == "MX"
    c.post("/cliente/acme/sprints/temporadas/adoptar", data={"clave": "buen_fin", "anio": "2026"})
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["Lanzamiento", "El Buen Fin"]
    c.post(f"/cliente/acme/sprints/temporadas/{t['id']}/archivar")
    assert [x["nombre"] for x in datos.temporadas("acme")] == ["El Buen Fin"]


def test_contexto_trae_lo_que_usa_la_pestana(app):
    from sprints import datos, rutas
    datos.crear_persona("acme", "Premium")
    ctx = rutas.contexto("acme")
    assert ctx["personas_sprint"][0]["nombre"] == "Premium" and ctx["sprints_lista"] == []
    assert [p["id"] for p in ctx["productos_sprint"]] == ["espejo_led", "division_bano"]
    assert ctx["pais_calendario"] == "CO" and any(p["clave"] == "navidad" for p in ctx["presets_temporadas"])
    assert ctx["estimado_sprint"]["video"] > 0 and ctx["estimado_sprint"]["imagen"] > 0
    assert "es_CO" in [d["codigo"] for d in ctx["destinos_sprint"]] and ctx["trabajo_sugerir"] is None


def test_cliente_sin_permiso_no_entra(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.post("/cliente/acme/sprints/personas", data={"nombre": "X"})
    assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"]
    from sprints import datos
    assert datos.personas("acme") == []
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: FAIL (`No module named 'sprints.rutas'`).

- [ ] **Step 3: Escribir `sprints/rutas.py`**

```python
# sprints/rutas.py
"""
Rutas de la pestaña Sprints (Blueprint `sprints`, prefijo
/cliente/<cliente>/sprints). Solo validan, delegan a sprints.datos /
sprints.estado / tareas.sprints y redirigen; la lógica vive en esos módulos.
`dashboard._guard_por_cliente` protege estas rutas igual que las demás porque
la URL lleva <cliente>. `contexto(cliente)` es lo que `ver_cliente` agrega
al render de cliente.html para la pestaña.
"""
import json
from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import catalogo_productos
import proyectos
import trabajos
from final_edition import tipos as fe_tipos
from providers import flowplus_modelos
from sprints import calendario, datos, estado, progreso
from tareas import sprints as tareas_sprints

bp = Blueprint("sprints", __name__, url_prefix="/cliente/<cliente>/sprints")

DURACION_ESTIMADO_S = 8      # duración típica de un video del sprint para el costo en vivo
N_REFERENCIAS_ESTIMADO = 3   # referencias por imagen para el estimado


# ------------------------------------------------------------ helpers ---

def _volver(cliente, sid=None, cid=None):
    if cid is not None:
        return redirect(url_for("sprints.campana_ver", cliente=cliente, sid=sid, cid=cid))
    if sid is not None:
        return redirect(url_for("sprints.ver", cliente=cliente, sid=sid))
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="sprints"))


def _quiere_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _partir(texto):
    """'a, b\nc' -> ['a', 'b', 'c']"""
    return [x.strip() for x in (texto or "").replace("\n", ",").split(",") if x.strip()]


def _entero(campo, defecto=0):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(f"«{campo}» debe ser un número entero.")


def _mood_desde_form():
    return {"paleta": _partir(request.form.get("paleta")), "luz": (request.form.get("luz") or "").strip(),
            "elementos": _partir(request.form.get("elementos"))}


def _productos(cliente):
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion") or "",
             "representativa_url": p.get("representativa_url")} for p in catalogo_productos.listar(cliente, "producto")]


def contexto(cliente):
    """Lo que necesita _tab_sprints.html. Se llama desde dashboard.ver_cliente."""
    prefs = proyectos.preferencias_flowplus(cliente)
    modelo_video, modelo_imagen = prefs["modelo_video"], prefs["modelo_imagen"]
    lista = []
    for sp in datos.sprints(cliente):
        sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
        lista.append(sp)
    pais = proyectos.pais(cliente)
    return {
        "sprints_lista": lista,
        "personas_sprint": datos.personas(cliente),
        "temporadas_sprint": datos.temporadas(cliente),
        "presets_temporadas": calendario.presets(pais),
        "pais_calendario": pais,
        "paises_calendario": proyectos.PAISES_CALENDARIO,
        "productos_sprint": _productos(cliente),
        "destinos_sprint": [{"codigo": f"{p['idioma']}_{codigo}", "nombre": p["nombre"], "bandera": p["bandera"],
                             "idioma": p["idioma"]} for codigo, p in fe_tipos.PAISES.items()],
        "estimado_sprint": {
            "video": float((flowplus_modelos.estimate_video(modelo_video, DURACION_ESTIMADO_S) or {}).get("usd") or 0.0),
            "imagen": float((flowplus_modelos.estimate_imagen(modelo_imagen, N_REFERENCIAS_ESTIMADO) or {}).get("usd") or 0.0),
            "modelo_video": flowplus_modelos.VIDEO[modelo_video]["nombre"],
            "modelo_imagen": flowplus_modelos.IMAGEN[modelo_imagen]["nombre"],
            "duracion_s": DURACION_ESTIMADO_S,
        },
        "intenciones_sprint": datos.INTENCIONES_NOMBRE,
        "tipos_temporada": datos.TIPOS_TEMPORADA,
        "trabajo_sugerir": ({"job_id": tareas_sprints.job_id_sugerir(cliente)}
                            if trabajos.en_curso(tareas_sprints.job_id_sugerir(cliente)) else None),
        "hoy": date.today().isoformat(),
    }


# ----------------------------------------------------------- personas ---

def _campos_persona():
    return dict(resumen=request.form.get("resumen"), descripcion=request.form.get("descripcion"),
                edad_rango=request.form.get("edad_rango"), tono=request.form.get("tono"),
                senales_visuales=_partir(request.form.get("senales_visuales")),
                palabras_clave=_partir(request.form.get("palabras_clave")), color=request.form.get("color") or None)


@bp.post("/personas")
def persona_crear(cliente):
    try:
        datos.crear_persona(cliente, request.form.get("nombre"), **_campos_persona())
        flash("Persona creada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/personas/<int:pid>")
def persona_editar(cliente, pid):
    try:
        campos = {k: v for k, v in _campos_persona().items() if request.form.get(k) is not None}
        if request.form.get("nombre") is not None:
            campos["nombre"] = request.form.get("nombre")
        if not datos.actualizar_persona(cliente, pid, **campos):
            flash("Esa persona no existe.", "error")
        else:
            flash("Persona guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/personas/<int:pid>/archivar")
def persona_archivar(cliente, pid):
    datos.archivar_persona(cliente, pid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/personas/sugerir")
def personas_sugerir(cliente):
    cuantas = min(5, max(1, _entero("cuantas", 3)))
    if tareas_sprints.encolar_sugerir(cliente, cuantas):
        flash("Claude está proponiendo personas; aparecerán aquí en unos segundos.", "ok")
    else:
        flash("Ya hay una sugerencia en curso.", "error")
    return _volver(cliente)


# --------------------------------------------------------- temporadas ---

@bp.post("/temporadas")
def temporada_crear(cliente):
    try:
        datos.crear_temporada(cliente, request.form.get("nombre"), request.form.get("inicio"), request.form.get("fin"),
                              contexto=request.form.get("contexto"), mood_visual=_mood_desde_form(),
                              tipo=request.form.get("tipo") or "propia")
        flash("Temporada creada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>")
def temporada_editar(cliente, tid):
    try:
        campos = {}
        for k in ("nombre", "inicio", "fin", "contexto", "tipo"):
            if request.form.get(k) is not None:
                campos[k] = request.form.get(k)
        if any(request.form.get(k) is not None for k in ("paleta", "luz", "elementos")):
            campos["mood_visual"] = _mood_desde_form()
        if not datos.actualizar_temporada(cliente, tid, **campos):
            flash("Esa temporada no existe.", "error")
        else:
            flash("Temporada guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/<int:tid>/archivar")
def temporada_archivar(cliente, tid):
    datos.archivar_temporada(cliente, tid, archivada=request.form.get("desarchivar") is None)
    return _volver(cliente)


@bp.post("/temporadas/adoptar")
def temporada_adoptar(cliente):
    try:
        calendario.adoptar(cliente, request.form.get("clave") or "", pais=proyectos.pais(cliente),
                           anio=request.form.get("anio") or None)
        flash("Temporada agregada desde el calendario.", "ok")
    except (datos.ErrorDatos, ValueError) as e:
        flash(str(e), "error")
    return _volver(cliente)


@bp.post("/temporadas/pais")
def calendario_pais(cliente):
    try:
        proyectos.guardar_pais(cliente, request.form.get("pais"))
    except ValueError as e:
        flash(str(e), "error")
    return _volver(cliente)
```

- [ ] **Step 4: Registrar el Blueprint en `dashboard.py`**

Debajo de `app = Flask(__name__)` (línea ~91; después de la configuración de `secret_key` si la hay justo ahí):

```python
from sprints import rutas as sprints_rutas  # noqa: E402  (Blueprint de la pestaña Sprints)
app.register_blueprint(sprints_rutas.bp)
```

En `ver_cliente`, en la llamada `return render_template("cliente.html", ...)`, agregar como ÚLTIMO argumento:

```python
        **sprints_rutas.contexto(cliente),
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py tests/test_rutas_experimentos.py -q`
Expected: PASS (las de experimentos siguen verdes: el Blueprint no cambia nada de lo existente).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/rutas.py dashboard.py
/opt/homebrew/bin/git add sprints/rutas.py dashboard.py tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: Blueprint con personas, temporadas, calendario y contexto de la pestaña

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


---

### Task 11: Rutas de sprints y campañas, página de detalle del sprint

**Files:**
- Modify: `sprints/rutas.py` (agregar al final), `sprints/datos.py` (alias público `validar_cantidades`)
- Create: `templates/_sprint_macros.html`, `templates/_sprint_nav.html`, `templates/sprint_detalle.html`
- Test: `tests/test_rutas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `datos.crear_sprint`, `datos.agregar_campana`, `datos.actualizar_campana`, `datos.eliminar_campana`, `datos.combinaciones`, `datos.registrar_evento`, `estado.recalcular`, `progreso.progreso_campana/progreso_sprint`, helpers de la Task 10.
- Produces: `datos.validar_cantidades(n_videos, n_imagenes) -> (int, int)`; endpoints `sprints.crear` (POST `/nuevo`, formulario del asistente con `campanas_json` o una campaña con campos sueltos), `sprints.ver` (GET `/<sid>`), `sprints.progreso_json` (GET `/<sid>/progreso`), `sprints.marcar_listo` (POST `/<sid>/listo`), `sprints.archivar` (POST `/<sid>/archivar`), `sprints.campana_agregar` (POST `/<sid>/campanas`), `sprints.campana_editar` (POST `/<sid>/campanas/<cid>`), `sprints.campana_eliminar` (POST `/<sid>/campanas/<cid>/eliminar`); helpers `_sprint_o_404`, `_campana_o_404`, `_validar_campanas`; macros Jinja `anillo(pct, tam)` y `chip_estado(estado)`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_rutas_sprints.py`)

```python
import json


def _base(datos):
    pid = datos.crear_persona("acme", "Premium")
    tid = datos.crear_temporada("acme", "Verano", "2026-06-01", "2026-07-15")
    return pid, tid


def test_crear_sprint_con_matriz(app):
    from sprints import datos
    pid, tid = _base(datos)
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    campanas = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 10, "n_imagenes": 25},
                {"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid2, "n_videos": 3, "n_imagenes": 0}]
    r = app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "Octubre", "inicio": "2026-10-01", "fin": "2026-10-31",
                                                           "destinos": ["es_CO", "es_MX"], "referencias_objetivo": "4",
                                                           "campanas_json": json.dumps(campanas)})
    assert r.status_code == 302 and "/sprints/" in r.headers["Location"]
    sp = datos.sprints("acme")[0]
    assert sp["destinos"] == ["es_CO", "es_MX"] and sp["campanas_total"] == 2 and sp["piezas_planeadas"] == 38
    assert sp["campanas"][0]["referencias_objetivo"] == 4 and sp["estado"] == "planeando"


def test_crear_sprint_rechaza_duplicados_y_productos_ajenos(app):
    from sprints import datos
    pid, tid = _base(datos)
    dup = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}] * 2
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(dup)})
    assert datos.sprints("acme") == []
    ajeno = [{"persona_id": pid, "catalogo_id": "no_existe", "temporada_id": tid, "n_videos": 1, "n_imagenes": 0}]
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(ajeno)})
    assert datos.sprints("acme") == []
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": "[]"})
    assert datos.sprints("acme") == []
    cero = [{"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid, "n_videos": 0, "n_imagenes": 0}]
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "X", "inicio": "2026-10-01", "fin": "2026-10-31", "campanas_json": json.dumps(cero)})
    assert datos.sprints("acme") == []


def _sprint(datos, pid, tid):
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    return sid, cid


def test_detalle_progreso_listo_y_campanas(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    c = app["c"]
    r = c.get(f"/cliente/acme/sprints/{sid}")
    assert r.status_code == 200 and b"Espejo LED" in r.data and b"Premium" in r.data and b"Verano" in r.data
    assert c.get("/cliente/acme/sprints/999").status_code == 404
    j = c.get(f"/cliente/acme/sprints/{sid}/progreso").get_json()
    assert j["estado"] == "planeando" and j["campanas"][0]["etapa"] == "referencias" and j["sprint"]["planeadas"] == 3
    c.post(f"/cliente/acme/sprints/{sid}/listo")
    assert datos.sprint("acme", sid)["estado"] == "listo_para_generar"
    assert datos.sprint("acme", sid)["eventos"][0]["tipo"] == "marcado_listo"
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    c.post(f"/cliente/acme/sprints/{sid}/campanas", data={"persona_id": pid, "catalogo_id": "division_bano", "temporada_id": tid2,
                                                         "n_videos": "1", "n_imagenes": "1"})
    assert len(datos.campanas("acme", sid)) == 2
    c.post(f"/cliente/acme/sprints/{sid}/campanas", data={"persona_id": pid, "catalogo_id": "espejo_led", "temporada_id": tid,
                                                         "n_videos": "1", "n_imagenes": "1"})       # duplicada
    assert len(datos.campanas("acme", sid)) == 2
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}", data={"n_videos": "7"})
    assert datos.campana("acme", cid)["n_videos"] == 7
    otro_sid = datos.crear_sprint("acme", "Otro", "2026-11-01", "2026-11-30")
    assert c.post(f"/cliente/acme/sprints/{otro_sid}/campanas/{cid}", data={"n_videos": "1"}).status_code == 404
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/eliminar")
    assert len(datos.campanas("acme", sid)) == 1
    c.post(f"/cliente/acme/sprints/{sid}/archivar")
    assert datos.sprints("acme") == [datos.sprints("acme")[0]] and datos.sprints("acme")[0]["id"] == otro_sid
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: FAIL (404 en `/sprints/nuevo`, plantillas ausentes).

- [ ] **Step 3: Alias público en `sprints/datos.py`** (debajo de `_cantidades`)

```python
def validar_cantidades(n_videos, n_imagenes):
    """Para que la ruta valide todas las campañas ANTES de crear el sprint."""
    return _cantidades(n_videos, n_imagenes)
```

- [ ] **Step 4: Agregar las rutas al final de `sprints/rutas.py`**

```python
# ------------------------------------------------------------ sprints ---

def _sprint_o_404(cliente, sid):
    sp = estado.recalcular(cliente, sid)
    if not sp:
        abort(404)
    return sp


def _campana_o_404(cliente, sid, cid):
    c = datos.campana(cliente, cid)
    if not c or c["sprint_id"] != sid:
        abort(404)
    return c


def _campanas_desde_form():
    """El asistente manda las campañas como JSON en `campanas_json`:
    [{persona_id, catalogo_id, temporada_id, n_videos, n_imagenes}]. El
    formulario simple manda una sola con los campos sueltos."""
    crudo = request.form.get("campanas_json")
    if crudo:
        try:
            lista = json.loads(crudo)
        except ValueError:
            raise datos.ErrorDatos("Las campañas del asistente no se pudieron leer.")
        if not isinstance(lista, list):
            raise datos.ErrorDatos("Las campañas del asistente no se pudieron leer.")
        return lista
    if request.form.get("persona_id"):
        return [{"persona_id": request.form.get("persona_id"), "catalogo_id": request.form.get("catalogo_id"),
                 "temporada_id": request.form.get("temporada_id"), "n_videos": request.form.get("n_videos"),
                 "n_imagenes": request.form.get("n_imagenes"),
                 "referencias_objetivo": request.form.get("referencias_objetivo")}]
    return []


def _validar_campanas(cliente, lista):
    """Producto en el catálogo, cantidades válidas y sin combinaciones
    repetidas dentro del mismo envío. Devuelve la lista normalizada."""
    ids = {p["id"] for p in catalogo_productos.listar(cliente, "producto")}
    vistas, limpias = set(), []
    for i, c in enumerate(lista, 1):
        try:
            persona_id, temporada_id = int(c.get("persona_id") or 0), int(c.get("temporada_id") or 0)
        except (TypeError, ValueError):
            raise datos.ErrorDatos(f"Campaña {i}: persona o temporada inválida.")
        catalogo_id = (c.get("catalogo_id") or "").strip()
        if catalogo_id not in ids:
            raise datos.ErrorDatos(f"Campaña {i}: el producto «{catalogo_id}» no está en el catálogo.")
        n_videos, n_imagenes = datos.validar_cantidades(c.get("n_videos"), c.get("n_imagenes"))
        clave = (persona_id, catalogo_id, temporada_id)
        if clave in vistas:
            raise datos.ErrorDatos(f"Campaña {i}: esa combinación de persona, producto y temporada está repetida.")
        vistas.add(clave)
        limpias.append({"persona_id": persona_id, "catalogo_id": catalogo_id, "temporada_id": temporada_id,
                        "n_videos": n_videos, "n_imagenes": n_imagenes,
                        "referencias_objetivo": c.get("referencias_objetivo") or None})
    return limpias


@bp.post("/nuevo")
def crear(cliente):
    try:
        campanas = _validar_campanas(cliente, _campanas_desde_form())
        if not campanas:
            raise datos.ErrorDatos("Un sprint necesita al menos una campaña.")
        sid = datos.crear_sprint(cliente, request.form.get("nombre"), request.form.get("inicio"),
                                 request.form.get("fin"), destinos=[d for d in request.form.getlist("destinos") if d],
                                 referencias_objetivo_defecto=request.form.get("referencias_objetivo") or 5,
                                 notas=request.form.get("notas"))
        for c in campanas:
            datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                                  c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"])
        estado.recalcular(cliente, sid)
        flash(f"Sprint creado con {len(campanas)} campaña(s). Ahora sube referencias a cada campaña.", "ok")
        return _volver(cliente, sid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return _volver(cliente)


@bp.get("/<int:sid>")
def ver(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    for c in sp["campanas"]:
        c["progreso"] = progreso.progreso_campana(c)
    sp["progreso"] = progreso.progreso_sprint(sp["campanas"])
    productos = _productos(cliente)
    return render_template("sprint_detalle.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, productos_por_id={p["id"]: p for p in productos}, productos_sprint=productos,
                           personas_sprint=datos.personas(cliente), temporadas_sprint=datos.temporadas(cliente),
                           combinaciones=[list(x) for x in datos.combinaciones(cliente, sid)])


@bp.get("/<int:sid>/progreso")
def progreso_json(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    return jsonify({"estado": sp["estado"], "sprint": progreso.progreso_sprint(sp["campanas"]),
                    "campanas": [{"id": c["id"], "estado": c["estado"], **progreso.progreso_campana(c)}
                                 for c in sp["campanas"]]})


@bp.post("/<int:sid>/listo")
def marcar_listo(cliente, sid):
    sp = _sprint_o_404(cliente, sid)
    if sp["estado"] in ("generando", "revision", "completado"):
        flash("El sprint ya pasó de la planificación.", "error")
        return _volver(cliente, sid)
    extra = dict(sp.get("extra") or {})
    extra["listo_manual"] = True
    datos.actualizar_sprint(cliente, sid, extra=extra)
    faltantes = [c["id"] for c in sp["campanas"] if c["referencias_listas"] < int(c["referencias_objetivo"] or 1)]
    datos.registrar_evento(cliente, sid, "marcado_listo", "Marcado listo para generar a mano",
                           {"campanas_con_referencias_incompletas": faltantes})
    estado.recalcular(cliente, sid)
    aviso = f" Ojo: {len(faltantes)} campaña(s) no llegan al objetivo de referencias." if faltantes else ""
    flash("Sprint marcado como listo para generar." + aviso, "ok")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/archivar")
def archivar(cliente, sid):
    if not datos.archivar_sprint(cliente, sid, archivado=request.form.get("desarchivar") is None):
        abort(404)
    flash("Sprint archivado.", "ok")
    return _volver(cliente)


@bp.post("/<int:sid>/campanas")
def campana_agregar(cliente, sid):
    _sprint_o_404(cliente, sid)
    try:
        lista = _validar_campanas(cliente, _campanas_desde_form())
        if not lista:
            raise datos.ErrorDatos("Faltan los datos de la campaña.")
        c = lista[0]
        datos.agregar_campana(cliente, sid, c["persona_id"], c["catalogo_id"], c["temporada_id"], c["n_videos"],
                              c["n_imagenes"], referencias_objetivo=c["referencias_objetivo"])
        estado.recalcular(cliente, sid)
        flash("Campaña agregada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/campanas/<int:cid>")
def campana_editar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        campos = {k: request.form.get(k) for k in ("n_videos", "n_imagenes", "referencias_objetivo")
                  if request.form.get(k) is not None}
        datos.actualizar_campana(cliente, cid, **campos)
        estado.recalcular(cliente, sid)
        flash("Campaña guardada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _volver(cliente, sid)


@bp.post("/<int:sid>/campanas/<int:cid>/eliminar")
def campana_eliminar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    datos.eliminar_campana(cliente, cid)
    estado.recalcular(cliente, sid)
    flash("Campaña eliminada.", "ok")
    return _volver(cliente, sid)
```

- [ ] **Step 5: Plantillas del detalle**

`templates/_sprint_macros.html`:

```jinja
{# Macros compartidas por la pestaña Sprints y sus páginas. #}
{% macro anillo(pct, tam=56) -%}
<svg class="anillo" width="{{ tam }}" height="{{ tam }}" viewBox="0 0 36 36" role="img" aria-label="{{ pct }} %">
  <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border)" stroke-width="3"/>
  <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round"
          stroke-dasharray="{{ pct }} 100" transform="rotate(-90 18 18)"/>
  <text x="18" y="21.5" text-anchor="middle" font-size="9" fill="currentColor">{{ pct }}%</text>
</svg>
{%- endmacro %}

{% macro chip_estado(estado) -%}
<span class="tag-estado estado-sprint estado-sprint-{{ estado }}">{{ estado | replace("_", " ") }}</span>
{%- endmacro %}

{% macro barra(pct, texto) -%}
<div class="sprint-barra" title="{{ texto }}"><div class="sprint-barra-fill" style="width: {{ pct }}%"></div><span>{{ texto }}</span></div>
{%- endmacro %}
```

`templates/_sprint_nav.html`:

```jinja
{# Migas y comportamiento de la barra lateral fuera de cliente.html: los
   botones de pestaña no tienen paneles en esta página, así que llevan de
   vuelta al proyecto con el hash de la pestaña. #}
<p class="sprint-migas">
  <a href="{{ url_for('ver_cliente', cliente=cliente, _anchor='sprints') }}">← Sprints</a>
  {% if sprint %} · <a href="{{ url_for('sprints.ver', cliente=cliente, sid=sprint.id) }}">{{ sprint.nombre }}</a>{% endif %}
  {% if campana %} · Campaña {{ campana.orden + 1 }}{% endif %}
</p>
<script>
  document.querySelectorAll('.sidebar-item[data-tab]').forEach(function (b) {
    b.addEventListener('click', function () {
      location.href = {{ url_for('ver_cliente', cliente=cliente) | tojson }} + '#' + b.dataset.tab;
    });
  });
</script>
```

`templates/sprint_detalle.html`:

```jinja
{% extends "base.html" %}
{% from "_sprint_macros.html" import anillo, chip_estado, barra %}
{% block title %}{{ sprint.nombre }} · Sprints{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}

<div class="pagina-cabecera sprint-cabecera">
  <div>
    <h1>{{ sprint.nombre }}</h1>
    <p class="vacio">{{ sprint.inicio }} → {{ sprint.fin }} · {{ chip_estado(sprint.estado) }}
      · {{ sprint.campanas | length }} campaña(s) · {{ sprint.progreso.planeadas }} piezas planeadas
      {% if sprint.destinos %}· destinos: {{ sprint.destinos | join(", ") }}{% endif %}</p>
  </div>
  <div class="sprint-cabecera-derecha">
    {{ anillo(sprint.progreso.porcentaje, 72) }}
    <small class="vacio" id="sprint-progreso-texto">{{ sprint.progreso.texto }}</small>
  </div>
</div>

<div class="acciones sprint-acciones">
  {% if sprint.estado in ("planeando", "referencias") %}
  <form method="post" action="{{ url_for('sprints.marcar_listo', cliente=cliente, sid=sprint.id) }}" class="inline"
        onsubmit="return confirm('¿Marcar el sprint como listo para generar aunque falten referencias?');">
    <button type="submit" class="btn-generar btn-sm">Marcar listo para generar</button>
  </form>
  {% endif %}
  <form method="post" action="{{ url_for('sprints.archivar', cliente=cliente, sid=sprint.id) }}" class="inline"
        onsubmit="return confirm('¿Archivar este sprint? Se puede desarchivar después.');">
    <button type="submit" class="btn-sm btn-peligro">Archivar</button>
  </form>
</div>

<h2>Campañas</h2>
{% if not sprint.campanas %}<p class="vacio">Este sprint no tiene campañas todavía.</p>{% endif %}
<div class="sprint-tablero">
  {% for c in sprint.campanas %}
  <article class="swap-card sprint-campana" id="campana-{{ c.id }}" data-cid="{{ c.id }}">
    <header class="sprint-campana-cab">
      <span class="sprint-punto" style="background: {{ c.persona_color or 'var(--accent)' }}"></span>
      <strong>{{ c.persona_nombre }}</strong>
      <span class="sprint-sep">·</span>
      {% set prod = productos_por_id.get(c.catalogo_id) %}
      {% if prod and prod.representativa_url %}<img class="sprint-mini" src="{{ prod.representativa_url }}" alt="">{% endif %}
      <strong>{{ prod.nombre if prod else c.catalogo_id }}</strong>
      <span class="sprint-sep">·</span>
      <span>{{ c.temporada_nombre }}</span>
      {{ chip_estado(c.estado) }}
    </header>
    <div class="sprint-campana-cuerpo">
      <form method="post" action="{{ url_for('sprints.campana_editar', cliente=cliente, sid=sprint.id, cid=c.id) }}" class="sprint-cantidades">
        <label>Videos <input type="number" name="n_videos" value="{{ c.n_videos }}" min="0" class="mini-input"></label>
        <label>Imágenes <input type="number" name="n_imagenes" value="{{ c.n_imagenes }}" min="0" class="mini-input"></label>
        <label>Ref. objetivo <input type="number" name="referencias_objetivo" value="{{ c.referencias_objetivo }}" min="1" class="mini-input"></label>
        <button type="submit" class="btn-xs">Guardar</button>
      </form>
      <div class="sprint-campana-progreso" data-cid="{{ c.id }}">
        {{ barra(c.progreso.porcentaje, c.progreso.texto) }}
      </div>
      <div class="sprint-campana-acciones">
        <a class="btn-generar btn-sm" href="{{ url_for('sprints.campana_ver', cliente=cliente, sid=sprint.id, cid=c.id) }}">
          {% if c.referencias_total == 0 %}Subir referencias{% else %}Referencias ({{ c.referencias_listas }}/{{ c.referencias_objetivo }}){% endif %}
        </a>
        <form method="post" action="{{ url_for('sprints.campana_eliminar', cliente=cliente, sid=sprint.id, cid=c.id) }}" class="inline"
              onsubmit="return confirm('¿Eliminar esta campaña y sus referencias?');">
          <button type="submit" class="btn-xs btn-peligro">Eliminar</button>
        </form>
      </div>
    </div>
  </article>
  {% endfor %}
</div>

{% if sprint.estado in ("planeando", "referencias", "listo_para_generar") %}
<details class="swap-card" id="agregar-campana">
  <summary class="swap-card-resumen">+ Agregar campaña</summary>
  <form method="post" action="{{ url_for('sprints.campana_agregar', cliente=cliente, sid=sprint.id) }}" class="form-experimento" id="form-agregar-campana"
        data-combinaciones='{{ combinaciones | tojson }}'>
    <div class="fe-opciones">
      <label>Persona
        <select name="persona_id" required>{% for p in personas_sprint %}<option value="{{ p.id }}">{{ p.nombre }}</option>{% endfor %}</select>
      </label>
      <label>Producto
        <select name="catalogo_id" required>{% for p in productos_sprint %}<option value="{{ p.id }}">{{ p.nombre }}</option>{% endfor %}</select>
      </label>
      <label>Temporada
        <select name="temporada_id" required>{% for t in temporadas_sprint %}<option value="{{ t.id }}">{{ t.nombre }} ({{ t.inicio }})</option>{% endfor %}</select>
      </label>
      <label>Videos <input type="number" name="n_videos" value="5" min="0"></label>
      <label>Imágenes <input type="number" name="n_imagenes" value="5" min="0"></label>
      <label>Ref. objetivo <input type="number" name="referencias_objetivo" value="{{ sprint.referencias_objetivo_defecto }}" min="1"></label>
    </div>
    <p class="campo-error" id="aviso-combinacion" hidden>Esa combinación ya existe en este sprint.</p>
    <button type="submit" class="btn-generar btn-sm">Agregar</button>
  </form>
</details>
{% endif %}

<h2>Línea de tiempo</h2>
<ul class="exp-eventos sprint-eventos">
  {% for e in sprint.eventos %}
  <li><small>{{ e.creado_en | replace("T", " ") }}</small> {{ e.mensaje }}{% if e.campana_id %} <small>(campaña #{{ e.campana_id }})</small>{% endif %}</li>
  {% else %}<li class="vacio">Sin eventos todavía.</li>{% endfor %}
</ul>

<script>
  (function () {
    // La combinación repetida se avisa antes de enviar (el servidor la rechaza igual).
    var form = document.getElementById('form-agregar-campana');
    if (form) {
      var usadas = JSON.parse(form.dataset.combinaciones || '[]').map(function (c) { return c.join('|'); });
      function revisar() {
        var clave = [form.persona_id.value, form.catalogo_id.value, form.temporada_id.value].join('|');
        var repetida = usadas.indexOf(clave) >= 0;
        document.getElementById('aviso-combinacion').hidden = !repetida;
        form.querySelector('button[type=submit]').disabled = repetida;
      }
      ['persona_id', 'catalogo_id', 'temporada_id'].forEach(function (n) { form[n].addEventListener('change', revisar); });
      revisar();
    }
    // Progreso agregado: mientras el sprint genera, el tablero se actualiza solo (Parte 2 lo usa de verdad).
    var estado = {{ sprint.estado | tojson }};
    if (estado === 'generando') {
      setInterval(function () {
        fetch({{ url_for('sprints.progreso_json', cliente=cliente, sid=sprint.id) | tojson }}, {headers: {'X-Requested-With': 'fetch'}})
          .then(function (r) { return r.json(); })
          .then(function (j) {
            document.getElementById('sprint-progreso-texto').textContent = j.sprint.texto;
            j.campanas.forEach(function (c) {
              var caja = document.querySelector('.sprint-campana-progreso[data-cid="' + c.id + '"]');
              if (!caja) return;
              caja.querySelector('.sprint-barra-fill').style.width = c.porcentaje + '%';
              caja.querySelector('span').textContent = c.texto;
            });
            if (j.estado !== 'generando') location.reload();
          }).catch(function () {});
      }, 5000);
    }
  })();
</script>
{% endblock %}
```

- [ ] **Step 6: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: PASS. (`campana_ver` aún no existe: el detalle usa `url_for('sprints.campana_ver', ...)`, así que agregar en `sprints/rutas.py` este esqueleto que la Task 12 reemplaza:)

```python
@bp.get("/<int:sid>/campanas/<int:cid>")
def campana_ver(cliente, sid, cid):
    _sprint_o_404(cliente, sid)
    _campana_o_404(cliente, sid, cid)
    return _volver(cliente, sid)   # la Task 12 renderiza campana_referencias.html
```

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile sprints/rutas.py sprints/datos.py
/opt/homebrew/bin/git add sprints/rutas.py sprints/datos.py templates/_sprint_macros.html templates/_sprint_nav.html templates/sprint_detalle.html tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: crear sprint con matriz de campañas, detalle con tablero, progreso JSON, marcar listo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Rutas de referencias y página de referencias de una campaña

**Files:**
- Modify: `sprints/rutas.py` (reemplazar el esqueleto de `campana_ver`, agregar rutas de referencias; `import os` y `from sprints import archivos` arriba)
- Create: `templates/campana_referencias.html`
- Test: `tests/test_rutas_sprints.py` (agregar)

**Interfaces:**
- Consumes: `archivos.guardar_subida`, `datos.agregar_referencia/actualizar_referencia/quitar_referencia/reutilizar_referencia/referencias/referencia`, `tareas_sprints.encolar_analisis/encolar_link/job_id_link`, `progreso.cobertura`, `catalogo_productos.encontrar(cliente, producto_id, categoria)` y `catalogo_productos.CATEGORIAS["producto"]["carpeta"]`.
- Produces: endpoints `sprints.campana_ver` (GET `/<sid>/campanas/<cid>`), `sprints.referencias_subir` (POST `/<sid>/campanas/<cid>/referencias`, archivos `archivos[]` y/o `link`), `sprints.referencias_catalogo` (POST `.../referencias/catalogo`), `sprints.referencias_reutilizar` (POST `.../referencias/reutilizar`, `referencia_id`), `sprints.referencias_estado` (GET `.../referencias/estado`, JSON), `sprints.referencia_editar` (POST `/referencias/<rid>`, JSON o formulario), `sprints.referencia_quitar` (POST `/referencias/<rid>/quitar`), `sprints.referencia_reanalizar` (POST `/referencias/<rid>/reanalizar`).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_rutas_sprints.py`)

```python
import io


def test_referencias_subir_editar_quitar(app, monkeypatch):
    from sprints import archivos, datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    monkeypatch.setattr(archivos, "guardar_subida", lambda c, a: None if a.filename.endswith(".pdf") else {
        "tipo": "imagen", "url": f"https://r2/{a.filename}", "frame_url": None, "ruta_local": "/tmp/x", "titulo": a.filename})
    c = app["c"]
    r = c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias", data={
        "archivos": [(io.BytesIO(b"a"), "a.jpg"), (io.BytesIO(b"b"), "b.pdf")], "intencion": ["paleta"]},
        content_type="multipart/form-data")
    assert r.status_code == 302
    refs = datos.referencias("acme", cid)
    assert len(refs) == 1 and refs[0]["intencion"] == ["paleta"] and refs[0]["estado"] == "borrador"
    assert [e["tipo"] for e in app["encolados"]] == ["sprint_analizar_referencia"]
    rid = refs[0]["id"]
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"descripcion": "quiero esa luz", "intencion": ["iluminacion", "otro"], "intencion_otro": "reflejos"})
    j = r.get_json()
    assert j["ok"] and j["estado"] == "lista" and j["referencias_listas"] == 1 and j["estado_sprint"] == "referencias"
    r = c.post(f"/cliente/acme/sprints/referencias/{rid}", json={"intencion": ["magia"]})
    assert r.status_code == 400 and not r.get_json()["ok"]
    page = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}")
    assert page.status_code == 200 and b"quiero esa luz" in page.data and b"a.jpg" in page.data
    j = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/estado").get_json()
    assert j["listas"] == 1 and j["referencias"][0]["analisis_estado"] == "pendiente"
    c.post(f"/cliente/acme/sprints/referencias/{rid}/reanalizar")
    assert len(app["encolados"]) == 2
    c.post(f"/cliente/acme/sprints/referencias/{rid}/quitar")
    assert datos.referencias("acme", cid) == []
    assert c.get(f"/cliente/acme/sprints/{sid}/campanas/999").status_code == 404


def test_referencias_link_catalogo_y_reutilizar(app, monkeypatch):
    from sprints import datos
    import catalogo_productos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    c = app["c"]
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias", data={"link": "https://www.tiktok.com/@x/video/1"})
    assert app["encolados"][-1]["tipo"] == "sprint_referencia_link" and app["encolados"][-1]["payload"]["campana_id"] == cid
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://r2")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cl, pid_, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "imagenes": ["1.jpg", "2.jpg"]})
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo")
    refs = datos.referencias("acme", cid)
    assert [r["origen"] for r in refs] == ["catalogo", "catalogo"] and refs[0]["estado"] == "lista"
    assert refs[0]["url"] == "https://r2/clientes/acme/productos/espejo_led/1.jpg"
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid}/referencias/catalogo")     # idempotente
    assert len(datos.referencias("acme", cid)) == 2
    tid2 = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    cid2 = datos.agregar_campana("acme", sid, pid, "espejo_led", tid2, 1, 0)
    c.post(f"/cliente/acme/sprints/{sid}/campanas/{cid2}/referencias/reutilizar", data={"referencia_id": refs[0]["id"]})
    assert datos.referencias("acme", cid2)[0]["origen"] == "reutilizada"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: FAIL (rutas de referencias ausentes).

- [ ] **Step 3: Rutas de referencias en `sprints/rutas.py`** (reemplaza el esqueleto de `campana_ver`; agregar `import os` y `from sprints import archivos, calendario, datos, estado, progreso` en los imports)

```python
# -------------------------------------------------------- referencias ---

def _referencia_o_404(cliente, rid):
    r = datos.referencia(cliente, rid)
    if not r:
        abort(404)
    return r


@bp.get("/<int:sid>/campanas/<int:cid>")
def campana_ver(cliente, sid, cid):
    sp = _sprint_o_404(cliente, sid)
    c = _campana_o_404(cliente, sid, cid)
    refs = datos.referencias(cliente, cid)
    c["progreso"] = progreso.progreso_campana(c)
    otras = [{"campana": oc, "referencias": datos.referencias(cliente, oc["id"])}
             for oc in sp["campanas"] if oc["id"] != cid]
    producto = next((p for p in _productos(cliente) if p["id"] == c["catalogo_id"]), None)
    job_link = tareas_sprints.job_id_link(cliente, cid)
    return render_template("campana_referencias.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           sprint=sp, campana=c, referencias=refs, producto=producto, otras_campanas=otras,
                           intenciones_sprint=datos.INTENCIONES_NOMBRE, cobertura=progreso.cobertura(c, refs),
                           trabajo_link={"job_id": job_link} if trabajos.en_curso(job_link) else None)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias")
def referencias_subir(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    link = (request.form.get("link") or "").strip()
    intencion = request.form.getlist("intencion")
    subidas, rechazadas = 0, 0
    for archivo in request.files.getlist("archivos"):
        if not archivo or not archivo.filename:
            continue
        info = archivos.guardar_subida(cliente, archivo)
        if not info:
            rechazadas += 1
            continue
        try:
            rid = datos.agregar_referencia(cliente, cid, info["tipo"], info["url"], frame_url=info["frame_url"],
                                           ruta_local=info["ruta_local"], origen="archivo", titulo=info["titulo"],
                                           intencion=intencion)
        except datos.ErrorDatos as e:
            flash(str(e), "error")
            continue
        tareas_sprints.encolar_analisis(cliente, rid)
        subidas += 1
    if link:
        if tareas_sprints.encolar_link(cliente, cid, link):
            flash("Descargando el link; la referencia aparecerá en unos segundos.", "ok")
        else:
            flash("Ya hay un link descargándose para esta campaña.", "error")
    if subidas:
        flash(f"{subidas} referencia(s) subida(s). Cuéntanos qué reutilizar de cada una.", "ok")
    if rechazadas:
        flash(f"{rechazadas} archivo(s) no son imagen ni video (jpg, png, webp, mp4, mov, webm).", "error")
    estado.recalcular(cliente, sid)
    if _quiere_json():
        return jsonify({"ok": True, "subidas": subidas, "rechazadas": rechazadas})
    return _volver(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/catalogo")
def referencias_catalogo(cliente, sid, cid):
    """Trae las fotos reales del producto de la campaña como referencias
    (origen catalogo), con intención ángulo de producto y descripción
    automática — cuentan como listas desde el primer momento."""
    c = _campana_o_404(cliente, sid, cid)
    producto = catalogo_productos.encontrar(cliente, c["catalogo_id"], "producto")
    if not producto:
        flash("El producto de la campaña ya no está en el catálogo.", "error")
        return _volver(cliente, sid, cid)
    existentes = {r["url"] for r in datos.referencias(cliente, cid)}
    base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    carpeta = catalogo_productos.CATEGORIAS["producto"]["carpeta"]
    nuevas = 0
    for nombre in producto.get("imagenes") or []:
        url = f"{base}/clientes/{cliente}/{carpeta}/{producto['id']}/{nombre}"
        if url in existentes:
            continue
        rid = datos.agregar_referencia(cliente, cid, "imagen", url, origen="catalogo", titulo=nombre,
                                       intencion=["angulo_producto"],
                                       descripcion=f"Foto real del producto {producto['nombre']}, tal como es.")
        tareas_sprints.encolar_analisis(cliente, rid)
        nuevas += 1
    flash(f"{nuevas} foto(s) del producto traídas del catálogo." if nuevas else "Las fotos del producto ya estaban.", "ok")
    estado.recalcular(cliente, sid)
    return _volver(cliente, sid, cid)


@bp.post("/<int:sid>/campanas/<int:cid>/referencias/reutilizar")
def referencias_reutilizar(cliente, sid, cid):
    _campana_o_404(cliente, sid, cid)
    try:
        datos.reutilizar_referencia(cliente, _entero("referencia_id"), cid)
        flash("Referencia reutilizada.", "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    estado.recalcular(cliente, sid)
    return _volver(cliente, sid, cid)


@bp.get("/<int:sid>/campanas/<int:cid>/referencias/estado")
def referencias_estado(cliente, sid, cid):
    c = _campana_o_404(cliente, sid, cid)
    return jsonify({"listas": c["referencias_listas"], "objetivo": c["referencias_objetivo"],
                    "referencias": [{"id": r["id"], "analisis_estado": r["analisis_estado"], "analisis": r["analisis"],
                                     "estado": r["estado"]} for r in datos.referencias(cliente, cid)]})


@bp.post("/referencias/<int:rid>")
def referencia_editar(cliente, rid):
    """Autoguardado de la tarjeta (JSON por fetch) o formulario clásico."""
    r = _referencia_o_404(cliente, rid)
    cuerpo = request.get_json(silent=True)
    es_json = cuerpo is not None or _quiere_json()
    fuente = cuerpo if cuerpo is not None else request.form
    campos = {}
    if "descripcion" in fuente:
        campos["descripcion"] = fuente.get("descripcion")
    if "intencion" in fuente:
        campos["intencion"] = fuente.get("intencion") if cuerpo is not None else request.form.getlist("intencion")
    if "intencion_otro" in fuente:
        campos["intencion_otro"] = fuente.get("intencion_otro")
    if "titulo" in fuente:
        campos["titulo"] = fuente.get("titulo")
    try:
        datos.actualizar_referencia(cliente, rid, **campos)
    except datos.ErrorDatos as e:
        if es_json:
            return jsonify({"ok": False, "error": str(e)}), 400
        flash(str(e), "error")
        return _volver(cliente, r["sprint_id"], r["campana_id"])
    sp = estado.recalcular(cliente, r["sprint_id"])
    c = next((x for x in sp["campanas"] if x["id"] == r["campana_id"]), None)
    if es_json:
        nueva = datos.referencia(cliente, rid)
        return jsonify({"ok": True, "estado": nueva["estado"],
                        "referencias_listas": c["referencias_listas"] if c else 0,
                        "referencias_objetivo": c["referencias_objetivo"] if c else 0,
                        "estado_sprint": sp["estado"]})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/quitar")
def referencia_quitar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    datos.quitar_referencia(cliente, rid)
    estado.recalcular(cliente, r["sprint_id"])
    if _quiere_json():
        return jsonify({"ok": True})
    return _volver(cliente, r["sprint_id"], r["campana_id"])


@bp.post("/referencias/<int:rid>/reanalizar")
def referencia_reanalizar(cliente, rid):
    r = _referencia_o_404(cliente, rid)
    datos.actualizar_referencia(cliente, rid, analisis_estado="pendiente")
    tareas_sprints.encolar_analisis(cliente, rid)
    if _quiere_json():
        return jsonify({"ok": True})
    flash("Analizando de nuevo.", "ok")
    return _volver(cliente, r["sprint_id"], r["campana_id"])
```

- [ ] **Step 4: Plantilla `templates/campana_referencias.html`**

```jinja
{% extends "base.html" %}
{% from "_sprint_macros.html" import chip_estado, barra %}
{% block title %}Referencias · {{ sprint.nombre }}{% endblock %}
{% block content %}
{% include "_sprint_nav.html" %}

<div class="pagina-cabecera sprint-cabecera">
  <div>
    <h1>Referencias de la campaña {{ campana.orden + 1 }}</h1>
    <p class="vacio">
      <span class="sprint-punto" style="background: {{ campana.persona_color or 'var(--accent)' }}"></span> {{ campana.persona_nombre }}
      · {% if producto and producto.representativa_url %}<img class="sprint-mini" src="{{ producto.representativa_url }}" alt="">{% endif %}{{ producto.nombre if producto else campana.catalogo_id }}
      · {{ campana.temporada_nombre }} · {{ campana.n_videos }} videos · {{ campana.n_imagenes }} imágenes · {{ chip_estado(campana.estado) }}
    </p>
  </div>
</div>

<section class="sprint-refs-progreso">
  <strong id="refs-contador">{{ campana.referencias_listas }} / {{ campana.referencias_objetivo }} referencias listas</strong>
  <div id="refs-barra">{{ barra(campana.progreso.porcentaje, campana.progreso.texto) }}</div>
  <p class="vacio">Una referencia cuenta cuando tiene descripción. Dinos qué quieres reutilizar de cada una: eso es lo que Claude analiza y lo que después arma las ideas.</p>
  {% for aviso in cobertura %}<p class="tag-estado sprint-aviso">{{ aviso }}</p>{% endfor %}
</section>

<form method="post" action="{{ url_for('sprints.referencias_subir', cliente=cliente, sid=sprint.id, cid=campana.id) }}"
      enctype="multipart/form-data" class="sprint-zona" id="zona-subida">
  <label class="sprint-zona-drop" for="input-archivos">
    <strong>Arrastra imágenes o videos aquí</strong>, o haz clic para elegir (jpg, png, webp, mp4, mov, webm).
    <input type="file" id="input-archivos" name="archivos" multiple accept="image/*,video/*" hidden>
  </label>
  <div class="fe-opciones">
    <span class="campo-label">Intención inicial (se puede cambiar por referencia):</span>
    {% for clave, nombre in intenciones_sprint.items() if clave != "otro" %}
    <label class="fe-check"><input type="checkbox" name="intencion" value="{{ clave }}"> {{ nombre }}</label>
    {% endfor %}
  </div>
  <div class="fe-opciones">
    <label>O pega un link (TikTok, Instagram, YouTube) <input type="url" name="link" placeholder="https://..." style="width: 22rem;"></label>
    <button type="submit" class="btn-generar btn-sm">Subir</button>
  </div>
  {% if trabajo_link %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_link.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <script>iniciarPolling({{ trabajo_link.job_id | tojson }}, {{ ("trabajo-" ~ trabajo_link.job_id) | tojson }});</script>
  {% endif %}
</form>

<div class="acciones">
  <form method="post" action="{{ url_for('sprints.referencias_catalogo', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
    <button type="submit" class="btn-sm">Traer las fotos del producto</button>
  </form>
  {% if otras_campanas %}
  <details class="inline sprint-reutilizar">
    <summary class="btn-sm">Reutilizar de otra campaña</summary>
    <ul>
      {% for o in otras_campanas %}{% for r in o.referencias %}
      <li>
        <img class="sprint-mini" src="{{ r.frame_url or r.url }}" alt=""> {{ r.titulo or r.url }} <small>({{ o.campana.persona_nombre }} · {{ o.campana.temporada_nombre }})</small>
        <form method="post" action="{{ url_for('sprints.referencias_reutilizar', cliente=cliente, sid=sprint.id, cid=campana.id) }}" class="inline">
          <input type="hidden" name="referencia_id" value="{{ r.id }}"><button type="submit" class="btn-xs">Usar</button>
        </form>
      </li>
      {% endfor %}{% endfor %}
    </ul>
  </details>
  {% endif %}
</div>

<div class="sprint-refs-grid" id="refs-grid"
     data-url-estado="{{ url_for('sprints.referencias_estado', cliente=cliente, sid=sprint.id, cid=campana.id) }}">
  {% for r in referencias %}
  <article class="swap-card sprint-ref" data-rid="{{ r.id }}" data-url="{{ url_for('sprints.referencia_editar', cliente=cliente, rid=r.id) }}">
    <div class="sprint-ref-media">
      {% if r.tipo == "video" %}<video src="{{ r.url }}" poster="{{ r.frame_url }}" controls muted preload="none"></video>
      {% else %}<img src="{{ r.url }}" alt="{{ r.titulo }}">{% endif %}
      <span class="tag-estado sprint-ref-estado">{{ r.estado }}</span>
    </div>
    <div class="sprint-ref-cuerpo">
      <small class="vacio">{{ r.titulo or r.url }} · {{ r.origen }}</small>
      <div class="sprint-chips">
        {% for clave, nombre in intenciones_sprint.items() %}
        <label class="sprint-chip"><input type="checkbox" name="intencion" value="{{ clave }}" {% if clave in (r.intencion or []) %}checked{% endif %}> {{ nombre }}</label>
        {% endfor %}
        <input type="text" name="intencion_otro" value="{{ r.intencion_otro or '' }}" placeholder="otro: ¿qué?" class="mini-input" {% if "otro" not in (r.intencion or []) %}hidden{% endif %}>
      </div>
      <textarea name="descripcion" rows="2" placeholder="¿Qué quieres reutilizar de esta referencia? (obligatorio para que cuente)">{{ r.descripcion or '' }}</textarea>
      <div class="sprint-ref-analisis" data-estado="{{ r.analisis_estado }}">
        {% if r.analisis_estado == "listo" and r.analisis %}
          <p>{{ r.analisis.resumen }}</p>
          <div class="sprint-paleta">{% for c in r.analisis.paleta %}<span title="{{ c }}" style="background: {{ c }}"></span>{% endfor %}</div>
          <details><summary>Ver análisis completo</summary>
            <dl class="sprint-analisis-dl">
              <dt>Composición</dt><dd>{{ r.analisis.composicion }}</dd>
              <dt>Iluminación</dt><dd>{{ r.analisis.iluminacion }}</dd>
              <dt>Movimiento</dt><dd>{{ r.analisis.movimiento }}</dd>
              <dt>Tipografía</dt><dd>{{ r.analisis.tipografia }}</dd>
              <dt>Estética</dt><dd>{{ r.analisis.estetica }}</dd>
              <dt>Storytelling</dt><dd>{{ r.analisis.storytelling }}</dd>
              <dt>Elementos</dt><dd>{{ r.analisis.elementos | join(", ") }}</dd>
            </dl>
          </details>
        {% elif r.analisis_estado == "error" %}
          <p class="tag-error">No se pudo analizar{% if r.analisis and r.analisis.error %}: {{ r.analisis.error }}{% endif %}</p>
        {% else %}
          <p class="vacio sprint-analizando">Analizando con IA…</p>
        {% endif %}
      </div>
      <div class="sprint-ref-acciones">
        <span class="sprint-guardado" hidden>Guardado</span>
        <form method="post" action="{{ url_for('sprints.referencia_reanalizar', cliente=cliente, rid=r.id) }}" class="inline"><button type="submit" class="btn-xs">Reanalizar</button></form>
        <form method="post" action="{{ url_for('sprints.referencia_quitar', cliente=cliente, rid=r.id) }}" class="inline"
              onsubmit="return confirm('¿Quitar esta referencia?');"><button type="submit" class="btn-xs btn-peligro">Quitar</button></form>
      </div>
    </div>
  </article>
  {% else %}
  <p class="vacio" id="refs-vacio">Todavía no hay referencias. Sube las que inspiran esta campaña.</p>
  {% endfor %}
</div>

<script>
  (function () {
    // 1) Arrastrar y soltar: los archivos entran al input y el formulario se envía.
    var zona = document.getElementById('zona-subida'), input = document.getElementById('input-archivos');
    ['dragenter', 'dragover'].forEach(function (ev) { zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.add('sobre'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.remove('sobre'); }); });
    zona.addEventListener('drop', function (e) { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; zona.submit(); } });
    input.addEventListener('change', function () { if (input.files.length) zona.submit(); });

    // 2) Autoguardado por tarjeta (intención, otro, descripción) con espera de 800 ms.
    document.querySelectorAll('.sprint-ref').forEach(function (card) {
      var temporizador = null;
      function guardar() {
        var intencion = Array.prototype.map.call(card.querySelectorAll('input[name=intencion]:checked'), function (i) { return i.value; });
        var otro = card.querySelector('input[name=intencion_otro]');
        otro.hidden = intencion.indexOf('otro') < 0;
        var cuerpo = {intencion: intencion, intencion_otro: otro.value, descripcion: card.querySelector('textarea[name=descripcion]').value};
        fetch(card.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'}, body: JSON.stringify(cuerpo)})
          .then(function (r) { return r.json(); })
          .then(function (j) {
            if (!j.ok) { alert(j.error); return; }
            card.querySelector('.sprint-ref-estado').textContent = j.estado;
            document.getElementById('refs-contador').textContent = j.referencias_listas + ' / ' + j.referencias_objetivo + ' referencias listas';
            var pct = Math.min(100, Math.round(100 * j.referencias_listas / Math.max(1, j.referencias_objetivo)));
            var fill = document.querySelector('#refs-barra .sprint-barra-fill'); if (fill) fill.style.width = pct + '%';
            var ok = card.querySelector('.sprint-guardado'); ok.hidden = false; setTimeout(function () { ok.hidden = true; }, 1500);
          }).catch(function () {});
      }
      function programar() { clearTimeout(temporizador); temporizador = setTimeout(guardar, 800); }
      card.querySelectorAll('input[name=intencion]').forEach(function (i) { i.addEventListener('change', guardar); });
      card.querySelector('input[name=intencion_otro]').addEventListener('input', programar);
      var ta = card.querySelector('textarea[name=descripcion]');
      ta.addEventListener('input', function () { ta.dataset.sucio = '1'; programar(); });
      ta.addEventListener('blur', function () { delete ta.dataset.sucio; });
    });

    // 3) Análisis en curso: se consulta el estado cada 4 s y se pinta sin recargar.
    var grid = document.getElementById('refs-grid');
    function hayPendientes() { return !!grid.querySelector('.sprint-ref-analisis[data-estado="pendiente"]'); }
    function pintar(j) {
      j.referencias.forEach(function (r) {
        var caja = grid.querySelector('.sprint-ref[data-rid="' + r.id + '"] .sprint-ref-analisis');
        if (!caja || caja.dataset.estado === r.analisis_estado) return;
        caja.dataset.estado = r.analisis_estado;
        if (r.analisis_estado === 'listo' && r.analisis) {
          var paleta = (r.analisis.paleta || []).map(function (c) { return '<span title="' + c + '" style="background:' + c + '"></span>'; }).join('');
          caja.innerHTML = '<p></p><div class="sprint-paleta">' + paleta + '</div><p class="vacio">Recarga para ver el análisis completo.</p>';
          caja.querySelector('p').textContent = r.analisis.resumen || '';
        } else if (r.analisis_estado === 'error') {
          caja.innerHTML = '<p class="tag-error">No se pudo analizar.</p>';
        }
      });
    }
    function sondear() {
      if (!hayPendientes()) return;
      fetch(grid.dataset.urlEstado, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) { return r.json(); }).then(pintar).catch(function () {});
      setTimeout(sondear, 4000);
    }
    setTimeout(sondear, 2000);
  })();
</script>
{% endblock %}
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile sprints/rutas.py
/opt/homebrew/bin/git add sprints/rutas.py templates/campana_referencias.html tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: referencias por campaña (subida, link, catálogo, reutilizar, autoguardado, análisis en vivo)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: Pestaña "Sprints" en el proyecto: lista, asistente con matriz, personas, temporadas, estilos

**Files:**
- Create: `templates/_tab_sprints.html`
- Modify: `templates/cliente.html` (sección + panel), `templates/_sidebar.html` (botón), `static/style.css` (bloque `/* Sprints */` al final)
- Test: `tests/test_rutas_sprints.py` (agregar)

**Interfaces:**
- Consumes: todo lo de `contexto(cliente)` (Task 10) y las macros de la Task 11.

- [ ] **Step 1: Escribir la prueba que falla** (agregar a `tests/test_rutas_sprints.py`)

```python
def test_pestana_sprints_se_renderiza(app):
    from sprints import datos
    pid, tid = _base(datos)
    sid, cid = _sprint(datos, pid, tid)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'id="tab-sprints"' in html and 'data-tab="sprints"' in html
    assert "Octubre" in html and "Premium" in html and "Verano" in html and "Nuevo sprint" in html
    assert "campanas_json" in html and "Sugerir personas" in html and "Black Friday" in html
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py::test_pestana_sprints_se_renderiza -q`
Expected: FAIL (`tab-sprints` ausente).

- [ ] **Step 3: `templates/_sidebar.html`** — después del botón de Crear:

```jinja
    <button type="button" class="sidebar-item" data-tab="sprints" role="tab" title="Sprints">
      <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="15" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><path d="M3 10h18M8 3v4M16 3v4M7 14h4M7 17h7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      <span class="sidebar-texto">Sprints</span>
    </button>
```

- [ ] **Step 4: `templates/cliente.html`** — después de la sección `tab-experimentos`:

```jinja
<section id="tab-sprints" class="tab-panel" role="tabpanel">
  {% include "_tab_sprints.html" %}
</section>
```

y en el objeto `paneles` del script:

```javascript
      sprints: document.getElementById('tab-sprints'),
```

- [ ] **Step 5: `templates/_tab_sprints.html`**

```jinja
{% from "_sprint_macros.html" import anillo, chip_estado %}
{# Pestaña Sprints. Contexto de sprints.rutas.contexto(cliente): sprints_lista,
   personas_sprint, temporadas_sprint, presets_temporadas, pais_calendario,
   paises_calendario, productos_sprint, destinos_sprint, estimado_sprint,
   intenciones_sprint, tipos_temporada, trabajo_sugerir, hoy. #}
<div class="panel-cabecera">
  <h2>Sprints</h2>
  <p class="vacio">Un sprint planea un mes de contenido como una matriz persona × producto × temporada. Cada celda es una campaña con sus videos e imágenes; nada se genera sin tu aprobación y sin ver el costo antes.</p>
</div>

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
  <p class="vacio">Todavía no hay sprints. Crea el primero abajo: necesitas al menos una persona, un producto en el catálogo y una temporada.</p>
  {% endfor %}
</div>

<details class="swap-card" id="nuevo-sprint" {% if not sprints_lista %}open{% endif %}>
  <summary class="swap-card-resumen">+ Nuevo sprint</summary>
  {% if not personas_sprint or not productos_sprint or not temporadas_sprint %}
  <p class="tag-estado sprint-aviso">Para armar la matriz hacen falta
    {% if not personas_sprint %}personas{% endif %}{% if not productos_sprint %} · productos en el catálogo{% endif %}{% if not temporadas_sprint %} · temporadas{% endif %}. Créalos más abajo.</p>
  {% else %}
  <form method="post" action="{{ url_for('sprints.crear', cliente=cliente) }}" id="form-sprint"
        data-estimado-video="{{ estimado_sprint.video }}" data-estimado-imagen="{{ estimado_sprint.imagen }}" data-cliente="{{ cliente }}">
    <fieldset class="sprint-paso" data-paso="1">
      <legend>1. Datos del sprint</legend>
      <div class="fe-opciones">
        <label>Nombre <input name="nombre" required maxlength="200" placeholder="Sprint octubre"></label>
        <label>Inicio <input type="date" name="inicio" required></label>
        <label>Fin <input type="date" name="fin" required></label>
        <label>Referencias por campaña <input type="number" name="referencias_objetivo" value="5" min="1" class="mini-input"></label>
      </div>
      <div class="fe-destinos checks-plataformas">
        <span class="campo-label">Destinos (idioma · país)</span>
        {% for d in destinos_sprint %}
        <label class="fe-destino"><input type="checkbox" name="destinos" value="{{ d.codigo }}" {% if d.codigo == "es_CO" %}checked{% endif %}> {{ d.bandera }} {{ d.nombre }} <small>({{ d.idioma }})</small></label>
        {% endfor %}
      </div>
      <label>Notas <textarea name="notas" rows="2"></textarea></label>
      <button type="button" class="btn-generar btn-sm" data-ir="2">Siguiente: la matriz →</button>
    </fieldset>

    <fieldset class="sprint-paso" data-paso="2" hidden>
      <legend>2. Matriz persona × producto</legend>
      <div class="fe-opciones">
        <label>Temporada
          <select id="matriz-temporada">{% for t in temporadas_sprint %}<option value="{{ t.id }}">{{ t.nombre }} ({{ t.inicio }} → {{ t.fin }})</option>{% endfor %}</select>
        </label>
        <small class="vacio">Haz clic en una celda para agregar esa campaña a la temporada elegida y fija sus videos e imágenes. Las celdas grises ya existen en esa temporada.</small>
      </div>
      <div class="sprint-matriz-scroll">
        <table class="sprint-matriz" id="matriz">
          <thead><tr><th></th>{% for p in productos_sprint %}<th>{% if p.representativa_url %}<img class="sprint-mini" src="{{ p.representativa_url }}" alt="">{% endif %}<br>{{ p.nombre }}</th>{% endfor %}</tr></thead>
          <tbody>
            {% for pe in personas_sprint %}
            <tr>
              <th><span class="sprint-punto" style="background: {{ pe.color or 'var(--accent)' }}"></span> {{ pe.nombre }}</th>
              {% for p in productos_sprint %}
              <td class="sprint-celda" data-persona="{{ pe.id }}" data-producto="{{ p.id }}" data-persona-nombre="{{ pe.nombre }}" data-producto-nombre="{{ p.nombre }}">
                <button type="button" class="sprint-celda-btn">+</button>
                <div class="sprint-celda-campos" hidden>
                  <label>V <input type="number" min="0" value="5" class="mini-input celda-videos"></label>
                  <label>I <input type="number" min="0" value="5" class="mini-input celda-imagenes"></label>
                </div>
              </td>
              {% endfor %}
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <p class="sprint-totales" id="matriz-totales">0 campañas · 0 videos · 0 imágenes · costo estimado USD 0,00</p>
      <small class="vacio">Estimado con {{ estimado_sprint.modelo_video }} ({{ estimado_sprint.duracion_s }} s por video) y {{ estimado_sprint.modelo_imagen }}. Se confirma antes de generar; hoy no se gasta nada.</small>
      <div class="acciones">
        <button type="button" class="btn-sm" data-ir="1">← Atrás</button>
        <button type="button" class="btn-generar btn-sm" data-ir="3">Siguiente: resumen →</button>
      </div>
    </fieldset>

    <fieldset class="sprint-paso" data-paso="3" hidden>
      <legend>3. Resumen</legend>
      <ul id="resumen-campanas"></ul>
      <input type="hidden" name="campanas_json" id="campanas-json">
      <div class="acciones">
        <button type="button" class="btn-sm" data-ir="2">← Atrás</button>
        <button type="submit" class="btn-generar btn-sm">Crear sprint</button>
      </div>
    </fieldset>
  </form>
  {% endif %}
</details>

<h3 class="sprint-subtitulo">Personas</h3>
<div class="sprints-personas">
  {% for p in personas_sprint %}
  <details class="swap-card sprint-persona">
    <summary class="swap-card-resumen"><span class="sprint-punto" style="background: {{ p.color or 'var(--accent)' }}"></span> <strong>{{ p.nombre }}</strong>
      <small class="vacio">{{ p.resumen }}{% if p.edad_rango %} · {{ p.edad_rango }}{% endif %}{% if p.origen == "sugerida_ia" %} · sugerida por IA{% endif %}</small></summary>
    <form method="post" action="{{ url_for('sprints.persona_editar', cliente=cliente, pid=p.id) }}" class="form-experimento">
      <div class="fe-opciones">
        <label>Nombre <input name="nombre" value="{{ p.nombre }}" required></label>
        <label>Resumen <input name="resumen" value="{{ p.resumen or '' }}" maxlength="200"></label>
        <label>Edad <input name="edad_rango" value="{{ p.edad_rango or '' }}" placeholder="30-45" class="mini-input"></label>
        <label>Color <input type="color" name="color" value="{{ p.color or '#4d8dff' }}"></label>
      </div>
      <label>Descripción (quién es, qué le importa, qué le duele) <textarea name="descripcion" rows="3">{{ p.descripcion or '' }}</textarea></label>
      <label>Tono (cómo hablarle) <input name="tono" value="{{ p.tono or '' }}"></label>
      <label>Señales visuales (separadas por coma) <input name="senales_visuales" value="{{ (p.senales_visuales or []) | join(', ') }}"></label>
      <label>Palabras clave <input name="palabras_clave" value="{{ (p.palabras_clave or []) | join(', ') }}"></label>
      <div class="acciones">
        <button type="submit" class="btn-generar btn-sm">Guardar</button>
        <button type="submit" class="btn-sm btn-peligro" formaction="{{ url_for('sprints.persona_archivar', cliente=cliente, pid=p.id) }}">Archivar</button>
      </div>
    </form>
  </details>
  {% else %}<p class="vacio">Sin personas todavía.</p>{% endfor %}
</div>
<div class="acciones">
  <details class="swap-card inline">
    <summary class="swap-card-resumen">+ Nueva persona</summary>
    <form method="post" action="{{ url_for('sprints.persona_crear', cliente=cliente) }}" class="form-experimento">
      <div class="fe-opciones">
        <label>Nombre <input name="nombre" required placeholder="Cliente Premium"></label>
        <label>Resumen <input name="resumen" maxlength="200" placeholder="Busca calidad y diseño"></label>
        <label>Edad <input name="edad_rango" placeholder="30-45" class="mini-input"></label>
        <label>Color <input type="color" name="color" value="#4d8dff"></label>
      </div>
      <label>Descripción <textarea name="descripcion" rows="3"></textarea></label>
      <label>Tono <input name="tono" placeholder="cercano y experto"></label>
      <label>Señales visuales (coma) <input name="senales_visuales" placeholder="cocina moderna, luz natural"></label>
      <label>Palabras clave (coma) <input name="palabras_clave"></label>
      <button type="submit" class="btn-generar btn-sm">Crear persona</button>
    </form>
  </details>
  <form method="post" action="{{ url_for('sprints.personas_sugerir', cliente=cliente) }}" class="inline">
    <input type="hidden" name="cuantas" value="3">
    <button type="submit" class="btn-sm" {% if trabajo_sugerir %}disabled{% endif %}>Sugerir personas con IA</button>
  </form>
  {% if trabajo_sugerir %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_sugerir.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>
  <script>iniciarPolling({{ trabajo_sugerir.job_id | tojson }}, {{ ("trabajo-" ~ trabajo_sugerir.job_id) | tojson }});</script>
  {% endif %}
</div>

<h3 class="sprint-subtitulo">Temporadas</h3>
<div class="sprints-temporadas">
  {% for t in temporadas_sprint %}
  <details class="swap-card sprint-temporada">
    <summary class="swap-card-resumen"><strong>{{ t.nombre }}</strong> <small class="vacio">{{ t.inicio }} → {{ t.fin }} · {{ t.tipo }}</small>
      <span class="sprint-paleta">{% for c in (t.mood_visual or {}).get("paleta", []) %}<span style="background: {{ c }}" title="{{ c }}"></span>{% endfor %}</span></summary>
    <form method="post" action="{{ url_for('sprints.temporada_editar', cliente=cliente, tid=t.id) }}" class="form-experimento">
      <div class="fe-opciones">
        <label>Nombre <input name="nombre" value="{{ t.nombre }}" required></label>
        <label>Inicio <input type="date" name="inicio" value="{{ t.inicio }}"></label>
        <label>Fin <input type="date" name="fin" value="{{ t.fin }}"></label>
        <label>Tipo <select name="tipo">{% for tt in tipos_temporada %}<option value="{{ tt }}" {% if tt == t.tipo %}selected{% endif %}>{{ tt }}</option>{% endfor %}</select></label>
      </div>
      <label>Contexto <textarea name="contexto" rows="2">{{ t.contexto or '' }}</textarea></label>
      <div class="fe-opciones">
        <label>Paleta (hex, coma) <input name="paleta" value="{{ (t.mood_visual or {}).get('paleta', []) | join(', ') }}"></label>
        <label>Luz <input name="luz" value="{{ (t.mood_visual or {}).get('luz', '') }}"></label>
        <label>Elementos (coma) <input name="elementos" value="{{ (t.mood_visual or {}).get('elementos', []) | join(', ') }}"></label>
      </div>
      <div class="acciones">
        <button type="submit" class="btn-generar btn-sm">Guardar</button>
        <button type="submit" class="btn-sm btn-peligro" formaction="{{ url_for('sprints.temporada_archivar', cliente=cliente, tid=t.id) }}">Archivar</button>
      </div>
    </form>
  </details>
  {% else %}<p class="vacio">Sin temporadas todavía. Adopta una del calendario o crea la tuya.</p>{% endfor %}
</div>
<div class="sprint-calendario">
  <form method="post" action="{{ url_for('sprints.calendario_pais', cliente=cliente) }}" class="inline">
    <label>Calendario comercial de
      <select name="pais" onchange="this.form.submit()">{% for p in paises_calendario %}<option value="{{ p }}" {% if p == pais_calendario %}selected{% endif %}>{{ p }}</option>{% endfor %}</select>
    </label>
  </form>
  <div class="sprint-presets">
    {% for pr in presets_temporadas %}
    <form method="post" action="{{ url_for('sprints.temporada_adoptar', cliente=cliente) }}" class="inline">
      <input type="hidden" name="clave" value="{{ pr.clave }}">
      <button type="submit" class="btn-xs" title="{{ pr.inicio }} → {{ pr.fin }}">+ {{ pr.nombre }}</button>
    </form>
    {% endfor %}
  </div>
  <details class="swap-card inline">
    <summary class="swap-card-resumen">+ Nueva temporada propia</summary>
    <form method="post" action="{{ url_for('sprints.temporada_crear', cliente=cliente) }}" class="form-experimento">
      <div class="fe-opciones">
        <label>Nombre <input name="nombre" required placeholder="Lanzamiento línea baño"></label>
        <label>Inicio <input type="date" name="inicio" required></label>
        <label>Fin <input type="date" name="fin" required></label>
        <label>Tipo <select name="tipo">{% for tt in tipos_temporada %}<option value="{{ tt }}" {% if tt == "propia" %}selected{% endif %}>{{ tt }}</option>{% endfor %}</select></label>
      </div>
      <label>Contexto (qué pasa, qué se vende, qué emoción) <textarea name="contexto" rows="2"></textarea></label>
      <div class="fe-opciones">
        <label>Paleta (hex, coma) <input name="paleta" placeholder="#1B2A41, #F2C14E"></label>
        <label>Luz <input name="luz" placeholder="cálida, de tarde"></label>
        <label>Elementos (coma) <input name="elementos"></label>
      </div>
      <button type="submit" class="btn-generar btn-sm">Crear temporada</button>
    </form>
  </details>
</div>

<script>
  (function () {
    var form = document.getElementById('form-sprint');
    if (!form) return;
    var KEY = 'sprint-asistente-' + form.dataset.cliente;
    var costoV = parseFloat(form.dataset.estimadoVideo || '0'), costoI = parseFloat(form.dataset.estimadoImagen || '0');
    var campanas = {};   // "persona|producto|temporada" -> {persona_id, catalogo_id, temporada_id, n_videos, n_imagenes, nombres}
    var selTemporada = document.getElementById('matriz-temporada');

    // Fechas por defecto: el mes siguiente completo.
    var hoy = new Date(), ini = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 1), fin = new Date(hoy.getFullYear(), hoy.getMonth() + 2, 0);
    function iso(d) { return d.toISOString().slice(0, 10); }
    if (!form.inicio.value) form.inicio.value = iso(ini);
    if (!form.fin.value) form.fin.value = iso(fin);
    if (!form.nombre.value) form.nombre.value = 'Sprint ' + ini.toLocaleDateString('es', {month: 'long', year: 'numeric'});

    // Estado guardado (por si se crea una persona o temporada a mitad de camino y la página recarga).
    try { var g = JSON.parse(sessionStorage.getItem(KEY) || 'null'); if (g) { campanas = g.campanas || {}; if (g.nombre) form.nombre.value = g.nombre; if (g.inicio) form.inicio.value = g.inicio; if (g.fin) form.fin.value = g.fin; } } catch (e) {}
    function guardarEstado() { try { sessionStorage.setItem(KEY, JSON.stringify({campanas: campanas, nombre: form.nombre.value, inicio: form.inicio.value, fin: form.fin.value})); } catch (e) {} }

    function clave(td) { return td.dataset.persona + '|' + td.dataset.producto + '|' + selTemporada.value; }
    function pintar() {
      var tNombre = selTemporada.options[selTemporada.selectedIndex].text;
      form.querySelectorAll('.sprint-celda').forEach(function (td) {
        var c = campanas[clave(td)];
        var enOtra = Object.keys(campanas).some(function (k) { return k.indexOf(td.dataset.persona + '|' + td.dataset.producto + '|') === 0 && k !== clave(td); });
        td.classList.toggle('activa', !!c);
        td.classList.toggle('en-otra', !c && enOtra);
        td.querySelector('.sprint-celda-campos').hidden = !c;
        td.querySelector('.sprint-celda-btn').textContent = c ? '✓' : '+';
        if (c) { td.querySelector('.celda-videos').value = c.n_videos; td.querySelector('.celda-imagenes').value = c.n_imagenes; }
      });
      var n = 0, v = 0, i = 0;
      Object.keys(campanas).forEach(function (k) { n++; v += +campanas[k].n_videos; i += +campanas[k].n_imagenes; });
      document.getElementById('matriz-totales').textContent = n + ' campañas · ' + v + ' videos · ' + i + ' imágenes · costo estimado USD ' + (v * costoV + i * costoI).toFixed(2).replace('.', ',');
      var ul = document.getElementById('resumen-campanas'); ul.innerHTML = '';
      Object.keys(campanas).forEach(function (k) {
        var c = campanas[k], li = document.createElement('li');
        li.textContent = c.persona_nombre + ' · ' + c.producto_nombre + ' · ' + c.temporada_nombre + ': ' + c.n_videos + ' videos, ' + c.n_imagenes + ' imágenes';
        ul.appendChild(li);
      });
      document.getElementById('campanas-json').value = JSON.stringify(Object.keys(campanas).map(function (k) {
        var c = campanas[k]; return {persona_id: c.persona_id, catalogo_id: c.catalogo_id, temporada_id: c.temporada_id, n_videos: c.n_videos, n_imagenes: c.n_imagenes};
      }));
      guardarEstado();
    }
    form.querySelectorAll('.sprint-celda').forEach(function (td) {
      td.querySelector('.sprint-celda-btn').addEventListener('click', function () {
        var k = clave(td);
        if (campanas[k]) { delete campanas[k]; }
        else {
          campanas[k] = {persona_id: +td.dataset.persona, catalogo_id: td.dataset.producto, temporada_id: +selTemporada.value,
                         n_videos: 5, n_imagenes: 5, persona_nombre: td.dataset.personaNombre, producto_nombre: td.dataset.productoNombre,
                         temporada_nombre: selTemporada.options[selTemporada.selectedIndex].text};
        }
        pintar();
      });
      ['.celda-videos', '.celda-imagenes'].forEach(function (sel, idx) {
        td.querySelector(sel).addEventListener('input', function (e) {
          var c = campanas[clave(td)]; if (!c) return;
          c[idx === 0 ? 'n_videos' : 'n_imagenes'] = Math.max(0, parseInt(e.target.value || '0', 10)); pintar();
        });
      });
    });
    selTemporada.addEventListener('change', pintar);
    ['nombre', 'inicio', 'fin'].forEach(function (n) { form[n].addEventListener('input', guardarEstado); });
    form.querySelectorAll('[data-ir]').forEach(function (b) {
      b.addEventListener('click', function () {
        var destino = b.dataset.ir;
        if (destino === '3' && !Object.keys(campanas).length) { alert('Agrega al menos una campaña en la matriz.'); return; }
        form.querySelectorAll('.sprint-paso').forEach(function (p) { p.hidden = p.dataset.paso !== destino; });
      });
    });
    form.addEventListener('submit', function () { try { sessionStorage.removeItem(KEY); } catch (e) {} });
    pintar();
  })();
</script>
```

- [ ] **Step 6: Estilos** — agregar al final de `static/style.css`:

```css
/* Sprints */
.sprints-lista { display: grid; gap: .6rem; margin-bottom: 1rem; }
.sprint-card { display: flex; gap: 1rem; align-items: center; padding: .8rem 1rem; text-decoration: none; color: inherit; }
.sprint-card:hover { background: var(--panel-hover); }
.anillo text { font-family: var(--font-body); font-weight: 700; }
.estado-sprint { text-transform: capitalize; }
.estado-sprint-planeando, .estado-sprint-planeada { border-color: var(--muted-2); }
.estado-sprint-referencias { border-color: var(--accent); }
.estado-sprint-listo_para_generar, .estado-sprint-ideas_aprobadas { border-color: var(--ok); }
.estado-sprint-generando { border-color: var(--warn); }
.estado-sprint-revision { border-color: var(--accent-2); }
.estado-sprint-completado, .estado-sprint-completada { border-color: var(--ok); color: var(--ok); }
.sprint-paso { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: .8rem 1rem; margin: .6rem 0; }
.sprint-paso legend { font-weight: 700; padding: 0 .4rem; }
.sprint-matriz-scroll { overflow-x: auto; }
.sprint-matriz { border-collapse: collapse; min-width: 100%; }
.sprint-matriz th, .sprint-matriz td { border: 1px solid var(--border); padding: .4rem .5rem; text-align: center; vertical-align: middle; }
.sprint-matriz tbody th { text-align: left; white-space: nowrap; }
.sprint-celda-btn { width: 2rem; height: 2rem; border-radius: 50%; border: 1px dashed var(--muted-2); background: transparent; color: var(--text); cursor: pointer; }
.sprint-celda.activa { background: rgba(77, 141, 255, .12); }
.sprint-celda.activa .sprint-celda-btn { border-style: solid; border-color: var(--accent); background: var(--accent); color: #fff; }
.sprint-celda.en-otra { background: rgba(255, 255, 255, .03); color: var(--muted); }
.sprint-celda-campos { display: flex; gap: .4rem; justify-content: center; margin-top: .3rem; }
.sprint-celda-campos .mini-input { width: 3.2rem; }
.sprint-totales { font-weight: 700; margin: .6rem 0 .2rem; }
.sprint-subtitulo { margin-top: 1.6rem; }
.sprint-punto { display: inline-block; width: .7rem; height: .7rem; border-radius: 50%; vertical-align: middle; margin-right: .3rem; }
.sprint-mini { width: 28px; height: 28px; object-fit: cover; border-radius: 6px; vertical-align: middle; }
.sprint-paleta { display: inline-flex; gap: .2rem; vertical-align: middle; margin-left: .4rem; }
.sprint-paleta span { width: 14px; height: 14px; border-radius: 3px; border: 1px solid var(--border-soft); display: inline-block; }
.sprint-presets { display: flex; flex-wrap: wrap; gap: .4rem; margin: .5rem 0; }
.sprint-calendario { margin: .6rem 0 1rem; }
.sprint-aviso { display: block; margin: .3rem 0; border-color: var(--warn); }
.sprint-cabecera { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.sprint-cabecera-derecha { text-align: center; }
.sprint-migas { color: var(--muted); font-size: .85rem; margin: 0 0 .6rem; }
.sprint-tablero { display: grid; gap: .6rem; }
.sprint-campana { padding: .7rem 1rem; }
.sprint-campana-cab { display: flex; align-items: center; gap: .4rem; flex-wrap: wrap; }
.sprint-sep { color: var(--muted-2); }
.sprint-campana-cuerpo { display: grid; grid-template-columns: auto 1fr auto; gap: 1rem; align-items: center; margin-top: .5rem; }
.sprint-cantidades { display: flex; gap: .5rem; align-items: end; }
.sprint-cantidades .mini-input { width: 4rem; }
.sprint-barra { position: relative; height: 1.3rem; background: var(--panel-2); border-radius: 999px; overflow: hidden; }
.sprint-barra-fill { height: 100%; background: var(--accent-grad); transition: width .4s ease; }
.sprint-barra span { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: .75rem; }
.sprint-campana-acciones { display: flex; gap: .4rem; align-items: center; }
.sprint-eventos li small { color: var(--muted); margin-right: .4rem; }
.sprint-refs-progreso { margin: .6rem 0 1rem; }
.sprint-zona { border: 2px dashed var(--border); border-radius: var(--radius); padding: 1rem; margin-bottom: .8rem; }
.sprint-zona.sobre { border-color: var(--accent); background: rgba(77, 141, 255, .06); }
.sprint-zona-drop { display: block; padding: 1.4rem; text-align: center; cursor: pointer; }
.sprint-refs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: .8rem; margin-top: 1rem; }
.sprint-ref { padding: 0; overflow: hidden; }
.sprint-ref-media { position: relative; background: #000; }
.sprint-ref-media img, .sprint-ref-media video { width: 100%; max-height: 260px; object-fit: contain; display: block; }
.sprint-ref-estado { position: absolute; top: .5rem; left: .5rem; }
.sprint-ref-cuerpo { padding: .7rem .9rem .9rem; display: grid; gap: .5rem; }
.sprint-chips { display: flex; flex-wrap: wrap; gap: .3rem; }
.sprint-chip { font-size: .75rem; border: 1px solid var(--border); border-radius: 999px; padding: .15rem .5rem; cursor: pointer; }
.sprint-chip:has(input:checked) { border-color: var(--accent); background: rgba(77, 141, 255, .15); }
.sprint-chip input { display: none; }
.sprint-ref-analisis p { margin: 0 0 .3rem; font-size: .85rem; }
.sprint-analisis-dl { font-size: .8rem; display: grid; grid-template-columns: auto 1fr; gap: .2rem .6rem; }
.sprint-analisis-dl dt { color: var(--muted); }
.sprint-analisis-dl dd { margin: 0; }
.sprint-analizando::before { content: ""; display: inline-block; width: .7rem; height: .7rem; border: 2px solid var(--accent); border-right-color: transparent; border-radius: 50%; margin-right: .4rem; animation: girar 1s linear infinite; }
@keyframes girar { to { transform: rotate(360deg); } }
.sprint-ref-acciones { display: flex; gap: .4rem; align-items: center; justify-content: flex-end; }
.sprint-guardado { color: var(--ok); font-size: .75rem; }
.sprint-reutilizar ul { list-style: none; padding: 0; margin: .4rem 0 0; display: grid; gap: .3rem; }
```

- [ ] **Step 7: Correr y ver que pasa; revisar en el navegador**

Run: `venv/bin/python -m pytest tests/test_rutas_sprints.py -q`
Expected: PASS.

Luego `venv/bin/python dashboard.py`, abrir `http://127.0.0.1:5050/cliente/<proyecto>#sprints` y comprobar a mano: la pestaña aparece en la barra lateral, el asistente arma la matriz y muestra el costo en vivo, se crea un sprint, el detalle muestra el tablero, y en una campaña se sube una imagen, se escribe la descripción y el estado pasa a `lista` sin recargar.

- [ ] **Step 8: Commit**

```bash
/opt/homebrew/bin/git add templates/_tab_sprints.html templates/cliente.html templates/_sidebar.html static/style.css tests/test_rutas_sprints.py
/opt/homebrew/bin/git commit -m "Sprints: pestaña con lista, asistente con matriz persona × producto, personas, temporadas y calendario

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Documentación y verificación final

**Files:**
- Modify: `CLAUDE.md` (sección nueva después de "Prompt generation")
- Test: suite completa

- [ ] **Step 1: Sección en `CLAUDE.md`**

```markdown
**Sprints de contenido** (`sprints/` + `tareas/sprints.py`, spec
`docs/superpowers/specs/2026-09-16-sprints-design.md`): a monthly production plan
as a matrix persona × producto × temporada. Tables `persona`, `temporada`,
`sprint`, `campana` (UNIQUE `uq_campana_combinacion` on sprint + persona +
catalogo_id + temporada), `referencia` (intención tags + descripción; a reference
without descripción is `borrador` and does not count toward progress),
`campana_pieza` (Parte 2) and `sprint_evento`. `sprints/datos.py` is the only
writer; `sprints/estado.py::recalcular` re-derives campaign/sprint states after
every event (states are stored but never trusted blindly); `sprints/progreso.py`
is pure. Routes live in the Blueprint `sprints/rutas.py`
(`/cliente/<cliente>/sprints/...`), registered from `dashboard.py`, which also
adds `sprints_rutas.contexto(cliente)` to the project page. Uploading a
reference enqueues `sprint_analizar_referencia` (Claude vision, cents); "Sugerir
personas" enqueues `sprint_sugerir_personas`; a pasted link goes through
`sprint_referencia_link` (yt-dlp via `referencias_link.descargar`). Nothing in
Parte 1 generates images or videos.
```

- [ ] **Step 2: Suite completa y compilación**

Run: `venv/bin/python -m pytest -q`
Expected: todo verde (las pruebas `slow` incluidas).

Run: `for f in db.py proyectos.py dashboard.py sprints/*.py tareas/sprints.py tareas/__init__.py migrations/versions/0006_sprints.py; do python3 -m py_compile "$f" || echo "FALLA $f"; done`
Expected: sin salida.

- [ ] **Step 3: Commit**

```bash
/opt/homebrew/bin/git add CLAUDE.md
/opt/homebrew/bin/git commit -m "Docs: sprints de contenido (Parte 1) en CLAUDE.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Autorrevisión del plan contra el spec (Parte 1)

- §1.1 modelo de datos → Task 1 (tablas y migración, incluida `campana_pieza`), Tasks 2, 4, 5 (CRUD).
- §1.2 validaciones → Tasks 2, 4, 5 (fechas, cantidades, unicidad en base y mensaje "ya existe en la campaña N", pertenencia al cliente) y Task 11 (`_validar_campanas`: producto en catálogo, repetidas en el mismo envío).
- §1.3 estados y recálculo → Task 6 (`estado.py`), invocado en cada ruta que cambia datos (Tasks 11 y 12); "Marcar listo" con aviso → Task 11.
- §1.4 progreso ponderado y cobertura → Task 6; se muestra en Tasks 11, 12 y 13.
- §1.5 análisis de referencias con Claude → Task 7 (módulo y tarea), regenerar desde la tarjeta → Task 12.
- §1.6 experiencia: pestaña, lista, asistente con matriz y costo en vivo, personas con sugerencia por IA, temporadas con calendario por país, detalle con tablero y línea de tiempo, referencias con arrastrar y soltar, chips de intención, autoguardado, análisis en vivo, traer del catálogo y reutilizar → Tasks 3, 8, 10, 11, 12, 13.
- §1.7 módulos y pruebas → cada tarea trae sus pruebas; suite completa en Task 14.
- Fuera de esta parte (a propósito): ideas, lotes, QA, revisión (Parte 2); plantillas y final edition de imágenes (Parte 3).
