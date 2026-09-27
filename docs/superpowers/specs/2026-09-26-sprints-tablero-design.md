# Sprints como tablero con panel de campaña — diseño (entrega 1 de 2)

Fecha: 2026-09-26. Aprobado por Daniel en el chat, por partes (forma del flujo, tarjeta, datos,
panel, búsqueda de referentes, errores, pruebas y alcance), con bocetos del compañero visual.

## Problema

Daniel odia cómo se crea un sprint (asistente de pasos + modal «Agregar campaña») y la campaña no
aprovecha la biblioteca de referentes. Mapa del flujo actual (2026-09-26):

- El asistente de `_tab_sprints.html` quedó a medio desarmar: «Siguiente: la matriz →» sin matriz,
  resumen vacío, botones Atrás/Siguiente del paso 2 visibles en todos los pasos, total de costo
  muerto, «Descripción» (`notas`) y `destinos` que no llegan a ningún lado.
- Crear o seguir una campaña reparte el trabajo en páginas sueltas (referencias, ideas, revisión)
  a las que solo se llega por redirección; las mini-pantallas AJAX del sprint (📎 💡 ✓) están rotas
  (no suben archivos, formularios que ignoran campos, conteos en 0).
- La campaña solo le pasa a los referentes la etapa (`funnel`) y, si la persona viene de Nicho, la
  consciencia. Producto, país, idioma, formato, dolor y marcas no se usan.
- El modal «Agregar campaña» del asistente y el del sprint no coinciden; «Variante (opcional)» es
  obligatoria de hecho; el funnel no se ve ni se edita después.
- Se insertan a la fuerza tres personas genéricas (Melissa, Marijke, Sophia) en todo proyecto y no
  hay pantalla para personas manuales ni temporadas (0020 ya volvió opcional la temporada).

Datos de la biblioteca en producción (2026-09-26): 5 535 referentes con imagen, **ninguno con
país**, idioma `en` 5 035 / `es` 500, todos `imagen`, 223 familias, 229 marcas; `dolor` en inglés
y texto libre («beer belly», «ninguno-oferta»…).

## Decisiones (del chat)

- **Tablero**: el sprint es una página con una tarjeta por campaña; «+ Nuevo sprint» es un
  formulario corto y el resto se arma en el tablero.
- **Tarjetas compactas + panel lateral** para editar una campaña (en celular el panel ocupa la
  pantalla).
- La campaña define: persona, producto, etapa, **consciencia, dolor o deseo, familias de formato,
  país/idioma y marcas a imitar**.
- País/idioma y marcas se definen en el **sprint** y cada campaña puede cambiarlos solo para ella.
- Personas: las de **Nicho + «crear persona rápida»** en el panel; las tres genéricas dejan de
  crearse solas (las que ya existen en HappyFlops no se borran).
- **«Momento del mes»** opcional en el sprint (del calendario del país o propio) reemplaza a la
  temporada por campaña; las campañas lo heredan.
- **Todo en el tablero por fases**: esta es la entrega 1 (armar + referentes). La entrega 2 (otra
  especificación) mete ideas, lote y revisión en el mismo panel.
- Se quita la unicidad persona+producto+temporada: puede haber TOF/MOF/BOF (o dos TOF con distinto
  formato) para la misma persona y producto; solo un aviso suave si ya hay una idéntica.

## Pantallas

### «+ Nuevo sprint» (pestaña Sprints)

Formulario corto, sin pasos: nombre; inicio y fin (por defecto el mes siguiente); país e idioma
(por defecto `proyectos.pais(cliente)` y español); momento del mes opcional (`sprints.calendario.
presets(pais)` o texto propio); marcas a imitar opcionales (nombre y, si se tiene, link del Ad
Library). «Crear y armar campañas →» crea el sprint y abre su tablero. La lista de sprints de la
pestaña no cambia.

### Tablero (`GET /cliente/<c>/sprints/<sid>`, reemplaza `sprint_detalle.html`)

- **Cabecera** (editable ahí mismo): nombre, fechas, país/idioma, momento, marcas; resumen
  «N campañas · M piezas planeadas · X/Y referentes elegidos»; acciones que ya existen (Generar
  lote, Revisar, Archivar, Eliminar).
- **Tarjetas**: etapa (TOF/MOF/BOF), número, persona · producto, consciencia · dolor, miniaturas
  de los referentes elegidos (vacíos hasta el objetivo), cantidades y **el siguiente paso** según
  el estado (elegir referentes → proponer ideas → aprobar ideas → generar → revisar).
- **«+ Campaña»** abre el panel en modo nuevo: persona y producto primero (obligatorios); al
  elegirlos se crea la campaña y el panel pasa al modo completo.
- `?panel=<cid>` abre el panel al cargar (lo usan las acciones que recargan la página).

### Panel de la campaña (fragmento por fetch, como la ficha de un referente)

Se guarda solo, campo por campo. Secciones:

1. **Audiencia y producto**: persona (Nicho + las existentes del proyecto; «+ Crear persona
   rápida»: nombre + una línea, `datos.crear_persona(origen="manual")`); producto como una sola
   lista donde cada variante es su opción («HOriginal — Beige»).
2. **Enfoque**: etapa (TOF/MOF/BOF); consciencia (5 niveles en español, claves de
   `doctrina.CONSCIENCIA_DESDE_INGLES`), precargada desde la persona de Nicho si la tiene; dolor o
   deseo (texto) con sugerencias sacadas de la persona (situaciones, evidencia, encaje).
3. **Formato**: familias de la biblioteca elegidas como etiquetas (buscador sobre las 223) más
   sugeridas para la etapa y la consciencia.
4. **Mercado y marcas**: lo del sprint con «cambiar solo aquí» (vacío = hereda).
5. **Piezas**: videos, imágenes, referentes objetivo.
6. **Referentes**: elegidos (con ✕) y sugeridos (con +); botones «Sugerir con IA ≈ US$»,
   «Buscar en la biblioteca» (grid en modo selección ya filtrado), «Traer nuevos de Meta»
   (formulario de Traer referentes prellenado con país, producto o marcas) y «Subir · link · fotos
   del producto» (las rutas actuales).
7. Pie: eliminar campaña; «Ideas de esta campaña →» a la página actual de ideas (hasta la
   entrega 2).

## Datos (migración 0021)

- `sprint`: `pais` String(2), `idioma` String(5), `marcas` JSON (lista de `{nombre, pagina_id?}`),
  `momento` JSON (`{clave?, nombre, contexto?, inicio?, fin?, mood_visual?}`); todos opcionales.
- `campana`: `consciencia` String(24), `dolor` Text, `familias` JSON (lista de nombres),
  `pais` String(2), `idioma` String(5), `marcas` JSON; los tres últimos NULL = hereda del sprint.
- Se elimina `uq_campana_combinacion` (batch, como 0020); `sprints.datos.agregar_campana` deja de
  lanzar `CampanaDuplicada` y devuelve un aviso si ya hay una idéntica (persona, producto, etapa,
  consciencia, familias).
- `sprints.datos` es el único escritor: validación de cada campo nuevo (consciencia en las claves de
  `doctrina`, etapa en `FUNNELS`, familias existentes, país ISO de 2 letras, idioma en `es, en, pt, fr, it, de` — la misma lista de «Traer referentes»),
  y una función para leer el valor **efectivo** (campaña o sprint) de país/idioma/marcas.
- `asegurar_personajes_predeterminados` deja de insertar las tres genéricas (no se borra nada).
- Los sprints existentes abren igual en el tablero, con los campos nuevos vacíos; si una campaña
  tiene temporada, las ideas la siguen usando cuando el sprint no tiene momento.

## Referentes sugeridos

`referentes/sugerir.py` (determinista, gratis) pasa a recibir la campaña efectiva:

- **Filtran**: etapa (siempre), consciencia y familias si están puestas. Si no alcanza el objetivo,
  afloja primero las familias y después la consciencia, y devuelve qué aflojó (el panel lo dice).
- **Ordenan**: marcas a imitar primero, luego el idioma de la campaña, luego
  `variantes × max(días, 1)` como hoy; una por familia salvo que la campaña haya elegido familias.
- **País** no filtra la biblioteca (no hay datos): va a «Traer nuevos de Meta» (Apify con país
  real) y al idioma de los textos.
- **«Sugerir con IA»** (`referentes_sugerir_ia`, `max_intentos=1`, precio a la vista) recibe además
  consciencia, dolor, familias y marcas; filtra candidatos igual que el camino gratis.
- Lo que llega con «Traer nuevos» no se agrega solo: aparece en los sugeridos.

## Ideas

`sprints/ideas.py` suma al prompt maestro: consciencia (etiqueta de `doctrina`), dolor o deseo,
familias elegidas con su descripción, mercado (país e idioma de la audiencia), marcas a imitar y el
momento del mes (o la temporada vieja si el sprint no tiene momento).

## Se quita

- El asistente de `_tab_sprints.html` (pasos, modal, matriz muerta y su JS).
- El formulario «+ Agregar campaña» de `sprint_detalle.html`.
- Las mini-pantallas del sprint `_sprint_referencias_ajax.html`, `_sprint_ideas_ajax.html`,
  `_sprint_revision_ajax.html` y sus rutas `…-ajax`.

Siguen igual (enlazadas desde el panel): páginas de referencias, ideas, lote, revisión y entrega.
Las rutas de personas/temporadas sin pantalla no se tocan.

## Errores

- Guardado de un campo que falla (red o validación): el campo vuelve a su valor y muestra el motivo
  a su lado; el resto del panel no se toca.
- Dos pestañas: gana el último guardado de cada campo.
- Sin sugeridos: estado vacío con «aflojar filtros», «Sugerir con IA» y «Traer nuevos de Meta».
- Abrir el panel y los sugeridos gratis no gastan; IA y Traer muestran el precio antes del clic.
- Campaña o sprint que ya no existe: el panel lo dice y ofrece volver al tablero.

## Pruebas

- `sprints.datos`: campos nuevos y su validación, herencia sprint → campaña, persona rápida, sin
  personas genéricas en proyectos nuevos, campañas «idénticas» permitidas con aviso.
- `referentes.sugerir`: filtros, orden por marca e idioma, cómo afloja y qué informa.
- Rutas: formulario corto, tablero, panel (nuevo y completo), guardado por campo (JSON), agregar y
  quitar referentes, eliminar campaña, sprints viejos abren; `?panel=`.
- `sprints.ideas`: el prompt lleva los campos nuevos y el momento (o la temporada vieja).
- Migración 0021 (columnas, sin la unicidad, llaves foráneas intactas) y ensayo en una copia de la
  base de producción antes de desplegar.
- En pantalla (app local sin llaves), escritorio 1280×800 y celular 375×812: armar un sprint de
  punta a punta; ningún desplazamiento lateral.

## Fuera de esta entrega

Ideas, lote y revisión dentro del panel (entrega 2); pantalla de personas y temporadas; país en los
datos de la biblioteca; referentes de video como video.
