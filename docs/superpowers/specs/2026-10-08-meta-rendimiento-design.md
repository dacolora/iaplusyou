# Meta: rendimiento de todas las cuentas, diagnóstico y recomendaciones

Fecha: 2026-10-08. Pedido de Daniel: «necesitamos que nuestra conexión a Meta sea la mejor… con happy flops cubrir
todas sus necesidades y, al igual que con Triple Whale, darle las mejores recomendaciones, los mejores diagnósticos y
proponerles cambios para mejorar sus ads». Antes, en la misma conversación: «lo que sí necesito es que ya aparezcan
todas esas métricas» (las 7 cuentas del Business de HappyFlops).

## 1. Lo que hay hoy y lo que falta

- Creatv solo lee de Meta las métricas de **sus propios experimentos** (`meta_detalle.py` filtra por la campaña del
  experimento; `tablero.py` sale de `metrica_snapshot`). No lee una cuenta publicitaria entera.
- La conexión (`meta_conexion.py`, modo propia) guarda **una** cuenta y **exige una Página** (`dashboard.meta_elegir`).
- happyflops no tiene ninguna conexión de Meta en producción.
- Prueba de lectura del 2026-10-08 con el token de usuario de Daniel (ForjaPlayer Habit, app Forja Ads, acceso
  parcial al portafolio HappyFlops 1213264469286406): `me/adaccounts` trae las 7 cuentas y `act_…/insights` responde.
  Ninguna Página de HappyFlops está asignada a Daniel.

Datos reales (30 días al 2026-10-08, todas en SEK, zona Europe/Stockholm, todas `OUTCOME_SALES`):

| Cuenta | id | Gasto 30 d | ROAS | Activos (camp · conj · anuncios) | Conjuntos «aprendizaje limitado» |
|---|---|---|---|---|---|
| HappyFlops Netherlands (Active) | 883891256188845 | 2 422 570 | 2,20 | 8 · 257 · 1 050 | 151 |
| HappyFlops Norway | 709406360806038 | 1 380 524 | 2,24 | 4 · 93 · 584 | 50 |
| HappyFlops Sweden | 5728901877226252 | 987 886 | 2,20 | 6 · 110 · 659 | 50 |
| HappyFlops Finland 2025 | 335308812712423 | 130 766 | 1,97 | 2 · 141 · 643 | 107 |
| HappyFlops Poland (old DK) | 1236343913931133 | 125 582 | 1,83 | 1 · 62 · 312 | 38 |
| HappyFlops World Wide | 708698354181244 | 56 304 | 0,22 | nada activo | — |
| HappyFlops MX | 228061763662782 | 0 | — | nada activo | — |

~9 600 anuncios con datos en 90 días. El volumen manda el diseño de la copia (§6).

## 2. Decisiones (rulings)

1. **Métricas** (Daniel): las del Business + ventas; ampliado por el segundo pedido a campaña, conjunto y anuncio,
   porque sin el anuncio no hay diagnóstico.
2. **Moneda** (Daniel): cada cuenta en su moneda; «Todas» en USD con la tasa diaria del BCE. Sin tasa, «USD no
   disponible», nunca una inventada. Si todas las cuentas elegidas comparten moneda, también se muestra el total
   exacto en esa moneda (hoy SEK).
3. **App**: happyflops usa la app Forja Ads (la de Daniel, Live). Su registro se copia en el VPS desde colorado_forja
   (`meta_conexion.guardar_app`), sin imprimir el secreto.
4. **La Página pasa a ser opcional al conectar.** Sin Página el proyecto queda «solo métricas»: lanzar un experimento,
   publicar en orgánico o el flujo viejo frenan con un mensaje en palabras antes de llamar a Meta.
5. **Cuentas que el proyecto lee**: lista propia (`meta_cuenta`), aparte de la cuenta única de `meta.json` con la que
   se lanza. Una cuenta publicitaria solo puede estar en un proyecto (índice único): los datos de un cliente nunca
   aparecen en otro.
6. **Lectura con token explícito**: `meta_rendimiento/graph.py` llama a Graph con el token y la cuenta como argumentos;
   no toca el estado global de `meta_ads.auth` ni sus candados (siete cuentas en un hilo del worker no deben bloquear al
   lanzador).
7. **Pestaña nueva «Meta»** después de «Triple Whale», por fetch al abrirse. No va dentro de Experimentos: otra
   conversación está cambiando `_tab_experimentos.html` (rama `exp-sin-meta`).
8. **El veredicto por anuncio reutiliza `triple_whale/evaluacion.py`** (puro, contra las medianas de la cuenta y las
   reglas del decisor del proyecto). Las compras y el valor salen del Píxel de Meta (`omni_purchase`), no de Triple Whale.
9. **Entregas**: E1 «Ver todo» y E2 «Diagnosticar y recomendar» se construyen ahora; E3 «Aplicar cambios» (pausar,
   activar, mover presupuesto en las cuentas del cliente) **se le pregunta a Daniel antes de construir**: toca su plata y
   sus anuncios vivos.
10. **Modo agencia**: fuera. El selector de cuentas lista lo que ve el token del proyecto (`listar_activos`); en un
    proyecto agencia la sección dice que todavía no está disponible.

## 3. Arquitectura

Paquete `meta_rendimiento/` (no `meta_ads/`, que es el submódulo, ni `meta_detalle.py`, que es de experimentos):

| Módulo | Hace | Depende de |
|---|---|---|
| `cuentas.py` | único escritor de `meta_cuenta`: elegir, quitar, cambiar país, adivinar país, marcar estado de copia | `db`, `triple_whale.paises` |
| `graph.py` | GET con token explícito, paginación, informes asíncronos de insights, errores de Meta en palabras | `requests`, `meta_errores` |
| `sync.py` | copia de una cuenta: objetos, días de cuenta, días de anuncio, alcance por ventana (E2: desgloses) | `graph`, `datos`, `tasas` |
| `datos.py` | único escritor de las tablas de copia; lecturas agregadas para la pestaña | `db` |
| `tasas.py` | tasas USD por día del BCE (frankfurter.app) con caché en `tasa_cambio` | `conectores.url` |
| `panel.py` | contexto de la pestaña (puro sobre `datos`) | `datos`, `tasas`, `triple_whale.evaluacion` |
| `rutas.py` | blueprint: pestaña, elegir cuentas, actualizar ahora (E2: evaluar, recomendaciones) | todo lo anterior |
| `recomendaciones.py` (E2) | reglas puras de cuenta/campaña/conjunto/anuncio | `datos` |
| `analisis.py` (E2) | evaluación con IA | `triple_whale.analisis` (reusa medios, miniaturas, visuales), `doctrina` |
| `avisos.py` (E2) | correo tras la copia: ganadores, fatiga, rechazados, cuenta con problemas | `notificaciones` |
| `tareas/meta_rendimiento.py` | tareas del worker | `sync`, `analisis` |

## 4. Datos (migración 0033)

- `meta_cuenta`: id, cliente, ad_account_id (`act_…`, **único global**), nombre, moneda, zona_horaria, pais (ISO-2 o
  NULL), estado (`ok|copiando|error`), error, ultima_copia, extra (JSON: `backfill_hecho`, `cuenta` = account_status,
  disable_reason, amount_spent, spend_cap), agregada_en, agregada_por. Índice (cliente).
- `meta_cuenta_dia`: cliente, ad_account_id, fecha (texto `AAAA-MM-DD`, zona de la cuenta), gasto, impresiones,
  alcance, clics, clics_salida, compras, valor, vistas_3s, thruplays, actualizado_en. UQ (cliente, ad_account_id, fecha).
  13 meses.
- `meta_anuncio_dia`: cliente, ad_account_id, fecha, campaign_id, adset_id, ad_id, gasto, impresiones, clics,
  clics_salida, compras, valor, vistas_3s, thruplays, p25, p50, p75, p100, actualizado_en. UQ (cliente, ad_account_id,
  ad_id, fecha); índice (cliente, ad_account_id, fecha). 90 días (el mantenimiento diario borra lo anterior).
- `meta_objeto`: cliente, ad_account_id, nivel (`campana|conjunto|anuncio`), objeto_id, padre_id, nombre, estado
  (`effective_status`), objetivo, optimizacion, presupuesto_diario, presupuesto_total (en la moneda de la cuenta, ya
  dividido entre 100), estrategia_puja, aprendizaje (`learning_stage_info.status`), creative_id, miniatura_url,
  video_id, destino_url, creado_en_meta, actualizado_en, extra (JSON). UQ (cliente, objeto_id).
- `meta_alcance`: cliente, ad_account_id, nivel (`cuenta|campana`), objeto_id, ventana (`7|14|30|90`), alcance,
  frecuencia, calculado_en. UQ (cliente, objeto_id, ventana). El alcance es gente única: no se suma por días.
- `tasa_cambio`: fecha, moneda, usd_por_unidad, fuente. UQ (fecha, moneda).
- E2: `meta_desglose` (cliente, ad_account_id, ventana, dimension, clave, gasto, impresiones, clics, compras, valor,
  calculado_en; UQ (cliente, ad_account_id, ventana, dimension, clave)) y `meta_evaluacion` (como `tw_evaluacion`:
  cliente, alcance (cuentas), desde, hasta, moneda, estado, resultado JSON, usd, pedido_por, creada_en, extra).

Las compras: el primer tipo presente de `("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")` en
`actions`/`action_values` (el mismo orden que `meta_ads/insights.obtener_resultados`). Clics de salida:
`outbound_clicks[outbound_click]`, y si falta, `inline_link_clicks`. Vistas de 3 s: `actions[video_view]`.

## 5. Conexión

- `meta_elegir`: la Página deja de ser obligatoria. Sin Página guarda `page_id=None` y el aviso dice «Conectado solo
  para métricas: sin Página no se pueden lanzar anuncios ni publicar». La plantilla `meta_elegir.html` ofrece «Sin
  Página (solo métricas)».
- `lanzador` (al lanzar), `organico` y `tareas/meta.publicar`: si `credenciales_ads(c)["page_id"]` es None, error en
  palabras antes de llamar a Meta y sin cobrar nada (no cobran, pero no deben dejar filas a medias).
- La tarjeta de Meta en Configuración › Conexiones muestra «Solo métricas» cuando no hay Página y un enlace a la
  pestaña Meta.
- En la pestaña Meta, «Elegir cuentas»: casillas con `listar_activos(token)["ad_accounts"]` (nombre, id, moneda,
  estado), el país adivinado y editable (`triple_whale.paises`, por nombre: Norway → NO, Netherlands → NL, Sweden → SE,
  Finland → FI, MX → MX, Poland → PL; World Wide → sin país). Guardar encola la copia de las nuevas. Quitar una cuenta
  borra sus copias (nunca las evaluaciones pagadas).

## 6. Copia

Tarea `meta_rend_sincronizar` (una por cuenta, `job_id = f"{cliente}__meta_rend__{ad_account_id}"`, `max_intentos=2`:
leer de Meta no cobra). Periódica `meta_rend_sincronizar_todas` cada 3 h en `worker.PERIODICAS`.

1. Cuenta: `act_X?fields=name,currency,timezone_name,account_status,disable_reason,amount_spent,spend_cap`.
2. Objetos: campañas, conjuntos y anuncios con `effective_status` en ACTIVE, PAUSED, CAMPAIGN_PAUSED, ADSET_PAUSED,
   WITH_ISSUES, DISAPPROVED, PENDING_REVIEW, IN_PROCESS (paginados de 500; anuncios con `creative{id,thumbnail_url,
   video_id,object_story_spec,asset_feed_spec}` solo para extraer miniatura, video y destino).
3. Días de cuenta: `level=account, time_increment=1`; la primera vez 13 meses (por tramos de 90 días), después los
   últimos 7.
4. Días de anuncio: informe asíncrono (`POST act_X/insights` con `level=ad, time_increment=1`, sondeo de
   `report_run_id` hasta `Job Completed`, máximo 10 min, luego `GET …/insights` paginado de 500). La primera vez 90
   días por tramos de 30; después los últimos 7. `datos.reemplazar_anuncios(cliente, act, desde, hasta, filas)` borra el
   tramo y escribe en una transacción, como Triple Whale.
5. Alcance: `level=account` y `level=campaign` (solo las campañas con gasto en 90 días) para `last_7d`, `last_14d`,
   `last_30d`, `last_90d`.
6. Tasas: `tasas.asegurar(monedas, desde, hasta)`.

Errores: un límite de Meta (códigos 4, 17, 32, 613, 80000–80014) deja la cuenta en `error` con el texto «Meta pidió
esperar» y la próxima pasada periódica reintenta; un token roto (190, 102, 10, 200) marca la cuenta en error con
«Reconecta Meta». Nunca un token en `error`, eventos ni registros (`cola.sin_token`).

## 7. Monedas

`tasas.usd(moneda, fecha)`: USD por unidad; para un día sin publicación del BCE (fin de semana, festivo) usa el último
día publicado anterior. `tasas.asegurar` pide `https://api.frankfurter.app/<desde>..<hasta>?from=<M>&to=USD` con
`conectores.url.abrir` y guarda lo que llega. USD → 1,0 sin pedir. Sin tasa: el total en USD del período dice «USD no
disponible» y la tarjeta muestra el total por moneda.

## 8. Pantalla (pestaña «Meta»)

Plantilla `_tab_meta.html` (shell + fetch) y `_meta_panel.html` (panel), estilo de la base visual común. Arriba:
selector «Todas | <cuenta> …» (con país) y período 7/14/30/90 días (por defecto 30); «Actualizar ahora» con barra
`data-poll-job`; «Última copia hace …».

1. KPIs con su variación contra el período anterior: gasto, valor de compras, ROAS, compras, costo por compra,
   alcance (suma de cuentas en «Todas»), impresiones, CPM, CTR de salida. En «Todas», montos en USD; en una cuenta, en
   su moneda.
2. Gráfico diario gasto contra valor (`app.extensions["grafico_tablero"]`).
3. Tabla de cuentas (como la tarjeta del Business): gasto, ROAS, compras, alcance, impresiones, activos y conjuntos
   en aprendizaje limitado; clic → elige esa cuenta.
4. Campañas del período (orden por gasto): estado, objetivo, presupuesto, gasto, ROAS, compras, CPA, alcance.
5. Conjuntos (top 24 por gasto, «Ver más» por fetch): estado, aprendizaje, presupuesto, gasto, ROAS, CPA, frecuencia.
6. Anuncios (top 24 por gasto, «Ver más»): miniatura (`loading="lazy"`), veredicto, problemas y fortalezas de
   `triple_whale.evaluacion` (sin `sin_rastreo`), gasto, ROAS, CTR, gancho, retención.

Nada de una consulta por tarjeta: cada lista es una consulta agregada. La copia vive en la base; abrir la pestaña no
llama a Meta.

## 9. E2: diagnosticar y recomendar

`recomendaciones.py` (puro, gratis, se calcula al abrir la sección) devuelve `[{nivel: alta|media|baja, tipo,
objetos, que_hacer, por_que, impacto}]`, en palabras y con los números que lo sostienen:

- **Aprendizaje limitado**: conjuntos activos con `aprendizaje == FAIL` y su gasto; propone consolidar en menos
  conjuntos con más presupuesto (Meta necesita ~50 conversiones por semana por conjunto).
- **Gasto en perdedores**: anuncios con veredicto `perdedor` y su gasto del período; propone pausarlos y cuánto se
  ahorra por día.
- **Ganadores con poco presupuesto**: veredicto `ganador` con menos gasto que la mediana de su conjunto; propone subir
  de a 20 % (más reinicia el aprendizaje).
- **Fatiga**: `fatiga` de la evaluación + frecuencia de 7 días ≥ 3; propone variantes del ganador (→ Crear).
- **Rechazados y con problemas**: anuncios `DISAPPROVED`/`WITH_ISSUES` y lo que gastaban antes.
- **Cuenta**: `account_status` distinto de 1, `spend_cap` a menos de 10 % de agotarse, cuenta con gasto y ROAS < 0,5
  (hoy World Wide), cuentas sin nada activo.
- **Segmentos caros** (con `meta_desglose`): edad, género, ubicación, país o dispositivo con ≥ 10 % del gasto y ROAS < la
  mitad del de la cuenta.
- **Concentración**: un anuncio con ≥ 60 % del gasto de su conjunto (dependencia de un creativo).

`meta_desglose` se copia una vez al día (ventanas 7 y 30, dimensiones edad+género, `publisher_platform+
platform_position`, `country`, `impression_device`), dentro de la misma tarea cuando la última tiene más de 20 h.

**«Evaluar con IA»** (tarea `meta_rend_evaluar`, `max_intentos=1`, precio `gastos.estimar("evaluacion_meta", n=)`
mostrado antes del clic, gasto real con `gastos.registrar_seguro(cliente, "evaluacion", usd, f"meta_eval:{id}:t{tarea}")`
también si falla después de pagar): manda a Claude el resumen de las cuentas elegidas, las recomendaciones de las
reglas, hasta 6 ganadores y 4 perdedores con su miniatura (reusa `triple_whale.analisis.medios_meta`,
`copiar_miniaturas`, `visuales`), los desgloses destacados y las rebanadas de doctrina `clasificar`, `angulo`, `gancho`,
`video`, en el idioma del proyecto. Devuelve diagnóstico, plan de cambios priorizado (cada uno con objeto, acción e
impacto esperado), patrones de los ganadores y 3–5 ideas de anuncio con ángulo validado y prompt de video en inglés
(«Llevar a Crear» con `triple_whale/puente.py`). Medido con `eval-claude` antes de darlo por bueno.

**Avisos** (correo, tipo `meta_rendimiento`): tras cada copia, una vez por novedad (estado en `meta_cuenta.extra`):
ganador nuevo, ganador cansándose, anuncio rechazado, cuenta con problema, spend cap por agotarse. La primera copia
solo siembra la línea base.

## 10. E3: aplicar cambios (no se construye sin el sí de Daniel)

Botones en cada recomendación: «Pausar», «Activar», «Subir presupuesto 20 %», con confirmación que muestra el cambio y
el gasto diario resultante, tarea `max_intentos=1`, bitácora y nada automático. Necesita el permiso «Administrar
campañas» que Daniel ya tiene. Preguntas abiertas: ¿quién puede aplicar (solo admin, o el cliente)? ¿se avisa a
HappyFlops de cada cambio?

## 11. Seguridad

POST con `_solo_mismo_origen`; cada ruta valida `cliente` y que la cuenta pertenezca al proyecto; las tareas llevan
`cliente`; la URL del BCE por `conectores.url.abrir`; miniaturas copiadas a R2 antes de mostrarlas o mandarlas a
Claude (E2); nombres de campañas y anuncios (texto ajeno) se escapan en plantillas y van entre etiquetas como DATOS en
el prompt de Claude (E2), nunca como instrucciones.

## 12. Pruebas

Graph con dobles (sin red): paginación, informe asíncrono (en curso → completado → fallido), límites, token roto,
tipos de compra; `datos.reemplazar_*` idempotente; `tasas` con fin de semana y sin tasa; `panel` con «Todas» en USD,
una cuenta, sin datos; rutas (mismo origen, cuenta de otro proyecto → 404, proyecto sin Meta); `meta_elegir` sin
Página; lanzador y orgánico frenan sin Página; migración 0033 en una copia. E2: cada regla de recomendaciones con su
caso; análisis con Claude doble; avisos una sola vez. Prueba real con la cuenta de Norway antes de desplegar y captura
de la pestaña.

## 13. Fuera de alcance y pendientes

- PND-148 (lanzar en varias cuentas por país) sigue abierto; con Página asignada y E1 hecho, es el siguiente paso.
- Modo agencia en la pestaña Meta.
- Renombrar la app Forja Ads a un nombre neutro (lo que ven los admins de HappyFlops al revisar integraciones).
- El token de usuario dura ~60 días y el acceso a datos 90: la pestaña avisa a 10 días de caducar (reusa
  `meta_conexion.estado`).
