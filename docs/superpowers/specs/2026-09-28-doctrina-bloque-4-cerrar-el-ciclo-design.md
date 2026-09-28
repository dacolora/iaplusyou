# Doctrina, bloque 4: cerrar el ciclo (y la doctrina en Flow Plus)

Fecha: 2026-09-28. Daniel: «Vamos a darle Todo y cerramos el chat» (tras «no me preguntes más nada, ejecuta todo»);
las decisiones de diseño de este bloque son rulings anotados, no preguntas.
Antecedentes: spec del bloque 1 (§14.4 «Cerrar el ciclo»), bloques 2 y 3 (ángulo visible, revisor), Theriot cap. 9–15
(notas de lectura), Hopkins («prueba, no adivines»), Great Leads (una sola idea).

## 1. Qué se construye

Cuatro cosas, todas sobre el motor de Experimentos que ya existe (decisor → acciones → derivaciones):

1. **Diagnóstico de una perdedora**: cuando el decisor marca una pieza `perdedor`, el motor explica por qué con la
   lista de Theriot (cap. 14) y propone el siguiente paso; el rescate lo usa.
2. **Derivar varía el gancho, no el mensaje**: las re-ediciones de una ganadora son todas de gancho, cada una con un
   arranque distinto y sin repetir los ganchos ya usados; el rescate salta de escalón cuando el diagnóstico dice que el
   gancho no es el problema, y se frena (propuesta) cuando el problema no es el creativo.
3. **Aprendizajes por proyecto**: cada veredicto deja una línea de aprendizaje; las ideas, el guion base y las variantes
   la reciben («lo que ya se probó en este proyecto»); se ven y se editan en Experimentos.
4. **La doctrina en Flow Plus**: los pasos de `guiones/` que escriben copy o planean el video reciben su rebanada.

Nada de esto lanza, publica ni gasta por su cuenta más de lo que ya gastaba el motor: el diagnóstico cuesta centavos
de Claude y se registra; el rescate y la derivación siguen pasando por `acciones.pedir` (modo + tope).

## 2. La rebanada `diagnosticar`

`doctrina/textos/diagnosticar.md` (≤ 600 palabras, nombra a Theriot y a Hopkins): la lista de Theriot de por qué un
anuncio pierde — `sin_urgencia`, `muy_educativo`, `estacionalidad`, `repeticion`, `landing`, `posicionamiento` — más
`gancho` (no retiene: el arranque o el gancho fallan) y `creativo` (lo visual no da creencia), la regla de iteración
(3 intentos de iteración, 3–6 de variación, luego concepto nuevo; nuevos ganchos alrededor del mismo mensaje) y la
regla de Hopkins (una pérdida es un dato: se anota la hipótesis y lo que se cambia). `REBANADAS` gana `diagnosticar`,
`PRESUPUESTO["diagnosticar"] = 600`, `COMBINACIONES["diagnosticar"] = ("diagnosticar",)`, `pagina.TITULOS` la titula
«Cuando pierde».

`doctrina.CAUSAS_PERDIDA`: tupla de `(codigo, nombre)` con las ocho causas; `CAUSAS_NO_CREATIVAS = ("landing",
"estacionalidad", "posicionamiento")` (un rescate del creativo no las arregla).

## 3. Diagnóstico (`doctrina/diagnostico.py`)

- **Pistas por métricas** (`pistas(snapshots, reglas, contexto) -> [{"codigo", "texto"}]`, pura, gratis), con el
  último snapshot y las reglas efectivas del decisor:
  - `gancho`: video, `thruplay_rate < thruplay_min` → «no retiene».
  - `sin_urgencia`: ThruPlay bien (o imagen) y `ctr < ctr_min` → miran pero no clican.
  - `landing`: pasó tráfico y no ventas (puerta 2 del veredicto) → la landing no continúa el pensamiento del anuncio.
  - `repeticion`: `frecuencia ≥ 3` → la misma gente ya lo vio.
  - `subasta_cara`: CTR bien y `cpc > cpc_max` → la impresión sale cara (audiencia/competencia, no el creativo).
  Sin evidencia de ninguna, `[]`.
- **Diagnóstico con Claude** (`diagnosticar(cliente, ex, pz, snapshots, reglas) -> (diagnostico, ent, sal)`): una
  llamada (`sprints.analisis._llamar_contando`, tope 4000, `system = doctrina.bloque_system("diagnosticar")`) con
  los DATOS delimitados: el veredicto del decisor (motivo y números), las pistas, el ángulo de la pieza, la revisión
  de la doctrina si existe (bloque 3: puntos «mejorar»), el guion (voz por bloque) si existe, el producto, el país,
  los días corridos y las causas posibles. Respuesta JSON `{"causas": [{"codigo": <de CAUSAS_PERDIDA>, "detalle":
  "...", "evidencia": "..."}], "siguiente": {"que": "gancho|estructura|regenerar|oferta|landing|pausar", "porque":
  "...", "hipotesis": "..."}, "aprendizaje": "una frase"}`; `parsear` exige al menos una causa con código válido y
  un `siguiente.que` válido; una corrección si no sirve; `ErrorDiagnostico` lleva los tokens pagados.
- **Guardado**: `experimento_pieza.extra.diagnostico = {version: 1, causas, siguiente, aprendizaje, pistas,
  modelo, usd, en}` (vía `experimentos.marcar_pieza`, con lock); si falla, `extra.diagnostico = {"error", "pistas",
  "en"}`. Gasto tipo `revision`, tarifa `diagnostico_pieza` (inicial US$ 0,03; se mide en la prueba real),
  referencia `diagnostico:<ep_id>:t<tarea_id>`, también cuando la respuesta no sirvió.
- **Cuándo corre** (ruling, corregido en la ejecución): dentro de `exp_decidir`, automáticamente, para cada pieza
  nueva en `perdedor` (video o imagen), DESPUÉS de pedir la pausa (el anuncio deja de gastar aunque Claude tarde o el
  worker muera en el medio) y antes del rescate, al que informa; una vez por veredicto; la llamada corre con timeout
  de 120 s y un reintento. Una «inconclusa» que solo se pausa no se diagnostica. Justificación: el decisor ya corre solo
  («sin mi pc prendido»), el rescate que propone gasta mucho más que el diagnóstico, y la propuesta necesita el texto.
  Un fallo del diagnóstico nunca frena el veredicto ni la pausa: queda el evento y se sigue.
- `experimentos._piezas` expone además `angulo` (el de la sesión, con `lead`/`gancho` de la variante si la pieza es
  una final variada: `pieza.capas.guion.parametros.angulo`), `revision_doctrina` y `productos_ids` (todo de columnas
  que ya están en la consulta).

## 4. El rescate y la derivación usan el diagnóstico

- `tareas/experimentos._aplicar_veredicto`, rama `rescatar` (video): el motivo del rescate es `motivo del decisor +
  " · Diagnóstico: <causas> — siguiente: <porque>"`. Según `siguiente.que`:
  - `gancho` → rescate normal (escalón siguiente).
  - `estructura` → `payload["salto"] = 2`; `regenerar` → `payload["salto"] = 3` (solo hacia adelante:
    `_planificar_rescatar` toma `max(escalón siguiente, salto)`; `_precio_estimado` lo respeta).
  - `oferta`, `landing`, `pausar` (o causa principal en `CAUSAS_NO_CREATIVAS`) → `payload["solo_proponer"] = True`:
    `acciones.pedir` deja siempre una propuesta (también en modo `auto`) con motivo «el diagnóstico apunta a
    <causa>, no al creativo: decide tú si rescatar»; la pausa sí se ejecuta según el modo, como hoy.
- `derivaciones._planificar_derivar`: todas las re-ediciones son `hook` (antes alternaban hook/estructura; Theriot:
  nuevos ganchos alrededor del mismo mensaje). Cada item lleva `contexto_variante = {"lead_objetivo", "hermana",
  "ganchos_usados"}` (corregido en la ejecución): `lead_objetivo` = el k-ésimo arranque recomendado para la
  consciencia del ángulo que no sea el actual ni uno ya probado por una final de la sesión (ni, en el rescate, el de
  la pieza que perdió); NO es cíclico: cuando no queda ninguno es None y la variante cambia el patrón del gancho;
  `hermana = {k, n}` cuando se producen varias a la vez; `ganchos_usados` = el gancho del ángulo + los de las
  variantes ya producidas de la sesión. Los aprendizajes no se guardan en el item (pesan y envejecen):
  `_opciones_de(item, cliente)` los agrega al encolar. `_planificar_rescatar` agrega `diagnostico` (causas +
  siguiente) al contexto. La línea de aprendizaje del motor cabe en 650 caracteres con la frase del diagnóstico
  entera; a mano, 300.
- `_opciones_de(item)` pasa `contexto_variante` en las opciones de `final_producir`; `final_edition.producir`
  (legado) y `final_edition/produccion.producir` (el camino por defecto) llaman
  `variar_guion(guion_base, variante_tipo, marca, angulo=entry["angulo"], contexto=o.get("contexto_variante"))`.
  `_mensaje_variar` agrega: «Usa el arranque «X»» (si `lead_objetivo`), «Ganchos ya usados, no los repitas ni los
  parafrasees: …», «Por qué perdió la versión anterior: … Hipótesis: …» (si `diagnostico`) y los aprendizajes.
  Arreglo de paso: el camino por defecto no le pasaba el ángulo a `variar_guion`.

## 5. Aprendizajes por proyecto (`doctrina/aprendizajes.py`)

- `proyectos.aprendizajes(cliente) -> list`, `proyectos.agregar_aprendizaje(cliente, item)`,
  `proyectos.quitar_aprendizaje(cliente, id)`: lista en `proyecto.json["aprendizajes"]`, máximo `MAX_APRENDIZAJES = 40`
  (los más nuevos primero; escritura atómica de `_json_store`; una carrera web/worker sobre el mismo archivo se
  acepta: son líneas informativas).
- `desde_veredicto(pz, v, diagnostico=None) -> item`: `{"id", "en", "tipo": "ganador|perdedor", "pais", "producto"
  (primer `productos_ids`), "gancho", "lead", "consciencia", "texto", "origen": "motor", "ep_id", "experimento_id"}`.
  El texto es determinista: «Ganó en CO: «<gancho>» (arranque <lead>, audiencia <consciencia>) para <producto> — CTR
  2,1 %, ThruPlay 34 %.» / «Perdió en CO: «<gancho>» (…) — no pasó la puerta de tráfico (ThruPlay 8 %). Diagnóstico:
  <aprendizaje de Claude>.» Se agrega en `_aplicar_veredicto` para `ganador` y `perdedor` (nunca `inconcluso`).
- `texto_para_prompt(lista, producto=None, limite=10) -> str`: bloque «LO QUE YA SE PROBÓ EN ESTE PROYECTO (aprende
  de esto: repite lo que ganó con otro gancho; no repitas lo que perdió)», primero los del mismo producto, los más
  nuevos primero, hasta `limite`; "" sin aprendizajes. Es DATOS (información, no instrucciones): se escapa el cierre.
- Dónde entra: `sprints/ideas.py` (línea nueva `APRENDIZAJES: {aprendizajes}` en `DATOS_IDEAS`, `contexto_campana`
  la carga; por tanto también «Reescribir»), `final_edition/guion.py::_mensaje_generar` (parte nueva; `preparar_guion`
  la pasa) y `_mensaje_variar` (vía `contexto_variante["aprendizajes"]`, que `derivaciones` rellena).
- UI: sección «Aprendizajes del proyecto» al final de la pestaña Experimentos (`_aprendizajes.html`): lista con fecha,
  tipo (etiqueta ganó/perdió), texto y «Quitar»; formulario «Agregar aprendizaje» (texto ≤ 300 caracteres, origen
  `manual`). Rutas `POST /cliente/<c>/aprendizajes` (`apr_agregar`) y `POST /cliente/<c>/aprendizajes/<id>/quitar`
  (`apr_quitar`), vuelven a `#experimentos`.

## 6. Dónde se ve el diagnóstico

En la fila de la pieza en Experimentos, debajo de un veredicto `perdedor`: chips con los nombres de las causas
(`CAUSAS_PERDIDA`), «Siguiente: <que> — <porque>» y «¿Por qué?» a `/cliente/<c>/doctrina#diagnosticar`; con
`extra.diagnostico.error`, «El diagnóstico no se pudo hacer: …». La propuesta de rescate ya muestra su motivo.

## 7. La doctrina en Flow Plus (`guiones/`)

`guiones/claude.llamar` recibe `system` tal cual y lo pasa a la API: acepta la lista de bloques de
`doctrina.bloque_system`. Cada paso recibe su rebanada como prefijo (con caché) y su `SISTEMA` propio como bloque
aparte:

| paso | rebanadas | por qué |
|---|---|---|
| `guiones/clips.py` (armar) | `video`, `gancho` | planea los clips y los hooks alternativos |
| `guiones/recorte.py` | `gancho` | decide qué líneas sobran: conserva promesa y prueba antes que educación |
| `guiones/imagenes.py` | (solo `base`) | prompts de imágenes: solo lo esencial (no inventar, especificidad) |
| `guiones/refinador.py` (chat) | `video`, `gancho` | corrige prompts antes de pagar |
| `guiones/lectura.py` | ninguna | copia literal verificada: la doctrina solo sumaría tokens |

`COMBINACIONES` gana `flowplus_clips`, `flowplus_recorte`, `flowplus_imagenes`, `flowplus_refinador` (el test de
presupuesto las suma). Las pruebas que miraban `system` como texto pasan a mirar el último bloque (`system[-1]["text"]`).

## 8. Errores y límites

- El diagnóstico nunca bloquea: si Claude falla, el veredicto, la pausa y el rescate siguen como hoy (sin salto ni
  freno) y queda el evento «diagnóstico no disponible».
- Solo se diagnostica una vez por veredicto (la bandera es el propio `extra.diagnostico`).
- `salto` solo avanza la escalera; nunca la retrocede ni pasa de 3.
- Los aprendizajes son texto informativo: nunca bloquean y se pueden quitar.
- Texto de personas, tiendas y Claude va siempre como DATOS delimitados; las plantillas escapan.

## 9. Pruebas

`pistas` (cada código y el vacío), `parsear` (bueno/malo), `diagnosticar` con `_llamar_contando` falso (texto, una
corrección, tokens, guardado, error guardado), tarifa y tipo; `_aplicar_veredicto` (diagnóstico + gasto + aprendizaje
+ salto/solo_proponer según `siguiente`), `acciones.pedir` con `solo_proponer`, `_precio_estimado` con `salto`;
`derivaciones` (derivar todo hook con `lead_objetivo` y `ganchos_usados`; rescatar con `salto`; `_opciones_de` pasa el
contexto); `variar_guion` con contexto (arranque objetivo, ganchos usados, diagnóstico, aprendizajes) y ambos
`producir` pasando ángulo y contexto; `desde_veredicto` y `texto_para_prompt`; rutas y plantilla de aprendizajes;
inyección en ideas y guion base; Flow Plus (cada paso recibe su rebanada; el refinador con la lista de bloques);
página de la doctrina con la rebanada nueva. Suite completa, prueba real (diagnóstico sobre una perdedora real de
Happy Flops si la hay; si no, sobre una pieza con veredicto simulado en la copia), despliegue.

## 10. Fuera de este bloque

- Explicar pérdidas con datos de la landing (velocidad, mensaje) que Creatv no mide.
- Aprender entre proyectos.
- El gasto fijo del guion (tarea aparte, chip).
