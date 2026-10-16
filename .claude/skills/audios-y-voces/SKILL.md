---
name: audios-y-voces
description: "Audios y voces: Mi música (canciones propias y ElevenLabs vía fal), el modo Audios de Crear (locuciones con las 22 voces, once idiomas), las voces propias (clonar o diseñar con MiniMax) y el Anuncio hablado (foto + guion → P-Video-Avatar). Cargar antes de tocar mi_musica.py, audios.py, voces_propias.py, hablado.py, hablado_rutas.py, providers/fal_audio.py, tareas/audios.py o tareas/hablado.py."
---

# Audios, voces y música en Crear

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Mi música** (`mi_musica.py`, spec `docs/superpowers/specs/2026-09-25-mi-musica-design.md`): the
client's own songs — uploaded (mp3/wav/m4a/aac/ogg, ≤ 20 MB, ≤ 10 min) or created with ElevenLabs
via fal (`fal_audio.musica_elevenlabs`, `fal-ai/elevenlabs/music`, always 60 s, US$ 0.60 per started
minute, worker task `musica_generar`, `max_intentos=1`, gasto tipo `musica`) — are `material` rows
(tipo `audio`, origen `subida`|`musica`, R2 `clientes/<c>/materiales/<hash><ext>`); `mi_musica` is
their only writer. Forms pick a song with the value `mat:<id>` (in «Música al crear» and in
«Producir finales») plus `musica_inicio_s`; `final_edition.musica.pista_propia` downloads it, cuts
from that second to a cached WAV and hands it to the same mixes (`mezclar_musica`, `render.componer`),
at cost 0. IA styles keep going through `obtener_pista` untouched. The panel `_mi_musica.html` lives
inside the Crear form, so it has no `<form>`: routes `mm_subir/mm_borrar/mm_crear/mm_lista` answer JSON
with the re-rendered panel and the song list. Voice cloning is NOT here (fal has no ElevenLabs clone).

**Audios en Crear** (`audios.py`, `tareas/audios.py`, spec
`docs/superpowers/specs/2026-09-28-crear-audios-design.md`): cuarto modo de Crear (`data-modo="audios"`,
`#audios`), pedido por Daniel al estilo de MoneyPrinterTurbo: un texto (≤ 3 000 caracteres) leído por una
de las 22 voces verificadas de `fal_audio.VOCES`, elegida en una galería de tarjetas (género y tono de
`audios.VOCES_INFO`/`fichas_voces`, filtros Mujer/Hombre, ▶ por voz: la muestra por voz e idioma se sintetiza UNA
vez para toda la plataforma, fila `material` y gasto del cliente interno `_creatv`; `precalentar_muestras.py`
las genera todas de antemano), once idiomas (es, en, pt, de, fr, it, fi, sv, no, cs, nl; holandés desde 2026-10-07),
velocidad (`speed` del modelo; nunca `language_code`, multilingual-v2 lo rechaza), y opcionalmente una
canción de Mi música con «empieza en el segundo» y volumen. El resultado es un mp3 (`libmp3lame` 192k):
la música arranca 0,6 s antes de la voz, se agacha (`mezcla.DUCKING_VOZ_SOBRE_MUSICA`), sigue 1,5 s y se
funde después del `loudnorm` (`audios.filtro_locucion`, puro). `audios.py` define las filas y sus
hashes; solo la tarea `audio_generar` y `audios.muestra` las crean (vía `materiales.obtener_o_crear`):
el audio es un `material` (tipo `audio`, origen `locucion`, `extra.{nombre,texto,voz,idioma,velocidad,volumen,musica}`)
con `padre_id` a la voz cruda (origen `voz`, hash `locucion_voz` = texto+voz+velocidad, sin el idioma (el modelo lo detecta del texto): el mismo
texto no se paga dos veces; misma combinación completa → «Ya tenías este audio»). Tarea `audio_generar`
(`max_intentos=1`, un trabajo por proyecto `<cliente>__audio_generar`): registra el gasto tipo `locucion`
(`locucion:<hash12>:t<tarea>`) en cuanto fal cobró, ANTES de mezclar; una canción borrada entre el clic y
el worker deja el audio solo con la voz (`musica.estado="ausente"`). Rutas JSON `au_lista/au_crear/au_borrar/
au_muestra/au_descargar` (el mp3 se sirve como adjunto desde Flask: `download` no funciona con otro origen).
La lista `_audios_lista.html` se re-pinta por fetch y su barra NO lleva `data-poll-job` (recargaría la
página): sondeo propio como `mm-progreso`. Subir una canción aquí usa `mm_subir` y avisa al panel de Mi
música con el evento `mi-musica:cambio` (y al revés). `fal_audio.COSTO_USD_POR_CARACTER` es 0,0001 desde
2026-09-28 (precio real de fal; estuvo 3× alto).

Desde 2026-09-30 (spec `docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md`) el motor lo
decide `audios.motor_de(voz, idioma)`: la galería por Multilingual v2 salvo el noruego, que v2 no habla y va por
ElevenLabs Turbo v2.5 con `language_code` (`fal_audio.IDIOMAS_TURBO`; desde 2026-10-08 las finales usan la misma regla con
`fal_audio.tts_galeria`); las **voces propias** por MiniMax Speech 2.8 HD con `language_boost`.
`voces_propias.py` es el único escritor de las voces propias (filas `material` origen `voz_propia`, `url` = su
muestra, `extra.voice_id` de MiniMax), de la grabación de un clon (origen `grabacion`, hash con prefijo propio para
no chocar con Mi música) y de sus muestras por idioma (hash `muestra_propia`, las paga el proyecto). Se crean con la
tarea `voz_propia_crear` (`max_intentos=1`, job `<cliente>__voz_propia`): clonar (base US$ 1,50 más vista previa y estreno, casilla de permiso
obligatoria guardada en `extra.consentimiento`) o diseñar desde una descripción (base US$ 3,00 más vista previa y estreno; el precio del botón varía según nombre e idioma); el gasto (tipo
`voz_propia`) se registra apenas fal responde y la tarea ESTRENA la voz leyendo su muestra, porque MiniMax borra
una voz sin uso real en 7 días (la vista previa no cuenta). En el formulario una voz propia es `vp:<id>`.
Desde 2026-10-01 (spec `docs/superpowers/specs/2026-10-01-mis-voces-en-final-edition-design.md`) Mis voces
también narran finales: grupo «Mis voces» en el selector «Voz» de «Producir finales» (`mis_voces_fe`, solo
valor y nombre), `fe_producir` rechaza una voz propia ajena o borrada sin encolar, `insumos.voz_bloque` (y el
legado `voz._sintetizar_bloque`) la leen con `voces_propias.sintetizar` (MiniMax, la estrena) con caché por
`voice_id`, el `voice_id` entra al hash de la receta del borrador, la capa `voz` anota `fal/minimax`
(`final_edition.proveedor_voz`) y una variante (de gancho o de estructura) conserva la voz propia de su final
original —o, en un destino sin original, la de la final original más reciente de la sesión—
(`final_edition.voz_variante`). Mismo precio por carácter que ElevenLabs.

Fuera: efectos, subtítulos, usar el audio en
un video o el editor, ElevenLabs v3.

**Anuncio hablado en Crear** (`hablado.py`, `hablado_rutas.py`, `tareas/hablado.py`, `static/hablado.js`, spec
`docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md`): quinto modo de Crear (`data-modo="hablado"`,
`#hablado`): una foto del proyecto + un guion de hasta 500 caracteres leído por una voz de Audios → P-Video-Avatar
(`pruna-ai/p-video/avatar`, 720p, US$ 0,025 por segundo de voz redondeado al segundo, tope 30 s). `flowplus_modelos.HABLADO`
es un registro aparte que ningún selector, Sprints ni derivación recorre (`es_hablado`, `es_sesion_hablada`,
`nombre_modelo`, `estimate_hablado`, `generar_hablado`; `estimate_video` delega, así el gasto y «Reintentar» salen de la
misma fórmula). La voz la paga `audios.voz_cruda` (la misma caché `locucion_voz` y el mismo gasto `locucion` que Audios:
una voz no se paga dos veces) desde la tarea `hablado_voz` (`max_intentos=1`, job `<c>__hablado_voz`, en `CARRIL_CREAR`).
La cáscara `_crear_hablado.html` va en la página y el panel (`_hablado_panel.html`: fotos + galería de voces, con la
macro `_voces_galeria.html` que comparte Audios) llega por fetch (`hablado.panel`) la primera vez que el modo se ve; el
JS sondea la voz por su cuenta (sin `data-poll-job`) y repite el POST con `solo_cache=1`, que nunca encola. Blueprint
`hablado` (`/cliente/<c>/hablado/{panel,foto,voz,crear}`, rechaza POST cross-site): la foto llega como ficha
`cf:`/`mat:`/`cat:` de ESTE proyecto, nunca como URL (un personaje del catálogo se sube a R2 al crear); la voz, por su
hash; el precio visto debe coincidir con `estimate_hablado` (si no, 409 y nada se crea). `hablado.crear_pieza` crea una
sesión de Crear (`modelo="p_video_avatar"`, `modo_crear="hablado"`, `enfoque_nombre` «Anuncio hablado»,
`hablado={foto_url, voz_url, movimiento, …}`) y la ruta la lanza con `flowplus_lanzar.lanzar`; el worker usa la misma
`flowplus_video` (`_preparar` conserva el modelo hablado sin ajustar duración ni formato; `ejecutar_video` llama
`generar_hablado`; `recuperar_video` lo encuentra por `nombre_modelo`). «Cómo se mueve» va tal cual como `video_prompt`
(vacío = no se manda). Apagado para una pieza hablada: director y «Editar y crear otra» (también en `cf_rearmar`,
`cf_guardar_prompt`, `fp_reusar`), el camino automático de Final edition (`fe_preparar`/`fe_producir`, nota «Este video
ya habla…») y derivar/rescatar en Experimentos (`pz["sin_derivar"]`, `derivaciones._rechazar_imagen`); el editor, la
doctrina, «Reintentar», «Recuperar» y la publicación orgánica sí funcionan.

**Precio del clon (2026-10-02, PND-011):** `gastos.estimar("voz_clonada", nombre=, idioma=)` incluye clon, vista previa y estreno con la frase que leerá la tarea. `fal_audio.costo_clonar_voz` calcula tanto el estimado como el cobro de creación; el botón recibe los precios por longitud de nombre e idioma del servidor.

PND-038/039/040 (2026-10-03): sintetizar reconoce los errores voice not found / voice_id does not exist / invalid voice id y los convierte al mensaje fijo traducible de voz ausente; otros errores siguen el manejo habitual. Las regeneraciones llevan la voz original al payload de finales. material usa AUTOINCREMENT (migración 0031): borrar la última voz no permite que otra herede su vp:id. No repara identificadores que ya hubieran sido reutilizados antes de migrar.

PND-095 (2026-10-07, lote 5 B): guardar_grabacion mide .aac/.ogg antes de convertir (descarta duración fuera del límite), y vuelve a validar la duración del mp3 final. _voces_galeria pone escuchar/borrar como hermanos del role=radio; conserva .au-voz/data-voz/tabindex y la delegación de eventos. El contenedor oculta también las acciones al filtrar la voz. La paginación fue delegada el 2026-10-08 (ver abajo); la muestra de Final edition y la validación vp: sin voz quedan como estaban.

PND-012 (2026-10-08, decisión delegada y corrección lote 6A): crear reserva la ficha y metadatos en kv mediante gastos.reservar_ficha antes de fal; la reserva no es una fila de Gasto en cero. Con la respuesta completa voice_id/hash/URL y anota el monto real antes de reportar/estrenar/subir/guardar. Si la reserva falla no llama al proveedor. Mis voces recupera fichas pagadas sin material mediante hash, sin fal ni descargas, pero omite tareas voz_propia_crear en_curso. Sin fichas pendientes vuelve antes de consultar tareas: no agrega lecturas a la página (test_perf_pagina_proyecto.py mantiene el límite de 3 consultas a tarea). El guardado final reutiliza el hash y actualiza URL/estrenada bajo el escritor materiales. Marca ficha_guardada y no restaura una voz borrada. Repetir la misma tarea usa su ficha; una reserva sin respuesta nunca relanza al proveedor. test_lote6_voces.py usa SQLite, fallos posteriores al cobro, concurrencia, aislamiento y repetición.

Finales en noruego (2026-10-08, spec de Noruega y Suecia §4; motivo: el público de happyflops es Noruega y Suecia): la regla del Turbo ya no es solo de Audios. `fal_audio.tts_galeria(texto, voz, idioma)` es el único camino de una voz de la galería hacia ElevenLabs: Multilingual v2, o Turbo v2.5 con `language_code` cuando el idioma está en `fal_audio.IDIOMAS_TURBO` (hoy solo `no`). Lo usan Audios (`audios.IDIOMAS_TURBO` es la misma tupla), las finales (`final_edition.insumos.voz_bloque`) y el legado `final_edition.voz._tts`. Una voz nueva de la galería o un idioma nuevo que v2 no hable se agrega a esa tupla, no en cada llamador. Sueco (`sv`) va por v2. El precio de una final en noruego se estima con la tarifa de v2 y se cobra con la de Turbo (la mitad): ver `final-edition`.


PND-095 (2026-10-08, decisión delegada): la lista inicial y au_lista leen 24 audios con corte SQL (25 para saber si hay siguiente), por proyecto y más reciente primero. Ver más pide ?desde=24,48... y agrega las tarjetas con delegación; una respuesta que llegó tras reemplazar el botón se descarta. au_crear/au_borrar y el fin del sondeo vuelven a la primera página. Fragmento sin scripts; lista de datos y HTML tienen el mismo corte. Las muestras de Final edition y la validación vp: quedan como estaban por el alcance delegado. test_rutas_audios.py incluye SQL/HTML/Node y aislamiento.

PND-062, entrega 2 (2026-10-10, pedido de Daniel): el JS de Audios vive en `static/crear-audios.js`
(`defer`, versión de estáticos). `#crear-audios-datos` contiene los once textos traducidos, el ejemplo USD
para el separador y las mismas tablas de clon/diseño con margen; los data-url y data-usd-caracter permanecen
en `#au`. Las pruebas anteriores de permiso, sondeo y precio leen ahora el archivo enlazado, con idénticas
expectativas. Node comprueba la inicialización y los eventos del módulo completo.

**La espera de fal que se agota ya no pierde lo cobrado (PND-313, decisión 2026-10-13, lote 1).** fal cobra lo que
termina aunque el worker deje de esperar. `fal_client.llamar`, al acabarse la espera, pregunta una última vez:
terminado → devuelve el resultado; en cola → pide cancelarlo (`PUT …/cancel`) y, si fal acepta, no hay cobro; en
curso o sin respuesta → `fal_client.EsperaAgotadaFal` (un `TimeoutError`) con `request_id` y `cobrado=True`. Los
de `fal_audio` (`tts`, `tts_minimax`, clonar, diseñar, `musica`, `musica_elevenlabs`, `transcribir_palabras`) le pegan
`costo_usd` a esa excepción (`_llamar_cobrando`) y también a la de una respuesta sin lo pedido (sin `custom_voice_id`,
sin URL: `_cobrado_sin_resultado`). Quien llama lo anota con `entregado=False`: `voces_propias.crear` (clonar y
diseñar, `_anotar_cobrado_sin_voz`, sin `ficha` en el extra porque no hay voice_id que recuperar; el estreno; la
muestra de voz propia que no se pudo subir se devuelve: no llegó),
`tareas/musica.py`, `audios.voz_cruda`; las finales ya lo sumaban (`insumos.voz_bloque` lee `e.costo_usd`). Whisper
cobra por la duración del audio: con `duracion_ms` se anota eso aunque no haya palabras (PND-186 (1): un audio sin voz
costaba 0), y su fallo pagado se anota en la referencia del guion (`final_edition._referencia`), en los subtítulos del
editor (`transcripcion.transcribir`) y en «Cómo mejorarlo» (`tareas/triple_whale`, que también anota un costo 0 como
constancia). Pruebas: `tests/test_fal_espera_agotada.py`.

**Voz propia recuperada desde su ficha (auditoría de PND-013, decisión de quien orquesta 2026-10-15).** Si la tarea
que pagó la voz falló después (el worker devolvió el cobro), Mis voces la recupera gratis al abrirse
(`recuperar_pendientes`, como siempre) y ese GET nunca cobra. Solo cuando la recupera su propia tarea
(`voces_propias.crear` con la ficha de la misma referencia), con el precio que la persona vio al lanzarla, se cobra con
`gastos.registrar_trasladando` (`_guardar_ficha(..., cobrar=True)`).

**El permiso del clon dice que la voz no se borra del proveedor (PND-041, decisión 2026-10-13).** La casilla de
«Clonar una voz» (`_crear_audios.html`, `voces_propias.TEXTO_CONSENTIMIENTO`) dice además que la voz clonada queda en
la cuenta del proveedor (MiniMax, vía fal) y que de ahí no se puede borrar, aunque se quite de Mis voces (`borrar`
solo quita la fila, sus muestras y la grabación). Ese texto se guarda tal cual en `extra.consentimiento` y la tarea lo
compara antes de pagar: cambiarlo hace que una tarea encolada con el texto viejo falle sin cobrar (el despliegue
reinicia el worker con la cola vacía). Prueba: `test_la_pagina_trae_mis_voces_el_panel_y_diez_idiomas`.

**«Pagada y sin cobrar» (PND-339, decisión 2026-10-15, lote 2).** La que recupera el GET de Mis voces en un proyecto que
cobra (`libro.cobra_activo`) y a la que no se le cobró nada (`cobros.vista.cobrado_por_gasto` en 0: una voz entregada y
cobrada cuya tarea solo falló al marcar `ficha_guardada` no se bloquea; revisión de guardian-gasto) se guarda igual (no se pierde) pero marcada `extra.por_cobrar` {referencia, usd} desde que
nace (`_guardar_ficha(..., por_cobrar=True)`): `resolver` no la devuelve (nadie la usa), `listar(cliente, usables=True)`
la saca de los selectores (Final edition, anuncio hablado, el `voces` del JSON de Mis voces) y la tarjeta
(`voz_propia_item(..., cobrar_url=)`, sin `data-voz` ni `role=radio`) dice «pagada y sin cobrar» con el botón «Usar esta
voz (se cobra ≈ X)» → `POST vp_cobrar` → `voces_propias.cobrar_recuperada`: `libro.pedido` (freno y reserva; sin saldo,
402 y la voz sigue bloqueada) y `gastos.registrar_trasladando` a `<referencia>:recuperada` (una sola vez, aunque haya dos
clics), y la libera (`por_cobrar=None`). Un proyecto que no cobra la recupera libre, como antes. Pruebas:
`tests/test_voz_propia_por_cobrar.py`.

**Sin saldo en fal por el lado del audio (PND-215, decisión 2026-10-13, lote 2).** `fal_client.llamar` (voces de Audios,
del anuncio hablado y de las finales, Mi música, la música de fondo, Whisper de los subtítulos, las voces propias)
reconoce al encolar que fal no tiene saldo (`fal_video.error_de_respuesta`: 402, «Exhausted balance», «top up»…),
llama a `saldo.marcar("fal")` como Seedance (el aviso de Crear, la alerta `saldo:fal`/`saldo:fal_recarga` y el correo
al admin, sin el proyecto: `fal_client` no lo conoce) y lanza `fal_video.SinSaldo`. Las tareas de voz
(`errores_voz.publico`) y la canción de Mi música lo dicen en palabras (`saldo.mensaje_audio`); otro rechazo de fal sigue
siendo el RuntimeError de siempre. Un audio que sale bien no limpia el aviso (lo limpia la próxima generación de
Seedance que sale bien o vence a las 12 h): limpiarlo en cada llamada de fal tocaría la base en cada voz. Pruebas:
`tests/test_saldo_fal_audio.py`.

**La grabación de un clon que no corrió (decisión de quien orquesta, 2026-10-15).** `voz_propia_crear` tiene gancho
`AL_INTERRUMPIR` (`tareas/voces_propias.interrumpida`): si la tarea no terminó (reinicio, colgada, el respaldo sin
saldo), borra la grabación con `voces_propias._borrar_grabacion_si_huerfana` (solo si es una grabación de ese proyecto
que ninguna voz usa), salvo que fal ya haya devuelto la voz (`gasto` `voz_propia:clonar:t<tarea>` con `voice_id` en
su ficha: Mis voces la recupera y esa voz usa su grabación). Pruebas: `tests/test_restos_tareas_interrumpidas.py`.
