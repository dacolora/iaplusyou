# Nicho y avatares — diseño

Fecha: 2026-09-18. Estado: aprobado por secciones en conversación; pendiente de
revisión escrita. Dos partes, cada una del tamaño de un plan de implementación:
**Parte 1** = tablas, datos, texto pegado y CSV/Excel, generación con Claude,
revisión, aprobar → persona, exportaciones, pantalla y worker de generación.
**Parte 2** = las fuentes conectadas (Reddit, YouTube y, de último, Apify) con
su worker de recolección y sus llaves en Puesta a punto. La Parte 1 ya es útil
sola: con comentarios pegados a mano se obtienen avatares reales.

## 0. Propósito y relación con lo que existe

Hoy las **personas** de Sprints (arquetipos de cliente, tabla `persona`) las
inventa Claude a partir de la guía de estilo y el catálogo
(`sprints/sugerencias.py`). No hay evidencia detrás: son plausibles, no reales.

Este módulo las hace nacer de lo que la gente escribe de verdad. El usuario crea
un **estudio** (un nicho o producto), recoge **comentarios** reales de varias
fuentes (texto pegado, CSV/Excel, Reddit, YouTube, Amazon/TikTok vía Apify), y
Claude los agrupa en **avatares**: un avatar **núcleo** por deseo ("quiero que
lavar la ropa sea fácil y que igual limpie bien") y, dentro de cada núcleo,
**sub-avatares** por emoción o por experiencia con el producto, cada uno con
los campos de las dos plantillas que usa el cliente (el doc "Desire-Based Core
Avatar" y la hoja "Personas" de HappyFlops) y con las **citas textuales** que
lo sustentan. Aprobar un sub-avatar crea una `persona` con origen
`investigada`, así Sprints, ideas y Crear lo consumen sin cambiar nada.

Decisiones tomadas con Daniel (2026-09-18):

- Vive **dentro de cada proyecto** (pestaña nueva "Nicho"), no en un espacio
  global. Un proyecto puede tener varios estudios (uno por producto o nicho).
- Enfoque **A**: módulo nuevo `nicho/` con tablas propias, fuentes con contrato
  común (como `conectores/base.py`) y tareas en el worker; no se extiende
  Sprints › Personas ni se parsea un documento libre.
- Las cuatro fuentes entran en la versión 1; la de pago (Apify) es la última
  pieza que se implementa y lleva su propia puerta de costo.
- Un sub-avatar aprobado alimenta las **personas de Sprints**. El personaje
  visual generado desde el avatar queda fuera de esta versión.

Qué existe y qué es nuevo:

| Concepto | Estado hoy |
|---|---|
| Persona (arquetipo) | Tabla `persona`, origen `manual` / `sugerida_ia`; `sprints/datos.py` es el único escritor; `sprints/ideas._persona_texto` la mete al prompt maestro |
| Fuentes externas de texto | No existe (solo `referencias_link` baja videos con yt-dlp) |
| Contrato de conector | `conectores/base.py` (tiendas): `tipo`, `probar()`, dicts normalizados, `ErrorConector.usuario` |
| Registro de modelos con precio | `providers/flowplus_modelos.py` (patrón a copiar para actores de Apify) |
| Llamada a Claude con JSON | `sprints/analisis._llamar` + `_parsear_json`; `generador_prompts.MODEL` (`claude-sonnet-5` salvo `ANTHROPIC_MODEL`) |
| Tareas en el worker | `tareas/__init__.registrar` / `al_interrumpir`, `trabajos.encolar`, `cola.reportar`, `iniciarPolling()` en `base.html` |
| Puesta a punto de llaves | `dashboard._estado_llaves` (solo `bool(os.environ.get(...))`) |
| Exportar Excel | `openpyxl` ya está en `requirements.txt` |

Filosofía que se mantiene: nada gasta crédito sin un clic con el costo a la
vista; nada se genera ni se recoge solo; un doble clic no lanza dos veces.

## 1. Flujo y puertas

```
Nuevo estudio (nombre + producto + tema + idioma)              gratis
  -> agregar comentarios, las veces que haga falta:
       pegar texto / subir CSV o Excel                         gratis, en la ruta
       Reddit por palabras clave o links de posts              gratis, worker
       YouTube por palabras clave o links de videos            gratis, worker
       Amazon o TikTok vía Apify                               [≈ $ a la vista] -> worker, max_intentos=1
  -> curar: excluir comentarios, quitar una fuente entera      gratis
  -> [≈ $ y N comentarios a la vista] -> Generar avatares      Claude, worker, max_intentos=1
  -> revisar: editar campos, leer las citas que lo sustentan
  -> [Aprobar un sub-avatar] -> persona con origen "investigada"
  -> exportar .md o .xlsx (formato de la hoja "Personas")      gratis
```

Estados del estudio: `armando` (recibiendo comentarios) → `generando` (tarea de
Claude viva) → `revisando` (hay avatares). Se guardan y se recalculan tras cada
evento (`nicho/datos.recalcular`), como hace `sprints/estado`, con esta regla:
`generando` si hay una tarea viva con el job_id de generación del estudio
(`cola.consultar_por_job`); si no, `revisando` si el estudio tiene al menos un
avatar; si no, `armando`. Regenerar vuelve a pasar por `generando`.
`archivado` es una bandera aparte.

## 2. Modelo de datos

Migración `0011_nicho` (`down_revision = '0010'`), tablas declaradas también en
`db.py`. Columnas comunes como en sprints: `cliente` (String 80),
`creado_en`, `actualizado_en` (String 19). Índice por `cliente` en las tres.

**`estudio`**

| Columna | Tipo | Notas |
|---|---|---|
| `nombre` | String 120 | obligatorio |
| `producto` | Text | qué vendemos, texto libre; se prellena al elegir un producto del catálogo |
| `catalogo_id` | String 80, nullable | id del activo del catálogo elegido, si lo hubo |
| `tema` | Text | qué buscar: nicho, mercado, dolores, palabras clave |
| `idioma` | String 5 | idioma de salida de los avatares, por defecto `es` |
| `estado` | String 12 | `armando` / `generando` / `revisando` |
| `archivado` | Boolean | por defecto 0 |
| `generacion` | Integer | número de la última corrida de Claude, empieza en 0 |
| `extra` | JSON | `recolecciones` (lista de registros), `ultima_generacion` (resumen), `ultimo_error` |

**`comentario`** — único por `(estudio_id, fuente, fuente_id)`
(`uq_comentario_fuente`).

| Columna | Tipo | Notas |
|---|---|---|
| `estudio_id` | Integer FK | |
| `fuente` | String 12 | `texto` / `csv` / `reddit` / `youtube` / `apify` |
| `fuente_id` | String 120 | id del comentario en la fuente; hash del texto normalizado para `texto`/`csv` |
| `texto` | Text | limpio, sin caracteres de control, máximo 2 000 caracteres |
| `url` | String 500, nullable | link al original |
| `contexto` | String 300, nullable | título del post, del video o del producto |
| `puntuacion` | Integer, nullable | votos, likes o estrellas |
| `fecha` | String 19, nullable | ISO sin zona, como `_fecha_iso` de conectores |
| `excluido` | Boolean | el usuario lo sacó; nunca entra a la generación |
| `extra` | JSON | lo que la fuente quiera guardar (subreddit, id del video, actor) |

No se guarda el nombre del autor: no hace falta para los avatares y expone
menos datos ajenos si el proyecto se publica.

**`avatar`**

| Columna | Tipo | Notas |
|---|---|---|
| `estudio_id` | Integer FK | |
| `padre_id` | Integer, nullable | vacío en un núcleo; id del núcleo en un sub-avatar |
| `tipo` | String 8 | `nucleo` / `sub` |
| `base` | String 24, nullable | `emocion` / `experiencia_producto` (solo sub) |
| `orden` | Integer | orden dentro del padre |
| `generacion` | Integer | corrida que lo creó |
| `nombre` | String 120 | "Melissa / La que regala con cabeza" |
| `deseo` | String 300 | en primera persona |
| `resumen` | Text | solo núcleo |
| `demografia` | Text | edad, género, dónde vive, momento de vida (vacío si los comentarios no lo dicen) |
| `edad_rango` | String 20 | "30-45" o vacío |
| `emocion` | Text | una línea |
| `identidad` | JSON | `{quiere_que_vean, cree_de_si, quiere_lograr}` (filas 4, 5 y 6 de la hoja) |
| `soluciones_previas` | JSON | lista de `{que, por_que_fallo: [..]}` (filas 8–11 y "Product experiences") |
| `situaciones` | JSON | lista de escenas del día a día (fila 12 y "Situational experiences") |
| `comportamiento` | Text | qué hace hoy y por qué |
| `conciencia` | JSON | `{nivel, detalle}`; nivel ∈ `inconsciente`, `consciente_del_problema`, `consciente_de_la_solucion`, `consciente_del_producto`, `muy_consciente` |
| `encaje_producto` | Text | cómo nuestro producto le resuelve el deseo (fila 7) |
| `tono` | Text | cómo habla esa gente, una línea |
| `palabras_clave` | JSON | lista |
| `evidencia` | JSON | lista de `{comentario_id, cita}` verificadas |
| `sin_evidencia` | Boolean | ninguna cita sobrevivió a la verificación |
| `estado` | String 12 | `propuesto` / `aprobado` / `descartado` |
| `persona_id` | Integer, nullable | la persona creada al aprobar |
| `extra` | JSON | |

`ORIGENES_PERSONA` en `sprints/datos.py` gana `investigada` (11 caracteres,
cabe en String 12). `crear_persona` acepta `extra` opcional.

`nicho/datos.py` es el **único escritor** de las tres tablas. API:

- Estudios: `crear_estudio(cliente, nombre, producto, tema, idioma="es", catalogo_id=None)`,
  `actualizar_estudio(cliente, id, **campos)`, `archivar_estudio`, `estudios(cliente)`,
  `estudio(cliente, id)`, `recalcular(cliente, id)`, `registrar_recoleccion(cliente, id, registro)`.
- Comentarios: `agregar_comentarios(cliente, estudio_id, fuente, lista) -> {"nuevos", "repetidos"}`
  (una transacción, `INSERT OR IGNORE` sobre la clave única), `comentarios(cliente, estudio_id,
  fuente=None, pagina=1, por_pagina=50)`, `contar_por_fuente(cliente, estudio_id)`,
  `excluir_comentario(cliente, id, excluido)`, `borrar_fuente(cliente, estudio_id, fuente)`.
- Avatares: `guardar_generacion(cliente, estudio_id, nucleos, resumen)`, `avatares(cliente,
  estudio_id)` (núcleos con sus subs anidados), `actualizar_avatar(cliente, id, **campos)`,
  `aprobar_avatar(cliente, id) -> persona_id`, `descartar_avatar(cliente, id)`.

Toda lectura-modificación-escritura sobre `estudio.extra` toma el bloqueo de
escritura de SQLite antes de leer (mismo `BEGIN IMMEDIATE` que
`experimentos._bloquear`): Flask y el worker escriben la misma fila.

## 3. Fuentes

### 3.1 Contrato (`nicho/fuentes/base.py`)

```python
CLAVES_COMENTARIO = ("fuente_id", "texto", "url", "contexto", "puntuacion", "fecha", "extra")

class Fuente:
    tipo = None          # "texto" | "csv" | "reddit" | "youtube" | "apify"
    de_pago = False      # True muestra la puerta de costo
    def probar(self): ...                       # {"ok", "detalle"}; no gasta
    def estimar(self, params): ...              # solo de_pago: {"max_resultados", "usd"}
    def recolectar(self, params, avanzar): ...  # itera dicts normalizados
```

`normalizar_comentario(d)` es el único camino: quita caracteres de control,
colapsa espacios, recorta a 2 000 caracteres, descarta textos de menos de 3
caracteres, cae al hash del texto como `fuente_id` cuando la fuente no trae
uno, valida `url` http(s), castea `puntuacion` a entero y `fecha` a ISO de 19
caracteres. `ErrorFuente(usuario)` es el único error que sale al dashboard o
al worker: mensaje en español, nunca llaves ni HTML ajeno (pasar por
`cola.sin_token` antes de guardar). `avanzar(etapa, detalle)` es el callback
de progreso que el worker traduce a `cola.reportar`.
`nicho/fuentes/__init__.py` registra por `tipo` y carga perezosamente
(`por_tipo`), como `conectores`.

### 3.2 Texto pegado y CSV/Excel (en la ruta, sin worker)

- `texto`: `partir_texto(texto, modo)` con `modo` = `lineas` (una línea por
  comentario) o `parrafos` (separados por línea en blanco). `fuente_id` =
  primeros 16 hex del SHA-1 del texto normalizado (minúsculas, espacios
  colapsados), así el mismo comentario pegado dos veces no se duplica.
- `csv` (la misma fuente para los dos formatos): archivos `.csv` (delimitador
  detectado con `csv.Sniffer`) o `.xlsx` (primera hoja, openpyxl), fila de
  encabezados. Columna de texto por nombre
  (`texto`, `comentario`, `comment`, `review`, `body`, `content`, `text`,
  `reseña`, `resena`, `mensaje`, `opinion`, sin importar mayúsculas) o, si no
  hay, la columna con mayor largo medio de texto. Columnas opcionales: url
  (`url`, `link`, `enlace`), puntuación (`score`, `likes`, `votos`,
  `puntuacion`, `rating`, `upvotes`), fecha (`fecha`, `date`, `created`,
  `published`). Máximo 5 MB y 5 000 filas. `fuente_id` = hash del texto.
- La ruta responde "entraron N, repetidos M" en un flash.

### 3.3 Reddit (API oficial, `requests`, sin librería nueva)

Llaves en el `.env` raíz: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USER_AGENT` (Reddit exige un user agent descriptivo, ej.
`creatv-machine/1.0 (by u/<usuario>)`). Token de solo lectura con
`POST https://www.reddit.com/api/v1/access_token`, `grant_type=client_credentials`,
autenticación básica `client_id:client_secret`; se pide al empezar la tarea y
no se guarda.

Parámetros: `palabras_clave` (obligatorio salvo que haya links), `subreddits`
(lista opcional), `links` (posts concretos, opcional), `max_posts` (tope 25),
`max_comentarios_por_post` (tope 200), `periodo` (`year` por defecto).

1. Búsqueda: `GET https://oauth.reddit.com/search?q=…&sort=relevance&t=<periodo>&limit=<max_posts>&type=link&raw_json=1`,
   o `GET /r/<sub>/search?…&restrict_sr=1` por subreddit. De un link se saca el
   id del post (`/comments/<id>/`).
2. Por post: `GET https://oauth.reddit.com/comments/<id>?sort=top&limit=<n>&depth=2&raw_json=1`.
   El texto del post (`selftext`) entra como comentario con `fuente_id` =
   id del post; cada `t1` entra con su id; se saltan `[deleted]`,
   `[removed]`, `more` y los de `AutoModerator`. `puntuacion` = `score`,
   `fecha` = `created_utc`, `url` = `https://www.reddit.com<permalink>`,
   `contexto` = título del post, `extra.subreddit`.
3. Una pausa de 1 s entre llamadas (queda bajo las 100 por minuto). Ante 429
   espera `Retry-After` (o 10 s) y reintenta hasta 3 veces; si sigue, entrega
   lo recogido y deja el aviso "Reddit limitó las llamadas; guardé X
   comentarios" en el registro de la recolección. 401/403 → `ErrorFuente`
   "Reddit no aceptó las llaves…".

Uso comercial: la API gratis de Reddit es para uso no comercial; si el
proyecto se vende como producto hay que pedir acceso comercial a Reddit. Se
anota en `SETUP.md`.

### 3.4 YouTube (API oficial, `google-api-python-client` que ya está)

Llave `YOUTUBE_API_KEY` (llave simple de Google Cloud con YouTube Data API v3
habilitada; los comentarios públicos no necesitan OAuth).

Parámetros: `palabras_clave`, `links` (videos concretos: `watch?v=`,
`youtu.be/`, `/shorts/`), `max_videos` (tope 10), `max_comentarios_por_video`
(tope 500), `idioma` y `region` para la búsqueda (por defecto los del estudio
y `proyectos.pais`).

1. `search().list(part="id,snippet", q=…, type="video", maxResults=max_videos,
   relevanceLanguage=idioma, regionCode=region)`: 100 unidades de las 10 000
   diarias. El título viene en `snippet.title` (contexto).
2. `commentThreads().list(part="snippet", videoId=…, maxResults=100,
   order="relevance", textFormat="plainText", pageToken=…)`: 1 unidad por
   página, hasta el tope. `texto` = `textOriginal`, `puntuacion` = `likeCount`,
   `fecha` = `publishedAt`, `url` = `https://www.youtube.com/watch?v=<vid>&lc=<id>`,
   `extra.video_id`.
3. `HttpError` 403 `commentsDisabled` → se salta el video; `quotaExceeded` →
   entrega lo recogido y avisa; 400 `keyInvalid` → `ErrorFuente`.

### 3.5 Apify (Amazon y TikTok; de pago)

Llave `APIFY_TOKEN`, enviada como cabecera `Authorization: Bearer …` (nunca
en la URL, para que no caiga en logs).

Registro `nicho/fuentes/apify_actores.py`, mismo patrón que
`flowplus_modelos`: por clave (`amazon_resenas`, `tiktok_comentarios`) el
`actor` (id `usuario/nombre`), `nombre` visible, `armar_entrada(links,
max_resultados)`, `leer_item(item)` → dict normalizado, y `usd_por_resultado`.
Solo entran actores con precio **por resultado**; los que cobran por cómputo
no se pueden estimar y quedan fuera.

Parámetros: `actor` (clave del registro), `links` (productos de Amazon o
videos de TikTok), `max_resultados` (tope 1 000).

`estimar` = `max_resultados × usd_por_resultado`, mostrado como "≈ $X por
hasta N resultados (aprox.: Apify cobra por resultado y por cómputo)".
`recolectar`: `POST /v2/acts/<actor>/runs` con la entrada → id de la corrida;
sondeo de `GET /v2/actor-runs/<id>` cada 10 s hasta `SUCCEEDED` / `FAILED` /
`ABORTED` / `TIMED-OUT`, máximo 20 minutos; luego
`GET /v2/datasets/<defaultDatasetId>/items?clean=true&limit=<max>`. Corrida
fallida o vencida → `ErrorFuente` con el estado (sin token).

> ⚠️ **Verificar antes de implementar**: los ids exactos de los actores de
> reseñas de Amazon y de comentarios de TikTok, la forma de su entrada y
> salida, y su precio por resultado en la tienda de Apify. Van al registro con
> la fecha de verificación en el docstring, como hace `flowplus_modelos`.

### 3.6 Llaves y puesta a punto

Las tres son herramientas compartidas, como Anthropic o fal: `.env` raíz, en
`.env.example`, y en Configuración › Puesta a punto (`_estado_llaves`) con la
insignia de configurada o falta, calculada solo con `bool(os.environ.get(...))`.
Sin la llave, la tarjeta de esa fuente dice qué variable falta y el botón
queda apagado. `SETUP.md` gana una sección con los pasos humanos: registrar la
app en Reddit (tipo *script*), crear la llave de YouTube Data API v3 en Google
Cloud, sacar el token de Apify.

Meta no entra en esta versión; podría entrar después para comentarios de las
páginas propias del proyecto usando la conexión que ya existe (`meta.json`).

## 4. Generación con Claude (`nicho/avatares.py`)

### 4.1 Qué entra

`seleccionar(comentarios, max_n=600, max_caracteres=250_000)`: fuera los
`excluido`; dentro de cada fuente se ordenan por `puntuacion` desc, `fecha`
desc, `id`; se toman en **ronda entre fuentes** hasta llenar el primer tope
que se alcance, para que una fuente no acapare. Cada comentario va numerado con
su `id` real de la tabla. Entran también el tema, el producto del estudio y
`marca.guia_efectiva(cliente)` (vacío si no hay).

### 4.2 Dos pasadas

**Pasada 1 — núcleos por deseo** (una llamada). Prompt: estratega que lee
comentarios reales y los agrupa por el deseo de fondo. Devuelve SOLO JSON:

```json
{"nucleos": [
  {"nombre": "Lavar sin cargar peso",
   "deseo": "Quiero que lavar la ropa sea fácil y que igual limpie bien",
   "resumen": "…",
   "comentarios": [12, 15, 40]}
]}
```

De 2 a 5 núcleos; un comentario cae en un solo núcleo o en ninguno (si Claude
lo repite, se queda en el primero). Un núcleo sin comentarios válidos se
descarta.

**Pasada 2 — sub-avatares** (una llamada por núcleo, con el núcleo y solo sus
comentarios). Devuelve SOLO JSON:

```json
{"sub_avatares": [
  {"base": "emocion",
   "nombre": "Melissa / La que regala con cabeza",
   "deseo": "…", "demografia": "…", "edad_rango": "30-45", "emocion": "…",
   "identidad": {"quiere_que_vean": "…", "cree_de_si": "…", "quiere_lograr": "…"},
   "soluciones_previas": [{"que": "Detergente líquido de marca", "por_que_fallo": ["Pesado de cargar", "Gotea en el estante"]}],
   "situaciones": ["Cargando garrafas de 2 litros desde el súper"],
   "comportamiento": "Sigue comprando líquido porque es lo probado",
   "conciencia": {"nivel": "consciente_del_problema", "detalle": "…"},
   "encaje_producto": "…",
   "tono": "…",
   "palabras_clave": ["…"],
   "evidencia": [{"comentario_id": 12, "cita": "…"}]}
]}
```

De 2 a 4 sub-avatares por núcleo, al menos uno de cada `base` cuando la
evidencia lo permita. El prompt pide las preguntas de la hoja "Personas" con
sus mismos rótulos, `demografia`/`edad_rango` **solo si los comentarios dan
señales** (si no, vacío), `deseo` en primera persona, 3 a 5 problemas por
solución previa, 2 a 4 situaciones, 2 a 5 citas **literales** por sub-avatar,
todo en `estudio.idioma` salvo las citas, que se conservan en el idioma en que
la gente escribió. Modelo: `generador_prompts.MODEL`; llamada con el mismo
patrón de `sprints/analisis._llamar` (`max_tokens` 4 000 en la pasada 1 y
8 000 en la 2 (tope de corte, no de costo; el estimado usa 1 500 y 3 000 por
núcleo de salida esperada)).

### 4.3 Validación y evidencia

`_parsear_nucleos` / `_parsear_subs` aceptan el JSON aunque venga entre
```` ``` ````, exigen las claves, castean listas, recortan largos (nombre 120,
deseo 300, textos 1 500, listas de hasta 8 elementos) y descartan un sub-avatar
sin `nombre` o sin `deseo`. `base` fuera de las dos opciones → `emocion`.
`conciencia.nivel` fuera de los cinco → vacío (no se inventa).

`verificar_evidencia(sub, comentarios_por_id)`: una cita vale si es un
fragmento literal del comentario que dice, comparando sin importar mayúsculas
ni espacios múltiples y con al menos 12 caracteres. La que no aparece se
descarta. Un sub-avatar que se queda sin citas **no se borra**: queda con
`sin_evidencia=True` para que el usuario decida. Sin esta verificación el doc
sería inventado, y toda la gracia es que no lo sea.

### 4.4 Puerta de costo

`estimar_costo(comentarios, modelo)` → `{"comentarios", "tokens", "usd"}`.
Tokens de entrada ≈ caracteres / 3.5 (conservador para español); la entrada
se cuenta dos veces (pasada 1 y de nuevo repartida en la pasada 2) más 800 de
prompt por llamada; salida ≈ 1 500 (pasada 1) + 3 000 × 5 núcleos (peor caso).
USD = entrada × precio de entrada + salida × precio de salida, redondeado hacia
arriba al centavo y mostrado con "≈". Precios en `PRECIOS_USD_POR_MILLON` del
módulo; si el modelo configurado no está en la tabla se estima con el precio
más alto registrado y se dice "estimado con precio de referencia".

> ⚠️ **Verificar antes de implementar**: los precios por millón de tokens del
> modelo configurado, contra la documentación de Anthropic, no de memoria
> (la skill `claude-api` es la referencia).

Con menos de `MIN_COMENTARIOS = 20` comentarios no excluidos el botón queda
apagado con la explicación. La tarea se encola con `max_intentos=1`.

### 4.5 Si Claude falla

JSON inválido o sin las claves en la pasada 1: la tarea queda en `error` con
mensaje claro, no se guarda nada, el estudio vuelve al estado anterior y el
mensaje dice que ese intento sí se cobró. Si falla la pasada 2 de **un**
núcleo, los demás se guardan y ese núcleo queda sin sub-avatares y con el error
en `avatar.extra.error`.

### 4.6 Guardado (`datos.guardar_generacion`)

Una sola transacción: `estudio.generacion += 1`; se borran los sub-avatares
`propuesto` y `descartado` de corridas anteriores y los núcleos que se quedan
sin ningún sub-avatar `aprobado`; se conservan los `aprobado` y los núcleos
que tengan al menos uno; se insertan los nuevos con la generación actual y
`orden`; el estudio pasa a `revisando`; `extra.ultima_generacion` guarda
`{generacion, nucleos, subs, con_evidencia, sin_evidencia, comentarios,
usd_estimado, fecha}`.

## 5. Aprobar → persona (`datos.aprobar_avatar`)

Solo los sub-avatares se aprueban o descartan; el núcleo es una agrupación y
no tiene botones. Mapeo a `persona` (origen `investigada`):

| persona | ← avatar |
|---|---|
| `nombre` | `nombre` |
| `resumen` | `deseo` (recortado a 200) |
| `descripcion` | demografía + emoción + comportamiento + soluciones previas ("Usó X: a; b. Usó Y: c.") |
| `edad_rango` | `edad_rango` |
| `tono` | `tono` |
| `senales_visuales` | `situaciones` |
| `palabras_clave` | `palabras_clave` |
| `color` | siguiente de `sugerencias.COLORES` |
| `extra` | `{avatar_id, estudio_id, identidad, conciencia, encaje_producto, evidencia}` |

Si el avatar ya tiene `persona_id`, aprobar de nuevo **actualiza** esa persona
(y la desarchiva si estaba archivada) en vez de crear otra. `descartar_avatar`
sobre un aprobado marca `descartado` y **archiva** su persona (reversible).
Editar un avatar aprobado no toca la persona hasta que se vuelva a aprobar.

## 6. Exportación

- `exportar_md(estudio)`: documento como el del detergente: un encabezado por
  núcleo con su deseo, y por sub-avatar todas las filas en el orden de la hoja
  "Personas", luego emoción, comportamiento, tono y las citas con su link.
- `exportar_xlsx(estudio)`: una hoja "Personas" con la plantilla del cliente:
  columna A los rótulos (Nombre / arquetipo, frase de cabecera, Demographics
  (ASL), las tres preguntas de identidad, cómo ayuda el producto, soluciones
  probadas y por qué fallaron, el día a día, nivel de conciencia, y al final
  emoción, comportamiento, tono, citas), una columna por sub-avatar aprobado o
  propuesto (los descartados no salen), en el orden núcleo → sub. Solo openpyxl.

## 7. Pantalla

Pestaña **Nicho** en `_sidebar.html` (`data-tab="nicho"`, después de Tablero) y
`<section id="tab-nicho">` en `cliente.html` con `_tab_nicho.html`, parciales
`_nicho_estudio.html`, `_nicho_comentarios.html`, `_nicho_avatares.html`.
Blueprint `nicho/rutas.py` (`bp = Blueprint("nicho", __name__,
url_prefix="/cliente/<cliente>/nicho")`) registrado en `dashboard.py`, con el
mismo guard por cliente que sprints; `nicho_rutas.contexto(cliente)` entra a
la página del proyecto y la pestaña lista los estudios; cada estudio abre en
su propia página `nicho_estudio.html` (`GET /cliente/<cliente>/nicho/<id>`),
como `sprint_detalle.html`.

- **Lista de estudios**: nombre, producto, chip de estado, "N comentarios de
  M fuentes", "K avatares aprobados". "Nuevo estudio": nombre, producto (con
  selector de `catalogo_productos.listar(cliente, "producto")` que prellena el
  texto), tema, idioma. Archivar.
- **Comentarios**: cinco tarjetas de fuente con su formulario corto. Texto y
  archivo responden al instante con el flash "entraron N, repetidos M". Reddit,
  YouTube y Apify encolan y muestran la barra de progreso con `iniciarPolling`
  (job_id en el `data-job` de la tarjeta). Apify muestra el estimado antes del
  botón (`GET …/recolectar/apify/estimar?actor=&max=` devuelve JSON y el
  formulario lo pinta al cambiar el número). Sin llave: la tarjeta dice qué
  variable falta y el botón va apagado. Debajo: contador por fuente, lista
  paginada de 50 con chip de fuente, texto, link, "excluir"/"incluir";
  "Quitar todos los de X" con confirmación.
- **Avatares**: botón "Generar avatares · ≈ $0.xx · N comentarios" (apagado
  con menos de 20, mientras corre, o si el estudio está archivado). Tarjetas
  por núcleo (nombre, deseo, resumen) con sus sub-avatares: chip de base,
  aviso "sin evidencia" si aplica, chip de estado. Cada sub-avatar se expande
  con sus campos editables (un formulario, `POST …/avatar/<id>/editar`) y sus
  citas con link al original. Botones Aprobar y Descartar; aprobado muestra
  "Persona: <nombre>" con link a Sprints › Personas. "Exportar .md" y
  "Exportar Excel".

Rutas:

| Método y ruta (bajo `/cliente/<cliente>/nicho`) | Hace |
|---|---|
| `POST /estudios` | crear estudio |
| `POST /estudio/<id>/editar`, `POST /estudio/<id>/archivar` | editar, archivar |
| `POST /estudio/<id>/comentarios/texto` | pegar texto |
| `POST /estudio/<id>/comentarios/archivo` | subir CSV/Excel |
| `POST /estudio/<id>/recolectar/<fuente>` | encola `nicho_recolectar` (reddit, youtube, apify) |
| `GET /estudio/<id>/recolectar/apify/estimar` | JSON `{max_resultados, usd}` |
| `POST /comentario/<id>/excluir` | alterna `excluido` |
| `POST /estudio/<id>/comentarios/borrar/<fuente>` | borra una fuente |
| `POST /estudio/<id>/generar` | encola `nicho_generar_avatares` |
| `POST /avatar/<id>/editar`, `/aprobar`, `/descartar` | revisar |
| `GET /estudio/<id>/exportar.md`, `GET /estudio/<id>/exportar.xlsx` | exportar |

El estimado de Claude se calcula en `contexto` (suma de caracteres de los
comentarios no excluidos): no necesita ruta.

## 8. Worker (`tareas/nicho.py`)

Se suma a `tareas.cargar_todas`. Dos tipos:

- `nicho_recolectar`, payload `{cliente, estudio_id, fuente, params}`,
  `job_id = "nicho:<cliente>:<estudio_id>:recolectar:<fuente>"`,
  `duracion_estimada=120`, etapas "Buscando", "Leyendo comentarios",
  "Guardando". `max_intentos=1` para `apify`; el valor por defecto para
  `reddit` y `youtube`, porque la dedup hace seguro el reintento. Al terminar,
  `datos.registrar_recoleccion` deja `{fuente, nuevos, repetidos, aviso,
  fecha}` en `estudio.extra.recolecciones`. Guarda en lotes de 100 por si la
  fuente corta a medias.
- `nicho_generar_avatares`, payload `{cliente, estudio_id}`,
  `job_id = "nicho:<cliente>:<estudio_id>:generar"`, `duracion_estimada=180`,
  etapas "Agrupando deseos", "Armando sub-avatares", "Guardando",
  `max_intentos=1`. Pone el estudio en `generando` al arrancar.

`al_interrumpir` para ambos: el estudio vuelve al estado que le toca por
`recalcular` y el mensaje queda en `extra.ultimo_error`. Ninguna tarea
periódica: nada corre solo. `encolar_recolectar` / `encolar_generar` en el
mismo módulo, como `tareas/sprints.py`.

## 9. Errores y mensajes

| Situación | Qué pasa |
|---|---|
| Falta una llave | Botón apagado; la tarjeta dice la variable que falta |
| `ErrorFuente` | Flash (rutas) o error de la tarea (worker); nunca la llave |
| Reddit 429 persistente / cuota de YouTube | Se guarda lo recogido, la tarea termina bien con aviso en el registro |
| Corrida de Apify fallida o vencida | Tarea en `error` con el estado de la corrida |
| Claude devuelve JSON inválido (pasada 1) | Tarea en `error`, nada guardado, "este intento se cobró" |
| Falla un núcleo en la pasada 2 | Los otros se guardan; ese queda sin subs con el error |
| Citas que no aparecen en el comentario | Se descartan; el sub-avatar queda "sin evidencia" si no le queda ninguna |
| Archivo > 5 MB o > 5 000 filas, sin columna de texto | Flash con la causa, nada guardado |
| Doble clic | `trabajos.encolar` devuelve `False` y la ruta solo redirige |

## 10. Privacidad y términos

- Solo se guardan texto, link, contexto, puntuación y fecha. Nunca el autor.
- Reddit y YouTube por sus APIs oficiales con user agent y llave que
  identifican la app. Apify es responsabilidad del usuario que pone el token:
  la tarjeta lo dice en una línea.
- Los comentarios sirven para entender a la gente; nunca se publican ni se
  copian en piezas. Las citas solo se muestran dentro de la revisión y en las
  exportaciones del propio usuario.

## 11. Pruebas (pytest, sin red)

Fixtures JSON grabadas en `tests/fixtures/nicho/` (respuestas de Reddit,
YouTube y Apify; salidas de Claude buenas y rotas). Claude se sustituye por una
función falsa como en `test_sprints_ideas.py`.

- `test_nicho_fuentes.py`: `normalizar_comentario`, `partir_texto` en los dos
  modos, detección de columnas en CSV y Excel, parsers de Reddit (post +
  comentarios, saltos de deleted/AutoModerator, 429 con reintento y entrega
  parcial) y de YouTube (paginación, comentarios cerrados, cuota), entrada y
  estimado de Apify, links → ids.
- `test_nicho_avatares.py`: `seleccionar` (excluidos fuera, topes, ronda por
  fuente), parseo de las dos pasadas, comentario repetido en dos núcleos,
  `verificar_evidencia`, `estimar_costo` con modelo conocido y desconocido.
- `test_nicho_datos.py`: CRUD, dedup de `agregar_comentarios`, `recalcular`,
  `guardar_generacion` conserva aprobados y sube la generación,
  `aprobar_avatar` crea la persona con el mapeo y re-aprobar la actualiza,
  `descartar_avatar` archiva la persona, bloqueo de `extra`.
- `test_nicho_export.py`: `.md` y `.xlsx` con la plantilla (rótulos y orden).
- `test_rutas_nicho.py`: cliente de Flask, guard por cliente, estimado
  visible, botones apagados sin llaves, job_id que no duplica, flashes.
- `test_tareas_nicho.py`: las dos tareas con fuente falsa y Claude falso,
  guardado por lotes, `al_interrumpir` deja el estudio consistente.
- `test_migracion.py`: `0011` sube y baja.

## 12. Fuera de esta versión

Regenerar un solo sub-avatar; personaje visual desde el avatar; comentarios
de páginas propias de Meta; recolección periódica; gráficas de sentimiento;
detección de idioma por comentario; traducción de las citas.

## 13. Verificar antes de implementar

1. Ids, entrada, salida y precio por resultado de los actores de Apify (§3.5).
2. Precios por millón de tokens del modelo configurado (§4.4).
3. Que `client_credentials` de Reddit sirva para una app tipo *script* en la
   cuenta de Daniel (si no, la app se registra como *web app*).
4. Costo en unidades de `search.list` y `commentThreads.list` de YouTube y la
   cuota diaria por defecto (§3.4), por si cambiaron.
