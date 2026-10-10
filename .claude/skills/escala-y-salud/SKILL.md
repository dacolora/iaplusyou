---
name: escala-y-salud
description: "Escala y salud: rendimiento con muchos usuarios (lecturas memorizadas por petición, índices, pool de la base, gunicorn y nginx del repo, caché de R2) y el monitoreo (/admin/salud, monitoreo.py, tabla error_app, registros en data/logs). Cargar antes de agregar una ruta GET que pinta muchas tarjetas, una consulta sobre una tabla que crece, tocar db.py, deploy/, monitoreo.py o registro_app.py, o investigar un error de producción."
---

# Escala y salud: rendimiento con muchos usuarios, índices y monitoreo

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Escala y salud** (spec `docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md`, pedido de Daniel:
muchos usuarios a la vez y enterarse de todos los errores). Medido con datos sembrados
(`rendimiento/sembrar.py`, nunca en producción) y una prueba de carga de 100 personas (`rendimiento/locustfile.py`;
guía en `rendimiento/README.md`). Lo que salió de medir, y las reglas que deja: las rutas GET que pintan muchas
tarjetas llevan `@trabajos.con_vivos_precargados` Y `@catalogo_productos.con_lecturas_memorizadas` (dentro, las
búsquedas `encontrar*` leen el catálogo del disco UNA vez por petición y devuelven copias; fuera —rutas que escriben, el
worker— todo igual; siempre a través de `listar()`/`listar_productos()`, que las pruebas sustituyen): «Ver más» de Crear
hacía 1 077 consultas y la página del proyecto escaneaba el catálogo dos veces por tarjeta (1 s → 0,2 s con 300 piezas
y 25 productos). Otra lectura de solo mirar que se repita por tarjeta va por `catalogo_productos.recordado(clave, leer)`
(así `final_edition._fila_producto` lee `tiendas.por_activo` una vez por petición). `_ctx_items_cf` calcula una vez lo que es igual en todas las tarjetas (`hijas_b`, `precio_revision`).
`idiomas.numero` reusa el `Locale` y el patrón de Babel ya analizados, y `idiomas.instalar_gettext_rapido` recuerda el
catálogo de traducciones por petición (junto al objeto `babel_locale`, así `force_locale` sigue mandando).
`usuarios.obtener` recuerda `usuarios.json` mientras su firma (inodo, mtime_ns, tamaño) no cambie y como mucho 2 s.
Índices: `rendimiento/auditar_indices.py` (plugin de pytest, `EXPLAIN QUERY PLAN` de cada consulta de la app) → migración
0026 (`pieza.padre_pieza_id`, `publicacion.pieza_id`, `metrica_snapshot(experimento_pieza_id, tomado_en)`,
`gasto.creado_en`, las claves foráneas que borrar recorría enteras…), vigilados por `tests/test_indices_escala.py`; una
consulta nueva sobre una tabla que crece debe usar índice. `experimentos.snapshots_de(ids, desde)` = `snapshots` de
muchas piezas en 2 consultas (panel del admin y, desde el centro de resultados de E2, 2026-10-03, `tablero._piezas_con_snapshots`: antes una o dos consultas por pieza, hoy dos para todas). El fragmento de resultados (`exp_resultados`, `resultados.contexto`) no agrega consultas por pieza: lee `metrica_dia` y `metrica_desglose` con UNA consulta por tabla (ids por trozos de 500) y `promedio_embudo` con una; `experimentos.cargar` lee las últimas métricas en una consulta conjunta (PND-134, 2026-10-07), con subconsulta de último id por pieza y sin índice nuevo. La prueba mide el número de consultas, no la latencia de producción. `tests/test_rutas_resultados.py::test_el_fragmento_no_hace_mas_consultas_por_pieza_que_experimentos_cargar` exige conteo constante con 3 y 15 piezas. `ver_cliente` entrega solo reglas y correo para el armazón, y cuenta vivos sin cargar piezas (PND-137, 2026-10-07); el fragmento y Nuevo conservan el contexto completo. Pool explícito (`db.opciones_pool`: `CREATV_DB_POOL` 10 +
`CREATV_DB_POOL_EXTRA` 10, ≥ hilos de gunicorn) y `temp_store=MEMORY`. **gunicorn se configura en el repo**
(`deploy/gunicorn.conf.py`, unidad de ejemplo `deploy/iaplusyou.service`): UN proceso a propósito —`trabajos.iniciar`,
`_TRABAJOS` y los cachés viven en su memoria; para usar más procesos primero hay que mover esos trabajos a la cola—,
16 hilos, nunca `max_requests`. `deploy/nginx-creatv.conf`: estáticos desde el disco con las mismas cabeceras, gzip,
tope al POST de `/login`, Cloudflare delante (IP real por `CF-Connecting-IP`). R2: `r2_uploader.cache_control(key)` da
caché de un año («immutable») SOLO a claves que nunca se reescriben (finales `__v<id>`, materiales con hash); el resto,
como antes. **Salud** (`/admin/salud`, `monitoreo.py`): tabla `error_app` (migración 0027, único escritor `monitoreo`)
con un error por huella (origen web|worker|hilo|log + tipo + `archivo:línea función()` más adentro de la app + ruta), veces,
primera/última, traza de la última —todo por `monitoreo.limpiar_texto` (tokens, Bearer, `sk-…`, `password=`…)—, estado
`abierto|resuelto|silenciado` (un resuelto que vuelve se reabre y avisa; correo a los admins vía `avisar_admin`
«error_app», como mucho 10/h). Lo alimentan `got_request_exception` (rutas), `worker._correr` (por tipo de tarea),
`trabajos.iniciar` (por la acción del job_id, dígitos → N) y todo `log.error`/`log.exception` de la app
(`registro_app._AErrores`, por logger + plantilla del mensaje); un `log.error` de algo ya registrado lleva
`extra={"sin_monitoreo": True}` o `registro_app.marcar_registrada(exc)`. Nunca lanza, y en las pruebas no guarda nada
salvo `CREATV_MONITOREO_EN_PRUEBAS=1`. `monitoreo.METRICAS` (en memoria del proceso web): por ruta n, 5xx, p50/p95
aproximados, consultas por petición; peticiones por minuto; las lentas (> 1 s); en curso. `monitoreo.sistema()/
cola_salud()/avisos()`: base y WAL, disco, memoria, carga, pool, worker atrasado, respaldo, r2.dev, SMTP, proxy.
`registro_app.configurar("web"|"worker")` (dashboard al importarse fuera de pytest, worker en `main`): `data/logs/
<proceso>.log` rotando (5 MB × 5), los `print` copiados línea por línea («[aviso]» = WARNING), leído en
`/admin/salud/registros`. `/salud` (público, sin sesión): `{"ok": true}` 200 o 503, para un monitor externo.

PND-090/136 (2026-10-07, lote 5 B): referentes.datos.por_ids evita una consulta por candidato en ambas vistas de Sprints; exp_pieza usa los memos existentes por petición (experimentos, catálogo y trabajos). La gestión de resultados completa solo el experimento elegido, conservando todos los datos del centro y las propuestas globales cuando no hay filtro. Las pruebas miden lecturas/valores, no prometen latencia real.

PND-062, entrega 1 (2026-10-10, pedido de Daniel: bajar el HTML inicial): `ver_cliente` ya no arma
`_productos_con_uso` ni `activos_por_categoria` para selectores ocultos. Mantiene contadores y el enlace comercial
histórico, y resuelve solo lo preseleccionado. `_pagina_swaps` corta antes de enriquecer nombres; la ruta tiene
precarga de vivos y memo del catálogo. Gasto pide 25 filas en SQL, entrega 24 y usa la extra para Ver más;
`desplazamiento` es OFFSET, mientras `desde` sigue siendo la fecha ISO. Los tres fragmentos omiten el chip del
sidebar incluso sin cabecera fetch. `tests/test_pagina_por_partes.py` vigila lecturas, HTML y tamaño con datos temporales.

Enmiendas PND-062, entrega 1 (2026-10-10, pedido de Daniel tras revisar la entrega): n_activos_por_categoria cuenta referencias con fotos desde las fichas ya leídas: cada color cuenta uno; los productos archivados no cuentan. n_por_categoria conserva las filas comerciales de Catálogo. La prueba de contexto rechaza listar directo en ver_cliente y lecturas planas adicionales para selectores ocultos.
