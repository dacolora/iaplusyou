---
name: seguridad
description: "Seguridad y cuentas: CSRF por Sec-Fetch-Site, cabeceras, quién puede sondear un trabajo, login con topes, subidas validadas por contenido, SSRF, tokens en disco, y las cuentas (correo verificado, recuperar clave, sesiones). Cargar antes de agregar una ruta POST, una subida, una URL que escribe una persona, un trabajo que se sondea, o tocar usuarios.py, cuentas.py o el login."
---

# Seguridad y cuentas

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

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
top of Configuración (`_tab_settings.html`), not on every tab (removed from `base.html` 2026-09-26; since 2026-10-02 the same case is also the alert `cuenta:correo:<usuario>` in the Alertas tab, skill `alertas`); admins can mark a user verified from the panel. Rate limits (`cuentas.limite_ok`,
`kv`, 5/h) per correo and per IP on registration, resend and recovery. Links are built from
`PLATAFORMA_URL` (never from the `Host` header) and the app 404s requests whose host isn't that
one (or localhost); `DETRAS_DE_PROXY=1` enables ProxyFix; session cookies are HttpOnly, SameSite
Lax, Secure when the platform URL is https. Emails go through `notificaciones.enviar(html=)` —
if SMTP is missing the flows still work and the admin panel shows the warning.

**Seguridad (auditoría 2026-10-01)**: reglas que valen para todo lo nuevo. (1) CSRF: `dashboard._solo_mismo_origen`
(before_request de la app, corre también para los Blueprints) rechaza todo POST/PUT/PATCH/DELETE que el navegador marque
de otro sitio (`Sec-Fetch-Site` distinto de `same-origin`/`none`; JSON a un fetch, 403 al resto); desde el 2026-10-08
(cobros 7/11) la app recibe UN webhook, el de Bold (`POST /pagos/bold/webhook`): exento por nombre de endpoint en
`dashboard.ENDPOINTS_OTRO_ORIGEN` y `ENDPOINTS_SIN_GUARD_SESION`, protegido por su firma HMAC (`cobros.bold.firma_valida`,
`compare_digest`) sobre el cuerpo crudo con tope de 64 KB; un evento con firma inválida se anota sin cuerpo y con cupo por hora (`recargas._cupo_sin_firma`), para que nadie infle `pago_evento` ni compita por el candado de escritura; otro webhook nuevo necesita lo mismo: su excepción por nombre exacto de endpoint (nunca por prefijo) Y su firma. Detalle y trampas en la skill `cobros`. (2) Cabeceras:
`_cabeceras_seguridad` pone `nosniff`, `X-Frame-Options: DENY`, una CSP que solo cierra `frame-ancestors`/`object-src`/
`base-uri` (todavía hay ~80 `<script>` y ~90 manejadores en línea, y los medios vienen de R2) y HSTS cuando el sitio es
https. (3) `/trabajo/<job_id>/estado` solo responde al admin o a quien puede entrar al proyecto dueño
(`trabajos.dueno`: el `cliente` de la fila de la cola o el de `trabajos.iniciar(..., cliente=)`); todo trabajo nuevo
que la persona sondea lleva su `cliente`, si no su barra no se ve. (4) Login: tope de intentos FALLIDOS por usuario (10)
y por IP (30) cada 15 min (`cuentas.limite_disponible` mira, `limite_ok` anota), hash de relleno para un usuario que no
existe, `_abrir_sesion` limpia la sesión y `_verificar_sesion` cierra la que traiga otro rol o proyecto que
usuarios.json. (5) Subidas: `MAX_CONTENT_LENGTH` = `MAX_BYTES_PETICION` (256 MB, 413 → `_peticion_demasiado_grande`);
una foto se valida por su contenido (`_foto_subida_invalida`: Pillow + 20 MB), nunca por la extensión; lo que se vuelve a
servir desde el dominio de la app va con `mimetype` de la lista blanca (`MIMETYPES_MEDIOS`), jamás adivinado;
`Image.MAX_IMAGE_PIXELS` = 64 MP en Flask y en el worker; un .xlsx pasa por `conectores.base.xlsx_demasiado_grande`.
(6) SSRF: toda URL que escribe una persona o trae una página ajena se pide con `conectores.url.abrir` (valida el host en
cada redirección; `host_permitido` rechaza todo lo que no sea `is_global`, también la IPv4 dentro de IPv6), una tienda con
dirección del cliente con `_http.pedir_tienda` (sin redirecciones: las claves irían al destino) y los links de video sin
el extractor genérico de yt-dlp. (7) Meta agencia en autoservicio: un portafolio que ya usa otro proyecto (conectado o
con solicitud) no se lista (`meta_agencia.portafolio_de_otro`), una Página asignada a otro proyecto tampoco, y una Página
escrita a mano va por «Avisar a Creatv». (8) Tokens de YouTube/TikTok en disco con 0600 (`_json_store.escribir_privado`). (9) Alertas (2026-10-02): `POST /cliente/<c>/alertas/descartar|restaurar` validan clave y huella con `fullmatch` (400) y responden 403 a quien no es admin si la clave es de una alerta `solo_admin` (`alertas.es_solo_admin`, prefijos `llave:`, `worker:`, `revision:`, `saldo:wavespeed_recarga`): los descartes son del proyecto y un cliente se los escondería al admin; nunca solo ocultar el botón. Ninguna alerta lleva un valor de llave ni un texto de error sin `cola.sin_token`.
Dependencias: `requirements.txt` trae pisos verificados con `pip-audit` (`venv/bin/pip install pip-audit && venv/bin/pip-audit`); en el VPS,
`pip install -U -r requirements.txt` los aplica.
