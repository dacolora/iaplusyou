# Cobros: saldo prepagado por proyecto, margen y recargas con Bold (2026-10-08)

Pedido de Daniel (2026-10-07): «la plataforma no tiene pasarela de pagos ni cómo ganar dinero; todos usan el producto
pero al final yo hago las recargas». Se cobra el uso con una comisión. Diseño aprobado por partes en la conversación;
después Daniel pidió llevarlo de punta a punta sin más preguntas: lo que quedaba abierto está en §12 como rulings.

Decisiones de Daniel (en la conversación, 2026-10-07/08):

1. **Saldo prepagado.** El cliente recarga, el uso descuenta, sin saldo el botón no arranca.
2. **Margen del 50 %**: se cobra el costo real × 1,5. Parámetro, no número quemado.
3. **Empresa en Colombia, clientes en varios países → Bold** como pasarela (tarjetas Visa/Mastercard de cualquier país
   con DCC; PSE y Nequi en Colombia; Bold liquida en pesos), más **recarga manual del admin**.
4. **Se cobra al terminar, sobre el costo real** (no sobre el estimado). El botón muestra el estimado con margen.
5. **Si el proveedor cobra y la pieza falla, al cliente no se le cobra, pero se le avisa.**
6. Cada proyecto con un interruptor **«Cobrar»** que arranca apagado: el despliegue no cambia nada hasta que Daniel lo
   prende proyecto por proyecto.

Lo que ya existe y se aprovecha: cada cobro real de un proveedor pasa por **una sola puerta**,
`gastos.registrar(cliente, tipo, usd, referencia, ...)` (vía `registrar_seguro`), con referencia única por proyecto
(`gastos.py:353`, tabla `gasto`, migración 0010). Cada botón ya muestra un «≈ US$» (`gastos.estimar`,
`gastos.py:336`; Crear lo calcula en el navegador con `data-usd-*`). Lo que no existe: saldo, precio al cliente,
pasarela, ni un freno previo (hoy «sin saldo» se detecta cuando el proveedor ya rechazó, `saldo.py`).

## 1. Vocabulario

- **Costo**: lo que Creatv le paga al proveedor. Es la tabla `gasto` de hoy, sin cambios.
- **Precio**: lo que paga el proyecto. `precio = costo × margen`.
- **Margen**: multiplicador (1,5 por defecto). Global en `kv` (`cobros:margen_global`), y un proyecto puede tener el
  suyo (`cuenta_saldo.margen`, NULL = el global).
- **Saldo**: suma del libro de movimientos del proyecto.
- **Disponible**: saldo − reservas vivas (§4).
- **Proyecto que cobra**: `cuenta_saldo.cobrar = 1`. Si no hay fila o está en 0, nada de este documento lo toca.

Todo monto del libro se guarda en **milésimas de dólar, entero** (`US$ 1,50 = 1500`). En pantalla se redondea a
centavos con `gastos.formatear`. Así un cobro de US$ 0,015 no se pierde ni se inventa.

## 2. Datos (migración 0032)

```
cuenta_saldo
  cliente          String(80)  PK
  cobrar           Boolean     NOT NULL default 0
  margen           Float       NULL      -- NULL = cobros:margen_global
  umbral_aviso     Integer     NOT NULL default 5000   -- milésimas (US$ 5)
  actualizado_en   String(19)
  actualizado_por  String(80)

movimiento_saldo                         -- el libro; nunca se borra ni se edita, salvo §3.3
  id               Integer PK autoincrement (sqlite_autoincrement: un id no se reutiliza)
  cliente          String(80)  NOT NULL, index
  creado_en        String(19)  NOT NULL
  tipo             String(16)  NOT NULL  -- recarga | cobro | reverso | no_cobrado | ajuste | anulacion
  milesimas        Integer     NOT NULL  -- con signo: recarga +, cobro −, reverso +, anulacion −, no_cobrado 0
  gasto_id         Integer     NULL      -- cobro / reverso / no_cobrado
  recarga_id       Integer     NULL      -- recarga / anulacion
  job_id           String(160) NULL      -- el trabajo del worker que lo originó (§5)
  tarea_id         Integer     NULL
  concepto         String(120) NOT NULL  -- en el idioma del proyecto al escribirlo
  detalle          String(300)
  usuario          String(80)  NULL      -- quién hizo un ajuste o una recarga manual
  extra            JSON
  UNIQUE (tipo, gasto_id)                -- un cobro, un reverso, un no_cobrado por gasto
  UNIQUE (tipo, recarga_id)              -- una acreditación y una anulación por recarga
  INDEX (cliente, creado_en)

reserva_saldo
  cliente          String(80)  NOT NULL
  job_id           String(160) NOT NULL
  milesimas        Integer     NOT NULL
  creada_en        String(19)  NOT NULL
  PK (cliente, job_id)

recarga
  id               Integer PK autoincrement (sqlite_autoincrement)
  cliente          String(80)  NOT NULL, index
  creada_en        String(19)  NOT NULL
  actualizada_en   String(19)
  medio            String(12)  NOT NULL  -- bold | manual
  estado           String(12)  NOT NULL  -- pendiente | aprobada | rechazada | expirada | anulada
  milesimas        Integer     NOT NULL  -- lo que se acredita (USD)
  referencia       String(60)  NOT NULL UNIQUE   -- la que va a Bold: "cv-<id>-<epoch>"
  link_id          String(40)  NULL      -- LNK_… de Bold
  pago_id          String(40)  NULL UNIQUE      -- payment_id de Bold
  moneda_pago      String(3)   NULL      -- lo que Bold reporta (COP)
  total_pago       Integer     NULL
  medio_pago       String(20)  NULL      -- CARD_WEB, PSE, NEQUI…
  usuario          String(80)  NOT NULL  -- quién la pidió (o el admin, si manual)
  nota             String(300)

pago_evento                              -- cada notificación de Bold tal como llegó (auditoría)
  id               Integer PK
  proveedor        String(12)  NOT NULL  -- bold
  evento_id        String(64)  NOT NULL  -- el "id" de la notificación
  tipo             String(24)  NOT NULL  -- SALE_APPROVED, SALE_REJECTED, VOID_APPROVED…
  referencia       String(60)  NULL
  recibido_en      String(19)  NOT NULL
  firma_ok         Boolean     NOT NULL
  resultado        String(40)  NOT NULL  -- acreditada | duplicada | sin_recarga | firma_invalida | ignorada | error
  cuerpo           JSON
  UNIQUE (proveedor, evento_id)
```

Escritor único (regla 5 del repo): **`cobros/libro.py`** escribe `cuenta_saldo`, `movimiento_saldo` y `reserva_saldo`;
**`cobros/recargas.py`** escribe `recarga` y `pago_evento` (y acredita llamando a `libro`). Nadie más.

El saldo se calcula con `SUM(milesimas)` por proyecto sobre el índice `(cliente, creado_en)`. Con miles de filas por
proyecto es una consulta de milisegundos; no se guarda un saldo en caché (YAGNI; una columna duplicada se desincroniza).

## 3. El cobro del uso: una sola puerta

### 3.1 Dónde

`gastos.registrar` ya es la única puerta del costo. Dentro de su misma transacción, después de insertar o actualizar la
fila de `gasto`, llama a `cobros.libro.cobrar_gasto(con, gasto_id, cliente, usd, tipo, entregado)` **dentro de un
savepoint propio** (`con.begin_nested()`): si el cobro falla, el gasto queda anotado igual, el error va a `log.error`
(lo recoge `error_app`) y al admin le llega `avisar_admin("cobro_no_anotado", …)`. Nunca se pierde el registro del costo
por culpa del cobro.

`cobrar_gasto`:

1. Si el proyecto no cobra → no hace nada.
2. `milesimas = ceil(usd × margen × 1000)`, con el margen vigente al primer registro del gasto (queda en
   `extra.margen`).
3. Si `entregado` es falso (§3.4) → escribe `no_cobrado` con `milesimas = 0` y en `extra.precio` lo que habría costado.
4. Si no → escribe `cobro` con `−milesimas`, el concepto (nombre del tipo de gasto en el idioma del proyecto, §9) y el
   `job_id`/`tarea_id` del contexto (§5).
5. Si la tarea de ese gasto ya terminó en error (puede pasar si el registro llega tarde) → escribe además el `reverso`.

### 3.2 Proyectos que no cobraban

Un gasto de un proyecto con «Cobrar» apagado no genera movimiento, y prenderlo después **no cobra hacia atrás**.
Apagarlo deja el saldo como está (se puede volver a prender).

### 3.3 Un gasto que se corrige

`registrar` con la misma referencia actualiza el monto (p. ej. la final que suma un país). Si ese gasto ya tiene `cobro`,
su `milesimas` se recalcula con el `extra.margen` guardado; si además tiene `reverso`, se recalcula igual (siempre el
opuesto exacto del cobro). Es la única edición permitida en el libro y es 1:1 con el costo, que también se edita.
Si el gasto no tenía cobro (el proyecto no cobraba al primer registro), sigue sin tenerlo.

### 3.4 Pagado pero no entregado

`registrar_seguro(..., entregado=False)`: el nuevo argumento (por defecto `True`) para los lugares que hoy anotan «lo
que se pagó aunque la pieza falló» (p. ej. Wan pasando los 20 min, `tareas/flowplus.py`; recuperaciones perdidas).
El plan lista cada llamador con `detalle` de fallo y lo marca. Costo anotado como hoy; al cliente, `no_cobrado`.

### 3.5 La tarea entera termina en error

El worker, en el mismo punto donde hoy marca una tarea en `error` definitivo y corre `AL_INTERRUMPIR`
(`worker.py:182-208`), llama a `cobros.libro.revertir_trabajo(cliente, job_id, motivo)`: escribe un `reverso` por cada
`cobro` de ese `job_id` que no tenga ya uno. Se revierte **por job_id**, no por tarea: una pieza encadenada con
`Continuar` (lanzar → sondear → recuperar) comparte job_id, y si al final la pieza no llegó, no se cobra ninguna parte.
No aplica a la tarea que vuelve a `pendiente` por tener intentos (no es fallo definitivo).

Las rutas sincrónicas (§6.2) que fallan después de cobrar lanzan una excepción que la ruta ya maneja; el cobro de
Claude quedó porque Claude sí respondió. Ruling: en una llamada sincrónica a Claude, «entregado» = Claude respondió.

### 3.6 El aviso

Cada `reverso` o `no_cobrado` dispara `notificaciones.avisar(cliente, "pieza_no_cobrada", …)` (correo si hay SMTP;
siempre bitácora) y aparece como alerta en la pestaña Alertas durante 7 días (§8). Al admin no se le avisa uno por uno:
lo ve en /admin/cobros.

## 4. Antes de cobrar: el freno y la reserva

`cobros.libro.exigir(cliente, costo_usd, job_id=None)`:

- Proyecto que no cobra → no hace nada.
- `precio = ceil(costo_usd × margen × 1000)`; sin precio conocido (`None`) → `precio = 1` (basta con tener saldo
  positivo).
- Si `disponible < precio` → lanza `cobros.SaldoInsuficiente(cliente, precio, disponible)`.
- Si viene `job_id` → inserta la reserva `(cliente, job_id, precio)`; si ya existe (segundo clic del mismo job_id) no
  duplica.

**Reserva viva** = existe una fila `tarea` con ese `job_id` en estado `pendiente` o `en_curso`. `disponible = saldo −
SUM(reservas vivas)`. No hace falta liberarla a mano: al terminar la tarea (bien o mal) deja de estar viva. Un
`Continuar` hereda el job_id, así que la reserva cubre la cadena entera. Las reservas muertas se borran en el
mantenimiento diario. Mientras una tarea viva ya cobró, su cobro y su reserva cuentan las dos: es conservador y dura
lo que dura la tarea.

La comprobación y la reserva van en una transacción. Ruling: entre dos clics exactamente simultáneos puede colarse uno
de más; el saldo puede quedar en negativo por unos centavos, igual que cuando el real supera al estimado. Se acepta.

## 5. Dónde se engancha el freno

### 5.1 Trabajos del worker

`trabajos.encolar(..., costo_estimado=None)` gana un argumento. Si el `tipo` está en **`tareas.TIPOS_QUE_COBRAN`**
(conjunto nuevo en `tareas/__init__.py`, uno por tipo que llama a un proveedor que cobra) llama a
`cobros.libro.exigir(cliente, costo_estimado, job_id)` **antes** de insertar la tarea. Cada ruta de la tabla de §5.3 ya
calcula el estimado para mostrarlo: se lo pasa.

Una prueba recorre `tareas.REGISTRO` y falla si un tipo que llama a `gastos.registrar_seguro` (búsqueda en el código de
su módulo) no está en `TIPOS_QUE_COBRAN` o en una lista explícita de exentos con su motivo.

**Contexto de la tarea.** `worker.ejecutar` fija una `contextvars.ContextVar` con `(tarea_id, job_id)` antes de correr
la función y la limpia al salir; `cobrar_gasto` la lee para anotar `job_id`/`tarea_id` en el cobro. Cada hilo del carril
de Crear tiene su propio contexto.

**Respaldo en el worker.** Antes de correr una tarea de `TIPOS_QUE_COBRAN` que **no** es continuación de una cadena
(no hay otra fila `tarea` con su mismo job_id en estado `hecha`), si el proyecto cobra y su saldo (el saldo, no el
disponible: la reserva de este mismo trabajo no cuenta en su contra) es ≤ 0, la tarea falla sin llamar al proveedor con el mensaje «Sin saldo: recarga para seguir. No se cobró
nada.». Cubre lo que se encola sin pasar por una ruta (modo automático de Experimentos, lotes de Sprints que el worker
encola, cualquier camino olvidado).

### 5.2 Rutas que cobran dentro de la petición

No pasan por el worker. Cada una llama a `cobros.libro.exigir(cliente, costo)` antes de llamar al proveedor:

| Dónde | Qué |
|---|---|
| `organico.py:563` | texto orgánico (caption) |
| `audios.py:260/404` | locución |
| `voces_propias.py:294/302/357` | voces propias |
| `final_edition/__init__.py:424/448/856` | final |
| `referentes/rutas.py:328/392/399` | Adaptar / leer referente |
| `guiones/refinador.py:519` | chat de Flow Plus |
| `importador.py:563` | regla de producto |
| `dashboard.py` (llamador de tipo `otro`) | el plan confirma qué es |
| `referentes/traducir.py:65` | traducción de referentes |

El plan verifica cada uno (algunos corren en el worker aunque estén fuera de `tareas/`).

### 5.3 Rutas que encolan trabajos que cobran

Las de Crear (`cf_crear_video`, recrear de referentes), Final edition (guion, producir), Mi música, Audios, voces
propias (diseñar, clonar), Anuncio hablado, Experimentos (lanzar), editor (transcribir, voz), Sprints (sugerir,
reescribir, ideas, lote, QA), Referentes (traer, clasificar), Flow Plus (cadena, pipeline, imágenes), Nicho
(investigación, estudios, avatares) y Triple Whale (evaluar). Lista completa con archivo:línea en el plan.
`flowplus_recuperar`, `edicion_producir` y `exp_decidir` no cobran (exentos con motivo).

### 5.4 Cómo se ve el rechazo

Un solo manejador: `@app.errorhandler(cobros.SaldoInsuficiente)`.

- Petición JSON o fetch → `402` con `{"ok": false, "error": "<frase>", "saldo_insuficiente": true,
  "recargar_url": "<Configuración › Saldo>"}`. El JS común de los formularios que ya pinta `error` lo muestra.
- Formulario normal → flash con la frase y enlace, y vuelve a la página de origen (`request.referrer` si es del mismo
  host, si no Configuración › Saldo).

Frase: «Saldo insuficiente: esto cuesta ≈ US$ 1,50 y tienes US$ 0,40 disponibles. Recarga para seguir.» Sin cobrar nada.

Las rutas que envuelven `encolar` en un `except Exception` genérico se ajustan para dejar pasar `SaldoInsuficiente`
(el plan las lista). Los encoladores que corren en el worker (§5.1) la capturan y lo dejan dicho en su entidad.

## 6. Los precios que se ven

Regla: en un proyecto que cobra, **toda persona que lo mira ve precios, no costos** (también el admin en los botones:
ve lo que se le cobrará al proyecto). El costo y el margen solo aparecen en /admin/cobros y en la columna «costo» que
Configuración › Gasto muestra **solo al admin** (§7).

- `gastos.estimar` sigue devolviendo `usd` = costo (lo usan reservas y cálculos) y su `texto` («≈ US$ 0,30») pasa a
  formatearse con `gastos.texto_precio(usd)`, que multiplica por el margen del proyecto de la petición en curso
  (`flask.g.margen_precio`, fijado por un `before_request` a partir del `<cliente>` de la URL; fuera de una petición o en
  un proyecto que no cobra, el margen es 1). Agrega también `usd_precio`.
- Crear y los demás formularios que calculan en el navegador con `data-usd-*`: `base.html` expone
  `data-margen-precio` en `<body>` y la función común que formatea «≈ US$» multiplica por él. El plan lista cada
  `data-usd-*` y cada «≈» armado en JS.
- Prueba de humo obligatoria: renderiza las pestañas del proyecto como cliente de un proyecto que cobra con margen 1,5 y
  un costo conocido, y falla si aparece la cifra del costo en lugar de la del precio.

## 7. Lo que ve el cliente

**Barra lateral.** En un proyecto que cobra, el chip pasa a «Saldo: US$ 37,20 · Recargar» (enlace a Configuración ›
Saldo). Con saldo bajo el umbral se pinta en tono de aviso; en cero o negativo, en tono de bloqueo. El «Este mes:
generación» del chip muestra lo **cobrado** del mes (cobros − reversos) a quien no es admin; al admin, costo y cobrado.
Proyecto que no cobra: el chip de hoy, sin cambios.

**Configuración › Saldo y recargas** (sección nueva en `_tab_settings.html`, ancla `#saldo`, visible solo si el proyecto
cobra o si mira el admin):

- Saldo, disponible (si hay reservas) y el umbral de aviso.
- **Recargar**: botones de US$ 20, 50, 100 y 200 y un campo libre (entero, mínimo 10, máximo 1 000). «Pagar con Bold»
  crea la recarga y redirige al checkout. Debajo: «Tarjetas de cualquier país; en Colombia también PSE y Nequi. Bold
  cobra en pesos colombianos a la tasa del día.» Sin llaves de Bold en el `.env`: el botón no aparece y dice «Las
  recargas en línea todavía no están disponibles; escríbenos para recargar.»
- **Movimientos**: tabla paginada (50) con fecha, concepto, monto y saldo después de cada uno; CSV con todo
  (`/cliente/<c>/saldo/movimientos.csv`, `;`, BOM, como el de gasto).
- **Recargas**: las últimas 20 con estado; una pendiente tiene «Verificar».

**Configuración › Gasto** en un proyecto que cobra: a quien no es admin le muestra lo cobrado (mismas tablas de hoy,
alimentadas por el libro); al admin le muestra las dos columnas, costo y cobrado. Lo mismo los CSV de gasto
(`gasto/mes.csv`, `gasto/todo.csv`) y la ficha del Tablero. El plan inventaría todo lugar que muestre una cifra de la
tabla `gasto` a un cliente (incluido el centro de resultados de Experimentos y la cifra de costo de Final edition) y lo
pasa por `cobros.vista.gasto_para(cliente, es_admin)`.

## 8. Avisos

Alertas calculadas (fuente nueva `_fuente_cobros` en `alertas.py`, solo si el proyecto cobra):

| Clave | Nivel | Cuándo |
|---|---|---|
| `cobros:sin_saldo` | bloquea | disponible ≤ 0 |
| `cobros:saldo_bajo` | atención | 0 < saldo < umbral |
| `cobros:no_cobrado:<mov_id>` | info | un `reverso` o `no_cobrado` de los últimos 7 días |
| `cobros:recarga_pendiente:<id>` | info | una recarga de Bold pendiente de hace más de 15 min |

Correos (`notificaciones.avisar`, tipos nuevos en `TIPOS`): recarga acreditada; saldo bajo (una vez por cruce del
umbral, recordado en `kv` `cobros:aviso_bajo:<cliente>` y limpiado al recargar); pieza no cobrada. Al admin
(`avisar_admin`): cada recarga acreditada, cada anulación de Bold, cada cobro que no se pudo anotar.

## 9. Recargas con Bold

### 9.1 Llaves

En el `.env` raíz: `BOLD_LLAVE_IDENTIDAD` y `BOLD_LLAVE_SECRETA` (las de producción o las de pruebas del panel de Bold;
en pruebas la secreta del webhook es la cadena vacía, y `BOLD_PRUEBAS=1` lo permite solo así). Sin
`BOLD_LLAVE_IDENTIDAD`, las recargas en línea están apagadas. Ninguna llave llega a logs, flashes ni eventos
(`cola.sin_token`).

### 9.2 Crear la recarga

`POST /cliente/<c>/saldo/recargar` (mismo origen, sesión con acceso al proyecto, proyecto que cobra, tope de 10 por
hora por proyecto en `kv`):

1. Valida el monto (entero, 10 a 1 000).
2. Inserta `recarga(estado=pendiente, medio=bold)` y arma `referencia = "cv-<id>-<epoch>"` (≤ 60, alfanumérica y
   guiones, como pide Bold).
3. `cobros/bold.py` crea el link: `POST https://integrations.api.bold.co/online/link/v1` con
   `Authorization: x-api-key <identidad>`, `amount_type: "CLOSE"`, `amount: {currency: "USD", total_amount: <monto>,
   tip_amount: 0, taxes: []}`, `reference`, `description` («Recarga Creatv · <proyecto>», ≤ 100), `callback_url`
   (`PLATAFORMA_URL/cliente/<c>/saldo/recarga/<id>`, nunca del encabezado Host), `expiration_date` a 24 h,
   `payer_email` si la cuenta tiene correo verificado. Tiempo de espera 15 s.
4. Guarda `link_id` y redirige a la `url` del checkout de Bold. Si Bold falla, la recarga queda `rechazada` con el
   motivo en palabras y la persona vuelve a Configuración › Saldo con el aviso.

### 9.3 Confirmar el pago

Una recarga solo se acredita por **lo que dice Bold desde el servidor**, nunca por los parámetros de la URL de vuelta.

- **Webhook** `POST /pagos/bold/webhook`: exento de la barrera CSRF y del guard de sesión (lista explícita de endpoints
  exentos, con su motivo al lado). Lee el cuerpo crudo, verifica la firma (`x-bold-signature` = HMAC-SHA256 hex del
  cuerpo en base64 con la llave secreta; `hmac.compare_digest`), guarda el evento en `pago_evento` (único por
  `evento_id`: un reenvío no se procesa dos veces) y responde 200 en menos de 2 s. Firma inválida → 401 y
  `pago_evento.resultado = firma_invalida`, sin tocar recargas. Tope de tamaño del cuerpo: 64 KB.
  - `SALE_APPROVED` con `metadata.reference` de una recarga `pendiente` → `aprobada`, guarda `pago_id`, moneda, total y
    medio de pago, y acredita `recarga` con `+milesimas` **de la recarga** (los USD que eligió la persona; Bold reporta
    el total en pesos, que queda solo como registro). Todo en una transacción; `UNIQUE(tipo, recarga_id)` y
    `UNIQUE(pago_id)` impiden acreditar dos veces.
  - `SALE_REJECTED` → `rechazada`.
  - `VOID_APPROVED` de una recarga `aprobada` → `anulada` y movimiento `anulacion` con `−milesimas` (el saldo puede
    quedar negativo) y aviso al admin.
  - Referencia desconocida → `sin_recarga`, aviso al admin, 200 (para que Bold no reintente).
- **Respaldo por consulta** (`cobros.recargas.verificar(recarga_id)`): `GET /online/link/v1/<link_id>`; `status ==
  "PAID"` → mismo camino de acreditación que el webhook (idempotente); `EXPIRED` → `expirada`. Corre en tres
  momentos: al volver del checkout (la página de vuelta lo llama una vez y luego sondea cada 3 s hasta 60 s), con el
  botón «Verificar» y en una tarea periódica del worker cada 10 min para las pendientes de menos de 26 h.

### 9.4 Página de vuelta

`GET /cliente/<c>/saldo/recarga/<id>`: «Verificando tu pago…» con barra (`data-poll-job` no aplica: sondea
`/cliente/<c>/saldo/recarga/<id>/estado`, JSON). Aprobada → «Listo: sumamos US$ 50,00 a tu saldo» y enlace de vuelta.
Rechazada o expirada → la frase y «Intentar de nuevo». Pendiente pasados 60 s → «Bold todavía no confirma el pago; te
avisaremos cuando llegue. Puedes cerrar esta página.»

## 10. Lo que ve el admin: /admin/cobros

`requiere_admin`. Plantilla `admin_cobros.html` sobre la base visual común.

- **Margen global** (campo, 1,00 a 5,00) y su guardado.
- **Tabla de proyectos**: proyecto · cobra (interruptor) · margen propio (vacío = global) · umbral · saldo · disponible
  · recargado del mes · cobrado del mes · costo del mes · ganancia del mes (cobrado − costo de lo cobrado). Una
  consulta por columna agregada, nunca una por fila (regla 8).
- **Recarga manual** por proyecto: monto (puede ser negativo para un ajuste, con nota obligatoria), nota, y tipo
  (recarga | ajuste). Escribe `recarga(medio=manual, estado=aprobada)` + movimiento `recarga`, o un movimiento
  `ajuste`, con el usuario del admin.
- **Últimos eventos de Bold** (20): hora, tipo, referencia, resultado. Si no llegó ninguno en 7 días con recargas
  pendientes, una línea de aviso.
- Enlace desde el panel de admin existente.

Al prender «Cobrar» en un proyecto sin saldo, la pantalla avisa: «Este proyecto no tiene saldo: desde ahora no podrá
generar nada que cueste hasta que recargue.»

## 11. Seguridad

Pasada obligatoria del subagente `auditor-seguridad` antes de mezclar. Puntos fijos:

- Webhook: firma HMAC con `compare_digest`, cuerpo crudo, tope de tamaño, idempotencia por `evento_id` y `pago_id`,
  respuesta que no revela nada (200/401 sin detalle). El único POST de la app que acepta otro origen.
- Recargas: monto validado en el servidor; la recarga es del proyecto de la URL (guard por cliente); la URL de vuelta
  sale de `PLATAFORMA_URL`; la vuelta nunca acredita.
- Aislamiento: un cliente solo ve el libro, las recargas y el saldo de su proyecto; el margen y el costo no salen en
  ninguna respuesta a quien no es admin (prueba de §6).
- Admin: interruptor, margen, recarga manual y ajuste solo con `requiere_admin` y mismo origen.
- Bold se llama con `requests` a un host fijo (`integrations.api.bold.co`), sin URLs que escriba una persona.

## 12. Rulings (decisiones tomadas sin preguntar)

1. **Milésimas enteras** en el libro; redondeo del cobro **hacia arriba** a la milésima.
2. **Margen del primer registro**: si el margen cambia, los gastos ya cobrados no se recalculan con el nuevo.
3. **Reserva atada al job_id**, viva mientras la tarea lo esté; sin liberación manual.
4. **Revertir por job_id** cuando la tarea termina en error definitivo.
5. **Llamadas sincrónicas a Claude**: entregado = Claude respondió.
6. **Recarga mínima US$ 10, máxima US$ 1 000, en dólares enteros**. Lo acreditado son los USD elegidos; la comisión de
   Bold la absorbe el margen.
7. **Saldo negativo permitido** (real > estimado, dos clics simultáneos, anulación): bloquea todo lo que cobra hasta
   recargar.
8. **Sin cobro hacia atrás** al prender «Cobrar».
9. **El admin también ve precios** en los botones de un proyecto que cobra.
10. **El saldo es por proyecto**, no por usuario: todos los usuarios del proyecto comparten saldo (hoy cada cuenta
    cliente tiene un solo proyecto).
11. **Lo que cobra Creatv a su propia cuenta** (`_creatv`, barridos del admin) nunca cobra: no tiene `cuenta_saldo`.
12. **La pauta de Meta no pasa por el saldo** (la paga el cliente en su cuenta publicitaria).
13. **Nada al flujo viejo de Higgsfield**.

## 13. Fuera de esta versión (van a `docs/pendientes.md`)

- Facturación electrónica ante la DIAN e IVA sobre el servicio (decisión de Daniel con su contador).
- Suscripción mensual y recarga automática.
- Otra pasarela (PayPal, Mercado Pago, transferencia internacional): `cobros/bold.py` es el único que habla con Bold.
- Precios por debajo del costo para promociones o créditos de regalo con vencimiento.
- Prueba real con el sandbox de Bold: espera las llaves de pruebas de Daniel (`BOLD_LLAVE_IDENTIDAD`/`SECRETA` de
  pruebas en el `.env` local) y registrar la URL del webhook en el panel de Bold.

## 14. Pruebas

- **Libro**: cobro con margen y redondeo; `no_cobrado`; corrección de un gasto (§3.3); reverso por job_id y que no se
  duplica; proyecto que no cobra no escribe nada; prender sin cobro hacia atrás; saldo y disponible con reservas vivas
  y muertas; el savepoint: un cobro que falla no pierde el gasto.
- **Freno**: `encolar` de un tipo que cobra sin saldo → `SaldoInsuficiente` y ninguna fila en `tarea`; con saldo →
  reserva; segundo clic del mismo job_id no reserva dos veces; el respaldo del worker no llama al proveedor; el manejador
  responde 402 a un fetch y flash a un formulario; la prueba de cobertura de `TIPOS_QUE_COBRAN`.
- **Worker**: una tarea con `Continuar` que falla al final revierte los cobros de toda la cadena; la `ContextVar` no se
  cruza entre dos hilos del carril de Crear.
- **Bold**: firma válida, inválida, cuerpo alterado; evento repetido; `SALE_APPROVED` con referencia desconocida;
  dos aprobaciones del mismo pago; `VOID_APPROVED`; `verificar` con `PAID`, `ACTIVE` y `EXPIRED` (HTTP falso); llaves que
  no aparecen en logs ni en `pago_evento`.
- **Pantallas**: la prueba de humo de §6; Configuración › Saldo como cliente y como admin; /admin/cobros sin N+1
  (contador de consultas); el chip de la barra lateral en los tres tonos; captura de pantalla en escritorio y celular.
- **Mutaciones** (subagente `revisor`): quitar el savepoint, el `ceil`, la verificación de firma, el `UNIQUE` de
  `pago_id`, la condición de reserva viva o el `exigir` de una ruta, y comprobar que alguna prueba falla.

## 15. Despliegue

Migración 0032 (tablas nuevas, nada se altera). Reinicio de los dos servicios (cambian el worker y las rutas). Con todo
apagado por defecto, el despliegue no cambia lo que ve ni paga ningún proyecto. Después, Daniel: llaves de Bold en el
`.env` del VPS, la URL del webhook (`https://app.creatvmachine.com/pagos/bold/webhook`) en el panel de Bold, y prender
«Cobrar» proyecto por proyecto en /admin/cobros.
