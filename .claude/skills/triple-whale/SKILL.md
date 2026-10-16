---
name: triple-whale
description: "Triple Whale: conexión, sincronización por SQL, veredictos y diagnóstico por anuncio, las tarjetas con «Cómo mejorarlo», «Evaluar con IA», avisos y la atribución de experimentos por Triple Whale (su pantalla es la pestaña Rendimiento, skill rendimiento). Cargar antes de tocar triple_whale/, triple_whale_tiendas.py, tareas/triple_whale.py, _tw_secciones.html, _tw_galeria.html o _triple_whale_conectar.html."
---

# Triple Whale

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**La pantalla es la pestaña Rendimiento desde el 2026-10-09** (Triple Whale y Meta juntos; skill `rendimiento`,
spec `2026-10-09-pestana-rendimiento-design.md`): la pestaña «Triple Whale» (`_tab_triple_whale.html`, `_tw_panel.html`,
`triple_whale.rutas.ver_panel` y `sincronizar`) se jubiló y sus enlaces viejos (`#triplewhale`) abren Rendimiento. Lo de
abajo que habla de «la pestaña» o «el panel» describe hoy las secciones de Triple Whale dentro de Rendimiento
(`_tw_secciones.html`, `_tw_galeria.html`), que siguen leyendo `triple_whale.panel.contexto` y posteando a
`triple_whale/rutas.py` con el alcance de la entrada (R13). Excepción desde Rendimiento E2 tarea 4 (2026-10-10): la
galería de tarjetas es UNA con los anuncios de Triple Whale y de Meta, y sus rutas (galería, tarjeta, «Cómo
mejorarlo», lote) son de la pestaña (`pestana_rendimiento/rutas.py`, skill `rendimiento`); cobran con
`triple_whale/pedidos.py` y el alcance de Triple Whale para cada anuncio de Triple Whale. Desde la tarea 5, también
«Evaluar con IA» (`rendimiento.evaluar`, un botón por fuente). Todo `_volver` de este paquete
y de `cfg_triple_whale_*` vuelve a `#rendimiento`.

**Triple Whale** (package `triple_whale/`, `triple_whale_tiendas.py`, `tareas/triple_whale.py`; spec
`docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md`, migrations 0023, 0024, 0032, 0034, 0036 (NVP) and 0037 (hooks); the
per-ad cards are in «Tarjetas de análisis» and the hooks and new copy in «Ganchos y copy» at the end): connected from
«Ajustes» of the Rendimiento tab (`_triple_whale_conectar.html`, included by `_tab_triple_whale.html` until
2026-10-09 and by `_tab_rendimiento.html` since; until 2026-09-28 the form sat in Configuración › Conexiones, and the
`cfg_triple_whale_*` routes now return to `#rendimiento`) (one Fernet-encrypted API key PER STORE; `cfg_triple_whale_conectar` adds a store: requires a verified correo, same
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
  second connect of the same domain reconnects; with no stores the form's settings are saved even if their row already exists; with stores they are preserved),
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
  product ids); `por_tienda` gives every store's totals in one query (Rendimiento's «Por país» reads it, in the
  selector's order; the old «Por tienda» table went with its tab on 2026-10-09). `panel.contexto(cliente, dias, canal,
  tienda_id)` reads one store or «Todas»; the selector is Rendimiento's (one entry per country; the old `?tienda=`
  still works there through `entradas.de_legado`).
- **Avisos** (`triple_whale/avisos.py`) always look at «Todas»: `tw_sincronizar` calls `avisos.revisar_y_avisar`
  only after `triple_whale_tiendas.reservar_aviso_sync` atomically marks its completion and finds no other unfinished sync, so the LAST one to finish
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

The **Triple Whale sections of the Rendimiento tab** (until 2026-10-09 the «Triple Whale» tab, `data-tab="triplewhale"`;
order and layout in the skill `rendimiento`): «Resultados de tu tienda» (cards + the interactive day-by-day chart + day
detail + reading + «Tus creativos», see the paragraph below; it replaced the store KPI tiles «Tu tienda» and the old SVG
«Día a día» on 2026-10-08), alerts, «Tus anuncios» (the account's ad KPI tiles + the card gallery, see «Tarjetas de
análisis»), the account's AI evaluation, spend by verdict/channel, «Lo que más se vende» and, inside «Ver como tabla» (a
closed `<details id="tw-cada-anuncio">`, opened by the day detail's «Ver todos los anuncios →»), every ad with a verdict
and a diagnosis from the pure `triple_whale/evaluacion.py` (compared with the medians of its own channel, or the account's when the
channel has fewer than `BENCH_MIN_ANUNCIOS` comparable ads; `ganador`/`prometedor`/`en_prueba`/`perdedor`/`sin_datos`; weak
hook, low hold, few clicks, clicks without sales, expensive CPM, fatigue 7d vs 7d, no TW tracking).
«Evaluar con IA» (now «Lo que hace ganar en tu cuenta»; `tw_evaluar`, `max_intentos=1`, price `gastos.estimar("evaluacion_tw", n=)`, real spend as
tipo `evaluacion`) sends Claude up to 6 winners + 4 losers with their Meta thumbnail (`analisis.medios_meta`,
read-only Graph) and doctrina `clasificar/angulo/gancho/video`; the result (`tw_evaluacion`) has patterns,
per-ad «why», and new ad ideas with a validated ángulo and an English video prompt. Its route is the Rendimiento tab's
`rendimiento.evaluar` (`fuente` "tw"; `triple_whale.rutas.evaluar` was retired in Rendimiento E2 task 5) over the
Triple Whale part of the entry. Since the final review of Rendimiento E2 (G3, 2026-10-10) the form sends `n` and
`precio_visto` (the price with the margin; without it the button is disabled) and `pedidos.pedir_evaluacion(...,
n_visto=, precio_visto=)` (keyword-only, required) creates and reserves nothing when they differ from what it computes
(E2-R6, like Meta's evaluation); the route does not ask for a verified email (S2: production has no SMTP; PND-292). Rendimiento E2 task 5 had also made it evaluate
the ads of Meta accounts without a store (`extra["fuente"] = "meta"`, «con sus métricas de Meta», `medios_meta` with
`meta_conexion.cargar`, `muestra` re-sorting the winners by revenue); at the integration with main (2026-10-10, INT-2)
that branch was retired in favour of main's «Evaluación con IA» of Meta (`meta_rendimiento/analisis.py`,
`meta_rend_evaluar`, skill `meta-rendimiento`), and `tw_evaluar`, `analisis.armar`/`PROMPT`, `muestra` and `medios_meta`
are main's again (the prompt says «de Triple Whale»; `medios_meta` still needs a launch account; its text goes
delimited since PND-286, 2026-10-12, see below). `analisis.FUENTES`/`nombre_fuente` stay: «Cómo mejorarlo» uses them for a Meta ad (below). `triple_whale/puente.py`:
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

**Shared with Meta rendimiento (2026-10-10, E2 «Evaluar con IA»).** `triple_whale.analisis` is reused, not copied, by `meta_rendimiento/analisis.py`, so a change here changes both: `llamar_con_correccion(content, system_, parsear_fn, llamar=None, correccion=None)` (`correccion(error) -> texto` is what the correction asks; TW keeps «Responde solo el JSON pedido», Meta passes `meta_rendimiento.analisis.correccion`, which asks for the complete JSON — E2-R8; ONE correction and ONLY when the answer does not parse — an answer that parses is never paid twice, E2-R5 2026-10-10: invented figures are marked, not corrected; any exception after Claude answered leaves the paid tokens on it through `anotar_tokens`, and a correction call that times out or loses the connection marks the error `sin_respuesta`, see `sin_respuesta(error)`, so the task can record the estimate), `imagenes_para`, `con_piezas_creatv` (also used by `tw_evaluar`), `copiar_miniaturas(..., carpeta=)` / `clave_miniatura(..., carpeta=)` (Meta uses `meta_rendimiento`: with the same folder its evaluation 3 overwrote TW evaluation 3's thumbnails) and `parsear(..., origen=)` (the ángulo's origin). `puente.prefill_crear(..., origen=)` carries another tab's prefixed origin («meta:<id>:<i>») in the same `origen_tw` key; `origen_desde_formulario` only accepts TW's digit forms, so it is never taken for a TW evaluation.

Coronas (2026-10-08, spec de Noruega y Suecia §3; motivo: las tiendas de happyflops son de Noruega y Suecia): `triple_whale.MONEDAS` trae NOK y SEK, así que la tienda de un país NO o SE guarda su moneda y el tablero y los experimentos la distinguen del dólar como a cualquier otra moneda local. Con moneda mezclada el ROAS se oculta (PND-138), no se convierte.

**«Resultados de tu tienda»** (spec `docs/superpowers/specs/2026-10-08-tw-resultados-de-tu-tienda-design.md`, pedido
de Daniel 2026-10-08 con la captura de «Día a día»): reemplazó a «Tu tienda» (tiles) y «Día a día» (el SVG de
`dashboard._grafico_tablero`, que se borró de `dashboard.py`; la pestaña Meta, que también lo usaba, se llevó el
cálculo y sus estilos a `meta_rendimiento/grafico.py` y `pantallas/meta.css` al mezclar main el 2026-10-08, y se
borraron con ella el 2026-10-09). `panel._resultados` arma UNA serie ancha (periodo +
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
copiado a ayer, 400 si no). `_tab_rendimiento.html` llama `TwResultados.iniciar(cont)` tras pintar el panel. Trampas:
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
Rendimiento E2 tarea 7 (2026-10-10; skill `rendimiento`): el «Qué pasó el …» de Meta y de la mezcla reusa
`resultados.detalle_dia` y `_tw_dia.html` (motivo: una sola forma del detalle). Por eso `detalle_dia` acepta en cada
anuncio `moneda` (en una mezcla cada uno va en la suya), `fuente` ("tw" | "meta") y `edad_conocida` (la antigüedad de SU
copia), `arrancaron` None (no se sabe) y devuelve `fuente`; sin esas claves el detalle de Triple Whale sale idéntico
(`test_solo_triple_whale_es_el_detalle_de_siempre` compara el HTML de las dos rutas). `armar(..., con_detalle=)`
sigue existiendo, pero hoy todas las fuentes lo ofrecen.

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
  unknown; `panel.precio_analisis(creativo, filas, fuente)`: the `tw_creativo` duration and, for a Meta-source ad
  without one, the `foto.creativo.duracion_s` an earlier analysis of the same ad saved — G2 of Rendimiento E2's final
  review, 2026-10-10 — with the rows the caller already read, for the card, the batch total and the charge alike). The tariff was 0.10 until 2026-10-09, measured on the real run of 2026-10-08 (4 happyflops ads,
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
  2026-10-08; skill `cobros`): `tw_analizar_anuncio` is in `tareas.TIPOS_QUE_COBRAN`; `pedidos.pedir_analisis` reads the
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
  voice, rings, trend, the attribution model and window, up to 3 winners of the channel, the account evaluation (never
  for a Meta-source ad: it is Triple Whale's Pixel, G4 of Rendimiento E2's final review), the project's learnings and
  top products; doctrina `revisar`+`diagnosticar`+`angulo`+`gancho`+`video`, the project's
  language, `max_tokens` 20 000 (12 000 until 2026-10-09, when a real run reached 11 323; only the tokens used are
  paid), one correction call (rule 7) except when the answer was cut by the cap: `mejorar._llamar` is its own call
  (same cache accounting as `_llamar_contando`) that also returns the `stop_reason`, and `max_tokens` raises
  `AnalisisCortado` with the paid tokens and no second call («La respuesta de Claude salió cortada; vuelve a
  intentarlo.»). Ad text, names and voice are someone else's text: `_dato`
  strips every run of 2+ `<`/`>` in one regex pass (two chained `replace` calls could be dodged) so a «<<<FIN>>>» in a
  copy cannot close the DATOS block, and the output only fills an escaped card and a Crear prefill the person reviews.
  Names, campaign and conjunto arrive in one line (`evaluacion._una_linea`), and in the prompt the names, the winners'
  title/copy and the account evaluation's summary and patterns go through `mejorar._linea` (`_dato` + one line; B3: a
  newline in a name opened what looked like a new part of the prompt and split the card's `data-confirmar`). `_dato`/`_linea`/`_RE_DELIMITADOR` live in `triple_whale/analisis.py` (`mejorar` imports
  that module, so the other way round is a circular import) and `mejorar._dato` / `_linea` are the same functions.
  «Evaluar con IA» (`analisis._bloque`, `texto_productos`) does the same since 2026-10-12 (PND-286): ad name, campaign,
  product name and sku through `_linea`, the Meta title/copy in an indented `<<<TEXTO>>>` … `<<<FIN>>>` block per ad
  (through `_dato`), and a line above `ANUNCIOS:` that says the names between « » and those blocks are data.
  `verificar_cifras` runs over the phrase, reasons with evidence, changes, `por_que` and the learning
  (`cifras_sin_dato`, non-blocking) against the DATA of the prompt (`mejorar.datos_verificables`: the same values
  without a word of the template; until 2026-10-09 it was the whole prompt, whose instruction numbers («3 cambios»,
  «60 a 120 palabras», «500 caracteres») let «60 días de prueba» pass into a video) plus `mejorar.segundos_verificables`
  (the «Segundo 12,6:» frame labels AND the integer part of every frame and voice-phrase second: «el segundo 31» for a
  phrase at 31,1 s is not an invented figure; the real test flagged 31 and 37 that way, 2026-10-08). `NOMBRES_CANAL` lives in `triple_whale/__init__.py` so the worker never imports the
  blueprint (`resultados.NOMBRES_CANAL` and `rutas.NOMBRES_CANAL` are that same dict).
- **Source in the foto (Rendimiento E2 task 1, 2026-10-10).** Why: Meta-source ads (accounts with no store) reuse this
  same paid pipeline (`tw_analisis`, `tw_analizar_anuncio`, its price and no-double-charge guarantees) instead of a
  copy. `mejorar.foto(..., fuente="triple_whale", ad_account_id=None)` now stores `"fuente"` (and `"ad_account_id"`
  with Meta); a foto saved before has no key and reads as Triple Whale. When `foto["fuente"] == "meta"` and its
  `creativo` is empty, the task reports «Trayendo el anuncio de Meta», calls `meta_rendimiento.creativo.traer` once
  (image and video copied to R2, never raises; skill `meta-rendimiento`), saves the foto with it and recomputes
  `medios["copy"]` before `mejorar.visuales`. If it brought nothing to look at (`creativo.sin_contenido`: no copy,
  title, image or video — an expired token, a network error, Meta's 75 % usage limit) the task raises
  `mejorar.AnuncioIlegible` BEFORE Whisper and Claude (the stage is declared first in `ETAPAS_ANALIZAR` since E2 task 4,
  so the bar moves while it reads): the row ends in `error` with «No pude leer el anuncio en Meta; no
  se cobró nada. Inténtalo más tarde.» and no `gasto` row (fix of the task 1 review, 2026-10-10: otherwise each one paid
  ~US$ 0,10 for an analysis blind to the ad, and the batch multiplied it). Copy alone, without media, goes on; the spend `detalle` says «un anuncio de Meta» / «la voz de un anuncio de
  Meta». The only prompt change: «con sus números de {fuente}» (`mejorar.PROMPT`, from `foto["fuente"]`) and «con sus
  métricas de {fuente}» (`analisis.PROMPT`, from `contexto["fuente"]`), names in `analisis.FUENTES` (=
  `mejorar.FUENTES`, proper names, not translated; `analisis.nombre_fuente` defaults to Triple Whale). Ruling of the E2
  plan: a source name alone does not need a new `eval-claude` measurement; the first real run is noted for Daniel.
  What a Meta analysis still reads from Triple Whale (`_evaluacion_de_cuenta`, `top_productos` by `tienda_id`) is
  unchanged in this step.
- **Shared sections (2026-10-09).** What `_tw_panel.html` painted after «Por tienda» (copy bars, the shared-account
  note, alerts, «Tus anuncios», «Lo que hace ganar», reparto, productos, «Ver como tabla») lives as macros in
  `_tw_secciones.html`, which `_rend_panel.html` calls (`_tw_panel.html` itself was retired with its tab the same
  day; since E2 task 4 «Tus anuncios» is only `tiles_anuncios` there, shown when the scope is Triple Whale only, and the
  gallery is painted by `_rend_panel.html`); a Triple Whale card of a `facebook-ads` ad shows
  «Meta reporta N×» from `m.roas_canal` (`valor_canal` / gasto) when there is that figure (spec 2026-10-09 R12; never on
  a Meta-source card).
- **Gallery.** The order of the sections is Rendimiento's (skill `rendimiento`). Since Rendimiento E2 task 4
  (2026-10-10) «Tus anuncios» is ONE gallery with the ads of both sources, ordered by spend in USD
  (`pestana_rendimiento/galeria.py`; it closed PND-196), and `panel.contexto` no longer builds a Triple Whale-only
  gallery; `panel.galeria` stays as the per-source eligibility that `pedidos.pedir_lote` recomputes. Its routes moved to
  the tab's blueprint (`pestana_rendimiento/rutas.py`: `ver_galeria`, `ver_tarjeta`, `analizar_anuncio`,
  `analizar_lote`, with `<fuente>` "tw"/"meta" in the URL) and resolve the Triple Whale scope with `panel.alcance` →
  `evaluar_periodo` from the tab's `entrada`/`dias`/`canal` (same as the panel, «Desde el inicio» included). 12 cards
  per page (`panel.POR_PAGINA`), filters (`Muy pocos datos` is not in «Todos»), and a fixed number of queries whatever
  the cards (`panel.enriquecer` once per source, `datos.analisis_de_anuncios` once for both;
  `test_las_consultas_no_crecen_con_las_tarjetas`, in both test files): a query per card was what made project pages take
  1 158 queries (2026-09-28 audit). `ver_galeria` with `entera=1` returns the whole block for a filter, so the batch's
  keys and price follow the filter; without it only the cards of «Ver más». What stays here: `analisis_detalle`,
  `analisis_crear`, `analisis_aprendizaje`, `anuncio_referente` (same thumbnail as the card; the card posts the Triple
  Whale scope to it, `params_tw`). A card's bar carries
  `data-poll-al-terminar="evento"` and dispatches `trabajo-terminado` instead of reloading (ten analyses would be ten
  reloads); the tab JS (`_tab_rendimiento.html`) repaints only that card. The async «Cómo mejorarlo» never re-POSTs on a failure: it repaints the
  card and shows a message, and paying again takes a fresh click and confirm (rule 1). The analisis routes take
  `<int(max=2**63-1):aid>` (`rutas.AID_MAX`, B7): a bigger id overflowed SQLite and gave a 500, now a 404; the account
  evaluation's `idea_crear` and `a_referente` take the same `eid` since PND-189 (2026-10-15). Whole sales
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
- **The route never pays twice for the same data (A1).** `pedidos.pedir_analisis` refuses without charging when the ad has a
  live task or a READY analysis of this scope that is not stale («Ese anuncio ya tiene un análisis con estos datos.»;
  the JSON path returns the card): a stale tab, or the 7-day tab after visiting 30 days, still shows the button.
- **Old analysis.** `panel.es_viejo` applies only inside the same scope (`panel.mismo_alcance`: same source, same store
  AND either the same period length or the same `desde`; the source since the Rendimiento E2 task 4 review: a covered Meta
  account viewed alone (R3) shows as a Meta card the SAME `(canal, ad_id)` that «Todas» shows as Triple Whale, and each
  card took the other source's analysis as its own stale one and offered to pay again forever; `foto["fuente"]`, missing
  = "triple_whale", against `alcance.get("fuente")`): a changed verdict or ≥ 1.5× the spend. «Desde el inicio» grows one day every
  day but always starts on the first copied day, so yesterday's analysis is still this scope (merge with «Resultados de
  tu tienda», 2026-10-08). The panel's CHANNEL filter is part of the scope too (A3): `foto.alcance_canal` is stored when
  asking (None or missing = «Todos»), because the verdict depends on the filter; without it an analysis looked stale
  under a filter and the batch charged it again. From another scope the card shows a neutral note and a secondary
  «Analizar con estos datos»; moving from 7 to 30 days must not nudge a second payment. The verdict only counts when
  the foto was taken with today's verdict method: every new analysis stores `foto["metodo"] = analisis.METODO_VEREDICTO`
  (2, set in `mejorar.foto`), and for a foto without it (paid before R9) only the spend makes it stale (2026-10-10,
  spend guardian: R9 moved the account's cost per sale and flipped verdicts of ads whose own numbers had not changed,
  so the card offered «Analizar otra vez» and the batch charged them again; `tests/test_rendimiento_r9_plata.py`).
- **Batch.** «Analizar los N que más gastaron» (`panel.N_LOTE` = 10) takes exactly the ads whose card shows the primary
  paid button (`a.ofrecer_analisis`: not `sin_datos`, no live task, no fresh analysis of this scope and no ready one of
  another scope), posts the `clave` inputs the form showed with their total price, and the route
  charges only posted ∩ still-eligible, never «the next N»: a second submit of the same form charges nothing (rules 1
  and 4). The total is the sum of each card's price at the ad's real duration (A5); with any price unknown it says
  «precio no disponible», never «US$ 0». `pedidos.claves_confirmadas` dedupes with a set and stops at N_LOTE valid keys (B6).
  Since E2 task 4 each key is `<fuente>:<canal>:<ad_id>` (both sources in one batch): `pestana_rendimiento.galeria`
  caps the confirmed keys at N_LOTE BETWEEN the two sources before splitting them (otherwise each source could charge
  N) and calls `pedidos.pedir_lote` per source with its own scope; the first source without balance stops everything.
- **Where the paid request lives (Rendimiento E2 task 2, 2026-10-10).** `triple_whale/pedidos.py`
  (`pedir_analisis`, `pedir_lote`, `pedir_evaluacion`, `claves_confirmadas`, `anuncio_del_alcance`), moved verbatim
  from `rutas.py` with their A1/A3/A4/B6/Cobros comments, so the Rendimiento blueprint charges a Meta-source ad
  through these same guarantees instead of a copy. Since E2 task 4, `pedir_analisis` passes the scope's source to the
  photo (`mejorar.foto(..., fuente=alc.get("fuente", "triple_whale"), ad_account_id=a.get("ad_account_id"))`: without it
  the paid task never fetched a Meta ad's media) and stores the analysis currency as `a.get("moneda") or
  alc["config"]["moneda"]` (a Meta scope with accounts in different currencies has no common one and saved None). The
  rutas alias `_claves_confirmadas` went with the batch route. `usuario` comes in explicitly (no `session`) and the routes keep
  `flash` and redirects; `pedir_lote` takes the gallery's `veredicto` (what is eligible depends on the filter) and
  re-raises `SaldoInsuficiente` with `.lote = (queued, failed)`; `pedir_evaluacion` returns `ok=None` when there is
  nothing to evaluate (the route flashes it as an error, as before) and `ok=False` when the button showed another N or
  price (G3, above). `pedir_analisis` stores `foto.alcance_dias` (the period asked for, B2: see «mismo_alcance» in the
  skill `rendimiento`).
- **From analysis to Crear and learnings.** `analisis_crear` sends `origen_tw = a<aid>`, stored as
  `concepto.extra.tw_idea = {"analisis_id", "titulo"}`; the cards list the pieces born from each analysis. The
  `aprendizaje` is saved only on click (`analisis_aprendizaje`, id `tw<aid>`, in the project's language: rule 3; for a
  Meta-source analysis it says «Ganó/Perdió/Analizado en Meta» with `origen: "meta"`, and the detail names its Meta
  account instead of «Todas las tiendas»: B1 of Rendimiento E2's final review): saved
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

## Lado Triple Whale de la pestaña Rendimiento (2026-10-09, E1 tarea 1)

Why: Triple Whale y Meta se unen en una sola pestaña «Rendimiento» (spec `docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md`);
lo atribuido por el Pixel sumaba 2,5 veces las ventas reales de la tienda (PND-157) porque contaba orígenes que no son anuncios.

- **Solo canales pagados (R9).** `datos.totales_por_anuncio` y `datos.serie_anuncios` dejan fuera todo canal sin gasto en la
  copia del alcance (`_canales_pagados`: `SUM(gasto) > 0` por canal, de la tienda o de todas, sobre toda la copia y no solo el
  periodo): orgánico, Klaviyo, Direct y lo que Triple Whale agregue mañana. `totales_anuncio` (el de UN anuncio, para
  Experimentos) no cambia: el decisor lee anuncios de Meta, que siempre tienen gasto (A4); una prueba lo fija
  (`tests/test_rendimiento_r9_plata.py`, G2 de la revisión final). `datos.canales` (el filtro «Canal») solo lista
  canales con gasto en el periodo: uno con impresiones y sin gasto daba una galería vacía (revisión final, 2026-10-10).
  No se tocan `VENTANA_DEFECTO`, `MODELO_DEFECTO` ni el ajuste de ningún proyecto.
- **Lecturas nuevas.** `datos.cuentas_meta_de_tiendas(cliente)` → `{tienda_id: {"act_…"}}` (R5: una cuenta de Meta cuyos
  anuncios llegan en la copia de una tienda está «dentro» de esa tienda; normaliza con o sin `act_`);
  `datos.totales_por_grupo(cliente, tienda_id, desde, hasta, nivel)` (`"campana"|"conjunto"`) → gasto, pedidos e ingresos del
  Pixel por campaña o conjunto, solo `facebook-ads`.
- **Parámetros.** `evaluacion.alertas(..., origen="tw"|"meta")`: con `"meta"` la alerta «sin ventas» habla del Pixel de Meta
  y no de los parámetros de rastreo. `panel.contexto(..., con_resultados=False)` no calcula «Resultados de tu tienda»
  (`"resultados"` es None); la pestaña Rendimiento arma los suyos cuando el alcance mezcla fuentes.
- **Pedir la copia.** `rutas.pedir_copia(cliente, tienda_id=None)` → (texto traducido, categoría de flash): la usa «Actualizar ahora» de Rendimiento (`rendimiento.actualizar`), con el mismo `job_id` de siempre (2026-10-09, tarea 6); la ruta `sincronizar` de la pestaña vieja se retiró en la tarea 8.
- **Lo de Meta que lee Rendimiento** vive en `meta_rendimiento.panel` por partes (`lista`, `rango_fechas`, `estructura`,
  `conjuntos_de`, `anuncios_evaluados`, `estado_copia`; skill `meta-rendimiento`); qué cuenta de Meta queda «dentro» de
  una tienda lo decide `cuentas_meta_de_tiendas` (R5), y las campañas y conjuntos de esas cuentas toman sus cifras de
  `totales_por_grupo` en la moneda de Triple Whale (skill `rendimiento`, R3).
- **Tasas.** Al terminar bien una copia, `tareas.triple_whale._asegurar_tasas(cliente)` pide a `meta_rendimiento.tasas` las
  tasas USD de la moneda del proyecto (si no es USD) desde el primer día copiado, para que «Todas» sume en dólares; nunca
  tumba la copia.

## Ganchos y copy (2026-10-09)

Why: Daniel (2026-10-09, «sigue con las siguientes etapas») chose «a new hook» first: an ad that already proved its body
(product, demo, offer) usually loses its money in the first 3 seconds, and regenerating only those seconds costs a
fraction of a new video. Spec `docs/superpowers/specs/2026-10-09-tw-ganchos-y-copy-design.md`, plan
`docs/superpowers/plans/2026-10-09-tw-ganchos-y-copy.md`, migration 0037 (it was 0035 until main was merged on
2026-10-09, which already had `0035_meta_rendimiento`, and 0036 until main brought `0036_tw_visitantes` on 2026-10-10),
eval `docs/superpowers/evals/2026-10-09-tw-ganchos-y-copy.md`.

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
  `usd|precio`: that filter falls back to margin 1,0 and shows the cost as the price (PND-231). A hook with `cifras_sin_dato` is shown with its warning and is neither
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
  open. The POST is one fetch after the price confirmation and is never repeated (`tests/test_tw_tarjetas_js.py`). Since
  the integration with Rendimiento (2026-10-10) that JS lives in `_tab_rendimiento.html` (the Triple Whale tab was retired
  on 2026-10-09) and the detail opens from the single gallery of «Tus anuncios», so an analysis of an ad of a Meta account
  without a store (Rendimiento E2, `foto.fuente = "meta"`, its video copied to R2) does NOT offer «Probar los 3 ganchos»
  since the final review of Rendimiento E2 (G1, 2026-10-10): it would charge ~US$ 1,01 of Kling through a path never
  tried in real, so `puede_probar` returns `MOTIVO_META` («Para anuncios de Meta todavía no: falta una prueba real.»)
  right after «sin ganchos», the detail shows that reason and the route answers 409 without rows or reservation. Since
  2026-10-12 there is one exception, `ganchos.prueba_meta_permitida(cliente, rol)` = an admin in a project of
  `PROYECTOS_PRUEBA_META` (`colorado_forja`), passed as `puede_probar(..., meta_en_prueba=)` by the detail and the
  paying route alike: Daniel wants the real test done in colorado_forja, «the account where everything is tested». Only
  there: with Cobros on, an admin asking in another project would pay with that client's balance (guardian-gasto).
  Open it to everyone after that test (PND-289).
- **The code.** `ganchos.codigo(gid) = "CV<gid>"`; `codigo_en(nombre)` (regex `\bCV(\d+)\b`, case-insensitive) is written
  and tested for stage 3, which will read it from the ad name in the sync to compare v1 with v2 ring by ring.
- **Real test (2026-10-09, one variant, ad 3 of the eval: HappyFluffs UGC 42,96 s).** preparar → Kling O3 Pro image to
  video accepted 3 s (clip 1080×1920 3,04 s without audio, US$ 0,336 recorded as `video:cf_…:t3`) → vigilar → armar →
  `edicion_producir` → `lista`, all in 120 s. Final 42,964 s 1080×1920 30 fps with the hook text on top; the cut at
  second 3 lands on the original's second 3 and the audio correlates 0,999 at zero offset (measured at 0,5, 5, 20 and
  38 s). The only problem was the start frame with another moment's subtitle (rule above).
- **Known gaps (all in `docs/pendientes.md`).** The figure gate is weaker than it looks: `doctrina._numeros` merges the
  digits of a decimal («4,0» → 40; PND-227, shared with Sprints and Nicho, changing it needs eval-claude), the
  copy can claim urgency or scarcity without a number («Lageret tømmes raskt») and the verifier cannot see it
  (PND-228), and the hook's `por_que` counts toward the check so a guessed figure there blocks a clean hook (PND-233).
  The scene chain still closes a recoverable clip as an error (PND-229; the hooks no longer do, fix C below). The
  originals count toward the 2 GB quota and, since PND-230 (2026-10-15), «Medios» deletes them like an upload when no
  edition uses them (armar downloads the original again if its material is gone). The `|precio` filter
  keeps showing the cost when the margin read fails in ~25 other templates (PND-231). Since PND-234 (2026-10-15) preparar's own
  failure path, like the vigilante, gives a row whose clip ran and failed its Crear session's error (`_error_ajeno`)
  instead of «Algo falló al preparar el gancho…»; small robustness items in PND-235. «Cómo mejorarlo» and its batch
  compare the price seen since 2026-10-15 (PND-236, below). `doctrina.verificar_cifras` does not check
  single-digit figures («en 2 días»), shared with Sprints and Nicho (PND-237). When `SaldoInsuficiente` hits a clip, its
  Crear session, already created, stays orphan in error (PND-238; no money). The 20 000 cap was measured in real
  (end_turn, 13 013 output tokens, US$ 0,1696; PND-232 closed).
- **Final review fixes (2026-10-09, guardian-gasto and auditor-seguridad, commits db605232..4e4a77a4, plus F and G
  from the controller's real measurement of A).** A: cap
  20 000 and a cut answer never pays a blind correction (above, «Cómo mejorarlo»). B: offers in words —
  `mejorar.TERMINOS_OFERTA` (a short reviewed heuristic list in es/en/no/sv/pt: gratis/free, envío/shipping/frakt,
  descuento/rabatt, regalo/gift, halv pris/halva priset, prueba/garantía/trial/warranty/money back/pengene
  tilbake/åpent kjøp/öppet köp…; whole word or phrase, a hyphen is not a border so «pain-free» is not «free»), plus two
  patterns with a number added by the last review (revisor, 2026-10-10): «take N pay M» in any form (`_LLEVA_PAGA`:
  «NxM» with one digit each side, since «12x10 cm» is a size; «N por/for/för M», «kjøp N betal for M», «köp N betala för
  M», «lleva N (y) paga M», «leve N pague M», «pague N lleve M», «buy N get M (free)», and since the re-review «kjøp/köp
  N, få M gratis», «compra N y llévate M gratis», «compre N e leve M grátis», read as take N + M pay N), compared by the
  offer (take, pay) and not by its form, so «3x2» and «3 por 2» are the same and «kjøp 3, få 1 gratis» is not the data's
  «2 for 1» even when «gratis» is in the data; scarcity with a number (`_ESCASEZ`: «últimas/last/siste/sista N»); and a
  trial with its days (`_PRUEBA_DIAS`: «prøv i N dager», «prova i N dagar», «try for N days»; never a bare «prøv»: the
  real hook «Prøv denne – aldri kalde føtter igjen» offers nothing). A sentence-ending period after the offer is read
  («Promo 3x2.»); a decimal is not («3x2,5 m»).
  Checked free against the 4 real eval answers: no hook newly blocked. `ofertas_sin_dato(texto, verificable)` adds the
  terms and offers that are not in the data to the
  hook's `cifras_sin_dato` (only its `texto`, what goes in the video: the hook is not generated) and to the new copy's
  (title and text: «revisa antes de publicar»); `funciona`/`falla`/`cambios` stay digits-only. C: a recoverable clip
  keeps its row (above). D: `usd_precio` in the button and the 409 (above). E: errors copied from the Crear session or
  the final go through `_error_ajeno` (`cola.recortar(cola.sin_token(…), 500)`) and the start frame key has a random
  suffix. F: tariff 0.15 (cold single clicks 0,131–0,170, mean 0,142, plus Whisper), then 0.17 by the controller's ruling (the most expensive measured single click). G: `fotograma_s` snapped to a
  frame Claude saw (above). Not changed: the Kling prompt stays folded in a `<details>` (UX), as the auditor allowed.
- **Out of this change** (spec §11): the chip on the gallery card (PND-223), «Volver a analizar» for an old analysis
  (PND-224), hooks for image ads (PND-225), the hooks in Meta paused with their code (PND-226).

PND-187 (2026-10-09, decisión delegada): nuevas miniaturas de a_referente pasan cliente a guardar_en_r2 y usan clientes/<cliente>/referentes/tw_<ad_id>.jpg. Una fila con imagen ok no se vuelve a subir ni migra. anuncio_id ya es único por proyecto por 0030; test_lote7_tw_aislamiento guarda el mismo anuncio en dos proyectos con filas y claves distintas y comprueba biblioteca e imagen histórica.

## NVP (2026-10-09; en la pestaña Rendimiento desde la integración, 2026-10-10)

Pedido del cliente de HappyFlops (spec `2026-10-09-nvp-visitantes-nuevos` §4.1): el % de visitantes nuevos dice si un
anuncio es TOF, MOF o BOF. Siempre con el chip `cx.nvp(nuevos, visitantes)` (skill `ui`) y las SUMAS del periodo.
- «Resultados de tu tienda»: `resultados.tarjeta_nvp` arma el KPI «Visitantes nuevos (NVP)» (`r.nvp`; solo con fuente
  «tienda» o «anuncios»: con fuente "meta" o "mixta" de Rendimiento es None, porque los visitantes de la copia de Triple
  Whale describirían solo una parte del alcance; el NVP de las cuentas de Meta va en «Campañas y conjuntos», skill
  `meta-rendimiento`), una celda más de
  `.twr-tarjetas` que NO es pestaña (no se grafica, spec §5): las pestañas viven en `.twr-pestanas` (role="tablist",
  `display: contents`), así `role="tab"` sigue contando 6 o 7. `por_dia` trae `vis`/`vnu` (no van al JSON del JS). El
  cambio va en puntos («▲ 20 pts», tono siempre neutro) con la regla de las demás tarjetas (días completos contra los
  anteriores), y solo si los dos lados tienen `visitantes.MIN_VISITANTES`. Con fuente «anuncios» (un canal o sin datos
  de tienda) es lo que el Pixel atribuye a los anuncios de la evaluación (`panel._resultados` suma `ev["anuncios"]`, sin
  consulta nueva) y no compara. Sin visitantes (copia de antes de 0036) el chip dice «—»; el KPI no se esconde.
- «Ver como tabla» lleva la columna NVP y cada tarjeta de análisis una cifra más en `.tw-cifras`, las dos de `a.m`
  (`evaluacion.metricas` ya suma visitantes). En la galería única de Rendimiento, una tarjeta de Meta toma sus visitantes
  de esta copia por `ad_id` (una lectura por página) y sin Triple Whale no dice NVP (`sin_nvp`).
- `evaluacion.resumen_tienda` suma `visitantes`/`visitantes_nuevos`, así `panel.resumen_total_tienda` (el `tienda_tw`
  del Tablero en Experimentos) los trae. Pruebas: `tests/test_tw_nvp_pantallas.py`.
- La copia (spec §3): `tw_anuncio_dia`/`tw_tienda_dia` tienen `visitantes` y `visitantes_nuevos` (0036). El Pixel tiene
  TRES versiones (`consultas_pixel` = con visitantes, sin visitantes, mínima; `sync.NOMBRES_CONSULTA_PIXEL`): si una
  cuenta no conoce las columnas, baja a la de antes y solo falta el NVP. La tienda los trae aparte de
  `web_analytics_table` (`consultas_visitantes_tienda`; si falla, `fallos.visitantes` y la tienda se guarda igual).
  Cada tienda vuelve a traer 90 días una vez (`extra.backfill_visitantes`; cuándo queda, en el último punto). La regla vive solo en `triple_whale/visitantes.py`; `datos.visitantes_por(cliente, campo, ids, …)` es la
  lectura compartida de Meta y Experimentos (una consulta; ~55 ms por nivel con las 61 218 filas de happyflops).
- La IA (spec §4.5): «Cómo mejorarlo» recibe por anuncio (y por cada ganador del canal) `visitantes.texto_prompt(...)` y
  la regla `visitantes.REGLA_PROMPT`; el NVP no le cambió el tope ni el costo (los de «Ganchos y copy»: 20 000 y 0,17).
  La regla es una instrucción y no entra en `mejorar.datos_verificables` (sus cortes no son cifras del anuncio; al
  mezclar main en tw-ganchos el 2026-10-10). «Evaluar con IA» guarda los visitantes en
  la muestra (`analisis.CAMPOS_M`) y, desde PND-217 (2026-10-15, decisión de Daniel del 2026-10-13: «con precios por
  debajo de 1 USD no debe ser un estoper de nada»), también su PROMPT: `{regla_nvp}` (`visitantes.REGLA_PROMPT`) bajo
  las medianas, una línea `visitantes.texto_prompt(...)` por anuncio en `_bloque` y la regla de que «etapa» es la medida.
  Con eso Claude acertó la etapa en 10 de 10 (sin NVP, 4 de 10; `docs/superpowers/evals/2026-10-09-nvp-en-la-ia.md`). El
  tope de 16 000 ya cortaba la primera respuesta con 10 anuncios y con el NVP una corrida falló en las dos llamadas: va
  con `MAX_TOKENS` = 32 000 y `TIMEOUT_CLAUDE_S` = 900 (sin tope de tiempo explícito el SDK exige streaming), siempre
  `max_retries=0` como «Cómo mejorarlo» (un reintento del SDK podía cobrarse sin anotarse). El precio a la vista
  (`gastos.EVALUACION_TW_BASE_USD` 0,67 + `_POR_ANUNCIO_USD` 0,005, US$ 0,72 con 10) es el del peor caso: las dos
  llamadas agotando 32 000 de salida más su entrada; lo medido sale muy por debajo y se cobra lo real × margen. Cada
  anuncio que manda los fotogramas de su video (una pieza de Creatv: hasta 8 de 640 px en cada llamada) suma
  `EVALUACION_TW_POR_VIDEO_USD` 0,032 (revisión del gasto, 2026-10-15: con 10 así el peor caso llegaba a ≈ 1,00).
  `analisis.estimado(cliente, muestra, creatv=None)` (`n_con_fotogramas`) es la ÚNICA cuenta: el botón
  (`panel.contexto`), la ruta que cobra (`pedidos.pedir_evaluacion`) y los estimados de la tarea.
  Medición del cambio: `docs/superpowers/evals/2026-10-15-tw-evaluar-32000-nvp.md`.
- La copia de 90 días del NVP deja la marca `backfill_visitantes` solo si trajo visitantes en todo el rango, o tras
  `sync.MAX_INTENTOS_VISITANTES` (3) copias sin lograrlo (`intentos_visitantes`); un error de red o de límite en
  `web_analytics_table` deja la tienda sin su NVP (`fallos.visitantes`) pero no corta la copia (llave y tienda sí).
- El aviso «Triple Whale no aceptó la consulta de: …» (macro `copias` de `_tw_secciones.html`) y el texto de la tarea
  nombran las partes en palabras y en el idioma de quien mira (`triple_whale.PARTES_COPIA` + `nombres_partes`, global
  Jinja `tw_partes_copia`; PND-219, 2026-10-15: pintaba `pixel`, `tienda`… también en inglés). Una cuenta sin
  `web_analytics_table` falla en cada copia: `sync` deja `extra.aviso_visitantes` en la primera y desde ahí no pone
  `visitantes` en `ultimo_resumen.fallos` (el aviso sale una sola vez); la marca se va cuando una copia trae la tienda
  con sus visitantes (si la tienda misma falla, no cambia). Pruebas en `tests/test_triple_whale_sync.py`.

PND-149(2–6) (2026-10-09, decisión del lote 8): serie_tienda solo resta duplicados de anuncios entre tiendas que tienen fila de tienda ese día; gasto_duplicado conserva su diagnóstico de todos los anuncios. Al refrescar un experimento, se limpian las marcas antiguas/nuevas de países cuya tienda ya está conectada, también si ninguna pieza queda sin tienda. uk al final del dominio da GB. agregar guarda los ajustes del formulario si no hay tiendas (aunque exista la fila); con tiendas conserva los ajustes anteriores. reservar_aviso_sync toma UPDATE sin efecto antes de leer extra/cola y marca ids+creada_en aún vivos en syncs_terminadas: la última reserva el aviso una sola vez aunque ambos hilos sigan vivos hasta volver al worker. actualizar_extra toma el mismo candado antes de leer, y desde PND-222 (2026-10-15) también actualizar_extra_tienda y cambiar_ajustes (UPDATE sin efecto antes del SELECT; pruebas `test_pnd222_*` con `escritor_en_medio`). tests/test_lote8_tw.py cubre cifras, reconexión, dos finales simultáneos y el ciclo siguiente; sin red. Se dejan (1) países repetidos por tarjeta y (7) ajustes durante copia por decisión; (8) sigue para la primera copia real.

**«Cómo mejorarlo» de un anuncio de imagen fija, y su idioma (2026-10-13).** Pedido de Daniel: el análisis de un
estático salía en español en un proyecto en inglés y proponía «pasar el formato a video»; «Llevar a Crear» abría un
video sin la imagen. Ahora `mejorar.es_estatico(foto)` lo decide el creativo guardado (una pieza de Creatv por su tipo;
si no, sin `video_url`, sin `duracion_s` ni un tipo con «video», y con imagen; en happyflops el tipo `dynamic` es video
o imagen según lo que traiga), nunca lo que Claude miró (un video cuya descarga falló llega como miniatura y sigue siendo video).
Con imagen, `PROMPT` pide (`_VERSION["imagen"]`, `{escena_version}`/`{prompt_version}`/`{regla_version}`) un prompt en
inglés para EDITAR esa misma imagen: conservar producto, foto, composición, colores y formato, cambiar lo mínimo que
falla, y el texto que se verá en la imagen entre comillas, en el idioma del anuncio y con solo las ofertas de los
datos; `_version` guarda `tipo` ("video"/"imagen") y, en imagen, `cifras_sin_dato` de TODO su prompt
(`cifras_en_imagen`, sin los formatos «9:16» pero sí «3x2»: solo las comillas dejaban pasar comillas simples, ningunas
o un `12"`; no bloquea, avisa en el detalle y en Crear al llegar). El prompt de video es palabra por palabra el de antes.
`mejorar.analizar` cierra el mensaje, después de las imágenes, con `cierre_idioma(idioma, tipo)`: con la orden solo en
el system, las instrucciones en español arrastraban la respuesta (PND-218; «Evaluar con IA» sigue pendiente). En inglés
la orden va ESCRITA en inglés y nombra cada campo: la misma orden en español al final no movió nada (1 de 3 en inglés
antes y con ella; 4 de 4 escrita en inglés, `docs/superpowers/evals/2026-10-13-mejorar-estaticos-idioma.md`). «Llevar a Crear» (`rutas.analisis_crear`) de una versión de imagen
llama a `puente.imagen_a_bandeja`: copia la imagen del anuncio (`mejorar.imagen_del_anuncio`, solo de un host
permitido y, si es de R2, solo de `clientes/<cliente>/`) a R2 con `referentes.imagenes.copiar_a_r2` (guarda de SSRF
y validación por contenido), y solo si salió bien REEMPLAZA la bandeja con ella (origen `triple_whale`, título el
nombre del anuncio). Un anuncio de fuente Meta usa su copia de R2 tal cual (`referentes.imagenes.medir`), sin otra
copia ni su nombre: esa copia se borra al soltar la cuenta (promesa de /eliminar-datos); el prefill
(`prefill_crear(tipo="imagen")`) va con el modelo de imagen del proyecto y el formato más cercano al de la imagen
(`formato_mas_cercano`). Si no se puede copiar (o R2 está caído), aviso en palabras y nada cambia. Un análisis de antes (sin `version.tipo`) sigue
siendo de video. Pruebas: `tests/test_tw_mejorar.py` (estático, prompt, cierre, parseo),
`tests/test_tw_tarjetas_rutas.py` («Llevar a Crear» de una imagen) y `tests/test_tw_tarjetas_tarea.py`.

**Idioma y claves internas en los tres prompts que escriben un análisis (2026-10-13, PND-218 y PND-306).** «Cómo
mejorarlo», «Evaluar con IA» (`analisis.analizar`) y la «Evaluación con IA» de Meta (`meta_rendimiento.analisis`) cierran
el mensaje, después de las imágenes, con `analisis.cierre_idioma(idioma, campos, fijos, excepciones_en=,
excepciones_es=)`: en inglés la orden va escrita en inglés, nombra los campos que se escriben en el idioma del proyecto
y pide conservar tal cual los valores de lista cerrada (`etapa`, `consciencia`, `accion`, `anillo`, `mueve`, y
`consciencia`/`lead`/`fuente` del ángulo: `FIJOS_ANGULO`), porque traducidos no validan; en español, la orden de
siempre. Y los datos del prompt nunca llevan una clave interna: veredicto, tendencia, señales y anillos sin dato pasan
por `evaluacion.texto_clave`, que da su texto (`ETIQUETAS_VEREDICTO`, `TENDENCIAS`, `FORTALEZAS`, `PROBLEMAS`,
`VACIOS_ANILLO`) en el idioma activo, que en el worker es el del proyecto (`worker.ejecutar`); una clave desconocida sale
tal cual. **Lo verificable NO**: `mejorar.datos_verificables` sigue con la clave (`mejorar._clave`), porque los textos
traen palabras que `ofertas_sin_dato` toma por una oferta de los datos («En prueba», «No spend in the last 7 days») y
un gancho con «Prueba 7 días» inventado se generaría y se cobraría (revisión del gasto, 2026-10-13). Un script que arme estos prompts fuera del worker los arma dentro de `idiomas.en_idioma(idioma)`, nunca con una
app de Flask propia sin catálogo (la medición lo pagó: mandó «Se está cansando» en un prompt en inglés). Medido:
`docs/superpowers/evals/2026-10-13-evaluaciones-idioma-y-claves.md` (con lo que cuesta cada llamada, lo que paga el
cliente y lo que ganamos).

**Rendimiento: las métricas que faltaban (2026-10-13).** `triple_whale/destacados.py` arma, desde los anuncios ya
evaluados del panel, productos con gasto y ROAS (por la página de destino contra el Catálogo), los mejores para
iterar, los que mejor convierten (`metricas()["cv_sesion"]` = pedidos / sesiones; `resumen_cuenta` ahora suma
`sesiones`) y las mejores imágenes y videos (`datos.tipos_creativo(cliente)`: `{(canal, ad_id): tipo}` en una
consulta). Detalle y reglas en la skill `rendimiento`, «Las métricas que faltaban».

**«Evaluar con IA» cortada a mitad (PND-268, 2026-10-15).** `tw_evaluar` deja la fila «en_cola» mientras baja
miniaturas y saca fotogramas, y la pone en «analizando» justo antes de llamar a Claude (revisión del gasto: así
«analizando» quiere decir «la llamada empezó»). Si un reinicio del worker la mata ahí, `_evaluar_interrumpida` anota el
estimado (`analisis.estimado`) con `entregado=False`, la
referencia de la tarea (`tw_eval:<id>:t<tarea>`) y el detalle «estimado: se interrumpió durante el análisis»
(`anotar_estimado_cortado`, que también usa la de Meta). Si ya había un gasto con esa referencia (la tarea anota a
Claude ANTES de dejar la fila «lista»), no lo pisa: el worker ya revirtió el cobro de la cadena. Con la fila «en_cola»
(el respaldo sin saldo: no corrió) no anota nada. Y como la de Meta (E2-R7), una llamada sin respuesta (tope de tiempo,
conexión cortada) anota el estimado con «estimado: sin respuesta de Claude». Pruebas: `tests/test_triple_whale_analisis.py`
(`test_interrumpida_*`, `test_tarea_evaluar_si_claude_no_responde_*`) y `tests/test_tareas_meta_rendimiento.py`.

**«Cómo mejorarlo» y el lote comparan el precio visto (PND-236, 2026-10-15).** Motivo: la ruta recalculaba el costo al
recibir el clic y se lo pedía al libro, así que una pestaña abierta antes de un cambio de tarifa (0,10 → 0,17 entre el
2026-10-09 y el 10) cobraba la nueva sin mostrarla, y desde el 2026-10-12 happyflops cobra (pospago, margen 3). Ahora
cada formulario de la tarjeta (`_tw_galeria.html`: el principal y «Analizar con estos datos») manda `precio_visto` =
`a.precio_analisis.usd_precio` (el PRECIO, con el margen; sin él, el botón apagado) y el del lote, el total
`g.lote.precio.usd_precio`. La ruta (`pestana_rendimiento.rutas`) lo pasa a costo UNA vez con `gastos.costo_de_precio`.
`pedidos.pedir_analisis(..., *, costo_visto)` (obligatorio, por nombre) lo compara con `pedidos.coincide` (±0,005)
DESPUÉS de lo que no cobra (sin datos, en curso, fresco) y ANTES de `libro.exigir`: si no coincide, (False, «El precio
cambió (ahora: X). Revisa y vuelve a confirmar.») sin fila ni reserva, y por fetch la tarjeta vuelve con el precio
nuevo. El lote: `galeria.pedir_lote(..., *, costo_visto)` suma el costo de AHORA de las claves confirmadas que siguen en
su alcance (`galeria.costos_confirmados` → `pedidos.costos_de`, la misma cuenta que la tarjeta, dos lecturas por
fuente; las que no están no cuentan ni se cobran); si alguna no tiene precio o el total no es el visto, lanza
`galeria.PrecioCambiado` y la ruta avisa «El precio cambió desde que lo viste…» sin pedir nada. Después cada fuente
cobra con `pedidos.pedir_lote(..., *, costos_vistos)`, cada clave con el costo de esa suma: se cobra lo visto o menos
(una que otra pestaña ya analizó se salta), nunca más. Prender «Cobrar» también cambia el precio (el margen): un botón
pintado antes no cobra. Pruebas: `tests/test_tw_tarjetas_rutas.py` (`test_si_el_precio_cambio_*`,
`test_la_tarjeta_manda_el_precio_que_muestra`) y `tests/test_rendimiento_e2_pedidos.py`; las demás piden la tarjeta y
mandan su precio (`tests/test_rutas_triple_whale.py::precio_visto`, `con_total` para un lote armado a mano).
