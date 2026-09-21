# Nicho, Parte 3: investigación automática del nicho (buscadores de marketplaces y redes)

Fecha: 2026-09-21. Estado: diseño aprobado por secciones con Daniel.
Continúa `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (Partes 1 y 2, en main).

## 0. Propósito y relación con lo que existe

Hoy un estudio de Nicho recibe comentarios de cuatro maneras: texto pegado, CSV,
Reddit/YouTube por palabras clave y Apify por link de producto (Amazon, TikTok). Todo
es manual: alguien pega, sube o busca links.

La Parte 3 convierte el estudio en una investigación automática: la persona escribe el
tema del nicho, aprueba UNA cifra y el sistema busca productos en los marketplaces del
país, decide cuáles son del nicho, trae sus reseñas de compradores, suma lo que digan
Reddit y YouTube, y genera los avatares. Nadie marca productos ni pega links. Lo único
que no desaparece es el clic que muestra el costo antes de gastar, porque esa regla
sostiene todo el producto (CLAUDE.md: nada gasta sin aprobación explícita).

Principios heredados que siguen valiendo: `nicho/datos.py` es el único escritor de las
tablas de Nicho; Apify es la integración con marketplaces (un token nuestro, actores con
precio por resultado, token solo en cabecera, techo de cobro por corrida, gasto
registrado aunque la corrida falle); `cola.sin_token` en todo error; nunca se guarda el
autor de una reseña; nunca se le pide nada al cliente (ni accesos, ni tiendas).

## 1. La cadena

Una investigación es una cadena de tareas del worker. Cada tarea termina llamando a
`nicho.investigacion.avanzar(cliente, estudio_id)`, que lee el estado, decide el
siguiente paso y lo encola con un `job_id` determinista. `avanzar` es idempotente: si la
tarea del siguiente paso ya está viva, no hace nada. Así ninguna tarea dura más que su
paso, el worker de un solo hilo no queda bloqueado 30 minutos seguidos, y una caída a
mitad se reanuda desde el paso pendiente sin volver a pagar lo hecho.

Pasos, en orden:

| Paso | Tarea del worker | Qué hace | Paga |
|---|---|---|---|
| `consultas` | `nicho_inv_consultas` | Claude convierte `tema` (+ `producto` opcional) en 2–4 búsquedas en el idioma del país | centavos (Claude) |
| `buscar:<plataforma>` (una por plataforma, en serie) | `nicho_inv_buscar` | El actor de búsqueda de la plataforma trae hasta `productos_por_consulta` productos por consulta; se guardan en `producto_nicho` | centavos (Apify) |
| `seleccionar` | `nicho_inv_seleccionar` | Claude marca cuáles productos son del nicho y por qué; de los relevantes quedan los `productos_elegidos` con más reseñas por plataforma | centavos (Claude) |
| `resenas:<plataforma>` (una por plataforma, en serie) | `nicho_recolectar` (la de la Parte 2, con `fuente` = la plataforma y `investigacion: true`) | El actor de reseñas trae hasta `resenas_por_producto` por producto elegido | el gasto real (Apify) |
| `redes:<fuente>` (`reddit`, `youtube`, si hay llave) | `nicho_recolectar` con las consultas como palabras clave | Lo que ya hacen esas fuentes | gratis |
| `generar` | `nicho_generar_avatares` (la de la Parte 1, con `auto: true` y el tope restante) | Núcleos y sub-avatares | Claude |

`job_id` por paso: `nicho:<cliente>:<estudio_id>:inv:<paso>` para consultas, buscar y
seleccionar (`inv:buscar:amazon`); las recolecciones conservan el de la Parte 2
(`nicho:<cliente>:<estudio_id>:recolectar:<fuente>`) y la generación el suyo. Un doble
clic no lanza nada dos veces (`trabajos.encolar` rechaza un job vivo).

Colas y reintentos: `consultas` y `seleccionar` con `max_intentos=2` (Claude, centavos,
idempotentes); `buscar` y `resenas` con `max_intentos=1` (Apify, de pago); `redes` como
en la Parte 2. `duracion_estimada`: 60 s los de Claude, 300 s los de Apify.

Estados de la investigación (`extra.investigacion.estado`): `consultas → buscando →
seleccionando → resenas → redes → generando → lista`, más `detenida` (la cadena paró
con motivo: sin productos relevantes, menos de 20 comentarios, el costo real de los
avatares supera lo aprobado, Claude falló dos veces, cancelada por la persona) e
`interrumpida` (el worker se reinició a mitad de un paso). `detenida` e `interrumpida`
muestran "Reanudar".

El estado del estudio (`estudio.estado`, `datos.recalcular`) no cambia de significado:
`generando` mientras vive la tarea de generación, `revisando` con avatares, `armando` si
no. La investigación es una capa aparte en `extra`.

## 2. Modelo de datos

Migración nueva (siguiente número libre al ejecutar; hoy main va en 0013 y otros planes
abiertos reservan 0014).

### 2.1 `estudio.pais`

Columna `pais String(2)` nullable. Al crear un estudio se toma del proyecto
(`proyectos.pais`) y se puede cambiar en el estudio. Decide el dominio de Amazon, el
sitio de Mercado Libre y el idioma de las consultas.

### 2.2 Tabla `producto_nicho`

| Columna | Tipo | Nota |
|---|---|---|
| `id` | Integer PK | |
| `cliente` | String(80) | |
| `estudio_id` | FK `estudio.id`, index | |
| `plataforma` | String(12) | `amazon`, `meli`, `tiktok_shop`, … (clave del registro) |
| `fuente_id` | String(120) | ASIN, id de MELI, id de TikTok Shop |
| `consulta` | String(200) | la búsqueda que lo encontró |
| `titulo` | String(300) | |
| `marca` | String(120) | |
| `precio` | Float | |
| `moneda` | String(3) | |
| `estrellas` | Float | |
| `n_resenas` | Integer | reseñas que la plataforma dice tener |
| `url` | String(500) | |
| `imagen` | String(500) | |
| `relevante` | Boolean nullable | NULL = Claude no lo ha juzgado |
| `motivo` | String(300) | por qué sí o por qué no |
| `resenas_traidas` | Integer default 0 | cuántas reseñas suyas se guardaron |
| `extra` | JSON | crudo útil del actor (`soldCount`, `isSponsored`, …) |
| `creado_en`, `actualizado_en` | String(19) | |

`UNIQUE (estudio_id, plataforma, fuente_id)`: una búsqueda repetida hace upsert
(actualiza precio, estrellas, `n_resenas`) y no duplica. Los productos con
`resenas_traidas > 0` no vuelven a pedirse.

### 2.3 Comentarios de las plataformas

Van a `comentario` con `fuente` = la clave de la plataforma (`amazon`, `meli`,
`tiktok_shop`; `String(12)` alcanza), `fuente_id` = id de la reseña en la plataforma
(o `hash_texto` si no trae id), `contexto` = título del producto, `puntuacion` =
estrellas, `url` = la de la reseña o la del producto, `extra = {"producto":
<fuente_id del producto>, "plataforma": <clave>}`. Nunca el nombre del autor. La
unicidad `uq_comentario_fuente` (estudio + fuente + fuente_id) sigue haciendo la dedup.

### 2.4 `estudio.extra.investigacion`

```json
{
  "version": 1,
  "estado": "resenas",
  "iniciada_en": "2026-09-21T10:00:00", "terminada_en": null,
  "pais": "SE", "idioma_consultas": "sv",
  "plataformas": ["amazon", "meli", "tiktok_shop"], "redes": ["reddit", "youtube"],
  "topes": {"consultas": 3, "productos_por_consulta": 20, "productos_elegidos": 15, "resenas_por_producto": 100},
  "estimado": {"por_plataforma": {"amazon": {"busqueda_usd": 0.18, "resenas_usd": 1.35}}, "claude_usd": 0.05, "avatares_usd": 1.20, "total_usd": 11.40},
  "aprobado_usd": 11.40, "gastado_usd": 2.31,
  "consultas": ["tofflor mot fotsmärta", "mjuka tofflor plantar fasciit", "ortopediska tofflor"],
  "pasos": {
    "consultas": {"estado": "hecho", "usd": 0.01},
    "buscar:amazon": {"estado": "hecho", "productos": 57, "usd": 0.17, "aviso": ""},
    "seleccionar": {"estado": "hecho", "relevantes": 31, "usd": 0.03},
    "resenas:amazon": {"estado": "en_curso", "resenas": 0, "usd": 0.0},
    "redes:reddit": {"estado": "pendiente"},
    "generar": {"estado": "pendiente"}
  },
  "detenida_por": null, "ultimo_error": null
}
```

Escritores: las tareas de la cadena y las rutas (iniciar, reanudar, cancelar), siempre
por `datos.actualizar_investigacion(cliente, estudio_id, fn)`, que toma el candado de
escritura ANTES de leer (`BEGIN IMMEDIATE` vía el no-op UPDATE de
`experimentos._bloquear`), porque Flask y el worker escriben el mismo JSON. La lógica
de estados (`siguiente_paso`, `marcar`, `puede_reanudar`, `resumen`) son funciones
puras sobre ese diccionario en `nicho/investigacion.py`.

## 3. Registro de plataformas (`nicho/fuentes/plataformas.py`)

Una entrada por plataforma, solo datos y funciones puras:

```python
PLATAFORMAS = {
  "amazon": {
    "nombre": "Amazon",
    "paises": {"US": "com", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it", "ES": "es", "NL": "nl",
               "SE": "se", "CA": "ca", "MX": "com.mx", "BR": "com.br", "AU": "com.au", "IN": "in", "JP": "co.jp", "AE": "ae"},
    "busqueda": {"actor": "junglee~amazon-crawler", "usd_por_resultado": 0.003, "modelo": "ppe",
                 "armar_entrada": _busqueda_amazon, "leer_producto": _producto_amazon},
    "resenas":  {"actor": "axesso_data~amazon-reviews-scraper", "usd_por_resultado": 0.0009, "modelo": "ppe",
                 "por_producto": True, "armar_entrada": _resenas_amazon, "leer_resena": _resena_amazon},
  },
  "meli": {...}, "tiktok_shop": {...},
}
IDIOMA_POR_PAIS = {"SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es", "PE": "es",
                   "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en", "BR": "pt", "DE": "de",
                   "FR": "fr", "IT": "it", "NL": "nl", "JP": "ja", "AE": "en"}
```

Funciones del módulo: `disponibles(pais)` (plataformas que cubren ese país; `"*"`
cubre todos), `dominio(clave, pais)`, `idioma(pais)` (sin entrada → `"en"`),
`estimar_busqueda(clave, consultas, productos_por_consulta)`,
`estimar_resenas(clave, productos, resenas_por_producto)` (ambas `ceil(round(n × precio ×
100, 6)) / 100`), `entradas_busqueda(clave, consultas, pais, max)` → lista de entradas
(una corrida por entrada), `leer_producto(clave, item)` → producto normalizado o None,
`entradas_resenas(clave, productos, max_por_producto)` → lista de entradas,
`leer_resena(clave, item)` → dict para `normalizar_comentario` o None.

Producto normalizado: `{fuente_id, titulo, marca, precio, moneda, estrellas, n_resenas,
url, imagen, extra}`; sin `fuente_id` o sin `titulo` se descarta.

### 3.1 Entradas iniciales (hechos del inventario del 2026-09-20; ver §12)

**Amazon.** Búsqueda con `junglee~amazon-crawler` (el más usado de la tienda, 23 k
usuarios, US$ 3 por 1 000 resultados): no acepta palabras sueltas, así que la entrada es
`{"categoryOrProductUrls": [{"url": "https://www.amazon.<dominio>/s?k=<consulta
codificada>"}], "maxItemsPerStartUrl": productos_por_consulta,
"maxSearchPagesPerStartUrl": 2, "proxyCountry": <país>}`, una corrida con las 2–4 URLs.
Producto: `asin`, `title`, `brand`, `price` (valor y moneda), `stars`, `reviewsCount`,
`url`, imagen. Reseñas con `axesso_data~amazon-reviews-scraper` (US$ 0,90 por 1 000, 15
marketplaces incluidos SE, ES, MX, BR): recibe UN `asin` + `domainCode` + `maxPages`
(10 reseñas por página, máximo 10 páginas = 100 reseñas), así que son varias corridas
por paso (§4, corridas en lote). Reseña: `reviewId`, `text`, `rating`, `date`,
`verified`; `userName` se descarta. `junglee~amazon-reviews-scraper` (el de la Parte 2)
queda para la tarjeta por link; solo documenta amazon.com.

**Mercado Libre.** Búsqueda con `karamelo~mercado-libre-listings-scraper` (US$ 2 por
1 000, 18 países): recibe UN `keyword` y `country` como URL del sitio
(`https://listado.mercadolibre.com.co/`, `.com.mx`, `.com.ar`, `.cl`, `.com.pe`,
`https://lista.mercadolivre.com.br/` …), `maxPages: 1`, `extractProductDetails:
false`; una corrida por consulta (lote). Reseñas con
`karamelo~mercadolibre-review-scraper` (US$ 0,70 por 1 000): `{"productUrls": [...],
"maxReviewsPerProduct": n}`, una corrida. Reseña: `reviewId`, `reviewText`,
`reviewRating`, `reviewDate`, `productId`; `reviewerName` se descarta.

**TikTok Shop.** Un solo actor, `unseenuser~tiktok-shop-scraper` (US$ 4,50 por 1 000,
2 k usuarios, 5,0/5): búsqueda `{"mode": "shop_search", "searchKeywords": [...],
"maxResults": n}`; reseñas `{"mode": "product_reviews", "productUrls": [...],
"maxReviewsPerProduct": n}`. Producto: `productId`, `title`, `price`, `rating`,
`soldCount`; reseña: `reviewId`, `text`, `rating`, `postedAt`, `verifiedPurchase`. Sin
lista de países visible: `paises: "*"`.

Los nombres exactos de campos de salida se confirman con la corrida de centavos (§10)
antes de congelar los fixtures; el registro es el único sitio que cambia si difieren.

### 3.2 Redes dentro de la cadena

`reddit` recibe `palabras_clave = " OR ".join(consultas)`, `subreddits = []`,
`max_posts = 25`, `max_comentarios_por_post = 50`; `youtube` recibe `palabras_clave =
" | ".join(consultas)`, `idioma = idioma(pais)`, `region = pais`, `max_videos = 10`,
`max_comentarios_por_video = 100`. Solo si sus llaves están (`fuentes.llaves_faltantes`);
si no, el paso se anota "sin llave" y se salta. La tarjeta "Comentarios de TikTok" por
link no entra: necesita links de videos (buscador de TikTok: Parte 4).

## 4. La fuente genérica y las corridas en lote

`nicho/fuentes/plataforma.py::FuentePlataforma(clave)`: `tipo = clave`, `de_pago =
True`, llaves `("APIFY_TOKEN",)`, y dos generadores:

- `buscar(consultas, pais, productos_por_consulta, avanzar)` → productos normalizados.
- `recolectar(params, avanzar)` con `params = {"productos": [{fuente_id, url, titulo}],
  "resenas_por_producto": n, "pais": "SE"}` → comentarios normalizados (contrato de
  `Fuente` de la Parte 2, así `nicho_recolectar` la usa sin cambios).

Las dos apoyan en `nicho/fuentes/apify.py`, del que se extrae `correr_lote(sesion, token,
actor, entradas, max_items, max_usd, avanzar, max_simultaneas=5)`: arranca hasta 5
corridas a la vez con `params={"timeout": 1200, "maxItems": …, "maxTotalChargeUsd": …}`
por corrida, sondea todas cada 10 s con la tolerancia a fallos de la Parte 2, lee el
dataset de cada una en cualquier estado terminal, y devuelve `{"items": [...],
"resultados": n_crudos, "corridas": [{run_id, dataset_id, estado, resultados}],
"aviso": ""}`. `FuenteApify` (Parte 2) pasa a usar el mismo `correr_lote` con una sola
entrada; su comportamiento y sus pruebas no cambian. `resultados` y `run_id` quedan como
atributos de la fuente para `_gasto_recoleccion` y `registrar_recoleccion` (Parte 2), que
ahora anotan la lista de corridas en `extra["corridas"]`.

Una plataforma con `resenas.por_producto` (Amazon) genera una entrada por producto
elegido; las demás una entrada con todos los productos. `max_usd` de cada corrida es su
parte proporcional del estimado del paso.

## 5. Claude: consultas y selección (`nicho/investigacion.py`)

Modelo `generador_prompts.MODEL`. Ambas llamadas usan `max_tokens` chico (800) y
`response` JSON validado; si el JSON no parsea se reintenta una vez dentro de la misma
tarea; si vuelve a fallar, la tarea falla y con `max_intentos=2` la investigación queda
`detenida` ("Claude no pudo …"), reanudable.

**Consultas.** Entrada: `tema`, `producto` (si hay), `pais`, `idioma(pais)`. Salida:
`{"consultas": ["...", "..."]}`, de 2 a 4, cada una de 2 a 6 palabras en ese idioma,
como las escribiría un comprador en el buscador de la tienda; sin marcas propias del
cliente (para ver competencia, no a uno mismo). Se guardan en
`extra.investigacion.consultas`.

**Selección.** Entrada: `tema`, `producto`, `pais` y la lista de productos encontrados
(por plataforma: `id`, `titulo`, `marca`, `precio` + `moneda`, `estrellas`,
`n_resenas`; máximo `plataformas × consultas × productos_por_consulta`, tope duro 300
filas; si hay más, se conservan primero los de más reseñas). Salida:
`{"productos": [{"id": …, "relevante": true, "motivo": "..."}]}`. Reglas mecánicas
después de Claude: por plataforma se eligen los `productos_elegidos` relevantes con más
`n_resenas` (empate: estrellas); los productos sin `n_resenas` cuentan como 0 y solo se
eligen si sobra cupo. Todo se persiste en `producto_nicho.relevante/motivo`. Si ninguna
plataforma tiene relevantes → `detenida` ("no se encontraron productos del nicho").

Costos: consultas ≈ 1 500 tokens de entrada y 100 de salida; selección ≈ 80 tokens por
producto de entrada y 25 de salida, más 600 de instrucciones. Se estiman con
`PRECIOS_USD_POR_MILLON` de `nicho/avatares.py` y se registran en `gastos` como tipo
nuevo `investigacion` con referencias `investigacion:<eid>:consultas:t<id>` e
`investigacion:<eid>:seleccion:t<id>`.

## 6. Estimado, tope y gasto

`investigacion.estimar(estudio, pais, plataformas, redes, topes)` devuelve el desglose
que se muestra y que se guarda en `extra.investigacion.estimado`:

- Por plataforma: `busqueda_usd = estimar_busqueda(clave, topes.consultas,
  productos_por_consulta)`; `resenas_usd = estimar_resenas(clave, productos_elegidos,
  resenas_por_producto)`.
- `claude_usd` = consultas + selección (§5) con `productos = plataformas × consultas ×
  productos_por_consulta`.
- `avatares_usd` = `avatares.estimar_costo` sobre el peor caso (`MAX_COMENTARIOS` = 600
  comentarios de 250 caracteres): `avatares.estimar_costo_maximo()`.
- `total_usd` = suma, redondeada hacia arriba al centavo. Es la cifra del botón y
  `aprobado_usd` al hacer clic.

Topes por defecto: consultas 3, productos por consulta 20, productos elegidos 15, reseñas
por producto 100. Límites duros: 1–4, 5–40, 3–30, 20–200. Con Amazon + Mercado Libre +
TikTok Shop el peor caso es ≈ US$ 11 (TikTok Shop pesa US$ 7). Reddit y YouTube: US$ 0.

Techos duros: cada corrida recibe `maxTotalChargeUsd` (su parte del paso) y `maxItems`
(`consultas × productos_por_consulta` en búsqueda, `productos × resenas_por_producto` en
reseñas). La generación de avatares recibe `tope_usd = aprobado_usd − gastado_usd`; si su
estimado real (`avatares.estimar_costo` con los comentarios de verdad) lo supera, no
corre: `detenida` ("los avatares costarían US$ X y quedan US$ Y aprobados") y el botón
"Generar avatares" de la Parte 1 muestra la cifra real.

Gasto real: cada paso registra lo suyo con `gastos.registrar_seguro` (búsquedas y
reseñas como `recoleccion` con `detalle` "búsqueda Amazon: 57 productos" / "reseñas
Amazon: 1 213 resultados aprox.", Claude como `investigacion`, avatares como
`avatares`), y suma el mismo valor a `extra.investigacion.gastado_usd` y a
`pasos[<paso>].usd`. Un paso que falla después de arrancar corridas registra lo cobrado
igual (Parte 2). `gastos.TIPOS` gana `investigacion`.

## 7. Fallos, reanudación, cancelación

- **Una plataforma falla o no encuentra nada** (actor con error, 0 productos, 0
  relevantes, token rechazado): su paso queda `error` o `vacio` con `aviso`, y `avanzar`
  sigue con la siguiente plataforma. Al llegar a `generar`, si
  `datos.comentarios_para_generar` trae menos de `avatares.MIN_COMENTARIOS` (20) →
  `detenida` ("solo hay N comentarios; hacen falta 20").
- **Claude falla dos veces** en consultas o selección → `detenida` con el error
  (`cola.sin_token`).
- **El worker se reinicia** → `al_interrumpir` de cada tarea marca su paso `pendiente`
  y el estado `interrumpida`.
- **Reanudar** (`POST .../investigar/reanudar`): valida que el estado sea `detenida` o
  `interrumpida`, pone `estado` según el primer paso pendiente y llama `avanzar`. Nada
  hecho se repite: consultas guardadas se reutilizan, `buscar:<p>` hecho se salta,
  `seleccionar` solo juzga productos con `relevante IS NULL`, `resenas:<p>` solo pide
  productos elegidos con `resenas_traidas == 0`. Si la parada fue por el tope de
  avatares, Reanudar no aplica: se usa el botón de generar con su costo.
- **Cancelar** (`POST .../investigar/cancelar`): `estado = detenida`, `detenida_por =
  "cancelada"`. `avanzar` no encola nada más; la tarea viva termina su paso (una corrida
  de Apify ya arrancada se cobra igual y su resultado se guarda).
- **Investigar de nuevo** con una investigación `lista` o `detenida`: nuevo
  `extra.investigacion` (el anterior se guarda en `extra.investigaciones_previas`, últimas
  3), mismas reglas de no repetir pago sobre `producto_nicho`.
- **Estudio archivado**: no se puede investigar ni reanudar; una cadena viva termina su
  paso y `avanzar` se detiene ("estudio archivado").

## 8. Pantalla

**Crear estudio** (`_tab_nicho.html`): se agrega el país (select con los de
`proyectos.PAISES_CALENDARIO` más SE, GB, DE, FR, IT, NL, CA, AU, IN, JP, AE; por defecto
el del proyecto). **Editar estudio**: idem.

**Tarjeta "Investigar el nicho"** (`templates/_nicho_investigacion.html`, incluida en
`nicho_estudio.html` arriba de las fuentes), cuando no hay investigación o la última
terminó:

- El tema del estudio (texto, con link a editar si está vacío: sin tema no hay botón).
- País (select), chips de plataformas (`plataformas.disponibles(pais)`, todas marcadas;
  sin `APIFY_TOKEN` salen apagadas con "(falta APIFY_TOKEN)"), chips de redes (Reddit,
  YouTube; apagadas sin llave).
- `<details>` "Ajustes" con los cuatro topes.
- Desglose del estimado por fila (búsqueda + reseñas por plataforma, Claude, avatares) y
  el total, pintado por `GET .../investigar/estimar` al cambiar cualquier chip o tope,
  con contador de peticiones y bloqueo del envío si el estimado no coincide con los
  valores actuales (misma regla que el confirm de Apify de la Parte 2).
- Botón "Investigar (≈ US$ X)" → `confirm` con el total → `POST .../investigar`.

**Mientras corre** (estado distinto de `lista`/`detenida`/`interrumpida`): la tarjeta
muestra la línea de pasos con icono por estado (hecho, en curso, pendiente, aviso,
error), cifras acumuladas (productos, relevantes, reseñas, gasto), la barra de progreso
de la tarea viva (`iniciarPolling` con el job de ese paso; la página se recarga al
terminar cada tarea y ve el siguiente paso en curso) y el botón "Cancelar".

**Al terminar** (`lista`, `detenida`, `interrumpida`): resumen (consultas usadas,
productos y relevantes por plataforma, reseñas por fuente, gasto real contra aprobado,
motivo de parada si lo hay), botones "Reanudar" (si aplica) e "Investigar de nuevo", y
un `<details>` "Productos del nicho" con la lista de `producto_nicho` ordenada por
plataforma y reseñas: título con link, marca, precio, estrellas, reseñas, `relevante`
con su motivo, reseñas traídas. Solo lectura.

La sección Comentarios de siempre sigue debajo, y cuenta las reseñas por plataforma
gracias a `fuente` = plataforma (`fuentes_nombre` gana esas claves). La sección de
avatares no cambia. La pestaña Nicho muestra por estudio el estado de la investigación
como chip.

**Puesta a punto**: nada nuevo (APIFY_TOKEN ya tiene tarjeta).

## 9. Rutas y tareas

Rutas (Blueprint `nicho`):

- `GET /cliente/<c>/nicho/<eid>/investigar/estimar?pais=&plataformas=a,b&redes=reddit&consultas=3&productos_por_consulta=20&productos_elegidos=15&resenas_por_producto=100`
  → JSON `{"filas": [{"clave", "nombre", "busqueda_usd", "resenas_usd", "texto"}], "claude_usd", "avatares_usd", "total_usd", "texto"}` o 400 `{error}`.
- `POST /cliente/<c>/nicho/<eid>/investigar` (los mismos campos como form): valida país,
  plataformas disponibles y llaves, topes en rango, tema no vacío, estudio no archivado,
  ninguna investigación viva; recalcula el estimado en el servidor (nunca confía en el
  del navegador); crea `extra.investigacion` con `aprobado_usd`; encola
  `nicho_inv_consultas`. Flash con el total aprobado.
- `POST .../investigar/reanudar`, `POST .../investigar/cancelar`.

Tareas (`tareas/investigacion.py`, registradas en `tareas.cargar_todas`):
`nicho_inv_consultas`, `nicho_inv_buscar` (payload `{cliente, estudio_id, plataforma}`),
`nicho_inv_seleccionar`; cada una con `al_interrumpir`. `tareas/nicho.py` cambia poco:
`ejecutar_recolectar` acepta `fuente` = plataforma (vía `fuentes.por_tipo`, que devuelve
`FuentePlataforma(clave)` para las claves del registro) y, si el payload trae
`investigacion: true`, al terminar (bien o mal) anota su paso y llama `avanzar`;
`ejecutar_generar` con `auto: true` aplica el tope (§6) y al terminar anota `generar` y
cierra la investigación (`lista`).

`datos.py` gana: `guardar_productos_nicho` (upsert), `productos_nicho(cliente, eid,
plataforma=None, solo_elegidos=False)`, `marcar_relevancia`, `sumar_resenas_traidas`,
`actualizar_investigacion` (RMW con candado), `investigacion(cliente, eid)`.

## 10. Pruebas (pytest, sin red) y prueba real

Sin red, con los patrones de la Parte 2 (sesión de Apify guionada, `dormir` parchado,
Claude parchado, SQLite real):

- Registro: por plataforma, `entradas_busqueda`/`entradas_resenas` arman exactamente lo
  documentado (URL de Amazon con dominio y consulta codificada; una entrada por consulta
  en MELI; modos de TikTok Shop; una entrada por ASIN en Amazon), `leer_producto` y
  `leer_resena` sobre fixtures con la forma de salida de cada actor (descartan ítems sin
  id o sin texto), `disponibles`, `dominio`, `idioma`, estimados.
- `correr_lote`: 3 entradas con `max_simultaneas=2` arrancan 2, luego 1; corridas con
  estados mixtos (SUCCEEDED, FAILED con ítems); un `maxTotalChargeUsd` por corrida;
  `resultados` crudos; `FuenteApify` de la Parte 2 sigue pasando sus pruebas sin cambios.
- `investigacion` puro: `siguiente_paso` recorre la cadena completa, salta plataformas
  sin llave y pasos hechos, se detiene con `detenida`/cancelada, `resumen`.
- Tareas: consultas (JSON válido, inválido una vez, inválido dos veces → detenida),
  buscar (productos guardados, upsert, gasto `recoleccion` con detalle de búsqueda,
  aviso por plataforma vacía), seleccionar (reglas de elección por reseñas, tope 300
  filas, ninguna relevante → detenida), `nicho_recolectar` con una plataforma
  (comentarios con `fuente` = plataforma y `contexto` = título; `resenas_traidas`;
  paso anotado; `avanzar` llamado), generar con `auto` (dentro del tope corre; fuera →
  detenida con el mensaje).
- Cadena de punta a punta con todo falso: desde `POST investigar` hasta la generación
  encolada, verificando el orden de los jobs y que `gastado_usd` = suma de los `gasto`.
- Reanudación: cadena caída en `resenas:meli` → Reanudar encola solo `resenas:meli`
  (con los productos sin reseñas) y lo que sigue; nada de `buscar` se repite.
- Rutas: estimar (JSON, 400), investigar (puerta de tema/llaves/topes/viva/archivado),
  reanudar, cancelar; plantillas (tarjeta sin llave, con llave, en curso, terminada).

**Prueba real de centavos (manual, con el visto bueno de Daniel, requiere
`APIFY_TOKEN`)**: un estudio de prueba con topes mínimos (1 consulta, 5 productos por
consulta, 2 elegidos, 20 reseñas por producto) en un país por plataforma (Amazon SE o
ES, Mercado Libre CO, TikTok Shop) para confirmar la forma de salida de cada actor,
ajustar `leer_producto`/`leer_resena` y congelar los fixtures. Costo esperado: menos de
US$ 0,50 en total. Sin esta prueba la Parte 3 no se da por terminada.

## 11. Entregas y fuera de alcance

- **Parte 3 (este spec)**: motor (§1, §2, §4–§9), plataformas Amazon, Mercado Libre y
  TikTok Shop, redes Reddit y YouTube en la cadena, pruebas y prueba real.
- **Parte 4**: Walmart, AliExpress, eBay, Etsy, reseñas de Google Maps, Trustpilot,
  Instagram y Facebook (comentarios públicos), Google Play y App Store, y un buscador de
  videos de TikTok para la fuente de comentarios; cada una es una entrada del registro
  con fixture, prueba y corrida de centavos. Temu queda fuera hasta que exista actor de
  reseñas.
- **Parte 5**: búsqueda en Google (SERP) y lectura de comentarios de páginas sueltas.
- **Fuera de alcance**: selección manual de productos (Daniel la descartó), conectores
  de tiendas del cliente como fuente de nicho, unificar la tarjeta "Amazon / TikTok
  (Apify)" por link con el registro nuevo (pendiente menor), traducción de reseñas
  (Claude las lee en su idioma; los avatares salen en el `idioma` del estudio).

## 12. Hechos verificados (2026-09-20, apify.com y docs.apify.com)

- `POST /v2/acts/{actorId}/runs` (alias `/v2/actors/`): `maxItems` limita los ítems
  facturados solo en actores pay-per-result; `maxTotalChargeUsd` limita el gasto total
  de la corrida en todos los modelos de precio (docs.apify.com/api/v2/act-runs-post).
- `junglee~amazon-reviews-scraper`: solo `productUrls`; `maxReviews` es POR URL de
  producto (y ~100 por nivel de estrellas); documenta amazon.com.
- `junglee~amazon-crawler`: `categoryOrProductUrls` exige URL completa (`/s?k=`), 23 282
  usuarios, US$ 3 por 1 000, `maxItemsPerStartUrl`, `proxyCountry`.
- `axesso_data~amazon-reviews-scraper`: `asin` + `domainCode` obligatorios, `maxPages` ≤
  10, US$ 0,90 por 1 000, 15 marketplaces (US, UK, DE, JP, AU, BR, CA, FR, IN, IT, ES,
  NL, SE, MX, AE), salida `text`, `rating`, `date`, `reviewId`, `verified`.
- `karamelo~mercado-libre-listings-scraper`: `keyword` + `country` (URL del sitio), 18
  países, US$ 2 por 1 000; `karamelo~mercadolibre-review-scraper`: `productUrls`,
  `maxReviewsPerProduct` (100 por defecto), US$ 0,70 por 1 000, salida `reviewId`,
  `reviewText`, `reviewRating`, `reviewDate`, `productId`.
- `unseenuser~tiktok-shop-scraper`: `mode` `shop_search` / `product_reviews`,
  `searchKeywords`, `productUrls`, `maxResults`, `maxReviewsPerProduct`, US$ 4,50 por
  1 000, 2 158 usuarios, 5,0/5.
- El inventario completo (14 plataformas, precios y campos) está en
  `docs/nicho/apify-inventario-2026-09-20.md`; los actores de la Parte 4 se re-verifican al planearla.
