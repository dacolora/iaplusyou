# Gasto real por proyecto (precio a la vista, sin créditos) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Que cada cosa que gasta dinero muestre su **precio en dólares** antes (estimado) y después (real), y que el proyecto vea cuánto lleva gastado en el mes — generación (Higgsfield, fal.ai, Claude) aparte de pauta (Meta) — con historial y CSV; el admin ve el gasto de todos los proyectos. Sin créditos, saldo ni recargas (decisión del dueño 2026-09-18: "nada de crédito, mostrar el precio").

**Architecture:** tabla `gasto` (0010) alimentada por un único punto `gastos.registrar(cliente, tipo, usd, referencia, detalle)` que llaman las tareas que pagan (flowplus video/imagen, swap, final guion/producir, importador regla, orgánico caption, derivaciones vía las anteriores) + `gastos.estimar(tipo, **params)` con la tabla de precios de proveedores para mostrar el precio antes; `gastos.resumen_mes(cliente)`, `gastos.serie/historial`, `gastos.csv`; pauta = deltas de `metrica_snapshot` ya calculados por `tablero`. UI: precio junto a cada botón que gasta, costo real en cada pieza/final (ya existe en parte), chip "Este mes: US$ X generación · Y pauta" en la barra lateral, Configuración › **Gasto** (mes por tipo, historial, CSV), Tablero (tile "Generación este mes"), panel admin (gasto por proyecto).

**Spec:** decisión del dueño 2026-09-18 (chat). Spec §7 hablaba de créditos: reemplazado por precio a la vista.

## Global Constraints
- Un solo registro por cobro real: cada tarea llama `gastos.registrar` una vez al terminar (o al fallar si el proveedor ya cobró — mismo criterio que hoy con `max_intentos=1`), con `referencia` única (`f"{tipo}:{id}"`) e índice único `(cliente, referencia)` → `registrar` es idempotente (segunda llamada actualiza `usd`/`detalle`, no duplica).
- Precios en USD con 2 decimales en la UI (`US$ 0,07`), redondeo a 4 en base. Estimados marcados "aprox." y nunca superiores al real conocido en más de 2× (si el modelo no tiene tarifa, se muestra "precio no disponible", no se inventa).
- Pauta (Meta) NO se registra en `gasto` (ya vive en `metrica_snapshot`, moneda de la cuenta); en la UI se muestra al lado, en su moneda.
- Nunca se bloquea una acción por gasto: solo se informa. Copy en español; suite verde sin red.

---

### Task 1: Migración 0010 + `gastos.py` + tabla de precios

**Files:** `migrations/versions/0010_gasto.py`, `db.py`, `gastos.py`, `flowplus_modelos.py` (leer `estimate_video/estimate_imagen`), tests `tests/test_gastos.py`.

**Interfaces:**
- Tabla `gasto`: `id, cliente (idx), creado_en, tipo (video|imagen|swap|guion|final|regla_producto|caption_organico|musica|otro), usd Float, proveedor String(30), referencia String(160), detalle String(300), extra JSON`; unique `(cliente, referencia)`.
- `gastos.registrar(cliente, tipo, usd, referencia, detalle="", proveedor=None, extra=None) -> id` (upsert por referencia; `usd` None/0 se guarda 0).
- `gastos.estimar(tipo, **params) -> {"usd": float|None, "texto": "US$ 0,10 aprox."|"precio no disponible", "detalle": str}` — tarifas: `video` → `flowplus_modelos.estimate_video(modelo, duracion, con_sonido)`; `imagen` → `estimate_imagen(modelo, n_referencias)`; `swap` → tarifa por proveedor de `prompt_swap`/swaps (leer qué guarda `swaps.py` en `costo`; si no hay tarifa → None); `guion` 0.02; `final` 0.10 + 0.02 por país extra (voz ~0.05, música 0.02, whisper ~0.01, guion 0.02); `regla_producto` 0.01; `caption_organico` 0.01; `regeneracion` = `video` del modelo; `reedicion` = `final`. `gastos.TARIFAS` dict público con esas constantes y su fuente en comentario.
- `gastos.resumen_mes(cliente, ahora_iso=None) -> {"desde", "hasta", "total": f, "por_tipo": {tipo: {"usd", "n"}}, "n": int}`; `gastos.historial(cliente, limite=200, desde=None) -> [dict]` (más nuevo primero); `gastos.serie_diaria(cliente, dias=30)`; `gastos.csv_mes(cliente)` (`;`, BOM, escapes de fórmulas como `tablero.csv_mes`); `gastos.por_proyecto_mes(clientes) -> {cliente: total}` (una consulta).
- `gastos.formatear(usd) -> "US$ 0,07"` (coma decimal, 2 decimales; `< 0.01` → "US$ <0,01"; None → "—").

- [ ] Tests: registrar idempotente; resumen por tipo con un gasto fuera del mes; historial orden; csv con BOM/escape; estimar cada tipo (monkeypatch `flowplus_modelos`); formatear.
- [ ] Commit `"Gasto: tabla gasto, registro idempotente, tarifas y resumen mensual"`.

### Task 2: Registrar en cada tarea que paga

**Files:** `tareas/flowplus.py` (video: `usd` del `estimate` + música `usd_musica`; imagen), `tareas/swap.py` (leer cómo calcula el costo), `final_edition/__init__.py` o `tareas/final_edition.py` (guion: `costo_guion`; final: `costo` total y por capa en `extra`), `importador.py` (regla: `generador_prompts.regla_fidelidad` → 0.01 real si hubo llamada; añadir a `regla_fidelidad` un retorno de costo si el SDK lo da: usar `usage` tokens × tarifa del modelo; si no, tarifa fija), `organico.py` (`redactar` → registrar cuando Claude respondió), `derivaciones.py` (nada: las finales/regeneraciones registran solas), tests por cada uno (asertar que `gastos.historial` tiene la fila con la referencia esperada).

- Referencias: `video:<cf_id>`, `imagen:<cf_id>`, `swap:<swap_id>`, `guion:<cf_id>`, `final:<final_id>`, `regla_producto:<producto_id>`, `caption_organico:<pieza_id>:<fecha_hora>`.
- Un fallo con cobro (p. ej. render fallido tras pagar voz/música) registra lo pagado (`detalle` "falló en render; voz y música cobradas").
- [ ] Commit `"Gasto: cada tarea que paga registra su costo real"`.

### Task 3: UI — precio antes y después, Configuración › Gasto, sidebar, Tablero, panel admin

**Files:** `dashboard.py` (contexto: `gasto_mes`, `pauta_mes` (de `tablero.resumen_mes` por moneda), `precios` = dict de estimados para los botones de la página: video por modelo/duración se calcula en JS con `gastos.TARIFAS` serializado (`|tojson`) o servidor si ya hay estimación (Crear ya muestra `credits`/`usd` — reutilizar), final por país, guion, regla, orgánico; ruta `gasto_csv` GET `/cliente/<c>/gasto/mes.csv`; `panel` admin: columna "Gasto del mes (US$)" con `gastos.por_proyecto_mes`), templates: `_sidebar.html` (chip bajo el nombre del proyecto: "Este mes: US$ 12,40 generación · 1.405.156 COP pauta" — pauta solo si hay), `_tab_creativeflowplus.html` (junto a "Generar": "≈ US$ 1,00" ya existe para FlowPlus — verificar y homogeneizar con `gastos.formatear`; Final edition: "Preparar guion ≈ US$ 0,02", "Producir N finales ≈ US$ 0,10 c/u"; cada final muestra "costó US$ 0,07" (ya está el costo, formatear)), `_tab_catalogo.html` (Crear activo desde fotos: "≈ US$ 0,01 la regla con IA"), `_organico_publicar.html` ("Escribir texto con IA ≈ US$ 0,01"), `_tab_experimentos.html` (derivar/rescatar en propuestas: "≈ US$ X" = n_reediciones × final + n_regeneraciones × video del modelo — calcular en `acciones.pedir` y guardar en `payload["precio_estimado"]`, mostrarlo en la propuesta), `_tab_settings.html` (sección **Gasto** después de Puesta a punto: tiles total mes generación / pauta, tabla por tipo, historial paginado (200), botón CSV, nota "precios reales de los proveedores; la pauta se cobra en tu cuenta de Meta"), `_tab_tablero.html` (tile "Generación este mes US$ X" junto a gasto de pauta), `panel.html`, `static/style.css`, tests `tests/test_rutas_gasto.py`.
- [ ] Tests: sidebar chip con valores; Configuración › Gasto render + CSV; precios en botones (strings "≈ US$"); propuesta con `precio_estimado`; panel admin con columna; cross-tenant CSV.
- [ ] Verificación manual; commit `"Gasto a la vista: precio estimado en cada botón, costo real por pieza, Configuración › Gasto, sidebar, Tablero y panel admin"`.

### Task 4: Docs
- [ ] `CLAUDE.md`/`SETUP.md`: gasto real (tabla `gasto`, `gastos.registrar` obligatorio en toda tarea nueva que pague, tarifas en `gastos.TARIFAS`). Commit `"Docs: gasto real por proyecto"`.
