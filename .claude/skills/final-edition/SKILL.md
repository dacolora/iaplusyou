---
name: final-edition
description: "Final edition: convertir un video aprobado de Crear en finales localizados por idioma y país (guion base, voz, música, mezcla, borrador por receta, decisión B de idiomas). Cargar antes de tocar final_edition/__init__.py, produccion.py, borrador.py, insumos.py, mezcla.py, tareas/final_edition.py, las rutas fe_* o _tab_final.html."
---

# Final edition: guion, voz, música y finales por país

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Final edition** (`final_edition/`): a second pipeline that takes an already-approved
CreativeFlowPlus video (`creative_flow.py`) and turns it into a localized, narrated,
subtitled, scored final ad per idioma/país (`fe_preparar` writes one guion base with
Anthropic; `fe_producir` queues one `final_producir` task per destino ticked, each
worth its own approval) — the base guion is written in the language picked in «Idioma base», which defaults to the
project's language (`idiomas.de_proyecto`), and each destino localizes it to its country's language (decisión B,
2026-09-28). `final_edition/__init__.py::producir` (the worker task `final_producir`, one per destino,
`max_intentos=1`) now runs through the editor (capa 2, 2026-09): `final_edition/produccion.py`
turns the guion into an **edición** (a capa-1 document built by `final_edition/borrador.py`
from materials cached by hash in `final_edition/insumos.py`: the raw clon, the voice per
block — TTS + `atempo` fit as a derived material, Whisper words in `material.extra.palabras` —,
the music track and the logo), translates the destino into it (`variables.textos/voz` and
`por_destino` keyed `<idioma>_<PAIS>` with `<idioma>` as fallback; the price is the reserved
text variable `precio`, formatted per country or absent), freezes a version and renders it with
`tareas.edicion.renderizar_final` (the same code path as `edicion_producir`). One edición per
"receta" (`borrador.receta`: guion base + variante + voz + música + sonido + mezcla + formato):
a second destino only pays its localization and voice; a changed guion or voice makes a new
edición; degraded borradores are never reused (a new one is built, paying only the missing
pieces). `capas`, `pieza.guion`, `final_id`s, the 5 `ETAPAS_FINAL` and the spend row
`final:<id>:t<tarea>` keep their old shape, so the finals UI (then in Crear's modal, now the Final
edition tab), derivaciones and experiments did not change. `FINAL_EDITION_LEGADO=1` switches the
worker back to the old layered pipeline
(`producir_legado`: `guion` -> `cortes` -> sonido -> `voz` -> `musica` -> `texto` -> `render`),
kept only until `render.py`/`texto.py` are retired. Since S2 the clon's native sound is a layer: `producir` reads the RAW clon
(`video_local_crudo`/`video_url_crudo`, never the music-mixed file), `render` trims `[0:a]`
with the very same segment `inicio`/`fin` as the video (sync by construction) and
`final_edition/mezcla.py::filtro_mezcla` mixes sound + voice + music (voice ducks sound at
ratio 4 and music at ratio 8, presets `equilibrada` / `voz_protagonista` /
`ambiente_protagonista`, explicit `volumenes` win, `loudnorm=I=-14:TP=-1.5:LRA=11` last), AAC forced to 48 kHz on output (`-ar 48000`: `loudnorm` emits 192 kHz).
Options `con_sonido`, `sonido` (`nativo|ninguno`), `mezcla`, `volumenes`; `capas.sonido`
is `ok | omitida | ausente` (a mute clon never degrades the piece). Stems and "Remezclar"
are S4, video→audio fallback is S3. State lives on
`creative_flow.crear_final`/`actualizar_final` (`data/creatv.db`), one row per
idioma/país keyed `<cf_id>__<idioma>_<pais>`; re-producing a destino that already has
a final keeps its `url_video`/`url_miniatura` until the new attempt succeeds, so a
failed retry never leaves the client without a video. Every price is per-destino
(`opciones["precios"]`, one raw number per país — never converted between currencies)
so a badge/voice-over price is either the number typed for that specific country or
absent, never another country's number reformatted. All fal.ai calls go through
`providers/fal_audio.py` (ElevenLabs `multilingual-v2` for TTS — MiniMax Speech 2.8 HD
for a project's own voices, see «Audios en Crear» —, `fal-ai/whisper` for
word-level timestamps, Stable Audio for music); the premade voice list there is
individually verified against fal (see the module docstring) rather than assumed from
ElevenLabs' own catalog. Fonts are checked into `static/fonts/`; generated music
tracks are cached in `data/musica/` and mirrored to R2. Worker tasks live in
`tareas/final_edition.py`; the dashboard routes are `fe_preparar`, `fe_guardar_guion`,
`fe_producir`, `fe_descartar`. Since 2026-09-27 its UI is its own tab, **Final edition**
(`_tab_final.html`, `data-tab="final"`, decisión de Daniel); Crear only keeps «Llevar a final edition»
(`#final?cf=<id>` opens that piece, painted or not), and the `fe_*` routes return to `#final`.

**Tablero** (pedido de Daniel, 2026-10-02: «no debe salir nuevamente la misma lista de crear»): the tab
no longer repaints Crear's videos. `final_edition/tablero.py::armar(items, ediciones_por_cf)` (pure, no
queries: the items of `_creative_flow_items` + `_ediciones_por_cf`) splits them into two columns.
**En edición** (`#fe-editando`) = one card per started video (guion written or being written, a person's
edición or the editor preparing, finals producing / in error / interrupted); a video leaves it once it has
a ready final and nothing live or failed, and comes back when a person's edición is saved after its last
ready final (the automatic borrador, `creada_por="final_edition"`, is re-saved on every production and
does not count; that is why `_final_a_dict` carries `actualizado_en`). **Finalizados** (`#fe-finalizados`)
= one card per final `listo` or `degradada`; failed finals are seen inside their video. Order: cards with a live job first (their bar must be among the 24 painted), then
the last movement. The ready videos only appear in the **«+ Nueva final edition»** selector (`#fe-elegir`
dialog), fetched the first time it opens (`final_tarjetas?lista=elegir`, cards without progress bars so a
`trabajo-<job>` id never repeats); picking one goes STRAIGHT TO THE EDITOR (Daniel, 2026-10-02: «de una lo
debería mandar al dashboard de edición»), the same way «Editar» in the detail does: its edición if it has one
(`data-editor-url`, `_eds[0]`), otherwise a free POST to `editor.desde_clon` (`data-desde-clon`; it comes back with
`#final?cf=<id>&abrir=editor` and enters the editor by itself when the job ends), or waits for the one already being
prepared (`data-preparando`). While it is being prepared, `desdeHash` highlights its En edición card
(`.fe-resaltada`) instead of opening the detail on top. The guion with AI and «Producir finales» are reached by
clicking the card in En edición. `fe_cifras` feeds
the header (en edición, produciéndose, finalizados, países, what the READY finals cost — which number to
show is Daniel's call, PND-111). Every live job of a video keeps its `data-poll-job` bar on its En edición
card (one visible, the rest hidden, each with its own `.progreso-texto`), so the page still reloads by
itself when a guion, the editor or a final finishes. A final has two possible live jobs:
`dashboard._job_final_vivo` checks the automatic one (`tareas_fe.job_id_final`) and the editor's «Producir»
(`tareas_edicion.job_id_producir`, one per edición); without the second an editor-produced final looked
interrupted («con error», no bar) while it was being produced.
Look: the section re-skins itself (navy + electric blue, see the `ui` skill).

**Gasto real del guion (2026-10-02, PND-001):** `final_edition/guion.py::_llamar` devuelve `(texto, usd)` con el costo sacado del `usage` de Anthropic (caché contada como en `guiones.claude.tokens_entrada_equivalentes`, precios de `nicho.avatares.costo_real`); antes era un US$ 0,01 fijo y el gasto quedaba en un cuarto de lo cobrado. `GuionInvalido.costo_usd` lleva lo que cobraron las llamadas que no sirvieron: `preparar_guion` lo anota antes de relanzar (detalle «guion base … · no salió válido»), `produccion.traducir` lo suma a `costo_pagado` y una variante inválida en `produccion.producir` lo anota en el gasto de la final (`registrar_gasto_final(..., fallo=True)`).
Revisión del mismo día (guardián del gasto + revisor): la tarea `final_guion` va con `max_intentos=1` (un reintento pagaba otra vez y pisaba el gasto con la misma referencia `guion:<cf>:t<tarea>`); una excepción de la API después de una llamada pagada también lleva `costo_usd`, y `preparar_guion` anota cualquier fallo posterior a la transcripción («· se cortó después de cobrar»); en `traducir` la capa `guion` registra lo cobrado con `estado="error"` (el gasto ya no dice «nada cobrado»); el camino legado anota la variante y la localización que no sirvieron. Las tarifas de `gastos.TARIFAS` subieron al peor caso calculado desde los topes: `guion` 0,13 y `final` 0,20 por país (PND-110: calibrarlas con el gasto real).

**Precios y respuestas cortadas (2026-10-02, PND-005/108):** `_precio_form` interpreta grupos de miles (`89.900` → 89900), decimales con punto o coma y rechaza valores no finitos. `_llamar` corta ante `stop_reason=max_tokens` con `GuionInvalido.costo_usd`; no paga una corrección de la respuesta truncada. `MAX_TOKENS` sigue en 4000: falta la medición real de `eval-claude`, registrada en PND-108.

PND-108 (revisión 2026-10-02): si la primera pasada es válida y solo tiene errores extra no bloqueantes, una corrección cortada o fallida devuelve esa primera pasada con el costo acumulado de ambas. El corte de la primera pasada sigue abortando sin pagar corrección.
