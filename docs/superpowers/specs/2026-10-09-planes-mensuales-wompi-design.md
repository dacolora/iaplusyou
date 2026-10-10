# Planes mensuales y Wompi (2026-10-09)

Pedido de Daniel (2026-10-09), sobre los cobros ya en producción (spec `2026-10-08-cobros-saldo-prepagado-design.md`,
skill `cobros`): «un amigo vende un paquete mensual de US$ 1 000… que la persona no solo pague por generación, sino que
tenga una suscripción mensual; que sienta que el paquete le sale más barato que hacerlo por aparte». Y: «necesito la mejor
manera de generar ganancia y que los clientes estén felices». Bold quedó bloqueado (su usuario personal ocupa la cédula y
Bold no tiene suscripciones): se pasa a **Wompi** para todo. Daniel aprobó el rumbo por partes en la conversación y pidió
avanzar sin más preguntas; lo que quedaba abierto está en §12 como rulings.

Decisiones de Daniel:

1. **Dos formas de comprar.** A la carta (recarga y paga cada cosa) y **plan mensual**.
2. **A la carta sube a ×2**: precio = costo del proveedor × 2 (antes ×1,5).
3. **Plan: bolsa de saldo + lo barato gratis**, sin bonos. El cliente paga el precio del plan y ese monto entra como saldo
   del plan, uno a uno. Lo que hace más barato el plan es el **precio de miembro** (margen menor), **lo barato gratis** y la
   **prioridad**. Primer plan: **US$ 1 000/mes, margen ×1,25**. Editable desde el admin.
4. **Úsalo o piérdelo**: cada mes la bolsa del plan se renueva y lo que sobró se pierde. Lo que el cliente recargó aparte
   a la carta **no** se pierde.
5. **Renovación automática** con la tarjeta (o Nequi) guardada en Wompi. Clientes del exterior pagan con Visa,
   Mastercard o Amex de cualquier país; Wompi cobra en pesos.
6. **Wompi para todo**: también las recargas a la carta. El módulo de Bold queda en el código, apagado sin llaves.

Recomendaciones aceptadas («listo»): precio fijo en dólares cobrado en pesos a la TRM del día; plan anual con dos meses
gratis; medidor visible del plan; días de gracia si falla la tarjeta; lo gratis con tope de uso justo; mostrar el ahorro.

Lo que no cambia: el libro (`movimiento_saldo`), el freno (`exigir` / `trabajos.encolar` / respaldo del worker), la
reversión, el «Cobrar» por proyecto, las pantallas de saldo y la regla «nada pago sin precio a la vista». Referencia técnica
de la API: `docs/pagos/wompi-api.md` (informe del 2026-10-09 con URL y citas de la documentación oficial).

## 1. Vocabulario

- **A la carta**: proyecto que cobra y no tiene plan vigente. Margen = el propio del proyecto o el global (2,0).
- **Plan**: producto que vende Creatv (`plan`): nombre, precio mensual en USD, precio anual opcional, margen de miembro,
  tope de lo incluido, activo.
- **Suscripción**: la relación de un proyecto con un plan (`suscripcion`): estado, ciclo (mensual o anual), fuente de pago
  de Wompi, próxima renovación.
- **Periodo**: un mes de plan (`periodo_plan`): inicio, fin, la foto del plan de ese mes (precio, margen, tope) y la bolsa
  que se acreditó. Un periodo existe solo si está pagado (o cubierto por un pago anual, o activado a mano por el admin).
- **Bolsa del plan / saldo propio**: el saldo sigue siendo uno solo (`SUM(movimiento_saldo.milesimas)`); la bolsa del plan
  se calcula (§3).
- **Incluido**: una generación «barata» que el plan regala (§4).

## 2. Datos (migración 0038; era la 0035 hasta mezclar main el 2026-10-10, que ya tenía 0035–0037)

```
plan
  id                Integer PK (sqlite_autoincrement)
  nombre            String(60)  NOT NULL
  precio_usd        Integer     NOT NULL           -- mensual, dólares enteros
  precio_anual_usd  Integer     NULL               -- NULL = sin opción anual
  margen            Float       NOT NULL           -- 1,00–5,00, el de miembro (1,25 el primero)
  tope_incluido_usd Float       NOT NULL default 25 -- costo de proveedor regalado por mes (§4)
  activo            Boolean     NOT NULL default 1  -- archivado = no se ofrece; las suscripciones siguen
  orden             Integer     NOT NULL default 0
  creado_en, actualizado_en String(19)

suscripcion
  id                Integer PK (sqlite_autoincrement)
  cliente           String(80)  NOT NULL, index
  plan_id           Integer     NOT NULL
  ciclo             String(8)   NOT NULL           -- mensual | anual
  estado            String(12)  NOT NULL           -- activa | cancelada | morosa | terminada
  renovar           Boolean     NOT NULL default 1  -- false tras cancelar: vive hasta fin de periodo
  fuente_pago_id    String(40)  NULL               -- payment_source id de Wompi
  medio_fuente      String(12)  NULL               -- CARD | NEQUI
  fuente_resumen    String(40)  NULL               -- «Visa ···4242» (lo que devuelve Wompi; nunca el número)
  correo            String(120) NULL
  cubierto_hasta    String(19)  NULL               -- fin de lo pagado (anual: 12 periodos)
  proximo_cobro     String(19)  NULL
  intentos_fallidos Integer     NOT NULL default 0
  usuario           String(80)  NOT NULL           -- quién la creó
  creada_en, actualizada_en String(19)
  -- a lo más UNA suscripción no terminada por cliente (índice único parcial estado != 'terminada')

periodo_plan
  id                Integer PK (sqlite_autoincrement)
  cliente           String(80)  NOT NULL, index
  suscripcion_id    Integer     NOT NULL
  inicio            String(19)  NOT NULL
  fin               String(19)  NOT NULL
  precio_usd        Integer     NOT NULL           -- foto del plan para ese mes
  margen            Float       NOT NULL
  tope_incluido_usd Float       NOT NULL
  credito_milesimas Integer     NOT NULL           -- lo que se acreditó como bolsa
  pago_id           Integer     NULL               -- pago_plan que lo cubre (NULL = activado a mano)
  cerrado           Boolean     NOT NULL default 0 -- ya se venció lo que sobró
  UNIQUE (suscripcion_id, inicio)

pago_plan
  id                Integer PK (sqlite_autoincrement)
  cliente           String(80)  NOT NULL, index
  suscripcion_id    Integer     NOT NULL
  ciclo             String(8)   NOT NULL
  usd               Integer     NOT NULL
  trm               Float       NULL
  monto_cop_centavos Integer    NULL
  referencia        String(60)  NOT NULL UNIQUE     -- «pl-<suscripcion>-<AAAAMMDD>-<intento>»
  transaccion_id    String(40)  NULL UNIQUE         -- id de la transacción de Wompi
  estado            String(12)  NOT NULL           -- pendiente | aprobado | rechazado | error | anulado
  motivo            String(300) NULL
  creado_en, actualizado_en String(19)
  medio             String(12)  NOT NULL           -- wompi | manual
  usuario           String(80)  NULL
```

`movimiento_saldo` gana la columna `periodo_id` (Integer NULL) y `UNIQUE(tipo, periodo_id)`, y tres tipos nuevos:
`plan` (+crédito de un periodo), `vencimiento` (−lo que sobró al cerrar un periodo), `incluido` (0, una generación
regalada; `extra.precio` dice cuánto habría costado). `recarga` gana `medio` = `wompi` (además de `bold` y `manual`) y
`pasarela_ref` (String(40), el id de la transacción de Wompi; `pago_id` de Bold se mantiene).

Escritores únicos (regla 5 del repo): `cobros/libro.py` sigue siendo el único que escribe `movimiento_saldo`,
`cuenta_saldo` y `reserva_saldo` (agrega `acreditar_plan`, `vencer_periodo` y la rama `incluido`). **`cobros/planes.py`**
escribe `plan`, `suscripcion`, `periodo_plan` y `pago_plan`. `cobros/recargas.py` sigue con `recarga` y `pago_evento`.

## 3. La bolsa del plan (sin partir el saldo)

El saldo sigue siendo una sola suma. La bolsa del plan de un periodo vigente se calcula **primero el plan** (FIFO):

```
gastado_en_periodo = −SUM(milesimas) de movimientos cobro + reverso del cliente con creado_en en [inicio, fin)
bolsa_restante     = max(0, credito_milesimas − gastado_en_periodo)
saldo_propio       = saldo − bolsa_restante
```

Todo cobro del periodo consume primero la bolsa; lo que excede, el saldo propio (recargas a la carta, que nunca vencen).
Al **cerrar** un periodo (`fin` ≤ ahora), `libro.vencer_periodo(periodo_id)` escribe `vencimiento` por
`−bolsa_restante` (0 si se gastó todo; con `UNIQUE(tipo, periodo_id)` es idempotente) y marca `cerrado`. Si el saldo total
es menor que la bolsa calculada (porque hubo una anulación o un ajuste negativo), el vencimiento se limita a no dejar el
saldo por debajo de 0 por culpa del vencimiento.

Al **abrir** un periodo pagado, `libro.acreditar_plan(periodo_id)` escribe `plan` por `+credito_milesimas`
(= `precio_usd × 1000`), también idempotente. El orden en la renovación es: cerrar el periodo viejo, abrir el nuevo, en una
transacción con el candado del libro.

## 4. Precio de miembro y lo incluido

- **Margen efectivo** (`libro._cuenta`): si el proyecto tiene un periodo abierto ahora → el `margen` del periodo; si no →
  el propio del proyecto o el global. El global por defecto pasa a **2,0** (ruling: se cambia el valor por defecto en el
  código y, en el despliegue, el valor guardado en `kv` si sigue en 1,5 — Daniel lo pidió explícito).
- **Incluido**: `cobros/planes.TIPOS_INCLUIDOS` = los tipos de gasto de Claude y transcripción: `guion`, `regla_producto`,
  `caption_organico`, `adaptar_referente`, `leer_referente`, `sugerir_ia`, `clasificacion`, `refinar_prompt`,
  `guion_clips`, `ideas`, `pedidos`, `revision`, `evaluacion`, `transcripcion` y el diagnóstico (el plan revisa la lista
  contra `gastos.TIPOS`). **No** incluye `recoleccion` (Apify, dólares) ni nada de video, imagen, voz o música.
  En `cobrar_gasto`, con periodo abierto y tipo incluido: si el costo incluido acumulado del periodo + este costo ≤
  `tope_incluido_usd` → movimiento `incluido` (0 milésimas, `extra.precio` con lo que habría costado a precio de miembro y
  `extra.costo`); si no → `cobro` normal a precio de miembro. El freno (`exigir`) trata un tipo incluido dentro del tope
  como precio 0 (no exige saldo).
- **Tope**: se mide en **costo de proveedor** (lo que le cuesta a Creatv), 25 USD por mes en el primer plan. Al 80 % y al
  100 % se avisa al admin (no al cliente). Pasado el tope, el cliente paga esas cosas a precio de miembro: la pantalla del
  plan lo dice («Lo incluido de este mes ya se usó; desde ahora se cobra a precio de miembro»).
- **Prioridad**: `trabajos.encolar` sube a 6 la prioridad de las tareas de un proyecto con periodo abierto (las normales son
  5 y los lotes < 5). No cambia los carriles del worker.
- Los precios de la pantalla (`|precio`, `texto_precio`) ya usan el margen del proyecto: con plan muestran el precio de
  miembro; las cosas incluidas muestran «Incluido en tu plan» mientras quede tope (la etiqueta sale de `planes.incluye`,
  una lectura memorizada por petición).

## 5. Wompi (la pasarela)

Llaves en el `.env` raíz: `WOMPI_LLAVE_PUBLICA`, `WOMPI_LLAVE_PRIVADA`, `WOMPI_SECRETO_EVENTOS`,
`WOMPI_SECRETO_INTEGRIDAD`. El prefijo dice el ambiente (`pub_test_`/`pub_prod_`): `cobros/wompi.py` elige
`https://sandbox.wompi.co/v1` o `https://production.wompi.co/v1` según la llave y **rechaza llaves de pruebas si el host de
`PLATAFORMA_URL` no es local** (la misma regla que `BOLD_PRUEBAS`). Ninguna llave en logs, flashes, eventos ni respuestas.
`cobros/wompi.py` es el único módulo que habla con Wompi; `cobros/pasarela.py` decide cuál se usa para recargas: Wompi si
tiene sus cuatro llaves, si no Bold si tiene las suyas, si no ninguna (solo recarga manual).

### 5.1 Recarga a la carta con Wompi (Web Checkout)

1. `POST /cliente/<c>/saldo/recargar` (la ruta de hoy): valida el monto (10–1 000 USD enteros), lee la TRM (§6), calcula
   `amount_in_cents = ceil(usd × trm) × 100`, crea `recarga(medio=wompi, estado=pendiente, referencia="cv-<id>-<epoch>")`.
2. Redirige a `https://checkout.wompi.co/p/` con `public-key`, `currency=COP`, `amount-in-cents`, `reference`,
   `signature:integrity` = `sha256(reference + amount_in_cents + "COP" + secreto_integridad)` hex,
   `redirect-url` = `PLATAFORMA_URL/cliente/<c>/saldo/recarga/<id>` y `customer-data:email` si hay correo verificado.
3. Wompi vuelve con `?id=<transaccion>`; la página de vuelta (la de hoy) no acredita: el servidor consulta
   `GET /v1/transactions/<id>` con la llave privada, comprueba que `reference`, `amount_in_cents` y `currency` sean los de
   la recarga, y solo con `status = APPROVED` acredita los **USD elegidos** (no los pesos).
4. El evento `transaction.updated` (§5.3) acredita igual, idempotente con lo anterior (`UNIQUE(pasarela_ref)`, `UPDATE`
   condicional sobre el estado, candado del libro).
5. La periódica `cobros_verificar_recargas` consulta también las de Wompi pendientes de < 26 h con transacción conocida.

### 5.2 Suscribirse y registrar la tarjeta

1. Configuración › Plan muestra los planes activos. «Suscribirme» abre el formulario del plan: ciclo (mensual / anual si
   hay precio anual), correo de cobro, y **dos casillas obligatorias** con los enlaces que da Wompi
   (`GET /v1/merchants/info` → `presigned_acceptance.permalink` y `presigned_personal_data_auth.permalink`) más una tercera
   de Creatv: «Autorizo el cobro automático de US$ X cada mes (en pesos a la TRM del día) hasta que cancele. El saldo del
   plan se renueva cada mes y no se acumula.»
2. La tarjeta se captura con el **widget de tokenización de Wompi** (`widget.js`, `data-widget-operation="tokenize"`,
   llave pública): el número nunca pasa por nuestra página ni por nuestro servidor. Nequi: número de celular →
   `POST /v1/tokens/nequi` y espera a que el usuario apruebe en su app (`GET /v1/tokens/nequi/<token>` hasta `APPROVED`).
   Lo que el widget entrega a nuestro formulario se verifica en sandbox al implementar (`docs/pagos/wompi-api.md` §13.1).
3. El servidor crea la fuente: `POST /v1/payment_sources` (llave privada) con `type`, `token`, `customer_email`,
   `acceptance_token`, `accept_personal_auth`. Guarda `fuente_pago_id`, `medio_fuente` y el resumen («Visa ···4242» de lo
   que devuelva Wompi).
4. Crea la `suscripcion` (estado `activa`, sin periodo aún) y cobra el primer periodo (§5.4) en el acto. Si el cobro sale
   `APPROVED` → abre el periodo y acredita la bolsa. Si sale rechazado → la suscripción queda `terminada`, el cliente ve el
   motivo en palabras y puede intentar con otra tarjeta. Un `PENDING` espera el evento (la pantalla sondea, como la vuelta
   de una recarga).

### 5.3 Eventos

`POST /pagos/wompi/eventos`: exento de la barrera CSRF y del guard de sesión **solo ese endpoint** (como el de Bold).
Verificación: `sha256(valores de signature.properties en orden + timestamp + secreto_eventos)` comparado en tiempo
constante con `signature.checksum` (y con `X-Event-Checksum` si viene). Tope de cuerpo 64 KB, JSON anidado inválido →
400, cupo de eventos sin firma como el de Bold, `pago_evento(proveedor="wompi")` único por (proveedor, id del evento) —
Wompi no manda un id de evento: se usa `sha256(cuerpo)` como `evento_id`. Responde exactamente 200 a todo evento con firma
válida (aunque no sea nuestro), 401 sin firma. `transaction.updated` con `reference` que empieza por `cv-` → recarga;
por `pl-` → pago de plan (`planes.aplicar_transaccion`). Antes de acreditar se relee la transacción con
`GET /v1/transactions/<id>` (defensa en profundidad) cuando el monto o la referencia no cuadran.

### 5.4 El cobro de un periodo

`planes.cobrar_periodo(suscripcion)`: `usd` = precio del plan (anual: `precio_anual_usd`), TRM del día,
`amount_in_cents = ceil(usd × trm) × 100`, `referencia = pl-<suscripcion>-<AAAAMMDD de la renovación>-<intento>` (única),
inserta `pago_plan(pendiente)` y llama `POST /v1/transactions` con `payment_source_id`, `amount_in_cents`,
`currency=COP`, `customer_email`, `reference`, `payment_method.installments=1`, `recurrent=true` y `signature` de
integridad. Respuesta o evento: `APPROVED` → `pago_plan.aprobado` + periodo(s) nuevos + bolsa; `DECLINED`/`ERROR` →
`rechazado`/`error` con el motivo de Wompi; `PENDING` → espera el evento o la consulta. **Nunca dos cobros del mismo
periodo**: antes de cobrar se mira que no haya un `pago_plan` aprobado o pendiente para esa renovación (con el candado).
Anual: un pago cubre 12 periodos; `cubierto_hasta` = inicio + 12 meses; los periodos 2–12 se abren sin cobrar (§7).

## 6. La TRM

`cobros/trm.py`: `https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde DESC` (campo `valor`,
`vigenciadesde`, `vigenciahasta`), con `conectores.url.abrir` o `requests` a ese host fijo, tiempo 10 s, cacheada en `kv`
(`cobros:trm`) por 6 h. Si falla: la última guardada si tiene ≤ 3 días; si no, no se cobra (el cobro de plan reintenta en
la siguiente vuelta; la recarga dice «No pudimos leer la tasa de cambio; intenta en unos minutos»). La TRM usada queda en
`pago_plan.trm` y en `recarga` (`extra` o columna).

## 7. Renovación, gracia y cancelación

Tarea periódica `planes_renovar` (cada 30 min, exenta de cobro: cobra a Wompi pero no genera nada; su gasto no va al
libro):

1. **Cerrar** los periodos con `fin` ≤ ahora no cerrados → `vencimiento`.
2. Por cada suscripción `activa`/`morosa` con `renovar` y sin periodo abierto: si `cubierto_hasta` > ahora (anual) → abre el
   siguiente periodo sin cobrar. Si no → `cobrar_periodo`.
3. **Gracia**: un cobro rechazado deja la suscripción `morosa` y reintenta a las 24 h y a las 48 h (tres intentos en total,
   `intentos_fallidos`). Mientras está morosa **no hay periodo abierto**: el proyecto usa su saldo propio a precio a la
   carta. Al tercer rechazo → `terminada`, aviso al cliente y al admin. Un pago aprobado en cualquier intento abre el
   periodo desde ese momento (el ciclo se corre al día del pago).
4. **Cancelar** (cliente o admin): `renovar = false`, estado `cancelada`; el periodo pagado sigue hasta su `fin`; al
   cerrarse, `terminada`. Nada se devuelve. Un plan anual cancelado sigue hasta `cubierto_hasta`.
5. **Cambiar de tarjeta**: registrar otra fuente (§5.2 pasos 2-3) reemplaza `fuente_pago_id`; si estaba morosa, intenta
   cobrar en el acto.
6. **Avisos** (`notificaciones.avisar` + alertas calculadas): 3 días antes de renovar («Tu plan se renueva el …, por
   US$ X»); renovado; cobro rechazado con lo que falta para perderlo; plan terminado; bolsa al 80 % usada; tope de incluido
   alcanzado (al admin).
7. **Activación manual** (admin): con pago por transferencia, el admin abre un periodo pagado a mano
   (`pago_plan.medio=manual`) desde /admin; sin fuente de pago, la suscripción no se renueva sola (queda `renovar=false` y
   se avisa 3 días antes).

## 8. Lo que ve el cliente

**Configuración › Plan** (apartado nuevo, `id="config-ap-plan"`), visible si el proyecto cobra o si mira el admin:

- Sin plan: las tarjetas de los planes activos con precio mensual (y anual con «2 meses gratis» si lo hay), «precio de
  miembro: tus generaciones cuestan X % menos que a la carta», «ideas, guiones, análisis y revisiones con IA incluidos»,
  «prioridad en la cola», y el botón «Suscribirme».
- Con plan: **el medidor** (bolsa usada / restante con barra, «se renueva el 15 de noviembre por US$ 1 000»), lo incluido
  usado del tope (en porcentaje, no en dólares de costo), **el ahorro del periodo** («este mes ahorraste US$ 210 frente a la
  carta» = lo que habrían costado sus cobros e incluidos a margen a la carta − lo que pagó a margen de miembro),
  la tarjeta registrada («Visa ···4242», «Cambiar tarjeta»), el historial de pagos del plan y «Cancelar plan» (con la
  frase de §7.4 antes de confirmar).
- Morosa: aviso en tono de bloqueo arriba de todo con «Actualizar tarjeta».
- El chip de saldo de la barra lateral suma «Plan: US$ 340 restantes» cuando hay periodo abierto.
- En la página de saldo, el saldo propio y la bolsa del plan se muestran por separado.

## 9. Lo que ve el admin

En **/admin/cobros**: una sección «Planes» (crear, editar, archivar; campos de §2) y por proyecto la suscripción (plan,
estado, próxima renovación, bolsa restante, incluido usado del tope en costo, ganancia del periodo) con acciones «Activar a
mano» (abre un periodo pagado por transferencia), «Cancelar», «Terminar ya» (corta el periodo sin devolución; con nota).
El margen global queda en 2,0 y se ve junto a los márgenes de los planes. La tabla de eventos muestra Bold y Wompi.

## 10. Seguridad

Pasada del `auditor-seguridad` y del `guardian-gasto` antes de mezclar. Fijo: firma de eventos verificada antes de tocar
nada; solo ese endpoint exento; montos y referencia comprobados contra lo guardado; la vuelta del checkout nunca acredita
sin consultar a Wompi; el número de tarjeta jamás pasa por la app (widget de Wompi); las llaves de pruebas solo en host
local; las casillas de aceptación son obligatorias y se guarda cuándo y quién aceptó (`suscripcion` +
`extra.aceptacion` con los dos tokens y la hora); un proyecto solo ve y cancela su suscripción; el cobro automático solo lo
dispara la periódica (nunca una ruta GET).

## 11. Pruebas

- Bolsa: FIFO con recargas propias mezcladas; vencimiento exacto e idempotente; vencimiento que no deja el saldo negativo;
  anual abre 12 periodos sin cobrar.
- Margen efectivo con y sin periodo; incluido dentro y fuera del tope (y el freno con precio 0); prioridad 6.
- Wompi: firma de integridad (el ejemplo de la doc con un secreto de prueba), firma de eventos (válida, inválida, cuerpo
  alterado), evento repetido, transacción de otra referencia, monto que no cuadra, llaves de pruebas en host no local.
- Recarga con checkout: crear, volver con `?id` (consulta APPROVED acredita USD, DECLINED no), evento + vuelta no
  duplican.
- Suscripción: alta con fuente (HTTP de Wompi falso), primer cobro APPROVED/DECLINED/PENDING, renovación, gracia de tres
  intentos, cancelación, cambio de tarjeta, activación manual; nunca dos cobros del mismo periodo bajo concurrencia.
- TRM: lectura, caché, falla con respaldo de ≤ 3 días, falla sin respaldo (no cobra).
- Pantallas: Configuración › Plan en los tres estados, medidor y ahorro correctos, admin de planes; sin N+1; captura en
  escritorio y celular. Mutaciones (`revisor`) sobre la firma, la idempotencia del cobro del periodo y la bolsa.
- Prueba real: sandbox de Wompi en local con las llaves de pruebas de Daniel (tarjeta `4242…` aprobada, `4111…`
  rechazada; Nequi `3991111111` / `3992222222`).

## 12. Rulings

1. **Cancelar**: el plan sigue hasta el fin del periodo pagado; sin devoluciones (lo que recomendé; Daniel: «avanza»).
2. **Un solo saldo y la bolsa calculada primero-el-plan**, en vez de dos saldos: no cambia ninguna consulta de saldo ni el
   freno.
3. **Sin plan anual pagado por adelantado no hay periodos sin pago**: el anual paga 12 periodos de una vez (precio anual
   que fija el admin; por defecto 10 × el mensual).
4. **Precio fijo en USD, cobro en COP a la TRM oficial del día** (datos.gov.co), redondeado al peso hacia arriba.
5. **Incluido con tope en costo de proveedor** (25 USD/mes el primer plan), editable por plan; pasado el tope, precio de
   miembro.
6. **Gracia: tres intentos en 48 h**, sin periodo abierto mientras está morosa (a la carta con su saldo propio).
7. **Margen global 2,0** por defecto y migración del valor guardado si sigue en 1,5.
8. **Bold queda en el código**, apagado sin llaves; Wompi gana si están las dos.
9. **El cobro de Wompi de la suscripción no es un «gasto»** (no pasa por `gastos.registrar`): es ingreso. Las comisiones de
   Wompi no se registran en la app (las ve Daniel en su panel).
10. **Nequi recurrente** se ofrece solo si la prueba en sandbox confirma que el débito no pide aprobación cada mes; si la
    pide, la suscripción solo acepta tarjeta (se decide en la implementación con el sandbox y queda anotado en la skill).

## 13. Fuera de esta versión

- Facturación electrónica DIAN (pendiente de Daniel con su contador).
- Paddle u otra pasarela en dólares para clientes del exterior.
- Varios planes con distintas listas de incluidos (hoy la lista es una sola; cambia el tope por plan).
- Cupones y pruebas gratis.
- Prorrateo al cambiar de plan a mitad de mes (cambiar de plan = cancelar y suscribirse al nuevo cuando termine el
  periodo; el admin puede «Terminar ya» y activar el nuevo a mano).

## 14. Despliegue

Migración 0038 (era la 0035; renumerada al mezclar main el 2026-10-10). Los dos servicios (cambian el worker y las rutas). Al desplegar: margen global a 2,0 si estaba en 1,5;
sembrar el plan «Pro» (US$ 1 000, anual 10 000, margen 1,25, tope 25) **archivado** para que Daniel lo revise y lo active en
/admin/cobros. Las llaves de producción de Wompi las pone Daniel en el `.env` del VPS; la URL de eventos
`https://app.creatvmachine.com/pagos/wompi/eventos` la registra en el panel de Wompi.
