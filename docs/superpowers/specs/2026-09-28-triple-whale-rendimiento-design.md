# Triple Whale: métricas, evaluación del contenido y ganadores (2026-09-28)

Pedido: «Mejoremos toda la experiencia de Triple Whale. Aún no está conectado, pero apenas lo
conectemos saquemos todos los indicadores y métricas, hagamos toda una evaluación del contenido para
posteriormente poder generar nuevos ads ganadores.»

Base: `docs/triple-whale/investigacion-api-2026.md` (fuentes primarias de Triple Whale). Nada de lo
que sigue se probó contra una tienda real: no hay ninguna conectada todavía (§9).

## 1. Qué cambia para la persona

1. **Conectar** (Configuración › Conexiones › Triple Whale): llave + dominio + moneda + modelo y
   ventana de atribución con el vocabulario real de Triple Whale. Antes de guardar se prueba la llave
   **y** una consulta SQL corta contra la tienda; si Triple Whale no la acepta, no se guarda nada.
2. **Apenas conecta** se encola la primera copia: los últimos **90 días** por anuncio y por día (gasto,
   impresiones, clics, clics de salida, vistas de 3 s, ThruPlays, cuartiles de video, compras que
   reporta la plataforma, pedidos/ingresos/clientes nuevos/sesiones/carritos/checkouts atribuidos por
   el Triple Pixel) y la tienda por día (ingresos, pedidos, clientes nuevos, reembolsos, costo,
   utilidad, gasto total). Después, cada 2 h, los últimos 7 días (Triple Whale reatribuye).
3. **Pestaña Triple Whale** (nueva, después del Tablero): la tienda (ingresos, pedidos, gasto, MER,
   ticket, % de clientes nuevos, con su variación), los anuncios (gasto, ingresos atribuidos, ROAS,
   costo por venta, CTR, CPM, gancho, retención), alertas, el día a día, el reparto del gasto por
   veredicto y por canal, y **cada anuncio con veredicto y diagnóstico**. Periodo 7/14/30/90 días y
   filtro por canal. Todo esto es gratis.
4. **Evaluación con IA** (botón con el precio y confirmación): Claude mira los ganadores y los
   perdedores —miniatura, texto y números— y devuelve por qué ganan, qué patrones se repiten, y
   **anuncios nuevos para probar**, cada uno con su ángulo (doctrina) y un prompt para el video.
5. **Del análisis a anuncios nuevos**: «Llevar a Crear» precarga el formulario de Crear con el prompt
   de la idea (generar sigue siendo el clic de siempre, con su precio); «Guardar en Referentes» deja
   un anuncio ganador propio en la biblioteca del proyecto, desde donde ya funcionan «Recrear con mi
   producto» y «Usar en sprint».
6. **Experimentos atribuidos a Triple Whale**: las ventas salen ahora de lo que atribuye el Pixel de
   Triple Whale, no de las compras que reporta Meta (§7).

## 2. Cliente de la API (`triple_whale/__init__.py`)

`triple_whale.py` pasó a ser el paquete `triple_whale/` (el cliente sigue en `__init__`, así
`import triple_whale` no cambió). Arreglos contra lo documentado:

| Antes | Ahora |
|---|---|
| Mandaba `parameters` (no documentado) y no mandaba `period` | `{"shopId", "query", "period": {"startDate", "endDate"}, "currency"}`; `@startDate`/`@endDate` los llena Triple Whale |
| Leía `rows` | Lee `data` (documentado); acepta `rows` o una lista por si cambia |
| `ads.account_name` y `ads.country` (no existen en `ads_table`) | Solo columnas del Data Dictionary |
| Compras = `ads_table.conversions` (lo que reporta Meta) | Compras = `pixel_joined_tvf.orders_quantity` (el Pixel) |
| Modelos «First Touch/Last Touch», ventanas «7/30» | `MODELOS` y `VENTANAS` del Data Dictionary; los valores viejos se traducen al leer |
| Dominio tal cual | `normalizar_dominio` (sin https, barras ni www) |
| Un error genérico | `ErrorLlave` (401), `ErrorTienda` (403 / tienda desconocida), `ErrorConsulta` (400 o 5xx que persiste); 429 respeta `Retry-After` |
| Un test llamaba a la API real | Ningún test toca la red |

"Our schema is dynamic": cada consulta tiene una versión **completa** y una **mínima** (solo las
columnas de los ejemplos oficiales). `consultar_con_respaldo` baja a la mínima solo ante un
`ErrorConsulta`. Modelo y ventana entran a la consulta como literales de una lista blanca.

## 3. Datos (migración 0023, `triple_whale/datos.py` es el único escritor)

- `tw_anuncio_dia` — `(cliente, canal, ad_id, fecha)` único; medidas de canal + del Pixel +
  `con_pixel` (si el Pixel respondió para esa fila) + dimensiones (campaña, conjunto, nombre, creativo,
  `utm_ok` = `is_utm_valid`). Pedidos en Float (los modelos lineales reparten un pedido).
- `tw_tienda_dia` — `(cliente, fecha)` único.
- `tw_evaluacion` — cada análisis con IA: la muestra (`anuncios`, con la miniatura que se usó), el
  `resultado`, `usd`, `estado` `en_cola|analizando|lista|error`.
- `triple_whale.extra` — `backfill_desde`, `ultimo_resumen` de la última copia.

Son copias: cambiar la tienda, la moneda, el modelo o la ventana borra lo copiado (se calculó con
otra atribución) y se vuelve a traer; desconectar también lo borra. Las evaluaciones pagadas se
conservan siempre.

## 4. Sincronización (`triple_whale/sync.py`, `tareas/triple_whale.py`)

- `rango_pendiente`: 90 días si nunca se copió; si no, los últimos 7 — o desde dos días antes de la
  última copia si el worker estuvo parado más tiempo.
- Tramos de 7 días ("Split wide date ranges into smaller chunks"). Por tramo: anuncios, Pixel y
  tienda. Cada `reemplazar_*` pone en cero / borra el rango antes de escribir, en la misma
  transacción: un pedido que Triple Whale movió de un anuncio a otro no queda duplicado.
- Si la consulta del Pixel o la de la tienda no sirve ni en su versión mínima, se sigue sin esa parte
  (se avisa en la pestaña); los anuncios nunca se pierden por eso. Llave, tienda, límite y red cortan
  la copia: la conexión queda en `error` con el motivo (sin la llave; se tacha su valor exacto) y la
  cola reintenta una vez (`max_intentos=2`; la API no cobra por llamada).
- Tareas: `tw_sincronizar` (job `<cliente>__tw_sync`), periódica `tw_sincronizar_todas` (2 h, antes
  de `exp_refrescar_todos` en `worker.PERIODICAS`).

## 5. Evaluación gratis (`triple_whale/evaluacion.py`, pura)

Cada anuncio se compara con **su propia cuenta** (mediana de los anuncios con ≥ `impresiones_min`
impresiones; con menos de 3 comparables se usan los umbrales absolutos del decisor o no se opina).
Reglas del decisor del proyecto (`impresiones_min`, `roas_min`, `ctr_min`, `thruplay_min`).

**Veredicto**: `sin_datos` (< `impresiones_min` y < 3 pedidos) · `ganador` (≥ 3 pedidos y ROAS ≥ la
meta: `roas_min`, o la mediana si está apagado, o 1,0) · `perdedor` (gastó ≥ 2 ventas al costo por
venta de la cuenta con ROAS < la mitad de la meta) · `prometedor` (gancho, clic o conversión
claramente sobre la mediana, sin «pocos clics») · `en_prueba`. Sin ningún pedido atribuido en la
cuenta no hay ganadores ni perdedores y una alerta explica por qué (rastreo o ventana).

**Diagnóstico** (qué hacer, no solo qué pasa): gancho débil/fuerte (vistas 3 s / impresiones),
no retiene/retiene (ThruPlays / vistas 3 s), pocos clics/mucho clic (CTR), clic sin compra/convierte
(pedidos / clics, con ≥ 50 clics), alcance caro/barato (CPM), **fatiga** (últimos 7 días contra los 7
anteriores: ROAS −30 % o CTR −25 %), sin rastreo de Triple Whale (`is_utm_valid` falso).

**Cuenta y tienda**: totales, reparto del gasto por veredicto y por canal, MER, NC-ROAS, ticket,
costo por venta, variación contra el periodo anterior. **Alertas**: sin ventas atribuidas, ≥ 30 % del
gasto en perdedores, ganadores cansándose, anuncios sin rastreo, MER −20 %, y los ganadores a usar
como base.

## 6. Evaluación con IA (`triple_whale/analisis.py`, tarea `tw_evaluar`)

### 6.1 Qué ve Claude
Hasta 6 ganadores/prometedores (por ingresos) y 4 perdedores (por gasto), con referencias A1…An,
sus números, su diagnóstico y, cuando Meta deja verla, la miniatura del creativo y su texto
(`medios_meta`: Graph API de solo lectura con la conexión del proyecto; `thumbnail_url` a 600 px;
la imagen se baja con la guarda SSRF de Referentes y va en base64). Rebanadas de doctrina:
`clasificar`, `angulo`, `gancho`, `video`; salida en el idioma del proyecto salvo el `prompt` de cada
idea, en inglés (va al modelo de video). Cada ángulo pasa por `doctrina.validar_angulo` (origen
`triple_whale`); una corrección si el JSON no sirve.

### 6.2 Costo
`gastos.estimar("evaluacion_tw", n=)` = US$ 0,08 + 0,012 por anuncio, a la vista en el botón y en su
confirmación. `max_intentos=1`. El gasto real se registra con los tokens medidos, tipo `evaluacion`,
referencia `tw_eval:<id>:t<tarea>`, también si la respuesta no sirvió.

### 6.3 Puente a anuncios nuevos (`triple_whale/puente.py`)
- «Llevar a Crear»: `session["fp_prefill"]` (el mismo de «Editar y crear otra») con el prompt de la
  idea, video 9:16 y las preferencias del proyecto. No se genera nada.
- «Guardar en Referentes»: referente del proyecto (`cliente=<proyecto>`, fuente `triple_whale`,
  `anuncio_id = tw:<ad_id>`), miniatura copiada a R2, etapa/consciencia/firma de Claude,
  métricas en `extra.triple_whale`. Solo ganadores/prometedores con miniatura.

## 7. Experimentos atribuidos a Triple Whale (`lanzador.refrescar`)

Mismo patrón que `tienda`: tráfico, gasto y **estado del anuncio** siguen saliendo de Meta (antes, el
camino de Triple Whale se saltaba Meta y con él la detección de anuncios rechazados); compras e
ingresos, de `tw_anuncio_dia` sumado desde que se creó la pieza (snapshot acumulado). Antes de leer,
`sync.sincronizar_si_hace_falta` (una vez por experimento, fuera del lock de Meta, solo si la copia
tiene > 30 min). Sin datos del Pixel para ese anuncio, el snapshot queda con lo de Meta. Ingresos en
otra moneda que la cuenta → ROAS 0 y un aviso (se decide por CPA), como la tienda.

## 8. Pantallas

- `_tab_triple_whale.html`: sin conexión, un estado vacío que cuenta qué se obtiene y lleva a
  Configuración; con conexión, un contenedor que pide `triple_whale.ver_panel` por fetch la primera
  vez que se abre la pestaña (la página del proyecto no calcula nada de esto al cargar — incidente
  del 2026-09-28). Todo el JS vive ahí.
- `_tw_panel.html`: el fragmento. Reusa tiles, secciones, alertas y el gráfico del Tablero
  (`app.extensions["grafico_tablero"]`). Tablas con scroll propio: la página no se desplaza de lado.
- Blueprint `triple_whale/rutas.py` bajo `/cliente/<cliente>/triple-whale` (`panel`, `sincronizar`,
  `evaluar`, `evaluacion/<id>/idea/<i>/crear`, `evaluacion/<id>/anuncio/<ref>/referente`), con
  chequeo de mismo origen en cada POST. Las rutas de Configuración (`cfg_triple_whale_*`) exigen
  correo verificado para conectar, mismo origen, y suman `ajustes`.

## 9. Lo que no está verificado

1. Ninguna consulta se corrió contra una tienda real. Las columnas de la versión completa salen del
   Data Dictionary; la mínima, de los ejemplos oficiales. `blended_stats_tvf()` se suma por
   `event_date`: si esa tabla trajera una fila por canal con los ingresos repetidos, los ingresos de
   la tienda saldrían multiplicados — revisar con la primera tienda conectada.
2. `is_utm_valid` puede no venir: entonces no se opina sobre rastreo.
3. Cadencia de Meta → Triple Whale no documentada: por eso se re-piden 7 días en cada copia.
4. (Resuelto en §12) Las miniaturas de Meta caducan: la de un referente y la de cada evaluación se
   copian a R2.
5. `orders_table.products_info` (§11): los nombres de sus medidas por producto no están en el Data
   Dictionary que leímos; la consulta completa asume `quantity`, `price` y `title`, y la mínima solo
   cuenta filas y reparte `order_revenue` en partes iguales. Si ninguna sirve, la copia sigue sin
   productos y la pestaña no muestra esa sección.

## 10. Parámetros de rastreo en los anuncios de Creatv (hecho) y siguientes pasos

- Hecho: `meta_ads.creative.crear_creative_imagen/video` aceptan `url_tags` (el campo «Parámetros de
  URL» del AdCreative, donde Meta resuelve `{{ad.id}}` y `{{site_source_name}}`). Con Triple Whale
  conectado, `lanzador._crear_anuncios` (y el camino viejo `tareas/meta.publicar`) mandan
  `triple_whale.URL_TAGS` = `tw_source={{site_source_name}}&tw_adid={{ad.id}}` en cada creative
  (`triple_whale_tiendas.url_tags`; None sin Triple Whale). El link sigue llevando
  `utm_content=<experimento_pieza.id>`, así la atribución por tienda no cambia. Los anuncios creados
  antes de conectar no los llevan: cambiarlos después manda el anuncio otra vez a revisión, así que
  Creatv no los toca y Configuración explica cómo ponerlos a mano.

## 11. Ventas por producto (hecho)

`tw_producto_dia` (migración 0024; `(cliente, producto_id, fecha)` único) copia `orders_table`
abierta por `products_info` (ARRAY JOIN) en la misma sincronización, con su versión completa y
mínima (`triple_whale.consultas_productos`, ver §9.5); dos variantes del mismo producto y día se
suman. La pestaña muestra «Lo que más se vende» (`panel.productos_periodo`: ingresos, % de la tienda,
pedidos, unidades, variación contra el periodo anterior y, si el `fuente_id` o el nombre coincide con
un producto del Catálogo, ese producto), no aplica con filtro de canal. El análisis con IA recibe los
5 que más venden (`analisis.texto_productos`) y cada idea dice a cuál apunta (`idea.producto`).

## 12. Lo que ve Claude y los avisos (hecho)

- **Fotogramas reales.** Un anuncio hecho en Creatv (`datos.piezas_creatv`, ahora con la pieza, su
  tipo, su video y su miniatura en R2) manda a Claude los fotogramas de su video
  (`analisis.visuales` → `sprints.qa.archivo_local` + `doctrina.revisor.bloques_visuales`, los mismos
  del revisor de la doctrina, con «Segundo N:»), o la imagen por URL si es una imagen; el temporal se
  borra al terminar (`borrar_temporales`, en un `finally`). Los demás anuncios siguen con su miniatura
  en base64. `anuncio.visual` (`fotogramas | imagen`) queda en la evaluación y la pestaña lo dice.
- **Miniaturas a R2.** `analisis.copiar_miniaturas` copia la miniatura de Meta de cada anuncio a
  `clientes/<c>/triple_whale/eval<id>_<ref>.jpg` antes de analizar (`medio.imagen` pasa a ser la
  copia; `imagen_origen` guarda la de Meta); las piezas de Creatv ya viven en R2 y no se copian.
- **Avisos por correo** (`triple_whale/avisos.py`, tipo `tw_evaluacion`). Tras cada copia el worker
  evalúa los últimos 30 días y compara con `triple_whale.extra.avisados`: nuevos ganadores, ganadores o
  prometedores que se están cansando y nuevos perdedores van en UN correo (`notificaciones.avisar`:
  sin SMTP o sin correo del proyecto queda en la bitácora); gasto sin ninguna venta atribuida avisa
  una sola vez (`extra.aviso_sin_ventas`) hasta que vuelvan las ventas. La primera copia solo guarda
  la base. Un fallo aquí nunca tumba la copia.
- **Pausar / activar desde la pestaña.** En «Cada anuncio», una pieza de Creatv activa ofrece
  «Pausar» y una pausada «Activar» (`triple_whale.pieza_estado` → `lanzador.pausar_pieza` /
  `activar_pieza`, con confirmación y su evento de experimento). Nada más se toca en Meta.

## 13. La tienda en el Tablero (hecho)

Con Triple Whale conectado y datos de tienda, el Tablero muestra «Tu tienda según Triple Whale»:
ingresos y pedidos del mes, % de clientes nuevos, MER y gasto, con la variación contra los mismos días
del mes anterior (`panel.resumen_mes_tienda`, parte `tienda_tw` de `_calcular_tablero`; la clave de
caché del Tablero incluye `triple_whale.actualizado_en`, así una copia nueva lo refresca). El detalle
sigue en la pestaña.

## 14. Idea → pieza → anuncio (hecho)

«Llevar a Crear» sigue sin generar nada, pero ahora deja rastro. El prefill lleva `origen_tw`
(«<evaluación>:<índice>», `puente.prefill_crear`), el formulario de Crear lo devuelve en un campo
oculto y `cf_crear_video` lo guarda en la sesión como `concepto.extra.tw_idea` =
`{evaluacion_id, idea, titulo}` (`puente.origen_desde_formulario` lo valida: forma, evaluación del
proyecto y `lista`, idea existente; un valor raro se ignora y la pieza se crea igual). Con eso:

- la tarjeta de cada idea de la última evaluación lista dice «Ya se hicieron N piezas con esta idea»
  y las lista con su estado de Crear (`datos.piezas_de_evaluacion`, `panel.ETIQUETAS_PIEZA`) y, si la
  pieza ya corre en Meta y aparece en el periodo, su veredicto («en Meta: Ganador»);
- cada anuncio de «Cada anuncio» hecho en Creatv que nació de una idea dice «Nació de la idea «…» de la
  evaluación con IA» (`datos.piezas_creatv` trae `tw_idea`; `panel.enlazar_ideas` cruza ambos sin
  consultas por fila).

Así se ve si lo que Claude propuso a partir de los ganadores también gana. Nada de esto se copia con
`duplicar` ni entra al análisis siguiente como dato.

Siguientes pasos (fuera de este cambio):

- Verificar §9 con la primera tienda real.
