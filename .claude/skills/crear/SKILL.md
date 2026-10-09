---
name: crear
description: "Crear (FlowPlus): generar video o imagen con WaveSpeed (Wan 3.0, Kling O3 Pro, Seedance 2.5, Seedream) desde la bandeja de referencias o solo texto. Cargar antes de tocar cf_crear_video, flowplus_prompt.py, flowplus_modelos.py, flowplus_lanzar.py, tareas/flowplus.py, director.py, plantillas_anuncio.py, la bandeja o el compositor de Crear, o al diagnosticar un video que falló, salió raro, quedó sin saldo o hay que recuperar sin pagar de nuevo."
---

# Crear (FlowPlus): video e imagen desde referencias o texto

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

`comparar_seedance_turbo.py` (2026-10-01) is a research CLI for the VPS, like `comparar_modelos.py`: it
regenerates existing Seedance 2.5 pieces through WaveSpeed's Turbo routes with the worker's same inputs
(`tareas.flowplus._preparar`) for a side-by-side page, asks «si» before spending and registers the gasto
(`docs/investigacion/2026-10-01-seedance-turbo.md`). Crear keeps the standard route until that comparison
says otherwise.

**Crear (FlowPlus)**. Two paths from the same form (`cf_crear_video`, field
`modo_prompt`). **Default = direct generation** (the "generación tradicional" clients rely
on, restored 2026-09-21 after the director had become the only path): since the
2026-09-26 incident the person's text goes to the model AS-IS via `flowplus_prompt.tal_cual`
(only `@Imagen N` → the model's token in video, plus `SONIDO: <texto>` when she typed a
sound) — no brand guide, no EVITAR/«Recordatorio», no FIDELIDAD/catalog rules, no project
logos. Never add anything in the background unless the person asks for it; `armar` is
still what the director fallback, Sprints and derivations use. `_lanzar_video_cf` launches
right away with the cost shown on the «Generar video» button. **Optional** «Armar prompt
con IA (gratis)» (`modo_prompt=director`, for people who don't know what to write):
sesión en `prompt_pendiente` -> worker
`tareas/director.py` (`director.compilar`: Claude escribe los planos por familia de
modelo, valida y compone A/B con `flowplus_prompt.armar(..., planos=)`; fallback al
prompt determinista, nunca bloquea) -> `prompt_listo` (la persona edita con
`cf_guardar_prompt` o rearma con `cf_rearmar`) -> `cf_generar_video` (A, o A+B vía
`creative_flow.duplicar(prompt_relleno=, variante="B")`) -> `flowplus_lanzar.lanzar`
-> worker `tareas/flowplus.py` -> `providers/flowplus_modelos.py`, todo vía WaveSpeed).
Never make the director mandatory again: a client's own prompt always wins.
References and catalog are optional (2026-09-25): with nothing attached the piece is
`enfoque="libre"` («Solo texto») — no logos, no brand guide, `flowplus_prompt.armar` returns
the person's text as-is (+ the SONIDO line), and each model goes through its `path_texto`
(WaveSpeed text-to-video / text-to-image, same prices; Seedance then does take a format,
`formatos_texto`). Sprints and derivations never use `libre` (they rotate `ORDEN_ENFOQUES`).
The reference tray (`referencias_flowplus`, one file per PROJECT, shared by everyone working on
it) follows «what you see is what gets used» (2026-09-26 incident: a «solo texto» piece took the 4
references another person had just loaded): the Crear form sends `bandeja_vista=1` + the `ref_ids`
it shows (hidden inputs with `form="form-flowplus"` in `_flowplus_bandeja.html`); `cf_crear_video`
uses only those, removes only those after creating (`_consumir_bandeja` → `quitar_varios`), and if
one of them is gone it generates and charges nothing. Without `bandeja_vista` (scripts/old tests)
the whole tray is used and emptied, as before.
Las referencias se nombran `Image N` / `Video N` (`flowplus_prompt.asignar_tokens`,
por modelo: Wan recibe los videos aparte). Spec:
`docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (Etapa 1 hecha;
presets de cámara, Etapa 2, pendiente). **Etapa 3, recetas de tomas (2026-09-30):**
`plantillas_anuncio.py` (8 recetas: «Antes y después» + las 7 del spec §9; datos puros +
`actos_en_segundos`, `n_planos`, `bloque_director`) y el selector «Receta de tomas» pegado a «Crear super
prompt» en Crear (`name="plantilla"`). Solo cuenta con `modo_prompt=director`: el «Generar video» directo la
ignora y guarda `plantilla=None`. Con receta, el enfoque lo fija la receta (si tiene; una pieza sin
referencias sigue `libre`), `director._mensaje` recibe los actos ya en segundos y `director.compilar` pide al
menos un plano por acto (nunca más de uno cada 2 s); «Recrear mi video de referencia» exige un `Video N`
(video en la bandeja con Wan 3.0) en el navegador y otra vez en `cf_crear_video`. Sprints sigue con
`banco_prompts.py`.
**Menciones y recuperación (incidente 2026-09-28,** 6 de 12 videos del día fallaron y los buenos traían
personajes dobles y el dibujo de otro clip**):** `flowplus_prompt.sustituir_tokens` entiende todo lo que la
gente pega de otras herramientas (`@Image1`, `@Image 1`, `@[Image 1](image_1)`, `@image_4`, cualquier
mayúscula) como la mención canónica `@Imagen N`/`@Video N`/`@Logo N`; una mención sin referencia en la
bandeja hace que `cf_crear_video` avise y NO cree la sesión (`menciones_sin_referencia`: nada se cobra).
WaveSpeed sigue trabajando cuando el worker deja de esperar (Wan 3.0 pasó de los 20 min cuatro veces ese
día) y cobra igual: `wavespeed_common.poll_hasta_listo` avisa el `prediction_id` por `on_progreso`
(`avisar_lanzada` apenas hay id), `tareas/flowplus._avisar_fase_de(..., cf_id=)` lo guarda en la sesión
(`extra.prediccion`), un tiempo agotado es `EsperaAgotada` (conserva el id) y un rechazo del proveedor es
`ErrorProveedor` (mensaje, código e id; `_mensaje_error` lo cuenta en palabras en el idioma del proyecto,
p. ej. Kling 1200 «contenido sensible»). El detalle de la pieza ofrece «Recuperar el video (sin pagar de
nuevo)» → `cf_recuperar` → tarea `flowplus_recuperar` (`max_intentos=1`, `TIEMPO_RECUPERAR` 10 min):
vuelve a preguntar por ese id y cierra la pieza con `_terminar_video` (el mismo cierre que la generación
normal; el gasto se anota ahí, con «recuperado»). Nunca genera de nuevo.
**Sin variables quemadas (pedido de Daniel, 2026-09-28):** cada creación nueva arranca limpia. «Empezar de cero»
(`#fp-empezar`, solo JS: `form.reset()` a lo que pintó el servidor + vaciar la bandeja por `fp_vaciar_referencias`)
deja el texto, el sonido, la música y el catálogo en blanco y la duración/modelo/formato en los del proyecto.
«Editar y crear otra a partir de esta» (`fp_reusar`) REEMPLAZA la bandeja con las referencias de esa pieza (antes
se sumaban a lo que hubiera y las referencias «del pasado» se colaban), su precarga (`session["fp_prefill"]`) lleva
`cliente` y `_prefill_para` la descarta en otro proyecto, y la casilla `solo_referencias` trae solo las imágenes con
el texto y los ajustes en blanco (para el clip siguiente con los mismos personajes). Y **ningún modelo recibe menos
referencias de las que la persona ve**: `flowplus_modelos.referencias_de_mas(modelo, referencias, tipo)` cuenta como
`_preparar`/`generar_video` (Wan: imágenes y videos aparte; Kling: el fotograma del video cuenta como imagen;
Seedance 2.5: SOLO la primera; Seedream: 10) y `cf_crear_video` avisa y no genera si sobra alguna (incidente «mira lo
que sacó»: cuatro referencias con Seedance, tres descartadas en silencio, US$ 3,6 cobrados); el compositor muestra el
mismo aviso en vivo (`#fp-aviso-refs`, `data-max`/`data-max-videos` de los radios de modelo) y frena el envío.
**Sin saldo y Wan con videos de referencia (incidente 2026-09-30):** WaveSpeed se quedó sin saldo y los videos
fallaban con su JSON crudo en la tarjeta. `wavespeed_common.error_de_respuesta(resp, path)` es lo que lanzan los cinco
lanzadores de WaveSpeed ante una respuesta no-ok: `SinSaldo` (RuntimeError; 402 o «insufficient credits» / «top up»)
o el RuntimeError de siempre. `saldo.py` recuerda la falta en `kv` (`sin_saldo:<proveedor>`), avisa al administrador
por `notificaciones.avisar_admin` (tipo `sin_saldo`) UNA vez cada `REAVISO_S`, `vigente()` pinta
`_aviso_sin_saldo.html` en Crear y en Cambiar producto (el admin ve desde cuándo y el enlace de recarga; el cliente,
un aviso neutro) y la próxima generación nueva que sale bien lo `limpia` (vence solo a las `VIGENCIA_S` sin fallos).
La tarjeta dice `saldo.mensaje_tarjeta` en el idioma del proyecto, en Crear (video e imagen, que ahora también pasa
por `_mensaje_error`) y en swap; un video sin saldo nunca persigue una predicción vieja. OJO: el VPS no tiene SMTP_* ni
un admin con correo verificado, así que hoy el aviso que llega es el de la app. Y Wan 3.0 con videos de referencia:
los videos juntos hasta 15 s y entrada + salida hasta 30 s (`max_videos_s`, `max_total_con_videos`; 1405 si no).
La bandeja guarda `duracion_s` de cada video (ffprobe al subirlo o bajar el link, `dashboard._duracion_video`;
`fp_reusar` la conserva), `cf_crear_video` avisa y no genera con `flowplus_modelos.problema_duracion`, el compositor
lo avisa en vivo (`data-duracion` en la bandeja, `data-max-total`/`data-max-videos-s` en los radios), el worker recorta
la salida como última barrera (`duracion_con_videos`, midiendo por URL lo que la sesión no traía) y el precio incluye
los segundos de entrada que WaveSpeed factura en Wan (`segundos_facturables_referencia`: cada video 1–15 s, el total
hasta 15 s, hacia arriba; `estimate_video(..., videos_ref_s=)` en el botón, al reintentar y en el gasto real).
Desde el carril de Crear (2026-09-28) eso pasa solo: la primera espera dura `ESPERA_PRIMERA` (10 min,
`wavespeed_common.cortable(plazo_s=)`), y si WaveSpeed sigue la sesión queda en `video_generando` y la tarea
devuelve `Continuar("flowplus_recuperar")`, que pregunta `TIEMPO_RECUPERAR` (45 s) cada `PAUSA_RECUPERAR` (60 s)
—el hilo queda libre entre vueltas— mientras la predicción tenga menos de `ESPERA_MAXIMA` (2 h); recién después
queda el botón. El sondeo aguanta hasta `FALLOS_SEGUIDOS` (6) cortes de red o 5xx seguidos, y un error que no sea
`ErrorProveedor` (estado final fallido) nunca borra el id: se sigue esperando. Un reinicio del worker corta esas esperas enseguida
(`wavespeed_common.fijar_detener` + `cortable()`, solo en las tareas que saben retomar; un swap o una imagen
siguen como antes) y el gancho `interrumpida` retoma por la predicción un video que quedó a medias por un
SIGKILL. Desplegar ya no pierde videos de Crear en curso.
Los lotes de
Sprints encolan el director con `auto_lanzar` (el costo ya se aprobó). `calidad`
`borrador` = Wan a 480p. Duración por defecto 8 s (`preferencias_flowplus`). `VIDEO` /
`IMAGEN` there are the only model registry (path, price, limits, `audio_nativo`,
`familia`, `min_duracion`/`max_duracion`, `formatos`). Crear makes ONE piece per click (the enfoque is
automatic: `producto`, or `persona` when a catalog personaje is among the references; since
2026-09-28 `armar` never forbids people or hands for `producto` — no «EVITAR: personas, pies,
manos», no «Recordatorio final … solo y sin nadie», no pruning of the brand guide —: the product
is the protagonist and the scenes show what it does or changes; the CON PERSONA block still comes
only with a catalog personaje or the `persona` enfoque, and `director._mensaje` spells out each
enfoque to Claude with `_ENFOQUES_DIRECTOR`),
offers 5–30 s (default 8 s) and the formats each model admits (verified on WaveSpeed 2026-09-18: Wan 3.0
2–30 s and 9:16/16:9/1:1/4:3/3:4; Kling O3 Pro 3–15 s and 9:16/16:9/1:1; Seedance 2.5 4–30 s
and follows the reference image, `aspect_ratio` None; Seedream V5 Pro takes `aspect_ratio`
for images). `ajustar_duracion`/`ajustar_formato` run in the route AND again in the worker's
`_preparar` (last barrier before spending), so nothing outside a model's range is ever
requested. Videos
ALWAYS ask for the model's native scene sound (`generar_video(..., con_sonido=True)`: Wan 3.0
`generate_audio` (the published schema's name since 2026-09-28; `enable_audio` was silently ignored), Kling O3 Pro `sound` — +0.028 $/s, already inside `estimate_video` and the
`usd_por_segundo_efectivo` the templates show —, Seedance 2.5 `generate_audio`), and the
`armar` prompt (director, Sprints, derivations) carries a `SONIDO:` line ("Sin diálogo
hablado ni música de fondo" keeps Kling's Chinese/English voices out; the Spanish voice
comes from final edition); direct generation carries one only when the person typed a
sound (`tal_cual`). Images never get that line. The session carries `con_sonido` (the "Sonido de la escena" check, default from
`proyectos.preferencias_sonido`), `sonido_texto` (the described sound, "Sugerir" asks
Claude through `final_edition/sonido.py`) and `musica_estilo` ("" = none). After the
download the worker's **Mezclando sonido** step (`ETAPAS_CREATIVE_FLOW`, 4 stages) probes
the audio track, mixes the chosen music underneath with `final_edition/mezcla.py`
(`mezclar_musica`: video copied, `loudnorm`) and stores `pieza.capas`
(`sonido {proveedor, estado: ok|ausente|desconocido|omitida}`, `musica`, `mezcla`),
`video_url` (mixed: what is seen, published and delivered) and `extra.video_url_crudo` /
`video_local_crudo` (native sound only: the source of final edition). Music failure is
degradable (the paid video is never lost) — it only reports, never regenerates. Spec:
`docs/superpowers/specs/2026-09-16-final-edition-estudio-design.md` S1 (done except
`proveedor_v2a` and style previews, which belong to S3/S5).

**Pedido rechazado al lanzar (2026-10-02, PND-107):** toda respuesta no-ok de WaveSpeed que no es de saldo es `wavespeed_common.PedidoRechazado` (RuntimeError, mismo `str(e)` técnico de siempre para la bitácora y `tarea.error`, más `status` y `mensaje` del proveedor); `tareas/flowplus._mensaje_error` la cuenta en palabras: «WaveSpeed no aceptó el pedido y no se cobró nada: <motivo>…» (o, sin mensaje legible, con el código de respuesta). Antes la tarjeta mostraba el JSON crudo. Cada tipo tiene su frase: 401/403 «rechazó la llave de Creatv», 429 «demasiados pedidos», 5xx «falla de su lado» SIN prometer que no se cobró (WaveSpeed pudo crear la predicción sin devolver su id), y un 4xx con o sin el motivo del proveedor. Un `PedidoRechazado`, como `SinSaldo`, no persigue la `prediccion` que haya en la sesión: es de un intento anterior, no de este video.

**Gasto y duplicación (2026-10-02, PND-004/014/109):** `duplicar(..., variante="B")` toma `BEGIN IMMEDIATE` antes de buscar y crear; dos clics obtienen la misma hija. El director cuenta `usage` con caché y conserva el costo en `DirectorError`; la ayuda gratis se anota bajo `_creatv` con el proyecto en `extra`, antes de guardar la sesión. Sus tareas van con `max_intentos=1`. La predicción conserva `referencia_gasto`: recuperar una descarga pagada mantiene la referencia del intento original, y una música nueva se registra aparte con la tarea de recuperación.

Director (revisión 2026-10-02, PND-014): Anthropic usa max_retries=0; un 529 cae al prompt básico sin reintentar y sin cobrar dos veces. PND-109: una generación normal persiste la referencia de su propia tarea; solo una recuperación reutiliza referencia_gasto. Guardar esa referencia está dentro del try de descarga y el gasto se registra antes de persistir un error.

PND-028/034 (2026-10-03): el rótulo A usa tiene_hija_b. El gancho interrumpida del director continúa la generación solo con auto_lanzar ya aprobado, también si alcanzó prompt_listo antes de cortarse; respeta prioridad y max_intentos=1. No vuelve a lanzar sesiones que ya salieron de esos estados.

PND-014/125 (2026-10-05): describir referencias y sugerir sonido anotan usage bajo _creatv antes de leer el texto, sin retries del SDK; no cambia el botón de sugerencia. extra.cliente identifica al proyecto que pidió la ayuda. El gasto del video se registra apenas se descarga y el de la pista antes de mezclar, conservando un cobro mayor cuando recuperar usa caché.

PND-144/145 (Codex, 2026-10-07): falla de descarga/R2 de pista conserva costo y URL en la capa fallida y gasto idempotente; imagen anota cobro antes de persistir el error o su bitácora. Pruebas locales en test_lote5_gasto; las revisiones del lote corresponden a Claude.

PND-072 (2026-10-07, lote 5 B): dashboard._encolar_director y Sprints delegan en tareas.director.encolar; job_id, payload, prioridad, duración y max_intentos=1 conservados. El fallback redacta tokens con monitoreo.limpiar_texto(motivo, 300) solo en aviso; no cambia el prompt ni la sesión enviada al director. Banco, referencias antiguas y retokenización quedan como preguntas en PND-070/072.

PND-143 (2026-10-08, decisión delegada): cargar añade el acumulado real de gasto por sesión y música (costos_sesiones, una consulta para todo el proyecto). Incluye referencias históricas/importadas y tareas fallidas y recuperadas; no cambia referencias, conservación ni reintentos. SQLite y fallo después del pago en test_lote6_costos; los campos mostrados ya no bajan a cero al recuperar una pista cacheada.

**Topes de ayudas Claude (2026-10-08, PND-141, decisión delegada):** Describir referencias y Sugerir sonido usan 4000 tokens; prompts intactos, SDK sin reintentos. La medición real con `eval-claude` queda para la tanda pagada autorizada por Daniel.

PND-068 (2026-10-08, decisión 2026-09-18: nada nuevo a Higgsfield): Nueva idea y Nueva idea visual están retiradas, incluidas sus rutas de generar/aprobar imágenes y animaciones. Las URL antiguas dan 404. Las piezas ya generadas, sus conceptos, archivos y gasto se conservan; los CLI y proveedores compartidos permanecen.

PND-068 (corrección 2026-10-08): la página del proyecto no carga estado_videos, bitácora ni conceptos_pendientes para un contexto que ninguna plantilla pinta. Retirados _conceptos_pendientes y sus job_id locales; se conservan los módulos/datos históricos y los consumidores vigentes (CLI, reconciliación y publicación). La regresión comprueba 404 de las rutas retiradas y 200 del proyecto con JSON antiguos sin leer conceptos para pintarlos; no usa una pieza Flow Plus como prueba del flujo Higgsfield.

**Corazón en las tarjetas (2026-10-08, pedido de la persona usuaria):** cada pieza lista de Crear trae un ♡/♥ arriba a la derecha para separar las versiones que se van a usar de las que no. Se guarda en `concepto.extra["favorito"]` con `creative_flow.marcar_favorito` (`BEGIN IMMEDIATE` antes de leer; quitarlo borra la clave) vía `POST cf_favorito` (`favorito=1|0`; por fetch responde `{ok, favorito}`, sin JS vuelve a `#creativeflowplus`). `duplicar` no lo copia. El botón es un `<form>` real dentro de la tarjeta; el delegado de `_tab_creativeflowplus.html` lo envía por fetch y pinta el cambio al instante (vuelve atrás si falla); como es un `button`, el clic no abre el detalle. Estilos en `pantallas/crear.css` (tokens `--velo-media`, `--sobre-media`). Pruebas: `tests/test_crear_favorito.py`. Solo marca: no filtra ni reordena.

**`creative_flow.actualizar` toma el candado antes de leer (2026-10-09, revisión del corazón):** leía `extra` en autocommit y lo reescribía entero, así que un corazón (u otra clave) confirmado entre esa lectura y su UPDATE se perdía cuando el worker escribía en la misma pieza (revisor de doctrina, Final edition, flowplus). Ahora hace `BEGIN IMMEDIATE` antes de `_ids`, igual que `marcar_favorito` y `duplicar` B; el otro escritor espera con `busy_timeout`. Prueba con `escritor_en_medio` en `tests/test_crear_favorito.py` (sin el candado, el escritor de en medio confirma y la prueba falla).
