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
Un archivo de la doctrina para una etapa (investigar, ángulo, gancho, guion, video, caption, clasificar, revisar);
cada llamada recibe la base más una o dos.

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
