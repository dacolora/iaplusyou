# Doctrina, bloque 3: el revisor de la pieza terminada

Fecha: 2026-09-27. Aprobado por Daniel en el chat (dos partes del diseño; luego «no me preguntes más nada, ejecuta todo»).
Antecedentes: spec del bloque 1 (`2026-09-25-doctrina-copywriting-design.md`, §14.3 «Revisor antes de gastar») y
la rebanada `doctrina/textos/revisar.md` (12 puntos, escrita en el bloque 1 y sin usar hasta ahora).

## 1. Qué se construye

Un revisor que contesta la lista de `revisar.md` sobre una **pieza terminada** de Crear (video o imagen, con su guion
y su caption si existen), antes de lanzarla a un experimento o publicarla. Nunca bloquea, nunca reescribe: informa.

Decisiones de Daniel:
- **Momento**: la pieza terminada (no antes de generar).
- **Disparo**: botón con precio en Crear; en Sprints, dentro del control de calidad que ya corre solo por pieza del
  lote (misma llamada).
- **Enfoque mixto**: lo mecánico lo revisan reglas (gratis, siempre visible, siempre igual); lo que pide criterio y
  ojos lo revisa Claude con visión al darle al botón.

## 2. Los 12 puntos

`doctrina.revisor.PUNTOS`: tupla de 12 `(n, clave, titulo, rebanada)`, en el orden de `revisar.md`. `rebanada` es el
ancla del «¿Por qué?» en `/cliente/<c>/doctrina#<rebanada>`.

| n | clave | título | rebanada |
|---|---|---|---|
| 1 | gancho | Gancho | gancho |
| 2 | una_idea | Una sola idea | angulo |
| 3 | reason_why | El porqué | base |
| 4 | pruebas | Pruebas | base |
| 5 | mecanismo | Mecanismo | angulo |
| 6 | visuales | Visuales | video |
| 7 | ojos | Texto en pantalla | video |
| 8 | lado_brillante | Lado brillante | guion |
| 9 | cierre | Cierre | guion |
| 10 | marca | Marca | revisar |
| 11 | aburrimiento | Aburrimiento | revisar |
| 12 | mismo_mensaje | Mismo mensaje | angulo |

## 3. Revisión rápida (reglas, gratis)

`doctrina.revisor.reglas(datos) -> [aviso]`, pura, sin llamadas. `aviso = {"n", "codigo", "texto", "donde"}`
(`texto` en frases simples para el cliente; `donde` ∈ `idea|angulo|guion|caption`). Reglas:

| código | punto | condición |
|---|---|---|
| `gancho_largo` | 1 | el gancho del ángulo tiene más de `doctrina.MAX_PALABRAS_GANCHO` palabras |
| `arranque_consciencia` | 1 | hay consciencia y arranque (`lead`) y el arranque no está en `doctrina.lead_por_consciencia(consciencia)` |
| `promesa_multiple` | 2 | `doctrina.validar_angulo(angulo)` devuelve `promesa_multiple` |
| `sin_mecanismo` | 5 | sofisticación (del ángulo o fija del producto) ≥ 3 y el ángulo no tiene mecanismo |
| `cifra_no_verificada` | 4 | `doctrina.verificar_cifras` encuentra cifras en el guion (texto de voz y de pantalla) o en el caption que no están en los datos verificables (ficha del producto con sus pruebas, `doctrina.texto_verificable(angulo)`, el texto que escribió la persona en Crear y la guía de marca); una por cifra |
| `sin_cta` | 9 | hay guion y su último bloque no tiene `rol == "cta"` |
| `gancho_distinto` | 12 | la pieza viene de una idea de sprint y el gancho de la idea no es el del ángulo (comparación sin mayúsculas ni espacios de más) |

Sin ángulo, las reglas que lo necesitan no se evalúan (no son un aviso). Se calcula al renderizar; no se guarda,
salvo la foto que queda dentro de una revisión de Claude (§4).

## 4. Revisión con Claude (botón)

- **Datos** (`doctrina.revisor.reunir(cliente, cf_id) -> dict`): la sesión de Crear (`creative_flow.cargar`), su
  ángulo (`angulo`), el texto que escribió la persona (`accion_central`) y el prompt usado (`prompt_relleno`), la idea
  del sprint si la hay (`extra.sprint`), el guion base (`creative_flow.guion_base`), el último caption no vacío de las
  `publicacion` de la pieza, el producto (`final_edition._producto`, con pruebas y sofisticación) y la guía de marca
  (`marca.guia_efectiva`). `reglas()` y el texto para Claude salen de este mismo dict.
- **Fotogramas** (`doctrina.revisor.tiempos(duracion)` + `fotogramas(ruta, tiempos)`): uno en 0,3 s (el gancho) y
  luego uno cada 3 s; si pasan de 8, se reparten 8 a lo largo del video. JPEG a 640 px. Cada fotograma va precedido
  de «Segundo N:» para que Claude cite dónde. Una imagen va por URL, sin fotogramas.
- **Llamada**: `generador_prompts.MODEL`, `system = doctrina.bloque_system("revisar", extra=INSTRUCCIONES_REVISAR)`,
  tope de salida 6000 (pensamiento adaptativo), vía `sprints.analisis._llamar_contando` (cuenta la caché). Respuesta
  JSON: `{"puntos": [{"n": 1..12, "estado": "pasa|mejorar|no_aplica", "detalle": "...", "donde": "..."}], "resumen":
  "una frase"}`. `parsear_revision` exige los 12 `n` una vez, estados válidos y `detalle` no vacío en `mejorar`; si
  no sirve, UNA corrección con el error; si tampoco, `AnalisisInvalido` con los tokens de las dos llamadas.
- **Guardado**: `concepto.extra.revision_doctrina` (sin migración) = `{"version": 1, "video_url", "puntos",
  "resumen", "reglas": <foto de reglas()>, "origen": "boton|sprint", "modelo", "usd", "revisado_en"}`.
  `creative_flow.duplicar` no la copia (pertenece al video generado). **Vigente** solo si `video_url` coincide con
  el de la pieza; si no, se muestra como «de una versión anterior».
- **Tarea** `pieza_revisar` (`tareas/doctrina.py`): `max_intentos=1`, `job_id = f"{cliente}__cf{cf_id}__revisar"`,
  payload `{cliente, cf_id}`. Gasto tipo nuevo `revision` («Revisión de la doctrina»), referencia
  `revision:<cf_id>:t<tarea_id>`, costo real (`nicho.avatares.costo_real`); también cuando la respuesta no sirvió
  (detalle «revisión · respuesta inválida»), y en ese caso guarda `revision_doctrina = {"error": ..., "video_url",
  "revisado_en"}` antes de subir la excepción.
- **Precio**: `gastos.TARIFAS["revision_pieza"]` (inicial US$ 0,05; se ajusta con lo medido en la prueba real),
  `gastos.estimar("revision_pieza")`.
- **Ruta** `POST /cliente/<c>/creative_flow/<cf_id>/revisar` (`cf_revisar`): solo piezas `video_listo` con
  `video_url`; encola y vuelve a Crear; un clic repetido no lanza dos (job_id determinista).

## 5. Dónde se ve

- **Crear** (`templates/_revision_doctrina.html`, macro `revision_doctrina(...)`): sección propia en el detalle de
  toda pieza lista (video o imagen), después del bloque de Final edition. «Revisión rápida» (avisos de reglas, cada
  uno con su «¿Por qué?»); la revisión de Claude agrupada: primero «Para mejorar», luego «Pasa» y «No aplica»
  plegados; el resumen; aviso «de una versión anterior» si no está vigente; error si lo hubo. Botón
  «Revisar con la doctrina (≈ US$ X)» o «Revisar de nuevo (≈ US$ X)», o la barra de progreso si hay un trabajo en
  curso (`iniciarPolling`, los `<script>` clonados no corren: se usa el `data-poll-job` que ya arranca `abrir()`).
- **Experimentos** (galería): `experimentos.elegibles` agrega `doctrina = {"estado": "sin_revisar|vieja|bien|
  mejorar|error", "n": <puntos para mejorar + avisos de la foto de reglas>}` leyendo solo `concepto.extra` (ya está en
  la consulta: cero llamadas nuevas). Etiqueta en cada pieza. En el paso 3 («Revisa»), una línea con las piezas
  elegidas que tienen puntos para mejorar. Nunca bloquea.
- **Sprints**: la página de revisión del lote muestra la misma etiqueta en cada tarjeta, junto al QA.

## 6. Sprints: el QA revisa también la doctrina

`sprints/qa.py::evaluar`:
- Mismos fotogramas que el revisor (`revisor.tiempos/fotogramas`), `system = doctrina.bloque_system("revisar")`, el
  JSON pide además `"doctrina": {"puntos": [...], "resumen": ...}` con los datos de `revisor.reunir`.
- Tope de salida 600 → 6000; la llamada va por `_llamar_contando` y `evaluar` devuelve los tokens.
- La parte de doctrina es opcional para el QA: si viene mal, el QA se guarda igual sin ella.
- Si el QA se guarda (misma sesión), `revision_doctrina` se guarda con `origen: "sprint"`.
- `ejecutar_qa_pieza` registra por fin su gasto real (tipo `revision`, referencia `qa:<cp_id>:t<tarea_id>`), también
  cuando la visión falla después de pagar (tokens en la excepción).

## 7. Errores y límites

- Nada de esto bloquea generar, lanzar ni publicar.
- Descarga o fotogramas fallidos: la tarea termina en error con un mensaje simple y sin gasto (no llegó a Claude).
- El botón no aparece en piezas sin video listo ni en finales de Final edition (una final se revisa por su pieza de
  origen).
- Tokens de la persona: el texto de Crear, el caption y la guía de marca van como DATOS delimitados (información, no
  instrucciones), igual que en el resto de la doctrina.

## 8. Pruebas

Unitarias de `reglas`, `tiempos`, `parsear_revision`, estado de vigencia y `resumen`; `revisar` con un
`_llamar_contando` falso (texto con fotogramas, una corrección, tokens de las dos llamadas); tarea y ruta (gasto,
job_id, max_intentos, error guardado); plantilla de Crear (rápida, completa, vieja, error, botón, barra); galería de
Experimentos y paso 3; QA de Sprints con doctrina (bien, sin doctrina, gasto). Suite completa en verde, prueba real
con Happy Flops sobre copia de la base (mide la tarifa) y despliegue.

## 9. Fuera de este bloque

- Arreglar automáticamente lo que el revisor marque (reescribir, regenerar): el bloque 4 varía ganchos desde
  Experimentos.
- Revisar cada final de Final edition por separado.
- El gasto fijo del guion (US$ 0,01 por llamada): tarea aparte ya creada.
