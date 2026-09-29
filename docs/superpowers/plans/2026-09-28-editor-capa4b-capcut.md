# Editor capa 4b — el editor tipo CapCut — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la página del editor sea un editor de verdad con la disposición de CapCut de escritorio: biblioteca a la izquierda (videos e imágenes del proyecto, lo que se sube, canciones, textos, transiciones) desde la que se AGREGA a la línea de tiempo; reproductor al centro donde se toca un texto o una imagen y se mueve o agranda; panel de propiedades a la derecha para lo elegido; y abajo una línea de tiempo de varias pistas con miniaturas, onda de audio, cortar en cualquier pista, borrar, deshacer y zoom. En la pestaña Final edition, el botón principal pasa a ser «Editar» y lo automático con IA queda aparte y opcional.

**Architecture:** Todo lo que el motor ya renderiza se vuelve editable desde la página (inventario: varios videos distintos en la principal, capas de imagen y de texto con inicio/fin, 5 transiciones, volumen y fundidos por clip, zoom lento). Lo nuevo del servidor es poco: subir video/imagen/audio a `material`, listar la biblioteca y convertir una pieza de Crear en material (tarea gratis). Lo nuevo del navegador son operaciones puras para AGREGAR y CAMBIAR (probadas con Node y validadas por Python con `documento.validar` + `verificar_recortes`), ayudas puras para tocar/arrastrar sobre el lienzo, y cuatro módulos de interfaz (biblioteca, propiedades, interacción del lienzo, línea de tiempo mejorada) sobre la página de la capa 4a.

**Tech Stack:** Python 3 / Flask / SQLAlchemy / ffmpeg (existente); JavaScript ES2022 en módulos nativos, DOM + Pointer Events; `node --test` para lo puro.

**Spec:** `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` §4 (Interfaz: barra de herramientas Texto/Audio/Medios/Efectos, panel contextual, lienzo con asas) — con el pedido explícito de Daniel del 2026-09-28 («algo tipo así», captura de CapCut de escritorio: biblioteca | reproductor | propiedades, línea de tiempo abajo; «donde se agreguen cosas, se corten videos, se pongan más, no esta mierda de preguntas para hacer cosas automáticas»). Inventario del motor: `inventario-motor-4b.md` (resumido en Global Constraints).

## Global Constraints

- Disposición de escritorio (≥ 1024 px): barra superior; fila central de tres columnas — biblioteca (izquierda, ~300 px), reproductor (centro, flexible), propiedades (derecha, ~300 px); debajo, barra de herramientas y la línea de tiempo a todo el ancho. En celular (≤ 760 px): reproductor arriba, barra de herramientas, línea de tiempo, y la biblioteca/las propiedades como hojas que suben desde abajo con botones «Medios · Audio · Texto · Transiciones» y «Editar» (propiedades). Nada desborda la página hacia los lados.
- Nada de preguntas para hacer cosas automáticas dentro del editor: todo es manual y directo. Nada de lo nuevo paga a un proveedor (subir, preparar una pieza de Crear, proxies: gratis).
- El documento que sale de cualquier operación cumple `documento.validar` y el espejo de `compilador.verificar_recortes` (ya en `operaciones.normalizar`). Cada operación nueva va a `tests/js/salida_operaciones.mjs` para que Python la valide.
- Solo se ofrece en la interfaz lo que el render hace de verdad: transiciones `corte, fundido, deslizar, zoom, desenfoque` (esta última se muestra como «Fundido a negro»: el filtro real es `fadeblack`); animación de entrada del texto solo `ninguna | deslizar`; fuentes solo las 3 de `static/fonts/` (Inter-Bold, Inter-SemiBold, SpaceGrotesk-Bold); NO video sobre video (PIP), NO filtros de color, NO rotación, NO foto como clip de la pista principal (una foto se agrega como capa de imagen, con «Llenar la pantalla»).
- Pistas: la principal `video` siempre existe; las demás (`texto`, `imagen`, `audio`) se crean al agregar algo que no cabe sin solaparse en una existente y se borran solas cuando quedan vacías (salvo la principal y `p_sonido`).
- Textos visibles en español llano; estilos con los tokens de `static/style.css`; los ids y clases nuevos llevan prefijo `ed-`. Seguridad: el guard de `<cliente>` de siempre; todo POST exige mismo origen (`_mismo_origen` de `final_edition/rutas_editor.py`); un material de otro proyecto nunca entra (ya lo impide `_materiales_ajenos` al guardar).
- Worktree `.claude/worktrees/editor-capa4`, rama `editor-capa4b` (desde main 4bc3bd7). `PY` = `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`. Antes de cada commit: `node --test tests/js/*.test.mjs` y `PY -m pytest -q -m "not slow" -p no:cacheprovider` (base 3139 con lentas; los 3 FutureWarning de google-auth son previos).

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `final_edition/biblioteca.py` (nuevo) | Lista de la biblioteca de un proyecto (materiales + piezas de Crear) y la forma de un material para la página |
| `final_edition/rutas_editor.py` (mod) | `editor.subir`, `editor.biblioteca`, `editor.agregar_pieza`, `editor.materiales_por_id` |
| `tareas/edicion.py` (mod) | `tiene_audio` en `edicion_proxy`; tarea `material_de_pieza` |
| `final_edition/vista_previa.py` (mod) | `material_para(m)` compartido |
| `static/editor/operaciones.js` (mod) | Agregar video/imagen/audio/texto, cortar cualquier clip, transición, editar texto, cambiar propiedades, espejo de sonido por clip y sin videos mudos, pistas vacías fuera |
| `static/editor/historial.js` (mod) | Fusionar pasos seguidos de un mismo control (un deslizador = un solo deshacer) |
| `static/editor/seleccion.js` (nuevo, puro) | Caja de una capa en pantalla, capa bajo el dedo, mover y escalar con imán al centro |
| `static/editor/linea_tiempo.js` (mod) | Cabeceras de pista, onda de audio, soltar desde la biblioteca, varias filas por tipo |
| `static/editor/biblioteca.js` (nuevo, navegador) | Panel izquierdo: pestañas, subir, preparar, agregar, arrastrar |
| `static/editor/propiedades.js` (nuevo, navegador) | Panel derecho: formularios por tipo de clip |
| `static/editor/lienzo_interaccion.js` (nuevo, navegador) | Caja de selección y asas sobre el reproductor |
| `static/editor/vista.js` (mod) | `agregarMateriales(mapa)` |
| `static/editor/pagina_editor.js` (mod) | Une todo |
| `templates/editor.html` (mod) | La disposición nueva |
| `templates/_tab_final.html`, `dashboard.py` (mod) | «Editar» como acción principal; lo automático con IA en un desplegable opcional |
| `tests/…` | Node y pytest de cada tarea |

---

### Task 1: El servidor de la biblioteca — subir, listar y preparar piezas de Crear

**Files:**
- Create: `final_edition/biblioteca.py`, `tests/test_biblioteca_editor.py`
- Modify: `final_edition/rutas_editor.py`, `final_edition/vista_previa.py`, `tareas/edicion.py`, `tests/test_rutas_editor.py`, `tests/test_tareas_edicion.py`, `tests/test_tareas_swap.py` (lista del registro, si se agrega una tarea)

**Interfaces:**
- Consumes: `materiales.subir/validar_subida/bytes_usados/CUOTA_BYTES/hash_archivo/obtener`, `mezcla.tiene_audio`, `cortes.ffprobe_json/duracion`, `final_edition/insumos.clon`, `creative_flow.cargar`, `trabajos.encolar/en_curso`, `vista_previa.materiales_para`.
- Produces:
  - `vista_previa.material_para(m) -> dict` (la forma que ya arma `materiales_para` por material: `id, tipo, url, url_proxy, duracion_ms, ancho, alto, picos, proxy_version, tira_url` **+ `tiene_audio`, `nombre`, `origen`**); `materiales_para` la usa.
  - `biblioteca.listar(cliente) -> {"materiales": [material_para…], "piezas": [{cf_id, nombre, tipo, formato, video_url, material_id|None, preparando: bool}]}`: materiales del proyecto de tipo `video|imagen|audio` (no los derivados: `origen` en `("subida","crear","musica","voz","logo")`; nunca `png_texto`, proxies ni tiras), más recientes primero, tope 200; piezas de Crear con `estado=="video_listo"` y `tipo=="video"`, con el `material_id` si esa pieza ya es material (`extra.cf_id`) y `preparando` si su tarea `material_de_pieza` está en curso.
  - `POST /cliente/<c>/ediciones/materiales/subir` (endpoint `editor.subir`), multipart `archivo` (uno por pedido): extensión → tipo (`.mp4 .mov .webm .m4v` video; `.jpg .jpeg .png .webp` imagen; `.mp3 .wav .m4a .aac .ogg` audio); guarda en una carpeta temporal del proyecto, mide con ffprobe (video: duración, ancho, alto, `tiene_audio`; imagen: ancho, alto con Pillow; audio: duración), `materiales.validar_subida` y la cuota (`bytes_usados + tamaño <= CUOTA_BYTES`), sube con `materiales.subir(cliente, local, f"clientes/{c}/materiales/{hash}{ext}", content_type, tipo=, origen="subida", duracion_ms=, ancho=, alto=, extra={"nombre": <nombre del archivo sin extensión, 80 máx.>, "tiene_audio": …})`, borra el temporal (finally), encola `edicion_proxy` (gratis, `max_intentos=3`, `prioridad=1`, job `f"{c}__proxy__{mid}"`) para video y audio, y responde 200 `{material: material_para(m)}` | 400 `{error}` (tipo no permitido, pesa más, dura más, cuota) | 403 (otro origen).
  - `GET /cliente/<c>/ediciones/biblioteca` (endpoint `editor.biblioteca`) → `biblioteca.listar(c)`.
  - `POST /cliente/<c>/ediciones/biblioteca/pieza/<cf_id>` (endpoint `editor.agregar_pieza`): valida `cf_id` con `_CF_RE` de `tareas/edicion.py`, que la pieza sea de este proyecto, `video_listo` y de tipo video; si ya es material responde `{material: …}`; si no, encola la tarea gratis `material_de_pieza` `{cliente, cf_id}` (job `f"{c}__{cf_id}__material"`, `max_intentos=2`) y responde 202 `{preparando: true}`.
  - Tarea `material_de_pieza`: la misma preparación que `edicion_clon.crear` hace con el clon (`insumos.clon` sobre el crudo, reusando `video_local_crudo` si está en disco), sin crear edición. Guarda `extra.nombre` = nombre visible de la pieza.
  - `GET /cliente/<c>/ediciones/materiales?ids=1,2,3` (endpoint `editor.materiales_por_id`) → `{materiales: {id: material_para(m)}}` solo de este proyecto (los ajenos no aparecen).
  - `edicion_proxy` guarda `extra["tiene_audio"]` para video (con `mezcla.tiene_audio(original)`).
- [ ] **Step 1: Pruebas que fallan** (pytest, con R2 parchado como en `tests/test_mi_musica.py`/`tests/test_tareas_edicion.py`; ffprobe real sobre medios sintéticos de `ffmpeg -f lavfi` — marcar `slow` solo si generan video): subir un mp4 corto → 200, fila `material` de tipo video con duración/ancho/alto/`tiene_audio`, tarea `edicion_proxy` encolada; subir un png → imagen con ancho/alto, sin proxy; subir un mp3 → audio + proxy; `.exe` → 400 «Sube un video, una imagen o un audio.»; otro origen → 403; cuota superada → 400; la biblioteca lista lo subido y las piezas de Crear listas (y no las de otro proyecto ni los `png_texto`); `agregar_pieza` de una pieza ajena → 404, de una lista → 202 y encola; la tarea `material_de_pieza` crea el material con `extra.cf_id` y `extra.nombre`; `materiales_por_id` no devuelve ids de otro proyecto; `edicion_proxy` guarda `tiene_audio`.
- [ ] **Step 2: Implementar** lo de Interfaces.
- [ ] **Step 3: Correr** focalizadas y suite rápida; commit `Editor capa 4b (1/9): biblioteca del proyecto — subir, listar y preparar piezas de Crear`.

---

### Task 2: Operaciones para AGREGAR y CAMBIAR (puras, validadas por Python)

**Files:**
- Modify: `static/editor/operaciones.js`, `static/editor/historial.js`, `tests/js/operaciones.test.mjs`, `tests/js/historial.test.mjs`, `tests/js/salida_operaciones.mjs`, `tests/test_operaciones_editor.py`

**Interfaces:**
- Consumes: el `normalizar`/`terminar`/`sincronizarSonido`/`recolocar`/`idNuevo` actuales.
- Produces (todas `(doc, …, info = {}) -> {doc, seleccion}` con doc NUEVO; `info` = `{material_id: {duracion_ms, tiene_audio}}` — las operaciones existentes siguen aceptando el mapa viejo `{id: duracion_ms}`: un número se lee como `{duracion_ms: n}`):
  - `agregarVideo(doc, material, {despuesDe = null} , info)`: inserta un clip del material entero (recorte 0..duración, velocidad 1, `transform` por defecto, `ken_burns: null`, sin transición) en la principal después del clip `despuesDe` (o al final); `seleccion` = el clip nuevo. Si el material no tiene duración conocida → `OperacionInvalida("Ese video todavía se está preparando.")`.
  - `agregarImagen(doc, material, tMs, {llenar = false, duracionMs = 3000}, info)`: capa en una pista `imagen` (la primera sin solape en `[t, t+d)`, o una nueva `p_imagen_N`); `transform` centrado; `llenar` pone `escala` para cubrir el lienzo (cover, con `ancho/alto` del material y `FORMATOS`) — sin `llenar`, `escala` que la deje a lo ancho del 60 % del lienzo.
  - `agregarAudio(doc, material, tMs, {rol = "musica"}, info)`: clip de audio del material entero en una pista `audio` sin solape (o nueva `p_audio_N`), `rol_audio` `musica` o `efecto`, volumen 1, sin fundidos (música: fundido de salida 1000 ms).
  - `agregarTexto(doc, tMs, preset, info)`: presets `titulo` (Inter-Bold 72, blanco, contorno negro 4, y 0.2), `subtitulo` (Inter-SemiBold 48, blanco, sombra, y 0.75), `precio` (SpaceGrotesk-Bold 56, fondo píldora del color de marca, y 0.6), `llamado` (Inter-Bold 52, fondo caja blanca 90 %, texto negro, y 0.85); literal «Escribe aquí» (precio: «$ 0»); 3000 ms; en una pista `texto` sin solape o nueva `p_texto_N`.
  - `cortarClip(doc, clipId, tMs, info)`: corta el clip indicado (de cualquier pista salvo `p_sonido`) en `tMs`; en audio/video parte también el `recorte`; en texto/imagen solo el tiempo (el `pngs[clipId]` se copia al nuevo id). `cortarEn` (principal bajo el cabezal) queda como está.
  - `ponerTransicion(doc, clipId, tipo, duracionMs = 500, info)`: en un clip de la principal que no es el último; `corte` la quita; `normalizar` ya acorta o quita la que no cabe.
  - `editarTexto(doc, clipId, texto, destino, info)`: si el clip tiene `texto.literal`, lo cambia; si tiene `texto.variable`, escribe `variables.textos[destino][variable]`; texto vacío → `OperacionInvalida("El texto no puede quedar vacío.")`; siempre borra `pngs[clipId]` (el servidor o el navegador lo vuelven a dibujar).
  - `cambiar(doc, clipId, cambios, info)`: aplica un objeto de cambios SOLO por esta lista blanca (lo demás → `OperacionInvalida`): `estilo.{fuente, tamano, color, alineacion, contorno, sombra, fondo, ancho_max}`, `transform.{x, y, escala, opacidad}`, `audio.{volumen, fundido_entrada_ms, fundido_salida_ms}`, `ken_burns` (`null|"in"|"out"`), `animacion.entrada` (`ninguna|deslizar`); valores fuera de rango se acotan (x, y, opacidad, volumen a 0..1; escala a 0.05..5; tamaño 12..200); en un clip de texto borra `pngs[clipId]` si cambia `estilo`.
  - `volumenSonido(doc, clipPrincipalId, volumen, info)`: volumen del sonido de la escena de ese clip (su espejo `s_<id>`).
  - `sincronizarSonido` conserva el `audio` de cada espejo por id (`s_<id>`) en vez de copiar el del primero, y NO crea espejo para un clip cuyo material tiene `tiene_audio === false` (desconocido cuenta como con audio, como hoy).
  - `terminar` elimina las pistas no principales que quedaron sin clips (nunca `p_sonido`, que desaparece sola si no hay nada que espejar y vuelve al haberlo).
  - `Historial.aplicar(doc, {clave = null} = {})`: si `clave` no es nula y es la misma del paso anterior hecho hace menos de 800 ms, reemplaza el paso en vez de apilar otro (un deslizador arrastrado = un solo deshacer); expone `Historial.ahora` inyectable para pruebas.
- [ ] **Step 1: Pruebas Node que fallan** para cada operación (casos felices, inválidos con mensaje, doc de entrada intacto, `seleccion`), el espejo por clip y sin mudos, la limpieza de pistas, y `Historial` con clave (fusiona dentro de 800 ms, no fusiona con otra clave o pasado el tiempo). Casos nuevos en `salida_operaciones.mjs` (al menos uno por operación, incluidos agregar un video de otro material con otra duración, cortar un audio y una imagen, transición a cada tipo) que `tests/test_operaciones_editor.py` pasa por `documento.validar` y `verificar_recortes`.
- [ ] **Step 2: Implementar.**
- [ ] **Step 3:** Node + `PY -m pytest -q tests/test_operaciones_editor.py tests/test_editor_js.py`; suite rápida; commit `Editor capa 4b (2/9): operaciones para agregar y cambiar`.

---

### Task 3: Ayudas puras para tocar y arrastrar sobre el reproductor

**Files:**
- Create: `static/editor/seleccion.js`, `tests/js/seleccion.test.mjs`

**Interfaces:**
- Consumes: `tiempo.capasEn`, `tiempo.posicionCapa`, `tiempo.tamanoCapaImagen`, `tiempo.CAPA_DEFECTO`, `formatos.js`, `geometria.js`.
- Produces:
  - `cajaCapa(doc, clip, tMs, materiales, medidasTexto) -> {x, y, ancho, alto}` en píxeles del lienzo (misma geometría que `lienzo.js` usa para dibujar esa capa en `tMs`; `medidasTexto[clipId] = [ancho, alto]` del PNG del navegador, o `CAPA_DEFECTO`).
  - `capaEnPunto(doc, tMs, px, py, materiales, medidasTexto) -> clipId | null`: la capa de arriba (la última en dibujarse) que contiene el punto; solo capas `texto` e `imagen` activas en `tMs`.
  - `moverCapa(transform, dxPx, dyPx, formato, {iman = 12}) -> {x, y}`: nueva posición en fracciones, acotada a 0..1, con imán al centro horizontal/vertical (si queda a menos de `iman` px del centro, se pega) — devuelve también `guias: {vertical: bool, horizontal: bool}` para dibujar las líneas.
  - `escalarCapa(transform, cajaInicial, dxPx, dyPx) -> escala` (arrastrar la esquina: la escala crece con la distancia al centro de la caja; acotada 0.05..5).
- [ ] **Step 1: Pruebas Node que fallan** con el `docBase` de las pruebas (texto `t1` en 1000..3000) y un clip de imagen: caja en píxeles que coincide con lo que calcula `posicionCapa`/`geometria` para ese instante; `capaEnPunto` elige la de arriba cuando se solapan y `null` fuera de su tiempo; `moverCapa` acota y pega al centro; `escalarCapa` duplica la escala al duplicar la distancia y respeta los topes.
- [ ] **Step 2: Implementar.** **Step 3:** Node; commit `Editor capa 4b (3/9): ayudas puras para tocar y arrastrar sobre el video`.

---

### Task 4: La disposición nueva de la página (tipo CapCut)

**Files:**
- Modify: `templates/editor.html`, `static/editor/pagina_editor.js`, `static/editor/vista.js`, `tests/test_rutas_editor.py`, `tests/js/modulos_navegador.test.mjs`

**Interfaces:**
- Consumes: todo lo de la capa 4a; `urls` de `datos_pagina` (sumar `biblioteca`, `subir`, `agregar_pieza` (con `__CF__` como marcador), `materiales_por_id`).
- Produces:
  - `templates/editor.html` con: `#ed-barra` (← Final edition, nombre, deshacer/rehacer, estado del guardado, Producir), `#ed-cuerpo` con `#ed-biblioteca` (izquierda: `#ed-pestanas-biblioteca` con botones `data-panel="medios|audio|texto|transiciones"` e iconos, y `#ed-panel-biblioteca`), `#ed-centro` (el lienzo de siempre `#lienzo` dentro de `#ed-escenario` — contenedor relativo para la capa de interacción — y el transporte), `#ed-propiedades` (derecha, `#ed-panel-propiedades` con el estado vacío «Elige algo en la línea de tiempo o en el video para cambiarlo.»); `#ed-herramientas` (deshacer, rehacer, cortar, borrar, duplicar, zoom de la línea) y `#linea` a todo el ancho. Mantiene los ids de la 4a que las pruebas y los módulos usan (`lienzo`, `destino`, `reproducir`, `inicio`, `tiempo`, `barra`, avisos, `producir*`, `h-*`, `estado-guardado`, `recargar`, `linea`, `linea-zoom`).
  - Celular (≤ 760 px): columnas apiladas; `#ed-biblioteca` y `#ed-propiedades` son hojas inferiores ocultas que se abren con `#ed-abrir-medios` y `#ed-abrir-propiedades` (y se cierran con su «Listo»); el reproductor ocupa como mucho 42vh.
  - `VistaPrevia.agregarMateriales(mapa)`: suma materiales (misma forma que `material_para`) sin recargar la página, renueva los `<video>` de los que cambiaron, y pide un cuadro; `pagina_editor.js` expone un único `editor` interno con `operar`, `seleccionar(id)`, `seleccion`, `doc()`, `tiempo()`, `info()` (el mapa `{id: {duracion_ms, tiene_audio}}`) y `agregarMateriales` para que los módulos de las tareas 5–8 se enganchen sin tocarse entre sí.
- [ ] **Step 1:** Pruebas pytest de la página (ids nuevos presentes, urls nuevas en los datos) y Node (los módulos importan sin efectos).
- [ ] **Step 2: Implementar** la disposición con CSS de la página usando los tokens; sin desborde lateral en 375 px (`tests/test_movil.py` sigue verde).
- [ ] **Step 3:** suite; commit `Editor capa 4b (4/9): la página con la disposición de CapCut`.

---

### Task 5: Línea de tiempo de varias pistas, con cabeceras, onda y soltar desde afuera

**Files:**
- Modify: `static/editor/linea_tiempo.js`, `static/editor/escala.js`, `tests/js/escala.test.mjs`, `static/editor/pagina_editor.js`

**Interfaces:**
- Consumes: `escala.filasVisuales`, `fondoTira`, los materiales con `picos`.
- Produces:
  - Cabecera por fila (icono + nombre: «Video», «Texto», «Imagen», «Música», «Voz», «Sonido»; ancho fijo, no se desplaza con la línea).
  - Onda de audio: cada clip de audio con `picos` dibuja barras (un `<canvas>` por clip, redibujado al cambiar zoom o recorte) a partir de `escala.barrasOnda(picos, clip, pps, alto) -> [{x, alto}]` (pura, probada: respeta el recorte del clip y la escala).
  - `LineaTiempo.puntoEn(clientX, clientY) -> {pistaId|null, tipo, tMs, indicePrincipal}` (para soltar desde la biblioteca: sobre la fila del video da el índice de inserción; sobre otra fila, el tiempo; fuera, `null`) y un resaltado de la fila bajo el dedo mientras se arrastra (`resaltar(punto|null)`).
  - «Cortar» de la barra corta el clip seleccionado en el cabezal (`cortarClip`) o, sin selección, la principal (`cortarEn`); «Borrar»/«Duplicar» sobre la selección; zoom con el deslizador de la barra de herramientas y con Ctrl/Cmd+rueda.
- [ ] **Step 1:** Pruebas Node de `barrasOnda` y de cualquier otra ayuda pura nueva (p. ej. la fila bajo un `y`).
- [ ] **Step 2: Implementar.** **Step 3:** Node + suite; commit `Editor capa 4b (5/9): línea de tiempo con cabeceras, onda y soltar desde la biblioteca`.

---

### Task 6: La biblioteca (panel izquierdo)

**Files:**
- Create: `static/editor/biblioteca.js`
- Modify: `static/editor/pagina_editor.js`, `templates/editor.html` (solo si falta algún contenedor), `tests/js/modulos_navegador.test.mjs`

**Interfaces:**
- Consumes: `urls.biblioteca/subir/agregar_pieza/materiales_por_id`; `editor` de la tarea 4; `LineaTiempo.puntoEn/resaltar`; operaciones `agregarVideo/agregarImagen/agregarAudio/agregarTexto/ponerTransicion`.
- Produces: `class Biblioteca({contenedor, pestanas, urls, editor, linea})` con cuatro paneles:
  - **Medios**: botón «Subir» (input de archivos múltiple; cada archivo sube con `XMLHttpRequest` mostrando su barra de progreso y su error en llano), cuadrícula de videos e imágenes del proyecto (miniatura: primera celda de la tira o el propio video con `#t=0.1`; duración), y debajo «Videos de Crear» (las piezas listas; tocar «+» en una que aún no es material la prepara y muestra «Preparando…» sondeando la biblioteca cada 3 s hasta tenerla, luego la agrega sola). En cada miniatura: «+» agrega (video → después del clip bajo el cabezal; imagen → capa en el cabezal) y se puede arrastrar a la línea de tiempo (video a la fila del video = en ese lugar; imagen a cualquier fila = capa en ese tiempo).
  - **Audio**: «Subir audio», la lista de audios del proyecto (subidos y canciones de Mi música, con su nombre y duración) con «+» (música desde el cabezal) y arrastre.
  - **Texto**: cuatro tarjetas de muestra («Título», «Subtítulo», «Precio», «Llamado») que se ven con su estilo; tocar o arrastrar agrega el texto en el cabezal y lo deja seleccionado con el campo de texto enfocado en propiedades.
  - **Transiciones**: «Corte», «Fundido», «Deslizar», «Zoom», «Fundido a negro»; se aplica al corte más cercano al cabezal en la principal (o al clip de video seleccionado) con 500 ms; la unión con transición se marca en la línea de tiempo.
  - Todo material nuevo entra a la vista previa con `editor.agregarMateriales` antes de operar.
- [ ] **Step 1:** Si surge lógica pura (p. ej. qué clip está «bajo el cabezal» para insertar después, o el corte más cercano), va a `escala.js`/`operaciones.js` con prueba Node.
- [ ] **Step 2: Implementar.** **Step 3:** Node + suite; commit `Editor capa 4b (6/9): la biblioteca — subir, agregar y arrastrar`.

---

### Task 7: El panel de propiedades (derecha)

**Files:**
- Create: `static/editor/propiedades.js`
- Modify: `static/editor/pagina_editor.js`, `tests/js/modulos_navegador.test.mjs`

**Interfaces:**
- Consumes: `editor.seleccion/doc/operar`; operaciones `editarTexto/cambiar/volumenSonido/cambiarVelocidad/ponerTransicion`; `Historial` con `clave`.
- Produces: `class Propiedades({contenedor, editor})` que se redibuja al cambiar la selección o el documento, con formularios por tipo:
  - **Video (principal)**: Velocidad (0,5×–2×), Volumen del sonido (0–100 %, deslizador), Zoom lento (Ninguno · Acercar · Alejar), Transición al siguiente (lista + duración 200–1500 ms), Borrar.
  - **Texto**: Texto (área de texto; se aplica al escribir con clave de fusión), Fuente (las 3, cada una escrita con su letra), Tamaño (deslizador), Color (paleta: blanco, negro, color de marca `doc.marca.color`, amarillo, rojo + selector libre), Contorno (sí/no, color, grosor), Sombra (sí/no), Fondo (Ninguno · Píldora · Caja, color, opacidad), Alineación (izquierda · centro · derecha), Animación de entrada (Ninguna · Deslizar), Posición («Centrar» horizontal/vertical), Borrar.
  - **Imagen**: Tamaño (deslizador de escala), Opacidad, «Llenar la pantalla», «Centrar», Borrar.
  - **Audio (música/efecto/voz)**: Volumen, Fundido de entrada, Fundido de salida, Silenciar (volumen 0 / volver al anterior), Borrar. Voz con `por_destino`: sin recorte (ya bloqueado) y el aviso «La voz se ajusta sola a cada país».
  - **Nada elegido**: el documento — Mezcla (Equilibrada · Voz primero · Ambiente primero → `doc.mezcla.preset`) y el aviso de qué hacer.
  - Cada control con etiqueta visible; deslizadores aplican al moverse con `clave` = `"<clipId>:<campo>"`.
- [ ] **Step 1:** Si hace falta una operación pura más (p. ej. `cambiarMezcla`), se agrega a `operaciones.js` con prueba y caso en `salida_operaciones.mjs`.
- [ ] **Step 2: Implementar.** **Step 3:** Node + suite; commit `Editor capa 4b (7/9): el panel de propiedades`.

---

### Task 8: Tocar, mover y agrandar sobre el reproductor

**Files:**
- Create: `static/editor/lienzo_interaccion.js`
- Modify: `static/editor/pagina_editor.js`, `templates/editor.html` (capa `#ed-interaccion` sobre el lienzo, si no quedó en la tarea 4)

**Interfaces:**
- Consumes: `seleccion.js` (tarea 3), `editor`, las medidas de los PNG de texto que ya calcula la vista previa (exponer `VistaPrevia.medidasTexto()` si hace falta).
- Produces: `class InteraccionLienzo({escenario, lienzo, editor, vista})`: una capa DOM transparente del tamaño del lienzo mostrado; tocar selecciona la capa de arriba bajo el dedo (y en la línea de tiempo); la seleccionada muestra su caja con una asa de esquina; arrastrar la caja mueve (`cambiar(transform.x/y)` con clave de fusión, guías de centro visibles mientras se pega); arrastrar el asa agranda/achica (`transform.escala`); doble toque en un texto enfoca su campo en propiedades; mientras se arrastra se pausa la reproducción; la caja sigue a la capa cuando corre el tiempo o cambia el documento, y desaparece si la capa no está activa en ese instante.
- [ ] **Step 1:** La lógica va a `seleccion.js` (tarea 3); aquí solo DOM y eventos.
- [ ] **Step 2: Implementar.** **Step 3:** Node + suite; commit `Editor capa 4b (8/9): tocar, mover y agrandar sobre el video`.

---

### Task 9: En Final edition, «Editar» primero; lo automático con IA aparte

**Files:**
- Modify: `templates/_tab_final.html`, `dashboard.py` (lo que la pestaña necesite: la edición más reciente de cada pieza), `tests/test_tab_final.py`

**Interfaces:**
- Consumes: `ediciones.listar(cliente, cf_id)`, `editor.desde_clon`.
- Produces: en la tarjeta/detalle de cada video listo, el botón principal «Editar»: si la pieza ya tiene una edición, abre la más reciente (`/cliente/<c>/ediciones/<id>`); si no, la crea (el `desde_clon` de siempre, con su barra) y, al terminar, la página abre el editor sola. «Empezar otra edición desde el video» queda como enlace secundario. Todo el bloque de guion con IA (ángulo, precio, idioma, «Preparar guion con IA», «Producir finales» automático) pasa a un `<details>` cerrado «Automático con IA (opcional)» debajo, sin cambiar sus rutas ni su comportamiento; las finales hechas siguen visibles como hoy.
- [ ] **Step 1:** Pruebas pytest: el botón «Editar» aparece primero y enlaza a la edición existente o al formulario de `desde_clon`; el bloque de IA está dentro de un `<details>` sin `open`; las rutas `fe_*` siguen presentes.
- [ ] **Step 2: Implementar.** **Step 3:** suite; commit `Editor capa 4b (9/9): en Final edition, Editar primero y lo automático aparte`.

---

### Cierre (controlador)

Prueba de punta a punta en el navegador integrado con el lanzador local (sin llaves; medios y salidas en carpeta temporal; R2 parchado a una copia local; un hilo que corre solo tareas gratis): subir un video y una foto, agregar el video de Crear, poner varios videos seguidos con transición, cortar, agregar texto y moverlo/agrandarlo en el reproductor, cambiar su color y fuente, agregar música y bajarle el volumen, deshacer, producir y mirar el video que sale; en celular, que las hojas abren y nada desborda. Documentación: párrafo del Editor en `CLAUDE.md` (capa 4b) y estado en el §2 del spec. Revisión final, una tanda de arreglos, fusión a main y despliegue.
