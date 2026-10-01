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
(`pendiente` -> `_prompt_row.html`, `imagen_pendiente` -> `_imagen_row.html`). These
old «Nueva idea» templates are kept on disk but have no live screen; since 2026-10-01 they
are translated like the rest (in the language guard, rendered in both languages by
`tests/test_i18n_nueva_idea.py`), and their routes' messages go through the catalog. When a
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
(once `max_intentos` is exhausted) — never one this worker is running right now
(`cola.recuperar_colgadas(excluir=worker.en_vuelo())`). Since 2026-09-28 (spec
`2026-09-28-crear-sin-cola`, «en Crear nada queda en cola») the worker has two lanes:
`CARRIL_CREAR` (`flowplus_video`, `flowplus_imagen`, `flowplus_recuperar`, `flowplus_director`, `hablado_voz`)
runs up to `HILOS_CREAR = 4` at once — Sprints batches (`prioridad < 5`) take at most
`HILOS_LOTE = 2`, so a single piece from Crear always finds a thread — and everything else
runs one at a time in order, as before; the main thread only supervises (`worker.repartir`).
Code reached from a Crear task must therefore be thread-safe: `_json_store.guardar` uses a
per-thread tmp, `estado.modificar` (used by the worker AND by Flask's approve/reject/publish and
`sprints.revision`) and `musica._bloqueo` take `flock`, R2 opens one boto3 session per call, and
`trabajos.reportar` never raises. A task may return `tareas.Continuar(tipo, payload,
ejecutar_desde=)`: the worker closes it and queues the follow-up with the SAME job_id in one
transaction (`cola.terminar_y_encolar`, retried; if it still fails the task goes to `error` and its
`AL_INTERRUMPIR` hook runs), so the card's bar never sees «nothing alive». A thread that fails to
start gives its task back (`cola.devolver`). **`dashboard.py` runs with `use_reloader=False`
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
`docs/superpowers/specs/2026-09-16-sprints-design.md`): a monthly production plan.
Since 2026-09-26 it is a **board** (spec `docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`):
«+ Nuevo sprint» is a short form (month, optional «momento del mes» from the PROJECT's calendar
`sprints.calendario.presets(proyectos.pais(cliente))` or free text, brands to imitate). Since 2026-09-27
a sprint is **for every country**: no país/idioma in the form, the sprint header or the campaign panel
(`CAMPOS_SPRINT`/`CAMPOS_CAMPANA` refuse them), new sprints store `pais=NULL` and
`idioma=datos.IDIOMA_BASE` ("en"), the idea prompt says «todos los países… cada país los adapta después
en la edición final», and localization per country/language is final edition's job; old sprints keep the
país/idioma they had (still read through `efectivos`). The sprint page (`sprint_detalle.html`) is a board with one card
per campaign (`_sprint_tarjeta.html`, «Siguiente: …» from the pure `sprints/tablero.py`) plus a side
panel (`_sprint_panel.html`, fetched; all its JS lives in `sprint_detalle.html` because scripts in
fetched fragments never run) that saves field by field (`sprints.campana_campo` /
`sprints.sprint_campo`, JSON `{campo, valor}`; `?panel=<cid>` reopens it). Tables `persona`,
`temporada`, `sprint` (`pais`, `idioma`, `marcas`, `momento` since 0021), `campana` (`consciencia`,
`dolor`, `familias`, and `pais`/`idioma`/`marcas` that override the sprint's — NULL inherits, read
through `sprints.datos.efectivos`; no uniqueness since 0021: TOF/MOF/BOF of the same persona and
product are allowed and `campanas_identicas` only warns; the three generic personas are no longer
auto-created), `referencia` (intención tags + descripción; a reference
without descripción is `borrador` and does not count toward progress),
`campana_pieza` (Parte 2) and `sprint_evento`. `sprints/datos.py` is the only
writer; `sprints/estado.py::recalcular` re-derives campaign/sprint states after
every event (states are stored but never trusted blindly); `sprints/progreso.py`
is pure. Routes live in the Blueprint `sprints/rutas.py`
(`/cliente/<cliente>/sprints/...`), registered from `dashboard.py`, which also
adds `sprints_rutas.contexto(cliente)` to the project page. Uploading a
reference enqueues `sprint_analizar_referencia` (Claude vision, cents); "Sugerir
personas" enqueues `sprint_sugerir_personas`; a pasted link goes through
`sprint_referencia_link` (yt-dlp via `referencias_link.descargar`). A reference can also come straight from the referentes library (`origen='biblioteca'`, pre-analyzed, no `sprint_analizar_referencia`): `sprints.datos.agregar_referencia_biblioteca` (deduped per campaign), the Referentes grid's `?campana=` selection mode, `referentes/sugerir.py` (deterministic + optional Claude pick, task `referentes_sugerir_ia`, tariff `sugerir_ia`), and 'Usar en sprint' from a referente's ficha. The panel's free suggestions come from `referentes.sugerir.sugerir_campana` (filters etapa + consciencia + familias, loosens familias then consciencia and says so, ranks brands to imitate → campaign language → variantes × días); «Sugerir con IA» sees the same candidates (`candidatos_aflojando`) plus dolor, marcas and the momento, and `sprints/ideas.py` passes enfoque, mercado, marcas and the momento (or the old temporada) to the idea prompt. Parte 2 (producción): `sprints/ideas.py` asks Claude for ideas per campaign
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
generates) and emails when a batch finishes. The QA row (score, one ✓/✗ per check, verdict) is
the macro `_sprint_qa.html`: tapping it opens each check's reason (a `<details>`, so it works
on a phone; the old `title` tooltip was hover-only). `sprints/revision.py` approves or
rejects (a rejected piece leaves `estado_videos.json`), closes and reopens the
sprint; `sprints/entrega.py` lists approved links and builds the zip
(`sprint_empaquetar`). Retries and regenerations always go through the cost
gate and `max_intentos=1`. Entrega 2 of the board (2026-09-27; it replaced a smaller Armar/Ideas-only version,
c91b6fc, that another session had shipped an hour earlier; spec
`docs/superpowers/specs/2026-09-27-sprints-tablero-entrega2-design.md`): the panel has three
tabs — Armar · Ideas · Piezas (`_sprint_panel_armar.html`, `_sprint_panel_ideas.html`,
`_sprint_panel_piezas.html`, all rendered in one fragment and toggled client-side;
`?panel=<cid>&paso=armar|ideas|piezas`, default from `sprints.tablero.paso_por_defecto`, counters
from `tablero.pestanas`). Armar describes references inline and shows the product's sofisticación;
the persona consciencia selector is gone from the panel (the campaign's consciencia wins,
`fijos_de`). Ideas (angle editor, «Otra idea», «Reescribir», «Aprobar todas») and the «Generar»
cost gate live in the Ideas tab — `campana_ideas` now only redirects there and
`campana_ideas.html` is deleted. The Piezas tab (`sprints.campana_piezas`, re-fetched every 8 s
while something is alive and never while a rejection reason is being typed) reviews, rejects with
an inline reason, retries and regenerates with the price shown and a confirm, and approves what
passed QA for THAT campaign only (`revision.aprobar_pasaron_qa(..., campana_id=)`); the
sprint-wide review page stays for bulk review, filters by campaign («n · ETAPA · persona ·
producto») and links each piece to its panel. «Proponer ideas» shows
`gastos.estimar("proponer_ideas", n=)` and registers its real spend (tipo `ideas`, counted with
`analisis._llamar_contando`, also when the answer was unusable, `max_intentos=1`). The routes the
panel calls answer JSON when asked (`_quiere_json`); plain form posts still redirect (to the panel's tab when `volver=panel`). `base.html`'s unsaved-changes guard marks on `input`, and on `change` only `<select>`s.
`static/angulo.js` clears `data-sucio` on its own fields only after a save that covered the
latest edit. It also makes anything that reads the angle on the server wait for its pending
save (`guardarAngulosPendientes`: «Reescribir», «Aprobar», any form submit — re-sent with `requestSubmit`,
so its `confirm()` asks once); a reload of the SAME campaign's panel keeps what was being typed, which
`<details>` were open and the cursor (`tomarEscrito`/`devolverEscrito`). The Blueprint refuses POSTs the
browser marks as cross-site (`Sec-Fetch-Site`), like Flow Plus and the editor.

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
muestran en Puesta a punto; sin ellas la tarjeta de esa fuente queda apagada — y solo
la ve el admin: al cliente no se le muestra una fuente sin llave ni instrucciones del `.env`
(`nicho/rutas._fuentes_conectadas`; si igual la pide, aviso neutro), porque las llaves son de
Creatv, no suyas (2026-09-27).
**Investigación automática** (spec `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`,
plan `docs/superpowers/plans/2026-09-28-nicho-investigacion-completar.md`): con el tema del estudio y UNA
cifra aprobada (el estimado lo calcula el servidor y el POST exige `total_visto`), la cadena de tareas
`nicho_inv_consultas` (Claude, hasta el tope aprobado de búsquedas — 1 a 4 — por idioma, todas en UNA
llamada: el del país y el de cada tienda que busca en otro, `investigacion.idiomas_necesarios`; se guardan
`consultas` — las del país, las de Reddit/YouTube — y `consultas_por_idioma`; la búsqueda nunca usa más
que ese tope) → `nicho_inv_buscar` por tienda, con las búsquedas de su idioma (si Claude no las escribió,
las del país, y el paso lo avisa) (`nicho/fuentes/plataformas.py`: Amazon con tienda propia, Mercado Libre
en 18 países, Walmart solo en EE. UU., TikTok Shop y AliExpress en todo el mundo — AliExpress busca en
inglés —; actores de Apify con precio por resultado más el arranque por corrida que cobran algunos
(`usd_por_corrida`), `providers.apify.correr_lote` hasta 5 corridas a la vez con techo de cobro cada una
(`plataformas.tope`); el estimado de una tienda es la suma de esos techos y el gasto, `plataformas.costo`)
→ `nicho_inv_seleccionar` (Claude marca lo del nicho; se eligen los de más reseñas y, sin ese dato, los de
más pedidos/vendidos) →
`nicho_recolectar` por tienda y por red (Reddit/YouTube con las mismas búsquedas) → `nicho_generar_avatares`
con `auto` y el tope restante; una investigación solo con redes, sin ninguna tienda, salta `seleccionar`
(no hay productos que juzgar). El estado vive en `estudio.extra.investigacion` (`nicho/investigacion.py`,
puro; RMW con candado en `datos.actualizar_investigacion`) y es el del primer paso pendiente o en curso
(`marcar_paso`), porque `avanzar` encola el siguiente paso sin marcarlo todavía; cada tarea llama
`tareas.investigacion.avanzar`, una tienda caída no frena a las demás, «Reanudar» no repite lo que cobró y
los productos van a `producto_nicho` (migración 0016; `resenas_traidas` evita pagar dos veces). La cifra
aprobada cubre el peor caso de cada paso pagado, incluida la línea de avatares
(`avatares.estimar_costo_maximo()`: los dos topes de `seleccionar` llenos a la vez — 600 comentarios que
suman 250 000 caracteres —, contados con la línea entera que va al prompt y la regla de otro mercado, más la
pasada de completado). La salida de Claude cuenta el pensamiento adaptativo (se cobra como salida): consultas
y selección por su tope de `max_tokens`, los avatares con salidas esperadas medidas en la prueba real del
2026-10-01. Gasto: Apify como `recoleccion`, Claude de la
investigación como `investigacion`; cada llamada a Claude de la cadena registra su gasto apenas responde,
con la referencia del spec en el primer intento, `:i<intento>` desde el segundo y `:fallido<intento>`
cuando el intento no sirvió (un reintento no vuelve a llamar a Claude si el paso ya quedó hecho). Los pasos
de red corren con `max_intentos=1`; un paso de la cadena de una investigación ya cancelada no hace nada ni
cobra. Si falla una tienda o una red, solo ese paso queda `error` y la cadena sigue; si Claude falla en el
último intento de consultas o selección, o fallan los avatares, la investigación queda `detenida`
(reanudable); y si una tarea no alcanza a cerrar su paso o a encolar el siguiente (`tareas.investigacion.
red_de_la_cadena`, `_avanzar_seguro`), queda `interrumpida` con el error: nunca colgada con un estado vivo y
nada en la cola. El `url` y la `imagen` de un producto solo se guardan si son `http(s)://` (van a un enlace).
Mientras la investigación está viva, la recolección manual del estudio y «Generar avatares»
esperan (las rutas los rechazan); si un trabajo manual con el mismo job_id sigue bloqueando un paso de la
cadena, `avanzar` deja la investigación `interrumpida` para que «Reanudar» funcione en cuanto termine. El
Blueprint de Nicho rechaza los POST que el navegador marca cross-site (`Sec-Fetch-Site`), como Sprints y
Flow Plus. Los precios por resultado del registro (`nicho/fuentes/plataformas.py`) son los del plan de
Apify de Creatv (FREE), verificados contra el cobro real de corridas reales (Amazon búsqueda y MELI
reseñas corregidos el 2026-10-01; un plan de pago puede bajar algunos); un actor que ahora exige acceso
completo a la cuenta (`full-permission-actor-not-approved`) se rechaza con su propio aviso, nunca con el
de token (`providers.apify.arrancar`).
**Otro mercado** (Parte 4, spec `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`): una tienda
sin sitio en el país del estudio no se rechaza: `plataformas.mercado(clave, pais)` → `("otro", casa)` y busca
y trae reseñas de su sitio principal (Amazon y Walmart → EE. UU., Mercado Libre → México); en la tarjeta va en
«De otros mercados», desmarcada de entrada («Marcar todas» marca todas las tiendas que tienen su llave, de los
dos grupos). Cada reseña de tienda guarda en
`comentario.extra` su `pais` (el del comprador si el actor lo da — AliExpress —, si no el del sitio) y
`mercado` (`local | otro`) respecto al país del estudio; si el estudio cambia de país («Investigar de nuevo»,
«Editar estudio»), `datos.actualizar_estudio` recalcula ese `mercado` en la misma transacción. Las reseñas de
Walmart y AliExpress se atribuyen a su producto también por el link que les mandamos (`producto_pedido`: su
`productId` puede ser el de una variante). La página lo muestra en comentarios y citas,
`avatares.seleccionar` pone primero las fuentes locales en cada vuelta y los prompts de avatares marcan
«otro mercado: <país>» con la regla de que identidad, demografía, edad, momento de vida, tono y conciencia
salen del mercado local. La selección de productos toma por turnos entre tiendas
(`investigacion._repartir_por_plataforma`): AliExpress, que no trae número de reseñas, no queda fuera del corte
de `MAX_FILAS_SELECCION`. eBay y Etsy se probaron con centavos y quedaron fuera (spec §1.1).
**Avatares del proyecto** (spec `docs/superpowers/specs/2026-09-29-nicho-avatares-proyecto-design.md`):
página `/cliente/<c>/nicho/avatares` y bloque en la pestaña. Nuevos = sub-avatares propuestos; aprobados =
personas no archivadas (lo que ve toda la app). Los avatares escritos a mano viven en un estudio oculto
(`extra.manual`) y nacen aprobados (persona `manual`); nunca se completan con IA porque no tienen
comentarios. Una persona sin avatar se edita creándole uno (`avatar_desde_persona`); editar un aprobado
actualiza su persona. Archivar/Desarchivar es solo para personas sin avatar; las que sí tienen uno usan el
Aprobar/Descartar del avatar. `nicho/calidad.py` define «completo»; la generación lo exige y una pasada de
completado llena solo lo vacío (citas verificadas); «Completar incompletos» (`nicho_completar_avatares`,
`max_intentos=1`, gasto `avatares`) lo hace con lo ya guardado, decidiendo contra la fila VIVA al guardar
— una edición hecha mientras corre nunca se pierde.
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
`referente_familia` y `barrido`. `referentes/datos.py` es el único escritor. La búsqueda (`q`) y las marcas a imitar
comparan sin tildes ni mayúsculas con `db.pliegue`, que `db.engine()` también registra como función SQL
`pliegue(col)` en cada conexión (el `lower()` de SQLite solo baja ASCII).
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
TrendTrack (2026-09-30, spec `2026-09-30-fuente-trendtrack-design.md`): tercera fuente de barrido,
`referentes/fuentes/trendtrack.py` (`TRENDTRACK_API_KEY`, plan Pro). Solo busca por palabra clave
(`MODOS = ("palabra",)`, `fuentes.modos(tipo)`: el formulario esconde «De una marca» y las rutas lo rechazan),
pide `GET /v1/ads?search&limit&offset` con `Authorization: Bearer`, prueba la llave con `GET /v1/me` (gratis) y
cobra 1 crédito por fila devuelta: el formato y «solo activos» se filtran AQUÍ, después de pagar, así que se
miran hasta 3× los anuncios pedidos. Como Atria, `usd_fuente` es 0 y el uso se cuenta en `kv`
(`creditos_este_mes`, `creditos_restantes` desde `X-Credits-Remaining`, visibles en `/admin/referentes`). **Los
nombres de los campos de cada anuncio NO están verificados** (la documentación estaba bloqueada): `_normalizar`
los lee con la tabla `_CLAVES`, la primera página es de 10 filas y, si ninguna se reconoce, el barrido se
detiene con un error que lista los campos recibidos.
Barridos por palabra (2026-09-27, tras «dolor de pies» que trajo ruido pagado): SIEMPRE en inglés
— `referentes/traducir.preparar_consulta` traduce lo escrito con Claude (≈ US$ 0,0002, gasto tipo
`otro`, bajo `_creatv` si es global), guarda `consulta.palabra_original`, fuerza `idioma=en` (no hay
selector de idioma en los formularios; «Mis barridos» muestra «dolor de pies» → «Foot pain») y si
no se puede traducir el barrido no se lanza. Atria va con `order=best_match` (sin él ordena por
`newest` y su `query` acepta cualquier palabra); Apify, con varias palabras, pide la frase exacta
(`keyword_exact_phrase` con comillas). `datos.borrar_de_barrido` quita los referentes de un barrido
y las familias `claude` que quedan vacías (el barrido queda por el historial del gasto; las
imágenes R2 las borra el llamador).
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
**Recrear fiel** (spec `docs/superpowers/specs/2026-09-30-recrear-fiel-design.md`, pedido de Daniel tras una imagen
que salió con una mano y un pie en vez de las dos sandalias de la referencia: una foto del producto sostenida con las
manos ponía su pose y la guía de marca pedía pies y manos): al abrir Recrear, el formulario pide solo
`POST …/recrear/leer` (`referentes/lectura.py`: una llamada de visión, ≈ US$ 0,01, gasto `adaptar_referente` también si
la respuesta no sirve) que describe la composición EN INGLÉS, el producto en singular, las unidades, si hay personas y
los textos de DENTRO de la imagen con su rol; se guarda una vez por referente en `referente.extra.lectura`
(`datos.guardar_lectura`, candado antes de leer) y el formato por defecto pasa a ser el más parecido
(`lectura.formato_cercano` con las medidas de `lectura.medir`). Los textos leídos son campos editables (`texto_<i>`;
el de rol `marca` nace vacío = se quita) bajo «Traer los textos de la referencia» (apagada = sin ningún texto,
`recrear.instruccion_textos`); reemplazan el campo «Titular». En imagen, dos casillas (`modo=fiel|libre`) crean una
sesión de Crear cada una (fiel primero, `extra.recrear_modo`, títulos « · igual» / « · variación»): la fiel
(`recrear.armar_prompt_fiel`) dice «edita Image 1 y déjala idéntica, cambia solo el producto», con la composición, las
unidades y «de Image 2 toma solo cómo es el producto», SIN guía de marca, firma ni dolor; la variación es
`armar_prompt` con la línea de textos. El servidor arma los prompts al generar (`_contexto_recrear`, marca
`campos_vista=1`) salvo el que la persona editó (`<campo>_editado=1`); sin la marca se usa `prompt` tal cual (camino
viejo). «Adaptar con IA» reescribe los textos alineados (misma cantidad; marca vacía) y el prompt de la variación. La
pestaña tiene dos `<script>` con su propio `cargarEnDialogo`: el de la ficha avisa con el evento `ref:fragmento` para
que el otro pida la lectura. Enter en un campo no envía. El Blueprint de Referentes rechaza los POST cross-site
(`Sec-Fetch-Site`).
**Como video** (spec §12 y §12.1, 2026-10-01): las mismas casillas; «igual» Y «variación» crean cada una su sesión
de IMAGEN (la fiel o la variación, con el prompt de imagen) con
`extra.animar_despues = {modelo, duracion, formato, prompt, con_sonido, titulo}` y, cuando el worker la termina
(`tareas/flowplus.ejecutar_imagen` → `_animar_imagen`), `recrear.lanzar_animacion` crea y lanza UN video con esa imagen
como única referencia (`recrear_modo="fiel_video"|"libre_video"`, `imagen_origen`; idempotente por `animar_despues.cf_video`; si falla,
la imagen queda lista con `animar_error`, que su detalle muestra). El modelo lo elige la persona en «Animar con»
(`MODELOS_ANIMAR`: Seedance 2.5 por defecto, el único que arranca desde la imagen; Wan 3.0); `armar_prompt_animar` dice
«Image 1 es el primer fotograma, no cambies nada» (el mismo para los dos). La variación hecha directo con Wan arrancaba
con el subtítulo viejo de la referencia y cortaba a la foto del producto con manos: por eso también va por imagen. El formato de video va al más
parecido que el modelo admite (`_formato_video`: 4:5 → 3:4 en Wan). Un formulario de video sin `modos_vista` (abierto
antes de esto) sigue haciendo un solo video.

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
The reference tray (`referencias_flowplus`, one file per PROJECT, shared by everyone working on
it) follows «what you see is what gets used» (2026-09-26 incident: a «solo texto» piece took the 4
references another person had just loaded): the Crear form sends `bandeja_vista=1` + the `ref_ids`
it shows (hidden inputs with `form="form-flowplus"` in `_flowplus_bandeja.html`); `cf_crear_video`
uses only those, removes only those after creating (`_consumir_bandeja` → `quitar_varios`), and if
one of them is gone it generates and charges nothing. Without `bandeja_vista` (scripts/old tests)
the whole tray is used and emptied, as before.
Las referencias se nombran `Image N` / `Video N` (`flowplus_prompt.asignar_tokens`,
por modelo: Wan recibe los videos aparte). Spec:
`docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (Etapa 1 hecha;
presets de cámara, Etapa 2, pendiente). **Etapa 3, recetas de tomas (2026-09-30):**
`plantillas_anuncio.py` (8 recetas: «Antes y después» + las 7 del spec §9; datos puros +
`actos_en_segundos`, `n_planos`, `bloque_director`) y el selector «Receta de tomas» pegado a «Crear super
prompt» en Crear (`name="plantilla"`). Solo cuenta con `modo_prompt=director`: el «Generar video» directo la
ignora y guarda `plantilla=None`. Con receta, el enfoque lo fija la receta (si tiene; una pieza sin
referencias sigue `libre`), `director._mensaje` recibe los actos ya en segundos y `director.compilar` pide al
menos un plano por acto (nunca más de uno cada 2 s); «Recrear mi video de referencia» exige un `Video N`
(video en la bandeja con Wan 3.0) en el navegador y otra vez en `cf_crear_video`. Sprints sigue con
`banco_prompts.py`.
**Menciones y recuperación (incidente 2026-09-28,** 6 de 12 videos del día fallaron y los buenos traían
personajes dobles y el dibujo de otro clip**):** `flowplus_prompt.sustituir_tokens` entiende todo lo que la
gente pega de otras herramientas (`@Image1`, `@Image 1`, `@[Image 1](image_1)`, `@image_4`, cualquier
mayúscula) como la mención canónica `@Imagen N`/`@Video N`/`@Logo N`; una mención sin referencia en la
bandeja hace que `cf_crear_video` avise y NO cree la sesión (`menciones_sin_referencia`: nada se cobra).
WaveSpeed sigue trabajando cuando el worker deja de esperar (Wan 3.0 pasó de los 20 min cuatro veces ese
día) y cobra igual: `wavespeed_common.poll_hasta_listo` avisa el `prediction_id` por `on_progreso`
(`avisar_lanzada` apenas hay id), `tareas/flowplus._avisar_fase_de(..., cf_id=)` lo guarda en la sesión
(`extra.prediccion`), un tiempo agotado es `EsperaAgotada` (conserva el id) y un rechazo del proveedor es
`ErrorProveedor` (mensaje, código e id; `_mensaje_error` lo cuenta en palabras en el idioma del proyecto,
p. ej. Kling 1200 «contenido sensible»). El detalle de la pieza ofrece «Recuperar el video (sin pagar de
nuevo)» → `cf_recuperar` → tarea `flowplus_recuperar` (`max_intentos=1`, `TIEMPO_RECUPERAR` 10 min):
vuelve a preguntar por ese id y cierra la pieza con `_terminar_video` (el mismo cierre que la generación
normal; el gasto se anota ahí, con «recuperado»). Nunca genera de nuevo.
**Sin variables quemadas (pedido de Daniel, 2026-09-28):** cada creación nueva arranca limpia. «Empezar de cero»
(`#fp-empezar`, solo JS: `form.reset()` a lo que pintó el servidor + vaciar la bandeja por `fp_vaciar_referencias`)
deja el texto, el sonido, la música y el catálogo en blanco y la duración/modelo/formato en los del proyecto.
«Editar y crear otra a partir de esta» (`fp_reusar`) REEMPLAZA la bandeja con las referencias de esa pieza (antes
se sumaban a lo que hubiera y las referencias «del pasado» se colaban), su precarga (`session["fp_prefill"]`) lleva
`cliente` y `_prefill_para` la descarta en otro proyecto, y la casilla `solo_referencias` trae solo las imágenes con
el texto y los ajustes en blanco (para el clip siguiente con los mismos personajes). Y **ningún modelo recibe menos
referencias de las que la persona ve**: `flowplus_modelos.referencias_de_mas(modelo, referencias, tipo)` cuenta como
`_preparar`/`generar_video` (Wan: imágenes y videos aparte; Kling: el fotograma del video cuenta como imagen;
Seedance 2.5: SOLO la primera; Seedream: 10) y `cf_crear_video` avisa y no genera si sobra alguna (incidente «mira lo
que sacó»: cuatro referencias con Seedance, tres descartadas en silencio, US$ 3,6 cobrados); el compositor muestra el
mismo aviso en vivo (`#fp-aviso-refs`, `data-max`/`data-max-videos` de los radios de modelo) y frena el envío.
**Sin saldo y Wan con videos de referencia (incidente 2026-09-30):** WaveSpeed se quedó sin saldo y los videos
fallaban con su JSON crudo en la tarjeta. `wavespeed_common.error_de_respuesta(resp, path)` es lo que lanzan los cinco
lanzadores de WaveSpeed ante una respuesta no-ok: `SinSaldo` (RuntimeError; 402 o «insufficient credits» / «top up»)
o el RuntimeError de siempre. `saldo.py` recuerda la falta en `kv` (`sin_saldo:<proveedor>`), avisa al administrador
por `notificaciones.avisar_admin` (tipo `sin_saldo`) UNA vez cada `REAVISO_S`, `vigente()` pinta
`_aviso_sin_saldo.html` en Crear y en Cambiar producto (el admin ve desde cuándo y el enlace de recarga; el cliente,
un aviso neutro) y la próxima generación nueva que sale bien lo `limpia` (vence solo a las `VIGENCIA_S` sin fallos).
La tarjeta dice `saldo.mensaje_tarjeta` en el idioma del proyecto, en Crear (video e imagen, que ahora también pasa
por `_mensaje_error`) y en swap; un video sin saldo nunca persigue una predicción vieja. OJO: el VPS no tiene SMTP_* ni
un admin con correo verificado, así que hoy el aviso que llega es el de la app. Y Wan 3.0 con videos de referencia:
los videos juntos hasta 15 s y entrada + salida hasta 30 s (`max_videos_s`, `max_total_con_videos`; 1405 si no).
La bandeja guarda `duracion_s` de cada video (ffprobe al subirlo o bajar el link, `dashboard._duracion_video`;
`fp_reusar` la conserva), `cf_crear_video` avisa y no genera con `flowplus_modelos.problema_duracion`, el compositor
lo avisa en vivo (`data-duracion` en la bandeja, `data-max-total`/`data-max-videos-s` en los radios), el worker recorta
la salida como última barrera (`duracion_con_videos`, midiendo por URL lo que la sesión no traía) y el precio incluye
los segundos de entrada que WaveSpeed factura en Wan (`segundos_facturables_referencia`: cada video 1–15 s, el total
hasta 15 s, hacia arriba; `estimate_video(..., videos_ref_s=)` en el botón, al reintentar y en el gasto real).
Desde el carril de Crear (2026-09-28) eso pasa solo: la primera espera dura `ESPERA_PRIMERA` (10 min,
`wavespeed_common.cortable(plazo_s=)`), y si WaveSpeed sigue la sesión queda en `video_generando` y la tarea
devuelve `Continuar("flowplus_recuperar")`, que pregunta `TIEMPO_RECUPERAR` (45 s) cada `PAUSA_RECUPERAR` (60 s)
—el hilo queda libre entre vueltas— mientras la predicción tenga menos de `ESPERA_MAXIMA` (2 h); recién después
queda el botón. El sondeo aguanta hasta `FALLOS_SEGUIDOS` (6) cortes de red o 5xx seguidos, y un error que no sea
`ErrorProveedor` (estado final fallido) nunca borra el id: se sigue esperando. Un reinicio del worker corta esas esperas enseguida
(`wavespeed_common.fijar_detener` + `cortable()`, solo en las tareas que saben retomar; un swap o una imagen
siguen como antes) y el gancho `interrumpida` retoma por la predicción un video que quedó a medias por un
SIGKILL. Desplegar ya no pierde videos de Crear en curso.
Los lotes de
Sprints encolan el director con `auto_lanzar` (el costo ya se aprobó). `calidad`
`borrador` = Wan a 480p. Duración por defecto 8 s (`preferencias_flowplus`). `VIDEO` /
`IMAGEN` there are the only model registry (path, price, limits, `audio_nativo`,
`familia`, `min_duracion`/`max_duracion`, `formatos`). Crear makes ONE piece per click (the enfoque is
automatic: `producto`, or `persona` when a catalog personaje is among the references; since
2026-09-28 `armar` never forbids people or hands for `producto` — no «EVITAR: personas, pies,
manos», no «Recordatorio final … solo y sin nadie», no pruning of the brand guide —: the product
is the protagonist and the scenes show what it does or changes; the CON PERSONA block still comes
only with a catalog personaje or the `persona` enfoque, and `director._mensaje` spells out each
enfoque to Claude with `_ENFOQUES_DIRECTOR`),
offers 5–30 s (default 8 s) and the formats each model admits (verified on WaveSpeed 2026-09-18: Wan 3.0
2–30 s and 9:16/16:9/1:1/4:3/3:4; Kling O3 Pro 3–15 s and 9:16/16:9/1:1; Seedance 2.5 4–30 s
and follows the reference image, `aspect_ratio` None; Seedream V5 Pro takes `aspect_ratio`
for images). `ajustar_duracion`/`ajustar_formato` run in the route AND again in the worker's
`_preparar` (last barrier before spending), so nothing outside a model's range is ever
requested. Videos
ALWAYS ask for the model's native scene sound (`generar_video(..., con_sonido=True)`: Wan 3.0
`generate_audio` (the published schema's name since 2026-09-28; `enable_audio` was silently ignored), Kling O3 Pro `sound` — +0.028 $/s, already inside `estimate_video` and the
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

**Audios en Crear** (`audios.py`, `tareas/audios.py`, spec
`docs/superpowers/specs/2026-09-28-crear-audios-design.md`): cuarto modo de Crear (`data-modo="audios"`,
`#audios`), pedido por Daniel al estilo de MoneyPrinterTurbo: un texto (≤ 3 000 caracteres) leído por una
de las 22 voces verificadas de `fal_audio.VOCES`, elegida en una galería de tarjetas (género y tono de
`audios.VOCES_INFO`/`fichas_voces`, filtros Mujer/Hombre, ▶ por voz: la muestra por voz e idioma se sintetiza UNA
vez para toda la plataforma, fila `material` y gasto del cliente interno `_creatv`; `precalentar_muestras.py`
las genera todas de antemano), diez idiomas (es, en, pt, de, fr, it, fi, sv, no, cs; desde 2026-09-30),
velocidad (`speed` del modelo; nunca `language_code`, multilingual-v2 lo rechaza), y opcionalmente una
canción de Mi música con «empieza en el segundo» y volumen. El resultado es un mp3 (`libmp3lame` 192k):
la música arranca 0,6 s antes de la voz, se agacha (`mezcla.DUCKING_VOZ_SOBRE_MUSICA`), sigue 1,5 s y se
funde después del `loudnorm` (`audios.filtro_locucion`, puro). `audios.py` define las filas y sus
hashes; solo la tarea `audio_generar` y `audios.muestra` las crean (vía `materiales.obtener_o_crear`):
el audio es un `material` (tipo `audio`, origen `locucion`, `extra.{nombre,texto,voz,idioma,velocidad,volumen,musica}`)
con `padre_id` a la voz cruda (origen `voz`, hash `locucion_voz` = texto+voz+velocidad, sin el idioma (el modelo lo detecta del texto): el mismo
texto no se paga dos veces; misma combinación completa → «Ya tenías este audio»). Tarea `audio_generar`
(`max_intentos=1`, un trabajo por proyecto `<cliente>__audio_generar`): registra el gasto tipo `locucion`
(`locucion:<hash12>:t<tarea>`) en cuanto fal cobró, ANTES de mezclar; una canción borrada entre el clic y
el worker deja el audio solo con la voz (`musica.estado="ausente"`). Rutas JSON `au_lista/au_crear/au_borrar/
au_muestra/au_descargar` (el mp3 se sirve como adjunto desde Flask: `download` no funciona con otro origen).
La lista `_audios_lista.html` se re-pinta por fetch y su barra NO lleva `data-poll-job` (recargaría la
página): sondeo propio como `mm-progreso`. Subir una canción aquí usa `mm_subir` y avisa al panel de Mi
música con el evento `mi-musica:cambio` (y al revés). `fal_audio.COSTO_USD_POR_CARACTER` es 0,0001 desde
2026-09-28 (precio real de fal; estuvo 3× alto).

Desde 2026-09-30 (spec `docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md`) el motor lo
decide `audios.motor_de(voz, idioma)`: la galería por Multilingual v2 salvo el noruego, que v2 no habla y va por
ElevenLabs Turbo v2.5 con `language_code`; las **voces propias** por MiniMax Speech 2.8 HD con `language_boost`.
`voces_propias.py` es el único escritor de las voces propias (filas `material` origen `voz_propia`, `url` = su
muestra, `extra.voice_id` de MiniMax), de la grabación de un clon (origen `grabacion`, hash con prefijo propio para
no chocar con Mi música) y de sus muestras por idioma (hash `muestra_propia`, las paga el proyecto). Se crean con la
tarea `voz_propia_crear` (`max_intentos=1`, job `<cliente>__voz_propia`): clonar (US$ 1,50, casilla de permiso
obligatoria guardada en `extra.consentimiento`) o diseñar desde una descripción (US$ 3,00); el gasto (tipo
`voz_propia`) se registra apenas fal responde y la tarea ESTRENA la voz leyendo su muestra, porque MiniMax borra
una voz sin uso real en 7 días (la vista previa no cuenta). En el formulario una voz propia es `vp:<id>`.
Desde 2026-10-01 (spec `docs/superpowers/specs/2026-10-01-mis-voces-en-final-edition-design.md`) Mis voces
también narran finales: grupo «Mis voces» en el selector «Voz» de «Producir finales» (`mis_voces_fe`, solo
valor y nombre), `fe_producir` rechaza una voz propia ajena o borrada sin encolar, `insumos.voz_bloque` (y el
legado `voz._sintetizar_bloque`) la leen con `voces_propias.sintetizar` (MiniMax, la estrena) con caché por
`voice_id`, el `voice_id` entra al hash de la receta del borrador, la capa `voz` anota `fal/minimax`
(`final_edition.proveedor_voz`) y una variante (de gancho o de estructura) conserva la voz propia de su final
original —o, en un destino sin original, la de la final original más reciente de la sesión—
(`final_edition.voz_variante`). Mismo precio por carácter que ElevenLabs.

Fuera: efectos, subtítulos, usar el audio en
un video o el editor, ElevenLabs v3.

**Anuncio hablado en Crear** (`hablado.py`, `hablado_rutas.py`, `tareas/hablado.py`, `static/hablado.js`, spec
`docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md`): quinto modo de Crear (`data-modo="hablado"`,
`#hablado`): una foto del proyecto + un guion de hasta 500 caracteres leído por una voz de Audios → P-Video-Avatar
(`pruna-ai/p-video/avatar`, 720p, US$ 0,025 por segundo de voz redondeado al segundo, tope 30 s). `flowplus_modelos.HABLADO`
es un registro aparte que ningún selector, Sprints ni derivación recorre (`es_hablado`, `es_sesion_hablada`,
`nombre_modelo`, `estimate_hablado`, `generar_hablado`; `estimate_video` delega, así el gasto y «Reintentar» salen de la
misma fórmula). La voz la paga `audios.voz_cruda` (la misma caché `locucion_voz` y el mismo gasto `locucion` que Audios:
una voz no se paga dos veces) desde la tarea `hablado_voz` (`max_intentos=1`, job `<c>__hablado_voz`, en `CARRIL_CREAR`).
La cáscara `_crear_hablado.html` va en la página y el panel (`_hablado_panel.html`: fotos + galería de voces, con la
macro `_voces_galeria.html` que comparte Audios) llega por fetch (`hablado.panel`) la primera vez que el modo se ve; el
JS sondea la voz por su cuenta (sin `data-poll-job`) y repite el POST con `solo_cache=1`, que nunca encola. Blueprint
`hablado` (`/cliente/<c>/hablado/{panel,foto,voz,crear}`, rechaza POST cross-site): la foto llega como ficha
`cf:`/`mat:`/`cat:` de ESTE proyecto, nunca como URL (un personaje del catálogo se sube a R2 al crear); la voz, por su
hash; el precio visto debe coincidir con `estimate_hablado` (si no, 409 y nada se crea). `hablado.crear_pieza` crea una
sesión de Crear (`modelo="p_video_avatar"`, `modo_crear="hablado"`, `enfoque_nombre` «Anuncio hablado»,
`hablado={foto_url, voz_url, movimiento, …}`) y la ruta la lanza con `flowplus_lanzar.lanzar`; el worker usa la misma
`flowplus_video` (`_preparar` conserva el modelo hablado sin ajustar duración ni formato; `ejecutar_video` llama
`generar_hablado`; `recuperar_video` lo encuentra por `nombre_modelo`). «Cómo se mueve» va tal cual como `video_prompt`
(vacío = no se manda). Apagado para una pieza hablada: director y «Editar y crear otra» (también en `cf_rearmar`,
`cf_guardar_prompt`, `fp_reusar`), el camino automático de Final edition (`fe_preparar`/`fe_producir`, nota «Este video
ya habla…») y derivar/rescatar en Experimentos (`pz["sin_derivar"]`, `derivaciones._rechazar_imagen`); el editor, la
doctrina, «Reintentar», «Recuperar» y la publicación orgánica sí funcionan.

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
12 min se da por interrumpido: un lote `leyendo` y un video `armando` o con imágenes `escribiendo`
pasan a `error`, y un video `recortando` vuelve a `configurando`. Claude planea y el código escribe: `lectura.py` (copia literal verificada),
`recorte.py` (orden de prescindibles; nunca la línea 1), `clips.py` (plan por números de línea →
`duracion.calcular_clip` → `plantillas.prompt_clip` → validaciones V1-V6/E1-E4 que bloquean; los
prompts entran al chat con `refinador.crear(origen="pipeline", texto_fijo=líneas exactas)`),
`imagenes.py` (hojas de personaje, entornos, producto con sus fotos; tabla imagen↔clip; checklist).
Todo prompt de fábrica pasa `refinador.validar`. Una llamada por paso vía `guiones/claude.py`
(`pedir_json`, gasto `guion_clips` también si la respuesta no sirvió), en un hilo
(`trabajos.iniciar`), siempre con streaming y topes amplios (armar 48 000, leer 32 000, imágenes 16 000, recorte
12 000): el pensamiento adaptativo gasta del mismo tope, y con 16 000 un guion real de 34 líneas nunca se armó
(2026-09-28; medido 2026-09-30: 19 809 de salida, US$ 0,21). Duración: `duracion.estimado_previo` suma medio segundo de redondeo por clip
esperado (uno cada 12 s) y, con objetivo, `clips.mensajes` le da a Claude lo hablado y el aire máximo
(`duracion.aire_disponible`, contado de más: clips de 10 s y 1 s de redondeo cada uno, porque Claude usa todo el
margen y V6 solo rechaza pasarse): sin eso HappyCozy salió 141/150/165 s con objetivos 133/145/155; con eso, 142 s
en 155 al primer intento. Cambiar una versión armada crea otra (`nueva_version`; con solo el bloque del
video, `clips.version_con_bloque` no llama a Claude). Notion: llave de integración cifrada en `kv`
(`notion:<cliente>`), solo `api.notion.com`, exige correo verificado. UI: `/panel` como fragmento
(`_gpg_*.html`) + `_crear_flowplus_guiones.html`; «Abrir en el chat» emite `gp:abrir-prompt`.
**Imágenes de cada escena** (spec `docs/superpowers/specs/2026-09-30-flowplus-imagenes-por-escena-design.md`,
pedido de Daniel; reemplazó la maqueta 555eb2b/b69620c que nunca llegó a `main`): en una versión `armado`,
`_gpg_escenas.html` (incluido en `_gpg_clips.html`) muestra Image 1…N (las referencias del REFERENCE MAP; las
«por crear» se completan con «Subir la imagen») más las extra (subidas o del Catálogo, numeradas después; el
prompt no las nombra) y, por escena, fichas que se prenden y apagan (sin tocar, lo sugerido = la regla de la
tabla imagen↔clip). `guiones/escenas.py` es puro (claves `r<n>`/`x<k>`, `pool`, `por_escena`, `usar`,
`poner_ref`, `agregar_extra`, `quitar`, `heredar`, `texto_por_clip`); el único escritor es
`datos.modificar_imagenes_escenas` (lock antes de leer; guarda en `guion_video.extra["imagenes_escenas"]`, sin
migración). Rutas JSON `/videos/<id>/escenas/<n>`, `/imagenes/subir` (multipart, `final_edition.biblioteca.subir`:
gratis; prueba antes de subir que se podrá guardar), `/imagenes/catalogo`, `/imagenes/quitar`; el JS del panel
manda `data-gpg-cuerpo` con `data-gpg-accion` y sube con `input[type=file][data-gpg-subir]`. Lo elegido va a los
dos `.md` y a «Antes de generar». `nueva_version` hereda las imágenes subidas de referencias iguales y las extra
(y lo elegido por escena solo con los mismos clips). «Llevar a Crear →» por escena (`/videos/<id>/escenas/<n>/crear`,
pedido de Daniel 2026-09-30): REEMPLAZA la bandeja de Crear con las imágenes de la escena en orden (las del Catálogo se
suben a R2 con la clave de `cf_crear_video`), precarga `session["fp_prefill"]` con `escenas.prompt_para_crear` (REFERENCE
MAP solo con esas imágenes, renumeradas como `@Imagen k` para que Crear las traduzca y revise; una imagen del video que la
escena no lleva se nombra en palabras — un número suelto haría que el modelo tome otra, incidente 2026-09-28 —; sin «Start
image = last frame of Clip N»), la duración de `DURACIONES_CREAR` que alcanza y el formato, y abre `#referencias` (hash
nuevo de `cliente.html`/`_tab_flowplus.html` que fuerza «Desde referencias»). Sin imagen en alguna referencia de la escena
o sin prompt en el chat, el botón queda apagado y la ruta responde 409. Nada se genera.
**Cadena de escenas** («Generar todas las escenas», spec `docs/superpowers/specs/2026-09-30-flowplus-cadena-escenas-design.md`,
plan `docs/superpowers/plans/2026-09-30-flowplus-cadena-escenas.md`; Etapa 0 real verificada el 2026-10-01): la escena 1 va
por Kling O3 Pro `reference-to-video` con sus imágenes y cada siguiente por `image-to-video` desde el último cuadro de la
anterior (`final_edition.cortes.ultimo_fotograma`) con hasta 3 «elementos» de Kling (`flowplus_modelos.crear_elemento`:
la API exige 1–3 `refer_images`, va la misma ficha; caché en `kv` `kling_elemento:<cliente>:<sha>`, gasto tipo `video`
US$ 0,01). Cada escena es una pieza de Crear (`tareas.cadena.lanzar_escena` → `flowplus_lanzar.lanzar`, prioridad 3;
la sesión lleva `imagen_inicial`/`elementos`/`cadena`), así hereda recuperación, gasto y tarjeta. `guiones/cadena.py` es
puro (revisión previa —imágenes, prompts, ≤ 7 imágenes en la 1, ≤ 3 elementos en las demás—, avisos de cambio de lugar,
precio con `estimate_video` + elementos nuevos, `prompt_escena`, transiciones con `preparando`/`detener`); el estado en
`guion_video.extra["cadena"]`, único escritor `datos.modificar_cadena` (candado; mientras corre, las imágenes por escena
quedan bloqueadas). Worker `tareas/cadena.py`: `cadena_elementos` (max_intentos=1), periódica `cadena_vigilar` (60 s:
escena lista → fotograma a R2 → siguiente; falló → `detenida`; al final `cadena_unir`, que arma la edición con
`edicion_clon.crear_de_piezas`). Rutas `POST /videos/<id>/cadena` `{desde, total_visto}` (409 si el precio recalculado no
coincide o falta algo) y `/cadena/detener`; UI `_gpg_cadena.html` dentro de `_gpg_escenas.html` (el panel sondea mientras
corre, con el tope de 12 min de siempre).

**Final edition** (`final_edition/`): a second pipeline that takes an already-approved
CreativeFlowPlus video (`creative_flow.py`) and turns it into a localized, narrated,
subtitled, scored final ad per idioma/país (`fe_preparar` writes one guion base with
Anthropic; `fe_producir` queues one `final_producir` task per destino ticked, each
worth its own approval) — the base guion is written in the language picked in «Idioma base», which defaults to the
project's language (`idiomas.de_proyecto`), and each destino localizes it to its country's language (decisión B,
2026-09-28). `final_edition/__init__.py::producir` (the worker task `final_producir`, one per destino,
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
`final:<id>:t<tarea>` keep their old shape, so the finals UI (then in Crear's modal, now the Final
edition tab), derivaciones and experiments did not change. `FINAL_EDITION_LEGADO=1` switches the
worker back to the old layered pipeline
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
`providers/fal_audio.py` (ElevenLabs `multilingual-v2` for TTS — MiniMax Speech 2.8 HD
for a project's own voices, see «Audios en Crear» —, `fal-ai/whisper` for
word-level timestamps, Stable Audio for music); the premade voice list there is
individually verified against fal (see the module docstring) rather than assumed from
ElevenLabs' own catalog. Fonts are checked into `static/fonts/`; generated music
tracks are cached in `data/musica/` and mirrored to R2. Worker tasks live in
`tareas/final_edition.py`; the dashboard routes are `fe_preparar`, `fe_guardar_guion`,
`fe_producir`, `fe_descartar`. Since 2026-09-27 its UI is its own tab, **Final edition**
(`_tab_final.html`, `data-tab="final"`, decisión de Daniel): the ready Crear videos with the guion,
«Producir finales» and their finals, plus each piece's ediciones with «Abrir en el editor»; Crear
only keeps «Llevar a final edition» (`#final?cf=<id>` opens that piece), and the `fe_*` routes
return to `#final`.

**Editor (capas 1–4c, 2026-09):** the editor's source of truth is a JSON document
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
`marca.marca_de_agua`; each principal clip is its own `-ss/-t` input (capa 3: a reordered clip
decodes only its span; the principal may mix sources). `motor/tramos.py` splits into windows past
`PRESUPUESTO_OVERLAYS=60` or past `PRESUPUESTO_VIDEOS=6` principal clips (each input costs ~85 MB
with ffmpeg 8 on the 1-CPU VPS: a 32-cut edit asked ~3 GB and the kernel killed it, 2026-09-30),
filling each window greedily from safe frontier to safe frontier and never cutting inside a
transition's `[fin_A, fin_A+d)` — exceeding the overlay budget at one instant is the only hard
error. Windows are `.tramoN.mov` with PCM audio (`render.OPCIONES_AUDIO_TRAMO`: per-window AAC
left a ~21 ms gap at every join) and `render.concatenar` copies the video and encodes the AAC
once; `motor.renderizar` cleans the partial files in a `finally`. Subtitles are one `.ass`
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
Capa 3 (2026-09-27): the browser preview `/cliente/<c>/ediciones/<id>` (Blueprint
`final_edition/rutas_editor.py`, data from `final_edition/vista_previa.py`, open to anyone with access
to the project) — ES modules in `static/editor/` (pure: `geometria`, `tiempo`, `resolver`, `precio`,
`texto`, `subtitulos`, `audio`, `reloj`, `pendientes`; browser: `texto_canvas`, `videos`, `lienzo`, `motor_audio`,
`vista`), tested with Node's own runner through `tests/test_editor_js.py` against parity tables that
Python generates (`tests/fixtures/generar_casos_editor.py`; `test_casos_del_editor_al_dia` fails when
one is stale). The preview draws only what the compiler renders (no rotation/PIP/watermark; x/y
keyframes; `deslizar` entry); subtitles use libass's size via `subtitulos.escala_libass()` (OS/2
metrics); audio is Web Audio with a ducking curve precomputed from the voice `picos`, which needs CORS
on R2 (`storage/r2_cors.py`, applied by hand), while video proxies and images load WITHOUT
`crossOrigin` (read-only preview; capa 5, which reads the canvas as PNG, must restore it). Proxies
are short-side 540 with a keyframe every 15 frames (`tareas.edicion.PROXY_VERSION = 2`; the page
re-queues older ones, free) and polls for them at most 5 min, swapping each one in as soon as it is ready
(never while playing). `sembrar_edicion_demo.py` builds a local demo edition (no spend, no R2); its CLI
refuses when `PLATAFORMA_URL` (env or root `.env`) points to a non-local host.
Capa 4a (2026-09-27): the page edits — `static/editor/operaciones.js` (pure: cut at playhead, delete
with ripple on the principal, duplicate, trim from either edge, reorder the principal, move other
layers with snapping, speed 0.5–2×; every result passes `documento.validar`, checked by
`tests/test_operaciones_editor.py` on the real JS output; `p_sonido` is rebuilt as a mirror of the
principal, without the clips at speed ≠ 1; `normalizar` mirrors `verificar_recortes`: it shortens any clip
that asks for more material than exists — counting with `Math.round`, which is never below Python's
round-half-to-even, so what fits in the browser fits in the render — and then the transitions; a voice clip with
`por_destino` can be moved or deleted but not trimmed, since `resolver` replaces it whole per destino),
`historial.js` (undo/redo in memory), `guardado.js` (debounced PUT `editor.guardar` with CAS
`version_n`, 409 → «Recargar»; the route refuses materials from another project), a DOM timeline
(`escala.js` pure + `linea_tiempo.js`) and `pagina_editor.js`; «Editar este video» in the Final edition
tab (`editor.desde_clon` → free worker task `edicion_desde_clon`, `final_edition/edicion_clon.py`: the
raw clon as one clip + mirrored scene sound, destino `<idioma del país>_<proyectos.pais>` via `origen.pais` — `en_US`
for a US project, decisión B; "es" without a country) and «Producir»
from the editor (`editor.producir`: `versionar` → `crear_final` → `edicion_producir` per destino, free; each
destino is first resolved and checked with `verificar_recortes`, a destino whose paid `final_producir` is running
is refused, and a final with video NOT made from this edición — `ediciones.edicion_de_final` — needs
`reemplazar: true`, which the dialog asks for). The editor and the automatic path now share the borrador:
`produccion.traducir` re-applies its pure steps on a CAS conflict (up to 2 retries) instead of paying again.
Capa 4b (2026-09-28, «tipo CapCut», plan `docs/superpowers/plans/2026-09-28-editor-capa4b-capcut.md`): the page is
library | player | properties with the toolbar and a multi-track timeline below at full width (≤ 760 px: player,
toolbar and timeline, and the library and properties are bottom sheets — «Medios · Audio · Texto · Transiciones» and
«Editar», closed with «Listo»); in the Final edition tab «Editar» is the main action of every ready video and the
automatic AI path is a closed, optional `<details>`. Library: `final_edition/biblioteca.py` (upload video/image/audio
as free `material` rows with origen `subida` — a phone photo is uploaded already rotated by its EXIF orientation —,
list the project's materials, the logo included (origen `marca`), plus the ready Crear pieces, and materialize a piece
with the free task `material_de_pieza`), routes `editor.subir`/`editor.biblioteca`/`editor.agregar_pieza`/
`editor.materiales_por_id` (`&preparar=<ids>` queues the free `edicion_proxy` for what still lacks its proxy or peaks,
asked once per material); browser modules `biblioteca.js`, `propiedades.js` (+ the pure `propiedades_modelo.js`),
`lienzo_interaccion.js` (tap, drag and scale on the player; pure `seleccion.js`), `avisos_editor.js` (how the page
notifies those modules; they only touch the edition through the `editor` object of `pagina_editor.js`, which also
exposes `enConflicto()` so the panels say «recarga la página» instead of pointing under the video), and `historial.js`
merges the consecutive steps of one control into one undo. New pure ops in `operaciones.js`: `agregarVideo/Imagen/
Audio/Texto`, `cortarClip` (any track but `p_sonido`), `ponerTransicion` (the five the render does; `desenfoque` is
shown as «Fundido a negro»), `editarTexto` (a variable text changes only the destino being viewed), `cambiar` (a
whitelist; `fondo.ancho: null` = automatic), `volumenSonido` and `cambiarMezcla` — each with a case in
`tests/js/salida_operaciones.mjs` that Python validates. Rules: `normalizar` NEVER creates `p_sonido` (a borrador
whose recipe had no scene sound leaves it out on purpose, and the automatic path reuses that borrador): only
`agregarVideo` (for its own clip; the clips already there get silent mirrors) and `volumenSonido` (that clip at the
slider's value, the rest at 0) create it, and with nothing to mirror it stays empty instead of disappearing; nothing
that is added lengthens the video (image/text layers and música/efecto end at the principal's end — music loops in
the render — and with the playhead at the end they enter whole, ending there); audio added by hand only reuses a
track whose clips share its `rol_audio` (music never lands in the voice's gap). Still out: PIP (video over video),
color filters, rotation and a photo as a principal clip (it goes in as an image layer with «Llenar la pantalla»).
Capa 4c (2026-09-29, trust fixes, spec §2): audio fades never exceed their clip (`normalizar`
+ a compiler `st >= 0` cap), «deslizar» stores 400 ms and drops 8 % of the canvas height in both engines, moving,
stretching or duplicating a layer stops at the principal's end, load warnings are recomputed per change
(`avisos_carga.js`), technical errors fold into «Detalle técnico»/`title`, an expired session says so
(`guardado.sesionTerminada`, `producir.js`), the library deletes unused `subida`/`crear` materials
(`editor.borrar_material` → `biblioteca.borrar`, 409 names the edición), «Editar» prefers the person's edición over
the «Borrador automático» (`ediciones.para_editar`/`nombre_visible`), and `rasterizar.sin_glifos_faltantes` strips
glyphs the font lacks (emojis) while the panel warns.

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
launch (resumable). Meta's raw errors («Meta Ads (<edge>) respondió 400: {JSON cut at 500 chars}») are stored as-is but shown through `meta_errores.explicar` (filter `error_meta`, also used by `tablero.alertas` and `lanzador.traducir_error_meta`): known codes become what to do (1885183 app in Development mode — also recognized in the already-explained text, so it re-renders in the viewer's language —, 190 reconnect, 10/200/294 permissions, 4/17/32/613/80004 rate limit, 368 policy block, 1/2 temporary), otherwise Meta's own `error_user_title/msg`, otherwise the code; the experiment card keeps the raw text in a folded «Detalle técnico». UI (since 2026-09-20, "la galería primero"): the Experimentos tab opens with a gallery of
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
Gasto. The key cards (`_llave_tarjeta.html`,
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
**Triple Whale tab** (`_tab_triple_whale.html`, `data-tab="triplewhale"`, after Tablero) fetches its panel
(`triple_whale.rutas.ver_panel` → `_tw_panel.html`) only when opened: store KPIs (MER, AOV, new customers,
vs. previous period), ad KPIs, alerts, the Tablero chart (`app.extensions["grafico_tablero"]`), spend by
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
Tablero shows «Tu tienda según Triple Whale» (`panel.resumen_mes_tienda`, part `tienda_tw`; the cache key
includes `triple_whale.actualizado_en`). Idea → pieza → anuncio (spec §14): the prefill of «Llevar a Crear»
carries `origen_tw` («<evaluación>:<índice>»), the Crear form returns it in a hidden field and `cf_crear_video`
stores `concepto.extra.tw_idea` (`puente.origen_desde_formulario` validates it, a bad value is ignored); the
idea card lists the pieces born from it with their Crear state and Meta verdict (`datos.piezas_de_evaluacion`,
`panel.enlazar_ideas`) and a Creatv ad says which idea it came from (`piezas_creatv(...)["tw_idea"]`). None of
the SQL has run against a real store yet (spec §9).

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
admins exempt); the «sin correo / confirma tu correo» notice (`#cuenta-banner`) shows only at the
top of Configuración (`_tab_settings.html`), not on every tab (removed from `base.html` 2026-09-26); admins can mark a user verified from the panel. Rate limits (`cuentas.limite_ok`,
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
(`tests/test_base_visual.py`, `tests/test_movil.py`). Phone review of every screen (2026-09-28, CSS block «Celular: revisión de pantallas» at the end of `style.css`): auto-fill grids use `minmax(min(100%, X), 1fr)` (never a bare fixed minimum — a test rejects it), card galleries (Crear, Final edition, Experimentos, Referentes) are 2 columns ≤ 760 px, button/filter rows (`.acciones`, summaries) wrap, long ids/JSON/URLs break instead of pushing the page, and data tables (`tabla-admin`, `tabla-tiendas`, `tabla-productos`, `gasto-tabla`, `sprint-entrega`, `gpg-tabla`, or opt-in `tabla-apilada`) become one card per row ≤ 640 px with each value labelled from its column header (`static/tablas.js` copies the `<th>` text to `data-etiqueta`, also for tables inserted later by fetch); `.solo-teclado` hides keyboard-only hints on touch screens. Crear's «Desde referencias» form is a **composer**
(spec `2026-09-27-crear-compositor`, CSS block «Crear: compositor»): a card whose top half is the bandeja
(OUTSIDE `#form-flowplus`, it carries its own `<form>`s) and whose bottom half is the form, with a bar of pills
whose menus hold the real radios/selects — the selects stay the hidden source of truth and the menus draw chips
from them —, so the POST to `cf_crear_video` is unchanged; upload/link inputs reach their empty outside forms via
`form=`, the catalog opens as a `<dialog>` (`_selector_productos.html` with `sel_dialogo=True`; «Cambiar producto»
keeps its `<details>`), and Enter in a one-line input never submits it (it used to generate and charge).

**Idioma** (`idiomas.py`, `catalogo_i18n.py`, spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md`):
Flask-Babel; el español es el msgid y el inglés vive en `translations/en/LC_MESSAGES/messages.po` (+ `.mo` en
git). **Todo texto nuevo que vea una persona pasa por el catálogo**: plantillas `{{ _('…') }}` (`%` literal =
`%%`, variables `%(x)s`, dentro de `<script>` con `|tojson`, nunca `{% set _ = %}`); Python
`gettext`/`ngettext` de `flask_babel` (nunca `as _`); constantes de módulo con `idiomas.N_` + `|traducir`.
Luego `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar`
(`tests/test_i18n_catalogo.py` falla si falta). Idioma de la persona en `usuarios.json`, del proyecto en
`proyecto.json`, cookie `idioma` antes del login; `idiomas.en_idioma(x)` para correos y worker.
Desde 2026-09-28 (decisión de Daniel) `idiomas.DEFECTO` es `"en"` y `ACTIVO_PARA_TODOS` es `True` para
todos: quien no eligió idioma ve la app en inglés y el selector queda visible para cualquier cliente; los
tests siguen fijos en español (`conftest`). Fase 5 (2026-09-28): Sprints, Nicho y Referentes
ya están en el catálogo. Sprints guarda lo que escribe (eventos, temporadas adoptadas, el momento del mes) en
el idioma del proyecto con `sprints.datos.texto_guardado(cliente, N_("…"), …)` y muestra estados con la macro
`etiqueta_sprint` de `_sprint_macros.html` (los diccionarios traducidos van DENTRO de macros: un `{% set %}` de
módulo en una plantilla importada se cachea en un solo idioma). Un estudio de Nicho toma el idioma del proyecto
(sin selector); el idioma de búsqueda de YouTube sale del país del proyecto (`nicho.fuentes.plataformas.idioma`),
no del idioma del estudio. La biblioteca global de referentes es bilingüe (§B7): `referente.extra.i18n[idioma]`
(firma/dolor; `referentes.datos.localizado`), `referente_familia.descripcion_en` (migración 0022;
`descripcion_familia`; botón admin «Escribir en inglés…» → tarea `referentes_familias_en` por tandas de 40, precio
a la vista, gasto `otro` bajo `_creatv`), `referentes.datos.rellenar_i18n_copycoders()` (idempotente, sin Claude:
correr una vez al desplegar), y los barridos globales clasifican en español e inglés en UNA llamada
(`clasificar.salida_para`, tarifa `clasificacion_bilingue`); la ficha sale en el idioma de quien mira y
Recrear/Adaptar/las referencias de un sprint en el del proyecto.
Desde la fase 6 (2026-09) toda la app pasa por el catálogo (excepciones a propósito: el contenido de
`mapa_codigo.html` — `<html lang="es">`, solo su barra `#mapa-barra` se traduce — y de la doctrina
(`doctrina/textos/*.md`), documentación interna en español; los mensajes de contrato de
`final_edition/documento.validar` y los de `static/editor/operaciones.js` (`INTERNOS` en `tests/test_i18n_editor.py`);
los prompts para los modelos de video e imagen y sus tokens `Image N`/`Video N`/`@Imagen N` (`prompt_swap.py`,
`flowplus_prompt`); las 9 plantillas del flujo viejo «Nueva idea» se tradujeron el 2026-10-01 y `EXCLUIDAS` ya solo
tiene el mapa. Una excepción a §B8: «Escribe aquí» y «Escribe el precio» (capa 4c), el texto inicial editable de un
clip de texto nuevo del editor, salen en el idioma de quien mira). Final edition sigue la **decisión B** (Daniel, 2026-09-28; reemplaza el §B5
del spec): cada final sale en el idioma de su país destino (`<idioma>_<PAIS>`); el guion base, que no es por destino,
en el idioma elegido en «Idioma base» (por defecto el del proyecto), y sus variantes en el del guion base. El editor
no es Jinja: sus textos viven en `static/editor/textos.js` (`ES`, la fuente) y la ruta `editor.ver` manda los
traducidos en `datos-editor.textos` (`final_edition/textos_editor.py::TEXTOS`, mismas claves con `N_`; un test de
paridad compara los dos); `pagina_editor.js` llama a `ponerTextos`, cada módulo usa `t("clave", {x})` (ninguna
variable local se llama `t`: `TAPA_T`) y `separadorDecimal()` para los números; todo texto nuevo de un módulo del
editor va con `t("clave")` en los dos. `pgettext` es palabra clave del extractor (`catalogo_i18n.PALABRAS`) para un
mismo español con dos inglés: «Fuente» del editor → Font (`msgctxt "editor"`), la columna «Referentes» de
`/admin/referentes` → References. Quién decide: lo que responde una ruta = quien mira; lo que se guarda o se manda
(errores de finales y publicaciones, `detalle` de gastos, eventos, mensajes y `return` de tareas, correos del
proyecto) = el proyecto (`worker.ejecutar` ya lo pone; en una ruta,
`with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` alrededor de lo que se guarda, no de lo que se responde);
los correos a admins = el idioma de cada admin. Guardias: `tests/test_i18n_plantillas.py` (toda plantilla
traducida o en `EXCLUIDAS` con su motivo), `test_i18n_mensajes.py` (`RUTAS`/`WORKER`: ninguna ruta ni tarea con un texto fijo fuera de gettext/N_; las claves
quedan eximidas), `test_i18n_editor.py` (JS del editor), `test_i18n_guardado.py` (lo guardado, en el idioma del
proyecto), `test_i18n_fugas.py` (render en inglés), `test_i18n_app_entera.py` (toda la app en inglés con los
valores de producción). Trampas: Babel 2.18 no extrae un `gettext(...)` anidado en los argumentos de
`ngettext(...)` (sácalo antes a una variable local); `actualizar` puede marcar una entrada `fuzzy`, que no se usa en
tiempo de ejecución — corrígela y quita la marca.
Fase 3 (Crear en el idioma del proyecto): las llamadas a Claude reciben el idioma con
`idiomas.de_proyecto(cliente)`, pasado a `doctrina.bloque_system(..., idioma=)` o envuelto a mano con
`idiomas.orden_idioma` (va al inicio Y al final de las instrucciones del sitio; el prompt para el modelo de
video/imagen y los tokens `Image N`/`Video N` siguen siempre en inglés, nunca en el idioma del proyecto —
`idiomas._ORDENES` trae esa excepción). Los textos de fondo (hilos de `trabajos.iniciar`, tareas del worker, sin
contexto de petición) se arman dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))`; los mensajes que
devuelve una ruta siguen el idioma de quien mira la pantalla.
Trampa: `_('…', x=dato)` con variables devuelve `Markup`, que ya escapó `x` como HTML, así que
`|tojson` detrás lo vuelve a escapar (doble escape) — arma esa cadena de JS con gettext en Python,
o usa `|tojson` solo sobre texto fijo y une los datos en JS; y nunca metas `|tojson` dentro de un
atributo con comillas dobles (`onsubmit="…"`), porque emite `"` que cierra el atributo a la mitad —
usa comillas simples o un `data-*`.

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
ni migraciones (bloque 1 de 4; los bloques 2–4 vienen en sus propios párrafos). Los topes de salida de estos sitios son
amplios (4 000–16 000 tokens): el pensamiento adaptativo de `claude-sonnet-5` los consume y con topes chicos la
respuesta llega vacía (prueba real del 2026-09-26).

**Doctrina, bloque 2: el ángulo a la vista** (spec `docs/superpowers/specs/2026-09-26-doctrina-bloque-2-angulo-visible-design.md`):
el ángulo se ve y se edita entero en la tarjeta de cada idea del sprint y en cada video de la pestaña Final edition
(antes de «Preparar guion»; se mudó de Crear con la sección de final edition, 2026-09-27): macro `templates/_angulo_editor.html` + `static/angulo.js` (autoguardado JSON; los campos no llevan `name`
para no mezclarse con el autoguardado de la tarjeta), rutas `sprints.idea_angulo` (409 si la idea ya tiene pieza) y
`cf_angulo`; `doctrina.angulo_desde_formulario` valida sin bloquear (`mensaje_error` da frases simples), conserva
`origen`, pone `editado_en` y quita los «error: …»; con `editado_en`, `texto_verificable` cuenta todo el ángulo como
dato (las cifras de la persona se usan tal cual). Un ángulo sin promesa o sin gancho no manda en `preparar_guion`.
«Reescribir la idea con este ángulo» (tarea `sprint_reescribir_idea`, `sprints.ideas.reescribir`, gasto `ideas`) cambia
título, escena y sonido sin tocar el ángulo. Datos del mercado: la consciencia (la de la campaña,
`campana.consciencia` del tablero de Sprints, y si la campaña no tiene, la de la persona:
`persona.extra.conciencia.nivel`, ruta `sprints.persona_conciencia` — desde la entrega 2 del tablero el panel ya no muestra ese selector: manda la consciencia de la campaña;
`sprints.ideas.fijos_de` aplica ese orden) y la sofisticación del producto (`producto.extra.sofisticacion`, selector en Catálogo) mandan cuando existen:
`doctrina.validar_angulo(..., fijos=)` los impone antes de validar y `doctrina.datos_fijos_texto` los pone en los
DATOS de ideas, guion (sin ángulo) y «Adaptar con IA». Pruebas y pedidos del producto viven en
`producto.extra.pruebas|pedidos` (`tiendas.EXTRA_INTERNO` los protege de la sync; único escritor
`doctrina/producto.py` vía `tiendas.modificar_extra_interno`, con lock): las pruebas entran a los DATOS de ideas,
guion, «Adaptar» y captions y cuentan como dato verificado; «Actualizar lo que Claude necesita» (tarea
`producto_pedidos`, `doctrina/pedidos.py`, gasto `pedidos`) junta los faltantes de las ideas y sesiones del producto
y los resume en máximo cinco pedidos; responder uno lo guarda como prueba. Página de solo lectura
`/cliente/<cliente>/doctrina` (`doctrina/pagina.py::a_html` escapa antes de convertir). Las plantillas reciben el
vocabulario con `doctrina.globales_plantilla()`.

**Doctrina, bloque 3: el revisor de la pieza terminada** (spec
`docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md`): `doctrina/revisor.py` contesta la lista de
`textos/revisar.md` (12 puntos; `PUNTOS`/`PUNTO` traen la rebanada del «¿Por qué?») sobre una pieza de Crear terminada.
Dos capas. `reglas(datos)`: pura y gratis, se calcula al renderizar (gancho largo, arranque fuera de la consciencia,
promesa múltiple, sin mecanismo con sofisticación ≥ 3 —la fija del producto manda—, cifras del caption que no están en
los datos verificables de `reunir()`, guion sin CTA, gancho de la idea distinto del ángulo). `revisar(cliente, cf_id)`:
Claude con visión, fotogramas de `tiempos()` (0,3 s, uno cada 3 s y el final; máximo 8) precedidos de «Segundo N:», los
DATOS de `reunir()` y la rebanada `revisar`; una corrección; `ErrorRevision` lleva los tokens pagados. Se guarda en
`concepto.extra.revision_doctrina` con el `video_url` revisado (`estado_revision` la marca «vieja» si el video cambió;
`duplicar` no la copia). Botón «Revisar con la doctrina» en el detalle de Crear (`cf_revisar` → tarea `pieza_revisar`,
`max_intentos=1`, gasto tipo `revision`, tarifa `revision_pieza`), macro `templates/_revision_doctrina.html`, barra de
progreso en la tarjeta. El QA de Sprints (`sprints/qa.py`) pide los 12 puntos en la misma llamada (rebanada `revisar`
en el system, mismos fotogramas, tope 6 000), por fin registra su gasto real (tipo `revision`, referencia
`qa:<cp_id>:t<tarea>:i<intento>`) y guarda la revisión en la sesión (`origen: sprint`). La galería de Experimentos
(`elegibles()["doctrina"]`, aviso en el paso 3) y la revisión del lote muestran la etiqueta con `resumen_galeria`,
leyendo solo `concepto.extra`. Nada de esto bloquea ni reescribe.

**Doctrina, bloque 4: cerrar el ciclo** (spec
`docs/superpowers/specs/2026-09-28-doctrina-bloque-4-cerrar-el-ciclo-design.md`): lo que el motor aprende de cada prueba
vuelve a la siguiente pieza. (1) **Diagnóstico de una perdedora** (`doctrina/diagnostico.py`; rebanada `diagnosticar` =
la lista de Theriot: `CAUSAS_PERDIDA` (ocho causas, `CAUSAS_NOMBRE` con `N_`), `CAUSAS_NO_CREATIVAS` = landing,
estacionalidad, posicionamiento, `SIGUIENTES_PASOS`/`SIGUIENTES_NOMBRE`): `exp_decidir` pide la pausa primero (el anuncio deja de gastar
aunque Claude tarde) y después diagnostica cada `perdedor` nuevo en `_diagnosticar` (timeout 120 s, un reintento;
una final variada se diagnostica con SU guion) — `pistas()` (puras y gratis: ThruPlay bajo el mínimo → gancho; CTR bajo con retención → sin_urgencia;
puerta 2 → landing; frecuencia ≥ 3 → repetición; CPC alto con CTR normal → subasta_cara) y una llamada a Claude con los
DATOS (veredicto y números, ángulo, revisión de la doctrina, guion base, producto; una corrección; `ErrorDiagnostico`
lleva los tokens pagados; `idioma=` del proyecto). Se guarda en `experimento_pieza.extra.diagnostico`
(`{version, causas, siguiente, aprendizaje, pistas, modelo, usd, en}` o `{error, pistas, en}`), gasto tipo `revision`,
tarifa `diagnostico_pieza`, referencia `diagnostico:<ep_id>:t<tarea>` (también con respuesta inválida), evento
`diagnostico`; nunca frena el veredicto. (2) **El diagnóstico guía el rescate** (`decision_rescate`): `siguiente`
estructura/regenerar → `payload.salto` 2/3 (`derivaciones._planificar_rescatar` toma `max(escalón siguiente, salto)`:
nunca vuelve atrás; `acciones._precio_estimado` cobra el escalón real) y oferta/landing/pausar, o causa principal no
creativa, → `payload.solo_proponer` (`acciones.pedir` deja `propuesta` en todo modo, con el diagnóstico en el motivo).
`derivar` hace todas las re-ediciones de gancho (ya no alterna hook/estructura) con `contexto_variante =
{lead_objetivo (el k-ésimo arranque recomendado que no sea el actual ni uno ya probado por una final de la sesión;
None cuando no queda ninguno: la variante cambia el patrón del gancho), hermana {k, n} cuando se producen varias a
la vez, ganchos_usados (el del ángulo de la sesión + `capas.guion.parametros.angulo.gancho` de cada final)}`; el
rescate suma `diagnostico` (causas + siguiente) y excluye el arranque de la pieza que perdió. Los aprendizajes NO se
guardan en el experimento: `_opciones_de(item, cliente)` los agrega al encolar. `variar_guion(..., angulo=,
contexto=)` lo escribe en el mensaje (`_contexto_variante_texto`, ganchos y aprendizajes entre etiquetas) — también
en `final_edition/produccion.py`, que antes variaba sin ángulo y que ahora guarda el `angulo_variante` en
`capas.guion.parametros.angulo` como el legado (también para los destinos que reutilizan el borrador). (3) **Aprendizajes por proyecto** (`doctrina/aprendizajes.py`;
`proyecto.json["aprendizajes"]` vía `proyectos.aprendizajes/agregar_aprendizaje/quitar_aprendizaje`, tope 40, los más
nuevos primero): una línea por ganador o perdedor (`desde_veredicto`: «Ganó en CO: «gancho» (arranque X, audiencia Y)
para P — CTR 2,1 %, ThruPlay 34 %.» / «Perdió en …: … — motivo. Diagnóstico: …»; gettext, así que sale en el idioma
del proyecto) o escrita a mano (sección «Aprendizajes del proyecto» al final de Experimentos, `_aprendizajes.html`,
rutas `apr_agregar`/`apr_quitar`). `texto_para_prompt(lista, producto=)` (los del mismo producto primero, 10, entre `<aprendizajes>`) entra
como DATOS en las ideas de sprint (`contexto_campana["aprendizajes"]`; las cifras del ángulo se verifican contra
los DATOS SIN aprendizajes), en el guion base (`generar_guion_base(aprendizajes=)`) y en las variantes. La línea
del motor cabe en 650 caracteres con la frase del diagnóstico entera (`MAX_TEXTO_MOTOR`); a mano, 300. (4) UI: bajo un veredicto `perdedor` la fila de la pieza
muestra las causas (`CAUSAS_NOMBRE|traducir`, `title` = detalle y evidencia), «Siguiente: …» y «¿Por qué?» →
`#diagnosticar` de la página de la doctrina; con error, el motivo. (5) Flow Plus: `guiones/clips.py`, `recorte.py`,
`imagenes.py` y `refinador.py` arman su system con `doctrina.bloque_system(*COMBINACIONES["flowplus_*"], extra=,
idioma=)` (clips y refinador `video`+`gancho`, recorte `gancho`, imágenes solo la base; la lectura no lleva doctrina) y
`guiones.claude.tokens_entrada_equivalentes` suma la caché al gasto (1,25× escribir, 0,1× leer) en `llamar` y en la
llamada directa del refinador. Límites: un diagnóstico por veredicto; nada se aplica solo salvo lo que el modo ya
ejecutaba; sin migraciones (todo vive en `extra` y en `proyecto.json`). Con esto los cuatro bloques del spec original
(§14) están en `main`.

**Rendimiento y almacenamiento (auditoría 2026-09-28, tras el incidente de la página que se
quedaba cargando):** `/cliente/<c>` trae todas las pestañas en un solo HTML (3 MB en happyflops:
Crear, Final edition y Experimentos repiten las mismas piezas con sus `<template>` de detalle), así
que lo que se agrega ahí le cuesta a TODAS las cargas. Reglas que salieron de la auditoría: los
`<video>` de listas nacen `preload="none" data-precarga` (base.html los pide al entrar en pantalla;
`tests/test_referentes_copycoders_proyecto.py` rechaza `preload="metadata"`) y las `<img>` van
`loading="lazy"`; las fotos del catálogo se piden con `?w=320` (`catalogo_productos.miniatura`,
Pillow, caché en `data/miniaturas/`); nada de una consulta por tarjeta: `ver_cliente` corre bajo
`trabajos.con_vivos_precargados` (UNA lectura de los job_ids vivos para todos los `en_curso`) y la
lista de Crear usa `creative_flow.guiones_base`/`finales_por_sesion` y
`doctrina.revisor.ultimos_captions` (`tests/test_perf_pagina_proyecto.py` falla si el número de
consultas vuelve a crecer con las piezas); `informe.completo` solo se arma para el admin; los
estáticos con `?v=` salen `immutable` un año (`/static/editor/` sigue `no-cache`); la biblioteca de
copycoders está apagada por proyecto hasta que la persona la trae (`proyectos.referentes_copycoders`).
Mantenimiento diario en el worker (`tareas/mantenimiento.py`): `salidas_limpiar` borra de `salidas/`
lo que tenga más de 14 días (todo lo de ahí es copia de trabajo: el video vive en R2 y
`publicador.archivo_local`, `final_edition._clon_local`, `materiales.descargar` y `sprints.qa`
lo vuelven a bajar), `cola_limpiar` purga las `tarea` cerradas (7 días; periódicas, 1 día) y
`db_respaldar` guarda `data/respaldos/creatv_<fecha>.db` (`Connection.backup`, 7 copias). Sigue
pendiente (no se hizo): borrar en R2 lo rechazado/descartado y las versiones viejas de finales,
`materiales_limpiar` no borra nada porque los proxies viven en la fila del video (no son `EFIMEROS`),
`metrica_snapshot` inserta cada 2 h aunque nada cambie.
**Tarjetas ligeras y detalle bajo demanda** (spec
`docs/superpowers/specs/2026-09-28-tarjetas-ligeras-detalle-bajo-demanda-design.md`): el 61 % de
la página eran los `<template class="generado-detalle">` de Crear y Final edition (1,86 MB de 3,03).
Ya no existen: las tarjetas son macros (`_crear_tarjetas.html`: `tarjeta_crear`/`lista_crear`;
`_final_tarjetas.html`: `tarjeta_video_fe`/`tarjeta_final_fe`/`lista_videos_fe`/`lista_finales_fe`),
la página pinta las 24 más recientes por lista (`TARJETAS_POR_PAGINA`, `_listas_crear_final`; los
contadores muestran el total) y «Ver más» pide las siguientes a `crear_tarjetas` /
`final_tarjetas?lista=videos|finales` (`?desde=N`, `_pagina_desde`). El detalle llega por fetch al
abrir la tarjeta (`data-detalle` → `cf_detalle`, `fe_detalle_video`, `fe_detalle_final`; macros en
`_crear_detalle.html` / `_final_detalle.html`, armadas con `_creative_flow_item(cliente, cf_id)` y
`_contexto_final_edition(cliente)`, que incluye `_contexto_organico`), nunca se cachea, y
`base.html` lo pinta con `abrirDetalleRemoto(modal, cuerpo, url, alInsertar)` («Cargando…» al
instante, solo el último pedido gana). `#final?cf=<id>` abre la pieza aunque no esté pintada.
Reglas: **ninguna barra de progreso lleva `<script>`** — todas `data-poll-job="<job_id>"` sobre el
`div.barra-progreso#trabajo-<job_id>` y `arrancarSondeos(raiz)` (DOMContentLoaded + el
MutationObserver de `data-precarga`) arranca el sondeo de lo que aparezca; los clics de tarjetas
van delegados sobre la cuadrícula (las agregadas por «Ver más» funcionan igual); el sondeo se pausa
con `document.hidden` y baja de ritmo (`intervaloSondeo`: 1,5 s → 3 s al minuto → 5 s a los 5 min).
`tests/test_tarjetas_ligeras.py` y `test_perf_pagina_proyecto.py` vigilan todo esto. Fuera de
alcance (anotado en el spec §7): el JS embebido a estáticos, Experimentos por fragmentos (Catálogo
ya carga su galería y su ficha por fragmento desde 2026-09-30: ver «Catálogo ecommerce y
conectores»), el chequeo de Meta en la carga, los N+1 de Sprints/Experimentos, el flujo viejo
«Nueva idea».

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
