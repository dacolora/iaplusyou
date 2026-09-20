# Alertas: una pestaña con todo lo que necesita atención — diseño

Fecha: 2026-09-20. Estado: aprobado (Daniel, 2026-09-20); plan `docs/superpowers/plans/2026-09-20-alertas.md`.
Agrega una pestaña **Alertas** al proyecto y un módulo de solo lectura que la
alimenta. No toca el worker de generación, los proveedores, el motor de
experimentos ni las tablas existentes: solo agrega una tabla pequeña para los
descartes y mueve a un módulo propio la lista de llaves de Puesta a punto.

## 0. Propósito y decisiones

Hoy lo que la plataforma le tiene que decir a la persona está regado: la lista
de alertas del Tablero (`tablero.alertas`) solo mira experimentos, Meta, tiendas
y Pixel; las llaves que faltan se ven solo entrando a Configuración › Puesta a
punto; el correo sin confirmar es un banner en todas las páginas; los prompts
listos sin generar, las sesiones de Crear en error, las piezas de sprint por
revisar, los avatares propuestos y las publicaciones orgánicas fallidas se ven
únicamente dentro de su pestaña; y varios avisos salen solo por correo, que
además se pierde cuando el servidor no tiene SMTP. No hay ningún sitio que diga
«esto es todo lo que te falta».

Decisiones (Daniel, 2026-09-20):

- **Una pestaña «Alertas»** en el sidebar, justo después de Tablero, con cuatro
  grupos: **Puesta a punto pendiente**, **Faltantes del proyecto**, **Esperan tu
  decisión** y **Fallos y errores**.
- **Se calcula al vuelo, no se almacena.** Cada alerta sale del estado real
  (llaves, tablas, archivos del proyecto) cada vez que se pide; lo único que se
  guarda es qué descartó la persona. Así nunca hay alertas viejas que ya no
  correspondan a la realidad: si algo se resuelve, desaparece solo.
- **Se puede descartar.** Una alerta descartada vuelve sola si la situación
  cambia (otra variable que falta, otro error, otra propuesta); un fallo
  descartado no vuelve porque su situación no cambia.
- **Los avisos dispersos se van a Alertas.** El Tablero muestra solo «N alertas →
  ver»; el banner del correo desaparece (queda solo el candado que bloquea
  conectar Meta o una tienda); Puesta a punto en Configuración sigue siendo el
  manual de cada llave, sin repetir la lista.
- **Contador en el menú**: burbuja con el número de alertas visibles en el ítem
  del sidebar, roja si alguna bloquea, ámbar si no.
- **Sin correo diario** (descartado el 2026-09-20). Los avisos por correo del
  motor (`notificaciones.avisar`) siguen como están.

## 1. Qué es una alerta

Un dict con estas llaves, siempre todas:

| llave | qué es |
|---|---|
| `clave` | id estable de la alerta dentro del proyecto: `<fuente>:<tipo>[:<entidad>]` (`llave:wavespeed`, `cuenta:correo:daniel`, `crear:error:cf_20260920_101010_1`, `sprint:revision:12`, `tablero:propuestas_pendientes:7`). Es lo que identifica un descarte. |
| `huella` | sha256 (hex) de la «situación» de la alerta: las variables que faltan, el texto del error, los ids pendientes. Si cambia, la alerta descartada vuelve a mostrarse. Cada fuente define qué entra en la huella (§2). |
| `nivel` | `bloquea` (rojo: algo no puede funcionar ahora mismo), `atencion` (ámbar: hace falta una decisión o algo importante falta) o `info` (gris: conviene, no urge). |
| `grupo` | `puesta_a_punto`, `faltantes`, `decision` o `fallos`. |
| `titulo` | una línea en español, con los números adentro («Faltan 2 variables de WaveSpeed»). |
| `detalle` | una o dos frases: qué pasa y qué hacer. Sin texto de excepciones, sin valores de llaves, sin tokens (`cola.sin_token` + `cola.recortar(…, 200)` sobre cualquier error que venga de una tabla). |
| `tab` | pestaña a la que lleva el botón «Ir a…»: `settings`, `catalogo`, `creativeflowplus`, `experimentos`, `sprints`, `nicho`. |
| `ancla` | id del elemento al que hacer scroll dentro de la pestaña (`llave-wavespeed`, `config-cuenta`, `config-correo`, `cf-<cf_id>`) o `None`. |
| `url` | URL completa cuando el destino es una página propia (sprint, estudio de nicho) o lleva query (`?exp=<id>#experimentos`); si está, gana sobre `tab`/`ancla`. |
| `entidad` | id de la entidad (experimento, sesión, sprint, estudio, publicación) o `None`. Solo informativo. |

Orden dentro de cada grupo: `bloquea` → `atencion` → `info`, y dentro del
mismo nivel el orden en que la fuente las produjo (las fuentes ya ordenan por
lo que más urge).

## 2. Fuentes

Todas leen estado que ya existe. Ninguna llama a un proveedor de pago ni a
Meta más allá de lo que ya hace el Tablero (`meta_conexion.estado`, cacheado
10 min; el Pixel solo desde caché).

### 2.1 Puesta a punto pendiente (`puesta_a_punto`)

| clave | condición | nivel | huella | destino |
|---|---|---|---|---|
| `llave:<id>` | tarjeta de `llaves.estado()` con `estado != "configurada"`, salvo la de Meta (`por_proyecto`, que ya cubre `tablero:meta_*`) | `bloquea`; `info` si la tarjeta es `opcional` | variables que faltan | `settings` / `llave-<id>` |
| `cuenta:correo:<usuario>` | cada cuenta rol `cliente` de este proyecto (`usuarios.por_cliente`) sin correo o con correo sin verificar | `bloquea` (sin correo verificado no se conecta Meta ni tienda) | `sin_correo` o `sin_verificar:<correo>` | `settings` / `config-cuenta` |
| `tablero:meta_sin_conectar`, `tablero:meta_roto`, `tablero:tienda_rota`, `tablero:pixel_sin_datos` | las mismas de `tablero.alertas()` | alta→`bloquea`, media→`atencion` | texto de la alerta | `settings` |
| `worker:parado` | última señal de vida del worker hace más de 30 min o nunca (§8) | `bloquea` | timestamp de esa última señal (así cada caída nueva reaparece) | `settings` / `config-puesta-a-punto` |

Títulos: «Falta la llave de {nombre}» / «Llave incompleta de {nombre}» con
detalle «Variables que faltan en el .env del servidor: A, B. {nota de la
tarjeta}»; «La cuenta {usuario} no tiene correo» / «Confirma el correo de la
cuenta {usuario}» con detalle «{correo}: abre el enlace que te mandamos o pide
uno nuevo en Configuración › Cuenta. Sin correo confirmado no puedes conectar
Meta ni una tienda»; «El worker no está corriendo» con detalle «Sin él no se
genera, no se lanza ni se publica nada. Última actividad: hace N min /
nunca».

### 2.2 Faltantes del proyecto (`faltantes`)

| clave | condición | nivel | huella | destino |
|---|---|---|---|---|
| `proyecto:guia_marca` | `marca.guia_efectiva(cliente)` vacía | `atencion` | vacía | `settings` / `config-marca` |
| `proyecto:producto` | ningún activo de categoría `producto` con al menos una foto (`catalogo_productos.listar(cliente, "producto")`, `referencias` no vacías) | `atencion` | vacía | `catalogo` |
| `proyecto:logo` | `clientes/<c>/logos/` sin imágenes | `info` | vacía | `settings` / `config-logos` |
| `proyecto:personaje` | ningún activo de categoría `personaje` | `info` | vacía | `catalogo` |
| `proyecto:tienda` | `tiendas.listar(cliente)` vacía | `info` | vacía | `settings` / `config-tienda` |
| `proyecto:correo_avisos` | SMTP configurado (`cuentas.smtp_configurado()`) y `proyectos.correo_notificaciones(cliente)` vacío | `atencion` | vacía | `settings` / `config-correo` |
| `proyecto:canal_organico` | `organico.disponibles(cliente)` vacía | `info` | vacía | `settings` / `config-canales-organicos` |
| `tablero:productos_sin_experimento` | la misma del Tablero | `info` | texto | `catalogo` |

La huella vacía es a propósito: un faltante descartado se queda descartado
hasta que se resuelva; cuando se resuelve, la alerta desaparece y su descarte
se poda (§3.4), de modo que una recaída meses después vuelve a verse.

Títulos: «El proyecto no tiene guía de marca» («Sin ella cada prompt sale sin
el estilo de la marca: súbela o genérala en Configuración › Identidad de
marca»), «No hay ningún producto con foto en el catálogo» («Crear y Sprints
necesitan al menos uno»), «Sin logos oficiales» («Con un logo el modelo no se
lo inventa»), «Sin personaje en el catálogo» («Crear solo hará videos de
producto»), «Sin tienda conectada» («Con una tienda los experimentos atribuyen
ventas reales»), «Sin correo de avisos» («El motor no tiene a quién avisarle
de propuestas, ganadores y rechazos»), «Sin canales orgánicos» («Las ganadoras
no se pueden publicar en Instagram, Facebook, TikTok ni YouTube»).

### 2.3 Esperan tu decisión (`decision`)

| clave | condición | nivel | huella | destino |
|---|---|---|---|---|
| `tablero:propuestas_pendientes:<exp>`, `tablero:tope_alcanzado:<exp>`, `tablero:ganador_sin_publicar:<exp o ->` | las mismas del Tablero | media→`atencion` | texto | `?exp=<id>#experimentos` o `settings` |
| `crear:prompt_listo` | sesiones de Crear en `prompt_listo` cuyo `creado_en` tiene más de 60 min (una sola alerta con el conteo; las recién armadas no molestan mientras la persona trabaja) | `atencion` | ids ordenados | `creativeflowplus` / `cf-<primer id>` |
| `sprint:ideas:<sid>` | sprint no completado con campañas en `ideas_propuestas` (cuenta sus ideas en `propuesta`) | `atencion` | ids de las ideas | página del sprint |
| `sprint:revision:<sid>` | sprint con piezas terminadas y `revision == "pendiente"` (`sprints.revision.resumen` → `sin_revisar > 0`) | `atencion` | conteo | página del sprint |
| `nicho:avatares:<eid>` | estudio en `revisando` con sub-avatares propuestos (`avatares_total − avatares_aprobados > 0`) | `atencion` | conteo | página del estudio |

Títulos: «{N} prompts listos sin generar en Crear», «{N} ideas por aprobar en
el sprint «{nombre}»», «{N} piezas por revisar en el sprint «{nombre}»», «{N}
avatares propuestos por aprobar en «{estudio}»».

### 2.4 Fallos y errores (`fallos`)

| clave | condición | nivel | huella | destino |
|---|---|---|---|---|
| `tablero:experimento_error:<exp>`, `tablero:anuncios_rechazados:<exp>` | las mismas del Tablero | alta→`bloquea` | texto | `?exp=<id>#experimentos` |
| `tablero:sin_metricas:<exp>` | la misma del Tablero | baja→`info` | **vacía** (el texto trae las horas y cambiaría cada hora) | `?exp=<id>#experimentos` |
| `crear:error:<cf_id>` | sesión de Crear en `error` con `creado_en` dentro de los últimos 30 días | `atencion` | texto del error | `creativeflowplus` / `cf-<cf_id>` |
| `organico:error:<pub_id>` | fila de `publicacion` en `error` con `actualizado_en` dentro de los últimos 30 días | `atencion` | texto del error | `experimentos` |
| `sprint:fallos:<sid>` | sprint no completado con piezas en `error` o con `qa.veredicto == "falla"` | `atencion` | ids de las piezas | página del sprint |
| `sprint:referencias:<sid>` | referencias con `analisis_estado == "error"` | `info` | ids | página del sprint |
| `nicho:error:<eid>` | estudio con `extra.ultimo_error` | `atencion` | texto del error | página del estudio |

Títulos: «Falló «{acción central recortada a 60}» en Crear» (detalle: el
error limpio y «Rearma el prompt o vuelve a generar»), «Falló la publicación en
{plataforma} de «{pieza}»» («Reintenta desde la pieza»), «{N} piezas fallidas
en el sprint «{nombre}»» («Regenéralas desde el sprint; cada una vuelve a
pasar por el costo»), «{N} referencias sin analizar en «{nombre}»», «Falló la
generación de avatares en «{estudio}»».

Los fallos más viejos de 30 días son historia, no alertas. Un fallo de
generación pagada es `atencion` (hace falta reintentar, no bloquea la
plataforma); un lanzamiento fallido o un anuncio rechazado por Meta sí es
`bloquea`, como ya lo trata el Tablero.

### 2.5 Cuando una fuente falla

Cada fuente corre en su propio `try/except`. Si revienta (Meta caída, una
tabla ilegible), en su lugar sale UNA alerta `revision:<fuente>` de nivel
`info`, grupo `puesta_a_punto`, título «No se pudo revisar {fuente}» y detalle
con solo el nombre de la clase de la excepción (`NombreError`), nunca el
mensaje — misma regla que `_calcular_tablero`. El resto de fuentes se calcula
igual. Una alerta `revision:*` desactiva la poda de descartes de esa pasada
(§3.4).

## 3. Módulo `alertas.py` (nuevo)

Solo lectura salvo la tabla de descartes; sin Flask; importable desde tests y
desde el worker (no lo usa hoy, pero nada lo impide).

```python
NIVELES = ("bloquea", "atencion", "info")
GRUPOS = ("puesta_a_punto", "faltantes", "decision", "fallos")
NOMBRES_GRUPO = {"puesta_a_punto": "Puesta a punto pendiente", "faltantes": "Faltantes del proyecto",
                 "decision": "Esperan tu decisión", "fallos": "Fallos y errores"}
NOMBRES_TAB = {"settings": "Configuración", "catalogo": "Catálogo", "creativeflowplus": "Crear",
               "experimentos": "Experimentos", "sprints": "Sprints", "nicho": "Nicho"}
DIAS_FALLOS = 30
MINUTOS_PROMPT_LISTO = 60
MINUTOS_WORKER = 30

def calcular(cliente, ahora_iso=None) -> list[dict]       # todas, ordenadas (§1), sin mirar descartes
def visibles(cliente, ahora_iso=None) -> dict              # {"visibles": [...], "descartadas": [...], "resumen": {...}}
def resumen(lista) -> dict                                 # {"n", "bloquea", "atencion", "info"} sobre una lista
def descartar(cliente, clave, huella) -> None              # upsert en alerta_descartada
def restaurar(cliente, clave) -> None                      # borra la fila
def huella(*partes) -> str                                 # sha256 hex de "|".join(str(p))
```

### 3.1 `calcular`

Recorre `FUENTES`, una lista de `(nombre, función)` — `llaves`, `cuentas`,
`worker`, `tablero`, `proyecto`, `crear`, `organico`, `sprints`, `nicho` — y
concatena lo que cada una devuelve, envuelta como dice §2.5. Luego asigna
`grupo` (las de `tablero` se reparten por `tipo` según las tablas de §2) y
ordena. Las fuentes reciben `(cliente, ahora)` y devuelven listas de dicts ya
completos; `_alerta(...)` es el constructor que rellena `ancla=None`,
`url=None`, `entidad=None`.

La fuente `tablero` es `tablero.alertas(cliente, ahora_iso)` traducida: `tipo`
→ `clave = f"tablero:{tipo}:{experimento_id or '-'}"`, nivel por el mapa
alta/media/baja → bloquea/atencion/info, `url = f"?exp={id}#experimentos"`
cuando hay experimento, `tab` tal cual si no. No se reescribe ninguna regla
de experimentos: la única lógica es en `tablero.py`.

### 3.2 `visibles`

`calcular()` menos las alertas que tienen una fila en `alerta_descartada` con
la **misma clave y la misma huella**. Devuelve también `descartadas` (las
alertas actuales que sí coinciden con una fila, con su `descartada_en`, para
el desplegable «Descartadas») y `resumen` de las visibles.

### 3.3 Descartar y restaurar

`descartar` hace upsert de `(cliente, clave) → huella, descartada_en`; si la
alerta vuelve con otra huella se muestra otra vez y un nuevo descarte
sobrescribe la fila. `restaurar` borra la fila. Ninguna de las dos calcula
nada.

### 3.4 Poda de descartes huérfanos

Dentro de `visibles()`: las filas de `alerta_descartada` del proyecto cuya
`clave` no está en el resultado de `calcular()` se borran, salvo que esa
pasada tenga alguna alerta `revision:*` (una fuente caída haría desaparecer
sus alertas y se perderían descartes válidos). Es idempotente y barato (una
consulta + un `DELETE … WHERE clave IN (…)`), y es lo que hace que un faltante
con huella vacía vuelva a verse si reaparece meses después.

## 4. Datos: tabla `alerta_descartada` (migración 0014)

```
alerta_descartada
  cliente        String(80)   PK
  clave          String(200)  PK
  huella         String(64)   NOT NULL
  descartada_en  String(19)   NOT NULL
```

Declarada en `db.py` como las demás. No se usa `kv` porque un blob JSON con
lectura-modificación-escritura pierde descartes cuando dos procesos de
gunicorn escriben a la vez; con PK compuesta el upsert es atómico.

## 5. Rutas, context processor y caché (`dashboard.py`)

- `POST /cliente/<cliente>/alertas/descartar` (form `clave`, `huella`) →
  `alertas.descartar`, `invalidar_alertas(cliente)`, flash «Alerta descartada»,
  redirect a `ver_cliente` con `_anchor="alertas"`.
- `POST /cliente/<cliente>/alertas/restaurar` (form `clave`) → `alertas.restaurar`,
  invalidar, redirect igual.
- Ambas pasan por `_guard_por_cliente` como cualquier ruta con `<cliente>`;
  `clave` se valida contra `^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$` y `huella` contra
  `^[0-9a-f]{64}$` (400 si no).
- Context processor `_alertas_sidebar`: para toda petición con `cliente` en
  `view_args`, con sesión, que no sea JSON (`_quiere_json`) ni la landing
  pública (`landing_cliente`), devuelve `alertas_ctx` = el dict de
  `alertas.visibles(cliente)` **cacheado**. Lo usan el sidebar (burbuja), el
  Tablero (la línea «N alertas») y `_tab_alertas.html`. Si el cálculo falla,
  `{}` y un `print("[aviso] …NombreError")`, nunca una página caída.
- Caché en proceso `_ALERTAS_CACHE[cliente] = (monotonic, ctx)`, TTL
  `ALERTAS_TTL_S = 60`, con `_ALERTAS_LOCK`; `invalidar_alertas(cliente=None)` la
  vacía, y `invalidar_tablero` la llama también (las acciones que cambian
  experimentos ya invalidan el tablero). Como el tablero, es por proceso de
  gunicorn: aceptable. Descartar y restaurar invalidan siempre.

## 6. Pestaña, sidebar y navegación

- `_sidebar.html`: ítem `data-tab="alertas"` después de Tablero, ícono de
  campana; a la derecha del texto, `<span class="sidebar-burbuja …">N</span>`
  con clase `bloquea` (roja) si `alertas_ctx.resumen.bloquea > 0`, si no ámbar;
  no se pinta cuando `n == 0`. En modo plegado la burbuja se ve sobre el ícono.
- `cliente.html`: panel `tab-alertas` con `{% include "_tab_alertas.html" %}` y la
  clave `alertas` en el mapa de paneles del JS.
- `_tab_alertas.html`: cabecera «Alertas» con el resumen («2 bloquean · 5 piden
  atención · 3 informativas»; «Todo en orden» si no hay ninguna visible); una
  sección por grupo en el orden de `GRUPOS`, omitida si está vacía; cada
  alerta es un `<li class="alerta alerta-{nivel}">` con chip de nivel
  («bloquea» / «atención» / «info»), `titulo`, `detalle`, botón «Ir a {pestaña}
  →» (nombre de `alertas.NOMBRES_TAB`, que reemplaza al `nombres_tab` local de
  `_tab_tablero.html`) y un `<form>` «Descartar» con `clave` y `huella`. Debajo, un `<details>`
  «Descartadas (N)» con cada una y su botón «Restaurar». Sin JS propio salvo el
  de navegación.
- Navegación: los enlaces con `data-ir-tab` funcionan como los del Tablero
  (activan la pestaña sin recargar); si además traen `data-ancla`, tras activar
  hacen `scrollIntoView` del elemento con ese id. Los que tienen `url` son
  enlaces normales. El script se mueve de `_tab_tablero.html` a `cliente.html`
  (una sola copia para las dos pestañas, con selector `[data-ir-tab]`).
- Anclas nuevas para que el scroll tenga adónde llegar: `id="cf-{{ item.id }}"`
  en cada tarjeta de Crear, `id="config-marca"` en el `<h2>` de
  `_seccion_marca.html`, `id="config-logos"` en «Logos oficiales».

## 7. Qué cambia en lo existente

- **Tablero** (`_tab_tablero.html`): la sección Alertas pasa a una línea:
  «{n} alertas necesitan tu atención → Ver Alertas» (enlace `data-ir-tab="alertas"`)
  o «Sin alertas. Todo en orden.», leída de `alertas_ctx`; si `alertas_ctx` no
  vino (el cálculo falló), «No se pudo calcular las alertas». `_calcular_tablero`
  deja de calcular la parte `alertas` (y `tb.alertas` desaparece del contexto);
  `tablero.alertas()` sigue existiendo porque ahora lo consume `alertas.py`.
- **Banner del correo** (`base.html`): se elimina el bloque `cuenta-banner` y su
  CSS. La alerta `cuenta:correo` lo reemplaza y `_requiere_correo_verificado`
  sigue bloqueando con su flash.
- **Puesta a punto → módulo `llaves.py` (nuevo)**: `SERVICIOS_LLAVES`,
  `NOTA_META_AGENCIA`, `PASOS_META_AGENCIA` y `_estado_llaves` salen de
  `dashboard.py` a `llaves.py` (`llaves.SERVICIOS`, `llaves.estado(...)`, misma
  firma y mismo resultado); `dashboard.py` conserva los nombres viejos como
  alias (`SERVICIOS_LLAVES = llaves.SERVICIOS`, `_estado_llaves = llaves.estado`)
  para no tocar tests ni plantillas. `alertas.py` importa `llaves`, nunca
  `dashboard`.
- **Tarjeta WaveSpeed** en `llaves.SERVICIOS`, después de Anthropic: id
  `wavespeed`, «WaveSpeed (videos e imágenes de Crear)», variables
  `["WAVESPEED_API_KEY"]`, costo «por segundo de video y por imagen: el precio
  se muestra antes de cada generación», url `https://wavespeed.ai/`, pasos
  (cuenta, saldo, API Keys, pegar en el .env, reiniciar los dos servicios),
  nota «Sin ella no se genera ningún video ni imagen en Crear ni en Sprints».
  **Higgsfield** pasa a `opcional: True` con nota «Solo la usa el flujo viejo
  «Nueva idea»; Crear no la necesita». Ambas se ven en Configuración con el
  mismo estilo de siempre.
- `usuarios.por_cliente(cliente)`: cuentas rol `cliente` de ese proyecto (sin
  hash), nueva función pequeña.
- `CLAUDE.md`: párrafo «Alertas» (qué es, dónde vive, la regla de calcular al
  vuelo + descartes con huella, y que las llaves viven en `llaves.py`).

## 8. Worker parado

Última señal de vida = el más reciente entre `kv["ultimo_sprint_qa_pendientes"]`
(la periódica de 5 min que el bucle del worker marca al encolarla) y
`MAX(tarea.iniciada_en)`. Si no existe ninguno → «El worker no está corriendo
(nunca ha corrido)»; si es más viejo que `MINUTOS_WORKER = 30` → «… Última
actividad: hace N min». 30 y no 15 porque el worker es de un solo hilo y una
render larga o una sincronización de tienda lo tiene ocupado sin pasar por el
bucle. Huella = ese timestamp: cada caída nueva reaparece aunque la anterior
se haya descartado.

## 9. Seguridad y disciplina del proyecto

- Ningún valor de llave sale de `llaves.estado` (sigue mirando solo
  `bool(os.environ.get(var))`); las alertas de llaves nombran variables, no
  valores.
- Textos de error que llegan a una alerta pasan por `cola.sin_token` y
  `cola.recortar(…, 200)`; una fuente caída reporta solo `NombreError`.
- Nada de este diseño gasta créditos, lanza tareas, publica ni llama a un
  proveedor: es lectura de estado más una tabla de descartes.
- Las rutas nuevas quedan bajo `_guard_por_cliente`; los formularios son POST
  con la cookie de sesión (SameSite Lax), como el resto.

## 10. Pruebas

- `tests/test_alertas.py` (módulo, con la base temporal de `conftest`):
  cada fuente con su estado simulado por `monkeypatch` (llaves presentes /
  ausentes / opcional; cuentas sin correo y sin verificar; tablero con las
  tres severidades y `sin_metricas` con huella vacía; faltantes uno por uno;
  prompts listos recientes vs de hace 2 h; sesión en error de hace 40 días
  excluida; sprint con `sin_revisar`, `error`, `qa.falla`, referencias en
  error; estudio con propuestos y con `ultimo_error`; worker con kv fresco /
  viejo / ausente y con tarea `iniciada_en` reciente); una fuente que revienta
  → alerta `revision:*` con solo el nombre de la clase y el resto intacto;
  orden por grupo y nivel; `descartar` + `visibles` (misma huella oculta, otra
  huella muestra), `restaurar`, poda de huérfanos y poda desactivada cuando
  hay `revision:*`; `huella` determinista.
- `tests/test_rutas_alertas.py`: la pestaña pinta los cuatro grupos, el resumen
  y el vacío; POST descartar (redirect, flash, desaparece, invalida caché),
  POST restaurar, claves y huellas inválidas → 400; la burbuja del sidebar
  aparece con clase roja/ámbar y no aparece en 0, también en una página del
  Blueprint de Sprints; el context processor no corre para JSON ni para la
  landing.
- Actualizaciones: `test_rutas_tablero` (la sección es ahora la línea y
  `tb.alertas` ya no existe), `test_rutas_cuentas` (ya no hay banner; la alerta
  `cuenta:correo` aparece en Alertas), `test_rutas_configuracion` (tarjeta
  WaveSpeed presente, Higgsfield opcional; `dashboard._estado_llaves` sigue
  funcionando como alias), snapshot de migraciones si existe.

## 11. Fuera de alcance

- Correo diario o resumen por correo de las alertas (decidido que no).
- Historial de alertas resueltas.
- Alertas en el panel del administrador (por proyecto ya hay columnas de
  salud; una vista global de alertas es otro diseño).
- El flujo viejo «Nueva idea» (`prompts_pendientes.json`, `estado_videos.json`):
  su destino sigue abierto (memoria `proveedor-solo-wavespeed`); no genera
  alertas.
- Notificaciones push o en el navegador.
