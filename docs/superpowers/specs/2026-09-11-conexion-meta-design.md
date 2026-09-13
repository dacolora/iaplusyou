# Diseño: conexión con Meta desde la web ("Conectar con Meta")

## Contexto y motivo

El módulo de Meta Ads (`meta_ads/`, `ads.py`, pestaña FlowMarketing — spec
`2026-09-05-meta-ads-marketing-api-design.md`) está completo y revisado, pero
**nunca ha hecho una llamada real**: al 2026-09-11 las seis variables `META_*`
del `.env` están vacías, ningún proyecto tiene credenciales propias y la app de
Meta no existe todavía. Ni los anuncios ni la publicación orgánica en
Facebook/Instagram (`uploaders/meta_uploader.py`) funcionan.

Las dos vías de autorización que hay en el repo son de terminal y no sirven
para el producto:

- `auth/auth_meta.py` hace OAuth completo, pero abre un navegador local con
  callback en `localhost:8765` — no corre en el VPS ni desde el celular — y
  **no pide `ads_management`**, así que su token no sirve para anuncios.
- `auth/auth_meta_ads.py` es un checklist de texto que pide pegar el ID de
  cuenta publicitaria a mano y asume que el token de Página tiene permiso de
  anuncios (no lo tiene).

Además, `meta_ads/auth.py` reutiliza el token de Página para los endpoints
`act_<id>/…`. Meta documenta tokens de **usuario** o de **usuario del sistema**
para cuentas publicitarias; el de Página no está documentado para eso.

La decisión de producto (2026-09-11): habrá muchos clientes, y **cada cliente
conecta su propia cuenta de Meta** con un botón, sin ver nunca un token. El
diagnóstico completo, con cada requisito de Meta verificado en su
documentación, está publicado como artefacto "Diagnóstico Meta Ads"; este spec
es su consecuencia.

## Metas

- Un botón "Conectar con Meta" en FlowMarketing: el cliente autoriza con su
  Facebook, elige su cuenta publicitaria y su Página (con el Instagram
  vinculado), y queda conectado. Sin terminal, sin pegar tokens.
- Un solo permiso cubre anuncios **y** publicación orgánica: la misma conexión
  alimenta `meta_ads/` y `meta_uploader.py`.
- Credenciales por proyecto, aisladas entre clientes, nunca en git.
- FlowMarketing dice la verdad: sin conexión no muestra el formulario de
  publicar; con la conexión rota, lo avisa y ofrece reconectar.
- Funciona igual mientras la app de Meta está en modo desarrollo (clientes
  agregados como *tester*) y después de pasar App Review (cualquiera).

## No-metas (explícitamente fuera de este spec)

- Crear cuentas publicitarias, Páginas o Business Managers desde la app — Meta
  no lo expone a terceros por API en este contexto; el cliente los crea en
  Meta y acá solo los elige.
- Cualquier cambio a cómo se crean campañas/creatives (`meta_ads/campaign.py`,
  `adset.py`, `creative.py`, `ad.py`, `insights.py`): solo cambia **de dónde
  sale el token**. El defecto conocido de `crear_creative_video` (URL donde
  Meta espera `video_id`) sigue siendo un ítem aparte, ya registrado.
- Pegar tokens/IDs a mano como alternativa (se descartó el 2026-09-11; si se
  necesita como plan B más adelante es un spec propio).
- Pasar App Review / Verificación de negocio: son trámites humanos (sección
  "Prerrequisitos"), no código.
- Renovación automática de tokens con expiración: la configuración pide tokens
  **sin expiración**; si Meta entregara uno de 60 días, se detecta como
  "conexión rota" y se reconecta a mano. Refresco automático queda para
  después.

## Arquitectura

```
FlowMarketing (sin conectar)
   │  clic "Conectar con Meta"
   ▼
GET /cliente/<c>/meta/conectar
   │  genera state (sesión), redirige a
   ▼
facebook.com/<v>/dialog/oauth?client_id&config_id&redirect_uri&state&response_type=code
   │  el cliente autoriza con SU Facebook
   ▼
GET /meta/callback?code=…&state=…
   │  valida state · servidor-a-servidor: /oauth/access_token (client_secret)
   │  lee /me?fields=client_business_id · lista cuentas y Páginas accesibles
   ▼
GET /cliente/<c>/meta/elegir   (pantalla: una cuenta + una Página)
   │  POST /cliente/<c>/meta/elegir
   ▼
clientes/<c>/meta.json  ──▶  meta_ads/auth.py (token de sistema, act_…)
                        ──▶  uploaders/meta_uploader.py (token de Página)
                        ──▶  capacidades → FlowMarketing "Conectado"
```

Módulos:

- **`meta_conexion.py`** (nuevo, raíz): todo lo que sabe de OAuth y de
  `meta.json`. Funciones puras + llamadas HTTP a Graph. Sin Flask.
  - `url_dialogo(state, redirect_uri) -> str`
  - `cambiar_code_por_token(code, redirect_uri) -> dict` (token + tipo)
  - `listar_activos(token) -> {"ad_accounts": [...], "pages": [...]}`
  - `guardar(cliente, datos)` / `cargar(cliente)` / `borrar(cliente)`
    (escritura atómica: tmp + `os.replace`)
  - `estado(cliente) -> "sin_conectar" | "conectado" | "roto"` — hace **una**
    llamada barata (`/me?fields=id`) y cachea el resultado por proceso 10
    minutos, para no pegarle a Meta en cada carga de página.
- **`dashboard.py`**: cuatro rutas nuevas (conectar, callback, elegir GET/POST,
  desconectar) y `capacidades_meta` en el contexto de `ver_cliente`.
- **`meta_ads/auth.py`** y **`uploaders/meta_uploader.py`**: dejan de leer
  `os.environ` para el token/ids del cliente; reciben el cliente y leen
  `meta_conexion.cargar(cliente)`. `_cargar_entorno_cliente` sigue existiendo
  para los otros `.env` (YouTube/TikTok), pero ya no carga nada de Meta.
- **`templates/_tab_ads.html`**: se parte en `_meta_conectar.html` (bloque de
  estado/botón) + el contenido actual, que solo se renderiza si
  `capacidades_meta.estado == "conectado"`.

## Flujo detallado

### 1. Conectar

`GET /cliente/<c>/meta/conectar` (requiere sesión con acceso a `<c>`, como
toda ruta con cliente):

1. `state = secrets.token_urlsafe(32)`; se guarda `session["meta_oauth"] =
   {"state": state, "cliente": c}`.
2. Redirige a `meta_conexion.url_dialogo(state, REDIRECT_URI)`:

   ```
   https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth
     ?client_id={META_APP_ID}
     &config_id={META_LOGIN_CONFIG_ID}
     &redirect_uri={REDIRECT_URI}
     &state={state}
     &response_type=code
   ```

   `config_id` reemplaza a `scope` (Facebook Login for Business); la
   configuración, creada en el panel de la app, define: tipo de token =
   *Business integration system user*, sin expiración, y los permisos
   `ads_management`, `ads_read`, `business_management`, `pages_show_list`,
   `pages_read_engagement`, `pages_manage_posts`, `publish_video`,
   `instagram_basic`, `instagram_content_publish`.

   ⚠️ **Por confirmar en la primera tarea del plan**, contra
   `developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow` y
   la página de Facebook Login for Business: si el diálogo exige además
   `override_default_response_type=true` cuando la configuración pide token de
   usuario del sistema. La doc consultada el 2026-09-11 confirma `config_id` y
   el intercambio por `code`, pero no muestra la URL completa.

`REDIRECT_URI` sale de `META_REDIRECT_URI` en el `.env`:
`http://localhost:5050/meta/callback` en desarrollo (Meta permite HTTP solo en
`localhost` y solo con la app en modo desarrollo) y
`https://app.creatvmachine.com/meta/callback` en producción. Las dos van
registradas en "Valid OAuth Redirect URIs" de la app, con coincidencia exacta.

### 2. Callback

`GET /meta/callback` — **sin `<cliente>` en la URL** (Meta manda a una sola
URL registrada), así que el guard general no aplica: la ruta valida por su
cuenta que `session["meta_oauth"]` exista, que `state` coincida, y toma el
cliente de la sesión, nunca de la query.

1. Si viene `error` (el usuario canceló, o negó permisos): flash con el
   `error_description` de Meta, redirige a FlowMarketing. Nada se guarda.
2. `meta_conexion.cambiar_code_por_token(code, REDIRECT_URI)`:
   `GET https://graph.facebook.com/{v}/oauth/access_token?client_id&client_secret&redirect_uri&code`
   (servidor-a-servidor; el `client_secret` nunca sale del servidor).
3. `GET /me?fields=id,name,client_business_id` con ese token — confirma que el
   token sirve y da el negocio del cliente.
4. `meta_conexion.listar_activos(token)`: cuentas publicitarias y Páginas a las
   que el token tiene acceso, cada Página con su `access_token` de Página e
   `instagram_business_account`.

   ⚠️ **Por confirmar en la primera tarea del plan**: los endpoints exactos de
   listado. Candidatos: `GET /me/adaccounts?fields=id,name,account_status,currency`
   y `GET /me/accounts?fields=id,name,access_token,instagram_business_account`
   (los que ya usa `auth_meta.py`). Para un token de usuario del sistema puede
   ser `GET /{client_business_id}/owned_ad_accounts` + `client_ad_accounts` y
   `owned_pages`. Se decide con una llamada real, no por lectura.
5. Guarda lo listado en `session["meta_oauth"]["activos"]` (no en disco
   todavía) y redirige a `/cliente/<c>/meta/elegir`.

### 3. Elegir cuenta y Página

`GET /cliente/<c>/meta/elegir`: formulario con dos radios — una cuenta
publicitaria y una Página — mostrando nombre, id, moneda y estado de cuenta, y
el Instagram vinculado de cada Página (o "sin Instagram vinculado"). Si el
token no ve ninguna cuenta publicitaria, se dice claro qué hacer ("tu usuario
no administra ninguna cuenta publicitaria — pídele acceso al administrador de
tu Business Manager") y no se guarda nada.

`POST /cliente/<c>/meta/elegir`: valida que los ids elegidos estén en la lista
de la sesión (nunca se acepta un id que no vino de Meta), y llama
`meta_conexion.guardar(cliente, datos)`. Limpia `session["meta_oauth"]`.
Redirige a FlowMarketing con "Meta conectado: cuenta X · Página Y".

### 4. Desconectar

`POST /cliente/<c>/meta/desconectar`: `meta_conexion.borrar(cliente)` y flash:
"Desconectado. La app sigue autorizada en tu Facebook hasta que la quites en
Configuración › Integraciones de negocio". No se intenta revocar en Meta
(evita una llamada que puede fallar y dejar un estado a medias).

## Modelo de datos — `clientes/<cliente>/meta.json`

```json
{
  "token": "EAAG…",
  "tipo_token": "business_integration_system_user",
  "expira_en": null,
  "business_id": "1234567890",
  "ad_account_id": "act_987654321",
  "ad_account_nombre": "Happy Flops Ads",
  "moneda": "COP",
  "page_id": "1122334455",
  "page_nombre": "Happy Flops",
  "page_access_token": "EAAG…",
  "ig_user_id": "17841400000000000",
  "scopes": ["ads_management", "ads_read", "…"],
  "conectado_en": "2026-09-12T10:22:00",
  "conectado_por": "happyflops",
  "graph_version": "v25.0"
}
```

- `ad_account_id` se guarda **con** el prefijo `act_` (es como lo devuelve
  Meta y como lo piden los endpoints); `meta_ads/auth.ad_account_id()` deja de
  agregarlo.
- `page_access_token` es el que devuelve `/me/accounts` para esa Página; con un
  token de usuario del sistema sin expiración, el de Página tampoco expira
  (por confirmar en la primera conexión real; si expira, se marca "roto").
- `expira_en`: `null` para tokens sin expiración; si Meta devolviera
  `expires_in`, se guarda la fecha para que `estado()` avise antes.
- El archivo va a `.gitignore` (`clientes/*/meta.json`) **antes** de que exista
  el primero, junto con `META_LOGIN_CONFIG_ID` y `META_REDIRECT_URI` en
  `.env.example`.
- Escritura atómica: se escribe a `meta.json.tmp` y se hace `os.replace`.
  Mismo patrón que pide el plan maestro para el resto de JSON; acá no es
  opcional porque el archivo contiene un token.

## Cambios en los consumidores del token

- `meta_ads/auth.py`: `llamar(...)` y `ad_account_id()` reciben `cliente` (o
  se llama `configurar(cliente)` una vez al inicio del job, que carga
  `meta.json` en variables de módulo protegidas por el `_ENV_LOCK` existente).
  Se elige la segunda forma: los jobs ya se ejecutan dentro de `with
  _ENV_LOCK`, así que `configurar(cliente)` dentro de ese bloque mantiene el
  aislamiento entre clientes sin cambiar la firma de las cinco funciones de
  creación ni sus `dry_run`.
- `uploaders/meta_uploader.py`: `_token()`, `_page_id()`, `_ig_user_id()` leen
  de `meta_conexion.cargar(cliente)`; `publicador.publicar_brief` ya recibe el
  cliente.
- Una sola constante `GRAPH_VERSION` compartida (v25.0) en `meta_conexion.py`;
  `auth_meta.py` (v21) y `meta_uploader.py` (v21) pasan a importarla.
- `auth/auth_meta.py` y `auth/auth_meta_ads.py` se **borran** en la última
  tarea del plan, con el commit propio y `SETUP.md`/`CLAUDE.md` actualizados
  (hoy los documentan como el único camino). El historial de git es el
  respaldo.

## Capacidades y estado en FlowMarketing

`ver_cliente` pasa `capacidades_meta = meta_conexion.estado(cliente)` con
forma `{"estado": "sin_conectar" | "conectado" | "roto", "detalle": {...}}`.

| Estado | Qué se ve |
|---|---|
| `sin_conectar` | Solo el bloque "Conecta tu cuenta de Meta": qué va a pedir (anuncios + publicar en tu Página e Instagram), botón "Conectar con Meta". Sin cola, sin formulario. |
| `conectado` | Línea "Cuenta X · Página Y · Instagram Z · conectado el D" + "Desconectar"; debajo, la cola y publicados actuales sin cambios. |
| `roto` | Aviso: "Meta ya no acepta la conexión de este proyecto (token revocado o permiso retirado)" + "Volver a conectar". La cola se ve pero sin botón de publicar. |

`estado()` distingue `roto` de un fallo de red: solo un error de Meta con
código 190 (token inválido) o 10/200 (permiso) marca `roto`; un timeout deja
el estado anterior y no cambia nada.

Esto cierra el hallazgo crítico #4 de la auditoría del 2026-09-11.

## Quién puede conectar

- **Hoy (app en modo desarrollo):** Meta solo deja autorizar a usuarios con
  rol en la app. El administrador agrega a cada cliente como *Tester* en
  App Dashboard › App roles (por nombre o ID de Facebook); el cliente acepta la
  invitación en su Facebook y ya puede conectar con permisos completos, sin
  App Review. El texto del bloque "sin conectar" lo dice: "Si el botón te
  muestra un error de permisos, pídenos que agreguemos tu Facebook a la app".
- **Después (app en Live):** cuando pase App Review de los permisos listados y
  la Verificación de negocio, cualquier persona conecta sin ese paso. No
  cambia una línea de código.

## Manejo de errores

Mismo patrón que el resto del proyecto: el mensaje real de Meta llega al
usuario (flash) y a la bitácora (`bitacora.registrar(cliente, "meta",
"conexion", "error", str(e))`), **nunca** con un token adentro —
`meta_conexion` construye sus propias excepciones (`MetaConexionError`) a
partir del JSON de error de Graph, y las excepciones de red se envuelven como
en `meta_ads/auth.py` (solo el nombre del tipo).

Casos cubiertos: usuario cancela el diálogo; `state` no coincide o sesión
vencida (se pide reintentar); `code` inválido o ya usado; token sin cuentas
publicitarias; token sin Páginas; Página sin Instagram (se conecta igual y se
avisa que Instagram no va a funcionar); `meta.json` corrupto (se trata como
`sin_conectar` y se registra).

## Seguridad

- `state` obligatorio y de un solo uso; el cliente del callback sale de la
  sesión, no de la URL.
- `META_APP_SECRET` solo se lee en `cambiar_code_por_token`; nunca en logs,
  errores, plantillas ni `dry_run`.
- `meta.json` con permisos `0600` y en `.gitignore`; nunca se copia a un
  artefacto ni se muestra: la UI enseña nombres e ids, jamás tokens.
- El callback responde con redirect, nunca renderiza el `code`.
- La ruta de callback no está bajo la protección temporal del HTML (D1 del
  plan maestro): igual que `/.well-known/acme-challenge/`, va en la lista de
  excepciones de Nginx cuando se despliegue.

## Testing

No hay suite (ver `CLAUDE.md`). Por tarea: `python3 -m py_compile` y una
prueba dirigida. Además:

- `meta_conexion.url_dialogo` y `guardar/cargar/borrar` se prueban con
  `python3 -c` sin red (URL exacta, archivo atómico, permisos 0600).
- La primera conexión real la hace el administrador con su propia cuenta (es
  admin de la app, así que funciona en modo desarrollo). Criterio: `/me`
  responde, `meta.json` existe, FlowMarketing muestra "Conectado".
- Primera campaña real: en cuenta *sandbox* si el panel deja crearla; si no,
  campaña PAUSED de USD 1 en cuenta real. Es la primera vez que
  `MAPEO_OBJETIVO` (adset) se valida contra Meta.

## Prerrequisitos humanos (antes de la primera tarea de código que llame a Meta)

1. Business Manager propio y **Verificación de negocio arrancada** hoy — es
   el trámite más lento y no depende de nada más.
2. App en developers.facebook.com, tipo *Business*, con los productos
   *Facebook Login for Business* y *Marketing API*. `META_APP_ID` y
   `META_APP_SECRET` al `.env` (laptop y VPS).
3. En Facebook Login for Business › Configurations: una configuración con
   token *Business integration system user*, sin expiración, y los permisos
   de la sección "Conectar". Su id → `META_LOGIN_CONFIG_ID`.
4. Valid OAuth Redirect URIs: `http://localhost:5050/meta/callback` y
   `https://app.creatvmachine.com/meta/callback`. La segunda exige el VPS
   con certificado (7 pasos pendientes del despliegue).
5. Cuenta publicitaria con método de pago en tu Business Manager (para
   probar tú), e intentar crear una *sandbox* desde el panel.
6. Por cada cliente mientras la app esté en desarrollo: agregarlo como
   *Tester*.
7. App Review (con grabación del flujo, solo posible cuando el botón exista)
   → Live.

## Verificación real (2026-09-12, cuenta ForjaPlayer Habit como tester)

Primera conexión de punta a punta con la app "Creatv Machine" (ID 2079910829579733,
modo desarrollo) sobre el proyecto `forja`:

- **Diálogo**: `url_dialogo()` con `config_id` + `override_default_response_type=true`
  abre Facebook Login for Business sin error y devuelve `?code=` al callback.
  **Verificado: el parámetro es válido y requerido tal como está.**
- **Intercambio**: `cambiar_code_por_token` devolvió un token de usuario del sistema
  de 338 caracteres, `token_type=bearer`, **sin `expires_in`** (`expira_en: null`).
  **Verificado: el token no expira.**
- **Listado**: `/me/adaccounts` y `/me/accounts` funcionan con el token de sistema y
  devuelven la cuenta y la Página compartidas en el diálogo (incluido el
  `access_token` de Página, 200 caracteres). **No hizo falta cambiar a los edges
  del negocio.**
- **Instagram**: `/me/accounts` NO trajo `instagram_business_account` aunque la
  cuenta `forja.habit` se compartió en el diálogo. Causa: el token solo tiene
  `ads_management, ads_read, business_management, pages_read_engagement,
  pages_show_list, public_profile` — falta `instagram_basic` (los 4 permisos de
  publicación orgánica no estaban disponibles al crear la configuración de login;
  se agregan desde Use cases › Página / Instagram › Customize). Hasta entonces la
  app muestra "sin Instagram vinculado" y los Reels no se publican. No afecta anuncios.
- **Primera llamada de anuncios** (`act_2122370558355633`): cuenta Forja Habit,
  COP, `account_status=1`, `America/Bogota`, gasto 0, 0 campañas. **Verificado:
  `ads_management`/`ads_read` operativos con el token de sistema.**
- **Cuenta publicitaria nueva desde el diálogo**: funciona (Meta la crea dentro del
  flujo pidiendo país, sitio web, divisa y zona horaria). La divisa es permanente.
  Meta puede interponer un control "nuevo dispositivo o ubicación" que exige
  confirmar identidad (Google/SMS) en Business Suite; tras confirmarla el diálogo se
  reinicia y hay que volver a elegir los activos.
- **Modo desarrollo**: una cuenta sin rol recibe `error=access_denied` y la pantalla
  "La app no está activa". Agregarla como Tester (App roles) + aceptar la
  invitación en developers.facebook.com › Solicitudes lo resuelve. Cualquier
  cliente sin ese paso requiere App Review + Verificación de negocio (ver
  docs/meta/app-review-solicitud.md).
- **Sandbox**: no probado (no hizo falta: la cuenta real quedó en 0 gasto).
- **Plazo de verificación de negocio**: pendiente; aún no iniciada.

## Próximos pasos

1. Usuario: prerrequisitos 1 y 2 (hoy). Sin App ID no hay tarea de código
   que pueda probarse contra Meta.
2. Plan de implementación (writing-plans) con la primera tarea dedicada a
   cerrar las cuatro incógnitas técnicas con llamadas reales usando la
   cuenta del administrador.
3. Después de conectada la primera cuenta: primera campaña PAUSED real y
   cierre del bug de `video_id`.
