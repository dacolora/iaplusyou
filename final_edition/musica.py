"""Final Edition, capa 3: biblioteca propia de música de fondo generada con
Stable Audio (`providers.fal_audio.musica`) y cacheada en R2. Cada pista se
identifica por `<estilo>_<segundos redondeados a 15/30/45>`: si ya existe en
`manifest.json` y el archivo local sigue ahí, no cuesta nada; si el manifest
tiene la entrada pero falta el archivo local (se limpió la carpeta de
caché), se vuelve a descargar de R2 sin generar de nuevo; si no hay entrada,
se genera, se sube a R2 y se registra en el manifest (escritura atómica vía
`_json_store`).
"""
import math
import os
from datetime import datetime, timezone

import requests

from final_edition import tipos
from providers import fal_audio
from storage import r2_uploader
import _json_store

CARPETA_CACHE_DEFAULT = os.path.join(tipos.BASE_DIR, "data", "musica")


def obtener_pista(estilo, segundos, carpeta_cache=None, on_progreso=None):
    """Devuelve `({"archivo", "url", "estilo", "generada"}, costo_usd)`.
    `segundos` se redondea hacia arriba al múltiplo de 15 más cercano (máx. 45)."""
    if estilo not in tipos.ESTILOS_MUSICA:
        validos = ", ".join(sorted(tipos.ESTILOS_MUSICA))
        raise ValueError(f"musica.obtener_pista: estilo desconocido '{estilo}'. Válidos: {validos}.")

    carpeta_cache = carpeta_cache or CARPETA_CACHE_DEFAULT
    os.makedirs(carpeta_cache, exist_ok=True)
    segundos_norm = min(45, 15 * math.ceil(segundos / 15))
    clave = f"{estilo}_{segundos_norm}"
    archivo_local = os.path.join(carpeta_cache, f"{clave}.wav")

    manifest_path = os.path.join(carpeta_cache, "manifest.json")
    manifest = _json_store.cargar(manifest_path, default={})
    entrada = manifest.get(clave)

    if entrada:
        if os.path.exists(archivo_local):
            resultado = {"archivo": archivo_local, "url": entrada["url"],
                         "estilo": estilo, "generada": False}
            return resultado, 0
        _descargar(entrada["url"], archivo_local)
        resultado = {"archivo": archivo_local, "url": entrada["url"],
                     "estilo": estilo, "generada": False}
        return resultado, 0

    prompt = tipos.ESTILOS_MUSICA[estilo]
    generado = fal_audio.musica(prompt, segundos_norm, on_progreso=on_progreso)
    costo = float(generado.get("costo_usd") or 0.0)
    _descargar(generado["url"], archivo_local)

    r2_key = f"musica/{clave}.wav"
    url_r2 = r2_uploader.upload_file(archivo_local, r2_key, "audio/wav")

    manifest[clave] = {
        "url": url_r2,
        "archivo": archivo_local,
        "creado_en": datetime.now(timezone.utc).isoformat(),
    }
    _json_store.guardar(manifest_path, manifest)

    resultado = {"archivo": archivo_local, "url": url_r2, "estilo": estilo, "generada": True}
    return resultado, costo


def elegir_estilo(categoria_producto, enfoque):
    """Elige un estilo de `tipos.ESTILOS_MUSICA` según la categoría del
    producto y el enfoque del video. `enfoque == "unboxing"` manda sobre la
    categoría; si no hay match, el estilo por defecto es "energetico"."""
    if enfoque == "unboxing":
        return "energetico"

    categoria = (categoria_producto or "").lower()

    if any(p in categoria for p in ("joy", "perfum", "lujo", "reloj")):
        return "lujo"
    if any(p in categoria for p in ("hogar", "beb", "cuidado", "spa")):
        return "calmado"
    if any(p in categoria for p in ("ropa", "calzado", "tecno", "gadget", "deport")):
        return "urbano"
    return "energetico"


def _descargar(url, destino):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for trozo in resp.iter_content(chunk_size=65536):
            if trozo:
                f.write(trozo)
    return destino
