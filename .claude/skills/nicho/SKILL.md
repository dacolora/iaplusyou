---
name: nicho
description: "Nicho y avatares: estudios con comentarios reales (texto, CSV, Reddit, YouTube, Apify), la investigación automática por tiendas (Amazon, Mercado Libre, Walmart, TikTok Shop, AliExpress, otro mercado) y los avatares del proyecto. Cargar antes de tocar nicho/, tareas/nicho.py, tareas/investigacion.py, providers/apify.py o las plantillas de Nicho."
---

# Nicho y avatares

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Nicho y avatares** (`nicho/` + `tareas/nicho.py`, spec
`docs/superpowers/specs/2026-09-18-nicho-avatares-design.md`): personas nacidas de
comentarios reales. Tablas `estudio`, `comentario` (única por estudio + fuente +
fuente_id, nunca guarda el autor) y `avatar` (núcleos por deseo con `padre_id`
NULL; sub-avatares colgando de ellos con los campos de las dos plantillas del
cliente: identidad, soluciones previas, situaciones, conciencia, encaje del
producto, evidencia). `nicho/datos.py` es el único escritor; `recalcular` deriva
`armando | generando | revisando`. Las fuentes entran por `nicho/fuentes/base.py`
(`normalizar_comentario`, `ErrorFuente.usuario`) y el registro perezoso
`nicho.fuentes.por_tipo`; `texto` y `csv` corren en la ruta; `reddit`, `youtube`
y `apify` corren en el worker con la tarea `nicho_recolectar`
(`tareas/nicho.py`: lotes de 100, `aviso` de entrega parcial, lo leído nunca se
pierde; Apify `max_intentos=1` con el estimado por resultado a la vista y su
gasto como tipo `recoleccion`; Reddit/YouTube `max_intentos=2`). Reddit usa el
token de solo lectura (`client_credentials`, 100 llamadas/min, solo uso no
comercial); YouTube una llave simple (`search.list` tiene cupo de 100
llamadas/día, una por recolección); Apify solo actores con precio por resultado
(`nicho/fuentes/apify_actores.py`, precios del plan FREE reverificados el 2026-10-01; junglee
—reseñas de Amazon, prueba real en producción el 2026-10-01, run `wpny9jQYLztteag8Z`— en el plan
FREE de Apify solo lee 1 link y entrega 10 reseñas por corrida (Starter lo sube a 40): UNA
corrida POR LINK (`corridas()`, nunca junta varios `productUrls`), 2048 MB (`memoria_mb`, para
que quepan 5 a la vez en el límite de 16 GB de la cuenta) y un techo mínimo de US$ 0,50 por
corrida que solo va en lo que se MANDA a Apify, nunca en lo que `estimar()` muestra antes del
clic (el peor caso real); actor, precio, techo mínimo, memoria y reseñas por corrida de junglee no se
escriben en `apify_actores`: `_junglee()` los lee del registro de la investigación,
`nicho/fuentes/plataformas.py`, un solo sitio que cambiar) y el token siempre en cabecera. La cuenta de
Apify de Creatv es FREE:
US$ 5 de uso al mes para toda la cuenta, 16 GB y 5 corridas a la vez. Las llaves
(`REDDIT_*`, `YOUTUBE_API_KEY`, `APIFY_TOKEN`) viven en el `.env` raíz y se
muestran en Puesta a punto; sin ellas la tarjeta de esa fuente queda apagada — y solo
la ve el admin: al cliente no se le muestra una fuente sin llave ni instrucciones del `.env`
(`nicho/rutas._fuentes_conectadas`; si igual la pide, aviso neutro), porque las llaves son de
Creatv, no suyas (2026-09-27).
**Investigación automática** (spec `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`,
plan `docs/superpowers/plans/2026-09-28-nicho-investigacion-completar.md`): con el tema del estudio y UNA
cifra aprobada (el estimado lo calcula el servidor y el POST exige `total_visto`), la cadena de tareas
`nicho_inv_consultas` (Claude, hasta el tope aprobado de búsquedas — 1 a 4 — por idioma, todas en UNA
llamada: el del país y el de cada tienda que busca en otro, `investigacion.idiomas_necesarios`; se guardan
`consultas` — las del país, las de Reddit/YouTube — y `consultas_por_idioma`; la búsqueda nunca usa más
que ese tope) → `nicho_inv_buscar` por tienda, con las búsquedas de su idioma (si Claude no las escribió,
las del país, y el paso lo avisa) (`nicho/fuentes/plataformas.py`: Amazon con tienda propia (sus reseñas
vienen de `junglee~amazon-reviews-scraper` desde 2026-10-01 — US$ 0,006 por reseña, una corrida POR
PRODUCTO con 2048 MB: el plan FREE de Apify solo lee 1 link y entrega 10 reseñas por corrida — Starter lo
sube a 40 —, techo mínimo US$ 0,50 por corrida solo en lo que se manda a Apify, nunca en el estimado;
axesso se dejó de usar porque exige acceso completo a la cuenta; la búsqueda guarda las variantes del
anuncio — `variantAsins` → `extra.variantes`, con el ASIN propio y tolerando una lista rara — y tanto
`FuentePlataforma.buscar` como `investigacion.elegir` dejan un solo producto por anuncio, porque las
variantes comparten reseñas: el 2026-10-01 dos variantes elegidas trajeron las mismas, pagadas dos veces;
`elegir` tampoco toma una variante de un anuncio cuyas reseñas ya trajo otro producto del estudio),
Mercado Libre en 18 países, Walmart solo
en EE. UU., TikTok Shop y AliExpress en todo el mundo — AliExpress busca en inglés —; actores de Apify con
precio por resultado más el arranque por corrida que cobran algunos (`usd_por_corrida`),
`providers.apify.correr_lote` hasta 5 corridas a la vez con techo de cobro cada una (`plataformas.tope`);
el estimado de una tienda es la suma del PEOR CASO REAL de cada corrida (`peor_usd`, nunca el techo mínimo
que algún actor exige solo para que Apify acepte la corrida — enmienda 2026-10-01) y el gasto,
`plataformas.costo`)
→ `nicho_inv_seleccionar` (Claude marca lo del nicho; se eligen los de más reseñas y, sin ese dato, los de
más pedidos/vendidos) →
`nicho_recolectar` por tienda y por red (Reddit/YouTube con las mismas búsquedas) → `nicho_generar_avatares`
con `auto` y el tope restante; una investigación solo con redes, sin ninguna tienda, salta `seleccionar`
(no hay productos que juzgar). El estado vive en `estudio.extra.investigacion` (`nicho/investigacion.py`,
puro; RMW con candado en `datos.actualizar_investigacion`) y es el del primer paso pendiente o en curso
(`marcar_paso`), porque `avanzar` encola el siguiente paso sin marcarlo todavía; cada tarea llama
`tareas.investigacion.avanzar`, una tienda caída no frena a las demás, «Reanudar» no repite lo que cobró y
los productos van a `producto_nicho` (migración 0016; `resenas_traidas` evita pagar dos veces). La cifra
aprobada cubre el peor caso de cada paso pagado, incluida la línea de avatares
(`avatares.estimar_costo_maximo()`: los dos topes de `seleccionar` llenos a la vez — 600 comentarios que
suman 250 000 caracteres —, contados con la línea entera que va al prompt y la regla de otro mercado, más la
pasada de completado). La salida de Claude cuenta el pensamiento adaptativo (se cobra como salida): consultas
y selección por su tope de `max_tokens`, los avatares con salidas esperadas medidas en la prueba real del
2026-10-01. Gasto: Apify como `recoleccion`, Claude de la
investigación como `investigacion`; cada llamada a Claude de la cadena registra su gasto apenas responde,
con la referencia del spec en el primer intento, `:i<intento>` desde el segundo y `:fallido<intento>`
cuando el intento no sirvió (un reintento no vuelve a llamar a Claude si el paso ya quedó hecho). Los pasos
de red corren con `max_intentos=1`; un paso de la cadena de una investigación ya cancelada no hace nada ni
cobra. Si falla una tienda o una red, solo ese paso queda `error` y la cadena sigue; si Claude falla en el
último intento de consultas o selección, o fallan los avatares, la investigación queda `detenida`
(reanudable); y si una tarea no alcanza a cerrar su paso o a encolar el siguiente (`tareas.investigacion.
red_de_la_cadena`, `_avanzar_seguro`), queda `interrumpida` con el error: nunca colgada con un estado vivo y
nada en la cola. El `url` y la `imagen` de un producto solo se guardan si son `http(s)://` (van a un enlace).
Mientras la investigación está viva, la recolección manual del estudio y «Generar avatares»
esperan (las rutas los rechazan); si un trabajo manual con el mismo job_id sigue bloqueando un paso de la
cadena, `avanzar` deja la investigación `interrumpida` para que «Reanudar» funcione en cuanto termine. El
Blueprint de Nicho rechaza los POST que el navegador marca cross-site (`Sec-Fetch-Site`), como Sprints y
Flow Plus. Los precios por resultado del registro (`nicho/fuentes/plataformas.py`) son los del plan de
Apify de Creatv (FREE), verificados contra el cobro real de corridas reales (Amazon búsqueda y MELI
reseñas corregidos el 2026-10-01; un plan de pago puede bajar algunos); un actor que ahora exige acceso
completo a la cuenta (`full-permission-actor-not-approved`) se rechaza con su propio aviso, nunca con el
de token (`providers.apify.arrancar`).
**Otro mercado** (Parte 4, spec `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`): una tienda
sin sitio en el país del estudio no se rechaza: `plataformas.mercado(clave, pais)` → `("otro", casa)` y busca
y trae reseñas de su sitio principal (Amazon y Walmart → EE. UU., Mercado Libre → México); en la tarjeta va en
«De otros mercados», desmarcada de entrada («Marcar todas» marca todas las tiendas que tienen su llave, de los
dos grupos). Cada reseña de tienda guarda en
`comentario.extra` su `pais` (el del comprador si el actor lo da — AliExpress —, si no el del sitio) y
`mercado` (`local | otro`) respecto al país del estudio; si el estudio cambia de país («Investigar de nuevo»,
«Editar estudio»), `datos.actualizar_estudio` recalcula ese `mercado` en la misma transacción. Las reseñas de
Walmart y AliExpress se atribuyen a su producto también por el link que les mandamos (`producto_pedido`: su
`productId` puede ser el de una variante). La página lo muestra en comentarios y citas,
`avatares.seleccionar` pone primero las fuentes locales en cada vuelta y los prompts de avatares marcan
«otro mercado: <país>» con la regla de que identidad, demografía, edad, momento de vida, tono y conciencia
salen del mercado local. La selección de productos toma por turnos entre tiendas
(`investigacion._repartir_por_plataforma`): AliExpress, que no trae número de reseñas, no queda fuera del corte
de `MAX_FILAS_SELECCION`. eBay y Etsy se probaron con centavos y quedaron fuera (spec §1.1).
**Avatares del proyecto** (spec `docs/superpowers/specs/2026-09-29-nicho-avatares-proyecto-design.md`):
página `/cliente/<c>/nicho/avatares` y bloque en la pestaña. Nuevos = sub-avatares propuestos; aprobados =
personas no archivadas (lo que ve toda la app). Los avatares escritos a mano viven en un estudio oculto
(`extra.manual`) y nacen aprobados (persona `manual`); nunca se completan con IA porque no tienen
comentarios. Una persona sin avatar se edita creándole uno (`avatar_desde_persona`); editar un aprobado
actualiza su persona. Archivar/Desarchivar es solo para personas sin avatar; las que sí tienen uno usan el
Aprobar/Descartar del avatar. `nicho/calidad.py` define «completo»; la generación lo exige y una pasada de
completado llena solo lo vacío (citas verificadas); «Completar incompletos» (`nicho_completar_avatares`,
`max_intentos=1`, gasto `avatares`) lo hace con lo ya guardado, decidiendo contra la fila VIVA al guardar
— una edición hecha mientras corre nunca se pierde.
`nicho/avatares.py` hace dos pasadas con Claude (`generador_prompts.MODEL`):
núcleos, luego sub-avatares por núcleo; cada cita se verifica literal contra el
comentario (`verificar_evidencia`) y la que no aparece se descarta — un
sub-avatar sin citas queda `sin_evidencia`, no se borra. `estimar_costo` (tokens ×
`PRECIOS_USD_POR_MILLON`) se muestra en el botón antes de encolar
`nicho_generar_avatares` (`max_intentos=1`; el gasto real va a `gastos` como tipo
`avatares`). Regenerar borra `propuesto`/`descartado` y conserva los `aprobado`.
Aprobar un sub-avatar crea (o actualiza) una `persona` con origen `investigada`
(`persona_desde_avatar`); descartar la archiva. Exportación `.md` y `.xlsx` con la
plantilla de la hoja "Personas" (`nicho/exportar.py`). UI: pestaña **Nicho**
(`_tab_nicho.html`) y página propia del estudio (`nicho_estudio.html`), Blueprint
`nicho/rutas.py` bajo `/cliente/<cliente>/nicho/...`.

PND-055 (2026-10-05): una búsqueda por subreddit o comentarios de un post con 400/410/422, o 403 con reason private/banned/quarantined, salta ese recurso. Reddit conserva el error global de 401/403 genérico. YouTube salta videoNotFound/commentThreadNotFound como commentsDisabled, conserva páginas leídas y propaga errores de llave/permisos; cuota sigue deteniendo con aviso.

PND-092 (2026-10-07, lote 5 B): los identificadores fuente de Reddit llevan t3_ (post) o t1_ (comentario); no se prefija el id usado para pedir el post. agregar_comentarios reconoce un id histórico desnudo solo con la misma URL, bajo bloqueo, para conservar la fila/citas y evitar duplicarla. YouTube omite la búsqueda si los links válidos únicos llenan MAX_VIDEOS; TikTok exige video/photo numérico, enlace Compartir /t/código/ o enlace corto vm/vt con identificador; rechaza perfiles (corrección 2026-10-08). El estimado agrupa inputs 250 ms, invalida el precio anterior inmediatamente y cancela el timer al pedir precio inmediato. Edad, probar() y helpers duplicados siguen en la fila.

Noruega (2026-10-08, spec de Noruega y Suecia §5; motivo: el público de happyflops es Noruega y Suecia): `datos.PAISES_ESTUDIO` y `NOMBRES_PAIS` traen NO (Suecia ya estaba); `fuentes.plataformas.IDIOMA_POR_PAIS["NO"] = "no"`. El «kr» a secas de un precio se lee como NOK en un estudio de Noruega y como SEK en uno de Suecia o sin país (`plataformas._CORONA_LOCAL`, la sueca de siempre). En los prompts el idioma va con su nombre, nunca el código suelto: `investigacion._NOMBRE_IDIOMA["no"]` y `avatares.IDIOMAS["no"]` dan «noruego (bokmål)», porque `no` solo se lee como la palabra «no».

PND-051 (2026-10-08, decisión delegada 2026-10-07): Nicho corre en un tercer carril de UN hilo: nicho_recolectar, nicho_inv_buscar, nicho_inv_consultas, nicho_inv_seleccionar, nicho_generar_avatares y nicho_completar_avatares (todos esperan proveedor). No se agrega al carril Crear. Fuentes/sesiones/contadores son instancias locales, los contextos de cadena y Apify son ContextVar. El estado se escribe exclusivamente mediante datos, bajo candado antes de leer. Buscar y recolectar conservan plan, intención de lanzamiento e IDs en extra.apify_pendientes por trabajo (nunca tokens). Una parada devuelve Continuar; un fallo/reinicio conserva el checkpoint para Reanudar, sin repetir el POST de una corrida con ID. Si el plan cambió o el POST pudo cobrar sin ID, se exige comprobar la corrida antes de otra, sin relanzamiento automático. El gasto conserva la referencia de la tarea que lanzó y la lectura gratuita del costo usa la regla conservadora de PND-007. tests/test_lote6c_nicho_carril.py.

PND-051, 2026-10-08 (third lane runs beside general): `datos.recalcular`,
`agregar_comentarios`, `guardar_productos_nicho` and `guardar_completado` acquire the
row write lock before reading the live study/avatar, including Reddit deduplication
and avatar merges. Atomic counters use SQL updates; checkpoints use
`actualizar_extra_estudio`, which locks before reading `extra`. The concurrency
tests use a second SQLite connection and require an actual `database is locked` result.
