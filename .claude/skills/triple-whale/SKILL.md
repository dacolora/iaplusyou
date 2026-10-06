---
name: triple-whale
description: "Triple Whale: conexión, sincronización por SQL, la pestaña de rendimiento con veredictos y diagnóstico, «Evaluar con IA», avisos y la atribución de experimentos por Triple Whale. Cargar antes de tocar triple_whale/, triple_whale_tiendas.py, tareas/triple_whale.py o _tab_triple_whale.html."
---

# Triple Whale

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Triple Whale** (package `triple_whale/`, `triple_whale_tiendas.py`, `tareas/triple_whale.py`; spec
`docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md`, migrations 0023 and 0024): connected from
the Triple Whale tab itself (`_triple_whale_conectar.html`, included by `_tab_triple_whale.html` in both states;
until 2026-09-28 the form sat in Configuración › Conexiones, and the `cfg_triple_whale_*` routes now return to
`#triplewhale`) (Fernet-encrypted API key; `cfg_triple_whale_conectar` requires a verified correo,
same origin, and tests the key AND a short SQL query before saving; `cfg_triple_whale_ajustes` changes
currency/model/window). The client (`triple_whale/__init__.py`) follows the documented SQL endpoint:
`{"shopId", "query", "period": {startDate, endDate}, "currency"}` → `data` (an older version sent an
undocumented `parameters` and read `rows`, so it never returned anything); `ErrorLlave`/`ErrorTienda`/
`ErrorConsulta`; `MODELOS`/`VENTANAS` are Triple Whale's own vocabulary (old «First Touch»/«7» values are
normalized on read); every query has a full and a minimal version (`consultar_con_respaldo` falls back only
on `ErrorConsulta`). On connect `tw_sincronizar` copies 90 days into `tw_anuncio_dia` (per canal/ad/day:
what the platform reports from `ads_table` + what the Triple Pixel attributes from `pixel_joined_tvf()` with
the project's model/window) and `tw_tienda_dia` (`blended_stats_tvf()`); the periodic
`tw_sincronizar_todas` (2 h, before `exp_refrescar_todos`) re-pulls the last 7 days because Triple Whale
re-attributes; each `triple_whale.datos.reemplazar_*` zeroes/deletes the range before writing. Changing
store/currency/model/window or disconnecting deletes the copies (never the paid evaluations). The
**Triple Whale tab** (`_tab_triple_whale.html`, `data-tab="triplewhale"`, after Alertas; since E2, 2026-10-03, there is
no Tablero tab) fetches its panel
(`triple_whale.rutas.ver_panel` → `_tw_panel.html`) only when opened: store KPIs (MER, AOV, new customers,
vs. previous period), ad KPIs, alerts, a day-by-day chart drawn by the old Tablero's `dashboard._grafico_tablero`
(`app.extensions["grafico_tablero"]`; the Tablero itself no longer computes a chart), spend by
verdict/channel and every ad with a verdict and a diagnosis from the pure `triple_whale/evaluacion.py`
(compared with the account's own medians; `ganador`/`prometedor`/`en_prueba`/`perdedor`/`sin_datos`; weak
hook, low hold, few clicks, clicks without sales, expensive CPM, fatigue 7d vs 7d, no TW tracking).
«Evaluar con IA» (`tw_evaluar`, `max_intentos=1`, price `gastos.estimar("evaluacion_tw", n=)`, real spend as
tipo `evaluacion`) sends Claude up to 6 winners + 4 losers with their Meta thumbnail (`analisis.medios_meta`,
read-only Graph) and doctrina `clasificar/angulo/gancho/video`; the result (`tw_evaluacion`) has patterns,
per-ad «why», and new ad ideas with a validated ángulo and an English video prompt. `triple_whale/puente.py`:
«Llevar a Crear» sets `session["fp_prefill"]` (nothing is generated) and «Guardar en Referentes» stores a
winning own ad as a project referente (fuente `triple_whale`, `anuncio_id = tw:<ad_id>`, thumbnail in R2).
Experiments with `atribucion="triple_whale"`: `lanzador.refrescar` keeps traffic, spend and ad status from
Meta (the old path skipped Meta, so rejections went unseen) and overrides purchases/revenue with the Pixel
orders from `tw_anuncio_dia` since the piece was created (after `sync.sincronizar_si_hace_falta`, once per
experiment, outside the Meta lock); another currency → ROAS 0 + one evento, like `tienda`. `"triple_whale"`
stays in `tablero.FUENTES_VENTAS` and `decisor.py`'s `con_atribucion`. With Triple Whale connected, every
creative Creatv creates (`lanzador._crear_anuncios`, and the legacy `tareas/meta.publicar`) carries
`url_tags=triple_whale.URL_TAGS` (`tw_source={{site_source_name}}&tw_adid={{ad.id}}`, resolved by Meta; the
`meta_ads.creative` functions take an optional `url_tags` for the AdCreative's «URL parameters»), via
`triple_whale_tiendas.url_tags(cliente)` — None without Triple Whale; ads created before connecting keep
none (changing them sends the ad back to review). Second round (spec §11–§13): `tw_producto_dia` (migration
0024) copies `orders_table` opened by `products_info` in the same sync (`consultas_productos`, full/minimal,
never verified: §9.5) → «Lo que más se vende» in the tab (`panel.productos_periodo`, matched to the Catálogo
by `fuente_id`/name) and the top 5 in the AI prompt (each idea carries `producto`); a Creatv-made ad
(`datos.piezas_creatv`, now with the pieza's video/thumbnail/state) sends Claude the real frames
(`analisis.visuales` → `sprints.qa.archivo_local` + `doctrina.revisor.bloques_visuales`, temp file deleted
in a `finally`; `anuncio.visual`), every Meta thumbnail is copied to R2 first (`analisis.copiar_miniaturas`,
`clientes/<c>/triple_whale/eval<id>_<ref>.jpg`); after every sync `triple_whale/avisos.py` emails (tipo
`tw_evaluacion`) new winners, fatiguing winners, new losers and «no attributed sales» once (state in
`triple_whale.extra.avisados` / `aviso_sin_ventas`; first sync only seeds the baseline); «Pausar»/«Activar» on a
Creatv piece in the tab (`triple_whale.pieza_estado` → `lanzador.pausar_pieza`/`activar_pieza`); and the
Experimentos results center shows «Tu tienda según Triple Whale» (`panel.resumen_mes_tienda`, part `tienda_tw` of
`dashboard._calcular_tablero`; the cache key includes `triple_whale.actualizado_en`) in two places: a line with the month's
revenue and MER under «01 Resumen del periodo» (`_exp_resultados.html`) and its tiles at the end of the folded
«Historial» (`_exp_historial.html`). Idea → pieza → anuncio (spec §14): the prefill of «Llevar a Crear»
carries `origen_tw` («<evaluación>:<índice>»), the Crear form returns it in a hidden field and `cf_crear_video`
stores `concepto.extra.tw_idea` (`puente.origen_desde_formulario` validates it, a bad value is ignored); the
idea card lists the pieces born from it with their Crear state and Meta verdict (`datos.piezas_de_evaluacion`,
`panel.enlazar_ideas`) and a Creatv ad says which idea it came from (`piezas_creatv(...)["tw_idea"]`). None of
the SQL has run against a real store yet (spec §9).
