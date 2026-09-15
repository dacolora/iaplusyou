"""Final Edition, capa 2: locución por bloque del guion. Por cada bloque
sintetiza `texto_voz` (fal_audio.tts), mide el mp3 y, si no cabe en la ventana
del bloque, lo acelera con `atempo` hasta 1.35×; si aun así no cabe, se deja
solapar con el bloque siguiente hasta 0.4 s (`recortado: True`) y se recorta
lo que pase de ahí. Las marcas por palabra salen de transcribir el mp3 ya
ajustado (subido a R2 para que Whisper lo lea) desplazadas a la línea de
tiempo del video. Al final mezcla todas las pistas, cada una en su `inicio_s`,
sobre silencio en un wav estéreo a 44.1 kHz.
"""
import os
import uuid

import requests

from final_edition import cortes
from providers import fal_audio
from storage import r2_uploader

FACTOR_MAX = 1.35   # aceleración máxima tolerable sin que la voz suene rara
SOLAPE_MAX_S = 0.4  # lo que una pista puede invadir al bloque siguiente
FRECUENCIA = 44100


def sintetizar(guion, voz, carpeta, on_progreso=None, cliente=None):
    """Devuelve `(salida, costo_usd)` con
    salida = {"pistas": [{"rol", "archivo_mp3", "inicio_s", "fin_s",
                          "duracion_real_s", "factor_velocidad", "recortado"?}],
              "palabras": [{"inicio", "fin", "texto"}]  (tiempos absolutos),
              "archivo_voz": <wav con todas las pistas colocadas>}.
    `cliente` (kwarg o `guion["cliente"]`) decide la carpeta temporal de R2."""
    cliente = cliente or guion.get("cliente")
    if not cliente:
        raise ValueError("voz.sintetizar: falta `cliente` (kwarg o guion['cliente']).")
    idioma = guion.get("idioma") or "es"
    bloques = guion.get("bloques") or []
    if not bloques:
        raise ValueError("voz.sintetizar: el guion no tiene bloques.")
    os.makedirs(carpeta, exist_ok=True)

    pistas, palabras = [], []
    costo = 0.0
    total = len(bloques)
    for i, bloque in enumerate(bloques):
        _avisar(on_progreso, {"fase": f"voz {i + 1}/{total}"})
        pista, palabras_bloque, costo_bloque = _sintetizar_bloque(
            bloque, voz, idioma, carpeta, cliente)
        pistas.append(pista)
        palabras.extend(palabras_bloque)
        costo += costo_bloque

    archivo_voz = os.path.join(carpeta, "voz.wav")
    _mezclar(pistas, archivo_voz)

    salida = {"pistas": pistas, "palabras": palabras, "archivo_voz": archivo_voz}
    return salida, round(costo, 4)


def _sintetizar_bloque(bloque, voz, idioma, carpeta, cliente):
    rol = bloque["rol"]
    inicio_s = float(bloque["inicio_s"])
    fin_s = float(bloque["fin_s"])
    ventana = fin_s - inicio_s

    resultado = fal_audio.tts(bloque["texto_voz"], voz, idioma)
    costo = float(resultado.get("costo_usd") or 0.0)
    crudo = os.path.join(carpeta, f"{rol}.mp3")
    _descargar(resultado["url"], crudo)
    dur_real = cortes.duracion(crudo)

    factor = min(FACTOR_MAX, dur_real / ventana) if dur_real > ventana else 1.0
    pista = {
        "rol": rol, "archivo_mp3": crudo, "inicio_s": inicio_s, "fin_s": fin_s,
        "duracion_real_s": round(dur_real, 3), "factor_velocidad": round(factor, 3),
    }
    if factor > 1.0:
        ajustado = os.path.join(carpeta, f"{rol}_ajustado.mp3")
        args = ["-i", crudo, "-filter:a", f"atempo={factor:.4f}"]
        if dur_real / factor > ventana + SOLAPE_MAX_S:
            pista["recortado"] = True
            args += ["-t", f"{ventana + SOLAPE_MAX_S:.3f}"]
        cortes.ffmpeg(args + [ajustado], timeout=120)
        pista["archivo_mp3"] = ajustado

    clave = f"clientes/{cliente}/final_edition/tmp/{uuid.uuid4().hex}.mp3"
    url = r2_uploader.upload_file(pista["archivo_mp3"], clave, "audio/mpeg")
    transcripcion = fal_audio.transcribir_palabras(url, idioma)
    costo += float(transcripcion.get("costo_usd") or 0.0)

    tope = fin_s + SOLAPE_MAX_S
    palabras = []
    for p in transcripcion.get("palabras") or []:
        ini = min(round(inicio_s + float(p.get("inicio") or 0.0), 3), tope)
        fin = min(round(inicio_s + float(p.get("fin") or 0.0), 3), tope)
        palabras.append({"inicio": ini, "fin": max(fin, ini), "texto": p.get("texto", "")})
    return pista, palabras, costo


def _mezclar(pistas, destino):
    """Coloca cada pista en su `inicio_s` (adelay) sobre silencio y las suma
    (amix sin normalizar, para no bajar el volumen de la voz)."""
    ultima = pistas[-1]
    duracion_total = ultima["fin_s"] + (SOLAPE_MAX_S if ultima.get("recortado") else 0.0)

    args = ["-f", "lavfi", "-i", f"anullsrc=r={FRECUENCIA}:cl=stereo", "-t", f"{duracion_total:.3f}"]
    filtros, etiquetas = [], ""
    for i, pista in enumerate(pistas, start=1):
        args += ["-i", pista["archivo_mp3"]]
        ms = int(round(pista["inicio_s"] * 1000))
        filtros.append(f"[{i}]aresample={FRECUENCIA},aformat=channel_layouts=stereo,"
                       f"adelay={ms}|{ms}[a{i}]")
        etiquetas += f"[a{i}]"
    n = len(pistas) + 1
    filtros.append(f"[0]{etiquetas}amix=inputs={n}:normalize=0:duration=first[out]")
    args += ["-filter_complex", ";".join(filtros), "-map", "[out]",
             "-ar", str(FRECUENCIA), "-t", f"{duracion_total:.3f}", destino]
    cortes.ffmpeg(args, timeout=300)


def _descargar(url, destino):
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for trozo in resp.iter_content(chunk_size=65536):
            if trozo:
                f.write(trozo)
    return destino


def _avisar(on_progreso, info):
    if not on_progreso:
        return
    try:
        on_progreso(info)
    except Exception:
        pass
