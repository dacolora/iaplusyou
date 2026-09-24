# Biblioteca de referentes — Bloque 1 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar la biblioteca de referentes existiendo y llena: tablas nuevas, importación del swipe file de copycoders (5587 anuncios ya clasificados, imágenes copiadas a R2, firmas traducidas), pestaña **Referentes** de solo lectura con filtros, paginación y ficha, y la página `/admin/referentes` con el botón «Importar».

**Architecture:** Módulo nuevo `referentes/` (`datos.py` único escritor de `referente`, `referente_familia` y `barrido`; `copycoders.py` parseo y traducción; `imagenes.py` descarga + R2), tareas del worker en `tareas/referentes.py` que avanzan por fases y tramos re-encolándose (patrón `tareas/tiendas.py`), Blueprint `referentes/rutas.py` bajo `/cliente/<cliente>/referentes` (protegido por `dashboard._guard_por_cliente` porque la URL lleva `<cliente>`), y dos rutas admin en `dashboard.py`. Sin JS framework: fragmentos HTML por `fetch` como en `sprint_detalle.html`.

**Tech Stack:** Python 3, Flask, SQLAlchemy Core sobre SQLite (`data/creatv.db`), Alembic, requests, Pillow, Anthropic SDK (solo traducción), Cloudflare R2 vía `storage/r2_uploader.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md` (§2.1, §3, §7, §8, §11–§14, §17 bloque 1). Los bloques 2–6 (Recrear, Sprints, Atria, Apify, admin completo) son planes aparte.

## Global Constraints

- Nada genera ni gasta solo: la importación la dispara el admin con un clic; la única llamada pagada de este bloque es la traducción de firmas (≈ US$1 total) y se registra con `gastos.registrar_seguro` bajo el proyecto reservado `_creatv`, tipo `otro`.
- Toda tarea que paga va con `max_intentos=1`. Errores al usuario pasan por `cola.sin_token` + `cola.recortar`.
- `referentes/datos.py` es el ÚNICO escritor de las tres tablas. Solo SQLAlchemy Core; nada de Flask ni proveedores ahí.
- Un anuncio, una fila: `referente.anuncio_id` es UNIQUE global. Un barrido/importación que encuentra un `anuncio_id` existente actualiza `dias`, `variantes`, `ultima_vez`, `activo` (y `cuerpo` si estaba vacío) y conserva `cliente` y la clasificación.
- La biblioteca nunca muestra una URL ajena: solo se listan referentes con `estado_imagen = "ok"` (imagen en nuestro R2, clave `referentes/<anuncio_id>.jpg`).
- Visibilidad: un proyecto ve `cliente IS NULL OR cliente = :cliente`. Nunca lo de otro proyecto.
- Etiquetas en la UI en español: `TOF/MOF/BOF` → «arriba del funnel / medio / abajo del funnel»; `unaware…most-aware` → «inconsciente / consciente del problema / de la solución / del producto / muy consciente». Los nombres de familia se quedan en inglés.
- Sin comentarios que expliquen el QUÉ; comentarios solo para un porqué no obvio. Sin linter: `python3 -m py_compile <archivo>` antes de cada commit. Pruebas: `venv/bin/python3 -m pytest -q tests/<archivo>`.
- Tests sin red: costuras `_bajar` (HTTP) y `_llamar` (Claude) se reemplazan con monkeypatch. Las tablas de test salen de `db.metadata.create_all` (fixture `base_temporal`), por eso cada tabla nueva va en `db.py` además de la migración.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `db.py` (modificar, antes de `kv`) | Declarar `referente_familia`, `barrido`, `referente`. |
| `migrations/versions/0017_referentes.py` (crear) | Las tres tablas en Alembic, `down_revision='0016'`. |
| `referentes/__init__.py` (crear, vacío) | Paquete. |
| `referentes/datos.py` (crear) | Único escritor: familias, upsert de referentes, listado con filtros/paginación, opciones de filtro, barridos, marcado de imágenes y traducciones. |
| `referentes/copycoders.py` (crear) | Bajar la página, extraer `DATA`, normalizar filas, traducir firmas y describir familias (Claude, costura `_llamar`). |
| `referentes/imagenes.py` (crear) | Bajar una imagen (costura `_bajar`), validar con Pillow, subir a R2. |
| `tareas/referentes.py` (crear) | Tarea `referentes_importar_copycoders` por fases (`anuncios` → `imagenes` → `traducir`) con continuaciones; helpers de encolado; hook `al_interrumpir`. |
| `tareas/__init__.py` (modificar `cargar_todas`) | Importar `referentes`. |
| `referentes/rutas.py` (crear) | Blueprint: `contexto(cliente)`, `GET /grid` (fragmento), `GET /<rid>/ficha` (fragmento). |
| `dashboard.py` (modificar) | Registrar el Blueprint, sumar `**referentes_rutas.contexto(cliente)` a `ver_cliente`, rutas `admin_referentes` (GET) y `admin_referentes_importar` (POST). |
| `templates/_tab_referentes.html` (crear) | Cabecera, filtros, contenedor del grid, ficha (`<dialog>`), JS. |
| `templates/_referentes_grid.html` (crear) | Fragmento: tarjetas + «Mostrar más». |
| `templates/_referente_ficha.html` (crear) | Fragmento de la ficha. |
| `templates/admin_referentes.html` (crear) | Tarjeta «Importar» + barra + última importación + totales. |
| `templates/cliente.html`, `templates/_sidebar.html`, `templates/panel.html` (modificar) | Pestaña nueva y enlace admin. |
| `static/style.css` (modificar, al final) | Bloque `.ref-*`. |
| `tests/fixtures/copycoders_swipe.html` (crear) | Página mínima con 3 filas. |
| `tests/test_referentes_datos.py`, `tests/test_referentes_copycoders.py`, `tests/test_referentes_imagenes.py`, `tests/test_tareas_referentes.py`, `tests/test_rutas_referentes.py` (crear) | Pruebas. |

---

### Task 1: Tablas en `db.py` y migración 0017

**Files:**
- Modify: `db.py` (insertar el bloque justo antes de `kv = Table("kv", metadata,`)
- Create: `migrations/versions/0017_referentes.py`
- Test: `tests/test_referentes_datos.py`

**Interfaces:**
- Produces: `db.referente_familia`, `db.barrido`, `db.referente` (Tables). Columnas exactas abajo; `referente.cliente` es NULLable (global), por eso NO usa `_comunes()`.

- [ ] **Step 1: Escribir la prueba que falla (las tablas existen y `anuncio_id` es único)**

Crear `tests/test_referentes_datos.py`:

```python
"""referentes.datos: único escritor de referente / referente_familia / barrido."""
import pytest
import sqlalchemy as sa


def _anuncio(**extra):
    base = {"anuncio_id": "1931355470987046", "pagina_id": "110920097280290", "fuente": "copycoders",
            "marca": "Lulutox Tea", "url_anuncio": "https://www.facebook.com/ads/library/?id=1931355470987046",
            "url_marca": "https://www.facebook.com/ads/library/?view_all_page_id=110920097280290",
            "titular": "WE'RE SAYING GOODBYE", "idioma": "en", "tipo": "imagen",
            "imagen_origen": "https://cdn.tryatria.com/adfiles/m1931355470987046_x.jpeg",
            "dias": 366, "variantes": 15, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Titular gigante estilo ruptura que fabrica urgencia.", "clasificacion": "fuente",
            "extra": {"sweep": "AUG"}}
    base.update(extra)
    return base


def test_tablas_existen_y_anuncio_id_unico(base_temporal):
    import db
    with db.conectar() as con:
        con.execute(db.barrido.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                               fuente="copycoders", consulta={}, tope=0, estado="en_cola", extra={}))
        con.execute(db.referente.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                 anuncio_id="1", fuente="copycoders", tipo="imagen",
                                                 estado_imagen="pendiente", clasificacion="fuente", extra={}))
        with pytest.raises(sa.exc.IntegrityError):
            con.execute(db.referente.insert().values(cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                     anuncio_id="1", fuente="atria", tipo="imagen",
                                                     estado_imagen="pendiente", clasificacion="pendiente", extra={}))
```

- [ ] **Step 2: Correr la prueba y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py::test_tablas_existen_y_anuncio_id_unico`
Expected: FAIL con `AttributeError: module 'db' has no attribute 'barrido'`.

- [ ] **Step 3: Declarar las tablas en `db.py`**

Insertar antes de `kv = Table("kv", metadata,`:

```python
# ---------------------------------------------------- referentes ---
# Biblioteca de referentes (spec 2026-09-23 §3). `cliente` NULL = global de
# Creatv; por eso no usa _comunes() (que exige cliente NOT NULL).

referente_familia = Table("referente_familia", metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(120), nullable=False, unique=True),
    Column("descripcion", Text),
    Column("origen", String(12), nullable=False, default="copycoders"),     # copycoders|claude|admin
    Column("creado_en", String(19), nullable=False),
)

barrido = Table("barrido", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),                              # NULL = global (admin)
    Column("creado_en", String(19), nullable=False),
    Column("actualizado_en", String(19), nullable=False),
    Column("fuente", String(12), nullable=False),                           # copycoders|atria|apify
    Column("consulta", JSON, default=dict),
    Column("tope", Integer, default=0),
    Column("estado", String(12), nullable=False, default="en_cola"),        # en_cola|trayendo|guardando|clasificando|listo|parcial|error
    Column("traidos", Integer, default=0),
    Column("nuevos", Integer, default=0),
    Column("clasificados", Integer, default=0),
    Column("pendientes", Integer, default=0),
    Column("con_imagen", Integer, default=0),
    Column("usd_estimado", Float, default=0.0),
    Column("usd_real", Float, default=0.0),
    Column("llamadas_fuente", Integer, default=0),
    Column("tarea_id", Integer),
    Column("pedido_por", String(40)),
    Column("aviso", Text),
    Column("extra", JSON, default=dict),
)

referente = Table("referente", metadata,
    Column("id", Integer, primary_key=True),
    Column("cliente", String(80), index=True),                              # NULL = global
    Column("creado_en", String(19), nullable=False),
    Column("actualizado_en", String(19), nullable=False),
    Column("anuncio_id", String(40), nullable=False, unique=True),          # id del Ad Library de Meta
    Column("pagina_id", String(40), index=True),                            # id de página de Meta (marca)
    Column("fuente", String(12), nullable=False),                           # copycoders|atria|apify
    Column("marca", String(160)),
    Column("url_anuncio", Text),
    Column("url_marca", Text),
    Column("titular", Text),
    Column("cuerpo", Text),
    Column("idioma", String(5)),
    Column("pais", String(2)),
    Column("tipo", String(8), nullable=False, default="imagen"),            # imagen|video|carrusel
    Column("imagen_url", Text),                                             # copia en R2
    Column("imagen_origen", Text),
    Column("estado_imagen", String(10), nullable=False, default="pendiente"),   # ok|pendiente|error
    Column("dias", Integer),
    Column("variantes", Integer),
    Column("primera_vez", String(10)),
    Column("ultima_vez", String(10)),
    Column("activo", Boolean),
    Column("etiquetas_fuente", JSON, default=dict),
    Column("etapa", String(3)),                                             # TOF|MOF|BOF
    Column("consciencia", String(16)),                                      # unaware|problem-aware|solution-aware|product-aware|most-aware
    Column("familia", String(120)),
    Column("dolor", String(120)),
    Column("firma", Text),
    Column("clasificacion", String(10), nullable=False, default="pendiente"),   # fuente|claude|pendiente|error
    Column("barrido_id", Integer, sa.ForeignKey("barrido.id"), index=True),
    Column("extra", JSON, default=dict),
    sa.Index("ix_referente_filtros", "cliente", "etapa", "consciencia", "familia"),
)
```

- [ ] **Step 4: Escribir la migración**

Crear `migrations/versions/0017_referentes.py`:

```python
"""biblioteca de referentes: referente, referente_familia y barrido

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-23 00:00:00.000000

Bloque 1 del spec docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md (§3).
referente.anuncio_id es UNIQUE global: un anuncio, una fila, venga de la fuente que venga.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('referente_familia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='copycoders'),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre', name='uq_referente_familia_nombre')
    )

    op.create_table('barrido',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=True),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('consulta', sa.JSON(), nullable=True),
        sa.Column('tope', sa.Integer(), server_default='0'),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='en_cola'),
        sa.Column('traidos', sa.Integer(), server_default='0'),
        sa.Column('nuevos', sa.Integer(), server_default='0'),
        sa.Column('clasificados', sa.Integer(), server_default='0'),
        sa.Column('pendientes', sa.Integer(), server_default='0'),
        sa.Column('con_imagen', sa.Integer(), server_default='0'),
        sa.Column('usd_estimado', sa.Float(), server_default='0'),
        sa.Column('usd_real', sa.Float(), server_default='0'),
        sa.Column('llamadas_fuente', sa.Integer(), server_default='0'),
        sa.Column('tarea_id', sa.Integer(), nullable=True),
        sa.Column('pedido_por', sa.String(length=40), nullable=True),
        sa.Column('aviso', sa.Text(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('barrido', schema=None) as batch_op:
        batch_op.create_index('ix_barrido_cliente', ['cliente'], unique=False)

    op.create_table('referente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=True),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.Column('anuncio_id', sa.String(length=40), nullable=False),
        sa.Column('pagina_id', sa.String(length=40), nullable=True),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('marca', sa.String(length=160), nullable=True),
        sa.Column('url_anuncio', sa.Text(), nullable=True),
        sa.Column('url_marca', sa.Text(), nullable=True),
        sa.Column('titular', sa.Text(), nullable=True),
        sa.Column('cuerpo', sa.Text(), nullable=True),
        sa.Column('idioma', sa.String(length=5), nullable=True),
        sa.Column('pais', sa.String(length=2), nullable=True),
        sa.Column('tipo', sa.String(length=8), nullable=False, server_default='imagen'),
        sa.Column('imagen_url', sa.Text(), nullable=True),
        sa.Column('imagen_origen', sa.Text(), nullable=True),
        sa.Column('estado_imagen', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('dias', sa.Integer(), nullable=True),
        sa.Column('variantes', sa.Integer(), nullable=True),
        sa.Column('primera_vez', sa.String(length=10), nullable=True),
        sa.Column('ultima_vez', sa.String(length=10), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=True),
        sa.Column('etiquetas_fuente', sa.JSON(), nullable=True),
        sa.Column('etapa', sa.String(length=3), nullable=True),
        sa.Column('consciencia', sa.String(length=16), nullable=True),
        sa.Column('familia', sa.String(length=120), nullable=True),
        sa.Column('dolor', sa.String(length=120), nullable=True),
        sa.Column('firma', sa.Text(), nullable=True),
        sa.Column('clasificacion', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('barrido_id', sa.Integer(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('anuncio_id', name='uq_referente_anuncio')
    )
    with op.batch_alter_table('referente', schema=None) as batch_op:
        batch_op.create_index('ix_referente_cliente', ['cliente'], unique=False)
        batch_op.create_index('ix_referente_pagina_id', ['pagina_id'], unique=False)
        batch_op.create_index('ix_referente_barrido_id', ['barrido_id'], unique=False)
        batch_op.create_index('ix_referente_filtros', ['cliente', 'etapa', 'consciencia', 'familia'], unique=False)
        batch_op.create_foreign_key('fk_referente_barrido', 'barrido', ['barrido_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('referente')
    op.drop_table('barrido')
    op.drop_table('referente_familia')
```

- [ ] **Step 5: Correr la prueba y la migración en una base temporal**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py::test_tablas_existen_y_anuncio_id_unico`
Expected: PASS.

Run: `CREATV_DB_URL=sqlite:////tmp/creatv_mig_test.db venv/bin/alembic upgrade head && CREATV_DB_URL=sqlite:////tmp/creatv_mig_test.db venv/bin/alembic downgrade 0016 && rm -f /tmp/creatv_mig_test.db`
Expected: las dos corridas terminan sin error (`migrations/env.py` toma la URL de `db.url()`, que lee `CREATV_DB_URL`).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile db.py migrations/versions/0017_referentes.py
git add db.py migrations/versions/0017_referentes.py tests/test_referentes_datos.py
git commit -m "Referentes: tablas referente, referente_familia y barrido (migración 0017)"
```

---

### Task 2: `referentes/datos.py` — familias y upsert de referentes

**Files:**
- Create: `referentes/__init__.py` (vacío)
- Create: `referentes/datos.py`
- Test: `tests/test_referentes_datos.py`

**Interfaces:**
- Produces:
  - Constantes `ETAPAS`, `CONSCIENCIAS`, `FUENTES`, `CLASIFICACIONES`, `ESTADOS_IMAGEN`, `ETIQUETAS_ETAPA` (dict), `ETIQUETAS_CONSCIENCIA` (dict), `POR_PAGINA = 60`, `CLIENTE_CREATV = "_creatv"`.
  - `class ErrorDatos(ValueError)`.
  - `familia_asegurar(nombre, descripcion="", origen="copycoders") -> int` (crea o devuelve; no pisa una descripción existente con vacío).
  - `familias(cliente=None) -> list[dict]` con `id, nombre, descripcion, origen, n` (n = referentes visibles con imagen ok), orden alfabético.
  - `familia_actualizar(familia_id, descripcion) -> bool`.
  - `guardar_referente(anuncio: dict, cliente=None, barrido_id=None) -> tuple[int, bool]` (id, creado).
  - `referente(cliente, referente_id) -> dict | None` (visible para ese cliente).
  - `_a_dict(fila)`, `_texto(v, largo=None)`, `_visible(t, cliente)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_referentes_datos.py`:

```python
def test_familia_asegurar_no_duplica_ni_pisa_descripcion(base_temporal):
    from referentes import datos
    a = datos.familia_asegurar("Blame Transplant", "Culpa a otra cosa, no a la persona.")
    b = datos.familia_asegurar("Blame Transplant", "")
    assert a == b
    f = [x for x in datos.familias() if x["nombre"] == "Blame Transplant"][0]
    assert f["descripcion"] == "Culpa a otra cosa, no a la persona." and f["origen"] == "copycoders" and f["n"] == 0
    assert datos.familia_actualizar(a, "Nueva descripción") and datos.familias()[0]["descripcion"] == "Nueva descripción"
    with pytest.raises(datos.ErrorDatos):
        datos.familia_asegurar("   ")


def test_guardar_referente_crea_y_actualiza_sin_reasignar(base_temporal):
    from referentes import datos
    rid, creado = datos.guardar_referente(_anuncio())
    assert creado is True
    r = datos.referente("acme", rid)
    assert r["cliente"] is None and r["estado_imagen"] == "pendiente" and r["clasificacion"] == "fuente"
    assert r["familia"] == "Price Slash Hero" and r["extra"]["sweep"] == "AUG"
    # Un barrido de cliente encuentra el mismo anuncio: actualiza días/variantes, conserva cliente y clasificación.
    rid2, creado2 = datos.guardar_referente(_anuncio(dias=400, variantes=20, cuerpo="Copy nuevo", clasificacion="pendiente",
                                                     familia=None, etapa=None), cliente="acme", barrido_id=None)
    assert rid2 == rid and creado2 is False
    r = datos.referente("acme", rid)
    assert r["dias"] == 400 and r["variantes"] == 20 and r["cuerpo"] == "Copy nuevo"
    assert r["cliente"] is None and r["clasificacion"] == "fuente" and r["familia"] == "Price Slash Hero"


def test_guardar_referente_valida(base_temporal):
    from referentes import datos
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(anuncio_id=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(fuente="otra"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(imagen_origen=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(etapa="XXX"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(consciencia="dormido"))


def test_referente_privado_solo_lo_ve_su_cliente(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="777"), cliente="acme")
    assert datos.referente("acme", rid)["cliente"] == "acme"
    assert datos.referente("otro", rid) is None
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'referentes'`.

- [ ] **Step 3: Implementar `referentes/datos.py`**

Crear `referentes/__init__.py` vacío y `referentes/datos.py`:

```python
"""
Biblioteca de referentes (spec 2026-09-23): anuncios reales clasificados por
etapa, consciencia, familia y dolor. ÚNICO escritor de `referente`,
`referente_familia` y `barrido`. Solo SQLAlchemy Core sobre data/creatv.db;
nada de Flask ni de proveedores.

Visibilidad: un proyecto ve los referentes globales (cliente NULL) y los
suyos. `anuncio_id` (id del Ad Library de Meta) es único global: un anuncio
que ya existe se actualiza, nunca se duplica ni cambia de dueño.
"""
import math

import sqlalchemy as sa

import db

ETAPAS = ("TOF", "MOF", "BOF")
CONSCIENCIAS = ("unaware", "problem-aware", "solution-aware", "product-aware", "most-aware")
FUENTES = ("copycoders", "atria", "apify")
CLASIFICACIONES = ("fuente", "claude", "pendiente", "error")
ESTADOS_IMAGEN = ("ok", "pendiente", "error")
TIPOS = ("imagen", "video", "carrusel")
ESTADOS_BARRIDO = ("en_cola", "trayendo", "guardando", "clasificando", "listo", "parcial", "error")
ETIQUETAS_ETAPA = {"TOF": "arriba del funnel", "MOF": "medio del funnel", "BOF": "abajo del funnel"}
ETIQUETAS_CONSCIENCIA = {"unaware": "inconsciente", "problem-aware": "consciente del problema",
                         "solution-aware": "consciente de la solución", "product-aware": "consciente del producto",
                         "most-aware": "muy consciente"}
POR_PAGINA = 60
CLIENTE_CREATV = "_creatv"

_CAMPOS_ANUNCIO = ("pagina_id", "fuente", "marca", "url_anuncio", "url_marca", "titular", "cuerpo", "idioma", "pais",
                   "tipo", "imagen_origen", "dias", "variantes", "primera_vez", "ultima_vez", "activo",
                   "etiquetas_fuente", "etapa", "consciencia", "familia", "dolor", "firma", "clasificacion", "extra")
_ACTUALIZABLES = ("dias", "variantes", "ultima_vez", "activo")
_CLASIFICACION = ("etapa", "consciencia", "familia", "dolor", "firma")
_BARRIDO_COLS = ("estado", "traidos", "nuevos", "clasificados", "pendientes", "con_imagen", "usd_estimado", "usd_real",
                 "llamadas_fuente", "tarea_id", "aviso", "extra", "consulta", "tope")


class ErrorDatos(ValueError):
    """Dato inválido; el mensaje se muestra tal cual a la persona."""


def _a_dict(fila):
    return dict(fila._mapping)


def _texto(v, largo=None):
    v = (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())
    return v[:largo] if largo else v


def _visible(t, cliente):
    return sa.or_(t.c.cliente.is_(None), t.c.cliente == cliente)


def _entero(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- familias ---

def familia_asegurar(nombre, descripcion="", origen="copycoders"):
    nombre = _texto(nombre, 120)
    if not nombre:
        raise ErrorDatos("La familia necesita un nombre.")
    if origen not in ("copycoders", "claude", "admin"):
        raise ErrorDatos(f"Origen de familia inválido: {origen}")
    descripcion = _texto(descripcion)
    t = db.referente_familia
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.nombre == nombre)).first()
        if f:
            if descripcion and not (f.descripcion or "").strip():
                con.execute(t.update().where(t.c.id == f.id).values(descripcion=descripcion))
            return f.id
        return con.execute(t.insert().values(nombre=nombre, descripcion=descripcion, origen=origen,
                                             creado_en=db.ahora())).inserted_primary_key[0]


def familias(cliente=None):
    t, r = db.referente_familia, db.referente
    conteo = (sa.select(r.c.familia, sa.func.count().label("n"))
              .where(_visible(r, cliente), r.c.estado_imagen == "ok").group_by(r.c.familia).subquery())
    q = (sa.select(t, sa.func.coalesce(conteo.c.n, 0).label("n"))
         .select_from(t.outerjoin(conteo, conteo.c.familia == t.c.nombre)).order_by(t.c.nombre))
    with db.conectar() as con:
        return [_a_dict(f) for f in con.execute(q)]


def familia_actualizar(familia_id, descripcion):
    t = db.referente_familia
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == familia_id).values(descripcion=_texto(descripcion))).rowcount == 1


# -------------------------------------------------------------- referentes ---

def _validar_anuncio(a):
    if not _texto(a.get("anuncio_id"), 40):
        raise ErrorDatos("El anuncio necesita anuncio_id.")
    if a.get("fuente") not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {a.get('fuente')}")
    if not _texto(a.get("imagen_origen")):
        raise ErrorDatos("El anuncio necesita imagen_origen.")
    if a.get("tipo") not in (None, "") + TIPOS:
        raise ErrorDatos(f"Tipo inválido: {a.get('tipo')}")
    if a.get("etapa") not in (None, "") + ETAPAS:
        raise ErrorDatos(f"Etapa inválida: {a.get('etapa')}")
    if a.get("consciencia") not in (None, "") + CONSCIENCIAS:
        raise ErrorDatos(f"Consciencia inválida: {a.get('consciencia')}")
    if a.get("clasificacion") not in (None, "") + CLASIFICACIONES:
        raise ErrorDatos(f"Clasificación inválida: {a.get('clasificacion')}")


def guardar_referente(anuncio, cliente=None, barrido_id=None):
    """Upsert por anuncio_id. Devuelve (id, creado). Si ya existe: actualiza
    dias/variantes/ultima_vez/activo (y cuerpo si estaba vacío); si estaba sin
    clasificar y la fuente trae clasificación, la toma; nunca cambia `cliente`."""
    a = dict(anuncio)
    _validar_anuncio(a)
    aid = _texto(a["anuncio_id"], 40)
    ahora = db.ahora()
    t = db.referente
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.anuncio_id == aid)).first()
        if fila:
            cambios = {k: a[k] for k in _ACTUALIZABLES if a.get(k) is not None}
            if not (fila.cuerpo or "").strip() and _texto(a.get("cuerpo")):
                cambios["cuerpo"] = _texto(a["cuerpo"])
            if fila.clasificacion in ("pendiente", "error") and a.get("clasificacion") == "fuente":
                cambios.update({k: a.get(k) for k in _CLASIFICACION})
                cambios["clasificacion"] = "fuente"
            con.execute(t.update().where(t.c.id == fila.id).values(actualizado_en=ahora, **cambios))
            return fila.id, False
        valores = {k: a.get(k) for k in _CAMPOS_ANUNCIO}
        valores.update(anuncio_id=aid, cliente=cliente, barrido_id=barrido_id, creado_en=ahora, actualizado_en=ahora,
                       tipo=a.get("tipo") or "imagen", estado_imagen="pendiente",
                       clasificacion=a.get("clasificacion") or "pendiente",
                       etiquetas_fuente=a.get("etiquetas_fuente") or {}, extra=a.get("extra") or {},
                       dias=_entero(a.get("dias")), variantes=_entero(a.get("variantes")),
                       marca=_texto(a.get("marca"), 160), titular=_texto(a.get("titular")), cuerpo=_texto(a.get("cuerpo")),
                       familia=_texto(a.get("familia"), 120) or None, dolor=_texto(a.get("dolor"), 120) or None,
                       firma=_texto(a.get("firma")) or None)
        return con.execute(t.insert().values(**valores)).inserted_primary_key[0], True


def referente(cliente, referente_id):
    t = db.referente
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.id == referente_id, _visible(t, cliente))).first()
        return _a_dict(f) if f else None
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py`
Expected: PASS (5 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile referentes/datos.py
git add referentes/__init__.py referentes/datos.py tests/test_referentes_datos.py
git commit -m "Referentes: datos — familias y upsert de referentes por anuncio_id"
```

---

### Task 3: `referentes/datos.py` — listado con filtros, opciones, imágenes, traducciones y barridos

**Files:**
- Modify: `referentes/datos.py` (agregar al final)
- Test: `tests/test_referentes_datos.py`

**Interfaces:**
- Produces:
  - `listar(cliente, filtros=None, pagina=1, por_pagina=POR_PAGINA) -> {"items", "total", "pagina", "paginas"}`; `filtros` acepta `etapa`, `consciencia`, `familia`, `dolor`, `marca`, `fuente` (`copycoders|atria|apify|mios`), `q`. Solo `estado_imagen == "ok"`. Orden: `dias` desc, `variantes` desc, `id` desc.
  - `opciones(cliente) -> {"total": int, "familias": [(nombre, n)], "marcas": [(marca, n)], "dolores": [(dolor, n)], "fuentes": [(fuente, n)]}` (solo con imagen ok; listas ordenadas por n desc, nombre asc).
  - `marcar_imagen(referente_id, estado, imagen_url=None) -> bool`.
  - `pendientes_imagen(fuente=None, limite=100) -> list[dict]` (estado_imagen `pendiente`, orden id asc).
  - `contar_imagenes(fuente=None) -> {"ok": n, "pendiente": n, "error": n}`.
  - `sin_traducir(limite=100) -> list[dict]` (fuente copycoders, `extra.traducida` falsy, `firma` no vacía).
  - `marcar_traducidas(pares: list[tuple[int, str]]) -> int` (pone `firma` y `extra.traducida=True`).
  - `crear_barrido(cliente, fuente, consulta, tope, pedido_por=None, usd_estimado=0.0) -> int`.
  - `actualizar_barrido(barrido_id, **campos) -> bool` (solo `_BARRIDO_COLS`).
  - `barrido(barrido_id) -> dict | None`, `barridos(cliente=None, fuente=None) -> list[dict]` (orden id desc; `cliente=None` devuelve los globales).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_referentes_datos.py`:

```python
def _sembrar(datos):
    ids = []
    for i, (etapa, cons, fam, dolor, marca) in enumerate([
            ("TOF", "problem-aware", "Villain Made Visible", "bloating", "Primal Queen"),
            ("TOF", "problem-aware", "Blame Transplant", "fatiga", "Neurotoned"),
            ("BOF", "most-aware", "Price Slash Hero", "ninguno-oferta", "Lulutox Tea"),
            ("MOF", "solution-aware", "Value Stack", "bloating", "Primal Queen")]):
        rid, _ = datos.guardar_referente(_anuncio(anuncio_id=str(100 + i), etapa=etapa, consciencia=cons, familia=fam,
                                                  dolor=dolor, marca=marca, titular=f"Titular {i}", dias=10 * (i + 1),
                                                  firma=f"firma {fam}"))
        datos.marcar_imagen(rid, "ok", f"https://r2/referentes/{100 + i}.jpg")
        ids.append(rid)
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="200", titular="Sin imagen"))   # pendiente: no se lista
    ids.append(rid)
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="300", titular="De otro", fuente="atria"), cliente="otro")
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/300.jpg")
    return ids


def test_listar_filtra_pagina_y_respeta_visibilidad(base_temporal):
    from referentes import datos
    _sembrar(datos)
    todo = datos.listar("acme")
    assert todo["total"] == 4 and [r["titular"] for r in todo["items"]] == ["Titular 3", "Titular 2", "Titular 1", "Titular 0"]
    assert datos.listar("acme", {"etapa": "TOF"})["total"] == 2
    assert datos.listar("acme", {"consciencia": "most-aware"})["items"][0]["marca"] == "Lulutox Tea"
    assert datos.listar("acme", {"familia": "Value Stack"})["total"] == 1
    assert datos.listar("acme", {"dolor": "bloating"})["total"] == 2
    assert datos.listar("acme", {"marca": "Primal Queen"})["total"] == 2
    assert datos.listar("acme", {"q": "blame"})["total"] == 1          # busca en firma
    assert datos.listar("acme", {"fuente": "mios"})["total"] == 0 and datos.listar("otro", {"fuente": "mios"})["total"] == 1
    assert datos.listar("otro")["total"] == 5 and datos.listar("acme", {"fuente": "atria"})["total"] == 0
    assert datos.listar("acme", {"etapa": "XXX"})["total"] == 4          # filtro inválido = sin filtro
    p = datos.listar("acme", pagina=2, por_pagina=3)
    assert p["paginas"] == 2 and p["pagina"] == 2 and len(p["items"]) == 1
    assert datos.listar("acme", pagina=99, por_pagina=3)["pagina"] == 2


def test_opciones(base_temporal):
    from referentes import datos
    _sembrar(datos)
    o = datos.opciones("acme")
    assert o["total"] == 4 and o["familias"][0][1] == 1 and len(o["familias"]) == 4
    assert o["marcas"][0] == ("Primal Queen", 2) and ("bloating", 2) in o["dolores"] and o["fuentes"] == [("copycoders", 4)]


def test_imagenes_y_traducciones(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(extra={"firma_original": "giant headline", "traducida": False}))
    assert datos.contar_imagenes() == {"ok": 0, "pendiente": 1, "error": 0}
    assert [r["id"] for r in datos.pendientes_imagen(fuente="copycoders")] == [rid]
    assert datos.marcar_imagen(rid, "error")
    assert datos.pendientes_imagen() == [] and datos.contar_imagenes()["error"] == 1
    with pytest.raises(datos.ErrorDatos):
        datos.marcar_imagen(rid, "rara")
    assert [r["id"] for r in datos.sin_traducir()] == [rid]
    assert datos.marcar_traducidas([(rid, "Titular gigante estilo ruptura")]) == 1
    r = datos.referente("acme", rid)
    assert r["firma"] == "Titular gigante estilo ruptura" and r["extra"]["traducida"] is True and r["extra"]["firma_original"] == "giant headline"
    assert datos.sin_traducir() == []


def test_barridos(base_temporal):
    from referentes import datos
    bid = datos.crear_barrido(None, "copycoders", {"url": "https://x"}, 0, pedido_por="admin")
    b = datos.barrido(bid)
    assert b["estado"] == "en_cola" and b["cliente"] is None and b["consulta"]["url"] == "https://x"
    assert datos.actualizar_barrido(bid, estado="listo", traidos=3, nuevos=2, aviso=None)
    assert datos.barridos(None, fuente="copycoders")[0]["traidos"] == 3 and datos.barridos("acme") == []
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_barrido(bid, cliente="acme")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_barrido(bid, estado="volando")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_barrido("acme", "otra", {}, 10)
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py`
Expected: FAIL con `AttributeError: module 'referentes.datos' has no attribute 'marcar_imagen'` (y similares).

- [ ] **Step 3: Implementar**

Agregar al final de `referentes/datos.py`:

```python
def _condiciones(cliente, filtros):
    f = filtros or {}
    t = db.referente
    cond = [_visible(t, cliente), t.c.estado_imagen == "ok"]
    if f.get("etapa") in ETAPAS:
        cond.append(t.c.etapa == f["etapa"])
    if f.get("consciencia") in CONSCIENCIAS:
        cond.append(t.c.consciencia == f["consciencia"])
    for campo in ("familia", "dolor", "marca"):
        v = _texto(f.get(campo), 160)
        if v:
            cond.append(getattr(t.c, campo) == v)
    fuente = f.get("fuente")
    if fuente == "mios":
        cond.append(t.c.cliente == cliente)
    elif fuente in FUENTES:
        cond.append(t.c.fuente == fuente)
    q = _texto(f.get("q"), 80)
    if q:
        like = f"%{q}%"
        cond.append(sa.or_(t.c.titular.ilike(like), t.c.firma.ilike(like), t.c.marca.ilike(like)))
    return cond


def listar(cliente, filtros=None, pagina=1, por_pagina=POR_PAGINA):
    t = db.referente
    cond = _condiciones(cliente, filtros)
    por_pagina = max(1, int(por_pagina))
    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.count()).select_from(t).where(*cond)).scalar() or 0
        paginas = max(1, math.ceil(total / por_pagina))
        pagina = min(max(1, _entero(pagina) or 1), paginas)
        filas = con.execute(sa.select(t).where(*cond)
                            .order_by(sa.desc(t.c.dias).nulls_last(), sa.desc(t.c.variantes).nulls_last(), t.c.id.desc())
                            .limit(por_pagina).offset((pagina - 1) * por_pagina))
        items = [_a_dict(r) for r in filas]
    return {"items": items, "total": int(total), "pagina": pagina, "paginas": paginas}


def opciones(cliente):
    t = db.referente
    base = [_visible(t, cliente), t.c.estado_imagen == "ok"]

    def _grupo(con, col):
        q = (sa.select(col, sa.func.count().label("n")).where(*base, col.isnot(None), col != "")
             .group_by(col).order_by(sa.desc("n"), col))
        return [(r[0], int(r[1])) for r in con.execute(q)]

    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.count()).select_from(t).where(*base)).scalar() or 0
        return {"total": int(total), "familias": _grupo(con, t.c.familia), "marcas": _grupo(con, t.c.marca),
                "dolores": _grupo(con, t.c.dolor), "fuentes": _grupo(con, t.c.fuente)}


# ---------------------------------------------------------------- imágenes ---

def marcar_imagen(referente_id, estado, imagen_url=None):
    if estado not in ESTADOS_IMAGEN:
        raise ErrorDatos(f"Estado de imagen inválido: {estado}")
    t = db.referente
    valores = {"estado_imagen": estado, "actualizado_en": db.ahora()}
    if imagen_url:
        valores["imagen_url"] = imagen_url
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == referente_id).values(**valores)).rowcount == 1


def pendientes_imagen(fuente=None, limite=100):
    t = db.referente
    q = sa.select(t).where(t.c.estado_imagen == "pendiente")
    if fuente:
        q = q.where(t.c.fuente == fuente)
    with db.conectar() as con:
        return [_a_dict(r) for r in con.execute(q.order_by(t.c.id).limit(limite))]


def contar_imagenes(fuente=None):
    t = db.referente
    q = sa.select(t.c.estado_imagen, sa.func.count()).group_by(t.c.estado_imagen)
    if fuente:
        q = q.where(t.c.fuente == fuente)
    conteo = {e: 0 for e in ESTADOS_IMAGEN}
    with db.conectar() as con:
        for estado, n in con.execute(q):
            if estado in conteo:
                conteo[estado] = int(n)
    return conteo


# ------------------------------------------------------------ traducciones ---

def sin_traducir(limite=100):
    t = db.referente
    q = (sa.select(t).where(t.c.fuente == "copycoders", t.c.firma.isnot(None), t.c.firma != "")
         .order_by(t.c.id).limit(limite * 4))
    with db.conectar() as con:
        filas = [_a_dict(r) for r in con.execute(q)]
    return [r for r in filas if not (r.get("extra") or {}).get("traducida")][:limite]


def marcar_traducidas(pares):
    t = db.referente
    n = 0
    with db.conectar() as con:
        for rid, firma in pares:
            firma = _texto(firma)
            if not firma:
                continue
            f = con.execute(sa.select(t.c.extra).where(t.c.id == rid)).first()
            if not f:
                continue
            extra = dict(f.extra or {})
            extra["traducida"] = True
            n += con.execute(t.update().where(t.c.id == rid)
                             .values(firma=firma, extra=extra, actualizado_en=db.ahora())).rowcount
    return n


# ---------------------------------------------------------------- barridos ---

def crear_barrido(cliente, fuente, consulta, tope, pedido_por=None, usd_estimado=0.0):
    if fuente not in FUENTES:
        raise ErrorDatos(f"Fuente desconocida: {fuente}")
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(db.barrido.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, fuente=fuente, consulta=dict(consulta or {}),
            tope=int(tope or 0), estado="en_cola", traidos=0, nuevos=0, clasificados=0, pendientes=0, con_imagen=0,
            usd_estimado=float(usd_estimado or 0.0), usd_real=0.0, llamadas_fuente=0,
            pedido_por=_texto(pedido_por, 40) or None, extra={})).inserted_primary_key[0]


def actualizar_barrido(barrido_id, **campos):
    malos = set(campos) - set(_BARRIDO_COLS)
    if malos:
        raise ErrorDatos(f"Campos no editables: {', '.join(sorted(malos))}")
    if "estado" in campos and campos["estado"] not in ESTADOS_BARRIDO:
        raise ErrorDatos(f"Estado de barrido inválido: {campos['estado']}")
    t = db.barrido
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == barrido_id)
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def barrido(barrido_id):
    t = db.barrido
    with db.conectar() as con:
        f = con.execute(sa.select(t).where(t.c.id == barrido_id)).first()
        return _a_dict(f) if f else None


def barridos(cliente=None, fuente=None):
    t = db.barrido
    q = sa.select(t).where(t.c.cliente.is_(None) if cliente is None else t.c.cliente == cliente)
    if fuente:
        q = q.where(t.c.fuente == fuente)
    with db.conectar() as con:
        return [_a_dict(r) for r in con.execute(q.order_by(t.c.id.desc()))]
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_datos.py`
Expected: PASS (9 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile referentes/datos.py
git add referentes/datos.py tests/test_referentes_datos.py
git commit -m "Referentes: datos — listado con filtros, opciones, imágenes, traducciones y barridos"
```

---

### Task 4: `referentes/copycoders.py` — extraer y normalizar el swipe file

**Files:**
- Create: `referentes/copycoders.py`
- Create: `tests/fixtures/copycoders_swipe.html`
- Test: `tests/test_referentes_copycoders.py`

**Interfaces:**
- Produces:
  - `URL_SWIPE = "https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/"`.
  - `class FormatoInvalido(RuntimeError)`.
  - `descargar_html(url) -> str` (requests, timeout 60, máx 20 MB).
  - `extraer_datos(html) -> list[dict]` (filas crudas tal como vienen).
  - `normalizar(fila, base_url) -> dict | None` (anuncio para `datos.guardar_referente`; `None` si no hay id o imagen).
  - `DOLOR_ESPECIAL = {"none-offer": "ninguno-oferta", "none-brand": "ninguno-marca"}`.

- [ ] **Step 1: Crear el fixture**

Crear `tests/fixtures/copycoders_swipe.html` (una fila con imagen en Atria, una con imagen relativa, una sin `sig` y con `door` vacío; el array va seguido de otra constante como en la página real):

```html
<!doctype html><html><head><title>The 9-Figure Static Swipe File</title></head><body>
<div id="grid"></div>
<script>
const DATA=[{"file": "lulutox_tea/94b906a823fcb25b.jpg", "img": "https://cdn.tryatria.com/adfiles/m1931355470987046_oCRJWtEuBl0.jpeg", "brand": "Lulutox Tea", "headline": "WE'RE SAYING GOODBYE", "aw": "most-aware", "stage": "BOF", "family": "Price Slash Hero", "days": 366, "variants": 15, "lib": "https://www.facebook.com/ads/library/?id=1931355470987046", "blib": "https://www.facebook.com/ads/library/?active_status=active&view_all_page_id=110920097280290", "door": "none-offer", "sig": "giant breakup-style headline announcing a sale is ending", "sweep": "AUG", "retired": 0},
{"file": "primal_queen/fd281f1918dfb5c3.jpg", "img": "swipe_assets_0803/primal_queen_fd281f1918dfb5c3.jpg.jpg", "brand": "Primal Queen", "headline": "THE BELLY YOU HAD BEFORE KIDS", "aw": "problem-aware", "stage": "TOF", "family": "Self-Diagnosis Chart", "days": 167, "variants": 4, "lib": "https://www.facebook.com/ads/library/?id=1234567890", "blib": "https://www.facebook.com/ads/library/?active_status=active&view_all_page_id=125572610639402", "door": "belly fat", "sig": "checklist of symptoms the reader self-diagnoses with", "sweep": "JUL", "retired": 0},
{"file": "zafira/abc.jpg", "img": "https://cdn.tryatria.com/adfiles/m555_abc.jpeg", "brand": "Zafira Organics", "headline": " ", "aw": "unaware", "stage": "TOF", "family": "Content Camouflage", "days": 231, "variants": 2, "lib": "https://www.facebook.com/ads/library/?id=555", "blib": "https://www.facebook.com/ads/library/?active_status=active&view_all_page_id=999", "door": "", "sig": "", "sweep": "FRESH", "retired": 0}];
const AW={"unaware":"UNAWARE"};
</script></body></html>
```

- [ ] **Step 2: Escribir las pruebas que fallan**

Crear `tests/test_referentes_copycoders.py`:

```python
"""referentes.copycoders: parseo del HTML del swipe file y normalización."""
import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "copycoders_swipe.html")


def _html():
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def test_extraer_datos():
    from referentes import copycoders
    filas = copycoders.extraer_datos(_html())
    assert len(filas) == 3 and filas[0]["brand"] == "Lulutox Tea" and filas[2]["sweep"] == "FRESH"


def test_extraer_datos_formato_raro():
    from referentes import copycoders
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.extraer_datos("<html>sin datos</html>")
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.extraer_datos("<script>const DATA=[{\"brand\": \"x\"}];</script>")   # faltan claves


def test_normalizar():
    from referentes import copycoders
    filas = copycoders.extraer_datos(_html())
    a = copycoders.normalizar(filas[0], copycoders.URL_SWIPE)
    assert a["anuncio_id"] == "1931355470987046" and a["pagina_id"] == "110920097280290" and a["fuente"] == "copycoders"
    assert a["etapa"] == "BOF" and a["consciencia"] == "most-aware" and a["familia"] == "Price Slash Hero"
    assert a["dolor"] == "ninguno-oferta" and a["clasificacion"] == "fuente" and a["tipo"] == "imagen" and a["idioma"] == "en"
    assert a["firma"] == "giant breakup-style headline announcing a sale is ending"
    assert a["extra"] == {"sweep": "AUG", "firma_original": "giant breakup-style headline announcing a sale is ending", "traducida": False}
    assert a["imagen_origen"].startswith("https://cdn.tryatria.com/") and a["dias"] == 366 and a["variantes"] == 15
    b = copycoders.normalizar(filas[1], copycoders.URL_SWIPE)
    assert b["imagen_origen"] == "https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/swipe_assets_0803/primal_queen_fd281f1918dfb5c3.jpg.jpg"
    assert b["dolor"] == "belly fat" and b["titular"] == "THE BELLY YOU HAD BEFORE KIDS"
    c = copycoders.normalizar(filas[2], copycoders.URL_SWIPE)
    assert c["dolor"] is None and c["firma"] is None and c["titular"] == "" and c["extra"]["traducida"] is True


def test_normalizar_descarta_sin_id_o_sin_imagen():
    from referentes import copycoders
    base = {"img": "https://cdn.tryatria.com/x.jpeg", "brand": "M", "headline": "H", "aw": "unaware", "stage": "TOF",
            "family": "F", "days": 1, "variants": 1, "lib": "https://www.facebook.com/ads/library/?id=1", "blib": "",
            "door": "", "sig": "s", "sweep": "AUG", "retired": 0}
    assert copycoders.normalizar({**base, "lib": "https://www.facebook.com/ads/library/"}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "img": ""}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "aw": "rara", "stage": "XXX"}, copycoders.URL_SWIPE)["consciencia"] is None
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_copycoders.py`
Expected: FAIL con `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 4: Implementar**

Crear `referentes/copycoders.py`:

```python
"""
Importación del swipe file de copycoders (spec 2026-09-23 §2.1 y §7). La
página es un solo HTML con `const DATA=[...]` adentro; acá se baja, se
extrae ese array y cada fila se normaliza al anuncio que entiende
`referentes.datos.guardar_referente`. La traducción de firmas y la
descripción de familias van por Claude (`_llamar` es la costura de pruebas).
"""
import json
import re
from urllib.parse import urljoin

import requests

from referentes import datos

URL_SWIPE = "https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/"
MAX_HTML = 20 * 1024 * 1024
CLAVES = ("img", "brand", "headline", "aw", "stage", "family", "days", "variants", "lib", "blib", "door", "sig", "sweep")
DOLOR_ESPECIAL = {"none-offer": "ninguno-oferta", "none-brand": "ninguno-marca"}
_RE_ID = re.compile(r"[?&]id=(\d+)")
_RE_PAGINA = re.compile(r"view_all_page_id=(\d+)")


class FormatoInvalido(RuntimeError):
    """La página no trae el dataset como lo conocemos; no se toca nada."""


def descargar_html(url):
    r = requests.get(url, timeout=60, headers={"User-Agent": "CreatvMachine/1.0"}, stream=True)
    r.raise_for_status()
    trozos, total = [], 0
    for parte in r.iter_content(65536):
        total += len(parte)
        if total > MAX_HTML:
            raise FormatoInvalido("La página pesa más de 20 MB; no parece el swipe file.")
        trozos.append(parte)
    return b"".join(trozos).decode("utf-8", errors="replace")


def extraer_datos(html):
    marca = "const DATA="
    i = html.find(marca)
    if i < 0:
        raise FormatoInvalido("No encontré `const DATA=` en la página.")
    inicio = html.find("[", i)
    if inicio < 0:
        raise FormatoInvalido("El dataset no empieza con un arreglo.")
    profundidad, fin = 0, -1
    for j in range(inicio, len(html)):
        c = html[j]
        if c == "[":
            profundidad += 1
        elif c == "]":
            profundidad -= 1
            if profundidad == 0:
                fin = j
                break
    if fin < 0:
        raise FormatoInvalido("El arreglo del dataset no cierra.")
    try:
        filas = json.loads(html[inicio:fin + 1])
    except ValueError as e:
        raise FormatoInvalido(f"El dataset no es JSON válido: {e}") from e
    if not isinstance(filas, list) or not filas or not isinstance(filas[0], dict):
        raise FormatoInvalido("El dataset está vacío o no es una lista de anuncios.")
    faltan = [k for k in CLAVES if k not in filas[0]]
    if faltan:
        raise FormatoInvalido(f"Al dataset le faltan claves: {', '.join(faltan)}")
    return filas


def _dolor(v):
    v = datos._texto(v, 120)
    if not v:
        return None
    return DOLOR_ESPECIAL.get(v, v)


def normalizar(fila, base_url):
    m = _RE_ID.search(fila.get("lib") or "")
    img = datos._texto(fila.get("img"))
    if not m or not img:
        return None
    pagina = _RE_PAGINA.search(fila.get("blib") or "")
    firma = datos._texto(fila.get("sig")) or None
    etapa = fila.get("stage") if fila.get("stage") in datos.ETAPAS else None
    consciencia = fila.get("aw") if fila.get("aw") in datos.CONSCIENCIAS else None
    return {
        "anuncio_id": m.group(1), "pagina_id": pagina.group(1) if pagina else None, "fuente": "copycoders",
        "marca": datos._texto(fila.get("brand"), 160), "url_anuncio": datos._texto(fila.get("lib")),
        "url_marca": datos._texto(fila.get("blib")) or None, "titular": datos._texto(fila.get("headline")),
        "cuerpo": "", "idioma": "en", "pais": None, "tipo": "imagen", "imagen_origen": urljoin(base_url, img),
        "dias": datos._entero(fila.get("days")), "variantes": datos._entero(fila.get("variants")),
        "primera_vez": None, "ultima_vez": None, "activo": not bool(fila.get("retired")),
        "etiquetas_fuente": {}, "etapa": etapa, "consciencia": consciencia,
        "familia": datos._texto(fila.get("family"), 120) or None, "dolor": _dolor(fila.get("door")), "firma": firma,
        "clasificacion": "fuente",
        "extra": {"sweep": datos._texto(fila.get("sweep"), 12), "firma_original": firma or "", "traducida": firma is None},
    }
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_copycoders.py`
Expected: PASS (4 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile referentes/copycoders.py
git add referentes/copycoders.py tests/fixtures/copycoders_swipe.html tests/test_referentes_copycoders.py
git commit -m "Referentes: extraer y normalizar el swipe file de copycoders"
```

---

### Task 5: `referentes/copycoders.py` — traducir firmas y describir familias con Claude

**Files:**
- Modify: `referentes/copycoders.py` (agregar al final)
- Test: `tests/test_referentes_copycoders.py`

**Interfaces:**
- Produces:
  - `_llamar(texto, max_tokens) -> (texto, tokens_entrada, tokens_salida)` (costura; una llamada a Claude con `generador_prompts.MODEL`).
  - `traducir_firmas(pares: list[tuple[int, str]]) -> (dict[int, str], tokens_entrada, tokens_salida)`; ids que Claude no devuelva quedan fuera.
  - `describir_familias(familias: list[tuple[str, list[str]]]) -> (dict[str, str], tokens_entrada, tokens_salida)`; entrada = (nombre, hasta 3 firmas de ejemplo).
  - `_parsear_json(texto) -> dict` (quita fences ```; reintenta con el trozo `{…}`; lanza `FormatoInvalido`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_referentes_copycoders.py`:

```python
def test_traducir_firmas(monkeypatch):
    from referentes import copycoders
    pedido = {}

    def falso(texto, max_tokens):
        pedido["texto"] = texto
        return ('```json\n{"7": "Titular gigante de despedida", "9": "Lista de síntomas"}\n```', 120, 30)
    monkeypatch.setattr(copycoders, "_llamar", falso)
    trad, ent, sal = copycoders.traducir_firmas([(7, "giant breakup headline"), (9, "symptom checklist"), (11, "x")])
    assert trad == {7: "Titular gigante de despedida", 9: "Lista de síntomas"} and (ent, sal) == (120, 30)
    assert '"7": "giant breakup headline"' in pedido["texto"] and "español" in pedido["texto"]


def test_traducir_firmas_respuesta_rota(monkeypatch):
    from referentes import copycoders
    monkeypatch.setattr(copycoders, "_llamar", lambda texto, max_tokens: ("no es json", 5, 5))
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.traducir_firmas([(1, "a")])
    assert copycoders.traducir_firmas([]) == ({}, 0, 0)


def test_describir_familias(monkeypatch):
    from referentes import copycoders
    monkeypatch.setattr(copycoders, "_llamar",
                        lambda texto, max_tokens: ('{"Blame Transplant": "Culpa a otra cosa.", "Otra": "x"}', 50, 20))
    desc, ent, sal = copycoders.describir_familias([("Blame Transplant", ["you are not lazy", "stop blaming the food"])])
    assert desc == {"Blame Transplant": "Culpa a otra cosa."} and ent == 50
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_copycoders.py`
Expected: FAIL con `AttributeError: ... has no attribute '_llamar'`.

- [ ] **Step 3: Implementar**

Agregar al final de `referentes/copycoders.py`:

```python
# ------------------------------------------------------------ Claude ---

PROMPT_TRADUCIR = """Traduce al español neutro (Latinoamérica) estas descripciones de por qué funciona un anuncio estático. Son frases cortas de marketing; conserva el sentido, los nombres de marca y los términos técnicos (GLP-1, ROAS). Máximo 40 palabras cada una.

Responde SOLO con un objeto JSON: la misma clave (el número) y la traducción como valor. Sin texto antes ni después.

{entrada}"""

PROMPT_FAMILIAS = """Eres director creativo de anuncios estáticos. Cada "familia" es un formato de anuncio recurrente. Para cada una escribe UNA línea en español (máximo 25 palabras) que explique en qué consiste el formato, a partir de su nombre y de las descripciones de ejemplo.

Responde SOLO con un objeto JSON: el nombre exacto de la familia como clave y la descripción como valor. Sin texto antes ni después.

{entrada}"""


def _llamar(texto, max_tokens=4000):
    """Una llamada de texto a Claude; devuelve (texto, tokens_entrada, tokens_salida)."""
    import anthropic
    from generador_prompts import MODEL, _api_key
    client = anthropic.Anthropic(api_key=_api_key())
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": texto}])
    uso = getattr(resp, "usage", None)
    entrada = int(getattr(uso, "input_tokens", 0) or 0)
    salida = int(getattr(uso, "output_tokens", 0) or 0)
    if resp.stop_reason == "refusal":
        raise FormatoInvalido("Claude rechazó la solicitud.")
    return "".join(b.text for b in resp.content if b.type == "text").strip(), entrada, salida


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
            raise FormatoInvalido("Claude no devolvió JSON.")
        try:
            data = json.loads(t[ini:fin + 1])
        except ValueError:
            raise FormatoInvalido("Claude no devolvió JSON válido.")
    if not isinstance(data, dict):
        raise FormatoInvalido("Claude no devolvió un objeto JSON.")
    return data


def traducir_firmas(pares):
    if not pares:
        return {}, 0, 0
    entrada = json.dumps({str(rid): firma for rid, firma in pares}, ensure_ascii=False, indent=0)
    texto, ent, sal = _llamar(PROMPT_TRADUCIR.format(entrada=entrada), max_tokens=max(800, 60 * len(pares)))
    data = _parsear_json(texto)
    validos = {rid for rid, _ in pares}
    resultado = {}
    for k, v in data.items():
        rid = datos._entero(k)
        v = datos._texto(v)
        if rid in validos and v:
            resultado[rid] = " ".join(v.split()[:40])
    return resultado, ent, sal


def describir_familias(familias):
    if not familias:
        return {}, 0, 0
    entrada = json.dumps({nombre: list(ejemplos)[:3] for nombre, ejemplos in familias}, ensure_ascii=False, indent=0)
    texto, ent, sal = _llamar(PROMPT_FAMILIAS.format(entrada=entrada), max_tokens=max(800, 80 * len(familias)))
    data = _parsear_json(texto)
    nombres = {nombre for nombre, _ in familias}
    return {k: datos._texto(v) for k, v in data.items() if k in nombres and datos._texto(v)}, ent, sal
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_copycoders.py`
Expected: PASS (7 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile referentes/copycoders.py
git add referentes/copycoders.py tests/test_referentes_copycoders.py
git commit -m "Referentes: traducir firmas y describir familias de copycoders con Claude"
```

---

### Task 6: `referentes/imagenes.py` — bajar, validar y subir a R2

**Files:**
- Create: `referentes/imagenes.py`
- Test: `tests/test_referentes_imagenes.py`

**Interfaces:**
- Produces:
  - `class ImagenInvalida(RuntimeError)`.
  - `MAX_BYTES = 8 * 1024 * 1024`, `clave_r2(anuncio_id) -> str` (`referentes/<anuncio_id>.jpg`).
  - `_bajar(url) -> bytes` (costura; requests con timeout 20 s y tope de bytes).
  - `guardar_en_r2(anuncio_id, url_origen, carpeta) -> str` (URL pública en R2). Convierte a JPEG RGB, máximo 1600 px por lado, borra el archivo local al terminar.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_referentes_imagenes.py`:

```python
"""referentes.imagenes: descarga (costura _bajar), validación con Pillow y subida a R2 (monkeypatch)."""
import io
import os

import pytest
from PIL import Image


def _png(ancho=2000, alto=1000):
    buf = io.BytesIO()
    Image.new("RGBA", (ancho, alto), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_guardar_en_r2_convierte_a_jpeg_y_limpia(monkeypatch, tmp_path):
    from referentes import imagenes
    subidas = []
    monkeypatch.setattr(imagenes, "_bajar", lambda url: _png())

    def subir(local, clave):
        with Image.open(local) as im:
            subidas.append((clave, im.format, im.size, im.mode))
        return f"https://r2.example/{clave}"
    monkeypatch.setattr(imagenes.r2_uploader, "upload_image", subir)
    url = imagenes.guardar_en_r2("123", "https://cdn/x.png", str(tmp_path))
    assert url == "https://r2.example/referentes/123.jpg"
    assert subidas == [("referentes/123.jpg", "JPEG", (1600, 800), "RGB")]
    assert os.listdir(tmp_path) == []


def test_guardar_en_r2_rechaza_lo_que_no_es_imagen(monkeypatch, tmp_path):
    from referentes import imagenes
    monkeypatch.setattr(imagenes, "_bajar", lambda url: b"<html>no</html>")
    monkeypatch.setattr(imagenes.r2_uploader, "upload_image", lambda local, clave: pytest.fail("no debe subir"))
    with pytest.raises(imagenes.ImagenInvalida):
        imagenes.guardar_en_r2("1", "https://cdn/x", str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_guardar_en_r2_propaga_fallo_de_descarga(monkeypatch, tmp_path):
    from referentes import imagenes

    def falla(url):
        raise imagenes.ImagenInvalida("timeout")
    monkeypatch.setattr(imagenes, "_bajar", falla)
    with pytest.raises(imagenes.ImagenInvalida):
        imagenes.guardar_en_r2("1", "https://cdn/x", str(tmp_path))
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_imagenes.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'referentes.imagenes'`.

- [ ] **Step 3: Implementar**

Crear `referentes/imagenes.py`:

```python
"""
Copia de la imagen de un referente a nuestro R2 (spec 2026-09-23 §6.2): la
biblioteca nunca muestra una URL ajena. `_bajar` es la costura de pruebas.
"""
import io
import os

import requests
from PIL import Image, UnidentifiedImageError

from storage import r2_uploader

MAX_BYTES = 8 * 1024 * 1024
LADO_MAX = 1600
TIMEOUT = 20


class ImagenInvalida(RuntimeError):
    """No se pudo bajar o no es una imagen; la fila queda en estado_imagen=error."""


def clave_r2(anuncio_id):
    return f"referentes/{anuncio_id}.jpg"


def _bajar(url):
    try:
        r = requests.get(url, timeout=TIMEOUT, stream=True, headers={"User-Agent": "CreatvMachine/1.0"})
        r.raise_for_status()
        trozos, total = [], 0
        for parte in r.iter_content(65536):
            total += len(parte)
            if total > MAX_BYTES:
                raise ImagenInvalida("La imagen pesa más de 8 MB.")
            trozos.append(parte)
        return b"".join(trozos)
    except requests.RequestException as e:
        raise ImagenInvalida(f"No se pudo bajar la imagen: {e.__class__.__name__}") from e


def guardar_en_r2(anuncio_id, url_origen, carpeta):
    crudo = _bajar(url_origen)
    try:
        with Image.open(io.BytesIO(crudo)) as im:
            im.load()
            im = im.convert("RGB")
            im.thumbnail((LADO_MAX, LADO_MAX))
            os.makedirs(carpeta, exist_ok=True)
            local = os.path.join(carpeta, f"{anuncio_id}.jpg")
            im.save(local, format="JPEG", quality=88)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImagenInvalida(f"No es una imagen válida: {e.__class__.__name__}") from e
    try:
        return r2_uploader.upload_image(local, clave_r2(anuncio_id))
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_referentes_imagenes.py`
Expected: PASS (3 pruebas).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile referentes/imagenes.py
git add referentes/imagenes.py tests/test_referentes_imagenes.py
git commit -m "Referentes: copiar la imagen de un referente a R2"
```

---

### Task 7: Tarea del worker `referentes_importar_copycoders` por fases

**Files:**
- Create: `tareas/referentes.py`
- Modify: `tareas/__init__.py:46` (`cargar_todas`)
- Test: `tests/test_tareas_referentes.py`

**Interfaces:**
- Consumes: `datos.*` (Task 2–3), `copycoders.*` (Task 4–5), `imagenes.guardar_en_r2` (Task 6), `trabajos.encolar`, `cola.encolar/reportar/sin_token/recortar`, `gastos.registrar_seguro`, `nicho.avatares.costo_real`.
- Produces:
  - `JOB_IMPORTAR = "referentes:importar:copycoders"`, `SUFIJO_CONT = "__cont"`, `TRAMO = 100`, `ETAPAS_IMPORTAR = [("Leyendo la página", 1), ("Guardando anuncios", 2), ("Guardando imágenes", 12), ("Traduciendo", 3)]`.
  - `encolar_importar_copycoders(url=copycoders.URL_SWIPE, pedido_por=None) -> bool` (crea la fila `barrido` y encola; `False` si ya hay una importación viva).
  - `trabajo_importacion() -> str | None` (el `job_id` vivo, con o sin `__cont`).
  - `ejecutar_importar(tarea)` registrada como `referentes_importar_copycoders`; payload `{"url", "barrido_id", "fase": "anuncios"|"imagenes"|"traducir"}`.
  - Carpeta de trabajo: `salidas/referentes/` (creada al vuelo).

Comportamiento por fase:
- `anuncios`: baja la página, extrae, normaliza y guarda cada fila (`guardar_referente`, global); asegura cada familia (`familia_asegurar`); actualiza el barrido (`traidos`, `nuevos`, `estado="guardando"`); encola la continuación con `fase="imagenes"`.
- `imagenes`: hasta `TRAMO` pendientes de fuente copycoders (`pendientes_imagen`); por cada una `guardar_en_r2` → `marcar_imagen(ok, url)` o `marcar_imagen(error)`; reporta `progreso` = ok/(ok+pendiente+error) sobre `contar_imagenes("copycoders")`; si quedan pendientes re-encola la misma fase; si no, encola `fase="traducir"`.
- `traducir`: hasta 3 lotes de `TRAMO` firmas (`sin_traducir`) → `traducir_firmas` → `marcar_traducidas`; registra el gasto real por lote con `costo_real`; luego familias sin descripción (hasta 40 por llamada, con 3 firmas de ejemplo) → `describir_familias` → `familia_actualizar`; si quedan firmas sin traducir re-encola; al terminar `estado="listo"` (o `parcial` con `aviso` si hay imágenes en error), `con_imagen` = ok.
- Cualquier excepción: barrido `estado="error"` (fase `anuncios`) o `"parcial"` (otras) con `aviso = cola.recortar(cola.sin_token(e), 300)`; luego `raise`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_tareas_referentes.py`:

```python
"""tareas.referentes: importación de copycoders por fases, sin red (costuras monkeypatcheadas)."""
import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "copycoders_swipe.html")


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    from referentes import copycoders, imagenes
    from tareas import referentes as tr
    encolados = []
    with open(FIXTURE, encoding="utf-8") as f:
        html = f.read()
    monkeypatch.setattr(copycoders, "descargar_html", lambda url: html)

    def guardar_falso(aid, url, carpeta):
        if aid == "555":
            raise imagenes.ImagenInvalida("no es imagen")
        return f"https://r2/referentes/{aid}.jpg"
    monkeypatch.setattr(imagenes, "guardar_en_r2", guardar_falso)
    monkeypatch.setattr(copycoders, "traducir_firmas", lambda pares: ({rid: f"ES {firma}" for rid, firma in pares}, 100, 40))
    monkeypatch.setattr(copycoders, "describir_familias", lambda fams: ({n: f"Desc {n}" for n, _ in fams}, 30, 10))
    monkeypatch.setattr(tr, "CARPETA", str(tmp_path))
    monkeypatch.setattr(tr.cola, "encolar", lambda tipo, payload, **kw: encolados.append({"tipo": tipo, "payload": payload, **kw}) or 1)
    monkeypatch.setattr(tr.cola, "reportar", lambda *a, **k: None)
    gastos = []
    monkeypatch.setattr(tr.gastos, "registrar_seguro", lambda *a, **k: gastos.append((a, k)))
    return {"tr": tr, "encolados": encolados, "gastos": gastos}


def _tarea(payload, tid=5):
    return {"id": tid, "job_id": "referentes:importar:copycoders", "payload": payload}


def test_encolar_crea_barrido(entorno, monkeypatch):
    from referentes import datos
    tr = entorno["tr"]
    llamadas = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: llamadas.append((job_id, tipo, payload, kw)) or True)
    assert tr.encolar_importar_copycoders(pedido_por="admin") is True
    job_id, tipo, payload, kw = llamadas[0]
    assert job_id == tr.JOB_IMPORTAR and tipo == "referentes_importar_copycoders" and payload["fase"] == "anuncios"
    assert kw["max_intentos"] == 1 and payload["barrido_id"] == datos.barridos(None, "copycoders")[0]["id"]


def test_fase_anuncios(entorno):
    from referentes import datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    msg = tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["traidos"] == 3 and b["nuevos"] == 3 and b["estado"] == "guardando" and b["tarea_id"] == 5
    assert datos.contar_imagenes("copycoders") == {"ok": 0, "pendiente": 3, "error": 0}
    assert {f["nombre"] for f in datos.familias()} == {"Price Slash Hero", "Self-Diagnosis Chart", "Content Camouflage"}
    assert entorno["encolados"][-1]["payload"]["fase"] == "imagenes" and entorno["encolados"][-1]["job_id"].endswith("__cont")
    assert "3" in msg


def test_fases_imagenes_y_traducir(entorno):
    from referentes import datos
    tr = entorno["tr"]
    bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "imagenes"}, tid=6))
    assert datos.contar_imagenes("copycoders") == {"ok": 2, "pendiente": 0, "error": 1}
    assert entorno["encolados"][-1]["payload"]["fase"] == "traducir"
    antes = len(entorno["encolados"])
    tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "traducir"}, tid=7))
    b = datos.barrido(bid)
    assert b["estado"] == "parcial" and "1" in b["aviso"] and b["con_imagen"] == 2
    lista = datos.listar("acme")
    assert lista["total"] == 2 and all(r["firma"].startswith("ES ") for r in lista["items"])
    assert datos.familias()[0]["descripcion"].startswith("Desc ")
    (args, kw), = [g for g in entorno["gastos"] if "traduccion" in g[0][3]][:1]
    assert args[0] == "_creatv" and args[1] == "otro" and kw["proveedor"] == "anthropic"
    assert datos.sin_traducir() == [] and len(entorno["encolados"]) == antes     # todo traducido: no se re-encola


def test_fase_anuncios_falla_deja_error(entorno, monkeypatch):
    from referentes import copycoders, datos
    tr = entorno["tr"]
    monkeypatch.setattr(copycoders, "descargar_html", lambda url: "<html>nada</html>")
    bid = datos.crear_barrido(None, "copycoders", {"url": "https://x"}, 0)
    with pytest.raises(copycoders.FormatoInvalido):
        tr.ejecutar_importar(_tarea({"url": "https://x", "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["estado"] == "error" and "const DATA" in b["aviso"] and entorno["encolados"] == []


def test_reimportar_actualiza_sin_duplicar(entorno):
    from referentes import datos
    tr = entorno["tr"]
    for _ in range(2):
        bid = datos.crear_barrido(None, "copycoders", {"url": tr.copycoders.URL_SWIPE}, 0)
        tr.ejecutar_importar(_tarea({"url": tr.copycoders.URL_SWIPE, "barrido_id": bid, "fase": "anuncios"}))
    b = datos.barrido(bid)
    assert b["traidos"] == 3 and b["nuevos"] == 0 and datos.contar_imagenes("copycoders")["pendiente"] == 3
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_referentes.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'tareas.referentes'`.

- [ ] **Step 3: Implementar la tarea**

Crear `tareas/referentes.py`:

```python
"""
Tareas del worker para la biblioteca de referentes (spec 2026-09-23 §7).
Bloque 1: importar el swipe file de copycoders por fases — `anuncios` (bajar
la página y guardar filas), `imagenes` (tramos de TRAMO copias a R2) y
`traducir` (firmas y descripciones de familias con Claude) — cada tramo se
re-encola a sí mismo (patrón tareas/tiendas.py) para no bloquear al worker.
La única llamada pagada es la traducción: gasto tipo `otro` bajo `_creatv`.
"""
import os
from datetime import datetime, timedelta

import cola
import gastos
import trabajos
from nicho.avatares import costo_real, modelo_actual
from referentes import copycoders, datos, imagenes
from tareas import al_interrumpir, ref_sufijo, registrar

TIPO_IMPORTAR = "referentes_importar_copycoders"
JOB_IMPORTAR = "referentes:importar:copycoders"
SUFIJO_CONT = "__cont"
TRAMO = 100
LOTES_TRADUCCION = 3
FAMILIAS_POR_LLAMADA = 40
ESPERA_CONT = 5
ETAPAS_IMPORTAR = [("Leyendo la página", 1), ("Guardando anuncios", 2), ("Guardando imágenes", 12), ("Traduciendo", 3)]
CARPETA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "salidas", "referentes")


def _job_continuacion(job_id):
    return job_id[:-len(SUFIJO_CONT)] if job_id.endswith(SUFIJO_CONT) else job_id + SUFIJO_CONT


def trabajo_importacion():
    for job in (JOB_IMPORTAR, JOB_IMPORTAR + SUFIJO_CONT):
        if trabajos.en_curso(job):
            return job
    return None


def encolar_importar_copycoders(url=copycoders.URL_SWIPE, pedido_por=None):
    if trabajo_importacion():
        return False
    bid = datos.crear_barrido(None, "copycoders", {"url": url}, 0, pedido_por=pedido_por)
    return trabajos.encolar(JOB_IMPORTAR, TIPO_IMPORTAR, {"url": url, "barrido_id": bid, "fase": "anuncios"},
                            duracion_estimada=2400, etapas=ETAPAS_IMPORTAR, max_intentos=1, prioridad=8)


def _continuar(tarea, payload):
    cuando = (datetime.now() + timedelta(seconds=ESPERA_CONT)).isoformat(timespec="seconds")
    cola.encolar(TIPO_IMPORTAR, payload, job_id=_job_continuacion(tarea.get("job_id") or JOB_IMPORTAR),
                 duracion_estimada=2400, etapas=ETAPAS_IMPORTAR, ejecutar_desde=cuando, max_intentos=1, prioridad=8)


def _fase_anuncios(tarea, p, bid, avanzar):
    avanzar("Leyendo la página")
    html = copycoders.descargar_html(p["url"])
    filas = copycoders.extraer_datos(html)
    avanzar("Guardando anuncios")
    traidos = nuevos = 0
    for i, fila in enumerate(filas, 1):
        a = copycoders.normalizar(fila, p["url"])
        if not a:
            continue
        if a.get("familia"):
            datos.familia_asegurar(a["familia"], origen="copycoders")
        _, creado = datos.guardar_referente(a, cliente=None, barrido_id=bid)
        traidos += 1
        nuevos += int(creado)
        if i % 200 == 0:
            cola.reportar(tarea.get("job_id") or JOB_IMPORTAR, progreso=100.0 * i / len(filas), detalle=f"{i}/{len(filas)}")
    datos.actualizar_barrido(bid, estado="guardando", traidos=traidos, nuevos=nuevos, tarea_id=tarea.get("id"))
    _continuar(tarea, {**p, "fase": "imagenes"})
    return f"{traidos} anuncios leídos ({nuevos} nuevos); siguen las imágenes."


def _fase_imagenes(tarea, p, bid, avanzar):
    avanzar("Guardando imágenes")
    for r in datos.pendientes_imagen(fuente="copycoders", limite=TRAMO):
        try:
            url = imagenes.guardar_en_r2(r["anuncio_id"], r["imagen_origen"], CARPETA)
            datos.marcar_imagen(r["id"], "ok", url)
        except imagenes.ImagenInvalida:
            datos.marcar_imagen(r["id"], "error")
        c = datos.contar_imagenes("copycoders")
        total = sum(c.values()) or 1
        cola.reportar(tarea.get("job_id") or JOB_IMPORTAR, progreso=100.0 * (c["ok"] + c["error"]) / total,
                      detalle=f"{c['ok'] + c['error']}/{total}")
    c = datos.contar_imagenes("copycoders")
    datos.actualizar_barrido(bid, con_imagen=c["ok"])
    if c["pendiente"]:
        _continuar(tarea, {**p, "fase": "imagenes"})
        return f"Imágenes: {c['ok']} listas, {c['pendiente']} por bajar."
    _continuar(tarea, {**p, "fase": "traducir"})
    return f"Imágenes listas: {c['ok']} ({c['error']} fallaron). Sigue la traducción."


def _registrar_traduccion(tarea, bid, lote, ent, sal, detalle):
    usd = costo_real(ent, sal)
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", usd,
                            f"referentes:copycoders:traduccion:b{bid}{ref_sufijo(tarea)}:{lote}",
                            detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})
    b = datos.barrido(bid) or {}
    datos.actualizar_barrido(bid, usd_real=round(float(b.get("usd_real") or 0.0) + usd, 4))


def _fase_traducir(tarea, p, bid, avanzar):
    avanzar("Traduciendo")
    for lote in range(LOTES_TRADUCCION):
        pendientes = datos.sin_traducir(limite=TRAMO)
        if not pendientes:
            break
        trad, ent, sal = copycoders.traducir_firmas([(r["id"], r["firma"]) for r in pendientes])
        datos.marcar_traducidas(list(trad.items()))
        _registrar_traduccion(tarea, bid, f"firmas{lote}", ent, sal, "traducción de firmas copycoders")
        if not trad:
            break
    familias = [f for f in datos.familias() if not (f["descripcion"] or "").strip()]
    if familias:
        ejemplos = {}
        for f in familias[:FAMILIAS_POR_LLAMADA]:
            ejemplos[f["nombre"]] = [r["firma"] for r in datos.listar_por_familia(f["nombre"], limite=3) if r.get("firma")]
        desc, ent, sal = copycoders.describir_familias(list(ejemplos.items()))
        for f in familias:
            if f["nombre"] in desc:
                datos.familia_actualizar(f["id"], desc[f["nombre"]])
        _registrar_traduccion(tarea, bid, f"familias{len(familias)}", ent, sal, "descripción de familias copycoders")
    if datos.sin_traducir(limite=1) or len(familias) > FAMILIAS_POR_LLAMADA:
        _continuar(tarea, {**p, "fase": "traducir"})
        return "Traduciendo firmas…"
    c = datos.contar_imagenes("copycoders")
    aviso = f"{c['error']} imágenes no se pudieron bajar; «Reintentar imágenes» las vuelve a pedir." if c["error"] else None
    datos.actualizar_barrido(bid, estado="parcial" if c["error"] else "listo", con_imagen=c["ok"], aviso=aviso)
    return f"Importación terminada: {c['ok']} referentes con imagen."


@registrar(TIPO_IMPORTAR)
def ejecutar_importar(tarea):
    p = tarea["payload"]
    bid = int(p["barrido_id"])
    fase = p.get("fase") or "anuncios"
    job = tarea.get("job_id") or JOB_IMPORTAR

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    try:
        if fase == "anuncios":
            return _fase_anuncios(tarea, p, bid, avanzar)
        if fase == "imagenes":
            return _fase_imagenes(tarea, p, bid, avanzar)
        return _fase_traducir(tarea, p, bid, avanzar)
    except Exception as e:
        datos.actualizar_barrido(bid, estado="error" if fase == "anuncios" else "parcial",
                                 aviso=cola.recortar(cola.sin_token(e), 300))
        raise


@al_interrumpir(TIPO_IMPORTAR)
def interrumpida_importar(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("barrido_id"):
        datos.actualizar_barrido(int(p["barrido_id"]), estado="parcial", aviso=cola.recortar(mensaje, 300))
```

La fase `traducir` usa `datos.listar_por_familia(nombre, limite)`, que no existe aún. Agregar a `referentes/datos.py` (sección referentes):

```python
def listar_por_familia(familia, limite=3):
    t = db.referente
    with db.conectar() as con:
        return [_a_dict(r) for r in con.execute(sa.select(t).where(t.c.familia == familia, t.c.firma.isnot(None))
                                                   .order_by(sa.desc(t.c.variantes).nulls_last()).limit(limite))]
```

Y en `tareas/__init__.py` cambiar la línea de `cargar_todas` por:

```python
    from tareas import director, edicion, experimentos, final_edition, flowplus, investigacion, meta, nicho, organico, referentes, sprints, swap, tiendas  # noqa: F401
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_referentes.py tests/test_referentes_datos.py`
Expected: PASS. Si `test_fases_imagenes_y_traducir` falla en la última aserción por el orden de encolado, revisar que tras `traducir` con todo traducido NO se encole otra continuación (la condición `datos.sin_traducir(limite=1)` debe ser vacía porque el falso `traducir_firmas` traduce todo).

- [ ] **Step 5: Correr toda la suite rápida para ver que nada se rompió**

Run: `venv/bin/python3 -m pytest -q -m "not slow"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile tareas/referentes.py tareas/__init__.py referentes/datos.py
git add tareas/referentes.py tareas/__init__.py referentes/datos.py tests/test_tareas_referentes.py
git commit -m "Referentes: tarea del worker que importa copycoders por fases (anuncios, imágenes, traducción)"
```

---

### Task 8: Blueprint `referentes/rutas.py` — contexto, grid y ficha

**Files:**
- Create: `referentes/rutas.py`
- Create: `templates/_referentes_grid.html`
- Create: `templates/_referente_ficha.html`
- Modify: `dashboard.py` (registro del Blueprint junto a nicho, ~línea 177; `**referentes_rutas.contexto(cliente)` al final de `ver_cliente`, ~línea 1524)
- Test: `tests/test_rutas_referentes.py`

**Interfaces:**
- Produces:
  - `bp = Blueprint("referentes", __name__, url_prefix="/cliente/<cliente>/referentes")`.
  - `contexto(cliente) -> {"ref_opciones": datos.opciones(cliente), "ref_etapas": ETAPAS, "ref_consciencias": CONSCIENCIAS, "ref_etiquetas_etapa", "ref_etiquetas_consciencia", "ref_fuentes": FUENTES}`.
  - `filtros_desde(args) -> dict` (toma `etapa, consciencia, familia, dolor, marca, fuente, q` de `request.args`).
  - `GET /grid?…&pagina=N` → `_referentes_grid.html` con `pagina` (dict de `datos.listar`), `filtros`, `cliente`.
  - `GET /<int:rid>/ficha` → `_referente_ficha.html` con `r`, `familia` (dict o None); 404 si no es visible.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_rutas_referentes.py`:

```python
"""Rutas del Blueprint referentes: grid y ficha como fragmentos; visibilidad por cliente."""
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
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [
        {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo", "representativa_url": "https://r2/e.jpg"}])
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def _anuncio(aid, **extra):
    base = {"anuncio_id": aid, "pagina_id": "1", "fuente": "copycoders", "marca": "Lulutox Tea",
            "url_anuncio": f"https://www.facebook.com/ads/library/?id={aid}", "titular": f"Titular {aid}", "idioma": "en",
            "tipo": "imagen", "imagen_origen": "https://cdn/x.jpg", "dias": 10, "variantes": 2, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Firma en español", "clasificacion": "fuente", "extra": {}}
    base.update(extra)
    return base


def _sembrar(cliente=None):
    from referentes import datos
    datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    ids = []
    for i in range(3):
        rid, _ = datos.guardar_referente(_anuncio(str(i), etapa="TOF" if i else "BOF"), cliente=cliente)
        datos.marcar_imagen(rid, "ok", f"https://r2/referentes/{i}.jpg")
        ids.append(rid)
    return ids


def test_grid_filtra_y_pagina(app):
    _sembrar()
    c = app["c"]
    html = c.get("/cliente/acme/referentes/grid").data.decode()
    assert html.count("ref-tarjeta") >= 3 and "Titular 2" in html and "Mostrar más" not in html
    html = c.get("/cliente/acme/referentes/grid?etapa=TOF").data.decode()
    assert "Titular 0" not in html and "Titular 1" in html
    html = c.get("/cliente/acme/referentes/grid?por_pagina=2").data.decode()
    assert "Mostrar más" in html and 'data-siguiente="2"' in html
    html = c.get("/cliente/acme/referentes/grid?por_pagina=2&pagina=2").data.decode()
    assert html.count("ref-tarjeta") >= 1 and "Mostrar más" not in html
    assert "abajo del funnel" in c.get("/cliente/acme/referentes/grid?etapa=BOF").data.decode()


def test_ficha_y_visibilidad(app):
    from referentes import datos
    ids = _sembrar()
    privado, _ = datos.guardar_referente(_anuncio("99"), cliente="otro")
    datos.marcar_imagen(privado, "ok", "https://r2/referentes/99.jpg")
    c = app["c"]
    html = c.get(f"/cliente/acme/referentes/{ids[0]}/ficha").data.decode()
    assert "Firma en español" in html and "Precio tachado en grande." in html and "facebook.com/ads/library" in html
    assert "muy consciente" in html and "Lulutox Tea" in html
    assert c.get(f"/cliente/acme/referentes/{privado}/ficha").status_code == 404
    assert c.get(f"/cliente/otro/referentes/{privado}/ficha").status_code == 200
    assert "Titular 99" not in c.get("/cliente/acme/referentes/grid").data.decode()


def test_pestana_en_pagina_del_proyecto(app):
    _sembrar()
    c = app["c"]
    html = c.get("/cliente/acme").data.decode()
    assert 'data-tab="referentes"' in html and 'id="tab-referentes"' in html and "Price Slash Hero" in html
    assert "Todas las familias" in html and "Solo míos" in html      # el conteo lo pinta el grid por fetch


def test_cliente_sin_permiso_no_entra(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.get("/cliente/acme/referentes/grid")
    assert r.status_code == 302 and "/cliente/otro" in r.headers["Location"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_referentes.py`
Expected: FAIL (404 en `/grid`, y `data-tab="referentes"` ausente).

- [ ] **Step 3: Crear el Blueprint**

Crear `referentes/rutas.py`:

```python
"""
Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Solo lectura en el
bloque 1: fragmentos HTML para el grid (filtros + paginación) y la ficha.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
`<cliente>`; la visibilidad (global + propios) la aplica referentes.datos.
"""
from flask import Blueprint, abort, render_template, request

from referentes import datos

bp = Blueprint("referentes", __name__, url_prefix="/cliente/<cliente>/referentes")
_FILTROS = ("etapa", "consciencia", "familia", "dolor", "marca", "fuente", "q")


def contexto(cliente):
    """Lo que necesita _tab_referentes.html. Se llama desde dashboard.ver_cliente."""
    return {"ref_opciones": datos.opciones(cliente), "ref_etapas": datos.ETAPAS, "ref_consciencias": datos.CONSCIENCIAS,
            "ref_etiquetas_etapa": datos.ETIQUETAS_ETAPA, "ref_etiquetas_consciencia": datos.ETIQUETAS_CONSCIENCIA,
            "ref_fuentes": datos.FUENTES}


def filtros_desde(args):
    return {k: (args.get(k) or "").strip() for k in _FILTROS if (args.get(k) or "").strip()}


def _entero(v, defecto):
    try:
        return int(v)
    except (TypeError, ValueError):
        return defecto


@bp.get("/grid")
def grid(cliente):
    filtros = filtros_desde(request.args)
    por_pagina = min(max(1, _entero(request.args.get("por_pagina"), datos.POR_PAGINA)), 120)
    pagina = datos.listar(cliente, filtros, pagina=_entero(request.args.get("pagina"), 1), por_pagina=por_pagina)
    return render_template("_referentes_grid.html", cliente=cliente, pagina=pagina, filtros=filtros, por_pagina=por_pagina,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)


@bp.get("/<int:rid>/ficha")
def ficha(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    return render_template("_referente_ficha.html", cliente=cliente, r=r, familia=familia,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)
```

- [ ] **Step 4: Crear los fragmentos**

`templates/_referentes_grid.html`:

```html
{# Fragmento del grid de Referentes (referentes.grid). Contexto: cliente, pagina
   ({items,total,pagina,paginas}), filtros, por_pagina, etiquetas_*. El JS de
   _tab_referentes.html lo pide por fetch y lo mete en #ref-grid (o anexa las
   tarjetas cuando viene de «Mostrar más»). #}
<p class="ref-conteo" data-total="{{ pagina.total }}">{{ pagina.total }} referente{{ 's' if pagina.total != 1 }}</p>
<div class="ref-tarjetas">
  {% for r in pagina["items"] %}
  <article class="ref-tarjeta" data-id="{{ r.id }}">
    <button type="button" class="ref-tarjeta-media" data-ficha="{{ url_for('referentes.ficha', cliente=cliente, rid=r.id) }}" title="Ver ficha">
      <img src="{{ r.imagen_url }}" alt="" loading="lazy">
    </button>
    <div class="ref-tarjeta-texto">
      <strong title="{{ r.titular }}">{{ r.titular or '(sin titular)' }}</strong>
      <div class="ref-etiquetas">
        <span class="tag-estado ref-marca">{{ r.marca }}</span>
        {% if r.consciencia %}<span class="tag-estado">{{ etiquetas_consciencia.get(r.consciencia, r.consciencia) }}</span>{% endif %}
        {% if r.etapa %}<span class="tag-estado">{{ etiquetas_etapa.get(r.etapa, r.etapa) }}</span>{% endif %}
        {% if r.familia %}<span class="tag-estado ref-familia">{{ r.familia }}</span>{% endif %}
      </div>
      <small>{% if r.dias %}{{ r.dias }} d{% endif %}{% if r.variantes %} · {{ r.variantes }} variante{{ 's' if r.variantes != 1 }}{% endif %} · {{ r.fuente }}</small>
    </div>
  </article>
  {% else %}
  <p class="vacio">Ningún referente coincide con esos filtros.</p>
  {% endfor %}
</div>
{% if pagina.pagina < pagina.paginas %}
<p class="ref-mas"><button type="button" class="btn-guardar btn-sm" data-siguiente="{{ pagina.pagina + 1 }}">Mostrar más</button></p>
{% endif %}
```

`templates/_referente_ficha.html`:

```html
{# Ficha de un referente (referentes.ficha), cargada en el <dialog> de la
   pestaña. Contexto: cliente, r (referente), familia (dict|None), etiquetas_*.
   Los botones de «Recrear con mi producto» llegan en el bloque 2. #}
<div class="generado-modal-cuerpo ref-ficha">
  <div class="detalle-media"><img src="{{ r.imagen_url }}" alt=""></div>
  <div class="detalle-info">
    <h3>{{ r.titular or '(sin titular)' }}</h3>
    <p class="ref-etiquetas">
      <span class="tag-estado ref-marca">{{ r.marca }}</span>
      {% if r.consciencia %}<span class="tag-estado">{{ etiquetas_consciencia.get(r.consciencia, r.consciencia) }}</span>{% endif %}
      {% if r.etapa %}<span class="tag-estado">{{ etiquetas_etapa.get(r.etapa, r.etapa) }}</span>{% endif %}
      {% if r.dolor %}<span class="tag-estado">dolor: {{ r.dolor }}</span>{% endif %}
    </p>
    {% if r.familia %}
    <p><strong>Formato:</strong> {{ r.familia }}{% if familia and familia.descripcion %} — {{ familia.descripcion }}{% endif %}</p>
    {% endif %}
    {% if r.firma %}<p><strong>Por qué funciona:</strong> {{ r.firma }}</p>{% endif %}
    {% if r.cuerpo %}<details><summary>Copy del anuncio</summary><p class="ref-cuerpo">{{ r.cuerpo }}</p></details>{% endif %}
    <p class="vacio">{% if r.dias %}{{ r.dias }} días corriendo{% endif %}{% if r.variantes %} · {{ r.variantes }} variante{{ 's' if r.variantes != 1 }}{% endif %} · fuente: {{ r.fuente }}{% if r.extra and r.extra.sweep %} · barrido {{ r.extra.sweep }}{% endif %}</p>
    <div class="detalle-acciones">
      {% if r.url_anuncio %}<a class="btn-guardar btn-sm" href="{{ r.url_anuncio }}" target="_blank" rel="noopener">Ver en Ad Library →</a>{% endif %}
      {% if r.url_marca %}<a class="btn-guardar btn-sm" href="{{ r.url_marca }}" target="_blank" rel="noopener">Librería viva de la marca →</a>{% endif %}
    </div>
  </div>
</div>
```

- [ ] **Step 5: Registrar el Blueprint y el contexto en `dashboard.py`**

Debajo de `app.register_blueprint(nicho_rutas.bp)` (~línea 178):

```python
from referentes import rutas as referentes_rutas  # noqa: E402  (Blueprint de la pestaña Referentes)
app.register_blueprint(referentes_rutas.bp)
```

Al final de la llamada a `render_template("cliente.html", …)` en `ver_cliente`, después de `**nicho_rutas.contexto(cliente),`:

```python
        **referentes_rutas.contexto(cliente),
```

- [ ] **Step 6: Correr las dos primeras pruebas y la de permiso**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_referentes.py -k "grid or ficha or permiso"`
Expected: PASS (3). `test_pestana_en_pagina_del_proyecto` sigue fallando hasta la Task 9.

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile referentes/rutas.py dashboard.py
git add referentes/rutas.py templates/_referentes_grid.html templates/_referente_ficha.html dashboard.py tests/test_rutas_referentes.py
git commit -m "Referentes: Blueprint con grid filtrable y ficha como fragmentos"
```

---

### Task 9: Pestaña Referentes en la página del proyecto

**Files:**
- Create: `templates/_tab_referentes.html`
- Modify: `templates/cliente.html` (sección nueva tras `tab-nicho`, entrada `referentes:` en el mapa `paneles`)
- Modify: `templates/_sidebar.html` (botón tras «Nicho»)
- Modify: `static/style.css` (bloque `.ref-*` al final)
- Test: `tests/test_rutas_referentes.py::test_pestana_en_pagina_del_proyecto`

**Interfaces:**
- Consumes: `ref_opciones`, `ref_etapas`, `ref_consciencias`, `ref_etiquetas_etapa`, `ref_etiquetas_consciencia`, `ref_fuentes` (Task 8), rutas `referentes.grid` y `referentes.ficha`.
- Comportamiento del JS: al mostrarse la pestaña lee la query del hash (`#referentes?etapa=TOF&familia=…`), la vuelca en los controles y pide el grid; cada cambio de filtro pide el grid y hace `history.replaceState` con `#referentes?…`; «Mostrar más» anexa las tarjetas de la página siguiente; clic en una imagen carga la ficha en el `<dialog>`.

- [ ] **Step 1: Crear `templates/_tab_referentes.html`**

```html
{# Pestaña Referentes (spec 2026-09-23 §8), solo lectura en el bloque 1.
   Contexto (referentes.rutas.contexto): ref_opciones ({total, familias, marcas,
   dolores, fuentes} con conteos), ref_etapas, ref_consciencias,
   ref_etiquetas_etapa, ref_etiquetas_consciencia, ref_fuentes. El grid y la
   ficha se piden por fetch a referentes.grid / referentes.ficha. #}
<div class="panel-cabecera">
  <h2>Referentes</h2>
  <p class="vacio">Anuncios reales que ya funcionaron, clasificados por etapa del funnel, nivel de consciencia, formato y dolor. Elige uno y úsalo como referencia para tus piezas.</p>
</div>

{% if not ref_opciones.total %}
<p class="vacio">Todavía no hay referentes. Creatv importa la biblioteca inicial desde el panel de administrador; después aparecen aquí.</p>
{% else %}
<section class="ref-panel" id="ref-panel" data-grid="{{ url_for('referentes.grid', cliente=cliente) }}">
  <div class="exp-filtros ref-chips" data-filtro="etapa">
    <button type="button" class="chip activo" data-valor="">Todos</button>
    {% for e in ref_etapas %}<button type="button" class="chip" data-valor="{{ e }}">{{ ref_etiquetas_etapa[e] | capitalize }}</button>{% endfor %}
  </div>
  <div class="exp-filtros ref-chips" data-filtro="consciencia">
    <button type="button" class="chip activo" data-valor="">Cualquier consciencia</button>
    {% for c in ref_consciencias %}<button type="button" class="chip" data-valor="{{ c }}">{{ ref_etiquetas_consciencia[c] | capitalize }}</button>{% endfor %}
  </div>
  <div class="ref-selects">
    <select data-filtro="marca"><option value="">Todas las marcas</option>{% for m, n in ref_opciones.marcas %}<option value="{{ m }}">{{ m }} ({{ n }})</option>{% endfor %}</select>
    <select data-filtro="familia"><option value="">Todas las familias</option>{% for f, n in ref_opciones.familias %}<option value="{{ f }}">{{ f }} ({{ n }})</option>{% endfor %}</select>
    <select data-filtro="dolor"><option value="">Cualquier dolor</option>{% for d, n in ref_opciones.dolores %}<option value="{{ d }}">{{ d }} ({{ n }})</option>{% endfor %}</select>
    <select data-filtro="fuente"><option value="">Todas las fuentes</option>{% for f, n in ref_opciones.fuentes %}<option value="{{ f }}">{{ f }} ({{ n }})</option>{% endfor %}<option value="mios">Solo míos</option></select>
    <input type="search" data-filtro="q" placeholder="Buscar en titular, firma o marca" maxlength="80">
  </div>
  <div id="ref-grid" class="ref-grid"><p class="vacio">Cargando referentes…</p></div>
</section>

<dialog class="generado-modal" id="ref-modal">
  <button type="button" class="generado-cerrar" id="ref-modal-cerrar" aria-label="Cerrar">×</button>
  <div id="ref-modal-cuerpo"></div>
</dialog>

<script>
  (function () {
    var panel = document.getElementById('ref-panel');
    if (!panel) return;
    var grid = document.getElementById('ref-grid');
    var modal = document.getElementById('ref-modal');
    var cuerpo = document.getElementById('ref-modal-cuerpo');
    var urlGrid = panel.dataset.grid;
    var filtros = {};
    var cargado = false;

    function leerHash() {
      var h = location.hash || '';
      if (h.indexOf('#referentes') !== 0 || h.indexOf('?') < 0) return {};
      var q = new URLSearchParams(h.slice(h.indexOf('?') + 1)), out = {};
      q.forEach(function (v, k) { if (v) out[k] = v; });
      return out;
    }
    function escribirHash() {
      var q = new URLSearchParams();
      Object.keys(filtros).forEach(function (k) { if (filtros[k]) q.set(k, filtros[k]); });
      var s = q.toString();
      history.replaceState(null, '', '#referentes' + (s ? '?' + s : ''));
    }
    function pintarControles() {
      panel.querySelectorAll('.ref-chips').forEach(function (g) {
        var v = filtros[g.dataset.filtro] || '';
        g.querySelectorAll('.chip').forEach(function (b) { b.classList.toggle('activo', b.dataset.valor === v); });
      });
      panel.querySelectorAll('select[data-filtro], input[data-filtro]').forEach(function (el) {
        el.value = filtros[el.dataset.filtro] || '';
      });
    }
    function pedir(pagina, anexar) {
      var q = new URLSearchParams();
      Object.keys(filtros).forEach(function (k) { if (filtros[k]) q.set(k, filtros[k]); });
      if (pagina > 1) q.set('pagina', pagina);
      fetch(urlGrid + '?' + q.toString(), { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          if (!anexar) { grid.innerHTML = html; return; }
          var tmp = document.createElement('div');
          tmp.innerHTML = html;
          var tarjetas = grid.querySelector('.ref-tarjetas');
          tmp.querySelectorAll('.ref-tarjeta').forEach(function (t) { tarjetas.appendChild(t); });
          var viejo = grid.querySelector('.ref-mas');
          if (viejo) viejo.remove();
          var nuevo = tmp.querySelector('.ref-mas');
          if (nuevo) grid.appendChild(nuevo);
        })
        .catch(function () { grid.innerHTML = '<p class="vacio">No se pudo cargar la biblioteca. Recarga la página.</p>'; });
    }
    function recargar() { escribirHash(); pedir(1, false); }

    panel.querySelectorAll('.ref-chips .chip').forEach(function (b) {
      b.addEventListener('click', function () {
        filtros[b.closest('.ref-chips').dataset.filtro] = b.dataset.valor;
        pintarControles(); recargar();
      });
    });
    panel.querySelectorAll('select[data-filtro]').forEach(function (s) {
      s.addEventListener('change', function () { filtros[s.dataset.filtro] = s.value; recargar(); });
    });
    var buscador = panel.querySelector('input[data-filtro="q"]'), temporizador = null;
    buscador.addEventListener('input', function () {
      clearTimeout(temporizador);
      temporizador = setTimeout(function () { filtros.q = buscador.value.trim(); recargar(); }, 350);
    });
    grid.addEventListener('click', function (ev) {
      var mas = ev.target.closest('[data-siguiente]');
      if (mas) { pedir(parseInt(mas.dataset.siguiente, 10), true); return; }
      var media = ev.target.closest('[data-ficha]');
      if (!media) return;
      fetch(media.dataset.ficha, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (html) { cuerpo.innerHTML = html; modal.showModal(); })
        .catch(function () { alert('No se pudo abrir la ficha.'); });
    });
    document.getElementById('ref-modal-cerrar').addEventListener('click', function () { modal.close(); });
    modal.addEventListener('click', function (ev) { if (ev.target === modal) modal.close(); });

    function iniciar() {
      if (cargado) return;
      cargado = true;
      filtros = leerHash();
      pintarControles();
      pedir(1, false);
    }
    // La pestaña se activa desde cliente.html (clase .activo en #tab-referentes).
    var tab = document.getElementById('tab-referentes');
    if (tab.classList.contains('activo')) iniciar();
    new MutationObserver(function () { if (tab.classList.contains('activo')) iniciar(); })
      .observe(tab, { attributes: true, attributeFilter: ['class'] });
  })();
</script>
{% endif %}
```

- [ ] **Step 2: Enganchar la pestaña en `cliente.html` y `_sidebar.html`**

En `templates/cliente.html`, después de la sección `tab-nicho`:

```html
<section id="tab-referentes" class="tab-panel" role="tabpanel">
  {% include "_tab_referentes.html" %}
</section>
```

y en el mapa `paneles` (después de `nicho: document.getElementById('tab-nicho'),`):

```js
      referentes: document.getElementById('tab-referentes'),
```

En `templates/_sidebar.html`, después del botón «Nicho»:

```html
    <button type="button" class="sidebar-item" data-tab="referentes" role="tab" title="Referentes">
      <svg viewBox="0 0 24 24"><rect x="3" y="4" width="8" height="7" rx="1.5" stroke="currentColor" stroke-width="2" fill="none"/><rect x="13" y="4" width="8" height="7" rx="1.5" stroke="currentColor" stroke-width="2" fill="none"/><rect x="3" y="13" width="8" height="7" rx="1.5" stroke="currentColor" stroke-width="2" fill="none"/><rect x="13" y="13" width="8" height="7" rx="1.5" stroke="currentColor" stroke-width="2" fill="none"/></svg>
      <span class="sidebar-texto">Referentes</span>
    </button>
```

- [ ] **Step 3: CSS**

Al final de `static/style.css`:

```css
/* Referentes — biblioteca (spec 2026-09-23 §8) */
.ref-panel { display:flex; flex-direction:column; gap:.6rem; margin-top:.6rem; }
.ref-selects { display:flex; gap:.5rem; flex-wrap:wrap; }
.ref-selects select, .ref-selects input { font-size:.8rem; max-width:16rem; }
.ref-conteo { color:var(--muted); font-size:.8rem; margin:.2rem 0; }
.ref-tarjetas { display:grid; grid-template-columns:repeat(auto-fill, minmax(190px, 1fr)); gap:.8rem; }
.ref-tarjeta { display:flex; flex-direction:column; gap:.4rem; border-radius:10px; padding:.4rem; background:var(--panel-2); }
.ref-tarjeta-media { display:block; width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:8px; background:#111; border:0; padding:0; cursor:zoom-in; }
.ref-tarjeta-media img { width:100%; height:100%; object-fit:cover; display:block; }
.ref-tarjeta-texto strong { font-size:.82rem; display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ref-tarjeta-texto small { color:var(--muted); font-size:.72rem; }
.ref-etiquetas { display:flex; gap:.3rem; flex-wrap:wrap; }
.ref-etiquetas .tag-estado { font-size:.68rem; }
.ref-marca { background:var(--accent); color:#fff; }
.ref-mas { text-align:center; margin:.8rem 0; }
.ref-ficha .detalle-media img { width:100%; height:auto; border-radius:8px; }
.ref-cuerpo { white-space:pre-wrap; font-size:.82rem; }
@media (max-width: 640px) { .ref-tarjetas { grid-template-columns:repeat(2, 1fr); } .ref-selects select, .ref-selects input { max-width:100%; } }
```

- [ ] **Step 4: Correr las pruebas de rutas**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_referentes.py`
Expected: PASS (4).

- [ ] **Step 5: Verla en el navegador**

Levantar el dashboard con el `preview_start` del proyecto (o `python dashboard.py`), entrar como admin a `/cliente/<un proyecto>`, pestaña **Referentes**: con la base vacía debe verse el mensaje «Todavía no hay referentes». Para ver tarjetas sin importar todavía, sembrar 3 filas con `venv/bin/python3 -c` usando `referentes.datos.guardar_referente` + `marcar_imagen(rid, "ok", "<cualquier URL de imagen pública>")`, recargar y comprobar: chips de etapa/consciencia filtran, los selects filtran, la búsqueda filtra, la ficha abre y cierra, el hash cambia a `#referentes?etapa=TOF`, y al recargar con ese hash los controles quedan marcados. Borrar las filas sembradas al terminar (`DELETE FROM referente` en la base local, solo si son las de prueba).

- [ ] **Step 6: Commit**

```bash
git add templates/_tab_referentes.html templates/cliente.html templates/_sidebar.html static/style.css tests/test_rutas_referentes.py
git commit -m "Referentes: pestaña con filtros, «Mostrar más» y ficha"
```

---

### Task 10: `/admin/referentes` con «Importar swipe file de copycoders»

**Files:**
- Create: `templates/admin_referentes.html`
- Modify: `dashboard.py` (dos rutas junto a `admin_meta`, ~línea 3251), `templates/panel.html:11` (enlace)
- Test: `tests/test_rutas_referentes.py`

**Interfaces:**
- Consumes: `tareas.referentes.encolar_importar_copycoders(url, pedido_por)`, `tareas.referentes.trabajo_importacion()`, `datos.barridos(None, "copycoders")`, `datos.contar_imagenes("copycoders")`, `datos.opciones(None)` (total global), `datos.familias()`, `_mismo_origen()`, `requiere_admin`.
- Produces: rutas `admin_referentes` (GET `/admin/referentes`) y `admin_referentes_importar` (POST `/admin/referentes/importar`, campo opcional `url`, solo `https://go.copycoders.ai/...` o vacío → `URL_SWIPE`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_rutas_referentes.py`:

```python
def test_admin_referentes_importar(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    c = app["c"]
    llamadas = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: llamadas.append(payload) or True)
    monkeypatch.setattr(tr.trabajos, "en_curso", lambda job_id: False)
    html = c.get("/admin/referentes").data.decode()
    assert "Importar" in html and "nunca" in html
    r = c.post("/admin/referentes/importar", data={}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/referentes")
    assert llamadas[0]["url"] == tr.copycoders.URL_SWIPE and llamadas[0]["fase"] == "anuncios"
    b = datos.barridos(None, "copycoders")[0]
    assert b["pedido_por"] == "admin" and b["consulta"]["url"] == tr.copycoders.URL_SWIPE
    r = c.post("/admin/referentes/importar", data={"url": "https://malo.example/x"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and len(llamadas) == 1
    datos.actualizar_barrido(b["id"], estado="listo", traidos=5587, nuevos=5587, con_imagen=5580)
    html = c.get("/admin/referentes").data.decode()
    assert "5587" in html and "5580" in html


def test_admin_referentes_solo_admin(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    assert c.get("/admin/referentes").status_code == 302
    assert c.post("/admin/referentes/importar", data={}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 302
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_referentes.py -k admin`
Expected: FAIL (404 en `/admin/referentes`).

- [ ] **Step 3: Rutas en `dashboard.py`**

Debajo de `admin_meta` y sus POST (~línea 3300, donde termine ese bloque):

```python
# ---------------------------------------------------- admin: referentes ---

@app.route("/admin/referentes")
@requiere_admin
def admin_referentes():
    """Biblioteca de referentes (spec 2026-09-23 §7-§8): importar copycoders y ver totales."""
    from referentes import datos as ref_datos
    from tareas import referentes as tareas_ref
    historial = ref_datos.barridos(None, "copycoders")
    return render_template("admin_referentes.html", url_swipe=tareas_ref.copycoders.URL_SWIPE,
                           trabajo=({"job_id": tareas_ref.trabajo_importacion()} if tareas_ref.trabajo_importacion() else None),
                           ultimo=(historial[0] if historial else None), historial=historial[:10],
                           imagenes=ref_datos.contar_imagenes("copycoders"), total=ref_datos.opciones(None)["total"],
                           familias=ref_datos.familias())


@app.route("/admin/referentes/importar", methods=["POST"])
@requiere_admin
def admin_referentes_importar():
    if not _mismo_origen():
        abort(403)
    from tareas import referentes as tareas_ref
    url = (request.form.get("url") or "").strip() or tareas_ref.copycoders.URL_SWIPE
    if not url.startswith("https://go.copycoders.ai/"):
        flash("Solo se importa desde go.copycoders.ai.", "error")
        return redirect(url_for("admin_referentes"))
    if tareas_ref.encolar_importar_copycoders(url, pedido_por=_sesion().get("usuario")):
        flash("Importando el swipe file; la página se recarga sola cuando termine cada fase.", "ok")
    else:
        flash("Ya hay una importación en curso.", "error")
    return redirect(url_for("admin_referentes"))
```

- [ ] **Step 4: Plantilla `templates/admin_referentes.html`**

```html
{% extends "base.html" %}
{% block title %}Referentes (admin){% endblock %}
{% block content %}
{# Panel admin de la biblioteca de referentes (dashboard.admin_referentes).
   Contexto: url_swipe, trabajo ({job_id}|None), ultimo (barrido|None),
   historial, imagenes ({ok,pendiente,error}), total (referentes globales con
   imagen), familias. #}
<section class="hero aparece">
  <div class="hero-texto">
    <span class="eyebrow">Panel de administrador</span>
    <h1>Biblioteca de referentes.</h1>
    <p class="hero-sub">La semilla es el swipe file de copycoders: se importa desde su página pública, las imágenes se copian a nuestro R2 y las firmas se traducen (≈ US$1 una sola vez). Se puede volver a importar cuando ellos publiquen un barrido nuevo: solo entra lo nuevo.</p>
    <p class="hero-sub"><a href="{{ url_for('panel') }}">← Volver al panel</a></p>
  </div>
  <div class="hero-stats">
    <div class="stat"><span class="stat-num">{{ total }}</span><span class="stat-label">referente{{ 's' if total != 1 }} con imagen</span></div>
    <div class="stat"><span class="stat-num">{{ familias | length }}</span><span class="stat-label">familia{{ 's' if familias | length != 1 }}</span></div>
    <div class="stat"><span class="stat-num">{{ imagenes.pendiente }}</span><span class="stat-label">imágenes por bajar</span></div>
    <div class="stat"><span class="stat-num">{{ imagenes.error }}</span><span class="stat-label">imágenes fallidas</span></div>
  </div>
</section>

<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Swipe file de copycoders</h2></div>
  <form method="post" action="{{ url_for('admin_referentes_importar') }}" class="agencia-form">
    <label>URL <input type="url" name="url" value="{{ url_swipe }}" style="min-width:32rem"></label>
    <button type="submit" class="btn-generar btn-sm" {% if trabajo %}disabled{% endif %}>Importar</button>
  </form>
  <p class="vacio">Última importación:
    {% if ultimo %}{{ ultimo.creado_en }} · estado <strong>{{ ultimo.estado }}</strong> · {{ ultimo.traidos }} leídos · {{ ultimo.nuevos }} nuevos · {{ ultimo.con_imagen }} con imagen{% if ultimo.usd_real %} · US$ {{ '%.2f' | format(ultimo.usd_real) }}{% endif %}{% if ultimo.aviso %} · {{ ultimo.aviso }}{% endif %}
    {% else %}nunca{% endif %}</p>
  {% if trabajo %}
  <div class="barra-progreso" id="trabajo-{{ trabajo.job_id }}"><div class="barra-progreso-fill"></div></div>
  <div class="progreso-texto"></div>
  <script>iniciarPolling({{ trabajo.job_id | tojson }}, {{ ("trabajo-" ~ trabajo.job_id) | tojson }});</script>
  {% endif %}
  {% if historial | length > 1 %}
  <details><summary>Importaciones anteriores</summary>
    <div class="admin-scroll"><table class="tabla-admin">
      <tr><th>Fecha</th><th>Estado</th><th>Leídos</th><th>Nuevos</th><th>Con imagen</th><th>Aviso</th></tr>
      {% for b in historial[1:] %}<tr><td>{{ b.creado_en }}</td><td>{{ b.estado }}</td><td>{{ b.traidos }}</td><td>{{ b.nuevos }}</td><td>{{ b.con_imagen }}</td><td>{{ b.aviso or '' }}</td></tr>{% endfor %}
    </table></div>
  </details>
  {% endif %}
</section>

<section class="admin-bloque">
  <div class="admin-cabecera"><h2>Familias ({{ familias | length }})</h2></div>
  <div class="admin-scroll"><table class="tabla-admin">
    <tr><th>Familia</th><th>Descripción</th><th>Referentes</th><th>Origen</th></tr>
    {% for f in familias %}<tr><td>{{ f.nombre }}</td><td>{{ f.descripcion or '—' }}</td><td>{{ f.n }}</td><td>{{ f.origen }}</td></tr>{% endfor %}
  </table></div>
</section>
{% endblock %}
```

En `templates/panel.html`, después de la línea del enlace a `admin_meta`:

```html
    <p class="hero-sub"><a href="{{ url_for('admin_referentes') }}">Referentes →</a> importar el swipe file de copycoders y ver la biblioteca global.</p>
```

- [ ] **Step 5: Correr todas las pruebas del bloque y la suite rápida**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_referentes.py tests/test_referentes_datos.py tests/test_referentes_copycoders.py tests/test_referentes_imagenes.py tests/test_tareas_referentes.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow"`
Expected: PASS.

- [ ] **Step 6: Importación real, una vez, en local**

Con el `.env` raíz con R2 y `ANTHROPIC_API_KEY`, y `venv/bin/alembic upgrade head` hecho: levantar `python dashboard.py` y `venv/bin/python3 worker.py`, entrar a `/admin/referentes` y pulsar **Importar**. Esperado: la barra avanza por «Leyendo la página» → «Guardando anuncios» (segundos) → «Guardando imágenes» (30–40 min, tramos de 100) → «Traduciendo»; al final «Última importación: … estado listo (o parcial con el aviso) · 5587 leídos»; la pestaña Referentes de cualquier proyecto muestra las tarjetas con imágenes desde R2; Configuración › Gasto NO muestra nada para los proyectos (el gasto quedó bajo `_creatv`). Si la traducción falla por cuota, la importación queda `parcial` y volver a pulsar Importar retoma solo lo pendiente.

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile dashboard.py
git add dashboard.py templates/admin_referentes.html templates/panel.html tests/test_rutas_referentes.py
git commit -m "Referentes: página admin con la importación del swipe file de copycoders"
```

---

### Task 11: CLAUDE.md y cierre del bloque

**Files:**
- Modify: `CLAUDE.md` (párrafo nuevo después del de «Nicho y avatares»)

- [ ] **Step 1: Documentar el módulo en `CLAUDE.md`**

Agregar, después del párrafo «**Nicho y avatares**», este párrafo:

```markdown
**Biblioteca de referentes** (`referentes/` + `tareas/referentes.py`, spec
`docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md`): anuncios
reales clasificados por etapa (TOF/MOF/BOF), consciencia, familia (190 de
copycoders + las que Claude proponga como `EMERGING`), dolor y firma («por qué
funciona»). Tablas `referente` (`anuncio_id` = id del Ad Library de Meta, UNIQUE
global; `cliente` NULL = global de Creatv, `<cliente>` = solo ese proyecto; solo
se lista con `estado_imagen=ok`, la copia en R2 `referentes/<anuncio_id>.jpg`),
`referente_familia` y `barrido`. `referentes/datos.py` es el único escritor.
Bloque 1: importación del swipe file de copycoders (`referentes/copycoders.py`
lee `const DATA=[...]` del HTML público; tarea `referentes_importar_copycoders`
por fases `anuncios → imagenes → traducir` con continuaciones `__cont`, la única
llamada pagada es la traducción de firmas, gasto tipo `otro` bajo `_creatv`) desde
`/admin/referentes`, y la pestaña **Referentes** (`_tab_referentes.html`, Blueprint
`referentes/rutas.py`: `grid` y `ficha` como fragmentos por fetch, filtros en el
hash `#referentes?etapa=TOF&…`). Los bloques siguientes agregan «Recrear con mi
producto», la puerta desde Sprints y los barridos Atria/Apify con clasificación
Claude; hasta entonces la biblioteca es de solo lectura.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: biblioteca de referentes (bloque 1)"
```

- [ ] **Step 3: Entrega**

Seguir `superpowers:finishing-a-development-branch`: suite completa verde (`venv/bin/python3 -m pytest -q`), mezclar a `main`, y en el VPS `alembic upgrade head` + reiniciar gunicorn y `creatv-worker` + pulsar Importar en `/admin/referentes` (spec §14).

---

## Self-review

**Cobertura del spec (bloque 1):** §3 tablas → Task 1; único escritor y upsert → Task 2–3; §2.1/§7 importación (extraer, normalizar, imágenes a R2, traducción, descripciones de familias, repetible, fallo sin tocar lo importado) → Task 4–7; §8 pestaña con filtros en la URL, «Mostrar más», ficha, biblioteca vacía, móvil, etiquetas en español → Task 8–9; §8 admin (importar, última importación, totales, tabla de familias) → Task 10; §11 gasto bajo `_creatv` → Task 7; §12 errores de imagen/formato/interrupción → Task 6–7; §13 pruebas sin red → todas; §14 despliegue → Task 11. Fuera de este bloque (y de este plan): «Reintentar imágenes» como botón (la re-importación ya reintenta las `pendiente`; las `error` quedan para el bloque 6), `Puesta a punto`, barridos, Recrear, Sprints.

**Consistencia de nombres:** `datos.guardar_referente(anuncio, cliente=None, barrido_id=None) -> (id, creado)`, `datos.marcar_imagen(rid, estado, imagen_url=None)`, `datos.contar_imagenes(fuente)`, `datos.pendientes_imagen(fuente, limite)`, `datos.sin_traducir(limite)`, `datos.marcar_traducidas(pares)`, `datos.listar_por_familia(familia, limite)`, `datos.crear_barrido(cliente, fuente, consulta, tope, pedido_por, usd_estimado)`, `datos.actualizar_barrido(bid, **campos)`, `datos.barridos(cliente, fuente)`, `copycoders.descargar_html/extraer_datos/normalizar/traducir_firmas/describir_familias/_llamar`, `imagenes.guardar_en_r2(anuncio_id, url_origen, carpeta)`, `tareas.referentes.encolar_importar_copycoders(url, pedido_por)` / `trabajo_importacion()` / `ejecutar_importar(tarea)` — usados con esos nombres en todas las tareas.
