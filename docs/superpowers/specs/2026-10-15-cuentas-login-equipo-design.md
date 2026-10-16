# Cuentas: entrar con correo o Google, recuperar acceso, Mi cuenta y equipo del proyecto

Fecha: 2026-10-15. Pedido de Daniel: «toda una sección mejorada de todo lo relacionado al login del cliente, cambiar
contraseñas, recuperación… ir teniendo todo el modelo estructurado» y «creemos algo bien serio, no te detengas». Cierra
PND-292 (rediseño del registro) y absorbe PND-048 en lo que depende del código. Decisiones previas que no se reabren:
relevo `docs/superpowers/relevos/2026-10-12-decisiones-de-daniel-rendimiento-y-registro.md` (registro abierto pero
cobrando, correo con Resend, bienvenida solo país e idioma y al final recargar o plan).

Decisiones de Daniel en esta conversación (2026-10-15):

| Pregunta | Respuesta |
|---|---|
| ¿Con qué entra un cliente? | **Correo + contraseña**; el correo es la identidad. Las cuentas viejas siguen entrando con su usuario. |
| ¿Y Google? | Sí: **«Continuar con Google»** (acceso rápido con la cuenta de Gmail). |
| ¿Equipo del cliente? | **Dueño y miembros.** El dueño invita, maneja la plata y quita gente; el miembro genera, edita, lanza y publica, pero no recarga, no cambia el plan ni invita. |
| ¿Rumbo? | Opción A: mover las cuentas a la base de datos con el modelo completo. |

Lo que necesita las manos de Daniel y por eso NO bloquea el código: la llave de Resend (los correos salen cuando esté),
el cliente OAuth de Google tipo «aplicación web» (el botón de Google aparece solo cuando sus dos variables existen) y
el contacto de soporte que se muestra cuando el correo no sale (`SOPORTE_CONTACTO`, por defecto `hola@galadsy.com`).

## 1. Qué cambia para una persona

- **Entrar** (`/login`): un campo «Correo» y uno «Contraseña», y debajo «Continuar con Google». Las cuentas creadas antes
  de este cambio también pueden escribir su usuario en el campo del correo (si lo escrito no tiene `@`, se busca por
  usuario). Al entrar: una cuenta con un solo proyecto va a él; con varios, a «Mis proyectos»; un admin, al panel.
- **Crear cuenta** (`/registro`, también desde el formulario de la portada): correo, contraseña y nombre de la empresa.
  Ya no se pide usuario: se genera uno estable a partir del correo (ver §3). O «Continuar con Google», que trae el correo
  ya verificado y pide solo el nombre de la empresa. El proyecto nace cobrando (PND-298) y la persona entra de una vez.
- **Bienvenida** (`/cliente/<c>/bienvenida`, solo la primera vez): país e idioma del proyecto, y al final dos botones:
  «Recargar saldo» y «Elegir un plan», con «Después» para saltarlo. Nada más (decisión 2026-10-12).
- **Olvidé mi contraseña** (`/recuperar`): pide el correo y manda un enlace de una hora (como hoy). Si el servidor no
  tiene correo, la pantalla lo dice sin rodeos y da las dos salidas: «Si tu cuenta usa Google, entra con Google» y
  «Escríbenos a <SOPORTE_CONTACTO>». La respuesta nunca dice si el correo existe.
- **Mi cuenta** (`/cuenta`, página propia, fuera de Configuración; el nombre de la cuenta en la cabecera lleva allá):
  nombre, correo (cambiarlo vuelve a pedir verificación), contraseña (la actual más la nueva), idioma, Google
  («Vinculada a …» / «Vincular» / «Desvincular», esta última solo si tiene contraseña), «Cerrar sesión en los demás
  dispositivos» y «Mis proyectos».
- **Equipo** (Configuración › «Equipo», apartado nuevo; solo lo ve el dueño o el admin): quién está en el proyecto y con
  qué rol, «Invitar» (correo y rol), invitaciones pendientes con «Copiar enlace», «Reenviar» y «Anular», «Quitar»,
  «Hacer dueño» (transfiere: el dueño anterior pasa a miembro). El enlace de la invitación siempre se puede copiar, con
  o sin correo en el servidor: hoy el correo no sale y el dueño se lo manda por WhatsApp.
- **Aceptar una invitación** (`/invitacion/<token>`): si ya está dentro con ese mismo correo, se une y listo; si no,
  elige contraseña o entra con Google. Una cuenta creada desde una invitación nace con el correo verificado: el
  enlace llegó a ese correo.
- **Lo que un miembro no puede**: recargar, verificar o buscar una recarga, el plan entero (alta, tarjeta, cancelar,
  Nequi), el apartado Equipo y cambiar el nombre del proyecto (`guardar_nombre_proyecto`). Sí ve el saldo disponible y todos los precios (regla 1:
  el precio a la vista antes de gastar) y una línea «Pídele a <dueño> que recargue» cuando no alcanza.

## 2. Modelo de datos

Las cuentas dejan `usuarios.json` y pasan a SQLite (`data/creatv.db`). Migración de esquema y de datos en una sola
revisión de Alembic (`0041_cuentas`; si al mezclar main ya tiene una 0041, se renumera, como se hizo con la 0036 → 0038).

```
cuenta
  id              INTEGER PK
  usuario         TEXT UNIQUE NOT NULL   -- identificador estable [a-z0-9._-]{3,40}; es lo que viaja en la sesión,
                                         -- la bitácora, idiomas, cobros (actualizado_por) y token_cuenta.usuario
  correo          TEXT UNIQUE            -- NULL solo en cuentas admin viejas sin correo; en minúsculas (usuarios.validar_correo)
  correo_verificado INTEGER NOT NULL DEFAULT 0
  password_hash   TEXT                   -- NULL si la cuenta solo entra con Google
  nombre          TEXT                   -- cómo quiere que la llamen; de Google viene solo
  rol             TEXT NOT NULL          -- 'admin' | 'cliente' (el rol global de hoy; el de proyecto va en miembro)
  google_sub      TEXT UNIQUE            -- el `sub` de Google; NULL si no vinculó
  idioma          TEXT                   -- 'es' | 'en' | NULL (hoy en usuarios.json)
  session_version INTEGER NOT NULL DEFAULT 1
  creado_en       TEXT NOT NULL
  ultimo_acceso   TEXT
  bienvenida_vista INTEGER NOT NULL DEFAULT 1   -- 0 solo para cuentas creadas por el registro nuevo hasta que pasen la bienvenida

miembro
  cuenta_id       INTEGER NOT NULL REFERENCES cuenta(id) ON DELETE CASCADE
  cliente         TEXT NOT NULL          -- carpeta del proyecto (clientes/<cliente>)
  rol             TEXT NOT NULL          -- 'dueno' | 'miembro'
  desde           TEXT NOT NULL
  invitado_por    TEXT                   -- cuenta.usuario de quien invitó; NULL en la migración y en el alta
  PRIMARY KEY (cuenta_id, cliente)
  -- un solo dueño por proyecto: índice único parcial sobre (cliente) WHERE rol='dueno'

invitacion
  id              INTEGER PK
  cliente         TEXT NOT NULL
  correo          TEXT NOT NULL
  rol             TEXT NOT NULL          -- 'dueno' | 'miembro' (dueño solo la usa el admin para entregar un proyecto)
  token_hash      TEXT UNIQUE NOT NULL   -- sha256 del token, como token_cuenta
  invitado_por    TEXT NOT NULL
  creado_en       TEXT NOT NULL
  vence_en        TEXT NOT NULL          -- creado_en + 7 días
  usado_en        TEXT                   -- NULL mientras esté viva
  usado_por       TEXT                   -- cuenta.usuario que la aceptó
  anulada_en      TEXT

token_cuenta (existe, migración 0011): sin cambios. Sus `usuario` siguen apuntando a cuenta.usuario.
```

Migración de datos, dentro de la misma revisión y antes de que la app arranque con el código nuevo:

1. Cada entrada de `usuarios.json` → una fila de `cuenta` con el mismo `usuario`, `correo`, `correo_verificado`,
   `password_hash`, `rol`, `idioma`, `session_version`, `creado_en`. `nombre` = NULL. `bienvenida_vista` = 1 (nadie
   viejo ve la bienvenida).
2. Cada cuenta con `rol = cliente` y `cliente` no vacío → una fila de `miembro` con rol `dueno`. Si dos cuentas viejas
   apuntan al mismo proyecto (las que se agregaron por línea de comandos), la más antigua es dueño y las demás miembros.
3. `usuarios.json` se renombra a `usuarios.json.migrado-<fecha>` (no se borra). Si el archivo no existe (instalación
   nueva), la migración solo crea las tablas. `downgrade` vuelve a escribir `usuarios.json` desde las tablas y las borra.
4. En producción hoy: 6 cuentas (1 admin sin correo, 5 clientes, 2 verificados). La migración se ensaya en una copia
   del VPS antes del despliegue (skill `despliegue`).

Regla 5 (un solo escritor): toda escritura en `cuenta`, `miembro` e `invitacion` pasa por `usuarios.py` (cuentas) y el
módulo nuevo `equipo.py` (miembros e invitaciones), en transacciones de `db.py`. Nadie más hace `INSERT`/`UPDATE` ahí.

## 3. `usuarios.py` como fachada

Las sesenta llamadas que hoy hace el resto de la app (`obtener`, `actualizar`, `verificar`, `puede_acceder`,
`por_correo`, `por_cliente`, `existe`, `crear`, `cambiar_password`, `validar_*`) **conservan nombre, firma y forma del
resultado** (`obtener` devuelve un dict con `rol`, `cliente`, `correo`, `correo_verificado`, `session_version`,
`idioma`, `creado_en`, más `nombre`, `google_sub` y `id`). Cambios de significado:

- `obtener(usuario)["cliente"]`: el proyecto del que es **dueño**; si no es dueño de ninguno, el primero del que es
  miembro; `None` sin proyectos. Lo que hoy lee `cliente` de ahí (dos sitios fuera del guard) sigue funcionando para
  una persona con un proyecto, que es todo el mundo hoy.
- `puede_acceder(sesion, cliente)`: admin siempre; si no, **que exista `miembro` para esa cuenta y ese proyecto** (ya
  no compara con `sesion["cliente"]`). Es la única puerta de `_guard_por_cliente` y no cambia de nombre.
- `crear(usuario, password, rol, cliente=None, correo=None, *, nombre=None, google_sub=None, verificado=False)`:
  `password` puede ser `None` solo con `google_sub`. Con `cliente`, crea el `miembro` dueño en la misma transacción.
- `cargar()` sigue existiendo **solo para leer** (devuelve el mismo dict `{usuario: entry}` armado desde la tabla;
  lo usan `notificaciones.admins_con_correo` y el panel). `guardar()` desaparece: quien lo llame falla en las pruebas.
- Nuevos: `por_google(sub)`, `vincular_google(usuario, sub, correo_google)`, `desvincular_google(usuario)`,
  `usuario_desde_correo(correo)` (la parte antes de la `@`, limpiada a `[a-z0-9._-]`, mínimo 3 caracteres rellenando
  con `u`, y un sufijo `-2`, `-3`… si ya existe), `proyectos_de(usuario)` → `[{cliente, nombre, rol}]`,
  `registrar_acceso(usuario)`, `cerrar_otras_sesiones(usuario)` (sube `session_version` y devuelve la nueva para
  resellar la sesión actual).

`equipo.py` (nuevo): `miembros(cliente)`, `rol_en(usuario, cliente)` → `'dueno' | 'miembro' | None`,
`es_dueno(usuario, cliente)`, `invitar(cliente, correo, rol, por, url_base)` → `(invitacion, enlace)`, `invitaciones(cliente)`,
`anular(id, por)`, `reenviar(id, por, url_base)` (emite token nuevo, invalida el anterior), `validar(token)`,
`aceptar(token, usuario)` (crea el `miembro`, marca usada; si el rol es `dueno`, degrada al dueño actual),
`quitar(cliente, usuario, por)` (nunca al dueño: primero «Hacer dueño» a otro), `hacer_dueno(cliente, usuario, por)`.
Cada operación anota en `bitacora` (`equipo`, tipo, actor → objetivo) y toma el candado antes de leer (regla 5).

## 4. Sesión y guards

- La sesión sigue llevando `usuario`, `rol`, `cliente` (el proyecto **actual**) y `sv`. Nada de lo que hoy lee
  `session["rol"]` (admin/cliente, más de treinta sitios) cambia.
- `_verificar_sesion`: la cuenta existe, `sv` coincide, el rol coincide y, si `session["cliente"]` no es `None`, hay
  `miembro` para ese proyecto (reemplaza la igualdad con `entry["cliente"]`). Si falta la membresía (lo quitaron),
  la sesión se cierra con el mismo aviso de hoy.
- `_guard_por_cliente` no cambia: sigue preguntándole a `puede_acceder`. Como efecto, al entrar a `/cliente/<c>` de un
  proyecto del que se es miembro, `session["cliente"]` se actualiza a `c` (cambio de proyecto implícito).
- **Guard de dueño** (`_solo_dueno(cliente)`, en `dashboard.py` y su gemelo en `cobros/rutas.py` como `_puede_ver_saldo`
  hoy): admin o dueño; a un miembro, 403 con JSON en los `fetch` y una página «Solo el dueño del proyecto puede hacer
  esto» en lo demás. Se aplica por nombre de endpoint a: `cobros.saldo_recargar`, `cobros.recarga_verificar`,
  `cobros.plan_alta` (GET y POST), `cobros.plan_tarjeta`, `cobros.plan_cancelar`, `cobros.plan_nequi`, todo
  `/cliente/<c>/equipo/*`, y `guardar_nombre_proyecto` (el nombre del proyecto). Las plantillas esconden los botones además del guard, nunca
  en vez de él (skill `seguridad`, regla 9).
- **Correo verificado en lo que cobra** (PND-292): `_requiere_correo_verificado` cubre, además de Meta y tienda, los
  endpoints que ya listó PND-292 (`pestana_rendimiento.CON_CORREO_VERIFICADO`, `triple_whale.ganchos_probar`) y el
  carril de Crear (`cf_crear_video`, `cf_rearmar`) **solo cuando `cuentas.smtp_configurado()` es True**: sin correo
  en el servidor nadie podría verificarse y sería cerrar la tienda. Una cuenta que entró por Google o aceptó una
  invitación nace verificada, así que no la frena. El admin sigue exento.
- Google OAuth: `state` y `nonce` aleatorios en la sesión, PKCE (S256), callback en `PLATAFORMA_URL/login/google/callback`
  (de `_url_base()`, nunca del `Host`). El `id_token` se verifica con `google.oauth2.id_token.verify_oauth2_token`
  (`google-auth` ya está en `requirements.txt`) contra `GOOGLE_LOGIN_CLIENT_ID`; se exige `email_verified = true`; el
  intercambio del código va con `requests` al endpoint de Google con 10 s de tiempo máximo. Los endpoints
  `login_google` y `login_google_callback` entran a `ENDPOINTS_SIN_GUARD_SESION`. Si un `google_sub` ya está en otra
  cuenta, o el correo de Google pertenece a una cuenta que no es la que intenta vincular, se rechaza con un aviso
  neutro. Los topes de intentos del login no aplican a Google (no hay contraseña que adivinar), pero el callback lleva
  `cuentas.limite_ok` por IP (30 por hora) para que no sea un camino de registro masivo.
- Tokens de invitación: 32 bytes `secrets.token_urlsafe`, se guarda el sha256, se muestra una sola vez (al crear y al
  reenviar). Aceptar exige que el correo de la cuenta que acepta sea el de la invitación (en minúsculas); con Google,
  el de Google. Topes: 20 invitaciones por proyecto y hora; 10 intentos de `/invitacion/<token>` por IP y hora.
- Un `miembro` quitado, un dueño transferido o una cuenta a la que le cambian el rol global: `session_version` sube y
  sus sesiones mueren en la siguiente petición (mecanismo existente).

## 5. Rutas y pantallas

| Ruta | Método | Quién | Qué |
|---|---|---|---|
| `/login` | GET, POST | público | correo (o usuario viejo) + contraseña; botón Google si está configurado |
| `/login/google` | GET | público | arma `state`, `nonce`, PKCE y redirige a Google; `?siguiente=` solo rutas internas (`/…`) |
| `/login/google/callback` | GET | público | verifica, y: cuenta por `sub` → entra; correo de cuenta existente → vincula y entra (marca verificado); correo nuevo → crea cuenta y manda a `/registro/empresa`; con `invitacion` en la sesión → la acepta |
| `/registro` | GET, POST | público | correo, contraseña, nombre de la empresa; crea cuenta + proyecto (cobrando) + miembro dueño; entra; a bienvenida |
| `/registro/empresa` | GET, POST | sesión sin proyectos | solo el nombre de la empresa (tras Google); crea proyecto; a bienvenida |
| `/cliente/<c>/bienvenida` | GET, POST | miembro | país e idioma del proyecto; «Recargar», «Elegir plan», «Después»; marca `bienvenida_vista` |
| `/recuperar` | GET, POST | público | como hoy; sin SMTP muestra las dos salidas (§1) |
| `/restablecer/<token>` | GET, POST | público | como hoy |
| `/verificar/<token>`, `/reenviar-verificacion` | | | como hoy |
| `/cuenta` | GET | sesión | Mi cuenta (§1) |
| `/cuenta/nombre`, `/cuenta/correo`, `/cuenta/password`, `/cuenta/idioma` | POST | sesión | cada campo; correo y password son las rutas de hoy movidas de Configuración |
| `/cuenta/google/vincular` | GET | sesión | va a Google con `vincular=1` en la sesión |
| `/cuenta/google/desvincular` | POST | sesión con contraseña | quita `google_sub` |
| `/cuenta/sesiones/cerrar` | POST | sesión | sube `sv`, resella la actual |
| `/proyectos` | GET | sesión | Mis proyectos (lista con rol); admin ve el enlace al panel |
| `/cliente/<c>/equipo` | GET | dueño/admin | fragmento del apartado Equipo (lo pide Configuración por `fetch`, como Saldo) |
| `/cliente/<c>/equipo/invitar` | POST | dueño/admin | correo + rol → fila + enlace; manda correo si hay SMTP; muestra el enlace para copiar |
| `/cliente/<c>/equipo/invitacion/<id>/reenviar`, `/anular` | POST | dueño/admin | |
| `/cliente/<c>/equipo/<usuario>/quitar`, `/hacer-dueno` | POST | dueño/admin | |
| `/invitacion/<token>` | GET, POST | público | aceptar (§1) |
| `/admin/usuarios` | GET | admin | lista de cuentas y proyectos (hoy está dentro del panel; pasa a su página) |
| `/admin/usuarios/<usuario>/verificar` | POST | admin | como hoy |
| `/admin/usuarios/<usuario>/enlace-restablecer` | POST | admin | genera un enlace de restablecer de una hora y lo muestra una vez para mandarlo por otro canal mientras no hay correo; queda en bitácora |
| `/admin/usuarios/<usuario>/rol` | POST | admin | admin ↔ cliente (sube `sv`) |

Todos los POST pasan por `_solo_mismo_origen` (ya es global). Las rutas de cuenta y equipo viven en un Blueprint nuevo
`cuentas_rutas.py` (`bp = Blueprint("cuentas", __name__)`), para no engordar `dashboard.py`; las de login, registro y
recuperación que hoy están en `dashboard.py` se mueven allá con sus nombres de endpoint intactos (`url_for('login')`
sigue existiendo: el Blueprint se registra sin prefijo y las rutas de login conservan `endpoint=` explícito).

Pantallas (skill `ui`): `login.html` conserva la escena de la vaca; gana el botón de Google (logo oficial en SVG en
`static/`, texto «Continuar con Google») y un separador «o». `registro.html` y `recuperar.html` usan la misma `login-caja`.
`cuenta.html` y `proyectos.html` extienden `base.html` dentro de la app. `_config_equipo.html` es un apartado más de
`_tab_settings.html` (botón «Equipo» solo para dueño/admin), cargado por `fetch` al abrirlo como Saldo. El nombre de
la cuenta en la cabecera (`header-usuario`) pasa a ser un enlace a `/cuenta` y muestra `nombre` o `usuario`. El CSS va
en `static/estilos/pantallas/cuentas.css` y `style.css` se regenera con `python3 estilos.py construir`. En el celular
nada empuja de lado; los formularios son de una columna.

Textos: todo con `_()` / `gettext` / `N_`, catálogo actualizado y traducido al inglés con `docs/i18n/glosario.md`
(skill `idioma`). Los correos de invitación y de restablecer van en el idioma de la cuenta que los recibe si existe;
si no, en el del proyecto. La tarjeta «Correo» de Puesta a punto (`llaves.py`) deja de hablar de Gmail: dice Resend,
`smtp.resend.com`, usuario `resend`, y la dirección pública con `galadsy.com`.

## 6. Correos (salen solo con SMTP; sin él, el enlace se muestra para copiar)

| Tipo | A quién | Contenido |
|---|---|---|
| verificación (existe) | la cuenta | como hoy |
| restablecer (existe) | la cuenta | como hoy |
| `invitacion` | el correo invitado | «<nombre o usuario> te invitó a <proyecto> en Galadsy», botón al enlace, vence en 7 días |
| `equipo_cambio` | la cuenta afectada | te quitaron / te hicieron dueño / te vincularon Google (aviso, sin enlace) |
| `cuenta_cambio` | la cuenta | tu correo cambió a …, tu contraseña cambió, se cerraron tus otras sesiones (aviso de seguridad al correo ANTERIOR cuando el correo cambia) |

Se agregan a `notificaciones.TIPOS`. Nunca llevan tokens salvo el enlace que es su razón de ser (invitación y
restablecer); ningún texto de error entra a un correo sin `cola.sin_token`.

## 7. Configuración nueva

```
GOOGLE_LOGIN_CLIENT_ID=      # cliente OAuth tipo «aplicación web» en Google Cloud; sin él no hay botón de Google
GOOGLE_LOGIN_CLIENT_SECRET=
SOPORTE_CONTACTO=hola@galadsy.com   # lo que se muestra cuando el correo no sale
```

Tarjeta nueva en Puesta a punto (`llaves.py`): «Entrar con Google», opcional, con los pasos: en
console.cloud.google.com crear un cliente OAuth «Aplicación web», origen autorizado `https://galadsy.com`, URI de
redirección `https://galadsy.com/login/google/callback`, pantalla de consentimiento con el logo y los enlaces de
privacidad y términos del sitio, y pegar las dos variables en el `.env` del servidor. Mientras la app de Google esté
«en pruebas», solo entran los correos que Daniel agregue como probadores: la tarjeta lo dice.

## 8. Lo que NO entra (a propósito)

Segundo factor propio (quien entre por Google ya lo tiene de Google; el admin puede vincular Google), borrar la cuenta
desde la web (`/eliminar-datos` sigue siendo el camino), historial de accesos por dispositivo, varios dueños, roles
más finos (lector), SSO con Meta o Apple, cambiar el `usuario` estable, y mandar correos a clientes existentes
(reenviar la verificación a ornate, happyfresh y haad es un paso del despliegue que se le pregunta a Daniel: es mandar
correo a clientes).

## 9. Pruebas

- Modelo y migración: `tests/test_cuentas_modelo.py` (fachada completa contra SQLite en memoria; `usuario_desde_correo`
  con colisiones y correos raros; `puede_acceder` por membresía; `cargar()` solo lectura) y
  `tests/test_migracion_0041.py` (un `usuarios.json` de muestra con admin sin correo, dos cuentas al mismo proyecto,
  idiomas; upgrade → filas correctas y archivo renombrado; downgrade → JSON equivalente; sin archivo → solo tablas).
- Rutas: `tests/test_rutas_login.py` (correo, usuario viejo, topes, redirección por número de proyectos),
  `tests/test_rutas_registro.py` (alta, cobrando, usuario generado, bienvenida una sola vez, país e idioma guardados),
  `tests/test_login_google.py` (Google simulado con `monkeypatch`: entra por `sub`, vincula por correo, crea cuenta y
  pide empresa, rechaza `email_verified` falso, `state` ajeno, `sub` ya usado, tope por IP, vincular desde Mi cuenta,
  desvincular solo con contraseña), `tests/test_rutas_cuenta.py` (cada campo, correo anterior avisado, cerrar otras
  sesiones mata la segunda y conserva la primera), `tests/test_equipo.py` (invitar, enlace una sola vez, aceptar con
  cuenta nueva/existente/Google, correo distinto rechazado, vencida, anulada, reenviar invalida, quitar, hacer dueño,
  un solo dueño, miembro 403 en cada endpoint de plata y de equipo, dueño 200, admin 200, botones escondidos para el
  miembro, sesión del quitado muere), `tests/test_admin_usuarios.py` (enlace de restablecer una vez y en bitácora).
- Las pruebas existentes (`test_cuentas.py`, `test_rutas_cuentas.py`, `test_usuarios_por_cliente.py`,
  `test_cuentas_idioma.py`, `test_i18n_fugas.py`, `test_rutas_configuracion.py`) se adaptan a la fachada, no se borran.
- Mutaciones obligatorias del `revisor`: quitar el guard de dueño de `saldo_recargar`; dejar que `aceptar` no compare el
  correo; devolver `True` en `puede_acceder` sin membresía; aceptar `email_verified` falso. Las pruebas tienen que verlo.
- Lo real manda: capturas de login, registro, bienvenida, Mi cuenta y Equipo en escritorio y celular con el servidor
  temporal (`verificar-ui-sin-contrasena`), y la migración ensayada sobre una copia de la base y del `usuarios.json`
  de producción.

## 10. Despliegue

Un solo despliegue de los dos servicios (el worker lee `usuarios.cargar()` en `notificaciones.admins_con_correo`):
respaldo de `data/creatv.db` y de `usuarios.json`, ensayo de la migración en una copia, cola vacía en su propio `ssh`,
pull, pip, `alembic upgrade head`, reinicio, humo (`/login` 200 con el campo «Correo», `/salud`, entrar con happyflops
por usuario viejo y por correo en el navegador integrado con una cuenta de prueba, nunca con la de un cliente).
Después, con Daniel: Google (su cliente OAuth), Resend (su llave), correo del admin y reenviar verificaciones.
