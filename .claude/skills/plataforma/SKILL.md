---
name: plataforma
description: "Plataforma de Creatv por dentro: carpetas por proyecto (clientes/<cliente>/), estado en JSON y en data/creatv.db, trabajos en segundo plano y el worker (trabajos.encolar, cola, carriles, job_id, Continuar, hilos), R2, el gasto real (gastos.registrar_seguro, gastos.estimar), el wrapper viejo de Higgsfield y el flujo viejo «Nueva idea». Cargar antes de crear o cambiar una tarea del worker, tocar trabajos.py, cola.py, worker.py, gastos.py, _json_store.py o estado.py, o agregar algo que cobre a un proveedor."
---

# Plataforma: proyectos, estado, trabajos en segundo plano y gasto

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

## El principio y el flujo viejo «Nueva idea»

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

**Prompt generation** (`generador_prompts.py`): calls Anthropic directly (not through
Higgsfield). `generar_prompts()` writes the 5 candidate prompts and folds in a
client's `marca.json` guía de estilo when present, so brand consistency doesn't have
to be repeated per idea. `analizar_marca()` uses Claude's vision input on uploaded
brand reference images to auto-write that guía de estilo.

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

**Cobros recuperados (2026-10-02, PND-109):** la identidad y la referencia del cobro original viajan en la predicción; una recuperación conserva ese id de tarea. Un gasto nuevo de música pertenece a la tarea que la obtuvo. Ver la regla de recuperación de `crear`.

PND-040/042 (2026-10-03): migración 0031 reconstruye material con AUTOINCREMENT conservando filas e ids. Todos los escritores de proyectos.py toman flock de proyecto.json.lock antes de leer; el idioma usa actualizar_campos y comparte el candado. Las escrituras rechazan un JSON ilegible en vez de sobrescribir ajustes. El generador de fixtures rendimiento/sembrar.py sigue siendo una inicialización fuera del flujo concurrente de producción.

PND-125 (2026-10-05): el cierre de Crear registra el video inmediatamente tras descargarlo, antes de la bitácora/mezcla, y la pista apenas recibe su costo, antes de mezclar; el registro final mantiene referencias idempotentes; _registrar_gasto activa conservar_mayor en gastos.registrar_seguro. La condición SQL impide que una recuperación con música de caché reduzca un cobro original con música; las recuperaciones que pagan una pista nueva conservan su referencia de tarea separada.

Revisión de Codex, 2026-10-05, lote 4: conservar_mayor se vigila también en la carrera IntegrityError con SQLite real. Describir referencias y sugerir sonido anotan bajo _creatv el cliente solicitante en extra.cliente. PND-144/145 registran los huecos aún abiertos de pista fallida e imagen cuyo error no se pudo persistir.

PND-144/145 (Codex, 2026-10-07): la imagen registra antes de escribir bitácora/error. Una pista fallida después de generar lleva costo_usd y URL en PistaPagadaError; Crear la registra con la referencia de tarea existente (o :musica de recuperación), conservando el video. No implica recuperación automática ni cubre SIGKILL antes del registro.

PND-072/088 (2026-10-07, lote 5 B): el encolado del director vive en tareas.director.encolar, conserva max_intentos=1 y prioridad del llamador. Una reserva perdida en sprints.produccion.crear_sesion archiva exclusivamente el concepto recién creado; no borra piezas ni la reserva de otro lote. La política de Repetir QA sigue pendiente (no se modifica cuándo cobra).

PND-144 (correcciones de lote 5, 2026-10-08): la referencia :musica de recuperación lleva proveedor fal explícito. Las pruebas provocan PistaPagadaError y fallo de bitácora juntos: generación y recuperación conservan US$ 0,82 sin duplicar la fila de pista. No se amplía la lógica de cobro en esta corrección.
