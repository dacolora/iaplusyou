# Rendimiento: las métricas que faltaban — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que la pestaña Rendimiento muestre, con datos de Triple Whale, ROAS de clientes nuevos, tasa de conversión,
productos con gasto y ROAS, los mejores anuncios para iterar, los que mejor convierten y las mejores imágenes y videos.

**Architecture:** un módulo puro `triple_whale/destacados.py` calcula todo desde `tw["ev"]["anuncios"]` (lo que el panel
ya evaluó para el país, periodo y canal) más dos lecturas fijas (tipo de creativo y Catálogo); `pestana_rendimiento.panel`
lo pone en `r.destacados` solo con fuente "tw"; macros nuevas en `templates/_rend_destacados.html` lo pintan.

**Tech Stack:** Flask + Jinja, SQLAlchemy Core sobre SQLite, Flask-Babel, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-rendimiento-metricas-que-faltaban-design.md`

## Global Constraints

- No cobra ni llama a proveedores: solo lee `tw_anuncio_dia`/`tw_creativo` (ya copiadas) y `producto`.
- Solo con `r.fuente == "tw"`; nunca con Meta o mezcla.
- Sigue el periodo de la pestaña («Desde el inicio» por defecto); nada de «este mes».
- Mínimos: `PEDIDOS_MIN_ITERAR = 10`, `SESIONES_MIN_CONVERSION = 100`, `PEDIDOS_MIN_CONVERSION = 3`; topes 8 / 8 / 6 por
  tipo / 10 productos + «Otros».
- Consultas fijas: `datos.tipos_creativo` (1), `tiendas.productos` (1), `datos.creativos` de ≤ 12 tarjetas (1).
- Todo texto visible por `_()` y traducido al inglés (`catalogo_i18n.py actualizar` → traducir → `compilar`).
- `<img loading="lazy">`, `<video preload="none" data-precarga>`; tablas en `.tw-tabla-scroll`; sin `<script>`.
- `static/style.css` es generado: editar `static/estilos/` y correr `python3 estilos.py construir`.
- Lecturas filtradas por `cliente`.

## Review Focus

1. Un proyecto sin Catálogo (o con el Catálogo vacío): todo va al handle o a «Otros», sin error.
2. Un anuncio con `destino_url` vacío o sin `/products/` y nombre de un solo carácter: «Otros», sin error.
3. Periodo de 7 días sin ningún anuncio que llegue a los mínimos: las dos listas dicen por qué están vacías.
4. Anuncios con `sesiones = 0`: `cv_sesion` None, nunca división por cero ni «0 %» inventado.
5. «Todas» con varias tiendas (handles `-1`, `-2` del mismo producto): una sola fila por producto.

---

### Task 1: el cálculo puro (`triple_whale/destacados.py`) y `cv_sesion`

**Files:**
- Create: `triple_whale/destacados.py`
- Modify: `triple_whale/evaluacion.py` (`metricas`: `m["cv_sesion"]`; `resumen_cuenta`: suma `sesiones`)
- Test: `tests/test_rendimiento_destacados.py`

**Interfaces:**
- Produces: `handle(url) -> str|None`; `catalogo_indice(productos) -> dict`; `producto_de(anuncio, indice) -> {"clave",
  "nombre", "producto_id"}`; `tipo_de(anuncio, tipos) -> {"tipo", "etiqueta", "grupo"}`;
  `resumir(anuncios, roas_cuenta, indice, tipos) -> {"iterar", "conversion", "imagenes", "videos", "productos",
  "roas_cuenta", "minimos"}`; constantes `PEDIDOS_MIN_ITERAR`, `SESIONES_MIN_CONVERSION`, `PEDIDOS_MIN_CONVERSION`,
  `MAX_ITERAR`, `MAX_CONVERSION`, `MAX_POR_TIPO`, `MAX_PRODUCTOS`, `OTROS`, `TIPOS`.
- Cada fila de las listas: `{"canal", "ad_id", "nombre", "m", "producto", "tipo", "etiqueta", "grupo", "creatv",
  "video_url"}`; cada producto: `{"clave", "nombre", "producto_id", "gasto", "ingresos", "pedidos", "anuncios", "roas",
  "es_otros"}`.

- [ ] **Step 1: pruebas que fallan** — `tests/test_rendimiento_destacados.py` con un ayudante `_a(ad_id, **campos)` que
  arma el anuncio como `evaluacion.evaluar` (`m = evaluacion.metricas(campos)`) y casos: `handle` (`-1`, guiones,
  `?variant=`, sin `/products/`, None); producto por página (`happyflops-cozy-1` → HappyCozy, `happy-cushers` →
  HappyCushers, `happyflops-1` → HappyFlops Original), por nombre (gana el más largo), handle fuera del Catálogo, «Otros»;
  suma del gasto de los productos = gasto de todos; tope 10 + «Otros» con lo que sobra; iterar (borde 10 y 9,99 compras,
  ROAS igual al de la cuenta entra, menor no; `roas_cuenta` None → vacía; orden por ventas; tope 8); conversión (borde
  100/99 sesiones, 3/2,9 compras; orden por conversión; sesiones 0 no entra); tipo (image, carousel, video, dynamic con y
  sin vistas de 3 s, sin tipo con y sin vistas); top por tipo (solo con pedidos, 6 por grupo, orden por ventas);
  `metricas` da `cv_sesion` y None sin sesiones; `resumen_cuenta` suma sesiones.
- [ ] **Step 2:** `venv/bin/python3 -m pytest tests/test_rendimiento_destacados.py -q` → falla (no existe el módulo).
- [ ] **Step 3: implementar** `triple_whale/destacados.py` (código en el commit de la tarea; reglas del spec §4) y en
  `evaluacion.metricas`: `m["cv_sesion"] = _div(m["pedidos"], m["sesiones"])`; en `resumen_cuenta` agregar
  `"sesiones"` a las claves que se suman.
- [ ] **Step 4:** la prueba pasa; `venv/bin/python3 -m pytest tests -q -k "tw_ or rendimiento"` sigue verde.
- [ ] **Step 5: commit** «Rendimiento: el cálculo de las métricas que faltaban».

### Task 2: las lecturas y el panel

**Files:**
- Modify: `triple_whale/datos.py` (nueva `tipos_creativo(cliente)`), `triple_whale/destacados.py` (`armar(cliente, tw)`),
  `pestana_rendimiento/panel.py` (`"destacados"` en `contexto`)
- Test: `tests/test_rendimiento_destacados.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `datos.tipos_creativo(cliente) -> {(canal, ad_id): tipo}` (una consulta, solo filas con tipo);
  `destacados.armar(cliente, tw) -> dict` = `resumir(...)` + `"moneda"` y, en cada tarjeta de `imagenes`/`videos`,
  `"medio"` (de `triple_whale.panel.medio_tarjeta`); `panel.contexto(...)["destacados"]` = eso con fuente "tw", si no None.

- [ ] **Step 1: pruebas que fallan** (con `base_temporal`): `tipos_creativo` de un proyecto no trae los de otro;
  `armar` con una tienda sembrada (anuncios, píxel con sesiones y nc_ingresos, creativos, Catálogo) arma las listas y el
  medio; `pestana_rendimiento.panel.contexto` da `destacados` con una tienda sola y None en una mezcla con Meta.
- [ ] **Step 2:** fallan.
- [ ] **Step 3: implementar.**
- [ ] **Step 4:** pasan.
- [ ] **Step 5: commit** «Rendimiento: las métricas que faltaban llegan al panel».

### Task 3: la pantalla y el idioma

**Files:**
- Create: `templates/_rend_destacados.html` (macros `listas(d)`, `tarjetas(d)`, `productos(d)`)
- Modify: `templates/_tw_secciones.html` (`tiles_anuncios` + 2 tiles; `resto(tw, cliente, d=None)` pinta
  `productos(d)` tras «Lo que más se vende»), `templates/_rend_panel.html` (llama `listas` y `tarjetas` después de «Tus
  anuncios» con fuente "tw"; pasa `r.destacados` a `resto`), `static/estilos/pantallas/rendimiento.css` +
  `static/style.css` regenerado, `translations/en/LC_MESSAGES/messages.po` (+ `.mo`)
- Test: `tests/test_rendimiento_destacados.py`

- [ ] **Step 1: pruebas que fallan** con el cliente de prueba (`tests.test_rutas_configuracion.app`): `?entrada=NO` pinta
  «ROAS de clientes nuevos», «Tasa de conversión», «Los mejores para iterar», «Los que mejor convierten», «Mejores
  imágenes», «Mejores videos», «Productos en tus anuncios» con HappyCozy; el orden «Tus anuncios» < «Los mejores para
  iterar» y «Lo que más se vende» < «Productos en tus anuncios»; con mezcla (Meta) no aparecen; las consultas del panel no
  crecen de 6 a 30 anuncios; las listas vacías dicen su motivo; el `<video>` lleva `preload="none" data-precarga`.
- [ ] **Step 2:** fallan.
- [ ] **Step 3: implementar** macros, tiles, CSS (`python3 estilos.py construir`), catálogo (`venv/bin/python3
  catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md`, `compilar`).
- [ ] **Step 4:** pasan; suite completa `venv/bin/python3 -m pytest -q` verde.
- [ ] **Step 5: commit** «Rendimiento: la pantalla de las métricas que faltaban».

### Task 4: guía, revisión, prueba con datos reales y despliegue

- [ ] Skill `rendimiento`: sección «Las métricas que faltaban (2026-10-13)»; skill `triple-whale`: `tipos_creativo` y
  `destacados.py`.
- [ ] Captura del panel con una copia de la base de producción (Noruega) en local, escritorio y 375 px.
- [ ] Revisor con contexto limpio contra el spec, con mutaciones (`-<dígitos>`, mínimo de pedidos, orden por conversión,
  grupo de video).
- [ ] Merge de `origin/main`, suite verde, push a main, despliegue (solo `iaplusyou`: si el diff no toca nada que el
  worker importe; `triple_whale/evaluacion.py` sí lo importa el worker → los dos, con la cola vacía), humo, memoria.
