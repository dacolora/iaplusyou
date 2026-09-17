# Unificar Productos en Catálogo y Campañas en Experimentos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Una sola pestaña para los activos (Catálogo: personajes, productos, entornos, logos) donde un producto se crea desde la página con fotos + precio + URL de compra, se marca en prueba / prioridad y se le crea un experimento; importar (CSV/URL/tienda) queda como opción secundaria. Y una sola pestaña para anuncios (Experimentos): Campañas desaparece y los anuncios sueltos existentes se ven dentro de Experimentos, solo lectura + pausar/activar.

**Architecture:** el activo del catálogo (carpeta + `productos.json`) sigue siendo la fuente de fotos y regla; la fila `producto` (tabla del motor) guarda lo comercial (precio, moneda, url_compra, en_prueba, prioridad, fuente). Se unen por `producto.activo_catalogo_id == activo.id`; todo activo de categoría `producto` tiene su fila (fuente `manual`, `fuente_id = activo.id`) creada al vuelo (`tiendas.asegurar_manual`). La UI de Catálogo pinta ambos lados; la pestaña Productos y sus rutas de importación se reubican dentro de Catálogo. Campañas: la pestaña se quita del sidebar; `_tab_experimentos.html` incluye un bloque "Anuncios sueltos (anteriores)" con las tarjetas de `ads` (métricas, pausar/activar/actualizar); las rutas `publicar_ad`/`nueva_campana` dejan de tener UI.

**Spec:** decisión del dueño 2026-09-17 (chat): "unifiquemos todo lo de productos con lo de catálogo… lo tiene que hacer desde la página"; "no entiendo cuál es la diferencia entre campañas y experimentos" → una sola.

## Global Constraints
- Nada de lo existente se rompe: rutas `prod_*`, `tienda_*`, `ads`, `publicar_ad`, `cambiar_estado_ad`, `actualizar_resultados_ad` siguen funcionando (los tests existentes se adaptan solo si cambia la UI que asertan, no la ruta).
- Un activo de categoría `producto` sin fila `producto` la recibe automáticamente (fuente `manual`) al listar; nunca dos filas para el mismo activo; borrar el activo archiva la fila (no la borra).
- Producto importado sin fotos: visible en Catálogo con "Subir fotos"; al subirlas se crea el activo y se enlaza.
- Copy en español; suite verde.

---

### Task 1: Datos — activo ⇄ producto (fuente manual)

**Files:** `tiendas.py`, `catalogo_productos.py`, `dashboard.py` (`crear_producto`, `actualizar_producto`, `eliminar_producto`), tests `tests/test_tiendas_db.py`, `tests/test_rutas_productos.py`.

**Interfaces:**
- `tiendas.asegurar_manual(cliente, activo_id, nombre, descripcion="") -> producto_id`: si hay fila con `activo_catalogo_id == activo_id` devuelve su id; si no, `upsert_producto(cliente, "manual", activo_id, {...})` + `marcar_producto(activo_catalogo_id=activo_id)`.
- `tiendas.por_activo(cliente) -> {activo_id: producto_dict}` (una consulta).
- `tiendas.marcar_producto` acepta también `nombre`, `descripcion`.
- `crear_producto` (categoría `producto`): lee `precio`, `moneda` (3 letras, default moneda de la cuenta de Meta o "COP"), `url_compra` (http(s) o `wa.me`), `en_prueba`, `prioridad`; tras crear el activo y guardar fotos → `asegurar_manual` + `marcar_producto(precio, moneda, url_compra, en_prueba, prioridad)`. `actualizar_producto`: igual (actualiza la fila si existe, la crea si no). `eliminar_producto`: `marcar_producto(archivado=True)` de la fila enlazada si existe.
- Tests: crear producto con precio crea fila manual; actualizar cambia precio; eliminar archiva; `asegurar_manual` idempotente; producto importado enlazado no duplica.

- [ ] Implementar con TDD; commit `"Catálogo: cada producto del catálogo tiene su fila comercial (precio, url de compra, en prueba)"`.

### Task 2: UI — Catálogo absorbe Productos

**Files:** `templates/_tab_catalogo.html`, `templates/_catalogo_lista.html`, `templates/_tab_productos.html` (se convierte en parcial `_catalogo_importar.html` + `_catalogo_sin_fotos.html`), `templates/_sidebar.html`, `templates/cliente.html`, `dashboard.py` (contexto, `prod_*` redirigen con `_anchor="catalogo"`, nueva ruta `prod_fotos_subir`), `static/style.css`, tests `tests/test_rutas_productos.py`, `tests/test_rutas_tablero.py` (alertas `tab: productos` → `catalogo`), `tablero.py`.

- Sidebar sin `productos`; sección `tab-productos` eliminada de `cliente.html`; `data-tab` de alertas y redirecciones → `catalogo`.
- Catálogo › panel `producto`: formulario "Nuevo producto" con `precio`, `moneda` (select con las monedas de `PRESUPUESTO_MINIMO_DIARIO`), `url_compra`, checkbox `en_prueba`, `prioridad`; ayuda: "La URL de compra es adonde llega el anuncio: tu tienda, WhatsApp (wa.me/57…) o tu landing".
- Tarjeta (`_catalogo_lista.html`, solo categoría producto): línea con precio/moneda, url_compra (enlace), badge fuente (manual/csv/url/shopify/woo/meli), "en prueba", prioridad, "en N experimentos"; formulario de edición con esos campos; botón **Crear experimento** (`prod_experimento`) y, si es importado, "Sincronizado de <tienda>".
- Bloque "Traer productos de…" (`<details>`): importar CSV/Excel (con la ayuda de columnas), URL de producto, enlace a Configuración › Tienda; barra de progreso de importación.
- Bloque "Importados sin fotos (N)": productos con `activo_catalogo_id` nulo: nombre, precio, fuente, formulario "Subir fotos" (`prod_fotos_subir` POST multipart → crea activo con `catalogo_productos.crear` + fotos + `marcar_producto(activo_catalogo_id)`), botón "Crear activo desde las fotos de la tienda" (= `prod_vincular` existente), Archivar.
- "Mostrar archivados" dentro de ese bloque.
- Tests: render de Catálogo con un producto manual (precio visible), uno importado sin fotos (bloque), `prod_fotos_subir` crea activo y enlaza, redirecciones a `#catalogo`, la pestaña Productos ya no está en el sidebar.

- [ ] Implementar; verificación manual; commit `"Catálogo absorbe Productos: precio, URL de compra, en prueba y experimento desde el catálogo; importar como opción secundaria"`.

### Task 3: Campañas dentro de Experimentos

**Files:** `templates/_tab_experimentos.html`, `templates/_tab_ads.html` (→ parcial `_anuncios_sueltos.html` recortado), `templates/_sidebar.html`, `templates/cliente.html`, `dashboard.py` (redirecciones `_anchor="ads"` → `experimentos`; `nueva_campana`/`publicar_ad` siguen existiendo pero sin UI — devolver flash "Usa Experimentos" si se llama), tests `tests/test_tareas_meta.py` (rutas), `tests/test_rutas_experimentos.py`.

- Sidebar sin `ads`; sección `tab-ads` eliminada; bloque en Experimentos "Anuncios sueltos (anteriores)" solo si `ads` no está vacío: por anuncio nombre, estado, KPIs (`.kpis`), motivo de rechazo, botones pausar/activar (`cambiar_estado_ad`), actualizar métricas (`actualizar_resultados_ad`), eliminar de la lista; sin "Nueva campaña" ni "Listos para publicar" (los `en_cola` se muestran con "Este anuncio venía de Campañas: crea un experimento con esta pieza" + botón "Meter en experimento" si la pieza existe en `elegibles_exp`).
- Texto de ayuda arriba de Experimentos: "Un experimento con una pieza y un país es un anuncio; con varias piezas y países, el motor decide cuál gana."
- Tests: sidebar sin `ads`; Experimentos muestra el anuncio suelto con sus KPIs; `nueva_campana` POST → flash + redirect a experimentos sin crear.

- [ ] Implementar; verificación manual; commit `"Campañas se funde en Experimentos: anuncios sueltos anteriores en solo lectura"`.

### Task 4: Configuración = puesta a punto, y las reglas se van a Experimentos

**Files:** `templates/_tab_settings.html`, `templates/_tab_experimentos.html`, `templates/_form_reglas.html`, `dashboard.py` (`cfg_reglas` redirige a `#experimentos`; nuevo helper `_estado_llaves()`), `static/style.css`, tests `tests/test_rutas_bloque4.py` (reglas por defecto), `tests/test_rutas_productos.py` (Configuración).

Decisión del dueño (2026-09-17): "Reglas por defecto de los experimentos que está en Configuración debe estar dentro de Experimentos"; "en Configuración debemos tener el paso a paso de todas las API keys necesarias para pagar" y "cómo esto se conecta a Shopify, WooCommerce, MercadoLibre".

- **Reglas**: el bloque "Reglas por defecto de los experimentos" (`_form_reglas.html` con `prefijo="cfg"`) se mueve de Configuración a Experimentos, arriba de la lista, dentro de `<details>` "Reglas del motor (valen para todos los experimentos)". La ruta `cfg_reglas` se conserva y redirige con `_anchor="experimentos"`. Configuración deja un enlace "Las reglas del decisor están en Experimentos →".
- **Puesta a punto** en Configuración, una tarjeta por servicio, en este orden y con este contenido (todo en español, sin mostrar jamás el valor de la llave — solo "configurada" / "falta"):
  1. **Anthropic (guiones y prompts)** — `ANTHROPIC_API_KEY`; console.anthropic.com › API keys; se paga por uso (centavos por guion); sin ella no hay prompts ni guiones.
  2. **fal.ai (voz y música)** — `FAL_KEY`; fal.ai/dashboard/keys; por uso (~$0.05 por final); sin ella las finales salen sin voz ni música.
  3. **Higgsfield (video e imagen)** — `HF_API_KEY_ID`/`HF_API_KEY_SECRET`; higgsfield.ai › API; por créditos; sin ella no se generan piezas.
  4. **Cloudflare R2 (almacenamiento)** — `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_BASE_URL`; dash.cloudflare.com › R2 › Manage API tokens; casi gratis; sin ella los videos no tienen URL pública y Meta no puede usarlos.
  5. **Meta (anuncios)** — `META_APP_ID`/`META_APP_SECRET` los pone el administrador; el proyecto se conecta con el botón "Conectar con Meta" (ya existente) y la cuenta publicitaria necesita método de pago en business.facebook.com › Facturación.
  6. **Correo de avisos (opcional)** — `SMTP_HOST/PORT/USER/PASS/FROM`.
  7. **MercadoLibre (opcional)** — `MELI_APP_ID`/`MELI_SECRET`, app en developers.mercadolibre.com con redirect `<url del sitio>/meli/callback`.
  Cada tarjeta: nombre, para qué sirve, cómo se paga, estado (badge verde "configurada" / ámbar "falta"), enlace externo (`target="_blank" rel="noopener"`), y la lista de variables que van en el `.env` del servidor (con nota "las pone quien administra el servidor; no se escriben desde aquí"). `_estado_llaves()` devuelve `[{clave(s), nombre, para_que, costo, estado, url, variables}]` leyendo solo `bool(os.environ.get(...))`.
- **Conectar tu tienda** (la sección de Tienda existente gana el paso a paso, en `<details>` por plataforma): Shopify (Configuración › Apps y canales de venta › Desarrollar apps › crear app › permisos `read_products` y `read_orders` › instalar › copiar el Admin API access token `shpat_…` › pegar aquí con el dominio `xxx.myshopify.com`); WooCommerce (WooCommerce › Ajustes › Avanzado › REST API › Añadir clave, permisos de lectura › copiar Consumer key y secret › pegar con la URL https de la tienda); MercadoLibre (botón "Conectar con MercadoLibre" si `MELI_APP_ID` está; si no, qué falta). Qué trae cada una: productos y pedidos con UTM (Shopify/Woo) o solo productos (MELI, se decide por tráfico).
- Tests: Configuración renderiza las 7 tarjetas con el badge correcto según variables de entorno monkeypatcheadas; no aparece ningún valor de llave en el HTML; Experimentos renderiza el formulario de reglas y `cfg_reglas` redirige a `#experimentos`; Configuración enlaza a Experimentos para las reglas.

- [ ] Implementar; verificación manual; commit `"Configuración: puesta a punto de llaves y tiendas paso a paso; las reglas del motor se van a Experimentos"`.

### Task 5: Docs
- [ ] `CLAUDE.md`/`SETUP.md`: Catálogo como único lugar de productos (importar es secundario); Experimentos como único lugar de anuncios; Campañas/Productos solo como rutas heredadas. Commit `"Docs: catálogo y experimentos unificados"`.
