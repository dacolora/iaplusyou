# Motor — Bloque 7: publicación orgánica del ganador — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Que la pieza ganadora de un experimento (o cualquier final que la persona elija) se publique como contenido orgánico en Instagram Reels, Facebook (Página), TikTok y YouTube Shorts, con un texto escrito por la IA a partir del guion y editable, respetando el modo del experimento (manual/semi → propuesta; auto → solo), guardando cada publicación (plataforma, URL, estado) y mostrándola en Experimentos, Tablero y Configuración › Canales orgánicos.

**Architecture:** tabla `publicacion` (0008) + `organico.py` (canales disponibles por proyecto, redacción del caption con Claude, `publicar(cliente, pieza_id, plataformas, captions)` que descarga el mp4 y llama a `publicador._publicar_una` por plataforma guardando el resultado) + tarea del worker `organico_publicar` (`max_intentos=1`) + acción `publicar_organico` en `modos`/`acciones`/`tareas.experimentos.exp_decidir` (ganador → propuesta o ejecución según modo) + rutas `org_*` + UI (botón en piezas de Experimentos, propuesta con texto editable, sección en Configuración, tarjetas en Tablero).

**Tech Stack:** Flask/Jinja, SQLAlchemy Core + Alembic, worker/cola, `publicador.py` + `uploaders/` existentes (Graph API, YouTube Data API, TikTok Content Posting), Anthropic (caption).

**Spec:** decisión del dueño 2026-09-18 (chat) sobre el diseño presentado; spec §9 "publicación orgánica del ganador" estaba fuera de la v1.

## Global Constraints
- Publicar es público e irreversible: nunca se publica sin clic salvo en modo `auto`; en `manual` y `semi` es una `propuesta` con el texto ya redactado y editable. Nunca se publica dos veces la misma pieza en la misma plataforma (unicidad `(cliente, pieza_id, plataforma)` mientras `estado in (en_cola, publicando, publicada)`).
- Los uploaders existentes no cambian de firma; `organico.publicar` los llama por plataforma, captura excepciones por plataforma (una falla no frena las demás) y nunca escribe tokens en `error`/eventos (`cola.sin_token`).
- Caption por plataforma: Instagram/TikTok sin URLs (→ "link en bio"), Facebook/YouTube con `url_compra` si existe; ≤ 2 200 chars (IG), ≤ 2 200 (TikTok, título ≤ 150), YouTube título ≤ 100 + descripción; hashtags 3–8; sin emojis excesivos; en el idioma de la pieza.
- Canales disponibles: `facebook` si `meta_conexion.cargar(cliente)` tiene `page_access_token` y `page_id`; `instagram` si además `ig_user_id`; `youtube` si existe `clientes/<c>/token_youtube.json`; `tiktok` si existe `clientes/<c>/token_tiktok.json`. La UI solo ofrece los disponibles y explica cómo activar los demás.
- Tarea `organico_publicar` con `max_intentos=1` y hook `al_interrumpir` (publicación `publicando` → `error`). El mp4 se descarga a `salidas/<c>/organico/<pieza_id>.mp4` y se borra al terminar.
- Copy en español; suite verde sin red (uploaders y Claude fakes por monkeypatch).

---

### Task 1: Migración 0008 + `organico.py` (datos, canales, caption)

**Files:** `migrations/versions/0008_publicacion.py`, `db.py`, `organico.py`, `generador_prompts.py` (`caption_organico`), tests `tests/test_organico.py`.

**Interfaces:**
- Tabla `publicacion`: `id, cliente, creado_en, actualizado_en, pieza_id FK pieza, experimento_pieza_id FK nullable, plataforma (facebook|instagram|youtube|tiktok), estado (en_cola|publicando|publicada|error), caption Text, titulo String(150), id_externo String(120), url String(500), error Text, publicado_en String(19), origen (manual|ganador), extra JSON`; índice `(cliente, pieza_id)`.
- `organico.PLATAFORMAS = {"instagram": {"nombre": "Instagram Reels", "links": False, "max_caption": 2200}, "facebook": {"nombre": "Facebook (Página)", "links": True, "max_caption": 5000}, "tiktok": {"nombre": "TikTok", "links": False, "max_caption": 2200, "max_titulo": 150}, "youtube": {"nombre": "YouTube Shorts", "links": True, "max_caption": 5000, "max_titulo": 100}}`.
- `organico.canales(cliente) -> [{"plataforma", "nombre", "disponible": bool, "motivo": str}]` (motivo en español cuando no disponible: "Conecta Meta con una Página", "La cuenta de Instagram no está vinculada a la Página", "Falta token_youtube.json (autoriza desde tu Mac con auth/auth_youtube.py)", "Falta token_tiktok.json…").
- `organico.redactar(cliente, pieza_id, plataformas) -> {plataforma: {"titulo", "caption"}}`: contexto = guion de la pieza (final: `pieza.guion`; clon: `concepto.extra.accion_central`), producto (`tiendas.por_activo` / nombre), `url_compra`, idioma; una llamada a Claude (`generador_prompts.caption_organico(contexto, plataformas) -> dict`) que devuelve JSON por plataforma; fallback determinista sin Claude (hook + CTA + 3 hashtags del nombre) si falla; recorta a los máximos; quita URLs en plataformas `links=False` y agrega "Link en bio".
- `organico.crear(cliente, pieza_id, plataforma, caption, titulo=None, origen="manual", ep_id=None) -> id` (rechaza duplicado vivo con `ValueError`), `organico.actualizar(cliente, pub_id, **campos)`, `organico.listar(cliente, pieza_id=None, ep_id=None) -> list`, `organico.por_pieza(cliente) -> {pieza_id: [pubs]}`, `organico.ganadoras_sin_publicar(cliente) -> [ep dicts]` (veredicto ganador y sin publicación `publicada` en ninguna plataforma disponible).
- `organico.publicar(cliente, pub_ids, on_etapa=None) -> {"ok": [...], "error": [...]}`: por publicación: `estado=publicando` → descarga el mp4 (una vez por pieza) → `publicador._publicar_una(plataforma, entry, cliente, token_paths)` con `entry={"video_local", "video_url", "title", "caption", "platforms":[p]}` — para capturar `id_externo`/`url` cambiar `_publicar_una` para que DEVUELVA el id que devuelve cada uploader (aditivo) y construir la URL (`https://www.facebook.com/{id}`, `https://www.instagram.com/reel/{shortcode}` si el uploader lo da, `https://youtu.be/{id}`, TikTok: `publish_id`) → `publicada` + `publicado_en`; excepción → `error` con `sin_token`; evento en el experimento si `ep_id`; borra el mp4 al final.

- [ ] Tests: migración up/down; canales según meta.json/tokens fake (tmp client dir); `redactar` con Claude fake y fallback, sin URLs en IG/TikTok, recortes; crear/duplicado; `publicar` con `publicador._publicar_una` fake (ok en una plataforma, excepción en otra → estados y sin token en error); `ganadoras_sin_publicar`.
- [ ] Commit `"Orgánico: tabla publicacion, canales disponibles, caption con IA y publicación por plataforma"`.

### Task 2: Acción del motor + tarea del worker

**Files:** `modos.py`, `acciones.py`, `propuestas.py` (dedupe por `pieza_id`+`plataformas`), `tareas/experimentos.py` (`exp_decidir`: ganador → `pedir("publicar_organico")`), `tareas/organico.py` (nuevo: `organico_publicar` {cliente, pub_ids}, `job_id_publicar(cliente, pieza_id)`), `tareas/__init__.py`, `notificaciones.py` (tipo `publicado`), tests `tests/test_modos_propuestas.py`, `tests/test_acciones.py`, `tests/test_tareas_decidir.py`, `tests/test_tareas_organico.py`.

- `modos.ACCIONES += ("publicar_organico",)`; tabla: manual → propuesta, semi → propuesta, auto → ejecutar.
- `acciones.ejecutar("publicar_organico", {ep_id, plataformas, captions?})`: si no hay `captions` → `organico.redactar`; crea una `publicacion` por plataforma disponible (origen `ganador`), encola `organico_publicar` (`max_intentos=1`, `etapas=[("Descargando", 15), ("Publicando", 85)]`); idempotente por `marcar_pieza(publicado_organico=True)` y por la unicidad viva. `acciones.pedir` con `publicar_organico`: en la propuesta guarda `payload={ep_id, plataformas, captions}` (los textos redactados ya, para que la persona los vea/edite).
- `exp_decidir`: tras `escalar_y_derivar` de un ganador, `pedir("publicar_organico", {ep_id, plataformas: disponibles})` solo si hay canales disponibles y la pieza no tiene publicación viva; aviso `ganador` ya existente menciona la propuesta.
- Tarea `organico_publicar`: `organico.publicar(cliente, pub_ids, on_etapa)`; `al_interrumpir` → publicaciones `publicando` → `error`; `notificaciones.avisar(tipo="publicado")` con las URLs.
- [ ] Tests con fakes; commit `"Orgánico: acción publicar_organico según modo, propuesta con texto, tarea del worker"`.

### Task 3: Rutas y UI

**Files:** `dashboard.py` (rutas `org_redactar` POST → JSON `{plataforma: {titulo, caption}}`; `org_publicar` POST {pieza_id|ep_id, plataformas[], caption_<p>, titulo_<p>} → crea + encola; `org_reintentar` (publicación en error → nueva cola); contexto `canales_org`, `publicaciones_por_pieza`, `trabajos_org`), `templates/_tab_experimentos.html` (en cada pieza con `url_video`: botón "Publicar orgánico" que abre un `<details>` con checkboxes de canales disponibles, botón "Escribir texto con IA" (fetch a `org_redactar`, rellena textareas), un textarea por plataforma, "Publicar"; lista de publicaciones de la pieza con badge/estado/URL/error/reintentar; en `_anuncios_sueltos` no), propuestas `publicar_organico` con los textos editables (prefijo `prop<id>_caption_<p>`) y "Aprobar" que manda los textos editados (`prop_aprobar` acepta overrides en el form → `payload["captions"]`), `templates/_tab_creativeflowplus.html` (en el detalle de una final `listo`: mismo botón "Publicar orgánico"), `templates/_tab_settings.html` (sección "Canales orgánicos" después de Pixel: estado por plataforma + pasos: Meta Página/Instagram vinculado + permiso `instagram_content_publish`; YouTube/TikTok: autorizar desde la Mac con `auth/auth_youtube.py` / `auth/auth_tiktok.py` y copiar `token_*.json` a `clientes/<c>/`), `templates/_tab_tablero.html` + `tablero.py` (tile "Ganadoras publicadas" + alerta `ganador sin publicar` nivel media → experimentos), `static/style.css`, tests `tests/test_rutas_organico.py`.
- [ ] Tests: canales en Configuración; `org_redactar` JSON con Claude fake; `org_publicar` crea publicaciones y encola con max_intentos=1; duplicado → flash; propuesta `publicar_organico` renderiza textos y aprobar con overrides usa el texto editado; cross-tenant.
- [ ] Verificación manual; commit `"Orgánico: publicar desde Experimentos y Crear, propuesta editable, canales en Configuración, tablero"`.

### Task 4: Docs y despliegue
- [ ] `CLAUDE.md` párrafo "Publicación orgánica"; `SETUP.md`: canales orgánicos (Meta Página + IG con `instagram_content_publish`, tokens de YouTube/TikTok por proyecto). Deploy: migración 0008, restart. Commit `"Docs: publicación orgánica"`.

## Autorevisión
Cobertura del diseño aprobado: plataformas IG/FB/TikTok/YouTube (T1), texto por IA editable (T1/T3), modos manual/semi → propuesta, auto → solo (T2), registro por publicación + Experimentos/Tablero/Configuración (T1/T3), reutiliza `publicador`/`uploaders` (T1), avisos IG permiso + OAuth local (T3 Configuración). Nombres: `organico.canales/redactar/crear/actualizar/listar/por_pieza/ganadoras_sin_publicar/publicar/PLATAFORMAS` (T1) ↔ T2/T3; `tareas.organico.job_id_publicar` (T2) ↔ T3; `modos` acción `publicar_organico` (T2) ↔ T3 propuestas. Riesgo: `_publicar_una` hoy no devuelve ids (cambio aditivo); Meta restringida impide probar FB/IG en prod.
