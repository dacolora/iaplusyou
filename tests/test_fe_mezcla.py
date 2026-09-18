"""Mezcla de audio (spec estudio S1/S2): presets, filtro compartido por el
worker de Crear y por render, y la mezcla clon + música con ffmpeg real."""
import re
import subprocess

import pytest

from final_edition import cortes, mezcla


def test_presets_y_volumenes():
    assert mezcla.volumenes_para() == {"voz": 1.0, "sonido": 1.0, "musica": 0.35}
    assert mezcla.volumenes_para("voz_protagonista") == {"voz": 1.0, "sonido": 0.6, "musica": 0.25}
    assert mezcla.volumenes_para("ambiente_protagonista") == {"voz": 1.0, "sonido": 1.0, "musica": 0.2}
    # volúmenes explícitos mandan sobre el preset y se acotan a 0–1
    assert mezcla.volumenes_para("voz_protagonista", {"musica": 0.9, "sonido": 7}) == {"voz": 1.0, "sonido": 1.0, "musica": 0.9}
    with pytest.raises(ValueError):
        mezcla.volumenes_para("reguetón")


def test_volumenes_efectivos():
    # F2: sin voz, la música baja a VOL_MUSICA_CON_SONIDO si hay sonido...
    assert mezcla.volumenes_efectivos(sonido=True, musica=True) == {"voz": 1.0, "sonido": 1.0, "musica": mezcla.VOL_MUSICA_CON_SONIDO}
    # ...o a VOL_MUSICA_SOLA si la música va sola...
    assert mezcla.volumenes_efectivos(musica=True) == {"voz": 1.0, "sonido": 1.0, "musica": mezcla.VOL_MUSICA_SOLA}
    # ...pero con voz manda el preset (o `volumenes`) tal cual, sin recalcular.
    assert mezcla.volumenes_efectivos(voz=True, musica=True) == mezcla.volumenes_para()


def test_filtro_mezcla_por_combinacion():
    assert mezcla.filtro_mezcla() == ""
    solo_son = mezcla.filtro_mezcla(sonido="[ac]")
    assert solo_son.endswith(f"{mezcla.LOUDNORM}[aout]") and "amix" not in solo_son and "volume=1.0" in solo_son
    # F1: el sonido lleva apad (una pista más corta que el video no debe cortar antes de -t)
    assert f"[ac]{mezcla.NORM},apad,volume=1.0[son]" in solo_son
    son_mus = mezcla.filtro_mezcla(sonido="[ac]", musica="[2:a]")
    assert f"volume={mezcla.VOL_MUSICA_CON_SONIDO}" in son_mus and "amix=inputs=2:duration=first:normalize=0" in son_mus
    assert "sidechaincompress" not in son_mus and son_mus.index("[son]") < son_mus.index("[mus]")
    assert f"[ac]{mezcla.NORM},apad,volume=1.0[son]" in son_mus
    todo = mezcla.filtro_mezcla(voz="[3:a]", sonido="[ac]", musica="[4:a]")
    assert "asplit=3[voz_sc0][voz_sc1][voz_mix]" in todo
    assert f"[ac]{mezcla.NORM},apad,volume=1.0[son]" in todo
    assert f"[son][voz_sc0]sidechaincompress={mezcla.DUCKING_VOZ_SOBRE_SONIDO}[son_d]" in todo
    assert f"[mus][voz_sc1]sidechaincompress={mezcla.DUCKING_VOZ_SOBRE_MUSICA}[mus_d]" in todo
    assert "[son_d][voz_mix][mus_d]amix=inputs=3:duration=first:normalize=0," + mezcla.LOUDNORM + "[aout]" in todo
    voz_mus = mezcla.filtro_mezcla(voz="[1:a]", musica="[2:a]", volumenes={"musica": 0.2})
    assert "asplit=2[voz_sc0][voz_mix]" in voz_mus and "volume=0.2[mus]" in voz_mus and "[son" not in voz_mus
    solo_voz = mezcla.filtro_mezcla(voz="[1:a]")
    assert "asplit" not in solo_voz and "apad" in solo_voz and "amix" not in solo_voz


def test_tiene_audio_lee_los_streams_de_ffprobe(monkeypatch):
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]})
    assert mezcla.tiene_audio("/x.mp4") is True
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video"}]})
    assert mezcla.tiene_audio("/x.mp4") is False

    def _boom(p):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr(cortes, "ffprobe_json", _boom)
    assert mezcla.tiene_audio("/x.mp4") is None
    assert mezcla.ESTADO_SONIDO == {True: "ok", False: "ausente", None: "desconocido"}


def _lavfi(salida, video=True, audio=None, segundos=6):
    args = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    if video:
        args += ["-f", "lavfi", "-i", "testsrc2=size=320x568:rate=25"]
    if audio:
        args += ["-f", "lavfi", "-i", audio]
    args += ["-t", str(segundos)]
    if video:
        args += ["-pix_fmt", "yuv420p"]
    if audio and video:
        args += ["-c:a", "aac"]
    subprocess.run(args + [salida], check=True)
    return salida


def _loudness(path):
    proc = subprocess.run([cortes.FFMPEG, "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                          capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", proc.stderr)
    assert m, proc.stderr[-800:]
    return float(m[-1])


@pytest.mark.slow
def test_mezclar_musica_con_y_sin_sonido(tmp_path):
    con = _lavfi(str(tmp_path / "con.mp4"), audio="sine=frequency=440:sample_rate=44100")
    mudo = _lavfi(str(tmp_path / "mudo.mp4"))
    pista = _lavfi(str(tmp_path / "musica.wav"), video=False, audio="sine=frequency=220:sample_rate=44100", segundos=3)
    r = mezcla.mezclar_musica(con, pista, str(tmp_path / "con_musica.mp4"), cortes.duracion(con))
    assert r["con_sonido"] is True and r["duracion_s"] == pytest.approx(6.0, abs=0.3)
    streams = {s["codec_type"]: s for s in cortes.ffprobe_json(r["archivo"])["streams"]}
    assert streams["audio"]["codec_name"] == "aac" and streams["video"]["codec_name"] == "h264"
    assert int(streams["audio"]["sample_rate"]) == 48000
    assert -14 - 2.5 <= _loudness(r["archivo"]) <= -14 + 2.5
    r2 = mezcla.mezclar_musica(mudo, pista, str(tmp_path / "mudo_musica.mp4"), cortes.duracion(mudo))
    assert r2["con_sonido"] is False
    assert r2["duracion_s"] == pytest.approx(6.0, abs=0.3)
    assert "audio" in {s["codec_type"] for s in cortes.ffprobe_json(r2["archivo"])["streams"]}
    assert r["volumenes"] == {"voz": 1.0, "sonido": 1.0, "musica": mezcla.VOL_MUSICA_CON_SONIDO}


def _lavfi_desincronizado(salida, video_segundos=6, audio_segundos=5):
    """Video y audio con duraciones distintas (sin `-shortest`), para probar
    que F1's `apad` en el sonido no deje que voz/música corten con él."""
    args = [
        cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-t", str(video_segundos), "-i", "testsrc2=size=320x568:rate=25",
        "-f", "lavfi", "-t", str(audio_segundos), "-i", "sine=frequency=440:sample_rate=44100",
        "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p", "-c:a", "aac", salida,
    ]
    subprocess.run(args, check=True)
    return salida


@pytest.mark.slow
def test_mezclar_musica_apad_cuando_el_sonido_es_mas_corto_que_el_video(tmp_path):
    """F1: el clon puede traer una pista de audio más corta que su video
    (medido: 6 s video / 5 s audio). Sin `apad` la mezcla completa (voz +
    música) cortaba con el sonido a los 5 s; con `apad` sale a los 6 s."""
    corto = _lavfi_desincronizado(str(tmp_path / "corto.mp4"))
    assert cortes.duracion(corto) == pytest.approx(6.0, abs=0.3)
    pista = _lavfi(str(tmp_path / "musica.wav"), video=False, audio="sine=frequency=220:sample_rate=44100", segundos=3)
    r = mezcla.mezclar_musica(corto, pista, str(tmp_path / "corto_musica.mp4"), cortes.duracion(corto))
    assert r["con_sonido"] is True and r["duracion_s"] == pytest.approx(6.0, abs=0.3)
    streams = {s["codec_type"]: s for s in cortes.ffprobe_json(r["archivo"])["streams"]}
    assert float(streams["audio"]["duration"]) == pytest.approx(6.0, abs=0.3)
