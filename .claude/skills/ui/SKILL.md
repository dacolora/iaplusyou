---
name: ui
description: "Pantallas de Creatv: el sistema de static/estilos/ y la base visual común, el celular, las tarjetas ligeras con detalle por fetch, las barras de progreso con data-poll-job y las reglas de rendimiento de la página del proyecto. Cargar antes de agregar o cambiar una pantalla, una tarjeta, una lista, una barra de progreso, o tocar cliente.html, base.html o style.css."
---

# Pantallas: base visual, celular y rendimiento de la página

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Sistema de estilos (2026-10-02, pedido de Daniel: el azul de la referencia en toda la plataforma y un lugar
para cambiar el diseño):** `static/estilos/` es la fuente; `static/style.css` es generado y se guarda en git.
Edita la carpeta y corre `python3 estilos.py construir`; `test_la_hoja_es_la_generada` falla si se edita la hoja a
mano, y `python3 estilos.py comprobar` verifica que esté al día. `ORDEN` une las capas: `tokens.css`, `legado/`
en su número, `base.css`, `componentes/`, `pantallas/`. Los valores de diseño nuevos van en `tokens.css`; los
colores literales restantes de `legado/` son la excepción transitoria: solo se vacía, con el trinquete
`TECHO_COLORES_LEGADO` en `tests/test_estilos_sistema.py` (199 al cerrar la entrega 1). Los estilos en línea
sin colores tampoco crecen (`TECHO_ESTILOS_EN_LINEA`: 414). Un componente nuevo lleva archivo en `componentes/`,
macro en `templates/_componentes.html` si tiene marcado, sección `data-componente="<nombre>"` en la Guía
`/admin/estilos` y una línea aquí. Cada CSS nuevo empieza con un comentario de uso, emplea tokens y se enumera
una sola vez en `ORDEN`; sin `@import`. `base.css` respeta `prefers-reduced-motion` y pinta los enlaces sin clase
con `:where(a) { color: var(--accent-texto) }` (sin ella Chrome los deja lila y, visitados, morados); un `<button>`
con clase que no pinta su fondo queda con el gris del navegador: dale fondo o súmalo al secundario de la base
visual (como `.menu-movil` y `.au-filtro`). Las animaciones se limitan a `ANIMACIONES_PERMITIDAS` y el pulso nuevo
a elementos vivos. El editor usa `--fondo-video` detrás del
reproductor y `--fondo-lienzo` en el canvas, sin brillos: la paleta de la interfaz no cambia los colores que se
renderizan dentro del video (spec §12).

**UI base** (2026-09-25/26, specs `2026-09-25-base-visual-comun` and `2026-09-26-movil`): the
block «Base visual común (2026-09-25)» in `static/estilos/legado/03-base-visual-comun-2026-09-25-spec.css`
(or its component after migration) is the source of truth for
fields, labels, buttons (`.btn-generar` = primary with white text; `.btn-sm`/`.btn`/classless
`button` = secondary), `summary`, the tab header (`.panel-cabecera` > text div with `h2` +
`.panel-cabecera-desc`, plus `.panel-cabecera-acciones`) and `.estado-vacio`; new screens reuse
those instead of new one-off styles. `cliente.html` switches tabs on `hashchange` and scrolls to
top; `data-abrir-detalle="<details id>"` opens a `<details>`. Up to 760 px the sidebar leaves the
screen and opens with «☰ Menú» (`body.menu-abierto`); nothing may scroll the page sideways
(`tests/test_base_visual.py`, `tests/test_movil.py`). **Crear in the sidebar** (2026-10-08, feedback Daniel received: it had to stand out more than the other tabs): `_sidebar.html` puts Crear first, apart, as a filled blue button (`.sidebar-item.sidebar-crear`, still `data-tab="creativeflowplus"`, rules in `static/estilos/base.css`, text `--sobre-accent`); the tab list still starts with Experimentos, the default tab (without Meta the page opens in Crear, `cliente.html`; `tests/test_rutas_tablero.py`). Its hover/open state uses a short glow and a ring, never `--shadow-glow`: the 28 px glow spilled onto the next row and Experimentos looked selected. Phone review of every screen (2026-09-28, CSS block «Celular: revisión de pantallas» in `static/estilos/legado/07-celular-revision-de-pantallas-2026-09-28.css`): auto-fill grids use `minmax(min(100%, X), 1fr)` (never a bare fixed minimum — a test rejects it), card galleries (Crear, Final edition, Experimentos, Referentes) are 2 columns ≤ 760 px, button/filter rows (`.acciones`, summaries) wrap, long ids/JSON/URLs break instead of pushing the page, and data tables (`tabla-admin`, `tabla-tiendas`, `tabla-productos`, `gasto-tabla`, `sprint-entrega`, `gpg-tabla`, or opt-in `tabla-apilada`) become one card per row ≤ 640 px with each value labelled from its column header (`static/tablas.js` copies the `<th>` text to `data-etiqueta`, also for tables inserted later by fetch); `.solo-teclado` hides keyboard-only hints on touch screens. Crear's «Desde referencias» form is a **composer**
(spec `2026-09-27-crear-compositor`, CSS block «Crear: compositor»): a card whose top half is the bandeja
(OUTSIDE `#form-flowplus`, it carries its own `<form>`s) and whose bottom half is the form, with a bar of pills
whose menus hold the real radios/selects — the selects stay the hidden source of truth and the menus draw chips
from them —, so the POST to `cf_crear_video` is unchanged; upload/link inputs reach their empty outside forms via
`form=`, the catalog opens as a `<dialog>` (`_selector_productos.html` with `sel_dialogo=True`; «Cambiar producto»
keeps its `<details>`), and Enter in a one-line input never submits it (it used to generate and charge).

**Final edition y la paleta global** (2026-10-02: Daniel pidió «un branding de este estilo» con una
referencia tecnológica — azul marino, azul eléctrico con brillo, números en círculos, íconos en recuadros,
flujo con flechas): la paleta vive en `tokens.css` para TODA la app; Final edition ya no redefine variables
dentro de `#tab-final`. Sus reglas propias siguen en `legado/11-final-edition-tablero-2026-10-02-daniel.css`
hasta la entrega de componentes comunes. Las superficies siguen oscuras (`test_modo_oscuro`: luminancia
≤ 0,05) y `--cian`, que pasa de 0,4, va solo en texto, trazos SVG y sombras. Íconos: macro `icono_fe(nombre)` de `_final_macros.html` (SVG en línea, `currentColor`). Ojo con los
nombres de selectores en el JS de una plantilla: `tests/i18n_util.py` lee como español suelto un literal con «en»,
«nueva», «de»… (por eso `#fe-editando` y `data-fe-elegir`). Un panel oculto del navegador integrado no pinta cuadros
de `<video>` en las capturas: miniaturas negras ahí no son un error (comprobar `readyState`).

**Rendimiento y almacenamiento (auditoría 2026-09-28, tras el incidente de la página que se
quedaba cargando):** `/cliente/<c>` trae todas las pestañas en un solo HTML (3 MB en happyflops:
Crear, Final edition y Experimentos repiten las mismas piezas con sus `<template>` de detalle), así
que lo que se agrega ahí le cuesta a TODAS las cargas. Reglas que salieron de la auditoría: los
`<video>` de listas nacen `preload="none" data-precarga` (base.html los pide al entrar en pantalla;
`tests/test_referentes_copycoders_proyecto.py` rechaza `preload="metadata"`) y las `<img>` van
`loading="lazy"`; las fotos del catálogo se piden con `?w=320` (`catalogo_productos.miniatura`,
Pillow, caché en `data/miniaturas/`); nada de una consulta por tarjeta: `ver_cliente` corre bajo
`trabajos.con_vivos_precargados` (UNA lectura de los job_ids vivos para todos los `en_curso`) y la
lista de Crear usa `creative_flow.guiones_base`/`finales_por_sesion` y
`doctrina.revisor.ultimos_captions` (`tests/test_perf_pagina_proyecto.py` falla si el número de
consultas vuelve a crecer con las piezas); `informe.completo` solo se arma para el admin; los
estáticos con `?v=` salen `immutable` un año (`/static/editor/` sigue `no-cache`); la biblioteca de
copycoders está apagada por proyecto hasta que la persona la trae (`proyectos.referentes_copycoders`).
Mantenimiento diario en el worker (`tareas/mantenimiento.py`): `salidas_limpiar` borra de `salidas/`
lo que tenga más de 14 días (todo lo de ahí es copia de trabajo: el video vive en R2 y
`publicador.archivo_local`, `final_edition._clon_local`, `materiales.descargar` y `sprints.qa`
lo vuelven a bajar), `cola_limpiar` purga las `tarea` cerradas (7 días; periódicas, 1 día) y
`db_respaldar` guarda `data/respaldos/creatv_<fecha>.db` (`Connection.backup`, 7 copias). Sigue
pendiente (no se hizo): borrar en R2 lo rechazado/descartado y las versiones viejas de finales,
`materiales_limpiar` no borra nada porque los proxies viven en la fila del video (no son `EFIMEROS`),
`metrica_snapshot` inserta cada 2 h aunque nada cambie.
**Tarjetas ligeras y detalle bajo demanda** (spec
`docs/superpowers/specs/2026-09-28-tarjetas-ligeras-detalle-bajo-demanda-design.md`): el 61 % de
la página eran los `<template class="generado-detalle">` de Crear y Final edition (1,86 MB de 3,03).
Ya no existen: las tarjetas son macros (`_crear_tarjetas.html`: `tarjeta_crear`/`lista_crear`;
`_final_tarjetas.html`, desde el tablero del 2026-10-02: `tarjeta_pieza_fe`/`tarjeta_final_fe`/
`tarjeta_elegir_fe` y sus `lista_*_fe`), la página pinta las 24 más recientes por lista
(`TARJETAS_POR_PAGINA`, `_listas_crear` y `_tablero_final`; los contadores muestran el total) y «Ver más»
pide las siguientes a `crear_tarjetas` / `final_tarjetas?lista=en_edicion|finalizados|elegir`
(`?desde=N`, `_pagina_desde`). El detalle llega por fetch al
abrir la tarjeta (`data-detalle` → `cf_detalle`, `fe_detalle_video`, `fe_detalle_final`; macros en
`_crear_detalle.html` / `_final_detalle.html`, armadas con `_creative_flow_item(cliente, cf_id)` y
`_contexto_final_edition(cliente)`, que incluye `_contexto_organico`), nunca se cachea, y
`base.html` lo pinta con `abrirDetalleRemoto(modal, cuerpo, url, alInsertar)` («Cargando…» al
instante, solo el último pedido gana). `#final?cf=<id>` abre la pieza aunque no esté pintada.
Reglas: **ninguna barra de progreso lleva `<script>`** — todas `data-poll-job="<job_id>"` sobre el
`div.barra-progreso#trabajo-<job_id>` y `arrancarSondeos(raiz)` (DOMContentLoaded + el
MutationObserver de `data-precarga`) arranca el sondeo de lo que aparezca; los clics de tarjetas
van delegados sobre la cuadrícula (las agregadas por «Ver más» funcionan igual); el sondeo se pausa
con `document.hidden` y baja de ritmo (`intervaloSondeo`: 1,5 s → 3 s al minuto → 5 s a los 5 min).
`tests/test_tarjetas_ligeras.py` y `test_perf_pagina_proyecto.py` vigilan todo esto. Fuera de
alcance (anotado en el spec §7): el JS embebido a estáticos, Experimentos por fragmentos (**hecho el
2026-10-03**: ver «Experimentos: armazón + fragmento»; Catálogo ya carga su galería y su ficha por fragmento desde
2026-09-30: ver «Catálogo ecommerce y conectores»), el chequeo de Meta en la carga, los N+1 de Sprints/Experimentos
(el de últimas métricas en `experimentos.cargar` se retiró en PND-134, 2026-10-07), el flujo viejo «Nueva idea».

**Barra que avisa en vez de recargar** (2026-10-08, tarjetas de Triple Whale): `iniciarPolling` recarga la página al
terminar, y con diez barras vivas en una lista serían diez recargas. Una barra con `data-poll-al-terminar="evento"`
despacha `trabajo-terminado` (`bubbles`; `detail.estado` y `detail.mensaje`; también si se pierde el rastro o la
conexión) y quien la pintó repinta solo lo suyo; la lista que llega por fetch llama a `arrancarSondeos(raiz)` con lo
insertado, y la barra de una tarjeta repintada vuelve a sondear porque la clave `job|id` solo bloquea mientras la barra
que la marcó siga en la página. Sin el atributo todo sigue igual (skill `triple-whale`).

**Experimentos: armazón + fragmento** (E2, 2026-10-03; skill `experimentos`): `#tab-experimentos` solo pinta el armazón
(`_tab_experimentos.html`). Los resultados llegan por `fetch` a `exp_resultados` (fragmento `_exp_resultados.html`, con el filtro
en el hash), el panel de una pieza a `exp_pieza` (`<dialog id="cr-panel">`, `_exp_pieza.html`) y «Nuevo experimento» es una
página aparte, `exp_nuevo`, a pantalla completa con «← Volver a resultados». Por eso el HTML de `/cliente/<c>` ya NO trae las
piezas elegibles (la galería), el tablero ni la gestión por experimento: lo que Experimentos necesite pintar se agrega al
fragmento, no a la página (la regla de «Rendimiento y almacenamiento»: lo pesado llega por fragmento). Sus estilos viven en
`static/estilos/pantallas/experimentos.css` (clases `cr-*`: el fragmento, el panel y la gestión) y
`pantallas/experimento-nuevo.css` (la página nueva); las `exp-*` viejas siguen en `legado/` hasta que se vacíe.
`static/style.css` es GENERADO: se reconstruye con `python3 estilos.py construir` y no se edita a mano. Reglas que ya cumple y
que no hay que romper: los `<video>` nacen `preload="none" data-precarga` y las `<img>` `loading="lazy"`; la barra de progreso
de un experimento lleva `data-poll-job` (nunca `<script>`); nada de una consulta por tarjeta (`tests/test_rutas_resultados.py`
mide el fragmento); en el celular los gráficos SVG escalan por `viewBox` y las tablas son `tabla-apilada`; los colores van por
tokens (`--ok`, `--error`, `--warn` y sus `-fondo` para mejor, peor y recuperándose; `--serie-N` para series; `--cian` solo en
texto, trazos y sombras) y siempre con ▲/▼, porque el significado no puede depender del color. El JS no pasa por Jinja: sus
textos viajan en `#cr-textos` (JSON) ya traducidos por el servidor.

**Alertas en pantalla** (2026-10-02, skill `alertas`): el centro de resultados de Experimentos (que absorbió el Tablero el 2026-10-03) no lista alertas, solo una línea («N alertas necesitan tu atención → Ver Alertas», `.cr-alertas-linea` en `_exp_resultados.html`); la lista vive en la pestaña Alertas (`_tab_alertas.html`, `#alertas`) y la burbuja del sidebar sale de `alertas_ctx`, el mismo dato del context processor `_alertas_sidebar`, que se calcula en cada página (caché de 60 s): una consulta por tarjeta ahí cuesta en todas las pantallas.

Precios del compositor y clon (2026-10-02, PND-011/016): el JS recibe tarifas y tablas calculadas en servidor; no duplica el precio del proveedor. La tarifa de música viene del servidor, desde gastos.costo_musica_estimada. La tabla de clon se cachea por proceso y varía con nombre e idioma antes del clic; se refresca también al vaciar el nombre después de clonar (revisión 2026-10-02).

PND-028/031/044 (2026-10-03, lote 2): «Versión A» requiere una hija B real; los enlaces de los diálogos de Referentes cierran el diálogo antes de cambiar de pestaña. Experimentos conserva la selección por pieza/país al reconstruir la cuadrícula y cuenta cero casillas sin sustituirlo por el total. Pruebas renderizadas con Node; la revisión visual a 375 px sigue a cargo del integrador.

PND-130/133 (2026-10-05, lote 4): en celular las cifras de Final edition colocan el icono encima para que la etiqueta use todo el ancho, sin cortar palabras: overflow-wrap normal solo dentro de @media max-width 760px; escritorio y .fe-flujo small conservan anywhere (revisión de Codex, 2026-10-05). El detalle remoto rechaza respuestas redirigidas (sesión vencida) antes de leer su HTML; conserva el aviso de error y no arranca sondeos. La revisión visual a 375 px la hace Claude.

**Enlace directo a Crear (2026-10-07, PND-120):** `#creativeflowplus?cf=<id>` abre el detalle remoto también si la
sesión queda fuera de las 24 tarjetas iniciales. El script del modal atiende carga y `hashchange`, valida el id y usa
la ruta `cf_detalle` existente, con su guardia de proyecto. `tests/test_tarjetas_ligeras.py` ejecuta el script renderizado
en Node con 30 sesiones y prueba 200/404 entre proyectos. La comprobación visual queda para Claude: Codex no abrió navegador.

PND-095/136/100 (2026-10-07, lote 5 B): acciones de voz fuera del role=radio con contenedor; foco del filtro se restaura tras reemplazar el fragmento; el fondo del panel cierra solo fuera de sus límites; popstate y cambios de filtro dentro de la misma pestaña conservan scroll; exp-minimo anuncia cambios. Se retira .regla-nombre code y se regenera style.css. El mapa es documentación interna generada por AST; su barra sigue por catálogo. Verificación de código con Flask/Node y dobles; inspección visual a cargo de Claude (encargo sin navegadores).

Correcciones del lote 5 (2026-10-08, pedido de Daniel): ESTRUCTURA.md y mapa_codigo.html conservan el mapa en llano de ecef5555 hasta la decisión PND-100. mapa_codigo_generar exige --salida aparte, solo lee fuentes versionadas y escapa también llaves en textos dinámicos; el estilo se compara con la plantilla del disco. El aviso exp-minimo y Usar ese total son hermanos dentro del único resumen vivo exp-resumen; el call de la plantilla coloca ambos juntos y anuncia el propio aviso, sin aria-live añadido. Las pruebas antiguas de modo oscuro y resumen único no se modifican.

**Precios con margen (cobros, 2026-10-08, spec `2026-10-08-cobros-saldo-prepagado` §6):** en un proyecto que cobra, toda cifra en dólares que la persona ve ANTES de gastar es precio (costo × margen), también para el admin en los botones. En plantillas: todo `data-usd*`/`data-recargo` y toda tarifa visible van por el filtro `|precio` (`{{ m.usd_por_segundo_efectivo|precio }}`, `{{ est.usd|precio|usd }}`); el `texto` de `gastos.estimar` ya llega con margen (`gastos.texto_precio`) y en Python se usa `gastos.precio(usd)`. Al navegador de un proyecto que cobra nunca le llega el costo (ni en un hidden, ni en `data-gpg-cuerpo`, ni en un JSON junto al texto): lo que vuelve para compararlo o cobrarlo (`total_visto`, `precio_visto`) es el precio que vio, y la ruta lo pasa a costo UNA vez con `gastos.costo_de_precio` antes de comparar (tolerancia de redondeo) o pedir saldo. El filtro lleva `pass_context` porque Jinja 3.1 resuelve al compilar todo filtro sobre una constante salvo los que piden el contexto (`pass_eval_context` NO basta): `{% if (1|precio) == 1 %}` quedó fijo con el margen de la primera petición (visto el 2026-10-08); para preguntar si hay margen, `margen_precio() == 1`. El margen se lee una vez por petición (`g.margen_precio`) y solo si algo pinta un precio. Lo ya gastado («costó», «gastado», Configuración › Gasto) no pasa por aquí: es lo cobrado del libro (`cobros.vista`, skill `cobros`). **Lo ya gastado (cobros 8/11, 2026-10-08):** toda cifra de algo ya pagado por una pieza va por el filtro `|cobrado(clave)` (`{{ item.usd|cobrado(item.tipo ~ ':' ~ item.id) }}`, `final:<id>`, `swap:<id>`, `tw_eval:<id>`; la clave es la referencia del gasto sin `:t<n>`): a quien no es admin en un proyecto que cobra le da lo cobrado del libro (None si nada) y a los demás el costo; sin clave (un desglose de costo, como las capas de una final) da None a ese cliente. `{% if ver_cobrado() %}` pregunta lo mismo. Los totales armados en Python pasan por `cobros.vista.gasto_para` / `suma_vista` / `cobrado_donde`, que leen las filas cobradas UNA vez por petición (nunca una consulta por tarjeta). Configuración › Saldo (`#config-ap-saldo`) solo trae un contenedor `data-saldo-panel`: `static/cobros.js` (lo carga `base.html` en toda página de un proyecto) pide el fragmento al abrir el apartado, sondea la vuelta del pago por `data-estado-url` y pinta el aviso `.aviso-sin-saldo` con «Recargar saldo» ante CUALQUIER fetch que reciba el 402 `saldo_insuficiente` (envuelve `window.fetch` una vez; las pantallas siguen pintando su `error`). `cliente.html` abre Configuración con cualquier ancla `#config-…`. Sus estilos: `pantallas/saldo.css`. **/admin/cobros (cobros 10/11, 2026-10-08):** `admin_cobros.html` reusa `hero`, `admin-bloque`, `admin-scroll` + `tabla-admin` (11 columnas: en escritorio la tabla se desplaza dentro de su caja; ≤ 640 px `tablas.js` la apila) y `flash warn`/`flash error` para los avisos de Bold; sus pocas reglas (`cobros-admin-*`) viven al final de `pantallas/saldo.css`. Un `<input>` dentro de una celda de `tabla-admin` necesita `min-width`: con `max-width: 100%` la columna auto lo encoge y corta el placeholder (visto en la captura del 2026-10-08). **Planes en /admin/cobros (planes 7/8, 2026-10-10):** dos tablas más (`#cobros-planes`, `#cobros-suscripciones`); la de planes por proyecto lleva `cobros-admin-planes`, que deja envolver el texto (con el `nowrap` de `cobros-admin-tabla` la columna de acciones quedaba fuera de la caja a 1366 px) y fuerza los formularios de su `<details>` a `minmax(0, 1fr)` (un `<select>` con opciones largas ensanchaba la celda). Visto en escritorio (1366) y a 375 px con el método «ver la UI sin contraseña».


PND-076/095/124 (2026-10-08, decisiones delegadas): accesos bloqueados reutiliza hero/admin-bloque/tabla-apilada/tabla-admin y data-etiqueta, sin CSS ni colores propios. Audios pagina por 24 con un botón delegado, separado de las tarjetas por el contenedor común acciones (R8, 2026-10-08) y conserva descarga/borrado de las tarjetas agregadas. El fragmento de lista no lleva scripts; el JS permanece en la plantilla completa. Alertas oculta las acciones protegidas sin ocultar sus avisos de plata. Las pantallas a 375 px y escritorio las mira Claude, por el encargo sin navegadores.

**Configuración › Plan (planes 6/8, 2026-10-10, skill `cobros`):** como el saldo, el apartado `#config-ap-plan` solo trae un contenedor y `static/planes.js` pide el fragmento al abrirlo; el formulario de alta (`plan_alta.html`) es la única página con el widget de Wompi. Estilos en `pantallas/planes.css`; las barras son `<progress class="plan-barra">` (sin `style=` en línea, que tiene techo). Un `<a class="btn-generar">` no hereda el relleno de `<button>`: en esas pantallas lo pone `planes.css`; y `.vacio` trae `padding: 1rem 0`, así que las notas cortas del formulario usan `.plan-ayuda`. Visto en escritorio y a 375 px con el método «ver la UI sin contraseña».
