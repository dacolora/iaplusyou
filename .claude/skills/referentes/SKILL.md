---
name: referentes
description: "Biblioteca de referentes: anuncios reales clasificados (copycoders, barridos con Atria, Apify y TrendTrack), la clasificación con Claude, «Recrear con mi producto» (fiel y variación, como imagen o video) y su puerta desde Sprints. Cargar antes de tocar referentes/, tareas/referentes.py, _tab_referentes.html o /admin/referentes."
---

# Biblioteca de referentes y Recrear

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Biblioteca de referentes** (`referentes/` + `tareas/referentes.py`, spec
`docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md`): anuncios
reales clasificados por etapa (TOF/MOF/BOF), consciencia, familia (190 de
copycoders + las que Claude proponga como `EMERGING`), dolor y firma («por qué
funciona»). Tablas `referente` (`anuncio_id` = id del Ad Library de Meta, UNIQUE
por proyecto (la biblioteca global NULL tiene su propia unicidad, migración 0030); `cliente` NULL = global de Creatv, `<cliente>` = solo ese proyecto; solo
se lista con `estado_imagen=ok`, la copia global en R2 `referentes/<anuncio_id>.jpg` y las nuevas privadas `referentes/<anuncio_id>_r<id>.jpg`),
`referente_familia` y `barrido`. `referentes/datos.py` es el único escritor. La búsqueda (`q`) y las marcas a imitar
comparan sin tildes ni mayúsculas con `db.pliegue`, que `db.engine()` también registra como función SQL
`pliegue(col)` en cada conexión (el `lower()` de SQLite solo baja ASCII).
Bloque 1: importación del swipe file de copycoders (`referentes/copycoders.py`
lee `const DATA=[...]` del HTML público; tarea `referentes_importar_copycoders`
por fases `anuncios → imagenes → traducir` con continuaciones `__cont`, la única
llamada pagada es la traducción de firmas, gasto tipo `otro` bajo `_creatv`) desde
`/admin/referentes`, y la pestaña **Referentes** (`_tab_referentes.html`, Blueprint
`referentes/rutas.py`: `grid` y `ficha` como fragmentos por fetch, filtros en el
hash `#referentes?etapa=TOF&…`). Bloque 3: la puerta desde Sprints (`sprints.datos.agregar_referencia_biblioteca`, el modo selección del grid, `referentes/sugerir.py`, «Usar en sprint»). Bloque 4: barridos en vivo — `referentes/fuentes/` (registro perezoso por módulo, no por clase: `referentes.fuentes.por_tipo(tipo)` devuelve el módulo con `estimar/probar/traer`), `referentes/fuentes/atria.py` (Ad Library de Meta vía la REST de Atria, `X-API-Key`, 20 llamadas/min, contador mensual en `kv`), `referentes/clasificar.py` (una llamada de visión por anuncio: etapa/consciencia/familia/dolor/firma, familias nuevas entran como `EMERGING: <nombre>`), tarea del worker `referentes_barrer` (tramos de 100, reanudable por `barrido.extra.cursor_atria`, tres fases: trayendo → guardando imágenes → clasificando) y `referentes_clasificar` (reclasifica solo lo pendiente de un barrido). Bloque 5: conector Apify (`providers/apify.py` -- arrancar/sondear/leer el
dataset/contarlo, compartido con `nicho/fuentes/apify.py`;
`referentes/fuentes/apify_actores.py` -- el actor oficial
`apify/facebook-ads-scraper` y su precio real; `apify_adlibrary.py` -- arma
la URL de la Ad Library con país real (a diferencia de Atria, que es solo
UE) e idioma, una sola corrida por barrido sin cursor que retomar, reporta
su costo real por resultado a `gastos` bajo el tipo `recoleccion`).
TrendTrack (2026-09-30, spec `2026-09-30-fuente-trendtrack-design.md`): tercera fuente de barrido,
`referentes/fuentes/trendtrack.py` (`TRENDTRACK_API_KEY`, plan Pro). Solo busca por palabra clave
(`MODOS = ("palabra",)`, `fuentes.modos(tipo)`: el formulario esconde «De una marca» y las rutas lo rechazan),
pide `GET /v1/ads?search&limit&offset` con `Authorization: Bearer`, prueba la llave con `GET /v1/me` (gratis) y
cobra 1 crédito por fila devuelta: el formato y «solo activos» se filtran AQUÍ, después de pagar, así que se
miran hasta 3× los anuncios pedidos. Como Atria, `usd_fuente` es 0 y el uso se cuenta en `kv`
(`creditos_este_mes`, `creditos_restantes` desde `X-Credits-Remaining`, visibles en `/admin/referentes`). **Los
nombres de los campos de cada anuncio NO están verificados** (la documentación estaba bloqueada): `_normalizar`
los lee con la tabla `_CLAVES`, la primera página es de 10 filas y, si ninguna se reconoce, el barrido se
detiene con un error que lista los campos recibidos.
Barridos por palabra (2026-09-27, tras «dolor de pies» que trajo ruido pagado): SIEMPRE en inglés
— `referentes/traducir.preparar_consulta` traduce lo escrito con Claude (≈ US$ 0,0002, gasto tipo
`otro`, bajo `_creatv` si es global), guarda `consulta.palabra_original`, fuerza `idioma=en` (no hay
selector de idioma en los formularios; «Mis barridos» muestra «dolor de pies» → «Foot pain») y si
no se puede traducir el barrido no se lanza. Atria va con `order=best_match` (sin él ordena por
`newest` y su `query` acepta cualquier palabra); Apify, con varias palabras, pide la frase exacta
(`keyword_exact_phrase` con comillas). `datos.borrar_de_barrido` quita los referentes de un barrido
y las familias `claude` que quedan vacías (el barrido queda por el historial del gasto; las
imágenes R2 las borra el llamador con `claves_r2`, extraídas de imagen_url; no reconstruye la clave desde anuncio_id, porque las filas privadas llevan `_r<id>`).
`traer()` ahora entrega `(pagina, cursor_siguiente, meta)`: `meta` es `{}`
para Atria (solo consume cupo del plan) o `{"costo_real": ...}` para una
fuente que cobra por resultado real. Bloque 6: panel admin completo
(`/admin/referentes`) -- «Traer referentes globales» (mismo formulario y
mecánica que el de un proyecto, pero `cliente=NULL`: el barrido queda
visible para todos), totales por fuente, contador «Atria: N/1200 llamadas
este mes», tabla de familias editable (`datos.familia_actualizar`, sin usar
desde el bloque 1) y las tarjetas de `ATRIA_API_KEY`/`APIFY_TOKEN` en Puesta
a punto. Con esto los seis bloques del diseño original (spec 2026-09-23 §17)
están en `main`. Bloque 2: «Recrear con mi producto» (`referentes/recrear.py`) — `armar_prompt`
determinista (nunca llama a Claude) construye el prompt con la imagen del referente
como `Image 1` y hasta 2 fotos del producto elegido como `Image 2`/`3`; «Adaptar con
IA» (`adaptar`, opcional, ≈ US$0.01) es la única llamada pagada de este bloque y solo
propone texto, nunca genera. Generar reutiliza el pipeline de Crear tal cual
(`creative_flow.crear` + `flowplus_lanzar.lanzar`, `productos_ids` guarda el nombre
visible del producto como en el resto de Crear): la pieza aparece en la pestaña Crear
con su barra de progreso y su Aprobar/Rechazar de siempre. `pieza.extra.referente_id`
(en realidad `concepto.extra.referente_id`, por cómo `creative_flow.actualizar` guarda
los campos que no son columnas propias) es lo que cuenta «Usado N veces» en la ficha.
**Recrear fiel** (spec `docs/superpowers/specs/2026-09-30-recrear-fiel-design.md`, pedido de Daniel tras una imagen
que salió con una mano y un pie en vez de las dos sandalias de la referencia: una foto del producto sostenida con las
manos ponía su pose y la guía de marca pedía pies y manos): al abrir Recrear, el formulario pide solo
`POST …/recrear/leer` (`referentes/lectura.py`: una llamada de visión, ≈ US$ 0,01, gasto `adaptar_referente` también si
la respuesta no sirve) que describe la composición EN INGLÉS, el producto en singular, las unidades, si hay personas y
los textos de DENTRO de la imagen con su rol; se guarda una vez por referente en `referente.extra.lectura`
(`datos.guardar_lectura`, candado antes de leer) y el formato por defecto pasa a ser el más parecido
(`lectura.formato_cercano` con las medidas de `lectura.medir`). Los textos leídos son campos editables (`texto_<i>`;
el de rol `marca` nace vacío = se quita) bajo «Traer los textos de la referencia» (apagada = sin ningún texto,
`recrear.instruccion_textos`); reemplazan el campo «Titular». En imagen, dos casillas (`modo=fiel|libre`) crean una
sesión de Crear cada una (fiel primero, `extra.recrear_modo`, títulos « · igual» / « · variación»): la fiel
(`recrear.armar_prompt_fiel`) dice «edita Image 1 y déjala idéntica, cambia solo el producto», con la composición, las
unidades y «de Image 2 toma solo cómo es el producto», SIN guía de marca, firma ni dolor; la variación es
`armar_prompt` con la línea de textos. El servidor arma los prompts al generar (`_contexto_recrear`, marca
`campos_vista=1`) salvo el que la persona editó (`<campo>_editado=1`); sin la marca se usa `prompt` tal cual (camino
viejo). «Adaptar con IA» reescribe los textos alineados (misma cantidad; marca vacía) y el prompt de la variación. La
pestaña tiene dos `<script>` con su propio `cargarEnDialogo`: el de la ficha avisa con el evento `ref:fragmento` para
que el otro pida la lectura. Enter en un campo no envía. El Blueprint de Referentes rechaza los POST cross-site
(`Sec-Fetch-Site`).
**Como video** (spec §12 y §12.1, 2026-10-01): las mismas casillas; «igual» Y «variación» crean cada una su sesión
de IMAGEN (la fiel o la variación, con el prompt de imagen) con
`extra.animar_despues = {modelo, duracion, formato, prompt, con_sonido, titulo}` y, cuando el worker la termina
(`tareas/flowplus.ejecutar_imagen` → `_animar_imagen`), `recrear.lanzar_animacion` crea y lanza UN video con esa imagen
como única referencia (`recrear_modo="fiel_video"|"libre_video"`, `imagen_origen`; idempotente por `animar_despues.cf_video`; si falla,
la imagen queda lista con `animar_error`, que su detalle muestra). El modelo lo elige la persona en «Animar con»
(`MODELOS_ANIMAR`: Seedance 2.5 por defecto, el único que arranca desde la imagen; Wan 3.0); `armar_prompt_animar` dice
«Image 1 es el primer fotograma, no cambies nada» (el mismo para los dos). La variación hecha directo con Wan arrancaba
con el subtítulo viejo de la referencia y cortaba a la foto del producto con manos: por eso también va por imagen. El formato de video va al más
parecido que el modelo admite (`_formato_video`: 4:5 → 3:4 en Wan). Un formulario de video sin `modos_vista` (abierto
antes de esto) sigue haciendo un solo video.

**Cobros e aislamiento (2026-10-02, PND-006/007/008):** `guardar_referente` toma `BEGIN IMMEDIATE` y hace upsert por `(cliente, anuncio_id)`; una corrida de otro proyecto crea su propia fila, sin modificar las de la biblioteca global o de otro proyecto. La migración 0030 conserva ids y rechaza bajar si habría que borrar duplicados entre proyectos. El gasto de fuente se anota antes de guardar anuncios; Apify conserva el costo contado cuando falla el sondeo y propaga `run_id`/`dataset_id`, guardados en `gasto.extra` con proveedor `apify`.

Listados (revisión 2026-10-02, PND-006): si existe una copia del anuncio en el proyecto, se oculta su fila global en listar, opciones, familias, familias_frecuentes y los sugeridos que usan esos lectores. referente(cliente, id) conserva su visibilidad por id.

PND-031/045 (2026-10-03): los enlaces internos de las fichas cierran su dialog antes de navegar. Apify devuelve estado/incompleto/aviso si termina sin SUCCEEDED y entrega resultados; el worker conserva aviso_trayendo y la fase final termina parcial, sin perder anuncios ni cambiar el cobro.

PND-090 (2026-10-07, lote 5 B): MAX_FOTOS_PRODUCTO=2 es el tope compartido por ambos prompts deterministas y referencias_para (la salida normal es la misma). Las sesiones de Recrear, incluida su animación, llevan origen=recrear. por_ids devuelve exactamente la visibilidad por id de referente(), incluida biblioteca global y proyecto propio, en una consulta; no usa el filtro de listado que ocultaría copias globales por id.

**Cobro de una corrida al rendirse el sondeo (2026-10-08, PND-007):** se hace una lectura adicional de `actor-runs/{id}` y se transporta `usageTotalUsd` antes del guardado, también con respuestas vacías. No se usa el tope como gasto. Si la corrida sigue RUNNING, se conserva `conciliacion_pendiente`: una lectura no garantiza la factura final y esa pregunta sigue en `docs/pendientes.md`. No se relanza el actor.


PND-007 (2026-10-08, decisión delegada enmendada): traer consulta el estado/cobro final gratis también cuando el estado ya es terminal. Con resultados leídos/contados registra el mayor entre usageTotalUsd y resultados × USD_POR_RESULTADO. Si ambas lecturas fallan, conserva tope × precio con estimado=True y conciliacion_pendiente=True. ErrorFuente transporta el costo antes de persistir el barrido; tests/test_lote6_apify.py usa SQLite, fallo posterior, referencia por tarea, idempotencia y aislamiento. Sigue abierta la pregunta de confirmar con una corrida real qué significa usageTotalUsd en este actor; no se llama a proveedores reales para estas pruebas.



PND-024 (enmienda 2026-10-08, R4 del lote 6B): Recrear muestra una línea neutra con el dolor del referente y el nombre del producto elegido, solo con producto y dolor real (excluye ninguno-oferta/ninguno-marca/vacío). Usa datos.localizado para el idioma de quien mira y la misma expresión etiquetas_dolor + traducir de la ficha. Usa la clase existente vacio. No compara familia/categoría, no llama a Claude, no cambia prompts/precios y no bloquea. test_rutas_referentes.py::test_r4_contexto_dolor_y_producto_sin_cobrar_ni_bloquear.

PND-051 (enmienda 2026-10-08): referentes_barrer va en el carril de Nicho, de UN hilo compartido con las recolecciones y búsquedas de Nicho. Ambos consumen la RAM de la misma cuenta Apify: dos tareas en paralelo provocaban 402 por capacidad. Todas las fases del tipo comparten ese carril, también con fuente Atria/TrendTrack; referentes_clasificar y las importaciones/traducciones sin Apify permanecen en general. Al parar se termina la tarea y esperar_hilos espera su hilo; no se añaden puntos de control ni continuaciones de Apify. tests/test_lote6c_nicho_carril.py::test_nicho_en_vuelo_impide_barrido_en_general.

PND-159/187 (2026-10-09, decisiones delegadas): Apify conserva run_id vía on_ids antes de comprobar dataset, intenta obtenerlo con un GET y, si falta, registra tope × tarifa marcado estimado/conciliacion_pendiente. Arranque no reintenta POST; GET igual. guardar_en_r2/clave_r2 aceptan cliente opcional: solo el puente de Triple Whale lo pasa para nuevas miniaturas clientes/<cliente>/referentes; los demás llamadores y archivos históricos conservan su clave.


Enmienda PND-159 (2026-10-09): on_ids avisa al worker para registrar YA tope × tarifa, estimado/conciliacion_pendiente y run_id, con la misma referencia referentes:barrer:<bid>:apify:t<tid> de la final. El upsert corrige monto e indicadores, sin sumar dos gastos. GET de corridas recientes gratuito resuelve un timeout/5xx solo con una corrida posterior al inicio del POST; 429 sí espera y reintenta.

Segunda ronda lote 7 (2026-10-09, regresión del estimado temprano): Apify entrega meta con costo_real también para una lista vacía y monto cero. La final corrige la misma fila y su saldo, y quita las marcas del estimado; un costo_real desconocido conserva el estimado marcado, según PND-007.
