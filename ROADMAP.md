# Roadmap de proveedores de generación

Este documento existe para poder explicarle a cualquier persona — un socio, un
inversionista, alguien nuevo en el proyecto — exactamente qué usamos para
generar contenido, por qué, y con qué números reales lo decidimos. No asume
que ya conoces el código: cada pieza técnica se explica en español llano antes
de nombrarla.

Investigado en vivo el 25 ago 2026. Los precios y rankings de estas APIs
cambian cada pocas semanas — antes de una decisión de volumen alto, re-verificar.

## Primero: cómo se conecta la matriz de Laura con la generación real

Esta es la parte que hoy no está clara, así que va primero y sin asumir nada.

Laura mantiene su sistema de marca (Happy Flops, o cualquier marca futura) en
un repositorio aparte: `happyflops-brand-matrix`. Adentro hay un archivo,
`root.json`, con varias piezas distintas. Cada una tiene un destino distinto —
algunas ya se usan de verdad en cada generación, otras todavía no:

| Pieza del `root.json` de Laura | Qué es | ¿Se usa hoy al generar contenido? |
|---|---|---|
| `invariants` (las 11 reglas) | Las leyes que nunca se rompen — luz, color, pies, tipografía, etc. | **Sí.** Se pre-redactan como un solo bloque de texto (`invariant_block`) y se pegan tal cual dentro del prompt que le mandamos a Claude cada vez que alguien escribe una idea. Código: `marca.guia_efectiva()`, usado en `generador_prompts.generar_prompts()`. |
| `prompt_blocks.negative_prompt` | Lista de lo que NUNCA debe aparecer (dedos de más, texto quemado en la imagen, etc.) | **Sí.** Se manda directo al modelo de imagen/video como parámetro `negative_prompt`. Código: `marca.negative_prompt_efectivo()`, usado en `_extra_params_video()`. |
| `free_variables` (momento, escenario, temporada, paleta, formato, cámara, energía...) | El espacio de juego — lo que SÍ debe variar de pieza en pieza | **No todavía.** Hoy están descritas en texto dentro de la matriz, pero no hay código que lea "temporada: invierno" y ajuste algo automáticamente. Falta construir un selector en el panel. |
| `trunk.*` (colecciones de evidencia — ej. `LUZ — trunk collection`, 37 fotos reales analizadas) | Fotos reales que Laura ya evaluó, con el porqué exacto de que funcionen o no | **No todavía.** Esto es lo que llamamos "referencias creativas" en la conversación anterior — la idea es que el sistema le muestre a Claude ejemplos reales al generar, no solo reglas en texto. Diseñado, no construido. |
| `submundos/` (temporadas, colecciones, proyectos que heredan del root y ajustan variables libres) | Una capa que se pone ENCIMA del root para un caso específico | **No todavía.** El mecanismo de herencia existe en el `schema.json` (qué puede y no puede cambiar un submundo), pero el dashboard de iaplusyou no tiene todavía manera de elegir "usa el submundo de Navidad" al generar. |
| `open_items` (lo que le falta a la matriz — reference pack, colourway hex, etc.) | Su lista de pendientes | Es informativo — se muestra en el panel de iaplusyou ("Lo que le falta a esta matriz") para que quien genere contenido sepa qué tan completa está la marca hoy. No bloquea la generación. |

**En una frase**: hoy, cada pieza de contenido que generamos SÍ respeta las 11
reglas invariables de Laura al 100% (eso es mecánico, no depende de que Claude
"se acuerde") — pero todavía NO aprovechamos las variables libres, las
referencias reales del trunk, ni los submundos. Ese es el trabajo que sigue
después de este roadmap.

## ¿Qué es `providers/image_provider.py`?

No existe todavía — es un archivo nuevo que vamos a crear. Hoy, todo el código
de generación de imagen le habla directo a un solo proveedor (Higgsfield). La
idea de `image_provider.py` es ponerle una capa en el medio: en vez de que el
resto del programa sepa "hablar Higgsfield", solo pide "genérame una imagen" y
esa capa decide, según lo que se elija, si se la pide a Higgsfield o a otro
proveedor (ej. Nano Banana). Así se puede agregar o quitar proveedores sin
tener que reescribir todo el pipeline cada vez.

## Criterio de decisión

En este orden: **(1) calidad real del resultado, (2) que tenga API programable
de verdad (no solo interfaz web que hay que operar a mano), (3) confiabilidad
del proveedor.** El precio es desempate, no el filtro principal — pero cuando
dos opciones empatan en calidad, gana la más barata.

## Comparación: precio + calidad, con fuente

| Uso | Proveedor | Costo real (por imagen / por 5s de video) | Posición en rankings de calidad (Artificial Analysis, ago 2026) |
|---|---|---|---|
| Imagen | **Nano Banana** (Gemini 2.5/3.1 Flash Image, directo) | **$0.039/imagen** (la variante más nueva, Nano Banana 2 Lite: $0.034) | No es el #1 absoluto (GPT Image 2 lidera con 1,370 Elo) pero está entre los más usados en 2026 por su fuerza específica en consistencia de personaje/edición — justo lo que necesitamos para mantener el mismo personaje entre escenas |
| Imagen | Higgsfield (soul/reference, el que ya usamos) | ~$0.065–0.075/imagen | No está en el ranking directo (es una capa sobre otros modelos), pero ya probado en producción con nuestros personajes reales |
| Video | **Higgsfield (kling-2.1-pro, el que ya usamos)** | **$0.49** (5s — cotización real de nuestra propia app vía el `/estimate` de Higgsfield, no un blog) | Kling 3.0 tiene 4 entradas en el top 10 del ranking — buena calidad, ya probado, y resulta ser lo más barato de esta lista |
| Video | Kling directo (revendedores fal.ai/Atlas/EvoLink) | ~$0.38–0.57 (5s) | Misma calidad que arriba (mismo modelo) — pero **más caro que quedarse en Higgsfield** |
| Video | Seedance 2.0 vía fal.ai directo (precio real de su página oficial, 27 ago 2026) | **~$2.31** (5s, 720p con audio, ~$0.46-0.47/s) | #1 en video-con-audio en Artificial Analysis. Es caro comparado con quedarse en Higgsfield (ver fila siguiente) — para Seedance, ir "directo" NO es más barato. |
| Video | Seedance 2.0 **vía Higgsfield** (precio real de higgsfield.ai/blog, 29 ago 2026 — no de un agregador de terceros) | **~$0.75–0.97** normalizado a 5s (Fast: 28cr/8s=$1.20; Standard: 36cr/8s=$1.55) | Mismo modelo, **más barato que fal.ai directo con los dos precios verificados en la fuente oficial**. Pendiente confirmar si el endpoint de desarrollador (`platform.higgsfield.ai`, el que ya usa `higgsfield_client.py`) expone Seedance — estos precios son de la app de consumo, no necesariamente de la API. |
| Video (premium) | Veo 3.1 (Google, directo) | $0.75 (Fast) – $2.00 (Standard) | #3 en el ranking con audio — motor propio de Google con audio nativo, ligeramente más barato que Seedance directo al precio real |

**Magnific** no es un generador — es un upscaler/mejorador (~$0.08–0.16 por
imagen en 2K/4K). Es un paso opcional de post-proceso sobre algo ya generado,
no compite por el rol de "proveedor base".

**ComfyUI** (self-hosted, corre en tu propia GPU o una rentada) solo compensa
a partir de volumen real — la comparación de mercado dice que empieza a valer
la pena entre 1,000 y 50,000 imágenes al mes. A nuestro volumen de hoy, tener
GPU propia agrega complejidad operativa sin ahorro neto.

## Proyección de costo por volumen (números reales, no estimados)

Para que el impacto se sienta en pesos y no en abstracto — 3 escenarios:

**Imagen** (por pieza: Nano Banana $0.039 vs. Higgsfield ~$0.07):

| Volumen mensual | Nano Banana | Higgsfield (actual) | Diferencia |
|---|---|---|---|
| 20 imágenes (fase de prueba) | $0.78 | $1.30 | $0.52 |
| 200 imágenes (operación real) | $7.80 | $13.00 | $5.20 |
| 1,000 imágenes (escala) | $39.00 | $130.00 | $91.00 |

**Video** (por pieza de 5s, precios reales verificados: Higgsfield/Kling $0.49 —cotización real de nuestra app— vs. Veo Fast $0.75 vs. Seedance directo ~$2.31):

| Volumen mensual | Higgsfield/Kling (actual) | Seedance vía Higgsfield | Veo 3.1 Fast (premium) | Seedance vía fal.ai directo |
|---|---|---|---|---|
| 20 videos (fase de prueba) | $9.80 | $15.00–19.40 | $15.00 | $46.20 |
| 200 videos (operación real) | $98.00 | $150.00–194.00 | $150.00 | $462.00 |
| 1,000 videos (escala) | $490.00 | $750.00–970.00 | $750.00 | $2,310.00 |

A 1,000 videos/mes, ir directo a fal.ai por Seedance sale entre **$1,340 y
$1,560 más caro al mes** que pedirlo a través de Higgsfield. Para video, hoy
no hay razón de costo para salir de Higgsfield en ningún caso — ni para Kling
ni para Seedance.

## Casos de uso concretos

No se trata de elegir UN proveedor para todo — se trata de elegir según qué
está en juego en esa pieza específica:

- **Contenido diario, alto volumen, bajo riesgo** (posts de rutina, pruebas
  de idea, contenido de relleno del calendario): Nano Banana para imagen +
  Higgsfield/Kling para video. Con el precio real verificado, Seedance dejó
  de ser la opción barata para este caso — Higgsfield sigue siendo lo más
  económico en video hoy.
- **Personaje recurrente que debe verse igual siempre** (mascota de marca,
  vocero): Nano Banana para la imagen base — es específicamente fuerte en
  mantener identidad/consistencia entre generaciones, más que Higgsfield.
- **Video insignia** (lanzamiento de producto, campaña principal, algo que va
  a pagarse en pauta): Veo 3.1 Standard — el costo por pieza deja de importar
  cuando es una sola pieza cara bien hecha, no miles baratas.
- **Cualquier cosa hoy mismo, sin construir nada nuevo**: Higgsfield —ya
  integrado, ya probado, con `estimate_video`/`estimate_image` antes de gastar.
  No hay que esperar a que se conecten los proveedores nuevos para seguir
  generando contenido real.

## Decisión

1. **Imagen: agregar Nano Banana como segundo proveedor**, sin quitar
   Higgsfield — se elige por idea/proyecto vía `providers/image_provider.py`
   (nuevo, explicado arriba).
2. **Video: Higgsfield/Kling sigue siendo la base y el default** — $0.49 el
   video de 5s, cotizado en vivo por Higgsfield. Es la opción más barata de
   las que ya funcionan hoy.
3. **Seedance: preferir pedirlo A TRAVÉS de Higgsfield, no directo por fal.ai**
   — con precios oficiales de ambos lados (29 ago 2026), Higgsfield sale más
   barato (~$0.75-0.97 el 5s equivalente, contra ~$2.31 directo).
   **Confirmado en vivo (29 ago 2026)**: el endpoint
   `/bytedance/seedance-2.0/image-to-video` SÍ existe en
   `platform.higgsfield.ai` (la API de desarrollador que ya usamos) — pero
   responde `503 model_disabled`, es decir, está apagado para nuestra
   cuenta/plan actual. Falta pedirle a Higgsfield que lo habilite (o subir de
   plan). `providers/seedance_client.py` (vía fal.ai) queda como respaldo
   funcional mientras tanto, pero no es el default por precio.
3. **Veo 3.1 queda documentado, no conectado todavía** — es la opción
   "calidad máxima, no importa el costo" para cuando una pieza puntual lo
   amerite, no para generación masiva.
4. **Magnific y ComfyUI quedan fuera del alcance actual**, explícitamente, con
   la razón escrita acá — no es que se nos olvidaron, es que no se justifican
   todavía a este volumen.
5. **Las variables libres, el trunk y los submundos de la matriz de Laura
   siguen sin conectarse a la generación real** — hoy solo las 11 reglas
   invariables y el negative_prompt están mecánicamente aplicados. Conectar
   el resto es trabajo aparte, no parte de este roadmap de proveedores.

## Próximos pasos (implementación)

Esto alimenta directo el spec pendiente: `providers/image_provider.py` +
`providers/nano_banana_client.py`, y el mismo patrón para
`providers/video_provider.py` + `providers/seedance_client.py`. El panel
"Avanzado" opcional para elegir proveedor sigue el mismo diseño ya acordado —
flujo simple por defecto, nadie tiene que tocar nada si no quiere.
