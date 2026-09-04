# Investigación: en WaveSpeed AI, ¿hay un modelo que además de cambiar el producto SUBA la calidad/realismo de la foto?

Investigado en vivo el **4 sep 2026**, solo contra páginas oficiales de
wavespeed.ai: las páginas de modelo (`wavespeed.ai/models/...`), la referencia
de API (`wavespeed.ai/docs/docs-api/...`), las páginas de colección
(`wavespeed.ai/collections/...`, `wavespeed.ai/image-upscaler-api`,
`wavespeed.ai/video-upscaler-api`) y el sitemap de modelos
(`wavespeed.ai/model-sitemap.xml`, **1 011 modelos** el 4 sep 2026 — se usó para
enumerar el catálogo completo en vez de confiar en lo que muestra la página de
"Explore"). Ningún blog de terceros, agregador ni listicle como fuente de una
capacidad o de un precio.

Todas las páginas de modelo de WaveSpeed llevan al pie esta advertencia, que
aplica a **todos** los precios de este documento:

> "Note: This website uses AI models provided by third parties. Documentation
> prices are for reference and may be outdated. The Generate button shows an
> estimate; the final task charge prevails."

## 0. Punto de partida (lo que ya está conectado en este repo)

Para "cambiar calzado" en **foto**, los 3 modelos conectados hoy
(`templates/_comparacion_modelos.html`, `providers/comparador_modelos.py`,
`providers/nano_banana_client.py`) son:

- **Nano Banana directo** = `gemini-2.5-flash-image` vía la API de Google
  (`generativelanguage.googleapis.com`), **no vía WaveSpeed** — $0.039/imagen.
  El mejor de los 3 en pruebas reales.
- **Nano Banana vía fal.ai** (`fal-ai/nano-banana/edit`) — $0.039/imagen.
- **Qwen Image Edit Plus vía fal.ai** (`fal-ai/qwen-image-edit-plus`) — $0.03/imagen.

**Ninguno de los tres sube resolución ni "mejora" la foto**: los tres devuelven
una imagen del mismo orden de tamaño que la entrada. Hoy **no hay ningún modelo
de imagen de WaveSpeed conectado** — de WaveSpeed solo se usan editores de
*video* (`providers/wavespeed_client.py`, `providers/wavespeed_video_edit.py`).
Eso significa que la clave `WAVESPEED_API_KEY` ya existe y el patrón
encolar+poll de `providers/wavespeed_common.py` ya sirve tal cual para
cualquier modelo de imagen de WaveSpeed, sin infraestructura nueva.

Límite real ya confirmado (2 sep 2026, foto de 3 personas): ninguno de los 3
cambia el calzado de todas las personas de forma confiable.

## 1. Resumen ejecutivo

**Sí existe la forma A (un solo modelo que edita con referencias Y produce
salida de mucha mayor resolución), y es una diferencia real, no de marketing:**

- **`google/nano-banana-pro/edit-ultra`** (Gemini 3.0 Pro Image) acepta **hasta
  14 imágenes de entrada** — o sea, foto a editar + referencias del producto en
  la misma lista, exactamente el patrón que ya usa este repo — y su parámetro
  `resolution` **solo admite `4k` u `8k`** (no hay tier de 1k). Es el único
  modelo de *edición* del catálogo de WaveSpeed que sale a 8K. **$0.15 a 4k,
  $0.18 a 8k.** Es una variante distinta de `google/nano-banana-pro/edit`
  (que va de 1k a 4k, $0.14–$0.24), no el mismo endpoint.

**Y también existe la forma B (segunda pasada), con un matiz importante:** casi
todos los upscalers de WaveSpeed son *generativos* — inventan detalle — y el
propio catálogo lo dice en su texto. Solo dos tienen una afirmación oficial
explícita de que **no** regeneran contenido:

- **`bria/increase-resolution`** — texto oficial exacto: *"upscales images with a
  method that **preserves original content without regeneration**"*. $0.04/run,
  factor fijo 2× o 4×. Es el más seguro para este caso de uso (la foto tiene que
  seguir siendo la misma persona, misma pose, mismo fondo).
- **`wavespeed-ai/real-esrgan`** — *"improves resolution and perceived detail
  **while keeping the original content intact**"*. $0.0024/imagen, el más barato
  del catálogo por dos órdenes de magnitud.

En cambio `wavespeed-ai/ultimate-image-upscaler` se describe a sí mismo como el
que *"**reimagines** fine detail"*, y los Clarity (`pro-upscaler`,
`crystal-upscaler`, `creative-upscaler`, `flux-upscaler`) exponen un parámetro
`creativity` cuyo propósito documentado es *"add more generated detail"* — son
buenos, pero por diseño alucinan si se sube ese parámetro. Detalle en §3.

**Lo que NO se encontró:** ninguna página oficial de WaveSpeed afirma que
alguno de estos modelos edite el mismo objeto en **varias personas** de una
misma foto. Se revisó explícitamente el texto de `nano-banana-pro/edit-ultra`,
`nano-banana-2/edit`, `seedream-v5.0-pro/edit` y `clarity-ai/pro-upscaler`
buscando "people / persons / multiple subjects / each person": **cero
menciones**. El límite multi-persona documentado el 2 sep 2026 sigue sin
resolverse por documentación oficial.

## 2. Forma A — un solo modelo que edita con referencias Y da más calidad

Todos comparten el mismo contrato de WaveSpeed que ya implementa
`providers/wavespeed_common.py`:

```
POST https://api.wavespeed.ai/api/v3/<MODEL_PATH>
  Authorization: Bearer $WAVESPEED_API_KEY
  -> { "code": 200, "data": { "id": "<prediction_id>", "model": ..., "status": ..., "urls": {...} } }
GET  https://api.wavespeed.ai/api/v3/predictions/{id}/result   (poll ~cada 2s)
  -> { "data": { "status": "completed"|"failed"|"cancelled"|"timeout"|"deleted",
                 "outputs": ["https://.../imagen.png"], "error": "", "timings": {...} } }
```

Estados terminales de fallo: `failed`, `cancelled`, `timeout`, `deleted` —
idénticos a los que ya maneja `poll_hasta_listo()`. No hace falta tocar nada de
ese helper.

### 2.1 `google/nano-banana-pro/edit-ultra` — Nano Banana Pro Edit Ultra (Gemini 3.0 Pro Image)

**El candidato principal de esta investigación.**

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/google/nano-banana-pro/edit-ultra`
- **Imágenes de entrada**: **hasta 14**, todas en el mismo array `images`.
  Esquema oficial exacto: `images` · `array<string>` · Required · rango
  *"0 ~ 14 items"* · descripción *"List of URLs of input images for editing. The
  maximum number of images is 14."* **No hay slots separados** para "foto a
  editar" vs. "referencia del producto" — es una lista plana, igual que
  `image_urls` en fal.ai. El orden lo define el prompt (el mismo patrón que ya
  usa `PROMPT_EDICION_IMAGEN` en `providers/comparador_modelos.py`, que dice
  "la primera imagen ... las imágenes de referencia siguientes").
- **Esquema de request completo** (referencia de API oficial):

  | Campo | Tipo | Req. | Default | Rango / valores |
  |---|---|---|---|---|
  | `prompt` | string | Sí | — | *"The positive prompt for the generation."* |
  | `images` | array\<string\> | Sí | — | 0 ~ 14 items |
  | `aspect_ratio` | string | No | — | `1:1`, `3:2`, `2:3`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9` |
  | `resolution` | string | No | `4k` | **`4k`, `8k`** (no existe 1k ni 2k en esta variante) |
  | `output_format` | string | No | `png` | `png`, `jpeg` |
  | `enable_sync_mode` | boolean | No | `false` | — |
  | `enable_base64_output` | boolean | No | `false` | — |

- **Precio verificado** (tabla oficial "💰 Pricing" de la página de modelo, y
  repetida idéntica en la referencia de API):

  | Resolution | Cost per image |
  |---|---|
  | 4k | **$0.15** |
  | 8k | **$0.18** |

  El playground muestra *"$ 0.15 per run · ~ 66 / $ 10"* con los defaults.
- **Qué dice la doc oficial sobre calidad/realismo** (citas literales, sin
  parafrasear):
  - *"Google Nano Banana Pro (Gemini 3.0 Pro Image) Edit enables image editing
    with highres output."*
  - *"Native 4K image generation — Produce crisp, production-ready images with
    fine detail and clean edges."*
  - *"Natural-language, context-aware editing — Modify images using simple text
    instructions. The model understands scene structure, objects, and
    relationships for **realistic edits**."*
  - *"Camera-style controls — Support for camera-related parameters such as
    angle, focus, depth of field, and color adjustment for **more photographic
    results**."* (Ojo: **estos "camera controls" NO aparecen como parámetros en
    el esquema** — solo se pueden pedir por texto en el `prompt`.)
  - *"Consistent character and style rendering — Maintain character identity,
    brand elements, and overall style across related images."*
  - *"Supports style transfer, relighting, background replacement, and **object
    modification**"*.
  - Uno de los ejemplos oficiales de la página es literalmente un swap de
    objeto: *"Swap the fries for green onions."*
  - **Advertencia honesta**: la doc **nunca dice que sea "más realista que una
    edición normal"**. Dice que la salida es de mayor resolución (4k/8k) y que
    las ediciones son "realistic"/"photographic". Es una afirmación de
    resolución + fidelidad de edición, **no** una afirmación de "mejora la foto
    de entrada". Si la foto original es de baja calidad, nada en la doc promete
    que la va a arreglar.
- **Multi-persona**: sin mención alguna en la página (búsqueda explícita de
  "people / person / multiple subjects / each person" → 0 resultados).
- **Video**: **no**. Es image-only. Los modelos de video de la misma familia en
  WaveSpeed son `google/gemini-omni-flash/video-edit` y
  `google/gemini-omni-1.1-flash/video-edit`, **ambos ya descartados** en
  `templates/_comparacion_modelos.html` por no aceptar imagen de referencia del
  producto (solo texto).

Fuentes: [wavespeed.ai/models/google/nano-banana-pro/edit-ultra](https://wavespeed.ai/models/google/nano-banana-pro/edit-ultra),
[wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit-ultra](https://wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit-ultra) — verificadas 4 sep 2026.

### 2.2 `google/nano-banana-pro/edit` — Nano Banana Pro Edit (la variante estándar)

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/google/nano-banana-pro/edit`
- **Imágenes de entrada**: **hasta 14** (`images`, `array<string>`, *"0 ~ 14
  items"*, *"The maximum number of images is 14."*) — idéntico a Edit Ultra.
- **Diferencia real con Edit Ultra**: solo el parámetro `resolution`, que aquí
  es `1k` (default), `2k` o `4k`. Todo lo demás (prompt, images, aspect_ratio,
  output_format, flags) es el mismo esquema.
- **Precio verificado**: 1k **$0.14**, 2k **$0.14**, 4k **$0.24**. Playground:
  *"$ 0.126 per run"*.
  → **A 4k es más caro que Edit Ultra a 4k ($0.24 vs $0.15).** Si el objetivo es
  máxima resolución, Edit Ultra domina en precio a esta variante. Esto se
  verificó en las dos páginas por separado; no es un error de lectura.
- **Texto oficial sobre calidad**: el mismo bloque que Edit Ultra (§2.1) más
  esta comparación de la propia WaveSpeed:
  - *"Original Nano Banana (Gemini 2.5 Flash Image) — Nano Banana Pro Edit
    trades pure speed for quality, delivering better reasoning, sharper text,
    improved character consistency, and richer camera controls at a higher unit
    cost."* ← **Esta es la única afirmación oficial encontrada que compara
    directamente contra el modelo que este repo ya usa** (Gemini 2.5 Flash
    Image). Nótese que habla de "better reasoning / improved character
    consistency", **no** de mejor realismo fotográfico.
  - *"Seedream — Nano Banana Pro Edit is tuned for reliable typography,
    **photo-real edits**, and mixed media layouts, while SeeDream excels at
    fast, stylized T2I generation..."*
  - *"Qwen Image 2509 — Nano Banana Pro Edit focuses on **high-fidelity 4K
    outputs** and multilingual on-image design control..."*
- **Video**: no (image-only).

Fuentes: [wavespeed.ai/models/google/nano-banana-pro/edit](https://wavespeed.ai/models/google/nano-banana-pro/edit),
[wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit](https://wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit) — verificadas 4 sep 2026.

### 2.3 `google/nano-banana-pro/edit-multi` — variante de lote (NO sirve para este caso)

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/google/nano-banana-pro/edit-multi`
- **Imágenes de entrada**: hasta 14 (`images`), igual que las otras dos.
- **Qué hace realmente** — texto oficial: *"Instead of generating a single
  edited image, this endpoint allows you to upload one or more input images and
  produce **multiple edited outputs in one run**."* Es decir, el "multi" son las
  **salidas** (variantes del mismo edit), no las personas ni las referencias.
  El parámetro `num_images` tiene rango documentado *"2 · 2 ~ 2"* — solo 2.
- **Precio verificado**: *"a flat **$0.07 per image**"*.
- **No tiene parámetro `resolution`** (a diferencia de `edit` y `edit-ultra`) —
  o sea, no sirve para el objetivo de más calidad/resolución.
- **Descartado para este caso de uso**: da 2 variantes A/B del mismo edit, que
  no es lo que se pide. Podría ser útil algún día para "generá 2 opciones y que
  el humano elija", que encaja con el flujo de aprobación del repo, pero no
  resuelve calidad ni multi-persona.

Fuente: [wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit-multi](https://wavespeed.ai/docs/docs-api/google/google-nano-banana-pro-edit-multi) — verificada 4 sep 2026.

### 2.4 `google/nano-banana-2/edit` — Nano Banana 2 Edit (Gemini 3.1 Flash Image)

La opción "barata" de la forma A. Es la línea **Flash** (la misma familia que el
`gemini-2.5-flash-image` ya en uso), dos generaciones más nueva.

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/google/nano-banana-2/edit`
- **Imágenes de entrada**: **hasta 14** — *"Multi-image reference — Upload up to
  14 reference images for complex edits and compositions."*; parámetro `images`,
  *"Reference images to edit (max: 14...)"*.
- **Esquema de request** (tabla "Parameters" de la página de modelo):
  `images` (req), `prompt` (req), `aspect_ratio` (opc: `1:1`, `3:2`, `2:3`,
  `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`, `1:4`, `4:1`, `1:8`,
  `8:1`), `resolution` (opc: **`0.5k`, `1k` (default), `2k`, `4k`**),
  `enable_web_search` (opc, default `false`), `enable_image_search` (opc,
  default `false`), `output_format` (opc: `png` default, `jpeg`).
- **Precio verificado** (tabla oficial):

  | Resolution | Cost |
  |---|---|
  | 0.5k | $0.045 |
  | 1k | $0.07 |
  | 2k | $0.105 |
  | **4k** | **$0.14** |
  | Web search | +$0.014 |
  | Image search | +$0.014 |

  Playground: *"$ 0.063 per run"*.
  → **A 4k cuesta $0.14, casi lo mismo que Edit Ultra a 4k ($0.15).**
- **Texto oficial sobre calidad**:
  - *"Google Nano Banana 2 Edit (Gemini 3.1 Flash Image) enables advanced image
    editing with 4K-capable output, fast iteration, and precise instruction
    following. Supports text translation, localization within images, and
    **maintains subject consistency during edits**."*
  - *"**Object Replacement** — Swap elements within images while preserving
    context."* ← descripción literal del caso de uso de este repo.
  - Los ejemplos oficiales de la página son exactamente del tipo que necesita el
    flujo: *"Keep the dancer exactly as-is. Replace background with a neon-lit
    Tokyo street at night... Same camera angle and perspective."*
- **Multi-persona**: la única mención cercana es un consejo de prompting —
  *"...'Change the man to a woman' rather than 'modify the person'"* — que habla
  de una sola persona, no de varias.
- **Video**: no (image-only).

Fuente: [wavespeed.ai/models/google/nano-banana-2/edit](https://wavespeed.ai/models/google/nano-banana-2/edit) — verificada 4 sep 2026.

### 2.5 `bytedance/seedream-v5.0-pro/edit` — Seedream V5.0 Pro Edit

Es el único candidato cuya doc oficial usa la palabra **"photographic realism"**
como característica del modelo, pero su techo de resolución es mucho más bajo.

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/bytedance/seedream-v5.0-pro/edit`
- **Imágenes de entrada**: **hasta 10**. `images` · `array<string>` · Required ·
  *"0 ~ 10 items"* · *"The images to edit. A maximum of 10 reference images can
  be uploaded."* En la página de modelo: *"Multi-image reference editing — Use up
  to 10 reference images for complex edits, compositions, and visual guidance."*
  Lista plana, sin slots separados.
- **Esquema de request completo**:

  | Campo | Tipo | Req. | Default | Rango / valores |
  |---|---|---|---|---|
  | `prompt` | string | Sí | — | — |
  | `images` | array\<string\> | Sí | — | 0 ~ 10 items |
  | `aspect_ratio` | string | No | — | `1:1`, `1:2`, `2:1`, `1:3`, `3:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `9:21`, `21:9`. *"Leave empty to automatically use the closest supported aspect ratio based on the first input image."* ← **resuelve solo el problema de encuadre** que en fal.ai obligó a escribir `providers/aspect_ratio.py` |
  | `resolution` | string | No | `1k` | **`1k`, `1.5k`, `2k`** (tope 2k) |
  | `output_format` | string | No | `jpeg` | `jpeg`, `png` |
  | `prompt_optimization_mode` | string | No | `standard` | `standard`, `fast` |
  | `enable_sync_mode` / `enable_base64_output` | boolean | No | `false` | — |

  Ojo con `prompt_optimization_mode`: *"The model **rewrites your prompt** before
  generating."* Es decir, el prompt cuidadosamente redactado de este repo
  (`PROMPT_EDICION_IMAGEN`) **sería reescrito por el modelo antes de usarse** —
  riesgo real para un prompt que depende de instrucciones muy específicas
  ("ninguna se queda con el original", "no debe sobresalir del contorno del
  pie"). No hay valor documentado para desactivar la reescritura.
- **Precio verificado** (tabla oficial): base por resolución **1k $0.045 ·
  1.5k $0.045 · 2k $0.090**, más *"The first input image is included; each
  additional input image costs **$0.003**."* Ejemplos oficiales: 1k con 10
  imágenes = $0.072; 2k con 10 imágenes = $0.117. Playground: *"$ 0.0405 per run"*.
  → **Es el más barato de la forma A por bastante**, pero tope 2k.
- **Texto oficial sobre calidad/realismo**:
  - *"Seedream V5.0 Pro Edit is a multimodal image editing model built for
    professional work: interactive precision editing, multi-reference control,
    **photographic realism**, and native multilingual text."*
  - *"Pro image quality — Designed for high-quality image editing with strong
    prompt adherence and polished visual output."*
  - *"Character and style guidance — Use reference images to **preserve
    identity**, outfit, mood, or visual style."*
  - El ejemplo oficial de la página es un caso de "mejorá la foto conservando al
    sujeto": *"Transform this image into a premium kitchen appliance commercial.
    Preserve the chef's face, chef jacket, posture, and kitchen composition.
    Upgrade the kitchen into a bright, modern luxury kitchen ... Keep it
    realistic, clean, warm, and trustworthy."*
  - **Advertencia honesta**: "photographic realism" es una descripción del
    *estilo* de salida del modelo, no una promesa de que mejore la calidad de la
    foto de entrada. Y con tope 2k **no aporta resolución** frente a lo que ya
    se tiene.
- **Multi-persona**: sin menciones (0 resultados en la búsqueda explícita).
- **Video**: no directamente. La familia ByteDance sí tiene editor de video
  (`bytedance/seedance-2.5/video-edit`, **ya en uso** en
  `providers/wavespeed_video_edit.py` y marcado como "recomendado por defecto"),
  pero es otro modelo, no un equivalente de Seedream V5 Pro Edit.

Fuentes: [wavespeed.ai/models/bytedance/seedream-v5.0-pro/edit](https://wavespeed.ai/models/bytedance/seedream-v5.0-pro/edit),
[wavespeed.ai/docs/docs-api/bytedance/bytedance-seedream-v5.0-pro-edit](https://wavespeed.ai/docs/docs-api/bytedance/bytedance-seedream-v5.0-pro-edit) — verificadas 4 sep 2026.

### 2.6 Los que la tarea pedía revisar y quedaron fuera

- **Seedream 4.0 / 4.5 Edit** (`bytedance/seedream-v4/edit`,
  `bytedance/seedream-v4.5/edit`, `bytedance/seedream-v4.5/edit-sequential`):
  existen en el catálogo (confirmado en el sitemap, 4 sep 2026) y ya fueron
  investigados a fondo el 2 sep 2026
  (`docs/investigacion/2026-09-02-modelos-edicion-multi-persona.md` §2.2), donde
  quedó documentado que su doc oficial **no** afirma edición multi-persona y que
  `edit-sequential` aplica el mismo edit a un LOTE de fotos separadas.
  **Seedream V5.0 Pro Edit (§2.5) es la versión superior de esa misma línea**
  (más nueva, con "photographic realism" en la descripción y tier 2k), así que
  no tiene sentido volver a 4.x. También existen `seedream-v5.0-lite/edit` y
  `seedream-v5.0-lite/edit-sequential` — variantes *más baratas y más flojas* de
  la misma familia; **redundantes** por la misma lógica con la que el repo
  descartó "Seedance 2.0 / 2.0 Fast / 2.0 Mini".
- **Qwen Image Edit**: el catálogo tiene **13 variantes de edición**
  (`wavespeed-ai/qwen-image/edit`, `/edit-plus`, `/edit-2511`, `/edit-lora`,
  `/edit-plus-lora`, `/edit-multiple-angles`, `/edit-2509-multiple-angles`,
  `/edit-2511-lora`, `wavespeed-ai/qwen-image-2.0/edit`,
  `wavespeed-ai/qwen-image-2.0-pro/edit`, `wavespeed-ai/qwen-image-max/edit`,
  `alibaba/qwen-image-3.0/edit`, `alibaba/qwen-image-3.0-pro/edit` — sitemap,
  4 sep 2026). **No se profundizó en ninguna**: el repo ya probó Qwen Image Edit
  Plus con la foto real de 3 personas y *"no cambió el calzado de nadie"*
  (`templates/_comparacion_modelos.html`), que es el peor resultado de los tres
  conectados. Ninguna página de WaveSpeed revisada afirma que una variante
  posterior de Qwen resuelva realismo o multi-persona; la propia WaveSpeed
  posiciona a Qwen como fuerte en *"document-style rendering"* y ecosistema
  open-source, no en fotorrealismo (cita en §2.2). Reabrir Qwen sin una
  afirmación oficial nueva sería re-recomendar algo ya rechazado con evidencia
  real en contra.
- **FLUX Kontext**: existen 12 variantes en WaveSpeed, **incluidas las `/multi`**
  (`wavespeed-ai/flux-kontext-pro/multi`, `wavespeed-ai/flux-kontext-max/multi`,
  `wavespeed-ai/flux-kontext-dev/multi`, `.../multi-ultra-fast`). Esto **corrige
  de nuevo** el matiz ya señalado el 2 sep 2026: la tabla del repo dice de Flux
  Kontext Pro *"No — solo recibe 1 imagen de entrada"*, y eso es cierto solo del
  endpoint por defecto. **Aun así se mantiene fuera**: fal.ai etiqueta las
  `/multi` como *"Experimental version ... with multi image handling
  capabilities"* (verificado 2 sep 2026) y no se encontró en WaveSpeed ninguna
  afirmación oficial de realismo superior ni de resolución 4k para Kontext. No
  hay razón documentada para preferirlo sobre §2.1–§2.5.
- **Un "photo-realistic edit" o tier "pro" dedicado**: se recorrió el sitemap
  completo (1 011 modelos) buscando `realis|photoreal|photo-real`. El único
  resultado fue `wavespeed-ai/wan-2.2/text-to-image-realism`, que es
  **text-to-image** (genera desde cero, no edita) — no aplica, por la misma
  razón por la que se descartó Higgsfield Soul.

## 3. Forma B — segunda pasada: enhancer / upscaler después del swap

El catálogo oficial declara **10 endpoints de upscale de imagen**
(`wavespeed.ai/image-upscaler-api`, verificado 4 sep 2026). El criterio decisivo
aquí no es el precio sino **si preservan o inventan**: la foto tiene que seguir
siendo la misma persona, misma pose, mismo fondo.

### 3.1 Los que la doc oficial dice que NO regeneran (los seguros)

#### `bria/increase-resolution` — Bria Increase Resolution ⭐

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/bria/increase-resolution`
- **Esquema de request**:

  | Campo | Tipo | Req. | Default | Rango |
  |---|---|---|---|---|
  | `image` | string | Sí | — | *"The URL of the image to erase."* (sic — la descripción oficial dice "erase", claramente un copy-paste de otro modelo; el resto de la página deja claro que es la imagen a escalar) |
  | `desired_increase` | integer | No | `2` | **`2` o `4`** · *"Resolution multiplier. Possible values are 2 or 4. Maximum total area is 8192x8192 pixels"* |
  | `enable_sync_mode` / `enable_base64_output` | boolean | No | `false` | — |

- **Precio verificado**: *"Per run: **$0.04**"*. Playground: *"$ 0.04 per run"*.
- **Afirmación oficial sobre preservación** (la cita que decide todo):
  > *"Bria Increase Resolution **upscales images with a method that preserves
  > original content without regeneration**, producing sharper, higher-quality
  > output."*

  Y en el README: *"Bria Increase Resolution enlarges images by a fixed 2× or 4×
  while **preserving sharp edges, textures, and natural color**."* /
  *"Quality-first — enhances detail while **avoiding over-sharpening or
  halos**."* / *"It's built on **licensed training data for compliant commercial
  use**"* ← relevante porque la salida de este repo se publica comercialmente.
- **Límite duro documentado**: *"maximum total area 8192×8192 px"*. Con 4× eso
  significa que la entrada no puede pasar de ~2048×2048 (4 MP). Con una foto de
  celular vertical típica hay que usar 2× o reducir antes.
- **Advertencia oficial de encaje**: *"This model is best suited for images that
  are **already reasonably sharp and clean**, and need additional resolution.
  For extremely blurry or heavily compressed sources, consider using
  ultimate-image-upscaler."* ← Esto encaja perfecto con el caso de uso: la
  salida de un editor como Nano Banana **ya es limpia**, solo le falta tamaño.
- **Video**: existe un equivalente de la misma marca, `bria/fibo/video-upscaler`
  (en la colección oficial de video upscalers), pero **no se verificó su esquema
  ni su precio** en esta investigación.

Fuentes: [wavespeed.ai/models/bria/increase-resolution](https://wavespeed.ai/models/bria/increase-resolution),
[wavespeed.ai/docs/docs-api/bria/bria-increase-resolution](https://wavespeed.ai/docs/docs-api/bria/bria-increase-resolution) — verificadas 4 sep 2026.

#### `wavespeed-ai/real-esrgan` — Real-ESRGAN

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/wavespeed-ai/real-esrgan`
- **Precio verificado**: tabla oficial — *"Per upscaled image **$0.0024**"*.
  Playground: *"$ 0.0024 per run · ~ 416 / $ 1"*. **Es, por lejos, el más barato
  del catálogo** (~60× más barato que el swap mismo).
- **Afirmación oficial sobre preservación**:
  > *"Real-ESRGAN is an image upscaling and enhancement model that improves
  > resolution and perceived detail **while keeping the original content
  > intact**."*

  Y: *"It's commonly used as a **final polish step** for portraits, product
  photos, and AI-generated images."* / *"Upscale **AI-generated images** before
  posting or printing"* ← el caso de uso literal de este repo.
- **⚠️ Discrepancia de esquema — verificar antes de escribir código.** La
  referencia de API oficial lista **un solo parámetro**: `image` (string,
  requerido). Pero (a) la descripción del modelo promete *"optional face
  correction and adjustable upscale factors"*, y (b) en el historial de ejemplos
  incrustado en la propia página de modelo el payload real enviado fue
  `{"image": ..., "face_enhance": false, "guidance_scale": 4}`. **O sea:
  `face_enhance` y `guidance_scale` existen de verdad pero no están
  documentados.** Este es exactamente el mismo tipo de mentira de documentación
  que ya se documentó para Wan 2.7 Video Edit en
  `providers/wavespeed_client.py` (dice "1–9 imágenes", la API rechaza más de 3).
  **No confiar en ninguno de los dos lados sin una llamada real.** `face_enhance`
  importaría mucho aquí: en una foto con personas, un restaurador de caras puede
  cambiar sutilmente los rasgos — que es justo lo que no se quiere.
- **Advertencia oficial**: *"If the source is extremely blurry, expect
  improvement but not full recovery of lost detail"*.
- **Video**: no.

Fuentes: [wavespeed.ai/models/wavespeed-ai/real-esrgan](https://wavespeed.ai/models/wavespeed-ai/real-esrgan),
[wavespeed.ai/docs/docs-api/wavespeed-ai/real-esrgan](https://wavespeed.ai/docs/docs-api/wavespeed-ai/real-esrgan) — verificadas 4 sep 2026.

### 3.2 Los Clarity AI — potentes, pero alucinan por diseño (parámetro `creativity`)

Los cuatro comparten el mismo patrón: `image` + `target_megapixels` +
`creativity`. **El parámetro `creativity` es literalmente el control de cuánto
detalle se inventa**, así que la seguridad depende de configurarlo bien.

#### `clarity-ai/pro-upscaler` — Clarity AI Pro Upscaler

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/clarity-ai/pro-upscaler`
- **Esquema de request**:

  | Campo | Tipo | Req. | Default | Rango |
  |---|---|---|---|---|
  | `image` | string | Sí | — | *"Input image to upscale."* |
  | `target_megapixels` | number | No | `4` | **1 ~ 64** MP |
  | `creativity` | number | No | `0` | **−10 ~ 10** · *"Negative values stay stricter to the source; positive values add more generated detail."* |

- **Precio verificado**: *"Rate: **$0.03 per target megapixel**"*, lineal. Tabla
  oficial de ejemplos: 4 MP $0.12 · 8 MP $0.24 · 16 MP $0.48 · 64 MP $1.92.
  *"creativity does not affect pricing"*. Playground: *"$ 0.03 per run"* (precio
  base; escala con `target_megapixels`).
- **Afirmación oficial sobre identidad y realismo** (la más fuerte del catálogo):
  > *"Clarity Pro Upscaler is a **photorealistic** image upscaler from Clarity AI
  > with **identity preservation**, creative detail control, and up to 16x
  > scaling."*

  Y en la colección oficial: *"clarity-ai/pro-upscaler delivers up to 16×
  photorealistic super-resolution with identity preservation and creative detail
  control — the highest scale factor in the collection. Useful for portraits,
  archival film stills, and source material that needs **aggressive enlargement
  without losing subject identity**."*
- **Cómo NO alucinar**: el propio "Pro Tips" oficial lo dice — *"**Keep
  creativity lower when identity, structure, or product accuracy matters
  most.**"* y *"Use creativity to balance stricter source preservation against
  stronger generated detail."* Para este caso de uso habría que usar
  `creativity` en 0 o negativo, siempre.
- **Video**: sí, existe `clarity-ai/crystal-video-upscaler` (ver §3.5), pero es
  la línea "crystal", no "pro".

Fuentes: [wavespeed.ai/models/clarity-ai/pro-upscaler](https://wavespeed.ai/models/clarity-ai/pro-upscaler),
[wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-pro-upscaler](https://wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-pro-upscaler) — verificadas 4 sep 2026.

#### `clarity-ai/crystal-upscaler`

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/clarity-ai/crystal-upscaler`
- **Esquema**: `image` (req) · `target_megapixels` (number, default `4`,
  **1 ~ 1500** MP) · `creativity` (number, default `0`, **0 ~ 10** — *"Crystal
  supports values from 0 to 10; higher values add more generated detail."*
  **Ojo: aquí no hay valores negativos**, a diferencia de pro-upscaler, así que
  no se puede pedir "más fiel que el default").
- **Precio verificado** (tiers, no lineal): ≤4 MP **$0.05** · >4–16 MP $0.20 ·
  >16–36 MP $0.80 · >36–100 MP $1.60 · >100–400 MP $6.40 · >400 MP $24.00.
  Playground: *"$ 0.03 per run"* (base).
- **Texto oficial**: *"Clarity AI Crystal Upscaler boosts image resolution with
  AI upscaling and **adjustable detail for portraits and landscapes**."* Sin
  afirmación de identity preservation.

Fuentes: [wavespeed.ai/models/clarity-ai/crystal-upscaler](https://wavespeed.ai/models/clarity-ai/crystal-upscaler),
[wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-crystal-upscaler](https://wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-crystal-upscaler) — verificadas 4 sep 2026.

#### `clarity-ai/creative-upscaler`

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/clarity-ai/creative-upscaler`
- **Esquema**: `image` (req) · `target_megapixels` (default `4`, 1 ~ 64) ·
  `creativity` (default `0`, **−10 ~ 10**).
- **Precio verificado** (tiers): ≤4 MP **$0.05** · >4–8 MP $0.10 · >8–16 MP $0.20 ·
  >16–25 MP $0.40 · >25–50 MP $0.80 · >50 MP $1.60.
- **Texto oficial**: *"Creative Upscaler enlarges images with style and detail
  control, restoring photos or **adding micro-textures** for portraits and
  anime."* / *"useful for both faithful restoration and more **stylized creative
  upscaling**"*. El nombre y el texto lo delatan: está pensado para agregar, no
  para preservar. Pro tip oficial: *"Keep creativity low when structure accuracy
  and source fidelity matter most."*

Fuentes: [wavespeed.ai/models/clarity-ai/creative-upscaler](https://wavespeed.ai/models/clarity-ai/creative-upscaler),
[wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-creative-upscaler](https://wavespeed.ai/docs/docs-api/clarity-ai/clarity-ai-creative-upscaler) — verificadas 4 sep 2026.

#### `clarity-ai/flux-upscaler` — el único guiable por prompt

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/clarity-ai/flux-upscaler`
- **Esquema**: `image` (req) · `target_megapixels` (opc) · **`prompt`** (opc —
  *"Optional prompt to guide tone, texture, lighting, or visual refinement."*) ·
  **`lora_link`** (opc) · `creativity` (opc).
- **Precio verificado** (tiers): ≤4 MP **$0.20** · >4–8 MP $0.40 · >8–16 MP $0.60 ·
  >16–25 MP $1.20 · >25–50 MP $2.40 · >50 MP $3.20. *"prompt, lora_link, and
  creativity do not affect pricing."* **Es el upscaler más caro del catálogo.**
- **Texto oficial**: *"Clarity AI Flux Upscaler **sharpens images while
  preserving natural textures and edges**, with prompt-guided refinement and
  LoRA support."* Caso de uso oficial: *"Fashion and portrait enhancement —
  Improve detail while **preserving skin tones, fabrics, and visual polish**."*
  Prompt de ejemplo oficial: *"Elegant editorial texture, soft natural light,
  refined fabric detail, **realistic skin tones**, premium fashion photography
  look."*
- **Por qué es interesante pese al precio**: es el único que dejaría empujar
  explícitamente hacia "más realista" con texto, y su ejemplo oficial es
  literalmente moda/retrato. **Pero** es 5× el precio de la alternativa segura y
  su `prompt` es otra superficie por la que el modelo puede inventar. No es el
  primer paso razonable.

Fuente: [wavespeed.ai/models/clarity-ai/flux-upscaler](https://wavespeed.ai/models/clarity-ai/flux-upscaler) — verificada 4 sep 2026.

### 3.3 Los genéricos de WaveSpeed (`target_resolution` en tiers 2k/4k/8k)

Los tres comparten esquema: `image` (req) · `target_resolution` (`2k`/`4k`/`8k`)
· `output_format` (`jpeg`/`png`/`webp`) · `enable_base64_output` ·
`enable_sync_mode`. Y comparten **exactamente el mismo README**, palabra por
palabra — lo cual es en sí mismo una señal de que el texto de marketing no
distingue realmente entre ellos:

> *"...intelligently increases image resolution while **preserving details,
> sharpness, and natural texture**. It uses advanced deep learning upscaling to
> restore fine features and eliminate blur or compression artifacts."*
> *"Detail Preservation — **Retains texture and structure without introducing
> artifacts or noise**."*

| Modelo | Endpoint | Precio verificado | Texto que lo diferencia |
|---|---|---|---|
| Image Upscaler | `wavespeed-ai/image-upscaler` | *"Every run only for **$0.01**"* | El default barato. WaveSpeed lo llama *"the default 2×/4× post-process pass to push generations to delivery resolution"* |
| Ultimate Image Upscaler | `wavespeed-ai/ultimate-image-upscaler` | *"Every run only for **$0.06**"* | ⚠️ *"the most advanced AI enhancer that **reimagines fine detail** while upscaling images to 4K or 8K"* — "reimagines" es una bandera roja explícita para este caso de uso |
| SeedVR2 Image | `wavespeed-ai/seedvr2/image` | *"Every run only for **$0.01**"* | *"SeedVR2 Image Upscaler boosts image resolution and quality, upscaling photos to 4K or 8K for sharp, detailed results."* |

Nota: los tres dicen *"Every run only for $X"* como precio plano, pero el
playground los describe como precio base que *"scales based on output
parameters"*. **El precio real a 8k no está publicado en tabla → no verificado.**

Fuentes: [wavespeed.ai/models/wavespeed-ai/image-upscaler](https://wavespeed.ai/models/wavespeed-ai/image-upscaler),
[wavespeed.ai/models/wavespeed-ai/ultimate-image-upscaler](https://wavespeed.ai/models/wavespeed-ai/ultimate-image-upscaler),
[wavespeed.ai/models/wavespeed-ai/seedvr2/image](https://wavespeed.ai/models/wavespeed-ai/seedvr2/image),
[wavespeed.ai/image-upscaler-api](https://wavespeed.ai/image-upscaler-api) — verificadas 4 sep 2026.

### 3.4 `wavespeed-ai/phota/enhance` — Phota Enhance

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/wavespeed-ai/phota/enhance`
- **Esquema**: `image` (req) · `num_images` (opc, default 1 — *"Supports batch
  enhancement up to 4 images"*) · `output_format` (`jpeg`/`png`/`webp`) ·
  `enable_base64_output` · `enable_sync_mode`.
- **Precio verificado** (tabla oficial): Standard **$0.09/imagen**, 4K
  **$0.18/imagen**; *"Total cost = cost per image × num_images"*.
- **Texto oficial**: *"Phota Enhance improves image quality and detail."* /
  *"recovers fine textures, sharp edges, and lost detail from low-quality or
  compressed source images"* / *"**Photo Restoration** — Recover detail and
  clarity from old, faded, or damaged photographs."*
- **Sin afirmación de preservación de identidad ni de no-alucinación.** Y su
  caso de uso principal declarado es *fotos viejas/dañadas/comprimidas*, no la
  salida limpia de un editor.

Fuente: [wavespeed.ai/models/wavespeed-ai/phota/enhance](https://wavespeed.ai/models/wavespeed-ai/phota/enhance) — verificada 4 sep 2026.

### 3.5 Topaz y los restauradores — revisados y NO aplican

La tarea mencionaba "Topaz-style". **Topaz sí está en WaveSpeed**, con 4 modelos
(`topaz/image/denoise`, `topaz/image/lighting`, `topaz/image/restore`,
`topaz/image/sharpen` — sitemap, 4 sep 2026). **No hay un `topaz/image/upscale`.**

- **`topaz/image/restore`** — *"Topaz Image Restore enhances older and poorer
  quality photos through restoration. **Remove dust, scratches, and damage from
  vintage photos**."* Esquema: `image` (req) · `model` (opc, default
  `Dust-Scratch V2`) · `output_format`. Precio verificado: *"Per 24 input
  megapixels (rounded up) **$0.096**"*, mínimo $0.096.
  **No aplica**: la doc lo restringe explícitamente — *"This model is optimized
  for dust and scratch removal, not for colorization or major damage repair."*
  Una foto de celular recién editada no tiene polvo ni rayones.
- **`topaz/image/sharpen`** — *"brings clarity and crisp definition to soft or
  out-of-focus images"*. Esquema: `image` (req) · `model` (opc, default
  `Standard`) · `output_format`. Ocho modelos disponibles, incluido
  **`Portrait` — *"Optimized for skin, hair, and facial features"*** y
  **`Natural` — *"Subtle, natural-looking sharpening"***. Precio verificado:
  *"Per 24 input megapixels (rounded up) **$0.096**"*, mínimo $0.096.
  **Parcialmente aplicable**: sirve como pulido final si la salida del swap sale
  blanda, pero **no sube resolución**, y a $0.096 cuesta más del doble que
  `bria/increase-resolution`, que sí escala. No es el primer paso.
- **`bria/fibo/restore`** — *"Bria Restore renews old photos by removing noise,
  scratches, and blur."* Esquema: solo `image` (req). Precio verificado:
  *"Per image **$0.04**"*. **No aplica** por la misma razón que Topaz Restore:
  está hecho para *"vintage photo"*, *"age-related degradation"*.

Fuentes: [wavespeed.ai/models/topaz/image/restore](https://wavespeed.ai/models/topaz/image/restore),
[wavespeed.ai/models/topaz/image/sharpen](https://wavespeed.ai/models/topaz/image/sharpen),
[wavespeed.ai/models/bria/fibo/restore](https://wavespeed.ai/models/bria/fibo/restore) — verificadas 4 sep 2026.

### 3.6 Los que no se investigaron a fondo

Del listado oficial de 10 upscalers de imagen quedaron sin fetch directo:
`pruna-ai/p-image/upscale` (*"from $0.005"*), `recraft-ai/recraft-crisp-upscale`
(*"from $0.004"*, *"enhances textures, fine details, and facial features"*) y
`recraft-ai/recraft-creative-upscale` (*"from $0.25"*, y su propia descripción
avisa *"**not increasing resolution**"* — o sea, no sirve para el objetivo).
Precios tomados de la página de colección
[wavespeed.ai/image-upscaler-api](https://wavespeed.ai/image-upscaler-api),
verificada 4 sep 2026; **esquemas no verificados**. Ninguno tiene afirmación de
preservación de identidad que supere a §3.1, así que no se profundizó.

## 4. ¿Existe equivalente para video?

Sí, y es una colección aparte: **8 endpoints de video upscale**
(`wavespeed.ai/video-upscaler-api`, verificado 4 sep 2026) —
*"Eight video super-resolution endpoints from five providers — WaveSpeedAI
(Standard, Pro, Ultimate, SeedVR2, LTX-2 19B), ByteDance, Bria, and Clarity AI"*.
Precios "desde" de esa página: Video Upscaler *"from $0.025"*, Video Upscaler Pro
*"from $0.20"*, Ultimate Video Upscaler *"from $0.15"*, LTX-2 19B Video Upscaler
*"from $0.15"*, SeedVR2 Video *"from $0.10"*.

El mejor documentado para preservar movimiento (lo crítico si se aplica después
de un `video-edit` de los que ya usa el repo):

**`wavespeed-ai/seedvr2/video`** — `POST https://api.wavespeed.ai/api/v3/wavespeed-ai/seedvr2/video`

- Texto oficial: *"This is the most advanced video upscaler in the world,
  delivering the highest output quality and **exceptional frame-to-frame
  consistency**."* / *"**Temporal consistency**: minimizes flicker and ghosting
  across frames for stable motion."* / *"Detail reconstruction: restores fine
  textures (hair, fabric, foliage) and sharp edges **without over-sharpening**."*
  / *"**Natural look**: balances perceptual quality with crispness to **avoid
  plastic or overprocessed outputs**."*
- **Precio verificado** (tabla oficial, por 5 segundos): 720p **$0.10** · 1080p
  **$0.20** · 2K **$0.25** · 4K **$0.30**. Reglas: *"The minimum billed duration
  is 3 seconds"*, *"Per-second rate = (price per 5 seconds) ÷ 5"*, duración
  redondeada hacia arriba. Ejemplo oficial: *"12s @ 1080p → 12 × $0.04 = $0.48"*.
- **Límites**: *"Max clip length per job: up to 10 minutes"*; *"approximately
  10–30 seconds of wall time to process 1 second of video"* ← **un clip de 10s
  tarda 100–300s**, comparable a los ~383s de Wan 2.7 Video Edit que ya se
  documentan en `providers/wavespeed_client.py`.

**`clarity-ai/crystal-video-upscaler`** — `POST https://api.wavespeed.ai/api/v3/clarity-ai/crystal-video-upscaler`.
Esquema: `video` (req) · `target_megapixels` (opc). Precio verificado:
*"Standard rate is $0.10 × target_megapixels × video duration (seconds)"*, con
mínimo $0.10. **Mucho más caro que SeedVR2 en la práctica**: 10s a 2 MP = $2.00,
donde SeedVR2 a 1080p/10s = $0.40.

Fuentes: [wavespeed.ai/models/wavespeed-ai/seedvr2/video](https://wavespeed.ai/models/wavespeed-ai/seedvr2/video),
[wavespeed.ai/models/clarity-ai/crystal-video-upscaler](https://wavespeed.ai/models/clarity-ai/crystal-video-upscaler),
[wavespeed.ai/video-upscaler-api](https://wavespeed.ai/video-upscaler-api) — verificadas 4 sep 2026.

**Sobre la forma A en video**: no existe. Ninguno de los editores de video ya
conectados (`bytedance/seedance-2.5/video-edit`,
`kwaivgi/kling-video-o3-pro/video-edit`, `alibaba/wan-2.7/video-edit`,
`luma/ray-3.2/video-edit`) tiene una variante "ultra"/4k documentada que además
suba calidad. Para video, la única ruta es la forma B: editar y después escalar.

## 5. Multi-persona: qué dice la documentación oficial (nada)

Se buscó explícitamente (`people`, `person`, `persons`, `multiple subjects`,
`each person`, `multi-person`, `subjects`) en el texto completo de las páginas de
`google/nano-banana-pro/edit-ultra`, `google/nano-banana-2/edit`,
`bytedance/seedream-v5.0-pro/edit` y `clarity-ai/pro-upscaler`, el 4 sep 2026.

**Resultado: cero afirmaciones relevantes.** La única coincidencia fue un consejo
de prompting en Nano Banana 2 Edit — *"'Change the man to a woman' rather than
'modify the person'"* — que habla de **una** persona.

Esto **confirma y no contradice** la conclusión del 2 sep 2026: sigue sin haber
ninguna fuente oficial que afirme la capacidad de editar el mismo objeto en
varias personas ya presentes en una misma foto. Lo más cercano sigue siendo la
afirmación de Google (blog oficial, no WaveSpeed) sobre consistencia de hasta 5
personas **al componer fotos separadas**, ya documentada y ya matizada en
`docs/investigacion/2026-09-02-modelos-edicion-multi-persona.md` §2.1. **Ningún
modelo de este documento se puede recomendar por multi-persona.**

## 6. Tabla comparativa

### Forma A — edición con referencias + más calidad/resolución

| Modelo | MODEL_PATH | Imágenes entrada | Resolución | Precio verificado | Afirmación de calidad (literal) | Video |
|---|---|---|---|---|---|---|
| **Nano Banana Pro Edit Ultra** | `google/nano-banana-pro/edit-ultra` | hasta 14 (`images`, lista plana) | **4k / 8k** | **4k $0.15 · 8k $0.18** | *"highres output"*, *"Native 4K image generation"*, *"realistic edits"* | No |
| Nano Banana Pro Edit | `google/nano-banana-pro/edit` | hasta 14 | 1k / 2k / 4k | 1k $0.14 · 2k $0.14 · 4k $0.24 | *"photo-real edits"*, *"high-fidelity 4K outputs"* | No |
| Nano Banana 2 Edit | `google/nano-banana-2/edit` | hasta 14 | 0.5k / 1k / 2k / 4k | 0.5k $0.045 · 1k $0.07 · 2k $0.105 · 4k $0.14 | *"maintains subject consistency during edits"*, *"Object Replacement — Swap elements ... while preserving context"* | No |
| Seedream V5.0 Pro Edit | `bytedance/seedream-v5.0-pro/edit` | hasta 10 (`images`) | 1k / 1.5k / 2k | 1k–1.5k $0.045 · 2k $0.090 (+$0.003 por imagen extra) | *"photographic realism"*, *"preserve identity, outfit, mood"* | No |
| Nano Banana Pro Edit Multi | `google/nano-banana-pro/edit-multi` | hasta 14 | sin parámetro `resolution` | $0.07/imagen (`num_images` 2~2) | *"multiple edited outputs in one run"* — variantes, no calidad | No |

### Forma B — segunda pasada (enhancer/upscaler)

| Modelo | MODEL_PATH | Esquema clave | Precio verificado | ¿Preserva o inventa? (literal) |
|---|---|---|---|---|
| **Bria Increase Resolution** | `bria/increase-resolution` | `image`, `desired_increase` (2\|4); máx. 8192×8192 px | **$0.04/run** | ✅ *"preserves original content **without regeneration**"* |
| **Real-ESRGAN** | `wavespeed-ai/real-esrgan` | `image` (doc); `face_enhance`+`guidance_scale` existen pero **sin documentar** | **$0.0024/imagen** | ✅ *"keeping the original content intact"* |
| Clarity Pro Upscaler | `clarity-ai/pro-upscaler` | `image`, `target_megapixels` (1–64), `creativity` (−10…10) | $0.03/MP → 4 MP $0.12 | ⚠️ *"photorealistic ... with **identity preservation**"* pero *"positive values add more generated detail"* |
| Clarity Crystal Upscaler | `clarity-ai/crystal-upscaler` | `image`, `target_megapixels` (1–1500), `creativity` (**0…10**, sin negativos) | ≤4 MP $0.05 · >4–16 MP $0.20 · … · >400 MP $24.00 | ⚠️ sin afirmación de preservación |
| Clarity Creative Upscaler | `clarity-ai/creative-upscaler` | `image`, `target_megapixels` (1–64), `creativity` (−10…10) | ≤4 MP $0.05 · >4–8 $0.10 · … · >50 MP $1.60 | ❌ *"adding micro-textures"*, *"stylized creative upscaling"* |
| Clarity Flux Upscaler | `clarity-ai/flux-upscaler` | `image`, `target_megapixels`, **`prompt`**, `lora_link`, `creativity` | ≤4 MP $0.20 · … · >50 MP $3.20 | ⚠️ *"preserving natural textures and edges"* + guiable por prompt |
| Image Upscaler | `wavespeed-ai/image-upscaler` | `image`, `target_resolution` (2k/4k/8k), `output_format` | *"$0.01"* base (escala: no verificado) | ⚠️ *"without introducing artifacts or noise"* |
| Ultimate Image Upscaler | `wavespeed-ai/ultimate-image-upscaler` | idem | *"$0.06"* base (escala: no verificado) | ❌ *"**reimagines** fine detail"* |
| SeedVR2 Image | `wavespeed-ai/seedvr2/image` | idem | *"$0.01"* base (escala: no verificado) | ⚠️ mismo README genérico |
| Phota Enhance | `wavespeed-ai/phota/enhance` | `image`, `num_images` (≤4), `output_format` | Standard $0.09 · 4K $0.18 por imagen | ⚠️ pensado para fotos viejas/comprimidas |
| Topaz Image Sharpen | `topaz/image/sharpen` | `image`, `model` (8 opciones, incl. `Portrait`, `Natural`), `output_format` | $0.096 / 24 MP de entrada | ⚠️ solo afila, **no escala** |
| Topaz Image Restore | `topaz/image/restore` | `image`, `model` (`Dust-Scratch V2`), `output_format` | $0.096 / 24 MP de entrada | ❌ no aplica (polvo/rayones de foto vintage) |
| Bria Fibo Restore | `bria/fibo/restore` | `image` | $0.04/imagen | ❌ no aplica (foto vintage) |
| SeedVR2 Video | `wavespeed-ai/seedvr2/video` | video; ≤10 min | 720p $0.10 · 1080p $0.20 · 2K $0.25 · 4K $0.30 **por 5s** (mín. 3s) | ✅ *"temporal consistency"*, *"avoid plastic or overprocessed outputs"* |
| Crystal Video Upscaler | `clarity-ai/crystal-video-upscaler` | `video`, `target_megapixels` | $0.10 × MP × seg (mín. $0.10) | ⚠️ sin afirmación de preservación |

## 7. Recomendación

**Cablear primero: `bria/increase-resolution` como segunda pasada opcional
después del swap actual — NO reemplazar el modelo de swap todavía.**

- **Endpoint**: `POST https://api.wavespeed.ai/api/v3/bria/increase-resolution`
- **Precio**: **$0.04 por run** (verificado, tabla oficial, 4 sep 2026)
- **Payload**: `{"image": <url_del_swap>, "desired_increase": 2}` (usar `4` solo
  si el resultado del swap cabe en 8192×8192 al escalar)

**Por qué esta y no otra:**

1. **Es la única cuya doc oficial afirma que no regenera**: *"preserves original
   content **without regeneration**"*. Todo el punto del flujo es que la foto
   siga siendo la misma persona, misma pose, mismo fondo — cualquier upscaler
   generativo (los Clarity con `creativity`, el `ultimate` que *"reimagines fine
   detail"*) pone eso en riesgo justamente en la cara de la persona.
2. **No toca lo que ya funciona.** Nano Banana directo es hoy el mejor de los
   3 conectados en pruebas reales; una segunda pasada no cambia ese resultado,
   solo lo entrega más grande y nítido. Y encaja con el diseño del repo: es un
   paso más que el humano puede aprobar o saltar, sin arriesgar el swap ya
   aprobado.
3. **Es barato y acotado**: $0.04 sobre un swap de $0.039 — el costo por foto no
   llega a duplicarse, y el paso es opcional. Si el resultado no gusta, se
   descarta y queda el swap original intacto (el mismo patrón de rechazo que ya
   usa todo el pipeline).
4. **La propia UI de WaveSpeed sugiere ese encadenamiento**: cada página de
   modelo de edición muestra un chip *"Next: Upscale"* apuntando a la colección
   de upscalers. Editar y después escalar es el flujo que el proveedor mismo
   propone, no una invención de esta investigación.

**Alternativa aún más barata a probar en la misma pasada**:
`wavespeed-ai/real-esrgan` a **$0.0024/imagen** — misma promesa de preservación
(*"keeping the original content intact"*) y su caso de uso oficial es literal
(*"Upscale AI-generated images before posting or printing"*). Pero tiene la
discrepancia de esquema documentada en §3.1 (`face_enhance`/`guidance_scale`
existen pero no están en la referencia oficial), así que hay que verificarlo con
una llamada real antes de confiar en él — y `face_enhance` es exactamente el
tipo de parámetro que podría alterar la cara de una persona.

**El segundo paso, después y por separado: probar
`google/nano-banana-pro/edit-ultra` ($0.15 a 4k) como modelo de swap.**

Es la mejor opción de la forma A y **no re-recomienda nada descartado**: en
`templates/_comparacion_modelos.html` los descartes de imagen son Flux Kontext
Pro (1 sola imagen) y Higgsfield Soul (generativo, no editor) — Edit Ultra no es
ninguno de los dos: acepta 14 imágenes y es un editor. La investigación del
2 sep 2026 ya había señalado Nano Banana Pro como "la prueba de siguiente paso
más razonable" pero vía fal.ai a $0.15/imagen (1K–2K); **este hallazgo mejora eso
en concreto: por el mismo precio, vía WaveSpeed, sale a 4K**, y a 8K por $0.18.

Pero hay que ser honesto sobre lo que esto sí y no resuelve:

- ✅ **Sí resuelve resolución**: 4k/8k nativo desde el editor, sin segunda pasada.
- ❓ **No hay evidencia oficial de que sea "más realista"**. La doc dice
  *"realistic edits"* y *"photographic results"*, pero nunca afirma mejorar la
  foto de entrada. Presentarlo como "hace la foto más realista" sería inflar la
  afirmación.
- ❌ **No resuelve multi-persona** (§5). Si el problema real que molesta es que
  con 3 personas no cambia el calzado de todas, **esto no lo arregla**, y no hay
  ninguna fuente oficial que diga lo contrario.
- ⚠️ **Requiere prueba en vivo con la misma foto real de 3 personas** antes de
  entrar a la lista, igual que se hizo con los 3 modelos actuales. Esta
  investigación es solo de documentación oficial.

**Lo que NO recomiendo, explícitamente:**

- **No reemplazar Nano Banana directo por Seedream V5.0 Pro Edit** aunque sea el
  único con "photographic realism" en la doc y el más barato ($0.045): tope 2k
  (no aporta resolución) y su `prompt_optimization_mode` **reescribe el prompt
  antes de generar**, sin forma documentada de desactivarlo — el prompt de este
  repo es demasiado específico como para dejar que un modelo lo reescriba.
- **No usar `wavespeed-ai/ultimate-image-upscaler`** pese a ser "el más
  avanzado": *"reimagines fine detail"* es lo contrario de lo que se necesita.
- **No usar los Clarity como primera opción** pese a que `pro-upscaler` tiene la
  mejor frase de marketing del catálogo (*"photorealistic ... identity
  preservation"*): son buenos, pero su parámetro `creativity` significa que la
  seguridad depende de configurarlo bien, y a 4 MP cuesta $0.12 (3× Bria) por
  una garantía más débil. Si Bria no alcanza, `clarity-ai/pro-upscaler` con
  `creativity` en negativo es el siguiente a probar.
- **No tocar los Topaz ni los "restore"**: su doc oficial los limita a fotos
  vintage con polvo, rayones y desvanecimiento — nada que ver con este flujo.

## 8. Qué NO se pudo confirmar

- **El precio real a 4k/8k de `wavespeed-ai/image-upscaler`,
  `ultimate-image-upscaler` y `seedvr2/image`.** Las tres páginas solo publican
  *"Every run only for $X"* ($0.01/$0.06/$0.01), pero el playground los describe
  como precio base que *"scales based on output parameters"*. **No hay tabla
  por resolución.** El precio real de un 8k queda **no verificado**.
- **El esquema real de `wavespeed-ai/real-esrgan`.** La referencia de API lista
  solo `image`; la descripción promete *"optional face correction and adjustable
  upscale factors"*; el historial de ejemplos de la propia página muestra
  `face_enhance` y `guidance_scale`. Se contradicen. Sin llamada real no se
  puede saber cuál manda (mismo caso que Wan 2.7 y su límite de 3 imágenes).
- **Si `google/nano-banana-pro/edit-ultra` realmente da mejor resultado que
  `gemini-2.5-flash-image` en la foto real de este repo.** Requiere prueba en
  vivo; no se ejecutó ninguna llamada de API en esta investigación, por diseño
  de la tarea.
- **Si el 8k de Edit Ultra es realmente nativo o un upscale interno.** La doc
  dice *"Native 4K image generation"* pero **no** dice "native 8K" — el tier
  `8k` existe en el esquema sin una afirmación de nativo detrás. No inferir.
- **Esquemas y precios de `pruna-ai/p-image/upscale`,
  `recraft-ai/recraft-crisp-upscale` y `recraft-ai/recraft-creative-upscale`** —
  solo se tomaron sus precios "desde" de la página de colección; sin fetch
  directo de la página de modelo.
- **Los 8 endpoints de video upscale en detalle.** Solo se verificaron a fondo
  `wavespeed-ai/seedvr2/video` y `clarity-ai/crystal-video-upscaler`. Los otros
  seis (`wavespeed-ai/video-upscaler`, `video-upscaler-pro`,
  `ultimate-video-upscaler`, `ltx-2-19b/video-upscaler`,
  `bytedance/video-upscaler`, `bria/fibo/video-upscaler`, más
  `black-forest-labs/flux-3/video-upscale`) quedaron con solo su precio "desde".
- **Las 13 variantes de Qwen Image Edit y las 12 de FLUX Kontext** del catálogo
  (§2.6): se enumeraron desde el sitemap pero no se hizo fetch de sus páginas,
  por las razones explicadas ahí. Si alguna vez se reabre Qwen o Kontext, hay que
  verificarlas una por una.
