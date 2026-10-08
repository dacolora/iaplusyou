---
name: doctrina
description: "Doctrina de copywriting: las rebanadas de doctrina/textos que reciben las llamadas a Claude, el ángulo (validar, editar, cifras verificables), el revisor de la pieza terminada, el diagnóstico de perdedoras y los aprendizajes por proyecto. Cargar antes de escribir o cambiar una llamada a Claude que escriba o clasifique copy, o tocar doctrina/."
---

# Doctrina de venta y ángulo

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Doctrina de venta y ángulo** (`doctrina/`, spec `docs/superpowers/specs/2026-09-25-doctrina-copywriting-design.md`,
ADR 0004): los principios de seis libros de copywriting (Kennedy, Hopkins, Ogilvy, Great Leads, Schwartz, Theriot)
destilados en nuestras palabras en `doctrina/textos/*.md`, por rebanadas (`base` siempre + `investigar`, `angulo`,
`gancho`, `guion`, `video`, `caption`, `clasificar`, `revisar`); los libros NO están en el repo. Cada llamada a Claude
que escribe o clasifica copy recibe su rebanada con `doctrina.bloque_system(*rebanadas, extra=<instrucciones del
sitio>)` (bloque con `cache_control`): ideas de sprint (`angulo`+`gancho`+`video`), director (`video`), guion
(`guion`+`gancho`, o además `angulo` si la sesión no tiene), localizar (base), variar (`gancho`), captions
(`caption`), «Adaptar con IA» (`angulo`+`gancho`), clasificar/sugerir referentes y analizar referencias
(`clasificar`), avatares y personas sugeridas (`investigar`). El **ángulo** (audiencia, consciencia, sofisticación
1–5, deseo, promesa única, mecanismo, pruebas con fuente `ficha|comentarios|demostracion`, arranque/`lead`, gancho,
faltantes) lo decide Claude antes de escribir y `doctrina.validar_angulo` lo limpia (nunca lanza; una corrección —
en el guion, la misma ronda del guion con errores no bloqueantes—; si la corrección falla por lo que sea, se guarda la
primera respuesta con `faltantes` «error: …» vía `doctrina.anotar_errores`, que los pone primero para que ninguno se
corte antes que un faltante de Claude: nunca se pierde lo pagado). Vive en `campana_pieza.extra.angulo`
(ideas) → `concepto.extra.angulo` (sesión; `duplicar` lo copia; «Adaptar» y el guion lo crean solo si la sesión no
tiene, y el guion solo si trae promesa y gancho) → director, guion, captions; las variantes guardan
`capas.guion.parametros.angulo` (`lead` y `gancho` nuevos). `doctrina.verificar_cifras`: ninguna cifra fuerte (2+
dígitos, %, moneda, «3x», «N de cada M») que no esté en los datos que Claude recibió; del ángulo solo cuenta como dato
`doctrina.texto_verificable` (las pruebas, y el resto solo si ningún `faltantes` es un «error: …»; nunca
`faltantes`). En el guion base y las variantes es bloqueante (va a la corrección y, si persiste, `GuionInvalido`);
localizar no verifica cifras (convierte unidades y precio y el base ya se verificó); en ideas y «Adaptar» queda en
`faltantes`. Sin precio escrito, el precio de la tienda solo entra al guion como `precio_base` si su moneda es la del
país base; si no, el guion no recibe precio. Vocabulario único:
`doctrina.CONSCIENCIAS` (el de Nicho; `normalizar_consciencia` traduce el inglés de referentes y
`referentes.sugerir.NIVEL_A_CONSCIENCIA` se deriva de ahí), `LEADS`, `SOFISTICACIONES`. Nada de esto agrega pantallas
ni migraciones (bloque 1 de 4; los bloques 2–4 vienen en sus propios párrafos). Los topes de salida de estos sitios son
amplios (4 000–16 000 tokens): el pensamiento adaptativo de `claude-sonnet-5` los consume y con topes chicos la
respuesta llega vacía (prueba real del 2026-09-26).

**Doctrina, bloque 2: el ángulo a la vista** (spec `docs/superpowers/specs/2026-09-26-doctrina-bloque-2-angulo-visible-design.md`):
el ángulo se ve y se edita entero en la tarjeta de cada idea del sprint y en cada video de la pestaña Final edition
(antes de «Preparar guion»; se mudó de Crear con la sección de final edition, 2026-09-27): macro `templates/_angulo_editor.html` + `static/angulo.js` (autoguardado JSON; los campos no llevan `name`
para no mezclarse con el autoguardado de la tarjeta), rutas `sprints.idea_angulo` (409 si la idea ya tiene pieza) y
`cf_angulo`; `doctrina.angulo_desde_formulario` valida sin bloquear (`mensaje_error` da frases simples), conserva
`origen`, pone `editado_en` y quita los «error: …»; con `editado_en`, `texto_verificable` cuenta todo el ángulo como
dato (las cifras de la persona se usan tal cual). Un ángulo sin promesa o sin gancho no manda en `preparar_guion`.
«Reescribir la idea con este ángulo» (tarea `sprint_reescribir_idea`, `sprints.ideas.reescribir`, gasto `ideas`) cambia
título, escena y sonido sin tocar el ángulo. Datos del mercado: la consciencia (la de la campaña,
`campana.consciencia` del tablero de Sprints, y si la campaña no tiene, la de la persona:
`persona.extra.conciencia.nivel`, ruta `sprints.persona_conciencia` — desde la entrega 2 del tablero el panel ya no muestra ese selector: manda la consciencia de la campaña;
`sprints.ideas.fijos_de` aplica ese orden) y la sofisticación del producto (`producto.extra.sofisticacion`, selector en Catálogo) mandan cuando existen:
`doctrina.validar_angulo(..., fijos=)` los impone antes de validar y `doctrina.datos_fijos_texto` los pone en los
DATOS de ideas, guion (sin ángulo) y «Adaptar con IA». Pruebas y pedidos del producto viven en
`producto.extra.pruebas|pedidos` (`tiendas.EXTRA_INTERNO` los protege de la sync; único escritor
`doctrina/producto.py` vía `tiendas.modificar_extra_interno`, con lock): las pruebas entran a los DATOS de ideas,
guion, «Adaptar» y captions y cuentan como dato verificado; «Actualizar lo que Claude necesita» (tarea
`producto_pedidos`, `doctrina/pedidos.py`, gasto `pedidos`) junta los faltantes de las ideas y sesiones del producto
y los resume en máximo cinco pedidos; responder uno lo guarda como prueba. Página de solo lectura
`/cliente/<cliente>/doctrina` (`doctrina/pagina.py::a_html` escapa antes de convertir). Las plantillas reciben el
vocabulario con `doctrina.globales_plantilla()`.

**Doctrina, bloque 3: el revisor de la pieza terminada** (spec
`docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md`): `doctrina/revisor.py` contesta la lista de
`textos/revisar.md` (12 puntos; `PUNTOS`/`PUNTO` traen la rebanada del «¿Por qué?») sobre una pieza de Crear terminada.
Dos capas. `reglas(datos)`: pura y gratis, se calcula al renderizar (gancho largo, arranque fuera de la consciencia,
promesa múltiple, sin mecanismo con sofisticación ≥ 3 —la fija del producto manda—, cifras del caption que no están en
los datos verificables de `reunir()`, guion sin CTA, gancho de la idea distinto del ángulo). `revisar(cliente, cf_id)`:
Claude con visión, fotogramas de `tiempos()` (0,3 s, uno cada 3 s y el final; máximo 8) precedidos de «Segundo N:», los
DATOS de `reunir()` y la rebanada `revisar`; una corrección; `ErrorRevision` lleva los tokens pagados. Se guarda en
`concepto.extra.revision_doctrina` con el `video_url` revisado (`estado_revision` la marca «vieja» si el video cambió;
`duplicar` no la copia). Botón «Revisar con la doctrina» en el detalle de Crear (`cf_revisar` → tarea `pieza_revisar`,
`max_intentos=1`, gasto tipo `revision`, tarifa `revision_pieza`), macro `templates/_revision_doctrina.html`, barra de
progreso en la tarjeta. El QA de Sprints (`sprints/qa.py`) pide los 12 puntos en la misma llamada (rebanada `revisar`
en el system, mismos fotogramas, tope 6 000), por fin registra su gasto real (tipo `revision`, referencia
`qa:<cp_id>:t<tarea>:i<intento>`) y guarda la revisión en la sesión (`origen: sprint`). La galería de Experimentos
(`elegibles()["doctrina"]`, aviso en el paso 3) y la revisión del lote muestran la etiqueta con `resumen_galeria`,
leyendo solo `concepto.extra`. Nada de esto bloquea ni reescribe.

**Doctrina, bloque 4: cerrar el ciclo** (spec
`docs/superpowers/specs/2026-09-28-doctrina-bloque-4-cerrar-el-ciclo-design.md`): lo que el motor aprende de cada prueba
vuelve a la siguiente pieza. (1) **Diagnóstico de una perdedora** (`doctrina/diagnostico.py`; rebanada `diagnosticar` =
la lista de Theriot: `CAUSAS_PERDIDA` (ocho causas, `CAUSAS_NOMBRE` con `N_`), `CAUSAS_NO_CREATIVAS` = landing,
estacionalidad, posicionamiento, `SIGUIENTES_PASOS`/`SIGUIENTES_NOMBRE`): `exp_decidir` pide la pausa primero (el anuncio deja de gastar
aunque Claude tarde) y después diagnostica cada `perdedor` nuevo en `_diagnosticar` (timeout 120 s, un reintento;
una final variada se diagnostica con SU guion) — `pistas()` (puras y gratis: ThruPlay bajo el mínimo → gancho; CTR bajo con retención → sin_urgencia;
puerta 2 → landing; frecuencia ≥ 3 → repetición; CPC alto con CTR normal → subasta_cara) y una llamada a Claude con los
DATOS (veredicto y números, ángulo, revisión de la doctrina, guion base, producto; una corrección; `ErrorDiagnostico`
lleva los tokens pagados; `idioma=` del proyecto). Se guarda en `experimento_pieza.extra.diagnostico`
(`{version, causas, siguiente, aprendizaje, pistas, modelo, usd, en}` o `{error, pistas, en}`), gasto tipo `revision`,
tarifa `diagnostico_pieza`, referencia `diagnostico:<ep_id>:t<tarea>` (también con respuesta inválida), evento
`diagnostico`; nunca frena el veredicto. (2) **El diagnóstico guía el rescate** (`decision_rescate`): `siguiente`
estructura/regenerar → `payload.salto` 2/3 (`derivaciones._planificar_rescatar` toma `max(escalón siguiente, salto)`:
nunca vuelve atrás; `acciones._precio_estimado` cobra el escalón real) y oferta/landing/pausar, o causa principal no
creativa, → `payload.solo_proponer` (`acciones.pedir` deja `propuesta` en todo modo, con el diagnóstico en el motivo).
`derivar` hace todas las re-ediciones de gancho (ya no alterna hook/estructura) con `contexto_variante =
{lead_objetivo (el k-ésimo arranque recomendado que no sea el actual ni uno ya probado por una final de la sesión;
None cuando no queda ninguno: la variante cambia el patrón del gancho), hermana {k, n} cuando se producen varias a
la vez, ganchos_usados (el del ángulo de la sesión + `capas.guion.parametros.angulo.gancho` de cada final)}`; el
rescate suma `diagnostico` (causas + siguiente) y excluye el arranque de la pieza que perdió. Los aprendizajes NO se
guardan en el experimento: `_opciones_de(item, cliente)` los agrega al encolar. `variar_guion(..., angulo=,
contexto=)` lo escribe en el mensaje (`_contexto_variante_texto`, ganchos y aprendizajes entre etiquetas) — también
en `final_edition/produccion.py`, que antes variaba sin ángulo y que ahora guarda el `angulo_variante` en
`capas.guion.parametros.angulo` como el legado (también para los destinos que reutilizan el borrador). (3) **Aprendizajes por proyecto** (`doctrina/aprendizajes.py`;
`proyecto.json["aprendizajes"]` vía `proyectos.aprendizajes/agregar_aprendizaje/quitar_aprendizaje`, tope 40, los más
nuevos primero): una línea por ganador o perdedor (`desde_veredicto`: «Ganó en CO: «gancho» (arranque X, audiencia Y)
para P — CTR 2,1 %, ThruPlay 34 %.» / «Perdió en …: … — motivo. Diagnóstico: …»; gettext, así que sale en el idioma
del proyecto) o escrita a mano (sección «Aprendizajes del proyecto» al final de Experimentos, `_aprendizajes.html`,
rutas `apr_agregar`/`apr_quitar`). `texto_para_prompt(lista, producto=)` (los del mismo producto primero, 10, entre `<aprendizajes>`) entra
como DATOS en las ideas de sprint (`contexto_campana["aprendizajes"]`; las cifras del ángulo se verifican contra
los DATOS SIN aprendizajes), en el guion base (`generar_guion_base(aprendizajes=)`) y en las variantes. La línea
del motor cabe en 650 caracteres con la frase del diagnóstico entera (`MAX_TEXTO_MOTOR`); a mano, 300. Toda línea pasa
por `_limpio`, que quita TODO `<` y `>` (2026-10-08, revisión final de las tarjetas de Triple Whale: el nombre ajeno de
un anuncio cerraba el bloque con `</APRENDIZAJES>`); una comparación entre números del decisor queda en ＜ ＞ («ThruPlay
8% ＜ 25%»). (4) UI: bajo un veredicto `perdedor` la fila de la pieza
muestra las causas (`CAUSAS_NOMBRE|traducir`, `title` = detalle y evidencia), «Siguiente: …» y «¿Por qué?» →
`#diagnosticar` de la página de la doctrina; con error, el motivo. (5) Flow Plus: `guiones/clips.py`, `recorte.py`,
`imagenes.py` y `refinador.py` arman su system con `doctrina.bloque_system(*COMBINACIONES["flowplus_*"], extra=,
idioma=)` (clips y refinador `video`+`gancho`, recorte `gancho`, imágenes solo la base; la lectura no lleva doctrina) y
`guiones.claude.tokens_entrada_equivalentes` suma la caché al gasto (1,25× escribir, 0,1× leer) en `llamar` y en la
llamada directa del refinador. Límites: un diagnóstico por veredicto; nada se aplica solo salvo lo que el modo ya
ejecutaba; sin migraciones (todo vive en `extra` y en `proyecto.json`). Con esto los cuatro bloques del spec original
(§14) están en `main`.
