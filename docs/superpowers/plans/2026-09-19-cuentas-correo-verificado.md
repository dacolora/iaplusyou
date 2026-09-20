# Cuentas bien formadas: correo verificado, recuperar contraseña, cuenta — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Que cada usuario tenga un correo verificado, pueda recuperar su contraseña sin pedirle a nadie, y cambie correo/contraseña desde Configuración › Cuenta; el SMTP existente pasa a ser el correo de la plataforma (cuentas). Decisión del dueño 2026-09-19 (chat) — nada de avisos por WhatsApp; el correo se usa para cuentas.

**Architecture:** `usuarios.py` sigue siendo la fuente (usuarios.json) y gana `correo`, `correo_verificado`, `creado_en`; los tokens (verificación y restablecimiento) van a una tabla `token_cuenta` en SQLite (hash sha256 del token, tipo, usuario, correo, vence_en, usado_en, ip) con migración 0011 — así son de un solo uso y con vencimiento sin tocar el JSON en cada clic. `cuentas.py` concentra la lógica (crear token, validar, enviar correos con `notificaciones.enviar`, límites por hora en `kv`). Rutas: `/registro` (formulario dedicado; el de la portada lo llama), `/verificar/<token>`, `/reenviar-verificacion`, `/recuperar`, `/restablecer/<token>`, `/cuenta` (Configuración › Cuenta). Banner "Confirma tu correo" en `base.html` para sesiones sin verificar; guard: sin correo verificado no se puede conectar Meta ni tiendas (`meta_conectar`, `meta_app_guardar`, `tienda_conectar`, `tienda_meli_iniciar`).

**Tech Stack:** Flask/Jinja, `secrets`, `hashlib`, SQLAlchemy Core + Alembic, `notificaciones.enviar` (SMTP), werkzeug password hashing.

## Global Constraints
- Tokens: 32 bytes `secrets.token_urlsafe`, guardados como sha256; verificación vence a 24 h, restablecimiento a 1 h; un solo uso; al usar uno, se invalidan los demás del mismo tipo para ese usuario.
- Nunca revelar si un correo/usuario existe en `/recuperar` ni en `/reenviar-verificacion` (misma respuesta siempre).
- Límites: máximo 5 correos de verificación/recuperación por hora por correo y por IP (clave en `kv`, ventana deslizante simple con timestamps en JSON); al superar → mensaje "Espera un momento" sin enviar.
- Contraseña mínima 8 caracteres; cambiarla exige la actual; al restablecer se cierran las demás sesiones (bump de `session_version` en el usuario; el guard compara).
- Sin SMTP configurado: registro y recuperación no fallan; el registro deja el usuario `correo_verificado=False`, el banner dice "el servidor no tiene correo configurado; avisa al administrador", y el panel admin muestra la alerta; el admin puede marcar verificado a mano desde el panel.
- Usuarios existentes (sin correo): al entrar se les pide el correo una vez (formulario en el banner) y quedan sin verificar hasta confirmar; los admins no están obligados.
- Correos en español, texto plano + HTML simple, con el nombre del proyecto, sin tokens en logs. Copy en español; suite verde sin red (SMTP fake).

---

### Task 1: Datos — `usuarios` con correo, tabla `token_cuenta`, `cuentas.py`

**Files:** `usuarios.py`, `migrations/versions/0011_token_cuenta.py`, `db.py`, `cuentas.py`, tests `tests/test_cuentas.py`.

**Interfaces:**
- `usuarios.crear(usuario, password, rol, cliente=None, correo=None)`; `usuarios.actualizar(usuario, **campos)` (`correo`, `correo_verificado`, `password_hash` vía `cambiar_password`, `session_version`); `usuarios.por_correo(correo) -> (usuario, entry)|None` (comparación en minúsculas); `usuarios.cambiar_password(usuario, nueva)` (hash pbkdf2, `session_version += 1`); `usuarios.validar_password(p) -> str|None` (mensaje de error); `usuarios.validar_correo(c) -> str normalizado|None`.
- Tabla `token_cuenta`: `id, usuario, tipo (verificacion|restablecer), correo, token_hash (unique), creado_en, vence_en, usado_en, ip`.
- `cuentas.emitir(tipo, usuario, correo, ip=None) -> token_crudo` (invalida anteriores del mismo tipo); `cuentas.consumir(tipo, token_crudo) -> {"usuario","correo"}|None` (verifica hash, vencimiento, no usado; marca usado); `cuentas.limite_ok(clave, maximo=5, ventana_s=3600) -> bool`.
- `cuentas.enviar_verificacion(usuario, correo, url_base, ip=None) -> bool`; `cuentas.enviar_restablecer(usuario, correo, url_base, ip=None) -> bool`; ambos construyen el enlace `f"{url_base}/verificar/{token}"` / `/restablecer/{token}` y usan `notificaciones.enviar(destinatario, asunto, cuerpo)` (extender `enviar` con `html=None` opcional para multipart).
- `cuentas.smtp_configurado() -> bool`.

- [ ] Tests: emitir/consumir (uso único, vencido, tipo equivocado, invalidación de anteriores), límite por hora, correo normalizado/validación, cambiar_password sube session_version, enviar_* con `notificaciones.enviar` fake (asunto/cuerpo contienen el enlace, nunca en logs), sin SMTP devuelve False sin excepción.
- [ ] Commit `"Cuentas: correo por usuario, tokens de un solo uso (migración 0011) y envío de verificación/restablecimiento"`.

### Task 2: Rutas y pantallas

**Files:** `dashboard.py`, templates `index.html` (form de registro con correo), `login.html` (enlace "¿Olvidaste tu contraseña?"), nuevos `registro_ok.html`, `recuperar.html`, `restablecer.html`, `cuenta_correo.html` (pedir correo a usuarios viejos), `base.html` (banner), `_tab_settings.html` (sección **Cuenta**), `panel.html` (correo + verificado + botón "marcar verificado"), tests `tests/test_rutas_cuentas.py`.

- `crear_proyecto`: exige `correo` válido y contraseña válida; crea usuario con correo; `cuentas.enviar_verificacion`; sesión inmediata; flash "Te mandamos un correo para confirmar…" (o "sin correo configurado" si SMTP falta).
- `GET /verificar/<token>`: consume → `correo_verificado=True` (y si el correo del token difiere del actual —cambio de correo—, lo actualiza); flash; redirige al proyecto/login.
- `POST /reenviar-verificacion` (sesión requerida): límite, reenvía, flash neutro.
- `GET/POST /recuperar`: form correo; POST siempre "Si ese correo está registrado, te llegará un enlace"; envía si existe y límite ok.
- `GET/POST /restablecer/<token>`: GET valida sin consumir (muestra form o "enlace vencido"); POST valida contraseña, consume, `cambiar_password`, cierra sesiones, flash, redirige a login.
- `POST /cuenta/correo` (cambiar correo: pide contraseña actual; guarda `correo` nuevo con `correo_verificado=False` y envía verificación), `POST /cuenta/password` (actual + nueva + confirmación).
- Banner en `base.html` cuando `session` tiene usuario sin `correo_verificado` (rol cliente): "Confirma tu correo <correo> — Reenviar" o, sin correo, un mini-form para ponerlo.
- Guard: `_requiere_correo_verificado()` en `meta_conectar`, `meta_app_guardar`, `tienda_conectar`, `tienda_meli_iniciar` → flash "Confirma tu correo primero".
- `session_version` en la sesión; `_guard_por_cliente` (o un `before_request`) cierra la sesión si no coincide con el usuario.
- Panel admin: columnas correo/verificado, botón "Marcar verificado" (`POST /admin/usuarios/<u>/verificar`), alerta "SMTP sin configurar".
- Tarjeta SMTP de Puesta a punto: nombre "Correo de la plataforma (cuentas y avisos)" y pasos.

- [ ] Tests: registro sin correo → error; con correo → usuario con correo, verificación enviada (fake), sesión abierta; verificar token válido/vencido/repetido; reenviar con límite; recuperar con correo inexistente → misma respuesta y sin envío; restablecer flujo completo y sesión vieja invalidada; cambiar correo/contraseña; guard de Meta/tienda sin verificar → flash; admin marca verificado; banner presente/ausente.
- [ ] Verificación manual; commit `"Cuentas: registro con correo verificado, recuperar y restablecer contraseña, Configuración › Cuenta, banner y guard"`.

### Task 3: Docs
- [ ] `CLAUDE.md` párrafo "Cuentas"; `SETUP.md`: SMTP es obligatorio para cuentas en producción (Gmail: contraseña de aplicación), usuarios viejos deben poner su correo. Commit `"Docs: cuentas con correo verificado"`.
