# Rendimiento: las métricas que faltaban (2026-10-13)

## 1. Pedido

Daniel (2026-10-13) mandó capturas de un informe «Happy Flops October Performance» (un artifact de otra persona, con
datos de Triple Whale por país) y pidió: «lo debemos de poner también en el performance, todas estas métricas que
estaban faltando», «necesito que esas métricas que faltan las tengamos desde Triple Whale». Eligió que sigan el
selector de periodo de la pestaña (opción A: «Desde el inicio» por defecto, regla del 2026-10-08) y aprobó este
diseño en el chat («si»). Va conectando en Creatv las tiendas de Triple Whale de los demás países (hoy happyflops solo
tiene Noruega, PND-216); no hay código que cambiar para eso.

## 2. Qué ya estaba y qué falta

Ya en Rendimiento: ROAS, gasto, ventas, compras, costo por compra, CTR, CPM, NVP, selector por país, lectura en
palabras. Faltan, todo con datos que la copia de Triple Whale YA guarda (`tw_anuncio_dia`, `tw_creativo`):

| Del informe | En Creatv | Dato |
|---|---|---|
| New-customer ROAS | tile «ROAS de clientes nuevos» | `nc_ingresos / gasto` de los anuncios (`m.nc_roas`, ya calculado) |
| Conversion rate | tile «Tasa de conversión» | `pedidos / sesiones` de los anuncios (nuevo `m.cv_sesion`) |
| Best-selling products con spend y ROAS | «Productos en tus anuncios» | anuncios agrupados por producto (§4.1) |
| Best ads to iterate | «Los mejores para iterar» | §4.2 |
| Best converting ads | «Los que mejor convierten» | §4.3 |
| Top image ads / Top video ads | «Mejores imágenes» / «Mejores videos» | `tw_creativo.tipo` (§4.4) |

Fuera: el título «para Black Friday» (caduca en diciembre), cualquier llamada a Claude, el mes en curso como periodo
(regla del 2026-10-08), y las entradas de solo Meta (Meta no da sesiones, ventas a clientes nuevos ni la página de
destino en nuestra copia).

## 3. Dónde y cuándo se ve

- Solo cuando `r.fuente == "tw"` (una tienda, o «Todas» con solo tiendas): la misma condición que los tiles de
  Triple Whale encima de la galería (`_rend_panel.html`). Con Meta o mezcla describirían solo una parte del alcance.
- Siguen país, periodo y canal del panel: se calculan sobre `tw["ev"]["anuncios"]`, que ya es ese alcance (R9: solo
  canales con gasto).
- Orden en la página: los dos tiles nuevos se suman a `tiles_anuncios`; debajo de la galería «Tus anuncios» van «Los
  mejores para iterar», «Los que mejor convierten», «Mejores imágenes» y «Mejores videos»; «Productos en tus anuncios»
  va justo después de «Lo que más se vende» (dentro de `resto`), que no cambia: mide otra cosa (lo vendido en la
  tienda, venga o no de un anuncio) y su nota lo dice.
- Una sección sin filas no se pinta, salvo las dos listas, que dicen por qué están vacías (los mínimos).

## 4. Reglas

Módulo nuevo `triple_whale/destacados.py`: funciones puras (sin base) más `armar(cliente, tw)`, que hace las lecturas.

### 4.1 Producto de un anuncio

En orden, la primera que dé:
1. **Página de destino → Catálogo.** De `destino_url` se toma el handle de `/products/<handle>`; se normaliza
   (minúsculas, sin el `-<dígitos>` final que Shopify agrega en otras tiendas, sin guiones). Se compara con el handle de
   `url_compra` de cada producto activo del Catálogo, normalizado igual. Medido en producción (happyflops, Noruega, 30
   días): el 92 % del gasto tiene handle de producto; `happyflops-cozy-1` → HappyCozy, `happy-cushers` → HappyCushers,
   `happyflops-1` → HappyFlops Original.
2. **Nombre del anuncio → Catálogo.** El nombre del producto normalizado (solo `a-z0-9`, 5 caracteres o más) dentro
   del nombre del anuncio normalizado; gana el más largo.
3. **El handle tal cual** (sin el `-<dígitos>`), si había uno: mejor un nombre de página que esconderlo en «Otros».
4. **«Otros»** (sin página de producto).

«Productos en tus anuncios»: por producto, ventas atribuidas, gasto, ROAS, compras y número de anuncios; orden por
ventas, hasta 10 productos, y «Otros» al final con lo que quede (también los productos más allá del 10). La suma del
gasto de las filas es el gasto de los anuncios del alcance (el tile «Gasto»).

### 4.2 «Los mejores para iterar»

ROAS ≥ el ROAS de los anuncios del alcance (`ev.cuenta.m.roas`) y `pedidos >= 10` (`PEDIDOS_MIN_ITERAR`). Orden por
ventas, hasta 8. Columnas: anuncio, producto, tipo, ventas, ROAS, compras, CTR. Sin ROAS de cuenta (sin ventas) la
lista queda vacía con su motivo. Pedidos en Float (los modelos lineales reparten): el mínimo compara el Float.

### 4.3 «Los que mejor convierten»

`sesiones >= 100` (`SESIONES_MIN_CONVERSION`) y `pedidos >= 3`; conversión = pedidos / sesiones. Orden por conversión
(desempate: pedidos, luego ad_id), hasta 8. Columnas: anuncio, producto, tipo, sesiones, compras, conversión.
`m.conversion` (pedidos / clics, la de los anillos) no cambia: esta es otra, por sesión, y lleva otro nombre
(`cv_sesion`).

### 4.4 Tipo y «Mejores imágenes» / «Mejores videos»

- Etiqueta: `tw_creativo.tipo` → Imagen (`image`), Carrusel (`carousel`), Video (`video`), Dinámico (`dynamic`); sin
  tipo, Video si el anuncio tiene vistas de 3 s (`m.es_video`), si no Imagen.
- Grupo: video si `tipo == "video"`, o si el tipo no es `image`/`carousel` y `m.es_video`; si no, imagen.
- Hasta 6 por grupo, con `pedidos > 0`, orden por ventas. Tarjeta liviana (no la de la galería: sin análisis ni
  botones que cobran): medio de `triple_whale.panel.medio_tarjeta` (mismos hosts permitidos; pieza de Creatv con lo suyo
  de R2), nombre, producto, ROAS, ventas, compras, CTR. `<img loading="lazy">`, `<video preload="none"
  data-precarga>` (regla 8 de CLAUDE.md).

## 5. Lecturas (escala)

Número fijo, crezcan o no los anuncios:
- `triple_whale.datos.tipos_creativo(cliente)`: UNA consulta `(canal, ad_id, tipo)` de `tw_creativo` del proyecto.
- `tiendas.productos(cliente)`: UNA consulta (el Catálogo activo).
- `triple_whale.datos.creativos(cliente, claves)` solo para las ≤ 12 tarjetas (un tramo: una consulta).
Lo llama `pestana_rendimiento.panel.contexto` solo con `fuente == "tw"` y lo pone en `r.destacados`.

## 6. Pantalla e idioma

- Macros nuevas en `templates/_rend_destacados.html` (sin `<script>`); estilos con la base visual común y, si hace
  falta, `static/estilos/pantallas/rendimiento.css`. En el celular las tablas van en `.tw-tabla-scroll` (nada empuja la
  página de lado).
- Todo texto por el catálogo (`_()`), traducido al inglés con `docs/i18n/glosario.md`.

## 7. Pruebas

- Puras: handle con `-1`, con guiones, sin `/products/`, nombre como respaldo, «Otros», suma del gasto = tile;
  mínimos de iterar y de conversión (borde 10 / 9,99; 100 / 99 sesiones); ROAS de cuenta None; tipo con y sin
  `tw_creativo`, dinámico con y sin vistas de 3 s; topes 8/8/6/6/10.
- Panel: `/rendimiento/panel` con una tienda sembrada pinta las secciones; con Meta o mezcla no; consultas que no
  crecen con los anuncios.
- Mutaciones (revisor): romper el `-<dígitos>`, el mínimo de pedidos, el orden por conversión, el grupo de video.
- Captura del panel con datos reales de Noruega (copia de la base de producción en local) antes de darlo por bueno.

## 8. Plata y seguridad

No cobra ni llama a proveedores: solo lee la copia. Nada nuevo entra a un prompt. Los medios son los ya permitidos
por `medio_tarjeta`. Lecturas filtradas por `cliente` (aislamiento entre proyectos).
