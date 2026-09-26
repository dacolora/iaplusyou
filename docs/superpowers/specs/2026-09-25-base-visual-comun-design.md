# Base visual común — diseño (parte 1 de 4 de «mejorar toda la experiencia visual»)

Fecha: 2026-09-25. Aprobado por Daniel en el chat el mismo día.

## Contexto

Recorrido visual de las 8 pestañas del proyecto (Tablero, Nicho, Referentes, Crear,
Experimentos, Sprints, Catálogo, Configuración) con datos reales en local, escritorio y
celular. Las causas comunes de lo «feo»:

- `h2` global es la etiqueta en mayúsculas con rayita («— SPRINTS»), y es lo que cada pestaña
  usa como título: no hay jerarquía. Arriba de todo se repite el nombre del proyecto en grande
  (`<h1 id="titulo-seccion">` en `cliente.html`).
- La descripción de cada pestaña usa `.vacio` (la clase del «todavía no hay…», con
  `padding: 1rem 0`): de ahí los huecos raros.
- El estilo base de campos (`textarea, select, input[type=number|text|password]`) deja fuera
  42 campos: 26 sin `type`, 7 `url`, 5 `email`, 2 `search`, 2 `date`. Salen como controles
  nativos del navegador.
- `.campo-label` en mayúsculas convive con `label` normales y leyendas de `fieldset` sin estilo.
- `.btn-generar` (el botón principal morado) tiene letra `#180d02` (café) sobre morado.
  `.btn`, `.btn-primary`, `.btn-secondary` se usan en plantillas y no tienen estilo; un
  `button` con solo `.btn-sm` cae en el gris del navegador.
- Los desplegables «+ Nuevo sprint», «+ Nuevo estudio», «Reglas del motor»
  (`details.swap-card > summary.swap-card-resumen`) parecen cajas de texto.
- `cliente.html` no escucha `hashchange`: un enlace `#settings` (alertas del Tablero, «Ir a
  Configuración →») no cambia de pestaña si ya estás en la página; al cambiar de pestaña la
  página queda a media altura.

## Decisiones

- Se mantiene la identidad: fondo claro, acento morado (`--accent`, `--accent-grad`), Space
  Grotesk + Inter. Cambia la consistencia, no la marca.
- Se quita el nombre grande del proyecto (`.pagina-cabecera h1`); el nombre sigue en la ruta de
  arriba («Proyectos / Happy Flow») y en el `<title>`.
- Textos, rutas y funciones no cambian. Es CSS más ajustes de marcado en `cliente.html` y las
  plantillas de pestaña.

## Componentes

1. **Encabezado de pestaña** (`.panel-cabecera`, ya presente en Tablero, Nicho, Referentes,
   Experimentos, Sprints; se agrega en Crear, Catálogo y Configuración): fila con el bloque de
   texto a la izquierda y `.panel-cabecera-acciones` a la derecha (se envuelve debajo en
   pantallas angostas). Dentro, el `h2` es el título de la pestaña: display, ~1.6rem, color de
   texto, sin mayúsculas ni rayita. La descripción es `.panel-cabecera-desc` (muted, sin el
   padding de `.vacio`, ancho de lectura ~70ch). Acción principal por pestaña: Referentes
   («Traer referentes», «Mis barridos»), Sprints («+ Nuevo sprint»), Nicho («+ Nuevo estudio»),
   Tablero («Descargar CSV del mes», ya está). Los `h2` que no están en el encabezado siguen
   siendo la etiqueta de subsección.
2. **Campos**: el estilo base cubre todo lo que se escribe o elige: `input:not([type])` y los
   tipos text, number, password, email, url, search, tel, date, time, datetime-local, month,
   más `select` y `textarea`. Foco morado. `input[type=file]` sin recortar su texto.
   `.campo-label`: texto normal (sin mayúsculas), .8rem, 600. `fieldset`: recuadro con borde y
   radio del sistema; `legend`: display, 600.
3. **Botones**: `button` sin clase propia = secundario (fondo `--panel-2`, borde `--border`).
   Principal = `.btn-generar`, `.btn-aprobar`, `.btn-primary` (degradado, **letra blanca**).
   Secundario = `.btn-guardar`, `.btn-secondary`, `.btn`. Peligro = `.btn-rechazar`,
   `.btn-peligro`. Tamaños `.btn-sm`, `.btn-xs`.
4. **Desplegables**: `summary` con cursor, 600 y flecha; `.swap-card-resumen` como fila
   clicable con flecha que gira al abrir; los «+ Nuevo …» en color de acento.
5. **Estado vacío** (`.estado-vacio`): recuadro con borde punteado, título corto
   (`.estado-vacio-titulo`), una línea (`.estado-vacio-texto`) y opcionalmente un botón. En
   Nicho, Referentes, Sprints y la galería de Experimentos. Un botón con
   `data-abrir-detalle="<id>"` abre ese `details` y lo trae a la vista (Sprints, Nicho).
6. **Pestañas**: `cliente.html` escucha `hashchange` y activa la pestaña del hash si existe
   (lo demás se ignora, así un `#algo` que no es pestaña no rompe nada); al cambiar de pestaña
   por clic o por hash la página vuelve arriba. La carga inicial no cambia.

## Fuera de esta parte

Menú de celular (parte 2), rediseño de Crear y Configuración y flujo viejo «Nueva idea»
(parte 4), imágenes rotas y videos sin portada (parte 5).

## Verificación

- `venv/bin/python3 -m pytest -q -m "not slow"` completa en verde (no hay pruebas atadas al
  marcado que cambia; se mantienen los textos que las pruebas buscan).
- Recorrido de las 8 pestañas en la app local (lanzador sin llaves, ver la nota
  «verificar-ui-sin-contrasena») en escritorio 1280×800 y celular 375×812, con captura de
  antes y después; comprobar a mano: foco, un `#settings` desde el Tablero, «+ Nuevo sprint»
  desde el estado vacío, formulario de Sprints y de Nicho.
- Commit propio sobre `main`, desplegado solo (solo web: son plantillas y CSS).
