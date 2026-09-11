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
python dashboard.py    # http://127.0.0.1:5050
```

`ffmpeg` must be installed on the system (`brew install ffmpeg`) — used to extract a
still frame from uploaded video assets, since Higgsfield's APIs need a static image
reference, never a video.

There is no test suite and no linter configured. `python3 -m py_compile <file>.py` is
the only sanity check currently used before committing.

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
state for a client.

**Background jobs** (`trabajos.py`): every slow action (image gen, video gen, brand
analysis, publish) is launched via `trabajos.iniciar(job_id, fn, duracion_estimada)`
on a daemon thread instead of blocking the request. The Flask route returns almost
instantly; the browser polls `/trabajo/<job_id>/estado` (JSON) and renders a progress
bar via the shared `iniciarPolling()` JS in `base.html`, reloading the page on
completion. `job_id` is deterministic per (cliente, prompt_id/brief_id, acción) —
`trabajos.iniciar` no-ops if that job is already running, which is the anti-double-
click guard. **`dashboard.py` runs with `use_reloader=False` on purpose**: Flask's
auto-reloader kills the whole process on file changes, which would silently abort
any in-flight background generation.

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
`uploaders/tiktok_uploader.py` (Content Posting API). YouTube and TikTok need a one-time OAuth authorization done locally (`auth/auth_youtube.py`,
`auth/auth_tiktok.py` — each opens a local browser + localhost callback server, so these
cannot run on a remote/deployed server; tokens must be generated locally and copied over).
Meta is different: the client connects their own account from the dashboard
(FlowMarketing › "Conectar con Meta", routes in `dashboard.py`, logic in `meta_conexion.py`),
and the credentials live in `clientes/<cliente>/meta.json` (git-ignored, 0600). `meta_ads/`
receives them via `auth.configurar(...)` — the submodule never reads the environment.

**Prompt generation** (`generador_prompts.py`): calls Anthropic directly (not through
Higgsfield). `generar_prompts()` writes the 5 candidate prompts and folds in a
client's `marca.json` guía de estilo when present, so brand consistency doesn't have
to be repeated per idea. `analizar_marca()` uses Claude's vision input on uploaded
brand reference images to auto-write that guía de estilo.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
