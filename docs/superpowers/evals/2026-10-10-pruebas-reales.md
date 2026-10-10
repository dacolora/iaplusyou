# Pruebas con gasto real (2026-10-10)

Daniel aprobó un tope de US$ 15 («vamos hazlo», 2026-10-10). Todo corrió en producción, en el proyecto de pruebas
`colorado_forja`, por las mismas rutas y tareas que usa un cliente (test client de Flask con sesión de admin y el worker
real). Las llamadas a Claude se midieron con la skill `eval-claude`: un envoltorio que solo observa `Messages.create`
(stop_reason y usage), sin tocar el código bajo prueba.

**Gasto total del día en `colorado_forja`: US$ 3,48** (video 2,68 · clasificación 0,30 · guion 0,23 · imágenes 0,18 ·
Apify 0,058 · otros 0,026). El costo del director (Claude) se anota aparte en `_creatv`, como siempre.

## PND-108 · Guion base de Final edition (`final_edition/guion.py`, tope 4 000)

| caso | 1.ª llamada: stop · salida/tope · US$ | corrección | valida |
|---|---|---|---|
| cf_20260912_160550_108303 | end_turn · 3 203/4 000 | sí (1 240) | sí · US$ 0,070 |
| cf_20260917_134920_335526 | end_turn · 3 562/4 000 | no | sí · US$ 0,051 |
| cf_20260927_095314_161799 | end_turn · 3 069/4 000 | no | sí · US$ 0,046 |
| cf_20261007_221411_960598 | end_turn · 944 | sí (397) | **no** · US$ 0,033 — Claude se negó (la pieza de prueba promociona drogas con personajes infantiles) |

Conclusión: la primera pasada usa hasta el 89 % del tope. Se sube `MAX_TOKENS` a 8 000; como se paga solo lo usado, el
costo no cambia y desaparece el riesgo de un guion cortado. El caso negado no es del tope: ver PND nuevo sobre negativas.

## PND-141 · Describir referencias y sugerir sonido (tope 4 000)

| llamada | casos | salida máxima | valida |
|---|---|---|---|
| `referencias_link.describir` (1, 3 y 6 imágenes) | 3 | 345 | 3 de 3 · US$ 0,004–0,010 |
| `final_edition.sonido.sugerir_descripcion` | 3 | 71 | 3 de 3 · US$ 0,0013 |

Conclusión: los topes de 4 000 sobran; no hay nada que cambiar.

## PND-007 · Apify (`usageTotalUsd`)

Barrido 11 (palabra «water bottle», US, tope 10). Corrida `qgUhY1Z8kyp6AN3p4`: actor PAY_PER_EVENT, 10 eventos
«apify-default-dataset-item» × US$ 0,0058; `usageTotalUsd` = 0,058; dataset con 10 anuncios. La app anotó US$ 0,058 con
`run_id`, `dataset_id` y `conciliacion_pendiente: false`. Conclusión: en un actor que cobra por resultado,
`usageTotalUsd` es el cobro total de la corrida y coincide con resultados × precio.

## PND-035 · Kling con «Image 1» (no «@Image1»)

Dos referencias generadas con Seedream (botella negra, mujer de suéter verde; US$ 0,09 c/u). Kling O3 Pro 5 s por la
ruta de Crear (prompt «The woman from Image 2 picks up the black bottle from Image 1…»), US$ 0,56: la misma mujer y la
misma botella en todo el video, toma, bebe y sonríe. Conclusión: Kling respeta «Image N»; no hace falta «@Image1».

## PND-071 · Director

- Receta «Antes y después», Kling 10 s, US$ 1,12: los tres actos se ven (bebe de una botella de plástico con mueca →
  pone y abre la botella negra → macro de condensación). Faltó el plano final de la mujer relajada.
- Persona con el producto, Seedance 2.5 con varias referencias, 12 s (US$ 5,68 estimados): **rechazado sin cobro** —
  ByteDance no acepta fotos realistas de personas como referencia aunque sean generadas con IA. La app lo dijo en
  palabras y no cobró.
- Hallazgos del prompt armado: salió en español (la regla del repo pide inglés para los modelos de video) y, en el de
  Seedance, inventó un nombre («Ana») y un «logotipo plateado» que la botella no tiene, contra su propia línea de
  fidelidad.

## PND-073 · Wan 3.0 con «Que Wan mejore mi prompt»

Mismo texto y referencias, 5 s, US$ 0,50 cada uno. Sin la casilla el video empieza con la mujer ya sentada; con la
casilla sigue la acción completa (camina por el parque, se sienta, bebe). Una sola muestra por lado: a favor de la
casilla, al mismo precio. Se queda opcional, como está.

## No probado

PND-074 (Seedance con imagen final) no está implementado: no hay qué probar.
