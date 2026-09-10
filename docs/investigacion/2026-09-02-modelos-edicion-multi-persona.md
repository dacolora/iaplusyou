# Investigación: ¿existe un editor de imagen que cambie el MISMO tipo de objeto en varias personas de una sola foto, en una sola llamada?

Investigado en vivo el 2 sep 2026, solo contra documentación/páginas oficiales
de cada proveedor (fal.ai, wavespeed.ai, blog.google, ai.google.dev,
developers.openai.com, seed.bytedance.com). Nada de blogs de terceros ni
agregadores como fuente de una afirmación de capacidad o de precio — se
usaron solo para *encontrar* la URL oficial a verificar, nunca como fuente
final. Los catálogos y precios de estas APIs cambian cada pocas semanas.

## 0. Punto de partida (lo ya probado en este repo, 2 sep 2026)

Foto real de 3 personas (2 con calzado puesto, 1 descalza), prompt ya
corregido para pedir explícitamente contar personas y editar a todas
(`providers/nano_banana_client.py` `SWAP_PROMPT`,
`providers/comparador_modelos.py` `PROMPT_EDICION_IMAGEN`):

- **Nano Banana / Gemini 2.5 Flash Image directo** — edita bien a la persona
  más prominente, deja a la segunda con su calzado original.
- **Nano Banana vía fal.ai** (`fal-ai/nano-banana/edit`) — peor: le puso
  calzado a la persona descalza y dejó sin cambiar a las dos que ya tenían.
- **Qwen Image Edit Plus** (`fal-ai/qwen-image-edit-plus`) — no cambió el
  calzado de nadie.

Documentado también en `templates/_comparacion_modelos.html`.

## 1. Resumen ejecutivo

**No se encontró ningún modelo cuya documentación OFICIAL afirme
explícitamente la capacidad exacta que se busca: editar el mismo tipo de
objeto en 2-3 personas que YA coexisten juntas en una sola foto de entrada,
en una sola llamada.** Todo lo que la documentación oficial de los
proveedores revisados sí afirma sobre "múltiples personas" o "múltiples
imágenes" describe una capacidad distinta y más limitada: **componer/fusionar
personas que vienen de fotos de referencia SEPARADAS en una escena nueva**
(Nano Banana Pro), o **aplicar el mismo prompt de edición a un LOTE de fotos
separadas que comparten un mismo sujeto/producto** (Seedream Edit Sequential),
no editar varias personas que ya están juntas en una única foto existente.

El candidato con la afirmación oficial más cercana — aunque no idéntica — al
caso de uso es:

- **Nano Banana Pro (Gemini 3 Pro Image) vía fal.ai**, endpoint
  `fal-ai/nano-banana-pro/edit`. Google afirma oficialmente (blog.google, ver
  §2.1) que el modelo *"maintain[s] the consistency and resemblance of up to
  5 people"* al combinar hasta 14 imágenes en una composición. **Pero el
  ejemplo oficial que acompaña esa afirmación es "Put these five people and
  this dog into a single image"** — es decir, describe tomar 5 fotos
  separadas de 5 personas distintas y fusionarlas en una escena nueva
  preservando la identidad de cada una, **no** editar un mismo objeto (p. ej.
  calzado) en 2-3 personas que ya están juntas en una sola foto de entrada.
  Es la misma familia de modelo (Gemini) que ya es el mejor de los 3
  conectados hoy, y su salto de razonamiento respecto a Gemini 2.5 Flash
  Image podría generalizar mejor al caso real — pero **eso es una hipótesis
  para probar, no una afirmación que la documentación oficial respalde**.
  No se debe presentar como confirmado.
- **Ningún otro candidato revisado** (Seedream 4.0/4.5 Edit, GPT-Image-1/2,
  Flux Kontext Pro/Max "multi", Recraft V3, OmniGen v1, Easel AI, modelos de
  virtual try-on) tiene en su documentación oficial una afirmación siquiera
  parecida a la de Nano Banana Pro. Ver detalle por modelo en §2-§4.

**Conclusión honesta: no hay una recomendación respaldada por fuente oficial
para reemplazar o complementar los 3 modelos ya conectados en esta tarea
específica.** Lo único defendible con la evidencia recolectada es: si se
quiere seguir intentando, Nano Banana Pro vía fal.ai es la prueba de siguiente
paso más razonable (mismo proveedor/familia que ya da el mejor resultado,
mayor límite de imágenes de referencia, modelo más nuevo con más
razonamiento) — pero requiere una prueba en vivo con la foto real de 3
personas, igual que se hizo con los 3 modelos actuales, antes de conectarlo.

## 2. Candidatos con afirmación oficial sobre "múltiples personas/imágenes"

### 2.1 Nano Banana Pro / Gemini 3 Pro Image — fal.ai

- **Endpoints**: generación `fal-ai/nano-banana-pro` (`/api`), edición
  `fal-ai/nano-banana-pro/edit` (`/api`). También existe un alias
  `fal-ai/gemini-3-pro-image-preview/edit`. Fuentes:
  [fal.ai/models/fal-ai/nano-banana-pro/edit](https://fal.ai/models/fal-ai/nano-banana-pro/edit),
  [fal.ai/models/fal-ai/nano-banana-pro/edit/api](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api),
  verificadas 2 sep 2026.
- **Imágenes de entrada**: parámetro `image_urls` (lista de strings),
  documentado como *"Combine up to 14 images in single composition"*. No hay
  un campo separado para "foto a editar" vs. "imágenes de referencia del
  producto" — todo entra en la misma lista `image_urls`. Fuente: página de
  edición de fal.ai, arriba, verificada 2 sep 2026.
- **Afirmación oficial de consistencia multi-persona** — texto exacto del
  blog oficial de Google (no de fal.ai, que solo lo repite):
  *"With Nano Banana Pro, you can blend more elements than ever before, using
  up to 14 images and maintaining the consistency and resemblance of up to
  5 people."* Ejemplo oficial que acompaña la afirmación: *"Put these five
  people and this dog into a single image"* con la nota de que preserva
  *"The identity of all five people and their attire"*. Otro ejemplo oficial
  citado: *"A high-fashion editorial shot set in a desert landscape that
  maintains the consistency and resemblance of the people from the 6 input
  photos."* Fuente:
  [blog.google/innovation-and-ai/products/nano-banana-pro](https://blog.google/innovation-and-ai/products/nano-banana-pro/),
  verificado 2 sep 2026.
  - **Lectura literal, sin inflar la afirmación**: esto es consistencia de
    identidad al **componer personas provenientes de fotos separadas** en
    una escena nueva — no es una afirmación sobre editar un mismo tipo de
    objeto (calzado) en varias personas que **ya están juntas** en una única
    foto de entrada. No se encontró, ni en el blog oficial ni en
    `ai.google.dev/gemini-api/docs/image-generation` (verificado 2 sep 2026,
    sin ese ejemplo específico), ningún ejemplo de "edita el mismo objeto en
    cada persona de esta foto existente".
- **Precio**: página oficial de fal.ai —
  *"$0.15"* por imagen en resolución estándar (1K/2K), *"4K outputs charged
  at 2x rate"* (≈$0.30). Fuente:
  [fal.ai/models/fal-ai/nano-banana-pro/edit](https://fal.ai/models/fal-ai/nano-banana-pro/edit),
  verificado 2 sep 2026.

### 2.2 Seedream 4.0 / 4.5 Edit — fal.ai y WaveSpeed AI

- **Endpoints**: `fal-ai/bytedance/seedream/v4/edit` y
  `fal-ai/bytedance/seedream/v4.5/edit` en fal.ai;
  `bytedance/seedream-v4/edit` y `bytedance/seedream-v4.5/edit` en WaveSpeed
  AI. Fuentes:
  [fal.ai/models/fal-ai/bytedance/seedream/v4/edit](https://fal.ai/models/fal-ai/bytedance/seedream/v4/edit),
  [wavespeed.ai/models/bytedance/seedream-v4.5/edit](https://wavespeed.ai/models/bytedance/seedream-v4.5/edit),
  verificadas 2 sep 2026.
- **Imágenes de entrada**: WaveSpeed documenta explícitamente *"Upload 1–10
  images under images. These are the photos that will be edited."* Fuente:
  página de WaveSpeed arriba, verificada 2 sep 2026.
- **Afirmación oficial sobre múltiples imágenes**: el ejemplo oficial de
  fal.ai describe composición cruzada entre imágenes, no edición de varias
  personas dentro de una misma foto: *"replace the product in Figure 1 with
  that in Figure 2"* / *"copy the text from Figure 3 to the top"*. Fuente:
  [fal.ai/models/fal-ai/bytedance/seedream/v4/edit](https://fal.ai/models/fal-ai/bytedance/seedream/v4/edit),
  verificado 2 sep 2026. **No hay mención de editar múltiples personas ya
  presentes en una misma foto.**
- **Variante "Edit Sequential"** (`bytedance/seedream-v4.5/edit-sequential`
  en WaveSpeed): se investigó específicamente porque el nombre sugería algo
  relevante. Su documentación oficial la describe como *"multi-image editing
  model designed to apply the same edit across a whole set of images. It
  automatically tracks the main subject through the series, keeps identity
  stable"*, con instrucción de subir *"images you want to edit sequentially
  (all should contain the same main subject or product)"*. Es decir: aplica
  UN mismo prompt de edición a un LOTE de fotos SEPARADAS de un mismo
  sujeto/producto (pensado para, p. ej., editar 8 fotos de producto igual),
  **no** editar varias personas distintas dentro de una sola foto. Descartado
  para este caso de uso. Fuente:
  [wavespeed.ai/models/bytedance/seedream-v4.5/edit-sequential](https://wavespeed.ai/models/bytedance/seedream-v4.5/edit-sequential),
  verificado 2 sep 2026.
- **Página oficial de ByteDance** (`seed.bytedance.com`, no un revendedor):
  confirma el mismo patrón — *"Seedream 4.0 can accept up to a dozen
  reference images at a time, extracting character features, scene styles,
  and object structures from them for organic fusion"* — composición desde
  referencias separadas, sin ejemplo de editar multi-persona dentro de una
  foto. Fuente:
  [seed.bytedance.com/en/blog/seedream-4-0-officially-released-beyond-drawing-into-imagination](https://seed.bytedance.com/en/blog/seedream-4-0-officially-released-beyond-drawing-into-imagination),
  verificado 2 sep 2026.
- **Precio**: fal.ai v4 edit *"$0.03 per image"*; WaveSpeed v4.5 edit
  *"$0.04 per generated image"*. Fuentes: páginas de modelo arriba,
  verificadas 2 sep 2026.

## 3. Candidatos sin afirmación oficial relevante (revisados y descartados)

### 3.1 GPT-Image-1 / GPT-Image-2 edit — fal.ai / OpenAI

- **Endpoints en fal.ai**: `fal-ai/gpt-image-1/edit-image`,
  `openai/gpt-image-2/edit`. Fuentes:
  [fal.ai/models/openai/gpt-image-2/edit](https://fal.ai/models/openai/gpt-image-2/edit),
  verificado 2 sep 2026.
- **Imágenes de entrada**: la página de fal.ai solo dice *"The image_urls
  field accepts a list of images"*, sin tope numérico explícito en esa
  página. Un resumen de búsqueda sobre la página de referencia oficial de
  OpenAI (`developers.openai.com/api/reference/resources/images/methods/edit`)
  indica *"up to 16 images"* para los modelos GPT Image — **este dato viene
  de un resumen de búsqueda, no de un fetch directo verificado**: el fetch
  directo a `platform.openai.com/docs/api-reference/images/createEdit`
  devolvió HTTP 403 y a `developers.openai.com/.../methods/edit` devolvió
  404 al intentarlo directamente. Tratar el "16 imágenes" como no verificado
  de forma independiente.
- **Multi-persona/multi-instancia**: no se encontró ninguna mención, ni en
  la página de fal.ai ni en los resúmenes de la documentación oficial de
  OpenAI, sobre editar múltiples personas o instancias de un mismo objeto
  dentro de una sola foto.
- **Precio**: fal.ai GPT Image 2 edit, ejemplo dado —
  *"1024 x 1024"* en calidad alta cuesta *"$0.219"* por imagen; el precio
  varía según dimensiones/calidad/complejidad del prompt. Fuente:
  [fal.ai/models/openai/gpt-image-2/edit](https://fal.ai/models/openai/gpt-image-2/edit),
  verificado 2 sep 2026.

### 3.2 Flux Kontext Pro / Max — variante "multi" (fal.ai)

- **Endpoints**: `fal-ai/flux-pro/kontext/multi` (Pro) y
  `fal-ai/flux-pro/kontext/max/multi` (Max) — **distintos** del endpoint
  estándar de un solo input que ya se descartó en
  `templates/_comparacion_modelos.html`. Es decir, sí existe una variante de
  Kontext Pro/Max que acepta varias imágenes, contrario a lo que dice
  actualmente la tabla del repo sobre Kontext Pro ("solo recibe 1 imagen de
  entrada") — **matiz a corregir si se vuelve a evaluar Kontext**: el
  endpoint por defecto es de 1 imagen, pero hay una variante `/multi`
  separada. Fuentes:
  [fal.ai/models/fal-ai/flux-pro/kontext/multi](https://fal.ai/models/fal-ai/flux-pro/kontext/multi),
  [fal.ai/models/fal-ai/flux-pro/kontext/max/multi](https://fal.ai/models/fal-ai/flux-pro/kontext/max/multi),
  verificadas 2 sep 2026.
- **Estado**: ambas están etiquetadas explícitamente por fal.ai como
  *"Experimental version of FLUX.1 Kontext [pro/max] with multi image
  handling capabilities"* — es decir, el propio proveedor la marca como
  experimental, no como capacidad estable. Fuente: mismas páginas arriba.
- **Multi-persona/multi-instancia**: no hay ninguna afirmación oficial sobre
  editar varias personas o instancias del mismo objeto en una sola foto; el
  único ejemplo de prompt mostrado en la página (*"Put the little duckling on
  top of the woman's t-shirt"*) es de composición de un solo elemento sobre
  una sola persona.
- **Precio**: Pro *"$0.04 per image"*, Max *"$0.08 per image"*. Fuentes:
  mismas páginas, verificadas 2 sep 2026.

### 3.3 Recraft V3 (image-to-image) — fal.ai

- **Endpoint**: `fal-ai/recraft/v3/image-to-image`. Es una transformación de
  UNA imagen de entrada (estilo/edición general), no un editor que reciba
  por separado "foto a editar" + "imagen de referencia del producto" — no
  encaja con el patrón que necesita este caso de uso (mostrarle al modelo el
  calzado exacto a poner). No se encontró mención de multi-imagen ni de
  multi-persona en su documentación. Precio: *"$0.04 per image"* ($0.08 en
  estilo vector). Fuente:
  [fal.ai/models/fal-ai/recraft/v3/image-to-image](https://fal.ai/models/fal-ai/recraft/v3/image-to-image),
  verificado 2 sep 2026 (vía resumen de búsqueda, no fetch directo). Descartado
  sin necesidad de más investigación.

### 3.4 OmniGen v1 — fal.ai

- **Endpoint**: `fal-ai/omnigen-v1`. Su descripción de uso lista
  explícitamente *"Image Editing, Personalized Image Generation, Virtual
  Try-On, Multi Person Generation and more!"* — la etiqueta "Multi Person
  Generation" aparece tal cual, lo que lo hace superficialmente relevante.
  Fuente: [fal.ai/models/fal-ai/omnigen-v1](https://fal.ai/models/fal-ai/omnigen-v1),
  verificado 2 sep 2026.
- **Pero**: no se encontró en esa página ninguna descripción, ejemplo o
  parámetro que confirme específicamente la capacidad de editar el mismo
  objeto en varias personas ya presentes en una foto usando una imagen de
  referencia del producto — la etiqueta "Multi Person Generation" queda sin
  desarrollar en el contenido revisado. Acepta múltiples imágenes vía
  `input_image_urls` y prompts con sintaxis `<|image_1|>`, pero es un modelo
  de investigación (paper OmniGen) más antiguo que los otros candidatos, sin
  evidencia de calidad superior. **No se puede recomendar con la evidencia
  disponible — solo se puede decir que la etiqueta existe.** Precio:
  *"$0.10 per processed megapixel"*. Fuente: misma página, verificada 2 sep
  2026.

### 3.5 Easel AI "multiplayer" — fal.ai

- Se encontró porque el nombre "multiplayer" sonaba relevante. **Es un
  face/body swap, no un editor de ropa/calzado** — texto oficial exacto:
  *"simultaneously transform two people with the multiplayer mode, all while
  retaining the original image's details like outfits and aesthetics."* Es
  decir, hace lo opuesto a lo que se necesita: preserva la ropa/calzado y
  cambia caras/cuerpos. Descartado. Fuente:
  [blog.fal.ai/new-image-editing-model-from-easel-ai-now-available-on-fal](https://blog.fal.ai/new-image-editing-model-from-easel-ai-now-available-on-fal),
  verificado 2 sep 2026.

### 3.6 Modelos de "virtual try-on" (FASHN y similares) — fal.ai

- Revisados porque conceptualmente son el caso de uso más cercano (poner una
  prenda/calzado de una foto de referencia sobre una persona). La
  documentación oficial de estos modelos (p. ej. FASHN v1.5/v1.6 en fal.ai)
  describe el flujo estándar como una persona + una prenda por llamada; no
  se encontró ninguna documentación oficial que indique soporte explícito
  para aplicar la prenda a varias personas dentro de la misma foto en una
  sola llamada. Fuente:
  [fal.ai/models/fal-ai/fashn/tryon/v1.5/api](https://fal.ai/models/fal-ai/fashn/tryon/v1.5/api)
  y [blog.fal.ai/new-sota-virtual-try-on-model-by-fashn-live-on-fal](https://blog.fal.ai/new-sota-virtual-try-on-model-by-fashn-live-on-fal),
  verificadas 2 sep 2026 (vía resumen de búsqueda).

## 4. Tabla comparativa

| Modelo | Endpoint | Imágenes de entrada | ¿Doc. oficial menciona multi-persona/multi-instancia EN UNA MISMA foto? | Precio (fuente oficial) | Fuente + fecha |
|---|---|---|---|---|---|
| Nano Banana Pro (Gemini 3 Pro Image) edit | `fal-ai/nano-banana-pro/edit` | Hasta 14 (`image_urls`) | **No exactamente** — afirma consistencia de hasta 5 personas, pero al COMPONER fotos separadas en una escena nueva, no al editar personas ya juntas en una foto existente | $0.15/imagen (1K/2K), $0.30 (4K) | blog.google/.../nano-banana-pro; fal.ai/models/fal-ai/nano-banana-pro/edit, 2 sep 2026 |
| Seedream 4.0/4.5 Edit | `fal-ai/bytedance/seedream/v4[.5]/edit`, `bytedance/seedream-v4[.5]/edit` (WaveSpeed) | 1–10 | No — composición cruzada entre imágenes de referencia, no edición multi-persona en una foto | fal.ai v4: $0.03/imagen; WaveSpeed v4.5: $0.04/imagen | fal.ai y wavespeed.ai model pages, 2 sep 2026 |
| Seedream 4.5 Edit Sequential | `bytedance/seedream-v4.5/edit-sequential` | Lote de fotos separadas del mismo sujeto | No — aplica el mismo edit a un LOTE de fotos separadas, no a varias personas dentro de una foto | $0.04 × `max_images` | wavespeed.ai/models/.../edit-sequential, 2 sep 2026 |
| GPT-Image-1/2 edit | `fal-ai/gpt-image-1/edit-image`, `openai/gpt-image-2/edit` | "Lista" sin tope confirmado en fal.ai; "hasta 16" según resumen no verificado de doc oficial OpenAI | No | GPT-Image-2: ej. $0.219 (1024×1024, alta calidad) | fal.ai/models/openai/gpt-image-2/edit, 2 sep 2026 |
| Flux Kontext Pro/Max "multi" (experimental) | `fal-ai/flux-pro/kontext/multi`, `.../max/multi` | Varias (sin tope numérico confirmado) | No — y el proveedor lo marca "experimental" | Pro $0.04/imagen, Max $0.08/imagen | fal.ai model pages, 2 sep 2026 |
| Recraft V3 image-to-image | `fal-ai/recraft/v3/image-to-image` | 1 (no aplica: no tiene campo de imagen de referencia separado) | No — descartado por diseño, no encaja con el flujo de referencia de producto | $0.04/imagen ($0.08 vector) | fal.ai model page, 2 sep 2026 |
| OmniGen v1 | `fal-ai/omnigen-v1` | Varias vía `input_image_urls` | Etiqueta "Multi Person Generation" presente pero sin desarrollo/ejemplo que confirme el caso de uso exacto | $0.10/megapixel | fal.ai/models/fal-ai/omnigen-v1, 2 sep 2026 |
| Easel AI multiplayer | (fal.ai, sin endpoint confirmado en esta investigación) | 2 personas | No aplica — es face/body swap que preserva la ropa, no editor de ropa/calzado | No verificado | blog.fal.ai/.../easel-ai, 2 sep 2026 |
| Virtual try-on (FASHN y similares) | `fal-ai/fashn/tryon/v1.5` | 1 persona + 1 prenda | No | No verificado en esta investigación | fal.ai model page, 2 sep 2026 |

## 5. Qué NO se pudo confirmar

- **El tope exacto de "hasta 16 imágenes" de la API oficial de OpenAI para
  `images.edit`** — el fetch directo a la documentación oficial de OpenAI
  (`platform.openai.com/docs/api-reference/images/createEdit` →
  HTTP 403; `developers.openai.com/api/reference/resources/images/methods/edit`
  → HTTP 404 en el intento directo) no se pudo verificar de primera mano;
  el dato viene de un resumen de búsqueda sobre esa misma página. Antes de
  usarlo para una decisión, habría que reintentar el fetch directo (posible
  bloqueo temporal) o consultar la doc con una cuenta autenticada.
- **Precio exacto de GPT-Image-1 (no -2) edit en fal.ai** — no se llegó a
  fetch directo de esa página específica, solo de GPT-Image-2.
- **Si Nano Banana Pro realmente resuelve el caso de uso de este repo** (2-3
  personas ya en una foto, cambiarles el calzado a todas) — esto requiere
  una prueba en vivo con la foto real de 3 personas, igual que se hizo con
  los 3 modelos actuales documentados en `templates/_comparacion_modelos.html`.
  Esta investigación es solo de documentación oficial, sin ejecutar llamadas
  de API ni comparar salidas reales — por diseño de la tarea.
- **Endpoint exacto y precio de Easel AI "multiplayer"** en fal.ai — el blog
  post no daba la ruta del modelo ni el precio; solo se confirmó el
  comportamiento (face/body swap, no relevante para este caso de uso), así
  que no se profundizó más al quedar descartado por diseño.
- **Precio y tope de imágenes de FASHN virtual try-on** — no se hizo fetch
  directo de la página de modelo, solo resumen de búsqueda; quedó fuera de
  alcance al no encontrarse ninguna mención de soporte multi-persona.
