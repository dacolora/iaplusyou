---
name: ui
description: "Pantallas de Creatv: la base visual común de static/style.css, el celular, las tarjetas ligeras con detalle por fetch, las barras de progreso con data-poll-job y las reglas de rendimiento de la página del proyecto. Cargar antes de agregar o cambiar una pantalla, una tarjeta, una lista, una barra de progreso, o tocar cliente.html, base.html o style.css."
---

# Pantallas: base visual, celular y rendimiento de la página

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**UI base** (2026-09-25/26, specs `2026-09-25-base-visual-comun` and `2026-09-26-movil`): the
block «Base visual común (2026-09-25)» at the END of `static/style.css` is the source of truth for
fields, labels, buttons (`.btn-generar` = primary with white text; `.btn-sm`/`.btn`/classless
`button` = secondary), `summary`, the tab header (`.panel-cabecera` > text div with `h2` +
`.panel-cabecera-desc`, plus `.panel-cabecera-acciones`) and `.estado-vacio`; new screens reuse
those instead of new one-off styles. `cliente.html` switches tabs on `hashchange` and scrolls to
top; `data-abrir-detalle="<details id>"` opens a `<details>`. Up to 760 px the sidebar leaves the
screen and opens with «☰ Menú» (`body.menu-abierto`); nothing may scroll the page sideways
(`tests/test_base_visual.py`, `tests/test_movil.py`). Phone review of every screen (2026-09-28, CSS block «Celular: revisión de pantallas» at the end of `style.css`): auto-fill grids use `minmax(min(100%, X), 1fr)` (never a bare fixed minimum — a test rejects it), card galleries (Crear, Final edition, Experimentos, Referentes) are 2 columns ≤ 760 px, button/filter rows (`.acciones`, summaries) wrap, long ids/JSON/URLs break instead of pushing the page, and data tables (`tabla-admin`, `tabla-tiendas`, `tabla-productos`, `gasto-tabla`, `sprint-entrega`, `gpg-tabla`, or opt-in `tabla-apilada`) become one card per row ≤ 640 px with each value labelled from its column header (`static/tablas.js` copies the `<th>` text to `data-etiqueta`, also for tables inserted later by fetch); `.solo-teclado` hides keyboard-only hints on touch screens. Crear's «Desde referencias» form is a **composer**
(spec `2026-09-27-crear-compositor`, CSS block «Crear: compositor»): a card whose top half is the bandeja
(OUTSIDE `#form-flowplus`, it carries its own `<form>`s) and whose bottom half is the form, with a bar of pills
whose menus hold the real radios/selects — the selects stay the hidden source of truth and the menus draw chips
from them —, so the POST to `cf_crear_video` is unchanged; upload/link inputs reach their empty outside forms via
`form=`, the catalog opens as a `<dialog>` (`_selector_productos.html` with `sel_dialogo=True`; «Cambiar producto»
keeps its `<details>`), and Enter in a one-line input never submits it (it used to generate and charge).

**Rendimiento y almacenamiento (auditoría 2026-09-28, tras el incidente de la página que se
quedaba cargando):** `/cliente/<c>` trae todas las pestañas en un solo HTML (3 MB en happyflops:
Crear, Final edition y Experimentos repiten las mismas piezas con sus `<template>` de detalle), así
que lo que se agrega ahí le cuesta a TODAS las cargas. Reglas que salieron de la auditoría: los
`<video>` de listas nacen `preload="none" data-precarga` (base.html los pide al entrar en pantalla;
`tests/test_referentes_copycoders_proyecto.py` rechaza `preload="metadata"`) y las `<img>` van
`loading="lazy"`; las fotos del catálogo se piden con `?w=320` (`catalogo_productos.miniatura`,
Pillow, caché en `data/miniaturas/`); nada de una consulta por tarjeta: `ver_cliente` corre bajo
`trabajos.con_vivos_precargados` (UNA lectura de los job_ids vivos para todos los `en_curso`) y la
lista de Crear usa `creative_flow.guiones_base`/`finales_por_sesion` y
`doctrina.revisor.ultimos_captions` (`tests/test_perf_pagina_proyecto.py` falla si el número de
consultas vuelve a crecer con las piezas); `informe.completo` solo se arma para el admin; los
estáticos con `?v=` salen `immutable` un año (`/static/editor/` sigue `no-cache`); la biblioteca de
copycoders está apagada por proyecto hasta que la persona la trae (`proyectos.referentes_copycoders`).
Mantenimiento diario en el worker (`tareas/mantenimiento.py`): `salidas_limpiar` borra de `salidas/`
lo que tenga más de 14 días (todo lo de ahí es copia de trabajo: el video vive en R2 y
`publicador.archivo_local`, `final_edition._clon_local`, `materiales.descargar` y `sprints.qa`
lo vuelven a bajar), `cola_limpiar` purga las `tarea` cerradas (7 días; periódicas, 1 día) y
`db_respaldar` guarda `data/respaldos/creatv_<fecha>.db` (`Connection.backup`, 7 copias). Sigue
pendiente (no se hizo): borrar en R2 lo rechazado/descartado y las versiones viejas de finales,
`materiales_limpiar` no borra nada porque los proxies viven en la fila del video (no son `EFIMEROS`),
`metrica_snapshot` inserta cada 2 h aunque nada cambie.
**Tarjetas ligeras y detalle bajo demanda** (spec
`docs/superpowers/specs/2026-09-28-tarjetas-ligeras-detalle-bajo-demanda-design.md`): el 61 % de
la página eran los `<template class="generado-detalle">` de Crear y Final edition (1,86 MB de 3,03).
Ya no existen: las tarjetas son macros (`_crear_tarjetas.html`: `tarjeta_crear`/`lista_crear`;
`_final_tarjetas.html`: `tarjeta_video_fe`/`tarjeta_final_fe`/`lista_videos_fe`/`lista_finales_fe`),
la página pinta las 24 más recientes por lista (`TARJETAS_POR_PAGINA`, `_listas_crear_final`; los
contadores muestran el total) y «Ver más» pide las siguientes a `crear_tarjetas` /
`final_tarjetas?lista=videos|finales` (`?desde=N`, `_pagina_desde`). El detalle llega por fetch al
abrir la tarjeta (`data-detalle` → `cf_detalle`, `fe_detalle_video`, `fe_detalle_final`; macros en
`_crear_detalle.html` / `_final_detalle.html`, armadas con `_creative_flow_item(cliente, cf_id)` y
`_contexto_final_edition(cliente)`, que incluye `_contexto_organico`), nunca se cachea, y
`base.html` lo pinta con `abrirDetalleRemoto(modal, cuerpo, url, alInsertar)` («Cargando…» al
instante, solo el último pedido gana). `#final?cf=<id>` abre la pieza aunque no esté pintada.
Reglas: **ninguna barra de progreso lleva `<script>`** — todas `data-poll-job="<job_id>"` sobre el
`div.barra-progreso#trabajo-<job_id>` y `arrancarSondeos(raiz)` (DOMContentLoaded + el
MutationObserver de `data-precarga`) arranca el sondeo de lo que aparezca; los clics de tarjetas
van delegados sobre la cuadrícula (las agregadas por «Ver más» funcionan igual); el sondeo se pausa
con `document.hidden` y baja de ritmo (`intervaloSondeo`: 1,5 s → 3 s al minuto → 5 s a los 5 min).
`tests/test_tarjetas_ligeras.py` y `test_perf_pagina_proyecto.py` vigilan todo esto. Fuera de
alcance (anotado en el spec §7): el JS embebido a estáticos, Experimentos por fragmentos (Catálogo
ya carga su galería y su ficha por fragmento desde 2026-09-30: ver «Catálogo ecommerce y
conectores»), el chequeo de Meta en la carga, los N+1 de Sprints/Experimentos, el flujo viejo
«Nueva idea».
