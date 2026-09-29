"""Audios en Crear (spec 2026-09-28 §2): la mezcla de verdad con ffmpeg."""
import os

import pytest

import audios
from final_edition import cortes

pytestmark = pytest.mark.slow


def _senal(path, segundos, fuente):
    cortes.ffmpeg(["-f", "lavfi", "-i", fuente, "-t", str(segundos), "-ar", "44100", "-ac", "2", path], timeout=60)
    return path


def _info(path):
    i = cortes.ffprobe_json(path)
    (a,) = [s for s in i["streams"] if s["codec_type"] == "audio"]
    return a, float(i["format"]["duration"])


def test_con_musica_dura_intro_mas_voz_mas_cola(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 2, "sine=frequency=440")
    musica = _senal(str(tmp_path / "musica.wav"), 5, "anoisesrc=amplitude=0.1")
    r = audios.mezclar(voz, musica, str(tmp_path / "a.mp3"), 2000, "media")
    a, dur = _info(r["archivo"])
    assert abs(dur - 4.1) < 0.25 and abs(r["duracion_ms"] - 4100) < 250
    assert a["codec_name"] == "mp3" and int(a["sample_rate"]) == 44100 and a["channels"] == 2
    assert os.path.getsize(r["archivo"]) > 20000


def test_sin_musica_dura_lo_que_la_voz(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 2, "sine=frequency=440")
    r = audios.mezclar(voz, None, str(tmp_path / "b.mp3"), 2000, "media")
    a, dur = _info(r["archivo"])
    assert abs(dur - 2.0) < 0.25 and a["codec_name"] == "mp3"


def test_la_musica_corta_se_repite_hasta_cubrir_la_voz(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 4, "sine=frequency=440")
    musica = _senal(str(tmp_path / "musica.wav"), 1, "anoisesrc=amplitude=0.1")
    r = audios.mezclar(voz, musica, str(tmp_path / "c.mp3"), 4000, "alta")
    _, dur = _info(r["archivo"])
    assert abs(dur - 6.1) < 0.25
