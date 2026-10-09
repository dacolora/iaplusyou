# Triple Whale: tres ganchos nuevos sobre el video original y copy nuevo para Meta (2026-10-09)

Segunda etapa de las tarjetas de análisis (spec `2026-10-08-triple-whale-tarjetas-analisis-design.md`, en producción
desde el 2026-10-08, main a0226183). Cierra PND-180 en su mitad «cambiar solo el gancho» y PND-182 en su mitad «copy
nuevo». La comparación v1↔v2 (la otra mitad de PND-180) y la predicción (PND-181) son las etapas siguientes, cada una
con su spec.

## 1. Qué pidió Daniel y qué decidió

- 2026-10-08: que la pestaña Triple Whale diga, por anuncio, en qué falló y cómo mejorarlo. «Esto es lo más
  importante: por esto la app va a ser la mejor del mundo.»
- 2026-10-09, «sigue con las siguientes etapas». Eligió estas opciones, todas las recomendadas:
  - **Orden:** primero «gancho nuevo» (más el copy para Meta en el mismo análisis), después v1 contra v2 y después la
    predicción.
  - **Ganchos:** 3 variantes por clic, ≈ US$ 1.
  - **Enlace v1↔v2:** un código en el nombre del anuncio. Esta etapa solo crea el código y lo muestra; la etapa
    siguiente lo lee en la sincronización.
  - **Predicción:** fuerte, medio o débil, sin números. Es de la etapa 3, no de esta.

**La idea:** el anuncio ya probó su cuerpo (producto, demostración, oferta). Lo que más se gasta sin vender suele
perderse en los primeros 3 segundos. Generar solo esos 3 segundos cuesta una fracción de un video nuevo y deja tres
anuncios listos para subir, cada uno con su código.

## 2. Alcance

**Entra:**

1. **El análisis trae dos cosas más:** `ganchos` (3 propuestas de los primeros 3 s) y `copy_nuevo` (título y texto
   para Meta en el idioma del anuncio).
2. **Botón «Probar los 3 ganchos».** Con un clic y el precio a la vista, hace esto con cada gancho:
   - genera un clip de 3 s con Kling O3 Pro, imagen a video, que arranca en un fotograma del original;
   - arma una edición con el clip + el original desde el segundo 3 + el audio original entero + el texto del gancho;
   - la produce (gratis) en el destino del anuncio.
3. **El código `CV<id>` de cada variante,** para el nombre del anuncio en Meta, con botón «Copiar».
4. **En el detalle del análisis:** el estado de cada variante, el video listo y los enlaces al editor y a Crear.

**No entra:**

- Publicar o duplicar el anuncio en Meta: toca lo público y la pauta (PND-182).
- Leer el código en la sincronización y comparar anillos. Es la etapa 3.
- TikTok: Triple Whale da una página, no un archivo (PND-183).
- Anuncios de imagen: reciben `copy_nuevo`, pero no ganchos.
- Volver a pedir un análisis viejo solo para tener ganchos (PND nuevo, §11).

## 3. El análisis trae ganchos y copy

### 3.1 Lo que se le pide a Claude

En `triple_whale/mejorar.py`, `PROMPT` suma dos claves al JSON y estas reglas:

```
 "ganchos": [{"texto": "texto en pantalla, máximo 8 palabras, en el idioma del TEXTO DEL ANUNCIO",
              "escena": "qué se ve en esos 3 s, máximo 40 palabras",
              "prompt": "English prompt for a 3-second image-to-video clip that starts on the chosen frame, 30 to 80 words",
              "fotograma_s": 4.2,
              "por_que": "qué arregla frente al gancho actual y por qué debería retener más"}],
 "copy_nuevo": {"titulo": "máximo 40 caracteres, en el idioma del TEXTO DEL ANUNCIO",
                "texto": "el texto principal del anuncio, máximo 500 caracteres, mismo idioma",
                "por_que": "qué cambia frente al copy actual"}
```

Reglas nuevas del prompt:

- **Ganchos:**
  - exactamente 3, distintos entre sí (otra pregunta, otro dolor, otra demostración, otra prueba), con la misma
    promesa del anuncio;
  - van solo si hay fotogramas del video; si no, `"ganchos": []`;
  - el clip nuevo reemplaza los 3 primeros segundos y la voz original sigue sonando debajo (es la del bloque VOZ), así
    que el texto tiene que funcionar con esa voz;
  - `fotograma_s` es el segundo de uno de los fotogramas que Claude vio, uno donde se vea bien el producto: el clip
    arranca en esa imagen;
  - el `prompt` describe movimiento y cámara durante 3 s desde esa imagen, sin pedir textos, subtítulos ni logos (el
    texto lo pone el editor).
- **Copy:** usa solo las ofertas, descuentos, precios y plazos que aparecen en el texto del anuncio o en los datos;
  nunca inventa uno.
- **Idiomas:**
  - `texto` y `copy_nuevo` (título y texto) van en el idioma del TEXTO DEL ANUNCIO;
  - `escena`, `por_que` y `copy_nuevo.por_que` van en el idioma pedido;
  - `prompt`, en inglés.

  `system()` dice estas tres excepciones en su `extra`. Es una excepción justificada a «lo que se guarda va en el
  idioma del proyecto»: el texto va dentro de un anuncio que se publica en el país de la tienda (un anuncio noruego
  lleva texto en noruego aunque el proyecto esté en español).

### 3.2 Cómo se lee

`parsear` no se vuelve más exigente: un análisis sin ganchos o sin copy sigue siendo válido y no paga una corrección.

- **`_ganchos(lista, verificable, duracion_s)`:**
  - acepta hasta 3 ganchos con `texto` y `prompt`;
  - recorta `texto` a 60 caracteres, sin saltos de línea ni caracteres de control;
  - recorta `escena` a 300, `por_que` a 300 y `prompt` a 1 000;
  - `fotograma_s` sale de un número; si no está en [0, duracion − 1], queda `duracion / 2` (sin duración, `None`, y la
    preparación usa la mitad del video medido);
  - cada gancho lleva `cifras_sin_dato` de `texto` + `por_que` (`doctrina.verificar_cifras`).
- **`_copy_nuevo(d, verificable)`:** devuelve `None` sin `texto`; si no, `{"titulo", "texto", "por_que",
  "cifras_sin_dato"}`.
- **El resultado** suma `"ganchos": [...]` y `"copy_nuevo": {...} | None`. Los análisis viejos no traen esas claves, y
  el código las lee siempre con `.get`.

**Una cifra inventada no entra a un video.** Un gancho con `cifras_sin_dato` se muestra con el aviso y no se genera, ni
entra en el precio (la misma regla que el aprendizaje, revisión B2 del 2026-10-08). El copy con cifras sin dato se
muestra con el aviso «revisa antes de publicar», porque copiarlo es decisión de la persona.

### 3.3 Medición y tarifa

- Se repite eval-claude con los 4 casos del 2026-10-08. La «línea base» son los números de ese eval y el «después», la
  rama. Gasto ≈ US$ 0,40, menos de US$ 1, así que no se pregunta.
- **Criterio:**
  - ningún caso deja de validar;
  - los casos con fotogramas traen 3 ganchos con `fotograma_s` entre los segundos vistos;
  - todos traen `copy_nuevo` en el idioma del anuncio.
- **La tarifa** `analisis_anuncio_tw` (0,10) sube a 0,12 solo si el promedio medido, contando las correcciones, pasa
  de 0,10. Va al eval `docs/superpowers/evals/2026-10-09-tw-ganchos-y-copy.md`.

## 4. «Probar los 3 ganchos»

### 4.1 Cuándo se ofrece y qué cuesta

**El botón aparece en el detalle del análisis si se cumplen todas estas condiciones:**

- el análisis está `lista`;
- tiene al menos un gancho sin `cifras_sin_dato`;
- el video original está permitido: `mejorar._url_voz(foto)`, es decir, el mp4 de `files.triplewhale.com` o el video
  de R2 de una pieza de Creatv;
- `foto.creativo.duracion_s`, si se conoce, es de al menos 5 s;
- no hay una tanda viva de ese análisis (§4.2).

**Precio:**

- `precio = n × gastos.estimar("video", modelo="kling_o3_pro", duracion=3, con_sonido=False)["usd"]`, donde `n` es el
  número de ganchos que se generan (hoy 0,336 cada uno: 3 = US$ 1,01).
- `gastos.estimar_ganchos_tw(n)` lo envuelve, así la ruta y la plantilla calculan lo mismo.
- La plantilla lo muestra con `|precio|usd` (con el margen de Cobros) en el botón, más `data-confirmar` con el número
  de clips y el precio.
- Sin precio conocido, el botón dice «precio no disponible» y no se puede pedir.

### 4.2 Datos: tabla `tw_gancho` (migración 0035)

Una fila por variante. Su único escritor es `triple_whale/datos.py`.

| columna | qué |
|---|---|
| `id` | INTEGER PK AUTOINCREMENT; es también el código `CV<id>` |
| `cliente`, `analisis_id` | el análisis del que nace (de ese cliente) |
| `tanda`, `n` | número de tanda dentro del análisis (1, 2…) y de la variante (1–3); UNIQUE (`analisis_id`, `tanda`, `n`) |
| `estado` | `preparando` → `generando` → `armando` → `produciendo` → `lista`, o `error` |
| `texto`, `prompt`, `fotograma_s` | copia del gancho al pedirlo (el resultado del análisis no se toca) |
| `frame_url`, `cf_id` | fotograma de arranque en R2 y sesión de Crear del clip |
| `edicion_id`, `final_id`, `url_final` | edición armada, final producida y su video |
| `job_id` | el trabajo de la etapa en curso (lo que sondea la pantalla) |
| `error` | el motivo en palabras, en el idioma del proyecto |
| `pedido_por`, `creado_en`, `actualizado_en` | quién y cuándo |

- **`crear_tanda(cliente, analisis_id, ganchos, pedido_por)`:**
  - con el candado del módulo tomado ANTES de leer, mira si hay filas vivas del análisis (estado distinto de `lista` y
    de `error`); si las hay, lanza `TandaViva`;
  - si no, inserta las filas de la tanda `max + 1` en una sola transacción y devuelve sus filas;
  - el UNIQUE es la red si dos procesos llegan a la vez.
- **`mover(gid, de, a, **campos)`:** `UPDATE … WHERE id = ? AND estado = ?`. Devuelve si cambió, así el vigilante y las
  tareas nunca avanzan dos veces la misma variante.
- **`ganchos_de_analisis(cliente, analisis_id)`, `ganchos_vivos()`:** para el detalle y para el vigilante, con una
  consulta cada una.

### 4.3 La ruta

`POST /cliente/<c>/triple-whale/analisis/<int(max=…):aid>/ganchos` (`triple_whale/rutas.py`, `ganchos_probar`):

1. `_solo_mismo_origen`; el análisis tiene que ser de ese cliente (si no, 404).
2. Revisa todo lo de §4.1 (si algo falla, 409 con el motivo en palabras).
3. **`precio_visto`** (es precio, vuelve a costo con `gastos.costo_de_precio`) tiene que coincidir con el precio
   recalculado ±0,005. Si no, 409 «El precio cambió…», como la cadena de escenas.
4. **`libro.exigir(cliente, precio)`:** sin saldo, `SaldoInsuficiente` sube al manejador de siempre y no se guarda ni se
   encola nada.
5. **`datos.crear_tanda(…)`:** `TandaViva` da 409.
6. **Encola `tw_ganchos_preparar`:**
   - job_id `f"{cliente}__tw_ganchos_{aid}_t{tanda}"`, `max_intentos=1`, `cliente=cliente`, prioridad 3;
   - guarda ese job_id en las filas.
   - Si el encolado falla, las filas pasan a `error` con el motivo.
7. **Responde:** JSON `{"ok": true}` si vino de `fetch`, o redirect al panel con un flash si es un POST de formulario.
   La pestaña ya tiene el patrón asíncrono de «Cómo mejorarlo», que nunca reenvía el POST.

### 4.4 Preparar (`tw_ganchos_preparar`, gratis en sí)

Está en `tareas/triple_whale.py` y entra en `TIPOS_EXENTOS_DE_COBRO` con el motivo «baja el video y lanza piezas de
Crear; cada pieza la cobra flowplus_video».

1. **Baja el original** con `conectores.url.descargar_archivo` (60 MB, solo `video/*`, SSRF por redirección) a
   `salidas/<c>/tw_ganchos/<aid>_t<tanda>/original.mp4`. Exige `mejorar.es_mp4` antes de darle el archivo a ffmpeg y
   mide su duración y tamaño con ffprobe.
2. **Material del original** para el editor, gratis y deduplicado por hash:
   `materiales.subir(cliente, ruta, f"clientes/{c}/materiales/{hash}.mp4", "video/mp4", tipo="video",
   origen="triple_whale", duracion_ms=…, ancho=…, alto=…, extra={"nombre": <nombre del anuncio>, "tiene_audio": …,
   "local": ruta, "ad_id": …})`.
   - Se encola su `edicion_proxy` como en `insumos.clon`.
   - `origen="triple_whale"` entra en `final_edition.biblioteca.ORIGENES_BIBLIOTECA`, así el original aparece en
     «Medios» del editor y se puede reusar.
3. **Por cada fila de la tanda que todavía no tenga `cf_id`** (así una corrida repetida no lanza dos veces):
   1. Saca el fotograma en `fotograma_s` con ffmpeg (`-ss` antes de `-i`, un cuadro, jpg) y lo sube con
      `r2_uploader.upload_image(jpg, f"clientes/{c}/triple_whale/ganchos/{gid}.jpg")`. Lo guarda en `frame_url`.
   2. Crea la sesión de Crear como `tareas.cadena.lanzar_escena` hace con una escena con imagen de arranque:
      ```python
      cf_id = creative_flow.crear(cliente, [], [], [], accion, 3, "", "A", referencias_urls=[], platforms=[])
      creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt, prompt_fuente=prompt, tipo="video",
                               modelo="kling_o3_pro", aspect_ratio=<el de Kling más cercano al original>,
                               con_sonido=False, sonido_texto="", musica_estilo="", calidad="final",
                               imagen_inicial=frame_url, elementos=[],
                               referencias=[{"tipo": "imagen", "url": frame_url, "frame_url": frame_url,
                                             "etiqueta": "@Imagen 1", "titulo": f"CV{gid}"}],
                               tw_gancho={"gancho_id": gid, "analisis_id": aid})
      ```
      `accion` es «Gancho n · <nombre del anuncio>», en el idioma del proyecto.
   3. `flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=3)`. Si devuelve falso, la fila pasa a `error`.
   4. La fila pasa a `generando`, con `cf_id` y `job_id = flowplus_lanzar.job_id(cliente, cf_id)`.
4. **Fallos:**
   - `SaldoInsuficiente` al lanzar una variante: esa fila y las que faltan pasan a `error` con `e.frase_proyecto()`, y
     las ya lanzadas siguen su camino.
   - Cualquier otra excepción antes de lanzar: las filas sin `cf_id` pasan a `error` con `texto_error`, sin rutas ni
     tokens.
   - El temporal del original se borra al final; el material ya guardó su copia en R2.

### 4.5 Vigilar (`tw_ganchos_vigilar`, periódica, cada 60 s, gratis)

Va en `worker.py` con las periódicas, junto a `cadena_vigilar`. Para cada fila viva (`ganchos_vivos()`, una consulta):

- **`generando`:**
  - si la sesión sigue en `VIVOS_CREAR`, no hace nada;
  - si está en `video_listo`, mueve la fila a `armando` y encola `tw_gancho_armar`
    (`f"{cliente}__tw_gancho_{gid}_armar"`, `max_intentos=2`, prioridad 1);
  - si la sesión ya no está o terminó en otro estado, la fila pasa a `error` con el error de la sesión.
- **`produciendo`:** mira la final (`creative_flow.final_por_legado(cliente, final_id)`).
  - Con `video_url` y estado listo o degradada, la fila pasa a `lista` con `url_final`.
  - Si la final está en `error`, la fila pasa a `error` con su motivo.
- **`preparando` o `armando`:** si su `job_id` ya no está vivo en la cola (`trabajos.en_curso` falso) y la fila no
  avanzó, pasa a `error` («la preparación se cortó»). Así ninguna tanda queda viva para siempre bloqueando el botón.

Una fila rota no frena a las demás: try/except por fila con `log.exception`, igual que `cadena_vigilar`.

### 4.6 Armar y producir (`tw_gancho_armar`, gratis)

Exento con el motivo «arma con ffmpeg y el editor un clip ya pagado y el original».

1. **Material del clip:** `biblioteca.materializar_pieza(cliente, cf_id, carpeta)`, el mismo de la cadena. El del
   original se busca por hash (§4.4.2); si falta (la base se limpió), se vuelve a bajar como en §4.4.1.
2. **Documento:** `triple_whale/ganchos.py`, `documento_gancho(clip, original, texto, formato, idioma, pais)`, una
   función pura y probada sola.
   - **Pista principal:**
     - `v0`: el clip, de 0 a `g = min(duración del clip, 3000)` ms, con volumen 0;
     - `v1`: el original, con recorte `desde_ms = g` hasta su final, desde `inicio_ms = g` y con volumen 0.
   - **Pista `p_sonido`:** el audio del original entero, desde 0, recorte 0–duración y volumen 1. Así, en el segundo 3
     se ven y se oyen los mismos 3 s del original y la voz sigue en sincronía. Sin audio en el original no hay
     `p_sonido`.
   - **Pista `p_texto`:** `{"literal": texto}` de 0 a `g`, con `borrador.ESTILO_HOOK` y `borrador.POS_HOOK`.
   - **Formato:** el de `documento.FORMATOS` más cercano a ancho/alto del original.
   - **Destino:** `pais` es el de la tienda del análisis si está en `tipos.PAISES`; si no, `proyectos.pais(cliente)`;
     si no, `CO`. `idioma` es el de ese país, y `origen = {"tipo": "triple_whale", "pais": pais, "analisis_id": aid,
     "gancho_id": gid}`.
   - Termina con `documento_mod.validar(doc)`.
3. **Edición:** `ediciones.crear(cliente, "video", f"{nombre del anuncio} · CV{gid}"[:120], doc, cf_id=cf_id,
   creada_por="triple_whale")`.
4. **Producir,** con lo mismo que `rutas_editor.producir` hace después de sus revisiones:
   1. `compilador.verificar_recortes`;
   2. `ediciones.versionar(…, motivo="producir")`;
   3. `creative_flow.crear_final(cliente, cf_id, idioma, pais)`;
   4. `trabajos.encolar(tareas_edicion.job_id_producir(…), "edicion_producir", {…}, max_intentos=1)`.

   Esos pasos 2 a 4 se extraen de la ruta a una función compartida,
   `rutas_editor.encolar_producciones(cliente, edicion_id, ed, version, destinos)`. La usan la ruta y la tarea, y lo que
   la ruta hace no cambia: sus pruebas siguen en verde sin tocarlas.
5. La fila pasa a `produciendo` con `edicion_id`, `final_id` y `job_id` del render. Un error pasa la fila a `error`
   con el motivo; con `max_intentos=2`, el segundo intento rehace desde el punto 1 (nada de esto cobra).

La final queda colgada de la sesión del clip: se ve en Crear y en Final edition como cualquier otra, y se puede abrir
en el editor para cambiar el texto o el corte.

### 4.7 El código `CV<id>`

- **`codigo(gid) = f"CV{gid}"`** (en `triple_whale/ganchos.py`). Es único en toda la base porque es el id de la fila.
- **En el detalle,** cada variante muestra el código con un botón «Copiar» (el `onclick` con `navigator.clipboard` que
  ya usa `_meta_agencia_cliente.html`) y el texto «Pon este código en el nombre del anuncio en Meta: así Creatv lo
  compara con el original».
- La comparación es de la etapa 3; esta solo garantiza que el código existe y se ve.
- `codigo_en(nombre)`, con la regex `\bCV(\d+)\b` (sin distinguir mayúsculas), queda escrita y probada para la etapa
  siguiente.

## 5. Pantalla (`templates/_tw_analisis.html`)

**«Copy nuevo para Meta»,** si `r.get('copy_nuevo')`, va antes de «Versión mejorada»:

- el título y el texto, cada uno con su botón «Copiar»;
- `por_que` en gris;
- el aviso si trae `cifras_sin_dato`.

**«Ganchos nuevos (primeros 3 s)»,** si `r.get('ganchos')`:

- **Cada gancho muestra:**
  - el texto entre comillas (es lo que irá en pantalla);
  - la escena y el porqué;
  - el prompt en un `<details>`;
  - el aviso si trae cifras sin dato: «No se genera: cita cifras que no están en los datos».
- **El botón** «Probar los 3 ganchos · US$ X» (o «Probar los 2…» si uno quedó fuera) va con `data-confirmar`, un input
  oculto `precio_visto` y el mismo patrón asíncrono de la pestaña. No se muestra si §4.1 no se cumple; en su lugar va
  una línea que dice por qué: «hay una tanda en curso», «sin video que se pueda bajar» o «video muy corto».
- **Por cada variante de la tanda más reciente:**
  - **viva:** el estado en palabras (Preparando, Generando el clip, Armando el video, Produciendo), el código y una
    barra `data-poll-job="{{ g.job_id }}"` con `data-poll-al-terminar="evento"`; el JS de la pestaña, que ya escucha
    `trabajo-terminado`, vuelve a pedir el detalle;
  - **`lista`:** `<video controls preload="none" data-precarga src=url_final>`, el código con «Copiar», un enlace
    «Descargar» (`url_final`), «Abrir en el editor» (la ruta del editor con `edicion_id`) y «Ver en Crear»;
  - **`error`:** el motivo.
- **Tandas anteriores:** solo una línea, «Antes: N tandas · ver», con un `<details>` que muestra los códigos y los
  enlaces de sus listas. Nada de una consulta por variante: `ganchos_de_analisis` trae todo en una.

**Un análisis viejo sin `ganchos`** muestra una línea: «Este análisis es de antes de los ganchos». Sin botón.

Todo sigue sin `<script>` en el fragmento y con lo de Claude escapado.

## 6. Plata (regla 1)

- **Precio:**
  - va a la vista antes, con el margen, `data-confirmar` y `precio_visto` comparado en el servidor;
  - `libro.exigir` del total antes de crear nada;
  - cada clip reserva lo suyo al encolarse (`flowplus_lanzar.lanzar` con `costo_estimado`).
- **Cobro:**
  - cada clip lo cobra y lo anota el cierre de Crear (`flowplus_video`, `max_intentos=1`, la recuperación de WaveSpeed,
    el gasto real con su referencia);
  - preparar, vigilar y armar no llaman a ningún proveedor que cobre;
  - el render es ffmpeg.
- **Nada avanza solo de un paso pagado a otro pagado.** Lo único pagado son los 3 clips, aprobados con un clic. Armar y
  producir son gratis.
- **Doble clic:** job_id determinista, `TandaViva` y UNIQUE. Una tanda en curso no se puede volver a pedir.
- **`guardian-gasto` revisa la rama** antes de mezclar.

## 7. Seguridad

- **La ruta:**
  - mismo origen;
  - el análisis tiene que ser del cliente de la URL;
  - `aid` con `int(max=…)`;
  - `precio_visto` numérico.
- **El archivo que se descarga:**
  - el video ajeno solo se pide con `conectores.url.descargar_archivo` y a un host de `medio_permitido`;
  - ffmpeg solo lo abre si ffprobe (`-protocol_whitelist file`) dice mp4/mov.
- **El texto de Claude** sale de un análisis que leyó texto ajeno (el copy del anuncio):
  - el `prompt` llega a Kling (pagado) solo después de que la persona lo pudo leer y aprobó el precio;
  - el `texto` llega al video recortado y sin caracteres de control;
  - todo se muestra escapado.
- **Aislamiento:** cada clave de R2 lleva `clientes/<c>/`; las filas llevan `cliente` y cada lectura filtra por él.
- **`auditor-seguridad` revisa la rama.**

## 8. Idioma

- Lo visible pasa por `gettext` o `_()`, y el catálogo se actualiza, se traduce con `docs/i18n/glosario.md` y se
  compila.
- `accion`, `error` y el nombre de la edición se guardan en el idioma del proyecto (`idiomas.en_idioma(…)` en la tarea).
- El texto del gancho y el copy nuevo van en el idioma del anuncio, por decisión de §3.1; el prompt a Kling, en inglés.

## 9. Archivos

- **Nuevo:**
  - `triple_whale/ganchos.py`: `codigo`, `codigo_en`, `documento_gancho`, `formato_cercano`, `aspecto_kling`, `destino`;
  - `migrations/versions/0035_tw_gancho.py`.
- **Cambian:**
  - `db.py` (tabla);
  - `triple_whale/datos.py` (tanda, mover, consultas);
  - `triple_whale/mejorar.py` (prompt, system, `_ganchos`, `_copy_nuevo`);
  - `tareas/triple_whale.py` (3 tareas);
  - `tareas/__init__.py` (exentas);
  - `worker.py` (periódica);
  - `gastos.py` (`estimar_ganchos_tw`);
  - `triple_whale/rutas.py` (ruta y contexto del detalle);
  - `templates/_tw_analisis.html`;
  - `templates/_tab_triple_whale.html` (re-pedir el detalle al terminar);
  - `static/estilos/pantallas/triple-whale.css` y el `style.css` generado;
  - el catálogo;
  - la skill `triple-whale`;
  - `docs/pendientes.md`.
  - `final_edition/rutas_editor.py` (extraer `encolar_producciones`);
  - `final_edition/biblioteca.py` (`ORIGENES_BIBLIOTECA`).

## 10. Pruebas y verificación

- **Unitarias** (sin red ni proveedores):
  - `_ganchos` y `_copy_nuevo`: límites, `fotograma_s` fuera de rango, cifras sin dato, análisis viejo;
  - `documento_gancho`: tiempos, volúmenes, recortes, sin audio, formatos, validar;
  - `codigo` y `codigo_en`;
  - `crear_tanda` (`TandaViva`, numeración) y `mover` (que no avance dos veces);
  - ruta: mismo origen, otro cliente, precio cambiado, sin saldo, tanda viva, análisis sin ganchos, sin video;
  - preparar: lanza n, no relanza una fila con `cf_id` y maneja `SaldoInsuficiente` a mitad;
  - vigilar: cada transición, sesión en error y trabajo muerto;
  - armar: documento y encolado del render;
  - plantilla: botón con precio, estados, el `<video>` con `preload="none"`, el código y que no haya `<script>`.
- **Suite entera en verde.**
- **eval-claude** de §3.3, ≈ US$ 0,40.
- **Prueba real de UNA variante** (≈ US$ 0,34; el total con el eval queda por debajo de US$ 1): con una base temporal
  sembrada de la exportación de producción, como el 2026-10-08, se corre el camino real:
  1. preparar (Kling 3 s de verdad, para confirmar que WaveSpeed acepta 3 s en imagen a video);
  2. vigilar;
  3. armar;
  4. producir en local.

  Se mira el mp4 final: el corte en el segundo 3, la voz en sincronía y el texto.
- **Captura** del detalle con el test client (render del fragmento con datos sembrados), en escritorio y celular.
- **Revisiones:** `revisor`, `guardian-gasto` y `auditor-seguridad` antes de mezclar.

## 11. Pendientes que nacen

- **Chip en la tarjeta de la galería** («2 ganchos listos») para verlos sin abrir el análisis.
- **«Volver a analizar»** para un análisis viejo sin ganchos aunque esté fresco (hoy el panel no ofrece pagar dos veces
  el mismo alcance).
- **Ganchos para anuncios de imagen:** otra imagen de portada en vez de un clip.
- **Los 3 ganchos en Meta en pausa con su código,** si Daniel lo quiere (toca lo público: se pregunta antes).
