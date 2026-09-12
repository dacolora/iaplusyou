"""
Modelos de FlowPlus (referencias + texto -> video nuevo, o -> imagen nueva),
todos vía WaveSpeed. Una sola tabla decide qué se puede elegir en la pestaña y
en FlowSettings; agregar un modelo es agregar una entrada acá.

Rutas y precios verificados en wavespeed.ai/models/* el 2026-09-12:
  - alibaba/wan-3.0/reference-to-video        hasta 10 imágenes · 0.10 $/s a 720p
  - kwaivgi/kling-video-o3-pro/reference-to-video  hasta 7 imágenes · 0.112 $/s
  - bytedance/seedance-2.5/image-to-video     1 imagen de arranque · 0.36 $/s a 720p
  - bytedance/seedream-v5.0-pro/edit          imagen (ya integrado en wavespeed_imagen)

"Wan Clone" no existe en WaveSpeed (ni en fal/Replicate/Higgsfield) a esta
fecha: cuando aparezca se agrega como una entrada más.
"""
import requests

from providers import wavespeed_common, wan3_client, wavespeed_imagen

VIDEO = {
    "wan3": {
        "nombre": "Wan 3.0",
        "path": wan3_client.MODEL_PATH,
        "max_referencias": 10,
        "usd_por_segundo": wan3_client.COSTO_USD_POR_SEGUNDO["720p"],
        "duraciones": (5, 8, 10, 12, 15, 20),
        "nota": "Hasta 10 referencias, 720p. El que mejor respeta varias imágenes a la vez.",
    },
    "kling_o3_pro": {
        "nombre": "Kling O3 Pro",
        "path": "kwaivgi/kling-video-o3-pro/reference-to-video",
        "max_referencias": 7,
        "usd_por_segundo": 0.112,
        "duraciones": (5, 8, 10, 12, 15),
        "nota": "Hasta 7 referencias. Movimiento y realismo de personas muy buenos.",
    },
    "seedance25": {
        "nombre": "Seedance 2.5",
        "path": "bytedance/seedance-2.5/image-to-video",
        "max_referencias": 1,
        "usd_por_segundo": 0.36,
        "duraciones": (5, 8, 10, 12, 15),
        "nota": "Usa SOLO la primera imagen como fotograma de arranque; el encuadre sale de esa imagen. Calidad cinematográfica, el más caro.",
    },
}

IMAGEN = {
    "seedream_v5_pro": {
        "nombre": "Seedream V5.0 Pro",
        "path": wavespeed_imagen.MODELO_SEEDREAM,
        "max_referencias": wavespeed_imagen.MAX_IMAGENES_SEEDREAM,
        "usd": wavespeed_imagen.COSTO_USD_SEEDREAM["2k"],
        "nota": "Imagen 2k a partir de tus referencias y el texto. Realismo fotográfico.",
    },
}

VIDEO_POR_DEFECTO = "wan3"
IMAGEN_POR_DEFECTO = "seedream_v5_pro"


def estimate_video(modelo_id, duration):
    info = VIDEO[modelo_id]
    return {"credits": None, "usd": round(info["usd_por_segundo"] * duration, 3)}


def estimate_imagen(modelo_id, n_referencias=1):
    info = IMAGEN[modelo_id]
    return wavespeed_imagen.estimate_seedream(resolution="2k", n_imagenes=max(1, n_referencias))


def _lanzar(path, payload, nombre, timeout_seconds=1200, on_progreso=None):
    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{path}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({path}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")
    resultado = wavespeed_common.poll_hasta_listo(
        prediction_id, nombre, timeout_seconds=timeout_seconds, on_progreso=on_progreso,
    )
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"{nombre} no devolvió ninguna salida: {resultado}")
    return outputs[0]


def generar_video(modelo_id, prompt, referencias, duration, aspect_ratio="9:16", on_progreso=None):
    """Devuelve la URL pública del video. referencias: URLs públicas, la primera
    es la principal (Seedance solo usa esa)."""
    info = VIDEO[modelo_id]
    if not referencias:
        raise ValueError(f"{info['nombre']} necesita al menos una imagen de referencia.")
    refs = list(referencias)[: info["max_referencias"]]
    if modelo_id == "wan3":
        return wan3_client.generar_video(
            prompt, refs, duration=duration, resolution="720p",
            aspect_ratio=aspect_ratio, on_progreso=on_progreso,
        )
    if modelo_id == "kling_o3_pro":
        payload = {
            "prompt": prompt, "images": refs, "aspect_ratio": aspect_ratio,
            "duration": int(duration), "sound": False,
        }
        return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
    if modelo_id == "seedance25":
        payload = {
            "prompt": prompt, "image": refs[0], "duration": int(duration),
            "resolution": "720p", "generate_audio": False,
        }
        return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
    raise ValueError(f"Modelo de video desconocido: {modelo_id}")


def generar_imagen(modelo_id, prompt, referencias, on_progreso=None):
    """Devuelve la URL pública de la imagen generada."""
    info = IMAGEN[modelo_id]
    if not referencias:
        raise ValueError(f"{info['nombre']} necesita al menos una imagen de referencia.")
    if modelo_id == "seedream_v5_pro":
        return wavespeed_imagen.editar_imagen_seedream(
            referencias[0], prompt, referencias_urls=list(referencias[1:]),
            resolution="2k", on_progreso=on_progreso,
        )
    raise ValueError(f"Modelo de imagen desconocido: {modelo_id}")
