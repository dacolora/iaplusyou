---
name: sprints
description: "Sprints de contenido: el plan mensual como tablero de campañas (persona, producto, consciencia, referencias, ideas, generar lote, QA, revisión, entrega). Cargar antes de tocar sprints/, tareas/sprints.py, sprint_detalle.html o los _sprint_*.html."
---

# Sprints de contenido

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Sprints de contenido** (`sprints/` + `tareas/sprints.py`, spec
`docs/superpowers/specs/2026-09-16-sprints-design.md`): a monthly production plan.
Since 2026-09-26 it is a **board** (spec `docs/superpowers/specs/2026-09-26-sprints-tablero-design.md`):
«+ Nuevo sprint» is a short form (month, optional «momento del mes» from the PROJECT's calendar
`sprints.calendario.presets(proyectos.pais(cliente))` or free text, brands to imitate; CO, MX, NO and SE have their own calendar since 2026-10-08 (reason: happyflops' audience is Norway and Sweden; spec 2026-10-08-noruega-y-suecia §5), any other country falls back to CO; `datos.IDIOMAS_NOMBRE` names sv/no with `idiomas_publicacion`, never the bare code, because `no` reads as the word «no» in a prompt). Since 2026-09-27
a sprint is **for every country**: no país/idioma in the form, the sprint header or the campaign panel
(`CAMPOS_SPRINT`/`CAMPOS_CAMPANA` refuse them), new sprints store `pais=NULL` and
`idioma=datos.IDIOMA_BASE` ("en"), the idea prompt says «todos los países… cada país los adapta después
en la edición final», and localization per country/language is final edition's job; old sprints keep the
país/idioma they had (still read through `efectivos`). The sprint page (`sprint_detalle.html`) is a board with one card
per campaign (`_sprint_tarjeta.html`, «Siguiente: …» from the pure `sprints/tablero.py`) plus a side
panel (`_sprint_panel.html`, fetched; all its JS lives in `sprint_detalle.html` because scripts in
fetched fragments never run) that saves field by field (`sprints.campana_campo` /
`sprints.sprint_campo`, JSON `{campo, valor}`; `?panel=<cid>` reopens it). Tables `persona`,
`temporada`, `sprint` (`pais`, `idioma`, `marcas`, `momento` since 0021), `campana` (`consciencia`,
`dolor`, `familias`, and `pais`/`idioma`/`marcas` that override the sprint's — NULL inherits, read
through `sprints.datos.efectivos`; no uniqueness since 0021: TOF/MOF/BOF of the same persona and
product are allowed and `campanas_identicas` only warns; the three generic personas are no longer
auto-created), `referencia` (intención tags + descripción; a reference
without descripción is `borrador` and does not count toward progress),
`campana_pieza` (Parte 2) and `sprint_evento`. `sprints/datos.py` is the only
writer; `sprints/estado.py::recalcular` re-derives campaign/sprint states after
every event (states are stored but never trusted blindly); `sprints/progreso.py`
is pure. Routes live in the Blueprint `sprints/rutas.py`
(`/cliente/<cliente>/sprints/...`), registered from `dashboard.py`, which also
adds `sprints_rutas.contexto(cliente)` to the project page. Uploading a
reference enqueues `sprint_analizar_referencia` (Claude vision, cents); "Sugerir
personas" enqueues `sprint_sugerir_personas`; a pasted link goes through
`sprint_referencia_link` (yt-dlp via `referencias_link.descargar`). A reference can also come straight from the referentes library (`origen='biblioteca'`, pre-analyzed, no `sprint_analizar_referencia`): `sprints.datos.agregar_referencia_biblioteca` (deduped per campaign), the Referentes grid's `?campana=` selection mode, `referentes/sugerir.py` (deterministic + optional Claude pick, task `referentes_sugerir_ia`, tariff `sugerir_ia`), and 'Usar en sprint' from a referente's ficha. The panel's free suggestions come from `referentes.sugerir.sugerir_campana` (filters etapa + consciencia + familias, loosens familias then consciencia and says so, ranks brands to imitate → campaign language → variantes × días); «Sugerir con IA» sees the same candidates (`candidatos_aflojando`) plus dolor, marcas and the momento, and `sprints/ideas.py` passes enfoque, mercado, marcas and the momento (or the old temporada) to the idea prompt. Parte 2 (producción): `sprints/ideas.py` asks Claude for ideas per campaign
(prompt maestro: persona + producto + temporada + reference analyses + brand
guide + banco de prompts) stored as `campana_pieza` rows; "Generar lote"
(`sprints/produccion.py`) shows the estimated cost first, then creates one
Crear session per approved idea (`creative_flow.crear(..., extra_sprint=)`,
prompt via `flowplus_prompt.armar(..., contexto=)`) and enqueues it through
`flowplus_lanzar.lanzar(..., prioridad=3)` — `tarea.prioridad` makes single
pieces from Crear (5) jump ahead of batches. `campana_pieza.cf_id` joins
`pieza.legado_id`, so progress and states come from the real sessions. The
worker periodic `sprint_qa_pendientes` (5 min) queues `sprint_qa_pieza`
(`sprints/qa.py`: Claude vision + ffprobe → `campana_pieza.qa`, never
generates) and emails when a batch finishes. The QA row (score, one ✓/✗ per check, verdict) is
the macro `_sprint_qa.html`: tapping it opens each check's reason (a `<details>`, so it works
on a phone; the old `title` tooltip was hover-only). `sprints/revision.py` approves or
rejects (a rejected piece leaves `estado_videos.json`), closes and reopens the
sprint; `sprints/entrega.py` lists approved links and builds the zip
(`sprint_empaquetar`). Retries and regenerations always go through the cost
gate and `max_intentos=1`. Entrega 2 of the board (2026-09-27; it replaced a smaller Armar/Ideas-only version,
c91b6fc, that another session had shipped an hour earlier; spec
`docs/superpowers/specs/2026-09-27-sprints-tablero-entrega2-design.md`): the panel has three
tabs — Armar · Ideas · Piezas (`_sprint_panel_armar.html`, `_sprint_panel_ideas.html`,
`_sprint_panel_piezas.html`, all rendered in one fragment and toggled client-side;
`?panel=<cid>&paso=armar|ideas|piezas`, default from `sprints.tablero.paso_por_defecto`, counters
from `tablero.pestanas`). Armar describes references inline and shows the product's sofisticación;
the persona consciencia selector is gone from the panel (the campaign's consciencia wins,
`fijos_de`). Ideas (angle editor, «Otra idea», «Reescribir», «Aprobar todas») and the «Generar»
cost gate live in the Ideas tab — `campana_ideas` now only redirects there and
`campana_ideas.html` is deleted. The Piezas tab (`sprints.campana_piezas`, re-fetched every 8 s
while something is alive and never while a rejection reason is being typed) reviews, rejects with
an inline reason, retries and regenerates with the price shown and a confirm, and approves what
passed QA for THAT campaign only (`revision.aprobar_pasaron_qa(..., campana_id=)`); the
sprint-wide review page stays for bulk review, filters by campaign («n · ETAPA · persona ·
producto») and links each piece to its panel. «Proponer ideas» shows
`gastos.estimar("proponer_ideas", n=)` and registers its real spend (tipo `ideas`, counted with
`analisis._llamar_contando`, also when the answer was unusable, `max_intentos=1`). The routes the
panel calls answer JSON when asked (`_quiere_json`); plain form posts still redirect (to the panel's tab when `volver=panel`). `base.html`'s unsaved-changes guard marks on `input`, and on `change` only `<select>`s.
`static/angulo.js` clears `data-sucio` on its own fields only after a save that covered the
latest edit. It also makes anything that reads the angle on the server wait for its pending
save (`guardarAngulosPendientes`: «Reescribir», «Aprobar», any form submit — re-sent with `requestSubmit`,
so its `confirm()` asks once); a reload of the SAME campaign's panel keeps what was being typed, which
`<details>` were open and the cursor (`tomarEscrito`/`devolverEscrito`). The Blueprint refuses POSTs the
browser marks as cross-site (`Sec-Fetch-Site`), like Flow Plus and the editor.

Director de Crear en lotes (2026-10-02, PND-014): también se encola con max_intentos=1 y registra el usage real bajo _creatv; sigue siendo una ayuda gratis para la persona.

PND-003 (revisión 2026-10-02): el estimado del lote usa gastos.estimar con musica_al_crear como musica_estilo, igual que la sesión generada.

PND-034 (2026-10-03): si se interrumpe el director de un lote con auto_lanzar aprobado, el fallback continúa por flowplus_lanzar con su prioridad original; una pieza que ya avanzó no se relanza. Se prueba con cola simulada, sin proveedores.

PND-127 (2026-10-05): _costo_regenerar pasa el musica_estilo de la sesión a gastos.estimar("video"); música generada suma su tarifa, Mi música no. La estimación comparte cálculo con la generación.

**Constantes compartidas (2026-10-07, PND-077/079):** `plataformas.PLATAFORMAS_VERTICALES` es la misma constante
inmutable en dashboard, producción de Sprints y tarea de Crear. `sprints.estado.LISTAS_PARA_REVISION` contiene listo y
degradada; `TERMINADAS` incluye además error para cerrar generación. `sprints.revision.TERMINADAS` conserva el alias
de revisables: error sigue sin poder aprobarse. `tests/test_lote5_higiene.py` vigila identidad y comportamiento.

PND-072/088/090 (2026-10-07, lote 5 B): el director usa el encolador común; perder la reserva archiva la sesión nueva, sin borrar estado ajeno. Los candidatos de IA se leen con referentes.datos.por_ids una vez en panel y página. datos._consumir_sugerencia toma el bloqueo de campaña antes de leer extra y elimina solo el referente agregado, conservando el resto; también limpia una sugerencia ya agregada. La política de QA fue delegada el 2026-10-08 (ver abajo); la instantánea de contexto no se toca en este lote.


PND-088 (2026-10-08, decisión delegada): Repetir QA no borra ni encola un veredicto pasa o una revisión aprobada. limpiar_qa_no_aprobada usa un UPDATE condicional por cliente/cp_id/cf_id para cubrir un resultado que llegó después de leer; el worker vuelve a comprobar el veredicto antes de llamar a Claude. R2 (2026-10-08): una pieza aprobada sin QA recibe su primer QA y deja de ser candidata de la periódica; una aprobada con cualquier QA o un veredicto pasa no se vuelve a evaluar. Las fallidas siguen el camino existente. No cambia el contexto por idea, ni los topes/prompts del QA. test_rutas_sprints.py y test_tareas_sprints.py.
