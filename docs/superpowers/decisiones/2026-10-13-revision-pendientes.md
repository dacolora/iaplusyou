# Revisión de pendientes: decisiones (2026-10-13)

**Qué pasó:** el 2026-10-12 siete revisores comprobaron los 182 pendientes abiertos contra el código (main 128a72e2): 6 ya no hacían falta y 14 estaban a medias (commit 97809074). El 2026-10-13 Daniel respondió varios y pidió: «veo muchas cosas que no son decisiones; haz un evalúo de todos los pendientes y toma lo más recomendable». Claude decidió todos los que quedaban, también los que otras conversaciones agregaron ese día.

**Resultado:** 99 se cierran (descartados, aceptados, ya decididos antes o unidos a otro) y 94 quedan abiertos, cada uno con su decisión y su grupo: lote 1 (24), lote 2 (34), lote 3 (24), proyectos (8), solo Daniel (4). Los cerrados siguen en «Cerrados al revisar» de `docs/pendientes.md` con su texto original resumido.

## Lo que dijo Daniel (2026-10-13)

| PND | Daniel | Qué se hace |
|---|---|---|
| 010 | «Todo esto debe cobrarse al cliente; después, cuando tengamos los planes, decidimos a qué cliente se le cobra y a cuál no. Por ahora todo se le cobra.» Y con la consola de Apify a la vista (US$ 1,99 de 5 usados en el mes): «acá no hay 5 dólares ahí utilizados». | No se sube de plan por ahora: el mes va en US$ 1,99 de 5 y el costo de cada corrida ya se le cobra al cliente. Starter solo daría 40 reseñas por producto en vez de 10. Se agrega un aviso en Alertas, solo para el admin, cuando el uso del mes de Apify pase el 80 % de su tope (lo lee de la API de Apify); al llegar ese aviso, o si 10 reseñas por producto se quedan cortas, se sube a Starter. Si el tope se llega antes, Nicho ya lo dice sin cobrar (`providers/apify.py`, el 402). |
| 013 | «Revisar todo el tema de facturación; todo se le debe cargar al cliente.» | Auditoría de cobros: recorrer cada llamada que paga a un proveedor y comprobar que, con «Cobrar» prendido, se le cobra al cliente (incluye el (1) de PND-186: Whisper que falla después de que fal cobró) y que lo anotado cuadra con las facturas del mes de fal, WaveSpeed y Anthropic; el precio de Whisper se mide ahí. Lo que falte se arregla en el mismo lote. Coordinar con la revisión de lo cobrable a happyflops de otra conversación, que ya abrió PND-312 a PND-319 (el 312 ya está cerrado). |
| 020 | «Actívalo.» | PND-322 (presupuestos en COP ×100) ya está arreglado y en producción. Activar un experimento con pauta real es tu plata: recomendado uno nuevo de Forja con el mínimo diario (4 000 COP), 3 días y tope 12 000 COP; te muestro el gasto exacto antes de lanzarlo. |
| 037 | «No debe ser solo para los que vienen de Meta: si alguien en Crear quiere hacer la publicación orgánica, a darle, pero debe tener las conexiones. Por ahora no es tan importante.» | Proyecto sin prisa: publicar orgánico desde cualquier pieza de Crear, no solo la ganadora de un experimento, para quien tenga sus redes conectadas. Antes de abrirlo a clientes, probarlo en real con un proyecto conectado. |
| 048 | «Esto es algo que le debemos dar mucha fuerza; armemos un plan de trabajo en otro chat como pendiente principal.» | Pendiente principal. Plan de trabajo en una conversación aparte: proveedor de correo (recomendado Resend con el dominio creatvmachine.com; Daniel crea la cuenta y pone los registros DNS SPF, DKIM y DMARC), `notificaciones.py` por API, las plantillas de cada correo (verificar la cuenta, recuperar la clave, saldo, deuda de pospago, avisos de experimentos y de Meta) y lo que destraba: el saldo de bienvenida (PND-299), el registro nuevo (PND-292) y los avisos por correo (lo que era PND-259). |
| 057 | «Dale la alerta al cliente.» | Alerta en Alertas, para el cliente del proyecto, cuando el negocio de su conexión de Meta no está verificado (`verification_status` del Business en la Graph API), con lo que tiene que hacer y el riesgo de que Meta restrinja la app. Para colorado_forja el cliente es Daniel. |
| 161 | «Debemos montar todo un sistema de facturación para la empresa que lo utilice.» | Sistema de facturación para cada empresa cliente: sus datos fiscales (NIT o identificación, razón social, correo de facturación) y una factura electrónica por cada recarga y cada pago de plan, emitida por un proveedor autorizado por la DIAN vía API (recomendado: Alegra o Siigo) en vez de hablar directo con la DIAN. Antes, con el contador: régimen, IVA y numeración. Incluye lo que era PND-248. |
| 192 | «Hagamos visible esto.» | Ya se ve en Rendimiento cuando hay datos. Claude comprueba en producción, solo leyendo, que haya desgloses copiados; si no hay, encola la copia. La primera «Evaluar con IA» la pulsa quien la use: cuesta menos de US$ 1. |
| 211 | «Lo mismo»: hacerlo visible. | Se abren 4:3, 3:4 y solo texto en Seedance 2.5 con varias referencias, al mismo precio por segundo. Su factura entra en la auditoría de PND-013. |
| 217 | «No importa ese incremento de gastos: con precios por debajo de 1 USD no debe ser un estoper de nada.» | Subir el tope a 32 000 con `timeout=900`, volver a meter el NVP en el prompt y poner a la vista el precio del peor caso medido. |
| 291 | «La idea es tener mucho cuidado que lo que haya en Meta y en Triple Whale no se esté duplicando, para no mostrar información errónea: revisar si las pautas son las mismas y mostrar un único indicador. Creo que con Triple Whale se tiene todo.» | Un solo indicador por cifra. Donde una cuenta de Meta está cubierta por una tienda de Triple Whale, las ventas, las compras y el ROAS salen solo de Triple Whale; el Diagnóstico y los Segmentos de esa cuenta muestran solo entrega (gasto, CPM, CTR, frecuencia, problemas), nunca las compras ni el ROAS del Pixel. El gasto se cruza: si el de Meta y el de Triple Whale de la misma cuenta difieren más de 5 %, sale un aviso en vez de dos cifras. Meta se sigue conectando porque es lo que deja lanzar, pausar y cambiar presupuestos, trae lo que Triple Whale no tiene (rechazos, aprendizaje, desgloses por edad y ubicación) y cubre las cuentas sin tienda. |
| 299 | «Podríamos darle hasta 2 o 3 dólares gratis para la generación; de resto todo de cuenta del cliente.» | Las cuatro ayudas con IA (director, describir referencias, sugerir sonido, analizar marca) cobran del saldo del proyecto como todo lo demás, y cada proyecto nuevo recibe **US$ 2 de saldo de bienvenida** (valor editable en /admin/cobros), una sola vez, al verificar su correo. Con esto se cierra PND-165. |
| 329 | «Flow Plus: siento que esta sección debe tener una reestructuración.» | Proyecto: empezar con una sesión de diseño (qué hace hoy cada parte, qué se usa de verdad, qué estorba) y maquetas antes de tocar código. |

Dos reglas nuevas que salen de ahí y valen para todo lo demás:
- **Todo se le cobra al cliente**, por ahora; con los planes se decidirá a quién no (PND-010).
- **Un costo por debajo de US$ 1 no frena nada**: ni una decisión, ni una prueba (PND-217).

## Cómo decidió Claude

En este orden: (1) que ningún cobro se pierda ni se esconda, y que todo se le cobre al cliente; (2) que nadie vea datos que no son suyos; (3) que no se borre nada que no se pueda recuperar; (4) que lo que el cliente ve sea verdad; (5) lo demás, solo si vale lo que cuesta. Una **función nueva nunca empezada no es un pendiente**: se cierra como descartada y se reabre si se pide. Una **menudencia sin daño** se acepta. Lo que **necesita las manos de Daniel** (sus cuentas, su plata, lo legal, la pauta de Meta) queda en «Solo Daniel», con lo que hay que hacer en una línea.

El saldo de bienvenida (PND-299): Daniel dijo «2 o 3 dólares». Se eligen **US$ 2**, editables en /admin/cobros, y se dan **al verificar el correo**, para que no se puedan sacar creando cuentas en serie. Como el VPS no tiene correo saliente (PND-048), mientras tanto el admin puede darlo a mano con un ajuste. Si Daniel prefiere US$ 3, es cambiar un número.

## Lote 1 · plata (24)

Lo que hoy se le cobra o se le muestra mal a un cliente que paga, y tus decisiones de hoy. Va primero.

| PND | Tema | Decisión |
|---|---|---|
| 013 | Comprobar en la factura de fal el precio real de Whisper (estimado US$ 0,002 por minuto) después de la… | Auditoría de cobros: recorrer cada llamada que paga a un proveedor y comprobar que, con «Cobrar» prendido, se le cobra al cliente (incluye el (1) de PND-186: Whisper que falla después de que fal cobró) y que lo anotado cuadra con las facturas del mes de fal, WaveSpeed y Anthropic; el precio de Whisper se mide ahí. Lo que falte se arregla en el mismo lote. Coordinar con la revisión de lo cobrable a happyflops de otra conversación, que ya abrió PND-312 a PND-319 (el 312 ya está cerrado). |
| 058 | Meta de colorado_forja: el acceso a datos vence el 2026-12-18 y hay que reconectar antes. La app guarda una… | Leer `data_access_expires_at` y avisar en Alertas 14 días antes de que venza. Daniel reconecta Meta de colorado_forja cuando salga el aviso (antes del 2026-12-18). |
| 136 | Deudas menores del centro de resultados que quedan: (8) en el modo manual del reparto, un país agregado o… | Solo queda el (15): «Activar» de un anuncio suelto dice el gasto diario antes de confirmar (regla 1). Lo demás pasó a E3 de Probar anuncios el 2026-10-08. |
| 192 | Meta rendimiento E2 «Diagnosticar y recomendar»: en producción desde el 2026-10-10 (7bb9208b, alembic 0039) y… | Ya se ve en Rendimiento cuando hay datos. Claude comprueba en producción, solo leyendo, que haya desgloses copiados; si no hay, encola la copia. La primera «Evaluar con IA» la pulsa quien la use: cuesta menos de US$ 1. |
| 208 | Meta rendimiento: mientras haya una tarea `exp_avanzar_todos` o `exp_decidir` pendiente o en curso en la cola… | Claude lo comprueba en el registro del worker de producción (solo lectura) y lo cierra. |
| 211 | Seedance 2.5 con varias referencias (fal): la prueba real del 2026-10-09 salió bien (3 referencias, 4 s,… | Se abren 4:3, 3:4 y solo texto en Seedance 2.5 con varias referencias, al mismo precio por segundo. Su factura entra en la auditoría de PND-013. |
| 214 | Al lanzar un video en WaveSpeed, una lectura agotada o una conexión cortada sale cruda en la tarjeta… | Una lectura agotada o una conexión cortada dice en palabras que el pedido pudo crearse y cobrarse, y ofrece «Recuperar el video» en vez de volver a pagar. |
| 217 | «Evaluar con IA» de Triple Whale: su tope de 16 000 tokens ya corta la primera respuesta con 10 anuncios… | Subir el tope a 32 000 con `timeout=900`, volver a meter el NVP en el prompt y poner a la vista el precio del peor caso medido. |
| 231 | El filtro de plantilla `precio` ignora una lectura fallida del margen: `gastos.margen_vigente()` devuelve 1,0… | El filtro `precio` dice «precio no disponible» cuando el margen no se pudo leer, igual que `texto_precio`. |
| 236 | El análisis «Cómo mejorarlo» de un anuncio (y el lote «Analizar los N que más gastaron») no compara el precio… | «Cómo mejorarlo» y «Analizar los N» comparan el precio que vio la persona, como «Evaluar con IA»: si cambió, se vuelve a mostrar antes de cobrar. |
| 241 | Cuando Claude se niega a escribir un guion por su contenido, la app paga la vuelta de corrección y muestra… | Si Claude se niega (la respuesta no trae JSON), no se paga la vuelta de corrección y se dice en palabras. |
| 243 | Dos detalles de la prueba real: (1) el precio de «Traer referentes» usa `gastos.estimar("clasificacion", n)`… | El precio de «Traer referentes» usa `bilingue` según el idioma del proyecto, y el nombre del modelo pasa por el catálogo. |
| 268 | Meta rendimiento y Triple Whale, «Evaluar con IA»: si el worker se reinicia (o el respaldo sin saldo lo mata)… | Una evaluación cortada a mitad de la llamada a Claude anota su estimado con `entregado=False`. |
| 299 | Plata, alta abierta: cuatro ayudas con IA que paga Creatv no frenan nunca, ni con saldo 0 ni sin correo… | Las cuatro ayudas con IA (director, describir referencias, sugerir sonido, analizar marca) cobran del saldo del proyecto como todo lo demás, y cada proyecto nuevo recibe **US$ 2 de saldo de bienvenida** (valor editable en /admin/cobros), una sola vez, al verificar su correo. Con esto se cierra PND-165. |
| 300 | Plata: las rutas que llaman a Claude dentro de la petición frenan con `libro.exigir` sin `job_id`, que no… | Las rutas que llaman a Claude dentro de la petición reservan con un id propio, para que dos pedidos seguidos no vean el mismo saldo libre. |
| 304 | Pagos, lo que quedó de la auditoría de seguridad del 2026-10-12 (`docs/pagos/seguridad-pagos.md`).… | Lo lleva la conversación de pagos (relevo `docs/superpowers/relevos/2026-10-12-modulo-de-pagos.md`). Para el (a), lo más simple es un `report-uri` que anote las violaciones, sin depender de que alguien mire la consola. |
| 313 | Plata: fal termina y cobra pero no se anota cuando se acaba la espera en trabajos caros: diseñar voz (US$ 3),… | Va con la auditoría de cobros (PND-013): al acabarse la espera se consulta el estado en fal y se anota lo cobrado, también sin `voice_id`. |
| 314 | Plata, Final edition: si la final falla después de pagar, el guion base se revierte y voz, Whisper y… | Va con la auditoría de cobros (PND-013): lo que queda en caché tras una final fallida se cobra cuando se reusa. |
| 315 | Plata, llamadas que cobran y no se anotan o se anotan con un estimado (centavos por evento): la revisión de… | Va con la auditoría de cobros (PND-013): cada una anota lo que de verdad cobró el proveedor. |
| 316 | Plata, al revés: `comparar_seedance_turbo.py` anota la investigación de Creatv al proyecto del `--cliente`… | Arreglo de una línea: el script anota a `_creatv`, no al cliente. |
| 318 | Plata, swap: si se agota la espera de 15 min (`wavespeed_common.poll_hasta_listo`, `timeout_seconds=900`)… | Va con la auditoría de cobros (PND-013): guardar el id del pedido de WaveSpeed antes de esperar, y al agotarse la espera consultar su estado y anotar lo cobrado, con «Recuperar» como en Crear. |
| 319 | Plata y seguridad, Crear: el precio de un video de referencia de Wan 3.0 (que se factura por sus segundos)… | Medir la duración del video de referencia con ffprobe sobre el archivo (como el swap de PND-312), no con la cabecera, y cobrar y mostrar con esa medida. |
| 324 | La tarea vieja `meta_publicar` (`tareas/meta.publicar`, los anuncios sueltos) manda el diario a Meta sin… | `tareas/meta.publicar` pasa por `comprobar_moneda` y la lectura de vuelta del diario, como el lanzador; no se borra porque los anuncios sueltos viejos dependen de ella. |
| 325 | `lanzador.comprobar_moneda` se salta la comprobación de la unidad (×10 contra el mínimo diario de Meta) sin… | Sin `min_daily_budget` de Meta no se manda ningún monto; para las monedas sin estimación propia, el mínimo esperado sale de US$ 1 convertido con las tasas del BCE (`meta_rendimiento.tasas`). |

## Lote 2 · lo que ve el cliente (34)

Pantallas, textos, privacidad y lo que Claude verifica a ojo.

| PND | Tema | Decisión |
|---|---|---|
| 010 | Apify está en el plan FREE: tope de US$ 5 al mes y junglee lee solo 10 reseñas por producto. Cuando Daniel… | No se sube de plan por ahora: el mes va en US$ 1,99 de 5 y el costo de cada corrida ya se le cobra al cliente. Starter solo daría 40 reseñas por producto en vez de 10. Se agrega un aviso en Alertas, solo para el admin, cuando el uso del mes de Apify pase el 80 % de su tope (lo lee de la API de Apify); al llegar ese aviso, o si 10 reseñas por producto se quedan cortas, se sube a Starter. Si el tope se llega antes, Nicho ya lo dice sin cobrar (`providers/apify.py`, el 402). |
| 029 | Quitar «logo» de la lista negativa de la marca de happyflops: choca con «producto exacto». | Se quita «logo» de la lista negativa de happyflops: el logo real del producto tiene que poder salir. Se deja la regla de no generar texto. |
| 033 | El editor de video nunca pasó la revisión de celular (no había ediciones en producción cuando se hizo). | Claude mira el editor a 375 px con una edición sembrada y arregla lo que empuje la página de lado. |
| 041 | El texto de consentimiento al clonar no dice que la voz no se puede borrar de la cuenta MiniMax de fal.… | El texto de consentimiento dice que la voz clonada queda en la cuenta del proveedor y no se puede borrar. |
| 057 | Forja Habit sigue sin verificar en Meta: la app Forja Ads puede quedar restringida como la vieja. | Alerta en Alertas, para el cliente del proyecto, cuando el negocio de su conexión de Meta no está verificado (`verification_status` del Business en la Graph API), con lo que tiene que hacer y el riesgo de que Meta restrinja la app. Para colorado_forja el cliente es Daniel. |
| 085 | Editor: la grabación con micrófono de la voz en off no se probó en un navegador real. | Claude prueba la grabación con micrófono en el navegador; si el navegador no da micrófono, se anota y se cierra. |
| 106 | Confirmar a ojo, en un Chrome visible, que las miniaturas de video se pintan. | Claude mira las miniaturas de video en el navegador y lo cierra. |
| 110 | Calibrar `TARIFAS["guion"]` (0,13) y `TARIFAS["final"]` (0,20) con el gasto real que se anota desde el… | Calibrar las tarifas de guion y de final con el promedio real de la tabla `gasto`, con 20 % de margen de seguridad. |
| 169 | Cobros: `cadena_elementos` (cuesta centavos) no tiene gancho `AL_INTERRUMPIR`: si el respaldo del worker la… | `cadena_elementos` y todo tipo que cobra registran su `AL_INTERRUMPIR`; el detalle del reverso dice «colgada» cuando lo fue. |
| 194 | Rendimiento: las tarjetas de los anuncios de Meta SIN análisis siguen enlazando la miniatura firmada de Meta… | Copiar a R2 las miniaturas de los anuncios de Meta sin análisis, como ya hace Triple Whale. |
| 206 | Meta rendimiento: `cuentas.elegir` no es atómica (agrega y quita en transacciones separadas), y quitar una… | `cuentas.elegir` en una sola transacción, y la copia comprueba que la cuenta siga elegida antes de escribir. |
| 215 | Sin saldo en fal por el lado del audio: las voces, la música y los subtítulos automáticos… | Voces, música y subtítulos reconocen «sin saldo en fal» y lo avisan como Seedance. |
| 219 | Pestaña Triple Whale: el aviso «Triple Whale no aceptó la consulta de: …» pinta los nombres internos de las… | Los nombres de las partes pasan por el catálogo y el aviso de `web_analytics_table` sale una sola vez. |
| 221 | NVP: la explicación de la etapa (qué es TOF, MOF y BOF y los cortes 70/40) solo vive en el `title` del chip,… | La explicación de TOF, MOF y BOF se ve al tocar el chip, también en el celular. |
| 227 | `doctrina._numeros` junta los dígitos de un decimal («4,0» pasa a 40, «5.00» a 500) y así debilita la… | Un solo arreglo con PND-228 y PND-237 para la comprobación de cifras inventadas: decimales bien leídos, cifras de un dígito con palabra de oferta y urgencia sin número. Se mide con `eval-claude`. |
| 228 | El copy nuevo y el texto de un gancho pueden afirmar urgencia o escasez sin un número («Lageret tømmes raskt… | Va con PND-227. |
| 229 | Un clip que Crear aún puede recuperar («Recuperar el video», sin pagar de nuevo) deja en `error` para siempre… | La cadena de escenas espera un clip recuperable, como los ganchos (`clip_recuperable`). |
| 237 | `doctrina.verificar_cifras` no verifica las cifras de un solo dígito: «Últimas 3 unidades», «Garantía de 5… | Va con PND-227. |
| 239 | El director arma el prompt de video en el idioma del proyecto (español en colorado_forja), no en inglés como… | El director escribe el prompt de video en inglés (regla 3). |
| 240 | El director inventa detalles que no están en las referencias: en la prueba real puso un nombre («Ana») y un… | El director no agrega nombres ni logos que no estén en las referencias; se mide con `eval-claude`. |
| 242 | Seedance 2.5 con varias referencias rechaza fotos realistas de personas aunque sean generadas con IA (regla… | Aviso antes de generar cuando se elige Seedance 2.5 con una persona en la bandeja. |
| 258 | Meta rendimiento: el motivo de cada anuncio `WITH_ISSUES` (2 641 en HappyFlops). La copia guarda el estado… | Copiar `issues_info` y que el Diagnóstico diga el problema de cada anuncio. |
| 264 | «Evaluar con IA»: los campos de `angulo` de una idea llegan con `repr` cuando Claude manda un dict o una… | `doctrina._texto` convierte un dict o una lista en texto legible. |
| 270 | Meta rendimiento, Alertas: las alertas `meta_rendimiento:<tipo>:<cuenta>` (perdedores gastando, anuncios con… | Las alertas de Meta solo las descarta un admin, como las de plata (misma regla que PND-124). |
| 291 | Rendimiento: el Diagnóstico y los Segmentos de Meta (main E2) corren sobre TODAS las cuentas de Meta del… | Un solo indicador por cifra. Donde una cuenta de Meta está cubierta por una tienda de Triple Whale, las ventas, las compras y el ROAS salen solo de Triple Whale; el Diagnóstico y los Segmentos de esa cuenta muestran solo entrega (gasto, CPM, CTR, frecuencia, problemas), nunca las compras ni el ROAS del Pixel. El gasto se cruza: si el de Meta y el de Triple Whale de la misma cuenta difieren más de 5 %, sale un aviso en vez de dos cifras. Meta se sigue conectando porque es lo que deja lanzar, pausar y cambiar presupuestos, trae lo que Triple Whale no tiene (rechazos, aprendizaje, desgloses por edad y ubicación) y cubre las cuentas sin tienda. |
| 295 | Privacidad, lo que queda de S1 de la revisión final de Rendimiento E2 tras el arreglo del 2026-10-12 (rama… | Al desconectar Meta, los aprendizajes conservan la lección pero pierden el nombre del anuncio, y `/eliminar-datos` lo dice. |
| 297 | Privacidad, gemelo del (3) de PND-295 para la «Evaluación con IA» de Meta: `meta_rendimiento.rutas.evaluar`… | La evaluación de Meta vuelve a mirar la conexión al crear su fila; si se desconectó, no la crea. |
| 307 | Spend en inglés muestra detalles guardados en español: las filas viejas de happyflops dicen «importado del… | Traducir al pintar los dos prefijos conocidos de las filas importadas; no se reescribe la base. |
| 308 | «Cómo mejorarlo»: el `lead` del ángulo de la versión sale inválido en la mayoría de las respuestas (medido el… | Mirar en las respuestas crudas qué escribe Claude como lead y aceptar esos valores o listarlos en el prompt; medir con `eval-claude`. |
| 311 | Triple Whale de happyflops: la tienda «HappyFlops WW» (`njd4pz-ab.myshopify.com`, 0 de gasto en los 7 días… | Una tienda sin país se muestra como su propia entrada «Resto del mundo» en el selector, nunca como fuente de todo el proyecto, y el decisor de Probar anuncios no la usa para un país. Con eso se conecta HappyFlops WW. |
| 321 | Rendimiento lento en producción: el panel (`/cliente/happyflops/rendimiento/panel`) tarda ~24 s con «Todas» y… | Medir dónde se van los 24 s del panel con «Todas» (consultas y lecturas de Meta), y bajarlo con lecturas memorizadas por petición o un resumen precalculado por la copia; meta: menos de 3 s. |
| 323 | «Nuevo experimento» dice que Meta solo acepta un tope desde 400 000 COP (`lanzador.minimo_tope_campana`, una… | El texto de «Nuevo experimento» usa el mínimo real de la cuenta (`min_campaign_group_spend_cap`), leído una vez y guardado con la conexión; sin lectura, dice «el mínimo de tu cuenta de Meta» sin inventar una cifra. |
| 327 | `tests/test_tareas_tiendas.py::test_sync_pedidos_guarda_y_resuelve_atribucion` falla en `main` desde antes… | Diagnosticar por qué la sync de pedidos no atribuye el `utm_content` del pedido (puede ser un defecto real de la atribución, no solo de la prueba) y arreglar la causa; la prueba vuelve a verde. |
| 328 | Wompi: una aprobación que llega tarde con todos sus campos firmados se aplica sin mirar si antes llegó una… | Antes de aplicar una aprobación de Wompi se mira si esa recarga tuvo una anulación. |

## Lote 3 · higiene (24)

Arreglos chicos que sí vale la pena hacer.

| PND | Tema | Decisión |
|---|---|---|
| 066 | `metrica_snapshot` guarda una fila cada 2 horas aunque nada haya cambiado. | Guardar la foto solo si cambió algo. |
| 101 | Siguen en la Mac worktrees ya fusionados (catalogo-colores, crear-anuncio-hablado, crear-audios,… | Claude borra los worktrees y ramas locales ya fusionados; nunca `flowplus-refinador` ni `respaldo/…`. |
| 175 | Cobros: detalles de texto y de código sin daño. `libro._validar_margen` muestra el rango como «1.0 a 5.0»… | Corregir los textos (rango con coma, «se acredita sola» solo los primeros minutos) y lo demás de la fila. |
| 189 | Las rutas de la evaluación de cuenta de Triple Whale con un id enorme dan 500 en vez de 404 (`OverflowError`… | `<int(max=…)>` en las dos rutas. |
| 199 | Meta rendimiento: el alcance de una campaña que dejó de entregar se queda en su último valor.… | Al copiar, borrar el alcance de las campañas que ya no entregan en la ventana. |
| 202 | Rendimiento, «Todas» con Meta: «Última copia» toma la más antigua de las cuentas del alcance, y si UNA cuenta… | «Última copia» dice cuántas cuentas faltan por copiar. |
| 207 | Meta rendimiento: `meta_agencia.desasignar` y `meta_conexion.borrar` por sí solas NO borran las métricas… | El borrado de métricas pasa adentro de `desasignar` y `borrar`. |
| 222 | RMW de Triple Whale aún sin candado antes de leer: actualizar_extra_tienda puede pisar cambios de extra;… | Las dos escrituras toman el candado antes de leer (regla 5). |
| 230 | El video original que baja un gancho de Triple Whale (origen `triple_whale`, uno por análisis, hasta 60 MB)… | `triple_whale` entra en `ORIGENES_BORRABLES`. |
| 234 | Si `tw_ganchos_preparar` falla, sus filas sin clip quedan en `error` con el mensaje genérico («Algo falló al… | La fila del gancho muestra el error de su sesión de Crear. |
| 262 | Meta rendimiento: una alerta guardada en `meta_cuenta.extra.alertas` no caduca si las copias siguen fallando.… | No mostrar la alerta guardada de una cuenta sin copia en 48 h. |
| 263 | Meta rendimiento, «Segmentos»: la tabla de la ventana de 7 días lleva la marca «Caro» calculada con la regla… | La tabla de Segmentos dice de qué ventana es la marca «Caro». |
| 269 | La suite de pruebas escribe en archivos ignorados del checkout en vez de en la carpeta temporal:… | Las pruebas escriben en carpetas temporales y una guarda falla si el árbol cambia. |
| 274 | Rendimiento, «Por país»: una entrada de Meta con unas cuentas cubiertas por una tienda y otras no (cubierta a… | Nota en la entrada cubierta a medias. |
| 275 | Rendimiento: una cuenta de Meta sin moneda conocida pinta sus montos como números sueltos («12,50», sin… | Un monto sin moneda dice «moneda no disponible». |
| 276 | Rendimiento, anuncios de fuente Meta en «Todas»: el «% del gasto en perdedores» (y la alerta «El N % del… | Junto con lo que eran PND-266 y PND-285: con monedas distintas en «Todas», todo lo que suma u ordena montos pasa por USD; sin conversión, se dice. Hoy las 7 cuentas son SEK. |
| 277 | Rendimiento, «Todas» con varias tiendas: si UNA tienda se atrasa (su copia no trajo los últimos días) y las… | El fin de los datos se toma por tienda. |
| 278 | Rendimiento: con una sola tienda sin país (R4), Meta conectado y ninguna cuenta elegida, «Actualizar ahora»… | El mensaje «Elige primero qué cuentas de Meta…» también con una sola tienda. |
| 280 | Pruebas: `tests/test_i18n_app_entera.py::test_i18n_app_entera[/admin/salud]` falla según el orden: si antes… | La etiqueta «(sin ruta)» pasa por el catálogo. |
| 283 | Rendimiento (auditor de seguridad, BAJO): tres `fetch` de la pestaña no detectan la redirección al login de… | Los cuatro `fetch` detectan la redirección al login. |
| 287 | Rendimiento: dos reglas de las recomendaciones propias de Rendimiento E2 (tarea 6), jubiladas al integrar… | Portar las dos reglas: conjuntos rechazados y motivo de la cuenta desactivada. |
| 293 | Rendimiento E2: «Cómo mejorarlo» de un anuncio de Meta con creativo dinámico (`asset_feed_spec`: varios… | Tomar el primer video de `asset_feed_spec`. |
| 303 | Operación: el reintento diario de borrados en R2 (`storage/r2_pendientes.reintentar`, dentro de… | Tope por corrida y borrado por lotes en R2. |
| 317 | Accesibilidad de las barras de pastillas `cat-tabs` (Sprints · Nicho, Catálogo, Configuración): sin… | Arreglarlo una vez para las tres barras. |

## Proyectos (8)

Necesitan diseño antes de construir.

| PND | Tema | Decisión |
|---|---|---|
| 037 | La publicación orgánica en Facebook, Instagram, YouTube y TikTok nunca se probó en producción (faltan tokens… | Proyecto sin prisa: publicar orgánico desde cualquier pieza de Crear, no solo la ganadora de un experimento, para quien tenga sus redes conectadas. Antes de abrirlo a clientes, probarlo en real con un proyecto conectado. |
| 048 | El VPS no tiene SMTP: no salen correos de cuenta (verificar, recuperar clave), ni el aviso de saldo agotado,… | Pendiente principal. Plan de trabajo en una conversación aparte: proveedor de correo (recomendado Resend con el dominio creatvmachine.com; Daniel crea la cuenta y pone los registros DNS SPF, DKIM y DMARC), `notificaciones.py` por API, las plantillas de cada correo (verificar la cuenta, recuperar la clave, saldo, deuda de pospago, avisos de experimentos y de Meta) y lo que destraba: el saldo de bienvenida (PND-299), el registro nuevo (PND-292) y los avisos por correo (lo que era PND-259). |
| 131 | Sistema de estilos, entregas 2 a 4: componentes nuevos e íconos Lucide (el orquestador baja los SVG: Codex no… | Proyecto aparte, cuando toque rediseñar pantallas. |
| 148 | Lanzar anuncios por país en VARIAS cuentas publicitarias de Meta de un mismo proyecto: hoy se lanza en una… | Proyecto: lo necesita happyflops para probar anuncios por país. |
| 161 | Cobros: facturación electrónica ante la DIAN e IVA sobre el servicio. Hoy una recarga solo deja el movimiento… | Sistema de facturación para cada empresa cliente: sus datos fiscales (NIT o identificación, razón social, correo de facturación) y una factura electrónica por cada recarga y cada pago de plan, emitida por un proveedor autorizado por la DIAN vía API (recomendado: Alegra o Siigo) en vez de hablar directo con la DIAN. Antes, con el contador: régimen, IVA y numeración. Incluye lo que era PND-248. |
| 193 | Meta rendimiento E3 «Aplicar cambios»: botones «Pausar», «Activar» y «Subir presupuesto 20 %» sobre las… | Daniel dijo sí el 2026-10-12, también para el cliente: proyecto con spec. |
| 292 | Seguridad: las rutas que cobran de la pestaña Rendimiento («Cómo mejorarlo», «Analizar los N», «Evaluar con… | Rediseño del registro de clientes nuevos (Daniel, 2026-10-12), con el correo verificado; necesita SMTP (PND-048). |
| 329 | Flow Plus: Daniel siente que la sección necesita una reestructuración (2026-10-13). Falta entender qué le… | Proyecto: empezar con una sesión de diseño (qué hace hoy cada parte, qué se usa de verdad, qué estorba) y maquetas antes de tocar código. |

## Solo Daniel (4)

Necesitan tus cuentas, tu plata o una decisión legal o comercial. Cada uno dice qué hacer.

| PND | Tema | Decisión |
|---|---|---|
| 020 | El motor de experimentos nunca corrió con gasto real de punta a punta. El anuncio 120251368262800189… | PND-322 (presupuestos en COP ×100) ya está arreglado y en producción. Activar un experimento con pauta real es tu plata: recomendado uno nuevo de Forja con el mínimo diario (4 000 COP), 3 días y tope 12 000 COP; te muestro el gasto exacto antes de lanzarlo. |
| 050 | HappyCozy v4 (Flow Plus): «Llevar a Crear» y la cadena de escenas siguen apagados hasta subir las imágenes 1… | Subir las imágenes 1 a 4 de HappyCozy v4, o que las genere el cliente. |
| 052 | Meta en modo agencia sin conectar en producción: falta la parte de Daniel (token del Business de Creatv,… | Meta en modo agencia: solo si un cliente no puede usar su propia app (con él va lo que era PND-197). |
| 247 | Planes: activar el plan Pro. Está sembrado ARCHIVADO (US$ 1 000 al mes, anual US$ 10 000, margen 1,25, tope… | Activar el plan Pro cuando un cliente lo pida. Antes de activarlo se arreglan los bordes de planes que se aceptaron mientras no hubiera planes vivos (lo que eran PND-250, 251, 254 y 305). |

## Se cierran (99)

Por tipo: aceptado 40, descartado 28, ya decidido 5, descartado como pendiente 4, unido a PND-247 4, no se hace 2, hecho 2, fuera de la lista 2, unido a PND-276 2, aparcado 2, lo hace el cliente 1, no hace falta por ahora 1, unido a PND-216 1, unido a PND-299 1, unido a PND-052 1, unido a PND-161 1, unido a PND-048 1, decidido 1.

| PND | Tema | Cierre | Por qué |
|---|---|---|---|
| 021 | El experimento 2 «Prueba 1» de colorado_forja sigue en error. «Reintentar lanzamiento» lo arregla, pero desde… | no se hace | No se reintenta: «Reintentar lanzamiento» ahora también activa y gasta, y el experimento 2 era una prueba. Queda en error como registro. |
| 022 | Finales: un video 4:3 sale en 16:9 y uno 3:4 sale en 4:5 (antes salían en 9:16). Es el único cambio visible… | aceptado | El cambio de formato es a propósito y nadie lo ha reportado. |
| 025 | Catálogo: los 14 productos viejos de happyflops duplican los de la tienda hasta que Daniel los archive con el… | lo hace el cliente | Daniel, 2026-10-13: «esto lo resuelve el cliente, no nosotros». Los productos viejos los archiva el cliente con el botón «Archivar». |
| 026 | La música de Eleven Music vía fal se revende sin revisión legal de la licencia. | aceptado | Daniel, 2026-10-13: si no hay problema, sigue; al final eso lo revisa Meta. Los términos de ElevenLabs para Eleven Music (vigentes desde el 2026-10-09) permiten todo uso comercial en línea y fuera de línea desde el plan Starter, salvo cine, TV, radio y videojuegos de estudio, y fal marca el modelo como de uso comercial. Lo que no se puede: armar bibliotecas de música, pedir nombres de artistas reales o letras conocidas, ni usarla en anuncios políticos o religiosos. |
| 047 | Anuncio hablado: la sincronía de labios y el acento colombiano no se han medido. | hecho | Daniel, 2026-10-13: «ya se probó con el holandés y funcionó». |
| 049 | Editor: recortar del todo. Hoy recorta antes de escalar con paridad exacta (5b57a2fe;… | aceptado | El recorte parcial ya evitó el error de memoria; recortar del todo no cambia lo que se ve. |
| 053 | Faltan las llaves `REDDIT_*` en el VPS: la fuente Reddit de Nicho sale apagada. Ojo: su uso gratis es solo no… | descartado | La API gratis de Reddit es solo para uso no comercial; las reseñas vienen de las tiendas. |
| 054 | Faltan `MELI_APP_ID` y `MELI_SECRET` en el VPS: el conector de Mercado Libre no conecta. | no hace falta por ahora | Daniel, 2026-10-13: «por ahora no es necesario». Se reabre cuando un cliente venda en Mercado Libre. |
| 059 | Anunciar instalaciones de una app: PROBADO EN REAL 2026-10-08 07:09 Bogotá — experimento 5 de colorado_forja… | no se hace | Daniel, 2026-10-13: «no hacer nada con esto». El experimento 5 queda en pausa; sus conjuntos en Meta se corrigen con el arreglo de PND-319. |
| 060 | Nicho de colorado_forja: pulsar «Reanudar» en el estudio 1 (selección, reseñas, YouTube y avatares) ahora que… | descartado | Era el estudio de prueba de colorado_forja; si hace falta, se reanuda desde Nicho. |
| 061 | 29 archivos de happyflops (`productos.json` y fotos) están en git. En el VPS nunca `reset`, `checkout` ni… | aceptado | La guarda del VPS y la regla 9 lo cubren; sacarlos de git borraría los archivos del VPS en el siguiente pull. |
| 063 | Propuesta para vidrios y espejos: confirmar los supuestos antes de enviar (IVA, permanencia, plazos, pago,… | fuera de la lista | Es un documento comercial, no la plataforma. |
| 064 | R2: nada borra lo rechazado o descartado ni las versiones viejas de las finales. Propuesta: 30 días, salvo lo… | descartado | R2 cuesta centavos al mes y borrar no se puede deshacer; `salidas/` ya se limpia sola. |
| 065 | `materiales_limpiar` solo borra tipos efímeros y en producción no encuentra nada que borrar. | aceptado | Sin daño. |
| 069 | Director, Etapa 2: presets de cámara. | descartado | Idea nunca empezada; el director es opcional. |
| 070 | Director: retirar `banco_prompts.py`, como pedía la Etapa 3. Sigue en uso. | ya decidido | Decidido el 2026-10-08: el banco de prompts se queda. |
| 072 | Director, menores que quedan: las sesiones viejas sin tokens se rearman con ACTIVOS vacío (`director.py:170`)… | ya decidido | Decidido el 2026-10-08: las sesiones viejas no se migran. |
| 074 | Seedance 2.5 con imagen final (`last_image`). | descartado | Idea nunca empezada; se reabre si se pide. |
| 081 | Editor, capa 2: la re-revisión de la última ola de arreglos (c3630ac) nunca corrió. | descartado | La revisión de c3630ac quedó vieja (14 cambios después) y el editor pasó revisiones posteriores. |
| 082 | Editor 5c-2: animaciones (hoy solo «deslizar»), rotación, filtros y keyframes; la spec la tiene en esbozo… | descartado como pendiente | Es una función nueva del editor; se retoma si Daniel la pide. |
| 083 | Editor 5d «Producir completo» (países, precio por país, traducir con costo, variantes A/B) y la imagen dentro… | descartado como pendiente | Es una función nueva del editor; se retoma si Daniel la pide. |
| 084 | Editor, deuda: ≈ 150 líneas de estimar y sondear repetidas entre los paneles de voz y subtítulos;… | ya decidido | Decidido el 2026-10-08: se unifica al volver a tocar el editor. |
| 086 | Final edition: el reintento por capa (spec §3) y el estudio de sonido S3 a S8 (stems, remezclar, respaldo de… | descartado | El editor reemplazó al estudio de sonido. |
| 087 | Sprints: faltan «Proponer ideas para todo el sprint» y «Reemplazar idea» sobre una pieza en error. | descartado | «Regenerar» con la misma idea ya cubre el caso. |
| 089 | Sprints, restos de sonido: falta el botón «Sugerir» sonido en las ideas del sprint… | descartado | Restos menores que ningún cliente ha pedido. |
| 091 | Referentes: traducir copycoders en lotes de 100 a veces se corta aun con 12 000 tokens. Bajar el lote si se… | aceptado | Se baja el lote solo si se vuelve a importar. |
| 092 | Nicho, menores que quedan: `edad_rango` cortado a 20 letras (`nicho/datos.py:466`); `probar()` de Reddit y… | ya decidido | Decidido el 2026-10-08: no vale lo que cuesta. |
| 093 | Nicho: sumar Google, Trustpilot y tiendas de apps como fuentes de reseñas (eBay, Etsy y Temu ya se… | descartado | Idea; las tiendas ya traen las reseñas. |
| 094 | Catálogo, seguimientos que quedan: la Admin API trae una sola variante (`conectores/shopify.py:55,231`,… | ya decidido | Decidido el 2026-10-08: pasan a proyectos nuevos. |
| 097 | Meta: borrar la app vieja «Creatv Machine» (opcional e irreversible). | descartado | Borrar la app vieja no se puede deshacer y no estorba. |
| 099 | Quitar `naia-app` de las carpetas extra de las sesiones: mete sus skills de FastAPI en este repo. | fuera de la lista | Es la configuración de la app de escritorio, no la plataforma. |
| 100 | `ESTRUCTURA.md`, `/mapa` y el artifact del mapa no se regeneran desde el 2026-09-20 (8fde9cb). El mapa aún… | descartado | El mapa se regenera si Daniel lo pide. |
| 103 | VPS: queda un `git stash` viejo con las ediciones a mano del 2026-09-22. | aceptado | El stash viejo del VPS no estorba y la guarda impide tocarlo. |
| 104 | Aprendizaje entre experimentos: el decisor no usa la frecuencia (solo se muestra como «fatiga»,… | descartado | Idea nueva para el decisor, no un defecto. |
| 105 | Ideas de Vendro sin hacer: marca desde la URL de la tienda, quitar fondo, revisión del embudo y chat sobre… | descartado | Ideas de la competencia, no defectos. |
| 121 | Alertas: lo que el worker cambia fuera de la clave del Tablero (un error de Crear, una investigación de… | aceptado | 60 s de espera en Alertas no molestan. |
| 135 | `resultados.py` tiene ~1 100 líneas (1 121 tras la revisión final de E2) con cuatro oficios mezclados.… | aceptado | Se parte al volver a tocarlo. |
| 149 | (8) Falta comprobar con la primera copia real que el gasto de cada tienda incluye toda la cuenta publicitaria… | unido a PND-216 | Se comprueba sola al conectar la segunda tienda. |
| 153 | Instalaciones reales: Forja Habit no tiene SDK de Meta ni AppsFlyer/Adjust/Branch, así que la v1 optimiza por… | descartado | Depende de meter el SDK en Forja Habit, que es otro producto. |
| 154 | Instalaciones de la app, decisiones de la v1 a revisar con datos: escalar sube el total del país y la subida… | aceptado | Se revisa cuando haya datos reales (PND-059). |
| 158 | «Resultados de tu tienda»: el detalle del día no trae miniaturas de los anuncios (pediría la Graph API de… | descartado | Idea, no defecto. |
| 163 | Cobros: no hay recarga automática cuando el saldo baja del umbral; cada recarga la inicia una persona. (La… | descartado | El pospago y los planes ya cubren al cliente que no quiere recargar a mano. |
| 164 | Cobros: Wompi es la pasarela (Bold quedó como respaldo apagado). PayPal, Mercado Pago o una transferencia… | descartado | Wompi basta; otra pasarela entra cuando haya clientes del exterior. |
| 165 | Cobros: no se puede cobrar por debajo del costo ni regalar saldo con vencimiento (promociones, créditos de… | unido a PND-299 | El saldo de bienvenida es el regalo que faltaba. |
| 167 | Cobros: casos de borde donde lo cobrado y lo entregado no cuadran (todos centavos, ninguno pierde plata de… | aceptado | Son centavos (Daniel, 2026-10-13: lo que vale menos de US$ 1 no frena nada); la auditoría de PND-013 los revisa si crecen. |
| 168 | Cobros: un tipo de tarea marcado «cobra» exige saldo positivo aunque esa corrida concreta sea gratis (Reddit… | aceptado | Es conservador, y con el saldo de bienvenida casi no se nota. |
| 170 | Cobros: algunas cifras de lo ya gastado que ve el cliente de un proyecto que cobra no coinciden exactamente… | aceptado | Diferencias de centésimas. |
| 173 | Cobros: costos de escala que hoy no duelen. `_filas_cobradas` lee todos los cobros del proyecto en cada… | aceptado | Hoy no duele. |
| 174 | Cobros: pruebas y migración que faltan. La migración 0033 (era la 0032 en la rama; renumerada al mezclar main… | aceptado | El módulo ya tiene muchas pruebas; las nuevas llegan con el lote 1. |
| 180 | Mitad «Cambiar solo el gancho» hecha el 2026-10-09 (spec 2026-10-09-tw-ganchos-y-copy-design.md, rama… | descartado como pendiente | Es la etapa 3 de una función nueva. |
| 181 | Etapa 4, predecir antes de gastar: la tarjeta «probable» de una pieza nueva, comparada con lo que gana en la… | descartado como pendiente | Es la etapa 4 de una función nueva. |
| 182 | Mitad «copy nuevo» hecha el 2026-10-09: el análisis trae `copy_nuevo` (título y texto en el idioma del… | descartado | Duplicar anuncios en Meta toca lo público; se retoma con PND-193. |
| 183 | Los videos de TikTok llegan de Triple Whale como una página (`www.tiktok.com/embed/…`), no como archivo: la… | descartado | Es un límite de Triple Whale. |
| 184 | «Pausar/Activar en Meta» de una pieza de Creatv se quedó solo en «Ver como tabla»; el spec §2.1 lo pedía… | aceptado | Un clic de más. |
| 186 | Residuales menores de las revisiones de las tarjetas de Triple Whale (2026-10-08). (1) Si Whisper falla… | aceptado | Menudencias; el (1) pasa a la auditoría de PND-013. |
| 188 | `triple_whale.medio_permitido` acepta el host de R2 también para las URLs que llegan en los datos de Triple… | aceptado | Sin daño. |
| 195 | Meta (pestaña Rendimiento): la frecuencia de un conjunto no se copia (solo la de la cuenta y la de cada… | descartado | Dato menor. |
| 197 | La parte Meta de la pestaña Rendimiento no soporta el modo agencia: «Elegir cuentas de Meta» (en «Ajustes»,… | unido a PND-052 | Solo importa si se usa el modo agencia. |
| 198 | Meta rendimiento, menudencias de la revisión de la tarea 10: (a) ya resuelto (un POST de «Elegir cuentas» sin… | aceptado | Menudencias. |
| 200 | Meta rendimiento: una primera copia puede durar más que `TimeoutStopSec=600` del worker (8 a 14 min por… | aceptado | La copia se reanuda sola. |
| 201 | Meta rendimiento E1, menudencias que quedan: (1) pruebas: la migración 0035 comprueba pocas restricciones;… | aceptado | Menudencias. |
| 203 | Barras de progreso: cuando varias barras `data-poll-job` fallan a la vez, cada una muestra su propio… | aceptado | Ya no pasa en Rendimiento. |
| 205 | Meta rendimiento: `cuentas.elegir` cuenta cualquier `IntegrityError` como cuenta «rechazada» (dice «ya está… | aceptado | Menudencia. |
| 212 | Seedance 2.5 con varias referencias: los videos de la bandeja entran por su fotograma. fal admite hasta 10… | descartado | Función nueva. |
| 220 | `triple_whale.datos.visitantes_por` por campaña, conjunto o cuenta ubica cada anuncio con una subconsulta… | aceptado | 55 ms. |
| 223 | Un chip en la tarjeta de la galería de Triple Whale («2 ganchos listos») para ver los ganchos sin abrir el… | descartado | Idea. |
| 224 | «Volver a analizar» para un análisis viejo sin ganchos aunque esté fresco: hoy el panel no ofrece pagar dos… | aceptado | Un análisis se renueva al vencer. |
| 225 | Ganchos para anuncios de imagen: otra imagen de portada en vez de un clip. Hoy un anuncio de imagen recibe… | descartado | Idea. |
| 226 | Subir los 3 ganchos a Meta en pausa con su código en el nombre, si Daniel lo quiere. Hoy la persona los… | descartado | Idea que toca lo público. |
| 233 | El `por_que` de un gancho cuenta para sus `cifras_sin_dato` (spec §3.2): una cifra adivinada en la… | aceptado | Bloquear de más es más seguro que dejar pasar una cifra inventada. |
| 235 | Tres detalles de robustez de los ganchos, sin daño hoy. (1) Un texto de gancho que es solo U+200D (el unión… | aceptado | Sin daño. |
| 238 | Si `SaldoInsuficiente` salta al lanzar el clip de un gancho, su sesión de Crear ya existe (se crea y se anota… | aceptado | Sin plata en juego. |
| 244 | Planes: **2026-10-12: prueba real en producción hecha** en `colorado_forja` (reemplaza la del sandbox):… | hecho | Daniel puso las llaves de pruebas el 2026-10-13 y los 12 escenarios de error pasan contra el sandbox de Wompi (924e17e2): rechazo en el alta, gracia, anual, anulación y Nequi. Repetirlos con plata real no vale lo que cuesta. |
| 248 | Planes: facturación electrónica ante la DIAN e IVA sobre el cobro mensual del plan (se suma a PND-161, que… | unido a PND-161 | Va con la factura de las recargas. |
| 249 | Planes: dudas de Wompi que mueven código (lista en `docs/pagos/wompi-api.md` §13). **Resueltas en la prueba… | aceptado | (a) basta mientras el campo no cambie; (e) el sandbox aprueba la renovación con Nequi sin pedir nada, y lo del celular real se sabrá con el primer cliente que pague con Nequi. |
| 250 | Planes: bordes de plata que quedan. (a) La corrección de un `incluido` ignora `entregado=False`… | unido a PND-247 | Se arregla antes de activar un plan. |
| 251 | Planes: robustez menor. (a) Una caída de Wompi corta el lazo de la periódica `planes_renovar` y las… | unido a PND-247 | Se arregla antes de activar un plan. |
| 252 | Planes: deuda de higiene. `!important` en `.cobros-admin-casilla` (pasa las guardas de estilos),… | aceptado | Higiene sin daño. |
| 253 | Planes: lo que quedó fuera de esta versión. Paddle u otra pasarela en dólares para clientes del exterior;… | descartado | Ideas para otra versión de planes. |
| 254 | Planes: bordes de plata aceptados en la revisión final (2026-10-10). (a) M3: si se corrige al alza el cobro… | unido a PND-247 | Se arregla antes de activar un plan. |
| 256 | Planes: riesgos aceptados en la auditoría final (2026-10-10). (a) Nequi acepta cualquier celular colombiano:… | aceptado | Riesgos aceptados en la auditoría. |
| 259 | Meta rendimiento: avisos por correo de las recomendaciones «alta» y de una evaluación terminada. E2 solo las… | unido a PND-048 | Llega con el correo saliente. |
| 260 | Meta rendimiento: no se ve qué piezas de Crear nacieron de una idea de «Evaluar con IA» de Meta. La sesión… | descartado | Idea. |
| 261 | Meta rendimiento: las etiquetas de ubicación y dispositivo están duplicadas en `resultados.py` (Experimentos)… | aceptado | Higiene. |
| 265 | Meta rendimiento, desgloses: (1) una combinación que falla cada día conserva sus filas viejas y solo se… | aceptado | Menudencias. |
| 266 | Meta rendimiento, «Todas» con monedas distintas: el orden por impacto de las recomendaciones y la elección de… | unido a PND-276 | Monedas distintas en «Todas». |
| 267 | Meta rendimiento E2, menudencias de las revisiones de las tareas 1 a 6 que siguen abiertas: (1) desconectar:… | aceptado | Menudencias. |
| 272 | Rendimiento: dos copias de lo mismo en `triple_whale/datos.py`. `CANAL_META` repite `triple_whale.CANAL_META`… | aceptado | Higiene. |
| 273 | Rendimiento: código muerto en `entradas.armar`. El `e["cubierta"] = True` dentro del bucle de cuentas se pisa… | aceptado | Código muerto inofensivo. |
| 279 | Rendimiento: la barrera de mismo origen propia del blueprint no tiene prueba que la ejercite: la de la app… | aceptado | La barrera global ya cubre. |
| 281 | Rendimiento: la pestaña Meta jubilada el 2026-10-09 mostraba cifras por cuenta que hoy no aparecen en ninguna… | decidido | Esas cifras no vuelven: Rendimiento ya resume lo que importa. |
| 284 | Rendimiento: «Guardar en Referentes» no existe para los anuncios de fuente Meta (cuentas sin tienda). Desde… | descartado | Idea. |
| 285 | Rendimiento, «Todas» con cuentas de Meta en monedas distintas: las campañas y los conjuntos se siguen… | unido a PND-276 | Monedas distintas en «Todas». |
| 288 | Rendimiento: con el periodo de 30 días y una entrada solo Meta, el Diagnóstico (`meta_panel.diagnostico`)… | aceptado | Número fijo de consultas. |
| 289 | «Probar los 3 ganchos» desde el detalle de un análisis de un anuncio de Meta sin tienda (fuente Meta de… | aparcado | «Probar los ganchos» de Meta se queda apagado (solo admin) hasta que un cliente lo pida. |
| 302 | Privacidad, condición para cerrar PND-289: «Probar los 3 ganchos» de un análisis de fuente Meta (hoy solo un… | aparcado | Va con PND-289. |
| 305 | Plata (pantalla y aviso): un pospago con plan, entre el fin del periodo y su cierre, muestra la deuda como 0… | unido a PND-247 | Solo pasa con un plan vivo; se arregla antes de activar uno. |
| 309 | Rendimiento, «Productos en tus anuncios»: el Catálogo se lee dos veces por carga del panel… | aceptado | Una consulta de más, de número fijo. |
| 310 | Rendimiento: `triple_whale.datos.tipos_creativo` lee el tipo de TODOS los anuncios del proyecto en… | aceptado | Se filtra si la página se vuelve lenta. |

Si una decisión resulta mala, se cambia aquí y en la fila de `docs/pendientes.md`; un pendiente cerrado se reabre con su mismo ID.
