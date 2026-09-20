# Meta en modo agencia (multi-cliente) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Dos modos de conexión con Meta por proyecto, elegidos por el admin: **propia** (lo de hoy: el cliente registra su app y conecta él — ADR 0001) y **agencia** (nuevo: el admin conecta UNA vez el Business Manager de Creatv con un token de usuario del sistema, y a cada proyecto le asigna una cuenta publicitaria y una Página de las que ese Business ve como propias o de clientes socios). Todo lo que ya usa `meta_conexion.cargar/credenciales_ads/estado/estado_pixel` y `uploaders/meta_uploader._credenciales` sigue funcionando sin cambios en el modo agencia. Decisión del dueño 2026-09-20 (chat): "las dos".

**Architecture:** `meta_agencia.py` guarda la conexión de agencia cifrada (Fernet con `FLASK_SECRET_KEY`, `cifrado.py`) en la tabla `kv` (clave `meta_agencia`): `{business_id, business_nombre, token (usuario del sistema), conectado_en, app_id?}`; valida contra Graph (`/me`, `/{business_id}?fields=name`) y lista activos (`/{business_id}/owned_ad_accounts` + `client_ad_accounts`, `/{business_id}/owned_pages` + `client_pages` con `instagram_business_account`); resuelve el token de Página (`/{page_id}?fields=access_token`) al asignar. El proyecto en modo agencia guarda en `clientes/<c>/meta.json`: `{modo: "agencia", ad_account_id, ad_account_nombre, page_id, page_nombre, ig_user_id, ig_username, moneda, page_access_token, asignado_en, asignado_por}` — **sin** token de usuario; `meta_conexion.cargar(cliente)` inyecta `token` desde la agencia cuando `modo == "agencia"` (y `estado()` chequea el token de agencia). Un solo cambio en el módulo de conexión; el resto del sistema no distingue modos.

**Spec:** ADR 0001 se complementa con **ADR 0002** ("modo agencia": una credencial de agencia solo opera activos que el cliente concedió como socio en Business Manager, o que la agencia posee; cada proyecto puede volver a modo propio en un clic).

## Global Constraints
- El token de agencia nunca sale de `meta_agencia` en claro: cifrado en `kv`, jamás en logs/flashes/eventos/plantillas; `_detalle`/`app_publica`/`estado` no lo exponen. Solo rutas `@requiere_admin` lo escriben o lo leen para mostrar activos.
- Un proyecto está en un modo a la vez. Pasar a *agencia* borra el `token` propio de `meta.json` (conservando `modo_anterior` y sus ids) y viceversa; los experimentos ya lanzados conservan sus ids de Meta (campaña/adset/ad) y siguen funcionando si la nueva credencial ve la misma cuenta publicitaria; si la cuenta asignada cambia, se avisa "los experimentos anteriores dejan de refrescarse".
- Sin `FLASK_SECRET_KEY` no se puede conectar la agencia (mismo criterio que tiendas).
- Cliente (rol cliente) en modo agencia ve "Gestionado por Creatv" y no puede cambiar de modo ni ver activos del Business; el guard de correo verificado no aplica en modo agencia (no conecta nada él).
- Copy en español; suite verde sin red (Graph fake).

---

### Task 1: `meta_agencia.py` + integración en `meta_conexion`

**Files:** `meta_agencia.py`, `meta_conexion.py`, `cifrado.py` (reusar), tests `tests/test_meta_agencia.py`.

**Interfaces:**
- `meta_agencia.conectada() -> bool`; `meta_agencia.conectar(token, business_id) -> dict publico` (valida `/me?fields=id,name` y `/{business_id}?fields=id,name`; guarda cifrado; devuelve `{business_id, business_nombre, usuario_nombre, conectado_en}`); `meta_agencia.desconectar()`; `meta_agencia.publica() -> dict|None` (sin token); `meta_agencia.token() -> str` (levanta `MetaAgenciaError` si no hay); `meta_agencia.listar_activos(forzar=False) -> {"ad_accounts": [{id, name, currency, account_status, origen: propia|cliente}], "pages": [{id, name, ig_user_id, ig_username, origen}]}` cacheado 10 min; `meta_agencia.asignar(cliente, ad_account_id, page_id=None, asignado_por=None) -> dict detalle` (busca los activos en la lista, obtiene `page_access_token` vía `/{page_id}?fields=access_token,instagram_business_account`, escribe `meta.json` con `modo="agencia"` y `modo_anterior` + datos propios previos en `propia_respaldo`, invalida caches); `meta_agencia.desasignar(cliente)` (vuelve a `modo="propia"` restaurando `propia_respaldo` si existía); `meta_agencia.proyectos_asignados() -> {cliente: detalle}` (recorre `estado_mod.listar_clientes()`); `meta_agencia.estado() -> {"estado": sin_conectar|conectada|rota, "detalle", "motivo"}` cacheado como `meta_conexion.estado`.
- `meta_conexion.cargar(cliente)`: si `datos.get("modo") == "agencia"` → devuelve copia con `token = meta_agencia.token()` (si la agencia no está conectada, sin token → `estado` = `roto` con motivo "La agencia no está conectada"). `meta_conexion.modo(cliente) -> "propia"|"agencia"`. `estado()`/`_detalle` incluyen `modo`. `revocar`/`borrar` en modo agencia solo desasignan (no tocan la agencia). `url_dialogo`/`meta_app_*` rechazan (ValueError en español) cuando el proyecto está en modo agencia.
- `uploaders/meta_uploader._credenciales` no cambia (lee `page_access_token`/`page_id`/`ig_user_id` del `meta.json`, que el modo agencia rellena).

- [ ] Tests (Graph fake por monkeypatch de `meta_conexion._graph_get`; tmp client dir; `FLASK_SECRET_KEY` fake): conectar/validar/desconectar, token cifrado en kv (no aparece en claro), listar_activos con origen propia/cliente y caché, asignar escribe meta.json sin token de usuario y con page_access_token, `cargar` inyecta el token, `credenciales_ads` funciona, `estado` conectado/roto (agencia desconectada), desasignar restaura propia, `url_dialogo` rechaza en agencia, `estado_pixel` funciona con token de agencia (fake).
- [ ] Commit `"Meta agencia: conexión del Business de Creatv cifrada, activos, asignación por proyecto y modo en meta_conexion"`.

### Task 2: Panel admin + Configuración del proyecto

**Files:** `dashboard.py`, `templates/panel.html` (o nuevo `panel_meta.html`), `templates/_meta_conectar.html`, `templates/_tab_settings.html`, `static/style.css`, tests `tests/test_rutas_meta_agencia.py`.

- Rutas admin (`@requiere_admin`, POST con `_mismo_origen` check): `GET /admin/meta` (página: estado de la agencia, form conectar (token + business id; ayuda paso a paso: Business Manager › Configuración del negocio › Usuarios › Usuarios del sistema › crear "creatv" admin › asignar activos › generar token con `ads_management, ads_read, business_management, pages_read_engagement, pages_manage_posts, pages_manage_ads, instagram_basic, instagram_content_publish` (los que la app tenga)), lista de activos con "Actualizar", tabla de proyectos con modo y asignación (select cuenta + select página → "Asignar"; "Volver a propia")); `POST /admin/meta/conectar`, `POST /admin/meta/desconectar` (confirm; avisa cuántos proyectos quedan sin conexión), `POST /admin/meta/asignar/<cliente>`, `POST /admin/meta/desasignar/<cliente>`, `POST /admin/meta/activos/actualizar`. Enlace desde `panel.html` ("Meta (agencia)").
- `_meta_conectar.html`: si `modo == "agencia"` → tarjeta "Gestionado por Creatv: cuenta X · Página Y" (+ IG) sin botones de app/conectar; para admin, enlace a `/admin/meta`. En modo propia igual que hoy.
- `_estado_llaves` tarjeta Meta: "configurada" también cuando la agencia está conectada y el proyecto asignado; texto según modo.
- Guard `_requiere_correo_verificado` no aplica a rutas de agencia (son admin).
- [ ] Tests: rutas admin-only (cliente → 302/403); conectar con Graph fake OK/fail (fail → nada guardado, flash sin token); asignar/desasignar; proyecto asignado renderiza "Gestionado por Creatv" y no "Conectar con Meta"; `meta_conectar` en modo agencia → flash; panel enlace; no token in any HTML.
- [ ] Verificación manual; commit `"Meta agencia: panel de admin (conectar Business, activos, asignar por proyecto) y vista del proyecto"`.

### Task 3: ADR + docs
- [ ] `docs/adr/0002-meta-modo-agencia.md` (contexto, decisión, consecuencias, relación con 0001); `CLAUDE.md` (reescribir el párrafo "Never reintroduce a global Meta credential" → los dos modos y la regla); `SETUP.md` (cómo conectar la agencia; requisitos: app de agencia con Advanced Access + verificación de negocio; mientras esté en desarrollo solo cuentas de prueba/roles de la app). Commit `"Docs: Meta en modo agencia (ADR 0002)"`.
