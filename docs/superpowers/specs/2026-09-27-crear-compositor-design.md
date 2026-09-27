# Crear: el formulario como compositor (mejora visual, parte 3b)

Fecha: 2026-09-27. Pedido por Daniel («mejorar toda esta experiencia visual de la parte de
Crear»). Dirección elegida con maquetas en el navegador: **B · compositor al centro**, frente a
A (dos columnas) y C (pasos numerados).

## 1. Problema

El formulario de «Desde referencias» (`templates/_tab_creativeflowplus.html`, hasta el cierre de
`#form-flowplus`) es una columna larga. Daniel marcó los cuatro problemas:

1. **Largo y desordenado.** Hay cinco avisos grises sueltos, dos párrafos y una lista de
   introducción, y ningún orden visible.
2. **No se ve premium.** Tiene radios y selects sin estilo, y el botón del catálogo es pequeño.
   Parece un formulario de administración.
3. **Lo importante se pierde.** La idea y las referencias no son el centro, y el precio y
   «Generar» quedan al fondo.
4. **Demasiadas opciones a la vista.** Sonido, música, Mi música, borrador y formato están
   siempre abiertos, aunque casi siempre se dejan igual.

Además hay un **riesgo de gasto**: Enter en un campo de una línea del formulario (por ejemplo,
«Sonido de la escena» o «Empieza en el segundo») hace el envío implícito del navegador con el
primer botón de envío, `#fp-generar` (`modo_prompt=directo`). Eso lanza y cobra un video. Es el
mismo tipo de fallo que el modal «Traer referentes» (incidente del 2026-09-27).

## 2. Alcance

**Dentro:** solo el formulario del modo «Desde referencias» de Crear. Incluye:

- la bandeja de referencias (`_flowplus_bandeja.html`);
- el selector del catálogo en modo `checkbox`;
- el panel Mi música (`_mi_musica.html`);
- el JavaScript del formulario (el tercer `<script>` de `_tab_creativeflowplus.html`);
- un bloque nuevo de CSS al final de `static/style.css`.

**Fuera:**

- la lista «Generados» y su detalle;
- los modos «Cambiar producto» y «Flow Plus»;
- Python: rutas, `creative_flow`, precios, modelos (no cambia nada);
- `_selector_productos.html` en modo `radio`, que usa «Cambiar producto» (debe quedar igual).

## 3. Lo que NO puede cambiar (contrato)

1. **Mismos campos hacia el servidor.** `POST cf_crear_video` recibe exactamente los mismos
   `name` y valores que hoy: `bandeja_vista`, `ref_ids` (desde la bandeja, con
   `form="form-flowplus"`), `productos_catalogo`, `accion_central`, `tipo`, `modelo_video`,
   `modelo_imagen`, `modelo` (oculto), `duracion_objetivo`, `aspect_ratio`,
   `aspect_ratio_imagen`, `con_sonido`, `sonido`, `musica_estilo`, `musica_inicio_s`,
   `calidad` y `modo_prompt` (`directo` | `director`). Cero cambios en `dashboard.py`.
2. **El texto de la persona va tal cual.** No se agrega nada al prompt (regla del
   incidente del 2026-09-26, CLAUDE.md › «Crear (FlowPlus)»). «Crear super prompt con IA (gratis)»
   sigue siendo opcional y nunca obligatorio (incidente del 2026-09-21).
3. **Mismo precio.** Se usa la misma fórmula del `refrescar()` actual: segundos × USD/s
   efectivo, menos el recargo si se apaga el sonido, 480p de Wan a 0,05, y + 0,02 por un estilo
   de música de IA. El precio siempre se ve junto a «Generar» antes de hacer clic.
4. **Mismas reglas por modelo.** Lo que el modelo no admite (duración fuera de
   `min/max_duracion`, formatos fuera de `formatos` o `formatos_texto`) no se puede elegir.
   Seedance con una imagen de arranque sigue el formato de esa imagen. El borrador es solo de
   Wan 3.0 en video. En Imagen desaparecen duración, sonido, música, borrador y «Crear super
   prompt con IA».
5. **Sin recargas.** Siguen funcionando igual: subir con barra de progreso, pegar link (y el
   sondeo mientras se descarga), quitar y vaciar referencias, «Describir con IA», «Sugerir»
   sonido, Mi música (subir, crear con ElevenLabs, borrar, reproductor + «Empieza en el
   segundo»), el prellenado de «Editar y crear otra» (`fp_prefill`) y la validación de texto
   vacío.
6. **Nada se genera sin el clic en «Generar».** Enter en cualquier `input` de
   `#form-flowplus` NO envía. En el `textarea` Enter es salto de línea, como siempre. El link se
   sigue agregando con Enter, porque va en su propio formulario (`#fp-form-link`) y no gasta.

## 4. Diseño

### 4.1 Estructura

```
.crear-comp  (div, la tarjeta visual)
├─ #fp-bandeja-wrap             ← FUERA de #form-flowplus: tiene sus propios <form> (quitar, vaciar)
│   └─ miniaturas @Imagen N / @Video N + «Describir con IA» · «Quitar todas»
├─ #fp-catalogo-elegidos        ← miniaturas de lo marcado en el catálogo (JS, desde los checkbox), con ×
└─ <form id="form-flowplus">
    ├─ .crear-comp-abajo (la mitad de abajo de la tarjeta)
    │   ├─ textarea accion_central (grande, sin borde, placeholder de ejemplo) + #fp-texto-error
    │   └─ .crear-barra
    │       ├─ «+» → menú: Subir · Pegar un link · Del catálogo
    │       ├─ pastillas: Tipo · Modelo · Duración · Formato · Sonido · Música
    │       └─ precio (#fp-precio) + «Generar video|imagen» (#fp-generar, modo_prompt=directo)
    ├─ .crear-pie (debajo de la tarjeta, todavía dentro del form):
    │     «Tu texto va tal cual al modelo · [logos] · se cobra al generar»
    │     + #fp-armar (submit, modo_prompt=director, «Crear super prompt con IA (gratis)», oculto en Imagen)
    └─ <dialog id="fp-catalogo"> con el selector del catálogo (checkbox dentro del form)
<form id="fp-form-subir"> y <form id="fp-form-link"> vacíos, fuera de todo;
sus controles viven en el menú «+» con form="fp-form-subir" / form="fp-form-link".
```

HTML no permite formularios anidados. Por eso la bandeja (que lleva formularios) queda fuera de
`#form-flowplus` dentro de la misma tarjeta, y los controles de subir o pegar un link se asocian
a su formulario con el atributo `form=`. La bandeja ya usa este patrón para `ref_ids`.

### 4.2 Pastillas y menús

- Cada pastilla es un `<button type="button" class="crear-pill" aria-expanded>`. Muestra lo
  elegido: «🎬 Video», «Wan 3.0» o «Wan 3.0 · borrador», «⏱ 8 s», «▯ 9:16» o «▯ Formato de la
  imagen», «🔊 Sonido» / «🔇 Sin sonido» / «🔊 risas y pasos…», «🎵 Sin música» / «🎵 alegre» /
  «🎵 Verano».
- Cada pastilla abre su `.crear-menu`. Solo hay un menú abierto a la vez. Se cierra con un clic
  fuera, con Escape o al elegir en los menús de una sola opción (tipo, modelo, duración,
  formato). Los menús de sonido y música se quedan abiertos mientras se edita.
- **Los controles reales viven dentro de los menús.** Así el JavaScript existente sigue leyendo
  los mismos elementos:
  - **Tipo:** los radios `tipo`, con estilo de lista.
  - **Modelo:** los radios `modelo_video` / `modelo_imagen`, como tarjetas con nombre, límites y
    precio por segundo. Debajo va el interruptor **Borrador a 480p** (checkbox `calidad`),
    visible solo con Wan 3.0 en video. Al final, la nota «Precios con el sonido de la escena
    incluido».
  - **Duración y formato:** los `<select>` actuales (`#fp-duracion`, `#fp-formato-video`,
    `#fp-formato-imagen`) siguen en el DOM, ocultos, y siguen siendo la fuente de verdad. El menú
    dibuja una ficha por cada `<option>`: la deshabilitada sale tachada y no se puede tocar, y al
    tocar una ficha se asigna el `select` y se dispara `change`. `limitarSelect` no cambia. Los
    avisos `#fp-duracion-larga` (> 15 s) y `#fp-duracion-nota` (videos de referencia con Wan)
    viven dentro del menú. `#fp-formato-nota` se ve cuando el formato sigue a la imagen, y
    entonces la pastilla dice «Formato de la imagen».
  - **Sonido:** el checkbox `con_sonido` como interruptor, el campo `sonido`, «Sugerir» y la nota
    «Vacío = ambiente natural de la escena».
  - **Música:** el `<select>` `#fp-musica` actual se queda como fuente de verdad, oculto. El
    menú muestra «Sin música», los estilos de IA como fichas (con «US$ 0,02 la primera vez») y
    «Mi música» (gratis) como lista de canciones. Al elegir una canción propia aparece
    `#fp-musica-inicio-wrap` (reproductor + «Empieza en el segundo» + «Usar donde va»). Debajo
    va `#mm-wrap` (subir canción, crear con ElevenLabs, lista para borrar).
- Las etiquetas de las pastillas las escribe `pintarPastillas()`, que corre al final de
  `refrescar()` y después de cada cambio de sonido o música.

### 4.3 El «+» y el catálogo

- El menú «+» tiene tres entradas:
  - **Subir imágenes o videos:** un `<label>` que envuelve el `input[type=file]`
    `#fp-input-archivos` con `form="fp-form-subir"`.
  - **Pegar un link:** despliega en el mismo menú el campo y «Agregar», con
    `form="fp-form-link"`.
  - **Del catálogo (N):** abre `<dialog id="fp-catalogo">` con buscador, «+ Nuevo producto» y la
    grilla por categorías.
- **Arrastrar y soltar** archivos sobre `.crear-comp` los pone en `#fp-input-archivos` (con
  `DataTransfer`) y dispara `change`. La subida sigue siendo el `XMLHttpRequest` actual, con la
  barra `#fp-subida` dentro de la tarjeta.
- El selector del catálogo gana un modo de presentación `sel_dialogo=True`: el mismo contenido
  dentro de un `<dialog>` en vez de `<details>`. Sin ese parámetro, el modo `radio` de «Cambiar
  producto» queda idéntico.
- Lo marcado en el catálogo se ve como miniatura en la tarjeta (imagen y nombre del `label`), y
  su × desmarca el checkbox. Al cerrar el diálogo se llama a `refrescar()`, porque marcar un
  catálogo cambia `sinAdjuntos()` y con eso los formatos de Seedance.

### 4.4 Adónde van los avisos de hoy

| Hoy (suelto) | Después |
|---|---|
| Introducción: dos párrafos y la lista «Dos caminos» | Se quita. La cabecera de Crear ya lo dice, y el pie de la tarjeta resume |
| «Una pieza por clic… sin referencias… tal cual» | Pie: «Tu texto va tal cual al modelo» |
| Logos oficiales (hay / no hay) | Pie, solo si hay referencias o catálogo: «se adjuntan tus N logos oficiales», o «sin logo oficial · súbelo en FlowSettings» |
| Nota de referencias (tokens, links de TrendTrack…) | Subtítulos de las entradas del menú «+» |
| Duración > 15 s / videos de referencia con Wan | Dentro del menú de duración, solo cuando aplica |
| Formato que sigue a la imagen | Dentro del menú de formato, y en la pastilla |
| Sonido nativo / música: USD 0,02 / licencias | Dentro de sus menús |
| «Borrador a 480p (solo Wan 3.0…)» | Interruptor dentro del menú de modelo |
| `#fp-ayuda-boton` | Pie: «se cobra al generar» |

Las fichas `@Imagen N` / `@Video N` (`#fp-etiquetas`) siguen encima del texto y siguen
insertando la etiqueta en el cursor.

### 4.5 Celular (≤ 760 px, las reglas de `test_movil.py`)

- La tarjeta ocupa todo el ancho.
- Las pastillas van en una sola fila que se desliza de lado dentro de la barra
  (`overflow-x: auto`). La página nunca se desliza de lado.
- Debajo de las pastillas va una fila con el precio a la izquierda y «Generar» estirado al resto del ancho.
- Los menús se abren como hoja desde abajo (`position: fixed; bottom: 0`), con fondo oscuro, y
  se cierran tocando el fondo.

### 4.6 Enter

Un `keydown` en `#form-flowplus`: Enter en un `INPUT` cuyo dueño es el formulario de Crear
(`input.form === #form-flowplus`) hace `preventDefault()`. En el `TEXTAREA`, Enter es salto de
línea. El campo del link vive en el menú «+», pero su dueño es `#fp-form-link`, así que se sigue
agregando con Enter (no gasta). El input de Mi música `#mm-prompt` queda cubierto: su dueño es
`#form-flowplus` y Enter ahí no envía nada.

### 4.7 Estilo

Todo el estilo nuevo va en un bloque «Crear: compositor (2026-09-27)» al final de
`static/style.css`. Usa los tokens existentes (`--panel`, `--panel-2`, `--border`,
`--accent-grad`, `--accent-texto`, `--warn`, `--radius*`) y el modo oscuro único. El HTML nuevo
no lleva `style=""` en línea. Pasa la guardia de colores del modo oscuro y la base visual común
(`tests/test_base_visual.py`).

## 5. Pruebas

- **Nuevas (`tests/test_crear_compositor.py`)**, sobre el HTML de `/cliente/acme` con la sesión
  de admin de las pruebas de rutas:
  - todos los `name` del contrato (§3.1) siguen dentro de `#form-flowplus`, o asociados con
    `form="form-flowplus"`;
  - ningún `<form>` anidado dentro de `#form-flowplus`;
  - los controles de subir o pegar un link llevan `form="fp-form-subir"` / `form="fp-form-link"`;
  - existen las seis pastillas y el menú «+»;
  - `#fp-armar` es `type=submit` y `value="director"`, dentro de `#form-flowplus` y después de `#fp-generar`;
  - no quedan los avisos sueltos de §4.4 fuera de sus menús o del pie;
  - el guardián de Enter está en el script;
  - el selector en modo `radio` («Cambiar producto») sigue siendo `<details>`.
- **Existentes:** se ajustan solo las que miran marcado que cambia a propósito
  (`test_bandeja_lo_que_ves.py`, `test_detalles_visuales.py`, `test_rutas_crear_director.py`,
  `test_rutas_final_edition.py`, `test_movil.py`, `test_base_visual.py`). La suite completa en
  verde.
- **En el navegador**, con la app local sin llaves (base temporal, sesión de admin sembrada):
  - cada menú abre y cierra (clic fuera, Escape);
  - al cambiar de modelo, la duración y el formato tachan lo que no admite, y el precio coincide
    con la fórmula;
  - en Imagen desaparece lo de video;
  - marcar del catálogo muestra la miniatura;
  - con el texto vacío no se envía y se ve el error;
  - Enter en «sonido» no envía;
  - el prellenado de «Editar y crear otra» funciona;
  - a 375 px la página no se desliza de lado;
  - la captura final se compara con la maqueta aprobada.

## 6. Entrega

Rama `crear-compositor` (worktree). Se mezcla a `main` y se despliega con el OK de Daniel.
Como es solo plantillas y CSS, se reinicia solo el servicio web `iaplusyou`.
