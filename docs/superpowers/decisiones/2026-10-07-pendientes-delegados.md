# Decisiones delegadas sobre pendientes (2026-10-07)

**Quién decide:** Daniel delegó las preguntas abiertas («vamos a dar lo mejor de todo, responde a tu conveniencia»,
2026-10-07). Claude decidió con tres criterios, en este orden:
1. Que ningún cobro se pierda, ni se anote dos veces, ni se esconda.
2. Que nadie vea datos que no son suyos.
3. Que no se borre nada que no se pueda recuperar.

**Qué NO se decidió aquí, y sigue en manos de Daniel:**
- lo que gasta plata real (las pruebas pagadas);
- lo legal (PND-026, PND-041);
- la marca de un cliente;
- lo que necesita sus cuentas: Meta, SMTP, llaves, Apify y fal (PND-048, 050, 052–054, 057–060, 010, 013, 021, 025, 063, 097,
  099, 101);
- borrar en el VPS (PND-103: el hook frena `git stash` allí, a propósito).

Cada fila de `docs/pendientes.md` se actualiza con su decisión al implementarla (lote 6 de Codex). Si una decisión resulta
mala, se cambia aquí y en la fila.

## Se implementan (lote 6)

| PND | Decisión | Por qué | Si sale mal |
|---|---|---|---|
| 124 | Las alertas de plata (`tablero:tope_alcanzado`, `tablero:propuestas_pendientes`, `tablero:experimento_error`, `crear:prompt_listo`, y desde la enmienda del 2026-10-08 también `tablero:ganador_sin_publicar` y `tablero:anuncios_rechazados`) solo las descarta un admin. El cliente no ve el botón y el servidor responde 403, como con `solo_admin`. Enmienda 2026-10-08: también `tablero:ganador_sin_publicar` y `tablero:anuncios_rechazados`. | Un cliente no puede esconderle al admin un aviso de plata. | El cliente ve esos avisos hasta que se resuelvan. |
| 123 | Cada cuenta cliente ve solo su propia alerta `cuenta:correo`; el admin ve todas. Se filtra al leer, por el usuario de la sesión. | Privacidad: nadie ve el correo de otra cuenta. | Ninguno. |
| 122 | Una pieza fallida que pertenece a un sprint vivo sale solo como `sprint:fallos` y no también como `crear:error`. | El reintento se hace desde el sprint, y el doble aviso infla la burbuja. | Si el sprint se archiva, el fallo vuelve a salir en Crear (como hoy). |
| 132 | Al cambiar el diario de un país después de lanzar, se bloquea todo valor cuya proyección por los días restantes pase el total del experimento. El formulario dice el máximo permitido. | Nunca gastar más de lo aprobado. | Para gastar más hay que subir el total a propósito. |
| 138 | El ROAS agrupado se calcula solo con los experimentos comparables y lleva la nota «excluye N en otra moneda». | Mostrar la cifra útil es mejor que ocultarla, siempre que diga qué deja fuera. | Ninguno: la nota lo deja claro. |
| 142 | Cada experimento fija su fuente de ventas al lanzar **según su atribución**: «triple_whale» si la atribución es Triple Whale y hay tiendas conectadas, «tienda» si es por pedidos de la tienda (utm), «meta» si es Pixel, «ninguna» si no mide ventas. Un día sin esa fuente sale «—» (no comparable), nunca se mezclan fuentes; con «ninguna» ninguna cifra dice que mide ventas. Una pieza sin ventas disponibles sigue pasando por la puerta de tráfico del decisor (solo la puerta de ventas queda pendiente). *Enmienda del 2026-10-08: la primera versión olvidaba la atribución «tienda» y dejaba sin pausar anuncios malos (revisión del lote 6A).* | Las cifras se pueden comparar y predecir. | Si Triple Whale se desconecta para siempre, el experimento muestra «—» en ventas. |
| 017 | El decisor no declara perdedor ni ganador **por ventas** con menos de 3 compras entre las piezas comparadas del país. Debajo de eso el veredicto es «inconcluso». La puerta de tráfico de hoy no cambia. | No pausar ni escalar pauta por azar. | Decide un poco más tarde. |
| 018 | Si el último snapshot de un experimento tiene más de 6 horas (Meta o Triple Whale caídos), el decisor no ejecuta nada en esa pasada y el experimento muestra «datos viejos». **Excepción: la pausa por tope sí se hace** (el gasto solo crece: si la foto vieja ya dice tope, el real es mayor). *Enmienda del 2026-10-08, revisión del lote 6A.* | No decidir con datos viejos. | Una pasada perdida; la siguiente decide. |
| 043 | Al derivar, las hermanas en cola reservan su arranque: dos ganadoras de la misma sesión nunca reciben el mismo. | Variantes que de verdad varían. | Ninguno. |
| 111 | La cifra del tablero de Final edition es el gasto real de todas las finales del proyecto (tabla `gasto`), incluidas las que fallaron y las reproducidas. Se llama «Lo que costaron las finales». | La cifra dice lo que de verdad se pagó. | Ninguno. |
| 112 | Cambiar el guion después de la final devuelve el video a «En edición». Editar el «Borrador automático» no lo devuelve (se reescribe en cada producción). | La final ya no coincide con el guion nuevo. | Ninguno. |
| 143 | Las cifras de la pieza (sesión y capa) muestran lo que de verdad se pagó en total, igual que `gasto`, no el costo del último intento. | Una sola verdad sobre lo pagado. | Ninguno. |
| 012 | La ficha completa de la voz propia se reserva en `kv` (`gastos.reservar_ficha`) ANTES de cobrar, y al abrir «Mis voces» se recupera sola, sin cobrar otra vez, la que se pagó y no se guardó. | Nadie paga una voz que no ve. | Ninguno. |
| 007 | Si el sondeo de Apify se rinde, se consulta a Apify el estado final de la corrida (es gratis), también cuando ya terminó, y se anota lo que costó. Mientras no se confirme con una corrida real qué significa `usageTotalUsd` en un actor que cobra por resultado, se anota **el mayor** entre `usageTotalUsd` y resultados × precio por resultado; si no se puede leer nada, el tope × precio, marcado `estimado` y `conciliacion_pendiente`. *Enmienda del 2026-10-08: nunca dejar un cobro sin anotar.* | Que el registro coincida con la factura. | Una llamada de lectura más. |
| 141 | Los topes de «Describir referencias» (300) y «Sugerir sonido» (200) suben a 4 000, como manda la regla 7 de CLAUDE.md. | Con topes chicos el pensamiento adaptativo deja la respuesta vacía y se paga igual. | Más tokens solo si el modelo los usa. Medir con `eval-claude` cuando Daniel apruebe el gasto. |
| 128 | Sin color de marca, **solo lo que era morado** (el precio) pasa a neutro (texto blanco con caja negra translúcida), no morado ni el azul de Creatv. El gancho, el CTA y los subtítulos quedan exactamente como estaban, con color y sin color; en el camino viejo el resaltado del karaoke sin color es el amarillo `#FFD400` del motor. *Enmienda del 2026-10-08: la primera versión cambiaba también gancho, CTA y subtítulos de todas las finales nuevas (revisión del lote 6B).* | El video es del cliente: no lleva colores de Creatv. | Ninguno. |
| 024 | «Recrear con mi producto» muestra, sin bloquear y sin afirmar que no coinciden, una línea neutra con **de qué habla el referente (su dolor, el mismo texto que ya sale en su ficha) y el producto elegido**, para que la persona vea el caso «moobs → cobija». Solo si el referente tiene un dolor real (no `ninguno-oferta` ni `ninguno-marca`). Usa la clasificación que ya existe, sin llamada nueva a Claude. *Enmienda del 2026-10-08: la primera versión comparaba la familia, que es de formato de anuncio, con la categoría del producto, y avisaba casi siempre (revisión del lote 6B).* | Evitar el caso «moobs → cobija» sin agregar costo. | La persona puede seguir igual. |
| 068 | Se retira el flujo viejo «Nueva idea» (Higgsfield). Se borran el código y las rutas, pero se conservan las piezas y los datos ya generados. | Decisión del 2026-09-18 (nada nuevo a Higgsfield). Ya no se ve en Crear y es deuda. | Volver a sacarlo de git. |
| 051 | Nicho tiene su propio carril de un hilo para las tareas que esperan a un proveedor, con parada limpia y recuperación. **Sin puntos de control ni continuaciones nuevas de Apify:** en una parada, el hilo de Nicho termina su espera como lo hacía en el carril general (esperar_hilos lo espera; en un despliegue la cola ya está vacía antes de reiniciar). *Enmienda del 2026-10-08: la primera versión agregó puntos de control y continuaciones que, en casos de borde, dejaban una corrida pagada sin anotar, sin leer o con el cobro revertido (guardian-gasto, lote 6C); el costo de un rediseño así no lo justifica. Los barridos de Referentes (`referentes_barrer`) van en el mismo carril: comparten con Nicho la RAM de la cuenta de Apify y, en paralelo, el segundo recibía un 402. PND-049 se despliega con la mejora parcial (paridad exacta) y queda abierto para el resto.* | Que finales y sprints no esperen a Apify. | Revisión con `revisor` y prueba de concurrencia. |
| 049 | El editor recorta antes de escalar: toma la ventana visible en píxeles de origen y la escala después. Lleva prueba de paridad con la vista previa y medición de memoria en la imagen Docker `render-vps`. | Que un zoom alto no mate el render por memoria. | Se ve en la paridad: si no cuadra, no se despliega. |

## Preguntas que dejó el lote 5 (decididas el 2026-10-08)

| PND | Decisión | Por qué |
|---|---|---|
| 076 | Sí: pantalla de admin con las cuentas bloqueadas por intentos de login y un botón «Desbloquear» (solo admin, POST del mismo origen, sin contraseñas ni tokens en pantalla). Entra al lote 6. | Hoy un bloqueo solo se quita esperando o a mano en el servidor. |
| 080 | Sí: una edición pasa a «producida» cuando una final se renderiza desde ella. No cambia qué se borra. Entra al lote 6. | El estado tiene que decir la verdad; borrar es otra decisión (PND-064). |
| 088 | Sí: «Repetir QA» solo vuelve a revisar las piezas que no pasaron. Entra al lote 6. | Repetir sobre lo aprobado gasta en Claude sin necesidad. |
| 095 | Sí a paginar la lista de audios (24 por página, como las demás listas). Lo demás queda como está. Entra al lote 6. | Rendimiento de la página. |
| 070 | No se retira el banco de prompts por ahora: retirarlo cambia lo que recibe Claude al proponer ideas. Se mide en la tanda de pruebas pagadas antes de decidir. | Regla 2 de CLAUDE.md y `eval-claude`. |
| 072 | Las sesiones viejas del director no se migran: siguen funcionando como hoy. | Migrarlas cambia prompts ya armados y no arregla nada visible. |
| 084 | El código repetido entre los paneles de voz y subtítulos se unifica solo cuando se vuelva a tocar el editor. | Sin daño hoy; otra frontera entre módulos. |
| 092 | Lo que queda de Nicho (botón «Probar», `edad_rango`, helpers) se cierra: no vale lo que cuesta. | Higiene sin efecto para el cliente. |
| 094 | Variantes por la Admin API y selectores que cargan al pedirlos pasan a proyectos nuevos (grupo 8 del plan). | Son funciones nuevas, no arreglos. |
| 136 | Lo que queda del centro de resultados (reparto, destino, ranking, «Activar») pasa a la entrega E3 de Experimentos. | Lo decide ese rediseño. |

## Lote 7 (decidido por Claude el 2026-10-09; Daniel dijo «sí, lánzalo»)

| PND | Decisión | Por qué | Costo si sale mal |
|---|---|---|---|
| 190 | `nicho_inv_consultas` y `nicho_inv_seleccionar` pasan a `max_intentos=1`. Si fallan, la investigación queda en error con su motivo y la persona la retoma con el botón que ya existe (o uno nuevo «Reintentar» con el precio a la vista), sin volver a pagar lo ya hecho. | Regla 1: lo que cobra no se reintenta solo. | Un fallo pide un clic más. |
| 166 | `sprint_analizar_referencia` y `sprint_sugerir_personas` anotan su gasto real (con el `usage` de Claude, como `sprint_proponer_ideas`), pasan a `max_intentos=1` y muestran su precio estimado junto al botón o la acción que las lanza. Si un análisis falla, la referencia ofrece «Reintentar análisis» con su precio. | Hoy cobran saldo para arrancar pero salen gratis y sin aviso; con Cobros, el cliente debe ver y pagar lo que gasta. | Unos centavos por referencia que antes no se anotaban. |
| 159 | Apify: la corrida se anota apenas se conoce su id. Si el POST responde sin el id del dataset, se lee la corrida (gratis) para obtenerlo; si tampoco se puede, se anota tope × precio marcado `estimado` y `conciliacion_pendiente`. Un POST que arranca una corrida nunca se reintenta solo (los GET sí). | Nunca un cobro sin anotar ni dos corridas por un timeout. | Un fallo de red pide un clic más. |
| 187 | Las miniaturas que Triple Whale guarda en Referentes van a R2 con el proyecto en la clave (`clientes/<cliente>/referentes/…`). Las ya subidas se quedan donde están; solo cambian las nuevas. | Un proyecto no debe poder pisar el archivo de otro. | Ninguno. |
| 176 | Se deja como está: una idea descartada no necesita aviso de error. | La persona ya dijo que no la quiere. | Ninguno. |
| 177 | Se arregla: un `extra` guardado como JSON `null` cuenta como vacío al marcar el cambio de guion. | Arreglo de una línea. | Ninguno. |
| 178 | `limpiar_reservas_muertas` solo borra reservas sin tarea viva con más de 10 minutos. | Cierra la ventana entre reservar y encolar. | Ninguno. |
| 191 | Se investiga la prueba de orgánico que falla a veces (reloj u orden) y se arregla la PRUEBA o su aislamiento, sin cambiar la publicación. | Una suite que falla a veces esconde fallos reales. | Ninguno. |

*Enmiendas del 2026-10-09 tras la revisión del lote 7 (guardian-gasto + revisor):* «Reanudar» de Nicho muestra lo que puede costar TODO lo que falta (suma de los pasos pendientes, con tope en lo aprobado menos lo gastado; «precio no disponible» si un paso no tiene estimado), no solo el siguiente paso. «Traer las fotos del producto» muestra cuántas fotos se van a analizar y el total. El botón «Sugerir personas» de la cabecera de Sprints NO vuelve (Daniel lo quitó el 2026-09-22): la ruta queda sin pantalla. Los botones con precio usan el texto de `gastos.estimar` («precio no disponible» si falla el margen). Las llamadas de analizar y sugerir conservan los reintentos del SDK de Anthropic, como las demás. Un 429 al arrancar una corrida de Apify sí se reintenta (no arranca nada); la red caída y los 5xx no. La corrida de Apify se anota con su estimado apenas se conoce su id y la anotación final corrige el monto.

## Lote 8 (decidido por Claude el 2026-10-09; Daniel dijo «sí, arregla meta_ads y lanza el lote 8»)

| PND | Decisión | Por qué | Costo si sale mal |
|---|---|---|---|
| 152 | Hecho por Claude el 2026-10-09: `instalaciones-app` quedó mezclada en el main de dacolora/CreaTvMetaAds (fe88fff, mismo código que 8a21bc5); el puntero de producción ya vive en main. | Que un despliegue no dependa de una rama suelta. | Ninguno. |
| 160 | Un segundo clic en «Lanzar a Meta» mientras el lanzamiento corre no toca el estado del experimento: responde «ya se está lanzando» y el experimento termina activo como pidió el primer clic. | Lanzar ya activa (pedido de Daniel, 2026-10-08); un doble clic no puede dejarlo en pausa. | Ninguno. |
| 209, 210, 032 | Se arreglan los desbordes y los filtros apretados a 375 px con la Base visual común (el CSS en `static/estilos/`). Claude los mira en captura antes de desplegar. | Regla 8: en el celular nada empuja la página de lado. | Ninguno. |
| 155 | Se arreglan (1) «299 Kr» y «NOK 299» como precio en Nicho, (2) `_final_detalle.html` usa la lista central de idiomas y (3) «Traer referentes» ofrece Noruega y Suecia. (4) se deja: el país del calendario sale del país del proyecto; la ruta queda para el admin. | Noruega y Suecia ya están en producción. | Ninguno. |
| 149 | Se arreglan (2) «Todas» no resta gasto duplicado un día en que solo una tienda tiene fila, (3) la marca `aviso_sin_tienda_tw` se limpia al conectar la tienda de ese país, (4) «uk» se adivina como GB, (5) los ajustes sin tiendas no se ignoran en silencio y (6) «la última avisa» es atómica. Se dejan (1) la lista de países por tarjeta (pocas tiendas por proyecto), (7) cambiar ajustes con una copia en curso (anterior y raro) y (8), que necesita la primera copia real. | Que el MER de «Todas» no salga inflado y los avisos sean ciertos. | Ninguno. |
| 023 | Se cierra sin código: el cambio de subtítulos es del 2026-10-01 y los clientes ya llevan días produciendo con él; un aviso ahora sería ruido. Si Daniel quiere avisarles, lo hace él en persona. | Evitar avisos tardíos. | Ninguno. |

## Se dejan como están (cerradas con su motivo)

| PND | Decisión | Por qué |
|---|---|---|
| 029 | No se toca la regla de marca de happyflops: sigue «nada de logos en la imagen». | Es la regla de marca del cliente y Crear no la agrega (el prompt va tal cual). Si Happy Flops la quiere cambiar, lo pide. |
| 065 | No se borran materiales pagados del editor. | Lo pagado no se puede regenerar gratis; el espacio es barato. Revisar si R2 pasa de 50 GB. |
| 066 | Los snapshots de métricas se siguen guardando cada 2 h. | Son la historia de la gráfica y la frescura de los datos; compactarlos cambia cifras. |
| 121 | Las alertas siguen con su caché de 60 s. | Lo que cambia la persona ya se ve al instante; solo lo del worker tarda hasta 60 s. |
| 091 | La tanda de traducción de copycoders se baja solo si se vuelve a importar. | Hoy no corre; cambiarla altera lo que se le manda a Claude sin necesidad. |
| 064 | Borrar lo rechazado de R2 y `salidas/`: primero un **informe en seco** (qué se borraría y cuánto pesa), con 90 días y nunca lo que está en un experimento, publicado o aprobado. Se borra solo después de que Daniel vea el informe. | Borrar es irreversible. |
| 110 | Las tarifas de guion y final se calibran cuando haya un mes de gasto real (desde el 2026-11-02). | Hace falta el dato. |

## Pruebas que gastan (grupo 7 del plan): necesitan un sí de Daniel con el precio

Presupuesto propuesto para hacerlas todas juntas: **hasta US$ 15**.
- `eval-claude` del guion (PND-108) y de los topes nuevos (PND-141): unos US$ 2.
- Kling con `@Image1` (PND-035), receta del director (PND-071), «Que Wan mejore mi prompt» (PND-073) y Seedance con imagen
  final (PND-074): unos 6 a 8 videos cortos, unos US$ 10.

PND-019, PND-020 y PND-037 necesitan antes algo de Daniel: una tienda en Triple Whale, pauta real o los tokens de cada red.
