---
name: rendimiento
description: "Rendimiento: la pestaña que junta Triple Whale y Meta (pestana_rendimiento/), el selector por país, la fuente de cada cifra, «Resultados» y «Por país» mezclados, «Actualizar ahora», los alias de las pestañas viejas y, desde la integración con main, el Diagnóstico, los Segmentos y la «Evaluación con IA» de Meta rendimiento E2. Cargar antes de tocar pestana_rendimiento/, _tab_rendimiento.html, los _rend_*.html, _tw_secciones.html, _meta_secciones.html, pantallas/rendimiento.css, o al decidir de qué fuente sale una cifra."
---

# Rendimiento: Triple Whale y Meta en una sola pestaña

> Parte de la guía del repositorio. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md).
> Si el código y este texto no coinciden, manda el código: corrige el texto.

Por qué existe (Daniel, 2026-10-09): «lo que tenemos en Meta es lo mismo que tenemos en Triple Whale, esto confunde a
los clientes». Las dos pestañas daban números distintos para el mismo anuncio (ROAS 2,2× contra 3,7× en Noruega). Spec
`docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md` (reglas R1–R16 y enmiendas A1–A6), plan
`docs/superpowers/plans/2026-10-09-pestana-rendimiento-e1.md`, medición E0
`docs/superpowers/evals/2026-10-09-atribucion-happyflops.md`. La copia de datos sigue en cada paquete (skills
`triple-whale` y `meta-rendimiento`); aquí solo se lee y se decide la fuente.

## Archivos

- `pestana_rendimiento/entradas.py` (puro): entradas del selector y su fuente (R2–R5).
- `pestana_rendimiento/resumen.py`: «Resultados» y «Por país» cuando hay Meta o mezcla (R5–R8), en USD con
  `meta_rendimiento.tasas.mapa`, y desde E2 tarea 7 el detalle de un día con Meta o mezcla (`dia`).
- `pestana_rendimiento/panel.py`: `contexto(cliente, dias, entrada, canal, tienda=, cuenta=)` junta todo con UNA
  resolución del alcance (`_resolver`), la misma que usan el «Ver más» de conjuntos (`conjuntos_pagina`), la galería y
  lo que cobra (`alcances`, E2 tarea 4) y «Actualizar ahora» (`alcance_para_copias`): un «Ver más» nunca lee otras
  cuentas que las del panel, y lo que se cobra es lo que se vio.
- `pestana_rendimiento/alcance_meta.py` (E2 tarea 3, 2026-10-10): `alcance(cliente, ids, dias, hoy, params)` arma para
  esas cuentas de Meta el MISMO dict que `triple_whale.panel.alcance` (más `fuente = "meta"`), para que el flujo pagado
  (`triple_whale/pedidos.py`) y la galería lo lean sin saber de qué fuente son los números. Cada anuncio lleva
  `canal = "facebook-ads"` (la copia de Meta dice `meta`; las llaves `(canal, ad_id)` de `tw_analisis` son las de
  Triple Whale), su `ad_account_id` y su `moneda`. Veredicto y anillos son contra SU cuenta; las medianas, el costo por
  venta y la meta de ROAS que lee el prompt pagado son las de todo el alcance (con una cuenta, las de esa cuenta; para
  el contexto exacto de la cuenta de un anuncio, el alcance de esa cuenta sola). Con monedas distintas (o una cuenta
  sin moneda) `config["moneda"]` es None, el CPM mediano queda None y `ev["cuenta"]["canales"]` vacío: ni una moneda ni
  un costo inventados (R6). Solo lee la copia: no cobra ni llama a Meta. Pruebas: `tests/test_rendimiento_e2_alcance_meta.py`.
- `pestana_rendimiento/galeria.py` (E2 tarea 4, 2026-10-10): «Tus anuncios» = UNA galería con los anuncios de las dos
  fuentes y UN lote (`armar`, `tarjeta`, `claves_confirmadas`, `pedir_lote`, `medio_meta`; ver «E2 tarea 4» abajo).
- `pestana_rendimiento/rutas.py`: blueprint `rendimiento` bajo `/cliente/<c>/rendimiento`: `ver_panel` (GET `/panel`),
  `ver_conjuntos` (GET `/conjuntos`, solo `<tr>`), `actualizar` (POST) y, desde E2 tarea 4, la galería y lo que cobra:
  `ver_galeria` (GET `/galeria`, `entera=1` o `pagina`), `ver_tarjeta` (GET `/tarjeta/<fuente>/<canal>/<ad_id>`),
  `analizar_anuncio` (POST `/anuncio/<fuente>/<canal>/<ad_id>/analizar`) y `analizar_lote` (POST `/analizar-lote`);
  desde E2 tarea 5, `evaluar` (POST `/evaluar`, «Evaluar con IA» de la parte Triple Whale; la de Meta es
  `meta_rendimiento.rutas.evaluar` con `entrada` desde la integración con main); desde E2 tarea 7, `ver_dia` (GET
  `/dia`, el detalle de un día de «Resultados»). El
  nombre `rendimiento/` ya era de las pruebas de carga (skill `escala-y-salud`).
- Pantalla: `_tab_rendimiento.html` (armazón + TODO el JS; el panel llega por fetch), `_rend_panel.html`,
  `_rend_macros.html`; la galería de las dos fuentes, `_tw_galeria.html` (macros) y `_tw_galeria_fragmento.html` (sus
  fragmentos por fetch); secciones heredadas como macros en `_tw_secciones.html` e include `_meta_secciones.html`;
  estilos `static/estilos/pantallas/rendimiento.css`; la gráfica, `static/tw_resultados.js`. Detalle de pantalla en la
  skill `ui`.
- Cableado (2026-10-09, tarea 8): `_sidebar.html` (botón `data-tab="rendimiento"` donde estaba Triple Whale; Meta
  salió), `cliente.html` (`#tab-rendimiento` y el alias), `dashboard.ver_cliente` (contexto barato `rendimiento` =
  `conectado`, `hay_tw`, `hay_meta`, `n_cuentas`, `es_admin`: ni Graph ni el panel al cargar la página).

## Reglas (cada una con su motivo)

- **R1. Nombre y alias.** Clave `rendimiento`, ancla `#rendimiento`. `cliente.html` traduce las claves viejas
  `triplewhale` y `meta` (hash, `localStorage`, `redirect(_anchor=…)` viejos) con `JUBILADAS`, como `idea` abre Crear:
  hay enlaces guardados y pestañas recordadas en el navegador de la gente. Nada nuevo apunta a las viejas
  (`tests/test_rendimiento_cableado.py` las busca en plantillas y `.py`, y corre el alias en Node).
- **R2. Entradas.** Una por país (su tienda de Triple Whale y sus cuentas de Meta con ese país), una por tienda o
  cuenta sin país, más «Todas». Orden: países por código, luego lo que no tiene país.
- **R3. Fuente por entrada.** Con tienda, Triple Whale; si no, el Pixel de Meta. Una entrada muestra el mismo número
  sola y dentro de «Todas», también en sus campañas y conjuntos (`_con_ventas_tw`: gasto, ventas y pedidos TODO de
  Triple Whale y en su moneda; mezclar ventas en USD con gasto en SEK dio un ROAS diez veces mal, 2026-10-10).
- **R4. Una tienda sin país** es la fuente de todo el proyecto y el selector queda solo con «Todas»: Triple Whale no
  separa esas ventas por país (misma regla que `lanzador._tienda_tw_de`).
- **R5. Sin contar dos veces.** Una cuenta de Meta cuyos anuncios llegan en la copia de una tienda
  (`triple_whale.datos.cuentas_meta_de_tiendas`) está dentro de esa tienda: «Todas» no suma su gasto aparte. Se decide
  con los datos, no con el país (una cuenta «World Wide» alimenta Noruega). «Por país» lo dice en una nota.
- **R6. Moneda.** Una entrada en su moneda; «Todas» en USD día por día con la tasa de ESE día; sin tasa, «USD no
  disponible», nunca una inventada; si todas comparten moneda, esa (también en «Por país», ver «Revisión final»). Una
  cuenta sin moneda conocida no se suma como si fuera de la de las demás.
- **R7. «Desde el inicio»** es el periodo por defecto (regla del 2026-10-08: métricas en total). En «Todas» con fuentes
  mezcladas arranca el día en que TODAS las fuentes ya tienen datos y lo dice: sumar 3 meses de una tienda con 13 de una
  cuenta daría un total que no es de nadie (con solo tiendas, A7). Una fuente atrasada no cuenta como ventas en cero
  (`resumen._fin_datos`).
- **R8. Ventas arriba = retorno real.** Con Triple Whale, «Ventas» es lo que entró a la tienda y «Retorno», ventas /
  gasto; con Meta, el valor del Pixel rotulado «según Meta». En una mezcla, una línea dice de dónde sale cada parte.
- **R9. Por anuncio, solo pagado.** Solo cuentan los canales con gasto en la copia del alcance: lo atribuido sumaba 2,5
  veces la tienda por orgánico, Klaviyo y Direct (PND-157, cerrado). Vive en `triple_whale.datos` (skill
  `triple-whale`).
- **R10/R11/A4. La ventana de atribución no la cambia el código.** E0 recomienda 7 días (cuadra 1,01× con la tienda);
  Daniel la cambia en «Ajustes» (`cfg_triple_whale_ajustes`). Nunca tocar `triple_whale.VENTANA_DEFECTO`,
  `MODELO_DEFECTO` ni el ajuste de un proyecto: mueven lo que decide el decisor de Experimentos (plata).
- **R12. «Meta reporta».** En la tarjeta de un anuncio `facebook-ads` de Triple Whale, «Meta reporta N×» sale de
  `valor_canal / gasto`; sin dato no aparece.
- **R13. Lo pagado no se reescribe.** Referentes, «Llevar a Crear» y Pausar/Activar siguen en
  `triple_whale/rutas.py` con su alcance y sus garantías; esta pestaña solo les pasa la tienda de la entrada (o
  `None`). «Cómo mejorarlo» y «Analizar los N» pasaron en E2 tarea 4 a las rutas de la pestaña (la galería es una con
  las dos fuentes), y «Evaluar con IA» de Triple Whale en E2 tarea 5, pero cobran con el mismo
  `triple_whale/pedidos.py` y el alcance de cada fuente, con todas sus garantías. El JS de la galería se trajo tal cual (`tests/test_tw_tarjetas_js.py` lo lee aquí) y no cambió
  al unir la galería: cada URL sale de la plantilla.
- **R14. Anuncios de fuente Meta sin IA** solo en E1 (tarjeta sin botón, ni apagado). Desde E2 (tareas 1 a 4) tienen
  «Cómo mejorarlo» con la misma tarjeta y el mismo flujo pagado; su «Evaluar con IA» es la «Evaluación con IA» de Meta
  rendimiento E2 (main; ver «Integración con main»).
- **R15. Conexión en «Ajustes».** El formulario de Triple Whale (`_triple_whale_conectar.html`, un `div`: una
  `section` cortaba la de la pestaña) y «Elegir cuentas de Meta» (solo admin, R20 de Meta) viven en `#rend-ajustes`; la
  conexión con Meta sigue en Configuración › Conexiones.
- **R16. Fuera:** Experimentos (solo cambió su enlace a `#rendimiento`), E3 de Meta (PND-193), lanzar en varias
  cuentas (PND-148), modo agencia de la lectura (PND-197).

## Enmiendas al planear

- **A1.** La galería de Triple Whale va tal cual y debajo las tarjetas de fuente Meta: mezclarlas antes de que tengan su
  análisis arriesgaba lo que cobra. Se unieron en E2 tarea 4 (2026-10-10, ver abajo) y ahí se cerró PND-196.
- **A2.** R7 vale para «Resultados» y «Por país»; anuncios y campañas usan el «Desde el inicio» de su propia copia.
- **A3.** Detalle del día y filtro «Canal» solo con alcance solo Triple Whale; con Meta o mezcla la gráfica no abre días.
  El detalle del día con Meta y mezcla llegó en E2 tarea 7 (2026-10-10, ver abajo); el filtro «Canal» sigue siendo solo
  de Triple Whale.
- **A5.** «Actualizar ahora» es una ruta (`rendimiento.actualizar`) que llama a `triple_whale.rutas.pedir_copia` y
  `meta_rendimiento.rutas.pedir_copia` con los `job_id` de siempre, la pausa compartida de Meta y la espera de 30
  minutos de quien no es admin. Solo la entrada VACÍA es «Todas»: una que ya no existe (pestaña vieja, país quitado,
  la de otro proyecto) no encola nada y dice «Esa vista ya no existe: recarga la pestaña.» (revisión de la tarea 8:
  ensanchada a «Todas» copiaba todas las cuentas y gastaba el límite de uso de Meta que necesitan los lanzamientos).
- **A6.** E2 trae «Cómo mejorarlo» para Meta con la misma tabla y tarea (`tw_analisis`, `tw_analizar_anuncio`); la
  copia de desgloses `meta_desglose` y los avisos por correo de Meta quedaron aparte (PND-271). Al integrar main
  (2026-10-10) los desgloses ya los había hecho Meta rendimiento E2 en producción (PND-271 se cerró; los correos son
  PND-259) y su «Evaluación con IA» reemplazó a la nuestra de E2 tarea 5 (INT-2).
- **A7 (revisión final de E1, 2026-10-10; enmienda R7 en un borde).** Con SOLO tiendas de Triple Whale en «Todas»
  (fuente "tw"), «Desde el inicio» es el de Triple Whale (`triple_whale.panel._primer_dia`: cada tienda desde su primer
  día) para Resultados Y para «Por país», sin `inicio_comun` ni línea «Desde el …»; el inicio común de R7 es solo para
  mezclas. Motivo: «Por país» arrancaba en la fecha común y no sumaba lo que decían los Resultados de arriba, y un
  `inicio` distinto haría que la galería y las rutas pagadas de `triple_whale/rutas.py` calcularan alcances distintos.

## Revisión final de E1 (2026-10-10): reglas que cambiaron

- **R6 en «Por país».** La cifra principal va en la moneda común de TODAS las filas (`resumen.moneda_pais`; entonces no
  se convierte nada ni se piden tasas) o, si no la hay, en USD; una fila sin USD dice «USD no disponible» en su celda y
  sale el aviso de la página (`por_pais_sin_usd`). Motivo: siempre iba en USD y sin tasa mostraba «—» callado; un
  proyecto en NOK veía dólares que no pidió.
- **Una sola barra para las copias** (`panel.contexto()["copias_vivas"]`, las del alcance: la barra sigue al primer
  trabajo vivo y dice «Trayendo N copias…»). Motivo: spec §5.1, y cada barra que termina recarga la página: con una por
  tienda y por cuenta eran varias recargas seguidas.
- **«Lo que necesita tu atención»** junta alertas de Triple Whale y de los anuncios de Meta (hasta la integración con
  main, también las recomendaciones propias de E2 tarea 6, jubiladas: lo que hay que corregir en las cuentas de Meta es
  el Diagnóstico de main, en su sección justo debajo) SIN
  quitar textos repetidos y en orden estable alta → media → bien (`panel._atencion`). Motivo: «2 anuncios ganadores» de
  cada fuente son cosas distintas y quitar una escondía la mitad; una cuenta desactivada no puede quedar debajo de «bien».
- **El filtro «Canal»** solo ofrece canales con gasto en el periodo (`triple_whale.datos.canales`, alineado con R9): uno
  sin gasto abría una galería vacía.
- **Análisis pagados antes de R9** no se vuelven a ofrecer por un veredicto que movió R9 (`foto["metodo"]`; skill
  `triple-whale`, «Old analysis»). Motivo: pagar dos veces lo mismo (guardián de gasto).
- Pruebas de la revisión: `tests/test_rendimiento_revision_final.py` (con las mutaciones 22–28 del revisor) y
  `tests/test_rendimiento_r9_plata.py`. Lo diferido: PND-272 a PND-283.

## E2 tarea 4 (2026-10-10): una sola galería y un solo lote

Por qué: con «Cómo mejorarlo» para Meta (E2 tareas 1 a 3) las tarjetas de fuente Meta de E1 eran la misma tarjeta con
el mismo flujo pagado; dos galerías daban dos órdenes, dos filtros y dos lotes (A1 la dejó para E2). Código:
`pestana_rendimiento/galeria.py`, pruebas `tests/test_rendimiento_e2_galeria.py` (con mutaciones del orden, el tope,
la miniatura, el saldo, la fuente en la foto, Referentes y «Meta reporta»).

- **Orden por gasto en USD** (cierra PND-196): cada anuncio en su moneda (Triple Whale: la del proyecto; Meta: la de su
  cuenta) con la tasa del último día del periodo de su alcance (`meta_rendimiento.tasas.usd`, una lectura por moneda).
  Sin tasa o sin moneda, al final en su orden nominal: jamás una tasa inventada (R6). Las tarjetas llevan `fuente`
  ("tw" | "meta"), `moneda` y `gasto_usd`.
- **Una página = 12 mezcladas** y un número fijo de consultas: análisis, tareas vivas y creativos se leen una vez para
  las dos fuentes y `triple_whale.panel.enriquecer` corre una vez por fuente. `triple_whale.panel.contexto` ya no arma
  la galería de Triple Whale (la une esta).
- **El lote**: los `N_LOTE` de más gasto en USD entre las dos fuentes a los que su tarjeta les ofrece el botón; cada clave
  es `"<fuente>:<canal>:<ad_id>"`. Al cobrar, `galeria.claves_confirmadas` recorta a N ENTRE LAS DOS fuentes ANTES de
  separar (si no, cada fuente cobraría hasta N: B6) y `galeria.pedir_lote` llama a `pedidos.pedir_lote` por fuente
  (confirmadas ∩ aún elegibles), en el orden de su primera clave; la primera fuente sin saldo para todo y el aviso dice
  cuántos salieron. Un segundo envío no cobra.
- **El alcance de cada ruta** sale de `panel.alcances` (la misma `_resolver` que el panel; `canal` solo con alcance solo
  Triple Whale). Una `entrada` no vacía que ya no es la clave de ninguna entrada (pestaña vieja) no se ensancha a
  «Todas»: no hay alcance y nada se cobra (como «Actualizar ahora», A5). En el panel, el alcance de Triple Whale sale
  de su contexto (`_alcance_tw_de`) y el de Meta de `_meta`, que lo arma con `alcance_meta` UNA vez y de ahí salen
  también las alertas de los anuncios de Meta (`meta["anuncios"]["ev"]`) y los anuncios ya evaluados que la «Evaluación
  con IA» de Meta cuenta para su N con 7, 14 o 90 días (`meta_panel.diagnostico(evaluados_periodo=)`).
- **Las rutas**: `<fuente>` "tw"/"meta" e ids con `id_valido` (si no, 404 antes de leer); un anuncio que no está en el
  alcance de esa fuente, 404. Sin el alcance de esa fuente (pestaña vieja, desconectada) «Cómo mejorarlo» responde JSON
  `ok: False` sin cobrar. El 402 sin saldo es el de `dashboard._saldo_insuficiente`, como antes. Correo verificado:
  solo «Actualizar ahora» lo exige (`rutas.CON_CORREO_VERIFICADO`); las que cobran no, como en producción (S2 de la
  revisión final, abajo).
- **La tarjeta de Meta** es la misma macro (`_tw_galeria.html`): cuenta con bandera en el sobretítulo, «según Meta» en el
  resultado, sin «Meta reporta» (R12 es de Triple Whale) ni «Guardar en Referentes» (PND-284). Su medio: una pieza de
  Creatv (R2); si no, la imagen que un análisis listo copió a R2; si no, la miniatura de Meta solo si
  `meta_rendimiento.datos.miniatura_valida` (al pintar: PND-282), a su tamaño (`.tw-medio-miniatura`: llega de 64 px y
  agrandada se vería borrosa).
- **Un análisis es de SU fuente** (revisión de la tarea 4): `triple_whale.panel.mismo_alcance` compara la fuente de la
  foto (`foto["fuente"]`, sin ella = Triple Whale) con la del alcance. Una cuenta cubierta por una tienda (R5), vista
  sola (R3), es de fuente Meta y muestra los MISMOS anuncios (mismo `(canal, ad_id)`, las filas y los job_id no llevan
  fuente) que «Todas» muestra como de Triple Whale: sin comparar la fuente, cada tarjeta tomaba el análisis de la otra
  por viejo, volvía a ofrecer pagarlo y lo metía al lote sin fin. Ahora ese análisis es «de otro alcance»: nota neutra y
  solo «Analizar con estos datos», nunca en el lote (`test_un_analisis_de_*_no_es_el_de_la_tarjeta_de_*`).
- **Los tiles de Triple Whale** («Gasto», «Ingresos atribuidos»…) van encima de la galería solo con alcance solo Triple
  Whale: con Meta o mezcla describirían solo una parte de lo que muestra la galería.
- Se jubilaron: `triple_whale.rutas.galeria`, `tarjeta`, `analizar_anuncio`, `analizar_lote` (y el alias
  `_claves_confirmadas`), `rendimiento.ver_anuncios_meta`, `panel.anuncios_meta_pagina`, `_rend_anuncios_meta.html`, el
  JS de `data-rend-mas` y las reglas `.rend-tarjeta*`/`.rend-anuncios-meta`/`.rend-subtitulo`. Sus pruebas apuntan a las
  rutas nuevas y vigilan lo mismo (A1, A3, A4, A5, B6, 402, ajenos 404, mismo origen, aislamiento).

## E2 tarea 5 (2026-10-10): «Evaluar con IA» desde la pestaña (su rama Meta se jubiló al integrar main)

Por qué: «Lo que hace ganar en tu cuenta» vivía en `triple_whale.rutas.evaluar`, aparte de la pestaña. Código: `panel._ia`, `rutas.evaluar`, la macro `ia` de `_tw_secciones.html` (recibe `r.ia` y `r.params`, ya
no `tw`); pruebas `tests/test_rendimiento_e2_evaluar.py`.

- **La ruta** (`POST /evaluar`, `fuente` "tw" o sin ella; otra, 404; `entrada`/`dias`/`canal`) vuelve a armar la muestra
  con `panel.alcances` (la misma resolución que el panel: se cobra lo que se vio) y llama a `pedidos.pedir_evaluacion`
  (Cobros antes de crear la fila, `max_intentos=1`, `libro.exigir(..., tipo="evaluacion")` de main). Una evaluación en
  curso bloquea otra (un `job_id` por proyecto); una vista sin Triple Whale (pestaña vieja) no cobra: «Esa vista ya no
  existe». Con mezcla, una línea dice que mira las tiendas de Triple Whale.
- **Se jubiló** `triple_whale.rutas.evaluar`; sus pruebas apuntan a `/rendimiento/evaluar`. Una entrada que no es del
  proyecto ya no evalúa «Todas»: no evalúa nada.
- **La rama Meta** (un botón por fuente, `extra["fuente"] = "meta"`, «con sus métricas de Meta», la etiqueta «Suecia en
  Meta», `alcance_meta` con `cuentas`, `alcances()["pais"]`, `medios_meta` con `meta_conexion.cargar` y `muestra`
  reordenando por ingresos) **se jubiló al integrar main** (INT-2: una sola implementación por función, gana la de
  producción): la evaluación de las cuentas de Meta es la «Evaluación con IA» de Meta rendimiento E2 (ver abajo).

## E2 tarea 7 (2026-10-10): el detalle del día con Meta y con mezcla

Por qué: A3 dejó para E2 el «Qué pasó el …» de Meta; con Meta o mezcla la gráfica no abría días y la lectura no ofrecía
«Ver qué pasó →» del mejor día. Código: `pestana_rendimiento/resumen.py::dia` (regla 7 del módulo), `panel.dia`
(regla 9), `rutas.ver_dia`, las lecturas nuevas de `meta_rendimiento/datos.py` (skill `meta-rendimiento`) y
`triple_whale.resultados.detalle_dia` con anuncios en su moneda (skill `triple-whale`); pruebas
`tests/test_rendimiento_e2_dia.py` (13 mutaciones atrapadas: orden nominal, tope por cuenta, tope 5, antigüedad por
fuente, +13, entrada ajena, sin tasa, día sin copia, rango, comparación sin tasa, anuncios fuera, inicio común,
arranques desconocidos).

- **Una ruta, `GET /rendimiento/dia?entrada=&fecha=`** (solo GET, solo lectura). Con alcance solo Triple Whale llama a
  `triple_whale.panel.contexto_dia` con la tienda de la entrada (el mismo HTML que `/triple-whale/dia`; el panel de
  esas entradas sigue pidiendo el día a `triple_whale.ver_dia`, sin cambios). Con Meta o mezcla, `resumen.dia`, y
  `rutas.ver_panel` pone su URL en `r.resumen.resultados.datos.url_dia` (`armar(..., con_detalle=True)`). Una `entrada`
  que no es la clave de ninguna entrada (otro proyecto, pestaña vieja) es 400 «Esa vista ya no existe» sin leer nada:
  como en la galería, nunca se ensancha a «Todas».
- **El rango**: del inicio común de R7 (el más tardío de los primeros días de las fuentes; con Meta sola, el de sus
  cuentas) a ayer, y no después del último día que todas las fuentes traen (`_fin_datos`: esos días van «sin copia» en
  la gráfica; sumar solo la fuente que llegó daría una caída que no existe). Fuera, 400 con el motivo.
- **La moneda** es la de los Resultados (R6): la común, o USD con la tasa de ESE día. Sin tasa ese día, 400 «USD no
  disponible ese día…», nunca una tasa inventada; el mismo día de la semana anterior sin tasa simplemente no se compara.
  (El JS muestra «No se pudo cargar ese día.» ante cualquier 400; con Resultados en USD todo día del periodo ya tenía
  tasa, así que ese 400 solo llega con una petición armada o una tasa borrada entre medias.)
- **Los anuncios**: los 5 que más vendieron entre las dos fuentes por ventas en USD (Triple Whale: el Pixel de los
  anuncios con gasto ese día; Meta: el valor de compras), cada uno mostrado en su moneda y, en la mezcla, «según Meta» o
  «según Triple Whale». La consulta de Meta trae los 5 mejores de CADA cuenta (con monedas distintas el orden nominal no
  es el orden en USD) y Python ordena y corta. Sin «Por canal» (es de la vista de una tienda). «Ver todos los anuncios →»
  va a la galería (`d.ir_a = "tw-galeria"`; con Triple Whale solo, a «Ver como tabla»). Ese botón no hacía nada
  desde el 2026-10-08, tampoco con Triple Whale: el recuadro del detalle lleva `data-twr-dia` vacío y el clic lo tomaba
  por «abrir un día»; `static/tw_resultados.js` ahora solo abre días desde un `button[data-twr-dia]` (visto en el
  navegador, 2026-10-10).
- **«Nuevo»** = hasta el primer día con gasto en SU copia + 13, y solo pasados 14 días del inicio de esa copia
  (`edad_conocida` por anuncio); «Ese día arrancaron N» solo si todas las fuentes del alcance lo saben (si no, nada).
- **Una fuente con gasto ese día y sin anuncios copiados** (la copia de anuncios de Meta guarda 90 días; las cuentas,
  400) lo dice (`anuncios_fuera`) en vez de «Ese día ningún anuncio tuvo gasto»: con «Desde el inicio» la lectura puede
  ofrecer un mejor día de hace meses.
- **Consultas fijas**: una lectura por fuente (serie, anuncios, arranques, inicio de la copia, primeros días), una de
  piezas de Creatv y una de tasas por moneda, crezcan o no los anuncios
  (`test_las_consultas_no_crecen_con_los_anuncios`).
- **Días que el detalle no abre (PND-294, 2026-10-12).** Con un periodo fijo la gráfica dibuja días anteriores al
  primero que la ruta acepta y el clic daba «No se pudo cargar ese día.»: `armar(inicio_detalle=…)` los marca `sin_dia`
  con la regla de la ruta (`resumen._primeros`; con Triple Whale solo, `datos.primer_dia_copia`, no `inicio_datos`) y el
  JS no los abre ni los invita (`tests/test_rendimiento_sin_dia.py`, `tests/js/tw_resultados_dia.test.mjs`). El motivo
  depende de cuántas fuentes tienen copia (`varias_fuentes`, no de `fuente == "mixta"`), y `dia_inicial` siempre es un
  día que abre (o "": el JS esconde el recuadro en vez de dejarlo en «Cargando…»).

## Integración con main (2026-10-10): lo de producción, dentro de Rendimiento

Por qué: mientras esta rama jubilaba las pestañas «Triple Whale» y «Meta», otras conversaciones sacaron a producción
(main 7bb9208b, alembic 0039) Meta rendimiento E2, los ganchos y el copy de Triple Whale, el NVP y la página por partes,
encima de esas pestañas. Rulings INT-1..8 en `.superpowers/sdd/2026-10-10-pestana-rendimiento-e2/integracion-main.md`;
el informe de la integración, al lado (`integracion-report.md`). Dónde vive cada cosa:

- **Diagnóstico y Segmentos de Meta** (main E2): los parciales `_meta_diagnostico.html` (después de «Lo que necesita tu
  atención») y `_meta_segmentos.html` (después de «Campañas» y «Conjuntos»), con `mr` = `r.meta.e2` de
  `meta_panel.diagnostico` sobre TODAS las cuentas de Meta del alcance (`meta_estructura`, cubiertas incluidas). Sus
  enlaces al Administrador de anuncios van tal cual. Las alertas «alta» de Meta (Alertas) llevan a `#rendimiento`.
- **«Evaluación con IA» de Meta** (main E2, cobra): `_meta_evaluar.html` y `_meta_evaluacion.html` después de «Lo que
  hace ganar en tu cuenta». Evalúa TODAS las cuentas de Meta de la entrada (`meta_estructura`, también las que cubre
  una tienda por R5 y las de un proyecto con una tienda sin país por R4): PND-290, Daniel 2026-10-12, «al unir ambos
  tableros tenemos que traer todo de ambos» (hasta entonces solo `meta_fuente`, y Noruega se quedaba sin la evaluación
  que la vieja pestaña Meta sí daba). Lee solo la copia de Meta, así que nunca hay dos fuentes en un prompt; si entra
  una cuenta cubierta (`mr.con_pixel`), una línea dice que usa las cifras del Pixel de Meta y que las ventas de Triple
  Whale las evalúa «Lo que hace ganar en tu cuenta». El formulario manda `entrada`, y `meta_rendimiento.rutas.evaluar` las resuelve con
  `panel.cuentas_evaluacion_meta` (la misma `_resolver`; una entrada vieja no se ensancha a «Todas») y se las pasa a
  `analisis.preparar(ids=)`. «Desde el inicio» evalúa los últimos 30 días (el defecto de la vieja pestaña; el texto lo
  dice); con 7, 14, 30 o 90, ese periodo. El N y el precio del botón salen del mismo cálculo que la ruta (E2-R6;
  `tests/test_rendimiento_meta_e2.py`). Los anuncios ya evaluados de la galería solo se reusan si la estructura es
  justo la de fuente Meta (`_meta`, `reusar`). Precio, `n`/`precio_visto`, `max_intentos=1` y el gasto son los de main,
  sin tocar.
- **NVP**: en Resultados de Triple Whale (fuente «tienda» o «anuncios»; con Meta o mezcla no hay tarjeta NVP: sería de
  una parte del alcance), en «Ver como tabla» y en cada tarjeta de la galería (las de Meta, de la copia de Triple Whale
  por `ad_id`; sin Triple Whale, sin la línea), y para las cuentas de Meta una línea arriba de «Campañas y conjuntos»
  más la columna en esas tablas (`meta_panel.nvp_estructura`). El KPI de la vieja pestaña Meta y su «Por cuenta» no
  tienen lugar aquí (PND-281).
- **Ganchos y copy de Triple Whale**: el detalle de un análisis (`_tw_analisis.html`, de `triple_whale.analisis_detalle`)
  se abre desde la galería única; su JS (esperas, «Probar los N ganchos» por fetch) vive en `_tab_rendimiento.html`.
  Un análisis de un anuncio de Meta sin tienda también los ofrece si su video está en R2 (PND-289).
- **Lo jubilado de esta rama**: las recomendaciones propias de E2 tarea 6 (`meta_rendimiento/recomendaciones.py` nuestro,
  `datos.objetos_para_recomendar`, `meta_rendimiento/constantes.py`, `tests/test_rendimiento_e2_recomendaciones.py`;
  dos reglas sin equivalente quedaron como PND-287), la rama Meta de E2 tarea 5 (arriba) y la limpieza propia de la base
  de pruebas (quedó la de main: `tests/test_conftest_limpieza.py`).
- **Pendientes renumerados** (INT-6: main llegó al PND-270): los de esta rama, del 209 al 224, pasaron al 271–286 (209 →
  271, 210 → 272, …, 224 → 286); 271 y 282 están cerrados.
- Dos arreglos de la revisión de E2 tarea 7: `rutas.ver_dia` rechaza una fecha fuera de 2000–2100 y `resumen.dia` mira el
  rango antes de restar días (0001-01-02 daba 500), y `anuncios_fuera` dice qué fuente no trae sus anuncios ("tw",
  "meta" o "ambas") para que el aviso no culpe siempre a la copia de 90 días de Meta.

## Revisión final de E2 e integración (2026-10-10): lo que cambió

Revisores `revisor`, `guardian-gasto` y `auditor-seguridad` sobre `git diff origin/main HEAD`; decisiones del
coordinador en `.superpowers/sdd/2026-10-10-pestana-rendimiento-e2/final-fixes.md`, informe al lado
(`final-fixes-report.md`). Cada punto con su prueba:

- **G1. Ganchos de un anuncio de Meta, apagados.** «Probar los 3 ganchos» de un análisis de fuente Meta cobraría unos
  US$ 1,01 de Kling por un camino sin prueba real: `triple_whale.ganchos.puede_probar` da `MOTIVO_META`, el detalle
  no pinta el botón y `ganchos_probar` responde 409 sin crear ni reservar. Desde el 2026-10-12 la única excepción es
  un admin en colorado_forja (`ganchos.prueba_meta_permitida`; Daniel: la prueba real se hace ahí, viendo el precio;
  en otro proyecto con Cobros la pagaría el cliente); se abre a todos tras esa prueba (PND-289).
- **G2. El precio de «Cómo mejorarlo» de un anuncio de Meta** usa la duración que guardó un análisis anterior del
  mismo anuncio (`triple_whale.panel.precio_analisis(creativo, filas, fuente)` + `duracion_vista`): un anuncio de
  una cuenta sin tienda no tiene `tw_creativo` y suponía 30 s. La misma llamada alimenta la tarjeta, el total del lote
  (`galeria.armar`) y el cobro (`pedidos.pedir_analisis`), con las filas ya leídas.
- **G3. «Evaluar con IA» de Triple Whale compara el precio visto** (la guarda E2-R6 de la de Meta): el formulario de
  la macro `ia` manda `n` y `precio_visto` (`usd_precio`; sin él, el botón apagado) y
  `pedidos.pedir_evaluacion(..., n_visto=, precio_visto=)` (obligatorios, por nombre) no crea ni reserva nada si no
  coinciden: el aviso dice el precio de ahora.
- **G4.** El prompt de «Cómo mejorarlo» de un anuncio de fuente Meta no recibe la evaluación de cuenta de Triple
  Whale (`evaluacion_cuenta=None`; los productos más vendidos sí).
- **S1.** Soltar una cuenta de Meta (quitarla o desconectar) borra los análisis de fuente Meta de esa cuenta y,
  después, su imagen y su video en R2 (skill `meta-rendimiento`, «Disconnecting»). Desde el 2026-10-12 (PND-295) tampoco
  quedan copias cuando la cuenta se suelta con un «Cómo mejorarlo» corriendo o pidiéndose, y lo que R2 no borró se
  reintenta cada día (skill `meta-rendimiento`, «Releasing an account while…»). **S3.** La imagen copiada de Meta
  solo se abre como JPEG/PNG/WEBP/GIF.
- **S2. Correo verificado solo en «Actualizar ahora»** (`rutas.CON_CORREO_VERIFICADO`): producción no tiene SMTP y
  la mitad de los usuarios cliente no pueden verificar; las rutas que cobran no lo exigían allá y siguen sin exigirlo
  (el mismo origen sí). Cuando haya SMTP: PND-292.
- **B1.** Un análisis de fuente Meta dice Meta: el aprendizaje («Ganó en Meta…», `origen: "meta"`) y el alcance del
  detalle (la cuenta, o «tus cuentas de Meta»; nunca «Todas las tiendas»).
- **B2. «Desde el inicio» de los anuncios de Meta** arranca en el primer día de la copia de ANUNCIOS
  (`meta_rendimiento.datos.primer_dia_anuncios`, 90 días), no en el de cuentas (A2). Esa ventana corre cada día: el
  análisis guarda `foto.alcance_dias` y `triple_whale.panel.mismo_alcance` da por el mismo alcance uno de Meta pedido
  en «Desde el inicio» (ni viejo ni de vuelta en el lote por eso; uno sin la marca cae en «otro alcance», nota
  neutra). Triple Whale no cambia.
- **T1/T2.** Pruebas para las mutaciones 27 (cada tarjeta de Meta en la moneda de SU cuenta, orden en USD) y 25 (el
  envío de «Probar los ganchos» se frena antes del fetch).
- Diferido: PND-290 a PND-295. PND-290 cerrado el 2026-10-12 (evaluación de Meta para todas las cuentas, arriba).

## Trampas

- Lo que se jubiló el 2026-10-10 con la galería única (no lo revivas): ver «E2 tarea 4»; con la evaluación de la
  pestaña, `triple_whale.rutas.evaluar` (ver «E2 tarea 5»); al integrar main, lo de «Integración con main».
- Cuando main vuelva a tocar algo de las pestañas jubiladas, se porta a Rendimiento y se incluye su parcial tal cual,
  armándole el contexto desde `pestana_rendimiento/panel.py` (como E2 de Meta); nunca se revive la pestaña.
- Lo que se jubiló el 2026-10-09 (no lo revivas): `_tab_triple_whale.html`, `_tab_meta.html`, `_tw_panel.html`,
  `_meta_panel.html`, `_meta_anuncios_filas.html`, `meta_rendimiento/grafico.py`, las rutas `triple_whale.ver_panel`,
  `triple_whale.sincronizar`, `meta_rendimiento.ver_panel`/`ver_anuncios`/`ver_conjuntos`/`sincronizar` y
  `meta_rendimiento.panel.contexto`/`anuncios_pagina`/`conjuntos_pagina`. Sus pruebas pasaron a `/rendimiento/panel`
  (con `entrada=` o los `tienda=`/`cuenta=` viejos) y `/rendimiento/actualizar`.
- «Por país» reemplazó a «Por tienda» (también con solo tiendas) y no compara con el periodo anterior.
- El panel trae un solo `<script>`: el JSON inerte `#tw-resultados-datos`. Las pruebas que buscan «sin scripts» lo
  descuentan.
- Con Meta conectado y sin cuentas, el panel igual se pide y dice que faltan cuentas (la pestaña puede tener Triple Whale).
