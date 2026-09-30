# Audios en Crear: locución con la voz que elijas sobre tu música (2026-09-28)

Pedido de Daniel: un cuarto modo en Crear, después de Flow Plus, para crear
audios «como en MoneyPrinterTurbo»: subir una música, escribir un texto y que
una voz elegida por la persona lo lea encima. El resultado es un mp3 para
escuchar, descargar y usar donde quiera. La voz clonada sigue aparcada (fal no
clona ElevenLabs y la cuenta directa tiene dudas de licencia, spec de Mi música).

## 1. Qué ve la persona

Crear tiene hoy tres modos (`_tab_flowplus.html`): Desde referencias, Cambiar
producto, Flow Plus. Se agrega **Audios** (`data-modo="audios"`; el hash
`#audios` abre Crear con ese modo, igual que `#flowplus`). El panel es
`_crear_audios.html`, en dos columnas desde 900 px (formulario | Tus audios) y
una sola por debajo.

### Formulario (todo con clases de la base visual común)

1. **Texto a leer**: `textarea`, hasta 3 000 caracteres, con contador
   «N / 3 000» y el precio en vivo debajo.
2. **Voz**: `select` con las 22 voces de `fal_audio.VOCES` (las verificadas en
   fal) y al lado el botón **Escuchar**: reproduce una muestra corta de esa voz
   en el idioma elegido (ver §3). Mientras llega, el botón dice «Cargando…».
3. **Idioma**: Español · English · Português (las tres claves de `VOCES`);
   por defecto el del proyecto (`idiomas.de_proyecto`) si está entre los tres,
   si no `es`.
4. **Velocidad**: Lenta (0,85) · Normal (1,0) · Rápida (1,15). Es el `speed`
   nativo del modelo (fal acepta 0,7–1,2).
5. **Música de fondo**: `select` con «Ninguna» y las canciones de Mi música
   (`mat:<id>`, las mismas de Crear). Al lado, **Subir canción** (mismo
   `mm_subir`, mismas validaciones: mp3/wav/m4a/aac/ogg, ≤ 20 MB, ≤ 10 min) y
   un enlace «¿Una canción hecha con IA? Créala en Desde referencias › 🎵
   Música» (abre ese modo). Con una canción elegida aparecen el reproductor,
   **«Empieza en el segundo __»** con «Usar donde va el reproductor» (como en
   Crear) y **Volumen de la música**: Baja (0,20) · Media (0,35, por defecto) ·
   Alta (0,50).
6. Botón **«Crear audio ≈ US$ X»** (`.btn-generar`). X = caracteres × tarifa
   (`gastos.estimar("locucion", caracteres=n)`); la música propia cuesta 0.
   Con el texto vacío el botón queda deshabilitado. Enter en un campo de una
   línea no envía.

Al pulsar, el formulario se bloquea, sale la barra de progreso (Sintetizando
la voz → Mezclando con la música → Guardando) y al terminar el audio aparece
arriba de **Tus audios** sin recargar la página (el texto escrito para el
siguiente no se pierde). Un audio a la vez por proyecto: un segundo clic
mientras corre responde «Ya se está creando un audio — espera a que termine».

### Tus audios

Lista (más reciente primero) con: nombre (las primeras palabras del texto),
voz · idioma · duración · nombre de la canción (o «solo voz»), reproductor
`<audio controls preload="none">`, **Descargar** (mp3 con nombre legible) y
**Borrar** (con confirmación). Vacía: `.estado-vacio` «Todavía no tienes
audios. Escribe un texto, elige la voz y créalo.»

## 2. Cómo suena

- Voz: ElevenLabs `multilingual-v2` vía fal (`fal_audio.tts`), la misma de las
  finales. `speed` solo se manda cuando no es 1,0. NO se manda
  `language_code`: ElevenLabs solo lo acepta en Turbo/Flash v2.5 y en
  multilingual-v2 devuelve error; el modelo detecta el idioma solo. El
  `idioma` elegido sirve para la muestra de la voz y queda guardado.
- Con música: la música (el tramo desde `inicio_s`, en bucle si es corta)
  empieza 0,6 s antes que la voz, se agacha mientras habla
  (`mezcla.DUCKING_VOZ_SOBRE_MUSICA`, ratio 8), sigue 1,5 s después de que la
  voz termina y se desvanece en ese 1,5 s. Duración total = 0,6 + voz + 1,5.
- Sin música: solo la voz, normalizada. Duración = la de la voz.
- `loudnorm=I=-14:TP=-1.5:LRA=11` (el de siempre) y el fundido DESPUÉS del
  `loudnorm` (si no, la normalización de una pasada levanta la cola).
- Salida: mp3 (`libmp3lame`, 192 kbps, 44,1 kHz, estéreo). Antes de desplegar
  se comprueba que el ffmpeg del VPS trae `libmp3lame`.

Filtergraph con música (voz `[0:a]`, música `[1:a]` con `-stream_loop -1`,
`-t <total>` cierra):

```
[0:a]<NORM>,adelay=600|600,apad,asplit=2[voz_mix][voz_sc];
[1:a]<NORM>,volume=<v>[mus];
[mus][voz_sc]sidechaincompress=<DUCKING>[mus_d];
[voz_mix][mus_d]amix=inputs=2:duration=first:normalize=0,<LOUDNORM>,afade=t=out:st=<total-1.5>:d=1.5[aout]
```

Sin música: `[0:a]<NORM>,<LOUDNORM>[aout]`. `NORM`, `LOUDNORM` y `DUCKING`
son las constantes de `final_edition/mezcla.py`.

## 3. Muestras de voz

`audios.muestra(voz, idioma)`: una frase corta por idioma que dice el nombre
de la voz («Hola, soy Rachel. Así suena mi voz en tu anuncio.» / «Hi, I'm
Rachel. This is how my voice sounds in your ad.» / «Olá, eu sou Rachel. É
assim que a minha voz soa no seu anúncio.»; sin artículos de género, las
voces son de ambos). Se sintetiza una sola vez para
toda la plataforma: fila `material` del cliente interno `_creatv` (tipo
`audio`, origen `voz`, hash `hash_clave("muestra_voz", voz, idioma,
VERSION_MUESTRA)`, R2 `clientes/_creatv/materiales/muestra_<voz>_<idioma>.mp3`)
y gasto de `_creatv` (tipo `locucion`, referencia `muestra_voz:<voz>:<idioma>`,
≈ US$ 0,005). La ruta la produce en línea (fal tarda 2–4 s) y devuelve la URL;
dos personas pidiendo la misma voz a la vez pueden producirla dos veces (la
segunda pierde el INSERT y relee), aceptado. `voz` e `idioma` se validan
contra `VOCES`/`IDIOMAS` antes de tocar fal.

## 4. Diseño técnico

### `audios.py` (raíz, nuevo, único escritor de los audios)

Constantes: `ORIGEN = "locucion"`, `IDIOMAS = ("es", "en", "pt")`,
`VELOCIDADES = {"lenta": 0.85, "normal": 1.0, "rapida": 1.15}`,
`VOLUMENES = {"baja": 0.2, "media": 0.35, "alta": 0.5}`, `MAX_CARACTERES =
3000`, `INTRO_MS = 600`, `COLA_MS = 1500`, `FUNDIDO_MS = 1500`,
`NOMBRES_VELOCIDAD`/`NOMBRES_VOLUMEN` con `idiomas.N_`.

- `validar(cliente, form) -> dict | EntradaInvalida`: `texto` (espacios
  colapsados, 1–3 000 caracteres), `voz` ∈ `fal_audio.VOCES["es"]`, `idioma` ∈
  `IDIOMAS`, `velocidad` ∈ `VELOCIDADES` (clave), `musica` = `mi_musica.resolver`
  del `mat:<id>` (vacío → `None`; un `mat:` que no es del cliente → error
  «Esa canción ya no está en Mi música»), `inicio_s` =
  `mi_musica.inicio_valido`, `volumen` ∈ `VOLUMENES` (clave). Devuelve
  `{"texto", "voz", "idioma", "velocidad", "musica_id", "inicio_s", "volumen"}`
  (el payload de la tarea).
- `nombre_de(texto)`: primeras 60 letras, «…» si se cortó.
- `hash_voz(texto, voz, idioma, velocidad)` = `materiales.hash_clave("locucion_voz", texto, voz, idioma, velocidad)`;
  `hash_audio(hash_voz, musica_id, inicio_s, volumen)` = `hash_clave("locucion", …)`.
  Mismo texto + voz + velocidad → la voz cruda no se paga dos veces; misma
  combinación completa → el audio no se vuelve a hacer.
- `filtro_locucion(con_musica, volumen, total_s) -> str`: el filtergraph de §2,
  puro.
- `duracion_total_ms(voz_ms, con_musica)`.
- `mezclar(voz_path, musica_path, salida_mp3, voz_ms, volumen) -> {"archivo",
  "duracion_ms"}`: corre `cortes.ffmpeg` (`-i voz`, `-stream_loop -1 -i
  musica` si hay, `-filter_complex`, `-map [aout]`, `-c:a libmp3lame -b:a 192k
  -ar 44100 -ac 2`, `-t total`).
- `listar(cliente)` → `[{id, nombre, duracion_s, url, voz, idioma, velocidad,
  musica, creado_en}]` (filas `material` tipo `audio` origen `locucion`, más
  reciente primero). `obtener(cliente, id)` (solo si es un audio de ese
  cliente). `borrar(cliente, id)` → `materiales.borrar` (propaga
  `MaterialEnUso`).
- `muestra(voz, idioma)` (§3) y `FRASES_MUESTRA`.

Cada audio es una fila `material`: `tipo="audio"`, `origen="locucion"`,
`url` en R2 `clientes/<c>/materiales/locucion_<hash12>.mp3`, `duracion_ms`,
`costo_usd` = lo pagado por la voz en ESTE audio (0 si la voz venía cacheada),
`padre_id` = la fila de la voz cruda, `extra = {"nombre", "texto", "voz",
"idioma", "velocidad", "volumen", "musica": {"material_id", "nombre",
"inicio_s", "estado": "ok" | "ausente"} | None}`. La voz cruda es otra fila
(`origen="voz"`, `extra={"texto", "voz", "idioma", "velocidad", "local"}`)
igual que las voces de las finales (`insumos.voz_bloque`), pero con su propio
hash (`locucion_voz`, que incluye la velocidad).

### Tarea `audio_generar` (`tareas/audios.py`)

`job_id(cliente) = f"{cliente}__audio_generar"`; etapas
`(("Sintetizando la voz", 55), ("Mezclando con la música", 30), ("Guardando", 15))`;
`max_intentos=1`; `duracion_estimada=60`. Payload: la salida de `validar`.

1. Si `materiales.buscar_hash(cliente, hash_audio)` existe → «Ya tenías este
   audio» (`marcar_uso`), sin llamar a nadie.
2. Voz: `materiales.obtener_o_crear(cliente, hash_voz, _tts)`; `_tts` llama a
   `fal_audio.tts(texto, voz, velocidad=)`, baja el mp3 a `salidas/audios/<hash>/`
   y lo sube a R2. **Si fal cobró, el gasto se registra ahí mismo**, antes de
   mezclar: `gastos.registrar_seguro(cliente, "locucion", usd,
   f"locucion:{hash_voz[:12]}:t{tarea_id}", detalle="ElevenLabs · N caracteres
   · <voz>", proveedor="fal/elevenlabs")`. Voz cacheada → sin gasto.
3. Música: `final_edition.musica.pista_propia(cliente, f"mat:{id}", inicio_s)`
   (tramo WAV cacheado, costo 0). Si la canción ya no existe, el audio sale
   solo con la voz y `extra.musica.estado = "ausente"`; el mensaje final lo
   dice. Nunca tumba un audio con la voz ya pagada.
4. `audios.mezclar(...)` → mp3.
5. `materiales.obtener_o_crear(cliente, hash_audio, producir)` con la subida a
   R2 y los campos de arriba. Se borra la carpeta de trabajo al terminar bien
   (queda si falla).
6. Devuelve «Audio listo: <nombre>».

Cualquier excepción después de pagar deja el gasto registrado (paso 2) y la
tarea en `error` con el mensaje limpio (`cola.sin_token`/`recortar` como las
demás). `AL_INTERRUMPIR` no hace falta: no hay fila de dominio que quede
«generando».

### Precio (`gastos.py`, `providers/fal_audio.py`)

- `fal_audio.COSTO_USD_POR_CARACTER` pasa de 0,0003 a **0,0001** (fal cobra
  «$0.1 per 1000 characters» para `elevenlabs/tts/multilingual-v2`, verificado
  el 2026-09-28; la constante estaba 3× alta, anotado desde 2026-09-25). El
  costo real de cada llamada sigue saliendo de esa constante, así que las
  finales también registran el precio correcto desde ahora.
- `fal_audio.tts(texto, voz, idioma, on_progreso, velocidad=None)`: `speed` en
  el payload solo si `velocidad` no es `None` ni 1,0.
- `gastos.TIPOS` + `"locucion"`; `NOMBRES_TIPO_GASTO["locucion"] =
  N_("Locuciones (audios)")`; `_ESTIMADORES["locucion"] = caracteres ×
  COSTO_USD_POR_CARACTER` con detalle «N caracteres con ElevenLabs»;
  `TARIFAS["voz"]` se queda como está (es otra cosa: la voz de una final).

### Rutas (`dashboard.py`, junto a las `mm_*`)

Todas responden JSON; el guard por cliente ya cubre `<cliente>`; los POST
exigen `_mismo_origen()` (403 si no).

- `GET  /cliente/<c>/audios/lista` → `_respuesta_audios(cliente)`:
  `{ok, html (fragmento _audios_lista.html), audios, trabajo: {job_id, estado_url} | null, error, mensaje, job_id}`.
- `POST /cliente/<c>/audios/crear` → `audios.validar` (400 con el mensaje) →
  `trabajos.encolar(job_id, "audio_generar", payload, duracion_estimada=60,
  etapas, cliente, max_intentos=1)`; si ya hay uno vivo, 400 «Ya se está
  creando un audio — espera a que termine». Devuelve `job_id`.
- `POST /cliente/<c>/audios/<int:aid>/borrar` → `audios.borrar`; `MaterialEnUso`
  → 400 con su mensaje.
- `POST /cliente/<c>/audios/muestra` (`voz`, `idioma`) → `{ok, url}`; fal roto →
  502 `{ok: false, error}` (sin tokens ni trazas: `type(e).__name__`).
- `GET  /cliente/<c>/audios/<int:aid>/descargar` → baja el mp3 de R2 y lo
  entrega con `Content-Disposition: attachment; filename="<nombre>.mp3"`
  (el atributo `download` no funciona con otro origen y R2 no tiene CORS). 404
  si no es un audio de ese cliente.

Contexto de `ver_cliente`: `**_contexto_audios(cliente)` = `{"audios":
listar, "trabajo_audio": {...} | None, "voces_audio", "idiomas_audio",
"velocidades_audio", "volumenes_audio", "idioma_audio_defecto",
"usd_por_caracter"}`. Una consulta más por página (la lista), ninguna por
tarjeta (`test_perf_pagina_proyecto` sigue en pie).

### Plantillas y JS

- `_tab_flowplus.html`: la pastilla «Audios» después de Flow Plus, el panel
  `#crear-modo-audios` con `_crear_audios.html`, `paneles.audios` y el hash
  `audios` en el arranque. Comentario de cabecera actualizado (cuatro modos).
- `cliente.html`: `resolver('audios')` guarda `crear-modo` = `audios` y abre
  Crear (como `flowplus`).
- `_crear_audios.html`: formulario + `<div id="au-lista">{% include
  "_audios_lista.html" %}</div>` + `<script>` propio (prefijo `au-`). El JS:
  contador y precio en vivo; Escuchar (POST muestra → `<audio id="au-muestra">`);
  música: reproductor + «Usar donde va el reproductor» + subir (XHR a
  `mm_subir`, con progreso) y repintar su `select` con `canciones`; crear
  (fetch → pinta `html` en `#au-lista`, arranca `vigilarAudio`); borrar
  (confirm → fetch → repinta). `vigilarAudio` consulta `estado_trabajo` cada
  4 s (como `vigilarCancion`) y al terminar pide `au_lista` y repinta; NO usa
  `data-poll-job`/`iniciarPolling` porque esos recargan la página al terminar.
  La barra lleva `id="trabajo-<job_id>"` y `data-job`, no `data-poll-job`.
  Todo lo que viene del servidor entra como fragmento ya escapado por Jinja
  (innerHTML); lo que escribe la persona nunca se pinta con innerHTML.
- Mi música en dos sitios: `_tab_creativeflowplus.html` emite
  `mi-musica:cambio` (`detail.canciones`, `detail.origen="mm"`) cuando su panel
  cambia, y escucha el mismo evento (origen ≠ `mm`) para repintar su optgroup;
  `_crear_audios.html` hace lo simétrico con origen `audios`. Así subir una
  canción en cualquiera de los dos deja las dos listas al día sin recargar.
- `_audios_lista.html`: la lista de §1 (`.au-item`), estado vacío.
- CSS: bloque «Crear › Audios (_crear_audios.html)» al final de `style.css`,
  prefijo `au-`; `.au-layout` en dos columnas ≥ 900 px; los `<audio>` al 100 %
  del ancho; nada pide más ancho que su caja (`test_movil`).
- Todo texto visible pasa por el catálogo (`_()`, `N_` + `|traducir`);
  `catalogo_i18n.py actualizar` → traducir → `compilar`.

### CLAUDE.md

Párrafo **Audios en Crear** después de «Mi música»: qué es, `audios.py` único
escritor, la tarea, las rutas, la regla del precio del TTS y lo que queda
fuera.

## 5. Fuera de alcance

Voz clonada; efectos de sonido; subtítulos o transcripción del audio; meter el
audio dentro de un video o en el editor (la tabla es la misma, lo hará la capa
que toque); ElevenLabs v3 con etiquetas (`[whispering]`); varios audios a la
vez por proyecto; editar el nombre del audio; música creada con IA desde este
modo (se crea en Desde referencias › Música y aparece aquí).

## 6. Pruebas

- `tests/test_audios.py`: `validar` (texto vacío/largo, voz, idioma, velocidad,
  volumen, `mat:` de otro cliente, `inicio_s` fuera de rango → 0),
  `nombre_de`, `hash_voz` (cambia con la velocidad), `filtro_locucion`
  (con/sin música: `adelay`, `sidechaincompress`, `afade` después de
  `loudnorm`, sin `amix` sin música), `duracion_total_ms`, `listar`/`obtener`/
  `borrar` (pertenencia, orden), `muestra` (cacheada no llama a fal; nueva
  llama una vez, sube y registra el gasto de `_creatv`).
- `tests/test_tarea_audio.py` (fal y ffmpeg simulados): crea la voz y el audio
  con sus `extra`, registra el gasto (`locucion`, `locucion:<hash>:t<id>`,
  `fal/elevenlabs`); voz cacheada → sin llamada ni gasto; falla al mezclar
  después de pagar → el gasto queda; canción borrada → solo voz y
  `musica.estado == "ausente"`; audio ya existente → no llama a nadie;
  `audio_generar` en `tareas.REGISTRO`.
- `tests/test_rutas_audios.py`: la página trae la pastilla y el panel; `crear`
  encola una sola tarea con `max_intentos=1` y el payload validado; segundo
  clic con trabajo vivo → 400; validaciones → 400 sin encolar; `lista`;
  `borrar`; `muestra` (cacheada → sin fal); `descargar` (cabecera
  `attachment`, 404 ajeno); POST de otro sitio → 403.
- `tests/test_audios_mezcla_real.py` (`slow`): voz de 2 s y música de 5 s
  sintetizadas con `lavfi`; con música el mp3 dura ≈ 4,1 s (0,6 + 2 + 1,5) y es
  estéreo a 44,1 kHz; sin música ≈ 2 s.
- `tests/test_fal_audio.py`: `speed` solo cuando aplica; el costo con la
  constante nueva. `test_i18n_catalogo` y `test_perf_pagina_proyecto` siguen
  verdes.
- Verificación en el navegador (pastilla, precio en vivo, Escuchar, subir,
  crear, lista, descargar, celular a 375 px) y una prueba real con una locución
  corta (centavos) antes del merge.
