import json
import os
import subprocess

import pytest
from PIL import Image

from final_edition import cortes, documento as d, motor
from final_edition.motor import render as r

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


@pytest.fixture(scope="module")
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("medios_editor")
    clon = str(carpeta / "clon.mp4"); voz = str(carpeta / "voz.wav"); musica = str(carpeta / "musica.wav")
    png = str(carpeta / "t1.png"); foto = str(carpeta / "foto.png")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30", "-t", "8", "-pix_fmt", "yuv420p", clon], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "7", voz], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "4", musica], check=True)
    Image.new("RGBA", (400, 200), (255, 0, 0, 200)).save(png)
    Image.new("RGB", (800, 600), (0, 128, 255)).save(foto)
    return {1: clon, 2: voz, 3: musica, "png:t1": png, "foto": foto}


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def _streams(path):
    info = cortes.ffprobe_json(path)
    return {s["codec_type"]: s for s in info["streams"]}, float(info["format"]["duration"])


@pytest.mark.slow
def test_renderiza_video_basico_con_audio_y_miniatura(tmp_path, medios):
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    etapas = []
    out = motor.renderizar(_doc(), rutas, str(tmp_path / "final.mp4"), on_etapa=etapas.append)
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 7.0) <= 0.2 and "audio" in streams
    assert streams["audio"]["sample_rate"] == "48000"
    assert os.path.exists(out["miniatura"]) and Image.open(out["miniatura"]).size == (1080, 1920)
    assert out["tramos"] == 1
    assert not os.path.exists(out["archivo"] + ".filtergraph.txt")


@pytest.mark.slow
@pytest.mark.skipif(not r.tiene_libass(), reason="este ffmpeg no trae libass (en el VPS sí)")
def test_con_libass_los_subtitulos_entran_por_ass(tmp_path, medios):
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    out = motor.renderizar(_doc(), rutas, str(tmp_path / "final.mp4"))
    assert out["con_ass"] is True and os.path.exists(rutas["ass"])


@pytest.mark.slow
def test_sin_libass_se_omiten_subtitulos_y_avisa(tmp_path, medios, monkeypatch):
    monkeypatch.setattr(r, "tiene_libass", lambda: False)
    etapas = []
    out = motor.renderizar(_doc(), {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"), on_etapa=etapas.append)
    assert out["con_ass"] is False and any("libass" in e for e in etapas)


@pytest.mark.slow
def test_render_por_tramos_concatena_sin_recodificar(tmp_path, medios, monkeypatch):
    from final_edition.motor import tramos
    # Fuerza dos tramos en la frontera entre clips (sin transición) para
    # ejercitar el render por partes y la concatenación con -c copy.
    monkeypatch.setattr(tramos, "partir", lambda doc, presupuesto=None: [(0, 3500), (3500, 7000)])
    doc = _doc()
    doc["pistas"][0]["clips"][0]["transicion"] = None
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert out["tramos"] == 2 and abs(dur - 7.0) <= 0.3 and "audio" in streams


@pytest.mark.slow
def test_imagen_estatica_sale_png(tmp_path, medios):
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    out = motor.renderizar(doc, {9: medios["foto"]}, str(tmp_path / "arte.png"))
    assert Image.open(out["archivo"]).size == (1080, 1080)
    assert out["miniatura"] == out["archivo"]


def test_validar_detecta_tamano_incorrecto(tmp_path, medios):
    from final_edition.motor.compilador import Plan
    plan = Plan(ancho=1080, alto=1920, duracion_ms=8000, salida_audio=False)
    with pytest.raises(RuntimeError, match="tamaño"):
        r.validar(medios[1], plan)  # el clon es 540x960
