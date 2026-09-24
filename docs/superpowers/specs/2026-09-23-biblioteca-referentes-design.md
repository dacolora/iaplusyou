# Biblioteca de referentes — diseño

Fecha: 2026-09-23. Estado: aprobado por secciones en conversación; pendiente de
revisión escrita. Un solo spec con seis bloques de entrega (§17), cada uno con
sus pruebas y mezclado a `main` por separado: 1) modelo + importar copycoders +
pestaña Referentes; 2) Recrear con mi producto; 3) puerta desde Sprints; 4)
conector Atria + barrido + clasificación; 5) conector Apify; 6) panel admin
completo. Las tres fuentes entran en esta versión.

## 0. Propósito y relación con lo que existe

Los clientes vieron el "9-Figure Static Swipe File" de copycoders
(`https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/`): 5587 anuncios
estáticos reales de 56 marcas DTC, cada uno clasificado por etapa del funnel,
nivel de consciencia, **familia** de formato (190) y **dolor** de entrada, con
una frase de por qué funciona. Quieren eso dentro de Creatv: **traerse
referentes de forma masiva** y **crear piezas con sus productos** a partir de
ellos, en vez de subir referencias una a una.

Hoy una referencia de Sprints (`referencia`, `sprints/datos.py`) vive dentro de
una campaña, la sube la persona (archivo o link) y Claude la analiza con visión
(`sprints/analisis.py`, pagado) para alimentar el prompt maestro de ideas
(`sprints/ideas.py`). No existe una biblioteca compartida ni una clasificación
por formato.

Lo que este módulo agrega:

- Una **biblioteca de referentes** (tabla `referente`) global de Creatv y con
  barridos propios por proyecto, con una clasificación única (etapa,
  consciencia, familia, dolor, firma) venga de donde venga el anuncio.
- Tres **fuentes**: la importación única del swipe file de copycoders (gratis,
  ya clasificado), **Atria** (API REST por suscripción) y el **Ad Library de
  Meta vía Apify** (por resultado). Las dos últimas son barridos que pide un
  cliente o el admin, con el costo total a la vista antes de confirmar.
- **«Recrear con mi producto»**: de un referente a una imagen (o video) con el
  producto del cliente por el pipeline de Crear que ya existe.
- **Puerta desde Sprints**: las referencias de una campaña se eligen o se
  sugieren desde la biblioteca, ya analizadas y sin volver a pagar visión.

Nada de esto genera ni gasta solo: todo barrido, clasificación y generación
pasa por una puerta con el precio y un clic explícito.

## 1. Decisiones tomadas (2026-09-23)

- **Las tres fuentes a la vez.** copycoders como semilla única (admin, global),
  Atria y Apify como barridos por proyecto y globales.
- **Biblioteca global + barridos por proyecto.** Un referente con
  `cliente=NULL` lo ven todos los proyectos; uno con `cliente=<c>` solo ese
  proyecto. Un barrido de cliente que encuentra un anuncio ya global lo reutiliza
  sin duplicarlo ni reasignarlo.
- **La clasificación Creatv es la taxonomía real.** Los "themes" de Atria son
  ocasionales (48 de 50 anuncios activos no tenían ninguno); se guardan como
  `etiquetas_fuente` pero no organizan la biblioteca.
- **Barrido + clasificación en un solo paso, un solo precio.** El formulario de
  «Traer referentes» muestra el total (fuente + clasificación con Claude) y con
  ese clic todo entra ya clasificado. «Clasificar pendientes» existe solo para
  reparar lo que se interrumpió.
- **Dos puertas de salida:** «Recrear con mi producto» desde la biblioteca y la
  elección/sugerencia de referencias desde una campaña del sprint.
- **Imagen por defecto, video opcional.** El swipe es de estáticos; «Como video»
  manda el mismo formato al pipeline de video de Crear.
- **El camino directo prima.** Recrear genera con un prompt determinista; la
  ayuda con IA («Adaptar con IA», «Sugerir con IA») es opcional y solo propone.

## 2. Las fuentes, tal como son (verificado 2026-09-23)

### 2.1 copycoders

La página es un solo HTML con el dataset embebido: `const DATA=[...]` en el
primer `<script>`, 5587 objetos con estas claves:

```
file, img, brand, headline, aw, stage, family, days, variants, lib, blib,
door, sig, sweep, retired
```

- `aw`: unaware 448 · problem-aware 1947 · solution-aware 934 · product-aware
  1246 · most-aware 1012. `stage`: TOF 2395 · MOF 934 · BOF 2258.
- `family`: 190 valores distintos (los más comunes: Villain Made Visible,
  Before/After Diptych, Benefit Stack Hero, Offer Theater, Blame Transplant…;
  prefijos `EMERGING:` y `NEW:` forman parte del nombre).
- `door`: el dolor de entrada («beer belly», «GLP-1 constipation»,
  «bloating»…) o `none-offer` / `none-brand` cuando el anuncio entra por oferta
  o por marca; 28 vacíos.
- `sig`: una frase en inglés de por qué funciona (2 vacías).
- `lib`: `https://www.facebook.com/ads/library/?id=<anuncio_id>`; `blib`:
  `…view_all_page_id=<pagina_id>` (56 marcas).
- `img`: 3879 en `https://cdn.tryatria.com/adfiles/m<anuncio_id>_….jpeg`, el
  resto rutas relativas (`swipe_assets_0803/<marca>_<hash>.jpg.jpg`) que se
  resuelven contra la URL de la página. `retired` es 0 en todas. `sweep`:
  AUG 3299 · JUL 1708 · FRESH 580.

Las imágenes son anuncios de terceros alojados por Atria o por copycoders:
**siempre se copian a nuestro R2**; la biblioteca nunca muestra una URL ajena.

### 2.2 Atria (REST)

- Base `https://api.tryatria.com/open/v1`, cabecera `X-API-Key: atria-sk_…`
  (llave `ATRIA_API_KEY` en el `.env` raíz; se crea en Atria › Settings & members
  › API Keys y se muestra una sola vez). Sobre `{code, message, data}`;
  `code 0` = ok; errores de negocio con HTTP 200 (`40401` no existe, `42901`
  límite excedido); 401 plano `{error, message, request_id}` sin llave válida.
- **Límite: 20 llamadas por minuto por workspace** (`Ratelimit-Policy:
  "api";q=20;w=60`). Plan Core (US$129/mes): 1200 llamadas REST al mes y 4000
  créditos (1 crédito por llamada que pase del cupo); Plus: ilimitado.
- `GET /ad-library/search`: `query` (texto en titular, cuerpo y marca),
  `language` (ISO 639-1), `display_format` (image|video|carousel|…), `status`
  (active|inactive), `min_days_running`, `min_creative_duplicates`, `brand_id`,
  `order` (newest|most_active|most_impressions|…), `page_size` ≤ 50, `cursor`.
  `data.total` se limita a 10 000. **`main_country` / `target_countries` solo
  saben de la UE** (CO y MX dan 0; ES 10 000+): para LatAm se filtra por
  `language=es` + palabra clave o por marca.
- `GET /brand-library/m<pagina_id>` y `GET /brand-library/m<pagina_id>/ads`
  (mismos filtros que search): **el id de marca de Atria es `m` + id de página
  de Meta**, así que un link del Ad Library basta. `GET /brand-library/search`
  busca por nombre con **`keyword=`** (`query=` es ignorado por la API).
- Cada anuncio trae: `id` (`m<anuncio_id>`), `platform_native_id`
  (= `anuncio_id`), `brand_id`, `brand_name`, `title`, `body`, `caption`,
  `link_url`, `display_format`, `media_format`, `images[{url,width,height}]`,
  `videos[{url,preview_image_url,…}]`, `start_date`, `end_date`,
  `last_seen_date`, `days_running`, `creative_duplicates` (≈ variantes),
  `status`, `language`, `themes` (etiquetas, casi siempre `null`),
  `brand_industries`, métricas de alcance. La búsqueda ya devuelve el anuncio
  completo: no hace falta una segunda llamada por anuncio.
- No hay endpoint REST de etiquetas creativas (`list_library_taggings` /
  `get_library_ad_creative_tags` existen solo en su MCP, que se autentica por
  OAuth en navegador y no sirve para el worker).

### 2.3 Ad Library de Meta vía Apify

- La API oficial de Meta no entrega anuncios comerciales fuera de la UE/UK; el
  camino es un actor de Apify con precio **por resultado** (única clase de
  actor admitida, como en `nicho/fuentes/apify_actores.py`).
- Actor: `apify/facebook-ads-scraper` (oficial), US$5.00 por 1000 anuncios en
  plan Starter (US$5.80 en el gratuito). Entrada: URLs del Ad Library (con
  `view_all_page_id=` para una marca o `q=` para palabra clave, **`country=CO`
  sí funciona**: es la ventaja de Apify para LatAm), estado activo, tope de
  resultados. Salida por anuncio: `adArchiveID`, `pageID`, `pageName`,
  `startDateFormatted`, `endDateFormatted`, `publisherPlatform`, `snapshot`
  (título, cuerpo, imágenes con `original_image_url`, videos, CTA, link),
  `collationCount` (variantes), `isActive`. Los nombres exactos de los campos
  de entrada se verifican contra el esquema del actor al implementar (el
  resumen público no los fija); `armar_entrada` es el único sitio que tocar.
- Llave `APIFY_TOKEN` en el `.env` raíz (hoy no está ni en local ni en el VPS).

## 3. Modelo de datos (migración 0017)

```
referente
  id, creado_en, actualizado_en
  cliente          NULL = global de Creatv | <cliente> = solo ese proyecto
  anuncio_id       id del Ad Library de Meta — UNIQUE (llave común a las tres fuentes)
  pagina_id        id de página de Meta (llave de marca común)
  fuente           copycoders | atria | apify
  marca, url_anuncio (Ad Library), url_marca (librería viva de la marca)
  titular, cuerpo (copy si la fuente lo trae), idioma, pais (NULL si no se sabe)
  tipo             imagen | video | carrusel   (formato de la creatividad)
  imagen_url       copia en R2: referentes/<anuncio_id>.jpg
  imagen_origen    URL original (solo para reintentar)
  estado_imagen    ok | pendiente | error
  dias, variantes, primera_vez, ultima_vez, activo
  etiquetas_fuente JSON  {"themes": [...], "industrias": [...]}  (Atria) | {} (Apify)
  etapa            TOF | MOF | BOF
  consciencia      unaware | problem-aware | solution-aware | product-aware | most-aware
  familia          nombre en referente_familia
  dolor            texto corto | ninguno-oferta | ninguno-marca | NULL
  firma            por qué funciona, ≤ 40 palabras, en español
  clasificacion    fuente | claude | pendiente | error
  barrido_id       FK barrido (NULL en copycoders)
  extra            JSON (firma_original en inglés, sweep, video_url, error…)
  índices: UNIQUE(anuncio_id); (cliente, etapa, consciencia, familia); (barrido_id); (pagina_id)

referente_familia
  id, nombre UNIQUE, descripcion (una línea, español), origen copycoders | claude | admin, creado_en

barrido
  id, creado_en, actualizado_en
  cliente          NULL = global (admin) | <cliente>
  fuente           atria | apify | copycoders
  consulta         JSON {modo: marca|palabra, pagina_id, marca, palabra, idioma, pais, formato,
                         solo_activos, min_dias, min_variantes}
  tope             máximo de anuncios aprobado
  estado           en_cola | trayendo | guardando | clasificando | listo | parcial | error
  traidos, clasificados, pendientes, con_imagen
  usd_estimado, usd_real, llamadas_fuente
  tarea_id, pedido_por (usuario), aviso (texto de entrega parcial), extra
```

- **Un anuncio, una fila.** Si un barrido encuentra un `anuncio_id` que ya
  existe, actualiza `dias`, `variantes`, `ultima_vez`, `activo` y, si estaba
  vacío, `cuerpo`; conserva `cliente` y la clasificación. Un barrido de cliente
  nunca vuelve privado un referente global.
- `referencia` (Sprints): `origen` suma `biblioteca` en `ORIGENES_REFERENCIA`;
  `INTENCIONES` suma `formato` («la estructura del anuncio»). `extra.referente_id`
  enlaza. Sin cambio de esquema: ambas columnas son texto/JSON.
- `gastos.TIPOS` suma `clasificacion`, `adaptar_referente` y `sugerir_ia`;
  `TARIFAS` da `clasificacion` ≈ US$0.006 por anuncio, `adaptar_referente` ≈
  US$0.01 y `sugerir_ia` ≈ US$0.02 por llamada (ver §11).
- Nada más cambia en tablas existentes.

## 4. Conectores de barrido (`referentes/fuentes/`)

Mismo patrón que `nicho/fuentes` y `conectores.por_tipo`: registro perezoso
`referentes.fuentes.por_tipo(tipo)`, un módulo por fuente, contrato común:

```
estimar(consulta, tope) -> {"usd_fuente": float, "llamadas": int, "detalle": str}   gratis
probar()                -> None | ErrorFuente (mensaje para el usuario, sin llave)
traer(consulta, tope, avanzar) -> iterador de páginas; cada anuncio normalizado:
   {anuncio_id, pagina_id, marca, titular, cuerpo, idioma, pais, tipo, imagen_origen,
    dias, variantes, primera_vez, ultima_vez, activo, url_anuncio, url_marca, etiquetas_fuente}
```

`traer` entrega página a página para que la tarea guarde al vuelo; una
excepción a mitad deja lo ya entregado. Un anuncio sin imagen (ni
`preview_image_url`) se descarta y se cuenta en `aviso`.

### 4.1 Atria (`fuentes/atria.py`)

- `consulta.modo="marca"`: `pagina_id` viene de pegar un link del Ad Library
  (`view_all_page_id=`) o de elegir en la búsqueda por nombre
  (`/brand-library/search?keyword=`, lista de hasta 10 con `ad_num` y
  `website_url` para reconocerla). Llama
  `/brand-library/m<pagina_id>/ads?display_format=image&status=active&order=most_active&page_size=50`
  (+ `min_days_running`, `min_creative_duplicates` si se pidieron).
- `consulta.modo="palabra"`: `/ad-library/search?query=<palabra>&language=<idioma>`
  con los mismos filtros. Sin filtro de país (no existe para LatAm).
- Formato: `imagen` por defecto; si se pide `video`, se guarda
  `preview_image_url` como imagen y la URL del video en `extra.video_url`.
- Ritmo: 3.2 s entre llamadas (20/min). Ante `code 42901` espera 60 s y
  reintenta esa página una vez; si vuelve a fallar, corta y entrega parcial.
- `estimar`: `llamadas = ceil(tope / 50)`, `usd_fuente = 0` con detalle
  «N llamadas del plan de Atria». Contador mensual en `kv`
  `atria_llamadas:<AAAA-MM>` (se incrementa por llamada real); Puesta a punto
  muestra «Atria: 240/1200 llamadas este mes» (el cupo es un valor de
  configuración, `ATRIA_LLAMADAS_MES`, por defecto 1200).
- `probar`: `GET /ad-library/search?page_size=1`; 401 → «Atria no aceptó la
  llave (ATRIA_API_KEY)».
- Costura de pruebas: `_pedir(sesion, metodo, url, params)`; las pruebas la
  reemplazan con fixtures de las formas reales (`tests/fixtures/atria_*.json`).

### 4.2 Ad Library vía Apify (`fuentes/apify_adlibrary.py`)

- El runner HTTP de `nicho/fuentes/apify.py` (POST corrida → sondeo → leer
  dataset → contar) se extrae a `providers/apify.py` y lo usan nicho y
  referentes sin duplicarlo. Nicho conserva su `FuenteApify` y sus pruebas.
- Registro de actores en `referentes/fuentes/apify_actores.py` (solo precio por
  resultado): `apify~facebook-ads-scraper`, US$5.00/1000. `armar_entrada`
  construye la URL del Ad Library: marca →
  `…/ads/library/?active_status=active&ad_type=all&country=<pais|ALL>&view_all_page_id=<pagina_id>&media_type=image`;
  palabra → `…&q=<palabra>&country=<pais>&media_type=image`; tope →
  `resultsLimit`. `item` mapea `adArchiveID`→`anuncio_id`, `pageID`→`pagina_id`,
  `pageName`→`marca`, `snapshot.title/body`, primera imagen de
  `snapshot.images[].original_image_url`, `startDateFormatted`→`primera_vez`,
  `collationCount`→`variantes`, `isActive`→`activo`, `dias` = hoy −
  `primera_vez`.
- `estimar`: `usd_fuente = tope × precio` («aprox.», Apify suma cómputo);
  `max_intentos=1` como toda tarea que paga.
- Sin `APIFY_TOKEN` la tarjeta de esa fuente queda apagada en el formulario.

## 5. Clasificación con Claude (`referentes/clasificar.py`)

- Una llamada de visión por anuncio (`generador_prompts.MODEL`): la imagen
  reducida a ≤ 800 px (Pillow, desde la copia en R2/local), titular, cuerpo,
  marca e idioma. El **vocabulario de familias** (nombre + descripción de una
  línea, desde `referente_familia`) va en la parte cacheada del prompt.
- Respuesta JSON obligatoria:

```
{"etapa": "TOF|MOF|BOF",
 "consciencia": "unaware|problem-aware|solution-aware|product-aware|most-aware",
 "familia": "<nombre exacto del vocabulario>" | null,
 "familia_nueva": {"nombre": "...", "descripcion": "..."} | null,
 "dolor": "<texto corto>" | "ninguno-oferta" | "ninguno-marca",
 "firma": "<≤ 40 palabras, español, por qué funciona>"}
```

- Validación (`validar(data, vocabulario)`): valores fuera de las listas →
  `error`; `familia` debe existir en el vocabulario; solo si `familia` es
  `null` se acepta `familia_nueva`, que entra a `referente_familia` con nombre
  `EMERGING: <nombre>` y origen `claude` (si ya existe una con ese nombre se
  reutiliza). `firma` se recorta a 40 palabras. JSON inválido → un reintento de
  parseo con el mismo texto (`_parsear_json` de `sprints/analisis.py`), luego
  `error`.
- Costura de pruebas: `_llamar(content, max_tokens)`.
- Gasto: `TARIFAS["clasificacion"]` = 0.006 por anuncio para el estimado; el
  real se calcula con los tokens que devuelve la API × `PRECIOS_USD_POR_MILLON`
  (los mismos de `nicho/avatares.py`) y se registra por tramo con referencia
  `barrido:<id>:t<tarea_id>:clasificacion:<tramo>`.

## 6. La tarea `referentes_barrer` y la puerta de precio

**Formulario «Traer referentes»** (tres pasos en un mismo panel):

1. **¿De dónde?** Atria · Ad Library (Apify) · (copycoders solo en admin).
   Una fuente sin llave aparece apagada con el motivo.
2. **¿Qué?** modo marca (link del Ad Library o búsqueda por nombre) o palabra
   clave + idioma (+ país solo con Apify), formato (imagen por defecto), solo
   activos, mínimo de días corriendo, mínimo de variantes, y **tope** (máximo
   de anuncios; límite duro 2000 por barrido).
3. **Precio** (se recalcula al cambiar el tope, vía `gastos.estimar`):

```
Traer hasta 500 anuncios de «Lulutox Tea» (Atria · imagen · activos)
  Fuente Atria .............. 10 llamadas del plan
  Clasificar 500 con Claude .. ≈ US$ 3.00
  Total ...................... ≈ US$ 3.00        [Traer y clasificar]
```

Confirmar crea la fila `barrido` y encola `referentes_barrer`
(`max_intentos=1`, `job_id` determinista por barrido, prioridad baja).

**La tarea** (`tareas/referentes.py`), tres etapas con barra de progreso por el
`/trabajo/<job_id>/estado` de siempre:

1. **Trayendo anuncios** — página a página; cada anuncio se guarda al llegar
   (upsert por `anuncio_id`, §3). `barrido.traidos` sube en vivo. Lo traído
   nunca se pierde aunque falle lo que sigue.
2. **Guardando imágenes** — descarga `imagen_origen` (timeout 20 s, ≤ 8 MB),
   verifica con Pillow que es imagen, sube a R2 `referentes/<anuncio_id>.jpg`
   (`r2_uploader.upload_image`), `estado_imagen=ok`. Falla → `error`, se
   cuenta y se sigue.
3. **Clasificando (n/N)** — §5, solo sobre filas `pendiente` con imagen `ok`.

**Tramos**: cada corrida procesa como mucho 100 anuncios de la etapa en curso y
se re-encola a sí misma (patrón del `importador`) hasta terminar, para que las
piezas de Crear (prioridad 5) pasen adelante. El estado del barrido cierra en
`listo` (todo clasificado), `parcial` (quedan pendientes o imágenes en error;
`aviso` lo dice en una frase) o `error` (la fuente falló antes de traer nada).

**«Clasificar pendientes ≈ US$ X»** en la tarjeta del barrido encola
`referentes_clasificar` solo para sus filas `pendiente`/`error` con imagen;
mismo cálculo de precio. Igual para el admin sobre los globales.

## 7. Importación de copycoders (`referentes/copycoders.py`)

- Tarjeta en `/admin/referentes` con la URL prellenada y el botón «Importar»
  (repetible; muestra última importación, traídos, nuevos, actualizados).
- Tarea `referentes_importar_copycoders`: descarga la página, extrae el array
  de `const DATA=` (búsqueda del cierre por profundidad de corchetes,
  `json.loads`), valida las claves de §2.1 y crea/actualiza referentes globales
  con `fuente=copycoders`, `clasificacion=fuente`, `pagina_id` desde `blib`,
  `anuncio_id` desde `lib`, `dolor` normalizado (`none-offer`→`ninguno-oferta`,
  `none-brand`→`ninguno-marca`, vacío→NULL), `extra.sweep`, `extra.firma_original`.
  Las 190 familias entran a `referente_familia` con origen `copycoders` y
  descripción vacía; un paso posterior (una llamada de texto por lote de 40
  familias, con 3 firmas de ejemplo por familia) escribe la descripción en
  español. Imágenes como en §6.2 (las relativas se resuelven contra la URL de la
  página). `firma`: traducción al español en lotes de 100 por llamada de texto
  (≈ US$1 en total, gasto tipo `otro` bajo `_creatv`, detalle «traducción
  copycoders»); si la traducción falla, queda la original y se reintenta en la
  siguiente importación.
- Un cambio de formato de la página → `error` con mensaje claro, sin tocar lo
  ya importado. Costo: ≈ 1 GB en R2, ≈ US$1, 30–40 min por las imágenes.

## 8. Pestaña Referentes (`referentes/rutas.py`, `_tab_referentes.html`)

Blueprint bajo `/cliente/<cliente>/referentes/...`, registrado desde
`dashboard.py` como Sprints y Nicho. La disposición replica la página de
copycoders:

```
REFERENTES                                   [Traer referentes]  [Mis barridos (2)]
[Todos] [Arriba del funnel] [Medio] [Abajo]
[Inconsciente] [Consciente del problema] [De la solución] [Del producto] [Muy consciente]
Marca ▾    Familia ▾ (con conteo)    Dolor ▾    Fuente ▾ (copycoders · Atria · Ad Library · míos)
🔍 buscar en titular, firma o marca                              5 587 referentes
┌──────────┐ ┌──────────┐ ┌──────────┐
│  imagen  │ │  imagen  │ │  imagen  │
│ titular · marca · consciencia · familia · días · variantes · fuente
│ [Recrear con mi producto] [Como video] · Ver en Ad Library
└──────────┘ └──────────┘ └──────────┘
                    [Mostrar más]
```

- Filtros en la URL (`?etapa=TOF&consciencia=&familia=&dolor=&marca=&fuente=&q=&pagina=`);
  60 tarjetas por página; consulta SQL con los índices de §3; imágenes de R2
  con `loading=lazy`. Solo se listan referentes con `estado_imagen=ok`.
- Ámbito: globales + los del proyecto; «Fuente: míos» deja solo los propios.
- Ficha (clic en la imagen): imagen grande, titular, cuerpo, **firma**, dolor,
  familia con descripción, días/variantes, link al Ad Library, botones de
  recrear, «Usar en sprint» (§10) y «Usado N veces» con enlace a la galería
  cuando hay piezas con `extra.referente_id`.
- Etiquetas traducidas en la UI (`most-aware` → «muy consciente», `BOF` →
  «abajo del funnel»); los nombres de familia se quedan en inglés con su
  descripción en español al pasar el mouse.
- «Mis barridos»: lista con estado, «312 traídos · 300 clasificados · 12
  pendientes», costo real y «Clasificar pendientes ≈ US$» si aplica.
- Biblioteca vacía: «Todavía no hay referentes» + botón Traer. Móvil: 2 por
  fila, filtros en un desplegable.
- Selección para Sprints: con `?campana=<id>` cada tarjeta muestra «Agregar» /
  «En la campaña» y una barra fija «N elegidos · Volver al sprint» (§10).

**Admin** (`/admin/referentes`): importar copycoders (§7), barridos globales
(mismo formulario, `cliente=NULL`), totales por fuente, «Atria: N/1200
llamadas este mes», tabla de familias (ver/editar descripción, conteo). En
Puesta a punto: `ATRIA_API_KEY` y `APIFY_TOKEN` con su badge (solo admin).

## 9. «Recrear con mi producto» (`referentes/recrear.py`)

Formulario sobre la tarjeta:

```
Recrear «WE'RE SAYING GOODBYE» (Lulutox · Price Slash Hero) con mi producto
Producto:  [Espejo biselado 60×90 ▾]      (activos del Catálogo con fotos; sin fotos → link a Catálogo)
Formato:   [1:1 ▾]                        (los del modelo; por defecto el más cercano al del referente)
Titular:   [WE'RE SAYING GOODBYE________]  [Adaptar con IA ≈ US$0.01]
Prompt:    (determinista, editable)
                                    [Generar imagen ≈ US$0.06]   [Como video ▸]
```

- `armar_prompt(referente, familia, producto, guia, titular, formato)` es puro
  y con pruebas. Plantilla (español):

```
Anuncio estático para redes, formato {formato}. Sigue la ESTRUCTURA y la
COMPOSICIÓN de Image 1 (referencia de formato «{familia}»: {descripcion_familia}).
Funciona porque: {firma}. Dolor que ataca: {dolor}.
Producto: el de Image 2{ y 3}: {nombre}. {descripcion}. {regla de fidelidad}.
Sustituye por completo el producto y la marca de la referencia.
Texto en la imagen: titular «{titular}» con el mismo peso y ubicación que en la
referencia; ningún otro texto.
Guía de estilo de la marca: {guia}.
Sin logos ni nombres de otras marcas. Sin marcas de agua.
```

  Referencias de imagen: el referente como `Image 1` y hasta 2 fotos del
  producto (`catalogo_productos`), dentro del límite de referencias del modelo
  (`flowplus_modelos.IMAGEN[...]`); `flowplus_prompt.asignar_tokens` nombra las
  imágenes como siempre.
- **«Adaptar con IA»** (tarea `referentes_adaptar`, una llamada de texto):
  recibe familia, firma, dolor, titular original, producto (nombre, descripción,
  regla) y guía; devuelve `{titular, prompt}` en español adaptados al producto.
  El resultado se guarda en `kv` bajo el `job_id` y el formulario lo recoge por
  polling y lo pone en los campos para editar. No genera nada. Gasto
  `adaptar_referente`.
- **Generar imagen**: `creative_flow.crear(cliente, tipo="imagen",
  productos_ids=[producto], prompt=<prompt>, aspect_ratio=<formato>,
  extra={"referente_id": id, "origen": "referente"})` →
  `flowplus_lanzar.lanzar(prioridad=5)` → `flowplus_imagen` (Seedream V5 Pro,
  `estimate_imagen` en el botón, gasto `imagen`, R2). El plan confirma la firma
  exacta de `crear` (hoy recibe `personajes_ids, productos_ids, escenas_ids,
  accion_central, …`; si hace falta un gancho para el prompt ya armado y el
  `extra`, se agrega como `extra_sprint=`). La pieza aparece en Crear con
  Aprobar/Rechazar y entra a Experimentos y orgánico por los caminos que ya
  existen. **Cero cambios en los workers de generación.**
- **«Como video»**: mismo formulario con las opciones de video de Crear (modelo
  por defecto `VIDEO_POR_DEFECTO`, 8 s, `con_sonido` según
  `preferencias_sonido`, formatos del modelo, `estimate_video` en el botón). El
  prompt añade «Cámara fija con leve acercamiento al producto; el titular
  aparece en los primeros 2 segundos» y la línea `SONIDO:` de siempre. Quien
  quiera más lo pasa por el director de Crear (`modo_prompt=director`). Lanza
  por `_lanzar_video_cf`.
- Texto en la imagen: lo renderiza el modelo en esta versión; «Regenerar» cuesta
  lo mismo. Superponer texto con Pillow queda fuera (§16).
- `pieza.extra.referente_id` alimenta «Usado N veces» y deja el dato para medir
  familias ganadoras en Experimentos más adelante.

## 10. Puerta desde Sprints

- `referencia` con `origen="biblioteca"` se llena sola desde el referente:
  `url`/`frame_url` = `imagen_url`, `titulo` = titular, `descripcion` = firma
  (→ `estado=lista`, cuenta para `referencias_objetivo`), `intencion=["formato"]`,
  `analisis = {"familia", "descripcion_familia", "etapa", "consciencia", "dolor",
  "firma", "resumen": firma}`, `analisis_estado="listo"`, `extra.referente_id`.
  **No se encola `sprint_analizar_referencia`.** Un referente no entra dos veces
  a la misma campaña (se comprueba en `agregar_referencia_biblioteca`). Quitarla
  borra solo la fila `referencia`.
- **«Elegir de la biblioteca»** en la tarjeta de la campaña abre la pestaña
  Referentes con `?etapa=<funnel de la campaña en mayúsculas>&campana=<id>` en
  modo selección (§8); `POST /cliente/<c>/sprints/campana/<id>/referencias_biblioteca`
  con los ids crea las filas y vuelve al sprint.
- **«Sugerir de la biblioteca» (gratis)** (`referentes/sugerir.py`, puro):
  candidatos visibles con `etapa` = funnel de la campaña, `estado_imagen=ok`,
  `clasificacion in (fuente, claude)` y no en la campaña; puntaje
  `variantes × max(dias, 1)`; se toman en orden **una familia distinta por
  sugerencia** hasta `referencias_objetivo − existentes` (mínimo 1). Se muestran
  como propuestas con «Agregar» cada una y «Agregar todas»; nada entra sin
  confirmar.
- **«Sugerir con IA ≈ US$0.02»** (tarea `referentes_sugerir_ia`): manda los 60
  mejores candidatos como texto (id, familia, dolor, firma, días, variantes)
  con la persona, el producto y la temporada de la campaña; Claude devuelve N
  ids con una razón de una línea (`extra.razon`); se validan contra los
  candidatos. Solo texto, sin visión. Misma pantalla de propuestas.
- **«Usar en sprint»** en la ficha del referente: elige una campaña de un
  sprint en `planeando`/`referencias` y llama al mismo endpoint.
- `sprints/ideas.py::_referencias_texto` describe una referencia de biblioteca
  con «Formato: {familia} — {descripcion_familia}; funciona porque: {firma};
  dolor: {dolor}; etapa: {etapa}» en lugar de paleta/iluminación.
- `sprints/produccion.py`: cuando una idea cita una referencia de biblioteca,
  la sesión de Crear recibe su imagen como referencia de formato (fotos del
  producto primero, el referente después, dentro del límite del modelo) y
  `extra.referente_id`. Costo del lote, `prioridad=3`, QA, revisión, entrega y
  `sprints/estado.py::recalcular` no cambian.

## 11. Gasto, permisos y llaves

- Tarifas nuevas en `gastos.TARIFAS`: `clasificacion` 0.006 por anuncio (la
  UI dice «≈»), `adaptar_referente` 0.01, `sugerir_ia` 0.02. `gastos.estimar`
  suma fuente + clasificación para el formulario de barrido. Todo gasto real
  pasa por `registrar_seguro` con referencia que incluye el id de la tarea;
  los barridos globales y la importación registran bajo el proyecto reservado
  `_creatv` (solo visible en el panel admin).
- Permisos: pestaña, «Traer referentes», «Recrear» y la puerta de Sprints para
  cualquier usuario del proyecto. Importar copycoders, barridos globales y
  familias: solo admin. Un proyecto nunca ve barridos de otro (toda consulta
  filtra `cliente IS NULL OR cliente = :c`).
- Llaves en el `.env` raíz: `ATRIA_API_KEY`, `APIFY_TOKEN`; opcional
  `ATRIA_LLAMADAS_MES` (1200). Aparecen en Puesta a punto (solo admin) y nunca
  en mensajes, eventos ni logs (`cola.sin_token`).

## 12. Errores

- Fuente sin llave → tarjeta apagada; llave inválida → `probar` lo dice con el
  nombre de la variable.
- Atria `42901` → espera y un reintento por página; si persiste, entrega
  parcial con `aviso`. Cupo mensual agotado → `error` con mensaje «Atria: se
  acabaron las llamadas del plan este mes».
- Apify 400 → el mensaje de Apify al usuario (sin token); corrida terminal sin
  ítems → `error`; ítems sin imagen → descartados y contados.
- Imagen que no descarga → `estado_imagen=error`, no se lista, se repara desde
  la tarjeta del barrido («Reintentar imágenes», gratis).
- Clasificación: JSON inválido o valores fuera de lista → `error` por anuncio,
  se sigue; «Clasificar pendientes» los incluye.
- Recrear: sin productos con fotos → el botón lleva a Catálogo; referente sin
  imagen → botón desactivado. Lo demás son los errores de Crear.
- Copycoders con formato distinto → `error` sin tocar lo importado.
- Worker interrumpido → lo guardado queda; el barrido muestra `parcial`.

## 13. Pruebas (`tests/test_referentes_*.py`, sin red)

- Parseo del HTML de copycoders (fixture con 3 filas y una relativa) y
  normalización de `door`/`aw`/`stage`.
- Normalizadores de Atria y Apify con fixtures de las formas reales
  (`tests/fixtures/atria_search.json`, `atria_brand_ads.json`,
  `apify_adlibrary_item.json`).
- `armar_entrada` de Apify (URL por marca y por palabra, tope) y `estimar` de
  las dos fuentes.
- Espaciado del límite de Atria y el reintento ante `42901` (tiempo simulado).
- `validar` de clasificación: familia del vocabulario, `familia_nueva` →
  `EMERGING`, valores inválidos → error, recorte de firma.
- Upsert por `anuncio_id`: un barrido de cliente sobre un global no duplica ni
  reasigna; actualiza días/variantes.
- `armar_prompt` de recrear (con y sin segunda foto, regla de fidelidad, guía).
- Sugerencia determinista: una familia por sugerencia, orden por puntaje,
  excluye los ya en la campaña, respeta `referencias_objetivo`.
- `referencia` desde referente: queda `lista`, `analisis_estado=listo` y **no**
  encola análisis; no entra dos veces.
- `_referencias_texto` con referencias de biblioteca.
- Rutas con el test client: la pestaña lista solo globales + propios, el modo
  selección, el formulario de precio recalcula, 403 para un cliente en
  `/admin/referentes`.
- La tarea de barrido con fuente falsa: guarda al vuelo, cierra `parcial` si
  falla la clasificación, re-encola por tramos.

## 14. Despliegue (VPS)

`alembic upgrade head` (0017); reiniciar gunicorn y `creatv-worker`; agregar
`ATRIA_API_KEY` (y `APIFY_TOKEN` cuando exista cuenta) al `.env` del servidor;
en `/admin/referentes` pulsar «Importar» (≈ 1 GB en R2, ≈ US$1, 30–40 min);
primer barrido de prueba con tope 50 antes de soltárselo a un cliente. Rotar
la llave de Atria que se compartió en el chat del diseño una vez todo funcione.

## 15. Riesgos

- El dataset de copycoders es HTML público, pero es su curaduría; se usa como
  semilla única y las imágenes son anuncios de terceros que solo prestan la
  estructura: siempre se enlaza al Ad Library y el prompt de recrear prohíbe
  logos y marcas ajenas. Con el tiempo los barridos propios son la fuente
  principal.
- Atria puede cambiar la API o el cupo; el conector es un módulo y el
  contador mensual avisa antes de agotar. Apify puede cambiar el actor;
  `armar_entrada` es el único sitio que tocar.
- Un barrido grande son horas de Claude en el worker único: los tramos de 100
  y la prioridad baja evitan que frene a Crear, y el tope de 2000 acota el
  gasto por clic.
- El texto que renderiza el modelo en la imagen puede salir mal: se regenera;
  la superposición con Pillow es la mejora prevista.

## 16. Fuera de esta versión

Favoritos/tableros por proyecto; seguimiento de marcas con avisos; barridos
automáticos periódicos; referentes de video como video (solo el fotograma);
texto superpuesto con Pillow; etiquetas creativas de Atria (solo por MCP);
anuncios de TikTok (la llave común es el id de Meta); reporte «qué familias
ganan» en Experimentos; crear campañas automáticamente desde la biblioteca.

## 17. Orden de entrega

1. Migración 0017, `referentes/` (datos, familias), importación de copycoders,
   pestaña Referentes de solo lectura + ficha.
2. «Recrear con mi producto» (imagen y video) + «Adaptar con IA».
3. Puerta desde Sprints (elegir, sugerir, sugerir con IA, ideas y lote).
4. Conector Atria + formulario «Traer referentes» + `referentes_barrer` +
   clasificación + «Clasificar pendientes» + «Mis barridos».
5. Conector Apify (`providers/apify.py` compartido con nicho).
6. Panel admin completo (barridos globales, familias, contador de Atria) y
   Puesta a punto.

Cada bloque llega a `main` con sus pruebas y es útil por sí solo.
