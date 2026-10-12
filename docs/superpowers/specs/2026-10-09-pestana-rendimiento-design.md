# Una sola pestaña «Rendimiento» en lugar de «Triple Whale» y «Meta»

Fecha: 2026-10-09. Pedido de Daniel: «siento que lo que tenemos en Meta es lo mismo que tenemos en Triple Whale,
entonces esto confunde a los clientes».

## 1. El problema, medido en el código

Las dos pestañas muestran casi lo mismo y, para el mismo anuncio, **números distintos**:

| | Meta (`meta_rendimiento/`) | Triple Whale (`triple_whale/`) |
|---|---|---|
| Selector | Todas / cuenta por país | Todas / tienda por país |
| Totales | Gasto, ROAS, compras, costo por compra | Gasto, ROAS (Pixel), pedidos, costo por venta |
| Día a día | `meta_rendimiento/grafico.py` | `triple_whale/resultados.py` + `static/tw_resultados.js` |
| Anuncios con veredicto, gancho, retención | sí, con `triple_whale/evaluacion.evaluar` | sí, el mismo cálculo |
| Periodo por defecto | 30 días (`meta_rendimiento/panel.py:29`) | «Desde el inicio» (`triple_whale/panel.py:37`) |

Solo Meta tiene campañas, conjuntos, presupuesto, «aprendizaje limitado» y alcance. Solo Triple Whale tiene las
ventas reales de la tienda, otros canales, productos, «Cómo mejorarlo» con IA, «Llevar a Crear» y Pausar/Activar.

Meta cuenta las ventas con su Pixel y Triple Whale con el suyo. En happyflops la cuenta de Noruega dice ROAS 2,2× en
Meta (30 días al 2026-10-08) y «Tus anuncios» de Triple Whale dice 3,7× (desde el inicio): periodos distintos, pero la
brecha es de ese orden. Además, lo que Triple Whale atribuye (Triple Attribution, ventana
`lifetime`, el defecto de `triple_whale/__init__.py:48`) **suma unas 2,5 veces las ventas reales de la tienda** (17 sep
2026: 48 697 atribuidos contra 19 273 de la tienda) y mete fuentes sin gasto, como orgánico, Klaviyo o Direct
(PND-157).

## 2. Decisiones de Daniel (2026-10-09)

1. **Una sola pestaña.** Selector Todas/país; campañas y conjuntos (de Meta) y productos (de Triple Whale) como
   secciones cuando hay datos.
2. **Manda Triple Whale; Meta en el detalle.** Tarjetas, totales y veredictos usan el número de Triple Whale cuando
   está conectado. Al abrir un anuncio, una línea chica dice «Meta reporta 2,2×» y por qué difiere.
3. **Lo inflado (PND-157) se arregla en este cambio.** Arriba, el retorno real (ventas de la tienda / gasto). Por
   anuncio, solo ventas atribuidas a canales pagados. La ventana se elige después de ver una medición con números reales
   de happyflops (E0).
4. **Camino A.** Una capa nueva que decide la fuente por país y entrega a la pantalla siempre la misma forma; las copias
   de datos de los dos paquetes no cambian.

## 3. Reglas (rulings) de este spec

Las marcadas con ★ salieron al leer el código después de la conversación: Daniel las revisa con el spec.

- **R1. Nombre y lugar.** La pestaña se llama «Rendimiento» (clave `rendimiento`, ancla `#rendimiento`) y ocupa en el
  menú el lugar de «Triple Whale»; «Meta» sale del menú. Las claves viejas `triplewhale` y `meta` (hash, `localStorage`,
  `redirect(_anchor=…)`) abren la nueva, como ya pasa con `idea` en `cliente.html`.
- **R2. Entradas del selector.** Una entrada por país del proyecto: su tienda de Triple Whale (si hay) y sus cuentas de
  Meta con ese país (si hay). Una tienda o una cuenta sin país es su propia entrada, con su nombre. Más «Todas».
- **R3. Fuente por entrada.** Si la entrada tiene tienda de Triple Whale, la fuente es Triple Whale; si no, el Pixel de
  Meta. Una entrada muestra el mismo número sola y dentro de «Todas».
- **R4 ★. Tienda sin país.** Si el proyecto tiene UNA tienda de Triple Whale sin país, esa tienda es la fuente de todo el
  proyecto y el selector solo tiene «Todas» (Triple Whale no separa esas ventas por país). Las cuentas de Meta aportan
  solo estructura (campañas y conjuntos) y la línea «Meta reporta». Es la misma regla que ya usa la atribución de experimentos
  (`lanzador._tienda_tw_de`).
- **R5 ★. Sin contar dos veces el gasto.** Una cuenta de Meta cuyos anuncios aparecen en la copia de una tienda de
  Triple Whale (`tw_anuncio_dia.cuenta_id`, canal `facebook-ads`) está **dentro** de esa tienda: en «Todas» su gasto y
  sus ventas no se suman aparte. Se decide con los datos, no con el país, porque una cuenta «World Wide» puede alimentar
  la tienda de Noruega. Si una entrada sin tienda queda cubierta así, «Todas» no es la suma de las entradas, y el
  cuadro «Por país» lo dice en una nota.
- **R6. Moneda.** Una entrada se ve en su moneda: la del proyecto en Triple Whale, la de la cuenta en Meta. «Todas» va
  en USD con `meta_rendimiento.tasas` (BCE, día por día); sin tasa dice «USD no disponible», nunca una inventada. Si
  todas las entradas comparten moneda, va en esa moneda.
- **R7 ★. «Desde el inicio».** Es el periodo por defecto (regla del 2026-10-08: métricas en total). En una entrada va
  desde su primer día copiado. En «Todas» va desde el día en que **todas** las fuentes del alcance ya tienen datos, y la
  pantalla dice desde qué fecha («Desde el 10 jul 2026, cuando empiezan los datos de todas tus fuentes»): sumar 3 meses
  de una tienda con 13 de una cuenta daría un total que no es de nadie. Los anuncios de Meta cubren los últimos 90 días
  (`meta_anuncio_dia` se purga a los 95) y la sección lo dice.
- **R8. Ventas arriba (retorno real).** Con fuente Triple Whale, «Ventas» es lo que entró a la tienda
  (`tw_tienda_dia.ingresos`) y «Retorno» es ventas de la tienda / gasto, como ya hace la tarjeta «Retorno (MER)» de
  «Resultados de tu tienda». Con fuente Meta, «Ventas» es el valor de compras del Pixel de Meta, rotulado «según Meta».
  En «Todas» mezclada, una línea dice de dónde sale cada parte («Ventas: tienda en Noruega; Pixel de Meta en Suecia,
  Países Bajos…»).
- **R9. Ventas por anuncio (solo pagado).** Con fuente Triple Whale, un anuncio cuenta solo si su canal tuvo gasto en la
  copia del alcance (`canal` con `SUM(gasto) > 0` en `tw_anuncio_dia`). Así quedan fuera orgánico, Klaviyo, Direct o
  cualquier fuente sin gasto, también las que Triple Whale agregue mañana. El tile «Ingresos atribuidos» suma solo esos.
- **R10. Ventana de atribución.** Se elige en E0 con los números reales. Pasa a ser el defecto de las conexiones nuevas
  (`triple_whale.VENTANA_DEFECTO`) y, con el sí de Daniel, el ajuste de happyflops. Cambiarlo borra y vuelve a copiar
  las copias de todas sus tiendas (`triple_whale_tiendas.cambiar_ajustes`); `tw_creativo`, las evaluaciones y los
  análisis pagados se quedan.
- **R11 ★ (plata, se pregunta en E0).** Experimentos usa esas mismas ventas de Triple Whale para el decisor
  (`lanzador._mezclar_ventas_triple_whale`), y en modo semi o auto pausa anuncios solo. Cambiar la ventana del proyecto
  cambia lo que ve el decisor. No se aplica sin que Daniel diga, con la medición delante, si Experimentos usa la misma
  ventana (recomendado: mismo número en toda la app) o se queda con la anterior.
- **R12. «Meta reporta».** En el detalle de un anuncio con fuente Triple Whale y canal `facebook-ads`, una línea dice
  «Meta reporta 2,2× · cada uno cuenta las ventas con su propio Pixel». Sale de `tw_anuncio_dia.valor_canal / gasto`
  (lo que Meta le informa a Triple Whale), sin pedir nada nuevo. Sin dato, la línea no aparece.
- **R13 ★. Lo pagado no se toca.** «Cómo mejorarlo», «Analizar los N», «Evaluar con IA», «Guardar en Referentes»,
  «Llevar a Crear» y Pausar/Activar siguen siendo las rutas de `triple_whale/rutas.py`, con su alcance (`tienda_id`,
  `canal`, `dias`) y todas sus garantías (precio a la vista, `max_intentos=1`, no pagar dos veces lo mismo, Cobros). La
  pestaña nueva solo les pasa el alcance de Triple Whale que corresponde a la entrada: una tienda, o `None` = todas las
  tiendas.
- **R14. Anuncios de fuente Meta en E1.** Tarjeta con miniatura, cifras y veredicto (el de hoy:
  `evaluacion.evaluar` contra su cuenta), sin botón de IA: «Cómo mejorarlo» para ellos llega en E2. No se dibuja un botón
  apagado: la tarjeta simplemente no lo tiene.
- **R15. La conexión.** El formulario de Triple Whale (`_triple_whale_conectar.html`, hoy dentro de su pestaña) y
  «Elegir cuentas» de Meta (solo admin, R20 de Meta rendimiento) viven en «Ajustes» de la pestaña nueva. La conexión
  con Meta sigue en Configuración › Conexiones; su enlace «#meta» pasa a «#rendimiento».
- **R16. Fuera de este cambio.** Experimentos y su centro de resultados (solo cambia su enlace `data-ir-tab`), E3 de Meta
  (aplicar cambios, PND-193), lanzar en varias cuentas (PND-148), modo agencia de la lectura de Meta (PND-197).

## 4. Arquitectura

Paquete nuevo `pestana_rendimiento/`. El nombre `rendimiento/` ya es de las pruebas de carga (skill `escala-y-salud`).

| Módulo | Hace | Depende de |
|---|---|---|
| `entradas.py` (puro) | R2–R5: arma las entradas del selector y la fuente de cada una a partir de las tiendas, las cuentas y las cuentas cubiertas | nada |
| `fuente_tw.py` | lee una entrada de Triple Whale con la forma común (totales, serie diaria, anuncios evaluados, campañas por `campana_id`) | `triple_whale.datos`, `triple_whale.evaluacion` |
| `fuente_meta.py` | lo mismo para una entrada de Meta | `meta_rendimiento.datos`, `triple_whale.evaluacion` |
| `panel.py` | `contexto(cliente, dias, entrada)`: junta las entradas del alcance, suma «Todas» (R5–R8), ordena anuncios por gasto en USD y prepara cada sección | los tres de arriba, `meta_rendimiento.tasas` |
| `rutas.py` | blueprint `/cliente/<c>/rendimiento`: `panel`, `galeria` (páginas de «Ver más»), `dia` (detalle de un día) | `panel` |

`triple_whale/` y `meta_rendimiento/` siguen siendo los únicos que copian y escriben sus tablas. No se agrega ninguna
tabla ni migración. Lo que cambia dentro de ellos:

- `triple_whale.datos`: una lectura `cuentas_meta_de_tiendas(cliente)` → `{tienda_id: {act…}}` (R5) y el filtro de
  canales con gasto (R9) en `totales_por_anuncio` y `resumen_cuenta`.
- `triple_whale.resultados.armar` acepta `fuente="meta"` (serie de `meta_cuenta_dia`; textos «según Meta»). Es puro y
  `tw_resultados.js` dibuja el mismo JSON.
- Se jubilan `triple_whale.rutas.ver_panel`, `meta_rendimiento.rutas.ver_panel`/`ver_anuncios`, `_tab_triple_whale.html`,
  `_tab_meta.html`, `_tw_panel.html` y `_meta_panel.html`. Sus partes reusables (resultados, galería, tarjeta, tabla de
  campañas y conjuntos, filas de «Ver más») pasan a parciales o macros que incluye `_rend_panel.html`.

### Forma común (lo que `fuente_*` entregan)

- `totales`: `gasto`, `ventas`, `pedidos`, `retorno`, `costo_venta`, `moneda`, `origen_ventas` (`tienda` | `pixel_tw` |
  `pixel_meta`).
- `serie`: filas `{fecha, gasto, ventas, pedidos}` en la moneda de la entrada.
- `anuncios`: lo que hoy devuelve `evaluacion.evaluar` (`veredicto`, `m`, anillos, problemas…), más `fuente`, `entrada`,
  `gasto_usd` (para ordenar «Todas») y `meta_reporta` (R12).
- `campanas` y `conjuntos`: los de `meta_rendimiento.datos` (presupuesto, estado, aprendizaje, alcance), con ventas y
  retorno según la fuente de su entrada.

## 5. Pantalla

`_tab_rendimiento.html` pinta solo el armazón; el panel llega por fetch al abrir la pestaña (como hoy las dos). En orden:

1. **Barra.** Selector de entradas (bandera, nombre y una etiqueta chica «Triple Whale» o «Meta»), periodo
   (Desde el inicio · 7 · 14 · 30 · 90), «Actualizar ahora» (encola las copias de Triple Whale y de Meta del alcance con
   sus `job_id` de siempre y una sola barra `data-poll-job`) y «Ajustes» (R15).
2. **01 Resultados.** «Resultados de tu tienda» de hoy, con cualquier fuente: tarjetas (gasto, ventas, retorno, pedidos,
   costo por venta), gráfica interactiva, detalle del día, lectura con reglas. La línea de origen de R8 va bajo las
   tarjetas.
3. **02 Por país** (solo «Todas» con dos entradas o más): gasto, ventas, retorno y fuente por entrada; nota de R5 si
   aplica.
4. **03 Lo que necesita tu atención.** Las alertas de hoy de Triple Whale (`evaluacion.alertas`). Las de Meta
   (aprendizaje limitado, fatiga, rechazados) llegan en E2.
5. **04 Tus anuncios.** Una galería con los de las dos fuentes, por gasto en USD, 12 por página, los filtros de hoy.
   Tarjetas de Triple Whale como hoy, más «Meta reporta» en el detalle; tarjetas de Meta según R14.
6. **05 Lo que hace ganar en tu cuenta** (Evaluar con IA): sobre la parte Triple Whale del alcance; el texto lo dice si
   el alcance mezcla fuentes. No aparece si el alcance no tiene Triple Whale.
7. **06 Campañas y conjuntos.** La tabla de hoy de la pestaña Meta para las cuentas del alcance, cubiertas incluidas
   (R5: la estructura sirve siempre). «Ver más» por fetch.
8. **07 Dónde se va el gasto** y **08 Lo que más se vende** (este último solo con Triple Whale), como hoy.
9. **Ver como tabla**: todos los anuncios, cerrada.

Sin Triple Whale ni Meta: «Conecta Meta o Triple Whale para ver tu rendimiento», con los dos enlaces. Con solo uno, la
pestaña funciona entera con esa fuente. Base visual común, celular sin scroll lateral (las tablas se desplazan dentro),
miniaturas `loading="lazy"`, número fijo de consultas por página (una por bloque, nunca una por tarjeta).

## 6. Entregas

- **E0. Medición (solo lectura, sin costo).** Con la llave de happyflops-norge desde el VPS y una copia de la base:
  para los mismos días, ventas de la tienda vs. lo atribuido a canales pagados con Triple Attribution en 1, 7, 14 y 28
  días y `lifetime`, vs. el Pixel de Meta de la cuenta de Noruega; y qué cuentas de Meta aparecen en la copia de cada
  tienda (R5). Resultado en `docs/superpowers/evals/2026-10-09-atribucion-happyflops.md`. Daniel elige la ventana y
  responde R11.
- **E1. La pestaña única.** Todo lo de §3 a §5; los anuncios de fuente Meta van sin IA (R14). PND-157 y PND-196 (orden
  por USD) se cierran.
- **E2. IA y recomendaciones para Meta.** «Cómo mejorarlo» y «Evaluar con IA» para anuncios de fuente Meta (medios desde
  la Graph API con la lista de hosts permitidos de `meta_rendimiento.datos`, miniatura copiada a R2 como en Triple Whale,
  PND-194), y las reglas de PND-192 dentro de «Lo que necesita tu atención». Tiene su propio plan y su medición con
  `eval-claude`.

## 7. Pruebas

- `entradas.py`: cada regla R2–R5 con su caso (tienda por país, tienda sin país, cuenta World Wide cubierta y no
  cubierta, proyecto solo Meta, solo Triple Whale, nada).
- «Todas» sin doble gasto (R5), en USD con un día sin tasa (R6), desde la fecha común (R7), con la línea de origen (R8).
- R9: un anuncio de un canal sin gasto (`klaviyo`) no entra en anuncios ni en «Ingresos atribuidos».
- R12: «Meta reporta» con `valor_canal` y sin él.
- R13: las tarjetas de Triple Whale de la galería nueva postean a las mismas rutas con el mismo alcance; las pruebas de
  `test_tw_tarjetas_*` siguen en verde sin tocarlas.
- Las claves viejas `#triplewhale` y `#meta` abren `rendimiento`; ningún `_anchor` ni `data-ir-tab` apunta a las viejas.
- Consultas fijas por página con 12 y con 24 tarjetas.
- Mutaciones del `revisor`: romper R5, R7, R9 y el alias de las claves, y ver que una prueba falla.
- Captura real antes de dar E1 por buena: escritorio y celular, «Todas» y una entrada de cada fuente, con datos
  parecidos a los de happyflops (memoria `verificar-ui-sin-contrasena`).

## 8. Pendientes que este spec toca

PND-157 (se cierra en E1), PND-196 (se cierra en E1), PND-192 (pasa a E2 de este spec), PND-194 (E2), PND-158 (sin
cambio), PND-149 (8) (el supuesto del gasto compartido lo comprueba E0).

## 9. Enmiendas al planear (2026-10-09, con «ejecuta todo» de Daniel: «vamos con las 3 entregas, no te detengas»)

Salieron al leer el código de las dos pestañas; se anotan como decisiones y se le cuentan a Daniel al final.

- **A1. La galería se une en E2, no en E1.** La galería de Triple Whale carga «Cómo mejorarlo», el lote «Analizar los
  N», sus precios y la regla de no cobrar dos veces lo mismo, todo atado a su alcance (`tienda_id`, `canal`, `dias`).
  Mezclarla con anuncios de Meta antes de que esos anuncios tengan su propio análisis arriesga lo que cobra. En E1,
  «04 Tus anuncios» muestra la galería de Triple Whale tal cual (la parte Triple Whale del alcance) y, debajo, las
  tarjetas de los anuncios cuya fuente es Meta, con un subtítulo solo cuando hay de los dos. Ningún anuncio aparece dos
  veces (R5). E2 junta todo en una sola galería con un solo lote, por gasto en USD, y ahí se cierra PND-196.
- **A2. R7 vale para «01 Resultados» y «02 Por país».** Los bloques de cada fuente (anuncios, campañas) usan el
  «Desde el inicio» de su propia copia.
- **A3. Detalle del día y filtro «Canal».** En E1 el detalle de un día y el selector «Canal» existen cuando el alcance
  es solo Triple Whale (es la pantalla de hoy). Con Meta o mezcla, la gráfica no abre días; el detalle del día de Meta
  llega en E2.
- **A4. R10 y R11 en el código.** El código no cambia `triple_whale.VENTANA_DEFECTO` ni el ajuste de happyflops: los
  dos cambian lo que decide el decisor de Experimentos. E0 deja la recomendación con números y Daniel la aplica desde
  «Ajustes» (`cfg_triple_whale_ajustes`), que ya existe. Lo inflado se arregla en E1 con R8 y R9, que no tocan al
  decisor (`lanzador._mezclar_ventas_triple_whale` lee `totales_anuncio` de anuncios de Meta, que siempre tienen gasto).
- **A5. «Actualizar ahora».** Una sola ruta (`rendimiento.actualizar`) encola las copias de Triple Whale y de Meta del
  alcance, con las reglas de cada una (la pausa compartida de Meta y la espera de 30 minutos de quien no es admin). Las
  dos rutas viejas de «Sincronizar» se retiran con sus pantallas.
- **A6. Alcance de E2.** «Cómo mejorarlo» y «Evaluar con IA» para anuncios de fuente Meta usando la misma tabla
  (`tw_analisis`/`tw_evaluacion`) y la misma tarea con una marca de fuente, para que la galería quede una sola; las
  reglas de PND-192 sobre la copia que ya existe; el detalle del día de Meta. La copia diaria de desgloses
  (`meta_desglose`) y los avisos por correo de Meta quedan como pendiente nuevo.
