# Nicho Parte 4 (primera tanda): más tiendas de productos — diseño

Fecha: 2026-09-30. Aprobado por Daniel por partes en la conversación «Avatares y subproductos por nicho»
(«va bien, ejecuta todo»). Se construye sobre la investigación automática de la Parte 3
(`docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`, en producción desde 2026-09-30) y el
inventario de actores `docs/nicho/apify-inventario-2026-09-20.md`.

## 0. Alcance

**Entran:** Walmart y AliExpress como tiendas de la cadena (buscar productos → Claude elige los del nicho
→ reseñas), más la regla de «otro mercado» para TODAS las tiendas (también Amazon y Mercado Libre) y las
búsquedas por idioma. eBay y Etsy se probaron y quedaron fuera (ver §1.1).

**Fuera de esta tanda:** Google Maps, Trustpilot, Google Play, App Store, Instagram y Facebook (tanda
siguiente: no son productos); Temu (ningún actor trae reseñas una por una, solo el promedio); ordenar por
«más reseñados» en Mercado Libre (su buscador no trae la cifra).

Decisiones de Daniel: (1) empezar por tiendas de productos; (2) las reseñas de compradores de otros países
SÍ cuentan, marcadas con su país; (3) probar cada actor con centavos ANTES de escribir su lector; (4) en la
pantalla, las tiendas de otros mercados vienen desmarcadas.

## 1. Verificación previa (probar antes de escribir)

Por cada tienda se corre el actor candidato de búsqueda y el de reseñas con lo mínimo (1 búsqueda en inglés,
3 productos, 5 reseñas de un solo producto), en el VPS (allí vive `APIFY_TOKEN`), con `maxItems` y
`maxTotalChargeUsd` en cada corrida. Lo que devuelva cada actor se guarda TAL CUAL (recortado a unos pocos
ítems, sin datos de autores) como fixture en `tests/fixtures/nicho/plataformas/<clave>_busqueda.json` /
`<clave>_resenas.json`; los lectores se escriben contra esos datos reales. El gasto se anota como interno
(`_creatv`, tipo `recoleccion`, referencia `verificacion:<clave>:<busqueda|resenas>:<fecha>`).

Candidatos (inventario 2026-09-20):

| Tienda | Búsqueda | Reseñas | Países |
|---|---|---|---|
| Walmart | `s-r/walmart-scraper` (US$ 1 / 1 000) | `good-apis/walmart-reviews` (US$ 0,80 / 1 000, gratis sin reseñas) | solo EE. UU. |
| AliExpress | `dami_studio/aliexpress-products-scraper` (US$ 0,12 / 1 000) | `axlymxp/aliexpress-reviews-scraper` (US$ 3 / 1 000, trae país del comprador) | todo el mundo |
| eBay | `xtracto/ebay-search-scraper` (US$ 2 / 1 000, 8 dominios) | `apt_marble/ebay-product-reviews-scraper` (US$ 1 / 1 000) | US, UK, DE, FR, IT, ES, CA, AU |
| Etsy | `good-apis/etsy-search-scraper` (US$ 0,90 / 1 000) | `reviewly/etsy-shop-reviews-scraper` (US$ 2,50 / 1 000, por tienda) | todo el mundo |

Plan B: si un actor falla, no trae texto de reseña o cobra distinto de lo que dice su página, se prueba la
alternativa del inventario; si ninguna sirve, la tienda queda fuera con el motivo anotado en este spec. El
precio que va al registro es el que se vio cobrar en la verificación.

### 1.1 Resultado de la verificación (2026-09-30, ≈ US$ 0,20 anotados bajo `_creatv`)

| Tienda | Búsqueda | Reseñas | Decisión |
|---|---|---|---|
| Walmart | `s-r~walmart-scraper` OK (item_id, title, rating, reviews_count, url, image, seller; **sin precio** salvo `fetch_prices`, que cobra US$ 0,003 por producto: no se pide) | `good-apis~walmart-reviews` falló (BACKEND_UNAVAILABLE y sin id de producto en la reseña); **`apt_marble~walmart-reviews-scraper` OK** (productId, reviewId, text, title, rating, date ISO, verifiedPurchase; US$ 0,001 por reseña; varios productos por corrida) | **entra** |
| AliExpress | `dami_studio~aliexpress-products-scraper` OK (productId, productUrl, title, price, currency, rating, **orders** — no trae número de reseñas; US$ 0,001 arranque + 0,00012 por producto) | `axlymxp~aliexpress-reviews-scraper` OK (review_id, review_text en el idioma del comprador, rating, review_date «30 Jun 2026», **buyer_country**, product_id; US$ 0,01 arranque + 0,003 por reseña; varios productos por corrida) | **entra** |
| eBay | `xtracto` 0 resultados (cobró 4 arranques); `burbn` llegó al techo sin resultados; `mrdoe` OK pero con precios en CLP (proxy de Chile) | `apt_marble~ebay-…` y `web_wanderer~ebay-…` devolvieron 0 reseñas para un producto común (eBay casi no tiene reseñas de producto fuera de su catálogo) | **fuera** de esta tanda |
| Etsy | `good-apis~etsy-search-scraper` OK | `reviewly~etsy-shop-reviews-scraper` >6 min sin traer 5 reseñas (se abortó, US$ 0,02); `getdataforme~etsy-review-scraper` exige acceso completo a la cuenta de Apify (no se concede) | **fuera** de esta tanda |

Consecuencias: esta tanda entrega **Walmart y AliExpress** más la regla de otro mercado para todas las tiendas
y las búsquedas por idioma. Al elegir «los más reseñados», un producto sin número de reseñas desempata por
sus pedidos/vendidos (`extra.vendidos`: AliExpress `orders`, Mercado Libre `soldQuantity`). Los fixtures de
pruebas son la salida real recortada (sin autores): `walmart_busqueda/resenas.json`,
`aliexpress_busqueda/resenas.json`.

## 2. Cómo entran en la cadena

- **Registro** (`nicho/fuentes/plataformas.py`): cada tienda nueva es una entrada de `PLATAFORMAS` con su
  buscador, su actor de reseñas, `armar_entradas`, lector y precio por resultado; la cadena no cambia
  (pasos `buscar:<clave>` / `resenas:<clave>`, `nicho.fuentes.plataforma.FuentePlataforma`).
- **Mercado local u otro mercado** (regla para todas): `plataformas.mercado(clave, pais)` → `("local",
  pais)` si la tienda tiene sitio en ese país, `("otro", casa)` si no, donde `casa` es su sitio principal
  (Amazon → US, Walmart → US, eBay → US, Mercado Libre → MX). AliExpress, Etsy y TikTok Shop venden a todo
  el mundo: son locales en cualquier país (su reseña trae el país del comprador cuando el actor lo da). Una
  tienda de otro mercado busca y trae reseñas de SU sitio (`casa`), nunca se rechaza por país.
- **Idioma de búsqueda**: `plataformas.idioma_busqueda(clave, pais)` — el idioma del sitio que se usa
  (local: el del país; otro mercado: el de la `casa`; AliExpress y Etsy: inglés).
- **Búsquedas por idioma**: `consultas_con_claude` pide en UNA llamada las búsquedas en cada idioma que
  necesiten las tiendas elegidas (`{"es": […], "en": […]}`), con el mismo tope aprobado por idioma. Se
  guardan `consultas` (las del idioma del país, las que usan Reddit/YouTube como hoy) y
  `consultas_por_idioma`; cada `buscar:<clave>` usa las de su idioma. Si la respuesta no trae un idioma, esa
  tienda usa las del idioma del país (salida de emergencia, sin volver a llamar a Claude).
- **Particularidades**: eBay solo trae reseñas de productos de su catálogo (los demás devuelven 0 y no
  cobran); Etsy pide las reseñas por TIENDA (una vez por tienda de los productos elegidos, tope por tienda) y
  cada reseña dice de qué producto es.
- **Topes y costo**: los mismos de hoy (búsquedas, productos por búsqueda, productos elegidos, reseñas por
  producto), con techo de cobro por corrida; la cifra aprobada cubre el peor caso de todas las tiendas
  marcadas.

## 3. Marcar el país y qué ve Claude

- Cada comentario de tienda guarda en `comentario.extra` el `pais` del comprador (o el del sitio si la
  reseña no lo trae) y `mercado` (`local` | `otro`) respecto al país del estudio. Sin migración.
- En la pantalla del estudio, los comentarios y las citas de otro mercado llevan una etiqueta con su país.
- Selección de comentarios para Claude (`avatares.seleccionar`, 600 / 250 000 caracteres): sigue el reparto
  por turnos entre fuentes, pero en cada vuelta van primero las fuentes del mercado local.
- Los prompts de generación y de completado marcan cada comentario de otro mercado («(otro mercado: EE.
  UU.)») y llevan la regla: identidad, demografía, edad, situación y nivel de conciencia salen de los
  comentarios del mercado local (si no alcanzan, «(inferido)»); deseos, dolores, soluciones que probaron,
  momentos de uso y palabras clave pueden salir de todos.
- Las citas se siguen verificando palabra por palabra contra el comentario original, en su idioma original,
  y muestran su país.

## 4. Pantalla y costo

- La tarjeta «Investigar el nicho» agrupa las tiendas: «Tiendas de <país>» (marcadas de entrada) y «De
  otros mercados» (desmarcadas, con el país del sitio: «Walmart (EE. UU.)», «Amazon (EE. UU.)») y un enlace
  «Marcar todas». Cada tienda muestra su costo en la tabla del estimado; un solo clic aprueba la cifra.
- Peor caso aproximado por tienda con los topes por defecto (3 búsquedas × 20 productos, 15 elegidos × 100
  reseñas), antes de la verificación: Amazon ≈ US$ 1,55 · Mercado Libre ≈ 1,20 · Walmart ≈ 1,30 · eBay ≈
  1,65 · Etsy ≈ 3,80 · AliExpress ≈ 4,50 · TikTok Shop ≈ 7,00.
- Visibilidad igual que hoy: las tiendas usan la llave de Apify de Creatv; sin llave el cliente no las ve y
  solo el admin ve el aviso.
- Todo texto nuevo pasa por el catálogo de idioma.

## 5. Pruebas, despliegue y prueba final

- Pruebas sin red: lectores contra los fixtures reales de la verificación; registro (`mercado`,
  `idioma_busqueda`, `cubre`, países); búsquedas por idioma (respuesta completa e incompleta); punta a punta
  con una tienda de otro mercado (comentarios marcados, prompt con la etiqueta, locales primero); pantalla
  (dos grupos, lo marcado de entrada, «Marcar todas», celular, idioma).
- Construcción como la Parte 3: plan por tareas, implementador + revisión por tarea, revisión final de toda
  la rama partida por zonas, publicación sobre `origin/main` sin arrastrar trabajo ajeno, despliegue con la
  cola vacía y los dos servicios.
- Prueba final de centavos: un estudio en colorado_forja con las tiendas nuevas y los topes mínimos. Sin
  crédito de Anthropic corren la verificación y las búsquedas; lo que necesita a Claude espera «Reanudar».

## 6. Estado

Implementado con el plan `docs/superpowers/plans/2026-09-30-nicho-mas-tiendas.md` (rulings R1–R11 allí): el
arranque por corrida entra en techos, estimados y gasto; Walmart y AliExpress piden reseñas con el link armado
desde el id; el tono va con lo que sale del mercado local; los nombres de país son los de `datos.NOMBRES_PAIS`.

## Enmienda 2026-10-01

Prueba real en producción (run `wpny9jQYLztteag8Z`, 3 productos de amazon.com.mx): junglee en el plan FREE de
Apify solo lee 1 link y entrega 10 reseñas por corrida (su propio aviso lo dice; Starter lo sube a 40) — una
corrida con los `productUrls` de varios productos deja sin leer a todos menos el primero. Ruling (controlador):
una corrida POR PRODUCTO (o por link, en la fuente manual de Apify), a 2048 MB para que quepan 5 a la vez
dentro del límite de 16 GB de la cuenta FREE. El techo mínimo de US$ 0,50 por corrida que Apify exige para
aceptar el POST sigue existiendo, pero YA NO infla el estimado que se le muestra a la persona antes de
aprobar: `estimar()`/`plataformas.estimar_busqueda`/`estimar_resenas` ahora suman el PEOR CASO REAL de cada
corrida (`peor_usd` = resultados × precio + arranque, sin piso); el mínimo solo entra al armar la corrida de
verdad (`corridas()`/`_con_tope`, campo `max_usd`), porque ahí Apify sí lo exige. Para un actor sin mínimo los
dos valores son iguales, así que sus estimados no cambiaron. Un 402 de Apify (límite de plan: uso mensual,
memoria, corridas simultáneas) muestra el mensaje de Apify, nunca el de token.
