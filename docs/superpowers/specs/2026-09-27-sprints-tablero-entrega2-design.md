# Sprints como tablero — entrega 2: ideas, generar y piezas dentro del panel

Fecha: 2026-09-27. Aprobado por Daniel en el chat, por partes (dónde se revisa, forma del panel,
pestaña Ideas, pestaña Piezas y revisión del sprint, páginas viejas, convivencia con la doctrina,
dinero, errores y pruebas), con bocetos del compañero visual. Continúa la entrega 1
(`docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`, en producción desde 2026-09-27,
main 0c84628, migración 0021).

## Problema

Después de elegir referentes, el trabajo de una campaña se va a tres pantallas sueltas: la página
de ideas de la campaña (`campana_ideas.html`), el modal «Generar lote» (`_sprint_lote_modal.html`)
y la página de revisión del sprint (`sprint_revision.html`). El panel de la campaña solo llega hasta
«Ideas de esta campaña →». Además, «Proponer ideas» llama a Claude sin mostrar precio y sin
registrar su gasto real (`tareas/sprints.py::ejecutar_proponer_ideas` no llama a
`gastos.registrar_seguro`), en contra de la regla del proyecto.

## Dependencia: doctrina, bloque 2

La rama `doctrina-bloque-2` (otra conversación; revisión final hecha, aún no en `main` el
2026-09-27) cambia justo la página de ideas: el ángulo de cada idea a la vista y editable
(macro `editor_angulo` en `templates/_angulo_editor.html`, `static/angulo.js` con
`window.iniciarEditoresAngulo(raiz)`, ruta `sprints.idea_angulo`), «Reescribir la idea con este
ángulo» (`sprints.idea_reescribir`, tarea `sprint_reescribir_idea`, tarifa `reescribir_idea`),
el selector «Qué tanto sabe <persona>» (`sprints.persona_conciencia`), la sofisticación del
producto (`producto.extra.sofisticacion`, se elige en Catálogo), los «datos fijos del mercado»
(`sprints.ideas.fijos_de`) y `sprints.analisis._llamar_contando` (texto + tokens para el gasto).

Esta entrega se construye **encima** de ese bloque, una vez esté en `main`: reutiliza sus piezas y
no las duplica. Si al empezar la implementación el bloque 2 todavía no está en `main`, se espera
(o se le pide a esa conversación que lo suba); nunca se mezcla su rama sin su revisión.

**Consciencia (regla única):** manda la de la campaña (`campana.consciencia`, entrega 1, que ya se
precarga de la persona de Nicho). Si la campaña no tiene, vale la de la persona
(`persona.extra.conciencia.nivel`). `fijos_de` (o su equivalente tras la fusión) recibe la campaña
y aplica esa precedencia; el selector «Qué tanto sabe <persona>» no se repite dentro del panel.

## Decisiones (del chat)

- **Pasos dentro del panel:** tres pestañas arriba — **Armar · Ideas · Piezas** — cada una con su
  conteo («Armar ✓», «Ideas 7/10», «Piezas 6/10»).
- El panel abre en la pestaña que toca según `tablero.siguiente_paso`: `referentes` → Armar;
  `aprobar`, `ideas`, `generar` → Ideas; `generando`, `errores`, `revisar`, `lista` → Piezas. La
  URL la recuerda: `?panel=<cid>&paso=armar|ideas|piezas` (cambiar de pestaña hace
  `replaceState`). Un `paso` inválido cae en el que toca.
- **Revisión en los dos sitios:** cada campaña revisa sus piezas en su panel y además se mantiene la
  revisión de todo el sprint (página «Revisar» con atajos y filtros).

## Pestaña «Armar»

Lo de la entrega 1, más:

- En Enfoque, solo lectura: «Promesas parecidas que ya vio el cliente: <nivel> · <texto> (se
  cambia en Catálogo)» con la sofisticación del producto (o «Claude lo decide»).
- Los referentes que dicen «falta describir» se describen ahí mismo: al tocar la miniatura se
  abre debajo un recuadro con las intenciones (`sprints.datos.INTENCIONES_NOMBRE`, chips) y la
  descripción; se guarda solo con la ruta que ya existe (`sprints.referencia_editar`, JSON) y al
  quedar «lista» se actualizan la tarjeta y el conteo. La página de referencias de la campaña se
  queda como «Más opciones de referencias» (reutilizar de otra campaña, links en descarga).

## Pestaña «Ideas»

- Arriba: «N de M aprobadas · videos a/b · imágenes c/d» y los botones «✨ Proponer las que faltan
  (X videos, Y imágenes) (≈ US$ Z)», «+3 videos», «+3 imágenes» (con su precio) y «Aprobar todas
  las propuestas». Mientras Claude propone: barra de progreso del trabajo (`iniciarPolling` con la
  URL de la pestaña; al terminar, la página vuelve al mismo panel y pestaña) y los botones de
  proponer deshabilitados.
- Cada idea viva es una fila compacta (tipo, título, duración, enfoque, estado: propuesta /
  aprobada / generada) que se abre para editar: título, escena, sonido (video), gancho — se
  guardan solos con `sprints.idea_editar` (JSON) —, el editor del ángulo de la doctrina
  (`editor_angulo`, iniciado con `iniciarEditoresAngulo(panel)` tras insertar el fragmento), las
  miniaturas de los referentes en que se apoya, y las acciones Aprobar, Otra idea, Reescribir con
  este ángulo (≈ precio, solo si el ángulo tiene promesa) y Descartar. Una idea con pieza queda de
  solo lectura con «Ver su pieza →» (abre la pestaña Piezas).
- Las descartadas van plegadas al final («▸ N descartadas»).
- Al pie, la caja **Generar**: «N aprobadas sin generar (v videos, i imágenes)», modelo de video y
  de imagen (por defecto los del proyecto) y el costo real al momento (`sprints.lote_estimar` con
  `campana_id`); el botón «Generar N piezas — US$ X» encola con `sprints.lote` (`campana_id`,
  respuesta JSON) y pasa a la pestaña Piezas. Sin ideas por generar, la caja lo dice y no ofrece el
  botón. El modal del encabezado del tablero («Generar lote» del sprint entero) no cambia.

## Pestaña «Piezas»

- El panel se ensancha (`min(960px, 100%)`; en celular ya ocupa la pantalla).
- Arriba: «L listas · G generando · C en cola · E con error · A aprobadas · US$ X gastado» (la entrada de
  esa campaña en `produccion.progreso(cliente, sid)["campanas"]`) y «Aprobar las que pasaron QA (n)» solo de esta
  campaña.
- Cuadrícula de piezas (no descartadas, con sesión de Crear): video con póster o imagen; estado
  (en cola, generando, lista, con error y su motivo); QA (puntaje, chequeos ✓/✗ con su nota,
  «QA pendiente…», «QA falló · Repetir QA»); revisión (pendiente / aprobada / rechazada con su
  motivo). Acciones: Aprobar; Rechazar con el motivo en un campo dentro de la tarjeta (no
  `prompt()`), obligatorio; Reintentar (error) y Regenerar, ambos con su precio en el botón y una
  confirmación; «Abrir en Crear» (edición final, experimentos).
- Mientras haya piezas en cola, generando o con QA pendiente y la pestaña Piezas esté a la vista,
  la pestaña se actualiza sola cada 8 s (vuelve a pedir solo su contenido); no pisa un motivo de
  rechazo que se esté escribiendo y se detiene al cerrar el panel o cambiar de pestaña.
- Sin piezas: estado vacío que lleva a la pestaña Ideas.

## Revisión de todo el sprint (`sprint_revision.html`)

Se queda con sus atajos (A, R, flechas), filtros, «Aprobar todas las que pasaron QA», «Cerrar
sprint» y «Entrega». Cambios: el filtro de campaña dice «<n> · <ETAPA> · <persona> · <producto>»;
cada pieza trae «Abrir en el panel» (tablero con `?panel=<cid>&paso=piezas`); rechazar pide el
motivo en el mismo campo dentro de la tarjeta que el panel.

## Rutas y datos

Sin migraciones. Las rutas existentes de ideas y piezas (`ideas_proponer`, `ideas_aprobar_todas`,
`idea_editar`, `idea_aprobar`, `idea_descartar`, `idea_otra`, `idea_reescribir`, `idea_angulo`,
`lote_estimar`, `lote`, `pieza_revision`, `pieza_reintentar`, `pieza_regenerar`, `pieza_qa`,
`revision_aprobar_qa`) responden JSON cuando las llama el panel (`X-Requested-With: fetch`) y,
llamadas desde un formulario, vuelven al tablero con el panel y la pestaña correspondientes.
`revision_aprobar_qa` acepta `campana_id` opcional. `campana_ideas` (GET) redirige a
`sprints.ver` con `panel=<cid>&paso=ideas`. El fragmento del panel lleva las tres pestañas; la de
Piezas también se puede pedir sola para la actualización automática.

## Dinero

- «Proponer ideas» (y «+3», «Otra idea»): precio aproximado en el botón (`gastos.estimar`, tarifa
  nueva por número de ideas, medida en una llamada real) y **gasto real registrado** por
  `gastos.registrar_seguro(cliente, "ideas", usd, "idea:proponer:<cid>:t<tarea_id>", ...)` con los
  tokens de todas las llamadas de esa propuesta (incluida la corrección), también cuando la
  respuesta no sirvió.
- Reescribir, Generar, Reintentar y Regenerar muestran su precio antes del clic; nada se relanza
  solo (`max_intentos=1` como hoy).

## Errores

- Propuesta de ideas o lote ya en curso para esa campaña: el botón lo dice («Ya hay una propuesta
  en curso») y no encola otra.
- Idea con pieza: no se edita ni se descarta (regla actual `MENSAJE_IDEA_CON_PIEZA`); se regenera
  desde Piezas.
- Guardado que falla: el campo vuelve a su valor y el motivo aparece a su lado (como en la
  entrega 1); una respuesta que no es JSON muestra el aviso genérico de la entrega 1.
- Rechazar sin motivo: el campo lo pide y no envía.
- Campaña o sprint que ya no existe: el panel lo dice y ofrece volver al tablero (entrega 1).

## Pruebas

- `tablero`: `paso` por defecto según `siguiente_paso` (función pura) y `paso` inválido.
- Rutas: el panel trae las tres pestañas con sus conteos y abre la pedida; JSON de cada acción de
  ideas, generar y piezas; redirecciones de formulario al panel; `campana_ideas` redirige;
  `revision_aprobar_qa` por campaña; la pestaña Piezas sola.
- Gasto: proponer ideas registra el gasto real en éxito y en respuesta inválida; el precio sale en
  el botón.
- Revisión del sprint: filtro nuevo y «Abrir en el panel».
- En pantalla (app local sin llaves), escritorio 1280×800 y celular 375×812: proponer (con
  Claude simulado o sin llave, el error se ve bien), aprobar, abrir y editar una idea con su
  ángulo, estimar el lote, revisar piezas con distintos estados; ningún desplazamiento lateral;
  modo oscuro.

## Fuera de esta entrega

Pantallas de personas y temporadas; «Proponer ideas en todas las campañas» de un clic; atajos de
teclado dentro del panel; la edición final dentro del panel (sigue en Crear).
