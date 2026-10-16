# Eval: «Analizar referencias y generar guía de estilo» con tope de 4 000 (PND-342), 2026-10-15

**Cambio medido:** `generador_prompts.analizar_marca` pasa de `max_tokens=400` a `MAX_TOKENS_ANALIZAR_MARCA = 4000`
(regla 7 del repo: con topes chicos el pensamiento adaptativo deja la respuesta vacía o cortada, y cobrada). El prompt y
el modelo no cambian.

**Cómo:** el código de la rama sin el cambio (antes) y con el cambio (después), con las mismas entradas, el modelo de
producción (`claude-sonnet-5`) y un envoltorio que solo observa `Messages.create` (stop_reason y usage). Imágenes
públicas de R2 del proyecto de pruebas de Creatv `colorado_forja` (ninguna de un cliente). Corridas fuera de la app: no
pasaron por `gastos.registrar_seguro`; quedan anotadas aquí con la referencia `eval:marca-<antes|despues>:<caso>`.

| caso | antes (400): stop · entrada · salida · US$ · valida | después (4 000): stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| `dos_imagenes_es` (2 imágenes de 2048×2048) | end_turn · 9 860 · 237 · 0,0221 · sí (631 caracteres) | end_turn · 214 · 0,0219 · sí (564) | el caso normal |
| `cinco_imagenes_es` (2 grandes + 3 medianas) | end_turn · 15 283 · 310 · 0,0337 · sí (827) | end_turn · 310 · 0,0337 · sí (816) | el tope de 5 imágenes |
| `tres_imagenes_en` (proyecto en inglés) | end_turn · 9 219 · 259 · 0,0210 · sí (745) | end_turn · 253 · 0,0210 · sí (738) | otro idioma |
| `cinco_grandes_es` (4 de 2048 o más + 1 mediana) | end_turn · 21 528 · 311 · 0,0462 · sí (837) | end_turn · 349 · 0,0465 · sí (925) | el más caro posible |

**Lo que mostró:**

- Los cuatro casos son válidos y terminan con `end_turn` en las dos versiones; la salida queda en 214–349 tokens, lejos
  de los dos topes. Con este modelo y este prompt el 400 no llegó a cortar ninguna respuesta, pero no dejaba margen al
  pensamiento adaptativo; con 4 000 se paga lo mismo (solo lo usado).
- **El precio a la vista estaba por debajo de lo que cuesta.** Una imagen grande son ~4 700 tokens de entrada: con
  cinco imágenes la llamada cuesta 0,034–0,047 y la tarifa `analizar_marca` decía 0,025. Se sube a **0,05** (lo más
  caro medido, redondeado hacia arriba, como el director). Con Cobros se cobra lo real × margen; la tarifa es el precio
  que se ve y se reserva antes.

**Gasto de esta medición:** US$ 0,2461 (antes 0,1230 · después 0,1231).

**Conclusión:** se cierra. Ningún caso cambia de resultado, el costo por llamada no cambia y el precio que se ve pasa a
cubrir el caso de cinco imágenes grandes.
