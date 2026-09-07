# Migración a app Flutter — diseño y plan maestro

**Estado:** en discusión / listo para ejecutar F0 · **Última revisión:** 2026-09-06 ·
**Fase activa:** ninguna todavía (arranca en F0) ·
**Planes de ejecución por fase:** se crean en `docs/superpowers/plans/` cuando cada
fase arranca; enlazados desde el bloque 5.

En una frase cada una:

- **Qué se construye.** Una app Flutter (móvil primero) que habla con una API JSON
  nueva (`/api/v1`) servida por el MISMO `dashboard.py` de siempre, alojado en un VPS,
  con login y push vía Firebase.
- **En qué orden.** F0 trámites y decisiones bloqueantes → F1 endurecer el backend en
  la laptop → F2 esqueleto caminante contra el VPS real → F3 corte de datos y una
  semana operando con el HTML de siempre → F4 extracción a servicios + lecturas →
  F5 acciones que gastan → F6 v1 en uso real → F7 v1.1 → F8 v2 (Flutter Web y
  jubilación del HTML).
- **Qué NO se toca.** La lógica de generación y publicación existente. Las cinco
  excepciones a esa regla están enumeradas una por una en §4.1 — ninguna otra.
- **Qué falta decidir.** 14 decisiones abiertas, cada una con el hito antes del cual
  hay que cerrarla; ver §2.9. La bloqueante del día uno es la protección del
  dashboard HTML en el VPS.

Índice de los cinco bloques:

1. [Qué y por qué](#1-qué-y-por-qué)
2. [Arquitectura y decisiones](#2-arquitectura-y-decisiones)
3. [Contratos de v1](#3-contratos-de-v1)
4. [Fundaciones y operación](#4-fundaciones-y-operación)
5. [Plan de trabajo](#5-plan-de-trabajo)

**Regla de gobierno del documento.** La tabla de alcance (§1.5) manda sobre QUÉ entra
en cada versión — ninguna otra sección asigna versiones, solo referencia esa tabla. El
bloque 5 manda sobre el ORDEN. Este bloque de entrada es el único lugar que hay que
actualizar cuando cambia el estado, y se actualiza en el mismo commit que cierra una
fase. Ninguna subsección debe pasar de ~40 líneas: lo que crezca más baja al plan de
esa fase.

---

## 1. Qué y por qué

### 1.1 Contexto y motivo

Hoy `dashboard.py` solo es alcanzable desde `localhost` en la laptop del usuario — el
diseño explícito del proyecto (ver `CLAUDE.md`) es que corre en red local, sin
autenticación, confiando en que solo el admin lo abre. El usuario quiere poder aprobar
contenido, disparar ideas nuevas y manejar la pestaña Publicidad (Meta Ads) desde el
celular, en cualquier lugar — no solo sentado frente a la laptop que corre el servidor.

El usuario es desarrollador Flutter experto, así que el cliente móvil es **Flutter
nativo** (no una PWA ni un WebView del dashboard existente).

**Destino final, decidido explícitamente:** la app Flutter no es un complemento del
dashboard HTML — es su reemplazo. Las 5 pestañas que hoy existen en
`templates/cliente.html` (FlowClone, Publicidad, FlowPlus, FlowCatálogo, FlowSettings)
terminan viviendo en Flutter, compilado tanto a móvil como a **Flutter Web** (mismo
código, build distinta). El HTML de Jinja se jubila cuando ese reemplazo esté completo
— no se diseña para convivir indefinidamente. La prioridad de construcción es **móvil
primero**, porque el flujo de aprobación es el que más urge tener en el bolsillo.

### 1.2 El cambio real: de script local a servicio expuesto

Esta es la sección que justifica el orden de todo el plan. El riesgo dominante de esta
migración **no es Flutter** — el usuario es experto en eso. El riesgo es que
`dashboard.py` pasa de "servidor de desarrollo de Werkzeug, en localhost, sin
autenticación, con un solo humano mirando la pantalla" a "servicio en internet 24/7,
multiusuario, con hilos de fondo que gastan créditos y publican anuncios reales".

Supuestos del código actual que dejan de valer en ese momento (todos verificados):

| Supuesto de hoy | Dónde vive | Qué pasa en un VPS |
|---|---|---|
| Servidor de desarrollo de Werkzeug con `debug=True` | `dashboard.py:2354` | Ejecución de código arbitrario para quien alcance el puerto |
| `app.secret_key = "solo-local-no-hace-falta-secreto-real"` | `dashboard.py:72`, versionado en git | Cualquiera que lea el repo firma cookies de sesión válidas |
| 49 rutas `@app.route` sin ninguna verificación de identidad | todo `dashboard.py` | Varias gastan créditos y crean campañas de Meta con presupuesto real |
| Escritura JSON en modo `"w"`, sin `os.replace` ni lock | `_json_store.py:18`, `ads.py:_guardar` | Proceso muerto o disco lleno = archivo truncado, sin copia |
| Estado de jobs solo en memoria, purgado a los 30 min | `trabajos.py:38`, `_EDAD_MAXIMA_TERMINADO` | Reinicio de systemd = jobs zombis; app en background = `desconocido` normal |
| `load_dotenv(..., override=True)` muta `os.environ` global | `dashboard.py:112` | Endpoints nuevos y frecuentes pisando credenciales de otro cliente |
| Todo el estado del negocio está en `.gitignore` | `.gitignore` | En el VPS no existiría ninguna otra copia |
| Nadie vigila nada porque el humano ve el proceso | — | Un fallo es invisible hasta que alguien abre la app y choca |

De ahí sale la regla que ordena el plan: **el backend se deja apto para producción
ANTES de exponerlo (F1), se expone y se prueba de punta a punta ANTES de construir
pantallas (F2–F3), y las pantallas se construyen sobre algo ya probado (F4–F8).**

### 1.3 Metas

- Una app Flutter (iOS/Android) que permite: iniciar sesión, ver los proyectos a los
  que el usuario tiene acceso, escribir ideas nuevas y disparar su generación,
  revisar/aprobar/rechazar prompts, imágenes candidatas y videos, y manejar la pestaña
  Publicidad completa (enviar a publicidad, ver métricas, pausar/activar).
- Que funcione **sin depender de que la laptop del usuario esté prendida** — incluidos
  los jobs de fondo.
- Notificaciones push cuando un job termina o falla.
- **Una sola implementación de cada acción**, invocada por las dos superficies (HTML y
  JSON), de modo que la paridad sea estructural y no dependa de disciplina. (Esto
  reemplaza a la meta original "cero reescritura, solo cambiar `render_template` por
  `jsonify`", que es falsa — ver §4.1.)
- Que el servicio sobreviva reinicios, despliegues y fallos de proveedor sin dejar
  estado zombi ni pérdida de datos.

### 1.4 Fuera del proyecto

Tres exclusiones definitivas. Lo que solo está diferido vive en la tabla de alcance,
no aquí.

- **Modo offline / sincronización diferida.** Sin conexión, la app muestra un error y
  un botón de reintentar — no hay cola local de cambios ni caché de escritura.
- **Multi-idioma.** La app queda en español, igual que el dashboard hoy.
- **Cambios a la lógica de generación y publicación existente**, más allá de la
  extracción a servicios (§4.1) y de las cinco excepciones que ese mismo apartado
  enumera.

### 1.5 Tabla de alcance por versión (fuente única de verdad)

Ninguna otra sección del documento asigna versiones. Se actualiza en el mismo commit
que cierra una fase, junto al bloque de entrada.

| Función | v1 | v1.1 | v2 | Nota |
|---|---|---|---|---|
| Login + lista de proyectos | ✅ | | | `GET /proyectos` devuelve `{id, nombre}` desde el día uno |
| Bandeja de aprobación | ✅ | | | Su composición exacta es la **decisión abierta D2** |
| Nueva idea (texto → 5 prompts) | ✅ | | | Formulario con personaje + plataformas, no texto libre |
| Imágenes candidatas (aprobar/regenerar/rechazar) | ✅ | | | "Rechazar imagen" es código nuevo, ver D8 |
| Videos: aprobar (publica) / rechazar | ✅ | | | |
| Publicidad (Meta Ads) | ✅ | | | Bloqueada por el `.env` de happyflops, ver D12 |
| Enviar a Publicidad (swap y video) | ✅ | | | Sin esto la cola de Publicidad no se llena desde el celular |
| Capacidades por cliente | ✅ | | | §3.4 |
| Listar personajes | ✅ | | | Hoy no hay ninguna ruta que lo exponga |
| FlowClone (swaps) | D2 | D2 | | 45 entradas hoy; su versión depende de D2 |
| FlowPlus (creative_flow) | | ✅ | | 3 entradas hoy |
| Ideas visuales (conceptos imagen-primero) | | ✅ | | 0 entradas hoy; ver D3 |
| FlowCatálogo (productos) | | ✅ | | |
| FlowSettings (marca, bitácora, informe) | | ✅ | | |
| Subida desde cámara/galería | D2 | ✅ | | Se adelanta a v1 solo si D2 mete FlowClone en v1 |
| Marca visual por proyecto (color, logo) | | ✅ | | |
| Alta de cliente nuevo desde la app | | ✅ | | Termina con el recordatorio de OAuth (§4.9) |
| Flutter Web | | | ✅ | |
| Jubilación del HTML de Jinja | | | ✅ | Se borra, no se deja inerte (D13) |
| Modo offline | | | | Fuera del proyecto (§1.4) |

**Mapa del estado: los siete archivos por cliente.** Es la garantía de que ninguna
familia de estado quede en tierra de nadie. Conteos reales de `clientes/happyflops/`
al 2026-09-06.

| Archivo | Qué contiene | Helper de lectura | Hoy | Llega en |
|---|---|---|---|---|
| `swaps.json` | FlowClone | `_swap_items` (`dashboard.py:1025`) | 45 (26 `listo`, 19 `error`) | D2 |
| `estado_videos.json` | Videos pendientes de publicar | bloque de `ver_cliente` (`dashboard.py:517-529`) | 2 (ambos `pendiente`) | v1 |
| `prompts_pendientes.json` | Ideas de texto y sus prompts | `_ideas_pendientes` (`dashboard.py:420`) | 0 (`{}`) | v1 |
| `ads.json` | Publicidad | `ads_mod.cargar` directo en `ver_cliente` | **no existe todavía** | v1 |
| `creative_flow_pendientes.json` | FlowPlus | `_creative_flow_items` (`dashboard.py:1043`) | 3 (2 `video_listo`, 1 `prompt_pendiente`) | v1.1 |
| `conceptos_pendientes.json` | Ideas visuales imagen-primero | `_conceptos_pendientes` (`dashboard.py:820`) | 0 (`{}`) | v1.1 (D3) |
| `productos.json` | FlowCatálogo | `catalogo_productos` | 4 | v1 lectura / v1.1 escritura |

### 1.6 Por qué este orden: riesgo primero

**Por qué endurecer el backend va antes que el VPS.** Tres defectos verificados hoy
casi no duelen porque hay un humano frente a la pantalla, y en un VPS con
`Restart=always` y un despliegue por día pasan solos, de noche, sin que nadie los vea:
`_json_store.guardar` (`_json_store.py:18`) abre en modo `"w"` y trunca antes de
escribir; el job de video toma un snapshot con `prompts_mod.cargar` (`dashboard.py:1850`)
y reescribe el archivo entero ~130 s después (`:1904`); y `_reconciliar_huerfanos`
(`dashboard.py:2244`) solo repara `swaps.json`, `creative_flow_pendientes.json` y
`conceptos_pendientes.json` — **no toca** `prompts_pendientes.json`, `estado_videos.json`
ni `ads.json`, que son exactamente los tres archivos de la superficie de v1. Mover el
estado a un disco sin respaldo con un truncador suelto es la peor primera jugada
posible.

**Por qué el esqueleto caminante va antes que cualquier pantalla.** La cadena
Flutter → ATS/TLS → Nginx → Flask → `verify_id_token` → accesos → JSON del cliente →
FCM → celular tiene al menos cinco formas de fallar **en silencio**: certificado mal
emitido, reloj del VPS desfasado (rompe `verify_id_token`), llave APNs incorrecta (el
push simplemente no llega, sin error), reglas de Firestore, `proxy_read_timeout` corto
para el polling. Descubrir cualquiera de esas con la Bandeja ya construida encima es
semanas de trabajo sobre una suposición. Validarlas cuesta tres pantallas feas.

**Por qué el corte de datos va antes de las pantallas de producto.** Para no
desarrollar contra un estado que después hay que migrar, y porque F3 incluye una
semana operando desde el VPS **con el dashboard HTML de siempre**: eso valida hosting,
TLS, systemd, zona horaria, submódulos, respaldo y despliegue con **cero código nuevo
encima**, y su rollback es literalmente volver a abrir la laptop.

---

## 2. Arquitectura y decisiones

### 2.1 Diagrama general

```
Flutter (iOS/Android; luego Web)
        │  HTTPS + Firebase ID Token (Authorization: Bearer <token>)
        ▼
Nginx (TLS, Certbot)
   ├── location /api/v1/        → abierto (autentica el propio backend)
   ├── location /.well-known/   → abierto (renovación del certificado)
   └── location /               → PROTEGIDO (decisión abierta D1) — rutas HTML
        │
        ▼  proxy_pass a 127.0.0.1:5050
gunicorn -w 1 -k gthread --threads 8   (un solo worker, ver §2.3)
        │
Flask (dashboard.py) en un VPS Hetzner
   ├── rutas HTML de Jinja        ─┐
   ├── blueprint /api/v1          ─┴─► servicios/ (funciones puras, §4.1)
   └── clientes/<cliente>/*.json     (sin base de datos nueva en el VPS)

Firebase (un solo proyecto)
  ├── Authentication  → email/contraseña por persona
  ├── Firestore       → accesos (uid↔proyectos), dispositivos (tokens FCM)
  └── Cloud Messaging → push cuando un job termina o falla

Cloudflare R2  → binarios (igual que hoy) + respaldo cifrado diario (§4.3)
```

### 2.2 Por qué un solo proceso Flask y no microservicios

La lógica actual es **estado de proceso**: `trabajos.py` guarda los trabajos en un
dict en memoria (`_TRABAJOS`, `trabajos.py:38`) y los ejecuta en hilos daemon;
`_ENV_LOCK` (`dashboard.py:79`) sincroniza la carga de secretos por cliente; `ffmpeg`
opera sobre archivos en disco local (`_extraer_frame`, `dashboard.py:183`). Partir eso
en piezas separadas complica sin necesidad real a esta escala (un admin, pocos
proyectos) y obligaría a inventar una capa de coordinación que hoy no hace falta. Un
único proceso Python sirve tanto las rutas HTML como el blueprint `/api/v1`.

### 2.3 Por qué exactamente un worker (restricción arquitectónica, no preferencia)

**Decisión:** `gunicorn -w 1 -k gthread --threads 8 --timeout 120 dashboard:app`, sin
`--preload` (`firebase-admin`/gRPC no sobrevive bien al `fork`). `app.run(...)`
(`dashboard.py:2354`) queda solo para desarrollo local, con `debug=False` en el VPS.

Se escribe aquí, y se replica como comentario en `trabajos.py` y en el unit de
systemd, porque la "optimización" obvia (subir workers, que es lo que recomienda
cualquier guía de despliegue) **rompe cuatro cosas sin dar un solo error visible**:

1. `_TRABAJOS` vive en memoria del proceso (`trabajos.py:38`), así que el polling
   caería en un worker que no conoce el job y devolvería `desconocido` de forma
   intermitente.
2. El guardado anti-doble-clic de `trabajos.iniciar` (`trabajos.py:108`) deja de
   funcionar entre procesos: dos toques desde el celular = dos generaciones = doble
   crédito.
3. `_ENV_LOCK` es un `threading.Lock` de proceso: dejaría de serializar nada, que es
   exactamente el bug de credenciales cruzadas que cerró el commit `453faa3`.
4. `if __name__ == "__main__"` no se ejecuta bajo WSGI, así que
   `_reconciliar_huerfanos` (`dashboard.py:2244`) nunca correría. Por eso F1 la saca
   de ahí.

*No verificado:* que `-w 1 --threads 8` alcance en carga real. Con un admin y pocos
proyectos es holgado, pero nadie lo midió.

### 2.4 Por qué Firebase para auth, accesos y push

Las notificaciones push requieren un proyecto de Firebase **de todas formas** — no hay
forma de mandar push a iOS/Android sin pasar por FCM. Dado que el proyecto de Firebase
ya es indispensable, usar también Firebase Auth evita escribir y mantener a mano
hashing de contraseñas, emisión/refresh de tokens y manejo de sesión (superficie
clásica de bugs de seguridad), y `FlutterFire` lo integra casi sin código del lado de
la app. Firestore reemplaza lo que hubiera sido una base SQLite nueva en el VPS: el
servidor queda sin base de datos local, solo los JSON de siempre.

El costo que trae: una clave de service account de máxima potencia viviendo en el VPS
(§4.4).

### 2.5 Por qué un VPS y no ngrok ni serverless

ngrok sirve para **desarrollo** (iterar rápido apuntando la app a la laptop) y se
conserva explícitamente para eso (§4.8). Como arquitectura de producto depende de que
la laptop quede prendida y conectada 24/7 — si se suspende, la app deja de funcionar y
cualquier job en curso muere a la mitad. Un backend serverless o PaaS con escalado a
cero tiene el mismo problema: los hilos de `trabajos.py` y el estado en memoria no
sobreviven un reinicio del proceso entre requests. Un VPS con Nginx + systemd corre el
mismo proceso 24/7, sin reinventar cómo ya funciona el código.

### 2.6 Autenticación y accesos

- **Login**: Firebase Authentication (email/contraseña). La app manda el ID token en
  `Authorization: Bearer <token>`.
- **Verificación**: un decorador único `@requiere_acceso` verifica el token con
  `firebase_admin.auth.verify_id_token` y extrae el `uid`.
- **Autorización, en este orden y antes de tocar disco**: (1) hay un `<cliente>` en la
  URL — TODAS las rutas de `/api/v1` lo llevan, sin excepción, ver §3.1; (2) ese
  `cliente` está en `estado.listar_clientes()` (`estado.py:29`); (3) ese `cliente` está
  en la lista del `uid`. Recién entonces se construye una ruta de archivo — hoy
  `_client_dir` (`dashboard.py:108`) hace `os.path.join` con la cadena cruda. **Prohibido
  usar `<path:cliente>`** en el blueprint.
- **Fail-closed**: sin documento en `accesos`, cero proyectos.
- **Dispositivos**: un documento por token FCM, con su `uid`. Se escribe vía
  `POST /api/v1/dispositivos`.

### 2.7 Ciclo de vida de la sesión

Los ID tokens de Firebase **expiran a los 60 minutos por diseño**. La regla original
del spec ("un 401 se traduce a vuelve a iniciar sesión") produciría un cierre de sesión
falso cada hora. Cinco reglas:

1. La app pide `getIdToken()` en cada request y, ante un 401, reintenta **una vez** con
   `getIdToken(true)` antes de mandar al login.
2. El logout llama `DELETE /api/v1/dispositivos/<token>` **antes** de cerrar sesión en
   Firebase; si no, el celular sigue recibiendo push de proyectos que ya no puede ver.
3. Varios dispositivos por usuario están permitidos (un documento por token, no por
   uid) y no se limitan.
4. Revocar acceso = borrar el documento de `accesos`. No se usa `check_revoked=True`,
   que cuesta una consulta de red por request.
5. Auto-registro **desactivado** en la consola de Firebase; los usuarios se crean a
   mano (§2.8). Con email/contraseña habilitado y sin esto, cualquiera que extraiga la
   API key del APK puede registrarse solo.

Rendimiento: la lista de proyectos del uid va en **custom claims**
(`firebase_admin.auth.set_custom_user_claims`), no en una lectura de Firestore por
request — el polling de un video de 130 s son decenas de peticiones. Contrapartida
escrita: un cambio de accesos tarda hasta 1 h en propagarse, o se fuerza con
`revoke_refresh_tokens` al cambiarlo.

### 2.8 Firestore: colecciones, reglas y alta de usuarios

- `accesos`: un documento por `uid` con `{clientes: [...]}`.
- `dispositivos`: un documento por token FCM con su `uid`, plataforma y fecha.
- **Reglas de seguridad: `allow read, write: if false` para todo.** La app Flutter
  nunca habla con Firestore directamente; solo el backend, vía Admin SDK, que ignora
  las reglas. Eso hace que `accesos` sea inalterable desde el celular **por
  construcción**. Sin esta regla, un usuario podría editar su propio documento y
  concederse todos los proyectos, saltándose el fail-closed entero.
- **Alta de usuarios**: a mano en la consola (crear el usuario en Authentication,
  copiar su uid, crear el documento en `accesos`), documentado paso a paso en
  `SETUP.md`. Una pantalla de administración se evalúa cuando haya más de un puñado de
  personas.

### 2.9 Decisiones abiertas

Una entrada por decisión, con el hito antes del cual hay que cerrarla. Las que no
tienen opción recomendada las decide el usuario; donde hay recomendación, es para el
plan, no para reabrir lo ya cerrado.

**D1 — Protección del dashboard HTML mientras siga vivo. BLOQUEANTE, cerrar en F0,
antes del primer `certbot`.** El documento anterior la trataba como pendiente de v1;
cronológicamente el HTML queda expuesto en el instante en que Nginx sirve el 443, que
ocurre en la primera tarea de infraestructura. Lo que queda expuesto, dimensionado:
49 rutas sin ninguna verificación, entre ellas `POST /cliente/<c>/prompt/<id>/aprobar_imagen`
(`dashboard.py:1835`, ~8 créditos), `POST /cliente/<c>/ads/publicar` (`:1572`, crea una
campaña con presupuesto real), `POST /cliente/<c>/aprobar/<brief_id>` (`:1935`, publica
en YouTube/Facebook/Instagram/TikTok) y `POST /cliente/<c>/swap/generar` (`:1237`); más
`GET /` (`:384`) que redirige **directo** a `/cliente/happyflops`, y `app.secret_key`
como literal en git (`:72`).

| Opción | Qué protege | Costo de setup | Fricción diaria | Costo de revertir | Cuándo se retira |
|---|---|---|---|---|---|
| Tailscale | Todo, a nivel de red | Instalar el cliente en cada máquina | Alta si se usa desde varias máquinas | Bajo (config) | F8 |
| HTTP Basic Auth en Nginx | Rutas HTML, sobre TLS | Una directiva `auth_basic` | Baja (usuario/clave en el navegador) | Bajo (config) | F8 |
| HTML bajo Firebase Auth | Rutas HTML | Escribir una capa de sesión web en `dashboard.py` | Baja | **Alto: código que se borra en F8** | F8 |

Criterio de desempate para el plan (sin reabrir opciones): es una medida temporal para
código condenado a desaparecer, así que pesa el costo de reversión más que la
elegancia. Restricción que **ninguna opción resuelve sola**: la protección va por
bloque `location`, dejando fuera `/api/v1/`, `/.well-known/acme-challenge/` y
`GET /api/v1/estado`, o rompe la app y la renovación del certificado.

**D2 — Qué familias de estado componen la Bandeja de aprobación de v1. Cerrar en F0,
antes de congelar el contrato.** La decisión ya tomada dice "v1 = Bandeja + Ideas +
Publicidad", pero nunca dice qué contiene la Bandeja, y `ver_cliente`
(`dashboard.py:516-555`) renderiza **seis** familias. Los datos de disco importan:
`prompts_pendientes.json` está vacío (`{}`), `conceptos_pendientes.json` está vacío,
`estado_videos.json` tiene 2, mientras `swaps.json` tiene **45** y `ads.json` ni
existe. La API de v1 tal como estaba escrita se construyó alrededor del flujo que hoy
tiene cero uso, y omitía FlowClone, que además es una de las **dos únicas** formas de
que aparezca una fila en `ads.json` (`enviar_swap_a_publicidad`, `dashboard.py:1539`,
y `enviar_video_a_publicidad`, `:1554` — son los únicos llamadores de `ads_mod.crear`).
Dos salidas honestas: (a) incluir FlowClone en la Bandeja de v1, lo que adelanta
también la subida desde cámara; (b) declarar por escrito que v1 es un piloto de
arquitectura y que la laptop sigue haciendo falta para el trabajo diario hasta v1.1.
Lo que no se puede es dejarlo sin decidir: determina el tamaño de v1 y el contenido de
la pantalla principal.

**D3 — Si el pipeline de idea visual (`conceptos_pendientes.json` / `conceptos_imagen.py`)
entra o queda fuera. Cerrar en F0.** Hoy el documento anterior no lo mencionaba en
ninguna parte, pese a tener cinco rutas propias (`nueva_idea_visual` `:664`,
`aprobar_concepto_imagen` `:698`, `descartar_concepto_imagen` `:723`,
`generar_video_animacion` `:730`, `eliminar_idea_visual` `:855`). Dato para decidir:
`nueva_idea_visual` lanza 5 escenas × 2 proveedores = 10 imágenes de inmediato, y su
propio docstring dice *"El costo no se pregunta: se generan todas"* (`dashboard.py:667`)
— una excepción al principio central de `CLAUDE.md` que conviene reconocer antes de
exponerla en un botón de celular.

**D4 — `applicationId` de Android y bundle id de iOS. Cerrar en F0.** Punto de no
retorno: la llave APNs y `google-services.json` se atan a ellos, y una vez distribuida
la app, cambiarlos es una app nueva desde cero.

**D5 — Dominio definitivo. Cerrar en F0.** Queda compilado en la app y en el
certificado.

**D6 — Canal de distribución. Cerrar en F0.** Recomendación para uso interno:
TestFlight con testers internos + canal de pruebas internas de Play, sin tiendas
públicas. Motivo específico de este diseño: la revisión pública de Apple exige una
cuenta de demostración funcional, y el modelo fail-closed hace que cualquier cuenta sin
entrada en `accesos` vea una pantalla vacía — rechazo casi seguro por *minimum
functionality*. Decisión de secuencia derivada: **Android primero** para el Hito 0
(no depende de Apple), iOS cuando la inscripción esté aprobada.

**D7 — Zona horaria del VPS. Cerrar antes del corte de datos (F3), y aplicar antes de
que se escriba un solo dato.** Todo el proyecto usa `datetime.now()` sin zona y los ids
se derivan de ella (`ad_YYYYMMDD_HHMMSS_ffffff` en `ads.py:39`,
`idea_YYYYMMDD_HHMMSS_<slug>` en `prompts.py:83`, cada fila de `bitacora.registrar`).
El orden de las listas depende de esos valores (`sorted(..., key=lambda kv:
kv[1].get("generado_en", ""))`, `dashboard.py:519`). Hetzner viene en UTC: sin fijar la
zona, los datos nuevos quedan desplazados varias horas respecto de los existentes,
**dentro de los mismos archivos**. Recomendación: `TZ` explícito en el unit de systemd,
igual al huso de la laptop, con la razón escrita para que nadie lo "corrija" a UTC.
La migración a `datetime.now(timezone.utc)` es más limpia pero tocaría todos los
módulos: va a "sin agendar".

**D8 — Qué significa "Rechazar" en una imagen candidata. Cerrar antes de F5.** No
existe ninguna ruta `rechazar_imagen`. Las rutas de prompt son exactamente cinco:
`guardar_prompt` (`:1718`), `aprobar_prompt` (`:1796`), `regenerar_imagen` (`:1816`),
`aprobar_imagen` (`:1835`), `rechazar_prompt` (`:1914`). Hoy las únicas salidas cuando
la imagen no gusta son regenerar (gasta ~1.5 créditos otra vez) o `rechazar_prompt`,
que **borra el prompt entero**. Opciones: (a) mapear el botón a `regenerar_imagen` y
que diga "Generar otra (~1.5cr)"; (b) mapearlo a `rechazar_prompt` y que diga
"Descartar este prompt"; (c) crear una ruta nueva que borre `imagen_url` y devuelva el
prompt a `estado="pendiente"` sin gastar. Solo (c) da simetría real con las otras dos
etapas, y es **código nuevo, no reutilización** — debe figurar como tal en la tabla.

**D9 — `POST /ideas`: síncrono o job de fondo. Cerrar antes de F5.** Hoy `nueva_idea`
(`dashboard.py:573`) llama `generador_prompts.generar_prompts(...)` **dentro del
request** (`:588`) — es la única acción lenta del proyecto que no pasa por
`trabajos.iniciar`. Son 10-30 s de Anthropic; sobre red celular y con
`proxy_read_timeout` se corta, y como `prompts.agregar_idea` genera un `idea_id` nuevo
con timestamp cada vez (`prompts.py:83`), **cada reintento crea otra idea con otros 5
prompts y otra llamada facturada**. Recomendación: envolverlo en `trabajos.iniciar` y
devolver 202 con `job_id`. Es un cambio a la lógica existente y por eso hay que
autorizarlo explícitamente (queda en la lista de §4.1).

**D10 — `actualizar_resultados_ad` y `cambiar_estado_ad`: síncronas o jobs. Cerrar
antes de F5.** Hoy `actualizar_resultados_ad` (`:1656`) llama
`meta_insights.obtener_resultados` en línea dentro de `with _ENV_LOCK` (`:1666-1671`),
y `cambiar_estado_ad` (`:1678`) llama `meta_campaign.actualizar_estado` igual de
síncrono (`:1694-1703`). Pueden bloquear el request tanto por la latencia de la Graph
API como esperando el lock que retiene una publicación de otro cliente — en móvil eso
es un spinner indefinido sin `job_id` que consultar. Envolverlas es cambio a la lógica
existente: hay que decidirlo, o documentar el timeout del cliente Flutter.

**D11 — Qué se hace con los archivos servidos por `send_file` desde disco local.
Cerrar antes de la primera pantalla que los muestre.** Son tres rutas:
`imagen_producto` (`dashboard.py:868`), la variante por nombre (`:879`) y
`imagen_swap_original` (`:1519`, sirve `entry["foto_original_local"]`, que vive en
`salidas/<cliente>/swaps_subidas/`). En el VPS no existen si no se mueven, y la app no
puede mostrarlos sin autenticación. Opciones: subirlos a R2 como todo lo demás, o
servirlos por un endpoint autenticado de `/api/v1`.

**D12 — Crear `clientes/happyflops/.env` con `META_AD_ACCOUNT_ID`,
`META_PAGE_ACCESS_TOKEN` y `META_PAGE_ID`. Cerrar antes de F5.** Verificado: esa
carpeta **no tiene `.env` propio** hoy (ni `token_youtube.json` ni `token_tiktok.json`),
así que `capacidades` devolvería `meta_ads: false` y la fase de Publicidad no se puede
cerrar sin ese paso del usuario. Decidir aparte qué se hace con
`ENABLE_YOUTUBE/FACEBOOK/INSTAGRAM/TIKTOK`: verificado que se leen en **un solo lugar
de todo el repo**, `run_batch.py:61` (el CLI viejo) — ni `dashboard.py`, ni
`publicador.py`, ni ningún uploader las consultan (`publicador.publicar_brief` itera
sobre `entry["platforms"]`). Además viven en el `.env` **raíz**, o sea que son globales
del proceso: reportarlas como "capacidad por cliente" daría el mismo resultado para
todos. O se mueven a por-cliente, o se eliminan de `.env.example`.

**D13 — Qué se hace con las rutas HTML en v2. Cerrar antes de F8.** El documento
anterior dejaba la disyuntiva abierta ("se pueden retirar, o dejarse inertes sin
mantenimiento"). No es neutral: "inertes" combinado con "la protección temporal puede
retirarse porque ya nadie usa el HTML" deja 49 rutas de escritura sin autenticación en
un servidor público que nadie mira. Recomendación: se **borran**, en un commit propio,
después de `git tag html-final`. El historial de git es el respaldo.

**D14 — Cómo se fuerza una actualización de la app. Cerrar antes de la primera build
que salga del celular del desarrollador.** Una app instalada no se recarga como una
página, y en v2 la app es la **única** forma de operar el sistema. Recomendación:
`GET /api/v1/estado` público devuelve `{"version_api", "version_minima_app", "mensaje"}`
y la app lo consulta al arrancar. Es barato ahora e **imposible de agregar
retroactivamente** a una app ya instalada; por eso se implementa en F2, no en F6.

---

## 3. Contratos de v1

Este bloque se congela en F0 (`docs/api/v1.md` + `docs/api/ejemplos/*.json`) y a partir
de ahí solo admite cambios aditivos.

### 3.1 Convenciones de la API

- **Prefijo uniforme `/api/v1/proyectos/<cliente>/...`, sin excepciones**, incluido el
  de jobs. Motivo verificado: los ids son locales por cliente —
  `prompts.encontrar_prompt` (`prompts.py:112`) busca dentro del JSON de UN cliente, no
  hay registro global de prompts ni de briefs ni de ads. Sin `cliente` en la URL el
  servidor no sabe qué archivo abrir, **y la propia regla de autorización de §2.6 no
  tiene contra qué autorizar**.
- Peticiones `application/json`, salvo subida de archivos (`multipart/form-data`).
- Respuesta exitosa: `{"ok": true, "mensaje": "...", "datos": {...}, "job_id": "..."|null}`.
- Respuesta de error: `{"error": "<mensaje real>"}`, nunca genérico y **nunca con una
  credencial interpolada** (mismo incidente de la key de Gemini filtrada en
  `swaps.json`, misma regla que ya rige `meta_ads/auth.py:_sin_token`).
- Fechas ISO-8601 **con offset explícito** (hoy `datetime.now().isoformat()` no lo
  lleva).
- Listas: `?limite=50&desde=<cursor>` desde el día uno aunque hoy devuelvan todo —
  `swaps.json` ya son 45 entradas y crece sin límite.
- **Idempotencia por transición de estado.** Cada acción declara desde qué estado es
  válida y devuelve `409` con el estado actual si no coincide: `publicar` solo desde
  `en_cola`, `aprobar_prompt` solo desde `pendiente`, `aprobar_imagen` solo desde
  `imagen_pendiente`. El guardado de `trabajos.iniciar` solo cubre "mismo `job_id`
  todavía en curso", **no** el reintento después de que terminó, que es el caso normal
  en red móvil: un segundo `POST /ads/publicar` crearía una segunda Campaign + AdSet +
  Ad reales en Meta y pisaría `meta_ids`, dejando la primera huérfana y facturando sin
  que nadie la vea. Para creaciones sin estado previo (`POST /ideas`, `POST /swaps`),
  `idempotency_key` generada por la app y guardada en el JSON.
- **Compatibilidad:** dentro de `/api/v1` solo cambios aditivos (campos nuevos,
  endpoints nuevos). Cualquier ruptura sube `version_minima_app` (D14) o abre
  `/api/v2`.

### 3.2 Códigos de error y qué hace la app con cada uno

| Código | Cuándo | Reacción de la app |
|---|---|---|
| 400 | Datos faltantes o inválidos | Mostrar el mensaje junto al campo |
| 401 | Token ausente, inválido o expirado | **Un** reintento con `getIdToken(true)`; solo si vuelve a fallar, login |
| 403 | El uid no tiene ese proyecto en `accesos` | "No tienes acceso a este proyecto"; volver a la lista |
| 404 | Recurso inexistente dentro de un proyecto accesible | Recargar la lista |
| 409 | Transición de estado inválida | "Esto ya se hizo" + recargar la lista |
| 413 | Archivo demasiado grande | Mensaje legible con el límite |
| 500 | Error del servidor | Mensaje corto + botón de reintentar |

### 3.3 Superficie de la API v1

Todo bajo `/api/v1`. La columna "Servicio" apunta a la función pura que F4 extrae; el
nombre entre paréntesis es la ruta/función **real de hoy** de la que se extrae.

| Endpoint | Servicio (origen real) | Cuerpo | Devuelve `job_id` | Pantalla |
|---|---|---|---|---|
| `GET /estado` (público) | nuevo — salud + `version_api` + `version_minima_app` | — | no | arranque |
| `POST /dispositivos` · `DELETE /dispositivos/<token>` | nuevo — Firestore | token, plataforma | no | login/logout |
| `GET /proyectos` | `estado.listar_clientes` + `proyectos.nombre_visible` filtrado por accesos | — | no | Lista de proyectos |
| `GET /proyectos/<c>/capacidades` | nuevo — §3.4 | — | no | todas |
| `GET /proyectos/<c>/personajes` | `_personajes` (`dashboard.py:161`) — **hoy no hay ninguna ruta que lo exponga** | — | no | Nueva idea |
| `POST /proyectos/<c>/ideas` | `nueva_idea` (`:573`) | `idea`, `image_url`, `platforms[]`, `idempotency_key` | sí (D9) | Nueva idea |
| `GET /proyectos/<c>/prompts` | `_ideas_pendientes` (`:420`) | `?con_costo=0` | no | Bandeja |
| `POST /proyectos/<c>/prompts/<pid>/guardar` | `guardar_prompt` (`:1718`) | los 5 de `_aplicar_edicion` | no | Detalle |
| `POST /proyectos/<c>/prompts/<pid>/aprobar` | `aprobar_prompt` (`:1796`) | los 5 de `_aplicar_edicion` | sí (`_job_id_imagen`) | Detalle |
| `POST /proyectos/<c>/prompts/<pid>/regenerar_imagen` | `regenerar_imagen` (`:1816`) | ídem | sí (`_job_id_imagen`) | Detalle |
| `POST /proyectos/<c>/prompts/<pid>/aprobar_imagen` | `aprobar_imagen` (`:1835`) | ídem | sí (`_job_id_video`) | Detalle |
| `POST /proyectos/<c>/prompts/<pid>/rechazar` | `rechazar_prompt` (`:1914`) — **borra el prompt** | — | no | Detalle |
| `POST /proyectos/<c>/prompts/<pid>/rechazar_imagen` | **código nuevo** — no existe hoy (D8) | — | no | Detalle |
| `GET /proyectos/<c>/videos` | `_videos_para_ui` (extraer de `ver_cliente:517-529`) | `?limite=&desde=` | no | Bandeja |
| `POST /proyectos/<c>/videos/<brief_id>/aprobar` | `aprobar` (`:1935`) — **publica en redes** | — | sí (`_job_id_publicar`) | Detalle |
| `POST /proyectos/<c>/videos/<brief_id>/rechazar` | `rechazar` (`:1969`) — síncrona, coste cero | — | no | Detalle |
| `POST /proyectos/<c>/videos/<brief_id>/enviar_a_publicidad` | `enviar_video_a_publicidad` (`:1554`) | — | no | Detalle |
| `GET /proyectos/<c>/ads` | `ads.cargar` | `?limite=&desde=` | no | Publicidad |
| `POST /proyectos/<c>/ads/publicar` | `publicar_ad` (`:1572`) | `ad_id`, `objetivo`, `presupuesto_diario_usd`, `dias`, `pais`, `edad_min`, `edad_max`, `destino_url` | sí | Publicidad |
| `POST /proyectos/<c>/ads/<ad_id>/actualizar` | `actualizar_resultados_ad` (`:1656`) — **síncrona bajo `_ENV_LOCK`** | — | no (D10) | Publicidad |
| `POST /proyectos/<c>/ads/<ad_id>/estado` | `cambiar_estado_ad` (`:1678`) — **síncrona bajo `_ENV_LOCK`** | `estado`: `ACTIVE`\|`PAUSED` | no (D10) | Publicidad |
| `POST /proyectos/<c>/ads/<ad_id>/eliminar` | `eliminar_ad` (`:1708`) — solo borra la fila local | — | no | Publicidad |
| `GET /proyectos/<c>/swaps` · acciones | `_swap_items` (`:1025`), `generar_swap` (`:1237`), `eliminar_swap` (`:1532`), `enviar_swap_a_publicidad` (`:1539`) | multipart en generar | sí en generar | FlowClone (D2) |
| `GET /proyectos/<c>/trabajos/<job_id>` | `trabajos.consultar` (mueve `/trabajo/<path:job_id>/estado`, `:93`) | — | — | todas |
| `POST /dev/job_prueba` · `POST /dev/push_prueba` | nuevos, solo desarrollo | — | sí / no | Hito 0 |

**Correcciones respecto de la tabla anterior**, todas verificadas contra el código:

- **`POST /prompts/<pid>/generar_imagen` no existe** y se elimina. Aprobar el texto
  del prompt **ya lanza la imagen** en el mismo request: `aprobar_prompt` llama
  `_lanzar_generacion_imagen` (`dashboard.py:1773`), que envuelve
  `_generar_imagen_candidata` en `trabajos.iniciar` con
  `job_id = _job_id_imagen(cliente, prompt_id)` (`:391`). No son dos pasos. En cambio
  **falta `regenerar_imagen`** (`:1816`), que sí existe y es una acción distinta.
- **`POST /prompts/<pid>/rechazar_imagen` no existe.** Ver D8.
- **Todas las URL llevan `<cliente>`.** En el código no existe ninguna ruta de acción
  sin él (`/cliente/<cliente>/...` en las 49).
- **Las rutas de video invierten el orden**: `/cliente/<c>/aprobar/<brief_id>` y
  `/cliente/<c>/rechazar/<brief_id>` (verbo antes del id) — herencia de cuando el
  dashboard solo manejaba videos. Se normalizan en `/api/v1`. Nota para quien
  implemente: la función se llama `aprobar` a secas, fácil de confundir con
  `aprobar_prompt` / `aprobar_imagen`.
- **`aprobar`, `regenerar_imagen` y `aprobar_imagen` aceptan un cuerpo.** Llaman
  `_aplicar_edicion(item, request.form)` (`:495`) **antes** de gastar créditos, con
  cinco campos: `prompt`, `model` (validado contra `prompts_mod.MODELOS_VALIDOS`),
  `aspect_ratio` (contra `ASPECT_RATIOS_VALIDOS`), `duration` (int), `cfg_scale`
  (float). Un endpoint que ignore el cuerpo descarta en silencio la edición del usuario
  y le cobra créditos por el texto viejo.
- **`GET /prompts` no puede reutilizar `prompts.cargar`.** Esa función
  (`prompts.py:60`) devuelve el JSON anidado crudo. Lo que la pantalla necesita es
  `_ideas_pendientes` (`:420`), que filtra a `pendiente`/`imagen_pendiente`, adjunta
  `trabajo: {job_id}` y numera los prompts. **Trampa para móvil:** por cada prompt
  pendiente llama `estimate_image` o `estimate_video` — peticiones HTTP reales a
  Higgsfield, en serie, dentro del request (`:439-451`). De ahí el `?con_costo=0` para
  el listado; el costo se pide al abrir el detalle, que es cuando el usuario lo
  necesita para decidir (regla de `CLAUDE.md`: nunca un botón de generar sin su costo).
- **`GET /videos` no puede reutilizar `estado.cargar` a secas.** `ver_cliente`
  (`:517-529`) enriquece cada entrada con `plataformas_estado` (vía `_estado_plataformas`,
  `:365`, que lee la bitácora) y con `trabajo: {job_id}` de la publicación en vuelo. Sin
  lo primero, la app no puede mostrar "se publicó en YouTube pero falló Instagram", que
  es un caso real: `publicar_brief` devuelve `False` sin abortar y `aprobar` lo convierte
  en un `RuntimeError` **después** de marcar el video como publicado (`:1948-1955`).
- **Dos vocabularios de estado en Publicidad.** `cambiar_estado_ad` exige
  `ACTIVE`/`PAUSED` en mayúsculas (`:1681`), pero `ads.json` persiste español:
  `en_cola` (`ads.py:52`), `publicando` (`:1594`), `pausado`/`activo` (`:1698`),
  `error`. Si la app reenvía el valor persistido, siempre falla. Además `publicar_ad`
  **deja el anuncio en `pausado` a propósito** (todo se crea `PAUSED` en Meta, para
  revisarlo en Ads Manager antes de activarlo): la pantalla debe decirlo o el usuario
  creerá que ya está gastando.

### 3.4 Capacidades por cliente

`GET /api/v1/proyectos/<cliente>/capacidades`. Resuelve un problema concreto: hoy
happyflops no tiene cuenta de Meta Ads configurada, y si la app muestra Publicidad como
funcional, cada acción falla contra Meta después de llenar un formulario. Respuesta:

```json
{"meta_ads": false, "facebook": false, "instagram": false,
 "youtube": false, "tiktok": false,
 "vencimientos": {"meta_page_token": null, "youtube": null, "tiktok": null}}
```

Regla de UI: **gris con un mensaje accionable** ("Configura tu cuenta de Meta Ads"), no
oculto y no error tardío.

**Fuentes corregidas y verificadas:**

- `meta_ads` = `META_AD_ACCOUNT_ID` (`meta_ads/auth.py:ad_account_id`) **y**
  `META_PAGE_ACCESS_TOKEN` (`meta_ads/auth.py:_token`) **y** `META_PAGE_ID`
  (`meta_ads/creative.py:_page_id`, que revienta sin él). El documento anterior solo
  pedía el primero.
- `facebook` = `META_PAGE_ACCESS_TOKEN` + `META_PAGE_ID`
  (`uploaders/meta_uploader.py:_page_token` y `upload_to_facebook_page`).
- `instagram` = `META_PAGE_ACCESS_TOKEN` + `META_IG_USER_ID`
  (`uploaders/meta_uploader.py:upload_to_instagram_reel`).
- `youtube` = existe `clientes/<c>/token_youtube.json` (`_token_paths`, `dashboard.py:119`).
- `tiktok` = existe `clientes/<c>/token_tiktok.json` (ídem).
- **`ENABLE_TIKTOK` se elimina de la lista.** Es una bandera muerta: se lee en un solo
  lugar de todo el repo, `run_batch.py:61`. Ver D12.

**Regla de implementación, escrita porque el camino obvio es el equivocado:**
capacidades **NO usa `_cargar_entorno_cliente`** (`dashboard.py:112`), que hace
`load_dotenv(..., override=True)` y muta `os.environ` de todo el proceso — un endpoint
de solo lectura y alta frecuencia (la app lo llama al entrar a cada proyecto) tomaría
`_ENV_LOCK` y pisaría las credenciales globales mientras corre una publicación de otro
cliente, que es exactamente el bug que cerró `453faa3`. Usa
`dotenv_values(os.path.join(_client_dir(c), ".env"))`, que devuelve un dict sin efectos
secundarios, más `os.path.exists` para los tokens.

*Riesgo reconocido y no resuelto por este endpoint:* `load_dotenv` nunca borra claves,
así que si el proyecto A carga `META_AD_ACCOUNT_ID` y el proyecto B no tiene `.env`, B
hereda la variable de A dentro del proceso. El aislamiento de credenciales **entre
proyectos no está garantizado** para los jobs de publicación; agregar un segundo
proyecto con `.env` propio es un cambio de riesgo, no una operación de rutina. Queda en
el registro de deuda (§4.11).

### 3.5 Trabajos de fondo: contrato y ciclo de vida

**Regla central: la lista es la fuente de verdad del desenlace; el job es solo la barra
de progreso.** La app nunca depende de un job para saber si algo salió bien — cada
endpoint de lista devuelve el estado persistido en el JSON.

- Ruta: `GET /api/v1/proyectos/<cliente>/trabajos/<job_id>`, validando que el `job_id`
  empiece por `<cliente>__`. **Eso convierte el prefijo del `job_id` en contrato, no en
  detalle de implementación**, y hay que escribirlo: hoy conviven siete formatos —
  `f"{cliente}__marca__analizar"` (`:295`), `__imagen` (`:391`), `__video` (`:395`),
  `__publicar` (`:399`), `__creative_flow` (`:403`), los de concepto y animación con 4 y
  5 segmentos (`:607`, `:611`), `f"{cliente}__{swap_id}__swap"` (`:1276`) y
  `f"{cliente}__{ad_id}__ads_publicar"` construido inline (`:1601`).
- `estado: "desconocido"` es **normal** en móvil: `_TRABAJOS` vive en memoria
  (`trabajos.py:38`) y se purga a los 30 minutos (`_EDAD_MAXIMA_TERMINADO`), y hoy la
  ruta devuelve ese estado con HTTP 200 (`dashboard.py:98-104`). La app lo traduce a
  "no pude confirmar el resultado, revisa la tarjeta" y recarga la lista — nunca a un
  error ni a un spinner eterno.
- **Sanitización obligatoria del mensaje.** `trabajos.consultar` devuelve `str(e)`, y
  `higgsfield_client.py:143` lanza `RuntimeError(f"La generación falló: {data}")` con el
  JSON crudo del proveedor; los errores de `requests` incluyen la URL completa, que en
  R2/fal puede llevar parámetros firmados. El detalle completo va a la bitácora; al
  cliente le llega un mensaje corto. La promesa de §3.1 hoy **no se cumple** para los
  mensajes de job: esto la cumple.
- **Reconciliación al arrancar.** `_reconciliar_huerfanos` (`:2244`) se extiende a
  `prompts_pendientes.json`, `estado_videos.json` y `ads.json` (un ad en `publicando`
  queda así para siempre y `_tab_ads.html:9` lo clasifica como publicado vía
  `rejectattr("estado", "equalto", "en_cola")`), y se saca de
  `if __name__ == "__main__"` (§2.3).
- **Watchdog**: un job que supera N veces su `duracion_estimada` se marca como error y
  notifica. Es lo único que hace visible un job huérfano en una app que no ve la
  consola.

### 3.6 Notificaciones push

Cuando una función corrida vía `trabajos.iniciar` termina, además de guardar el
resultado dispara un push vía `firebase_admin.messaging` a los tokens de `dispositivos`
de los `uid` que tengan ese `cliente` en `accesos`.

**Cómo sabe el push a quién notificar.** `trabajos.iniciar(job_id, fn, duracion_estimada,
etapas)` no conoce cliente, tipo ni id: solo un `job_id` opaco y una closure. Parsear el
`job_id` es frágil (siete formatos, §3.5). **Decisión: parámetro aditivo
`notificar={"cliente":…, "tipo":…, "id":…}`** en `trabajos.iniciar`, guardado junto al
trabajo; `_run()` (`trabajos.py:143-159`) se lo pasa a un módulo nuevo `push.py` al
terminar, **en la rama de éxito y en la de excepción**. Es retrocompatible: los
llamadores que no lo pasen siguen funcionando.

Dos reglas de seguridad operativa, no negociables:

1. **El envío ocurre FUERA del bloque `with _LOCK`**, en un hilo aparte. Ese mismo lock
   lo toma `consultar()` (`trabajos.py:205`) en **cada** request de polling de **cada**
   usuario; una llamada de red a FCM adentro congelaría todas las barras de progreso.
2. **Envuelto en su propio `try/except`.** Un fallo de FCM jamás debe tumbar un job que
   ya gastó créditos — misma filosofía que el `reportar()` no-op silencioso que el
   módulo ya documenta.

El payload lleva `{cliente, tipo, id}` **más el desenlace** (`ok`/`error` y un mensaje
corto), porque el polling posterior puede llegar tarde y encontrar `desconocido`. Al
tocar la notificación la app navega directo a esa tarjeta, nunca a una pantalla
genérica.

Pendientes de FCM que hay que resolver: llave APNs `.p8` (sin ella el push en iOS
simplemente no llega, sin error, y no funciona en simulador); permiso de notificaciones
en iOS y Android 13+, con degradación elegante si el usuario lo niega (la app sigue
funcionando solo con polling); comportamiento en primer plano (FCM no muestra nada por
sí solo); `onTokenRefresh` → `POST /dispositivos`; borrado de los tokens que FCM
reporte como `UNREGISTERED` al enviar.

### 3.7 Pantallas de la app y qué consume cada una

1. **Login** — email/contraseña vía Firebase Auth. *Consume:* `GET /estado` al arrancar
   (D14), Firebase Auth, `POST /dispositivos`.
2. **Lista de proyectos** — *Consume:* `GET /proyectos`. Devuelve `{id, nombre}` desde
   v1: el id de carpeta es `happyflops` y el nombre visible es **"Happy Flow"**
   (`clientes/happyflops/proyecto.json`, vía `proyectos.nombre_visible`,
   `proyectos.py:29`). Si v1 devolviera solo `estado.listar_clientes()`, la app diría
   "happyflops" donde la web dice "Happy Flow".
3. **Bandeja de aprobación** — cola única con pull-to-refresh; tocar un item abre su
   detalle con Aprobar/Rechazar y el costo estimado visible antes de aprobar.
   *Consume:* `GET /prompts`, `GET /videos` (+ `GET /swaps` si D2 los incluye),
   `GET /capacidades`, `GET /trabajos/<job_id>`. La agregación de varias familias en una
   sola cola es trabajo real: se decide en D2 si la hace el servidor (endpoint
   `GET /bandeja`) o el cliente.
4. **Nueva idea** — **es un formulario, no un campo de texto libre.** `nueva_idea`
   (`dashboard.py:573-582`) exige `idea` **y** `image_url` (la foto del personaje; sin
   ella, error y redirect) y lee `platforms` con `request.form.getlist`, que alimenta
   `_aspect_ratio_para_plataformas` (`:562`) para fijar el `aspect_ratio` de los 5
   prompts. *Consume:* `GET /personajes`, `POST /ideas`, luego la Bandeja.
5. **Publicidad** — espejo de la pestaña web: cola "listos para publicar" con el
   formulario completo (objetivo, presupuesto diario USD, días, país, edad mín/máx, URL
   de destino) y "publicados" con métricas y Pausar/Activar, más el texto explícito de
   que publicar deja el anuncio **PAUSED** a propósito. *Consume:* `GET /capacidades`,
   `GET /ads`, las cuatro acciones de ads, `GET /trabajos/<job_id>`.

---

## 4. Fundaciones y operación

### 4.1 Los cambios que sí se hacen a la lógica existente

**La premisa "solo cambia `render_template(...)` por `jsonify(...)`" es falsa y hay que
decirlo antes de estimar.** Ninguna de las rutas de la tabla usa `render_template`:
`publicar_ad` (`:1572`) lee ocho campos de `request.form`, tiene la orquestación
Campaign→AdSet→Creative→Ad dentro de una closure, llama `flash()` y termina en
`redirect(url_for("ver_cliente", ...))`; `aprobar_prompt` (`:1796`) llama
`_aplicar_edicion(item, request.form)` — la edición está acoplada al objeto `request`;
`generar_swap` (`:1237`) lee `request.files`. Son 49 rutas en 2.354 líneas, sin ninguna
suite de tests. Esa extracción es la mayor parte del trabajo de servidor y la mayor
fuente de subestimación del plan.

**Regla de extracción (F4).** Por cada acción: una función pura en
`servicios/<dominio>.py` con firma `(cliente, ids, datos: dict) -> resultado` (o
excepción), **sin `request`, sin `flash`, sin `redirect`**. El handler HTML queda como
cáscara que parsea el formulario y llama al servicio. El endpoint `/api/v1` llama al
**mismo** servicio.

**Regla del commit único.** Extracción + reapunte del handler HTML + endpoint JSON van
en el **mismo commit**. Así las dos vías no pueden divergir y el commit es la unidad de
reversión. Es paridad estructural, no disciplina.

**Las cinco excepciones autorizadas a "no tocamos la lógica existente"** — esta lista
es cerrada:

1. **Escritura atómica** en `_json_store.guardar` (`_json_store.py:18`) y
   `ads._guardar` (`ads.py:34`): temporal en el mismo directorio + `os.replace`. Más un
   lock por ruta de archivo (§4.2).
2. **`_reconciliar_huerfanos` ampliada** a `prompts_pendientes.json`,
   `estado_videos.json` y `ads.json`, y sacada de `if __name__ == "__main__"`.
3. **Parámetro `notificar` en `trabajos.iniciar`** (§3.6), aditivo y retrocompatible.
4. **`app.secret_key`, `HOST` y `PUERTO` desde variables de entorno**
   (`dashboard.py:72`, `:2299-2300`), con fallback local.
5. **`POST /ideas` envuelto en `trabajos.iniciar`** (D9), si el usuario lo autoriza.

*Lo único que sí es reutilizable tal cual hoy es `_aplicar_edicion` (`:495`), que ya
acepta cualquier objeto tipo dict.*

### 4.2 Durabilidad y concurrencia del estado JSON

El patrón actual es `cargar()` → mutar → `guardar()` **sin ningún lock**, y
`_json_store.guardar` abre en modo `"w"`: trunca primero y escribe después. Dos fallas
que la app multiplica:

- **Lost updates.** El job de video carga `prompts_pendientes.json` al empezar
  (`dashboard.py:1850`) y reescribe el archivo **entero** ~130 s después (`:1904`);
  `_lanzar_generacion_imagen` hace lo mismo en ~45 s (`:1780-1788`); `ads.actualizar`
  también. Cualquier aprobación hecha desde el celular en ese lapso se pierde. Hoy es
  difícil porque hay una sola pestaña; con app + navegador + push que invita a actuar
  justo cuando termina un job, es el caso normal.
- **Corrupción.** Si el proceso muere o el disco se llena entre el truncado y el
  `json.dump`, el archivo queda vacío o partido — y no hay ninguna otra copia (§4.3).

**Solución mínima y suficiente:** `os.replace` atómico; `threading.Lock` por ruta de
archivo expuesto como context manager `con_bloqueo(path)` en `_json_store`, envolviendo
cada ciclo leer-mutar-guardar; y en los jobs largos, **releer y mutar solo la entrada
propia justo antes de guardar** en vez de reescribir el snapshot viejo. Un lock de
proceso alcanza **únicamente porque el worker es uno solo** (§2.3) — anotado así para
que se revise si algún día eso cambia.

### 4.3 Respaldo y restauración

Motivo: **todo el estado operativo está en `.gitignore`** — `clientes/*/estado_videos.json`,
`prompts_pendientes.json`, `conceptos_pendientes.json`, `swaps.json`, `ads.json`,
`creative_flow_pendientes.json`, `marca.json`, `clientes/*/.env`, `token_youtube.json`,
`token_tiktok.json`, `salidas/` y `registro_generaciones.csv`. Ese CSV es además la
fuente de verdad de `informe.py`, que existe para sustentar una cuenta de cobro:
perderlo es perder la evidencia de facturación. Hoy el respaldo de facto es "está en mi
laptop", y **ese respaldo desaparece en el momento del corte**. Señal de que ya duele:
hay un `clientes/happyflops/swaps.json.respaldo_20260904_023504` hecho a mano.

**Decisión:** cron diario en el VPS que empaqueta `clientes/**/*.json` +
`registro_generaciones.csv` + los `.env` y tokens, lo cifra (`age` o `gpg` simétrico) y
lo sube **al mismo bucket de R2 que ya está configurado**, bajo `backups/YYYY-MM-DD/`,
con retención de 30 días. Cero infraestructura nueva. La llave de firma de Android va
al mismo respaldo.

**Regla: un respaldo que nunca se restauró no es un respaldo.** El procedimiento de
restauración se documenta en `SETUP.md` y se prueba una vez en limpio **antes** del
corte (F3).

### 4.4 Seguridad del servicio (checklist previo a abrir el puerto)

- `debug=False` (`dashboard.py:2354`) — el modo debug de Werkzeug permite ejecución de
  código arbitrario para quien lo alcance.
- `app.secret_key` desde `FLASK_SECRET_KEY` con valor aleatorio. Hoy es el literal
  `"solo-local-no-hace-falta-secreto-real"` (`:72`), versionado en git: cualquiera que
  lea el repo puede firmar cookies de sesión válidas mientras el HTML siga vivo.
- Bind en `127.0.0.1:5050`; el puerto **nunca** se publica hacia afuera. Firewall de
  Hetzner además de `ufw`.
- **Clave de service account de Firebase Admin**: permite acuñar tokens de cualquier
  uid, leer y escribir todo Firestore y mandar push a todos los dispositivos. Vive en
  `/etc/iaplusyou/firebase-sa.json`, **fuera del árbol del repo**, `chmod 600`, dueño el
  usuario del servicio, cargada por `GOOGLE_APPLICATION_CREDENTIALS` en el unit de
  systemd. Nunca en `clientes/`.
- Agregar `serviceAccountKey*.json`, `firebase*.json`, `google-services.json` y
  `GoogleService-Info.plist` al `.gitignore` **ANTES** de generar ninguna clave. Hoy el
  `.gitignore` no menciona nada de Firebase, y este proyecto ya tuvo un incidente de
  API key filtrada (la de Gemini en `swaps.json`).
- Protección del HTML (D1) puesta y verificada desde una red ajena antes de abrir el
  puerto.

### 4.5 Despliegue: procedimiento, no solo destino

- **VPS Hetzner**, la instancia más económica que corra Python 3 + Flask + ffmpeg. Fijar
  la línea de Python (hoy se desarrolla en **3.9.6**; un Ubuntu actual trae 3.11/3.12).
- **Submódulos**: el repo tiene dos (`meta_ads` → `CreaTvMetaAds` y
  `clientes/happyflops/marca` → `happyflops-brand-matrix`, ver `.gitmodules`). Hace falta
  `git clone --recurse-submodules` y una deploy key de solo lectura si son privados; sin
  eso el `import meta_ads` queda roto y la guía de marca vacía.
- **Historia de git obligatoria**: `informe.py` corre `subprocess` contra `git log` /
  `git ls-files` / `git rev-list` (`informe.py:31-88`), así que el VPS necesita un
  checkout con historia, no un export.
- **`requirements.txt` fijado.** Hoy no tiene **ni una sola versión** (`requests`,
  `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`,
  `google-auth-oauthlib`, `boto3`, `Flask`, `anthropic`, `jsonschema`, `Pillow`). Se
  congela con `pip freeze` del venv que hoy funciona y se agregan `gunicorn` y
  `firebase-admin`. Probar la instalación en la instancia elegida **antes** de
  comprometerse con su tamaño: `firebase-admin` arrastra gRPC, que es lo más pesado de
  compilar en una instancia chica (y peor si es ARM).
- **Nginx**: `client_max_body_size 200m` (el default es **1 MB**, así que una foto de
  iPhone devuelve 413 antes de llegar a Flask), `proxy_read_timeout` y
  `proxy_send_timeout` acordes al polling y a las rutas lentas. **Certbot** con
  renovación automática.
- **systemd**: `Restart=always`, `RestartSec` generoso, `TimeoutStopSec` largo,
  `EnvironmentFile`, `TZ` explícito (D7), `GOOGLE_APPLICATION_CREDENTIALS`, y
  `ExecStartPre` de reconciliación. Reemplaza al `use_reloader=False` manual de hoy, que
  **sigue aplicando**: nunca activar el reloader de Flask, mataría jobs en curso.
- **`desplegar.sh`** (diez líneas): verifica que no haya jobs en curso →
  `git pull && git submodule update --init --recursive && pip install -r requirements.txt
  && systemctl restart iaplusyou`. **Advertencia escrita: cada despliegue mata los jobs
  en vuelo** — antes reiniciar era un acto manual y consciente; ahora será rutina.
- **Rollback**: `git checkout <tag del último despliegue conocido-bueno>` + restart.

### 4.6 Corte a producción y convivencia laptop/VPS

El documento anterior describía el destino y nunca la transición: su única frase sobre
el tema era "el resto del entorno se copia al VPS exactamente como está".

1. **Inventario de lo que se mueve** (todo fuera de git): los siete JSON por cliente,
   `proyecto.json`, `.env` raíz y por cliente, `token_youtube.json`, `token_tiktok.json`,
   `registro_generaciones.csv`, `clientes/*/personajes|escenas|productos|productos_referencia|marca`,
   y `salidas/<cliente>/swaps_subidas/` (porque `imagen_swap_original`, `:1519`, sirve
   `foto_original_local` desde ahí — ver D11).
2. **Verificación por conteos**: 45 swaps, 2 videos, 3 creative_flow, 4 productos.
3. **La laptop queda congelada como servidor.** Después del corte solo abre el dashboard
   del VPS por el navegador; para desarrollo se usa una copia local y ngrok, nunca el
   estado vivo. Es una regla humana que ningún código va a hacer cumplir, así que se
   escribe también en `CLAUDE.md` y `SETUP.md`.
4. **Criterio de rollback**: si la plataforma se muestra inestable durante la semana de
   F3, se restaura el respaldo en la laptop y se la descongela. A partir de F4 el
   rollback deja de ser gratis, porque hay estado nuevo que la laptop no tiene — por eso
   F3 dura una semana entera antes de escribir un solo endpoint.

### 4.7 Observabilidad

Mientras el dashboard corre en la laptop, si algo muere el usuario lo ve al instante. En
un VPS remoto, un proceso en bucle de reinicio, un disco lleno, un certificado sin
renovar o un token de Meta expirado son invisibles hasta que alguien abre la app y
falla. Tres piezas casi gratis:

1. `GET /api/v1/estado` como health check, vigilado por un monitor externo gratuito que
   mande correo si deja de responder 5 minutos.
2. Logs a journald con `SystemMaxUse=500M`; `journalctl -u iaplusyou` documentado en
   `SETUP.md` como el sitio donde mirar (hoy todo va a stdout con `print`).
3. **Reutilizar el canal de push** para avisar al admin cuando un job termina en error y
   cuando la reconciliación de arranque marca algo — la plomería ya existe, es mandar el
   push también en la rama de excepción de `trabajos._run` (`trabajos.py:153`).

Más: watchdog por exceso de duración (§3.5), alerta de disco al 80%, y aviso de
vencimiento de tokens de publicación **antes** de que falle una publicación (§4.9).

### 4.8 Ambiente de pruebas sin gastar créditos

Probar la app contra el único backend que existe dispara acciones caras e irreversibles:
aprobar un prompt gasta ~1.5 créditos, aprobar una imagen ~8, probar Publicidad crea una
Campaign real en Meta, y probar la publicación orgánica sube contenido de prueba a las
cuentas reales del cliente. Sin montar un segundo servidor:

- **`clientes/demo/`** con su `.env` **sin** credenciales de Meta Ads ni tokens de
  publicación. Doble beneficio: `capacidades` lo reporta como no configurado, que es
  exactamente el camino de UI en gris que hay que probar.
- **`IAPLUSYOU_SIMULACRO=true`** en ese proyecto: las llamadas a proveedores devuelven
  una URL fija en vez de generar, para recorrer el circuito completo sin gastar un
  crédito.
- **`POST /api/v1/dev/job_prueba`** (un job de 20 s que no llama a ningún proveedor) y
  **`POST /api/v1/dev/push_prueba`**: depurar APNs/FCM y el cableado de `trabajos.py`
  cuesta cero en vez de ~8 créditos y 6 minutos por intento. Es lo que hace ejecutable
  el Hito 0.
- Durante el desarrollo la app apunta a la laptop vía **ngrok**; el VPS se reserva para
  producción. Un segundo VPS de staging queda para cuando haya más de una persona.

### 4.9 Límites conocidos

**1. Los wizards de OAuth necesitan una computadora — y es un paso RECURRENTE, no
único.** `auth/auth_meta.py`, `auth/auth_youtube.py`, `auth/auth_tiktok.py` y
`auth/auth_meta_ads.py` abren un navegador local con callback en `localhost`: no se
pueden correr desde el celular ni desde el servidor. El documento anterior lo presentaba
como un paso de alta que se hace una vez; en la práctica:

- `uploaders/youtube_uploader.py:_get_credentials` **refresca y reescribe**
  `token_youtube.json` en el VPS (`with open(token_path, "w")`, línea 26), así que la
  copia del VPS diverge de la de la laptop y volver a copiar la vieja rompe la
  publicación. Además ese `open("w")` no es atómico.
- Si la pantalla de consentimiento de Google está en estado *Testing*, el refresh token
  muere a los 7 días y hay que volver a correr el wizard.
- El access token de TikTok dura 24 h; los tokens de página de Meta también caducan.

Consecuencia: mantener un cliente vivo exige volver a una computadora cada tanto — justo
lo que la migración quería eliminar. Mitigaciones: publicar la app de Google a producción
para que el refresh token deje de caducar a los 7 días; el aviso de vencimiento en
`capacidades`; y un runbook de renovación en modo dos máquinas en `SETUP.md`.

**2. El contenido en R2 es público y con URLs predecibles.** `storage/r2_uploader.py`
construye URLs contra `R2_PUBLIC_BASE_URL` (bucket con acceso público **a propósito**,
porque Instagram exige URLs públicas para publicar) y las claves son deterministas por
construcción: `clientes/<cliente>/videos/<prompt_id>.mp4`,
`clientes/<cliente>/imagenes/<nombre>.png`, y `prompt_id` es
`idea_YYYYMMDD_HHMMSS_<slug>_pN`. **Se acepta explícitamente como limitación conocida:
el control de acceso por proyecto aplica al estado y a las acciones, NO a los binarios.**
Mitigación barata: componente aleatorio en la clave de R2 al subir, para que dejen de ser
adivinables. Si algún día entra un cliente para el que no sea aceptable, la alternativa
es un endpoint proxy autenticado en `/api/v1` para lo que ve la app, dejando públicas
solo las URLs que Meta necesita.

**3. Desplegar mata los jobs en curso** (§4.5).

### 4.10 Distribución de la app y costos

**Canal** (D6): TestFlight con testers internos + canal de pruebas internas de Google
Play, sin tiendas públicas. Elimina el choque entre la revisión de Apple y el modelo
fail-closed, y baja el ciclo de actualización a minutos. Recordatorio: las builds de
TestFlight expiran a los 90 días.

**Dependencias externas con plazo**: inscripción al Apple Developer Program (99 USD/año,
puede tardar días — **es el ítem de mayor plazo de todo el proyecto**), Google Play
Console (25 USD pago único), llave APNs `.p8`, `applicationId`/bundle id (D4), llave de
firma de Android (si se pierde, no se puede volver a publicar esa app).

**Costos.** Hoy el proyecto no tiene ningún costo fijo de infraestructura: el servidor es
la laptop. Después del cambio:

| Concepto | Orden de magnitud |
|---|---|
| VPS Hetzner de entrada | ~4-6 EUR/mes |
| Dominio | ~12 USD/año |
| Let's Encrypt | 0 |
| Firebase plan Spark (Auth + Firestore + FCM) | 0 para un admin y pocos proyectos — salir del gratuito exige activar Blaze |
| Apple Developer Program | 99 USD/año, recurrente y **bloqueante si caduca** |
| Google Play Console | 25 USD, pago único |

Total aproximado: **~6-8 USD/mes + 99 USD/año**. Los costos variables de siempre
(Higgsfield, fal, WaveSpeed, Anthropic, Gemini, R2, presupuesto de Meta Ads) no cambian
con este diseño. Estos fijos deberían poder entrar en `informe.py`.

### 4.11 Registro de deuda técnica aceptada

Lo que este plan difiere **a propósito**, con fecha de pago. Regla de corte: se acepta
deuda salvo cuando puede **perder datos** o **gastar dinero/créditos dos veces** — esas
dos categorías se pagan antes de la fase que las dispara.

| Deuda | Qué duele | Por qué se acepta ahora | Se paga en |
|---|---|---|---|
| `_cargar_entorno_cliente` sigue mutando `os.environ` para los jobs de publicación | El aislamiento de credenciales entre proyectos no está garantizado | Solo hay un proyecto real; `capacidades` ya lo evita | Cuando entre el segundo proyecto con `.env` propio |
| Paginación implementada pero listas devueltas enteras | Un pull-to-refresh trae 45 swaps | Los endpoints ya aceptan `limite`/`desde`; migrar es cambiar el cliente | Cuando una lista pase de ~200 |
| `salidas/` sin poda (282 MB hoy, 93 archivos, todo duplicado en R2) | Llena el disco del VPS, y disco lleno + escritura no atómica = pérdida | La escritura atómica de F1 convierte "disco lleno" en "la operación falla" | F7 (cron de limpieza) |
| Sin ambiente de staging separado | Probar contra producción | `clientes/demo/` + `IAPLUSYOU_SIMULACRO` cubren el caso | Cuando haya más de una persona |
| Timestamps sin zona horaria | Ambigüedad si algún día cambia el huso | Migrar a UTC tocaría todos los módulos; `TZ` fijo mantiene continuidad | Sin agendar |
| Subida de archivos síncrona (`_subir_asset`, `:188`, encadena disco + R2 + `ffmpeg`) | Un video de celular abre el request varios minutos | Solo aplica a v1.1 | F7 |
| Bucket R2 público (§4.9 #2) | El control por proyecto no cubre binarios | Quitarlo rompe la publicación en Instagram | Solo si entra un cliente que lo exija |

---

## 5. Plan de trabajo

Reglas de trabajo que valen para todas las fases:

- **Extracción justo a tiempo**, con la regla del commit único (§4.1). Nunca un
  big-bang de las 49 rutas.
- Ninguna tarea que cruce un **punto de no retorno** (§5.4) se ejecuta el mismo día en
  que se decide.
- Los guiones paso a paso de cada fase se crean en `docs/superpowers/plans/` **cuando
  esa fase arranca**, con el formato de `2026-09-05-meta-ads-fase1.md` (`### Task N`,
  checkboxes, verificación por tarea), y se enlazan desde aquí. Así este maestro sigue
  siendo legible y no se ensucia al tachar tareas.
- Para los pasos manuales que solo puede hacer el humano (consola de Firebase,
  aprovisionar Hetzner, certbot, llave APNs, alta del primer usuario), conviene generar
  un guion interactivo con la skill `wizard` en vez de una lista en prosa: son
  exactamente los pasos donde un experto en Flutter pierde horas.
- Los **rangos de esfuerzo** son estimaciones gruesas en días de trabajo enfocado, no
  compromisos. Se anotan para poder detectar que algo se desbordó, no para planificar
  una fecha. El rango de F4 es el menos confiable de todos.

### 5.1 Verificación sin suite de tests

No hay suite de tests en el proyecto (confirmado en `CLAUDE.md`), y "prueba manual" sin
guion no es un criterio de listo. Cuatro artefactos **versionados en el repo**, que son
parte del criterio de cierre de cada fase:

1. **`scripts/humo_api.sh`** — cadena de `curl` con un token real de Firebase que
   recorre salud → proyectos → capacidades → listas → una escritura barata → estado de
   job, imprimiendo OK/FALLO por paso. Crece con cada endpoint nuevo y se corre completo
   antes de cada commit de API.
2. **`docs/humo-html.md`** — checklist manual numerada de ~12 clics que recorre las 5
   pestañas del dashboard HTML. Se corre después de **cada** extracción de ruta: es lo
   único que protege la vía web.
3. **Prueba de resiliencia** — `systemctl restart` a mitad de un job; la tarjeta debe
   quedar en "error" visible, no colgada. Y `kill -9` durante una escritura: el JSON
   debe seguir siendo válido.
4. **`python3 -m py_compile`** antes de cada commit, como ya manda `CLAUDE.md`; y
   `dry_run=True` para todo lo que gaste dinero en Meta, siguiendo el precedente de
   `docs/superpowers/plans/2026-09-05-meta-ads-fase1.md`.

### 5.2 Fases

---

#### F0 — Trámites externos, decisiones bloqueantes y contrato congelado
*Qué gana el usuario: nada visible todavía — pero deja de perder semanas después.*
**Esfuerzo: ~2-3 días** (más la espera externa de Apple, que corre en paralelo).
**Depende de:** nada. Todo lo demás depende de esto.

Tareas:

1. Cerrar **D1** (protección del HTML), **D2** (composición de la Bandeja), **D3**
   (idea visual), **D4** (bundle id), **D5** (dominio), **D6** (canal de distribución) y
   escribir cada una en §2.9 con la opción elegida y su razón.
2. Arrancar los trámites externos **el día uno, en paralelo**: Apple Developer Program,
   Google Play Console, compra del dominio y DNS. Marcarlos como "externos: pueden tardar
   días; no bloquean el trabajo local pero sí el Hito 0 en iOS".
3. **Inventario de rutas** en `docs/api/inventario-rutas.md`: las 49 rutas de
   `dashboard.py` con cuatro columnas — ruta | pestaña que la usa hoy | destino (v1 /
   v1.1 / v2 / jubilar) | endpoint `/api/v1` equivalente. Media hora de trabajo que
   revela los huecos y da el insumo de estimación de F4.
4. **Congelar el contrato**: `docs/api/v1.md` con método, ruta, cuerpo, forma exacta de
   respuesta y códigos por endpoint, más `docs/api/ejemplos/*.json` con una respuesta
   **real** de cada uno, copiada del estado actual de happyflops con credenciales
   quitadas. Esto es la costura que desbloquea el carril Flutter (§5.3).

**Listo cuando:** las dos cuentas de desarrollador están pagadas y en trámite (no hace
falta que estén aprobadas); el dominio es del usuario; `inventario-rutas.md` cubre las 49
rutas sin ninguna celda vacía en "destino"; `docs/api/v1.md` y los ejemplos están
commiteados y el desarrollo de Flutter puede arrancar contra ellos sin backend; las seis
decisiones están escritas.

---

#### F1 — Endurecer el backend, todavía en la laptop
*Qué gana el usuario: que nada de lo que ya tiene se pierda cuando salga de su laptop.*
**Esfuerzo: ~4-6 días.**
**Depende de:** nada técnico — puede correr en paralelo con F0. Es la fase que se puede
empezar hoy mismo, sin VPS, sin Firebase y sin cuentas.

Tareas:

1. Escritura atómica en `_json_store.guardar` y `ads._guardar` (tmp + `os.replace`).
2. `con_bloqueo(path)` en `_json_store` (un `threading.Lock` por ruta) envolviendo cada
   ciclo cargar-mutar-guardar en `prompts.py`, `ads.py`, `estado.py`, `swaps.py`,
   `creative_flow.py`, `conceptos_imagen.py`.
3. Corregir los jobs largos para que relean y muten solo su entrada justo antes de
   guardar: `dashboard.py:1850→1904` (video), `:1780-1788` (imagen), `ads.actualizar`.
4. Ampliar `_reconciliar_huerfanos` (`:2244`) a `prompts_pendientes.json`,
   `estado_videos.json` y `ads.json` (`publicando` → `error` con mensaje y camino de
   reintento visible), y sacarla de `if __name__ == "__main__"`.
5. Agregar `notificar=None` a `trabajos.iniciar` y el hook en `_run()` en ambas ramas,
   **fuera del `with _LOCK`**, en un hilo aparte, con `try/except` propio. Por ahora el
   hook solo imprime; `push.py` llega en F2. Pasarlo en los puntos de llamada de
   `dashboard.py`.
6. `app.secret_key`, `HOST` y `PUERTO` desde entorno; `debug` configurable.
7. Idempotencia por transición de estado en las acciones que gastan (`publicar_ad`,
   `aprobar_prompt`, `aprobar_imagen`), devolviendo el estado actual cuando no coincide.
8. `MAX_CONTENT_LENGTH` en Flask con un manejador de 413 que devuelva JSON legible.
9. Envolver `POST /ideas` en `trabajos.iniciar` (D9), si se autorizó.
10. Congelar `requirements.txt` con `pip freeze`, agregar `gunicorn` y `firebase-admin`,
    anotar la versión de Python objetivo.
11. Escribir `docs/humo-html.md`.
12. Agregar `serviceAccountKey*.json`, `firebase*.json`, `google-services.json` y
    `GoogleService-Info.plist` al `.gitignore`, **antes** de que exista ninguna clave.

**Listo cuando:** `python3 -m py_compile` limpio en todo lo tocado; `docs/humo-html.md`
pasa completa contra el dashboard corriendo bajo gunicorn en local; se lanzó una
generación, se mató el proceso a mitad, se reinició, y la tarjeta quedó en "error"
visible — repetido una vez por cada una de las tres familias nuevas (prompts, videos,
ads); `kill -9` durante una escritura y el JSON sigue siendo válido;
`git grep 'solo-local-no-hace-falta'` no devuelve nada; un segundo POST de publicar sobre
un ad ya publicado es rechazado con su estado actual, sin crear una segunda campaña.

---

#### F2 — Esqueleto caminante contra el VPS real (Hito 0)
*Qué gana el usuario: la certeza de que la arquitectura entera funciona, comprada con
tres pantallas feas en vez de con cinco pantallas de producto.*
**Esfuerzo: ~5-8 días.**
**Depende de:** F0 (dominio, D1, contrato) y F1 completa — no se levanta el VPS antes de
tener escritura atómica y reconciliación ampliada.

Tareas:

1. Aprovisionar el VPS. Fijar `TZ` (D7) **antes de que se escriba un solo dato**.
2. `git clone --recurse-submodules` con deploy keys; verificar que `import meta_ads`
   funciona y que `informe.py` encuentra historia de git.
3. Instalar desde el `requirements.txt` congelado y **verificar que `firebase-admin`
   instala en la instancia elegida**. Si no, cambiar de instancia ahora, no después.
4. gunicorn `-w 1 -k gthread --threads 8 --timeout 120`, sin `--preload`; `debug=False`;
   bind en 127.0.0.1; unit de systemd con todo lo de §4.5 y §4.4.
5. Nginx (`client_max_body_size 200m`, timeouts), la protección de D1 por `location`
   dejando fuera `/api/v1/`, `/.well-known/` y `/api/v1/estado`, y certbot.
6. Proyecto Firebase: Auth email/contraseña con auto-registro **desactivado**, **dos**
   usuarios creados a mano (uno con accesos y **uno sin**, que existe solo para demostrar
   el fail-closed); Firestore con `allow read, write: if false`; llave APNs subida;
   `google-services.json` / `GoogleService-Info.plist`.
7. Blueprint `/api/v1` con lo mínimo: `GET /estado` (público, con `version_api` y
   `version_minima_app`), el decorador `@requiere_acceso` con la validación en tres pasos
   de §2.6, `GET /proyectos` devolviendo `{id, nombre}`,
   `GET /proyectos/<c>/videos` (las 2 entradas reales de `estado_videos.json`),
   `POST /proyectos/<c>/videos/<brief_id>/rechazar` (síncrona, coste cero — la escritura
   más barata que existe), `POST /dispositivos`,
   `GET /proyectos/<c>/trabajos/<job_id>`, y `POST /dev/job_prueba` + `POST /dev/push_prueba`.
8. `push.py`: envío vía `firebase_admin.messaging` a los tokens de `dispositivos` de los
   uid con ese cliente en `accesos`, enganchado al `notificar` que dejó F1.
9. App Flutter de tres pantallas feas: login, lista de proyectos, y una pantalla de
   videos con un botón "Probar push". **Ni un widget más.**
10. `scripts/humo_api.sh` con la cadena de curl de todo lo anterior.

**Listo cuando pasan los siete puntos del Hito 0**, todos contra el VPS **real de
producción** y desde un celular físico:

1. Login con Firebase Auth.
2. `GET /api/v1/proyectos` con Bearer devuelve `[{"id":"happyflops","nombre":"Happy Flow"}]`.
3. El usuario **sin** documento en `accesos` recibe lista vacía y 403 al pedir el
   proyecto — **fail-closed demostrado, no asumido**.
4. Un token vencido o basura devuelve 401, y la app lo traduce a "vuelve a iniciar
   sesión" **solo después** de un reintento con `getIdToken(true)`.
5. La app muestra las 2 entradas reales de `estado_videos.json`, y rechazar un video
   desde el celular cambia el JSON en el VPS.
6. "Probar push" dispara un job de 20 s que al terminar manda una notificación que llega
   **con la app cerrada**, con payload `{cliente, tipo, id}`, y al tocarla abre una
   pantalla que lo imprime.
7. `systemctl restart` y todo lo anterior sigue funcionando.

Más: `curl https://<dominio>/` desde una red ajena devuelve 401 o no conecta;
`curl https://<dominio>/api/v1/estado` responde 200 sin token; `humo_api.sh` da OK en
todos sus pasos.

*Nota de secuencia:* si la cuenta de Apple todavía no está aprobada, el Hito 0 se
demuestra en Android y el punto 6 se repite en iOS cuando llegue la llave APNs. No
bloquea F3.

---

#### F3 — Corte de datos y una semana operando desde el VPS con el HTML de siempre
*Qué gana el usuario: su servidor deja de ser su laptop.*
**Esfuerzo: ~1 día de trabajo + 7 días de calendario de uso real.**
**Depende de:** F2 (el Hito 0 pasó, así que la arquitectura está validada antes de mover
el estado real). **Punto de no retorno.**

Tareas:

1. Escribir el inventario de §4.6 y montar el respaldo de §4.3 **antes de mover nada**;
   restaurarlo una vez en limpio en un directorio vacío y comparar conteos.
2. Correr los cuatro wizards de OAuth en la laptop y copiar los tokens al VPS por `scp`,
   `chmod 600`. Hacer atómica la reescritura de `token_youtube.json`.
3. Resolver **D11** (los tres `send_file`) y aplicarlo.
4. `rsync` del inventario a la misma ruta relativa; verificar por conteos (45 swaps, 2
   videos, 3 creative_flow, 4 productos).
5. Declarar la laptop congelada como servidor; escribirlo en `CLAUDE.md` y `SETUP.md`.
6. `desplegar.sh` + etiquetado de despliegues conocidos-buenos; correrlo una vez de punta
   a punta, y probar el rollback por tag.
7. Crear `clientes/demo/` con `IAPLUSYOU_SIMULACRO=true` (§4.8).
8. Monitor externo contra `GET /api/v1/estado`; journald con `SystemMaxUse=500M`.

**Listo cuando:** el dashboard HTML servido desde el VPS pasa `docs/humo-html.md`
completa, con los mismos datos y las mismas imágenes que la laptop; el respaldo del día
está en R2 y **ya se restauró una vez en limpio**; `GET /capacidades` de happyflops
devuelve lo esperado (hoy `meta_ads: false`) y el de `demo` todo en `false`; y **siete
días corridos de trabajo real hechos íntegramente contra el VPS**, incluyendo al menos
una generación completa y una publicación, sin abrir el dashboard local ni una vez.

---

#### F4 — Extracción a servicios y endpoints de lectura
*Qué gana el usuario: ve sus colas reales en el celular (solo lectura).*
**Esfuerzo: ~8-15 días.** Es la estimación menos confiable del plan: depende del
inventario de F0 y de cuántas rutas resulten enredadas. Si a mitad de la fase el ritmo
real es menos de ~2 rutas por día, hay que replantear el alcance de v1, no apretar.
**Depende de:** F3. El contrato congelado de F0 permite que el carril Flutter vaya en
paralelo desde antes.

Tareas:

1. Crear `servicios/` y aplicar la regla del commit único (§4.1) ruta por ruta.
2. **Empezar por las lecturas**, que no tienen efectos: `_ideas_pendientes` (con
   `?con_costo=0`), `_videos_para_ui` (extraído de `ver_cliente:517-529`, con
   `plataformas_estado` y el job de publicación), `ads.cargar`, `_personajes`, y las
   familias que D2 haya incluido.
3. `GET /capacidades` con las fuentes corregidas y `dotenv_values` (§3.4).
4. Mover el polling a `/api/v1/proyectos/<c>/trabajos/<job_id>` con validación de prefijo
   y mensaje sanitizado; hacer que el JS del HTML llame a esa misma ruta. La ruta vieja
   `/trabajo/<path:job_id>/estado` queda solo para el HTML, dentro de la protección de D1.
5. Paginación (`?limite=&desde=`) en todas las listas desde el primer día.
6. En paralelo, carril Flutter: capa de red con el interceptor de 401, modelos, y las
   pantallas de lectura.

**Listo cuando:** `humo_api.sh` da OK en todos los endpoints de lectura contra el VPS;
`docs/humo-html.md` pasa completa **después de cada extracción**; `py_compile` limpio;
la app muestra la Bandeja y Publicidad con datos reales en modo solo lectura; y
`git log` muestra un commit por ruta con las tres piezas juntas.

---

#### F5 — Acciones: las escrituras que gastan créditos y publican
*Qué gana el usuario: aprueba y publica desde el celular, con la laptop apagada.*
**Esfuerzo: ~6-10 días.**
**Depende de:** F4, y de tener cerradas **D8** (rechazar imagen), **D9** (`POST /ideas`),
**D10** (ads síncronos) y **D12** (`.env` de happyflops) **antes** de tocar el primer
endpoint que gasta.

Tareas, en orden de riesgo creciente:

1. `guardar_prompt` y `rechazar_prompt` (coste cero).
2. `aprobar_prompt` (~1.5cr) — **debe aceptar el cuerpo de `_aplicar_edicion`**, o el
   usuario paga por el texto viejo.
3. `regenerar_imagen`, y el "rechazar imagen" que resuelva D8.
4. `aprobar_imagen` (~8cr).
5. `enviar_swap_a_publicidad` y `enviar_video_a_publicidad` — síncronas y triviales,
   pero son lo **único** que alimenta la cola de Publicidad.
6. `aprobar` video (publica en redes) y `rechazar`.
7. Las cuatro de ads, con la validación de transición de §3.1.
8. Todo endpoint que lanza un job devuelve el `job_id` calculado más `ya_en_curso`; todo
   endpoint que gasta expone el costo estimado en el GET previo.
9. Probar **cada** acción primero contra `clientes/demo` con `IAPLUSYOU_SIMULACRO=true`,
   y solo después una vez contra happyflops.
10. Pantallas Flutter: detalle con Aprobar/Rechazar/Editar, Nueva idea (formulario con
    selector de personaje y checkboxes de plataforma), Publicidad completa.

**Listo cuando:** un contenido recorre el pipeline completo desde el celular con la
laptop apagada, con barra de progreso y push de fin; un segundo POST de cada acción
devuelve 409 y la app lo traduce a "esto ya se hizo" (probado a mano para publicar,
aprobar prompt y aprobar imagen); un anuncio publicado desde el celular aparece en Meta
Ads Manager en **PAUSED** y la app lo muestra como `pausado`; `docs/humo-html.md` sigue
pasando; `humo_api.sh` cubre también las escrituras usando `demo`.

---

#### F6 — v1 en operación real
*Qué gana el usuario: descubre qué le falta de verdad, antes de construir más.*
**Esfuerzo: ~7 días de calendario + ~2-3 días de correcciones.**
**Depende de:** F5.

Tareas: distribuir la build por el canal de D6; usar la app como herramienta principal
una semana; **anotar cada vez que hubo que abrir el dashboard HTML y por qué** (esa lista
es el backlog real de v1.1); cerrar los huecos que aparezcan (manejo de `desconocido`,
formato de fechas, tamaños de imagen, textos); restaurar el respaldo del día en limpio y
comparar.

**Listo cuando:** una semana de operación real sin abrir el HTML para nada de lo que v1
cubre, con al menos un contenido aprobado de punta a punta y un anuncio publicado desde el
celular; la lista de "tuve que abrir el HTML por X" está escrita y priorizada; ningún job
quedó zombi en la semana (verificado mirando los siete JSON).

---

#### F7 — v1.1: FlowCatálogo, FlowSettings y subida desde el celular
*Qué gana el usuario: el HTML deja de hacerle falta.*
**Esfuerzo: ~10-15 días.**
**Depende de:** F6.

Tareas:

1. FlowCatálogo (crear/actualizar/eliminar productos, subir y eliminar imágenes) y
   FlowSettings, con la misma regla de un commit por ruta.
2. Subida desde cámara/galería: la app comprime antes de subir (fotos a lado mayor 2048
   px); el servidor **renombra siempre** a `<timestamp>_<slug>.<ext>` y nunca confía en
   el nombre del cliente (el selector de Flutter manda `image_picker.jpg`, y
   `secure_filename` sobre ese nombre sobrescribiría el archivo anterior del mismo
   proyecto); todo lo lento (R2 + `ffmpeg`) corre en `trabajos.iniciar` y devuelve
   `job_id`, no dentro del request.
3. Marca: son **dos** endpoints, no uno. `subir_marca` (`:288`) recibe el archivo;
   `analizar_marca` (`:299`) **no recibe archivos** — lee las URLs ya subidas vía
   `_marca_referencias` y lanza `trabajos.iniciar` con `job_id = f"{cliente}__marca__analizar"`.
   Y `guardar_marca` (`:324`) acepta **tres** campos: `guia_estilo`, `style_id` y
   `style_strength` (los dos últimos alimentan `_extra_params_image`, `:485`, en cada
   generación).
4. FlowPlus (`cf_generar_prompt` `:1983`, `cf_regenerar_prompt` `:2090`,
   `cf_guardar_prompt` `:2120`, `cf_descartar` `:2131`, `cf_generar_video` `:2138`).
   *Verificar antes cuál plantilla está viva:* `cliente.html:23` incluye
   `_tab_flowplus.html`; existe además un `_tab_creativeflowplus.html` que parece muerto.
5. Ideas visuales, si D3 las incluyó, con la advertencia de costo de `nueva_idea_visual`.
6. Marca visual por proyecto: `color_acento` y `logo_url` en `proyecto.json`, devueltos
   por `GET /proyectos`.
7. Alta de cliente nuevo desde la app, terminando con el recordatorio explícito del paso
   OAuth desde una computadora (§4.9).
8. Cron de limpieza de `salidas/` y alerta de disco al 80%.

**Listo cuando:** siete días corridos sin abrir el dashboard HTML para **nada** del
trabajo diario. Si hubo que abrirlo, lo que faltó es trabajo de F7, no de F8, y ese es
exactamente el momento de descubrirlo — antes de invertir en la build web. Además: una
foto de 8 MB sube desde el celular sin 413; un producto creado desde el celular aparece
en la lista de FlowClone y se puede usar en un swap.

---

#### F8 — v2: Flutter Web y jubilación del HTML
*Qué gana el usuario: una sola interfaz, y una superficie de ataque menos.*
**Esfuerzo: ~5-8 días.**
**Depende de:** el criterio de salida de F7 **cumplido de verdad** (los siete días), no
la impresión de que ya no se usa.

Tareas: build web del mismo código con ajustes de layout; probarla como reemplazo real
unos días; `git tag html-final`; borrar rutas HTML y plantillas Jinja en un commit propio
(D13); retirar la protección temporal de Nginx; actualizar `CLAUDE.md` y `SETUP.md` al
mundo sin Jinja.

**Listo cuando:** el usuario opera una semana desde Flutter Web;
`grep -c "render_template" dashboard.py` devuelve 0; `templates/` ya no existe;
`curl https://<dominio>/cliente/happyflops` devuelve 404; el tag `html-final` está en el
repo; `humo_api.sh` pasa completo.

---

### 5.3 Carriles paralelos y qué bloquea a qué

**La costura es el contrato congelado de F0** (`docs/api/v1.md` +
`docs/api/ejemplos/*.json`). A partir de ahí:

- **Carril A (backend/infra):** F1 → F2 → F3 → extracción y endpoints (F4-F5).
- **Carril B (Flutter):** login con Firebase (solo depende del proyecto Firebase de
  F2.6), capa de red, modelos y pantallas construidas contra los JSON de ejemplo
  servidos localmente.

Serializado de verdad, y hay que decirlo: **el contrato bloquea todo**; **el TLS bloquea
cualquier prueba real de la app** (sin TLS válido iOS bloquea por ATS y Android por
cleartext, así que la app literalmente no puede hablarle al backend); **el Hito 0 bloquea
el inicio de las pantallas de producto**; **la extracción de una ruta bloquea su
endpoint**; los trámites externos bloquean el Hito 0 en iOS pero no el trabajo local.
Todo lo demás se solapa.

### 5.4 Puntos de no retorno

| Punto | Se cierra en | Qué hay que haber decidido antes | Costo de revertir |
|---|---|---|---|
| Forma del documento `accesos` y modelo de identidad | F2 (decorador) | §2.6, §2.8 | Re-login de todos + reescribir reglas |
| `applicationId` / bundle id | F2 (crear la app en Firebase) | D4 | App nueva desde cero |
| Dominio y DNS | F2 (certbot) | D5 | Redistribuir la app |
| Un solo worker | F2 (unit de systemd) | §2.3 | Bugs silenciosos, no un error |
| Corte de datos al VPS | F3 | §4.3 y §4.6, con el respaldo **restaurado** | Migración inversa |
| Contrato `/api/v1` | Antes de la primera build en un celular ajeno | §3.1, D14 | El backend debe seguir sirviendo el contrato viejo |

**Regla que sobrevive a la implementación:** ninguna tarea que cruce un punto de no
retorno se ejecuta el mismo día en que se decide.

### 5.5 Criterios de salida por versión

- **v1 terminado** = una semana de operación real sin abrir el dashboard HTML para lo
  que v1 cubre, con al menos un contenido aprobado de punta a punta y un anuncio
  publicado desde el celular (F6).
- **v1.1 terminado** = siete días corridos sin abrir el dashboard HTML para **nada** del
  trabajo diario (F7). Si hubo que abrirlo, lo que faltó es trabajo de v1.1.
- **v2 arranca** solo después de eso (F8).

---

## Sin agendar / a evaluar más adelante

Explícitamente **sin números de versión** — ninguna sección fuera de §1.5 asigna
versiones.

- **Modo offline básico**: cachear la última Bandeja para verla sin conexión, aunque no
  se pueda actuar sobre ella.
- **Ambiente de staging separado** en Hetzner, cuando efectivamente haya más de un
  desarrollador tocando el backend.
- **Pantalla de administración de usuarios y accesos** dentro de la app, cuando haya más
  de un puñado de personas.
- **Migración de todas las marcas de tiempo a `datetime.now(timezone.utc)`** con
  conversión en la capa de presentación: más correcto, pero tocaría todos los módulos y
  dejaría ambiguos los registros anteriores al corte.
- **Endpoint proxy autenticado para binarios**, si algún día entra un cliente para el que
  el bucket público de R2 no sea aceptable (§4.9 #2).
- **Resucitar o eliminar los `ENABLE_*`** de `.env.example` (D12).
