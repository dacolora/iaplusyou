# Triple Whale con varias tiendas, una por país (spec 2026-10-08)

## 1. Por qué

happyflops tiene una tienda de Shopify por país y cada una vive en Triple Whale con su propio shop-id y su propia
llave de API (Daniel lo confirmó el 2026-10-08: «al parecer son diferentes»). La publicidad es la misma y se publica
en varios países, así que **un proyecto de Creatv tiene que poder conectar varias tiendas de Triple Whale**. Un
proyecto por país quedó descartado: partiría catálogo, piezas y sprints.

Hoy (`main` 90366336) todo cuelga del proyecto: la tabla `triple_whale` tiene una fila por `cliente`, y las copias
`tw_anuncio_dia`, `tw_tienda_dia` y `tw_producto_dia` no saben de qué tienda vino cada fila. Conectar otra tienda
reemplaza la anterior y borra sus cifras.

Lo que Daniel decidió en la conversación del 2026-10-08:

| Pregunta | Decisión |
|---|---|
| ¿Una llave para todas o una por tienda? | Una por tienda (cada tienda con su llave y su shop-id). |
| ¿Una tienda puede cubrir varios países? | No: cada tienda vende a su país. |
| ¿Cómo se ve la pestaña? | Selector de tienda arriba más «Todas», que suma; todo en USD. |
| ¿Las tiendas comparten cuenta de Meta? | No se sabe: por ahora una, pero tiene que funcionar si hay más. |
| Lo demás | «Haz lo mejor para la experiencia del usuario», sin más preguntas. |

## 2. Qué cambia para la persona

- En la pestaña Triple Whale ve la lista de **tiendas conectadas**, cada una con su bandera, país, dominio, estado y
  última copia. Abajo, «+ Agregar otra tienda» con llave, dominio y país.
- El **país se adivina por el dominio** (`happyflops-norge.myshopify.com` → Noruega) y queda elegido en el
  formulario; la persona lo confirma o lo cambia. Una tienda ya conectada puede cambiar de país sin perder sus cifras.
- Arriba del panel hay un **selector de tienda**: «Todas las tiendas» (por defecto) o una sola. Con una sola tienda
  conectada no aparece selector.
- En «Todas», debajo de los indicadores de la tienda aparece **«Por tienda»**: ingresos, pedidos, gasto, MER y la
  variación contra el periodo anterior de cada país, para ver dónde poner presupuesto.
- Moneda, modelo y ventana de atribución son **del proyecto** y valen para todas las tiendas. La moneda por
  defecto sigue siendo USD (Daniel: «todas en USD»).
- Los experimentos con atribución Triple Whale toman las ventas de **la tienda del país de cada conjunto**.
- Los correos de avisos (ganadores, cansados, perdedores, sin ventas) salen **una vez por proyecto**, sobre «Todas».

## 3. Datos (migración 0032)

### 3.1 Tabla nueva `tw_tienda`

Una fila por tienda conectada. Columnas: `id`, `cliente` (index), `creado_en`, `actualizado_en`, `pais` (String(2),
ISO 3166-1 alfa-2 en mayúsculas, nullable: una tienda migrada cuyo país no se pudo adivinar), `dominio`
(String(200), normalizado con `triple_whale.normalizar_dominio`), `llave` (Text, Fernet), `zona_horaria`,
`estado` (`conectada` | `error`), `error` (Text), `ultima_sincronizacion` (String(19)), `extra` (JSON:
`backfill_desde`, `ultimo_resumen`, `gasto_7d`).

Restricciones: `UNIQUE(cliente, dominio)` y un índice único parcial `(cliente, pais) WHERE pais IS NOT NULL` (una
tienda por país; varias sin país se permiten mientras se eligen).

Único escritor: `triple_whale_tiendas.py` (regla 5 de CLAUDE.md).

### 3.2 La tabla `triple_whale` pasa a ser los ajustes del proyecto

Sigue una fila por proyecto con `moneda`, `modelo_atribucion`, `ventana_atribucion` y `extra` (que conserva
`avisados` y `aviso_sin_ventas`: los avisos son del proyecto, §7). Sus columnas `llave`, `dominio_tienda`,
`zona_horaria`, `estado`, `error` y `ultima_sincronizacion` **se dejan de leer y de escribir** pero no se borran ni
se vacían: si hubiera que volver al despliegue anterior, la conexión vieja sigue entera. La fila existe mientras
haya al menos una tienda; quitar la última tienda la borra junto con las copias (como el «Desconectar» de hoy).

### 3.3 Las copias diarias llevan la tienda

`tw_anuncio_dia`, `tw_tienda_dia` y `tw_producto_dia` ganan `tienda_id` (Integer, NOT NULL, sin FK declarada, igual
que el resto de la base). Las restricciones únicas pasan a ser:

- `tw_anuncio_dia`: `(cliente, tienda_id, canal, ad_id, fecha)`; índice `(cliente, tienda_id, fecha)` además del
  `(cliente, fecha)` que ya existe.
- `tw_tienda_dia`: `(cliente, tienda_id, fecha)`.
- `tw_producto_dia`: `(cliente, tienda_id, producto_id, fecha)`; índice `(cliente, tienda_id, fecha)`.

Se usa `tienda_id` y no `pais` como clave para que cambiar el país de una tienda no toque sus cifras.

`tw_evaluacion` no cambia de esquema: el alcance va en `extra.tienda_id` (None = todas) y `extra.pais`.

### 3.4 Migración de lo que ya hay

Por cada fila de `triple_whale` con `llave` no nula:

1. Inserta su `tw_tienda` con `dominio = dominio_tienda`, la misma `llave` cifrada (no se descifra), `zona_horaria`,
   `estado`, `error`, `ultima_sincronizacion`, `extra` = `{backfill_desde, ultimo_resumen, gasto_7d}` de la fila
   vieja y `pais = adivinar_pais(dominio)` (§4.2; None si no se reconoce).
2. Pone ese `tienda_id` en todas las filas de las tres copias de ese `cliente`.

Filas de las copias de un `cliente` sin conexión se borran (huérfanas). Después de llenar `tienda_id` se recrean las
tablas con la columna NOT NULL y las restricciones nuevas (`batch_alter_table`, SQLite). `downgrade` deshace todo:
quita `tienda_id` (borrando antes las filas de toda tienda que no sea la más vieja de su proyecto, para que la
restricción vieja quepa) y borra `tw_tienda`. Se ensaya en una copia de la base de producción antes de desplegar.

## 4. Conexión (`triple_whale_tiendas.py`)

### 4.1 Funciones

- `ajustes(cliente)` → dict de la fila del proyecto (`moneda`, `modelo_atribucion`, `ventana_atribucion`, `extra`,
  `actualizado_en`) o None.
- `tiendas(cliente)` → lista de dicts SIN llave (`id`, `pais`, `dominio`, `zona_horaria`, `estado`, `error`,
  `ultima_sincronizacion`, `extra`, `creado_en`), ordenadas por país y luego por id.
- `tienda(cliente, tienda_id)` → una (verificando el `cliente`, para el aislamiento) o None.
- `tienda_de_pais(cliente, pais)` → la tienda de ese país o None.
- `obtener(cliente)` → se conserva para quien solo pregunta «¿hay Triple Whale?»: los ajustes más `tiendas`, o None
  si no hay ninguna tienda. `url_tags`/`kw_url_tags` siguen igual (hay tags si hay al menos una tienda).
- `obtener_llave(cliente, tienda_id)` → la llave descifrada de esa tienda.
- `agregar(cliente, llave, dominio, pais, moneda=…, modelo=…, ventana=…)` → id. Si el proyecto no tenía ajustes,
  los crea con los valores dados; si ya tenía, **ignora** moneda/modelo/ventana (son del proyecto y se cambian en
  Ajustes). Si ya hay una tienda con ese dominio, reemplaza su llave y país (reconectar) y la deja `conectada`. Si
  el país ya lo usa OTRA tienda, lanza `PaisOcupado` (la ruta lo dice en palabras).
- `cambiar_pais(cliente, tienda_id, pais)` → mismo control de país ocupado; no toca copias.
- `actualizar_tienda(cliente, tienda_id, **campos)` y `actualizar_extra_tienda(cliente, tienda_id, cambios)` (toma
  la fila y escribe en la misma transacción, regla 5).
- `actualizar_extra(cliente, cambios)` → sigue escribiendo en el `extra` del proyecto (avisos).
- `cambiar_ajustes(cliente, …)` → igual que hoy; si algo cambia borra las copias de **todas** las tiendas y vacía el
  `backfill_desde` de cada una.
- `quitar(cliente, tienda_id)` → borra esa tienda y sus copias; si era la última, borra también la fila del
  proyecto. Las evaluaciones con IA se conservan siempre.
- `conectadas()` → `[(cliente, tienda_id)]` con llave, para la sincronización periódica.
- `firma(cliente)` → `(n tiendas, max(actualizado_en) de tiendas y ajustes)`: para la clave de caché del Tablero.

### 4.2 Países

- `adivinar_pais(dominio)`: compara el subdominio de Shopify (sin `.myshopify.com`) partido por `-`, `_` y `.`
  contra (a) los nombres de los países en inglés, español y en su idioma local (Babel: `Locale(...).territories`
  para `en`, `es`, `nb`, `sv`, `da`, `fi`, `de`, `fr`, `it`, `nl`, `pt`, `pl`), normalizados sin acentos ni
  espacios, y (b) un sufijo final de dos letras que sea un código ISO de país (`happyflops-se`). Devuelve el código
  o None. Puro y con pruebas: `happyflops-norge` → NO, `happyflops-sverige` → SE, `shop-de` → DE,
  `happyflops` → None.
- `paises_opciones(locale)`: `[(código, «🇳🇴 Noruega»)]` de todos los territorios de dos letras de Babel en el
  idioma de quien mira, ordenados por nombre. Es la lista del selector: no está limitada a los países de Final
  edition (`final_edition.tipos.PAISES`).
- `nombre_pais(codigo, locale)` y `bandera(codigo)` para pintar.

## 5. Sincronización

- `sync.sincronizar(cliente, tienda_id, desde=None, hasta=None, on_progreso=None, hoy=None)`: lo mismo que hoy pero
  con la llave, el dominio y el `extra` de esa tienda, y moneda/modelo/ventana de los ajustes del proyecto. Los
  `datos.reemplazar_*` reciben `tienda_id` y solo tocan las filas de esa tienda.
- `sync.sincronizar_si_hace_falta(cliente, tienda_id, minutos=30)`.
- Tareas (`tareas/triple_whale.py`):
  - `job_id_sync(cliente, tienda_id)` → `f"{cliente}__tw_sync__{tienda_id}"`.
  - `encolar_sync(cliente, tienda_id=None)`: con id encola esa; sin id encola todas las del proyecto. Devuelve
    cuántas quedaron en cola.
  - `tw_sincronizar` lleva `tienda_id` en el payload. Un error deja **esa** tienda en `error` con el motivo sin
    token (y sin la llave de esa tienda); las demás no se enteran.
  - `tw_sincronizar_todas` encola una por tienda conectada.
  - `syncs_en_curso(cliente)` → job ids vivos del proyecto, para las barras del panel.
- Al terminar la copia de una tienda, los avisos (§7) corren solo si no queda otra copia del mismo proyecto en cola
  o en curso: así la última que termina avisa una vez, con todo al día.

## 6. Lectura y panel

### 6.1 `triple_whale/datos.py`

Todas las lecturas reciben `tienda_id`: un entero lee esa tienda; `None` lee **todas** del proyecto.

- Con una tienda, igual que hoy, filtrando por `tienda_id`.
- Con todas, `tw_anuncio_dia` se agrega primero por `(canal, ad_id, fecha)`: las medidas de canal (`gasto`,
  `impresiones`, `clics`, `clics_salida`, `compras_canal`, `valor_canal`, `thruplays`, `vistas_3s`, `p25`…`p100`)
  con **MAX** entre tiendas y las del Pixel (`pedidos`, `ingresos`, `nc_*`, `sesiones`, `carritos`, `checkouts`)
  con **SUMA**; `con_pixel` con MAX. Si dos tiendas comparten la cuenta de Meta, el mismo anuncio llega igual por
  las dos y su gasto se cuenta una vez; si cada país tiene su cuenta, los `ad_id` no se repiten y MAX = el único
  valor. Las mismas reglas valen para `totales_por_anuncio`, `serie_anuncios`, `canales` y `rango`.
- `serie_tienda(cliente, None, …)` suma por día ingresos, pedidos, nuevos, reembolsos, cogs y utilidad; al `gasto`
  le resta el **gasto duplicado** de ese día (Σ por anuncio de `suma − máximo` de su gasto entre tiendas) y a la
  `utilidad_neta` se lo suma de vuelta. Así «Todas» cuenta una vez el gasto compartido y deja intacto el gasto que
  no viene de anuncios.
- `gasto_duplicado(cliente, desde, hasta)` → total del rango; mayor que 0 significa que hay cuentas compartidas.
- `top_productos(cliente, None, …)` agrupa por nombre normalizado (minúsculas, espacios colapsados): cada tienda de
  Shopify tiene sus propios `product_id` para el mismo producto. Con una tienda sigue por `producto_id`.
- `por_tienda(cliente, desde, hasta, desde_prev, hasta_prev)` → una fila por tienda con sus totales de tienda y su
  variación (para «Por tienda»).
- `totales_anuncio(cliente, tienda_id, canal, ad_id, desde, hasta=None)` con `tienda_id` obligatorio.

### 6.2 `triple_whale/panel.py` y la pestaña

- `contexto(cliente, dias, canal, tienda_id=None)`: si el `tienda_id` pedido no es del proyecto se ignora (todas).
  Con una sola tienda, `tienda_id` es esa. Devuelve además `tiendas`, `tienda_actual`, `por_tienda` (solo en
  «Todas» con 2+ tiendas), `gasto_duplicado` y `jobs_sync` (lista).
- `evaluar_periodo(cliente, dias, canal, tienda_id=None, hoy=None)` y `resumen_mes_tienda(cliente)` (Tablero:
  siempre «Todas»).
- `_tw_panel.html`: selector «Tienda» (`data-tw-param="tienda"`) junto a periodo y canal, con «Todas las tiendas
  (N)» y una opción por tienda con bandera y país (o el dominio si no tiene país). Bloque «Por tienda» como tabla
  compacta con scroll horizontal propio en el celular (regla 8). Si `gasto_duplicado > 0`: nota «Estas tiendas
  comparten cuenta publicitaria: el gasto de cada tienda incluye anuncios de los otros países. «Todas» lo cuenta
  una sola vez.» Viendo una sola tienda con gasto duplicado, la misma nota avisa además que el ROAS de cada anuncio
  allí solo cuenta las ventas de esa tienda.
- Una barra `data-poll-job` por cada copia en curso, con el país en la etiqueta.
- `_triple_whale_conectar.html`: tarjetas de tiendas (bandera, país, dominio, estado, error, última copia;
  «Probar», «Cambiar país» como `<details>` con el selector, «Quitar» con confirmación que dice que se borran las
  cifras de esa tienda). «+ Agregar otra tienda» (`<details>`, abierto si no hay ninguna) con llave, dominio y
  país; el país viene preseleccionado con lo que adivine un `fetch` al salir del campo dominio
  (`GET …/cfg_triple_whale/adivinar_pais?dominio=…`, JSON `{pais}`), y el servidor vuelve a adivinar si llega vacío.
  Si no hay ninguna tienda, el formulario trae también moneda (USD por defecto), modelo y ventana. Con tiendas,
  esos tres viven en «Ajustes de atribución (todas las tiendas)». Una tienda migrada sin país muestra un aviso
  «Elige el país de esta tienda» con su selector abierto.
- El JS de `_tab_triple_whale.html` recuerda el filtro `tienda` como ya recuerda `dias` y `canal`.

## 7. Avisos por correo

`avisos.revisar_y_avisar(cliente)` evalúa «Todas» (30 días), guarda la base en el `extra` del proyecto como hoy y
manda un solo correo. Evaluar por tienda daría perdedores falsos con una cuenta compartida (un anuncio de Suecia no
vende en la tienda de Noruega). Sin cambios en el texto del correo.

## 8. Evaluar con IA

- La ruta `evaluar` recibe `tienda` del formulario (lo que se está viendo). La muestra, los benchmarks y los
  productos salen de ese alcance; `extra` guarda `tienda_id` y `pais`. `tw_evaluar` lee `top_productos` con ese
  `tienda_id`.
- La lista de evaluaciones muestra el alcance de cada una («Noruega», «Todas las tiendas»). Precio, `max_intentos=1`
  y registro de gasto no cambian (regla 1).
- Sigue habiendo una evaluación a la vez por proyecto (`job_id_evaluar` igual).

## 9. Experimentos y Tablero

- `lanzador.refrescar`: para atribución `triple_whale`, por cada país de las piezas del experimento busca su tienda
  (`tienda_de_pais`); si el proyecto tiene **una sola** tienda, esa sirve para todos los países (comportamiento de
  hoy). Sincroniza cada tienda usada una vez (`sincronizar_si_hace_falta`, fuera del candado de Meta). Una pieza de
  un país sin tienda se queda con las ventas de Meta y deja **un** evento por experimento y país: «No hay tienda de
  Triple Whale para %(pais)s: se usan las ventas de Meta.» (sin repetirse en cada refresco: marca en el `extra` del
  experimento, como `aviso_moneda`).
- `_mezclar_ventas_triple_whale(cliente, ex, pz, snap, ajustes, tienda_id)` lee `totales_anuncio` de esa tienda; la
  regla de moneda usa la moneda de los ajustes.
- Clave de caché del Tablero (`dashboard.py`): agrega `triple_whale_tiendas.firma(cliente)`.

## 10. Rutas

Todas con `_mismo_origen()` en POST y el `cliente` en la URL (`_guard_por_cliente`); toda tienda se busca con
`tienda(cliente, id)` y si no es del proyecto se responde 404 (aislamiento).

| Ruta | Cambio |
|---|---|
| `POST cfg_triple_whale/conectar` | Agrega o reconecta una tienda: `llave_api`, `dominio_tienda`, `pais` (+ ajustes si es la primera). Prueba llave y SQL antes de guardar (como hoy). Encola la copia de esa tienda. |
| `POST cfg_triple_whale/probar` | Recibe `tienda_id`. |
| `POST cfg_triple_whale/pais` (nueva) | `tienda_id`, `pais`. |
| `GET cfg_triple_whale/adivinar_pais` (nueva) | `dominio` → `{"pais": "NO"}` o `{"pais": null}`. Solo lectura, sin llamar a nadie. |
| `POST cfg_triple_whale/ajustes` | Igual; encola la copia de todas. |
| `POST cfg_triple_whale/desconectar` | Recibe `tienda_id` y quita esa tienda. |
| `POST triple-whale/sincronizar` | Sin `tienda_id` trae todas; con él, esa. |
| `GET triple-whale/panel` | Acepta `tienda`. |
| `POST triple-whale/evaluar` | Acepta `tienda`. |

## 11. Textos

Todo texto nuevo pasa por el catálogo (regla 3): plantillas con `_()`, Python con `gettext`, y luego
`catalogo_i18n.py actualizar`, traducir al inglés con `docs/i18n/glosario.md` y `compilar`. Los nombres de país
salen de Babel en el idioma de quien mira.

## 12. Pruebas

- Migración: base con una conexión y copias → una `tw_tienda` con el país adivinado, todas las filas con su
  `tienda_id`, huérfanas borradas, `downgrade` vuelve al esquema anterior; idempotente sobre una base vacía.
- `adivinar_pais` con los casos de §4.2 y dominios con mayúsculas o `https://…/admin`.
- Conexión: agregar dos tiendas, país ocupado, reconectar el mismo dominio, cambiar país sin perder copias, quitar
  una (las copias de la otra intactas), quitar la última (borra ajustes), aislamiento (tienda de otro proyecto → 404).
- Sync: dos tiendas con dobles de `sql_query` → cada copia con su `tienda_id`; error en una deja la otra `conectada`;
  `tw_sincronizar_todas` encola una por tienda; avisos solo al terminar la última.
- Lectura en «Todas»: mismo `ad_id` en dos tiendas → gasto una vez, pedidos sumados; `ad_id` distintos → todo
  sumado; `serie_tienda` resta el gasto duplicado; productos con el mismo nombre en dos tiendas → una fila.
- Panel: selector solo con 2+ tiendas, «Por tienda», nota de gasto compartido, `tienda` ajeno ignorado.
- Lanzador: pieza NO con tienda NO usa sus ventas; pieza SE sin tienda (y 2 tiendas) queda con Meta y un evento
  único; proyecto con una tienda la usa para cualquier país.
- Mutaciones (revisor): quitar el MAX (sumar gasto) y la resta del gasto duplicado tiene que romper pruebas.
- Captura real de la pestaña con dos tiendas, en escritorio y en celular (regla 4 de «Cómo se trabaja»).

## 13. Fuera de este cambio

- Lanzar experimentos y finales en Noruega, Suecia y otros países europeos: `final_edition.tipos.PAISES` solo trae
  AR, BR, CL, CO, ES, MX, PE y US. Se anota como pendiente nuevo.
- Varias cuentas publicitarias de Meta por proyecto en la conexión de Meta de Creatv: hoy es una; Triple Whale ya
  funciona con una o varias (§6.1). Se anota como pendiente nuevo.
- Ninguna consulta SQL de Triple Whale ha corrido contra una tienda real (spec 2026-09-28 §9): sigue igual; la
  primera copia real de happyflops-norge después del despliegue es la prueba.
