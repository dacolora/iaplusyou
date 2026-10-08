# Experimentos: objetivo «Instalaciones de la app» (iOS + Android)

Fecha: 2026-10-07 · Pedido de Daniel (cliente `colorado_forja`, app Forja Habit) · Estado: spec para revisión

## Problema

Un experimento con un enlace de App Store o Google Play como destino lo rechaza Meta: «Solo puede incluirse la URL
de la app con el objetivo de instalaciones de la app». Hoy el objetivo se calcula solo (`experimentos.objetivo_sugerido`
→ `OUTCOME_SALES` o `OUTCOME_TRAFFIC`), `meta_ads/campaign.py:11` no admite `OUTCOME_APP_PROMOTION`, hay un solo
`destino_url` por experimento y `Targeting` no sabe segmentar por sistema operativo. Una app tiene dos tiendas:
iOS y Android no pueden compartir conjunto de anuncios.

## Alcance de la versión 1

Dentro:
- Objetivo nuevo «Instalaciones de la app» (`OUTCOME_APP_PROMOTION`), elegible a mano en Avanzado. Nunca se sugiere solo.
- Dos URLs opcionales (App Store, Google Play) en lugar del destino único cuando se elige ese objetivo.
- App ID de Meta guardado por proyecto.
- Un conjunto de anuncios por país **y** plataforma con URL, segmentado a iOS o Android.
- Optimización por **clics al enlace de la tienda** (`LINK_CLICKS`), porque la app de Forja no tiene SDK de Meta ni
  servicio de atribución (revisado en `flutter-wt-upsell/pubspec.yaml` el 2026-10-04). El decisor juzga por CPC y CTR.
- Comprobaciones antes de tocar Meta (App ID, URLs, app en modo desarrollo).

Fuera (segunda fase, cuando la app tenga SDK o atribución):
- Optimizar por instalaciones reales (`APP_INSTALLS`) y juzgar por costo por instalación.
- Eventos dentro de la app (registro, compra) y `OUTCOME_SALES` para apps.
- Campañas Advantage+ de apps (una sola campaña que reparte entre tiendas).

Verificado en la documentación de Meta (2026-10-07): para promoción de apps, `LINK_CLICKS` lleva `promoted_object` con
`application_id` y `object_store_url`. **Sin probar contra la cuenta real**: es el primer paso del plan (ver «Prueba real»).

## Diseño

### Datos (sin migración nueva)
- App ID de la app **anunciada** (Forja Habit): archivo propio `meta_app_anunciada.json` del proyecto, escrito por
  `meta_conexion.guardar_app_anunciada`. NO es `meta_app.json`: ese guarda la app de inicio de sesión de Creatv (app_id,
  app_secret, login_config_id) y son cosas distintas. Se pide en el bloque Avanzado del formulario, precargado con el guardado.
  Es un identificador público, no un secreto.
- Las URLs viajan en `experimento.extra["app"] = {"ios_url": …, "android_url": …}` (JSON que ya existe). `destino_url` queda
  con la primera URL presente solo para que el resto de la app (galería, tarjeta) siga mostrando algo; nunca se usa para el
  enlace del anuncio con este objetivo.
- Una fila `experimento_pieza` **por pieza × país × plataforma**, con `extra["plataforma"] = "ios" | "android"`.
  Todo lo que ya trabaja fila por fila (lanzar, refrescar, decisor, pausar, escalar) sigue igual. En `paises[]` el id del
  conjunto pasa a ser `meta_adsets: {"ios": id, "android": id}`; `meta_adset_id` se mantiene para los demás objetivos.
- Costo de esta decisión: las cuentas de «piezas» se multiplican por la cantidad de plataformas; la tarjeta etiqueta cada
  fila con su plataforma. Verificar en el plan que la restricción de unicidad de `experimento_pieza` incluya la plataforma.

### Meta (`meta_ads/`)
- `campaign.py`: agrega `OUTCOME_APP_PROMOTION` a los válidos.
- `adset.py`: `MAPEO_OBJETIVO["OUTCOME_APP_PROMOTION"] = {optimization_goal: LINK_CLICKS, billing_event: IMPRESSIONS}`;
  `promoted_object = {application_id, object_store_url}` obligatorio, validado antes de llamar (igual que SALES con el Pixel).
- `targeting.py`: método `sistema(os)` que fija `user_os` (`["iOS"]` o `["Android"]`) y `device_platforms: ["mobile"]`.
- `creative.py`: con este objetivo el anuncio **no lleva enlace web**. El `link` del creative es la URL de la tienda de su
  plataforma y el botón es `INSTALL_MOBILE_APP`; el `object_story_spec` de video e imagen sigue igual. No se agregan `utm_*`
  (la tienda no los usa y `url_destino` los metería en una URL de tienda); la atribución de ese anuncio es por `ad_id`, no por
  `utm_content`.

### Lanzador (`lanzador.py`)
- `_promoted_object_para` devuelve, para este objetivo, la plantilla `{application_id}`; la URL de tienda se completa por
  conjunto.
- Antes de crear campaña o conjuntos: falla con mensaje claro si no hay App ID, si no hay ninguna URL, si una URL no es de
  `apps.apple.com` / `itunes.apple.com` / `play.google.com`, o si el proyecto marca la app en modo desarrollo. Nada de esto
  cobra, pero un rechazo tardío de Meta deja una campaña huérfana (lección del Pixel apagado).
- El bucle de conjuntos recorre país × plataforma; reanuda por `meta_adsets[plataforma]` igual que hoy por `meta_adset_id`.
- `meta_errores.explicar` ya traduce el 1885183 (app en desarrollo); se agrega el texto de este error nuevo para que se
  vea en palabras y no como JSON.

### Formulario (`dashboard.exp_probar`, `_tab_experimentos.html`)
- En Avanzado, el selector de objetivo suma «Instalaciones de la app». Al elegirlo, el campo «URL de destino» se oculta y
  aparecen «URL de App Store (iOS)» y «URL de Google Play (Android)», ambos opcionales con al menos uno requerido.
- La cuadrícula del paso 3 NO cambia (pieza × país): las plataformas se expanden en el servidor. El presupuesto diario por
  país se reparte en partes iguales entre sus plataformas y cada parte debe alcanzar el mínimo de Meta.
- Todo texto nuevo pasa por el catálogo (`_()`), inglés y español.

### Decisor y métricas
- Sin cambios de lógica: el objetivo cae en la puerta de tráfico (CPC/CTR; ThruPlay se omite para imágenes). La puerta de
  ventas no aplica (sin atribución).
- `metrica_snapshot` no cambia. Cuando exista SDK se agrega la columna de instalaciones.

### Plata
- Mismo flujo de hoy: lanzar crea todo **en pausa**, activar es otro clic, `exp_lanzar` sigue con `max_intentos=1`. El
  precio visible es el presupuesto diario por país ya existente. Pasar a conjuntos por plataforma **no sube el gasto**
  porque el presupuesto por país se divide, no se duplica.

## Pruebas
- Unitarias: `targeting.sistema`, mapeo del adset (con y sin `promoted_object`), creative de tienda sin `utm_*`, validación de
  URLs de tienda, expansión pieza × país × plataforma en `crear_con_piezas`, reanudación sin duplicar por plataforma.
- `tests/test_lanzador.py`: un caso de dos plataformas y uno de una sola (la otra URL vacía crea la mitad de los conjuntos).
- Prueba de mutación (agente `revisor`): quitar el filtro de plataforma o el `application_id` y ver que las pruebas lo noten.
- Pantalla: captura del formulario con el objetivo nuevo, en escritorio y celular, antes de dar por bueno.

## Prueba real (último paso del plan; el token solo vive en el VPS)
Tras desplegar, lanzar un experimento mínimo de `colorado_forja` (todo en pausa, gasto cero) y confirmar que Meta acepta la campaña y
los conjuntos; o a mano, crear en pausa y borrar después una campaña `OUTCOME_APP_PROMOTION` con un conjunto
`LINK_CLICKS` + `promoted_object` y confirmar que Meta lo acepta, una vez por plataforma. No cobra: todo queda en pausa.
Si Meta rechaza `LINK_CLICKS` para apps, la versión 1 cambia y se vuelve a este spec antes de seguir. Derivar y rescatar quedan
desactivados para este objetivo (las piezas nuevas no tendrían plataforma): solo pausar y escalar.

## Parte de Daniel en Meta for Developers (no se puede hacer desde el código)
En la app de Meta usada para anunciar, Configuración → Básica, agregar las dos plataformas con sus datos reales:
- Android: nombre del paquete `com.danielcolorado.liferpg` (`android/app/build.gradle.kts`) y la clave hash si Meta la pide.
- iOS: ID del paquete `com.danielcolorado.apptemporal` (`ios/Runner.xcodeproj`) y el ID de la tienda (el número de la URL
  de App Store).
- Copiar el App ID a Configuración en Creatv. Dejar la app en modo **Live**: en modo desarrollo Meta responde 1885183.
Nota de riesgo ya anotada: Forja Habit figura como `not_verified`, con riesgo de restricción de cuenta.

## Repositorios
`meta_ads/` es un submódulo (`dacolora/CreaTvMetaAds`): los cambios de campaña, conjunto, targeting y creative se commitean
allí y después se sube el puntero. Publicar en ese repositorio externo se consulta antes.

## Riesgos y decisiones abiertas
1. Si `LINK_CLICKS` no se acepta para apps, la v1 depende del SDK y se re-plantea (se sabe en la prueba real).
2. Una fila por plataforma duplica las cifras por pieza en la galería; si estorba se agrupa solo en la vista.
3. Anuncios de imagen y video comparten creative de tienda; el video de reels exige relaciones de aspecto de Meta, igual que hoy.
4. Limitación conocida de la v1 (revisión final, 2026-10-08): el ranking top-tercio del decisor ordena juntas las filas
   de iOS y Android de un país, aunque vivan en conjuntos distintos y compitan por públicos distintos. Una tienda con
   CTR más bajo por naturaleza puede caer al tercio de abajo sin perder contra su propia tienda. Si estorba, el ranking
   se hace por país y plataforma.
