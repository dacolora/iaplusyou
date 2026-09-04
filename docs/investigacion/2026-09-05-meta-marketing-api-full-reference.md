# Investigación: Meta Marketing API — superficie completa de parámetros (Campaign, AdSet/Targeting, Ad, AdCreative, Insights)

Investigado en vivo el 5 sep 2026, **solo contra developers.facebook.com** (páginas
oficiales de Meta for Developers). Ninguna afirmación de este documento viene de
memoria del modelo ni de blogs/agregadores de terceros — cada URL listada fue
efectivamente obtenida (`WebFetch`) en esta sesión. Donde la búsqueda (`WebSearch`)
solo sirvió para *encontrar* la URL correcta, se indica aparte y no se usa como
fuente de un dato.

## Contexto y motivo

`iaplusyou` ya publica contenido orgánico en Facebook/Instagram vía
`uploaders/meta_uploader.py` (Graph API, permisos de página/organic posting). Esta
investigación es insumo para un **módulo nuevo de anuncios pagos** (Marketing API),
que requeriría el permiso `ads_management` — **no** lo tiene hoy la app. Este
documento es solo investigación: no se tocó `dashboard.py` ni ningún archivo de
proveedor.

## Nota importante sobre versión de la API observada

Las páginas fetchadas en esta sesión no todas mostraron la misma versión: la
mayoría (Campaign, AdSet, Targeting, Ad, Insights, placements) mostró **v25.0**,
pero las páginas de `object_story_spec` y `degrees-of-freedom-spec` (fetchadas más
tarde en la misma sesión) mostraron **v26.0**. Esto es consistente con que
developers.facebook.com sirve la versión "actual" del Graph API en el momento del
fetch — Meta libera versiones nuevas periódicamente y las páginas de referencia
"sin número de versión en la URL" siempre muestran la última. **No asumir v25.0
como fija**: al implementar, verificar la versión vigente en el momento de
construir el módulo y fijarla explícitamente en el endpoint (`/v25.0/...` o la que
corresponda) para evitar breaking changes silenciosos entre versiones.

---

## 1. Campaign object

**Fuente:** https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group/
(fetchada en vivo, v25.0 mostrada en la página)

**Endpoint de creación:** `POST /v25.0/act_{ad_account_id}/campaigns`

### Campos creables/settable

| Campo | Notas |
|---|---|
| `name` | string, admite emoji |
| `objective` | enum — ver abajo |
| `status` | `ACTIVE`, `PAUSED` (solo estos dos válidos en creación; otros estados existen para updates) |
| `buying_type` | `AUCTION` (default), `RESERVED` |
| `daily_budget` | int64 |
| `lifetime_budget` | int64 |
| `spend_cap` | int64, mínimo equivalente a $100 USD |
| `is_adset_budget_sharing_enabled` | boolean — Campaign Budget Optimization (CBO) |
| `bid_strategy` | enum — ver abajo |
| `special_ad_categories` | array, **requerido** — ver abajo |
| `special_ad_category_country` | array de códigos de país |
| `promoted_object` | objeto (depende del objective) |
| `adlabels` | array |
| `source_campaign_id` | para duplicar campañas |
| `start_time`, `stop_time` | |
| `is_skadnetwork_attribution` | boolean |
| `campaign_optimization_type` | |
| `execution_options` | |
| `iterative_split_test_configs` | |
| `budget_schedule_specs` | |

**`objective` (enum completo mostrado en la página):**
`APP_INSTALLS`, `BRAND_AWARENESS`, `CONVERSIONS`, `EVENT_RESPONSES`,
`LEAD_GENERATION`, `LINK_CLICKS`, `LOCAL_AWARENESS`, `MESSAGES`, `OFFER_CLAIMS`,
`OUTCOME_APP_PROMOTION`, `OUTCOME_AWARENESS`, `OUTCOME_ENGAGEMENT`,
`OUTCOME_LEADS`, `OUTCOME_SALES`, `OUTCOME_TRAFFIC`, `PAGE_LIKES`,
`POST_ENGAGEMENT`, `PRODUCT_CATALOG_SALES`, `REACH`, `STORE_VISITS`,
`VIDEO_VIEWS`

Nota: los valores `OUTCOME_*` son los objetivos "ODAX" (Outcome-Driven Ad
Experiences) que Meta introdujo como reemplazo del set clásico; los valores
clásicos (`LINK_CLICKS`, `CONVERSIONS`, etc.) siguen documentados en esta página
pero conviene verificar al implementar si siguen aceptándose para cuentas nuevas
o si Meta ya fuerza `OUTCOME_*` — la página fetchada no fue explícita sobre
deprecación, solo los listó todos juntos.

**`bid_strategy` (enum):** `LOWEST_COST_WITHOUT_CAP`, `LOWEST_COST_WITH_BID_CAP`,
`COST_CAP`, `LOWEST_COST_WITH_MIN_ROAS`

**`special_ad_categories` (enum):** `NONE`, `EMPLOYMENT`, `HOUSING`, `CREDIT`,
`ISSUES_ELECTIONS_POLITICS`, `ONLINE_GAMBLING_AND_GAMING`,
`FINANCIAL_PRODUCTS_SERVICES` — **campo obligatorio en toda campaña nueva**: la
página cita textualmente *"All businesses using the Marketing API must identify
whether or not new and edited campaigns belong to a Special Ad Category"*.

### Límite documentado
Máximo 200 ad sets por campaña (citado en la página).

### Acceso / permisos
La página no detalla el nivel de acceso exacto por campo, pero crear campañas
requiere el permiso `ads_management` sobre la cuenta publicitaria — ver sección 6
para el detalle de App Review encontrado en `docs/permissions/`.

---

## 2. AdSet object — incluyendo el Targeting spec completo

**Fuentes fetchadas en vivo:**
- AdSet (campos fuera de targeting): https://developers.facebook.com/docs/marketing-api/reference/ad-campaign/ (v25.0)
- Targeting básico: https://developers.facebook.com/docs/marketing-api/audiences/reference/basic-targeting/ (v25.0)
- Targeting avanzado: https://developers.facebook.com/docs/marketing-api/audiences/reference/advanced-targeting (v25.0)
- Placements: https://developers.facebook.com/docs/marketing-api/audiences/reference/placement-targeting/ (v25.0)

**Endpoint de creación:** `POST /v25.0/act_{ad_account_id}/adsets`

> Nota de navegación: la URL "clásica"
> `https://developers.facebook.com/docs/marketing-api/reference/ad-campaign/targeting-specs/`
> devolvió **404** al fetchearla en esta sesión — Meta reorganizó esta parte de
> la documentación bajo `/docs/marketing-api/audiences/reference/` (y en paralelo
> existe una segunda jerarquía nueva `/documentation/ads-commerce/marketing-api/...`
> encontrada por búsqueda pero no fetcheada por no ser necesaria una vez
> localizadas las páginas `/docs/...` equivalentes). Si se retoma esta
> investigación más adelante, usar las URLs `/docs/marketing-api/audiences/reference/*`
> listadas arriba, no la ruta `targeting-specs/` antigua.

### 2.1 Campos del AdSet fuera de targeting

| Campo | Detalle |
|---|---|
| `optimization_goal` | enum — ver abajo |
| `billing_event` | enum — ver abajo |
| `bid_amount` | integer; cap o target de costo según optimization_goal/billing_event |
| `bid_strategy` | mismo enum que Campaign: `LOWEST_COST_WITHOUT_CAP`, `LOWEST_COST_WITH_BID_CAP`, `COST_CAP`, `LOWEST_COST_WITH_MIN_ROAS` |
| `daily_budget` | int64 — presupuesto diario recurrente (si no se usa CBO a nivel campaña) |
| `lifetime_budget` | int64 — presupuesto total, requiere `end_time` |
| `start_time` | UTC UNIX timestamp |
| `end_time` | UTC UNIX timestamp |
| `attribution_spec` | lista de `{event_type, window_days, weight}` |
| `destination_type` | `WEBSITE`, `APP`, `MESSENGER`, `INSTAGRAM_DIRECT`, `INSTAGRAM_PROFILE`, más tipos ODAX (`ON_AD`, `ON_POST`, `ON_VIDEO`, `ON_PAGE`, `ON_EVENT`) |
| `promoted_object` | objeto target (pixel_id, page_id, application_id, product_set_id, etc. — varía según objective de la campaña) |
| `status` | `ACTIVE`, `PAUSED`, `DELETED`, `ARCHIVED` (solo `ACTIVE`/`PAUSED` válidos en creación) |

**`optimization_goal` (enum completo mostrado en la página):**
`NONE`, `APP_INSTALLS`, `AD_RECALL_LIFT`, `ENGAGED_USERS`, `EVENT_RESPONSES`,
`IMPRESSIONS`, `LEAD_GENERATION`, `QUALITY_LEAD`, `LINK_CLICKS`,
`OFFSITE_CONVERSIONS`, `PAGE_LIKES`, `POST_ENGAGEMENT`, `QUALITY_CALL`, `REACH`,
`LANDING_PAGE_VIEWS`, `VISIT_INSTAGRAM_PROFILE`, `ENGAGED_PAGE_VIEWS`, `VALUE`,
`THRUPLAY`, `DERIVED_EVENTS`, `APP_INSTALLS_AND_OFFSITE_CONVERSIONS`,
`CONVERSATIONS`, `IN_APP_VALUE`, `MESSAGING_PURCHASE_CONVERSION`,
`MESSAGING_DEEP_CONVERSATION_AND_FOLLOW`, `SUBSCRIBERS`, `REMINDERS_SET`,
`MEANINGFUL_CALL_ATTEMPT`, `PROFILE_VISIT`, `PROFILE_AND_PAGE_ENGAGEMENT`,
`ADVERTISER_SILOED_VALUE`, `AUTOMATIC_OBJECTIVE`,
`MESSAGING_APPOINTMENT_CONVERSION`

**`billing_event` (enum):** `APP_INSTALLS`, `CLICKS`, `IMPRESSIONS`,
`LINK_CLICKS`, `NONE`, `OFFER_CLAIMS`, `PAGE_LIKES`, `POST_ENGAGEMENT`,
`THRUPLAY`, `PURCHASE`, `LISTING_INTERACTION`

### 2.2 Targeting object — spec completo

#### Demografía básica
- `age_min` (int) — mínimo 13, default 18
- `age_max` (int) — hasta 65
- `genders` (array) — `1` (hombres), `2` (mujeres), omitir para todos
- `user_age_unknown` (boolean) — incluye usuarios de WhatsApp Status con edad
  desconocida
- `relationship_statuses` (array de int) — `1` soltero, `2` en pareja, `3`
  casado, `4` comprometido, `6` no especificado

#### Ubicación geográfica (`geo_locations`)
- `countries` (array de códigos ISO, ej. "US", "JP")
- `regions` (array de `{key}`), límite 200
- `cities` (array de `{key, radius (10–50 millas / 17–80 km), distance_unit}`), límite 250
- `zips` (array de `{key}`), límite 50,000
- `places` (array de `{key, name, radius, distance_unit}`), límite 200
- `custom_locations` (array de `{address_string}` O `{latitude, longitude}` +
  `radius, distance_unit, name`), límite 200
- `geo_markets` (array, claves de mercado Comscore), límite 2,500
- `electoral_district` (array)
- `location_types` (array) — `["home", "recent"]`, default ambos si se omite
- `country_groups` (array) — valores enumerados: `worldwide`, `africa`, `afta`,
  `android_app_store`, `android_free_store`, `apec`, `asia`, `caribbean`,
  `central_america`, `cisfta`, `eea`, `emerging_markets`, `europe`, `gcc`,
  `itunes_app_store`, `mercosur`, `nafta`, `north_america`, `oceania`,
  `south_america`
- `excluded_geo_locations` (objeto, misma estructura que `geo_locations`)

Restricciones citadas textualmente en la página: *"You must specify at least one
country in targeting, unless you use a Custom Audience"*; el uso de `radius`
puede generar error si se combina con múltiples ubicaciones; una dirección tipo
apartado postal (PO Box) sola no es válida para `custom_locations` — se requiere
al menos una dirección de calle.

#### Interés / comportamiento / segmentación avanzada ("flexible targeting")
- `interests` (array de `{id, name}`)
- `behaviors` (array de `{id, name}`)
- `flexible_spec` (array de objetos que contienen, entre otros, `interests`) —
  implementa lógica AND entre bloques del array, OR dentro de cada bloque
- `life_events` (array de `{id, name}`)
- `family_statuses` (array de `{id, name}`)
- `education_schools` (array de `{id, name}`), máx. 200
- `education_statuses` (array de int 1–13, niveles de estudio)
- `college_years` (array de años, el más antiguo 1980)
- `education_majors` (array), máx. 200
- `work_employers` (array), máx. 200
- `work_positions` (array), máx. 200
- `income` (array de `{id, name}`)
- `industries` (array de `{id, name}`)
- `user_adclusters` (array, "broad category targeting" (BCT) pairs), máx. 50

Nota: la página de advanced-targeting no mostró explícitamente un campo llamado
`home_type` — puede estar dentro de las categorías de `behaviors`/BCT
(comportamiento de "home ownership") en vez de ser un campo top-level propio; no
se pudo confirmar su existencia como campo de primer nivel en esta sesión.

Restricción citada: *"If you use `flexible_spec`, you must also provide one of
the following under `targeting`: `geo_locations`, `custom_audiences`,
`product_audience_specs`, or `dynamic_audience_ids`."*

#### Audiencias
- `custom_audiences` (array — IDs numéricos o `{id}`), máx. 500
- `excluded_custom_audiences` (array), máx. 500
- (`lookalike_audiences` no apareció como campo propio separado en las páginas
  fetcheadas — las audiencias lookalike se referencian normalmente igual que
  cualquier `custom_audiences` por su ID, ya que un lookalike es un tipo de
  Custom Audience en la Graph API; no se encontró en esta sesión una página que
  lo contradijera ni lo confirmara explícitamente como campo separado —
  flag de ambigüedad, ver sección de brechas)

#### Idioma
- `locales` (array, IDs de idioma/locale), máx. 50

#### Dispositivo / conexión
- `user_os` (array) — `iOS`, `Android`, o rangos de versión (ej.
  `iOS_ver_8.0_and_above`)
- `user_device` (array) — nombres de dispositivo específicos según el OS
- `excluded_user_device` (array)
- `wireless_carrier` (array) — valor documentado: `Wifi` únicamente
- (`connection_type` no apareció como nombre de campo en las páginas
  fetcheadas en esta sesión — el control de tipo de conexión parece cubrirse
  vía `wireless_carrier`/`user_device`, no se pudo verificar un campo separado
  llamado literalmente `connection_type`)

#### Ubicación de publicación / placements
- `publisher_platforms` (array): `facebook`, `instagram`, `threads`,
  `messenger`, `audience_network`
- `facebook_positions` (array): `feed`, `right_hand_column`, `marketplace`,
  `video_feeds`, `story`, `search`, `instream_video`, `facebook_reels`,
  `facebook_reels_overlay`, `profile_feed`, `notification`
- `instagram_positions` (array): `stream`, `story`, `explore`, `explore_home`,
  `reels`, `profile_feed`, `ig_search`, `profile_reels`
- `audience_network_positions` (array): `classic`, `rewarded_video`
- `messenger_positions` (array): `sponsored_messages`, `story`
- `threads_positions` (array): `threads_stream`
- `whatsapp_positions` (array): `status`
- `device_platforms` (array): `mobile`, `desktop`

Lógica documentada: dentro de un mismo parámetro los valores son OR (ej.
`publisher_platforms=['facebook','instagram']` entrega en ambos); entre
parámetros distintos es AND (ej. `publisher_platforms=['facebook']` +
`device_platforms=['mobile']` entrega solo en Facebook móvil). Si no se
especifica nada en un campo de placement, Meta usa "todas las posiciones
default posibles" para ese campo (colocación automática).

#### Automatización de targeting
```json
"targeting_automation": {
  "individual_setting": { "age": 0|1, "gender": 0|1, "geo": 0|1 }
}
```

---

## 3. Ad object

**Fuente:** https://developers.facebook.com/docs/marketing-api/reference/adgroup/
(fetchada en vivo, v25.0)

**Endpoint de creación:** `POST /v25.0/act_{ad_account_id}/ads`

### Campos requeridos
- `name` (string)
- `adset_id` (int64) — requerido en creación
- `creative` (objeto AdCreative — ID existente o spec inline)
- `status` (enum) — `ACTIVE` o `PAUSED` en creación

### Campos adicionales creables
- `ad_schedule_start_time` / `ad_schedule_end_time` (datetime) — horario de
  entrega del anuncio individual
- `adlabels` (list)
- `conversion_domain` (string) — dominio donde ocurren las conversiones;
  **requerido cuando la campaña comparte datos de píxel**
- `tracking_specs` (Object) — registra acciones de la gente sobre el anuncio
- `display_sequence` (int64) — secuencia dentro de la campaña
- `engagement_audience` (boolean) — crea audiencia a partir de quienes
  interactúan con el anuncio
- `creative_asset_groups_spec` (string)
- `execution_options` (list) — `validate_only`, `synchronous_ad_review`,
  `include_recommendations`

### Notas de comportamiento
Un anuncio nuevo entra en estado de revisión pendiente y requiere aprobación de
Meta antes de poder entregar. La documentación recomienda crear en `PAUSED`
durante pruebas para evitar gasto accidental.

---

## 4. AdCreative object — todos los formatos

**Fuentes fetchadas en vivo:**
- Creative principal: https://developers.facebook.com/docs/marketing-api/reference/ad-creative/ (v25.0)
- `object_story_spec`: https://developers.facebook.com/docs/marketing-api/reference/ad-creative-object-story-spec/ (v26.0)
- `call_to_action` (link_data): https://developers.facebook.com/docs/marketing-api/reference/ad-creative-link-data-call-to-action/ (v26.0)
- `asset_feed_spec`: https://developers.facebook.com/docs/marketing-api/ad-creative/asset-feed-spec/ (v25.0)
- `degrees_of_freedom_spec`: https://developers.facebook.com/docs/marketing-api/reference/ad-creative-degrees-of-freedom-spec/ (v26.0)

**Endpoint de creación:** `POST /v25.0/act_{ad_account_id}/adcreatives`
**Cómo se adjunta a un anuncio:** el `Ad` referencia la creative vía su campo
`creative` (usualmente `{creative_id: <ID>}`, o el spec inline al crear el ad
directamente).

### 4.1 `object_story_spec` (contenedor común a la mayoría de formatos)

| Campo | Tipo | Uso |
|---|---|---|
| `page_id` | numeric string | Página de Facebook donde se crea el post no publicado subyacente |
| `instagram_user_id` | numeric string | Cuenta de Instagram para publicar el anuncio |
| `link_data` | AdCreativeLinkData | Posts de enlace y **carrusel** |
| `photo_data` | AdCreativePhotoData | Posts de foto |
| `video_data` | AdCreativeVideoData | Posts de video |
| `text_data` | AdCreativeTextData | Posts solo texto |
| `template_data` | AdCreativeLinkData | Dynamic Product Ads |
| `product_data` | list\<AdCreativeProductData\> | Experiencias basadas en catálogo |

La página fetcheada no detalló los sub-campos internos de `AdCreativeLinkData`
(como `child_attachments`, `image_hash`, `message`, `picture`) más allá de
nombrarlos como tipos referenciados — ver brechas al final.

### 4.2 Formato: imagen única / enlace (Link Ad)
- `object_story_spec.link_data`: `image_hash` o `image_url`, `link`, `message`
- `object_story_spec.page_id`
- `name`
- `call_to_action_type` (opcional, a nivel raíz según el ejemplo de la página) o
  `call_to_action` dentro de `link_data`

### 4.3 Formato: video único
- `object_story_spec.video_data`: `video_id`, `image_url`/`image_hash`
  (thumbnail)
- `call_to_action` opcional: objeto `{type, value}`

### 4.4 Formato: carrusel
- `object_story_spec.link_data.child_attachments` (array) — la página general
  de AdCreative confirma que carrusel usa `child_attachments` dentro de
  `link_data`; existe una página de referencia dedicada
  (`ad-creative-link-data-child-attachment`) que **no se fetcheó en esta
  sesión** — ver brechas.

### 4.5 Formato: colección / Instant Experience
- `object_story_spec.template_data` (tipo `AdCreativeLinkData`, reutilizado
  para Dynamic Product Ads / Instant Experience según la página de
  object_story_spec)

### 4.6 Formato: Dynamic Creative (`asset_feed_spec`)

Fuente: https://developers.facebook.com/docs/marketing-api/ad-creative/asset-feed-spec/ (v25.0)

Campos de nivel superior documentados:
- `images` — array de `{hash, url_tags}`
- `videos` — array de `{video_id, thumbnail_url, url_tags}`
- `bodies` — array de textos de cuerpo
- `titles` — array de títulos
- `descriptions` — array de descripciones
- `call_to_action_types` — array de strings CTA (ej. `SHOP_NOW`, `LEARN_MORE`)
- `call_to_actions` — array de objetos CTA completos
- `link_urls` — array de `{website_url}`
- `ad_formats` — array de formatos, ej. `SINGLE_IMAGE`, `SINGLE_VIDEO`
- `optimization_type` — ej. `REGULAR`

Nota citada textualmente de la página: *"For Dynamic Creative, `asset_feed_spec`
should **not** have customization rules."*

### 4.7 `degrees_of_freedom_spec`

Fuente: https://developers.facebook.com/docs/marketing-api/reference/ad-creative-degrees-of-freedom-spec/ (v26.0)

- Controla *"how different ad assets can be modified by Dynamic Creative when
  optimizing the creative"*.
- Único campo documentado en la página: `creative_features_spec` (tipo
  `AdCreativeFeaturesSpec`) — *"metadata to specify behavior for individual
  features"*. El detalle de qué transformaciones habilita/deshabilita cada
  feature vive en la página `ad-creative-features-spec`, **no fetcheada en
  esta sesión** (ver brechas).
- Esta sub-referencia solo soporta **lectura** (`Read: sí`; `Create/Update/
  Delete: no` según la tabla de operaciones de la página) — es metadata que se
  consulta, no un campo que se setea directo vía este endpoint específico
  (se setea como parte del payload de creación de la creative, la tabla de
  operaciones se refiere al nodo de referencia en sí).

### 4.8 `call_to_action` — enum `type` (fuente: ad-creative-link-data-call-to-action, v26.0)

Lista completa observada en la página (100+ valores):
`OPEN_LINK`, `LIKE_PAGE`, `SHOP_NOW`, `PLAY_GAME`, `INSTALL_APP`, `USE_APP`,
`CALL`, `CALL_ME`, `VIDEO_CALL`, `INSTALL_MOBILE_APP`, `USE_MOBILE_APP`,
`MOBILE_DOWNLOAD`, `BOOK_TRAVEL`, `LISTEN_MUSIC`, `WATCH_VIDEO`, `LEARN_MORE`,
`SIGN_UP`, `DOWNLOAD`, `WATCH_MORE`, `NO_BUTTON`, `VISIT_PAGES_FEED`,
`CALL_NOW`, `APPLY_NOW`, `CONTACT`, `BUY_NOW`, `GET_OFFER`, `GET_OFFER_VIEW`,
`BUY_TICKETS`, `UPDATE_APP`, `GET_DIRECTIONS`, `BUY`, `SEND_UPDATES`,
`MESSAGE_PAGE`, `DONATE`, `SUBSCRIBE`, `SAY_THANKS`, `SELL_NOW`, `SHARE`,
`DONATE_NOW`, `GET_QUOTE`, `CONTACT_US`, `ORDER_NOW`, `START_ORDER`,
`ADD_TO_CART`, `VIEW_CART`, `VIEW_IN_CART`, `VIDEO_ANNOTATION`, `RECORD_NOW`,
`INQUIRE_NOW`, `CONFIRM`, `REFER_FRIENDS`, `REQUEST_TIME`, `GET_SHOWTIMES`,
`LISTEN_NOW`, `TRY_DEMO`, `FOLLOW_USER`, `RAISE_MONEY`, `SEE_SHOP`,
`GET_DETAILS`, `FIND_OUT_MORE`, `VISIT_WEBSITE`, `BROWSE_SHOP`, `EVENT_RSVP`,
`WHATSAPP_MESSAGE`, `FOLLOW_NEWS_STORYLINE`, `SEE_MORE`, `BOOK_NOW`,
`FIND_A_GROUP`, `PAY_TO_ACCESS`, `PURCHASE_GIFT_CARDS`, `FOLLOW_PAGE`,
`SEND_A_GIFT`, `SWIPE_UP_SHOP`, `SWIPE_UP_PRODUCT`, `SEND_GIFT_MONEY`,
`PLAY_GAME_ON_FACEBOOK`, `GET_STARTED`, `OPEN_INSTANT_APP`, `AUDIO_CALL`,
`GET_PROMOTIONS`, `JOIN_CHANNEL`, `MAKE_AN_APPOINTMENT`, `ASK_ABOUT_SERVICES`,
`BOOK_A_CONSULTATION`, `GET_A_QUOTE`, `BUY_VIA_MESSAGE`, `ASK_FOR_MORE_INFO`,
`CHAT_WITH_US`, `VIEW_PRODUCT`, `VIEW_CHANNEL`, `GET_IN_TOUCH`,
`ASK_A_QUESTION`, `START_A_CHAT`, `CHAT_NOW`, `ASK_US`, `WATCH_LIVE_VIDEO`,
`JOIN_LIVE_VIDEO`, `SHOP_WITH_AI`, `TRY_ON_WITH_AI`

Limitación citada: Facebook Stories excluye soporte para `CALL_NOW` y
`GET_DIRECTIONS`.

El campo `value` del CTA (subestructura con `link`, `app_link`, `page`,
`product_link`, etc.) tiene su propia página de referencia
(`ad-creative-link-data-call-to-action-value`) que **no se fetcheó** en esta
sesión — se confirmó que existe pero no su contenido exacto.

### Límite documentado
La página general de AdCreative cita: *"Only returns 50,000 ad creatives;
pagination past this is unavailable."*

---

## 5. Insights API

**Fuentes fetchadas en vivo:**
- Overview: https://developers.facebook.com/docs/marketing-api/insights/ (v25.0 referenciada en el texto)
- Reference de campos: https://developers.facebook.com/docs/marketing-api/reference/ad-account/insights/ (v25.0)
- Breakdowns: https://developers.facebook.com/docs/marketing-api/insights/breakdowns/

### Endpoints por nivel
- `GET /{ad-account-id}/insights` — nivel cuenta
- `GET /{campaign-id}/insights` — nivel campaña
- `GET /{ad-set-id}/insights` — nivel ad set
- `GET /{ad-id}/insights` — nivel ad individual
- También soporta `POST /act_{ad_account_id}/insights` para generar reportes
  asíncronos (ver abajo)
- El parámetro `level` (`account`, `campaign`, `adset`, `ad`) permite pedir
  agregación a un nivel distinto del nodo consultado

### Métricas/campos observados
La página overview confirma explícitamente solo `impressions`, `clicks`,
`spend` como ejemplo mínimo, y remite a la página de referencia de campos para
la lista completa. La página de referencia (`ad-account/insights`) devolvió,
además de esos tres:
- `reach`, `frequency`
- `ctr`, `cpc`, `cpm`, `cpp` (costo estimado por 1000 personas alcanzadas)
- `actions`, `action_values`, `cost_per_action_type`, `total_actions`
- `conversions`, `conversion_values`, `cost_per_conversion`
- Métricas de video: `video_play_actions`, `video_p25_watched_actions`,
  `video_p50_watched_actions`, `video_p75_watched_actions`,
  `video_p95_watched_actions`, `video_p100_watched_actions`,
  `video_complete_watched_actions`, `cost_per_completed_video_view`,
  `video_avg_time_watched_actions`, `video_play_curve_actions`

La página en sí declara *"you can customize your requests and obtain nearly
any metric available in Meta Ads Manager"* y que existen "300+ campos" en
total — **no se pudo extraer la lista literal completa de 300+ campos en esta
sesión**; lo anterior es el subconjunto que la herramienta de fetch devolvió
explícitamente. Para una integración real, la lista completa debe
consultarse directamente contra
`https://developers.facebook.com/docs/marketing-api/reference/ad-account/insights/`
en el momento de implementar (la página es auto-generada desde el schema
vigente y cambia).

### Breakdowns disponibles (fuente: `insights/breakdowns/`)
- Demográfico/geográfico: `age`, `gender`, `country`, `region`, `dma`
- Dispositivo/plataforma: `device_platform`, `impression_device`,
  `publisher_platform`, `platform_position`
- Relacionados a acción: `action_type`, `action_device`, `action_destination`,
  `action_target_id`, `action_reaction`, `action_video_sound`,
  `action_video_type`
- Basado en asset (Dynamic Creative): `ad_format_asset`, `body_asset`,
  `call_to_action_asset`, `description_asset`, `image_asset`,
  `link_url_asset`, `title_asset`, `video_asset`
- Producto/carrusel: `product_id`, `action_carousel_card_id`,
  `action_carousel_card_name`, `action_canvas_component_name`
- Otros: `frequency_value`, `user_segment_key`, `place_page_id`,
  `skan_campaign_id`, `skan_conversion_id`, `app_id`,
  `is_conversion_id_modeled`

**Restricciones citadas textualmente:** *"Do not request the following fields
when specifying a breakdown: app_store_clicks, newsfeed_avg_position,
newsfeed_clicks, relevance_score, newsfeed_impressions"*. También: los
breakdowns "Tipo 1" (region, dma, hourly_stats) no devuelven ciertas métricas
off-Meta; los breakdowns "Tipo 2" pierden valores de breakdown en algunos
casos; los breakdowns por hora no se pueden combinar con campos de video; solo
ciertas combinaciones/permutaciones de breakdowns están soportadas
simultáneamente (no se listó la matriz completa de combinaciones válidas en la
página fetcheada).

### Parámetros de request
- `fields` — lista separada por comas de métricas
- `breakdowns` — lista de dimensiones de desglose
- `date_preset` (enum observado): `today`, `yesterday`, `this_month`,
  `last_month`, `this_quarter`, `last_7d`, `last_14d`, `last_28d`, `last_30d`,
  `last_90d`, `maximum` (hasta 37 meses). El valor `lifetime` está
  **deprecado/deshabilitado desde Graph API v10.0**, citado textualmente en
  la página.
- `time_range` — alternativa a `date_preset`: `{since: "YYYY-MM-DD", until: "YYYY-MM-DD"}`
- `level` — `account`, `campaign`, `adset`, `ad`
- Comportamiento default sin parámetros: métricas básicas del objeto, típicamente
  de los últimos 30 días

### Async vs. sync
- Un `POST` al edge `/insights` crea un reporte asíncrono y devuelve
  `{report_run_id: <numeric_string>}`; ese ID se usa después para hacer poll y
  recuperar el resultado procesado.
- La página menciona genéricamente "Asynchronous Requests" como funcionalidad
  a explorar pero **no detalló en el contenido fetcheado** el mecanismo exacto
  de polling (endpoint de poll, campo de estado `async_status`, límites de
  cuántos reportes async concurrentes se permiten) — ver brechas.

---

## 6. Acceso / App Review por sección

**Fuente:** https://developers.facebook.com/docs/permissions/ (fetchada en vivo;
página general de referencia de permisos, no específica de Marketing API)

- **`ads_management`** — permiso central para las 5 áreas de este documento
  (crear/editar Campaign, AdSet, Ad, AdCreative). Descrito textualmente como:
  *"read and manage the ad accounts that belong to you or that account owners
  granted you access to"*. Depende de otros permisos: `pages_read_engagement`,
  `pages_show_list`. Requiere **App Review** para acceder a datos que la app no
  posee/administra directamente, y **Business Verification** para acceder en
  modalidad "advanced access" (nomenclatura antigua). Meta exige además una
  grabación de pantalla del flujo de login/permiso/uso de datos de rendimiento
  publicitario como parte de la revisión.
- **`ads_read`** — permiso separado, de solo lectura, para el edge de
  Insights/reportes (*"access the advertising statistics API to obtain ad
  reports"*) y para enviar eventos server-side. También requiere App Review
  pero, según lo citado en la página, **no exige Business Verification** de la
  misma forma que `ads_management`.
- La terminología "Standard Access" / "Advanced Access" está siendo reemplazada
  por Meta (nomenclatura encontrada por `WebSearch`, no confirmada por fetch
  directo de una página que lo declare version-por-version: referencias a
  "Limited Access"/"Full Access" aparecieron en resultados de búsqueda de blog
  de Meta, mayo 2026, pero **no se fetcheó esa página oficial en esta sesión**
  — ver brechas). Lo que sí se confirmó por fetch directo en `docs/permissions/`
  es que `ads_management` requiere revisión de app y verificación de negocio
  para acceso ampliado.
- **Relevancia para iaplusyou:** la app hoy solo tiene los permisos orgánicos
  usados por `uploaders/meta_uploader.py` (posting a Página/Instagram vía Graph
  API estándar). Ninguno de los 5 objetos cubiertos aquí (Campaign, AdSet, Ad,
  AdCreative, Insights de ads) es alcanzable sin agregar `ads_management` (y
  `ads_read` si se quiere separar el alcance de solo-lectura de reportes) como
  permisos nuevos, pasar App Review, y completar Business Verification de la
  app/negocio en Meta for Developers antes de poder llamar cualquiera de estos
  endpoints en producción con una cuenta publicitaria que no sea propiedad
  directa del mismo desarrollador/rol de la app.

---

## Brechas y ambigüedades explícitas (no rellenadas con memoria)

1. **Targeting**: no se pudo confirmar en esta sesión si `home_type` y
   `connection_type` existen como campos de primer nivel del objeto Targeting
   (no aparecieron en `basic-targeting` ni `advanced-targeting`); es posible
   que estén cubiertos por `behaviors`/BCT en vez de ser campos dedicados.
   `lookalike_audiences` tampoco apareció como campo propio separado de
   `custom_audiences` en las páginas fetcheadas — en la Graph API los
   lookalikes suelen referenciarse por ID igual que cualquier Custom Audience,
   pero esto no quedó confirmado por una cita textual de una página oficial en
   esta sesión.
2. **AdCreative — `child_attachments` (carrusel)**: se confirmó su existencia
   y propósito, pero la página de referencia dedicada
   (`ad-creative-link-data-child-attachment`) no se fetcheó; faltan los
   sub-campos exactos (`link`, `image_hash`, `name`, `description`,
   `call_to_action` por card).
3. **AdCreative — `call_to_action_value`**: la subestructura exacta del campo
   `value` dentro de un objeto `call_to_action` (con `link`, `app_link`,
   `page`, `product_link`, etc.) no se fetcheó — solo se confirmó que la página
   existe.
4. **AdCreative — `AdCreativeFeaturesSpec`**: el detalle de qué
   transformaciones habilita cada "feature" dentro de `degrees_of_freedom_spec`
   no se fetcheó.
5. **Insights**: la lista de 300+ campos de métricas mencionada por la propia
   documentación de Meta no se pudo extraer completa vía fetch en esta sesión
   — se documentó el subconjunto explícito que la herramienta devolvió. El
   mecanismo exacto de polling de reportes asíncronos (endpoint de poll,
   nombre del campo de estado, límites de concurrencia) tampoco quedó
   documentado con una cita textual.
6. **Nomenclatura "Standard/Advanced Access" vs "Limited/Full Access"**: se
   encontró por `WebSearch` (no por fetch directo de una página oficial
   dedicada) que Meta habría renombrado estos niveles de acceso hacia mayo de
   2026; esto debería reverificarse contra una página oficial fetcheada antes
   de documentarlo como hecho para el spec del módulo de ads.
7. **Endpoint URL duplicada**: existe una segunda jerarquía de documentación
   (`developers.facebook.com/documentation/ads-commerce/marketing-api/...`)
   que apareció repetidamente en resultados de búsqueda junto a la jerarquía
   `/docs/marketing-api/...` que sí se usó en este documento. No se determinó
   en esta sesión si son estructuras duplicadas, una migración en curso, o
   contenido divergente — al retomar esta investigación, vale la pena
   fetchear al menos una página de esa segunda jerarquía y comparar contra su
   equivalente en `/docs/` para confirmar si son iguales o si una está más
   actualizada que la otra.
