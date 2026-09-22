# Investigación: API de Triple Whale como fuente de métricas y atribución (2026-09-21)

Preparado el 2026-09-21 solo con fuentes primarias de Triple Whale: el portal de desarrolladores
(developers.triplewhale.com), la referencia oficial de la API (triplewhale.readme.io, que es a donde
apuntan los enlaces "API Documentation" y "Developer Docs" de la KB y el "Read the docs" del portal),
la Knowledge Base (kb.triplewhale.com) y triplewhale.com (precios, página /api, términos). Cada dato
lleva su URL; las citas van en inglés tal como las sirve Triple Whale. Lo que ninguna fuente escribe va
marcado **no documentado** y recogido en §10. Las páginas de readme.io llevan un `updatedAt` que anoto
cuando importa.

Una advertencia de método: developers.triplewhale.com es un portal con login (email/contraseña o
Google) y no publica documentación; lo único que pude leer de él es su bundle JavaScript público
(`/assets/index-DRabXQfu.js`). Todo lo que salga de ahí va marcado **(portal, código)**: es fuente
primaria, pero no es documentación y puede cambiar sin aviso.

Contexto: Creatv Machine hoy lee insights por anuncio de la Marketing API de Meta (gasto,
impresiones, clics, thruplay, compras, ingresos, ROAS/CPA) y los guarda como snapshots acumulados por
anuncio (`metrica_snapshot`); el tablero y el decisor trabajan con deltas de esos acumulados. La
pregunta es si Triple Whale puede ser también (o en su lugar) la fuente de métricas y atribución, con
una tienda de Triple Whale por proyecto.

## Resumen ejecutivo

1. **Hay API pública REST/JSON** con base `https://api.triplewhale.com/api/v2/` y llave en la cabecera
   `x-api-key`. La llave la genera un usuario en Settings › API Keys (`app.triplewhale.com/api-keys`)
   con scopes por endpoint, se muestra una sola vez, queda ligada a ese usuario y sirve para todas las
   tiendas a las que él tiene acceso: la tienda va en cada petición como dominio (`shop-id`, p. ej.
   `example.myshopify.com`).
2. **No existe un endpoint "métricas por anuncio con atribución"**. Lo que Creatv necesita se saca
   con `POST /orcabase/api/sql` (SQL sabor ClickHouse) sobre dos tablas documentadas: `ads_table`
   (lo que reporta Meta: spend, impressions, clicks, thruplays, conversions, conversion_value, una fila
   por anuncio y día) y `pixel_joined_tvf` (lo atribuido por el Triple Pixel: orders_quantity,
   order_revenue, new_customer_orders, pixel_roas, pixel_cpa, con `model` y `attribution_window` como
   columnas filtrables; por defecto Triple Attribution y ventana lifetime).
3. Los dos endpoints "de producto" son **Summary** (`POST /summary-page/get-data`: KPIs de la tienda
   por periodo; los nombres de métricas no están documentados) y **Customer Journey**
   (`POST /attribution/get-orders-with-journeys-v2`: pedidos con atribución first click + eventos del
   journey, paginado hasta 100 por página).
4. **Límites documentados**: SQL 100 req/s y 600 req/min; Data-In 25 000 req/min; eventos offline
   1 000/min y 3 KB; cabeceras `RateLimit-Policy` / `RateLimit` / `Retry-After` (429). Tamaño máximo de
   respuesta, número de filas y profundidad histórica: **no documentados**.
5. **Planes**: la tabla de precios (2026-09-21) marca "Data-In API" y "Data-Out API" en las cuatro
   columnas (Free, Foundation, Automate, Enterprise); la guía de errores dice "All paid Triple Whale
   plans include access to the API endpoints they are entitled to"; la KB de planes advierte que MCP
   ≠ API y que "native API, headless-platform, or custom integration access … may require different
   products, permissions, or agreements". No hay costo aparte, beta ni solicitud documentados para la
   API con llave. Las **apps OAuth** de terceros (portal) sí exigen cuenta de desarrollador y revisión.
6. **Sin SDK oficial de servidor** (solo el Triple Pixel Mobile SDK, para emitir eventos desde apps) y
   **sin webhooks de salida**: todo es polling. Hay MCP (`https://mcp.triplewhale.com/v1/mcp`) con
   OAuth2 `moby:read` o llave "MCP: Read".
7. Para Creatv: TW puede alimentar el tablero y el decisor con filas diarias por anuncio (y por país)
   vía SQL, guardando por proyecto la llave (cifrada), el dominio de la tienda, el modelo y la ventana.
   Condición previa: los anuncios que Creatv crea deben llevar los parámetros de rastreo de TW
   (`tw_source={{site_source_name}}&tw_adid={{ad.id}}`) en "URL Parameters"; sin ellos TW solo tiene
   gasto/clics/impresiones de Meta y "attribution accuracy may suffer significantly".

## 1. Autenticación

**Llave de API (lo documentado).**
- Dónde se crea: "To create a new API key, head to Settings > API Keys and click Generate an API Key"
  (KB, https://kb.triplewhale.com/en/articles/8116412-creating-and-managing-api-keys, 2026-07-26). La
  referencia lo llama "Data > APIs" y enlaza `https://app.triplewhale.com/api-keys`
  (https://triplewhale.readme.io/reference/creating-and-managing-triple-whale-api-keys, 2026-06-18).
- Descripción + scopes + "Generate"; "Your newly generated key will be displayed in a popup. Copy and
  store it somewhere safe. Once the popup is closed, you will no longer be able to access it again."
  La tabla de llaves muestra prefijo, descripción, scopes y "the timestamp of the last API call using
  the key". Revocar: "This action is irreversible." (mismas fuentes).
- Cabecera: `x-api-key`. Prueba documentada:
  `curl https://api.triplewhale.com/api/v2/users/api-keys/me -H "x-api-key: <PUT_API_KEY_HERE>"` (KB
  8116412). "All Triple Whale API requests should be sent to `https://api.triplewhale.com/api/v2/...`
  and authenticated with an `x-api-key` header. Shopify session JWTs and other token types are not
  supported." (https://triplewhale.readme.io/reference/troubleshooting-common-triple-whale-api-errors,
  2026-08-31). El esquema OpenAPI de cada endpoint declara `securitySchemes.apiKeyAuth: {type: apiKey,
  in: header, name: x-api-key}` (p. ej. https://triplewhale.readme.io/reference/get-summary-page-data).
- **Por tienda o por cuenta**: la llave es de la cuenta/usuario, no de la tienda. "API keys are tied to
  the user who created them. If that user loses access to the account (e.g. removed from the
  workspace), the associated API key will also stop working." (readme, API keys). La tienda se manda en
  cada petición y "The API key owner must also have access to the shop, otherwise the request will
  return 403." (https://triplewhale.readme.io/reference/get-customer-journey-attribution-data y
  https://triplewhale.readme.io/reference/create-ad-record).
- **Scopes** (readme, API keys, 2026-06-18): "Summary Page: Read", "Pixel Attribution: Read",
  "MCP: Read", "Ads: Write", "Orders: Write", "Customers: Write", "Products: Write", "PPS: Write",
  "Subscriptions: Write", "Compliance: Write". La KB (8116412) solo lista los dos primeros. La guía de
  errores añade un scope llamado **"Data Out"** para el endpoint SQL: "the endpoint being called
  requires a key with the matching scope (for example, Orders: Write for order ingestion, Pixel
  Attribution: Read for the Customer Journey endpoint, Summary Page: Read for Summary Page data, and
  Data Out for the SQL endpoint)". Ese nombre no aparece en la lista de la página de llaves —
  discrepancia entre páginas, ver §10.
- Buenas prácticas documentadas: "Use separate keys for production, testing, and development
  workflows" (https://triplewhale.readme.io/reference/introduction-to-the-triple-whale-api, 2026-08-31);
  "Regenerate periodically"; "Limit scope" (readme, API keys).
- Errores: 401 = llave ausente/revocada/sin scope/JWT de Shopify; 403 en SQL = casi siempre `shopId`
  ausente o mal formado ("The 403 response message reads "Access token is required", but on the SQL
  endpoint the actual cause is a missing shopId"); 500 = "Unrecognized shop identifier" (guía de
  errores).

**OAuth (lo documentado).** Solo para MCP: "OAuth2: A secure sign-in standard that authorizes an
external tool to access your Triple Whale data without sharing an API key. It is scoped to read-only
access (moby:read) and can be revoked at any time." … "Add Triple Whale. Select Triple Whale from the
tool's connector directory where available, or enter the server URL https://mcp.triplewhale.com/v1/mcp"
(https://kb.triplewhale.com/en/articles/15656798-triple-whale-mcp, 2026-08-20). Alternativa: llave
"MCP: Read" en `x-api-key` vía `npx mcp-remote` (misma KB). En toda la referencia de readme.io no
aparece la palabra OAuth ni Bearer (grep sobre las 40 páginas de la referencia).

**OAuth para apps de terceros (portal, código; no documentado).** developers.triplewhale.com se
describe en su `<meta name="description">` como "Build OAuth apps on the Triple Whale API"; la pantalla
de login ofrece "Sign Up" para "developer account" y el bundle expone:
- Rutas `/apps`, `/apps/new`, `/apps/:appId`; alta de app con nombre, App URL, "Privacy policy URL"
  (obligatoria), "Terms of service URL", "Launch URL" ("Where merchants would land if Triple Whale
  links to your app later"), logo y "Registered redirect URIs" ("Must use https:// (http:// only for
  localhost)", "Wildcards are not allowed"); roles Owner/Admin/Member e invitaciones.
- Endpoints (con `Sd = https://api.triplewhale.com/api`): `authorize: ${Sd}/v2/auth/oauth2/auth`
  (`response_type=code&client_id&redirect_uri&scope&state`), `token: ${Sd}/v2/auth/oauth2/token`
  (`grant_type=authorization_code` o `refresh_token`, con `client_id` y `client_secret`,
  `application/x-www-form-urlencoded`), `revoke: ${Sd}/v2/auth/oauth2/revoke`,
  `grantedShops: ${Sd}/v2/developers/oauth2/granted-shops` (con `Authorization: Bearer <access_token>`)
  y `dataInAds: ${Sd}/v2/data-in/ads` (Bearer, cuerpo `{"shop":"<shop_domain>","data":[]}`).
- Scopes (`SupportedScopes`): `ads-metrics:read`, `ads-metrics:write`, `attribution:read`, `moby:read`,
  `ads:write`, `email-sms:write`, más `offline_access` siempre añadido. Textos de consentimiento:
  `attribution:read` = "Send attribution data to <app> from your Triple Whale account";
  `ads-metrics:read` = "Send metrics data to <app> from your Triple Whale account".
- Revisión: "A scope change needs a review before it goes live. Your app stays active on its current
  scopes until Triple Whale approves the change, and a rejection leaves it on what it has today." y
  "Write scopes let your app push data into merchants' Triple Whale accounts, so they get a closer look
  during review." (justificación obligatoria para scopes `:write`).
- También hay una constante `TW_SHOP_ID_HEADER = "x-tw-shop-id"` en código compartido y un host de
  staging `staging.api.triplewhale.com`; su uso en la API pública es **no documentado**.

**"Orchestration" / service accounts**: no aparece nada con ese nombre para la API en ninguna fuente
primaria ("orchestration" solo sale en marketing de Moby). **No documentado.**

## 2. URL base, versionado y formato

| Dato | Valor | Fuente |
|---|---|---|
| Base | `https://api.triplewhale.com/api/v2/` (`servers[0].url` del OpenAPI de cada endpoint) | https://triplewhale.readme.io/reference/get-summary-page-data |
| Formato | REST + JSON; especificación OpenAPI 3.1.0 embebida en cada página (`"openapi": "3.1.0"`, `info.version: "1.0"`); sin GraphQL en ninguna fuente | misma |
| Versionado | Solo el prefijo `/api/v2/`; el endpoint de journeys lleva `-v2` en la ruta (`/attribution/get-orders-with-journeys-v2`); no hay política de versiones escrita (**no documentado**) | https://triplewhale.readme.io/reference/get-customer-journey-attribution-data |
| Índice máquina | "Append .md to any documentation page URL to get its markdown version." + índice en `https://triplewhale.readme.io/llms.txt` | https://triplewhale.readme.io/llms.txt |
| SQL | "SQL editor … (using Clickhouse-flavored SQL)" | https://triplewhale.readme.io/docs/how-data-works-in-triple-whale (2026-01-12) |

## 3. Endpoints

### 3.1 Data-Out (leer)

Todas las rutas cuelgan de `https://api.triplewhale.com/api/v2`.

| Método y ruta | Para qué | Scope | Cuerpo / parámetros | Respuesta | Fuente |
|---|---|---|---|---|---|
| `POST /summary-page/get-data` | "Retrieve data from the Summary Page for a specified time period." | Summary Page: Read | `shopDomain` (string, "the `shop-id` value in your Triple Whale app URL"), `period.start` / `period.end` (ISO 8601, ej. `2023-01-01`), `todayHour` (number, "base-1 (range: 1–25)") — los tres obligatorios | `{ "metrics": [ { "metricName": "revenue", "value": 12345.67 }, { "metricName": "orders", "value": 345 } ] }`; cabeceras `RateLimit-Policy` (ej. `100;w=60`), `RateLimit`; 400 `{success:false,message}`; 429 con `Retry-After` | https://triplewhale.readme.io/reference/get-summary-page-data (2025-03-05) |
| `POST /attribution/get-orders-with-journeys-v2` | "Export full customer journey data, with Triple Pixel attribution, for all customers who placed an order in the specified period." | Pixel Attribution: Read | `shop`, `startDate`, `endDate` (ISO 8601 con offset, ej. `2021-01-01T00:00:00.000-0400`), `page` (1–10000, def. 1), `pageSize` (1–100, def. 50), `excludeJourneyData` (bool) | `totalForRange`, `count`, `startDate`, `endDate`, `page`, `ordersWithJourneys[]` = `{order_id, created_at, order_name, attribution{firstClick[{source, campaignId, adsetId, adId, clickDate}]}, customer_id, total_price, currency, journey[{time, event ∈ {"page loaded","add2c"}, path, productId}]}`, `earliestDate`, `error` | https://triplewhale.readme.io/reference/get-customer-journey-attribution-data (2025-03-05) |
| `POST /orcabase/api/sql` | "Run custom SQL queries for structured data retrieval. The response returns the query results in a JSON format." | "Data Out" (guía de errores) | `shopId`, `query` (con `@startDate` y `@endDate` dentro del SQL), `period.startDate` / `period.endDate` (`YYYY-MM-DD`), `currency` opcional ("Defaults to the currency provided during user account registration") | `{ "success": true, "message": "...", "data": [ {...}, ... ] }` con propiedades dinámicas; 400 `Missing fields: query, startDate, endDate`; 403 `Access token is required`; 429 `Retry-After`; 500 | https://triplewhale.readme.io/reference/data-out-execute-custom-sql-query (2026-01-06) |
| `GET /users/api-keys/me` | "Validate Your Triple Whale API Key" | — | ninguno | 200 (ejemplo documentado: `{}`), 400, 429 | https://triplewhale.readme.io/reference/validate-your-triple-whale-api-key (2025-03-05) |

Notas documentadas del SQL: "Avoid using `SELECT *` in your queries. Our schema is dynamic, and using
wildcard selection can lead to broken or inconsistent results as fields change."; en el SQL Builder de
la app se usan `@start_date`/`@end_date` (snake_case) y en la API `@startDate`/`@endDate`
(camelCase); "Validate SQL in-app first." (readme SQL + guía de errores). Ejemplo de la referencia:
`SELECT SUM(spend) AS spend, channel FROM ads_table a WHERE event_date BETWEEN @startDate AND @endDate GROUP BY channel`.

**Las métricas del Summary**: el esquema solo pone `revenue` y `orders` como ejemplo de `metricName`;
la lista de nombres que devuelve el endpoint es **no documentada** (la KB "Summary Dashboard Metrics
Library" describe métricas de la UI, no claves de API).

### 3.2 (a) Métricas de anuncios de Meta por campaña / conjunto / anuncio, con atribución del Pixel

No hay endpoint dedicado: se consulta por SQL. Las tablas están documentadas en el "Data Dictionary"
de readme.io (una página por tabla, con dimensiones, medidas y derivadas):

| Tabla | Grano | Columnas útiles para Creatv | Fuente |
|---|---|---|---|
| `ads_table` — "channel-reported advertising performance across all connected ad platforms. One row per ad per day." | anuncio × día | Dimensiones: `event_date`, `event_hour`, `account_id`, `campaign_id`, `campaign_name`, `campaign_status`, `adset_id`, `adset_name`, `adset_status`, `ad_id`, `ad_name`, `ad_status`, `channel`, `creative_id`, `video_url`, `destination_url`, `is_utm_valid`, `shop_id`, `breakdown_dimension`/`breakdown_value` ("available for Facebook Ads only"), `actions.*` (one_day_view, seven_day_click, twenty_eight_day_click… con `_value`). Medidas: `spend`, `impressions`, `reach`, `clicks`, `outbound_clicks`, `conversions` ("Number of channel-reported conversions (purchases)"), `conversion_value`, `all_conversions`, `all_conversion_value`, `thruplays`, `three_second_video_view`, `total_video_view`, `video_p25_watched` … `video_p100_watched`, `one_day_click_purchases`, `seven_day_click_purchases`, `twenty_eight_day_click_purchases` (y `_conversion_value`, y las `_view_`), `onsite_*`. Derivadas: `roas`, `cpa`, `cpm`, `ctr`, `cpc`, `cost_per_video_view`. | https://triplewhale.readme.io/docs/ads-table (2026-06-23) |
| `pixel_joined_tvf` — "Pixel-attributed ad performance by channel, campaign, ad set, and ad, combining ad spend with attributed revenue and customer acquisition. One row per ad per day." | anuncio × día × (modelo, ventana) | Dimensiones: las de campaña/conjunto/anuncio + **`model`** ("Possible values: `Total Impact`, `Triple Attribution`, `Triple Attribution + Views`, `Clicks & Views`, `Linear All`, `Linear Paid`, `First Click`, `Last Click`"; "By default `Triple Attribution`"), **`attribution_window`** ("Example values: `1_day`, `7_days`, `14_days`, `28_days`, `lifetime`"; "By default `lifetime`"), `country`, `channel_type`. Medidas: `spend`, `impressions`, `clicks`, `orders_quantity`, `order_revenue`, `new_customer_orders`, `new_customer_order_revenue`, `channel_reported_conversions`, `channel_reported_conversion_value`, `sessions`, `unique_visitors`, `add_to_carts`, `checkouts`, `website_purchases`. Derivadas: `pixel_roas`, `pixel_cpa`, `ncpa`, `new_customer_roas`, `pixel_conversion_rate`, `channel_reported_roas`, `channel_reported_cpa`, `cpc`, `cpm`, `ctr`. Parámetros de la TVF: `use_click_date` ("Uses click date instead of purchase date for `event_date`"), `include_custom_ad_spend`, `country_filter`, `city_filter`, `sales_platform_filter`, `subscription_filter`, `order_tags_filter`, `use_legacy_sessions`. | https://triplewhale.readme.io/docs/pixel-joined-table (2026-07-28) |
| `pixel_orders_table` — "One row per order per attributed ad or channel; orders can have multiple rows under multi-touch attribution" | pedido × touchpoint | `order_id`, `order_name`, `created_at`, `channel`, `campaign_id`, `adset_id`, `ad_id`, `model`, `attribution_window`, `click_date`, `click_ts`, `is_new_customer`, `utm_source`, `utm_medium`, `landing_page`, `triple_id`, `session_id`, `customer_id`; `order_revenue`, `orders_quantity`, `refund_money`. "The Total Impact model and the Clicks & Views model are not supported on the Pixel Orders table". | https://triplewhale.readme.io/docs/pixel-orders-table (2026-07-29) |
| `creatives_table` | creativo | por `ad_id` ("performance by individual creative asset, image, or video") | https://triplewhale.readme.io/docs/creatives-table |

Cómo se elige modelo y ventana en SQL: en los ejemplos del diccionario se filtra por columna, p. ej.
`AND pjt.model = 'Triple Attribution'` (https://triplewhale.readme.io/docs/snapchat-roas y decenas de
páginas de métricas); los parámetros de la TVF van entre paréntesis con `nombre = valor`, p. ej.
`blended_stats_tvf (include_amazon = TRUE)`
(https://triplewhale.readme.io/docs/including-marketplace-data-in-blended-metrics) y
`pixel_joined_tvf () pj` (https://triplewhale.readme.io/docs/sql-example-monthly-pixel-roas-for-selected-channels-bing-facebook-google).
Aviso de la tabla: "`group by attribution_window` and `group by model` may not work on certain complex
queries. The Pixel Joined table functions as a simulated view that dynamically processes data".

Definiciones de Meta en el diccionario (todas sobre `ads_table` con `where channel = 'facebook-ads'`):
"Facebook ROAS = Facebook Ads Conversion Value / Facebook Ad Spend"
(https://triplewhale.readme.io/docs/facebook-roas); "Facebook Conversions (Purchases) represent the
number of purchases on your main shop and your Meta shop, as reported by Facebook" =
`SUM(conversions)` (https://triplewhale.readme.io/docs/facebook-conversions-purchases); "Facebook Ad
Spend … = `SUM(spend)`" (https://triplewhale.readme.io/docs/facebook-ad-spend); "Facebook CV … =
`SUM(conversion_value)`" (https://triplewhale.readme.io/docs/facebook-cv). Canal estandarizado de Meta:
`facebook-ads`; Google `google-ads`; TikTok `tiktok-ads`; Microsoft `bing`; Pinterest `pinterest-ads`;
Snapchat `snapchat-ads`; Twitter `twitter-ads`
(https://triplewhale.readme.io/docs/ads-standardized-channel-ids, 2026-01-08).

Consulta tipo para Creatv (**propuesta nuestra**, armada con los ejemplos documentados; no probada
contra una tienda real):

```sql
SELECT ad_id, adset_id, campaign_id, country, event_date,
       SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks,
       SUM(orders_quantity) AS pixel_orders, SUM(order_revenue) AS pixel_revenue,
       SUM(new_customer_orders) AS pixel_nc_orders
FROM pixel_joined_tvf() pj
WHERE event_date BETWEEN @startDate AND @endDate
  AND channel = 'facebook-ads'
  AND model = 'Last Click' AND attribution_window = '7_days'
GROUP BY ad_id, adset_id, campaign_id, country, event_date
```

ThruPlay no está en `pixel_joined_tvf`: sale de `ads_table.thruplays` (misma llave `ad_id` +
`event_date`; el diccionario documenta el join `Ads` ↔ `Pixel Joined` por `ad_id`).

**Modelos y ventanas de atribución** (KB
https://kb.triplewhale.com/en/articles/5960333-understanding-and-utilizing-attribution-models,
2026-07-26): ventanas "1 Day, 7 Days, 14 Days, 28 Days, Lifetime … The default window is 28 days" (en
la UI; en SQL el default es `lifetime`, ver arriba). Modelos: First Click, Last Click (single touch);
Clicks & Deterministic Views, Linear (All / Paid), Triple Attribution, Triple Attribution + Platform
Views, Total Impact (multi-touch). Reglas que importan para leer números por anuncio:
- Triple Attribution: "each platform receives 100% credit" … "Do not use Triple Attribution for
  financial reporting or total revenue analysis" … "total attributed revenue across all channels will
  exceed actual revenue"; recomendado "1-day click for same-day optimization; 7 days for weekly
  performance review" y "at the channel or campaign level, not the 'All Channels' view".
- Clicks & Deterministic Views: "Clicks update in real time but views refresh daily"; "Allow 24–48
  hours after enabling data to populate".
- Total Impact: "requires … at least 7 days of survey response data. Without PPS data, the model behaves
  similarly to Linear All"; "Date range: 7 days minimum".
- "Neither First Click nor Last Click uses Post-Purchase Survey data."

### 3.3 (b) Resumen de la tienda por día

- Endpoint Summary (§3.1): un periodo → una lista de métricas agregadas, sin desglose por día en el
  esquema (para series diarias hay que llamar por día o usar SQL).
- Por SQL: `blended_stats_tvf` ("`event_date` is a required field … refers to the date of the order")
  con `spend`, `order_revenue`, `orders_count`, `new_customer_orders`, `new_customer_revenue`,
  `refund_money`, `cogs`, `total_costs`, `roas`, `mer`, `ncpa`, `net_profit`, `net_margin`, `poas`,
  `blended_cpa` (https://triplewhale.readme.io/docs/blended-stats-table, 2026-07-29).

### 3.4 (c) Pedidos

- Leer: `orders_table` — "the canonical record of revenue and purchases across all connected sales
  platforms. One row per order." Dimensiones `order_id`, `order_name`, `platform`, `created_at`,
  `customer_id`, `is_new_customer`, `discount_code`, `products_info.*` (product_id, sku, variant_id…),
  `tags`, `shop_timezone`, `source_name`; medidas `order_revenue`, `gross_product_sales`,
  `refund_money`, `taxes`, `shipping_price`, `cost_of_goods`, `discount_amount`
  (https://triplewhale.readme.io/docs/orders-table, 2026-09-16). "Refund amounts (`refund_money`) are
  calculated based on the original order date, not the refund date."
- Pedidos con su journey: endpoint `/attribution/get-orders-with-journeys-v2` (§3.1).
- Escribir (Data-In): `POST /data-in/orders`, `POST /data-in/bulk-orders`, `POST
  /data-in/orders-enrichment` (§3.6).

### 3.5 (d) "Attribution" / "pixel"

- El único endpoint con "attribution" en la ruta es el de journeys (§3.1). Su esquema de `attribution`
  documenta **solo `firstClick`**; ningún otro modelo por pedido está documentado ahí (**no
  documentado**). Para modelo/ventana por pedido: `pixel_orders_table` por SQL (§3.2).
- Pixel hacia dentro: `POST /data-in/event` — "Send offline or server-side Pixel events—such as leads,
  MQLs, SQLs, opportunities, book-a-demo events, or fully custom events—into Triple Whale. Rate limit
  is 1,000 events/min. Max payload is 3 KB."
  (https://triplewhale.readme.io/reference/enrich-pixel-with-offline-events, 2026-02-07).
- Relación pixel ↔ pedido: "Triggering a `purchase` or `NewSubscription` event alone will not initiate
  attribution. Triple Whale must also receive a matching order record … For Shopify and other native
  platforms, the order is received automatically via webhook."
  (https://triplewhale.readme.io/reference/pixel-setup-guide-for-custom-sales-platform).
- Ontología: "Attribution is an explanation layer, not revenue truth. These tables are not canonical
  transactional records and should not be used for finance or ops reconciliation." … "What is my
  ROAS?" → Attribution (modeled) → sanity-check against Store / Business"
  (https://triplewhale.readme.io/docs/triple-whale-data-ontology, 2026-06-02).

### 3.6 (e) Data In / Data Out / Data Warehouse Export

**Data-In API** (todas `POST`, `x-api-key`, cuerpo JSON con `shop`; fuente:
https://triplewhale.readme.io/reference/data-in-api-use-cases, 2026-06-30, y las páginas de cada
endpoint):

| Ruta | Scope | Notas |
|---|---|---|
| `/data-in/orders`, `/data-in/bulk-orders` | Orders: Write | "Re-submit the entire order when updates occur"; `void: true` = borrado lógico (solo Orders) |
| `/data-in/products`, `/data-in/subscriptions`, `/data-in/customers` | Products/Subscriptions/Customers: Write | "No Batch Import Support: Submit each product separately." |
| `/data-in/ads` | Ads: Write | `shop`, `channel` (id estandarizado o custom), `channel_account_id` (def. `CUSTOM_CHANNEL`), `event_date` ("in local timezone", `YYYY-MM-DD`), `currency`, `campaign{id,name,status ∈ PAUSED|ACTIVE}`, `adset{…}`, `ad{…}`, `metrics{clicks, conversions, conversion_value, impressions, spend, visits}`, `ad_image_url`, `updated_at`; "At least one of `campaign`, `adset`, or `ad` is required"; actualizar = reenviar con `shop, channel, channel_account_id, event_date, campaign.id, adset.id, ad.id` iguales (https://triplewhale.readme.io/reference/create-ad-record, 2025-11-12) |
| `/data-in/email-sms`, `/data-in/pps` | — / PPS: Write | email/SMS/correo directo; encuestas post-compra |
| `/data-in/orders-enrichment`, `/data-in/products-enrichment` | Orders: Write / — | solo para plataformas nativas (Shopify, BigCommerce, WooCommerce) |
| `/data-in/event` | — | eventos offline del pixel (1 000/min, 3 KB) |
| `/compliance/requests/create-request` | Compliance: Write | "delete/mask customer PII for a shop using one or more identifiers (emails and/or phone numbers)" |

Límite global: "**Rate Limit:** 25 000 requests **per minute** across all Data-In endpoints"
(https://triplewhale.readme.io/reference/api-setup-guide-for-custom-sales-platform, 2026-03-08).
Latencia: "Data from the past 2 days should appear in about 5 minutes. Older data may take up to 20
minutes to process." Las conexiones creadas por Data-In se ven y se borran ("Hard Delete") en
Integrations › Data In (https://triplewhale.readme.io/reference/managing-data-in-connections). Hay
plantilla de Google Sheets para subir ads (https://triplewhale.readme.io/reference/google-sheets-data-in-template).

**Data-Out API**: los tres endpoints de §3.1 ("Custom SQL Queries", "Customer Journey Attribution",
"Summary Page Metrics", https://triplewhale.readme.io/reference/data-out-api-use-cases, 2026-08-31).

**Data Warehouse Export** (no es API: se configura en la app): "export data directly into your
BigQuery, Snowflake, AWS S3, or Google Cloud Storage warehouse—either as a one-time export or on a
recurring schedule" definida por SQL; "Each export run appends new data rows; existing data is not
replaced"; sin deduplicación ("Users need to implement deduplication strategies"); frecuencia "hourly,
daily, weekly". Comparativa oficial: Custom SQL API "Slower for large exports; limited by rate and
response size" vs. Export "No limits on data size"
(https://triplewhale.readme.io/reference/introduction-to-data-warehouse-export, 2026-07-09). Es un
add-on de pago aparte ("Data Warehouse Sync is a separate add-on … Enterprise customers must also have
the appropriate Data Warehouse Sync entitlement", §5).

### 3.7 (f) TikTok y Google

Van por las mismas tablas (`channel = 'tiktok-ads'` / `'google-ads'`) y por Data-In si hiciera falta.
Conexión en la KB: Meta "When you click Connect, you'll be redirected to Meta. Make sure you're already
logged into Meta using an account that has access to the Meta Ads Manager account … You can connect up
to 20 ad accounts." y al volver "prompted to select the Attribution Window that your Meta account
currently uses" (https://kb.triplewhale.com/en/articles/9507673-meta-ads-integration, 2026-07-26);
Google "an account that has admin privileges to the Google Ads account … (An MCC account is also
acceptable.)" y "we will automatically begin adding tracking parameters to all your Google campaigns
and adgroups" (https://kb.triplewhale.com/en/articles/9507702-google-ads-integration); TikTok "an
account that has access to the TikTok Ads Manager account … Check all the boxes" + permisos Smart+
(https://kb.triplewhale.com/en/articles/9516097-tiktok-ads-integration). En los tres, "Triple
Attribution + Views" trae las view-through conversions "By connecting directly to <plataforma>'s API".

## 4. Rangos de fecha, zona horaria, granularidad, paginación y límites

| Tema | Lo documentado | Fuente |
|---|---|---|
| Fechas Summary | `period.start`/`end` "ISO 8601" (ejemplos `2023-01-01`); `todayHour` "base-1 (range: 1–25)" | readme get-summary-page-data |
| Fechas journeys | `startDate`/`endDate` "date or timestamp … ISO 8601" con offset (`-0400` en el ejemplo) | readme get-customer-journey-attribution-data |
| Fechas SQL | `period.startDate`/`endDate` `format: date`; "Use `YYYY-MM-DD`, and confirm `startDate` is on or before `endDate`" | readme SQL + guía de errores |
| Zona horaria | Tablas: "`event_date` … Based on the shop time zone at the moment of the event (or the user time zone, if no sales platform is connected)"; `event_hour` idem; `orders_table.shop_timezone` ("according to the timezone database"). Data-In: `event_date` "in local timezone"; timestamps "ISO 8601 format, with explicit timezone information (`Z` or `+/-HH:mm` offset)". Zona de los endpoints Summary/journeys: **no documentada** | https://triplewhale.readme.io/docs/ads-table; https://triplewhale.readme.io/docs/orders-table; readme create-ad-record |
| Granularidad | Día (`event_date`) y hora (`event_hour`, "24-hour clock") en `ads_table`, `pixel_joined_tvf`, `orders_table`; derivadas `event_date.week` (domingo), `.month`, `.quarter`, `.year` | mismas |
| Paginación | Solo el endpoint de journeys: `page` 1–10000, `pageSize` 1–100 (def. 50), `totalForRange`, `earliestDate`. Summary y SQL: sin paginación documentada | readme get-customer-journey-attribution-data |
| Rate limits | SQL: "100 requests per second" y "600 requests per minute" → 429. Summary, journeys, validate: cabeceras `RateLimit-Policy` "`{quota};w={window}`" (ejemplo `100;w=60`) y `RateLimit`; el valor real "varies by endpoint — refer to the specific endpoint's API reference page for its quota" (en esas páginas solo consta el ejemplo). Data-In: 25 000 req/min; `/data-in/event`: 1 000 eventos/min | readme SQL; guía de errores; api-setup-guide; enrich-pixel |
| Reintentos | "Every `429` response includes a `Retry-After` response header (in seconds)"; "Add backoff … Break up large jobs. Split wide date ranges into smaller chunks"; Data-In: "Retry 3 times on timeout (`5xx`) or `429` … exponential back-off (e.g., 2s, 4s, 8s)"; backfill "about 5 requests/second" | guía de errores; api-setup-guide |
| Tamaños | `/data-in/event` "Max payload is 3 KB". Filas o bytes máximos por respuesta SQL/Summary/journeys: **no documentado** ("limited by rate and response size", sin cifra) | enrich-pixel; DWH intro |
| Historia disponible | "the platform will pull historical data up to the limit allowed by the specific channel's API … some channels may provide access to a full year's worth of data, while others might limit access to only a few months" (integraciones). Cuánto atrás se puede consultar por API: **no documentado** | https://kb.triplewhale.com/en/articles/9591899-will-my-historical-data-backfill (2026-07-26) |
| Frescura de Meta | Reconexión: "it may take 30–60 minutes for your data to fully reimport" (Meta), "about 30–40 minutes" (Google). Cadencia de sincronización normal de Meta: **no documentada**. Vistas (C&DV): "views refresh daily" | KB Meta/Google; KB modelos |
| Moneda | SQL `currency` (def. la de registro de la cuenta); `ads_table.currency` y `currency_rate`; pedidos `currency` | readme SQL; readme ads-table |

## 5. Planes, costo y estado de la API

- **Tabla comparativa de precios** (https://www.triplewhale.com/pricing, leída el 2026-09-21; columnas
  "Free · Get started for free", "Foundation · Book a walkthrough", "Automate · Book a walkthrough",
  "Enterprise · Contact sales"; los iconos son SVG con clase `tw-cmp-ic-check` / `tw-cmp-ic-minus`):

| Fila | Free | Foundation | Automate | Enterprise | Tooltip |
|---|---|---|---|---|---|
| Data-In API | ✓ | ✓ | ✓ | ✓ | "Connect any data source or platform to Triple Whale — ingest ads, orders, subscriptions, products, post- purchase survey data, and more." |
| Data-Out API | ✓ | ✓ | ✓ | ✓ | "Sync your Triple Whale data outbound at scale via API — for your warehouse, BI tool, or internal app." |
| SQL Editor | — | ✓ | ✓ | ✓ | "Access and query your raw data directly with a SQL interface." |
| CSV Export | — | ✓ | ✓ | ✓ | |
| Data Warehouse Export | — | Add on | Add on | Add on | "Easily export Triple Whale data to BigQuery, Snowflake, Redshift, and more." |

- **Referencia**: "All paid Triple Whale plans include access to the API endpoints they are entitled
  to. A `403` is almost always about the request payload, not account permissions." (guía de errores,
  2026-08-31). La KB de llaves (más vieja) empieza con "For customers with access to the Triple Whale
  API" (8116412). Qué endpoints están "entitled" en cada plan: **no documentado**.
- **KB de planes** (https://kb.triplewhale.com/en/articles/16046642-understanding-triple-whale-plans-foundation-automate-and-enterprise,
  2026-08-12): tres planes de pago, Foundation / Automate / Enterprise; "The plans, add-ons, included
  Moby usage, and pricing available to your business may vary based on annual gross merchandise value
  (GMV), contract, and account configuration."; "Triple Whale MCP access should not be treated as native
  API, headless-platform, or custom integration access. Those are separate capabilities and may require
  different products, permissions, or agreements."; Enterprise incluye "Custom integrations" y "uses
  custom pricing" ("generally designed for businesses with at least $10 million in annual GMV. This is a
  recommendation rather than a strict eligibility requirement"); "Data Warehouse Sync may be available
  as an add-on across Foundation, Automate, and Enterprise" y "is not automatically included with
  Enterprise". Los nombres Founders/Growth/Pro no aparecen en ninguna fuente vigente; la KB solo dice
  "Some existing customers may still see earlier plan names".
- **Costo aparte, beta o solicitud** para la API con llave: nada escrito (**no documentado**). La
  página comercial https://www.triplewhale.com/api aún muestra "Apply Now" (Summary Page API) y "Coming
  Soon" (enriquecer journeys con eventos custom) — es marketing antiguo y contradice a la referencia,
  que ya documenta `/data-in/event`. El **portal OAuth** exige "developer account" y revisión de scopes
  (portal, código; §1).

## 6. SDKs oficiales y webhooks

- **SDK de servidor (Node/Python)**: ninguno documentado. La referencia trae ejemplos con `curl` y
  Python `requests` (https://triplewhale.readme.io/reference/api-setup-guide-for-custom-sales-platform;
  https://triplewhale.readme.io/reference/sample-automation-submit-deletion-requests-from-a-csv-python).
  El snippet `new SummaryApi({token:"your-token"})` de https://www.triplewhale.com/api es ilustrativo:
  no hay paquete publicado ni enlazado.
- **Triple Pixel Mobile SDK** (para emitir eventos del pixel desde apps, no para leer métricas):
  Android `com.triplewhale.pixel:shared` (Maven Central), iOS `TriplePixelSDK` (SPM,
  github.com/Triple-Whale/triple-pixel-sdk-spm), React Native `@triplewhale/react-native-triple-pixel`
  (npm); "Current SDK version: **0.2.0**"; MIT; "Until version 1.0.0, minor releases may contain
  breaking changes." (https://triplewhale.readme.io/reference/intro-to-the-triple-pixel-mobile-sdk,
  2026-09-06).
- **Webhooks / eventos de salida**: ninguno documentado. La única mención de "webhook" en toda la
  referencia es la entrada de pedidos de Shopify hacia Triple Whale (§3.5). Lo más parecido a "push"
  es Data Warehouse Export programado (§3.6).
- **MCP**: servidor `https://mcp.triplewhale.com/v1/mcp`, OAuth2 `moby:read` (recomendado) o llave
  "MCP: Read" con `x-api-key` vía `npx mcp-remote`; "read-only … it does not mutate or act on anything"
  (KB 15656798). Incluido en Foundation, Automate y Enterprise.

## 7. Identificación de la tienda y listado de tiendas

- El identificador es el dominio que aparece en la URL de la app: "This is the `shop-id` value in your
  Triple Whale app URL (for example `?shop-id=example.myshopify.com`)" (todas las páginas de endpoint).
  El nombre del campo cambia por endpoint: "`shopId` for the SQL endpoint, `shop` for the Customer
  Journey Attribution endpoint and all Data-In endpoints, and `shopDomain` for the Summary Page
  endpoint" (guía de errores). Formato: "a plain string (e.g. `"example.myshopify.com"`). No leading or
  trailing slashes, no URL wrapping." Para tiendas custom es el dominio propio ("Store Domain – e.g.
  `example.myshop.com`", api-setup-guide).
- En SQL las tablas llevan `shop_id` ("often corresponds to the shop domain … Can be used to group or
  filter data by shop in multi-store reports. Example values: `example-US.myshopify.com`,
  `example-EU.myshopify.com`") y `shop_name` (readme pixel-joined-table). Las cuentas publicitarias de
  Meta van en `account_id` / `account_name` de `ads_table` ("You can connect up to 20 Meta ad accounts
  to a single Triple Whale account", KB Meta).
- **Listar las tiendas a las que una llave tiene acceso**: **no documentado**. `GET
  /users/api-keys/me` solo valida (esquema de respuesta: objeto sin campos, ejemplo `{}`). Para apps
  OAuth existe `GET /api/v2/developers/oauth2/granted-shops` con Bearer (portal, código; §1).

## 8. Restricciones de uso

- **No hay términos de API ni de desarrollador públicos**: la búsqueda en triplewhale.com, la KB y
  readme.io no devuelve ninguno (**no documentado**). El formulario de alta del portal enlaza los
  términos del sitio y el aviso de privacidad (`https://www.triplewhale.com/pages/terms-of-service`,
  `https://www.triplewhale.com/pages/privacy-notice`; portal, código).
- **Website Terms of Service** (https://www.triplewhale.com/pages/terms-of-service): rigen el sitio y
  remiten a un contrato aparte para clientes — "you may also be required to execute a separate sales
  contract or similar agreement that contains customer-specific terms and conditions ("Customer Terms
  and Conditions") … To the extent any of the Customer Terms and Conditions differ or conflict with the
  terms of this Agreement, the terms in the Customer Terms and Conditions will prevail." Ese contrato
  de cliente no es público. Cláusulas que tocan a un integrador:
  - Prohibido "engaging in any automated or non-automated "scraping" on the Site" y "using any
    automated system, including without limitation "robots," "spiders," "offline readers," etc., to
    access the Site in a manner that sends more request messages to the Triple Whale servers than a
    human can reasonably produce" (habla del **Site**, no de la API).
  - Prohibido "reverse engineering, disassembling, decompiling, decoding, adapting, or otherwise
    attempting to derive or gain access to any software component of the Site".
  - "Triple Whale Content … are the exclusive property of Triple Whale and its licensors … you agree not
    to sell, license, rent, modify, distribute, copy, reproduce, transmit, publicly display …" (marca y
    contenido; no dice nada específico de datos obtenidos por API → reventa de datos **no documentada**).
  - Sobre datos del cliente: "Triple Whale creates derivatives of the User Content you Share with us for
    our own business purposes, including without limitation by aggregating data from multiple Users …
    training machine learning algorithms" con "commercially reasonable efforts to ensure that any
    derivatives … cannot reasonably be used to identify the User".
  - Límite de responsabilidad: "IN NO EVENT SHALL TRIPLE WHALE … BE LIABLE TO YOU … IN AN AMOUNT
    EXCEEDING $200."; arbitraje individual y ley de Ohio.
- **Datos personales**: la API expone `customer_email`, `customer_first_name`, teléfonos, etc. en
  `orders_table`/`pixel_orders_table`/journeys; existe el endpoint de cumplimiento para borrar PII por
  email/teléfono (§3.6) y la KB "How to submit a Data Subject Deletion Request"
  (https://kb.triplewhale.com/en/articles/11961967-how-to-submit-a-data-subject-deletion-request).
- **Llaves**: "You should not share your API key publicly or place it anywhere your team does not
  control." (KB 8116412).

## 9. Qué implica para Creatv

**Qué usar (y para qué).**

| Necesidad de Creatv hoy | Con Triple Whale | Cómo |
|---|---|---|
| Insights por anuncio de Meta (spend, impressions, clicks, thruplay, purchases, revenue, ROAS/CPA) | `ads_table` (mismos números "channel-reported" que la Marketing API, ya con ventanas 1/7/28 días en `actions.*` y `*_click_purchases`) | `POST /orcabase/api/sql`, `WHERE channel = 'facebook-ads' AND event_date BETWEEN @startDate AND @endDate GROUP BY ad_id, event_date` |
| Compras/ingresos **atribuidos por el Pixel** por anuncio, con modelo y ventana | `pixel_joined_tvf` (+ `pixel_orders_table` si hace falta pedido a pedido) | mismo endpoint, filtrando `model` y `attribution_window` |
| Atribución por país (los experimentos son un adset por país) | `pixel_joined_tvf.country` / `country_filter` | agrupar por `country` además de `ad_id` |
| Pedidos e ingresos "verdad" para el tablero | `orders_table` / `blended_stats_tvf` | SQL por día |
| KPIs de tienda de un vistazo | `POST /summary-page/get-data` | solo si se descubren los `metricName` con una llave real (no documentados) |

**Cómo encaja con los snapshots.** Meta devuelve totales acumulados por anuncio y `tablero` resta
snapshots; Triple Whale devuelve **una fila por anuncio y día** (y por modelo/ventana). Lo natural es
no forzar acumulados: guardar filas diarias `(cliente, experimento_pieza, ad_id, event_date, modelo,
ventana, spend, impressions, clicks, thruplays, purchases, revenue, nc_orders)` en una tabla nueva (o
`metrica_snapshot` con `fuente='triple_whale'` y el acumulado calculado al insertar, para que
`valor_en(hasta) − valor_en(desde)` siga valiendo). Un periodo se recalcula reconsultando el rango:
Triple Whale no garantiza que un día viejo no cambie (los pedidos se reatribuyen al llegar; las vistas
"refresh daily"), así que conviene re-pedir los últimos N días en cada corrida, no solo el día actual.

**Qué guardar por proyecto (`clientes/<cliente>/`).**
- La **llave** `x-api-key` del cliente (o de Creatv si el cliente invita a un usuario de Creatv a su
  workspace), cifrada con Fernet como `tienda.credenciales`, nunca en logs/flash/eventos; scopes
  mínimos: "Data Out" (SQL) y, si se usan, "Summary Page: Read" y "Pixel Attribution: Read". Recordar
  que muere si ese usuario pierde acceso al workspace: tratar 401 como "reconectar Triple Whale", no
  como error de datos.
- El **dominio de la tienda** (`shop-id`), la **moneda** que devuelve TW (pasar `currency` explícito
  igual a la de la cuenta publicitaria para que `tablero` no mezcle monedas), el **modelo y la
  ventana** elegidos (default TW en SQL: Triple Attribution + lifetime; el decisor debería fijar algo
  como Last Click 7 días o Linear Paid 7 días y guardarlo en `proyecto.json`), y la **zona horaria de
  la tienda** (`shop_timezone`), que puede no coincidir con la de la cuenta de Meta.
- En `experimentos`, una **atribución `triple_whale`** junto a `pixel` / `tienda` / `ninguna`, con la
  misma lógica que hoy usa `lanzador.refrescar` para sobrescribir compras/ingresos/CPA desde la tienda.

**Condición previa en los anuncios que Creatv crea.** TW atribuye por parámetros de URL:
"REQUIRED TRACKING PARAMETERS: `tw_source={{site_source_name}}&tw_adid={{ad.id}}`" en "URL
Parameters" (o `utm_source=facebook` + `fbadid={{ad.id}}`); "Tracking will only begin once UTMs are
correctly implemented and cannot retroactively apply to past ad activity."; sin ellos "Spend Data" y
"Engagement Metrics like clicks and impressions" siguen llegando pero "attribution accuracy may suffer
significantly" (KB Meta). `lanzador.url_destino` ya pone `utm_content = experimento_pieza.id`; habría
que añadir `tw_source`/`tw_adid` a los parámetros de URL del creativo (nota nuestra: en la Marketing
API es `url_tags`) sin romper la atribución por tienda. Cambiar los parámetros de un anuncio activo lo
manda a "processing" ("can take up to 1 hour and will pause spend") — hacerlo al crear, no después.

**Riesgos.**
1. Entitlement ambiguo: precios dicen API en Free, la referencia "all paid plans", la KB "may require
   different products, permissions, or agreements". Confirmar con la llave real del piloto antes de
   diseñar más (llamar `GET /users/api-keys/me` y una consulta SQL mínima).
2. "Our schema is dynamic": nombrar columnas siempre; versionar las consultas en código y tener una
   prueba que las valide contra una tienda de prueba.
3. `group by model` / `attribution_window` "may not work on certain complex queries": filtrar por un
   modelo y una ventana por consulta.
4. Sin webhooks: la periódica `exp_refrescar_todos` (2 h) tendría que pedir el rango completo de cada
   experimento; con 600 req/min sobra, pero hay que respetar `Retry-After` y partir rangos largos.
5. Frescura no documentada de la sincronización Meta → TW y "views refresh daily": el decisor no debe
   leer "hoy" como completo; mejor cerrar decisiones sobre días completos.
6. Triple Attribution duplica ingresos entre plataformas: para comparar piezas de Meta entre sí sirve;
   para totales de tablero usar Linear/Total Impact/C&DV o `orders_table`.
7. Multi-tenant: una llave por proyecto (modo "propia"). El modelo "agencia" equivalente sería una
   **app OAuth** de Creatv con `attribution:read`/`ads-metrics:read` y consentimiento por comerciante,
   pero hoy es un portal sin documentación pública y con revisión manual: no diseñar sobre él todavía.
8. PII en las tablas de pedidos: no traer `customer_email`/teléfonos a Creatv; seleccionar solo
   columnas agregadas.

## 10. Lo que NO pude confirmar

1. Qué endpoints vienen con cada plan (Free vs. pago) y si el SQL de Data-Out exige tener el "SQL
   Editor" del plan; el nombre exacto del scope del endpoint SQL ("Data Out" según la guía de
   errores; ausente en la página de llaves).
2. Los `metricName` que devuelve `/summary-page/get-data` y su zona horaria; el sentido de `todayHour`
   "1–25".
3. Tamaño máximo de respuesta / filas del SQL y de Summary; cuánta historia se puede consultar.
4. Cadencia normal de sincronización de Meta → Triple Whale (solo consta el reimport de 30–60 min al
   reconectar y "views refresh daily").
5. La sintaxis oficial para pasar `model`/`attribution_window` a `pixel_joined_tvf` (los ejemplos
   filtran por columna; no hay ejemplo con parámetros de atribución entre paréntesis).
6. Si `attribution` del endpoint de journeys expone más que `firstClick` (el esquema solo documenta
   ese).
7. Todo lo del portal OAuth (endpoints `/v2/auth/oauth2/*`, scopes `ads-metrics:read`, etc.): solo
   está en el código del portal; no hay documentación, plazos de revisión ni requisitos publicados.
8. Términos de uso de la API (reventa de datos, marca): solo existen los ToS del sitio y un "Customer
   Terms and Conditions" no público.
9. Cómo listar las tiendas accesibles con una llave (`/users/api-keys/me` devuelve `{}` en el ejemplo).
10. Un endpoint dedicado de métricas por anuncio con atribución: no existe en la referencia; todo pasa
    por SQL.

## Fuentes (consultadas el 2026-09-21)

Portal de desarrolladores
- https://developers.triplewhale.com/ — login; `<meta name="description" content="Build OAuth apps on the Triple Whale API">`; bundle público `https://developers.triplewhale.com/assets/index-DRabXQfu.js` (endpoints OAuth, scopes, textos de revisión).

Referencia oficial (readme.io; `updatedAt` entre paréntesis)
- https://triplewhale.readme.io/ y https://triplewhale.readme.io/llms.txt
- https://triplewhale.readme.io/reference/introduction-to-the-triple-whale-api (2026-08-31)
- https://triplewhale.readme.io/reference/creating-and-managing-triple-whale-api-keys (2026-06-18)
- https://triplewhale.readme.io/reference/validate-your-triple-whale-api-key (2025-03-05)
- https://triplewhale.readme.io/reference/data-out-api-use-cases (2026-08-31)
- https://triplewhale.readme.io/reference/get-summary-page-data (2025-03-05)
- https://triplewhale.readme.io/reference/get-customer-journey-attribution-data (2025-03-05)
- https://triplewhale.readme.io/reference/data-out-execute-custom-sql-query (2026-01-06)
- https://triplewhale.readme.io/reference/troubleshooting-common-triple-whale-api-errors (2026-08-31)
- https://triplewhale.readme.io/reference/data-in-api-use-cases (2026-06-30)
- https://triplewhale.readme.io/reference/api-setup-guide-for-custom-sales-platform (2026-03-08)
- https://triplewhale.readme.io/reference/custom-sales-platform-setup-overview (2025-07-20)
- https://triplewhale.readme.io/reference/pixel-setup-guide-for-custom-sales-platform
- https://triplewhale.readme.io/reference/create-ad-record (2025-11-12)
- https://triplewhale.readme.io/reference/enrich-pixel-with-offline-events (2026-02-07)
- https://triplewhale.readme.io/reference/managing-data-in-connections (2025-11-26)
- https://triplewhale.readme.io/reference/google-sheets-data-in-template
- https://triplewhale.readme.io/reference/sample-automation-submit-deletion-requests-from-a-csv-python
- https://triplewhale.readme.io/reference/introduction-to-data-warehouse-export (2026-07-09)
- https://triplewhale.readme.io/reference/intro-to-the-triple-pixel-mobile-sdk (2026-09-06)
- https://triplewhale.readme.io/docs/how-data-works-in-triple-whale (2026-01-12)
- https://triplewhale.readme.io/docs/triple-whale-data-ontology (2026-06-02)
- https://triplewhale.readme.io/docs/ads-table (2026-06-23)
- https://triplewhale.readme.io/docs/pixel-joined-table (2026-07-28)
- https://triplewhale.readme.io/docs/pixel-orders-table (2026-07-29)
- https://triplewhale.readme.io/docs/orders-table (2026-09-16)
- https://triplewhale.readme.io/docs/blended-stats-table (2026-07-29)
- https://triplewhale.readme.io/docs/customer-journey-table
- https://triplewhale.readme.io/docs/creatives-table
- https://triplewhale.readme.io/docs/ads-standardized-channel-ids (2026-01-08)
- https://triplewhale.readme.io/docs/including-marketplace-data-in-blended-metrics
- https://triplewhale.readme.io/docs/sql-example-library-overview-and-best-practices (2025-08-04)
- https://triplewhale.readme.io/docs/sql-example-monthly-pixel-roas-for-selected-channels-bing-facebook-google
- https://triplewhale.readme.io/docs/sql-example-weekly-performance-metrics-roas-ctr-cvr
- https://triplewhale.readme.io/docs/facebook-roas, …/docs/facebook-conversions-purchases, …/docs/facebook-ad-spend, …/docs/facebook-cv (2025-01-29)
- https://triplewhale.readme.io/docs/snapchat-roas (ejemplo de `model = 'Triple Attribution'`)

Knowledge Base
- https://kb.triplewhale.com/en/articles/8116412-creating-and-managing-api-keys (2026-07-26)
- https://kb.triplewhale.com/en/collections/19642502-apis
- https://kb.triplewhale.com/en/collections/19645572-data
- https://kb.triplewhale.com/en/articles/10371684-understanding-triple-whale-s-data-in-feature (2026-07-26)
- https://kb.triplewhale.com/en/articles/16046642-understanding-triple-whale-plans-foundation-automate-and-enterprise (2026-08-12)
- https://kb.triplewhale.com/en/collections/19642545-plans-and-payment
- https://kb.triplewhale.com/en/articles/15656798-triple-whale-mcp (2026-08-20)
- https://kb.triplewhale.com/en/articles/5960333-understanding-and-utilizing-attribution-models (2026-07-26)
- https://kb.triplewhale.com/en/articles/9591899-will-my-historical-data-backfill (2026-07-26)
- https://kb.triplewhale.com/en/articles/9507673-meta-ads-integration (2026-07-26)
- https://kb.triplewhale.com/en/articles/9507702-google-ads-integration
- https://kb.triplewhale.com/en/articles/9516097-tiktok-ads-integration
- https://kb.triplewhale.com/en/articles/9579777-how-accurate-is-triple-whale-s-data (2026-07-26)
- https://kb.triplewhale.com/en/articles/11961967-how-to-submit-a-data-subject-deletion-request
- https://kb.triplewhale.com/en/articles/6855429-attribution-dashboard-metrics-library — devolvió "THAT PAGE DOESN'T EXIST" el 2026-09-21

triplewhale.com
- https://www.triplewhale.com/pricing (tabla comparativa y add-ons)
- https://www.triplewhale.com/api (página comercial "Summary Page API" / "Attribution API")
- https://www.triplewhale.com/pages/terms-of-service

No se usó ninguna fuente secundaria (blogs, resúmenes de terceros).
