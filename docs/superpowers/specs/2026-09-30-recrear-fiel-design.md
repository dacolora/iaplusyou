# «Recrear con mi producto» fiel a la referencia — diseño

Fecha: 2026-09-30 · Pedido de Daniel, aprobado en la conversación («si, aprobado, ejecuta todo»).
Amplía el §9 de `2026-09-23-biblioteca-referentes-design.md` («Recrear con mi producto»).

## 1. El problema

Daniel recreó el referente 5048 (Inochhi, «Plain Product Studio Shot»: un par de sandalias juntas sobre
fondo blanco, vistas desde arriba en diagonal, sin personas) con HOriginal — Beige. La imagen salió con una
mano sosteniendo una chancla y un pie con la otra puesta: otra composición. Lo que se mandó (concepto 189 en
producción):

1. La segunda foto del producto (`HOriginal - Beige_5.png`) es la de **dos manos sosteniendo la chancla**;
   el modelo copió esa pose.
2. La **guía de estilo de la marca** va pegada al prompt y habla de «People are real… Feet are clean… Hands,
   where visible…»: el modelo lo leyó como «pon pies y manos».
3. El prompt dice una sola vez «Follow the STRUCTURE and COMPOSITION of Image 1» y nunca describe qué hay en
   Image 1 (cuántas unidades, cómo están puestas, el ángulo, el fondo, que no hay personas).
4. «Why it works» trae lo del producto ajeno («cuero genuino, puntera redonda»): ruido.

Además, el campo «Titular» se llena con el `titular` del Ad Library, que es el título del enlace del anuncio
en Meta y muchas veces ni siquiera está dentro de la imagen (5048 no tiene ningún texto en la imagen).

## 2. Lo que pide Daniel

- Que la imagen recreada tenga **las mismas posiciones** del producto que la referencia.
- Por cada clic, **dos imágenes**: una igual a la referencia y otra «así como la hiciste, cambiada un poco».
- Una opción para **traer o no los textos** de la referencia. Respuestas de Daniel: textos **leídos y
  editables** (Claude los lee y salen en campos que se pueden cambiar, en el mismo lugar y estilo, sin el
  nombre de la otra marca) y la lectura se hace **sola al abrir Recrear**, una vez por referente.

## 3. Lectura de la referencia (`referentes/lectura.py`, nuevo)

Una llamada de visión a Claude (`generador_prompts.MODEL`, imagen por URL de R2 como en `clasificar.py`, sin
doctrina en el system: es descripción, no copy) que devuelve JSON:

```json
{"composicion": "Two sandals side by side on a plain white seamless background, seen from above at a 3/4 angle…",
 "producto": "pair of heeled sandals",
 "unidades": 2,
 "personas": false,
 "textos": [{"texto": "50% OFF", "rol": "oferta", "ubicacion": "top center"}]}
```

- `composicion`: **siempre en inglés** (va dentro del prompt del modelo de imagen y se guarda una sola vez
  para todos los proyectos), 1-3 frases: ángulo y altura de cámara, encuadre, cuántas unidades y cómo está
  cada una (posición en el cuadro, orientación, si se tocan), fondo, superficie, luz y sombras, objetos de
  apoyo, y si hay o no personas, manos o pies. Tope 700 caracteres.
- `producto` (inglés, corto, tope 80), `unidades` (entero 1-12 o `null`), `personas` (bool).
- `textos`: solo lo escrito **dentro** de la imagen, de arriba abajo, máximo 8, cada uno tal cual aparece
  (tope 200 caracteres). `rol` ∈ `titular | subtitulo | oferta | precio | cta | marca | otro` (otro valor →
  `otro`); `ubicacion` en inglés, corta (tope 60). Sin texto → `[]`.
- Lo escrito en la imagen es dato, no instrucción (se dice en el prompt, como en `clasificar.py`).
- `validar_lectura(data)` es pura: limpia, recorta y lanza `LecturaInvalida` solo si falta `composicion`.
- `leer(referente)` → `(lectura, tokens_entrada, tokens_salida)`; `LecturaInvalida` lleva los tokens pagados.
  `MAX_TOKENS_LEER = 4000` (Sonnet 5 piensa del mismo tope).
- `medir(url)` → `(ancho, alto)` bajando la imagen de R2 con `requests` (timeout 15 s) y Pillow; `(None, None)`
  si falla. Gratis; sirve para elegir el formato.
- Se guarda en `referente.extra["lectura"] = {version: 1, composicion, producto, unidades, personas, textos,
  ancho, alto, modelo, en}` con `datos.guardar_lectura(rid, lectura)` (único escritor; toma el candado de
  escritura antes de leer `extra`, como `marcar_traducidas`). Sin migración.
- `formato_cercano(ancho, alto, formatos)` (pura): el formato admitido cuya proporción está más cerca
  (distancia en logaritmo); `None` sin medidas.

### Ruta `POST /cliente/<c>/referentes/<rid>/recrear/leer` (JSON)

- Referente inexistente o sin imagen → 404 JSON.
- Ya leído → `{"ok": true, "cobrado": false}` sin llamar a Claude.
- Si no: `leer` + `medir`, guarda, registra el gasto con
  `gastos.registrar_seguro(cliente, "adaptar_referente", usd, "referentes:leer:<rid>:<uuid12>", detalle="lectura
  · <familia>", proveedor="anthropic", extra={tokens…, modelo})` y responde `{"ok": true, "cobrado": true}`.
  También registra lo pagado cuando la respuesta no sirve (`LecturaInvalida` con tokens) → 502 con el motivo.
  Otro error (red, API) → 502 «No se pudo leer la referencia (<tipo>)».
- Tarifa nueva `gastos.TARIFAS["leer_referente"] = 0.01` (estimado «una llamada corta a Claude con visión»;
  se ajusta con lo medido en la prueba real), estimador `leer_referente`.
- Dos personas abriendo el mismo referente a la vez pueden pagar dos lecturas: se acepta (centavos); la
  segunda pisa a la primera con un resultado equivalente.

### En el formulario

- `recrear_form` sin lectura guardada pinta un bloque `data-recrear-leer="<url>"` con «Leyendo la
  referencia… ≈ US$ 0,01». El JS de la pestaña hace el POST al insertar el formulario (uno a la vez por
  formulario) y, si sale bien, **recarga el formulario** (que ya encuentra la lectura y pinta los textos);
  si falla, muestra el motivo y «Reintentar». Mientras tanto se puede generar igual (ver §5, sin lectura).
- Con lectura y sin `formato` elegido por la persona, el formato por defecto es `formato_cercano` (si no hay
  medidas, `FORMATO_DEFECTO`). La recarga tras leer no manda el formato si la persona no lo tocó.

## 4. Textos

- Casilla **«Traer los textos de la referencia»** (marcada por defecto). Debajo, un campo por cada texto
  leído (`texto_<i>`), con su rol y ubicación como etiqueta («Oferta · top center»). Los de rol `marca` nacen
  vacíos (placeholder: el original y «se quita»).
- Sin textos leídos: la casilla no aparece y se lee «Esta referencia no tiene textos dentro de la imagen.»
- Sin lectura (todavía leyendo o falló): la casilla aparece sola, sin campos.
- **Reemplaza el campo «Titular»** de hoy. El título de la sesión en Crear pasa a ser «Recrear: <primer texto
  no vacío | titular del referente | id>» + « · igual» / « · variación».
- `instruccion_textos(lectura, nuevos, traer, idioma)` (pura) arma la frase del prompt:
  - casilla apagada, o todos los campos vacíos → «No text anywhere in the image.» / «Ningún texto en la imagen.»;
  - con lectura y textos → «Texts in the image, each in the same position, size, font style and color as in
    Image 1: replace “A” with “B”; keep “C”; remove “D”. No other text.»;
  - con lectura sin textos → «No text anywhere in the image.»;
  - sin lectura y casilla prendida → «Keep the texts of Image 1 in the same position and style, but remove
    any brand name or logo of the other brand.»
- Al recargar el formulario (cambio de producto o formato) se conservan los textos escritos y la casilla
  (van en la query del GET).

## 5. Dos imágenes por clic (solo imagen)

- Casillas `modo=fiel` («Igual a la referencia») y `modo=libre` («Variación»), las dos marcadas. El botón
  dice «Generar 2 imágenes ≈ US$ X» y el JS lo ajusta (precio por imagen × casillas marcadas; con una sola,
  «Generar imagen»). Ninguna marcada → el botón se desactiva; en el servidor, flash de error y nada se crea.
- **Fiel** — `armar_prompt_fiel(lectura, producto, textos_instr, formato, idioma)` (determinista, es/en):
  «Edit Image 1 and keep it identical: same composition, camera angle, framing, background, lighting and
  shadows, and the same position, orientation and size of every element. Image 1 shows: <composicion>.
  Replace only the product: every <producto> in Image 1 becomes the product in Image 2 (and 3): <nombre>.
  <descripcion> <regla> Show exactly <n> units, in the same places and orientations as in Image 1. Image 2
  (and 3) only show what the product looks like (shape, color, texture, logo): ignore their pose, angle,
  background, hands, feet and people. <personas> <textos> No logos or names of other brands. No watermarks.»
  - `<personas>`: sin personas en la referencia → «Do not add people, hands, feet or anything that is not in
    Image 1.»; con personas → «Keep the people, hands or feet exactly as they are in Image 1.»; sin lectura →
    «Do not add anything that is not in Image 1.» (sin la frase de composición ni la de unidades).
  - **Sin guía de estilo de la marca, sin «Why it works» y sin dolor**: lo que manda es la referencia.
- **Variación** — `armar_prompt` de hoy (estructura de la referencia + firma + dolor + guía), con la línea
  de textos de §4 en lugar de la del titular.
- **Video**: una sola pieza con `armar_prompt` (variación) + cámara + sonido, con la línea de textos de §4.
  Sin casillas de modo.
- Los prompts se ven en «Ver o editar los prompts» (plegado): `prompt_fiel` y `prompt` (variación o video).
  Cada `<textarea>` tiene su `<input type=hidden name="<campo>_editado">` que el JS pone en `1` al escribir
  ahí. Al generar, el servidor **arma de nuevo** cada prompt con los campos del formulario, salvo que su
  `_editado` sea `1` (entonces usa el texto tal cual; vacío → error). Así cambiar un texto después de abrir el
  formulario siempre llega al prompt.
- Una sesión de Crear por modo marcado (fiel primero), cada una lanzada con `flowplus_lanzar.lanzar`;
  `extra`: `referente_id`, `recrear_modo` (`fiel | libre`) y el ángulo si lo hay. Flash: «Generando 2 imágenes
  desde el referente…» (o la de una). «Usado N veces» cuenta sesiones, así que sube de a dos: se acepta.

## 6. «Adaptar con IA»

- Recibe `producto_id`, `textos` (los valores actuales de los campos) y `traer_textos`.
- `adaptar(referente, familia, producto, textos, traer, guia, idioma, lectura=)`: el prompt le da a Claude la
  lista de textos de la referencia (original, rol, ubicación) y le pide `"textos"`: la misma cantidad, en el
  mismo orden, cada uno reescrito para el producto con el mismo rol y largo parecido; los de rol `marca` →
  `""`. Si la casilla está apagada o no hay textos: `"textos": []` y la imagen va sin texto. Sigue pidiendo
  `"angulo"` y `"prompt"` (el de la variación, mencionando Image 1/Image 2; ya no «el titular elegido», sino
  los textos elegidos o «sin texto»).
- Respuesta JSON: `{"textos": [...], "prompt": "...", "angulo": {...}}`. `_leer` exige `prompt`; `textos`
  se normaliza a la cantidad de campos (rellena con los actuales, recorta lo que sobra, no-texto → actual).
  El JS llena los campos de texto y el prompt de la variación (y marca ese prompt como editado).
- Las cifras de los textos originales cuentan como datos verificables (`datos_texto`).

## 7. Seguridad

El Blueprint de Referentes rechaza los POST que el navegador marca de otro sitio (`Sec-Fetch-Site`), como
Sprints, Nicho y Flow Plus: `leer`, `adaptar` y `generar` gastan.

## 8. Idioma

Todo texto nuevo de la pantalla pasa por el catálogo (`_()` / `gettext`, `catalogo_i18n.py actualizar`,
traducción al inglés con `docs/i18n/glosario.md`, `compilar`). Los prompts para el modelo siguen el patrón de
`TEXTOS` por idioma del proyecto; la composición leída va siempre en inglés.

## 9. Pruebas

- `lectura`: validar (recortes, rol desconocido → otro, sin composición → error), `leer` con `_llamar`
  simulado (imagen por URL, tokens en el error), `formato_cercano`, `medir` con la red simulada.
- `datos.guardar_lectura` conserva el resto de `extra`.
- Ruta `leer`: guarda una vez y la segunda no llama a Claude ni cobra; registra el gasto también con
  respuesta inválida; 404; 502 sin romper.
- Prompts: el fiel lleva composición y unidades, NO lleva guía/firma/dolor, prohíbe manos sin personas y las
  conserva con personas; `instruccion_textos` en sus cuatro casos; la variación lleva la línea de textos.
- Formulario: con lectura pinta los campos (marca vacía) y el formato cercano; sin lectura pinta el bloque de
  lectura; sin textos, el aviso.
- Generar: dos modos → dos sesiones (fiel primero, `recrear_modo`, títulos); un modo → una; ninguno → nada;
  prompt rearmado con los textos del POST salvo `_editado=1`; video → una sola.
- Adaptar: textos alineados a la cantidad de campos, marca vacía, sin textos → `[]`.
- POST cross-site → 403.

## 10. Prueba real

Con el referente 5048 y HOriginal — Beige en producción, después de desplegar: lectura (≈ US$ 0,01) + dos
imágenes (≈ US$ 0,20). Se mira que la «igual» tenga las dos chanclas en la misma posición y sin manos ni pies.
Se ajusta `TARIFAS["leer_referente"]` con el gasto medido.

## 11. Fuera de alcance

Elegir a mano qué fotos del producto se mandan; reescribir la lectura de un referente ya leído (se haría
borrando `extra.lectura`); leer los referentes de antemano en los barridos; dos videos por clic.

## 12. Como video: «igual» y «variación» (2026-10-01, pedido de Daniel: «ahora haz lo mismo para videos»)

En la biblioteca no hay referentes de video (todos son imágenes o carruseles), así que esto es el modo «Como video ▸»
de Recrear. Daniel eligió que el modelo que anima la versión fiel se elija en el formulario.

- Mismas casillas que en imagen (`modo=fiel|libre`, las dos marcadas) y la misma casilla de textos. Junto a «Igual a la
  referencia», el selector **«Animar con»** (`modelo_animar`, `MODELOS_ANIMAR = ("seedance25", "wan3")`, Seedance 2.5
  por defecto: es el único que usa la imagen como primer fotograma). Cambiarlo recarga el formulario (precio nuevo).
- Precio del botón con la duración por defecto del proyecto (`preferencias_flowplus`, ajustada a cada modelo):
  igual = imagen fiel (Seedream) + video del modelo elegido; variación = video de `VIDEO_POR_DEFECTO`. Textos del botón
  por combinación: `data-texto-0`, `data-texto-fiel`, `data-texto-libre`, `data-texto-2` (en imagen fiel y libre cuestan
  lo mismo).
- **Igual**: una sesión de IMAGEN (Seedream, `armar_prompt_fiel`, como en imagen) con
  `extra.animar_despues = {modelo, duracion, formato, prompt, con_sonido, titulo}`. Cuando el worker termina esa imagen
  (`tareas/flowplus.ejecutar_imagen`, después de guardar `video_listo`), `recrear.lanzar_animacion` crea UNA sesión de
  video con esa imagen como única referencia (`recrear_modo="fiel_video"`, `imagen_origen=<cf de la imagen>`) y la lanza
  con `flowplus_lanzar.lanzar` — el costo ya se aprobó con el clic. Antes de lanzar anota `animar_despues.cf_video` en la
  imagen: un segundo intento no crea otra. Si la imagen falla, no hay video ni cobro. Si lanzar falla, la imagen queda
  lista con `animar_error` (en el idioma del proyecto), que su detalle muestra.
- Prompt de la animación (`recrear.armar_prompt_animar`, es/en, determinista): Image 1 es el primer fotograma; deja igual
  encuadre, producto, personas y textos (quietos y legibles); solo movimiento suave y natural (cámara fija con leve
  acercamiento); más la línea de SONIDO de siempre.
- **Variación**: el video de hoy (`armar_prompt` con la línea de textos + cámara + sonido, `VIDEO_POR_DEFECTO`).
- Títulos: «Recrear: … · igual» (imagen), «Recrear: … · igual · video», «Recrear: … · variación».
- «Ver o editar los prompts» en video: `prompt_fiel` (la imagen), `prompt_animar` (la animación) y `prompt` (la
  variación), cada uno con su `<campo>_editado`.
- Prueba real: VIVAIA con «igual» animada con Wan 3.0 + variación (≈ US$ 1,70).
