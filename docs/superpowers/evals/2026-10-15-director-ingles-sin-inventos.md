# Eval: el director en inglés y sin nombres ni logos inventados (PND-239 y PND-240), 2026-10-15

**Cambios medidos** (`director.py`), en dos pasos con las mismas entradas:

1. **PND-239** (commit `dfc3a50d`): los planos, las cámaras y las etiquetas del prompt compuesto van en inglés
   (`IDIOMA_PROMPT`, regla 3 del repo); `diferencia_b` sigue en el idioma del proyecto.
2. **PND-240**: la regla 4 ya no pide «nombre» ni «logotipo tal cual» (un activo sin nombre en ACTIVOS se describe por
   lo que se ve; no se nombran logos, marcas, etiquetas ni textos que la IDEA o ACTIVOS no traigan), los ejemplos de los
   tokens dicen «the woman (Image 1)» / «the woman@Image1» en vez de «Ana…», y una validación nueva
   (`_sin_logos_inventados`) devuelve como corrección un plano que nombra un logo que nadie trajo (decir que no hay
   logo siempre vale).

**Cómo:** el modelo de producción (`claude-sonnet-5`), proyecto `colorado_forja` en español (el de pruebas de Creatv),
y un envoltorio que solo observa `Messages.create`. Dos sesiones reales de la prueba del 2026-10-10 (copia de solo
lectura de producción del 2026-10-14) y una armada a mano. El director solo lee texto (la tabla ACTIVOS), no las
imágenes. Corridas fuera de la app: no pasaron por `gastos.registrar_seguro`; quedan anotadas aquí
(`eval:director-<antes|despues239|despues240>:<caso>`).

| caso | antes: stop · salida · US$ · valida | después de 239 | después de 239 + 240 | lo que se buscaba |
|---|---|---|---|---|
| `forja_seedance_persona` (cf_20261010_072542_466338: Seedance 2.5 con varias referencias, 12 s, mujer + botella sin nombre ni logo) | end_turn · 1 703 · 0,0263 · sí · **español** · «para mostrar su **logotipo**» | end_turn · 1 662 · 0,0260 · sí · inglés · «turning its label…», «surface and **logo**» (A y B) | end_turn · 2 221 · 0,0264 · sí · inglés · sin logo ni nombre | el caso que en real inventó «Ana» y un «logotipo plateado» |
| `forja_kling_antes_despues` (cf_20261010_072542_445549: Kling, receta «Antes y después», 10 s) | end_turn · 1 621 + corrección 886 · 0,0356 · sí · **español** | end_turn · 2 267 · 0,0271 · sí · inglés · «**Ana** (Image 2)» y «matte finish and **logo**» (A y B) | end_turn · 1 623 · 0,0209 · sí · inglés · «The woman (Image 2)», sin logo | la receta con actos |
| `armado_wan_lucia_es` (Wan 3.0, 8 s, personaje «Lucía» y producto del catálogo, idea en español) | end_turn · 824 · 0,0118 · sí · **español** | end_turn · 1 346 · 0,0171 · sí · inglés · «Lucía (Image 1)» | end_turn · 998 · 0,0139 · sí · inglés · «Lucia (Image 1)» | un nombre que SÍ viene en ACTIVOS se conserva |

**Lo que mostró:**

- **Idioma (PND-239):** antes los tres prompts salían en español (planos, cámaras y etiquetas). Después, los tres en
  inglés —«Shot 1 (0-4s): medium shot, the camera moves straight toward the subject…», `FIDELITY`, `AVOID`— y
  `diferencia_b` en español en los tres. El texto de la persona (el nombre y la regla del activo, «Botella térmica
  negra 750 ml») va tal cual.
- **Inventos (PND-240):** con solo el cambio de idioma, el ejemplo «Ana (Image 1)» volvió a producir «Ana (Image 2)»
  en Kling (la mujer no tiene nombre en ACTIVOS) y dos casos nombraron un logo que la botella no tiene. Con el cambio de
  PND-240, ningún caso nombra un logo ni inventa un nombre, sin necesitar la corrección (la validación nueva no se
  disparó: la regla del prompt bastó). El personaje con nombre en ACTIVOS se sigue llamando por su nombre, aunque
  Claude lo escribió sin tilde («Lucia») y acortó el del producto («Botella negra mate»); las líneas `CHARACTER` y
  `EXACT PRODUCT` del prompt los llevan exactos.
- **De paso:** en el caso de Seedance Claude puso un id de cámara como tamaño de plano («macro_a_abierto, starts on a
  macro shot…»). No rompe el prompt; queda anotado.
- **Costo:** 0,0737 antes, 0,0702 tras 239 y 0,0612 tras 239 + 240 (los tres casos); ninguna corrección después del
  cambio (antes, una). La revisión de guardian-gasto (2026-10-16) pidió que el precio visto cubra el PEOR caso: dos
  llamadas al tope de 4 000 de salida, ≈ 0,109. La tarifa `director` pasa de 0,05 a 0,11 (se cobra lo real × margen).

**Gasto de esta medición:** US$ 0,2051 (antes 0,0737 · después de 239 0,0702 · después de 240 0,0612).

**Conclusión:** se cierra. Ningún caso que validaba deja de validar, los tres prompts van en inglés con la explicación
en español, y ninguno inventa nombres ni logos. Es una sola muestra por caso: la validación de logos queda como red si
en producción vuelve a aparecer uno; un nombre inventado no tiene red automática (solo la regla).
