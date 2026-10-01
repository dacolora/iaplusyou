# Flow Plus: generar todas las escenas encadenadas

Fecha: 2026-09-30 · Pedido de Daniel: «diseña lo de generar todas las escenas». Es la Parte B del spec del
cliente (`docs/flowplus/workflow-automation-spec.md` §1.4: «El último frame de un clip se usa como imagen de
arranque del siguiente»). Sigue a «Imágenes de cada escena» y «Llevar a Crear»
(`2026-09-30-flowplus-imagenes-por-escena-design.md`).

## 1. Qué decidió Daniel

| Pregunta | Decisión |
|---|---|
| ¿Qué pesa más? | **Continuidad exacta**: cada escena arranca en el último fotograma de la anterior y conserva a los personajes. |
| ¿Cómo se aprueba el gasto? | **Todo de una, con freno**: un precio total y una sola aprobación; si una escena falla la cadena se detiene y no cobra lo que sigue; después, «Rehacer desde la escena N» con su propio precio. |
| ¿Más de 3 personajes/productos en una escena? | **Avisar antes de cobrar**: no se genera hasta que la persona apague fichas en esa escena. |
| ¿Al terminar? | **Unir en el editor**: una edición con todas las escenas en orden y su sonido, gratis, sin render. |

## 2. Lo que dicen los modelos (verificado en WaveSpeed el 2026-09-30)

- `alibaba/wan-3.0/reference-to-video` y `kwaivgi/kling-video-o3-pro/reference-to-video` (los que usa Crear):
  **no** reciben imagen de arranque, solo referencias.
- `kwaivgi/kling-video-o3-pro/image-to-video`: `image` (arranque, obligatoria), `end_image` opcional y
  `element_list` (hasta 3 «elementos» de Kling, la identidad de un personaje u objeto). 3–15 s.
  US$ 0,112/s, 0,14 con `sound`. Sin `aspect_ratio`: sigue a la imagen (sin verificar).
- `kwaivgi/kling-elements-advanced`: crea un elemento reutilizable con `frontal_image` + 2–4 `refer_images`
  (o un video). US$ 0,01 por elemento de imagen.
- Wan 3.0 y Seedance 2.5 tienen «imagen a video», pero **sin** referencias: solo sirven de plan B.

Por eso la cadena usa **Kling O3 Pro**: la escena 1 por `reference-to-video` (con sus imágenes, como hoy), las
siguientes por `image-to-video` con el último fotograma de la anterior y los elementos.

## 3. Cómo se ve

En «Imágenes de cada escena» de una versión **armada**, un bloque «Generar todas las escenas»:

1. **Revisión previa, gratis** (`cadena.revisar`): la lista de lo que impide generar, por escena —
   escena sin prompt en el chat; imagen «por crear» sin subir; escena 1 con más de 7 imágenes; escena 2+ con
   más de 3 elementos (personajes, productos y extras de la escena); una cadena ya corriendo. Con algo de eso,
   el botón queda apagado y cada fila dice qué falta.
2. **Precio** (`cadena.precio`): Σ `flowplus_modelos.estimate_video("kling_o3_pro", duración de la escena,
   con_sonido=True)` + US$ 0,01 por elemento que todavía no existe. HappyCozy v4: 142 s × 0,14 ≈ US$ 20.
3. **Aprobar**: «Generar las N escenas · ≈ US$ X» con un `confirm()`. El POST lleva `total_visto`; el servidor
   recalcula y, si no coincide, no lanza nada (mismo criterio que la investigación de Nicho).
4. **Progreso**: cada escena muestra su estado (en espera · generando · lista · falló · detenida), el enlace a
   su pieza de Crear y, si falló, el motivo en palabras (`_mensaje_error` de Crear).
5. **Botones según el estado**: «Detener» mientras corre (frena después de la escena en curso: la que ya se está
   generando la cobra WaveSpeed igual); «Rehacer desde la escena N» con la cadena detenida o terminada (precio de
   N…final, otra aprobación; las escenas anteriores quedan); «Abrir en el editor» cuando terminó.

Todo pasa por el catálogo de idiomas (`_()`/`gettext`), como el resto de la app.

## 4. Cómo se arma

### 4.1 Cada escena es una pieza de Crear

La cadena no tiene generador propio: por escena crea una sesión con `creative_flow.crear` + `actualizar`
(prompt, modelo `kling_o3_pro`, duración, formato, `con_sonido=True`, `tipo="video"`) y la lanza con
`flowplus_lanzar.lanzar(..., prioridad=PRIORIDAD_LOTE)` (carril de Crear, como un lote de Sprints). Hereda así la
recuperación automática de WaveSpeed, el registro del gasto real (`video:<cf_id>:t<tarea>`), el aviso de saldo,
la tarjeta y el Aprobar/Rechazar de Crear. La sesión lleva `extra.cadena = {guion_video_id, indice}`.

### 4.2 Kling «imagen a video»

`providers/flowplus_modelos.generar_video` acepta dos campos nuevos de la sesión, que `tareas/flowplus._preparar`
le pasa: `imagen_inicial` (URL) y `elementos` (ids). Con `imagen_inicial`, Kling O3 Pro va a
`kwaivgi/kling-video-o3-pro/image-to-video` con `{"prompt", "image", "element_list", "duration", "sound"}`; sin
él, todo sigue como hoy. `ajustar_duracion` y `referencias_de_mas` siguen valiendo (la imagen de arranque no
cuenta como referencia; los elementos tienen su propio tope de 3).

### 4.3 El eslabón

En `tareas/flowplus._terminar_video` (el cierre común de la generación y de «Recuperar»), si la sesión tiene
`extra.cadena`, se encola la tarea gratuita `cadena_eslabon` (`max_intentos=2`):

1. Saca el último fotograma del video crudo (`ffmpeg -sseof -0.1 … -frames:v 1`, función nueva y probada con un
   video real) y lo sube a R2 (`clientes/<c>/flowplus/cadena/<video>_<k>.jpg`).
2. Marca la escena `lista` con su `frame_url`.
3. Si la cadena sigue `corriendo` y hay escena siguiente: crea y lanza la sesión de k+1 con
   `imagen_inicial = frame_url`. Si era la última: estado `terminada` y encola `cadena_unir`.

El fallo de una pieza de la cadena (error del proveedor, contenido sensible, espera agotada sin recuperación)
encola `cadena_eslabon` con el error: la escena queda `fallo` y la cadena `detenida`. Nada de lo que sigue se
crea ni se cobra.

### 4.4 Los elementos

La tarea `cadena_elementos` (`max_intentos=1`, paga centavos) corre una vez al aprobar: por cada imagen de
personaje, producto o extra que usen las escenas 2+, busca su elemento en `kv` (`kling_elemento:<cliente>:<sha1
de la URL>`) y, si no está, lo crea con `kling-elements-advanced`. Gasto tipo `video`, referencia
`kling_elemento:<sha1>`. Cuando termina, lanza la escena `desde`. Si falla, la cadena queda `detenida` antes de
generar ningún video.

### 4.5 Los prompts

`cadena.prompt_escena(texto, video, k, imagenes, elementos)` parte del prompt vigente del chat (el mismo que usa
«Llevar a Crear»):
- Escena 1: igual que `escenas.prompt_para_crear` (REFERENCE MAP solo con sus imágenes, `@Imagen k`).
- Escena 2+: el REFERENCE MAP pasa a nombrar los elementos con la forma que acepte Kling (se fija en la
  Etapa 0); la línea «Start image = last frame of Clip N.» se cambia por «The video starts exactly on the
  provided first frame.»; una imagen que la escena no lleva se nombra en palabras, como en «Llevar a Crear».
- Límite conocido: `image-to-video` no recibe entornos como imagen (solo el fotograma y los elementos). Si una
  escena 2+ cambia de lugar, el lugar nuevo llega solo por el texto; la revisión previa lo avisa (sin
  bloquear) cuando una escena 2+ tiene un entorno distinto del de la escena anterior.

### 4.6 Datos

Sin migración. `guion_video.extra["cadena"]`:

```
{"estado": "corriendo|detenida|terminada|cancelada", "desde": 1, "actual": 3,
 "modelo": "kling_o3_pro", "aprobado_usd": 19.9, "aprobado_por": "<usuario>", "aprobado_en": "...",
 "detener": false,
 "escenas": {"1": {"cf_id": "...", "estado": "espera|generando|lista|fallo", "frame_url": "...", "error": "..."}},
 "elementos": {"<sha1>": "<element_id>"}, "edicion_id": null}
```

Único escritor: `guiones/datos.modificar_cadena(cliente, video_id, fn)`, que toma el candado de SQLite antes de
leer (como `modificar_imagenes_escenas`). `guiones/cadena.py` es puro: revisión, precio, prompts y transiciones
(`aprobar`, `lista`, `fallo`, `detener`, `rehacer_desde`, `siguiente`). Mientras la cadena corre, la versión no
admite cambios de imágenes por escena (las rutas responden 409).

### 4.7 La edición al terminar

La tarea gratuita `cadena_unir` materializa cada pieza (`final_edition.biblioteca.materializar_pieza`) y arma un
documento con todas las escenas en la pista principal, en orden y contiguas, más el sonido de escena espejado.
Generaliza `final_edition/edicion_clon.documento`, que hoy arma la edición de un solo clon, y la guarda con
`ediciones.crear` (origen `{tipo: "flowplus", guion_video_id}`). El `edicion_id` queda en la cadena y el panel
muestra «Abrir en el editor».

## 5. Errores y frenos

- **Falla una escena**: la cadena queda `detenida` en k; se ve el motivo; «Rehacer desde la escena k».
- **«Detener»**: pone `detener: true`; el eslabón no lanza la siguiente; la cadena queda `detenida`.
- **«Rehacer desde N»**: exige la cadena detenida o terminada y el fotograma de N−1 (o N = 1); precio de N…final
  y otra aprobación con `total_visto`. Las piezas viejas de N en adelante quedan en Crear como historial.
- **Reinicio del worker**: lo cubren las continuaciones y la recuperación de Crear. Un eslabón que no llegó a
  correr se vuelve a encolar (`max_intentos=2`, es gratis y no repite lo pagado: la sesión siguiente ya
  existente no se vuelve a crear).
- **Nada se cobra dos veces**: cada escena tiene su `job_id` de Crear (un clic repetido no hace nada) y el
  eslabón no lanza una escena que ya tiene `cf_id` con estado vivo.

## 6. Etapa 0: prueba real antes de programar

Script en el scratchpad (no en el repo), con el crédito de WaveSpeed de Creatv, unos US$ 2–3: dos escenas cortas
(5 s) de HappyCozy con sus fichas.

1. Crear dos elementos con nuestras fichas de personaje (una imagen con varias vistas): ¿Kling las acepta como
   `frontal_image` + `refer_images`? Si pide fotos distintas, probar recortes de la ficha.
2. Escena 1 por `reference-to-video`; sacar su último fotograma.
3. Escena 2 por `image-to-video` con ese fotograma y los dos elementos: ¿arranca de verdad en el fotograma?, ¿se
   mantiene 9:16?, ¿cómo se nombran los elementos en el prompt para que se usen?

**Sale bien** si la escena 2 empieza en el mismo cuadro y con los mismos personajes. **Si sale mal**, se para y
se le cuenta a Daniel antes de seguir; el plan B es la cadena con Wan 3.0 `image-to-video` solo con el
fotograma (más barato, identidad sostenida solo por el fotograma).

## 7. Pruebas

- Puras: `cadena.revisar` (cada motivo), `cadena.precio`, `cadena.prompt_escena`, las transiciones.
- Rutas: aprobar con y sin `total_visto` correcto, de otro proyecto, con la cadena corriendo; «Detener»;
  «Rehacer desde»; el panel con cada estado; textos escapados.
- Worker con proveedor simulado: la cadena completa de 3 escenas; el freno por fallo en la 2; «Detener»; un
  reinicio entre escenas; la edición final.
- ffmpeg real (marcada `slow`): el último fotograma de un video de prueba.
- i18n: las guardias `tests/test_i18n_*.py`.

## 8. Fuera

Aprobar escena por escena o por tandas; otros modelos que no sean Kling O3 Pro (salvo el plan B); generar las
variantes de hook (clip 1 alternativo); música; producir la final automáticamente; generar las imágenes «por
crear» desde aquí.
