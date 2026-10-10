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

## Segunda medición (E2-R8, Task 7b, 2026-10-10)

**Cambio medido** (commit `b0f0db00`): `MAX_TOKENS` 16 000 → 48 000, con el mismo `timeout` de 600 s. `parsear` ahora
rechaza una respuesta sin `resumen`, sin ningún paso de plan o con menos de 3 ideas válidas, y deja 5 como mucho. La
corrección pide el JSON COMPLETO con todas sus secciones (`analisis.correccion`); Triple Whale sigue con su texto. Las
instrucciones piden de 3 a 5 ideas, un plan de 8 pasos como mucho y una sola frase corta por anuncio. El esquema del
JSON no cambió. La barra calcula 360 s (`DURACION_EVALUAR`).

**Cómo:** igual que la primera medición. El código de la rama fue a `/tmp/creatv-e2b` y la base de producción se copió
con `sqlite3.backup`. Una diferencia: `alembic upgrade head` sobre la copia falló porque la copia está en la `0037` de
`main` («Can't locate revision identified by '0037'»). Las dos tablas de E2 se crearon entonces con
`db.metadata.create_all(engine, tables=[db.meta_desglose, db.meta_evaluacion])` y la marca de alembic de la copia no
se tocó. Se corrió con el `.env` de producción sin imprimir ningún valor. Las miniaturas eran reales: se copiaron a R2
y después se borraron (20 borradas, 0 fallidas; `eval1_A1.jpg` y `eval2_A1.jpg` dan 404). `/tmp/creatv-e2b` también se
borró. Los mismos alcances que los casos 1 y 4 de la primera medición: `happyflops`, idioma `en`, muestra de 10
anuncios (6 ganadores y 4 perdedores), 5 con imagen y sin segmentos (`meta_desglose` sigue sin desplegar).

| caso | antes (7a): 1.ª stop · entrada / salida · US$ · s · valida · ideas | después (7b): 1.ª stop · entrada / salida · US$ · s · valida · ideas | lo que se buscaba |
|---|---|---|---|
| «Todas», 30 días (7a caso 1 → 7b c1) | max_tokens (vacía) + corrección · 32 094 / 31 306 · 0,3772 · 320,8 · sí, tras la corrección · 4 | **end_turn**, sin corrección · 20 881 / 21 094 · **0,2527** · **204,8** · sí · **4** | que la primera llamada termine sola y una sola llamada pague |
| Netherlands, 30 días (7a caso 4 → 7b c2) | max_tokens (JSON cortado) + corrección · 26 287 / 23 391 · 0,2865 · 232,8 · sí, tras la corrección · **0** | **end_turn**, sin corrección · 8 418 / 20 763 · **0,2245** · **214,3** · sí · **4** | lo mismo, y que no llegue sin ideas |

«Entrada» es la entrada equivalente (caché: escribir 1,25× y leer 0,1×). En el c1 la caché se escribió (8 303) y en
el c2 se leyó. Los US$ salen de `costo_real` a 2 y 10 US$ por millón.

| caso | cifras_sin_dato | plan | ideas | diagnóstico | patrones + / − | por anuncio (palabras, la más larga) | pasos con enlace |
|---|---|---|---|---|---|---|---|
| c1 | 4 (`47`, `4,100`, `2,092`, `556`) | 8 | 4 | 5 | 3 / 2 | 10 de 10 (22) | 4 |
| c2 | 3 (`1,210`, `9,124`, `15%`) | 8 | 4 | 5 | 2 / 2 | 10 de 10 (16) | 7 |

- **Verde en los dos casos.** La primera llamada termina sola, con ≈ 21 000 tokens de salida: el 44 % del tope nuevo.
  Las respuestas pesan 18 084 y 15 304 caracteres. Ninguna pidió corrección, así que cada evaluación paga una sola
  llamada. Con 16 000 de tope esa salida nunca cabía: por eso fallaban las tres de la primera medición.
- **Lo que trae cada respuesta:** 4 ideas, cada una con su ángulo sin errores y un prompt en inglés de 74 a 96
  palabras. Hay 8 pasos de plan y una nota por cada uno de los 10 anuncios, de una frase de 16 a 22 palabras. Antes, 2
  de las 3 correcciones llegaban sin ideas y con nota solo para 4 de los 10 anuncios.
- **Calidad igual de buena.** El c1 consolida NL, SE y NO por su aprendizaje limitado, pausa los perdedores de las
  cuatro cuentas (R7–R9, R12), cierra World Wide y revisa los anuncios marcados. El c2 pausa A7–A10 y consolida. Además
  escala un 20 % los tres conjuntos que ya salieron del aprendizaje, pide variantes de los que se desgastan y
  replantea los anuncios de whitelisting. Las ideas siguen los ganadores (pies fríos o cansados → alivio, oferta
  directa) y nombran en `basada_en` los anuncios de los que salen.
- **Las cifras sin dato siguen siendo derivadas.** Son sumas de «en juego» de varias R (4 100, 2 092 y 556 SEK por
  día), el total de perdedores (47 = 13 + 18 + 12 + 4), la suma de los aumentos de presupuesto (1 210), el gasto de A8
  más A9 (9 124) o un umbral redondo para el patrón (15 %). Ninguna es inventada, y el aviso de la pantalla basta (E2-R5).
- **Latencia:** 205 y 214 s, una sola llamada en cada caso. Antes la tarea entera tardaba de 233 a 321 s. Una
  respuesta que llegara al tope de 48 000 tardaría unos 500 s a esta velocidad (≈ 100 tokens por segundo), así que el
  `timeout` de 600 s alcanza. La barra calcula 360 s.

**Gasto de esta medición:** US$ 0,4772 (0,2527 + 0,2245), todo Claude. Está anotado en la `gasto` de producción como
`_creatv` / `evaluacion` / `eval:meta_eval_b:c1` y `:c2` (ids 1652 y 1653, detalle «medición eval-claude E2 (segunda,
E2-R8)»). Entre las dos mediciones van US$ 1,4502.

**Tarifa nueva:** `TARIFAS["evaluacion_meta"]` = 0,25 de base y `evaluacion_meta_por_anuncio` = 0,005. Con N = 10 da
US$ 0,30, cuando antes daba 0,40. La base cubre lo que no crece con N: la salida con pensamiento (≈ 0,21) y la doctrina
escrita en caché (≈ 0,02). Cada anuncio suma su bloque de DATOS, su imagen y su nota (≈ 0,004). 0,30 queda por encima
de lo más caro que se midió (0,2527). También queda por encima de lo peor esperable sin corrección: 10 imágenes, caché
fría y segmentos dan ≈ 0,28. Una corrección, que desde E2-R8 solo llega si la respuesta no sirve, costaría otra llamada
(≈ 0,5 en total). En un proyecto que cobra, el saldo puede quedar por debajo de la reserva, como dice la skill `cobros`.

**Conclusión:** se puede cerrar. En los dos casos la primera llamada termina sola, la respuesta valida, trae 4 ideas y
el plan completo, y paga una sola llamada. La evaluación sale a US$ 0,22–0,25, contra 0,29–0,38 antes, y tarda unos
210 s, contra 233–321 s. No medido: `<segmentos>` (sin desplegar) y una muestra con menos de 10 anuncios.
