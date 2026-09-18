"""Mezcla de audio (spec estudio S1/S2): la única fábrica del filtro que junta
el sonido de la escena (audio nativo del clon), la voz y la música. La usan
dos lugares: el paso "Mezclando sonido" del worker de Crear (clon + música,
`mezclar_musica`) y `render.construir_filtergraph` (final: sonido recortado
por segmento + voz + música). Reglas:

  - la voz manda: el sonido se agacha por la voz (sidechaincompress ratio 4)
    y la música también (ratio 8, el de siempre);
  - volúmenes por preset (`PRESETS`) o explícitos (`volumenes` manda);
  - sin voz, la música baja a VOL_MUSICA_CON_SONIDO si hay sonido, o a
    VOL_MUSICA_SOLA si va sola;
  - `amix ... duration=first`: voz y sonido llevan `apad` (para que una pista
    de audio más corta que su video no corte antes) y la música entra con
    `-stream_loop -1`; `-t` en la salida acota todo al final;
  - `loudnorm` de una pasada al final (±1 LU, suficiente para redes).
"""
from final_edition import cortes

LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"
NORM = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
VOL_SONIDO = 1.0
VOL_MUSICA_CON_VOZ = 0.35
VOL_MUSICA_SOLA = 0.5
VOL_MUSICA_CON_SONIDO = 0.45
DUCKING_VOZ_SOBRE_MUSICA = "threshold=0.05:ratio=8:attack=20:release=300"
DUCKING_VOZ_SOBRE_SONIDO = "threshold=0.05:ratio=4:attack=20:release=300"

PRESET_DEFECTO = "equilibrada"
PRESETS = {
    "equilibrada": {"voz": 1.0, "sonido": 1.0, "musica": VOL_MUSICA_CON_VOZ},
    "voz_protagonista": {"voz": 1.0, "sonido": 0.6, "musica": 0.25},
    "ambiente_protagonista": {"voz": 1.0, "sonido": 1.0, "musica": 0.2},
}
ESTADO_SONIDO = {True: "ok", False: "ausente", None: "desconocido"}


def volumenes_para(preset=None, volumenes=None):
    """{voz, sonido, musica} en 0–1: el preset (defecto `equilibrada`) y
    encima lo que venga en `volumenes`. Preset desconocido → ValueError."""
    nombre = preset or PRESET_DEFECTO
    if nombre not in PRESETS:
        raise ValueError(f"Preset de mezcla desconocido: {nombre}. Opciones: {sorted(PRESETS)}")
    v = dict(PRESETS[nombre])
    for k, val in (volumenes or {}).items():
        if k in v and val is not None:
            v[k] = min(1.0, max(0.0, float(val)))
    return v


def volumenes_efectivos(voz=None, sonido=None, musica=None, volumenes=None):
    """{voz, sonido, musica} con el volumen de música REALMENTE aplicado (no
    el preset crudo de `volumenes_para`): sin voz, la música baja a
    VOL_MUSICA_CON_SONIDO si hay sonido o a VOL_MUSICA_SOLA si va sola; con
    voz, manda el preset/`volumenes` tal cual. Misma regla que `filtro_mezcla`
    — esto es lo que va en `capas.mezcla.volumenes`."""
    v = volumenes_para(None, volumenes)
    if musica and not voz:
        v["musica"] = VOL_MUSICA_CON_SONIDO if sonido else VOL_MUSICA_SOLA
    return v


def tiene_audio(path):
    """True/False según ffprobe encuentre una pista de audio; None si ffprobe
    no está o falla. Solo informa: nunca bloquea una generación."""
    try:
        info = cortes.ffprobe_json(path)
    except Exception:
        return None
    return any((st or {}).get("codec_type") == "audio" for st in (info.get("streams") or []))


def filtro_mezcla(voz=None, sonido=None, musica=None, volumenes=None, salida="[aout]"):
    """Texto de filtergraph que consume las etiquetas de entrada dadas (p. ej.
    `voz="[3:a]"`, `sonido="[ac]"`, `musica="[4:a]"`) y produce `salida`.
    Devuelve "" si no hay ninguna capa. `volumenes` es un dict parcial o total
    de `volumenes_para` (None = preset por defecto para lo que falte)."""
    v = volumenes_efectivos(voz, sonido, musica, volumenes)
    partes, mezclar = [], []
    n_sc = (1 if sonido else 0) + (1 if musica else 0)
    if voz:
        if n_sc:
            etiquetas = "".join(f"[voz_sc{i}]" for i in range(n_sc)) + "[voz_mix]"
            partes.append(f"{voz}{NORM},apad,volume={v['voz']},asplit={n_sc + 1}{etiquetas}")
        else:
            partes.append(f"{voz}{NORM},apad,volume={v['voz']}[voz_mix]")
        mezclar.append("[voz_mix]")
    sc = 0
    if sonido:
        partes.append(f"{sonido}{NORM},apad,volume={v['sonido']}[son]")
        if voz:
            partes.append(f"[son][voz_sc{sc}]sidechaincompress={DUCKING_VOZ_SOBRE_SONIDO}[son_d]")
            sc += 1
            mezclar.insert(0, "[son_d]")
        else:
            mezclar.insert(0, "[son]")
    if musica:
        partes.append(f"{musica}{NORM},volume={v['musica']}[mus]")
        if voz:
            partes.append(f"[mus][voz_sc{sc}]sidechaincompress={DUCKING_VOZ_SOBRE_MUSICA}[mus_d]")
            sc += 1
            mezclar.append("[mus_d]")
        else:
            mezclar.append("[mus]")
    if not mezclar:
        return ""
    if len(mezclar) == 1:
        partes.append(f"{mezclar[0]}{LOUDNORM}{salida}")
    else:
        partes.append(f"{''.join(mezclar)}amix=inputs={len(mezclar)}:duration=first:normalize=0,{LOUDNORM}{salida}")
    return ";".join(partes)


def mezclar_musica(video_in, pista_musica, salida_mp4, duracion_s, volumenes=None):
    """Clon + música (paso "Mezclando sonido" de Crear): el video se copia sin
    recodificar; el audio es el sonido nativo (si lo hay) con la música
    debajo, `loudnorm` al final. Devuelve {"archivo", "con_sonido",
    "duracion_s", "volumenes"} — `volumenes` son los EFECTIVOS (el de música
    ya resuelto), listos para guardar en `capas.mezcla.volumenes`."""
    con_sonido = tiene_audio(video_in) is True
    v = volumenes_efectivos(sonido=con_sonido, musica=True, volumenes=volumenes)
    fg = filtro_mezcla(sonido="[0:a]" if con_sonido else None, musica="[1:a]", volumenes=v)
    duracion_s = float(duracion_s)
    cortes.ffmpeg([
        "-i", video_in, "-stream_loop", "-1", "-i", pista_musica,
        "-filter_complex", fg, "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{duracion_s:.3f}", "-movflags", "+faststart", salida_mp4,
    ], timeout=max(300, int(duracion_s * 10)))
    return {"archivo": salida_mp4, "con_sonido": con_sonido,
            "duracion_s": round(cortes.duracion(salida_mp4), 3), "volumenes": v}
