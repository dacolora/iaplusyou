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
one (or localhost), except a host listed in `PLATAFORMA_ALIAS` (www, or the old domain during a domain
change — app.creatvmachine.com → galadsy.com, PND-326, 2026-10-14): its GET/HEAD get a 302 to the same
path and query on `PLATAFORMA_URL` (302, not 301, so a rollback isn't stuck in browser caches) and any
other method is served there (the Wompi/Bold webhooks keep posting to the old address until someone
changes it in their panel, and nobody re-sends a redirected POST); `DETRAS_DE_PROXY=1` enables ProxyFix; session cookies are HttpOnly, SameSite
Lax, Secure when the platform URL is https. Emails go through `notificaciones.enviar(html=)` —
if SMTP is missing the flows still work and the admin panel shows the warning.

**Seguridad (auditoría 2026-10-01)**: reglas que valen para todo lo nuevo. (1) CSRF: `dashboard._solo_mismo_origen`
(before_request de la app, corre también para los Blueprints) rechaza todo POST/PUT/PATCH/DELETE que el navegador marque
de otro sitio (`Sec-Fetch-Site` distinto de `same-origin`/`none`; JSON a un fetch, 403 al resto); desde el 2026-10-08
(cobros 7/11; planes 4/8, 2026-10-09) la app recibe DOS webhooks, el de Bold (`POST /pagos/bold/webhook`) y los eventos de Wompi
(`POST /pagos/wompi/eventos`, firma `cobros.wompi.evento_valido`, ver la skill `cobros`): exentos por nombre de endpoint en
`dashboard.ENDPOINTS_OTRO_ORIGEN` y `ENDPOINTS_SIN_GUARD_SESION`, protegido por su firma HMAC (`cobros.bold.firma_valida`,
`compare_digest`) sobre el cuerpo crudo con tope de 64 KB; un evento con firma inválida se anota sin cuerpo y con cupo por hora (`recargas._cupo_sin_firma`), para que nadie infle `pago_evento` ni compita por el candado de escritura; otro webhook nuevo necesita lo mismo: su excepción por nombre exacto de endpoint (nunca por prefijo) Y su firma. Detalle y trampas en la skill `cobros`. La tercera excepción (PND-304 a, 2026-10-15) es `POST /pagos/csp/tarjeta` (`cobros.csp_tarjeta`), los reportes de la política de scripts de la página de la tarjeta: los manda el navegador y no se pueden firmar, así que NO mueven nada, van con topes (16 KB, por IP —una IPv6 por su /64—, por hora, 20 violaciones distintas; lo descartado marca la lista como incompleta), marcados de otro sitio solo pasan con `Sec-Fetch-Dest: report`, solo cuentan los de un documento de nuestro host y guardan solo la directiva, el origen bloqueado (sin números largos) y la página, nunca la URL completa ni el proyecto (`cobros/csp.py`). Una excepción sin firma solo vale para algo así. (2) Cabeceras:
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

PND-072/136 (2026-10-07, lote 5 B): el aviso del fallback del director pasa por monitoreo.limpiar_texto(motivo, 300), que también tapa Bearer y llaves sk-; el prompt permanece igual. _int_form limita identificadores al entero positivo de SQLite y _volver_org no consulta un ep_id fuera de rango, evitando OverflowError. La pregunta PND-076 fue delegada el 2026-10-08 (ver implementación abajo); los topes no cambian.


PND-076/123/124 (2026-10-08, decisiones delegadas): /admin/cuentas/bloqueos y POST /admin/cuentas/desbloquear requieren requiere_admin y el POST pasa por _solo_mismo_origen. cuentas solo lista claves de límites de login válidas y vigentes (usuario o IP), sin leer fichas de contraseña ni tokens. Desbloquear toma el candado antes de leer, registra actor/objetivo en bitacora y borra únicamente ese límite; si falla la bitácora no borra. Los topes no cambian. Alertas de plata y correos ajenos rechazan descartar/restaurar con 403 en servidor. test_rutas_cuentas.py y test_rutas_alertas.py; inspección visual por Claude.

R5/R6/S2 (2026-10-08, revisión lote 6B): los topes y la ventana del login se definen solo en cuentas.py y dashboard los lee allí. Usuario: login:u:<nombre en minúsculas, máximo 200 caracteres>; IP: login:ip:<IP>. El parser de desbloqueo acepta u: no vacío hasta 200, incluidos espacios/acentos de cuentas viejas; no acepta otros prefijos. Vencimiento de pantalla en minutos redondeados hacia arriba con ngettext. Permisos, bitácora y datos personales de admin se conservan. S3: cola_limpiar diaria poda limite:* con todas sus marcas mayores de siete días o valor ilegible, bajo candado antes de leer; no toca otras claves. La búsqueda del 2026-10-08 halló ventanas de 900/3600 segundos, ninguna superior a un día.

Meta rendimiento (revisión final 2026-10-08): elegir qué cuentas publicitarias lee un proyecto es SOLO del admin (`meta_rendimiento/rutas.py::solo_admin`, 403 al resto). El token de un usuario de Meta ve las cuentas de OTROS clientes, y quien elige una cuenta lee todo su gasto; la cuenta con la que lanza otro proyecto cuenta como «En otro proyecto». Desconectar Meta, salir del modo agencia o desasignar borra las métricas copiadas: `/privacidad` y `/eliminar-datos` lo prometen, y desde PND-207 (2026-10-15) lo hacen `meta_conexion.borrar` y `meta_agencia.desasignar` por sí solas (`meta_rendimiento.soltar`), así ningún llamador nuevo puede saltárselo; desde la ronda 2 (2026-10-15) las cuentas se sueltan y dejan de mostrarse al instante y sus métricas las borra la limpieza encolada en los minutos siguientes (las páginas lo dicen así). Desde la revisión final de Rendimiento E2 (S1, 2026-10-10) soltar una cuenta (quitarla o desconectar) borra también los análisis «Cómo mejorarlo» de sus anuncios de fuente Meta (`tw_analisis` con `foto.fuente = "meta"`) y, después de las filas, su imagen y su video en R2; nunca un análisis de Triple Whale. Detalle en la skill `meta-rendimiento`.

PND-062, entrega 1 (2026-10-10, pedido de Daniel): `catalogo_selector`, `swaps_lista` y `gasto_lista`
son GET bajo `<cliente>`, pasan por `_guard_por_cliente` y rechazan con 403 a una sesión sin acceso. El catálogo
acepta únicamente sel=plus|clone y fija modo/campo en servidor; toda lectura y precarga se resuelve dentro del
proyecto de la URL. `desde` de Gasto se limita al rango SQLite. El JS rechaza respuestas redirigidas antes de
insertar HTML. Pruebas con sesión de cliente: 200 propio y 403 ajeno para los tres fragmentos.

Enmiendas PND-062, entrega 1 (2026-10-10, pedido de Daniel tras revisar la entrega): Los shells de catálogo e historiales distinguen 401/403 y redirección al login: muestran sesión vencida y un enlace a login, sin reintento perpetuo ni insertar el HTML redirigido. Se mantienen las guardias de proyecto de las rutas.

**ffprobe sobre un video subido** (auditoría de seguridad 2026-10-13, `POST /cliente/<c>/swap/medir` y `generar_swap`,
PND-312): un precio NUNCA sale solo de la cabecera del archivo (mvhd/mdhd se falsifican con 20 líneas: un video de
12 s que dice 2 s pagaba la sexta parte). `providers/swap_video_precio.medir` toma la mayor entre la cabecera y el fin
del último paquete, y cuenta los paquetes para los cuadros (sin decodificar). ffprobe va con `-protocol_whitelist file`
(una lista HLS/concat disfrazada no hace pedidos de red; ffmpeg ya limita una entrada local, esto es defensa extra).
Topes: dos mediciones a la vez (`_MEDIR_VIDEO_TURNOS`; un 8192×8192 le pide 176 MB y el VPS tiene 2 GB; sin turno,
503), 200 MB por video (413) y 120 mediciones por persona y hora (`cuentas.limite_ok`, 429). La ruta está en el
conjunto que responde 403 (no redirección) a un fetch sin acceso, y la pantalla dice sesión vencida, tamaño o turno.
Pruebas: `tests/test_swap_video_precio.py` (cabecera falsa, lista blanca, topes, 403). Pendiente: el precio de Wan 3.0
en Crear (`dashboard._duracion_video`) todavía confía en la cabecera (PND-319).

**Correo verificado y saldo de bienvenida (PND-299, 2026-10-15):** toda verificación (el enlace, restablecer la clave
desde ese correo y «marcar verificado» del admin) pasa por `cuentas.confirmar_correo(usuario, correo=None)`, que además
le da al proyecto de la cuenta su saldo de bienvenida una sola vez (`cobros.libro.dar_bienvenida`, skill `cobros`). Un
camino nuevo que deje una cuenta verificada usa esa función, no `usuarios.actualizar(..., correo_verificado=True)`.

Pruebas: `tests/test_swap_video_precio.py` (cabecera falsa, lista blanca, topes, 403). El precio de los videos de referencia de Wan 3.0 en Crear (`dashboard._duracion_video`, PND-319, 2026-10-13) usa la misma medida: ya no confía en la cabecera (skill `crear`).

**La clave otra vez para mover plata (PND-347, 2026-10-15).** `cuentas.clave_reciente(session)` y
`cuentas.confirmar_clave(session, clave, ip)`: antes de una recarga manual, un ajuste, «Activar a mano» un plan, el
tope de lo sumado a mano, la tasa de referencia de la TRM, «Aceptar la tasa de hoy», «Cobrar», el pospago, los márgenes,
el saldo de bienvenida o crear o editar un plan en /admin/cobros se pide la clave
de quien tiene la sesión; vale `REAUTH_S` (10 min) en la sesión firmada (`clave_confirmada_en`; un login nuevo la
borra; cambiar la clave cierra las DEMÁS sesiones y la que la cambió la conserva). **Todo formulario que pide la clave
de quien ya tiene sesión pasa por `cuentas.verificar_con_tope`** (también Configuración › Cuenta: cambiar el correo o
la clave, `dashboard._clave_actual_ok`): un fallo cuenta contra los MISMOS topes del login (`login:u:<usuario>`,
`login:ip:<ip>`) y con el tope lleno ni se mira; antes, una sesión robada adivinaba la clave ahí sin límite y con ella
pasaba la confirmación (auditoría de seguridad de la revisión, 2026-10-15). Por lo mismo, **un admin no se desbloquea a
sí mismo** en `/admin/cuentas/desbloquear` (ni su usuario ni su IP). Una acción nueva del admin que cree saldo usa
`rutas._clave_para_mover_plata` y avisa a todos los admins. El detalle está en la skill `cobros` («Los controles de plata del admin»). Pruebas: `tests/test_cobros_controles_plata.py`, `tests/test_rutas_cuentas.py`.
