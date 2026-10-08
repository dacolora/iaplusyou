---
name: triple-whale
description: "Triple Whale: conexión, sincronización por SQL, la pestaña de rendimiento con veredictos y diagnóstico, «Evaluar con IA», avisos y la atribución de experimentos por Triple Whale. Cargar antes de tocar triple_whale/, triple_whale_tiendas.py, tareas/triple_whale.py o _tab_triple_whale.html."
---

# Triple Whale

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Triple Whale** (package `triple_whale/`, `triple_whale_tiendas.py`, `tareas/triple_whale.py`; spec
`docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md`, migrations 0023, 0024 and 0032): connected from
the Triple Whale tab itself (`_triple_whale_conectar.html`, included by `_tab_triple_whale.html` in both states;
until 2026-09-28 the form sat in Configuración › Conexiones, and the `cfg_triple_whale_*` routes now return to
`#triplewhale`) (one Fernet-encrypted API key PER STORE; `cfg_triple_whale_conectar` adds a store: requires a verified correo, same
origin, a country (the form's or the one guessed from the domain) and tests the key AND a short SQL query before
saving; `cfg_triple_whale_ajustes` changes the project's currency/model/window; `cfg_triple_whale_probar`,
`cfg_triple_whale_pais` and `cfg_triple_whale_desconectar` act on ONE store through its `tienda_id`, 404 if it is not
the project's). The client (`triple_whale/__init__.py`) follows the documented SQL endpoint:
`{"shopId", "query", "period": {startDate, endDate}, "currency"}` → `data` (an older version sent an
undocumented `parameters` and read `rows`, so it never returned anything); `ErrorLlave`/`ErrorTienda`/
`ErrorConsulta`; `MODELOS`/`VENTANAS` are Triple Whale's own vocabulary (old «First Touch»/«7» values are
normalized on read); every query has a full and a minimal version (`consultar_con_respaldo` falls back only
on `ErrorConsulta`). On connect `tw_sincronizar` (ONE job per store, `job_id` `<cliente>__tw_sync__<tienda_id>`, payload `cliente` +
`tienda_id`; `max_intentos=2`, it only reads) copies 90 days of that store into `tw_anuncio_dia` (per
canal/ad/day: what the platform reports from `ads_table` + what the Triple Pixel attributes from `pixel_joined_tvf()`
with the project's model/window) and `tw_tienda_dia` (`blended_stats_tvf()`); the periodic `tw_sincronizar_todas`
(2 h, before `exp_refrescar_todos`) enqueues `encolar_sync(cliente, tienda_id)` for every `conectadas()` store and
each re-pulls its last 7 days because Triple Whale re-attributes; each `triple_whale.datos.reemplazar_*(cliente,
tienda_id, desde, hasta, registros)` zeroes/deletes only THAT store's range before writing. Changing
currency/model/window (`cambiar_ajustes`) deletes the copies of ALL stores; removing a store (`quitar`) deletes only its
copies, and the project's `triple_whale` settings row goes with the last one (never the paid evaluations).

## Varias tiendas, una por país (2026-10-08)

Why: happyflops has one Shopify store per country and each one lives in Triple Whale with its own shop-id and its own
API key (Daniel confirmed it on 2026-10-08), while the ads are the same in all countries; one project per country was
rejected because it would split catalog, pieces and sprints. Spec
`docs/superpowers/specs/2026-10-08-triple-whale-varias-tiendas-design.md`, migration 0032, plan in `docs/superpowers/plans/`.

- **Tables.** `tw_tienda` (one row per connected store: `pais` ISO-2 or None, `dominio`, encrypted `llave`,
  `zona_horaria`, `estado`, `error`, `ultima_sincronizacion`, `extra` = `backfill_desde`/`ultimo_resumen`/`gasto_7d`;
  unique per (cliente, dominio) and per (cliente, pais) when the country is set). `triple_whale` is now the PROJECT's
  settings (currency, model, window, `extra` = `avisados`/`aviso_sin_ventas`), one row while there is at least one store;
  its old connection columns are unused but kept so the previous deploy can still run; they are only written to EMPTY
  them: when the store they name (`dominio_tienda`) is removed or reconnected with ANOTHER key, `llave` and
  `dominio_tienda` become None and the row stays with its settings and avisos (`_vaciar_conexion_vieja`; 2026-10-08,
  security audit: an old copy of a rotated key must not linger). `tw_tienda` has AUTOINCREMENT (db.py and 0032):
  a removed store's id is never reused, so an old evaluation's `tienda_id` never takes another store's name. The three copies
  (`tw_anuncio_dia`, `tw_tienda_dia`, `tw_producto_dia`) carry `tienda_id` (NOT NULL, no FK) inside their unique keys.
- **Single writer.** `triple_whale_tiendas.py` writes `tw_tienda` and `triple_whale`: `agregar(cliente, llave, dominio,
  pais=None, moneda, modelo_atribucion, ventana_atribucion, zona_horaria)` (guesses the country from the domain; a
  second connect of the same domain reconnects; the project's settings are only created, never overwritten),
  `cambiar_pais(cliente, tienda_id, pais)`, `actualizar_tienda`, `actualizar_extra_tienda`, `actualizar_extra`
  (project's), `cambiar_ajustes`, `quitar(cliente, tienda_id)`; reads `ajustes`, `tiendas`, `tienda(cliente,
  tienda_id)`, `tienda_de_pais`, `obtener` (settings + `tiendas`, None without stores), `obtener_llave(cliente,
  tienda_id)`, `conectadas()`, `firma(cliente)` (cache key of the Tablero). A taken country raises `PaisOcupado`.
  `triple_whale/paises.py` is pure (Babel/CLDR names): `adivinar_pais(dominio)`, `es_pais`, `bandera`, `nombre_pais`.
- **Reads take `tienda_id`** as their second argument: an integer is that store, `None` is «Todas». In `datos._anuncio_dia`
  «Todas» is, per (canal, ad_id, fecha), the MAX of the channel measures (the same ad arrives through every store that
  shares an ad account: its spend counts once) and the SUM of the Pixel measures (each store attributes its own
  orders). `serie_tienda(None)` sums the stores and subtracts from `gasto` the duplicated ad spend of that day
  (`_duplicado_por_dia`: Σ over ads of sum − max) and gives it back to `utilidad_neta`; `gasto_duplicado(cliente,
  desde, hasta, tienda_id=None)` says if any is shared: None = that Σ, a store = ITS spend on the (canal, ad, day)
  that also bring spend through another store of the project (one query). The panel uses the scope being viewed, so
  a store with its own ad account shows no note, and a store that shares one repeats a line next to «Evaluar con IA»
  recommending «Todas las tiendas» (2026-10-08, spend guardian: evaluating one store alone reads the other countries'
  ad spend). `top_productos(None)` groups by normalized name (each store has its own
  product ids); `por_tienda` is the «Por tienda» table in one query (the panel orders its rows like
  `triple_whale_tiendas.tiendas`, the selector's order). The panel (`panel.contexto(cliente, dias,
  canal, tienda_id)`, `?tienda=` in `ver_panel`) has a store selector; with one store it is always that one.
- **Avisos** (`triple_whale/avisos.py`) always look at «Todas»: `tw_sincronizar` calls `avisos.revisar_y_avisar`
  only when no OTHER sync of the project is still queued or running (`syncs_en_curso`), so the LAST one to finish
  warns once with everything fresh. «Evaluar con IA» evaluates the selected scope and saves it in
  `tw_evaluacion.extra` (`tienda_id`, `pais`; None = Todas).
- **Atribución de experimentos** by the store of the piece's country: see below (`lanzador._tienda_tw_de`). A single
  store serves every country ONLY if it has no country; a store WITH a country serves only that country's pieces,
  even when it is the only one (2026-10-08, spend guardian: a Swedish piece read with the Norwegian Pixel got 0
  purchases → «perdedor» → the decisor paused it on its own in semi/auto).
- **Keys never in text.** `triple_whale.tachar_llave(texto, llave)` / `triple_whale_tiendas.sin_llave(cliente,
  tienda_id, texto)` strike the exact key value (Triple Whale may echo it without «key=», which `cola.sin_token` does
  not catch): in `_probar_triple_whale` (flash and saved `error`), in the experiment evento «Error al traer métricas
  de Triple Whale de <país o dominio>», in `ultimo_resumen.fallos` and in the sync task's error (2026-10-08,
  security audit).
- **Removed store.** Every `datos.reemplazar_*` checks inside its transaction that the store still belongs to the
  cliente (`_tienda_existe`) and writes nothing if not: a sync that was running when the store was removed must not
  leave orphan rows that «Todas» (filters only by cliente) would count.
- **Routes (dashboard.py).** `cfg_triple_whale_pais` (POST, change a store's country without touching its figures;
  `PaisOcupado` -> flash) and `cfg_triple_whale_adivinar_pais` (GET, `{"pais": "NO"}` or null from the typed domain;
  reads text only, calls nobody). The project has ONE currency, model and window for all its stores (happyflops: USD).
- Not done yet (spec §13): European countries are not in `final_edition.tipos.PAISES` (PND-147), several Meta ad
  accounts per project (PND-148), the residuals of the final reviews (PND-149), and no SQL has run against a real
  store: the first copy of happyflops-norge after the deploy is the test.

The **Triple Whale tab** (`_tab_triple_whale.html`, `data-tab="triplewhale"`, after Alertas; since E2, 2026-10-03, there is
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
orders of THE STORE OF THE PIECE'S COUNTRY (`lanzador._tienda_tw_de`: the country's store, or the only one if the
project has one WITHOUT a country; `datos.totales_anuncio` raises `ValueError` without a store) from `tw_anuncio_dia` since the piece was
created (after `sync.sincronizar_si_hace_falta` once per store used, outside the Meta lock). A piece whose country
has no store keeps Meta's sales and leaves ONE evento per experiment and country
(`extra.aviso_sin_tienda_tw`); a piece WITHOUT a country does the same with the mark "" and its own text «Una pieza
sin país no tiene tienda de Triple Whale…» (2026-10-08, spend guardian: before it fell to Meta silently). Every `datos.reemplazar_*` checks inside its transaction that the store still
exists for the cliente (a removed store's running sync writes nothing). Currency comes from the project's
`ajustes`; another currency → ROAS 0 + one evento, like `tienda`. `"triple_whale"`
stays in `tablero.FUENTES_VENTAS` and `decisor.py`'s `con_atribucion`. With Triple Whale connected, every
creative Creatv creates (`lanzador._crear_anuncios`, and the legacy `tareas/meta.publicar`) carries
`url_tags=triple_whale.URL_TAGS` (`tw_source={{site_source_name}}&tw_adid={{ad.id}}`, resolved by Meta; the
`meta_ads.creative` functions take an optional `url_tags` for the AdCreative's «URL parameters»), via
`triple_whale_tiendas.url_tags(cliente)` — None without Triple Whale; ads created before connecting keep
none (changing them sends the ad back to review). Second round (spec §11–§13): `tw_producto_dia` (migration
0024) copies `orders_table` opened by `products_info` in the same sync (`consultas_productos`, full/minimal;
checked against happyflops-norge on 2026-10-08, PND-150: `products_info` is an array of objects opened with
`ARRAY JOIN products_info AS p`, fields `product_id`, `product_name`, `product_sku`, `product_name_price` (unit),
`product_name_quantity_sold`, `net_discount_amount_for_product`; price × quantity matches the store's
`gross_product_sales`; the full query subtracts the discount) → «Lo que más se vende» in the tab (`panel.productos_periodo`, matched to the Catálogo
by `fuente_id`/name) and the top 5 in the AI prompt (each idea carries `producto`); a Creatv-made ad
(`datos.piezas_creatv`, now with the pieza's video/thumbnail/state) sends Claude the real frames
(`analisis.visuales` → `sprints.qa.archivo_local` + `doctrina.revisor.bloques_visuales`, temp file deleted
in a `finally`; `anuncio.visual`), every Meta thumbnail is copied to R2 first (`analisis.copiar_miniaturas`,
`clientes/<c>/triple_whale/eval<id>_<ref>.jpg`); after the LAST sync of the project (see «Varias tiendas») `triple_whale/avisos.py` emails (tipo
`tw_evaluacion`, over «Todas») new winners, fatiguing winners, new losers and «no attributed sales» once (state in
`triple_whale.extra.avisados` / `aviso_sin_ventas`; first sync only seeds the baseline); «Pausar»/«Activar» on a
Creatv piece in the tab (`triple_whale.pieza_estado` → `lanzador.pausar_pieza`/`activar_pieza`); and the
Experimentos results center shows «Tu tienda según Triple Whale» (`panel.resumen_total_tienda`, part `tienda_tw` of
`dashboard._calcular_tablero`; the cache key includes `triple_whale_tiendas.firma(cliente)`) in two places: a line with
revenue and MER since the first copied day under «01 Resumen del periodo» (`_exp_resultados.html`) and its tiles in the folded
«Totales desde el inicio» (`_exp_historial.html`). Since 2026-10-08 the tab opens on «Desde el inicio»
(`panel.PERIODOS = (0, 7, 14, 30, 90)`, `PERIODO_DEFECTO = 0`; `panel.periodo(0, hoy, primero)` starts at the first copied
day, `_primer_dia` = min of `datos.rango` and `datos.primer_dia_tienda`, and its «previous» is the empty day before, so no
comparison and the «vs. periodo anterior» columns are hidden); «Evaluar con IA» posts the same `dias`. Daniel asked for
every metric as a total because short periods confused their clients. `panel.resumen_mes_tienda` stays for tests only. Idea → pieza → anuncio (spec §14): the prefill of «Llevar a Crear»
carries `origen_tw` («<evaluación>:<índice>»), the Crear form returns it in a hidden field and `cf_crear_video`
stores `concepto.extra.tw_idea` (`puente.origen_desde_formulario` validates it, a bad value is ignored); the
idea card lists the pieces born from it with their Crear state and Meta verdict (`datos.piezas_de_evaluacion`,
`panel.enlazar_ideas`) and a Creatv ad says which idea it came from (`piezas_creatv(...)["tw_idea"]`). Since 2026-10-08 every query runs against the real store (happyflops-norge): ads, Pixel and products full; the store
query dropped `net_profit` (not a `blended_stats_tvf()` column — it made every copy fall back to the minimal one and
lose new customers); `utilidad_neta` stays 0 and is shown nowhere.

Coronas (2026-10-08, spec de Noruega y Suecia §3; motivo: las tiendas de happyflops son de Noruega y Suecia): `triple_whale.MONEDAS` trae NOK y SEK, así que la tienda de un país NO o SE guarda su moneda y el tablero y los experimentos la distinguen del dólar como a cualquier otra moneda local. Con moneda mezclada el ROAS se oculta (PND-138), no se convierte.
