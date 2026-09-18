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

Sonido de la escena (spec estudio S1): los tres modelos generan audio nativo y
se pide SIEMPRE salvo que el llamador diga `con_sonido=False`. Parámetros y
precios verificados en wavespeed.ai/models/* el 2026-09-17: Wan 3.0
`enable_audio` (default true, sin recargo), Kling O3 Pro `sound` (default
false, 0.112 -> 0.140 $/s; solo disponible sin video de referencia, que Kling
nunca recibe aquí), Seedance 2.5 `generate_audio` (default true, sin recargo).
`audio_nativo` de cada entrada guarda el nombre del parámetro y el recargo por
segundo; `estimate_video` lo suma para que el costo se vea antes del clic.

Duraciones y formatos (verificados en wavespeed.ai el 2026-09-18): Wan 3.0
2-30 s (con videos de referencia, sus segundos más los de la salida no pasan
de 30) y 9:16/16:9/1:1/4:3/3:4; Kling O3 Pro 3-15 s y 9:16/16:9/1:1; Seedance
2.5 4-30 s y el formato sigue a la imagen de referencia (no se elige);
Seedream V5 Pro acepta `aspect_ratio` (sin él sigue a la primera imagen).
`min_duracion`/`max_duracion` y `formatos` de cada entrada son lo que la UI
ofrece y lo que `ajustar_duracion`/`ajustar_formato` imponen antes de gastar.
"""
import requests

from providers import wavespeed_common, wan3_client, wavespeed_imagen

VIDEO = {
    "wan3": {
        "nombre": "Wan 3.0",
        "path": wan3_client.MODEL_PATH,
        "max_referencias": 10,
        "usd_por_segundo": wan3_client.COSTO_USD_POR_SEGUNDO["720p"],
        "duraciones": (5, 8, 10, 12, 15, 20, 25, 30),
        "min_duracion": 2,
        "max_duracion": 30,
        "formatos": ("9:16", "16:9", "1:1", "4:3", "3:4"),
        "max_videos": 5,
        "audio_nativo": {"parametro": "enable_audio", "recargo_usd_s": 0.0},
        "nota": "Hasta 10 imágenes y 5 videos de referencia (1-15 s), 720p, hasta 30 s (con videos de referencia, sus segundos más los del resultado no pasan de 30). El único que usa videos tal cual. Sonido de la escena incluido.",
    },
    "kling_o3_pro": {
        "nombre": "Kling O3 Pro",
        "path": "kwaivgi/kling-video-o3-pro/reference-to-video",
        "max_referencias": 7,
        "usd_por_segundo": 0.112,
        "duraciones": (5, 8, 10, 12, 15),
        "min_duracion": 3,
        "max_duracion": 15,
        "formatos": ("9:16", "16:9", "1:1"),
        "max_videos": 0,
        "audio_nativo": {"parametro": "sound", "recargo_usd_s": 0.028},
        "nota": "Hasta 7 imágenes. De un video usa solo un fotograma. Movimiento y realismo de personas muy buenos. Hasta 15 s. El sonido de la escena cuesta 0,028 USD/s más (ya incluido en el estimado).",
    },
    "seedance25": {
        "nombre": "Seedance 2.5",
        "path": "bytedance/seedance-2.5/image-to-video",
        "max_referencias": 1,
        "usd_por_segundo": 0.36,
        "duraciones": (5, 8, 10, 12, 15, 20, 25, 30),
        "min_duracion": 4,
        "max_duracion": 30,
        "formatos": (),   # el formato sigue a la imagen de referencia: no se elige
        "max_videos": 0,
        "audio_nativo": {"parametro": "generate_audio", "recargo_usd_s": 0.0},
        "nota": "Usa SOLO la primera imagen como fotograma de arranque; el encuadre y el formato salen de esa imagen. Hasta 30 s. Calidad cinematográfica, el más caro. Sonido de la escena incluido.",
    },
}

IMAGEN = {
    "seedream_v5_pro": {
        "nombre": "Seedream V5.0 Pro",
        "path": wavespeed_imagen.MODELO_SEEDREAM,
        "max_referencias": wavespeed_imagen.MAX_IMAGENES_SEEDREAM,
        "usd": wavespeed_imagen.COSTO_USD_SEEDREAM["2k"],
        "formatos": ("9:16", "1:1", "4:5", "16:9", "3:4", "4:3"),
        "nota": "Imagen 2k a partir de tus referencias y el texto, en el formato que elijas. Realismo fotográfico.",
    },
}

# Lo que ofrece el selector de duración de Crear; cada modelo recorta a su rango.
DURACIONES_CREAR = (5, 8, 10, 12, 15, 20, 25, 30)
DURACION_DEFECTO = 10
FORMATO_DEFECTO = "9:16"
FORMATOS_NOMBRES = {
    "9:16": "Vertical 9:16 (Reels, TikTok, Shorts)",
    "4:5": "Retrato 4:5 (feed de Instagram)",
    "1:1": "Cuadrado 1:1",
    "3:4": "Retrato 3:4",
    "4:3": "Horizontal 4:3",
    "16:9": "Horizontal 16:9 (YouTube)",
}


def ajustar_duracion(modelo_id, duracion):
    """Duración (int, segundos) dentro del rango del modelo; sin valor o con
    basura, la de defecto (también recortada)."""
    info = VIDEO[modelo_id]
    try:
        d = int(float(duracion))
    except (TypeError, ValueError):
        d = DURACION_DEFECTO
    return max(int(info["min_duracion"]), min(int(info["max_duracion"]), d))


def ajustar_formato(modelo_id, formato, tipo="video"):
    """Formato que se le pide al modelo: el elegido si lo admite; si no, el
    vertical (o el primero que admita). None cuando el modelo no elige formato
    (Seedance: sigue a la imagen de referencia)."""
    info = (IMAGEN if tipo == "imagen" else VIDEO)[modelo_id]
    formatos = tuple(info.get("formatos") or ())
    if not formatos:
        return None
    if formato in formatos:
        return formato
    return FORMATO_DEFECTO if FORMATO_DEFECTO in formatos else formatos[0]

# Tarifa que ve la persona antes del clic: la del modelo más el recargo del
# sonido (siempre se pide). Las plantillas la muestran y el estimado en vivo
# de Crear la multiplica por la duración.
for _info in VIDEO.values():
    _info["usd_por_segundo_efectivo"] = round(_info["usd_por_segundo"] + _info["audio_nativo"]["recargo_usd_s"], 4)

VIDEO_POR_DEFECTO = "wan3"
IMAGEN_POR_DEFECTO = "seedream_v5_pro"


def usd_por_segundo(modelo_id, con_sonido=True):
    """Costo por segundo efectivo: el del modelo más el recargo del sonido
    nativo cuando se pide (Kling O3 Pro es el único que cobra aparte)."""
    info = VIDEO[modelo_id]
    return info["usd_por_segundo_efectivo"] if con_sonido else info["usd_por_segundo"]


def estimate_video(modelo_id, duration, con_sonido=True):
    return {"credits": None, "usd": round(usd_por_segundo(modelo_id, con_sonido) * duration, 3)}


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


def generar_video(modelo_id, prompt, referencias, duration, aspect_ratio="9:16", on_progreso=None,
                  videos=None, con_sonido=True):
    """Devuelve la URL pública del video. referencias: URLs públicas de imágenes
    (la primera es la principal; Seedance solo usa esa). videos: URLs públicas
    de videos de referencia — solo Wan 3.0 los recibe tal cual; para los demás
    el llamador ya convirtió cada video en un fotograma dentro de `referencias`.
    con_sonido: pide el audio nativo del modelo (sonido de la escena); True
    salvo que la pieza se quiera muda a propósito."""
    info = VIDEO[modelo_id]
    videos = list(videos or [])[: info.get("max_videos", 0)]
    if not referencias and not videos:
        raise ValueError(f"{info['nombre']} necesita al menos una imagen de referencia.")
    refs = list(referencias)[: info["max_referencias"]]
    if modelo_id == "wan3":
        return wan3_client.generar_video(
            prompt, refs, duration=duration, resolution="720p",
            aspect_ratio=aspect_ratio, on_progreso=on_progreso, reference_videos=videos,
            enable_audio=bool(con_sonido),
        )
    if modelo_id == "kling_o3_pro":
        payload = {
            "prompt": prompt, "images": refs, "aspect_ratio": aspect_ratio,
            "duration": int(duration), "sound": bool(con_sonido),
        }
        return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
    if modelo_id == "seedance25":
        payload = {
            "prompt": prompt, "image": refs[0], "duration": int(duration),
            "resolution": "720p", "generate_audio": bool(con_sonido),
        }
        return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
    raise ValueError(f"Modelo de video desconocido: {modelo_id}")


def generar_imagen(modelo_id, prompt, referencias, on_progreso=None, aspect_ratio=None):
    """Devuelve la URL pública de la imagen generada. aspect_ratio: uno de
    `IMAGEN[modelo]["formatos"]` o None (el modelo sigue a la primera imagen)."""
    info = IMAGEN[modelo_id]
    if not referencias:
        raise ValueError(f"{info['nombre']} necesita al menos una imagen de referencia.")
    if modelo_id == "seedream_v5_pro":
        return wavespeed_imagen.editar_imagen_seedream(
            referencias[0], prompt, referencias_urls=list(referencias[1:]),
            resolution="2k", on_progreso=on_progreso, aspect_ratio=aspect_ratio,
        )
    raise ValueError(f"Modelo de imagen desconocido: {modelo_id}")
