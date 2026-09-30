import copy
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
    # La voz y la música terminan con el primer tramo: el segundo no tiene
    # ningún clip de audio activo, así que ejercita el relleno de silencio
    # (homogeneidad de streams entre tramos para `concat -c copy`).
    doc["pistas"][2]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][2]["clips"][0]["recorte"]["hasta_ms"] = 3500
    doc["pistas"][3]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][3]["clips"][0]["recorte"]["hasta_ms"] = 3500
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert out["tramos"] == 2 and abs(dur - 7.0) <= 0.3 and "audio" in streams
    assert abs(float(streams["audio"]["duration"]) - 7.0) <= 0.3


@pytest.mark.slow
def test_muchos_cortes_se_renderizan_por_tramos_con_su_audio(tmp_path, medios, monkeypatch):
    # Incidente 2026-09-30: 32 cortes = 32 entradas de ffmpeg y ~3 GB de RAM.
    # Con el presupuesto de videos, 10 cortes (fundidos y cámara lenta
    # incluidos) salen por tramos y la unión conserva duración y audio.
    from final_edition.motor import tramos
    monkeypatch.setattr(tramos, "PRESUPUESTO_VIDEOS", 4)
    doc = _doc()
    base = doc["pistas"][0]["clips"][0]
    clips = []
    for i in range(10):
        c = copy.deepcopy(base)
        vel = 0.75 if i % 3 == 1 else 1.0
        desde = 500 * (i % 6)
        c.update(id=f"v{i}", inicio_ms=i * 700, duracion_ms=700, velocidad=vel,
                 recorte={"desde_ms": desde, "hasta_ms": desde + round(700 * vel)},
                 transicion={"tipo": "fundido", "duracion_ms": 200} if i % 2 == 0 and i < 9 else None)
        clips.append(c)
    doc["pistas"][0]["clips"] = clips
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert out["tramos"] >= 3
    assert abs(dur - 7.0) <= 0.3 and "audio" in streams
    assert abs(float(streams["audio"]["duration"]) - 7.0) <= 0.3


def _silencios(ruta, umbral_db=-45, minimo_s=0.005):
    """Inicios (s) de los silencios de al menos `minimo_s` en el audio."""
    err = subprocess.run([cortes.FFMPEG, "-hide_banner", "-nostats", "-i", ruta, "-af",
                          f"silencedetect=noise={umbral_db}dB:d={minimo_s}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [float(l.split("silence_start:")[1]) for l in err.splitlines() if "silence_start:" in l]


@pytest.mark.slow
def test_la_union_de_tramos_no_deja_huecos_en_el_audio(tmp_path, medios, monkeypatch):
    # El AAC de cada tramo trae ~21 ms de relleno al principio; unido con
    # `-c copy` sonaba como un corte en cada frontera. La voz y la música
    # suenan de punta a punta (el final se apaga con su fundido de salida,
    # por eso no cuenta): no debe haber ni un silencio antes.
    from final_edition.motor import tramos
    monkeypatch.setattr(tramos, "partir", lambda doc, presupuesto=None: [(0, 3500), (3500, 7000)])
    doc = _doc()
    doc["pistas"][0]["clips"][0]["transicion"] = None
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    assert out["tramos"] == 2
    assert [t for t in _silencios(out["archivo"]) if t < 6.9] == []


def test_fallo_a_mitad_de_tramos_no_deja_parciales(tmp_path, monkeypatch):
    from final_edition.motor import tramos
    monkeypatch.setattr(tramos, "partir", lambda doc, presupuesto=None: [(0, 3500), (3500, 7000)])

    llamadas = []

    def _ejecutar_falso(plan, salida, ass_ruta=None, timeout=None, opciones_audio=None):
        llamadas.append(salida)
        if len(llamadas) == 1:
            with open(salida, "w", encoding="utf-8") as f:
                f.write("x")
            return salida
        raise RuntimeError("ffmpeg murió")

    monkeypatch.setattr(r, "ejecutar", _ejecutar_falso)
    # ejecutar() está mockeado (nunca toca ffmpeg ni disco salvo el archivo
    # falso de arriba), así que las rutas no necesitan existir de verdad.
    rutas = {1: "/fake/clon.mp4", 2: "/fake/voz.wav", 3: "/fake/musica.wav", "png:t1": "/fake/t1.png"}
    salida = str(tmp_path / "f.mp4")
    with pytest.raises(RuntimeError, match="ffmpeg murió"):
        motor.renderizar(_doc(), rutas, salida)
    assert not list(tmp_path.glob("f.mp4.tramo*"))
    assert not os.path.exists(salida)


@pytest.mark.slow
def test_imagen_estatica_sale_png(tmp_path, medios):
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    out = motor.renderizar(doc, {9: medios["foto"]}, str(tmp_path / "arte.png"))
    assert Image.open(out["archivo"]).size == (1080, 1080)
    assert out["miniatura"] == out["archivo"]


@pytest.mark.slow
def test_renderiza_sonido_mas_efecto_y_capa_translucida(tmp_path, medios):
    # C1 + I2 con ffmpeg real: el amix de sonido+efecto hacia [au_sonido] y
    # la capa escalada/atenuada (scale + format=rgba,colorchannelmixer) son
    # grafos que ffmpeg acepta y producen el video completo.
    doc = _doc()
    doc["pistas"][1]["clips"][0]["transform"]["escala"] = 1.5
    doc["pistas"][1]["clips"][0]["transform"]["opacidad"] = 0.5
    doc["pistas"][3]["clips"] = [
        {"id": "s1", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 3, "rol_audio": "sonido",
         "recorte": {"desde_ms": 0, "hasta_ms": 4000}, "audio": {"volumen": 1.0}},
        {"id": "e1", "inicio_ms": 1000, "duracion_ms": 500, "material_id": 3, "rol_audio": "efecto",
         "recorte": {"desde_ms": 0, "hasta_ms": 500}, "audio": {"volumen": 1.0}},
    ]
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2 and "audio" in streams
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)


@pytest.mark.slow
def test_pista_principal_corta_se_rellena_y_la_miniatura_se_acota(tmp_path, medios, monkeypatch):
    # I6 con ffmpeg real: la principal termina en 6000 y la voz sigue hasta
    # 7000 — el video sale de 7,0 s (tpad clona el último cuadro) y la
    # miniatura pedida en 6500 se acota al fin de la principal (5999) en vez
    # de pedirle a ffmpeg un cuadro que la pista no tiene.
    doc = _doc()
    doc["pistas"][0]["clips"][1]["duracion_ms"] = 2500
    doc["miniatura_ms"] = 6500
    pedidos = []
    original = r.miniatura

    def _miniatura(video, salida_png, t_ms):
        pedidos.append(t_ms)
        return original(video, salida_png, t_ms)
    monkeypatch.setattr(r, "miniatura", _miniatura)
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2 and "audio" in streams
    assert os.path.exists(out["miniatura"]) and Image.open(out["miniatura"]).size == (1080, 1920)
    assert pedidos == [5999]


def test_miniatura_lanza_si_ffmpeg_no_deja_el_png(tmp_path, monkeypatch):
    # antes, un `-ss` más allá del final terminaba "bien" sin archivo y el
    # error aparecía recién al subir a R2.
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: None)
    with pytest.raises(RuntimeError, match="miniatura"):
        r.miniatura(str(tmp_path / "v.mp4"), str(tmp_path / "m.png"), 1000)


def test_validar_detecta_tamano_incorrecto(tmp_path, medios):
    from final_edition.motor.compilador import Plan
    plan = Plan(ancho=1080, alto=1920, duracion_ms=8000, salida_audio=False)
    with pytest.raises(RuntimeError, match="tamaño"):
        r.validar(medios[1], plan)  # el clon es 540x960


@pytest.mark.slow
def test_ken_burns_renderiza_con_la_misma_duracion(tmp_path, medios):
    doc = _doc()
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    doc["pistas"][0]["clips"][1]["ken_burns"] = "out"
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "kb.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2 and (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)


@pytest.mark.slow
def test_clips_reordenados_de_la_misma_fuente_renderizan_su_tramo(tmp_path, medios):
    # Reordenar clips del mismo clon era lo que disparaba la memoria (1,39 GB):
    # con una entrada -ss/-t por clip cada uno decodifica solo lo suyo.
    doc = _doc()
    c1, c2 = doc["pistas"][0]["clips"]
    c1["transicion"] = None
    c2["inicio_ms"], c1["inicio_ms"] = 0, 3500
    doc["pistas"][0]["clips"] = [c2, c1]
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    out = motor.renderizar(doc, rutas, str(tmp_path / "reordenado.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)


@pytest.mark.slow
def test_musica_de_400_ms_con_fundido_de_1_s_renderiza(tmp_path, medios):
    # Capa 4c (1/10), con ffmpeg real: un audio de menos de 1 s con el
    # fundido de salida de la música (1 s) hacía `afade=t=out:st=-0.600` y
    # ffmpeg rechazaba el grafo ("out of range"): la final salía en error.
    doc = _doc()
    m1 = doc["pistas"][3]["clips"][0]
    m1.update(inicio_ms=6600, duracion_ms=400, recorte={"desde_ms": 0, "hasta_ms": 400})
    m1["audio"].update(fundido_entrada_ms=0, fundido_salida_ms=1000)
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "corto.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2 and "audio" in streams
