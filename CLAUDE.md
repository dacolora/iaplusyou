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
`clientes/<cliente>/meta.json` (also git-ignored, 0600). There is no Meta credential in the
root `.env` — only `META_REDIRECT_URI`, the public callback URL every client registers in
their own app. That is the **propia** mode (ADR 0001). Since 2026-09-20 there is a second,
admin-only mode per project, **agencia** (ADR 0002, `meta_agencia.py`): the admin connects
Creatv's Business Manager ONCE with a system-user token (Fernet-encrypted in `kv` under
`meta_agencia`, never in any `meta.json`, template, flash or log) and assigns each project an
ad account + Page from the assets that Business owns or was granted as a partner
(`/admin/meta`). An agencia project's `meta.json` has `modo: "agencia"`, the assigned ids,
the resolved `page_access_token` and NO user token — `meta_conexion.cargar()` injects the
agency token on read, so `credenciales_ads`, `estado`, `estado_pixel`, `lanzador`,
`meta_uploader` and everything else are mode-agnostic. `guardar`/`borrar`/`url_dialogo`/
`cambiar_code_por_token`/`guardar_app` raise `ModoAgenciaError` for agencia projects (only
`meta_agencia.asignar/desasignar` may write them); the previous propia data is kept in
`propia_respaldo` so "Volver a propia" restores it. The rule: an agency credential only ever
operates assets the client granted in Business Manager or the agency owns; a client's own
data still never flows through another client's app. `meta_ads/` receives credentials via
`auth.configurar(...)` — the submodule never reads the environment.
Since 2026-09-20 (ADR 0003) **the client chooses the form** in Configuración › Meta:
`proyectos.meta_forma` (`agencia | propia | None`, in `proyecto.json`) is the client's intention,
`meta_conexion.modo` (meta.json) is the real state (with a connection or a registered app and no
form, the form is inferred). «Que Creatv lo gestione» is self-service: the client shares assets
with Creatv's Business ID, pastes their portfolio id, the routes `meta_agencia_buscar/conectar`
show ONLY assets whose owner is that portfolio (`meta_agencia.activos_de_portafolio`:
`client_ad_accounts`/`client_pages` with `business{id}`) and
`asignar(..., asignado_por="cliente:<u>", portafolio_id=)` connects — one ad account per project,
enforced there. Fallback «Avisar a Creatv» stores a `kv` row `meta_solicitud:<cliente>`
(`meta_agencia.solicitar/solicitudes`) shown in `/admin/meta`; `notificaciones.avisar_admin` mails
verified admins. The client may switch forms (including leaving agencia via `meta_agencia_salir`)
only with nothing running (`_bloqueo_cambio_forma`: no experiment in `ESTADOS_VIVOS`, no organic
publication `en_cola`/`publicando`). Creatv's one-time Meta work is in
`docs/meta/puesta-en-marcha-agencia.md`; the glossary for these terms (forma, modo, agencia,
activo, portafolio, asignación, solicitud) is `CONTEXT.md`.

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
`sprint_referencia_link` (yt-dlp via `referencias_link.descargar`). A reference can also come straight from the referentes library (`origen='biblioteca'`, pre-analyzed, no `sprint_analizar_referencia`): `sprints.datos.agregar_referencia_biblioteca` (deduped per campaign), the Referentes grid's `?campana=` selection mode, `referentes/sugerir.py` (deterministic + optional Claude pick, task `referentes_sugerir_ia`, tariff `sugerir_ia`), and 'Usar en sprint' from a referente's ficha. Parte 2 (producción): `sprints/ideas.py` asks Claude for ideas per campaign
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

**Nicho y avatares** (`nicho/` + `tareas/nicho.py`, spec
`docs/superpowers/specs/2026-09-18-nicho-avatares-design.md`): personas nacidas de
comentarios reales. Tablas `estudio`, `comentario` (única por estudio + fuente +
fuente_id, nunca guarda el autor) y `avatar` (núcleos por deseo con `padre_id`
NULL; sub-avatares colgando de ellos con los campos de las dos plantillas del
cliente: identidad, soluciones previas, situaciones, conciencia, encaje del
producto, evidencia). `nicho/datos.py` es el único escritor; `recalcular` deriva
`armando | generando | revisando`. Las fuentes entran por `nicho/fuentes/base.py`
(`normalizar_comentario`, `ErrorFuente.usuario`) y el registro perezoso
`nicho.fuentes.por_tipo`; `texto` y `csv` corren en la ruta; `reddit`, `youtube`
y `apify` corren en el worker con la tarea `nicho_recolectar`
(`tareas/nicho.py`: lotes de 100, `aviso` de entrega parcial, lo leído nunca se
pierde; Apify `max_intentos=1` con el estimado por resultado a la vista y su
gasto como tipo `recoleccion`; Reddit/YouTube `max_intentos=2`). Reddit usa el
token de solo lectura (`client_credentials`, 100 llamadas/min, solo uso no
comercial); YouTube una llave simple (`search.list` tiene cupo de 100
llamadas/día, una por recolección); Apify solo actores con precio por resultado
(`nicho/fuentes/apify_actores.py`) y el token siempre en cabecera. Las llaves
(`REDDIT_*`, `YOUTUBE_API_KEY`, `APIFY_TOKEN`) viven en el `.env` raíz y se
muestran en Puesta a punto; sin ellas la tarjeta de esa fuente queda apagada.
`nicho/avatares.py` hace dos pasadas con Claude (`generador_prompts.MODEL`):
núcleos, luego sub-avatares por núcleo; cada cita se verifica literal contra el
comentario (`verificar_evidencia`) y la que no aparece se descarta — un
sub-avatar sin citas queda `sin_evidencia`, no se borra. `estimar_costo` (tokens ×
`PRECIOS_USD_POR_MILLON`) se muestra en el botón antes de encolar
`nicho_generar_avatares` (`max_intentos=1`; el gasto real va a `gastos` como tipo
`avatares`). Regenerar borra `propuesto`/`descartado` y conserva los `aprobado`.
Aprobar un sub-avatar crea (o actualiza) una `persona` con origen `investigada`
(`persona_desde_avatar`); descartar la archiva. Exportación `.md` y `.xlsx` con la
plantilla de la hoja "Personas" (`nicho/exportar.py`). UI: pestaña **Nicho**
(`_tab_nicho.html`) y página propia del estudio (`nicho_estudio.html`), Blueprint
`nicho/rutas.py` bajo `/cliente/<cliente>/nicho/...`.

**Biblioteca de referentes** (`referentes/` + `tareas/referentes.py`, spec
`docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md`): anuncios
reales clasificados por etapa (TOF/MOF/BOF), consciencia, familia (190 de
copycoders + las que Claude proponga como `EMERGING`), dolor y firma («por qué
funciona»). Tablas `referente` (`anuncio_id` = id del Ad Library de Meta, UNIQUE
global; `cliente` NULL = global de Creatv, `<cliente>` = solo ese proyecto; solo
se lista con `estado_imagen=ok`, la copia en R2 `referentes/<anuncio_id>.jpg`),
`referente_familia` y `barrido`. `referentes/datos.py` es el único escritor.
Bloque 1: importación del swipe file de copycoders (`referentes/copycoders.py`
lee `const DATA=[...]` del HTML público; tarea `referentes_importar_copycoders`
por fases `anuncios → imagenes → traducir` con continuaciones `__cont`, la única
llamada pagada es la traducción de firmas, gasto tipo `otro` bajo `_creatv`) desde
`/admin/referentes`, y la pestaña **Referentes** (`_tab_referentes.html`, Blueprint
`referentes/rutas.py`: `grid` y `ficha` como fragmentos por fetch, filtros en el
hash `#referentes?etapa=TOF&…`). Bloque 3: la puerta desde Sprints (`sprints.datos.agregar_referencia_biblioteca`, el modo selección del grid, `referentes/sugerir.py`, «Usar en sprint»). Bloque 4: barridos en vivo — `referentes/fuentes/` (registro perezoso por módulo, no por clase: `referentes.fuentes.por_tipo(tipo)` devuelve el módulo con `estimar/probar/traer`), `referentes/fuentes/atria.py` (Ad Library de Meta vía la REST de Atria, `X-API-Key`, 20 llamadas/min, contador mensual en `kv`), `referentes/clasificar.py` (una llamada de visión por anuncio: etapa/consciencia/familia/dolor/firma, familias nuevas entran como `EMERGING: <nombre>`), tarea del worker `referentes_barrer` (tramos de 100, reanudable por `barrido.extra.cursor_atria`, tres fases: trayendo → guardando imágenes → clasificando) y `referentes_clasificar` (reclasifica solo lo pendiente de un barrido). Bloque 5: conector Apify (`providers/apify.py` -- arrancar/sondear/leer el
dataset/contarlo, compartido con `nicho/fuentes/apify.py`;
`referentes/fuentes/apify_actores.py` -- el actor oficial
`apify/facebook-ads-scraper` y su precio real; `apify_adlibrary.py` -- arma
la URL de la Ad Library con país real (a diferencia de Atria, que es solo
UE) e idioma, una sola corrida por barrido sin cursor que retomar, reporta
su costo real por resultado a `gastos` bajo el tipo `recoleccion`).
`traer()` ahora entrega `(pagina, cursor_siguiente, meta)`: `meta` es `{}`
para Atria (solo consume cupo del plan) o `{"costo_real": ...}` para una
fuente que cobra por resultado real. Bloque 6: panel admin completo
(`/admin/referentes`) -- «Traer referentes globales» (mismo formulario y
mecánica que el de un proyecto, pero `cliente=NULL`: el barrido queda
visible para todos), totales por fuente, contador «Atria: N/1200 llamadas
este mes», tabla de familias editable (`datos.familia_actualizar`, sin usar
desde el bloque 1) y las tarjetas de `ATRIA_API_KEY`/`APIFY_TOKEN` en Puesta
a punto. Con esto los seis bloques del diseño original (spec 2026-09-23 §17)
están en `main`. Bloque 2: «Recrear con mi producto» (`referentes/recrear.py`) — `armar_prompt`
determinista (nunca llama a Claude) construye el prompt con la imagen del referente
como `Image 1` y hasta 2 fotos del producto elegido como `Image 2`/`3`; «Adaptar con
IA» (`adaptar`, opcional, ≈ US$0.01) es la única llamada pagada de este bloque y solo
propone texto, nunca genera. Generar reutiliza el pipeline de Crear tal cual
(`creative_flow.crear` + `flowplus_lanzar.lanzar`, `productos_ids` guarda el nombre
visible del producto como en el resto de Crear): la pieza aparece en la pestaña Crear
con su barra de progreso y su Aprobar/Rechazar de siempre. `pieza.extra.referente_id`
(en realidad `concepto.extra.referente_id`, por cómo `creative_flow.actualizar` guarda
los campos que no son columnas propias) es lo que cuenta «Usado N veces» en la ficha.

**Crear (FlowPlus)**. Two paths from the same form (`cf_crear_video`, field
`modo_prompt`). **Default = direct generation** (the "generación tradicional" clients rely
on, restored 2026-09-21 after the director had become the only path): since the
2026-09-26 incident the person's text goes to the model AS-IS via `flowplus_prompt.tal_cual`
(only `@Imagen N` → the model's token in video, plus `SONIDO: <texto>` when she typed a
sound) — no brand guide, no EVITAR/«Recordatorio», no FIDELIDAD/catalog rules, no project
logos. Never add anything in the background unless the person asks for it; `armar` is
still what the director fallback, Sprints and derivations use. `_lanzar_video_cf` launches
right away with the cost shown on the «Generar video» button. **Optional** «Armar prompt
con IA (gratis)» (`modo_prompt=director`, for people who don't know what to write):
sesión en `prompt_pendiente` -> worker
`tareas/director.py` (`director.compilar`: Claude escribe los planos por familia de
modelo, valida y compone A/B con `flowplus_prompt.armar(..., planos=)`; fallback al
prompt determinista, nunca bloquea) -> `prompt_listo` (la persona edita con
`cf_guardar_prompt` o rearma con `cf_rearmar`) -> `cf_generar_video` (A, o A+B vía
`creative_flow.duplicar(prompt_relleno=, variante="B")`) -> `flowplus_lanzar.lanzar`
-> worker `tareas/flowplus.py` -> `providers/flowplus_modelos.py`, todo vía WaveSpeed).
Never make the director mandatory again: a client's own prompt always wins.
References and catalog are optional (2026-09-25): with nothing attached the piece is
`enfoque="libre"` («Solo texto») — no logos, no brand guide, `flowplus_prompt.armar` returns
the person's text as-is (+ the SONIDO line), and each model goes through its `path_texto`
(WaveSpeed text-to-video / text-to-image, same prices; Seedance then does take a format,
`formatos_texto`). Sprints and derivations never use `libre` (they rotate `ORDEN_ENFOQUES`).
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
`armar` prompt (director, Sprints, derivations) carries a `SONIDO:` line ("Sin diálogo
hablado ni música de fondo" keeps Kling's Chinese/English voices out; the Spanish voice
comes from final edition); direct generation carries one only when the person typed a
sound (`tal_cual`). Images never get that line. The session carries `con_sonido` (the "Sonido de la escena" check, default from
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

**Mi música** (`mi_musica.py`, spec `docs/superpowers/specs/2026-09-25-mi-musica-design.md`): the
client's own songs — uploaded (mp3/wav/m4a/aac/ogg, ≤ 20 MB, ≤ 10 min) or created with ElevenLabs
via fal (`fal_audio.musica_elevenlabs`, `fal-ai/elevenlabs/music`, always 60 s, US$ 0.60 per started
minute, worker task `musica_generar`, `max_intentos=1`, gasto tipo `musica`) — are `material` rows
(tipo `audio`, origen `subida`|`musica`, R2 `clientes/<c>/materiales/<hash><ext>`); `mi_musica` is
their only writer. Forms pick a song with the value `mat:<id>` (in «Música al crear» and in
«Producir finales») plus `musica_inicio_s`; `final_edition.musica.pista_propia` downloads it, cuts
from that second to a cached WAV and hands it to the same mixes (`mezclar_musica`, `render.componer`),
at cost 0. IA styles keep going through `obtener_pista` untouched. The panel `_mi_musica.html` lives
inside the Crear form, so it has no `<form>`: routes `mm_subir/mm_borrar/mm_crear/mm_lista` answer JSON
with the re-rendered panel and the song list. Voice cloning is NOT here (fal has no ElevenLabs clone).

**Flow Plus en Crear** (`guiones/`, since 2026-09-25): Crear's third mode «Flow Plus»
(`_tab_flowplus.html` → `_crear_flowplus.html`, hash `#flowplus`; the package is `guiones`
because `flowplus_*` already names Crear's own pipeline). This paragraph covers the correction
chat for a resulting prompt BEFORE generation; the guion → clip prompts → reference-image
prompts pipeline that feeds it is «Flow Plus: del guion a los prompts» below.
Tables `guion_prompt` (`texto_original`, `texto_vigente`, `version_n` CAS, `texto_fijo` =
fragments that must stay literal — the approved guion's exact dialogue —, `estado`
`abierto|aprobado`, `origen` `manual|pipeline`, `extra` for the pipeline's video/clip ids) and
`guion_mensaje` (migration 0018). `guiones/refinador.py` is the only writer: `pedir_cambio`
stores the person's message plus a `pendiente` Claude row, the route runs `responder` on a
`trabajos.iniciar` thread (not the worker queue: a chat must not wait behind renders) and the
page polls `GET .../prompts/<id>`; a `pendiente` older than 3 min becomes `error`. Claude
(`generador_prompts.MODEL`) returns JSON `{respuesta, prompt}` — the FULL revised prompt, in
English — and `validar` (pure: texto_fijo present, clip header 5–15 s, `FINAL CLIP` needs
`HARD CUT`, no un-negated fade to black; `imagen` only checks texto_fijo) marks proposals that
break the non-negotiables; those can't be used or approved. Nothing is applied on its own: the
person picks «Usar esta versión» (or goes back to the original, or edits by hand) and approves.
Every Claude call is registered as gasto `refinar_prompt` (`guiones:refinar:<mensaje_id>`),
also when the answer was unusable. JSON routes in the Blueprint `guiones/rutas.py`
(`/cliente/<cliente>/guiones/prompts...`, same-origin check on every POST).

**Flow Plus: del guion a los prompts** (`guiones/` pipeline, spec
`docs/superpowers/specs/2026-09-25-flowplus-pipeline-guiones-design.md`, migración 0019): Parte A del
spec del cliente (`docs/flowplus/workflow-automation-spec.md`). Tablas `guion_lote` (texto pegado o una
página de Notion, `leyendo|leido|error`), `guion` (un script: `lectura` con líneas numeradas y
`literal`, `leido|confirmado`) y `guion_video` (una versión: `config`, `recorte`, `plan`, `clips`,
`hooks_alt`, `validaciones`, `avisos`, `imagenes`; `configurando|recortando|armando|armado|invalido|error`
y `estado_imagenes`). `guiones/datos.py` es el único escritor; un trabajo con `iniciado_en` de más de
6 min se da por interrumpido: un lote `leyendo` y un video `armando` o con imágenes `escribiendo`
pasan a `error`, y un video `recortando` vuelve a `configurando`. Claude planea y el código escribe: `lectura.py` (copia literal verificada),
`recorte.py` (orden de prescindibles; nunca la línea 1), `clips.py` (plan por números de línea →
`duracion.calcular_clip` → `plantillas.prompt_clip` → validaciones V1-V6/E1-E4 que bloquean; los
prompts entran al chat con `refinador.crear(origen="pipeline", texto_fijo=líneas exactas)`),
`imagenes.py` (hojas de personaje, entornos, producto con sus fotos; tabla imagen↔clip; checklist).
Todo prompt de fábrica pasa `refinador.validar`. Una llamada por paso vía `guiones/claude.py`
(`pedir_json`, gasto `guion_clips` también si la respuesta no sirvió), en un hilo
(`trabajos.iniciar`). Cambiar una versión armada crea otra (`nueva_version`; con solo el bloque del
video, `clips.version_con_bloque` no llama a Claude). Notion: llave de integración cifrada en `kv`
(`notion:<cliente>`), solo `api.notion.com`, exige correo verificado. UI: `/panel` como fragmento
(`_gpg_*.html`) + `_crear_flowplus_guiones.html`; «Abrir en el chat» emite `gp:abrir-prompt`.

**Final edition** (`final_edition/`): a second pipeline that takes an already-approved
CreativeFlowPlus video (`creative_flow.py`) and turns it into a localized, narrated,
subtitled, scored final ad per idioma/país (`fe_preparar` writes one guion base with
Anthropic; `fe_producir` queues one `final_producir` task per destino ticked, each
worth its own approval). `final_edition/__init__.py::producir` (the worker task `final_producir`, one per destino,
`max_intentos=1`) now runs through the editor (capa 2, 2026-09): `final_edition/produccion.py`
turns the guion into an **edición** (a capa-1 document built by `final_edition/borrador.py`
from materials cached by hash in `final_edition/insumos.py`: the raw clon, the voice per
block — TTS + `atempo` fit as a derived material, Whisper words in `material.extra.palabras` —,
the music track and the logo), translates the destino into it (`variables.textos/voz` and
`por_destino` keyed `<idioma>_<PAIS>` with `<idioma>` as fallback; the price is the reserved
text variable `precio`, formatted per country or absent), freezes a version and renders it with
`tareas.edicion.renderizar_final` (the same code path as `edicion_producir`). One edición per
"receta" (`borrador.receta`: guion base + variante + voz + música + sonido + mezcla + formato):
a second destino only pays its localization and voice; a changed guion or voice makes a new
edición; degraded borradores are never reused (a new one is built, paying only the missing
pieces). `capas`, `pieza.guion`, `final_id`s, the 5 `ETAPAS_FINAL` and the spend row
`final:<id>:t<tarea>` keep their old shape, so the Crear modal, derivaciones and experiments did
not change. `FINAL_EDITION_LEGADO=1` switches the worker back to the old layered pipeline
(`producir_legado`: `guion` -> `cortes` -> sonido -> `voz` -> `musica` -> `texto` -> `render`),
kept only until `render.py`/`texto.py` are retired. Since S2 the clon's native sound is a layer: `producir` reads the RAW clon
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

**Editor (capas 1–2, 2026-09):** the editor's source of truth is a JSON document
(`final_edition/documento.py`: validate, resolve variables per idioma/país, migrate
schema). `validar` is the contract everything else leans on: the principal `video` track
must be contiguous from 0 (first clip at 0, each clip starts where the previous ends —
`imagen` tracks have no timeline), every pista/clip id matches `^[A-Za-z0-9_-]{1,40}$`
with clip ids unique across the document, `pngs` is `{text clip id: material id}`,
keyframes have strictly increasing `t_ms`, audio clips keep `velocidad` 1.0 (no `atempo`
yet), and `materiales` is DERIVED (given list ∪ clip `material_id`s ∪ `pngs` values), so
`en_uso`/`marcar_uso` never trust the browser's list. The document is stored in `edicion` with CAS autosave (`ediciones.guardar`: `version_n` must match
or `Conflicto`) and frozen copies in `edicion_version` (`versionar` takes SQLite's write
lock before `MAX(n)`, same trick as `experimentos._bloquear`; `restaurar` migrates the
frozen document before reusing it). Every file that costs money or time is a `material`
row keyed by `UNIQUE(cliente, hash)` (`materiales.py`: never pay twice; `borrar` only
deletes R2 objects under `clientes/<cliente>/materiales/` — any other key, e.g. a Crear
piece's video with origen `crear`, loses just its row — and propagates a failed R2 delete
instead of swallowing it, so the row survives for retry — `limpiar_sin_uso` skips those
rows too; `en_uso` scans live documents AND frozen `edicion_version`s;
`obtener_o_crear`'s `producir()` can still run twice in a true race, accepted). `final_edition/motor/` compiles a resolved document into
one ffmpeg filtergraph (`compilador.py`, pure): a `transicion` of `d` ms on clip A
occupies output `[fin_A, fin_A + d)` while B keeps its timeline position — the extra
frames come from A's tail (`recorte.hasta_ms + d × velocidad`), and a hard cut is
`concat,settb=1/fps`. Audio chains one filter per clip
(`atrim`/`asetpts`/`volume`/`afade` at real clip edges, `adelay` past the window start),
`amix`ed per role at ≥ 2 clips into `mezcla.filtro_mezcla`, with `anullsrc` covering a
window with no audio clip so `concat -c copy` never breaks on a stream mismatch, and `-t`
always closes the output (the mix carries `apad` too); only x/y keyframes are interpreted
(piecewise-linear in `t` — escala/opacidad/rotación wait for PNG-alpha layers). Free
texts are browser-rendered PNGs (`rutas["png:<clip_id>"]`, `ancho_px`/`alto_px` per clip,
400×200 fallback) placed via `final_edition/geometria.py`'s
fraction→pixel math (round-half-up; `tests/fixtures/geometria_casos.json` is the parity
table the browser must match too), scaled to that box (`scale=w:h`) with per-clip
`opacidad` (`colorchannelmixer`); the native scene sound is just an `audio` pista with
`rol_audio: sonido` over the same material (all non-voz/musica roles `amix` into
`filtro_mezcla`'s sonido input); `tpad=stop_mode=clone` pads the main track when the audio
outlasts it; subtitles get `fontsdir=static/fonts` and every path inside the graph goes
through `_ruta_filtro` (two-level ffmpeg escaping — `'` becomes `\'\''`). NOT rendered in
capa 1: `superpuesto` (PIP — `compilar` raises if it has clips), `rotacion` and
`marca.marca_de_agua`; and one `-ss/-t` input per principal clip (memory bound for
reordered clips) is due before capa 3. `motor/tramos.py` splits into windows past
`PRESUPUESTO_OVERLAYS=60`, never cutting inside a transition's `[fin_A, fin_A+d)` —
exceeding budget at one instant is the only hard error — and `motor.renderizar` cleans
partial `.tramoN.mp4` files in a `finally`. Subtitles are one `.ass`
(`motor/subtitulos.py`) only when the host ffmpeg has libass (`render.tiene_libass()`,
cached: the VPS does, the dev Mac doesn't — `renderizar` reports the omission via
`on_etapa`). Worker tasks in `tareas/edicion.py`: `edicion_producir` renders the FROZEN
version (`max_intentos=1`, no spend of its own: the automatic path pays in
`final_edition/produccion.py`; the route must `crear_final` BEFORE enqueuing — the task
raises if `actualizar_final`/`apuntar_final` find no row — and `idioma`/`pais` are
shape-checked before the work folder exists; `preparar_rutas` stamps `imagen` clip sizes
from the material row and runs `compilador.verificar_recortes` with the known
`duracion_ms`), uploads to versioned keys
`clientes/<c>/finales/<final_id>__v<version_id>.mp4`/`.png` (thumbnail first), errors go
through `cola.sin_token`/`cola.recortar`, and wipes its work folder at start and on
success (kept on failure, for the `.filtergraph.txt`); `edicion_proxy` (540p, frame strip,
scene cuts, `aresample=48000`-first waveform peaks) wipes its folder in `finally`; the
daily `materiales_limpiar` (`worker.PERIODICAS`) is what deletes efímero materials.
Capa 2 additions: `documento` keys by destino (`<idioma>_<PAIS>` wins over `<idioma>`), the
reserved `precio` variable (clip dropped when the country has no price), `por_destino`/`bloque` on
voice clips, `ken_burns: in|out` on principal clips (compiler `zoompan`), normalized
`estilo.{contorno,sombra,fondo,ancho_max}` (fractions of the canvas) and opaque `origen`/`guion`.
Text clips without a browser PNG are rasterized server-side by `final_edition/rasterizar.py`
(Pillow, same TTFs) inside `preparar_rutas` — the automatic path has no browser. `materiales.descargar`
copies `extra.local` when the file is still on disk; `materiales.actualizar_extra` merges into
`extra`; `ediciones.buscar_origen` finds the borrador of a receta. A fatal first-block voice
failure raises `produccion.VozFatal`, and any exception raised after paying carries
`costo_pagado`/`capas_pagadas` so `producir` still records the spend (Task 8's rulings).

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
launch (resumable). UI (since 2026-09-20, "la galería primero"): the Experimentos tab opens with a gallery of
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
or `prod_vincular` creates their activo. Configuración (`_tab_settings.html`) shows one
apartado at a time (pills, last one remembered, `window.irAConfig(id)` opens the apartado
holding `id`): Puesta a punto (admin only), Conexiones (Meta full width, store, Pixel, organic
channels), Marca, Generación, Cuenta y avisos, Gasto. The key cards (`_llave_tarjeta.html`,
`dashboard._estado_llaves`) list every
paid key (Anthropic, fal, Higgsfield, R2, Meta, SMTP, MELI) with configured/missing badges —
computed from `bool(os.environ.get(...))` only, values are never rendered. Since 2026-09-20 that
full list is admin-only: `dashboard._llaves_visibles` gives a cliente just the `por_proyecto`
cards (Meta), and the template hides `.env` variables, the server note and the "Cómo
conseguirla" steps for them (the client sees `cliente_hace`: billing + the connect block).

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
also returns the last row before the window) and derives the month tiles, the 30-day
series, the top-5 winners and the alerts; `dashboard._contexto_tablero` caches it 60 s per
client keyed by the latest snapshot id and the proposal count, and degrades part by part
(never leaking exception text). The chart is inline SVG on a single axis (spend bars,
revenue line, validated colorblind-safe pair). `csv_mes` escapes formula-leading cells.
When the suggested attribution is `pixel`, `experimentos.objetivo_sugerido` is
`OUTCOME_SALES`; `lanzador.lanzar` then re-checks the Pixel before touching Meta and sends
`promoted_object={pixel_id, PURCHASE}` on every adset (`meta_ads/adset.py` refuses SALES
without it). The objective is fixed at creation — Meta doesn't allow changing it.

**Triple Whale** (`triple_whale.py`, `triple_whale_tiendas.py`, table `triple_whale`): an
optional, per-project alternative to Meta Pixel/store attribution, connected from
Configuración › Conexiones (Fernet-encrypted API key, same pattern as Shopify/WooCommerce —
the connect/probar/desconectar form was accidentally removed for ~4 days in 2026-09 by an
abandoned "move to Experimentos" refactor that never got its second half; restored where it
was, since Meta never moved either). A project picks `atribucion="triple_whale"` on its
experiment the same way it picks `pixel`/`tienda`; `lanzador._obtener_metricas_triple_whale`
calls `triple_whale.metricas_por_anuncio` (Triple Whale's `ads_table`+`pixel_joined_tvf()` SQL,
one row per ad per day), filters to the piece's `meta_ad_id`, and SUMS the days into a
lifetime-cumulative snapshot (never averaging the API's own per-day `pixel_roas`/`pixel_cpa`,
which are ratios) — ctr/cpc/cpm/thruplay_rate are computed from those sums with the same
formula `meta_ads/insights.py` uses. `"triple_whale"` is a first-class member of
`tablero.FUENTES_VENTAS` and of `decisor.py`'s `con_atribucion` sales-gate tuple, so a
Triple-Whale-attributed experiment can win/lose on ROAS/CPA exactly like `pixel`/`tienda` —
until 2026-09-26 it silently could not (a parameter-name mismatch in the metrics call always
raised, caught by a broad `except Exception`, so it fell back to Meta Pixel every time; even
fixed, the missing `FUENTES_VENTAS`/`con_atribucion` entries would still have zeroed revenue
and blocked the sales gate). The exact SQL (column names, whether the model/window filter
belongs in the `JOIN ... ON` or the `WHERE`) is Creatv's own best reading of Triple Whale's
public "Data Dictionary" docs (`docs/triple-whale/investigacion-api-2026.md`) — flagged there
as **never verified against a real connected store**.

**Gasto real por proyecto** (`gastos.py`, table `gasto`, migration 0010): there are no
credits or balances — the product shows the real provider price. Every paying task registers
one row per charge through `gastos.registrar_seguro(cliente, tipo, usd, referencia, ...)`
(never raises), with a reference that includes the task id (`final:<id>:t<tarea_id>`,
`video:<cf_id>:t<tarea_id>`, …) so re-runs add history instead of overwriting it; the
reference is unique per cliente, so registering is idempotent. **Any new task that pays a
provider must call it** where the real figure is known (on failure after paying, register what
was paid with a detalle). `gastos.estimar(tipo, **params)` gives the "≈ US$" shown next to
buttons from `gastos.TARIFAS` (video/imagen from `flowplus_modelos`, `final` per country,
guion, regla_producto, caption_organico) and returns "precio no disponible" rather than
guessing. Meta spend is NOT in `gasto` — it comes from `metrica_snapshot` via `tablero` and is
shown next to generation spend in its own currency. UI: sidebar chip "Este mes: US$ X
generación · Y pauta" (context processor, template renders only, cached), Configuración ›
Gasto (by type, history, CSV), Tablero tile, admin panel column.

**Cuentas** (`usuarios.py`, `cuentas.py`, table `token_cuenta`, migration 0011): users still
live in `usuarios.json` (now with `correo`, `correo_verificado`, `session_version`,
`creado_en`; correo unique across users, usuario validated `[a-z0-9._-]{3,40}`), while
one-time tokens (verification 24 h, password reset 1 h) live in SQLite as sha256 hashes —
emitting a new token invalidates the previous ones of that type, `consumir` marks it used.
Flows: registration asks for correo and sends a verification link; `/verificar/<token>`;
`/reenviar-verificacion`; `/recuperar` (always the same neutral answer) →
`/restablecer/<token>` (GET validates without consuming, POST consumes, changes the password
and bumps `session_version` so every other session dies — `_verificar_sesion` compares the
cookie's `sv` on each request and rejects sessions whose usuario no longer exists);
Configuración › Cuenta (change correo → re-verify; change password → current required).
Without a verified correo a cliente cannot connect Meta or a store (`_requiere_correo_verificado`;
admins exempt); admins can mark a user verified from the panel. Rate limits (`cuentas.limite_ok`,
`kv`, 5/h) per correo and per IP on registration, resend and recovery. Links are built from
`PLATAFORMA_URL` (never from the `Host` header) and the app 404s requests whose host isn't that
one (or localhost); `DETRAS_DE_PROXY=1` enables ProxyFix; session cookies are HttpOnly, SameSite
Lax, Secure when the platform URL is https. Emails go through `notificaciones.enviar(html=)` —
if SMTP is missing the flows still work and the admin panel shows the warning.

**UI base** (2026-09-25/26, specs `2026-09-25-base-visual-comun` and `2026-09-26-movil`): the
block «Base visual común (2026-09-25)» at the END of `static/style.css` is the source of truth for
fields, labels, buttons (`.btn-generar` = primary with white text; `.btn-sm`/`.btn`/classless
`button` = secondary), `summary`, the tab header (`.panel-cabecera` > text div with `h2` +
`.panel-cabecera-desc`, plus `.panel-cabecera-acciones`) and `.estado-vacio`; new screens reuse
those instead of new one-off styles. `cliente.html` switches tabs on `hashchange` and scrolls to
top; `data-abrir-detalle="<details id>"` opens a `<details>`. Up to 760 px the sidebar leaves the
screen and opens with «☰ Menú» (`body.menu-abierto`); nothing may scroll the page sideways
(`tests/test_base_visual.py`, `tests/test_movil.py`).

**Doctrina de venta y ángulo** (`doctrina/`, spec `docs/superpowers/specs/2026-09-25-doctrina-copywriting-design.md`,
ADR 0004): los principios de seis libros de copywriting (Kennedy, Hopkins, Ogilvy, Great Leads, Schwartz, Theriot)
destilados en nuestras palabras en `doctrina/textos/*.md`, por rebanadas (`base` siempre + `investigar`, `angulo`,
`gancho`, `guion`, `video`, `caption`, `clasificar`, `revisar`); los libros NO están en el repo. Cada llamada a Claude
que escribe o clasifica copy recibe su rebanada con `doctrina.bloque_system(*rebanadas, extra=<instrucciones del
sitio>)` (bloque con `cache_control`): ideas de sprint (`angulo`+`gancho`+`video`), director (`video`), guion
(`guion`+`gancho`, o además `angulo` si la sesión no tiene), localizar (base), variar (`gancho`), captions
(`caption`), «Adaptar con IA» (`angulo`+`gancho`), clasificar/sugerir referentes y analizar referencias
(`clasificar`), avatares y personas sugeridas (`investigar`). El **ángulo** (audiencia, consciencia, sofisticación
1–5, deseo, promesa única, mecanismo, pruebas con fuente `ficha|comentarios|demostracion`, arranque/`lead`, gancho,
faltantes) lo decide Claude antes de escribir y `doctrina.validar_angulo` lo limpia (nunca lanza; una corrección —
en el guion, la misma ronda del guion con errores no bloqueantes—; si la corrección falla por lo que sea, se guarda la
primera respuesta con `faltantes` «error: …» vía `doctrina.anotar_errores`, que los pone primero para que ninguno se
corte antes que un faltante de Claude: nunca se pierde lo pagado). Vive en `campana_pieza.extra.angulo`
(ideas) → `concepto.extra.angulo` (sesión; `duplicar` lo copia; «Adaptar» y el guion lo crean solo si la sesión no
tiene, y el guion solo si trae promesa y gancho) → director, guion, captions; las variantes guardan
`capas.guion.parametros.angulo` (`lead` y `gancho` nuevos). `doctrina.verificar_cifras`: ninguna cifra fuerte (2+
dígitos, %, moneda, «3x», «N de cada M») que no esté en los datos que Claude recibió; del ángulo solo cuenta como dato
`doctrina.texto_verificable` (las pruebas, y el resto solo si ningún `faltantes` es un «error: …»; nunca
`faltantes`). En el guion base y las variantes es bloqueante (va a la corrección y, si persiste, `GuionInvalido`);
localizar no verifica cifras (convierte unidades y precio y el base ya se verificó); en ideas y «Adaptar» queda en
`faltantes`. Sin precio escrito, el precio de la tienda solo entra al guion como `precio_base` si su moneda es la del
país base; si no, el guion no recibe precio. Vocabulario único:
`doctrina.CONSCIENCIAS` (el de Nicho; `normalizar_consciencia` traduce el inglés de referentes y
`referentes.sugerir.NIVEL_A_CONSCIENCIA` se deriva de ahí), `LEADS`, `SOFISTICACIONES`. Nada de esto agrega pantallas
ni migraciones (bloque 1 de 4; los bloques 2–4 están en el §14 del spec). Los topes de salida de estos sitios son
amplios (4 000–16 000 tokens): el pensamiento adaptativo de `claude-sonnet-5` los consume y con topes chicos la
respuesta llega vacía (prueba real del 2026-09-26).

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
