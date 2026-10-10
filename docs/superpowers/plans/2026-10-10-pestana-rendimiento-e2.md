# Pestaña «Rendimiento» E2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los anuncios de fuente Meta queden a la par de los de Triple Whale en la pestaña «Rendimiento»: una sola galería con un solo lote, «Cómo mejorarlo» y «Evaluar con IA» para ellos, recomendaciones de la cuenta (PND-192) y detalle del día.

**Architecture:** Se REUSA el flujo pagado de Triple Whale (tabla `tw_analisis`/`tw_evaluacion`, tareas `tw_analizar_anuncio`/`tw_evaluar`, sus garantías de precio y de no cobrar dos veces) con una marca de fuente en la «foto». Lo único nuevo para Meta: de dónde salen imagen, video y texto (`meta_rendimiento/creativo.py`, copia a R2), un «alcance» de Meta con la misma forma que el de Triple Whale, y rutas de la pestaña que eligen la fuente de cada tarjeta.

**Tech Stack:** Python 3, Flask, SQLAlchemy Core/SQLite, Jinja2, JS ES5, Flask-Babel, pytest; Graph API de Meta (solo lectura, token del proyecto); Cloudflare R2.

**Spec:** `docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md` (§6 E2, §9 A1 y A6). El plan de E1 (`docs/superpowers/plans/2026-10-09-pestana-rendimiento-e1.md`) ya está hecho: lee su «Global Constraints».

## Global Constraints

- Las mismas de E1 (worktree `rendimiento-unificado`, catálogo, estilos, commits, skills a cargar, hooks), más:
- **Plata (CLAUDE.md regla 1):** todo lo que cobra muestra su precio antes (`gastos.estimar`), corre como tarea con `max_intentos=1`, anota lo que de verdad cobró con `gastos.registrar_seguro` (también al fallar después de pagar) y pasa por Cobros (`libro.exigir` antes de crear filas; `costo_estimado` al encolar). Un segundo clic o un segundo envío del mismo formulario no cobra (job_id determinista; el lote cobra solo lo confirmado Y aún elegible). Nada de esto se reescribe: se mueve y se reusa.
- **Seguridad:** el token de Meta nunca llega a un error, flash, evento, log, foto ni plantilla (`cola.sin_token`, `graph`). Toda URL de Meta que el servidor baja pasa por `conectores.url.descargar_archivo` (SSRF en cada redirección, tope de tamaño y tiempo) y solo si su host termina en `fbcdn.net` (videos) o es `fbcdn.net`/`facebook.com`/`fbsbx.com` (imágenes, `meta_rendimiento.datos.miniatura_valida`). Lo que se le manda a Claude o se muestra en una tarjeta solo sale de R2 o de `files.triplewhale.com` (`triple_whale.medio_permitido`). Texto ajeno (copy, título, nombre) llega a Claude delimitado como hoy (`mejorar._dato`/`_linea`).
- **Prompt:** el único cambio de prompt permitido es el nombre de la fuente de los números («de Triple Whale» → «de {fuente}»). No se cambia doctrina, `max_tokens`, modelo ni validación. (Ruling: con solo el nombre de la fuente no se repite la medición de `eval-claude`; la primera ejecución real queda anotada para Daniel.)
- **Modo agencia y «solo métricas»:** leer medios usa `meta_conexion.cargar(cliente)["token"]` (funciona sin Página); en modo agencia la lectura de Meta sigue como en E1 (PND-197).

---

### Task 1: Medios de un anuncio de Meta para el análisis pagado

**Files:**
- Create: `meta_rendimiento/creativo.py`
- Modify: `meta_rendimiento/graph.py` solo si falta un GET de un objeto por id con campos (reusa lo que haya)
- Modify: `triple_whale/mejorar.py` (`foto(..., fuente="triple_whale", ad_account_id=None)`; `PROMPT` con `{fuente}`; `armar` pasa la fuente)
- Modify: `triple_whale/analisis.py` (`PROMPT` de la evaluación con `{fuente}`; `analizar(..., fuente=...)`)
- Modify: `tareas/triple_whale.py` (`tw_analizar_anuncio`: si `foto["fuente"] == "meta"` y `foto["creativo"]` vacío, trae los medios, guarda la foto y sigue; `detalle` del gasto «un anuncio de Meta»)
- Test: `tests/test_rendimiento_e2_creativo.py`

**Interfaces:**
- Produces:
  - `meta_rendimiento.creativo.traer(cliente, ad_id, analisis_id) -> dict` con las claves de `triple_whale.datos.COLUMNAS_CREATIVO` (`tipo`, `imagen_url`, `video_url`, `titulo`, `copy`, `cta`, `duracion_s`). `imagen_url` y `video_url` son URL de R2 (claves `clientes/<cliente>/rendimiento/a<analisis_id>_<ad_id>.jpg|.mp4`) o None. Nunca lanza: lo que falla queda en None.
  - `mejorar.foto(a, creativo, cuenta, ganadores, fuente="triple_whale", ad_account_id=None)`: la foto lleva `"fuente"` y, con Meta, `"ad_account_id"`.
  - `mejorar.FUENTES = {"triple_whale": "Triple Whale", "meta": "Meta"}` (nombres propios, no se traducen).

Reglas:
1. Lectura con el token del proyecto (`meta_conexion.cargar(cliente)["token"]`) y `meta_rendimiento.graph` (token explícito, nunca `meta_ads.auth`): `GET /{ad_id}?fields=creative{id,body,title,thumbnail_url,image_url,video_id,object_type,call_to_action_type,object_story_spec,asset_feed_spec}`; si hay `video_id`: `GET /{video_id}?fields=source,length`. Texto: `body`/`title`, y si faltan, los de `object_story_spec` (`link_data.message`/`name`, `video_data.message`/`title`) o el primero de `asset_feed_spec` (`bodies[0].text`, `titles[0].text`). Recorta como `tw_creativo` (título 300, copy sin tope pero el prompt ya recorta).
2. Imagen: `image_url` o `thumbnail_url` solo si `datos.miniatura_valida(url)`; se baja (como `analisis.copiar_miniaturas`: PIL, JPEG, lado `analisis.LADO_IMAGEN`) y se sube con `storage.r2_uploader.upload_image`.
3. Video: `source` solo si es https y su host termina en `.fbcdn.net`; se baja con `conectores.url.descargar_archivo(url, ruta_temporal)` (tope de 60 MB y de tiempo del conector), se comprueba con `mejorar.es_mp4`, y se sube con `storage.r2_uploader.upload_video`; el temporal se borra en un `finally`. `duracion_s` = `length`.
4. Un error de Graph (incluido el límite de uso, `ErrorGraph.limite`) o de red deja la clave en None y se anota en el log con `type(e).__name__`, sin token. No toca la pausa compartida (dos llamadas no la justifican).
5. En `tw_analizar_anuncio`, antes de `mejorar.visuales(foto)`: si `foto.get("fuente") == "meta" and not foto.get("creativo")`, `trabajos.reportar(job_id, etapa=idiomas.N_("Trayendo el anuncio de Meta"))`, `foto["creativo"] = creativo.traer(cliente, fila["ad_id"], aid)`, `datos.actualizar_analisis(aid, foto=foto)`, y `medios["copy"]` se recalcula. El resto de la tarea no cambia.
6. `PROMPT` de `mejorar` y de `analisis`: «con sus números de {fuente}» / «con sus métricas de {fuente}». `armar` toma la fuente de `fila["foto"]["fuente"]` (defecto Triple Whale); `analisis.analizar` la recibe del contexto (`contexto["fuente"]`, defecto Triple Whale).

- [ ] **Step 1: Write the failing tests** — con `monkeypatch` sobre `meta_rendimiento.graph` (o la función de GET que uses), `storage.r2_uploader.upload_image/upload_video`, `conectores.url.descargar_archivo` y `mejorar.es_mp4`:
  - `traer` arma título/copy desde `creative.body/title` y, sin ellos, desde `object_story_spec`; sube imagen y video a R2 y devuelve esas URL; `duracion_s == length`.
  - un `source` de video con host que no termina en `.fbcdn.net` (p. ej. `https://evil.example/v.mp4`) NO se baja (`descargar_archivo` no se llama) y `video_url` queda None; una imagen que no pasa `miniatura_valida` no se baja.
  - un `ErrorGraph` deja todo en None y el token no aparece en ningún registro (`caplog`).
  - `tw_analizar_anuncio` con una fila cuya foto es `{"fuente": "meta", "creativo": {}, …}`: llama a `creativo.traer` UNA vez, guarda la foto con el creativo, y el texto que llega a Claude dice «de Meta» y no «de Triple Whale» (monkeypatch de `mejorar.analizar` capturando el texto; reusa los ayudantes de `tests/test_tw_tarjetas_tarea.py` o el archivo de la tarea de análisis que exista).
  - una foto sin `fuente` (las de Triple Whale ya guardadas) sigue diciendo «de Triple Whale».
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `venv/bin/python3 -m pytest tests/test_rendimiento_e2_creativo.py tests/test_tw_tarjetas_*.py tests/test_triple_whale_analisis.py -q`; catálogo (`actualizar`, traducir, `compilar`).
- [ ] **Step 5: Commit** «Rendimiento E2 (1/7): los medios de un anuncio de Meta llegan a R2 para el análisis y el prompt dice de qué fuente son los números».

---

### Task 2: El pedido pagado sale de las rutas de Triple Whale a un módulo propio

**Files:**
- Create: `triple_whale/pedidos.py`
- Modify: `triple_whale/rutas.py` (sus rutas llaman a `pedidos`; ningún cambio de comportamiento)
- Test: los existentes (`tests/test_tw_tarjetas_rutas.py`, `tests/test_rutas_triple_whale.py`) siguen verdes sin tocarlos; `tests/test_rendimiento_e2_pedidos.py` para las funciones movidas.

**Interfaces:**
- Produces (movidas tal cual desde `triple_whale/rutas.py`, sin cambiar lógica ni textos):
  - `pedidos.anuncio_del_alcance(alc, canal, ad_id)`
  - `pedidos.pedir_analisis(cliente, alc, a, usuario) -> tuple[bool, str]` (la de hoy `_pedir_analisis`, con `usuario` explícito en vez de `session`)
  - `pedidos.claves_confirmadas(valores, tope=None)`
  - `pedidos.pedir_lote(cliente, alc, claves, usuario) -> tuple[int, int]` (lo que hoy hace el cuerpo de `analizar_lote` después de resolver el alcance: cobra solo `confirmadas ∩ elegibles`, para en el primero sin saldo, re-lanza `SaldoInsuficiente`)
  - `pedidos.pedir_evaluacion(cliente, alc_eval, usuario) -> tuple[bool, str]` (el cuerpo de `evaluar`: muestra, precio, `libro.exigir`, crear fila con su `extra`, encolar, borrar si falla)
- `alc` sigue siendo el dict de `triple_whale.panel.alcance` (`config`, `tienda`, `tienda_id`, `dias`, `canal`, `ev`, `desde`, `hasta`, `params`). `alc_eval` = `{"ev", "desde", "hasta", "moneda", "extra"}` (lo que la evaluación guarda).

Regla: es una mudanza. Cada comentario que explica una garantía (A1, A4, A5, B6, Cobros) se muda con su código. `tests/test_tw_tarjetas_rutas.py` y los de `evaluar` no se tocan y siguen verdes; si alguno necesita cambiar, la mudanza cambió comportamiento: para y repórtalo.

- [ ] Steps: test de humo de las funciones movidas (importan, firmas) → mudanza → suite de Triple Whale verde → commit «Rendimiento E2 (2/7): el pedido pagado de un análisis vive en triple_whale/pedidos.py».

---

### Task 3: El alcance de Meta con la forma del de Triple Whale

**Files:**
- Create: `pestana_rendimiento/alcance_meta.py`
- Test: `tests/test_rendimiento_e2_alcance_meta.py`

**Interfaces:**
- Consumes: `meta_rendimiento.panel.anuncios_evaluados`, `rango_fechas`, `lista`; `pestana_rendimiento.panel._resolver` (o la función pública equivalente que exista) para las cuentas `meta_fuente` del alcance.
- Produces: `alcance_meta.alcance(cliente, ids, dias, hoy, params) -> dict | None` con la MISMA forma que `triple_whale.panel.alcance`:
  - `config = {"moneda": <moneda común de las cuentas o "USD">, "modelo_atribucion": "Pixel de Meta", "ventana_atribucion": "Meta"}`
  - `tienda = None`, `tienda_id = None`, `canal = None`, `dias`, `desde`, `hasta`, `params` (los de la pestaña: `entrada`, `dias`)
  - `ev` = la evaluación de Meta con cada anuncio con `canal = "facebook-ads"` (`triple_whale.CANAL_META`), `creative_id`, `nombre`, `campana`, `veredicto`, `m`, `anillos`…, más `ev["cuenta"]` (`evaluacion.resumen_cuenta`), `ev["benchmarks"]`, `ev["benchmarks_canal"]`, `ev["meta_roas"]`, `ev["conteo"]`, `ev["hay_ventas"]`.
  - `fuente = "meta"` (clave nueva; el de Triple Whale no la tiene y se lee como `"triple_whale"`).
- Regla: con cuentas en monedas distintas, `config["moneda"]` es None y el pedido pagado guarda la moneda de la cuenta del anuncio (cada anuncio lleva `moneda`).

- [ ] Steps: tests (forma igual a la de Triple Whale; canal `facebook-ads`; un anuncio que no es del alcance no aparece; moneda común y mezcla) → implementar → commit «Rendimiento E2 (3/7): el alcance de Meta habla como el de Triple Whale».

---

### Task 4: Una sola galería y un solo lote

**Files:**
- Create: `pestana_rendimiento/galeria.py`
- Modify: `pestana_rendimiento/rutas.py` (rutas nuevas), `pestana_rendimiento/panel.py` (la galería unida en el contexto), `templates/_tw_galeria.html` (las URL de la tarjeta y del lote salen de un parámetro), `templates/_rend_panel.html` (04 Tus anuncios = una galería), `templates/_tab_rendimiento.html` (el JS apunta a las rutas nuevas), y se jubilan `triple_whale.rutas.galeria`, `tarjeta`, `analizar_anuncio`, `analizar_lote` y el bloque de tarjetas Meta de E1 (`_rend_anuncios_meta.html`, `rendimiento.ver_anuncios_meta`) con sus pruebas migradas.
- Test: `tests/test_rendimiento_e2_galeria.py`

**Interfaces:**
- Consumes: Task 2 (`pedidos.*`), Task 3 (`alcance_meta.alcance`), `triple_whale.panel.alcance`/`enriquecer`/`elegir_analisis`/`precio_analisis`/`filtrar`/`FILTROS_GALERIA`/`POR_PAGINA`/`N_LOTE`, `meta_rendimiento.tasas.usd(moneda, fecha)`.
- Produces:
  - `galeria.armar(cliente, alc_tw, alc_meta, veredicto="", pagina=1) -> dict` con la forma de `triple_whale.panel.galeria` (`tarjetas`, `pagina`, `hay_mas`, `total`, `veredicto`, `conteo_filtros`, `lote{n, claves, elegibles, precio}`), donde cada tarjeta lleva `fuente` (`"tw"`|`"meta"`) y `gasto_usd`, y cada clave del lote es `"<fuente>:<canal>:<ad_id>"`.
  - Rutas: `GET /cliente/<c>/rendimiento/galeria` (`entera=1` o `pagina`), `GET /cliente/<c>/rendimiento/tarjeta/<fuente>/<canal>/<ad_id>`, `POST /cliente/<c>/rendimiento/anuncio/<fuente>/<canal>/<ad_id>/analizar`, `POST /cliente/<c>/rendimiento/analizar-lote`. Todas resuelven el alcance con `entrada`/`dias` (+ `canal` solo si el alcance es solo Triple Whale), validan `fuente ∈ {"tw","meta"}` y los ids con `tareas.triple_whale.id_valido`, y para cobrar llaman a `pedidos.pedir_analisis` / `pedidos.pedir_lote` con el alcance de SU fuente.

Reglas:
1. Orden: veredicto no; **gasto en USD** (cada anuncio en su moneda, convertida con la tasa del último día del periodo, `tasas.usd`), de mayor a menor. Sin tasa, va al final en su orden nominal. Esto cierra PND-196.
2. Una página = 12 tarjetas mezcladas; `enriquecer` se llama UNA vez por fuente con sus tarjetas de la página (número fijo de consultas: la prueba de consultas de la galería de Triple Whale se replica con las dos fuentes).
3. El lote: los `N_LOTE` de más gasto en USD entre las dos fuentes a los que su tarjeta les ofrece el botón principal; el precio total es la suma de sus precios (con uno desconocido, «precio no disponible»); la ruta cobra solo lo confirmado Y aún elegible, separando por fuente y llamando a `pedidos.pedir_lote` por fuente; para en el primero sin saldo.
4. Tarjeta de Meta: la misma macro que la de Triple Whale. `medio` = miniatura de Meta (`miniatura_url` válida) mientras no haya análisis; si hay un análisis listo con `foto.creativo.imagen_url` de R2, esa. Sin «Guardar en Referentes» para Meta (queda en un PND nuevo).
5. «Meta reporta» (R12) solo en tarjetas de Triple Whale.

- [ ] Steps: tests (orden por USD con dos monedas; filtros y conteo mezclados; lote mezclado y su cobro solo de lo confirmado y elegible por fuente; un segundo envío no cobra; sin saldo para y no crea filas; tarjeta de Meta postea a la ruta nueva con `fuente=meta`; consultas fijas con 12 y 24 tarjetas; foránea → 404) → implementar → migrar pruebas de las rutas jubiladas → commit «Rendimiento E2 (4/7): una galería con los anuncios de las dos fuentes y un solo lote».

---

### Task 5: «Evaluar con IA» para los anuncios de Meta

**Files:**
- Modify: `pestana_rendimiento/rutas.py` (`POST /cliente/<c>/rendimiento/evaluar`), `templates/_tw_secciones.html` (o donde viva la macro `ia`) para postear a la ruta nueva, `tareas/triple_whale.py::tw_evaluar` (lee `extra["fuente"]` para el nombre en el prompt y `extra["cuentas"]` no hace falta: la muestra ya viene guardada).
- Test: `tests/test_rendimiento_e2_evaluar.py`

Reglas:
- Alcance solo Triple Whale: igual que hoy (`pedidos.pedir_evaluacion` con el alcance de Triple Whale).
- Alcance solo Meta: muestra de `alcance_meta` (`analisis.muestra(ev)`), `extra = {"fuente": "meta", "cuentas": ids, "modelo": "Pixel de Meta", "ventana": "Meta", "benchmarks", "meta_roas", "tienda_id": None, "pais": <de la entrada o None>}`; precio `gastos.estimar("evaluacion_tw", n=)` igual.
- Mezcla: la sección ofrece DOS botones con su precio («Evaluar los de tus tiendas» y «Evaluar los de tus cuentas de Meta»), nunca uno que mezcle fuentes en el mismo prompt (los números no son comparables).
- `tw_evaluar`: `medios_meta` ya lee miniaturas de Meta; usa `meta_conexion.cargar(cliente)["token"]` en vez de `credenciales_ads` (que exige cuenta de lanzamiento) — cambio mínimo en `analisis.medios_meta` con su prueba.
- Una evaluación en curso bloquea otra (`tareas_tw.evaluacion_en_curso`), como hoy.

- [ ] Steps: tests (Meta solo: crea la fila con su `extra`, precio, cobro; mezcla: dos formularios; el prompt dice «de Meta»; sin saldo no crea nada) → implementar → commit «Rendimiento E2 (5/7): Evaluar con IA también para los anuncios de Meta».

---

### Task 6: Recomendaciones de la cuenta (PND-192, sin desgloses)

**Files:**
- Create: `meta_rendimiento/recomendaciones.py` (puro)
- Modify: `pestana_rendimiento/panel.py` (`atencion` suma las recomendaciones de las cuentas de Meta del alcance)
- Test: `tests/test_rendimiento_e2_recomendaciones.py`

Reglas (spec de Meta rendimiento §9; las que necesitan `meta_desglose` quedan fuera, A6). Cada una devuelve `{"nivel": "alta"|"media"|"bien", "texto": …}` en el idioma de quien mira, con cifras que salen de los datos:
1. **Aprendizaje limitado:** conjuntos activos con `aprendizaje == "FAIL"`: «N de M conjuntos están en aprendizaje limitado (X % del gasto): junta conjuntos o sube su presupuesto para que salgan de ahí.» (media si ≥ 30 % del gasto).
2. **Rechazados o con problemas:** anuncios o conjuntos con `estado` en `DISAPPROVED`/`WITH_ISSUES`: «N anuncio(s) rechazado(s) o con problemas.» (alta).
3. **Cuenta con problema:** `extra.cuenta.account_status != 1` → alta, con `disable_reason` en palabras si se conoce; `spend_cap` con menos de 10 % disponible (`amount_spent`) → media.
4. **Ganadores con poco presupuesto:** anuncio `ganador` cuyo conjunto tiene `presupuesto_diario` menor que la mediana de los conjuntos activos con presupuesto → «Sube el presupuesto de …» (bien).
5. **Concentración:** un anuncio con ≥ 60 % del gasto de su conjunto en el periodo y su conjunto con ≥ 3 anuncios → media.
6. **Fatiga con frecuencia:** anuncio con `fatiga` y la campaña con frecuencia de 7 días ≥ 3 (`meta_alcance` ventana 7, nivel campaña) → media.
Lecturas: las que ya trae el contexto (estructura, anuncios evaluados, cuentas con `extra`), más una de `meta_objeto` para estados de anuncios/conjuntos activos si no está (una consulta). Número fijo de consultas.

- [ ] Steps: un test por regla con su umbral y su borde; textos en español (`idiomas.en_idioma("es")`) → implementar → commit «Rendimiento E2 (6/7): Rendimiento dice qué hacer en tus cuentas de Meta».

---

### Task 7: Detalle del día con Meta y con mezcla, cableado y documentos

**Files:**
- Modify: `meta_rendimiento/datos.py` (`anuncios_del_dia(cliente, cuentas, fecha, limite=5)` con nombre de `meta_objeto`, `primeros_dias` por anuncio, `arrancaron_el(cliente, cuentas, fecha)`), `pestana_rendimiento/resumen.py` (detalle de un día con Meta o mezcla usando `triple_whale.resultados.detalle_dia(..., fuente="meta"|"mixta")`), `pestana_rendimiento/rutas.py` (`GET /cliente/<c>/rendimiento/dia?entrada=&fecha=`; con alcance solo Triple Whale redirige el trabajo a `triple_whale.panel.contexto_dia` como hoy), `pestana_rendimiento/panel.py` (`url_dia` y `con_detalle=True` para Meta y mezcla), plantilla del día (reusa `_tw_dia.html` si su forma alcanza).
- Docs: skill `rendimiento` (E2), `triple-whale` (pedidos.py, fuente en la foto), `meta-rendimiento` (creativo.py, recomendaciones), `docs/pendientes.md` (PND-192 cerrado salvo desgloses; PND-194 parcial: las imágenes analizadas quedan en R2; PND-196 cerrado; PND nuevo: «Guardar en Referentes» para anuncios de Meta).
- Test: `tests/test_rendimiento_e2_dia.py`

Reglas: un día del primer día común a ayer; montos en la moneda del alcance (USD en la mezcla, con la misma regla de tasas que Resultados: sin tasa, 400 «USD no disponible ese día»); los anuncios del día de las dos fuentes por ventas en USD (Triple Whale: Pixel pagado; Meta: valor de compras), máximo 5; «nuevo» = primer día con gasto en su copia + 13. Consultas fijas.

- [ ] Steps: tests → implementar → suite completa → commit «Rendimiento E2 (7/7): el detalle del día con Meta y la guía al día».
