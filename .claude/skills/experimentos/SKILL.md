---
name: experimentos
description: "Experimentos en Meta y el tablero: armar y lanzar pruebas (campaña → conjunto por país → anuncio por pieza), métricas, el decisor (ganador/perdedor), modos manual/semi/auto, escalar, derivar, rescatar, y el Tablero (totales, mes a mes, OUTCOME_SALES). Cargar antes de tocar experimentos.py, lanzador.py, decisor.py, modos.py, acciones.py, derivaciones.py, propuestas.py, tablero.py, meta_detalle.py o _tab_experimentos.html."
---

# Experimentos, decisor y tablero

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Experimentos** (`experimentos.py` + `lanzador.py`): the ecommerce test loop's unit
of work. An experiment (table `experimento`, `legado=False` — `ads.py`'s "Anuncios
sueltos" is the one `legado=True` row per client and is untouched) names countries with
a daily budget each, a total cap, days, objective and destination URL; pieces (finals
for their own country, or text-free clones for any country) are attached as
`experimento_pieza` rows. `lanzador.lanzar` maps it onto Meta as 1 campaign
(`spend_cap` = tope total, only when it clears Meta's minimum) -> 1 adset per country
(`Targeting().edad().paises([pais])`, budget in the ad ACCOUNT's currency, never the
country's) -> 1 ad per piece, all `PAUSED`, saving every id as soon as Meta returns it so
a retry resumes instead of duplicating. Launching and activating are two different
clicks (`exp_lanzar` queues the `exp_lanzar` task with `max_intentos=1`; `exp_estado`
activates/pauses the whole experiment or one country inline). Metrics: `lanzador.refrescar`
appends a `metrica_snapshot` per ad (thruplay, purchases, ROAS when Meta reports them) —
the worker periodic `exp_refrescar_todos` (every 2 h, `worker.PERIODICAS`) does it for
every `corriendo` experiment. Every verdict/action writes an `evento`. Experiment
states: `armando -> lanzando -> pausado <-> corriendo -> cerrado`, `error` on a failed
launch (resumable). Meta's raw errors («Meta Ads (<edge>) respondió 400: {JSON cut at 500 chars}») are stored as-is but shown through `meta_errores.explicar` (filter `error_meta`, also used by `tablero.alertas` and `lanzador.traducir_error_meta`): known codes become what to do (1885183 app in Development mode — also recognized in the already-explained text, so it re-renders in the viewer's language —, 190 reconnect, 10/200/294 permissions, 4/17/32/613 and the 80000…80014 business-use-case family (`meta_errores._LIMITE`, `es_limite`) rate limit, 368 policy block, 1/2 temporary), otherwise Meta's own `error_user_title/msg`, otherwise the code; the experiment card keeps the raw text in a folded «Detalle técnico». UI (since 2026-09-20, "la galería primero"): the Experimentos tab opens with a gallery of
every piece with a public URL (`experimentos.elegibles`: Crear videos AND images, sprint
pieces, finals; `origen`, `formato`, `en_experimentos`), the user ticks pieces and a 3-step
form appears (where: countries + daily budget; how much: cap + days with a live count;
review: piece × country grid, auto name «Prueba 20 sep · 3 piezas · CO, MX», "Avanzado"
with objective/attribution/mode/URL). One `POST exp_probar` runs
`experimentos.crear_con_piezas` (experiment + `experimento_pieza` rows in ONE transaction,
`validar_combinacion`: a final only in its country, clones/images only in the experiment's
countries) and enqueues `exp_lanzar` — activating is still a separate click. The old
"+ Nuevo experimento" form is gone: `exp_crear` has no UI any more and is kept for
tests/scripts; `exp_agregar_pieza`/`exp_meter_pieza` remain for an `armando` experiment's
card. Crear (and the legacy "Anuncios sueltos" queue) link to `#experimentos?piezas=<pieza_id>`
(the gallery opens with that piece ticked); Catálogo does NOT — "Crear experimento" on a
product redirects with `?exp_nombre=&exp_destino=`, which step 3 prefills. Images are real
Meta ads (`crear_creative_imagen`, no video upload); the decisor skips ThruPlay for them
(`contexto["es_imagen"]`), never asks `derivar`/`rescatar` on one (a winner only scales, a
loser is only paused — `derivaciones` refuses image sessions), and they never enter the
organic publish path (`organico`/`publicador` are video-only; for an image piece `url_video`
IS the image URL, so every gate also checks `es_imagen`). `experimentos.ESTADOS_VIVOS`
(the gallery's «en prueba» label) includes `decidido`: winners keep delivering there.

**Decisor, escalera y modos** (`decisor.py`, `modos.py`, `propuestas.py`, `acciones.py`,
`derivaciones.py`, `notificaciones.py`): the part of the loop that closes on its own.
`decisor.decidir(snapshots, reglas, contexto)` is a pure function — traffic gate first
(impressions/spend/hours evidence, then CPC/CTR/ThruPlay thresholds; zero impressions is
never a loser; ThruPlay is skipped when `contexto["es_imagen"]`), sales gate second only with attribution (ROAS/CPA after
`ventana_ventas_horas`), top-third ranking per country when ≥ 3 ads — returning
`ganador | perdedor | inconcluso | pendiente` plus an action. Rules layer
`REGLAS_DEFECTO ← proyecto.json["reglas_experimentos"] ← experimento.reglas`. The worker
periodic `exp_decidir_todos` (1 h) runs `exp_decidir` per `corriendo` experiment: verdicts
are persisted once per piece, and every action goes through `acciones.pedir`, which
consults `modos.resolver(modo, accion)` — manual proposes everything, semi executes
`pausar`/`archivar` and proposes `escalar`/`derivar`/`rescatar`/`activar`, auto executes
all — and downgrades to a `propuesta` whenever the experiment's tope is reached or the
derivation depth hits 2. Winners: `escalar_pais` (+`escalar_pct_dia` up to
`escalar_tope_dia`) and `derivar` (a child experiment with `n_reediciones` guion variants
via `final_edition.producir(opciones.variante/variante_tipo)` and `n_regeneraciones` new
clones via `creative_flow.duplicar`). Losers: `rescatar` climbs `escalon_rescate` 1 → 2 → 3
(hook re-edit, structure re-edit, regeneration; each pauses the previous piece) and
`archivar` marks the concepto at step 3. `derivaciones.py` is the async state machine
(`experimento.extra["derivaciones"]`, advanced by the periodic `exp_avanzar_todos` every
10 min) that produces the pieces, attaches them, creates their ads with
`lanzador.lanzar_piezas_nuevas` and asks `activar` per the mode. Every RMW on
`experimento.extra`/`paises`/`experimento_pieza.extra` goes through `experimentos.actualizar_extra`,
`actualizar_pais`, `marcar_pieza`, which take SQLite's write lock BEFORE reading
(`_bloquear`) — pysqlite otherwise runs the SELECT in autocommit and two processes lose
updates. Notifications (`notificaciones.avisar`: propuesta, ganador, rechazo_meta,
error_lanzamiento) go by SMTP when `SMTP_HOST` is set and the project has a
`correo_notificaciones`; otherwise they are only eventos.

There is also NO Campañas tab any more: `_tab_ads.html` is gone, `nueva_campana`/`publicar_ad`
are no-ops that flash and redirect, and the legacy "Anuncios sueltos" (Forja's ads) render
read-only inside Experimentos (`_anuncios_sueltos.html`: KPIs, pausar/activar, actualizar).
The decisor's default rules (`cfg_reglas`) are edited in Experimentos ("Reglas del motor"),
not in Configuración.

**Tablero y OUTCOME_SALES** (`tablero.py`): the first tab. Every figure is a **delta of
cumulative snapshots** (`metrica_snapshot` stores Meta's lifetime totals per ad, so a period
is `valor_en(hasta) − valor_en(desde)`, negatives truncated to 0) grouped by account
currency; revenue only counts snapshots attributed by Meta Pixel, store, or Triple Whale
(`tablero.FUENTES_VENTAS`). `tablero.contexto`
loads each piece's snapshots once (bounded by `experimentos.snapshots(ep_id, desde=)`, which
also returns the last row before the window) and derives the tiles, the 30-day
series, the top-5 winners and the alerts. Since 2026-10-01 (pedido de Daniel) the tiles are the
**total since the start** (`resumen_total`: a piece's total is its latest snapshot, already in the
loaded window, so nothing is re-read; `resumen_total_triple_whale`; generation from
`gastos.resumen_total`) and below them the **«Mes a mes»** table (`mes_a_mes`: one row per month,
newest first, from the first month with ad spend or generation, a row per currency, generation only
on the first; the month-end snapshots come from ONE query, `_cierres_de_mes`, ROW_NUMBER per piece
and month, where a snapshot taken exactly at 00:00 of day 1 closes the previous month so the current
month's row equals `resumen_mes` and the months add up to the total; generation per month from
`gastos.por_mes`). `resumen_mes` (the month in progress) now only feeds the sidebar chip; the
«Tu tienda según Triple Whale» block and the CSV are still the current month.
`dashboard._contexto_tablero` caches it 60 s per client keyed by the latest snapshot id, the
proposal count and the project's generation charges (count, last id, sum), and degrades part by
part (never leaking exception text). The chart is inline SVG on a single axis (spend bars,
revenue line, validated colorblind-safe pair). `csv_mes` escapes formula-leading cells.
When the suggested attribution is `pixel`, `experimentos.objetivo_sugerido` is
`OUTCOME_SALES`; `lanzador.lanzar` then re-checks the Pixel before touching Meta and sends
`promoted_object={pixel_id, PURCHASE}` on every adset (`meta_ads/adset.py` refuses SALES
without it). The objective is fixed at creation — Meta doesn't allow changing it.

**Detalle de Meta** (`meta_detalle.py`, spec `2026-10-02-experimentos-centro-de-resultados` §3, E1 2026-10-02): único escritor de
`metrica_dia` (una fila por anuncio y día: tráfico, embudo `visitas_pagina`/`carrito`/`pago_iniciado`/`compras_meta`,
retención `vistas_3s`/`p25…p100`/`thruplay`/`tiempo_medio_s`) y `metrica_desglose` (desde la creación del experimento por
`ubicacion`/`edad_genero`/`dispositivo`/`region`), y de `experimento_pieza.extra["rankings_meta"]`. Pide a nivel
campaña con `level=ad` (1 diario + 4 desgloses + 1 rankings por experimento) con `meta_ads.auth.llamar`, sin tocar
el submódulo; los desgloses y los rankings van con `time_range` (creación → hoy, nunca `date_preset=maximum`) y los
desgloses piden solo lo que `fila_desglose` guarda (`CAMPOS_DESGLOSE`: sin `reach`/`frequency`/`cpm`/`clicks`).
Corre al final de `exp_refrescar` en su propio `try` (el decisor no depende de esto; su log lleva el error sin token) y como
tarea `exp_detalle` (`max_intentos=2`, no cobra; `meta_detalle.encolar_todos()` hace la carga inicial). El rango del
día a día se cura solo: desde el último día guardado menos 2 (Meta corrige días recientes) o desde la creación del
experimento. Un desglose que Meta rechaza no tumba los otros. Cortan la pasada entera dos cosas: un **código de
límite** (la familia de `meta_errores._LIMITE`: 4/17/32/613 y 80000…80014 por caso de uso de negocio;
`meta_errores.es_limite`, a la que delega `meta_detalle.es_limite`) y un **fallo de red o HTTP 5xx** (texto
«falló en red» / «respondió 5…» de `meta_ads.auth.llamar`; marca `cortado`, no `limite`). `exp_detalle` no dice «al
día» con lo que falta: con límite devuelve `Continuar("exp_detalle", {…, "vuelta": n+1}, ejecutar_desde=ahora+30 min)`
hasta 3 vueltas y a la tercera termina diciendo que quedó incompleto; con errores nombra las partes que fallaron. El
estado queda en `experimento.extra["detalle_meta"]` (`actualizado_en`, `desde`, `errores` sin token, `limite`,
`cortado`).
Reglas para quien lea o muestre esos datos: (a) `metrica_dia` y `metrica_desglose` **no tienen columna `cliente`**:
todo lector las une con `experimento_pieza` y filtra por `cliente` y `experimento_id`, nunca con un id que venga del
navegador sin ese join (si no, un proyecto lee las cifras de otro). (b) `detalle_meta.errores` guarda texto crudo de
Meta (ya sin token): se muestra con `meta_errores.explicar` y con el autoescape de Jinja, nunca con `|safe`. (c) El
alcance y la frecuencia **diarios no se suman** entre días: la frecuencia del periodo o de la pieza sale del último
`metrica_snapshot` (acumulada de por vida) y se rotula «acumulada»; la regla de fatiga usa esa, no la diaria.
