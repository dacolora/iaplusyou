# Escala y monitoreo: muchos usuarios a la vez, y enterarse de cada error

Fecha: 2026-10-01. Pedido de Daniel: «necesitamos mejorar temas de cuando se conecten muchos
usuarios al tiempo… connection pooling, capa de caché, índices en la DB para no escanear la
tabla entera, CDN para los estáticos, pruebas de carga simulando 100 users a la vez, y algo
para revisar desde admin todos los logs y monitores, para enterarnos de todos los errores».
También preguntó por HookAce (Capafy) y PostHog: §9.

Regla de trabajo: **medir antes de cambiar**. Nada de esto se adivinó: cada cambio sale de un
perfil, un `EXPLAIN QUERY PLAN` o la prueba de carga, y cada uno tiene su prueba automática.

## 1. Cómo se midió

- `rendimiento/sembrar.py`: 10 proyectos `carga01…10` con 300 sesiones de Crear cada uno (85 %
  listas, 10 % error, 5 % generando con su tarea viva), un catálogo de 25 productos × 3 colores ×
  4 fotos, un gasto por pieza, 500 filas de cola por proyecto y 2 experimentos × 10 anuncios con un
  snapshot cada 2 h durante 14 días (33 600 snapshots). Base de 12 MB. Solo en una copia local;
  se niega si `PLATAFORMA_URL` no es local; `--limpiar` lo borra.
- Perfil con `cProfile` y conteo de consultas por ruta con el test client.
- Copia «antes» = `main` (`git archive HEAD`) con los MISMOS datos; «después» = esta rama.

Lo que encontró el perfil (una petición, máquina de 4 núcleos, sin carga):

| Ruta | Antes | Después |
|---|---|---|
| Página del proyecto `/cliente/<c>` | 1 023 ms · 134 consultas | 198 ms · 73 consultas |
| «Ver más» de Crear | 1 173 ms · 1 136 consultas | 35 ms · 14 consultas |
| Sondeo de una barra `/trabajo/<id>/estado` | 2,1 ms · 2 consultas | 1,9 ms · 2 consultas |
| Galería del catálogo | 43 ms · 42 consultas | 37 ms · 42 consultas |
| Panel del admin `/panel` | 415 consultas (2 por anuncio) | 15 consultas |

Las causas, de mayor a menor:

1. **El catálogo se leía del disco dos veces por TARJETA de Crear.** La revisión rápida de la
   doctrina busca el producto de cada pieza (`final_edition._producto` →
   `catalogo_productos.encontrar_por_id_o_nombre` → `listar()` dos veces: productos.json,
   proyecto.json y un `listdir` por producto y por color). El memo por tupla de `productos_ids`
   no guardaba los productos que ya no están en el catálogo. Con 25 productos × 3 colores y 300
   piezas: ~800 ms por carga.
2. **«Ver más» y los detalles no precargaban los trabajos vivos**: una consulta a la cola por
   tarjeta (la página ya tenía `con_vivos_precargados` desde el 2026-09-28; estas rutas no).
3. Por cada producto distinto de las tarjetas, `final_edition._fila_producto` volvía a cargar
   TODAS las filas comerciales del proyecto (`tiendas.por_activo`, una consulta cada vez).
4. `tiene_hija_b` recorría todas las sesiones por cada tarjeta (n²) y `gastos.estimar` se
   calculaba por tarjeta.
5. Babel volvía a analizar el locale en cada número (≈ 0,2 ms × 500) y Flask-Babel pasaba por
   varios proxies en cada `_()` (2 600 por carga, 18 % del tiempo de la página).

## 2. Índices

`rendimiento/auditar_indices.py`: un plugin de pytest que corre `EXPLAIN QUERY PLAN` sobre cada
consulta que la **app** manda durante toda la suite (las de los tests, las migraciones y el propio
auditor no cuentan) y escribe las que hacen `SCAN <tabla>` sin índice, con cuántas veces y la
línea que la mandó. Resultado (además de las tablas que no crecen):

| Consulta | Dónde | Índice (migración 0026) |
|---|---|---|
| Finales del proyecto, en CADA carga de la página | `creative_flow.finales_por_sesion` | `pieza(padre_pieza_id)` |
| Captions de Crear, en CADA carga | `doctrina.revisor.ultimos_captions` | `publicacion(pieza_id)` |
| Base del delta del Tablero: leía y ORDENABA todo el historial de cada anuncio | `experimentos.snapshots(ep, desde)` | `metrica_snapshot(experimento_pieza_id, tomado_en)` (el de solo `experimento_pieza_id` se queda: sirve a «la última foto» sin ordenar) |
| «Últimos cobros» del panel (todos los proyectos) | `admin.ultimos_cobros` | `gasto(creado_en)` |
| Borrar una sesión, un anuncio o un avatar: con `foreign_keys=ON` SQLite recorre la tabla hija entera | `creative_flow.eliminar`, `ads`, `nicho` | `experimento_pieza(pieza_id)`, `evento(experimento_pieza_id)`, `pedido(experimento_pieza_id)`, `avatar(padre_id)`, `sprint_evento(campana_id)` |
| Contadores de `/admin/referentes` | `referentes.datos.contar_imagenes` | `referente(fuente, estado_imagen)` |

Con los datos sembrados la diferencia es de milisegundos; lo que cambia es la forma: sin índice
el costo crece con TODAS las filas de TODOS los proyectos (los snapshots crecen 12 por anuncio y
día, para siempre). Medido: snapshots 1,7 → 0,16 ms por 20 anuncios; últimos cobros 0,32 → 0,03 ms.

Quedan sin índice, a propósito: `json_extract(extra, …)` de `guion_prompt`/`guion_video` (tablas
chicas; un índice de expresión exige cambiar la consulta), las periódicas del worker sobre
`experimento`/`sprint`/`campana_pieza` (cada 5–60 min, tablas chicas).

`tests/test_indices_escala.py` vigila que esas consultas sigan usando su índice y que db.py y las
migraciones declaren lo mismo. También se agregó `experimentos.snapshots_de(ids, desde)` (dos
consultas para muchas piezas) para el panel del admin.

## 3. Conexiones (pool) y gunicorn

- **Pool**: SQLAlchemy ya usaba un `QueuePool` de 5 + 10 conexiones; ahora es explícito y se
  configura (`db.opciones_pool`: `CREATV_DB_POOL` 10, `CREATV_DB_POOL_EXTRA` 10,
  `CREATV_DB_POOL_ESPERA` 15 s). Cada hilo de gunicorn toma una conexión prestada y la devuelve
  al cerrar la transacción. Con otra base (si algún día se migra a Postgres) agrega `pre_ping` y
  `recycle`. `PRAGMA temp_store=MEMORY` para los ordenamientos sin índice. **No** se tocó
  `synchronous` (FULL): sin una medición que lo pida no se cambia la durabilidad de lo pagado.
- **gunicorn**: su configuración ahora vive en el repo (`deploy/gunicorn.conf.py`,
  `deploy/iaplusyou.service`). **Un solo proceso, a propósito**: `trabajos.iniciar` (pipeline
  Higgsfield, análisis de marca, chat de Flow Plus) guarda el progreso en la memoria del proceso;
  con dos, la barra que sondea caería en el otro y vería «desconocido». En el VPS de 1 CPU, además,
  más procesos no dan más velocidad. 16 hilos (antes 8): un sondeo dura ~2 ms y una página
  ~200 ms; con más hilos los sondeos no esperan detrás de las páginas. Nunca `max_requests`
  (mataría los hilos de fondo a mitad de una generación pagada).

## 4. Capa de caché

En memoria del proceso y con reglas de invalidación explícitas; nada que pueda mostrar datos de
otro proyecto ni datos viejos más de un par de segundos:

| Qué | Dónde | Cuánto vive | Por qué es seguro |
|---|---|---|---|
| Catálogo leído por las búsquedas | `catalogo_productos.lecturas_memorizadas()` | una petición GET que solo pinta | fuera de esas rutas no existe; devuelve copias; escribir la meta lo olvida |
| Filas comerciales por activo (precio, url) | `catalogo_productos.recordado(("por_activo", c), …)` en `final_edition._fila_producto` | la misma petición | igual; `_fila_producto` devuelve una copia |
| Trabajos vivos de la cola | `trabajos.con_vivos_precargados` (ya existía) | una petición | igual |
| `usuarios.json` en `obtener` | `usuarios._cargar_recordado` | mientras no cambie la firma del archivo, máx. 2 s | `guardar` reemplaza el archivo (otra firma); `verificar` (login) lee siempre |
| `Locale` y patrón de Babel | `idiomas._locale_babel`, `_patron_numero` | el proceso | son constantes |
| Catálogo de traducciones | `idiomas._traducciones` | una petición, mientras sea el mismo `babel_locale` | `force_locale` pone otro objeto → se vuelve a pedir |
| Tablero | `dashboard._contexto_tablero` (ya existía) | 60 s | clave con el último snapshot |

Descartado: cachear la página entera (depende de demasiadas fuentes y de la sesión) y un caché
genérico de los JSON con copia profunda (copiar cuesta más que `json.load`, medido). Redis no
hace falta con un proceso.

## 5. Estáticos y CDN

- La app ya mandaba `immutable` a los estáticos con `?v=`. `deploy/nginx-creatv.conf` (ejemplo
  versionado) los sirve **desde el disco** con las mismas cabeceras (un CSS no ocupa un hilo de
  gunicorn), comprime con gzip el HTML (0,7–3 MB por página → ~10× menos), CSS, JS y JSON, limita
  el POST de `/login` y trae el bloque para poner **Cloudflare** delante (DNS «proxied»; la IP real
  por `CF-Connecting-IP` solo desde los rangos de Cloudflare, si no los límites por IP se rompen).
- **Imágenes y videos** viven en R2: para que salgan del CDN, `R2_PUBLIC_BASE_URL` debe ser un
  dominio propio del bucket, no `pub-….r2.dev` (límite de tráfico, sin caché, «no para
  producción»). `/admin/salud` lo avisa. `r2_uploader.cache_control(key)` pone un año
  «immutable» SOLO a claves que nunca se reescriben (finales `__v<id>`, voces/locuciones/
  grabaciones/música con hash); un video de Crear regenerado reusa su clave y sigue sin caché.

## 6. Salud: errores, registros y monitores (`/admin/salud`)

### 6.1 Errores agrupados (`error_app`, migración 0027, `monitoreo.py`)

Una fila por huella = origen (`web` ruta de Flask · `worker` tarea · `hilo` trabajo de
`trabajos.iniciar` · `log` un `log.error`) + tipo + `archivo:línea función()` del marco más adentro
que es código de la app + ruta (endpoint, tipo de tarea, acción del job con los dígitos como `N`,
o la plantilla del mensaje del log). Guarda veces, primera y última vez, la traza de la última,
método, path sin query, proyecto y usuario. Todo texto pasa por `limpiar_texto` (tokens de URL,
`Bearer`, `sk-…`, `password=`, `api_key=`…). Estados: abierto → resuelto (si vuelve a pasar se
reabre solo) · silenciado (sigue contando, nunca avisa). Un error nuevo o reabierto manda un
correo a los admins con correo verificado (`notificaciones.avisar_admin("error_app")`, en otro
hilo, máx. 10 por hora, `CREATV_AVISOS_ERRORES=0` lo apaga). `registrar*` nunca lanza; en las
pruebas no guarda nada salvo `CREATV_MONITOREO_EN_PRUEBAS=1`. Tarea diaria `errores_limpiar`:
resueltos/silenciados de más de 90 días y lo que pase de 2 000 filas.

### 6.2 Métricas y sistema

`monitoreo.METRICAS` (memoria del proceso web, desde que arrancó): por ruta peticiones, 5xx,
p50/p95 aproximados por cubetas, máximo y **consultas por petición** (así un N+1 nuevo se ve en
producción: así se encontró el del panel); peticiones por minuto de la última hora; las 50
últimas de más de 1 s; cuántas en curso y el pico. `cola_salud()`: atrasadas (debían empezar hace
> 10 min = el worker no corre), en curso > 30 min, por tipo en 24 h (hechas, error, duración media
y máxima). `sistema()`: base y WAL, disco, memoria (del sistema y del proceso), carga, conexiones
prestadas del pool, último respaldo, tamaño de los registros. `avisos()` lo dice en palabras, lo
grave primero.

### 6.3 Registros (`/admin/salud/registros`, `registro_app.py`)

`data/logs/web.log` y `worker.log` (rotan a 5 MB, guardan 5): todo `logging` INFO+ y los `print`
de los módulos (copiados línea por línea; `[aviso]` = WARNING), sin tokens ni llaves. Se filtran
por nivel y texto y se descargan. La salida estándar sigue yendo a journald como siempre.
`CREATV_SIN_REGISTRO=1` lo apaga.

### 6.4 Disponibilidad

`/salud` (público, sin sesión, sin detalles): `{"ok": true}` 200 si la app y la base responden,
503 si no. Para un monitor externo gratuito (UptimeRobot, Better Stack) cada 1–5 min: es lo único
que avisa si el servidor entero se cae (nadie más queda para mandar el correo).

## 7. Prueba de carga: 100 usuarios a la vez

`rendimiento/locustfile.py` (Locust): cada persona entra con su cuenta, abre su proyecto, sondea
las barras que trae la página, pide «Ver más», abre el detalle de una pieza y la galería del
catálogo. Ritmo `realista` = una acción cada 3–8 s (casi siempre el sondeo que el navegador hace
solo) ≈ 18 acciones por segundo con 100 personas: es «100 personas trabajando a la vez», bastante
más que 100 conectadas. Se niega a apuntar a otra máquina salvo `CARGA_PERMITIR_REMOTO=1`. Mismos
datos sembrados para «antes» y «después»; guía en `rendimiento/README.md`.

**A. Como el VPS: gunicorn fijado a UN núcleo** (`taskset -c 0`, Locust en los otros tres para no
robarle CPU), 100 usuarios a 5 por segundo y 150 s medidos DESPUÉS de que todos entraron
(`--reset-stats`):

| | Antes (`main`) | Después |
|---|---|---|
| Peticiones atendidas | 269 (2,1 por s) | 1 887 (14,4 por s) — **7×** |
| Mediana de todas | 27 s | 9 ms |
| Sondeo de una barra (mediana / p95) | 43 s / 71 s | 6 ms / 6 s |
| Detalle de una pieza (mediana) | 46 s | 46 ms |
| «Ver más» de Crear (mediana) | 68 s (2 alcanzaron a salir) | 77 ms |
| Página del proyecto (mediana / p95) | 59 s / 79 s | 14 s / 25 s |
| Entrar (POST /login, mediana) | 26 s | 13 s |
| Errores | 0 | 0 |

Con 1 proceso × 16 hilos, 1 × 4 o 2 procesos × 8 el resultado fue el mismo (14,4–14,8 por s; la
página 11–14 s): en un núcleo el límite es la CPU, no los hilos ni el GIL.

**B. Ráfaga: los 100 entran en 10 s** (1 proceso sin fijar, versión intermedia de esta rama, 3
min): antes 234 peticiones, y abrir la pantalla de entrada tardaba 129 s de mediana y entrar 13 s
(todo hacía fila detrás de páginas de 1 s); después 723 peticiones, 2,7 s y 4,8 s.

**C. Con más CPU: 4 procesos** (máquina de 4 núcleos, sin fijar, ritmo realista 4 min): 3 426
peticiones (18 por s), página 200 ms de mediana y 420 ms p95, detalle 33 ms, sondeo 6 ms, «Ver más»
54 ms, 1 error en 3 426 (una conexión cortada por Locust sin nginx delante).

**Conclusión honesta.** Lo que cuesta ahora es casi solo pintar la página del proyecto (≈ 0,2 s de
CPU: 71 % plantillas, de eso un 30 % la pestaña Experimentos) y cada login (≈ 0,4 s de pbkdf2, a
propósito). Todo lo demás pasó de decenas de segundos a milisegundos. Con UN núcleo, 100 personas
abriendo páginas sin parar todavía lo llenan: las acciones livianas siguen rápidas, pero la página
del proyecto hace fila. Para 100 personas activas a la vez hace falta CPU: un VPS de 2–4 núcleos y,
para usarlos, `workers > 1` (§8: antes mover `trabajos.iniciar` a la cola). Y la pestaña
Experimentos bajo demanda bajaría la página otro ~30 % en cualquier máquina.

## 8. Fuera de alcance / siguiente paso

- **Más de un proceso de gunicorn** (más CPU): primero mover a la cola lo que aún corre en
  `trabajos.iniciar` (o guardar su progreso en la base), y los cachés por proceso dejan de ser
  exactos entre procesos (tablero 60 s, Meta). Recién ahí `workers > 1` o un VPS con más núcleos.
- **Postgres**: SQLite con WAL alcanza para un servidor; migrar solo si se separa la base de la
  máquina o hay varias máquinas. El pool ya está listo para eso; las consultas con `pliegue()` y
  `json_extract` no.
- La página del proyecto sigue trayendo todas las pestañas (0,8 MB sembrada, 3 MB happyflops):
  Experimentos por fragmentos sería el siguiente gran recorte (spec 2026-09-28 §7).
- Login: pbkdf2 cuesta ~0,4 s de CPU por intento a propósito (seguridad); 100 logins a la vez son
  ~40 s de CPU. No se toca; el tope de nginx a `/login` evita que eso se use para tumbar el sitio.
- `metrica_snapshot` sigue insertando cada 2 h aunque nada cambie (spec 2026-09-28).

## 9. HookAce (Capafy) y PostHog

- **Capafy** es un marketplace de «Skills» para agentes (Claude Code, Codex…). La mayoría corre en
  sus servidores («Run Online», el código no se ve) y se cobran por semana o mes.
- **HookAce** («First 6-Second Retention Predictor», ~US$ 9,99/semana) **predice** con IA la
  retención de los primeros 6 s de un video o guion, con ganchos alternativos y una tabla de
  cortes. No lee datos reales de ninguna plataforma: no dice si la gente de verdad está mirando.
- **El dato real ya está al alcance**: Meta Insights da por anuncio `video_play_curve_actions` (%
  que sigue mirando en cada segundo 0–14, luego tramos hasta 60 s+),
  `video_continuous_2_sec_watched_actions`, `video_6_sec_watched_actions`, `video_p25…p100` y
  `video_avg_time_watched_actions`; hoy `meta_ads/insights.py` solo pide ThruPlay. Pedir esos
  campos (cambio en el submódulo `meta_ads`), guardarlos en `metrica_snapshot.extra` y dibujar la
  curva de los primeros segundos por pieza en Experimentos daría la retención REAL de cada
  anuncio, comparable entre ganchos, gratis. Para orgánico: Instagram da `ig_reels_avg_watch_time`
  y `reels_skip_rate` (saltos en los primeros 3 s); YouTube Analytics la curva completa
  (`audienceWatchRatio`); TikTok solo por la API de Business. HookAce podría servir ANTES de pagar
  la pauta (predecir), no para medir.
- **PostHog** mide lo que pasa después del clic: con su snippet en la tienda (Shopify: el tema +
  un «custom pixel» para el checkout) captura las UTM (las piezas ya llevan
  `utm_content = experimento_pieza.id`) y arma embudos, grabaciones de sesión y conversión por
  anuncio u orgánico. Plan gratis: 1 M eventos y 5 000 grabaciones al mes, 100 000 excepciones.
  También tiene seguimiento de errores, pero para la app el panel propio ya cubre lo pedido sin
  mandar datos de los clientes a un tercero. Encaje sugerido: en la **tienda**, no en la app.
