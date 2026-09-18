# Final edition como editor (tipo CapCut) — mapa de posibilidades

Fecha: 2026-09-18. Estado: **mapa para decidir**, no es un spec. Cuando
elijamos qué entra, el diseño se escribe aparte y reemplaza las secciones S5–S8
del spec de estudio (`2026-09-16-final-edition-estudio-design.md`) y §3.1/§3.4
del spec de sprints (`2026-09-16-sprints-design.md`), para que no queden tres
diseños compitiendo por la misma pantalla.

Cómo leerlo: cada capacidad lleva una etiqueta. **[hoy]** ya existe en el
código; **[spec S#]** o **[spec §#]** ya está aprobado en uno de los dos specs
pero no construido; **[nuevo]** no está en ninguna parte. **[paga]** marca lo
que gasta dinero en un proveedor; todo lo demás es gratis una vez que el
material existe.

---

## 1. Punto de partida (hechos del código, 2026-09-18)

- Final edition es un **pipeline de una pasada**: clon de Crear → Claude escribe
  un guion fijo de 5 bloques (`hook, problema, producto, prueba, cta`) → cortes
  por detección de escena → voz ElevenLabs por bloque + Whisper por palabra →
  música Stable Audio → overlays PNG con Pillow → un filtergraph de ffmpeg →
  mp4. ~150 s por final, `max_intentos=1` porque cada corrida vuelve a pagar
  voz y música.
- La pantalla de edición en Crear (`_tab_creativeflowplus.html:234-351`) es un
  formulario: precio, idioma, texto en pantalla y texto de voz por bloque (los
  tiempos no se pueden tocar), destinos con precio por país, voz, estilo de
  música, tres checks y un preset de mezcla. **No hay vista previa de nada**:
  lo primero que se ve es el mp4 terminado.
- Texto: 4 arquetipos fijos (hook, subtítulos karaoke, badge de precio, tarjeta
  CTA) en posiciones escritas a mano en `texto.py`, 3 fuentes, blanco + un
  color de acento que nada escribe (siempre `#7c3aed`). Sin animación: el único
  movimiento es el Ken Burns de `zoompan` (máx. 1,08).
- Tope duro: **80 overlays** por render (`render.py:52`), ~8 MB de RAM cada uno
  en ffmpeg; los subtítulos se autolimitan a 60.
- Sin timeline, sin recorte, sin split, sin reordenar, sin capas libres, sin
  imágenes encima, sin control de tipografía/color/posición, sin stems (voz y
  música se pierden al terminar), sin edición de imágenes (bloqueada en la ruta),
  sin estado de edición persistido (no hay columna `opciones`).
- Ya construido del spec de estudio: S1 (sonido nativo al crear, música al
  crear, mezcla) y S2 (capa sonido en el render). S3–S8 y toda la Parte 3 de
  sprints son solo papel.
- Servidor: **1 núcleo, 1,9 GB de RAM**, sin GPU, ffmpeg 8.0.1 con `xfade`,
  `drawtext`, `ass/subtitles`, `zoompan`, `chromakey`, `lut3d`, `minterpolate`,
  `tblend`, `libplacebo`; Python solo con Pillow (sin numpy). Worker de una tarea
  a la vez.
- Frontend: HTML de servidor, JS inline, sin framework, sin bundler, sin ningún
  `<canvas>` en el repo.

## 2. La idea central: el "proyecto de edición"

Un editor tipo CapCut no es un formulario más largo: es **un documento**. Todo
lo que sigue se apoya en una sola pieza de arquitectura:

- **Proyecto de edición**: JSON versionado con formato, duración, pistas, clips,
  capas, keyframes y variables (textos por idioma, precio por país). Es la
  única fuente de verdad.
- **Materiales**: lo que cuesta dinero o tiempo y se produce una vez (clon,
  voz por bloque, música, sonido de escena, efectos, imágenes generadas,
  subidas del usuario). Viven en R2 con caché por hash; editar nunca vuelve a
  pagar un material que ya existe.
- **Vista previa**: el navegador reproduce el proyecto (video + canvas + Web
  Audio) sin tocar el servidor.
- **Render**: el servidor convierte el mismo proyecto en mp4/png con ffmpeg.
  Gratis, ilimitado, encolado.
- **Borrador automático**: el pipeline actual (guion de 5 bloques, cortes,
  voz, música, textos) deja de ser "el" final y pasa a ser el generador del
  primer proyecto, que se abre en el editor listo para tocar. Nadie arranca de
  un lienzo en blanco a menos que quiera.

Todo lo de abajo son capacidades de ese documento y de sus dos motores
(navegador y ffmpeg).

## 3. Mapa por áreas

### A. Lienzo (vista previa)

- Reproducción en tiempo real en el navegador: play/pausa, barra, ir a
  fotograma, bucle sobre la selección, velocidad de repro. **[nuevo]** (el spec
  de estudio lo dejó fuera explícitamente; con un editor deja de ser opcional)
- Formatos 9:16, 4:5, 1:1, 16:9 y **reencuadre** al cambiar: cover/contain,
  paneo manual del video dentro del marco, posiciones de capas relativas al
  formato. **[hoy]** solo hereda el formato de Crear; **[nuevo]** el resto
- Zonas seguras por red (donde Reels/TikTok pintan su interfaz), guías, rejilla,
  imán a centro/bordes. **[nuevo]**
- Selección directa sobre el lienzo: mover, escalar, rotar, arrastrar textos,
  imágenes y PIP con asas; edición de texto en sitio. **[nuevo]**
- Fondo del lienzo: color, o desenfoque del propio video para rellenar barras
  (16:9 → 9:16). **[nuevo]**
- Zoom del lienzo. **[nuevo]**

### B. Línea de tiempo

- Pistas: video principal, videos superpuestos, imágenes/stickers, textos,
  subtítulos, voz, música, sonido de escena, efectos de sonido. **[nuevo]**
- Clips de video: cortar en el cabezal (split), recortar por los extremos
  (trim), mover, reordenar, duplicar, borrar, ripple (cerrar huecos), imán.
  **[nuevo]** (hoy los segmentos salen de `scdet` y no se ven)
- Velocidad por clip (0,5×–2×), congelar fotograma, reversa. **[nuevo]**
  (`minterpolate` para cámara lenta suave es caro en 1 núcleo)
- Marcadores automáticos: cortes detectados **[hoy, no visibles]**, compases
  por BPM **[spec S7]**, bloques del guion **[spec S6]**
- Tira de fotogramas en los clips de video **[spec S5]**, forma de onda en los
  clips de audio **[nuevo]**
- Zoom y desplazamiento del timeline, regla de tiempo, atajos (espacio, J/K/L,
  S para cortar, flechas por fotograma, Cmd+Z). **[nuevo]**
- Deshacer/rehacer, autoguardado, historial. **[nuevo]**
- Multi-selección, agrupar/desagrupar, bloquear pista, ocultar/silenciar pista.
  **[nuevo]**
- Estructura de guion **libre**: bloques con rol, cualquier número y orden
  (hoy exactamente 5, orden fijo, validado en `tipos.validar_guion`). **[nuevo]**

### C. Medios (biblioteca del proyecto)

- Fuentes ya en la casa: el clon de Crear (crudo y mezclado) **[hoy]**; otras
  piezas del proyecto (Crear, sprints, ganadores de experimentos) **[nuevo]**;
  imágenes del catálogo (bloque 5) **[nuevo]**; personajes y referencias de
  marca (`clientes/<c>/personajes`, `marca`) **[nuevo]**; logo **[hoy, solo en
  la tarjeta CTA]**
- Subidas del usuario: video, imagen, audio (locución propia, jingle).
  **[nuevo]** (hoy solo se suben personajes y marca)
- Generar desde el editor sin salir: imagen (Higgsfield), video (FlowPlus),
  variación de un clip, con estimado y aprobación antes, como manda la casa.
  **[nuevo] [paga]**
- Proxies para el navegador: versión 540p de cada video para que la vista
  previa fluya; el render usa el original. **[nuevo]**
- Buscar, filtrar, favoritos, arrastrar al timeline. **[nuevo]**

### D. Texto

- Capas de texto libres, tantas como quepan en el cupo. **[nuevo]**
- Roles con estilo (hook, subtítulo, CTA, precio, badge, descripción) y
  plantillas por marca → producto → temporada → país. **[spec §3.1]**
- Tipografía: familia (set curado de Google Fonts OFL, ~20 en vez de 3), peso,
  tamaño, interlineado, espaciado, alineación, mayúsculas. **[nuevo]**
- Color, degradado, contorno, sombra, fondo (píldora, tarjeta, caja),
  opacidad, redondeo. **[hoy]** solo lo fijo por arquetipo; **[nuevo]** editable
- Posición libre, anclas, rotación, escala. **[nuevo]** (hoy fracciones fijas)
- Animaciones de entrada/salida con duración: aparecer, deslizar, rebote,
  máquina de escribir, zoom, palabra por palabra. **[spec S7]** solo el hook;
  **[nuevo]** para cualquier capa
- Subtítulos automáticos: karaoke por palabra **[hoy]**, estilos predefinidos
  tipo CapCut (varios) **[nuevo]**, agrupación por líneas y posición **[nuevo]**,
  corregir palabras y resincronizar **[nuevo]**, apagar por bloque **[spec S6]**
- Textos como variables multiidioma por destino y precio por país nunca
  convertido. **[spec §3.2]** + regla vigente **[hoy]**
- Emojis en texto. **[nuevo]** (fuente de emojis a color en el servidor)

### E. Imágenes y videos superpuestos

- Imagen como capa: posición, escala, rotación, opacidad, máscara (círculo,
  esquinas), sombra, borde, entrada/salida animada. **[nuevo]**
- Video superpuesto (PIP): segunda pista de video con las mismas asas, recorte,
  su sonido encendido o apagado. **[nuevo]**
- Secuencia de varios videos: montaje de varias piezas una tras otra en la
  pista principal (la final deja de "colgar" de un solo clon). **[nuevo]**
- Marca de agua/logo persistente con posición. **[nuevo]**
- Chroma key (fondo verde) con `chromakey` de ffmpeg. **[nuevo]**
- Quitar fondo de una imagen con IA. **[nuevo] [paga]** (vía fal; el servidor
  no tiene numpy)
- Formas simples (rectángulo, flecha, línea, círculo) para señalar. **[nuevo]**
- Stickers/emojis grandes. **[nuevo]**
- Máscara sobre el video principal (zoom a una región, viñeta). **[nuevo]**

### F. Audio

- Pistas: voz por bloque **[hoy]**, música por estilo **[hoy]**, sonido de la
  escena nativo **[hoy]**, sonido generado desde el video **[spec S3] [paga]**,
  efectos cortos (whoosh, golpe) **[spec S7] [paga una vez]**, audio subido por
  el usuario **[nuevo]**, grabar voz con el micrófono en el navegador **[nuevo]**
- Por clip de audio: volumen, fundido de entrada/salida, recorte, dividir,
  keyframes de volumen, silenciar. **[nuevo]** (hoy solo 3 presets; `volumenes`
  existe en la API y no en la UI)
- Ducking automático de música y sonido bajo la voz **[hoy]**, normalización
  `loudnorm` **[hoy]**, medidor de nivel en la vista previa **[nuevo]**
- Voz: selector con muestra de 3 s **[spec S5]**, velocidad/tempo por bloque
  **[hoy, automática]**, pausas y énfasis **[nuevo]**, caché por bloque para
  pagar solo lo cambiado **[spec S6]**
- Música: muestra de 15 s por estilo **[spec S5]**, BPM fijo por estilo y
  cortes al compás **[spec S7]**, recorte y punto de inicio de la pista
  **[nuevo]**
- Stems guardados (voz + palabras, música, sonido) y remezcla sin pagar.
  **[spec S4]** — prerrequisito de cualquier edición gratis
- Sincronizar subtítulos a una locución subida (Whisper). **[nuevo] [paga]**

### G. Efectos, transiciones y movimiento

- Transiciones entre clips: corte, fundido, deslizar, zoom, desenfoque (ffmpeg
  8 trae ~50 `xfade`). **[nuevo]**
- Movimiento: Ken Burns **[hoy, automático]**; keyframes de posición, escala,
  rotación y opacidad en cualquier capa **[nuevo]**; sacudida y "zoom punch" en
  los golpes de la música **[nuevo]**
- Color: LUT por marca (`lut3d`), brillo/contraste/saturación, viñeta,
  desenfoque, grano, blanco y negro, presets. **[nuevo]**
- Flash o `tblend` en cortes, glitch. **[nuevo]** (limitar: es lo primero que
  cansa)
- Tarjeta final de marca e intro. **[spec S7]**
- Cámara lenta con interpolación. **[nuevo]** (caro en CPU; probable "fuera")

### H. IA dentro del editor

- Borrador automático: guion, cortes, voz, música y textos ya colocados
  **[hoy, como pipeline cerrado]** → abre en el editor **[nuevo]**
- Variantes de hook y de estructura **[hoy, solo desde derivaciones]** → botón
  en el editor **[nuevo]**
- "Pídele al editor": instrucción en texto ("hook más grande y amarillo, corta
  el segundo 3 al 5, música más suave") → Claude edita el documento con
  herramientas y el cambio aparece en el lienzo, deshacible. **[nuevo]** (encaja
  con el stack: el documento es JSON y Claude ya está en todas partes)
- Auto-subtítulos y traducción/localización por destino **[hoy]**, con
  corrección en pantalla **[nuevo]**
- Sugerir sonido de la escena **[hoy]**, generar sonido **[spec S3]**, efectos
  por descripción **[spec S7]**
- Cortar silencios y muletillas automáticamente. **[nuevo]**
- Visión: detectar dónde está el producto/rostro para no taparlo con textos y
  para reencuadrar con criterio. **[nuevo] [paga centavos]**
- Imagen: quitar fondo, mejorar resolución, extender (outpaint). **[nuevo] [paga]**
- QA del final antes de exportar (texto cortado, precio ilegible, capa fuera
  del marco, audio saturado). **[nuevo]** (hay QA con visión en sprints §2.4)

### I. Plantillas y marca

- Kit de marca: colores, logo, fuentes, voz y música por defecto, zonas
  seguras, LUT. **[hoy]** solo `marca.json` de estilo y un `color_acento` que
  nada escribe; **[nuevo]** el resto
- Plantillas de texto por rol y ámbito. **[spec §3.1]**
- Plantillas de video completas: un proyecto de edición con huecos
  (placeholders) que se aplica a otra pieza; "guardar este proyecto como
  plantilla". **[nuevo]**
- Presets de subtítulos, de mezcla **[hoy]**, de transiciones **[nuevo]**
- Crear plantilla desde una referencia con visión. **[spec §3.1]**

### J. Destinos, idiomas y salidas

- Un proyecto → N finales por idioma/país con voz por idioma, textos por
  idioma, precio por país. **[hoy]** (por checkboxes) → desde el mismo documento
  **[nuevo]**
- Un proyecto → varios formatos (9:16 + 4:5 + 1:1) con reencuadre por capa.
  **[nuevo]**
- Exportar: resolución (1080/720), fps, calidad, con o sin marca de agua,
  miniatura eligiendo el fotograma, solo audio, GIF corto, portada estática.
  **[hoy]** solo 1080 a 30 fps y miniatura del medio
- Final edition de imágenes: el mismo editor con lienzo estático → PNG/JPG, y
  carrusel de varias imágenes. **[spec §3.3]** (allí como módulo aparte; aquí
  como el mismo editor)
- Video desde imagen (Ken Burns sobre una foto de producto). **[nuevo]**
- Versiones: cada "Producir" guarda una versión del documento; comparar y
  restaurar. **[nuevo]** (hoy no se persisten ni las opciones)
- Entrega: descarga, link, al sprint, a un experimento, publicación orgánica
  del ganador (bloque 7). **[hoy]** en parte

### K. Revisión y aprobación

- Comentarios anclados a un tiempo del video, con marcador en el timeline
  (cliente ↔ agencia). **[nuevo]**
- Estados del final: borrador → producido → aprobado, con quién y cuándo.
  **[hoy]** solo `generando/listo/degradada/error`
- Link público de revisión (ya existe la landing pública). **[nuevo]**

### L. Costos (regla de la casa)

- Antes de cada clic que paga, el costo exacto: "2 bloques de voz USD 0,01 ·
  música en caché USD 0 · render gratis". **[spec S8]**
- Nada se paga dos veces: caché por hash de voz **[spec S6]**, música
  **[hoy]**, stems **[spec S4]**, materiales generados **[nuevo]**
- Render y vista previa siempre gratis. **[nuevo]** (hoy cada render re-paga)
- Presupuesto por proyecto/sprint y aviso al acercarse. **[nuevo]**

## 4. Lo que manda del stack (y las bifurcaciones que abre)

1. **La vista previa vive en el navegador.** Con 1 núcleo y 1,9 GB, el servidor
   no puede renderizar nada por cada ajuste. Video con `<video>` por clip
   (proxies 540p), capas sobre `<canvas>`, audio con Web Audio. Es el bloque de
   frontend más grande que ha tenido el repo.
2. **Cómo se pinta el texto en el render final** (la fidelidad "lo que ves es lo
   que sale"):
   - *PNG desde el navegador*: al exportar, el navegador rasteriza cada capa de
     texto/forma a PNG con alfa a resolución final y lo sube junto al documento;
     ffmpeg solo compone. Idéntico al preview. Pero cada PNG es un `overlay`
     (~8 MB de RAM) y los subtítulos palabra por palabra revientan el tope de 80.
   - *ASS/libass en el servidor*: todos los textos y subtítulos en un solo
     archivo `.ass` (fuentes, colores, contorno, sombra, posición, karaoke,
     animaciones `\move \fad \t`) → **un solo filtro**, sin tope de overlays.
     El navegador dibuja lo mismo con su propio código y las mismas fuentes;
     puede haber diferencias de un píxel.
   - *Híbrido (probable)*: PNG del navegador para las pocas capas libres
     (textos grandes, formas, imágenes), ASS para los subtítulos (muchos y
     sincronizados). `drawtext` de ffmpeg queda fuera: no sabe envolver ni
     karaoke.
3. **Dónde se renderiza el final**: servidor (ffmpeg, cola, reproducible, N
   destinos sin que el navegador esté abierto) o navegador (WebCodecs, al
   instante, depende del dispositivo y de dejar la pestaña abierta).
   Recomendación previsible: servidor para el final, navegador solo para ver.
4. **Memoria de ffmpeg**: una sola pasada con `xfade` obliga a decodificar dos
   clips a la vez; con varias pistas de video superpuestas hay que renderizar
   por tramos y concatenar. Es diseño, no impedimento.
5. **Un núcleo**: un final de 20 s tarda hoy ~150 s (la mitad es voz/música). Con
   más capas y transiciones subirá; el worker es de una tarea a la vez. Se
   mitiga con proxies, render por tramos y prioridad de cola; se resuelve con
   un segundo núcleo o un worker de render aparte.
6. **Frontend sin framework**: el editor necesita módulos JS propios (ES
   modules sin bundler siguen valiendo), un estado central del documento,
   deshacer/rehacer y pruebas de JS (hoy no hay ninguna). Adoptar algo pequeño
   por CDN (Preact/Svelte) es una decisión, no una necesidad.
7. **Fuentes**: pasar de 3 TTF a un set curado OFL, cargado en el navegador
   (`@font-face`) y en el servidor (Pillow/libass), con el mismo archivo para
   que midan igual.
8. **Modelo de datos**: hoy la final es una `pieza tipo=final` colgada de un
   clon, sin `opciones`. Hace falta una tabla `edicion` (documento JSON
   versionado, materiales, de qué piezas depende) y que la final apunte a la
   versión que la produjo.
9. **Celular**: CapCut nació en el teléfono; este dashboard se usa desde el
   celular para aprobar. Un timeline con dedos es otro nivel de trabajo. Cabe
   un "modo simple" en el teléfono (plantilla, textos, aprobar) y el editor
   completo en escritorio.

## 5. Decisiones que hay que tomar (en este orden)

1. **Quién edita y dónde**: Daniel/agencia en escritorio, el cliente en el
   celular, o ambos con dos modos.
2. **Qué es "poner otros videos"**: secuencia (montaje de varias piezas), PIP
   (encima), o ambos. Y si el editor abre siempre con el borrador automático.
3. **Fidelidad del texto**: PNG del navegador, ASS o híbrido (§4.2).
4. **Render final**: servidor o navegador (§4.3).
5. **Imágenes desde el día 1** en el mismo editor, o después.
6. **Frontend**: módulos propios o una librería pequeña.
7. **Fases**: qué se ve funcionando primero.

## 6. Fuera, probablemente (para no perderse)

Multicámara, seguimiento de movimiento, curvas de color profesionales,
ecualizador, edición colaborativa simultánea, clonación de voz del cliente,
música con letra, 3D, plugins, exportar proyecto a Premiere/CapCut, pantalla
verde con iluminación, cámara lenta interpolada, doblaje.

## 7. Orden de construcción posible (para discutir en el diseño)

1. **Motor**: documento de edición + render ffmpeg desde el documento +
   borrador automático que produce ese documento (el pipeline de hoy, con
   stems y caché de voz). Sin UI nueva: la pantalla actual sigue, pero todo
   pasa por el documento. Visible: nada cambia para el usuario; deja de pagarse
   dos veces.
2. **Editor base**: lienzo con vista previa, timeline con recorte/split/orden,
   capas de texto e imagen con posición, fuente, color y animaciones básicas,
   subtítulos con estilos, deshacer, autoguardado, exportar. Visible: CapCut
   básico sobre una pieza de Crear.
3. **Audio**: pistas, formas de onda, volumen por clip y fundidos, subir audio,
   grabar, muestras de voz y música, cortes al compás, efectos.
4. **Medios y montaje**: varias piezas, PIP, catálogo, generar desde el editor,
   proxies.
5. **Plantillas, formatos e idiomas**: kit de marca, plantillas de video, N
   formatos y N destinos desde un proyecto, imágenes y carruseles.
6. **IA en el editor**: "pídele al editor", visión para no tapar el producto,
   QA antes de exportar, comentarios de revisión.
