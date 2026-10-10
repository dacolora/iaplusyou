# Planes mensuales y Wompi — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que un proyecto pueda tener un plan mensual (bolsa que se renueva, precio de miembro, lo barato incluido, prioridad) cobrado automáticamente con Wompi, y que las recargas a la carta también vayan por Wompi.

**Architecture:** se monta sobre `cobros/` (ya en producción). `cobros/libro.py` sigue siendo el único escritor del libro y gana la bolsa del plan (calculada primero-el-plan), el margen efectivo con periodo y la rama `incluido`. Módulos nuevos: `cobros/trm.py` (tasa de cambio), `cobros/wompi.py` (único que habla con Wompi), `cobros/pasarela.py` (elige Wompi o Bold para recargas), `cobros/planes.py` (único escritor de `plan`, `suscripcion`, `periodo_plan`, `pago_plan`), y la periódica `planes_renovar`.

**Tech Stack:** Python 3, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (WAL), Alembic, `requests`, pytest, el widget de tokenización de Wompi en el navegador.

**Spec:** `docs/superpowers/specs/2026-10-09-planes-mensuales-wompi-design.md`. Referencia de la API: `docs/pagos/wompi-api.md` (con su lista de incertidumbres §13). Lo construido antes: `.claude/skills/cobros/SKILL.md` (léela entera: trampas de SQLite, candado del libro, `nuevo=False`, `excluir_job`, fail-closed, el costo que no llega al navegador).

## Global Constraints

- Trabaja SOLO en el worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/planes-wompi` (rama `planes-wompi`).
- `PY=/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`. Pruebas: `$PY -m pytest -q <archivo>`; suite rápida `$PY -m pytest -q -m "not slow"`.
- Carga las skills `cobros`, `plataforma`, `seguridad`, `idioma` y, si tocas pantallas, `ui`, antes de tocar código.
- Montos del libro en milésimas de dólar enteras. Precio de un plan en dólares enteros. Wompi cobra en COP: `amount_in_cents = ceil(usd × trm) × 100`.
- Margen global por defecto **2,0** (a la carta). Primer plan: «Pro», US$ 1 000/mes, anual US$ 10 000, margen **1,25**, tope incluido **25 USD de costo**/mes, sembrado **archivado**.
- Escritores únicos: `cobros/libro.py` → `movimiento_saldo`, `cuenta_saldo`, `reserva_saldo`; `cobros/planes.py` → `plan`, `suscripcion`, `periodo_plan`, `pago_plan`; `cobros/recargas.py` → `recarga`, `pago_evento`.
- Toda lectura-modificación-escritura del libro o de pagos toma el candado (`libro._candado(con)`) ANTES de leer (pysqlite no abre transacción antes de un SELECT).
- Llaves Wompi en `.env`: `WOMPI_LLAVE_PUBLICA`, `WOMPI_LLAVE_PRIVADA`, `WOMPI_SECRETO_EVENTOS`, `WOMPI_SECRETO_INTEGRIDAD`; el prefijo (`_test_`/`_prod_`) decide el ambiente; llaves de pruebas solo con host local de `PLATAFORMA_URL`. Nunca en logs, flashes, eventos, respuestas ni pruebas (valores falsos marcados con `llave-de-prueba` en la línea).
- Un proyecto que no cobra no cambia en nada. Toda prueba existente sigue pasando.
- Todo texto visible por el catálogo (`gettext`, `{{ _() }}`), traducido según `docs/i18n/glosario.md` (plan = plan, suscripción = subscription, bolsa del plan = plan balance, precio de miembro = member price, incluido = included), sin `fuzzy`.
- Commits en español terminados en `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nunca subagentes ni revisores propios.

---

### Task 1: Datos (migración 0035, hoy 0038 tras mezclar main el 2026-10-10) y margen global 2,0

**Files:** `db.py`, `migrations/versions/0038_planes_wompi.py` (era `0035_planes_wompi.py`), `cobros/libro.py` (`MARGEN_DEFECTO = 2.0`), `tests/test_planes_db.py`.

**Produces:** `db.plan`, `db.suscripcion`, `db.periodo_plan`, `db.pago_plan` con las columnas exactas del spec §2; `movimiento_saldo.periodo_id` + `UNIQUE(tipo, periodo_id)` (con `batch_alter_table` en SQLite; recuerda que `UNIQUE(tipo, gasto_id)` y `UNIQUE(tipo, recarga_id)` ya existen y deben quedar); `recarga.pasarela_ref` String(40) UNIQUE NULL; índice único parcial en `suscripcion(cliente)` donde `estado != 'terminada'` (`sqlite_where`). En la migración: si `kv['cobros:margen_global']` vale `1.5`, pasarlo a `2.0`; sembrar el plan «Pro» archivado (`activo=0`). `down_revision = '0034'` (verifica el id real en `migrations/versions/0034_tw_tarjetas.py`).

- [ ] Prueba que falla: tablas e índices existen; dos suscripciones no terminadas del mismo cliente chocan, una terminada + una activa no; `UNIQUE(tipo, periodo_id)`; `pasarela_ref` único; `libro.margen_global()` sin kv = 2.0; la migración pasa 1.5→2.0 y deja otro valor intacto; el plan sembrado existe archivado.
- [ ] Implementar; ensayar `alembic upgrade head`, `downgrade 0034`, `upgrade head` sobre una base nueva en /tmp y sobre una copia de `/Users/colorado/Documents/GitHub/iaplusyou/data/creatv.db` en /tmp (nunca el archivo real). `alembic heads` debe dar una sola cabeza.
- [ ] Pruebas existentes que dependan del margen 1,5 por defecto: ajústalas solo si comprueban el valor por defecto (no la lógica); lista cada una en el informe.
- [ ] Commit «Planes 1/8: tablas de planes, suscripciones, periodos y pagos (0035); margen a la carta 2,0».

### Task 2: El libro con plan (bolsa, margen de miembro, incluidos, prioridad)

**Files:** `cobros/libro.py`, `cobros/planes.py` (solo lecturas en esta tarea: `periodo_abierto(con|None, cliente, ahora=None)`, `TIPOS_INCLUIDOS`, `incluido_usado(cliente, periodo)`), `trabajos.py`, `tests/test_planes_libro.py`.

**Produces (firmas):**
- `planes.TIPOS_INCLUIDOS: frozenset[str]` (spec §4; verifica cada nombre contra `gastos.TIPOS` y agrega el del diagnóstico con su nombre real).
- `planes.periodo_abierto(cliente, ahora=None) -> dict|None` (`{"id","inicio","fin","margen","tope_incluido_usd","credito_milesimas","suscripcion_id"}`; memorizada por petición si hay contexto Flask).
- `libro.bolsa_plan(cliente, ahora=None) -> dict|None` → `{"periodo_id","credito","gastado","restante","fin"}` según spec §3 (primero el plan).
- `libro.acreditar_plan(con, periodo_id) -> int|None` (movimiento `plan`, idempotente) y `libro.vencer_periodo(con, periodo_id) -> int` (movimiento `vencimiento` por −restante limitado para no dejar el saldo < 0 por el vencimiento; marca `cerrado` llamando a una función de `planes` que reciba `con` — o devuelve el monto y `planes` marca: el escritor de `periodo_plan` es `planes`).
- `_cuenta` / `margen_precio` / `estado`: margen efectivo = el del periodo abierto si lo hay.
- `cobrar_gasto`: con periodo abierto y `tipo in TIPOS_INCLUIDOS`, si `incluido_usado + usd ≤ tope` → movimiento `incluido` (0, `extra={"precio": precio_miembro, "costo": usd, "margen": m}`), resultado `"incluido"`; si no → cobro normal. Correcciones (`nuevo=False`) de un `incluido`: siguen incluidas (recalcula `extra`).
- `exigir`: tipo incluido dentro del tope → precio 0 (sin reserva). Para eso `exigir(…, tipo=None)` acepta el tipo de gasto opcional; `trabajos.encolar` lo pasa si el tipo de tarea tiene un tipo de gasto conocido (mapa en `planes`) — si no, se comporta como hoy.
- `trabajos.encolar`: prioridad 6 si el proyecto tiene periodo abierto y la prioridad pedida es la normal (5); nunca baja la de un lote.
- `gastos._despues_del_cobro`: `"incluido"` no avisa nada al cliente; al admin, al cruzar 80 % y 100 % del tope (una vez por periodo, `kv`).

- [ ] Pruebas que fallan (con `base_temporal`, filas reales de `periodo_plan`): FIFO con recarga propia a mitad del periodo; `vencer_periodo` exacto e idempotente y que no deja el saldo negativo tras una anulación; margen 1,25 con periodo y 2,0 sin él; incluido dentro del tope (0) y el que cruza el tope (cobro a 1,25); `exigir` con tipo incluido dentro del tope no exige saldo; prioridad 6 con plan y 5 sin plan; un lote (3) sigue en 3; proyecto que no cobra: nada cambia.
- [ ] Implementar con el candado; correr `tests/test_cobros_*.py` (deben seguir verdes) y la suite rápida.
- [ ] Commit «Planes 2/8: la bolsa del plan primero, precio de miembro, lo incluido con tope y prioridad».

### Task 3: TRM, cliente de Wompi y elección de pasarela

**Files:** `cobros/trm.py`, `cobros/wompi.py`, `cobros/pasarela.py`, `.env.example`, `tests/test_wompi.py`, `tests/test_trm.py`.

**Produces:**
- `trm.actual() -> float` (lanza `trm.SinTasa` si no hay tasa ≤ 3 días); caché `kv['cobros:trm']` 6 h; host fijo `www.datos.gov.co`, dataset `32sa-8pi3`, campo `valor`.
- `wompi.configurado() -> bool`, `wompi.pruebas() -> bool`, `wompi.base_url()`, `wompi.ErrorWompi` (con `.caida` como `bold.ErrorBold`), `wompi.firma_integridad(referencia, centavos, moneda="COP", expiracion=None) -> str`, `wompi.evento_valido(cuerpo_dict, checksum_header=None) -> bool` (spec §5.3; `hmac.compare_digest`), `wompi.url_checkout(referencia, centavos, redirect_url, correo=None) -> str`, `wompi.aceptaciones() -> {"acceptance_token","acceptance_url","personal_token","personal_url"}` (`GET /v1/merchants/info`, header `x-merchant-public-key`... verifica en `docs/pagos/wompi-api.md` §2), `wompi.transaccion(id, tiempo=…) -> dict`, `wompi.crear_fuente(tipo, token, correo, acceptance_token, personal_token) -> {"id","tipo","resumen"}`, `wompi.cobrar_fuente(fuente_id, centavos, correo, referencia) -> dict` (con `recurrent=True`, `installments=1`, `signature`), `wompi.token_nequi(celular) -> str` y `wompi.estado_token_nequi(token) -> str`.
- Regla de host: con llaves `_test_` y `PLATAFORMA_URL` no local, `configurado()` es False y toda llamada lanza `ErrorWompi` en palabras (prueba).
- `pasarela.para_recargas() -> "wompi"|"bold"|None`.

- [ ] Pruebas que fallan (HTTP falso con `monkeypatch` de `requests`; nunca red): firma de integridad contra un caso calculado en la prueba con un secreto de prueba; evento válido / inválido / propiedades alteradas / checksum en cabecera; ambiente por prefijo; llaves de pruebas en host no local; errores 4xx/5xx/timeout → `ErrorWompi` sin llaves en el texto; TRM con caché, respaldo ≤ 3 días y `SinTasa`.
- [ ] Commit «Planes 3/8: TRM oficial, cliente de Wompi (checkout, fuentes, cobros, eventos) y elección de pasarela».

### Task 4: Recargas a la carta con Wompi y el endpoint de eventos

**Files:** `cobros/recargas.py`, `cobros/rutas.py`, `dashboard.py` (exenciones del endpoint `cobros.wompi_eventos`, igual que `cobros.bold_webhook`), plantillas de recarga si cambian textos, `tests/test_recargas_wompi.py`.

**Produces:** spec §5.1 y §5.3. `recargas.crear` usa la pasarela elegida (Wompi: recarga con `medio="wompi"`, TRM guardada en `nota`/`extra`, redirige a `wompi.url_checkout`). La vuelta con `?id=` consulta `wompi.transaccion` (bajo el semáforo y el guard en vuelo de hoy) y acredita los USD elegidos solo si referencia, centavos y moneda cuadran y `status == "APPROVED"`. `recargas.procesar_evento_wompi(cuerpo_bytes, checksum)` (cupo sin firma, `pago_evento(proveedor="wompi", evento_id=sha256(cuerpo))`, `transaction.updated`: `cv-` → recarga; `pl-` → `planes.aplicar_transaccion` (Task 5; en esta tarea deja el gancho que la llama si existe y si no responde `ignorada`)). `verificar_pendientes` incluye las de Wompi. Ruta `POST /pagos/wompi/eventos` → 200/400/401/413 sin cuerpo.

- [ ] Pruebas que fallan: crear con Wompi (URL de checkout con firma correcta, centavos = ceil(usd×trm)×100); vuelta APPROVED acredita USD una vez; DECLINED no; monto o referencia que no cuadran no acreditan y avisan al admin; evento firmado acredita; evento + vuelta no duplican (bajo `escritor_en_medio`); evento sin firma 401 sin tocar nada; la exención es exactamente ese endpoint (`ENDPOINTS_OTRO_ORIGEN == {"cobros.bold_webhook", "cobros.wompi_eventos"}`); sin llaves de Wompi pero con Bold, sigue Bold.
- [ ] Commit «Planes 4/8: recargas a la carta por Wompi (checkout firmado, vuelta verificada, eventos)».

### Task 5: Planes y suscripciones (alta, cobro del periodo, renovación, gracia, cancelación)

**Files:** `cobros/planes.py`, `tareas/planes.py` (periódica `planes_renovar` cada 1800 s en `worker.PERIODICAS`, exenta en `tareas.TIPOS_EXENTOS_DE_COBRO` con motivo), `cobros/avisos.py`, `notificaciones.py` (tipos nuevos), `tests/test_planes.py`.

**Produces:** spec §5.2 (lado servidor), §5.4, §7. Funciones: `planes.listar(activos=True)`, `crear_plan/editar_plan/archivar_plan(…, usuario)` (validan precio entero > 0, margen 1–5, tope ≥ 0), `suscribir(cliente, plan_id, ciclo, tipo_fuente, token, correo, aceptacion: dict, usuario) -> dict` (crea fuente en Wompi, suscripción y cobra el primer periodo), `cobrar_periodo(suscripcion_id) -> estado` (idempotente por renovación con el candado: nunca dos `pago_plan` aprobados/pendientes para la misma renovación), `aplicar_transaccion(transaccion: dict) -> resultado` (APPROVED abre periodo(s) y acredita bolsa vía `libro.acreditar_plan`; DECLINED/ERROR cuenta intento), `renovar_todo(ahora=None) -> resumen` (cierra periodos vencidos con `libro.vencer_periodo`, abre periodos anuales cubiertos, cobra las que tocan, gracia 24 h / 48 h, termina al tercer rechazo), `cancelar(cliente, usuario)`, `terminar_ya(cliente, usuario, nota)`, `cambiar_fuente(cliente, tipo, token, correo, aceptacion, usuario)`, `activar_manual(cliente, plan_id, ciclo, usuario, nota)`, `estado_cliente(cliente) -> dict` (para pantallas: suscripción, periodo, bolsa, incluido usado en %, ahorro del periodo, próximos pasos). Avisos de spec §7.6.

- [ ] Pruebas que fallan (Wompi falso): alta con primer cobro APPROVED abre periodo y acredita 1 000 000 milésimas; DECLINED deja `terminada` sin periodo; PENDING + evento APPROVED; renovación al vencer (cierra con vencimiento, cobra, abre); dos `renovar_todo` simultáneos no cobran dos veces (`escritor_en_medio` o dos hilos); gracia: rechazo → morosa sin periodo → reintento 24 h → 48 h → terminada; pago en el segundo intento abre desde ese día; cancelar mantiene hasta fin y luego terminada; anual: un pago, 12 periodos que se abren sin cobrar; activación manual; cambio de fuente en morosa cobra en el acto; aviso 3 días antes una sola vez.
- [ ] Commit «Planes 5/8: suscripciones con cobro automático en Wompi, renovación, gracia y cancelación».

### Task 6: Lo que ve el cliente (Configuración › Plan, medidor, ahorro, chip)

**Files:** `cobros/rutas.py` (rutas del plan bajo `/cliente/<cliente>/plan/…`: panel por fetch, suscribir, estado de alta, cancelar, cambiar tarjeta, token Nequi), `cobros/vista.py`, `templates/_config_plan.html`, `templates/_plan_panel.html`, `templates/_tab_settings.html` (apartado `config-ap-plan`), `templates/_sidebar.html`, `templates/_saldo_panel.html` (saldo propio vs bolsa), `static/planes.js` (widget de tokenización, casillas, sondeo del alta), estilos en `static/estilos/` + regenerar `style.css`, `tests/test_planes_vista.py`.

**Produces:** spec §8. El widget de tokenización de Wompi se carga solo en el formulario de alta/cambio de tarjeta (CSP: verifica que la política permite `checkout.wompi.co`; si no, ajústala solo para ese script). Las tres casillas son obligatorias en el servidor (no solo en el HTML). Lo que el widget entrega al formulario se averigua en sandbox; mientras tanto, la ruta acepta `token` + `tipo` y la prueba lo simula. Medidor, incluido en %, ahorro del periodo, tarjeta enmascarada, historial, cancelar con la frase de §7.4, aviso de morosa. El cliente nunca ve el costo ni el margen ni el tope en dólares de costo.

- [ ] Pruebas que fallan: los tres estados (sin plan, con plan, morosa) como `user_acme`; alta sin una casilla → error sin llamar a Wompi; otro proyecto no ve ni cancela; números del medidor y del ahorro con datos sembrados; chip con «Plan: US$ X restantes»; sin N+1 (contador de consultas). Captura en escritorio y 375 px con el método de la memoria «ver la UI sin contraseña» (no dejes cambios en el `.claude/launch.json` del checkout principal).
- [ ] Commit «Planes 6/8: Configuración › Plan con medidor, ahorro, alta con tarjeta tokenizada y cancelación».

### Task 7: Lo que ve el admin

**Files:** `cobros/rutas.py` (admin), `cobros/vista.py` (`resumen_admin` + suscripciones), `templates/admin_cobros.html`, `tests/test_planes_admin.py`.

**Produces:** spec §9: CRUD de planes, por proyecto la suscripción con acciones (activar a mano, cancelar, terminar ya con nota), márgenes visibles (global 2,0 y de cada plan), ganancia del periodo, eventos de Bold y Wompi (solo firmados). Avisos de configuración: Wompi sin llaves, llaves de pruebas en producción.

- [ ] Pruebas: solo admin y mismo origen; validaciones; consultas constantes con 3 vs 6 proyectos; activar a mano abre periodo y acredita.
- [ ] Commit «Planes 7/8: /admin/cobros con planes y suscripciones».

### Task 8: Alertas, catálogo, skill y pendientes

**Files:** `alertas.py` (`cobros:plan_morosa`, `cobros:plan_renueva` 3 días antes, `cobros:plan_bolsa_80`), `translations/…` (catálogo), `.claude/skills/cobros/SKILL.md` (sección «Planes y Wompi» con las trampas), `CLAUDE.md` (si la fila de la skill cambia), `CONTEXT.md` (plan, suscripción, periodo, bolsa del plan, incluido, precio de miembro), `docs/pendientes.md` (lo de §13 del spec y lo que quede de las incertidumbres de Wompi, con IDs libres después del máximo de main), `tests/test_planes_alertas.py`.

- [ ] Pruebas de alertas; `tests/test_guia_agentes.py`, `tests/test_i18n_catalogo.py`; suite completa `$PY -m pytest -q`.
- [ ] Commit «Planes 8/8: alertas del plan, catálogo, skill y pendientes».
