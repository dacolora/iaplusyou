# El cliente elige cómo conectar Meta — diseño

Fecha: 2026-09-20. Estado: aprobado en conversación por Daniel (secciones 1–6 del
diseño presentado en chat). Complementa los ADR 0001 (app por proyecto) y 0002 (modo
agencia) y cambia una regla del 0002 (§4); el ADR 0003 se escribe con la implementación.
Respaldo documental: `docs/meta/investigacion-requisitos-meta-plataforma-2026.md`
(requisitos reales de Meta, con la URL de cada afirmación).

## 0. Por qué

Hoy la forma por defecto de conectar Meta es la del ADR 0001: el cliente crea su propia
app en developers.facebook.com, elige casos de uso, arma una configuración de Facebook
Login for Business, pega la URI de retorno y registra tres datos. La guía en pantalla ni
siquiera dice que la app debe pasar a modo Live: el 2026-09-20 el primer experimento de
`colorado_forja` («Prueba 1») falló al crear el anuncio con el subcódigo 1885183 («la
publicación se creó con una app en modo de desarrollo»). Además el token de usuario caduca
a los 60 días. Un cliente normal no va a pasar por eso, y Daniel tampoco quiere que lo
intente.

El modo agencia del ADR 0002 evita todo eso (el cliente comparte sus activos con el
Business de Creatv como con cualquier agencia y el token de Creatv no caduca), pero hoy lo
activa solo el admin desde `/admin/meta`, y el cliente ni lo ve ni lo elige.

Decisión: **el cliente elige la forma de conectar**, con guía paso a paso en las dos, y
la forma «Que Creatv lo gestione» es autoservicio: el cliente termina conectado sin
esperar al admin, y el admin solo entra como respaldo. Nada de esto toca el motor:
`meta_conexion.cargar()` sigue siendo la única puerta y los consumidores (lanzador,
orgánico, insights, Pixel) siguen sin distinguir modos.

Vocabulario: **forma** es lo que el cliente eligió (`agencia` | `propia`), guardado en
`clientes/<c>/proyecto.json`; **modo** sigue siendo el estado real de `meta.json`
(`meta_conexion.modo`). Antes de conectar hay forma sin modo; después coinciden. Si un
proyecto quedó conectado sin haber elegido (lo asignó el admin, o venía del ADR 0001), la
forma vigente es su modo.

## 1. La elección (Configuración › Meta)

La tarjeta Meta de Configuración (`_meta_conectar.html`) tiene cuatro estados:

- **Sin forma y sin conexión**: dos tarjetas lado a lado, cada una con botón «Elegir».
  - «Que Creatv lo gestione» · etiqueta *Recomendada* · «Cinco minutos. No creas nada en
    Meta. El acceso no caduca. Creatv solo ve lo que compartas y lo puedes revocar
    cuando quieras desde tu Business Suite.» Si la agencia no está conectada
    (`meta_agencia.conectada()` es False) la tarjeta se ve pero el botón está apagado con
    «Disponible en cuanto Creatv termine de activarlo»; el admin ve además el enlace a
    `/admin/meta`.
  - «Con mi propia app de Meta» · «Control total. Media hora. Creas una app en
    developers.facebook.com y la pasas a modo Live. Vuelves a conectar cada 60 días.»
- **Forma agencia, sin conexión**: guía y formulario del §2.
- **Forma propia, sin conexión**: guía corregida y formulario existente del §3.
- **Conectado (cualquier modo)**: lo de hoy (cuenta, Página, Instagram, desde cuándo,
  Desconectar) más «Cambiar de forma» (§4).

Persistencia: `proyectos.meta_forma(cliente)` → `"agencia" | "propia" | None` y
`proyectos.guardar_meta_forma(cliente, forma)` en `proyecto.json` (misma mecánica que
`correo_notificaciones`). Ruta `POST /cliente/<c>/meta/forma` (`forma=agencia|propia`,
`_mismo_origen()`), flash y vuelta a `#configuracion`. Elegir una forma no toca Meta ni
`meta.json`.

## 2. Forma «Que Creatv lo gestione» (autoservicio)

### 2.1 Guía en pantalla

Arriba, grande y con botón de copiar: el ID del Business de Creatv y su nombre
(`meta_agencia.publica()["business_id"]` / `business_nombre`). Luego cuatro pasos con los
nombres de menú tal como los muestra Meta en español:

1. Entra a business.facebook.com › **Configuración del negocio** › **Socios** › **Agregar**
   › **Dar acceso a un socio a tus activos** y pega el ID de Creatv. Si Meta te pide
   activar la autenticación en dos pasos del portafolio, hazlo: es requisito suyo para
   compartir activos.
2. Marca lo que Creatv va a operar: en **Cuentas publicitarias**, tu cuenta con
   «Administrar campañas»; en **Páginas**, tu Página con «Crear anuncios» y, si quieres
   publicar Reels y posts, también «Crear contenido»; en **Cuentas de Instagram**, tu
   cuenta con lo mismo (opcional).
3. Copia el **ID de tu portafolio comercial**: Configuración del negocio › **Información
   del negocio**.
4. Pégalo abajo y pulsa **Buscar mis activos**.

### 2.2 Buscar mis activos

Formulario GET (sin estado): `/cliente/<c>?agencia_portafolio=<id>#configuracion`, con
`refrescar=1` cuando el cliente pulsa «Volver a buscar». `ver_cliente` calcula
`agencia_activos` solo si la forma es `agencia` y el parámetro valida `^\d{5,20}$`.

`meta_agencia.activos_de_portafolio(portafolio_id, forzar=False)`:

- `listar_activos` pide además el dueño: cuentas con
  `fields=id,name,currency,account_status,business{id,name}` y Páginas con
  `fields=id,name,instagram_business_account{id,username},business{id,name}`
  (`business` existe en AdAccount, «The Business Manager, if this ad account is owned by
  one», y en Page, «The Business associated with this Page», que exige
  `business_management`). Se guarda en el mismo caché de 10 min.
- Devuelve solo cuentas y Páginas de origen `cliente` cuyo `business.id` es el portafolio
  pedido, excluyendo las cuentas ya asignadas a **otro** proyecto. El cliente nunca ve
  activos de otros clientes ni los propios de Creatv.
- Si ninguna Página trae `business` legible (Meta lo permite solo cuando quien generó el
  token administra la Página), el formulario muestra el campo «ID de tu Página» y la
  acepta únicamente si está en `client_pages`; el piloto (§7) dice cuál de los dos casos
  ocurre.

Resultado en la misma tarjeta: radio de cuentas (nombre · id · moneda), radio de Páginas
(nombre · @instagram si tiene) más «Sin Página (solo anuncios)», y botón **Conectar**.
Sin resultados: «Todavía no vemos activos compartidos desde ese portafolio. A veces Meta
tarda unos minutos: revisa que el ID de Creatv sea el de arriba y que hayas marcado la
cuenta y la Página», con «Volver a buscar» y «Avisar a Creatv» (§2.4).

### 2.3 Conectar

`POST /cliente/<c>/meta/agencia/conectar` (`portafolio_id`, `ad_account_id`, `page_id`
opcional). La ruta vuelve a calcular `activos_de_portafolio` y exige que los dos ids estén
ahí (nunca se confía en lo que mandó el navegador). Luego
`meta_agencia.asignar(cliente, ad_account_id, page_id, asignado_por="cliente:<usuario>",
portafolio_id=...)`, que además:

- rechaza con `MetaAgenciaError` («Esa cuenta publicitaria ya está conectada a otro
  proyecto; avísale a Creatv») si `ad_account_id` figura en `proyectos_asignados()` de
  otro cliente — una cuenta, un proyecto;
- guarda `portafolio_cliente_id` en `meta.json` (auditoría; nunca un token);
- borra la solicitud pendiente del proyecto si la había (§2.4).

Después: `bitacora.registrar(cliente, "meta", "agencia", "ok", ...)`, aviso al admin
`meta_conexion_cliente` (§2.5) y los mismos flashes que `admin_meta_asignar` (cuenta
cambiada, Página sin Instagram, sin Página). El proyecto queda en modo agencia con la
conexión propia anterior, si existía, en `propia_respaldo` (como hoy).

### 2.4 Respaldo: avisar a Creatv

`POST /cliente/<c>/meta/agencia/avisar` (`portafolio_id`, `ad_account_id` y `page_id`
como texto opcional, `nota` ≤ 500) → `meta_agencia.solicitar(cliente, datos)`: una fila
en `kv` con clave `meta_solicitud:<cliente>` (JSON: portafolio_id, ad_account_id,
page_id, nota, usuario, creado_en; una por proyecto, la nueva reemplaza a la anterior) y
aviso al admin `meta_solicitud`. Flash: «Listo: Creatv recibió tu solicitud y te avisa por
correo cuando quede conectado». La tarjeta muestra «Solicitud enviada el <fecha>» con
«Volver a buscar» (Meta pudo tardar) y «Cancelar solicitud» (`POST .../agencia/avisar/cancelar`).
`meta_agencia.solicitud(cliente)`, `solicitudes()` y `borrar_solicitud(cliente)`
completan el módulo; `asignar` y `desasignar` borran la del proyecto.

En `/admin/meta`, sección nueva **Solicitudes de clientes**: proyecto, portafolio, ids
escritos, nota, fecha, y el formulario de asignar de siempre con la cuenta y la Página
preseleccionadas cuando coinciden con un activo visible, más «Descartar».

### 2.5 Avisos al admin

`notificaciones.avisar_admin(tipo, asunto, cuerpo)`: manda el correo a cada usuario con
rol `admin` y correo verificado (`usuarios.cargar()`), deja bitácora en el cliente
`_admin`, nunca lanza; sin SMTP o sin correos solo queda la bitácora. Tipos nuevos en
`notificaciones.TIPOS`: `meta_solicitud`, `meta_conexion_cliente`, `meta_cambio_forma`.

## 3. Forma «Con mi propia app» (guía corregida)

Mismo formulario (`meta_app_guardar`) y mismo botón «Conectar con Meta»; cambia la guía:

1. Crea la app en developers.facebook.com/apps/creation (tipo **Negocio**) y elige tu
   portafolio comercial.
2. Casos de uso: **Crear y administrar anuncios (API de marketing)**, **Medir datos de
   rendimiento**, **Administrar todos los aspectos de tu Página** y, si vas a publicar
   Reels, **Administrar mensajes y contenido en Instagram**.
3. **Inicio de sesión con Facebook para empresas › Configuraciones**: crea una
   configuración con **token de usuario** (el de usuario del sistema no sirve: Meta lo
   excluye para el portafolio dueño de la app), activos Páginas y Cuentas publicitarias
   (e Instagram si aplica) y los permisos `ads_management, ads_read, business_management,
   pages_show_list, pages_read_engagement, pages_manage_ads, pages_manage_posts,
   instagram_basic, instagram_content_publish`. Copia el identificador de configuración.
4. **Inicio de sesión con Facebook para empresas › Configurar**: URI de
   redireccionamiento válido = `{{ meta_redirect_uri }}`.
5. **Configuración › Básica**: nombre, correo de contacto, URL de términos, URL de
   política de privacidad, ícono 1024×1024 sin logos de Meta, categoría, propósito y
   «Eliminación de datos» (URL con instrucciones). Copia el identificador de la app y la
   clave secreta.
6. **Arriba del panel, «Modo de la app»: pásala de Desarrollo a Live.** Sin esto Meta
   rechaza cada anuncio (subcódigo 1885183). En Live sin App Review solo pueden usar la
   app las personas con rol en ella: conecta con el Facebook que la administra.
7. Pega los tres datos aquí, guarda y pulsa «Conectar con Meta».

Nota fija bajo la guía: «Tu acceso caduca a los 60 días: cuando pase, esta tarjeta dirá
"Meta ya no acepta la conexión" y con "Volver a conectar" queda listo». El error
1885183 en un lanzamiento ya se traduce a esta instrucción (`lanzador.traducir_error_meta`,
2026-09-20). `SETUP.md` §3 se reescribe con estos mismos pasos.

## 4. Cambiar de forma (regla nueva; sustituye a la del ADR 0002)

El ADR 0002 decía que salir del modo agencia era decisión exclusiva del admin. Nueva
regla: **el cliente también puede, desde Configuración, mientras nada esté en marcha**;
el admin recibe un aviso.

- Botón «Cambiar de forma» en el estado conectado. Bloqueado (con el motivo) si el
  proyecto tiene experimentos en `experimentos.ESTADOS_VIVOS` (`experimentos.cargar`) o
  publicaciones orgánicas en `en_cola`/`publicando` (`organico.listar`): «Termina o cierra
  primero: N experimentos vivos · M publicaciones en curso».
- Propia → agencia: `guardar_meta_forma("agencia")` y se muestra la guía del §2; la
  conexión propia sigue viva hasta que el cliente conecta por agencia, momento en que
  `asignar` la guarda en `propia_respaldo`.
- Agencia → propia: `POST /cliente/<c>/meta/agencia/salir` → mismo bloqueo →
  `meta_agencia.desasignar(cliente)` (restaura `propia_respaldo` si lo había) +
  `guardar_meta_forma("propia")` + bitácora + aviso `meta_cambio_forma`. Si no había
  respaldo, el cliente ve la guía del §3.
- `meta_conexion.borrar`/`guardar`/`url_dialogo` siguen lanzando `ModoAgenciaError` en
  modo agencia: la única salida del modo agencia es `desasignar` (admin o cliente).
- `_estado_llaves` («Puesta a punto»): con forma agencia sin conexión muestra «conexión de
  agencia: pendiente de que compartas tus activos».

## 5. Módulos y rutas

- `proyectos.py`: `meta_forma`, `guardar_meta_forma`.
- `meta_agencia.py`: `listar_activos(forzar=False)` con `business{id,name}`;
  `activos_de_portafolio`; `asignar(..., portafolio_id=None)` con la regla «una cuenta,
  un proyecto»; `cuentas_asignadas()`; `solicitar`, `solicitud`, `solicitudes`,
  `borrar_solicitud` (kv `meta_solicitud:<cliente>`).
- `notificaciones.py`: `avisar_admin` y los tres tipos.
- `dashboard.py`: rutas `meta_forma`, `meta_agencia_conectar`, `meta_agencia_avisar`,
  `meta_agencia_avisar_cancelar`, `meta_agencia_salir`; contexto de `ver_cliente`:
  `meta_forma`, `agencia_publica` (id y nombre del Business, nunca token),
  `agencia_activos` (solo con `?agencia_portafolio=`), `agencia_solicitud`,
  `puede_cambiar_forma` y `motivo_bloqueo_forma`; contexto de `admin_meta`: `solicitudes`.
  Todas las POST pasan por `_mismo_origen()` y por `puede_acceder`.
- Plantillas: `_meta_conectar.html` se parte en `_meta_elegir_forma.html`,
  `_meta_agencia_cliente.html` (guía + búsqueda + resultados + solicitud) y
  `_meta_propia_guia.html`; `admin_meta.html` gana la sección de solicitudes.
- Seguridad: el cliente solo ve activos filtrados por su portafolio; los ids se revalidan
  en el servidor; ningún token llega a plantilla, flash, bitácora ni correo
  (`cola.sin_token` en cada mensaje de error de Meta); `portafolio_id` validado por
  regex; la llamada a Meta al buscar usa el caché de 10 min salvo «Volver a buscar».

## 6. La parte de Creatv, una sola vez (`docs/meta/puesta-en-marcha-agencia.md`)

Guía escrita para Daniel, en este orden, con lo que Meta exige según la investigación:

0. **Portafolio limpio.** Meta Business Support Home › estado de la cuenta del portafolio
   Creatv Machine (1444407330918092): si está restringido, «Solicitar revisión» (Meta
   responde en unas 48 h; la restricción del 2026-09-14 nació ahí, no en la app). Decidir
   si se sigue con ese portafolio o con uno nuevo.
1. **Verificación de negocio** (Business Suite › Centro de seguridad): nombre legal,
   dirección, teléfono y sitio HTTPS; certificado de Cámara de Comercio y RUT de la
   empresa. Hasta 14 días hábiles. No hace falta para pasar a Live, pero sí para no volver
   a caer en restricción y para subir de nivel.
2. **App de Creatv** (la actual si se levanta la restricción, o una nueva) tipo Negocio,
   casos de uso Marketing API + Páginas + Instagram, Configuración › Básica completa,
   URL de eliminación de datos, y **Modo de la app: Live**. Sin App Review: solo la usa
   el usuario del sistema de Creatv, que tiene rol por pertenecer al Business dueño.
3. **Usuario del sistema** «creatv» con rol administrador (Configuración del negocio ›
   Usuarios del sistema) y token generado con la app de Creatv, caducidad nunca, con los
   nueve permisos de `permisos_agencia`.
4. `/admin/meta` › **Conectar la agencia** (ID del Business + token).
5. **Piloto con Forja**: Forja Habit comparte `act_2122370558355633`, la Página y el
   Instagram con el ID de Creatv; en el proyecto `colorado_forja`, Configuración › Meta ›
   «Que Creatv lo gestione» › Buscar › Conectar; «Reintentar lanzamiento» de «Prueba 1».
   Si la cuenta compartida no aparece en el panel, asignarla al usuario del sistema en
   Business Manager (Usuarios del sistema › Asignar activos) y «Actualizar desde Meta».
6. **Full Access**: cuando la app lleve 500 llamadas exitosas en 15 días (el refresco de
   métricas cada 2 h lo cumple con dos o tres anuncios corriendo), App Dashboard ›
   Marketing API › «Upgrade». Sin video desde 2026-05-04.

## 7. Dudas que resuelve el piloto

1. Si `client_ad_accounts` / `client_pages` responden con el nivel Limited («No Business
   Manager access to manage ad accounts…»); si no, vale el respaldo manual del §2.4 y el
   admin asigna.
2. Si el token del usuario del sistema crea anuncios en una cuenta de socio con la app en
   Live y sin App Review (la lectura de Meta dice que sí; ninguna página lo escribe con
   esas palabras).
3. Si `business` viene en las Páginas de socios con ese token (si no, campo «ID de tu
   Página» del §2.2).
4. Si el usuario del sistema administrador ve los activos de socios sin asignarlos a mano.
5. Si «Prueba 1» acepta el video ya subido (`extra.meta_video_id`) con creativos nuevos; si
   Meta repite 1885183, se vacía ese id y se vuelve a subir.

## 8. Pruebas

- `tests/test_meta_agencia.py`: `activos_de_portafolio` filtra por dueño y excluye cuentas
  de otros proyectos; `asignar` rechaza la cuenta duplicada y guarda `portafolio_cliente_id`;
  solicitudes: crear, reemplazar, listar, borrar al asignar/desasignar; `listar_activos`
  pide `business{id,name}`.
- `tests/test_rutas_meta_forma.py` (nuevo): elegir forma; tarjeta apagada con agencia sin
  conectar; buscar muestra solo activos del portafolio; conectar revalida ids y crea la
  conexión; avisar crea la solicitud y manda el correo (con `enviar` simulado); cancelar;
  salir bloqueado con experimento vivo y permitido sin nada en marcha; admin ve y descarta
  solicitudes; ningún token en el HTML.
- `tests/test_notificaciones.py`: `avisar_admin` elige solo admins con correo verificado y
  nunca lanza.
- Plantillas: la guía propia contiene «Modo de la app» y «Live»; la de agencia contiene el
  ID del Business.

## 9. Fuera de esta versión

- Inicio de sesión con Facebook dentro de Creatv para cualquier negocio (App Review con
  Advanced Access + Access Verification como Tech Provider): etapa 2, cuando haya clientes
  operando en agencia.
- Detectar por API si una app está en modo Desarrollo (Meta no lo expone).
- Aviso previo a la caducidad de 60 días en forma propia (hoy: estado `roto` + «Volver a
  conectar»).
- Que Creatv pida los activos al cliente desde su Business (el cliente los comparte).
- Wizard interactivo para la parte de Daniel: la guía escrita basta por ahora.
