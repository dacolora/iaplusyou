# NVP: el porcentaje de visitantes nuevos en todas las métricas

Fecha: 2026-10-09. Pedido del cliente de HappyFlops a Daniel: «Are we able to see the NVP as well? New Visitor
Percentage. This is a very important percentage to see if it is TOF, MOF or BOF». Daniel: «metámoslo en todas
nuestras métricas». Diseño aprobado en el chat el mismo día, con cortes 70 % / 40 % y «ejecuta todo».

## 1. Qué es y de dónde sale

NVP = visitantes nuevos ÷ visitantes únicos × 100, como lo define Triple Whale (`pixel_new_visitor_percent` =
New Visitors / Unique Visitors, https://triplewhale.readme.io/docs/pixel-joined-table, leído 2026-10-09).

- **Por anuncio y día:** `pixel_joined_tvf()` trae `unique_visitors` y `new_visitors` («The Pixel-reported number
  of first-time visitors to the site»), por canal/anuncio/día, con el modelo y la ventana del proyecto.
- **Por tienda y día:** `web_analytics_table` trae los mismos dos (`blended_stats_tvf` no los tiene).
- **Meta no lo da.** Sin Triple Whale conectado no hay NVP en ningún lado.

**Comprobado contra la tienda real** (happyflops-norge, 2026-10-02..08, sonda de solo lectura desde el VPS):
Pixel 2 888 filas, 28 777 únicos, 13 848 nuevos (48,1 %); facebook-ads 52,3 %; Direct 34,9 %; Klaviyo 24,9 %;
google-ads 61,2 %; los anuncios de Meta con más tráfico entre 67 y 83 %. `web_analytics_table`: 7 filas,
29 866 únicos, 13 848 nuevos (46,4 %). Las columnas existen y el dato tiene sentido.

**Límites que se dicen en pantalla (un `title`/nota, no un párrafo):**
- Solo cuentan las visitas que el Pixel atribuye a un anuncio (sin rastreo de Triple Whale = «sin datos»).
- Los únicos vienen contados por día (y por canal en el Pixel): sumar días cuenta dos veces a quien vuelve otro
  día, así que en periodos largos el NVP es aproximado y puede diferir un poco del de Triple Whale. Se suma igual
  en todos lados (`SUM(nuevos) / SUM(visitantes)`), nunca un promedio de porcentajes.

## 2. Etapa del embudo

Una sola regla pura para toda la app, `triple_whale/visitantes.py` (sin Flask ni base):

| Visitantes únicos del periodo | NVP | Etapa |
|---|---|---|
| 0 | — | «sin datos» |
| 1 a 49 | se muestra en gris | «pocos datos» (sin etapa) |
| ≥ 50 | ≥ 70 % | **TOF** (llega a gente que no te conoce) |
| ≥ 50 | 40 % a < 70 % | **MOF** |
| ≥ 50 | < 40 % | **BOF** (gente que ya visitó la tienda) |

Constantes `UMBRAL_TOF = 70`, `UMBRAL_BOF = 40`, `MIN_VISITANTES = 50` (decisión de Daniel, 2026-10-09: 70/40,
la opción recomendada; el cliente puede pedir otros y se cambian aquí). La etapa es una lectura, no un veredicto:
no cambia ganador/perdedor, ni el decisor de Experimentos, ni ninguna regla que gaste.

## 3. Datos (migración 0036)

- `tw_anuncio_dia` y `tw_tienda_dia` ganan `visitantes` y `visitantes_nuevos` (Integer, default 0).
- `datos.COLUMNAS_PIXEL` y `datos.COLUMNAS_TIENDA` los incluyen: todas las lecturas que ya suman esas listas
  (`totales_por_anuncio`, `totales_anuncio`, `serie_tienda`…) los traen sin código nuevo.
- **Consultas del Pixel: tres versiones.** `consultas_pixel` = [con visitantes, completa, mínima]. Si Triple
  Whale rechaza las columnas nuevas, la copia baja a la completa de hoy y solo falta el NVP (lección de
  `net_profit`, PND-150: una columna de más tumbaba la copia entera a la mínima). `NOMBRES_CONSULTA` pasa a ser
  por tipo de consulta.
- **Visitantes de la tienda: consulta aparte** (`consultas_visitantes_tienda`, sobre `web_analytics_table`)
  dentro del bloque de la tienda: se mezcla por fecha en los registros de `tw_tienda_dia` antes de
  `reemplazar_tienda`. Si falla, la tienda se guarda sin visitantes y el resumen lo anota en `fallos`.
- **Historia:** cada tienda vuelve a traer sus 90 días UNA vez (`rango_pendiente` mira la marca
  `extra.backfill_visitantes`). Enmienda de la revisión: la marca queda cuando la copia trajo visitantes en todo el
  rango, o tras 3 copias sin lograrlo (una cuenta sin visitantes no repite 90 días cada 2 h para siempre, y un error
  pasajero durante la copia de 90 días no deja esas semanas en cero).

## 4. Dónde se ve

Un componente `chip-nvp` (macro `nvp(...)` en `_componentes.html`, CSS en `static/estilos/componentes/nvp.css`,
sección en la Guía): «52 % · MOF», gris si son pocos datos, «—» sin datos; `title` con nuevos/únicos y la regla.

1. **Pestaña Triple Whale.** KPI de la tienda «Visitantes nuevos (NVP)» con el periodo anterior; columna NVP en la
   tabla de anuncios; el dato en la tarjeta de análisis de cada anuncio.
2. **Pestaña Meta (las cuentas leídas).** Columna NVP en «Por cuenta», campañas, conjuntos y anuncios, y KPI
   arriba. Sale de `tw_anuncio_dia` (canal `facebook-ads`) agrupado por el mismo id del nivel, UNA consulta por
   nivel y página (nunca una por fila). Sin Triple Whale: la columna no aparece y una línea dice «Conecta Triple
   Whale para ver el % de visitantes nuevos (NVP)».
3. **Experimentos.** NVP por pieza (por su `ad_id`) y por experimento en el centro de resultados; solo se muestra.
4. **Tablero.** En «Tu tienda según Triple Whale», el NVP de la tienda.
5. **IA.** «Evaluar con IA» y «Cómo mejorarlo» reciben el NVP y la etapa de cada anuncio (y de la tienda) para
   leer el embudo (p. ej. «una campaña de prospección que llega a gente que ya te conoce»). Se mide con
   `eval-claude` antes y después; no cambia precio ni topes. **Enmienda del mismo día** (eval
   `2026-10-09-nvp-en-la-ia.md`, revisiones guardian-gasto y revisor): «Cómo mejorarlo» lo lleva; «Evaluar con IA»
   necesita subir su tope de 16 000 a 32 000 para no cortar la respuesta, eso cambia lo que cuesta y lo decide Daniel
   (PND-210): hasta entonces su prompt sigue igual (las cifras sí viajan en la muestra guardada).

## 5. Fuera de alcance

Cambiar los cortes desde la pantalla; usar el NVP en el decisor o en reglas automáticas; NVP sin Triple Whale
(GA4, Shopify); una gráfica día a día del NVP. Si el cliente lo pide, va como pendiente.

## 6. Pruebas

- `visitantes.py`: bordes 0 / 49 / 50, 40 y 70 exactos.
- Sync: la versión con visitantes guarda los dos números; si se rechaza, baja a la completa y la copia sigue;
  la consulta de la tienda falla sin tumbar la tienda; la marca de historia trae 90 días una sola vez.
- Migración en una copia de la base de producción antes de desplegar.
- Cada pantalla: el NVP aparece con Triple Whale y no rompe sin él; una consulta por nivel (no por fila);
  captura en el navegador de la pestaña Triple Whale y la pestaña Meta con datos de verdad.
