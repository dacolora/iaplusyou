# Prueba real: Seedance 2.5 con varias referencias vía fal (2026-10-09)

Pedido de Daniel: «en Higgsfield Seedance acepta más de 3 imágenes y en el nuestro solo una». WaveSpeed solo tiene la
imagen-a-video de Seedance 2.5 (`image` + `last_image`); su reference-to-video no existe (404 ese día). El modelo nuevo
`seedance25_ref` va a `bytedance/seedance-2.5/reference-to-video` en fal (`providers/fal_video.py`). Daniel aprobó una
prueba real de ≈ US$ 1,89 antes de desplegar.

## Lo que se corrió

Mismo camino que Crear: `flowplus_prompt.asignar_tokens` + `tal_cual` + `flowplus_modelos.generar_video("seedance25_ref", …)`,
4 s, 9:16, 720p, con sonido. Referencias públicas de picsum.photos (sin datos de clientes).

| intento | referencias | resultado | cobro |
|---|---|---|---|
| 1 (`01a122bc-d7a2-74a1-ad7c-d93a2bcf468d`) | retrato de una mujer real, zapatos blancos, castillo | **422** tras 104 s: «The images or videos provided may contain likenesses of real people or other private information that cannot be processed.» | fal no cobra un pedido que termina en error (su política); no se pudo ver en la factura: la llave de Creatv no tiene permiso para la API de uso (403) |
| 2 | cachorro negro, zapatos blancos, castillo | video en 179 s: 720×1280, 24 fps, 4,09 s, h264 + aac (con sonido); las TRES referencias aparecen (el cachorro olfatea los zapatos con el castillo al fondo) | ≈ US$ 1,89 (estimado de la app: 4 × 0,473); falta verlo en la factura de fal |

Prompt del intento 2, tal cual llegó a fal: `El cachorro de @Image1 encuentra los zapatos blancos de @Image2 sobre un
sendero de piedra y los olfatea moviendo la cola; al fondo se ve el castillo de @Image3. La cámara baja hasta un primer
plano de los zapatos.` + `SONIDO: olfateo, patitas sobre piedra y viento suave.`

## Lo que destapó (y ya está arreglado)

1. **Las URLs de estado y resultado**: con la ruta completa (`bytedance/seedance-2.5/reference-to-video/requests/<id>/status`),
   que es como las escribe el OpenAPI de fal, el estado responde **405**. Funcionan por la app
   (`bytedance/seedance-2.5/requests/<id>/status`), que es lo que fal devuelve en `status_url`/`response_url`. El estado
   en curso responde 202; el resultado pedido antes de tiempo, 400 «Request is still in progress». Arreglado en
   `fal_video._base`. Con el error de antes, el pedido pagado no se habría perdido (el 405 es un error de red: la sesión
   guarda el id y sigue esperando), pero tampoco se habría podido traer.
2. **Personas reales**: ByteDance rechaza referencias que parecen fotos de personas reales. La tarjeta lo explica en
   palabras (`tareas/flowplus._mensaje_error`) y la nota del modelo lo avisa antes de pagar: los personajes tienen que
   ser creados con IA.
3. «Recuperar el video» (`flowplus_modelos.esperar_fal`) trajo el mismo video del intento 2 por su id, sin volver a lanzar.

## Lo que falta (PND-209)

- Ver en la factura de fal que el intento 2 costó ≈ US$ 1,89 y el 1 nada (hace falta una llave de administrador o el
  panel de fal).
- Medir un 4:3 o 3:4 (fuera del selector hasta saberlo) y uno de solo texto.
