---
name: eval-claude
description: "Medir una llamada a Claude con casos reales y el modelo real, antes y después de un cambio: tokens, stop_reason, costo, si la respuesta valida y si cumple lo pedido. Cargar antes de dar por bueno un cambio de prompt, rebanada de doctrina, max_tokens, modelo o validación en director.py, sprints/ideas.py, final_edition/guion.py, guiones/, nicho/avatares.py, referentes/lectura.py o clasificar.py, doctrina/revisor.py o diagnostico.py, sprints/qa.py."
---

# Medir una llamada a Claude contra lo real

**Una medición contra datos de prueba no cuenta.** Las pruebas con Claude simulado demuestran que el código lee bien
una respuesta; no demuestran que el modelo real responda dentro del tope, en el formato y con lo pedido. Lo que ya
pasó aquí, y ninguna prueba simulada vio:

- topes de salida chicos: el pensamiento adaptativo gasta del mismo `max_tokens` y la respuesta llegó **vacía**
  (2026-09-26, skill `doctrina`);
- un guion real de 34 líneas **nunca se armó** con 16 000 de tope: hizo falta 48 000 (2026-09-28, medido 19 809 de
  salida el 2026-09-30, skill `flowplus-guiones`);
- duraciones de 141/150/165 s con objetivos de 133/145/155 hasta que Claude recibió el aire disponible (2026-09-30);
- los estimados de avatares no contaban el pensamiento: 47 589 tokens de salida para 94 comentarios (2026-10-01, skill
  `nicho`).

## Cuándo

Antes de cerrar cualquier cambio en el prompt, la doctrina que recibe, `max_tokens`, el modelo
(`generador_prompts.MODEL`) o la validación de una de estas llamadas (verificadas el 2026-10-01):

| Llamada | Dónde |
|---|---|
| Director de Crear | `director.compilar` (`director.py:249`) |
| Ideas de sprint | `sprints.ideas.proponer` (`sprints/ideas.py:405`), tope `max_tokens_para` (`:348`) |
| Guion base de final edition | `final_edition.guion.generar_guion_base` (`final_edition/guion.py:432`) |
| Flow Plus (leer, recorte, clips, imágenes, refinador) | `guiones.claude.pedir_json` (`guiones/claude.py:95`) |
| Avatares | `nicho/avatares.py` (`_llamar`, `:516`) |
| Lectura de Recrear / clasificar referentes | `referentes.lectura.leer` (`:125`) / `referentes.clasificar.clasificar` (`:206`) |
| Revisor, QA, diagnóstico | `doctrina/revisor.py`, `sprints/qa.py`, `doctrina/diagnostico.py` |

## Pasos

1. **Elige 3 a 5 casos reales** de `data/creatv.db` (local, o una copia de producción) que cubran lo que el cambio
   toca: uno normal, uno grande (el que más tokens pide) y uno de los que ya fallaron. Usa un proyecto de Creatv; el
   de un cliente solo con el visto bueno de Daniel. Anótalos (id y por qué) en la tabla del resultado.
2. **Precio primero.** Calcula el costo de la corrida (tokens esperados × `PRECIOS_USD_POR_MILLON`, o la tarifa de
   `gastos.estimar`). Hasta US$ 1 en total se corre sin preguntar. Por encima, muéstrale el precio a Daniel antes.
3. **Antes y después, con las mismas entradas.** La línea base corre con el código de `main` (otro worktree) y el
   cambio con tu rama. Por cada caso anota `stop_reason`, tokens de entrada y salida, US$, segundos, si la respuesta
   pasó la validación (o qué error dio) y el dato que el cambio busca mejorar. El gasto lo anotan las funciones de la app
   como siempre (`gastos.registrar_seguro`); si una corrida no pasa por ellas, anótalo tú con la referencia
   `eval:<tema>:<caso>`.
4. **Escribe el resultado** en `docs/superpowers/evals/AAAA-MM-DD-<tema>.md`:

   ```markdown
   | caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
   ```

   con el total gastado y la conclusión en una línea.
5. **Criterio para cerrar**: ningún caso que antes salía bien sale mal ahora (`max_tokens`, JSON inválido, validación
   rechazada, campo vacío). Si el costo sube más de un 20 %, se explica por qué vale la pena. Un caso en rojo bloquea el
   cierre aunque la suite esté verde.

## Reglas

- La medición usa el modelo de producción (`generador_prompts.MODEL`), nunca uno más barato «para probar».
- Nada de cambiar el código bajo prueba para medirlo (sin parches ni atajos en la función).
- Si no hubo forma de medir (sin saldo de Anthropic, por ejemplo), se dice así en el resultado y en el resumen a Daniel:
  «no medido contra el modelo real».
