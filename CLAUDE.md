# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Flask dashboard + Python pipeline that turns a text idea into a published social
video, for one or more "proyectos" (brand/character content channels). The whole
point of the design is that **every expensive step requires explicit human approval
before the next one runs** — nothing generates or publishes silently:

```
idea (texto)
  -> 5 prompts candidatos (Anthropic, gratis/barato)
  -> [aprobar 1 prompt] -> imagen candidata (Higgsfield soul/reference, ~1.5cr)
  -> [aprobar la imagen] -> video final (Higgsfield kling-2.1-pro, ~8cr)
  -> [aprobar el video] -> publicado en YouTube/Facebook/Instagram/TikTok
```

Rejecting at any stage stops the chain there — no credits spent on the next step.
Never skip a stage or auto-advance through the pipeline when writing code here;
that defeats the reason this exists.

## Running it

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill in HF_API_KEY_ID/SECRET, R2_*, ANTHROPIC_API_KEY, etc.
venv/bin/alembic upgrade head   # creates/updates data/creatv.db
python dashboard.py    # http://127.0.0.1:5050
venv/bin/python3 worker.py      # second terminal — processes the tarea queue
```

`ffmpeg` must be installed on the system (`brew install ffmpeg`) — used to extract a
still frame from uploaded video assets, since Higgsfield's APIs need a static image
reference, never a video.

Tests: `venv/bin/python3 -m pytest -q` (fast by default; tests marked `slow`
render real video with ffmpeg and take several seconds each — still included
in the default run, `-m "not slow"` skips them for a quick loop). There is
no linter configured; `python3 -m py_compile <file>.py` remains a quick
sanity check before committing.

The alternate CLI entry points (`run_batch.py`, `revisar.py`, `subir_personaje.py`)
predate the dashboard and still work, but `dashboard.py` is the primary interface —
prefer extending it over the CLI scripts unless asked for a batch/scriptable path.
See `SETUP.md` for the full human-facing setup walkthrough (registering apps with
Google/Meta/TikTok, Cloudflare R2, etc.).

## Architecture

**Multi-tenant via folders.** Each "proyecto" is a directory under `clientes/<nombre>/`
(the UI now says "Proyectos" but the folder name, route param, and Python variable
`cliente` were deliberately left as-is during that rename — only user-facing text
changed, to avoid touching the working state-machine/background-job logic). Layout:

```
clientes/<cliente>/
  personajes/          # character reference images/videos (+ .frame.jpg for videos)
  marca/                # brand reference images/videos, same convention
  marca.json            # guía de estilo (text) injected into every prompt generation
  prompts_pendientes.json  # ideas -> nested prompts, mid-pipeline state
  estado_videos.json    # generated videos awaiting/past final approval
  .env                   # per-client secrets (Meta page tokens), layered over root .env
  token_youtube.json, token_tiktok.json   # per-client OAuth tokens
```

Credentials layer in two tiers: the root `.env` (shared: Higgsfield, R2, Anthropic,
Meta app id/secret, TikTok client key/secret) loaded once at startup, then
`clientes/<cliente>/.env` loaded with `override=True` right before an action needs
per-client secrets (see `_cargar_entorno_cliente` in `dashboard.py`). Because this
mutates process-wide `os.environ` and publish now runs on a background thread,
`_ENV_LOCK` serializes that load-then-use section so two clients' publish jobs can't
clobber each other's credentials mid-flight.

**State machine modules** (`estado.py`, `prompts.py`, `marca.py`) are thin JSON
read/write wrappers, one file per client, no database. `prompts.py` nests prompts
under an `idea_id`; each prompt's `estado` field drives which template renders it
(`pendiente` -> `_prompt_row.html`, `imagen_pendiente` -> `_imagen_row.html`). When a
video finally generates, its entry is deleted from `prompts_pendientes.json` and
created fresh in `estado_videos.json` — the two files together are the full pipeline
state for a client. `creative_flow.py` and `ads.py` present the same read/write API
but now persist to `data/creatv.db` (see `db.py`, `migrations/`) instead of JSON;
`creative_flow_pendientes.json`/`ads.json` are kept only as a read-only backup,
and `migrar_json_a_db.py` (idempotent) is what originally imported them into the
database.

**Background jobs** (`trabajos.py`): this is an adapter over two execution paths.
The older Higgsfield pipeline (image gen, video gen, brand analysis, publish) still
goes through `trabajos.iniciar(job_id, fn, duracion_estimada)`, which runs the
function in-memory on a daemon thread. The migrated jobs (`flowplus_video`,
`flowplus_imagen`, `meta_publicar`, `meta_refrescar`, `swap_generar`, under
`tareas/`) go through `trabajos.encolar(...)`, which inserts a row into the `tarea`
table (`cola.py`, `data/creatv.db`) for the separate `worker.py` process (systemd
unit `deploy/creatv-worker.service`) to pick up and run. Either way the Flask route
returns almost instantly; the browser polls `/trabajo/<job_id>/estado` (JSON) —
the same endpoint for both paths — and renders a progress bar via the shared
`iniciarPolling()` JS in `base.html`, reloading the page on completion. `job_id` is
deterministic per (cliente, prompt_id/brief_id, acción) so a repeat click no-ops
instead of double-launching. Tasks that spend credits are queued with
`max_intentos=1` — they never auto-retry. A queued task stuck running for more than
30 minutes is either re-queued (if it still has attempts left) or marked `error`
(once `max_intentos` is exhausted). **`dashboard.py` runs with `use_reloader=False`
on purpose**: Flask's auto-reloader kills the whole process on file changes, which
would silently abort any in-flight background generation.

**Higgsfield API wrapper** (`higgsfield_client.py`): all calls follow launch ->
`poll_until_done(status_url)` -> extract-result, for both video (`kling-2.1-pro`,
`extract_video_url`) and image (`soul-reference`, `extract_image_url`) generation.
`estimate_video`/`estimate_image` hit Higgsfield's `/estimate/...` endpoints (free)
and are always called before showing a generate button's cost in the UI — when
adding a new generation path, estimate it too rather than generating blind.
`ENDPOINTS`/`IMAGE_ENDPOINTS` dicts are the only place model routes are registered.

**Storage** (`storage/r2_uploader.py`): every generated/uploaded binary (personaje
images/videos, brand references, candidate images, final videos) is pushed to
Cloudflare R2 and referenced by its public URL from then on — binaries are never
committed to git (`.gitignore` excludes `clientes/*/personajes/*`, `clientes/*/marca/*`,
`salidas/`, the `*.json` state files, all `.env`/token files).

**Publishing** (`publicador.py` + `uploaders/`): dispatches per-platform based on a
brief's `platforms` list. `uploaders/youtube_uploader.py` (google-api-python-client),
`uploaders/meta_uploader.py` (Graph API, covers both Facebook and Instagram),
`uploaders/tiktok_uploader.py` (Content Posting API). YouTube and TikTok need a one-time
OAuth authorization done locally (`auth/auth_youtube.py`, `auth/auth_tiktok.py` — each
opens a local browser + localhost callback server, so these cannot run on a
remote/deployed server; tokens must be generated locally and copied over). Meta is
different: **each proyecto brings its own Meta app** (app id, app secret, Facebook Login
for Business config id), registered from the dashboard (FlowMarketing › "Registra tu app de
Meta") into `clientes/<cliente>/meta_app.json` (git-ignored, 0600); only then does
"Conectar con Meta" (routes in `dashboard.py`, logic in `meta_conexion.py`) open that
app's login dialog, and the resulting tokens/ad account/Page live in
`clientes/<cliente>/meta.json` (also git-ignored, 0600). There is NO shared Meta app and
no `META_APP_ID`/`META_APP_SECRET` in the root `.env` — only `META_REDIRECT_URI`, the same
public callback URL every client registers in their own app. Never reintroduce a global
Meta credential: a client's data must only ever flow through that client's app. `meta_ads/`
receives them via `auth.configurar(...)` — the submodule never reads the environment.

**Prompt generation** (`generador_prompts.py`): calls Anthropic directly (not through
Higgsfield). `generar_prompts()` writes the 5 candidate prompts and folds in a
client's `marca.json` guía de estilo when present, so brand consistency doesn't have
to be repeated per idea. `analizar_marca()` uses Claude's vision input on uploaded
brand reference images to auto-write that guía de estilo.

**Sprints de contenido** (`sprints/` + `tareas/sprints.py`, spec
`docs/superpowers/specs/2026-09-16-sprints-design.md`): a monthly production plan
as a matrix persona × producto × temporada. Tables `persona`, `temporada`,
`sprint`, `campana` (UNIQUE `uq_campana_combinacion` on sprint + persona +
catalogo_id + temporada), `referencia` (intención tags + descripción; a reference
without descripción is `borrador` and does not count toward progress),
`campana_pieza` (Parte 2) and `sprint_evento`. `sprints/datos.py` is the only
writer; `sprints/estado.py::recalcular` re-derives campaign/sprint states after
every event (states are stored but never trusted blindly); `sprints/progreso.py`
is pure. Routes live in the Blueprint `sprints/rutas.py`
(`/cliente/<cliente>/sprints/...`), registered from `dashboard.py`, which also
adds `sprints_rutas.contexto(cliente)` to the project page. Uploading a
reference enqueues `sprint_analizar_referencia` (Claude vision, cents); "Sugerir
personas" enqueues `sprint_sugerir_personas`; a pasted link goes through
`sprint_referencia_link` (yt-dlp via `referencias_link.descargar`). Parte 2 (producción): `sprints/ideas.py` asks Claude for ideas per campaign
(prompt maestro: persona + producto + temporada + reference analyses + brand
guide + banco de prompts) stored as `campana_pieza` rows; "Generar lote"
(`sprints/produccion.py`) shows the estimated cost first, then creates one
Crear session per approved idea (`creative_flow.crear(..., extra_sprint=)`,
prompt via `flowplus_prompt.armar(..., contexto=)`) and enqueues it through
`flowplus_lanzar.lanzar(..., prioridad=3)` — `tarea.prioridad` makes single
pieces from Crear (5) jump ahead of batches. `campana_pieza.cf_id` joins
`pieza.legado_id`, so progress and states come from the real sessions. The
worker periodic `sprint_qa_pendientes` (5 min) queues `sprint_qa_pieza`
(`sprints/qa.py`: Claude vision + ffprobe → `campana_pieza.qa`, never
generates) and emails when a batch finishes. `sprints/revision.py` approves or
rejects (a rejected piece leaves `estado_videos.json`), closes and reopens the
sprint; `sprints/entrega.py` lists approved links and builds the zip
(`sprint_empaquetar`). Retries and regenerations always go through the cost
gate and `max_intentos=1`.

**Crear (FlowPlus)** (`cf_crear_video` -> sesión en `prompt_pendiente` -> worker
`tareas/director.py` (`director.compilar`: Claude escribe los planos por familia de
modelo, valida y compone A/B con `flowplus_prompt.armar(..., planos=)`; fallback al
prompt determinista, nunca bloquea) -> `prompt_listo` (la persona edita con
`cf_guardar_prompt` o rearma con `cf_rearmar`) -> `cf_generar_video` (A, o A+B vía
`creative_flow.duplicar(prompt_relleno=, variante="B")`) -> `flowplus_lanzar.lanzar`
-> worker `tareas/flowplus.py` -> `providers/flowplus_modelos.py`, todo vía WaveSpeed).
Las referencias se nombran `Image N` / `Video N` (`flowplus_prompt.asignar_tokens`,
por modelo: Wan recibe los videos aparte). Spec:
`docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (Etapa 1 hecha;
presets de cámara y plantillas de anuncio son las Etapas 2 y 3). Los lotes de
Sprints encolan el director con `auto_lanzar` (el costo ya se aprobó). `calidad`
`borrador` = Wan a 480p. Duración por defecto 8 s (`preferencias_flowplus`). `VIDEO` /
`IMAGEN` there are the only model registry (path, price, limits, `audio_nativo`,
`familia`, `min_duracion`/`max_duracion`, `formatos`). Crear makes ONE piece per click (the enfoque is
automatic: `producto`, or `persona` when a catalog personaje is among the references),
offers 5–30 s (default 8 s) and the formats each model admits (verified on WaveSpeed 2026-09-18: Wan 3.0
2–30 s and 9:16/16:9/1:1/4:3/3:4; Kling O3 Pro 3–15 s and 9:16/16:9/1:1; Seedance 2.5 4–30 s
and follows the reference image, `aspect_ratio` None; Seedream V5 Pro takes `aspect_ratio`
for images). `ajustar_duracion`/`ajustar_formato` run in the route AND again in the worker's
`_preparar` (last barrier before spending), so nothing outside a model's range is ever
requested. Videos
ALWAYS ask for the model's native scene sound (`generar_video(..., con_sonido=True)`: Wan 3.0
`enable_audio`, Kling O3 Pro `sound` — +0.028 $/s, already inside `estimate_video` and the
`usd_por_segundo_efectivo` the templates show —, Seedance 2.5 `generate_audio`), and the
prompt carries a `SONIDO:` line ("Sin diálogo hablado ni música de fondo" keeps Kling's
Chinese/English voices out; the Spanish voice comes from final edition). Images never get
that line. The session carries `con_sonido` (the "Sonido de la escena" check, default from
`proyectos.preferencias_sonido`), `sonido_texto` (the described sound, "Sugerir" asks
Claude through `final_edition/sonido.py`) and `musica_estilo` ("" = none). After the
download the worker's **Mezclando sonido** step (`ETAPAS_CREATIVE_FLOW`, 4 stages) probes
the audio track, mixes the chosen music underneath with `final_edition/mezcla.py`
(`mezclar_musica`: video copied, `loudnorm`) and stores `pieza.capas`
(`sonido {proveedor, estado: ok|ausente|desconocido|omitida}`, `musica`, `mezcla`),
`video_url` (mixed: what is seen, published and delivered) and `extra.video_url_crudo` /
`video_local_crudo` (native sound only: the source of final edition). Music failure is
degradable (the paid video is never lost) — it only reports, never regenerates. Spec:
`docs/superpowers/specs/2026-09-16-final-edition-estudio-design.md` S1 (done except
`proveedor_v2a` and style previews, which belong to S3/S5).

**Final edition** (`final_edition/`): a second pipeline that takes an already-approved
CreativeFlowPlus video (`creative_flow.py`) and turns it into a localized, narrated,
subtitled, scored final ad per idioma/país (`fe_preparar` writes one guion base with
Anthropic; `fe_producir` queues one `final_producir` task per destino ticked, each
worth its own approval). `final_edition/__init__.py` orchestrates the layers in order
— `guion` (Anthropic: base guion, then localize per destino) -> `cortes` (ffmpeg: cut
detection on the source clip) -> sonido (the clon's native track, `ausente` when it has
none) -> `voz` (fal/ElevenLabs TTS per block, degradable
except a failure on the FIRST block, which is fatal and never reaches música) ->
`musica` (fal/Stable Audio, degradable, cached) -> `texto` (Pillow: overlay PNGs for
hook/subtitles/price badge/CTA) -> `render` (ffmpeg: one filtergraph, `MAX_OVERLAYS_TOTAL`
caps the overlay count so a long guion can't OOM the box). Since S2 the clon's native sound is a layer: `producir` reads the RAW clon
(`video_local_crudo`/`video_url_crudo`, never the music-mixed file), `render` trims `[0:a]`
with the very same segment `inicio`/`fin` as the video (sync by construction) and
`final_edition/mezcla.py::filtro_mezcla` mixes sound + voice + music (voice ducks sound at
ratio 4 and music at ratio 8, presets `equilibrada` / `voz_protagonista` /
`ambiente_protagonista`, explicit `volumenes` win, `loudnorm=I=-14:TP=-1.5:LRA=11` last), AAC forced to 48 kHz on output (`-ar 48000`: `loudnorm` emits 192 kHz).
Options `con_sonido`, `sonido` (`nativo|ninguno`), `mezcla`, `volumenes`; `capas.sonido`
is `ok | omitida | ausente` (a mute clon never degrades the piece). Stems and "Remezclar"
are S4, video→audio fallback is S3. State lives on
`creative_flow.crear_final`/`actualizar_final` (`data/creatv.db`), one row per
idioma/país keyed `<cf_id>__<idioma>_<pais>`; re-producing a destino that already has
a final keeps its `url_video`/`url_miniatura` until the new attempt succeeds, so a
failed retry never leaves the client without a video. Every price is per-destino
(`opciones["precios"]`, one raw number per país — never converted between currencies)
so a badge/voice-over price is either the number typed for that specific country or
absent, never another country's number reformatted. All fal.ai calls go through
`providers/fal_audio.py` (ElevenLabs `multilingual-v2` for TTS, `fal-ai/whisper` for
word-level timestamps, Stable Audio for music); the premade voice list there is
individually verified against fal (see the module docstring) rather than assumed from
ElevenLabs' own catalog. Fonts are checked into `static/fonts/`; generated music
tracks are cached in `data/musica/` and mirrored to R2. Worker tasks live in
`tareas/final_edition.py`; the dashboard routes are `fe_preparar`, `fe_guardar_guion`,
`fe_producir`, `fe_descartar`.

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
launch (resumable). UI: sidebar tab "Experimentos" (`_tab_experimentos.html`, tree
experiment -> country -> piece) and "Meter en experimento" in Crear's detail modal.

**Decisor, escalera y modos** (`decisor.py`, `modos.py`, `propuestas.py`, `acciones.py`,
`derivaciones.py`, `notificaciones.py`): the part of the loop that closes on its own.
`decisor.decidir(snapshots, reglas, contexto)` is a pure function — traffic gate first
(impressions/spend/hours evidence, then CPC/CTR/ThruPlay thresholds; zero impressions is
never a loser), sales gate second only with attribution (ROAS/CPA after
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

**Publicación orgánica** (`organico.py`, `tareas/organico.py`, `_organico_publicar.html`):
a winning piece (or any final) goes out as organic content on Instagram Reels, Facebook
Page, TikTok and YouTube Shorts, reusing `publicador._publicar_una` + `uploaders/`. One
`publicacion` row per (pieza, plataforma), `en_cola -> publicando -> publicada | error`,
and the partial unique index `uq_publicacion_viva` guarantees "never twice" while a row is
alive. Publishing is public and irreversible, so nothing here decides *when*: only the
`organico_publicar` task (`max_intentos=1`, queued by a click in `org_publicar` /
`org_reintentar`, or by `acciones.ejecutar("publicar_organico")` in modo `auto` / on
approving the proposal) touches a platform; `redactar` (Claude captions with a
deterministic fallback, always normalized server-side by `organico.normalizar_captions`)
is read-only. Once an uploader returns an id, `id_externo` is persisted FIRST in its own
transaction; a later bookkeeping failure leaves the row `publicando` with the id (never
`error`, which would enable a second upload) and `reconciliar_subidas` (run by the task
before each batch) closes it later. TikTok is asynchronous: `check_status` decides
`publicada` / `error` (FAILED, id cleared, retryable) / still `publicando`. Rows with an
`id_externo` are never retried. Tokens never reach `error`/eventos (`cola.sin_token`).

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
UI: there is NO Productos tab — products live in **Catálogo › Productos** (`_tab_catalogo.html` +
`_catalogo_lista.html`): every activo of categoría `producto` has a `producto` row (fuente
`manual`, `fuente_id = activo id`, created on the fly by `tiendas.asegurar_manual`) that holds
precio/moneda/url_compra/en_prueba/prioridad; importing (CSV/URL) is the "Traer productos de…"
details, imported products without photos sit in "Importados sin fotos" until `prod_fotos_subir`
or `prod_vincular` creates their activo. Store connections and the Pixel check are in
Configuración, whose first section "Puesta a punto" (`dashboard._estado_llaves`) lists every
paid key (Anthropic, fal, Higgsfield, R2, Meta, SMTP, MELI) with configured/missing badges —
computed from `bool(os.environ.get(...))` only, values are never rendered.

There is also NO Campañas tab any more: `_tab_ads.html` is gone, `nueva_campana`/`publicar_ad`
are no-ops that flash and redirect, and the legacy "Anuncios sueltos" (Forja's ads) render
read-only inside Experimentos (`_anuncios_sueltos.html`: KPIs, pausar/activar, actualizar).
The decisor's default rules (`cfg_reglas`) are edited in Experimentos ("Reglas del motor"),
not in Configuración.

**Tablero y OUTCOME_SALES** (`tablero.py`): the first tab. Every figure is a **delta of
cumulative snapshots** (`metrica_snapshot` stores Meta's lifetime totals per ad, so a period
is `valor_en(hasta) − valor_en(desde)`, negatives truncated to 0) grouped by account
currency; revenue only counts snapshots attributed by Meta Pixel or store. `tablero.contexto`
loads each piece's snapshots once (bounded by `experimentos.snapshots(ep_id, desde=)`, which
also returns the last row before the window) and derives the month tiles, the 30-day
series, the top-5 winners and the alerts; `dashboard._contexto_tablero` caches it 60 s per
client keyed by the latest snapshot id and the proposal count, and degrades part by part
(never leaking exception text). The chart is inline SVG on a single axis (spend bars,
revenue line, validated colorblind-safe pair). `csv_mes` escapes formula-leading cells.
When the suggested attribution is `pixel`, `experimentos.objetivo_sugerido` is
`OUTCOME_SALES`; `lanzador.lanzar` then re-checks the Pixel before touching Meta and sends
`promoted_object={pixel_id, PURCHASE}` on every adset (`meta_ads/adset.py` refuses SALES
without it). The objective is fixed at creation — Meta doesn't allow changing it.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
