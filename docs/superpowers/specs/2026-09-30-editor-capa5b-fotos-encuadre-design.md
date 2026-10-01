# Editor capa 5b — fotos y encuadre, y todo sigue a su clip — diseño

Fecha: 2026-09-30. Estado: **implementado** 2026-10-01 (plan
`docs/superpowers/plans/2026-09-30-editor-capa5b-fotos-encuadre.md`). Base de código: `main` **después** de fusionar
la capa 5a (`editor-capa5a`: subtítulos derivados y voz en off), que a su vez va sobre la fase 6 del idioma
(`worktree-idioma-oscuro`). Nace de:

- spec del editor `2026-09-18-final-edition-editor-design.md` §4 («Vista previa: … fondo desenfocado automático cuando
  el video no llena el marco»; «Formato: … paneo manual del video»; «Medios: … un video sobre otro es PIP»;
  «Timeline: … Borrar (ripple en la principal)»);
- inventario del motor (capa 4b): §2 «imagen fija como clip PRINCIPAL» (L), §8 PIP (L), §9 filtros (L);
- auditoría post-despliegue de la 4b, Parte 2: #7 «cortar o borrar video no mueve la voz, los textos ni los
  subtítulos», #10 «una transición entre dos videos enteros se vuelve corte seco», #12 «un video horizontal en un
  anuncio vertical siempre queda recortado»; Parte 3, ítems 4 (fotos de producto y encuadre) y 7 (vínculos).

Pedido de Daniel: «todo, el mejor editor». Esta capa deja armar un anuncio de producto con fotos (la mayoría de los
clientes de ecommerce tiene más fotos que videos), elegir qué parte del cuadro se ve, unir dos clips enteros con una
transición de verdad, y que lo que está encima de un clip de video (textos, imágenes, voces, efectos) se mueva con él.


**Ajustes de la ejecución (2026-10-01):** `setsar=1` va al FINAL de cada cadena de la principal, después del zoompan (como
el arreglo 25edb51 que ya estaba en producción), no antes de `fps`; las etiquetas de «Editar» son «Duración de la foto» y
«Acercar el cuadro» (claves propias, no `prop.duracion`: en el mismo panel ya hay otra «Duración» y otro «Acercar»); un
toque sobre el video elige su clip y lo de encima se toma primero (salvo el asa del video elegido); `vocesJuntas` no
cuenta dos voces de idiomas distintos (nunca suenan a la vez); «Corte» elegido a propósito nunca es un aviso rojo.

---

## 0. Qué entra y qué no

**Entra**

1. **Foto como clip del video** (presentación de producto): una imagen dentro de la pista principal, mezclada con
   videos, de N segundos (3 s por defecto, de 0,1 a 60 s), con zoom lento opcional y transiciones con sus vecinos.
   En la biblioteca, «+» sobre una imagen ofrece «Como clip del video» y «Encima del video» (la capa de hoy).
2. **Encuadre por clip de la principal**: «Llenar» (el recorte de hoy) o «Ajustar con fondo desenfocado» (el cuadro
   entero y, detrás, una copia desenfocada que llena), más **mover y acercar dentro del cuadro** arrastrando sobre el
   video, como en CapCut. Los dos motores; paridad al píxel donde se puede medir (el primer plano) y aproximada donde
   no (el desenfoque).
3. **Transiciones entre dos clips enteros**: una transición nueva **junta** los dos clips (el video queda más corto
   por lo que dura), así que nunca se vuelve corte seco por falta de material.
4. **Todo sigue a su clip** («vinculado»): al cortar, borrar, reordenar, recortar, cambiar la velocidad o poner una
   transición en la principal, los textos, imágenes, voces y efectos que están sobre un clip se mueven con él. Un
   interruptor «Vincular» (prendido por defecto) lo apaga.
5. Arreglos que esto destapó: la unión con corte seco de un video horizontal y uno vertical **no renderiza hoy**
   (D3, verificado con ffmpeg); un video grabado de pie con el celular se mide acostado (D6).

**No entra** (anotado para otras capas): video sobre video (PIP, D14); filtros y ajustes de color; rotación de la
principal; cambiar el formato de la edición; encuadre que se mueve en el tiempo (paneo animado, keyframes del
encuadre); fondo de color liso o de imagen en «Ajustar» (solo desenfocado); pellizcar con dos dedos (el zoom va con el
asa y con el deslizador); vincular o desvincular un clip suelto (el interruptor es de toda la página); que la música
se estire cuando el video crece; cruzar el sonido de la escena en una transición (sigue en corte, como hoy); el
carrusel de la edición de imagen (capa 6: la pista `imagen` principal sigue con una sola fuente); fotos del Catálogo
dentro de la biblioteca (auditoría #8); cambiar la intensidad del zoom lento; «Producir e idiomas» (capa **5d**; la 5c es textos y gráficos, §6).

---

## 1. Decisiones

### D1. Una foto es un CLIP de la pista principal (`foto: true`), no una pista nueva

Hoy la pista principal es de un solo tipo: `video` (una línea de tiempo) o `imagen` (la edición de imagen, sin tiempo,
una sola fuente). Para mezclar fotos con videos hay dos caminos:

| Opción | Cómo | Problema |
|---|---|---|
| A. Pista principal de un tipo nuevo («mixta») | `pista_principal` elige entre `video`, `mixta`, `imagen` | Todo lo que hoy pregunta «¿la principal es video?» (compilador, tramos, operaciones, línea de tiempo, vista previa, 5a) tendría que aprender otro tipo; y un documento pasa de `video` a `mixta` al agregar la primera foto. |
| **B. Un clip de la pista `video` que es una foto (elegida)** | el clip lleva `foto: true`; su `material_id` es una imagen | Nada más cambia de tipo: la principal sigue contigua desde 0, y cortar, borrar con ripple, reordenar, duplicar, las transiciones, el zoom lento, el espejo del sonido y los vínculos funcionan igual. Solo cambia cómo se DIBUJA ese clip y qué reglas de tiempo tiene. |

Reglas de un clip `foto` (contrato en §2.1): velocidad 1 (una foto no tiene velocidad: cambia cuánto dura); dura de
100 ms a 60 s; su `recorte` es siempre `{desde_ms: 0, hasta_ms: duracion_ms}` (no hay tiempo de fuente, pero todo el
código que lee `recorte` sigue funcionando); nunca tiene espejo en `p_sonido` (una foto no suena); `ken_burns`,
`transicion` y `encuadre` como cualquier clip de video.

La edición de imagen (pista `imagen` principal, duración 0) no cambia: sigue siendo la de un anuncio de una sola foto
(capa 6).

### D2. Cómo la dibuja el render: se decodifica una vez y se repite

- **Entrada**: la foto entra SIN `-loop 1` (con `-loop 1` el demuxer vuelve a leer y decodificar el archivo en cada
  cuadro) y el filtro `loop` repite en memoria el cuadro ya escalado:
  `…,setsar=1,format=yuv420p,loop=loop=<n−1>:size=1:start=0,setpts=N/(30*TB),fps=30<zoompan>,format=yuv420p`, con
  `n = max(1, round((cuánto se ve en el tramo + cola de su transición) × 30 / 1000))`. El escalado y el encuadre van
  ANTES del `loop` (corren una vez); el zoom lento va después (cambia en cada cuadro). Verificado con ffmpeg 9.0.1: un
  video de 2 s que se funde (0,5 s) en una foto de 3 s da exactamente 5,000 s; una foto de 2 s con zoom lento que se
  funde en un video de 2 s da 4,000 s.
- **La foto que se compila es una copia preparada** (`final_edition/fotos.preparar`, Pillow, en `preparar_rutas`):
  orientación EXIF aplicada, la transparencia sobre negro (así la ve también la vista previa, que pinta el lienzo de
  negro antes), RGB, lado largo ≤ 4096 px, JPEG calidad 92. Va en `rutas["foto:<material_id>"]`, aparte de
  `rutas[<material_id>]`: la misma imagen puede estar a la vez como foto y como capa encima (que necesita su alfa).
- **Cola de una transición**: los cuadros de más salen del mismo `loop`; una foto nunca se queda sin material, así que
  `verificar_recortes` y `normalizar` la saltan.
- **Memoria (`motor/tramos.py`)**: cada clip de la principal cuenta 1 en `PRESUPUESTO_VIDEOS = 6` (b8ca01f), sea video
  o foto. Medido en la Mac (ffmpeg 9, x264 de un hilo): seis fotos de 4000×3000 piden 332 MB de RSS; seis videos
  1080p, 565 MB. Una foto cuesta menos que un video, pero sin medir en el VPS no se le baja el peso: queda anotado
  (§4, riesgo 1) y el controlador lo mide en la prueba en vivo.

### D3. `setsar=1` en cada clip de la principal (bug real de hoy)

`scale=…:force_original_aspect_ratio=increase,crop=…` deja el SAR que haga falta para compensar el redondeo
(p. ej. `10240:10239`), y **`concat` exige el mismo SAR** en sus dos entradas; `xfade` no lo mira. Resultado,
verificado con ffmpeg 9.0.1 sobre el filtergraph que arma hoy `compilador.compilar`: un video 16:9 seguido de uno 9:16
con corte seco NO renderiza —

> `Input link in0:v0 parameters (size 1080x1920, SAR 1:1) do not match the corresponding output link in0:v0
> parameters (1080x1920, SAR 10240:10239)`

— y lo mismo una foto con SAR propio (4:3) junto a un video. La capa 4b ya deja mezclar videos de distintas
proporciones; nadie lo había producido con un corte seco. Arreglo: cada cadena de la principal termina su encuadre con
`,setsar=1`. Cambia el texto del filtergraph de todos los documentos (las pruebas que comparan la cadena exacta se
actualizan); la imagen que sale es la misma.

### D4. El encuadre: `encuadre = {modo, zoom, x, y}` por clip, y UNA fórmula para los dos motores

Campo nuevo, opcional, en los clips de la pista `video` (videos y fotos). `null` (o ausente) = lo de hoy: llenar,
centrado, sin acercar — y en ese caso el compilador y la vista previa usan **exactamente** el código de hoy (el mismo
texto de filtergraph salvo `setsar`, D3), así un documento viejo se ve y se produce igual.

- `modo`: `"llenar"` (el cuadro cubre el lienzo y lo que sobra se recorta) o `"ajustar"` (el cuadro entra entero y el
  hueco se llena con el fondo desenfocado, D5).
- `zoom`: 1,0–4,0, sobre el tamaño del modo (en «ajustar», 1 = entra justo; más = se acerca y puede pasar el lienzo).
- `x`, `y`: 0–1, **qué parte se ve** cuando el cuadro escalado es más grande que el lienzo: 0 = el borde izquierdo
  (o de arriba) del cuadro pegado al del lienzo, 1 = el derecho (o el de abajo), 0,5 = centrado. Cuando el cuadro es
  más chico que el lienzo (ajustar), la misma regla lo coloca: 0 a la izquierda, 1 a la derecha.

La fórmula (`final_edition/encuadre.py::caja` = `static/editor/encuadre.js::caja`, tabla de paridad
`tests/fixtures/encuadre_casos.json`), con `w×h` el tamaño del cuadro que se VE (D6) y `W×H` el lienzo:

```
par(v) = 2·⌊v/2 + 0,5⌋                                   # el par más cercano (yuv420p: medidas y desplazamientos pares)
manda_el_alto = (w·H ≥ h·W) == (modo == "llenar")        # enteros: sin error de coma flotante
si manda_el_alto:  sh = par(H·zoom);  sw = par(w·sh / h)
si no:             sw = par(W·zoom);  sh = par(h·sw / w)
px = 0 − par((sw − W)·x);  py = 0 − par((sh − H)·y)      # dónde queda la esquina del cuadro escalado en el lienzo
```

Las mismas operaciones de coma flotante, en el mismo orden, dan los mismos números en Python y en JS (`0 − …` para que
JS no dé `-0`). En «llenar» el render hace `scale=sw:sh,crop=W:H:−px:−py`; en «ajustar», el primer plano
`scale=sw:sh` va con `overlay=x=px:y=py` (px/py pueden ser negativos: `overlay` recorta lo que sale del lienzo). Todo
par, así `crop` en yuv420p no corre el desplazamiento. Ejemplos (9:16): un video 1920×1080 en «llenar» con `x: 0` →
`sw 3414, sh 1920, px 0`; con `x: 1` → `px −2334`; en «ajustar» → `sw 1080, sh 608, py 656`; una foto 400×200 en
«ajustar» → `sw 1080, sh 540, py 690`.

El zoom lento (`ken_burns`) se aplica DESPUÉS del encuadre, sobre el cuadro ya compuesto (como hoy sobre el recortado):
acerca hacia el centro del lienzo.

### D5. «Ajustar con fondo desenfocado»: el mismo cuadro, chico, desenfocado y agrandado

- **Render**: `split=2`; una copia va al lienzo chico `fondo(W, H) = (par(W/10), par(H/10))` (108×192 en 9:16,
  108×136 en 4:5, 108×108 en 1:1, 192×108 en 16:9) con el recorte «llenar» de siempre, `boxblur=luma_radius=6:
  luma_power=2` y se agranda a `W×H`; la otra es el primer plano de D4; `overlay` los junta. Desenfocar el lienzo chico
  cuesta casi nada por cuadro (verificado: el video y la foto salen con el primer plano exacto en su franja y el fondo
  mezclado alrededor). Sin color de fondo elegible: solo desenfocado (lo que pide la auditoría #12 y lo que CapCut
  hace por defecto).
- **Vista previa**: el mismo camino — la fuente se dibuja en un lienzo chico del mismo tamaño (un 20 % más grande que
  ese lienzo, para que el desenfoque no traiga negro de los bordes) con `filter = "blur(5px)"` y se agranda al lienzo;
  el primer plano va con la caja de D4. Donde el navegador no tiene `filter` en el lienzo (Safari viejo), el agrandado
  del lienzo chico ya se ve blando: se acepta. El fondo es **aproximado** (como hoy las transiciones «Zoom» y
  «Fundido a negro»); el primer plano, **exacto** (±2 px, D6).
- La vista previa sigue sin `crossOrigin`: dibujar el video en un lienzo chico lo «contamina», pero nadie lee sus
  píxeles.

### D6. Las medidas que se VEN, medidas donde está el archivo

El encuadre depende de la proporción del cuadro. Un video grabado de pie con el celular viene codificado acostado
(1920×1080) con una marca de rotación de 90° (`side_data_list[].rotation` en ffprobe; verificado con
`-display_rotation 90`: ffprobe dice 1280×720 y ffmpeg decodifica 720×1280). Hoy `biblioteca._medir` y
`ejecutar_proxy` guardan el ancho y el alto codificados (auditoría #24).

- **Render**: `preparar_rutas` estampa `ancho_px`/`alto_px` en cada clip de la principal que tiene `encuadre`, con las
  medidas que se ven — de la foto preparada (D2) o de ffprobe con `encuadre.medidas_visibles(stream)` (rotación ±90 o
  270 intercambia ancho y alto; lee `side_data_list[].rotation` y, en ffprobe viejos, `tags.rotate`). El compilador
  calcula la caja con esos números enteros (cadenas con números, fáciles de probar). Un clip con `encuadre` y sin esas
  medidas es un error de quien llama (`ValueError` con su nombre).
- **Vista previa**: usa las medidas del elemento que dibuja (`videoWidth`/`naturalWidth`: el navegador ya aplica la
  rotación, y la copia liviana sale derecha de ffmpeg). La copia liviana tiene la misma proporción salvo el redondeo
  a pares, así que el primer plano coincide con el render a ±2 px (hoy se acepta 1–4 px).
- **Desde ahora** la subida y la tarea del proxy guardan las medidas que se ven (así el encuadre automático, D7, y las
  miniaturas de la biblioteca las usan bien). Los materiales viejos no se re-miden: el render mide siempre por su
  cuenta.

### D7. El encuadre que se pone solo al AGREGAR (y solo ahí)

Al agregar un video o una foto a la principal, si su proporción difiere de la del lienzo en más de un 25 %
(`4·w·H > 5·h·W` o `5·w·H < 4·h·W`, enteros) entra con `encuadre: {modo: "ajustar"}`; si no, sin encuadre (llenar).
Así una foto cuadrada o un video horizontal en un 9:16 se ven enteros con el fondo desenfocado, y una foto vertical de
celular (1284×2778 en 9:16: 18 % más alta) llena el cuadro. Nunca se toca el encuadre de lo que ya estaba (un borrador
automático sigue igual).

### D8. Mover y acercar el encuadre sobre el video

- **Tocar el video** (dentro del lienzo, fuera de textos e imágenes) elige el clip de la principal que suena en el
  cabezal — hoy no elige nada —; tocar fuera del lienzo sigue quitando la selección. Con un clip de la principal
  elegido, **arrastrar** mueve el cuadro (cambia `x`/`y`: la imagen sigue al dedo, con imán al centro como las capas)
  y el **asa** de la esquina lo acerca o aleja (`zoom` 1–4). Cada arrastre es UN deshacer (`operarCon({clave:
  "<clip>:encuadre"})`). Si el cuadro no tiene margen para moverse (llenar sin acercar y misma proporción), el panel
  dice «Acerca el video para poder moverlo».
- **Propiedades** del clip de video y de la foto: «Encuadre» con «Llenar» · «Ajustar con fondo desenfocado»,
  «Acercar» (100–400 %) y «Centrar». La foto además: «Duración» (0,1–60 s) y sin «Velocidad» ni «Volumen del sonido».
- Durante una transición se ven dos clips: el gesto actúa sobre el del cabezal (el que entra).

### D9. Transiciones que JUNTAN los dos clips (`modo: "solape"`)

Hoy una transición de `d` ms en el clip A ocupa `[fin_A, fin_A + d)` con cuadros de la COLA de A (material después de
su recorte), y si A no tiene cola (dos videos enteros de la biblioteca, el caso común) se vuelve corte seco en
silencio (auditoría #10).

| Opción | Cómo | Problema |
|---|---|---|
| A. Solapar en el documento | B empieza en `fin_A − d` | La principal deja de ser contigua: `validar`, el `offset` del compilador, `tramos`, `principalEn`, `videos.js`, el espejo del sonido, cortar, reordenar, la 5a… todo cambia, y la vía automática también. |
| B. Cabeza de B (el espejo de la cola) | cuadros ANTES del recorte de B | Un video entero tampoco tiene nada antes de su inicio. |
| **C. A cede sus últimos `d` ms (elegida)** | al poner la transición, A se acorta `d` (duración y `recorte.hasta_ms`) y esos ms pasan a ser su cola | El documento sigue contiguo y la cola que el render ya sabe usar existe siempre (es lo recortado). Compilador, `verificar_recortes`, `tramos` y la vista previa **no cambian**. Lo que se ve es lo de CapCut: los dos clips enteros, `d` ms uno sobre otro, y el video `d` ms más corto. |

`transicion.modo = "solape"` guarda que esos `d` ms salieron de A. Reglas (todas en `operaciones.js`):

- **Complementa, no reemplaza.** Sin `modo`, una transición es de «cola», como hasta hoy (los borradores automáticos y
  lo que ya se editó: entre cortes del mismo clon hay cola y convertirlas acortaría un anuncio que tiene la voz
  medida). Toda transición que se pone donde no había (`corte` → un tipo) nace `solape`.
- **Cambiar el tipo** (de fundido a deslizar) no toca la duración ni el modo. **Cambiar la duración** de una `solape`
  devuelve la de antes y quita la nueva (A cambia `d_viejo − d_nuevo`). Una de «cola» cambia como hoy.
- **Quitarla** (`corte`) devuelve a A sus `d` ms (acotado a su material por `normalizar`).
- **Topes**: `d ≤ duración de A − 100 ms` y `d ≤ duración de B − 100 ms`; si así no llega a 200 ms, «Esos clips son muy
  cortos para una transición».
- **Si A queda último** (se reordenó o se borró lo que venía después), `normalizar` deshace su `solape`: A recupera sus
  `d` ms y la transición se va (en el último clip no hace nada y A estaría perdiendo `d` ms).
- **Alargar A por la derecha** usa esa cola: `normalizar` achica la transición a lo que queda (la regla de hoy), y al
  quitarla A recupera solo eso — la cuenta cierra.
- Cortar A deja la transición en la mitad derecha (como hoy). Una foto como A cede sus `d` ms igual (misma regla, aunque
  su cola sea infinita): un solo comportamiento que explicar.

La biblioteca lo dice al ponerla: ««Fundido» quedó en la unión: junta los dos clips y el video quedó 0,5 s más corto.». El sonido de la
escena sigue cortándose en la unión, como hoy (fuera de esta capa).

### D10. Todo sigue a su clip: el vínculo se DERIVA en el momento de la operación

| Opción | Cómo | Problema |
|---|---|---|
| A. Vínculo guardado (`vinculo: <id>` en cada capa) | se pone al agregar o soltar una capa | Hay que mantenerlo en cada arrastre (volver a vincular al soltar sobre otro clip), en cada corte (la mitad derecha tiene id nuevo), al duplicar, al deshacer; queda apuntando a clips borrados; los borradores automáticos no lo traen. Una segunda verdad. |
| **B. Vínculo derivado (elegida)** | justo antes de aplicar una operación que cambia la principal, el ancla de cada capa es el clip de la principal que suena en su INICIO y el momento de ese clip (tiempo del material); después va adonde ese momento suena ahora | Nada que mantener, nada guardado: la misma idea que la 5a (D1: derivar en vez de guardar) y que `materiales` en `validar`. |

`static/editor/vinculos.js::seguirPrincipal(antes, despues, info)`, pura, la aplica la página después de CADA
operación (`pagina_editor.operarCon`) cuando «Vincular» está prendido; si la principal no cambió devuelve el mismo
documento. Reglas (algoritmo exacto en §2.4):

1. **Qué sigue**: textos, imágenes, y audios de voz, efecto, subida y grabación (las voces agregadas en el editor y las
   grabaciones de la 5a). **Qué no**: la principal, `p_sonido` (se rehace como espejo), la **música** (es el fondo de
   todo el anuncio: moverla con el primer clip la dejaría corta al reordenar) y las **voces con `por_destino`** (la voz
   del guion de la vía automática: `resolver` la cambia entera por la de cada país, con otra duración — es la columna
   del anuncio, no algo de un plano). Lo que empieza en o después del fin de la principal tampoco se mueve.
2. **Ancla**: el clip A de la principal con `inicio ≤ inicio de la capa < fin` (una capa que empieza justo en un corte
   es del clip de la derecha) y el momento `f` = `recorte.desde + (inicio de la capa − inicio de A) × velocidad` (en una
   foto, el desfase).
3. **Adónde va**: el clip de `despues` que muestra ese momento `f` — primero el mismo id, si no uno nuevo de su misma
   raíz y material (la mitad derecha de un corte: `idNuevo` conserva la raíz); la capa queda en `inicio' + (f − desde') /
   velocidad'`. Así sigue al CONTENIDO: si el clip se recortó por delante, el texto que salía con el producto sigue
   saliendo con el producto; si cambió de velocidad, también. Si `f` ya no se ve (se recortó), se queda en el borde
   más cercano del clip.
4. **Si su clip se borró**, la capa no se borra (lo escrito o lo pagado nunca desaparece solo; deshacer está a un
   toque): va al punto donde estaba ese clip — donde ahora empieza el siguiente que sobrevivió, o el fin del video — más
   el mismo desfase, así varias capas de ese clip conservan su orden y separación.
5. **Nada alarga el video** (regla de la 4b/4c): una capa que sigue a su clip, o la música, que terminaba en o antes del
   fin de antes y ahora pasa del fin nuevo, se corta en el fin; si quedaría empezando en o después del fin, entra entera
   terminando ahí (como `lugarCapa`). Lo que ya pasaba del fin antes de la operación (la cola de una voz de un borrador)
   no se toca, y una voz con `por_destino` nunca se corta (el render congela el último cuadro, como hoy).
6. **Filas**: si una capa MOVIDA (su inicio cambió) queda encima de otra de su misma fila, pasa a la primera fila de su
   clase donde quepa — en el orden de su nuevo inicio y, a igual inicio, en el de antes: la primera se queda
   (la regla de agregar, `pistaLibre`: un audio solo comparte fila con los de su mismo rol); sin filas libres (8 como
   máximo) se queda en la suya.
7. **Dos voces a la vez**: si después de moverse suenan dos voces al mismo tiempo (en filas distintas), la edición lo
   avisa bajo el video («Dos voces suenan al mismo tiempo en 0:04: muévelas o borra una.») — un aviso de carga más, que
   se va solo cuando se arregla (`avisos_carga.vocesJuntas`).
8. **Deshacer**: la operación y lo que se movió son UN paso (la página guarda un solo documento).
9. **«Vincular»**: botón con estado (`aria-pressed`) en la barra de herramientas, prendido por defecto, recordado por
   quien mira (`localStorage`, con `try/catch`: si falla, prendido). Apagado = el comportamiento de antes de esta capa,
   exacto. No va en el documento: es una forma de editar, no algo que se produce.

**Qué sigue igual**: cortar la principal no mueve nada (la línea de tiempo no cambia); duplicar un clip deja sus capas
con el original (no las copia, como CapCut); cortar o duplicar una capa: cada trozo toma su ancla por su propio inicio
en la próxima operación. Los fotogramas clave de una capa son relativos a su inicio: viajan con ella.

### D11. Los subtítulos y la 5a

- Los subtítulos derivados de la 5a siguen a su AUDIO (5a D1): una voz o grabación que sigue a su clip lleva sus
  subtítulos; los de «El sonido del video» siguen a la principal por construcción; los de una canción no se mueven
  (la música no sigue). Los subtítulos de legado (palabras absolutas sin `fuentes`) no siguen: la 5a ya lo dice en su
  panel y adopta la voz al abrir cuando puede (5a D14).
- Una foto no tiene sonido: `subtitulos_fuente.clips_de_fuente` (Python) / `clipsDeFuente` y `materialesDeFuente`
  (JS) saltan los clips `foto` en la fuente `{tipo: "sonido"}`, y `subtitulos_modelo.fuentesDisponibles` no ofrece «El
  sonido del video» cuando solo hay fotos o videos mudos. Si no, la página pediría transcribir una imagen (la ruta de la
  5a respondería 404).
- Una transición `solape` recorta el final de A: las palabras de esos ms salen por la regla del centro (5a D2), igual
  que el sonido que se deja de oír.

### D12. La biblioteca y la línea de tiempo

- «+» sobre una imagen abre dos opciones: «Como clip del video» (`agregarFoto`, después del clip del cabezal, como un
  video) y «Encima del video» (`agregarImagen`, la capa de hoy). Arrastrarla a la fila del video la pone como foto en
  ese lugar; a cualquier otra fila, encima. Al agregarla: «Foto agregada al video: dura 3 s. Cámbialo en «Editar».».
- En la fila del video, una foto se ve con su imagen repetida a lo largo (la copia liviana, D13), sin tira de
  fotogramas.
- «Vincular» en la barra de herramientas, con su icono, junto a Cortar · Duplicar · Borrar; en el celular cabe en la
  misma barra (375 px).

### D13. Copias livianas de las fotos para la vista previa

Una foto de 12 MP decodificada ocupa ~48 MB en el navegador; diez fotos de producto tumbarían Safari en un iPhone. La
tarea gratis `edicion_proxy` (hoy: «Sin proxy para este tipo» para imágenes) hace para una imagen una copia de lado
largo ≤ 1920 px (JPEG calidad 85, o PNG si tiene transparencia, para que una capa encima conserve su alfa), en
`clientes/<c>/materiales/<id>_proxy.jpg|png`, y la guarda en `url_proxy`. `vista_previa.pendientes` la pide para las
imágenes que no la tienen (como hoy los videos: se encola al abrir la edición y la vista usa el original mientras
tanto). La vista previa y las miniaturas de la biblioteca usan `url_proxy` cuando existe; el render, siempre el
original preparado (D2).

### D14. Video sobre video (PIP): se aplaza, con su porqué

El contrato ya acepta pistas `superpuesto` y el compilador las rechaza. No entra en esta capa porque:

1. **Memoria del render**: cada clip de PIP es otra entrada de video decodificándose a la vez (~85 MB en el VPS de un
   núcleo, la medición de b8ca01f). `tramos.partir` tendría que contar esas entradas en `PRESUPUESTO_VIDEOS` y no cortar
   una ventana en medio de un PIP (hoy solo respeta las transiciones de la principal). Es un diseño de tramos propio.
2. **Vista previa en el celular**: el spec (§3) fija «nunca más de dos decodificando»; un PIP sobre una transición son
   tres. Hay que medirlo en teléfonos reales (capa 7) antes de prometerlo.
3. **Su sonido**: el sonido de la escena es un espejo de la PRINCIPAL (`p_sonido`); un PIP necesita su propio espejo o
   una regla de «sin sonido», y eso toca la mezcla y la 5a.
4. **Lo que pide un anuncio de producto** (auditoría, Parte 3): fotos y encuadre (ítem 4) y vínculos (ítem 7) antes que
   PIP. Con fotos + encuadre + capas de imagen se cubren casi todos los armados.

En esta capa: el mensaje del compilador deja de decir «llega en la capa 4» y pasa a «El video encima de otro video
todavía no se puede producir.» (con `gettext`), y ninguna operación ni pedido de la biblioteca crea una pista
`superpuesto` (probado).

### D15. Idioma de la interfaz (fase 6)

Todo texto nuevo de `static/editor/*.js` es una clave definida igual en `final_edition/textos_editor.py::TEXTOS` (con
`N_`) y en `static/editor/textos.js::ES`, usada con `t()`: `op.*` (errores de las operaciones), `tr.*` (transiciones),
`prop.*` (encuadre y foto), `bib.*` (agregar una imagen), `editar.*` (el interruptor «Vincular»), `vista.*` (el aviso de
voces). Se reutilizan `prop.centrar`, `prop.duracion`, `prop.zoom_lento`, `prop.transicion_siguiente`, `prop.tipo`,
`prop.borrar`, `tr.*` de los nombres, `bib.agregado`. Los mensajes de contrato de `cambiar` («encuadre.x no se puede
cambiar», «Ese encuadre no existe») quedan en español como los demás de su clase (`INTERNOS` de
`tests/test_i18n_editor.py`). En Python, los mensajes nuevos que pueden llegar a la persona (`preparar_rutas`,
`fotos`, el del PIP) van con `gettext`, en el idioma del proyecto porque corren en el worker; `final_edition/fotos.py`
entra a `WORKER` de `tests/test_i18n_mensajes.py`. Las plantillas con `{{ _('…') }}`.

---

## 2. Formas de datos

### 2.1 Documento (esquema 1, sin migración de número)

```json
{"id": "foto_2", "inicio_ms": 4000, "duracion_ms": 3000, "material_id": 42, "foto": true,
 "recorte": {"desde_ms": 0, "hasta_ms": 3000}, "velocidad": 1.0, "ken_burns": "in",
 "encuadre": {"modo": "ajustar", "zoom": 1.0, "x": 0.5, "y": 0.5},
 "transicion": {"tipo": "fundido", "duracion_ms": 500, "modo": "solape"}, "...": "lo de siempre"}
```

`documento.validar` — cambios exactos (mensajes de contrato, en español, sin `gettext`, como el resto de `validar`):

- Constantes nuevas: `FOTO_MIN_MS = 100`, `FOTO_MAX_MS = 60000`, `FOTO_DEFECTO_MS = 3000`,
  `MODOS_TRANSICION = ("solape",)`.
- `foto`: si viene, `bool` (otro tipo falla); solo en pistas `video` (en otra, falla: «foto solo va en la pista de
  video»). `foto: false` se quita (el clip queda como antes). Con `foto: true`: `velocidad` debe ser 1.0 (si no, falla:
  «una foto va a velocidad 1»), `duracion_ms` entre 100 y 60 000 (si no, falla), y `recorte` se normaliza a
  `{desde_ms: 0, hasta_ms: duracion_ms}` sin fallar.
- `encuadre`: si viene, `null` u objeto; solo en pistas `video` (en otra, falla). Claves permitidas `modo`, `zoom`,
  `x`, `y` (otra clave falla); `modo` en `encuadre.MODOS` (por defecto `"llenar"`), `zoom` número 1,0–4,0 (por
  defecto 1,0), `x`/`y` fracción (por defecto 0,5). Se guarda completo; si queda igual a `encuadre.DEFECTO`, se guarda
  `null`.
- `transicion.modo`: si viene, debe estar en `MODOS_TRANSICION`; ausente = cola.
- Nada de esto suma a `materiales` (ya estaban los `material_id`).

**Compatibilidad**: un documento sin `foto`, `encuadre` ni `transicion.modo` valida igual, byte a byte. No hay
migración ni adopción al abrir. `resolver` (Python y JS) copia los campos nuevos tal cual (tabla `resolver_casos.json`
ampliada con una foto con encuadre y una transición `solape`).

### 2.2 Material

- Imagen: `url_proxy` (copia liviana, D13). `ancho`/`alto` siguen siendo las medidas de la imagen derecha (ya lo eran:
  la subida la endereza por EXIF).
- Video: `ancho`/`alto` = las medidas que se ven (D6), desde ahora, en `biblioteca._medir` y en `edicion_proxy`.

### 2.3 Compilador (cadenas exactas)

Para el clip `i` de la principal con entrada `idx`, `enc` su encuadre y `(sw, sh, px, py)` la caja de D4 con sus
`ancho_px`/`alto_px`, `(fw, fh) = fondo(W, H)`:

| Caso | Fragmento de encuadre |
|---|---|
| `encuadre` nulo (hoy) | `scale=W:H:force_original_aspect_ratio=increase,crop=W:H` |
| llenar | `scale={sw}:{sh},crop=W:H:{−px}:{−py}` |
| ajustar | sentencias aparte: `[…]split=2[f{i}a][f{i}b]`; `[f{i}a]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},boxblur=luma_radius=6:luma_power=2,scale=W:H,setsar=1[f{i}c]`; `[f{i}b]scale={sw}:{sh},setsar=1[f{i}d]`; `[f{i}c][f{i}d]overlay=x={px}:y={py}` y sigue la cadena |

- Video: `[idx:v]{setpts},{encuadre},setsar=1,fps=30{zoompan},format=yuv420p[v{i}]` (entrada `-ss/-t` de siempre).
- Foto: entrada `{"ruta": rutas["foto:<mid>"], "opciones": []}`;
  `[idx:v]{encuadre},setsar=1,format=yuv420p,loop=loop={n−1}:size=1:start=0,setpts=N/(30*TB),fps=30{zoompan},format=yuv420p[v{i}]`.
- `verificar_recortes` salta los clips `foto`. `tramos.videos` los cuenta (docstring al día).
- Mensajes con `gettext`: «Falta el tamaño del clip «%(clip)s» para su encuadre.» y el de PIP (D14).

### 2.4 El algoritmo de `seguirPrincipal(antes, despues, info)`

```
firma(doc) = [(id, inicio, duración, desde, velocidad, foto) de cada clip de la principal]
si firma(antes) == firma(despues): devolver despues (el mismo objeto)
res = copia de despues;  finAntes, fin = fin de la principal en antes / en res
para cada capa X de res que SIGUE (D10.1), que existe en antes con el mismo id y el MISMO inicio (la operación no la
movió: si `normalizar` acortó la principal mientras se arrastraba un texto, gana el arrastre), y cuyo inicio < finAntes:
    A = clip de la principal de antes con A.inicio ≤ X.inicio < A.fin;  d = X.inicio − A.inicio
    f = A.foto ? d : A.desde + round(d × A.velocidad)
    C = clip de res con id A.id que muestra f; si no, uno nuevo (no estaba en antes) de raíz(A.id) y mismo material que muestra f;
        si no, el de id A.id aunque no muestre f
    si C:  X.inicio = C.inicio + (C.foto ? acotar(f, 0, C.dur) : acotar(round((f − C.desde) / C.velocidad), 0, C.dur))
    si no: cierre = inicio en res del primer clip que seguía a A en antes y sobrevivió, o fin;  X.inicio = cierre + d
para cada X de res que sigue o es música, sin por_destino, que en antes terminaba en o antes de finAntes y ahora pasa de fin:
    si X.inicio ≥ fin: X.inicio = max(0, fin − X.dur)
    X.dur = min(X.dur, fin − X.inicio)   (en audio también recorte.hasta = desde + X.dur)
movidas = las X cuyo inicio cambió, en orden de su nuevo inicio (a igual inicio, el orden de antes)
para cada X movida que pisa otra de su fila: pasa a pistaLibre(res, tipo, BASE_PISTA, X.inicio, X.dur, [p_sonido], mismo rol)
normalizar(res, info)
```

`vocesJuntas(doc) → [{t_ms, ids: [a, b]}]`: pares de clips de voz o grabación (de cualquier fila salvo `p_sonido`) que
se solapan, con el primer instante del solape; la página muestra el primero.

### 2.5 Rutas y tareas

Ninguna ruta ni tarea nueva, nada que pague. Cambian: `edicion_proxy` (imágenes, D13), `preparar_rutas` (fotos y
medidas, D2/D6; revisa tipos: un clip `foto` cuyo material no es imagen, o uno de video cuyo material es imagen, falla
con «El clip «%(clip)s» es una foto, pero su archivo no es una imagen.» / «El clip «%(clip)s» del video no es un
video.»), `biblioteca._medir` (D6), `vista_previa.pendientes` (D13).

---

## 3. Página

- Módulos: `static/editor/encuadre.js` (puro: caja, fondo, encuadre automático, mover y acercar),
  `static/editor/vinculos.js` (puro: seguir la principal, voces juntas y la preferencia «Vincular»). Se enganchan como
  siempre: la vista previa los usa al dibujar; `pagina_editor.operarCon` aplica `seguirPrincipal`; los paneles solo
  tocan la edición por el objeto `editor`.
- `lienzo.js`: dibuja la principal con su encuadre y su fondo; `vista.js`: la copia liviana de las fotos, un lienzo
  chico para el fondo, y las medidas del cuadro de un clip de la principal (para arrastrar);
  `videos.js`: una foto nunca pide un `<video>`.
- `seleccion.js` / `lienzo_interaccion.js`: tocar el video elige el clip de la principal; arrastrar = encuadre; el asa =
  acercar. `propiedades*.js`: la forma «foto» y el bloque «Encuadre» en video y foto.
- `biblioteca.js`: el menú de dos opciones de una imagen; `escala.js`/`linea_tiempo.js`: la foto en la fila del video;
  `pagina_editor.js` + `editor.html`: el botón «Vincular» y el aviso de voces juntas.

---

## 4. Riesgos

1. **Memoria del render con fotos**: cada foto cuenta como un video (conservador). Si en el VPS una foto resulta costar
   la mitad (en la Mac: 332 MB seis fotos contra 565 MB seis videos), se le da peso 0,5 en `tramos.videos` en otra
   entrega, con la medición en la mano. Mitigación en esta: `loop` en vez de `-loop 1`, escalado antes del `loop`,
   fotos preparadas a ≤ 4096 px.
2. **Decodificar fotos en el celular** (vista previa): copias livianas (D13); las fotos se liberan junto con la página.
   Sin medir en iPhone (capa 7).
3. **El fondo desenfocado en la vista previa**: `ctx.filter` falta en Safari viejo (se ve blando pero sin desenfoque
   real); dibujar dos veces por cuadro. Se mide en la prueba en vivo del controlador.
4. **`setsar=1` cambia todas las cadenas** del compilador: muchas pruebas de texto exacto se actualizan en una tarea.
5. **Vincular sorprende** a quien quiere reordenar planos bajo una voz fija: por eso la voz del guion (`por_destino`) y
   la música no siguen, y el interruptor la apaga. Dos voces que quedan juntas se avisan.
6. **`solape` acorta el video**: a propósito (como CapCut) y dicho en el panel; con «Vincular» lo que viene después se
   corre con su clip. La vía automática nunca pone transiciones nuevas (no llama a `ponerTransicion`).
7. **Medidas de videos viejos** (acostados): el render mide por su cuenta (D6); solo el encuadre automático de un video
   viejo podría elegir «ajustar» sin hacer falta — y «ajustar» de un video que en verdad tiene la proporción del
   lienzo lo llena igual.
8. **Paridad ±2 px** del primer plano (copia liviana vs original): se revisa en cuatro instantes en la prueba en vivo,
   como en la capa 3.

---

## 5. Pruebas (resumen; el detalle está en el plan)

- Python: `validar` (foto, encuadre, modo de transición, compatibilidad), `encuadre` (caja, fondo, automático, medidas
  que se ven), `subtitulos_fuente` sin fotos, compilador (cadenas exactas de los tres casos, foto con cola y zoom lento,
  foto partida por tramos, `setsar`, errores), `verificar_recortes` y `tramos` con fotos, `fotos.preparar`/`ligera`
  (EXIF, alfa sobre negro, tope 4096/1920), `preparar_rutas` (tipos, medidas estampadas), proxy de imágenes, medidas
  rotadas.
- Render real (`slow`, medios de juguete con `ffmpeg -f lavfi` y Pillow): video + foto con fundido (5,0 s exactos);
  16:9 + 9:16 con corte seco (hoy fallaba); foto roja|azul de 400×200 en «llenar» con `x: 0` y `x: 1` (el píxel
  central sale rojo y azul); en «ajustar» (franja exacta en las filas 690–1229, fondo mezclado fuera); video rotado con
  encuadre; ocho fotos sin sonido partidas en dos tramos.
- Paridad: `encuadre_casos.json` nueva, `resolver_casos.json` y `subtitulos_fuente_casos.json` ampliadas;
  `test_casos_del_editor_al_dia`; constantes espejo (`MODOS`, `ZOOM_MIN/MAX`, `FONDO_DIVISOR`, `FOTO_*`).
- Node: `encuadre.js`, `vinculos.js`, operaciones nuevas, `lienzo` con contexto falso (qué `drawImage` pide cada
  encuadre), selección y propiedades; `salida_operaciones.mjs` con los casos nuevos (`foto_*`, `encuadre_*`,
  `solape_*`, `vinculado_*`) que Python pasa por `validar` y `verificar_recortes`.
- En vivo (controlador): lanzador local sin llaves (nada paga en esta capa).

---

## 6. Relación con la 5a y con lo que sigue

- **5a**: se construye encima; D11 cubre los tres puntos de contacto (derivados que siguen a su audio, fotos fuera de
  «El sonido del video», `solape` y la regla del centro). El `idioma` de un clip de audio (5a D10) viaja con el clip.
- **Nombre de la siguiente**: el spec de la 5a llama «capa 5b, Producir e idiomas» a la traducción de subtítulos y la
  pantalla de destinos. Quedó como **5d** (la 5c es textos y gráficos); la mención de la 5a ya dice 5d.
- **PIP**: entrega propia después de medir en el VPS y en teléfonos (D14), con sus cuatro requisitos: tramos que cuenten
  y respeten los PIP, límite de videos a la vez en la vista previa, sonido del PIP, y encuadre/tamaño sobre el video.
