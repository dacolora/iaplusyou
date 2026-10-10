---
name: triple-whale
description: "Triple Whale: conexión, sincronización por SQL, la pestaña de rendimiento con veredictos y diagnóstico, «Evaluar con IA», avisos y la atribución de experimentos por Triple Whale. Cargar antes de tocar triple_whale/, triple_whale_tiendas.py, tareas/triple_whale.py o _tab_triple_whale.html."
---

# Triple Whale

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Triple Whale** (package `triple_whale/`, `triple_whale_tiendas.py`, `tareas/triple_whale.py`; spec
`docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md`, migrations 0023, 0024, 0032, 0034 and 0036; the
per-ad cards are in «Tarjetas de análisis» and the hooks and new copy in «Ganchos y copy» at the end): connected from
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
(`triple_whale.rutas.ver_panel` → `_tw_panel.html`) only when opened, in this order: «Resultados de tu tienda» (cards +
the interactive day-by-day chart + day detail + reading + «Tus creativos», see the paragraph below; it replaced the
store KPI tiles «Tu tienda» and the old SVG «Día a día» on 2026-10-08), «Por tienda» (only «Todas» with 2+ stores),
alerts, «Tus anuncios» (the account's ad KPI tiles + the card gallery, see «Tarjetas de análisis»), the account's AI
evaluation, spend by verdict/channel, «Lo que más se vende» and, inside «Ver como tabla» (a closed `<details
id="tw-cada-anuncio">`, opened by the day detail's «Ver todos los anuncios →»), every ad with a verdict and a diagnosis
from the pure `triple_whale/evaluacion.py` (compared with the medians of its own channel, or the account's when the
channel has fewer than `BENCH_MIN_ANUNCIOS` comparable ads; `ganador`/`prometedor`/`en_prueba`/`perdedor`/`sin_datos`; weak
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
has no store marks sales unavailable (no Meta fallback) and leaves ONE new evento per experiment and country
(`extra.aviso_ventas_no_comparables_tw`); a piece WITHOUT a country uses the mark "" and its own text.
This notice is independent of the old fallback notice (PND-142 amended, 2026-10-08). Every `datos.reemplazar_*` checks inside its transaction that the store still
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

**«Resultados de tu tienda»** (spec `docs/superpowers/specs/2026-10-08-tw-resultados-de-tu-tienda-design.md`, pedido
de Daniel 2026-10-08 con la captura de «Día a día»): reemplazó a «Tu tienda» (tiles) y «Día a día» (el SVG de
`dashboard._grafico_tablero`, que se borró de `dashboard.py`; la pestaña Meta, que también lo usaba, se llevó el
cálculo y sus estilos a `meta_rendimiento/grafico.py` y `pantallas/meta.css` al mezclar main el 2026-10-08). `panel._resultados` arma UNA serie ancha (periodo +
anterior + 28 días para los días raros) y llama a `triple_whale/resultados.py` (puro: tarjetas, variaciones con días
completos — hoy va aparte —, días raros contra la mediana del mismo día de la semana, mejor día, lectura con reglas,
«Tus creativos» por mes de arranque, la tabla y el JSON). Las consultas nuevas de `datos.py` (`gasto_por_antiguedad`,
`gasto_por_canal`, `anuncios_del_dia`, `arrancaron_el`, `cohortes`) van sobre `_medidas_dia` (solo gasto MAX entre
tiendas, ventas y pedidos SUMA: `_anuncio_dia` con sus 30 columnas costaba el doble) y `_primeros_dias` (primer día
con gasto de cada anuncio en la copia: nuevo = hasta ese día + 13; la antigüedad se conoce desde el inicio de la copia +
14). `_tw_resultados.html` pinta tarjetas, lectura, creativos y tabla en el servidor y deja el JSON en
`<script type="application/json" id="tw-resultados-datos">`; `static/tw_resultados.js` (ES5, como
`exp_resultados.js`, textos en el JSON, números con los separadores de la app) dibuja la gráfica al ancho real del
contenedor y pide el detalle del día a `GET /triple-whale/dia` (`panel.contexto_dia` → `_tw_dia.html`; del primer día
copiado a ayer, 400 si no). `_tab_triple_whale.html` llama `TwResultados.iniciar(cont)` tras pintar el panel. Trampas:
un periodo anterior que empieza antes del primer día copiado NO se compara (serían ceros que no son ventas; con 10
días de prueba, «7 días» no compara); «Desde el inicio» nunca compara (5fce2658); lo atribuido del Pixel suma más que
la tienda (PND-157) y solo se usa para comparar anuncios y canales; el CSS heredado tenía un comentario cerrado con
`#}` que se tragaba `.tb-barra-tw` (por eso la gráfica vieja salía con barras naranjas y línea verde).
Reglas que añadió la revisión (2026-10-08, cada una con su prueba de mutación): los días después del último copiado
(`fin_datos`, una copia atrasada) van vacíos y fuera de cifras, comparaciones y días raros; en «Todas» la antigüedad se
cuenta desde la tienda que empezó a copiarse MÁS TARDE (`datos.inicio_para_antiguedad`); el detalle del día no marca
«nuevo» ni cuenta arranques antes de ese inicio + 14; con canal (o sin datos de tienda) cada frase, ayuda y el texto de
hoy dicen «según el Pixel»; la alerta «el MER de la tienda cayó» toma la variación de la tarjeta (días completos, sin
periodo anterior fuera de la copia); `/dia` usa `datos.primer_dia_copia` y valida el canal por su forma, sin
recorrer la copia en cada clic.

PND-142 (2026-10-08, decisión delegada enmendada): fuente_ventas_fija se fija al lanzar según la atribución: triple_whale solo con atribución triple_whale y tiendas conectadas (sin tiendas, meta); tienda para pedidos por UTM, meta para Pixel y ninguna si no mide ventas. Una fuente fijada no se cambia por conectar/desconectar después. La lectura corrige las marcas antiguas que ignoraban tienda/Pixel/ninguna. Con ninguna, ninguna foto marca ventas medibles, aunque Meta reporte compras. Si la fuente fija no está disponible, ventas_no_disponibles y ventas no comparables (—), sin respaldo a Meta; todavía se permite el cierre sin evidencia y el perdedor por tráfico del decisor, pero no ganar/escalar por ventas. Triple Whale lee solo la tienda del país. El aviso nuevo aviso_ventas_no_comparables_tw no se deduplica contra el viejo aviso de respaldo. tests/test_lote6_ventas.py, test_atribucion.py y test_lote6_decisor.py vigilan la regla, pedidos e aislamiento.

## Tarjetas de análisis (2026-10-08)

Why: Daniel (2026-10-08, three screenshots of an Instagram post) asked for one card per ad with the real creative, a
verdict, rings and «how to improve it»; the tab was a table and «Evaluar con IA» (whole account) had never been used in
production. It must work for ANY ad, not only Creatv's: in happyflops only 4 pieces have a `meta_ad_id`. Spec
`docs/superpowers/specs/2026-10-08-triple-whale-tarjetas-analisis-design.md`, plan in `docs/superpowers/plans/`.

- **Tables (migration 0034; it was 0033 until main brought `0033_cobros` on 2026-10-08).** `tw_creativo` = the ad as
  `ads_table` gives it (type, thumbnail, mp4, title, copy, duration), one row per (cliente, canal, ad_id) with NO
  store: the same ad arrives identical through every store that shares an ad account. `tw_analisis` = one paid «Cómo
  mejorarlo» (state, `foto` = the ad as it looked when asked, `resultado`, `medios`, `usd`), AUTOINCREMENT, never
  deleted with stores: it is money already spent, like `tw_evaluacion`. Only `triple_whale/datos.py` writes them; the
  one other delete is `tw_creativo` in `triple_whale_tiendas.quitar`/`desconectar` (`_borrar_creativos`) when the LAST
  store goes. It is not in `_borrar_copias`, so changing currency/model/window or removing one of several stores keeps
  it: it depends on neither. Reads for a page of ads go through `datos._por_claves`, a flat `(canal, ad_id) IN (…)` in
  chunks of 400: a chain of ORs hit SQLite's expression-depth limit with ~2 500 ads («Expression tree is too large»).
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
  hosts; paths `/l.php`, `/redirect`, `/link` (TikTok), `/offsite` (Pinterest), `/flx/warn` (Facebook), read as the
  server would (`_ruta_como_la_lee_el_servidor`: %-decoded, `\` as `/`, `.`/`..` segments resolved with
  `posixpath.normpath`, one leading slash, lowercase): `l.facebook.com/l.php?u=…` would send anywhere; the last three
  and `//l.php` slipped through until the final review, B8, and `/./l.php`, `/a/../l.php`, `/%2e/l.php` until its last
  pass). `conectores.url.descargar_archivo` streams to `ruta + ".part"` and
  renames on success (a cut download never destroys a good file), 60 MB cap, `tiempo_max` = 120 s for the whole
  download, enforced by a watchdog `threading.Timer` that shuts the socket down (B5: `timeout` is per read, and a
  check «between chunks» never runs while `iter_content(65536)` waits for its 64 KB, so a server dripping 1 byte every
  0.25 s held the worker 12 s with `tiempo_max=2`; proved against a real slow-drip `http.server`,
  `tests/test_conectores_descarga_lenta.py`), `video/*` only, SSRF check on every redirect. ffmpeg opens the downloaded file only if ffprobe says mp4/mov
  (`mejorar.es_mp4`, B4: it is a third-party file and an odd demuxer must not get it; ffprobe runs with
  `-protocol_whitelist file` and fails closed); otherwise the thumbnail.
- **«Cómo mejorarlo» (`triple_whale/mejorar.py`, task `tw_analizar_anuncio`).** Price first:
  `gastos.estimar("analisis_anuncio_tw", segundos=)` = tariff 0.17 + Whisper by the video's duration (30 s when
  unknown). The tariff was 0.10 until 2026-10-09, measured on the real run of 2026-10-08 (4 happyflops ads,
  `docs/superpowers/evals/2026-10-08-tw-como-mejorarlo.md`): one call US$ 0,067–0,084 with a warm cache, US$ 0,095 cold
  (the cache write), US$ 0,16 when the correction call was needed (1 of 4); Whisper ≤ US$ 0,0014 (PND-179). It is 0.17
  since the analysis also brings hooks and copy («Ganchos y copy», below): the output grew about 50 %, and the same 4
  ads measured US$ 0,086–0,111 with a warm cache and US$ 0,131–0,170 cold (mean 0,142; the 0,1696 run is the one with
  the 20 000 cap, 13 013 output tokens that the old 12 000 cap would have cut)
  (`docs/superpowers/evals/2026-10-09-tw-ganchos-y-copy.md`). The price shown is the most expensive measured cold single
  click (controller's ruling, 2026-10-10: the price seen before charging is never below what a measured single click
  cost); a tanda of 4 reads the cache and costs less, and Cobros charges the real cost × margin, the tariff is only the
  price seen beforehand (0.10 → 0.14 → 0.15 on 2026-10-09 → 0.17 on 2026-10-10). `max_intentos=1`, `job_id`
  `<cliente>__tw_anuncio__<canal>__<ad_id>`: a second click launches nothing. `id_valido` is a `fullmatch` because `$`
  lets a trailing newline through and «p1%0A» would be its own job, a second paid analysis; `encolar_analisis` refuses
  invalid ids. Spend: Whisper as `transcripcion`/fal `tw_anuncio:<aid>:t<tarea>:voz`, Claude as `evaluacion`/anthropic
  `tw_anuncio:<aid>:t<tarea>`, once, also when it fails after paying (the tokens ride the exception). The Claude call has
  `timeout=300, max_retries=0` (A6: a retry by the SDK could be paid without being recorded; a failure ends in error
  and the person asks again with the price in view). **Cobros** (main's prepaid balance, wired in when main was merged on
  2026-10-08; skill `cobros`): `tw_analizar_anuncio` is in `tareas.TIPOS_QUE_COBRAN`; `_pedir_analisis` reads the
  creative, takes the button's COST (`panel.precio_analisis(...)["usd"]`) and calls `libro.exigir(cliente, usd)` BEFORE
  closing stale rows or creating the `tw_analisis` row, then `encolar_analisis(..., costo_estimado=usd)` reserves it;
  `SaldoInsuficiente` goes up to `dashboard._saldo_insuficiente` (402 JSON to the card's fetch, which treats 402 as a
  known answer and only re-enables its buttons, since `static/cobros.js` paints «Recargar saldo»; flash to the form).
  The batch stops at the first ad without balance: the ones already queued keep their reservation, the flash says how
  many, and the exception is re-raised for the common handler. Claude's spend after a failed call goes with
  `entregado=False` (paid, not delivered: never charged), like `tw_evaluar`. The detail's figure is
  `fila.usd | cobrado('tw_anuncio:' ~ fila.id)`: `cobros.vista.clave_de` folds `…:t<id>` and `…:t<id>:voz` into that
  key, so a client of a charging project sees what was charged, never the cost. Tests:
  `tests/test_tw_tarjetas_rutas.py` (`test_sin_saldo_…`, `test_con_saldo_…`, `test_el_lote_sin_saldo_…`). The task reads its row inside the `try` and guards the `except`'s
  own write (A4), so any failure leaves the row in `error`, with words: a row stuck in `en_cola` would block that ad. Claude gets up to 8
  frames with their second (a Creatv piece's from R2, else the video, else the thumbnail), the ad text, the Whisper
  voice, rings, trend, the attribution model and window, up to 3 winners of the channel, the account evaluation, the
  project's learnings and top products; doctrina `revisar`+`diagnosticar`+`angulo`+`gancho`+`video`, the project's
  language, `max_tokens` 20 000 (12 000 until 2026-10-09, when a real run reached 11 323; only the tokens used are
  paid), one correction call (rule 7) except when the answer was cut by the cap: `mejorar._llamar` is its own call
  (same cache accounting as `_llamar_contando`) that also returns the `stop_reason`, and `max_tokens` raises
  `AnalisisCortado` with the paid tokens and no second call («La respuesta de Claude salió cortada; vuelve a
  intentarlo.»). Ad text, names and voice are someone else's text: `_dato`
  strips every run of 2+ `<`/`>` in one regex pass (two chained `replace` calls could be dodged) so a «<<<FIN>>>» in a
  copy cannot close the DATOS block, and the output only fills an escaped card and a Crear prefill the person reviews.
  Names, campaign and conjunto arrive in one line (`evaluacion._una_linea`), and in the prompt the names, the winners'
  title/copy and the account evaluation's summary and patterns go through `mejorar._linea` (`_dato` + one line; B3: a
  newline in a name opened what looked like a new part of the prompt and split the card's `data-confirmar`).
  `verificar_cifras` runs over the phrase, reasons with evidence, changes, `por_que` and the learning
  (`cifras_sin_dato`, non-blocking) against the DATA of the prompt (`mejorar.datos_verificables`: the same values
  without a word of the template; until 2026-10-09 it was the whole prompt, whose instruction numbers («3 cambios»,
  «60 a 120 palabras», «500 caracteres») let «60 días de prueba» pass into a video) plus `mejorar.segundos_verificables`
  (the «Segundo 12,6:» frame labels AND the integer part of every frame and voice-phrase second: «el segundo 31» for a
  phrase at 31,1 s is not an invented figure; the real test flagged 31 and 37 that way, 2026-10-08). `NOMBRES_CANAL` lives in `triple_whale/__init__.py` so the worker never imports the
  blueprint (`resultados.NOMBRES_CANAL` and `rutas.NOMBRES_CANAL` are that same dict).
- **Gallery.** Tab order: bar, «Resultados de tu tienda» (main's section, 2026-10-08), «Por tienda», alerts, «Tus
  anuncios» (tiles + gallery), «Lo que hace ganar en tu cuenta», «Dónde se va el gasto», «Lo que más se vende», «Ver como
  tabla». The gallery, card, analyze and batch routes resolve their scope with `panel.alcance` → `evaluar_periodo`, the
  same as the panel, «Desde el inicio» (`dias=0`, from the first copied day) included. 12 cards per page by spend (`panel.POR_PAGINA`), filters (`Muy pocos datos` is not in
  «Todos»), and a fixed number of queries whatever the cards (`panel.enriquecer`, `datos.analisis_de_anuncios`;
  `test_las_consultas_no_crecen_con_las_tarjetas`): a query per card was what made project pages take 1 158 queries
  (2026-09-28 audit). Routes: `galeria` (`entera=1`
  returns the whole block for a filter, so the batch's keys and price follow the filter; without it only the cards of
  «Ver más»), `tarjeta`, `analizar_anuncio` (JSON for the tab JS), `analizar_lote`, `analisis_detalle`,
  `analisis_crear`, `analisis_aprendizaje`, `anuncio_referente` (same thumbnail as the card). A card's bar carries
  `data-poll-al-terminar="evento"` and dispatches `trabajo-terminado` instead of reloading (ten analyses would be ten
  reloads); the tab JS repaints only that card. The async «Cómo mejorarlo» never re-POSTs on a failure: it repaints the
  card and shows a message, and paying again takes a fresh click and confirm (rule 1). The analisis routes take
  `<int(max=2**63-1):aid>` (`rutas.AID_MAX`, B7): a bigger id overflowed SQLite and gave a 500, now a 404. Whole sales
  show without a decimal (`tw_ventas`: «10 ventas», not «10,0»; D2) and «Ya se hizo N piezas con esta mejora» ends
  with the Crear state of the latest one (`panel.ETIQUETAS_PIEZA`, spec §7.1; D3).
- **Which analysis a card shows (final review A2 and A4, 2026-10-08).** `datos.analisis_de_anuncios` reads ALL rows
  of the page's keys, newest first (one query per chunk), and `panel.elegir_analisis(a, filas, alcance)` picks: `vivo`
  = the ad's deterministic job is alive (`tareas_tw.analisis_vivos`) → its bar; else `mismo` = newest row of THIS scope
  (ready → phrase + «Ver el análisis»; stale → «Analizar otra vez»; error → «Intentar otra vez»); else `otro` = newest
  READY row of another scope → neutral note + «Analizar con estos datos». Another scope's ERROR is ignored. Why: only
  the newest row was read, so a fresh analysis was hidden by a newer one of another scope, and another scope's error
  offered «Intentar otra vez» and put the ad back in the batch. A row in `en_cola`/`analizando` whose job is NOT alive
  is shown as an error («Se interrumpió antes de terminar.») and never blocks; the route closes such orphans
  (`datos.cerrar_colgados`) before creating the new row (A4: a task that died before its `try` blocked the ad forever).
- **The route never pays twice for the same data (A1).** `_pedir_analisis` refuses without charging when the ad has a
  live task or a READY analysis of this scope that is not stale («Ese anuncio ya tiene un análisis con estos datos.»;
  the JSON path returns the card): a stale tab, or the 7-day tab after visiting 30 days, still shows the button.
- **Old analysis.** `panel.es_viejo` applies only inside the same scope (`panel.mismo_alcance`: same store AND either the
  same period length or the same `desde`): a changed verdict or ≥ 1.5× the spend. «Desde el inicio» grows one day every
  day but always starts on the first copied day, so yesterday's analysis is still this scope (merge with «Resultados de
  tu tienda», 2026-10-08). The panel's CHANNEL filter is part of the scope too (A3): `foto.alcance_canal` is stored when
  asking (None or missing = «Todos»), because the verdict depends on the filter; without it an analysis looked stale
  under a filter and the batch charged it again. From another scope the card shows a neutral note and a secondary
  «Analizar con estos datos»; moving from 7 to 30 days must not nudge a second payment.
- **Batch.** «Analizar los N que más gastaron» (`panel.N_LOTE` = 10) takes exactly the ads whose card shows the primary
  paid button (`a.ofrecer_analisis`: not `sin_datos`, no live task, no fresh analysis of this scope and no ready one of
  another scope), posts the `clave=<canal>:<ad_id>` inputs the form showed with their total price, and the route
  charges only posted ∩ still-eligible, never «the next N»: a second submit of the same form charges nothing (rules 1
  and 4). The total is the sum of each card's price at the ad's real duration (A5); with any price unknown it says
  «precio no disponible», never «US$ 0». `_claves_confirmadas` dedupes with a set and stops at N_LOTE valid keys (B6).
- **From analysis to Crear and learnings.** `analisis_crear` sends `origen_tw = a<aid>`, stored as
  `concepto.extra.tw_idea = {"analisis_id", "titulo"}`; the cards list the pieces born from each analysis. The
  `aprendizaje` is saved only on click (`analisis_aprendizaje`, id `tw<aid>`, in the project's language: rule 3): saved
  learnings feed every future prompt, and the id makes two clicks or two tabs one line. `doctrina.aprendizajes._limpio`
  removes every `<` and `>` (the data tags whole, in any case; a numeric comparison of the decisor such as «8% < 25%»
  becomes «8% ＜ 25%») and the detail shows next to the button the EXACT text that will be saved («Se guarda así: …»).
  Why (B1, security audit): the ad name is third-party text and a single case-sensitive `replace("</aprendizajes>")`
  let `</APRENDIZAJES>` and `</aprend</aprendizajes>izajes>` close the block in every future prompt (ideas, guiones,
  derivaciones in auto mode). Invented figures (B2): when `cifras_sin_dato` is not empty the detail says «Claude citó
  cifras que no están en los datos: …», and an `aprendizaje` that contains one of them is neither offered nor saved
  (`mejorar.cifras_del_aprendizaje`, also in the route against an old form): it would enter every prompt as a fact.
- **Rulings that differ from the spec.** Ring code `sin_video` (above). «Pausar/Activar en Meta» stays only in «Ver como
  tabla» (the spec listed it on the card): 4 Creatv pieces live in production and the table keeps the action; the cost
  is one extra click (PND-184). The card's «Costo por venta» compares with the ad's CHANNEL (`cpa_canal`), not the
  account (spec §2.1, D4): the rings already measure inside the channel and the account's figure is mostly Meta's, so a
  Snapchat or TikTok ad looked cheap or expensive just for its channel; the verdict still uses the account's CPA.
- **Out of this change (spec §13, PND-180 to PND-186).** Stage 2 (2026-10-09, «Ganchos y copy» below) did «change only
  the hook» (half of PND-180) and «new Meta copy» (half of PND-182). What stays: «v1 vs v2 ring by ring»; predict
  before spending; duplicate the ad in Meta with the new copy; TikTok videos without frames; the retention-by-quarters curve; Whisper
  `language: null` (`fal_audio.transcribir_palabras(url, None)`): fal accepted it in the real run of 2026-10-08 (3 of 4
  ads transcribed, Norwegian and English), so PND-185 is closed; if fal ever rejects it, the task goes on without
  voice.

## Ganchos y copy (2026-10-09)

Why: Daniel (2026-10-09, «sigue con las siguientes etapas») chose «a new hook» first: an ad that already proved its body
(product, demo, offer) usually loses its money in the first 3 seconds, and regenerating only those seconds costs a
fraction of a new video. Spec `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md`, plan
`docs/superpowers/plans/2026-10-09-tw-ganchos-y-copy.md`, migration 0036 (it was 0035 until main was merged on
2026-10-09, which already had `0035_meta_rendimiento`), eval `docs/superpowers/evals/2026-10-09-tw-ganchos-y-copy.md`.

- **The analysis brings two more keys.** `mejorar.PROMPT` asks for `ganchos` (exactly 3 whenever Claude sees video
  frames, also for a winner, `[]` otherwise) and `copy_nuevo` (title + main text for Meta). `parsear(texto, verificable,
  duracion_s=None)` never gets stricter: `_ganchos` keeps up to 3 with `texto` (one line, no control/format chars, cut
  at a word, ≤ 60) and `prompt` (≤ 1 000), `fotograma_s` through `segundo_fotograma` ([0, duration − 1], else half the
  video; without a duration a number ≥ 0 stays and preparar re-clamps it against the measured file) and then
  `al_segundo_visto`: the nearest second Claude actually saw (`segundos_vistos`, read by `mejorar.segundos_vistos` from
  the «Segundo N:» frame labels and passed by the task through `analizar` → `parsear` → `_ganchos`; ties → the earlier;
  only seen seconds within [0, duration − 1], since preparar would move a later one; none → unchanged; the real run of
  2026-10-09 returned 13,5 for frames at 0,3 · 4,15 · 8 · 11,84 · 15,7, a second whose burned-in text nobody checked),
  and `cifras_sin_dato` of texto + por_que; `_copy_nuevo` is None without text and keeps line breaks. Old results have
  neither key: always read with `.get` (`'ganchos' not in r` is how the screen knows an analysis predates hooks). The
  task passes `foto.creativo.duracion_s` and empties `ganchos` when Claude saw no video frames (an image ad gets copy,
  not hooks). **Which frame:** the prompt asks for one WITHOUT burned-in text (subtitles, titles, prices); if all have
  it, the first one (second 0,3), because its subtitle is the one of the voice that plays under the hook. The real test
  (below) showed why: the clip starts on the chosen frame with its subtitle, and a frame from second 18 showed another
  moment's subtitle for 3 s against the voice. It is an instruction to the model, not a guarantee: code cannot know
  whether a frame has subtitles. **Languages:** hook text and copy in the AD's language (a Norwegian ad gets Norwegian
  text even in a Spanish project, an explicit exception to «what is saved goes in the project's language»),
  escena/por_que in the project's, prompts in English (`system()` says the three exceptions, and that they win over
  the IDIOMA line).
- **Money.** `gastos.estimar_ganchos_tw(n)` = n × Kling O3 Pro image-to-video, 3 s, no sound (US$ 0,336 each); the
  detail shows its `usd_precio` (cost × margin; None when the margin read failed, `gastos._margen_fallido`: then the
  reason is «precio no disponible», the button is disabled and the route answers 409) in the button, `data-confirmar`
  and a hidden `precio_visto` (the PRICE, back to cost once with `gastos.costo_de_precio`, ±0,005, else 409). Never
  `usd|precio`: that filter falls back to margin 1,0 and shows the cost as the price (PND-223). A hook with `cifras_sin_dato` is shown with its warning and is neither
  generated nor priced. `libro.exigir` of the total before creating anything; each clip reserves its own when
  `flowplus_lanzar.lanzar` queues it and Crear's closing (`flowplus_video`) charges it. Preparar, vigilar and armar
  never call a paid provider (all three in `TIPOS_EXENTOS_DE_COBRO`); armar and the render are ffmpeg. The analysis
  itself costs the 0.17 tariff of «Tarjetas de análisis».
- **Table `tw_gancho`** (one row per variant; AUTOINCREMENT because its id IS the code `CV<id>`), single writer
  `triple_whale/datos.py`. `crear_tanda` takes SQLite's write lock (BEGIN IMMEDIATE) BEFORE reading, checks inside that
  transaction that the analysis is the cliente's (`AnalisisAjeno`, a LookupError → the route answers 404), raises
  `TandaViva` (409) while any row of the analysis is alive, and numbers tandas per analysis; UNIQUE (analisis_id, tanda,
  n), and only THAT clash becomes `TandaViva` (`_es_choque_de_tanda`); a repeated `n` is a `ValueError` (400). `n` is
  the hook's position in Claude's list (a hook left out keeps the others' numbers). `mover` is a CAS on `estado` (with
  `vacios=` for columns that must still be NULL), so the vigilante and the tasks never advance a variant twice;
  `actualizar_gancho` never touches `estado` and has no state guard: use it only on live rows.
- **Flow.** Route `ganchos_probar` (same origin, the analysis of this cliente or 404, `int(max=AID_MAX)`) → task
  `tw_ganchos_preparar` (`<c>__tw_ganchos_<aid>_t<tanda>`, max_intentos=1, prioridad 3): downloads the original with
  `conectores.url.descargar_archivo` only from `mejorar._url_voz`, ffprobe must say mp4/mov (`es_mp4`), measures it
  BEFORE uploading anything (a video under `MIN_ORIGINAL_S` = 5 s leaves nothing in R2 or in the queue), stores it as a
  material (origen `triple_whale`, deduped by hash, shown in «Medios»), and for each row WITHOUT `cf_id` extracts the
  frame at `fotograma_s` (`-ss` before `-i`) to `clientes/<c>/triple_whale/ganchos/<gid>_<token_hex(8)>.jpg` (random
  suffix: the bare id let anyone guess the other variants' keys), creates the Crear session
  like `tareas.cadena.lanzar_escena` (kling_o3_pro, `imagen_inicial`, 3 s, no sound, `tw_gancho={gancho_id, analisis_id,
  original_hash}`), writes `cf_id` BEFORE launching (a CAS with `vacios=("cf_id",)`: a second run never launches the
  same row twice) and launches with prioridad 3. `lanzar` answering False means the clip is already in the queue (a
  clip being paid): the row goes on to `generando`, never to error. `SaldoInsuficiente` mid-way: that row and the rest
  → error with `frase_proyecto()`; the launched ones go on. If preparar fails, only rows WITHOUT a clip go to error
  (`_clip_salio`, with the project's sessions: the clip's job is alive, or its session already has the video or is in
  an error Crear can recover); a row whose clip is on its way goes to `generando`: nothing paid is lost. The periodic `tw_ganchos_vigilar` (60 s, after `cadena_vigilar`, one failing row or
  project never stops the others) moves `generando` → `armando` when the session is `video_listo` (enqueues
  `tw_gancho_armar`, `<c>__tw_gancho_<gid>_armar`, max_intentos=2, prioridad 1), keeps it in `generando` WITHOUT writing
  anything while the session is in an error Crear can recover (`ganchos.clip_recuperable`, the exact condition of
  `cf_recuperar`) for up to `ESPERA_RECUPERABLE_S` = 24 h since the row's `actualizado_en` (then error with the
  session's error), `produciendo` → `lista`/`error` from the
  final, and closes a `preparando`/`armando` row whose job is gone only after `GRACIA_S` (120 s) without changes (the
  route stores the job_id right after creating the rows and the vigilante moves to `armando` before enqueuing, so a
  fresh row has a moment with no job in the queue). In `preparando` it shows the Crear session's error when the clip
  ran and failed. `tw_gancho_armar` builds the edition (`ganchos.documento_gancho`), runs `verificar_recortes` BEFORE
  creating it (an unproducible document leaves no draft in Final edition), `versionar` and
  `rutas_editor.encolar_producciones` (the same tail as the editor's «Producir»; it takes the version the caller froze);
  it writes `edicion_id` on the row right after `ediciones.crear` and a retry REUSES that edition (saving the new
  document) instead of leaving an orphan draft and creating another; if the retry finds the render already queued or
  done it only records the ids. Only its last attempt writes the error to the row.
- **The document.** `v0` = the clip from 0 to g = min(clip, 3 000 ms), `v1` = the original from g to its end (both
  muted), the original's WHOLE audio in its own track `p_original` (rol `sonido`) from 0, and the hook text (literal,
  `borrador.ESTILO_HOOK`/`POS_HOOK`) from 0 to g: at second g the same seconds of the original are seen and heard and
  the voice stays in sync. Not in `p_sonido`: the editor's `normalizar` rebuilds `p_sonido` as a mirror of the
  principal on every operation (`sincronizarSonido`), which would silence the first 3 s the first time someone edits the
  text. Without audio in the original there is no `p_original`. The original material is found by the `original_hash`
  stored in the clip's Crear session (if the base was cleaned, it is downloaded again). Format = the closest of
  `documento.FORMATOS`; destino = the store's country if it is in `tipos.PAISES`, else the project's, else CO;
  `origen = {"tipo": "triple_whale", "pais", "analisis_id", "gancho_id"}`; the edition is named
  `<ad name> · CV<gid>` (the name is cut, the code never).
- **Screen** (`_tw_analisis.html`, by fetch, no `<script>`): «Copy nuevo para Meta» (copy buttons; a warning with figures
  not in the data, «revisa antes de publicar»), «Ganchos nuevos (primeros 3 s)» with the button or the reason in words
  (`ganchos.puede_probar`), and the latest tanda's variants (state, code with «Copiar» only when it is not in error,
  `<video preload="none" data-precarga>`, «Descargar» and the video in another tab with `rel="noopener"`; a `generando`
  variant whose clip Crear can recover says «El clip ya está pagado: recupéralo en Crear.» with «Abrir en Crear»
  (`#creativeflowplus?cf=<cf_id>`, which opens that piece's detail; sessions read once, only when such a variant
  exists, and it does not make the tab re-ask the detail), «Abrir en el
  editor», «Ver en Final edition» = the existing deep link `#final?cf=<cf_id>`); older tandas fold into one
  `<details>`. Variant rows come in ONE query (`ganchos_de_analisis`); a bar is painted only when its job is alive in
  the queue (`cola.job_ids_vivos_todos`): a bar over a finished job would fire `trabajo-terminado` at once and the tab
  would re-ask the detail in a loop. The tab JS re-asks the detail when a variant's bar ends and, while a live variant
  waits for the vigilante (`data-tw-ganchos-esperan`), every 20 s, at most 30 times in a row and only with the detail
  open. The POST is one fetch after the price confirmation and is never repeated (`tests/test_tw_tarjetas_js.py`).
- **The code.** `ganchos.codigo(gid) = "CV<gid>"`; `codigo_en(nombre)` (regex `\bCV(\d+)\b`, case-insensitive) is written
  and tested for stage 3, which will read it from the ad name in the sync to compare v1 with v2 ring by ring.
- **Real test (2026-10-09, one variant, ad 3 of the eval: HappyFluffs UGC 42,96 s).** preparar → Kling O3 Pro image to
  video accepted 3 s (clip 1080×1920 3,04 s without audio, US$ 0,336 recorded as `video:cf_…:t3`) → vigilar → armar →
  `edicion_producir` → `lista`, all in 120 s. Final 42,964 s 1080×1920 30 fps with the hook text on top; the cut at
  second 3 lands on the original's second 3 and the audio correlates 0,999 at zero offset (measured at 0,5, 5, 20 and
  38 s). The only problem was the start frame with another moment's subtitle (rule above).
- **Known gaps (all in `docs/pendientes.md`).** The figure gate is weaker than it looks: `doctrina._numeros` merges the
  digits of a decimal («4,0» → 40; PND-219, shared with Sprints and Nicho, changing it needs eval-claude), the
  copy can claim urgency or scarcity without a number («Lageret tømmes raskt») and the verifier cannot see it
  (PND-220), and the hook's `por_que` counts toward the check so a guessed figure there blocks a clean hook (PND-225).
  The scene chain still closes a recoverable clip as an error (PND-221; the hooks no longer do, fix C below). The
  originals count toward the 2 GB quota but «Medios» cannot delete origen `triple_whale` (PND-222). The `|precio` filter
  keeps showing the cost when the margin read fails in ~25 other templates (PND-223). The 20 000 cap still needs one
  eval-claude case (PND-224). preparar's own failure path does not show the Crear session's error (PND-226); small
  robustness items in PND-227. «Cómo mejorarlo» and its batch do not compare the price seen (PND-228; Cobros is off
  everywhere today).
- **Final review fixes (2026-10-09, guardian-gasto and auditor-seguridad, commits db605232..4e4a77a4, plus F and G
  from the controller's real measurement of A).** A: cap
  20 000 and a cut answer never pays a blind correction (above, «Cómo mejorarlo»). B: offers in words —
  `mejorar.TERMINOS_OFERTA` (a short reviewed heuristic list in es/en/no/sv/pt: gratis/free, envío/shipping/frakt,
  descuento/rabatt, regalo/gift, halv pris/halva priset, 2x1/«2 for 1»…; whole word or phrase, a hyphen is not a border
  so «pain-free» is not «free») and `ofertas_sin_dato(texto, verificable)` add the terms that are not in the data to the
  hook's `cifras_sin_dato` (only its `texto`, what goes in the video: the hook is not generated) and to the new copy's
  (title and text: «revisa antes de publicar»); `funciona`/`falla`/`cambios` stay digits-only. C: a recoverable clip
  keeps its row (above). D: `usd_precio` in the button and the 409 (above). E: errors copied from the Crear session or
  the final go through `_error_ajeno` (`cola.recortar(cola.sin_token(…), 500)`) and the start frame key has a random
  suffix. F: tariff 0.15 (cold single clicks 0,131–0,170, mean 0,142, plus Whisper), then 0.17 by the controller's ruling (the most expensive measured single click). G: `fotograma_s` snapped to a
  frame Claude saw (above). Not changed: the Kling prompt stays folded in a `<details>` (UX), as the auditor allowed.
- **Out of this change** (spec §11): the chip on the gallery card (PND-215), «Volver a analizar» for an old analysis
  (PND-216), hooks for image ads (PND-217), the hooks in Meta paused with their code (PND-218).
