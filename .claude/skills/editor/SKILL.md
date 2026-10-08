---
name: editor
description: "Editor de video: el documento JSON (documento.validar), el motor que lo compila a ffmpeg (motor/compilador, tramos, subtítulos), materiales, ediciones con CAS, la página tipo CapCut en static/editor/ y sus pruebas de paridad Python↔JS, subtítulos automáticos y voz en off. Cargar antes de tocar final_edition/documento.py, motor/, materiales.py, ediciones.py, rutas_editor.py, biblioteca.py, tareas/edicion.py o static/editor/."
---

# Editor de video (documento, motor de render y página)

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Editor (capas 1–5b, 2026-09/10):** the editor's source of truth is a JSON document
(`final_edition/documento.py`: validate, resolve variables per idioma/país, migrate
schema). `validar` is the contract everything else leans on: the principal `video` track
must be contiguous from 0 (first clip at 0, each clip starts where the previous ends —
`imagen` tracks have no timeline), every pista/clip id matches `^[A-Za-z0-9_-]{1,40}$`
with clip ids unique across the document, `pngs` is `{text clip id: material id}`,
keyframes have strictly increasing `t_ms`, audio clips keep `velocidad` 1.0 (no `atempo`
yet), and `materiales` is DERIVED (given list ∪ clip `material_id`s ∪ `pngs` values), so
`en_uso`/`marcar_uso` never trust the browser's list. The document is stored in `edicion` with CAS autosave (`ediciones.guardar`: `version_n` must match
or `Conflicto`) and frozen copies in `edicion_version` (`versionar` takes SQLite's write
lock before `MAX(n)`, same trick as `experimentos._bloquear`; `restaurar` migrates the
frozen document before reusing it). Every file that costs money or time is a `material`
row keyed by `UNIQUE(cliente, hash)` (`materiales.py`: never pay twice; `borrar` only
deletes R2 objects under `clientes/<cliente>/materiales/` — any other key, e.g. a Crear
piece's video with origen `crear`, loses just its row — and propagates a failed R2 delete
instead of swallowing it, so the row survives for retry — `limpiar_sin_uso` skips those
rows too; `en_uso` scans live documents AND frozen `edicion_version`s;
`obtener_o_crear`'s `producir()` can still run twice in a true race, accepted). `final_edition/motor/` compiles a resolved document into
one ffmpeg filtergraph (`compilador.py`, pure): a `transicion` of `d` ms on clip A
occupies output `[fin_A, fin_A + d)` while B keeps its timeline position — the extra
frames come from A's tail (`recorte.hasta_ms + d × velocidad`), and a hard cut is
`concat,settb=1/fps`. Audio chains one filter per clip
(`atrim`/`asetpts`/`volume`/`afade` at real clip edges, `adelay` past the window start),
`amix`ed per role at ≥ 2 clips into `mezcla.filtro_mezcla`, with `anullsrc` covering a
window with no audio clip so `concat -c copy` never breaks on a stream mismatch, and `-t`
always closes the output (the mix carries `apad` too); only x/y keyframes are interpreted
(piecewise-linear in `t` — escala/opacidad/rotación wait for PNG-alpha layers). Free
texts are browser-rendered PNGs (`rutas["png:<clip_id>"]`, `ancho_px`/`alto_px` per clip,
400×200 fallback) placed via `final_edition/geometria.py`'s
fraction→pixel math (round-half-up; `tests/fixtures/geometria_casos.json` is the parity
table the browser must match too), scaled to that box (`scale=w:h`) with per-clip
`opacidad` (`colorchannelmixer`); the native scene sound is just an `audio` pista with
`rol_audio: sonido` over the same material (all non-voz/musica roles `amix` into
`filtro_mezcla`'s sonido input); `tpad=stop_mode=clone` pads the main track when the audio
outlasts it; subtitles get `fontsdir=static/fonts` and every path inside the graph goes
through `_ruta_filtro` (two-level ffmpeg escaping — `'` becomes `\'\''`). NOT rendered in
capa 1: `superpuesto` (PIP — `compilar` raises if it has clips), `rotacion` and
`marca.marca_de_agua`; each principal clip is its own `-ss/-t` input (capa 3: a reordered clip
decodes only its span; the principal may mix sources). `motor/tramos.py` splits into windows past
`PRESUPUESTO_OVERLAYS=60` or past `PRESUPUESTO_VIDEOS=6` principal clips (each input costs ~85 MB
with ffmpeg 8 on the 1-CPU VPS: a 32-cut edit asked ~3 GB and the kernel killed it, 2026-09-30),
filling each window greedily from safe frontier to safe frontier and never cutting inside a
transition's `[fin_A, fin_A+d)` — exceeding the overlay budget at one instant is the only hard
error. Windows are `.tramoN.mov` with PCM audio (`render.OPCIONES_AUDIO_TRAMO`: per-window AAC
left a ~21 ms gap at every join) and `render.concatenar` copies the video and encodes the AAC
once; `motor.renderizar` cleans the partial files in a `finally`. Subtitles are one `.ass`
(`motor/subtitulos.py`) only when the host ffmpeg has libass (`render.tiene_libass()`,
cached: the VPS does, the dev Mac doesn't — `renderizar` reports the omission via
`on_etapa`). Worker tasks in `tareas/edicion.py`: `edicion_producir` renders the FROZEN
version (`max_intentos=1`, no spend of its own: the automatic path pays in
`final_edition/produccion.py`; the route must `crear_final` BEFORE enqueuing — the task
raises if `actualizar_final`/`apuntar_final` find no row — and `idioma`/`pais` are
shape-checked before the work folder exists; `preparar_rutas` stamps `imagen` clip sizes
from the material row and runs `compilador.verificar_recortes` with the known
`duracion_ms`), uploads to versioned keys
`clientes/<c>/finales/<final_id>__v<version_id>.mp4`/`.png` (thumbnail first), errors go
through `cola.sin_token`/`cola.recortar`, and wipes its work folder at start and on
success (kept on failure, for the `.filtergraph.txt`); `edicion_proxy` (540p, frame strip,
scene cuts, `aresample=48000`-first waveform peaks) wipes its folder in `finally`; the
daily `materiales_limpiar` (`worker.PERIODICAS`) is what deletes efímero materials.
Capa 2 additions: `documento` keys by destino (`<idioma>_<PAIS>` wins over `<idioma>`), the
reserved `precio` variable (clip dropped when the country has no price), `por_destino`/`bloque` on
voice clips, `ken_burns: in|out` on principal clips (compiler `zoompan`), normalized
`estilo.{contorno,sombra,fondo,ancho_max}` (fractions of the canvas) and opaque `origen`/`guion`.
Text clips without a browser PNG are rasterized server-side by `final_edition/rasterizar.py`
(Pillow, same TTFs) inside `preparar_rutas` — the automatic path has no browser. `materiales.descargar`
copies `extra.local` when the file is still on disk; `materiales.actualizar_extra` merges into
`extra`; `ediciones.buscar_origen` finds the borrador of a receta. A fatal first-block voice
failure raises `produccion.VozFatal`, and any exception raised after paying carries
`costo_pagado`/`capas_pagadas` so `producir` still records the spend (Task 8's rulings).
Capa 3 (2026-09-27): the browser preview `/cliente/<c>/ediciones/<id>` (Blueprint
`final_edition/rutas_editor.py`, data from `final_edition/vista_previa.py`, open to anyone with access
to the project) — ES modules in `static/editor/` (pure: `geometria`, `tiempo`, `resolver`, `precio`,
`texto`, `subtitulos`, `audio`, `reloj`, `pendientes`; browser: `texto_canvas`, `videos`, `lienzo`, `motor_audio`,
`vista`), tested with Node's own runner through `tests/test_editor_js.py` against parity tables that
Python generates (`tests/fixtures/generar_casos_editor.py`; `test_casos_del_editor_al_dia` fails when
one is stale). The preview draws only what the compiler renders (no rotation/PIP/watermark; x/y
keyframes; `deslizar` entry); subtitles use libass's size via `subtitulos.escala_libass()` (OS/2
metrics); audio is Web Audio with a ducking curve precomputed from the voice `picos`, which needs CORS
on R2 (`storage/r2_cors.py`, applied by hand), while video proxies and images load WITHOUT
`crossOrigin` (read-only preview; capa 5, which reads the canvas as PNG, must restore it). Proxies
are short-side 540 with a keyframe every 15 frames (`tareas.edicion.PROXY_VERSION = 2`; the page
re-queues older ones, free) and polls for them at most 5 min, swapping each one in as soon as it is ready
(never while playing). `sembrar_edicion_demo.py` builds a local demo edition (no spend, no R2); its CLI
refuses when `PLATAFORMA_URL` (env or root `.env`) points to a non-local host.
Capa 4a (2026-09-27): the page edits — `static/editor/operaciones.js` (pure: cut at playhead, delete
with ripple on the principal, duplicate, trim from either edge, reorder the principal, move other
layers with snapping, speed 0.5–2×; every result passes `documento.validar`, checked by
`tests/test_operaciones_editor.py` on the real JS output; `p_sonido` is rebuilt as a mirror of the
principal, without the clips at speed ≠ 1; `normalizar` mirrors `verificar_recortes`: it shortens any clip
that asks for more material than exists — counting with `Math.round`, which is never below Python's
round-half-to-even, so what fits in the browser fits in the render — and then the transitions; a voice clip with
`por_destino` can be moved or deleted but not trimmed, since `resolver` replaces it whole per destino),
`historial.js` (undo/redo in memory), `guardado.js` (debounced PUT `editor.guardar` with CAS
`version_n`, 409 → «Recargar»; the route refuses materials from another project), a DOM timeline
(`escala.js` pure + `linea_tiempo.js`) and `pagina_editor.js`; «Editar este video» in the Final edition
tab (`editor.desde_clon` → free worker task `edicion_desde_clon`, `final_edition/edicion_clon.py`: the
raw clon as one clip + mirrored scene sound, destino `<idioma del país>_<proyectos.pais>` via `origen.pais` — `en_US`
for a US project, decisión B; "es" without a country) and «Producir»
from the editor (`editor.producir`: `versionar` → `crear_final` → `edicion_producir` per destino, free; each
destino is first resolved and checked with `verificar_recortes`, a destino whose paid `final_producir` is running
is refused, and a final with video NOT made from this edición — `ediciones.edicion_de_final` — needs
`reemplazar: true`, which the dialog asks for). The editor and the automatic path now share the borrador:
`produccion.traducir` re-applies its pure steps on a CAS conflict (up to 2 retries) instead of paying again.
Capa 4b (2026-09-28, «tipo CapCut», plan `docs/superpowers/plans/2026-09-28-editor-capa4b-capcut.md`): the page is
library | player | properties with the toolbar and a multi-track timeline below at full width (≤ 760 px: player,
toolbar and timeline, and the library and properties are bottom sheets — «Medios · Audio · Texto · Transiciones» and
«Editar», closed with «Listo»); in the Final edition tab «Editar» is the main action of every ready video and the
automatic AI path is a closed, optional `<details>`. Library: `final_edition/biblioteca.py` (upload video/image/audio
as free `material` rows with origen `subida` — a phone photo is uploaded already rotated by its EXIF orientation —,
list the project's materials, the logo included (origen `marca`), plus the ready Crear pieces, and materialize a piece
with the free task `material_de_pieza`), routes `editor.subir`/`editor.biblioteca`/`editor.agregar_pieza`/
`editor.materiales_por_id` (`&preparar=<ids>` queues the free `edicion_proxy` for what still lacks its proxy or peaks,
asked once per material); browser modules `biblioteca.js`, `propiedades.js` (+ the pure `propiedades_modelo.js`),
`lienzo_interaccion.js` (tap, drag and scale on the player; pure `seleccion.js`), `avisos_editor.js` (how the page
notifies those modules; they only touch the edition through the `editor` object of `pagina_editor.js`, which also
exposes `enConflicto()` so the panels say «recarga la página» instead of pointing under the video), and `historial.js`
merges the consecutive steps of one control into one undo. New pure ops in `operaciones.js`: `agregarVideo/Imagen/
Audio/Texto`, `cortarClip` (any track but `p_sonido`), `ponerTransicion` (the five the render does; `desenfoque` is
shown as «Fundido a negro»), `editarTexto` (a variable text changes only the destino being viewed), `cambiar` (a
whitelist; `fondo.ancho: null` = automatic), `volumenSonido` and `cambiarMezcla` — each with a case in
`tests/js/salida_operaciones.mjs` that Python validates. Rules: `normalizar` NEVER creates `p_sonido` (a borrador
whose recipe had no scene sound leaves it out on purpose, and the automatic path reuses that borrador): only
`agregarVideo` (for its own clip; the clips already there get silent mirrors) and `volumenSonido` (that clip at the
slider's value, the rest at 0) create it, and with nothing to mirror it stays empty instead of disappearing; nothing
that is added lengthens the video (image/text layers and música/efecto end at the principal's end — music loops in
the render — and with the playhead at the end they enter whole, ending there); audio added by hand only reuses a
track whose clips share its `rol_audio` (music never lands in the voice's gap). Still out: PIP (video over video),
color filters, rotation and a photo as a principal clip (it goes in as an image layer with «Llenar la pantalla»).
Capa 4c (2026-09-29, trust fixes, spec §2): audio fades never exceed their clip (`normalizar`
+ a compiler `st >= 0` cap), «deslizar» stores 400 ms and drops 8 % of the canvas height in both engines, moving,
stretching or duplicating a layer stops at the principal's end, load warnings are recomputed per change
(`avisos_carga.js`), technical errors fold into «Detalle técnico»/`title`, an expired session says so
(`guardado.sesionTerminada`, `producir.js`), the library deletes unused `subida`/`crear` materials
(`editor.borrar_material` → `biblioteca.borrar`, 409 names the edición), «Editar» prefers the person's edición over
the «Borrador automático» (`ediciones.para_editar`/`nombre_visible`), and `rasterizar.sin_glifos_faltantes` strips
glyphs the font lacks (emojis) while the panel warns.
Capa 5a (2026-10-01, automatic subtitles + voice-over, spec `2026-09-30-editor-capa5a-subtitulos-voz-design.md`):
subtitles are no longer stored with absolute times. The document says WHAT is subtitled per language
(`subtitulos.fuentes`: `voz` | `sonido` | `material:<id>`, ≤ 8; `[]` = none; absent = the old absolute `palabras`
stay) plus `correcciones[material_id][índice]`; the words live on the material (`extra.palabras`, material time,
`[]` counts as transcribed) and the pure `final_edition/subtitulos_fuente.py` (mirror `static/editor/subtitulos_fuente.js`,
parity table `subtitulos_fuente_casos.json`) maps them onto the timeline when each destino is resolved: a word belongs
to the clip that holds its midpoint, through recorte/velocidad/inicio (`mapear` in quarters, half-to-even), capped at the
clip and principal ends — so subtitles follow every cut, trim, reorder, delete and speed change, and corrections survive
cuts. `tareas.edicion.renderizar_final` derives before `preparar_rutas`; `vista.js` derives after `resolver`. Audio clips
may carry `idioma` (`resolver` drops them in other languages); `subtitulos.visibles`, `escala` (0.6–1.6) and
`resaltado` (`#RRGGBB`) are new. Four styles (`karaoke`, `caja`, `palabra_grande`, `minimal`, table `ESTILOS_ASS`) come
from ONE event list (`motor/subtitulos.eventos`, mirror `subtitulos.js`, table `subtitulos_eventos_casos.json`): the ASS
writes one `Dialogue` per event (highlight with `\1c`, no `\k`), `generar_ass(ventana=)` crops per render window, and the
canvas draws the same events. Paid, always behind a button with the server's price and `max_intentos=1`: task
`material_transcribir` (`final_edition/transcripcion.py`, Whisper via fal, a video's audio goes to a temp R2 key deleted
in a `finally`, gasto `transcripcion` registered before saving; price `fal_audio.costo_whisper`, US$0.002/min, an
ESTIMATE until checked against fal's billing) and task `editor_voz` (`audios.voz_cruda`, the Crear › Audios cache by
`hash_voz`, then its Whisper words; errors are sanitized so the text never reaches the unauthenticated job status).
Free: the mic recording (`biblioteca.guardar_grabacion`: webm/m4a/ogg/wav → mp3, ≤ 5 min with a 2 s margin, duration-less
webm transcoded with a bound and trimmed). `edicion_proxy` now MERGES `extra`. Automatic drafts write `fuentes = {idioma:
[voz]}` (`borrador.es_voz_de_guion`: a voice with `bloque`); an old draft adopts its voice as source on open when every
voice material has words (`avisos_carga.arreglarAlAbrir`). UI: a «Subtítulos» library tab (`subtitulos_modelo.js` +
`subtitulos_panel.js`: source, generate, styles, highlight, height/size, word-by-word correction, quitar línea) with a
read-only row at the top of the timeline; voice-over at the top of «Audio» (`voz_modelo.js` + `voz_panel.js`: AI voice
with the 22-voice gallery and samples, mic recording with a level meter), «Suena en» on a voice clip (not on guion
voices) and recordings/AI voices listed in the library and re-added as VOICE (`escala.rolDeMaterial`).
Capa 5b (2026-10-01, photos and framing, «todo sigue a su clip», spec `2026-09-30-editor-capa5b-fotos-encuadre-design.md`):
a photo is a clip of the principal `video` track with `foto: true` (velocidad 1, 0.1–60 s, `recorte {0, dur}`, never a
`p_sonido` mirror, skipped by `verificar_recortes` and by «El sonido del video»); the render prepares it once per material
(`final_edition/fotos.py::preparar`: EXIF, transparency over black, ≤ 4096, JPEG 92 → `rutas["foto:<mid>"]`) and repeats one
frame with `loop`; a photo counts as one input in `PRESUPUESTO_VIDEOS` (427 MB measured on the Mac for 6 framed photos at
`-threads 1`; still unmeasured on the VPS), while a VIDEO whose `encuadre` zooms in weighs `ceil(zoom²)` inputs, capped at
`PRESUPUESTO_VIDEOS` (`tramos.peso_video`): this conservative weight remains until measurement on render-vps
justifies lowering it; the compiler now crops the source before scaling (PND-049, decision 2026-10-07). `encuadre = {modo: llenar|ajustar, zoom 1–4, x, y}` per principal clip, ONE
integer formula in `final_edition/encuadre.py` and `static/editor/encuadre.js` (`caja`, `fondo`, `par`, parity table
`encuadre_casos.json`): the compiler turns it into source `crop/scale/crop` or `split` + `boxblur` background + cropped foreground `overlay`, the preview
into `drawImage` (`lienzo.dibujarPrincipal`); no `encuadre` = the old chain; EVERY principal chain ends in
`setsar=1,format=yuv420p`. `preparar_rutas` stamps `ancho_px/alto_px` from the prepared photo or from
`encuadre.medidas_visibles` (rotation-aware ffprobe) and refuses a photo clip whose material isn't an image (and the
reverse). New transitions are `modo: "solape"`: A cedes `d` ms (so the video gets shorter by the transition) and the old
tail path does the rest; old tail transitions are untouched; a `solape` on the last clip is undone by `normalizar`.
Layers follow their clip: `static/editor/vinculos.js::seguirPrincipal(antes, despues)` re-anchors texts, images, voices
and effects to the moment of the principal clip under their start (music is only cut, `por_destino` voices never move),
and `pagina_editor.operarCon` wraps EVERY operation with `vinculos.operar` behind the «Vincular» toggle (`#h-vincular`,
default on, `localStorage` `creatv.editor.vincular`); one action = one undo. Lightweight photo copies for the preview:
`fotos.ligera` (≤ 1920, PNG if transparent) in the image branch of the free `edicion_proxy`, images without `url_proxy`
are `pendientes`, and `biblioteca.faltaPreparar` asks for them. UI: «+» on an image asks «Como clip del video» /
«Encima del video» (`.ed-bib-como`), a photo shows its image in the timeline's video row (`escala.fondoFoto`), dragging on
the player moves the framing and its corner zooms (`seleccion.gestoEn` → `encuadre`/`asa_encuadre`,
`encuadre.moverEncuadre/zoomEncuadre/cajaVisible`), «Editar» has the «Encuadre» block and the «foto» form (duration,
slow zoom, transition), and `avisos_carga.vocesJuntas` warns when two voices sound at once. Final-review fixes
(2026-10-01): a photo never passes `FOTO_MAX_MS` when a solape gives its ms back (`devolverASolape`, plus `acotarFotos` in
`normalizar` as the last barrier); a transparent photo gets black under its foreground at the same alpha and the small
blurred-background canvas is filled black before every draw (the render flattens on black); with every track taken (`MAX_PISTAS`: 8 until capa 5c, 20 since its live check — `documento.py` and `operaciones.js` mirror it, and the render does not depend on the number of tracks: `tramos` splits by layers and principal clips) a
followed layer stays in its own row instead of refusing the operation (D10.6); a KEYED gesture (`operarCon({clave})`)
derives from its base through `vinculos.operarGesto` (`crudo = fn(crudoPrevio ?? base)`, `seguirPrincipal(base, crudo)`,
restarted when `historial.fusionaria(clave)` is false, on undo/redo, save, conflict or a «Vincular» change), and a layer
whose clip no longer shows its moment lands on that clip's last ms, never on the next clip's start; «junta» is reported
only when the video really got shorter (`finAntes − finDespues`); toggling «Vincular» says so under the video (phones
never see `title`); an image edition adds an image straight as a layer; a framing margin under `IMAN_ENCUADRE_PX` (12
canvas px) counts as «sin margen» in the drag and the panel (`encuadre.sinMargen`) and the magnet never takes more than a
quarter of the margin; the menu's deferred repaint waits for the closing tap's click (`biblioteca.despuesDelToque`); and
a second tap on the already selected principal clip deselects it (`seleccion.eleccionTrasToque`). Still out: PIP (video
over video, D14), per-clip «Vincular», filters and rotation (capa 5c-2), Producir per country (capa 5d).
Capa 5c-1 (2026-10-02, «textos y gráficos que venden», spec `2026-10-01-editor-capa5c-textos-graficos-design.md`):
the SERVER still rasterizes every text; the preview imitates it through a SHARED LAYOUT. `final_edition/fuentes.py` reads
the TTFs with `struct` (no new dependency) into `static/editor/tipografia.json` (`generar_tabla`/`escribir_tabla`, run
`PY -m final_edition.fuentes`; `test_tabla_al_dia` fails when stale): advances per code point of `REPERTORIO`, asc/desc,
for the 11 fonts of `fuentes.CATALOGO` (`CATEGORIAS` clasicas/impacto/redondeadas/manuscritas/serifa; 8 OFL fonts added
2026-10-01 with their licences in `static/fonts/licencias/`) plus Twemoji Mozilla (`static/fonts/emoji/`, CC-BY 4.0 — the
attribution is shown under «Stickers › Emojis»). `cargar_tabla()` (process-wide cache) returns `emoji: None` with
`EDITOR_SIN_EMOJI=1` OR when the emoji TTF is missing, and BOTH engines read that same table (the valve needs BOTH
services restarted). `final_edition/tipografia.py` ↔ `static/editor/tipografia.js` (parity table
`tipografia_casos.json`, compared EXACTLY): `simplificar` (skin tones, flags, keycaps, ZWJ families simplified the same in
both), `limpiar` (NFC first; what neither the text font nor the emoji font covers is dropped and listed), `fuente_de` (from
U+2190 the emoji font wins; only it decides «emoji», never `fuentes.emoji_capas`), `ajustar` (greedy, words split ONLY on
U+0020 — a no-break space keeps «$ 89.900» together), `maquetar` (box, lines and each letter's origin; letters rounded half
UP), `escala_max`/`factor_nitidez` (the PNG is drawn at ceil(scale) ≤ 4×, ≤ 4096 px, but the box stays NATURAL so the
compiler doesn't change). A text with `estilo.version: 2` is drawn from that layout: Pillow letter by letter in
`rasterizar._png_v2` (three passes shadow → contour → fill, each glyph `alpha_composite`d like the canvas, background ending
at `(margen+caja)·f − 1` because Pillow's rectangle is inclusive, fonts opened with `layout_engine=BASIC` — the VPS Pillow
12.3 has Raqm and would draw Pacifico's contextual «final forms»), the canvas in `texto_canvas.js` (`fontKerning none`,
`textRendering optimizeSpeed`, a translucent pass drawn opaque on a scratch canvas and composited once with `globalAlpha`;
cache capped at 200 texts AND `TOPE_AREA_CACHE` 24 MP, evicted canvases emptied for Safari). EMOJI: Pillow's
`embedded_color` clips COLRv0 to the base glyph's empty box, so the render draws each COLR layer as a plain glyph from an
in-memory copy of Twemoji without COLR/CPAL whose cmap puts glyph g at `PUA_CAPAS + g` (`fuentes.fuente_emoji_capas`,
`emoji_capas`, palette index 0xFFFF = the text colour; zero-area layers dropped); the browser composes COLR itself from the
`@font-face` «CreatvEmoji» (declared only when the table has the emoji font). Old texts (no `version`) render exactly as
before (fingerprints `tests/fixtures/rasterizar_v1.json`, Pillow 11.3 only; checked byte-identical under 12.3 in the
`render-vps` Docker image); the v1 preview draws `sinGlifosV1`. A text becomes v2 when it is added, or when its content,
style or SCALE really changes (`operaciones.aV2`; a no-op change and moving it don't convert); «Mostrar los emojis»
(`actualizarTexto`) converts on purpose. Automatic drafts (`borrador.py`) still write v1. New text ops: `estilo.ancho_max`
slider «Ancho del texto» + «Sin límite» (`ANCHO_TEXTO` 0.3–1, default 0.86), fonts grouped by family and loaded only when
the list is visible (IntersectionObserver), warnings `avisosTexto` («No sale en el video: …», simplified emoji, «Este texto
es de antes…»), presets `oferta nuevo descuento envio ultimas mas_vendido` («Para vender», born in the viewer's language,
editable) and `emoji` — `agregarTexto(doc, tMs, preset, opciones, info)`: callers ALWAYS pass the options object (`{}` /
`{literal}`), otherwise `info` lands in its slot. Stickers: `final_edition/stickers.py` draws 20 white word-free stickers
(deterministic, committed in `static/stickers/` with `stickers.json`); `POST editor.agregar_sticker` turns one into a free
project material (origin `sticker`, `extra.tenible`, `url_proxy = url`, R2 `clientes/<c>/materiales/sticker_<id>.png`,
deduped by hash, never in «Medios», never deletable); an image clip may carry `tinte: "#RRGGBB"` (only on `imagen` tracks):
`[n:v]format=rgba,lutrgb=r=R:g=G:b=B` in the compiler, `destination-in` in the preview (`vista.imagenTenida`), «Color»
in «Editar» only for a `tenible` material. Library tab «Stickers» (`stickers_modelo.js`: flechas, marcas, formas, and 39
emoji when the table has the font) and the 7th phone button. Safe zones (`static/editor/zonas.js`, page only):
`ZONAS["9:16"]` for TikTok/Reels/Shorts (Reels from Meta's published margins; TikTok/Shorts are starting values),
striped guides `#ed-zonas` (`ControlZonas`, remembered in `localStorage` `creatv.editor.zonas`, default Reels) and
`#aviso-zonas` (a layer inside a zone ≥ 8 px or off the frame; an image covering ≥ 95 % of the frame is a background and
never warns; a layer with an entry animation is measured where the entry ends). `MAX_PISTAS` went from 8 to 20 in the live
check (a draft already uses 7). Test anything that touches Pillow ALSO in the `render-vps:latest` image (VPS Pillow and
ffmpeg): the local venv has Pillow 11.3 without Raqm. Before restarting the VPS after a change to text rendering, run
the pre-restart check (scratchpad script of the 5c deploy: emoji layers, a v2 text with every style at factor 3, base glyphs
under Raqm, v1 against `main`, `lutrgb`). Still out (capa 5c-2): text animations beyond «deslizar», rotation, scale/opacity
keyframes, colour filters; widening `REPERTORIO` (Cyrillic, ẞ, ⅓, ① — the v1 preview drops them while the v1 render draws them).


PND-012 (2026-10-08, corrección lote 6A): materiales.actualizar_ficha actualiza URL/campos y mezcla extra por (cliente, hash), tomando el candado antes de leer. La creación de una voz usa obtener_o_crear y después actualizar_ficha: una ficha recuperada antes del guardado final conserva su id y recibe la URL final y estrenada, sin duplicarla. Prueba test_lote6_voces.py::test_revision_guardado_idempotente_actualiza_url.


PND-080/128 (2026-10-08, decisiones delegadas): apuntar_final, compartido por los dos caminos de producción, marca producida bajo el candado SQLite si el documento actual coincide con la versión congelada del render. Un documento editado durante el render conserva borrador; guardar vuelve a borrador. PND-128, enmienda 2026-10-08: sin color explícito, documentos nuevos llevan marca.color=None y solo el precio que era morado pasa a negro a 0.6 con texto blanco. Gancho/CTA conservan ESTILO_HOOK/ESTILO_CTA con y sin marca; subtítulos conservan karaoke/resaltado=None. El legado sin marca resalta el karaoke #FFD400. No se migra ningún documento, edición ni estilo guardado, ni se modifica motor/subtitulos.py. Regresiones en test_ediciones.py, test_documento.py y operaciones.test.mjs; no se cambia retención ni url_local.

PND-049, 2026-10-08 (decision 2026-10-07; two clips zoom 2.45 in one transition window exhausted RAM):
`motor.compilador._ventana_visible` keeps `encuadre.caja` as the geometry contract. For each source axis O scaled
to S, crop offsets and sizes use multiples of `lcm(O/gcd(O,S), 2)` (doubled when its scaled length is odd),
so source and scaled offsets are even and the scale ratio and interpolation phase stay unchanged. Expand
the visible interval outward by four source pixels for interpolation, snap outward to that unit, and clamp
to the source bounds. `crop=...:exact=1` precedes `scale`; the final canvas crop or overlay removes the guard
margin. A coprime ratio may require keeping the whole source axis: do not change the ratio to save RAM.
`ajustar` keeps its original blurred background and only crops the foreground; zoom < 1, photo preparation,
rotation-aware source dimensions, Ken Burns and transitions retain their existing geometry. Legacy clips
without framing keep their original filter because their source dimensions may be absent.

Verification: `test_lote6c_crop_paridad.py` compares four lossless frames in each of twelve small real ffmpeg
renders (including transitions, photos and rotation). Mean absolute RGB difference must be < 0.5 out of 255
per channel, allowing interpolation without accepting a framing shift: max observed 0.036781, while a
deliberate two-pixel shift gives 1.493974. Do not edit `tests/fixtures/*.json` to accommodate a discrepancy.
`deploy/medir_memoria_render.py` compares isolated children with two 1920×1080 clips, zoom 2.45, one window
and one transition, offline. macOS peak RSS: old 888.45 MiB, new 707.81 MiB (20.33% lower). Claude must
measure in render-vps before changing the conservative window budget; this local measurement is not a VPS limit.
