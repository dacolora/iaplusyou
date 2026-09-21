# Guía de configuración — desde cero

**La forma normal de usar esto es el dashboard web** (`python dashboard.py`, abre
`http://127.0.0.1:5050`) — ahí se hace todo: escribir ideas, revisar/editar prompts,
aprobar imágenes candidatas, aprobar videos, publicar, subir personajes (imagen o video).
`run_batch.py` / `revisar.py` siguen existiendo como alternativa por terminal para lotes
grandes de briefs ya armados, pero no hace falta usarlos.

Pipeline en 4 pasos, cada uno con su propia aprobación — nunca se gasta crédito sin que
tú lo confirmes primero:
1. **Idea → prompts**: escribes una idea en el dashboard, Claude (vía API de Anthropic)
   propone 5 variantes de prompt. Gratis, no toca Higgsfield.
2. **Prompt → imagen candidata**: apruebas un prompt → se genera una imagen de escena
   nueva (modelo `soul/reference`, ~1.5 créditos) que mantiene la identidad del personaje
   pero puede cambiar fondo/pose/aspect ratio. Barato, para previsualizar antes de gastar
   en video.
3. **Imagen → video**: apruebas esa imagen (o la regeneras si no te gustó) → se genera el
   video real (`kling-2.1-pro`, ~8 créditos) usando esa imagen ya aprobada como referencia.
4. **Video → publicar**: apruebas el video final → se publica al instante en las redes que
   traía el prompt. Lo que rechazas en cualquier paso nunca gasta el siguiente crédito.

Lo que necesitas configurar, plataforma por plataforma, son las credenciales para poder
generar y publicar. Es la parte que toma más tiempo la primera vez porque cada servicio
exige registrar una "app" — después de eso, todo corre desde el dashboard.

## 0. Instalar dependencias

```bash
cd ~/Documents/GitHub/iaplusyou
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Rellena `HF_API_KEY_ID` / `HF_API_KEY_SECRET` en `.env` con tus llaves de Higgsfield, y
`ANTHROPIC_API_KEY` con una API key de [console.anthropic.com](https://console.anthropic.com/)
(Settings → API Keys) — la necesita el dashboard para generar los 5 prompts por idea.

El paso de "video como personaje" (extraer un fotograma de referencia) necesita `ffmpeg`
instalado en el sistema: `brew install ffmpeg`.

---

## 0.1 Base de datos y worker

FlowPlus, las campañas de Meta y los swaps ya no viven solo en JSON: usan una base
SQLite (`data/creatv.db`) y una cola de tareas que procesa un proceso aparte.

1. Crea/actualiza el esquema (idempotente, se corre cada vez que hay migraciones nuevas):
   ```bash
   venv/bin/alembic upgrade head
   ```
2. La primera vez, importa lo que ya existía en `creative_flow_pendientes.json` /
   `ads.json` a la base (también idempotente, se puede volver a correr sin duplicar):
   ```bash
   python migrar_json_a_db.py
   ```
3. Instala el servicio del worker (procesa la cola: generación de FlowPlus, publicar
   en Meta, refrescar métricas, generar swaps):
   ```bash
   sudo cp deploy/creatv-worker.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now creatv-worker
   ```
   En local basta con correrlo en una segunda terminal: `venv/bin/python3 worker.py`.

**En cada despliegue hay que reiniciar los dos servicios**, no solo el dashboard:
```bash
sudo systemctl restart iaplusyou creatv-worker
```
Si solo se reinicia `iaplusyou`, el worker sigue corriendo código viejo y puede quedar
desalineado con el esquema de la base tras una migración.

**Cuentas con correo verificado** (registro con correo, "olvidé mi contraseña",
Configuración › Cuenta) necesitan dos variables más en el `.env` del servidor (el
servicio `iaplusyou` de gunicorn lo carga con `EnvironmentFile=.env`, así que no hay que
tocar la unidad de systemd):
- `PLATAFORMA_URL=https://app.creatvmachine.com`: la dirección pública fija del sitio. Es
  la base de los enlaces que viajan en los correos (confirmar cuenta, restablecer
  contraseña) — nunca se toma de la cabecera `Host` de la petición, que la manda quien
  pide — y el único host que el servidor atiende (cualquier otro `Host` responde 404;
  `localhost`/`127.0.0.1` pasan siempre). Con `https` la cookie de sesión sale `Secure`.
  Sin ella los enlaces usan el host de `META_REDIRECT_URI`, o `http://127.0.0.1:5050`
  en local, y el log lo avisa una vez.
- `DETRAS_DE_PROXY=1`: solo en el VPS, donde nginx está delante de gunicorn y es lo único
  que le llega. Con esto la IP y el esquema reales se leen de `X-Forwarded-For` /
  `X-Forwarded-Proto` (el último valor, el que añade nginx con
  `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` y
  `proxy_set_header X-Forwarded-Proto $scheme;`). En local déjala vacía: sin proxy,
  cualquiera podría inventar esas cabeceras y saltarse los límites por IP (5 registros,
  5 correos de verificación y 5 de recuperación por hora y por IP).
El correo sale por el SMTP de la sección de abajo; sin SMTP el administrador marca las
cuentas como verificadas desde el panel.

**Final edition** (guion + voz + música + texto en pantalla sobre un video de
CreativeFlowPlus ya aprobado) necesita que exista la carpeta donde cachea las pistas
de música generadas — no la crea sola, y si falta el worker revienta al primer
`final_producir`:
```bash
mkdir -p data/musica
```
No hace falta ninguna llave nueva en `.env`: usa las mismas `FAL_KEY` (fal.ai — voz y
música) y `ANTHROPIC_API_KEY` (guion) que ya configuraste en el paso 0.

**Experimentos** (campaña multi-país en Meta con métricas cada 2 h): no necesita
llaves nuevas — usa la conexión de Meta del proyecto (Configuración › Conectar con
Meta). La actualización periódica de métricas corre dentro de `creatv-worker`
(`worker.PERIODICAS`), así que sin el worker los experimentos se lanzan pero no se
refrescan solos. La migración `0004` agrega columnas a `experimento`: correr
`venv/bin/alembic upgrade head` en cada despliegue como siempre.

**Decisor y avisos por correo** (bloque 4): el worker evalúa cada experimento que corre
cada hora (`exp_decidir_todos`) y avanza las derivaciones cada 10 minutos
(`exp_avanzar_todos`) — sin `creatv-worker` nada de esto pasa. Los avisos por correo
(propuestas pendientes, ganador nuevo, anuncio rechazado por Meta, lanzamiento fallido)
son opcionales: se activan poniendo `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` y
`SMTP_FROM` en `.env` (ver `.env.example`) y el "Correo para avisos" del proyecto en
Configuración. Sin SMTP todo queda igualmente en la bitácora del experimento. Las
reglas por defecto del decisor se editan en Configuración y se pueden afinar por
experimento.

**Productos y tiendas** (bloque 5): `pip install -r requirements.txt` trae dos
dependencias nuevas (`cryptography`, `openpyxl`) y hay migración (`0005`). Las
credenciales de las tiendas se guardan cifradas con una clave derivada de
`FLASK_SECRET_KEY`: esa variable tiene que existir en el `.env` del servidor (si la
cambias, hay que volver a conectar cada tienda). Para conectar:
- **Shopify**: en la tienda, Configuración › Apps y canales de venta › Desarrollar apps ›
  Crear app › permisos `read_products` y `read_orders` › instalar y copiar el "Admin API
  access token" (empieza por `shpat_`). En Creatv: Configuración › Tienda › Shopify con el
  dominio `xxx.myshopify.com` y ese token.
- **WooCommerce**: WooCommerce › Ajustes › Avanzado › REST API › Añadir clave (permisos de
  lectura) → pegar Consumer key y Consumer secret junto con la URL https de la tienda.
- **MercadoLibre**: requiere una app en developers.mercadolibre.com con redirect URI
  `https://app.creatvmachine.com/meli/callback`; poner `MELI_APP_ID` y `MELI_SECRET` en
  `.env` y usar el botón "Conectar con MercadoLibre". MELI no manda UTM ni Pixel: sus
  experimentos se deciden por tráfico.
- **CSV/Excel**: columnas `nombre, precio, moneda, url_compra, fotos (varias con |),
  descripcion, categoria, sku`. **URL**: pega el enlace de un producto (lee JSON-LD / Open
  Graph).
El Pixel de Meta se comprueba desde Configuración › Pixel (botón "Comprobar"); con Pixel
activo los experimentos nuevos usan atribución `pixel`, con tienda Shopify/Woo conectada
usan `tienda` (pedidos con `utm_content`), si no `ninguna` (solo tráfico).

**Tablero** (bloque 6): la primera pestaña muestra gasto del mes, compras e ingresos
atribuidos, ROAS, el gráfico de 30 días, las 5 piezas ganadoras y las alertas. Las cifras
salen de los refrescos de métricas del worker (cada 2 h), así que el "mes" empieza en el
primer refresco del mes y cambia con cada uno; "Descargar CSV del mes" baja el detalle por
pieza. Con el Pixel comprobado y activo, los experimentos nuevos sugieren el objetivo
"Compras" (Meta optimiza por compra); sin Pixel, "Tráfico".

**Dónde está cada cosa** (desde 2026-09-17): los productos se crean y editan en **Catálogo**
(nombre, fotos, precio, URL de compra, "en prueba", prioridad, y el botón "Crear
experimento"); importar de Excel/CSV, de una URL o de una tienda es opcional y está ahí mismo
en "Traer productos de…". Los anuncios se hacen en **Experimentos** (un experimento con una
pieza y un país es un anuncio); la pestaña Campañas ya no existe y sus anuncios anteriores se
ven dentro de Experimentos. **Configuración** empieza con "Puesta a punto": una tarjeta por
servicio que se paga (Anthropic, fal.ai, Higgsfield, Cloudflare R2, Meta, correo, MercadoLibre)
con el paso a paso para conseguir la llave, qué cuesta y si está puesta en el servidor, y
después el paso a paso para conectar Shopify, WooCommerce y MercadoLibre. Las reglas del
decisor se editan en Experimentos › "Reglas del motor".

**Precios a la vista** (sin créditos): cada botón que gasta muestra "≈ US$" antes de
lanzar, cada pieza/final muestra lo que costó, y Configuración › **Gasto** tiene el total del
mes por tipo, el historial y un CSV. Son los precios reales de los proveedores (Higgsfield,
fal.ai, Anthropic); la pauta de Meta se cobra en la cuenta publicitaria del cliente y se
muestra aparte, en su moneda.

---

## 1. Cloudflare R2 — storage propio y permanente

Cada video generado se sube aquí antes de publicarse en cualquier red. Es tu copia
maestra: nunca depende de que la URL de Higgsfield siga viva, y es la URL que usa
Instagram para publicar.

1. Crea una cuenta en [dash.cloudflare.com](https://dash.cloudflare.com/) (el plan gratis alcanza de sobra para esto).
2. En el panel, ve a **R2 Object Storage** y crea un bucket, por ejemplo `higgsfield-videos`.
3. Entra al bucket > **Settings** > **Public access**, y activa **"Allow Access"** sobre el
   dominio `r2.dev` (te da una URL pública tipo `https://pub-xxxxxxxx.r2.dev` al instante).
   Si prefieres tu propio dominio (ej. `videos.tudominio.com`), conéctalo ahí mismo — es
   opcional, el `r2.dev` funciona igual de bien para esto.
4. Copia esa URL pública a tu `.env` como `R2_PUBLIC_BASE_URL` (sin barra al final), y el
   nombre del bucket como `R2_BUCKET_NAME`.
5. Ve a **R2 > Manage R2 API Tokens** > **Create API Token**.
   - Permisos: **Object Read & Write**.
   - Puedes limitarlo a este bucket específico.
   - Al crearlo te muestra el **Access Key ID** y el **Secret Access Key** — cópialos a tu
     `.env` como `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` (el secreto solo se muestra una vez).
6. Tu **Account ID** de Cloudflare aparece en la barra lateral derecha del dashboard, o en
   la URL del panel de R2. Ponlo en `.env` como `R2_ACCOUNT_ID`.

Con esto, `run_batch.py` sube automáticamente cada video a R2 después de generarlo — no
hace falta correr nada aparte, no requiere autorización OAuth como las redes sociales.

---

## 2. YouTube (Google Cloud)

1. Ve a [console.cloud.google.com](https://console.cloud.google.com/) y crea un proyecto nuevo (o usa uno existente).
2. En el buscador del panel, ve a **"APIs y servicios" > "Biblioteca"**, busca **"YouTube Data API v3"** y haz clic en **Habilitar**.
3. Ve a **"APIs y servicios" > "Pantalla de consentimiento OAuth"**:
   - Tipo de usuario: **Externo**.
   - Completa nombre de la app, tu correo, etc.
   - En "Scopes" agrega `.../auth/youtube.upload`.
   - En "Usuarios de prueba" agrega tu propio correo de Google (mientras la app no esté publicada/verificada, solo estos correos pueden autorizarla — es suficiente para uso personal).
4. Ve a **"APIs y servicios" > "Credenciales" > "Crear credenciales" > "ID de cliente de OAuth"**.
   - Tipo de aplicación: **App de escritorio**.
   - Descarga el JSON generado.
5. Guarda ese archivo descargado en la carpeta del proyecto con el nombre exacto:
   `client_secret_youtube.json`
6. Corre la autorización de una sola vez:
   ```bash
   python auth/auth_youtube.py
   ```
   Se abrirá el navegador, inicia sesión con la cuenta de YouTube donde quieres publicar y acepta. Esto crea `token_youtube.json`, que el uploader reutiliza automáticamente (se refresca solo).

Listo, YouTube queda funcionando.

---

## 3. Facebook + Instagram (Meta)

### 3.0 El cliente elige la forma

En Configuración › Meta cada proyecto elige cómo conectar (ADR 0003):

- **Que Creatv lo gestione** (recomendada). El cliente comparte su cuenta publicitaria, su
  Página y su Instagram con el ID del Business de Creatv desde Business Suite (Configuración
  del negocio › Socios › Agregar › «Dar acceso a un socio a tus activos»), pega el ID de su
  portafolio comercial en Creatv, ve sus activos y conecta. No toca developers.facebook.com y
  el acceso no caduca. Si no ve sus activos, «Avisar a Creatv» deja una solicitud en
  `/admin/meta`. Requisitos del lado de Creatv (una sola vez): `docs/meta/puesta-en-marcha-agencia.md`
  y `FLASK_SECRET_KEY` en el `.env` (el token de agencia se guarda cifrado).
- **Con mi propia app de Meta**. El cliente crea su app y conecta él; pasos abajo.

Requisito previo en ambos casos: una **Página de Facebook** y, para Reels, una cuenta de
**Instagram Business o Creator vinculada a esa Página**.

### 3.1 Con mi propia app (pasos del cliente)

CreatvMachine no pone una app propia en medio: solo comparte la URL de vuelta
(`META_REDIRECT_URI` en el `.env`), que el cliente pega tal cual en su app.

1. Ve a [developers.facebook.com/apps/creation](https://developers.facebook.com/apps/creation/), crea una
   app del tipo **Negocio** y elige tu **portafolio comercial**.
2. Casos de uso: **Crear y administrar anuncios (API de marketing)**, **Medir datos de rendimiento**,
   **Administrar todos los aspectos de tu Página** y, si vas a publicar Reels, **Administrar mensajes y
   contenido en Instagram**. En **Casos de uso › Personalizar**, agrega los permisos que falten.
3. **Inicio de sesión con Facebook para empresas › Configuraciones**: crea una configuración con
   **token de usuario** (el de usuario del sistema no sirve: Meta lo excluye para el portafolio dueño de la
   app), activos Páginas y Cuentas publicitarias (e Instagram si aplica) y los permisos `ads_management`,
   `ads_read`, `business_management`, `pages_show_list`, `pages_read_engagement`, `pages_manage_ads`,
   `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`. Copia el **identificador de
   configuración**.
4. **Inicio de sesión con Facebook para empresas › Configurar**: en «URI de redireccionamiento de OAuth
   válidos» pega `https://<tu-dominio>/meta/callback` (igual a `META_REDIRECT_URI`; con «Aplicar HTTPS»
   Meta rechaza `http://localhost`).
5. **Configuración › Básica**: nombre, correo de contacto, URL de términos, URL de política de privacidad,
   ícono 1024×1024 sin logos de Meta, categoría, propósito y «Eliminación de datos». Copia el
   **identificador de la app** y la **clave secreta**.
6. **Modo de la app: Live** (arriba del panel). Sin esto Meta rechaza cada anuncio con el subcódigo 1885183.
   En Live sin App Review solo pueden usar la app las personas con rol en ella (Roles de la app).
7. En Creatv, Configuración › Meta › «Con mi propia app» › pega los tres datos › **Guardar** › **Conectar
   con Meta** con el Facebook que administra la app, y elige cuenta y Página. Queda en
   `clientes/<cliente>/meta.json`. El token caduca a los 60 días: la tarjeta avisa y «Volver a conectar» basta.

---

## 4. TikTok

1. Ve a [developers.tiktok.com](https://developers.tiktok.com/) y crea una cuenta de desarrollador, luego **"Manage apps" > "Create an app"**.
2. En el panel de la app, agrega el producto **"Content Posting API"**.
3. En la configuración de la app, agrega la URI de redirección:
   `http://localhost:8766/callback`
4. Copia **Client Key** y **Client Secret** a tu `.env`:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   ```
5. Mientras la app esté en modo **sandbox/sin auditar**, ve a la sección de la app donde se agregan **"Target users"** (usuarios de prueba) y agrega tu propia cuenta de TikTok — solo esas cuentas podrán autorizar y recibir publicaciones, y quedarán como **privadas (Solo yo)** aunque el código pida otro nivel de privacidad.
6. Corre la autorización de una sola vez:
   ```bash
   python auth/auth_tiktok.py
   ```
   Esto genera `token_tiktok.json`.

**Para publicar público en cualquier cuenta** (no solo la tuya en modo prueba), TikTok exige
enviar la app a **auditoría de la Content Posting API** desde el panel de developers.tiktok.com,
explicando el caso de uso. Esto puede tardar varios días y es un proceso manual de TikTok,
no algo que se pueda automatizar.

### 4.1 Canales orgánicos en el dashboard

Con lo anterior configurado, cada proyecto ve en **Configuración › Canales orgánicos**
qué plataformas puede usar para publicar una pieza como contenido orgánico (sin pauta):

- **Facebook (Página)** e **Instagram Reels**: salen del `meta.json` que se guarda al
  «Conectar con Meta» desde el dashboard (Página con token de página; Instagram además
  necesita la cuenta profesional vinculada y el permiso `instagram_content_publish`).
- **YouTube Shorts** y **TikTok**: `clientes/<empresa>/token_youtube.json` y
  `token_tiktok.json`, generados en tu Mac con `auth/auth_youtube.py --cliente <empresa>`
  y `auth/auth_tiktok.py --cliente <empresa>` y copiados al servidor.

Publicar es público e irreversible: nada sale sin un clic («Publicar orgánico» en
Experimentos o en Crear, o aprobar la propuesta que el motor arma al declarar una
ganadora; solo en modo `auto` se publica sola). Nunca se publica dos veces la misma pieza
en la misma plataforma mientras haya una publicación viva. TikTok procesa el video
después de subirlo: la fila queda «subida, confirmando» hasta que TikTok confirma; si lo
rechaza, queda en error con el motivo y se puede reintentar. Mientras la app de TikTok no
esté auditada, el video sale como «Solo yo» y TikTok no devuelve enlace, solo un id.

---

## 5. Correr el pipeline completo

Edita `briefs_example.json` (o crea tu propio archivo) con tus videos, y luego:

```bash
python run_batch.py briefs_example.json
```

Por cada brief: genera el video con Higgsfield, lo descarga a `salidas/`, lo sube a R2, y
lo deja anotado como **pendiente** en `estado_videos.json`. Nada se publica en esta etapa.

Cuando quieras revisar lo generado:

```bash
python revisar.py
```

Te muestra, uno por uno, cada video pendiente (título, prompt, plataformas a las que se
publicaría, y lo abre en el navegador para que lo veas) y te pregunta:

- **s** → lo aprueba y lo publica de inmediato en todas las plataformas de su brief.
- **n** → lo rechaza, no se publica nunca en ninguna red.
- **Enter** → lo deja pendiente para revisarlo después (por si necesitas más tiempo).

Todo intento —generación, storage y cada publicación— queda registrado en
`registro_generaciones.csv`.

Puedes desactivar una plataforma temporalmente sin tocar código, solo poniendo por ejemplo
`ENABLE_TIKTOK=false` en `.env` antes de generar (esa lista queda grabada en el brief pendiente).

---

## 6. Manejar varias empresas (multi-cliente)

Este es el flujo pensado para cuando una empresa te manda su personaje/imagen de
referencia y tú generas y publicas videos para ellos, sin mezclar credenciales ni
contenido entre clientes.

**Lo que es tuyo y se comparte entre todos los clientes** (vive en el `.env` de la raíz):
- Las llaves de Higgsfield.
- Las apps registradas (Google Cloud, Meta, TikTok) — no hace falta crear una app nueva
  por cliente, cada uno simplemente autoriza su propia cuenta contra tus apps.
- El bucket de R2 (cada cliente tiene su propia carpeta dentro del mismo bucket).

**Lo que es propio de cada empresa** (vive en `clientes/<empresa>/`):
- Su `meta.json` con las credenciales de Meta (Página, cuenta de Instagram y cuenta
  publicitaria elegidas al conectar desde el dashboard).
- Sus tokens de YouTube y TikTok (`token_youtube.json`, `token_tiktok.json`).
- Su carpeta `personajes/` con las imágenes de referencia que te mandó.
- Su carpeta `briefs/` con los JSON de los videos a generar.

### Paso a paso para dar de alta un cliente nuevo

1. Crea su carpeta (o cópiala de `clientes/empresa_ejemplo/`):
   ```bash
   mkdir -p clientes/empresa_a/briefs clientes/empresa_a/personajes
   ```
2. Sube la imagen de referencia que te mandó y obtén su URL pública:
   ```bash
   python subir_personaje.py --cliente empresa_a ruta/a/foto-que-me-mandaron.jpg
   ```
   Esto la guarda en tu R2 bajo `clientes/empresa_a/personajes/` e imprime la URL —
   esa es la que va en `image_url` dentro de sus briefs.
3. Autoriza las cuentas de esa empresa (inicia sesión con LAS DE ELLOS, no las tuyas,
   cuando el navegador te lo pida):
   ```bash
   python auth/auth_youtube.py --cliente empresa_a
   # Meta: se conecta desde el dashboard (FlowMarketing > "Conectar con Meta"), no por script.
   python auth/auth_tiktok.py --cliente empresa_a
   ```
   (Salta el que no necesites según lo que te haya pedido esa empresa.)
4. Crea `clientes/empresa_a/briefs/lote1.json` con sus videos (usa la URL del paso 2
   como `image_url`).
5. Genera el lote (esto NO publica nada todavía):
   ```bash
   python run_batch.py clientes/empresa_a/briefs/lote1.json --cliente empresa_a
   ```
6. Revisa y publica lo que apruebes:
   ```bash
   python revisar.py --cliente empresa_a
   ```

Todo queda registrado en el mismo `registro_generaciones.csv` (con una columna `cliente`),
así que puedes ver de un vistazo la actividad de todas las empresas juntas. El manifiesto
de pendientes/rechazados/publicados de cada una vive en
`clientes/<empresa>/estado_videos.json`.

**Nota sobre TikTok con varios clientes reales**: mientras tu app no esté auditada, cada
cliente que autorices con `auth_tiktok.py --cliente` tiene que estar agregado como "target
user" de prueba en tu panel de TikTok for Developers, y solo publicará en privado. Para que
un cliente publique en público de verdad, hace falta pasar la auditoría de la Content
Posting API con tu app (una sola vez, cubre a todos los clientes futuros).

## 7. Nicho: fuentes de comentarios (Reddit, YouTube, Apify)

Las tres son opcionales: sin ellas, un estudio de Nicho funciona con texto pegado y CSV/Excel. Cada llave va en el `.env` raíz del servidor (nunca en la base ni en una URL) y aparece con su insignia en Configuración › Puesta a punto. Después de editar el `.env`, reinicia gunicorn y el worker.

### 7.1 Reddit (gratis para uso propio)

1. Con la cuenta de Reddit de la empresa entra a [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) y pulsa **create another app…**.
2. Tipo **script**, nombre `creatv-machine`, redirect uri `http://localhost:8080` (no se usa). Crea la app.
3. Copia el id que aparece bajo el nombre como `REDDIT_CLIENT_ID` y el **secret** como `REDDIT_CLIENT_SECRET`.
4. `REDDIT_USER_AGENT` debe describir la app, por ejemplo `creatv-machine/1.0 (by u/tu_usuario)`; Reddit rechaza user agents genéricos.

Límites: 100 llamadas por minuto por app (la recolección hace una pausa de 1 s entre llamadas). La API gratis es para uso **no comercial**; si Creatv Machine se vende como producto, hay que pedir acceso comercial a Reddit antes de usar esta fuente para clientes.

### 7.2 YouTube Data API (gratis, con cuota)

Es una **llave de API** simple, distinta del OAuth de publicación de la sección 2 (que sigue igual).

1. En el mismo proyecto de Google Cloud donde habilitaste **YouTube Data API v3**, ve a **APIs y servicios › Credenciales › Crear credenciales › Clave de API**.
2. En **Restricciones de API** limítala a YouTube Data API v3.
3. Cópiala como `YOUTUBE_API_KEY`.

Cuota: la búsqueda (`search.list`) tiene un cupo de **100 llamadas por día** por proyecto; cada recolección usa una. Leer comentarios cuesta 1 unidad por página de 100, de las 10 000 diarias. Los links de video no gastan búsqueda.

### 7.3 Apify (de pago, por resultado)

1. Crea la cuenta en [apify.com](https://apify.com) (trae crédito gratis mensual) y agrega una tarjeta si vas a superarlo.
2. **Settings › Integrations › Personal API token**: cópialo como `APIFY_TOKEN`.

El dashboard usa dos actores de la tienda, ambos con precio por resultado: `junglee~amazon-reviews-scraper` (≈ US$ 3 por 1 000 reseñas) y `clockworks~tiktok-comments-scraper` (≈ US$ 0,50 por 1 000 comentarios). Antes de cada clic se muestra el estimado y la corrida nunca se reintenta sola; el gasto real queda en Configuración › Gasto como tipo `recoleccion`. Traer datos de Amazon o TikTok por scraping es una zona gris de sus términos de uso: es responsabilidad de quien pone el token.

## Resumen de limitaciones a tener en cuenta

- **Instagram** usa la URL pública de tu bucket R2 (no la de Higgsfield), así que no depende
  de que esa URL temporal siga viva. Si por algún motivo falla la subida a R2, el pipeline
  cae de vuelta a la URL de Higgsfield para no bloquear la publicación, pero eso solo pasa
  si algo está mal configurado en R2 — revisa el log en ese caso.
- **TikTok** solo publica público después de que tu app pase auditoría; mientras tanto,
  solo prueba con tu propia cuenta y en modo privado. No hay apuro en esto, tómate el tiempo
  que haga falta para que la auditoría quede bien hecha.
- **YouTube** y **Facebook** funcionan de inmediato con tu propio usuario, sin revisión externa.
- Cada video queda guardado para siempre en tu bucket de R2, con nombre `<id_del_brief>.mp4`,
  independientemente de si la publicación en alguna red falla o no.
- **La revisión (`revisar.py`) la corres tú desde la terminal.** Si el cliente final
  necesita aprobar él mismo sin depender de ti, esto se puede convertir después en una
  página web simple donde solo hace clic en "aprobar"/"rechazar" — díselo si les hace
  falta, pero de momento el flujo asume que tú (el admin) tienes la última palabra al
  correr el comando, aunque la decisión te la haya dado el cliente por otro medio.
