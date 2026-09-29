# Catálogo por colores, traído de Shopify sin llaves

Fecha: 2026-09-28. Estado: aprobado por Daniel («Hagamos todo. Traigámoslo y lo
cargamos a Catálogo»). Caso que lo motiva: Happy Flops (happyflops.com).

## 1. Resumen

Hoy un producto del catálogo es una carpeta con hasta 6 fotos y una regla de
fidelidad. Para una marca de calzado como Happy Flops eso no sirve: «HappyFlops
Original» tiene 14 colores y el modelo necesita la foto del color exacto que va
en el anuncio. Este diseño hace tres cosas:

1. **Un producto tiene colores.** Cada color lleva sus propias fotos de referencia
   y es lo que Crear, Sprints y «Cambiar producto» eligen como `@Producto`. El
   precio, la URL, «en prueba», la prioridad, la sofisticación y las pruebas siguen
   siendo del producto (una sola fila comercial por producto).
2. **Se trae de Shopify sin llaves.** Un conector nuevo lee el catálogo público de
   cualquier tienda Shopify (`/products.json`, `/meta.json`): productos, colores con
   su foto de estudio, precio, moneda y URL de compra. Se pega el dominio y listo; se
   sincroniza solo cada 6 h como las demás tiendas. El conector con Admin API sigue
   existiendo para pedidos y atribución.
3. **La pestaña Catálogo se rehace:** galería de tarjetas con filtros y una ficha por
   producto en un panel lateral (colores, fotos, datos, lo que Claude necesita, usos,
   acciones). Personajes y entornos usan la misma galería. Se arreglan los
   redireccionamientos que hoy mandan a Crear al guardar.

Nada de esto genera ni publica nada. Lo único que se paga es la regla de fidelidad
por producto al importar (Claude, centavos), como hoy.

## 2. Por qué ahora

Happy Flops en Shopify (leído el 2026-09-28 del catálogo público):

| Dato | Valor |
|---|---|
| Productos publicados | 19 (18 reales + «Shipping protection», que hay que omitir) |
| Colores/estampados | 130 en total, de 2 a 14 por producto |
| Foto de estudio por color | exactamente 1, ligada al color en Shopify (`variant.featured_image`) |
| Fotos «lifestyle» sin color | la mayoría (31 de 37 en Bohemian) |
| Precio | uno por producto (€19.95–59.95); las tallas no cambian el precio |
| Moneda | EUR (`/meta.json` → `currency`) |

Lo que Creatv tiene hoy para happyflops: 2 productos a mano (HOriginal con
beige/rose/sky y una cobija), sin precio, sin URL, sin tienda. El conector Shopify
actual pide `variants(first: 1)` e `images(first: 6)`: importaría 18 productos con 6
fotos de colores mezclados cada uno y el modelo recibiría la beige cuando el anuncio
es de la rosa.

Problemas de la pestaña actual: lista vertical de `<details>` con formularios
adentro; al guardar (`actualizar_producto`, `subir_imagen_producto`,
`eliminar_imagen_producto`, `eliminar_producto`) redirige a `#cambiar` (Crear);
Personajes aparece dos veces (categoría del catálogo + sección vieja); «Importados
sin fotos» es una tabla aparte con otro estilo; dos tipos de id en las rutas
(`<producto_id>` de disco y `<int:pid>` de la fila).

## 3. Vocabulario

- **Producto**: lo que se vende. Carpeta `clientes/<c>/productos/<pid>/` + entrada en
  `productos.json` + UNA fila `producto` (comercial). Id `pid` sin `/`.
- **Color** (variante visual; en Shopify «Colour», «Patterns»…): una versión del
  producto con sus propias fotos de referencia. Subcarpeta `<pid>/<color_id>/`,
  entrada `variantes[color_id]` en la meta del producto. Su id compuesto es
  `<pid>/<color_id>` y es lo que guardan `campana.catalogo_id`, los checkbox de Crear
  y los swaps. Un producto sin colores es un producto **plano**: sus fotos van en la
  raíz de su carpeta y su id de referencia es `pid`.
- **Foto de estudio**: la foto de referencia de un color (la que Shopify liga a la
  variante). **Foto general**: foto del producto sin color asignado (lifestyle); en un
  producto con colores viven en la raíz y NO son referencia del producto.
- **Activo del catálogo**: cualquier entrada de `catalogo_productos.listar()` (un color,
  un producto plano, un personaje, un entorno). Distinto del «activo» de Meta del
  glosario (`CONTEXT.md`): aquí siempre se dice «activo del catálogo».
- **Fila comercial**: la fila `producto` (precio, moneda, URL de compra, en prueba,
  prioridad, sofisticación, pruebas, pedidos), una por producto, ligada por
  `activo_catalogo_id = pid`.
- **Tienda pública**: una tienda Shopify conectada solo por su dominio (`tipo`
  `shopify_publico`, `fuente` `shopify`).

## 4. Alcance, fuera de alcance y decisiones tomadas

Dentro:
- Modelo producto → colores en disco y en `catalogo_productos` (§5).
- Conector `shopify_publico` (§6) y el importador con colores (§7).
- Una fila comercial por producto, con migración de datos 0022 (§8).
- Los consumidores del catálogo que deben entender el id compuesto (§9).
- La pestaña Catálogo nueva: galería + ficha + traer de mi tienda (§10), la opción
  «Shopify (sin llaves)» en Configuración › Conexiones, el selector de Crear agrupado
  por producto, «Crear con este color» y el select de Sprints con `<optgroup>`.
- Traer y cargar el catálogo real de Happy Flops en producción (§16).

Fuera (y por qué):
- Precios por país (Shopify Markets): el precio por país ya se escribe en Final
  edition por destino y nada lo consume antes. Se anota como siguiente paso.
- Tallas: se guardan en `extra.tallas` y no se muestran.
- Colecciones de Shopify como filtro: `/collections.json` no dice qué productos tiene
  cada una sin una llamada por colección; se guardan `tags` y `product_type`.
- Cambiar qué guarda `productos_ids` (nombres): sigue igual; los consumidores
  resuelven por id o nombre como hoy.
- Sprints por producto con rotación de colores: una campaña sigue apuntando a UN
  activo del catálogo (un color o un producto plano).
- Quitar el bloque de Logos duplicado en Configuración › Marca.
- Archivar un producto que tiene activo: sigue existiendo solo «Eliminar»
  (irreversible, con modal). «Archivar» queda para filas sin activo, como hoy.

Decisiones (rulings) que no se vuelven a discutir:
- El orden de los colores es el de la tienda (orden de inserción en la meta), no
  alfabético.
- Cada color trae de Shopify su foto de estudio y las fotos que Shopify ligue a sus
  variantes (tope `MAX_FOTOS` = 6); las fotos sin color van a la raíz (tope 6). Las
  fotos se piden al CDN con `width=1000` (≈0,7 MB en vez de 1 MB; verificado que
  `format=` no convierte).
- El precio del producto es la **moda** de los precios de sus variantes disponibles
  (empate → el menor); `extra.precios = {min, max}` cuando difieren.
- Un producto importado es un producto con colores si Shopify tiene una opción de
  color (§6); si no, es plano con sus 6 primeras fotos, como hoy.
- La regla de fidelidad se pide a Claude UNA vez por producto (al crear el activo),
  nunca por color.
- La fila comercial es del producto. Los ids compuestos que hoy tienen filas propias
  (happyflops: `horiginal/beige`…) se migran a la del producto (§8).
- La galería y la ficha se cargan por fragmento (fetch), como Referentes y el panel de
  Sprints: la página del proyecto no crece con el catálogo.

## 5. Modelo de datos en disco (`catalogo_productos.py`)

### 5.1 Carpetas y meta

```
clientes/<c>/productos/<pid>/           # producto
  01.jpg 02.png …                       # plano: fotos de referencia · con colores: fotos generales
  <color_id>/01.png 02.jpg …            # un color: sus fotos de referencia (01.* es la de estudio)
clientes/<c>/productos.json
  "<pid>": {
    "nombre", "descripcion", "tipo", "zonas", "regla",
    "variantes": {                      # ausente o {} = producto plano
      "<color_id>": {"nombre": "Pink", "descripcion": "", "fuente_id": "57361654743417",
                     "url_compra": "https://…/products/happyflops?variant=57361654743417",
                     "disponible": true}
    },
    "fuente": {"tipo": "shopify", "handle": "happyflops"}    # opcional, informativo
  }
```

Es la forma «variantes» que ya existe (commit 3217699) vuelta de primera clase.
`color_id = id_desde_nombre(nombre del color)` desambiguado con `-2`, `-3`. Los
ids de producto nunca llevan `/`: `producto_base("horiginal/beige") == "horiginal"`
es una función pura (todo lo que va antes del primer `/`).

Reglas:
- Un producto con `variantes` no vacío: los archivos de la raíz son fotos generales.
  Sin `variantes`: los archivos de la raíz son sus fotos de referencia (como hoy).
- Un color sin fotos existe en la meta pero no aparece en `listar()` (igual que un
  activo sin fotos); la ficha lo muestra como «sin fotos» con su botón de subir.
- `carpeta_de(cliente, pid, categoria, variante=None)` valida `pid` Y `variante`
  contra fugas de directorio (ninguno puede salir de la carpeta del producto).
- Personajes y entornos no tienen colores (la meta nunca lleva `variantes`); todo
  lo de este diseño que dice «color» aplica solo a la categoría `producto`.

### 5.2 Lecturas

`listar(cliente, categoria)` devuelve lo mismo que hoy (una entrada por color o por
producto plano, mismas claves) más:

| Clave nueva | Valor |
|---|---|
| `producto_id` | `pid` |
| `nombre_producto` | nombre del producto |
| `variante` | `color_id` o `None` |
| `variante_nombre` | nombre del color o `None` |
| `disponible` | `variantes[c].disponible` (True si no se sabe) |

La `regla` de un color es la del producto (regla de la categoría + regla propia) más,
si el color tiene `descripcion`, una frase al final: «Variante «Pink»: <descripcion>»
(en el idioma del proyecto, vía `idiomas`). El `nombre` de un color es
`variantes[c].nombre` si lo hay (el importador guarda «<producto> — <color>»), si no
`<producto> <Color>` como hoy. El orden de los colores es el de la meta.

`listar_productos(cliente, categoria="producto")` → una entrada por PRODUCTO:

```
{id, categoria, nombre, descripcion, tipo, zonas, mapa_texto, mapa_etiqueta, regla,
 regla_propia, tiene_colores, fuente,
 colores: [{id, nombre, descripcion, fuente_id, url_compra, disponible, imagenes,
            referencias, representativa, sin_fotos}],   # orden de la meta; [] si plano
 fotos_generales: [nombres de archivo de la raíz],       # si tiene colores
 imagenes: [nombres de archivo de la raíz],              # si es plano
 representativa: ruta de la primera foto de referencia (primer color con foto, o raíz),
 n_fotos, n_colores}
```

Para personaje/entorno devuelve lo mismo con `tiene_colores=False`. `listar_todo`
no cambia.

`encontrar(cliente, id, categoria=None)`: como hoy y, además, si `id` es un producto
con colores (no aparece en `listar()` por sí mismo), devuelve su primer color con
fotos. Así `campana.catalogo_id = "horiginal"` o un `productos_ids` viejo siguen
resolviendo a una referencia con foto. `encontrar_producto(cliente, pid, categoria)`
devuelve la entrada de `listar_productos`. `encontrar_por_id_o_nombre` acepta también
el nombre del producto (devuelve su primer color).

`claves_de_producto(cliente, pid)` → `{"ids": {pid, "pid/c1", …}, "nombres": {nombre
del producto, nombres de los colores}}` todo en `casefold()`: lo usan
`doctrina.pedidos`, el conteo de experimentos y la ficha para reunir usos.

### 5.3 Escrituras (siempre bajo `modificar_meta`)

- `crear(...)`: sin cambios (crea un producto plano).
- `agregar_color(cliente, pid, nombre, descripcion="", fuente_id=None, url_compra=None,
  disponible=True, color_id=None, convertir_actual=None) -> color_id`: crea
  `variantes[color_id]` y la subcarpeta. Si el producto es plano y tiene fotos en la
  raíz, exige `convertir_actual` (el nombre del color de esas fotos): mueve las fotos
  de la raíz a ese primer color y luego agrega el nuevo. `ValueError` si el color ya
  existe con el mismo nombre (mismo `color_id`) — el importador pasa `color_id`
  explícito y adopta.
- `actualizar_color(cliente, pid, color_id, **campos)`: nombre, descripcion,
  fuente_id, url_compra, disponible.
- `quitar_color(cliente, pid, color_id)`: borra la subcarpeta y la entrada. Se niega
  si es el último color con fotos del producto (ValueError con mensaje: «elimina el
  producto entero»).
- `mover_foto_a_color(cliente, pid, nombre_archivo, color_id)`: `os.replace` de la
  raíz a la subcarpeta (renumerando si choca el nombre).
- `eliminar_imagen(cliente, pid, nombre, categoria, variante=None)`: con `variante`
  borra dentro del color y nunca deja al color sin fotos (mismo mensaje que hoy para
  el producto).
- `eliminar(cliente, pid, categoria)`: borra la carpeta entera (colores incluidos).

## 6. Conector `shopify_publico` (`conectores/shopify_publico.py`)

Clase `ShopifyPublico(Conector)` registrada con `@registrar`:
`tipo = "shopify_publico"`, `fuente = "shopify"` (atributo nuevo de `Conector`,
`None` por defecto = usa `tipo`), `tiene_pedidos = False`, `soporta_utm = False`,
`NOMBRE = "Shopify (sin llaves)"`. Credenciales: `{"dominio": "www.happyflops.com"}`
(se guardan cifradas como cualquier tienda; no hay secreto).

- `normalizar_dominio(texto)`: quita esquema, ruta, query, espacios, punto final;
  minúsculas. `ErrorConector` si queda vacío o con caracteres que no son de host.
  Antes de cada petición, `conectores.url.host_permitido("https://<dominio>/")`
  (SSRF, como el conector de URL).
- HTTP por `conectores._http.pedir` (timeouts y reintentos de siempre), UA de
  navegador, `Accept: application/json`. Toda respuesta se valida como JSON con la
  forma esperada; HTML (tienda con contraseña, dominio que no es Shopify) →
  `ErrorConector("No encontré un catálogo público de Shopify en <dominio>. ¿Es una
  tienda Shopify y está abierta al público, sin contraseña?")`.
- `probar()`: `GET /meta.json` (`TIMEOUT_PROBAR`, sin reintentos) → `{"ok": True,
  "nombre": meta["name"], "detalle": "Tienda pública leída: N productos, moneda EUR."}`.
  Si `/meta.json` no responde JSON, prueba `/products.json?limit=1`; si tampoco, el
  error de arriba.
- `listar_productos()`: `moneda = meta["currency"]` (None si no hay meta); páginas
  `GET /products.json?limit=250&page=N` hasta que una traiga menos de 250 o
  `MAX_PAGINAS = 40`. Por producto:
  - Se omite si `published_at` es null, o si `_es_servicio(p)`: alguna palabra de
    `PALABRAS_SERVICIO` en `product_type` o `title` (casefold, sin acentos):
    «shipping protection», «package protection», «route protection», «upcart»,
    «insurance», «seguro de envio», «proteccion de envio», «gift card», «tarjeta de
    regalo», «tarjeta regalo», «donation», «donacion», «propina». Los omitidos van a
    `self.omitidos` (títulos) y el resumen de la sync los nombra.
  - Opción de color: la primera opción (por posición) cuyo nombre normalizado esté en
    `OPCIONES_COLOR = {"colour", "color", "colores", "colors", "pattern", "patterns",
    "estampado", "estampados", "diseno", "design", "print", "estilo", "style",
    "acabado", "finish", "modelo"}`. Si ninguna: la primera opción con ≥ 2 valores
    cuyas variantes tengan ≥ 2 `featured_image.id` distintos. Si ninguna: producto
    plano.
  - Por valor de color (en orden de la opción): variantes con ese valor;
    `fuente_id` = id de la primera; `disponible` = alguna `available`; `url_compra` =
    `<url del producto>?variant=<id de la primera>`; `fotos` = `featured_image` de la
    primera variante que tenga una, más las imágenes del producto cuyos `variant_ids`
    toquen esas variantes (sin repetir, orden del producto), tope `MAX_FOTOS`.
  - Producto: `fuente_id = str(p["id"])` (el mismo número que `_id_de_gid` del
    conector con API: las filas son las mismas), `nombre = title`, `descripcion =
    limpiar_html(body_html)`, `precio` = moda (§4), `moneda`, `url_compra =
    https://<dominio>/products/<handle>`, `categoria = product_type or None`,
    `url_imagen_principal` = primera imagen, `fotos` = con colores: imágenes con
    `variant_ids == []` (tope `MAX_FOTOS_GENERALES = 6`); plano: todas (tope 6, la
    principal primero). `extra = {"handle", "tags", "tallas", "precios", "variantes":
    [normalizar_variante(...)]}`.
  - Toda URL de imagen de `cdn.shopify.com` lleva `width=1000` añadido a su query
    (`_foto_url`); otras URLs van tal cual.
- `conectores.base.normalizar_variante(d)` (nuevo, público): `{id, nombre, fuente_id,
  url_compra, fotos, disponible}` con las mismas limpiezas que `normalizar_producto`
  (`_fotos`, `_nombre`, `_texto_o_none`). Cualquier conector futuro (CSV con columna
  «color») puede entregar `extra["variantes"]` con esa forma.
- `conectores.TIPOS_CONECTABLES = ("shopify_publico",) + TIPOS_API`: lo que la UI
  ofrece. `TIPOS_API` no cambia.

`tareas/tiendas.py`: `fuente = getattr(con, "fuente", None) or tienda["tipo"]` en
`tienda_sync_productos` (para `importar_lista`, `archivar_faltantes` y el chequeo de
«primera importación»). `tienda_conectar` acepta `tipo == "shopify_publico"` con solo
`dominio` (mismos requisitos: correo verificado para clientes, cifrado disponible) y,
al conectar un `shopify` con API cuyo dominio ya tiene una tienda `shopify_publico`,
desconecta la pública primero (misma `fuente`: las filas no se tocan). El correo de
«tienda rota» y las periódicas funcionan igual.

## 7. Importador con colores (`importador.py`)

`vincular_activo(cliente, producto_id, forzar_fotos=False, errores=None)`:

- `variantes = (prod["extra"] or {}).get("variantes") or []`.
- **Activo nuevo**: como hoy (id disponible o adopción de carpeta con el mismo id,
  descarga a temporal, regla de Claude UNA vez, `crear`) y además, por cada variante
  (si adopta un activo plano que ya tiene fotos en la raíz, el primer `agregar_color`
  lleva `convertir_actual=<nombre del producto>`: esas fotos pasan a ser un color y
  nunca se pierde la referencia):
  `agregar_color(..., color_id=id_desde_nombre(nombre) desambiguado, fuente_id,
  url_compra, disponible, nombre=f"{nombre del producto} — {color}")` y sus fotos a la
  subcarpeta (temporal → `_reemplazar_fotos(carpeta_del_color, temporal)`). Las fotos
  generales van a la raíz. Sin NINGUNA foto (ni de color ni general) no se crea el
  activo (aviso «sin fotos», como hoy). Un color cuya foto no bajó queda en la meta
  sin carpeta con fotos (la ficha lo muestra «sin fotos»).
- **Activo ya ligado** (carpeta existe): refresca nombre/descripción del producto (la
  regla nunca). Colores: los que no están en la meta se agregan y se descargan; los
  que ya están refrescan `nombre`, `url_compra`, `disponible`, `fuente_id`, y sus
  fotos solo con `forzar_fotos` o si la subcarpeta no tiene ninguna; los que tienen
  `fuente_id` y ya no vienen de la tienda quedan `disponible=False` (nunca se borran
  fotos solas). Fotos generales: solo con `forzar_fotos` o si la raíz no tiene
  numeradas.
- `_activo_completo`: tiene alguna foto en la raíz o en algún color.
- `resumen["colores"]`: colores creados en la corrida; `resumen_texto` los nombra.
- `producto_vincular` (worker, «Crear activo desde las fotos de la tienda» y
  reintentos) sigue con `forzar_fotos=True`.
- `MAX_FOTOS` (por color y por producto plano) sigue en 6; `MAX_FOTOS_GENERALES = 6`.

## 8. Una fila comercial por producto (+ migración 0022)

- `_asegurar_filas_producto(cliente, productos)` recorre `listar_productos()` (ids de
  producto) y crea la fila manual que falte. Nunca crea filas para ids con `/`.
- `tiendas.por_activo(cliente)` no cambia (claves = `activo_catalogo_id`). Quien tenga
  un id de activo cualquiera consulta `.get(catalogo_productos.producto_base(id))`.
- **Migración Alembic 0022 (datos)**: para cada fila `producto` cuyo
  `activo_catalogo_id` contenga `/`, con `base` = lo anterior al `/`:
  1. si el cliente no tiene otra fila con `activo_catalogo_id == base`: la fila pasa a
     ser la del producto (`activo_catalogo_id = base`; si `fuente == "manual"`, también
     `fuente_id = base`);
  2. si ya la hay y esta fila está «vacía» (precio y url_compra NULL, en_prueba 0,
     prioridad 0, `extra` sin `sofisticacion`/`pruebas`/`pedidos`): se borra;
  3. si no está vacía: `activo_catalogo_id = base`, `archivado = 1`,
     `extra.archivado_por = "manual"` (se conserva, visible en «Archivados»).
  `downgrade` no hace nada (documentado en el docstring). Se procesa por cliente en
  orden de `id` para que el resultado sea determinista.
- `_guardar_fila_producto`, `crear_producto`, `actualizar_producto`, `eliminar_producto`
  reciben siempre el `pid` (las rutas de disco siguen usando `<producto_id>`; para un
  color la ruta lleva `?variante=` o un campo `variante`, nunca `pid/color` en la URL).

## 9. Consumidores del catálogo

| Dónde | Qué cambia |
|---|---|
| `dashboard.py:2732` (swaps), `organico.py:356`, `sprints/ideas.py:196`, `sprints/rutas.py:504`, `final_edition/__init__.py:159`, `referentes/rutas.py:231` | `por_activo(cliente).get(x)` → `.get(catalogo_productos.producto_base(x))` |
| `doctrina/pedidos.faltantes_del_producto` | usa `claves_de_producto`: campañas con `catalogo_id` en `ids`, sesiones cuyos `productos_ids` toquen `ids ∪ nombres` |
| `dashboard._productos_tienda_contexto` / `_experimentos_por_activo` | `n_experimentos` suma las claves de todos los colores del producto |
| `flowplus_prompt.armar`, `cf_crear_video`, `sprints/produccion.py`, `tareas/swap.py`, `guiones/config.py`, `referentes/recrear` | sin cambios: reciben entradas de `listar()`/`encontrar()` como hoy (`activo` = nombre del color, `regla` con la frase del color) |
| `_selector_productos.html` (Crear, Cambiar producto, Recrear) | tiles agrupados por producto (§10.5); el `value` no cambia |
| `_sprint_panel_armar.html`, `sprints/rutas.py` (select de producto) | `<optgroup>` por producto con colores; ids iguales |
| `tablero.py` (alerta «en prueba sin experimento») | sin cambios (filas por producto) |

## 10. UI

### 10.1 La pestaña (`_tab_catalogo.html`)

```
.panel-cabecera  h2 Catálogo · desc · acciones: [+ Nuevo producto] [Traer de mi tienda]
.cat-tabs        Productos (n) · Personajes (n) · Entornos (n) · Logos (n)
[cat-panel producto]
  barra de sync (si una tienda sincroniza: data-poll-job)
  toolbar: buscador · chips Todos · En prueba · Sin precio · Sin URL · Sin fotos (n) · Archivados (n) · orden Prioridad|Nombre
  #catalogo-grid  ← fragmento (fetch), tarjetas + «Ver más»
  details «Traer productos de…»  (Shopify sin llaves · CSV/Excel · URL · Configuración)
  details «+ Nuevo producto»     (id nuevo-producto; el botón de la cabecera lo abre con data-abrir-detalle)
[cat-panel personaje]  toolbar (buscador) · grid · details «+ Nuevo personaje» · details «Personajes del flujo anterior» (la sección vieja, plegada)
[cat-panel entorno]    toolbar · grid · details «+ Nuevo entorno»
[cat-panel logo]       como hoy
<aside class="tablero-panel" id="catalogo-panel" hidden> + <div class="tablero-fondo">   ← la ficha
modal de eliminar (como hoy)
```

Estados vacíos con `.estado-vacio` y la acción que corresponde («+ Nuevo producto» /
«Traer de mi tienda»). Los contadores de las sub-pestañas cuentan productos (no
colores). Todo con las clases de la base visual; nada de estilos sueltos nuevos salvo
el bloque «Catálogo: galería y ficha» al final de `style.css`.

### 10.2 La galería (`GET /cliente/<c>/catalogo/grid`, fragmento `_catalogo_grid.html`)

Parámetros: `cat` (producto|personaje|entorno), `q` (nombre, casefold, también por
nombre de color), `filtro` (`todos|en_prueba|sin_precio|sin_url|sin_fotos|archivados`),
`orden` (`prioridad` por defecto: prioridad desc, luego nombre; `nombre`), `pagina`
(60 por página; el fragmento trae un botón «Ver más» con la página siguiente, que
anexa). Los filtros viven en el hash (`#catalogo?cat=producto&filtro=en_prueba&q=…`)
como en Referentes, y el JS de la pestaña los lee al abrir y los escribe al cambiar.

Tarjeta (`_catalogo_tarjeta.html`, `id="producto-<pid>"`, `data-cat`, `data-id`):
foto representativa (`?w=320`, `loading="lazy"`), nombre, fila de colores (hasta 6
miniaturas redondas de 22 px con `title` = nombre del color, y «+N»), precio (con
`dinero`) o «sin precio», y chips: fuente (badge), «en prueba», «sin URL», «N
colores», «N fotos», «usado en N» (piezas de Crear + experimentos + campañas, un
número). Clic en la tarjeta → ficha. Filas sin activo (`filtro=sin_fotos` y también en
`todos` al final, marcadas) se pintan como tarjeta con la foto de la tienda
(`url_imagen_principal`), chip «Sin fotos» y sus acciones de hoy: «Subir fotos» (input
oculto, POST `prod_fotos_subir`), «Crear activo desde las fotos de la tienda» (POST
`prod_vincular`, barra `data-poll-job` si corre), «Archivar»/«Recuperar». La tabla
`_catalogo_sin_fotos.html` desaparece.

### 10.3 La ficha (`GET /cliente/<c>/catalogo/<cat>/<activo_id>/ficha`, fragmento `_catalogo_ficha.html`)

Panel lateral (`.tablero-panel`, mismas clases y comportamiento que el de Sprints: fondo,
Escape, ✕, `body.panel-abierto`, 100 % de ancho en celular). Se abre con
`#catalogo?ficha=<cat>:<pid>` (deep link) y el JS de la pestaña lo reabre al cargar la
página si el hash lo trae. Todo su JS vive en `_tab_catalogo.html` (los `<script>` de
un fragmento no corren); las barras de progreso del fragmento se arrancan buscando
`[data-poll-job]`, y `_producto_doctrina.html` pasa a esa convención.

Secciones para un producto:

1. **Cabecera**: nombre, badges (fuente, en prueba, prioridad), precio y rango
   (`extra.precios`), URL de compra (enlace, solo http/https), nota «Sincronizado de
   Shopify: la tienda manda sobre nombre, descripción y colores; precio, URL, en prueba
   y prioridad que pongas aquí se respetan» cuando `fuente != manual`.
2. **Colores** (si `tiene_colores`): tira de fichas de color (miniatura + nombre; la
   elegida resaltada; «sin fotos» punteada; «ya no está en la tienda» atenuada). Debajo,
   las fotos del color elegido (92 px, ✕ → `eliminar_imagen_producto` con `variante`),
   «Subir fotos a este color» (input oculto → `subir_imagen_producto` con `variante`),
   «Quitar color» (confirm → `catalogo_color_quitar`). Cambiar de color es solo JS
   (todas las fotos vienen en el fragmento, `hidden` las de otros colores). Si es plano:
   sección **Fotos** (como hoy). En ambos casos, formulario **+ Color** (nombre, fotos;
   si el producto es plano con fotos, además «¿De qué color son las fotos actuales?»,
   prellenado con el nombre del producto) → `catalogo_color_agregar`.
3. **Fotos de ambiente** (si hay fotos generales): miniaturas con ✕ y, si hay colores,
   un select «Asignar a color» por foto (→ `catalogo_foto_mover`). Texto: «No son
   referencia del producto; asígnalas a un color para que el modelo las use».
   «Subir fotos de ambiente» (input oculto → `subir_imagen_producto` sin `variante`).
4. **Datos** (un formulario → `actualizar_producto` con `volver=ficha`): nombre, tipo,
   descripción, regla propia, mapa corporal (`_maniqui.html`, con su JS arrancado por
   el panel al cargar el fragmento), campos comerciales
   (`_catalogo_campos_comerciales.html`) → «Guardar cambios».
5. **Lo que Claude necesita** + **Pruebas** (`_producto_doctrina.html`, como hoy).
6. **Usos**: «Piezas de Crear: N · Experimentos: N · Campañas de sprints: N», con
   enlaces (`#creativeflowplus`, `#experimentos`, `#sprints`). Se calculan en la ruta de
   la ficha con `claves_de_producto` (una pasada por `creative_flow.cargar`, una por
   experimentos, una consulta a `campana`).
7. **Acciones**: «Crear con este producto» (si hay colores, un select del color; POST
   `catalogo_crear_con`), «Crear experimento» (`prod_experimento`, como hoy),
   «Eliminar producto» (abre el modal de hoy con `data-*`; `eliminar_producto`).

Personaje/entorno: cabecera, fotos (+ subir, ✕), datos (nombre, descripción, regla) y
«Eliminar».

Toda ruta POST del catálogo vuelve con `_volver_catalogo(cliente, cat, pid)` →
`redirect(url_for("ver_cliente", …, _anchor=f"catalogo?ficha={cat}:{pid}"))` (o a
`#catalogo` si no hay ficha). El parámetro `volver` de hoy se respeta cuando lo manda
otro sitio (`volver=creativeflowplus` desde el alta rápida del selector de Crear).

### 10.4 Traer de mi tienda

En «Traer productos de…» la primera opción, abierta, es **Tu tienda Shopify (sin
llaves)**: un campo «Dominio de tu tienda» (`happyflops.com`), texto «Leo el catálogo
público de tu tienda: productos, colores con su foto, precio y URL de compra. No
necesita ninguna llave y se actualiza solo cada 6 h. Para pedidos y atribución
conecta después con la Admin API en Configuración.», botón «Traer catálogo» (≈ precio
de la regla con IA por producto, como el botón de CSV) → `POST tienda_conectar` con
`tipo=shopify_publico`, `dominio`, `volver=catalogo`. Después siguen CSV/Excel, URL y el
enlace a Configuración. Si ya hay una tienda pública conectada, en su lugar se ve
«Shopify: <nombre> · última sync <fecha> · [Sincronizar ahora]» (`tienda_sync`) y la
barra si está corriendo. En Configuración › Conexiones › Conectar tienda, el primer
tipo es «Shopify (sin llaves)» con el mismo formulario; la tabla de tiendas muestra la
etiqueta «Shopify (sin llaves)» y el badge de Shopify.

### 10.5 Crear, «Crear con este color» y Sprints

- `_selector_productos.html`: en ambos modos, las entradas se agrupan por
  `producto_id`: un encabezado con el nombre del producto y «N colores» y un tile por
  color con el nombre del color como pie; un producto plano es un tile con su nombre.
  `data-nombre` (buscador) = producto + color. El `value` sigue siendo
  `<cat>:<pid>/<color>` o `<pid>/<color>` (radio).
- `POST /cliente/<c>/catalogo/producto/<pid>/crear-con` (campo `variante` opcional):
  `session["fp_prefill"] = {"productos_catalogo": ["producto:<pid>/<color>"]}` y
  redirige a `#creativeflowplus`. En `_tab_creativeflowplus.html` el consumidor del
  prefill, si trae `productos_catalogo`, marca esos checkbox y repinta los elegidos
  (`pintarCatalogo()`); `ca.checked` solo se toca si `prefill.calidad` viene.
- Sprints: el select de producto del panel agrupa con `<optgroup label="<producto>">`
  los colores de un mismo producto (`productos` ya trae `producto_id`/`nombre_producto`).

## 11. Rutas

Nuevas (todas bajo `/cliente/<cliente>`, GET responden fragmento HTML):

| Ruta | Método | Hace |
|---|---|---|
| `/catalogo/grid` | GET | galería (§10.2) |
| `/catalogo/<cat>/<activo_id>/ficha` | GET | ficha (§10.3); 404 si no existe |
| `/productos/<pid>/colores` | POST | `catalogo_color_agregar`: nombre, descripción, fotos, `convertir_actual` |
| `/productos/<pid>/colores/<color_id>/quitar` | POST | `catalogo_color_quitar` |
| `/productos/<pid>/fotos/<nombre>/mover` | POST | `catalogo_foto_mover` (`variante`) |
| `/catalogo/producto/<pid>/crear-con` | POST | `catalogo_crear_con` (§10.5) |

Modificadas: `imagen_producto` e `imagen_producto_archivo` pasan a
`<path:producto_id>`: hoy un id con `/` (`horiginal/beige`) genera una URL que la ruta
`<producto_id>` no reconoce y las fotos de los colores dan 404 (verificado el
2026-09-28 con `url_map.bind`). Aceptan `pid` (representativa del producto) o
`pid/color`, y `imagen_producto_archivo` además `?variante=` cuando el id es el del
producto. `subir_imagen_producto` y `eliminar_imagen_producto` reciben el campo
`variante`; `actualizar_producto`, `eliminar_producto`, `subir_imagen_producto`,
`eliminar_imagen_producto` y todas las `prod_*` vuelven con `_volver_catalogo`;
`tienda_conectar` acepta `shopify_publico` y `volver`; `tienda_sync` acepta `volver`.
La ficha (`/catalogo/<cat>/<path:activo_id>/ficha`) tolera un id compuesto y resuelve
su producto. Fuera de eso no cambian URLs: los tests y enlaces existentes siguen
valiendo.

Todas las rutas del catálogo exigen acceso al proyecto (`_guard_por_cliente`) como
hoy; las GET de fragmentos responden 404 (no redirect) cuando el activo no existe.

## 12. Rendimiento

- `ver_cliente` deja de pintar tarjetas del catálogo: solo pasa los contadores por
  categoría y lo que Crear/Sprints ya necesitaban (`activos_por_categoria`, `productos`).
  `producto_comercial`, `productos_sin_activo` y las barras de `vincular`/`pedidos` se
  calculan en las rutas del grid y de la ficha, no en la página.
- Miniaturas `?w=320` en tarjetas y fichas; `loading="lazy"`.
- `test_perf_pagina_proyecto` sigue valiendo (menos trabajo en la página). El grid hace
  UNA consulta a `producto`, una a la cola por tipo de tarea y una pasada por
  experimentos/creative_flow para «usado en N».
- Disco: Happy Flops ≈ 130 fotos de estudio × 0,7 MB + ≤ 108 generales pequeñas ≈
  100 MB en `clientes/happyflops/productos/`. Aceptable; el mantenimiento diario no
  toca el catálogo.

## 13. Idioma

Todo texto nuevo pasa por `_()`/`gettext` con su inglés en
`translations/en/LC_MESSAGES/messages.po` (`catalogo_i18n.py actualizar` → traducir con
`docs/i18n/glosario.md` → `compilar`; `tests/test_i18n_catalogo.py` lo exige). Las
frases que van a Claude o al modelo (la frase «Variante «X»: …» de la regla) se arman
con `idiomas` en el idioma del proyecto.

## 14. Errores y casos raros

- Tienda con contraseña o dominio que no es Shopify → `probar()` falla con mensaje
  claro; no se guarda la tienda.
- La sync de una tienda pública que deja de responder → `estado="rota"` + aviso, igual
  que las demás.
- Producto de Shopify con opción de color pero sin `featured_image` en ninguna
  variante → los colores quedan en la meta «sin fotos» y el producto usa las
  generales como… nada: si ninguna foto bajó, no hay activo (aviso «sin fotos»); si
  bajaron generales, el activo existe con colores sin fotos y la ficha invita a subirlas.
- Dos colores con el mismo nombre normalizado («Pink» y «pink») → `-2`.
- Un producto importado cuyo nombre coincide con un activo subido a mano se ADOPTA
  (como hoy); los colores se agregan al activo adoptado (sus fotos de raíz pasan a ser
  generales y, si estaban solas, a un color «<nombre del producto>» vía
  `convertir_actual`: el importador lo pasa siempre para no perder la referencia).
- Eliminar un producto con colores borra todo; el modal dice cuántas fotos (todas).
- Un id de color inválido (`..`) en formularios → `ValueError` → flash + volver.
- `quitar_color` del último color con fotos → mensaje, no se quita.
- Renombrar un producto no rompe la ficha ni los enlaces (los ids no cambian).

## 15. Tests

Nuevos:
- `tests/test_catalogo_colores.py`: `listar` con colores (orden, claves nuevas, regla
  con la frase del color), `listar_productos`, `encontrar` con fallback, `producto_base`,
  `claves_de_producto`, `agregar_color` (con y sin `convertir_actual`), `quitar_color`
  (último con fotos), `mover_foto_a_color`, `eliminar_imagen` con `variante`,
  `carpeta_de` con `variante` maliciosa.
- `tests/test_conector_shopify_publico.py`: con un fixture recortado del catálogo real
  de Happy Flops (`tests/fixtures/shopify_publico_happyflops.json`, 3 productos +
  shipping protection + uno sin publicar + uno sin opción de color): colores y fotos
  por color, generales, precio moda y rango, moneda de meta.json, url por variante,
  omitidos, paginación, `width=1000`, `probar()` (ok, HTML, 404), `normalizar_dominio`,
  SSRF.
- `tests/test_importador_colores.py`: `vincular_activo` con `extra.variantes`
  (subcarpetas, meta, generales, regla una vez y su gasto, colores nuevos en una
  segunda sync, `disponible=False` al desaparecer, `forzar_fotos`, adopción con
  `convertir_actual`, sin fotos en ningún lado → sin activo).
- `tests/test_rutas_catalogo.py`: grid (filtros, orden, paginación, `sin_fotos`,
  archivados, búsqueda por color), ficha (producto con colores, plano, personaje,
  404), redirecciones a `#catalogo?ficha=…` de cada POST, `catalogo_color_agregar`
  (incluida la conversión), `quitar`, `mover`, `crear-con` (prefill), subir/eliminar
  foto con `variante`, `tienda_conectar` con `shopify_publico` (y la desconexión de la
  pública al conectar la API), la etiqueta en Configuración.
- `tests/test_migracion_0022.py`: los tres casos del §8 sobre una base temporal,
  con el mismo patrón que `tests/test_migracion_0012.py` (alembic sobre una base
  sembrada a mano en la revisión anterior).
Cambian: `tests/test_rutas_productos.py` (los asserts de la tabla «Importados sin
fotos» y de la lista pasan al grid/ficha; el resto igual), `tests/test_tareas_tiendas.py`
(`fuente` del conector), `tests/test_crear_compositor.py` si mira el selector,
`tests/test_i18n_catalogo.py` (nuevas traducciones), `tests/test_base_visual.py`
(la cabecera del catálogo con acciones).

## 16. Despliegue y carga de Happy Flops

1. `main` → VPS: `alembic upgrade head` (0022), reiniciar **los dos** servicios
   (conector e importador corren en el worker; rutas y plantillas en gunicorn).
2. Prueba local previa con el catálogo real: conectar `www.happyflops.com` como
   `shopify_publico` en el proyecto `happyflops` de la copia local, correr el worker,
   revisar la galería y varias fichas en el navegador integrado (capturas). Costo:
   ≈ 18 reglas de fidelidad (centavos).
3. En producción: conectar la misma tienda en el proyecto `happyflops` (un script
   con `tiendas.conectar` + `trabajos.encolar` de `tienda_sync_productos`, o desde la
   UI como admin) y esperar la sync (18 productos, 130 colores: unos minutos, con
   continuaciones si hace falta). Verificar contadores en la base y en la página.
4. Los activos viejos `horiginal` (3 colores a mano) y `happyblanket` quedan como
   están; Daniel decide si los elimina desde la ficha (irreversible, un clic). Los
   swaps viejos apuntan a ids ya huérfanos (`ho_sky`…) y no cambian.
5. Anotar en `CLAUDE.md` (párrafo del Catálogo), `CONTEXT.md` (vocabulario del §3) y el
   ADR 0005 («Colores como sub-activos en disco; una fila comercial por producto;
   Shopify público como conector de primera clase»).

## 17. Siguientes pasos que este diseño deja listos

- Precios por país desde Shopify Markets (`extra.precios_por_pais`) alimentando el
  precio por destino de Final edition.
- Colecciones como filtro de la galería.
- Sprints por producto rotando colores en el lote.
- Un CSV con columna «color» que entregue `extra.variantes`.
