# Audios: idiomas de la zona europea y voces propias (2026-09-30)

Pedido de Daniel: el público objetivo de Audios pasa a ser la zona europea
(Finlandia, Irlanda, Suiza, Suecia, Alemania, República Checa, Noruega), así que
Audios necesita esos idiomas, y además «voces propias» del proyecto. Decisión de
Daniel (2026-09-30): clonar y diseñar voces con **MiniMax vía fal** (fal no ofrece
clonar ni diseñar con ElevenLabs). Construye sobre
`docs/superpowers/specs/2026-09-28-crear-audios-design.md` y la galería de voces
del 2026-09-29.

## 1. Qué ve la persona

### Idiomas

- El selector «Idioma» pasa a llamarse **«Idioma del texto»** y ofrece diez
  idiomas, cada uno en su propia lengua: Español, English, Português, Deutsch,
  Français, Italiano, Suomi, Svenska, Norsk, Čeština. Por defecto, el del
  proyecto (como hoy).
- La ayuda debajo dice: «Elige el idioma en que está escrito el texto: con él
  suena la muestra de cada voz y, en noruego y en tus voces propias, se fuerza
  el acento.»
- Irlanda va en inglés y Suiza en alemán, francés o italiano estándar. No se
  ofrece irlandés gaélico ni suizo alemán (fuera de alcance, §6).

### Mis voces

Arriba de la galería de las 22 voces aparece la sección **«Mis voces»**:

- Una tarjeta por voz propia, con el mismo aspecto que las de la galería:
  nombre, «Clonada» o «Diseñada», ▶ para oír su muestra en el idioma del texto,
  y un botón «Borrar». Tocar la tarjeta la elige, igual que una voz de la galería.
- Una tarjeta **«+ Crear voz propia»** que abre un panel con dos pestañas:
  - **Clonar una voz:** nombre (1–40 caracteres), archivo de audio (mp3, wav,
    m4a, aac u ogg; de 10 segundos a 5 minutos; hasta 20 MB) y una casilla
    obligatoria: «Es mi voz o tengo permiso escrito de la persona para clonarla
    y usarla en anuncios.» Botón «Clonar voz ≈ US$ 1,50».
  - **Diseñar una voz:** nombre y descripción (10–500 caracteres, con ejemplo:
    «Mujer de unos 30 años, voz cálida y cercana, ritmo pausado, acento sueco
    suave»). Aviso: «No describas a una persona real ni pidas imitar a alguien
    famoso.» Botón «Diseñar voz ≈ US$ 3,00».
- Al pulsar, aparece una barra de progreso en «Mis voces» (Creando la voz →
  Estrenando la voz → Guardando). Al terminar, la sección se repinta sola, la
  voz nueva queda elegida y un aviso lo dice. Una creación a la vez por
  proyecto.
- Sin voces propias todavía, la sección muestra solo la tarjeta de crear y una
  línea: «Clona una voz con permiso o diseña una nueva desde una descripción.»
- Los filtros Todas · Mujer · Hombre siguen filtrando solo las voces de la
  galería; «Mis voces» se ve siempre.

## 2. Cómo suena cada voz: motores

Un solo punto del código, `audios.motor_de(voz, idioma)`, decide:

| Voz | Idioma | Motor (fal) | Idioma forzado | Precio |
|---|---|---|---|---|
| De la galería | todos menos noruego | `fal-ai/elevenlabs/tts/multilingual-v2` | no (lo detecta del texto) | US$ 0,10 / 1 000 caracteres |
| De la galería | noruego | `fal-ai/elevenlabs/tts/turbo-v2.5` | `language_code: "no"` | US$ 0,05 / 1 000 caracteres |
| Propia (`vp:<id>`) | todos | `fal-ai/minimax/speech-2.8-hd` | `language_boost` | US$ 0,10 / 1 000 caracteres |

Verificado con llamadas reales el 2026-09-30: Turbo v2.5 lee noruego con «Adam»
(voz fuera de su lista documentada) y velocidad 1,15; MiniMax Speech 2.8 HD
responde `{"audio": {"url"}, "duration_ms"}`; Multilingual v2 lee checo.

- `language_boost` de MiniMax: es→Spanish, en→English, pt→Portuguese,
  de→German, fr→French, it→Italian, fi→Finnish, sv→Swedish, no→Norwegian,
  cs→Czech.
- Velocidad: ElevenLabs `speed` (0,7–1,2) y MiniMax `voice_setting.speed`
  (0,5–2,0) con los mismos valores de hoy (0,85 / 1,0 / 1,15).
- MiniMax: `output_format: "url"`, `audio_setting: {format: mp3, sample_rate:
  44100, bitrate: 128000, channel: 1}`.
- Hash de la voz cruda (`audios.hash_voz`): para Multilingual v2 se mantiene la
  fórmula de hoy (sin idioma, para no invalidar lo ya cacheado); para Turbo y
  MiniMax entra el motor y el idioma, porque ahí el idioma cambia lo que suena.

## 3. Voces propias con MiniMax

### Crear

Tarea del worker `voz_propia_crear` (`tareas/voces_propias.py`),
`max_intentos=1`, job `<cliente>__voz_propia` (una creación a la vez por
proyecto; independiente de `audio_generar`). Etapas: «Creando la voz» (70),
«Estrenando la voz» (20), «Guardando» (10).

- **Clonar:** la ruta guarda primero la grabación en R2 como `material`
  (tipo `audio`, origen `grabacion`, hash `hash_clave("grabacion", <hash del
  archivo>)` para no chocar con una canción idéntica de Mi música, key
  `clientes/<c>/materiales/grabacion_<hash16><ext>`) y encola. La tarea llama a
  `fal-ai/minimax/voice-clone` con `{audio_url, noise_reduction: true,
  need_volume_normalization: true}` → `custom_voice_id`. Costo US$ 1,50.
- **Diseñar:** la tarea llama a `fal-ai/minimax/voice-design` con `{prompt:
  descripción, preview_text: frase de muestra}` → `custom_voice_id` (+ un audio
  de vista previa). Costo US$ 3,00 más US$ 0,03 por 1 000 caracteres de vista
  previa.
- **El gasto de la creación se registra en cuanto fal responde**, antes de
  seguir (tipo `voz_propia`, referencia `voz_propia:<forma>:t<tarea_id>`,
  proveedor `fal/minimax`).
- **Estrenar:** MiniMax borra una voz que no se usa en una síntesis real
  dentro de 7 días (la vista previa del clon no cuenta). Por eso la tarea, en
  el mismo paso, sintetiza con `speech-2.8-hd` la frase de muestra del idioma
  elegido («Hola, soy <nombre>…») y registra ese gasto (tipo `locucion`). Ese
  mp3 queda en R2 y es la muestra de la voz en ese idioma.
- **Si estrenarla falla** (después de pagar la creación), la voz se guarda
  igual, con `extra.estrenada = false` y como muestra la vista previa del
  diseño o la grabación del clon; la tarea termina con el mensaje «Voz creada,
  pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda.» El
  primer ▶ o el primer audio con esa voz la estrena.
- **Guardar:** la voz es una fila `material` del proyecto: tipo `audio`, origen
  `voz_propia`, `url` = su muestra, hash `hash_clave("voz_propia", "minimax",
  custom_voice_id)`, `duracion_ms` de la muestra, `costo_usd` = lo pagado por
  crearla, `extra = {nombre, forma: "clonada"|"disenada", proveedor: "minimax",
  voice_id, idioma_muestra, estrenada, descripcion? (diseño), consentimiento?
  (clon: {usuario, fecha, texto}), grabacion_id? (clon)}`. Sin migración.

### Usar

- En el formulario, una voz propia viaja como `voz = "vp:<material_id>"`.
  `audios.validar` la acepta si `voces_propias.resolver(cliente, valor)` la
  encuentra en ese proyecto.
- La tarea `audio_generar` sintetiza con `audios.sintetizar(...)`, que despacha
  por motor; con una voz propia llama a MiniMax con su `voice_id` y el
  `language_boost` del idioma del texto. El gasto se registra igual que hoy,
  con el proveedor del motor en el detalle.
- En la lista «Tus audios» el ítem muestra el nombre de la voz propia.
- Si la voz se borró entre el clic y el worker, la tarea falla sin pagar nada.
- ▶ de una voz propia en otro idioma: la ruta `au_muestra` sintetiza esa
  muestra (cacheada por `hash_clave("muestra_propia", voice_id, idioma, 1)`,
  origen `voz`, bajo el proyecto) y la cobra al proyecto (tipo `locucion`).

### Borrar

«Borrar» quita la fila de la voz, su grabación (si es un clon) y sus muestras
por idioma, con sus objetos en R2 (`materiales.borrar`). La voz en la cuenta de
MiniMax de fal no se puede borrar desde fal y queda ahí sin uso. Los audios ya
hechos con esa voz se conservan.

### Consentimiento

- Clonar exige la casilla; la ruta responde 400 sin ella («Marca la casilla de
  permiso para clonar esta voz.»).
- Se guarda `extra.consentimiento = {usuario, fecha, texto}`, donde `texto` es
  el msgid exacto de la casilla.
- La grabación queda en R2 mientras exista la voz.

## 4. Diseño técnico

### `providers/fal_audio.py`

- Constantes: `MODELO_TTS_TURBO = "fal-ai/elevenlabs/tts/turbo-v2.5"`,
  `COSTO_TURBO_POR_CARACTER = 0.00005`, `MODELO_MINIMAX_TTS =
  "fal-ai/minimax/speech-2.8-hd"`, `COSTO_MINIMAX_POR_CARACTER = 0.0001`,
  `MODELO_MINIMAX_CLONAR = "fal-ai/minimax/voice-clone"`, `COSTO_CLONAR_VOZ =
  1.50`, `MODELO_MINIMAX_DISENAR = "fal-ai/minimax/voice-design"`,
  `COSTO_DISENAR_VOZ = 3.00`, `COSTO_VISTA_PREVIA_POR_CARACTER = 0.00003`,
  `IDIOMAS_MINIMAX` (el mapa de §2).
- `tts(texto, voz, idioma, on_progreso, velocidad, timeout, modelo=MODELO_TTS,
  language_code=None)`: mismo contrato; `language_code` solo viaja si no es
  None; el costo usa la tarifa del modelo.
- `tts_minimax(texto, voice_id, idioma, velocidad=None, timeout=180)` →
  `{"url", "costo_usd", "duracion_ms"}`.
- `clonar_voz_minimax(audio_url, timeout=300)` → `{"voice_id", "costo_usd"}`.
- `disenar_voz_minimax(prompt, preview_text, timeout=300)` → `{"voice_id",
  "url_vista_previa", "costo_usd"}`.
- Cada una lanza `RuntimeError` si fal no devuelve lo esperado.

### `audios.py`

- `IDIOMAS` con los diez; `NOMBRES_IDIOMA`; `FRASES_MUESTRA` en los diez.
- `motor_de(voz, idioma)` → `"elevenlabs"`, `"elevenlabs_turbo"` o `"minimax"`.
- `hash_voz` según §2 (misma firma).
- `validar` acepta `vp:<id>`.
- `sintetizar(cliente, voz, texto, idioma, velocidad, timeout=180)` →
  `{"url", "costo_usd", "proveedor", "voz_nombre"}`; `ValueError` si la voz
  propia ya no existe.
- `muestra(voz, idioma)` (galería) usa Turbo para el noruego; el resto igual.

### `voces_propias.py` (nuevo, único escritor de las filas `voz_propia` y `grabacion`)

`PREFIJO = "vp:"`, `ORIGEN`, `ORIGEN_GRABACION`, `FORMAS`, límites, `MENSAJES`
(msgids), `TEXTO_CONSENTIMIENTO` (msgid), `EntradaInvalida`.
`listar(cliente)`, `resolver(cliente, valor)`, `obtener(cliente, id)`,
`validar_disenar(form)`, `guardar_grabacion(cliente, archivo, carpeta_tmp)`,
`validar_clonar(cliente, form, grabacion)`, `crear(cliente, payload,
ref_sufijo, reportar)` (lo llama la tarea), `muestra(cliente, voz, idioma)`,
`borrar(cliente, id)`.

### Rutas (`dashboard.py`, junto a las `au_*`)

- `GET /cliente/<c>/audios/voces` (`vp_lista`) → JSON `{ok, html (fragmento
  `_audios_mis_voces.html`), voces, trabajo, error, mensaje, job_id}`.
- `POST /cliente/<c>/audios/voces/clonar` (`vp_clonar`), multipart.
- `POST /cliente/<c>/audios/voces/disenar` (`vp_disenar`).
- `POST /cliente/<c>/audios/voces/<int:vid>/borrar` (`vp_borrar`).
- `au_muestra` acepta `vp:<id>` del proyecto.
- Todos los POST exigen `_mismo_origen()`; todo va bajo `<cliente>`.

### Gastos

`gastos.TIPOS` suma `voz_propia`; `NOMBRES_TIPO_GASTO["voz_propia"] =
N_("Voces propias")`; estimadores `voz_clonada` y `voz_disenada` con las
constantes de `fal_audio`.

### Plantillas, JS, CSS e idioma

`_audios_mis_voces.html` (fragmento de la sección, re-pintado por fetch; su
barra usa `data-job` + `data-estado`, nunca `data-poll-job`), `_crear_audios.html`
(la sección arriba de la galería, el panel de crear, el selector con diez
idiomas y la ayuda nueva, el JS de crear/borrar/sondear y ▶ de voces
propias), CSS con prefijo `au-vp`, todo texto al catálogo inglés.

## 5. Pruebas

- `tests/test_fal_audio.py`: `tts` con `modelo`/`language_code` y tarifa por
  modelo; `tts_minimax` (payload, mapa de idiomas, respuesta, error);
  `clonar_voz_minimax` y `disenar_voz_minimax` (payload y respuesta).
- `tests/test_audios.py`: `motor_de`, `hash_voz` por motor, `validar` con
  `vp:`, `sintetizar` por motor, `muestra` del noruego por Turbo, diez frases.
- `tests/test_voces_propias.py`: grabación (extensión, 10 s–5 min, cuota, hash
  propio), `validar_clonar` sin casilla, `validar_disenar`, `crear` clon y
  diseño con fal simulado (gasto registrado antes de estrenar, fila con
  `extra`, estreno fallido guarda la voz con `estrenada=false`), `listar`,
  `resolver` ajeno, `muestra` cacheada y cobrada al proyecto, `borrar`.
- `tests/test_tarea_voz_propia.py` y `tests/test_tarea_audio.py`: tarea
  registrada, mensajes fijos sin texto del cliente, `audio_generar` con voz
  propia por MiniMax con `language_boost`.
- `tests/test_rutas_audios.py`: sección y panel en la página, diez idiomas,
  crear (casilla obligatoria, una a la vez, `max_intentos=1`), borrar,
  `au_muestra` con `vp:`, 403 de otro sitio.
- Inventario del worker, catálogo inglés, rendimiento de la página: verdes.
- Prueba real con fal: diseñar una voz, sintetizar con ella ~15 s, clonar desde
  ese audio, leer en finés, noruego y checo, y un audio de la galería en
  noruego y en alemán; limpieza al final. ≈ US$ 4,60, sin grabar a nadie.

## 6. Fuera de alcance

Usar las voces propias en Final edition o en los videos de Crear; irlandés
gaélico y suizo alemán; más voces de fábrica de MiniMax en la galería; borrar
la voz en la cuenta de MiniMax; límite de voces por proyecto (el costo visible
en el botón basta por ahora).
