---
name: experimentos
description: "Experimentos en Meta y su centro de resultados: armar y lanzar pruebas (campaña → conjunto por país → anuncio por pieza), «Nuevo experimento» con presupuesto total + días, métricas, el decisor (ganador/perdedor), modos manual/semi/auto, escalar, derivar, rescatar, filtros y panel de pieza (resultados.py) y el dinero del Tablero (totales desde el inicio, OUTCOME_SALES). Cargar antes de tocar experimentos.py, lanzador.py, decisor.py, modos.py, acciones.py, derivaciones.py, propuestas.py, tablero.py, meta_detalle.py, resultados.py, presupuesto_experimentos.py, static/exp_resultados.js, _tab_experimentos.html, exp_nuevo.html o las plantillas _exp_*."
---

# Experimentos, decisor y centro de resultados

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Experimentos** (`experimentos.py` + `lanzador.py`): the ecommerce test loop's unit
of work. An experiment (table `experimento`, `legado=False` — `ads.py`'s "Anuncios
sueltos" is the one `legado=True` row per client and is untouched) names countries with
a daily budget each, a total cap, days, objective and destination URL; pieces (finals
for their own country, or text-free clones for any country) are attached as
`experimento_pieza` rows. `lanzador.lanzar` maps it onto Meta as 1 campaign
(`spend_cap` = tope total, only when it clears Meta's minimum) -> 1 adset per country
(`Targeting().edad().paises([pais])`, budget in the ad ACCOUNT's currency, never the
country's) -> 1 ad per piece, all created `PAUSED`, saving every id as soon as Meta returns it so
a retry resumes instead of duplicating. **Lanzar crea y activa** (pedido de Daniel 2026-10-08: «si la persona ya lo
había configurado es porque ya le había dado aprobar»; es la excepción a la regla 1 de CLAUDE.md: el clic de «Lanzar a
Meta», con el gasto diario a la vista en Revisar, en el botón y en el confirm, ES la aprobación). Las dos rutas de la
persona (`exp_probar` y `exp_lanzar`, que también sirve para «Reintentar lanzamiento») encolan la tarea `exp_lanzar` con
`{"activar": True}` y `max_intentos=1`; la tarea corre `lanzador.lanzar` y después `lanzador.activar_tras_lanzar`, que
activa por el MISMO camino que «Activar todo» (`cambiar_estado(..., "ACTIVE")`: campaña, conjuntos —también
`meta_adsets` de apps—, anuncios y el plazo de PND-113) solo si el experimento quedó `pausado` y ninguna pieza quedó sin
anuncio o en error; registra «Activado al lanzar: ≈ X al día» (`datos`: diario y moneda). Un `lanzar` que falla sale
por excepción y nada se activa. Si la activación falla, vuelve a pausar todo (lo que alcanzó a activarse gastaría con el
experimento «en pausa» aquí), guarda el motivo en `experimento.error` (lo borra `_a_corriendo` al activar después) y un
evento, y no se reintenta. Sin `activar` (cualquier otro llamador) todo queda en pausa como antes;
`derivaciones`/`lanzar_piezas_nuevas` no pasan por aquí. Ronda de guardian-gasto (2026-10-08): (1) con `activar` la
tarea llama `lanzar(..., soltar=False)` y el experimento sigue en `lanzando` hasta que `activar_tras_lanzar` lo saca
(a `corriendo`, o a `pausado` con motivo en `error`): así la barra sigue sondeando (etapas
`ETAPAS_LANZAR_Y_ACTIVAR`, con «Activar»), `exp_cerrar` rechaza, `cambiar_estado` dice «Espera a que termine el
lanzamiento» (solo la tarea pasa `desde_lanzamiento=True`), y el hook `interrumpida` y la reconciliación de huérfanos
de `dashboard` llaman `lanzador.repausar` ANTES de marcar el error (lo que alcanzó a activarse vuelve a pausa);
`_a_corriendo` nunca pisa `cerrado`. Un fallo al activar también manda `notificaciones.avisar("error_lanzamiento")`.
(2) «Nuevo experimento» es de un solo envío: `exp_nuevo` pinta un `token_form` oculto, `exp_probar` arma
`clave_form` («t:<token>», o sin token «h:<huella>» de piezas × países, diarios, días, total, objetivo, destino, app)
y `experimentos.crear_con_piezas` la busca con el candado de escritura tomado antes de leer (token: 1 día; huella:
10 min); repetida es `ExperimentoRepetido(eid)`: no se crea ni se encola nada y la ruta lleva al que ya existe.
Pruebas: `tests/test_lanzar_activa.py`. `exp_estado`
activates/pauses the whole experiment or one country inline. Metrics: `lanzador.refrescar`
appends a `metrica_snapshot` per ad (thruplay, purchases, ROAS when Meta reports them) —
the worker periodic `exp_refrescar_todos` (every 2 h, `worker.PERIODICAS`) does it for
every `corriendo` experiment. Every verdict/action writes an `evento`. Experiment
states: `armando -> lanzando -> pausado <-> corriendo -> cerrado`, `error` on a failed
launch (resumable). Meta's raw errors («Meta Ads (<edge>) respondió 400: {JSON cut at 500 chars}») are stored as-is but shown through `meta_errores.explicar` (filter `error_meta`, also used by `tablero.alertas` and `lanzador.traducir_error_meta`): known codes become what to do (1885183 app in Development mode — also recognized in the already-explained text, so it re-renders in the viewer's language —, 190 reconnect, 10/200/294 permissions, 4/17/32/613 and the 80000…80014 business-use-case family (`meta_errores._LIMITE`, `es_limite`) rate limit, 368 policy block, 1/2 temporary), otherwise Meta's own `error_user_title/msg`, otherwise the code; the experiment card keeps the raw text in a folded «Detalle técnico». UI de Experimentos («la galería primero», 2026-09-20; movida a su propia página el 2026-10-03, E2): la pestaña abre con
RESULTADOS (ver «Centro de resultados» abajo) y ya no lista las piezas de Crear. «Nuevo experimento» es la ruta `exp_nuevo`
(`exp_nuevo.html` + `_exp_probar.html`) a pantalla completa, sin menú lateral y con «← Volver a resultados»; sus estilos
viven en `static/estilos/pantallas/experimento-nuevo.css`. El recorrido es 01 Piezas · 02 Dónde · 03 Total y días ·
04 Revisar. El paso 1 es la galería de toda pieza con URL pública (`experimentos.elegibles`: videos e imágenes de Crear,
piezas de sprints, finales; `origen`, `formato`, `en_experimentos`), con filtros y buscador en el navegador. El paso 2
son países con bandera y edad. El paso 4 es la cuadrícula pieza × país, el nombre automático editable («Prueba 20 sep ·
3 piezas · CO, MX»), «Avanzado» (objetivo, atribución, modo, URL) y el aviso de doctrina. Un solo `POST exp_probar` corre
`experimentos.crear_con_piezas` (experimento + filas `experimento_pieza` en UNA transacción, `validar_combinacion`: una
final solo en su país, clones e imágenes solo en los países del experimento) y encola `exp_lanzar` con `activar`: el
paso Revisar dice «Al lanzar empieza a gastar: ≈ X al día» (`.exp-al-lanzar`) y el botón «Lanzar a Meta · ≈ X al día»
(`.exp-lanzar-dia`), los dos desde el `diario` que ya calcula `refrescarCuenta` (2026-10-08). **El presupuesto se pide como UN total y los días** (Daniel, 2026-10-02: la pantalla vieja pedía
diario + tope + días, respondía con un multiplicador y nunca decía cuánto iba a gastar, que roza la regla 1 de la casa).
`presupuesto_experimentos.py` es el único lugar de la cuenta: `repartir` (diario de cada país = total × su parte de
anuncios ÷ días, redondeado HACIA ABAJO a la unidad de la moneda, de modo que la suma por los días nunca pasa del
total; devuelve los países bajo el mínimo y el total mínimo que lo arregla), `atajos` (Prueba rápida · Estándar ·
Fuerte = 4× / 8× / 15× el mínimo diario por anuncio durante 4 / 7 / 10 días; son una «Sugerencia», no el precio de un
proveedor), `validar` (la comprobación del servidor, que no se fía del navegador) y `PRESUPUESTO_MINIMO_DIARIO` (que
`dashboard.py` importa de ahí); `static/presupuesto_exp.js` es su espejo para pintar al instante y
`tests/test_presupuesto_experimentos.py` corre los dos con los mismos casos (prueba de paridad, como el editor). El POST
no cambió (`presupuesto_<país>`, `tope_total` = el total, `dias`…), y el servidor rechaza un reparto cuya suma × días
supere el total × 1,01 (el 1 % es el margen por redondeo): así «Máximo que puede gastar» es verdad aunque alguien arme el
POST a mano. El titular dice **«Máximo que puede gastar» solo cuando Meta recibe `spend_cap`** (total ≥
`lanzador.minimo_tope_campana(moneda)`); con un total menor dice «Presupuesto planeado» y una línea de que Meta no pone un
tope duro y que el límite lo dan los diarios por país y la fecha de cierre (ronda 1 de R4, 2026-10-03: decir «máximo»
sin tope duro prometía de más). Los días cuentan desde la PRIMERA activación (desde 2026-10-08, la que hace el propio lanzamiento si sale bien; ver PND-039/044/113
al final). Llegadas a la página: Crear, Final edition, los anuncios sueltos y «Probar en otro experimento» del panel de
una pieza enlazan a `exp_nuevo?piezas=<pieza_id>` (la pieza llega marcada); un hash viejo `#experimentos?piezas=` salta ahí
por JS; Catálogo › «Crear experimento» redirige a `exp_nuevo?exp_nombre=&exp_destino=`, que el paso 4 trae puestos. Images are real
Meta ads (`crear_creative_imagen`, no video upload); the decisor skips ThruPlay for them
(`contexto["es_imagen"]`), never asks `derivar`/`rescatar` on one (a winner only scales, a
loser is only paused — `derivaciones` refuses image sessions), and they never enter the
organic publish path (`organico`/`publicador` are video-only; for an image piece `url_video`
IS the image URL, so every gate also checks `es_imagen`). `experimentos.ESTADOS_VIVOS`
(the gallery's «en prueba» label) includes `decidido`: winners keep delivering there.

**Decisor, escalera y modos** (`decisor.py`, `modos.py`, `propuestas.py`, `acciones.py`,
`derivaciones.py`, `notificaciones.py`): the part of the loop that closes on its own.
`decisor.decidir(snapshots, reglas, contexto)` is a pure function — traffic gate first
(impressions/spend/hours evidence, then CPC/CTR/ThruPlay thresholds; zero impressions is
never a loser; ThruPlay is skipped when `contexto["es_imagen"]`), sales gate second only with attribution (ROAS/CPA after
`ventana_ventas_horas`), top-third ranking per country when ≥ 3 ads — returning
`ganador | perdedor | inconcluso | pendiente` plus an action. Rules layer
`REGLAS_DEFECTO ← proyecto.json["reglas_experimentos"] ← experimento.reglas`. The worker
periodic `exp_decidir_todos` (1 h) runs `exp_decidir` per `corriendo` experiment: verdicts
are persisted once per piece, and every action goes through `acciones.pedir`, which
consults `modos.resolver(modo, accion)` — manual proposes everything, semi executes
`pausar`/`archivar` and proposes `escalar`/`derivar`/`rescatar`/`activar`, auto executes
all — and downgrades to a `propuesta` whenever the experiment's tope is reached or the
derivation depth hits 2. Winners: `escalar_pais` (+`escalar_pct_dia` up to
`escalar_tope_dia`) and `derivar` (a child experiment with `n_reediciones` guion variants
via `final_edition.producir(opciones.variante/variante_tipo)` and `n_regeneraciones` new
clones via `creative_flow.duplicar`). Losers: `rescatar` climbs `escalon_rescate` 1 → 2 → 3
(hook re-edit, structure re-edit, regeneration; each pauses the previous piece) and
`archivar` marks the concepto at step 3. `derivaciones.py` is the async state machine
(`experimento.extra["derivaciones"]`, advanced by the periodic `exp_avanzar_todos` every
10 min) that produces the pieces, attaches them, creates their ads with
`lanzador.lanzar_piezas_nuevas` and asks `activar` per the mode. Every RMW on
`experimento.extra`/`paises`/`experimento_pieza.extra` goes through `experimentos.actualizar_extra`,
`actualizar_pais`, `marcar_pieza`, which take SQLite's write lock BEFORE reading
(`_bloquear`) — pysqlite otherwise runs the SELECT in autocommit and two processes lose
updates. Notifications (`notificaciones.avisar`: propuesta, ganador, rechazo_meta,
error_lanzamiento) go by SMTP when `SMTP_HOST` is set and the project has a
`correo_notificaciones`; otherwise they are only eventos.

**Sin Meta conectado** (2026-10-08, pedido de Daniel: happyflops tenía Triple Whale y no Meta, y la pestaña le mostraba
la tabla vacía y una galería que dejaba marcar piezas que después no se podían lanzar): `ver_cliente` pone
`exp_sin_meta = not meta_conectado and not experimentos.hay_historial(cliente)` (un EXISTS: experimento no legado o
anuncio suelto; con Meta conectado ni se consulta). Con `exp_sin_meta` la pestaña es SOLO la tarjeta `#exp-sin-meta`
(«Conecta Meta…» o, con `estado == "roto"`, «La conexión con Meta se cortó»; una línea más si hay Triple Whale) con el
botón a Configuración › Conexiones › Meta (`data-ir-tab="settings" data-ancla="config-meta"`): ni resultados, ni
reglas del motor, ni CSV, y Configuración esconde su enlace a las reglas. Con historial y sin Meta se ven los
resultados con un aviso, pero ningún «+ Nuevo experimento» (tampoco en `_exp_resultados.html` ni el `data-url-nuevo`).
`exp_nuevo` sin Meta redirige a `#experimentos` (no pinta la galería) y `exp_probar`/`exp_crear` avisan «Conecta Meta en
Configuración › Conexiones…». Y la página del proyecto abre en Crear en vez de Experimentos (`cliente.html`), también
si Experimentos quedó como la pestaña recordada; un `#experimentos` explícito la sigue abriendo. Pruebas:
`tests/test_experimentos_sin_meta.py`.

There is also NO Campañas tab any more: `_tab_ads.html` is gone, `nueva_campana`/`publicar_ad`
are no-ops that flash and redirect, and the legacy "Anuncios sueltos" (Forja's ads) render
read-only inside the centro de resultados, plegados en su «Historial» (`_anuncios_sueltos.html`: KPIs, pausar/activar,
actualizar). Las reglas por defecto del decisor (`cfg_reglas`) se editan en el cajón **«Cómo decide el motor»** del
armazón de la pestaña (`#reglas-motor`; antes «Reglas del motor», no en Configuración) y cada experimento puede cambiar
una en su propia gestión (`exp_reglas`). Se muestran en palabras, sin claves de código (spec §4.7, 2026-10-03):
`decisor.ETIQUETAS` da la frase de cada regla (`N_` + `|traducir` en la plantilla) y `decisor.GRUPOS_REGLAS` las agrupa
en cuatro `<fieldset>` («Antes de juzgar una pieza» · «Cuándo pierde por tráfico» · «Cuándo gana o pierde por ventas» ·
«Qué hace con una ganadora»); toda clave de `REGLAS_DEFECTO` está en UN solo grupo y una prueba lo exige (una que falte
no se vería). `_form_reglas.html` es el mismo formulario: los `name` de los campos son las claves de `REGLAS_DEFECTO`, y
`cfg_reglas`/`exp_reglas` no cambiaron.

**Centro de resultados (E2, 2026-10-03)** (spec `docs/superpowers/specs/2026-10-02-experimentos-centro-de-resultados-design.md`;
reemplaza la pantalla de la galería y la pestaña Tablero; no cambia el motor: lee lo que ya guardan lanzador, decisor y
detalle de Meta). La pestaña es un **armazón** (`_tab_experimentos.html`: cabecera con «+ Nuevo experimento» y «Descargar
CSV del mes», el cajón «Cómo decide el motor», `#cr-resultados`, el `<dialog id="cr-panel">` y los
textos del JS en `#cr-textos`) más un **fragmento** que llega por `fetch`. El HTML de la página del proyecto ya no trae las
piezas elegibles, el tablero ni la gestión de cada experimento (la regla de `ui`: lo pesado llega por fragmento).
Desde PND-137 (2026-10-07), tampoco los calcula: `_contexto_motor_experimentos` solo entrega reglas y correo; el
bloqueo de «Cambiar de forma» cuenta experimentos vivos con `contar_vivos`, sin cargar piezas. El
Tablero dejó de ser pestaña: `resolver('tablero')` de `cliente.html` abre Experimentos, y el hash `#tablero` o `#ads` también.
- **Rutas** (las tres GET y solo leen: nada gasta ni publica; el acceso lo decide `_guard_por_cliente`): `exp_resultados`
  (`/cliente/<c>/experimentos/resultados`, fragmento `_exp_resultados.html`; con `?exp=<id>` suma la gestión
  `_exp_gestionar.html`; trae `elegibles_exp` solo cuando algo del fragmento las pinta: el «Agregar pieza» de un experimento en
  armado o un anuncio suelto en cola), `exp_pieza` (`/experimentos/pieza/<ep_id>`, panel `_exp_pieza.html`; una pieza de
  otro proyecto o que no existe es 404 porque `resultados.pieza` solo busca entre las del `cliente`) y `exp_nuevo`
  (`/experimentos/nuevo`, el MISMO URL que el POST `exp_crear`, otro método). Las acciones POST de un experimento
  redirigen a `#experimentos?exp=<id>` (`_volver_exp(cliente, eid)`; sin id, a `#experimentos`) para no perder la selección.
- **Cliente** (`static/exp_resultados.js`, ES5, pasa `node --check`): el filtro vive en el hash
  `#experimentos?exp=&dias=&pais=&pieza=&tipo=&moneda=`, así un enlace o un recargar lo conserva; al abrir la pestaña o
  cambiar el filtro pide el fragmento (solo gana el último pedido; una redirección, p. ej. sesión vencida, no se pinta como
  fragmento) y dibuja SVG desde los atributos `data-cr-*` y el JSON de `#cr-datos` / `.cr-datos-pieza` (barras + línea, curvas
  mínimas, dona, retención, embudo), solo con `textContent`/`setAttribute`. Un `?exp=<id>` viejo de la dirección pasa UNA vez
  al hash (`consumirExpViejo`: si se releyera, el filtro no se podría quitar).
- **`resultados.py`** (puro: no llama a Meta ni a Claude, cero costo): `Filtro` (inmutable; `dias` 14 por defecto,
  `experimento_id`, `pais`, `ep_id`, `tipo`, `moneda`), `filtro_de(request.args)` (lo inválido vale el defecto, nunca un
  error), `a_query(filtro, **cambios)` (la query de un enlace: solo lo que difiere del defecto, `None` quita), `periodo`
  (7 · 14 · 30 · 90 días o 0 = desde el inicio; se compara con el periodo anterior de igual largo, salvo desde el inicio;
  el tope de 180 días solo recorta lo que se DIBUJA, los totales suman todo), `cargar(cliente, filtro)` → `Carga` y
  `contexto(cliente, filtro)` → el dict que pinta el fragmento (más `datos_graficos`, JSON). No tiene caché propia; la de
  60 s es la de `dashboard._contexto_tablero`.
- **De dónde sale cada número**: el DINERO (gasto, compras, ingresos, ROAS, costo por compra) del motor de `tablero.py` sobre
  los datos filtrados (`tablero.filtrar`: las mismas funciones, la misma atribución), así los totales, el mes a mes y lo
  que ya se veía cuadran; TODO lo demás (impresiones, clics, CTR, CPC, CPM, gancho, retención, embudo, desgloses) de
  `metrica_dia` / `metrica_desglose`. Un cociente nunca mezcla fuentes. La moneda es la del experimento y nunca se convierte
  (con más de una aparece un filtro; por defecto, la de más gasto). El dinero se suma con `tablero._deltas_pieza` sobre
  la carga (ya no llama `resumen_periodo` ni `serie_diaria`). Trampa: `tablero._datos` recarga el proyecto ENTERO si
  se le pide una ventana que empieza antes de `datos.desde`, y el filtro se pierde; y cada delta necesita el snapshot
  anterior a su ventana: por eso `cargar` trae desde el inicio del periodo anterior (o `tablero.INICIO`) y nada pide una
  ventana más vieja.
- **Revisión final de E2 (2026-10-03), tres reglas de plata:** (1) **ROAS «—» sin ventas medibles**: compras, ingresos,
  ROAS y costo por compra existen solo si algo de lo elegido mide ventas: atribución Pixel, tienda o Triple Whale
  (`resultados.ATRIBUCION_CON_VENTAS`, la puerta del decisor) o un snapshot que ya trae ventas (`tablero.mide_ventas`).
  Sin ninguno: «—» y «sin ventas medibles» (KPI, ranking, tarjeta, panel), nunca 0,0×. Con algo que mide, la cuenta es
  la del Tablero (`tablero.ventas_medidas`): lo vendido sobre TODO el gasto, igual que el Historial. Ojo: `fuente_ventas`
  solo se marca cuando hay compras; la primera versión (2026-10-03) sacaba del denominador lo que aún no vendía e
  inflaba el ROAS (3,0× contra 1,0× del Tablero), corregido el 2026-10-04. (2) **Todo «Activar» dice el diario**: el `confirm()` de «Activar <país>» (panel y gestión)
  lleva el diario del país y la moneda de la cuenta, y el de «Activar todo» la suma de los diarios de los países con
  conjunto. (3) **Países sin repetir**: `exp_probar` y `exp_crear` quitan los repetidos (`dict.fromkeys`, en orden) antes
  de validar y de crear; `paises=CO&paises=CO` creaba un conjunto huérfano en Meta. `metrica_dia` solo se lee con ids de pieza que
  salen de `tablero.cargar_datos(cliente)` (aislamiento: no tiene `cliente`).
- **Historia por pieza**, con reglas fijas y sin Claude: tramos del veredicto en el tiempo, tendencia de los últimos 5 días
  (sube/baja/estable con ±10 %), fatiga (frecuencia ACUMULADA > 2,5 con la métrica cayendo), gancho < 25 %, el rescate
  en curso, las causas del diagnóstico de la doctrina y «le faltan N impresiones / h más» según las reglas efectivas. La
  métrica principal es el ROAS en un experimento OUTCOME_SALES y el CTR del enlace en los demás, siempre contra la misma del
  experimento ENTERO (la línea punteada) aunque el filtro esconda piezas. Los veredictos tienen nombre humano (Ganadora ·
  Perdiendo · Sin diferencia clara · Aprendiendo · Recuperándose).
- **Embudo** (impresiones → clics en el enlace → visitas → carrito → pago → compras): la frase compara cada paso con el
  promedio del PROPIO proyecto (`promedio_embudo`, todos sus experimentos, sin filtros ni periodo) y solo con ≥ 2
  experimentos con impresiones: no se inventan promedios de mercado. Un paso bajo el 80 % de su promedio es «la caída». Los
  pasos que dependen del Pixel (`_PASOS_PIXEL`: visitas a la página —`landing_page_view` es del Pixel—, carrito, pago y
  compras) se apagan con «requiere el Pixel»; nunca son «la caída», y con alguno apagado no se dice que «todos» están en
  el promedio.
- **Frecuencia**: la del periodo o la pieza sale del último `metrica_snapshot` (acumulada, ponderada por impresiones) y no se
  suma entre días: la diaria de `metrica_dia` es del día (regla (c) de «Detalle de Meta»).
- **Consultas**: `exp_resultados` y `exp_nuevo` corren bajo `experimentos.con_lecturas_memorizadas`;
  `experimentos.cargar` obtiene las últimas métricas en una consulta conjunta (`_ultimas_metricas`, PND-134,
  2026-10-07): última por id, no por fecha, con el mismo `_snapshot_a_dict` y sin borrar snapshots.
  `tests/test_lote5_experimentos.py` contrasta cifras, historia, decisiones y otro proyecto vivo;
  `tests/test_rutas_resultados.py` exige consultas constantes con 3 y 15 piezas. Ahí también están los 404 de piezas
  o experimentos de otro proyecto.

**`tablero.py` y OUTCOME_SALES** (el motor del dinero; desde E2 sin pestaña propia: lo pinta el centro; `tab_descargar_csv`
sigue como botón de la cabecera). Cada cifra es un **delta de snapshots acumulados** (`metrica_snapshot` guarda los totales
de por vida de Meta por anuncio, así que un periodo es `valor_en(hasta) − valor_en(desde)`, negativos truncados a 0)
agrupado por moneda de la cuenta; el ingreso solo cuenta snapshots atribuidos por Pixel de Meta, tienda o Triple Whale
(`tablero.FUENTES_VENTAS`). `tablero.cargar_datos` lee UNA vez los experimentos y la serie de cada pieza: `_piezas_con_snapshots`
usa `experimentos.snapshots_de(ids, desde)`, DOS consultas para todas las piezas (la ventana y la última fila anterior, la
base del delta), no dos por pieza. Siguen vivos: `resumen_total` (el total desde el inicio: el último snapshot de cada
pieza, ya cargado; `resumen_total_triple_whale`; la generación sale de `gastos.resumen_total`), **`mes_a_mes`** (una fila por
mes, del más nuevo al más viejo, desde el primer mes con pauta o generación, una fila por moneda y la generación solo en la
primera; los cierres de mes salen de UNA consulta, `_cierres_de_mes`, ROW_NUMBER por pieza y mes, y un snapshot tomado a las
00:00 del día 1 cierra el mes anterior, así la fila del mes en curso es igual a `resumen_mes` y los meses suman el total; la
generación por mes sale de `gastos.por_mes`), `resumen_mes` (el mes en curso: alimenta el chip del menú, la fila «Tu tienda
según Triple Whale» y el CSV; `dashboard._calcular_tablero` ya no calcula la serie de 30 días, el top ni los gráficos, que
nadie pinta desde E2), `tablero.alertas` (la lee `alertas.py`: skill `alertas`; cambiar un `tipo` o las cifras del texto
de una alerta cambia su huella de descarte; el centro muestra UNA línea «N alertas necesitan tu atención → Ver Alertas»,
`.cr-alertas-linea` en `_exp_resultados.html`) y la atribución. `dashboard._contexto_tablero` lo cachea 60 s por proyecto e
idioma, con la clave del último snapshot, el conteo de propuestas y los cobros de generación del proyecto, y degrada por
partes sin filtrar el texto de una excepción; el total vive en «Totales desde el inicio», plegado al final del centro
(`_exp_historial.html`). **Desde 2026-10-08 todo es desde el inicio** (Daniel: el mes y los periodos cortos confundían a
sus clientes): `resultados.PERIODO_DEFECTO = 0` («Desde el inicio», primer chip; 7/14/30/90 días siguen como filtro), la
tabla «Mes a mes» ya no se pinta (`tablero.mes_a_mes` sigue calculándose y probándose), y «Descargar CSV» (ruta
`tab_descargar_csv`, `/tablero/mes.csv`) sale de `tablero.csv_total`: lo acumulado de cada pieza. `csv_mes`/`csv_total`
escapan las celdas que empiezan con fórmula. Con atribución sugerida `pixel`,
`experimentos.objetivo_sugerido` es `OUTCOME_SALES`; `lanzador.lanzar` vuelve a comprobar el Pixel antes de tocar Meta y manda
`promoted_object={pixel_id, PURCHASE}` en cada conjunto (`meta_ads/adset.py` rechaza SALES sin él). El objetivo queda fijo al
crear: Meta no deja cambiarlo.

**Instalaciones de la app** (2026-10-07; spec `docs/superpowers/specs/2026-10-07-experimentos-instalaciones-app-design.md`).
Un objetivo más del experimento: anuncia una app (App Store iOS y/o Google Play Android) en vez de una web. El
experimento lleva `extra["app"]` (URLs de tienda y App ID) y **cada pieza tiene una fila por plataforma**
(`pieza.extra["plataforma"]`; `experimentos.plataformas_de(extra)`), así que el lanzador crea un conjunto por país y
plataforma (`lanzador._clave_adset`, el presupuesto del país se reparte con `app_tiendas.parte_presupuesto`).
Activar, pausar, presupuesto y escalar recorren los conjuntos del país con `lanzador._adsets_de_pais`, nunca un solo
`meta_adset_id`. El App ID de la app anunciada (distinta de la de inicio de sesión) vive en
`clientes/<cliente>/meta_app_anunciada.json` (`meta_conexion.cargar/guardar_app_anunciada`; se valida con
`meta_conexion.validar_app_anunciada`: solo dígitos ASCII, y se guarda tras crear con éxito). Se optimiza por
`LINK_CLICKS` a la tienda: las instalaciones reales solo se miden cuando la app tenga SDK de Meta o un servicio de
atribución; la app debe estar en modo Live. Los campos de tienda y App ID viven en «Avanzado» de «Nuevo experimento»
(`_exp_probar.html`, `data-solo-app`/`data-solo-no-app`; `app_id_guardado` lo trae `_contexto_experimentos`); `exp_crear` rechaza
el objetivo de apps (se crea en «Nuevo experimento»). Derivar y rescatar quedan omitidos por
`acciones.pedir` para estos experimentos, y no se agregan piezas sueltas ni antes ni después de lanzar
(`experimentos.agregar_pieza` lanza `ValueError` y `_agregar_pieza_validada` devuelve el mismo aviso: una fila sin
plataforma bloqueaba el lanzamiento; las filas por tienda solo las arma `crear_con_piezas`). Meta rechaza una URL de
tienda con otro objetivo: `meta_errores.explicar` lo dice en palabras. `meta_ads/` es un submódulo.
Arreglos de la revisión final (2026-10-08, plata y seguridad): `cambiar_presupuesto_pais` cambia los conjuntos uno a
uno y, si Meta falla a medias, devuelve los ya cambiados a `centavos(anterior) // n` y no toca lo guardado del país
(antes el panel decía un presupuesto y Meta gastaba otro); `exp_presupuesto` valida el mínimo de Meta contra cada
parte (`centavos(total) // n`), como `exp_probar`; el lanzador usa el App ID de `extra["app"]["app_id"]` (el aprobado
al crear) y solo de respaldo el del proyecto; un perdedor en las dos tiendas se diagnostica con Claude UNA vez
(`experimentos.diagnostico_hermano` + `tareas.experimentos._diagnostico_de_hermana` copian el de la otra fila, con
evento y sin gasto); `app_tiendas.plataforma_de_url` rechaza `\`, usuario/clave, puerto, espacios y todo host que
no sea exactamente el de la tienda (`https://evil.com\@apps.apple.com` daba `ios`).
Tras fusionar el centro de resultados (2026-10-08): toda condición «el país tiene conjunto en Meta» mira
`meta_adset_id or meta_adsets` (`_exp_gestionar.html`, `_exp_pieza.html` con `resultados.py` pasando `meta_adsets`,
`lanzador.cambiar_estado` con `_adsets_de_pais`) y la suma diaria de «Activar todo» cuenta los países de apps; sin
eso «Activar país» de una app decía «Ese país no tiene conjunto en Meta» y el confirm de «Activar todo» mostraba 0.
Ola 2 de la revisión final (2026-10-08): `cambiar_presupuesto_pais` con UN solo conjunto relanza la excepción
original de Meta (el aviso o la propuesta pendiente conserva el motivo); con varios, el «se dejó como estaba» termina
con `traducir_error_meta(cola.sin_token(…))` y el evento guarda el error sin token. Una pieza que gana en las dos
tiendas escala su país UNA vez (`tareas.experimentos._hermana_ya_gano`: si la fila hermana, misma `pieza_id` y país,
ya es `ganador`, no se pide otro `escalar` y queda un evento) y el decisor juzga con el presupuesto del conjunto
(`_presupuesto_para_decidir` = `app_tiendas.parte_presupuesto`), no con el del país. Cada fila muestra su tienda
(«iOS»/«Android», `.tag-estado`) en la gestión, el ranking y el panel (`resultados.piezas` trae `plataforma`), y el
anuncio y el creative en Meta llevan el sufijo « · iOS» / « · Android». Limitación conocida: el ranking top-tercio del
decisor mezcla las filas de iOS y Android de un país.

**Detalle de Meta** (`meta_detalle.py`, spec `2026-10-02-experimentos-centro-de-resultados` §3, E1 2026-10-02): único escritor de
`metrica_dia` (una fila por anuncio y día: tráfico, embudo `visitas_pagina`/`carrito`/`pago_iniciado`/`compras_meta`,
retención `vistas_3s`/`p25…p100`/`thruplay`/`tiempo_medio_s`) y `metrica_desglose` (desde la creación del experimento por
`ubicacion`/`edad_genero`/`dispositivo`/`region`), y de `experimento_pieza.extra["rankings_meta"]`. Pide a nivel
campaña con `level=ad` (1 diario + 4 desgloses + 1 rankings por experimento) con `meta_ads.auth.llamar`, sin tocar
el submódulo; los desgloses y los rankings van con `time_range` (creación → hoy, nunca `date_preset=maximum`) y los
desgloses piden solo lo que `fila_desglose` guarda (`CAMPOS_DESGLOSE`: sin `reach`/`frequency`/`cpm`/`clicks`).
Corre al final de `exp_refrescar` en su propio `try` (el decisor no depende de esto; su log lleva el error sin token) y como
tarea `exp_detalle` (`max_intentos=2`, no cobra; `meta_detalle.encolar_todos()` hace la carga inicial). El rango del
día a día se cura solo: desde el último día guardado menos 2 (Meta corrige días recientes) o desde la creación del
experimento. Un desglose que Meta rechaza no tumba los otros. Cortan la pasada entera dos cosas: un **código de
límite** (la familia de `meta_errores._LIMITE`: 4/17/32/613 y 80000…80014 por caso de uso de negocio;
`meta_errores.es_limite`, a la que delega `meta_detalle.es_limite`) y un **fallo de red o HTTP 5xx** (texto
«falló en red» / «respondió 5…» de `meta_ads.auth.llamar`; marca `cortado`, no `limite`). `exp_detalle` no dice «al
día» con lo que falta: con límite devuelve `Continuar("exp_detalle", {…, "vuelta": n+1}, ejecutar_desde=ahora+30 min)`
hasta 3 vueltas y a la tercera termina diciendo que quedó incompleto; con errores nombra las partes que fallaron. El
estado queda en `experimento.extra["detalle_meta"]` (`actualizado_en`, `desde`, `errores` sin token, `limite`,
`cortado`).
Reglas para quien lea o muestre esos datos: (a) `metrica_dia` y `metrica_desglose` **no tienen columna `cliente`**:
todo lector las une con `experimento_pieza` y filtra por `cliente` y `experimento_id`, nunca con un id que venga del
navegador sin ese join (si no, un proyecto lee las cifras de otro). (b) `detalle_meta.errores` guarda texto crudo de
Meta (ya sin token): se muestra con `meta_errores.explicar` y con el autoescape de Jinja, nunca con `|safe`. (c) El
alcance y la frecuencia **diarios no se suman** entre días: la frecuencia del periodo o de la pieza sale del último
`metrica_snapshot` (acumulada de por vida) y se rotula «acumulada»; la regla de fatiga usa esa, no la diaria.

PND-003 (revisión 2026-10-02): el precio de rescatar/derivar pasa musica_estilo de la sesión a gastos.estimar para cada regeneración; no cambia decisiones ni autorizaciones de pauta.

PND-039/044/113 (2026-10-03): regenerar conserva las voces originales por destino en el item; un destino nuevo hereda la última voz original conocida. El payload explícito mantiene esa elección al producir. La cuadrícula conserva desmarcadas por combinación. Antes de la primera activación (experimento, país o pieza), lanzador reserva fin_primera_activacion bajo el escritor de extra y envía end_time a todos los conjuntos; solo después activa. Reanudar no extiende el plazo ni cambia presupuestos. Una reserva tras un fallo conserva la misma fecha en el próximo intento; los experimentos ya activados mantienen su fecha previa. PND-043 sigue esperando la decisión de reserva de arranques entre experimentos.

PND-138/139/140 (revisión de Codex, 2026-10-05): aviso_moneda invalida ingresos/ROAS solo si hubo gasto, compras, impresiones o ingresos en el período; compras/CPA se conservan por moneda ajena, también al gestionar. Daniel decide si el agrupado futuro excluye los no comparables con nota o sigue oculto (PND-138); no convertir monedas. Una base sin ventas solo vale cero si nunca hubo compras ni fuente medible antes de desde. También se revisa el cierre: si no mide ventas y tiene cero compras, con serie.primera_venta <= hasta, el período no es comparable (compras/ingresos/ROAS/CPA None y pantalla —), nunca cero. Si serie.primera_venta es None o posterior a hasta, no se recorre la historia para buscar fuentes: no hubo ventas hasta el cierre y los resultados no cambian (segunda revisión del lote 4, 2026-10-05, pruebas test_tablero_cierre_ciego y test_tablero_rendimiento_ventas); el historial anterior se consulta en una tercera consulta conjunta para todas las piezas (conteo constante, probado con 3 y 13 piezas) y se conserva en los cierres mensuales. Entre fuentes distintas compras/ingresos/ROAS/CPA son None, CSV vacío, y la pantalla explica «Las ventas cambiaron de fuente en este período». La primera venta real se conserva. El día desconocido de TW→respaldo ciego→TW no se convierte en cero; reconstruir/fijar fuente y conciliar intervalos sigue como decisión PND-142. Historial sin gasto muestra —; con Pixel y gasto sin compras muestra 0,0×. La nota de gasto sin ventas medibles no se repite si el KPI ya dice sin ventas medibles. No cambia el decisor ni la pauta.

**Capacidad de atribución (2026-10-07, PND-078):** `atribucion_sugerida` conserva la prioridad del Pixel y pregunta
`conectores.por_tipo(tipo).soporta_utm` a cada tienda conectada. Un tipo desconocido se omite. No cambia capacidades
ni atribuciones ya guardadas; `tests/test_lote5_higiene.py` usa conectores dobles con y sin UTM.

PND-136 (2026-10-07, lote 5 B): exp_pieza memoriza lecturas solo durante la petición. En resultados, gestión_id limita trabajos, propuestas y reglas al experimento seleccionado; sin selección mantiene las propuestas de todos (son visibles en Necesita tu decisión). Las marcas del panel usan el mismo truncado y MAX_MARCAS, sin cortar la bitácora. Día a día abre con ROAS para ventas y CTR para tráfico; en el centro con mezcla de objetivos conserva CTR. Gráfica role=group admite marcas enfocables; aria-live del contenedor se hereda, sin duplicarlo. No se cambia el decisor, reparto ni destino de publicación.

Regresión aria-live del lote 5 corregida (2026-10-08, pedido de Daniel): el aviso #exp-minimo pertenece al resumen vivo #exp-resumen, sin aria-live propio; la copia #exp-resumen-final sigue sin región viva. La prueba de PND-136 comprueba herencia y conteo único; la prueba antigua de presupuesto permanece intacta.

Noruega y Suecia (2026-10-08, spec `docs/superpowers/specs/2026-10-08-noruega-y-suecia-design.md` §3 y §5; motivo: el público de happyflops es Noruega y Suecia): un conjunto por país NO o SE sale con su moneda de la lista de países (`final_edition.tipos.PAISES`: NOK y SEK, símbolo «kr», que va detrás del número). Los mínimos de Meta se avisan con `presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO` (NOK y SEK: 15 al día) y `lanzador._MIN_POR_MONEDA` (1 300 para el tope de gasto; 1 000 NOK ≈ US$94 quedaba bajo el mínimo de Meta, 2026-10-08); NOK y SEK llevan decimales para Meta (no están en `SIN_DECIMALES`). El presupuesto se compara contra la moneda de FACTURACIÓN de la cuenta, no la del país del conjunto, como siempre. `proyectos.paises_calendario()` ahora sale de `PAISES` (importa `final_edition.tipos` dentro de la función: `import proyectos` no debe cargar `final_edition`): un país nuevo en `PAISES` entra solo al selector de país del proyecto; si le falta calendario de Sprints usa el de Colombia. Las tiendas de Triple Whale por país NO y SE ya se conectaban; ahora una pieza de esos países sí se puede lanzar y producir (cierra PND-147).
