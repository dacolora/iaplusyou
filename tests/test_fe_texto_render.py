import os
import shutil
import subprocess
import time

import pytest
from PIL import Image

from final_edition import cortes, render, texto

pytestmark = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None,
    reason="ffmpeg/ffprobe no instalados",
)


GUION = {
    "idioma": "es", "pais": "CO", "precio_texto": "$ 89.900",
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Tus pies merecen esto", "texto_voz": "…", "inicio_s": 0, "fin_s": 2},
        {"rol": "problema", "texto_pantalla": "Sin dolor", "texto_voz": "…", "inicio_s": 2, "fin_s": 4},
        {"rol": "producto", "texto_pantalla": "HappyFlops", "texto_voz": "…", "inicio_s": 4, "fin_s": 6},
        {"rol": "prueba", "texto_pantalla": "Miles felices", "texto_voz": "…", "inicio_s": 6, "fin_s": 8},
        {"rol": "cta", "texto_pantalla": "Pide las tuyas hoy en happyflops.co", "texto_voz": "…", "inicio_s": 8, "fin_s": 10},
    ],
}

PALABRAS = [
    {"inicio": 0.2, "fin": 0.6, "texto": "Tus"},
    {"inicio": 0.6, "fin": 1.0, "texto": "pies"},
    {"inicio": 1.0, "fin": 1.5, "texto": "merecen"},
    {"inicio": 1.5, "fin": 1.9, "texto": "esto"},
    {"inicio": 4.1, "fin": 4.5, "texto": "HappyFlops"},
    {"inicio": 4.5, "fin": 4.8, "texto": "sin"},
    {"inicio": 4.8, "fin": 5.4, "texto": "dolor"},
    {"inicio": 8.2, "fin": 8.9, "texto": "Pide"},
]


def _es_png_rgba(path, ancho=1080, alto=1920):
    assert os.path.exists(path)
    with Image.open(path) as im:
        assert im.mode == "RGBA"
        assert im.size == (ancho, alto)
        # Fondo transparente en una esquina (nunca hay texto ahí).
        assert im.getpixel((2, 2))[3] == 0


@pytest.fixture()
def logo(tmp_path):
    ruta = str(tmp_path / "logo.png")
    Image.new("RGBA", (600, 300), (255, 0, 0, 255)).save(ruta)
    return ruta


@pytest.fixture()
def overlays(tmp_path, logo):
    carpeta = str(tmp_path / "ov")
    return texto.generar_overlays(GUION, PALABRAS, {"color_acento": "#ff8800", "logo_path": logo}, carpeta)


# --- texto -------------------------------------------------------------------

def test_hook_png_y_tiempos(overlays):
    hook = overlays["hook"]
    _es_png_rgba(hook["png"])
    assert hook["inicio"] == 0 and hook["fin"] == 2


def test_subtitulos_uno_por_palabra_con_ventanas_extendidas(overlays):
    subs = overlays["subtitulos"]
    assert len(subs) == 8
    for s in subs:
        _es_png_rgba(s["png"])
    # Cada palabra dura hasta el inicio de la siguiente de su grupo; la última
    # del grupo hasta fin + 0.3.
    assert subs[0]["inicio"] == pytest.approx(0.2) and subs[0]["fin"] == pytest.approx(0.6)
    assert subs[3]["inicio"] == pytest.approx(1.5) and subs[3]["fin"] == pytest.approx(2.2)
    # Hueco > 0.8 s entre "esto" y "HappyFlops": grupo nuevo.
    assert subs[4]["inicio"] == pytest.approx(4.1) and subs[4]["fin"] == pytest.approx(4.5)
    assert subs[6]["fin"] == pytest.approx(5.7)
    assert subs[7]["fin"] == pytest.approx(9.2)
    # Las PNG son distintas (la palabra resaltada cambia).
    assert len({s["png"] for s in subs}) == 8


def test_badge_solo_con_precio(tmp_path, overlays):
    badge = overlays["badge"]
    assert badge is not None
    _es_png_rgba(badge["png"])
    assert badge["inicio"] == 4 and badge["fin"] == 8

    guion_sin = dict(GUION)
    guion_sin.pop("precio_texto")
    sin = texto.generar_overlays(guion_sin, PALABRAS, {}, str(tmp_path / "ov2"))
    assert sin["badge"] is None


def test_cta_con_logo_y_sin_logo(tmp_path, overlays):
    cta = overlays["cta"]
    _es_png_rgba(cta["png"])
    assert cta["inicio"] == 8 and cta["fin"] == 10
    sin = texto.generar_overlays(GUION, PALABRAS, {}, str(tmp_path / "ov3"))
    _es_png_rgba(sin["cta"]["png"])


def test_sin_palabras_no_hay_subtitulos(tmp_path):
    ov = texto.generar_overlays(GUION, [], {}, str(tmp_path / "ov4"))
    assert ov["subtitulos"] == []
    assert ov["hook"] and ov["cta"]


def test_muchas_palabras_agrupa_por_linea(tmp_path):
    palabras = [{"inicio": i * 0.05, "fin": i * 0.05 + 0.04, "texto": f"p{i}"} for i in range(200)]
    ov = texto.generar_overlays(GUION, palabras, {}, str(tmp_path / "ov5"))
    assert 0 < len(ov["subtitulos"]) <= texto.MAX_OVERLAYS_SUBTITULOS


def test_tamano_personalizado(tmp_path):
    ov = texto.generar_overlays(GUION, PALABRAS[:2], {}, str(tmp_path / "ov6"), ancho=540, alto=960)
    _es_png_rgba(ov["hook"]["png"], 540, 960)
    _es_png_rgba(ov["subtitulos"][0]["png"], 540, 960)


# --- render ------------------------------------------------------------------

@pytest.fixture(scope="module")
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("medios")
    clip = str(carpeta / "clip.mp4")
    voz = str(carpeta / "voz.wav")
    musica = str(carpeta / "musica.wav")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25", "-t", "10",
                           "-pix_fmt", "yuv420p", clip], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "10", voz], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "15", musica], check=True)
    return {"clip": clip, "voz": voz, "musica": musica}


SEGMENTOS = [
    {"inicio": 0.0, "fin": 3.5, "zoom": "in"},
    {"inicio": 3.5, "fin": 7.0, "zoom": "out"},
    {"inicio": 7.0, "fin": 10.0, "zoom": None},
]


def _streams(path):
    info = cortes.ffprobe_json(path)
    return {s["codec_type"]: s for s in info["streams"]}, float(info["format"]["duration"])


@pytest.mark.slow
def test_componer_completo(tmp_path, overlays, medios):
    salida = str(tmp_path / "final.mp4")
    t0 = time.monotonic()
    res = render.componer(medios["clip"], SEGMENTOS, overlays, medios["voz"], medios["musica"],
                          salida, 10.0, preset="ultrafast")
    wall = time.monotonic() - t0
    assert res["archivo"] == salida and os.path.exists(salida)
    assert os.path.exists(res["miniatura"])
    streams, dur = _streams(salida)
    assert dur == pytest.approx(10.0, abs=0.2)
    assert res["duracion_s"] == pytest.approx(10.0, abs=0.2)
    assert streams["video"]["width"] == 1080 and streams["video"]["height"] == 1920
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    with Image.open(res["miniatura"]) as im:
        assert im.size == (1080, 1920)
    print(f"\nrender wall time: {wall:.1f}s")


@pytest.mark.slow
def test_componer_sin_audio(tmp_path, overlays, medios):
    salida = str(tmp_path / "mudo.mp4")
    res = render.componer(medios["clip"], SEGMENTOS, overlays, None, None, salida, 10.0, preset="ultrafast")
    streams, dur = _streams(salida)
    assert "audio" not in streams
    assert dur == pytest.approx(10.0, abs=0.2)
    assert res["duracion_s"] == pytest.approx(10.0, abs=0.2)


@pytest.mark.slow
def test_componer_solo_musica_y_solo_voz(tmp_path, overlays, medios):
    a = str(tmp_path / "musica.mp4")
    render.componer(medios["clip"], SEGMENTOS, overlays, None, medios["musica"], a, 10.0, preset="ultrafast")
    assert "audio" in _streams(a)[0]
    b = str(tmp_path / "voz.mp4")
    render.componer(medios["clip"], SEGMENTOS, overlays, medios["voz"], None, b, 10.0, preset="ultrafast")
    assert "audio" in _streams(b)[0]


def test_filtergraph_forma(overlays):
    fg = render.construir_filtergraph(SEGMENTOS, overlays, True, True, 1080, 1920)
    assert fg.count("zoompan") == 3
    assert "concat=n=3:v=1:a=0[vc]" in fg
    assert "sidechaincompress" in fg and "amix" in fg
    assert fg.count("overlay=0:0") == 1 + 8 + 1 + 1
    assert fg.endswith("[aout]") or "[aout]" in fg
    assert "format=yuv420p[vout]" in fg
    assert "min(1+0.08*on/105,1.08)" in fg
    assert "max(1.08-0.08*on/105,1.0)" in fg


def test_filtergraph_sin_audio(overlays):
    fg = render.construir_filtergraph(SEGMENTOS, overlays, False, False, 1080, 1920)
    assert "[aout]" not in fg and "amix" not in fg


def test_filtergraph_largo_se_escribe_a_archivo(tmp_path, overlays, medios, monkeypatch):
    llamadas = []

    def falso_ffmpeg(args, timeout=300):
        llamadas.append(list(args))
        raise RuntimeError("parar aquí")

    monkeypatch.setattr(render.cortes, "ffmpeg", falso_ffmpeg)
    monkeypatch.setattr(render, "MAX_FILTERGRAPH_INLINE", 10)
    with pytest.raises(RuntimeError):
        render.componer(medios["clip"], SEGMENTOS, overlays, None, None, str(tmp_path / "x.mp4"), 10.0)
    assert "-filter_complex_script" in llamadas[0]
    idx = llamadas[0].index("-filter_complex_script")
    assert os.path.exists(llamadas[0][idx + 1])
