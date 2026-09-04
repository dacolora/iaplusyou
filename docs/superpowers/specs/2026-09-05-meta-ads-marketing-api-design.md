# Diseño: módulo de Meta Ads (Marketing API)

Fecha: 5 sep 2026
Investigación base: `docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md`
(605 líneas, 29 llamadas reales contra developers.facebook.com — cada campo de
este spec viene de ahí, no de memoria).

## Contexto y motivo

`iaplusyou` hoy publica contenido **orgánico** en Facebook/Instagram vía
`uploaders/meta_uploader.py` (Graph API estándar). Este documento diseña un
módulo nuevo y separado: publicar el mismo tipo de contenido (fotos/videos ya
generados por "cambiar calzado", "Nueva idea" o CreativeFlowPlus) como
**anuncio pagado** vía la Marketing API, ver sus resultados (impresiones,
clics, gasto), y — en fases futuras no cubiertas aquí — subirle presupuesto a
lo que funciona automáticamente.

El plan completo del usuario es un ciclo cerrado: crear contenido → publicar
como anuncio → medir resultados → retroalimentar (más de lo que funciona,
presupuesto arriba) → opcionalmente buscar contenido similar en plataformas
como tryatria.com para clonarlo y repetir el ciclo. Este spec cubre **solo**
la pieza de publicar + medir. Buscar/clonar contenido externo y la
retroalimentación automática son módulos aparte, fuera de este documento.

## Metas

- Publicar una foto/video ya aprobado en `iaplusyou` como campaña de Meta Ads
  real, con control medio (yo elijo objetivo, presupuesto, días, audiencia
  básica — no cada campo posible desde el primer día).
- Ver resultados básicos (impresiones, clics, gasto, CTR) de lo publicado.
- Que cada cliente futuro de la herramienta pueda configurar su propia cuenta
  de Ads de forma repetible, sin tocar las credenciales de otros clientes.
- Cubrir, en el diseño (aunque no todo se implemente ya), la superficie
  completa de la Marketing API — Campaign, AdSet/Targeting, Ad, AdCreative en
  todos sus formatos, e Insights — para que sumar cada pieza más adelante sea
  extender, no rediseñar.

## No-metas (explícitamente fuera de este spec)

- Motor de reglas / retroalimentación automática (pausar, subir presupuesto,
  generar más contenido similar según resultados) — fase futura separada.
- Integración con tryatria.com u otras plataformas de descubrimiento de
  contenido — fase futura separada.
- UI de creación de audiencias personalizadas/lookalike desde cero (se
  referencian por ID, no se construyen aquí).

---

## Arquitectura general

Un módulo por objeto de la API, siguiendo el patrón ya usado en el proyecto
(`higgsfield_client.py`, `providers/kling_o1_client.py`, etc. — un archivo
por proveedor/objeto, funciones puras que hablan HTTP directo, sin ORM ni
framework intermedio):

```
meta_ads/
  __init__.py
  auth.py          # token, ad_account_id, headers comunes
  targeting.py      # builder del Targeting spec (Fase 1 básico, Fase 2 completo)
  campaign.py        # crear/leer Campaign
  adset.py            # crear/leer AdSet
  ad.py                 # crear/leer Ad
  creative.py            # crear AdCreative (Fase 1: imagen/video; Fase 3: carrusel/colección/dynamic)
  insights.py              # leer resultados (Fase 1: básico; Fase 4: breakdowns/async)
ads.py                # estado — cola "listo para publicar" + resultados, un JSON por cliente
auth/auth_meta_ads.py   # wizard de cuenta, un cliente a la vez
```

### Por qué un `targeting.py` builder y no un diccionario armado a mano

El Targeting spec de Meta tiene ~40 campos posibles entre demografía, geo,
intereses/comportamientos, audiencias, idioma, dispositivo y placements (ver
investigación, sección 2.2). Armar ese diccionario a mano en cada llamada es
frágil y repetitivo. Un builder encadenable mantiene el código de publicación
legible:

```python
targeting = (
    Targeting()
    .edad(18, 45)
    .paises(["CO"])
    .intereses([{"id": "...", "name": "..."}])
    .placements(publisher_platforms=["facebook", "instagram"])
    .to_dict()
)
```

Fase 1 solo expone edad/género/país-ciudad/placements por defecto. Fase 2
añade el resto de métodos al mismo builder — no se reescribe nada, se suma.

### Contrato "Enviar a Publicidad" (ya acordado)

Cualquier módulo (FlowClone, Nueva idea, CreativeFlowPlus) puede llamar:

```python
ads.crear(cliente, fuente, contenido_url, contenido_tipo, nombre)
```

`ads.py` no conoce el formato interno de `swaps.json`, `estado_videos.json`
ni el JSON de CreativeFlowPlus — solo recibe estos 5 valores. Esto es
deliberado: CreativeFlowPlus sigue evolucionando activamente en otra sesión
de trabajo sobre este mismo repo, y este contrato mínimo evita que un cambio
en su esquema rompa el módulo de Ads.

---

## Fase 0 — Configuración de cuenta (wizard)

`auth/auth_meta_ads.py --cliente <nombre>` (mismo patrón que
`run_batch.py`/`revisar.py`: sin `--cliente`, usa el modo de un solo cliente
en la raíz del proyecto).

Pasos que guía el script:
1. Verifica que existe Business Manager (si no, da el link y los pasos
   exactos para crearlo).
2. Guía la creación del Ad Account dentro del Business Manager + método de
   pago.
3. Guía agregar el permiso `ads_management` (y `ads_read` si se quiere
   separar el alcance de solo-lectura) a la app de Facebook Developers
   existente — reutiliza el token ya usado por `meta_uploader.py`, solo pide
   el scope nuevo. Explica que esto requiere **App Review + Business
   Verification** (investigación, sección 6) y puede tardar días.
4. Valida el acceso con una llamada real de prueba (`GET
   /act_{id}/campaigns`, aunque esté vacío) antes de darse por terminado.
5. Guarda `META_AD_ACCOUNT_ID` (y cualquier token refrescado) en
   `clientes/<cliente>/.env` — **no** en el `.env` raíz, para que cada
   cliente futuro corra el mismo script con su propio nombre y quede aislado
   de los demás, igual que ya pasa hoy con `META_PAGE_ACCESS_TOKEN` por
   cliente.

---

## Modelo de datos — `clientes/<cliente>/ads.json`

```json
{
  "ad_20260905_143022_118349": {
    "fuente": "swap",
    "fuente_id": "swap_20260901_102143_409551",
    "contenido_url": "https://pub-.../swap_....png",
    "contenido_tipo": "foto",
    "nombre": "HOriginal Sky Blue — swap niña columpio",
    "estado": "en_cola",
    "objetivo": "OUTCOME_TRAFFIC",
    "presupuesto_diario_usd": 10.0,
    "dias": 3,
    "audiencia": {
      "edad_min": 18, "edad_max": 45,
      "paises": ["CO"],
      "intereses": []
    },
    "meta_ids": {
      "campaign_id": null, "adset_id": null,
      "ad_id": null, "creative_id": null
    },
    "metricas": {
      "impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0,
      "actualizado_en": null
    },
    "error": null,
    "creado_en": "2026-09-05T14:30:22"
  }
}
```

`estado`: `en_cola` (recién enviado, sin publicar) → `publicando` (job en
curso, mismo patrón `trabajos.iniciar` que el resto de la app) → `activo`
(campaña corriendo en Meta) → `pausado` → `error`.

Funciones de `ads.py` (mismo patrón que `swaps.py`):
`crear(...)`, `actualizar(cliente, ad_id, **campos)`, `cargar(cliente)`,
`eliminar(cliente, ad_id)`.

---

## Fase 1 — Ciclo mínimo de punta a punta

### Campaign (`meta_ads/campaign.py`)

Fuente: investigación §1. `POST /v25.0/act_{ad_account_id}/campaigns`

Campos que expone Fase 1 en la UI: `name`, `objective` (menú acotado a
`OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`, `OUTCOME_SALES`, `OUTCOME_LEADS` —
los 4 objetivos ODAX más comunes; el resto del enum completo queda en el
código como constante `OBJETIVOS_VALIDOS` para cuando se necesite exponer
más), `status=PAUSED` (siempre se crea pausada, nunca activa directo — el
usuario la activa a mano tras revisar, mismo espíritu de aprobación explícita
que el resto de la app), `special_ad_categories=["NONE"]` fijo en Fase 1
(campo obligatorio según la API — exponer las demás categorías, que aplican
a rubros regulados como empleo/vivienda/crédito, queda para cuando haga
falta).

```python
def crear_campaign(ad_account_id, nombre, objetivo, presupuesto_diario_centavos):
    payload = {
        "name": nombre,
        "objective": objetivo,
        "status": "PAUSED",
        "special_ad_categories": ["NONE"],
        "daily_budget": presupuesto_diario_centavos,
    }
    ...
```

### AdSet básico (`meta_ads/adset.py` + `targeting.py`)

Fuente: investigación §2. `POST /v25.0/act_{ad_account_id}/adsets`

Fase 1 expone: `age_min`/`age_max` (default 18-65), `genders` (opcional,
default ambos), `geo_locations.countries` (requerido — la API exige al menos
un país salvo que se use Custom Audience), `optimization_goal` (fijo según
objective: `OUTCOME_TRAFFIC`→`LINK_CLICKS`, `OUTCOME_ENGAGEMENT`→
`POST_ENGAGEMENT`, etc. — mapeo automático, no lo elige el usuario en Fase
1), `billing_event` (derivado del `optimization_goal`, mismo criterio),
`daily_budget` (viene del formulario de publicar), `start_time` (ahora),
`end_time` (ahora + días elegidos).

> ⚠️ **Sin verificar todavía**: la investigación (§1 y §2.1) documentó el
> enum completo de `objective` y de `optimization_goal` por separado, pero
> **no** una tabla de qué combinaciones son válidas entre sí — el mapeo de
> arriba es una propuesta razonable, no un hecho confirmado por una página
> oficial. Antes de implementar, hacer una llamada real (o `dry_run` seguido
> de una consulta a la API de validación) para confirmar que cada
> combinación propuesta no es rechazada.

Placements: Fase 1 no expone control manual — se omite `publisher_platforms`
etc. por completo, lo que activa colocación automática de Meta ("todas las
posiciones default posibles", confirmado en la investigación §2.2). Control
granular de placements es Fase 2.

### Ad (`meta_ads/ad.py`)

Fuente: investigación §3. `POST /v25.0/act_{ad_account_id}/ads`

Campos: `name`, `adset_id`, `creative` (`{creative_id: <id>}`),
`status=PAUSED`. Se crea siempre pausado — igual que la campaña, activar es
una acción explícita separada del usuario.

### AdCreative — imagen/video único (`meta_ads/creative.py`)

Fuente: investigación §4.2/§4.3. `POST /v25.0/act_{ad_account_id}/adcreatives`

Fase 1 solo implementa el formato más simple:

```python
def crear_creative_imagen(ad_account_id, page_id, imagen_url, mensaje, link, cta_type="LEARN_MORE"):
    payload = {
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {"image_url": imagen_url, "message": mensaje, "link": link},
        },
        "call_to_action_type": cta_type,  # ver enum completo en investigación §4.8
    }
```

Para video, `video_data` en vez de `link_data` (requiere subir el video
primero vía el endpoint de videos de la Página — reusa lógica ya existente en
`meta_uploader.upload_to_facebook_page`, que ya sube video y devuelve un
`video_id` usable acá).

`instagram_user_id` se agrega a `object_story_spec` cuando el destino incluye
Instagram (ya lo tenemos en `META_IG_USER_ID` por cliente).

### Insights básico (`meta_ads/insights.py`)

Fuente: investigación §5. `GET /{ad-id}/insights`

Fase 1 pide solo: `fields=impressions,clicks,spend,ctr,reach`,
`date_preset=maximum` (todo el histórico del anuncio, hasta 37 meses). Sin
breakdowns, sin reportes async — para el volumen de un anuncio individual de
esta app, la llamada síncrona alcanza.

```python
def obtener_resultados(ad_id):
    resp = requests.get(f"{BASE_URL}/{ad_id}/insights", params={
        "fields": "impressions,clicks,spend,ctr,reach",
        "date_preset": "maximum",
        "access_token": _token(),
    })
    ...
```

Se llama on-demand (botón "Actualizar resultados" en la UI) — no hay job de
fondo automático en Fase 1, coherente con que la retroalimentación
automática es una fase futura no cubierta aquí.

### UI Fase 1

Pestaña nueva "Publicidad": dos secciones, "Listos para publicar" (lo que
llegó vía `ads.crear(...)` desde otros módulos, formulario de
objetivo/presupuesto/días/país/edad) y "Publicados" (tarjetas con
impresiones/clics/gasto/CTR + botón "Actualizar resultados" + botón
"Pausar"/"Activar" que llama `POST /{campaign_id}` con `status` actualizado).

---

## Fase 2 — Targeting avanzado

Extiende `targeting.py` con los métodos que la investigación §2.2 documenta
completos: `.intereses_comportamientos(flexible_spec)`,
`.audiencias_personalizadas(ids)`, `.excluir_audiencias(ids)`,
`.idiomas(locales)`, `.dispositivo(user_os, user_device)`,
`.placements_granular(publisher_platforms, facebook_positions,
instagram_positions, ...)`.

**Antes de implementar**, resolver las dos ambigüedades marcadas en la
investigación (§ Brechas 1): confirmar si `home_type`/`connection_type`
existen como campos de primer nivel o viven dentro de `behaviors`, y si
`lookalike_audiences` es un campo separado o se referencia como
`custom_audiences` normal — ambas cosas requieren una llamada de prueba real
contra la API (crear un AdSet de prueba con esos campos y ver si la
validación los acepta) más que otra lectura de documentación.

UI: la pantalla de publicar gana una sección "Audiencia avanzada" opcional
(colapsada por default, coherente con el resto de la app — no abrumar con
campos que la mayoría no va a tocar).

---

## Fase 3 — Formatos de creative avanzados

- **Carrusel**: `object_story_spec.link_data.child_attachments`. **Antes de
  implementar**, fetchear la página dedicada
  `ad-creative-link-data-child-attachment` (no fetcheada en la
  investigación) para confirmar los sub-campos exactos por card.
- **Colección/Instant Experience**: `object_story_spec.template_data`.
- **Dynamic Creative**: `asset_feed_spec` (múltiples imágenes/videos/textos/
  títulos, Meta prueba combinaciones automáticamente) + `degrees_of_freedom_spec`.
  **Antes de implementar**, fetchear `ad-creative-features-spec` (no
  fetcheada) para saber qué transformaciones habilitar/deshabilitar.

UI: selector de formato al publicar (imagen/video único, ya en Fase 1;
carrusel; colección; dynamic creative), cada uno con su propio sub-formulario.

---

## Fase 4 — Insights completo

- Breakdowns: edad, género, dispositivo, ubicación, por asset (para comparar
  qué imagen/texto de un Dynamic Creative funcionó mejor) — lista completa en
  investigación §5.
- Reportes async (`POST /insights` → `report_run_id` → poll) para rangos de
  fecha grandes o breakdowns pesados. **Antes de implementar**, el mecanismo
  exacto de polling (endpoint, campo de estado, límites de concurrencia) no
  quedó documentado con cita textual — requiere otra pasada de investigación
  o una llamada de prueba real.
- Lista completa de 300+ métricas: la documentación de Meta genera esa
  página dinámicamente desde el schema vigente — se debe re-consultar
  `ad-account/insights` en el momento de implementar esta fase, no confiar
  en el subconjunto ya documentado.

UI: vista de comparación entre anuncios (tabla ordenable por métrica), y
gráfico de tendencia por día.

---

## Manejo de errores

Mismo patrón que el resto de la app: cada llamada HTTP fallida se captura,
el mensaje de error real de Meta (no un genérico) se guarda en
`ads.json[id].error` y se muestra en la tarjeta — igual que ya hicimos con
Nano Banana y Kling O1 en este mismo proyecto, donde ocultar el cuerpo del
error real costó horas de debugging esta sesión. Nunca incluir el
`access_token` en un mensaje de error que se vaya a guardar en JSON (mismo
incidente que ya tuvimos con la key de Gemini filtrada en `swaps.json`).

## Testing

No hay suite de tests en el proyecto (confirmado en `CLAUDE.md`). Verificación
manual: `python3 -m py_compile` antes de cada commit, y — dado que esto
gasta dinero real en publicidad — cada función de creación debe soportar un
modo `dry_run` que arma el payload completo y lo imprime sin enviarlo, para
poder revisar el payload exacto antes de la primera llamada real con
presupuesto de verdad.

---

## Próximos pasos

1. Usuario corre `auth/auth_meta_ads.py` (Fase 0) para su propia cuenta —
   esto no depende de nada más de este spec y puede arrancar ya.
2. Mientras tanto, implementar Fase 1 completa (los 5 módulos +
   `ads.py` + UI) contra cuentas de prueba/sandbox si Meta las ofrece, o con
   `dry_run` hasta que la cuenta real tenga `ads_management` aprobado.
3. Fases 2-4 se implementan en ese orden, cada una revisando primero las
   brechas de investigación marcadas arriba antes de escribir código.
