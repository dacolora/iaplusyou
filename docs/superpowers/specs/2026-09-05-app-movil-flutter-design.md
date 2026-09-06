# Diseño: app móvil Flutter + API para iaplusyou

## Contexto y motivo

Hoy `dashboard.py` solo es alcanzable desde `localhost` en la laptop del
usuario — el diseño explícito del proyecto (ver `CLAUDE.md`) es que corre en
red local, sin autenticación, confiando en que solo el admin lo abre. El
usuario quiere poder aprobar contenido, disparar ideas nuevas y manejar la
pestaña Publicidad (Meta Ads) desde el celular, en cualquier lugar — no solo
sentado frente a la laptop que corre el servidor.

El usuario es desarrollador Flutter experto, así que el cliente móvil es
Flutter nativo (no una PWA ni un WebView del dashboard existente). La lógica
de negocio (generación de prompts/imágenes/videos, publicación en Meta Ads,
estado por cliente) ya vive completamente desacoplada del HTML en módulos
Python puros (`estado.py`, `prompts.py`, `ads.py`, `meta_ads/`,
`generador_prompts.py`, `trabajos.py`, etc.) — este diseño no toca esa
lógica, solo le agrega una segunda forma de invocarla.

## Metas

- Una app Flutter (iOS/Android) que permite: iniciar sesión, ver los
  proyectos a los que el usuario tiene acceso, escribir ideas nuevas y
  disparar su generación, revisar/aprobar/rechazar prompts, imágenes
  candidatas y videos, y manejar la pestaña Publicidad completa (enviar a
  publicidad, ver métricas, pausar/activar).
- Que funcione sin depender de que la laptop del usuario esté prendida —
  el backend corre en un servidor propio, siempre encendido.
- Notificaciones push cuando un job de fondo termina (video listo para
  aprobar, anuncio publicado) o cuando algo falla.
- Reutilizar el 100% de la lógica Python existente — cero reescritura del
  pipeline, solo una capa de traducción a JSON encima de las mismas
  funciones que ya usan las rutas HTML.

## No-metas (explícitamente fuera de alcance de v1)

- Modo offline / sincronización diferida. Sin conexión, la app muestra un
  error y un botón de reintentar — no hay cola local de cambios pendientes
  ni caché de escritura.
- FlowCatálogo (gestión de catálogo de productos) y FlowSettings (guía de
  marca, bitácora, informe de operación) — siguen siendo solo-navegador.
  Candidatos naturales para una v2, no antes.
- Subir fotos/videos de referencia nuevos de personaje o producto desde el
  celular — sigue siendo tarea de escritorio (requiere el flujo de alta que
  hoy vive en FlowCatálogo/marca).
- Multi-idioma — la app queda en español, igual que el dashboard hoy.
- Cualquier cambio a la lógica de negoción existente (generación, Meta Ads,
  publicación orgánica). Este spec es una capa de acceso nueva, no una
  reescritura.

## Arquitectura general

```
Flutter (iOS/Android)
        │  HTTPS + Firebase ID Token (header Authorization: Bearer <token>)
        ▼
Nginx (TLS, Let's Encrypt) ──▶ Flask (dashboard.py) en un VPS Hetzner
                                  ├── rutas HTML existentes — sin tocar
                                  ├── /api/v1/*  (blueprint nuevo)
                                  │     verifica el ID token con el
                                  │     Firebase Admin SDK (Python) y
                                  │     reutiliza las mismas funciones que
                                  │     ya usan las rutas HTML
                                  └── clientes/<cliente>/*.json
                                        (exactamente igual que hoy — sin
                                        base de datos nueva en el VPS)

Firebase (un solo proyecto)
  ├── Authentication  → login/contraseña por persona
  ├── Firestore       → accesos (usuario↔proyecto), tokens de dispositivo
  └── Cloud Messaging (FCM) → push cuando termina un job o falla
```

Un único proceso Python (el mismo `dashboard.py` de siempre) sirve tanto las
rutas HTML del navegador como el blueprint `/api/v1` que consume la app.
Nada de microservicios ni de segundo proceso: la razón de ser de esta
elección es que la lógica actual (`trabajos.py` con hilos de fondo,
`_ENV_LOCK` sincronizando secretos por cliente, llamadas a `ffmpeg` en
disco) es estado de proceso — partirla en piezas separadas complica sin
necesidad real a esta escala (un admin, pocos proyectos).

**Por qué Firebase para auth/accesos/push, en vez de una base de datos
propia:** las notificaciones push (FCM) requieren un proyecto de Firebase
de todas formas — no hay forma de mandar push a iOS/Android sin pasar por
ahí. Dado que el proyecto de Firebase ya es indispensable, usar también
Firebase Auth evita escribir y mantener a mano hashing de contraseñas,
emisión/refresh de tokens y manejo de sesión (superficie de bugs de
seguridad clásica), y `FlutterFire` lo integra casi sin código del lado de
la app. Firestore reemplaza lo que hubiera sido una base SQLite nueva en el
VPS — el servidor queda sin base de datos local, solo los JSON de siempre.

**Por qué un VPS y no ngrok / no serverless:** ngrok sirve para desarrollo
(iterar rápido apuntando la app a la laptop), pero como arquitectura de
producto real depende de que la laptop quede prendida y conectada 24/7 — si
se suspende o se cierra, la app deja de funcionar y cualquier job en curso
muere a la mitad. Un backend serverless/PaaS-con-escalado-a-cero tiene el
mismo problema: los hilos de `trabajos.py` y el estado en memoria no
sobreviven un reinicio del proceso entre requests. Un VPS con Nginx +
systemd corre el mismo proceso 24/7, sin reinventar cómo ya funciona el
código.

## Autenticación y accesos

- **Login**: Firebase Authentication (email/contraseña). La app obtiene un
  ID token de Firebase y lo manda en cada request como
  `Authorization: Bearer <token>`.
- **Verificación en el backend**: cada ruta de `/api/v1` pasa por un
  decorador que verifica el token con el Firebase Admin SDK
  (`firebase_admin.auth.verify_id_token`) y extrae el `uid`.
- **Accesos por proyecto** (Firestore, colección `accesos`): un documento
  por `uid`, con la lista de `clientes` (proyectos) a los que tiene acceso.
  Cada ruta que recibe un `cliente` en la URL valida que el `uid` del token
  tenga ese cliente en su lista antes de tocar cualquier archivo de
  `clientes/<cliente>/`. Sin entrada en `accesos` = sin acceso a ningún
  proyecto (fail-closed).
- **Dispositivos** (Firestore, colección `dispositivos`): un documento por
  token FCM registrado, asociado al `uid` que lo registró. Se escribe vía
  `POST /api/v1/dispositivos` la primera vez que la app arranca sesión en
  un dispositivo nuevo.

## Superficie de la API v1

Todo bajo el prefijo `/api/v1`. Cada endpoint reutiliza exactamente la
función Python que ya usa la ruta HTML equivalente — nunca duplica lógica,
solo cambia `render_template(...)` por `jsonify(...)`.

| Grupo | Endpoint | Reutiliza |
|---|---|---|
| Dispositivos | `POST /dispositivos` | nuevo — registra token FCM en Firestore |
| Proyectos | `GET /proyectos` | `estado.listar_clientes` filtrado por `accesos` de Firestore |
| Ideas | `POST /proyectos/<cliente>/ideas` | `generador_prompts.generar_prompts` |
| Prompts | `GET /proyectos/<cliente>/prompts` | `prompts.cargar` |
| Prompts | `POST /prompts/<prompt_id>/aprobar` \| `/rechazar` \| `/guardar` | rutas ya existentes `aprobar_prompt`/`rechazar_prompt`/`guardar_prompt` |
| Imagen candidata | `POST /prompts/<prompt_id>/generar_imagen` | ruta ya existente de generación de imagen |
| Imagen candidata | `POST /prompts/<prompt_id>/aprobar_imagen` \| `/rechazar_imagen` | rutas ya existentes |
| Videos | `GET /proyectos/<cliente>/videos` | `estado.cargar` |
| Videos | `POST /videos/<brief_id>/aprobar` \| `/rechazar` | rutas `aprobar`/`rechazar` |
| Publicidad | `GET /proyectos/<cliente>/ads` | `ads.cargar` |
| Publicidad | `POST /ads/publicar` | `publicar_ad` (dashboard.py) |
| Publicidad | `POST /ads/<ad_id>/actualizar` | `actualizar_resultados_ad` |
| Publicidad | `POST /ads/<ad_id>/estado` | `cambiar_estado_ad` |
| Publicidad | `POST /ads/<ad_id>/eliminar` | `eliminar_ad` |
| Jobs | `GET /trabajo/<job_id>/estado` | `trabajos.py` — mismo polling que ya usa la web |

Los nombres exactos de función/ruta en la columna "Reutiliza" son la mejor
referencia disponible hoy contra el estado actual de `dashboard.py` — el
plan de implementación debe reverificarlos contra el código real antes de
escribir cada tarea, ya que este archivo ha cambiado de forma bien
documentada durante el desarrollo de otras funciones en este mismo
proyecto (ver `docs/superpowers/plans/2026-09-05-meta-ads-fase1.md` para
un precedente de ese mismo cuidado).

## Flujo de notificaciones push

Cuando una función corrida vía `trabajos.iniciar` termina (éxito o error),
además de guardar el resultado en el JSON del cliente como hoy, dispara un
push vía Firebase Admin SDK (`firebase_admin.messaging`) a todos los
tokens de dispositivo (colección `dispositivos`) de los `uid` que tengan
ese `cliente` en su documento de `accesos`. El payload incluye
`{cliente, tipo, id}` (ej. `{"cliente": "happyflops", "tipo": "video",
"id": "brief_..."}`) para que la app, al abrir la notificación, navegue
directo a esa tarjeta en la Bandeja de aprobación o en Publicidad — nunca a
una pantalla genérica.

## Pantallas de la app (v1)

1. **Login** — email/contraseña vía Firebase Auth.
2. **Lista de proyectos** — los `clientes` en el documento `accesos` del
   usuario (hoy, en la práctica, solo Happyflops).
3. **Bandeja de aprobación** — unifica prompts pendientes, imágenes
   candidatas pendientes y videos pendientes en una sola cola con
   pull-to-refresh; tocar un item abre su detalle con Aprobar/Rechazar.
4. **Nueva idea** — campo de texto libre → dispara `POST /ideas`, luego
   navega a la Bandeja de aprobación a esperar los 5 prompts candidatos.
5. **Publicidad** — espejo 1:1 de la pestaña web: cola "listos para
   publicar" con el formulario de objetivo/presupuesto/país/edad/URL de
   destino, y "publicados" con métricas + Pausar/Activar.

## Despliegue

- **VPS**: Hetzner, la instancia más pequeña que corra Python 3 + Flask +
  ffmpeg cómodamente (sobra con la más económica del catálogo).
- **Nginx** como proxy inverso terminando TLS, con **Certbot** (Let's
  Encrypt) para el certificado, renovado automático.
- **systemd** corriendo `dashboard.py` como servicio — reinicio automático
  si el proceso muere o si el servidor reinicia. Reemplaza al
  `use_reloader=False` manual de hoy (que sigue aplicando: nunca activar el
  reloader de Flask, mataría jobs en curso).
- **Antes de exponer el puerto a internet**: apagar `debug=True` — el modo
  debug de Werkzeug permite ejecución de código arbitrario si alguien
  externo lo alcanza, es aceptable en local pero no en un servidor público.
- El resto del entorno (`.env` raíz y por cliente, R2, Higgsfield,
  Anthropic, Meta) se copia al VPS exactamente como está — nada de esto
  cambia. Los wizards de OAuth (`auth_meta.py`, `auth_youtube.py`,
  `auth_meta_ads.py`) se siguen corriendo una vez desde una laptop (abren
  un callback en `localhost`) y sus tokens resultantes se copian al VPS,
  igual que ya documenta `CLAUDE.md`/`SETUP.md` para el flujo actual.

## Manejo de errores

Mismo patrón que el resto del proyecto: cada llamada fallida devuelve un
JSON `{"error": "<mensaje real>"}` con el código HTTP apropiado — nunca un
mensaje genérico, y nunca con un `access_token` u otra credencial
interpolada en el texto (mismo incidente de la key de Gemini filtrada en
`swaps.json`, misma regla que ya rige `meta_ads/auth.py`). Un token de
Firebase inválido o expirado devuelve `401` con un mensaje que la app
traduce a "vuelve a iniciar sesión", nunca un stack trace.

## Testing

No hay suite de tests en el proyecto (confirmado en `CLAUDE.md`).
Verificación manual: `python3 -m py_compile` para el backend antes de cada
commit, y pruebas manuales de cada endpoint nuevo con `curl` (token de
prueba de Firebase) antes de conectar la app real. Del lado de Flutter,
pruebas manuales contra el VPS de desarrollo (o Hetzner de staging si hace
falta) — este proyecto no usa TDD/pytest, y este spec no introduce esa
práctica de la nada.

## Próximos pasos (fuera de este spec, fases futuras)

1. v2: llevar FlowCatálogo y FlowSettings a la app.
2. v2: modo offline básico (cachear la última Bandeja de aprobación
   cargada para verla sin conexión, aunque no se pueda actuar sobre ella).
3. Evaluar más adelante si conviene un ambiente de staging separado en
   Hetzner antes de cada release de la app, una vez haya más de un
   desarrollador tocando el backend.
