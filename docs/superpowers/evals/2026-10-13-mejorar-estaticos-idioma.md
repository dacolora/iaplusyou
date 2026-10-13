# Eval: «Cómo mejorarlo» de un anuncio estático y el idioma de la respuesta (2026-10-13)

**Pedido de Daniel (2026-10-13):** «el analysis que entrega el producto en el performance lo entrega en español; […] si
el ad es un static, no debería pedir un video: cuando le damos en take to create debe anexar la imagen al create con el
nuevo prompt». Los dos análisis de happyflops (proyecto en inglés) estaban en español, y el de hoy, que pidió y pagó el
cliente, proponía «pasar el formato a video» en un estático.

**Cambio medido:** `triple_whale/mejorar.py` en la rama `mejorar-static-idioma`. (1) Un anuncio de imagen fija
(`es_estatico`) recibe en `PROMPT` la versión de imagen (`_VERSION["imagen"]`: un prompt en inglés para EDITAR esa
imagen) y el system suma una frase; el de video queda igual palabra por palabra. (2) El mensaje cierra, después de las
imágenes, con `cierre_idioma`.

**Cómo:** `mejorar.armar` + `mejorar.analizar` llamados tal cual con el modelo de producción
(`generador_prompts.MODEL`), `idioma="en"`, desde dos worktrees: **antes** = `origin/main` 2f616ce6 (mismo
`mejorar.py` que 379c0350), **después** = la rama. Mismas entradas, exportadas de producción con una sonda de solo
lectura (base abierta con `mode=ro`, sin importar `dashboard`): las filas `tw_analisis` 1 y 2 de happyflops y, de
control, el anuncio de video de Noruega con más gasto armado como `pedidos.pedir_analisis`. Con las imágenes y los
fotogramas reales (`mejorar.visuales`) y sin voz en los dos lados (Whisper no cambia). Proyecto de cliente con el visto
bueno de Daniel (2026-10-13).

**Casos:**
- `analisis_1`: «NO - JA_KA0938.2_V1 - STATIC - SALE…», perdedor, Triple Whale Noruega, tipo `dynamic` sin video (el
  análisis de producción del 2026-10-09, en español).
- `analisis_2`: «fotos.00_00_13_02.Still003», ganador, fuente Meta, tipo `imagen` (el que pidió el cliente hoy, en
  español y proponiendo video).
- `video_control`: «AESTETHIC FEBRUARY 2026 AMBER», prometedor, video de 23 s (que el video siga siendo video).

## Resultados

| caso | antes: stop · salida · US$ · valida | después: stop · salida · US$ · valida | lo que se buscaba |
|---|---|---|---|
| analisis_1 | end_turn · 8 828 · 0,1190 · sí | v1: end_turn · 7 019 · 0,0828 · sí — v2: end_turn · 9 581 · 0,1085 · sí | prompt de edición de imagen y respuesta en inglés |
| analisis_2 | end_turn · 6 406 · 0,0747 · sí | v1: end_turn · 6 019 · 0,0719 · sí — v2: end_turn · 4 663 · 0,0584 · sí — v2: end_turn · 8 236 · 0,0941 · sí | ídem |
| video_control | end_turn · 9 371 · 0,1199 · sí | v1: end_turn · 10 627 · 0,1328 · sí — v2: end_turn · 9 085 · 0,1174 · sí | que siga siendo video y en inglés |

«Salida» incluye el pensamiento. US$ = `nicho.avatares.costo_real` sobre los tokens devueltos. «end_turn» porque
`analizar` lanza `AnalisisCortado` con `max_tokens` y ninguna se cortó. **v1** = la orden de idioma al final escrita en
español («IDIOMA: escribe en inglés…» + excepciones); **v2** = la misma orden escrita en inglés y nombrando cada campo
(lo que queda en la rama).

**Idioma de los campos que lee la persona** (frase, funciona, falla, cambios, `por_que`, `escena`, `angulo`, aprendizaje):

| caso | antes | después v1 | después v2 |
|---|---|---|---|
| analisis_1 | inglés | **español** | inglés |
| analisis_2 | **español** | **español** (escena en inglés) | inglés · inglés |
| video_control | **español** (por_que y escena en inglés) | inglés | inglés |
| **en inglés** | **1 de 3** | **1 de 3** | **4 de 4** |

**Tipo de la versión:**

| caso | antes | después |
|---|---|---|
| analisis_1 | «A continuous 3-second-per-beat product video. Scene 1…» (video) | «Edit this existing flat-lay product image: keep the pink slide sandal, the three-line checklist…» |
| analisis_2 | «A sunny poolside terrace. First, close-up of bare feet…» (video) | «Edit this exact photo: keep the two men, their poses, the pool… unchanged» |
| video_control | video | video (igual que antes) |

## Lo que mostró

- **Los estáticos se mejoran como imagen.** Las 5 respuestas de los dos estáticos piden editar la imagen, conservando
  producto, composición, colores y logo, y cambiar solo el texto o la oferta. El video de control sigue igual.
- **La orden al final en español no alcanza; en inglés sí.** Con v1 seguían 2 de 3 en español (igual que antes; la
  salida varía entre corridas). Con v2 salieron 4 de 4 en inglés en todos los campos. El copy nuevo y el gancho siguen
  en el idioma del anuncio («HappyFlops — nu 40% korting», «Varme skritt er tilbake»), como pide la regla.
- **El costo no sube:** antes 0,075–0,120 por análisis; después 0,058–0,133. Nada salió cortado ni inválido.
- **Un aviso que no es del todo justo:** en `analisis_1` el prompt de imagen conserva el «40% RABATT» que ya está en la
  imagen original, y `cifras_sin_dato` lo marca (`['40%', 'rabatt']`): los datos que verificamos son de texto, y ese
  anuncio no lo trae en su copy. Solo avisa («revísalo antes de generar»). Lo mismo ya pasaba con `copy_nuevo`.

**Total gastado:** US$ 0,98 (6 llamadas de la primera vuelta, US$ 0,60; 4 de la segunda, US$ 0,38), Anthropic, cuenta
de Creatv. **Conclusión:** se cierra. Ningún caso que salía bien sale mal, los estáticos piden la edición de su imagen y,
con la orden en inglés, la respuesta sale en inglés.
