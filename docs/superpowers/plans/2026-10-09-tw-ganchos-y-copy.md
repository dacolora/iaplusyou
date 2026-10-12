# Triple Whale: tres ganchos nuevos y copy para Meta (etapa 2), plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El análisis «Cómo mejorarlo» trae tres ganchos nuevos (los primeros 3 s) y un copy nuevo para Meta, y con un
clic y el precio a la vista cada gancho se vuelve un anuncio listo: un clip de 3 s de Kling que arranca en un fotograma
del original, pegado al original desde el segundo 3 con su audio entero y el texto del gancho, producido gratis en el
destino del anuncio y marcado con su código `CV<id>`.

**Architecture:** `mejorar.parsear` lee dos claves más sin volverse más exigente. La tabla `tw_gancho` (migración 0035,
único escritor `triple_whale/datos.py`) guarda una fila por variante con su estado. La ruta `ganchos_probar` no cobra:
revisa, compara el precio visto, pide saldo, crea la tanda y encola `tw_ganchos_preparar` (gratis), que baja el
original y lanza una pieza de Crear por gancho (cada una se cobra en el cierre de Crear). La periódica
`tw_ganchos_vigilar` mueve cada variante; `tw_gancho_armar` arma la edición con `triple_whale/ganchos.py` (puro) y la
produce con la misma cola del editor (`rutas_editor.encolar_producciones`, extraída sin cambiar la ruta).

**Tech Stack:** Python 3.14, Flask + Jinja + Flask-Babel, SQLAlchemy Core sobre SQLite, Alembic, ffmpeg/ffprobe,
WaveSpeed (Kling O3 Pro imagen a video, vía `flowplus_lanzar`), el editor (`final_edition/`), pytest, Node solo para el
`node --check` del hook.

**Spec:** `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md` (léelo entero antes de empezar; este plan cita
sus secciones como «spec §N»). Las decisiones donde el código contradijo al spec están en «Rulings» al final de este
encabezado y se escriben de vuelta en el spec en la Task 7.

## Global Constraints

- Trabaja SOLO en el worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/tw-ganchos` (rama
  `tw-ganchos`). Nunca `cd` al checkout principal (está viejo). Nada de `git stash`, nada de `git add -A`: cada commit
  nombra sus archivos.
- Pruebas: `venv/bin/python3 -m pytest -q <archivos>`; al final de cada tarea, además, la suite de Triple Whale:
  `venv/bin/python3 -m pytest -q tests/test_triple_whale*.py tests/test_tw_*.py tests/test_rutas_triple_whale.py`.
- Regla 1 (plata, spec §6): lo único pagado son los clips (Kling O3 Pro, imagen a video, 3 s, sin sonido:
  `gastos.estimar("video", modelo="kling_o3_pro", duracion=3, con_sonido=False)["usd"] == 0.336` cada uno). El precio
  va a la vista antes (`gastos.estimar_ganchos_tw(n)`, `|precio|usd`, `data-confirmar`); vuelve como `precio_visto`
  (es PRECIO) y la ruta lo pasa a costo UNA vez con `gastos.costo_de_precio` y lo compara ±0,005 (409 si no); después
  `libro.exigir(cliente, total)` ANTES de crear nada; cada clip reserva lo suyo al encolarse (`flowplus_lanzar.lanzar`)
  y lo cobra el cierre de Crear. Preparar, vigilar y armar no llaman a ningún proveedor que cobre. Nada avanza solo de
  un paso pagado a otro pagado: armar y producir son ffmpeg.
- Doble clic (spec §6): job_id determinista, `datos.TandaViva` y UNIQUE (`analisis_id`, `tanda`, `n`).
- Regla 3 (textos): todo texto visible pasa por el catálogo: `{{ _('…') }}` / `ngettext` en plantillas, `gettext` /
  `ngettext` de `flask_babel` en Python, `idiomas.N_` en constantes (y `gettext(variable)` con la constante en una
  variable, nunca `gettext(MODULO.CONSTANTE)`). Dentro de `_()` con argumentos un `%` literal es `%%`. Al terminar cada
  tarea que agrega textos: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir cada entrada que liste
  `venv/bin/python3 catalogo_i18n.py pendientes` en `translations/en/LC_MESSAGES/messages.po` con
  `docs/i18n/glosario.md` (Gancho = Hook, Crear = Create, Final = Final cut), quitar todo `#, fuzzy` traduciendo bien
  esa entrada, y `venv/bin/python3 catalogo_i18n.py compilar`. Comprobar con
  `venv/bin/python3 -m pytest -q tests/test_i18n_catalogo.py tests/test_i18n_plantillas.py tests/test_i18n_mensajes.py`.
- Idiomas (spec §3.1 y §8): `accion`, `error` y el nombre de la edición se guardan en el idioma del proyecto (el
  worker ya lo pone con `idiomas.de_tarea`; el vigilante, que es periódico, lo pone a mano por proyecto; una ruta que
  guarda envuelve con `idiomas.en_idioma(idiomas.de_proyecto(cliente))`). El texto del gancho y el copy nuevo van en el
  idioma del anuncio; los prompts a Kling, en inglés.
- Regla 5: `tw_gancho` solo la escribe `triple_whale/datos.py`; toda lectura-modificación-escritura toma el candado
  ANTES de leer (`BEGIN IMMEDIATE`, como `referentes/datos.guardar_referente`); el estado solo cambia con `mover` (CAS).
- Regla 6 (spec §7): el POST pasa por `_mismo_origen` del blueprint (ya existe, `triple_whale/rutas.py:53`); `aid` con
  `<int(max={AID_MAX}):aid>`; toda fila se busca por `(cliente, id)`; el video ajeno solo se baja con
  `conectores.url.descargar_archivo` desde `mejorar._url_voz(foto)` y ffmpeg solo lo abre si `mejorar.es_mp4`; cada
  clave de R2 empieza por `clientes/<cliente>/`; nada de rutas ni tokens en un error guardado.
- Regla 8 (pantallas): `<video>` de listas con `preload="none" data-precarga`; barras con `data-poll-job`, un `id` único
  y `data-poll-al-terminar="evento"`, nunca `<script>` en el fragmento; nada de una consulta por variante; en el celular
  nada empuja la página de lado; rejillas con `minmax(min(100%, X), 1fr)`.
- Estilos: se editan en `static/estilos/pantallas/triple-whale.css` y luego `venv/bin/python3 estilos.py construir`
  (genera `static/style.css`; `tests/test_estilos_sistema.py` falla si se edita la hoja a mano). Solo tokens de
  `tokens.css` (`--border`, `--panel`, `--panel-2`, `--radius-sm`, `--fondo-video`…), ningún color literal.
- Los hooks del repo revisan cada edición: un `.py` compila, una plantilla se lee con Jinja y tiene sus `<div>` en
  pareja, el JS pasa `node --check`, el catálogo no queda con `fuzzy`. Si un hook frena, se arregla la causa.
- Commits: uno por tarea, mensaje en español, terminado en la línea
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Antes de commitear:
  `ls $(git rev-parse --git-dir)/MERGE_HEAD $(git rev-parse --git-dir)/REBASE_HEAD 2>/dev/null` no debe mostrar nada.
- Nombres compartidos entre tareas (no los cambies): ver «Interfaces» de cada tarea.

## Rulings (donde el spec era ambiguo o el código lo contradijo)

1. **El audio del original va en su propia pista `p_original` (rol `sonido`), no en `p_sonido`** (spec §4.6.2). El
   editor rehace `p_sonido` como espejo de la principal en cada operación (`static/editor/operaciones.js:413-417`
   llama a `sincronizarSonido`, líneas 232-241): la primera vez que alguien cambiara el texto en el editor, los 3
   primeros segundos quedarían mudos. El compilador no trata `p_sonido` aparte (`final_edition/documento.py:104`).
2. **`encolar_producciones(cliente, edicion_id, ed, version, destinos)` recibe la versión ya congelada**: `versionar`
   se queda en quien llama (la ruta conserva su CAS con `version_n` y su 409, `final_edition/rutas_editor.py:222-225`;
   la tarea congela por su cuenta). La función hace los pasos 3 y 4 de spec §4.6.4.
3. **El original se busca por el hash guardado en la sesión del clip** (`tw_gancho.original_hash`, junto a `gancho_id`
   y `analisis_id`): la tabla no tiene dónde guardarlo y `materiales.buscar_hash` (`materiales.py:49`) lo necesita.
4. **El vigilante cierra una fila `preparando`/`armando` solo si su trabajo no está vivo Y lleva `GRACIA_S` = 120 s
   sin cambiar**: la ruta guarda el `job_id` después de `crear_tanda`, así que una fila recién nacida tiene unos
   milisegundos sin trabajo en la cola (`trabajos.en_curso`, `trabajos.py:264`). Y el detalle solo pinta una barra si
   su trabajo está vivo en la cola: una barra sobre un trabajo ya terminado avisaría `trabajo-terminado` al instante
   (`templates/base.html:211-216`) y la pestaña pediría el detalle en bucle; mientras una variante viva espera al
   vigilante, la pestaña vuelve a pedir el detalle cada 20 s, a lo sumo 30 veces.
5. **`parsear` y `analizar` ganan `duracion_s=None`** (`triple_whale/mejorar.py:396` y `:465`): sin duración, un
   `fotograma_s` ≥ 0 se conserva y la preparación lo vuelve a acotar contra el video medido. La tarea vacía `ganchos`
   cuando Claude no vio fotogramas del video (spec §2: los anuncios de imagen no reciben ganchos). `n` es la posición
   del gancho en la lista de Claude: si el 2 quedó fuera por cifras, las variantes son 1 y 3.

---

### Task 1: Tabla `tw_gancho` (migración 0035) y su escritor

**Files:**
- Modify: `db.py` (después de `tw_analisis`, ~línea 570)
- Create: `migrations/versions/0035_tw_gancho.py`
- Modify: `triple_whale/datos.py` (sección nueva al final, después de `piezas_de_analisis`)
- Test: `tests/test_tw_ganchos_datos.py` (nuevo), `tests/test_migracion_0035.py` (nuevo)

**Interfaces:**
- Consumes: `db._comunes()`, `db.conectar()`, `db.ahora()`, `datos.crear_analisis` (existente).
- Produces: `db.tw_gancho`; en `triple_whale.datos`: `ESTADOS_GANCHO = ("preparando", "generando", "armando",
  "produciendo", "lista", "error")`, `VIVOS_GANCHO = ("preparando", "generando", "armando", "produciendo")`,
  `CAMPOS_GANCHO = ("frame_url", "cf_id", "edicion_id", "final_id", "url_final", "job_id", "error")`,
  `class TandaViva(Exception)`, `crear_tanda(cliente, analisis_id, ganchos, pedido_por=None) -> list[dict]` (`ganchos` =
  `[{"n", "texto", "prompt", "fotograma_s"}]`; devuelve las filas ordenadas por `n`), `mover(gancho_id, de, a,
  **campos) -> bool`, `actualizar_gancho(gancho_id, **campos) -> bool`, `ganchos_de_analisis(cliente, analisis_id) ->
  list[dict]` (tanda descendente, `n` ascendente), `ganchos_vivos() -> list[dict]` (todos los proyectos),
  `gancho(cliente, gancho_id) -> dict | None`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_tw_ganchos_datos.py`:

```python
"""Ganchos de Triple Whale (spec 2026-10-09 §4.2): la tabla tw_gancho y su único escritor."""
import pytest
import sqlalchemy as sa
from sqlalchemy import event

from triple_whale import datos

GANCHOS_T = [{"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0},
             {"n": 3, "texto": "Tres", "prompt": "Pan left", "fotograma_s": None}]


def _analisis(cliente="acme"):
    return datos.crear_analisis(cliente, None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", {})


def test_crear_tanda_numera_y_no_deja_pedir_otra_mientras_vive(base_temporal):
    aid = _analisis()
    filas = datos.crear_tanda("acme", aid, GANCHOS_T, pedido_por="admin")
    assert [(f["tanda"], f["n"], f["estado"]) for f in filas] == [(1, 1, "preparando"), (1, 3, "preparando")]
    assert filas[0]["texto"] == "Uno" and filas[0]["fotograma_s"] == 2.0 and filas[1]["fotograma_s"] is None
    assert filas[0]["pedido_por"] == "admin" and filas[0]["cliente"] == "acme" and filas[0]["cf_id"] is None
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    for f in filas:
        assert datos.mover(f["id"], "preparando", "error", error="se cortó")
    assert [(f["tanda"], f["n"]) for f in datos.crear_tanda("acme", aid, GANCHOS_T[:1])] == [(2, 1)]
    otro = _analisis()
    assert datos.crear_tanda("acme", otro, GANCHOS_T[:1])[0]["tanda"] == 1      # cada análisis numera sus tandas
    with pytest.raises(ValueError):
        datos.crear_tanda("acme", otro, [])


def test_una_variante_viva_bloquea_y_las_terminadas_no(base_temporal):
    aid = _analisis()
    f1, f2 = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "lista", url_final="https://r2.test/a.mp4")
    assert datos.mover(f2["id"], "preparando", "produciendo")
    with pytest.raises(datos.TandaViva):
        datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f2["id"], "produciendo", "error", error="falló")
    assert datos.crear_tanda("acme", aid, GANCHOS_T)[0]["tanda"] == 2


def test_crear_tanda_toma_el_candado_antes_de_leer(base_temporal, escritor_en_medio):
    """Regla 5: dos clics a la vez no pueden leer los dos «sin tanda viva». Justo antes de la primera lectura otra
    conexión (otro hilo de gunicorn) intenta meter una fila viva: con el candado ya tomado queda bloqueada."""
    aid = _analisis()
    estado = escritor_en_medio(
        "FROM tw_gancho",
        "INSERT INTO tw_gancho (cliente, creado_en, actualizado_en, analisis_id, tanda, n, estado) "
        f"VALUES ('acme', 'x', 'x', {aid}, 9, 1, 'preparando')")
    datos.crear_tanda("acme", aid, GANCHOS_T)
    assert estado["hecho"] and estado["resultado"].startswith("bloqueado")


def test_mover_no_avanza_dos_veces_la_misma_variante(base_temporal):
    aid = _analisis()
    f1, _ = datos.crear_tanda("acme", aid, GANCHOS_T)
    assert datos.mover(f1["id"], "preparando", "generando", cf_id="cf_1", job_id="acme__cf_1__creative_flow")
    assert not datos.mover(f1["id"], "preparando", "generando", cf_id="cf_2")      # ya no está en preparando
    g = datos.gancho("acme", f1["id"])
    assert g["estado"] == "generando" and g["cf_id"] == "cf_1" and g["job_id"] == "acme__cf_1__creative_flow"
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "raro")
    with pytest.raises(ValueError):
        datos.actualizar_gancho(f1["id"], estado="lista")          # el estado solo cambia con mover
    with pytest.raises(ValueError):
        datos.mover(f1["id"], "generando", "armando", texto="otro")  # el texto del gancho no se reescribe
    assert datos.actualizar_gancho(f1["id"], frame_url="https://r2.test/f.jpg")
    assert datos.gancho("acme", f1["id"])["frame_url"] == "https://r2.test/f.jpg"
    assert datos.gancho("otro", f1["id"]) is None


def test_lecturas_filtran_por_proyecto_y_son_una_consulta(base_temporal):
    a1, a2 = _analisis(), _analisis("otro")
    for f in datos.crear_tanda("acme", a1, GANCHOS_T):
        datos.mover(f["id"], "preparando", "error", error="x")
    datos.crear_tanda("acme", a1, GANCHOS_T)
    datos.crear_tanda("otro", a2, GANCHOS_T)
    consultas = []
    contar = lambda conn, cursor, statement, *a: consultas.append(statement)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        filas = datos.ganchos_de_analisis("acme", a1)
        vivos = datos.ganchos_vivos()
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)
    assert len(consultas) == 2
    assert [(f["tanda"], f["n"]) for f in filas] == [(2, 1), (2, 3), (1, 1), (1, 3)]
    assert datos.ganchos_de_analisis("otro", a1) == []
    assert sorted((f["cliente"], f["tanda"]) for f in vivos) == [("acme", 2), ("acme", 2), ("otro", 1), ("otro", 1)]
```

`tests/test_migracion_0035.py`:

```python
"""Migración 0035 (spec 2026-10-09 §4.2): crea tw_gancho encima de 0034 y la bajada la quita sola."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0035_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig35.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0035")
        with db.conectar() as con:
            insp = sa.inspect(con)
            assert {"tw_gancho", "tw_analisis"} <= set(insp.get_table_names())
            ddl = con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='tw_gancho'")).scalar()
            assert "AUTOINCREMENT" in ddl.upper() and "uq_tw_gancho_tanda" in ddl
            indices = {i["name"] for i in insp.get_indexes("tw_gancho")}
            assert {"ix_tw_gancho_cliente", "ix_tw_gancho_analisis", "ix_tw_gancho_estado"} <= indices
        command.downgrade(_cfg(), "0034")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            assert "tw_gancho" not in tablas and "tw_analisis" in tablas
    finally:
        db._reset_para_tests()
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_datos.py tests/test_migracion_0035.py`
Expected: FAIL (`AttributeError: module 'triple_whale.datos' has no attribute 'crear_tanda'` / `Can't locate revision
identified by '0035'`).

- [ ] **Step 3: Implementar la tabla**

`db.py`, justo después de la definición de `tw_analisis`:

```python
# Ganchos nuevos de un análisis (spec 2026-10-09-tw-ganchos-y-copy §4.2, migración 0035): una fila por variante de
# «Probar los 3 ganchos». Su id es también el código `CV<id>` que va en el nombre del anuncio en Meta: AUTOINCREMENT
# para que nunca se reuse. Único escritor: triple_whale/datos.py.
tw_gancho = Table("tw_gancho", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("analisis_id", Integer, nullable=False),
    Column("tanda", Integer, nullable=False),
    Column("n", Integer, nullable=False),
    Column("estado", String(12), nullable=False, default="preparando"),  # preparando|generando|armando|produciendo|lista|error
    Column("texto", String(200)),
    Column("prompt", Text),
    Column("fotograma_s", Float),
    Column("frame_url", String(2000)),
    Column("cf_id", String(80)),
    Column("edicion_id", Integer),
    Column("final_id", String(200)),
    Column("url_final", String(2000)),
    Column("job_id", String(255)),
    Column("error", Text),
    Column("pedido_por", String(80)),
    sa.UniqueConstraint("analisis_id", "tanda", "n", name="uq_tw_gancho_tanda"),
    sa.Index("ix_tw_gancho_analisis", "cliente", "analisis_id", "tanda"),
    sa.Index("ix_tw_gancho_estado", "estado"),
    sqlite_autoincrement=True,
)
```

`migrations/versions/0035_tw_gancho.py`:

```python
"""Triple Whale: ganchos nuevos sobre el video original (spec 2026-10-09-tw-ganchos-y-copy §4.2)

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-09 12:00:00.000000

`tw_gancho`: una fila por variante de «Probar los 3 ganchos». AUTOINCREMENT: el id es el código CV<id> que va en el
nombre del anuncio en Meta y nunca se reusa.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0035'
down_revision: Union[str, Sequence[str], None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tw_gancho',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('analisis_id', sa.Integer(), nullable=False),
        sa.Column('tanda', sa.Integer(), nullable=False),
        sa.Column('n', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('texto', sa.String(200)),
        sa.Column('prompt', sa.Text()),
        sa.Column('fotograma_s', sa.Float()),
        sa.Column('frame_url', sa.String(2000)),
        sa.Column('cf_id', sa.String(80)),
        sa.Column('edicion_id', sa.Integer()),
        sa.Column('final_id', sa.String(200)),
        sa.Column('url_final', sa.String(2000)),
        sa.Column('job_id', sa.String(255)),
        sa.Column('error', sa.Text()),
        sa.Column('pedido_por', sa.String(80)),
        sa.UniqueConstraint('analisis_id', 'tanda', 'n', name='uq_tw_gancho_tanda'),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_tw_gancho_cliente', 'tw_gancho', ['cliente'])
    op.create_index('ix_tw_gancho_analisis', 'tw_gancho', ['cliente', 'analisis_id', 'tanda'])
    op.create_index('ix_tw_gancho_estado', 'tw_gancho', ['estado'])


def downgrade() -> None:
    op.drop_index('ix_tw_gancho_estado', table_name='tw_gancho')
    op.drop_index('ix_tw_gancho_analisis', table_name='tw_gancho')
    op.drop_index('ix_tw_gancho_cliente', table_name='tw_gancho')
    op.drop_table('tw_gancho')
```

- [ ] **Step 4: Implementar el escritor**

En `triple_whale/datos.py`, el docstring del módulo suma «y `tw_gancho` (ganchos, spec 2026-10-09 §4.2)» a la lista
de tablas, y al final del archivo:

```python
# ------------------------------------------------- ganchos (spec 2026-10-09 §4.2) ---
ESTADOS_GANCHO = ("preparando", "generando", "armando", "produciendo", "lista", "error")
VIVOS_GANCHO = ("preparando", "generando", "armando", "produciendo")
# Lo que las tareas anotan en una variante. El texto, el prompt y el fotograma son la copia del gancho al pedirlo y no
# se reescriben; el estado solo cambia con `mover`.
CAMPOS_GANCHO = ("frame_url", "cf_id", "edicion_id", "final_id", "url_final", "job_id", "error")


class TandaViva(Exception):
    """Ese análisis ya tiene una tanda de ganchos en curso: no se pide otra (doble clic, dos pestañas)."""


def _campos_gancho(campos):
    raros = set(campos) - set(CAMPOS_GANCHO)
    if raros:
        raise ValueError(f"campos de tw_gancho no permitidos: {sorted(raros)}")


def crear_tanda(cliente, analisis_id, ganchos, pedido_por=None):
    """Las filas de una tanda nueva del análisis, en `preparando` (spec §4.2). `ganchos` = [{"n", "texto", "prompt",
    "fotograma_s"}] (`triple_whale.ganchos.ganchos_generables`). El candado de escritura de SQLite se toma ANTES de
    leer (BEGIN IMMEDIATE, como referentes.datos.guardar_referente): dos clics a la vez no leen los dos «sin tanda
    viva». Con alguna fila viva del análisis lanza TandaViva; si no, inserta la tanda max + 1 en la misma transacción
    y devuelve sus filas por `n`. El UNIQUE (analisis_id, tanda, n) es la red si algo se cuela."""
    if not ganchos:
        raise ValueError("crear_tanda: sin ganchos no hay tanda")
    t = db.tw_gancho
    aid = int(analisis_id)
    ahora = db.ahora()
    try:
        with db.conectar() as con:
            con.exec_driver_sql("BEGIN IMMEDIATE")
            vivas = con.execute(sa.select(sa.func.count()).select_from(t).where(
                t.c.cliente == cliente, t.c.analisis_id == aid, t.c.estado.in_(VIVOS_GANCHO))).scalar()
            if vivas:
                raise TandaViva()
            tanda = int(con.execute(sa.select(sa.func.coalesce(sa.func.max(t.c.tanda), 0)).where(
                t.c.cliente == cliente, t.c.analisis_id == aid)).scalar() or 0) + 1
            ids = [con.execute(t.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, analisis_id=aid, tanda=tanda, n=int(g["n"]),
                estado="preparando", texto=g["texto"], prompt=g["prompt"], fotograma_s=g.get("fotograma_s"),
                pedido_por=pedido_por)).inserted_primary_key[0] for g in ganchos]
            filas = con.execute(sa.select(t).where(t.c.id.in_(ids)).order_by(t.c.n)).all()
    except sa.exc.IntegrityError:
        raise TandaViva() from None
    return [dict(f._mapping) for f in filas]


def mover(gancho_id, de, a, **campos):
    """CAS de estado: `UPDATE … WHERE id = ? AND estado = de`. True si cambió: el vigilante y las tareas nunca
    avanzan dos veces la misma variante (spec §4.2)."""
    if de not in ESTADOS_GANCHO or a not in ESTADOS_GANCHO:
        raise ValueError(f"estado inválido: {de} → {a}")
    _campos_gancho(campos)
    t = db.tw_gancho
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == int(gancho_id), t.c.estado == de)
                           .values(estado=a, actualizado_en=db.ahora(), **campos)).rowcount == 1


def actualizar_gancho(gancho_id, **campos):
    """Anota `CAMPOS_GANCHO` sin tocar el estado. True si la fila existe."""
    _campos_gancho(campos)
    t = db.tw_gancho
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == int(gancho_id))
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def ganchos_de_analisis(cliente, analisis_id):
    """Todas las variantes del análisis, la tanda más nueva primero y por `n` dentro de cada una: UNA consulta (el
    detalle pinta la última tanda y resume las anteriores)."""
    t = db.tw_gancho
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(t).where(t.c.cliente == cliente, t.c.analisis_id == int(analisis_id))
            .order_by(t.c.tanda.desc(), t.c.n))]


def ganchos_vivos():
    """Las variantes vivas de todos los proyectos (el vigilante), en una consulta."""
    t = db.tw_gancho
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(t).where(t.c.estado.in_(VIVOS_GANCHO)).order_by(t.c.id))]


def gancho(cliente, gancho_id):
    t = db.tw_gancho
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.id == int(gancho_id), t.c.cliente == cliente)).first()
    return dict(fila._mapping) if fila else None
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_datos.py tests/test_migracion_0035.py tests/test_migracion_0034.py tests/test_sprints_db.py::test_alembic_tiene_una_sola_cabeza`
Expected: PASS.

Luego la suite de Triple Whale (Global Constraints). Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add db.py migrations/versions/0035_tw_gancho.py triple_whale/datos.py tests/test_tw_ganchos_datos.py tests/test_migracion_0035.py
git commit -m "Triple Whale ganchos: tabla tw_gancho (migración 0035) con su escritor, tanda con candado y CAS de estado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: El análisis trae ganchos y copy nuevo, y su precio

**Files:**
- Modify: `triple_whale/mejorar.py` (`PROMPT` ~línea 202, `system` ~360, helpers nuevos antes de `parsear`, `parsear`
  ~396, `analizar` ~465)
- Modify: `gastos.py` (después de `_estimar_analisis_anuncio_tw`, ~línea 431)
- Modify: `tareas/triple_whale.py` (`tw_analizar_anuncio`, la llamada a `mejorar.analizar` ~línea 169)
- Modify: `tests/test_tw_mejorar.py` (constantes `GANCHOS` y `COPY_NUEVO` + pruebas nuevas)
- Modify: `tests/test_tw_tarjetas_tarea.py` (tres dobles de `mejorar.analizar` aceptan `duracion_s` + una prueba)

**Interfaces:**
- Consumes: `doctrina.verificar_cifras(texto, verificable)`, `analisis._texto`, `analisis._json` (existentes).
- Produces: en `triple_whale.mejorar`: `MAX_GANCHOS = 3`, `MAX_TEXTO_GANCHO = 60`, `segundo_fotograma(valor,
  duracion_s) -> float | None`, `_ganchos(lista, verificable, duracion_s) -> list[dict]` (cada uno `{"texto",
  "escena", "prompt", "fotograma_s", "por_que", "cifras_sin_dato"}`), `_copy_nuevo(d, verificable) -> dict | None`
  (`{"titulo", "texto", "por_que", "cifras_sin_dato"}`), `parsear(texto, verificable, duracion_s=None)` (el resultado
  suma `"ganchos"` y `"copy_nuevo"`), `analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None)`.
  En `gastos`: `GANCHO_TW_MODELO = "kling_o3_pro"`, `GANCHO_TW_SEGUNDOS = 3`, `estimar_ganchos_tw(n) -> dict` (la
  misma forma que `estimar`: `usd` es el costo, `usd_precio` y `texto` con el margen). En `tests.test_tw_mejorar`:
  `GANCHOS` (3 ganchos sin cifras) y `COPY_NUEVO`.

- [ ] **Step 1: Escribir las pruebas que fallan**

En `tests/test_tw_mejorar.py`, debajo de `respuesta()`:

```python
# Ganchos y copy de ejemplo (spec 2026-10-09 §3.1): ninguna cifra de dos dígitos, así ninguno trae cifras sin dato.
GANCHOS = [
    {"texto": "¿Te duelen los pies al final del día?", "escena": "Un pie cansado entra en la chancla",
     "prompt": "Slow push-in on a tired foot sliding into a soft slipper, warm light, handheld camera.",
     "fotograma_s": 4.2, "por_que": "Abre con el dolor en vez del logo"},
    {"texto": "Así se ve el alivio", "escena": "Primer plano de la suela",
     "prompt": "Macro shot of the cushioned sole pressing down, slow motion, soft daylight.",
     "fotograma_s": 6, "por_que": "Muestra la prueba primero"},
    {"texto": "Tus pies te lo van a agradecer", "escena": "Una mamá se quita los zapatos",
     "prompt": "A mother sits down and slips off her shoes, the camera tilts down to her feet.",
     "fotograma_s": 1.5, "por_que": "Otra audiencia, la misma promesa"},
]
COPY_NUEVO = {"titulo": "Descanso para tus pies", "texto": "Chanclas suaves para después del trabajo.\nPruébalas hoy.",
              "por_que": "Abre con el beneficio en vez del producto"}
```

Y al final del archivo:

```python
# ---------------------------------------------------- ganchos y copy (spec 2026-10-09 §3) ---

def test_el_prompt_pide_ganchos_y_copy_con_sus_reglas():
    p = mejorar.PROMPT
    assert '"ganchos": [{"texto"' in p.replace("{{", "{") and '"copy_nuevo": {"titulo"' in p.replace("{{", "{")
    assert "fotograma_s" in p and "exactamente 3" in p and '"ganchos": []' in p
    assert "nunca inventes" in p and "la voz original sigue sonando" in p and "subtítulos ni logos" in p
    texto = mejorar.armar("Acme", {"foto": _foto(), "desde": "2026-09-01", "hasta": "2026-09-30", "moneda": "USD",
                                   "canal": "facebook-ads"})
    assert '"ganchos": [{"texto"' in texto and "{{" not in texto           # el formato sigue armando el prompt


def test_system_dice_las_tres_excepciones_de_idioma(monkeypatch):
    import doctrina
    capturado = {}
    monkeypatch.setattr(doctrina, "bloque_system",
                        lambda *reb, extra="", idioma=None: capturado.update(extra=extra) or "S")
    mejorar.system("es")
    extra = capturado["extra"]
    assert "TEXTO DEL ANUNCIO" in extra and "copy_nuevo" in extra and "inglés" in extra and "gancho" in extra


def test_ganchos_se_limpian_y_se_acotan():
    largo = "x" * 400
    crudo = [
        {"texto": "Hola\n\x00mundo‮ " + "y" * 80, "escena": largo, "prompt": "p" * 1500, "fotograma_s": 4.2,
         "por_que": largo},
        {"texto": "Sin prompt"},                                       # se descarta
        "no es un dict",                                               # se descarta
        {"texto": "Dos", "prompt": "Push in", "fotograma_s": 99},      # fuera de rango: la mitad
        {"texto": "Tres", "prompt": "Pan", "fotograma_s": "abc"},      # no es número: la mitad
        {"texto": "Cuatro", "prompt": "Tilt", "fotograma_s": 1},       # el cuarto válido sobra
    ]
    g = mejorar._ganchos(crudo, "datos", 20.0)
    assert len(g) == 3
    assert g[0]["texto"].startswith("Hola mundo y") and len(g[0]["texto"]) == mejorar.MAX_TEXTO_GANCHO
    assert not any(c in g[0]["texto"] for c in ("\n", "\x00", "‮"))
    assert len(g[0]["escena"]) == 300 and len(g[0]["por_que"]) == 300 and len(g[0]["prompt"]) == 1000
    assert [x["fotograma_s"] for x in g] == [4.2, 10.0, 10.0]
    assert all(x["cifras_sin_dato"] == [] for x in g)
    assert mejorar._ganchos("no es una lista", "datos", 20.0) == [] and mejorar._ganchos(None, "datos", None) == []


def test_segundo_fotograma_sin_duracion_conserva_un_numero_valido():
    assert mejorar.segundo_fotograma(33, None) == 33.0
    assert mejorar.segundo_fotograma(-1, None) is None and mejorar.segundo_fotograma("abc", None) is None
    assert mejorar.segundo_fotograma(True, 20.0) == 10.0                  # un bool no es un segundo
    assert mejorar.segundo_fotograma(19, 20.0) == 19.0 and mejorar.segundo_fotograma(19.5, 20.0) == 10.0
    assert mejorar.segundo_fotograma(float("nan"), 8.0) == 4.0


def test_un_gancho_con_cifras_sin_dato_lo_dice():
    g = mejorar._ganchos([{"texto": "50 % menos dolor", "prompt": "x", "por_que": "Retiene 3 veces más"}], "datos", 20.0)
    assert g[0]["cifras_sin_dato"] == ["50 %", "3 veces"]
    g = mejorar._ganchos([{"texto": "50 % menos dolor", "prompt": "x", "por_que": "Retiene 3 veces más"}],
                         "dolor 50 % · 3 veces", 20.0)
    assert g[0]["cifras_sin_dato"] == []


def test_copy_nuevo_conserva_saltos_limpia_y_avisa_cifras():
    assert mejorar._copy_nuevo(None, "datos") is None and mejorar._copy_nuevo({"titulo": "Solo título"}, "datos") is None
    c = mejorar._copy_nuevo({"titulo": "T" * 100, "texto": "Línea 1\n\n\n\nLínea 2\x00", "por_que": "Porque sí"},
                            "datos")
    assert len(c["titulo"]) == 80 and c["texto"] == "Línea 1\n\nLínea 2" and c["por_que"] == "Porque sí"
    assert c["cifras_sin_dato"] == []
    assert mejorar._copy_nuevo({"texto": "Hasta 50 % de descuento"}, "datos")["cifras_sin_dato"] == ["50 %"]
    assert mejorar._copy_nuevo({"texto": "Hasta 50 % de descuento"}, "descuento 50 %")["cifras_sin_dato"] == []


def test_parsear_un_analisis_sin_ganchos_ni_copy_sigue_valido():
    r = mejorar.parsear(respuesta(), "datos")
    assert r["ganchos"] == [] and r["copy_nuevo"] is None and r["frase"]
    r = mejorar.parsear(respuesta(ganchos="raro", copy_nuevo=[1, 2]), "datos")
    assert r["ganchos"] == [] and r["copy_nuevo"] is None
    r = mejorar.parsear(respuesta(ganchos=GANCHOS, copy_nuevo=COPY_NUEVO), "datos", duracion_s=20.0)
    assert [g["texto"] for g in r["ganchos"]] == [g["texto"] for g in GANCHOS]
    assert r["copy_nuevo"]["titulo"] == "Descanso para tus pies" and "\n" in r["copy_nuevo"]["texto"]


def test_analizar_le_pasa_la_duracion_al_parseo(monkeypatch):
    monkeypatch.setattr(mejorar, "_llamar", lambda content, system_: (respuesta(ganchos=GANCHOS), 100, 10))
    monkeypatch.setattr(mejorar, "system", lambda idioma: "SYSTEM")
    r, _, _ = mejorar.analizar("DATOS", [], "es", duracion_s=8.0)
    assert [g["fotograma_s"] for g in r["ganchos"]] == [4.2, 6.0, 1.5]
    r, _, _ = mejorar.analizar("DATOS", [], "es", duracion_s=5.0)
    assert [g["fotograma_s"] for g in r["ganchos"]] == [2.5, 2.5, 1.5]        # 4,2 y 6 pasan de 5 − 1


def test_precio_de_los_ganchos_es_n_clips_de_kling():
    tres = gastos.estimar_ganchos_tw(3)
    assert tres["usd"] == pytest.approx(3 * 0.336) and tres["texto"] == "US$ 1,01 aprox."
    assert gastos.estimar_ganchos_tw(2)["usd"] == pytest.approx(0.672)
    uno = gastos.estimar("video", modelo=gastos.GANCHO_TW_MODELO, duracion=gastos.GANCHO_TW_SEGUNDOS, con_sonido=False)
    assert gastos.estimar_ganchos_tw(1)["usd"] == uno["usd"] == pytest.approx(0.336)
    assert gastos.estimar_ganchos_tw(0)["usd"] is None and gastos.estimar_ganchos_tw(0)["texto"] == "precio no disponible"


def test_sin_tarifa_de_kling_los_ganchos_no_tienen_precio(monkeypatch):
    from providers import flowplus_modelos
    monkeypatch.setattr(flowplus_modelos, "estimate_video", lambda *a, **k: {"usd": None})
    assert gastos.estimar_ganchos_tw(3)["usd"] is None
```

En `tests/test_tw_tarjetas_tarea.py`, los tres dobles de `mejorar.analizar` aceptan la duración (la tarea la pasa
desde esta tarea en adelante):
- `def _analizar(texto, imagenes, idioma, verificable_extra=""):` (línea ~39) pasa a
  `def _analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None):`
- las dos lambdas `lambda texto, imagenes, idioma, verificable_extra="": (` (líneas ~98 y ~172) pasan a
  `lambda texto, imagenes, idioma, verificable_extra="", duracion_s=None: (` (Edit con `replace_all`).

Y al final de ese archivo:

```python
def test_la_tarea_pasa_la_duracion_y_sin_fotogramas_no_deja_ganchos(en_cola, monkeypatch):
    """Spec 2026-10-09 §3.2 y §2: `fotograma_s` se acota con la duración del video, y un anuncio que Claude solo vio
    como imagen recibe copy pero no ganchos (aunque Claude los mande)."""
    from tests.test_tw_mejorar import GANCHOS
    recibido = {}

    def _analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None):
        recibido["duracion_s"] = duracion_s
        return mejorar.parsear(respuesta(ganchos=GANCHOS), texto, duracion_s=duracion_s), 100, 50
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    en_cola["t"].tw_analizar_anuncio({"id": 21, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert recibido["duracion_s"] == 21.0
    assert len(datos.analisis_anuncio("acme", en_cola["aid"])["resultado"]["ganchos"]) == 3
    aid2 = datos.crear_analisis("acme", None, "facebook-ads", "p2", "2026-09-01", "2026-09-30", "USD", _foto())
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [], "clase": "imagen", "fotogramas": 0}, []))
    en_cola["t"].tw_analizar_anuncio({"id": 22, "payload": {"cliente": "acme", "analisis_id": aid2}})
    assert datos.analisis_anuncio("acme", aid2)["resultado"]["ganchos"] == []
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_mejorar.py tests/test_tw_tarjetas_tarea.py`
Expected: FAIL (`AttributeError: module 'triple_whale.mejorar' has no attribute '_ganchos'`, `module 'gastos' has no
attribute 'estimar_ganchos_tw'`, `TypeError: parsear() got an unexpected keyword argument 'duracion_s'`).

- [ ] **Step 3: Implementar el prompt y el system**

En `triple_whale/mejorar.py`, imports: suma `import math` y `import unicodedata` (orden alfabético con los demás).

En `PROMPT`, la última clave del JSON pedido cambia de

```
 "aprendizaje": "una frase de máximo 200 caracteres para este proyecto: en esta cuenta, X funciona o no porque Y"}}
```

a

```
 "aprendizaje": "una frase de máximo 200 caracteres para este proyecto: en esta cuenta, X funciona o no porque Y",
 "ganchos": [{{"texto": "texto en pantalla, máximo 8 palabras, en el idioma del TEXTO DEL ANUNCIO",
              "escena": "qué se ve en esos 3 s, máximo 40 palabras",
              "prompt": "English prompt for a 3-second image-to-video clip that starts on the chosen frame, 30 to 80 words",
              "fotograma_s": 4.2,
              "por_que": "qué arregla frente al gancho actual y por qué debería retener más"}}],
 "copy_nuevo": {{"titulo": "máximo 40 caracteres, en el idioma del TEXTO DEL ANUNCIO",
                "texto": "el texto principal del anuncio, máximo 500 caracteres, mismo idioma",
                "por_que": "qué cambia frente al copy actual"}}}}
```

y después de la última regla («- Si no hay fotogramas ni imagen, juzga por el texto, la voz y los números, y dilo en
"frase".») se suman, antes del `"""` final:

```
- "ganchos": exactamente 3 si ves fotogramas del video (las imágenes con «Segundo N:»); si no los ves (solo una imagen, o nada), "ganchos": []. Los 3 son distintos entre sí (otra pregunta, otro dolor, otra demostración, otra prueba) y llevan la misma promesa del anuncio.
- El clip de cada gancho reemplaza los 3 primeros segundos y la voz original sigue sonando debajo (es la del bloque VOZ): su "texto" tiene que funcionar con esa voz.
- "fotograma_s" es el segundo de uno de los fotogramas que viste, uno donde se vea bien el producto: el clip arranca en esa imagen.
- El "prompt" de cada gancho describe el movimiento y la cámara durante 3 s desde esa imagen; nunca pide textos, subtítulos ni logos (el texto lo pone el editor).
- "copy_nuevo": usa solo las ofertas, descuentos, precios y plazos que aparecen en el TEXTO DEL ANUNCIO o en los datos de arriba; nunca inventes uno.
- Idiomas: el "texto" de cada gancho y el "titulo" y el "texto" de "copy_nuevo" van en el idioma del TEXTO DEL ANUNCIO (si no hay texto, en el de la voz); "escena" y "por_que" van en el idioma pedido; el "prompt" de cada gancho, en inglés.
```

(Las reglas no llevan llaves: el `.format` de `armar` sigue igual.)

`system`:

```python
def system(idioma):
    extra = ("Todo el texto de la respuesta va en el idioma pedido, con tres excepciones: el campo \"prompt\" de "
             "\"version\" y el de cada gancho van siempre en inglés, porque son para el modelo de video; y el \"texto\" "
             "de cada gancho y el \"titulo\" y el \"texto\" de \"copy_nuevo\" van en el idioma del TEXTO DEL ANUNCIO "
             "(si no hay texto, en el de la voz), porque se publican dentro del anuncio.")
    return doctrina.bloque_system("revisar", "diagnosticar", "angulo", "gancho", "video", extra=extra, idioma=idioma)
```

- [ ] **Step 4: Implementar el parseo**

En `triple_whale/mejorar.py`, junto a las constantes del principio:

```python
MAX_GANCHOS = 3
MAX_TEXTO_GANCHO = 60
```

Antes de `parsear`:

```python
# ------------------------------------------------- ganchos y copy (spec 2026-10-09 §3.2) ---

def _limpio(valor, tope):
    """Una línea sin caracteres de control ni de formato (saltos, U+0000…, U+202E…): el texto de un gancho va dentro
    de un video y su prompt a Kling, y los dos salen de un análisis que leyó texto ajeno."""
    texto = " ".join(str(valor if valor is not None else "").split())
    texto = "".join(ch for ch in texto if unicodedata.category(ch) not in ("Cc", "Cf"))
    return " ".join(texto.split())[:tope]


def _texto_largo(valor, tope):
    """El texto principal de un anuncio: conserva los saltos de línea (Meta los muestra), sin otros caracteres de
    control ni de formato y sin más de una línea en blanco seguida."""
    lineas = []
    for linea in str(valor if valor is not None else "").splitlines():
        limpia = "".join(ch for ch in " ".join(linea.split()) if unicodedata.category(ch) not in ("Cc", "Cf"))
        lineas.append(" ".join(limpia.split()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()[:tope]


def segundo_fotograma(valor, duracion_s):
    """El segundo donde arranca el clip (spec §3.2): un número en [0, duración − 1] queda; si no, la mitad del video.
    Sin duración conocida, un número ≥ 0 queda (la preparación lo vuelve a acotar contra el video medido) y lo demás es
    None. Un bool no es un segundo."""
    try:
        s = None if isinstance(valor, bool) else float(valor)
    except (TypeError, ValueError):
        s = None
    if s is not None and not math.isfinite(s):
        s = None
    try:
        dur = float(duracion_s) if duracion_s else None
    except (TypeError, ValueError):
        dur = None
    if dur and dur > 0:
        return round(s, 2) if s is not None and 0 <= s <= dur - 1 else round(dur / 2, 2)
    return round(s, 2) if s is not None and s >= 0 else None


def _ganchos(lista, verificable, duracion_s):
    """Hasta MAX_GANCHOS ganchos con `texto` y `prompt`. Nunca lanza: uno malo se descarta y un análisis sin ganchos
    sigue siendo válido (no paga una corrección). Cada uno lleva `cifras_sin_dato` de su texto y su porqué: con alguna
    no se genera ni entra en el precio (la misma regla que el aprendizaje, revisión B2 del 2026-10-08)."""
    salida = []
    for g in lista if isinstance(lista, list) else []:
        if len(salida) >= MAX_GANCHOS:
            break
        if not isinstance(g, dict):
            continue
        texto, prompt = _limpio(g.get("texto"), MAX_TEXTO_GANCHO), _limpio(g.get("prompt"), 1000)
        if not texto or not prompt:
            continue
        por_que = analisis._texto(g.get("por_que"), 300)
        salida.append({"texto": texto, "escena": analisis._texto(g.get("escena"), 300), "prompt": prompt,
                       "fotograma_s": segundo_fotograma(g.get("fotograma_s"), duracion_s), "por_que": por_que,
                       "cifras_sin_dato": doctrina.verificar_cifras(f"{texto} {por_que}", verificable)})
    return salida


def _copy_nuevo(d, verificable):
    """{"titulo", "texto", "por_que", "cifras_sin_dato"}, o None sin texto. Una cifra sin dato no bloquea: el detalle
    la muestra con «revisa antes de publicar», porque copiarlo es decisión de la persona."""
    if not isinstance(d, dict):
        return None
    texto = _texto_largo(d.get("texto"), 1000)
    if not texto:
        return None
    titulo, por_que = _limpio(d.get("titulo"), 80), analisis._texto(d.get("por_que"), 300)
    return {"titulo": titulo, "texto": texto, "por_que": por_que,
            "cifras_sin_dato": doctrina.verificar_cifras(f"{titulo} {texto} {por_que}", verificable)}
```

`parsear`: el cuerpo de hoy no cambia; cambian la firma, el docstring y el `return`. La firma y el docstring pasan a

```python
def parsear(texto, verificable, duracion_s=None):
    """El resultado limpio (forma en el docstring del módulo y spec §6.3). AnalisisInvalido sin frase, sin razones,
    con menos de 3 cambios o sin versión con título y prompt. `ganchos` y `copy_nuevo` (spec 2026-10-09 §3.2) nunca lo
    vuelven más exigente; los análisis de antes no los traen y se leen con `.get`. `duracion_s` (la del video del
    anuncio, o None) acota el `fotograma_s` de cada gancho."""
```

y el `return` del final (hoy `return {"frase": frase, … "cifras_sin_dato": doctrina.verificar_cifras(" ".join(textos),
verificable)}`) pasa a

```python
    return {"frase": frase, "funciona": funciona, "falla": falla, "cambios": cambios, "version": version,
            "aprendizaje": aprendizaje, "cifras_sin_dato": doctrina.verificar_cifras(" ".join(textos), verificable),
            "ganchos": _ganchos(data.get("ganchos"), verificable, duracion_s),
            "copy_nuevo": _copy_nuevo(data.get("copy_nuevo"), verificable)}
```

`analizar` entera (gana `duracion_s=None` y lo pasa a los dos `parsear`):

```python
def analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None):
    """(resultado, tokens_entrada, tokens_salida). Una corrección si la primera respuesta no sirve; si tampoco,
    AnalisisInvalido con los tokens pagados. `verificable_extra` suma a los datos verificables lo que Claude ve fuera
    del texto (los segundos de los fotogramas); `duracion_s` (la del video del anuncio, o None) acota el `fotograma_s`
    de cada gancho (spec 2026-10-09 §3.2)."""
    content = [{"type": "text", "text": texto}] + list(imagenes or [])
    system_ = system(idioma)
    verificable = texto + ("\n" + verificable_extra if verificable_extra else "")
    crudo, entrada, salida = _llamar(content, system_)
    try:
        return parsear(crudo, verificable, duracion_s), entrada, salida
    except analisis.AnalisisInvalido as e:
        correccion = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). "
                                                         "Responde solo el JSON pedido."}]
        try:
            crudo, e2, s2 = _llamar(correccion, system_)
        except Exception:
            e.tokens_entrada, e.tokens_salida = entrada, salida
            raise e
        entrada, salida = entrada + e2, salida + s2
        try:
            return parsear(crudo, verificable, duracion_s), entrada, salida
        except analisis.AnalisisInvalido as e3:
            e3.tokens_entrada, e3.tokens_salida = entrada, salida
            raise e3
```

- [ ] **Step 5: Implementar el precio**

En `gastos.py`, después de `_estimar_analisis_anuncio_tw`:

```python
# Ganchos de Triple Whale (spec 2026-10-09-tw-ganchos-y-copy §4.1): cada variante es un clip de Kling O3 Pro, imagen
# a video, de 3 s y sin sonido; armarlo y producirlo es ffmpeg (gratis).
GANCHO_TW_MODELO = "kling_o3_pro"
GANCHO_TW_SEGUNDOS = 3


def estimar_ganchos_tw(n):
    """El precio de «Probar los N ganchos»: n × el clip de Kling, la MISMA cuenta en la ruta y en la plantilla. La
    misma forma que `estimar` (`usd` es el costo). Sin ganchos o sin tarifa, «precio no disponible» (usd None), nunca
    US$ 0."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    uno = estimar("video", modelo=GANCHO_TW_MODELO, duracion=GANCHO_TW_SEGUNDOS, con_sonido=False)["usd"]
    if n <= 0 or uno is None:
        return _estimado(None, "sin ganchos que generar")
    return _estimado(uno * n, f"{n} clip(s) de {GANCHO_TW_SEGUNDOS} s con Kling O3 Pro, imagen a video")
```

- [ ] **Step 6: La tarea pasa la duración y no deja ganchos sin fotogramas**

En `tareas/triple_whale.py`, `tw_analizar_anuncio`, la llamada a `mejorar.analizar` y la línea que sigue:

```python
        resultado, entrada, salida = mejorar.analizar(texto, vis["bloques"], idiomas.de_proyecto(cliente),
                                                      verificable_extra=mejorar.segundos_verificables(vis["bloques"], voz),
                                                      duracion_s=(foto.get("creativo") or {}).get("duracion_s"))
        if vis["clase"] != "fotogramas":
            # Spec 2026-10-09 §2: sin fotogramas del video (un anuncio de imagen, o nada) hay copy pero no ganchos,
            # aunque Claude los mande: el clip arranca en un fotograma que Claude tiene que haber visto.
            resultado["ganchos"] = []
```

- [ ] **Step 7: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_mejorar.py tests/test_tw_tarjetas_tarea.py tests/test_tw_tarjetas_rutas.py tests/test_gastos*.py`
Expected: PASS. Luego la suite de Triple Whale. Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add triple_whale/mejorar.py gastos.py tareas/triple_whale.py tests/test_tw_mejorar.py tests/test_tw_tarjetas_tarea.py
git commit -m "Triple Whale ganchos: el análisis trae tres ganchos y copy nuevo para Meta, y el precio de probarlos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `triple_whale/ganchos.py`: código, formato, destino, documento y por qué no

**Files:**
- Create: `triple_whale/ganchos.py`
- Test: `tests/test_tw_ganchos.py` (nuevo)
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`

**Interfaces:**
- Consumes: `gastos.GANCHO_TW_MODELO`, `gastos.GANCHO_TW_SEGUNDOS`, `gastos.SIN_PRECIO` (Task 2);
  `triple_whale.datos.VIVOS_GANCHO` (Task 1); `final_edition.documento` (`FORMATOS`, `nuevo_video`, `validar`),
  `final_edition.borrador` (`ESTILO_HOOK`, `POS_HOOK`), `final_edition.tipos.PAISES`,
  `providers.flowplus_modelos.VIDEO`.
- Produces (en `triple_whale.ganchos`): `MODELO`, `SEGUNDOS`, `MIN_ORIGINAL_S = 5`, `PISTA_ORIGINAL = "p_original"`,
  `class GanchoError(Exception)` (su mensaje es un msgid de `N_`: quien lo muestra hace `gettext`), las constantes
  `MOTIVO_NO_LISTO`, `MOTIVO_VIEJO`, `MOTIVO_SIN_GANCHOS`, `MOTIVO_SIN_VIDEO`, `MOTIVO_CORTO`, `MOTIVO_TANDA_VIVA`,
  `MOTIVO_SIN_PRECIO`, `ERROR_BAJAR`, `ERROR_NO_MP4`, `ERROR_FOTOGRAMA`; `codigo(gancho_id) -> str`,
  `codigo_en(nombre) -> int | None`, `formato_cercano(ancho, alto) -> str`, `aspecto_kling(ancho, alto) -> str`,
  `destino(pais_tienda, pais_proyecto) -> (idioma, pais)`, `ganchos_generables(resultado) -> list[dict]`
  (`{"n", "texto", "prompt", "fotograma_s"}`, `n` = posición 1–3 en la lista de Claude), `puede_probar(fila,
  generables, filas_ganchos, precio_usd, url_video) -> str | None`, `tandas(filas) -> list[{"tanda", "filas"}]` (cada
  fila con `codigo`), `documento_gancho(clip, original, texto, formato, idioma, pais, analisis_id=None,
  gancho_id=None) -> dict` (validado).

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_tw_ganchos.py`:

```python
"""Las funciones puras de los ganchos (spec 2026-10-09 §4.6 y §4.7): código, formato, destino, el documento del
editor y por qué no se ofrece el botón. Sin base, sin red y sin ffmpeg."""
import pytest

from final_edition import borrador, vista_previa
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from triple_whale import ganchos

URL = "https://files.triplewhale.com/v/p1.mp4"
GEN = [{"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0}]
CLIP = {"id": 7, "duracion_ms": 3040, "extra": {"tiene_audio": False}}
ORIGINAL = {"id": 9, "duracion_ms": 20000, "ancho": 1080, "alto": 1920, "extra": {"tiene_audio": True}}


def test_codigo_y_codigo_en():
    assert ganchos.codigo(12) == "CV12" and ganchos.codigo("7") == "CV7"
    assert ganchos.codigo_en("Chanclas · gancho 2 · CV12") == 12
    assert ganchos.codigo_en("cv7 prueba") == 7 and ganchos.codigo_en("[CV31]") == 31
    for nombre in ("ACV12", "CV12a", "CV", "", None, "Sin código"):
        assert ganchos.codigo_en(nombre) is None, nombre


def test_formato_y_aspecto_mas_cercanos():
    assert ganchos.formato_cercano(1080, 1920) == "9:16" and ganchos.formato_cercano(1920, 1080) == "16:9"
    assert ganchos.formato_cercano(1080, 1350) == "4:5" and ganchos.formato_cercano(1000, 1000) == "1:1"
    assert ganchos.formato_cercano(720, 1280) == "9:16" and ganchos.formato_cercano(None, 0) == "9:16"
    assert ganchos.aspecto_kling(1080, 1920) == "9:16" and ganchos.aspecto_kling(1920, 1080) == "16:9"
    assert ganchos.aspecto_kling(1080, 1350) == "1:1" and ganchos.aspecto_kling(None, None) == "9:16"


def test_destino_tienda_proyecto_y_colombia():
    assert ganchos.destino("NO", "CO") == ("no", "NO")
    assert ganchos.destino(None, "US") == ("en", "US")
    assert ganchos.destino("DE", "SE") == ("sv", "SE")          # Alemania no está en tipos.PAISES
    assert ganchos.destino(None, "ZZ") == ("es", "CO")


def test_ganchos_generables_deja_fuera_los_que_citan_cifras_y_numera_por_posicion():
    r = {"ganchos": [{"texto": "Uno", "prompt": "a", "fotograma_s": 1.0, "cifras_sin_dato": []},
                     {"texto": "50 % menos", "prompt": "b", "fotograma_s": 2.0, "cifras_sin_dato": ["50 %"]},
                     {"texto": "Tres", "prompt": "c", "fotograma_s": None, "cifras_sin_dato": []}]}
    assert ganchos.ganchos_generables(r) == [{"n": 1, "texto": "Uno", "prompt": "a", "fotograma_s": 1.0},
                                             {"n": 3, "texto": "Tres", "prompt": "c", "fotograma_s": None}]
    assert ganchos.ganchos_generables({}) == [] and ganchos.ganchos_generables(None) == []


def _fila(resultado=None, estado="lista", duracion=20.0):
    return {"estado": estado, "resultado": {"ganchos": [{"texto": "Uno"}]} if resultado is None else resultado,
            "foto": {"creativo": {"duracion_s": duracion}}}


def test_puede_probar_dice_por_que_no():
    assert ganchos.puede_probar(_fila(), GEN, [], 0.336, URL) is None
    assert ganchos.puede_probar(_fila(estado="analizando"), GEN, [], 0.336, URL) == ganchos.MOTIVO_NO_LISTO
    assert ganchos.puede_probar(_fila({"frase": "x"}), [], [], None, URL) == ganchos.MOTIVO_VIEJO
    assert ganchos.puede_probar(_fila(), [], [], None, URL) == ganchos.MOTIVO_SIN_GANCHOS
    assert ganchos.puede_probar(_fila(), GEN, [], 0.336, None) == ganchos.MOTIVO_SIN_VIDEO
    assert ganchos.puede_probar(_fila(duracion=4.9), GEN, [], 0.336, URL) == ganchos.MOTIVO_CORTO
    assert ganchos.puede_probar(_fila(duracion=None), GEN, [], 0.336, URL) is None      # sin duración: se mide al bajar
    assert ganchos.puede_probar(_fila(), GEN, [{"estado": "armando"}], 0.336, URL) == ganchos.MOTIVO_TANDA_VIVA
    assert ganchos.puede_probar(_fila(), GEN, [{"estado": "lista"}, {"estado": "error"}], 0.336, URL) is None
    assert ganchos.puede_probar(_fila(), GEN, [], None, URL) == ganchos.MOTIVO_SIN_PRECIO


def test_tandas_agrupa_la_mas_nueva_primero_con_su_codigo():
    filas = [{"id": 4, "tanda": 1, "n": 2}, {"id": 9, "tanda": 2, "n": 1}, {"id": 3, "tanda": 1, "n": 1}]
    t = ganchos.tandas(filas)
    assert [x["tanda"] for x in t] == [2, 1]
    assert [(f["id"], f["codigo"]) for f in t[1]["filas"]] == [(3, "CV3"), (4, "CV4")]
    assert ganchos.tandas([]) == []


def test_documento_gancho_clip_original_audio_entero_y_texto():
    doc = ganchos.documento_gancho(CLIP, ORIGINAL, "¿Te duelen los pies?", "9:16", "no", "NO",
                                   analisis_id=5, gancho_id=12)
    v0, v1 = doc["pistas"][0]["clips"]
    assert (v0["material_id"], v0["inicio_ms"], v0["duracion_ms"]) == (7, 0, 3000)
    assert v0["recorte"] == {"desde_ms": 0, "hasta_ms": 3000} and v0["audio"]["volumen"] == 0.0
    assert (v1["material_id"], v1["inicio_ms"], v1["duracion_ms"]) == (9, 3000, 17000)
    assert v1["recorte"] == {"desde_ms": 3000, "hasta_ms": 20000} and v1["audio"]["volumen"] == 0.0
    pistas = {p["id"]: p for p in doc["pistas"]}
    assert "p_sonido" not in pistas                                   # ruling 1: el editor rehace p_sonido
    [audio] = pistas[ganchos.PISTA_ORIGINAL]["clips"]
    assert (audio["material_id"], audio["inicio_ms"], audio["duracion_ms"]) == (9, 0, 20000)
    assert audio["recorte"] == {"desde_ms": 0, "hasta_ms": 20000} and audio["audio"]["volumen"] == 1.0
    assert audio["rol_audio"] == "sonido" and pistas[ganchos.PISTA_ORIGINAL]["tipo"] == "audio"
    [texto] = pistas["p_texto"]["clips"]
    assert texto["texto"] == {"literal": "¿Te duelen los pies?"} and (texto["inicio_ms"], texto["duracion_ms"]) == (0, 3000)
    assert texto["estilo"]["fuente"] == borrador.ESTILO_HOOK["fuente"] and texto["transform"]["y"] == borrador.POS_HOOK["y"]
    assert doc["origen"] == {"tipo": "triple_whale", "pais": "NO", "analisis_id": 5, "gancho_id": 12}
    assert doc["idioma_base"] == "no" and doc["formato"] == "9:16" and set(doc["materiales"]) == {7, 9}
    assert vista_previa.destinos(doc) == ["no_NO"]
    resuelto = documento_mod.resolver(doc, "no", "NO")
    compilador.verificar_recortes(resuelto, {7: 3040, 9: 20000})      # nada pide más material del que hay


def test_documento_gancho_clip_corto_sin_audio_y_original_muy_corto():
    corto = dict(CLIP, duracion_ms=2500)
    doc = ganchos.documento_gancho(corto, dict(ORIGINAL, extra={"tiene_audio": False}), "Hola", "16:9", "es", "CO")
    v0, v1 = doc["pistas"][0]["clips"]
    assert v0["duracion_ms"] == 2500 and v1["inicio_ms"] == 2500 and v1["recorte"]["desde_ms"] == 2500
    assert ganchos.PISTA_ORIGINAL not in {p["id"] for p in doc["pistas"]}      # sin audio no hay pista de audio
    with pytest.raises(ganchos.GanchoError) as e:
        ganchos.documento_gancho(CLIP, dict(ORIGINAL, duracion_ms=3500), "Hola", "9:16", "es", "CO")
    assert str(e.value) == ganchos.MOTIVO_CORTO
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'triple_whale.ganchos'`).

- [ ] **Step 3: Implementar**

`triple_whale/ganchos.py`:

```python
"""Ganchos nuevos de un anuncio (spec 2026-10-09-tw-ganchos-y-copy §4): funciones puras, sin base, red ni ffmpeg.

- `codigo` / `codigo_en`: el código `CV<id>` de una variante, para el nombre del anuncio en Meta (la etapa 3 lo leerá en
  la sincronización para comparar v1 con v2).
- `ganchos_generables` y `puede_probar`: qué ganchos se pueden pedir y, si no se ofrece el botón, por qué (en palabras:
  constantes `N_`, quien las muestra hace `gettext` o `|traducir`).
- `documento_gancho`: la edición del editor: el clip nuevo de 0 a 3 s, el original desde el segundo 3 y el audio
  ENTERO del original en su propia pista (`PISTA_ORIGINAL`, no `p_sonido`: el editor rehace `p_sonido` como espejo
  de la principal en cada operación y los 3 primeros segundos quedarían mudos al primer cambio).
"""
import copy
import math
import re

import gastos
from final_edition import borrador, tipos
from final_edition import documento as documento_mod
from idiomas import N_
from providers import flowplus_modelos
from triple_whale.datos import VIVOS_GANCHO

MODELO = gastos.GANCHO_TW_MODELO
SEGUNDOS = gastos.GANCHO_TW_SEGUNDOS
MIN_ORIGINAL_S = 5               # spec §4.1: con menos no queda cuerpo que conservar después del gancho
MIN_CUERPO_MS = 1000             # el original tiene que durar al menos esto más allá del clip
PISTA_ORIGINAL = "p_original"
PAIS_DEFECTO = "CO"

MOTIVO_NO_LISTO = N_("El análisis todavía no está listo.")
MOTIVO_VIEJO = N_("Este análisis es de antes de los ganchos.")
MOTIVO_SIN_GANCHOS = N_("Este análisis no trae ganchos que se puedan generar.")
MOTIVO_SIN_VIDEO = N_("Sin video que se pueda bajar: los ganchos necesitan el video original.")
MOTIVO_CORTO = N_("El video es muy corto: dura menos de 5 s.")
MOTIVO_TANDA_VIVA = N_("Hay una tanda en curso: espera a que termine.")
MOTIVO_SIN_PRECIO = gastos.SIN_PRECIO
ERROR_BAJAR = N_("No se pudo bajar el video original.")
ERROR_NO_MP4 = N_("El video original no es un mp4: no se puede editar.")
ERROR_FOTOGRAMA = N_("No se pudo sacar el fotograma de arranque.")

_RE_CODIGO = re.compile(r"\bCV(\d+)\b", re.IGNORECASE)
_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_TRANSFORM = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}


class GanchoError(Exception):
    """Un motivo para la persona: el mensaje es un msgid (`N_`) y quien lo guarda o lo muestra hace `gettext`."""


def codigo(gancho_id):
    return f"CV{int(gancho_id)}"


def codigo_en(nombre):
    """El id de la variante cuyo código aparece en el nombre de un anuncio («… · CV12» → 12), o None."""
    m = _RE_CODIGO.search(str(nombre or ""))
    return int(m.group(1)) if m else None


def _proporcion(ancho, alto):
    try:
        r = float(ancho) / float(alto)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return r if r > 0 and math.isfinite(r) else None


def _mas_cercano(opciones, ancho, alto, defecto="9:16"):
    """La opción «a:b» cuya proporción está más cerca (en escala logarítmica) de ancho/alto."""
    r = _proporcion(ancho, alto)
    if r is None:
        return defecto

    def distancia(f):
        a, b = (float(x) for x in f.split(":"))
        return abs(math.log((a / b) / r))
    return min(opciones, key=distancia)


def formato_cercano(ancho, alto):
    """El formato del documento (`documento.FORMATOS`) más cercano al original; sin medidas, 9:16."""
    return _mas_cercano(tuple(documento_mod.FORMATOS), ancho, alto)


def aspecto_kling(ancho, alto):
    """El formato de Kling más cercano al original (la sesión de Crear lo pide; en imagen a video manda la imagen)."""
    return _mas_cercano(tuple(flowplus_modelos.VIDEO[MODELO]["formatos"]), ancho, alto)


def destino(pais_tienda, pais_proyecto):
    """(idioma, país) de la final (spec §4.6.2): el país de la tienda del análisis si está en `tipos.PAISES`; si no,
    el del proyecto; si no, Colombia. El idioma es el de ese país (decisión B)."""
    for pais in (pais_tienda, pais_proyecto):
        p = str(pais or "").upper()
        if p in tipos.PAISES:
            return tipos.PAISES[p]["idioma"], p
    return tipos.PAISES[PAIS_DEFECTO]["idioma"], PAIS_DEFECTO


def ganchos_generables(resultado):
    """Los ganchos del análisis que se pueden pedir: con texto y prompt y SIN cifras que no están en los datos (spec
    §3.2: una cifra inventada no entra a un video ni al precio). `n` es su posición (1–3) en la lista de Claude."""
    r = resultado if isinstance(resultado, dict) else {}
    salida = []
    for i, g in enumerate((r.get("ganchos") or [])[:3], start=1):
        if not isinstance(g, dict) or g.get("cifras_sin_dato") or not g.get("texto") or not g.get("prompt"):
            continue
        salida.append({"n": i, "texto": g["texto"], "prompt": g["prompt"], "fotograma_s": g.get("fotograma_s")})
    return salida


def puede_probar(fila, generables, filas_ganchos, precio_usd, url_video):
    """None si el botón se ofrece; si no, el motivo (spec §4.1), en este orden: el análisis no está listo, es de antes
    de los ganchos, no trae ninguno generable, no hay video que bajar (`url_video` = `mejorar._url_voz(foto)`), el
    video conocido dura menos de MIN_ORIGINAL_S, hay una tanda viva, o no hay precio."""
    f = fila or {}
    r = f.get("resultado") or {}
    if f.get("estado") != "lista":
        return MOTIVO_NO_LISTO
    if "ganchos" not in r:
        return MOTIVO_VIEJO
    if not generables:
        return MOTIVO_SIN_GANCHOS
    if not url_video:
        return MOTIVO_SIN_VIDEO
    try:
        duracion = float(((f.get("foto") or {}).get("creativo") or {}).get("duracion_s"))
    except (TypeError, ValueError):
        duracion = None
    if duracion is not None and duracion < MIN_ORIGINAL_S:
        return MOTIVO_CORTO
    if any((g or {}).get("estado") in VIVOS_GANCHO for g in filas_ganchos or []):
        return MOTIVO_TANDA_VIVA
    if precio_usd is None:
        return MOTIVO_SIN_PRECIO
    return None


def tandas(filas):
    """[{"tanda", "filas"}], la más nueva primero y cada una por `n`; cada fila suma su `codigo`."""
    salida = []
    for f in sorted(filas or [], key=lambda x: (-int(x["tanda"]), int(x["n"]))):
        if not salida or salida[-1]["tanda"] != f["tanda"]:
            salida.append({"tanda": f["tanda"], "filas": []})
        salida[-1]["filas"].append(dict(f, codigo=codigo(f["id"])))
    return salida


def _pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


def documento_gancho(clip, original, texto, formato, idioma, pais, analisis_id=None, gancho_id=None):
    """La edición de una variante (spec §4.6.2, ruling 1). `clip` y `original` son filas de `material` (`id`,
    `duracion_ms`, `extra.tiene_audio`). g = min(clip, 3 000 ms):
      - principal: `v0` el clip de 0 a g y `v1` el original con recorte [g, fin] desde g, los dos mudos;
      - `PISTA_ORIGINAL`: el audio del original ENTERO desde 0 (rol sonido, volumen 1): en el segundo g se ven y se
        oyen los mismos segundos del original y la voz sigue en sincronía. Sin audio en el original, no va;
      - `p_texto`: el texto del gancho (literal) de 0 a g, con el estilo y la posición del gancho del borrador.
    GanchoError(MOTIVO_CORTO) si al original no le queda al menos MIN_CUERPO_MS después del clip."""
    g = min(int(clip["duracion_ms"]), SEGUNDOS * 1000)
    total = int(original["duracion_ms"])
    if g <= 0 or total - g < MIN_CUERPO_MS:
        raise GanchoError(MOTIVO_CORTO)
    mudo = dict(_AUDIO, volumen=0.0)
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)
    doc["pistas"][0]["clips"] = [
        {"id": "v0", "inicio_ms": 0, "duracion_ms": g, "material_id": int(clip["id"]),
         "recorte": {"desde_ms": 0, "hasta_ms": g}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
         "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(mudo)},
        {"id": "v1", "inicio_ms": g, "duracion_ms": total - g, "material_id": int(original["id"]),
         "recorte": {"desde_ms": g, "hasta_ms": total}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
         "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(mudo)}]
    if (original.get("extra") or {}).get("tiene_audio"):
        doc["pistas"].append(_pista(PISTA_ORIGINAL, "audio", [
            {"id": "o0", "inicio_ms": 0, "duracion_ms": total, "material_id": int(original["id"]),
             "rol_audio": "sonido", "recorte": {"desde_ms": 0, "hasta_ms": total}, "velocidad": 1.0,
             "audio": dict(_AUDIO)}]))
    doc["pistas"].append(_pista("p_texto", "texto", [
        {"id": "t_gancho", "inicio_ms": 0, "duracion_ms": g, "material_id": None, "texto": {"literal": texto},
         "estilo": copy.deepcopy(borrador.ESTILO_HOOK), "transform": dict(borrador.POS_HOOK), "keyframes": [],
         "animacion": None}]))
    doc["miniatura_ms"] = min(1000, g // 2)
    doc["origen"] = {"tipo": "triple_whale", "pais": pais, "analisis_id": analisis_id, "gancho_id": gancho_id}
    return documento_mod.validar(doc)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos.py`
Expected: PASS. Si `documento_mod.validar` rechaza alguna clave del clip, el mensaje dice cuál: compara con el clip
de `final_edition/edicion_clon.py:documento` (es el mismo molde) y ajusta solo esa clave.

- [ ] **Step 5: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py pendientes`
Traduce en `translations/en/LC_MESSAGES/messages.po` (msgstr de cada uno; «precio no disponible» ya existe):

| msgid | msgstr |
|---|---|
| El análisis todavía no está listo. | The analysis isn't ready yet. |
| Este análisis es de antes de los ganchos. | This analysis is from before hooks. |
| Este análisis no trae ganchos que se puedan generar. | This analysis has no hooks that can be generated. |
| Sin video que se pueda bajar: los ganchos necesitan el video original. | No video that can be downloaded: hooks need the original video. |
| El video es muy corto: dura menos de 5 s. | The video is too short: it lasts less than 5 s. |
| Hay una tanda en curso: espera a que termine. | A batch is in progress: wait for it to finish. |
| No se pudo bajar el video original. | Couldn't download the original video. |
| El video original no es un mp4: no se puede editar. | The original video isn't an mp4: it can't be edited. |
| No se pudo sacar el fotograma de arranque. | Couldn't extract the starting frame. |

Run: `venv/bin/python3 catalogo_i18n.py compilar && venv/bin/python3 -m pytest -q tests/test_i18n_catalogo.py`
Expected: PASS (`pendientes` ya no lista nada).

- [ ] **Step 6: Commit**

```bash
git add triple_whale/ganchos.py tests/test_tw_ganchos.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Triple Whale ganchos: funciones puras (código CV, formato, destino, documento del editor y por qué no)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: El editor produce sin navegador y muestra el original de Triple Whale

**Files:**
- Modify: `final_edition/rutas_editor.py` (extraer el final de `producir`, líneas ~226-246)
- Modify: `final_edition/biblioteca.py:54` (`ORIGENES_BIBLIOTECA`)
- Modify: `.claude/skills/editor/SKILL.md` (un párrafo al final)
- Test: `tests/test_editor_encolar_producciones.py` (nuevo), `tests/test_biblioteca_editor.py` (una prueba al final)

**Interfaces:**
- Consumes: `ediciones.versionar`, `creative_flow.crear_final`, `tareas.edicion.job_id_producir`,
  `tareas.edicion.ETAPAS_EDICION`, `final_edition.estimar.segundos` (existentes).
- Produces: `final_edition.rutas_editor.encolar_producciones(cliente, edicion_id, ed, version, destinos) ->
  list[{"destino", "final_id", "encolada"}]` (`ed` = la edición de `ediciones.cargar`, con `cf_id` y `documento`;
  `version` = lo que devuelve `ediciones.versionar`; `destinos` = `["<idioma>_<PAIS>", …]` ya revisados);
  `"triple_whale"` en `biblioteca.ORIGENES_BIBLIOTECA`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_editor_encolar_producciones.py`:

```python
"""El final de «Producir» como función compartida (spec 2026-10-09 §4.6.4): la ruta del editor y la tarea de los
ganchos encolan igual. Las pruebas de la ruta (tests/test_rutas_editor.py) no se tocan y siguen en verde."""
from tests.test_rutas_editor import _edicion_con_pieza, dashboard, encolados  # noqa: F401  (fixtures)


def test_encolar_producciones_crea_la_final_y_encola_el_render(dashboard, encolados):  # noqa: F811
    import creative_flow
    import ediciones
    from final_edition import rutas_editor
    ed, cf = _edicion_con_pieza()
    version = ediciones.versionar("acme", ed["id"], motivo="producir")
    out = rutas_editor.encolar_producciones("acme", ed["id"], ed, version, ["es_CO"])
    assert out == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": True}]
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_producir"]
    assert args[0] == f"acme__ed{ed['id']}__es_CO__producir"
    assert args[2] == {"cliente": "acme", "edicion_id": ed["id"], "version_id": version["id"],
                       "final_id": f"{cf}__es_CO", "idioma": "es", "pais": "CO"}
    assert kw["max_intentos"] == 1 and kw["cliente"] == "acme" and kw["duracion_estimada"] >= 1
    assert creative_flow.final_por_legado("acme", f"{cf}__es_CO")["estado"] == "generando"


def test_encolar_producciones_no_repite_un_render_vivo(dashboard, encolados, monkeypatch):  # noqa: F811
    import creative_flow
    import ediciones
    import trabajos
    from final_edition import rutas_editor
    ed, cf = _edicion_con_pieza()
    version = ediciones.versionar("acme", ed["id"], motivo="producir")
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: job_id.endswith("__producir"))
    out = rutas_editor.encolar_producciones("acme", ed["id"], ed, version, ["es_CO"])
    assert out == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": False}]
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]
    assert creative_flow.final_por_legado("acme", f"{cf}__es_CO") is None        # ni siquiera reinicia la final
```

Al final de `tests/test_biblioteca_editor.py`:

```python
def test_listar_incluye_el_original_de_un_anuncio_de_triple_whale(entorno):
    """Spec 2026-10-09 §4.4.2: el video original que bajan los ganchos queda en «Medios» y se puede reusar."""
    import materiales
    m = materiales.registrar("acme", tipo="video", origen="triple_whale", url="https://r2/o.mp4", hash="h-tw",
                             bytes=1, duracion_ms=20000, extra={"nombre": "Anuncio p1", "ad_id": "p1"})
    assert m["id"] in {x["id"] for x in entorno.listar("acme")["materiales"]}
    assert m["id"] not in {x["id"] for x in entorno.listar("otro")["materiales"]}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_editor_encolar_producciones.py tests/test_biblioteca_editor.py::test_listar_incluye_el_original_de_un_anuncio_de_triple_whale`
Expected: FAIL (`AttributeError: module 'final_edition.rutas_editor' has no attribute 'encolar_producciones'`; el
material no aparece).

- [ ] **Step 3: Implementar**

En `final_edition/rutas_editor.py`, antes de `producir`:

```python
def encolar_producciones(cliente, edicion_id, ed, version, destinos):
    """El final de «Producir» (capa 4a §6), compartido con la tarea de los ganchos de Triple Whale (spec 2026-10-09
    §4.6.4), que arma y produce sin navegador: por destino, si su render no está corriendo, crea (o reinicia) la final
    y encola `edicion_producir` de la versión YA congelada (`version`, de `ediciones.versionar`). Gratis: se produce
    con materiales ya pagados. Quien llama ya revisó los destinos (`verificar_recortes`) y congeló la versión.
    Devuelve [{"destino", "final_id", "encolada"}]."""
    segundos = estimar.segundos(ed["documento"])
    producidas = []
    for d in destinos:
        idioma, pais = d.split("_")
        job_id = tareas_edicion.job_id_producir(cliente, edicion_id, idioma, pais)
        if trabajos.en_curso(job_id):
            producidas.append({"destino": d, "final_id": f"{ed['cf_id']}__{d}", "encolada": False})
            continue
        final_id = creative_flow.crear_final(cliente, ed["cf_id"], idioma, pais)
        encolada = trabajos.encolar(job_id, "edicion_producir",
                                    {"cliente": cliente, "edicion_id": edicion_id, "version_id": version["id"],
                                     "final_id": final_id, "idioma": idioma, "pais": pais},
                                    duracion_estimada=segundos, etapas=list(tareas_edicion.ETAPAS_EDICION),
                                    cliente=cliente, max_intentos=1)
        producidas.append({"destino": d, "final_id": final_id, "encolada": bool(encolada)})
    return producidas
```

Y en `producir`, todo lo que va desde `segundos = estimar.segundos(doc)` hasta el `for` inclusive se reemplaza por una
línea (el `return jsonify(...)` de después queda igual):

```python
    producidas = encolar_producciones(cliente, edicion_id, ed, version, destinos)
```

En `final_edition/biblioteca.py:54` (el comentario de arriba suma la línea «Spec 2026-10-09 (ganchos de Triple
Whale): «triple_whale», el video original de un anuncio, bajado una vez y deduplicado por hash.»):

```python
ORIGENES_BIBLIOTECA = ("subida", "crear", "musica", "voz", "marca", "grabacion", "locucion", "triple_whale")
```

- [ ] **Step 4: Escribir el párrafo de la skill**

Al final de `.claude/skills/editor/SKILL.md`:

```markdown
**Producir sin navegador (2026-10-09, ganchos de Triple Whale, spec `2026-10-09-tw-ganchos-y-copy-design.md` §4.6):**
`rutas_editor.encolar_producciones(cliente, edicion_id, ed, version, destinos)` is the tail of `producir` (per destino:
skip a live render, `creative_flow.crear_final`, `edicion_producir` of the FROZEN version, `max_intentos=1`); the route
and `tareas/triple_whale.tw_gancho_armar` share it, so a task that builds a document produces exactly as the button
does, after its own `verificar_recortes` and `versionar` (the route keeps its `version_n` CAS and its 409). Materials
with origen `triple_whale` (an ad's original video, downloaded once and deduped by hash) are in `ORIGENES_BIBLIOTECA`:
they show in «Medios» and can be reused, but they are not in `ORIGENES_BORRABLES`.
```

- [ ] **Step 5: Correr y ver que pasan, también las de la ruta sin tocarlas**

Run: `venv/bin/python3 -m pytest -q tests/test_editor_encolar_producciones.py tests/test_rutas_editor.py tests/test_biblioteca_editor.py tests/test_guia_agentes.py`
Expected: PASS (las 15 pruebas `test_producir_*` de `tests/test_rutas_editor.py` sin cambios).

- [ ] **Step 6: Commit**

```bash
git add final_edition/rutas_editor.py final_edition/biblioteca.py .claude/skills/editor/SKILL.md tests/test_editor_encolar_producciones.py tests/test_biblioteca_editor.py
git commit -m "Editor: el final de Producir como función compartida y el original de Triple Whale en Medios

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: El worker: preparar, vigilar y armar

**Files:**
- Modify: `tareas/triple_whale.py` (docstring, imports, sección nueva al final)
- Modify: `tareas/__init__.py` (`TIPOS_EXENTOS_DE_COBRO`)
- Modify: `worker.py` (`PERIODICAS`, después de `("cadena_vigilar", 60)`)
- Modify: `tests/test_tareas_swap.py` (lista del registro), `tests/test_tareas_decidir.py` (lista de periódicas)
- Test: `tests/test_tw_ganchos_tareas.py` (nuevo)
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`

**Interfaces:**
- Consumes: Task 1 (`datos.crear_tanda`, `mover`, `actualizar_gancho`, `ganchos_de_analisis`, `ganchos_vivos`,
  `gancho`), Task 2 (`mejorar.segundo_fotograma`, `mejorar._url_voz`, `mejorar.es_mp4`), Task 3 (`ganchos.*`),
  Task 4 (`rutas_editor.encolar_producciones`); `flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=)` (devuelve
  falso si no encoló, lanza `SaldoInsuficiente`), `flowplus_lanzar.job_id(cliente, cf_id)`, `tareas.cadena.VIVOS_CREAR`,
  `biblioteca.materializar_pieza(cliente, cf_id, carpeta)`, `materiales.subir/buscar_hash/hash_archivo`,
  `insumos.job_id_proxy`, `cortes.ffmpeg/ffprobe_json/duracion`, `encuadre.medidas_visibles`, `mezcla.tiene_audio`,
  `r2_uploader.upload_image`, `conectores.url.descargar_archivo`.
- Produces (en `tareas.triple_whale`): `BASE_DIR`, `TIPO_GANCHOS_PREPARAR = "tw_ganchos_preparar"`,
  `TIPO_GANCHOS_VIGILAR = "tw_ganchos_vigilar"`, `TIPO_GANCHO_ARMAR = "tw_gancho_armar"`, `PRIORIDAD_GANCHOS = 3`,
  `GRACIA_S = 120`, `ETAPAS_GANCHOS`, `ETAPAS_ARMAR`, `job_id_preparar(cliente, analisis_id, tanda)` →
  `f"{cliente}__tw_ganchos_{aid}_t{tanda}"`, `job_id_armar(cliente, gancho_id)` → `f"{cliente}__tw_gancho_{gid}_armar"`,
  `encolar_preparar(cliente, analisis_id, tanda) -> bool`, `tw_ganchos_preparar(tarea)`, `vigilar_gancho(cliente, g,
  sesiones)`, `tw_ganchos_vigilar(tarea)`, `tw_gancho_armar(tarea)`, y los auxiliares `_fotograma_en(ruta, segundo,
  destino)`, `_bajar_original(foto, carpeta)`, `_material_original(cliente, ruta, foto)`, `_texto_error(e)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_tw_ganchos_tareas.py`:

```python
"""Los ganchos en el worker (spec 2026-10-09 §4.4–§4.6): preparar, vigilar y armar, con la descarga, ffprobe, ffmpeg y
R2 simulados. Kling no se llama nunca: `flowplus_lanzar.lanzar` solo encola en la base de prueba."""
import os
import shutil
import subprocess

import pytest
import sqlalchemy as sa

import creative_flow
import db
import ediciones
import flowplus_lanzar
import gastos
import materiales
import proyectos
from tests.test_tw_mejorar import GANCHOS, respuesta
from triple_whale import datos, ganchos, mejorar

FOTO = {"nombre": "Anuncio p1", "ad_id": "p1", "canal": "facebook-ads",
        "creativo": {"tipo": "video", "video_url": "https://files.triplewhale.com/v/p1.mp4",
                     "imagen_url": "https://files.triplewhale.com/t/p1.jpg", "duracion_s": 20.0}}
FFPROBE = {"format": {"duration": "20.0"},
           "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}]}
GANCHOS_GEN = {"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0}


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    from conectores import url as conector_url
    from final_edition import cortes
    from storage import r2_uploader
    from tareas import triple_whale as t
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(t, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    bajadas = []

    def _bajar(url, ruta, **_k):
        bajadas.append(url)
        with open(ruta, "wb") as f:
            f.write(b"mp4 de prueba " + url.encode())
        return 20
    monkeypatch.setattr(conector_url, "descargar_archivo", _bajar)
    monkeypatch.setattr(mejorar, "es_mp4", lambda ruta: True)
    probe = {"info": FFPROBE}
    monkeypatch.setattr(cortes, "ffprobe_json", lambda ruta: probe["info"])
    monkeypatch.setattr(r2_uploader, "upload_file", lambda local, key, ct: f"https://r2.test/{key}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda local, key: f"https://r2.test/{key}")

    def _fotograma(ruta, segundo, destino):
        with open(destino, "wb") as f:
            f.write(b"jpg")
        return destino
    monkeypatch.setattr(t, "_fotograma_en", _fotograma)
    aid = datos.crear_analisis("acme", None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", FOTO)
    datos.actualizar_analisis(aid, estado="lista",
                              resultado=mejorar.parsear(respuesta(ganchos=GANCHOS), "datos", duracion_s=20.0))
    generables = ganchos.ganchos_generables(datos.analisis_anuncio("acme", aid)["resultado"])
    filas = datos.crear_tanda("acme", aid, generables, pedido_por="admin")
    return {"t": t, "aid": aid, "filas": filas, "bajadas": bajadas, "tmp": tmp_path, "probe": probe}


def _preparar(e, tarea_id=1):
    return e["t"].tw_ganchos_preparar({"id": tarea_id, "job_id": f"acme__tw_ganchos_{e['aid']}_t1",
                                       "payload": {"cliente": "acme", "analisis_id": e["aid"], "tanda": 1}})


def _vigilar(e):
    return e["t"].tw_ganchos_vigilar({"id": 99, "payload": {}})


def _cola(tipo):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.tarea).where(db.tarea.c.tipo == tipo))]


def _materiales_tw():
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(db.material).where(db.material.c.origen == "triple_whale"))]


def _envejecer(gid):
    with db.conectar() as con:
        con.execute(db.tw_gancho.update().where(db.tw_gancho.c.id == gid).values(actualizado_en="2026-01-01T00:00:00"))


def _filas(e):
    return datos.ganchos_de_analisis("acme", e["aid"])


# ------------------------------------------------------------------------------------------------- preparar ---

def test_preparar_lanza_un_clip_de_kling_por_gancho(entorno):
    msg = _preparar(entorno)
    filas = _filas(entorno)
    assert [f["estado"] for f in filas] == ["generando"] * 3 and all(f["cf_id"] for f in filas)
    sesiones = creative_flow.cargar("acme")
    [mat] = _materiales_tw()
    for f in filas:
        e = sesiones[f["cf_id"]]
        assert e["modelo"] == "kling_o3_pro" and e["duracion_objetivo"] == 3 and e["con_sonido"] is False
        assert e["imagen_inicial"] == f["frame_url"] == f"https://r2.test/clientes/acme/triple_whale/ganchos/{f['id']}.jpg"
        assert e["aspect_ratio"] == "9:16" and e["estado"] == "video_generando" and e["calidad"] == "final"
        assert e["referencias"][0]["titulo"] == f"CV{f['id']}" and e["elementos"] == []
        assert e["tw_gancho"] == {"gancho_id": f["id"], "analisis_id": entorno["aid"], "original_hash": mat["hash"]}
        assert e["prompt_relleno"] == f["prompt"] and e["accion_central"].startswith(f"Gancho {f['n']} · Anuncio p1")
        assert f["job_id"] == f"acme__{f['cf_id']}__creative_flow"
        # el precio que reserva cada clip es el mismo que vio la persona
        assert flowplus_lanzar.costo_estimado(e) == gastos.estimar_ganchos_tw(1)["usd"]
    clips = _cola("flowplus_video")
    assert len(clips) == 3 and {x["prioridad"] for x in clips} == {3} and {x["max_intentos"] for x in clips} == {1}
    assert mat["duracion_ms"] == 20000 and (mat["ancho"], mat["alto"]) == (1080, 1920)
    assert mat["url"] == f"https://r2.test/clientes/acme/materiales/{mat['hash']}.mp4"
    assert mat["extra"]["ad_id"] == "p1" and mat["extra"]["tiene_audio"] is True and mat["extra"]["nombre"] == "Anuncio p1"
    assert len(_cola("edicion_proxy")) == 1
    assert entorno["bajadas"] == ["https://files.triplewhale.com/v/p1.mp4"]
    assert not os.path.exists(os.path.join(str(entorno["tmp"]), "salidas", "acme", "tw_ganchos", f"{entorno['aid']}_t1"))
    assert "3" in msg


def test_preparar_no_relanza_una_fila_que_ya_tiene_su_clip(entorno):
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    # el proceso murió entre crear la sesión y moverla: la fila tiene cf_id y sigue en preparando
    assert datos.mover(f1["id"], "generando", "preparando")
    assert "No había" in _preparar(entorno, tarea_id=2)
    assert len(_cola("flowplus_video")) == 3 and len(entorno["bajadas"]) == 1


def test_sin_saldo_a_mitad_las_que_faltan_quedan_en_error_y_las_lanzadas_siguen(entorno):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    una = libro.precio_milesimas(0.336, libro.margen_precio("acme"))
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", una + 5, "ajuste", usuario="admin", detalle="prueba")
    _preparar(entorno)
    f1, f2, f3 = _filas(entorno)
    assert f1["estado"] == "generando"
    assert f2["estado"] == f3["estado"] == "error" and "Saldo insuficiente" in f2["error"] and f3["error"] == f2["error"]
    assert f3["cf_id"] is None and len(_cola("flowplus_video")) == 1


def test_un_original_que_no_se_puede_bajar_deja_la_tanda_en_error_en_palabras(entorno, monkeypatch):
    from conectores import url as conector_url
    from conectores.base import ErrorConector

    def _cae(url, ruta, **_k):
        raise ErrorConector("403 en https://files.triplewhale.com/v/p1.mp4?token=secreto")
    monkeypatch.setattr(conector_url, "descargar_archivo", _cae)
    with pytest.raises(RuntimeError):
        _preparar(entorno)
    filas = _filas(entorno)
    assert {f["estado"] for f in filas} == {"error"}
    assert filas[0]["error"] == "No se pudo bajar el video original." and "secreto" not in filas[0]["error"]
    assert _cola("flowplus_video") == [] and creative_flow.cargar("acme") == {}


def test_un_original_de_menos_de_cinco_segundos_no_lanza_nada(entorno):
    entorno["probe"]["info"] = dict(FFPROBE, format={"duration": "4.0"})
    with pytest.raises(RuntimeError):
        _preparar(entorno)
    assert {f["error"] for f in _filas(entorno)} == {"El video es muy corto: dura menos de 5 s."}
    assert _cola("flowplus_video") == []


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")
def test_fotograma_en_saca_un_jpg_del_segundo_pedido(tmp_path):
    from final_edition import cortes
    from tareas import triple_whale as t
    video = str(tmp_path / "v.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=320x240:rate=25", "-t", "3", "-pix_fmt", "yuv420p", video], check=True)
    jpg = t._fotograma_en(video, 1.5, str(tmp_path / "f.jpg"))
    with open(jpg, "rb") as f:
        assert f.read(2) == b"\xff\xd8"                                       # un JPEG de verdad
    with pytest.raises(ganchos.GanchoError):
        t._fotograma_en(video, 30, str(tmp_path / "g.jpg"))                   # más allá del final: no hay cuadro


# ------------------------------------------------------------------------------------------------- vigilar ---

def test_vigilar_lleva_un_clip_listo_a_armar_una_sola_vez(entorno):
    _preparar(entorno)
    f1, f2, f3 = _filas(entorno)
    creative_flow.actualizar("acme", f1["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")
    creative_flow.actualizar("acme", f2["cf_id"], estado="error", error="Kling: contenido sensible")
    _vigilar(entorno)
    _vigilar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == "armando" and g1["job_id"] == f"acme__tw_gancho_{g1['id']}_armar"
    assert g2["estado"] == "error" and g2["error"] == "Kling: contenido sensible"
    assert g3["estado"] == "generando"                                       # sigue generando: nada cambia
    [armar] = _cola("tw_gancho_armar")
    assert armar["payload"] == {"cliente": "acme", "gancho_id": g1["id"]}
    assert armar["max_intentos"] == 2 and armar["prioridad"] == 1 and armar["job_id"] == g1["job_id"]


def test_vigilar_una_sesion_borrada_es_un_error(entorno):
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    creative_flow.eliminar("acme", f1["cf_id"])
    _vigilar(entorno)
    g1 = _filas(entorno)[0]
    assert g1["estado"] == "error" and g1["error"] == "El clip de este gancho ya no está en Crear."


def test_vigilar_cierra_lo_producido(entorno):
    _preparar(entorno)
    f1, f2, _ = _filas(entorno)
    fin1 = creative_flow.crear_final("acme", f1["cf_id"], "es", "CO")
    fin2 = creative_flow.crear_final("acme", f2["cf_id"], "es", "CO")
    assert datos.mover(f1["id"], "generando", "produciendo", final_id=fin1)
    assert datos.mover(f2["id"], "generando", "produciendo", final_id=fin2)
    _vigilar(entorno)
    assert [g["estado"] for g in _filas(entorno)[:2]] == ["produciendo", "produciendo"]     # siguen renderizando
    creative_flow.actualizar_final("acme", fin1, estado="listo", url_video="https://r2.test/final1.mp4")
    creative_flow.actualizar_final("acme", fin2, estado="error", error="ffmpeg falló")
    _vigilar(entorno)
    g1, g2, _ = _filas(entorno)
    assert g1["estado"] == "lista" and g1["url_final"] == "https://r2.test/final1.mp4"
    assert g2["estado"] == "error" and g2["error"] == "ffmpeg falló"


def test_vigilar_cierra_una_preparacion_cortada_solo_despues_de_la_gracia(entorno):
    f1, f2, f3 = entorno["filas"]
    vivo = entorno["t"].job_id_preparar("acme", entorno["aid"], 1)
    for f in (f1, f2, f3):
        datos.actualizar_gancho(f["id"], job_id=vivo)
    _envejecer(f1["id"])
    _envejecer(f2["id"])                                       # f3: recién tocada, dentro de la gracia
    _vigilar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == g2["estado"] == "error" and g1["error"] == "La preparación se cortó antes de terminar."
    assert g3["estado"] == "preparando"
    # con la preparación viva en la cola, ni una vieja se toca
    otra = datos.crear_tanda("acme", datos.crear_analisis("acme", None, "facebook-ads", "p9", "2026-09-01",
                                                           "2026-09-30", "USD", FOTO), [GANCHOS_GEN])
    assert entorno["t"].encolar_preparar("acme", otra[0]["analisis_id"], 1)
    datos.actualizar_gancho(otra[0]["id"], job_id=entorno["t"].job_id_preparar("acme", otra[0]["analisis_id"], 1))
    _envejecer(otra[0]["id"])
    _vigilar(entorno)
    assert datos.gancho("acme", otra[0]["id"])["estado"] == "preparando"


def test_una_variante_rota_no_frena_a_las_demas(entorno, monkeypatch):
    _preparar(entorno)
    f1, f2, _ = _filas(entorno)
    assert datos.mover(f1["id"], "generando", "produciendo", final_id="cf_x__es_CO")
    creative_flow.actualizar("acme", f2["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")

    def _rota(cliente, final_id):
        raise RuntimeError("base caída")
    monkeypatch.setattr(entorno["t"].creative_flow, "final_por_legado", _rota)
    _vigilar(entorno)
    g1, g2, _ = _filas(entorno)
    assert g1["estado"] == "produciendo" and g2["estado"] == "armando"


# --------------------------------------------------------------------------------------------------- armar ---

def _listo_para_armar(entorno, monkeypatch, clip_ms=3040):
    from final_edition import biblioteca
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    creative_flow.actualizar("acme", f1["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")
    _vigilar(entorno)
    clip = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clip.mp4", hash="h-clip",
                                bytes=10, duracion_ms=clip_ms, ancho=1080, alto=1920,
                                extra={"tiene_audio": False, "cf_id": f1["cf_id"]})
    pedidos = []
    monkeypatch.setattr(biblioteca, "materializar_pieza",
                        lambda c, cf, carpeta: pedidos.append(cf) or clip)
    return datos.gancho("acme", f1["id"]), clip, pedidos


def _armar(entorno, gid, intentos=1):
    return entorno["t"].tw_gancho_armar({"id": 7, "intentos": intentos, "max_intentos": 2,
                                         "job_id": f"acme__tw_gancho_{gid}_armar",
                                         "payload": {"cliente": "acme", "gancho_id": gid}})


def test_armar_hace_la_edicion_y_encola_el_render(entorno, monkeypatch):
    g, clip, pedidos = _listo_para_armar(entorno, monkeypatch)
    _armar(entorno, g["id"])
    assert pedidos == [g["cf_id"]]
    g = datos.gancho("acme", g["id"])
    assert g["estado"] == "produciendo" and g["final_id"] == f"{g['cf_id']}__es_CO"
    assert g["job_id"] == f"acme__ed{g['edicion_id']}__es_CO__producir"
    ed = ediciones.cargar("acme", g["edicion_id"])
    assert ed["nombre"] == f"Anuncio p1 · CV{g['id']}" and ed["cf_id"] == g["cf_id"] and ed["creada_por"] == "triple_whale"
    doc = ed["documento"]
    [original] = _materiales_tw()
    v0, v1 = doc["pistas"][0]["clips"]
    assert (v0["material_id"], v0["inicio_ms"], v0["duracion_ms"]) == (clip["id"], 0, 3000)
    assert (v1["material_id"], v1["inicio_ms"], v1["recorte"]) == (original["id"], 3000, {"desde_ms": 3000, "hasta_ms": 20000})
    [audio] = [p for p in doc["pistas"] if p["id"] == ganchos.PISTA_ORIGINAL][0]["clips"]
    assert audio["recorte"] == {"desde_ms": 0, "hasta_ms": 20000} and audio["audio"]["volumen"] == 1.0
    [texto] = [p for p in doc["pistas"] if p["id"] == "p_texto"][0]["clips"]
    assert texto["texto"] == {"literal": GANCHOS[0]["texto"]}
    assert doc["origen"] == {"tipo": "triple_whale", "pais": "CO", "analisis_id": entorno["aid"], "gancho_id": g["id"]}
    [render] = _cola("edicion_producir")
    assert render["payload"]["final_id"] == g["final_id"] and render["max_intentos"] == 1
    assert creative_flow.final_por_legado("acme", g["final_id"])["estado"] == "generando"
    assert len(entorno["bajadas"]) == 1                                  # el original no se volvió a bajar


def test_armar_produce_en_el_pais_de_la_tienda_del_analisis(entorno, monkeypatch):
    import triple_whale_tiendas
    tid = triple_whale_tiendas.agregar("acme", "tw_x", "acme-norge.myshopify.com", "NO", moneda="USD")
    datos.actualizar_analisis(entorno["aid"], tienda_id=tid)
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)
    _armar(entorno, g["id"])
    g = datos.gancho("acme", g["id"])
    assert g["final_id"].endswith("__no_NO") and ediciones.cargar("acme", g["edicion_id"])["documento"]["idioma_base"] == "no"


def test_armar_vuelve_a_bajar_el_original_si_ya_no_esta(entorno, monkeypatch):
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)
    entry = creative_flow.cargar("acme")[g["cf_id"]]
    creative_flow.actualizar("acme", g["cf_id"], tw_gancho=dict(entry["tw_gancho"], original_hash="no-existe"))
    _armar(entorno, g["id"])
    assert len(entorno["bajadas"]) == 2 and datos.gancho("acme", g["id"])["estado"] == "produciendo"


def test_armar_que_falla_reintenta_y_en_el_ultimo_intento_lo_dice(entorno, monkeypatch):
    from final_edition import biblioteca
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)

    def _cae(c, cf, carpeta):
        raise RuntimeError("/srv/creatv/salidas/x.mp4 no existe")
    monkeypatch.setattr(biblioteca, "materializar_pieza", _cae)
    with pytest.raises(RuntimeError):
        _armar(entorno, g["id"], intentos=1)
    assert datos.gancho("acme", g["id"])["estado"] == "armando"            # queda el segundo intento
    with pytest.raises(RuntimeError):
        _armar(entorno, g["id"], intentos=2)
    g = datos.gancho("acme", g["id"])
    assert g["estado"] == "error" and "RuntimeError" in g["error"] and "/srv" not in g["error"]
    assert _cola("edicion_producir") == []


def test_armar_una_fila_que_ya_no_esta_armando_no_hace_nada(entorno, monkeypatch):
    g, _clip, pedidos = _listo_para_armar(entorno, monkeypatch)
    assert datos.mover(g["id"], "armando", "error", error="x")
    assert "nada" in _armar(entorno, g["id"])
    assert pedidos == [] and _cola("edicion_producir") == []
```

En `tests/test_tareas_swap.py`, la lista ordenada de `test_registro_contiene_swap_generar` suma los tres tipos
nuevos en su lugar (`… "tw_analizar_anuncio", "tw_evaluar", "tw_gancho_armar", "tw_ganchos_preparar",
"tw_ganchos_vigilar", "tw_sincronizar", "tw_sincronizar_todas", "voz_propia_crear",`).

En `tests/test_tareas_decidir.py::test_periodica_decidir_registrada`, la lista esperada pasa de
`("errores_limpiar", 86400), ("cadena_vigilar", 60),` a
`("errores_limpiar", 86400), ("cadena_vigilar", 60), ("tw_ganchos_vigilar", 60),`.

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_tareas.py tests/test_tareas_swap.py tests/test_tareas_decidir.py::test_periodica_decidir_registrada tests/test_cobros_worker.py`
Expected: FAIL (`AttributeError: module 'tareas.triple_whale' has no attribute 'tw_ganchos_preparar'`; las listas no
coinciden).

- [ ] **Step 3: Implementar las tareas**

En `tareas/triple_whale.py`, el docstring suma:

```
  tw_ganchos_preparar   -> f"{cliente}__tw_ganchos_{aid}_t{tanda}"  (max_intentos=1, prioridad 3; gratis: baja el
                           original y lanza una pieza de Crear por gancho, cada una la cobra flowplus_video)
  tw_ganchos_vigilar    -> periódica (worker.PERIODICAS, 60 s): mueve cada variante viva (spec 2026-10-09 §4.5)
  tw_gancho_armar       -> f"{cliente}__tw_gancho_{gid}_armar"  (max_intentos=2, prioridad 1; gratis: arma la
                           edición con el clip ya pagado y el original, y encola su render)
```

Imports (sumados a los de hoy, en su orden):

```python
import os
import shutil
from datetime import datetime, timedelta

from flask_babel import gettext, ngettext

import creative_flow
import ediciones
import flowplus_lanzar
import materiales
from cobros import SaldoInsuficiente
from conectores import url as conector_url
from conectores.base import ErrorConector
from final_edition import borrador, cortes, encuadre, insumos, mezcla
from final_edition import documento as documento_mod
from final_edition.motor import compilador
from storage import r2_uploader
from tareas import edicion as tareas_edicion
from tareas.cadena import VIVOS_CREAR
from triple_whale import ganchos
```

Al final del archivo:

```python
# ------------------------------------------------ ganchos nuevos (spec 2026-10-09 §4.4–§4.6) ---

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIPO_GANCHOS_PREPARAR = "tw_ganchos_preparar"
TIPO_GANCHOS_VIGILAR = "tw_ganchos_vigilar"
TIPO_GANCHO_ARMAR = "tw_gancho_armar"
# Como la cadena de escenas y los lotes de Sprints: una pieza suelta de Crear (5) siempre pasa adelante.
PRIORIDAD_GANCHOS = 3
# Una fila recién creada tiene unos milisegundos sin su trabajo en la cola (la ruta guarda el job_id después de
# crear la tanda; el vigilante mueve a «armando» antes de encolar): solo se da por cortada pasado esto sin cambios.
GRACIA_S = 120
ETAPAS_GANCHOS = [(idiomas.N_("Bajando el video"), 40), (idiomas.N_("Lanzando los clips"), 60)]
ETAPAS_ARMAR = [(idiomas.N_("Armando el video"), 100)]


def job_id_preparar(cliente, analisis_id, tanda):
    return f"{cliente}__tw_ganchos_{int(analisis_id)}_t{int(tanda)}"


def job_id_armar(cliente, gancho_id):
    return f"{cliente}__tw_gancho_{int(gancho_id)}_armar"


def encolar_preparar(cliente, analisis_id, tanda):
    """La preparación de una tanda. Gratis en sí: cada clip lo cobra su pieza de Crear. max_intentos=1: si se corta,
    el vigilante cierra la tanda y la persona la vuelve a pedir con su precio a la vista. False si ya estaba viva."""
    return trabajos.encolar(job_id_preparar(cliente, analisis_id, tanda), TIPO_GANCHOS_PREPARAR,
                            {"cliente": cliente, "analisis_id": int(analisis_id), "tanda": int(tanda)},
                            cliente=cliente, duracion_estimada=90, etapas=ETAPAS_GANCHOS, max_intentos=1,
                            prioridad=PRIORIDAD_GANCHOS)


def _texto_error(e):
    """El motivo en palabras, en el idioma del proyecto (el worker ya lo pone), sin rutas ni tokens: lo nuestro
    (`ganchos.GanchoError`, un msgid) traducido; una descarga que falla, en palabras; lo demás, solo el tipo."""
    if isinstance(e, ganchos.GanchoError):
        mensaje = str(e)
        return gettext(mensaje)
    if isinstance(e, ErrorConector):
        mensaje = ganchos.ERROR_BAJAR
        return gettext(mensaje)
    return gettext("Algo falló al preparar el gancho (%(error)s).", error=type(e).__name__)


def _fotograma_en(ruta, segundo, destino):
    """El cuadro del segundo `segundo` como JPG (`-ss` antes de `-i`: busca por el índice sin decodificar lo de
    antes). GanchoError si ffmpeg falla o no escribe nada (un segundo más allá del final)."""
    if os.path.exists(destino):
        os.remove(destino)
    try:
        cortes.ffmpeg(["-ss", f"{float(segundo):.3f}", "-i", ruta, "-frames:v", "1", "-q:v", "2", destino], timeout=120)
    except RuntimeError:
        raise ganchos.GanchoError(ganchos.ERROR_FOTOGRAMA) from None
    if not (os.path.isfile(destino) and os.path.getsize(destino) > 0):
        raise ganchos.GanchoError(ganchos.ERROR_FOTOGRAMA)
    return destino


def _bajar_original(foto, carpeta):
    """El video del anuncio a `carpeta/original.mp4` (spec §4.4.1): solo desde `mejorar._url_voz` (el mp4 de
    files.triplewhale.com o el video de R2 de una pieza de Creatv), con `conectores.url.descargar_archivo` (60 MB,
    solo video/*, SSRF en cada redirección), y ffmpeg solo lo abre si ffprobe dice mp4/mov."""
    url = mejorar._url_voz(foto or {})
    if not url:
        raise ganchos.GanchoError(ganchos.MOTIVO_SIN_VIDEO)
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "original.mp4")
    try:
        conector_url.descargar_archivo(url, ruta)
    except ErrorConector:
        raise ganchos.GanchoError(ganchos.ERROR_BAJAR) from None
    if not mejorar.es_mp4(ruta):
        raise ganchos.GanchoError(ganchos.ERROR_NO_MP4)
    return ruta


def _material_original(cliente, ruta, foto):
    """El original como material del editor (spec §4.4.2): gratis, deduplicado por hash, en «Medios» (origen
    triple_whale) y con su proxy en cola si aún no lo tiene."""
    info = cortes.ffprobe_json(ruta)
    video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    ancho, alto = encuadre.medidas_visibles(video)
    h = materiales.hash_archivo(ruta)
    mat = materiales.subir(cliente, ruta, f"clientes/{cliente}/materiales/{h}.mp4", "video/mp4", tipo="video",
                           origen="triple_whale", duracion_ms=borrador.ms(cortes.duracion(ruta)),
                           ancho=ancho or None, alto=alto or None,
                           extra={"nombre": str(foto.get("nombre") or foto.get("ad_id") or "")[:120],
                                  "tiene_audio": mezcla.tiene_audio(ruta), "local": ruta, "ad_id": foto.get("ad_id")})
    if not mat.get("url_proxy"):
        trabajos.encolar(insumos.job_id_proxy(cliente, mat["id"]), "edicion_proxy",
                         {"cliente": cliente, "material_id": mat["id"]}, cliente=cliente, duracion_estimada=120,
                         max_intentos=3, prioridad=1)
    return mat


def _lanzar_gancho(cliente, aid, g, foto, ruta, duracion_s, original, carpeta):
    """Una variante (spec §4.4.3): el fotograma de arranque a R2, la sesión de Crear del clip (como
    `tareas.cadena.lanzar_escena` con imagen de arranque: Kling O3 Pro imagen a video, 3 s, sin sonido) y su lugar en
    la cola. El cf_id se anota ANTES de lanzar: una corrida repetida nunca lanza dos veces la misma fila.
    SaldoInsuficiente sube a quien llama. True si quedó en la cola."""
    gid = g["id"]
    segundo = mejorar.segundo_fotograma(g["fotograma_s"], duracion_s)
    jpg = _fotograma_en(ruta, segundo, os.path.join(carpeta, f"g{gid}.jpg"))
    frame_url = r2_uploader.upload_image(jpg, f"clientes/{cliente}/triple_whale/ganchos/{gid}.jpg")
    datos.actualizar_gancho(gid, frame_url=frame_url)
    accion = gettext("Gancho %(n)s · %(nombre)s", n=g["n"], nombre=foto.get("nombre") or foto.get("ad_id") or "")[:200]
    cf_id = creative_flow.crear(cliente, [], [], [], accion, ganchos.SEGUNDOS, "", "A", referencias_urls=[],
                                platforms=[])
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=g["prompt"], prompt_fuente=g["prompt"], tipo="video",
                             modelo=ganchos.MODELO,
                             aspect_ratio=ganchos.aspecto_kling(original.get("ancho"), original.get("alto")),
                             con_sonido=False, sonido_texto="", musica_estilo="", calidad="final",
                             imagen_inicial=frame_url, elementos=[],
                             referencias=[{"tipo": "imagen", "url": frame_url, "frame_url": frame_url,
                                           "etiqueta": "@Imagen 1", "titulo": ganchos.codigo(gid)}],
                             tw_gancho={"gancho_id": gid, "analisis_id": aid, "original_hash": original["hash"]})
    datos.actualizar_gancho(gid, cf_id=cf_id)
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_GANCHOS):
        datos.mover(gid, "preparando", "error", error=gettext("No se pudo poner el clip en la cola."))
        return False
    datos.mover(gid, "preparando", "generando", job_id=flowplus_lanzar.job_id(cliente, cf_id))
    return True


@registrar(TIPO_GANCHOS_PREPARAR)
def tw_ganchos_preparar(tarea):
    p = tarea["payload"]
    cliente, aid, tanda = p["cliente"], int(p["analisis_id"]), int(p["tanda"])
    job_id = tarea.get("job_id") or job_id_preparar(cliente, aid, tanda)
    pendientes = [g for g in datos.ganchos_de_analisis(cliente, aid)
                  if g["tanda"] == tanda and g["estado"] == "preparando" and not g["cf_id"]]
    if not pendientes:
        return gettext("No había ganchos que preparar.")
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "tw_ganchos", f"{aid}_t{tanda}")
    lanzados = 0
    try:
        foto = (datos.analisis_anuncio(cliente, aid) or {}).get("foto") or {}
        trabajos.reportar(job_id, etapa=idiomas.N_("Bajando el video"))
        ruta = _bajar_original(foto, carpeta)
        original = _material_original(cliente, ruta, foto)
        duracion_s = (original.get("duracion_ms") or 0) / 1000
        if duracion_s < ganchos.MIN_ORIGINAL_S:
            raise ganchos.GanchoError(ganchos.MOTIVO_CORTO)
        trabajos.reportar(job_id, etapa=idiomas.N_("Lanzando los clips"))
        for i, g in enumerate(pendientes):
            try:
                if _lanzar_gancho(cliente, aid, g, foto, ruta, duracion_s, original, carpeta):
                    lanzados += 1
            except SaldoInsuficiente as e:
                # Cobros (spec §4.4.4): esa variante y las que faltan quedan en error con la frase; las ya lanzadas
                # siguen su camino con su reserva.
                frase = e.frase_proyecto()
                for resto in pendientes[i:]:
                    datos.mover(resto["id"], "preparando", "error", error=frase)
                break
    except Exception as e:
        log.exception("ganchos: no se pudo preparar la tanda %s del análisis %s", tanda, aid)
        mensaje = _texto_error(e)
        for g in datos.ganchos_de_analisis(cliente, aid):
            if g["tanda"] == tanda and g["estado"] == "preparando":
                datos.mover(g["id"], "preparando", "error", error=mensaje)
        raise RuntimeError(mensaje) from None
    finally:
        # El material ya guardó su copia en R2 (spec §4.4.4).
        shutil.rmtree(carpeta, ignore_errors=True)
    return ngettext("%(num)s gancho en camino.", "%(num)s ganchos en camino.", lanzados)


def _quieto(g, segundos=GRACIA_S):
    """¿La fila lleva al menos `segundos` sin cambiar?"""
    try:
        return datetime.fromisoformat(g["actualizado_en"]) <= datetime.now() - timedelta(seconds=segundos)
    except (TypeError, ValueError):
        return True


def vigilar_gancho(cliente, g, sesiones):
    """Un paso de una variante viva (spec §4.5). `sesiones` = `creative_flow.cargar(cliente)` (una lectura por
    proyecto). Seguro de llamar de más: `datos.mover` es un CAS y nada avanza dos veces."""
    estado, gid = g["estado"], g["id"]
    if estado == "generando":
        entry = sesiones.get(g["cf_id"]) if g["cf_id"] else None
        if entry is None:
            datos.mover(gid, "generando", "error", error=gettext("El clip de este gancho ya no está en Crear."))
        elif entry.get("estado") in VIVOS_CREAR:
            return
        elif entry.get("estado") == "video_listo":
            job = job_id_armar(cliente, gid)
            if datos.mover(gid, "generando", "armando", job_id=job):
                try:
                    trabajos.encolar(job, TIPO_GANCHO_ARMAR, {"cliente": cliente, "gancho_id": gid}, cliente=cliente,
                                     duracion_estimada=60, etapas=ETAPAS_ARMAR, max_intentos=2, prioridad=1)
                except Exception:  # noqa: BLE001 — sin tarea nadie la armaría: queda en error con su motivo
                    log.exception("ganchos: no se pudo encolar el armado del gancho %s", gid)
                    datos.mover(gid, "armando", "error", error=gettext("No se pudo poner el armado en la cola."))
        else:
            datos.mover(gid, "generando", "error", error=entry.get("error") or gettext("El clip no se pudo generar."))
    elif estado == "produciendo":
        final = creative_flow.final_por_legado(cliente, g["final_id"]) if g["final_id"] else None
        if final is None:
            datos.mover(gid, "produciendo", "error", error=gettext("La final de este gancho ya no existe."))
        elif final.get("estado") in ("listo", "degradada") and final.get("video_url"):
            datos.mover(gid, "produciendo", "lista", url_final=final["video_url"])
        elif final.get("estado") == "error":
            datos.mover(gid, "produciendo", "error", error=final.get("error") or gettext("No se pudo producir el video."))
    elif estado in ("preparando", "armando"):
        if not trabajos.en_curso(g["job_id"]) and _quieto(g):
            datos.mover(gid, estado, "error", error=gettext("La preparación se cortó antes de terminar."))


@registrar(TIPO_GANCHOS_VIGILAR)
def tw_ganchos_vigilar(tarea):
    por_cliente = {}
    for g in datos.ganchos_vivos():
        por_cliente.setdefault(g["cliente"], []).append(g)
    for cliente, filas in por_cliente.items():
        # Periódica: no tiene proyecto propio; lo que guarda va en el idioma de cada proyecto (spec §8).
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            try:
                sesiones = creative_flow.cargar(cliente) if any(g["estado"] == "generando" for g in filas) else {}
            except Exception:  # noqa: BLE001 — se reintenta en 60 s
                log.exception("ganchos: no pude leer las sesiones de %s", cliente)
                continue
            for g in filas:
                try:
                    vigilar_gancho(cliente, g, sesiones)
                except Exception:  # noqa: BLE001 — una variante rota no frena a las demás (como cadena_vigilar)
                    log.exception("ganchos: falló el vigilante en el gancho %s", g["id"])
    return None


def _ultimo_intento(tarea):
    return int(tarea.get("intentos") or 1) >= int(tarea.get("max_intentos") or 1)


def _armar(cliente, g):
    """Spec §4.6: el material del clip, el del original (por su hash; si ya no está, se vuelve a bajar), el documento,
    la edición, la versión congelada y su render. Nada de esto cobra."""
    from final_edition import biblioteca, rutas_editor  # tardío: arrastran el blueprint del editor
    fila = datos.analisis_anuncio(cliente, g["analisis_id"]) or {}
    foto = fila.get("foto") or {}
    carpeta = os.path.join(BASE_DIR, "salidas", cliente, "tw_ganchos", f"g{g['id']}")
    try:
        clip = biblioteca.materializar_pieza(cliente, g["cf_id"], os.path.join(carpeta, "clip"))
        h = ((creative_flow.cargar(cliente).get(g["cf_id"]) or {}).get("tw_gancho") or {}).get("original_hash")
        original = materiales.buscar_hash(cliente, h) if h else None
        if original is None:
            original = _material_original(cliente, _bajar_original(foto, carpeta), foto)
        tienda = triple_whale_tiendas.tienda(cliente, fila["tienda_id"]) if fila.get("tienda_id") else None
        idioma, pais = ganchos.destino((tienda or {}).get("pais"), proyectos.pais(cliente))
        doc = ganchos.documento_gancho(clip, original, g["texto"],
                                       ganchos.formato_cercano(original.get("ancho"), original.get("alto")),
                                       idioma, pais, analisis_id=g["analisis_id"], gancho_id=g["id"])
        nombre = f"{foto.get('nombre') or foto.get('ad_id') or ''} · {ganchos.codigo(g['id'])}"[:120]
        ed = ediciones.crear(cliente, "video", nombre, doc, cf_id=g["cf_id"], creada_por="triple_whale")
        compilador.verificar_recortes(documento_mod.resolver(ed["documento"], idioma, pais),
                                      {int(clip["id"]): int(clip["duracion_ms"]),
                                       int(original["id"]): int(original["duracion_ms"])})
        version = ediciones.versionar(cliente, ed["id"], motivo="producir")
        destino = f"{idioma}_{pais}"
        [producida] = rutas_editor.encolar_producciones(cliente, ed["id"], ed, version, [destino])
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    if not datos.mover(g["id"], "armando", "produciendo", edicion_id=ed["id"], final_id=producida["final_id"],
                       job_id=tareas_edicion.job_id_producir(cliente, ed["id"], idioma, pais)):
        log.warning("ganchos: el gancho %s dejó de estar armando mientras se armaba", g["id"])
    return ganchos.codigo(g["id"])


@registrar(TIPO_GANCHO_ARMAR)
def tw_gancho_armar(tarea):
    p = tarea["payload"]
    cliente, gid = p["cliente"], int(p["gancho_id"])
    g = datos.gancho(cliente, gid)
    if not g or g["estado"] != "armando":
        return gettext("No había nada que armar.")
    try:
        codigo = _armar(cliente, g)
    except Exception as e:
        log.exception("ganchos: no se pudo armar el gancho %s", gid)
        mensaje = _texto_error(e)
        if _ultimo_intento(tarea):
            # Con max_intentos=2 el primer fallo deja la fila en «armando» y la cola vuelve a intentar desde el
            # principio (spec §4.6.5); el último deja el motivo en la fila.
            datos.mover(gid, "armando", "error", error=mensaje)
        raise RuntimeError(mensaje) from None
    return gettext("Gancho armado: produciendo %(codigo)s.", codigo=codigo)
```

- [ ] **Step 4: Clasificar los tipos y la periódica**

`tareas/__init__.py`, en `TIPOS_EXENTOS_DE_COBRO` (después de `"tw_sincronizar_todas"`):

```python
    "tw_ganchos_preparar": "baja el video y lanza piezas de Crear; cada pieza la cobra flowplus_video",
    "tw_ganchos_vigilar": "periódica: mueve las variantes de los ganchos; cada clip lo cobra flowplus_video",
    "tw_gancho_armar": "arma con ffmpeg y el editor un clip ya pagado y el original",
```

`worker.py`, `PERIODICAS`, después de `("cadena_vigilar", 60),`:

```python
              # Ganchos de Triple Whale (spec 2026-10-09 §4.5): mueve cada variante viva (gratis; cada clip lo
              # cobra Crear y el armado y el render son ffmpeg).
              ("tw_ganchos_vigilar", 60),
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_tareas.py tests/test_tareas_swap.py tests/test_tareas_decidir.py tests/test_cobros_worker.py tests/test_tareas_cadena.py tests/test_tw_tarjetas_tarea.py`
Expected: PASS (la prueba `slow` corre ffmpeg de verdad y tarda unos segundos).

- [ ] **Step 6: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py pendientes`
Traduce («Bajando el video» ya existe):

| msgid | msgstr |
|---|---|
| Lanzando los clips | Launching the clips |
| Armando el video | Building the video |
| No había ganchos que preparar. | There were no hooks to prepare. |
| Gancho %(n)s · %(nombre)s | Hook %(n)s · %(nombre)s |
| No se pudo poner el clip en la cola. | Couldn't queue the clip. |
| %(num)s gancho en camino. / %(num)s ganchos en camino. | %(num)s hook on its way. / %(num)s hooks on their way. |
| Algo falló al preparar el gancho (%(error)s). | Something failed while preparing the hook (%(error)s). |
| El clip de este gancho ya no está en Crear. | This hook's clip is no longer in Create. |
| El clip no se pudo generar. | The clip couldn't be generated. |
| No se pudo poner el armado en la cola. | Couldn't queue the video assembly. |
| La final de este gancho ya no existe. | This hook's final cut no longer exists. |
| No se pudo producir el video. | Couldn't produce the video. |
| La preparación se cortó antes de terminar. | The preparation stopped before finishing. |
| No había nada que armar. | There was nothing to build. |
| Gancho armado: produciendo %(codigo)s. | Hook built: producing %(codigo)s. |

(El plural va en `msgstr[0]` y `msgstr[1]`.)
Run: `venv/bin/python3 catalogo_i18n.py compilar && venv/bin/python3 -m pytest -q tests/test_i18n_catalogo.py tests/test_i18n_mensajes.py`
Expected: PASS.

- [ ] **Step 7: Suite de Triple Whale y commit**

Run: la suite de Triple Whale (Global Constraints). Expected: PASS.

```bash
git add tareas/triple_whale.py tareas/__init__.py worker.py tests/test_tw_ganchos_tareas.py tests/test_tareas_swap.py tests/test_tareas_decidir.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Triple Whale ganchos: preparar lanza un clip de Kling por gancho, el vigilante los mueve y armar produce la edición

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: La pantalla: «Probar los 3 ganchos», el copy nuevo y las variantes

**Files:**
- Modify: `triple_whale/rutas.py` (imports, `_contexto_ganchos`, `_respuesta_ganchos`, `analisis_detalle`, ruta
  nueva `ganchos_probar`; el docstring del módulo suma una línea)
- Modify: `templates/_tw_analisis.html` (bloques «Ganchos nuevos» y «Copy nuevo para Meta»)
- Modify: `templates/_tab_triple_whale.html` (volver a pedir el detalle, el POST de los ganchos)
- Modify: `static/estilos/pantallas/triple-whale.css` y el generado `static/style.css`
- Test: `tests/test_tw_ganchos_rutas.py` (nuevo), `tests/test_tw_tarjetas_js.py` (una prueba al final)
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`

**Interfaces:**
- Consumes: Task 1 (`datos.crear_tanda`, `TandaViva`, `mover`, `actualizar_gancho`, `ganchos_de_analisis`,
  `VIVOS_GANCHO`), Task 2 (`gastos.estimar_ganchos_tw`), Task 3 (`ganchos.ganchos_generables`, `puede_probar`,
  `tandas`, `MOTIVO_SIN_PRECIO`), Task 5 (`tareas_tw.job_id_preparar`, `encolar_preparar`); `cola.job_ids_vivos_todos`,
  `gastos.costo_de_precio`, `gastos.precio`, `gastos.formatear`, `libro.exigir`, `mejorar._url_voz`.
- Produces: endpoint `triple_whale.ganchos_probar` (`POST /cliente/<c>/triple-whale/analisis/<aid>/ganchos`, campo
  `precio_visto`); `_contexto_ganchos(cliente, fila) -> {"generables", "n", "precio", "motivo", "sin_precio", "ultima",
  "anteriores", "esperan"}` (la plantilla lo recibe como `gh`; cada fila de `ultima` y de `anteriores[*].filas` trae
  `codigo` y `barra`); en el fragmento, `form[data-tw-ganchos]` y el marcador `data-tw-ganchos-esperan`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_tw_ganchos_rutas.py`:

```python
"""La pantalla de los ganchos (spec 2026-10-09 §4.1, §4.3, §5, §6 y §7): la ruta que pide la tanda y el detalle que
la muestra. Nada se genera: la tarea de preparar solo queda en la cola."""
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event

import db
import proyectos
import trabajos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_tw_mejorar import COPY_NUEVO, GANCHOS, respuesta
from triple_whale import datos, mejorar
from triple_whale import ganchos as ganchos_tw


@pytest.fixture(autouse=True)
def _proyecto_aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))


def _analisis(cliente="acme", lista_ganchos=None, video=True, duracion=20.0, copy_nuevo=True, estado="lista"):
    foto = {"nombre": "Anuncio p1", "ad_id": "p1", "canal": "facebook-ads",
            "creativo": {"tipo": "video", "video_url": "https://files.triplewhale.com/v/p1.mp4" if video else None,
                         "imagen_url": "https://files.triplewhale.com/t/p1.jpg", "duracion_s": duracion,
                         "titulo": "Título", "copy": "Copy"}}
    aid = datos.crear_analisis(cliente, None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", foto)
    cambios = {"ganchos": GANCHOS if lista_ganchos is None else lista_ganchos}
    if copy_nuevo:
        cambios["copy_nuevo"] = COPY_NUEVO
    datos.actualizar_analisis(aid, estado=estado, usd=0.08,
                              resultado=mejorar.parsear(respuesta(**cambios), "datos", duracion_s=duracion),
                              medios={"visual": "fotogramas", "fotogramas": 6, "copy": True})
    return aid


def _detalle(app, aid):  # noqa: F811
    return app["c"].get(f"/cliente/acme/triple-whale/analisis/{aid}").data.decode()


def _probar(app, aid, precio="1.008", json=True, **headers):  # noqa: F811
    h = dict(headers)
    if json:
        h["Accept"] = "application/json"
    return app["c"].post(f"/cliente/acme/triple-whale/analisis/{aid}/ganchos", data={"precio_visto": precio}, headers=h)


def _preparaciones():
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(db.tarea).where(db.tarea.c.tipo == "tw_ganchos_preparar"))]


def _generables(aid):
    return ganchos_tw.ganchos_generables(datos.analisis_anuncio("acme", aid)["resultado"])


def _cobra(milesimas=0):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, "acme", "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")
    return libro


# --------------------------------------------------------------------------------------------------- detalle ---

def test_el_detalle_muestra_copy_ganchos_y_el_boton_con_su_precio(app):  # noqa: F811
    aid = _analisis()
    html = _detalle(app, aid)
    assert "Copy nuevo para Meta" in html and "Descanso para tus pies" in html
    assert html.index("Copy nuevo para Meta") < html.index("Versión mejorada")
    assert html.count('onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)"') == 2
    assert "Ganchos nuevos (primeros 3 s)" in html and "«¿Te duelen los pies al final del día?»" in html
    assert "Slow push-in on a tired foot" in html                                 # el prompt, en un <details>
    assert "Probar los 3 ganchos · US$ 1,01" in html and "data-tw-ganchos" in html
    assert "¿Generar 3 clips de 3 s con Kling y armar sus videos? Costo: US$ 1,01" in html
    assert re.search(r'name="precio_visto" value="1\.008"', html)
    assert f'action="/cliente/acme/triple-whale/analisis/{aid}/ganchos"' in html
    assert "<script" not in html


def test_un_gancho_con_cifras_no_se_genera_ni_entra_al_precio(app):  # noqa: F811
    lista = [GANCHOS[0], dict(GANCHOS[1], texto="50 % menos dolor"), GANCHOS[2]]
    aid = _analisis(lista_ganchos=lista)
    html = _detalle(app, aid)
    assert "No se genera: cita cifras que no están en los datos (50 %)." in html
    assert "Probar los 2 ganchos · US$ 0,67" in html
    r = _probar(app, aid, precio="0.672")
    assert r.status_code == 200 and r.get_json()["ok"]
    assert [f["n"] for f in datos.ganchos_de_analisis("acme", aid)] == [1, 3]


def test_un_analisis_viejo_sin_ganchos_lo_dice_y_no_ofrece_nada(app):  # noqa: F811
    aid = _analisis()
    datos.actualizar_analisis(aid, resultado={"frase": "Pierde porque arranca con el logo."})
    html = _detalle(app, aid)
    assert "Este análisis es de antes de los ganchos." in html and "data-tw-ganchos" not in html
    assert "Copy nuevo para Meta" not in html
    r = _probar(app, aid)
    assert r.status_code == 409 and r.get_json()["mensaje"] == "Este análisis es de antes de los ganchos."


@pytest.mark.parametrize("kw, motivo", [({"video": False}, "Sin video que se pueda bajar"),
                                         ({"duracion": 4.0}, "El video es muy corto")])
def test_sin_video_o_con_video_corto_dice_por_que_y_no_cobra(app, kw, motivo):  # noqa: F811
    aid = _analisis(**kw)
    html = _detalle(app, aid)
    assert motivo in html and 'name="precio_visto"' not in html
    r = _probar(app, aid)
    assert r.status_code == 409 and motivo in r.get_json()["mensaje"]
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_el_detalle_muestra_cada_variante_segun_su_estado(app):  # noqa: F811
    aid = _analisis()
    f1, f2, f3 = datos.crear_tanda("acme", aid, _generables(aid), pedido_por="admin")
    assert datos.mover(f1["id"], "preparando", "lista", cf_id="cf_x", edicion_id=5,
                       url_final="https://r2.test/final.mp4")
    assert datos.mover(f2["id"], "preparando", "error", error="Kling: contenido sensible")
    trabajos.encolar("acme__cf_y__creative_flow", "flowplus_video", {"cliente": "acme", "cf_id": "cf_y"},
                     cliente="acme", max_intentos=1)
    assert datos.mover(f3["id"], "preparando", "generando", cf_id="cf_y", job_id="acme__cf_y__creative_flow")
    html = _detalle(app, aid)
    assert '<video controls preload="none" data-precarga src="https://r2.test/final.mp4"' in html
    assert f"CV{f1['id']}" in html and f"CV{f3['id']}" in html and f'data-copiar="CV{f1["id"]}"' in html
    assert "/cliente/acme/ediciones/5" in html and "#creativeflowplus?cf=cf_x" in html
    assert 'href="https://r2.test/final.mp4" download' in html
    assert "Kling: contenido sensible" in html
    assert f'id="tw-gancho-{f3["id"]}" data-poll-job="acme__cf_y__creative_flow" data-poll-al-terminar="evento"' in html
    assert "Generando el clip" in html and "Pon este código en el nombre del anuncio en Meta" in html
    assert "Hay una tanda en curso" in html and 'name="precio_visto"' not in html      # sin botón mientras vive
    assert "data-tw-ganchos-esperan" not in html and "<script" not in html


def test_una_variante_viva_sin_trabajo_vivo_no_pinta_barra_y_pide_esperar(app):  # noqa: F811
    """Ruling 4: una barra sobre un trabajo ya terminado avisaría al instante y la pestaña pediría el detalle en
    bucle. Sin trabajo vivo (el clip terminó y el vigilante todavía no pasó) va el estado sin barra y el marcador."""
    aid = _analisis()
    f1, _f2, _f3 = datos.crear_tanda("acme", aid, _generables(aid))
    assert datos.mover(f1["id"], "preparando", "generando", cf_id="cf_z", job_id="acme__cf_z__creative_flow")
    html = _detalle(app, aid)
    assert "data-poll-job" not in html and "data-tw-ganchos-esperan" in html and "Generando el clip" in html


def test_el_detalle_lee_las_variantes_en_una_consulta_y_resume_las_tandas_viejas(app):  # noqa: F811
    aid = _analisis()
    for _ in range(2):
        for f in datos.crear_tanda("acme", aid, _generables(aid)):
            datos.mover(f["id"], "preparando", "lista", cf_id="cf", edicion_id=1, url_final="https://r2.test/x.mp4")
    vistas = []
    contar = lambda conn, cursor, statement, *a: vistas.append(statement)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", contar)
    try:
        html = _detalle(app, aid)
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", contar)
    assert sum(1 for s in vistas if "tw_gancho" in s) == 1
    assert "Antes: 1 tanda · ver" in html and html.count("<video") == 3


# ------------------------------------------------------------------------------------------------------ ruta ---

def test_probar_crea_la_tanda_y_encola_la_preparacion_una_vez(app):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "mensaje": "Generando 3 ganchos…"}
    filas = datos.ganchos_de_analisis("acme", aid)
    job = f"acme__tw_ganchos_{aid}_t1"
    assert [(f["tanda"], f["n"], f["estado"]) for f in filas] == [(1, 1, "preparando"), (1, 2, "preparando"),
                                                                   (1, 3, "preparando")]
    assert {f["job_id"] for f in filas} == {job} and {f["pedido_por"] for f in filas} == {"admin"}
    assert filas[0]["texto"] == GANCHOS[0]["texto"] and filas[0]["prompt"] == GANCHOS[0]["prompt"]
    [t] = _preparaciones()
    assert t["job_id"] == job and t["max_intentos"] == 1 and t["prioridad"] == 3 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "analisis_id": aid, "tanda": 1}
    r = _probar(app, aid)                                            # segundo clic: tanda viva, nada nuevo
    assert r.status_code == 409 and "Hay una tanda en curso" in r.get_json()["mensaje"]
    assert len(_preparaciones()) == 1 and len(datos.ganchos_de_analisis("acme", aid)) == 3


def test_probar_por_formulario_vuelve_a_la_pestana(app):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid, json=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    assert len(_preparaciones()) == 1


def test_probar_rechaza_otro_origen_otro_proyecto_e_ids_raros(app):  # noqa: F811
    aid = _analisis()
    assert _probar(app, aid, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    ajeno = _analisis(cliente="otro")
    assert _probar(app, ajeno).status_code == 404
    assert app["c"].post("/cliente/acme/triple-whale/analisis/99999999999999999999/ganchos").status_code == 404
    assert datos.ganchos_de_analisis("otro", ajeno) == [] and _preparaciones() == []


@pytest.mark.parametrize("precio", ["0.50", "", "abc", "1e9"])
def test_si_el_precio_cambio_no_crea_ni_encola_nada(app, precio):  # noqa: F811
    aid = _analisis()
    r = _probar(app, aid, precio=precio)
    assert r.status_code == 409 and r.get_json()["mensaje"].startswith("El precio cambió: ahora es US$ 1,01.")
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_sin_saldo_no_guarda_nada_y_el_fetch_recibe_402(app):  # noqa: F811
    aid = _analisis()
    _cobra()
    visto = re.search(r'name="precio_visto" value="([^"]+)"', _detalle(app, aid)).group(1)  # el precio con margen
    r = _probar(app, aid, precio=visto)
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert datos.ganchos_de_analisis("acme", aid) == [] and _preparaciones() == []


def test_con_saldo_pide_el_total_y_no_reserva_hasta_lanzar_cada_clip(app):  # noqa: F811
    aid = _analisis()
    _cobra(milesimas=5000)
    visto = re.search(r'name="precio_visto" value="([^"]+)"', _detalle(app, aid)).group(1)
    assert _probar(app, aid, precio=visto).get_json()["ok"]
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.reserva_saldo)).scalar() == 0
    assert len(_preparaciones()) == 1


def test_una_tanda_que_se_cuela_entre_la_revision_y_el_insert_es_409(app, monkeypatch):  # noqa: F811
    aid = _analisis()

    def _viva(*a, **k):
        raise datos.TandaViva()
    monkeypatch.setattr(datos, "crear_tanda", _viva)
    r = _probar(app, aid)
    assert r.status_code == 409 and "Ya hay una tanda de ganchos en curso" in r.get_json()["mensaje"]
    assert _preparaciones() == []


def test_si_no_se_puede_encolar_la_tanda_queda_en_error_y_el_boton_vuelve(app, monkeypatch):  # noqa: F811
    from tareas import triple_whale as tareas_tw
    aid = _analisis()
    monkeypatch.setattr(tareas_tw, "encolar_preparar", lambda *a, **k: False)
    r = _probar(app, aid)
    assert r.status_code == 409 and "vuelve a intentarlo" in r.get_json()["mensaje"]
    filas = datos.ganchos_de_analisis("acme", aid)
    assert {f["estado"] for f in filas} == {"error"} and filas[0]["error"] == "No se pudo poner la preparación en la cola."
    assert "Probar los 3 ganchos" in _detalle(app, aid)


def test_la_hoja_tiene_las_reglas_de_los_ganchos():
    with open("static/style.css", encoding="utf-8") as f:
        css = f.read()
    assert ".tw-variantes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 12rem), 1fr))" in css
    assert ".tw-copy-texto { margin: 0; white-space: pre-line; }" in css
```

Al final de `tests/test_tw_tarjetas_js.py`:

```python
def test_los_ganchos_vuelven_a_pedir_el_detalle_y_nunca_reenvian_el_post():
    """Spec 2026-10-09 §5 y regla 1: la barra de una variante pide el detalle otra vez (no repinta la tarjeta, que
    cerraría el detalle); el POST de «Probar los N ganchos» es un solo fetch después de la confirmación, nunca se
    repite, y mientras una variante espera al vigilante el detalle se vuelve a pedir con un tope."""
    tab = _leer("_tab_triple_whale.html")
    terminado = _manejador(tab, "cont.addEventListener('trabajo-terminado'", "closest('form[data-tw-ganchos]')")
    assert "closest('.tw-analisis-detalle')" in terminado and "recargarDetalle(caja)" in terminado
    assert terminado.index("recargarDetalle(caja)") < terminado.index("repintarTarjeta(")
    ganchos = _manejador(tab, "closest('form[data-tw-ganchos]')", "function siActiva()")
    assert ganchos.count("fetch(") == 1 and "method: 'POST'" in ganchos
    assert "ev.defaultPrevented" in ganchos and ganchos.index("ev.defaultPrevented") < ganchos.index("fetch(")
    assert "recargarDetalle(caja, T_TW.pedido)" in ganchos and ".submit(" not in tab
    espera = _manejador(tab, "function programarEspera(", "function avisoDetalle(")
    assert "MAX_ESPERAS" in espera and "setTimeout" in espera and "caja.isConnected" in espera
    assert "data-tw-ganchos-esperan" in espera
    detalle = _sin_comentarios(_leer("_tw_analisis.html"))
    assert "<script" not in detalle and 'preload="none" data-precarga' in detalle
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_rutas.py tests/test_tw_tarjetas_js.py`
Expected: FAIL (404 en `/ganchos`, el detalle sin «Copy nuevo para Meta», la pestaña sin `data-tw-ganchos`).

- [ ] **Step 3: Implementar la ruta y el contexto del detalle**

En `triple_whale/rutas.py`: imports `import cola` (junto a `import gastos`) y `from triple_whale import ganchos as
ganchos_tw` (en la línea de `from triple_whale import analisis, datos, …`); el docstring suma
«- `ganchos_probar` (POST, spec 2026-10-09 §4.3): «Probar los N ganchos» de un análisis: revisa, compara el precio
visto, pide saldo, crea la tanda (`tw_gancho`) y encola su preparación (gratis; cada clip lo cobra su pieza de Crear).».

Después de `_aprendizaje_de`:

```python
def _contexto_ganchos(cliente, fila):
    """Lo que el detalle pinta de los ganchos (spec 2026-10-09 §4.1 y §5) y lo que la ruta revisa antes de pedir:
    los generables, su precio, por qué no se ofrece el botón (o None) y las tandas. UNA consulta a tw_gancho, y una a
    la cola solo si hay variantes vivas: una barra se pinta solo si su trabajo sigue vivo (ruling 4)."""
    r = fila.get("resultado") or {}
    generables = ganchos_tw.ganchos_generables(r)
    filas = datos.ganchos_de_analisis(cliente, fila["id"])
    precio = gastos.estimar_ganchos_tw(len(generables))
    motivo = ganchos_tw.puede_probar(fila, generables, filas, precio["usd"], mejorar._url_voz(fila.get("foto") or {}))
    tandas = ganchos_tw.tandas(filas)
    vivos = cola.job_ids_vivos_todos() if any(f["estado"] in datos.VIVOS_GANCHO for f in filas) else set()
    for t in tandas:
        for g in t["filas"]:
            g["barra"] = g["estado"] in datos.VIVOS_GANCHO and bool(g.get("job_id")) and g["job_id"] in vivos
    ultima = tandas[0]["filas"] if tandas else []
    return {"generables": generables, "n": len(generables), "precio": precio, "motivo": motivo,
            "sin_precio": motivo == ganchos_tw.MOTIVO_SIN_PRECIO, "ultima": ultima, "anteriores": tandas[1:],
            "esperan": any(g["estado"] in datos.VIVOS_GANCHO and not g["barra"] for g in ultima)}


def _respuesta_ganchos(cliente, ok, mensaje, estado=200):
    """JSON {"ok", "mensaje"} al fetch de la pestaña (que nunca reenvía el POST); al formulario, aviso y vuelta."""
    if _quiere_json():
        return {"ok": ok, "mensaje": mensaje}, estado
    flash(mensaje, "ok" if ok else "warn")
    return _volver(cliente)
```

`analisis_detalle` pasa además el contexto de los ganchos:

```python
@bp.get(f"/analisis/<int(max={AID_MAX}):aid>")
def analisis_detalle(cliente, aid):
    fila = _analisis_listo(cliente, aid)
    r = fila["resultado"] or {}
    item = _aprendizaje_de(cliente, fila)
    return render_template("_tw_analisis.html", cliente=cliente, fila=fila, r=r,
                           guardado=_aprendizaje_guardado(cliente, aid), alcance_nombre=_nombre_alcance(cliente, fila),
                           aprendizaje_texto=item["texto"] if item else None,
                           cifras_aprendizaje=mejorar.cifras_del_aprendizaje(r),
                           gh=_contexto_ganchos(cliente, fila))
```

Después de `analisis_aprendizaje`:

```python
@bp.post(f"/analisis/<int(max={AID_MAX}):aid>/ganchos")
def ganchos_probar(cliente, aid):
    """«Probar los N ganchos» (spec 2026-10-09 §4.3). Revisa §4.1 (409 con el motivo), compara `precio_visto` (es
    PRECIO: vuelve a costo una vez) con el recalculado ±0,005 (409 «El precio cambió…»), pide el total al libro
    (SaldoInsuficiente sube al manejador común: 402 / «Recargar saldo», sin guardar ni encolar), crea la tanda
    (TandaViva → 409) y encola su preparación con un job_id determinista. Si el encolado falla, la tanda queda en
    error con el motivo (en el idioma del proyecto) y el botón vuelve."""
    fila = datos.analisis_anuncio(cliente, aid)
    if fila is None:
        abort(404)
    gh = _contexto_ganchos(cliente, fila)
    if gh["motivo"]:
        motivo = gh["motivo"]
        return _respuesta_ganchos(cliente, False, gettext(motivo), 409)
    usd = gh["precio"]["usd"]
    visto = gastos.costo_de_precio(request.form.get("precio_visto"))
    if visto is None or abs(visto - usd) > 0.005:
        return _respuesta_ganchos(cliente, False, gettext(
            "El precio cambió: ahora es %(precio)s. Revisa y vuelve a pedirlo.",
            precio=gastos.formatear(gastos.precio(usd))), 409)
    libro.exigir(cliente, usd)
    try:
        filas = datos.crear_tanda(cliente, aid, gh["generables"], pedido_por=session.get("usuario"))
    except datos.TandaViva:
        return _respuesta_ganchos(cliente, False, gettext("Ya hay una tanda de ganchos en curso para este análisis."), 409)
    tanda = filas[0]["tanda"]
    job_id = tareas_tw.job_id_preparar(cliente, aid, tanda)
    for g in filas:
        datos.actualizar_gancho(g["id"], job_id=job_id)
    try:
        encolada = tareas_tw.encolar_preparar(cliente, aid, tanda)
    except Exception as e:  # noqa: BLE001 — sin tarea nadie terminaría la tanda: queda en error y el botón vuelve
        log.warning("ganchos: no se pudo encolar la tanda %s del análisis %s (%s)", tanda, aid, type(e).__name__)
        encolada = False
    if not encolada:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):          # lo que se guarda, en el idioma del proyecto
            error = gettext("No se pudo poner la preparación en la cola.")
        for g in filas:
            datos.mover(g["id"], "preparando", "error", error=error)
        return _respuesta_ganchos(cliente, False, gettext("No se pudo poner la preparación en la cola: vuelve a intentarlo."), 409)
    return _respuesta_ganchos(cliente, True, ngettext("Generando %(num)s gancho…", "Generando %(num)s ganchos…", len(filas)))
```

- [ ] **Step 4: Implementar la plantilla del detalle**

En `templates/_tw_analisis.html`, el comentario de arriba suma «Spec 2026-10-09 §5: ganchos nuevos (con el botón y
las variantes de la última tanda) y copy nuevo para Meta.». Después del bloque `{% if r.cambios %}…{% endif %}` y
ANTES de `{% set v = r.version or {} %}`:

```jinja
  {#- Ganchos nuevos (spec 2026-10-09 §5): cada gancho escapado; el botón con su precio, o por qué no se ofrece; las
      variantes de la última tanda (barra solo con su trabajo vivo: ruling 4) y las anteriores en un <details>. -#}
  {% set estados_gancho = {"preparando": _('Preparando'), "generando": _('Generando el clip'), "armando": _('Armando el video'), "produciendo": _('Produciendo')} %}
  {% if 'ganchos' not in r %}
  <p class="vacio tw-ganchos-viejo">{{ _('Este análisis es de antes de los ganchos.') }}</p>
  {% elif r.ganchos %}
  <div class="tw-ganchos-bloque"{% if gh.esperan %} data-tw-ganchos-esperan{% endif %}>
    <h5>{{ _('Ganchos nuevos (primeros 3 s)') }}</h5>
    <ol class="tw-analisis-lista tw-ganchos">{% for x in r.ganchos %}
      <li class="tw-gancho">
        <strong>«{{ x.texto }}»</strong>
        {% if x.escena %}<p class="tw-escena">{{ x.escena }}</p>{% endif %}
        {% if x.por_que %}<small class="vacio">{{ x.por_que }}</small>{% endif %}
        {% if x.cifras_sin_dato %}<p class="tag-advertencia tw-aviso">{{ _('No se genera: cita cifras que no están en los datos (%(cifras)s).', cifras=x.cifras_sin_dato | join(', ')) }}</p>{% endif %}
        <details><summary>{{ _('Prompt del clip') }}</summary><p class="tw-prompt">{{ x.prompt }}</p></details>
      </li>{% endfor %}
    </ol>
    {% if gh.motivo and not gh.sin_precio %}
    <p class="vacio tw-ganchos-motivo">{{ gh.motivo | traducir }}</p>
    {% else %}
    {% set precio_ganchos = _('precio no disponible') if gh.sin_precio else (gh.precio.usd | precio | usd) %}
    <form method="post" class="tw-ganchos-probar" data-tw-ganchos
          action="{{ url_for('triple_whale.ganchos_probar', cliente=cliente, aid=fila.id) }}"
          data-confirmar="{{ ngettext('¿Generar %(num)s clip de 3 s con Kling y armar su video? Costo: %(precio)s', '¿Generar %(num)s clips de 3 s con Kling y armar sus videos? Costo: %(precio)s', gh.n, precio=precio_ganchos) }}">
      <input type="hidden" name="precio_visto" value="{{ '' if gh.sin_precio else gh.precio.usd | precio }}">
      <button type="submit" class="btn-generar btn-sm"{% if gh.sin_precio %} disabled{% endif %}>{{ ngettext('Probar %(num)s gancho · %(precio)s', 'Probar los %(num)s ganchos · %(precio)s', gh.n, precio=precio_ganchos) }}</button>
    </form>
    {% endif %}
    {% if gh.ultima %}
    <div class="tw-variantes">{% for g in gh.ultima %}
      <div class="tw-variante">
        <p class="tw-variante-cabeza"><strong>{{ _('Gancho %(n)s', n=g.n) }}</strong> <code>{{ g.codigo }}</code>
          <button type="button" class="btn-xs" data-copiar="{{ g.codigo }}" onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)">{{ _('Copiar') }}</button></p>
        {% if g.estado == 'lista' %}
        <video controls preload="none" data-precarga src="{{ g.url_final }}"></video>
        <p class="tw-variante-acciones">
          <a href="{{ g.url_final }}" download>{{ _('Descargar') }}</a>
          {% if g.edicion_id %}<a href="{{ url_for('editor.ver', cliente=cliente, edicion_id=g.edicion_id) }}">{{ _('Abrir en el editor') }}</a>{% endif %}
          {% if g.cf_id %}<a href="{{ url_for('ver_cliente', cliente=cliente) }}#creativeflowplus?cf={{ g.cf_id }}">{{ _('Ver en Crear') }}</a>{% endif %}
        </p>
        {% elif g.estado == 'error' %}
        <p class="tag-error">{{ g.error or _('No se pudo hacer este gancho.') }}</p>
        {% else %}
        <div class="tw-progreso">
          {% if g.barra %}<div class="barra-progreso" id="tw-gancho-{{ g.id }}" data-poll-job="{{ g.job_id }}" data-poll-al-terminar="evento"><div class="barra-progreso-fill" style="width:0%"></div></div>{% endif %}
          <div class="progreso-texto">{{ estados_gancho.get(g.estado, g.estado) }}…</div>
        </div>
        {% endif %}
      </div>{% endfor %}
    </div>
    <p class="vacio tw-ganchos-codigo">{{ _('Pon este código en el nombre del anuncio en Meta: así Creatv lo compara con el original.') }}</p>
    {% endif %}
    {% if gh.anteriores %}
    <details class="tw-tandas-anteriores"><summary>{{ ngettext('Antes: %(num)s tanda · ver', 'Antes: %(num)s tandas · ver', gh.anteriores | length) }}</summary>
      <ul>{% for t in gh.anteriores %}{% for g in t.filas %}
        <li><code>{{ g.codigo }}</code> «{{ g.texto }}»
          {% if g.estado == 'lista' %}· <a href="{{ g.url_final }}">{{ _('Ver el video') }}</a>{% if g.edicion_id %} · <a href="{{ url_for('editor.ver', cliente=cliente, edicion_id=g.edicion_id) }}">{{ _('Abrir en el editor') }}</a>{% endif %}
          {% else %}· <span class="vacio">{{ g.error or estados_gancho.get(g.estado, g.estado) }}</span>{% endif %}</li>{% endfor %}{% endfor %}
      </ul>
    </details>
    {% endif %}
  </div>
  {% endif %}
  {#- Copy nuevo para Meta (spec 2026-10-09 §5), antes de la versión mejorada: va en el idioma del anuncio; copiarlo
      es decisión de la persona, así que una cifra sin dato se avisa en vez de esconder el copy. -#}
  {% set cn = r.get('copy_nuevo') %}
  {% if cn %}
  <h5>{{ _('Copy nuevo para Meta') }}</h5>
  <div class="tw-copy-nuevo">
    {% if cn.cifras_sin_dato %}<p class="tag-advertencia tw-aviso">{{ _('Cita cifras que no están en los datos (%(cifras)s): revisa antes de publicar.', cifras=cn.cifras_sin_dato | join(', ')) }}</p>{% endif %}
    {% if cn.titulo %}<p class="tw-copy-campo"><strong>{{ cn.titulo }}</strong>
      <button type="button" class="btn-xs" data-copiar="{{ cn.titulo }}" onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)">{{ _('Copiar el título') }}</button></p>{% endif %}
    <p class="tw-copy-texto">{{ cn.texto }}</p>
    <p class="tw-copy-campo"><button type="button" class="btn-xs" data-copiar="{{ cn.texto }}" onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)">{{ _('Copiar el texto') }}</button></p>
    {% if cn.por_que %}<small class="vacio">{{ cn.por_que }}</small>{% endif %}
  </div>
  {% endif %}
```

(La prueba del detalle cuenta 2 `onclick` porque esa variante no tiene tanda todavía: título y texto del copy.)

- [ ] **Step 5: Implementar el JS de la pestaña**

En `templates/_tab_triple_whale.html`, después de la función `aplicarVeredicto` y antes de `function cargar()`:

```javascript
    // Ganchos nuevos (spec 2026-10-09 §5): el detalle de un análisis se vuelve a pedir cuando termina la barra de una
    // de sus variantes y, mientras una variante viva espera al vigilante (sin trabajo vivo que sondear; el fragmento lo
    // marca con data-tw-ganchos-esperan), cada ESPERA_DETALLE_MS, a lo sumo MAX_ESPERAS veces seguidas sin que una
    // barra termine y solo con el detalle abierto. Nunca un bucle: el servidor no pinta una barra sin trabajo vivo.
    var ESPERA_DETALLE_MS = 20000, MAX_ESPERAS = 30;
    function programarEspera(caja) {
      if (caja.dataset.esperando || !caja.querySelector('[data-tw-ganchos-esperan]')) return;
      var n = parseInt(caja.dataset.esperas || '0', 10);
      if (n >= MAX_ESPERAS) return;
      caja.dataset.esperas = String(n + 1);
      caja.dataset.esperando = '1';
      setTimeout(function () {
        delete caja.dataset.esperando;
        if (caja.isConnected && !caja.hidden) recargarDetalle(caja);
      }, ESPERA_DETALLE_MS);
    }
    // Un aviso corto arriba del detalle (textContent: nunca se interpreta).
    function avisoDetalle(caja, texto) {
      var p = document.createElement('p');
      p.className = 'tag-error';
      p.setAttribute('role', 'status');
      p.textContent = texto;
      caja.insertBefore(p, caja.firstChild);
    }
    function recargarDetalle(caja, aviso) {
      var ver = caja && caja.parentElement ? caja.parentElement.querySelector('[data-tw-ver-analisis]') : null;
      if (!ver) { if (aviso) window.alert(aviso); return; }
      // Las tres variantes de una preparación comparten trabajo: sus barras terminan juntas y basta un pedido.
      if (caja.dataset.recargando) return;
      caja.dataset.recargando = '1';
      fetch(ver.dataset.url, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
        .then(function (html) {
          delete caja.dataset.recargando;
          pintarDetalle(caja, html);
          if (aviso) avisoDetalle(caja, aviso);
        })
        .catch(function () { delete caja.dataset.recargando; avisoDetalle(caja, aviso || T_TW.detalle); });
    }
    function pintarDetalle(caja, html) {
      caja.innerHTML = html;
      caja.dataset.cargado = '1';
      sondear(caja);
      programarEspera(caja);
    }
```

En el clic de `[data-tw-ver-analisis]`, el `.then` que pinta pasa a usar la misma función:

```javascript
          .then(function (html) { pintarDetalle(caja, html); caja.hidden = false; })
```

El oyente de `trabajo-terminado` mira primero si la barra es de una variante:

```javascript
    // La barra de una tarjeta avisa al terminar (data-poll-al-terminar="evento", base.html) en vez de recargar la página.
    // Si es la de una variante de ganchos, se vuelve a pedir solo el detalle (repintar la tarjeta lo cerraría).
    cont.addEventListener('trabajo-terminado', function (ev) {
      var caja = ev.target.closest('.tw-analisis-detalle');
      if (caja) { caja.dataset.esperas = '0'; recargarDetalle(caja); return; }
      repintarTarjeta(ev.target.closest('article.tw-tarjeta'),
                      { falla: T_TW.tarjeta, mensaje: (ev.detail && ev.detail.mensaje) || '' });
    });
```

Y DESPUÉS de ese oyente (antes de `function siActiva()`), un oyente propio para el POST de los ganchos (el de arriba,
que pide la confirmación del precio, no se toca: `test_un_pedido_que_cobra_nunca_se_repite_solo` mide su único
`fetch`):

```javascript
    // «Probar los N ganchos»: el oyente de arriba ya pidió la confirmación del precio (si la persona cancela, el evento
    // llega con defaultPrevented). Un solo POST por clic y nunca repetido: la respuesta, o su falta, solo hace que el
    // detalle se vuelva a pedir y la persona vea el estado real antes de pagar otra vez (regla 1). 402 = sin saldo:
    // static/cobros.js ya pinta «Recargar saldo».
    cont.addEventListener('submit', function (ev) {
      var f = ev.target.closest('form[data-tw-ganchos]');
      if (!f || ev.defaultPrevented) return;
      ev.preventDefault();
      var caja = f.closest('.tw-analisis-detalle');
      f.querySelectorAll('button[type="submit"]').forEach(function (b) { b.disabled = true; });
      fetch(f.action, { method: 'POST', body: new FormData(f),
                        headers: { 'Accept': 'application/json', 'X-Requested-With': 'fetch' } })
        .then(function (r) { return (r.ok || r.status === 402 || r.status === 409) ? r.json() : Promise.reject(r.status); })
        .then(function (d) {
          if (d && !d.ok && d.mensaje) window.alert(d.mensaje);
          recargarDetalle(caja);
        }, function () { recargarDetalle(caja, T_TW.pedido); });
    });
```

- [ ] **Step 6: Implementar los estilos**

En `static/estilos/pantallas/triple-whale.css`, el comentario de arriba suma «y, dentro del detalle `.tw-analisis`,
los ganchos nuevos y el copy para Meta (spec 2026-10-09 §5)». Al final del archivo:

```css
/* Ganchos nuevos y copy para Meta (spec 2026-10-09 §5), dentro del detalle `.tw-analisis` (_tw_analisis.html):
   `.tw-copy-nuevo` (título y texto con «Copiar»), `.tw-ganchos` (los ganchos de Claude), `.tw-ganchos-probar` (el
   botón con su precio), `.tw-variantes`/`.tw-variante` (cada variante de la última tanda: estado, código, video) y
   `.tw-tandas-anteriores`. */
.tw-copy-nuevo { display: flex; flex-direction: column; gap: .35rem; padding: .6rem .7rem; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--panel-2); }
.tw-copy-campo { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin: 0; }
.tw-copy-texto { margin: 0; white-space: pre-line; }
.tw-ganchos { display: flex; flex-direction: column; gap: .5rem; }
.tw-gancho { min-width: 0; }
.tw-gancho p { margin: .2rem 0; }
.tw-ganchos-probar { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; margin: .3rem 0 0; }
.tw-variantes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 12rem), 1fr)); gap: .6rem; margin-top: .4rem; }
.tw-variante { display: flex; flex-direction: column; gap: .35rem; min-width: 0; padding: .5rem; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--panel); }
.tw-variante-cabeza { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin: 0; }
.tw-variante code { overflow-wrap: anywhere; }
.tw-variante video { display: block; width: 100%; max-height: 22rem; border-radius: var(--radius-sm); background: var(--fondo-video); }
.tw-variante-acciones { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0; font-size: .82rem; }
.tw-tandas-anteriores ul { margin: .3rem 0 0; padding-left: 1.1rem; overflow-wrap: anywhere; }
```

Run: `venv/bin/python3 estilos.py construir`

- [ ] **Step 7: Catálogo**

Run: `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py pendientes`
Traduce («Copiar», «Descargar», «Abrir en el editor», «Ver en Crear», «precio no disponible» y «Armando el video»
ya existen):

| msgid | msgstr |
|---|---|
| El precio cambió: ahora es %(precio)s. Revisa y vuelve a pedirlo. | The price changed: it's now %(precio)s. Check it and ask again. |
| Ya hay una tanda de ganchos en curso para este análisis. | There's already a batch of hooks in progress for this analysis. |
| No se pudo poner la preparación en la cola. | Couldn't queue the preparation. |
| No se pudo poner la preparación en la cola: vuelve a intentarlo. | Couldn't queue the preparation: try again. |
| Generando %(num)s gancho… / Generando %(num)s ganchos… | Generating %(num)s hook… / Generating %(num)s hooks… |
| Preparando | Preparing |
| Generando el clip | Generating the clip |
| Produciendo | Producing |
| Ganchos nuevos (primeros 3 s) | New hooks (first 3 s) |
| No se genera: cita cifras que no están en los datos (%(cifras)s). | Not generated: it cites figures that aren't in the data (%(cifras)s). |
| Prompt del clip | Clip prompt |
| ¿Generar %(num)s clip de 3 s con Kling y armar su video? Costo: %(precio)s / ¿Generar %(num)s clips de 3 s con Kling y armar sus videos? Costo: %(precio)s | Generate %(num)s 3-second clip with Kling and build its video? Cost: %(precio)s / Generate %(num)s 3-second clips with Kling and build their videos? Cost: %(precio)s |
| Probar %(num)s gancho · %(precio)s / Probar los %(num)s ganchos · %(precio)s | Try %(num)s hook · %(precio)s / Try the %(num)s hooks · %(precio)s |
| Gancho %(n)s | Hook %(n)s |
| No se pudo hacer este gancho. | This hook couldn't be made. |
| Pon este código en el nombre del anuncio en Meta: así Creatv lo compara con el original. | Put this code in the ad's name in Meta: that's how Creatv compares it with the original. |
| Antes: %(num)s tanda · ver / Antes: %(num)s tandas · ver | Before: %(num)s batch · view / Before: %(num)s batches · view |
| Ver el video | Watch the video |
| Copy nuevo para Meta | New copy for Meta |
| Cita cifras que no están en los datos (%(cifras)s): revisa antes de publicar. | It cites figures that aren't in the data (%(cifras)s): check before publishing. |
| Copiar el título | Copy the title |
| Copiar el texto | Copy the text |

Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 8: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tw_ganchos_rutas.py tests/test_tw_tarjetas_js.py tests/test_tw_tarjetas_rutas.py tests/test_tw_tarjetas_cobro.py tests/test_i18n_catalogo.py tests/test_i18n_plantillas.py tests/test_i18n_mensajes.py tests/test_estilos_sistema.py tests/test_movil.py tests/test_tarjetas_ligeras.py`
Expected: PASS. Luego la suite de Triple Whale. Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add triple_whale/rutas.py templates/_tw_analisis.html templates/_tab_triple_whale.html static/estilos/pantallas/triple-whale.css static/style.css tests/test_tw_ganchos_rutas.py tests/test_tw_tarjetas_js.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Triple Whale ganchos: «Probar los 3 ganchos» con su precio, el copy nuevo para Meta y las variantes en el detalle

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: La skill, los pendientes, el spec al día y la suite completa

**Files:**
- Modify: `.claude/skills/triple-whale/SKILL.md` (encabezado: migraciones; sección nueva al final; la línea «Out of
  this change» de las tarjetas)
- Modify: `docs/pendientes.md` (filas PND-180 y PND-182; filas nuevas PND-190 a PND-193)
- Modify: `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md` (los rulings)

**Interfaces:**
- Consumes: todo lo anterior (solo se describe).
- Produces: nada de código.

- [ ] **Step 1: Comprobar el número libre de pendientes**

Run: `grep -o "PND-[0-9]\+" docs/pendientes.md | sort -t- -k2 -n | tail -1`
Expected: `PND-189` (el 2026-10-09). Si salió otro, numera desde el siguiente y usa esos números en los Steps 2 y 3.

- [ ] **Step 2: La skill**

En `.claude/skills/triple-whale/SKILL.md`, la primera línea de contenido dice «migrations 0023, 0024, 0032, 0034 and
0036» y, en «Tarjetas de análisis», la viñeta «Out of this change (spec §13, PND-180 to PND-186)» empieza con «Stage 2
(2026-10-09, below) did «change only the hook» (half of PND-180) and «new Meta copy» (half of PND-182).». Al final del
archivo:

```markdown
## Ganchos y copy (2026-10-09)

Why: Daniel (2026-10-09, «sigue con las siguientes etapas») chose «a new hook» first: an ad that already proved its body
(product, demo, offer) usually loses its money in the first 3 seconds, and regenerating only those seconds costs a
fraction of a new video. Spec `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md`, plan
`docs/superpowers/plans/2026-10-09-tw-ganchos-y-copy.md`, migration 0036 (0035 before merging main on 2026-10-09, which
already had 0035_meta_rendimiento).

- **The analysis brings two more keys.** `mejorar.PROMPT` asks for `ganchos` (exactly 3 when Claude sees video frames,
  `[]` otherwise) and `copy_nuevo` (title + main text for Meta). `parsear(texto, verificable, duracion_s=None)` never
  gets stricter: `_ganchos` keeps up to 3 with `texto` (one line, no control/format chars, ≤ 60) and `prompt` (≤ 1 000),
  `fotograma_s` through `segundo_fotograma` ([0, duration − 1], else half the video; without a duration a number ≥ 0
  stays and preparar re-clamps it against the measured file) and `cifras_sin_dato` of texto + por_que; `_copy_nuevo` is
  None without text and keeps line breaks. Old results have neither key: always read with `.get`. The task passes
  `foto.creativo.duracion_s` and empties `ganchos` when Claude saw no video frames (an image ad gets copy, not hooks).
  Languages: hook text and copy in the AD's language (a Norwegian ad gets Norwegian text even in a Spanish project, an
  explicit exception to «what is saved goes in the project's language»), escena/por_que in the project's, prompts in
  English (`system()` says the three exceptions).
- **Money.** `gastos.estimar_ganchos_tw(n)` = n × Kling O3 Pro image-to-video, 3 s, no sound (US$ 0,336 each); the detail
  shows it with `|precio|usd`, `data-confirmar` and a hidden `precio_visto` (the PRICE, back to cost once with
  `gastos.costo_de_precio`, ±0,005, else 409). A hook with `cifras_sin_dato` is shown with its warning and is neither
  generated nor priced. `libro.exigir` of the total before creating anything; each clip reserves its own when
  `flowplus_lanzar.lanzar` queues it and Crear's closing (`flowplus_video`) charges it. Preparar, vigilar and armar never
  call a paid provider (all three in `TIPOS_EXENTOS_DE_COBRO`); armar and the render are ffmpeg.
- **Table `tw_gancho`** (one row per variant; AUTOINCREMENT because its id IS the code `CV<id>`), single writer
  `triple_whale/datos.py`. `crear_tanda` takes SQLite's write lock (BEGIN IMMEDIATE) BEFORE reading, raises `TandaViva`
  while any row of the analysis is alive and numbers tandas per analysis; UNIQUE (analisis_id, tanda, n). `n` is the
  hook's position in Claude's list (a hook left out keeps the others' numbers). `mover` is a CAS on `estado`, so the
  vigilante and the tasks never advance a variant twice; `actualizar_gancho` never touches `estado`.
- **Flow.** Route `ganchos_probar` (same origin, the analysis of this cliente or 404, `int(max=AID_MAX)`) → task
  `tw_ganchos_preparar` (`<c>__tw_ganchos_<aid>_t<tanda>`, max_intentos=1, prioridad 3): downloads the original with
  `conectores.url.descargar_archivo` only from `mejorar._url_voz`, ffprobe must say mp4/mov (`es_mp4`), stores it as a
  material (origen `triple_whale`, deduped by hash, shown in «Medios»), and for each row WITHOUT `cf_id` extracts the
  frame at `fotograma_s` (`-ss` before `-i`) to `clientes/<c>/triple_whale/ganchos/<gid>.jpg`, creates the Crear session
  like `tareas.cadena.lanzar_escena` (kling_o3_pro, `imagen_inicial`, 3 s, no sound, `tw_gancho={gancho_id, analisis_id,
  original_hash}`), writes `cf_id` BEFORE launching and launches with prioridad 3. `SaldoInsuficiente` mid-way: that row
  and the rest → error with `frase_proyecto()`; the launched ones go on. The periodic `tw_ganchos_vigilar` (60 s, after
  `cadena_vigilar`) moves `generando` → `armando` when the session is `video_listo` (enqueues `tw_gancho_armar`,
  `<c>__tw_gancho_<gid>_armar`, max_intentos=2, prioridad 1), `produciendo` → `lista`/`error` from the final, and closes a
  `preparando`/`armando` row whose job is gone after `GRACIA_S` (120 s) without changes (the route stores the job_id
  right after creating the rows, so a fresh row has a moment with no job in the queue). `tw_gancho_armar` builds the
  edition (`ganchos.documento_gancho`), runs `verificar_recortes`, `versionar` and `rutas_editor.encolar_producciones`
  (the same tail as the editor's «Producir»); only its last attempt writes the error to the row.
- **The document.** `v0` = the clip from 0 to g = min(clip, 3 000 ms), `v1` = the original from g to its end (both
  muted), the original's WHOLE audio in its own track `p_original` (rol `sonido`) from 0, and the hook text (literal,
  `borrador.ESTILO_HOOK`/`POS_HOOK`) from 0 to g: at second g the same seconds of the original are seen and heard and
  the voice stays in sync. Not in `p_sonido`: the editor's `normalizar` rebuilds `p_sonido` as a mirror of the
  principal on every operation (`sincronizarSonido`), which would silence the first 3 s the first time someone edits the
  text. Format = the closest of `documento.FORMATOS`; destino = the store's country if it is in `tipos.PAISES`, else the
  project's, else CO; `origen = {"tipo": "triple_whale", "pais", "analisis_id", "gancho_id"}`.
- **Screen** (`_tw_analisis.html`, by fetch, no `<script>`): «Copy nuevo para Meta» (copy buttons; a warning with figures
  not in the data, «revisa antes de publicar»), «Ganchos nuevos (primeros 3 s)» with the button or the reason in words
  (`ganchos.puede_probar`), and the latest tanda's variants (state, code with «Copiar», `<video preload="none"
  data-precarga>`, download, editor, Crear); older tandas fold into one `<details>`. Variant rows come in ONE query
  (`ganchos_de_analisis`); a bar is painted only when its job is alive in the queue (`cola.job_ids_vivos_todos`): a bar
  over a finished job would fire `trabajo-terminado` at once and the tab would re-ask the detail in a loop. The tab JS
  re-asks the detail when a variant's bar ends and, while a live variant waits for the vigilante
  (`data-tw-ganchos-esperan`), every 20 s, at most 30 times. The POST is one fetch after the price confirmation and is
  never repeated (`tests/test_tw_tarjetas_js.py`).
- **The code.** `ganchos.codigo(gid) = "CV<gid>"`; `codigo_en(nombre)` (regex `\bCV(\d+)\b`, case-insensitive) is written
  and tested for stage 3, which will read it from the ad name in the sync to compare v1 with v2 ring by ring.
- **Out of this change** (spec §11): the chip on the gallery card (PND-190), «Volver a analizar» for an old analysis
  (PND-191), hooks for image ads (PND-192), the hooks in Meta paused with their code (PND-193).
```

- [ ] **Step 3: Los pendientes**

En `docs/pendientes.md`:
- PND-180: «Qué es» empieza con «Mitad «Cambiar solo el gancho» hecha el 2026-10-09 (spec
  2026-10-09-tw-ganchos-y-copy-design.md, rama `tw-ganchos`: tres ganchos por análisis, cada uno un anuncio con su código
  `CV<id>`). Queda: comparar la versión lanzada con el original anillo por anillo; la etapa 3 lee el código del nombre
  del anuncio en la sincronización (`triple_whale.ganchos.codigo_en`).» y el resto de la descripción sigue; «Estado»
  pasa a `decidido sin hacer`.
- PND-182: «Qué es» empieza con «Mitad «copy nuevo» hecha el 2026-10-09: el análisis trae `copy_nuevo` (título y texto
  en el idioma del anuncio) con «Copiar». Queda: duplicar el anuncio en Meta con ese copy (toca lo público y la pauta: se
  pregunta a Daniel antes).» y el resto sigue.
- Filas nuevas al final de «Abiertos» (después de PND-189):

```markdown
| PND-190 | Un chip en la tarjeta de la galería de Triple Whale («2 ganchos listos») para ver los ganchos sin abrir el análisis. | `templates/_tw_galeria.html`, `triple_whale/panel.py` (`enriquecer`: leer las variantes de la página en UNA consulta junto a `analisis_de_anuncios`). | sin empezar | higiene | no determinado | 2026-10-09 | spec 2026-10-09-tw-ganchos-y-copy-design.md (§11) |
| PND-191 | «Volver a analizar» para un análisis viejo sin ganchos aunque esté fresco: hoy el panel no ofrece pagar dos veces el mismo alcance (`_pedir_analisis` rechaza uno listo y fresco), así que un análisis del 2026-10-08 nunca tendrá ganchos. | `triple_whale/rutas.py` (`_pedir_analisis`), `triple_whale/panel.py` (`elegir_analisis`). Cobra un análisis nuevo: precio a la vista y `max_intentos=1` (regla 1). | sin empezar | higiene | clientes en producción | 2026-10-09 | spec 2026-10-09-tw-ganchos-y-copy-design.md (§11) |
| PND-192 | Ganchos para anuncios de imagen: otra imagen de portada en vez de un clip. Hoy un anuncio de imagen recibe copy nuevo pero ningún gancho. | `triple_whale/mejorar.py` (`PROMPT`, `_ganchos`), `tareas/triple_whale.py` (`tw_analizar_anuncio` vacía `ganchos` sin fotogramas). Cobra imágenes: precio a la vista. | sin empezar | higiene | no determinado | 2026-10-09 | spec 2026-10-09-tw-ganchos-y-copy-design.md (§11) |
| PND-193 | Subir los 3 ganchos a Meta en pausa con su código en el nombre, si Daniel lo quiere. Hoy la persona los descarga y los sube a mano. | `lanzador.py`, `triple_whale/ganchos.py` (`codigo`). Toca lo público y la pauta: se pregunta a Daniel antes (regla de «Cómo se trabaja» 2). | sin empezar | higiene | no determinado | 2026-10-09 | spec 2026-10-09-tw-ganchos-y-copy-design.md (§11) |
```

- [ ] **Step 4: El spec al día con los rulings**

En `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md`:
- §3.2, la viñeta de `fotograma_s` termina con «Sin duración conocida, un número ≥ 0 se conserva (la preparación lo
  vuelve a acotar contra el video medido) y lo demás es `None`. `parsear` y `analizar` reciben `duracion_s=None`; la
  tarea vacía `ganchos` cuando Claude no vio fotogramas del video.»
- §4.4.3.2, el `tw_gancho={…}` del bloque de código pasa a `tw_gancho={"gancho_id": gid, "analisis_id": aid,
  "original_hash": <hash del material del original>}` y se suma «El `cf_id` se anota en la fila antes de lanzar.»
- §4.5, la viñeta de `preparando` o `armando` suma «… y la fila lleva al menos 120 s sin cambiar (`GRACIA_S`). El detalle
  pinta una barra solo si su trabajo está vivo en la cola; si no, la pestaña vuelve a pedir el detalle cada 20 s, a lo
  sumo 30 veces.»
- §4.6.1, «se busca por hash» suma «(el `original_hash` de la sesión del clip)».
- §4.6.2, la viñeta de la pista `p_sonido` pasa a: «**Pista `p_original`** (tipo audio, rol `sonido`): el audio del
  original entero, desde 0, recorte 0–duración y volumen 1. No va en `p_sonido` porque el editor rehace `p_sonido` como
  espejo de la principal en cada operación (`sincronizarSonido`) y los 3 primeros segundos quedarían mudos. Sin audio en
  el original no hay `p_original`.»
- §4.6.4, «Esos pasos 2 a 4 se extraen» pasa a «Los pasos 3 y 4 se extraen (`versionar` queda en quien llama: la ruta
  conserva su CAS con `version_n`)».
- §11 suma al final de cada viñeta su número (PND-190 a PND-193).

- [ ] **Step 5: La guía y la suite completa**

Run: `venv/bin/python3 -m pytest -q tests/test_guia_agentes.py` y luego la suite entera `venv/bin/python3 -m pytest -q`
(tarda varios minutos).
Expected: PASS, con el número total de pruebas escrito en el resumen de la tarea.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/triple-whale/SKILL.md docs/pendientes.md docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md
git commit -m "Triple Whale ganchos: skill, pendientes PND-190 a 193 y el spec con los rulings de la implementación

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Después del plan (lo hace el orquestador, no un subagente de tarea)

1. **eval-claude** (spec §3.3, skill `eval-claude`): los 4 casos del 2026-10-08
   (`docs/superpowers/evals/2026-10-08-tw-como-mejorarlo.md` es la línea base) con la rama. Gasto ≈ US$ 0,40, menos de
   US$ 1: no se pregunta. Criterio: ningún caso deja de validar; los casos con fotogramas traen 3 ganchos con
   `fotograma_s` entre los segundos vistos; todos traen `copy_nuevo` en el idioma del anuncio. La tarifa
   `analisis_anuncio_tw` (`gastos.TARIFAS`, 0,10) sube a 0,12 solo si el promedio medido, contando las correcciones,
   pasa de 0,10 (y entonces `test_la_tarifa_del_analisis_es_la_medida_en_la_prueba_real` cambia con ella). Informe en
   `docs/superpowers/evals/2026-10-09-tw-ganchos-y-copy.md`.
2. **Prueba real de UNA variante** (≈ US$ 0,34; con el eval queda por debajo de US$ 1): base temporal sembrada de la
   exportación de producción, como el 2026-10-08; preparar con Kling de verdad (confirma que WaveSpeed acepta 3 s en
   imagen a video), vigilar, armar y producir en local. Mirar el mp4: el corte en el segundo 3, la voz en sincronía y el
   texto. Si Kling no acepta 3 s, se para y se le cuenta a Daniel (cambiar a 5 s cambia el precio y el diseño).
3. **Captura** del detalle con el test client (fragmento con datos sembrados: copy, 3 ganchos, una variante en cada
   estado), en escritorio y a 375 px (memoria «ver la UI sin contraseña»).
4. **Revisiones:** `revisor` (contra el spec, con mutaciones), `guardian-gasto` y `auditor-seguridad`.
5. Mezcla a `main` y despliegue con la skill `despliegue`: migración 0036 (era la 0035; renumerada al mezclar main el 2026-10-09) ensayada en una copia; los DOS servicios
   (cambia el worker: tareas y periódica nueva), con la cola vacía comprobada en su propio `ssh`.
