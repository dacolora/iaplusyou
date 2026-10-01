import copy
import json
import os
import subprocess

import pytest
from PIL import Image

from final_edition import cortes, documento as d, encuadre, fotos, motor
from final_edition.motor import render as r

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


@pytest.fixture(scope="module")
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("medios_editor")
    clon = str(carpeta / "clon.mp4"); voz = str(carpeta / "voz.wav"); musica = str(carpeta / "musica.wav")
    png = str(carpeta / "t1.png"); foto = str(carpeta / "foto.png"); horizontal = str(carpeta / "horizontal.mp4")
    vertical = str(carpeta / "vertical.mp4"); rotado = str(carpeta / "rotado.mp4")
    roja_azul = str(carpeta / "roja_azul.png"); roja_azul_jpg = str(carpeta / "foto_7.jpg")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30", "-t", "8", "-pix_fmt", "yuv420p", clon], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "4", "-pix_fmt", "yuv420p", horizontal], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30", "-t", "2", "-pix_fmt", "yuv420p", vertical], check=True)
    # grabado «de pie»: codificado 1280x720 con una marca de rotación de 90°
    subprocess.run(base + ["-display_rotation:v:0", "90", "-i", horizontal, "-t", "2", "-c", "copy", rotado], check=True)
    # capa 5b: una foto 400x200 roja a la izquierda y azul a la derecha,
    # preparada como en `preparar_rutas` (rutas["foto:7"])
    im = Image.new("RGB", (400, 200), (255, 0, 0))
    im.paste((0, 0, 255), (200, 0, 400, 200))
    im.save(roja_azul)
    fotos.preparar(roja_azul, roja_azul_jpg)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "7", voz], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "4", musica], check=True)
    Image.new("RGBA", (400, 200), (255, 0, 0, 200)).save(png)
    Image.new("RGB", (800, 600), (0, 128, 255)).save(foto)
    return {1: clon, 2: voz, 3: musica, 4: horizontal, 5: vertical, 6: rotado, "foto:7": roja_azul_jpg,
            "png:t1": png, "foto": foto}


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
@pytest.mark.parametrize("transicion", [None, {"tipo": "fundido", "duracion_ms": 500}])
def test_un_video_horizontal_entre_verticales_se_renderiza(tmp_path, medios, transicion):
    # Un video horizontal subido a una edición vertical: al llevarlo al
    # cuadro, el `scale` deja una proporción de píxel apenas distinta de 1
    # (3413:3414) y `concat` rechazaba el corte seco («Nothing was written»).
    doc = _doc()
    doc["pistas"][0]["clips"][0]["transicion"] = transicion
    doc["pistas"][0]["clips"][1].update(material_id=4, recorte={"desde_ms": 0, "hasta_ms": 3500})
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 7.0) <= 0.3 and "audio" in streams


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
    # la voz y la música cruzan todas las uniones sin un solo hueco
    assert [t for t in _silencios(out["archivo"]) if t < 6.9] == []


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
    # "ass": con libass (el VPS) el compilador escribe ahí los subtítulos; sin
    # esta ruta la prueba fallaba con KeyError solo en el servidor.
    rutas = {1: "/fake/clon.mp4", 2: "/fake/voz.wav", 3: "/fake/musica.wav", "png:t1": "/fake/t1.png",
             "ass": str(tmp_path / "s.ass")}
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


# ---- capa 5b: fotos en la principal y encuadre (renders reales) -----------

def _cuadro(video, t_ms, tmp_path):
    """El cuadro de `video` en `t_ms`, como imagen RGB de Pillow."""
    png = str(tmp_path / f"cuadro_{t_ms}.png")
    r.miniatura(video, png, t_ms)
    return Image.open(png).convert("RGB")


def _solo_principal(clips):
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = clips
    return d.resolver(d.validar(doc), "es", "CO")


def _foto(clip_id="f1", inicio=0, dur=1000, **extra):
    return {"id": clip_id, "inicio_ms": inicio, "duracion_ms": dur, "material_id": 7, "foto": True, **extra}


@pytest.mark.slow
def test_un_video_que_se_funde_en_una_foto_dura_lo_de_la_linea_de_tiempo(tmp_path, medios):
    doc = _solo_principal([
        {"id": "v0", "inicio_ms": 0, "duracion_ms": 2000, "material_id": 1, "recorte": {"desde_ms": 0, "hasta_ms": 2000},
         "transicion": {"tipo": "fundido", "duracion_ms": 500}},
        _foto(inicio=2000, dur=3000)])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 5.0) <= 0.2 and "audio" not in streams


@pytest.mark.slow
def test_una_foto_con_zoom_lento_que_se_funde_en_un_video(tmp_path, medios):
    # D2: la cola del fundido sale del mismo `loop` de la foto (2 s + 2 s = 4 s)
    doc = _solo_principal([
        _foto(dur=2000, ken_burns="in", transicion={"tipo": "fundido", "duracion_ms": 500, "modo": "solape"}),
        {"id": "v1", "inicio_ms": 2000, "duracion_ms": 2000, "material_id": 1, "recorte": {"desde_ms": 0, "hasta_ms": 2000}}])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 4.0) <= 0.2


@pytest.mark.slow
@pytest.mark.parametrize("x, rojo", [(0, True), (1, False)])
def test_encuadre_llenar_muestra_la_parte_elegida_de_la_foto(tmp_path, medios, x, rojo):
    doc = _solo_principal([_foto(encuadre={"x": x}, ancho_px=400, alto_px=200)])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    r_, _g, b = _cuadro(out["archivo"], 500, tmp_path).getpixel((540, 960))
    if rojo:
        assert r_ > 200 and b < 60
    else:
        assert b > 200 and r_ < 60


@pytest.mark.slow
def test_encuadre_ajustar_la_foto_entera_sobre_su_fondo_desenfocado(tmp_path, medios):
    # 400x200 en 9:16: primer plano 1080x540 en las filas 690-1229; arriba y
    # abajo, la misma foto llenando un lienzo chico, desenfocada y agrandada.
    doc = _solo_principal([_foto(encuadre={"modo": "ajustar"}, ancho_px=400, alto_px=200)])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    cuadro = _cuadro(out["archivo"], 500, tmp_path)
    for punto in ((270, 960), (270, 700)):
        r_, _g, b = cuadro.getpixel(punto)
        assert r_ > 200 and b < 60, punto
    for punto in ((810, 960), (810, 1220)):
        r_, _g, b = cuadro.getpixel(punto)
        assert b > 200 and r_ < 60, punto
    for punto in ((540, 600), (540, 1300)):
        r_, _g, b = cuadro.getpixel(punto)
        assert r_ > 60 and b > 60, punto
    # El punto que distingue «ajustar» de «llenar»: arriba a la izquierda, en
    # «llenar» se ve la mitad roja pura; en «ajustar» el fondo desenfocado
    # mezcla el rojo con el azul (revisión de la Tarea 3).
    r_, _g, b = cuadro.getpixel((480, 300))
    assert r_ > 60 and b > 60, (r_, b)


@pytest.mark.slow
def test_video_grabado_de_pie_con_encuadre_se_renderiza(tmp_path, medios):
    info = cortes.ffprobe_json(medios[6])
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (1280, 720)
    ancho, alto = encuadre.medidas_visibles(stream)
    assert (ancho, alto) == (720, 1280)
    doc = _solo_principal([{"id": "v0", "inicio_ms": 0, "duracion_ms": 2000, "material_id": 6,
                            "recorte": {"desde_ms": 0, "hasta_ms": 2000}, "encuadre": {"modo": "ajustar"},
                            "ancho_px": ancho, "alto_px": alto}])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 2.0) <= 0.2


@pytest.mark.slow
def test_corte_seco_entre_un_horizontal_ajustado_y_un_vertical(tmp_path, medios):
    # D3 con encuadre: el overlay del «ajustar» y el scale del vertical
    # llegan al concat con la misma proporción de píxel.
    doc = _solo_principal([
        {"id": "v0", "inicio_ms": 0, "duracion_ms": 2000, "material_id": 4, "recorte": {"desde_ms": 0, "hasta_ms": 2000},
         "encuadre": {"modo": "ajustar"}, "ancho_px": 1280, "alto_px": 720},
        {"id": "v1", "inicio_ms": 2000, "duracion_ms": 2000, "material_id": 5, "recorte": {"desde_ms": 0, "hasta_ms": 2000},
         "encuadre": {"modo": "llenar", "zoom": 1.5, "x": 0.2}, "ancho_px": 720, "alto_px": 1280}])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 4.0) <= 0.2


@pytest.mark.slow
def test_ocho_fotos_sin_sonido_salen_en_dos_tramos(tmp_path, medios):
    doc = _solo_principal([_foto(f"f{i}", inicio=i * 1000, ken_burns="in" if i % 2 else None) for i in range(8)])
    out = motor.renderizar(doc, medios, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert out["tramos"] == 2
    assert abs(dur - 8.0) <= 0.3 and "audio" not in streams
