---
name: alertas
description: "Alertas del proyecto: la pestaña que junta lo que necesita atención (puesta a punto, faltantes, decisiones y fallos) con trece fuentes calculadas al vuelo, descartes por huella, alertas solo para el admin, caché de 60 s y la burbuja del sidebar; y la lista de tarjetas de Puesta a punto (llaves.py). Cargar antes de agregar una fuente de alertas, tocar alertas.py, llaves.py, _tab_alertas.html o la burbuja del sidebar."
---

# Alertas: lo que necesita la atención de la persona

> Parte de la guía del repositorio. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.
>
> Spec: `docs/superpowers/specs/2026-09-20-alertas-design.md` (la §12, «Rescate del 2026-10-02», manda donde difiere de las demás). La rama vieja `worktree-alertas` nunca se fusionó; se rehízo sobre `main` el 2026-10-02 (PND-102) en seis tareas (`alertas (1/6)` a `(6/6)` en el historial).

## Qué es y la regla de oro

La pestaña Alertas (`_tab_alertas.html`), la burbuja del sidebar (`_sidebar.html`: roja si alguna bloquea, ámbar si no) y la línea del centro de resultados de Experimentos («N alertas necesitan tu atención → Ver Alertas», `.cr-alertas-linea` en `_exp_resultados.html`; el Tablero dejó de ser pestaña el 2026-10-03) muestran lo mismo: lo que `alertas.py` calcula para el proyecto.

**Se calcula al vuelo; solo se guardan los descartes** (2026-09-20). Cada alerta sale del estado real (llaves del `.env`, tablas, archivos del proyecto), así que nunca hay una alerta vieja que ya no corresponda: si algo se resuelve, desaparece sola. Lo único que se escribe es la tabla `alerta_descartada` (migración 0029, `(cliente, clave) → huella`), y su ÚNICO escritor es `alertas.py` (`descartar`, `restaurar`, la poda).

Una alerta es un dict armado por `alertas._alerta` (nunca a mano):

| Llave | Qué es |
|---|---|
| `clave` | Estable: `<fuente>:<tipo>[:<entidad>]`. Tiene que pasar `CLAVE_VALIDA` (`^[a-z_]+:[A-Za-z0-9_:.\-]{1,180}$`): si metes un nombre de persona, límpialo (ver `cuenta:correo:`). |
| `huella` | sha256 de la «situación» (`alertas.huella(*partes)`). Un descarte vale mientras la alerta exista con esa huella. |
| `nivel` | `bloquea` · `atencion` · `info` (`NIVELES`, en ese orden). |
| `grupo` | `puesta_a_punto` · `faltantes` · `decision` · `fallos` (`GRUPOS`, en ese orden). |
| `titulo`, `detalle` | Texto ya traducido al idioma de quien mira (`gettext`/`ngettext` al calcular). |
| `tab`, `ancla`, `url` | A dónde lleva «Ir a …»: una pestaña (con ancla opcional, `data-ir-tab`/`data-ancla`) o una página propia (`url`, armada con `_url_proyecto`, que no usa Flask). |
| `entidad` | El id de lo que falla (experimento, sesión, estudio…), o `None`. |
| `solo_admin` | `True`: la ve y la toca solo un admin (ver abajo). |

`calcular(cliente)` corre cada fuente de `FUENTES` en su propio `try/except` y ordena por grupo, luego nivel, y dentro de eso en el orden de las fuentes. Si una fuente revienta sale `revision:<fuente>` (`info`, `solo_admin`) con SOLO el nombre de la clase de la excepción, nunca el mensaje (podría arrastrar un token), y las demás se calculan igual. Los nombres de grupo, nivel y pestaña son constantes `idiomas.N_` (`NOMBRES_GRUPO`, `NOMBRES_NIVEL`, `NOMBRES_TAB`) que la plantilla traduce con `|traducir`.

## Las trece fuentes (en el orden de `FUENTES`)

| # | Fuente | Claves | Grupo · nivel | Huella |
|---|---|---|---|---|
| 1 | `llaves` | `llave:<id de tarjeta>` | puesta_a_punto · `bloquea` (`info` si la tarjeta es `opcional`) · **solo_admin** | los nombres de las variables que faltan |
| 2 | `cuentas` | `cuenta:correo:<usuario>` | puesta_a_punto · `bloquea` (cada cliente ve la suya; el admin todas, PND-123) | «sin correo», o «sin verificar» + el correo |
| 3 | `worker` | `worker:parado` | puesta_a_punto · `bloquea` · **solo_admin** | la última señal de vida |
| 4 | `saldo` | `saldo:wavespeed` (neutra, para todos) y `saldo:wavespeed_recarga` (con la URL de recarga); después `saldo:fal` y `saldo:fal_recarga` (2026-10-09) | puesta_a_punto · `bloquea` (las de fal, `atencion`: solo se pausan sus modelos) · las `_recarga` **solo_admin** | el `desde` del aviso de cada proveedor (las dos de un proveedor, igual) |
| 5 | `tablero` | `tablero:<tipo>:<experimento o ->` | según el tipo: meta, tienda y píxel → puesta_a_punto; productos sin experimento → faltantes; propuestas, tope, ganador sin publicar → decision; error, rechazados, sin métricas → fallos | tipo + experimento + los números del texto |
| 6 | `proyecto` | `proyecto:{guia_marca,producto,logo,personaje,tienda,correo_avisos,canal_organico}` | faltantes · `atencion` o `info` | vacía a propósito (un faltante descartado sigue descartado hasta que se resuelva) |
| 7 | `crear` | `crear:prompt_listo` (una con el conteo), `crear:error:<cf_id>` | decision / fallos · `atencion` | ids ordenados / el error |
| 8 | `organico` | `organico:error:<pub_id>` | fallos · `atencion` | el error |
| 9 | `sprints` | `sprint:{ideas,revision,fallos,referencias}:<sprint_id>` | decision / fallos | los ids (o el conteo) |
| 10 | `nicho` | `nicho:avatares`, `nicho:error:<estudio_id>` | decision / fallos · `atencion` | el conteo / el error guardado |
| 11 | `cobros` | `cobros:sin_saldo`, `cobros:saldo_bajo`, `cobros:no_cobrado:<mov_id>`, `cobros:recarga_pendiente:<id>` | puesta_a_punto `bloquea` / puesta_a_punto `atencion` / fallos `info` / decision `info`; todas del cliente, a Configuración › Saldo y recargas (`config-ap-saldo`) | `sin_saldo` constante; `saldo_bajo` el saldo en dólares redondeados; las otras, tipo y monto o el id |
| 12 | `meta` | `meta:metodo_pago` | puesta_a_punto · `info`, solo con la app propia de Meta conectada (no en modo agencia) | vacía |
| 13 | `meta_rendimiento` | `meta_rendimiento:<tipo>:<act_…>` | decision · `atencion`, a la pestaña Meta (sin ancla: el «Diagnóstico» llega por fetch) | la de la recomendación (`recomendaciones.huella_recomendacion`), guardada por la copia |

Detalles que ya costaron una duda:

- **Llaves**: una alerta por tarjeta de `llaves.estado()` que no esté `configurada`. Meta no tiene tarjeta aquí (vive en Experimentos; la cubre `tablero:meta_*`, que además sabe si está rota); la fuente igual salta un id `meta` por si vuelve. Solo nombres de variables: `llaves.estado` nunca entrega un valor. `llaves.py` es la lista de tarjetas de Configuración › Puesta a punto (antes `SERVICIOS_LLAVES` en `dashboard.py`, que sigue ahí como alias); una tarjeta `opcional` da una alerta `info` y Anthropic, WaveSpeed, fal, R2 y Gemini dan `bloquea` (las demás son opcionales; Higgsfield desde el 2026-10-02, porque solo lo usa el flujo viejo «Nueva idea»).
- **Worker**: parado si pasaron más de `MINUTOS_WORKER` (30) sin señal, o nunca. Señal = lo más nuevo entre las marcas `kv` `ultimo_<tipo>` que el bucle del worker escribe al encolar sus periódicas y `MAX(tarea.iniciada_en)` (el worker es de un solo hilo: una render larga lo deja ocupado sin pasar por el bucle). Dos consultas fijas (una por tabla), sin importar cuántas marcas haya.
- **Saldo**: dos alertas con la misma huella a propósito. La del cliente no dice la cuenta, el proveedor ni el enlace de recarga (la cuenta es de Creatv); la del admin sí. El admin ve las dos (aceptado). Con fal (Seedance 2.5 con varias referencias, PND-213) es lo mismo pero `atencion`: la neutra nombra los modelos en pausa (`saldo.nombres_modelos("fal")`) y pide elegir otro.
- **Tablero**: `tablero.alertas()` no se reescribe; solo se le pone clave, nivel (`alta→bloquea`, `media→atencion`, `baja→info`) y grupo. La única lógica de experimentos sigue en `tablero.py`. El texto se acota con `_limpio(texto, 400)`: la guía de Meta en modo Desarrollo ronda los 330 caracteres y su llamado a la acción va al final. Los números de la huella salen del texto ENTERO y limpio (`_limpio(texto, None)`), no del recortado: un texto que se corta en un idioma y en el otro no cambia la huella.
- **Crear**: los prompts listos son UNA alerta con el conteo y solo cuentan los de hace más de `MINUTOS_PROMPT_LISTO` (60): los recién armados no molestan mientras la persona trabaja. Fallos de los últimos `DIAS_FALLOS` (30) días; una sesión con dos piezas cuenta una vez.
- **Nicho**: una investigación `detenida` alerta si tiene motivo y no es `cancelada` (clic de la persona, 2026-10-02); una `interrumpida`, siempre; un estudio, una alerta (la investigación manda sobre el error de generación).
- **Cobros** (2026-10-08, spec `2026-10-08-cobros-saldo-prepagado` §8): solo si `libro.estado(cliente)["cobrar"]`; un proyecto que no cobra sale tras leer la cuenta y no consulta nada más. `sin_saldo` mira el DISPONIBLE (saldo menos lo reservado) ≤ 0; `saldo_bajo` mira el saldo (0 < saldo < umbral) y no sale si ya hay `sin_saldo`; su huella lleva el saldo en dólares redondeados, así que un descarte no esconde un saldo que siguió bajando. `no_cobrado`: un `reverso` o `no_cobrado` de los últimos `DIAS_NO_COBRADO` (7) días (en el `no_cobrado` el monto es `extra.precio`); `recarga_pendiente`: Bold pendiente de hace más de `MINUTOS_RECARGA_PENDIENTE` (15) min. Dos consultas fijas (movimientos y recargas, tope `TOPE_COBROS` = 20 cada una). El concepto sale de `cobros.vista.nombre_concepto`. Ninguna es `solo_admin`. El apartado `config-ap-saldo` solo existe en la página de un cliente que cobra (el admin siempre lo ve).
- **Orgánico**: reintentar es una acción de la persona sobre la pieza; aquí solo se avisa.
- **Meta rendimiento** (E2, 2026-10-10, spec `2026-10-10-meta-rendimiento-e2-design.md` §10; skill `meta-rendimiento`): la fuente
  NO calcula reglas (cargar 30 días de anuncios en cada página sería caro) y hace UNA consulta (`cuentas.listar`, una
  fila por cuenta del proyecto). Al terminar bien cada copia, `tareas.meta_rendimiento._guardar_alertas` guarda en
  `meta_cuenta.extra.alertas` las recomendaciones de nivel «alta» de ESA cuenta como `[{tipo, huella}]` (calculadas con
  `panel.recomendaciones_de_cuenta`, guardadas con `cuentas.actualizar_extra`; un fallo se anota con su tipo y no tumba
  la copia). Lo que puede ser «alta» es `meta_rendimiento.recomendaciones.TIPOS_ALTA` (`cuenta_estado`,
  `cuenta_roas_bajo`, `aprendizaje_limitado`, `perdedores_gastando`, `anuncios_con_problemas`) y cada tipo tiene su
  par `N_` (título y detalle) en `alertas.TEXTOS_META_RENDIMIENTO`: la fuente ignora un tipo sin texto, y una prueba
  exige que las tres listas coincidan. **Un tipo nuevo que pueda ser «alta» se agrega a `TIPOS_ALTA` y a
  `TEXTOS_META_RENDIMIENTO` (más su traducción), o su alerta se pierde en silencio.** Cada una sale como alerta de
  nivel `atencion`, grupo `decision`, clave `meta_rendimiento:<tipo>:<act_…>`, a la pestaña `meta` (sin ancla: el
  «Diagnóstico» llega por fetch), con el nombre de la cuenta (dato de Meta) pasado por `_limpio`. **La huella es la de la
  recomendación** (ruling E2-R4: `sha256` hex completo, `alertas.HUELLA_VALIDA`): en los tipos que juntan TODO lo de
  una cuenta es tipo + cuenta + nivel, porque su lista de objetos cambia en cada copia y una alerta descartada no puede
  volver cada 3 horas (sí vuelve si cambia el nivel); en los demás, tipo + cuenta + los ids de sus objetos. El título NO
  se guarda (el spec decía `{tipo, titulo, huella}`): guardado quedaría en el idioma del proyecto y la regla de esta
  skill es traducir al calcular. Un elemento roto (tipo desconocido, huella que no es sha256, algo que no es un dict)
  se ignora. Cada cliente puede descartarla (es de su cuenta). Una copia que falla deja lo guardado, y las alertas
  guardadas no caducan (PND-249); quitar la cuenta borra su fila y con ella sus alertas.

## Quién ve qué: `solo_admin` (2026-10-02)

Las llaves del `.env`, el worker, el enlace de recarga del saldo y las fuentes caídas son de Creatv: un cliente no ve instrucciones del servidor (el mismo criterio de `dashboard._llaves_visibles` para las tarjetas de Puesta a punto). `visibles(..., rol=, usuario=)` las quita para un cliente y el resumen (la burbuja) se cuenta sobre lo que esa persona ve; el cliente nunca recibe `llave:*`, `worker:parado`, `saldo:wavespeed_recarga`, `saldo:fal_recarga` ni `revision:*`.

**El servidor lo hace cumplir, no la plantilla.** Los descartes son del proyecto: si un cliente pudiera descartar `saldo:wavespeed_recarga` o una `llave:*`, se las escondería al admin. Por eso `POST /cliente/<c>/alertas/descartar` y `/restaurar` responden 403 a un no-admin con una clave `solo_admin` (`dashboard._clave_alerta_del_form` + `alertas.es_solo_admin`, que mira primero la lista ya calculada y, si la alerta ya no está, el prefijo `PREFIJOS_SOLO_ADMIN = ("llave:", "worker:", "revision:", "saldo:wavespeed_recarga", "saldo:fal_recarga")`). Motivo: la revisión de la tarea 5 (2026-10-02) encontró que ocultar el botón no bastaba. Una alerta `solo_admin` nueva tiene que empezar por uno de esos prefijos (o se agrega el prefijo): `tests/test_rutas_alertas.py::test_toda_alerta_solo_admin_de_las_fuentes_lleva_prefijo_de_admin` lo comprueba.

Las rutas validan lo que llega: la clave con `CLAVE_VALIDA` y largo ≤ 200, la huella con `HUELLA_VALIDA`, ambas con `fullmatch` (con `$` un salto de línea al final pasaría), y devuelven 400 si no calzan. **`descartar` solo escribe si la clave está en el cálculo actual** (`_alertas_calculadas`): con una clave válida pero inventada responde un redirect con «Esa alerta ya no está.» y no guarda nada (auditoría de seguridad, 2026-10-02, CWE-770: sin esto cualquiera con sesión llenaba `alerta_descartada` de filas que nunca se podan). `restaurar` no tiene ese chequeo porque solo borra. Pasan por `_solo_mismo_origen` y `_guard_por_cliente` como toda ruta POST con proyecto; solo leen el cálculo en caché (con la caché fría lo hacen una vez) y no gastan ni encolan.

## La caché de 60 s (`dashboard.py`)

El context processor `_alertas_sidebar` pinta `alertas_ctx` en TODA página con `<cliente>` en la URL y sesión (también Sprints y Nicho, que no pasan por `ver_cliente`); no corre para peticiones JSON/fetch ni para `landing_cliente`. Si el cálculo revienta, la página sale sin alertas y el log dice solo la clase del error.

- `_alertas_calculadas(cliente)` guarda `alertas.calcular` por `(cliente, idiomas.activo())` durante `ALERTAS_TTL_S = 60`: los títulos salen traducidos al calcular, así que cada idioma tiene su entrada. Guarda el cálculo COMPLETO y el rol y usuario de sesión se filtran al leer; los descartes se leen siempre en vivo (una consulta por página).
- Se renueva antes del TTL en tres casos, porque 60 s con una alerta ya resuelta se sentía roto (revisión de la tarea 5, 2026-10-02): (1) cambia `_clave_tablero` (un snapshot, una propuesta, una publicación: lo que hace el worker sin pasar por una ruta; la misma clave del Tablero, leída una vez por petición con `_clave_tablero_de_la_peticion`); (2) después de toda escritura que salió bien (`_alertas_tras_escribir`, un `after_request` para POST/PUT/PATCH/DELETE con status < 400 y `<cliente>` en la ruta, y solo si la sesión puede acceder a ese proyecto: el 302 de `_guard_por_cliente` también es < 400 y sin ese chequeo cualquiera mantendría fría la caché ajena); (3) al descartar o restaurar, ANTES de redirigir: la página siguiente se calcula con lo real y no con una lista de hace unos segundos.
- `invalidar_alertas(cliente)` olvida todos los idiomas; `invalidar_tablero` también la llama.
- Es por proceso: gunicorn corre UN proceso con hilos (`deploy/gunicorn.conf.py`), pero el worker es otro proceso y no vacía esta caché; lo que cambia el worker FUERA de la clave del Tablero (un error de Crear, una investigación de Nicho) puede tardar hasta 60 s en aparecer o desaparecer. PND-121 sigue como pregunta para Daniel: invalidación compartida sin subir el costo por página (2026-10-07).

## Descartes por huella

- Descartar guarda `(cliente, clave) → huella` con un upsert atómico; descartar de nuevo la misma clave reemplaza la fila. Un descarte vale mientras la alerta exista con esa misma huella: si la situación cambia, la alerta vuelve sola.
- Si la alerta ya no existe, `visibles` poda su descarte (mirando TODAS las alertas, no solo las que ve esta persona: una pasada de un cliente no puede borrar el descarte de una `solo_admin`). **La poda se salta si en esa pasada hay una alerta `revision:*`**: sus alertas pueden faltar por el fallo y se perderían descartes válidos. El borrado exige también la huella que se leyó, para no llevarse un descarte que otro proceso reescribió entre la lectura y el borrado.
- **La huella nunca sale de un texto traducido** (regla del 2026-10-02). Un descarte es del proyecto y lo comparten un admin en español y un cliente en inglés: con el texto, el «Descartar» de uno no valdría para el otro y cada uno pisaría el del otro. La huella del Tablero es tipo + experimento + los números del texto en el orden en que aparecen («1.250» y «1,250» dan los mismos números); `sin_metricas` lleva huella vacía porque su texto dice «lleva N h» y cambiaría cada hora. Nicho guarda y hashea el texto original del motivo, y lo traduce solo para mostrarlo. Quien agregue una fuente: huella de ids, conteos, estados o texto guardado, jamás de un `gettext`.

## Reglas de código

- **`alertas.py` no importa `dashboard`** (círculo): lo importan `dashboard.py` y los tests, y no tiene rutas ni app de Flask (solo `gettext`, que fuera de una petición devuelve el español). Las dependencias pesadas (`tablero`, `organico`, `saldo`…) se importan DENTRO de la fuente. `tests/test_alertas_fuentes.py::test_alertas_no_importa_el_dashboard`.
- **Consultas acotadas por fuente** (motivo: la pestaña se calcula en cada carga de página): nada de un bucle con una consulta por tarjeta, sesión, sprint o estudio, ni `creative_flow.cargar`. La fuente de Crear es UNA consulta con el estado calculado en SQL; Sprints son dos; Nicho son cuatro fijas (una de estudios con error y tres del resumen de avatares). Crear, orgánico, Sprints y Nicho traen su prueba de «corre las mismas consultas con pocas o con muchas filas» y `test_en_frio_las_alertas_no_crecen_con_las_piezas` (más `tests/test_perf_pagina_proyecto.py`) vigila la página entera.
- **Nada de aquí gasta, encola, publica ni llama a un proveedor.** Una alerta avisa y lleva a donde la persona decide (regla del precio primero).
- **Ningún valor de llave sale de aquí.** El texto de un error ajeno pasa por `_limpio`, que es `monitoreo.limpiar_texto(texto, n)`: `cola.sin_token` (tokens en URLs) más `Bearer …`, `sk-…`, `secret=`, `password=` y las cabeceras `Authorization`, y el recorte (200 caracteres; 400 el del Tablero; `n=None` no recorta). Un `Bearer` de menos de 8 caracteres no cuenta como token y no se redacta (límite de `monitoreo._SECRETOS`).
- **Todo texto por el catálogo** (`gettext`/`ngettext` al calcular, `idiomas.N_` en constantes). Después `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar`; sin `fuzzy`. Skill `idioma`.
- Anclas: `ancla` tiene que existir en la página (`tests/test_rutas_alertas.py::test_cada_ancla_de_alertas_existe_en_la_pagina` las cuenta). Hoy: `llave-<id>`, `config-cuenta`, `config-puesta-a-punto`, `config-marca`, `config-logos`, `config-tienda`, `config-correo`, `config-canales-organicos` y `cf-<id>` (Crear).

## Cómo agregar una fuente

1. En `alertas.py` escribe `_fuente_<nombre>(cliente, ahora_iso) -> lista de _alerta(...)`, con sus imports adentro. Una sola consulta acotada (o las mínimas, fijas). Clave que pase `CLAVE_VALIDA`; huella de datos que no dependan del idioma; nivel y grupo de las constantes; textos con `gettext`/`ngettext`; `tab` de `NOMBRES_TAB` (si es una pestaña nueva, agrégala ahí con `idiomas.N_`) y `ancla` existente, o `url` con `_url_proyecto` para una página propia.
2. Regístrala al final del archivo en `FUENTES.extend([...])` en el lugar que le toque: el orden decide cómo se listan las de un mismo grupo y nivel.
3. Si es `solo_admin`, su clave tiene que empezar por un prefijo de `PREFIJOS_SOLO_ADMIN`.
4. Pruebas en `tests/test_alertas_fuentes.py`: la alerta con su huella (y que no cambia con el idioma), que no deja pasar tokens, el caso resuelto, el otro proyecto que no se mezcla (con filas VIVAS en el otro proyecto: con filas cerradas o descartadas la prueba pasa aunque falte el filtro de `cliente`; los helpers de `tests/test_alertas_fuentes.py` aceptan `cliente=`), la prueba de consultas con 1 y con 6, y su salida en inglés. Actualiza `test_las_diez_fuentes_se_registran_en_su_orden`.
5. Catálogo (`actualizar`, traducir, `compilar`), y agrega la fila a la tabla de este archivo.
6. Corre `tests/test_alertas*.py`, `tests/test_rutas_alertas.py` y `tests/test_perf_pagina_proyecto.py`.

## Pendientes conocidos (`docs/pendientes.md`)

- PND-121: lo que cambia el worker fuera de la clave del Tablero puede tardar hasta 60 s en aparecer o desaparecer.
- PND-122/123/124 (decisiones delegadas, 2026-10-08): Crear excluye los errores vinculados a sprints vivos
  (archivado o completado vuelve a alertar en Crear). Cada cliente ve y toca solo su `cuenta:correo`, por `entidad`
  y usuario de sesión, después de la caché y antes de contar o mostrar descartadas; el admin ve todas. La poda
  sigue mirando el cálculo completo. Los seis tipos de plata (enmienda S1, 2026-10-08) permanecen visibles pero `puede_descartar` es
  falso para clientes: `descarte_solo_admin` protege descartar/restaurar con 403 incluso si la clave ya desapareció.
  Pruebas `test_rutas_alertas.py` y `test_alertas_fuentes.py`, con mutaciones locales; pantalla pendiente de Claude.


**Pedidos vencidos (2026-10-02, PND-015):** la fuente Tablero agrega `tablero:pedidos_sin_atribuir:-`, grupo `fallos`, nivel `atencion`, huella del conteo y del plazo fijo. Cuenta pedidos del proyecto con UTM que siguen sin atribución después de 30 días; informa, sin resolverlos ni tocar ventas.

PND-118/119 (2026-10-03): Tablero entrega tienda_id y la fuente lo usa como entidad, clave y parte de la huella. Un descarte no oculta otra tienda. Orgánico excluye un error si existe una publicación posterior (id mayor) de la misma pieza, plataforma y proyecto en en_cola/publicando/publicada; sigue siendo una consulta, y un éxito anterior no tapa un error nuevo.

**Gemini y detalle de Crear (2026-10-07, PND-075/120):** `llaves.py` trae `GEMINI_API_KEY`; la tarjeta es obligatoria
para ese proveedor porque también se usa en Crear › Cambiar producto con Nano Banana (`tareas/swap.py`), además del
flujo viejo. Textos por `N_` y catálogo; `estado()` entrega solo presencia, nunca el valor. Alertas de error y prompt
listo enlazan a `#creativeflowplus?cf=<id>`; el modal carga el detalle aunque no haya tarjeta inicial. El catálogo y
las pruebas de fuentes, llaves, ruta por proyecto y JS cubren el cambio; la vista real queda para Claude.

S1/S4 (2026-10-08, enmienda de revisión lote 6B): ganador_sin_publicar y anuncios_rechazados también protegen descartar/restaurar con 403 para cliente. Si sanear/truncar el usuario cambia su nombre exacto, cuenta:correo agrega - y ocho hex del sha256 del nombre exacto; nombres ya limpios mantienen la clave. Esto evita que dos cuentas viejas compartan descartes. R7 prueba que un sprint vivo ajeno con el mismo cf_id no esconde el error de Crear.

PND-176 (2026-10-09, decisión delegada): se conserva la ausencia de aviso para una idea descartada de un sprint vivo, aunque su sesión esté en error: la persona ya dijo que no la quiere. Sin cambio de código.
