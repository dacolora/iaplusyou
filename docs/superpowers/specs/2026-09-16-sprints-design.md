# Sprints de contenido — diseño

Fecha: 2026-09-16. Estado: aprobado por secciones en conversación; pendiente de
revisión escrita. Tres partes, cada una del tamaño de un plan de implementación.

## 0. Propósito y relación con el motor de ecommerce

Un **sprint** planifica y produce en volumen el contenido mensual de un proyecto
(el servicio Creatv Grow: ~30 piezas al mes con la identidad de la marca) a
partir de una matriz de **campañas** = persona × producto × temporada, con
referencias visuales cargadas de forma progresiva, generación con IA por lotes,
control de calidad automático, bandeja de revisión y final edition (texto,
plantillas, idiomas) también para imágenes.

Decisión de arquitectura (con Daniel, 2026-09-16): el sprint es una **capa de
planificación y producción encima de Crear**. Cada pieza planeada se convierte en
una sesión de Crear (`creative_flow.crear`) y la generan las tareas que ya existen
(`flowplus_imagen`, `flowplus_video`). Final edition de video se reutiliza tal
cual. Los experimentos de pauta siguen siendo del motor de ecommerce
(`docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md`); una pieza del
sprint entra a un experimento con el "Meter en experimento" de hoy. El sprint no
toca catálogo/conectores (bloque 5), tablero (bloque 6) ni el decisor.

Qué existe y qué es nuevo:

| Concepto | Estado hoy |
|---|---|
| Producto | Catálogo de Crear (`catalogo_productos`, carpeta por producto); tabla `producto` del bloque 5 |
| Persona (arquetipo de cliente) | No existe (los "personajes" son voceros visuales) |
| Temporada | No existe |
| Sprint / campaña | No existe (el único agrupador es `experimento`, con forma de Meta) |
| Referencias | Bandeja de Crear: URL + `@Imagen N`, sin intención ni descripción persistida |
| Análisis de referencias con IA | Parcial: `referencias_link.describir`, `analizar_marca` |
| Prompt maestro | Parcial: `flowplus_prompt.armar` mezcla producto + marca + referencias + enfoque |
| Generación de imágenes y videos | Existe por sesión (`tareas/flowplus.py`) |
| Control de calidad automático, progreso agregado | No existe |
| Final edition de video, multiidioma, precio por destino | Existe (bloque 2) |
| Final edition de imágenes, plantillas de texto | No existe (`texto.py` son constantes) |

Filosofía que se mantiene: nada gasta crédito sin un clic con el costo a la
vista, y ningún paso caro se reintenta solo.

---

## Parte 1 — Planificación

### 1.1 Modelo de datos

Migración Alembic nueva, encadenada a la última que exista al implementar (el
bloque 5 puede haber agregado otras). Convenciones del motor: `id`, `cliente`
(indexado), `creado_en`, `actualizado_en` (`db._comunes()`), JSON para listas,
`extra` JSON para lo que no merece columna.

**persona**: `nombre`, `resumen` (una línea), `descripcion` (quién es, qué le
importa, qué le duele), `edad_rango` (texto, ej. "25-40"), `tono` (cómo
hablarle), `senales_visuales` (json: escenarios, estilo de vida, objetos),
`palabras_clave` (json[]), `color` (hex, para el tablero), `origen`
(`manual|sugerida_ia`), `archivada` (bool), `extra`.

**temporada**: `nombre`, `inicio` (fecha `YYYY-MM-DD`), `fin`, `contexto` (qué
pasa, qué se vende, qué emoción), `mood_visual` (json: paleta, luz, elementos),
`tipo` (`comercial|estacional|propia`), `archivada`, `extra`.

**sprint**: `nombre`, `inicio`, `fin`, `estado` (§1.3), `destinos` (json[] de
`"<idioma>_<pais>"`, por defecto los del proyecto), `referencias_objetivo_defecto`
(int, defecto 5), `notas`, `extra` (json: `qa_umbral`, modelos elegidos para el
lote, costo acumulado).

**campana**: `sprint_id` (FK), `persona_id` (FK), `catalogo_id` (string: id de la
carpeta del producto en el catálogo de Crear), `producto_id` (FK nullable a
`producto`, para cuando el bloque 5 enlace catálogo y tabla), `temporada_id` (FK),
`n_videos` (int), `n_imagenes` (int), `referencias_objetivo` (int, hereda del
sprint), `estado` (§1.3), `orden` (int), `extra`.
`UNIQUE(sprint_id, persona_id, catalogo_id, temporada_id)` (`uq_campana_combinacion`).

**referencia**: `campana_id` (FK), `tipo` (`imagen|video`), `url` (R2),
`frame_url` (video: fotograma extraído), `ruta_local`, `origen`
(`archivo|link|catalogo|reutilizada`), `titulo`, `intencion` (json[] con
etiquetas del vocabulario fijo `estilo_visual, composicion, paleta,
movimiento_camara, tipografia, transiciones, storytelling, iluminacion,
angulo_producto, otro` y, si `otro`, `intencion_otro` texto), `descripcion`
(texto; obligatoria para que la referencia cuente), `analisis` (json, §1.5),
`analisis_estado` (`pendiente|listo|error`), `estado` (`borrador|lista`,
derivado: `lista` si tiene descripción), `orden`, `extra`.

**sprint_evento**: `cliente`, `sprint_id`, `campana_id` (nullable), `tipo`
(string corto), `mensaje`, `datos` (json), `creado_en`. Línea de tiempo legible
del sprint (mismo espíritu que `evento` del motor, que es por experimento).

`campana_pieza` se define en la Parte 2 pero se crea en la misma migración.

### 1.2 Validaciones

- `inicio < fin` en sprint y temporada.
- `n_videos >= 0`, `n_imagenes >= 0`, `n_videos + n_imagenes >= 1`.
- Un sprint sale de `planeando` solo con al menos una campaña.
- Persona + producto + temporada única por sprint: la interfaz deshabilita la
  combinación repetida con "ya existe en la campaña N"; el servidor la rechaza
  con el mismo mensaje (captura del `IntegrityError` del índice único).
- Persona, temporada y producto deben pertenecer al mismo `cliente` del sprint.
- Una referencia sin `descripcion` se guarda (`borrador`) pero no suma al progreso.

### 1.3 Estados y su recálculo

Sprint: `planeando → referencias → listo_para_generar → generando → revision →
completado`. Además `archivado` (bandera, no estado).

Campaña: `planeada → referencias → ideas_propuestas → ideas_aprobadas →
generando → revision → completada`.

Los estados se guardan y `sprints/estado.py::recalcular(sprint_id)` los vuelve a
derivar de las campañas después de cada evento (subida de referencia, ideas,
lote, QA, revisión), para que la interfaz nunca mienta:
- campaña `referencias` cuando tiene ≥ 1 referencia; `ideas_propuestas` cuando
  hay ideas; `ideas_aprobadas` cuando las aprobadas cubren `n_videos +
  n_imagenes`; `generando` cuando hay al menos una sesión encolada o generando;
  `revision` cuando todas las piezas planeadas terminaron (listo o error) y
  `completada` cuando cada cupo planeado (`n_videos + n_imagenes`) tiene una
  pieza aprobada, o cuando se cierra el sprint (§2.6). Una idea descartada
  libera su cupo: no cuenta como planeada hasta que se reemplace.
- sprint = `referencias` en cuanto alguna campaña sale de `planeada`; `listo_para_generar` cuando todas alcanzan su objetivo de referencias (o `extra.listo_manual`),
  `generando` si alguna genera, `revision` si todas están en revisión o
  completadas y al menos una en revisión, `completado` al cerrar (§2.6).

El sprint aconseja, no bloquea: "Marcar listo para generar" está disponible
aunque falten referencias, con un aviso de lo que falta; queda registrado en
`sprint_evento`.

### 1.4 Progreso

Funciones puras en `sprints/progreso.py`, con pruebas:
- Campaña en referencias: `min(referencias_listas / referencias_objetivo, 1)`.
- Campaña en producción: `piezas_listas / (n_videos + n_imagenes)`.
- Campaña en revisión: `piezas_aprobadas / (n_videos + n_imagenes)`.
- Sprint: promedio de las campañas **ponderado por piezas planeadas** (una
  campaña de 25 piezas pesa más que una de 3), más el contador "N de M piezas".
- Cobertura de intención: para campañas con `n_videos > 0`, se sugiere tener al
  menos una referencia con `movimiento_camara` o `transiciones`; con
  `n_imagenes > 0`, al menos una con `composicion` o `angulo_producto`. Es una
  sugerencia en pantalla, no una validación.

### 1.5 Análisis de referencias con IA

Al subir una referencia se encola `sprint_analizar_referencia`
(`payload {cliente, referencia_id}`, `max_intentos=3`, barato). Claude con visión
sobre la imagen o sobre tres fotogramas del video (extraídos con la utilidad de
`referencias_link.fotogramas`), con las etiquetas de intención como foco.
Escribe en `referencia.analisis`:

```
{resumen, paleta: [hex], composicion, iluminacion, movimiento, tipografia,
 estetica, storytelling, elementos: []}
```

Módulo `sprints/analisis.py` (prompt en el estilo de
`referencias_link.DESCRIPCION_PROMPT`, salida JSON validada; si Claude no
devuelve JSON válido se reintenta una vez con la corrección en el prompt).
Se puede regenerar desde la tarjeta. Este análisis alimenta el prompt maestro
(§2.1).

### 1.6 Experiencia de usuario

Pestaña nueva **Sprints** en la barra lateral (`data-tab="sprints"`,
`templates/_tab_sprints.html` y parciales), mismo patrón de pestañas de
`cliente.html`. Rutas en un Blueprint `sprints/rutas.py` registrado en
`dashboard.py` bajo `/cliente/<cliente>/sprints/...`, con el mismo guard por
cliente. Personas y Temporadas son sub-secciones de la pestaña.

1. **Lista de sprints**: tarjetas con nombre, fechas, chip de estado, anillo de
   progreso, "4 campañas · 60 piezas", costo estimado y gastado. Botón "Nuevo sprint".
2. **Nuevo sprint** (asistente en la misma página, tres pasos): (a) nombre,
   fechas (por defecto el mes siguiente), destinos; (b) **matriz persona ×
   producto** con la temporada como filtro arriba: cada celda es una campaña
   posible, clic para abrirla y fijar videos e imágenes; celda ya usada en esa
   temporada en gris con "ya existe"; el total de piezas y el costo estimado se
   actualizan en vivo con los modelos por defecto del proyecto
   (`flowplus_modelos.estimate_video/estimate_imagen`); también existe "Agregar
   campaña" como formulario; "+ Nueva persona" y "+ Nueva temporada" abren un
   modal sin salir; (c) resumen y crear.
3. **Personas**: lista y edición; "Sugerir personas" encola
   `sprint_sugerir_personas` (Claude lee `marca.guia_efectiva` y el catálogo,
   propone tres personas completas con `origen=sugerida_ia`, editables).
   **Temporadas**: lista y edición; presets del calendario comercial en
   `sprints/calendario.py` (por país del proyecto y año en curso: Navidad, Black
   Friday, Día de la madre, Día del padre, Amor y amistad, Regreso a clases,
   Halloween, temporada de lluvias/verano) que se adoptan con un clic.
4. **Detalle del sprint**: cabecera (estado, fechas, anillo global, costo) y
   **tablero de campañas**: una fila por campaña (persona · producto · temporada,
   barra por etapa, contador de referencias, acción contextual: "Subir
   referencias", "Ver ideas", "Generar", "Revisar"). Filtros por persona,
   producto y temporada. Línea de tiempo (`sprint_evento`) al pie.
5. **Referencias de una campaña**: zona de arrastrar y soltar (varios archivos o
   un link, reusando `_guardar_referencia_archivo` y `referencias_link.descargar`
   por detrás), grid de tarjetas; cada tarjeta: miniatura, chips de intención,
   descripción con autoguardado (`PATCH`), estado del análisis (indicador
   mientras corre; al terminar, resumen y paleta como muestras). Botones "Traer
   del catálogo" (fotos del producto, `origen=catalogo`) y "Reutilizar de otra
   campaña" (`origen=reutilizada`, copia la fila). Arriba: "cargadas / objetivo" y
   la sugerencia de cobertura (§1.4).

Roles: un usuario por proyecto y el admin, misma interfaz para ambos.
Aprobaciones por rol quedan fuera (§4).

### 1.7 Módulos y pruebas

`sprints/__init__.py`, `sprints/datos.py` (CRUD y validaciones), `sprints/estado.py`,
`sprints/progreso.py`, `sprints/analisis.py`, `sprints/calendario.py`,
`sprints/sugerencias.py`, `sprints/rutas.py`, `tareas/sprints.py`
(`sprint_analizar_referencia`, `sprint_sugerir_personas`).

Pruebas (pytest): validaciones y unicidad (incluido el `IntegrityError`),
recálculo de estados, progreso ponderado y cobertura, presets del calendario,
rutas con el cliente de pruebas de Flask, análisis y sugerencias con un Claude falso.

---

## Parte 2 — Producción

### 2.1 Ideas por campaña y prompt maestro

"Proponer ideas" (por campaña o para todo el sprint) encola
`sprint_proponer_ideas` (`payload {cliente, campana_id, cuantas}`,
`max_intentos=2`). El **prompt maestro** combina: persona (descripcion, tono,
senales_visuales), producto (nombre, descripcion y `regla` del catálogo),
temporada (contexto, mood_visual), análisis de las referencias (resumen, paleta,
movimiento), guía de marca (`marca.guia_efectiva`) y el banco de prompts como
ejemplos de estilo. Devuelve `n_videos` ideas de video y `n_imagenes` de imagen,
cada una con `titulo`, `tipo`, `escena` (texto que irá a Crear como
`accion_central`), `sonido` (descripción del sonido de la escena, va al prompt
como `SONIDO:`; ver `2026-09-16-final-edition-estudio-design.md` §S1), `enfoque`
(clave de `flowplus_prompt.ENFOQUES`), `gancho`
(frase corta para el texto de final edition), `referencias_ids`, `duracion_s`
(videos, dentro de lo que admite el modelo por defecto) y `plataformas`.
Salida JSON validada; reintento único con corrección.

**campana_pieza** (creada en la migración de la Parte 1): `campana_id` (FK),
`tipo` (`video|imagen`), `titulo`, `escena`, `sonido`, `enfoque`, `gancho`,
`referencias_ids` (json[]), `duracion_s`, `plataformas` (json[]), `estado_idea`
(`propuesta|aprobada|descartada`), `cf_id` (legado_id de la sesión de Crear,
nullable, indexado), `qa` (json, §2.4), `revision`
(`pendiente|aprobada|rechazada`), `revision_motivo`, `textos` (json, Parte 3),
`orden`, `extra`. Los contadores de progreso salen de un `JOIN` con `pieza` por
`legado_id`.

Interfaz: tarjetas con título, tipo, escena editable en línea, chip de enfoque
y miniaturas de las referencias que la inspiran. Acciones: aprobar, descartar,
"otra idea" (regenera solo esa: encola con `cuantas=1` y `reemplaza=cp_id`),
"proponer 3 más", "aprobar todas". Encabezado: "8 de 10 videos · 25 de 25
imágenes aprobadas".

### 2.2 Generación por lotes

"Generar lote" (campaña o sprint) hace, por cada idea aprobada sin `cf_id`:
1. `creative_flow.crear(cliente, personajes_ids=[], productos_ids=[nombre],
   escenas_ids=[], accion_central=escena, duracion_objetivo=duracion_s,
   tono=persona.tono, modo="A", referencias_urls=<referencias de la campaña, las
   de la idea primero>, platforms=<según destinos>, extra_sprint={sprint_id,
   campana_id, cp_id})`. `crear` gana el parámetro opcional `extra_sprint` que se
   guarda en `extra["sprint"]`; la tarjeta en Crear muestra "Sprint Octubre ·
   Campaña 2" con enlace de vuelta.
2. Referencias de la sesión: las del producto en el catálogo (con `producto` y
   `regla`, como hace `cf_crear_video`) más las de la campaña; los logos del
   proyecto se agregan como hoy.
3. Prompt: `flowplus_prompt.armar(..., contexto={"persona": ..., "temporada":
   ...})`. `armar` gana el parámetro opcional `contexto`; cuando viene, emite
   dos líneas al principio del bloque de contexto: `AUDIENCIA: <resumen y
   señales visuales>` y `TEMPORADA: <nombre, contexto y mood>`; con `None` el
   resultado es idéntico al actual (prueba de regresión).
4. `creative_flow.actualizar(prompt_relleno, tipo, modelo)` y encolar con el
   helper compartido (§2.7) `flowplus_video` o `flowplus_imagen`,
   `max_intentos=1`, `prioridad=3`.

**Puerta de costo** antes de encolar: modal con "10 videos (wan3, 8 s) y 25
imágenes (seedream_v5_pro): USD 9,40 estimado · acumulado del sprint USD 12,10 ·
tiempo estimado 1 h 40 min". Modelos por defecto del proyecto, cambiables en el
modal; el estimado usa `estimate_video(modelo, duracion_s)` y
`estimate_imagen(modelo, n_referencias)`; el tiempo, `duracion_estimada` de cada
tarea sumada (el worker es de una tarea a la vez). Al confirmar se registra un
`sprint_evento` con las cantidades y el costo; si hay SMTP configurado
(`notificaciones.py`) se avisa por correo cuando el lote termina.

**Prioridad en la cola**: columna `tarea.prioridad` (int, defecto 5) y
`cola.reclamar` ordena por `prioridad DESC, id`. Los lotes encolan con 3 para que
una pieza suelta de Crear (5) pase antes. `trabajos.encolar` gana el parámetro
`prioridad=5`.

**Progreso agregado**: `GET /cliente/<c>/sprints/<id>/progreso` devuelve
`{planeadas, encoladas, generando, listas, error, aprobadas, costo_usd,
segundos_restantes}` por sprint y por campaña; el tablero lo consulta cada 5 s
con `iniciarPollingSprint` (mismo CSS de barra que `iniciarPolling`). Una pieza
en error muestra "Reintentar" (encola esa sola, `max_intentos=1`) o "Reemplazar
idea" (la descarta y pide otra). Nunca se reintenta solo.

### 2.3 Interrupciones

Las tareas de FlowPlus ya marcan la sesión en `error` si el worker se reinicia
(`AL_INTERRUMPIR`); el sprint lo refleja por el `JOIN`. `recalcular` corre al
consultar progreso, así el estado del sprint se corrige aunque el evento se pierda.

### 2.4 Control de calidad automático

Periódica `sprint_qa_pendientes` (`worker.PERIODICAS`, cada 300 s): busca
`campana_pieza` con sesión `listo` y `qa IS NULL`, y encola `sprint_qa_pieza`
(`max_intentos=3`, barato). Claude con visión sobre la imagen o tres fotogramas
del video, más `ffprobe` (aspecto y duración). Cinco chequeos, cada uno con `ok`
y `nota`: `consistencia_visual` (contra análisis de referencias y guía de
marca), `presencia_marca`, `compatibilidad_campana` (se ve el producto; encaja
con persona y temporada), `calidad_minima` (artefactos, texto quemado, manos,
producto deformado), `formato` (9:16 o el pedido; duración dentro del objetivo
±20 %). Resultado:

```
{score: 0-100, checks: {nombre: {ok, nota}}, veredicto: pasa|revisar|falla,
 modelo, costo_usd, evaluado_en}
```

`veredicto`: `pasa` si `score >= umbral` y todos los checks ok; `falla` si
`calidad_minima` o `formato` fallan; `revisar` en el resto. Umbral en
`sprint.extra.qa_umbral` (defecto 70). **El QA nunca gasta en generación**:
marca, explica y ofrece "Regenerar (USD X)" (usa `creative_flow.duplicar` y el
lote de una pieza).

### 2.5 Bandeja de revisión

Tablero del sprint en `revision`: grid de piezas terminadas (video con póster,
imagen), filtros por campaña, tipo y veredicto; cada tarjeta muestra el score
con un icono por chequeo y la nota al pasar el cursor. Acciones: aprobar,
rechazar (motivo obligatorio), regenerar (con costo), "Final edition" (Parte 3;
para video, el flujo actual). Atajos: `A` aprobar, `R` rechazar, flechas para
moverse; "Aprobar todas las que pasaron QA". Cada acción escribe
`campana_pieza.revision` y un `sprint_evento`.

Las aprobadas siguen siendo sesiones de Crear: entran a experimentos y a la cola
de publicación (`estado_videos.json`) como hoy; una rechazada se retira de esa
cola si estaba.

### 2.6 Cierre y entrega

"Cerrar sprint" (disponible en `revision`) muestra el resumen (aprobadas,
rechazadas, sin revisar, costo total, duración) y pasa a `completado`.
**Entrega**: lista de enlaces por campaña y destino, "Copiar enlaces" y
"Descargar aprobadas (zip)", que encola `sprint_empaquetar` (descarga de R2,
zip en `salidas/<cliente>/sprints/<id>.zip`, subida a R2, enlace con fecha).
Un sprint completado se puede reabrir a `revision`.

### 2.7 Cambios a lo existente (mínimos)

- `flowplus_prompt.armar(..., contexto=None)`.
- `creative_flow.crear(..., extra_sprint=None)`.
- Mover `_lanzar_video_cf`, `_job_id_creative_flow` y `ETAPAS_CREATIVE_FLOW` de
  `dashboard.py` a `flowplus_lanzar.py`; `dashboard.py` los importa de ahí.
- `tarea.prioridad` (migración), `cola.reclamar` por prioridad,
  `trabajos.encolar(prioridad=5)`.
- `worker.PERIODICAS` += `("sprint_qa_pendientes", 300)`.

### 2.8 Módulos y pruebas

`sprints/ideas.py`, `sprints/produccion.py` (estimado, creación de sesiones,
encolado), `sprints/qa.py`, `sprints/revision.py`, `sprints/entrega.py`,
`tareas/sprints.py` (+ `sprint_proponer_ideas`, `sprint_qa_pieza`,
`sprint_qa_pendientes`, `sprint_empaquetar`).

Pruebas: parseo y validación de ideas con Claude falso; creación de sesiones
desde una idea (el prompt contiene `AUDIENCIA` y `TEMPORADA`; con
`contexto=None` es idéntico al actual; orden de referencias); matemática del
estimado y del tiempo; orden por prioridad en `cola.reclamar`; parseo, umbral y
veredictos del QA; transiciones de revisión, cierre y reapertura; empaquetado
con R2 falso.

---

## Parte 3 — Final edition ampliada

### 3.1 Plantillas de texto

**plantilla_texto**: `cliente`, `nombre`, `ambito` (json: `{nivel:
marca|producto|temporada|pais, catalogo_id?, temporada_id?, pais?}`), `formato`
(`9:16|4:5|1:1`), `elementos` (json[]), `origen` (`defecto|manual|desde_referencia`),
`archivada`, `extra`. Cada elemento:

```
{rol: titulo|subtitulo|cta|descripcion|badge, fuente, peso, tamano:
 pequeno|mediano|grande, color, alineacion: izquierda|centro|derecha,
 posicion: sup_izq|sup_der|centro|inf_izq|inf_der|{x_pct, y_pct},
 fondo: ninguno|pildora|tarjeta, margen_pct}
```

`tamano` se mapea a píxeles por formato en `final_edition/plantillas.py`
(`grande` en 9:16 = el `TAM_HOOK` actual). Cada proyecto nace con una plantilla
"Marca" (`origen=defecto`) construida desde el color de acento, el logo y las
constantes actuales de `texto.py`, así los videos de hoy se ven igual hasta que
alguien elija otra. **Resolución** al producir: elección explícita por pieza >
país > temporada > producto > marca.

"Crear desde referencia": Claude con visión sobre una referencia con intención
`tipografia` o `composicion` propone una plantilla; las fuentes se aproximan al
set de `static/fonts/`, que se amplía con una selección curada de Google Fonts
(licencia OFL, archivos versionados). **Editor**: vista previa sobre el póster de
una pieza real; los elementos se colocan en las cinco posiciones o por
porcentaje; cada cambio pide `POST .../plantillas/<id>/previsualizar` que
compone con Pillow y devuelve la imagen.

### 3.2 Textos como variables multiidioma

`campana_pieza.textos` (json): por rol, un diccionario por idioma:
`{headline: {es, en, pt}, subtitulo: {...}, cta: {...}, descripcion: {...}}`;
el precio va aparte, por `idioma_pais`, y **nunca se convierte entre monedas**
(regla vigente de final edition). Se prellena desde el `gancho` de la idea y
Claude localiza por destino con el criterio de `guion.localizar_guion` (moneda,
unidades, tono); tarea `sprint_localizar_textos` (`max_intentos=2`). Edición en
una tabla roles × idiomas con autoguardado y "Traducir faltantes". Para videos
la fuente sigue siendo el guion de cinco bloques (la plantilla solo cambia cómo
se ven); para imágenes estas variables son la fuente.

### 3.3 Final edition de imágenes

`final_edition/imagen.py::producir(cliente, cf_id, idioma, pais, opciones,
on_etapa)`: entrada = pieza imagen + plantilla resuelta + `textos[idioma]` +
precio del destino (`opciones["precios"]["<idioma>_<pais>"]`, o ninguno) + logo;
salida = arte final en el formato de origen y, si `opciones["formatos"]` lo pide,
en otro (reencuadre centrado y plantilla reacomodada). Los primitivos de dibujo
de `texto.py` se generalizan en `dibujar_elemento(elemento, texto, lienzo)`,
usado también por el video. Sin proveedor externo: tarea `final_imagen`
(`max_intentos=3`, segundos), una por destino, `job_id =
f"{cliente}__{cf_id}__{idioma}_{pais}__final_imagen"`.

Persistencia: `creative_flow.crear_final` para imágenes crea una `pieza`
`tipo=final` con `padre_pieza_id` la imagen; columna nueva `pieza.url_imagen`
(migración). Se retiran los bloqueos de imagen en `dashboard._sesion_con_video`
y `dashboard._creative_flow_items`; el de `derivaciones._rechazar_imagen` se
queda (ahí manda el motor).

### 3.4 Plantilla en video

`final_producir` acepta `opciones["plantilla_id"]`; `texto.py` toma el estilo de
cada rol desde la plantilla (`hook` ← `titulo`, `subtitulos` ← `subtitulo`,
`badge` ← `badge`, `cta` ← `cta`) con las constantes actuales como respaldo. Los
subtítulos palabra por palabra conservan su agrupación y sincronía; la plantilla
decide fuente, tamaño, color, fondo y posición.

### 3.5 Experiencia

En la bandeja de revisión y en el detalle de Crear, "Final edition" de una
imagen abre: destinos (los del sprint), plantilla (resuelta sola, cambiable),
tabla de textos prellenada, precio por destino, vista previa por idioma y
"Producir 3 artes finales (gratis, ~10 s)". El panel de video gana el selector
de plantilla. A nivel de sprint, "Final edition del sprint": aplica plantilla y
textos a todas las aprobadas; imágenes al instante, videos encolados con su
costo de voz y música mostrado antes (como hoy). La entrega (§2.6) agrupa
finales por idioma y país. Sección "Plantillas" dentro de la pestaña Sprints.

### 3.6 Módulos y pruebas

`final_edition/plantillas.py` (modelo, resolución, mapeo de tamaños, plantilla
por defecto), `final_edition/imagen.py`, `sprints/textos.py`,
`tareas/final_edition.py` (+ `final_imagen`), `tareas/sprints.py`
(+ `sprint_localizar_textos`).

Pruebas: render con Pillow comparando cajas de texto y posiciones (no píxeles);
resolución de plantillas por ámbito; plantilla por defecto reproduce los
overlays actuales (misma caja, misma fuente); localización de textos con Claude
falso; precio ausente cuando el destino no tiene precio; bloqueos de imagen
retirados; migración.

---

## 4. Orden de construcción y alcance

1. Parte 1 (planificación): visible: crear un sprint con su matriz, subir
   referencias con intención, ver análisis y progreso.
2. Parte 2 (producción): visible: proponer y aprobar ideas, generar un lote con
   su costo, ver QA y revisar; cerrar y entregar.
3. Parte 3 (final edition ampliada): visible: plantilla en video e imagen,
   artes finales por idioma, entrega con finales.

Cada parte: plan de implementación propio y ejecución por subagentes, como los
bloques del motor.

Fuera de esta versión: aprobaciones por rol (diseñador, marketing, manager);
versionado de campañas (ya existen `duplicar` y las derivaciones del motor);
publicación directa a LinkedIn, Google Ads o CMS; score de calidad más allá del
QA de §2.4; conversión de moneda.

## 5. Riesgos conocidos

- El worker es de una tarea a la vez: un lote de 35 piezas toma 1-2 h. La
  prioridad evita bloquear a Crear; paralelizar el worker es un cambio aparte.
- Numeración de migraciones compartida con el bloque 5: encadenar a la última al
  implementar y no reutilizar números.
- El QA con visión es un juicio, no una medición: los umbrales se calibran con
  el primer sprint real.
- `estado_videos.json` recibirá muchos más videos; si estorba, filtrar por
  origen sprint en esa cola es un cambio pequeño posterior.
