# Triple Whale: «Resultados de tu tienda» (spec 2026-10-08)

## 1. Por qué

Daniel mandó una captura de la gráfica «Día a día» del panel de Triple Whale (barras naranjas de gasto, línea verde
de ingresos, leyenda con una muestra azul que no coincide) y dijo: «me parece horrible; cuando uno se para en un día
no pasa nada; quiero que sea más interactiva, más diciente, que muestre la importancia de usar esta app». Después:
«no importa que no haya sido lanzado [desde Creatv], necesitamos darle resultados a las personas» y, con la maqueta
v1 aprobada, «vamos con más detalle, recuerda que vamos a ser la mejor plataforma de ADs del mundo». Aprobó la
maqueta v2 (la de este spec), **todo en una entrega** y **salir a producción** al terminar sin más preguntas.

Lo que estaba mal en la gráfica de hoy (`_tw_panel.html` «Día a día», armada por `dashboard._grafico_tablero`):

- Colores que no cuadran: `.tb-barra-tw`/`.tb-linea-tw` pintan con `--serie-3`, la leyenda con `--tb-ingresos`.
- Al pasar el mouse solo hay un `<title>` nativo que tarda o no sale; no hay detalle de nada.
- El último día (hoy, copiado a las 06:14) se dibuja como una caída del 60 %: es un día a medias.
- Dice cuánto se gastó y cuánto se vendió, pero no qué pasó, por qué ni qué hacer.

Datos reales de happyflops que el diseño respeta (consultas de solo lectura en producción, 2026-10-08):

- `tw_tienda_dia` trae gasto, ingresos y pedidos; `nc_pedidos`, `nc_ingresos`, `reembolsos`, `cogs` y
  `utilidad_neta` llegan en 0 → nada de tarjetas de utilidad ni de clientes nuevos mientras no haya datos.
- `tw_producto_dia` está vacía (PND-150) → nada de productos por día en esta entrega.
- El modelo es Triple Attribution con ventana «lifetime»: lo atribuido por anuncio **suma más** que las ventas de la
  tienda (17 sep: 48 697 atribuidos contra 19 273 de la tienda). Lo atribuido se usa para **comparar** anuncios y
  canales entre sí y siempre dice «según el Pixel»; los totales de la tienda salen de `tw_tienda_dia`.
- Ningún anuncio de happyflops lo lanzó Creatv; los 4 de Creatv son de colorado_forja. La sección no depende de eso.
- Los anuncios nuevos (menos de 14 días) rinden menos al empezar (1,83× contra 3,48× de los establecidos, 9 sep–7
  oct): se dice tal cual. El mensaje es «sin pruebas nuevas no aparece el próximo ganador», no «lo nuevo vende más».

Decisión del mismo día que manda (5fce2658, «Métricas en su totalidad»): el periodo por defecto del panel es
**«Desde el inicio»** (`PERIODO_DEFECTO = 0`, todo lo copiado) y en ese periodo **no hay comparación**. Este spec
la respeta: la comparación con el periodo anterior y las variaciones ▲▼ solo existen con 7/14/30/90 días.

## 2. Qué ve la persona

«Tu tienda» (tiles) y «Día a día» (gráfica) se funden en **una sección: «Resultados de tu tienda»**, en el mismo
lugar del panel. El resto del panel (Por tienda, Tus anuncios, alertas, reparto, productos, evaluación con IA, Cada
anuncio) no cambia en esta entrega. El selector de periodo, de canal y de tienda sigue siendo el de la barra de
arriba del panel (`data-tw-param`): esta sección no trae otro selector de periodo.

### 2.1 Tarjetas que mueven la gráfica

Seis tarjetas (botones, `role="tab"`): **Ventas, Pedidos, Gasto en anuncios, Retorno por dólar (MER), Ticket
promedio, Costo por pedido**. Cada una muestra el total del periodo, una minigráfica (la serie diaria, sin ejes) y,
solo con un periodo de N días, la variación contra los N días anteriores (▲/▼, verde si es bueno, rojo si es malo,
gris para el gasto, que no es bueno ni malo; en «Costo por pedido» bajar es bueno). Tocar una tarjeta cambia la
métrica de la gráfica; la elegida queda marcada.

Con un canal elegido no hay datos de tienda: las tarjetas pasan a **Ventas atribuidas, Pedidos atribuidos, Gasto,
ROAS (Pixel), Ticket atribuido, Costo por pedido atribuido**, todo del canal.

Las tarjetas de utilidad y clientes nuevos **no existen** en esta entrega (sus columnas llegan en 0).

### 2.2 La gráfica

- **Ventas** (por defecto): línea azul con un área suave debajo + barras de gasto. Las demás métricas de línea
  (Pedidos, Retorno, Ticket, Costo por pedido): solo la línea con su área. **Gasto**: barras apiladas, con un
  selector **«Por antigüedad» / «Por canal»**:
  - por antigüedad: anuncios nuevos (menos de 14 días desde su primer gasto) y anuncios con más de 14 días;
  - por canal: Meta, Google, Snapchat, TikTok y «Otros» (cualquier otro canal con gasto, fundido). Con un canal
    elegido no hay «Por canal»: solo antigüedad, sobre el gasto de ese canal.
- **Un solo eje.** Ventas y gasto son dinero en la misma moneda; Retorno se ve en su propia vista (nunca dos ejes).
- **Hoy va aparte**: el último punto es hoy, punteado y con el marcador hueco; su barra va rayada. La etiqueta del eje
  dice «hoy». Debajo de la gráfica: «Hoy va en 4.273 USD y 50 pedidos con 1.322 USD de gasto · día a medias (última
  copia 06:14)».
- **Comparar** (interruptor, encendido por defecto, solo con N días): la misma métrica de los N días anteriores,
  alineada día con día, como línea gris punteada.
- **Tendencia** (interruptor, apagado por defecto): la línea pasa a ser el promedio de los últimos 7 días (también la
  comparación); se esconden los marcadores de día raro y de mejor día.
- **Mejor día** del periodo: punto lleno con su valor encima (en «Costo por pedido», el más bajo).
- **Días fuera de lo normal**: hasta 3 días marcados con un anillo (verde arriba, rojo abajo) cuando el valor se
  aparta 25 % o más de la mediana del mismo día de la semana en las 4 semanas anteriores (hacen falta 3 de esas 4
  semanas con dato). Hoy nunca se marca.
- **Retorno**: además, una línea punteada ámbar «tu meta 2×» con la misma meta de ROAS que ya usa el panel
  (`evaluacion.meta_roas`: el `roas_min` de las reglas del proyecto; si está apagado, la mediana de la cuenta).
- **Pasar el mouse** (o el dedo) sobre la gráfica: una línea vertical sigue al día más cercano y aparece un recuadro
  con ese día: fecha con día de la semana, ventas, gasto, retorno, pedidos, % del gasto que fue a anuncios nuevos, la
  nota «▲ 38 % sobre un miércoles normal» si es un día raro, el valor del día equivalente del periodo anterior si
  «Comparar» está encendido y la pista «Clic para ver qué pasó ese día». Con teclado: la gráfica es enfocable,
  ← → mueven el día y Enter lo abre.
- **Antigüedad desconocida**: los primeros 14 días de la copia de Triple Whale no permiten saber si un anuncio era
  nuevo (pudo empezar antes de la copia). Esos días, en «Por antigüedad», la barra va en gris neutro con la leyenda
  «antigüedad desconocida» y el recuadro dice «—» en anuncios nuevos.

### 2.3 «Qué pasó el miércoles 17 sep» (detalle del día)

Debajo de la gráfica, siempre visible; arranca en **ayer** (o en el último día completo con datos, si ayer no tiene). Un clic en un día (o Enter, o ‹ › del propio panel)
cambia el día; el día elegido queda sombreado en la gráfica. Llega por fetch (fragmento HTML del servidor, ver §4.3)
con «Cargando…» al instante y gana solo el último pedido. Muestra:

- Ventas, Pedidos, Gasto y Retorno del día, cada uno contra **el mismo día de la semana anterior** (▲▼). Esta
  comparación existe también en «Desde el inicio»: es del día, no del periodo.
- **Por canal**: gasto del canal (barra = su parte del gasto del día) y su retorno atribuido según el Pixel; solo
  canales con gasto ese día (Direct, Klaviyo, orgánico y demás fuentes sin gasto no entran: no son anuncios).
- **Los anuncios que más vendieron**: hasta 5 anuncios **con gasto ese día**, ordenados por ventas atribuidas; cada
  uno con nombre, canal, «nuevo» si tenía menos de 14 días, ventas atribuidas, gasto y retorno, y «Hecho en Creatv»
  con enlace al experimento si `datos.piezas_creatv` lo reconoce.
- «Ese día arrancaron N anuncios nuevos.» y el enlace «Ver todos los anuncios →», que baja a «Cada anuncio».
- Con un canal elegido, todo se limita a ese canal (y no hay «Por canal»).
- Hoy no se puede abrir (día a medias): el clic sobre hoy no hace nada y ‹ › no llegan a hoy.

### 2.4 «Lo que dicen los números»

De 1 a 4 frases armadas con reglas (sin IA, gratis), en este orden y solo si aplican:

1. **Cómo vas** (solo con N días): «Vendiste 0,8 % menos que en los 29 días anteriores con 3,8 % menos de gasto:
   cada dólar trajo 2,42× (antes 2,35×).» Compara días completos (§3.2).
2. **Mejor día**: «Tu mejor día: el jueves 17 sep, con 19.273 USD y 271 pedidos. Ver qué pasó →» (abre el detalle).
3. **Anuncios nuevos sin presupuesto** (aviso ámbar): si en los últimos 2 días completos la parte del gasto que fue a
   anuncios nuevos quedó 15 puntos o más por debajo de la del periodo: «Los anuncios nuevos se quedaron sin
   presupuesto: 12 % del gasto de los últimos 2 días (en el periodo, 49 %). Sin pruebas nuevas no aparece el próximo
   ganador.» con dos botones: **«Crear anuncios nuevos →»** (lleva a Crear, `#creativeflowplus`; no genera nada) y
   **«Evaluar con IA»** (baja a la sección de evaluación; el botón que cobra sigue siendo el de allá, con su precio).
4. **Por canal** (solo sin canal elegido y con 2+ canales con gasto): «Meta se llevó el 89 % del gasto con 2,0× de
   retorno atribuido; Google, el 3 % con 34×; Snapchat, el 8 % con 5,4× (según el Pixel).» Los canales con menos de
   1 % del gasto no se nombran.

### 2.5 «Tus creativos»

De dónde salieron las ventas atribuidas del periodo según **el mes en que arrancó cada anuncio** (su primer día con
gasto en la copia):

- Dos barras horizontales apiladas: «Ventas atribuidas» y «Gasto», cada una partida por mes de arranque (azul, más
  claro = más reciente). El mes más viejo de la copia se llama «julio o antes» (la copia pudo empezar a mitad de mes).
- Leyenda por mes: «septiembre · 540 anuncios · 41 % de las ventas · 1,89×».
- Tres cifras: **anuncios nuevos probados** en el periodo (arrancaron dentro de él), **retorno de los nuevos** (sus
  primeros 14 días) y **retorno de los establecidos** (después de sus primeros 14 días), según el Pixel.
- Solo canales de pago (con gasto). Con un canal elegido, solo ese canal.
- Con menos de 2 meses distintos, no hay barras: solo las tres cifras.

### 2.6 Celular

Tarjetas en 3 columnas hasta 760 px y en 2 hasta 480 px; la gráfica ocupa el ancho y se toca para ver el recuadro
(arriba de la gráfica, nunca fuera de la pantalla); el detalle del día apila sus dos columnas; nada empuja la página
de lado (`tests/test_movil.py`).

## 3. Reglas de cálculo

### 3.1 Periodos y hoy

- El periodo es el del panel (`panel.periodo(dias, hoy, primero)`): N días que terminan **hoy**, o «Desde el inicio»
  (del primer día copiado a hoy). Las tarjetas muestran el total del periodo **con hoy incluido** (como el resto del
  panel y como `resumen_total_tienda`).
- La gráfica tiene un punto por día del periodo, hoy incluido como punto a medias. Con «Desde el inicio» y más de
  120 días, la gráfica muestra igual todos los días (barras más finas, etiquetas de fecha más espaciadas).

### 3.2 Variaciones y comparación

- La variación de una tarjeta compara **días completos**: los N−1 días del periodo sin hoy contra los N−1 días
  anteriores. El recuadro de la tarjeta dice «contra los N−1 días anteriores (días completos)». Así hoy a medias no
  inventa una caída.
- La comparación de la gráfica alinea el día i del periodo con el día i de los N días anteriores (sin el punto de hoy).
- Sin dato en el periodo anterior (variación sin base), no se muestra variación.

### 3.3 Métricas por día

`mer = ingresos/gasto`, `ticket = ingresos/pedidos`, `costo por pedido = gasto/pedidos`; con divisor 0 el valor es
None (la línea se corta en ese día, el recuadro dice «—»). Las de periodo se calculan de las sumas, nunca promediando
razones diarias.

### 3.4 Antigüedad de un anuncio

- `primer_dia(canal, ad_id)` = la primera fecha con gasto > 0 en toda la copia del alcance (tienda o «Todas»).
- Un anuncio es **nuevo** en la fecha f si `f <= primer_dia + 13 días` (14 días contando el primero).
- La antigüedad se conoce desde `inicio_copia + 14 días`. Antes de eso, el gasto del día va a «antigüedad
  desconocida» y esos días no cuentan para el aviso de §2.4.3 ni para «retorno de los nuevos/establecidos».
- Gasto del día por antigüedad: `nuevos` = suma del gasto de anuncios nuevos ese día; `establecidos` = gasto de la
  tienda del día − `nuevos` (≥ 0). Así la barra suma el gasto de la tienda aunque haya gasto fuera de los anuncios.

### 3.5 Días fuera de lo normal

Para cada día completo del periodo y la métrica elegida: la mediana de esa métrica en los 4 mismos días de la semana
anteriores (necesita al menos 3 con valor; la serie para esto se pide con 28 días extra hacia atrás). `desvío =
valor/mediana − 1`; se marcan los 3 de mayor |desvío| con |desvío| ≥ 0,25. La lógica vive en Python (§4.1) y viaja
al JS como `raros: {métrica: {índice: desvío}}`, así se prueba con pytest.

## 4. Cómo se construye

### 4.1 `triple_whale/resultados.py` (nuevo, puro)

Funciones sin base de datos ni Flask, que reciben filas y devuelven lo que pinta la sección:

- `armar(dias_periodo, serie, serie_previa, serie_extra, antiguedad, canales_dia, hoy, inicio_copia, roas_min,
  fuente)` → el diccionario `resultados` (tarjetas, puntos, raros, mejor día, hoy, lectura, creativos) listo para
  JSON. `fuente` es `"tienda"` o `"anuncios"` (con canal).
- `variacion`, `raros`, `mejor_dia`, `lectura`, `creativos` como funciones separadas, cada una probada sola.

Las frases de «Lo que dicen los números» se arman aquí con `gettext`/`ngettext` (idioma de quien mira) y números con
`idiomas.numero` y el filtro de dinero del panel (`tablero.dinero`). Nada de esto llama a Triple Whale ni a Claude.

### 4.2 `triple_whale/datos.py` (único lector de las tablas `tw_*`)

Consultas nuevas, todas con SQLAlchemy Core y el mismo criterio de «Todas» que `_anuncio_dia` (gasto de canal con
MAX por anuncio y día, Pixel con SUMA):

- `primeros_dias(cliente, tienda_id)` → subconsulta `(canal, ad_id, primer_dia)`; base de las otras tres.
- `gasto_por_antiguedad(cliente, tienda_id, desde, hasta, canal=None)` → `{fecha: gasto_nuevos}`.
- `gasto_por_canal(cliente, tienda_id, desde, hasta)` → `{fecha: {canal: (gasto, ingresos_pixel)}}`.
- `anuncios_del_dia(cliente, tienda_id, fecha, canal=None, limite=5)` → los anuncios con gasto ese día ordenados por
  ingresos del Pixel, con `nuevo` y `primer_dia`; y `arrancaron_el(cliente, tienda_id, fecha, canal=None)` → cuántos
  tuvieron su primer día ese día.
- `cohortes(cliente, tienda_id, desde, hasta, canal=None)` → por mes de arranque: anuncios, gasto, ingresos del
  Pixel; más gasto e ingresos de nuevos y de establecidos (solo días con antigüedad conocida) y los anuncios que
  arrancaron en el periodo.

Una consulta por bloque, nunca una por día ni por anuncio. Índices existentes: `ix_tw_anuncio_dia_cliente_fecha` y
`ix_tw_anuncio_dia_cliente_tienda_fecha` (60 663 filas de happyflops: el `MIN(fecha)` por anuncio de toda la copia
recorre el índice del cliente). De paso, `serie_anuncios` gana el parámetro `canal`: hoy, con un canal elegido, la
gráfica vieja mostraba el gasto de todos los canales.

### 4.3 Rutas

- `ver_panel` deja de armar `grafico` con `_grafico_tablero` (que sigue vivo para el Tablero): el contexto trae
  `resultados` y la plantilla lo vuelca como JSON en `<script type="application/json" id="tw-resultados-datos">`
  (con `|tojson`, que escapa `<`).
- **Nueva** `GET /cliente/<cliente>/triple-whale/dia?fecha=AAAA-MM-DD&tienda=&canal=` → fragmento `_tw_dia.html`.
  Protegida por `dashboard._guard_por_cliente` (la URL lleva `<cliente>`). `fecha` se valida con
  `date.fromisoformat` y tiene que estar entre el primer día copiado y ayer (si no, 400 con un texto corto); `tienda`
  pasa por `panel.tienda_elegida` (un id ajeno se ignora); `canal` solo si está en `datos.canales` del día. Solo
  lectura; los nombres de anuncios son texto ajeno y salen escapados por Jinja.

### 4.4 Plantillas

- `_tw_resultados.html` (nuevo): la sección, incluida desde `_tw_panel.html` donde hoy están «Tu tienda» y «Día a
  día». El esqueleto (cabecera, contenedores de tarjetas, gráfica, recuadro, detalle, lectura, creativos) lo pinta el
  servidor; el JS lo llena con el JSON. La lectura y «Tus creativos» los pinta el servidor (texto y barras), así se
  leen aunque el JS falle.
- `_tw_dia.html` (nuevo): el detalle del día.

### 4.5 `static/tw_resultados.js` (nuevo)

Como `static/exp_resultados.js`: ES5, sin librerías, `window.TwResultados.iniciar(raiz)`; los datos solo con
`textContent`/`setAttribute`; `innerHTML` solo con el fragmento del servidor; colores por clases (no en línea); los
textos de la interfaz llegan en el JSON (`textos`), traducidos por el servidor; números y fechas con
`toLocaleString(document.documentElement.lang)` y el código de moneda del JSON. `_tab_triple_whale.html` lo carga con
`<script src=… defer>` y llama `TwResultados.iniciar(cont)` después de pintar el panel (los `<script>` del fragmento
no corren). Funciones puras (escala del eje, pasos redondos, promedio de 7 días, posición del recuadro) expuestas en
`TwResultados._puro` para probarlas con Node.

### 4.6 Estilos

`static/estilos/pantallas/triple-whale.css` (la fuente; `python3 estilos.py construir` regenera `style.css`). Colores
solo con tokens: ventas `--serie-1`, gasto `--serie-2`, nuevos `--serie-3`, canales Meta `--serie-1`, Google
`--serie-3`, Snapchat `--serie-4`, TikTok `--serie-5`, Otros `--muted-2`; meses de arranque en una rampa de azules
derivada de `--serie-1`; anillos con `--ok`/`--error`; mínimo con `--warn`. Paletas validadas con el validador de la
skill dataviz sobre `--panel` y `--bg`: (ventas, gasto, nuevos) y (Meta, Google, Snapchat, TikTok) pasan todas las
pruebas. Se borran las reglas `.tb-*-tw` que solo usaba la gráfica vieja de esta pestaña.

### 4.7 Textos

Todo texto visible por el catálogo: plantillas con `_()`, Python con `gettext`, y los textos del JS dentro del JSON
(`textos`), armados con `gettext` en `resultados.py`. Después `catalogo_i18n.py actualizar`, traducir al inglés con
`docs/i18n/glosario.md` y `compilar`.

## 5. Pruebas

- `tests/test_tw_resultados.py`: las funciones puras — variación con días completos, sin comparación en «Desde el
  inicio», hoy a medias fuera de la variación, razones con divisor 0, días raros (umbral, máximo 3, mínimo 3 semanas,
  hoy excluido), antigüedad desconocida en los primeros 14 días, cada regla de la lectura (aparece y no aparece),
  canales chicos fuera de la frase, creativos con un solo mes.
- `tests/test_tw_resultados_datos.py`: las consultas sobre una base SQLite de prueba — primer día por anuncio, nuevo
  hasta el día 14, gasto por antigüedad y por canal, anuncios del día (solo con gasto, orden, límite), cohortes, y
  «Todas» con una cuenta compartida que no duplica el gasto.
- `tests/test_rutas_triple_whale.py` (ampliado): el panel trae el JSON y ya no el SVG viejo; la ruta `dia` (200,
  400 con fecha mala o fuera de rango, hoy rechazado, cliente ajeno bloqueado, tienda ajena ignorada, canal); número
  de consultas acotado (no crece con los días ni con los anuncios).
- Node (`tests/js/tw_resultados.test.mjs`, corrido como los demás): funciones puras del JS.
- Mirarlo de verdad: el panel con datos sembrados en el navegador (escritorio y 375 px), capturas de cada vista,
  recuadro, detalle del día y teclado, antes de dar nada por bueno (regla 4 de CLAUDE.md).

## 6. Fuera de esta entrega

- Miniaturas de los anuncios en el detalle del día (piden la Graph API de Meta al abrir).
- Rango de fechas libre, horas del día, proyección de cómo cierra hoy.
- Productos por día (PND-150) y utilidad / clientes nuevos (Triple Whale no los manda hoy).
- Llevar este mismo diseño al Tablero, a Experimentos y al resto del panel de Triple Whale.

## 7. Riesgos

- **Lo atribuido suma más que la tienda**: mitigado diciendo siempre «según el Pixel» y usándolo solo para comparar.
- **Rendimiento**: 4 consultas nuevas sobre `tw_anuncio_dia`; medidas con la prueba de número de consultas y con un
  tiempo real sobre una copia de producción antes de desplegar.
- **Otra conversación tocó el panel hoy** (5fce2658): este trabajo sale de `main` aa24b02 y se vuelve a mezclar con
  `main` antes de desplegar.
