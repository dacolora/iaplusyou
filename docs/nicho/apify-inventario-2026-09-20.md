# Inventario de actores de Apify Store — buscar productos por keyword y traer reseñas/comentarios

Investigación de solo lectura, hecha el 2026-09-20 vía WebSearch/WebFetch sobre apify.com. No se creó cuenta, no se ejecutó ningún actor, no se gastó nada. Todos los precios/estadísticas son los que mostraba la página en la fecha indicada y pueden cambiar. Donde un dato no aparecía en la página fuente, se escribió "no visible" en vez de inventarlo.

Leyenda de modelo de precio: **PPR** = pay per result (precio fijo por ítem del dataset). **PPE** = pay per event (precio fijo por evento definido por el desarrollador — puede incluir un cargo por arranque de run + un cargo por ítem). **Rental** = cuota mensual + uso de plataforma. **Uso de plataforma** = sin precio fijo, se cobra el cómputo/proxy de Apify.

---

## 1. Amazon

### 1a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave | Mercados no-US |
|---|---|---|---|---|---|---|
| `clearrun/amazon-products` | Busca en Amazon por término y devuelve cada producto de la página de resultados (precio, rating, badges) | PPE, **$2.00 / 1,000 productos** | 1 usuario total, 1 mensual, 100% runs OK, sin rating | `queries` (array de términos), `asins`, `productUrls`, `marketplace` (com, co.uk, de, fr, it, **es**, ca, com.au, in, co.jp, **com.mx**, nl, **se**, pl), `maxResultsPerQuery`, `sortBy`, `minPrice`/`maxPrice`, `primeOnly` | `asin`, `title`, `brand`, `price`, `currency`, `rating`, `reviewCount`, `isPrime`, `isSponsored`, `isBestSeller`, `availability`, `seller`, `images` | Sí — 14 marketplaces, incluye explícitamente `es`, `se` y `com.mx` (los ejemplos pedidos) |
| `scrapecrafter/amazon-search-scraper` | Scrapea resultados de búsqueda de Amazon (ASIN, precio, rating, sponsored) | PPE, **$0.99 / 1,000 resultados** | 2 usuarios, 1 mensual, 100% OK, sin rating | `queries` (array), `marketplace` (dominio Amazon), `maxPages`, `maxResults`, `sort`, `excludeSponsored`, `deduplicate` | `results` (array de productos), `runSummary` | Sí — acepta cualquier dominio Amazon vía `marketplace`, sin lista cerrada visible |
| `junglee/amazon-crawler` | El scraper de Amazon más usado del store: categorías/productos/búsquedas por URL, precios, reviews agregadas, ASINs | PPE, **$3.00 / 1,000 resultados** | **23,282 usuarios totales, 1,989 mensuales, 91.3% runs OK, 4.16/5** | `categoryOrProductUrls` (⚠️ requiere URL completa, ej. `.../s?k=teclado`, **no** admite un string de keyword suelto), `maxItemsPerStartUrl`, `proxyCountry`, `maxSearchPagesPerStartUrl`, `maxOffers`, `scrapeSellers` | `title`, `asin`, `price`, `brand`, stock, `stars`, `reviewsCount`, seller, `images` | Sí — cambia de dominio en la URL (ej. `amazon.de`); `proxyCountry` ajustable; no se vio lista cerrada de dominios soportados |

Fuentes: https://apify.com/clearrun/amazon-products , https://apify.com/scrapecrafter/amazon-search-scraper , https://apify.com/junglee/amazon-crawler , https://apify.com/junglee/amazon-crawler/input-schema

Nota: `getanyapi/amazon-product-scraper` (https://apify.com/getanyapi/amazon-product-scraper) aparecía en la búsqueda como "Pay Per Result $5.00/1K" pero su único input es `url` (una URL de producto) — es un scraper de **detalle de producto**, no de búsqueda por keyword, así que no calificó para esta lista.

### 1b. Reseñas de compradores (por URL de producto/ASIN)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) | Mercados no-US |
|---|---|---|---|---|---|---|
| `junglee/amazon-reviews-scraper` | Extrae reseñas de un producto Amazon (rating, texto, imágenes, verificado) | PPE, **$3.00 / 1,000 reviews** | **13,644 usuarios, 1,638 mensuales, 99.0% OK, 3.92/5** | `productUrls` (array de URLs, no acepta keyword de búsqueda de producto), `maxReviews`, `filterByRatings`, `reviewsFilterByKeywords` (filtra el *texto* de la reseña, no busca productos), `sort`, `reviewsCutoffDate`, `includeGdprSensitive` | `ratingScore`, `reviewTitle`, `reviewDescription`, `productAsin`, `reviewUrl`, `reviewReaction`, `reviewedIn`, `isVerified`, `variant`, `reviewImages`, `position` | Solo se documentó `amazon.com`; sin mención explícita de otros dominios en esta página (ver pregunta (b) más abajo para detalle) |
| `axesso_data/amazon-reviews-scraper` | Reseñas de Amazon en tiempo real (rating, título, imágenes) | PPE, **$0.90 / 1,000 reviews** | 5,785 usuarios, 412 mensuales, 100% OK, 4.22/5 | `asin` (requerido), `domainCode` (requerido), `maxPages` (máx 10), `sortBy`, `filterByStar`, `filterByKeyword`, `reviewerType` | `text`, `rating`, `date`, `reviewId`, `userName`, `numberOfHelpful`, `variationId`, `verified`, `imageUrlList`, `videoUrlList` | Sí — 15 marketplaces: US, UK, DE, JP, AU, BR, CA, FR, IN, IT, ES, NL, SE, MX, AE |
| `apivault_labs/amazon-reviews-scraper` | Reseñas públicas de Amazon con verified-purchase y resumen de keywords | PPE, **$3.00 / 1,000 reviews** + $0.00005 por arranque de run | 34 usuarios, 7 mensuales, 100% OK, sin rating | `asins` (hasta 25 ASINs o URLs), `domain`, `maxResults` (1–100), `maxPages` (1–5), `sortBy`, `filterByStar`, `outputPreset` | `reviewId`, `text`, `ratingValue`, `date`, `asin`, `reviewerName`, `verifiedPurchaseValue`, `productVariant` | Sí — 12 marketplaces: US, UK, DE, FR, IT, ES, CA, AU, JP, IN, MX, BR |

Fuentes: https://apify.com/junglee/amazon-reviews-scraper , https://apify.com/junglee/amazon-reviews-scraper/input-schema , https://apify.com/junglee/amazon-reviews-scraper/pricing , https://apify.com/axesso_data/amazon-reviews-scraper , https://apify.com/apivault_labs/amazon-reviews-scraper

---

## 2. Walmart

### 2a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave | No-US |
|---|---|---|---|---|---|---|
| `devcake/walmart-product-scraper` | Extrae productos de Walmart (precio, stock, sellers, rating, UPC, variantes) | PPE, **$1.00 / 1,000 resultados** (solo se cobran productos guardados/enriquecidos) | 2 usuarios, 0 mensuales, 93.4% OK, sin rating | `targets` (nombres de producto, item IDs o URLs, 1–50), `maxResults` (def. 10, máx 500), `sort`, `includeDetails` | `id`, `name`, `url`, `price`, `availability`, `brand`, rating, `reviewCount`, seller, `images`, specs, UPC | **No** — página indica explícitamente que solo cubre EE.UU., no Walmart Canadá/México |
| `s-r/walmart-scraper` | Scrapea productos Walmart con título, rating, reviews, disponibilidad, sin browser ni CAPTCHA | PPE: `run_start` $0.0010/run, `product` $0.0010 c/u ($1.00/1,000), `product_detail` $0.0030 c/u (solo si se piden precios) | 1 usuario, 0 mensuales, 100% OK, sin rating | `query` (término de búsqueda), `url`, `fetch_prices`, `limit` (1–600), `retries` | `position`, `item_id`, `url`, `title`, `rating`, `reviews_count`, `availability`, `price`, `was_price`, `currency` | No — "US only" según la página |

Fuentes: https://apify.com/devcake/walmart-product-scraper , https://apify.com/s-r/walmart-scraper

### 2b. Reseñas de compradores

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `apt_marble/walmart-reviews-scraper` | Reseñas de Walmart: texto, rating, autor, fecha, votos útiles | PPE: reviews $0.001 c/u ($1.00/1,000); resumen de producto $0.002 c/u | 3 usuarios, 2 mensuales, 100% OK, sin rating | `products` (links o item IDs), `sort`, `maxReviewsPerProduct` (máx 2,000), `includeProductSummary`, `maxConcurrency` | `reviewId`, `productId`, `rating`, `text`, `author`, `date`, `helpfulVotes`, `verifiedPurchase` |
| `good-apis/walmart-reviews` | Reseñas de producto Walmart sin login ni proxy propio | **PPR, $0.80 / 1,000 reviews** (gratis si el producto tiene 0 reviews) | 2 usuarios, 1 mensual, 100% OK, sin rating | `item_id`, `url`, `max_reviews` (def. 30), `seed_search` (keyword para auto-elegir el top resultado) | `review_id`, `rating`, `text`, `title`, `author`, `date`, `verified_purchaser`, `helpful_positive/negative`, `photos` |

Fuentes: https://apify.com/apt_marble/walmart-reviews-scraper , https://apify.com/good-apis/walmart-reviews

---

## 3. AliExpress

### 3a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave | No-US |
|---|---|---|---|---|---|---|
| `scrapyx/aliexpress-products-scraper` | Scrapea listados de búsqueda/categoría de AliExpress | PPE, **$1.05 / 1,000 resultados** | 2 usuarios, 1 mensual, 100% OK, sin rating | `mode` ("search"/"urls"), `keywords` (array), `listingUrls`, `locale` (ej. "US","DE"), `sortBy`, `maxPages`, `maxItems` | `recordType`, `productId`, `productUrl`, `title`, `salePrice`, `originalPrice`, `starRating`, `ordersText`, `imageUrls` | Sí — `locale` fija idioma/moneda independiente de la IP del proxy |
| `dami_studio/aliexpress-products-scraper` | Busca en AliExpress y trae ID, título, precio, rating, pedidos | PPE, **$0.12 / 1,000 productos** | 5 usuarios, 2 mensuales, 100% OK, sin rating | `searchQueries`, `productUrls`, `maxItems` (def. 40, máx 5,000), `currency`, `country` (código de envío, def. "US") | `productId`, `title`, `productUrl`, `price`, `originalPrice`, `rating`, `orders`, `imageUrl` | Sí — `country`/`currency` configurables |

Fuentes: https://apify.com/scrapyx/aliexpress-products-scraper , https://apify.com/dami_studio/aliexpress-products-scraper

### 3b. Reseñas de compradores

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `getdataforme/aliexpress-product-reviews-scraper` | Reseñas de producto AliExpress con rating, comentario, imágenes | PPE, **$10.00 / 1,000 resultados** | 89 usuarios, 8 mensuales, 93.8% OK, sin rating | `urls` (array de páginas de producto), `itemLimit`, `proxyConfiguration` | `review_id`, `review_text`, `rating`, `review_date`, `product_id`, `reviewer_name`, `country`, `images`, `original_text` (idioma original) |
| `axlymxp/aliexpress-reviews-scraper` | Reseñas de AliExpress a escala: rating, texto, país del comprador, fotos | PPE, **$3.00 / 1,000 ítems** | 2 usuarios, 1 mensual, 100% OK, sin rating | `productUrls` (URL o ID numérico), `maxReviewsPerProduct`, `sort`, `onlyWithPhotos`, `language` | `product_id`, `review_id`, `rating`, `review_text`, `buyer_name`, `buyer_country`, `review_date`, `images`, `up_votes` |

Fuentes: https://apify.com/getdataforme/aliexpress-product-reviews-scraper , https://apify.com/axlymxp/aliexpress-reviews-scraper

---

## 4. Temu

### 4a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave |
|---|---|---|---|---|---|
| `apivault_labs/temu-product-scraper` | Listados de Temu en tiempo real: título, precio, rating, reviews, vendidos | PPE, **$0.003/ítem ($3.00 / 1,000 productos)** | 349 usuarios, 80 mensuales, 100% OK, **5.0/5** | `searchKeywords` (array — sí admite keyword), `productUrls`, `region`, `maxProductsPerKeyword`, `trendingNow`, `sortBy` | `title`, `productId`, `priceUsd`, `rating`, `reviewsCountInt` (solo agregado), `soldCountInt`, `shopName`, `images` |
| `scrapesage/temu-scraper` | Resultados de búsqueda de Temu → producto estructurado | PPE, **$1.10 / 1,000 productos** | no visible (no se relevó en detalle) | Términos de búsqueda, Start URLs, `maxProductsPerTerm`, filtros de precio | `productId`, `title`, `url`, `price`, `originalPrice`, `sellerId`, `imageUrl`, `soldCount` |
| `piotrv1001/temu-listings-scraper` | Extrae datos de producto **desde URLs de Temu** (no busca por keyword) | PPE, **$1.50 / 1,000 productos** | 1,116 usuarios, 13 mensuales, 0.0% runs OK (⚠️ mala racha reciente), 2.97/5 | `searchUrls` (solo URLs de producto) | `id`, `title`, `price`, `rating`, `totalReviews` (agregado), `salesCount`, `imageUrl` |

Fuentes: https://apify.com/apivault_labs/temu-product-scraper , https://apify.com/scrapesage/temu-scraper , https://apify.com/piotrv1001/temu-listings-scraper

### 4b. Reseñas de compradores

**Sin actor claro.** Los scrapers de producto de Temu revisados (`apivault_labs/temu-product-scraper`, `goat255/temu-products-scraper`, `scrapesage/temu-scraper`, `piotrv1001/temu-listings-scraper`) solo devuelven **rating/reviewCount agregados**, ninguno expone texto de reseña individual, autor o fecha por reseña. No se encontró un actor dedicado "Temu reviews scraper" con esos campos en la tienda. (Sí existen actores que scrapean reseñas de la *app* Temu en App Store/Google Play/Trustpilot, pero eso no es lo pedido: reseñas de producto en temu.com.)

Fuentes: https://apify.com/goat255/temu-products-scraper , https://apify.com/apivault_labs/temu-product-scraper , búsqueda web sin resultados de un actor de reseñas de producto Temu con campos individuales.

---

## 5. eBay

### 5a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave | No-US |
|---|---|---|---|---|---|---|
| `mrdoe/ebay-product-scraper` | Búsqueda y detalle de listados eBay sin cuenta ni API key | PPE, **$0.70 / 1,000 resultados** (primeras 10 filas de cada run gratis) | 1 usuario, 1 mensual, 96.4% OK, sin rating | `query`/`queries`, `operation` ("search"/"productDetails"), `itemId(s)`, `maxItems`, `sortBy`, `condition`, `minPrice`/`maxPrice` | `itemId`, `title`, `price`, `condition`, `soldCount`, `seller`, `rating`, `reviewCount`, `images` | **No** — la página dice explícitamente que solo cubre `ebay.com`, otros sitios (.co.uk, .de…) "aún no soportados" |
| `xtracto/ebay-search-scraper` | Búsqueda por keyword en eBay, recolecta cada card de resultado paginado | PPE, **$2.00 / 1,000 resultados** | 2 usuarios, 0 mensuales, 100% OK, sin rating | `queries` (array), `domain`, `maxPagesPerQuery`, `maxConcurrency` | `itemId`, `title`, `price`, `condition`, `location`, `listingType`, `image`, `url` | Sí — 8 dominios (US, UK, DE, FR, IT, ES, CA, AU) |
| `burbn/ebay-search-scraper` | Búsqueda por keyword en 20+ marketplaces globales de eBay | PPE, **$5.00 / 1,000 resultados** | 23 usuarios, 4 mensuales, 100% OK, sin rating | `query`, `domain`, `sort_by`, `condition`, `buying_format`, `min_price`/`max_price`, `maxPages` (1–100) | `itemId`, `title`, `price`, `sellerName`, `sellerFeedbackPercentage`, `rating`, `reviewCount` | Sí — "20+" dominios, lista completa no visible en la página |

Fuentes: https://apify.com/mrdoe/ebay-product-scraper , https://apify.com/xtracto/ebay-search-scraper , https://apify.com/burbn/ebay-search-scraper

### 5b. Reseñas / feedback de comprador

Nota de dominio: eBay no tiene "reseñas de producto" al estilo Amazon; lo que existe es feedback de vendedor y, para algunos catálogos con `epid`, reseñas de producto agregadas por eBay. Los actores de abajo scrapean eso.

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña/feedback) |
|---|---|---|---|---|---|
| `apt_marble/ebay-product-reviews-scraper` | Reseñas públicas de producto eBay: autor, rating, fecha, texto, verificado | PPE: reviews $1.00/1,000; resumen de producto $2.00/1,000 | 2 usuarios, 1 mensual, 100% OK, sin rating | `products` (número, link o URL de listado), `sort`, `maxReviewsPerProduct`, `includeProductSummary`, `marketplace`, `maxConcurrency` | `reviewId`, `rating`, `body`, `dateIso`, `author`, `epid` (product id de catálogo), `verifiedPurchase` |
| `web_wanderer/ebay-reviews-scraper` | Reseñas de producto y feedback de vendedor eBay, 40+ dominios | PPE (precio exacto no visible en la página) | 31 usuarios, 2 mensuales, 92.5% OK, sin rating | `product_urls`, `reviews_limit`, `sort`, `overall_rating`, `filter_image`, `domain` | `rating`, `comment`, `review_time`, `item_id`, `review_position`, `is_buyer`, `verified_purchase`, `image` |

Fuentes: https://apify.com/apt_marble/ebay-product-reviews-scraper , https://apify.com/web_wanderer/ebay-reviews-scraper

---

## 6. TikTok Shop

Un mismo actor cubre bien ambos objetivos.

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave |
|---|---|---|---|---|---|
| `unseenuser/tiktok-shop-scraper` | Todo-en-uno: productos, reseñas, tiendas y creadores afiliados de TikTok Shop | PPE, **$4.50 / 1,000 resultados** | **2,158 usuarios, 206 mensuales, 100% OK, 5.0/5** | `mode` (`shop_search`, `shop_catalog`, `product_details`, `product_reviews`, `creator_showcase`), `searchKeywords`, `shopUrls`, `productUrls`, `maxResults`, `maxReviewsPerProduct` | Filas de producto: `productId`, `title`, `price`, `rating`, `soldCount`. Filas de reseña (`mode=product_reviews`): `reviewId`, `text`, `rating`/`ratingStars`, `postedAt`, `verifiedPurchase`, imágenes |
| `jungle_synthesizer/tiktok-shop-product-detail-scraper` | Detalle de producto/tienda TikTok Shop, sin reviews individuales | PPE (precio exacto no visible; cobra arranque + por ítem) | 40 usuarios, 11 mensuales, 99.1% OK, sin rating | `items` (IDs o URLs), `country` (fr, de, gb, ie, it, es, us, jp, id, th, vn, ph, my, sg, tw, kr, mx, br — 18 mercados), `maxItems` | title, precio localizado, `rating`, `reviewCount` (agregado, sin texto individual) |
| `webdata_labs/tiktok-shop-scraper` | Productos TikTok Shop por keyword/categoría/tienda, con vendidos y rating | PPE, **$7.80–$10 / 1,000** (según plan) | 5 usuarios, 3 mensuales, 100% OK, sin rating | `searchQueries`, `categoryUrls`, `shopUrls`, `maxItems`, `minRating`, `onSaleOnly` | title, precio, `soldCount`, `rating`, `reviewCount` (agregado, sin texto) |

No-US: `jungle_synthesizer` documenta explícitamente 18 mercados no-US; `unseenuser` no listó países en la página pero su modo `shop_search` acepta cualquier keyword/tienda, sin lista de países visible.

Fuentes: https://apify.com/unseenuser/tiktok-shop-scraper , https://apify.com/jungle_synthesizer/tiktok-shop-product-detail-scraper , https://apify.com/webdata_labs/tiktok-shop-scraper

---

## 7. Etsy

### 7a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave |
|---|---|---|---|---|---|
| `good-apis/etsy-search-scraper` | Busca por keyword en Etsy, listados con precio/rating/shop | PPE, **$0.90 / 1,000 resultados** | 2 usuarios, 1 mensual, 100% OK, sin rating | `query` (requerido), `max_results` (def. 48, máx ~96) | `listing_id`, `title`, `price`, `original_price`, `shop`, `rating`, `reviews`, `image`, `url` |
| `xtracto/etsy-search-scraper` | Búsqueda por keyword, recolecta cada card paginada | PPE, **$2.00 / 1,000 resultados** | 7 usuarios, 1 mensual, 94.3% OK, sin rating | `queries` (array), `maxPagesPerQuery`, `maxConcurrency`, `maxRequestRetries` | `listingId`, `title`, `price`, `currency`, `shopName`, `image`, `url` |
| `epctex/etsy-scraper` | Extractor genérico de Etsy (producto, seller, listados) — el más usado | **Rental $30.00/mes** + uso de plataforma | **5,031 usuarios, 25 mensuales, 99.9% OK, 4.20/5** | `startUrls`, `search` (keyword), `endPage`, `maxItems`, `includeDescription`, `includeVariationPrices` | nombre, URL, imágenes, precio, seller (rating/reviewCount), variaciones, `reviewCount`, favoritos |

No-US: Etsy es un solo sitio global (no hay dominios país-por-país); ninguna de las páginas revisadas mostró parámetro de "marketplace"/país — el idioma/moneda del comprador se maneja del lado de Etsy, no vía input del actor.

Fuentes: https://apify.com/good-apis/etsy-search-scraper , https://apify.com/xtracto/etsy-search-scraper , https://apify.com/epctex/etsy-scraper

### 7b. Reseñas de compradores

Nota: en Etsy las reseñas están ancladas a la **tienda** (shop), no solo al listado; ambos actores devuelven igual el `listingId` de qué producto trata cada reseña.

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `reviewly/etsy-shop-reviews-scraper` | Todas las reseñas de una tienda Etsy, con bypass de bot-detection | PPE, **$2.50 / 1,000 reviews** | 41 usuarios, 23 mensuales, 94.9% OK, sin rating | `startUrls` (URLs de tienda), `maxReviews` (0=todas), `sortOption`, `targetDate` | `reviewId`, `rating`, `reviewBody`, `date` (ISO), `listingId`, `reviewerName`, `photos` |
| `getdataforme/etsy-review-scraper` | Reseñas de una tienda Etsy especificada por nombre | PPE, **$5.00 / 1,000 resultados** | 211 usuarios, 1 mensual, 100% OK, **5.00/5** | `shop_name_keyword`, `limit` (def. 10) | `receipt_id`, `listing_review`, `rating`, `date`, `buyer_login_name`, `listing_title`, `response` (respuesta del vendedor) |

Fuentes: https://apify.com/reviewly/etsy-shop-reviews-scraper , https://apify.com/getdataforme/etsy-review-scraper

---

## 8. Mercado Libre

### 8a. Buscar productos por keyword

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave | Países |
|---|---|---|---|---|---|---|
| `karamelo/mercado-libre-listings-scraper` | Listados de búsqueda y detalle de producto en 18 marketplaces LATAM | PPR: listados $2.00/1,000; detalle enriquecido $6.00/1,000 | 20 usuarios, 5 mensuales, 100% OK, sin rating | `keyword`, `country` (URL completa, ej. `https://listado.mercadolibre.com.ar/`), `sort`, `maxPages` (1–50), `extractProductDetails` | title, price, discount, seller, rating, SKU, shipping, `reviews`, `questions` | **18 países**: Argentina, Bolivia, Brasil, Chile, **Colombia**, Costa Rica, Rep. Dominicana, Ecuador, El Salvador, Guatemala, Honduras, **México**, Nicaragua, Panamá, Paraguay, Perú, Uruguay, Venezuela |
| `scrapesage/mercadolibre-scraper` | Productos, precios, sellers y specs en 14 marketplaces LATAM | PPE, **$2.00 / 1,000 productos** base (detalle/reviews cuestan aparte) | 7 usuarios, 4 mensuales, 100% OK, sin rating | `searchQueries`, `site` (códigos MLM, MLB, MLA, MLC, **MCO**, MPE, MLU, MLV, MEC, MRD, MBO, MPY, MGT, MPA), `maxItems`, `includeProductDetails`, `includeReviews` | `id`, `title`, `price`, `soldQuantity`, `rating`, `sellerReputation`, `officialStore`, specs | 14 países incluido **Colombia (MCO)** y México (MLM) |

Fuentes: https://apify.com/karamelo/mercado-libre-listings-scraper , https://apify.com/scrapesage/mercadolibre-scraper

### 8b. Reseñas de compradores (opiniones)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `karamelo/mercadolibre-review-scraper` | Reseñas públicas, rating, fecha, votos útiles, fotos, variante | PPE, **$0.70 / 1,000 resultados** | 3 usuarios, 2 mensuales, 100% OK, sin rating | `productUrls` (o ID de catálogo), `maxReviewsPerProduct` (def. 100), `reviewOrder`, `maxConcurrency` | `reviewId`, `reviewRating`, `reviewText`, `reviewDate`, `productId`, `catalogProductId`, `reviewerName`, `reviewLikes` |

Solo se relevó un actor con datos completos verificados en esta pasada (había más candidatos en la búsqueda — `omao/mercado-libre-reviews-scraper`, `sourabhbgp/mercadolibre-review-scraper` — pero no se abrió su página de detalle; no se incluyen para no inventar precios/campos).

Fuente: https://apify.com/karamelo/mercadolibre-review-scraper

---

## 9. Google Maps (reseñas)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) | No-US |
|---|---|---|---|---|---|---|
| `compass/google-maps-reviews-scraper` | El scraper de reseñas de Google Maps más usado del store | PPE, **desde $0.30 / 1,000 reseñas** (baja con el plan) | **57,229 usuarios, 6,821 mensuales, 99.6% OK, 4.85/5** | `startUrls` (URLs de lugar), `placeIds` (formato ChIJ/GhIJ), `maxReviews`, `reviewsSort`, `language`, `reviewsOrigin`, `personalData` | `text`, `stars`, `publishedAtDate`, `reviewId`, `name` (autor), `placeId`, `responseFromOwnerText` | Sí — cobertura de 190+ países vía Google Maps, `language` configurable |
| `getanyapi/google-maps-reviews-scraper` | Reseñas de cualquier lugar en Google Maps | **PPR, $0.25 / 1,000 resultados** | 1 usuario, 0 mensuales, 100% OK, sin rating | `placeId` (requerido), `limit` (1–100), `sort`, `reviewsFilterString`, `postedLimit`, `language` | `text`, `rating`, `createdUtc`, `reviewId`, `author`, `publishedAgo`, `likes`, `ownerResponse` | Sí — `language` configurable, sin lista de países pero cubre cualquier `placeId` global |
| `scraperlink/google-maps-scraper` | Extracción de listados de negocio + reseñas opcionales | PPE: base $0.40/1,000 resultados; add-on reseñas completas $0.25/1,000 | **3,702 usuarios, 611 mensuales, 99.9% OK, 4.97/5** | `query`, `num` (hasta 5,000), `gl`/`hl` (país/idioma), `reviews` (bool para activar reseñas), filtros geográficos | Con `reviews` activado: texto, rating (1–5), fecha, identidad del autor | Sí — `gl`/`hl` por país/idioma |

Fuentes: https://apify.com/compass/google-maps-reviews-scraper , https://apify.com/getanyapi/google-maps-reviews-scraper , https://apify.com/scraperlink/google-maps-scraper

---

## 10. Trustpilot (reseñas)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `webdata_labs/trustpilot-review-scraper` | Reseñas Trustpilot con filtro por estrella/fecha/idioma/verificación | PPE, **$0.50/1,000 (plan Free) hasta $0.12/1,000 (plan Diamond)**; sin cargo de arranque | 4 usuarios, 2 mensuales, 100% OK, sin rating | `companyUrls` (dominios o URLs Trustpilot, hasta 50), `maxReviewsPerCompany`, `stars`, `dateFrom`/`dateTo`, `languages`, `verificationStatus`, `replyStatus` | `reviewId`, `text`, `title`, `rating`, `publishedDate`, `experienceDate`, `authorName`, `country`, `hasReply`, `companyDomain`, `companyTrustScore` |
| `thirdwatch/trustpilot-reviews-scraper` | Reseñas, ratings, respuestas, metadata del reviewer y TrustScore | PPE, **$0.002/reseña (Free) → $0.0011/reseña (Gold) = ~$1.10–$2.00/1,000** + $0.05 por sesión de browser | 13 usuarios, 4 mensuales, 88.5% OK, 5.0/5 | `companyUrls`, `maxReviewsPerCompany` (1–1,000), `ratings`, `languages`, `reviewerCountries`, `sortBy`, `verifiedOnly` | `review_id`, `review_text`, `review_title`, `review_rating`, `review_date`, `reviewer_name`, `reviewer_country`, `verified`, `reply_text` |

Fuentes: https://apify.com/webdata_labs/trustpilot-review-scraper , https://apify.com/thirdwatch/trustpilot-reviews-scraper

---

## 11. Google Play (reseñas)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `automation-lab/google-play-scraper` | App details + búsqueda + reseñas de Google Play, todo en un actor | PPE, **desde ~$0.0023/detalle de app y ~$0.00115/reseña (plan Free)**, baja en planes pagos | **783 usuarios, 129 mensuales, 81.3% OK, 5.00/5** | `mode` (search/topCharts/details/reviews), `searchTerms`, `appIds` (ej. `com.whatsapp`), `country`, `language`, `maxResults` (1–500), `reviewSort`, `reviewScore` | `reviewId`, `appId`, `score`, `text`, `date`, `userName`, `thumbsUp`, `version`, `replyText`/`replyDate` |
| `scrapesage/google-play-reviews-scraper` | Reseñas de apps Google Play con respuestas del developer, multi-país | PPE, **$0.10 / 1,000 reseñas** (mucho más barato, pero mucha menos base de usuarios) | 2 usuarios, 1 mensual, 100% OK, sin rating | `appIds`, `countries` (array, ej. us/gb/de), `maxReviewsPerApp`, `ratings`, `publishedAfter`/`publishedBefore`, `onlyWithDeveloperReply` | `score`, `text`, `publishedAt`, `reviewId`, `appId`, `userName`, `developerReplyText` |

Fuentes: https://apify.com/automation-lab/google-play-scraper , https://apify.com/scrapesage/google-play-reviews-scraper

---

## 12. App Store (reseñas de iOS)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por reseña) |
|---|---|---|---|---|---|
| `automation-lab/apple-app-store-reviews-scraper` | Reseñas de App Store desde el RSS público de iTunes | PPE, **~$0.09–$0.17 / 1,000 reseñas** según plan (cifras de la página: $0.0001725/reseña Free → $0.000042 Diamond) + $0.005 arranque de run | 21 usuarios, 4 mensuales, **100% OK**, sin rating | `appUrls`, `appIds`, `countries`, `maxReviewsPerApp`, `reviewsFromDate`, `includeAppMetadata` | `reviewText`, `rating`, `reviewDate`, `reviewId`, `appId`, `authorName`, `reviewVersion`, `voteCount` |
| `easyapi/app-store-reviews-scraper` | Reseñas de App Store, configurable por país | PPE, **$2.99 / 1,000 resultados** | 538 usuarios, 18 mensuales, 100% OK, **1.24/5 ⚠️ (rating bajo)** | `appId`/`id`, `country` (def. "us"), `limit` | `id`, `score`, `text`, `updated`, `userName`, `userUrl`, `url`, `version` |
| `appdata-labs/app-store-reviews` | Reseñas desde el feed oficial de Apple, sin parsear HTML | PPE, **$4.00 / 1,000 reseñas** | 1 usuario, 0 mensuales, **0.0% OK ⚠️**, sin rating | `appStoreUrlsOrIds`, `countries`, `maxReviewsPerApp` (tope 500), `sortBy`, `fallbackCountries` | `text`, `rating`, `updatedAt`, `reviewId`, `appId`, `userName`, `country` |

Fuentes: https://apify.com/automation-lab/apple-app-store-reviews-scraper , https://apify.com/easyapi/app-store-reviews-scraper , https://apify.com/appdata-labs/app-store-reviews

---

## 13. Instagram (comentarios públicos / hashtag)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave |
|---|---|---|---|---|---|
| `apify/instagram-comment-scraper` (oficial Apify) | Comentarios de posts/reels de Instagram, con perfil y engagement | PPE, **$1.90 / 1,000 comentarios** | **54,676 usuarios, 4,925 mensuales, 100% OK, 4.66/5** | `directUrls` (URLs de post/reel), `resultsLimit`, `includeNestedComments` | `text`, `timestamp`, `id`, `ownerUsername`, `likesCount`, `repliesCount`, `ownerProfilePicUrl` |
| `apify/instagram-hashtag-scraper` (oficial Apify) | Posts/reels por hashtag: engagement, caption, primeros comentarios | PPE, **desde $1.90 / 1,000 resultados** | **116,769 usuarios, 9,248 mensuales, 100% OK, 3.39/5** | `hashtags` (array, con o sin #), `keywordSearch` (bool), `resultsType` ("posts"/"reels"), `resultsLimit` | id de post, owner, likes/comments/shares, caption, `hashtags`, `mentions`; con `keywordSearch` incluye hasta 10 comentarios recientes |

Fuentes: https://apify.com/apify/instagram-comment-scraper , https://apify.com/apify/instagram-hashtag-scraper

---

## 14. Facebook (comentarios públicos de posts)

| Actor ID | Qué hace | Precio | Usuarios/runs/rating | Input clave | Output clave (por comentario) |
|---|---|---|---|---|---|
| `apify/facebook-comments-scraper` (oficial Apify) | Comentarios de posts públicos de Facebook | PPE, **$1.40 / 1,000 comentarios** | **43,465 usuarios, 3,322 mensuales, 100% OK, 4.75/5** | `startUrls` (URLs de post), `resultsLimit`, `includeNestedComments`, `viewOption`, `onlyCommentsNewerThan` | `text`, `date`, `commentId`, `facebookId` (post), `facebookUrl`, `profileName`, `likesCount` |
| `bovi/facebook-comments-scraper` | Comentarios sin login, funciona en posts/páginas/grupos públicos | PPE, **$1.94 / 1,000 comentarios** | 3 usuarios, 0 mensuales, 100% OK, sin rating | `postUrls`, `maxComments`, `pageSize` | `comment_id`, `post_id`, `post_url`, `author_name`, `text`, `like_count`, `created_time`, `is_reply` |

Fuentes: https://apify.com/apify/facebook-comments-scraper , https://apify.com/bovi/facebook-comments-scraper

---

## Preguntas específicas

### (a) ¿`POST /v2/acts/{actorId}/runs` acepta `maxItems` y `maxTotalChargeUsd`? ¿Qué limita cada uno?

Sí, ambos son query parameters documentados en el endpoint "Run Actor". Verificado en dos páginas equivalentes de la documentación oficial (contenido idéntico):

- **`maxItems`** — cita textual: *"Specifies the maximum number of dataset items that will be charged for pay-per-result Actors. This does NOT guarantee that the Actor will return only this many items. It only ensures you won't be charged for more than this number of items. Only works for pay-per-result Actors."* Es decir: **solo aplica a actores PPR (pay-per-result)**; pone un techo a cuántos ítems del dataset se facturan (el actor puede seguir corriendo/produciendo de más, pero no te cobran esos extra). Se refleja dentro del run vía la env var `ACTOR_MAX_PAID_DATASET_ITEMS`.
- **`maxTotalChargeUsd`** — cita textual: *"Specifies the maximum total cost of the run. Use it to cap the total amount charged for all pricing models. You can access the maximum cost in your Actor by using the `ACTOR_MAX_TOTAL_CHARGE_USD` environment variable."* Es decir: **aplica a todos los modelos de precio** (incluido PPE) y pone un techo al gasto total en USD del run completo — el actor puede leer ese tope internamente para auto-limitarse (vía `ACTOR_MAX_TOTAL_CHARGE_USD`) y frenar antes de pasarse.

En resumen: para un actor **pay-per-result**, `maxItems` limita cantidad de resultados facturables; para un actor **pay-per-event** (que no tiene un "precio por ítem del dataset" fijo, sino precio por evento), la única forma de poner techo de gasto vía la API es `maxTotalChargeUsd`.

Fuentes: https://docs.apify.com/api/v2 (landing, enlaza a la referencia), https://docs.apify.com/api/v2/act-runs-post , confirmado también en https://docs.apify.com/api/v2/actors-runs-post.md

### (b) `junglee/amazon-reviews-scraper`: ¿admite keyword/búsqueda o solo URLs de producto? ¿`maxReviews` es por URL de producto?

**Solo URLs de producto**, no busca por keyword de producto. El input schema (https://apify.com/junglee/amazon-reviews-scraper/input-schema) tiene `productUrls` como campo principal — "Enter the URL or URLs of the Amazon products you want to scrape... Click + Add to scrape multiple URLs at once." No hay ningún campo para buscar productos por término; el único campo con "keywords" en el nombre es `reviewsFilterByKeywords`, que **filtra el texto de las reseñas ya traídas** (ej. quedarte solo con reseñas que mencionen "calidad" o "precio"), no busca productos.

**`maxReviews` sí es efectivamente por URL de producto**: como el input es un array de `productUrls`, y la descripción del campo dice literalmente *"Type in the amount of reviews to be scraped... Note: max amount of reviews per product is 100 per star count (e.g. 100 reviews per 1 star)"* — el límite se aplica **producto por producto** (cada URL en el array), con un tope duro adicional de ~100 reseñas por cada nivel de estrella por producto (o sea, hasta ~500 reseñas por producto si tiene ≥100 por cada rating de 1 a 5), independientemente de qué tan alto pongas `maxReviews`.

Fuentes: https://apify.com/junglee/amazon-reviews-scraper , https://apify.com/junglee/amazon-reviews-scraper/input-schema

---

## Notas generales sobre confiabilidad de los datos

- Los conteos de "usuarios/runs/rating" son una foto del 2026-09-20; varios actores candidatos tienen muy pocos usuarios (1-5) y "sin rating" — son operativos pero sin historial que confirme confiabilidad real. Donde había un actor con mucha más tracción (ej. `junglee/amazon-crawler`, `compass/google-maps-reviews-scraper`, los `apify/*` oficiales, `unseenuser/tiktok-shop-scraper`), se priorizó mencionarlo aunque no siempre sea el más barato.
- Dos actores mostraron señales de alerta que vale la pena repetir antes de usarlos: `piotrv1001/temu-listings-scraper` tenía **0.0% de runs exitosos** el día de esta consulta, y `appdata-labs/app-store-reviews` también **0.0%**; `easyapi/app-store-reviews-scraper` tiene rating **1.24/5** pese a 538 usuarios.
- No se abrió la pestaña `/pricing` de cada actor por separado (solo para `junglee/amazon-reviews-scraper` como verificación cruzada) — el resto de precios vienen del badge/resumen visible en la página principal del actor, que Apify normalmente sincroniza con `/pricing`.
