# Cómo se protege el módulo de pagos

Pedido de Daniel (2026-10-12): «cómo nos cuidamos de vulnerabilidades». Este documento junta lo que ya protege los
pagos de Creatv (recargas con saldo, planes mensuales, Wompi y Bold), lo que se arregló tras la auditoría de ese día y
lo que queda como riesgo aceptado. La skill `.claude/skills/cobros/SKILL.md` trae el detalle de cada regla; si el código
y este texto no coinciden, manda el código.

Fuentes: la auditoría de seguridad del módulo (subagente `auditor-seguridad`, 2026-10-12; sin hallazgos críticos ni
altos), dos revisiones de plata (`guardian-gasto`), diez ataques de prueba contra producción (todos rechazados como
debían) y la prueba real con plata de ese día.

## Lo que ya nos protege

| Riesgo | Cómo se frena | Dónde |
|---|---|---|
| Alguien inventa un pago para ganar saldo | Wompi firma cada aviso con un secreto que solo tenemos nosotros (sha256, comparado en tiempo constante, ventana de 72 h hacia atrás y 5 min hacia adelante). Aun firmado, antes de acreditar se vuelve a preguntar la transacción a Wompi y se comparan referencia, monto, moneda y comercio. | `cobros/wompi.py` `evento_valido`; `cobros/recargas.py` `_releer`, `_cuadra` |
| El navegador trae un id de transacción ajeno | El `?id=` de la página de vuelta solo sirve para MOSTRAR cómo va; nunca acredita ni guarda nada. Wompi responde 404 a ids que no son de nuestro comercio (probado en producción). | `cobros/recargas.py` `consultar` |
| Dos clics, dos pestañas o dos procesos acreditan o cobran dos veces | Un candado en la base tomado ANTES de leer, cambios de estado condicionales («solo si sigue pendiente») y restricciones `UNIQUE` en el libro y en las referencias. | `cobros/libro.py` `_candado`; `cobros/planes.py` `_decidir` |
| Cobrar dos veces la renovación de un mes | Cada renovación tiene UNA referencia (`pl-<suscripción>-<fecha>-<n>`); si algo falla se reintenta con esa misma, nunca con otra, y Wompi rechaza con 422 una referencia repetida. Un cobro que «pudo haber salido» queda pendiente y se busca en Wompi antes de reenviar. | `cobros/planes.py`, `cobros/wompi.py` `cobrar_fuente` |
| Cobrar un precio distinto del aceptado | La suscripción guarda el precio que la persona vio y aceptó; toda renovación cobra ese, no el del plan de hoy. | `cobros/planes.py` `_precio_aceptado` |
| Un proyecto ve o toca lo de otro | Toda lectura por id filtra por proyecto (recargas, pagos de plan, tokens de Nequi por sesión); `_guard_por_cliente` en todas las rutas del proyecto. | `cobros/rutas.py`, `dashboard.py` |
| Un sitio ajeno hace que alguien pague o cancele sin saber (CSRF) | Todo POST marcado por el navegador como de otro sitio se rechaza (403). Solo las dos rutas de avisos de las pasarelas están exentas, por nombre exacto, y exigen firma; y la de los reportes de la política de la tarjeta, que no mueve nada y tiene topes. | `dashboard._solo_mismo_origen` |
| La tarjeta pasa por nuestro servidor | El número lo escribe la persona en la ventana de Wompi; a Creatv solo llega un token. La página de la tarjeta tiene su propia política de scripts (solo los nuestros con nonce y los de `checkout.wompi.co`; marcos solo de Wompi; formularios solo hacia aquí). | `templates/plan_alta.html`, `cobros/rutas.py` `CSP_TARJETA` |
| Cuerpos gigantes, JSON anidado sin fin, avisos sin firma a montones | Tope de 64 KB leyendo del stream, 400 para JSON roto o anidado, cupo propio para avisos sin firma. | `cobros/rutas.py` `wompi_eventos`, `cobros/recargas.py` |
| Una tasa de cambio rara cobra de más o regala el plan | La TRM oficial se acepta solo entre 2 500 y 7 000 COP/USD y sin saltos de más de 8 %; si no, no se cobra en pesos hasta que el admin la acepte. | `cobros/trm.py` |
| Llaves en registros o pantallas | Ninguna llave llega a registros, avisos, eventos guardados ni páginas (`cola.sin_token`); las llaves de pruebas no funcionan con el servidor público. | `cobros/wompi.py`, `cobros/bold.py` |
| Una tarjeta robada paga planes | «Cobrar» lo prende Daniel proyecto por proyecto: sin eso nadie puede pagar ni suscribirse. | `/admin/cobros` |

## Lo que se arregló el 2026-10-12

- **La firma de los avisos de Wompi** leía el `timestamp` del lugar equivocado: todo aviso verdadero se rechazaba. Desplegado ese día (d3cf88da).
- **Recargas o cobros de plan que Wompi sí hizo pero cuyo aviso se perdió (PND-296):** la periódica los busca por su referencia, los relee por id y los aplica una sola vez; en planes, solo si salió de la tarjeta de esa suscripción y por su monto exacto.
- **Pago de plan anulado o contracargo:** la bolsa que compró ese pago vence en el acto (antes se podía seguir gastando el resto del mes) y, si era el último pago, lo pagado vuelve a su inicio, así una activación a mano abre la bolsa de inmediato.
- **«No se cobró» del admin:** busca primero en Wompi y se niega si hay una transacción con esa referencia que no esté anulada, releída por id (marcarlo con el cobro hecho llevaba a un segundo cargo a la tarjeta); con solo anuladas vale, porque la plata volvió.
- **«Buscar en Wompi» en /admin/cobros** para una recarga pagada sin acreditar, en vez de la recarga manual (que se sumaba otra vez si después llegaba el aviso).
- **Los avisos de plata a la vista en /admin/cobros:** el servidor no manda correos (PND-048) y nadie se enteraba.
- Menores: un 3xx en un cobro queda incierto; lo releído con otra referencia no se aplica; tope a `?pagina=`; Bold no sigue redirecciones; cupo por proyecto a las consultas del `?id=` de la vuelta; el checkout de una recarga vence a las 24 h; sin manejadores en línea en la página de la tarjeta.

## Lo que se arregló el 2026-10-15 (PND-304 y PND-328)

- **Un pago anulado que Wompi aprueba tarde ya no se acredita (PND-328):** los avisos de Wompi pueden llegar en desorden.
  Si llega primero la anulación, la recarga queda anulada sin sumar nada; la aprobación que llegue después, aunque venga
  firmada entera, ve esa anulación y no suma.
- **Una recarga aprobada que Wompi anula después y cuyo aviso se pierde (PND-304 b):** la revisión cada 10 minutos vuelve
  a preguntarle a Wompi por las recargas aprobadas de los últimos 30 días (cada 2 horas los dos primeros días, después una
  vez al día). Si Wompi la anuló, descuenta el saldo una sola vez y avisa al admin. Los pagos de plan todavía dependen solo
  del aviso firmado para enterarse de una anulación.
- **La política de scripts de la página de la tarjeta ahora se anota sola (PND-304 a):** el navegador manda cada cosa que
  esa política bloquearía a `POST /pagos/csp/tarjeta`, que guarda solo la directiva, el origen y la página (nunca la
  dirección completa ni el proyecto), con topes de tamaño y cantidad. Se ve en /admin/cobros, «Política de scripts de la
  página de la tarjeta», y una nueva llega a «Avisos de plata». Sigue en «solo reporte».

## Riesgos aceptados o pendientes

- **Correo del servidor (PND-048):** mientras el VPS no tenga SMTP, los avisos de plata solo se ven en /admin/cobros. Hay que mirarla.
- **Cuenta de admin sin segundo factor:** con una sesión de admin robada se podría crear saldo con recargas manuales o ajustes (hasta US$ 100 000 por clic). Ver PND-304.
- **La banda de la TRM se corre con cada lectura buena:** quien controlara datos.gov.co podría bajarla de a ~8 %. Hipótesis; se acepta (PND-304).
- **Nequi a cualquier celular** y **`widget.js` sin SRI** (PND-256): aceptados.
- **El token de Nequi viaja en la ruta del sondeo** (queda en los registros de acceso): solo sirve con nuestra llave privada y es de un solo uso.
- **La política de scripts de la página de la tarjeta sigue en «solo reporte»** (`CSP_TARJETA_SOLO_REPORTE`): se pasa a
  bloquear cuando, después de al menos un alta y un cambio de tarjeta reales con el widget, la lista de /admin/cobros esté
  vacía o solo tenga extensiones del navegador. Si aparece algo de Wompi o de Creatv, primero se permite en la política.
  La ruta de los reportes no lleva firma (un navegador no firma): por eso no mueve nada y tiene topes.
- **Sin probar todavía con la API de verdad:** el rechazo en el alta, la gracia, el anual, la anulación, Nequi y la referencia repetida. El script `deploy/prueba_wompi_sandbox.py` los corre contra el sandbox (necesita las llaves de pruebas en `.env.wompi-sandbox`).
