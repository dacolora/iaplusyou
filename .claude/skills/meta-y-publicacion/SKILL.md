---
name: meta-y-publicacion
description: "Conexión con Meta (modo propia y agencia, la forma que elige el cliente) y publicación en YouTube, Facebook, Instagram y TikTok, incluida la publicación orgánica de una pieza ganadora. Cargar antes de tocar meta_conexion.py, meta_agencia.py, publicador.py, uploaders/, organico.py, tareas/organico.py o auth/."
---

# Conexión con Meta y publicación

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

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
`clientes/<cliente>/meta.json` (also git-ignored, 0600). Don't confuse `meta_app.json` (the app used for **login**) with `meta_app_anunciada.json` (the App ID of the app a project *advertises* in App installs experiments; see the `experimentos` skill). There is no Meta credential in the
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

**Candado común (2026-10-02, PND-114):** la ruta legado `cambiar_estado_ad` opera campaña, conjunto y anuncio mediante `lanzador._con_credenciales`, con `tareas.meta._LOCK`; `_ENV_LOCK` queda para el entorno del flujo viejo, no para configurar las credenciales globales de Meta.

PND-036 (2026-10-03): organico.crear rechaza tipo imagen antes de insertar una publicación; protege también un POST manual. PND-113: la primera activación del lanzador ajusta end_time antes de activar; se conserva el presupuesto y nunca se activa por actualizar fechas. Ver experimentos para reintentos y reanudación.

**Error del legado (2026-10-07, PND-096):** la tarea `meta_publicar` sigue registrada para filas antiguas.
Su subcódigo 1885183/modo Desarrollo tiene mensaje propio por gettext, separado de permisos (#3), sin prometer
reutilización que ese camino no implementa. `tests/test_tareas_meta.py` provoca el rechazo con dobles; no cambia
la publicación ni los reintentos.

**Conexión «solo métricas» (2026-10-08, Meta rendimiento E1):** en modo propia, `meta_elegir` acepta una cuenta publicitaria
SIN Página (`page_id` vacío o ausente; la opción «Sin Página (solo métricas)» va al final de la lista, marcada solo si no
hay Páginas). `meta.json` queda con `page_id`, `page_nombre`, `page_access_token`, `ig_user_id` e `ig_username` en `None`;
`organico.py` y `uploaders/meta_uploader.py` ya tratan eso como «sin Página». Lanzar y publicar frenan en palabras ANTES de
llamar a Meta con `meta_conexion.sin_pagina(cliente)` (exige token, para no confundirlo con «sin conexión»; el texto es
`error_solo_metricas(cliente)`, que en modo agencia manda al admin de Creatv): `lanzador._validar_para_lanzar`,
`lanzador.lanzar_piezas_nuevas`, las rutas `exp_lanzar` y `exp_probar` (antes de crear o encolar nada) y la tarea legado
`meta_publicar`. Leer métricas (`meta_refrescar`, la copia de `meta_rendimiento/`, skill `meta-rendimiento`) no
necesita Página y no se frena. La tarjeta de Configuración › Conexiones muestra «Solo métricas» con un enlace a `#meta`.
