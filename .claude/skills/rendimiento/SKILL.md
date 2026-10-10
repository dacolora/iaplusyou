---
name: rendimiento
description: "Rendimiento: la pestaña que junta Triple Whale y Meta (pestana_rendimiento/), el selector por país, la fuente de cada cifra, «Resultados» y «Por país» mezclados, «Actualizar ahora» y los alias de las pestañas viejas. Cargar antes de tocar pestana_rendimiento/, _tab_rendimiento.html, los _rend_*.html, _tw_secciones.html, _meta_secciones.html, pantallas/rendimiento.css, o al decidir de qué fuente sale una cifra."
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
  `meta_rendimiento.tasas.mapa`.
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
  `analizar_anuncio` (POST `/anuncio/<fuente>/<canal>/<ad_id>/analizar`) y `analizar_lote` (POST `/analizar-lote`). El
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
- **R13. Lo pagado no se reescribe.** «Evaluar con IA», Referentes, «Llevar a Crear» y Pausar/Activar siguen en
  `triple_whale/rutas.py` con su alcance y sus garantías; esta pestaña solo les pasa la tienda de la entrada (o
  `None`). «Cómo mejorarlo» y «Analizar los N» pasaron en E2 tarea 4 a las rutas de la pestaña (la galería es una con
  las dos fuentes), pero cobran con el mismo `triple_whale/pedidos.py` y el alcance de la fuente de cada anuncio, con
  todas sus garantías. El JS de la galería se trajo tal cual (`tests/test_tw_tarjetas_js.py` lo lee aquí) y no cambió
  al unir la galería: cada URL sale de la plantilla.
- **R14. Anuncios de fuente Meta sin IA** solo en E1 (tarjeta sin botón, ni apagado). Desde E2 (tareas 1 a 4) tienen
  «Cómo mejorarlo» con la misma tarjeta y el mismo flujo pagado.
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
- **A5.** «Actualizar ahora» es una ruta (`rendimiento.actualizar`) que llama a `triple_whale.rutas.pedir_copia` y
  `meta_rendimiento.rutas.pedir_copia` con los `job_id` de siempre, la pausa compartida de Meta y la espera de 30
  minutos de quien no es admin. Solo la entrada VACÍA es «Todas»: una que ya no existe (pestaña vieja, país quitado,
  la de otro proyecto) no encola nada y dice «Esa vista ya no existe: recarga la pestaña.» (revisión de la tarea 8:
  ensanchada a «Todas» copiaba todas las cuentas y gastaba el límite de uso de Meta que necesitan los lanzamientos).
- **A6.** E2 (PND-192) trae «Cómo mejorarlo»/«Evaluar con IA» para Meta con la misma tabla y tarea; la copia de
  desgloses `meta_desglose` y los avisos por correo de Meta quedaron aparte (PND-209).
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
- **«Lo que necesita tu atención»** junta alertas de Triple Whale, de los anuncios de Meta y recomendaciones de Meta SIN
  quitar textos repetidos y en orden estable alta → media → bien (`panel._atencion`). Motivo: «2 anuncios ganadores» de
  cada fuente son cosas distintas y quitar una escondía la mitad; una cuenta desactivada no puede quedar debajo de «bien».
- **El filtro «Canal»** solo ofrece canales con gasto en el periodo (`triple_whale.datos.canales`, alineado con R9): uno
  sin gasto abría una galería vacía.
- **Análisis pagados antes de R9** no se vuelven a ofrecer por un veredicto que movió R9 (`foto["metodo"]`; skill
  `triple-whale`, «Old analysis»). Motivo: pagar dos veces lo mismo (guardián de gasto).
- Pruebas de la revisión: `tests/test_rendimiento_revision_final.py` (con las mutaciones 22–28 del revisor) y
  `tests/test_rendimiento_r9_plata.py`. Lo diferido: PND-210 a PND-221.

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
  también las alertas y las recomendaciones de los anuncios de Meta (`meta["anuncios"]["ev"]`).
- **Las rutas**: `<fuente>` "tw"/"meta" e ids con `id_valido` (si no, 404 antes de leer); un anuncio que no está en el
  alcance de esa fuente, 404. Sin el alcance de esa fuente (pestaña vieja, desconectada) «Cómo mejorarlo» responde JSON
  `ok: False` sin cobrar; el correo sin verificar, también JSON al fetch (`_correo_verificado`). El 402 sin saldo es el
  de `dashboard._saldo_insuficiente`, como antes.
- **La tarjeta de Meta** es la misma macro (`_tw_galeria.html`): cuenta con bandera en el sobretítulo, «según Meta» en el
  resultado, sin «Meta reporta» (R12 es de Triple Whale) ni «Guardar en Referentes» (PND-222). Su medio: una pieza de
  Creatv (R2); si no, la imagen que un análisis listo copió a R2; si no, la miniatura de Meta solo si
  `meta_rendimiento.datos.miniatura_valida` (al pintar: PND-220), a su tamaño (`.tw-medio-miniatura`: llega de 64 px y
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

## Trampas

- Lo que se jubiló el 2026-10-10 con la galería única (no lo revivas): ver «E2 tarea 4».
- Lo que se jubiló el 2026-10-09 (no lo revivas): `_tab_triple_whale.html`, `_tab_meta.html`, `_tw_panel.html`,
  `_meta_panel.html`, `_meta_anuncios_filas.html`, `meta_rendimiento/grafico.py`, las rutas `triple_whale.ver_panel`,
  `triple_whale.sincronizar`, `meta_rendimiento.ver_panel`/`ver_anuncios`/`ver_conjuntos`/`sincronizar` y
  `meta_rendimiento.panel.contexto`/`anuncios_pagina`/`conjuntos_pagina`. Sus pruebas pasaron a `/rendimiento/panel`
  (con `entrada=` o los `tienda=`/`cuenta=` viejos) y `/rendimiento/actualizar`.
- «Por país» reemplazó a «Por tienda» (también con solo tiendas) y no compara con el periodo anterior.
- El panel trae un solo `<script>`: el JSON inerte `#tw-resultados-datos`. Las pruebas que buscan «sin scripts» lo
  descuentan.
- Con Meta conectado y sin cuentas, el panel igual se pide y dice que faltan cuentas (la pestaña puede tener Triple Whale).
