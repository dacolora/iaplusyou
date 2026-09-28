# Tarjetas ligeras y detalle bajo demanda (Crear y Final edition)

Fecha: 2026-09-28. Estado: aprobado por Daniel («ok, ejecuta todo»).
Antecedentes: incidente de la página que se quedaba cargando (2026-09-28) y la
auditoría de rendimiento del mismo día (memoria
`auditoria-rendimiento-almacenamiento-2026-09-28`, CLAUDE.md «Rendimiento y
almacenamiento»).

## 1. Problema

`/cliente/<cliente>` trae las nueve pestañas en un solo HTML. En happyflops pesa
3.030 KB sin comprimir (283 KB con gzip) y el navegador tiene que parsearlo
entero antes de mostrar nada. Medido pestaña por pestaña:

| Pestaña        | Peso      | De eso, `<template class="generado-detalle">` |
|----------------|-----------|-----------------------------------------------|
| Crear          | 1.342 KB (118 tarjetas) | 1.005 KB |
| Final edition  |   910 KB (93 tarjetas)  |   854 KB |
| Referentes     |   320 KB (ya bajó: filtro «dolor» recortado) | 0 |
| Catálogo       |   247 KB | 0 |
| Experimentos   |   126 KB | 0 |
| el resto       | < 30 KB cada una | 0 |

El 61 % de la página son los detalles de las tarjetas (el contenido del modal
que se clona al abrir una), y cada tarjeta trae el suyo aunque nunca se abra.
Las tarjetas en sí pesan ~2 KB. Además cada tarjeta con un trabajo en curso
lleva un `<script>iniciarPolling(...)</script>` propio, y las tarjetas se pintan
todas (118) de una.

Cargar las pestañas enteras por fragmentos (lo que se pidió al principio) era la
palanca equivocada: costaría reescribir ~90 KB de JS embebido de Crear, cambiar
34 archivos de pruebas y los enlaces `#pestaña?…`, y Crear seguiría pesando
1,3 MB al abrirla.

## 2. Meta y reglas fijadas

Meta, medida en happyflops: la página baja de 3.030 KB a menos de 700 KB sin
comprimir; abrir una tarjeta tarda menos de 0,3 s; cero regresión en la suite.

Reglas (rulings de esta entrega):

1. **24 tarjetas por lista.** Crear («Generados») y las dos listas de Final
   edition («Videos listos» y «Finales») muestran las 24 más recientes y un
   botón «Ver más» que trae las 24 siguientes por fetch, sin recargar. Los
   contadores de cabecera («Generados (118)», «Videos listos (93)»,
   «Finales (8)») siguen mostrando el total.
2. **El detalle se trae al abrir la tarjeta.** El modal abre al instante con
   «Cargando…» y el HTML del detalle llega por fetch. Nunca se cachea en el
   navegador: cada apertura lo pide de nuevo (el detalle trae formularios con
   estado vivo: guion, ángulo, finales en curso).
3. **Las pestañas siguen como hoy**: todas en la página, cambio instantáneo,
   mismos enlaces `#creativeflowplus`, `#final?cf=<id>`,
   `#experimentos?piezas=<id>`.
4. **Una pieza vieja sigue llegando por su enlace directo.** `#final?cf=<id>`
   abre el detalle de esa pieza aunque su tarjeta no esté entre las 24 pintadas.
5. **Ninguna barra de progreso lleva `<script>` propio.** Todas usan
   `data-poll-job` (el patrón que ya usan Final edition, Referentes y Sprints) y
   un solo observador en `base.html` arranca el sondeo de cualquier barra que
   aparezca: al cargar, al «Ver más» y al abrir un detalle.
6. **El sondeo de trabajos se pausa con la pestaña del navegador oculta** y
   baja de ritmo: 1,5 s el primer minuto, 3 s hasta los cinco minutos, 5 s
   después. Al terminar un trabajo sigue recargando la página (que ahora es
   liviana) — no se cambia ese comportamiento.

## 3. Servidor

### 3.1 Armado de piezas

`dashboard._creative_flow_items(cliente)` sigue construyendo la lista completa
de dicts de sesión (ya carga por proyecto, no por pieza, desde la auditoría). Se
extrae de su cuerpo `_armar_item_cf(cliente, cf_id, entry, data, ctx)` — el
dict de UNA sesión a partir de la sesión cargada y un `ctx` con las lecturas
por proyecto (`pieza_ids`, `guiones`, `finales_por_cf`, `captions`,
`guia_marca`, `productos_por_ids`) — y `_creative_flow_item(cliente, cf_id)`
que arma el `ctx` (las mismas funciones, una consulta cada una) y devuelve el
dict de esa sesión o `None` si no existe para ese cliente. `_creative_flow_items`
pasa a ser un bucle sobre `_armar_item_cf`. Nada cambia en el contenido del
dict.

La página sigue construyendo la lista completa una vez por carga (con 118
piezas cuesta ~0,1 s tras la auditoría; lo caro era pintarla) y recorta en la
ruta: `crear_items = items[:24]`, `final_videos = [video_listo y no imagen][:24]`,
`finales = [(item, f) por cada final][:24]`, más los totales. Constante
`TARJETAS_POR_PAGINA = 24` en `dashboard.py`.

### 3.2 Plantillas

Las tarjetas y los detalles salen de `_tab_creativeflowplus.html` y
`_tab_final.html` a macros propias, para que la página y los fragmentos pinten
exactamente lo mismo:

- `templates/_crear_tarjetas.html`: macro `tarjeta_crear(item)` (la tarjeta de
  Crear, SIN `<template>`; con `data-detalle="<url del detalle>"`) y macro
  `lista_crear(items, desde, total)` que pinta las tarjetas y, si quedan más,
  `<button type="button" class="btn-sm generados-mas" data-siguiente="<desde+24>">Ver más (quedan N)</button>`.
- `templates/_crear_detalle.html`: macro `detalle_crear(item)` con el contenido
  que hoy va dentro del `<template>` (importa `revision_doctrina`).
- `templates/_final_tarjetas.html`: macros `tarjeta_video_fe(item)`,
  `tarjeta_final_fe(item, f)`, `lista_videos_fe(items, desde, total)` y
  `lista_finales_fe(pares, desde, total)`.
- `templates/_final_detalle.html`: macros `detalle_video_fe(item)` y
  `detalle_final_fe(item, f)` (importan `editor_angulo` y `bloque_organico`
  `with context`, porque leen `paises_fe`, `voces_fe`, `estilos_fe`,
  `presets_mezcla`, `mi_musica`, `precios`, `ediciones_por_cf` del contexto).

Las barras de progreso de tarjetas y detalles llevan `data-poll-job="<job_id>"`
sobre el `<div class="barra-progreso" id="trabajo-…">` y pierden su `<script>`.
La tarjeta de Final que hoy sondea el trabajo del editor con un contenedor
oculto conserva ese contenedor (con `data-poll-job`).

Los `<template class="generado-detalle">` desaparecen de la página.

### 3.3 Rutas nuevas (todas GET, devuelven HTML de fragmento)

Viven en `dashboard.py`; `_guard_por_cliente` las protege porque la URL lleva
`<cliente>`. Responden `text/html` con `Cache-Control: no-store` (lo pone
`_sin_cache`). Un `desde` que no sea entero ≥ 0 vale 0.

| Ruta | Devuelve |
|---|---|
| `GET /cliente/<c>/crear/tarjetas?desde=N` | `lista_crear(items[N:N+24], N, total)` |
| `GET /cliente/<c>/final/tarjetas?lista=videos&desde=N` | `lista_videos_fe(...)` |
| `GET /cliente/<c>/final/tarjetas?lista=finales&desde=N` | `lista_finales_fe(...)`; otro valor de `lista` → 400 |
| `GET /cliente/<c>/creative_flow/<cf_id>/detalle` | `detalle_crear(item)`; 404 si la sesión no existe o es de otro cliente |
| `GET /cliente/<c>/creative_flow/<cf_id>/final/detalle` | `detalle_video_fe(item)`; 404 si no existe o no es un video `video_listo` |
| `GET /cliente/<c>/creative_flow/<cf_id>/final/<final_id>/detalle` | `detalle_final_fe(item, f)`; 404 si esa final no es de esa sesión |

Los detalles de Final edition necesitan el mismo contexto que hoy recibe la
página: se extrae `_contexto_final_edition(cliente)` (`paises_fe`, `voces_fe`,
`estilos_fe`, `presets_mezcla`, `mi_musica`, `precios`, `ediciones_por_cf`) de
`ver_cliente` y lo usan la página y las rutas de detalle.

### 3.4 Lo que NO cambia

Las rutas POST (`cf_generar_video`, `fe_producir`, `cf_descartar`, …) y sus
redirects con `_anchor` quedan igual. El modal de Experimentos, la galería y
Catálogo no se tocan. El contenido del detalle es el mismo HTML de hoy: solo
cambia de dónde viene.

## 4. Navegador

### 4.1 `base.html`

- `arrancarSondeos(raiz)`: por cada `[data-poll-job]` bajo `raiz` sin
  `data-sondeando`, marca y llama `iniciarPolling(el.dataset.pollJob, el.id)`.
  Corre sobre `document` en `DOMContentLoaded` y desde el `MutationObserver`
  que ya existe para los videos (`data-precarga`), que pasa a observar también
  `[data-poll-job]` en los nodos insertados. `iniciarPolling` conserva su
  propia deduplicación por `jobId|contenedorId`.
- `iniciarPolling`: el intervalo sale de `intervaloSondeo(inicio)` (1.500 ms
  antes de 60 s, 3.000 ms antes de 300 s, 5.000 ms después). Si
  `document.hidden`, `tick` no consulta: se registra un `visibilitychange`
  que reanuda con un `tick` inmediato al volver. Los reintentos por error
  (2 s, máximo 6) y el resto del comportamiento no cambian.

### 4.2 Modales de Crear y Final edition

Un helper compartido en `base.html`, `abrirDetalleRemoto(modal, cuerpo, url, alInsertar)`:
pone «Cargando…» en `cuerpo`, abre el modal, hace `fetch(url, {headers:
{'X-Requested-With': 'fetch'}})`, y si la respuesta sigue siendo la última
pedida (contador por modal) reemplaza `cuerpo.innerHTML`, corre
`arrancarSondeos(cuerpo)` y `alInsertar(cuerpo)` (Final: `iniciarEditoresAngulo`).
Si falla: «No se pudo cargar el detalle. Recarga la página.». Cerrar el modal
vacía el cuerpo (como hoy) e invalida el contador.

Crear y Final delegan sobre su contenedor (`#creativeflowplus-resultados`,
`#tab-final`): `click`/`keydown` en `.generado` → `abrirDetalleRemoto(...,
card.dataset.detalle, ...)`; `mouseover`/`mouseout` reproducen y pausan el
video de la tarjeta (con `relatedTarget` para no repetir al mover el mouse
dentro de la tarjeta); `click` en `[data-siguiente]` → fetch de
`…/tarjetas?desde=N` y `insertAdjacentHTML('beforeend')` de las tarjetas sobre
la cuadrícula, reemplazando el botón. Los `<video data-precarga>` y las barras
nuevas los recogen los observadores.

`#final?cf=<id>`: `desdeHash` abre la tarjeta si está pintada; si no, llama
`abrirDetalleRemoto` con la URL del detalle construida desde el id. El resto
del JS de los modales (costo A+B, «Producir N finales», confirmación de
reemplazo) ya está delegado sobre el cuerpo del modal y sigue igual.

### 4.3 Textos nuevos

«Ver más (quedan %(n)s)», «Cargando…», «No se pudo cargar el detalle. Recarga la
página.» pasan por `_()` / `|tojson` y al catálogo (`catalogo_i18n.py
actualizar` + traducir + `compilar`).

## 5. Pruebas

`tests/test_tarjetas_ligeras.py` (siembra sesiones con
`creative_flow.crear/actualizar/crear_final`, como `test_perf_pagina_proyecto.py`):

- Con 30 videos listos y 3 finales: la página no contiene
  `<template class="generado-detalle">` ni `iniciarPolling(` embebido en
  tarjetas; la cuadrícula de Crear tiene 24 `.generado` y un
  `[data-siguiente="24"]`; «Generados (30)»; Final: 24 videos + botón,
  «Videos listos (30)», «Finales (3)» sin botón.
- `…/crear/tarjetas?desde=24` → 6 tarjetas y sin botón; `desde=abc` → como 0;
  `…/final/tarjetas?lista=x` → 400.
- Detalle de Crear: 200 con «Descargar», el formulario `fp_reusar` y
  `revision_doctrina` cuando aplica; 404 para un id inexistente y para el de
  otro cliente (sesión sembrada bajo `otro`).
- Detalle de video en Final: 200 con «Producir finales» cuando hay guion y con
  «Preparar guion» cuando no; 404 para una imagen. Detalle de final: 200 con
  «Capas»; 404 con un `final_id` de otra sesión.
- Una sesión `video_generando` con tarea viva: la tarjeta trae
  `data-poll-job` y no `<script>`.
- Contrato del JS (lectura de plantillas): `base.html` define
  `arrancarSondeos`, `abrirDetalleRemoto`, `intervaloSondeo` y consulta
  `document.hidden`; `_tab_creativeflowplus.html` y `_tab_final.html` no
  contienen `template.generado-detalle` y sí `data-detalle`.
- `tests/test_perf_pagina_proyecto.py` gana la comprobación de que con 40
  piezas ninguna cuadrícula pasa de 24 tarjetas y no hay `<template>`.

Pruebas existentes que buscaban el detalle dentro de la página
(`test_tab_final.py`, `test_rutas_final_edition.py`,
`test_rutas_crear_director.py`, `test_rutas_mi_musica.py`,
`test_tareas_doctrina.py`, `test_rutas_configuracion.py`) pasan a pedirlo a su
ruta de detalle; la afirmación no cambia, solo de dónde sale el HTML.

## 6. Entrega

Rama `tarjetas-ligeras` desde `main`. Prueba real antes de desplegar: en el VPS,
con el test client sobre la base real de happyflops, medir el tamaño de
`/cliente/happyflops`, el tiempo de cada detalle y que los tres fragmentos de
«Ver más» devuelvan lo que falta; y en el navegador, abrir una tarjeta de Crear
y una de Final y verificar que el modal se llena y que «Ver más» agrega
tarjetas. Despliegue: solo cambia código del dashboard y plantillas
(`systemctl restart iaplusyou`; el worker no se toca).

## 7. Fuera de alcance (anotado para después)

- Pasar los ~300 KB de JS embebido en las pestañas a archivos estáticos
  cacheables.
- Cargar Catálogo (247 KB) o Experimentos (126 KB) por fragmentos.
- El chequeo de Meta (`meta_conexion.estado`, una llamada a Graph con 5 s de
  tope cada 10 min) durante la carga.
- Los N+1 de Sprints y Experimentos (invisibles con 6 sprints y 3 experimentos).
- El flujo viejo «Nueva idea» (`_ideas_pendientes`, `videos`, `log`) que
  `ver_cliente` sigue calculando.
- Restaurar la expansión de «Ver más» tras la recarga automática de un trabajo.
