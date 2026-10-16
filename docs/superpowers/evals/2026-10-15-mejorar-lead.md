# Eval: el `lead` del ángulo de «Cómo mejorarlo» (PND-308, 2026-10-15)

**Pendiente:** el `lead` del ángulo de la versión salía inválido en la mayoría de las respuestas (3 de 3 y 5 de 9 el
2026-10-13; también la `consciencia` en 2 de 9). `doctrina.validar_angulo` lo anotaba como «error: valor_invalido:lead»
y el ángulo quedaba sin arranque. Decisión 2026-10-13: mirar en las respuestas crudas qué escribe Claude y aceptar esos
valores o listarlos en el prompt.

**Respuestas crudas guardadas:** no había. La base local no tiene `tw_analisis` y lo guardado en producción ya pasó por
`validar_angulo` (el valor inválido se cambia por None). Las respuestas de `crudo_antes2.json`/`crudo_despues2.json` del
scratchpad son de «Evaluar con IA», no de «Cómo mejorarlo». Se midió.

**Cómo:** `mejorar.armar` + `mejorar.analizar` tal cual, con el modelo de producción (`generador_prompts.MODEL`), dentro
de `idiomas.en_idioma(idioma)` como el worker, solo texto (sin fotogramas: el `lead` no depende de ellos). La respuesta
cruda se leyó observando `Messages.create`, sin tocar el código bajo prueba. Casos armados con las funciones de la app
(`evaluacion.evaluar` + `mejorar.foto`) y textos de un anuncio de chanclas inventados, sin datos de clientes:
`en_perdedor` (proyecto en inglés, copy en inglés, perdedor), `en_ganador` (inglés, ganador) y `es_perdedor` (español).
Gasto anotado a `_creatv` con la referencia `eval:pnd308:<antes|despues>:<caso>` (`gastos.registrar_seguro`, base local).

## Lo que escribe Claude

| caso | lead crudo | consciencia cruda | antes: lead · consciencia |
|---|---|---|---|
| en_perdedor | `problema-solucion` | `problem-aware` | ok · ok |
| en_ganador | `promesa` | `consciente del producto` | ok · ok |
| en_perdedor (2.ª) | `problema-solución` | `Consciente de la solución` | **inválido** · **inválida** |
| es_perdedor | `problema-solución` | `consciente del problema` | **inválido** · ok |

Claude escribe el arranque y la consciencia **como los nombra la rebanada `angulo` de la doctrina** («*problema-solución*»,
«*proclamación*», «Consciente de la solución»), con tildes, guiones y mayúsculas. `validar_angulo` cambiaba guiones y
espacios por `_` pero no quitaba las tildes, así que `problema_solución` no era `problema_solucion`. «Evaluar con IA» no
tenía el problema porque su system lleva la rebanada `clasificar`, que nombra los arranques con la clave
(`*problema_solucion*`); la de «Cómo mejorarlo» no la lleva.

## El arreglo: aceptar esos valores

`doctrina.normalizar_lead` (nuevo) y `normalizar_consciencia` quitan tildes (`_sin_tildes`), mayúsculas, guiones y
espacios; el arranque también se acepta en inglés (`LEAD_DESDE_INGLES`, como `CONSCIENCIA_DESDE_INGLES`), y la `fuente`
de una prueba sin tildes («Demostración»). Se eligió aceptar y no listar en el prompt: lo que escribe Claude es el nombre
de la doctrina, no un valor inventado, y aceptar no cambia el prompt, ni el costo, ni la caché. Un valor que no es un
arranque («grito») sigue siendo inválido.

## Resultados

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lead y consciencia |
|---|---|---|---|
| en_perdedor | end_turn · 5 273 · 0,0813 · sí | (re-parseada) sí | ok · ok → ok · ok |
| en_ganador | end_turn · 4 072 · 0,0499 · sí | (re-parseada) sí | ok · ok → ok · ok |
| en_perdedor (2.ª) | end_turn · 6 105 · 0,0705 · sí | (re-parseada) sí | inválido · inválida → ok · ok |
| es_perdedor | end_turn · 7 779 · 0,0872 · sí | (re-parseada) sí | inválido · ok → ok · ok |
| es_perdedor (nueva) | — | end_turn · 4 713 · 0,0566 · sí | `problema-solución` → ok · ok |
| en_perdedor (3.ª, nueva) | — | end_turn · 4 422 · 0,0537 · sí | `problema-solución`, `consciente de la solución` → ok · ok |

«Re-parseada» = la MISMA respuesta cruda de la línea base, validada con el código de la rama (las mismas entradas y la
misma salida: el arreglo no cambia lo que se manda a Claude). Ninguna se cortó y todas validaron en los dos lados.

**Total gastado: US$ 0,3992** (6 llamadas, anotadas a `_creatv`).

**Conclusión:** de 4 de 6 ángulos con el arranque perdido (y 2 con la consciencia perdida) en los valores crudos, a 0 de
6; sin tocar el prompt ni el costo.
