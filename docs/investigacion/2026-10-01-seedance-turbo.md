# Seedance 2.5 Turbo en WaveSpeed (2026-10-01)

**Pregunta:** ¿podemos pasar Seedance 2.5 de Crear a su acceso Turbo, que es más barato, sin perder
calidad?

**Respuesta corta:** el precio y los parámetros cuadran, pero la calidad nadie la ha medido.
`comparar_seedance_turbo.py` regenera con Turbo dos o tres piezas que ya existen para verlas lado a lado
antes de decidir.

## Qué se pudo verificar

Desde la sesión de esta investigación wavespeed.ai estaba bloqueado. No hay ninguna página de WaveSpeed
vista directamente. Todo sale de código público que llama a WaveSpeed, de una copia de su catálogo y de
su esquema de entrada, y de una auditoría de precios del 2026-09-13.

| | Seedance 2.5 (hoy) | Seedance 2.5 Turbo |
|---|---|---|
| Ruta con imagen | `bytedance/seedance-2.5/image-to-video` | `bytedance/seedance-2.5/image-to-video-turbo` |
| Ruta solo texto | `bytedance/seedance-2.5/text-to-video` | `bytedance/seedance-2.5/text-to-video-turbo` |
| 720p | US$ 0,36/s | **US$ 0,20/s** (44 % menos) |
| 1080p | US$ 0,90/s (sin verificar) | ~US$ 0,21/s (sin verificar) |
| 480p | US$ 0,18/s | no existe |
| Parámetros con imagen | `prompt`, `image`, `last_image`, `duration` 4–30, `resolution`, `generate_audio` | los mismos; `resolution` solo 720p/1080p |

Crear siempre pide 720p a Seedance, así que el pedido de hoy sirve tal cual con la ruta Turbo.

**Fuentes:**

- Rutas: aparecen en varios repos que las usan, como `eRepublik-Labs/comfyui-nodes-erpk`,
  `bruetsch-dev/ShortsLab`, `pina753753-star/seedance-black-studio` y `seedsat1/saad-studio`, y en el
  catálogo copiado en `dvaJi/infera`.
- Precios de 720p: `manavpthaker/operator-economy` (auditoría del 2026-09-13) y el `STATUS.md` de
  `seedance-black-studio`, que dice haberlos revisado en la especificación oficial el 2026-08-30.
- Esquema de entrada: copia en `PurpleDoubleD/locally-uncensored`.

## Qué falta

- **Calidad.** Lo único que dice WaveSpeed, según la copia de su catálogo, es «a faster, more affordable
  high-resolution tier». No dice qué se pierde ni si es otro modelo. Para eso es el script.
- **Precio real.** No está confirmado si `generate_audio` cambia el precio. Tampoco si hay una promoción
  del 10 %: un cobro real de Turbo de US$ 2,835 por 15 s a 1080p con sonido sale de 15 × 0,21 × 0,9.
  Después de la comparación hay que cotejar lo anotado en `gasto` con la facturación de WaveSpeed.
- **Formatos de Turbo solo texto.** No está verificada la lista exacta de `aspect_ratio`, aunque los cinco
  que usamos aparecen en todas las fuentes.

## Cómo comparar (en el VPS)

```bash
venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops            # lista, gratis
venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops --cf A --cf B   # total, gratis
venv/bin/python3 comparar_seedance_turbo.py --cliente happyflops --cf A --cf B --generar
```

El último comando pide escribir «si» antes de cobrar. Usa las mismas entradas que preparó el worker
(`tareas.flowplus._preparar`). El gasto queda anotado como `video`, con la referencia
`turbo:<cf_id>:<marca>`. La página que muestra los dos videos lado a lado queda en R2, en
`clientes/<c>/comparaciones/seedance_turbo/<marca>/index.html`.

Conviene elegir una pieza con persona y producto (caras, manos, el producto de cerca) y una con mucho
movimiento.

## Si la calidad aguanta

El cambio son las rutas y el precio de `seedance25` en `providers/flowplus_modelos.py::VIDEO`: `path`,
`path_texto` y `usd_por_segundo`, más la `nota`. Recrear, el compositor y el gasto ya leen de ahí. Las
piezas que siguen esperando en WaveSpeed se recuperan por su id, así que no les afecta.
