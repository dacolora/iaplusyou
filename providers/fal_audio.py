"""Proveedores de audio de Final Edition, todos vía fal.ai (providers/fal_client.py):
voz (ElevenLabs TTS multilingüe), transcripción con marcas por palabra (Whisper) y
música de fondo (Stable Audio). Cada función lanza+poll con fal_client.llamar y
devuelve un dict con la URL pública del resultado y el costo estimado en USD.

Formas de respuesta verificadas contra fal.ai el 2026-09-15 (ver plan
docs/superpowers/plans/2026-09-15-motor-bloque2-final-edition.md > Global Constraints):
  TTS       -> {"audio": {"url": ...}}
  Whisper   -> {"text": ..., "chunks": [{"timestamp": [ini, fin], "text": ...}]}
  Stable Audio -> {"audio_file": {"url": ...}}
`fal-ai/wizper` NO acepta chunk_level="word" — por eso se usa fal-ai/whisper.
"""
import math

from providers import fal_client

MODELO_TTS = "fal-ai/elevenlabs/tts/multilingual-v2"
MODELO_STT = "fal-ai/whisper"
MODELO_MUSICA = "fal-ai/stable-audio"

# $/carácter, $/minuto de audio y $/pista, estimados (ver Global Constraints del plan).
COSTO_USD_POR_CARACTER = 0.0003
COSTO_USD_POR_MINUTO_AUDIO = 0.002
COSTO_USD_POR_PISTA_MUSICA = 0.02

# Eleven Music vía fal (verificado en fal.ai/models/fal-ai/elevenlabs/music el
# 2026-09-25): prompt + music_length_ms (3 000–600 000) + force_instrumental;
# responde {"audio": {"url"}}; cobra US$ 0,60 por minuto empezado.
MODELO_MUSICA_ELEVENLABS = "fal-ai/elevenlabs/music"
COSTO_USD_POR_MINUTO_ELEVENLABS = 0.60

# Voces premade multilingües de ElevenLabs disponibles vía fal. Todas sirven
# para es/en/pt (multilingües); Rachel primero en las tres por ser la más
# verificada.
#
# Verificadas una a una contra fal.ai el 2026-09-15 (una llamada TTS mínima
# "Hola." por nombre, script en el plan de Bloque 2 final edition — I3).
# `Antoni`, `Bella`, `Domi`, `Elli`, `Josh`, `Arnold` y `Sam` son voces
# "legacy" de ElevenLabs que YA NO existen en el catálogo que expone fal
# (fal.ai responde 422 "Voice not found") — se quitaron de la lista. El resto
# de la lista (incluidas las agregadas) respondió 200 con audio.
_VOCES_MULTILINGUES = [
    "Rachel", "Adam", "Charlotte", "Matilda", "Daniel", "Aria", "Roger",
    "Sarah", "Laura", "Charlie", "George", "Callum", "River", "Liam",
    "Alice", "Jessica", "Eric", "Chris", "Brian", "Lily", "Bill", "Will",
]
VOCES = {
    "es": list(_VOCES_MULTILINGUES),
    "en": list(_VOCES_MULTILINGUES),
    "pt": list(_VOCES_MULTILINGUES),
}


def tts(texto, voz="Rachel", idioma="es", on_progreso=None):
    """Sintetiza `texto` con la voz `voz` (ver VOCES). Devuelve
    {"url": mp3 público, "costo_usd": len(texto) * COSTO_USD_POR_CARACTER}."""
    if not texto:
        raise ValueError("fal_audio.tts: texto vacío.")

    payload = {
        "text": texto,
        "voice": voz,
        "stability": 0.5,
        "similarity_boost": 0.75,
    }
    data = fal_client.llamar(MODELO_TTS, payload, timeout=180, on_progreso=on_progreso)

    url = (data.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({MODELO_TTS}) no devolvió una URL de audio: {data}")

    costo = round(len(texto) * COSTO_USD_POR_CARACTER, 4)
    return {"url": url, "costo_usd": costo}


def transcribir_palabras(audio_url, idioma, on_progreso=None):
    """Transcribe `audio_url` con marcas de tiempo por palabra. Devuelve
    {"texto": str, "palabras": [{"inicio", "fin", "texto"}], "costo_usd": float}."""
    payload = {
        "audio_url": audio_url,
        "task": "transcribe",
        "language": idioma,
        "chunk_level": "word",
    }
    data = fal_client.llamar(MODELO_STT, payload, timeout=180, on_progreso=on_progreso)

    chunks = data.get("chunks") or []
    palabras = []
    duracion_s = 0.0
    for chunk in chunks:
        inicio, fin = chunk.get("timestamp") or (0.0, 0.0)
        palabras.append({"inicio": inicio, "fin": fin, "texto": (chunk.get("text") or "").strip()})
        if fin is not None and fin > duracion_s:
            duracion_s = fin

    costo = round((duracion_s / 60.0) * COSTO_USD_POR_MINUTO_AUDIO, 4)
    return {"texto": data.get("text", ""), "palabras": palabras, "costo_usd": costo}


def musica(prompt, segundos, on_progreso=None):
    """Genera una pista de música de fondo de `segundos` de duración a partir
    de `prompt` (inglés, ver tipos.ESTILOS_MUSICA). Devuelve
    {"url": wav público, "costo_usd": 0.02}."""
    payload = {"prompt": prompt, "seconds_total": int(segundos)}
    data = fal_client.llamar(MODELO_MUSICA, payload, timeout=300, on_progreso=on_progreso)

    url = (data.get("audio_file") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({MODELO_MUSICA}) no devolvió una URL de audio: {data}")

    return {"url": url, "costo_usd": COSTO_USD_POR_PISTA_MUSICA}


def costo_elevenlabs(segundos):
    """fal cobra por minuto empezado: 30 s cuesta lo mismo que 60 s."""
    return round(COSTO_USD_POR_MINUTO_ELEVENLABS * math.ceil(int(segundos) / 60), 2)


def musica_elevenlabs(prompt, segundos=60, instrumental=True, on_progreso=None):
    """Canción a medida con Eleven Music. Devuelve {"url": mp3 público, "costo_usd"}."""
    segundos = max(3, min(600, int(segundos)))
    payload = {"prompt": prompt, "music_length_ms": segundos * 1000, "force_instrumental": bool(instrumental)}
    data = fal_client.llamar(MODELO_MUSICA_ELEVENLABS, payload, timeout=600, on_progreso=on_progreso)
    url = (data.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({MODELO_MUSICA_ELEVENLABS}) no devolvió una URL de audio: {data}")
    return {"url": url, "costo_usd": costo_elevenlabs(segundos)}
