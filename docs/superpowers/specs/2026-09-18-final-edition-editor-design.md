# Final edition como editor manual (tipo CapCut) — diseño

Fecha: 2026-09-18. Estado: aprobado por secciones en conversación con Daniel;
pendiente de revisión escrita. Nace del mapa
`2026-09-18-final-edition-editor-mapa.md`. **Reemplaza** las secciones S5–S8 del
spec de estudio (`2026-09-16-final-edition-estudio-design.md`) y §3.1, §3.4 y
§3.5 de la Parte 3 del spec de sprints (`2026-09-16-sprints-design.md`): la
línea de tiempo del guion, las plantillas de texto y la final edition de
imágenes pasan a vivir dentro de este editor. S3 (video→audio de respaldo) y S4
(stems) siguen vigentes y se apoyan en el modelo de materiales de aquí.

## 0. Decisiones (Daniel, 2026-09-18)

- La final edition actual (formulario de 5 bloques sin vista previa) no gustó a
  los clientes. Se reemplaza por un **editor manual tipo CapCut**, bien hecho.
- **Quien edita es el cliente**, en **celular y computador**, con una sola
  interfaz de disposición vertical (vista previa arriba, timeline abajo, barra de
  herramientas) que en computador solo gana espacio.
- Material: **lo generado en la herramienta más lo que el cliente suba** (video,
  foto, audio).
- **Imágenes desde el inicio**, en el mismo editor (lienzo sin tiempo; carrusel).
- Se arma el video en el idioma base; **idiomas, países y precios son de lo
  último**, justo antes de producir. Después, ajustes por destino.
- **Una sola entrega** al cliente, con todo, como CapCut. Se construye por capas
  probables por separado, pero no se anuncia hasta que esté completo.
- La IA queda para asistencias puntuales (borrador, subtítulos, variantes de
  hook, traducción, sonido), **no** como forma principal de editar.
- Arquitectura **opción 1**: documento JSON + vista previa en el navegador +
  render final en el servidor con ffmpeg.

Hechos del stack que mandan (verificados 2026-09-18): VPS con 1 núcleo y 1,9 GB
de RAM, sin GPU, ffmpeg 8.0.1 (`xfade`, `subtitles`/`ass`, `drawtext`,
`zoompan`, `chromakey`, `lut3d`, `minterpolate`, `tblend`), Python solo con
Pillow, worker de una tarea a la vez, frontend sin framework ni pruebas de JS,
3 fuentes TTF. Estado del código de final edition: ver el mapa §1.

---

## 1. Arquitectura y documento de edición

Cuatro piezas:

- **Edición** (`edicion`): el proyecto del cliente, un documento JSON con
  autoguardado y versiones. Nace del **borrador automático** (el pipeline actual
  pasa a producir este documento en vez de un mp4), de un clon crudo, o de una
  imagen. Única fuente de verdad.
- **Material** (`material`): cada archivo que entra o se produce: clon de Crear,
  otra pieza del proyecto, foto del catálogo, subida del cliente, voz sintetizada
  por bloque, música, sonido, efecto, grabación, PNG de texto, proxy, tira de
  fotogramas, forma de onda. URL en R2, hash, duración, medidas, costo. **Un
  material se produce una vez y se reutiliza siempre.**
- **Versión** (`edicion_version`): copia congelada del documento en cada
  "Producir" (o a mano). Las finales apuntan a la versión que las produjo.
- **Final**: lo que ya existe (`pieza tipo=final`, mp4 o png en R2 por idioma y
  país); aprobación, publicación, experimentos y entrega no cambian.

### 1.1 El documento

```
esquema: 1
formato: 9:16 | 4:5 | 1:1 | 16:9      fps: 30      idioma_base: es
duracion_ms: derivada de las pistas; 0 = imagen estática
paginas: [ ... ]                       solo imágenes (carrusel); un video tiene 1
pistas: [
  { id, tipo: video | superpuesto | imagen | texto | subtitulos | audio,
    bloqueada, silenciada, oculta,
    clips: [
      { id, inicio_ms, duracion_ms, material_id,
        recorte: { desde_ms, hasta_ms }, velocidad: 1.0,
        transform: { x, y, escala, rotacion, opacidad, ancla },
        keyframes: [ { t_ms, transform } ],           // solo los generados por animaciones
        animacion: { entrada, salida, duracion_ms },
        transicion: { tipo, duracion_ms },            // hacia el clip siguiente
        texto: { literal } | { variable: rol },       // pistas texto
        estilo: { fuente, peso, tamano, color, contorno, sombra, fondo, alineacion, interlineado },
        audio: { volumen, fundido_entrada_ms, fundido_salida_ms, ducking: true },
        mascara: { tipo, parametros } } ] } ]
subtitulos: { estilo_id, posicion, palabras: [ { t_ms, dur_ms, texto } ] }   // por idioma
variables: { textos: { rol: { es, en, pt } }, precios: { "<idioma>_<pais>": numero } }
marca: { color, logo_material_id, marca_de_agua: { posicion, opacidad } }
mezcla: { preset, volumenes: { voz, sonido, musica } }
materiales: [ ids ]                    // para descargar y para no borrar en uso
miniatura_ms: 4200
```

Reglas que hacen que el mismo documento sirva para todo:

- Tiempos en **milisegundos enteros**.
- Posiciones en **fracción del lienzo** (0–1) y tamaños de texto en **fracción
  de la altura**; el documento se renderiza igual en 1080p, en el proxy de 540p y
  al cambiar de formato.
- Un texto es **literal o variable**; la variable se resuelve por idioma al
  producir. La composición no depende del idioma.
- El precio de un país es el número escrito para ese país o no existe; **nunca se
  convierte** entre monedas (regla vigente).
- Máximo 8 pistas. Sin keyframes manuales: `keyframes` solo los escribe una
  animación predefinida (entrada/salida/Ken Burns) y el motor los interpreta.

### 1.2 Módulos

- `final_edition/documento.py`: esquema, validación, migración entre `esquema`,
  resolución de variables por idioma, duración derivada, utilidades puras.
- `final_edition/geometria.py` y `static/editor/geometria.js`: **la misma
  tabla de casos** en ambos (posición, ancla, escala, rotación, keyframes →
  píxeles). Es lo que garantiza que el navegador y ffmpeg lleguen al mismo píxel.

---

## 2. Motor de render (servidor)

> Estado: **capa 1 implementada** (plan
> `docs/superpowers/plans/2026-09-18-editor-capa1-documento-motor.md`). Subtítulos
> por ASS solo donde ffmpeg trae libass (VPS); sin libass se omiten y el render lo
> avisa. Pendiente de la capa 2: el borrador automático produce una `edicion`.
>
> Decisiones de implementación que ajustan la letra de este capítulo:
> - **Transición** (§2.1): una `transicion` de `d` ms en el clip A ocupa el
>   intervalo de SALIDA `[fin_A, fin_A + d)`; B conserva su posición exacta y los
>   cuadros extra salen de la cola de A (`recorte.hasta_ms + d × velocidad`), nunca
>   de un recorte de B.
> - **Keyframes solo x/y**: interpolación lineal por tramos en `t`; escala,
>   opacidad y rotación por keyframe quedan para las animaciones con alfa en PNG.
> - **`anullsrc` en tramos sin audio**: si el documento tiene audio pero la
>   ventana no tiene ningún clip activo, el filtergraph rellena con `anullsrc`
>   para que `concat -c copy` no rompa por streams heterogéneos entre tramos.
> - **Claves de la final, versionadas**: `edicion_producir` sube a
>   `clientes/<c>/finales/<final_id>__v<version_id>.mp4`/`.png` (miniatura
>   primero) en vez de una clave fija, así un reintento nunca pisa el archivo que
>   la fila todavía enlaza.
> - **Migración `0012`** (`0012_editor.py`, encadenada tras `0011_token_cuenta.py`;
>   `0010` y `0011` las tomaron `gasto.py` y cuentas en el ínterin; ver §5).
> - **Caja por defecto 400×200**: una capa sin `ancho_px`/`alto_px` (la capa 3
>   aún no los manda) usa 400×200 px como tamaño de referencia para
>   `geometria.caja`; `preparar_rutas` estampa el tamaño natural del material
>   en los clips `imagen` que no lo traen. Cada capa se escala a su caja
>   (`scale=w:h`) y su `opacidad` se aplica por clip (`colorchannelmixer`).
> - **Sonido nativo de la escena** (§2.1 punto 5): se modela como una pista
>   `audio` con `rol_audio: sonido` sobre el MISMO material que la pista
>   principal; el compilador nunca lee `[0:a]` del clon por su cuenta. Todos
>   los roles distintos de `voz`/`musica` se suman con `amix` en la entrada
>   "sonido" de `mezcla.filtro_mezcla`.
> - **No se renderiza en la capa 1**: `superpuesto` (PIP; `compilar` lo
>   rechaza con un error explícito si trae clips), `rotacion` y
>   `marca.marca_de_agua`. Llegan con la capa 4.
> - **Subtítulos**: `subtitles='<ass>':fontsdir='<static/fonts>'` (las mismas
>   fuentes del repo que usa `tipos.py`); ambas rutas escapadas para el doble
>   parseo de ffmpeg (`compilador._ruta_filtro`).
> - **Contrato de la ruta que encola `edicion_producir`** (capa 3):
>   `ediciones.versionar(motivo="producir")` → `creative_flow.crear_final`
>   (la fila final DEBE existir: la tarea falla con mensaje si
>   `actualizar_final`/`apuntar_final` no la encuentran) →
>   `trabajos.encolar("edicion_producir", ..., max_intentos=1,
>   duracion_estimada=estimar.segundos(doc), etapas=ETAPAS_EDICION)`;
>   `edicion_proxy` va con `max_intentos=3`. Abierto: qué final se crea para
>   una edición sin `cf_id` (hoy `crear_final` exige una sesión de Crear).
> - **Pendiente antes de la capa 3**: una entrada `-ss/-t` por clip de la
>   pista principal (hoy el clon entra una sola vez y cada clip hace `trim`
>   sobre él): con clips reordenados ffmpeg decodifica y retiene todo lo que
>   hay entre recortes — medido 1,39 GB de RSS en un reorden de 10 s. Cambia
>   `Plan.entradas`, así que va en una tarea propia.

`final_edition/motor/` recibe un documento resuelto (variables ya sustituidas)
y devuelve mp4 o png. Reemplaza `render.py`.

### 2.1 Compilación

`compilar(documento, materiales_locales) -> Plan {entradas, filtergraph, salida,
tramos}`. Función pura; la mayoría de las pruebas son documento → filtergraph
esperado.

1. **Pista principal**: por clip `trim` + `setpts` + velocidad (`setpts=PTS/v`,
   `atempo` en audio) + escala/recorte al lienzo + transform; entre clips `xfade`
   con tipo y duración, o corte seco (`concat`).
2. **Capas encima** (superpuestos, imágenes, PNG de texto, formas, marca de
   agua): un `overlay` cada una con `enable` por ventana de tiempo y expresiones
   en `t` para opacidad, posición y escala cuando hay animación.
3. **Textos libres**: llegan como PNG con alfa rasterizados por el navegador en la
   resolución final (material `png_texto`). El servidor no interpreta fuentes
   para ellos.
4. **Subtítulos**: un `.ass` por idioma (estilo, posición, karaoke por palabra)
   → un solo filtro `subtitles`. Sin límite por cantidad de palabras.
5. **Audio**: por clip `atrim` + `volume` + `afade`; mezcla de voz, sonido,
   música y efectos con `mezcla.filtro_mezcla` (ducking, presets, `loudnorm`),
   que ya existe.
6. **Salida**: `libx264 veryfast crf 22`, AAC 48 kHz, como hoy; `png` en
   `miniatura_ms` para imágenes; miniatura del video en `miniatura_ms`.

### 2.2 Memoria y CPU

- Presupuesto de overlays por proceso: `PRESUPUESTO_OVERLAYS = 60` (~8 MB cada
  uno). Si un documento lo supera, el compilador **parte el render por tramos**
  (cada tramo solo con las capas activas en su ventana, nunca más de dos
  transiciones) y concatena sin recodificar (`-c copy` sobre los tramos) al
  final. No hay tope para el cliente; solo tarda más.
- `xfade` decodifica dos clips a la vez: siempre originales, no proxies.
- `estimar(documento) -> segundos` (duración × capas × transiciones, calibrado
  con mediciones en el VPS) se muestra en el botón Producir.
- Recomendación operativa: pasar el VPS a 4 núcleos (Hetzner, cambio de plan sin
  migrar). Con un núcleo un final de 30 s con 3 transiciones y 20 capas ronda
  4–6 min.

### 2.3 Materiales y caché

- `material.hash` es la clave de caché: voz por bloque `hash(texto_voz, voz,
  idioma)`, música `hash(estilo, duracion)`, PNG de texto `hash(estilo, texto,
  tamano_px)`, traducción `hash(texto, idioma_destino)`. Antes de pagar se
  consulta.
- Proxies: al entrar un video, la tarea `edicion_proxy` genera 540p a ~1 Mbps,
  tira de fotogramas (1 por segundo, jpg pequeños en una tira) y cortes por
  escena (`cortes.detectar_cortes`); al entrar un audio, la forma de onda (JSON
  de picos por 50 ms). Hasta que existan, el editor muestra el clip como
  "preparando".
- Subida directa a R2 por URL firmada (no pasa por gunicorn); límites: video 200
  MB y 2 min, imagen 20 MB, audio 20 MB; 2 GB por proyecto.

### 2.4 Tareas

- `edicion_producir` `{cliente, edicion_id, version_id, idioma, pais}`: una por
  destino, `max_intentos=1` (paga solo materiales nuevos). Etapas: materiales →
  voz → música → render → subida.
- `edicion_proxy` `{cliente, material_id}`: `max_intentos=3`, gratis.
- `final_producir` (existente) pasa a: borrador → documento por defecto →
  `edicion_producir`. Derivaciones y experimentos no cambian.
- Periódica `materiales_limpiar` (diaria): borra `png_texto` y proxies sin uso
  hace 30 días; originales, voces y músicas se conservan.

### 2.5 Pruebas

Compilador puro contra filtergraphs esperados (documentos de referencia);
partición por tramos con 200 capas; `slow`: render de un documento con dos clips,
una transición, un PNG de texto, subtítulos ASS y música, verificado con
ffprobe (duración ±0,2 s, tamaño, audio); salida png para imagen; estimación
calibrada.

---

## 3. Vista previa (navegador)

`static/editor/` como módulos ES. Segundo motor: reproduce el mismo documento en
vivo, sin servidor.

- **Reloj maestro**: `requestAnimationFrame` sincronizado a
  `AudioContext.currentTime`. Todo se dibuja en función de `t`.
- **Video**: un `<video>` oculto por material (proxy 540p); en cada cuadro el
  clip activo se posiciona en `recorte.desde + (t − inicio) × velocidad` y se
  dibuja en el lienzo; el siguiente clip se precarga 500 ms antes. Nunca más de
  dos decodificando.
- **Lienzo**: `<canvas>` a la resolución del formato, escalado por CSS; orden de
  dibujo = orden de pistas; transform por capa; textos con `fillText`/
  `strokeText` y fuentes `@font-face`; imágenes con `drawImage`; máscaras con
  `clip`. Con la reproducción parada solo se dibuja el fotograma actual.
- **Transiciones**: fundido y deslizar se dibujan fieles; las demás se muestran
  como fundido con la etiqueta "vista aproximada". Única diferencia aceptada.
- **Audio**: Web Audio, un nodo por clip con `GainNode` (volumen, fundidos) y
  ducking con la misma curva que `mezcla.py`. No replica `loudnorm`.
- **Paridad**: geometría compartida (§1.2); PNG de textos rasterizados por el
  mismo canvas al producir; subtítulos con las mismas fuentes que libass
  (diferencia de 1 px aceptada); antes de producir el navegador manda una
  captura de `miniatura_ms` y el servidor la compara por bloques con su
  fotograma: si difieren por encima del umbral, la final queda en `revisar`.
- **Rendimiento**: objetivo 30 fps con un video, 3 textos y música en un teléfono
  de gama media; si no llega, baja a 24 fps y lo indica. Imágenes reducidas al
  formato al cargar. Timeline en su propio canvas.
- **Pruebas**: vitest (geometría, keyframes, orden de capas, clip activo en `t`,
  reloj con tiempo simulado); Playwright con un documento de referencia y
  capturas en tres instantes comparadas contra imágenes de referencia.

---

## 4. Interfaz

Una sola disposición vertical (CapCut móvil); en computador el timeline es más
alto y el panel de propiedades va a la derecha. Sin hover, sin clic derecho.

```
barra superior: ← Volver · nombre · Deshacer Rehacer · [Producir]
vista previa: lienzo con asas de selección, guías de zona segura al arrastrar
transporte: ⏮ ▶ ⏭ · tiempo actual / total
timeline (canvas): tira de fotogramas del video, pistas debajo, formas de onda;
                   pinza = zoom, dos dedos = desplazar; imán a cortes, clips y cabezal
barra de herramientas: Cortar · Texto · Subtítulos · Audio · Medios · Efectos · Formato · Marca
panel contextual: propiedades de lo seleccionado (abajo en celular, derecha en computador)
```

- **Timeline**: la pista principal siempre existe; las demás se crean al soltar
  algo. Arrastrar mueve, bordes recortan. Clip seleccionado: Cortar aquí,
  Borrar (ripple en la principal), Duplicar, Velocidad (0,5–2×), Silenciar,
  Reemplazar. Marcadores tenues de cortes por escena y compases.
- **Vista previa**: tocar selecciona; asas de escalar y rotar; imán a centro y
  bordes; doble toque edita texto en sitio; fondo desenfocado automático cuando el
  video no llena el marco.
- **Texto**: contenido, fuente (set curado OFL de ~20 con muestra), tamaño,
  color (paleta de marca + libre), contorno, sombra, fondo (píldora, caja),
  alineación, interlineado, animación de entrada/salida (con vista previa
  animada), duración; "Convertir en variable" (rol hook, cta, precio,
  descripcion, badge).
- **Subtítulos**: generar (Whisper sobre voz o audio), estilos visuales
  (karaoke, caja, palabra grande, minimal), posición, lista de palabras con
  tiempos para corregir, apagar por tramo.
- **Audio**: voz (selector con reproducir muestra, texto por bloque, regenerar
  bloque con costo), música (estilo con reproducir 15 s, o subida propia,
  recorte y punto de inicio), sonido de la escena (on/off, volumen, "generar"
  si mudo), grabar con micrófono, efectos cortos. Por clip: volumen, fundidos,
  silenciar. Preset de mezcla y tres deslizadores.
- **Medios**: pestañas Este video (clon crudo/mezclado), Proyecto (piezas de
  Crear y sprints), Catálogo, Marca (logo, personajes), Subidos, y Subir.
  Tocar agrega al final; arrastrar coloca; un video sobre otro es PIP.
- **Efectos**: transiciones (tocar la unión: corte, fundido, deslizar, zoom,
  desenfoque), filtros de color (presets + LUT de marca), movimiento (Ken Burns,
  sacudida en golpes), máscara del video (círculo, zoom a región).
- **Formato**: cambio con reencuadre cover, paneo manual del video, capas por
  fracción.
- **Marca**: color, logo como marca de agua con posición, tarjeta final.
- **Producir** (última pantalla): destinos por idioma y país, precio por país,
  "Traducir textos y voz" por idioma nuevo con costo, vista previa por idioma con
  variables resueltas, costo total y tiempo estimado. Después: "Ajustar este
  destino" abre una copia del documento resuelto para ese idioma/país.
- **Imágenes**: mismo editor sin transporte ni timeline; carrusel = páginas con
  flechas.
- **Atajos** en computador: espacio, S (cortar), Supr, Cmd/Ctrl+Z/Shift+Z,
  flechas por fotograma, +/− zoom del timeline.
- **Fuera**: keyframes manuales, chroma key, curvas de color, pistas anidadas,
  más de 8 pistas.

Tecnología: Preact + htm **vendorizados** en `static/vendor/` (sin CDN) para los
paneles; dos `<canvas>` con módulos propios; eventos de puntero (dedo y mouse
iguales); estado central inmutable con historial para deshacer.

---

## 5. Modelo de datos y persistencia

Migración nueva encadenada a la última existente al implementar (hoy `0009`).

> Nota: la migración del editor es la `0012` (`migrations/versions/0012_editor.py`, tras `0011_token_cuenta.py`); `0010` y `0011` las tomaron `gasto.py` y cuentas en el ínterin.

- **`edicion`**: `id`, `cliente`, `cf_id` (nullable), `tipo` (`video|imagen`),
  `nombre`, `documento` JSON, `version_n` int, `estado` (`borrador|producida`),
  `creada_en`, `actualizada_en`, `creada_por`.
- **`edicion_version`**: `id`, `edicion_id` FK, `n`, `documento` JSON, `motivo`
  (`producir|manual`), `creada_en`. Índice (`edicion_id`, `n`).
- **`material`**: `id`, `cliente`, `tipo` (`video|imagen|audio|png_texto|proxy|
  tira|forma_onda`), `origen` (`crear|subida|catalogo|marca|voz|musica|sonido|
  efecto|grabacion|texto|traduccion`), `url`, `url_proxy`, `hash`,
  `duracion_ms`, `ancho`, `alto`, `bytes`, `costo_usd`, `padre_id`, `extra`
  JSON, `creado_en`, `usado_en`. Índice único (`cliente`, `hash`).
- **`pieza`**: columna `edicion_version_id` (nullable). `concepto.guion_base` se
  conserva para las derivaciones.

Flujo de guardado: `PUT /cliente/<c>/ediciones/<id>` con documento y
`version_n`; el servidor acepta solo si coincide (CAS como en `pieza_qa`) y
devuelve el nuevo `version_n`; conflicto → 409 y el editor ofrece recargar.
Deshacer/rehacer solo en memoria. Producir: `POST .../producir` → versión →
PNG de textos como `material` → `pieza tipo=final` por destino (como hoy) →
`edicion_producir` por destino.

Borrador: `final_edition.borrador(cliente, cf_id) -> edicion_id` (guion con
Claude, cortes, voz por bloque cacheada, música, textos hook/badge/CTA en las
posiciones actuales, subtítulos, variables prellenadas). "Preparar guion" pasa a
ser "Crear borrador"; el modal de Crear muestra "Editar final" que abre el editor
a pantalla completa. `render.py` y `texto.py` quedan como base del compilador y
del borrador y se retiran al final.

Rutas: `editor(cliente, edicion_id)` (GET, pantalla completa), `ediciones`
(POST crear desde clon/imagen/vacía), `edicion_guardar` (PUT CAS),
`edicion_producir` (POST), `edicion_versiones` (GET/POST restaurar),
`materiales_subir` (POST → URL firmada + registro), `materiales_listar` (GET
por pestaña), `material_borrar` (POST, solo sin uso), `edicion_variantes_hook`
(POST, Claude), `edicion_subtitular` (POST, Whisper), `edicion_traducir` (POST).

Pruebas: CAS (dos escrituras con el mismo `version_n`, una pierde); `material`
deduplicado por hash; borrador → documento válido; migración sube y baja; final
apunta a versión; subida rechaza tipos y tamaños fuera de límite; borrar
material en uso falla.

---

## 6. IA, costos y producción

IA solo como asistencia al que edita a mano: borrador automático; subtítulos
automáticos (Whisper sobre voz sintetizada, subida o grabación); "otras 3
opciones" de hook sobre un texto con rol hook (`guion.variar_guion`);
traducción al final (textos por variable y voz por bloque, criterio de
`localizar_guion`); sugerir/generar sonido (S1/S3); revisión local antes de
producir (texto fuera del marco o zona no segura, precio ausente para un país
marcado, capa más corta que su animación, volúmenes que saturan) como avisos,
sin bloquear. Órdenes de magnitud con precios de 2026-09: traducir un video de
20 s a un idioma ≈ USD 0,01 + voz; 3 variantes de hook < USD 0,01; Whisper ≈
USD 0,01/min.

Costos, regla de la casa: todo lo que paga muestra su costo **en el botón** con
las mismas funciones de estimación de Crear y final edition; nada se paga dos
veces (caché por hash); editar, previsualizar, deshacer y renderizar son
gratis y la pantalla lo dice; Producir muestra suma por destino, total y
tiempo estimado.

Producción: Producir → destinos, precios, traducciones pendientes, costo y
tiempo → confirmar → PNG por idioma subidos → versión → una tarea por destino
→ barra de progreso por etapas (`iniciarPolling`) → final como hoy (aprobar,
publicar, experimento, entrega) → "Ajustar este destino".

Se conserva sin tocar: `mezcla.py`, `voz.py` (+ caché por bloque), `musica.py`,
`guion.py`, `cortes.py` (detección), `tipos.py`, `providers/fal_audio.py`, la
cola, `iniciarPolling`, aprobación y publicación de finales, derivaciones y
experimentos. Desaparece: el formulario de final edition del modal de Crear.

---

## 7. Orden de construcción, riesgos y alcance

Una sola entrega al cliente; siete capas, cada una con su plan de
implementación y ejecución por subagentes con revisión:

1. **Documento y motor**: esquema, tablas y migración, compilador, tramos,
   ASS, `material` con caché, proxies, tareas. Probado con documentos a mano.
2. **Borrador como documento**: el pipeline actual produce una `edicion`;
   derivaciones y experimentos producen por esa vía. **Desplegable sin que el
   cliente lo note**: es el seguro de no romper lo que funciona.
3. **Vista previa**: reloj, lienzo, video por proxy, audio, geometría
   compartida, paridad.
4. **Editor**: timeline, selección y asas, texto, subtítulos, audio, medios y
   subidas, efectos, formato, marca, deshacer, autoguardado, atajos.
5. **Producir e idiomas**: pantalla final, traducciones, PNG por idioma, ajuste
   por destino, revisión previa.
6. **Imágenes y carrusel**.
7. **Pulido en dispositivos reales** (iPhone, Android gama media, Safari y
   Chrome de escritorio), rendimiento medido, prueba con 2–3 clientes reales
   antes de anunciar.

Riesgos: paridad vista previa/render (PNG del mismo navegador, geometría
compartida y probada, mismas fuentes, comparación de fotograma antes de
publicar); rendimiento en teléfono (proxies, dos videos como máximo, redibujo
solo al cambiar); un núcleo en el VPS (recomendar 4 núcleos desde la capa 1;
prioridad de cola y tiempo visible mientras tanto); memoria de ffmpeg (tramos,
prueba de 200 capas); Safari/iOS (`<video>` en canvas y Web Audio se prueban en
la capa 3); fuentes (mismo TTF en ambos lados, set OFL versionado, prueba de
medida); subidas grandes (URL firmada, límites); frontend sin pruebas (vitest
desde el primer módulo, lógica fuera de los componentes).

Fuera de esta versión: keyframes manuales, chroma key, curvas de color, pistas
anidadas o más de 8, multicámara, tracking, clonación de voz, música con letra,
cámara lenta interpolada, colaboración simultánea, exportar a otros editores,
"pídele al editor" en lenguaje natural.
