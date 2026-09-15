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


def _png_recortado(entrada, ancho=1080, alto=1920):
    """PNG RGBA recortado que cabe en el frame en la posición (x, y).
    Devuelve (x, y, w, h)."""
    path = entrada["png"]
    assert os.path.exists(path)
    with Image.open(path) as im:
        assert im.mode == "RGBA"
        w, h = im.size
    x, y = entrada["x"], entrada["y"]
    assert 0 <= x and x + w <= ancho
    assert 0 <= y and y + h <= alto
    assert w < ancho or h < alto  # ya no es un PNG a tamaño de frame
    return x, y, w, h


def _sin_solapes(subs):
    for i, a in enumerate(subs):
        for b in subs[i + 1:]:
            assert a["fin"] <= b["inicio"] or b["fin"] <= a["inicio"], (a, b)


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

def test_hook_png_recortado_en_tercio_superior(overlays):
    hook = overlays["hook"]
    x, y, w, h = _png_recortado(hook)
    assert hook["inicio"] == 0 and hook["fin"] == 2
    assert y + h <= 1920 / 3 + 20
    assert w > 200 and h > 40  # hay texto de verdad


def test_subtitulos_uno_por_palabra_con_ventanas_extendidas(overlays):
    subs = overlays["subtitulos"]
    assert len(subs) == 8
    for s in subs:
        x, y, w, h = _png_recortado(s)
        assert y >= 2 * 1920 / 3  # tercio inferior
        assert w <= 1080 - 2 * texto.MARGEN_SUB
    # Cada palabra dura hasta el inicio de la siguiente de su grupo; la última
    # del grupo hasta fin + 0.3 (si el grupo siguiente no empieza antes).
    assert subs[0]["inicio"] == pytest.approx(0.2) and subs[0]["fin"] == pytest.approx(0.6)
    assert subs[3]["inicio"] == pytest.approx(1.5) and subs[3]["fin"] == pytest.approx(2.2)
    # Hueco > 0.8 s entre "esto" y "HappyFlops": grupo nuevo.
    assert subs[4]["inicio"] == pytest.approx(4.1) and subs[4]["fin"] == pytest.approx(4.5)
    assert subs[6]["fin"] == pytest.approx(5.7)
    assert subs[7]["fin"] == pytest.approx(9.2)
    # Las PNG son distintas (la palabra resaltada cambia).
    assert len({s["png"] for s in subs}) == 8
    _sin_solapes(subs)


def test_subtitulos_consecutivos_no_se_solapan_entre_grupos(tmp_path):
    palabras = [{"inicio": round(i * 0.3, 3), "fin": round(i * 0.3 + 0.25, 3), "texto": f"palabra{i}"}
                for i in range(8)]
    ov = texto.generar_overlays(GUION, palabras, {}, str(tmp_path / "ov_sol"))
    subs = ov["subtitulos"]
    assert len(subs) == 8
    _sin_solapes(subs)
    # La última del primer grupo se recorta al inicio del segundo (1.2 s), no a fin + 0.3.
    assert subs[3]["fin"] == pytest.approx(1.2)
    assert subs[7]["fin"] == pytest.approx(2.1 + 0.25 + 0.3)


def test_subtitulos_agrupan_por_ancho_medido(tmp_path):
    textos = "Compramos chanclas increíblemente cómodas".split()
    palabras = [{"inicio": i * 0.4, "fin": i * 0.4 + 0.35, "texto": t} for i, t in enumerate(textos)]
    ov = texto.generar_overlays(GUION, palabras, {}, str(tmp_path / "ov_ancho"))
    subs = ov["subtitulos"]
    assert len(subs) == 4
    lineas = set()
    for s in subs:
        x, y, w, h = _png_recortado(s)
        assert w <= 1080 - 2 * texto.MARGEN_SUB
        lineas.add((w, h))
    # Las 4 palabras no caben en una línea: al menos 2 grupos (PNG de distinto ancho).
    grupos = texto.agrupar_palabras(palabras, 4, 1080 - 2 * texto.MARGEN_SUB - 72 - 16,
                                    texto._fuente("texto", texto.TAM_SUB))
    assert len(grupos) >= 2
    assert len(lineas) >= 2


def test_palabra_mas_ancha_que_el_limite_reduce_fuente(tmp_path):
    palabras = [{"inicio": 0, "fin": 1, "texto": "Supercalifragilisticoespialidosamente"}]
    ov = texto.generar_overlays(GUION, palabras, {}, str(tmp_path / "ov_larga"))
    s = ov["subtitulos"][0]
    x, y, w, h = _png_recortado(s)
    assert w <= 1080  # cabe en el frame aunque sea a 48 px


def test_badge_solo_con_precio(tmp_path, overlays):
    badge = overlays["badge"]
    assert badge is not None
    x, y, w, h = _png_recortado(badge)
    assert x + w >= 1080 - 48 - 8  # arriba a la derecha
    assert badge["inicio"] == 4 and badge["fin"] == 8

    guion_sin = dict(GUION)
    guion_sin.pop("precio_texto")
    sin = texto.generar_overlays(guion_sin, PALABRAS, {}, str(tmp_path / "ov2"))
    assert sin["badge"] is None


def test_cta_con_logo_y_sin_logo(tmp_path, overlays):
    cta = overlays["cta"]
    x, y, w, h = _png_recortado(cta)
    assert cta["inicio"] == 8 and cta["fin"] == 10
    assert w == pytest.approx(1080 * 0.8, abs=20)
    sin = texto.generar_overlays(GUION, PALABRAS, {}, str(tmp_path / "ov3"))
    _png_recortado(sin["cta"])


def test_sin_palabras_no_hay_subtitulos(tmp_path):
    ov = texto.generar_overlays(GUION, [], {}, str(tmp_path / "ov4"))
    assert ov["subtitulos"] == []
    assert ov["hook"] and ov["cta"]


def test_muchas_palabras_agrupa_por_linea(tmp_path):
    palabras = [{"inicio": i * 0.05, "fin": i * 0.05 + 0.04, "texto": f"p{i}"} for i in range(200)]
    ov = texto.generar_overlays(GUION, palabras, {}, str(tmp_path / "ov5"))
    assert 0 < len(ov["subtitulos"]) <= texto.MAX_OVERLAYS_SUBTITULOS
    _sin_solapes(ov["subtitulos"])


def test_tamano_personalizado(tmp_path):
    ov = texto.generar_overlays(GUION, PALABRAS[:2], {}, str(tmp_path / "ov6"), ancho=540, alto=960)
    _png_recortado(ov["hook"], 540, 960)
    x, y, w, h = _png_recortado(ov["subtitulos"][0], 540, 960)
    assert w <= 540 - 2 * texto.MARGEN_SUB * 0.5


# --- render ------------------------------------------------------------------

@pytest.fixture(scope="module")
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("medios")
    clip = str(carpeta / "clip.mp4")
    clip20 = str(carpeta / "clip20.mp4")
    voz = str(carpeta / "voz.wav")
    musica = str(carpeta / "musica.wav")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25", "-t", "10",
                           "-pix_fmt", "yuv420p", clip], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=25", "-t", "20",
                           "-pix_fmt", "yuv420p", clip20], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "10", voz], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "15", musica], check=True)
    return {"clip": clip, "clip20": clip20, "voz": voz, "musica": musica}


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
    assert not os.path.exists(salida + ".filtergraph.txt")  # se borra tras un render correcto
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


@pytest.mark.slow
def test_componer_muchos_overlays_filtergraph_por_archivo(tmp_path, medios):
    """20 s, 60 palabras → ≥ 60 overlays: ejercita `-/filter_complex <archivo>`
    con ffmpeg real (y sirve de prueba de rendimiento: sin `-loop 1`)."""
    palabras = [{"inicio": round(0.5 + i * 0.3, 3), "fin": round(0.5 + i * 0.3 + 0.25, 3),
                 "texto": f"palabra{i}"} for i in range(60)]
    guion = dict(GUION)
    guion["bloques"] = [dict(b) for b in GUION["bloques"]]
    guion["bloques"][-1].update({"inicio_s": 18, "fin_s": 20})
    ov = texto.generar_overlays(guion, palabras, {"color_acento": "#00aaff"}, str(tmp_path / "ov60"))
    assert len(render._lista_overlays(ov)) >= 60
    segmentos = [{"inicio": 0.0, "fin": 10.0, "zoom": "in"}, {"inicio": 10.0, "fin": 20.0, "zoom": "out"}]
    salida = str(tmp_path / "largo.mp4")
    t0 = time.monotonic()
    res = render.componer(medios["clip20"], segmentos, ov, medios["voz"], medios["musica"],
                          salida, 20.0, preset="ultrafast")
    wall = time.monotonic() - t0
    streams, dur = _streams(salida)
    assert dur == pytest.approx(20.0, abs=0.2)
    assert res["duracion_s"] == pytest.approx(20.0, abs=0.2)
    assert streams["video"]["width"] == 1080
    assert not os.path.exists(salida + ".filtergraph.txt")
    print(f"\nrender 20 s / {len(render._lista_overlays(ov))} overlays wall time: {wall:.1f}s")


def test_componer_corta_si_hay_demasiados_overlays(tmp_path):
    """I2: `MAX_OVERLAYS_TOTAL` corta duro ANTES de invocar ffmpeg (no hay
    PNGs reales ni segmentos válidos: si esto llamara a ffmpeg, fallaría por
    otra razón antes de llegar al ValueError esperado)."""
    n = render.MAX_OVERLAYS_TOTAL + 1
    overlays_de_mas = {"hook": None, "badge": None, "cta": None,
                       "subtitulos": [{"png": "no-existe.png", "inicio": i, "fin": i + 1, "x": 0, "y": 0}
                                      for i in range(n)]}
    with pytest.raises(ValueError, match=r"Demasiados textos en pantalla \(\d+ > 80\)"):
        render.componer("no-existe.mp4", [{"inicio": 0.0, "fin": 1.0}], overlays_de_mas,
                        None, None, str(tmp_path / "salida.mp4"), 1.0)


def test_filtergraph_forma(overlays):
    fg = render.construir_filtergraph(SEGMENTOS, overlays, True, True, 1080, 1920)
    assert fg.count("zoompan") == 3
    assert "concat=n=3:v=1:a=0[vc]" in fg
    assert "sidechaincompress" in fg and "amix" in fg
    assert fg.count("overlay=") == 1 + 8 + 1 + 1
    assert fg.count("eof_action=repeat") == 11
    assert "between(" not in fg
    hook = overlays["hook"]
    assert f"overlay={hook['x']}:{hook['y']}:eof_action=repeat:enable='gte(t,0.000)*lt(t,2.000)'" in fg
    assert "format=yuv420p[vout]" in fg
    assert "min(1+0.08*on/105,1.08)" in fg
    assert "max(1.08-0.08*on/105,1.0)" in fg


def test_filtergraph_sin_audio(overlays):
    fg = render.construir_filtergraph(SEGMENTOS, overlays, False, False, 1080, 1920)
    assert "[aout]" not in fg and "amix" not in fg


def test_componer_siempre_pasa_el_filtergraph_por_archivo(tmp_path, overlays, medios, monkeypatch):
    llamadas = []

    def falso_ffmpeg(args, timeout=300):
        llamadas.append(list(args))
        raise RuntimeError("parar aquí")

    monkeypatch.setattr(render.cortes, "ffmpeg", falso_ffmpeg)
    with pytest.raises(RuntimeError):
        render.componer(medios["clip"], SEGMENTOS, overlays, None, None, str(tmp_path / "x.mp4"), 10.0)
    args = llamadas[0]
    assert "-filter_complex_script" not in args and "-filter_complex" not in args
    assert "-loop" not in args and "-framerate" not in args
    idx = args.index("-/filter_complex")
    assert os.path.exists(args[idx + 1])  # se conserva si ffmpeg falla
    with open(args[idx + 1], encoding="utf-8") as f:
        assert "[vout]" in f.read()
