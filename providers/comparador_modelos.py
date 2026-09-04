"""
Candidatos de edición de imagen/video que SÍ ven la foto de referencia del
producto (no solo una descripción en texto) — el requisito no negociable para
"cambiar calzado": clonar la foto/video original exacto y solo reemplazar el
calzado. Todos llamados vía fal.ai con la misma FAL_KEY.

Kling O1 (el candidato de video ya en producción) vive aparte en
kling_o1_client.py y no se duplica aquí.

Se descartaron Flux Kontext Pro (fal-ai/flux-pro/kontext) y Gemini Omni Flash
edit (google/gemini-omni-flash/v1.1/edit): ambos solo aceptan una imagen de
entrada (la foto a editar) sin poder ver una segunda imagen de referencia del
producto — el color/diseño del calzado se les tendría que describir en texto,
que es justo lo que no queremos para este flujo.

También se evaluó Seedance (bytedance/seedance-2.0 y 2.5, endpoint
reference-to-video) y se descartó: su esquema NO tiene un campo "video a
editar" — `video_urls`/`image_urls` son todas referencias del mismo nivel que
alimentan una generación nueva guiada por el prompt (como Higgsfield Soul),
no una edición que preserve un video base pixel a pixel. Mismo problema de
fondo aunque su marketing lo llame "editing".

Esquemas verificados contra la documentación oficial de cada modelo en
fal.ai (31 ago 2026) — si algo falla, vuelve a verificar ahí antes de asumir
que el código está mal:
  - Nano Banana (fal-ai/nano-banana/edit): campo `image_urls` (lista) + `prompt`.
  - Qwen Image Edit Plus (fal-ai/qwen-image-edit-plus): `image_urls` (lista) + `prompt`.
  - Luma Ray3 Modify (fal-ai/luma-dream-machine/ray-2/modify): `video_url` +
    `prompt` + `mode`, y un `image_url` opcional (uno solo, no lista).
  - Wan-2.2 Animate Replace (fal-ai/wan/v2.2-14b/animate/replace): `video_url`
    (el video a editar) + `image_url` (una sola imagen de referencia — el
    producto/personaje que reemplaza lo original). Sin campo de prompt: el
    modelo lo genera solo, está hecho específicamente para "reemplaza esto
    por esto otro" en un video real.
"""
from providers import aspect_ratio, fal_client

MODELOS_IMAGEN = {
    "nano_banana_fal": {
        "path": "fal-ai/nano-banana/edit",
        "nombre": "Nano Banana (vía fal)",
        "costo_usd": 0.039,
    },
    "qwen_edit": {
        "path": "fal-ai/qwen-image-edit-plus",
        "nombre": "Qwen Image Edit Plus",
        "costo_usd": 0.03,
    },
}

MODELOS_VIDEO = {
    "luma_modify": {
        "path": "fal-ai/luma-dream-machine/ray-2/modify",
        "nombre": "Luma Ray3 Modify",
        "costo_usd_por_segundo": 0.35,
    },
    "wan_animate_replace": {
        "path": "fal-ai/wan/v2.2-14b/animate/replace",
        "nombre": "Wan-2.2 Animate Replace",
        "costo_usd_por_segundo": 0.04,  # 480p (default); 720p sube a $0.08/seg
    },
}


PROMPT_EDICION_IMAGEN = """Esto es una EDICIÓN de foto, no la creación de una foto nueva. \
Parte de la primera imagen tal cual existe, píxel por píxel, y edítala.

La ÚNICA edición permitida: localiza el calzado que lleva puesta CADA persona \
que aparezca en la foto — si hay varias, se reemplaza el de TODAS, ninguna se \
queda con el original — y reemplázalo por {descripcion_producto} (mostrado en \
la(s) imagen(es) de referencia siguientes). Bórralo por completo en cada una, \
incluyendo cualquier media o parte del calzado original que quede asomada — no \
debe quedar ningún resto visible debajo o alrededor del calzado nuevo en \
ninguna persona.

El calzado nuevo debe medir exactamente lo mismo que medía el original de cada \
persona en esa foto — ni más grande, ni más ancho — nunca debe sobresalir del \
contorno natural de ningún pie.

No cambies nada más: mismas personas, mismos rostros, mismos cuerpos, misma \
ropa, misma pose, mismo fondo, misma luz, mismo encuadre exactos."""


def editar_imagen(modelo_id, foto_url, descripcion_producto, referencias_urls,
                  foto_local_path=None, on_progreso=None):
    """Edita foto_url reemplazando el calzado por el producto mostrado en
    referencias_urls, con el modelo_id indicado (ver MODELOS_IMAGEN). Si se pasa
    foto_local_path, se detecta el encuadre real de esa foto y se le pide al
    modelo que lo respete (si no, cada uno elige su propio encuadre por default
    y el resultado sale recortado respecto al original). Devuelve la URL
    pública de la imagen resultante. on_progreso se propaga a la cola de fal.ai
    (ver fal_client.llamar) para poder mostrar en qué fase va."""
    info = MODELOS_IMAGEN[modelo_id]
    prompt = PROMPT_EDICION_IMAGEN.format(descripcion_producto=descripcion_producto)
    payload = {"prompt": prompt, "image_urls": [foto_url] + referencias_urls[:2]}

    if foto_local_path:
        if modelo_id == "nano_banana_fal":
            payload["aspect_ratio"] = aspect_ratio.detectar_fal_nano_banana(foto_local_path)
        elif modelo_id == "qwen_edit":
            ancho, alto = aspect_ratio.dimensiones_para_qwen(foto_local_path)
            payload["image_size"] = {"width": ancho, "height": alto}

    data = fal_client.llamar(info["path"], payload, on_progreso=on_progreso)
    imagenes_resultado = data.get("images") or []
    if not imagenes_resultado:
        raise RuntimeError(f"{info['nombre']} no devolvió ninguna imagen: {data}")
    return imagenes_resultado[0]["url"]


def editar_video(modelo_id, video_url, descripcion_producto, referencia_imagen_url, on_progreso=None):
    """Edita video_url reemplazando el calzado por el producto mostrado en
    referencia_imagen_url, con el modelo_id indicado (ver MODELOS_VIDEO).
    Devuelve la URL pública del video resultante. on_progreso se propaga a la
    cola de fal.ai (ver fal_client.llamar)."""
    info = MODELOS_VIDEO[modelo_id]

    if modelo_id == "wan_animate_replace":
        # Sin campo de prompt en este modelo — solo video a editar + referencia.
        payload = {"video_url": video_url, "image_url": referencia_imagen_url}
    else:
        prompt = (
            f"Reemplaza el calzado que lleva puesta CADA persona del video (si hay "
            f"varias, el de TODAS, ninguna se queda con el original) por "
            f"{descripcion_producto} (mostrado en la imagen de referencia). No cambies "
            f"nada más: mismo movimiento, mismas personas, mismo fondo, misma "
            f"iluminación, mismo encuadre."
        )
        payload = {"video_url": video_url, "prompt": prompt, "mode": "adhere_2", "image_url": referencia_imagen_url}

    data = fal_client.llamar(info["path"], payload, on_progreso=on_progreso)
    video = data.get("video") or {}
    url = video.get("url")
    if not url:
        raise RuntimeError(f"{info['nombre']} no devolvió una URL de video: {data}")
    return url


def estimate_image(modelo_id):
    return {"credits": None, "usd": MODELOS_IMAGEN[modelo_id]["costo_usd"]}


def estimate_video(modelo_id, duration_seconds=5):
    costo_seg = MODELOS_VIDEO[modelo_id]["costo_usd_por_segundo"]
    return {"credits": None, "usd": round(costo_seg * duration_seconds, 3) if costo_seg else None}
