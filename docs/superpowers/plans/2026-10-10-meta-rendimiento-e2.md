# Meta rendimiento — E2 «Diagnosticar y recomendar» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sobre la copia de E1, Creatv diagnostica las cuentas de Meta con reglas gratis (aprendizaje limitado, perdedores, escalar, fatiga, problemas, segmentos…), las muestra en la pestaña Meta y en Alertas, y ofrece una evaluación con IA pagada con plan de cambios e ideas que van a Crear.

**Architecture:** Módulos nuevos en `meta_rendimiento/` (`desgloses`, `recomendaciones`, `administrador`, `analisis`), migración 0036 (`meta_desglose`, `meta_evaluacion`), tarea `meta_rend_evaluar` (cobra), fuente nueva de Alertas, secciones nuevas en `_meta_panel.html`. Reusa `triple_whale.analisis` y `triple_whale.puente`.

**Tech Stack:** Python 3, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite, Alembic, pytest, Jinja2, Anthropic (Claude) vía los helpers del repo.

**Spec:** `docs/superpowers/specs/2026-10-10-meta-rendimiento-e2-design.md`

## Global Constraints

- Worktree: `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/meta-e2`. Python `../../../venv/bin/python3`. Pruebas con archivos explícitos y `-p no:cacheprovider -x`; la suite completa (`-m "not slow"`) una vez antes del commit final de cada tarea.
- Leer antes: `CLAUDE.md`, skills `meta-rendimiento`, `cobros`, `doctrina`, `alertas`, `idioma`, `ui`, `seguridad` (en `.claude/skills/`).
- Todo texto visible por el catálogo (gettext / `_()` / `N_`); al final `catalogo_i18n.py actualizar` + traducir con `docs/i18n/glosario.md` + `compilar`, sin fuzzy.
- Nada se aplica en Meta: E2 solo lee y recomienda. Ninguna escritura a Graph.
- La tarea `meta_rend_evaluar` está en `tareas.TIPOS_QUE_COBRAN`, `max_intentos=1`, encolada con `trabajos.encolar(..., costo_estimado=)`, y anota el gasto real con `gastos.registrar_seguro(cliente, "evaluacion", usd, f"meta_eval:{id}{ref_sufijo(tarea)}")` también si Claude respondió inválido (y `entregado=False` si corresponde según la skill `cobros`).
- Llamada a Claude: `doctrina.bloque_system(...)` con el idioma del proyecto, `max_tokens` 16 000, texto ajeno (nombres de Meta) entre etiquetas como DATOS.
- Ningún token en errores, eventos, flashes, plantillas ni registros. URLs ajenas por `conectores.url.abrir`; miniaturas solo si `datos.miniatura_valida`.
- Único escritor: `meta_desglose` y `meta_evaluacion` solo desde `meta_rendimiento/datos.py`; `meta_cuenta.extra` solo vía `cuentas.actualizar_extra`.
- Rendimiento: abrir la pestaña no llama a Meta ni a Claude; cada lista es una consulta agregada; `panel.contexto` sube como mucho 4 consultas sobre su presupuesto actual (ajustar la prueba de conteo).
- Commits en español, archivos por nombre, última línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; nunca `git add -A` ni `git stash`.

---

### Task 1: Migración 0036 y datos

**Files:** `db.py`, `migrations/versions/0036_meta_rendimiento_e2.py`, `meta_rendimiento/datos.py`, `tests/test_meta_rend_migracion.py` (o un archivo nuevo `tests/test_meta_rend_e2_datos.py`).

- Tablas `meta_desglose` y `meta_evaluacion` exactamente como el spec §4 (UQ `uq_meta_desglose` (cliente, ad_account_id, ventana, dimension, clave); índice `ix_meta_evaluacion_cliente_creado` (cliente, creado_en)); migración `revision='0036'`, `down_revision='0035'`; downgrade las borra. Verificar una sola cabeza de alembic.
- `datos.reemplazar_desgloses(cliente, act, ventana, dimension, filas) -> int` (borra esa combinación y escribe, una transacción).
- `datos.desgloses(cliente, cuentas, ventana) -> list[dict]` (una consulta; filas con ad_account_id, dimension, clave y métricas).
- `datos.gasto_por_conjunto(cliente, cuentas, desde, hasta) -> dict[adset_id, {"gasto", "compras", "valor"}]` y `datos.gasto_por_anuncio_en_conjunto` si la regla de concentración lo necesita (o derivarlo de `totales_por_anuncio`, que ya trae `adset_id`: preferir eso y no agregar consulta).
- Evaluaciones: `crear_evaluacion(cliente, cuentas, desde, hasta, moneda, muestra, recomendaciones, pedido_por) -> id`, `actualizar_evaluacion(evaluacion_id, **campos)`, `evaluacion(cliente, id) -> dict|None` (filtra por cliente), `evaluaciones(cliente, limite=5)`, `borrar_evaluacion(cliente, id)`.
- `datos.borrar_cuenta` también borra los desgloses de esa cuenta (no las evaluaciones: son pagadas).
- Pruebas: idempotencia, aislamiento por cliente, migración arriba/abajo/arriba.

### Task 2: Desgloses en la copia

**Files:** `meta_rendimiento/desgloses.py`, `meta_rendimiento/sync.py`, `tests/test_meta_rend_desgloses.py`, `tests/test_meta_rend_sync.py`.

- `desgloses.DIMENSIONES = {"edad_genero": "age,gender", "ubicacion": "publisher_platform,platform_position", "pais": "country", "dispositivo": "impression_device"}`, `VENTANAS = (7, 30)`.
- `desgloses.fila(f, dimension) -> dict` (pura): clave = valores de los breakdowns unidos con «|» (en el orden de la dimensión), métricas como `sync.fila_cuenta` (compras con `graph.TIPOS_COMPRA`).
- `desgloses.copiar(cliente, act, token) -> int`: por ventana y dimensión, `graph.paginar(f"{act}/insights", token, {"level": "account", "date_preset": f"last_{v}d", "breakdowns": …, "fields": "spend,impressions,clicks,outbound_clicks,inline_link_clicks,actions,action_values", "limit": 500})` → `datos.reemplazar_desgloses`. Un `ErrorGraph` con `limite` sube; cualquier otro error de una combinación se anota (nombre del error) y sigue con la siguiente.
- `sync.sincronizar`: llama a `desgloses.copiar` cuando `extra.desglose_en` falta o tiene más de 20 h (y lo marca al terminar), después del alcance. Pruebas con el doble de Graph de `tests/test_meta_rend_sync.py`.

### Task 3: Reglas y enlaces al Administrador

**Files:** `meta_rendimiento/recomendaciones.py`, `meta_rendimiento/administrador.py`, `tests/test_meta_rend_recomendaciones.py`.

- `administrador.enlace(act, nivel, ids) -> str|None` según el spec §7 (ids numéricos validados, máximo 50; `None` si no hay ids válidos).
- `recomendaciones.calcular(entrada) -> list[dict]` puro, con las 9 reglas del spec §6, constantes con nombre al inicio del módulo, textos con gettext/ngettext y cifras con `idiomas.numero`. Define `entrada` como un dict con: `cuentas` (cada una con ad_account_id, nombre, moneda, extra.cuenta), `totales_7`, `totales_7_prev`, `totales_30` por cuenta, `objetos` (campañas y conjuntos activos con estado, presupuesto_diario, aprendizaje, campaign_id), `conjuntos_7` (gasto/compras/valor por conjunto en 7 días), `anuncios` (evaluados: ad_id, ad_account_id, adset_id, campaign_id, nombre, estado, veredicto, problemas, m), `frecuencia_7` por campaña (de `meta_alcance`), `desgloses_30` por cuenta. Documenta la forma en el docstring.
- Cada recomendación: `{id (huella estable: tipo + cuenta + objetos), nivel, tipo, cuenta, titulo, que_hacer, por_que, impacto, objetos, enlace}`; orden: alta > media > baja, luego impacto desc.
- Pruebas: cada regla con un caso que la dispara y uno que no (umbrales exactos), orden, huella estable, enlace correcto, sin regla para una cuenta sin datos.

### Task 4: Panel, Diagnóstico, Segmentos y Alertas

**Files:** `meta_rendimiento/panel.py`, `templates/_meta_panel.html` (y un parcial `_meta_diagnostico.html` / `_meta_segmentos.html`), `tareas/meta_rendimiento.py`, `alertas.py`, `tests/test_meta_rend_panel.py`, `tests/test_rutas_meta_rendimiento.py`, `tests/test_alertas*.py`.

- `panel.contexto` arma la `entrada` de las reglas con lo que ya leyó (sin consultas por fila; a lo sumo: objetos activos, conjuntos 7 días, alcance 7, desgloses 30 — 4 consultas) y agrega `recomendaciones` y `segmentos` (desgloses de la ventana más cercana, sumados por clave en «Todas» solo si comparten moneda; si no, por cuenta). Una función `panel.recomendaciones_de_cuenta(cliente, act, hoy=None)` reutilizable por la copia.
- Plantillas: sección «Diagnóstico» tras los KPIs (chips por nivel, tarjetas con título, qué hacer, por qué, impacto y enlace «Ver en el Administrador de anuncios» `target="_blank" rel="noopener noreferrer"`; más de 6 → «Ver todas» con `<details>`), sección «Segmentos» al final (tablas por dimensión con gasto, compras, ROAS, CPA; filas de segmentos caros marcadas). Base visual común, sin `<script>`, móvil sin desborde.
- Copia: al terminar `meta_rend_sincronizar` con éxito, calcula `panel.recomendaciones_de_cuenta` y guarda las «alta» como `extra.alertas = [{tipo, titulo, huella}]` (un fallo aquí se anota y no tumba la copia).
- Alertas: `_fuente_meta_rendimiento(cliente, ahora)` lee `meta_cuenta` del proyecto (una consulta) y produce una alerta por elemento (`nivel` atención, tab `meta`, huella estable, título con la cuenta); registrada en `FUENTES`. Seguir la skill `alertas` (cómo agregar una fuente, caché, solo_admin no aplica).
- Captura: renderizar la pestaña con datos falsos y mirarla (escritorio y 375 px).

### Task 5: Evaluación con IA (backend)

**Files:** `meta_rendimiento/analisis.py`, `tareas/meta_rendimiento.py`, `tareas/__init__.py` (`TIPOS_QUE_COBRAN`), `gastos.py` (tarifa `evaluacion_meta`), `triple_whale/puente.py` (origen genérico), `meta_rendimiento/rutas.py`, tests (`tests/test_meta_rend_analisis.py`, `tests/test_tareas_meta_rendimiento.py`, `tests/test_rutas_meta_rendimiento.py`, `tests/test_cobros_worker.py`).

- `analisis.armar(cliente, fila_evaluacion, medios, bloques) -> (datos_texto, bloques)` según el spec §8 (resumen por cuenta 7/30 y anteriores, recomendaciones, muestra con métricas y diagnóstico, segmentos destacados, aprendizaje limitado, aprendizajes del proyecto); nombres ajenos entre etiquetas.
- `analisis.system(idioma)` con `doctrina.bloque_system("clasificar", "angulo", "gancho", "video", "diagnosticar", extra=…, idioma=…)`; `analisis.analizar(...) -> (resultado, tokens_in, tokens_out)` reusando el cliente/llamada de `triple_whale.analisis` (sin copiar código: extraer un helper común si hace falta, con pruebas de Triple Whale verdes); `analisis.parsear(texto, refs_validas, ids_recomendaciones, datos_texto)` valida `resumen`, `diagnostico`, `plan` (máximo 8, acción del vocabulario, refs conocidas), y delega patrones/anuncios/ideas en el parser de Triple Whale; cifras verificadas con `doctrina.verificar_cifras` (una corrección).
- Tarea `meta_rend_evaluar` (`TIPOS_QUE_COBRAN`), job `<cliente>__meta_eval`, `max_intentos=1`: miniaturas desde `meta_objeto` → `triple_whale.analisis.copiar_miniaturas` → `visuales` → `analizar` → gasto real con `registrar_seguro` (siempre que hubo tokens) → fila `lista` o `error` (mensaje en palabras, sin token); `al_interrumpir` deja la fila en error. Clasificación en `TIPOS_QUE_COBRAN` y `test_cobros_worker` verde.
- `gastos.TARIFAS["evaluacion_meta"]` (por ahora con los valores de `evaluacion_tw`; la Task 7 la mide).
- Rutas: `POST /evaluar` (mismo origen, correo verificado, arma muestra con `panel` del alcance pedido, crea la fila, `trabajos.encolar(..., costo_estimado=gastos.estimar("evaluacion_meta", n=…)["usd"])`, una viva por proyecto; `SaldoInsuficiente` lo maneja el manejador global), `GET /evaluacion/<id>` (fragmento), `POST /evaluacion/<id>/idea/<i>/crear` (prefill con origen «meta:<id>:<i>», nada se genera). `triple_whale.puente.prefill_crear` acepta un `origen` genérico sin romper Triple Whale.
- Pruebas con Claude doble: éxito, inválido → error + gasto anotado, excepción con tokens → gasto anotado; ruta: precio, sin muestra, viva, saldo insuficiente (402/aviso), otro proyecto 404.

### Task 6: Evaluación con IA (pantalla)

**Files:** `templates/_meta_panel.html` + parcial `_meta_evaluacion.html`, `templates/_tab_meta.html` (JS: barra, cargar evaluación anterior), `meta_rendimiento/panel.py` (última evaluación y su job), tests de rutas.

- Sección «Evaluación con IA» tras «Diagnóstico»: botón «Evaluar N anuncio(s) con IA · <precio con margen>» con confirmación (como `_tw_panel.html`), barra `data-poll-job` mientras corre, la última lista (resumen, diagnóstico, plan numerado con enlace al Administrador si la acción tiene objetos, patrones, ideas con «Llevar a Crear»), error en palabras, y las 5 anteriores cargadas por fetch. Precios con `|precio`; nada del costo a un cliente de un proyecto que cobra (prueba de humo de cobros).
- Captura en escritorio y 375 px.

### Task 7: Medición real, tarifa, catálogo, skill y pendientes

- Cargar la skill `eval-claude`. En el VPS, sobre una copia de la base en /tmp y el código de la rama en /tmp (como la prueba de E1), correr `meta_rend_evaluar`'s núcleo (`analisis.armar` + `analizar`) 3 veces con la muestra real de «Todas» 30 días y una vez con una sola cuenta; anotar tokens de entrada/salida, `stop_reason`, costo, validez y si cumple el spec; fijar `gastos.TARIFAS["evaluacion_meta"]` (base + por anuncio) redondeando hacia arriba el máximo medido; guardar el informe en `docs/superpowers/evals/2026-10-10-meta-evaluacion.md`.
- Catálogo al día (sin fuzzy), skill `meta-rendimiento` (E2: reglas, desgloses, evaluación, alertas, precio medido), `cobros` (el tipo nuevo), `alertas` (la fuente nueva), `docs/pendientes.md` (PND-192 hecho; nuevos: «Cómo mejorarlo» de Meta, `issues_info`, avisos por correo), decisiones de E2 en `docs/superpowers/decisiones/2026-10-10-meta-rendimiento-e2.md`.
