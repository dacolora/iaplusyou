# Flow Plus: del guion a los prompts — diseño (Parte A)

Fecha: 2026-09-25. Estado: aprobado por secciones en conversación; pendiente de
revisión escrita. Parte A de dos: **del guion a los prompts** (pasos 1-3 del spec
del cliente). La Parte B (generar imágenes y clips en WaveSpeed desde los
prompts aprobados, encadenando clips) tendrá su propio spec. Cinco bloques de
entrega (§15), cada uno con sus pruebas.

Fuente: el spec del cliente, copiado en `docs/flowplus/workflow-automation-spec.md`
(en adelante «el spec del cliente», citado por sección: §0, §2.4…).

## 0. Propósito y relación con lo que existe

Hoy una persona convierte a mano, conversando con Claude, un guion (de Notion,
con diálogos, hooks alternativos y personajes) en prompts de video por clip
(≤ 15 s, 9:16) y en prompts de imágenes de referencia. El spec del cliente
describe ese proceso para automatizarlo, con reglas que no se negocian: el
diálogo es un subconjunto **literal y en orden** del guion, cada clip dura 5-15 s,
el último clip cierra con hard cut, sin logo ni fundido a negro, y la
verificación la hace el código, no una persona.

Ya existe (commit `2edca51`, rama `flowplus-refinador`): el tercer modo de Crear
«Flow Plus» con el **chat de corrección** (`guiones/refinador.py`, tablas
`guion_prompt`/`guion_mensaje`, migración 0018). Cada prompt tiene texto
original, texto vigente, versión, `texto_fijo` (fragmentos que deben seguir
literales) y se aprueba antes de generar. Este diseño llena ese chat: cada
prompt que produce el pipeline entra con `refinador.crear(..., origen="pipeline")`
y ahí se corrige y se aprueba.

Lo que esta parte agrega en Flow Plus:

- **Guiones**: pegar el texto o traer una página de Notion; Claude lee y el código
  verifica; la persona confirma la lectura.
- **Videos**: una o varias versiones por guion (duración, modo, hook,
  referencias del Catálogo), con recorte de líneas propuesto por Claude y
  decidido por la persona.
- **Clips**: Claude planea, el código calcula duraciones, valida y escribe los
  prompts con plantillas fijas; los prompts entran al chat.
- **Imágenes de referencia**: prompts de personaje/entorno/producto y la tabla
  imagen↔clip.

Nada se genera en esta parte. Todo lo que se paga son llamadas a Claude
(centavos), cada una con su precio a la vista antes del clic y registrada en
`gasto`.

## 1. Decisiones tomadas (2026-09-25)

1. **Claude planea, el código escribe** (opción 1 de la conversación). Claude
   nunca reescribe el diálogo: referencia líneas por número y el código pega el
   texto exacto. La fidelidad textual es por construcción, no por obediencia.
2. **Entrada**: pegar texto **y** link de Notion (llave de integración por
   proyecto, cifrada).
3. **Usuarios**: clientes también (no solo admin). La pantalla se explica sola y
   cada costo se ve antes del clic.
4. **Alcance final**: prompts **y** generar; generar es la Parte B.
5. **Versiones**: cambiar un video ya armado crea una versión nueva; nunca se pisa
   una versión con prompts ya corregidos (spec del cliente §5).
6. **Tokens de referencia**: «Image N» como en el resto de Crear
   (`flowplus_prompt.asignar_tokens`), no «@ImageN» de Higgsfield: los prompts
   quedan listos para la Parte B (WaveSpeed).
7. **Segundo plano**: las llamadas a Claude corren en un hilo
   (`trabajos.iniciar`), no en la cola del worker (que puede estar ocupado con
   renders de minutos), con estado en la base y vencimiento por reinicio, igual
   que el chat.

## 2. Recorrido (UI)

Dentro de Crear › Flow Plus (`_crear_flowplus.html`), arriba de «Prompts sueltos»
(el chat que ya existe), una sección **Guiones**:

1. **Guion.** «Nuevo guion»: textarea para pegar, o campo «Link de Notion» (solo
   si el proyecto conectó Notion; si no, un enlace «Conectar Notion» con la guía
   de §9). Botón «Leer guion · US$ X aprox.». Un documento puede traer varios
   scripts: sale un guion por script, agrupados en un **lote**. Por guion se ve
   la lectura: título, personajes (nombre + descripción), líneas numeradas,
   hooks, notas de estilo, link de video de referencia, palabras y duración
   estimada del guion completo. Cada línea/hook que no aparece literal en el
   texto original se marca «no aparece tal cual en el guion». La persona puede
   editar la lectura (texto de una línea, unir con la siguiente, partir, borrar,
   pasar a hooks, editar/agregar personajes) y «Confirmar guion». Confirmado,
   la lectura ya no se edita (sus videos dependen de ella); para cambiarla:
   «Duplicar guion», gratis, que crea una copia editable.
2. **Video.** «Nuevo video» sobre un guion confirmado. Configuración (§5):
   modo (diálogo a cámara / voz en off), duración objetivo o «guion completo»,
   formato, ritmo, hook, referencias «Image N» (activo del Catálogo o «por
   crear» con descripción y, para personajes, casting: edad, vestuario,
   paleta), estilo (lleno con la guía de marca). Si hay duración objetivo y no
   alcanza: «Proponer qué quitar · US$ X» → la lista de líneas con casillas
   (las propuestas vienen marcadas), la duración estimada y los bloques de
   texto que salen, recalculados en vivo (gratis, §6). La línea 1 no se puede
   quitar.
3. **Clips.** «Armar clips · US$ X aprox.». Mientras corre: «Claude está
   planeando los clips…». Resultado: si alguna validación falla, el video queda
   **inválido** con la lista en rojo y «Volver a armar · US$ X» (Claude recibe
   las fallas). Si pasa: tabla resumen (clip, duración, palabras, título), el
   bloque del video, los clips 1 alternativos por hook con la duración total
   que daría cada uno, avisos de continuidad (no bloquean), y cada clip como
   un prompt del chat (abrir → corregir → aprobar). «Descargar documento (.md)».
   «Nueva versión» (con otra configuración, o editando el bloque del video —
   esto último re-escribe los prompts sin llamar a Claude, gratis).
4. **Imágenes de referencia.** «Escribir prompts de imágenes · US$ X aprox.»
   sobre un video armado: orden recomendado (personajes → entornos → producto),
   un prompt por imagen necesaria (cada uno entra al chat como tipo `imagen`),
   la tabla imagen↔clip y el checklist de lo que falta antes de generar (§8.4).
   «Descargar documento (.md)».

Estados visibles siempre con texto («Leyendo…», «Armado», «Inválido: 2
problemas»…), nunca solo un color.

## 3. Modelo de datos (migración 0019)

Número 0019 porque 0018 es el chat (rama `flowplus-refinador`). Si `main` recibe
otra 0018 antes de mezclar, se renumera al mezclar (§14).

`guion_lote` — un documento pegado o traído de Notion:
`id`, `cliente`, `creado_en`, `actualizado_en` (`_comunes()`); `fuente`
String(10) `texto|notion`; `notion_page_id` String(40) nullable; `titulo`
String(200) (de Notion o de la primera línea); `texto_crudo` Text not null
(≤ 60 000 caracteres); `estado` String(12) `leyendo|leido|error`; `aviso` Text;
`usd` Float default 0; `iniciado_en` String(19) (para el vencimiento); `extra`
JSON.

`guion` — un script dentro de un lote:
`id`, `_comunes()`; `lote_id` FK `guion_lote.id` not null, index; `orden`
Integer; `titulo` String(200); `lectura` JSON (§4.2); `estado` String(12)
`leido|confirmado`; `extra` JSON.

`guion_video` — una versión de un video:
`id`, `_comunes()`; `guion_id` FK `guion.id` not null, index; `version_n`
Integer (1, 2, 3… por guion; UNIQUE `uq_guion_video_version` (guion_id,
version_n)); `nombre` String(120) (p. ej. «80 s · diálogo · v2»); `config` JSON
(§5); `recorte` JSON `{"propuesta": [n], "motivos": {n: str}, "quitadas": [n]}`;
`plan` JSON (lo que devolvió Claude, §7.1, tal cual); `bloque_video` JSON (los
campos del bloque del video, §7.3, editables); `clips` JSON (calculados, §7.2);
`hooks_alt` JSON (clip 1 alternativo por hook, calculado); `validaciones` JSON
(`[{"regla", "ok", "detalle"}]`); `avisos` JSON (continuidad); `imagenes` JSON
(§8); `estado` String(12) `configurando|recortando|armando|armado|invalido|error`;
`estado_imagenes` String(12) `ninguno|escribiendo|listo|error`; `aviso` Text;
`iniciado_en` String(19); `usd` Float default 0; `extra` JSON.

`guion_prompt` (existe): los prompts del pipeline llevan `origen="pipeline"`,
`tipo` `clip|imagen` y en `extra`: `{"guion_id", "video_id", "clip_index",
"variante": "principal" | "hook:<id>", "imagen_id"}`. Consultas por
`json_extract(extra, '$.video_id')` (volumen chico; sin columna nueva).

Llave de Notion: `kv` clave `notion:<cliente>`, valor `cifrado.cifrar(llave)`
(misma derivación que las tiendas: rotar `FLASK_SECRET_KEY` obliga a reconectar).

`guiones/datos.py` es el único escritor de `guion_lote`, `guion` y
`guion_video`; toma el lock de escritura antes de leer en todo RMW (mismo
`_bloquear` que el refinador).

## 4. Paso 1 — Leer el guion (`guiones/lectura.py`)

### 4.1 Llamada a Claude

Entrada: `texto_crudo` entre delimitadores `<documento>` (el cierre se quita del
texto, como en el refinador). Instrucción: separar el documento en scripts y,
por script, devolver **copiando literal** cada línea hablada tal como aparece
(sin re-oracionar ni fusionar, spec del cliente §1.3), los hooks alternativos
aparte, personajes con su descripción, notas de estilo, link de video de
referencia y si el hook tiene una animación/estilo distinto al resto.

```json
{"guiones": [{
  "titulo": "AI podiatrist",
  "video_referencia_url": "https://…" ,
  "personajes": [{"nombre": "AI podiatrist", "descripcion": "AI male podiatrist, British English accent"}],
  "lineas": ["Here are four shoes I would never recommend...", "..."],
  "hooks": ["I would never buy these shoes if my feet were tired by the end of day.", "..."],
  "notas_estilo": "…",
  "hook_con_estilo_distinto": false
}]}
```

### 4.2 Lo que hace el código (puro: `normalizar`, `numerar`, `resumen`)

- Numera líneas `n = 1…` y hooks `hook_1…` (el hook «original» es la línea 1).
- `literal`: cada línea y hook se busca en el texto crudo con espacios
  colapsados y comillas curvas ’‘“” → rectas (la misma normalización que
  `refinador._normalizar`); `false` se marca en la UI.
- `palabras` (de las líneas, sin hooks), `segundos_estimados` = palabras ÷ 2,4.
- `video_referencia_url` solo si es http(s); si no, se descarta.
- Lectura guardada en `guion.lectura`:
  `{"titulo", "video_referencia_url", "personajes": [...], "lineas":
  [{"n", "texto", "literal", "editada": false}], "hooks": [{"id", "texto",
  "literal"}], "notas_estilo", "hook_con_estilo_distinto", "palabras"}`.
- Ediciones de la persona (`POST /guiones/<id>/lectura`) re-numeran y marcan
  `editada: true`; recalculan `literal` contra el texto crudo. Desde la
  confirmación, **la lectura confirmada es la fuente de verdad** de la
  fidelidad (lo editado a mano es decisión de la persona).

## 5. Configuración de un video (`config`)

```json
{
  "modo": "lipsync",                 // lipsync | voiceover
  "duracion_objetivo": 80,           // null = guion completo, sin recorte
  "formato": "9:16",                 // uno de flowplus_modelos.FORMATOS_NOMBRES
  "palabras_por_segundo": 2.4,       // 1.5..4.0
  "aire_por_linea": 0.6,             // solo para el estimado previo al plan (§6)
  "hook": "original",                // "original" (línea 1) | "hook_2"…
  "referencias": [                   // orden = Image 1..N (máx. 7: tope de Kling)
    {"tipo": "personaje", "activo_id": null, "descripcion": "the AI podiatrist, adult British man (~45)",
     "casting": {"edad": "45", "vestuario": "white clinic coat", "paleta": "white, navy"}},
    {"tipo": "entorno", "activo_id": "clinica", "descripcion": ""},
    {"tipo": "producto", "activo_id": "happyflops_original", "descripcion": ""}
  ],
  "estilo": "ultra-photorealistic live-action, …",   // por defecto: marca.guia_efectiva o un estilo genérico
  "voz": "Calm British English male voice"          // opcional; si falta, sale de la descripción del personaje
}
```

- `activo_id` apunta a `catalogo_productos` (`personaje|entorno|producto`); su
  nombre, descripción y regla alimentan la línea del mapa de referencias. Sin
  activo: `descripcion` obligatoria y la imagen queda «por crear» (paso 3).
- Validación de la config en la ruta (400 con mensaje): al menos un slot,
  máx. 7, tipos válidos, hook existente, formato válido, rango del ritmo,
  `duracion_objetivo` ≥ 5 o null.
- El bloque global (§7.3) no vive en la config: es del proyecto
  (`proyecto.json["flowplus_bloque_global"]`, editable en «Avanzado»; vacío =
  el de fábrica).

## 6. Recorte por duración (`guiones/duracion.py` puro + `guiones/recorte.py`)

`duracion.py` (puro, spec del cliente §2.2-§2.3):

- `palabras(texto)` = tokens separados por espacios; `seg_hablados(texto, wps)`.
- `estimado_previo(lineas_conservadas, wps, aire_por_linea)` =
  Σ palabras/wps + aire × n_líneas + 1 s (cuadro final). Es solo una guía para
  el recorte; la duración real sale del plan (§7.2).
- `bloques_quitados(lineas, quitadas)` → textos de las corridas contiguas
  quitadas, en orden (spec del cliente §2.2 paso 5).
- Texto efectivo de la línea 1 = el hook elegido (`config.hook`); todo el resto
  del pipeline trabaja sobre esa sustitución.

`recorte.py` — «Proponer qué quitar» (Claude, solo si `duracion_objetivo` y el
estimado del guion completo la supera): recibe las líneas numeradas y el
objetivo; devuelve `{"orden": [n…], "motivos": {"n": "…"}}` (de menos a más
importante; núcleo = hook, lista de puntos, recomendación del producto,
cierre). El código quita en ese orden, **nunca la línea 1**, hasta que
`estimado_previo ≤ objetivo`; guarda `recorte.propuesta` y la deja marcada en
`recorte.quitadas`. La persona ajusta las casillas (`POST
/videos/<id>/recorte`) y ve el estimado y los bloques quitados en vivo con
`POST /videos/<id>/calcular` (gratis, sin Claude, no guarda nada).

## 7. Paso 2 — Armar clips (`guiones/clips.py` + `guiones/plantillas.py`)

### 7.1 Plan de Claude

Entrada: las líneas conservadas (número + texto efectivo), personajes, notas de
estilo, la config (modo, formato, referencias con su «Image N», estilo), el
ritmo y la regla de duración, y, al rearmar, el plan anterior con la lista de
fallas. Instrucciones clave: agrupar líneas consecutivas en clips coherentes
de 5-15 s; cada momento dice como máximo líneas enteras (por número, nunca
texto); el último momento del último clip es un cuadro sostenido sin diálogo;
`estado_inicio` del clip N+1 igual a `estado_fin` del clip N; declarar qué
entornos usa cada clip; proponer los campos del bloque del video; un clip 1
alternativo por cada hook que no es el elegido, con las mismas líneas que el
clip 1 principal (salvo la 1, que es ese hook) y el mismo `estado_fin`.

```json
{
  "bloque_video": {"conteo_objetos": "…", "disposicion_inicial": "…", "props": "…",
                   "quien_sostiene": "…", "voz": "…"},
  "clips": [{
    "titulo": "Flip-flops: the thin sole",
    "lineas": [3, 4],
    "estado_inicio": "Hands empty.",
    "estado_fin": "Holding ONE flip-flop in his right hand.",
    "entornos": [2],
    "momentos": [
      {"dice": null, "visual": "He reaches down-left and lifts ONE pair…", "aire": 0.5},
      {"dice": [3], "visual": "He holds the flip-flop up beside his face.", "aire": 0.1},
      {"dice": [4], "visual": "Insert macro: the paper-thin edge…", "aire": 0.6}
    ]
  }],
  "hooks": {"hook_2": {"titulo": "…", "lineas": [1, 2], "estado_inicio": "…", "estado_fin": "…",
                       "entornos": [2], "momentos": [...]}}
}
```

Las claves de `hooks` son todos los hooks distintos del elegido; si el elegido
no es `original`, `original` (la línea 1 del guion) también tiene su clip 1
alternativo. `aire` ∈ [0, 6]. Llamada: `max_tokens` 16 000 (el modelo razona antes de
responder y eso cuenta como salida), timeout 240 s, sin reintentos.

### 7.2 Cálculo (puro)

Por clip: `t` acumula `seg_hablados(dice) + aire` por momento (redondeo a 0,1);
`duracion = ceil(Σ)`; si `< 5` se lleva a 5 y el sobrante lo absorbe el último
momento; si `> 15` **no se recorta**: falla V3. El último momento termina
exactamente en `duracion`. Resultado en `guion_video.clips`: por clip `indice`,
`total`, `titulo`, `lineas`, `estado_inicio`, `estado_fin`, `entornos`,
`es_final`, `duracion`, `palabras`, `momentos: [{t_ini, t_fin, dice, texto,
visual}]`. Lo mismo para cada clip 1 alternativo en `hooks_alt`, con
`duracion_total_video` = total − clip 1 principal + ese clip.

### 7.3 Plantillas (puro, `plantillas.py`)

Prompt de un clip = **BLOQUE DEL VIDEO** + **bloque del clip** + **BLOQUE
GLOBAL**, separados por una línea en blanco (spec del cliente §2.4).

- **Bloque del video**, en este orden: `REFERENCE MAP` (una línea por slot:
  `Image N = <character|environment|hero object> — <nombre/descripción>.`; para
  personaje/entorno `Do not copy the background of Image N.`; para producto
  `Preserve its exact geometry, proportions, materials and construction; never
  redesign it.` + la regla del activo si existe), `FORMAT & STYLE` (formato +
  `config.estilo`), `EXACT OBJECT COUNT`, `STARTING LAYOUT` (si hay),
  `PERSISTENT PROP RULES`, `OWNERSHIP LOCK`, `VOICE & AUDIO` (lipsync:
  la voz + `The SAME voice in every clip.`; voiceover: `AUDIO: no speech is
  generated; the voice-over is added in post. Ambient sound only.`). Los
  campos 3-6 salen de `bloque_video`.
- **Bloque del clip**, literal del spec del cliente §2.4:

  ```
  CLIP {i} of {n} — {duracion} seconds — {formato} — {titulo}
  Start image = last frame of Clip {i-1}.            (solo si i > 1)
  START STATE: {estado_inicio}
  DIALOGUE (exact words, natural unhurried pace, lip-sync exactly):     (lipsync)
  VOICE-OVER: added in post, do NOT generate speech. Exact text for timing reference:   (voiceover)
  "{texto exacto de las líneas del clip, unidas por un espacio}"
  TIMED SCRIPT
  {t_ini}–{t_fin}s  [SAY: "{texto}"]  {visual}      (sin [SAY] si el momento no dice nada)
  END STATE: {estado_fin}
  FINAL CLIP: end on the held frame described in the last beat. HARD CUT, no logo, no fade.   (solo el último)
  ```

- **Bloque global** (de fábrica, en inglés): `PHYSICAL CAUSALITY`, `CAMERA`,
  `IDENTITY PRIORITY`, `CLOSING RULES` con el contenido del spec del cliente
  §2.4. Invariante: **todo prompt renderizado pasa `refinador.validar` con su
  `texto_fijo`** (p. ej. las negaciones del fundido van pegadas: «Never fade to
  black», no «…starts or ends with a fade to black», que el validador del chat
  marcaría). Una prueba lo asegura para el bloque de fábrica; al guardar un
  bloque global propio se corre `validar` y se rechaza con los problemas.
- `documento_md(video)` (spec del cliente §2.7): tabla resumen, «cómo funciona
  esto», líneas quitadas, bloque del video, hooks alternativos, todos los
  clips con el **texto vigente** de su prompt del chat, tabla de clips.
  Nombre: `batch-{lote_id}-videos-prompts-{objetivo}s-v{version_n}.md` (o
  `-completo-`).

### 7.4 Validaciones (puro, `clips.validar`) — bloquean

| Regla | Qué comprueba |
|---|---|
| V1 fidelidad | concatenar el texto de todos los momentos con `dice`, en orden de clip y momento, con espacios normalizados = concatenar las líneas conservadas (con la línea 1 = hook elegido) |
| V2 cobertura | la secuencia de números dichos = las líneas conservadas: sin repetidos, sin faltantes, en orden |
| V3 duración | `5 ≤ duracion ≤ 15` en cada clip y en cada clip 1 alternativo |
| V4 continuidad temporal | momentos contiguos, desde 0,0 hasta `duracion` |
| V5 cierre | el último clip tiene la marca FINAL CLIP/HARD CUT y su último momento no dice nada; todo prompt renderizado pasa `refinador.validar` sin problemas |
| V6 total | con objetivo: Σ duraciones ≤ `duracion_objetivo` |
| E1 | las `lineas` de cada clip = los números que dicen sus momentos |
| E2 | el clip 1 empieza con la línea 1 |
| E3 | cada `entornos` apunta a slots de tipo entorno que existen |
| E4 | cada clip 1 alternativo dice las mismas líneas que el clip 1 principal (con su hook) y tiene su mismo `estado_fin` |

Avisos (no bloquean, `avisos`): `estado_fin` de N ≠ `estado_inicio` de N+1 tras
normalizar; `estado_inicio`/`estado_fin` vacío.

Si todo pasa: estado `armado` y, por clip y por clip 1 alternativo, un
`refinador.crear(cliente, texto=prompt, titulo="Clip i de n · {titulo}"
(o "Clip 1 · hook_2 · …"), tipo="clip", contexto=<líneas conservadas + estados
de los clips vecinos>, texto_fijo=[texto de cada línea que dice el clip],
origen="pipeline", extra={...})`. Si algo falla: `invalido`, sin prompts.

### 7.5 Nueva versión

`POST /videos/<id>/nueva-version` con `config` y/o `bloque_video`:
- Solo `bloque_video` distinto y el plan ya existe → versión nueva con el mismo
  plan, re-render y re-validación **sin Claude** (gratis) → `armado` o
  `invalido`.
- Config distinta → versión nueva en `configurando` (el recorte se copia si la
  duración objetivo no cambió).
La versión anterior y sus prompts quedan intactos.

## 8. Paso 3 — Imágenes de referencia (`guiones/imagenes.py`)

### 8.1 Qué imágenes hacen falta (puro)

- Slot `personaje` sin activo → **hoja de personaje**.
- Slot `entorno` sin activo → **imagen de entorno**.
- Slot `producto` → **conversión de estilo** con las fotos reales del activo (si
  el slot de producto no tiene activo, el checklist lo pide: no se inventa el
  producto).
- `hook_con_estilo_distinto` → una imagen aparte por hook, con `STYLE OVERRIDE`.
- Slots con activo de personaje/entorno ya tienen imagen: no se piden.

### 8.2 Llamada a Claude

Recibe esa lista, los personajes del guion, el casting de cada slot, el estilo
y las notas; escribe el cuerpo de cada prompt en inglés:
`{"imagenes": [{"id": "img_1", "slot": 1, "tipo": "personaje", "hook_id": null,
"titulo": "…", "prompt": "…"}]}`. El código:
- Hoja de personaje: antepone `16:9, plain studio background.` y el layout fijo
  (fila superior: 4 vistas de cuerpo completo — frente, 3/4, perfil, espalda;
  fila inferior: 3 primeros planos con expresiones del arco del personaje),
  agrega `The character is fictional and does not resemble any real person.`
- Entorno: `9:16`, sin personas; solo atmósfera, materiales y luz.
- Producto: `Use the attached photos of the real product (Image 1…k).`, `Do not
  redesign the product.`, 3 vistas mínimo (perfil, cenital, 3/4).
- Todas terminan con `No text, no logos, no watermark.` (entorno: `…, no
  people.`), y ese cierre va como `texto_fijo` del prompt en el chat (el chat
  no puede quitarlo).
- El estilo coincide con `config.estilo` (o con el override del hook).

Cada imagen entra al chat: `refinador.crear(..., tipo="imagen",
texto_fijo=[cierre], extra={"guion_id", "video_id", "imagen_id"})`.

### 8.3 Tabla imagen↔clip (pura)

Por clip: los slots de personaje y producto (en todos) + los entornos que el
plan declaró para ese clip, con el nombre de la imagen (activo o «por crear:
img_2»). Sale de `clips`; si una versión nueva cambia el plan, su tabla es la
suya.

### 8.4 Documento y checklist

`documento_imagenes_md(video)` (spec del cliente §3.4): orden recomendado
(personajes → entornos → producto), formato y modelo sugerido por tipo
(Seedream V5 Pro para producto — necesita las fotos; para hojas de personaje y
entornos sin referencia se anota que la Parte B definirá el modelo de texto a
imagen), cada prompt con su **texto vigente**, la tabla imagen↔clip y el
checklist: slots «por crear» sin imagen, producto sin fotos, prompts de clip e
imagen aún no aprobados. Nombre: `batch-{lote_id}-imagenes-referencia-prompts.md`
(se puede sobrescribir: depende de la segmentación vigente).

## 9. Notion (`guiones/notion.py`)

- «Conectar Notion» (Flow Plus): guía de 3 pasos (crear una integración interna
  en notion.so/profile/integrations, compartir la página del guion con ella,
  pegar su llave `ntn_…`/`secret_…`). Guardar exige correo verificado (mismo
  criterio que `dashboard._requiere_correo_verificado`; admins exentos) y prueba
  la llave con `GET /v1/users/me` antes de guardar. «Desconectar» borra la
  fila de `kv`.
- Leer: del link se extrae el id (32 hex, con o sin guiones); la URL nunca se
  usa como destino — solo `https://api.notion.com/v1/…` con `Notion-Version`
  fijo. `GET /pages/{id}` (título) y `GET /blocks/{id}/children` paginado,
  recursivo para bloques con hijos (toggles, columnas) hasta profundidad 4 y
  3 000 bloques; `rich_text[].plain_text` por bloque, un salto de línea por
  bloque, viñetas con «- ». El texto resultante sigue el mismo camino que uno
  pegado (`fuente="notion"`, `notion_page_id`).
- Errores en llano: 401 «La llave de Notion no sirve; vuelve a conectarla»;
  404 «Esa página no está compartida con tu integración de Notion»; 429
  «Notion pidió esperar; intenta en un minuto». La llave nunca va a un log,
  un flash, un evento ni un mensaje de error.

## 10. Rutas (Blueprint `guiones`, JSON, `/cliente/<cliente>/guiones/…`)

Mismo blueprint que el chat (chequeo de mismo origen en todo POST, cuerpo JSON
obligatorio, errores `{"error"}` en español, 404 para lo de otro proyecto).

| Método y ruta | Qué hace |
|---|---|
| `POST /lotes` `{texto}` o `{notion_url}` | crea el lote en `leyendo` y lanza la lectura → 202 `{lote_id}` |
| `GET /lotes/<id>` | estado del lote + sus guiones |
| `GET /guiones` | lotes y guiones del proyecto (resumen) + costos estimados |
| `GET /guiones/<id>` | lectura + versiones de video (resumen) |
| `POST /guiones/<id>/lectura` `{lectura}` | edita la lectura (solo `leido`) |
| `POST /guiones/<id>/confirmar` · `/duplicar` | confirmar / copia editable |
| `POST /guiones/<id>/videos` `{config}` | versión nueva en `configurando` |
| `POST /videos/<id>/config` `{config}` | edita (solo `configurando`) |
| `POST /videos/<id>/calcular` `{quitadas}` | estimado y bloques quitados, gratis |
| `POST /videos/<id>/recorte/proponer` | Claude propone → 202 |
| `POST /videos/<id>/recorte` `{quitadas}` | guarda la decisión |
| `POST /videos/<id>/armar` | arma (o rearma si `invalido`/`error`) → 202 |
| `GET /videos/<id>` | todo: config, recorte, clips, hooks_alt, validaciones, avisos, imágenes, ids de sus prompts |
| `POST /videos/<id>/nueva-version` `{config?, bloque_video?}` | §7.5 |
| `POST /videos/<id>/imagenes` | escribe los prompts de imágenes → 202 |
| `GET /videos/<id>/documento.md` · `/imagenes.md` | descargas |
| `GET /notion` · `POST /notion` `{llave}` · `POST /notion/borrar` | conexión |
| `GET/POST /bloque-global` | leer / guardar el bloque global del proyecto |

La página sondea el `GET` del recurso cada 2 s mientras su estado sea
`leyendo|recortando|armando|escribiendo` (tope 6 min), como el chat.

## 11. Segundo plano, vencimiento y costos

- `trabajos.iniciar(f"guion_{accion}_{id}", fn)`; `fn` nunca lanza: todo
  termina en la fila (`error` + `aviso` en español sin texto de excepción).
- Al leer una fila en estado de trabajo con `iniciado_en` de hace más de 6 min,
  pasa a `error` («Se interrumpió; vuelve a intentarlo»). Un resultado que
  llega después se descarta (el gasto sí queda).
- Un solo punto de llamada a Claude (`guiones/claude.py::llamar_json(system,
  messages, max_tokens, timeout)`), la costura que las pruebas reemplazan; el
  refinador pasa a usarlo también.
- Gasto: tipo nuevo `guion_clips` («Guiones a clips (Flow Plus)» en
  `NOMBRES_TIPO_GASTO`), referencia `guiones:{paso}:{id}:{uuid8}` con `paso` ∈
  `leer|recorte|armar|imagenes`; se registra con los tokens reales, también
  cuando la respuesta no sirvió.
- Estimados (`gastos.estimar("guion_clips", paso=…, palabras=…)`), redondeados
  hacia arriba y mostrados en cada botón: leer ≈ US$ 0,02 + 0,01 por cada 500
  palabras; recorte ≈ US$ 0,02; armar ≈ US$ 0,06 + 0,02 por cada 100 palabras
  conservadas; imágenes ≈ US$ 0,04. Se ajustan con los primeros usos reales
  (el plan deja una tarea para compararlos contra `gasto`).

## 12. Permisos y seguridad

- Rutas con `<cliente>`: `_guard_por_cliente` (clientes y admin del proyecto).
- Todo texto ajeno (documento, lectura, líneas) va a Claude entre delimitadores
  sin su cierre; lo que devuelve Claude se valida por forma antes de guardarse
  y la UI lo pinta solo con `textContent`.
- `texto_crudo` ≤ 60 000 caracteres; lectura ≤ 400 líneas; plan ≤ 40 clips.
- Llave de Notion: §9.

## 13. Pruebas (sin red, sin Claude real)

- `duracion.py`: fórmula con el ejemplo del spec del cliente (clip de 13 s),
  mínimo 5 con sobrante al último momento, > 15 falla, contigüidad.
- `clips.validar`: cada regla V1-V6 y E1-E4 con un caso que pasa y uno que
  falla; hook elegido sustituye la línea 1.
- `plantillas.py`: un clip del podólogo sale con el formato exacto de §7.3
  (comparación de texto completo); lipsync vs voiceover; «Start image» solo
  desde el clip 2; FINAL CLIP solo en el último; todo prompt de fábrica pasa
  `refinador.validar`.
- `lectura.py`: literal/no literal, varios scripts en un lote, numeración,
  edición y re-numeración.
- `recorte.py`: nunca quita la línea 1; se detiene al llegar al objetivo;
  bloques contiguos.
- `imagenes.py`: qué imágenes hacen falta según slots; cierres fijos; tabla
  imagen↔clip.
- `notion.py`: extracción del id, texto desde bloques anidados (respuestas de
  la API simuladas), errores 401/404/429, la llave nunca en un mensaje.
- Pipeline con Claude falso: lote → confirmar → video → recorte → armar →
  prompts en el chat con `texto_fijo` → imágenes; rearmar tras `invalido`;
  vencimiento; gasto registrado.
- Rutas: forma de las respuestas, 404 entre proyectos, 403 sin mismo origen,
  Notion exige correo verificado.
- Navegador (servidor de prueba del scratchpad, Claude falso): recorrido
  completo, celular 375 px.

## 14. Riesgos

- **Número de migración**: si `main` recibe otra 0018/0019 antes de mezclar,
  se renumera la cadena al mezclar (y se prueba `alembic upgrade head` sobre
  una copia de la base de producción).
- **Calidad del plan**: Claude puede agrupar mal o dejar un clip en 16 s; las
  validaciones lo frenan y rearmar le pasa las fallas, pero cuesta otra
  llamada. El chat corrige lo que las validaciones no ven (acción, cámara).
- **Costo real mayor al estimado** en guiones largos (razonamiento del modelo);
  por eso el estimado redondea hacia arriba y se revisa con datos reales.
- **Voz entre clips** (modo diálogo): el generador puede cambiar la voz de un
  clip a otro; se resuelve en la Parte B (voz en off con `final_edition`, o
  unificación de voz), no aquí.
- **Tope de 7 referencias** (Kling O3 Pro): la config no admite más.
- **Nombre del cliente en el repo**: `docs/flowplus/workflow-automation-spec.md`
  nombra a la marca del cliente; si el repo se hace público, quitarlo o
  anonimizarlo.

## 15. Orden de entrega

1. **Guiones**: migración 0019, `datos.py`, `claude.py`, `lectura.py`, rutas de
   lotes/guiones, tipo de gasto, UI del paso 1 (pegar, leer, revisar,
   editar, confirmar).
2. **Video y recorte**: config, `duracion.py`, `recorte.py`, calcular en vivo, UI
   del paso 2.
3. **Clips**: `clips.py`, `plantillas.py`, validaciones, prompts al chat, hooks
   alternativos, nueva versión, bloque global del proyecto, documento `.md`, UI
   del paso 3.
4. **Imágenes de referencia**: `imagenes.py`, tabla imagen↔clip, checklist,
   documento, UI del paso 4.
5. **Notion**: conectar/desconectar, leer página, UI.

Cada bloque termina con la suite rápida en verde y, desde el 1, una prueba en
el navegador con Claude falso. Al final, `CLAUDE.md` gana un párrafo del
pipeline.

## 16. Fuera de esta parte

Generar imágenes y clips, extraer el último cuadro para encadenar, unir los
clips en un video, voz en off con `final_edition` (todo Parte B); escribir de
vuelta en Notion; chequeo automático de continuidad más allá del aviso;
guiones en otros idiomas que no sean los del propio texto (el pipeline no
traduce).
