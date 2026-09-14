# Motor de ecommerce — diseño

Fecha: 2026-09-14. Estado: aprobado por secciones en conversación; pendiente de revisión escrita.

## 1. Propósito

Convertir Creatv Machine en una máquina de creativos para productos de ecommerce:
a partir de un producto y un video referente (un ad que ya funciona), generar un
clon con nuestro producto, producir versiones finales con texto, voz, música y
cortes por idioma y país, publicarlas en Meta, medir tráfico y ventas, declarar
ganadores y perdedores, derivar variantes del ganador y rescatar al perdedor por
escalera — con tres modos de autonomía elegibles por el cliente (manual,
semiautomático, piloto automático).

Enfoque elegido: **motor de experimentos con cola persistente** (SQLite + worker
propio), construido al lado del dashboard actual, que sigue funcionando.

Decisiones tomadas con Daniel:
- Ganador se decide en cascada: tráfico como filtro rápido, ventas como verdad final.
- Los tres modos de autonomía existen y se eligen por experimento.
- Final edition completa desde la primera versión: texto + voz + música + cortes,
  por idioma y país; la IA escribe el guion y el cliente puede editarlo.
- Todas las fuentes de catálogo: Shopify, WooCommerce, MercadoLibre, CSV, URL,
  alta manual (WhatsApp/Instagram).
- Rescate del perdedor en escalera: re-edición → re-edición → regeneración → archivar.
- Ganador: derivados configurables, default 3 re-ediciones + 2 regeneraciones.

## 2. Modelo de datos (SQLite)

Base única `data/creatv.db` (WAL), SQLAlchemy Core, migraciones Alembic. Todas
las tablas llevan `cliente` (id de proyecto), `creado_en`, `actualizado_en`.

### producto
`id, cliente, fuente (shopify|woo|meli|csv|url|manual), fuente_id, nombre,
descripcion, precio, moneda, url_compra, fotos (json[]), categoria,
activo_catalogo_id (enlace al catálogo de Crear), prioridad (int),
en_prueba (bool), archivado (bool)`.

### concepto
`id, producto_id, origen (referente_link|ganador_derivado|rescate|manual),
referencia_url, referencia_frames (json[]), referencia_transcripcion, enfoque
(producto|persona|unboxing), guion_base (json, ver §3.0), idioma_base,
padre_concepto_id, motivo_archivo, archivado`.

### pieza
`id, concepto_id, tipo (clon_limpio|final), idioma, pais, modelo, url_video,
url_miniatura, duracion_s, aspect_ratio, capas (json: por capa {proveedor,
parametros, costo_usd, estado, error}), costo_usd, estado
(pendiente|generando|listo|error|degradada), padre_pieza_id (la final apunta
a su clon), guion (json, copia localizada del guion_base)`.

### experimento
`id, producto_id, nombre, modo (manual|semi|auto), reglas (json, ver §5),
paises (json[] de {pais, idioma, presupuesto_dia}), moneda, tope_total,
dias, objetivo_meta (OUTCOME_TRAFFIC|OUTCOME_SALES|OUTCOME_APP_PROMOTION),
atribucion (pixel|tienda|ninguna), estado
(armando|esperando_aprobacion|corriendo|decidido|cerrado), meta_campaign_id,
gasto_acumulado`.

### experimento_pieza
`id, experimento_id, pieza_id, pais, meta_adset_id, meta_ad_id,
meta_creative_id, estado_meta, veredicto (pendiente|ganador|perdedor|inconcluso),
veredicto_motivo, veredicto_en, escalon_rescate (0..3), presupuesto_dia_actual`.

### metrica_snapshot
`id, experimento_pieza_id, tomado_en, impresiones, alcance, frecuencia, clics,
clics_enlace, ctr, cpc, cpm, thruplay, thruplay_rate, gasto, compras,
ingresos, roas, cpa, fuente_ventas (meta|tienda|ninguna)`. El decisor trabaja
sobre snapshots, nunca sobre una lectura suelta.

### evento
`id, experimento_id, experimento_pieza_id (nullable), tipo, mensaje, datos
(json), creado_en`. Bitácora legible del loop: cada veredicto, propuesta,
acción y error.

### propuesta
`id, experimento_id, accion (publicar|activar|escalar|derivar|rescatar|pausar),
payload (json), estado (pendiente|aprobada|rechazada|ejecutada), creado_en,
resuelta_en`. Las puertas que esperan clic viven aquí.

### tarea (cola)
`id, tipo, payload (json), estado (pendiente|en_curso|hecha|error), intentos,
ejecutar_desde, iniciada_en, terminada_en, progreso (0-100), etapa, error,
cliente`.

### tienda
`id, cliente, tipo (shopify|woo|meli), credenciales (json cifrado con
FLASK_SECRET_KEY-derivada), ultima_sync_productos, ultima_sync_pedidos, estado`.

### pedido
`id, cliente, tienda_id, fuente_id, fecha, total, moneda, items (json),
utm_content (pieza_id si viene), experimento_pieza_id (resuelto)`.

Migración: `ads.json` → `experimento` "legado" + `experimento_pieza`;
`creative_flow.json` → `concepto` (origen manual) + `pieza` (clon_limpio). El
catálogo de Crear sigue en archivos; `producto.activo_catalogo_id` lo referencia.
`estado_videos.json`, `prompts_pendientes.json` y el pipeline Higgsfield no forman
parte del motor y no se migran.

## 3. Final edition por capas

Entrada: una `pieza` tipo `clon_limpio`. Salida: una `pieza` tipo `final` por
(idioma, país). Cada capa es un módulo `final_edition/<capa>.py` con la misma
interfaz `aplicar(entrada, contexto) -> (salida, costo_usd)`; el proveedor de
cada capa se elige en configuración.

**3.0 Guion (Claude).** Contexto: producto, referente (fotogramas + transcripción
Whisper; se copia la estructura, no el texto), enfoque, idioma, país. Salida
JSON: `bloques[] = {rol (hook|problema|producto|prueba|cta), texto_pantalla,
texto_voz, inicio_s, fin_s}`, con `sum(fin-inicio) <= duracion`. Se genera una
vez en el idioma base y se traduce+localiza por país (moneda, unidades, tono,
envíos). Único paso editable por el cliente en manual/semi.

**3.1 Cortes.** `ffmpeg scdet` sobre el clon; si no hay cortes naturales, se
fabrican 3-4 segmentos con zoom/velocidad (ken burns). Salida: segmentos con
tiempos, ajustados a la duración objetivo por plataforma (9:16, 6-15 s).

**3.2 Voz.** ElevenLabs multilingüe, voz por país (voz de marca opcional).
Un audio por bloque, velocidad ajustada para caber en su ventana. Salida:
pistas + marcas de tiempo por palabra.

**3.3 Música.** Biblioteca propia en R2 con licencia comercial, etiquetada por
estilo; elección por regla (categoría + enfoque), override manual. Ducking bajo
la voz.

**3.4 Texto y render.** Plantilla de marca (fuente, colores, logo de
FlowSettings): hook grande, subtítulos palabra por palabra, badge de
precio/oferta, CTA final. Render ffmpeg (ASS para subtítulos) → mp4 +
miniatura → R2.

Errores: cada capa falla sola; la pieza guarda la capa fallida y el worker
reintenta solo esa. Si voz falla tras los reintentos, la final sale
`degradada` (solo texto) y el experimento no se bloquea.

Pruebas: clip fijo de 8 s + guion fijo por capa; ffprobe valida audio+video;
el guion se valida por estructura (5 roles, tiempos dentro de la duración).

## 4. Lanzador multi-país y atribución

Estructura en Meta por experimento: 1 campaña → 1 conjunto por país (país +
idioma, presupuesto diario propio) → 1 anuncio por pieza final de ese idioma.
`lanzador.py` traduce el experimento en llamadas al submódulo `meta_ads`
(campaign/adset/creative/ad ya probados) y guarda los IDs en
`experimento_pieza`. `spend_cap` de campaña = tope total del experimento.

Objetivo según capacidades del cliente: sin Pixel → `OUTCOME_TRAFFIC`
(destino: url_compra o `/l/<cliente>`); con Pixel/CAPI → `OUTCOME_SALES`
optimizando `purchase`; app → `OUTCOME_APP_PROMOTION` (requiere app
registrada en Meta; fuera del primer bloque).

Cada URL de destino lleva `utm_source=creatv&utm_medium=meta&utm_content=<pieza_id>`.

Atribución, de mejor a peor, el experimento usa la mejor disponible:
1. Meta Insights `actions.purchase`, `action_values`, `purchase_roas` (requiere Pixel).
2. Pedidos de la tienda con `utm_content` (Shopify/Woo).
3. Ninguna → veredicto solo por tráfico, marcado "sin ventas medibles".

Chequeo de Pixel en Configuración (`act_X/adspixels` + stats) con instrucciones
por plataforma.

Métricas: el worker refresca cada anuncio cada 2 h mientras el experimento corre
(`metrica_snapshot`). Todo anuncio nace en pausa; activar respeta el modo.

## 5. Decisor y escalera

Función pura `decidir(snapshots, reglas) -> (veredicto, motivo, accion)`.

Reglas por experimento (json), con defaults por país/categoría editables:
`ventana_horas=48, impresiones_min=1000, gasto_min=2×presupuesto_dia,
cpc_max, ctr_min, thruplay_min, ventana_ventas_horas=72, cpa_max, roas_min=2.0,
n_reediciones=3, n_regeneraciones=2, escalar_pct_dia=20, escalar_tope_dia`.

Puerta 1 (tráfico): evalúa cuando hay evidencia mínima; compara cpc_enlace,
ctr, thruplay_rate con umbrales. Puerta 2 (ventas): solo si pasó la 1 y hay
atribución; cpa ≤ cpa_max o roas ≥ roas_min a ≥ 72 h.

Veredictos:
- **Ganador**: pasa ambas (o la 1 sin ventas) y está en el tercio superior de su
  país (con ≥ 3 anuncios; si no, solo umbrales). Acciones: escalar presupuesto
  del conjunto +escalar_pct_dia hasta el tope; derivar n_reediciones +
  n_regeneraciones en un experimento hijo (nunca en el mismo conjunto).
- **Perdedor**: falla la 1, o pasa la 1 y falla la 2 con evidencia. Escalera
  (`escalon_rescate`): 1) re-edición (otro hook + voz); 2) re-edición (otra
  estructura + música); 3) regeneración (otro enfoque/modelo). Cada escalón
  pausa el anterior. Si el 3 pierde, el concepto se archiva con motivo y no se
  vuelve a proponer para ese producto.
- **Inconcluso**: sin evidencia al cerrar la ventana de días → pausa, anota, no dispara.

Toda acción chequea tope del experimento y saldo de créditos antes de gastar;
si no alcanza queda como `propuesta` aunque el modo sea auto. Cada veredicto y
acción escribe un `evento` con los números.

## 6. Catálogo ecommerce y conectores

Contrato: `listar_productos() -> [ProductoNormalizado]`;
`pedidos_desde(fecha) -> [Pedido]` cuando exista. Sincronización en el worker
(productos cada 6 h; pedidos cada 2 h si hay experimentos corriendo).

Conectores, en orden: Shopify (OAuth/custom app, Admin GraphQL, pedidos con
UTM, opcional instalar Pixel con `write_pixels`); WooCommerce (REST,
`_wc_order_attribution_utm_content`); MercadoLibre (OAuth, items y pedidos,
sin UTM ni Pixel → veredicto por tráfico); CSV/Excel (columnas `nombre, precio,
moneda, url_compra, fotos`); URL de producto (scraper OG + JSON-LD); alta
manual (= catálogo actual; url_compra `wa.me/...` o landing).

Al importar, cada producto crea/actualiza su activo en el catálogo de Crear
(fotos descargadas, regla de fidelidad generada por Claude desde la
descripción). El cliente marca productos "en prueba" y prioridad; el worker
crea conceptos para los N primeros según presupuesto, no para todos.

## 7. Modos de autonomía y UI

Puertas por paso:

| Paso | Manual | Semi | Auto |
|---|---|---|---|
| Generar conceptos y clones | clic | solo | solo |
| Finales por idioma | clic | solo | solo |
| Publicar y activar (gasta) | clic | clic | solo |
| Escalar presupuesto | clic | clic | solo (tope) |
| Derivar del ganador | clic | propone | solo |
| Rescate del perdedor | clic | propone | solo |
| Pausar perdedor | clic | solo | solo |

El modo se elige al crear y se cambia cuando sea. Lo que espera clic es una
`propuesta` visible con motivo y números; existe "aprobar todo lo pendiente".

UI (misma barra lateral):
- **Productos** (nueva): tabla con fuente, precio, estado en el loop, "Conectar tienda", "Importar CSV/URL".
- **Experimentos** (evoluciona Campañas): lista con semáforo, gasto vs tope, mejor CPC/ROAS; detalle con árbol del concepto (referente → clon → finales por país → derivados/escalones) con veredicto y métricas por nodo, línea de tiempo de eventos, propuestas pendientes, subir/bajar presupuesto, pausar/activar por país.
- **Crear**: igual + "Meter en experimento" por pieza + pestaña "Final edition" (editar guion, voz, música, previsualizar por idioma).
- **Configuración**: Tienda, Pixel, Reglas por defecto, Voces y música, Idiomas/países.
- **Tablero**: gasto del mes, ventas atribuidas, ROAS, top 5 ganadoras, alertas.

Notificaciones por correo (WhatsApp después) para propuestas pendientes,
ganador nuevo y rechazos de Meta. Créditos: cada acción del worker descuenta del
saldo del cliente; el gasto en Meta va a su tarjeta.

## 8. Infraestructura y migración

- SQLite WAL + SQLAlchemy Core + Alembic. Postgres es un cambio de URL si hace falta.
- `creatv-worker` (systemd, `python worker.py`): reclama tareas con
  `UPDATE ... WHERE id=? AND estado='pendiente'`; reintentos exponenciales; tarea
  en curso > 30 min vuelve a pendiente; planificador interno para periódicas.
  `trabajos.py` pasa a encolar y la barra de progreso lee `tarea.progreso`.
- Proveedores nuevos: ElevenLabs, Whisper (`faster-whisper` local o API),
  música en R2. Claves en `.env`.
- Migración sin corte: base y worker vacíos → importar ads/creative_flow →
  Campañas y Crear leen de la base → jobs migran al worker uno a uno.

## 9. Orden de construcción

1. Cimientos: SQLite + worker + migración. Visible: generaciones sobreviven reinicios.
2. Final edition (capas 0-4) + pestaña en Crear. Visible: clon → 3 idiomas con voz y subtítulos.
3. Experimento manual: lanzador multi-país + snapshots + árbol en UI.
4. Decisor + escalera + modos semi/auto + notificaciones. Visible: el loop cierra solo.
5. Catálogo: CSV/URL, luego Shopify (Pixel + pedidos), Woo, MELI.
6. Tablero + ventas atribuidas + `OUTCOME_SALES`.

Fuera de esta versión: avatares/presentador IA, publicación orgánica del
ganador, cuentas de agencia multi-cliente en Meta, `OUTCOME_APP_PROMOTION`.

## 10. Riesgos conocidos

- App de Meta en acceso Standard: cada cliente debe ser tester hasta pasar App Review + verificación (en curso).
- Umbrales iniciales son benchmarks, no datos propios; se calibran con los primeros experimentos.
- ffmpeg en el VPS comparte CPU con gunicorn: el worker limita a 1 render simultáneo.
- Licencias de música: solo pistas con licencia comercial verificada en la biblioteca.
