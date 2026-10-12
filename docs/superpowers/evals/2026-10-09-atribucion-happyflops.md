# E0: qué ventana de atribución de Triple Whale cuadra con las ventas reales (happyflops, 2026-10-09)

Medición de solo lectura para el spec `docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md` (E0, R10,
R11). Sin costo: consultas a la base de producción en modo lectura y cinco consultas SQL agregadas a la API de Triple
Whale con la llave de happyflops-norge (la llave nunca se imprimió). Scripts en el scratchpad de la conversación.

## Datos del proyecto en producción

- Triple Whale: UNA tienda, `happyflops-norge.myshopify.com` (NO), moneda del proyecto USD, modelo Triple Attribution,
  ventana `lifetime`. Copia desde el 2026-07-10.
- Meta: 7 cuentas en SEK — Norway (NO), Netherlands (NL), Sweden (SE), Finland (FI), Poland (PL), MX (MX) y World Wide
  (sin país). Días de cuenta desde el 2025-09-09 (MX desde el 2026-03-25, World Wide desde el 2026-05-03); días de
  anuncio desde el 2026-07-12.
- **Cobertura (R5):** la copia de la tienda de Noruega trae anuncios de UNA sola cuenta de Meta, `act_709406360806038`
  (Norway). World Wide y las demás no llegan por esa tienda. El gasto de Meta que ve Triple Whale (136 786 USD en 30
  días) es el de la cuenta de Noruega (1 349 575 SEK ≈ 136 700 USD): el supuesto de PND-149 (8) se cumple aquí.
- Tasas guardadas: solo SEK (USD no la necesita).

## Lo atribuido contra las ventas reales (9 sep – 8 oct 2026, USD)

Ventas reales de la tienda (`tw_tienda_dia`): **385 279** con 158 244 de gasto en publicidad → retorno real **2,43×**.

Lo que hoy copia Creatv (ventana `lifetime`), por canal: facebook-ads 271 444 (con 136 786 de gasto), organic_and_social
193 727 (sin gasto), google-ads 163 949 (con 4 811 de gasto), klaviyo 113 970 (sin gasto), snapchat-ads 61 833 (con
11 369), y 29 canales más sin gasto. Sumar todo daba ~884 000: **2,3 veces** las ventas reales (PND-157).

Con cada ventana (Triple Attribution), mismos días:

| Ventana | Todos los canales | Solo canales con gasto (facebook + google + snapchat) | Contra la tienda | Meta: atribuido / ROAS |
|---|---|---|---|---|
| 1 día | 513 654 | 338 349 | 0,88× | 210 029 / 1,54× |
| **7 días** | 572 863 | **390 710** | **1,01×** | 233 858 / **1,71×** |
| 14 días | 605 812 | 414 420 | 1,08× | 243 671 / 1,78× |
| 28 días | 635 914 | 431 869 | 1,12× | 250 909 / 1,83× |
| lifetime (hoy) | 884 176 | 497 415 | 1,29× | 271 444 / 1,98× |

Meta, por su lado, dice que esos mismos anuncios vendieron 311 559 (ROAS 2,28×, su ventana por defecto).

## Lectura

1. **R9 (solo canales con gasto) quita la mayor parte de lo inflado** sin cambiar ninguna ventana: de 2,3× a 1,29× las
   ventas reales. Lo que sobra con `lifetime` es sobre todo Google (164 000 atribuidos con 4 811 de gasto: búsquedas de
   la marca).
2. **Con 7 días, lo atribuido a los anuncios cuadra con lo que entró a la tienda (1,01×).** Es la ventana recomendada.
3. **Costo de cambiarla (R11, plata):** el ROAS de los anuncios de Meta según Triple Whale baja de 1,98× a 1,71×. El
   decisor de Experimentos usa ese número para los experimentos con atribución Triple Whale; con una meta de ROAS cerca
   de 2×, más anuncios saldrían perdedores y en modo semi o auto se pausarían solos. Hoy happyflops no tiene
   ningún experimento (consulta del 2026-10-09), así que el riesgo inmediato es nulo, pero el cambio afecta a todo
   experimento futuro del proyecto.

## Recomendación para Daniel

Cambiar la ventana de happyflops a **7 días** desde Rendimiento › Ajustes («Modelo y ventana»). Cambiarla borra y
vuelve a copiar 90 días de Triple Whale (unos minutos; los análisis pagados se quedan). El código no la cambia solo
(spec A4).
