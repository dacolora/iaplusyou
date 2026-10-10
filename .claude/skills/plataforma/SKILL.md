---
name: plataforma
description: "Plataforma de Creatv por dentro: carpetas por proyecto (clientes/<cliente>/), estado en JSON y en data/creatv.db, trabajos en segundo plano y el worker (trabajos.encolar, cola, carriles, job_id, Continuar, hilos), R2, el gasto real (gastos.registrar_seguro, gastos.estimar), el wrapper viejo de Higgsfield (solo CLI). Cargar antes de crear o cambiar una tarea del worker, tocar trabajos.py, cola.py, worker.py, gastos.py, _json_store.py o estado.py, o agregar algo que cobre a un proveedor."
---

# Plataforma: proyectos, estado, trabajos en segundo plano y gasto

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

## El principio

Cada paso caro o público necesita aprobación humana con el precio a la vista. No se avanza automáticamente entre pasos pagados.

**Multi-tenant via folders.** Each "proyecto" is a directory under `clientes/<nombre>/`
(the UI now says "Proyectos" but the folder name, route param, and Python variable
`cliente` were deliberately left as-is during that rename — only user-facing text
changed, to avoid touching the working state-machine/background-job logic). Layout:

```
clientes/<cliente>/
  personajes/          # character reference images/videos (+ .frame.jpg for videos)
  marca/                # brand reference images/videos, same convention
  marca.json            # guía de estilo (text) injected into every prompt generation
  prompts_pendientes.json  # ideas -> nested prompts, mid-pipeline state
  estado_videos.json    # generated videos awaiting/past final approval
  .env                   # per-client secrets (Meta page tokens), layered over root .env
  token_youtube.json, token_tiktok.json   # per-client OAuth tokens
```

Credentials layer in two tiers: the root `.env` (shared: Higgsfield, R2, Anthropic,
Meta app id/secret, TikTok client key/secret) loaded once at startup, then
`clientes/<cliente>/.env` loaded with `override=True` right before an action needs
per-client secrets (see `_cargar_entorno_cliente` in `dashboard.py`). Because this
mutates process-wide `os.environ` and publish now runs on a background thread,
`_ENV_LOCK` serializes that load-then-use section so two clients' publish jobs can't
clobber each other's credentials mid-flight.

**Estado histórico** (`estado.py`, `marca.py`, `conceptos_imagen.py`): conserva los videos, imágenes y conceptos existentes; no se borran JSON ni archivos al retirar productores. `creative_flow.py` and `ads.py` present the same read/write API
but now persist to `data/creatv.db` (see `db.py`, `migrations/`) instead of JSON;
`creative_flow_pendientes.json`/`ads.json` are kept only as a read-only backup,
and `migrar_json_a_db.py` (idempotent) is what originally imported them into the
database.

**Background jobs** (`trabajos.py`): this is an adapter over two execution paths.
Brand analysis and legacy publication still
goes through `trabajos.iniciar(job_id, fn, duracion_estimada)`, which runs the
function in-memory on a daemon thread. The migrated jobs (`flowplus_video`,
`flowplus_imagen`, `meta_publicar`, `meta_refrescar`, `swap_generar`, under
`tareas/`) go through `trabajos.encolar(...)`, which inserts a row into the `tarea`
table (`cola.py`, `data/creatv.db`) for the separate `worker.py` process (systemd
unit `deploy/creatv-worker.service`) to pick up and run. Either way the Flask route
returns almost instantly; the browser polls `/trabajo/<job_id>/estado` (JSON) —
the same endpoint for both paths — and renders a progress bar via the shared
`iniciarPolling()` JS in `base.html`, reloading the page on completion. `job_id` is
deterministic per (cliente, prompt_id/brief_id, acción) so a repeat click no-ops
instead of double-launching. Tasks that spend credits are queued with
`max_intentos=1` — they never auto-retry. A queued task stuck running for more than
30 minutes is either re-queued (if it still has attempts left) or marked `error`
(once `max_intentos` is exhausted) — never one this worker is running right now
(`cola.recuperar_colgadas(excluir=worker.en_vuelo())`). Since 2026-09-28 (spec
`2026-09-28-crear-sin-cola`, «en Crear nada queda en cola») the worker runs in lanes; since 2026-10-08 there are four: crear, nicho (PND-051, decisión delegada 2026-10-07, implementada 2026-10-08), `lectura` (below) and general:
`CARRIL_CREAR` (`flowplus_video`, `flowplus_imagen`, `flowplus_recuperar`, `flowplus_director`, `hablado_voz`)
runs up to `HILOS_CREAR = 4` at once — Sprints batches (`prioridad < 5`) take at most
`HILOS_LOTE = 2`, so a single piece from Crear always finds a thread — and everything else
runs one at a time in order, as before; Nicho has its own single thread (`CARRIL_NICHO`: recolectar, inv_buscar, inv_consultas, inv_seleccionar, generar_avatares, completar_avatares, referentes_barrer), excluded alongside Crear from general; the main thread only supervises (`worker.repartir`).
Code reached from a Crear task must therefore be thread-safe: `_json_store.guardar` uses a
per-thread tmp, `estado.modificar` (used by the worker AND by Flask's approve/reject/publish and
`sprints.revision`) and `musica._bloqueo` take `flock`, R2 opens one boto3 session per call, and
`trabajos.reportar` never raises. A task may return `tareas.Continuar(tipo, payload,
ejecutar_desde=)`: the worker closes it and queues the follow-up with the SAME job_id in one
transaction (`cola.terminar_y_encolar`, retried; if it still fails the task goes to `error` and its
`AL_INTERRUMPIR` hook runs), so the card's bar never sees «nothing alive». A thread that fails to
start gives its task back (`cola.devolver`). **`dashboard.py` runs with `use_reloader=False`
on purpose**: Flask's auto-reloader kills the whole process on file changes, which
would silently abort any in-flight background generation.

**Lane `lectura` (2026-10-08, ruling R16 of «Meta rendimiento»):** `CARRIL_LECTURA = ("meta_rend_sincronizar",)`
runs in its own single thread (`HILOS_LECTURA = 1`), and the general lane excludes `CARRIL_CREAR`, `CARRIL_NICHO`
and `CARRIL_LECTURA`. Why: the first copy of one Meta ad account measured on the real API takes 8 min (Norway) to
14 min (Netherlands), about an hour for happyflops' 7 accounts; on the single general thread that would have
blocked experiment launches and refreshes, Triple Whale and the stores for that long. Copies of different accounts
still run one after another (Meta's rate limits are per user+app, shared across accounts). It is free (reading
Meta never charges, `max_intentos=2`, and all three `meta_rend_*` types are in `TIPOS_EXENTOS_DE_COBRO`, so a project
with «Cobrar» on still syncs). `meta_rend_sincronizar_todas` and `meta_rend_limpiar` stay in the general
lane (instant). The area's own skill is `meta-rendimiento`. A new long, free, read-only sync can join this lane; anything that charges stays out of it.

**Higgsfield API wrapper** (`higgsfield_client.py`): all calls follow launch ->
`poll_until_done(status_url)` -> extract-result, for both video (`kling-2.1-pro`,
`extract_video_url`) and image (`soul-reference`, `extract_image_url`) generation.
`estimate_video`/`estimate_image` retain the free `/estimate/...` compatibility
for existing callers. No new Higgsfield generation path is added (decision
2026-09-18); the retired Nueva idea buttons and producers are gone (PND-068).
`ENDPOINTS`/`IMAGE_ENDPOINTS` dicts are the only place model routes are registered.

**Storage** (`storage/r2_uploader.py`): every generated/uploaded binary (personaje
images/videos, brand references, candidate images, final videos) is pushed to
Cloudflare R2 and referenced by its public URL from then on — binaries are never
committed to git (`.gitignore` excludes `clientes/*/personajes/*`, `clientes/*/marca/*`,
`salidas/`, the `*.json` state files, all `.env`/token files).
To delete: `delete_file(key)` builds one boto3 client per call; for a batch use `delete_files(keys)` (ONE client, each key on its
own, returns `(borradas, tipos_de_error)`, never the error text; no keys = no client).

**Ayudas de marca** (`generador_prompts.py`): calls Anthropic directly. `analizar_marca()` uses Claude's vision input on uploaded
brand reference images to auto-write that guía de estilo.

**Gasto real por proyecto** (`gastos.py`, table `gasto`, migration 0010): the table holds the real
provider COST. Since 2026-10-08 a project with «Cobrar» on also pays a prepaid balance (price = cost ×
markup, charged from `gastos.registrar`): see the skill `cobros`; every other project still just sees the
real provider price. Every paying task registers one row per charge through
`gastos.registrar_seguro(cliente, tipo, usd, referencia, ...)` (never raises), with a reference that includes the task id (`final:<id>:t<tarea_id>`,
`video:<cf_id>:t<tarea_id>`, …) so re-runs add history instead of overwriting it; the
reference is unique per cliente, so registering is idempotent. **Any new task that pays a
provider must call it** where the real figure is known (on failure after paying, register what
was paid with a detalle). `gastos.estimar(tipo, **params)` gives the "≈ US$" shown next to
buttons from `gastos.TARIFAS` (video/imagen from `flowplus_modelos`, `final` per country,
guion, regla_producto, caption_organico) and returns "precio no disponible" rather than
guessing. Reads: `resumen_mes` (the month), `resumen_total` (everything since the first charge, with `desde`),
`por_mes`, `historial`, `csv_mes` and `csv_todo` — Configuración › Gasto shows the month AND the total since the start
with a month-by-month table and «Descargar CSV de todo» (`gasto_csv_todo`), and the admin panel card shows both figures
(`admin.generacion_total`): on 2026-10-07 the screens only said «este mes» (US$ 66) and the US$ 200 of earlier months
looked lost. **Since 2026-10-08 every spend figure is a total since the start, never the month** (Daniel: «quiero que
todas las métricas aparezcan en la totalidad, no por mes, porque confunden a mis clientes»): the sidebar chip says
«Gasto total: US$ X generación · Y pauta» (`_chip_gasto(gastos.resumen_total, _pauta_mes(ctx, "total"))`, context processor,
cached), Configuración › Gasto shows «Generación total», «Pauta total», «Por tipo» since the start (`gastos.resumen_todo`),
the history and ONE «Descargar CSV» (`gasto_csv_todo`; `/gasto/mes.csv` still answers but nothing links it), and the
admin panel (`admin.resumen`, `desde=tablero.INICIO`) counts generation, ad spend and pieces since the start; only its
«Historial» table and its CSV stay per month (bookkeeping for invoices). Meta spend is NOT in `gasto` — it comes from
`metrica_snapshot` via `tablero` and is shown next to generation spend in its own currency. A new screen with money
shows the total; do not bring back «este mes».

**Cobros recuperados (2026-10-02, PND-109):** la identidad y la referencia del cobro original viajan en la predicción; una recuperación conserva ese id de tarea. Un gasto nuevo de música pertenece a la tarea que la obtuvo. Ver la regla de recuperación de `crear`.

PND-040/042 (2026-10-03): migración 0031 reconstruye material con AUTOINCREMENT conservando filas e ids. Todos los escritores de proyectos.py toman flock de proyecto.json.lock antes de leer; el idioma usa actualizar_campos y comparte el candado. Las escrituras rechazan un JSON ilegible en vez de sobrescribir ajustes. El generador de fixtures rendimiento/sembrar.py sigue siendo una inicialización fuera del flujo concurrente de producción.

PND-125 (2026-10-05): el cierre de Crear registra el video inmediatamente tras descargarlo, antes de la bitácora/mezcla, y la pista apenas recibe su costo, antes de mezclar; el registro final mantiene referencias idempotentes; _registrar_gasto activa conservar_mayor en gastos.registrar_seguro. La condición SQL impide que una recuperación con música de caché reduzca un cobro original con música; las recuperaciones que pagan una pista nueva conservan su referencia de tarea separada.

Revisión de Codex, 2026-10-05, lote 4: conservar_mayor se vigila también en la carrera IntegrityError con SQLite real. Describir referencias y sugerir sonido anotan bajo _creatv el cliente solicitante en extra.cliente. PND-144/145 registran los huecos aún abiertos de pista fallida e imagen cuyo error no se pudo persistir.

PND-144/145 (Codex, 2026-10-07): la imagen registra antes de escribir bitácora/error. Una pista fallida después de generar lleva costo_usd y URL en PistaPagadaError; Crear la registra con la referencia de tarea existente (o :musica de recuperación), conservando el video. No implica recuperación automática ni cubre SIGKILL antes del registro.

PND-072/088 (2026-10-07, lote 5 B): el encolado del director vive en tareas.director.encolar, conserva max_intentos=1 y prioridad del llamador. Una reserva perdida en sprints.produccion.crear_sesion archiva exclusivamente el concepto recién creado; no borra piezas ni la reserva de otro lote. PND-088 (2026-10-08, decisión delegada del 2026-10-07, lote 6 B): Repetir QA solo limpia y encola piezas que no pasaron ni fueron aprobadas; rutas y worker comprueban antes de llamar a Claude. R2 (2026-10-08): el worker permite el primer QA de una aprobada con qa=None, y bloquea una aprobada que ya tiene QA. Pruebas en tests/test_rutas_sprints.py y tests/test_tareas_sprints.py.

PND-144 (correcciones de lote 5, 2026-10-08): la referencia :musica de recuperación lleva proveedor fal explícito. Las pruebas provocan PistaPagadaError y fallo de bitácora juntos: generación y recuperación conservan US$ 0,82 sin duplicar la fila de pista. No se amplía la lógica de cobro en esta corrección.

**Lecturas de gasto real (2026-10-08, PND-111/143):** `gastos.total_tipo` suma también finales fallidas/reproducidas; `gastos.costos_sesiones` agrupa referencias de video/imagen por sesión y su `extra.usd_musica`. No se usa el costo del último intento para sustituir lo ya pagado. PND-012 reserva la ficha de voz en kv (gastos.reservar_ficha, no es gasto en cero) antes del proveedor, y con su respuesta la completa en gasto.extra junto al cobro real; la recuperación no llama a fal ni descarga otra vez y omite tareas en_curso (corrección lote 6A, 2026-10-08).

**Cobro al cliente en la puerta del costo (cobros 3/11, 2026-10-08, spec `2026-10-08-cobros-saldo-prepagado-design.md` §3):** `gastos.registrar` llama a `cobros.libro.cobrar_gasto` en un savepoint propio, después del upsert del gasto; si el cobro falla, el gasto queda y a los admins les llega `cobro_no_anotado`. Solo un gasto INSERTADO estrena cobro (`nuevo=True`); corregir uno que ya existía recalcula su cobro si lo tenía y nunca lo crea (prender «Cobrar» no cobra hacia atrás). Un proyecto que no cobra no cambia. **Toda rama de fallo después de pagar donde la pieza no llega a la persona anota con `entregado=False`** (`registrar_seguro(..., entregado=False)`): el costo queda igual y al cliente le queda un `no_cobrado` (o un `reverso` si ya tenía cobro) con su aviso. En una ruta sincrónica a Claude, «entregado» = Claude respondió (spec §3.5): esas no se marcan. Trampa de SQLite en WAL (revisión 2026-10-08): una transacción diferida que lee y después escribe recibe «database is locked» al instante si otro escritor confirmó en medio (SQLITE_BUSY_SNAPSHOT; busy_timeout no aplica), y pysqlite no emite BEGIN antes de un SAVEPOINT. Por eso el cobro corre DENTRO del savepoint del gasto, después del INSERT que ya tomó el candado (o después del UPDATE en la rama que corrige), y `cobros/libro.py` toma el candado antes de leer (`_candado`: `UPDATE kv SET valor=valor`, el truco de `saldo.marcar` y `cuentas.limite_ok`) en `exigir`, `revertir_trabajo`, `cobrar_gasto`, `configurar` y `guardar_margen_global`. Toda función nueva que lea y después escriba en una transacción hace lo mismo; el fixture `escritor_en_medio` de `tests/conftest.py` mete otro escritor justo antes de un statement para probarlo.

**El worker y los cobros (cobros 4/11, 2026-10-08, spec §3.5 y §5.1):** `_correr` corre `ejecutar` dentro de `libro.en_trabajo(tarea_id, job_id)` (ContextVar por hilo: el cobro anota de qué tarea y trabajo salió). Cada tipo de `tareas/` está en `tareas.TIPOS_QUE_COBRAN` (puede llamar a WaveSpeed, fal, Anthropic, Apify, Atria o TrendTrack a cuenta del proyecto) o en `tareas.TIPOS_EXENTOS_DE_COBRO` con su motivo; `tests/test_cobros_worker.py` falla con un tipo nuevo sin clasificar o un nombre que sobra. **Respaldo:** antes de correr un tipo que cobra, si el proyecto cobra, no es continuación de una cadena y su saldo es ≤ 0, la tarea queda en `error` definitivo (`cola.fallar(..., definitivo=True)`) con `worker.MENSAJE_SIN_SALDO`, sin llamar al proveedor, y corre su gancho `AL_INTERRUMPIR`. **Reversión:** todo error definitivo (excepción sin intentos, interrumpida por reinicio, continuación perdida, respaldo) llama a `libro.revertir_trabajo(..., desde_tarea=libro.inicio_de_cadena(tarea))`: devuelve los cobros del job_id **solo desde la primera tarea de la cadena** (`Continuar`). Los job_id se reusan entre corridas (`<cliente>__hablado_voz`, `<cliente>__voz_propia` y Audios son uno por proyecto): sin ese límite, una voz que falla hoy devolvía todas las ya entregadas (hallado al implementar, 2026-10-08). Una tarea que vuelve a `pendiente` no revierte; sin filas `cobro` de la cadena (`libro.tiene_cobros`, solo lee) `_revertir` no toma el candado de escritura. **Exentos que igual pagan algo** piden saldo adentro: `tienda_sync_productos` (periódica) sigue sin saldo, pero `importador._regla_si_hay_saldo` hace `libro.exigir` antes de la regla de fidelidad y, sin saldo, el producto entra sin regla; `sprint_qa_pendientes` no encola QA a un proyecto que cobra con saldo ≤ 0 (si no, el respaldo dejaba una tarea en error cada 5 min por pieza; ruling del orquestador, 2026-10-08). Trampa: la reversión es de toda la cadena; una tarea que entrega una parte y después lanza (`material_transcribir` con un archivo fallido, un barrido que falla en la fase de imágenes) devuelve también lo entregado.

**El freno antes de cobrar (cobros 5/11, 2026-10-08, spec §4-§5):** `trabajos.encolar(..., costo_estimado=)` (USD del proveedor, sin margen; None = basta saldo positivo): un job_id vivo devuelve False sin exigir; si el tipo está en `tareas.TIPOS_QUE_COBRAN`, `libro.exigir(cliente, costo, job_id)` comprueba y reserva antes de insertar la tarea, o lanza `cobros.SaldoInsuficiente` sin encolar nada. Un proyecto que no cobra no cambia. **Un solo rechazo:** `dashboard._saldo_insuficiente` (`@app.errorhandler`) responde 402 JSON `{ok: false, error, saldo_insuficiente: true, recargar_url}` a un fetch/JSON y, a un formulario, un aviso con enlace «Recargar saldo» y vuelta al `Referer` del mismo sitio (si no, a `ver_cliente#config-ap-saldo`). Una ruta que envuelve el encolado en `except Exception` deja pasar `SaldoInsuficiente` (`except SaldoInsuficiente: raise`). **Toda ruta que guarda algo antes de encolar** (sesión de Crear, swap, fila de final, barrido, evaluación de TW, grabación de voz, archivo de importación, el QA que se borra) pide `libro.exigir(cliente, costo)` sin job_id ANTES de guardar, y si el encolado igual falla (otro clic gastó el saldo en medio) deja la entidad en error con `e.frase_proyecto()` (la frase en el idioma del proyecto: se GUARDA) o la borra. `flowplus_lanzar.lanzar` calcula el estimado de la sesión (`costo_estimado(entry)`, mismas reglas que la tarea) y sin saldo devuelve la sesión a `prompt_listo` si venía de ahí o la deja en `error` con la frase. **Rutas que llaman al proveedor en la petición** (o en un hilo de `trabajos.iniciar`) piden saldo antes: Adaptar/leer referente, traducir la palabra de un barrido, «Escribir con IA» (orgánico; `organico.redactar` sin saldo cae al texto determinista para la publicación de una ganadora), muestra de voz propia, chat y pasos con Claude de Flow Plus (`guiones/rutas.py`, `rutas_pipeline._exigir`). **Encoladores que corren en el worker** atrapan `SaldoInsuficiente` y lo dejan dicho en su entidad, nunca revientan la tarea: el director con `auto_lanzar` (sesión en error y la frase como mensaje), la animación de «Recrear como video» (`animar_error`), la cadena de escenas (`_fallar`), las derivaciones (`_avanzar_item` → `_fallar`), la investigación de Nicho (`avanzar` → detenida con la frase), el análisis de una referencia de Sprints (`encolar_analisis` → análisis en error) y el lote de Sprints (pieza omitida). **Derivar y rescatar** piden saldo en `acciones._exigir_saldo` ANTES de `derivaciones.planificar` (que crea el hijo y marca `derivado`/`rescatado_en_escalon`): aprobar a mano sin saldo deja la propuesta pendiente con la frase (`dashboard._ejecutar_propuesta`), y en modo automático `acciones.pedir` la convierte en propuesta (revisión 1 de cobros 5/11, 2026-10-08: antes se gastaba la única derivación y el aviso decía «planificada»). Lo que paga Creatv (`_creatv`: describir referencias, sugerir sonido, muestras de voces de la galería, director) no pide saldo.

S3 (2026-10-08, auditoría lote 6B): la periódica diaria cola_limpiar llama mantenimiento.limpiar_limites. Solo poda kv limite:* si la marca más nueva tiene más de siete días o el valor es ilegible; UPDATE sin cambios toma el candado antes de leer/borrar. Ventanas existentes de 15 minutos/una hora; prueba SQLite en test_tareas_mantenimiento.py.

PND-068 (2026-10-08, decisión 2026-09-18: nada nuevo a Higgsfield): retirados productores y rutas de Nueva idea y sus nueve plantillas. No eran tareas de cola, sino hilos de Flask. Un tipo desconocido queda en error en palabras sin llamar al proveedor (tests/test_lote6c_retirar_ideas.py); proveedores/CLI y datos históricos conservados.

PND-051 (enmienda 2026-10-08): el carril Nicho tiene un solo hilo para sus seis tareas que esperan proveedor y referentes_barrer. Los barridos comparten la RAM y el límite de corridas de Apify con Nicho; repartirlos en paralelo daba 402 por capacidad. General excluye Crear + Nicho, y en_vuelo, esperar_hilos y recuperación son comunes a los tres carriles. En SIGINT/SIGTERM no se interrumpe el sondeo de Apify: el hilo termina la tarea y esperar_hilos lo espera. En un despliegue la cola debe estar vacía antes de reiniciar. No hay puntos de control ni continuaciones nuevas de Apify: se conserva el contrato anterior del proveedor y del gasto. Pruebas: tests/test_lote6c_nicho_carril.py, incluido un 402 sin cobro seguido de un segundo clic explícito con el mismo job_id que sí termina. No cambia max_intentos ni la política de cobro.

PND-190/166/159 (2026-10-09, decisiones delegadas lote 7): consultas/selección de Nicho y análisis/personas de Sprints se encolan con un intento y costo estimado. Sprints pasa un acumulador de usage (caché incluida), registra con referencia por tarea también si falla el guardado/JSON y usa entregado=False al fallar. El POST de arranque Apify pasa reintentar=False; los GET conservan su política.


Enmiendas lote 7 (2026-10-09, decisión delegada): SDK de Claude conserva sus reintentos. Apify registra estimado al recibir run_id, misma referencia de tarea para corregir al final (también cero si ya se anotó gasto; sin anotación previa, cero no crea fila). POST solo repite 429 con esperas; timeout/5xx leen hasta cinco corridas recientes, siguen una única posterior al inicio o avisan incertidumbre. Fuentes de Nicho propagan on_ids al registro antes del sondeo; hooks con corrida anotada dejan error, no pendiente.
