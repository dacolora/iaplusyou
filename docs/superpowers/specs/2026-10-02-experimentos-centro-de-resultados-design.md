# Experimentos: centro de resultados — diseño

Fecha: 2026-10-02. Estado: rumbo aprobado en conversación por Daniel (maqueta del centro de resultados
«vamos»; Tablero fundido en Experimentos; presupuesto «total + días»; orden de entregas datos → centro →
nuevo experimento). Reemplaza la pantalla de Experimentos de `2026-09-20-experimentos-galeria-primero-design.md`
y la pestaña Tablero del Bloque 6 de `2026-09-14-motor-ecommerce-design.md`. **No cambia el motor**
(lanzador, decisor, modos, acciones, derivaciones): lee lo que ya guardan y le agrega datos nuevos de Meta.

**Estado al 2026-10-03 (cierre de E2, rama `exp-centro`, aún sin mezclar a main):** E1 está en producción (2026-10-02).
E2 está construida: el centro de resultados con su fragmento, el panel de cada pieza, la gestión por experimento y el
Tablero fundido (§4), y además, por decisión del controlador (la dirección de E3 que Daniel aprobó), «Nuevo experimento» ya
va a pantalla completa con «← Volver a resultados» y el presupuesto «total + días» (§5.2 y §5.3, con la validación del
servidor y las reglas del motor en palabras, §4.7). De E3 queda solo lo que dice la nota «Estado de §5» al principio de §5.

## 0. Por qué

Daniel, 2026-10-02, con dos referencias visuales (un tablero «Big Data» azul marino y azul eléctrico, y un
tablero de Meta Ads lleno de métricas): «la parte más importante del proyecto es la que tiene la experiencia
más fea». Lo que se encontró al leer el código:

- La pestaña abre con **todas** las piezas de Crear, sprints y finales (`experimentos.elegibles`, sin límite);
  los experimentos quedan abajo como acordeones. Lo primero que se ve no son resultados.
- El presupuesto se pide como número diario por país + tope + días, y la pantalla responde con un
  multiplicador («3 piezas × 2 países = 6 anuncios · hasta 8.000 COP/día · tope … · 7 días»). **Nunca dice
  cuánto va a gastar en total** (roza la regla 1 de la casa, «primero el precio»).
- Las métricas son una fila de 7 números chicos por anuncio, sin comparación, sin curva en el tiempo y con
  el veredicto como una etiqueta. «Reglas del motor» muestra claves de código (`gasto_min_x_presupuesto`).
- A Meta se le pide poco: totales acumulados por anuncio cada 2 h (`meta_ads/insights.CAMPOS_BASICOS`,
  `date_preset=maximum`). Ni día a día, ni embudo (Meta ya manda `actions` con visitas y carrito y se botan),
  ni retención del video, ni desgloses por ubicación/edad/género/región, ni los rankings de calidad de Meta.

Lo que Daniel quiere ver, en sus palabras: «una evolución del diagnóstico… lo más importante, ver cómo se
comporta, para poder replicar, mejorar más».

## 1. Alcance y entregas

Tres entregas, cada una se mezcla y se despliega sola, en este orden:

| Entrega | Qué | Por qué en este orden |
|---|---|---|
| **E1 · Datos completos de Meta** | tablas `metrica_dia` y `metrica_desglose`, módulo `meta_detalle.py`, carga inicial | todo lo demás se dibuja con esto; desplegada primero, los datos se acumulan mientras se construye E2 |
| **E2 · Centro de resultados** | la pestaña Experimentos nueva (con el Tablero adentro), el panel de cada pieza, la gestión de cada experimento, la identidad visual | es lo que Daniel mira cada día |
| **E3 · Nuevo experimento** | página propia a pantalla completa: piezas → dónde → cuánto (total + días) → revisar | saca la galería de la pestaña y arregla el presupuesto |

Fuera de alcance (anotado en `docs/pendientes.md` al cerrar cada entrega si sigue vivo): mapa geográfico real
(se muestra tabla por país y región), desgloses filtrados por periodo (v1: desde el inicio), comparar dos
experimentos lado a lado, la identidad azul en el resto de la app, reescribir el decisor.

## 2. Identidad visual («centro de mando»)

- Pedido explícito de Daniel (2026-10-02): «que el estilo de la parte de experimentos tenga este branding». Este spec
  suponía que solo Experimentos sería azul y que el resto de la app seguiría morada; el mismo día el **sistema de estilos**
  (`2026-10-02-sistema-de-estilos-design.md`) llevó el azul a TODA la app, así que lo siguiente ya no es cierto y quedó así:
- **No se crearon los tokens `--exp-*` ni la clase `.zona-exp` que remapeaba variables** (el bloque «Experimentos: centro de
  mando» de `static/style.css` no existe). Se reusa la paleta azul global de `static/estilos/tokens.css` (2026-10-02), y
  los colores de estado del centro se hacen con esos mismos tokens. Los reales, los que usa
  `static/estilos/pantallas/experimentos.css`: fondo y superficies `--bg`, `--panel`, `--panel-2`, `--panel-hover`; bordes
  `--border`, `--border-soft`; texto `--text`, `--muted`, `--muted-2`; acento `--accent`, `--accent-2`, `--accent-texto`;
  `--cian` (solo texto, trazos SVG y sombras: pasa de 0,4 de luminancia); brillo y sombras `--brillo`, `--brillo-sm`,
  `--shadow`, `--shadow-soft`, `--shadow-glow`, `--fondo-escena`; tipografía `--font-display`, `--font-body`; las series de
  las gráficas `--serie-1` a `--serie-8`; y los **colores de estado del centro**: `--ok`, `--error`, `--warn` con sus
  `--ok-fondo`, `--error-fondo`, `--warn-fondo` (`.cr-mejor`, `.cr-peor`, `.cr-neutro`, y el veredicto con
  `.cr-veredicto.cr-v-ganadora` / `cr-v-perdiendo` / `cr-v-recuperandose` / `cr-v-neutra`). Colores solo por variables
  (`tests/test_modo_oscuro.py`).
- Los estilos del centro (fragmento, panel de pieza y gestión, clases `cr-*`) viven en
  `static/estilos/pantallas/experimentos.css`, y los de «Nuevo experimento» en `pantallas/experimento-nuevo.css`; las
  `exp-*` anteriores siguen en `legado/`. `static/style.css` es GENERADO (`python3 estilos.py construir`).
- Lenguaje visual tomado de la referencia: secciones numeradas («01 Resumen del periodo», número en azul
  eléctrico con `--font-display`), tarjetas con borde fino y brillo azul en la destacada, donas de avance,
  curvas finas, iconos lineales. Verde/rojo solo para mejor/peor, siempre con ▲/▼ (no depende del color).
- Celular (≤ 760 px): indicadores a 2 columnas, gráficas al ancho (el SVG escala por `viewBox`, nada empuja
  la página de lado), tablas `tabla-apilada`, filtros que envuelven. Reglas de `tests/test_movil.py`.

## 3. E1 · Datos completos de Meta

### 3.1 Tablas nuevas (migración `0028_metricas_detalle`)

`metrica_dia` — una fila por anuncio (`experimento_pieza`) y día de la cuenta de Meta:

| Columna | De dónde (insights) |
|---|---|
| `experimento_pieza_id` FK, `fecha` (`YYYY-MM-DD`, zona de la cuenta) | `date_start` |
| `impresiones`, `alcance`, `frecuencia`, `clics`, `clics_enlace`, `gasto`, `cpm` | `impressions`, `reach`, `frequency`, `clicks`, `inline_link_clicks`, `spend`, `cpm` |
| `vistas_3s` | `actions[video_view]` (reproducciones de 3 s) |
| `reproducciones`, `p25`, `p50`, `p75`, `p95`, `p100`, `thruplay`, `tiempo_medio_s` | `video_play_actions`, `video_pNN_watched_actions`, `video_thruplay_watched_actions`, `video_avg_time_watched_actions` |
| `visitas_pagina`, `carrito`, `pago_iniciado`, `compras_meta`, `ingresos_meta` | `actions[landing_page_view]`, `[add_to_cart \| omni_add_to_cart]`, `[initiate_checkout \| omni_initiated_checkout]`, `[purchase \| omni_purchase]`, `action_values[purchase \| omni_purchase]` |
| `actualizado_en` | — |

Única por (`experimento_pieza_id`, `fecha`); índice por `fecha`. Se **reemplaza** la fila del día al volver a
pedirla (Meta corrige los últimos días).

`metrica_desglose` — totales desde el inicio por anuncio y valor de una dimensión:

| Columna | Nota |
|---|---|
| `experimento_pieza_id` FK, `dimension`, `clave` | `dimension` ∈ `ubicacion` (`publisher_platform`+`platform_position`, clave `instagram|reels`), `edad_genero` (`age`+`gender`, clave `25-34|female`), `dispositivo` (`device_platform`), `region` (`region`) |
| `impresiones`, `clics_enlace`, `gasto`, `vistas_3s`, `thruplay`, `compras_meta`, `ingresos_meta` | mismos orígenes que arriba |
| `actualizado_en` | — |

Única por (`experimento_pieza_id`, `dimension`, `clave`); se reemplaza el juego completo de un anuncio y una
dimensión en cada pasada (en una transacción: borrar + insertar).

Los rankings de Meta (`quality_ranking`, `engagement_rate_ranking`, `conversion_rate_ranking`, solo con ≥ 500
impresiones) van a `experimento_pieza.extra["rankings_meta"]` con `experimentos.marcar_pieza` (único escritor
de ese `extra`, toma el candado antes de leer — regla 5).

### 3.2 `meta_detalle.py` (nuevo, del lado de Creatv)

No se toca el submódulo `meta_ads` (vive en otro repo): se usa `meta_ads.auth.llamar` y `lanzador._con_credenciales`.

- `pedir_diario(campaign_id, desde, hasta)`: `GET act_<cuenta>/insights` con `level=ad`,
  `filtering=[{campaign.id EQUAL <id>}]`, `time_increment=1`, `time_range`, campos de §3.1, `limit=500`;
  sigue `paging.next` (hasta 20 páginas; si hay más, lo anota y para). Una llamada por experimento, no una por
  anuncio.
- `pedir_desglose(campaign_id, dimension, desde, hasta)`: igual pero con `time_range` desde la creación del
  experimento hasta hoy (no `date_preset=maximum`: pedir lo de por vida con desgloses es caro y Meta lo
  restringe) y `breakdowns=<dims>`; una llamada por dimensión (4). Pide **solo los campos que se guardan**
  (`ad_id`, `impressions`, `inline_link_clicks`, `spend`, `actions`, `action_values`,
  `video_thruplay_watched_actions`): sin `reach`, `frequency`, `cpm` ni `clicks`, porque el alcance con desgloses
  es lo más caro y Meta lo limita a 13 meses. Si Meta rechaza una combinación de campos con un desglose, esa
  dimensión queda en `experimento.extra["detalle_meta"]["errores"]` (sin inundar la bitácora cada 2 h) y las
  otras siguen.
- `pedir_rankings(campaign_id, desde, hasta)`: `level=ad`, `time_range` desde la creación hasta hoy, los tres
  rankings.
- `refrescar_detalle(cliente, experimento_id, hoy=None)`: junta todo, mapea `ad_id → experimento_pieza.id`
  (los ids de anuncio que no son de este experimento se ignoran: aislamiento entre proyectos) y escribe.
  El rango del día a día se cura solo: desde el último día guardado menos 2, o desde la creación del
  experimento; el de los desgloses y los rankings es siempre la creación del experimento (acotada a hoy) hasta
  hoy.
- Errores: el texto pasa por `cola.sin_token` antes de un evento o un log (regla 6). Un fallo de detalle
  **nunca** tumba el refresco de siempre ni el decisor (`refrescar_detalle` no lanza). Dos clases de fallo cortan
  la pasada entera para no seguir golpeando a Meta: un **límite de llamadas** (`limite = True`, §3.3) y un
  **fallo de red o un HTTP 5xx** (el texto trae «falló en red» o «respondió 5…», el formato de
  `meta_ads.auth.llamar`; `cortado = True`, sin marcar `limite`). La parte que falló queda en `errores`.
  El estado se guarda en `experimento.extra["detalle_meta"]`: `actualizado_en`, `desde`, `errores` (sin token),
  `limite` y `cortado`.

### 3.3 Cuándo se pide

- `tareas/experimentos.exp_refrescar` llama `lanzador.refrescar` (como hoy, el decisor depende de eso) y
  **después** `meta_detalle.refrescar_detalle`, en su propio `try`.
- Carga inicial: tarea nueva `exp_detalle` (job `<cliente>__exp<id>__detalle`, `max_intentos=2`, no cobra)
  que pide desde la creación del experimento. Se encola una vez por experimento con `meta_campaign_id`: al
  desplegar (un comando de §7, carga inicial con `meta_detalle.encolar_todos()`); uno nuevo lo cubre su primer
  `exp_refrescar`, que ya parte de la creación del experimento. Como `exp_refrescar` ahora también pide el
  detalle, su `duracion_estimada` es 90 (antes 30), tanto en la periódica como en el botón «Actualizar».
- Costo: cero (Meta no cobra lecturas). Límite de Meta: 1 + 4 + 1 llamadas por experimento cada 2 h; hoy son
  2 por anuncio. Un **código de límite** es cualquiera de la familia de `meta_errores._LIMITE` (4, 17, 32, 613 y
  los límites «por caso de uso de negocio» 80000, 80001, 80002, 80003, 80004, 80005, 80006, 80008, 80009 y
  80014; 80000 es el de Ads Insights); `meta_errores.es_limite(texto)` lo dice y `meta_detalle.es_limite`
  delega en ella. Con uno se corta la pasada de detalle. En `exp_refrescar` se reintenta en la siguiente
  (2 h); `exp_detalle` **no dice «al día» si Meta pidió esperar**: devuelve `Continuar("exp_detalle", …)` con
  `vuelta + 1` y `ejecutar_desde` a 30 minutos (mismo `job_id`), hasta 3 vueltas (`payload["vuelta"]`, 0 si no
  viene); a la tercera termina con un mensaje que dice que Meta siguió pidiendo esperar y que el detalle quedó
  incompleto. Si no hubo límite pero alguna parte falló, el mensaje nombra las partes que fallaron
  («Detalle de Meta incompleto: falló region, rankings») y solo sin errores dice «al día».

### 3.4 Pruebas de E1

`tests/test_meta_detalle.py` con respuestas de Meta grabadas a mano (sin red): mapeo de campos y `actions`,
paginación, reemplazo del día, desglose borrar+insertar, rankings en `extra`, anuncio ajeno ignorado, un
desglose que falla no tumba los otros, un fallo de detalle no tumba `exp_refrescar`, token nunca en el evento
(ni en el log de `exp_refrescar`), la familia de códigos de límite, una red caída o un 5xx que corta la pasada
sin marcar límite, los desgloses y rankings con `time_range` y solo los campos que se guardan, `exp_detalle` con
`Continuar` (vuelta 1 con `ejecutar_desde` en el futuro; a la vuelta 3 termina; con errores nombra la parte) y el
aislamiento de `guardar_desglose` entre experimentos.

## 4. E2 · Centro de resultados

### 4.1 Estructura

- La pestaña Experimentos deja de pintarse dentro de `ver_cliente` (hoy viaja en los 3 MB de la página).
  `cliente.html` trae solo el armazón; al abrir la pestaña, `fetch` a
  `GET /cliente/<c>/experimentos/resultados?<filtros>` (patrón de `catalogo/grid`), que devuelve el fragmento.
  Cambiar un filtro vuelve a pedir el fragmento y deja el filtro en el hash
  (`#experimentos?exp=12&dias=14&pais=CO&pieza=55&tipo=video`), así un enlace o un recargar lo conserva.
- **Tablero fundido**: el botón «Tablero» sale del menú; `resolver('tablero')` en `cliente.html` devuelve
  `experimentos` (como `ads` hoy) y la pestaña por defecto al abrir un proyecto pasa a Experimentos. El chip
  del mes en el menú se queda y lleva a Experimentos. `tab_descargar_csv` se queda (botón en la cabecera).
  `?exp=<id>#experimentos` (enlaces viejos, alertas, correos) se traduce al filtro `exp=<id>`.
- Cálculo en un módulo nuevo y puro, `resultados.py` (`contexto(cliente, filtro, ahora_iso=None)`), que reusa
  `tablero.py` para el dinero y lee `metrica_dia`/`metrica_desglose` para el resto. **Sin caché propia** (así
  quedó en E2, revisión final 2026-10-03): `resultados.contexto` se calcula en cada pedido del fragmento y hoy no hace
  falta más; lo pesado que podría pedirla está anotado aparte (PND-134, el N+1 de `experimentos.cargar`; PND-137, el
  contexto que la página calcula sin pintar). La única caché de 60 s es la de `dashboard._contexto_tablero` (historial,
  tienda según Triple Whale, CSV del mes). Consultas acotadas: una por tabla, nunca una por tarjeta
  (`tests/test_rutas_resultados.py::test_el_fragmento_no_hace_mas_consultas_por_pieza_que_experimentos_cargar`).

### 4.2 De dónde sale cada número

- **Dinero** (gasto, compras, ingresos, ROAS, costo por compra): el mismo motor del Tablero de hoy
  (deltas de `metrica_snapshot`, `tablero.resumen_periodo` / `serie_diaria`), que respeta la atribución
  (Pixel, tienda, Triple Whale) y ya tiene pruebas. Así los totales, el mes a mes y lo que Daniel ya veía
  cuadran.
- **Sin ventas medibles, «—» y no 0** (revisión final de E2, 2026-10-03): compras, ingresos, ROAS y costo por compra
  solo existen si algo de lo elegido mide ventas, con la MISMA regla del Tablero: el snapshot de cierre tiene
  `fuente_ventas` en `tablero.FUENTES_VENTAS` (Pixel con compras, tienda o Triple Whale; `tablero.mide_ventas` /
  `tablero.ventas_medidas`). Sin ninguno, la pantalla pinta «—» y «sin ventas medibles» en el indicador, en el ranking
  (una nota bajo la tabla), en la tarjeta del experimento y en el panel de la pieza; antes un experimento de tráfico
  con atribución «ninguna» decía ROAS 0,0×. Con unos que miden y otros no, el ROAS y el costo por compra salen de los
  que miden (ingresos / gasto de esos); el gasto sigue siendo el de todo.
- **Todo lo demás** (impresiones, clics, CTR, CPC, CPM, gancho, retención, embudo, desgloses; el alcance y la
  frecuencia, con la regla del siguiente punto): `metrica_dia` y `metrica_desglose`. Los cocientes se calculan dentro de la misma fuente (CPC =
  gasto_dia / clics_dia de `metrica_dia`), nunca mezclando fuentes en una fracción.
- **Alcance y frecuencia no se suman entre días.** `alcance` y `frecuencia` de `metrica_dia` son del día (las
  personas únicas de un día no se suman a las de otro, y la frecuencia de un día no es la del periodo). La
  frecuencia del periodo o de la pieza sale del **último `metrica_snapshot`** (acumulada de por vida, la que
  Meta ya calcula) y se rotula «acumulada»; el alcance del periodo tampoco se arma sumando días.
- Moneda: se agrupa por la moneda del experimento y nunca se convierte. Con más de una moneda en el
  proyecto, aparece un filtro de moneda (por defecto la de más gasto).
- Sin datos diarios (experimento viejo sin la carga inicial todavía) la sección dice «cargando el detalle
  de Meta» en vez de ceros.

### 4.3 Filtros (fila de chips arriba)

Periodo (7 · **14** · 30 · 90 días · desde el inicio; se compara con el periodo anterior de igual largo, salvo
«desde el inicio»), experimento, país, pieza, tipo (video/imagen) y moneda si aplica. Botones a la derecha:
**«+ Nuevo experimento»** (lleva a `GET /cliente/<c>/experimentos/nuevo`, ruta `exp_nuevo`) y «Descargar CSV
del mes».

**Costura E2 → E3** (actualizada el 2026-10-03): para que E2 se pudiera desplegar sola, E2 crea la ruta `exp_nuevo` y muda
a ella la galería, la barra «Probar en Meta» y los pasos de hoy, y cambia los enlaces de §5.4. **Decisión del controlador,
2026-10-03 (la dirección de E3 que Daniel aprobó):** «Nuevo experimento» quedó ya en E2 a **pantalla completa**, sin menú
lateral y con «← Volver a resultados» (no «tal cual» dentro de una página con la identidad de §2), y el presupuesto
«total + días» (§5.2 y §5.3) también llegó en E2. Lo que de §5 sigue para E3 está en la nota «Estado de §5».

### 4.4 Secciones (de arriba abajo, como la maqueta aprobada)

0. **Necesita tu decisión**: propuestas pendientes (con su precio estimado cuando lo tienen, como hoy) y
   alertas de `tablero.alertas`, con Aprobar/Rechazar en línea (mismas rutas y los mismos `confirm()` cuando
   gasta). Sin nada pendiente, una línea «Nada por decidir» — solo si tampoco hay alertas; con alertas va solo la
   línea «N alertas necesitan tu atención → Ver Alertas».
1. **01 Resumen del periodo**: 12 indicadores en 3 filas — Gasto, Compras, Ingresos, ROAS · CTR del enlace,
   Costo por clic, CPM, Frecuencia (rotulada «acumulada»: del último `metrica_snapshot`, nunca la suma ni el
   promedio de las diarias) · Impresiones, Gancho (3 s), ThruPlay, Costo por compra. Cada uno con
   valor, variación ▲/▼ contra el periodo anterior (verde = mejor, rojo = peor según la métrica: un CPC que
   baja es verde) y una curva mínima de 14 puntos. Compras, Ingresos, ROAS y Costo por compra dicen «—» y «sin
   ventas medibles» cuando nada de lo elegido mide ventas (§4.2). Debajo, en línea aparte: «Generación con IA» (gasto de
   proveedores del periodo, `gastos`) y, con Triple Whale conectado, la fila «Tu tienda según Triple Whale»
   del Tablero de hoy.
2. **02 Día a día**: barras de gasto + una línea a elegir (CTR, ROAS, CPC, CPM, Frecuencia, Gancho) con
   chips; marcas verticales en los días donde el motor actuó (eventos `veredicto`, `accion`, `tope`, pausas,
   escaladas) con su texto al pasar el dedo.
3. **03 Dónde se cae la gente**: embudo impresiones → clics en el enlace → visitas a la página → carrito →
   pago → compras, con el porcentaje de cada paso. La frase de abajo compara cada paso con **el promedio del
   propio proyecto** (todos sus experimentos) y nombra el de mayor caída relativa; con menos de 2
   experimentos con datos no hay frase (no se inventan promedios de mercado). Pasos sin Pixel se ven
   apagados con «requiere el Pixel»: **las visitas a la página también son del Pixel** (`landing_page_view`), así que
   `resultados._PASOS_PIXEL` las incluye junto al carrito, el pago y las compras (revisión final de E2: sin ellas, un
   proyecto sin Pixel leía «la caída más grande está en las visitas»). Un paso sin Pixel nunca es «la caída», y con
   pasos sin medir no se dice que «todos» están en el promedio.
4. **04 Evolución del diagnóstico por pieza**: una tarjeta por pieza del filtro (las 8 de más gasto; «ver
   todas»), con la métrica principal día a día contra el promedio del experimento (línea punteada), el
   veredicto con nombre humano y la historia en una línea armada **sin llamar a Claude** (cero costo):
   tramos del veredicto en el tiempo (de los eventos y `veredicto_en`), tendencia de los últimos 5 días
   (sube/baja/estable por pendiente), fatiga (frecuencia **acumulada** — la del último `metrica_snapshot`, no la
   diaria de `metrica_dia` — > 2,5 con la métrica cayendo), gancho bajo (< 25 %),
   el rescate en curso (`escalon_rescate`) y las causas del diagnóstico de la doctrina si existen. La
   métrica principal sale del objetivo: ventas → ROAS; tráfico → CTR del enlace.
   Nombres de veredicto: `ganador` → «Ganadora», `perdedor` → «Perdiendo», `inconcluso` → «Sin diferencia
   clara», `pendiente` → «Aprendiendo» con lo que le falta según las reglas efectivas («le faltan 380
   impresiones» / «12 h más»), rescate → «Recuperándose (rescate 2/3)».
5. **05 Ranking de piezas**: tabla ordenable (gasto, CTR, gancho, CPC, ROAS, compras, Δ ROAS) con barras en
   la celda y miniatura. Tocar una fila abre el **panel de la pieza** (§4.5).
   **Lo que quedó en E2:** el plan lo achicó — la tabla NO se ordena (sale por gasto, de mayor a menor) y no tiene
   columna «compras» (Pieza · País · Gasto · CTR · Gancho · CPC · ROAS · Δ ROAS). Ordenar y la columna de compras
   van para E3 (§5, «Queda para E3» (e), y PND-136 punto 14).
6. **06 Quién compra y dónde lo ve**: dona de ubicaciones por gasto, barras por edad (y género), tabla por
   país (de los conjuntos) y por región, dispositivo. Rótulo «desde el inicio» (v1 no filtra desgloses por
   periodo). Métrica de las barras: ROAS con ventas, CTR sin ventas.
7. **07 Experimentos**: una tarjeta por experimento con dona de presupuesto usado (gasto / tope), día x de y,
   estado, piezas y países, ROAS o CTR y su mejor pieza; tocarla filtra la pantalla a ese experimento.
8. **08 Lo que ya aprendió el proyecto**: el bloque de `_aprendizajes.html` de hoy (doctrina, bloque 4).
9. **Historial mes a mes** plegado (`tablero.mes_a_mes`, la tabla de hoy) y, si existen, **Anuncios sueltos
   (de antes)** plegados (`_anuncios_sueltos.html`, solo lectura como hoy).

Sin Meta conectada: estado vacío con `_meta_conectar.html`. Sin experimentos: estado vacío con el botón de
nuevo experimento.

### 4.5 Panel de la pieza

Se abre a la derecha (abajo en el celular) por `fetch` a `GET /cliente/<c>/experimentos/pieza/<ep_id>`
(`abrirDetalleRemoto` de `base.html`). Lleva: el video o la imagen, todos los indicadores de la pieza en el
periodo, sus curvas (métrica principal, CPC, frecuencia, gancho), la **curva de retención** (3 s / 25 / 50 /
75 / 95 / 100 %, solo video), sus desgloses, los rankings de Meta, la historia del veredicto, el diagnóstico de
la doctrina («¿Por qué?» como hoy) y acciones: «Probar en otro experimento» (E3 con esa pieza marcada), «Ver en
Crear», publicar orgánico (`bloque_organico`, como hoy) y quitar/pausar donde aplica hoy.

### 4.6 Gestionar un experimento (filtro `exp=<id>`)

Con un experimento elegido, encima de las secciones aparece su cabecera: nombre, estado, modo, atribución,
objetivo, parentesco (padre/derivados) y el error explicado (`error_meta`, «Detalle técnico» plegado), y la
barra de acciones de hoy (Lanzar / Reintentar, Activar todo, Pausar todo, Evaluar ahora, Actualizar
métricas, Cerrar) con los mismos `confirm()`. Debajo, plegado «Gestionar»: países con presupuesto diario
editable y Activar/Pausar país, piezas por país (quitar en `armando`), agregar pieza (en `armando`/`error`),
modo, reglas propias, derivaciones en curso y bitácora. Todo con las **mismas rutas POST**; lo único que
cambia es que, al terminar, redirigen a `#experimentos?exp=<id>` para no perder la selección. Barra de
progreso del lanzamiento con `data-poll-job` (sin `<script>`).

### 4.7 «Cómo decide el motor» (antes «Reglas del motor»)

Mismo formulario y misma ruta (`cfg_reglas`, `exp_reglas`, `_form_reglas.html`), en un cajón desde la
cabecera; sin claves de código a la vista y con cada regla dicha como frase, p. ej. «Antes de juzgar una
pieza: al menos [1.000] impresiones, [48] horas y que haya gastado [2] días de su presupuesto diario».
Las etiquetas viven en `decisor.ETIQUETAS` (se reescriben ahí).

### 4.8 Gráficas

`resultados.py` entrega series ya calculadas como JSON (`<script type="application/json">` dentro del
fragmento); `static/exp_resultados.js` (nuevo, pasa `node --check`) dibuja SVG en línea: barras + línea,
curvas mínimas, dona, retención y embudo, con aviso al pasar el dedo o el mouse y los chips de métrica sin
volver a pedir datos. Sin librerías externas. Colores solo por las variables del sistema de estilos (§2; los tokens
`--exp-*` nunca existieron): barras del día a día `--accent` / `--accent-2` (la activa), línea `--cian`, series de la
dona y la leyenda `--serie-1` a `--serie-8`, la curva de una pieza según su veredicto `--ok` / `--error` / `--warn` /
`--muted` y la del promedio `--accent-2` (`static/estilos/pantallas/experimentos.css`).

### 4.9 Pruebas de E2

- `tests/test_resultados.py` (puro, base en memoria): variación contra periodo anterior, mejor/peor por
  métrica, fuentes (dinero del motor del Tablero, el resto de `metrica_dia`), embudo con y sin Pixel, frase
  del embudo solo con ≥ 2 experimentos, historia de la pieza (tendencia, fatiga, gancho, «le faltan N»),
  desgloses agregados, filtros (experimento, país, pieza, tipo, moneda), aislamiento entre proyectos.
- `tests/test_rutas_resultados.py`: el fragmento y el panel de la pieza (200, 404 de otro proyecto,
  consultas acotadas con 3 y con 30 piezas), `#tablero` → experimentos, redirecciones a
  `#experimentos?exp=<id>`, botón de nuevo experimento.
- Se adaptan (no se borran a ciegas) las pruebas que fijan el HTML viejo: `test_rutas_experimentos_galeria.py`,
  `test_rutas_tablero.py`, `test_base_visual.py`, `test_movil.py`; las de `tablero.py` siguen igual porque el
  módulo no cambia.
- Captura real antes de dar por buena la pantalla (regla 4 de «Cómo se trabaja»): escritorio y celular, con
  datos sembrados.

## 5. E3 · Nuevo experimento (página propia)

**Estado de §5 al 2026-10-03** (contra `templates/exp_nuevo.html` y `_exp_probar.html`):

- **Ya hecho en E2:** la página a pantalla completa con «← Volver a resultados» y la barra de pasos (01 Piezas · 02 Dónde ·
  03 Total y días · 04 Revisar); un solo `<form>` que termina en `POST exp_probar`; los países con bandera y la edad (paso 2,
  con la línea de que las finales conservan su país); el paso 3 entero (total grande y días, los atajos Prueba rápida ·
  Estándar · Fuerte como «Sugerencia», la barra «Ajustar el total», «Usar ese total», «Ajustar reparto» plegado con «Volver al
  reparto automático», y debajo «Máximo que puede gastar…» o «Presupuesto planeado…», «≈ X al día», «N anuncios (P piezas en C
  países)» y «Nada gasta hasta que pulses Activar»); el paso 4 (cuadrícula pieza × país, nombre automático editable,
  «Avanzado», aviso de doctrina y «Lanzar a Meta (en pausa)» con `confirm()` que repite el resumen); §5.2 y §5.3 completos
  (módulo `presupuesto_experimentos.py`, espejo `static/presupuesto_exp.js`, la validación `suma × días ≤ total × 1,01` en el
  servidor); y los enlaces de §5.4.
- **Queda para E3:** (a) el paso 1 sigue siendo la galería de siempre: todas las piezas elegibles van en el HTML y los
  filtros y el buscador corren en el navegador. Falta paginarla (24 por página con «Ver más» y el fragmento
  `GET /cliente/<c>/experimentos/nuevo/piezas?desde=N&filtro=&q=`, que **no existe**). (b) Falta el resultado de lo ya probado
  en cada pieza («Ganadora · CTR 2,6 % en Prueba 19 sep», para replicar lo que funcionó): hoy una pieza solo dice «en prueba:
  <nombre>» si está en un experimento vivo, y nada de lo que ya terminó. (c) Los países del paso 2 son casillas con bandera,
  no tarjetas. (d) Las pruebas de (a) y (b), que §5.5 detalla. (e) Del centro (§4.4.5): ordenar el ranking de piezas
  y su columna «compras».

### 5.1 Recorrido

`GET /cliente/<c>/experimentos/nuevo` — página a pantalla completa con la identidad de §2, sin el menú
lateral, con «← Volver a resultados» y una barra de pasos arriba. Un solo `<form>` que termina en el mismo
`POST exp_probar` de hoy (el motor no cambia).

1. **Piezas**: la galería que hoy está en la pestaña, ahora aquí: filtros (Todo · Videos · Imágenes · Finales
   · Sprints), buscador, 24 por página con «Ver más» (fragmento
   `GET /cliente/<c>/experimentos/nuevo/piezas?desde=N&filtro=&q=`, nada de cargar todas). Cada pieza que
   ya se probó muestra su resultado («Ganadora · CTR 2,6 % en Prueba 19 sep») para replicar lo que funcionó.
   Llegadas: `?piezas=1,2` (desde Crear, Final edition, Sprints) y `?exp_nombre=&exp_destino=` (Catálogo).
2. **Dónde**: países como tarjetas con bandera; una final fija su país; edad.
3. **Cuánto**: la opción aprobada — una cifra total grande y los días, con atajos **Prueba rápida ·
   Estándar · Fuerte** y una barra para ajustar (o escribir la cifra). Creatv reparte solo: presupuesto
   diario de cada país = total × (anuncios del país / anuncios totales) / días, redondeado hacia abajo a la
   unidad de la moneda. Debajo, en grande: «Máximo que puede gastar: 300.000 COP en 7 días», «≈ 42.857 COP
   al día · 🇨🇴 21.428 · 🇲🇽 21.428», «6 anuncios (3 piezas en 2 países)» y «Nada gasta hasta que pulses
   Activar». Si un país queda bajo el mínimo diario de Meta, se dice en palabras con el total mínimo que lo
   arregla y un botón «Usar ese total». «Ajustar reparto» (plegado) deja editar el diario de cada país y la
   cifra total se recalcula. Sin multiplicador a la vista.
4. **Revisar**: tarjeta resumen con el máximo en grande, la cuadrícula pieza × país (como hoy), el nombre
   automático editable, «Avanzado» plegado (objetivo, atribución, modo, URL, como hoy) y el aviso de doctrina
   de hoy. Botón único **«Lanzar a Meta (en pausa)»** con `confirm()` que repite el máximo.

### 5.2 Los atajos de presupuesto

Módulo nuevo `presupuesto_experimentos.py` (puro; el espejo en JS es `static/presupuesto_exp.js`): `atajos(moneda, anuncios_por_pais)` → tres opciones con total y
días, a partir del mínimo diario de Meta por moneda (`PRESUPUESTO_MINIMO_DIARIO`, que se muda aquí desde
`dashboard.py`): diario por anuncio = 4× / 8× / 15× el mínimo, durante 4 / 7 / 10 días, total redondeado a
2 cifras significativas. Se rotulan «sugerencia» (no son precios de un proveedor; el precio es la cifra que
elige la persona). `repartir(total, dias, anuncios_por_pais, moneda)` hace la cuenta de §5.1 y devuelve
también los países bajo el mínimo y el total mínimo que los arregla; el JS de la página la replica y una
prueba de paridad compara ambos (como el editor).

### 5.3 Validación en el servidor

`exp_probar` gana una comprobación: `suma(presupuesto_<país>) × días ≤ tope_total` (con 1 % de margen por
redondeo); si no, rechaza con «el reparto supera el total». Así «máximo que puede gastar» es verdad aunque
alguien arme el POST a mano. El resto de validaciones no cambia. Límite que ya existe y se dice en la
pantalla: el conjunto de Meta termina a los N días contados desde el lanzamiento, no desde la activación
(`meta_ads/adset.crear_adset`, `end_time`); se anota como pendiente nuevo en `docs/pendientes.md`. (Después se resolvió aparte, no en E2/E3: PND-113, lote 2 de Codex, 2026-10-03; el fin de la pauta se fija en la primera activación y la pantalla dice que los días empiezan a contar cuando se activa.)

### 5.4 Qué sale de la pestaña y qué enlaces cambian (se hace en E2, ver la costura de §4.3)

- Sale de `_tab_experimentos.html`: la galería, la barra «Probar en Meta» y los tres pasos (con su JS).
  `experimentos.elegibles` deja de llamarse en `ver_cliente`; solo lo usan la página nueva y, en «Gestionar»
  de un experimento `armando`/`error`, el selector «agregar pieza».
- Los enlaces `#experimentos?piezas=<id>` de `_crear_detalle.html`, `_final_detalle.html` (y sprints) pasan
  a `url_for('exp_nuevo', cliente=…, piezas=…)`; un hash viejo con `piezas` se redirige por JS a la página
  nueva. «Crear experimento» de Catálogo redirige a la página nueva con `exp_nombre`/`exp_destino`.

### 5.5 Pruebas de E3

`tests/test_presupuesto_experimentos.py` (reparto, redondeo por moneda sin decimales, país bajo el mínimo, atajos, paridad
Python↔JS del reparto) y `tests/test_rutas_exp_nuevo_presupuesto.py` (la página y su cuenta, el «Máximo que puede gastar» o
el «Presupuesto planeado», `exp_probar` rechaza un reparto que supera el total) **ya existen, hechas en E2**; las
pruebas de la galería y de los enlaces desde Crear/Catálogo se adaptaron en E2 (`tests/test_rutas_resultados.py`,
`tests/test_rutas_experimentos_galeria.py`). Para E3 faltan las de la galería paginada (`nuevo/piezas`) y las del
resultado por pieza.

## 6. Reglas de la casa que aplican

- Plata: E1 y E2 solo leen; E3 no cambia qué gasta ni cuándo (lanzar sigue en pausa, activar sigue siendo un
  clic con `confirm()`), y hace visible el máximo antes de lanzar. `guardian-gasto` revisa E3.
- Seguridad: rutas GET nuevas con `cliente` validado y aislamiento (una pieza o experimento de otro proyecto
  da 404); nada de POST nuevo salvo los que ya existen; ids de Meta ajenos ignorados. `auditor-seguridad`
  revisa E1 y E2.
- Idioma: todo texto nuevo por el catálogo y traducido al inglés (`catalogo_i18n.py actualizar` →
  traducir con el glosario → `compilar`).
- Skills: al cerrar cada entrega se actualizan `experimentos`, `ui` y `escala-y-salud` con lo nuevo.

## 7. Despliegue (cada entrega, con la skill `despliegue`)

- E1: reinician worker y Flask; `alembic upgrade head` (0028) ensayado en una copia; luego la carga inicial,
  en este orden («lo real manda»: lectura gratis, se mira antes de repetirla en todos):
  1. **Uno primero.** Se encola `exp_detalle` solo para el experimento 3 de Forja (`colorado_forja`):
     `cola.encolar("exp_detalle", {"cliente": "colorado_forja", "experimento_id": 3}, cliente="colorado_forja",
     job_id=job_id_detalle("colorado_forja", 3), duracion_estimada=60, max_intentos=2)` (con `job_id_detalle` de
     `tareas.experimentos`), corrido a mano en el VPS con `TZ=America/Bogota`. Se espera a que el worker la termine
     y se mira el mensaje de la tarea, las filas nuevas de `metrica_dia` y
     `experimento.extra.detalle_meta.errores` de ese experimento. Si Meta rechaza algo (un desglose, un campo), se
     arregla antes de seguir.
  2. **Todos.** `ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && TZ=America/Bogota
     venv/bin/python3 -c "import meta_detalle; print(meta_detalle.encolar_todos())"'` (una tarea `exp_detalle`
     por experimento con campaña en Meta, idempotente por `job_id`; imprime cuántos encoló).
  3. **Humo.** Cuando la cola termine: contar las filas de `metrica_dia` y revisar
     `experimento.extra.detalle_meta.errores` de cada experimento (vacío = bien; un límite de Meta se reintenta
     solo hasta 3 vueltas de 30 min, y el resto lo completa el siguiente `exp_refrescar`).
- E2 y E3: solo Flask (salvo que toquen tareas).
- Daniel aprueba cada despliegue antes de hacerlo.
