# Doctrina, bloque 2: el ángulo a la vista — diseño

Fecha: 2026-09-26. Estado: aprobado en conversación, pendiente de revisión escrita.
Antecedente: `docs/superpowers/specs/2026-09-25-doctrina-copywriting-design.md` (bloque 1,
en producción desde 2026-09-26, `d20e133`) y su ADR `docs/adr/0004-doctrina-destilada-y-angulo.md`.

## 0. Propósito

El bloque 1 hizo que Claude decida un **ángulo** antes de escribir y lo guarde, pero todo
ocurre por dentro: nadie lo ve ni lo puede corregir, Claude adivina qué tanto sabe la
audiencia y cuántas promesas parecidas vio el mercado, lo que Claude anota como
`faltantes` se pierde en un JSON, y la doctrina solo existe en archivos del repo.

El bloque 2 lo saca a la vista, en cuatro partes:

1. **El ángulo visible y editable** en cada idea del sprint y en el guion de cada pieza,
   con un botón opcional para reescribir la idea desde el ángulo editado.
2. **Datos del mercado**: la consciencia de cada persona y la sofisticación de cada
   producto las elige la persona que usa la app, y cuando están elegidas mandan.
3. **Lo que Claude necesita**: los `faltantes` de todas las piezas de un producto se
   resumen en pedidos concretos al cliente; cada respuesta queda como **prueba del
   producto** y entra en todo lo que se genere después.
4. **La doctrina visible**: una página de solo lectura, «Cómo escribe Creatv».

## 1. Decisiones (tomadas con Daniel el 2026-09-26)

| Pregunta | Decisión |
|---|---|
| Alcance | Las cuatro partes en esta tanda. |
| Qué del ángulo se edita | **Todo**: audiencia, consciencia, sofisticación, deseo, promesa, mecanismo, pruebas, arranque, gancho. |
| Datos del mercado | **Mandan siempre** cuando están elegidos; vacíos («Que Claude lo decida») todo sigue como hoy. |
| Pedidos | **En cada producto**; la respuesta queda como prueba del producto. |
| Cómo se arman los pedidos | **Claude los resume** con un clic (≈ US$0,01), máximo cinco; todo en los `extra` que ya existen, sin tablas nuevas. |
| Doctrina visible | **Todos**, solo lectura. |
| Tras editar un ángulo | Guardar es gratis; botón opcional «Reescribir la idea con este ángulo» con su precio. |

Reglas del proyecto que siguen vigentes: el camino directo de Crear («Generar video») nunca
pide un ángulo; ningún paso pagado corre solo (un clic con el precio a la vista,
`max_intentos=1`, `gastos.registrar_seguro`); nunca se pierde lo pagado; sin migraciones.

Ajuste respecto de lo conversado: hoy **no existe un formulario para editar personas** (la
ruta `sprints.persona_editar` existe, pero ninguna plantilla la usa; las personas nacen en
Nicho o en «Sugerir personas»). El selector de consciencia va por eso en la página de ideas
de la campaña, junto al nombre de la persona, que es donde se generan las ideas (§4.1).

## 2. Glosario nuevo (entra a `CONTEXT.md`)

- **Datos del mercado**: la consciencia de una persona y la sofisticación de un producto
  elegidas a mano; cuando existen, Claude no las decide.
- **Prueba del producto**: un hecho real con su fuente (`ficha` = dato que dio el cliente,
  `comentarios` = comentario real de un comprador) guardado en el producto; entra a los
  DATOS de toda generación con ese producto y cuenta como dato verificado.
- **Pedido**: algo concreto que Claude necesita del cliente para escribir mejor sobre un
  producto («pega un comentario real sobre el calor del forro»), con su «para qué».
- **Ángulo editado a mano**: un ángulo que alguien guardó desde la app; pasa a ser
  responsabilidad de quien lo editó (§3.4).

## 3. Parte 1: el ángulo visible y editable

### 3.1 Dónde aparece

- **Idea del sprint** (`templates/campana_ideas.html`, tarjeta `.sprint-idea`): un
  `<details class="angulo">` plegado bajo la escena, con el resumen en el `<summary>`
  («Consciente del problema · problema-solución · “El primer paso…”») y el editor dentro.
  Si la idea ya tiene sesión (`i.sin_sesion` falso), el editor queda de solo lectura, igual
  que el título y la escena hoy: el ángulo vivo pasa a ser el de la sesión.
- **Guion de una pieza de Crear** (`templates/_tab_creativeflowplus.html`, bloque de
  edición final, antes de «Preparar guion» y junto al guion ya preparado): el mismo
  editor sobre `concepto.extra.angulo`. Una sesión sin ángulo muestra «Todavía no tiene
  ángulo: se decide al preparar el guion» y permite llenarlo a mano.
- Un solo parcial para los dos: `templates/_angulo_editor.html` (macro
  `editor_angulo(angulo, url_guardar, solo_lectura)`).

### 3.2 El editor

| Campo | Control |
|---|---|
| Audiencia, deseo, promesa, mecanismo | `input`/`textarea` de texto |
| Consciencia | `select` con `doctrina.CONSCIENCIAS` y sus nombres + «Que Claude lo decida» |
| Sofisticación | `select` 1–5 con `doctrina.SOFISTICACIONES_NOMBRE` |
| Arranque | `select` con `doctrina.LEADS` y `LEADS_NOMBRE`; marca los recomendados para la consciencia elegida (`lead_por_consciencia`) |
| Gancho | `input` con contador de palabras (máx. 12) |
| Pruebas | hasta 3 filas `texto` + `select` fuente (`ficha` / `comentarios` / `demostracion`) |
| Faltantes | lista de solo lectura (sin las líneas `error: …`), con enlace a los pedidos del producto |

Cada grupo de campos lleva un enlace «¿Por qué?» a la sección de la doctrina que lo explica
(§6.3). Autoguardado con el mismo patrón de las tarjetas de idea (debounce + `fetch` JSON,
aviso «Guardado»).

### 3.3 Rutas

- `POST /cliente/<cliente>/sprints/ideas/<cp_id>/angulo` (Blueprint `sprints/rutas.py`,
  `idea_angulo`): JSON `{angulo}` → valida (§3.4) → `datos.actualizar_idea(cp_id,
  extra={..., "angulo": limpio}, gancho=limpio["gancho"])`. El campo «Gancho» que ya tiene
  la tarjeta y el gancho del ángulo son el mismo: editar cualquiera de los dos actualiza
  ambos. 409 si la idea ya tiene sesión.
- `POST /cliente/<cliente>/creative_flow/<cf_id>/angulo` (`dashboard.py`, `cf_angulo`, junto a `fe_preparar`): igual sobre
  `creative_flow.actualizar(cliente, cf_id, angulo=limpio)`.
- Ambas responden `{ok, angulo, avisos}`; mismas comprobaciones de dueño y de origen que las
  rutas vecinas.

### 3.4 Validación de lo editado a mano

Función pura `doctrina.angulo_desde_formulario(datos) -> (limpio, avisos)`:

- Pasa por `validar_angulo(datos, datos_texto=None)`: las reglas de forma (una sola
  promesa, mecanismo si sofisticación ≥ 3, gancho ≤ 12 palabras, valores del vocabulario).
- Las cifras que escribe la persona **no** se verifican contra nada: las puso ella.
- `avisos` traduce cada código a una frase simple (`doctrina.MENSAJES_ERROR`, p. ej.
  `promesa_multiple` → «La promesa tiene más de una idea: déjala en una sola frase.»).
  Los avisos se muestran bajo el campo y **no bloquean** el guardado.
- Conserva `origen` (dónde nació) y agrega `editado_en` (`db.ahora()` en ISO).
- Quita de `faltantes` las líneas `error: …` que había dejado Claude: al guardar a mano el
  ángulo pasa a ser de quien lo editó.

`doctrina.texto_verificable` cambia: si el ángulo tiene `editado_en`, audiencia, deseo,
promesa, mecanismo y gancho cuentan como dato verificado aunque hubiera errores antes.
Así el guion puede decir una cifra que escribió la persona.

### 3.5 «Reescribir la idea con este ángulo»

- Botón en la tarjeta de la idea, solo si `sin_sesion`, con el precio
  (`gastos.estimar("reescribir_idea")`).
- `POST .../ideas/<cp_id>/reescribir` encola la tarea `sprint_reescribir_idea`
  (`max_intentos=1`, `job_id` determinista por idea, barra de progreso en la tarjeta).
- `sprints/ideas.reescribir(cliente, cp_id)`: una llamada con
  `doctrina.bloque_system("gancho", "video", extra=...)`, los mismos DATOS de la campaña
  (`contexto_campana` + `armar_prompt`) y el ángulo como fijo; Claude devuelve
  `{titulo, escena, sonido}`. El gancho es el del ángulo (no se reescribe) y el ángulo no
  se toca. Tope de salida con el mismo criterio de `max_tokens_para(1)`.
- Respuesta inválida o error de la API: la idea queda como estaba; si hubo tokens pagados
  se registran igual. Gasto `gastos.registrar_seguro(cliente, "ideas", usd,
  f"idea:reescribir:{cp_id}:t{tarea_id}")` con los tokens reales.

## 4. Parte 2: datos del mercado

### 4.1 Consciencia de la persona

- En `campana_ideas.html`, junto al nombre de la persona: `select` «Qué tanto sabe
  <persona>» con los cinco niveles (cada uno con una frase de ejemplo) + «Que Claude lo
  decida». Viene marcado si `persona.extra.conciencia.nivel` existe (las personas de Nicho
  y de «Sugerir personas» ya lo traen).
- `POST /cliente/<cliente>/sprints/personas/<pid>/conciencia` (JSON `{nivel}`) guarda
  `persona.extra.conciencia = {"nivel": <clave>, "detalle": <el que había>, "origen":
  "manual"}` con `doctrina.normalizar_consciencia`; `nivel` vacío borra el nivel.
- La misma persona se usa en todas sus campañas: cambiarla en una página la cambia en todas
  (se avisa en el texto del selector).

### 4.2 Sofisticación del producto

- En `templates/_catalogo_campos_comerciales.html` (Catálogo › producto, junto al precio):
  `select` «Cuántas promesas parecidas vio ya tu cliente», 1–5 con palabras simples + «Que
  Claude lo decida».
- Se guarda en `producto.extra.sofisticacion` (1–5 o ausente) desde `_campos_comerciales` /
  `actualizar_producto`, con una función nueva `tiendas.anotar_doctrina(cliente,
  producto_id, **claves)`.
- **`tiendas.EXTRA_INTERNO` gana `sofisticacion`, `pruebas` y `pedidos`**: una
  sincronización de tienda reescribe `producto.extra` y solo conserva esas claves; sin esto
  la próxima sync borraría lo que el cliente escribió.

### 4.3 Cómo mandan

- `doctrina.validar_angulo(angulo, datos_texto=None, fijos=None)`: con
  `fijos={"consciencia": ..., "sofisticacion": ...}` reemplaza esos campos **antes** de
  revisar las reglas, así el mecanismo obligatorio y el arranque recomendado se evalúan con
  los valores fijos y sus errores entran a la ronda de corrección que cada sitio ya tiene.
- Los DATOS que recibe Claude dicen «Consciencia de la persona (fija, no la cambies): …» y
  «Sofisticación del mercado (fija): N — …».
- Sitios:
  - Ideas de sprint (`sprints/ideas.py`): consciencia de la persona de la campaña +
    sofisticación del producto de la campaña.
  - Guion cuando Claude decide el ángulo (`final_edition/guion.generar_guion_base` sin
    ángulo): sofisticación del producto de la sesión.
  - «Adaptar con IA» (`referentes/recrear.adaptar`): sofisticación del producto elegido.
- Un ángulo editado a mano (§3.4) puede tener otro nivel: vale para esa pieza.

## 5. Parte 3: lo que Claude necesita y las pruebas del producto

### 5.1 Datos (en `producto.extra`, protegidos por `EXTRA_INTERNO`)

```
pruebas: [{"id": "p1", "texto": "...", "fuente": "ficha"|"comentarios", "creada_en": "...", "pedido_id": "k3"|null}]
pedidos: [{"id": "k3", "texto": "...", "para_que": "...", "estado": "abierto"|"respondido"|"descartado",
           "creado_en": "...", "respondido_en": null}]
```

Máximo 20 pruebas por producto y textos de hasta 400 caracteres. Escritor único:
`tiendas.anotar_doctrina` y funciones pequeñas en `doctrina/pedidos.py` que lo usan.

Todas las rutas de producto usan `<producto_id>` = el id del activo del catálogo, igual que
`actualizar_producto` y sus vecinas; la fila `producto` (donde viven `extra.pruebas` y
`extra.pedidos`) se obtiene con `tiendas.asegurar_manual`, que la crea si falta.

### 5.2 Juntar lo que falta (puro)

`doctrina.pedidos.faltantes_del_producto(cliente, producto) -> list[str]`:

- Ángulos de las ideas (`campana_pieza.extra.angulo`) de las campañas cuyo `catalogo_id`
  es el activo del producto (`producto.activo_catalogo_id`).
- Ángulos de las sesiones (`concepto.extra.angulo`) cuyo `productos_ids` apunta al producto
  (id o nombre, con `catalogo_productos.encontrar_por_id_o_nombre`).
- Quita las líneas `error: …`, las «arranque fuera de lo recomendado», y las que hablan de
  consciencia o sofisticación (las resuelve la Parte 2); sin repetir textos idénticos.

### 5.3 Resumir en pedidos (pagado, un clic)

- Botón «Actualizar lo que Claude necesita» con el precio estimado, en el producto; `POST
  /cliente/<cliente>/productos/<producto_id>/pedidos/actualizar` encola `producto_pedidos`
  (`max_intentos=1`, `job_id` determinista por producto, barra de progreso). Sin faltantes,
  no encola y avisa «Claude no ha pedido nada para este producto».
- `doctrina.pedidos.resumir(cliente, producto_id)`: una llamada con
  `doctrina.bloque_system(extra=INSTRUCCIONES_PEDIDOS)` (rebanada `base`), que recibe los
  faltantes, la ficha del producto, las pruebas que ya tiene y los pedidos respondidos o
  descartados («no vuelvas a pedir esto»). Devuelve máximo cinco `{texto, para_que}` en
  español, en imperativo y concretos.
- Reemplaza solo los pedidos `abierto`; conserva `respondido` y `descartado`. Respuesta
  inválida o error: quedan los pedidos que había. Gasto `pedidos` con los tokens reales
  (`producto:pedidos:<producto_id>:t<tarea_id>`), también si la respuesta no sirvió.

### 5.4 Responder, descartar y pruebas directas

- En el producto, «Lo que Claude necesita»: cada pedido abierto con su «para qué», un
  `textarea` «Tu respuesta», un `select` «Es un dato del producto / Es un comentario real
  de un comprador», «Guardar como prueba» y «No aplica».
- `POST .../pedidos/<pedido_id>/responder` crea la prueba (`pedido_id` enlazado) y marca el
  pedido `respondido`; `POST .../pedidos/<pedido_id>/descartar` lo marca `descartado`.
- «Pruebas del producto»: lista con «Agregar prueba» (`POST .../pruebas`) y «Borrar»
  (`POST .../pruebas/<prueba_id>/borrar`), sin pasar por un pedido.
- La lista de productos muestra «N pedidos» en el resumen del producto cuando hay abiertos.

### 5.5 Dónde entran las pruebas

Como una línea «PRUEBAS REALES DEL PRODUCTO» (texto + fuente) en los DATOS de:

- Ideas de sprint (`sprints/ideas.contexto_campana` → `armar_prompt`).
- Guion (`final_edition._producto` gana `pruebas`; `_datos_verificables` ya serializa el
  producto, así que cuentan para la verificación de cifras).
- «Adaptar con IA» (el `producto` que arma `referentes/rutas`, y su `datos_texto`).
- Captions (`organico.contexto_pieza` → `generador_prompts.caption_organico`).

En todos los sitios cuentan como dato verificado: una cifra que está en una prueba real sí se
puede decir.

## 6. Parte 4: la doctrina visible

### 6.1 Página

- `GET /doctrina` (`dashboard.py`, `doctrina_pagina`), para cualquier usuario con sesión.
  Plantilla `templates/doctrina.html`: título «Cómo escribe Creatv», una línea «Así le
  explicamos a Claude cómo escribir tus anuncios. Cada pieza que genera la app sigue estas
  reglas.», índice y las nueve rebanadas en el orden de `doctrina.REBANADAS`, cada una con
  su ancla (`#base`, `#angulo`, `#gancho`, …).
- Lee los mismos `doctrina/textos/*.md` que recibe Claude: nunca se desincroniza.

### 6.2 Conversión

`doctrina/pagina.py::a_html(texto) -> Markup`, puro y sin librerías nuevas: primero escapa
todo el HTML, después convierte lo que usan los textos (títulos `#`/`##`, listas `-`,
párrafos, `**negrita**`, `*cursiva*`, `` `código` ``). Nada del texto puede inyectar HTML.

### 6.3 Enlaces

- «¿Por qué?» del editor de ángulo: audiencia, deseo, consciencia, sofisticación, promesa,
  mecanismo y pruebas → `#angulo`; arranque y gancho → `#gancho`; el aviso de cifras →
  `#base`.
- Configuración › Generación: enlace «Cómo escribe Creatv».

## 7. Qué no cambia

- «Generar video» directo, el director opcional, Sprints sin enfoque `libre`.
- El bloque 1: vocabulario, verificación de cifras, correcciones, orden de rebanadas.
- Ningún texto de la doctrina se edita desde la app.
- Cada cliente solo ve y edita sus personas, productos, ideas y sesiones.

## 8. Costos

- Dos acciones pagadas nuevas, ambas con precio en el botón: «Reescribir la idea con este
  ángulo» (`gastos.TARIFAS["reescribir_idea"]`) y «Actualizar lo que Claude necesita»
  (`gastos.TARIFAS["pedidos_producto"]`). Las tarifas se fijan con los tokens medidos en la
  prueba real (§10), no a ojo; hasta entonces el estimado usa el costo medido de una
  llamada de ideas del bloque 1.
- `gastos.TIPOS` gana `ideas` y `pedidos`.
- Las pruebas del producto agregan pocas líneas a los DATOS: costo marginal.

## 9. Pruebas automáticas

- `tests/test_doctrina.py`: `angulo_desde_formulario` (avisos en español, no bloquea, quita
  `error:`, pone `editado_en`), `validar_angulo(..., fijos=)` (reemplaza y re-evalúa
  mecanismo y arranque), `texto_verificable` con `editado_en`.
- `tests/test_doctrina_pedidos.py`: `faltantes_del_producto` (ideas + sesiones por id y por
  nombre, filtros), `resumir` con Claude simulado (conserva respondidos/descartados, respuesta
  inválida no borra nada, registra gasto), responder/descartar/borrar.
- `tests/test_doctrina_pagina.py`: `a_html` (escapa `<script>`, convierte títulos, listas,
  negritas), la página muestra las nueve rebanadas y exige sesión.
- Rutas: guardar ángulo de idea (y 409 con sesión), de sesión, consciencia de persona,
  sofisticación en Catálogo, pedidos (encola con precio, no encola sin faltantes).
- `tests/test_tiendas*`: una sync conserva `sofisticacion`, `pruebas` y `pedidos`.
- Sitios: ideas y guion reciben los datos fijos y las pruebas en DATOS; «Reescribir»
  conserva el ángulo y el gancho.

## 10. Orden de construcción

1. Datos del mercado: `validar_angulo(fijos=)`, `EXTRA_INTERNO`, campos en Catálogo y en la
   página de ideas, los tres sitios.
2. Ángulo visible y editable: parcial, rutas, `angulo_desde_formulario`, `texto_verificable`.
3. «Reescribir la idea con este ángulo».
4. Pruebas del producto y pedidos.
5. Página de la doctrina y enlaces.
6. Documentación (`CLAUDE.md`, `CONTEXT.md`) y prueba real con Happy Flops (con OK de
   Daniel; mide las tarifas de §8).

## 11. Riesgos

| Riesgo | Cómo se acota |
|---|---|
| Una sync de tienda borra pruebas y pedidos | `EXTRA_INTERNO` + prueba automática. |
| Un ángulo editado con una cifra falsa llega a la voz | Queda marcado `editado_en`; es decisión explícita de quien lo editó y la interfaz lo dice. |
| Pedidos repetidos o vagos | Claude recibe lo ya respondido/descartado; máximo cinco; «No aplica». |
| La página de la doctrina inyecta HTML | `a_html` escapa antes de convertir; prueba con `<script>`. |
| Un cambio de consciencia en una campaña afecta otras | Es la misma persona: el selector lo dice. |
| Formularios largos en el celular | Editor plegado por defecto; campos en una columna a < 760 px. |

## 12. Fuera de este bloque

- Bloque 3 (revisor gratis antes de gastar) y bloque 4 (cerrar el ciclo con Experimentos).
- La doctrina en el pipeline de Flow Plus (`guiones/`).
- Editar la doctrina desde la app.
- Reclasificar los referentes viejos para que tengan `lead`.
