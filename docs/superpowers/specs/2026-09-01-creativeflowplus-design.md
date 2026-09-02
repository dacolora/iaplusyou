# Diseño: CreativeFlowPlus — tab de generación de video vía plantilla maestra

Fecha: 2026-09-01
Estado: aprobado por el usuario, pendiente de implementación

## Por qué

Los flujos de video que ya existen (`Nueva idea`, `Cambiar calzado`) no producen el
tipo de video cinematográfico narrativo que describe la "Plantilla Maestra —
Prompts de video Happy Flops" (documento aportado por el usuario): referencias
bloqueadas de personaje/producto/escena, guion por tiempos con bullet-time o
narrativa lineal, reglas de cámara explícitas, prioridad de identidad, y reglas
de cierre no negociables (nunca logo, nunca fade to black). Escribir esa
plantilla a mano cada vez es lento y frágil — la idea es que el usuario solo
defina variables simples (Paso 1) y Claude arme las 11 secciones completas de
forma consistente.

Contexto de decisiones previas relevantes:
- [`docs/investigacion/2026-09-01-wan3-seedance-wavespeed.md`](../../investigacion/2026-09-01-wan3-seedance-wavespeed.md) —
  investigación en vivo que determinó que Wan 3.0 vía WaveSpeed AI es la única
  opción ya evaluada que genera video **nuevo** (no edición de uno existente)
  en una sola llamada hasta 30s, con audio nativo — encaja con lo que pide la
  plantilla maestra. Seedance 2.0 `video-edit` vía WaveSpeed quedó documentada
  como alternativa pero NO se conecta en este spec (es edición de un video ya
  existente, un caso de uso distinto al de CreativeFlowPlus).
- `providers/fal_client.py` fue migrado de síncrono a cola asíncrona (queue.fal.run)
  el 1 sep 2026 tras un timeout real con `wan_animate_replace` — no aplica
  directo a este spec (Wan 3.0 va por WaveSpeed, no por fal.ai), pero confirma
  el patrón "lanzar + poll" como el correcto para llamadas largas en este repo.
- El `invariant_block`/`negative_prompt` de la identidad de marca no se tocan
  en este trabajo — CreativeFlowPlus es un tab nuevo, independiente; no
  reemplaza ni modifica `Nueva idea` ni `Cambiar calzado`.

## Flujo nuevo, completo

```
Paso 1 (formulario simple):
  elegir personajes (multi, de la sección "Personajes")
  + elegir productos (multi, de la sección "Productos")
  + elegir escenas (multi, de la sección "Escenas")
  + acción central / detonante (texto libre corto)
  + duración objetivo (12-15s)
  + tono
Paso 2:
  elegir Modo A (bullet-time) o Modo B (narrativa lineal)
  → [generar prompt] (gratis, vía Claude)
  → Claude rellena las 11 secciones de la plantilla maestra completa,
    usando las referencias elegidas etiquetadas (@Imagen 1 = persona1,
    @Imagen 2 = objeto1, @Imagen 3 = escena1, en el orden
    personajes → productos → escenas)
  → el usuario ve el prompt final completo, editable
  → puede regenerar (nueva llamada a Claude) o editar el texto a mano
  → aprueba
  → [generar video] (Wan 3.0 vía WaveSpeed, ~$0.05-0.20/seg, estimate()
    siempre antes de mostrar el botón) usando las mismas referencias +
    el prompt final aprobado
  → el video entra a estado_videos.json exactamente como hoy → aprobación
    final → publicación (sin cambios en este tramo)
```

Cada flecha marcada como "aprueba"/"generar" es una aprobación humana
explícita — no se auto-avanza del prompt al video sin que el usuario lo pida.

## Qué es nuevo vs. qué se reutiliza sin tocar

**Reutilizado tal cual:**
- `clientes/<cliente>/personajes/` y `clientes/<cliente>/productos/` — las
  secciones "Personajes" y "Productos" del Paso 1 leen de estas carpetas ya
  existentes, no hay que subir nada nuevo para esas dos categorías.
- Aprobación final, publicación, `estado_videos.json`, `bitacora.py`,
  `trabajos.py` — nada de esto cambia; el video de Wan 3.0 entra a
  `estado_videos.json` igual que cualquier otro video ya generado.
- `marca.guia_efectiva()` — sigue disponible para que Claude respete la
  identidad de marca al rellenar la plantilla, igual que en `generador_prompts.py`.
- El patrón `trabajos.iniciar(job_id, fn, duracion_estimada)` para la
  generación de video en background, con su barra de progreso ya existente.

**Nuevo:**

1. **`clientes/<cliente>/escenas/`** — carpeta nueva, mismo patrón que
   `personajes/`/`productos/` (binarios, nunca se commitean salvo `.gitkeep`).
   Necesita su propio uploader en el tab (no existe hoy en ningún lado de la app).

2. **`providers/wan3_client.py`** — cliente nuevo para Wan 3.0 vía WaveSpeed AI.
   Lo que quedó **confirmado** en `docs/investigacion/2026-09-01-wan3-seedance-wavespeed.md`
   (1 sep 2026): endpoint base `POST https://api.wavespeed.ai/api/v3/alibaba/wan-3.0/reference-to-video`,
   duración 2-30s en un solo pase, resoluciones 480p/720p/1080p, audio nativo
   opcional, precio $0.05/$0.10/$0.20 por segundo (480p/720p/1080p) — mismo
   `estimate_video(duration, resolution)` con el contrato `{"credits": None,
   "usd": ...}` que el resto de proveedores no-Higgsfield.

   **Lo que NO quedó verificado** (la investigación confirmó el endpoint y sus
   límites, no el body exacto request/response): nombres de campo exactos del
   payload (ej. si la lista de referencias se llama `images`, `image_urls`, o
   algo distinto; si acepta referencias de video/audio en el mismo campo como
   sugiere "reference-to-video"), y la forma exacta de la respuesta de
   polling. Antes de escribir el cliente, hay que repetir el mismo paso que ya
   se hizo para `wavespeed_client.py`/`fal_client.py`: `curl` a
   `wavespeed.ai/models/alibaba/wan-3.0/reference-to-video` (o una llamada real
   de prueba) para confirmar el schema exacto, documentarlo en el docstring del
   cliente con su fecha de verificación, y solo entonces dar la integración por
   cerrada. Se asume el mismo patrón de polling que `wavespeed_client.py` ya
   usa para Wan 2.7 (`POST` → `{"data": {"id": ...}}` → poll
   `/predictions/{id}/result`) como punto de partida, no como hecho confirmado.

3. **`generador_prompts.generar_prompt_creative_flow(variables, modo, plantilla_maestra, guia_estilo)`**
   — nueva función en el mismo módulo que ya concentra las llamadas a
   Anthropic para generar texto (`generar_prompts`, `generar_conceptos_imagen`,
   `evaluar_contra_matriz`). Recibe las variables del Paso 1/2 + el texto
   completo de la plantilla maestra (ver Apéndice) como instrucciones de
   sistema, y devuelve el prompt final relleno (texto largo, NO JSON — a
   diferencia de las otras tres funciones del módulo, esta no necesita el
   parseo de fences/`json.loads` que ya se repite 3 veces ahí).

4. **`creative_flow.py`** — nuevo módulo de estado, mismo patrón que
   `swaps.py`/`conceptos_imagen.py` (un JSON por cliente:
   `clientes/<cliente>/creative_flow_pendientes.json`). Estructura:
   ```json
   {
     "cf_20260901_220000_123456": {
       "creado_en": "...",
       "personajes_ids": ["persona1", "persona2"],
       "productos_ids": ["objeto1"],
       "escenas_ids": ["escena1"],
       "accion_central": "...",
       "duracion_objetivo": 14,
       "tono": "...",
       "modo": "A",
       "estado": "prompt_pendiente|prompt_listo|video_generando|video_listo|error",
       "prompt_relleno": "...",
       "video_url": null,
       "video_local": null,
       "credits": null,
       "usd": null,
       "error": null
     }
   }
   ```
   **Nota de deuda técnica**: el Standards review del 1 sep 2026 ya señaló que
   el boilerplate `cargar()/guardar()` de JSON-por-cliente está duplicado 5
   veces (`estado.py`, `prompts.py`, `marca.py`, `conceptos_imagen.py`,
   `swaps.py`). Este módulo nuevo NO debe ser la sexta copia — debe usar un
   helper compartido (`_json_store.py` con `cargar(path, default)`/`guardar(path,
   data)` genéricos) que se extrae como parte de esta implementación, y los
   5 módulos existentes se migran a usarlo también en el mismo trabajo.

5. **Rutas nuevas en `dashboard.py`**:
   - `POST /cliente/<cliente>/creative_flow/escena/subir` — sube una imagen a
     `clientes/<cliente>/escenas/`.
   - `POST /cliente/<cliente>/creative_flow/generar_prompt` — recibe las
     selecciones del Paso 1/2, llama a `generar_prompt_creative_flow`, crea la
     entrada en `creative_flow_pendientes.json` con `estado: prompt_listo`.
   - `POST /cliente/<cliente>/creative_flow/<id>/regenerar_prompt` — vuelve a
     llamar a Claude con las mismas variables (gratis, se puede repetir).
   - `POST /cliente/<cliente>/creative_flow/<id>/guardar_prompt` — edita el
     texto del prompt final a mano antes de aprobar.
   - `POST /cliente/<cliente>/creative_flow/<id>/generar_video` — dispara Wan
     3.0 en background (`trabajos.iniciar`), mueve el resultado a
     `estado_videos.json` al terminar.
   - `POST /cliente/<cliente>/creative_flow/<id>/descartar` — descarta una
     sesión sin generar video.

6. **Templates nuevos**: `_tab_creativeflowplus.html` (las 3 secciones de
   referencia + Paso 1/2 + lista de sesiones en curso) y una pieza reusable
   para mostrar/editar el prompt final antes de aprobar (mismo espíritu que
   `_prompt_row.html`, pero para texto largo estructurado en vez de una
   descripción corta).

## Qué NO cambia / queda fuera de este spec

- `Nueva idea` y `Cambiar calzado` no se tocan — CreativeFlowPlus es un tab
  aparte, aditivo.
- Seedance 2.0 `video-edit` vía WaveSpeed queda documentado en la
  investigación pero no se conecta — es para editar un video ya existente,
  caso de uso distinto (podría ser una fase 2 si en el futuro se quiere
  re-editar un video ya generado por CreativeFlowPlus).
- El `invariant_block`/`negative_prompt` de marca no cambian — se siguen
  usando tal cual vienen de `marca.guia_efectiva()`.
- No hay generación de múltiples variantes de prompt (a diferencia de
  `generar_prompts()`, que da 5 candidatos) — CreativeFlowPlus da 1 prompt
  relleno por vez, con botón de regenerar si no convence. Esto es intencional:
  cada regeneración es gratis (texto), pero el video final si se aprueba puede
  costar hasta ~$6 (30s a 1080p), así que no tiene sentido generar candidatos
  de video en paralelo como si fueran baratos.

## Errores y casos borde

- Si `generar_prompt_creative_flow` falla (Anthropic caído, respuesta vacía),
  la sesión queda en `estado: error` con el mensaje, se puede reintentar sin
  costo.
- Si Wan 3.0 falla o se cae la conexión durante el poll, igual que
  `wavespeed_client.py`/`fal_client.py` ya hacen: se captura la excepción, se
  guarda un mensaje sanitizado (nunca la URL cruda con la API key, mismo
  cuidado que ya se aplicó en `nano_banana_client.py` tras el incidente de la
  key filtrada), `estado: error`, y se puede reintentar.
- Si el usuario no eligió ninguna escena (o ningún producto), el formulario no
  debe bloquear el envío — la plantilla maestra permite escenas descritas en
  texto sin imagen de referencia si hace falta, pero personaje SÍ es
  obligatorio (la plantilla no tiene sentido sin `@Imagen 1`).
- La duración objetivo se valida en el formulario contra el rango 12-15s antes
  de llamar a Claude (coincide con el no-negociable #1 de la plantilla); si
  Wan 3.0 en la práctica no logra respetar exactamente esa duración, se genera
  igual y se muestra la duración real obtenida.

## Testing

- Generar una sesión real con 1 personaje + 1 producto + 1 escena, Modo A,
  confirmar que el prompt final tiene las 11 secciones y respeta las reglas de
  cierre (sin logo, sin fade to black).
- Confirmar que `@Imagen N` en el prompt final corresponde exactamente al
  orden personajes→productos→escenas elegido.
- Generar el video con Wan 3.0 real, confirmar duración obtenida entre 12-15s
  y que el resultado entra a `estado_videos.json` correctamente.
- Confirmar que `Nueva idea` y `Cambiar calzado` siguen funcionando exactamente
  igual (CreativeFlowPlus es aditivo).
- Confirmar que los 5 módulos de estado migrados al `_json_store` compartido
  siguen leyendo/escribiendo sus JSON existentes sin romper compatibilidad
  (no cambia el formato de archivo, solo quién lo lee/escribe).

## Apéndice: plantilla maestra completa

El texto completo de la "Plantilla Maestra — Prompts de video Happy Flops"
(no negociables, las 11 secciones, tablas de guion por tiempos Modo A/B,
checklist) es el que el usuario aportó en la conversación del 1 sep 2026 — se
usa tal cual, sin editar, como instrucciones de sistema en
`generar_prompt_creative_flow()`. Se guarda como constante en el propio código
(`generador_prompts.py`) en vez de duplicarlo en este documento, para tener
una sola fuente de verdad.
