# Editor capa 5a — subtítulos automáticos y voz en off — diseño

Fecha: 2026-09-30. Estado: diseño para implementar (plan
`docs/superpowers/plans/2026-09-30-editor-capa5a-subtitulos-voz.md`). Base de código: `main` **después** de
fusionar la rama `worktree-idioma-oscuro` (fase 6 del idioma: el editor ya habla inglés con
`final_edition/textos_editor.py` + `static/editor/textos.js`). Nace de:

- spec del editor `2026-09-18-final-edition-editor-design.md` §4 («Subtítulos: generar (Whisper sobre voz o
  audio), estilos visuales (karaoke, caja, palabra grande, minimal), posición, lista de palabras con tiempos
  para corregir»; «Audio: … grabar con micrófono») y §6 (la IA como asistencia, con el costo en el botón);
- auditoría post-despliegue de la capa 4b (Parte 1, B «Audio»: grabar voz **Falta**, voz con IA dentro del
  editor **Falta**; C «Texto»: subtítulos automáticos **Falta** — «no siguen los cortes, no se pueden
  corregir»; Parte 3, ítems 2 y 10).

Pedido de Daniel: «todo, el mejor editor». Esta capa pone dentro del editor los subtítulos que hoy solo existen
en la vía automática, y la voz en off (IA y micrófono) que hoy solo existe en Crear › Audios.

---

## 0. Qué entra y qué no

**Entra**

1. Subtítulos automáticos dentro del editor, desde una fuente que la persona elige: la voz, el sonido de los
   videos de la pista principal, o un audio de la edición (canción, efecto, grabación). Transcripción con
   Whisper vía fal, **pagada**, con el precio en el botón; una sola vez por archivo (caché en el material).
2. Subtítulos que **siguen la edición**: cortar, recortar, reordenar, borrar, cambiar la velocidad o mover un
   audio nunca los desincroniza, porque no se guardan con tiempos absolutos (§1, D1).
3. Corregir una palabra, quitar una palabra, quitar una línea; lo corregido sobrevive a cualquier corte (D3).
4. Cuatro estilos visibles — Karaoke, Caja, Palabra grande, Mínimo — con el MISMO aspecto en la vista previa y
   en el video final (tabla de paridad), color de la palabra que suena, altura y tamaño; mostrar/ocultar.
5. Voz con IA desde un texto (ElevenLabs vía fal, la galería de voces de Crear › Audios con sus muestras),
   pagada, con el precio en el botón; entra en el cabezal en una pista de voz y trae sus palabras, así que sus
   subtítulos son gratis.
6. Grabar con el micrófono (MediaRecorder), gratis: se sube, el servidor la pasa a mp3 y entra en el cabezal.
7. Un audio de voz sabe en qué idioma habla (`idioma` del clip) y solo suena en los destinos de ese idioma.

**No entra** (queda anotado para otras capas): cambiar a mano los TIEMPOS de una palabra o agregar palabras
nuevas; volver a transcribir un archivo en otro idioma (D5); traducir subtítulos a otro idioma (capa 5b,
«Producir e idiomas»); apagar subtítulos por tramo (se cubre con «Quitar la línea»); arrastrar los subtítulos
sobre el video; más estilos, fuentes o animaciones de subtítulos; emojis en subtítulos (se avisa, como en los
textos: `rasterizar.sin_glifos_faltantes`); vincular la voz y los textos a su clip de video (auditoría #7: otra
entrega — los subtítulos siguen a su AUDIO, que es lo correcto, D1); voz clonada, efectos de voz, reducción de
ruido, velocidad o tono de un audio; zonas seguras de TikTok/Reels; la marca de tiempo por carácter de
ElevenLabs (se usa Whisper, D9).

---

## 1. Decisiones

### D1. Los subtítulos se DERIVAN al resolver cada destino; no se guardan con tiempos absolutos

Tres opciones:

| Opción | Cómo | Problema |
|---|---|---|
| A. Tiempos absolutos guardados (lo de hoy) | `subtitulos.palabras[destino] = [{t_ms, dur_ms, texto}]` en tiempo de la línea | Cada operación (cortar, borrar con ripple, reordenar, velocidad, mover un audio) tendría que mover palabras; con ~20 operaciones y voces por destino, es el bug #7 de la auditoría multiplicado. |
| B. Espejo recalculado en cada operación (como `p_sonido`) | `normalizar` reescribe `subtitulos.palabras` desde las fuentes | Hay un espejo POR destino (la voz cambia por país); la página tendría que conocer todos los destinos y todas las palabras de todos los materiales en cada operación; y la vía automática, que guarda sin navegador, tendría que hacer lo mismo o dejaría el espejo viejo. Dos verdades que se desincronizan. |
| **C. Derivar al resolver (elegida)** | El documento guarda **qué** subtitular (`fuentes`) y **las correcciones**; las palabras viven en el MATERIAL, en su propio tiempo (`material.extra.palabras`, como ya las deja `insumos.voz_bloque`). Al resolver un destino, una función pura mapea cada palabra de cada clip-fuente a la línea de tiempo con el `recorte`, la `velocidad` y el `inicio_ms` de ese clip. | Ninguno de los de arriba: no hay nada que mantener sincronizado. El precio: quien resuelve para renderizar necesita las palabras de los materiales (el worker las lee de la base; el navegador las recibe con cada material). |

Por qué C: la verdad de «qué se dice y cuándo» es el audio; si el audio se corta, se mueve o se acelera, lo que
se dice se corta, se mueve o se acelera con él. Derivar hace que eso sea cierto **por construcción**, para
todos los destinos a la vez, sin que ninguna operación tenga que acordarse de los subtítulos. Es la misma idea
que `materiales` en `validar` (se deriva, nunca se confía en una lista guardada).

Es **pura y probada en los dos motores**: `final_edition/subtitulos_fuente.py` y
`static/editor/subtitulos_fuente.js`, con una tabla de paridad que genera Python
(`tests/fixtures/subtitulos_fuente_casos.json`). Las operaciones de la página siguen pasando por
`documento.validar` en Python (`tests/test_operaciones_editor.py`).

`documento.resolver` NO cambia de firma: la derivación es un paso aparte sobre el documento YA resuelto
(`subtitulos_fuente.aplicar(resuelto, palabras_por_material)`), porque el resuelto ya aplicó `por_destino` (la
voz de cada país) y ya quitó los audios de otro idioma (D10). Quien renderiza (`tareas.edicion.renderizar_final`,
que usan el editor y la vía automática) y la vista previa (`vista.js`) llaman a los dos. Quien resuelve sin
renderizar (p. ej. `editor.producir` para `verificar_recortes`) no necesita las palabras.

### D2. El mapeo exacto (idéntico en Python y JS)

Para cada clip que es fuente (D4) y cada palabra `w = {t_ms, dur_ms, texto}` de su material (tiempo del
material, ms enteros):

1. `desde = recorte.desde_ms`, `v = velocidad` (1 en audio), `tramo = duracion_ms × v` redondeado a la par.
   El clip muestra el material en `[desde, desde + tramo)`.
2. **Regla del centro**: la palabra entra si `2·desde ≤ 2·t_ms + dur_ms < 2·(desde + tramo)` (su centro cae
   dentro, comparado en enteros). Un corte que parte una palabra la deja en UNA sola mitad — nunca dos veces,
   nunca en ninguna salvo que se recorte su centro.
3. `ini = inicio_ms + mapear(max(0, t_ms − desde), v)`, `fin = inicio_ms + mapear(max(0, t_ms + dur_ms −
   desde), v)`, acotados a `[inicio_ms, min(fin del clip, fin de la principal))`; si `ini` queda en el tope, la
   palabra no entra.
4. `mapear(dt, v)`: las velocidades del editor son cuartos (`VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2]`), así
   que con `k = round(4·v)` (si `|4·v − k| < 1e-9`) es la división ENTERA `4·dt / k` redondeada a la par
   (`divmod`, sin flotantes: paridad exacta); cualquier otra velocidad cae a `round(dt / v)` (Python) /
   `redondearPar(dt / v)` (JS). `tramo` se calcula igual (`duracion_ms·k / 4` a la par).
5. El texto de la palabra: la corrección si existe (D3), si no el de Whisper; espacios colapsados y recortados;
   vacío = la palabra no entra.
6. Resultado ordenado por `t_ms` y, a igual `t_ms`, por el orden de pistas/clips/palabras. Cada palabra
   derivada lleva `{t_ms, dur_ms, texto, material_id, indice, clip_id}`; al documento resuelto solo pasan
   `{t_ms, dur_ms, texto}`.

Solo cuentan pistas no `oculta` ni `silenciada`. Un documento sin pista principal de video (imagen) no tiene
subtítulos.

### D3. Las correcciones viven por MATERIAL y por índice de palabra

`subtitulos.correcciones = {"<material_id>": {"<indice>": "texto" | ""}}`. El índice es la posición en
`material.extra.palabras`, que nunca cambia (la transcripción de un material se hace una vez y no se rehace,
D5). `""` = palabra quitada. Por qué por material y no por clip: los ids de clip cambian al cortar (la mitad
derecha recibe un id nuevo) y al duplicar; el material y el índice no. Una palabra corregida sigue corregida
en las dos mitades de un corte, en una copia del clip, y vuelve corregida si se deshace un borrado. Como el
idioma de un material es uno solo, la corrección vale para todos los destinos donde ese material suena.

«Volver a lo que se oyó» borra la corrección. Una corrección igual al texto original también se borra (no se
guardan correcciones vacías de sentido). Tope: 120 caracteres por palabra corregida.

### D4. Qué se subtitula se elige POR IDIOMA

`subtitulos.fuentes = {"<clave>": [fuente, …]}` con la clave de destino de siempre (`<idioma>` o
`<idioma>_<PAIS>`, gana la más específica: `valor_destino`). El editor escribe SIEMPRE bajo `<idioma>` (los
subtítulos dependen del idioma, no del país). Una fuente es:

- `{"tipo": "voz"}`: todos los clips de audio con `rol_audio: "voz"` (de cualquier pista salvo `p_sonido`) del
  destino resuelto — la voz del guion con su `por_destino` y las voces agregadas en el editor;
- `{"tipo": "sonido"}`: los clips de la pista principal de video (lo que se dice en cámara; a velocidad ≠ 1 el
  mapeo escala los tiempos, así siguen a los labios aunque el render quite ese sonido);
- `{"tipo": "material", "material_id": N}`: los clips (de audio no `p_sonido`, o de la principal) de ese
  material — una canción, un efecto, una grabación. Por material y no por clip, por la misma razón de D3.

Un clip cuenta una sola vez aunque dos fuentes lo nombren. La interfaz deja elegir UNA fuente por idioma (dos
fuentes que hablan a la vez se mezclarían en la misma línea); el dato es una lista para no cerrar la puerta.

Estados por idioma: clave **ausente** = lo de antes (se usan las `palabras` guardadas, si las hay: legado);
**lista vacía** `[]` = «sin subtítulos en este idioma» (gana sobre las palabras guardadas); **lista con
fuentes** = subtítulos derivados. `visibles: false` apaga los subtítulos en todos los destinos sin perder
nada.

### D5. La transcripción se paga una vez y queda en el material

- Resultado: `material.extra.palabras = [{t_ms, dur_ms, texto}]` en el tiempo del material (la misma forma que
  deja `insumos.voz_bloque`), `extra.palabras_idioma = "es"`, `extra.palabras_fuente = "whisper"`. Una
  transcripción vacía (`[]`: música sin letra, silencio) cuenta como hecha: no se vuelve a pagar.
- **Video**: Whisper recibe audio, no el video entero — el worker baja el original (o copia `extra.local`),
  extrae el audio con ffmpeg (`-vn -ac 1 -ar 16000 -c:a libmp3lame -b:a 48k`, ~360 KB por minuto), lo sube a
  una clave temporal de R2 (`clientes/<c>/materiales/stt_<material_id>.mp3`), transcribe y borra esa clave
  (`r2_uploader.delete_file`, en un `finally`; si el borrado falla, se anota y sigue: el archivo es chico).
  Las palabras quedan en el material de VIDEO.
- **Audio**: Whisper recibe la URL pública del material tal cual.
- **Idioma**: la persona lo elige («Idioma de lo que se dice»: es/en/pt, por defecto el idioma del destino que
  está viendo). fal documenta `language` como opcional (autodetección si es null, verificado en
  fal.ai/models/fal-ai/whisper/api el 2026-09-30), pero en clips cortos la autodetección falla más que acierta;
  se manda siempre. `fal_audio.transcribir_palabras` ya lo manda.
- **No se retranscribe**: si se eligió mal el idioma, las palabras quedan mal; la persona puede quitarlas o
  corregirlas. «Transcribir de nuevo» (que pagaría otra vez y borraría las correcciones de ese material) queda
  fuera de 5a.
- Carrera: `edicion_proxy` reescribe `extra` entero (lee al empezar, escribe minutos después). Hoy es seguro
  porque el worker corre una tarea a la vez, pero se endurece en esta capa: el proxy pasa a
  `materiales.actualizar_extra` (mezcla) para no pisar nunca unas `palabras` recién guardadas.

### D6. Precios y puertas de pago

| Qué | Proveedor | Precio usado | De dónde sale |
|---|---|---|---|
| Transcribir | `fal-ai/whisper` | US$ 0,002 por minuto de audio (`fal_audio.COSTO_USD_POR_MINUTO_AUDIO`) | Estimado del 2026-09-15 que ya usa la vía automática. fal no publica el precio de Whisper: la página del modelo dice «$0 per compute second» (marcador) y fal.ai/pricing no lo lista (revisado el 2026-09-30). **Pendiente**: comprobarlo en la facturación de fal en la primera prueba real y, si difiere, cambiar esa única constante. |
| Voz con IA | `fal-ai/elevenlabs/tts/multilingual-v2` | US$ 0,10 por 1 000 caracteres (`fal_audio.COSTO_USD_POR_CARACTER = 0.0001`) | fal.ai/pricing, verificado el 2026-09-30 (la misma cifra del 2026-09-28). |
| Muestra de una voz | la misma | la paga Creatv (`_creatv`), una vez por voz e idioma | `audios.muestra`, sin cambios. |
| Grabar, subir, pasar a mp3, proxies, estilos, correcciones, render | — | gratis | — |

- `fal_audio.costo_whisper(duracion_ms) = round(duracion_ms / 60 000 × COSTO_USD_POR_MINUTO_AUDIO, 4)`: la
  misma fórmula para el «≈» del botón y para el gasto registrado (por duración del audio, no por la última
  palabra: el silencio también se procesa). Un clip de 30 s cuesta US$ 0,001 → el botón dice «≈ US$ <0,01».
- `gastos.TIPOS` suma `"transcripcion"` (rótulo «Subtítulos (transcripción)» en `NOMBRES_TIPO_GASTO`); la voz
  usa el tipo existente `"locucion"`. Estimadores nuevos: `estimar("transcripcion", segundos=N)` y
  `estimar("voz_editor", caracteres=N)` = locución + transcripción de `ceil(N / 12)` segundos (12 caracteres por
  segundo: una locución lenta; redondea el estimado hacia arriba).
- Referencias de gasto: `transcripcion:<material_id>:t<tarea>` y `locucion:<hash12>:t<tarea>`
  (`tareas.ref_sufijo`), registradas con `gastos.registrar_seguro` **en cuanto el proveedor cobró**, antes de
  guardar nada — un fallo después (R2, base) no pierde el gasto. `detalle` en el idioma del proyecto.
- Puertas: ningún pago sin un clic en un botón que muestra el precio que calculó el servidor
  (`gastos.estimar(...)["texto"]`, ya formateado en el idioma de quien mira: el JS nunca formatea dinero). Si
  el precio no se pudo calcular, el botón queda desactivado con «No se pudo calcular el precio». Si todo ya está
  transcrito (o la voz ya existe con sus palabras), el botón dice «(gratis)» y no se encola nada. Tareas
  pagadas con `max_intentos=1`; un `job_id` por edición y acción (`<c>__ed<id>__subtitulos`,
  `<c>__ed<id>__voz`): un segundo clic mientras corre responde 409 y no encola otra.
- Nada se paga solo: no hay transcripción automática al agregar un audio ni al abrir. La única cosa automática
  es gratis (D14).

### D7. Estilos: una lista de EVENTOS compartida, en vez de `\k`

Hoy el karaoke usa `\k` de libass: la línea aparece naranja y cada palabra se vuelve blanca al decirse (el
color «secundario» antes, el «primario» después). No es el karaoke de CapCut (la palabra que suena resaltada) y
el `\k` obliga a imitar el acumulado en centésimas en la vista previa. Se reemplaza por una función pura que
decide QUÉ se ve y CUÁNDO — `motor/subtitulos.eventos(subtitulos, formato)` y su espejo
`static/editor/subtitulos.js::eventos` —, y los dos motores solo dibujan eventos:

```
evento = {t_ms, dur_ms, tam_px, palabras: [{texto, resaltada}]}
```

Reglas (idénticas en los dos motores, tabla `tests/fixtures/subtitulos_eventos_casos.json`):

1. Las palabras (ya derivadas o del legado) se limpian (`{`→`(`, `}`→`)`, `\`→`/`, espacios colapsados) y, si
   el estilo lo pide, van en mayúsculas (`upper()` / `toUpperCase()`).
2. `ventanas(palabras, max_palabras, max_ms=1800, max_caracteres)` — la de hoy más un tope de caracteres por
   línea (la línea se cierra si la palabra siguiente la haría pasar de `max_caracteres`; una palabra sola
   siempre entra). Sin `max_caracteres` se comporta como hoy (las tablas viejas siguen valiendo).
3. Cada ventana se estira hasta el inicio de la siguiente si el hueco es ≤ `HUECO_MAX_MS` (600 ms): la línea no
   parpadea entre palabras. Nunca se solapan: si la siguiente empieza antes de que esta termine, esta termina
   ahí. Siempre hay como mucho un evento visible.
4. Estilos que resaltan: una línea de varias palabras se parte en un evento por palabra — la palabra `j` va
   resaltada desde su inicio (la primera, desde el inicio de la línea) hasta el inicio de la siguiente (la
   última, hasta el fin de la línea). Una línea de una palabra: un evento con la palabra resaltada. Estilos que
   no resaltan: un evento por línea, nada resaltado.
5. Tamaño: `tam_px = round(tam × escala × factor)` a la par, con `factor = min(1, max_caracteres / largo de la
   línea)` — solo una palabra más larga que el tope achica su línea (una palabra de 16 letras en «Palabra
   grande» no se sale del video: ASS va con `WrapStyle: 2`, sin cortes de línea, y el navegador tampoco corta).

Los cuatro estilos (medidas en px del `PlayResY` del formato, como hoy; `fondo` es la caja con `borde: 3` o la
sombra con `borde: 1`):

| id | Nombre | tam | letra | caja/contorno (ASS `&HAABBGGRR&`, AA = transparencia) | resalta | max palabras / caracteres | mayúsculas | resaltado por defecto |
|---|---|---|---|---|---|---|---|---|
| `karaoke` | Karaoke | 64 | Inter Bold | `borde 3`, caja `&H66000000&` (negra, 60 % opaca) | sí | 4 / 22 | no | `#FFD400` |
| `caja` | Caja | 60 | Inter Bold | `borde 3`, caja `&H4D000000&` (negra, 70 % opaca) | no | 4 / 22 | no | — |
| `palabra_grande` | Palabra grande | 110 | Inter Bold | `borde 1`, contorno `&H00000000&` grosor 5, sombra `&H80000000&` de 3 | sí | 1 / 10 | sí | `#FFD400` |
| `minimal` | Mínimo | 52 | Inter SemiBold (`negrita 0`) | `borde 1`, contorno `&H00000000&` grosor 2, sin sombra | no | 5 / 28 | no | — |

Primario blanco `&H00FFFFFF&` en los cuatro; `secundario` deja de usarse (el `Style` lo escribe igual al
primario).

`motor/subtitulos.ESTILOS_ASS` (lo que ya viaja a la página en `config_navegador()["subtitulos"]["estilos"]`)
suma `max_palabras`, `max_caracteres`, `resalta`, `mayusculas` y `resaltado`; el navegador los lee de ahí,
nunca copiados. El ASS: una línea `Style` con `Fontsize = round(tam × escala)`, un `Dialogue` por evento con
`{\an5\pos(x,y)}`, `{\fs<tam_px>}` solo si el evento difiere del tamaño base, y la palabra resaltada envuelta en
`{\1c&HBBGGRR&}…{\1c&H<primario>&}`. En `compilar`, los eventos se calculan con TODO el documento y después se
recortan a la ventana del tramo (`generar_ass(..., ventana=(ini, fin))`): una línea que cruza la unión de dos
tramos sale igual que sin tramos (hoy se recortaban las palabras antes de agrupar).

Campos del documento: `estilo_id` (desconocido → `karaoke`, como hoy), `posicion` (0–1, centro de la línea),
`escala` (0,6–1,6; «Tamaño» 60–160 %), `resaltado` (`#RRGGBB` o `null` = el del estilo). El panel ofrece
Amarillo `#FFD400`, Verde `#3DDC84`, Blanco `#FFFFFF` y el color de marca (`doc.marca.color`).

Cambio visible para la vía automática: sus finales pasan del «naranja que se vuelve blanco» a «la palabra que
suena en amarillo». Es la corrección que la spec dejó pendiente («el color de resaltado es el del estilo
karaoke, no el acento de marca (pendiente de la capa 4)»).

### D8. Grabar con el micrófono

- Navegador: `getUserMedia({audio: true})` + `MediaRecorder`, con el primer tipo que el navegador soporte de
  `audio/webm;codecs=opus` (Chrome, Edge, Firefox) → `.webm`, `audio/mp4` (Safari) → `.m4a`,
  `audio/ogg;codecs=opus` → `.ogg`, `audio/webm` → `.webm`. Tope 5 min (se detiene sola y lo dice); se puede
  escuchar antes de usarla o descartarla. Sin `navigator.mediaDevices` (página no segura) o sin MediaRecorder,
  el botón explica por qué no graba. Producción es https y `127.0.0.1` cuenta como seguro.
- Servidor: ruta propia `editor.grabacion` (no la subida general, donde `.webm` es VIDEO): acepta `.webm .m4a
  .mp4 .ogg .wav` hasta 20 MB, exige una pista de audio (ffprobe), la pasa SIEMPRE a mp3 (`-vn -ac 1 -ar 44100
  -c:a libmp3lame -b:a 128k`) — el `.webm` de Chrome no trae duración y Safari viejo no decodifica opus con
  `decodeAudioData` —, mide la duración del mp3 (≤ 5 min, si no 400), respeta la cuota, sube con
  `materiales.subir(tipo="audio", origen="grabacion", extra={"nombre": "Grabación 14:32"})` (nombre armado en el
  servidor, en el idioma del proyecto, con la hora local que manda el navegador) y encola los picos (`edicion_proxy`, gratis). Grabar es gratis.
- En la edición entra como VOZ (D10): `rol_audio: "voz"` (así agacha la música como una locución), en el
  cabezal, con `idioma` = el del destino que se está viendo.

### D9. Voz con IA dentro del editor

- Se reutiliza Crear › Audios: las 22 voces de `fal_audio.VOCES` con la ficha de `audios.fichas_voces()`
  (género, tono) y la muestra de `au_muestra` (una vez por voz e idioma para toda la plataforma, la paga
  Creatv). Velocidad lenta/normal/rápida (`audios.VELOCIDADES`), texto hasta 3 000 caracteres
  (`audios.MAX_CARACTERES`), validación con `audios.validar`.
- **La misma caché que Crear › Audios**: la voz cruda es el material con hash `audios.hash_voz(texto, voz,
  idioma, velocidad)` (origen `voz`). El mismo texto con la misma voz y velocidad no se paga dos veces, se haya
  hecho en Crear o en el editor. Para no duplicar el código de pago, lo que hoy hace `tareas/audios.py::_tts`
  pasa a `audios.voz_cruda(cliente, texto, voz, idioma, velocidad, carpeta, referencia)` y lo usan las dos
  tareas.
- La tarea `editor_voz` hace TTS y, enseguida, Whisper sobre esa voz (con el idioma elegido): las palabras
  quedan en el material y «Generar subtítulos» con la voz sale gratis. El precio del botón suma las dos cosas
  (`estimar("voz_editor")`). Si Whisper falla, la voz (ya pagada) igual se entrega y el aviso dice que sus
  subtítulos se generan después. Se usa Whisper y no las marcas de tiempo propias de ElevenLabs para que todas
  las palabras del sistema salgan del mismo lugar con la misma forma.
- Entra en el cabezal (`agregarAudio(..., {rol: "voz", idioma})`), en una pista de voz, con las reglas de
  siempre: nada alarga el video (si dura más de lo que queda, se corta y se avisa «se cortó en 0:12»; con el
  cabezal al final entra entera terminando ahí). A diferencia de la voz del guion, NO lleva `por_destino`: se
  puede recortar y cortar.

### D10. Un audio puede decir en qué idioma habla (`idioma` del clip)

Contrato nuevo, compatible: un clip de audio puede llevar `idioma: "es"` (dos letras) o no llevarlo. Al
resolver un destino, un clip con `idioma` distinto del idioma del destino SE QUITA (como una voz con
`por_destino` sin ese destino). Sin `idioma`, suena en todos (lo de siempre). La voz con IA y la grabación
entran con el idioma del destino que se ve; propiedades ofrece «Suena en: Solo en Español · Todos los idiomas»
(`cambiar(clip, {idioma})`). Por qué no `por_destino`: esa forma reemplaza el clip ENTERO por destino y por eso
no se deja recortar (`cambiaPorDestino`); una grabación casi siempre hay que recortarla.

### D11. La vía automática solo toca las voces de SU guion

`borrador.agregar_destino`, `borrador.tiene_destino` y `produccion.traducir` (`hay_pista_voz`) miraban
cualquier clip `rol_audio == "voz"`. Con voces agregadas en el editor eso rompería: a un clip sin `bloque` le
pondrían `por_destino = {destino: None}` (desaparece de ese destino y ya no se puede recortar), `tiene_destino`
quedaría falso para siempre y la vía automática pagaría voces de guion en una edición que no tiene ninguna. Se
define `borrador.es_voz_de_guion(clip)` = `rol_audio == "voz"` y `bloque` no vacío, y los tres sitios lo usan.

Además, la vía automática ya deja sus subtítulos como derivados: `armar_documento` escribe
`fuentes = {<idioma>: [{"tipo": "voz"}]}` cuando hay voces, y `agregar_destino` hace `setdefault` de la misma
fuente para el idioma del destino nuevo. Sigue escribiendo `palabras` absolutas como hasta hoy (respaldo de
legado, las pruebas viejas no cambian), pero al renderizar ganan las derivadas.

### D12. Dónde vive cada cosa en la interfaz

- **Pestaña nueva «Subtítulos»** en la biblioteca: «Medios · Audio · Texto · Subtítulos · Transiciones» (en la
  columna, solo iconos; en el celular, el sexto botón de la barra de abajo). No va dentro de «Texto» porque no
  es un clip que se agrega: es una capa de la edición con su propio flujo (fuente, precio, progreso, estilo,
  lista de palabras). Su contenido, de arriba abajo: estado y «Mostrar los subtítulos»; «¿De dónde salen?»
  (La voz · El sonido del video · Audio «…») con el idioma de lo que se dice y el botón con el precio; Estilo
  (4 tarjetas que se ven con su estilo), color de la palabra que suena, Altura (Arriba · Centro · Abajo y un
  deslizador) y Tamaño; «Lo que dicen los subtítulos» (líneas con su tiempo; tocar el tiempo lleva el cabezal
  ahí; tocar una palabra la abre para corregirla — Enter guarda, Esc deja como estaba, vacía se quita —;
  «Quitar la línea»; la línea que suena se marca); «Quitar los subtítulos de este idioma».
- **Línea de tiempo**: una fila de solo lectura «Subtítulos» arriba de todo, con un bloque por línea; tocar un
  bloque lleva el cabezal ahí y abre la pestaña Subtítulos en esa línea. No se arrastra ni se recorta (los
  tiempos salen del audio).
- **Voz en off** en la pestaña **Audio**, arriba de la lista: «Voz con IA» y «Grabar tu voz», cada una abre su
  formulario ahí mismo. Galería de voces en dos columnas con filtro Mujer/Hombre y ▶ por voz.
- **Propiedades** de un audio de voz: «Suena en» (D10) y «Subtítulos de este audio» (abre la pestaña).
- El editor edita el destino que se está viendo: las fuentes se escriben bajo el IDIOMA de ese destino; el
  estado dice «Este idioma todavía no tiene subtítulos» al pasar a un destino en otro idioma, con el mismo botón
  (gratis si esas palabras ya existen). Estilo, altura, tamaño y visibles valen para todos los destinos.

### D13. Idioma de la interfaz (fase 6)

Todo texto nuevo de `static/editor/*.js` es una clave con prefijo `sub.`, `voz.` o `grab.` (y `fila.subtitulos`,
`op.*`, `prop.*`) definida igual en `final_edition/textos_editor.py::TEXTOS` (con `N_`) y en
`static/editor/textos.js::ES`; se reutilizan las que existen (`fila.voz`, `bib.subir_audio`, `bib.cargando`,
`bib.listo`, `bib.pesa_audio`, `prop.tamano`, `prop.color_*`, `prop.nota_voz`, `op.voz_destino`…). El dinero
nunca se formatea en JS: el servidor manda `precio` ya formateado y el botón usa una clave con marcador
(`"sub.generar_precio": "Generar subtítulos ≈ {precio}"`). Las rutas responden en el idioma de quien mira; lo
que se guarda o corre en el worker (nombre de una grabación, `detalle` del gasto, etapas, mensajes de la tarea)
en el del proyecto. El TEXTO de los subtítulos (lo que dice el audio, lo que escribe la persona) es contenido:
nunca pasa por el catálogo. Los mensajes de las tareas nunca llevan el texto de la persona (la ruta de estado
de trabajos no pide sesión).

### D14. Lo único automático: adoptar la voz al abrir (gratis, mismas palabras)

Un borrador automático ya existente guarda palabras absolutas y no tiene `fuentes`. Al abrirlo en el editor,
`arreglarAlAbrir` (el mismo paso de la capa 4c que acorta clips al abrir y se guarda solo) le pone
`fuentes = {<idioma>: [{"tipo": "voz"}]}` para cada idioma de sus palabras guardadas, **solo si** el documento
tiene clips de voz y TODOS sus materiales de voz (también los de `por_destino`) traen `palabras`. Resultado: los
mismos subtítulos (las palabras vienen de los mismos materiales; como mucho cambia una palabra que empezaba en
los últimos milisegundos de una voz cortada), pero desde ese momento siguen a la voz si se mueve o se corta. No
paga nada. Si no se cumple, el panel lo explica y ofrece «Generar subtítulos».

---

## 2. Formas de datos

### 2.1 Documento (esquema 1, sin migración de número)

```json
"subtitulos": {
  "estilo_id": "karaoke",
  "posicion": 0.78,
  "escala": 1.0,
  "resaltado": null,
  "visibles": true,
  "fuentes": {"es": [{"tipo": "voz"}], "en": []},
  "correcciones": {"42": {"7": "Creatv", "8": ""}},
  "palabras": {"es_CO": [{"t_ms": 0, "dur_ms": 400, "texto": "Tu"}], "es": []}
}
```

Clip de audio: campo opcional `"idioma": "es"`.

`documento.validar` — cambios exactos (los mensajes, como el resto de `validar`, son de contrato: en español,
sin `gettext`):

- `subtitulos` no objeto → `DocumentoInvalido("subtitulos debe ser un objeto.")`.
- `estilo_id`: si no está en `ESTILOS_SUBTITULOS = ("karaoke", "caja", "palabra_grande", "minimal")` (nueva
  constante en `documento.py`; `motor/subtitulos.ESTILOS` pasa a ser ESA tupla) se normaliza a `"karaoke"` sin
  fallar (hoy el motor ya caía a karaoke).
- `escala`: `_numero(sub.get("escala", 1.0), "subtitulos.escala", 0.6, 1.6)`.
- `resaltado`: `None` o `#RRGGBB` (6 dígitos, sin alfa) → si no, falla.
- `visibles`: `bool` si viene (otro tipo falla); por defecto `True`.
- `fuentes`: objeto con claves `_CLAVE_RE`; cada valor una lista de hasta 8 fuentes; cada fuente un objeto con
  `tipo` en `("voz", "sonido", "material")`; `material` exige `material_id` entero > 0 y las otras no lo
  llevan; sin repetidas. Por defecto `{}`.
- `correcciones`: objeto `{str de dígitos (id > 0): {str de dígitos (índice ≥ 0): str ≤ 120}}`. Por defecto
  `{}`.
- `palabras[clave][k].texto` debe ser `str` (hoy no se miraba).
- Clip de audio: `idioma` `None` o `^[a-z]{2}$`; en otra clase de pista, `idioma` falla.
- `materiales` NO suma los ids de `fuentes` ni de `correcciones` (no son archivos que se descarguen: un id que
  ya no existe simplemente no aporta palabras).

**Compatibilidad**: un documento viejo (sin ninguna clave nueva) valida igual y sale con `escala: 1.0`,
`resaltado: None`, `visibles: True`, `fuentes: {}`, `correcciones: {}`; como `fuentes` está vacío, se usan sus
`palabras` guardadas: se ve igual que hoy salvo el estilo karaoke (D7). No hay migración de esquema; la única
conversión es la adopción al abrir (D14), que es una operación más del editor y se guarda con CAS.

`documento.resolver` (y `static/editor/resolver.js`, tabla `resolver_casos.json` ampliada):

- quita los clips de audio cuyo `idioma` no es el del destino (antes de mirar `por_destino`);
- con `visibles is False`, `subtitulos.palabras = []`;
- conserva `fuentes`, `correcciones`, `escala`, `resaltado` y `visibles` en `res["subtitulos"]` (hoy ya
  conserva las claves que no son `palabras`).

`vista_previa.destinos` no cambia (las fuentes se escriben bajo `<idioma>`, sin país).

### 2.2 Material

`extra.palabras` (lista, puede ser vacía), `extra.palabras_idioma` (`"es"`), `extra.palabras_fuente`
(`"whisper"`). Orígenes nuevos: `grabacion` (grabación del micrófono). La biblioteca lista también `grabacion`
y `locucion` (los audios de Crear › Audios) y deja borrar `grabacion`.

`vista_previa.material_para(m, con_palabras=False)` agrega siempre `tiene_palabras` (bool: `palabras` presente)
y, con `con_palabras=True`, `palabras` (la lista). `materiales_para` (datos de la página) y
`materiales_por_id?…&palabras=1` las mandan; `biblioteca.listar` no (200 materiales con sus palabras pesarían
cientos de KB).

### 2.3 Tareas del worker

| Tarea | Payload | Intentos | Paga | Job id |
|---|---|---|---|---|
| `material_transcribir` | `{cliente, edicion_id, material_ids, idioma}` | 1 | Whisper por material | `<c>__ed<id>__subtitulos` |
| `editor_voz` | `{cliente, edicion_id, texto, voz, idioma, velocidad}` | 1 | TTS (si no estaba) + Whisper | `<c>__ed<id>__voz` |

Etapas (`N_`, con su español exacto): `ETAPAS_TRANSCRIBIR = (("Preparando el audio", 20), ("Transcribiendo",
70), ("Guardando", 10))`, `ETAPAS_VOZ = (("Creando la voz", 60), ("Preparando sus subtítulos", 30),
("Guardando", 10))`. Mensajes finales con `N_`: «Subtítulos listos.», «Voz lista.», «Voz lista; sus subtítulos
se generan después (no se pudieron preparar ahora).». `material_transcribir` sigue con los demás materiales si
uno falla (cada uno ya registró lo suyo) y al final lanza «No se pudo transcribir N archivo(s).» si alguno
falló; la página aplica lo que sí quedó.

### 2.4 Rutas (Blueprint `editor`, todas con el guard de `<cliente>`; todo POST exige mismo origen)

| Endpoint | Método y ruta | Entrada | Respuesta |
|---|---|---|---|
| `editor.subtitulos_estimar` | POST `/<id>/subtitulos/estimar` | `{material_ids}` | `{faltan: [ids], segundos, usd, precio, gratis}` |
| `editor.transcribir` | POST `/<id>/subtitulos/transcribir` | `{material_ids, idioma}` | 200 `{listo: true}` (nada que pagar) · 202 `{job_id}` · 400/404/409 `{error}` |
| `editor.voz_estimar` | POST `/<id>/voz/estimar` | `{texto, voz, velocidad, idioma}` | `{caracteres, usd, precio, ya_existe}` |
| `editor.voz` | POST `/<id>/voz` | `{texto, voz, velocidad, idioma}` | 200 `{material}` (ya existía con palabras) · 202 `{job_id, clave}` · 400/409 `{error}` |
| `editor.voz_material` | GET `/voz/<clave>` (`^[0-9a-f]{64}$`) | — | 200 `{material}` (con palabras) · 404 |
| `editor.grabacion` | POST `/materiales/grabacion` | multipart `archivo` (+ `hora` `HH:MM` opcional) | 200 `{material}` · 400 `{error}` |
| `editor.materiales_por_id` | GET `/materiales?ids=&preparar=&palabras=1` | — | igual que hoy, con `palabras` si se pide |

Límites de `transcribir`: hasta 20 ids, solo materiales de ESTE proyecto de tipo `video`/`audio` (otro → 404),
un video sin sonido (`tiene_audio is False`) se salta, suma de lo que falta ≤ 10 min (si no, 400 «Es demasiado
audio para una sola vez: hasta 10 minutos.»), idioma en `audios.IDIOMAS`.

`datos_pagina` suma: `urls.{subtitulos_estimar, transcribir, voz_estimar, voz, voz_material (con __CLAVE__),
grabacion, muestra_voz (= au_muestra), estado_trabajo (con __JOB__)}`; `voces` (fichas con género y tono
traducidos); `voz = {idiomas, nombres_idioma, velocidades: {clave: nombre traducido}, max_caracteres,
idioma_defecto}`; `grabacion = {max_ms: 300000, max_bytes}`; `trabajos_vivos = {subtitulos: job_id|null, voz:
job_id|null}` (si la página se recarga mientras algo corre, sigue la barra).

---

## 3. Página

- Módulos nuevos: `static/editor/subtitulos_fuente.js` (puro: derivar), `static/editor/subtitulos_modelo.js`
  (puro: qué fuentes hay, qué materiales pide cada una, las líneas del listado, el estado del botón),
  `static/editor/subtitulos_panel.js` (navegador: la pestaña), `static/editor/voz_modelo.js` (puro: tipo de
  grabación, reloj, estado del formulario de voz), `static/editor/voz_panel.js` (navegador: Voz con IA y
  Grabar). Se enganchan SOLO por el objeto `editor` de `pagina_editor.js`, que suma `ir(tMs)`,
  `resuelto()` (el documento resuelto del destino, con las palabras ya derivadas), `materiales()`,
  `mostrarBiblioteca(panel)` y el aviso `"biblioteca"`.
- `vista.js`: tras `resolver`, `aplicarFuentes(resuelto, palabrasDe(this.materiales))`; `infoDe` suma
  `palabras`; `fusionarMateriales` conserva `palabras` (una copia de la biblioteca sin ellas no las borra).
- `lienzo.js`: dibuja el evento de `eventos(...)` activo en `t` (caché por documento resuelto).
- Los resultados que llegan tarde (transcripción, voz) se aplican como una OPERACIÓN sobre el documento
  vigente (no sobre una copia de cuando se pidió): nunca hay conflicto de CAS por esperar.

---

## 4. Riesgos

1. **Precio de Whisper sin verificar** (D6). Mitigación: una constante, gasto registrado con la misma fórmula,
   comprobación en la primera prueba real con llaves.
2. **Whisper inventa en música o silencio** («Gracias por ver»): la lista deja quitar palabras y líneas; el
   aviso «Whisper no encontró palabras» cubre el caso vacío.
3. **Idioma equivocado** al transcribir: palabras malas sin retranscribir en 5a (D5). Mitigación: el idioma se
   elige a la vista, por defecto el del destino.
4. **Cambio visible del karaoke** en finales automáticas (D7). Es una mejora pedida; se anuncia.
5. **Mac sin libass**: el render local omite los subtítulos (ya avisado por `on_etapa`); las pruebas miran el
   texto ASS y los eventos, nunca el video. La prueba lenta de render con subtítulos solo comprueba el `.ass`
   cuando `render.tiene_libass()` es falso.
6. **Peso de la página**: las palabras de los materiales de la edición viajan en `datos-editor` (≈ 300 palabras
   por 2 min de audio ≈ 20 KB). La biblioteca NO las manda.
7. **Voces que se solapan** (voz del guion y una grabación a la vez) mezclan sus palabras en la misma línea: la
   interfaz ofrece una sola fuente; con `voz` como fuente, dos voces al mismo tiempo son decisión de la persona.
8. **Safari/iOS**: `MediaRecorder` con `audio/mp4` desde Safari 14.1; si no hay, el botón lo explica. El permiso
   del micrófono lo pide el navegador; negado → mensaje claro.
9. **La vía automática sobre un borrador editado** (D11): cubierto con `es_voz_de_guion` y pruebas.
10. **Subtítulos de otro idioma**: un destino en inglés no hereda los subtítulos del sonido en español; es
    intencional (van por idioma) y el panel lo dice.

---

## 5. Pruebas (resumen; el detalle está en el plan)

- Python: `validar` (claves nuevas, compatibilidad), `resolver` (`idioma`, `visibles`), `subtitulos_fuente`
  (cortes, velocidades en cuartos, regla del centro, correcciones, fuentes por idioma, `[]` vs ausente, pistas
  ocultas, fin de la principal), `eventos`/`generar_ass` (cuatro estilos, resaltado, estiramiento, sin solapes,
  factor de tamaño, ventana de tramo), `borrador` (fuentes, `es_voz_de_guion`), render que deriva con las
  palabras de la base, transcripción (video → audio temporal → borrado; caché; vacía; gasto aunque falle
  después), voz (caché compartida con Audios, Whisper incluido, degradación), grabación (webm/m4a → mp3, tope 5
  min), rutas (mismo origen, ajenos, 409, precios formateados), i18n (claves, catálogo, guardias).
- Paridad: `subtitulos_fuente_casos.json`, `subtitulos_eventos_casos.json`, `resolver_casos.json` y
  `ventanas_casos.json` ampliadas; `test_casos_del_editor_al_dia`.
- Node: los módulos puros; `salida_operaciones.mjs` con las operaciones nuevas validadas por Python.
- En vivo (controlador): lanzador local sin llaves, fal falso, micrófono falso de Chrome.
