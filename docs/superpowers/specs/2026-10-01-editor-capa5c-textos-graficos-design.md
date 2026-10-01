# Editor capa 5c — textos y gráficos que venden — diseño

Fecha: 2026-10-01. Estado: **diseño** (plan de la 5c-1: `docs/superpowers/plans/2026-10-01-editor-capa5c-textos-graficos.md`).
Base de código: `main` en e6e38a9 (capa 5b en producción). Nace de:

- spec del editor `2026-09-18-final-edition-editor-design.md` §4 («Texto: … ~20 fuentes»; «zonas seguras de
  TikTok/Reels»; «stickers»; «animaciones de texto»);
- auditoría post-4b (scratchpad `auditoria-capcut-4b.md`): bugs #3 (los emojis se ven en la vista previa y salen
  como cajas o desaparecen en la final), #8 (agrandar un texto con el asa lo deja borroso en la final), #9 (un texto
  largo se sale de la pantalla); Parte 3, ítems 1, 5 («zonas seguras, ajuste de línea y 10–15 fuentes más») y 6
  («animaciones de texto que funcionen y un paquete chico de stickers de ecommerce»);
- pedido de Daniel: «el mejor editor», al nivel de CapCut en textos y gráficos.

**La capa se parte en dos entregas** (D1). Este documento diseña la **5c-1, «textos y gráficos que venden»**, entera
(§0–§8), y deja un **esbozo de la 5c-2, «movimiento y color»** (§9) con las decisiones que ya se pueden tomar y lo que
se verificó con ffmpeg para tomarlas.

---

## 0. Qué entra y qué no

**Entra en la 5c-1**

1. **Zonas seguras**: guías sobre el reproductor con las zonas que tapan los botones y textos de TikTok, Instagram
   Reels y YouTube Shorts (9:16), y un aviso cuando un texto, un sticker, una imagen o los subtítulos caen en una
   zona, o se salen del video. Solo guías: nada se renderiza.
2. **Ajuste de línea**: los textos nuevos se parten solos a un ancho máximo (control «Ancho del texto»), los saltos
   con Enter se respetan, y la vista previa parte las líneas **exactamente** donde las parte el render.
3. **Fuentes de anuncio**: 8 fuentes nuevas (OFL) en cinco familias de estilo — clásicas, de impacto (gruesas y
   condensadas), redondeada, manuscritas y con serifa — que la página carga solo cuando hacen falta.
4. **Emojis de verdad** en los textos: una fuente de emojis a color (COLRv0) que usan los dos motores, así el emoji
   que se ve es el que sale. Los subtítulos (libass) **siguen sin emojis** (D6.6).
5. **Texto nítido a cualquier tamaño**: agrandar un texto con el asa ya no lo deja borroso (bug #8).
6. **Stickers**: un paquete propio de 20 gráficos sin palabras (flechas, marcas a mano, insignias, estrellas…),
   hechos en el repo con Pillow, de un color que se elige; 6 **plantillas de texto para vender** («OFERTA», «NUEVO»,
   «-50 %», «ENVÍO GRATIS», «¡ÚLTIMAS UNIDADES!», «MÁS VENDIDO»), editables y en el idioma de quien edita; y
   **emojis como sticker** (un texto con un emoji grande).

**Entra en la 5c-2** (esbozo en §9): animaciones de entrada y salida (las seis del documento, que hoy solo
«deslizar» renderiza), rotación de textos, imágenes y stickers (asa sobre el video y control en «Editar»),
fotogramas clave de escala y opacidad, y filtros de color en los clips de la principal (videos y fotos).

**No entra en ninguna**: plantillas de texto con efectos (curvas, degradados, «word art»), texto escrito directo
sobre el video, fuentes subidas por el cliente, GIF animados y stickers animados, banderas y emojis compuestos
completos (D6.4), emojis en los subtítulos, tocar la vía automática (`borrador.py` sigue creando textos de antes, D3),
cambiar el formato de la edición, PIP.

---

## 1. Decisiones

### D1. Dos entregas, en este orden: primero lo que se lee y vende, después lo que se mueve

Las siete cosas pedidas no caben en una entrega de ~9 tareas, y se agrupan solas por la máquina que tocan:

| Entrega | Qué | Máquina | Por qué primero / después |
|---|---|---|---|
| **5c-1** | zonas seguras, ajuste de línea, fuentes, emojis, nitidez, stickers | capas ESTÁTICAS: el PNG de texto (Pillow ↔ lienzo), las capas de imagen de siempre | Lo que hoy le cuesta ventas a un anuncio: un precio bajo los botones de Reels, una frase cortada en el borde, el «🔥 50 % OFF» que pierde el emoji en la final (rompe la confianza en el editor) y una letra genérica. La auditoría los pone 1.º y 5.º. |
| **5c-2** | animaciones (entrada y salida), rotación, keyframes de escala/opacidad, filtros | capas que CAMBIAN en el tiempo (la capa deja de ser un PNG quieto) y la cadena de la principal | El «toque CapCut»; comparte el cambio de fondo del compilador: la capa pasa a ser un flujo de cuadros (`loop` + `scale`/`rotate`/`fade` por cuadro), con su propia cuenta de memoria en los tramos. Los filtros tocan la principal: otra superficie, otra paridad. |

Rotación va en la 5c-2 aunque un sticker torcido venda: rotar es el mismo camino del compilador que animar (la capa
deja de ser una caja recta: `rotate` con alfa, la caja de selección rotada, el toque con la caja rotada) y hacerlo dos
veces sería pagar dos veces. Los stickers de la 5c-1 entran derechos; la 5c-2 los deja torcer.

### D2. Un solo motor de texto: el servidor rasteriza SIEMPRE; la vista previa lo imita con matemática compartida

Hoy el navegador nunca sube sus PNG (`pngs` se usa solo en el servidor: `grep` en `static/editor/` no encuentra a
nadie que lo escriba): **todo texto de toda final lo dibuja Pillow** (`rasterizar.png_texto`) con `static/fonts/`, y la
vista previa dibuja otro (`texto_canvas.rasterizarTexto`) con el lienzo del navegador. De ahí salen los tres bugs de
la auditoría: el emoji que el navegador pinta con la fuente del sistema y Pillow no (#3), las líneas que se parten
distinto porque cada motor mide distinto (#9), y el borroso porque el PNG se dibuja a su tamaño y se estira (#8).

| Opción | Cómo | Problema |
|---|---|---|
| A. Subir los PNG del navegador al producir | lo que se ve es lo que sale, por construcción | Un PNG por texto **y por destino** (los textos variables y el precio cambian por país) subido en cada «Producir»; la vía automática sigue sin navegador (dos motores igual); en un iPhone el emoji que sale es el de Apple, cuya licencia no permite usarlo en un anuncio de otro; y cada equipo daría otra final. |
| **B. El servidor rasteriza siempre y la vista previa usa la MISMA maqueta (elegida)** | dónde va cada letra se calcula con una tabla de avances sacada de las mismas TTF, en Python y en JS, con los mismos números | Los dos motores ponen cada letra en el mismo punto y la caja mide lo mismo; solo cambia el suavizado (±1 px por borde). El emoji sale de una fuente que el repo trae (D6) y es el mismo en todo equipo. |

Con B la tarea de «capa 5» que nunca se hizo (subir PNG desde el navegador) queda descartada: `pngs` sigue en el
contrato (lo escribe quien quiera, como hoy) y nadie lo escribe.

### D3. Texto v2 (`estilo.version: 2`): lo nuevo sale exacto; lo viejo se produce igual que antes

Medir con la tabla compartida (D4) no da los mismos números que medir con Pillow: Pillow suma avances **ajustados al
píxel** por el hinting de cada tamaño. Medido con las TTF del repo (Pillow 11.3, FreeType 2.13.3), en 40 frases de 8
a 200 px el ancho de Pillow y el de la tabla difieren en 2 (Inter Bold), 1 (Inter SemiBold) y 10 (Space Grotesk Bold)
casos, por 1–5 px. Los borradores automáticos usan `ancho_max` (`borrador.ESTILO_HOOK` 0,8889, `ESTILO_CTA` 0,6815):
cambiarles la medida podría mover un salto de línea de un anuncio que ya existe. La regla del editor (un documento
viejo valida byte a byte igual y se produce igual) manda:

- **v1** (sin `estilo.version`): exactamente lo de hoy en el render — medida de Pillow, `multiline_text`, caja por
  `multiline_textbbox`, emojis quitados (`sin_glifos_faltantes`). La vista previa mejora su paridad con lo que el
  render hace — quita lo que la fuente no tiene con `tipografia.sin_glifos_v1`, el espejo de `sin_glifos_faltantes`
  con la cobertura de la tabla — pero sigue midiendo con el lienzo, como hoy.
- **v2** (`estilo.version: 2`): la maqueta compartida (D5), los emojis (D6), la nitidez (D8).
- **Cuándo un texto es v2**: nace v2 todo texto que agrega el editor (`agregarTexto`, las plantillas para vender y los
  emojis-sticker), y PASA a v2 un texto viejo en cuanto la persona le cambia algo que se dibuja: su contenido
  (`editarTexto`), su estilo (`cambiar` con `estilo`) o su tamaño (`cambiar` con `transform.escala`). Mover o cambiar
  de tiempo no lo cambia. Un texto v1 que tiene caracteres que su fuente no trae (emojis escritos antes de esta capa)
  muestra en «Editar» el aviso y un botón «Mostrar los emojis» (`actualizarTexto`, un deshacer).
- **La vía automática no cambia** en esta capa: `borrador.py` sigue creando v1 (un borrador nuevo se produce igual
  que uno de ayer). Pasarla a v2 es una decisión aparte (riesgo 5).

### D4. La tabla tipográfica: avances y cobertura leídos de las TTF, un JSON para los dos motores

`final_edition/fuentes.py` lee cada TTF **sin dependencias nuevas** (el `venv` no tiene fontTools; Pillow no expone ni
`cmap` ni `hmtx`): un lector de ~80 líneas con `struct` para las tablas `head` (unitsPerEm), `hhea` (ascender,
descender, numberOfHMetrics), `hmtx` (avances) y `cmap` (formatos 4 y 12). Probado sobre las tres TTF de hoy:
Inter Bold 2048 u/em, ascendente 1984, descendente 494, 2857 códigos (525 latinos); Space Grotesk Bold 1000 u/em,
984/292, 731 códigos; «Hola» en Inter Bold a 100 px mide `(1530 + 1256 + 555 + 1189) × 100 / 2048 = 221,19140625`.

`fuentes.generar_tabla()` escribe `static/editor/tipografia.json` (lo sirve `static/` y lo lee Python; la página lo
recibe en `datos.config.tipografia`):

```json
{"version": 1,
 "repertorio": [[32, 591], [8192, 8303], [8352, 8399], [8448, 8527], [8592, 8703], [8704, 8959], [8960, 9215],
                [9632, 9727], [9728, 10175], [11008, 11263], [126976, 129791]],
 "fuentes": {"Inter-Bold": {"upem": 2048, "asc": 1984, "desc": 494, "avances": [[32, [485, 586, …]], [160, […]], …]}},
 "emoji": {"id": "TwemojiMozilla", "upem": …, "asc": …, "desc": …, "avances": [[…]]}}
```

- `repertorio`: los rangos que se tabulan (latín básico, Latin-1, Latin Extended-A/B, puntuación general, monedas,
  letras-símbolo, flechas, matemáticas, técnicos, figuras geométricas, símbolos varios y dingbats, flechas y figuras
  suplementarias, y los planos de emojis 1F000–1FAFF). Un carácter fuera del repertorio **no está cubierto** por
  ninguna fuente en ningún motor (se quita, D5.2): el editor es para anuncios en español, inglés y portugués.
- `avances`: por fuente, tramos de códigos consecutivos `[primer_código, [avance, …]]` en unidades de la fuente,
  solo de los códigos del repertorio que su `cmap` trae (un código ausente = la fuente no lo dibuja).
- `emoji`: la fuente de emojis (D6) o `null` si no está en el repo. Un código desde U+2190 que ella tiene va con ella
  aunque la fuente del texto también lo traiga (D5.3); uno anterior (sus dígitos, `#`, `*` para los «keycaps», © ®)
  va con la del texto.
- `tests/test_tipografia_tabla.py::test_tabla_al_dia` falla si el JSON no es lo que `generar_tabla()` da con las TTF
  del repo (como `test_casos_del_editor_al_dia`); se regenera con `venv/bin/python3 -m final_edition.fuentes`.

### D5. La maqueta v2: dónde va cada letra, con los mismos números en Python y en JS

`final_edition/tipografia.py` y `static/editor/tipografia.js` (puros, espejo; tabla de paridad
`tests/fixtures/tipografia_casos.json`) hacen, en este orden y con las mismas operaciones de coma flotante:

1. **`simplificar(texto) → (texto, simplificado)`**, recorriendo puntos de código (`for ch in texto` en Python,
   `for (const ch of texto)` en JS — los dos iteran puntos de código, no unidades UTF-16): quita los selectores de
   variante U+FE0E/U+FE0F (no cuentan como cambio visible), los modificadores de tono de piel U+1F3FB–1F3FF, el
   «keycap» U+20E3, las etiquetas U+E0020–E007F y los indicadores regionales U+1F1E6–1F1FF (las banderas); en una
   secuencia con U+200D (ZWJ) se queda con el primer pictograma y quita la unión y lo que sigue hasta el próximo
   carácter que no sea pictograma, ZWJ ni selector. `simplificado` es verdadero si quitó algo de lo anterior salvo
   los selectores (D6.4).
2. **`limpiar(texto, fuente, tabla) → {texto, quitados, simplificado}`**: tabulador → espacio; `\r\n`/`\r` → `\n`;
   simplifica; quita todo carácter que ni la fuente del texto ni la de emojis cubren (salvo espacio, U+00A0 y `\n`);
   después, en cada línea, junta espacios repetidos y quita los de los bordes (lo mismo que
   `rasterizar.sin_glifos_faltantes`). `quitados`: los caracteres quitados (para el aviso, D7.5).
3. **`fuente_de(cp, fuente, tabla)`** → `"emoji"` si `cp ≥ U+2190` y la fuente de emojis lo tiene (así «❤», que Inter
   trae como dibujo de texto de un color, sale rojo como lo escribió la persona; «→», «★» o «✓», que no son emojis,
   siguen en la fuente del texto); si no `"texto"` si la fuente del texto lo tiene; si no `"emoji"` si la de emojis
   lo tiene; si no `null` (ya se quitó en 2).
4. **`ancho(texto, fuente, tam, tabla)`** = suma, en orden, de `avance × tam / upem` de cada carácter (con la tabla de
   su fuente: la del texto o la de emojis). Sin kerning ni ligaduras en ningún motor: Pillow sin Raqm no los aplica y
   el lienzo se pone `fontKerning = "none"` y dibuja letra por letra (D5.7).
5. **`ajustar(texto, fuente, tam, ancho_max_px, tabla) → [líneas]`**: el algoritmo voraz de hoy (`ajustar_lineas`),
   pero las palabras se separan **solo por U+0020** (el espacio duro U+00A0 no parte: «50 %» o «$ 89.900» escritos
   con espacio duro quedan juntos; el `\s` de JS y el `split()` de Python no cubren los mismos caracteres, así que
   ninguno de los dos se usa) y la medida es `ancho`. Comparación `ancho(candidata) > ancho_max_px` en coma flotante,
   idéntica en los dos.
6. **`maquetar(texto, estilo, formato, tabla, factor=1) → maqueta`**: con `m = medidas_texto(estilo, formato)` (las de
   hoy: `tam`, `espaciado`, `grosor`, `sdx`, `sdy`, `padX`, `padY`, `anchoMaxPx`, `fondoAnchoPx`, `radio`, redondeo
   al par como `rasterizar._px`), `asc_px = asc × tam / upem`, `desc_px = desc × tam / upem` (de la fuente del texto),
   `paso = tam + espaciado` y los anchos `w_i` de cada línea:
   - `tw = ceil(max w_i) + 2·grosor`, `th = ceil(asc_px + desc_px + (n − 1)·paso) + 2·grosor`;
   - la caja de hoy `cajaTexto(m, tw, th)` → `ancho_px`, `alto_px`, `margen`, `cajaW`, `cajaH`, `radio`;
   - `x_i` de la línea: izquierda `margen + padX + grosor`; derecha `margen + cajaW − padX − grosor − w_i`; centro
     `margen + (cajaW − w_i) / 2`; `base_i = margen + padY + grosor + asc_px + i·paso`;
   - cada letra: `{cp, x, base, fuente: "texto"|"emoji"}` con `x` acumulando los avances desde `x_i`.
   La maqueta lleva `ancho_px`/`alto_px` (enteros: lo que `preparar_rutas` estampa y lo que `geometria.caja` coloca),
   las líneas (`texto`, `x`, `base`, `ancho`) y las letras. Los números salen iguales en los dos motores porque son
   las mismas operaciones IEEE en el mismo orden (la tabla de paridad los compara EXACTOS).
7. **Dibujo** (cada motor el suyo, sobre la maqueta): un lienzo de `ancho_px·f × alto_px·f` (`f` = `factor`, D8);
   el fondo (rectángulo redondeado de hoy, ×f); después tres pasadas por letra, cada una en el origen
   `(redondear(x·f), redondear(base·f))` (medio hacia arriba: Pillow redondea así el origen y el lienzo se lleva al
   mismo píxel) y con el tamaño `tam·f`: **sombra** (en su color, con el grosor del contorno, desplazada `sdx·f`,
   `sdy·f`), **contorno** (trazo de `2·grosor·f` en el lienzo; `stroke_width = grosor·f` en Pillow, con relleno del
   mismo color) y **relleno**. Las letras de emoji van solo en la pasada de relleno (un emoji a color no tiene
   sombra ni contorno en ningún motor: el lienzo pintaría el emoji entero en la sombra y Pillow lo ignoraría). Letra
   por letra en las tres pasadas: el contorno de la letra siguiente nunca tapa el relleno de la anterior.
   Pillow dibuja con `anchor="ls"` (izquierda, línea de base) y, en las de emoji, `embedded_color=True`; el lienzo con
   `textBaseline = "alphabetic"`, `fontKerning = "none"` y `ctx.font = "<tam·f>px \"<fuente>\""` (la de emojis:
   `"CreatvEmoji"`), sin lista de respaldo: lo que la tabla no cubre ya no está.

### D6. Emojis: una fuente a color COLRv0 que el repo trae, para los dos motores

1. **La fuente**: Twemoji Mozilla (`static/fonts/emoji/TwemojiMozilla.ttf`, 1,47 MB, COLRv0: capas de color
   vectoriales). Es el formato que dibujan los dos motores: FreeType ≥ 2.10 compone las capas COLR v0 con
   `FT_LOAD_COLOR` y Pillow las pinta con `embedded_color=True` (Pillow 11.3 / FreeType 2.13.3 en la Mac; el VPS
   instala `Pillow>=12.3.0`, con FreeType más nuevo); los navegadores dibujan COLRv0 desde una `@font-face`.
   Descartadas: Noto Color Emoji en CBDT (≈ 10 MB, mapas de bits a un solo tamaño, Safari y Firefox no los dibujan) y
   en COLRv1 (Safari no la dibuja y FreeType no la compone sola); OpenMoji (CC BY-SA: «compartir igual» sobre los
   anuncios de los clientes); la fuente del sistema del equipo (D2: cada equipo daría otra final, y la de Apple no se
   puede usar fuera de sus equipos).
2. **Licencia**: el arte de Twemoji es CC-BY 4.0 (Twitter/X) y la compilación de Mozilla, Apache-2.0. CC-BY pide
   atribución: va en `static/fonts/emoji/LICENSE.md` (el archivo del proyecto) y en una línea al pie del panel de
   emojis («Emojis: Twemoji, CC-BY 4.0»). Se le dice a Daniel al pedir el permiso (§4); si prefiere no usarla, todo lo
   demás de la capa funciona y los emojis siguen quitándose con aviso, como hoy.
3. **Dónde vive**: en una subcarpeta para que no aparezca como fuente de texto (`vista_previa.fuentes()` mira solo
   `static/fonts/*.ttf`) ni la tome libass (`fontsdir=static/fonts` no entra en subcarpetas): libass no dibuja color y
   pondría siluetas. La página la declara como `@font-face {font-family: "CreatvEmoji"}`.
4. **Secuencias**: sin Raqm (el Pillow de la Mac no lo trae y no se puede contar con él en el VPS), Pillow no aplica las
   ligaduras que arman banderas (dos indicadores regionales), tonos de piel, familias (ZWJ) y «keycaps». Por eso
   `simplificar` (D5.1) las reduce **en los dos motores**: un tono de piel queda en el amarillo de base, una familia
   en su primer emoji, un «1️⃣» en un «1», y las banderas se quitan. El panel lo dice (D7.5). Los emojis de un solo
   código (🔥 ✅ ⭐ 💯 🎁 🚚 💥 ❤ 👇 😍 …: los de los anuncios) salen tal cual.
5. **Si la fuente no está** (no se bajó): `tabla["emoji"]` es `null`, un emoji no está cubierto y se quita en los dos
   motores con el aviso de siempre; la pestaña de emojis de «Stickers» no aparece.
6. **Subtítulos: siguen sin emojis**, a propósito. libass no dibuja fuentes a color (pinta la silueta de la capa base
   en el color del texto) y los subtítulos salen de palabras transcritas, que casi nunca traen emojis; la corrección
   de una palabra ya los quita (`operaciones.sinEmojis`, capa 5a). No cambia nada ahí.
7. **Safari y COLRv0**: Chrome y Firefox dibujan COLRv0 desde `@font-face`; Safari, según la documentación pública,
   también — se comprueba en un iPhone en la prueba en vivo (riesgo 2). Si un navegador no la dibujara, ese navegador
   muestra su propio emoji en el mismo lugar y del mismo ancho (la maqueta no cambia): solo cambia el dibujo.

### D7. Ajuste de línea y ancho del texto

1. **Ancho por defecto**: los textos nuevos nacen con `ancho_max` (fracción del ANCHO del lienzo, el campo de hoy):
   0,86 para «Título» y «Subtítulo», 0,8 para «Llamado», `null` para «Precio», las plantillas para vender y los
   emojis (son cortos: que no se partan).
2. **Control «Ancho del texto»** en «Editar» (texto): deslizador 30–100 % (`estilo.ancho_max` = valor / 100, con
   `operarCon({clave: "<id>:ancho"})`: un arrastre es un deshacer) y casilla «Sin límite» (`ancho_max: null`).
3. **Saltos a mano**: Enter en el campo del texto ya escribe `\n` (capa 4b) y las dos maquetas los respetan.
4. **El ancho es del texto a escala 1**: la escala (el asa) agranda la caja entera, como en CapCut; un texto ancho y
   agrandado puede salirse del video, y eso se avisa (D10.4).
5. **Avisos del texto** (bajo el campo, en «Editar»; `propiedades_modelo.avisosTexto`): «No sale en el video: «…»
   (esta fuente no tiene esos caracteres)» con los `quitados` de `limpiar`; «Las banderas, los tonos de piel y los
   emojis compuestos salen simplificados» si `simplificado`; y en un texto v1 con caracteres que su fuente no trae:
   «Este texto es de antes: sus emojis no salen en el video.» con el botón «Mostrar los emojis». Reemplazan al aviso
   de la capa 4c (`prop.aviso_emoji`), que se borra.

### D8. Texto nítido a cualquier tamaño (bug #8): el PNG se dibuja al tamaño en que se ve

`factor_nitidez(e, ancho_px, alto_px) = min(4, max(1, ceil(e)))` (bajado hasta que el lado más largo quepa en 4096 px),
con `e = escala_max(clip)`, la escala más grande del clip (su `transform.escala` y la de cada fotograma clave), en
`tipografia.py`/`tipografia.js`. Un texto v2 se rasteriza a ese factor (D5.7) — el PNG mide
`ancho_px·f × alto_px·f` — pero `ancho_px`/`alto_px` siguen siendo los NATURALES (la maqueta a factor 1): la caja que
coloca `geometria.caja` no cambia, y el `scale=w:h` del compilador, que hoy estira, ahora achica o deja igual (nítido).
El compilador no cambia. La vista previa hace lo mismo con su lienzo (escala el contexto por `f`). Tope: el lado más
largo del PNG ≤ 4096 px (si `ancho_px·f` lo pasaría, `f` baja hasta caber), igual en los dos motores. Solo v2: un
texto v1 agrandado sigue igual de borroso hasta que se lo toca (D3).

### D9. Fuentes de anuncio: un catálogo curado, cargado solo cuando hace falta

1. **Catálogo** (`final_edition/fuentes.py::CATALOGO`, en este orden; `id` = nombre del archivo sin `.ttf`, que es lo
   que guarda `estilo.fuente`; `nombre` = el nombre propio de la familia, que no se traduce):

   | Familia de estilo (clave) | id | nombre | Para qué |
   |---|---|---|---|
   | Clásicas (`prop.fuentes_clasicas`) | `Inter-Bold`, `Inter-SemiBold`, `SpaceGrotesk-Bold` (hoy) y `Poppins-ExtraBold` | Inter Bold, Inter SemiBold, Space Grotesk, Poppins | texto de lectura, subtítulos de producto |
   | De impacto (`prop.fuentes_impacto`) | `ArchivoBlack-Regular`, `Anton-Regular`, `BebasNeue-Regular` | Archivo Black, Anton, Bebas Neue | precios, descuentos, «OFERTA»; condensadas para frases largas en 9:16 |
   | Redondeada (`prop.fuentes_redondeadas`) | `LilitaOne-Regular` | Lilita One | tono amable (niños, mascotas, comida) |
   | Manuscritas (`prop.fuentes_manuscritas`) | `Pacifico-Regular`, `CaveatBrush-Regular` | Pacifico, Caveat Brush | firmas, «hecho a mano», notas |
   | Con serifa (`prop.fuentes_serifa`) | `DMSerifDisplay-Regular` | DM Serif Display | belleza, joyería, lujo |

   Todas cubren el español y el portugués (á é í ó ú ñ ü ç ã õ ¿ ¡ €); Bebas Neue no tiene minúsculas propias (las
   dibuja como mayúsculas: es su estilo). `fuentes.catalogo()` devuelve solo las que tienen su archivo en
   `static/fonts/` (si Daniel no aprueba una, simplemente no se ofrece) y es lo que `vista_previa.config_navegador()`
   manda: `config.fuentes` sigue siendo la lista de ids (las `@font-face` de la plantilla la recorren), ahora en el
   orden del catálogo, y se suman `config.catalogo_fuentes` (`[{id, nombre, categoria}]`) y `config.tipografia`.
2. **`operaciones.FUENTES` = los ids de `fuentes.CATALOGO`** (constante espejo, comparada por `tests/test_editor_js.py`;
   `info()` es un mapa de materiales y no se le mezclan otras cosas): `cambiar` acepta cualquier fuente del catálogo y
   la página solo ofrece las que tienen su archivo. Si Daniel no aprueba una fuente, el controlador la saca de
   `CATALOGO` (pasos [FUENTES]) y las plantillas que la pedían usan `Inter-Bold` (cada preset trae su respaldo).
3. **Carga perezosa** (hoy `vista.iniciar` baja TODAS las fuentes antes del primer cuadro: con 11 serían ~2 MB en el
   celular): la página baja al abrir solo las fuentes que usa algún texto del documento (en cualquier destino) y la de
   emojis si algún texto v2 tiene un emoji; el selector de fuentes baja las demás cuando se abre (para mostrar cada
   nombre en su letra). Cuando una fuente termina de bajar, `texto_canvas` invalida lo que dibujó con la de respaldo
   (la caché lleva un contador de fuentes cargadas en la clave) y la vista se redibuja. De paso, la caché de textos
   deja de crecer sin tope (auditoría #19): guarda los últimos 200.
4. **Selector**: en «Editar» › texto, la lista de hoy (`ed-prop-fuente`) agrupada por familia de estilo, cada nombre
   escrito en su fuente (`style.fontFamily`), con su `aria-label` = el nombre.

### D10. Zonas seguras: guías y avisos, solo en la página

1. **Datos** (`static/editor/zonas.js`, puro): para el formato 9:16, por plataforma, rectángulos en fracción del
   lienzo que la interfaz de esa app tapa. Son **medidas de partida** (constantes con su fuente anotada; la prueba en
   vivo las compara con capturas reales y solo se ajustan los números):

   | Plataforma | arriba | abajo | lados / botones |
   |---|---|---|---|
   | `reels` (guía de anuncios de Meta: 14 % arriba, 35 % abajo, 6 % a cada lado) | y 0–0,14 | y 0,65–1 | x 0–0,06 y x 0,94–1, todo el alto |
   | `tiktok` | y 0–0,08 | y 0,80–1 | botones: x 0,87–1, y 0,40–0,80 |
   | `shorts` | y 0–0,07 | y 0,81–1 | botones: x 0,87–1, y 0,45–0,81 |

   Otros formatos (4:5, 1:1, 16:9): sin zonas — el selector dice «Las zonas son para videos verticales (9:16)».
2. **Guías**: `<div id="ed-zonas">` dentro de `#ed-escenario`, debajo de la capa de toques (`pointer-events: none`,
   `aria-hidden`), con un rectángulo rayado y translúcido por zona, en % del lienzo (como la caja de selección, sigue
   al lienzo en cualquier tamaño). Nada se dibuja en el `<canvas>` ni en el video.
3. **Elegir**: un `<select id="zonas">` en la barra de herramientas: «Zonas: no» · «TikTok» · «Reels» · «Shorts».
   Lo que se elige se recuerda por quien mira (`localStorage` `creatv.editor.zonas`, con `try/catch`; si falla o no
   hay nada: «Reels», porque las pruebas de Creatv corren en Meta). No va en el documento.
4. **Avisos** (`zonas.revisar(doc, medidas, materiales, plataforma, cfg)`, sobre el documento RESUELTO del destino
   que se ve — los textos variables y el precio miden distinto por país —): por cada capa de texto o imagen (stickers
   incluidos), su caja al empezar (`seleccion.cajaCapa` en su `inicio_ms`), y una franja para los subtítulos (alto =
   2 × el `tam_px` más grande de sus eventos, ancho 80 % centrado, en `subtitulos.posicion`):
   - **zona**: la caja se mete al menos 8 px en los dos ejes en un rectángulo de la plataforma elegida;
   - **fuera**: la caja se sale del lienzo al menos 8 px (con cualquier plataforma, también con «Zonas: no»).
   La página muestra el primero en `#aviso-zonas` («El texto «Envío gratis» queda bajo la interfaz de Reels
   (abajo).», «Los subtítulos quedan bajo la interfaz de Reels: súbelos en «Subtítulos».», «El texto «…» se sale del
   video: achícalo o baja su ancho.») y «y N más» si hay varios; nunca en rojo (puede ser a propósito). Se recalcula
   en cada refresco, como los avisos de carga.

### D11. Stickers gráficos: hechos en casa, sin palabras y del color que se elija

1. **20 stickers** dibujados con Pillow por `final_edition/stickers.py` (código en el repo, sin nada que bajar ni
   licencias de terceros), a 4× y reducidos (bordes suaves), BLANCOS sobre transparente, 512 px de lado mayor:
   - flechas: `flecha_recta`, `flecha_curva`, `flecha_mano` (trazo a mano), `flecha_abajo`;
   - marcas a mano: `circulo_mano`, `subrayado_mano`, `tachado_mano`, `chulo`, `equis`, `exclamacion`;
   - formas e insignias: `estallido`, `estrella`, `estrellas_5`, `corazon`, `etiqueta`, `cinta`, `circulo`,
     `burbuja`, `rayo`, `destellos`.
   Los trazos «a mano» salen de listas de puntos con un temblor de semilla fija: el generador da siempre lo mismo.
   Los PNG van commiteados en `static/stickers/` con `static/stickers/stickers.json`
   (`{"version": 1, "stickers": [{"id", "categoria": "flechas"|"marcas"|"formas", "archivo", "ancho", "alto",
   "color"}]}`, `color` = el de entrada: amarillo `#FFD400` las flechas y formas, rojo `#E11D48` las marcas).
2. **Un sticker es una capa de imagen** de siempre (pista `imagen`, `material_id`): sigue a su clip con «Vincular»,
   se mueve, se agranda y se borra igual, y en la 5c-2 se rota y se anima con lo demás. Al usarlo por primera vez en
   un proyecto, la ruta `editor.agregar_sticker` lo vuelve un `material` (gratis: `materiales.obtener_o_crear` por el
   hash del PNG — como `materiales.subir`, pero guardando también `url_proxy` — con la clave
   `clientes/<c>/materiales/sticker_<id>.png`, origen `sticker`, `extra = {nombre, sticker: id, tenible: true}`,
   `url_proxy = url` — un PNG de 512 px no necesita copia liviana); la segunda vez lo encuentra por su hash.
3. **Color (`tinte`)**: un clip de imagen puede llevar `tinte: "#RRGGBB"` (o nada). El render reemplaza el color y
   conserva el alfa — `[n:v]format=rgba,lutrgb=r=R:g=G:b=B,scale=w:h…` (`lutrgb` corre UNA vez: la entrada es una
   imagen de un cuadro que `overlay` repite) — y la vista previa hace lo mismo en un lienzo aparte (rellenar con el
   color y `globalCompositeOperation = "destination-in"` con la imagen): color constante × el mismo alfa, exacto en
   los dos. «Editar» muestra «Color» (la paleta de los textos) solo para un material `tenible`; en una foto no tiene
   sentido (la volvería una silueta).
4. **Idioma**: los stickers gráficos no tienen palabras; sus nombres (para el lector de pantalla y el `title`) son
   claves `bib.sticker_<id>`.
5. **No entran**: stickers de colores múltiples (para eso están los emojis, D12.2), animados, subidos por el cliente
   como «stickers» (una imagen subida ya es una capa).

### D12. Plantillas de texto para vender y emojis como sticker

1. **Plantillas** (sección «Para vender» de la pestaña «Texto»): presets nuevos de `agregarTexto` — textos v2 de
   siempre, editables en todo (contenido, fuente, colores, fondo), que nacen en el idioma de **quien edita** (la
   misma excepción que «Escribe aquí» de la capa 4c, §B8 del idioma):

   | preset | texto (es) | fuente (respaldo Inter-Bold) | px (9:16) | color | fondo |
   |---|---|---|---|---|---|
   | `oferta` | OFERTA | Anton-Regular | 96 | #FFFFFF | caja #E11D48, radio 0,01 |
   | `nuevo` | NUEVO | BebasNeue-Regular | 110 | #111111 | píldora #FFD400 |
   | `descuento` | -50 % | ArchivoBlack-Regular | 120 | #FFD400 | sin fondo, contorno #111111 de 6 px |
   | `envio` | ENVÍO GRATIS | Poppins-ExtraBold | 56 | #FFFFFF | píldora #16A34A |
   | `ultimas` | ¡ÚLTIMAS UNIDADES! | Poppins-ExtraBold | 52 | #FFFFFF | caja #111111 |
   | `mas_vendido` | MÁS VENDIDO | LilitaOne-Regular | 64 | #111111 | píldora #FFD400 |

   «-50 %» lleva espacio duro (U+00A0) para que nunca se parta. Una plantilla es un texto: su palabra se cambia
   escribiendo, se traduce como cualquier texto, y si la edición se produce para varios países la persona decide qué
   decir en cada uno.
2. **Emojis como sticker** (pestaña «Stickers», sección «Emojis», solo si la fuente de emojis está): una cuadrícula de
   40 emojis de anuncio (🔥 ✅ ⭐ 💯 🎁 🚚 💥 ❤ 👇 👉 😍 🤩 🛒 💸 ⏰ 🆕 ✨ 📦 💪 🙌 👀 ‼ ⚡ 🎉 🥇 👍 😱 🤑 📣 🔔 ⬇ ➡ ✔ ❌ 🌟 💎 🎯 🧡 🏷 🛍
   — la lista exacta en `static/editor/stickers_modelo.js`, filtrada por la cobertura de la tabla). Tocar uno agrega
   un texto v2 con ese emoji solo (preset `emoji`: 160 px, sin fondo, sin contorno, sin sombra, `ancho_max: null`):
   se agranda con el asa sin perder nitidez (D8) y sigue a su clip.
3. **Nada alarga el video**: todo entra con `lugarCapa` (3 s desde el cabezal, cortado en el fin), como los textos y
   las imágenes de hoy.

### D13. Las reglas del editor, con las capas nuevas

- **Un toque = un deshacer**: agregar un sticker es una sola operación (`agregarImagen`; el pedido a
  `editor.agregar_sticker` va antes y no toca el documento); el deslizador de ancho y el color del sticker fusionan su
  arrastre con `clave`; «Mostrar los emojis» es una operación.
- **«Vincular»**: los stickers son capas de imagen y los emojis-sticker y plantillas son textos: `vinculos.sigue` ya los
  incluye. Caso nuevo de prueba: un sticker sobre `v1` se mueve con él al reordenar.
- **Los módulos tocan la edición solo por `editor`**: `zonas.js` es puro; la capa de guías lee la vista (documento
  resuelto, medidas) por el objeto `editor`, como `lienzo_interaccion.js`.
- **Celular** (≤ 760 px): el selector de zonas cabe en la barra de herramientas a 375 px (se envuelve, nunca empuja
  la página); la pestaña «Stickers» es una más de la hoja de la biblioteca (icono + nombre, como las otras cinco);
  las cuadrículas de stickers y emojis usan `minmax(min(100%, 64px), 1fr)`; el deslizador de ancho es el de siempre.

### D14. Memoria y tiempo del render: nada cambia de presupuesto

- Un texto v2 sigue siendo **un** overlay de un PNG (D5): `PRESUPUESTO_OVERLAYS` lo cuenta igual. Su PNG a factor
  `f` pesa `f²` veces más en la etapa de `scale` (que corre una vez: la entrada es un cuadro) — un texto de
  900×200 a f = 4 son 3600×800×4 bytes ≈ 11,5 MB una vez, no por cuadro. El tope de 4096 px (D8) acota el peor caso.
- Un sticker es un overlay de imagen (512 px); `lutrgb` corre una vez.
- Rasterizar letra por letra con Pillow (tres pasadas): un texto de 40 letras son ~120 llamadas — milisegundos.
- La fuente de emojis se abre una vez por render (`functools.lru_cache` por tamaño, como hoy `_fuente_prueba`).

### D15. Idioma de la interfaz (fase 6)

Todo texto nuevo de `static/editor/*.js` es una clave definida igual en `final_edition/textos_editor.py::TEXTOS` (con
`N_`) y `static/editor/textos.js::ES`, usada con `t()`; prefijos que ya acepta `CLAVE` de
`tests/test_i18n_editor.py`: `prop.` (ancho, fuentes por familia, avisos de texto, color del sticker), `bib.`
(pestaña y secciones de stickers, nombres de los 20 stickers, plantillas), `op.` (textos iniciales de las plantillas
— `op.texto_oferta`… — y errores), `vista.` (avisos de zonas). Los nombres de las fuentes son nombres propios y no
pasan por el catálogo (vienen de `fuentes.CATALOGO`). Se borran `prop.fuente_inter_gruesa`, `prop.fuente_inter_media`,
`prop.fuente_space` (los reemplaza el nombre de la familia) y `prop.aviso_emoji` (D7.5). Los mensajes de contrato
nuevos de `operaciones.cambiar` («Esa fuente no está disponible» ya está en `INTERNOS`; «tinte debe ser un color
#RRGGBB.» se suma) quedan en español. En la plantilla: el selector de zonas y la pestaña «Stickers» con `{{ _('…') }}`.
En Python, el error de la ruta de stickers («Ese sticker no existe.») con `gettext` (responde a quien mira); los de
`rasterizar`/`fuentes` que pueden llegar a la persona (una fuente que falta: ya existía, `FuenteNoDisponible`) con
`gettext` en el idioma del proyecto (corren en el worker).

### D16. Esquema: sigue en 1; dos campos nuevos, opcionales

- `estilo.version` (texto): ausente = v1; si viene, debe ser `2` (otro valor falla: «estilo.version debe ser 2 o no
  estar»). No se agrega a `_ESTILO_DEFECTO`: un documento sin ella valida byte a byte igual.
- `tinte` (clip de una pista `imagen`): ausente/`null` = sin color; si viene, `#RRGGBB` (`_COLOR_SIN_ALFA_RE`); en
  otro tipo de pista falla.
- `resolver` (Python y JS) copia los dos tal cual (tabla `resolver_casos.json` ampliada con un texto v2 y un sticker
  con `tinte`). Ninguna migración ni adopción al abrir.

---

## 2. Formas de datos

### 2.1 Documento (esquema 1)

```json
{"id": "oferta_1", "inicio_ms": 2000, "duracion_ms": 3000,
 "texto": {"literal": "🔥 OFERTA"},
 "estilo": {"version": 2, "fuente": "Anton-Regular", "tamano": 0.05, "color": "#FFFFFF", "ancho_max": null,
            "fondo": {"color": "#E11D48", "opacidad": 1, "radio": 0.01, "relleno_x": 0.03, "relleno_y": 0.015, "ancho": null},
            "…": "lo de siempre"},
 "transform": {"x": 0.5, "y": 0.35, "escala": 1.6, "…": "…"}}
{"id": "img_3", "inicio_ms": 0, "duracion_ms": 3000, "material_id": 88, "tinte": "#FFD400",
 "transform": {"x": 0.7, "y": 0.55, "escala": 0.74, "…": "…"}, "ancho_px": 512, "alto_px": 391}
```

`documento.validar`: las dos reglas de D16, con mensajes de contrato en español (sin `gettext`) y la ruta del clip,
como el resto. Nada suma a `materiales` (el sticker ya va por `material_id`).

### 2.2 Tabla tipográfica — D4 (`static/editor/tipografia.json`)

Generada, nunca escrita a mano. `config_navegador()["tipografia"]` = el contenido; `config["fuentes"]` = los ids del
catálogo presente (como hoy, en el orden del catálogo); `config["catalogo_fuentes"]` = `[{id, nombre, categoria}]`; `config["emoji"]` = `{"familia": "CreatvEmoji", "url": …}` o `null`.

### 2.3 Maqueta — D5

```
maquetar(texto, estilo, formato, tabla, factor=1) -> {
  "texto": <limpio>, "quitados": [..], "simplificado": bool,
  "tam": int, "ancho_px": int, "alto_px": int, "factor": int,
  "margen": int, "caja_w": num, "caja_h": num, "radio": int,
  "lineas": [{"texto": str, "x": num, "base": num, "ancho": num}],
  "letras": [{"cp": int, "x": num, "base": num, "fuente": "texto" | "emoji"}]
}
```

`factor_nitidez(clip) -> int` (D8); `es_v2(estilo) -> bool`.

### 2.4 Stickers — D11

`static/stickers/stickers.json` (generado por `final_edition/stickers.py`, commiteado con los PNG). Material:
`{tipo: "imagen", origen: "sticker", ancho, alto, url, url_proxy: url, extra: {nombre, sticker, tenible: true}}`.

### 2.5 Rutas y tareas

- Nueva: `POST /cliente/<c>/ediciones/biblioteca/sticker/<sticker_id>` (`editor.agregar_sticker`): mismo origen
  (`_mismo_origen`), `sticker_id` contra el manifiesto (`^[a-z0-9_]{1,40}$` y que exista; si no, 404 «Ese sticker no
  existe.»), `materiales.subir` (idempotente por hash) → `{"material": vista_previa.material_para(m)}`. Gratis.
- `editor.ver`: `config.catalogo_fuentes`, `config.tipografia`, `config.emoji` y `datos.stickers` (el manifiesto con la
  URL de cada PNG); `textos` con las claves nuevas.
- `tareas.edicion.preparar_rutas`: a un texto v2 lo rasteriza con la maqueta y su factor (aunque traiga `pngs`, como
  hoy un PNG del navegador gana — nadie lo manda) y le estampa los `ancho_px`/`alto_px` NATURALES; sin cambios para v1.
- Ninguna tarea nueva del worker; nada paga.

---

## 3. Paridad, función por función

| Función | Cómo se garantiza | Prueba |
|---|---|---|
| Qué caracteres salen (cobertura, emojis simplificados) | la misma `limpiar` en Python y JS sobre la misma tabla | `tipografia_casos.json` (sección `limpiar`) |
| Dónde se parte cada línea | `ajustar` con `ancho` de la tabla, mismas operaciones | `tipografia_casos.json` (`ajustar`), exacto |
| Tamaño de la caja (`ancho_px`/`alto_px`) y origen de cada letra | `maquetar` compartida | `tipografia_casos.json` (`maquetar`), exacto; Python comprueba además que el PNG de Pillow mide `ancho_px·f × alto_px·f` |
| El dibujo de cada letra | cada motor rasteriza su glifo en el mismo origen entero | **tolerancia medida**: en la prueba en vivo, la vista previa y el render en 4 instantes, la caja de cada texto ±1 px y la tinta dentro de la caja (en la Tarea 9) |
| El emoji | la misma TTF COLRv0 en los dos | prueba lenta: el píxel central de un 🔥 de 200 px en el render es naranja/rojo (R > 180, B < 90) y NO el blanco del texto; en vivo, comparación visual en Chrome y Safari |
| La nitidez | los dos dibujan a `f` y achican a la caja | prueba lenta que DISCRIMINA: el mismo texto con escala 3 en v1 y en v2, en una edición de imagen (PNG sin compresión) — la transición fondo→letra del borde de una «H» tiene ≤ 2 px intermedios en v2 y, en v1 (estirado ×3), al menos 3 y más que en v2; con el código de hoy las dos darían lo de v1 |
| El tinte | color constante × alfa en los dos | prueba lenta: un sticker blanco con `tinte #FF0000` sale rojo (R > 200, G < 40) en su centro; sin tinte, blanco |
| Las zonas | solo página: no hay render | Node: rectángulos, choques y avisos con cajas conocidas |

Constantes espejo comparadas con `_constante_js` (`tests/test_editor_js.py`): `REPERTORIO`, `FACTOR_MAX = 4`,
`LADO_MAX_PNG = 4096`, `SEPARADOR = " "`, los rangos de `simplificar`, `ANCHO_DEFECTO` de los presets.

---

## 4. Archivos a bajar (pide permiso)

Nada de esto se baja sin que Daniel lo apruebe; el controlador lo pide antes de la Tarea 1 y anota el SHA-256 de
cada archivo bajado en el mensaje del commit. Tamaños confirmados con `curl -sIL` (HEAD) el 2026-10-01. Cada familia
OFL trae su `OFL.txt` (4–5 KB) en la misma carpeta de Google Fonts: se baja junto a su fuente (la licencia OFL pide
que viaje con el archivo) y se guarda como `static/fonts/licencias/<Familia>-OFL.txt`.

| Archivo (se guarda como) | Fuente exacta | Licencia | Tamaño | Sin él |
|---|---|---|---|---|
| `static/fonts/Anton-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf` (+ `…/ofl/anton/OFL.txt`) | SIL OFL 1.1 | 170 812 B | la plantilla «OFERTA» cae a Inter Bold; no hay condensada gruesa |
| `static/fonts/BebasNeue-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 61 400 B | «NUEVO» cae a Inter Bold |
| `static/fonts/Poppins-ExtraBold.ttf` | `https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-ExtraBold.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 154 836 B | «ENVÍO GRATIS» y «¡ÚLTIMAS UNIDADES!» caen a Inter Bold |
| `static/fonts/ArchivoBlack-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/archivoblack/ArchivoBlack-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 90 988 B | «-50 %» cae a Inter Bold |
| `static/fonts/LilitaOne-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/lilitaone/LilitaOne-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 28 092 B | sin redondeada; «MÁS VENDIDO» cae a Inter Bold |
| `static/fonts/Pacifico-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/pacifico/Pacifico-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 329 380 B | sin manuscrita fluida |
| `static/fonts/CaveatBrush-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/caveatbrush/CaveatBrush-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 295 568 B | sin letra de pincel |
| `static/fonts/DMSerifDisplay-Regular.ttf` | `https://github.com/google/fonts/raw/main/ofl/dmserifdisplay/DMSerifDisplay-Regular.ttf` (+ `OFL.txt`) | SIL OFL 1.1 | 76 580 B | sin serifa |
| `static/fonts/emoji/TwemojiMozilla.ttf` | `https://github.com/mozilla/twemoji-colr/releases/download/v0.7.0/Twemoji.Mozilla.ttf` (+ `https://raw.githubusercontent.com/mozilla/twemoji-colr/master/LICENSE.md` como `static/fonts/emoji/LICENSE.md`, 2 172 B) | arte CC-BY 4.0 (Twitter/X, pide atribución) · compilación Apache-2.0 | 1 474 284 B | los emojis se siguen quitando de los textos con aviso (como hoy); no hay sección «Emojis» en «Stickers». Todo lo demás de la capa funciona |

Total: 8 fuentes (1,21 MB) + la de emojis (1,47 MB) + 9 licencias (~40 KB). El controlador confirma, antes de bajar,
que v0.7.0 sigue siendo la última versión publicada de `twemoji-colr` (si hay una más nueva, se usa esa y se anota).
Las tres fuentes de hoy y `static/fonts/OFL.txt` no cambian (`OFL.txt` es la de Inter; Space Grotesk ya estaba sin la
suya: se agrega `licencias/SpaceGrotesk-OFL.txt` del mismo lugar, `…/ofl/spacegrotesk/OFL.txt`).

**Lo que funciona sin bajar nada**: zonas seguras, ajuste de línea y control de ancho, texto v2 exacto con las tres
fuentes de hoy, nitidez, stickers gráficos con su color, plantillas (todas en Inter Bold) y los avisos. El plan
marca con **[EMOJI]** y **[FUENTES]** los pasos que dependen de los archivos: si Daniel no aprueba alguno, el
controlador quita esos pasos antes de repartir la tarea.

---

## 5. Página

- Módulos nuevos, puros: `static/editor/tipografia.js` (D5, D8), `static/editor/zonas.js` (D10),
  `static/editor/stickers_modelo.js` (manifiesto → secciones, lista de emojis filtrada, presets de plantillas).
- `texto_canvas.js`: v2 dibuja la maqueta letra por letra a su factor (D5.7, D8); v1 sigue igual salvo que quita lo
  que la tabla dice que su fuente no tiene. La caché lleva el contador de fuentes cargadas y tiene tope (D9.3).
- `vista.js`: carga perezosa de fuentes y de la de emojis; `medidasTexto` desde la maqueta en v2; el tinte de las
  imágenes (`imagenTenida(mid, color)`, caché por par); `revisarZonas()` para la página.
- `lienzo.js`: dibuja el PNG de texto a su factor dentro de la caja; usa la imagen tenida si el clip tiene `tinte`.
- `operaciones.js`: presets nuevos de `agregarTexto` (con `version: 2` y su `ancho_max`), `actualizarTexto`, la
  conversión a v2 en `editarTexto`/`cambiar`, `tinte` en `cambiar` (solo imagen), `fraccion` y `tinte` en
  `agregarImagen`, `FUENTES` = el catálogo.
- `propiedades_modelo.js`/`propiedades.js`: ancho y «Sin límite», fuentes por familia, avisos del texto y «Mostrar
  los emojis», «Color» del sticker.
- `biblioteca.js`: pestaña «Stickers» (flechas · marcas · formas · emojis) y sección «Para vender» en «Texto».
- `pagina_editor.js` + `editor.html`: capa `#ed-zonas`, `<select id="zonas">`, `#aviso-zonas`, pestaña e icono
  `stickers`, `@font-face` de las fuentes del catálogo y de `CreatvEmoji`.

---

## 6. Riesgos

1. **Pillow y COLRv0 en el VPS**: no se puede probar en la Mac sin bajar la fuente; si el Pillow del VPS no compone
   COLRv0 (FreeType sin soporte de color), los emojis saldrían en la silueta de la capa base. Mitigación: la Tarea 3
   tiene una prueba lenta con el píxel del 🔥, y el controlador la corre EN EL VPS antes de desplegar (Tarea 9); si
   falla allí, se despliega con `EDITOR_SIN_EMOJI=1` en el `.env` del VPS: `fuentes.cargar_tabla()` devuelve la tabla
   con `emoji: null` a los dos motores (los emojis se quitan con aviso, como hoy) y se anota.
2. **Safari y COLRv0 en `@font-face`**: se comprueba en un iPhone (D6.7). Si no lo dibuja, la vista previa de Safari
   muestra el emoji de Apple en el mismo lugar; el render sale con Twemoji igual.
3. **Licencia CC-BY de Twemoji**: atribución en el repo y en el panel (D6.2). Si Daniel la rechaza, D6.5.
4. **Medidas de las zonas** (D10.1): son de partida; las de Reels siguen la guía publicada por Meta, las de TikTok y
   Shorts se ajustan con capturas en la prueba en vivo. Con los subtítulos en su altura de siempre (0,78) Reels
   avisará: es lo que la guía de Meta dice (el 35 % de abajo lo tapa el texto del anuncio). No se cambia la altura de
   los subtítulos en esta capa (cambiaría renders de borradores).
5. **Dos motores de texto conviviendo** (v1 y v2) hasta que la vía automática pase a v2: más código, pero cada uno
   probado. Pasar `borrador.py` a v2 (los borradores nuevos saldrían con la maqueta compartida) queda como decisión
   aparte: cambia cómo se ven los anuncios automáticos nuevos.
6. **La tabla no tiene kerning**: «AV» o «To» en v2 quedan un poco más abiertos que en v1 (Pillow sin Raqm tampoco
   lo aplicaba con estas fuentes: no tienen tabla `kern`, solo `GPOS`). Las ligaduras («fi») tampoco: las tres fuentes
   de hoy y las ocho nuevas se leen bien sin ellas.
7. **Peso de la página**: `tipografia.json` de 11 fuentes + emojis ≈ 40–60 KB sin comprimir, en los datos de la
   página; las fuentes bajan solo cuando se usan (D9.3).

---

## 7. Pruebas (resumen; el detalle está en el plan)

- Python: lector de TTF (las tres fuentes de hoy: `upem`, `asc`, `desc`, avances de «H», «o», «l», «a», cobertura de
  «✓» en Inter y no en Space Grotesk), `test_tabla_al_dia`, `tipografia` (`simplificar`, `limpiar`, `ancho`,
  `ajustar`, `maquetar`, `factor_nitidez` con valores exactos), `validar` (`version`, `tinte`, compatibilidad byte a
  byte), `rasterizar` v2 (el PNG mide `ancho_px·f × alto_px·f`; v1 da el MISMO PNG que en `main`, comparado byte a
  byte con un archivo de referencia generado antes del cambio), compilador (`tinte`), `preparar_rutas` (v2 estampa
  los naturales), stickers (manifiesto = archivos, generador determinista en tamaño), ruta `agregar_sticker`.
- Lentas (ffmpeg real): emoji a color en la final [EMOJI]; nitidez v1 contra v2 (la que discrimina); tinte; un texto
  v2 partido en dos líneas renderiza su caja donde la maqueta dice (la fila de la línea de base tiene tinta).
- Paridad: `tipografia_casos.json` nueva (con la tabla REAL del repo), `resolver_casos.json` ampliada,
  `test_casos_del_editor_al_dia`; constantes espejo.
- Node: `tipografia.js` contra la tabla, `texto_canvas` con un contexto falso que anota `fillText`/`strokeText`/`font`
  y los orígenes, `zonas.js`, `stickers_modelo.js`, operaciones nuevas (y sus casos en `salida_operaciones.mjs` que
  Python valida), propiedades, biblioteca, módulos del navegador sin efectos.
- En vivo (controlador): lanzador local sin llaves; Chrome escritorio y celular a 375 px; Safari en iPhone.

---

## 8. Lo que no entra en la 5c-1

Animaciones, rotación, keyframes de escala/opacidad y filtros (5c-2, §9); pasar la vía automática a v2 (riesgo 5);
kerning y ligaduras; banderas y emojis compuestos completos (hace falta Raqm en el VPS o un atlas propio de emojis:
otra entrega); emojis en subtítulos; fuentes del cliente; texto escrito sobre el video; asa lateral para el ancho (el
ancho va con el deslizador); stickers de varios colores, animados o subidos; mover la altura por defecto de los
subtítulos.

---

## 9. Capa 5c-2 — movimiento y color (esbozo)

Se diseña y planea entera después de desplegar la 5c-1 (con la memoria del render de la 5c-1 medida en el VPS). Lo
que sigue son las decisiones que ya se pueden tomar y lo que se comprobó con ffmpeg 9.0.1 en la Mac
(scratchpad, 2026-10-01) para tomarlas.

### 9.1 Qué entra

1. **Animaciones de capa** (textos, imágenes y stickers, no la principal): de **entrada** y de **salida** —
   `aparecer` (alfa 0→1), `deslizar` (la de hoy: baja el 8 % del alto), `rebote` (escala 0,6→1,12→1 con
   amortiguación), `zoom` (escala 0,4→1), `maquina` (máquina de escribir: letra por letra; solo textos v2) — y
   `ninguna`; 400 ms por defecto (`DURACION_ANIMACION_MS`), 100–2000 ms. El documento gana `animacion.salida` (ya
   validada en `ANIMACIONES`) y `animacion.duracion_salida_ms` (nueva, opcional). Una animación vieja con solo
   `entrada: "deslizar"` se ve y se produce igual.
2. **Rotación** de textos, imágenes y stickers: `transform.rotacion` (ya validada, en grados) se renderiza; asa de
   rotar sobre el video (un círculo encima de la caja, con el dedo) que pega a 0/90/180/270 a menos de 5°, y un campo
   «Rotar» (−180–180) en «Editar».
3. **Fotogramas clave de escala y opacidad**: decisión — **se interpretan los dos**, por la misma vía que las
   animaciones (la capa ya es un flujo de cuadros: el «esperar a PNG con alfa» de la capa 1 queda resuelto con
   `scale=…:eval=frame` y `fade`/`geq` sobre RGBA). La rotación por fotograma clave **no** (rotar cada cuadro con un
   ángulo distinto cuesta un `rotate` completo por cuadro; si la medición en el VPS lo permite, entra después).
4. **Filtros de color** en los clips de la principal (videos y fotos), como «Filtros» de CapCut: 8 recetas — Vivo,
   Cálido, Frío, B/N, Vintage, Suave, Contraste, Atardecer — con **intensidad** (0–100 %) y tres ajustes (brillo,
   contraste, saturación). Una foto lo aplica una vez, antes de su `loop`.

### 9.2 La capa animada: de un PNG quieto a un flujo de cuadros (verificado)

- **Hoy**: una capa es un PNG de un cuadro que `overlay` repite (`eof_action=repeat`) con x/y por expresión.
- **Con animación, escala/opacidad por fotograma clave o rotación**: la entrada se vuelve flujo con
  `loop=loop=<n−1>:size=1:start=0,setpts=N/(30*TB)+<inicio>/TB` (n = cuadros visibles en el tramo; el mismo truco
  que las fotos de la 5b), y por cuadro:
  - **escala**: `scale=w='<expr de t>':h='<expr de t>':eval=frame` (de a pares) y `overlay=x='cx-overlay_w/2'`
    — comprobado: con un PNG de 763×118 que entra en 0,5 s y crece 0→1 en 400 ms, la franja roja mide 187 px a los
    0,6 s, 337 a los 0,7 y 753 a los 1,2 (el `overlay` acepta una entrada que cambia de tamaño en cada cuadro);
  - **alfa**: `format=rgba,fade=t=in:st=<s>:d=<d>:alpha=1` y `fade=t=out:…:alpha=1` — comprobado: el píxel del fondo
    de la caja pasa de (51,74,150) a 0,05 s, (109,58,123) a 0,2 s y (228,25,70) entero, y vuelve a la mitad en la
    salida;
  - **máquina de escribir**: `geq` sobre el alfa con `T`, revelando hasta el corte de la letra `k(t)` de cada línea —
    `a='if(lt(X,<corte de la línea según Y y T>),alpha(X,Y),0)'` con `enable='between(t,<ini>,<fin>)'` (fuera de la
    animación no corre) — comprobado: la tinta llega a x = 295, 643 y 901 a los 0,1, 0,25 y 0,5 s de una revelación
    de 0,4 s. Los cortes por letra salen de la maqueta v2 (D5: el `x` de cada letra), la misma que usa la vista
    previa: **la paridad es exacta en qué letras se ven en cada cuadro**;
  - **rotación**: `format=rgba,rotate=a=<rad>:ow='rotw(<rad>)':oh='roth(<rad>)':c=none` y el `overlay` centrado en la
    caja — comprobado: las esquinas quedan transparentes (el fondo se ve tal cual) y el centro es el del PNG.
    Estática: corre una vez (entrada de un cuadro). Animada: `a='<expr de t>'` por cuadro (solo si se mide barata).
- **La vista previa** hace lo mismo con `drawImage` + `ctx.globalAlpha` + `ctx.rotate`, y la máquina de escribir con
  `ctx.save(); ctx.beginPath(); ctx.rect(…); ctx.clip()` por línea. Las curvas (`rebote`, `zoom`) son UNA función pura
  `animacion.valor(tipo, fase, t)` en Python y JS con tabla de paridad (`animacion_casos.json`), y el compilador la
  vuelve una expresión de ffmpeg por tramos lineales de 1 cuadro (30 puntos por segundo de animación: la expresión
  da el mismo número que la función en cada cuadro, comprobado en la tabla).
- **Memoria**: una capa animada deja de ser «un overlay de 8 MB»: su flujo pasa cuadros por `scale`/`fade` mientras
  se ve. En `tramos.py`, una capa animada o rotada **pesa 2** en `PRESUPUESTO_OVERLAYS` (a medir en el VPS en la
  5c-2: si el número real es otro, se cambia el peso, no el diseño) y `n` se acota a lo que se ve en el tramo.
- **Selección rotada**: `seleccion.capaEnPunto` lleva el punto al sistema de la caja (rotación inversa alrededor de su
  centro) antes de comparar; la caja de selección del DOM lleva `transform: rotate()`; el asa de rotar va 32 px de
  pantalla encima del borde superior, rotada con la caja.

### 9.3 Filtros de color: una matriz y una curva, los mismos números en los dos motores

- **Receta pura** (`final_edition/filtros.py` / `static/editor/filtros.js`, tabla `filtros_casos.json`):
  `receta(filtro) → {matriz: 3×4, curva: [r[256], g[256], b[256]]}` desde `{receta, intensidad, brillo, contraste,
  saturacion}`; intensidad k mezcla `I + k·(M − I)` y `v + k·(curva(v) − v)`.
- **Render**: `colorchannelmixer=<matriz>` + `lut1d=file='<ruta>'` con un `.cube` 1D de 256 entradas (el compilador
  sigue puro: devuelve el texto del `.cube` en el plan, como hoy el `.ass`, y el renderizador lo escribe). Con 256
  entradas y entrada de 8 bits, `lut1d` cae justo en cada entrada (sin interpolar). Medido en la Mac a 1080×1920, un
  hilo: `colorchannelmixer` + `lut1d` = 9 ms por cuadro (+45 MB); `eq` solo, 1,2 ms. En el VPS (≈ 3× más lento) un
  anuncio de 30 s suma ~25 s de render: se acepta y se mide en la 5c-2.
- **Vista previa**: un filtro SVG en la página (`<feColorMatrix type="matrix">` con la misma matriz +
  `<feComponentTransfer>` con `type="table"` de 256 valores, `color-interpolation-filters="sRGB"`) aplicado con
  `ctx.filter = "url(#ed-filtro-<clip>)"` al dibujar la principal: la misma cuenta, píxel a píxel salvo el redondeo
  de 8 bits y la conversión YUV del video. Donde `ctx.filter` no existe (Safari viejo), una aproximación con
  `saturate()`/`brightness()`/`contrast()` y el aviso «Vista aproximada» de las transiciones. **Paridad medida**:
  prueba lenta con parches de color planos (sin submuestreo de croma que moleste): la salida de ffmpeg contra la
  receta aplicada en Python (Pillow `point` + `convert(matrix)`), ±4 por canal; en vivo, captura de la vista contra
  el cuadro del render en 4 instantes.
- En una transición se ven dos clips con filtros distintos: cada uno se filtra antes del `xfade`, en los dos motores.

### 9.4 Tareas previstas (para el plan de la 5c-2)

1. `animacion.py`/`animacion.js` (curvas, tabla) y el contrato (`salida`, `duracion_salida_ms`). 2. Compilador: capa
como flujo (escala, alfa, máquina) + peso en `tramos`. 3. Vista previa de las animaciones. 4. Rotación en el
compilador y la vista previa. 5. Asa de rotar, selección rotada y «Rotar» en «Editar». 6. Panel de animaciones
(entrada/salida, duración, vista previa al elegir). 7. `filtros.py`/`filtros.js` + compilador (`lut1d` en el plan) +
fotos. 8. Vista previa de filtros (SVG) y panel «Filtros». 9. Controlador: medir memoria y tiempo en el VPS, prueba
en vivo, guía y despliegue.
