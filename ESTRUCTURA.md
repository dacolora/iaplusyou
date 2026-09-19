# Mapa del repositorio (para leerlo en frío)

Este documento existe para que cualquiera —vos mismo dentro de seis meses, un socio,
alguien que entra al proyecto— entienda qué es esto, con qué está hecho, dónde guarda
las cosas y qué hace cada archivo, sin tener que adivinarlo leyendo código. Está
organizado por lo que cada pieza *hace*, no en orden alfabético, y explica cada término
técnico la primera vez que aparece.

Regenerado el 18 de septiembre de 2026 desde el commit `5e3f40d`. La versión anterior
(1 de septiembre) describía una arquitectura sin base de datos que ya no existe. Cuando
la estructura cambie mucho, vale más regenerarlo que confiar en él. La referencia
técnica que manda sigue siendo `CLAUDE.md`; este mapa es la puerta de entrada. La
misma información, con el diagrama interactivo y el inventario con buscador, está
dentro de la app en `/mapa` (plantilla `templates/mapa_codigo.html`, solo admin):
al regenerar uno, regenerar el otro.

## Si solo vas a leer una cosa

- **Qué es:** una fábrica de videos e imágenes para redes y pauta, con un botón de
  aprobación humana entre cada paso que cuesta dinero.
- **Con qué está hecho:** Python + Flask. Las páginas las arma el servidor con
  plantillas Jinja. No hay Angular, React, npm ni paso de build: un solo archivo CSS y
  JavaScript escrito a mano dentro de las plantillas.
- **Dónde guarda:** una base SQLite en un archivo (`data/creatv.db`, 19 tablas), archivos
  JSON por proyecto para lo más viejo, y Cloudflare R2 para todo lo pesado (fotos,
  videos, música).
- **Cuántos programas corren:** dos. `dashboard.py` es la web y `worker.py` es la cola
  que hace el trabajo caro. Solo se hablan a través de la tabla `tarea`.
- **La regla de oro:** nada que gaste créditos corre solo. Idea → prompts → imagen →
  video → publicación, y entre cada paso alguien aprueba. Al escribir código nunca se
  salta ni se auto-avanza un paso.

## La analogía del restaurante

Sirve para todo el resto del documento. Cada pieza del código tiene un papel:

| En el restaurante | En el código | Qué hace |
|---|---|---|
| **El cliente que pide** | El navegador: `templates/`, `static/style.css` | Manda formularios HTML y pregunta "¿cómo va mi pedido?" cada uno o dos segundos (`iniciarPolling()` en `base.html`). |
| **El mesero** | `dashboard.py` + `sprints/rutas.py` (el proceso web, gunicorn en producción) | Toma el pedido, revisa que tengas permiso sobre ese proyecto, calcula el precio, lo anota. **Nunca cocina.** |
| **La comanda en la barra** | La tabla `tarea` (`cola.py`, `trabajos.py`) | Una fila por pedido con un identificador fijo (proyecto + entidad + acción): un doble clic no duplica nada. |
| **La cocina** | `worker.py` + `tareas/` (el proceso worker, servicio systemd `creatv-worker`) | Un cocinero, un plato a la vez. Es el único que llama a los proveedores que cobran. Si se cae a mitad de un plato, la comanda vuelve a la barra. |
| **El recetario** | Los módulos de dominio: `creative_flow.py`, `final_edition/`, `sprints/`, `experimentos.py`, `tiendas.py`… | Las reglas del negocio. Los usan el mesero y la cocina por igual. |
| **Los proveedores** | Anthropic (Claude), WaveSpeed, fal.ai, Higgsfield, Gemini, Meta, las tiendas | Cobran por cada plato; Claude cobra centavos por cada consulta. |
| **El libro de cuentas** | SQLite `data/creatv.db` (`db.py`) | Estado, métricas y la cola misma. Lo comparten los dos procesos. |
| **Los cuadernos viejos** | `clientes/<proyecto>/*.json`, `usuarios.json`, `registro_generaciones.csv` | El estado anterior a la base. Sigue funcionando y nadie lo tocó. |
| **La bodega** | Cloudflare R2 (`storage/r2_uploader.py`) | Fotos, videos, música. En la base solo queda la URL. |

## El flujo completo, en una línea

```
IDEA (texto) → 5 PROMPTS (Claude, centavos) → IMAGEN candidata → VIDEO → PUBLICACIÓN
                    ↑ aprobar uno          ↑ aprobar         ↑ aprobar   ↑ aprobar
```

Ese es el núcleo original (pipeline Higgsfield). Encima hay cuatro capas más nuevas,
todas con la misma regla de aprobación:

| Capa | Qué agrega | Dónde vive |
|---|---|---|
| **Crear (FlowPlus)** | Generar imagen o video nuevo a partir de referencias (personaje, producto, escena) y texto, con sonido nativo y música. También "cambiar producto" sobre una foto o video real. | `creative_flow.py`, `flowplus_*.py`, `tareas/flowplus.py`, `tareas/swap.py`, `providers/flowplus_modelos.py` |
| **Final edition** | Convertir un video aprobado en un anuncio por idioma y país: guion, voz, subtítulos, precio, CTA y música. | `final_edition/`, `tareas/final_edition.py` |
| **Sprints** | Planear un mes de contenido como matriz persona × producto × temporada, pedir ideas a Claude, producir por lotes, QA automático, revisión y entrega. | `sprints/`, `tareas/sprints.py` |
| **Experimentos** | Probar piezas en Meta Ads por país, con un decisor que dicta ganadores y perdedores y propone o ejecuta acciones según el modo. Catálogo y tiendas conectadas para atribuir ventas. Tablero con el resumen del mes. | `experimentos.py`, `lanzador.py`, `decisor.py`, `derivaciones.py`, `tiendas.py`, `conectores/`, `tablero.py`, `tareas/experimentos.py`, `tareas/tiendas.py` |

## Qué pasa cuando pulsas "Generar video" en Crear

Los demás botones caros (producir una final, lanzar un lote de sprint, lanzar un
experimento, importar un catálogo) siguen exactamente el mismo camino; solo cambian el
tipo de tarea y el módulo que hace el trabajo.

1. **Pulsas el botón.** El navegador manda un formulario normal a
   `/cliente/<proyecto>/creative_flow/<cf_id>/generar_video`. No hay ninguna app
   corriendo en tu computador, solo HTML (`templates/_tab_creativeflowplus.html`).
2. **El mesero revisa el pedido.** La ruta en `dashboard.py` comprueba que estés
   logueado y que el proyecto sea tuyo, estima el costo con
   `providers/flowplus_modelos.estimate_video` y anota en la base que la sesión está
   `video_generando` (`creative_flow.actualizar`). Todavía no se gastó nada.
3. **Deja la comanda en la barra.** `flowplus_lanzar.lanzar` → `trabajos.encolar` →
   `cola.encolar` inserta una fila `flowplus_video` en la tabla `tarea` con
   `max_intentos=1` y un `job_id` fijo. La ruta responde de inmediato. Si haces doble
   clic, la segunda vez no pasa nada: ya hay una tarea viva con ese id.
4. **Tu pantalla pregunta "¿cómo va?".** `iniciarPolling()` (en `base.html`) consulta
   `/trabajo/<job_id>/estado` cada uno o dos segundos y dibuja la barra de progreso
   con las etapas que reporta la tarea (`trabajos.consultar`).
5. **La cocina toma la comanda.** `worker.py` reclama la fila con `cola.reclamar` (un
   UPDATE condicionado: solo un proceso puede ganarla) y busca la función registrada
   para ese tipo en `tareas.REGISTRO`.
6. **Se cocina el plato caro.** `tareas/flowplus.ejecutar_video` llama al modelo en
   WaveSpeed, descarga el video, lo sube a R2, le mezcla la música elegida
   (`final_edition/mezcla`), guarda la `pieza` en SQLite y reporta cada etapa con
   `cola.reportar`. Aquí es donde se gastan los créditos.
7. **Listo: te toca decidir.** `cola.terminar` marca la fila; el sondeo lo ve y recarga
   la página, que ahora muestra el video esperando tu aprobación. Aprobarlo es otro
   clic y otra ruta. Si el worker se hubiera caído a la mitad, la fila volvería a
   `pendiente` a los 30 minutos (o a `error`, con la sesión marcada para que lo veas).

Las llamadas baratas (los cinco prompts de una idea, las estimaciones de costo) sí
salen directo del proceso web. El pipeline original de Higgsfield todavía corre en hilos
dentro del proceso web (`trabajos.iniciar`), no en el worker.

## Las seis pestañas y qué archivos las mueven

La página de un proyecto es `templates/cliente.html`: seis secciones, una por pestaña,
cada una incluida desde su propia plantilla. Las rutas van siempre bajo
`/cliente/<proyecto>/…` y cada una revisa en el servidor que el usuario tenga acceso a
ese proyecto (`usuarios.puede_acceder`).

| Pestaña | Qué hace la persona ahí | Plantillas | Rutas (bajo `/cliente/<c>/`) | Módulos | Tareas del worker |
|---|---|---|---|---|---|
| **Tablero** | Ver el gasto del mes, ventas atribuidas, ROAS, las cinco piezas ganadoras y alertas. | `_tab_tablero.html` | `tablero/mes.csv` | `tablero.py`, `experimentos.py` | Ninguna propia: lee los snapshots que dejan `exp_refrescar*`. |
| **Crear** | Generar imagen o video con referencias y texto; cambiar el producto en una foto o video real; las ideas del pipeline original; preparar y producir la final edition por país. | `_tab_flowplus.html` → `_tab_creativeflowplus.html`, `_tab_cambiar_calzado.html`, `_seccion_ideas.html`, `_flowplus_bandeja.html` | `creative_flow/*`, `flowplus/*`, `swap/*`, `idea/*`, `prompt/*`, `aprobar/<brief>` | `creative_flow`, `flowplus_prompt`, `flowplus_lanzar`, `referencias_flowplus`, `referencias_link`, `swaps`, `prompt_swap`, `prompts`, `estado`, `final_edition/` | `flowplus_video`, `flowplus_imagen`, `swap_generar`, `final_guion`, `final_producir` |
| **Sprints** | Planear el mes (personas × productos × temporadas), subir referencias, pedir ideas a Claude, lanzar el lote, revisar el QA, aprobar y entregar. | `_tab_sprints.html` + páginas propias `sprint_detalle`, `campana_referencias`, `campana_ideas`, `sprint_revision`, `sprint_entrega` | `sprints/*` (43 rutas del Blueprint) | `sprints/` (13 módulos) | `sprint_analizar_referencia`, `sprint_sugerir_personas`, `sprint_referencia_link`, `sprint_proponer_ideas`, `sprint_qa_pieza`, `sprint_qa_pendientes`, `sprint_empaquetar` |
| **Experimentos** | Armar un experimento con piezas y países, lanzarlo a Meta en pausa, activarlo, leer veredictos y propuestas del decisor, editar las reglas del motor, registrar la app de Meta; los anuncios sueltos legado. | `_tab_experimentos.html`, `_anuncios_sueltos.html`, `_form_reglas.html`, `_meta_conectar.html` | `experimentos/*`, `propuestas/*`, `ads/*`, `meta/*`, `config/reglas` | `experimentos`, `lanzador`, `decisor`, `modos`, `acciones`, `propuestas`, `derivaciones`, `ads`, `meta_conexion`, `meta_ads/` | `exp_lanzar`, `exp_refrescar`, `exp_decidir`, `exp_avanzar_todos`, `meta_publicar`, `meta_refrescar` |
| **Catálogo** | Productos como activos con fotos, mapa corporal, precio, moneda y URL de compra; importar desde CSV, URL o tienda; personajes y escenas de referencia. | `_tab_catalogo.html`, `_catalogo_lista`, `_catalogo_importar`, `_catalogo_sin_fotos`, `_catalogo_campos_comerciales`, `_maniqui`, `_seccion_personajes` | `productos/*`, `personaje/*`, `escena/*`, `producto_referencia/*`, `logos/*` | `catalogo_productos`, `tiendas`, `importador`, `conectores/`, `mapa_corporal` | `catalogo_importar`, `producto_vincular` |
| **Configuración** | Guía de estilo de la marca (con análisis de Claude), preferencias de Crear y de sonido, nombre visible, correo de avisos, tiendas conectadas, Pixel, y la "puesta a punto" que dice qué llaves faltan. | `_tab_settings.html`, `_seccion_marca.html`, `_meta_conectar.html`, `_comparacion_modelos.html` | `marca/*`, `preferencias*/guardar`, `config/*`, `nombre`, `meli/callback` | `marca`, `proyectos`, `tiendas`, `cifrado`, `meta_conexion`, `generador_prompts.analizar_marca` | `tienda_sync_productos`, `tienda_sync_pedidos` |

Fuera de esa página hay seis más: `index.html` (lista de proyectos, solo admin),
`panel.html` (entrada de un usuario cliente), `login.html`, `landing_cliente.html` (alta
de un proyecto nuevo por link público, ruta `/l/<proyecto>`), `legal.html` (privacidad,
términos y borrado de datos, que Meta exige) y `meta_elegir.html` (elegir cuenta
publicitaria y página después del OAuth).

## Dónde vive cada dato

Tres lugares. La regla para saber cuál: lo que nació con el motor de ecommerce o los
sprints está en SQLite; lo que ya existía antes sigue en JSON por proyecto; cualquier
archivo pesado está en R2 y aquí solo queda su URL.

### SQLite: `data/creatv.db` (19 tablas, definidas en `db.py`)

| Grupo | Tablas | Qué guardan |
|---|---|---|
| Cola | `tarea` | Tipo, payload, estado, intentos, prioridad, etapas y progreso de cada trabajo del worker. |
| Crear y piezas | `concepto`, `pieza` | Una sesión cf_… es un concepto (idea + referencias) con una pieza (clon limpio o final: URL, costo, capas de audio). |
| Experimentos | `experimento`, `experimento_pieza`, `metrica_snapshot`, `propuesta`, `evento` | El experimento, cada anuncio en Meta, las métricas acumuladas por anuncio, las propuestas del decisor y la bitácora de eventos. |
| Catálogo y tiendas | `tienda`, `producto`, `pedido` | Tiendas conectadas (credenciales cifradas), catálogo normalizado, pedidos con `utm_content`. |
| Sprints | `persona`, `temporada`, `sprint`, `campana`, `referencia`, `campana_pieza`, `sprint_evento` | El plan del mes y su producción. |
| Varios | `kv` | Valores sueltos. |

El esquema lo crean y actualizan las migraciones de `migrations/versions/` con
`venv/bin/alembic upgrade head`. La carpeta `data/` no se versiona.

### JSON y CSV en disco (el estado previo a la base)

| Archivo | Módulo dueño | Qué guarda |
|---|---|---|
| `clientes/<c>/proyecto.json` | `proyectos.py` | Nombre visible, preferencias, reglas, correo, país. Es el único JSON versionado. |
| `clientes/<c>/marca.json` y `marca/root.json` | `marca.py` | Guía de estilo y matriz de marca. |
| `clientes/<c>/productos.json` + `productos/<id>/` | `catalogo_productos.py` | Activos del catálogo con sus fotos. |
| `prompts_pendientes.json`, `estado_videos.json`, `conceptos_pendientes.json` | `prompts.py`, `estado.py`, `conceptos_imagen.py` | Pipeline original. |
| `swaps.json`, `referencias_pendientes.json` | `swaps.py`, `referencias_flowplus.py` | Swaps y la bandeja de referencias de Crear. |
| `meta_app.json`, `meta.json`, `.env`, `token_youtube.json`, `token_tiktok.json` | `meta_conexion.py`, uploaders | Secretos por proyecto, permisos 0600, ignorados en git. |
| `usuarios.json` (raíz) | `usuarios.py` | Login: usuarios con contraseña hasheada y rol. |
| `registro_generaciones.csv` (raíz) | `bitacora.py` | Bitácora append-only de generaciones y publicaciones. |
| `creative_flow_pendientes.json`, `ads.json` | — | Ya migrados a SQLite; quedan solo como respaldo. |

### Cloudflare R2 y caché local

Personajes, escenas, referencias, fotos del catálogo, imágenes candidatas, videos
crudos (solo sonido nativo) y mezclados, finales por país, miniaturas, pistas de música,
fotogramas y zips de entrega. Todo sube por `storage/r2_uploader.py`. Caché local
ignorada en git: `data/musica/`, `salidas/`, `clientes/<c>/sprints/`, `importaciones/`.

## El árbol de carpetas

```
iaplusyou/
├── dashboard.py              ← la web: 112 rutas, login, subida de archivos, encola trabajos
├── worker.py                 ← la cola: ejecuta tareas una a la vez, corre las periódicas
├── cola.py · trabajos.py     ← la comanda: tabla tarea, job_id anti doble clic, progreso
├── db.py                     ← las 19 tablas (SQLAlchemy Core) y la conexión SQLite
├── usuarios.py · proyectos.py · _json_store.py · bitacora.py · cifrado.py · notificaciones.py
├── creative_flow.py · flowplus_prompt.py · flowplus_lanzar.py · referencias_flowplus.py
│   referencias_link.py · banco_prompts.py · mapa_corporal.py · prompt_swap.py · swaps.py
│   generador_prompts.py · marca.py · catalogo_productos.py      ← Crear y cambiar producto
├── experimentos.py · lanzador.py · decisor.py · modos.py · acciones.py · propuestas.py
│   derivaciones.py · atribucion.py · tablero.py · ads.py · meta_conexion.py
│                                                              ← Experimentos y Tablero
├── tiendas.py · importador.py                                 ← catálogo y tiendas conectadas
├── prompts.py · estado.py · conceptos_imagen.py · higgsfield_client.py · publicador.py
│                                                              ← pipeline original (legado)
├── run_batch.py · revisar.py · subir_personaje.py · validar_marca.py · comparar_modelos.py
│   migrar_json_a_db.py · reconstruir_historial.py · informe.py  ← scripts de terminal
├── tareas/            ← lo que ejecuta el worker: flowplus, swap, final_edition, sprints,
│                         experimentos, meta, tiendas (33 tipos registrados)
├── final_edition/     ← guion → cortes → sonido → voz → musica → texto → render (+ mezcla, tipos)
├── sprints/           ← datos, estado, progreso, calendario, sugerencias, analisis, archivos,
│                         ideas, produccion, qa, revision, entrega, rutas
├── conectores/        ← base (el contrato), _http, shopify, woo, meli, csv_excel, url
├── providers/         ← clientes de IA: flowplus_modelos, wan3, wavespeed_*, fal_*, nano_banana,
│                         kling_o1, seedance, comparador, aspect_ratio, image/video_provider
├── uploaders/ · auth/ ← publicar en YouTube, Facebook/Instagram, TikTok; OAuth de una sola vez
├── storage/           ← r2_uploader.py, la bodega (Cloudflare R2)
├── meta_ads/          ← submódulo git: cliente sin estado de la Marketing API de Meta
├── templates/ (48)    ← base.html, cliente.html, _sidebar.html, _tab_*.html y parciales
├── static/            ← style.css (todo el CSS), fonts/, img/
├── migrations/        ← Alembic 0001–0008
├── tests/ (83)        ← pytest, con respuestas grabadas en tests/fixtures/
├── clientes/<c>/      ← una carpeta por proyecto (ver "Dónde vive cada dato")
├── data/              ← creatv.db y data/musica/ (no versionado)
├── deploy/            ← creatv-worker.service (unidad systemd del worker)
├── docs/              ← superpowers/specs y plans, investigacion/, adr/, agents/, meta/
└── CLAUDE.md · SETUP.md · ROADMAP.md · ESTRUCTURA.md · requirements.txt · .env.example
    alembic.ini · pytest.ini · .gitmodules · .gitignore
```

## "Quiero hacer X": qué archivo toco

| Quiero… | Toco… | Ojo |
|---|---|---|
| Agregar o cambiar un modelo de video o imagen en Crear | `providers/flowplus_modelos.py` (diccionarios `VIDEO` e `IMAGEN`: ruta, precio, límites, audio nativo) | La pestaña y la estimación de costo leen de ahí; no hay que tocar plantillas. |
| Cambiar cómo se arma el prompt de Crear | `flowplus_prompt.py` | El texto de la persona va tal cual; lo que se antepone es el bloque de fidelidad y la línea `SONIDO:`. |
| Cambiar lo que Claude escribe (prompts, guía de marca, guiones, ideas) | `generador_prompts.py`, `final_edition/guion.py`, `sprints/ideas.py` | Cada uno tiene su plantilla de prompt; las pruebas reemplazan la llamada real. |
| Agregar una pestaña | `templates/_sidebar.html`, `templates/cliente.html`, una `_tab_x.html` nueva, rutas en `dashboard.py` o un Blueprint como `sprints/rutas.py` | El contexto de cada pestaña lo arma `ver_cliente` en `dashboard.py`. |
| Agregar una acción lenta o que cueste créditos | Una función en `tareas/<área>.py` con `@registrar("tipo")`, importada en `tareas/__init__.cargar_todas`, encolada con `trabajos.encolar(..., max_intentos=1)` | Nunca en un hilo del proceso web; estimar el costo antes de mostrar el botón. |
| Agregar una tabla o una columna | `db.py` + una migración nueva en `migrations/versions/` + `alembic upgrade head` | La web y el worker comparten la base: reiniciar los dos servicios. |
| Cambiar las reglas por defecto del decisor | `decisor.py` (`REGLAS_DEFECTO`) y el formulario `templates/_form_reglas.html` | Un proyecto y un experimento pueden sobreescribirlas. |
| Conectar otro tipo de tienda | Un módulo en `conectores/` que implemente `conectores/base.Conector` y se registre por tipo | `tiendas.py` e `importador.py` no cambian. |
| Agregar un país, una voz o un estilo de música a final edition | `final_edition/tipos.py` (`PAISES`, `ESTILOS_MUSICA`) y `providers/fal_audio.py` (`VOCES`) | Las voces se verifican una por una contra fal antes de listarlas. |
| Cambiar el look de la interfaz | `static/style.css` (tokens en `:root`) y `templates/base.html` | Un solo CSS para todo. |
| Cambiar cada cuánto corren las periódicas | `worker.py` (`PERIODICAS`) | El orden dentro de un tick importa: pedidos de tiendas antes que experimentos. |
| Saber por qué un trabajo se quedó pegado | La tabla `tarea` (`estado`, `error`, `etapa_actual`) y `journalctl -u creatv-worker` en el VPS | Una tarea corriendo más de 30 min se re-encola o pasa a `error`. |
| Publicar cambios en producción | En el VPS: `git pull`, `pip install -r requirements.txt`, `alembic upgrade head`, `systemctl restart iaplusyou creatv-worker` | Siempre los dos servicios. Detalle en `CLAUDE.md` y `SETUP.md`. |
| Dar acceso a un cliente nuevo | El link público `/l/<proyecto>` crea proyecto y usuario; o `usuarios.crear` a mano | El rol `cliente` solo ve su proyecto; `admin` ve todos. |

## Archivo por archivo

Las líneas son las del 18 de septiembre de 2026. "Legado" significa que sigue enchufado
pero ya no es el camino principal; "terminal" son scripts que se corren a mano.

### Raíz: la app, los dos procesos y lo que comparten

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `dashboard.py` | 4 495 | La app web Flask: login, las 112 rutas, subida de archivos, el contexto de las seis pestañas y el encolado de trabajos. Corre sin auto-reloader a propósito, para no matar generaciones en curso. |
| `worker.py` | 145 | El segundo proceso: toma tareas de la cola una a la vez, encola las seis periódicas, recupera las colgadas a los 30 minutos y para limpio con SIGINT. Nunca correr dos contra la misma base. |
| `cola.py` | 182 | La cola persistente sobre la tabla `tarea`: encolar, reclamar (UPDATE condicionado), terminar, fallar, reportar progreso, recuperar colgadas. |
| `trabajos.py` | 321 | Adaptador de trabajos en segundo plano: hilos en memoria para el pipeline original (`iniciar`) o fila en la cola (`encolar`); `job_id` determinista contra el doble clic; `consultar` alimenta la barra de progreso por los dos caminos. |
| `db.py` | 411 | Las 19 tablas en SQLAlchemy Core (sin ORM) y la conexión a `data/creatv.db` en modo WAL. |
| `usuarios.py` | 79 | `usuarios.json` con contraseñas hasheadas y dos roles: admin entra a todo, cliente solo a su proyecto. |
| `proyectos.py` | 139 | `proyecto.json`: nombre visible (el id es la carpeta y no se toca), preferencias de Crear y sonido, reglas del motor, correo, país. |
| `_json_store.py` | 31 | Leer y escribir un JSON por proyecto; lo usan los once módulos que guardan estado en archivos. |
| `bitacora.py` | 29 | Log CSV append-only de cada generación, subida y publicación. |
| `cifrado.py` | 41 | Fernet con clave derivada de `FLASK_SECRET_KEY` para las credenciales de tiendas. Rotar la clave obliga a reconectar cada tienda. |
| `notificaciones.py` | 84 | Correos SMTP del motor (propuesta, ganador, rechazo de Meta, error de lanzamiento, tienda caída). Sin SMTP solo queda el evento. |
| `migrar_json_a_db.py` | 89 | Importó `creative_flow_pendientes.json` y `ads.json` a SQLite; idempotente. Terminal. |

### Crear (FlowPlus): referencias + texto → imagen o video nuevo

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `creative_flow.py` | 432 | Estado de cada sesión cf_… en SQLite (concepto + pieza): crear, actualizar, duplicar, archivar y las finales por idioma/país. Conserva la API de dicts que tenía cuando era un JSON. |
| `flowplus_prompt.py` | 243 | Arma el prompt final: texto de la persona tal cual + bloque de fidelidad por producto + línea `SONIDO:`. |
| `flowplus_lanzar.py` | 33 | Encola la generación con `max_intentos=1` y prioridad (5 pieza suelta, 3 lote de sprint). |
| `tareas/flowplus.py` | 286 | El trabajo real: llama al modelo en WaveSpeed, descarga, sube a R2, mezcla la música y guarda la pieza con su video crudo aparte. |
| `providers/flowplus_modelos.py` | 160 | El único registro de modelos de Crear (Wan 3.0, Kling O3 Pro, Seedance 2.5…): ruta, precio por segundo, límites, audio nativo, estimaciones. |
| `providers/wan3_client.py` · `wavespeed_common.py` | 142 | Wan 3.0 vía WaveSpeed, y la autenticación y el poll que comparten todos los clientes de WaveSpeed. |
| `referencias_flowplus.py` | 62 | La bandeja de referencias pendientes de Crear, que sobrevive a las recargas. |
| `referencias_link.py` | 156 | Trae una referencia desde un link (TrendTrack directo; TikTok, Instagram y YouTube con yt-dlp), saca fotogramas y la describe con Claude. |
| `banco_prompts.py` | 87 | Recetas de partida para no escribir la idea desde cero. |
| `mapa_corporal.py` | 133 | Zonas tocadas en el maniquí → instrucción de tamaño y ubicación del producto. |
| `generador_prompts.py` | 346 | Todas las llamadas de texto a Claude: 5 prompts por idea, conceptos de imagen, análisis de marca (visión), regla de fidelidad, prompt de creative flow. |
| `marca.py` | 77 | Guía de estilo y `root.json` de la matriz de marca; guía efectiva y negative prompt de cada generación. |
| `catalogo_productos.py` | 299 | Activos del catálogo: una carpeta por producto con varias fotos, metadatos en `productos.json` con flock. |
| `prompt_swap.py` | 203 | Los prompts de "cambiar producto" en un solo lugar y los tipos de producto válidos. |

### Cambiar producto (swap)

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `swaps.py` | 63 | Estado de los swaps en `swaps.json`. |
| `tareas/swap.py` | 400 | Genera la foto o el video con el producto puesto según el modelo elegido, con segunda pasada de mejora de calidad; sube a R2. |
| `providers/nano_banana_client.py` | 185 | Gemini 2.5 Flash Image directo (responde la imagen en la misma llamada). |
| `providers/wavespeed_imagen.py` | 165 | nano-banana-pro edit-ultra (edita y saca 4k/8k), bria para agrandar, Seedream. |
| `providers/kling_o1_client.py` | 43 | Kling O1 vía fal.ai: edita un video existente preservando movimiento. |
| `providers/wavespeed_client.py` · `wavespeed_video_edit.py` | 151 | Wan 2.7 Video Edit y los editores de video premium de WaveSpeed. |
| `providers/comparador_modelos.py` | 130 | Candidatos de edición vía fal.ai (Luma Ray3, Wan-2.2 Animate, Qwen Edit…). |
| `providers/aspect_ratio.py` | 76 | Detecta la proporción del original y la traduce a lo que acepta cada proveedor. |
| `providers/fal_client.py` | 91 | Helper encolar + poll para cualquier modelo de fal.ai. |
| `comparar_modelos.py` | 158 | Investigación: la misma foto contra varios modelos, lado a lado. Terminal. |

### Final edition: del clon aprobado al anuncio final por idioma y país

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `final_edition/__init__.py` | 471 | Orquestador: `preparar_guion` y `producir`; encadena las capas y guarda el estado con `creative_flow.crear_final`, una fila por destino. |
| `final_edition/guion.py` | 378 | Claude escribe el guion base en 5 bloques (hook → problema → producto → prueba → cta), lo localiza por país y genera variantes. |
| `final_edition/cortes.py` | 140 | ffmpeg `scdet`: cortes y plan de segmentos; helpers ffmpeg/ffprobe/duración. |
| `final_edition/sonido.py` | 39 | Claude sugiere qué se oye en la escena (campo de Crear). |
| `final_edition/voz.py` | 151 | Locución por bloque (ElevenLabs vía fal.ai), `atempo` si no cabe, marcas por palabra con Whisper. Fallar el primer bloque es fatal; los demás degradan. |
| `final_edition/musica.py` | 95 | Música de fondo con Stable Audio, cacheada en `data/musica/` y R2. |
| `final_edition/texto.py` | 362 | Overlays PNG con Pillow (hook, subtítulos, precio, CTA); el ffmpeg del VPS no trae `drawtext`. |
| `final_edition/render.py` | 211 | Un solo filtergraph de ffmpeg: segmentos con zoompan, overlays por tiempo, audio mezclado, AAC a 48 kHz. |
| `final_edition/mezcla.py` | 130 | La única fábrica del filtro de audio: sonido + voz + música con ducking, presets y loudnorm. También mezcla la música en Crear. |
| `final_edition/tipos.py` | 116 | Roles del guion, países con idioma y moneda, estilos de música, validación, fuentes TTF. |
| `tareas/final_edition.py` | 84 | Tareas `final_guion` y `final_producir`. |
| `providers/fal_audio.py` | 103 | Voz, transcripción y música vía fal.ai, con costo estimado. |

### Sprints: un mes de contenido como matriz persona × producto × temporada

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `sprints/rutas.py` | 950 | Blueprint con las 43 rutas; valida, delega y redirige. `contexto()` alimenta la pestaña. |
| `sprints/datos.py` | 763 | El único escritor de las siete tablas de sprints; validaciones de negocio. |
| `sprints/estado.py` · `progreso.py` | 135 | Estados derivados tras cada evento; progreso y cobertura (funciones puras). |
| `sprints/calendario.py` · `sugerencias.py` | 164 | Calendario comercial por país; personas sugeridas por Claude. |
| `sprints/analisis.py` · `archivos.py` | 166 | Análisis de referencias con Claude visión; guardado local + R2 y fotogramas. |
| `sprints/ideas.py` | 227 | El prompt maestro → ideas de video e imagen por campaña. |
| `sprints/produccion.py` | 388 | Lotes: costo estimado, una sesión de Crear por idea aprobada, lanzar, reintentar, regenerar, progreso. |
| `sprints/qa.py` | 188 | QA automático con Claude visión y ffprobe; nunca genera. |
| `sprints/revision.py` · `entrega.py` | 192 | Aprobar/rechazar, cerrar/reabrir; enlaces y zip de entrega en R2. |
| `tareas/sprints.py` | 265 | Siete tipos de tarea (analizar, sugerir, link, ideas, QA pieza, QA pendientes, empaquetar). |

### Experimentos: probar piezas en Meta Ads y dejar que el motor decida

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `experimentos.py` | 479 | Solo datos: experimento, piezas, snapshots, eventos; escrituras con el bloqueo de SQLite tomado antes de leer. |
| `lanzador.py` | 558 | Traduce un experimento a Meta (1 campaña → 1 conjunto por país → 1 anuncio por pieza, todo en pausa), guarda cada id apenas vuelve; refrescar métricas, escalar, cerrar. |
| `decisor.py` | 176 | Función pura: puerta de tráfico, puerta de ventas, ranking → ganador / perdedor / inconcluso / pendiente. |
| `modos.py` · `acciones.py` · `propuestas.py` | 354 | manual/semi/auto; pedir y ejecutar acciones respetando modo y tope; la tabla `propuesta`. |
| `derivaciones.py` | 478 | Máquina de estados asíncrona que produce piezas nuevas (re-ediciones y regeneraciones) y las mete al experimento. |
| `atribucion.py` | 93 | Liga pedidos con `utm_content` a la pieza que los generó. |
| `tablero.py` | 538 | Cálculos de solo lectura para Tablero: deltas de snapshots, serie de 30 días, top 5, alertas, CSV. |
| `ads.py` | 149 | "Anuncios sueltos" sobre el experimento legado de cada proyecto. Legado. |
| `meta_conexion.py` | 485 | Conexión con Meta por proyecto: `meta_app.json`, OAuth desde la app, `meta.json`, Pixel. No hay app de Meta compartida. |
| `tareas/experimentos.py` · `tareas/meta.py` | 566 | Lanzar, refrescar, decidir y avanzar derivaciones; publicar y refrescar anuncios sueltos. |
| `meta_ads/` (submódulo) | 338 | Cliente sin estado de la Marketing API: campaign, adset, targeting, ad, creative, insights, pixel, auth. Todo acepta `dry_run`. |

### Catálogo y tiendas

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `tiendas.py` | 430 | Tablas `tienda`, `producto`, `pedido`; credenciales cifradas; upsert (lo que desaparece se archiva); ventas por pieza. |
| `conectores/base.py` | 260 | El contrato `Conector` y la normalización: todas las fuentes devuelven las mismas claves. |
| `conectores/__init__.py` · `_http.py` | 138 | Registro por tipo con carga perezosa; HTTP común con timeout y un reintento. |
| `conectores/shopify.py` · `woo.py` · `meli.py` | 735 | Admin GraphQL de Shopify, REST v3 de WooCommerce, OAuth de MercadoLibre. |
| `conectores/csv_excel.py` · `url.py` | 485 | Catálogo desde archivo, o un producto desde la URL de su página (JSON-LD, Open Graph) con guardas contra SSRF. |
| `importador.py` | 541 | Producto normalizado → fila `producto` → activo del catálogo con fotos y regla de fidelidad de Claude; por tandas. |
| `tareas/tiendas.py` | 389 | Sync de productos y pedidos, importar, vincular, y las dos periódicas. |

### Pipeline original (Higgsfield): idea → 5 prompts → imagen → video → publicar

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `prompts.py` · `estado.py` · `conceptos_imagen.py` | 277 | El estado en JSON del pipeline original y del flujo "imagen primero". Legado. |
| `higgsfield_client.py` | 200 | Cliente Higgsfield (kling-2.1-pro, soul-reference) con estimaciones gratis antes de generar. Legado. |
| `providers/image_provider.py` · `video_provider.py` · `seedance_client.py` | 128 | Capa única "generame una imagen/un video con este proveedor". Legado. |
| `publicador.py` | 55 | Publica un brief aprobado en las plataformas que indique; nunca se dispara solo. |
| `uploaders/youtube_uploader.py` · `meta_uploader.py` · `tiktok_uploader.py` | 363 | YouTube Data API v3; Facebook e Instagram con el `meta.json` del proyecto (vivo); TikTok Content Posting API. |
| `auth/auth_youtube.py` · `auth_tiktok.py` | 175 | OAuth de una sola vez, en tu máquina; generan los `token_*.json`. Terminal. |
| `storage/r2_uploader.py` | 101 | Sube y borra en Cloudflare R2. Lo importan 13 módulos. Vivo. |

### Scripts de terminal

`run_batch.py` (lote de briefs con Higgsfield), `revisar.py` (revisar y publicar desde la
terminal), `subir_personaje.py`, `validar_marca.py` (un submundo nunca pisa un
invariante de la matriz), `reconstruir_historial.py` (rearma `swaps.json` desde la
bitácora), `informe.py` (informe verificable para una cuenta de cobro),
`briefs_example.json`.

### Plantillas, estilos, base, pruebas, documentación

| Qué | Dónde | Notas |
|---|---|---|
| Esqueleto y polling | `templates/base.html`, `_sidebar.html`, `cliente.html` | Fuentes, `style.css`, el menú lateral y `iniciarPolling()`. |
| Pestañas | `_tab_tablero`, `_tab_flowplus` → `_tab_creativeflowplus` (779 líneas, la más grande), `_tab_cambiar_calzado`, `_tab_sprints`, `_tab_experimentos`, `_tab_catalogo`, `_tab_settings` | Cada una con sus parciales `_catalogo_*`, `_sprint_*`, `_meta_conectar`, `_form_reglas`, `_seccion_*`. |
| Piezas reutilizables | `_idea_card`, `_idea_visual_card`, `_prompt_row`, `_imagen_row`, `_progreso_row`, `_video_card`, `_selector_productos*`, `_maniqui` | La fila de progreso es la que engancha el polling. |
| Estilos | `static/style.css` (1 564 líneas), `static/fonts/`, `static/img/` | Tokens en `:root`; los TTF los usa Pillow en final edition. |
| Base | `alembic.ini`, `migrations/env.py`, `migrations/versions/0001…0008` | 0001 crea el motor; 0006 los sprints; 0008 la prioridad de la cola. |
| Pruebas | `tests/` (83 archivos), `tests/conftest.py`, `tests/fixtures/` | `venv/bin/python3 -m pytest -q`; `-m "not slow"` salta los renders reales. |
| Documentación | `CLAUDE.md`, `SETUP.md`, `ROADMAP.md`, `docs/superpowers/specs` (8), `plans` (13), `docs/investigacion`, `docs/adr/0001`, `docs/agents`, `docs/meta` | `CLAUDE.md` es la biblia técnica. Cada bloque tiene spec y plan con fecha. |
| Despliegue | `deploy/creatv-worker.service`, `requirements.txt`, `.env.example` | La unidad de gunicorn y la config de nginx viven solo en el VPS. |

## Servicios externos y qué llave los abre

Todo sale de `.env` en la raíz más el `.env` y los JSON de cada proyecto. Configuración ›
"Puesta a punto" muestra cuáles faltan sin enseñar nunca el valor.

| Llave | Servicio | Para qué | Módulos |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (Claude) | Prompts, guiones, análisis con visión, ideas, QA, reglas de fidelidad, sugerencias. Centavos por llamada. | `generador_prompts`, `final_edition/guion`, `sprints/*`, `importador` |
| `WAVESPEED_API_KEY` | WaveSpeed AI | Los modelos de Crear, Wan 2.7 Video Edit, Nano Banana Pro, upscales, editores premium. | `providers/flowplus_modelos`, `wan3_client`, `wavespeed_*` |
| `FAL_KEY` | fal.ai | Voz, transcripción y música de final edition; Kling O1, Seedance 2.0 y comparadores. | `providers/fal_audio`, `fal_client`, `kling_o1_client`, `seedance_client`, `comparador_modelos` |
| `HF_API_KEY_ID`, `HF_API_KEY_SECRET` | Higgsfield | Pipeline original. | `higgsfield_client` |
| `GEMINI_API_KEY` | Google Gemini | Nano Banana para cambiar producto. | `providers/nano_banana_client` |
| `R2_*` (5 variables) | Cloudflare R2 | Todos los binarios y sus URLs públicas. | `storage/r2_uploader` |
| `META_REDIRECT_URI` + `meta_app.json` y `meta.json` por proyecto | Meta | Cada proyecto trae su propia app de Meta. No existe credencial global de Meta. | `meta_conexion`, `meta_ads/`, `lanzador`, `tareas/meta`, `uploaders/meta_uploader` |
| `client_secret_youtube.json` + token | YouTube Data API v3 | Publicar. | `uploaders/youtube_uploader`, `auth/auth_youtube` |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` + token | TikTok | Publicar (solo "Solo yo" mientras la app no esté auditada). | `uploaders/tiktok_uploader`, `auth/auth_tiktok` |
| `MELI_APP_ID`, `MELI_SECRET` | MercadoLibre | Conectar una tienda por OAuth. | `conectores/meli` |
| (cifradas en la tabla `tienda`) | Shopify, WooCommerce | Catálogo y pedidos. | `conectores/shopify`, `woo`, `tiendas`, `cifrado` |
| `SMTP_*` | Correo | Avisos del motor y de los lotes. Opcional. | `notificaciones` |
| `FLASK_SECRET_KEY` | — | Firma las sesiones y deriva la clave de cifrado de tiendas. | `dashboard`, `cifrado` |
| `CREATV_DB_URL`, `FLASK_DEBUG`, `ENABLE_*` | — | Ruta alternativa de la base, debug (nunca en el VPS), plataformas por defecto del pipeline original. | `db`, `dashboard`, `publicador` |
| `ffmpeg`, `ffprobe`, `yt-dlp` | Binarios del sistema | Fotogramas, cortes, render y mezcla; descarga de referencias. | `final_edition/*`, `sprints/archivos`, `referencias_link` |

## Qué está vivo y qué es legado

- **Núcleo actual:** SQLite + worker + cola; Crear con sonido y música; final edition;
  sprints; experimentos, decisor, derivaciones y tablero; catálogo, tiendas y
  conectores; conexión con Meta por proyecto y publicación en Facebook e Instagram.
- **Legado, enchufado pero no principal:** el pipeline Higgsfield (`prompts`, `estado`,
  `conceptos_imagen`, `higgsfield_client`, `image_provider`, `video_provider`,
  `seedance_client`), que sigue visible en Crear › ideas y corre en hilos del proceso
  web; "Anuncios sueltos" (`ads.py`, `tareas/meta`); los JSON ya migrados; publicar en
  YouTube y TikTok con tokens generados a mano.
- **Solo desde la terminal:** los scripts de la sección anterior y los dos `auth/`.

## Cómo se corre y cómo se despliega

En local (detalle en `CLAUDE.md` y `SETUP.md`):

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env            # llenar llaves
venv/bin/alembic upgrade head   # crea o actualiza data/creatv.db
python dashboard.py             # http://127.0.0.1:5050
venv/bin/python3 worker.py      # en otra terminal
venv/bin/python3 -m pytest -q   # pruebas
```

En producción (`app.creatvmachine.com`): un VPS con nginx delante de gunicorn
(servicio `iaplusyou`) y el worker (servicio `creatv-worker`, unidad en `deploy/`),
los dos leyendo `data/creatv.db`. Para publicar cambios: `git pull`, `pip install`,
`alembic upgrade head` y reiniciar **los dos** servicios. Los JSON de `clientes/`,
`usuarios.json` y `salidas/` no viajan por git: se copian con rsync.

## Glosario

| Palabra | Qué significa aquí |
|---|---|
| proyecto / cliente | La misma cosa. La interfaz dice "proyecto"; el código, las rutas y las carpetas dicen `cliente` a propósito para no romper nada. |
| sesión cf_… | Una generación de Crear: la idea, sus referencias y lo que salió. En SQLite es un `concepto` más una `pieza`. |
| clon (limpio) | El video o imagen generado sin texto encima; materia prima de la final edition y de los experimentos. |
| final | El clon convertido en anuncio para un idioma y país: narrado, subtitulado, con precio, CTA y música. |
| swap | Cambiar el producto en una foto o video real sin tocar nada más. |
| brief | Del pipeline original: un video con su prompt y las plataformas donde publicarlo. |
| experimento | Piezas probadas en Meta Ads con presupuesto por país: 1 campaña, 1 conjunto por país, 1 anuncio por pieza (`experimento_pieza`). |
| snapshot | Una foto de las métricas acumuladas de un anuncio; el Tablero resta dos snapshots para hablar de un período. |
| propuesta | Una acción que el decisor recomienda pero espera un clic humano, por el modo del experimento o por el tope de gasto. |
| sprint / campaña | El plan de un mes y cada celda persona × producto × temporada; una `campana_pieza` es una idea que se convierte en sesión de Crear. |
| activo del catálogo | Un producto con fotos y mapa corporal listo para citarse como @Producto; tiene su fila `producto` con precio y URL. |
| tarea / job_id | Una fila de la cola y su identificador determinista, el que el navegador sondea y el que impide lanzar lo mismo dos veces. |

## Cosas sueltas que vale la pena ordenar (al 18 sep 2026)

- Los respaldos del `.env` no están ignorados: `.gitignore` cubre `.env`, no `.env.*`.
  Una copia como `.env.bak_…` dejada en la carpeta se subiría con un `git add .` con
  llaves reales (el 18 de septiembre había una; ya no está). Conviene ignorar `.env.*`.
- `clientes/happyflops/swaps.json.respaldo_*` y `docs/propuestas/` (propuesta comercial
  con precios) tampoco están ignorados.
- Las fotos de producto de Happy Flops en `clientes/happyflops/productos/` y el
  submódulo privado `clientes/happyflops/marca` están versionados: si el repo se hace
  público, salen con él.
- `HO-rose/`, `HO-sky/` y `HOriginal/` en la raíz solo contienen un `.DS_Store`
  versionado cada una (hay cuatro `.DS_Store` en git en total).
- El docstring de `dashboard.py` todavía dice que "solo corre en tu máquina".
