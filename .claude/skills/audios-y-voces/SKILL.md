---
name: audios-y-voces
description: "Audios y voces: Mi música (canciones propias y ElevenLabs vía fal), el modo Audios de Crear (locuciones con las 22 voces, diez idiomas), las voces propias (clonar o diseñar con MiniMax) y el Anuncio hablado (foto + guion → P-Video-Avatar). Cargar antes de tocar mi_musica.py, audios.py, voces_propias.py, hablado.py, hablado_rutas.py, providers/fal_audio.py, tareas/audios.py o tareas/hablado.py."
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
las genera todas de antemano), diez idiomas (es, en, pt, de, fr, it, fi, sv, no, cs; desde 2026-09-30),
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
ElevenLabs Turbo v2.5 con `language_code`; las **voces propias** por MiniMax Speech 2.8 HD con `language_boost`.
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
