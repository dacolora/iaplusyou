# Eval: el NVP en «Evaluar con IA» y «Cómo mejorarlo» (2026-10-09)

**Cambio medido:** spec 2026-10-09-nvp-visitantes-nuevos §4.5. Los dos prompts de Triple Whale reciben, por anuncio,
«visitantes N · NVP X % → TOF/MOF/BOF (medido)» (o «sin datos del Pixel» / «muy pocos visitantes») y la regla
(`visitantes.REGLA_PROMPT`: 70 / 40, mínimo 50). «Evaluar con IA» además pide que la `etapa` de cada anuncio sea la
medida y que diga cuándo no cuadra con lo que busca la campaña. Durante la medición salió un segundo cambio:
`analisis.MAX_TOKENS` de 16 000 a 32 000, con `timeout=900` (sin él, el SDK exige streaming).

**Cómo:** `analisis.analizar` y `mejorar.armar` + `mejorar.analizar` llamados tal cual, con el modelo de producción
(`claude-sonnet-5`), desde dos worktrees: **antes** = `origin/main` 7a2ee5c, **después** = la rama
`nvp-visitantes-nuevos`. Mismas entradas en los dos lados, exportadas de producción con una sonda de solo lectura
(nada se escribió ni se encoló): la muestra de «Evaluar con IA» de happyflops (Noruega, facebook-ads, 2026-09-10 a
2026-10-09; 1 071 anuncios evaluados, 10 en la muestra) armada con `panel.evaluar_periodo` + `analisis.muestra`, y
las fotos de «Cómo mejorarlo» del ganador con más visitantes y del perdedor con más gasto (`mejorar.foto`), más los
visitantes reales del Pixel de cada anuncio (`pixel_joined_tvf`, mismo modelo y ventana). Sin imágenes, fotogramas ni
voz en ninguno de los dos lados: lo que cambia es el texto. `idioma="en"`. Proyecto de cliente (happyflops), dentro
del «ejecuta todo» de Daniel de este bloque.

## Resultados

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| Evaluar con IA, 10 anuncios (1.ª corrida) | respondió (279 s) pero el script de la medición la leyó mal: tokens no anotados (≈ US$ 0,30) | 16 000 tope ×2 · 32 000 · 0,3406 · **no**: «JSON inválido» (la primera y la corrección llegaron cortadas) | que el NVP no rompa la respuesta |
| Evaluar con IA, 10 anuncios (2.ª corrida) | 1.ª cortada en 16 000 + corrección · 28 466 · 0,3031 · sí | una llamada · 13 065 · 0,1409 · sí | ídem, otra muestra |
| Evaluar con IA, tope 32 000 | — | una llamada · 20 859 · 0,2292 · sí | que el tope nuevo no pida corrección |
| Cómo mejorarlo, ganador `120254135261610640` (NVP 72 %, TOF) | end_turn · 4 994 · 0,0570 · sí | end_turn · 6 191 · 0,0697 · sí | que use la etapa medida |
| Cómo mejorarlo, perdedor `120253165127820640` (NVP 78 %, TOF) | end_turn · 6 376 · 0,0708 · sí | end_turn · 5 030 · 0,0581 · sí | ídem |

«Salida» incluye el pensamiento (sale del mismo `max_tokens`). Las US$ son `nicho.avatares.costo_real` sobre los
tokens que devolvió la llamada.

**Etapa de cada anuncio de «Evaluar con IA» contra la medida por el NVP:**

| anuncio | veredicto | NVP medido | antes | después (16 000) | después (32 000) |
|---|---|---|---|---|---|
| A1 (campaña «Prospecting») | ganador | 30 % BOF | TOF | BOF | BOF |
| A2 | ganador | 72 % TOF | TOF | TOF | TOF |
| A3 (catálogo dinámico) | ganador | 38 % BOF | TOF | BOF | BOF |
| A4 | ganador | 41 % MOF | TOF | MOF | MOF |
| A5 | ganador | 78 % TOF | TOF | TOF | TOF |
| A6 | ganador | 65 % MOF | TOF | MOF | MOF |
| A7 | perdedor | 78 % TOF | TOF | TOF | TOF |
| A8 | perdedor | 48 % MOF | TOF | MOF | MOF |
| A9 | perdedor | 60 % MOF | MOF | MOF | MOF |
| A10 | perdedor | 62 % MOF | BOF | MOF | MOF |
| **aciertos** | | | **4 de 10** | **10 de 10** | **10 de 10** |

## Lo que mostró

- **Sin el NVP, Claude adivina la etapa por el creativo y se equivoca en 6 de 10**: llamó TOF a casi todo. Con el
  NVP acierta las 10 y lee lo que el cliente pidió ver: «el NVP muestra que llegó a audiencia BOF, no TOF como dice el
  nombre» (A1, en una campaña llamada «Prospecting»), y en el resumen «varias campañas etiquetadas TOF/BOF en realidad
  llegan a audiencias MOF o BOF, señal de solapamiento de públicos».
- **«Cómo mejorarlo» usa la etapa para los cambios**: «mismo formato 9x16 TOF», «conserva… el alcance TOF», «un gancho
  fuerte no salva un video TOF largo y vago». Las dos respuestas siguen válidas y el costo no cambia (0,058–0,070).
  `cifras_sin_dato` marcó «15» en el perdedor antes y «15, 18» después: un aviso que ya existía, no bloquea.
- **El tope de 16 000 ya fallaba antes del NVP**: con el prompt de producción la primera respuesta de 10 anuncios
  llegó cortada y solo la salvó la corrección (28 466 tokens, US$ 0,30). Con el NVP una corrida falló en las dos
  llamadas (US$ 0,34 pagados sin resultado) y otra salió en 13 065. La salida varía mucho entre corridas; con 32 000
  la respuesta llegó entera en una llamada de 20 859. Por eso `MAX_TOKENS = 32000` (regla 7 de CLAUDE.md).
- **Costo**: una llamada sola salió entre US$ 0,14 y 0,23 contra US$ 0,20 que se muestra (`evaluacion_tw`, n = 10);
  con corrección, 0,30. El tope nuevo debería quitar la mayoría de las correcciones; falta un promedio de corridas
  reales antes de tocar el precio (PND-210).
- **Idioma**: con `idioma="en"`, 2 de 6 respuestas salieron en español, una de ellas con el prompt de producción: ya
  pasaba (PND-211).

**Gasto total de la medición:** ≈ US$ 1,57 en Anthropic (antes 0,128 + 0,303 + ≈ 0,30 de la corrida mal leída;
después 0,468 + 0,141 + 0,229), con la llave de Creatv y sin filas en `gasto` (corrió fuera de la app). Pasó el
US$ 1 de la skill por dos tropiezos: el error del script (una llamada perdida) y la primera corrida después, que
falló en el tope de 16 000; el resto era necesario para medir el tope nuevo.

**Conclusión:** el NVP en los prompts no rompe ninguna respuesta con el tope nuevo y cambia la lectura de la etapa
de 4/10 a 10/10. El tope viejo de 16 000 ya estaba al borde en producción: se sube a 32 000 en el mismo cambio.
