# Creatv Machine

Plataforma que convierte ideas en piezas de video e imagen con IA y las prueba, publica y
mide en Meta para varios proyectos (clientes) a la vez. Este glosario recoge solo los
términos propios del producto; empieza por la conexión con Meta (ADR 0001-0003) y crece a
medida que se resuelven otros términos.

## Language

### Conexión con Meta

**Proyecto**:
Un cliente de la plataforma con su carpeta, su contenido, su conexión con Meta y su gasto
propios. En el código y las rutas se llama `cliente`.
_Avoid_: cuenta, tenant, marca

**Forma (de conectar)**:
Lo que el cliente eligió en Configuración › Meta para conectar: «agencia» (que Creatv lo
gestione) o «propia» (con su propia app de Meta). Es una intención: existe antes de que haya
conexión.
_Avoid_: modo (es otra cosa), opción, tipo de conexión

**Modo (de conexión)**:
El estado real de la conexión con Meta de un proyecto, leído de `meta.json`: «agencia»
(opera con la credencial del Business de Creatv) o «propia» (opera con su propia app y su
propio token). Si hay conexión sin forma elegida, la forma vigente es el modo.
_Avoid_: forma, tipo

**Agencia**:
El Business Manager de Creatv conectado una sola vez por el admin con un usuario del
sistema; opera únicamente los activos que cada cliente compartió como socio o que Creatv
posee.
_Avoid_: app global, credencial compartida

**Activo**:
Una cuenta publicitaria, una Página de Facebook o una cuenta de Instagram que un negocio
posee y puede compartir con un socio en Business Manager.
_Avoid_: recurso, asset

**Portafolio (comercial)**:
El Business Manager de un cliente en Meta, identificado por su ID; es el dueño de sus
activos y desde donde los comparte con Creatv.
_Avoid_: business, BM, cuenta de negocio

**Asignación**:
El acto de poner un proyecto en modo agencia con una cuenta publicitaria (y opcionalmente
una Página) que el Business de Creatv ve; la hace el propio cliente en autoservicio o el
admin desde el panel. Una cuenta publicitaria solo puede estar asignada a un proyecto.
_Avoid_: vinculación, enlace

**Solicitud (de conexión)**:
El aviso que deja un cliente en forma «agencia» cuando compartió sus activos pero Creatv
todavía no los ve; queda pendiente hasta que el admin asigna el proyecto o la descarta.
_Avoid_: ticket, petición, pendiente

**Puesta a punto**:
La sección de Configuración que dice qué llaves y conexiones tiene el proyecto y cuáles le
faltan, sin mostrar nunca un valor. El administrador ve todas las llaves del servidor; un
cliente ve solo lo que se configura por proyecto (Meta) y lo que le toca hacer ahí.
_Avoid_: setup, checklist

### Doctrina de venta

**Doctrina**:
Los principios de venta que la app le da a Claude en cada llamada que escribe o clasifica copy; vive en
`doctrina/textos/*.md`, en nuestras palabras.
_Avoid_: reglas de estilo (eso es la guía de marca), prompt maestro

**Rebanada**:
Un archivo de la doctrina para una etapa (investigar, ángulo, gancho, guion, video, caption, clasificar, revisar,
diagnosticar); cada llamada recibe la base más una o dos.

**Ángulo**:
Las decisiones que se toman antes de escribir una pieza: audiencia y su consciencia, sofisticación del mercado,
deseo, promesa única, mecanismo, pruebas, arranque, gancho y lo que falta. Claude lo propone y viaja con la pieza.
_Avoid_: brief, concepto, enfoque (ya es producto/persona/libre en Crear)

**Consciencia**:
Qué tanto sabe la audiencia de su problema, de las soluciones y del producto: inconsciente, consciente del problema,
de la solución, del producto, muy consciente.
_Avoid_: awareness, etapa (eso es TOF/MOF/BOF)

**Sofisticación**:
Qué tan quemado está el mercado, de 1 (nadie lo prometió) a 5 (agotado: solo identificación); desde 3 hace falta
mecanismo.
_Avoid_: madurez, competencia

**Arranque** (lead):
Cómo abre la pieza: oferta, promesa, problema-solución, secreto, proclamación o historia; se elige por la consciencia.
_Avoid_: hook (eso es el gancho), intro

**Gancho**:
La primera frase o el texto de los primeros tres segundos: llama a la audiencia, implica un beneficio y deja
curiosidad. Es la expresión del arranque.

**Mecanismo**:
Cómo el producto logra la promesa, solo con lo que dice su ficha.

**Prueba**:
Un hecho que respalda la promesa con su fuente: la ficha del producto, un comentario real o algo que la pieza muestra
pasar. Sin fuente no es prueba.

**Datos del mercado**:
La consciencia de una persona y la sofisticación de un producto elegidas a mano; cuando existen, Claude no las decide.
_Avoid_: segmentación, nivel

**Prueba del producto**:
Un hecho real con su fuente (dato que dio el cliente o comentario real de un comprador) guardado en el producto; entra
en todo lo que se escribe con ese producto y cuenta como dato verificado.
_Avoid_: testimonio inventado, beneficio

**Pedido**:
Algo concreto que Claude necesita del cliente para escribir mejor sobre un producto («pega un comentario real sobre…»);
responderlo crea una prueba del producto.

**Ángulo editado a mano**:
Un ángulo guardado desde la app; pasa a ser de quien lo editó y sus cifras se usan tal cual.

**Revisión de la doctrina**:
Los 12 puntos de la lista de revisión contestados sobre una pieza terminada: las reglas gratis siempre a la vista y, si
se pide, la revisión de Claude con los fotogramas. Solo informa; nunca bloquea ni reescribe.
_Avoid_: QA (el QA de Sprints revisa la calidad técnica; desde el bloque 3 trae también la revisión)

**Diagnóstico (de una perdedora)**:
Por qué perdió una pieza, según el motor: una o más de las ocho causas de la lista (el gancho no retiene, sin urgencia
en el deseo, demasiado educativo, estacionalidad, repetición, la landing no continúa el anuncio, posicionamiento
equivocado, lo visual no da creencia), con su evidencia, más el siguiente paso y una frase de aprendizaje. Se hace solo,
una vez por veredicto, y solo informa: al rescate y a la persona.
_Avoid_: veredicto (eso es ganó/perdió; el diagnóstico es el porqué), revisión (la revisión mira la pieza antes de gastar)

**Siguiente paso**:
Lo único que el diagnóstico recomienda cambiar: otro gancho, otra estructura, regenerar el video, revisar la oferta,
revisar la landing o pausar. Otra estructura y regenerar saltan el escalón del rescate (nunca hacia atrás); la oferta,
la landing y pausar dejan el rescate en propuesta en todo modo, porque no los arregla otro creativo.

**Aprendizaje (del proyecto)**:
Una línea por prueba decidida («Ganó en CO: …», «Perdió en MX: … Diagnóstico: …») o escrita a mano, guardada en el
proyecto (40 como máximo, las más nuevas primero) y leída como DATOS por las ideas de sprint, el guion base y las
variantes. Nunca obliga a nada.
_Avoid_: regla, insight

### Catálogo

**Producto**:
Lo que se vende: una carpeta `clientes/<c>/productos/<pid>/`, su entrada en `productos.json` y UNA fila comercial.
_Avoid_: activo (a secas), item

**Color**:
Una versión visual de un producto (en Shopify «Colour», «Patterns»…) con sus propias fotos de referencia: una
subcarpeta `<pid>/<color_id>/` con el id compuesto `pid/color`.
_Avoid_: variante (es el nombre técnico en `productos.json`), colorway, SKU

**Producto plano**:
Un producto sin colores; sus fotos de referencia van en la raíz de su carpeta.

**Foto de estudio**:
La foto de referencia de un color: la que Shopify liga a la variante.

**Foto de ambiente**:
Una foto del producto sin color asignado (lifestyle). En un producto con colores vive en la raíz de su carpeta y no es
referencia.
_Avoid_: foto general (nombre interno: `fotos_generales`)

**Activo del catálogo**:
Cualquier cosa del catálogo que se elige como referencia en Crear, Sprints o «Cambiar producto»: un color, un
producto plano, un personaje o un entorno (cada entrada de `catalogo_productos.listar()`). Distinto del «Activo» de Meta.

**Fila comercial**:
La fila `producto` de un producto, una sola aunque tenga colores: precio, moneda, URL de compra, en prueba, prioridad,
sofisticación, pruebas y pedidos.

**Tienda pública**:
Una tienda Shopify conectada solo con su dominio, sin llaves («Shopify (sin llaves)», `shopify_publico`): lee el
catálogo público y guarda sus filas con la fuente `shopify`, la misma de la conexión por Admin API. Es la fuente del
catálogo: si la Admin API también está conectada, esa solo suma pedidos y atribución.

**Ficha**:
El panel lateral de un producto, un personaje o un entorno en la pestaña Catálogo.
_Avoid_: detalle, modal

**Producto archivado**:
Un producto que la persona sacó de circulación con «Archivar» en su ficha, o que su tienda dejó de listar: no se borra
nada, solo deja de salir en la galería (queda en «Archivados») y al elegir producto, salvo donde ya estaba elegido.
Vuelve con «Desarchivar».
_Avoid_: eliminado, oculto, inactivo

### Cobros

**Costo**:
Lo que Creatv le paga al proveedor por una generación; es la fila de la tabla `gasto`, sin cambios. Solo lo ve el
admin en un proyecto que cobra.
_Avoid_: precio (es lo que paga el proyecto), gasto (es el nombre de la tabla y de la pantalla)

**Precio**:
Lo que paga un proyecto que cobra: el costo × el margen, redondeado hacia arriba a la milésima de dólar. Es lo único que
ve la persona del proyecto, en los botones («≈ US$») y en lo ya gastado.
_Avoid_: tarifa (es el costo por unidad de un proveedor, `gastos.TARIFAS`)

**Margen**:
El multiplicador del costo (1,5 por defecto, de 1,00 a 5,00): global en `kv` y propio de un proyecto si el admin lo
fija. En inglés, «markup». El margen del primer registro de un gasto queda en el cobro; cambiarlo no recalcula lo
ya cobrado.
_Avoid_: comisión, recargo, porcentaje

**Saldo**:
La suma del libro de movimientos de un proyecto, en milésimas de dólar enteras. Puede quedar negativo (el costo real
superó al estimado, una anulación de Bold) y entonces no se genera nada que cueste hasta recargar.
_Avoid_: crédito, créditos (los créditos son los de Higgsfield, del flujo viejo)

**Disponible**:
El saldo menos las reservas vivas. Es lo que mira el freno antes de aceptar un trabajo; el respaldo del worker mira el
saldo, no el disponible.

**Reserva**:
Lo que un trabajo encolado aparta del disponible mientras su tarea está pendiente o en curso (`reserva_saldo`, por
`job_id`). No se libera a mano: al terminar la tarea, bien o mal, deja de contar.

**Recarga**:
Un ingreso de saldo: con Bold (el cliente paga un link y el webhook firmado la acredita) o manual (el admin). Va en
dólares enteros, de 10 a 1 000. Lo acreditado son los USD que se eligieron; lo que Bold cobra en pesos queda solo como
registro.
_Avoid_: pago (es lo que reporta Bold), compra, depósito

**Cobrar** (el interruptor):
La casilla por proyecto que decide si el uso se descuenta del saldo. Arranca apagada; prenderla no cobra lo ya
generado. Un proyecto con «Cobrar» apagado, o sin cuenta de saldo, se comporta como siempre. En inglés, «Charge usage».
_Avoid_: facturar, activar saldo

**Movimiento**:
Una fila del libro de un proyecto (`movimiento_saldo`): `recarga`, `cobro`, `reverso`, `no_cobrado` (monto 0, avisa
que no se cobró una pieza), `ajuste` o `anulacion`. No se borra ni se edita, salvo el recálculo de un cobro cuando el
costo de su gasto se corrige.
_Avoid_: transacción, asiento
