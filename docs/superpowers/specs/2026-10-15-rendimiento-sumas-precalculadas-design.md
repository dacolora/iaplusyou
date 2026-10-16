# Rendimiento: sumas precalculadas y un año de historia (2026-10-15)

## 1. Pedido y motivo

Daniel (2026-10-15) pidió periodos de 15 días, un mes, 3, 6 y 12 meses, traer un año de historia de Triple Whale y
«vamos con todas las etapas». Medido el mismo día:

- Con las 5 tiendas de happyflops (288 000 filas en `tw_anuncio_dia`, 90 días) «Todas, desde el inicio» tardaba 24 s en
  el VPS después del arreglo del gasto duplicado, y 9 a 13 s un país. Las etapas 1 y 2 (periodos y consultas sin
  agrupar) lo bajan a la mitad o un tercio, pero queda: 7 u 8 sumas sobre la copia entera (1–2,5 s cada una:
  `totales_por_anuncio`, `cohortes`, `serie_tienda`, `gasto_por_antiguedad`, `gasto_por_canal`, `gasto_duplicado`,
  `totales_por_grupo`, `visitantes_por`) y unos 3–4 s de Python (veredictos, «Resultados»).
- Un año son ~4 veces más filas: cada suma crece igual. «Todas» pasaría de un minuto.
- Probado: leer la tabla sin el índice no cambia nada (0,8 s contra 1 s): el costo es la cantidad, no el plan.

## 2. Decisión

**Las sumas pesadas se calculan en el worker después de cada copia de Triple Whale y se guardan comprimidas en la
base; la pestaña las lee cuando son de la misma versión de los datos y si no, calcula en el momento como hoy.**

Descartado:
- Totales por semana o por mes en otra tabla: «Resultados» necesita cada día (anuncios nuevos contra establecidos, por
  canal, por mes de arranque) y el detalle por anuncio; habría que reescribir casi cada lectura.
- Guardar en la memoria del proceso web: «Todas» son ~50 MB de resultados y el VPS tiene 2 GB (incidente OOM del
  2026-09-30); además se perdería en cada reinicio.
- Guardar la pantalla armada: los veredictos y la lectura de «Resultados» salen en el idioma de quien mira. Se guardan
  solo las sumas (sin idioma); Python arma en el momento.

## 3. Cómo funciona

- **Tabla `tw_memo`** (migración 0041): `cliente`, `clave` (sha256 del nombre de la función y sus argumentos),
  `version`, `datos` (JSON comprimido con zlib), `creado_en`; única por (cliente, clave). Único escritor:
  `triple_whale/memo.py`.
- **Versión de los datos** (`memo.version(cliente)`): la última sincronización de cada tienda del proyecto, la moneda,
  el modelo y la ventana. Cambia con cualquier copia nueva, con un cambio de ajustes o al quitar o agregar una tienda.
- **Las funciones pesadas de `triple_whale/datos.py`** se envuelven con `@memo.precalculable`: si hay un resultado
  guardado con la clave de esos argumentos y la versión de hoy, lo devuelven; si no, consultan como siempre. Solo leen
  la tabla; nunca escriben desde una petición web.
- **Tarea `tw_precalcular`** (worker, gratis, `job_id` `<cliente>__tw_precalcular`, exenta de Cobros): corre la pestaña
  (`pestana_rendimiento.panel.contexto`) para «Todas» y cada país con todos los periodos y sin canal, en modo «grabar»:
  cada función envuelta guarda lo que calculó con la versión del momento. Al final borra lo de versiones viejas. Se
  encola al terminar cada `tw_sincronizar` (un segundo encolado con el mismo `job_id` no lanza otra).
- **Frescura**: el periodo termina hoy, así que los argumentos llevan la fecha; un resultado de ayer nunca se usa. Si
  una copia termina mientras se precalcula, lo grabado lleva la versión vieja y no se usa: se calcula en vivo hasta la
  próxima vuelta.
- **Lo que no se guarda**: con un canal elegido, el detalle de un día, lo que depende de la persona o de lo que corre
  (análisis pagados, trabajos vivos, precios, piezas de Creatv) y todo lo de Meta.

## 4. Un año de historia

`triple_whale.sync.sincronizar` acepta un `desde` explícito; una tarea `tw_sincronizar` con `{"desde": hoy − 364}` copia
el año hacia atrás por tramos de 7 días, como la primera copia (gratis; ~4 veces la primera copia de 90 días, una tienda
a la vez). `rango_pendiente` ya no la recorta. Se corre una vez por tienda de happyflops después de desplegar el
precálculo; su `backfill_desde` queda en la fecha más vieja copiada.

## 5. Escala y riesgos

- La base crece ~550 MB con el año de happyflops (de ~265 a ~800 MB) y la tabla `tw_memo` ~60 MB. Hay 23 GB libres; los
  7 respaldos diarios pasan a ~6 GB.
- El precálculo corre ~42 veces la pestaña cada 2 h en el worker (minutos de CPU). Va en el carril de lectura (un hilo,
  el de las copias de Meta), así no compite con Crear ni con los lanzamientos.

## 6. Pruebas

- Lo guardado da exactamente lo mismo que lo calculado en vivo (ida y vuelta por JSON de cada función envuelta).
- Versión vieja, otro proyecto u otros argumentos: se calcula en vivo.
- La web nunca escribe en `tw_memo`.
- Con el precálculo listo, el panel hace menos consultas y ninguna de las sumas pesadas.
- `tw_precalcular` se encola al terminar una copia y no se encola dos veces; no cobra.
- Medición antes y después con la copia de producción y con un año simulado.
