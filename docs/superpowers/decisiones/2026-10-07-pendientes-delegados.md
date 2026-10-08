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
| 051 | Nicho tiene su propio carril de un hilo para las tareas que esperan a un proveedor, con parada limpia y recuperación. | Que finales y sprints no esperen a Apify. | Revisión con `revisor` y prueba de concurrencia. |
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
