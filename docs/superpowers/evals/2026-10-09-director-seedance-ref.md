# Eval: el director con Seedance 2.5 con varias referencias (familia `seedance_ref`), 2026-10-09

Cambio medido: la familia nueva `seedance_ref` de `director._FAMILIAS` (Seedance 2.5 reference-to-video vía fal, que
nombra las imágenes `@Image1`, `@Image2`…) y su validación (`director._TOKEN`). Antes de este cambio el modelo no
existía: no hay «antes» con el mismo modelo, así que la columna «antes» es la primera versión del cambio (ronda 1) y
«después» la que queda (ronda 2). Las familias `wan`, `kling` y `seedance` no cambian: su system prompt es byte a
byte el de `main` (comprobado en `es` y `en`).

Modelo: `claude-sonnet-5` (`director.MODEL` = `generador_prompts.MODEL`, el de producción). Casos armados a mano con un
proyecto de prueba de Creatv (`creatv_eval`, sin guía de marca), sin datos de clientes: la base local solo tiene
sesiones de happyflops y la regla pide el visto bueno de Daniel para usarlas. El director solo lee texto (la tabla
ACTIVOS), no las imágenes, así que URLs falsas no cambian lo que se mide.

| caso | ronda 1: stop · llamadas · salida · US$ · valida | ronda 2: stop · llamadas · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| `normal_8s_es` (personaje + producto + lugar, 8 s, persona) | end_turn · 2 · 983+1106 · 0,0353 · sí (al 2.º intento) | end_turn · 1 · 1175 · 0,0154 · sí | tokens `@Image1..3` bien en el prompt |
| `grande_30s_6refs_es` (6 imágenes, 30 s = 5 planos) | end_turn · 2 · 1910+2000 · 0,0504 · **no**: «el plano 1 cita Image 1, que no existe» → prompt fijo | end_turn · 1 · 2165 · 0,0255 · sí | `@Image1..6` |
| `normal_12s_en` (unboxing, inglés) | end_turn · 2 · 1164+1586 · 0,0369 · **no**: «cita Image 1» → prompt fijo | end_turn · 1 · 1181 · 0,0154 · sí | `@Image1..3` |

Causa de la ronda 1: la regla 4 común ponía de ejemplo «Ana (Image 1)» y la 8 decía «Image N, Video N»; Claude seguía
el ejemplo aunque la tabla ACTIVOS dijera `@Image1`. Arreglo: el ejemplo y la forma de los tokens salen de la familia
(`director._TOKENS_REGLAS`: «Ana@Image1», «@Image1, @Image2…») y, como red, un «Image N» suelto se vuelve «@ImageN» antes
de validar cuando la sesión usa la forma pegada (`_a_tokens_pegados`; un número que no existe sigue rechazado).

Total gastado: US$ 0,18 en Anthropic (ronda 1: 0,1226; ronda 2: 0,0563). Corridas fuera de la app (no pasaron por
`gastos.registrar_seguro`; quedan anotadas aquí).

Conclusión: con la ronda 2 los tres casos validan en la primera llamada, con todos los `@ImageN` correctos y menos de la
mitad del costo de la ronda 1. Ningún caso queda en rojo.
