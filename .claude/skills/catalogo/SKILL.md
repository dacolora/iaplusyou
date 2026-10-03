---
name: catalogo
description: "Catálogo ecommerce: la tabla producto, productos por colores, conectores de tiendas (Shopify sin llaves, Shopify Admin, WooCommerce, Mercado Libre, CSV/Excel, URL), importador, atribución de pedidos y la galería Catálogo › Productos con su ficha. Cargar antes de tocar tiendas.py, conectores/, importador.py, atribucion.py, catalogo_productos.py, catalogo_vista.py o los _catalogo_*.html."
---

# Catálogo ecommerce, colores y conectores de tiendas

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Catálogo ecommerce y conectores** (`tiendas.py`, `conectores/`, `importador.py`,
`atribucion.py`, `cifrado.py`): the `producto` table is the normalized catalog (unique per
`(cliente, fuente, fuente_id)`; sync = upsert, disappearing products are archived, never
deleted; a manual archive — `extra.archivado_por="manual"` — survives syncs). Every source
implements one contract in `conectores/base.py` (`listar_productos()`, `pedidos_desde(fecha)`,
`probar()`, normalized dict shapes): `csv_excel` and `url` (JSON-LD/OG scraper with SSRF
guards: private hosts refused, redirects re-validated) for files/links, and `shopify`
(Admin GraphQL 2025-07, query cost kept under the 1 000-point cap, THROTTLED handled),
`woo` (REST v3, `_wc_order_attribution_utm_content`) and `meli` (OAuth, single-use refresh
token persisted after every refresh, never retried) for stores — registered by `tipo` and
loaded lazily by `conectores.por_tipo`. Store credentials live Fernet-encrypted in
`tienda.credenciales` with a key derived from `FLASK_SECRET_KEY` (rotating it means
reconnecting every store); they never reach logs, flashes or eventos. `importador` turns
a normalized product into an activo of the Crear catalog (`catalogo_productos`, folder
`clientes/<c>/productos/<id>/`, ≤ 6 photos ≤ 8 MB, one Claude call for the fidelity rule
that is never overwritten once edited; no photo → no activo), capped per run
(`max_activos`) with a self-scheduled continuation task so a big catalog never starves the
single-threaded worker; all `productos.json` writes go through
`catalogo_productos.modificar_meta` (flock) because Flask and the worker both write it.
Worker periodics: `tienda_sync_productos_todas` (6 h) and `tienda_sync_pedidos_todas` (2 h,
only for clients with a `corriendo` experiment attributed by store). Orders carry
`utm_content = experimento_pieza.id` (set by `lanzador.url_destino`; legacy `pieza.id`
still resolves) and `atribucion.resolver_pendientes` links them; when an experiment's
`atribucion` is `tienda`, `lanzador.refrescar` overrides purchases/revenue/CPA from the
store (ROAS forced to 0 when order and account currencies differ, with one evento).
`meta_conexion.estado_pixel` (cached 10 min, computed only by the Configuración button —
never on page load) feeds `experimentos.atribucion_sugerida`: pixel > tienda > ninguna.
Since 2026-09-30 (spec `docs/superpowers/specs/2026-09-28-catalogo-por-colores-design.md`, ADR 0005) a **product has
colors**. On disk `productos.json` keeps
`variantes: {color_id: {nombre, descripcion, fuente_id, url_compra, disponible}}` (store order) and each color
is a subfolder `productos/<pid>/<color_id>/` with its own reference photos (the root holds the «fotos de ambiente»,
`fotos_generales`, when there are colors, or the reference photos of a plain product); a `color_id` is
`id_desde_nombre` of the color name minus a «<producto> — » prefix (`_id_color_desde_nombre`).
`.gitignore` ignores new catalog files (`clientes/*/productos/`, `personajes_catalogo/`, `entornos/` and their
`.json` metas), but happyflops' old `productos.json` and photos are still tracked (untracking them would delete them
on the VPS at the next `git pull`): never `git checkout .`/`reset --hard`/`stash` on the VPS without backing up
`clientes/*/productos*` first. `catalogo_productos.listar()` still yields one entry per color plus `producto_id/variante/nombre_producto`; its id
`pid/color` is the value of Crear's checkbox and of `fp_prefill` (as `<cat>:<id>`), `campana.catalogo_id` and a
swap's `producto_id`, while Crear's `productos_ids` keeps the visible name (which is why `claves_de()` also returns
names); `listar_productos()` yields one entry per product with `colores` and `fotos_generales` (it is also what
Sprints' «Sugerir personas» prompt and Nicho's product picker list, ids = pid); `encontrar(pid)`
falls back to the first color with photos; `producto_base()` strips the color (every `tiendas.por_activo(...)`
lookup by activo id goes through it); `claves_de()`/`claves_de_producto()` give every id and name a product can be
referred by (doctrina pedidos, usos, experiment counts, the Tablero alert «en prueba sin experimento»); `carpeta_de`
refuses any id that resolves to the category folder itself («.», «», «x/..»). ONE `producto` row per product
(`activo_catalogo_id = pid`; a hand-made product's `manual` row, `fuente_id = pid`, is created on the fly by
`tiendas.asegurar_manual`, never for an id with «/»); data migration 0025 (`downgrade` a no-op) folded the old
per-color rows into the product's (empty ones deleted, non-empty duplicates archived as manual,
`extra.archivado_por="manual"` — they keep their data in the DB but the gallery does NOT show them, not even under
«Archivados», while the product has its live row: per activo the live row wins). `conectores/shopify_publico.py` (tipo `shopify_publico`, fuente `shopify`, only a
`dominio`) reads a store's public `/meta.json` + `/products.json`: the color option (`OPCIONES_COLOR`, or the first
option whose values have distinct featured images), one variante per color (`normalizar_variante`, in
`extra.variantes`) with its studio photo(s) (`width=1000`), unassigned images as fotos de ambiente
(`fotos_generales`), price = mode of the variants (`extra.precios` when they differ), currency from meta.json,
services skipped (`PALABRAS_SERVICIO`); rows are saved under the connector's `fuente` (`Conector.fuente`, None =
`tipo`; `tareas.tiendas` uses it). The public store is THE catalog source (ruling final-5, 2026-09-30): it and the
Admin-API `shopify` can both be connected (neither disconnects nor refuses the other), and while the project has a
`shopify_publico` the Admin API's `tienda_sync_productos` touches no product (no import, no archive; only
`ultima_sync_productos`, `tareas.tiendas.catalogo_desde_tienda_publica`) — the Admin API only adds orders and
attribution (its connector brings no colors and would freeze them; with the same `fuente` each sync would archive
what only the other sees; domains are never compared, the API connects with the `.myshopify.com` one). A project
with only the Admin API keeps syncing products from it, without colors. `desconectar(..., archivar=True)` archives
by the connector's `fuente`, not the store's `tipo`, and the `tienda_desconectar` route passes `archivar=False` when
another store of the project with the same `fuente` remains. `importador.vincular_activo` creates/refreshes colors
(`_colocar_colores`: new colors always download, existing ones only with `forzar_fotos` or when empty, colors gone
from the store become `disponible=False`; an existing color is matched by `fuente_id` first — Shopify's is the id of
the color's FIRST variant, which changes when a size is deleted or reordered — and otherwise adopted by name (stored
name first, then the derived id) only when it has no `fuente_id` or its `fuente_id` no longer comes from the store,
`_color_existente`, so two store variants whose names normalize alike still get `-2`); the root photos of an activo
ALREADY linked to the store are store photos and never become a color (`agregar_color(..., conservar_raiz=True)`:
they stay as fotos de ambiente) — only adopting a hand-made folder converts them (`convertir_actual`); it pays the
regla once per product and never leaves an activo without photos. UI: there is NO Productos tab — products live in
**Catálogo › Productos** (`_tab_catalogo.html`), a gallery fetched from `catalogo_grid` (`_catalogo_grid.html` +
`_catalogo_tarjeta.html`, 60 cards per «Ver más»; `catalogo_vista.py` is the pure filter/sort/paginate/usos layer;
filters live in the hash `#catalogo?cat=&filtro=&q=&orden=`) with a side-panel ficha fetched from `catalogo_ficha`
(`_catalogo_ficha.html`, `#catalogo?ficha=<cat>:<pid>`; colors strip, per-color photos, lifestyle photos with
«Asignar a color», datos + comercial fields, doctrina, usos, «Crear con este producto» →
`fp_prefill.productos_catalogo` (with `cliente`: `_prefill_para` uses it once, only in that project), «Crear
experimento», Eliminar) that closes when the hash leaves `#catalogo` (hashchange or a sidebar click) — but with an
unsaved edit (`data-sucio`) it is only hidden, content kept, and comes back when Catálogo is active again;
Escape/backdrop/✕ (and opening another ficha) ask before discarding unsaved edits, and Escape with the delete modal
open closes only the modal. «Archivar» in the ficha's footer (`catalogo_archivar`, 2026-10-01, for happyflops' old
hand-made products) hides the WHOLE product without deleting anything: `tiendas.archivar_activo` turns every live or
sync-archived row of that activo into a manual archive marked `extra.archivado_con_producto` (an `EXTRA_INTERNO` key,
so the sync keeps it archived), and «Desarchivar» (the ficha's notice) restores only those — never a row archived by
hand for another reason, like 0025's duplicates, which would change which row wins; with none, it restores the row the
gallery shows. `tiendas.activos_archivados` (products whose rows are ALL archived, one query) is what the gallery's
«Archivados» shows and what `catalogo_productos.sin_archivados(entradas, archivados, conservar)` drops from every
product picker — Crear and Cambiar producto (`ver_cliente`, also the tab's count), the Sprints panel and new-campaign
form, Nicho, Recrear, Flow Plus (`_catalogo_para_elegir`) and the «Sugerir personas» prompt — except what is already
chosen (the Crear prefill, the campaign's, the study's or the requested product, the version's references), so no
selection is ever lost silently. Lookups (`encontrar`, `producto_base`, usos, history) still see archived products.
Grid and ficha read Crear sessions and experiments once per request:
`_experimentos_por_activo`, `_productos_tienda_contexto` and `_usos_por_producto` take them preloaded
(`experimentos_exp`, `sesiones_cf`, `por_clave`). Every catalog POST returns to `#catalogo`, to that ficha when it
still exists (`_volver_catalogo`/`_volver_fila`), except by design «Crear con este producto» (`#creativeflowplus`)
and «Crear experimento» (`#experimentos`); only the two GET photo routes (`imagen_producto`,
`imagen_producto_archivo`) take `<path:producto_id>` (ids with «/»), the POST photo routes take `<producto_id>` plus
a `variante` form field (uploading to a `variante` that is not a color of the meta is refused, nothing written);
`imagen_producto_archivo` serves a file name only if it is one of that folder's images (no `secure_filename`:
happyflops' tracked «HOriginal - Beige_5.png» has spaces); controls that never hold an unsaved edit (the orden select, the one-action selects «Asignar
a color» and the color of «Crear con») carry `data-busqueda` so the «Sin guardar» guard ignores them. «Traer de mi
tienda» (`_catalogo_importar.html`, `details#cat-traer`: Shopify sin llaves first, then CSV/Excel and URL) connects
a `shopify_publico` store from the catalog (`tienda_conectar`/`tienda_sync` with `volver=catalogo`; once connected
it shows the last sync as `YYYY-MM-DD HH:MM` and, when the store is `rota`, its error; its sync banner
is `id="cat-sync-<job>"`, because Configuración paints its own `trabajo-<job>` bar for the same job); Configuración
› Conexiones offers «Shopify (sin llaves)» first (`conectores.TIPOS_CONECTABLES`). Crear's picker
(`_selector_productos.html`) groups colors under their product and the Sprints panel select
(`_sprint_panel_armar.html`) uses `<optgroup>`, both through the Jinja filter
`catalogo_productos.agrupar_por_producto` (registered in `dashboard.py`; not `groupby`, which sorts first and breaks
on entries without `producto_id`). Rows without an activo (imported without photos) are cards in the same gallery
(«Sin fotos» filter) with Subir fotos / Crear activo / Archivar. Configuración (`_tab_settings.html`) shows one
apartado at a time (pills, last one remembered, `window.irAConfig(id)` opens the apartado
holding `id`): Puesta a punto (admin only), Conexiones (store, Pixel, organic channels — since
2026-09-28 the Meta connection card is NOT here: it lives only in Experimentos,
`_meta_conectar.html`; the Triple Whale form left the same day for the Triple Whale tab,
`_triple_whale_conectar.html`), Marca, Generación, Cuenta y avisos,
Gasto. The key cards (`_llave_tarjeta.html`;
the list and its state live in `llaves.py`: `llaves.SERVICIOS` / `llaves.estado`, aliased in `dashboard.py` as
`SERVICIOS_LLAVES` / `_estado_llaves`) list every
paid key (Anthropic, WaveSpeed, fal, Higgsfield — optional, only the old «Nueva idea» flow —, R2, SMTP, MELI,
Nicho and Referentes sources) with configured/missing badges —
computed from `bool(os.environ.get(...))` only, values are never rendered (`alertas.py` reads the same `llaves.estado()`: every card not configured is also an admin-only alert `llave:<id>` — `info` if the card is `opcional` —, skill `alertas`). Since 2026-09-20 that
full list is admin-only: `dashboard._llaves_visibles` gives a cliente just the `por_proyecto`
cards (Meta), and the template hides `.env` variables, the server note and the "Cómo
conseguirla" steps for them (the client sees `cliente_hace`: billing + the connect block).

**Pedidos sin atribuir (2026-10-02, PND-015):** pasado `DIAS_RESOLVER_PEDIDOS`, se conservan sin reintento y `tiendas.pedidos_vencidos_sin_resolver` los cuenta por proyecto. `tablero.alertas` avisa en Alertas que no entran en las ventas atribuidas; no cambia el criterio de atribución ni convierte importes.

PND-015 (revisión 2026-10-02): el aviso de pedidos vencidos cuenta solo UTM numéricos según atribucion._numero que correspondan a experimento_pieza.id o pieza.id del mismo cliente; un UTM externo no genera aviso.
