# Motor — Bloque 6: tablero, ventas atribuidas y OUTCOME_SALES — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar la versión del motor con la vista que el dueño abre cada mañana — **Tablero**: gasto del mes, ventas atribuidas (Meta o tienda), ROAS, top 5 ganadoras, alertas y una serie de 30 días — y con campañas que optimizan por compra cuando hay Pixel (`OUTCOME_SALES` con `promoted_object`), que es lo que hace que "ventas decide" sea real y no solo tráfico.

**Architecture:** `tablero.py` (agregaciones puras sobre `metrica_snapshot`, `experimento(_pieza)`, `propuesta`, `tienda`, `pedido` — deltas por día a partir de snapshots acumulados) + `meta_ads/adset.py` con `promoted_object` + `lanzador` que elige `OUTCOME_SALES` + pixel cuando el experimento tiene atribución `pixel` + pestaña **Tablero** (`_tab_tablero.html`, primera del sidebar) con tiles, top 5, alertas, gráfico SVG inline y exportación CSV.

**Tech Stack:** Flask/Jinja, SQLAlchemy Core (SQLite), `meta_ads` (Graph v25.0), SVG inline (sin librerías).

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §7 (Tablero), §4 (objetivo según capacidades: con Pixel → `OUTCOME_SALES` optimizando `purchase`; atribución 1–3), §9 punto 6.

## Global Constraints

- Las métricas de Meta en `metrica_snapshot` son **acumuladas** por anuncio (`date_preset=maximum`); las de tienda también (`ventas_por_pieza` desde activación). Todo cálculo por período usa **deltas entre snapshots**: valor en un instante = último snapshot con `tomado_en ≤ instante`; período `[a, b)` = valor(b) − valor(a), nunca sumas de snapshots. Un delta negativo (Meta corrige hacia abajo) se trunca a 0.
- Moneda: todo en la moneda de la cuenta de Meta del proyecto (`experimento.moneda`); si hay experimentos en monedas distintas, el tablero agrupa por moneda y lo dice. Ingresos de tienda en otra moneda no se suman al ROAS (mismo criterio del bloque 5).
- `OUTCOME_SALES` solo se lanza si `meta_conexion.estado_pixel(cliente, solo_cache=True)` es `ok` en el momento de lanzar (el lanzador re-chequea; si no, aborta con error claro en vez de crear una campaña que Meta rechazará). `promoted_object = {"pixel_id": <id>, "custom_event_type": "PURCHASE"}` en cada conjunto.
- Cambiar el objetivo de un experimento ya lanzado no se permite (Meta no lo permite): el objetivo se fija al crear; la UI sugiere `OUTCOME_SALES` cuando la atribución sugerida es `pixel` y `OUTCOME_TRAFFIC` en los demás casos.
- Tablero de solo lectura: ninguna acción que gaste sale de aquí; las alertas enlazan a la pestaña donde se resuelve.
- Copy en español; suite verde sin red; bloques 1–5 sin cambios de comportamiento (cambios aditivos).

---

## Estructura de archivos

- Create: `tablero.py`, `templates/_tab_tablero.html`, `tests/test_tablero.py`, `tests/test_outcome_sales.py`, `tests/test_rutas_tablero.py`.
- Modify (submódulo): `meta_ads/adset.py` (`promoted_object`).
- Modify: `lanzador.py`, `experimentos.py` (`objetivo_sugerido`), `dashboard.py` (contexto + `tab_descargar_csv`, `exp_crear` default), `templates/_sidebar.html`, `templates/cliente.html`, `templates/_tab_experimentos.html` (objetivo sugerido), `static/style.css`, `CLAUDE.md`, `SETUP.md`.

---

### Task 1: `tablero.py` — agregaciones por deltas

**Files:**
- Create: `tablero.py`
- Test: `tests/test_tablero.py`

**Interfaces (Produces):**
- `tablero.valor_en(snaps, instante_iso, campo) -> float`: último snapshot con `tomado_en <= instante`, 0 si no hay. `tablero.delta(snaps, desde_iso, hasta_iso, campo) -> float` = `max(0, valor_en(hasta) - valor_en(desde))`.
- `tablero.resumen_periodo(cliente, desde_iso, hasta_iso) -> {"por_moneda": {"COP": {"gasto", "compras", "ingresos", "roas", "clics_enlace", "impresiones", "anuncios"}}, "experimentos_corriendo": n, "propuestas_pendientes": n, "piezas_activas": n}` — recorre `experimento` no legado del cliente con sus piezas y `experimentos.snapshots(ep_id)`; `ingresos` solo de snapshots con `fuente_ventas in ("meta", "tienda")`; `roas = ingresos/gasto` (0 si gasto 0).
- `tablero.resumen_mes(cliente, ahora_iso=None)` = `resumen_periodo` del primer día del mes a `ahora`; incluye `"desde"`, `"hasta"`.
- `tablero.serie_diaria(cliente, dias=30, ahora_iso=None) -> [{"dia": "YYYY-MM-DD", "gasto": f, "compras": i, "ingresos": f}]` (deltas por día, en la moneda mayoritaria; si hay varias, la de más gasto y campo `"moneda"` en el dict raíz — devolver `{"moneda": "COP", "dias": [...]}`).
- `tablero.top_ganadoras(cliente, n=5) -> [dict]`: piezas con `veredicto == "ganador"` de experimentos no cerrados… (también cerrados: es histórico) ordenadas por `roas` desc (si > 0) y luego `cpc` asc (usando la última métrica); cada una: `ep_id, experimento_id, experimento_nombre, pais, nombre, url_miniatura, url_video, metricas (última), veredicto_motivo, veredicto_en, escalon_rescate`.
- `tablero.alertas(cliente) -> [{"tipo", "nivel": "alta"|"media"|"baja", "texto", "tab": "experimentos"|"productos"|"settings"|"ads", "experimento_id": int|None}]`, en este orden: Meta `roto`/`sin_conectar` (alta, settings); experimentos en `error` (alta); propuestas pendientes (media, con cuenta por experimento); anuncios `estado_meta` DISAPPROVED/WITH_ISSUES (alta); tope alcanzado (`gasto_acumulado >= tope_total` y estado corriendo/pausado) (media); tiendas `rota` (media, settings); pixel `sin_datos`/`sin_pixel` si hay experimentos con atribución pixel (media, settings); productos `en_prueba` sin experimento (baja, productos); experimentos `corriendo` sin snapshot en 6 h (baja). Cada alerta con `texto` en español con números.
- `tablero.csv_mes(cliente, ahora_iso=None) -> str` (CSV con `;`: experimento, país, pieza, veredicto, impresiones, clics, gasto, compras, ingresos, roas, moneda — deltas del mes por pieza).

- [ ] **Step 1: Tests** (base_temporal; crear experimentos/piezas con `experimentos.*`, snapshots con `experimentos.snapshot(ep_id, {...})` controlando `tomado_en` — añadir parámetro opcional `tomado_en=None` a `experimentos.snapshot` para tests/backfill): `valor_en`/`delta` con 3 snapshots y truncado a 0; `resumen_mes` con dos piezas (una con ventas meta, otra tienda) y un snapshot anterior al mes (delta excluye lo previo); dos monedas → dos grupos; `serie_diaria` 3 días; `top_ganadoras` ordena por roas luego cpc y trae miniatura/nombre; `alertas` cubre cada tipo con fakes de `meta_conexion.estado/estado_pixel` y `tiendas.listar`; `csv_mes` cabecera y una fila.

- [ ] **Step 2: Implementar. Step 3: Tests. Step 4: Commit** `"Tablero: agregaciones por deltas (mes, serie diaria, top ganadoras, alertas, CSV)"`.

---

### Task 2: `OUTCOME_SALES` con Pixel

**Files:**
- Modify (submódulo): `meta_ads/adset.py`
- Modify: `lanzador.py`, `experimentos.py`, `dashboard.py` (`exp_crear`), `templates/_tab_experimentos.html`
- Test: `tests/test_outcome_sales.py`

**Interfaces:**
- `meta_adset.crear_adset(nombre, campaign_id, objetivo_campaign, targeting_dict, presupuesto_diario_centavos, dias, dry_run=False, promoted_object=None)` → si viene, `payload["promoted_object"] = json.dumps(promoted_object)`. Para `OUTCOME_SALES` sin `promoted_object` → `ValueError` en español (Meta lo exige).
- `experimentos.objetivo_sugerido(cliente) -> "OUTCOME_SALES"|"OUTCOME_TRAFFIC"` (`SALES` si `atribucion_sugerida == "pixel"`).
- `lanzador.lanzar`: si `ex["objetivo_meta"] == "OUTCOME_SALES"`: `px = meta_conexion.estado_pixel(cliente, solo_cache=True)`; si `px` es None → calcular (`estado_pixel(cliente)`); si `estado != "ok"` → `ValueError("Este experimento optimiza por compras y el Pixel no está activo…")` antes de crear nada; `promoted_object = {"pixel_id": px["pixel_id"], "custom_event_type": "PURCHASE"}` a cada `crear_adset`. Evento con el pixel usado.
- `exp_crear`: objetivo por defecto en el form = `objetivo_sugerido`; si el form manda `OUTCOME_SALES` y `atribucion` no es `pixel` → flash y no crea. `_tab_experimentos.html`: selector con la sugerencia marcada + ayuda ("Compras: requiere Pixel activo; Tráfico: clics al enlace").

- [ ] **Step 1: Tests**: `crear_adset` con y sin `promoted_object` (auth fake); `lanzar` con SALES + pixel ok → cada adset lleva `promoted_object` (fixture `entorno` de `tests/test_lanzador.py`, monkeypatch `lanzador.meta_conexion.estado_pixel`); SALES sin pixel → ValueError, no llamadas a Meta, experimento `error`; TRAFFIC sin promoted_object; `objetivo_sugerido`; ruta `exp_crear` rechaza SALES sin pixel.

- [ ] **Step 2: Implementar (commit en submódulo + puntero). Step 3: Tests. Step 4: Commit** `"OUTCOME_SALES con Pixel: promoted_object por conjunto, objetivo sugerido, validación al crear y lanzar"`.

---

### Task 3: Pestaña Tablero

**Files:**
- Create: `templates/_tab_tablero.html`
- Modify: `dashboard.py` (contexto `tablero=...` en `ver_cliente` — calculado solo para esta pestaña: usar un helper `_contexto_tablero(cliente)` que envuelve cada parte en try/except y devuelve `None` para la que falle, con el error en `tablero["errores"]`; ruta `tab_descargar_csv` GET `/cliente/<c>/tablero/mes.csv` → `text/csv` con `Content-Disposition`), `templates/_sidebar.html` (tab `tablero` primero, ícono de gráfico), `templates/cliente.html`, `static/style.css`
- Test: `tests/test_rutas_tablero.py`

**UI:** cabecera "Tablero · <mes en español>"; fila de tiles (`.kpi-tile`): Gasto del mes, Compras, Ingresos, ROAS (con "sin ventas medibles" si 0 y no hay atribución), Experimentos corriendo, Propuestas pendientes (enlace a Experimentos); por moneda si hay varias. Gráfico de 30 días: SVG inline con barras de gasto y línea de ingresos (escala automática, ejes con 4 marcas, `<title>` por barra); "Top 5 ganadoras": tarjetas con miniatura (o placeholder), país con bandera (`paises_fe`), CTR/CPC/ROAS, motivo, botón "Ver experimento" (`#experimentos` + abre el `<details>` por id vía `?exp=<id>` que la pestaña Experimentos ya puede leer — añadir 3 líneas de JS allí si no existe). "Alertas": lista con color por nivel y enlace a la pestaña. Botón "Descargar CSV del mes". Estado vacío amable cuando no hay experimentos ("Crea tu primer experimento…").

- [ ] **Step 1: Tests**: render con datos (tiles con números, top con nombre, alertas con texto), render vacío, CSV route (content-type, cabecera, cross-tenant 302), `_contexto_tablero` tolera una parte que explota (monkeypatch `tablero.alertas` → raise) y sigue mostrando el resto.

- [ ] **Step 2: Implementar. Step 3: Tests + suite; verificación manual local con datos simulados (snapshots sembrados). Step 4: Commit** `"Tablero: gasto, ventas atribuidas, ROAS, serie de 30 días, top 5 ganadoras, alertas y CSV"`.

---

### Task 4: Docs y despliegue

- [ ] `CLAUDE.md` párrafo "Tablero y OUTCOME_SALES"; `SETUP.md`: qué muestra el tablero, que las cifras son deltas de snapshots (cambian con cada refresco), y cómo se activa optimizar por compras (Pixel ok → objetivo Compras al crear).
- [ ] Deploy (controlador): sin migraciones (verificar `alembic heads`), push del submódulo, reiniciar ambos servicios, abrir el Tablero en prod.
- [ ] Commit `"Docs: tablero y OUTCOME_SALES"`.

---

## Autorevisión

**Spec §7 Tablero:** gasto del mes, ventas atribuidas, ROAS, top 5 ganadoras, alertas (T1, T3). **§4:** con Pixel → `OUTCOME_SALES` optimizando `purchase` (T2); atribución 1 (Meta) y 2 (tienda) ya sumadas en snapshots (bloque 5) y agregadas aquí (T1). **§9.6** completo. Fuera (spec "fuera de esta versión" + ledgers): créditos/saldo del cliente, WhatsApp, avatares, publicación orgánica, agencia multi-cliente, `OUTCOME_APP_PROMOTION`.

**Nombres:** `tablero.resumen_mes/serie_diaria/top_ganadoras/alertas/csv_mes` (T1) ↔ T3; `experimentos.snapshot(tomado_en=)` (T1) ↔ tests T3; `meta_adset.crear_adset(promoted_object=)`, `experimentos.objetivo_sugerido`, `lanzador` pixel check (T2) ↔ T3 UI.

**Riesgos:** los deltas dependen de la frecuencia de refresco (2 h): el "mes" empieza en el primer snapshot del mes, no a medianoche exacta — se documenta. `OUTCOME_SALES` real no se puede probar mientras Meta tenga la app restringida.
