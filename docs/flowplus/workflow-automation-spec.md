# Spec: automatización del workflow guion → prompts de video → prompts de imágenes

Documento para que un desarrollador convierta en pipeline/herramienta el proceso que hoy se hace a mano en esta conversación. Describe entradas, salidas, algoritmos y plantillas de los 3 pasos: (1) presentación del guion, (2) master prompts + prompts de clips con duración, (3) prompts de imágenes de referencia.

Contexto de dominio: la marca es **Happy Flops** (sandalias). Los guiones vienen de un doc de Notion ("ORIGINALS - AI RISKY BATCH") con uno o más scripts, cada uno con texto hablado, hooks alternativos y descripciones de personajes. La salida son prompts de texto en inglés para un generador de video/imagen tipo Higgsfield (formato 9:16, clips de máximo 15 s cada uno, editados juntos en un video final).

---

## 0. Principios que el pipeline debe preservar

Estos son no negociables descubiertos durante el proceso manual; el desarrollador no debe optimizarlos ni "mejorarlos":

1. **Fidelidad textual.** El diálogo/voz en off de cada clip debe ser un **subconjunto exacto, en orden, palabra por palabra** del guion original. Nunca se parafrasea ni se reescribe una frase que se conserva. Si hay que acortar duración, se **eliminan frases completas**, nunca se editan.
2. **Duración por clip.** Cada clip individual dura entre 5 y 15 segundos (límite duro del generador de video). Un video completo se arma con varios clips editados en secuencia.
3. **Reglas de cierre no negociables** (aplican a todo clip generado):
   - Ningún clip termina con el logo de la marca en pantalla.
   - Ningún clip empieza ni termina con fundido a negro / disolvencia a negro.
   - El último clip de cada video cierra con **hard cut** sobre una imagen fija de acción, gesto u objeto.
4. **Continuidad entre clips.** Cada clip declara un `START STATE` y un `END STATE` (qué tiene el personaje en las manos, dónde está cada prop). El `END STATE` del clip N debe ser compatible con el `START STATE` del clip N+1. El último frame de un clip se usa como imagen de arranque (`start_image`) del siguiente.
5. **Todo prompt en inglés.** Las notas para el usuario van en español; el contenido que se pega en el generador va en inglés.
6. **Verificación automática, no manual.** El pipeline debe verificar por código (no por inspección visual) que: (a) el texto de cada video es un subconjunto ordenado exacto del original, (b) cada clip cae en [5,15] s, (c) los tiempos internos de cada clip son contiguos y sin huecos, (d) el último clip de cada video contiene la marca de hard-cut.

---

## 1. Paso 1 — Presentación del guion

### 1.1 Entrada
- Uno o más guiones en texto plano (pegados, subidos, o extraídos de una URL de Notion vía fetch/API).
- Cada guion puede incluir: título/nombre del script, texto hablado principal, descripciones de personajes, link a video de referencia, una o más "hook variations" (variantes de la primera línea/gancho), notas de estilo de animación.

### 1.2 Qué hace este paso
Parsear el texto crudo a una estructura de datos y devolver un **resumen legible para que el usuario confirme antes de continuar** (nunca generar prompts de una vez; siempre mostrar primero qué se entendió).

### 1.3 Modelo de datos — `Script`

```json
{
  "script_id": "script_1",
  "title": "AI podiatrist",
  "reference_video_url": "https://...",
  "characters": [
    {"name": "AI podiatrist", "description": "AI male podiatrist, British English accent"}
  ],
  "lines": [
    {"n": 1, "text": "Here are four shoes I would never recommend..."},
    {"n": 2, "text": "And I see women wearing them on hard floors every single day."}
  ],
  "hook_variations": [
    {"id": "hook_2", "text": "I would never buy these shoes if my feet were tired by the end of day."},
    {"id": "hook_3", "text": "If you're on your feet all the time..."}
  ],
  "style_notes": "Hook animation differs from the rest of the body (if applicable)",
  "word_count": 753
}
```

Reglas de parsing:
- `lines` se segmenta por oración/línea tal como aparece en el documento fuente (no se re-oracionan ni se fusionan líneas del original). Cada línea conserva su número original — este número es la clave que se usa después para "qué se conserva / qué se quita".
- Las hook variations se guardan aparte, nunca se mezclan con `lines`.
- `word_count` = conteo de palabras de `lines` concatenadas.

### 1.4 Salida de este paso (para el usuario)
Un resumen por script: personajes, sinopsis en 2-3 líneas, número de palabras, duración estimada si se leyera completo (ver fórmula en §2.2), y cualquier directriz especial detectada (ej. "el hook tiene una animación distinta al resto del video"). Este resumen es lo que hoy se envía como mensaje de chat antes de tocar los prompts — el pipeline debe exponerlo como un paso explícito con checkpoint humano (aprobar/editar antes de seguir), no saltárselo.

---

## 2. Paso 2 — Master prompts + prompts de clips con duración

### 2.1 Configuración por video — `VideoConfig`

Antes de generar, el pipeline necesita, por cada video, una configuración que hoy se decide conversando con el usuario:

```json
{
  "video_id": "v1",
  "script_id": "script_1",
  "mode": "lipsync",            // "lipsync" (diálogo a cámara) | "voiceover" (voz en off, se genera aparte)
  "target_duration_seconds": 80, // null = usar el guion completo sin recorte
  "aspect_ratio": "9:16",
  "words_per_second": 2.4,       // ritmo natural ~145 wpm; configurable
  "reference_map": [
    {"slot": "@Image1", "kind": "character", "desc": "the AI podiatrist, adult British man (~45)"},
    {"slot": "@Image2", "kind": "environment", "desc": "modern bright podiatry clinic"},
    {"slot": "@Image3", "kind": "hero_object", "desc": "HappyFlops Original slipper"}
  ],
  "style_block": "ultra-photorealistic live-action, ARRI Alexa 35 look, ...",
  "object_count_rules": "...",
  "prop_rules": [...],
  "ownership_lock": "...",
  "voice_audio": "Calm British English male voice, same in every clip, lip-sync exactly."
}
```

`mode` determina dos cosas: (a) si el texto del clip se etiqueta `DIALOGUE` (lipsync) o `VOICE-OVER` (voiceover, con la instrucción "do NOT generate speech, added in post"), y (b) si aplica la regla de "una sola voz generada aparte para todo el video" (voiceover) o "la misma voz debe mantenerse igual en cada clip vía prompt + herramienta de unificación de voz" (lipsync).

### 2.2 Selección de líneas y presupuesto de duración

Cuando `target_duration_seconds` es `null`: se usan **todas** las `lines` del script, en orden.

Cuando `target_duration_seconds` tiene un valor: el pipeline debe producir un subconjunto `kept_lines ⊆ lines` (por número de línea original, preservando orden) tal que la duración total estimada quede en o por debajo del objetivo. Algoritmo recomendado:

1. Calcular `duration(line) = words(line) / words_per_second`.
2. Sumar duración de bloques de puesta en escena por clip (cada beat visual añade unos segundos extra de "aire" no verbal — ver §2.3). Esto es un presupuesto adicional, no solo palabras.
3. Si la suma de todas las líneas excede el objetivo, **eliminar líneas completas** (nunca recortar dentro de una línea) empezando por las de menor relevancia narrativa. La relevancia no es automática de forma confiable — en la práctica esta priorización la decide un humano (qué frases son "core": hook, la lista de puntos principales, la recomendación del producto, el cierre) y las de detalle/ejemplo se quitan primero. El pipeline debe soportar esto como **input editable** (una lista de line-numbers a excluir), no como una decisión 100% automática.
4. Repetir hasta que `sum(duration(kept_lines)) + overhead ≤ target_duration_seconds`.
5. Registrar `removed_lines` (texto exacto, en orden) para mostrarlo al usuario — nunca se descarta silenciosamente qué se quitó.

Salida de este sub-paso: `kept_lines: number[]`, `removed_runs: string[]` (frases quitadas, agrupadas en bloques contiguos, tal como aparecen en el original).

### 2.3 Segmentación en clips

Entrada: `kept_lines` (o todas las líneas si no hay recorte). Salida: lista de `Clip`.

```json
{
  "clip_index": 1,
  "clip_total": 8,
  "title": "Flip-flops: the thin sole",
  "line_refs": [3, 6],
  "start_state": "Hands empty.",
  "end_state": "Holding ONE flip-flop in his right hand.",
  "is_final": false,
  "beats": [
    {"say_line_refs": null, "visual": "He reaches down-left and lifts ONE pair of thin black rubber flip-flops...", "extra_seconds": 0.5},
    {"say_line_refs": [3], "visual": "He holds the flip-flop up beside his face.", "extra_seconds": 0.1},
    {"say_line_refs": [6], "visual": "Insert macro: the paper-thin edge...", "extra_seconds": 0.6}
  ],
  "duration_seconds": 13
}
```

Reglas de segmentación:
- Un clip agrupa 1 o más líneas consecutivas (por número de línea original) cuya duración hablada + overhead cabe en ≤15 s. Si una sola línea no cabe en 15 s (muy raro, pero posible con `words_per_second` bajo), se **divide la puesta en escena en beats**, no el texto — es decir, la línea se dice completa en un beat, y el resto del tiempo del beat es acción visual sin diálogo adicional.
- Cada `beat` tiene: qué se dice en ese instante (`say_line_refs`, puede ser `null` si es puro visual), la descripción de la acción/cámara, y segundos extra de aire no hablado.
- `duration_seconds` de un clip = techo (`ceil`) de la suma de `words(beat.say)/words_per_second + beat.extra_seconds` para todos los beats del clip, con mínimo 5 y máximo 15. El remanente de redondeo se absorbe en el último beat del clip.
- `start_state`/`end_state` son texto libre que describe el estado físico relevante para continuidad (qué sostiene el personaje, dónde está cada prop). Deben ser consistentes: `end_state` del clip N ≈ `start_state` del clip N+1 (mismo objeto en la misma mano, etc.). Esto hoy lo redacta un humano; el pipeline puede al menos **validar** que no haya contradicciones obvias (ej. "Hands empty" seguido de "Still holding X" sin un beat intermedio que recoja X).
- El primer clip de un video incluye el **hook** (la primera frase/gancho). El último clip lleva `is_final: true` y su último beat es una imagen fija sin diálogo con la instrucción explícita de hard-cut.

### 2.4 Plantillas de bloques reutilizables

**MASTER BLOCK** (uno por video, se pega al inicio de cada clip de ese video): se arma concatenando, en este orden fijo:
1. `REFERENCE MAP` — una línea por cada slot de `reference_map`, con el formato `@ImageN = <kind label> — <desc>. ... Do not copy the background of @ImageN.` (para character/environment) o instrucciones de preservar geometría exacta (para hero_object).
2. `FORMAT & STYLE` — `style_block` de la config.
3. `EXACT OBJECT COUNT` — cuántas instancias de cada personaje/prop deben existir, y qué excepciones hay (ej. inserts con "copias idénticas" de un prop para planos de detalle).
4. Reglas de layout inicial si aplica (ej. dónde está cada objeto en la escena al arrancar el video).
5. `PERSISTENT PROP RULES` — descripción física fija de cada prop relevante, para que no cambie de un clip a otro.
6. `OWNERSHIP LOCK` — quién sostiene qué, y qué pasa cuando se suelta un objeto (nunca desaparece ni se duplica).
7. `VOICE & AUDIO` (o `AUDIO` si es silencioso) — descripción de la voz/silencio, y la instrucción de que sea la MISMA en todos los clips.

**GLOBAL BLOCK** (uno solo, igual para todos los videos y todos los clips, se pega al final de cada prompt): contiene 4 secciones fijas que no cambian entre proyectos salvo que el usuario las edite explícitamente:
- `PHYSICAL CAUSALITY` (todo cambio visible tiene causa física, se trata como toma continua salvo los insert cutaways).
- `CAMERA` (el acercamiento es la cámara moviéndose, nunca el objeto agrandándose; un insert muestra el MISMO objeto más cerca).
- `IDENTITY PRIORITY` (lista de prioridad: identidad facial > ojos/boca > cabello > proporciones > vestuario > geometría del hero object > continuidad de manos/objetos > movimiento creíble).
- `CLOSING RULES` (las 3 reglas no negociables del §0, más la regla de que el nombre de marca solo puede aparecer hablado o físicamente en el producto, nunca como plano de cierre tipo anuncio).

**Prompt final de un clip** = `MASTER BLOCK` + bloque específico del clip (ver formato abajo) + `GLOBAL BLOCK`.

Formato del bloque específico del clip (texto plano, no JSON — esto es lo que se pega en el generador):

```
CLIP {clip_index} of {clip_total} — {duration_seconds} seconds — {aspect_ratio} — {title}
Start image = last frame of Clip {clip_index - 1}.        ← omitir si clip_index == 1
START STATE: {start_state}
DIALOGUE (exact words, natural unhurried pace, lip-sync exactly):   ← si mode == lipsync
VOICE-OVER: added in post, do NOT generate speech. Exact text for timing reference:  ← si mode == voiceover
"{texto exacto de las líneas dichas en este clip, concatenadas}"
TIMED SCRIPT
{para cada beat, una línea:}  {t_inicio}–{t_fin}s  [SAY: "{texto del beat}"]  {descripción visual del beat}
END STATE: {end_state}
FINAL CLIP: end on the held frame described in the last beat. HARD CUT, no logo, no fade.   ← solo si is_final
```

### 2.5 Hooks alternativos

Cada script puede traer variantes del hook (primera línea). El pipeline debe generar, para cada variante, un **clip 1 completo alternativo** (mismo formato que cualquier clip, con su propio `duration_seconds` recalculado según el largo de esa variante), no solo el texto suelto. Debe reportar cuánto cambia la duración total del video con cada variante (duración total = duración con clip 1 original − duración del clip 1 original + duración del clip 1 alternativo).

### 2.6 Validaciones automáticas obligatorias (tests, no revisión visual)

Para cada video generado, el pipeline debe correr y reportar:
1. **Fidelidad**: concatenar el texto de todos los beats con `say_line_refs` no nulos, en orden de clip y de beat, normalizar espacios, y comparar contra la concatenación de `kept_lines` del guion original — deben ser **idénticas**.
2. **Cobertura**: el conjunto de `line_refs` usados en todos los clips = `kept_lines` exactamente (sin repetidos, sin faltantes).
3. **Duración por clip**: `5 ≤ duration_seconds ≤ 15` para todo clip.
4. **Continuidad temporal**: dentro de un clip, los intervalos de tiempo de los beats son contiguos, empiezan en 0.0 y terminan exactamente en `duration_seconds`.
5. **Cierre**: el último clip de cada video contiene la marca de hard-cut y no contiene menciones de logo/fundido a negro como cierre.
6. **Duración total** (si había `target_duration_seconds`): `sum(duration_seconds de todos los clips) ≤ target_duration_seconds`.

Cualquier fallo debe bloquear la entrega del documento final (fail loud, no silencioso) — esto reemplaza la revisión manual que hoy se hace con un script ad hoc antes de entregar.

### 2.7 Salida de este paso
Un documento markdown (o los datos estructurados para renderizarlo) con: tabla resumen (video, guion, palabras original→usadas, clips, duración), sección "cómo funciona esto" con las notas de fidelidad/duración/reglas, las frases quitadas por video (si hubo recorte), el `MASTER BLOCK` de cada video, los hooks alternativos, todos los clips en el formato de texto de §2.4, y una tabla resumen de clips (índice, duración, palabras, título).

---

## 3. Paso 3 — Prompts de imágenes de referencia

### 3.1 Entrada
- Los `reference_map` de cada `VideoConfig` del paso 2 (qué slots `@ImageN` existen y qué son: character / environment / hero_object).
- Fotos reales del producto (el hero object real, ej. la sandalia) que el usuario debe adjuntar — estas no se generan, se usan como `[ATTACH: ...]` en los prompts de conversión de estilo.
- Descripciones de personajes tomadas del `Script.characters` (paso 1) y decisiones de casting no especificadas en el guion (edad, vestuario, paleta de color) que hoy se inventan de forma consistente con el tono de marca — el pipeline debe exponer esto como campos editables, no hardcodeados.

### 3.2 Reglas de generación de prompts de imagen

Para cada slot de tipo `character`: generar una **hoja de personaje** (character reference sheet):
- Formato 16:9, fondo de estudio liso.
- Layout fijo: fila superior con 4 vistas de cuerpo completo (frente, 3/4, perfil, espalda), fila inferior con 3 primeros planos de rostro con expresiones distintas relevantes al arco emocional del personaje en el video.
- Debe declarar explícitamente que el personaje es **ficticio** y no se parece a ninguna persona real.
- Debe terminar con `No text, no logos, no watermark.`
- El estilo visual (fotorrealista / claymation / 3D animado) debe coincidir exactamente con el `style_block` del video al que pertenece.

Para cada slot de tipo `environment`: generar una imagen de ambiente **sin personas**, mismo formato que el video final (9:16), que solo fija atmósfera, materiales y dirección de luz — nunca composición exacta a copiar. También termina con `No text, no logos, no watermark, no people.`

Para el `hero_object` (producto real, ej. la sandalia): generar un prompt de **conversión de estilo** que toma la foto real adjunta (`[ATTACH: ...]`) y la reconstruye en el estilo del video (clay, 3D animado, etc.) preservando geometría, proporciones y construcción exactas — instrucción explícita de "no redesign the slipper". 3 vistas mínimo: perfil, cenital, 3/4.

Si un video tiene un **hook con estilo visual distinto al resto** (detectado en el paso 1 como `style_notes`), generar una imagen de referencia aparte por cada variante de hook, con su propio `STYLE OVERRIDE` y sin mezclar con el `style_block` general del video.

### 3.3 Mapeo imagen ↔ clip

El pipeline debe producir, por video, una tabla que indique **qué imagen(es) de ambiente adjuntar en cada clip** (un clip puede necesitar más de un ambiente si la escena cambia de lugar dentro del clip). Esta tabla depende directamente de la segmentación de clips del paso 2 (§2.3): cada vez que se regenera la segmentación (por ejemplo al cambiar `target_duration_seconds`), esta tabla debe regenerarse también — no queda fija.

### 3.4 Salida de este paso
Documento markdown con: orden recomendado de generación (personajes → ambientes → conversión del hero object), formatos y modelo sugerido por tipo de imagen, un prompt en inglés por cada imagen necesaria (agrupados por video, con referencia a qué slot `@ImageN` llena), y la tabla de mapeo imagen↔clip por video. Checklist final de qué falta antes de poder generar los videos.

---

## 4. Orquestación end-to-end

```
Script(s) crudos
   │
   ▼
[Paso 1] Parse + resumen  ──► checkpoint humano: ¿el resumen es correcto?
   │
   ▼
[Paso 2] VideoConfig (por video) + selección de líneas (si hay target de duración)
   │         ──► checkpoint humano: ¿qué frases se quitan? ¿qué modo (lipsync/voiceover)?
   ▼
   Segmentación en clips + MASTER/GLOBAL blocks + hooks alternativos
   │
   ▼
   Validaciones automáticas (§2.6) ──► si falla, no continuar
   │
   ▼
   Documento de prompts de video (markdown)
   │
   ▼
[Paso 3] Prompts de imágenes de referencia (usa reference_map de cada VideoConfig
   │       + segmentación de clips para la tabla imagen↔clip)
   ▼
   Documento de prompts de imágenes (markdown)
```

Puntos de decisión humana que el pipeline **no debe automatizar por sí solo** (requieren input explícito de la persona, con default razonable si no responde):
- Confirmar que el resumen del guion es correcto (paso 1).
- Elegir `target_duration_seconds` por video, o "guion completo sin recorte".
- Elegir qué frases se quitan cuando hay que recortar (el pipeline puede proponer un candidato, pero el usuario aprueba o ajusta).
- Elegir qué hook usar cuando hay variantes.
- Rellenar descripciones de personajes/ambientes que el guion no especifica (edad, vestuario, paleta).
- Aprobar el modelo de generación de video/imagen y confirmar costo antes de generar (fuera del alcance de este documento — esto pasa en la herramienta de generación, no en el pipeline de prompts).

---

## 5. Convenciones de nombres y versionado de documentos de salida

Cada corrida del pipeline con una configuración distinta de duración produce un documento **nuevo**, nunca sobrescribe uno anterior con una configuración diferente — el usuario puede querer comparar versiones (ej. "versión corta de 45 s" vs "versión de 2 min" vs "versión final de 1:20/1:15"). Sugerencia de nombre: `batch-{batch_id}-videos-prompts-{duracion_o_variante}.md` y `batch-{batch_id}-imagenes-referencia-prompts.md` (este último sí se puede regenerar/sobrescribir porque depende de la segmentación vigente, no es una "versión" independiente).

---

## 6. Glosario rápido

- **Clip**: unidad de generación de video, ≤15 s, con un solo prompt.
- **Video**: uno o más clips editados en secuencia = el anuncio final.
- **MASTER BLOCK**: contexto fijo por video (referencias, estilo, props, voz) que se repite en cada clip de ese video.
- **GLOBAL BLOCK**: reglas fijas iguales para todos los videos del proyecto.
- **Beat**: sub-segmento de un clip con su propio texto (opcional) y descripción visual.
- **Hard cut**: corte directo a la última imagen del clip final, sin fundido, sin logo.
- **kept_lines / removed_runs**: qué líneas del guion original se conservan/quitan cuando hay recorte por duración.
