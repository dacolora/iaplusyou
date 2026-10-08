---
name: triple-whale
description: "Triple Whale: conexión, sincronización por SQL, la pestaña de rendimiento con veredictos y diagnóstico, «Evaluar con IA», avisos y la atribución de experimentos por Triple Whale. Cargar antes de tocar triple_whale/, triple_whale_tiendas.py, tareas/triple_whale.py o _tab_triple_whale.html."
---

# Triple Whale

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Triple Whale** (package `triple_whale/`, `triple_whale_tiendas.py`, `tareas/triple_whale.py`; spec
`docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md`, migrations 0023, 0024, 0032 and 0033; the
per-ad cards are in «Tarjetas de análisis» at the end): connected from
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
with the project's model/window) and `tw_tienda_dia` (`blended_stats_tvf()`), plus products and the ads as they came
(five queries per tramo, below); the periodic `tw_sincronizar_todas`
(2 h, before `exp_refrescar_todos`) enqueues `encolar_sync(cliente, tienda_id)` for every `conectadas()` store and
each re-pulls its last 7 days because Triple Whale re-attributes; each `triple_whale.datos.reemplazar_*(cliente,
tienda_id, desde, hasta, registros)` zeroes/deletes only THAT store's range before writing. Changing
currency/model/window (`cambiar_ajustes`) deletes the copies of ALL stores; removing a store (`quitar`) deletes only its
copies, and the project's `triple_whale` settings row and the ads as they came (`tw_creativo`) go with the last one
(never the paid evaluations and analyses).

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
vs. previous period), ad KPIs, alerts, «Tus anuncios» (the account tiles + the card gallery, see «Tarjetas de
análisis»), the account's AI evaluation, a day-by-day chart drawn by the old Tablero's `dashboard._grafico_tablero`
(`app.extensions["grafico_tablero"]`; the Tablero itself no longer computes a chart), spend by
verdict/channel and, inside «Ver como tabla», every ad with a verdict and a diagnosis from the pure
`triple_whale/evaluacion.py` (compared with the medians of its own channel, or the account's when the channel has
fewer than `BENCH_MIN_ANUNCIOS` comparable ads; `ganador`/`prometedor`/`en_prueba`/`perdedor`/`sin_datos`; weak
hook, low hold, few clicks, clicks without sales, expensive CPM, fatigue 7d vs 7d, no TW tracking).
«Evaluar con IA» (now «Lo que hace ganar en tu cuenta»; `tw_evaluar`, `max_intentos=1`, price `gastos.estimar("evaluacion_tw", n=)`, real spend as
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
0024) copies `orders_table` opened by `products_info` in the same sync (`consultas_productos`, full/minimal,
never verified: §9.5) → «Lo que más se vende» in the tab (`panel.productos_periodo`, matched to the Catálogo
by `fuente_id`/name) and the top 5 in the AI prompt (each idea carries `producto`); a Creatv-made ad
(`datos.piezas_creatv`, now with the pieza's video/thumbnail/state) sends Claude the real frames
(`analisis.visuales` → `sprints.qa.archivo_local` + `doctrina.revisor.bloques_visuales`, temp file deleted
in a `finally`; `anuncio.visual`), every Meta thumbnail is copied to R2 first (`analisis.copiar_miniaturas`,
`clientes/<c>/triple_whale/eval<id>_<ref>.jpg`); after the LAST sync of the project (see «Varias tiendas») `triple_whale/avisos.py` emails (tipo
`tw_evaluacion`, over «Todas») new winners, fatiguing winners, new losers and «no attributed sales» once (state in
`triple_whale.extra.avisados` / `aviso_sin_ventas`; first sync only seeds the baseline); «Pausar»/«Activar» on a
Creatv piece in the tab (`triple_whale.pieza_estado` → `lanzador.pausar_pieza`/`activar_pieza`); and the
Experimentos results center shows «Tu tienda según Triple Whale» (`panel.resumen_mes_tienda`, part `tienda_tw` of
`dashboard._calcular_tablero`; the cache key includes `triple_whale_tiendas.firma(cliente)`) in two places: a line with the month's
revenue and MER under «01 Resumen del periodo» (`_exp_resultados.html`) and its tiles at the end of the folded
«Historial» (`_exp_historial.html`). Idea → pieza → anuncio (spec §14): the prefill of «Llevar a Crear»
carries `origen_tw` («<evaluación>:<índice>»), the Crear form returns it in a hidden field and `cf_crear_video`
stores `concepto.extra.tw_idea` (`puente.origen_desde_formulario` validates it, a bad value is ignored); the
idea card lists the pieces born from it with their Crear state and Meta verdict (`datos.piezas_de_evaluacion`,
`panel.enlazar_ideas`) and a Creatv ad says which idea it came from (`piezas_creatv(...)["tw_idea"]`). None of
the SQL has run against a real store yet (spec 2026-09-28 §9).

## Tarjetas de análisis (2026-10-08)

Why: Daniel (2026-10-08, three screenshots of an Instagram post) asked for one card per ad with the real creative, a
verdict, rings and «how to improve it»; the tab was a table and «Evaluar con IA» (whole account) had never been used in
production. It must work for ANY ad, not only Creatv's: in happyflops only 4 pieces have a `meta_ad_id`. Spec
`docs/superpowers/specs/2026-10-08-triple-whale-tarjetas-analisis-design.md`, plan in `docs/superpowers/plans/`.

- **Tables (migration 0033).** `tw_creativo` = the ad as `ads_table` gives it (type, thumbnail, mp4, title, copy,
  duration), one row per (cliente, canal, ad_id) with NO store: the same ad arrives identical through every store that
  shares an ad account. `tw_analisis` = one paid «Cómo mejorarlo» (state, `foto` = the ad as it looked when asked,
  `resultado`, `medios`, `usd`), AUTOINCREMENT, never deleted with stores: it is money already spent, like
  `tw_evaluacion`. Only `triple_whale/datos.py` writes them; the one other delete is `tw_creativo` in
  `triple_whale_tiendas.quitar`/`desconectar` (`_borrar_creativos`) when the LAST store goes. It is not in
  `_borrar_copias`, so changing currency/model/window or removing one of several stores keeps it: it depends on neither.
  Reads for a page of ads go through `datos._por_claves`, a flat `(canal, ad_id) IN (…)` in chunks of 400: a chain of
  ORs hit SQLite's expression-depth limit with ~2 500 ads («Expression tree is too large»).
- **Sync.** `triple_whale.consultas_creativos()` (full/minimal) is the fifth query of each tramo, in its own step. A
  failure goes to `ultimo_resumen.fallos["creativos"]` (key struck) and the copy continues, and it is not retried in
  later tramos: a card without its creative still has its numbers, and the ads must never be lost for this.
- **Free calculation (`evaluacion.py`, pure).** The diagnosis uses medians PER CHANNEL (a Snapchat ad was being measured
  with Meta's CTR), falling back to the account's when the channel has fewer than `BENCH_MIN_ANUNCIOS` comparables; the
  verdict keeps the account's bench and CPA, because the business looks at its total cost per sale. Rings = percentile
  inside the ad's own channel and scope: `gancho`, `retencion`, `clic`, `compra`. Empty-ring codes: `sin_video` (the
  channel reports no video metrics; the spec said `es_imagen`, but a video with zero 3 s views is not an image),
  `pocos_datos`, `pocas_comparables`, `sin_ventas`, `pocos_clics`. The raw figure still shows without a percentile; the
  `clic` value is a percentage, the others are fractions, so format each accordingly. Trend: `cansando`, `mejorando`,
  `sin_gasto`, `estable`, or None without evidence.
- **Media allow-list.** Only `triple_whale.medio_permitido(url)` (https, no userinfo or odd port, host exactly
  `files.triplewhale.com` or the R2 host) is embedded or downloaded: the URLs arrive inside ad-platform data and our
  server fetches them and hands them to ffmpeg and fal (SSRF). A TikTok video arrives as a page, so it is a «Ver en
  TikTok» link: `enlace_permitido(url, canal)` accepts only the ad's own platform and refuses redirectors (`l.`/`lm.`
  hosts, `/l.php`, `/redirect`: `l.facebook.com/l.php?u=…` would send anywhere). `conectores.url.descargar_archivo`
  streams to `ruta + ".part"` and renames on success (a cut download never destroys a good file), 60 MB cap, `video/*`
  only, SSRF check on every redirect.
- **«Cómo mejorarlo» (`triple_whale/mejorar.py`, task `tw_analizar_anuncio`).** Price first:
  `gastos.estimar("analisis_anuncio_tw", segundos=)` = tariff 0.08 + Whisper by the video's duration (30 s when
  unknown). The 0.08 is an initial guess, not measured (PND-171). `max_intentos=1`, `job_id`
  `<cliente>__tw_anuncio__<canal>__<ad_id>`: a second click launches nothing. `id_valido` is a `fullmatch` because `$`
  lets a trailing newline through and «p1%0A» would be its own job, a second paid analysis; `encolar_analisis` refuses
  invalid ids. Spend: Whisper as `transcripcion`/fal `tw_anuncio:<aid>:t<tarea>:voz`, Claude as `evaluacion`/anthropic
  `tw_anuncio:<aid>:t<tarea>`, once, also when it fails after paying (the tokens ride the exception). Any failure after
  reading the row leaves it in `error`, with words: a row stuck in `en_cola` would block that ad. Claude gets up to 8
  frames with their second (a Creatv piece's from R2, else the video, else the thumbnail), the ad text, the Whisper
  voice, rings, trend, the attribution model and window, up to 3 winners of the channel, the account evaluation, the
  project's learnings and top products; doctrina `revisar`+`diagnosticar`+`angulo`+`gancho`+`video`, the project's
  language, `max_tokens` 12 000, one correction call (rule 7). Ad text, names and voice are someone else's text: `_dato`
  strips every run of 2+ `<`/`>` in one regex pass (two chained `replace` calls could be dodged) so a «<<<FIN>>>» in a
  copy cannot close the DATOS block, and the output only fills an escaped card and a Crear prefill the person reviews.
  `verificar_cifras` runs over the phrase, reasons with evidence, changes, `por_que` and the learning
  (`cifras_sin_dato`, non-blocking). `NOMBRES_CANAL` lives in `triple_whale/__init__.py` so the worker never imports the
  blueprint.
- **Gallery.** Tab order: bar, «Tu tienda», alerts, «Tus anuncios» (tiles + gallery), «Lo que hace ganar en tu cuenta»,
  day by day…, «Ver como tabla». 12 cards per page by spend (`panel.POR_PAGINA`), filters (`Muy pocos datos` is not in
  «Todos»), and a fixed number of queries whatever the cards (`panel.enriquecer`, `datos.ultimos_analisis`;
  `test_las_consultas_no_crecen_con_las_tarjetas`): a query per card was what made project pages take 1 158 queries
  (2026-09-28 audit). Routes: `galeria` (`entera=1`
  returns the whole block for a filter, so the batch's keys and price follow the filter; without it only the cards of
  «Ver más»), `tarjeta`, `analizar_anuncio` (JSON for the tab JS), `analizar_lote`, `analisis_detalle`,
  `analisis_crear`, `analisis_aprendizaje`, `anuncio_referente` (same thumbnail as the card). A card's bar carries
  `data-poll-al-terminar="evento"` and dispatches `trabajo-terminado` instead of reloading (ten analyses would be ten
  reloads); the tab JS repaints only that card. The async «Cómo mejorarlo» never re-POSTs on a failure: it repaints the
  card and shows a message, and paying again takes a fresh click and confirm (rule 1).
- **Old analysis.** `panel.es_viejo` applies only inside the same scope (same store and same period length): a changed
  verdict or ≥ 1.5× the spend. From another scope the card shows a neutral note and a secondary «Analizar con estos
  datos»; moving from 7 to 30 days must not nudge a second payment.
- **Batch.** «Analizar los N que más gastaron» (`panel.N_LOTE` = 10; `sin_datos`, fresh and in-flight ads are skipped)
  posts the `clave=<canal>:<ad_id>` inputs the form showed with their total price, and the route charges only posted ∩
  still-eligible, never «the next N»: a second submit of the same form charges nothing (rules 1 and 4).
- **From analysis to Crear and learnings.** `analisis_crear` sends `origen_tw = a<aid>`, stored as
  `concepto.extra.tw_idea = {"analisis_id", "titulo"}`; the cards list the pieces born from each analysis. The
  `aprendizaje` is saved only on click (`analisis_aprendizaje`, id `tw<aid>`, in the project's language: rule 3): saved
  learnings feed every future prompt, and the id makes two clicks or two tabs one line.
- **Rulings that differ from the spec.** Ring code `sin_video` (above). «Pausar/Activar en Meta» stays only in «Ver como
  tabla» (the spec listed it on the card): 4 Creatv pieces live in production and the table keeps the action; the cost
  is one extra click (PND-176).
- **Out of this change (spec §13, PND-171 to PND-178).** Measuring the tariff with `eval-claude` (4 real ads, ≈ US$ 0,35,
  Daniel's yes first); «v1 vs v2 ring by ring» and «change only the hook»; predict before spending; new Meta copy;
  TikTok videos without frames; the retention-by-quarters curve; Whisper `language: null`
  (`fal_audio.transcribir_palabras(url, None)`) never sent to the real fal API: if fal rejects it, the task goes on
  without voice.
