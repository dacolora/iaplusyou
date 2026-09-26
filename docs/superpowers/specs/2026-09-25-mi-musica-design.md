# Mi música: canciones propias y música con ElevenLabs (2026-09-25)

Pedido de Daniel: que el cliente pueda poner su propia música en las piezas —
subir sus audios y elegir desde qué segundo empiezan— y generar música a medida
con ElevenLabs. La voz clonada (tercera parte pedida) queda **fuera** de este
spec: fal no ofrece clonación de ElevenLabs y la cuenta directa tiene dudas de
licencia (uso individual / reventa); se decide aparte.

## Qué ve el cliente

### En Crear (junto a «Música al crear»)

- El selector `musica_estilo` pasa a tener dos grupos:
  - **Estilos IA** — los de `final_edition.tipos.ESTILOS_MUSICA`, como hoy (≈ US$ 0,02).
  - **Mi música** — las canciones del proyecto (subidas o creadas), valor `mat:<material_id>`.
- Botón **Subir canción** (mp3, wav, m4a, aac, ogg; ≤ 20 MB; ≤ 10 min).
- Botón **Crear canción con IA (ElevenLabs)**: abre un mini formulario con la
  descripción, la casilla **Instrumental** (marcada por defecto) y el botón
  «Crear canción ≈ US$ 0,60». Aviso: no nombrar artistas, canciones ni sellos
  (ElevenLabs lo rechaza).
- Al elegir una canción de Mi música aparece un reproductor `<audio>` y el campo
  **«Empieza en el segundo __»** (entero ≥ 0), con el botón **«Usar donde va el
  reproductor»** que copia `currentTime` (redondeado) al campo.
- Lista **Mi música**: nombre, duración, escuchar, borrar (con confirmación).
- Aviso fijo: «Sube solo música tuya o con licencia: Meta silencia o rechaza
  anuncios con canciones protegidas.»
- El costo del botón «Generar video» suma US$ 0,02 solo con un estilo IA; con
  una canción de Mi música la música cuesta 0.

### En la edición final («Producir finales»)

El selector «Música» también lista Mi música (`mat:<id>`) y hay un campo
«Empieza en el segundo» (sin reproductor: el formulario vive en un `<template>`
clonado).

## Comportamiento

- La canción suena desde `inicio_s` hasta el final del video. Si el tramo
  `[inicio_s, fin]` es más corto que el video, ese mismo tramo se repite (loop).
- Mezcla idéntica a la de hoy (`mezcla.mezclar_musica` en Crear, `render.componer`
  en la final): ambos ya hacen `-stream_loop -1` + `-t`. Lo único nuevo es que la
  pista que reciben es el tramo recortado.
- `inicio_s` fuera de rango (≥ duración) se ajusta a 0 en la ruta; en el worker,
  un material que ya no existe degrada la capa música (`estado: error`), nunca
  tumba la generación pagada.
- Borrar una canción la quita de R2 y de la biblioteca; los videos ya generados
  conservan su audio mezclado.

## Diseño técnico

### Biblioteca (`mi_musica.py`, nuevo, único escritor)

Cada canción es una fila de `material` (tabla del editor, sin migración):
`tipo="audio"`, `origen="subida"` (subida) o `"musica"` (ElevenLabs), R2
`clientes/<cliente>/materiales/<hash><ext>`, `duracion_ms` por ffprobe,
`extra = {"nombre", "fuente": "subida"|"elevenlabs", "prompt"?, "instrumental"?}`.
Dedupe por `UNIQUE(cliente, hash)` (subir el mismo archivo dos veces no duplica).
Cuota: `materiales.CUOTA_BYTES` por cliente.

- `listar(cliente)` → `[{id, nombre, duracion_s, url, fuente}]`, más reciente primero.
- `subir(cliente, archivo)` → valida extensión, tamaño (`materiales.validar_subida`),
  cuota, que tenga pista de audio y ≤ 10 min; lanza `SubidaInvalida` con mensaje
  para la persona.
- `registrar_generada(cliente, local_path, prompt, instrumental, costo_usd)`.
- `borrar(cliente, material_id)` → solo materiales de música de ese cliente.
- `resolver(cliente, valor)` → la fila si `valor == "mat:<id>"` es una canción de
  ese cliente; si no, `None`.
- `es_propia(valor)` → `valor.startswith("mat:")`.

### Pista para mezclar (`final_edition/musica.py`)

`obtener_pista(estilo, segundos, carpeta_cache=None, on_progreso=None, cliente=None, inicio_s=0)`:
con `mat:<id>` descarga el material (caché por hash en `data/musica/propia/`),
recorta desde `inicio_s` a WAV (`ffmpeg -ss <inicio> -i src -vn -ac 2 -ar 48000`,
caché `<hash>_<inicio>.wav`) y devuelve `({"archivo", "url", "estilo": nombre,
"generada": False, "material_id", "inicio_s", "fuente"}, 0)`. Con un estilo IA,
igual que hoy.

### Crear

- `cf_crear_video`: acepta `musica_estilo` si es estilo IA o `mi_musica.resolver`
  lo encuentra; guarda `musica_inicio_s` (entero, 0 si no aplica o fuera de rango).
- `tareas/flowplus.py` paso «Mezclando sonido»: pasa `cliente` e `inicio_s`;
  `capas.musica = {estilo: nombre, material_id?, inicio_s?, fuente, url, costo_usd, estado}`.
- `fp_reusar` precarga `musica_inicio_s`.

### Edición final

- `fe_producir`: acepta `mat:<id>` del cliente; `opciones["musica_inicio_s"]`.
- `final_edition.producir`: pasa `cliente`/`inicio_s` a `obtener_pista`; la capa
  música lleva proveedor `propia` / `elevenlabs` / `fal/stable-audio`.

### Música con ElevenLabs

- `providers/fal_audio.musica_elevenlabs(prompt, segundos=60, instrumental=True)`:
  `fal-ai/elevenlabs/music`, payload `{prompt, music_length_ms, force_instrumental}`,
  respuesta `{"audio": {"url"}}`; costo US$ 0,60 por minuto empezado (verificado
  en fal el 2026-09-25). Siempre 60 s: fal cobra 30 s igual que 60 s.
- Ruta `mm_crear` encola `musica_generar` (`max_intentos=1`, un trabajo a la vez
  por cliente: job_id `<cliente>__musica_generar`). El botón muestra
  `gastos.estimar("musica_elevenlabs")`.
- Tarea `tareas/musica.py::musica_generar`: llama a fal, descarga el mp3,
  `mi_musica.registrar_generada`, `gastos.registrar_seguro(cliente, "musica", usd,
  f"musica_el:t<tarea_id>")`. Si fal cobró y algo falla después, igual registra
  el gasto con detalle.

### Rutas (dashboard, junto a las de FlowPlus)

`mm_subir` (POST, fetch con progreso), `mm_borrar` (POST), `mm_crear` (POST),
`mm_lista` (GET, para refrescar tras la generación). Respuesta JSON
`{ok, html (parcial _mi_musica.html), canciones, error}`; el JS reconstruye el
optgroup «Mi música» de los dos selectores con `canciones`.

## Fuera de alcance

Voz clonada; canción propia como música por defecto del proyecto
(`preferencias_sonido.musica_al_crear` sigue siendo solo estilos IA); Sprints
(sigue con estilos IA); reproductor en la edición final; que el editor liste Mi
música (lo hará la capa correspondiente del editor, la tabla ya es la misma).

## Riesgo

Los términos de Eleven Music prohíben reventa y bibliotecas de música en planes
self-serve; no está claro qué aplica al comprar por fal. Revisión legal
pendiente, igual que la voz clonada. No bloquea construir.

## Pruebas

Rutas (subir, validar, borrar, elegir en Crear y en la final, `inicio_s`),
`mi_musica` (dedupe, cuota, pertenencia), recorte real con ffmpeg (`slow`),
tarea `musica_generar` con fal simulado (material creado + gasto), capa música
en el worker con canción propia (costo 0, `inicio_s`). Verificación en el
navegador y una prueba real de Daniel.
