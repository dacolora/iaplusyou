"""Final Edition, capa 4b: render del video final con ffmpeg en un solo
proceso (sin archivos intermedios).

Filtergraph:
  por segmento i:  [0:v]trim,setpts,scale(cover),crop,fps=30,zoompan[v_i]
  [v_0]..[v_n]concat[vc]
  [vc][1:v]overlay=x:y:eof_action=repeat:enable='gte(t,a)*lt(t,b)'[o1] ...
  [oK]format=yuv420p[vout]
  audio: mezcla.filtro_mezcla — sonido del clon recortado por segmento
         ([0:a]atrim + concat a=1), voz (apad) y música (-stream_loop -1),
         ducking por la voz, presets y loudnorm (ver final_edition/mezcla.py).
         Sin ninguna capa no hay stream de audio.

Cada PNG de overlay (recortado a su contenido por texto.py, con `x`/`y` en
coordenadas del frame) entra como `-i png` a secas: un solo frame decodificado
una vez, y `overlay=...:eof_action=repeat` lo mantiene el resto del video. No
se usa `-loop 1 -framerate 30` porque eso re-decodifica el PNG 30 veces por
segundo por overlay (con 60 overlays: varios GB de RSS y decenas de segundos
de CPU). La ventana `enable` es semiabierta (`gte*lt`) para que dos overlays
consecutivos no coincidan en el frame de frontera. `-t duracion_s` cierra la
salida. La música entra con `-stream_loop -1` y la voz lleva `apad` para que
ninguna de las dos corte el audio antes de la duración objetivo (una voz corta
terminaría el `sidechaincompress` y con él la música). `loudnorm` (último
filtro de la mezcla) emite a 192 kHz y el codificador AAC lo dejaría en 96 kHz,
por encima del tope de 48 kHz de Instagram Reels: la salida lleva `-ar 48000`
como opción de salida (no se remuestrea dentro del filtro).

El filtergraph se escribe SIEMPRE a `<salida>.filtergraph.txt` y se pasa con
`-/filter_complex <archivo>` (sintaxis de ffmpeg ≥ 7; `-filter_complex_script`
desapareció en ffmpeg 8). Evita el límite de argv y facilita depurar; el
archivo se borra tras un render correcto y se conserva si ffmpeg falla.

Presupuesto de memoria medido (2026-09-15, clip 30 s / 1080x1920, testsrc2):
cada `overlay` encadenado le cuesta a ffmpeg ~8 MB de RSS (decodifica un PNG
una vez, pero el filtro sigue buffereando el frame completo yuv420p por cada
capa de la cadena); 63 overlays ≈ 482 MB, 113 overlays ≈ 980-1027 MB — el
costo es lineal en el NÚMERO de overlays, no en el tamaño de cada PNG. En el
VPS de 1 CPU / 2 GB (gunicorn + worker en el mismo proceso) eso deja poco
margen, así que `MAX_OVERLAYS_TOTAL` corta duro antes de intentar el render
en vez de dejar que ffmpeg reviente por OOM a mitad de un render ya pagado.
"""
import os

from final_edition import cortes, mezcla

FPS = 30
ZOOM_MAX = 1.08
TOLERANCIA_DURACION_S = 0.2
# ~8 MB de RSS de ffmpeg por overlay encadenado (medido, ver docstring del
# módulo); 80 overlays ≈ 640 MB, deja margen en el VPS de 2 GB compartido con
# gunicorn + worker.
MAX_OVERLAYS_TOTAL = 80


def componer(clon_path, segmentos, overlays, archivo_voz, pista_musica, salida_mp4,
             duracion_s, ancho=1080, alto=1920, preset="veryfast", con_sonido=False, volumenes=None):
    """Renderiza `salida_mp4` (H.264 + AAC, faststart) y una miniatura PNG.
    `con_sonido`: conservar el audio nativo del clon (recortado con los mismos
    segmentos que el video); si el clon no trae pista, sale sin esa capa y
    `con_sonido` vuelve False en el resultado. `volumenes`: dict de
    `mezcla.volumenes_para` (None = preset por defecto). Valida con ffprobe
    (duración ± 0.2 s, tamaño, audio presente si y solo si hay alguna capa).
    Devuelve `{"archivo", "miniatura", "duracion_s", "con_sonido"}`. Lanza
    `ValueError` si los overlays superan `MAX_OVERLAYS_TOTAL`."""
    if not segmentos:
        raise ValueError("componer: no hay segmentos que renderizar")
    duracion_s = float(duracion_s)
    hay_voz = bool(archivo_voz)
    hay_musica = bool(pista_musica)
    hay_sonido = bool(con_sonido) and mezcla.tiene_audio(clon_path) is True
    lista_overlays = _lista_overlays(overlays)
    if len(lista_overlays) > MAX_OVERLAYS_TOTAL:
        raise ValueError(
            f"Demasiados textos en pantalla ({len(lista_overlays)} > {MAX_OVERLAYS_TOTAL}); acorta el guion"
        )

    args = ["-i", clon_path]
    for ov in lista_overlays:
        args += ["-i", ov["png"]]
    if hay_voz:
        args += ["-i", archivo_voz]
    if hay_musica:
        args += ["-stream_loop", "-1", "-i", pista_musica]

    os.makedirs(os.path.dirname(os.path.abspath(salida_mp4)), exist_ok=True)
    fg = construir_filtergraph(segmentos, overlays, hay_voz, hay_musica, ancho, alto,
                               hay_sonido=hay_sonido, volumenes=volumenes)
    archivo_fg = salida_mp4 + ".filtergraph.txt"
    with open(archivo_fg, "w", encoding="utf-8") as f:
        f.write(fg)
    args += ["-/filter_complex", archivo_fg]

    con_audio = hay_voz or hay_musica or hay_sonido
    args += ["-map", "[vout]"]
    if con_audio:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
    args += [
        "-c:v", "libx264", "-preset", preset, "-crf", "22", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-movflags", "+faststart", "-t", f"{duracion_s:.3f}",
        salida_mp4,
    ]
    cortes.ffmpeg(args, timeout=max(600, int(duracion_s * 30)))
    if os.path.exists(archivo_fg):
        os.remove(archivo_fg)

    real = _validar(salida_mp4, duracion_s, ancho, alto, con_audio)
    miniatura = os.path.splitext(salida_mp4)[0] + "_miniatura.png"
    _miniatura(salida_mp4, miniatura, real)
    return {"archivo": salida_mp4, "miniatura": miniatura, "duracion_s": real, "con_sonido": hay_sonido}


def construir_filtergraph(segmentos, overlays, hay_voz, hay_musica, ancho, alto, hay_sonido=False, volumenes=None):
    """Texto del `-filter_complex`. Los índices de entrada siguen el orden en
    que `componer` añade los `-i`: 0 clon, 1..K overlays, luego voz, luego
    música. `hay_sonido`: el audio del clon (`[0:a]`) se recorta con los mismos
    segmentos que el video y entra como capa "sonido" de `mezcla.filtro_mezcla`;
    `volumenes` es el dict de `mezcla.volumenes_para` (None = preset por
    defecto). Salidas etiquetadas `[vout]` y, si hay alguna capa, `[aout]`."""
    lista_overlays = _lista_overlays(overlays)
    partes = []

    for i, seg in enumerate(segmentos):
        ini, fin = float(seg["inicio"]), float(seg["fin"])
        frames = max(1, int(round((fin - ini) * FPS)))
        partes.append(
            f"[0:v]trim=start={ini:.3f}:end={fin:.3f},setpts=PTS-STARTPTS,"
            f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,"
            f"crop={ancho}:{alto},fps={FPS},"
            f"zoompan=z='{_expr_zoom(seg.get('zoom'), frames)}':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={FPS}[v{i}]"
        )
    entradas = "".join(f"[v{i}]" for i in range(len(segmentos)))
    partes.append(f"{entradas}concat=n={len(segmentos)}:v=1:a=0[vc]")

    actual = "[vc]"
    for k, ov in enumerate(lista_overlays, start=1):
        etiqueta = f"[o{k}]"
        partes.append(
            f"{actual}[{k}:v]overlay={int(ov.get('x', 0))}:{int(ov.get('y', 0))}:eof_action=repeat:"
            f"enable='gte(t,{float(ov['inicio']):.3f})*lt(t,{float(ov['fin']):.3f})'{etiqueta}"
        )
        actual = etiqueta
    partes.append(f"{actual}format=yuv420p[vout]")

    idx_voz = 1 + len(lista_overlays)
    idx_musica = idx_voz + (1 if hay_voz else 0)
    etiqueta_sonido = None
    if hay_sonido:
        # El audio del clon se recorta con los MISMOS inicio/fin que el video:
        # sincronía por construcción, sin desfases acumulados.
        for i, seg in enumerate(segmentos):
            ini, fin = float(seg["inicio"]), float(seg["fin"])
            partes.append(f"[0:a]atrim=start={ini:.3f}:end={fin:.3f},asetpts=PTS-STARTPTS[a{i}]")
        entradas_a = "".join(f"[a{i}]" for i in range(len(segmentos)))
        partes.append(f"{entradas_a}concat=n={len(segmentos)}:v=0:a=1[ac]")
        etiqueta_sonido = "[ac]"
    audio = mezcla.filtro_mezcla(
        voz=f"[{idx_voz}:a]" if hay_voz else None,
        sonido=etiqueta_sonido,
        musica=f"[{idx_musica}:a]" if hay_musica else None,
        volumenes=volumenes or mezcla.volumenes_para(),
    )
    if audio:
        partes.append(audio)
    return ";".join(partes)


def _expr_zoom(modo, frames):
    if modo == "in":
        return f"min(1+{ZOOM_MAX - 1:.2f}*on/{frames},{ZOOM_MAX})"
    if modo == "out":
        return f"max({ZOOM_MAX}-{ZOOM_MAX - 1:.2f}*on/{frames},1.0)"
    return "1"


def _lista_overlays(overlays):
    """Aplana el dict de texto.generar_overlays en orden de dibujo: hook,
    subtítulos, badge, cta (los últimos quedan encima)."""
    if not overlays:
        return []
    lista = []
    if overlays.get("hook"):
        lista.append(overlays["hook"])
    lista.extend(overlays.get("subtitulos") or [])
    if overlays.get("badge"):
        lista.append(overlays["badge"])
    if overlays.get("cta"):
        lista.append(overlays["cta"])
    return [o for o in lista if o and o.get("png") and float(o["fin"]) > float(o["inicio"])]


def _validar(salida, esperada, ancho, alto, con_audio):
    info = cortes.ffprobe_json(salida)
    streams = {s.get("codec_type"): s for s in info.get("streams") or []}
    video = streams.get("video")
    if not video:
        raise RuntimeError(f"render: {salida} no tiene stream de video")
    if (video.get("width"), video.get("height")) != (ancho, alto):
        raise RuntimeError(
            f"render: tamaño {video.get('width')}x{video.get('height')}, esperado {ancho}x{alto}")
    if bool(streams.get("audio")) != con_audio:
        raise RuntimeError(f"render: audio {'ausente' if con_audio else 'inesperado'} en {salida}")
    real = float((info.get("format") or {}).get("duration") or video.get("duration") or 0)
    if abs(real - esperada) > TOLERANCIA_DURACION_S:
        raise RuntimeError(f"render: duración {real:.2f}s, esperada {esperada:.2f}s")
    return round(real, 3)


def _miniatura(video, destino, duracion_real):
    punto = min(1.0, max(0.0, duracion_real / 2))
    cortes.ffmpeg(["-ss", f"{punto:.3f}", "-i", video, "-frames:v", "1", destino], timeout=60)
