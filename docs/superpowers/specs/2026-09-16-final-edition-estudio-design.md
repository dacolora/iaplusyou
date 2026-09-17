# Final edition: sonido de la escena, música al crear y estudio de remezcla — diseño

Fecha: 2026-09-16. Estado: aprobado por secciones en conversación; pendiente de
revisión escrita. Amplía el bloque 2 del motor
(`docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §3) sin cambiar
su contrato de capas.

## 0. Propósito y decisiones

La pieza final es lo que se vende. Hoy: los tres modelos de video pueden generar
el sonido de la escena y el código lo apaga (`enable_audio=False`, `"sound":
False`, `"generate_audio": False`); final edition descarta el audio del clon y
solo mezcla voz y música; la voz, la música y las palabras con tiempos se
calculan pero no se guardan, así que cualquier ajuste vuelve a pagar. El check
"con música" ya existe en final edition; no existe al crear.

Decisiones (Daniel, 2026-09-16), arquitectura **A: el sonido nace en Crear y
final edition lo conserva y remezcla**:
- Sonido de la escena **siempre** al generar un video (audio nativo del modelo),
  con descripción del sonido en el prompt.
- Música **opcional al crear** (además del check que ya existe en final edition).
- Final edition conserva el sonido del clon como una capa más y guarda stems para
  **remezclar sin volver a pagar**.
- Video→audio externo solo como **respaldo** para clones mudos (los existentes) o
  con sonido malo.
- Después: vistas previas de voces y músicas, editor de línea de tiempo del
  guion, efectos y ritmo.

Hechos verificados el 2026-09-16 en fuentes primarias (fal, ElevenLabs,
Higgsfield): Higgsfield no expone video→audio; lo que muestra su app es el audio
nativo de los modelos. Audio nativo: Wan 3.0 sin recargo (`audio`), Kling O3
Pro `generate_audio` de USD 0,112 a 0,14 por segundo, Seedance incluido
(`generate_audio`). Voces nativas de Kling: solo chino e inglés. Video→audio con
licencia clara: `sonilo/v1.1/video-to-sound-effects` (USD 0,009/s, solo audio,
acepta `segments[]` con descripción por tramo) y `fal-ai/kling-video/video-to-audio`
(USD 0,035 por clip de 3–20 s, MP3 aparte). MMAudio y ThinkSound descartados
(licencia no comercial, balbuceos). Efectos por texto:
`fal-ai/elevenlabs/sound-effects/v2` (USD 0,002/s). Los nombres de parámetro
del proveedor que usa `wan3_client` (WaveSpeed) se confirman con una llamada de
prueba al implementar.

---

## S1. Sonido de la escena al crear (Crear)

> Estado 2026-09-17: **núcleo implementado** (rama `worktree-sonido-crear`):
> `audio_nativo` por modelo con parámetros verificados en WaveSpeed (Wan 3.0
> `enable_audio` sin recargo, Kling O3 Pro `sound` +0,028 USD/s, Seedance 2.5
> `generate_audio` sin recargo), `generar_video(..., con_sonido=True)` y
> `estimate_video(..., con_sonido=True)` por defecto, `usd_por_segundo_efectivo`
> en las plantillas, `flowplus_prompt.armar(..., sonido=, con_sonido=)` con la
> línea SONIDO (regresión: sin sonido el prompt es idéntico), y el worker anota
> con ffprobe `sonido {proveedor, estado}` en la sesión (🔊/🔇 en la tarjeta).
> Pendiente de S1: check "Sonido de la escena", campo con "Sugerir"
> (`fp_sugerir_sonido`), preferencias por proyecto, música al crear, paso
> Mezcla, `video_url_crudo` y `pieza.capas`.

- `flowplus_modelos.VIDEO[modelo]["audio_nativo"] = {"parametro": ...,
  "recargo_usd_s": ...}`: Wan 3.0 (`audio`/`enable_audio` según proveedor, 0),
  Kling O3 Pro (`generate_audio`, 0.028), Seedance 2.5 (`generate_audio`, 0).
  `generar_video(..., con_sonido=True)` activa el parámetro;
  `estimate_video(modelo, duracion, con_sonido=True)` suma el recargo.
- Crear: check "Sonido de la escena" marcado por defecto (se puede quitar para
  piezas solo con música). Preferencia por proyecto en Configuración
  (`proyectos.preferencias_sonido`: `con_sonido`, `musica_al_crear`,
  `proveedor_v2a`).
- Campo "Sonido de la escena" (texto corto, opcional) con botón "Sugerir": ruta
  `fp_sugerir_sonido` llama a Claude con la escena, la persona (si viene de un
  sprint) y el enfoque; devuelve 1–2 líneas ("risas de niños, pasos descalzos
  sobre baldosa, respiración agitada al final").
- `flowplus_prompt.armar(..., sonido=None)`: cuando hay texto agrega
  `SONIDO: <texto>. Sin diálogo hablado ni música de fondo.`; cuando `con_sonido`
  y no hay texto, agrega solo `SONIDO: ambiente natural de la escena. Sin diálogo
  hablado ni música de fondo.`; con `sonido=None` y `con_sonido=False` el prompt
  es idéntico al actual (prueba de regresión). "Sin diálogo" evita las voces
  nativas de Kling (chino/inglés); la voz en español la pone ElevenLabs.
- Selector "Música al crear: ninguna | <estilo>" (defecto: preferencia del
  proyecto; inicial ninguna) con botón de reproducir por estilo (S5).
- `tareas/flowplus.ejecutar_video` gana el paso **Mezcla** (`ETAPAS_CREATIVE_FLOW`
  suma `("Mezclando sonido", 5)` y se reponderan las demás para seguir sumando
  100) usando `final_edition/mezcla.py`:
  1. `ffprobe`: ¿trae pista de audio? Si no, `capas.sonido.estado = "ausente"`.
  2. Si eligió música: `musica.obtener_pista(estilo, duracion)` (caché, USD
     0,02); mezcla sonido 1.0 + música 0.45 + `loudnorm=I=-14:TP=-1.5:LRA=11`.
  3. Sube `video_url` (mezclado, el que se ve, publica y entrega) y
     `extra["video_url_crudo"]` (solo sonido nativo, fuente de final edition).
     Sin música, el crudo es el mismo archivo y no se recodifica.
- El clon guarda en `pieza.capas`: `sonido {proveedor: <modelo>, estado: ok |
  ausente, parametros: {prompt}}`, `musica {estilo, url, costo_usd}` y `mezcla
  {loudnorm, volumenes}`. `creative_flow.actualizar` acepta `capas` y
  `video_url_crudo` para el clon (`_PIEZA_COLS` / `extra`).
- Tarjeta del clon en Crear: iconos de sonido y música, reproductor, y "Sin
  sonido · Generar sonido (USD 0,09)" cuando `ausente` (S3).
- Las ideas del sprint ganan el campo `sonido` (spec de sprints §2.1).

## S2. Capa "sonido" en final edition

- Fuente: `extra.video_url_crudo`, o `video_url` en clones anteriores.
- `cortes.py`: `planificar_segmentos` no cambia; `render.construir_filtergraph`
  recorta el audio del clon con los mismos `inicio`/`fin` de cada segmento
  (`[0:a]atrim=...,asetpts=PTS-STARTPTS[a_i]`) y los concatena (`concat
  v=0:a=1`), así queda sincronizado por construcción. Si el clon no tiene pista
  de audio, la capa se marca `omitida`.
- Mezcla (`mezcla.py`, usada por el render): voz encima; sonido con ducking
  suave por la voz (`sidechaincompress` ratio 4, attack 20, release 300); música
  con el ducking actual (ratio 8); `amix` de las que existan (1 a 3) y
  `loudnorm` final. Constantes: `VOL_SONIDO = 1.0`, `VOL_MUSICA_CON_VOZ = 0.35`,
  `VOL_MUSICA_SOLA = 0.5`, `VOL_MUSICA_CON_SONIDO = 0.45`.
- Opciones nuevas en `_OPCIONES_DEFECTO`: `con_sonido: True`, `sonido: "nativo"
  (nativo | generado | ninguno)`, `mezcla: "equilibrada"`, `volumenes: None`
  ({voz, sonido, musica} en 0–1, manda sobre el preset).
- Presets: `equilibrada` (1.0 / 1.0 / 0.35), `voz_protagonista` (1.0 / 0.6 /
  0.25), `ambiente_protagonista` (1.0 / 1.0 / 0.2).
- `capas.sonido` de la final: `{proveedor: nativo | sonilo | kling_v2a,
  estado, url (stem recortado en R2), costo_usd}`.

## S3. Respaldo: video→audio

- `providers/fal_audio.py::sonido_desde_video(video_url, segmentos=None,
  prompt=None, proveedor="sonilo")`: Sonilo por defecto (`segments[]` contiguos
  desde 0 con la descripción de cada bloque del guion, o un solo tramo con el
  texto de "Sonido de la escena"); Kling V2A como alternativa (`sound_effect_prompt`
  = mismo texto, `background_music_prompt = "no music"`, verificar en la prueba
  que no incrusta música). Devuelve `{url_audio, costo_usd, proveedor}`.
  Costos: Sonilo `0.009 × segundos`; Kling 0.035 por clip.
- Dos usos: (a) botón "Generar sonido" en la tarjeta de un clon mudo → tarea
  `flowplus_sonido` (`max_intentos=1`, gasta): genera, mezcla como en S1, guarda
  `capas.sonido {proveedor, url, costo}` y reemplaza `video_url` / `video_url_crudo`;
  (b) en final edition, `sonido = "generado"` produce el stem desde el clon crudo
  (costo mostrado antes) y lo guarda en `capas.sonido.url` para no volver a pagar.
- Proveedor elegible en Configuración; el costo aparece siempre antes del clic.

## S4. Stems y "Remezclar"

- Cada final guarda en R2 (`clientes/<c>/finales/<final_id>/`): `voz.wav` →
  `capas.voz.url` y `capas.voz.palabras` (json con tiempos), `capas.musica.url`
  (ya existe), `sonido.wav` → `capas.sonido.url`. Los overlays de texto no se
  guardan: se regeneran gratis con Pillow.
- Tarea `final_remezclar` (`payload {cliente, final_id, opciones}`,
  `max_intentos=3`, sin costo salvo bloques de voz cambiados, ~20–30 s): baja
  los stems, regenera texto con la plantilla elegida, renderiza con las opciones
  nuevas (`con_voz`, `con_musica`, `con_sonido`, `mezcla` o `volumenes`,
  `plantilla_id`, `entrada_hook`, `cierre`, `efectos`, `cortes_al_ritmo`).
  Reemplaza `url_video`/`url_miniatura` solo al terminar bien (como hoy); guarda
  las opciones en `capas.render.parametros`.
- Finales producidas antes de este cambio no tienen stems: "Remezclar"
  deshabilitado con "producida antes de los stems; vuelve a producir".
- `job_id = f"{cliente}__{final_id}__remezcla"`.

## S5. Vistas previas de voces y músicas

- Voces: muestra de ~3 s por voz e idioma con una frase fija (`tipos.FRASE_MUESTRA`
  por idioma), generada una vez por la tarea `fe_muestras` (≈ USD 1,30 en total
  para 22 voces × 3 idiomas) y guardada en R2 (`data/muestras/voces/<voz>_<idioma>.mp3`);
  `final_edition/muestras.py` lista las existentes y encola las que falten. En el
  selector de voz, botón de reproducir por opción.
- Músicas: 15 s por estilo desde `musica.obtener_pista(estilo, 15)` (USD 0,02 por
  estilo, una vez); botón de reproducir junto al estilo en final edition y en Crear.
- Tira de fotogramas: al abrir final edition de un clon se extraen 8 fotogramas
  (una vez, `clientes/<c>/finales/tiras/<cf_id>_<n>.jpg` en R2) y los cinco
  bloques del guion se dibujan encima según sus tiempos.

## S6. Editor de línea de tiempo del guion

- Sobre la tira: inicio y fin de cada bloque arrastrables (contiguos, mínimo
  0,8 s, total ≤ duración), texto en pantalla y texto de voz editables, y por
  bloque los interruptores `con_voz` y `en_pantalla` (nuevas claves opcionales
  del bloque, defecto `true`). `fe_guardar_guion` acepta tiempos y banderas;
  `tipos.validar_guion` los valida (roles y orden intactos, tiempos contiguos y
  dentro de la duración).
- Caché de voz por bloque: `voz._sintetizar_bloque` guarda cada mp3 en R2 con
  clave `hash(texto_voz, voz, idioma)` (`data/voz_cache/<hash>.mp3`) y reutiliza
  si existe; al producir o remezclar solo se sintetizan los bloques cambiados.
  "Aplicar" muestra el costo exacto ("2 bloques de voz: USD 0,01") antes del clic.
- `texto.generar_overlays` respeta `en_pantalla=false` (sin overlay de ese bloque;
  los subtítulos siguen la voz).

## S7. Efectos y ritmo

- Cortes al ritmo (`final_edition/ritmo.py`): la música se pide con BPM fijo por
  estilo en el prompt (`tipos.BPM_POR_ESTILO`: energético 124, calmado 80, lujo
  90, etc.); los límites de los segmentos se ajustan a la rejilla de compases
  (`60/BPM × 4`, con tolerancia de ±0,25 s y respetando `min_seg`); el desfase
  inicial se estima con la envolvente de energía de `ffmpeg astats` por ventanas
  de 50 ms (sin librerías de audio en Python; el servidor solo tiene Pillow).
  Opción `cortes_al_ritmo` (defecto `true` cuando hay música). Funciones puras
  con pruebas.
- Golpes y whoosh (`final_edition/efectos.py`): set de 8 efectos cortos
  generados una vez con `fal-ai/elevenlabs/sound-effects/v2` (centavos) y
  cacheados en R2 (`data/sfx/`), con la licencia de fal verificada antes de
  activarlo en producción. Whoosh en cada corte y golpe suave al inicio del hook,
  a -12 dB, entradas adicionales en la misma mezcla. Opción `efectos` (defecto `true`).
- Animación del hook: entrada por deslizamiento con rebote mediante expresiones
  de tiempo en `overlay` (`y='...'` en función de `t`, sin decodificar el PNG de
  nuevo) y aparición gradual con 6 PNG de alfa durante 300 ms (6 overlays más,
  dentro de `MAX_OVERLAYS_TOTAL`). Opción de plantilla `entrada_hook: ninguna |
  deslizar | aparecer` (defecto `deslizar`).
- Tarjeta final: `cierre: tarjeta | ninguno` (defecto `tarjeta`): los últimos
  1,5 s son una tarjeta a pantalla completa con logo, CTA y color de marca, en
  lugar de la tarjeta de CTA sobre el video. Se implementa como overlay opaco de
  pantalla completa; los subtítulos no se dibujan en esa ventana.
- Las opciones de plantilla se leen de `plantilla_texto` cuando exista (spec de
  sprints, Parte 3) y de `_OPCIONES_DEFECTO` mientras tanto.

## S8. El "Estudio" (experiencia)

Panel de final edition en cuatro bloques y barra fija abajo:

1. **Guion**: la tira con los bloques (S6).
2. **Audio**: voz (selector con reproducir, `con_voz`), sonido de la escena
   (`nativo | generado | ninguno`, con "Generar sonido" y su costo cuando no hay
   nativo), música (estilo con reproducir, `con_musica`), preset de mezcla y tres
   deslizadores con el número al lado.
3. **Visual**: plantilla (selector con miniatura), entrada del hook, tarjeta
   final, efectos en cortes, cortes al ritmo.
4. **Destinos y precios**: como hoy.

Barra inferior: costo de lo que se va a pagar ("Voz 2 bloques USD 0,01 · Música
en caché USD 0 · Sonido nativo USD 0 · Render gratis") y un solo botón:
"Producir N finales" la primera vez, "Remezclar (gratis)" después. Regla
visible: la primera producción paga voz y música; después todo es gratis o
centavos. Cada final muestra qué capas tiene (iconos) y sus stems.

En Crear: la tarjeta del clon muestra sonido y música, reproductor y "Generar
sonido" si salió mudo; el formulario gana "Sonido de la escena" y "Música al crear".

## S9. Módulos, cambios y pruebas

Nuevos: `final_edition/mezcla.py`, `final_edition/sonido.py`,
`final_edition/efectos.py`, `final_edition/ritmo.py`, `final_edition/muestras.py`.
Tareas: `final_remezclar`, `flowplus_sonido`, `fe_muestras`. Rutas:
`fp_sugerir_sonido`, `fe_remezclar`, `fe_generar_sonido`, `fe_muestras`.

Cambios a lo existente: `flowplus_modelos` (`audio_nativo`, `con_sonido` en
`generar_video` y `estimate_video`), `flowplus_prompt.armar(sonido=)`,
`tareas/flowplus.ejecutar_video` (paso Mezcla), `creative_flow` (`capas` y
`video_url_crudo` en el clon), `render.py` (entrada de audio del clon, tres
capas, `loudnorm`, animaciones, tarjeta final), `voz.py` (caché por bloque,
`con_voz` por bloque), `texto.py` (`en_pantalla`, alfa del hook, tarjeta final),
`guion.py`/`tipos.validar_guion`/`fe_guardar_guion` (tiempos y banderas),
`providers/fal_audio.py` (`sonido_desde_video`, `efecto_sonoro`, BPM en el prompt
de música), `proyectos.py` (preferencias de sonido), Configuración. Sin
migración: `pieza.capas` y `extra` ya existen.

Pruebas: sincronía del audio recortado con una pista de clics conocida
(`slow`); mezcla con `aevalsrc` y loudness verificado con `ebur128` (`slow`);
stems persistidos y remezcla sin llamadas a proveedores (fal falso); caché de
voz por bloque (solo se sintetizan los cambiados); rejilla de BPM y ajuste de
segmentos (puras); estimado con recargo de Kling; prompt con `SONIDO:` y
regresión sin él; `validar_guion` con tiempos editados; render con `en_pantalla`
y tarjeta final (cajas, no píxeles).

## S10. Orden de construcción y alcance

1. Sonido nativo en Crear + "Sonido de la escena" + música al crear + capa sonido
   en final edition (S1, S2). Visible: un video nuevo suena; la final lo conserva.
2. Stems, Remezclar y vistas previas (S4, S5). Visible: cambiar volúmenes o
   plantilla sin pagar; escuchar voces y músicas antes.
3. Video→audio de respaldo, efectos y ritmo (S3, S7). Visible: clones viejos
   con sonido; cortes al compás; hook animado; tarjeta final.
4. Editor de línea de tiempo (S6). Visible: mover bloques y editar por bloque
   pagando centavos.

Fuera de esta versión: doblaje o clonación de la voz del cliente, voces nativas
del modelo en español, música con letra, detección de beats con librerías de
audio (se usa rejilla por BPM), vista previa en tiempo real en el navegador
(el render de 20 s es la vista previa).

## S11. Riesgos

- Nombres y precios de los parámetros de audio nativo en WaveSpeed (proveedor de
  `wan3_client`) pueden diferir de fal: confirmar con una llamada de prueba y
  con `estimate` antes de fijar el recargo.
- Kling V2A: no está documentado si `background_music_prompt` vacío suprime la
  música; probar antes de ofrecerlo; Sonilo es el defecto.
- `loudnorm` de una pasada puede desviarse ±1 LU; suficiente para redes.
- Cada overlay cuesta ~8 MB de RSS en ffmpeg: los 6 PNG de alfa del hook y la
  tarjeta final entran en `MAX_OVERLAYS_TOTAL` (se descuentan del cupo de
  subtítulos si hace falta).
- Licencia de los efectos generados con ElevenLabs vía fal: verificar por
  escrito antes de usarlos en anuncios pagados.
