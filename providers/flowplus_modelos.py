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
`generate_audio` (default true, sin recargo; hasta el 2026-09-28 mandábamos
`enable_audio`, que el esquema publicado ya no tiene), Kling O3 Pro `sound` (default
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

Solo texto (2026-09-25): en Crear las referencias y el catálogo son
opcionales. Sin ninguna imagen ni video cada modelo va a su ruta de texto
(`path_texto`, verificadas en wavespeed.ai/docs el 2026-09-25, mismos precios
que la ruta con referencias): alibaba/wan-3.0/text-to-video (480p/720p,
`generate_audio`), kwaivgi/kling-video-o3-pro/text-to-video (sin resolución,
`sound`), bytedance/seedance-2.5/text-to-video (a diferencia de image-to-video
SÍ elige formato: `formatos_texto`, `generate_audio`) y
bytedance/seedream-v5.0-pro (text-to-image, sin sufijo).

Seedance 2.5 con varias referencias (2026-10-09, pedido de Daniel: «en
Higgsfield Seedance acepta más de 3 imágenes»): WaveSpeed solo tiene su
image-to-video (`image` de arranque + `last_image`), así que `seedance25_ref`
va por fal (`proveedor: "fal"`, providers/fal_video.py):
bytedance/seedance-2.5/reference-to-video (`image_urls`, que el prompt nombra
@Image1, @Image2…; `duration` es TEXTO "4".."30"; formato elegible) y, sin
ninguna imagen, bytedance/seedance-2.5/text-to-video. Precio verificado el
2026-10-09 en la API de precios de fal (0,0214 USD por 1 000 tokens en las dos
rutas) y en sus páginas: ~0,4730 USD/s a 720p, con o sin sonido. Videos de referencia como
video quedan fuera por ahora (fal los factura aparte): entran por su
fotograma, como en Kling. No entra en la rotación automática de modelos de
las derivaciones (`rotar: False`): solo se usa si alguien lo elige.

Anuncio hablado (spec 2026-10-01): `HABLADO` es un registro aparte (foto +
voz → video que habla, P-Video-Avatar). Ningún selector, Sprints, derivación
ni CIERRE_SONIDO lo recorre; `estimate_video` delega en `estimate_hablado`
para que el gasto y «Reintentar» salgan de la misma fórmula.
"""
import math

import requests

from idiomas import N_
from providers import fal_video, wavespeed_common, wan3_client, wavespeed_imagen

VIDEO = {
    "wan3": {
        "nombre": N_("Wan 3.0"),
        "familia": "wan",
        "path": wan3_client.MODEL_PATH,
        "path_texto": "alibaba/wan-3.0/text-to-video",
        "max_referencias": 10,
        "usd_por_segundo": wan3_client.COSTO_USD_POR_SEGUNDO["720p"],
        "duraciones": (5, 8, 10, 12, 15, 20, 25, 30),
        "min_duracion": 2,
        "max_duracion": 30,
        "formatos": ("9:16", "16:9", "1:1", "4:3", "3:4"),
        "max_videos": 5,
        # Con videos de referencia (esquema de WaveSpeed, 2026-09-30): juntos suman
        # hasta 15 s, y entrada + salida no pasan de 30 s (1405 si no).
        "max_videos_s": 15,
        "max_total_con_videos": 30,
        "audio_nativo": {"parametro": "generate_audio", "recargo_usd_s": 0.0},
        "nota": N_("Hasta 10 imágenes y 5 videos de referencia (1-15 s), 720p, hasta 30 s (con videos de referencia, sus segundos más los del resultado no pasan de 30). El único que usa videos tal cual. Sonido de la escena incluido."),
    },
    "kling_o3_pro": {
        "nombre": N_("Kling O3 Pro"),
        "familia": "kling",
        "path": "kwaivgi/kling-video-o3-pro/reference-to-video",
        "path_texto": "kwaivgi/kling-video-o3-pro/text-to-video",
        # Imagen a video (cadena de escenas de Flow Plus, spec 2026-09-30): arranca en
        # `image` y conserva identidades con hasta 3 «elementos» de Kling.
        "path_i2v": "kwaivgi/kling-video-o3-pro/image-to-video",
        "max_elementos": 3,
        "max_referencias": 7,
        "usd_por_segundo": 0.112,
        "duraciones": (5, 8, 10, 12, 15),
        "min_duracion": 3,
        "max_duracion": 15,
        "formatos": ("9:16", "16:9", "1:1"),
        "max_videos": 0,
        "audio_nativo": {"parametro": "sound", "recargo_usd_s": 0.028},
        "nota": N_("Hasta 7 imágenes. De un video usa solo un fotograma. Movimiento y realismo de personas muy buenos. Hasta 15 s. El sonido de la escena cobra un recargo por segundo (ya incluido en el estimado)."),
    },
    "seedance25": {
        "nombre": N_("Seedance 2.5"),
        "familia": "seedance",
        "path": "bytedance/seedance-2.5/image-to-video",
        "path_texto": "bytedance/seedance-2.5/text-to-video",
        "max_referencias": 1,
        "usd_por_segundo": 0.36,
        "duraciones": (5, 8, 10, 12, 15, 20, 25, 30),
        "min_duracion": 4,
        "max_duracion": 30,
        "formatos": (),   # el formato sigue a la imagen de referencia: no se elige
        "formatos_texto": ("9:16", "16:9", "1:1", "4:3", "3:4"),   # sin imagen sí se elige
        "max_videos": 0,
        "audio_nativo": {"parametro": "generate_audio", "recargo_usd_s": 0.0},
        "nota": N_("Usa SOLO la primera imagen como fotograma de arranque; el encuadre y el formato salen de esa imagen. Hasta 30 s. Calidad cinematográfica, el más caro. Sonido de la escena incluido."),
    },
    "seedance25_ref": {
        "nombre": N_("Seedance 2.5 · varias referencias"),
        "familia": "seedance_ref",
        "proveedor": "fal",
        "path": "bytedance/seedance-2.5/reference-to-video",
        "path_texto": "bytedance/seedance-2.5/text-to-video",
        # fal admite 30; Crear manda hasta 10 imágenes (dashboard.cf_crear_video).
        "max_referencias": 10,
        "usd_por_segundo": 0.473,
        "duraciones": (5, 8, 10, 12, 15, 20, 25, 30),
        "min_duracion": 4,
        "max_duracion": 30,
        # fal cobra por píxeles de salida: 0,473 USD/s es su cifra de 720p (16:9 y
        # 9:16; 1:1 tiene menos píxeles). 4:3 y 3:4 quedan fuera hasta medir su
        # cobro real (PND-211): podrían pasar de esa cifra.
        "formatos": ("9:16", "16:9", "1:1"),
        "max_videos": 0,
        # Cómo nombra fal cada imagen en el prompt (esquema de reference-to-video).
        "token_imagen": "@Image{n}",
        "rotar": False,
        "audio_nativo": {"parametro": "generate_audio", "recargo_usd_s": 0.0},
        # Prueba real 2026-10-09: ByteDance rechaza (422, sin cobro) las fotos de personas reales.
        "nota": N_("Hasta 10 imágenes de referencia (personajes, producto, lugar) que nombras en el texto con @Imagen 1, @Imagen 2…; de un video usa solo un fotograma. No acepta fotos de personas reales: los personajes tienen que ser creados con IA. Hasta 30 s, en el formato que elijas. Va por fal y es el más caro. Sonido de la escena incluido."),
    },
}

IMAGEN = {
    "seedream_v5_pro": {
        "nombre": N_("Seedream V5.0 Pro"),
        "path": wavespeed_imagen.MODELO_SEEDREAM,
        "path_texto": "bytedance/seedream-v5.0-pro",
        "max_referencias": wavespeed_imagen.MAX_IMAGENES_SEEDREAM,
        "usd": wavespeed_imagen.COSTO_USD_SEEDREAM["2k"],
        "formatos": ("9:16", "1:1", "4:5", "16:9", "3:4", "4:3"),
        "nota": N_("Imagen 2k a partir de tus referencias y el texto, en el formato que elijas. Realismo fotográfico."),
    },
}

# Lo que ofrece el selector de duración de Crear; cada modelo recorta a su rango.
DURACIONES_CREAR = (5, 8, 10, 12, 15, 20, 25, 30)
DURACION_DEFECTO = 8
FORMATO_DEFECTO = "9:16"
# Etiquetas del selector de formato en Crear (_tab_creativeflowplus.html);
# marcadas con N_, se traducen con {{ nombre|traducir }} donde se muestran.
FORMATOS_NOMBRES = {
    "9:16": N_("Vertical 9:16 (Reels, TikTok, Shorts)"),
    "4:5": N_("Retrato 4:5 (feed de Instagram)"),
    "1:1": N_("Cuadrado 1:1"),
    "3:4": N_("Retrato 3:4"),
    "4:3": N_("Horizontal 4:3"),
    "16:9": N_("Horizontal 16:9 (YouTube)"),
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


def ajustar_formato(modelo_id, formato, tipo="video", solo_texto=False):
    """Formato que se le pide al modelo: el elegido si lo admite; si no, el
    vertical (o el primero que admita). None cuando el modelo no elige formato
    (Seedance: sigue a la imagen de referencia). solo_texto: la pieza no lleva
    ninguna imagen, así que vale `formatos_texto` si el modelo lo declara."""
    info = (IMAGEN if tipo == "imagen" else VIDEO)[modelo_id]
    formatos = tuple((solo_texto and info.get("formatos_texto")) or info.get("formatos") or ())
    if not formatos:
        return None
    if formato in formatos:
        return formato
    return FORMATO_DEFECTO if FORMATO_DEFECTO in formatos else formatos[0]

def referencias_de_mas(modelo_id, referencias, tipo="video"):
    """Etiquetas de las referencias que NO llegarían al modelo elegido, en el
    orden de la bandeja, con la misma cuenta que hacen `_preparar` y
    `generar_video`: Wan 3.0 recibe hasta `max_referencias` imágenes y aparte
    hasta `max_videos` videos; con los demás modelos el video entra por su
    fotograma y cuenta como una imagen más; Seedance 2.5 usa solo la primera
    (`max_referencias` 1). Incidente 2026-09-28 («mira lo que sacó»): cuatro
    referencias con Seedance, tres descartadas en silencio y el modelo más
    caro cobrado — la ruta de Crear avisa y no genera."""
    info = (IMAGEN if tipo == "imagen" else VIDEO)[modelo_id]
    max_img = int(info.get("max_referencias") or 0)
    max_vid = int(info.get("max_videos") or 0)
    sobran, n_img, n_vid = [], 0, 0
    for i, r in enumerate(referencias or []):
        if r.get("tipo") == "video" and max_vid > 0:
            n_vid += 1
            cabe = n_vid <= max_vid
        else:
            n_img += 1
            cabe = n_img <= max_img
        if not cabe:
            sobran.append(r.get("etiqueta") or f"#{i + 1}")
    return sobran


# Tarifa que ve la persona antes del clic: la del modelo más el recargo del
# sonido (siempre se pide). Las plantillas la muestran y el estimado en vivo
# de Crear la multiplica por la duración.
for _info in VIDEO.values():
    _info["usd_por_segundo_efectivo"] = round(_info["usd_por_segundo"] + _info["audio_nativo"]["recargo_usd_s"], 4)

VIDEO_POR_DEFECTO = "wan3"
IMAGEN_POR_DEFECTO = "seedream_v5_pro"


def proveedor_de(modelo_id):
    """Quién genera (y cobra) con ese modelo: "wavespeed", salvo los que
    declaran otro (`seedance25_ref` → "fal")."""
    info = VIDEO.get(modelo_id) or IMAGEN.get(modelo_id) or HABLADO.get(modelo_id) or {}
    return info.get("proveedor", "wavespeed")


def modelos_de_proveedor(proveedor):
    """Los modelos de video que genera ese proveedor (el aviso de sin saldo de
    fal en Crear nombra los que quedan en pausa)."""
    return [m for m in VIDEO if proveedor_de(m) == proveedor]


def video_rotables():
    """Los modelos de video que una regeneración automática puede elegir
    (derivaciones._otro): todos menos los que piden `rotar: False`."""
    return [m for m, info in VIDEO.items() if info.get("rotar", True)]

# Anuncio hablado (spec 2026-10-01): foto + voz → un video donde la persona de
# la foto dice la voz. Registro aparte a propósito: ningún selector de modelos,
# Sprints, derivación ni CIERRE_SONIDO recorre HABLADO (por eso no va en
# VIDEO). Verificado en la prueba real del 2026-09-30: pruna-ai/p-video/avatar
# recibe `image`, `audio`, `resolution` (720p|1080p) y `video_prompt` opcional
# («The person is talking.» por defecto); cobra US$ 0,025 por segundo de audio
# a 720p, redondeado al segundo y sin mínimo; entrega 704×1280 con una foto 9:16.
HABLADO = {
    "p_video_avatar": {
        "nombre": "P-Video-Avatar",
        "path": "pruna-ai/p-video/avatar",
        "usd_por_segundo": {"720p": 0.025, "1080p": 0.045},
        "max_segundos": 30,
    },
}
HABLADO_POR_DEFECTO = "p_video_avatar"
RESOLUCION_HABLADO = "720p"


def es_hablado(modelo_id):
    return modelo_id in HABLADO


def es_sesion_hablada(entry):
    """Una sesión de Crear que es un anuncio hablado (por su modo o por su
    modelo): no tiene director, «Editar y crear otra», final edition
    automático ni derivaciones (spec §6)."""
    e = entry or {}
    return e.get("modo_crear") == "hablado" or es_hablado(e.get("modelo"))


def nombre_modelo(modelo_id):
    """Nombre visible del modelo (VIDEO, IMAGEN o HABLADO); None si no existe."""
    info = VIDEO.get(modelo_id) or IMAGEN.get(modelo_id) or HABLADO.get(modelo_id)
    return info["nombre"] if info else None


def segundos_facturables(segundos):
    """Segundos que cobra P-Video-Avatar: hacia arriba al segundo (7,05 s → 8)."""
    return int(math.ceil(float(segundos) - 1e-9))

# Frase de cierre del bloque de sonido, literal de cada fabricante (guías
# oficiales de Wan 3.0, Kling y Seedance 2.5): así se apagan la voz y la
# música nativas sin depender de cómo entienda el modelo una frase en español.
CIERRE_SONIDO = {
    "wan": "No dialogue. No background music.",
    "kling": "No dialogue. No music.",
    "seedance": "No BGM; generate only environmental sounds and action sounds. No dialogue.",
    "seedance_ref": "No BGM; generate only environmental sounds and action sounds. No dialogue.",
}

# Calidad de la generación: "borrador" pide a Wan 3.0 480p (mitad de precio)
# para probar un prompt antes de la versión final; los demás modelos no tienen
# tarifa de borrador y la ignoran.
CALIDADES = ("final", "borrador")


def cierre_sonido(modelo_id):
    return CIERRE_SONIDO[VIDEO[modelo_id]["familia"]]


def _resolucion_wan(calidad):
    return "480p" if calidad == "borrador" else "720p"


def usd_por_segundo(modelo_id, con_sonido=True, calidad="final"):
    """Costo por segundo efectivo: el del modelo más el recargo del sonido
    nativo cuando se pide (Kling O3 Pro es el único que cobra aparte). Con
    calidad "borrador" Wan 3.0 cobra su tarifa de 480p; los demás, la misma."""
    info = VIDEO[modelo_id]
    base = info["usd_por_segundo"]
    if modelo_id == "wan3" and calidad == "borrador":
        base = wan3_client.COSTO_USD_POR_SEGUNDO["480p"]
    return round(base + (info["audio_nativo"]["recargo_usd_s"] if con_sonido else 0.0), 4)


def segundos_videos(modelo_id, referencias):
    """Duraciones conocidas (s) de los videos de referencia que el modelo
    recibe COMO VIDEO: solo Wan 3.0 (hasta `max_videos`); los demás usan su
    fotograma. Un video sin `duracion_s` se omite."""
    info = VIDEO.get(modelo_id) or {}
    max_videos = int(info.get("max_videos") or 0)
    if not max_videos:
        return []
    videos = [r for r in (referencias or []) if r.get("tipo") == "video"][:max_videos]
    return [float(r["duracion_s"]) for r in videos if r.get("duracion_s") is not None]


def problema_duracion(modelo_id, referencias, duracion):
    """None si la duración pedida cabe con los videos de referencia; si no,
    qué regla rompe (incidente 2026-09-30 en Forja: 14,9 s de video + 20 s
    pedidos → WaveSpeed 1405 «exceeds 30s limit»):
    {"motivo": "videos_largos", "videos_s", "maxima_videos"} o
    {"motivo": "total", "videos_s", "maxima"} (la salida más larga que cabe).
    Un video de duración desconocida no se juzga: lo mide el worker."""
    info = VIDEO.get(modelo_id) or {}
    segundos = segundos_videos(modelo_id, referencias)
    if not segundos or not info.get("max_total_con_videos"):
        return None
    total = round(sum(segundos), 2)
    if total > info["max_videos_s"]:
        return {"motivo": "videos_largos", "videos_s": total, "maxima_videos": info["max_videos_s"]}
    maxima = int(math.floor(info["max_total_con_videos"] - total))
    if int(duracion) > maxima:
        return {"motivo": "total", "videos_s": total, "maxima": maxima}
    return None


def duracion_con_videos(modelo_id, referencias, duracion):
    """La duración que de verdad se pide: con videos de referencia de
    duración conocida, Wan 3.0 recorta la salida para que entrada + salida no
    pasen de 30 s (última barrera en el worker y precio para reintentar, igual
    que ajustar_duracion); sin videos, o con otros modelos, no cambia."""
    info = VIDEO.get(modelo_id) or {}
    segundos = segundos_videos(modelo_id, referencias)
    if not segundos or not info.get("max_total_con_videos"):
        return duracion
    maxima = int(math.floor(info["max_total_con_videos"] - sum(segundos)))
    return max(int(info["min_duracion"]), min(int(duracion), maxima))


def segundos_facturables_referencia(duraciones):
    """Segundos de entrada que WaveSpeed factura en Wan 3.0 (esquema
    publicado): cada video cuenta entre 1 y 15 s, el total hasta 15 s,
    redondeado hacia arriba al segundo."""
    if not duraciones:
        return 0
    total = sum(min(15.0, max(1.0, float(d))) for d in duraciones)
    return int(math.ceil(min(15.0, total) - 1e-9))


def estimate_video(modelo_id, duration, con_sonido=True, calidad="final", videos_ref_s=()):
    """Costo de la generación. `videos_ref_s`: duraciones de los videos de
    referencia; solo Wan 3.0 los factura (los segundos de entrada normalizados
    más los de salida, a la misma tarifa) — antes del 2026-09-30 el estimado y
    el gasto los ignoraban. Los demás modelos reciben el fotograma y no cambian.
    Un modelo de HABLADO cobra por los segundos de la voz (`estimate_hablado`)."""
    if es_hablado(modelo_id):
        return estimate_hablado(modelo_id, duration)
    segundos = duration
    if (VIDEO.get(modelo_id) or {}).get("max_videos") and videos_ref_s:
        segundos = duration + segundos_facturables_referencia(videos_ref_s)
    return {"credits": None, "usd": round(usd_por_segundo(modelo_id, con_sonido, calidad) * segundos, 3)}


def estimate_imagen(modelo_id, n_referencias=1):
    info = IMAGEN[modelo_id]
    return wavespeed_imagen.estimate_seedream(resolution="2k", n_imagenes=max(1, n_referencias))


def estimate_hablado(modelo_id, segundos, resolucion=RESOLUCION_HABLADO):
    """Precio del anuncio hablado: segundos de la voz, hacia arriba al segundo,
    por la tarifa de la resolución (spec §9.5: la fórmula local coincidió al
    centavo con lo cobrado; no se llama a la API de precios)."""
    tarifa = HABLADO[modelo_id]["usd_por_segundo"][resolucion]
    return {"credits": None, "usd": round(segundos_facturables(segundos) * tarifa, 4)}


def _lanzar(path, payload, nombre, timeout_seconds=1200, on_progreso=None):
    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{path}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise wavespeed_common.error_de_respuesta(resp, path)
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")
    wavespeed_common.avisar_lanzada(on_progreso, prediction_id)
    resultado = wavespeed_common.poll_hasta_listo(
        prediction_id, nombre, timeout_seconds=timeout_seconds, on_progreso=on_progreso,
    )
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"{nombre} no devolvió ninguna salida: {resultado}")
    return outputs[0]


def esperar_fal(modelo_id, request_id, con_referencias, timeout_seconds, on_progreso=None, interval_seconds=5):
    """«Recuperar el video» de un modelo de fal: vuelve a preguntar por el
    pedido ya lanzado, en la misma ruta que eligió `generar_video` (con
    imágenes, `path`; sin ninguna, `path_texto`). Devuelve la URL del video;
    nunca lanza otro pedido."""
    info = VIDEO[modelo_id]
    ruta = info["path"] if con_referencias else info["path_texto"]
    return fal_video.esperar(ruta, request_id, info["nombre"], interval_seconds=interval_seconds,
                             timeout_seconds=timeout_seconds, on_progreso=on_progreso)


def generar_video(modelo_id, prompt, referencias, duration, aspect_ratio="9:16", on_progreso=None,
                  videos=None, con_sonido=True, calidad="final", mejorar_prompt=False, imagen_inicial=None,
                  elementos=None):
    """Devuelve la URL pública del video. referencias: URLs públicas de imágenes
    (la primera es la principal; Seedance solo usa esa). videos: URLs públicas
    de videos de referencia — solo Wan 3.0 los recibe tal cual; para los demás
    el llamador ya convirtió cada video en un fotograma dentro de `referencias`.
    con_sonido: pide el audio nativo del modelo (sonido de la escena); True
    salvo que la pieza se quiera muda a propósito. Sin imágenes ni videos va a
    la ruta de solo texto del modelo (`path_texto`). mejorar_prompt: prende el
    mejorador propio de Wan 3.0 (`enable_prompt_expansion`) — solo cuando la
    persona marcó la casilla; los demás modelos no tienen y lo ignoran.
    imagen_inicial/elementos: la cadena de escenas de Flow Plus — con Kling O3
    Pro el video arranca en esa imagen y conserva hasta 3 elementos (ids de
    `crear_elemento`); el formato lo da la imagen."""
    info = VIDEO[modelo_id]
    if imagen_inicial and info.get("path_i2v"):
        payload = {"prompt": prompt, "image": imagen_inicial, "duration": int(duration), "sound": bool(con_sonido)}
        ids = [str(e) for e in (elementos or []) if e][: info.get("max_elementos", 0)]
        if ids:
            payload["element_list"] = [{"element_id": e} for e in ids]
        return _lanzar(info["path_i2v"], payload, info["nombre"], on_progreso=on_progreso)
    videos = list(videos or [])[: info.get("max_videos", 0)]
    if not referencias and not videos:
        return _generar_video_texto(modelo_id, prompt, duration, aspect_ratio, on_progreso, con_sonido, calidad,
                                    mejorar_prompt)
    refs = list(referencias)[: info["max_referencias"]]
    if modelo_id == "wan3":
        return wan3_client.generar_video(
            prompt, refs, duration=duration, resolution=_resolucion_wan(calidad),
            aspect_ratio=aspect_ratio, on_progreso=on_progreso, reference_videos=videos,
            generate_audio=bool(con_sonido), enable_prompt_expansion=bool(mejorar_prompt),
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
    if modelo_id == "seedance25_ref":
        payload = {
            "prompt": prompt, "image_urls": refs, "duration": str(int(duration)), "resolution": "720p",
            "aspect_ratio": aspect_ratio or FORMATO_DEFECTO, "generate_audio": bool(con_sonido),
        }
        return fal_video.lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
    raise ValueError(f"Modelo de video desconocido: {modelo_id}")


def _generar_video_texto(modelo_id, prompt, duration, aspect_ratio, on_progreso, con_sonido, calidad,
                         mejorar_prompt=False):
    """Solo texto: el mismo modelo por su ruta text-to-video. El parámetro de
    audio va siempre explícito (Kling lo trae apagado por defecto); Kling no
    acepta resolución; sin `aspect_ratio` el modelo usa el suyo (16:9)."""
    info = VIDEO[modelo_id]
    if proveedor_de(modelo_id) == "fal":
        payload = {"prompt": prompt, "duration": str(int(duration)), "resolution": "720p",
                   "aspect_ratio": aspect_ratio or FORMATO_DEFECTO, "generate_audio": bool(con_sonido)}
        return fal_video.lanzar(info["path_texto"], payload, info["nombre"], on_progreso=on_progreso)
    payload = {"prompt": prompt, "duration": int(duration)}
    if modelo_id == "wan3":
        payload["resolution"] = _resolucion_wan(calidad)
        payload["enable_prompt_expansion"] = bool(mejorar_prompt)
    elif modelo_id == "seedance25":
        payload["resolution"] = "720p"
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio
    payload[info["audio_nativo"]["parametro"]] = bool(con_sonido)
    return _lanzar(info["path_texto"], payload, info["nombre"], on_progreso=on_progreso)


def generar_imagen(modelo_id, prompt, referencias, on_progreso=None, aspect_ratio=None):
    """Devuelve la URL pública de la imagen generada. aspect_ratio: uno de
    `IMAGEN[modelo]["formatos"]` o None (el modelo sigue a la primera imagen).
    Sin referencias va a la ruta de solo texto del modelo (`path_texto`)."""
    info = IMAGEN[modelo_id]
    if not referencias:
        payload = {"prompt": prompt, "resolution": "2k"}
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        return _lanzar(info["path_texto"], payload, info["nombre"], on_progreso=on_progreso)
    if modelo_id == "seedream_v5_pro":
        return wavespeed_imagen.editar_imagen_seedream(
            referencias[0], prompt, referencias_urls=list(referencias[1:]),
            resolution="2k", on_progreso=on_progreso, aspect_ratio=aspect_ratio,
        )
    raise ValueError(f"Modelo de imagen desconocido: {modelo_id}")


def generar_hablado(modelo_id, imagen_url, audio_url, video_prompt=None, resolucion=RESOLUCION_HABLADO,
                    on_progreso=None):
    """Anuncio hablado: la persona de `imagen_url` dice `audio_url`. Devuelve
    la URL pública del video. `video_prompt` («Cómo se mueve») va TAL CUAL;
    vacío o solo espacios, no se manda y el modelo usa su «The person is
    talking.». Mismo `_lanzar` que el resto: el id de la predicción se avisa
    por `on_progreso` apenas existe («Recuperar el video» lo usa)."""
    info = HABLADO[modelo_id]
    payload = {"image": imagen_url, "audio": audio_url, "resolution": resolucion}
    if video_prompt and video_prompt.strip():
        payload["video_prompt"] = video_prompt
    return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)


# «Elementos» de Kling: la identidad reutilizable de un personaje u objeto que
# usa la cadena de escenas de Flow Plus. Etapa 0 (2026-10-01): la API exige 1–3
# `refer_images`; con una sola ficha va la misma imagen en las dos.
ELEMENTOS_PATH = "kwaivgi/kling-elements-advanced"
PRECIO_ELEMENTO = 0.01


def crear_elemento(nombre, descripcion, imagen_url):
    """Crea un elemento de Kling y devuelve su `element_id` (texto)."""
    salida = _lanzar(ELEMENTOS_PATH, {
        "name": (nombre or "Element").strip()[:20], "description": (descripcion or nombre or "").strip()[:100],
        "reference_type": "image_refer", "frontal_image": imagen_url, "refer_images": [imagen_url],
    }, "Kling Elements", timeout_seconds=300)
    eid = salida.get("element_id") if isinstance(salida, dict) else None
    if not eid:
        raise RuntimeError(f"Kling no devolvió el elemento: {str(salida)[:300]}")
    return str(eid)
