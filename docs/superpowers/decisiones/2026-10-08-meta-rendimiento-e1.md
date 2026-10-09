# Meta rendimiento E1: decisiones del 2026-10-08

Registro de las decisiones («rulings» R1 a R30) que se tomaron al construir y revisar la pestaña Meta (varias cuentas
publicitarias leídas por proyecto). Salen del libro de trabajo de la construcción (`.superpowers/sdd/…`, carpeta ignorada
por git, por eso se copian aquí). Spec: `docs/superpowers/specs/2026-10-08-meta-rendimiento-design.md`. Plan:
`docs/superpowers/plans/2026-10-08-meta-rendimiento-e1.md`. Skill del área: `.claude/skills/meta-rendimiento/SKILL.md`.

Formato de cada línea: **qué se decidió — por qué — qué cuesta si está mal.** Si una decisión resulta mala, se cambia aquí
y en el código. Las sub-decisiones (R4b, R4c, R11b) refinan a la que llevan por número.

## Decisiones

### Durante la construcción (tareas 1 a 11)

- **R1.** `datos.guardar_objetos` actualiza solo las columnas presentes en cada diccionario (el nombre con `coalesce`) — los
  insights traen nombres sin `estado` y un pisado completo vaciaría estados y miniaturas — si está mal: cada copia de 3 h
  dejaría todos los estados en blanco.
- **R2.** El doble de prueba de `paginar` lleva `cursors.after` en la primera página y la prueba comprueba que la segunda
  llamada manda `after=A` — el plan lo pedía y sin eso la paginación no se probaba — si está mal: paginar sin prueba.
- **R3.** `test_nombre_none_no_pisa` se refuerza: tras el upsert con nombre `None`, `totales_por_anuncio` sigue diciendo
  «Video 1» y estado `PAUSED`, y `marcar_sin_estado` deja `a9` sin estado — la prueba original no afirmaba nada sobre el
  nombre — si está mal: la conservación del nombre queda sin probar.
- **R4.** `tasas.asegurar` se salta una moneda solo si ya hay una tasa en o antes del primer día hábil ≥ `desde` y la más
  reciente alcanza el objetivo (último día hábil ≤ `hasta`, o ≤ ayer si `hasta` es hoy); los huecos interiores son festivos
  (se rellena hacia delante); caché negativo de 6 h por (moneda, objetivo) cuando la consulta no llegó al objetivo o dio
  distinto de 200/404; todo dentro de `try`, nunca lanza; la moneda se valida con `[A-Z]{3}` — el código del plan volvía a
  pedir festivos y monedas sin soporte en cada llamada y dejaba rangos de un día viejos — si está mal: una consulta de más a
  frankfurter o un día viejo rellenado hacia delante.
- **R4b.** Se afina R4: el inicio es `min(último día hábil ≤ desde, objetivo)`, se salta si hay una fecha ≤ inicio y la
  más reciente ≥ objetivo, se comparan fechas ISO como texto y no hay salto anticipado — un rango «solo hoy» necesita la
  tasa de ayer rellenada hacia delante — si está mal: una consulta de más.
- **R4c.** Los fallos de red o de `ErrorConector` no entran al caché negativo: cada copia reintenta — una caída cuesta una
  consulta por copia pero nunca deja una tasa vieja — si está mal: unas consultas de más durante la caída.
- **R5.** Quitar una cuenta borra primero sus copias y después la fila de `meta_cuenta`; las excepciones suben y la fila
  sobrevive para que un reintento termine — «quitar borra sus copias» tiene que poder repararse — si está mal: una quita
  fallida muestra un error y hay que repetirla.
- **R6.** `actualizar_extra` toma el candado de la fila primero con un `UPDATE` vacío (patrón de `experimentos._bloquear`) y
  usa `rowcount` para saber si existe — regla 5 de CLAUDE.md (candado ANTES de leer; web y worker escriben `extra`) — si está
  mal: nada.
- **R7.** `adivinar_pais` usa el código ISO solo en la ÚLTIMA palabra del nombre («HappyFlops MX» da MX; «HappyFlops AD
  Account» da None) — menos falsos positivos y la persona siempre puede corregir — si está mal: un país más que elegir a
  mano.
- **R8.** `graph.paginar` reduce a la mitad `limit` (mínimo 25, hasta 3 veces) y reintenta la MISMA página ante los códigos 1
  y 2 de Meta; el listado de anuncios empieza en 100 — Meta rechazó de verdad un listado con `creative{}` a 500 por página —
  si está mal: el listado es más lento.
- **R9.** `graph.informe` recibe un callback `por_pagina`; `sync` convierte cada página en filas pequeñas al llegar y suelta
  las crudas; `TRAMO_ANUNCIO` pasa de 30 a 10 días — el VPS tiene 2 GB y una fila cruda pesa ~8 KB — si está mal: más
  informes en la primera copia.
- **R10.** Los anuncios también se listan con estados `PAUSED`/`ADSET_PAUSED`/`CAMPAIGN_PAUSED` con campos ligeros (sin
  `creative`), y `marcar_sin_estado` corre sobre la unión — así un anuncio pausado dice «En pausa» y no «Archivado», como
  muestra el spec §8 — si está mal: un listado paginado más por copia.
- **R11.** `sincronizar` devuelve `{"omitida": True}` si la cuenta ya no está en el proyecto; los marcadores de primera
  copia se parten en `backfill_cuenta` y `backfill_anuncios` para que un fallo tardío no rehaga lo terminado; el reinicio
  de una copia posterior arranca en `min(hoy-6, último día copiado)` para cubrir huecos tras una caída — menudencias reales
  de la revisión de la tarea 6 — si está mal: nada.
- **R11b.** La recopia arranca EN el último día guardado (no el siguiente) porque ese día estaba parcial cuando se copió —
  desviación del implementador aceptada — si está mal: un día de más releído.
- **R12.** `graph.paginar` lanza `ErrorGraph` si se detiene en el tope de páginas con `paging.next` todavía presente; nunca
  se escribe un tramo parcial — un tramo parcial se guardaría como completo — si está mal: una cuenta enorme falla en voz
  alta en vez de contar de menos en silencio.
- **R13.** Límites reales de Meta (código 17): el sondeo del informe crece 5→10→15…→30 s; el listado de pausados y
  `marcar_sin_estado(anuncio)` solo corren si el último listado completo tiene más de 20 h (`extra.listado_completo_en`),
  las copias de 3 h listan campañas y conjuntos (todos los estados) y solo anuncios que entregan o esperan; la primera
  copia de anuncios va del tramo más nuevo al más viejo y anota `extra.anuncios_desde` tras cada tramo, así un fallo 17
  retoma donde quedó — cada sondeo y cada listado cuentan contra el límite compartido — si está mal: un anuncio que pasa de
  pausado a archivado se ve hasta un día tarde.
- **R14.** `sync` asegura las tasas desde el día de cuenta más viejo guardado (`datos.rango`) hasta hoy, no solo desde la
  ventana de esta corrida — una primera copia repartida en varias corridas dejaba días viejos sin USD — si está mal: una
  petición más ancha a frankfurter.
- **R15.** La prioridad de las tareas `meta_rend_*` es 2 (`cola.reclamar` toma primero la más alta) — el «8» del encargo
  estaba al revés — si está mal: las copias se adelantan a Crear y a los experimentos.
- **R16.** Carril propio del worker, `lectura` (1 hilo), para `meta_rend_sincronizar`; el carril general lo excluye — una
  primera copia dura 8 a 14 min por cuenta (~1 h las siete) y en el único hilo general bloquearía lanzamientos y
  refrescos; la copia espera a Meta, casi no usa CPU (pico ~118 MB) — si está mal: un escritor más de SQLite (WAL) y ~40 MB
  de RAM mientras corre una copia.
- **R17.** Solo `tareas/meta.publicar` se frena sin Página (`refrescar` solo lee métricas); las conexiones de agencia sin
  Página también frenan al lanzar, antes de crear nada — más seguro que antes — si está mal: nada.
- **R18.** Se fusionó `origin/main` ANTES de la tarea 11 y nuestra migración pasa a ser la 0034 (`down_revision` 0033) —
  `cobros` de main es dueña de la 0033 y puede estar ya desplegada; la nuestra nunca se desplegó — si está mal: nada.
  (R29, 2026-10-09: en la segunda mezcla de main, que trajo `0034_tw_tarjetas`, la nuestra pasa a ser la 0035,
  `down_revision` 0034, y sus pendientes se renumeran a PND-190…206, después de los de main; en la tercera, a PND-192…208, R31.)
- **R19.** En `docs/pendientes.md`, E2 «Diagnosticar y recomendar» queda `decidido sin hacer` y E3 «Aplicar cambios» queda
  `bloqueado por Daniel` (cambia pauta en Meta) — así lo piden las definiciones de estado de la tabla — si está mal: solo
  cambia el estado de una fila del registro.

### Revisión final de la rama (2026-10-08)

- **R20.** «Elegir cuentas» (GET y POST) y cambiar el país son solo para administradores (403 al resto); la cuenta con la que
  LANZA otro proyecto (`ad_account_id` de su `meta.json`) cuenta como «En otro proyecto» (deshabilitada y rechazada); tope de
  20 cuentas por proyecto (`cuentas.MAX_POR_PROYECTO`) — el token de un usuario ve las cuentas de OTROS clientes y el selector
  dejaba a cualquier persona de un proyecto reclamarlas (aislamiento, spec §2.5); Daniel es admin y no pierde nada — si está
  mal: un cliente no puede elegir sus cuentas por su cuenta y lo hace un administrador.
- **R21.** Desconectar Meta, desasignar, salir del modo agencia y desconectar la agencia llaman a `cuentas.elegir(cliente,
  [])` (borra las copias y libera las cuentas) mediante `dashboard._soltar_cuentas_meta`; `/privacidad` y `/eliminar-datos`
  dicen que las métricas copiadas se borran — la política publicada promete el borrado — si está mal: hay que volver a
  copiar tras reconectar.
- **R22.** Guarda contra los límites de uso: `graph` lee `x-app-usage`, `x-business-use-case-usage` y `x-ad-account-usage`;
  75 % o más, o los códigos 4/17/32/613/8000x, ponen una pausa compartida en `kv` (`meta_rendimiento/pausa.py`, el mayor
  entre lo que Meta dice y 30 min); mientras dura, ninguna copia arranca ni la periódica encola, y una copia no arranca si hay
  una tarea que ESCRIBE en Meta pendiente o corriendo (`TIPOS_ESCRITURA_META`); el límite no sube como error de la cola; «Actualizar ahora»
  espera 30 min desde la última copia para quien no es admin — el límite es por usuario + app y colorado_forja comparte
  ambos, así que leer no puede gastar lo que necesita un lanzamiento — si está mal: los datos llegan hasta 3 h más viejos.
- **R23.** Derivar y rescatar (todo lo que produce un anuncio nuevo para lanzar) miran `meta_conexion.sin_pagina` ANTES de
  cobrar, reservar o encolar producción de pago: `acciones.ejecutar` y `derivaciones.planificar` lanzan el texto de «solo
  métricas», `acciones.pedir` deja la acción como propuesta con ese texto en el motivo (en auto no se intenta), y una
  derivación en marcha a la que se le quita la Página no encola más clones ni finales; escalar y pausar no se tocan —
  con token y sin Página se pagaba todo y `lanzar_piezas_nuevas` fallaba al final (revisión de gasto) — si está mal: nada.
- **R24.** `tasas.mapa` rellena hacia delante como mucho 4 días (fin de semana + un festivo); más allá devuelve None
  («USD no disponible») — el spec §7 prohíbe inventar tasas — si está mal: más «USD no disponible» en una caída larga del BCE
  o de frankfurter.
- **R25.** Las miniaturas de los anuncios con gasto en los últimos 30 días (pausados incluidos) se piden con `?ids=` en
  lotes de 50 durante el listado completo diario (se refrescan si tienen más de 20 h) — la revisión pidió que un anuncio
  pausado con gasto reciente no se quede sin imagen — si está mal: ~20 llamadas extra por cuenta y día.
- **R26.** `meta_rend_limpiar` también borra `meta_cuenta_dia` de más de 400 días — la skill prometía 13 meses y nada lo
  purgaba — si está mal: nada.
- **R27.** La ola de arreglos de la revisión final se parte en tres encargos más chicos (P1: copia, tasas, panel; P2: rutas,
  desconexión, privacidad, catálogo; P3: derivar/rescatar sin Página y esta documentación), con un commit por letra — el
  implementador único se atascó dos veces sin dejar commits — si está mal: más encargos.
- **R28.** `acciones.pedir` sin Página deja derivar y rescatar como propuestas con el texto de «solo métricas» en el motivo,
  en todos los modos (en auto tampoco se intenta ejecutarlas) — es más seguro que omitirlas: la persona ve que existen y por
  qué no corren — si está mal: una propuesta que la persona descarta.
- **R29.** Segunda mezcla de `origin/main` (trajo `0034_tw_tarjetas` y PND-179…189): se revisa primero la ola de arreglos y
  después se mezcla; nuestra migración pasa a ser la 0035 (`down_revision` 0034) y nuestros pendientes se renumeran a
  PND-190…206, después del máximo de main — la nuestra nunca se desplegó — si está mal: nada.
  (R31: en la tercera mezcla pasan a PND-192…208.)
- **R30.** Las copias de Meta ya no se pierden por ceder el turno: los tipos periódicos que escriben en Meta (`exp_decidir`,
  `exp_avanzar_todos`) frenan la copia solo mientras CORREN y los que dispara una persona (`exp_lanzar`, `meta_publicar`,
  `organico_publicar`) mientras están en cola o corriendo; una copia pospuesta se vuelve a encolar sola para dentro de 10
  minutos (`tareas.Continuar` con `max_intentos` opcional, conserva los 2 de la copia), como mucho 6 veces
  (`MAX_POSPOSICIONES`, el contador viaja en el payload) y después deja que la retome la periódica de 3 h; la pausa
  compartida por el límite de uso de Meta tiene un tope de 24 h; «Actualizar ahora» durante la pausa avisa «Meta pidió
  esperar: la copia sigue a las HH:MM» y no encola nada — la revisión encontró que `exp_avanzar_todos` (cada 10 min, en
  el único carril general) casi siempre estaba en cola y dejaba cuentas horas sin copiar (PND-208) — si está mal: unas
  pocas filas extra en la cola.
- **R31.** Tercera mezcla de `origin/main` (2026-10-09, lote 6C: carril de Nicho, PND-190 y PND-191 de main): el worker
  queda con cuatro carriles (crear, nicho, lectura y general) y el general excluye a los otros tres; nuestra migración sigue
  siendo la 0035 (main sigue en 0034) y nuestros pendientes se renumeran otra vez, de PND-190…206 a PND-192…208 (+2),
  después del máximo de main — si está mal: nada.

## Hechos medidos contra la API real de Meta

Corridas contra la API real de Meta (cuentas de happyflops, todas en SEK), con la copia sobre una base temporal en el VPS, al cerrar la tarea 6:

- **Noruega, primera copia: 490 s y 116 MB de pico de memoria (RSS).** 396 días de cuenta, 23 860 filas de anuncio-día,
  14 823 objetos (anuncios: 7 148 `ADSET_PAUSED`, 1 914 `CAMPAIGN_PAUSED`, 1 795 `PAUSED`, 581 `ACTIVE`, 415 `WITH_ISSUES`,
  1 `DISAPPROVED`), 997 miniaturas, 24 filas de alcance y 283 tasas.
- **Cuadre de totales (Noruega, 30 días):** la cuenta suma 1 337 490 SEK y los anuncios 1 337 704 SEK (214 SEK, 0,016 %);
  las compras son 3 861 en ambos. Alcance de 30 días 1 148 105 personas, frecuencia 10,7.
- **Holanda, primera copia: 824 s, 53 442 filas de anuncio-día, 14 571 objetos y 118 MB de pico.** A 30 días la cuenta y los
  anuncios cuadran en 2 389 727 SEK y 7 562 compras; 161 de 256 conjuntos activos están en aprendizaje limitado (`FAIL`).
- **Copia incremental (7 días): ~110 s** en Noruega (115 s con el listado completo, 106 s con el ligero), 2 015 filas de
  anuncio, pico 115 MB; los totales siguen cuadrando.
- **Código 17 («user request limit»): una segunda corrida inmediata lo dispara.** Pasó en Noruega y en Holanda. El
  presupuesto es del USUARIO + la APP, y colorado_forja usa el mismo usuario y la misma app (Forja Ads) para sus
  experimentos: leer puede quitarle cupo a un lanzamiento. De ahí R13 (reanudable), R22 (pausa compartida) y que las siete
  primeras copias de producción se repartan en varios ciclos de 3 h (~1 h de trabajo en total).
- **«Please reduce the amount of data» (código 1) con `limit=500` y los campos de `creative{}`** en el listado de anuncios:
  Meta lo rechaza de verdad. De ahí R8 (partir el límite en mitades, empezar en 100).
- **El filtro de campañas con `CAMPAIGN_PAUSED`/`ADSET_PAUSED` lo acepta Meta** (213 campañas pausadas + 4 activas y 2 660
  conjuntos listados en Noruega). De ahí R10.
- **Estados raros vistos en anuncios:** `ARCHIVED` (7) y sin estado (47): ambos tienen etiqueta en el panel.
