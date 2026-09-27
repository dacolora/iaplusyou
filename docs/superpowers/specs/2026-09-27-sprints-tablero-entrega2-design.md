# Sprints: ideas y lote dentro del panel de campaña (entrega 2 de 2)

Fecha: 2026-09-27. Continúa `docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`
(entrega 1, en producción), que dejó explícitamente fuera "ideas, lote y revisión dentro
del panel". Aprobado por Daniel en el chat (alcance, pestañas del panel, qué se queda
afuera) con mockups del compañero visual.

## Problema

El panel lateral de una campaña (`_sprint_panel.html`) ya arma persona, enfoque, formato,
mercado y referentes con autoguardado. Pero para proponer/aprobar ideas y generar el lote
hay que salir a `campana_ideas.html`, una página aparte con su propio flujo de guardado
(fetch para editar campos, pero formularios con recarga completa para proponer/aprobar
todas/reescribir/otra idea). Revisar el sprint completo (`sprint_revision.html`) es distinto:
filtra piezas de TODAS las campañas con atajos de teclado para aprobar/rechazar en cadena,
así que no encaja en un panel por campaña.

## Decisiones (del chat, con mockup)

- El panel gana una segunda pestaña interna **"Ideas · N"** (N = ideas vivas) junto a
  **"Armar"** (lo que ya existe: audiencia, enfoque, formato, mercado, piezas, referentes).
  Cambiar de pestaña es solo mostrar/ocultar en el cliente — las dos vienen en la misma
  respuesta de `campana_panel`, sin una segunda petición.
- **Revisión sigue siendo su propia página** (`sprint_revision.html`), sin cambios; se
  seguirá enlazando desde la cabecera del tablero como hoy.
- **"Generar lote" no es código nuevo**: el modal (`_sprint_lote_modal.html`) y su JS
  (`abrirLote(campanaId)`, ya global en `sprint_detalle.html`) no cambian; la pestaña
  Ideas solo agrega un botón que lo llama.
- `campana_ideas.html` y su ruta `sprints.campana_ideas` **desaparecen**: todo lo que
  hacían pasa a la pestaña Ideas del panel. El único enlace externo que apuntaba ahí
  (la insignia "Sprint · Campaña N" en `_tab_creativeflowplus.html`) pasa a abrir el
  tablero con el panel y la pestaña Ideas ya seleccionados.
- Las acciones de idea (proponer, aprobar todas, aprobar una, descartar, "otra idea",
  reescribir con ángulo, editar campos) pasan a responder JSON y a dispararse por fetch
  igual que ya hacen "aprobar" y "editar campo" hoy — nunca un formulario con recarga de
  página. Las que encolan un trabajo de Claude (proponer, reescribir) usan el mecanismo
  YA existente de `data-poll-job` + `iniciarPolling` (el mismo de "Sugerir con IA"): barra
  de progreso sin recargar, y al terminar recarga la página completa (ya reabre el panel
  por el `?panel=`, patrón ya establecido, no uno nuevo).

## Pantallas

### Panel de la campaña: pestañas

`_sprint_panel.html` antepone una barra de dos pestañas (`Armar` / `Ideas · N`) al
`<div class="panel-campana">`. Las secciones actuales (audiencia…referentes) quedan
envueltas en `<div data-tab="armar">`; el pie ("Eliminar campaña") se queda fuera de
ambas pestañas, siempre visible. El enlace "Ideas de esta campaña →" del pie desaparece
(ya no hace falta: es la otra pestaña).

### Pestaña "Ideas" (`_panel_ideas.html`, nuevo, incluido por `_sprint_panel.html`)

Contenido de `campana_ideas.html` portado tal cual (conteo de aprobadas, botones
"Proponer las que faltan / 3 videos más / 3 imágenes más / Aprobar todas", tarjetas de
idea con editor de ángulo (`_angulo_editor.html`, sin cambios) y sus acciones, selector
de consciencia de la persona), MENOS: el `<script>` propio (todo el JS pasa al bloque
compartido de `sprint_detalle.html`, porque el HTML de un fragmento por fetch no corre
sus `<script>`, igual que ya pasa con `_sprint_panel.html`) y los `<form method="post">`
con recarga (se vuelven botones con `data-*` manejados por delegación, igual que
referentes). "Generar lote de esta campaña" usa `onclick="abrirLote({{ c.id }})"` tal cual
hoy.

## Rutas (`sprints/rutas.py`)

- `campana_panel` (ya existe): agrega al contexto lo que hoy arma `campana_ideas`
  (`ideas`, `conteo`, `enfoques`, `trabajo_ideas`, `nivel_persona`, `sof_producto`,
  `precio_reescribir`, `reescribiendo`) para que `_sprint_panel.html` pueda incluir
  `_panel_ideas.html` en la misma respuesta.
- `ideas_proponer`, `ideas_aprobar_todas`, `idea_reescribir`, `idea_otra`: ganan la rama
  `if _quiere_json(): return jsonify(...)` que ya tienen `idea_editar`/`idea_aprobar`/
  `idea_descartar` (mismo criterio: cuerpo `{ok: true, ...}` en éxito, `{ok: false,
  error}` con 400/409 en error — p. ej. "ya hay una propuesta en curso" o
  `MENSAJE_IDEA_CON_PIEZA`); la rama de formulario (flash + redirect) se queda para
  scripts/pruebas viejas que no manden el header.
- `campana_ideas` (GET) se **elimina**; su URL deja de existir.
- `sprints.ver`: acepta `?tab=ideas` (además del `?panel=` que ya acepta) y lo pasa al
  template como `tab_inicial`.

## Plantillas fuera de Sprints

- `_tab_creativeflowplus.html:241`: el `href` de la insignia "Sprint · Campaña N" cambia
  de `sprints.campana_ideas` a `sprints.ver` con `panel=<cid>` y `tab=ideas`.
- `mapa_codigo.html`: las dos filas que listan `campana_ideas` como página propia se
  actualizan para reflejar que las ideas viven en el panel (texto, no afecta rutas).

## JS (`sprint_detalle.html`, dentro del bloque `window.tableroPanelListo`/delegación ya
existente — nada de scripts nuevos por fragmento)

- Tabs: un manejador de click delegado en `panel` para `[data-tab-btn]` que
  muestra/oculta `[data-tab="armar"]`/`[data-tab="ideas"]` y marca el botón activo;
  `tableroPanelListo` selecciona `armar` por defecto, o `ideas` si
  `panel.dataset.tabInicial === 'ideas'` (una sola vez, al abrir por el enlace externo).
- Autoguardado de campos de idea (título/escena/sonido/gancho): mismo patrón que ya
  existe para los campos de la campaña (`data-sucio`, guardar en `blur`/debounce), pero
  apuntando a `sprints.idea_editar` por idea — se generaliza la función `guardar()' ya
  escrita para que la use cualquier `[data-url-campo]`, no solo el de la campaña.
- Botones de acción de idea (`data-idea-aprobar`, `data-idea-descartar`, `data-idea-otra`,
  `data-idea-reescribir`, `data-ideas-proponer`, `data-ideas-aprobar-todas`): fetch POST,
  al terminar refrescan la pestaña Ideas (recargando el panel completo con `T.abrir(cid)`,
  igual que ya hacen los referentes) — no hace falta granularidad menor porque abrir el
  panel ya es rápido (misma consulta que hoy).
- El editor de ángulo (`static/angulo.js`) sigue intacto: ya funciona por delegación de
  eventos sobre el documento, no depende de que su HTML esté en una página completa.

## Se quita

- `templates/campana_ideas.html`.
- La ruta `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/ideas` (`sprints.campana_ideas`).
- El enlace "Ideas de esta campaña →" del pie del panel.

Sigue igual: `sprint_revision.html` y su ruta; `_sprint_lote_modal.html` y `abrirLote`;
`campana_referencias.html` (para describir referentes pendientes, ya fuera del alcance de
la entrega 1).

## Pruebas

- `sprints.rutas` (rutas): `campana_panel` devuelve el HTML de las dos pestañas con las
  ideas de la campaña; `ideas_proponer`/`ideas_aprobar_todas`/`idea_reescribir`/
  `idea_otra` responden JSON con el header de fetch (éxito y cada error ya cubierto en
  su versión de formulario); `campana_ideas` ya no resuelve (404); `sprints.ver` con
  `?tab=ideas` pasa `tab_inicial` al contexto.
- Plantillas: `_panel_ideas.html` no tiene `<script>` propio (regla ya probada para
  `_sprint_panel.html`); ambas pestañas están presentes en el HTML de `campana_panel`
  aunque una esté oculta por CSS (para que el fetch no dependa de un segundo viaje).
- Suite completa (`pytest -q`) sin marcar `slow` para el ciclo corto, completa antes de
  desplegar.

## Fuera de esta entrega

Revisión dentro del panel (se descartó: no encaja con "revisar todo el sprint seguido");
`campana_referencias.html` (describir referentes pendientes) sigue aparte.
