"""Final Edition, capa 3: biblioteca propia de música de fondo generada con
Stable Audio (`providers.fal_audio.musica`) y cacheada en R2. Cada pista se
identifica por `<estilo>_<segundos redondeados a 15/30/45>`: si ya existe en
`manifest.json` y el archivo local sigue ahí, no cuesta nada; si el manifest
tiene la entrada pero falta el archivo local (se limpió la carpeta de
caché), se vuelve a descargar de R2 sin generar de nuevo; si no hay entrada,
se genera, se sube a R2 y se registra en el manifest (escritura atómica vía
`_json_store`).
"""
import fcntl
import math
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask_babel import gettext

import mi_musica
from mi_musica import es_propia  # noqa: F401 — los llamadores preguntan musica.es_propia(valor)
from final_edition import cortes, tipos
from providers import fal_audio
from storage import r2_uploader
import _json_store

CARPETA_CACHE_DEFAULT = os.path.join(tipos.BASE_DIR, "data", "musica")
CARPETA_PROPIA_DEFAULT = os.path.join(CARPETA_CACHE_DEFAULT, "propia")


class PistaPagadaError(RuntimeError):
    """La pista se pagó, pero no quedó conservada; otro intento sin caché puede cobrarla de nuevo."""
    def __init__(self, error, costo_usd, url):
        super().__init__(str(error))
        self.costo_usd = costo_usd
        self.url = url


def obtener_pista(estilo, segundos, carpeta_cache=None, on_progreso=None):
    """Devuelve `({"archivo", "url", "estilo", "generada"}, costo_usd)`.
    `segundos` se redondea hacia arriba al múltiplo de 15 más cercano (máx. 45)."""
    if estilo not in tipos.ESTILOS_MUSICA:
        validos = ", ".join(sorted(tipos.ESTILOS_MUSICA))
        raise ValueError(gettext("musica.obtener_pista: estilo desconocido '%(estilo)s'. Válidos: %(validos)s.",
                                 estilo=estilo, validos=validos))

    carpeta_cache = carpeta_cache or CARPETA_CACHE_DEFAULT
    os.makedirs(carpeta_cache, exist_ok=True)
    segundos_norm = min(45, 15 * math.ceil(segundos / 15))
    clave = f"{estilo}_{segundos_norm}"
    archivo_local = os.path.join(carpeta_cache, f"{clave}.wav")

    manifest_path = os.path.join(carpeta_cache, "manifest.json")
    # Dos piezas con el mismo estilo terminando a la vez (varias generaciones en
    # el worker): la que llega segunda espera y usa la pista de la primera en vez
    # de pagar otra. El manifest se relee y se escribe bajo su propio candado.
    with _bloqueo(os.path.join(carpeta_cache, f".{clave}.lock")):
        entrada = _json_store.cargar(manifest_path, default={}).get(clave)

        if entrada:
            if not os.path.exists(archivo_local):
                _descargar(entrada["url"], archivo_local)
            resultado = {"archivo": archivo_local, "url": entrada["url"],
                         "estilo": estilo, "generada": False}
            return resultado, 0

        prompt = tipos.ESTILOS_MUSICA[estilo]
        generado = fal_audio.musica(prompt, segundos_norm, on_progreso=on_progreso)
        costo = float(generado.get("costo_usd") or 0.0)
        try:
            _descargar(generado["url"], archivo_local)
            r2_key = f"musica/{clave}.wav"
            url_r2 = r2_uploader.upload_file(archivo_local, r2_key, "audio/wav")

            with _bloqueo(os.path.join(carpeta_cache, ".manifest.lock")):
                manifest = _json_store.cargar(manifest_path, default={})
                manifest[clave] = {
                    "url": url_r2,
                    "archivo": archivo_local,
                    "creado_en": datetime.now(timezone.utc).isoformat(),
                }
                _json_store.guardar(manifest_path, manifest)
        except Exception as e:
            raise PistaPagadaError(e, costo, generado["url"]) from e

    resultado = {"archivo": archivo_local, "url": url_r2, "estilo": estilo, "generada": True}
    return resultado, costo


@contextmanager
def _bloqueo(ruta):
    """`fcntl.flock` exclusivo sobre `ruta`: serializa hilos y procesos."""
    with open(ruta, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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


def pista_propia(cliente, valor, inicio_s=0, carpeta_cache=None):
    """Canción de Mi música (`mat:<id>`) lista para mezclar: el tramo desde
    `inicio_s` hasta el final, en WAV 48 kHz estéreo. El original se cachea
    por hash y el tramo por hash + inicio: la segunda vez no descarga ni
    recorta. Las mezclas ya hacen `-stream_loop -1` + `-t`, así que si el
    tramo es más corto que el video se repite ese mismo tramo. Cuesta 0."""
    m = mi_musica.resolver(cliente, valor)
    if not m:
        raise ValueError(gettext("Esa canción ya no está en Mi música."))
    inicio = mi_musica.inicio_valido(m, inicio_s)
    carpeta = carpeta_cache or CARPETA_PROPIA_DEFAULT
    os.makedirs(carpeta, exist_ok=True)
    ext = os.path.splitext(urlparse(m["url"]).path)[1] or ".mp3"
    original = os.path.join(carpeta, f"{m['hash']}{ext}")
    tramo = os.path.join(carpeta, f"{m['hash']}_{inicio}.wav")
    # Dos videos con la misma canción terminando a la vez: uno baja y recorta,
    # el otro espera y usa lo mismo.
    with _bloqueo(os.path.join(carpeta, f".{m['hash']}.lock")):
        if not os.path.exists(original):
            _descargar(m["url"], original)
        if not os.path.exists(tramo):
            tmp = tramo + ".tmp.wav"
            cortes.ffmpeg(["-ss", str(inicio), "-i", original, "-vn", "-ac", "2", "-ar", "48000", tmp])
            os.replace(tmp, tramo)
    c = mi_musica.como_cancion(m)
    return ({"archivo": tramo, "url": m["url"], "estilo": c["nombre"], "generada": False,
             "material_id": m["id"], "inicio_s": inicio, "fuente": c["fuente"]}, 0)
