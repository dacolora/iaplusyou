# Fuente TrendTrack para la biblioteca de referentes (2026-09-30)

Pedido de Daniel: «agreguemos también la plataforma TrendTrack». Hasta hoy TrendTrack solo servía para
pegar un link compartido en Crear (`referencias_link.py`). Ahora es una tercera fuente de barrido de
Referentes, junto a Atria y Apify (spec 2026-09-23 §4): `referentes/fuentes/trendtrack.py`, mismo
contrato (`estimar`, `probar`, `traer`), misma tarea (`referentes_barrer`), misma clasificación con Claude.

## 1. Qué trae y qué no

- **Anuncios de Meta por palabra clave.** `GET /v1/ads` exige `search`; el filtro por página de una marca
  vive en `POST /v1/ads/query`, cuyo cuerpo no conocemos, así que el modo «De una marca» no se ofrece
  (`MODOS = ("palabra",)`, `fuentes.modos(tipo)`; el formulario esconde esa tarjeta, y las rutas y el
  panel admin rechazan el modo con un aviso). Lo demás de TrendTrack (tiendas Shopify, anunciantes,
  Google y TikTok Ads) queda fuera de este cambio.
- La palabra llega ya traducida al inglés (`referentes.traducir.preparar_consulta`, como en las otras
  fuentes). No hay filtro de idioma ni de país.

## 2. Lo confirmado y lo no verificado

Confirmado por la documentación pública (leída el 2026-09-30 a través de resúmenes: `docs.trendtrack.io`
está bloqueado desde el contenedor, así que **nunca se vio una respuesta real**):

| Tema | Regla |
|---|---|
| Base y autenticación | `https://api.trendtrack.io`, `Authorization: Bearer <llave>` (no hay `x-api-key`) |
| Prueba de la llave | `GET /v1/me`, sin consumir créditos |
| Paginación | `limit` + `offset`; una página más corta que `limit` es la última |
| Sobre | `{data, requestId}` más paginación en las colecciones |
| Costo | 1 crédito por fila devuelta; US$ 1 = 1 000 créditos; Pro incluye 20 000 al mes |
| Ritmo (Pro) | 20 peticiones por segundo, 1 200 por hora |
| Errores | 401 llave, 402 `insufficient_credits`, 429 con `Retry-After` |
| Plan | La API no viene en el Starter |

**No verificado: los nombres de los campos de cada anuncio.** `_normalizar` los lee con una tabla de alias
(`_CLAVES`) y nada más depende de ellos. Tres redes de seguridad:

1. La **primera página es de 10 filas** (`PAGINA_PRUEBA`): si ninguna se reconoce, el barrido se detiene
   con un error que lista los NOMBRES de los campos recibidos (nunca sus valores) y no se gastan más
   créditos. Ajustar la tabla cuesta una corrección.
2. Un id sin forma de la Ad Library se guarda como `tt:<id>` (los que sí lo son, sin prefijo, para
   deduplicar contra Atria/Apify).
3. Una fila sin id o sin imagen utilizable se descarta.

## 3. Costo

Como Atria, el costo es el cupo del plan (`usd_fuente` = 0); no se registra en `gastos`. El formato
(imagen/video) y «solo activos» **no se mandan** a TrendTrack: se filtran aquí después de recibir la fila
(que ya se pagó), así que se revisan hasta `FACTOR_ESCANEO` = 3 veces los anuncios pedidos y la estimación
lo dice («hasta N créditos… US$ X si fueran de recarga»). `barrido.extra.cursor_atria` guarda el
`offset` ya pagado, así una continuación no vuelve a pagar filas. Sin créditos (402) o con el ritmo agotado
(429 dos veces): entrega parcial con `AVISO_CUOTA_AGOTADA` si ya trajo algo, `ErrorFuente` si no.

Contadores en `kv` y en `/admin/referentes`: `trendtrack_creditos:<AAAA-MM>` (lo gastado desde aquí) y
`trendtrack_saldo` (el `X-Credits-Remaining` de la última llamada medida).

## 4. Activación

`TRENDTRACK_API_KEY` en el `.env` del servidor (tarjeta en Configuración › Puesta a punto, `SETUP.md` §7.4).
Sin ella la fuente queda apagada, igual que Atria. `referente.fuente` guarda `trendtrack` (cabe en los 12
caracteres de la columna; sin migración).

## 5. Pendiente

- Con una llave real: correr `probar()` y una búsqueda de 10 filas, pegar los campos reales en
  `tests/fixtures/trendtrack_ads.json` y ajustar `_CLAVES`. Comprobar que `limit` admite 50.
- Si `POST /v1/ads/query` acepta filtro por página y por tipo de medio: ofrecer «De una marca» y dejar de
  pagar filas que luego se descartan.
