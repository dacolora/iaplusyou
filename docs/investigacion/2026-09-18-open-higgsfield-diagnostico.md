# Investigación: ¿qué nos podemos traer de open-higgsfield para mejorar la creación de videos? Diagnóstico completo

Investigado en vivo el **18 sep 2026**. Fuentes: el código de los dos repos
(`/Users/colorado/Documents/GitHub/open-higgsfield`, 3 commits, y este repo en `main`),
la documentación oficial de la Higgsfield Platform API (docs.higgsfield.ai,
open.higgsfield.ai/pricing), las guías oficiales de prompting de los fabricantes de
los modelos (kling.ai para Kling 3.0, docs.byteplus.com/ModelArk para Seedance 2.0 y
2.5 más el skill oficial `sd25-pe` de ByteDance, alibabacloud.com/help para Wan 3.0)
y las guías de Higgsfield para Kling 3.0 y Seedance 2.5. Ningún blog de terceros como
fuente de una capacidad, un parámetro o un precio. Además se hizo una **sonda real con
nuestra llave** contra el endpoint gratuito `POST /estimate/{ruta}` de Higgsfield
(nunca contra el de generación; el estimado no gasta créditos) para saber qué rutas
existen para nuestra cuenta y a qué precio. Precios y catálogos cambian cada pocas
semanas: antes de una decisión de volumen, re-verificar.

> **Decisión (18 sep 2026):** no se conecta nada nuevo a Higgsfield; todo sigue por
> WaveSpeed. De este documento queda vigente lo que no depende del proveedor: las
> guías oficiales de prompts (sección 5), la comparación con nuestros prompts
> (sección 6), los patrones de UX (sección 7) y el plan P1/P2 (sección 9). Las
> secciones 3, 4 y P3 quedan solo como referencia de precios y contrato. Pendiente
> decidir qué hacer con el flujo viejo (Nueva idea), que hoy depende de Higgsfield y
> tiene el modelo bloqueado: retirarlo o moverlo a WaveSpeed.

## 0. Resumen ejecutivo

1. **open-higgsfield no tiene prompts que traerse.** Es un front Next.js sobre la
   Platform API de Higgsfield: 38 modelos, un compositor, una galería. Cero LLM,
   cero mejora de prompts, cero estimación de costo, cero tests. Sus "prompts" son 12
   frases de ejemplo de paisajes para el estado vacío. Lo que sí vale: su **catálogo
   declarativo** (rutas y parámetros exactos de la API que ya pagamos), su manejo del
   **contrato de la API** y media docena de **patrones de UX** (sección 7).
2. **Hallazgo urgente, ajeno a open-higgsfield pero destapado por la sonda:** el
   modelo de video del flujo viejo (`kling-2.1-pro`, `higgsfield_client.py:19`) responde
   **423 `model_blocked`** para nuestra llave, igual que toda la familia Kling 2.1.
   Hoy ese flujo no puede generar video y la fila ni siquiera muestra costo. Hay
   reemplazos directos que sí responden (Kling 2.5 Turbo Pro a 0,35 USD los 5 s,
   Kling 3.0 Std a 0,42/0,63 USD) — sección 3.1.
3. **Segundo bug de contrato:** `poll_until_done` no conoce el estado terminal
   `nsfw` (`higgsfield_client.py:141-143`): una imagen o video rechazado por
   moderación deja el trabajo dando vueltas 10 minutos hasta `TimeoutError`.
4. **Los "prompts con los que se sacan mejores videos" están en las guías oficiales
   de Kling, ByteDance (Seedance) y Alibaba (Wan)**, no en open-higgsfield. Las tres
   coinciden en lo mismo: estructura por planos o por tiempos, un movimiento de cámara
   por plano, sujetos definidos con 2-3 rasgos y nombrados siempre igual, activos
   mapeados por número de subida (`Image 1`, `Video 1`), emociones como gestos
   observables, negativos solo para subtítulos y audio, y **parámetros (duración,
   formato, resolución, sonido) fuera del prompt**. ByteDance publica además un skill
   oficial (`sd25-pe`) que es literalmente un "compilador de prompts" para agentes.
5. **Nuestro Crear manda el texto de la persona tal cual** entre bloques fijos
   (`flowplus_prompt.py:1-19`). La plantilla cinematográfica de 11 secciones que el
   spec de CreativeFlowPlus diseñó para que Claude la rellenara sigue en el código,
   **sin llamadores** (`generador_prompts.py:254-346`), y se parece mucho a lo que
   ByteDance y Higgsfield recomiendan hoy. La mejora de mayor impacto es reactivar ese
   paso (gratis, editable, aprobable) con las fórmulas oficiales por modelo.
6. Dos desajustes concretos y testeables en el prompt actual: los activos se nombran
   `@Imagen N` / `@Logo N` cuando los fabricantes documentan `Image N` / `Video N` en
   inglés (los logos llegan al modelo como imágenes numeradas y el prompt los llama
   con un token que nadie documenta), y la supresión de voz/música va en español cuando
   Wan documenta las frases literales *"No dialogue."* / *"No background music."*.
7. **Ningún proveedor sale más barato por Higgsfield** que lo que ya pagamos en
   WaveSpeed (Seedance 2.5 sale ~28 % más caro allí; Wan 3.0 igual). Lo que
   Higgsfield añade son modelos que hoy no ofrecemos: Kling 3.0 Std/Pro/Turbo (con
   `multi_shots`, `cfg_scale`, último fotograma y sonido; Std con sonido es 10 % más
   barato que Kling O3 Pro en WaveSpeed), Kling O3/Omni primer-último fotograma, Wan
   3.0 Prime, Seedance 2.5 `reference-to-video` / `video-edit` / `video-extend`, y Soul
   2 / Soul Cinema a **0,004 USD la imagen** (sin referencia de identidad).

## 1. Qué es open-higgsfield realmente

`open-higgsfield` (repo local `/Users/colorado/Documents/GitHub/open-higgsfield`, 3
commits, 105 archivos) es un **estudio web Next.js 16 / React 19 / Zustand** sobre la
**Higgsfield Platform API**: una barra de prompt, un selector de 38 modelos (8 de
imagen, 30 de video), un rail de ajustes por modelo, adjuntos por rol
(start/end/reference/video/audio), galería con historial en IndexedDB y favoritos
(`README.md:1-80`). No tiene backend propio: el navegador llama a *server actions*
que hacen `POST /{model}` y `GET /requests/{id}/status` con `Authorization: Key
id:secret` (`README.md:91-93`, `src/generation/platform.ts:53-79`).

Lo que **no** tiene, confirmado con `grep` sobre todo `src/` (informe del agente,
sección 4):

- **Ningún LLM ni mejora de prompts propia.** Cero menciones a Anthropic/OpenAI;
  el único rastro es el flag `enhance_prompt` que se le pasa tal cual a Soul
  (`src/generation/catalog/soul.ts:8`, `src/generation/to-platform.ts:43`).
- **Ninguna estimación de costo ni precio.** No llama a `/estimate/...`; lo único
  que reconoce el gasto es un comentario en `src/generation/stores/active.ts:8-11`.
- **Ni negative prompt, ni seed, ni tests, ni audio/voz/música** más allá de los
  toggles que declara cada modelo (`generateAudio`, `sound`, `keepOriginalSound`).
- **Los "prompts con los que sacan mejores videos" son 12 frases de ejemplo por
  superficie** para el estado vacío (`src/openhiggsfield/data.ts:30-61`) y un
  placeholder: *"Describe the shot — subject, camera move, light, pacing…"*
  (`data.ts:25-28`). Nada más.

Conclusión de esta parte: **open-higgsfield no es una fuente de prompts.** Su valor
para nosotros está en tres cosas: (a) el **catálogo declarativo** de modelos con
rutas y parámetros exactos de la misma API que ya pagamos, (b) el **contrato de la
API** bien manejado (estados terminales, sondeo agrupado, reanudación), y (c) media
docena de **patrones de UX** que encajan con una herramienta de aprobación por etapa.
Los prompts buenos hay que traerlos de las guías oficiales de los fabricantes de los
modelos (sección 5), no de este repo.

## 2. Punto de partida: cómo arma hoy iaplusyou los prompts y qué modelos usa

Resumen del informe de lectura de código (todo en `main`, 18 sep 2026):

- **Crear (FlowPlus)** no usa Claude para el prompt de video. `flowplus_prompt.armar`
  (`flowplus_prompt.py:135-243`) concatena bloques en español: `VIDEO DE PRODUCTO
  SOLO…` (si no hay persona), `AUDIENCIA/TEMPORADA` (solo lotes de sprint), un
  `PRODUCTO EXACTO / PERSONAJE / ENTORNO: {etiqueta} es "{activo}". {regla}` por
  activo del catálogo, `LOGO OFICIAL: @Logo 1…`, `@Video 1…: referencia de movimiento`,
  `CON PERSONA: …manos y pies anatómicamente correctos (cinco dedos…)`, `ESTILO DE
  MARCA: {guía}`, `ESCENA: {texto de la persona tal cual}`, `SONIDO: {texto}. Sin
  diálogo hablado ni música de fondo.` y `EVITAR: texto inventado, logos inventados,
  marcas de agua, subtítulos, deformaciones…`. Ningún modelo de Crear recibe
  `negative_prompt`, `seed`, `cfg`, resolución elegible ni último fotograma
  (`providers/flowplus_modelos.py:184-201`); Wan va fijo a 720p; Seedance 2.5 recibe
  **solo la primera imagen**; Seedream recibe `prompt_optimization_mode: "standard"`,
  que reescribe el prompt sin forma documentada de apagarlo (`wavespeed_imagen.py:141-153`).
- **Registro de modelos** (`providers/flowplus_modelos.py:36-100`): Wan 3.0
  (`alibaba/wan-3.0/reference-to-video`, 0,10 USD/s a 720p, 10 imágenes + 5 videos),
  Kling O3 Pro (`kwaivgi/kling-video-o3-pro/reference-to-video`, 0,112 + 0,028 de
  sonido, 7 imágenes), Seedance 2.5 (`bytedance/seedance-2.5/image-to-video`, 0,36
  USD/s, 1 imagen) y Seedream V5 Pro para imagen (0,09 USD). Los precios son
  constantes verificadas a mano con fecha; no se consulta ningún `/estimate`.
- **Flujo viejo** (idea → 5 prompts → imagen → video): `SYSTEM_PROMPT` de
  `generador_prompts.py:12-26` pide "UNA sola acción física… filmable en 5-10
  segundos", 1-2 frases, en español, sin luz ni sonido; el video va a Higgsfield
  `kling-2.1-pro` con `duration`, `cfg_scale` y el `negative_prompt` del `root.json`
  de marca (`dashboard.py:792-813`).
- **Sprints**: `sprints/ideas.py:20-43` pide por idea una `escena` de 40-90 palabras
  "qué se ve, qué hace el producto o la persona, cámara, luz y ambiente", una línea
  `sonido` y un `gancho` para texto en pantalla que **no se usa** al generar. Del
  análisis de referencias (9 claves: composición, iluminación, tipografía, estética,
  storytelling…) solo `resumen`, `movimiento` y `paleta` vuelven a un prompt.
- **Claude**: `claude-sonnet-5` por defecto, sin `temperature` en ninguna llamada; las
  de visión no usan `system`. La plantilla maestra de 11 secciones (REFERENCE MAP,
  MASTER VISUAL CONCEPT, EXACT OBJECT COUNT, PERSISTENT PROP RULES, OWNERSHIP LOCK,
  GUION POR TIEMPOS, CAMERA RULES, PHYSICAL CAUSALITY, IDENTITY PRIORITY, ESTILO,
  REGLAS DE CIERRE) existe en `generador_prompts.py:254-306` pero nadie la llama; el
  spec `docs/superpowers/specs/2026-09-01-creativeflowplus-design.md` la diseñó como
  paso gratis y aprobable antes de gastar, y la implementación lo descartó
  (`flowplus_prompt.py:4-5`).
- **UX de Crear**: una pieza por clic, sin variantes, sin edición del prompt final
  antes de generar (solo se muestra en un `<details>`), "Editar y crear otra" no
  recupera sonido/música (`dashboard.py:4156-4163`), `creative_flow.duplicar` no tiene
  botón, "Reintentar" relanza exactamente lo mismo y el flash dice siempre "Wan 3.0"
  (`dashboard.py:4352`), sin favoritos ni filtros en "Generados".

## 3. Modelos alcanzables hoy con nuestra llave (sonda real del 18 sep 2026)

Nuestro `higgsfield_client.py:14` apunta a `https://platform.higgsfield.ai`; los docs
oficiales usan `https://api.higgsfield.ai` (quickstart y autenticación en
docs.higgsfield.ai). **Ambos hosts respondieron idéntico** a nuestra llave (misma
lista de rutas, mismos precios), así que son el mismo backend; conviene migrar el
`BASE_URL` al documentado. Para averiguar qué rutas del catálogo de open-higgsfield
existen para nuestra cuenta se llamó **solo** al endpoint gratuito
`POST /estimate/{ruta}` (nunca al de generación; `failed`/`nsfw` no se cobran y el
estimado no genera nada, docs *Billing and retention*). Tarifa observada: **1 crédito
= 0,0625 USD** (1,5 cr = 0,094 USD).

### 3.1 Hallazgo urgente: el video del flujo viejo está bloqueado

| Ruta | Respuesta del estimado |
|---|---|
| `kling-video/v2.1/pro/image-to-video` (**nuestro `kling-2.1-pro`**, `higgsfield_client.py:19`) | **423 `model_blocked`** |
| `kling-video/v2.1/standard/image-to-video`, `.../v2.1/master/...` | 423 `model_blocked` |
| `bytedance/seedance-2.0/fast/...`, `.../mini/...` | 423 `model_blocked` |
| `blackforestlabs/flux-3/text-to-video` | 503 `model_disabled` |

Según *Errors and retries* de Higgsfield, 423 = *"Model is temporarily blocked"*
(reintentar más tarde) y 503 = *"Model is disabled or not ready"*. Toda la familia
Kling 2.1 está bloqueada para nuestra cuenta: en el flujo viejo (idea → 5 prompts →
imagen Soul → video) el estimado falla silenciosamente y la fila queda sin costo
(`dashboard.py:756-776` atrapa la excepción y deja `usd=None`), y el botón de generar
video lanza `generate_video` → `raise_for_status()` → error 423 en el trabajo
(`dashboard.py:3702-3706`, `higgsfield_client.py:55-56`). `dop-standard`
(`higgsfield-ai/dop/standard`, 0,563 USD/generación) sí responde, pero es el modelo
secundario de `prompts.py:50`. Reemplazos que sí responden hoy con nuestra llave,
del más barato al más caro, a 5 s y 9:16:

| Ruta (imagen → video) | Valores permitidos (los devuelve el propio estimado al mandar un valor inválido) | 5 s | USD/s |
|---|---|---|---|
| `kling-video/v2.5-turbo/standard/image-to-video` | duration ∈ {5, 10} | 0,210 | 0,042 |
| `kling-video/v2.5-turbo/pro/image-to-video` | duration ∈ {5, 10}; acepta `cfg_scale`, `negative_prompt` sin quejarse | 0,350 | 0,070 |
| `kling-video/v3.0/std/image-to-video` | duration ≥ 3 (hasta 15); `sound` ∈ {on, off}; `cfg_scale` ∈ [0, 1]; `multi_shots` bool; `last_image_url` opcional | 0,420 sin sonido / 0,630 con sonido | 0,084 / 0,126 |
| `kling-video/v3.0-turbo/image-to-video` | resolution ∈ {720p, 1080p}; duration ≥ 3; sin `sound` | 0,560 | 0,112 |
| `kling-video/o3/first-last-frame`, `kling-video/omni/first-last-frame` | `first_frame_url` (+ `last_frame_url`); aspect ∈ {16:9, 9:16, 1:1}; duration ≥ 3 | 0,560 | 0,112 |
| `kling-video/v2.6/pro/image-to-video` | — | 0,700 | 0,140 |
| `kling-video/v3.0/pro/image-to-video` | como std; 1080p mismo precio | 0,560 sin sonido / 0,840 con sonido (10 s: 1,68; 15 s: 2,52) | 0,112 / 0,168 |
| `kling-video/v3.0/4k/image-to-video` | como std | 2,100 | 0,420 |

Kling 3.0 Pro/Std cobran lo mismo a 720p y 1080p y con o sin `multi_shots`; el sonido
nativo sube 50 %. `kling-video/v3/motion-control/{std,pro}` devolvió **500** al
estimar en todas las variantes probadas (no se puede presupuestar hoy, así que no
se puede ofrecer bajo nuestra regla de "estimar antes de generar").

### 3.2 El resto del catálogo, con precio real para nuestra cuenta

Precios devueltos por `/estimate` el 18 sep 2026 (5 s, 720p, 9:16 salvo que se
indique). Las columnas "valores permitidos" salen de los mensajes 400 del estimado:
son el contrato real, más fiable que el catálogo TypeScript de open-higgsfield (que
por ejemplo declara resoluciones `1k/2k/4k` para Soul 2 cuando la API solo acepta
`720p/1080p`, `src/generation/catalog/defaults.ts:19` vs. sonda).

**Video**

| Ruta | Valores permitidos observados | Precio |
|---|---|---|
| `alibaba/wan-3.0/{text,image}-to-video` | resolution {480p, 720p, 1080p}; aspect {16:9, 4:3, 1:1, 3:4, 9:16, adaptive}; duration ≥ 2 | El estimado **no da número**: devuelve la descripción *"480p $0.05, 720p $0.10, 1080p $0.20 por segundo"*. Igual que WaveSpeed (`providers/wan3_client.py:41`). |
| `alibaba/wan-3.0-prime/{text,image}-to-video` | idem Wan 3.0 | 0,700 (0,14 USD/s) |
| `wan/v2.7/{text,image}-to-video` | resolution {720p, 1080p}; duration ≥ 2 | 0,500 (0,10 USD/s); 10 s = 1,000 |
| `bytedance/seedance-2.5/{text,image,reference}-to-video`, `/video-edit`, `/video-extend` | resolution {480p, 720p}; aspect {16:9, 4:3, 1:1, 3:4, 9:16, 21:9}; duration ≥ 4; `generate_audio` bool; `image_urls`/`video_urls`/`audio_urls` en reference-to-video | **No da número**, devuelve la fórmula: *tokens = ceil((s de video de entrada + s generados) × ancho × alto × 24 / 1024); 0,0214 USD por 1 000 tokens a 480p/720p* (extend: 0,01284 USD/1 000 tokens, entrada y salida facturables). Calculado por nosotros con esa fórmula: **720p 9:16 = 21 600 tokens/s = 0,462 USD/s** (5 s = 2,31 USD); 480p ≈ 0,206 USD/s. |
| `bytedance/seedance-2.0/image-to-video` | — | Fórmula: 0,014 USD/1 000 tokens a 480p/720p/1080p, 0,008 a 4K → calculado 720p 9:16 ≈ 0,302 USD/s |
| `minimax/h3/{text,image}-to-video` | resolution **solo `2K`**; duration ≥ 5; aspect {auto, adaptive, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16} | 0,650 (0,13 USD/s) |
| `minimax/hailuo-2.3/standard/text-to-video` | duration ∈ {6, 10} | 0,280 a 6 s (0,047 USD/s) |
| `lightricks/ltx-2.5/text-to-video/{pro,fast}` | duration ∈ {6, 8, 10} | pro 0,720 / fast 0,540 a 6 s |
| `pixverse/v6/{text,image}-to-video` | resolution {360p, 540p, 720p, 1080p} | 0,255 (0,051 USD/s); 8 s 1080p = 0,782 |
| `higgsfield-ai/dop/lite` / `dop/standard` | por generación | 0,125 / 0,563 |
| `alibaba/happy-horse/v1.1/text-to-video` | — | 0,700 |
| `xai/grok-imagine-video/v1.5/reference-to-video` | `image_urls` | 0,710 |

**Imagen**

| Ruta | Valores permitidos | Precio por imagen |
|---|---|---|
| `higgsfield-ai/soul/reference` (**nuestro `soul-reference`**) | `image_reference_url`; aspect {9:16, 16:9, 4:3, 3:4, 1:1, 2:3, 3:2}; resolution {720p, 1080p}; `batch_size` ∈ {1, 4}; `enhance_prompt` bool | 0,094 (720p) / 0,188 (1080p) |
| `higgsfield-ai/soul/standard` | sin referencia | 0,094 |
| `higgsfield-ai/soul/v2/standard` | sin referencia; resolution {720p, 1080p}; batch {1, 4} | **0,004** (720p) / 0,006 (1080p) |
| `higgsfield-ai/soul/cinema` | idem Soul 2 | 0,004 / 0,006; lote de 4 a 1080p = 0,022 |
| `higgsfield-ai/soul/character` | exige `custom_reference_id` (un personaje registrado previamente en Higgsfield) | — |
| `z-image/turbo` | — | 0,015 |
| `recraft/v4.1/text-to-image` | — | 0,035 |
| `alibaba/qwen-image-3/text-to-image` | — | 0,040 |
| `ideogram/v4.0`, `xai/grok-imagine-image-2.0` | — | 0,060 |

Contexto de tarifa pública: la página de precios de la API (open.higgsfield.ai/pricing,
leída el 18 sep 2026 con el navegador porque se renderiza con JS) publica "desde"
por familia: Kling 3.0 desde 0,084 USD/s, Kling 2.6 desde 0,07, Kling 2.5 desde
0,042, Kling O1/O3 desde 0,084, Seedance 2.5 desde 0,1234 (coincide con `video-extend`
a 480p según la fórmula), Seedance 2.0 desde 0,1407, Wan 3.0 desde 0,05, Wan 3.0
Prime desde 0,068, MiniMax H3 0,13, LTX 2.5 Pro desde 0,12, PixVerse 6 0,115,
Soul 2 desde 0,0032/imagen, Marketing Studio Image 0,0162/imagen. Nuestros números
de la sonda son los que aplican a esta cuenta.

### 3.3 Qué significa frente a lo que pagamos en WaveSpeed

`providers/flowplus_modelos.py:36-77` (precios verificados el 12 y 17 sep 2026):

| Modelo en Crear | WaveSpeed hoy | Equivalente en Higgsfield con nuestra llave | Lectura |
|---|---|---|---|
| Wan 3.0 `alibaba/wan-3.0/reference-to-video` | 0,10 USD/s a 720p (`wan3_client.py:41`) | Wan 3.0 0,10 USD/s a 720p (misma escalera 0,05/0,10/0,20) | Mismo precio. Ojo: el estimado de Higgsfield no devuelve número para Wan, habría que calcularlo como ya hacemos. |
| Kling O3 Pro `kwaivgi/kling-video-o3-pro/reference-to-video` | 0,112 + 0,028 de sonido = 0,14 USD/s | Kling 3.0 Pro 0,168 USD/s con sonido (0,112 sin); Kling 3.0 Std 0,126 con sonido (0,084 sin); Kling O3 first-last-frame 0,112 | **Kling 3.0 Std con sonido es 10 % más barato que O3 Pro en WaveSpeed y trae `multi_shots`, `cfg_scale` y `last_image_url`.** Kling 3.0 Pro es 20 % más caro. |
| Seedance 2.5 `bytedance/seedance-2.5/image-to-video` | 0,36 USD/s | ≈ 0,462 USD/s a 720p 9:16 (fórmula) | **WaveSpeed es ~22 % más barato.** No mover Seedance a Higgsfield; además allí el estimado no da número. |

Es decir: open-higgsfield no nos descubre un proveedor más barato para lo que ya
tenemos; nos descubre **modelos que hoy no ofrecemos** (Kling 3.0 Std/Pro/Turbo,
Kling O3/Omni con primer y último fotograma, Wan 3.0 Prime, Seedance 2.5
`reference-to-video` con hasta 30 imágenes y 10 videos/10 audios, `video-edit`,
`video-extend`, Soul 2/Cinema a 0,004 USD la imagen) y **rutas de reemplazo para el
modelo bloqueado**.

## 4. Contrato de la Platform API: lo que open-higgsfield hace bien y a nosotros nos falta

Verificado contra docs.higgsfield.ai (*Requests and lifecycle*, *Polling*, *Webhooks*,
*Errors and retries*, *Rate limits*, *Billing and retention*, *File uploads*) y contra
el código de ambos repos.

| Tema | Docs oficiales | open-higgsfield | iaplusyou hoy |
|---|---|---|---|
| Estados terminales | `completed`, `failed`, `nsfw`, `canceled`; `queued` e `in_progress` no lo son | `TERMINAL = {completed, failed, nsfw, canceled}` (`src/generation/poll.ts:5`); un `completed` sin URL cuenta como fallo (`openhiggsfield-app.tsx:110`) | `poll_until_done` solo corta en `completed/succeeded/success/done` y `failed/error/canceled/cancelled` (`higgsfield_client.py:141-143`). **`nsfw` no es terminal: la tarea da vueltas 600 s hasta `TimeoutError`** mientras el trabajo ya murió gratis. |
| Sondeo | Empezar en 2 s, subir gradualmente hasta 10 s, *jitter* con muchos workers, usar el `status_url` de la respuesta | 4 s fijos, plazo 10 min, **una sola llamada por ronda para todas las requests en vuelo**, 3 rondas fallidas seguidas antes de rendirse (`poll.ts:7-11, 25-29`) | 5 s fijos, 600 s, una request por trabajo, `raise_for_status` sin reintento en un 5xx transitorio (`higgsfield_client.py:111-146`) |
| Reanudación | — | Las filas `running` guardan `requestId` y al recargar se vuelven a observar (`openhiggsfield-app.tsx:289-304`) | El trabajo viejo vive en un hilo daemon en memoria (`trabajos.iniciar`): un reinicio de gunicorn pierde un video ya pagado. |
| Errores | Envelope `{"detail": ...}`; 400 parámetros o **concurrencia alcanzada**; 401; 403 sin créditos; 404; 422; **423 modelo bloqueado temporalmente**; 500 reintentar con backoff; **503 modelo deshabilitado**. *"Do not automatically repeat a generation POST after an ambiguous timeout because submissions do not currently accept an idempotency key"* | `PlatformError` con `detail` humano (`platform.ts:5-15, 136-140`) | `raise_for_status()` a secas: el usuario ve "423 Client Error: Locked". |
| Cancelación | `POST /requests/{id}/cancel` solo mientras todo sigue `queued`; 202 ok, 400 si ya empezó; se reembolsa | guarda `cancelUrl` pero no lo usa | no existe |
| Webhooks | Query `hf_webhook` al enviar; envelope `request_id, status, error, payload`; se dispara en `completed/failed/nsfw`; reintentos de red/5xx hasta 2 h; responder 2xx en < 10 s; **entregas duplicadas posibles, deduplicar por `request_id` + estado**; sin firma | no | no (tenemos URL pública en app.creatvmachine.com: sería un ahorro real de sondeo para el worker) |
| Concurrencia | Límite por cuenta y modelo, visible en la consola; al superarlo la API devuelve **400** *"Maximum number of concurrent requests (4) has been reached"*, sin cabeceras `Retry-After` | no lo maneja | no lo maneja (un lote de sprint podría chocar con el límite y verlo como error de parámetros) |
| Facturación | Se cobra solo lo exitoso; `failed`/`nsfw` no se cobran y se reembolsa lo reservado; créditos caducan al año | — | coincide con nuestra regla de `max_intentos=1` |
| Retención | La salida es accesible **al menos 7 días** y puede borrarse después | README avisa que el historial viejo puede quedar con huecos | nosotros ya subimos todo a R2, correcto |
| Entrada de medios | URL HTTPS pública o `POST https://api.higgsfield.ai/files/generate-upload-url` (URL prefirmada, expira en 1 h); MIME: jpeg/jpg/png/webp/gif, wav/x-wav, mp4 | sube a Vercel Blob y manda URLs públicas | subimos a R2 y mandamos URLs públicas (equivalente) |
| Validación previa | — | re-valida los settings **en el servidor** contra el catálogo antes de enviar (`src/generation/actions.ts:34-42`) | el worker ajusta duración/formato (`flowplus_modelos.ajustar_*`) pero no rechaza enums ilegales |

## 5. Prompts: lo que enseñan las guías oficiales (y que open-higgsfield no tiene)

Todo lo de esta sección viene de páginas oficiales de los fabricantes o de Higgsfield
(URLs en la sección 10), leídas el 18 sep 2026. Se cita textual donde importa.

### 5.1 Kling 3.0 (kling.ai, guía oficial del modelo y guía de texto-a-video)

- **Fórmula base (guía text-to-video):** *"Prompt = Subject (Subject Description) +
  Subject Movement + Scene (Scene Description) + (Camera Language + Lighting +
  Atmosphere)"*, con los tres últimos opcionales. Consejos literales: *"Use simple
  words and sentence structures"*, *"Keep the visual content as simple as possible,
  aiming for a completion within 5 to 10 seconds"*, *"Current large video models are
  not sensitive to numbers, making it difficult to maintain consistency in counts"*;
  evitar físicas complejas (rebotes, trayectorias).
- **Multi-shot (3.0):** dos modos, automático (*"Multi-Shot"*, el modelo planifica
  y puede quedarse en un plano si la escena lo pide) y manual (*"Custom Multi-Shot"*,
  número de planos y duración). Sintaxis del ejemplo oficial: *"Shot 1, profile shot
  of black man driving a truck, cinematic handheld. Shot 2, frontal macro shot …
  Shot 3, macro shot of hands on the steering wheel …"*. Por plano: tamaño de plano,
  ángulo, movimiento, estilo. Higgsfield añade en su guía de Kling 3.0: hasta 5
  planos, *"Assign one action + one camera move per shot"*, *"Don't … pack five
  shots into very short clips"*, *"Draft at 720p before final 4K rendering"*, y que
  la transferencia de movimiento exige Motion Control, no el modelo base.
- **Diálogo y voz:** formato `Personaje (tono, idioma si no es inglés): "línea"`.
  Ejemplo oficial: *"Mom (softly, in a surprised tone): Wow, I didn't expect this
  plot at all. Dad (in a low voice, agreeing, in a calm tone): Yeah…"*. Idiomas
  soportados: **chino, inglés, japonés, coreano y español**; acentos etiquetables
  (americano, británico, indio…). Voz en off: *"Voiceover (lazy French female
  voice, British accent, slow pace): Bathe in the golden hour."* Ambiente en la
  descripción de escena (*"faint hum of the living room air conditioner"*). En
  escenas con 3+ personajes, nombrar quién dice qué *"to eliminate ambiguity"*.
- **Consistencia de sujeto:** "Elements" a partir de 2-4 imágenes o de un video
  (extrae apariencia y voz); *"If you choose a subject with a pre-bound voice tone,
  it's not recommended to set the tone again in the prompt."* Producto: *"the camera
  pans slowly in from the scattered rose petals, shifting focus to the faceted cut
  of the Kling perfume bottle…"*.
- **Texto en imagen:** 3.0 *"automatically identifies text content in uploaded
  images … avoiding issues such as text displacement or blurring"* (uso declarado:
  publicidad e-commerce). Sin sintaxis oficial para "sin diálogo" ni para `cfg`.
- **Cámara (guía de control de cámara de Kling):** vocabulario pan / tilt / zoom /
  dolly / orbit / crane / tracking; frase modelo *"Close-up shot, slow dolly forward
  while tilting up slightly, revealing subject's face, cinematic quality with shallow
  depth of field, 4-second duration"*; movimientos compuestos son más difíciles,
  *"change one aspect per test"*; velocidades: ultra-lento 2-3 s, lento 5-8 s,
  moderado 3-5 s, rápido 1-2 s.
- **Precio en la app de Kling (no en Higgsfield):** 1080p con audio 12 cr/s, 720p
  con audio 9 cr/s, 1080p sin audio 8 cr/s, 720p sin audio 6 cr/s: el sonido nativo
  cuesta +50 %, igual que en Higgsfield.

### 5.2 Seedance 2.5 y 2.0 (BytePlus ModelArk, guías oficiales de prompt + skill `sd25-pe`)

**Guía 2.0 (fórmula avanzada, vigente para 2.5):** *"precise subject + action
details + scene/environment + lighting & color tone + camera movement + visual style
+ image quality + constraints"*. El modelo es *"a multimodal AI director"* que separa
capa espacial (qué hay) y temporal (cómo cambia); un buen prompt es *"an
engineering-style instruction"*, no copy. Reglas concretas:

- **Definir sujetos con 2-3 rasgos estáticos** y nombrarlos siempre igual:
  *"Define the woman wearing a red dress and a straw hat in Image 1 as Subject 1"*;
  al mencionarlos, `Nombre@Image 1`.
- **Storyboard por planos** (`Shot 1 / Shot 2 / Shot 3`), cada plano = movimiento de
  cámara + acción y expresión + posición + audio. Contraejemplo oficial: *"A man
  runs nervously down the street, and the scene feels very cinematic."*
- **Acciones lentas, suaves, continuas** (evitar sprints, saltos, rodadas);
  concretar la parte del cuerpo y el grado (*"slowly raise a hand"*); **emociones
  como gestos observables** (tabla oficial: tristeza = cabeza baja, hombros que
  tiemblan, dedos que aprietan la ropa…).
- **Un solo movimiento de cámara por plano:** *"Do not require push, pull, pan, and
  move at the same time, as this will increase image instability."*
- **Constraints:** *"keep it subtitle-free"*, *"do not generate a logo"*, *"do not
  generate a watermark"* (los subtítulos no se pueden evitar al 100 %; en horizontal
  aparecen bastante menos que en vertical).
- **Símbolos:** música entre `（）`, efectos entre `<>`, diálogo entre `{}` (marcar
  el idioma si no es chino/inglés), rótulos entre `【】`. **No mezclar idiomas en el
  diálogo.**
- **Activos: 4-5 en total** (1-2 imágenes del personaje —**headshot + cuerpo
  entero, nunca "tres vistas"**—, 1 de escena, 1 video de cámara, 1 audio); *"It is
  not recommended to use the full asset limit"*. Deriva de identidad: cara demasiado
  pequeña en una imagen mixta → añadir un primer plano solo de la cara y ponerla
  primero. "Gemelos": definir cada personaje con su imagen y cerrar con *"Throughout
  the video, characters with completely identical appearance… are prohibited"*.
- Plantillas de producto (ejemplos oficiales): *"Use the cameras featured in Image 1,
  Image 2 and Image 3. Replace the original background with a white one… The camera
  first focuses on the cameras in close-up, then slowly rotates 360°…"*; *"Replace
  the perfume featured in Video 1 with the face cream from Image 1, with all original
  motions and camera work preserved."*

**Guía 2.5 (diferencias que importan):**

- Hasta 30 s, 50 activos (30 imágenes ≤ 4K, 10 videos ≤ 30 s en total, 10 audios).
  Recomendado: 1-8 sujetos por imagen, 1-5 por audio/video, clips de 5-10 s; edición
  de videos ≤ 20 s con 1-5 imágenes.
- **Timestamps enteros de 1 s sí funcionan** (*"0-3 seconds… 3-7 seconds… 7-15
  seconds"*, *"[1s-4s]…"*, marcas puntuales *"At the 2-second mark…"*, relativas
  *"After 3 seconds…"*): 2.0 solo respondía a `Shot N`. Sin huecos en la línea de
  tiempo; poca trama por tramo = el modelo improvisa; demasiada = cortes de más.
- Estructura recomendada: **mapeo de activos por orden de subida** (*"Image 1 depicts
  the protagonist John and uses the voice timbre from Audio 1"*; nunca poner el
  nombre dentro de la imagen), **resumen de una frase** (*"Subject + Location + Event
  + Genre/Style + Camera movement"*), **desglose por tiempos o planos**, **notas de
  consistencia** (ángulo, entorno, sonido). Positivo siempre; negativo solo para
  subtítulos y audio (*"No subtitles"*, *"No BGM; generate only environmental sounds
  and action sounds"*, *"No audio"*).
- Tareas **bloqueadas** (edición, primer/último fotograma, extensión) fijan la
  relación de aspecto al activo de entrada (`ratio=adaptive`) y la edición fija
  también la duración (`duration=-1`); recomiendan `mov` de salida. Disparadores en
  el prompt: *edit video / add / remove / replace…* y *extend forward / backward /
  continue…*. Primer fotograma por parámetro (`first_frame`) o por texto (*"Image 1
  is the first frame"*, sin bloquear el aspecto).
- Cámara: términos estándar directos (*push in / pull out / pan / track / orbit /
  dolly zoom / handheld / speed ramp*); lo raro se escribe como *término + explicación*.
  Transiciones con punto y método: *"At the 5-second mark, the camera quickly
  transitions leftward using a left wipe combined with a natural dissolve."*
- Ejemplo oficial completo de 2.5 con el formato entero (panda en la ladera): estilo
  → sujeto y escena → cámara → `0s-3s` → `3s-8s` → notas de cámara, foco y audio
  (*"Natural environmental audio only… The overall mood is warm, realistic, and
  natural."*).

**Skill oficial `sd25-pe` (ByteDance, v0.1.1):** la guía recomienda instalarlo con
`npx skills add … --skill sd25-pe`; se obtuvo en modo lectura con `skills use`
(no se instaló nada). Es un system prompt de ~40 KB para que un agente convierta
texto + activos en **un** prompt listo para enviar. Principios literales que
deberían gobernar nuestro `flowplus_prompt.armar`:

1. *"Intent First"*: no cambiar identidades, cantidades, props, causalidad ni final.
2. *"Template First"*: reorganizar siempre con la plantilla, no parafrasear.
3. *"Account for Every Asset"*: cada activo usado dice qué se toma de él; los no
   usados se listan bajo `【Unused Assets】` *"to prevent downstream prompt enhancement
   from reactivating it"*.
4. *"Separate Parameters"*: **relación de aspecto, duración total, resolución, fps
   y el toggle de sonido no van en el prompt**; se mandan por API.
5. *"Do Not Add Unrequested Constraints"*: nada de "quality packs", "stability
   packs" ni negativos genéricos que el usuario no pidió.
6. *"One Best Version"*; *"Separate Facts from Observations"* (identidad/edad/
   relaciones salen del texto del usuario, las imágenes solo aportan lo visible);
   *"Match Subject Cardinality"* (una imagen de una persona no define dos personajes).
7. *Dialogue ledger*: por tramo, quién habla, texto exacto, idioma, on/off screen;
   si hay solo una frase suelta, esa es la única que se puede decir; sin texto, no
   inventar diálogo.
8. Prioridad de mapeo: *"User's explicit specification > Prompt description > Asset
   content > Filename and metadata > Upload order"*.
9. Plantilla básica: `<Sujeto> <acción principal> en <escena>. / Los visuales
   presentan <estilo>. / La cámara usa <plano, posición, movimiento>. / El sonido
   incluye <diálogo, ambiente, efectos, música>.` Plantilla con referencias:
   `【Generation Goal】 / 【Reference Asset Roles】 / 【Unused Assets】 / 【Subjects and
   Relationships】 / 【Event Script】 (inicio, evento, final) / 【Maintain Consistency】`.
   Ejemplo oficial del carpintero: *"@Image1 is used for the carpenter's facial
   features, short hair, and dark blue work apron; do not use the image background."*

### 5.3 Wan 3.0 (Alibaba Cloud Model Studio, guía oficial de prompts)

- **Básico:** *"Prompt = Entity + Scene + Motion"*; **avanzado:** *"+ Aesthetic
  control + Stylization"* (fuente y tipo de luz, hora, tamaño de plano, composición,
  focal, ángulo, tono).
- **Imagen-a-video:** *"Prompt = Motion + Camera movement"*: la imagen ya fija sujeto,
  escena y estilo; describir solo lo que se mueve y la cámara (*"camera pushes in"*,
  *"fixed camera"*). **Esto es exactamente nuestro caso en Crear**, donde la imagen
  aprobada es el arranque.
- **Fórmula de sonido (3.0/2.7/2.6/2.5):** voz = *"Character's lines + Emotion +
  Tone + Speed + Timbre + Accent"*; efectos = *"Source material + Action + Ambient
  sound"*; música = *"Background music + Style"*. Para suprimir: **"No dialogue."** y
  **"No background music."** (literal, en inglés).
- **Multi-shot:** *"Overall description + Shot number + Timestamp + Shot content"*
  (*"Shot 1 [0–3 s]: …"*). **Referencias:** *"Image 1"*, *"Video 1"* (mayúscula y
  espacio en inglés), numeradas por orden de subida y contadas por tipo.
- **No hacer:** personas reales por nombre; cambios de escena rápidos dentro de un
  clip; texto legible exacto; secuencias de acción largas; lip-sync a palabras
  concretas. Órbitas < 45°.
- La API tiene `prompt_extend` (expansión automática del prompt) y hasta 20 activos
  (10 imágenes ≤ 20 MB, 5 videos ≤ 15 s en total, 5 audios); `duration=-1` = duración
  inteligente; `audio=false` apaga el audio nativo.

### 5.4 La guía de Seedance 2.5 de Higgsfield (blog oficial de Higgsfield)

Complementa a ByteDance con una estructura de **10 secciones etiquetadas en un solo
bloque**: *GLOBAL STYLE → SCENE → CHARACTERS → LOCATION → FIRST FRAME AND BLOCKING →
SHOT-BY-SHOT BREAKDOWN → OPTICS → PHYSICS → LIGHTING → AUDIO*; *"Skip a section and
the output tends to fail in a specific, predictable way."* Tres de sus ocho ejemplos
son publicidad y merecen guardarse como referencia de formato:

- **Comercial de producto (auriculares):** *"ACTIVE REFERENCES"* (identidad de la
  chica bloqueada a la referencia ignorando el fondo; producto heredado tal cual,
  *"unbranded, no logos"*), cinco segmentos con cortes duros, *"zero drift"*, audio
  *"diegetic-plus-product sound"*, sin música.
- **UGC (galletas en el avión):** *"Vertical 9:16 UGC video, 30 seconds total, 24fps,
  shot on iPhone 14 Pro, authentic phone-camera look"*, *"arm's-length wobble, tiny
  refocus moments"*, *"reactions arrive a half-beat late, smiles start small and
  grow… no performing"*, geometría del asiento fija en todos los planos, *"All speech
  ends by 25s"*, sin texto en pantalla, termina en su cara y no en el packshot.
- Reglas transversales: bloqueos positivos (*"MEMBER COUNT LOCK"*, *"LENS LOCK"*),
  focal por segmento para evitar deriva, cortes duros marcados, tiempos exactos,
  *"No music, no narration, no subtitles"* por defecto.

### 5.5 Lo que sí aporta open-higgsfield en prompts

Solo dos cosas, y pequeñas: el placeholder que enseña la estructura mínima
(*"subject, camera move, light, pacing"*) y la idea de **estado vacío con tres
prompts completos** que cargan la barra sin generar nada (*"pressing Generate stays
the visitor's call"*, `openhiggsfield-app.tsx:587-596`). Sus 12 prompts de video son
de paisajes y cine, no de producto; no sirven de banco para Creatv.

## 6. Cómo se comparan nuestros prompts con lo que piden los fabricantes

| Regla oficial | Quién la dice | Nuestro prompt hoy | Delta |
|---|---|---|---|
| Activos por número de subida: `Image 1`, `Video 1`, `Audio 1` (Wan: mayúscula y espacio en inglés; Seedance: `Image 1` / `@Image 1`) | Wan, Seedance 2.5 | `@Imagen N`, `@Video N`, `@Logo N` (`flowplus_prompt.py:18`); los logos se añaden al final de la lista de imágenes (`dashboard.py:4258-4263`), así que el modelo los recibe como `Image k` mientras el prompt dice `@Logo 1` | **Hipótesis fuerte de desajuste**: `Imagen` (español) y `Logo` no son tokens documentados. Probar `Image N` con Wan a 480p (0,25 USD por prueba de 5 s). |
| Parámetros fuera del prompt (duración, formato, resolución, fps, toggle de sonido) | Skill `sd25-pe`, principio 7 | Cumplido: duración/formato/sonido van por API | — |
| Estructura por planos o tiempos: `Shot N` (Kling, Seedance 2.0), `0-3s / 3-8s` (Seedance 2.5, Wan `Shot 1 [0–3 s]`) | Las tres guías | `ESCENA:` es un párrafo libre; la idea de sprint son 40-90 palabras sin línea de tiempo; el default de Crear son 10 s y llega a 30 | Para > 8 s las guías piden desglose; hoy el modelo improvisa el ritmo. Es el mayor salto de calidad disponible sin cambiar de modelo. |
| Un movimiento de cámara por plano; una acción + un movimiento por plano | Seedance 2.0, Higgsfield/Kling 3.0 | No se controla | Regla para el compilador de prompts. |
| Imagen-a-video = *"Motion + Camera movement"* (la imagen ya fija sujeto y escena) | Wan | Con Seedance 2.5 (primer fotograma) re-describimos producto, persona y marca | Para Seedance 2.5 image-to-video, describir movimiento y cámara; la fidelidad ya está en el fotograma. |
| Sujetos con 2-3 rasgos estáticos, nombrados siempre igual; `Nombre@Image 1` | Seedance | `PERSONAJE: Personaje 1 es "Ana" (sus vistas son la misma persona). {regla}` + `CON PERSONA: la única persona en escena es Ana` | Alineado en espíritu; falta ligar el nombre al número (`Ana@Image 1`). |
| Personaje: headshot + cuerpo entero, **no** "tres vistas" (2.0); 2.5 admite multivista con ≤ 5 sujetos | Seedance | Hasta 3 fotos por personaje (`dashboard.py:4240`) — llegan a Wan y Kling O3, no a Seedance (que solo toma la primera) | Sin conflicto hoy; si se activa Seedance reference-to-video, mandar cara + cuerpo entero. |
| Negativos solo para subtítulos y audio (2.5); *"keep it subtitle-free"*, *"do not generate a logo/watermark"* (2.0); no añadir "quality packs" ni negativos genéricos no pedidos | Seedance, skill `sd25-pe` | `EVITAR: texto inventado, logos inventados, marcas de agua, subtítulos, deformaciones, {negative_marca[:400]}`; `CON PERSONA: … cinco dedos, dedos relajados y juntos, uñas naturales` | Subtítulos/logos/marca de agua coinciden con lo documentado; "deformaciones" y la anatomía son el "quality pack" que el skill desaconseja. Probar sin ellos. |
| Supresión de voz/música con frases literales: *"No dialogue."*, *"No background music."* (Wan); *"No BGM; generate only environmental sounds and action sounds."* (Seedance); fórmula de sonido = fuente + acción + ambiente | Wan, Seedance | `SONIDO: {texto}. Sin diálogo hablado ni música de fondo.` (`flowplus_prompt.py:118-132`) | Misma intención, otro idioma. Añadir las frases literales en inglés cuesta nada. |
| Emociones como gestos observables; acciones lentas y continuas; parte del cuerpo + grado | Seedance | Depende del texto de la persona / de Claude en sprints (no se pide) | Regla para el compilador. |
| Diálogo `Personaje (tono, idioma): "línea"`, idiomas incl. español; voz en off | Kling 3.0 | Por diseño no hay diálogo nativo (la voz sale de final edition) | Opción futura: Kling 3.0 vía Higgsfield con voz nativa en español para UGC. |
| Estado inicial / evento / estado final; bloqueos de cantidad y propiedad ("EXACT OBJECT COUNT", "OWNERSHIP LOCK") | Skill `sd25-pe` (`【Event Script】`), Higgsfield (*"POSITIVE LOCKS"*) | **Ya lo tiene la plantilla maestra muerta** (`generador_prompts.py:254-306`) | Reactivarla recortada por modelo. |
| Texto en pantalla: Seedance sí lo genera (rótulos `【】`, slogans con tiempo y posición); Kling 3.0 conserva texto de la imagen | Seedance, Kling | El `gancho` de la idea se guarda y no se usa; `EVITAR: texto inventado` | Si se quiere texto nativo, pasar el gancho con la sintaxis oficial; si no, mantener la prohibición. |
| Idioma del prompt | Ninguna guía prohíbe el español; todos los ejemplos son inglés/chino; Kling declara español para diálogo | Todo en español, sin traducción (`flowplus_prompt.py`, `sprints/ideas.py:43`) | No asumir: A/B inglés vs español con la misma semilla de idea, a 480p. |

Lo que la comparación **no** dice: que nuestros prompts estén mal. Los bloques con
etiqueta, la fidelidad por activo y el sonido explícito son exactamente el estilo
que Higgsfield recomienda (*"labeled sections"*). Lo que falta es el **eje temporal**
(planos/tiempos), el **mapeo numérico** de activos y sacar los **negativos genéricos**;
y la forma de conseguirlo sin cargar a la persona es el paso de compilación con
Claude que el spec original ya preveía.

## 7. Patrones de UX y arquitectura que sí vale la pena copiar

Del informe del agente sobre open-higgsfield (rutas relativas a
`open-higgsfield/src/`), filtrados por lo que encaja con una cola de trabajos y
aprobación por etapa:

1. **El registro es la única fuente de verdad.** Cada modelo declara `roles` con
   tope por rol y `settings` con tipo, valores permitidos y default
   (`generation/catalog/types.ts:22-30`); `parseSettings` rechaza valores ilegales
   (`generation/catalog/parse-settings.ts:3-25`) en cliente y de nuevo en servidor
   (`generation/actions.ts:34-42`); el formulario, la descripción del picker
   (*"Video from a prompt, frames or references · to 1080p, 4–30s"*,
   `openhiggsfield/data.ts:218-240`) y el contador de adjuntos por rol
   (`asset-picker.tsx:250-270`) se derivan de ahí. Nuestro
   `providers/flowplus_modelos.py` ya es ese registro a medias (duraciones, formatos,
   `max_referencias`, `audio_nativo`): le faltan `roles` y `settings` declarados, y
   que las plantillas de Crear los rendericen en vez de listas paralelas.
2. **Guardar el "plano" resuelto con cada run** (`openhiggsfield/history.ts:28-30`:
   *"so reuse can restore the dials and not just the words"*) y que "Reuse/Recreate"
   lo rehidrate en el compositor (`openhiggsfield-app.tsx:405-420`). Lo que a ese
   repo le falta y a nosotros nos sobra: los adjuntos (personajes, producto,
   fotograma aprobado). Aplica a "Duplicar" y a las regeneraciones del decisor.
3. **Reintentar = recargar, nunca reenviar.** Un run fallido conserva modelo, prompt,
   settings y **la razón** (`openhiggsfield-app.tsx:107-150`), y el botón *"Retry this
   run"* solo precarga (`gallery.tsx:171-196`); generar sigue siendo un clic humano.
   Es la traducción exacta de `max_intentos=1` + cost gate.
4. **`nsfw` y `canceled` como fallos terminales con texto humano**
   (`openhiggsfield-app.tsx:145-150`: *"the platform flagged the result as NSFW"*), y
   `completed` sin URL = fallo.
5. **Sondeo agrupado y reanudable** (`poll.ts:25-29`, `actions.ts:44-60`,
   `openhiggsfield-app.tsx:289-304`): una ronda por intervalo para todos los
   `request_id` en vuelo, tolerancia de 3 rondas fallidas, `request_id` persistido
   para reanudar tras reinicio.
6. **Lote con stepper de valores permitidos** (`composer.tsx:395-475`: Soul ofrece 1
   o 4, *"there is no 2 to land on"*) y un skeleton por resultado con cronómetro
   (`gallery.tsx:548-570`). Para la etapa de imagen candidata, mostrando el costo × N.
7. **Aprobado = favorito que no caduca** (`history.ts:100-108`: los favoritos
   sobreviven al tope de 60 registros). Lo aprobado nunca entra en limpiezas.
8. **Undo de 6 s con barra que se drena** (`openhiggsfield-app.tsx:35-36, 430-463,
   719-765`) **solo para acciones gratis** (descartar un candidato); lo que gasta
   créditos sigue pidiendo confirmación.
9. **Estados vacíos que enseñan** (`gallery.tsx:489-546`) y **placeholder con la
   estructura del prompt** (`data.ts:25-28`), en nuestro caso sacando los tres
   ejemplos de `marca.json` del proyecto.
10. **Los resultados de una etapa como entradas de la siguiente** (`asset-picker.tsx:
    92-104, 123-136`): la imagen aprobada ofrecida automáticamente como `start`,
    personajes y producto como `reference`, con topes por rol; al llenar `start` el
    foco salta a `end`.
11. **Errores con `detail` humano** y **lámpara de estado** (llave presente / run en
    vuelo, `topbar.tsx:123-139`).

Lecciones de lo que **falla** allí y no hay que repetir: LTX 2.5 descarta el start
frame en silencio por un helper de rutas (`generation/catalog/defaults.ts:6-9`,
`to-platform.ts:134-139`); varios modelos se envían sin inputs por los fallbacks del
mapper (`to-platform.ts:140-142`) → validar "rol requerido por ruta" antes de
encolar; el botón Generate no se bloquea con runs en vuelo (`composer.tsx:95-97`);
`/api/blob` no tiene auth (`app/api/blob/route.ts:12`); loguea cuerpos completos de
request/response (`platform.ts:55,66`).

## 8. Qué NO traer

- **La app en sí** (Next.js, Vercel Blob, IndexedDB): duplica lo que ya tenemos en
  Flask + R2 + SQLite y no tiene multiusuario, cola, cost gate ni aprobación.
- **Su modelo de llave en cookie del navegador**: nosotros ya la tenemos en el servidor.
- **Sus prompts de ejemplo** (paisajes/cine, sin producto ni marca).
- **Seedance 2.5 vía Higgsfield** para reemplazar a WaveSpeed (más caro, sin
  estimado numérico).
- **Kling 3 Motion Control** hasta que `/estimate` deje de responder 500 (no se puede
  presupuestar).
- **El `enhance_prompt` de Soul** como sustituto de nuestra generación de prompts
  con Claude: es una caja negra por imagen y no conoce la guía de estilo del proyecto.

## 9. Plan priorizado (todo pasa por la cost gate y `max_intentos=1`)

**P0 — esta semana, sin diseño nuevo**

1. **Desbloquear el flujo viejo**: en `higgsfield_client.ENDPOINTS` cambiar el
   default a `kling-video/v2.5-turbo/pro/image-to-video` (acepta `duration` 5|10,
   `cfg_scale` y `negative_prompt` sin quejarse; 0,35 USD los 5 s) o a
   `kling-video/v3.0/std/image-to-video` (0,42 USD sin sonido; duración libre 3-15 s;
   `last_image_url`, `multi_shots`); actualizar `prompts.MODELOS_VALIDOS` y el
   `_extra_params_video` de `dashboard.py:792-800`. Mover `BASE_URL` a
   `https://api.higgsfield.ai` (el documentado; el otro responde igual hoy).
2. **`poll_until_done`**: añadir `nsfw` y `canceled` como terminales con mensaje humano
   ("moderación de contenido rechazó la entrada o el resultado, no se cobra"), tratar
   `completed` sin URL como fallo, mapear 423/503/400-concurrencia a texto legible y
   quitar el `print` de la respuesta cruda (`higgsfield_client.py:130-133`).
3. **Dos pruebas de prompt a 480p con Wan** (≈ 0,25 USD cada una): (a) `@Imagen N` vs
   `Image N` y logos como `Image k`; (b) `SONIDO: … Sin diálogo…` vs añadir *"No
   dialogue. No background music."*. Guardar el resultado en esta carpeta.

**P1 — la mejora de prompts (días)**

4. **"Compilar prompt con IA"** antes de generar: un paso gratis con Claude que toma
   la `ESCENA` de la persona (o la idea del sprint), los activos y la guía de marca, y
   produce un prompt con la fórmula oficial **del modelo elegido**: Wan (`Entity +
   Scene + Motion` + `Shot N [t]` + fórmula de sonido, `Image N`), Seedance 2.5
   (mapeo `Image N` → rol, resumen de una frase, tramos `0-3s…`, notas de
   consistencia, negativos solo subtítulos/audio), Kling (`Shot N, tamaño, ángulo,
   movimiento, estilo`, una acción + un movimiento por plano). El system prompt se
   escribe a partir de los principios del skill `sd25-pe` (intent first, template
   first, cada activo con rol y los no usados listados, parámetros fuera del prompt,
   sin negativos genéricos, una sola versión, hechos del texto vs. observaciones de
   las imágenes) y de la plantilla maestra muerta, recortada. El resultado se muestra
   **editable** y la persona lo aprueba: es el flujo del spec de 2026-09-01 que se
   abandonó, ahora con las reglas de los fabricantes.
5. Alimentar ese compilador con lo que ya calculamos y tiramos: las 9 claves del
   análisis de referencias (`composicion`, `iluminacion`, `estetica`, `storytelling`),
   el `gancho` y la `paleta` de la idea, y la duración elegida para repartir tramos.
6. Placeholder y tres ejemplos por proyecto en la textarea de Crear (patrón de
   open-higgsfield), sacados de `marca.json` y de las 8 recetas del banco.

**P2 — registro como fuente de verdad y reuso (días)**

7. Declarar en `providers/flowplus_modelos.py` `roles` (start/end/reference/video/
   audio con tope) y `settings` (resolución, sonido, cfg, multi_shots…) por modelo, y
   renderizar el formulario de Crear y la descripción del modelo desde ahí, validando
   en el worker antes de gastar (patrón `parseSettings` + re-validación en servidor).
8. Guardar el plano resuelto de cada pieza y exponer **Duplicar** (ya existe
   `creative_flow.duplicar`), hacer que "Editar y crear otra" recupere sonido y música,
   que "Reintentar" permita cambiar prompt/modelo/duración pasando por el estimado, y
   arreglar el flash "Wan 3.0" fijo. Añadir "Aprobados" como vista que nunca se limpia.

**P3 — modelos nuevos vía Higgsfield, cada uno con `/estimate` antes del botón**

9. **Kling 3.0 Std/Pro** en Crear como alternativa a Kling O3 Pro: imagen-a-video con
   `last_image_url` (primer y último fotograma), `multi_shots`, `cfg_scale`, `sound`;
   Std con sonido cuesta 0,126 USD/s frente a 0,14 de O3 Pro en WaveSpeed. Y **Kling
   O3/Omni first-last-frame** (0,112 USD/s) para transiciones entre dos imágenes
   aprobadas.
10. **Soul 2 / Soul Cinema** (0,004-0,006 USD por imagen, lotes de 4) para
    moodboards y "ideas de imagen" de sprint donde no haga falta identidad de
    personaje; Soul reference (0,094) sigue para personajes.
11. **Seedance 2.5 `reference-to-video`, `video-edit` y `video-extend`** solo si
    WaveSpeed no los ofrece al mismo precio: en Higgsfield el estimado no devuelve
    número (hay que calcular con la fórmula de tokens) y el image-to-video sale ~22 %
    más caro que en WaveSpeed (0,46 frente a 0,36 USD/s).
12. **Webhooks `hf_webhook`** para el worker (tenemos URL pública): quita el sondeo y
    reintenta 2 h; deduplicar por `request_id` + estado y conservar el poll como
    respaldo, como recomiendan los docs.

**P4 — borradores baratos**

13. "Borrador a 480p" con Wan (0,05 USD/s) antes de la versión final a 720p/1080p, el
    equivalente al *"Draft at 720p before final 4K"* de la guía de Kling 3.0: encaja
    con la filosofía de aprobar antes de gastar.

## 10. Qué NO se pudo confirmar

- **Precio real de Seedance 2.5 y 2.0 en Higgsfield para nuestra cuenta**: el
  estimado devuelve solo la fórmula de tokens; los USD/s de la sección 3 son cálculo
  nuestro (720p 9:16 = 21 600 tokens/s). El "desde 0,1234 USD/s" de la página pública
  coincide con `video-extend` a 480p, no con image-to-video.
- **Kling 3 Motion Control**: `/estimate` responde 500 en todas las variantes de
  cuerpo probadas; no se sabe si es un fallo temporal o que el modelo no está
  habilitado para la cuenta.
- **Si Kling 3.0 acepta `negative_prompt`**: la API ignora campos desconocidos sin
  error (probado con `motion`, `style`), así que un 200 no prueba que lo use.
- **Que `@Imagen N` no funcione** y que el español degrade el resultado: son
  hipótesis a partir de los docs, sin prueba A/B todavía (P0.3).
- **La ruta de "Marketing Studio Image"** (0,0162 USD/imagen en la página de precios):
  no aparece en el catálogo de open-higgsfield ni en el spec OpenAPI público.
- **El texto completo del skill `sd25-pe`**: se leyó en modo lectura (`skills use`)
  y la salida quedó truncada tras las plantillas de generación; faltan las de
  keyframes/storyboard, edición, extensión y el "Final Self-Check". No se instaló.
- El spec OpenAPI público de docs.higgsfield.ai solo lista rutas antiguas (Kling
  2.1/2.5, Seedance v1, Soul reference, Veo 3.1): el catálogo real hay que
  descubrirlo en la consola o con `/estimate`, como se hizo aquí.

## 11. Fuentes

Repos: `/Users/colorado/Documents/GitHub/open-higgsfield` (README.md,
`src/generation/**`, `src/openhiggsfield/**`) y este repo (`higgsfield_client.py`,
`flowplus_prompt.py`, `generador_prompts.py`, `providers/flowplus_modelos.py`,
`providers/wan3_client.py`, `sprints/ideas.py`, `dashboard.py`, `tareas/flowplus.py`).

Higgsfield (oficial): https://docs.higgsfield.ai/docs/quickstart.md ·
https://docs.higgsfield.ai/docs/authentication.md ·
https://docs.higgsfield.ai/docs/concepts/requests.md ·
https://docs.higgsfield.ai/docs/concepts/polling.md ·
https://docs.higgsfield.ai/docs/how-to/webhooks.md ·
https://docs.higgsfield.ai/docs/concepts/errors.md ·
https://docs.higgsfield.ai/docs/concepts/rate-limits.md ·
https://docs.higgsfield.ai/docs/concepts/billing-and-retention.md ·
https://docs.higgsfield.ai/docs/concepts/file-uploads.md ·
https://docs.higgsfield.ai/docs/openapi.json · https://open.higgsfield.ai/pricing
(3 páginas, leídas con el navegador) · https://higgsfield.ai/blog/higgsfield-api ·
https://higgsfield.ai/blog/seedance-2-5-prompting-guide ·
https://higgsfield.ai/blog/Kling-3.0-is-on-Higgsfield-User-Guide-AI-Video-Generation.
Sonda `/estimate` con nuestra llave: scripts en el scratchpad de la sesión
(`estimar_rutas*.py`), 18 sep 2026.

Kling (oficial): https://kling.ai/quickstart/klingai-video-3-model-user-guide ·
https://kling.ai/quickstart/text-to-video-prompt-guide ·
https://kling.ai/blog/ai-camera-control-movement-prompts-guide.

ByteDance / BytePlus (oficial): https://docs.byteplus.com/en/docs/ModelArk/2607689
(Seedance 2.5 prompt guide) · https://docs.byteplus.com/en/docs/ModelArk/2222480
(Seedance 2.0 series prompt guide) · skill `sd25-pe` v0.1.1 publicado en
`https://arkdocs-en.tos-ap-southeast-1.volces.com/skills/` (leído con `npx skills use`,
sin instalar) ·
https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5.

Alibaba (oficial): https://www.alibabacloud.com/help/en/model-studio/text-to-video-prompt ·
https://www.alibabacloud.com/help/en/model-studio/wan3-video-generation-guide.
