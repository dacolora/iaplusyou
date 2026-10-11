# Pestaña «Rendimiento»: las decisiones que tomó el coordinador (2026-10-09/10)

Daniel pidió «vamos con las 3 entregas, no te detengas por nada, crea subagentes y mergea a main cuando tengamos todo».
Estas son, en el orden en que se tomaron, las decisiones que se tomaron en su nombre durante la ejecución con subagentes,
cada una con lo que cuesta si está mal. Spec: `docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md`
(§9 enmiendas A1–A7); planes en `docs/superpowers/plans/2026-10-09-pestana-rendimiento-e1.md` y
`docs/superpowers/plans/2026-10-10-pestana-rendimiento-e2.md`; medición E0 en
`docs/superpowers/evals/2026-10-09-atribucion-happyflops.md`. Las que esperan a Daniel están en `docs/pendientes.md`
(PND-286 ex-224, PND-289 a PND-295).

Nota: los registros de trabajo están en inglés (es la lengua de los subagentes); se copian tal cual.

## E1 (la pestaña única) y su revisión final

- Ruling: endpoint functions in pestana_rendimiento/rutas.py are named ver_panel, ver_conjuntos, ver_anuncios_meta, actualizar — T7 references them by these names — cost if wrong: a rename in T7.
- Ruling: implementers run sequentially (skill rule), not in parallel — slower wall clock — none.
- Ruling: Task 2 implementer runs while Task 1 is under review (files disjoint except the catalog; any Task 1 fix round waits until Task 2 reports) — saves wall clock — cost if wrong: one catalog merge by hand.
- Ruling: fix the plan-mandated Meta wording to «%(ventas)s en ventas según Meta y %(compras)s» with a new ngettext «compra/compras» helper — the spec wants one vocabulary per source and cards already say Ventas/Compras — cost if wrong: two msgids reworded.
- Ruling: the plan's test expectation `"cubiertas_tw": []` for a single TW entry is a plan defect — spec R3/R4 and the brief's own code/docstring want the entry's accounts — restore the unconditional extend, fix the test to ["act_no"], add R4 + alone-vs-Todas parity assertions — cost if wrong: none (spec is explicit).
- Ruling: accept Task 5 concern 1 (inicio_datos = latest first day) — with dias>0 `desde` would suppress valid comparisons; equal to desde when dias==0 — cost if wrong: comparisons shown for a period where one source lacks the previous days (armar already refuses previous periods before inicio_datos).
- Ruling: for TW-only «Todas» with 2+ stores, Task 7 shows the unified «Por país» (replacing TW's «Por tienda») and keeps TW's own Resultados (spec §5.3 «Por país» for «Todas» with 2+ entries) — cost if wrong: one section swap.
- Ruling: fin_datos for mixed scopes = min over sources with data of min(last row date, date of that source's last copy) — a lagging sync is not zero sales (same protection as the TW panel); Meta accounts without delivery have no rows, so the copy timestamp, not the last row alone, bounds coverage — cost if wrong: the last day(s) hidden as «sin copia» a bit too eagerly.
- Ruling: accept Task 5 fix deviation — per-source end = max(last row, copy date) for Meta accounts and sparse TW ad rows, last row for store totals — my min() formula would flag a healthy paused account as lagging, contradicting the ruling's own reason — cost if wrong: a stuck sync whose copy date still advances would hide its gap.
- Ruling: accept concern 1 — a campaign absent from TW's copy keeps Meta's numbers labelled «Meta» (a zero TW never measured would be invented) — cost if wrong: a row labelled by source instead of zero.
- Ruling: concern 2 — rows with origen "tw" take gasto as well as pedidos/ingresos from totales_por_grupo, so their ROAS uses one source over one window (A2: each block uses its own copy's «Desde el inicio») — cost if wrong: TW-row spend under «Desde el inicio» covers TW's window, not Meta's 13 months.
- Ruling: origen "tw" rows take gasto, ingresos/valor, pedidos/compras from totales_por_grupo AND carry moneda = TW project currency; the budget keeps the account currency in a new key moneda_presupuesto, and _meta_macros.presupuesto uses `f.moneda_presupuesto or f.moneda` — one source and one currency per amount — cost if wrong: TW rows show spend in USD next to a SEK budget (labelled).
- Ruling: include review Minor 4 in the fix (`_resolver` must not carry the Meta token in its return) — token-handling hygiene per seguridad skill — cost if wrong: none.
- Ruling: accept Task 7's spec-over-brief order (IA before campaigns, separate macro) — spec §5 is binding — cost if wrong: none.
- Ruling: accept no 01–09 numerals on screen (sections are conditional, numbers would skip) — cost if wrong: cosmetic.
- Ruling: Task 8 fix round also (a) makes base_temporal remove its folder at teardown (cause of the disk incident) — cost if wrong: none; (b) a NON-EMPTY entrada that doesn't resolve in POST /rendimiento/actualizar flashes and enqueues nothing (only empty = «Todas») — protects Meta's per-user+app usage limit that launches need — cost if wrong: a stale tab's click does nothing but says why; (c) Minor 1–4 (pendientes pointers to deleted files, stale comments in _tw_secciones/_meta_secciones, 'tw-panel' loop in tw_resultados.js, link-scan test covering static/*.js and nested .py and quoted forms).
- Ruling: new analyses saved from now on carry foto["metodo"] = 2 (R9 method); panel.es_viejo ignores a verdict change for an analysis whose foto lacks metodo>=2 (only spend ≥ FACTOR_VIEJO counts) — deploy-date independent, no data migration — cost if wrong: a pre-R9 analysis whose verdict truly changed for other reasons is shown as current until its spend grows 1.5×.
- Ruling: add a test pinning that datos.totales_anuncio (decisor) keeps counting pixel rows regardless of R9.
- Ruling (A7, amends R7 for an edge): with ONLY Triple Whale stores in «Todas», keep Triple Whale's own «Desde el inicio» (each store since its first day, as the old tab) for Resultados AND make «Por país» use that same start (no inicio_comun); R7's common start applies only when the scope mixes sources — keeps the paid gallery's scope identical to what triple_whale routes recompute (an `inicio` override would make cards and paid requests disagree) — cost if wrong: TW-only «Todas» totals mix store periods (happyflops has one store today).
- Ruling: Por país leads with the scope's common currency when all entries share it (USD otherwise) and shows «USD no disponible» when any row lacks USD.
- Ruling: one progress bar for the scope's copies (the first live job) with «Trayendo N copias…», not one per store/account (each finishing job reloads the page).
- Ruling: alerts from the two sources are concatenated, not de-duplicated by text (count-bearing texts would hide one).
- Ruling: datos.canales() lists only channels with spend (aligned with R9).

## E2 (Meta a la par), integración con main y revisión final

- Ruling: E2 Task 1 starts while E1 final reviews run (low file overlap: E2-T1 touches mejorar/analisis/tareas TW + new meta_rendimiento/creativo.py) — cost if wrong: a merge of a final-review fix into those files.
- Ruling: E2 plan tasks 2–7 are prose-level (interfaces + rules, less literal code than E1); implementers are opus — cost if wrong: more review rounds.
- Ruling: accept copy cap 3000 (matches tw_creativo; prompt never trims own copy) — cost if wrong: very long copies cut.
- Ruling: accept the extra 600px thumbnail read (64px default useless to Claude; failure falls back) — cost if wrong: one more Graph call per paid analysis.
- Ruling: keep TW account evaluation + top products in a Meta ad's prompt (same brand and catalog; the evaluation is labelled by scope) — cost if wrong: slightly less relevant context for a Meta-only country.
- Ruling: if the fetched creative has no copy, titulo, imagen_url nor video_url, the task raises a worded error BEFORE Whisper/Claude, nothing charged («No pude leer el anuncio en Meta; no se cobró nada. Inténtalo más tarde.») — the person approved the price of an analysis of the ad — cost if wrong: a Meta ad with genuinely no text/media can't be analysed.
- Ruling: accept Task 2's three interface additions (needed to keep behavior identical) — Tasks 4/5 call them this way — cost if wrong: none.
- Ruling: fix round 2's scoped re-review done by controller inspection of the 1-line diff + implementer's green fast suite (no logic change; texto_error maps the type) — cost if wrong: none.
- Ruling: accept config["moneda"] None for mixed/unknown currencies (spec R6: never invent USD) — cost if wrong: a mixed-currency Meta scope's paid prompt shows «—» for currency.
- Ruling: keep scope-level alcance for paid Meta requests (not per-ad account) so mismo_alcance/A1 stay consistent with what the card shows; happyflops is single-currency — cost if wrong: a mixed-currency scope's winners list mixes currencies in the prompt.
- Ruling: run Task 6 before Task 4/5 (independent, pure) to use wall clock while E1's revisor runs — cost if wrong: none.
- Ruling: rule 1 silent below 30 % confirmed (no lower level than media; a below-threshold line is noise) — cost if wrong: a small limited-learning share goes unmentioned.
- Ruling: rule 6 excluding «perdedor» confirmed (losers are covered by the spend-on-losers alert) — cost if wrong: none.
- Ruling: Task 6 fix round (after the E1 fix wave lands) — rule 4 must skip winners whose ad is not active (a paused winner must not trigger «Sube el presupuesto»); move the two constants imported from meta_rendimiento.rutas into a neutral module so the pure module doesn't import a blueprint.
- Ruling: accept verified-email requirement on the unified paid POSTs (seguridad rule for new POSTs) — cost if wrong: a client with an unverified email can't request analyses until verifying.
- Ruling: accept per-source charging order in a mixed lote (balance-limited edge: if the balance runs out midway, a lower-spend ad of the first source may be queued before a higher-spend ad of the other) — cost if wrong: which ads get analysed first when balance is short.
- Ruling: mismo_alcance returns False when the row's foto fuente (default triple_whale) differs from the alcance's fuente (default triple_whale) → the other source's analysis is «otro» (neutral note, secondary button, never in the batch) — cost if wrong: one ad seen from both sources may be paid once per source (each with its own numbers), never repeatedly.
- Ruling: accept deleting triple_whale.rutas.evaluar (no caller; the unified route enforces verified email) — cost if wrong: none.
- Ruling: PND-224 (raw Meta ad text in the evaluation prompt, OWASP LLM01) stays deferred — low severity (own account's text; output only fills escaped cards and a Crear prefill a person reviews; no tools); the real fix needs delimiters + an «es un dato» instruction measured with eval-claude (real Claude calls), outside E2's «only the source name» constraint — cost if wrong: a malicious ad copy in the client's own account could steer the evaluation text. Note: E2 widens exposure (metrics-only projects now reach this prompt). Flag for Daniel.
- Ruling INT-1..8 (see integracion-main.md): live features must stay reachable in Rendimiento; one implementation per feature with main's (live) winning — our E2 Task 6 recomendaciones and E2 Task 5's Meta evaluation branch are retired in favor of main's; our E1, per-ad Meta «Cómo mejorarlo», unified gallery and day detail stay; catalog/submodule/PND renumbering per repo rules — cost if wrong: rework of the dropped duplicates (they're in git history).
- Ruling: accept Meta AI evaluation limited to Meta-source accounts of the scope (one number per country, spec principle) — cost if wrong: Daniel loses evaluating TW-country ads on Meta numbers (reversible: offer it on TW entries).
- Ruling: accept main's Diagnóstico over all Meta accounts in scope (mostly structure rules: learning, rejected, budgets, segments) — cost if wrong: a sales-based diagnosis line for a TW country quotes Meta's Pixel.
- Ruling (money): hide «Probar los 3 ganchos» for analyses with foto.fuente == "meta" until a real test (PND-289) — cost if wrong: Meta ads lose that paid option for now.
- Ruling: final fix wave makes Meta disconnection (dashboard._soltar_cuentas_meta) and removing accounts (meta_rendimiento.cuentas.elegir removal path) delete tw_analisis rows with foto.fuente=="meta" whose foto.ad_account_id is among the released accounts, then their R2 keys (creativo.clave_r2) — rows first, R2 after (E2-R2 order), with a warning if R2 fails; never delete TW-source analyses — cost if wrong: none (it's the public promise).
- Ruling: also in the wave — ganchos_probar requires verified email (paid POST); PIL Image.open with formats=("JPEG","PNG","WEBP","GIF") in creativo.py.
- Ruling: ganchos refused server-side for foto.fuente=="meta" (puede_probar returns a motivo; button not painted; POST → 409), PND-289 to enable after a real test.
- Ruling: Meta-card price uses the latest analysis' foto.creativo.duracion_s when known (else 30 s) — same function for card, batch total and charge.
- Ruling: TW «Evaluar con IA» adopts main's E2-R6 guard (form sends n and precio_visto; route refuses without charging when they differ and shows the current price).
- Ruling (reverses my Task 1 ruling): a Meta-source ad's «Cómo mejorarlo» prompt gets NO Triple Whale account evaluation (spec: never mix the two Pixels in one prompt); top products stay (catalog-level) — cost if wrong: slightly less context.
- Ruling: add a PND for «Meta evaluation no longer offered for TW-covered accounts (production allowed it)» — product decision for Daniel.
- Ruling (B3/S2): paid unified routes and ganchos_probar keep production's behavior (no verified-email requirement; same-origin yes); verified email stays only on «Actualizar ahora»; PND to require it once SMTP works — cost if wrong: an unverified client user can trigger paid analyses as in production today.
- Ruling: B4 and B5 left as they are (Daniel decides; PNDs) — cost if wrong: see PNDs.
