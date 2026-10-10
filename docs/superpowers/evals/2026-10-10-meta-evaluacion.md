# Eval: «Evaluar con IA» de Meta rendimiento (2026-10-10)

**Cambio medido:** la llamada nueva a Claude de la tarea `meta_rend_evaluar` (rama `meta-e2`, HEAD `5a51c731`):
`meta_rendimiento/analisis.py` `preparar` → `armar` → `analizar` (`triple_whale.analisis.llamar_con_correccion` con
`parsear`). La doctrina va en el system con caché, `max_tokens` = 16 000, `timeout` = 600 s, `max_retries` = 0, modelo
`generador_prompts.MODEL` = `claude-sonnet-5`. **No hay «antes»:** la llamada es nueva. La tabla trae solo el
resultado y lo que se buscaba con cada caso. La medición fija la tarifa `evaluacion_meta` (Task 7 de E2).

**Cómo:** el código de la rama se copió al VPS (`/tmp/creatv-e2`, sin `.git`, `clientes`, `data` ni `tests`) junto con
una copia consistente de la base de producción (`sqlite3.backup`). Solo se copió `clientes/happyflops/proyecto.json`,
para el nombre, el idioma y los aprendizajes. La copia estaba en la migración `0037` de `main`, que no existe en la
rama, así que se marcó en `0035` y se aplicó encima la `0036` de la rama: `meta_desglose` y `meta_evaluacion`, sin
chocar con lo que agregan la `0036` y la `0037` de `main`. Cada caso hace lo mismo que la ruta: `analisis.preparar` y
la fila con `datos.crear_evaluacion`, en la copia. Después corre lo de la tarea: `medios`, `piezas_creatv`,
`copiar_miniaturas` a R2 de verdad, `visuales`, `armar` y `analizar` contra el modelo real. Corrió con el `.env` de
producción y sin imprimir ningún valor. El código bajo prueba no se tocó: un envoltorio sobre `Messages.create` solo
anota `stop_reason`, uso y segundos de cada llamada. Al final se borraron de R2 las 30 claves posibles de las
miniaturas (`analisis.borrar_miniaturas` sobre la copia: 30 borradas, 0 fallidas; `eval1_A1.jpg` da 404) y también
`/tmp/creatv-e2`.

**Casos:** happyflops es proyecto de cliente; Daniel pidió E2 para él. La muestra tiene siempre 10 anuncios
(6 ganadores + 4 perdedores) e idioma `en`.

| caso | por qué | stop (1.ª · corrección) | entrada equiv. / salida | US$ | s | valida | lo que se buscaba |
|---|---|---|---|---|---|---|---|
| 1 · «Todas», 30 días (eval 1) | el normal y el más grande: 7 cuentas, 12 recomendaciones, DATOS de 16 576 caracteres, 5 miniaturas | max_tokens · end_turn | 32 094 / 31 306 | 0,3772 | 320,8 | sí, tras la corrección | diagnóstico y plan para todas las cuentas: aprendizaje limitado, perdedores, World Wide en 0,18× |
| 2 · «Todas», 30 días otra vez | varianza | — | — | — | — | **no corrió** | el presupuesto no alcanzaba: después del caso 1 cada corrida costaba ≈ US$ 0,30–0,40 y el tope era US$ 1,20 |
| 3 · «Todas», 7 días (eval 2) | otra ventana de anuncios con las mismas cuentas, y la única con 10 miniaturas | max_tokens · end_turn | 23 029 / 26 321 | 0,3093 | 284,1 | sí, tras la corrección, **sin ideas** | sirve también de varianza del caso 1 |
| 4 · Netherlands (`act_883891256188845`), 30 días (eval 3) | una sola cuenta: DATOS de 10 483 caracteres, 8 recomendaciones, 5 miniaturas | max_tokens · end_turn | 26 287 / 23 391 | 0,2865 | 232,8 | sí, tras la corrección, **sin ideas** | el plan de una cuenta: fatiga, perdedores, consolidar, escalar |

Las llamadas, una por una («entrada» es `usage.input_tokens` sin la caché; escribir la caché cuesta 1,25× y leerla
0,1×, como en `sprints.analisis._llamar_contando`; los US$ salen de `costo_real` a 2/10 US$ por millón):

| caso · llamada | stop | entrada / caché / salida | s | texto de la respuesta |
|---|---|---|---|---|
| 1 · 1.ª | max_tokens | 10 421 / escribe 8 303 / 16 000 | 166,4 | 0 caracteres: todo fue pensamiento |
| 1 · corrección | end_turn | 10 464 / lee 8 303 / 15 306 | 154,3 | 16 916 caracteres (a 694 tokens del tope) |
| 3 · 1.ª | max_tokens | 10 653 / lee 8 303 / 16 000 | 177,2 | 1 077 caracteres, JSON cortado |
| 3 · corrección | end_turn | 10 716 / lee 8 303 / 10 321 | 106,8 | 8 801 caracteres |
| 4 · 1.ª | max_tokens | 7 507 / escribe 8 303 / 16 000 | 155,7 | 8 607 caracteres, JSON cortado |
| 4 · corrección | end_turn | 7 571 / lee 8 303 / 7 391 | 77,0 | 6 932 caracteres |

Lo que salió en cada respuesta válida:

| caso | cifras_sin_dato | plan | ideas | diagnóstico | patrones + / − | por anuncio | pasos con enlace |
|---|---|---|---|---|---|---|---|
| 1 | 5 (`3,431`, `2,205`, `1,241`, `31`, `350`) | 8 | 4 | 5 | 2 / 2 | 10 de 10 | 5 |
| 3 | 1 (`47`) | 8 | **0** | 5 | 4 / 4 | 4 de 10 | 6 |
| 4 | 1 (`770`) | 7 | **0** | 5 | 2 / 2 | 4 de 10 | 6 |

**Gasto total:** US$ 0,9730 (0,3772 + 0,3093 + 0,2865), todo Claude, anotado en la `gasto` de producción como
`_creatv` / `evaluacion` / `eval:meta_eval:c1`, `:c3` y `:c4` (ids 1649–1651, detalle «medición eval-claude E2»). El
estimado de entonces (`evaluacion_tw`: 0,08 + 0,012 × 10 = 0,20) se quedaba corto en las tres.

**Latencia:** la llamada más lenta tardó 177,2 s, un 30 % del tope de 600 s. La tarea entera, con las dos llamadas,
tardó de 233 a 321 s, contra los 150 s de `duracion_estimada` que usa la barra. Sale a unos 95–100 tokens de salida por
segundo: un tope de 32 000 tardaría unos 330–350 s por llamada, todavía dentro de los 600 s.

## Lo que mostró

- **Rojo: 3 de 3 primeras llamadas llegaron a `max_tokens` = 16 000.** Es el fallo que la skill ya conoce: el
  pensamiento adaptativo gasta del mismo tope. En el caso 1 la respuesta llegó vacía; en el 3 y el 4, con el JSON
  cortado. Las tres se salvaron con la corrección pagada, pero la del caso 1 terminó a 694 tokens del tope. Así cada
  evaluación paga dos llamadas (≈ US$ 0,29–0,38 en vez de ≈ 0,15–0,20) y tarda el doble. Una respuesta completa pide
  más de 16 000 tokens de salida (pensamiento + JSON de ≈ 4–5 mil): la corrección del caso 1, la única que trajo todo
  (4 ideas y los 10 anuncios), usó 15 306.
- **La corrección recorta el contenido.** Con «Responde solo el JSON pedido», 2 de 3 respuestas salieron sin ninguna
  idea (el contrato pide 4) y con «por anuncio» en 4 de 10. `parsear` las acepta porque traen patrones. Para la persona
  es una evaluación cobrada sin «Llevar a Crear».
- **Calidad buena en los tres.** Resumen, diagnóstico y plan tienen sentido para HappyFlops:
  - Caso 1. Diagnóstico: conjuntos repartidos en aprendizaje limitado (NL 181/258, PL 81 %, FI 87 %), perdedores que
    siguen gastando, FI y PL bajo la meta de 2,0× y empeorando, World Wide en 0,18× y frecuencia alta en NL/NO. Plan:
    consolidar NL, SE y NO primero (ordenados por SEK por día en juego), pausar perdedores, apagar World Wide. Las 4
    ideas repiten el ángulo «pies fríos → pantufla cálida» de los ganadores, con prompt en inglés.
  - Caso 3. Igual de bien y además ve que el mismo video reciclado gana en SE (ROAS 2,22) y se hunde en PL (0,37), y
    lo atribuye a la audiencia, no al creativo. Pone World Wide primero y junta los 4 R de perdedores en un paso. Sin
    ideas.
  - Caso 4. NL sube a 2,26× gastando 19 % menos; marca la frecuencia de 8,01 como fatiga y lo que en verdad cuelga:
    los anuncios de whitelisting (gancho 11–13 %, ROAS 0,7×). El plan pausa A7–A10, consolida, escala un 20 % lo que
    dicen R4–R6 y propone variantes de los que se desgastan. Una frase mezcla «R1's 'en juego' figure for R2». Sin
    ideas.
- **Las cifras sin dato son derivadas, no inventadas.** Son sumas de los «en juego» de varias R
  (3 431 = 2 314 + 789 + 328), el total de perdedores (47 = 13 + 18 + 12 + 4) o el umbral más bajo de CPA (770). El
  aviso de la pantalla basta (E2-R5).
- **Imágenes:** la copia solo guarda una miniatura válida para 5 de los 10 anuncios en los casos 1 y 4, y para 10 de 10
  en el caso 3. Todas se copiaron a R2 y ninguna era una pieza de Creatv.
- **No medido:** `<segmentos>`. En producción no existe todavía `meta_desglose`: la copia de desgloses de E2 no está
  desplegada, así que los tres casos fueron sin segmentos. Con ellos se suman unas 35 líneas (≈ 1–2 mil tokens de
  entrada, ≈ US$ 0,003–0,005 por llamada), que caben en el margen de la tarifa.

**Tarifa (commit `fc5b4e6e`):** `TARIFAS["evaluacion_meta"]` = 0,30 de base y `TARIFAS["evaluacion_meta_por_anuncio"]`
= 0,01, la misma forma que `evaluacion_tw`. Con 10 anuncios da US$ 0,40, por encima de lo más caro que se midió
(0,3772) y de lo peor posible con este código: las dos llamadas en el tope, ≈ 0,39 con la entrada del caso 1. La base
pesa más porque casi todo el costo es la salida con pensamiento, que no crece con N.

**Conclusión:** la llamada no se puede cerrar así. Las 3 primeras respuestas llegaron a `max_tokens` (una vacía) y 2
de 3 correcciones salieron sin ideas. Hay que subir `MAX_TOKENS` (a 32 000, por ejemplo), volver a medir con estos
mismos casos y recalcular la tarifa. La de 0,40 cubre el código de hoy.
