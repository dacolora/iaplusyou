# Eval: «Cómo mejorarlo» con ganchos y copy nuevo (2026-10-09)

**Cambio medido:** la llamada de `tw_analizar_anuncio` con el prompt nuevo de `triple_whale/mejorar.py` (spec
`2026-10-09-tw-ganchos-y-copy-design.md` §3). El JSON pide dos claves más: `ganchos` (3, con texto en pantalla en el
idioma del anuncio, escena, prompt en inglés, `fotograma_s` y porqué) y `copy_nuevo` (título, texto, porqué). Además,
las cifras se verifican contra los datos y ya no contra el prompt entero (revisión de la Task 2). El tope de salida
sigue en 12 000.

**Cómo:**

- Se usó el mismo guion que el 2026-10-08 (`eval_tw.py`, en la carpeta temporal de la conversación), apuntado a la rama
  `tw-ganchos`.
- Corrió la tarea real, sin tocar el código bajo prueba:
  - el mp4 se baja de `files.triplewhale.com`;
  - ffmpeg saca los fotogramas;
  - Whisper (fal) transcribe la voz;
  - Claude responde con `claude-sonnet-5`, el modelo de producción.
- La base temporal se sembró con la misma exportación de solo lectura de producción. Daniel aprobó el 2026-10-08 el uso
  de esos datos para medir.
- Solo se observa `stop_reason` y `usage` de la respuesta.

**Casos:** los mismos 4 anuncios de Meta de happyflops del 2026-10-08, que sirven de línea base: 2 ganadores y
2 perdedores, todos con video, en noruego.

| caso | antes (2026-10-08): stop · salida · US$ · valida | después (2026-10-09): stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| 1 · `120254135261610640` HappyCozy 9:16, ganador | end_turn · 5 326 + corrección 4 438 · 0,1628 · sí, tras corregir | end_turn · 8 655 · 0,1309 · sí, sin corrección; 3 ganchos y copy | caché fría (escribe la doctrina), voz casi muda |
| 2 · `120254215001750640` HappyComfy 4:5, ganador | end_turn · 5 454 · 0,0729 · sí | 1.ª corrida: end_turn · 6 629 · 0,0864 · válido pero **sin ganchos**. 2.ª: end_turn · 11 323 · 0,1333 · 3 ganchos. Tras la regla nueva: end_turn · 11 226 · 0,1324 · 3 ganchos | un ganador: ¿propone ganchos para escalarlo? |
| 3 · `120253165127820640` HappyFluffs UGC 9:16, perdedor | end_turn · 6 004 · 0,0850 · sí | end_turn · 8 080 · 0,1074 · sí; 3 ganchos y copy | el caso grande: voz larga en noruego, oferta dicha en la voz |
| 4 · `120254045495980640` HappyCozy copia, perdedor | end_turn · 4 604 · 0,0667 · sí | end_turn · 9 364 · 0,1159 · sí; 3 ganchos y copy | sin voz: ganchos solo con lo visual y el copy |

Los US$ son los que anotó la tarea (`gastos.registrar_seguro`, tokens reales; Whisper incluido). Ninguna llamada pasó
de 120 s; el tope de la llamada es 300 s.

**Gasto total de esta medición:** US$ 0,7063.

- 0,4406 de la corrida de los 4 casos.
- 0,1333 de la segunda corrida del caso 2, con la respuesta cruda guardada para ver qué pasó.
- 0,1324 del caso 2 con la regla nueva.

Las filas de gasto quedaron en la base temporal de la corrida.

## Lo que mostró

- **Todos los casos son válidos y con `end_turn`.** Ninguno necesitó la llamada de corrección (antes, 1 de 4). La salida
  va de 6 629 a 11 323 tokens, por debajo del tope de 12 000. Es el doble que antes en el peor caso y conviene
  vigilarla (PND nuevo).
- **Ganchos:**
  - En la primera corrida, 3 de 4 trajeron 3 ganchos. El ganador del caso 2 no trajo ninguno, aunque tenía 8
    fotogramas: Claude los dejó fuera, y la misma entrada dio 3 en la segunda corrida.
  - Arreglo, en el commit `89ebaae5`: la regla del prompt dice ahora que los ganchos van SIEMPRE que haya fotogramas,
    también en un ganador (para escalarlo antes de que se canse). Con la regla nueva, el caso 2 trajo sus 3.
- **`fotograma_s`:**
  - 11 de 12 caen en el segundo de un fotograma visto (por ejemplo 3, 6 y 12 en un video de 20 s, o 11,84 en el de
    27 s).
  - El otro es 8,5, en el caso 4, entre los fotogramas de los segundos 6 y 9. Cae dentro del video, y la preparación lo
    acota contra la duración medida.
- **Idioma:**
  - el texto de los ganchos y el copy salieron en noruego, el idioma del anuncio;
  - escena y porqué, en español, el idioma del proyecto;
  - los prompts, en inglés.
  
  La regla de que las excepciones mandan sobre la línea de IDIOMA funcionó en los 4 casos.
- **Cifras:**
  - Ningún gancho ni copy salió con `cifras_sin_dato`.
  - El copy del caso 3 usa la oferta que dice la voz («kjøp 2 … 1»): es un dato, no una invención.
  - El caso 2 de la primera corrida marcó dos cifras sin dato (72, 77) en el análisis. Se ven con el aviso de siempre.
- **Algo que mirar en la doctrina (sin cifra, no lo marca el verificador):** el copy del caso 1 agrega urgencia
  («Lageret tømmes raskt denne vinteren»: el inventario se acaba rápido). No es un número, pero es una afirmación que
  los datos no muestran. Va como PND para la doctrina del copy.
- **Costo:**
  - una llamada sin corrección cuesta 0,086–0,133, con media 0,110 en la primera corrida;
  - la línea base era 0,097 de media, contando la corrección del caso 1;
  - por llamada, la salida crece un 50 %.
  
  La regla de la tarifa del spec §3.3 (subir a 0,12 si la media pasa de 0,10) se aplicó en el commit `89ebaae5`:
  `analisis_anuncio_tw` = 0,12.

## Criterio para cerrar

- **Ningún caso que antes validaba deja de validar.** Cumple: 4 de 4 válidos y ninguna corrección.
- **Los casos con fotogramas traen 3 ganchos con `fotograma_s` entre los segundos vistos.** Cumple con la regla nueva.
  En la primera corrida un ganador no los trajo, y con la regla nueva sí. Que la regla lo arregla siempre está medido
  en una corrida del caso que falló, no en muchas: si en producción aparece un análisis sin ganchos con video, el
  detalle lo dice y queda el PND de «Volver a analizar».
- **Todos traen `copy_nuevo` en el idioma del anuncio.** Cumple: 4 de 4 en noruego.
- **El costo sube más del 20 % por llamada.** Vale la pena porque cada análisis trae ahora tres anuncios listos para
  probar y un copy listo para Meta. La tarifa se ajustó a lo medido.

## Segunda ronda: el fotograma de arranque y el precio de un clic suelto

**El fotograma.** La prueba real de una variante (caso 3, Kling de verdad) mostró que el clip arranca en el fotograma
elegido CON su subtítulo quemado. El fotograma del segundo 18,46 traía el subtítulo de ese momento, y durante 3 s no
coincidía con la voz que suena debajo.

- **Arreglo** (commit `0cbf026e`): la regla de `fotograma_s` pide un fotograma SIN texto quemado. Si todos lo tienen, se
  usa el primero (el del segundo 0,3), porque su subtítulo es el de la voz del gancho.
- **Medición** con el caso 3: end_turn · 9 647 de salida · US$ 0,1424 · válido.
  - Claude vio que todos los fotogramas del UGC traen subtítulos y eligió el 0,3 en los 3 ganchos.
  - Cada gancho mantiene su movimiento y su texto propios.
  - Es una instrucción al modelo y no una garantía: el código no puede saber si un fotograma tiene subtítulos.

**El precio.** La media de 0,110 sale de una tanda en la que 3 de 4 llamadas leyeron la caché del prompt. Un clic
suelto en una tarjeta, que es el caso normal, va con la caché fría: 0,1309 · 0,1333 · 0,1324 · 0,1424. Un precio
mostrado antes de cobrar no puede quedar por debajo de lo que cuesta ese clic. Por eso la tarifa `analisis_anuncio_tw`
queda en **0,14**, y no en 0,12. Con Cobros se cobra lo real × margen; la tarifa es el precio que se ve antes.

**Gasto total de esta medición:** US$ 0,8487 (0,7063 de la primera ronda + 0,1424). La prueba real de Kling se anota
aparte: US$ 0,336.

## Tercera ronda: tope de salida 20 000 (revisión de gasto, riesgo 1)

La revisión de `guardian-gasto` vio que la salida llegó a 11 323 de 12 000 tokens. Con eso, una respuesta cortada
pagaría la llamada de corrección con el mismo tope. Los cambios son dos:

- `MAX_TOKENS` sube a 20 000 (solo se paga lo usado).
- Si la respuesta corta por `max_tokens`, ya no se reintenta a ciegas: el análisis queda en error con lo pagado anotado.

**Medición** con el caso 2 (el que más salida dio), la caché fría y el tope de 20 000:

- end_turn · **13 013** de salida · US$ 0,1696 · válido, con 3 ganchos y copy;
- con el tope viejo de 12 000, esta respuesta habría llegado cortada y pagada dos veces;
- Claude devolvió `fotograma_s` 13,5, que no es un segundo que haya visto (sus fotogramas eran 0,3 · 4,15 · 8 · 11,84 ·
  15,7…). Por eso el código ahora lleva el segundo al fotograma visto más cercano;
- los clics sueltos medidos con la caché fría quedan entre 0,131 y 0,170, con media de 0,142. La tarifa mostrada pasó a
  0,15 (y en el cierre, a 0,17).

**Gasto total de esta medición:** US$ 1,0183 (0,8487 + 0,1696). El último caso lo pasó por US$ 0,02 del tope de
US$ 1 del eval: lo midió el orquestador porque cambiar `max_tokens` exige medir (skill `eval-claude`), y se anota aquí.

**Conclusión:** se cierra. El análisis con ganchos y copy es válido en los 4 casos reales, sin correcciones, en el
idioma correcto y sin cifras inventadas. La tarifa queda en US$ 0,17 (ver el cierre).

**Cierre (2026-10-10):** por el ruling del controlador, el precio que se ve antes de cobrar no puede quedar por debajo
de lo que costó un clic suelto medido (0,1696): `analisis_anuncio_tw` queda en **0,17**; una tanda con la caché
caliente cuesta menos y se cobra lo real.
