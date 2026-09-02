# Investigación: Wan 3.0 y Seedance vía WaveSpeed — video largo en una sola llamada

Investigado en vivo el 1 sep 2026, solo contra documentación/páginas oficiales de
cada proveedor (wavespeed.ai, fal.ai, alibabacloud.com/help, higgsfield.ai,
docs.higgsfield.ai). Nada de blogs de terceros ni agregadores. Los precios y
catálogos de estas APIs cambian cada pocas semanas — antes de una decisión de
volumen alto, re-verificar.

## 1. Resumen ejecutivo

**Sí hay una opción real hoy para 12–15s continuos en una sola llamada de API,
y no una sino dos, en dos plataformas ya conectadas o conectables a este repo:**

- **Wan 3.0 (Alibaba)**, vía **WaveSpeed AI** o **fal.ai** o directo en
  **Alibaba Cloud Model Studio/DashScope**, genera hasta **30 segundos en un
  solo pase** (`text-to-video`, `image-to-video`, `reference-to-video`), con
  audio nativo opcional, desde **$0.05/seg a 480p** ($0.10 a 720p, $0.20 a
  1080p). Es generación nueva guiada por referencias, **no edición de un video
  existente preservándolo pixel a pixel**.
- **Seedance 2.0 vía WaveSpeed AI** (a diferencia de la Seedance de fal.ai que
  ya está documentada en este repo como solo-generación) sí tiene un endpoint
  **`video-edit`** que toma un video existente y lo edita con un prompt,
  con un **máximo de 15 segundos de salida** — encaja justo en el rango de
  12-15s pedido, y si el objetivo es "editar" en vez de "generar desde cero"
  es la única de las dos rutas que aplica.
- **Higgsfield NO tiene Wan 3.0 en su API programable** (la que ya usa este
  repo vía `higgsfield_client.py`) — solo lo agregó a su app de consumo
  (changelog, 24 ago 2026). Ver detalle en §2.3.

## 2. Wan 3.0 (Alibaba)

**Sí existe con API pública programable**, confirmado en tres lugares
independientes: la documentación oficial de Alibaba Cloud Model Studio, la
página de modelo de WaveSpeed AI, y la página de modelo de fal.ai. No es un
modelo teórico ni exclusivo de una app de consumo — aunque en una de las tres
plataformas revisadas (Higgsfield) sí resultó ser solo-consumo.

### 2.1 Alibaba Cloud Model Studio / DashScope (el proveedor original)

- **Endpoint**: `POST https://{WorkspaceId}.{region}.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
  — asíncrono, requiere header `X-DashScope-Async: enable` y `Authorization: Bearer sk-xxxx` (API key de DashScope).
  Fuente: [Wan3.0 Video Generation API Reference](https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference), verificado 1 sep 2026.
- **Regiones internacionales disponibles** (no solo China continental): Singapur, Beijing, EE.UU. (Virginia), Tokio, Fráncfort, Hong Kong. Fuente: misma página.
- **Modelos**: `wan3.0-video` (estándar) y `wan3.0-video-prime` (variante acelerada). Fuente: [wan3.0-video-prime — model information](https://www.alibabacloud.com/help/en/model-studio/wan3-0-video-prime), verificado 1 sep 2026.
- **Duración máxima**: parámetro de duración documentado como "an integer in the range [2, 30]" segundos, en una sola generación (no video encadenado). Fuente: Wan3.0 Video Generation API Reference, arriba.
- **Audio nativo**: sí, parámetro `audio` (boolean), default `true`. Misma fuente.
- **Resolución**: 480P / 720P / 1080P, default 1080P. Misma fuente.
- **Precio (variante Prime, USD/seg)**: 480P $0.0636, 720P $0.1272, 1080P $0.2544 en la mayoría de regiones; Singapur ligeramente más caro: $0.068 / $0.14 / $0.28. Fuente: [wan3.0-video-prime — model information](https://www.alibabacloud.com/help/en/model-studio/wan3-0-video-prime), verificado 1 sep 2026.
- **Precio (variante estándar `wan3.0-video`)**: la página de referencia de API no listaba una tabla de precios en USD en el contenido que se pudo extraer — ver "Qué NO se pudo confirmar" (§5). El precio estándar $0.05/$0.10/$0.20 por segundo (480p/720p/1080p) sí quedó confirmado de forma independiente en WaveSpeed y fal.ai (§2.2), que replican el pricing oficial de Alibaba.

### 2.2 WaveSpeed AI y fal.ai (revendedores/agregadores con API propia)

Ambas plataformas exponen Wan 3.0 como modelo de catálogo con su propio
esquema HTTP, consistente con el patrón que ya usa `providers/wavespeed_client.py`
en este repo para Wan 2.7.

| Dato | WaveSpeed AI | fal.ai |
|---|---|---|
| Endpoints | `POST https://api.wavespeed.ai/api/v3/alibaba/wan-3.0/{text-to-video,image-to-video,reference-to-video}` y las mismas tres bajo `wan-3.0-prime/` | `alibaba/wan-3.0/{text-to-video,reference-to-video}` y `alibaba/wan-3.0-prime/{text-to-video,image-to-video,reference-to-video}` (rutas fal, se llaman vía cliente fal) |
| Duración | 2–30s por request, default 5s, "en un solo pase de generación, no encadenado" | hasta 30s (confirmado también por un ejemplo de salida con `"duration": 30.022993`) |
| Audio | sí, `enable_audio` (default `true` en la variante Prime image-to-video) | sí (opción "Audio" en el formulario/input) |
| Resolución | 480p / 720p / 1080p | 480p / 720p / 1080p |
| Precio estándar (USD/seg) | 480p $0.05, 720p $0.10, 1080p $0.20 | 480p $0.05, 720p $0.10, 1080p $0.20 (texto exacto de la página: "you will be charged $0.05 480p, $0.10 720p, or $0.20 1080p") |
| Precio Prime (USD/seg) | 480p $0.075, 720p $0.15, 1080p $0.30 (`wan-3.0-prime/image-to-video`) | $0.068 / $0.14 / $0.28 según un resumen de búsqueda — no se pudo verificar con fetch directo de la página fal (ver §5, la página devolvió 429) |
| ¿Video-edit (subir video existente)? | **No.** El catálogo de Wan 3.0 en WaveSpeed solo tiene `text-to-video`, `image-to-video`, `reference-to-video` (más las variantes Prime). El único `video-edit` de Alibaba en WaveSpeed sigue siendo el de **Wan 2.7** (`alibaba/wan-2.7/video-edit`, ya documentado en `providers/wavespeed_client.py`), no de Wan 3.0. | No investigado a fondo por el 429; no hay indicio en las URLs de modelo listadas de un `video-edit` de Wan 3.0. |

Fuentes: [wavespeed.ai/wan-3-api](https://wavespeed.ai/wan-3-api), [wavespeed.ai/models/alibaba/wan-3.0/image-to-video](https://wavespeed.ai/models/alibaba/wan-3.0/image-to-video), [wavespeed.ai/models/alibaba/wan-3.0-prime/image-to-video](https://wavespeed.ai/models/alibaba/wan-3.0-prime/image-to-video), [wavespeed.ai/collections/wan-3.0](https://wavespeed.ai/collections/wan-3.0), [fal.ai/models/alibaba/wan-3.0/text-to-video](https://fal.ai/models/alibaba/wan-3.0/text-to-video) — todas verificadas 1 sep 2026.

**Nota sobre `reference-to-video`**: acepta imágenes, video y audio de referencia
juntos para guiar una generación nueva ("image, video, and audio references
together" — wavespeed.ai/wan-3-api). Esto **no es lo mismo que editar un video
existente preservándolo**: al igual que con Seedance en fal.ai (ya documentado
en `providers/comparador_modelos.py`), el video de referencia alimenta una
generación nueva guiada por el prompt, no una edición pixel a pixel del clip
subido.

### 2.3 Higgsfield.ai

**Wan 3.0 SÍ apareció en Higgsfield — pero solo en la app de consumo, no en su
API programable.**

- El changelog público de Higgsfield confirma: *"Wan 3.0 and Wan 3.0 Prime.
  Now on Higgsfield. The newest Wan video models are live, generating video
  from text and images."* — fechado **24 ago 2026**, hasta 30s, 480p/720p/1080p,
  audio sincronizado. Acceso: *"open Video → model selector → choose Wan 3.0
  or Wan 3.0 Prime"* — es decir, un flujo de UI, no un parámetro de API.
  Fuente: [higgsfield.ai/creator-hub/changelog](https://higgsfield.ai/creator-hub/changelog), verificado 1 sep 2026.
- La documentación de la **API programable** de Higgsfield
  (`docs.higgsfield.ai/docs`, la misma familia de docs contra la que este repo
  ya integró `soul/v2/standard` en `higgsfield_client.py`) **no menciona "Wan"
  en ningún lugar** de su índice. Fuente: [docs.higgsfield.ai/docs](https://docs.higgsfield.ai/docs), verificado 1 sep 2026.
- Conclusión: si se quisiera usar Wan 3.0 desde Higgsfield específicamente
  (que es el proveedor de video ya integrado en este repo), **hoy no se puede
  vía API** — solo manualmente en la app. Para automatizarlo desde este repo,
  la ruta real es WaveSpeed AI o fal.ai directamente (§2.2), o Alibaba Cloud
  Model Studio directo (§2.1).

## 3. Seedance vía WaveSpeed AI (no fal.ai)

**Sí, WaveSpeed expone Seedance 2.0 como familia de modelos propia**, en
`wavespeed.ai/collections/seedance-2.0`, con un patrón de endpoints mucho más
amplio que el único endpoint (`image-to-video`) que fal.ai ofrece y que ya usa
este repo en `providers/seedance_client.py`.

### 3.1 Catálogo confirmado

Cada tarea (`text-to-video`, `image-to-video`, `video-edit`, `video-extend`,
más variantes `-turbo`) existe en tres tiers de modelo: estándar, `-fast` y
`-mini`. Ejemplos de ruta verificados directamente con fetch (no solo listado):

- `https://api.wavespeed.ai/api/v3/bytedance/seedance-2.0/video-edit`
- `https://api.wavespeed.ai/api/v3/bytedance/seedance-2.0-mini/video-edit`

Fuente: [wavespeed.ai/models/bytedance/seedance-2.0/video-edit](https://wavespeed.ai/models/bytedance/seedance-2.0/video-edit), [wavespeed.ai/models/bytedance/seedance-2.0-mini/video-edit](https://wavespeed.ai/models/bytedance/seedance-2.0-mini/video-edit), [wavespeed.ai/models/bytedance/seedance-2.0/image-to-video](https://wavespeed.ai/models/bytedance/seedance-2.0/image-to-video) — verificadas 1 sep 2026.

### 3.2 La pregunta clave: ¿edita un video existente o solo genera nuevo?

**A diferencia de la Seedance de fal.ai (que este repo ya descartó para
edición porque `video_urls`/`image_urls` solo alimentan una generación nueva,
`providers/comparador_modelos.py` líneas ~16-21), la Seedance 2.0 de WaveSpeed
SÍ tiene un endpoint `video-edit` que toma un `video` (URL) como campo de
entrada obligatorio y lo edita.**

Texto exacto de la descripción del modelo (`bytedance/seedance-2.0/video-edit`):
*"edits an input video from a natural-language prompt"*, donde *"the reference
video drives subject identity, composition, and motion while the model
rewrites"* los elementos que pida el prompt — es decir, el video de entrada
sí condiciona/preserva identidad, composición y movimiento, y el prompt cambia
solo lo indicado. Esto es análogo en espíritu al `wan-2.7/video-edit` que ya
usa este repo (`providers/wavespeed_client.py`), no al patrón de "referencia
que alimenta generación nueva" de Wan 3.0/Seedance-fal.ai.

Parámetros de entrada confirmados (`video-edit`, ambos tiers estándar y mini):
`video` (URL, requerido), `prompt` (requerido), `reference_images` (opcional,
guía de identidad/estilo), `reference_audios` (opcional), `duration` (4–15s),
`aspect_ratio`, `resolution` (480p/720p/1080p/4k), `generate_audio` (boolean).

### 3.3 Duración máxima — el dato crítico para el objetivo de negocio

**15 segundos de salida es el máximo**, y los videos de entrada más largos de
15s se recortan automáticamente a 15s antes de editarlos: *"Videos longer than
15 s are trimmed to 15 s."* Fuente: [wavespeed.ai/models/bytedance/seedance-2.0/video-edit](https://wavespeed.ai/models/bytedance/seedance-2.0/video-edit), verificado 1 sep 2026 — mismo tope confirmado independientemente en la variante `-mini` y en `image-to-video`/`text-to-video-mini` (rango "4-15 segundos (continuous)").

Esto encaja directo con el objetivo de negocio (12–15s continuos): **el tope
de 15s de Seedance-WaveSpeed es justo el límite superior pedido**, ya sea
generando desde imagen/texto o editando un video existente.

### 3.4 Precio (USD)

Confirmado con fetch directo de cada página de modelo (no de una tabla de
precios general, que solo lista "Seedance 2.0 Fast: $0.10/seg" sin desglose
por tier — ver §5):

| Modelo | 480p | 720p | 1080p | 4K |
|---|---|---|---|---|
| `seedance-2.0/video-edit` | $0.075/seg | $0.15/seg | $0.375/seg | $0.750/seg |
| `seedance-2.0-mini/video-edit` | $0.0375/seg | $0.075/seg | $0.1875/seg | $0.3750/seg |
| `seedance-2.0/image-to-video` | $0.12/seg | $0.24/seg | $0.60/seg | $1.20/seg |

El precio de `video-edit` se factura sobre "(input duration + output
duration)" — igual que `wan-2.7/video-edit`, que ya factura entrada + salida
(ver comentario en `providers/wavespeed_client.py` línea 21). El precio de
`image-to-video` es notablemente más caro por segundo que `video-edit` en el
mismo tier — vale la pena usar `video-edit` si el caso de uso lo permite.

Fuentes: mismas páginas de modelo del §3.1, verificadas 1 sep 2026.

## 4. Tabla comparativa final

| Proveedor / modelo | Endpoint | Duración máx. por llamada | Edición vs. generación nueva | Audio nativo | Precio USD | Fuente + fecha |
|---|---|---|---|---|---|---|
| Wan 3.0 estándar — Alibaba Cloud directo | `POST https://{ws}.{region}.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis` (`model: wan3.0-video`) | 2–30s, un solo pase | Generación nueva (T2V/I2V/ref-to-video) | Sí, opcional (`audio: true` default) | $0.05/$0.10/$0.20 por seg (480p/720p/1080p) — confirmado vía réplicas en WaveSpeed/fal, no en la tabla de precios oficial directa (ver §5) | alibabacloud.com/help/en/model-studio/wan3-video-generation-api-reference, 1 sep 2026 |
| Wan 3.0 Prime — Alibaba Cloud directo | mismo endpoint, `model: wan3.0-video-prime` | 2–30s | Generación nueva | Sí | $0.0636/$0.1272/$0.2544 por seg (Singapur algo más: $0.068/$0.14/$0.28) | alibabacloud.com/help/en/model-studio/wan3-0-video-prime, 1 sep 2026 |
| Wan 3.0 — WaveSpeed AI | `POST https://api.wavespeed.ai/api/v3/alibaba/wan-3.0/{text-to-video\|image-to-video\|reference-to-video}` | 2–30s, un solo pase | Generación nueva | Sí (`enable_audio`) | $0.05/$0.10/$0.20 por seg | wavespeed.ai/models/alibaba/wan-3.0/image-to-video, 1 sep 2026 |
| Wan 3.0 Prime — WaveSpeed AI | `.../alibaba/wan-3.0-prime/image-to-video` | 30s | Generación nueva | Sí | $0.075/$0.15/$0.30 por seg | wavespeed.ai/models/alibaba/wan-3.0-prime/image-to-video, 1 sep 2026 |
| Wan 3.0 — fal.ai | `alibaba/wan-3.0/{text-to-video,reference-to-video}` | hasta 30s | Generación nueva | Sí | $0.05/$0.10/$0.20 por seg | fal.ai/models/alibaba/wan-3.0/text-to-video, 1 sep 2026 |
| Wan 3.0 / Wan 3.0 Prime — Higgsfield | **No hay endpoint de API** — solo app UI (Video → model selector) | 30s (según changelog, no verificable vía API) | Generación nueva | Sí | No aplica (no hay API) | higgsfield.ai/creator-hub/changelog (24 ago 2026) + docs.higgsfield.ai/docs (sin "Wan"), verificado 1 sep 2026 |
| Seedance 2.0 `video-edit` — WaveSpeed AI | `POST https://api.wavespeed.ai/api/v3/bytedance/seedance-2.0/video-edit` | **15s** (input >15s se recorta a 15s) | **Edición real** de un video subido (`video` requerido), preserva identidad/composición/movimiento | Sí (`generate_audio`) | $0.075/$0.15/$0.375/$0.750 por seg (480p/720p/1080p/4k), factura entrada+salida | wavespeed.ai/models/bytedance/seedance-2.0/video-edit, 1 sep 2026 |
| Seedance 2.0 mini `video-edit` — WaveSpeed AI | `.../bytedance/seedance-2.0-mini/video-edit` | 4–15s | Edición real | Sí | $0.0375/$0.075/$0.1875/$0.375 por seg | wavespeed.ai/models/bytedance/seedance-2.0-mini/video-edit, 1 sep 2026 |
| Seedance 2.0 `image-to-video` — fal.ai (ya en el repo) | `https://fal.run/bytedance/seedance-2.0/image-to-video` | 5s por defecto en el cliente del repo (rango de la API no re-verificado aquí) | Generación nueva, sin campo de video a editar | No verificado en esta investigación | $0.473/seg a 720p (ya documentado en el repo) | providers/seedance_client.py, ROADMAP.md (28 ago 2026) |
| Wan 2.7 `video-edit` — WaveSpeed AI (ya en el repo, referencia) | `.../alibaba/wan-2.7/video-edit` | 2–10s facturados | Edición real, hasta 3 imágenes de referencia | No documentado en el cliente actual | $0.10/seg 720p, $0.15/seg 1080p | providers/wavespeed_client.py (verificado 1 sep 2026 según el propio repo) |

## 5. Qué NO se pudo confirmar

- **Precio USD del `wan3.0-video` estándar directo en la doc oficial de
  Alibaba Cloud.** La página de referencia de API (`wan3-video-generation-api-reference`)
  no traía una tabla de precios en el contenido extraído por el fetch — el
  precio $0.05/$0.10/$0.20 por segundo que se reporta arriba para el modelo
  estándar viene de las páginas de WaveSpeed y fal.ai (que replican pricing de
  Alibaba, y coinciden entre sí), no de una página de precios de Alibaba Cloud
  vista directamente. Antes de presupuestar con este número, valdría la pena
  entrar a la consola de Alibaba Cloud Model Studio con una cuenta y confirmar
  en su página de precios (`alibabacloud.com/product/model-studio-pricing` o
  similar), que requiere navegar la consola/posible login.
- **Precio exacto de Wan 3.0 Prime en fal.ai** ($0.068/$0.14/$0.28 por
  segundo). La página `fal.ai/wan-3` devolvió **HTTP 429 (rate limit)** en el
  intento de fetch directo, así que ese número viene únicamente del resumen de
  un WebSearch, no de un fetch verificado de la página oficial. Tratar como
  no confirmado hasta re-intentar el fetch directo.
- **Si Wan 3.0 en WaveSpeed o fal.ai tiene algún tope de duración distinto
  para audio activado vs. desactivado**, o si el audio nativo cuenta hacia
  algún límite de "generaciones con audio" separado del cupo normal — no
  apareció nada al respecto en las páginas revisadas.
- **Rango de duración real de la API de Seedance-fal.ai** (la que ya usa este
  repo): el cliente del repo (`providers/seedance_client.py`) pasa
  `duration=5` por defecto pero no documenta el rango máximo aceptado por la
  API; no se volvió a verificar esto en esta investigación porque ya estaba
  fuera del alcance pedido (la tarea pedía WaveSpeed, no fal.ai).
- **Un video-edit de Wan 3.0 en WaveSpeed** — se buscó explícitamente
  (`wavespeed.ai/models/alibaba/wan-3.0/video-edit` devolvió 404, y la página
  de colección `wavespeed.ai/collections/wan-3.0` solo lista text/image/
  reference-to-video más las variantes Prime) — parece confirmado que no
  existe, pero no se revisó exhaustivamente cada posible variación de URL.
- **Login/cuenta necesarios para ver precios con volumen/descuentos por tier**
  en WaveSpeed o fal.ai (planes empresariales, descuentos por volumen) — no se
  intentó, se reportan solo los precios pay-as-you-go públicos.
