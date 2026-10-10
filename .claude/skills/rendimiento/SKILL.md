---
name: rendimiento
description: "Rendimiento: la pestaña que junta Triple Whale y Meta (pestana_rendimiento/), el selector por país, la fuente de cada cifra, «Resultados» y «Por país» mezclados, «Actualizar ahora» y los alias de las pestañas viejas. Cargar antes de tocar pestana_rendimiento/, _tab_rendimiento.html, los _rend_*.html, _tw_secciones.html, _meta_secciones.html, pantallas/rendimiento.css, o al decidir de qué fuente sale una cifra."
---

# Rendimiento: Triple Whale y Meta en una sola pestaña

> Parte de la guía del repositorio. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md).
> Si el código y este texto no coinciden, manda el código: corrige el texto.

Por qué existe (Daniel, 2026-10-09): «lo que tenemos en Meta es lo mismo que tenemos en Triple Whale, esto confunde a
los clientes». Las dos pestañas daban números distintos para el mismo anuncio (ROAS 2,2× contra 3,7× en Noruega). Spec
`docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md` (reglas R1–R16 y enmiendas A1–A6), plan
`docs/superpowers/plans/2026-10-09-pestana-rendimiento-e1.md`, medición E0
`docs/superpowers/evals/2026-10-09-atribucion-happyflops.md`. La copia de datos sigue en cada paquete (skills
`triple-whale` y `meta-rendimiento`); aquí solo se lee y se decide la fuente.

## Archivos

- `pestana_rendimiento/entradas.py` (puro): entradas del selector y su fuente (R2–R5).
- `pestana_rendimiento/resumen.py`: «Resultados» y «Por país» cuando hay Meta o mezcla (R5–R8), en USD con
  `meta_rendimiento.tasas.mapa`.
- `pestana_rendimiento/panel.py`: `contexto(cliente, dias, entrada, canal, tienda=, cuenta=)` junta todo con UNA
  resolución del alcance (`_resolver`), la misma que usan los «Ver más» (`conjuntos_pagina`, `anuncios_meta_pagina`) y
  «Actualizar ahora» (`alcance_para_copias`): un «Ver más» nunca lee otras cuentas que las del panel.
- `pestana_rendimiento/rutas.py`: blueprint `rendimiento` bajo `/cliente/<c>/rendimiento`: `ver_panel` (GET `/panel`),
  `ver_conjuntos` (GET `/conjuntos`, solo `<tr>`), `ver_anuncios_meta` (GET `/anuncios-meta`, solo tarjetas) y
  `actualizar` (POST). El nombre `rendimiento/` ya era de las pruebas de carga (skill `escala-y-salud`).
- Pantalla: `_tab_rendimiento.html` (armazón + TODO el JS; el panel llega por fetch), `_rend_panel.html`,
  `_rend_macros.html`, `_rend_anuncios_meta.html`; secciones heredadas como macros en `_tw_secciones.html` e include
  `_meta_secciones.html`; estilos `static/estilos/pantallas/rendimiento.css`; la gráfica, `static/tw_resultados.js`.
  Detalle de pantalla en la skill `ui`.
- Cableado (2026-10-09, tarea 8): `_sidebar.html` (botón `data-tab="rendimiento"` donde estaba Triple Whale; Meta
  salió), `cliente.html` (`#tab-rendimiento` y el alias), `dashboard.ver_cliente` (contexto barato `rendimiento` =
  `conectado`, `hay_tw`, `hay_meta`, `n_cuentas`, `es_admin`: ni Graph ni el panel al cargar la página).

## Reglas (cada una con su motivo)

- **R1. Nombre y alias.** Clave `rendimiento`, ancla `#rendimiento`. `cliente.html` traduce las claves viejas
  `triplewhale` y `meta` (hash, `localStorage`, `redirect(_anchor=…)` viejos) con `JUBILADAS`, como `idea` abre Crear:
  hay enlaces guardados y pestañas recordadas en el navegador de la gente. Nada nuevo apunta a las viejas
  (`tests/test_rendimiento_cableado.py` las busca en plantillas y `.py`, y corre el alias en Node).
- **R2. Entradas.** Una por país (su tienda de Triple Whale y sus cuentas de Meta con ese país), una por tienda o
  cuenta sin país, más «Todas». Orden: países por código, luego lo que no tiene país.
- **R3. Fuente por entrada.** Con tienda, Triple Whale; si no, el Pixel de Meta. Una entrada muestra el mismo número
  sola y dentro de «Todas», también en sus campañas y conjuntos (`_con_ventas_tw`: gasto, ventas y pedidos TODO de
  Triple Whale y en su moneda; mezclar ventas en USD con gasto en SEK dio un ROAS diez veces mal, 2026-10-10).
- **R4. Una tienda sin país** es la fuente de todo el proyecto y el selector queda solo con «Todas»: Triple Whale no
  separa esas ventas por país (misma regla que `lanzador._tienda_tw_de`).
- **R5. Sin contar dos veces.** Una cuenta de Meta cuyos anuncios llegan en la copia de una tienda
  (`triple_whale.datos.cuentas_meta_de_tiendas`) está dentro de esa tienda: «Todas» no suma su gasto aparte. Se decide
  con los datos, no con el país (una cuenta «World Wide» alimenta Noruega). «Por país» lo dice en una nota.
- **R6. Moneda.** Una entrada en su moneda; «Todas» en USD día por día con la tasa de ESE día; sin tasa, «USD no
  disponible», nunca una inventada; si todas comparten moneda, esa. Una cuenta sin moneda conocida no se suma como si
  fuera de la de las demás.
- **R7. «Desde el inicio»** es el periodo por defecto (regla del 2026-10-08: métricas en total). En «Todas» arranca el
  día en que TODAS las fuentes ya tienen datos y lo dice: sumar 3 meses de una tienda con 13 de una cuenta daría un
  total que no es de nadie. Una fuente atrasada no cuenta como ventas en cero (`resumen._fin_datos`).
- **R8. Ventas arriba = retorno real.** Con Triple Whale, «Ventas» es lo que entró a la tienda y «Retorno», ventas /
  gasto; con Meta, el valor del Pixel rotulado «según Meta». En una mezcla, una línea dice de dónde sale cada parte.
- **R9. Por anuncio, solo pagado.** Solo cuentan los canales con gasto en la copia del alcance: lo atribuido sumaba 2,5
  veces la tienda por orgánico, Klaviyo y Direct (PND-157, cerrado). Vive en `triple_whale.datos` (skill
  `triple-whale`).
- **R10/R11/A4. La ventana de atribución no la cambia el código.** E0 recomienda 7 días (cuadra 1,01× con la tienda);
  Daniel la cambia en «Ajustes» (`cfg_triple_whale_ajustes`). Nunca tocar `triple_whale.VENTANA_DEFECTO`,
  `MODELO_DEFECTO` ni el ajuste de un proyecto: mueven lo que decide el decisor de Experimentos (plata).
- **R12. «Meta reporta».** En la tarjeta de un anuncio `facebook-ads` de Triple Whale, «Meta reporta N×» sale de
  `valor_canal / gasto`; sin dato no aparece.
- **R13. Lo pagado no se mueve.** «Cómo mejorarlo», «Analizar los N», «Evaluar con IA», Referentes, «Llevar a Crear» y
  Pausar/Activar siguen en `triple_whale/rutas.py` con su alcance y sus garantías; esta pestaña solo les pasa la tienda
  de la entrada (o `None`). El JS de la galería se trajo tal cual (`tests/test_tw_tarjetas_js.py` lo lee aquí).
- **R14. Anuncios de fuente Meta sin IA** en E1: tarjeta con veredicto contra SU cuenta y sin botón (ni apagado).
- **R15. Conexión en «Ajustes».** El formulario de Triple Whale (`_triple_whale_conectar.html`, un `div`: una
  `section` cortaba la de la pestaña) y «Elegir cuentas de Meta» (solo admin, R20 de Meta) viven en `#rend-ajustes`; la
  conexión con Meta sigue en Configuración › Conexiones.
- **R16. Fuera:** Experimentos (solo cambió su enlace a `#rendimiento`), E3 de Meta (PND-193), lanzar en varias
  cuentas (PND-148), modo agencia de la lectura (PND-197).

## Enmiendas al planear

- **A1.** La galería de Triple Whale va tal cual y debajo las tarjetas de fuente Meta: mezclarlas antes de que tengan su
  análisis arriesgaba lo que cobra. Se unen en E2 (y ahí se cierra PND-196, orden por USD).
- **A2.** R7 vale para «Resultados» y «Por país»; anuncios y campañas usan el «Desde el inicio» de su propia copia.
- **A3.** Detalle del día y filtro «Canal» solo con alcance solo Triple Whale; con Meta o mezcla la gráfica no abre días.
- **A5.** «Actualizar ahora» es una ruta (`rendimiento.actualizar`) que llama a `triple_whale.rutas.pedir_copia` y
  `meta_rendimiento.rutas.pedir_copia` con los `job_id` de siempre, la pausa compartida de Meta y la espera de 30
  minutos de quien no es admin. Una entrada ajena es «Todas»: nunca encola la tienda o la cuenta de otro proyecto.
- **A6.** E2 (PND-192) trae «Cómo mejorarlo»/«Evaluar con IA» para Meta con la misma tabla y tarea; la copia de
  desgloses `meta_desglose` y los avisos por correo de Meta quedaron aparte (PND-209).

## Trampas

- Lo que se jubiló el 2026-10-09 (no lo revivas): `_tab_triple_whale.html`, `_tab_meta.html`, `_tw_panel.html`,
  `_meta_panel.html`, `_meta_anuncios_filas.html`, `meta_rendimiento/grafico.py`, las rutas `triple_whale.ver_panel`,
  `triple_whale.sincronizar`, `meta_rendimiento.ver_panel`/`ver_anuncios`/`ver_conjuntos`/`sincronizar` y
  `meta_rendimiento.panel.contexto`/`anuncios_pagina`/`conjuntos_pagina`. Sus pruebas pasaron a `/rendimiento/panel`
  (con `entrada=` o los `tienda=`/`cuenta=` viejos) y `/rendimiento/actualizar`.
- «Por país» reemplazó a «Por tienda» (también con solo tiendas) y no compara con el periodo anterior.
- El panel trae un solo `<script>`: el JSON inerte `#tw-resultados-datos`. Las pruebas que buscan «sin scripts» lo
  descuentan.
- Con Meta conectado y sin cuentas, el panel igual se pide y dice que faltan cuentas (la pestaña puede tener Triple Whale).
