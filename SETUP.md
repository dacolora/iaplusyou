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

Requisito previo: necesitas una **Página de Facebook** y una cuenta de **Instagram
Business o Creator vinculada a esa Página** (se vincula desde Configuración de la Página
de Facebook > Instagram > Conectar cuenta).

1. Ve a [developers.facebook.com/apps](https://developers.facebook.com/apps) y crea una app nueva, tipo **"Otro" > "Empresa"**.
2. En el panel de la app, agrega el producto **"Facebook Login for Business"**.
3. En **Facebook Login for Business > Configuración**, agrega en "URIs de redirección de OAuth válidas":
   `http://localhost:8765/callback`
4. Agrega también el producto **"Instagram Graph API"** (o "Instagram" si aparece así) desde el catálogo de productos.
5. En **Configuración básica** de la app, copia el **ID de la app** y el **secreto de la app**, y ponlos en tu `.env`:
   ```
   META_APP_ID=...
   META_APP_SECRET=...
   ```
6. Mientras la app esté en modo "Desarrollo" (no publicada), solo los usuarios con rol de **administrador/desarrollador/tester de la app** (agregados en "Roles de la app") pueden autorizarla. Agrégate a ti mismo si no apareces ya.
7. Corre la autorización de una sola vez:
   ```bash
   python auth/auth_meta.py
   ```
   Inicia sesión, autoriza los permisos, elige tu Página si tienes varias. El script imprime `META_PAGE_ACCESS_TOKEN`, `META_PAGE_ID` y `META_IG_USER_ID` — cópialos a tu `.env`.

**Nota sobre permisos avanzados**: los scopes `pages_manage_posts`, `publish_video` e
`instagram_content_publish` son "permisos avanzados". Para uso personal (tu propia Página,
mientras la app está en modo Desarrollo con tu usuario como administrador) funcionan sin
revisión de Meta. Si más adelante quieres que otra persona/negocio use esta misma app,
Meta exige pasar **App Review** para esos permisos.

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
- Su `.env` con `META_PAGE_ACCESS_TOKEN`, `META_PAGE_ID`, `META_IG_USER_ID`.
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
   python auth/auth_meta.py --cliente empresa_a
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
