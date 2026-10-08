# Eval: «Cómo mejorarlo» de Triple Whale (2026-10-08)

**Cambio medido:** la llamada nueva a Claude de la tarea `tw_analizar_anuncio` (`triple_whale/mejorar.py`: `armar` →
`analizar`, hasta 8 fotogramas + la voz transcrita + los datos del anuncio, doctrina en el system con caché, tope de
salida `MAX_TOKENS` = 12 000). No hay «antes»: la llamada no existía, así que la tabla trae solo el resultado y lo que
se buscaba con cada caso. Sirve también para medir la tarifa `analisis_anuncio_tw` (PND-179).

**Cómo:** la tarea real `tw_analizar_anuncio`, sin tocar el código bajo prueba: el mp4 se baja de
`files.triplewhale.com` (`descargar_archivo`), ffmpeg saca los fotogramas, Whisper (fal) transcribe la voz y Claude
(`claude-sonnet-5`, el modelo de producción) responde. Corrió sobre una base temporal sembrada con una exportación de
solo lectura de producción; Daniel aprobó la corrida y el uso de los datos del cliente. Cada caso es un análisis
pedido como lo pediría la persona (tarea con `max_intentos=1`, una sola por anuncio).

**Casos:** 4 anuncios reales de Meta de happyflops (proyecto de cliente, con el visto bueno de Daniel): 2 ganadores y 2
perdedores, todos con video, escogidos para cubrir el camino con voz, el camino sin voz y el más grande.

| caso | veredicto | stop | entrada / caché / salida | US$ | s | valida | lo que se buscaba |
|---|---|---|---|---|---|---|---|
| 1 · `120254135261610640` (HappyCozy, 9:16, el que más gastó: 2 833) · 1.ª llamada | ganador | end_turn | 10 419 / escribe 8 315 / 5 326 | 0,0949 | 61,0 | no: el código pidió la corrección | llamada con la caché fría (la que escribe la doctrina) y voz casi muda («you» de Whisper) |
| 1 · misma tarea · corrección | ganador | end_turn | 10 487 / lee 8 315 / 4 438 | 0,0670 | 54,5 | sí | que la corrección arregle lo que la primera no cumplió |
| 2 · `120254215001750640` (HappyComfy, 4:5, 784) | ganador | end_turn | 8 268 / lee 8 315 / 5 454 | 0,0727 | 63,5 | sí | voz en inglés sobre un anuncio noruego: ¿ve el desajuste? |
| 3 · `120253165127820640` (HappyFluffs, UGC 9:16, 2 644) | perdedor | end_turn | 10 933 / lee 8 315 / 6 004 | 0,0836 | 71,0 | sí | el caso grande: voz larga en noruego, más entrada y más salida |
| 4 · `120254045495980640` (HappyCozy, copia, 1 681) | perdedor | end_turn | 9 478 / lee 8 315 / 4 604 | 0,0667 | 54,7 | sí | el camino sin voz: 7 fotogramas, sin Whisper, razones solo con lo visual y el copy |

«Entrada» es `usage.input_tokens` sin la caché; la caché va aparte (escribirla cuesta 1,25× y leerla 0,1×, como en
`sprints.analisis._llamar_contando`). Los US$ son los que la tarea anotó (`gastos.registrar_seguro`, tokens reales).
Segundos de la tarea entera (descarga + fotogramas + Whisper + Claude): 126,7 · 72,6 · 95,8 · 78,8. El tope de la
llamada (`TIMEOUT_CLAUDE_S`) es 300 s: la más lenta fue de 71 s.

**Gasto total:** US$ 0,3874 (Claude 0,3849 + Whisper 0,0025: 0,0009 · 0,0002 · 0,0014 · el caso 4 no tiene voz y no
pagó Whisper). El plan de la medición decía ≈ US$ 0,35. Las filas de gasto (`tw_anuncio:<id>:t901` … `t904` y sus
`:voz`) quedaron en la base temporal de la corrida, no en la `gasto` de producción de happyflops; el cobro real fue de
Anthropic y fal con las llaves de la corrida.

## Lo que mostró

- **Los 4 son válidos** (`estado = lista`), todos con `stop_reason = end_turn` y la salida entre 4 438 y 6 004 tokens,
  la mitad del tope de 12 000 (el pensamiento adaptativo sale del mismo tope y no se comió la respuesta). Ningún caso
  en rojo.
- **1 de 4 necesitó la corrección** (el caso 1): la primera respuesta no pasó `parsear` y la segunda, con la misma
  entrada y el aviso, sí. La corrida no guardó el motivo del rechazo. Cuesta US$ 0,1619 en total contra 0,067–0,084 de
  una llamada sola; la primera llamada además fue la de la caché fría (0,0949, de ellos 0,019 de escribir la doctrina).
  Las otras tres leyeron la caché (8 315 tokens) y salieron entre 0,0667 y 0,0836.
- **La evidencia cita segundos.** Cada caso trae 3 razones que funcionan y 3 que fallan, y cada razón con su evidencia.
  Los segundos y los rangos son concretos: «segundos 3, 9, 15 y 18 muestran la misma acción» (caso 1), «segundo 8» y
  «11,84–15,69» (caso 2), «voz, segundo 17,6–23,8» (caso 3), «Segundo 6–12» (caso 4).
- **Citas de la voz y cifras contra el canal.** En el caso 3 cita la voz en noruego («hvor har du kjøpt de der?») y la
  ubica en el tiempo; en el caso 2 ve que la voz (inglés) no tiene relación con el anuncio noruego y lo vuelve un cambio
  («voz en off en noruego»); en el caso 1 toma el «you» de Whisper como silencio, no como una frase. Las cifras se
  comparan con la mediana del canal, y esas medianas coinciden de un caso a otro (gancho 23,6 % en los casos 1, 3 y 4;
  retención 17,9 % y costo por venta 47,92 en los casos 1, 2 y 3): «gancho 30,0 % vs mediana 23,6 %, percentil 63»,
  «retención 8,9 % vs 17,9 %, percentil 0», «costo por venta 97,91 vs 47,92 del canal».
- **Los cambios son concretos** en 3 de 4 casos: el caso 1 propone el texto de pantalla por segundo (0, 8 y 15), el 2
  cambia el gancho por «HappyComfy er tilbake på lager» calzando con los ganadores de la cuenta, el 3 pide la oferta
  «2 por 1» en pantalla entre los segundos 31 y 37. El menos concreto es el caso 4 (su tercer cambio, «otro ángulo,
  antes/después», es una dirección y no un plano), y el segundo cambio del caso 3 es revisar la landing, útil pero no
  un cambio de creativo. Los 4 traen versión mejorada con título y prompt de video en inglés.
- **Cifras sin dato:** vacío en los casos 1, 2 y 4; el caso 3 marcó `95`, `31` y `37` (aviso, no bloquea). El `95` sale
  de restarle a 100 el percentil 5 de compra: una cifra derivada, no un dato. El `31` es el segundo en que la voz dice
  la oferta (31,1 s) y el `37` el final de un rango que Claude propone para el texto de cierre. Lo del `31` lo arregla
  `mejorar.segundos_verificables`: la parte entera de cada segundo de fotograma y de frase de voz entra al verificable,
  así que citar «el segundo 31» ya no se marca. Un segundo que Claude propone y que no coincide con un fotograma ni con
  una frase (el `37`, si no cae en uno) y una cifra derivada como el `95` pueden seguir saliendo como aviso: no cambia
  el análisis ni el gasto, y un aprendizaje que las contenga no se ofrece ni se guarda.

## La tarifa

La estimación que ve la persona es `TARIFAS["analisis_anuncio_tw"]` + Whisper por la duración (30 s sin dato). Estaba
en US$ 0,08, una cifra inicial. Lo medido:

| | US$ |
|---|---|
| una llamada con la caché caliente (casos 2, 3 y 4) | 0,067–0,084 |
| una llamada con la caché fría (caso 1, 1.ª) | 0,095 |
| la tarea con corrección (caso 1) | 0,162 |
| Whisper | ≤ 0,0014 |
| promedio de los 4 casos (Claude + Whisper) | 0,097 |

**Decisión:** la tarifa pasa a **0,10** (`gastos.py`), esperado ≈ 0,075 × 1,25 + Whisper, redondeado hacia arriba. Con
0,08 el precio mostrado (≈ US$ 0,081 para un anuncio de 30 s) quedaba por debajo del costo real en 2 de los 4 casos (el
1 y el 3); con 0,10 (≈ 0,101) cubre la llamada fría más Whisper y queda cerca del promedio medido (0,097). Un análisis
que necesita la corrección cuesta ≈ 0,16, un 60 % más que el precio mostrado: es el costo real (se anota tal cual) y le
pasó a 1 de 4. La corrección ocurre dentro de la misma tarea (`max_intentos=1`): ninguna tarea repite sola un cobro.

## Criterio para cerrar

Ningún caso en rojo (no hay `max_tokens`, JSON inválido final, validación rechazada ni campo vacío); no hay «antes» con
el que comparar el costo. Sin saldo ni errores de proveedor. Se midió con el modelo real, sin cambiar el código bajo
prueba. Whisper con `language: null` lo aceptó fal (3 de 4 anuncios con voz transcrita), que es lo que esperaba el
PND-185.

**Conclusión:** la llamada responde válida y dentro del tope en los 4 anuncios reales (1 con corrección), con evidencia
de segundos, voz y cifras del canal, y cuesta US$ 0,067–0,084 (0,16 con corrección); la tarifa queda en 0,10.
