# Eval: el idioma de las evaluaciones de cuenta y las claves internas en los prompts (2026-10-13)

**Pedido de Daniel (2026-10-13):** «vamos» a lo que quedó del arreglo de «Cómo mejorarlo»: PND-218 en «Evaluar con
IA» y PND-306 («trend: cansando»); medición «completo, pero con el costo adicional con el cual ganaremos».

**Cambio medido** (rama `idioma-evaluar`):
- `triple_whale.analisis.cierre_idioma(idioma, campos, fijos, …)`: la última línea del mensaje, después de las
  imágenes. En inglés va escrita en inglés, nombra los campos que se escriben en el idioma del proyecto y pide conservar
  tal cual los valores de una lista cerrada (`etapa`, `consciencia`, `accion`, el `lead`/`fuente` del ángulo). La usan
  «Evaluar con IA» de Triple Whale (`analisis.analizar`), la «Evaluación con IA» de Meta
  (`meta_rendimiento.analisis.analizar`) y «Cómo mejorarlo» (`mejorar.cierre_idioma`, que ahora la reusa y suma los
  valores fijos).
- `triple_whale.evaluacion.texto_clave(clave)`: el veredicto, la tendencia, las señales y los anillos sin dato van en
  los datos del prompt por su texto en el idioma de la tarea (el worker corre cada tarea en el de su proyecto), no por la
  clave interna (`perdedor`, `cansando`, `clic_fuerte`).

**Cómo:** las funciones de la app llamadas tal cual con el modelo de producción (`generador_prompts.MODEL`),
`idioma="en"` y dentro de `idiomas.en_idioma("en")` como `worker.ejecutar`. **Antes** = `origin/main` f329ed52 (otro
worktree), **después** = la rama. Mismas entradas, exportadas de producción con una sonda de solo lectura (`mode=ro`,
sin llamar a Meta): la muestra de «Evaluar con IA» de happyflops Noruega (Triple Whale, 30 días: 6 ganadores + 4
perdedores, con su título y copy de `tw_creativo`) y la de la «Evaluación con IA» de Meta de las cuentas de Suecia (30
días: 10 anuncios + 5 recomendaciones), las dos SOLO TEXTO (sin imágenes, como la medición del 2026-10-09: lo que cambia
es texto). «Cómo mejorarlo», sobre los casos de `2026-10-13-mejorar-estaticos-idioma` (con imagen y fotogramas). Proyecto
de cliente con el visto bueno de Daniel; costo aprobado por Daniel (≈ US$ 1,40).

## Resultados

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| Evaluar con IA (TW Noruega, 10 anuncios) | end_turn · 11 058 · 0,1396 · sí (4 ideas) | end_turn · 13 352 · 0,1629 · sí (4 ideas) | todo en inglés, sin claves internas, valores fijos intactos |
| Evaluación de Meta (Suecia, 10 + 5 R) | end_turn · 18 671 · 0,2214 · sí (5 ideas, 8 pasos) | end_turn · 17 495 · 0,2102 · sí (4 ideas, 6 pasos) | ídem |
| Cómo mejorarlo `analisis_1` (estático, Noruega) | — (ver eval del estático) | end_turn · 9 288 · 0,1248 · sí — end_turn · 7 919 · 0,0918 · sí | «trend» por su texto |
| Cómo mejorarlo `video_control` | — | end_turn · 8 407 · 0,1107 · sí | que el video siga igual |

«end_turn»: ninguna se cortó (las tres funciones lanzan con `max_tokens`). US$ = `nicho.avatares.costo_real`.

**Idioma y claves internas en la respuesta:**

| caso | antes | después |
|---|---|---|
| Evaluar con IA | todo en inglés · cita `sin_clic` | todo en inglés · ninguna clave |
| Evaluación de Meta | todo en inglés · cita `clic_fuerte`, `fatiga`, `barato` («Strong CTR ('clic_fuerte')…») | todo en inglés · ninguna clave |
| Cómo mejorarlo `analisis_1` | en español 1 de 2 veces (la corrida «antes» del eval del estático y el análisis de producción) · «(trend: cansando)» al rehacerlo | en inglés · «7-day trend 'Fatiguing'» |
| Cómo mejorarlo `video_control` | en español (su corrida «antes») | en inglés · ninguna clave |

**Valores fijos:** las `etapa` (TOF/MOF/BOF) y las `accion` del plan de Meta (`pausar`, `escalar`, `variantes`,
`revisar`, `consolidar`) llegaron todas válidas en los dos lados; ningún ángulo de las evaluaciones con un valor
inválido. En «Cómo mejorarlo» el `lead` del ángulo sigue saliendo inválido a veces, como antes del cambio (PND-307).

## Lo que mostró

- **Las dos evaluaciones de cuenta ya salieron en inglés antes del cambio en esta corrida:** la deriva al español
  no es fija (el 2026-10-09 fueron 2 de 6 en español). Con el cierre siguen en inglés y lo que cambia a la vista es que
  **dejan de citar claves internas** (la de Meta citaba tres). El cierre queda como seguro, igual que en «Cómo
  mejorarlo», donde sí movió el idioma (1 de 3 → 4 de 4).
- **«Cómo mejorarlo» ya no cita «cansando»:** la tendencia llega como «Fatiguing».
- **Costo:** Evaluar con IA 0,1396 → 0,1629 (+17 %, una corrida por lado: dentro del ruido y por debajo del 20 % de la
  regla); Meta 0,2214 → 0,2102 (−5 %); «Cómo mejorarlo» 0,092–0,125, como antes (0,058–0,133).
- **Una trampa de la propia medición (no de la app):** la primera corrida de «Cómo mejorarlo» armaba su propia app de
  Flask sin el catálogo y mandó las etiquetas en español («Se está cansando»). El corredor pasó a `idiomas.en_idioma`,
  como el worker, y salió «Fatiguing». Dos corridas se cortaron por la red local (un `APITimeoutError` a los 300 s con
  cinco llamadas a la vez y un `APIConnectionError`); se repitieron de una en una.

## Lo que cuesta y lo que ganamos

Cobros cobra el costo REAL de cada llamada por el margen del proyecto (`cobros.libro.cobrar_gasto`); el estimado
(`gastos.estimar`) solo pone el precio del botón y la reserva. happyflops paga ×3 (pospago), haad, happy_fresh y ornate
×2 (margen global), colorado_forja no cobra.

| llamada | costo real medido el 2026-10-13 | precio del botón (estimado × margen) | cobrado ×3 · ganancia | cobrado ×2 · ganancia |
|---|---|---|---|---|
| «Cómo mejorarlo» (un anuncio, con imagen o fotogramas) | 0,058–0,133 (las dos mediciones de hoy) | 0,17 → 0,51 (×3) · 0,34 (×2) | 0,17–0,40 · **0,12–0,27** | 0,12–0,27 · **0,06–0,13** |
| «Evaluar con IA» TW (10 anuncios, solo texto) | 0,14–0,16 | 0,20 → 0,60 · 0,40 | 0,42–0,49 · **0,28–0,33** | 0,28–0,33 · **0,14–0,16** |
| «Evaluación con IA» Meta (10 anuncios, solo texto; con imágenes 0,2245–0,2527, eval 2026-10-10) | 0,21–0,22 | 0,30 → 0,90 · 0,60 | 0,63–0,66 · **0,42–0,44** | 0,42–0,44 · **0,21–0,22** |

El arreglo no cambia lo que cuesta ni lo que se cobra: los precios a la vista son los mismos y, en estas corridas,
quedan por encima del costo medido. **No siempre:** el cobro es el costo real por el margen, sin tope en lo reservado, y
«Evaluar con IA» de Triple Whale puede pasar su estimado (0,08 + 0,012 por anuncio): con una muestra chica (solo la
salida ya cuesta ≈ 0,13) o cuando la primera respuesta se corta en el tope de 16 000 y paga la corrección (0,3031 el
2026-10-09 con 10 anuncios: 0,91 cobrados ×3 contra 0,60 a la vista). Es PND-217, ya abierto, y este cambio no lo
mueve (la corrida «después» usó 13 352 de 16 000).

**Total gastado:** US$ 1,06 en las siete corridas válidas (0,1396 + 0,1629 + 0,2214 + 0,2102 + 0,1248 + 0,1107 +
0,0918), más lo que Anthropic haya cobrado de las dos llamadas que cortó la red (sin datos: el SDK no devuelve uso de
una llamada cortada; a lo sumo ≈ US$ 0,30). Cuenta de Creatv. **Conclusión:** se cierra. Ningún caso que salía bien sale
mal, las respuestas quedan en inglés sin claves internas y los valores fijos llegan intactos.

**Revisión del gasto (2026-10-13), arreglada antes de desplegar:** en la primera versión los datos VERIFICABLES de «Cómo
mejorarlo» (`datos_verificables`) también llevaban los textos de las claves, y «En prueba» o «No spend in the last 7
days» hacían que `ofertas_sin_dato` diera por buena una oferta inventada («Prueba 7 días», «last 7 left») en un gancho
que se genera y se cobra. Lo verificable sigue con la clave (`mejorar._clave`); solo el prompt lleva el texto. No cambia
lo que recibe Claude, así que esta medición vale igual.
