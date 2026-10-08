# Triple Whale con varias tiendas — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que un proyecto conecte varias tiendas de Triple Whale (una por país), las vea juntas o por separado y
atribuya cada experimento a la tienda de su país.

**Architecture:** tabla nueva `tw_tienda` (una fila por tienda, con su llave); la tabla `triple_whale` queda como
ajustes del proyecto (moneda, modelo, ventana, avisos). Las tres copias diarias ganan `tienda_id`. Las lecturas
aceptan `tienda_id=None` = todas, con el gasto de un mismo anuncio contado una sola vez (MAX entre tiendas) y lo del
Pixel sumado.

**Tech Stack:** Flask, SQLAlchemy Core sobre SQLite, Alembic (`batch_alter_table`), Jinja, Babel, pytest.

**Spec:** `docs/superpowers/specs/2026-10-08-triple-whale-varias-tiendas-design.md` (leerlo entero antes de cada
tarea: los números de sección de abajo apuntan ahí).

## Global Constraints

- Worktree: `.claude/worktrees/tw-varias-tiendas`, rama `tw-varias-tiendas`. Nunca tocar el checkout principal.
- Python: `venv/bin/python3` (el `venv` del worktree es un enlace al del repo). Pruebas:
  `venv/bin/python3 -m pytest -q -m "not slow" <archivos>`.
- Antes de tocar código, cargar las skills `triple-whale` y `plataforma`; además `ui` e `idioma` si se toca una
  plantilla o un texto, `seguridad` si se toca una ruta, `experimentos` si se toca `lanzador.py`.
- Regla 5 de CLAUDE.md: `triple_whale_tiendas.py` es el único escritor de `triple_whale` y `tw_tienda`;
  `triple_whale/datos.py` el único de `tw_*_dia` y `tw_evaluacion`. Lectura-modificación-escritura en una sola
  transacción.
- La llave nunca sale en logs, flashes, eventos ni errores guardados (`cola.sin_token` + tachar la llave de ESA
  tienda).
- Todo texto visible pasa por el catálogo (`_()`, `gettext`, `idiomas.N_`). Los nombres de país salen de Babel.
- Toda tienda se busca con `cliente` + `id`; una de otro proyecto es 404 (aislamiento).
- Celular: nada empuja la página de lado; tablas anchas con scroll propio.
- Cada tarea termina con su commit. Mensaje en español, terminado en
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nunca `git add -A`: añadir archivos por nombre.
- Cada tarea arregla las pruebas existentes que su cambio rompa (`grep -rln "triple_whale\|tw_" tests/`). Al final
  de cada tarea pasan: `tests/test_triple_whale*.py tests/test_rutas_triple_whale.py tests/test_migracion*.py` más
  las pruebas que la tarea nombre.

---

### Task 1: Esquema, migración 0032 y países

**Files:**
- Create: `migrations/versions/0032_triple_whale_varias_tiendas.py`
- Create: `triple_whale/paises.py`
- Modify: `db.py` (tabla `tw_tienda` nueva; `tienda_id` y restricciones en `tw_anuncio_dia`, `tw_tienda_dia`,
  `tw_producto_dia`; comentario de `triple_whale` diciendo qué columnas quedaron sin uso, spec §3.2)
- Test: `tests/test_tw_paises.py`, `tests/test_migracion_tw_tiendas.py`

**Interfaces:**
- Produces: `db.tw_tienda`; columna `tienda_id` en las tres copias; `triple_whale.paises.adivinar_pais(dominio) ->
  str | None`, `paises_opciones(locale) -> list[tuple[str, str]]`, `nombre_pais(codigo, locale) -> str`,
  `bandera(codigo) -> str`. `triple_whale/paises.py` no importa Flask (la migración lo usa).

- [ ] **Step 1: pruebas de países.** En `tests/test_tw_paises.py`:

```python
from triple_whale import paises

def test_adivina_por_nombre_local_e_ingles():
    assert paises.adivinar_pais("happyflops-norge.myshopify.com") == "NO"
    assert paises.adivinar_pais("https://HappyFlops-Sverige.myshopify.com/admin") == "SE"
    assert paises.adivinar_pais("happyflops-denmark.myshopify.com") == "DK"
    assert paises.adivinar_pais("tienda-espana.myshopify.com") == "ES"

def test_adivina_por_sufijo_iso():
    assert paises.adivinar_pais("shop-de.myshopify.com") == "DE"
    assert paises.adivinar_pais("happyflops_fi.myshopify.com") == "FI"

def test_sin_pista_no_inventa():
    assert paises.adivinar_pais("happyflops.myshopify.com") is None
    assert paises.adivinar_pais("") is None
    assert paises.adivinar_pais(None) is None

def test_opciones_en_el_idioma_de_quien_mira():
    es = dict(paises.paises_opciones("es"))
    en = dict(paises.paises_opciones("en"))
    assert "Noruega" in es["NO"] and "Norway" in en["NO"]
    assert all(len(c) == 2 and c.isalpha() for c in es)
    assert paises.bandera("NO") == "🇳🇴"
```

- [ ] **Step 2:** correr, ver que fallan por `ModuleNotFoundError`.
- [ ] **Step 3: implementar `triple_whale/paises.py`.** Nombres de Babel (`babel.Locale(loc).territories`) para
  `en, es, nb, sv, da, fi, de, fr, it, nl, pt, pl`, solo claves de dos letras alfabéticas, sin `EU`, `EZ`, `UN`,
  `ZZ`, `QO`. Normalizar con `unicodedata` (NFKD, sin marcas), minúsculas, solo `[a-z]`. Construir una vez (caché de
  módulo) `{nombre_normalizado: codigo}` descartando nombres de menos de 4 letras. `adivinar_pais`: quitar esquema,
  ruta y `.myshopify.com` (reusar la misma limpieza que `triple_whale.normalizar_dominio` sin importar ese módulo:
  copiarla en una función privada pequeña), partir por `-`, `_`, `.`; buscar cada trozo (y la unión de trozos
  contiguos, para «new-zealand») en el mapa; si nada, y el ÚLTIMO trozo tiene dos letras y es un territorio válido,
  ese código. `bandera`: dos «regional indicator» (`chr(0x1F1E6 + ord(c) - 65)`). `paises_opciones(locale)`:
  `[(codigo, f"{bandera(codigo)} {nombre}")]` ordenado por nombre con `locale.strxfrm`-independiente (ordenar por el
  nombre normalizado). `nombre_pais` devuelve el código si Babel no lo conoce.
- [ ] **Step 4:** pruebas de países en verde.
- [ ] **Step 5: prueba de la migración.** En `tests/test_migracion_tw_tiendas.py`, seguir el patrón de
  `tests/test_migracion_triple_whale.py` (alembic sobre una base temporal hasta `0031`, insertar datos crudos con
  SQL, subir a `0032`). Casos: (a) proyecto `acme` con fila en `triple_whale` (llave `"cifrada"`, dominio
  `happyflops-norge.myshopify.com`, extra con `backfill_desde`, `avisados`) y filas en las tres copias → una
  `tw_tienda` con `pais="NO"`, la llave tal cual, extra solo con `backfill_desde/ultimo_resumen/gasto_7d`, y todas
  las filas de copias con su `tienda_id`; la fila de `triple_whale` sigue con su llave y su `extra.avisados`. (b)
  filas de copias de un `cliente` sin conexión → borradas. (c) dos filas mismo `(cliente, canal, ad_id, fecha)` con
  distinto `tienda_id` caben después de subir. (d) `downgrade` a `0031` deja el esquema viejo y una sola tienda por
  proyecto en las copias. (e) base sin datos sube y baja sin error.
- [ ] **Step 6: escribir la migración** `0032` (`down_revision = '0031'`). `upgrade`: crear `tw_tienda` (columnas
  del spec §3.1, `UniqueConstraint('cliente','dominio', name='uq_tw_tienda_dominio')`, índice `ix_tw_tienda_cliente`
  y `op.create_index('uq_tw_tienda_pais', 'tw_tienda', ['cliente','pais'], unique=True,
  sqlite_where=sa.text('pais IS NOT NULL'))`); `add_column tienda_id` nullable en las tres copias; con
  `op.get_bind()` leer `triple_whale` con llave no nula, insertar cada tienda (pais con
  `triple_whale.paises.adivinar_pais`), `UPDATE … SET tienda_id=:id WHERE cliente=:c`; `DELETE … WHERE tienda_id IS
  NULL`; luego `batch_alter_table(..., recreate='always')` por tabla: `alter_column('tienda_id', nullable=False)`,
  soltar la restricción única vieja y crear la nueva (spec §3.3), índices nuevos. `downgrade`: por proyecto
  conservar la tienda de menor id, borrar filas de las demás, recrear restricciones viejas, soltar `tienda_id`, soltar
  `tw_tienda`. Reflejar el mismo esquema en `db.py`.
- [ ] **Step 7:** `venv/bin/python3 -m pytest -q tests/test_tw_paises.py tests/test_migracion_tw_tiendas.py
  tests/test_migracion_triple_whale.py tests/test_db*.py` en verde (si existe una prueba que compara `db.py` con las
  migraciones, también).
- [ ] **Step 8: commit** «Triple Whale: tabla de tiendas, tienda en las copias y países (migración 0032)».

### Task 2: Conexión por tiendas (`triple_whale_tiendas.py`)

**Files:**
- Modify: `triple_whale_tiendas.py`
- Test: `tests/test_tw_tiendas.py` (nuevo); ajustar `tests/test_triple_whale.py` si usa la API vieja.

**Interfaces:**
- Consumes: `db.tw_tienda`, `triple_whale.paises.adivinar_pais`.
- Produces (spec §4.1, firmas exactas):
  - `class PaisOcupado(ValueError)`
  - `ajustes(cliente) -> dict | None` (`id, moneda, modelo_atribucion, ventana_atribucion, extra, actualizado_en`)
  - `tiendas(cliente) -> list[dict]` sin llave (`id, cliente, pais, dominio, zona_horaria, estado, error,
    ultima_sincronizacion, extra, creado_en, actualizado_en`), orden `(pais is None, pais, id)`
  - `tienda(cliente, tienda_id) -> dict | None`, `tienda_de_pais(cliente, pais) -> dict | None`
  - `obtener(cliente) -> dict | None` = `{**ajustes, "tiendas": tiendas}` solo si hay ≥1 tienda
  - `obtener_llave(cliente, tienda_id) -> str | None`
  - `agregar(cliente, llave, dominio, pais=None, moneda="USD", modelo_atribucion=MODELO_DEFECTO,
    ventana_atribucion=VENTANA_DEFECTO, zona_horaria="") -> int`; `pais=None` → `adivinar_pais(dominio)`
  - `conectar(...)` = alias de `agregar` con la firma vieja (para no romper llamadas de prueba).
  - `cambiar_pais(cliente, tienda_id, pais) -> None` (lanza `PaisOcupado`; `pais` vacío → None)
  - `actualizar_tienda(cliente, tienda_id, **campos)`, `actualizar_extra_tienda(cliente, tienda_id, cambios)`
  - `actualizar_extra(cliente, cambios)` (proyecto), `cambiar_ajustes(cliente, moneda=None, modelo_atribucion=None,
    ventana_atribucion=None) -> bool`
  - `quitar(cliente, tienda_id) -> bool`, `desconectar(cliente)` (quita todas; la usa nadie más que pruebas)
  - `conectadas() -> list[tuple[str, int]]`, `firma(cliente) -> tuple[int, str | None]`
  - `url_tags(cliente)`, `kw_url_tags(cliente)` sin cambios de comportamiento.
  - Se ELIMINA `actualizar(cliente, **campos)` (escribía estado de la conexión): quien lo usaba pasa a
    `actualizar_tienda`.

- [ ] **Step 1: pruebas** (fixture `base_temporal` + `FLASK_SECRET_KEY` como en `tests/test_triple_whale_sync.py`):
  agregar dos tiendas (NO y SE) → `tiendas()` dos, ajustes creados con la moneda de la primera; segunda llamada con
  moneda `EUR` no cambia la moneda; reconectar mismo dominio con otra llave → mismo id, llave nueva, estado
  `conectada`; país ocupado → `PaisOcupado`; `cambiar_pais` no toca filas de `tw_anuncio_dia` (insertar una a mano
  con su `tienda_id`); `quitar` una → sus copias borradas y las de la otra intactas; `quitar` la última → `ajustes()`
  None y `obtener()` None; `tienda("otro", id)` None; `obtener_llave` devuelve la de cada tienda;
  `cambiar_ajustes` borra copias de todas y vacía `backfill_desde` de cada tienda; `conectadas()` lista ambas;
  `firma` cambia tras `actualizar_tienda`.
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar.** Cifrado con `cifrado.cifrar` igual que hoy. `_borrar_copias(con, cliente,
  tienda_id=None)` borra en las TRES copias (hoy olvida `tw_producto_dia`: arreglarlo). Toda escritura con
  `db.conectar()` (una transacción).
- [ ] **Step 4:** verdes + `tests/test_triple_whale*.py` (arreglar las que usen `actualizar` o lean
  `config["dominio_tienda"]`; las de sync/panel pueden seguir rojas hasta la tarea 4: anotarlo en el reporte, no
  dejarlas comentadas).
- [ ] **Step 5: commit** «Triple Whale: varias tiendas por proyecto en la conexión».

### Task 3: Copias y lecturas por tienda (`triple_whale/datos.py`)

**Files:**
- Modify: `triple_whale/datos.py`
- Test: `tests/test_tw_datos_tiendas.py` (nuevo); ajustar las pruebas que llamen a `datos.*` con la firma vieja.

**Interfaces:**
- Produces (spec §6.1): `reemplazar_anuncios_canal(cliente, tienda_id, desde, hasta, registros)`, ídem
  `reemplazar_anuncios_pixel`, `reemplazar_tienda`, `reemplazar_productos`; lecturas con `tienda_id` como SEGUNDO
  argumento (`None` = todas): `totales_por_anuncio(cliente, tienda_id, desde, hasta, canal=None)`,
  `totales_anuncio(cliente, tienda_id, canal, ad_id, desde, hasta=None)` (tienda obligatoria),
  `serie_anuncios(cliente, tienda_id, desde, hasta)`, `serie_tienda(cliente, tienda_id, desde, hasta)`,
  `top_productos(cliente, tienda_id, desde, hasta, limite=10)`, `hay_productos(cliente, tienda_id=None)`,
  `rango(cliente, tienda_id=None)`, `hay_tienda(cliente, tienda_id=None)`, `canales(cliente, tienda_id, desde,
  hasta)`, nuevas `gasto_duplicado(cliente, desde, hasta) -> float` y `por_tienda(cliente, desde, hasta, desde_prev,
  hasta_prev) -> list[dict]` (cada dict: `tienda_id`, `actual` y `previo` = salida de `serie_tienda` sumada:
  `ingresos, pedidos, gasto, nc_pedidos, nc_ingresos`). Evaluaciones sin cambios de firma.

- [ ] **Step 1: pruebas.** Con dos tiendas (ids de `triple_whale_tiendas.agregar`):
  - mismo `ad_id` y día en las dos con `gasto=10, pedidos=1` y `gasto=10, pedidos=2` → `totales_por_anuncio(c, None,
    …)` da `gasto == 10`, `pedidos == 3`; por tienda da 10/1 y 10/2.
  - `ad_id` distintos (cuentas separadas) → todo suma.
  - `serie_tienda(c, None, …)` con `gasto` 100 y 100 en el mismo día y un anuncio compartido de 30 → `gasto == 170`,
    `utilidad_neta` sumada `+ 30`; `gasto_duplicado == 30`.
  - productos «Chancla Azul» con `producto_id` distintos en cada tienda → `top_productos(c, None, …)` una fila con
    las unidades sumadas; por tienda, por `producto_id`.
  - `reemplazar_tienda(c, t1, …)` no borra filas de `t2`.
  - `por_tienda` devuelve una fila por tienda, incluida una sin datos (ceros).
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar.** Escrituras: `tienda_id` en `nuevo`, en el `WHERE` del cero/borrado del rango y en
  `index_elements` del upsert (`["cliente","tienda_id","canal","ad_id","fecha"]`). Lecturas «todas» con una
  subconsulta:

```python
def _anuncio_dia(cliente, tienda_id, desde, hasta, canal=None):
    """Una fila por (canal, ad_id, fecha). Con una tienda, sus filas. Con todas,
    medidas de canal con MAX (el mismo anuncio llega por cada tienda que comparte
    la cuenta) y del Pixel con SUMA (cada tienda atribuye sus propios pedidos)."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente, t.c.fecha >= desde, t.c.fecha <= hasta]
    if tienda_id is not None:
        cond.append(t.c.tienda_id == tienda_id)
    if canal:
        cond.append(t.c.canal == canal)
    medidas = ([sa.func.max(getattr(t.c, c)).label(c) for c in COLUMNAS_CANAL]
               + [sa.func.sum(getattr(t.c, c)).label(c) for c in COLUMNAS_PIXEL]
               + [sa.func.max(sa.cast(t.c.con_pixel, sa.Integer)).label("con_pixel")]
               + [sa.func.max(getattr(t.c, c)).label(c) for c in COLUMNAS_DIMENSION if c != "utm_ok"]
               + [sa.func.min(sa.cast(t.c.utm_ok, sa.Integer)).label("utm_ok")])
    return (sa.select(t.c.canal, t.c.ad_id, t.c.fecha, *medidas).where(*cond)
            .group_by(t.c.canal, t.c.ad_id, t.c.fecha).subquery())
```

  y `totales_por_anuncio`, `serie_anuncios`, `canales`, `rango` leen de esa subconsulta (con una tienda da lo mismo
  que hoy). `gasto_duplicado` por día: `SUM(gasto) - MAX(gasto)` agrupado por `(canal, ad_id, fecha)`, sumado por
  fecha; `serie_tienda(c, None, …)` suma por fecha y resta ese duplicado del día al `gasto` y lo suma a
  `utilidad_neta`. `top_productos(c, None, …)`: agrupar por `lower(trim(nombre))` (o `producto_id` si el nombre es
  nulo), `producto_id` = el MIN del grupo, `nombre` = MAX.
- [ ] **Step 4:** verdes.
- [ ] **Step 5: commit** «Triple Whale: copias y lecturas por tienda, «Todas» sin gasto duplicado».

### Task 4: Sincronización, tareas y avisos

**Files:**
- Modify: `triple_whale/sync.py`, `tareas/triple_whale.py`, `triple_whale/avisos.py`
- Test: `tests/test_triple_whale_sync.py`, `tests/test_triple_whale_avisos.py` (ajustar), casos nuevos ahí mismo.

**Interfaces:**
- Consumes: tareas 2 y 3.
- Produces: `sync.sincronizar(cliente, tienda_id, desde=None, hasta=None, on_progreso=None, hoy=None)`,
  `sync.sincronizar_si_hace_falta(cliente, tienda_id, minutos=MINUTOS_FRESCO)`, `sync.rango_pendiente(tienda, hoy)`
  y `sync.esta_fresca(tienda, …)` sobre el dict de la TIENDA. `tareas_tw.job_id_sync(cliente, tienda_id)`,
  `encolar_sync(cliente, tienda_id=None) -> int`, `syncs_en_curso(cliente) -> list[str]`,
  `job_id_evaluar(cliente)` y `encolar_evaluacion` sin cambios. `avisos.revisar_y_avisar(cliente, ev=None,
  config=None, dias=DIAS)` evalúa «todas» (`panel.evaluar_periodo(cliente, dias, tienda_id=None)`).

- [ ] **Step 1: pruebas** (reusar `TripleWhaleFalso`; distinguir tiendas por `shop`): dos tiendas → cada una copia
  con su `tienda_id` y su llave (mirar `llamadas`); `ErrorTienda` en una → esa queda `error`, la otra `conectada`, y
  el mensaje guardado no contiene la llave; `tw_sincronizar_todas` encola dos; `encolar_sync(c)` encola dos y
  devuelve 2, una segunda vez 0; avisos: con la otra tienda aún en cola `revisar_y_avisar` NO se llama (monkeypatch
  contador), cuando termina la última sí, una vez.
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar** según spec §5 y §7. En `tw_sincronizar`: payload `{"cliente", "tienda_id"}`; si la
  tienda ya no existe, devolver «Esa tienda de Triple Whale ya no está conectada.»; texto final con el país
  (`paises.nombre_pais(pais, idiomas.de_proyecto(cliente))` o el dominio). `_sin_llave(cliente, tienda_id, texto)`.
  Avisos: `otras = [j for j in syncs_en_curso(cliente) if j != job_id]`; si `otras`, no avisar. Mantener
  `max_intentos=2` para sync y `1` para evaluar.
- [ ] **Step 4:** verdes, incluidas todas las de `tests/test_triple_whale_sync.py` y `_avisos.py` adaptadas.
- [ ] **Step 5: commit** «Triple Whale: una copia por tienda y avisos cuando termina la última».

### Task 5: Panel, pestaña y evaluación con IA

**Files:**
- Modify: `triple_whale/panel.py`, `triple_whale/rutas.py`, `tareas/triple_whale.py` (solo `tw_evaluar`:
  `top_productos` con `extra.tienda_id`), `templates/_tw_panel.html`, `templates/_tab_triple_whale.html` (solo el JS
  si hace falta), `static/style.css` vía la fuente de estilos que corresponda (leer la skill `ui`: `static/estilos/`
  genera `style.css`)
- Test: `tests/test_rutas_triple_whale.py` (ajustar + casos nuevos)

**Interfaces:**
- Consumes: tareas 2–4.
- Produces: `panel.contexto(cliente, dias=…, canal=None, tienda_id=None, hoy=None)` con claves nuevas `tiendas`,
  `tienda_actual` (dict o None = todas), `por_tienda` (lista de dicts con `tienda`, `actual`, `previo`, `mer`,
  `variacion_ingresos`), `gasto_duplicado`, `jobs_sync`; `panel.evaluar_periodo(cliente, dias, canal=None,
  tienda_id=None, hoy=None)`; `panel.resumen_mes_tienda(cliente, hoy=None)` (todas). Las rutas `ver_panel` y
  `evaluar` leen `tienda` (entero; ajeno o inválido → todas); `sincronizar` lee `tienda_id` opcional.

- [ ] **Step 1: pruebas de rutas:** con dos tiendas y copias sembradas → el HTML del panel tiene el selector con
  «Todas las tiendas (2)» y las dos banderas, el bloque «Por tienda» y, con un anuncio compartido, la nota de cuenta
  compartida; con `?tienda=<id>` no aparece «Por tienda»; `?tienda=<id de otro proyecto>` = todas; con una sola
  tienda no hay selector; `POST evaluar` con `tienda=<id>` guarda `extra.tienda_id` y `extra.pais`;
  `POST sincronizar` sin id encola dos. Panel hace un número constante de consultas al crecer el número de anuncios
  (si ya hay una prueba de conteo de consultas, extenderla).
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar** según spec §6.2 y §8. Selector como los de periodo y canal
  (`<select data-tw-param="tienda">`). Lista de evaluaciones con el alcance. Barras: una `data-poll-job` por job en
  `jobs_sync` con id único por tienda. Nada de `<script>` en `_tw_panel.html`.
- [ ] **Step 4:** verdes. Comprobar la plantilla con el hook (`div` en pareja).
- [ ] **Step 5: commit** «Triple Whale: selector de tienda, «Por tienda» y evaluación por alcance».

### Task 6: Conectar, probar, cambiar país y quitar (dashboard)

**Files:**
- Modify: `dashboard.py` (rutas `cfg_triple_whale_*` §10, contexto de `ver_cliente` con `tw_tiendas`,
  `tw_paises` = `paises_opciones(idioma de quien mira)`, clave de caché del Tablero con
  `triple_whale_tiendas.firma`), `templates/_triple_whale_conectar.html`, `templates/_tab_triple_whale.html`
- Test: `tests/test_rutas_triple_whale.py` o `tests/test_rutas_configuracion.py` (donde ya estén las de conectar)

**Interfaces:**
- Consumes: tareas 1–5.
- Produces: rutas `cfg_triple_whale_pais` (POST) y `cfg_triple_whale_adivinar_pais` (GET, JSON), y las existentes con
  `tienda_id`.

- [ ] **Step 1: pruebas:** conectar segunda tienda (monkeypatch de `triple_whale.validar_llave` y
  `triple_whale.probar`) → dos tiendas y una copia encolada para la nueva; país ocupado → flash en palabras y nada
  guardado; sin país y dominio sin pista → flash «Elige el país de la tienda» y nada guardado; `probar` con
  `tienda_id` ajeno → 404; `pais` cambia el país; `desconectar` con `tienda_id` quita solo esa; `adivinar_pais`
  devuelve `{"pais": "NO"}`; POST con `Sec-Fetch-Site: cross-site` → 403; la página del proyecto pinta las dos
  tarjetas, el formulario «Agregar otra tienda» cerrado y los ajustes aparte; una tienda sin país muestra «Elige el
  país de esta tienda». Clave de caché del Tablero cambia al agregar una tienda.
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar** según spec §6.2 (conexión) y §10. JS del formulario en `_tab_triple_whale.html` (el
  fragmento conectar se incluye en la página, no llega por fetch, así que su `<script>` corre; preferir un solo
  bloque al final de `_tab_triple_whale.html`): al `change`/`blur` del dominio, si el país está en «Detectar por el
  dominio», `fetch` a `adivinar_pais` y seleccionar. El primer `<option>` del selector de país es
  «Detectar por el dominio» (valor vacío).
- [ ] **Step 4:** verdes.
- [ ] **Step 5: commit** «Triple Whale: conectar varias tiendas, cambiar país y quitar una».

### Task 7: Experimentos con la tienda de su país

**Files:**
- Modify: `lanzador.py` (`_sincronizar_triple_whale`, `_mezclar_ventas_triple_whale`, `refrescar`)
- Test: `tests/test_lanzador.py` y las de revisión que toquen Triple Whale (`grep -ln triple_whale tests/`)

**Interfaces:**
- Consumes: `triple_whale_tiendas.tiendas`, `tienda_de_pais`, `ajustes`; `datos.totales_anuncio(cliente,
  tienda_id, …)`; `sync.sincronizar_si_hace_falta(cliente, tienda_id)`.
- Produces: `lanzador._tienda_tw_de(tiendas, pais) -> dict | None` (la del país, o la única si hay una).

- [ ] **Step 1: pruebas:** experimento `triple_whale` con piezas NO y SE, tiendas NO y SE con ventas distintas para
  el mismo `ad_id` → cada pieza toma las de su tienda; con solo tienda NO y dos tiendas (NO + DK) una pieza SE
  queda con Meta y hay UN evento «No hay tienda de Triple Whale para…» aunque se refresque dos veces; con una sola
  tienda (sin país) la usa para todas; cada tienda usada se sincroniza una vez por refresco.
- [ ] **Step 2:** verlas fallar.
- [ ] **Step 3: implementar** según spec §9. Marca anti-repetición en `experimentos.actualizar_extra(cliente,
  ex_id, …)` con clave `aviso_sin_tienda_tw` = lista de países ya avisados.
- [ ] **Step 4:** verdes, más `tests/test_tablero*.py tests/test_rutas_tablero.py`.
- [ ] **Step 5: commit** «Experimentos: las ventas de Triple Whale salen de la tienda del país de cada pieza».

### Task 8: Textos, documentación y suite completa

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po` (vía `catalogo_i18n.py`), `.claude/skills/triple-whale/SKILL.md`,
  `docs/pendientes.md`
- Test: suite completa

- [ ] **Step 1:** `venv/bin/python3 catalogo_i18n.py actualizar`, traducir cada msgid nuevo al inglés siguiendo
  `docs/i18n/glosario.md` (sin `fuzzy`), `venv/bin/python3 catalogo_i18n.py compilar`.
- [ ] **Step 2:** reescribir en la skill `triple-whale` lo que cambió (tablas, funciones con firma nueva, «Todas»
  con MAX/SUMA y gasto duplicado, avisos sobre todas, atribución por país, rutas nuevas) con la fecha 2026-10-08 y el
  motivo (happyflops con una tienda por país).
- [ ] **Step 3:** en `docs/pendientes.md` agregar `PND-146` (países europeos en `final_edition.tipos.PAISES` para
  experimentos y finales; severidad `bloqueo de uso`; afecta `clientes en producción`; desde 2026-10-08; origen este
  spec §13) y `PND-147` (varias cuentas publicitarias de Meta por proyecto en la conexión de Meta; `higiene`;
  `no determinado`; 2026-10-08; spec §13). Comprobar antes que 146 y 147 están libres.
- [ ] **Step 4:** `venv/bin/python3 -m pytest -q` completo (incluye `slow`). Todo verde; si algo falla fuera del área,
  mirar si ya fallaba en `origin/main` antes de tocarlo y decirlo en el reporte.
- [ ] **Step 5: commit** «Triple Whale varias tiendas: textos en inglés, skill y pendientes».
