# Eval: la comprobación de cifras inventadas (PND-227, PND-228 y PND-237), 2026-10-15/16

**Cambio medido** (un solo arreglo, decisión 2026-10-13, lote 2):

- **PND-227**: `doctrina.verificar_cifras` compara valores y no dígitos pegados (`_valores`): «4,0» y «5.00» valen 4 y
  5 (antes 40 y 500); un separador seguido de tres cifras puede ser de miles o decimal («89.900» → 89 900 u 89,9).
- **PND-237**: un solo dígito con palabra de oferta o de escasez se verifica (`_RE_DIGITO_OFERTA`: «Últimas 3»,
  «Garantía de 5 años», «Prøv i 7 dager», «llega en 2 días», «3 pairs left»). Un dígito suelto («3 pasos», «en 3 días
  lo notas») y una frase de tiempo («los últimos 3 inviernos») siguen sin verificarse.
- **PND-228**: urgencia o escasez sin número (`doctrina.urgencias_sin_dato`, lista `URGENCIAS`), solo en lo que se
  publica de «Cómo mejorarlo» (`mejorar.ofertas_sin_dato`: texto del gancho —bloquea su generación—, copy nuevo y
  versión de imagen —aviso—), y una regla nueva en `mejorar.PROMPT`: ni los ganchos ni el copy nuevo afirman escasez,
  urgencia ni prueba social que el texto del anuncio, la voz o los datos no muestren.

## 1. Lo que marca la comprobación, antes y después (gratis)

La comprobación es código: se midió pasando las respuestas reales de Claude guardadas en la copia de solo lectura de
producción del 2026-10-14 por la versión de `l1-integracion` y por la nueva. Los datos de cada texto son los que quedan
guardados (el ángulo y sus pruebas para guiones e ideas; `mejorar.datos_verificables` rehecho desde la foto para Triple
Whale): para guiones e ideas es una cota (lo marcado aquí solo pediría corrección si tampoco estaba en los DATOS
completos). Solo cifras agregadas; ningún texto de cliente sale de la copia.

| área | textos | marcados antes | marcados después | con urgencia sin dato |
|---|---|---|---|---|
| guion base de Final edition (bloqueante) | 60 bloques de 12 guiones | 0 | 0 | — (no se mira) |
| guion de las finales | 15 bloques | 0 | 0 | — |
| ideas de Sprints (ángulo y escena) | 61 | 0 | 0 | — |
| «Cómo mejorarlo»: copy nuevo | 2 | 1 («40%») | 1 («40%») | 0 |
| «Cómo mejorarlo»: análisis y versión | 4 | 2 | 2 | — / 0 |

Ningún texto real cambia de veredicto: el arreglo no agrega correcciones pagadas al guion ni avisos de más. Los casos
que sí cambian están en las pruebas (`tests/test_doctrina.py`, `tests/test_tw_mejorar.py`).

## 2. La regla nueva del prompt, con Claude (`mejorar.analizar`, PND-228)

Mismas entradas antes (código de `l1-integracion`) y después: los dos análisis reales de la copia (anuncios de imagen de
happyflops en noruego y neerlandés; los datos de Triple Whale de happyflops que Daniel aprobó usar para medir esta
llamada el 2026-10-08), sin aprendizajes ni productos (iguales en las dos corridas), modelo de producción, envoltorio que
solo observa `Messages.create`. Corridas fuera de la app (`eval:tw-mejorar-<antes|despues>:<caso>`).

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| `analisis_1` (imagen; el copy del anuncio ya dice «Lageret tømmes raskt») | end_turn · 8 593 · 0,1172 (escribe la caché) · sí | end_turn · 8 685 · 0,0992 · sí | que no invente urgencia y que la del anuncio siga valiendo |
| `analisis_2` (sin imagen legible; neerlandés) | end_turn · 5 555 · 0,0658 · sí | end_turn · 5 267 · 0,0632 · sí | sin urgencia en los datos |

- Los dos casos validan en las dos versiones, con salida y costo parecidos (sin la caché fría, −4 %).
- Ningún copy nuevo trae urgencia sin dato, antes ni después. En `analisis_1` el copy repite «Lageret tømmes raskt»,
  que es del texto del propio anuncio: la regla y la comprobación lo aceptan, como debe ser. Ojo con el caso del eval
  del 2026-10-09 que originó PND-228: si el texto de ese anuncio también lo decía, la «urgencia inventada» era del
  cliente. No se pudo comprobar (ese anuncio no está en la copia).
- `analisis_1` sigue con «40% rabatt», que no está en los datos, antes y después: la regla de ofertas ya existía y la
  comprobación lo marca («revisa antes de publicar»).

**Gasto de esta medición:** US$ 0,3454 (antes 0,1830 · después 0,1624). La parte 1 es gratis.

**Conclusión:** se cierra. La comprobación nueva no cambia el veredicto de ninguna respuesta real guardada (no suma
correcciones pagadas ni bloqueos), atrapa los casos de PND-227/237 en las pruebas y la urgencia sin dato en los textos
que se publican; la regla del prompt no rompe ningún caso ni sube el costo. Es una muestra chica (2 análisis): la
comprobación es la red si la regla falla.
