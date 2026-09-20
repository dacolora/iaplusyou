import json
import os

import pytest

from final_edition import documento as d, mezcla
from final_edition.motor import compilador as c

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def _doc(idioma="es", pais="CO"):
    with open(os.path.join(FIX, "video_basico.json"), encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), idioma, pais)


RUTAS = {1: "/m/clon.mp4", 2: "/m/voz.wav", 3: "/m/musica.wav", "png:t1": "/m/t1.png", "ass": "/m/sub.ass"}


def _esperado():
    with open(os.path.join(FIX, "esperado_basico.filtergraph.txt"), encoding="utf-8") as f:
        lineas = [l for l in f.read().splitlines() if l.strip()]
    mezcla_txt = mezcla.filtro_mezcla(voz="[au_voz]", sonido=None, musica="[au_musica]",
                                      volumenes=mezcla.volumenes_para("equilibrada"))
    return lineas + mezcla_txt.split(";")


def test_filtergraph_del_fixture_basico_sin_ass():
    plan = c.compilar(_doc(), RUTAS, con_ass=False)
    assert plan.filtergraph.split(";") == _esperado()
    assert [e["ruta"] for e in plan.entradas] == ["/m/clon.mp4", "/m/t1.png", "/m/voz.wav", "/m/musica.wav"]
    assert plan.entradas[3]["opciones"] == ["-stream_loop", "-1"]
    assert plan.salida_audio and plan.duracion_ms == 7000 and (plan.ancho, plan.alto) == (1080, 1920)
    assert plan.overlays == 1


def test_con_ass_agrega_un_solo_filtro_subtitles_y_el_texto():
    plan = c.compilar(_doc(), RUTAS, con_ass=True)
    assert plan.filtergraph.count("subtitles=") == 1
    assert "subtitles='/m/sub.ass'" in plan.filtergraph
    assert plan.ass_texto.startswith("[Script Info]")
    # los textos libres siguen siendo PNG aunque haya ASS
    assert "[1:v]overlay" in plan.filtergraph


def test_sin_subtitulos_en_el_idioma_no_hay_filtro():
    plan = c.compilar(_doc("en", "US"), RUTAS, con_ass=True)
    assert "subtitles=" not in plan.filtergraph and plan.ass_texto == ""


def test_ventana_desplaza_tiempos_a_cero():
    plan = c.compilar(_doc(), RUTAS, ventana=(3500, 7000), con_ass=False)
    assert "trim=start=3.500:end=7.000" in plan.filtergraph
    assert "xfade" not in plan.filtergraph
    assert plan.duracion_ms == 3500
    assert "overlay" not in plan.filtergraph  # el texto t1 termina en 2700 < 3500


def test_imagen_estatica_sin_audio_ni_tiempo():
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {9: "/m/foto.png"})
    assert plan.salida_video and not plan.salida_audio and plan.duracion_ms == 0
    assert "scale=1080:1080" in plan.filtergraph and "overlay" not in plan.filtergraph


def test_velocidad_aplica_setpts_y_atempo():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    doc["pistas"][0]["clips"][0]["audio"]["volumen"] = 1.0
    doc["pistas"][0]["clips"][0]["transicion"] = None
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "setpts=(PTS-STARTPTS)/2.0" in plan.filtergraph


def test_pista_oculta_y_silenciada_se_ignoran():
    doc = _doc()
    doc["pistas"][1]["oculta"] = True
    doc["pistas"][3]["silenciada"] = True
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "overlay" not in plan.filtergraph and "[au_musica]" not in plan.filtergraph


def test_transiciones_mapean_a_xfade():
    assert c._transicion_xfade("fundido") == "fade"
    assert c._transicion_xfade("deslizar") == "slideleft"
    assert c._transicion_xfade("zoom") == "zoomin"
    assert c._transicion_xfade("desenfoque") == "fadeblack"
