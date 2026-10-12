# Eval: localizar un guion a noruego y sueco (2026-10-08)

**Cambio medido:** `final_edition/guion.py` pone el nombre del idioma junto al código en el prompt de localización
(«noruego (bokmål) ('no')»), porque con el código solo `'no'` se lee como la palabra «no». La redacción cambia
también para es/en/pt («español ('es')» en vez de «'es'»).

**Cómo:** `guion.localizar_guion(guion_base, idioma, pais, 149.9)` con el modelo de producción (`claude-sonnet-5`,
sin `ANTHROPIC_MODEL` en el `.env` local ni en el del VPS). Antes = `main` 60232e4 (worktree `tw-varias-tiendas`),
después = rama `paises-nordicos` 03da5032. Se observó el SDK (stop_reason y tokens) sin tocar el código bajo prueba.

**Casos:** los dos guiones base de `colorado_forja` (proyecto de Creatv) que había en producción:
`0` = `cf_20260918_192103_590644` (es/CO, 881 caracteres), `1` = `cf_20260917_145315_732404` (es/CO, 921).

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| 0 → es/MX | end_turn · 1 326 · 0,0188 · sí | end_turn · 826 · 0,0109 · sí | que es/en/pt no empeore |
| 0 → pt/BR | end_turn · 826 · 0,0109 · sí | end_turn · 736 · 0,0100 · sí | ídem |
| 1 → es/MX | end_turn · 614 · 0,0088 · sí | end_turn · 1 095 · 0,0136 · sí | ídem |
| 1 → pt/BR | end_turn · 694 · 0,0096 · sí | end_turn · 1 047 · 0,0132 · sí | ídem |
| 0 → no/NO | (no existía NO) | end_turn · 1 012 · 0,0128 · sí | noruego: «Se hva han fant» … «Last ned appen nå», 149,90 kr |
| 0 → sv/SE | (no existía SE) | end_turn · 1 405 · 0,0167 · sí | sueco: «Titta vad den hittade» … «Ladda ner appen nu», 149,90 kr |
| 1 → no/NO | — | end_turn · 750 · 0,0102 · sí | «Se her, dette tror du ikke.» … «Gå inn og lag din egen nå.» |
| 1 → sv/SE | — | end_turn · 675 · 0,0095 · sí | «Kolla in det här, du kommer inte tro det.» … «Gå in och skapa din egen nu.» |

Entrada estable (1 169–1 238 tokens). En es/pt la salida media pasa de 865 a 926 tokens (+7 %, dentro de la variación
entre corridas: el mismo caso va de 614 a 1 095). Ningún caso llegó a `max_tokens` (4 000) ni falló la validación.

**Gasto total:** US$ 0,145 (antes 0,048 + después 0,097), cuenta de Anthropic de Creatv; corrida fuera de la app, sin
fila en `gasto`.

**Conclusión:** el prompt nuevo localiza bien a noruego bokmål y sueco con el precio en coronas, y no empeora es/pt.
