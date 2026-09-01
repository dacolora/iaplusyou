# Diseño: generación imagen-primero, multi-proveedor, con combinaciones

Fecha: 2026-08-27
Estado: pendiente de revisión del usuario

## Por qué

Hoy el pipeline es: idea → 5 prompts de VIDEO (texto) → aprobar 1 → imagen
candidata (Higgsfield) → aprobar → video. El problema: se elige un prompt de
texto (cámara, movimiento, narrativa) antes de haber visto ninguna imagen real
— como diseñar el guion antes de ver el storyboard.

Se decidió invertir el orden: ver primero varias direcciones visuales reales
(imágenes), elegir la(s) que mejor se vea(n), y solo ahí decidir cómo animarla.
Además, se agrega la posibilidad de elegir proveedor de imagen (Higgsfield o
Nano Banana) y de probar varias combinaciones imagen×animación antes de
comprometerse a un video final.

Contexto de decisiones previas relevantes:
- [ROADMAP.md](../../../ROADMAP.md) — por qué Nano Banana para imagen, y qué
  proveedores quedan fuera de alcance (Seedance/Veo quedan documentados, no
  conectados en este spec — solo aplica a IMAGEN, video sigue en
  Higgsfield/Kling sin cambios).
- El `invariant_block`/`negative_prompt` no se tocan en este trabajo — siguen
  viniendo tal cual de `root.json` vía `marca.guia_efectiva()` /
  `marca.negative_prompt_efectivo()`, sin cambios.

## Flujo nuevo, completo

```
idea (texto) + cantidad (3/5/10) + proveedor de imagen (Higgsfield | Nano Banana)
  → N conceptos de imagen (texto corto vía Claude, gratis — usa invariant_block)
  → las N imágenes se generan automáticamente con el proveedor elegido (sin
    aprobación individual previa — el gasto de las N ya fue aceptado al elegir
    cantidad+proveedor)
  → el usuario aprueba 0..N de esas imágenes (puede aprobar varias, no solo 1)
  → por CADA imagen aprobada: 5 propuestas de animación (texto vía Claude,
    gratis, igual que el generador de prompts que ya existe hoy)
  → el usuario aprueba 0..5 propuestas de animación por imagen (puede probar
    varias combinaciones de la misma imagen)
  → CADA combinación aprobada (imagen + animación) genera un VIDEO directo
    (Higgsfield/kling-2.1-pro, sin paso intermedio de "imagen candidata" — la
    imagen ya quedó fija en el paso anterior)
  → los videos entran a estado_videos.json exactamente como hoy → aprobación
    final → publicación (sin cambios en este tramo)
```

## Qué es nuevo vs. qué se reutiliza sin tocar

**Reutilizado tal cual:**
- `generador_prompts.generar_prompts()` — ya genera 5 propuestas de animación
  de texto para una imagen dada. Se reutiliza exactamente igual, solo que
  ahora se dispara por cada imagen aprobada en vez de una vez por idea.
- Generación de video (Higgsfield/kling-2.1-pro), aprobación final,
  publicación, `estado_videos.json`, `bitacora.py`, `trabajos.py` — nada de
  esto cambia.
- `marca.guia_efectiva()` / `marca.negative_prompt_efectivo()` — se siguen
  usando igual, tanto para generar conceptos de imagen como animaciones.

**Nuevo:**
1. `generador_prompts.generar_conceptos_imagen(idea, n, guia_estilo)` — nueva
   función. A diferencia de `generar_prompts()` (que describe movimiento de
   cámara para VIDEO), esta describe escenas fijas para IMAGEN — sin lenguaje
   de cámara/animación.
2. `providers/image_provider.py` — capa única de generación de imagen. Recibe
   `(proveedor, referencia, prompt, params)` y decide internamente si llama a
   Higgsfield (como hoy: lanzar → poll → extraer) o a Nano Banana (llamada
   directa, sin polling). El resto del código nunca habla con Higgsfield o
   Nano Banana directamente, solo con esta capa.
3. `providers/nano_banana_client.py` — cliente nuevo para Gemini 2.5 Flash
   Image. Necesita `GEMINI_API_KEY` en `.env` (ya la tiene el usuario, pendiente
   agregarla al archivo). Costo: ~$0.039/imagen, se muestra en USD directo, no
   en créditos (a diferencia de Higgsfield).
4. `conceptos_imagen.py` — nuevo módulo de estado, mismo patrón que
   `prompts.py` (un JSON por cliente:
   `clientes/<cliente>/conceptos_pendientes.json`). Estructura:
   ```json
   {
     "idea_20260827_140000_mi_idea": {
       "idea": "texto original",
       "creado_en": "...",
       "proveedor_imagen": "nano_banana",
       "cantidad": 5,
       "conceptos": {
         "concepto_1": {
           "texto": "descripción corta de la escena",
           "estado": "generando | listo | error | aprobado | descartado",
           "imagen_url": null,
           "imagen_local": null,
           "animaciones": {
             "anim_1": { "prompt": "...", "estado": "pendiente", ... }
           }
         }
       }
     }
   }
   ```
   Cada entrada de `animaciones` tiene la misma forma que un prompt de
   `prompts_pendientes.json` hoy, para poder reusar `_prompt_row.html` y la
   ruta de generación de video sin reescribirlas.
5. Rutas nuevas en `dashboard.py`:
   - `POST /cliente/<cliente>/idea/nueva_visual` — recibe idea+cantidad+
     proveedor, genera los N conceptos, lanza las N generaciones de imagen en
     background (`trabajos.iniciar` por cada una, mismo patrón de barra de
     progreso que ya existe).
   - `POST /cliente/<cliente>/concepto/<concepto_id>/aprobar` — marca la
     imagen como aprobada, dispara `generar_prompts()` para esa imagen
     específica, guarda las 5 animaciones bajo ese concepto.
   - `POST /cliente/<cliente>/concepto/<concepto_id>/descartar` — descarta una
     imagen no elegida.
   - `POST /cliente/<cliente>/concepto/<concepto_id>/animacion/<anim_id>/guardar`
     — edita el texto de una propuesta de animación antes de generar.
   - `POST /cliente/<cliente>/concepto/<concepto_id>/animacion/<anim_id>/descartar`
     — descarta una propuesta de animación no elegida.
   - `POST /cliente/<cliente>/concepto/<concepto_id>/animacion/<anim_id>/generar_video`
     — genera el video directo (imagen ya fija + esa animación), lo mueve a
     `estado_videos.json`. Reutiliza la lógica de generación de video que ya
     existe en `aprobar_imagen`, adaptada para no requerir el paso de "imagen
     candidata" (ya no aplica en este flujo).
6. Templates nuevos: `_concepto_card.html` (muestra las N imágenes generadas
   en una grilla, con aprobar/descartar por imagen) y `_animacion_row.html`
   — parecido a `_prompt_row.html` pero más simple (no necesita selector de
   modelo ni aspect ratio, esos ya quedaron fijos al generar la imagen): texto
   editable + botón "Generar video" (dispara el video directo) + descartar.
   Apunta a las rutas nuevas de animación, no a las de `prompts_mod`.
7. El formulario "Nueva idea" de Happy Flops se **reemplaza** por este flujo
   nuevo (cantidad + proveedor visibles siempre como parte del formulario
   principal — no hace falta abrir nada extra para elegirlos, son solo dos
   selects). El resto de parámetros avanzados que ya existían (cfg_scale,
   duration) sí quedan detrás de un colapsable opcional, con los valores de
   hoy como default. Forja sigue con el formulario viejo intacto — no se toca
   nada de su flujo.

## Qué NO cambia / queda fuera de este spec

- El flujo viejo (`nueva_idea`, `prompts_pendientes.json` tal como está hoy)
  **no se borra** — Forja y cualquier cliente futuro sin este flujo nuevo
  siguen funcionando exactamente igual. Este spec es aditivo.
- Video sigue siendo solo Higgsfield/kling-2.1-pro. Seedance/Veo quedan
  documentados en el roadmap, no se conectan aquí.
- Variables libres, trunk (LUZ), submundos de la matriz — siguen sin
  conectarse a la generación (ver ROADMAP.md). Fuera de alcance.
- QA automático post-generación contra los 11 invariantes (mencionado como
  idea al hablar de "camisa de fuerza") — no está en este spec, queda anotado
  como mejora futura si se pide explícitamente.

## Errores y casos borde

- Si una de las N generaciones de imagen falla (proveedor caído, contenido
  bloqueado, etc.), las otras N-1 siguen su curso normal — no se bloquea el
  lote completo por una falla individual. El concepto fallido se muestra con
  su error, se puede reintentar o descartar.
- Si el usuario no aprueba ninguna imagen de las N, la idea queda "abierta"
  sin generar nada más — igual que hoy cuando se descartan todos los prompts.
- Nano Banana no tiene `negative_prompt` como parámetro nativo de la misma
  forma que Higgsfield/kling — `image_provider.py` debe manejar esa diferencia
  (incluirlo en el prompt principal si el proveedor no soporta el parámetro
  separado, documentado en el propio cliente de Nano Banana).

## Testing

- Generar una idea real con Nano Banana y cantidad=3, confirmar que las 3
  imágenes se generan y muestran correctamente, con costo en USD (no créditos).
- Aprobar 2 de las 3 imágenes, confirmar que cada una recibe sus propias 5
  animaciones independientes.
- Aprobar 1 animación de cada imagen aprobada, confirmar que se generan 2
  videos independientes, cada uno con la imagen correcta.
- Confirmar que Forja (sin este flujo activado) sigue funcionando exactamente
  como antes.
