---
name: crear
description: "Crear (FlowPlus): generar video o imagen con WaveSpeed (Wan 3.0, Kling O3 Pro, Seedance 2.5, Seedream) desde la bandeja de referencias o solo texto. Cargar antes de tocar cf_crear_video, flowplus_prompt.py, flowplus_modelos.py, flowplus_lanzar.py, tareas/flowplus.py, director.py, plantillas_anuncio.py, la bandeja o el compositor de Crear, o al diagnosticar un video que falló, salió raro, quedó sin saldo o hay que recuperar sin pagar de nuevo."
---

# Crear (FlowPlus): video e imagen desde referencias o texto

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

`comparar_seedance_turbo.py` (2026-10-01) is a research CLI for the VPS, like `comparar_modelos.py`: it
regenerates existing Seedance 2.5 pieces through WaveSpeed's Turbo routes with the worker's same inputs
(`tareas.flowplus._preparar`) for a side-by-side page, asks «si» before spending and registers the gasto under
`_creatv` with the project in `extra.cliente` (PND-316, 2026-10-13: it went to the `--cliente`, and happyflops in
pospago ×3 would have paid our research) (`docs/investigacion/2026-10-01-seedance-turbo.md`). Crear keeps the standard route until that comparison
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
con IA» (`modo_prompt=director`, for people who don't know what to write; not free since PND-299, see below):
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
Seedance 2.5: SOLO la primera; Seedance 2.5 con varias referencias: 10; Seedream: 10) y `cf_crear_video` avisa y no genera si sobra alguna (incidente «mira lo
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
la salida como última barrera (`duracion_con_videos`, midiendo lo que la sesión no traía) y el precio incluye
los segundos de entrada que WaveSpeed factura en Wan (`segundos_facturables_referencia`: cada video 1–15 s, el total
hasta 15 s, hacia arriba; `estimate_video(..., videos_ref_s=)` en el botón, al reintentar y en el gasto real).
**La duración del video de referencia no sale de la cabecera (PND-319, decisión 2026-10-13, lote 1):** un mp4 con
mvhd/mdhd falsos (12 s que dicen 2 s) bajaba el precio visto y el anotado de Wan 3.0, y WaveSpeed cobraba el video
entero. `_duracion_video` mide con `providers.swap_video_precio.medir` (la mayor entre cabecera y paquetes, solo
archivos del disco; los mismos dos turnos de ffprobe que «Cambiar producto»), `cf_crear_video` vuelve a medir el
archivo de la bandeja si sigue en disco (una referencia subida antes guardó la medida de la cabecera) y, si un video que
Wan recibe como video queda sin medida (`flowplus_modelos.videos_sin_duracion`), avisa y no genera; el worker
(`tareas/flowplus.medir_video_url`) baja a un temporal lo que una sesión vieja no traía y lo mide igual (tope
`MAX_BYTES_VIDEO_REFERENCIA`, solo de nuestro R2: `R2_PUBLIC_BASE_URL`) y, si tampoco puede, no lanza (revisión del
guardián de gasto). Una referencia reusada con «Editar y crear otra» no tiene archivo en disco: `fp_reusar` la mide
bajándola de R2 y `cf_crear_video` la vuelve a medir así (`_duracion_video_url`) cuando el modelo la factura; si no se
puede, no genera y lo dice (R7). Si la medida nueva no es
la que guardaba la bandeja (la que usó el precio de la pantalla), `cf_crear_video` no genera: la guarda
(`referencias_flowplus.fijar_duracion`) y avisa, así el precio a la vista es el que se cobra. Kling y Seedance usan el
fotograma y no miran la duración. Pruebas:
`tests/test_crear_duracion_referencia.py`.
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

**Seedance 2.5 con varias referencias, vía fal (2026-10-09, pedido de Daniel: «en Higgsfield Seedance acepta más de
3 imágenes y en el nuestro solo una»):** WaveSpeed solo tiene la imagen-a-video de Seedance 2.5 (`image` de arranque +
`last_image`; su reference-to-video no existe, 404 verificado ese día), así que `seedance25_ref` es la ÚNICA entrada de
`VIDEO` que no va por WaveSpeed: `proveedor: "fal"` (`flowplus_modelos.proveedor_de`), ruta
`bytedance/seedance-2.5/reference-to-video` (`image_urls`, `duration` como TEXTO "4".."30", `aspect_ratio`
9:16/16:9/1:1/4:3/3:4, 720p, `generate_audio`) y sin imágenes `bytedance/seedance-2.5/text-to-video` (mismos formatos y
precio). 4:3 y 3:4 se abrieron el 2026-10-13 (PND-211, decisión del lote 1) al mismo precio por segundo: fal cobra por
píxeles de salida y a 720p esos formatos no pasan de los de 16:9; la factura la revisa la auditoría de PND-013. Hasta 10 imágenes (fal admite 30, pero
`cf_crear_video` corta `referencias_urls[:10]`; subir el tope exige subir esos cortes). Las menciones se vuelven
`@Image1`, `@Image2`… (`token_imagen` del registro, `flowplus_prompt.asignar_tokens`) y el director tiene su familia
`seedance_ref` (`director._TOKEN` acepta las dos formas). Precio 0,473 USD/s a 720p (API de precios de fal: 0,0214 USD por
1 000 tokens; la página de fal da ~0,4730 USD/s), con o sin sonido. `providers/fal_video.py` repite las garantías de
WaveSpeed con las MISMAS excepciones de `wavespeed_common` (subclases con `proveedor = "fal"`): el `request_id` sale por
`avisar_lanzada` y queda en `prediccion`, `cortable()` acorta o corta la espera (`plazo_cortable`, `hay_que_cortar`), y
«Recuperar el video» pregunta a la cola de fal (`flowplus_modelos.esperar_fal`, en `path` o `path_texto` según haya
imágenes) sin volver a lanzar. El gasto se anota con `proveedor="fal"`, `saldo.limpiar`/`marcar` van por proveedor
(`saldo.PROVEEDORES["fal"]`) y `_mensaje_error` nombra al proveedor (`saldo.nombre_proveedor`). No entra en la
rotación automática de regeneraciones (`rotar: False`, `flowplus_modelos.video_rotables`), y una regeneración nunca va a
un modelo que dejaría referencias sin usar (`derivaciones.modelo_regeneracion` filtra con `referencias_de_mas`). Un video
que fal ya terminó y cobró pero cuyo resultado no se pudo traer (429, 5xx, red) sale como error de red y conserva el id;
`ErrorProveedor` es solo para un 4xx con motivo (revisión del guardián de gasto, 2026-10-09). Sin saldo en fal (PND-213, 2026-10-09): `_aviso_sin_saldo.html` pinta un aviso aparte con `con_fal` (solo lo pone Crear)
y `aviso_saldo_fal`/`modelos_fal`; Alertas suma `saldo:fal`/`saldo:fal_recarga`. Pendientes: la factura de
fal de la prueba real y de un 4:3 o un solo texto (PND-211, dentro de la auditoría de PND-013), videos de referencia como
video (PND-212). Desde PND-215 (2026-10-15) el audio de fal también marca el saldo (skill `audios-y-voces`).

**Pedido rechazado al lanzar (2026-10-02, PND-107):** toda respuesta no-ok de WaveSpeed que no es de saldo es `wavespeed_common.PedidoRechazado` (RuntimeError, mismo `str(e)` técnico de siempre para la bitácora y `tarea.error`, más `status` y `mensaje` del proveedor); `tareas/flowplus._mensaje_error` la cuenta en palabras: «<proveedor> no aceptó el pedido y no se cobró nada: <motivo>…» (WaveSpeed o fal.ai, `saldo.nombre_proveedor`) (o, sin mensaje legible, con el código de respuesta). Antes la tarjeta mostraba el JSON crudo. Cada tipo tiene su frase: 401/403 «rechazó la llave de Creatv», 429 «demasiados pedidos», 5xx «falla de su lado» SIN prometer que no se cobró (WaveSpeed pudo crear la predicción sin devolver su id), y un 4xx con o sin el motivo del proveedor. Un `PedidoRechazado`, como `SinSaldo`, no persigue la `prediccion` que haya en la sesión: es de un intento anterior, no de este video.

**Gasto y duplicación (2026-10-02, PND-004/014/109):** `duplicar(..., variante="B")` toma `BEGIN IMMEDIATE` antes de buscar y crear; dos clics obtienen la misma hija. El director cuenta `usage` con caché y conserva el costo en `DirectorError`; su gasto se anota antes de guardar la sesión (desde PND-299, al proyecto: ver abajo). Sus tareas van con `max_intentos=1`. La predicción conserva `referencia_gasto`: recuperar una descarga pagada mantiene la referencia del intento original, y una música nueva se registra aparte con la tarea de recuperación.

**Lanzamiento incierto (PND-214, decisión 2026-10-13, lote 1; dos revisiones del guardián de gasto).** Regla: ante
cualquier duda NADIE recibe un video por suposición; el posible cobro queda anotado (`entregado=False`) y se avisa al
admin. Una lectura agotada, una conexión cortada, un 2xx sin id o CUALQUIER 5xx al LANZAR (de WaveSpeed o de su
pasarela: el pedido pudo crearse antes de fallar) es `wavespeed_common.LanzamientoIncierto` (lo arma
`lanzar_prediccion`, que usan `flowplus_modelos._lanzar` y `wan3_client.generar_video`); no poder ni conectar
(`ConnectTimeout`, `NewConnectionError`) es `SinConexion` («no salió, no se cobró»); un 4xx sigue siendo
`PedidoRechazado`. Video: `tareas/flowplus._lanzamiento_incierto` guarda `lanzamiento_incierto` {path, modelo, desde,
hasta, causa, estado, en, referencia_gasto, prompt_sha (huella del prompt enviado, `huella_prompt`)} y sigue
`flowplus_recuperar` cuando cerró la ventana tardía (`TARDANZA_MAX_S` 300 s tras el corte) más `ESPERA_LISTADO_S`.
`_buscar_lanzamiento` primero mira si OTRO lanzamiento incierto (cualquier proyecto, cualquier modelo, también uno
descartado: `kv` `crear:lanzamiento:<cliente>:<cf_id>`) cruza su ventana ENTERA de búsqueda (`_ventana_busqueda`): si sí,
dudosa sin preguntar. Si no, lee el historial (`buscar_lanzada` → `POST /predictions`, paginando hasta una página vacía;
una página que repite es `HistorialNoDisponible`). **Lo que trae el historial (leído en vivo el 2026-10-15):** `data.items`
del más nuevo al más viejo, filtrado por `created_after/before`; cada ítem con id (32 hex), model (la ruta completa, p. ej.
`alibaba/wan-3.0/reference-to-video`), status, created_at con nanosegundos y «Z», outputs, urls, timings, error y code;
**sin la entrada (prompt)**. Por eso hoy una predicción de la ruta en la ventana NUNCA se entrega: «encontrada» exige
que el ítem traiga `input.prompt` con la misma huella (si WaveSpeed algún día lo agrega). Resultados: «ninguna» (ni una
de la ruta ni un `model` fuera de `flowplus_modelos.rutas_wavespeed()`, con un historial que filtró y se entiende) → «no
se creó ni se cobró», `estado: no_creado`, vuelve «Reintentar» y una línea de posible cobro anterior vuelve a 0;
«dudosa» (cualquier candidata sin entrada que la confirme, dos o más, un `model` desconocido, un id raro, un historial
que no filtró, un cruce) o historial caído → en palabras, posible cobro en Gasto con la `referencia_gasto` del intento y
`avisar_admin("lanzamiento_dudoso")` UNA vez (`avisado`). Si alguna vez entrega, la toma con
`creative_flow.reclamar_prediccion` (`BEGIN IMMEDIATE`; ninguna otra sesión la nombra: `prediccion`,
`prediccion_entregada` o `kv` `crear:prediccion:<id>` de una descartada). Mientras `estado` es `buscando` o `dudoso`
(`lanzamiento_pendiente`): «Recuperar el video» sí, «Reintentar» y «Rearmar» no (`cf_generar_video`, `cf_rearmar`,
`flowplus_lanzar.lanzar` devuelven sin cobrar), y mientras está `buscando` tampoco «Descartar»; descartar en otro estado
anota el posible cobro (`anotar_posible_cobro_al_descartar`) y `creative_flow.eliminar` guarda en `kv` la predicción y
el lanzamiento. `duplicar` no copia `prediccion`, `prediccion_entregada` ni `lanzamiento_incierto`. Imagen (no se
recupera): posible cobro anotado, `lanzamiento_incierto.estado = "imagen"` y «Reintentar» pide confirmar con el precio
(`confirmo_posible_cobro`); tras confirmar queda `imagen_reintentada`. fal sigue contándolo como su 5xx. Riesgo que
queda: una predicción hecha con la misma llave fuera de esta base (web de WaveSpeed, pruebas locales) con una ruta de la
app no se distingue; como nunca se entrega sin la entrada, solo puede volver dudosa una búsqueda. Pruebas:
`tests/test_lanzamiento_incierto.py`.


Director (revisión 2026-10-02, PND-014): Anthropic usa max_retries=0; un 529 cae al prompt básico sin reintentar y sin cobrar dos veces. PND-109: una generación normal persiste la referencia de su propia tarea; solo una recuperación reutiliza referencia_gasto. Guardar esa referencia está dentro del try de descarga y el gasto se registra antes de persistir un error.

PND-028/034 (2026-10-03): el rótulo A usa tiene_hija_b. El gancho interrumpida del director continúa la generación solo con auto_lanzar ya aprobado, también si alcanzó prompt_listo antes de cortarse; respeta prioridad y max_intentos=1. No vuelve a lanzar sesiones que ya salieron de esos estados.

PND-014/125 (2026-10-05): describir referencias y sugerir sonido anotan usage antes de leer el texto, sin retries del SDK (bajo _creatv hasta PND-299; ahora al proyecto). El gasto del video se registra apenas se descarga y el de la pista antes de mezclar, conservando un cobro mayor cuando recuperar usa caché.

PND-144/145 (Codex, 2026-10-07): falla de descarga/R2 de pista conserva costo y URL en la capa fallida y gasto idempotente; imagen anota cobro antes de persistir el error o su bitácora. Pruebas locales en test_lote5_gasto; las revisiones del lote corresponden a Claude.

PND-072 (2026-10-07, lote 5 B): dashboard._encolar_director y Sprints delegan en tareas.director.encolar; job_id, payload, prioridad, duración y max_intentos=1 conservados. El fallback redacta tokens con monitoreo.limpiar_texto(motivo, 300) solo en aviso; no cambia el prompt ni la sesión enviada al director. Banco, referencias antiguas y retokenización quedan como preguntas en PND-070/072.

PND-143 (2026-10-08, decisión delegada): cargar añade el acumulado real de gasto por sesión y música (costos_sesiones, una consulta para todo el proyecto). Incluye referencias históricas/importadas y tareas fallidas y recuperadas; no cambia referencias, conservación ni reintentos. SQLite y fallo después del pago en test_lote6_costos; los campos mostrados ya no bajan a cero al recuperar una pista cacheada.

**Topes de ayudas Claude (2026-10-08, PND-141, decisión delegada):** Describir referencias y Sugerir sonido usan 4000 tokens; prompts intactos, SDK sin reintentos. La medición real con `eval-claude` queda para la tanda pagada autorizada por Daniel.

PND-068 (2026-10-08, decisión 2026-09-18: nada nuevo a Higgsfield): Nueva idea y Nueva idea visual están retiradas, incluidas sus rutas de generar/aprobar imágenes y animaciones. Las URL antiguas dan 404. Las piezas ya generadas, sus conceptos, archivos y gasto se conservan; los CLI y proveedores compartidos permanecen.

PND-068 (corrección 2026-10-08): la página del proyecto no carga estado_videos, bitácora ni conceptos_pendientes para un contexto que ninguna plantilla pinta. Retirados _conceptos_pendientes y sus job_id locales; se conservan los módulos/datos históricos y los consumidores vigentes (CLI, reconciliación y publicación). La regresión comprueba 404 de las rutas retiradas y 200 del proyecto con JSON antiguos sin leer conceptos para pintarlos; no usa una pieza Flow Plus como prueba del flujo Higgsfield.

**Corazón en las tarjetas (2026-10-08, pedido de la persona usuaria):** cada pieza lista de Crear trae un ♡/♥ arriba a la derecha para separar las versiones que se van a usar de las que no. Se guarda en `concepto.extra["favorito"]` con `creative_flow.marcar_favorito` (`BEGIN IMMEDIATE` antes de leer; quitarlo borra la clave) vía `POST cf_favorito` (`favorito=1|0`; por fetch responde `{ok, favorito}`, sin JS vuelve a `#creativeflowplus`). `duplicar` no lo copia. El botón es un `<form>` real dentro de la tarjeta; el delegado de `_tab_creativeflowplus.html` lo envía por fetch y pinta el cambio al instante (vuelve atrás si falla); como es un `button`, el clic no abre el detalle. Estilos en `pantallas/crear.css` (tokens `--velo-media`, `--sobre-media`). Pruebas: `tests/test_crear_favorito.py`. Solo marca: no filtra ni reordena.

**`creative_flow.actualizar` toma el candado antes de leer (2026-10-09, revisión del corazón):** leía `extra` en autocommit y lo reescribía entero, así que un corazón (u otra clave) confirmado entre esa lectura y su UPDATE se perdía cuando el worker escribía en la misma pieza (revisor de doctrina, Final edition, flowplus). Ahora hace `BEGIN IMMEDIATE` antes de `_ids`, igual que `marcar_favorito` y `duplicar` B; el otro escritor espera con `busy_timeout`. Prueba con `escritor_en_medio` en `tests/test_crear_favorito.py` (sin el candado, el escritor de en medio confirma y la prueba falla).

**Probado en real el 2026-10-10** (`docs/superpowers/evals/2026-10-10-pruebas-reales.md`): Kling O3 Pro respeta «Image N» (no hace falta «@Image1»); `seedance25_ref` rechaza fotos realistas de personas como referencia aunque sean de IA (ByteDance; la app no cobra y lo dice, PND-242); «Que Wan mejore mi prompt» siguió la acción completa en la única muestra, al mismo precio; el director arma el prompt en el idioma del proyecto e inventó detalles (PND-239, PND-240).

Cambiar producto cobra un video por lo que dura (PND-312, 2026-10-13): la tabla es `providers/swap_video_precio.py` y el detalle está en la skill `cobros` («Swap de video por su duración»); el precio se ve antes de generar (`#swap-precio`, `static/swap-precio.js`).

PND-062, entrega 1 (2026-10-10, pedido de Daniel): Del catálogo y Cambiar producto comparten
`GET /cliente/<cliente>/catalogo/selector?sel=plus|clone`. La grilla llega dentro del formulario original; los nombres
y valores de `productos_catalogo` (categoria:id) y `producto_id` (id/color) siguen iguales. Precargas seleccionadas
existen como inputs antes de abrir, se mandan como `marcado` y se sustituyen al llegar la grilla sin duplicarlas.
Los archivados solo vuelven si están marcados. Historial de swaps: 24, vivos primero y todas sus barras visibles,
Ver más por fetch sin scripts. Las pruebas envían los inputs del fragmento a ambas rutas con proveedores dobles.

Enmiendas PND-062, entrega 1 (2026-10-10, pedido de Daniel tras revisar la entrega): Cambiar producto comprueba la elección antes de enviar archivos aunque el selector siga cerrado: cancela submit, abre sel-clone y muestra el aviso por catálogo. No cambia producto_id ni la ruta de generación. Los contadores del selector y del compositor vuelven a contar activos/colores elegibles, como antes de paginar.

PND-062, entrega 2 (2026-10-10, pedido de Daniel; enmienda de carga tras revisar): el compositor se carga sin `defer` desde
`static/crear-compositor.js`; `_tab_creativeflowplus.html` conserva sus textos traducidos y los seis datos
interpolados en `#crear-compositor-datos` (JSON). `fp_prefill`, las etiquetas de la bandeja, las rutas y la
misma tarifa con margen llegan intactos. Las precargas de Crear con este producto y Editar y crear otra
siguen aplicándose antes del primer evento de modo; modelos, precios, DOM y POST no cambian.
El script conserva su lugar después del formulario y su JSON: las guardas del submit se registran
al parsear esa sección, antes de los módulos posteriores y del selector de modos.

**Llegar a Crear desde un análisis de Rendimiento (2026-10-13):** la versión mejorada de un anuncio de imagen fija abre
Crear en modo imagen con la imagen del anuncio como la ÚNICA referencia de la bandeja (se reemplaza, como «Editar y
crear otra» y la escena de Flow Plus) y un prompt para editarla; nada se genera hasta «Generar» con su precio. El
detalle vive en la skill `triple-whale` («Cómo mejorarlo» de un anuncio de imagen fija).

**Las ayudas con IA las paga el proyecto (PND-299, decisión 2026-10-13, lote 1; Daniel: «de resto todo de cuenta del
cliente»).** El director («Crear super prompt» y «Rearmar»), «Describir con IA», «Sugerir» sonido y «Analizar
referencias» de la marca ya no van a `_creatv` ni son gratis: cada botón dice su precio (`precio_de('director')`,
`precio_describir(refs)` según las imágenes que se mandan, `gastos.TARIFAS` `director` 0,05, `describir_referencias`
0,004 + 0,0015 por imagen, `sugerir_sonido` 0,002, `analizar_marca` 0,025, de lo medido) y el gasto va al proyecto con su
tipo (`director`, `describir_referencias`, `sugerir_sonido`, `analizar_marca`). `flowplus_director` está en
`TIPOS_QUE_COBRAN`: `cf_crear_video` (modo director) y `cf_rearmar` exigen antes de tocar la sesión y
`tareas.director.encolar` reserva `costo_estimado()`; si la reserva falla tras crear la sesión, queda en `error` con la
frase (la bandeja no se consume). El director que cae al prompt básico se anota con `entregado=False` (no se cobra).
Describir y sugerir corren con `libro.pedido` en la petición; «Analizar marca» con `trabajos.iniciar_con_pedido`
(`generador_prompts.analizar_marca(on_usage=)` avisa el uso apenas Claude responde: antes no se anotaba). Los lotes de
Sprints suman el director de cada video al precio del lote si el proyecto cobra (`director_usd`, como el QA), y
«Regenerar» de un video lo suma siempre (`costo_regenerar`; «Reintentar» no pasa por el director: `costo_reintentar`).
El video que lanza el director con `auto_lanzar` no cuenta la reserva del director (`flowplus_lanzar.lanzar(...,
excluir_job=)`): ya está cobrada. «Analizar marca» vacía o cortada (`max_tokens` 400) lanza `RespuestaInvalida`: se
anota con `entregado=False` y no pisa la guía. Un plan no las incluye (no están en `planes.TIPOS_INCLUIDOS`). Pruebas:
`tests/test_cobros_ayudas_ia.py`.

**Cambiar producto: la espera agotada y «Recuperar el resultado» (PND-318, decisión 2026-10-13, lote 1).** Un swap cuya
espera de WaveSpeed se agotaba (`poll_hasta_listo`, 900 s) no anotaba nada aunque WaveSpeed lo terminara y cobrara (un
Seedance de 30 s son US$ 13,20) y no había cómo traer el resultado. Ahora los editores de WaveSpeed avisan el id apenas
lo reciben (`wavespeed_common.avisar_lanzada` en `wavespeed_client`, `wavespeed_video_edit` y `wavespeed_imagen`) y el
swap lo guarda en `swaps.json` (`prediccion = {id, proveedor, referencia_gasto, en}`; solo el modelo principal, no la
mejora de calidad). Al agotarse la espera, `tareas/swap._al_agotarse` pregunta UNA vez (`wavespeed_common.consultar`):
terminado → se entrega como siempre; fallido → `ErrorProveedor` sin gasto; en curso o sin poder preguntar →
`SwapEnEspera`: el costo previsto (calculado ANTES de llamar, y guardado en `prediccion.usd`) se anota con
`entregado=False` (no se le cobra al cliente) y la clave `pred:<id>` en `extra.cache`. Si el worker se reinicia con
el pedido lanzado, el gancho `interrumpida` anota lo mismo. La tarjeta ofrece «Recuperar el resultado (se cobra ≈ X)»
(decisión de quien orquesta, 2026-10-15: todo se cobra, con el precio a la vista) → `recuperar_swap`, que pasa por
el freno de saldo (`exigir` y `encolar(..., costo_estimado=)`; `swap_recuperar` está en TIPOS_QUE_COBRAN,
`max_intentos=1`, mismo job_id que el swap para que la tarjeta muestre su barra): pregunta por ese id
(`TIEMPO_RECUPERAR` 120 s) sin lanzar otro pedido (WaveSpeed no cobra de nuevo), y si llegó, lo baja, lo sube, evalúa
la marca y anota con `gastos.registrar_trasladando` (por la clave `pred:<id>`): el costo pasa de la fila del intento
agotado a `swap:<id>:t<tarea>` y AHÍ se cobra (sin contarlo dos veces). Solo un pedido «failed» pone lo anotado en 0
(no cobró); uno cancelado, borrado o vencido de su lado pudo cobrarse y no se toca, ni al agotarse la espera (se
anota sin «Recuperar») ni al recuperar (como `tareas/flowplus`). Un swap de fal (Kling O1, comparador) que se agota
se anota si fal lo va a cobrar (`EsperaAgotadaFal.cobrado`, PND-313) pero no se recupera. La mejora de calidad
pagada que no llega (falla al bajar o se agota su espera) se anota aparte en `swap:<id>:t<tarea>:mejora`, sin
cobrarla (PND-315). Pruebas: `tests/test_swap_recuperar.py`, `tests/test_tareas_swap.py`.

**Lo que de verdad cobró cada llamada de Cambiar producto (PND-315).** La revisión de marca de cada swap
(`generador_prompts.evaluar_contra_matriz`) anota lo que cobró Claude en `revision_marca:<swap>:t<tarea>` (tipo
`revision`; sin cobrarla si la respuesta no se pudo leer) con `generador_prompts.contar_uso()`, que junta el `usage`
de las llamadas del módulo sin cambiar sus firmas (`usd_de(usos)`), y va en el precio que se ve antes: con reglas
de marca en el proyecto (`dashboard._revision_marca_swap`), `gastos.estimar("swap", ..., con_revision=True)` suma
`TARIFAS["revision_marca"]` (0,02, el peor caso con su tope) y `_precios_swap` manda `revision` para que
`static/swap-precio.js` la sume por archivo. Gemini (`nano_banana_client._llamar`, `on_cobro(usd, entregado)`) avisa
lo que cobra cada intento: la imagen (entregado), un `ReadTimeout` (Google pudo generarla y cobrarla) y una
respuesta sin imagen (su `usageMetadata`). Al cliente solo se le cobra el intento que entregó; los otros van en
`swap:<id>:t<tarea>:intentos` con `entregado=False`, también cuando el swap falla.
