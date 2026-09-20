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


def test_velocidad_aplica_setpts():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    doc["pistas"][0]["clips"][0]["transicion"] = None
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "setpts=(PTS-STARTPTS)/2.0" in plan.filtergraph


def test_transicion_con_velocidad_escala_la_cola():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    plan = c.compilar(doc, RUTAS, con_ass=False)
    # 3500 ms de salida a 2x = 7000 ms de fuente, más la cola de transición
    # (500 ms de salida) también a 2x = 1000 ms de fuente -> 8000.
    assert "trim=start=0.000:end=8.000" in plan.filtergraph
    # el offset del xfade es tiempo de SALIDA: no lo toca la velocidad.
    assert "xfade=transition=fade:duration=0.500:offset=3.500" in plan.filtergraph


def test_tres_clips_corte_y_fundido():
    # corte seco 0-2000, fundido 500 ms 2000-5000, corte seco 5000-7000.
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [
        {"id": "c1", "inicio_ms": 0, "duracion_ms": 2000, "material_id": 1,
         "recorte": {"desde_ms": 0, "hasta_ms": 2000}},
        {"id": "c2", "inicio_ms": 2000, "duracion_ms": 3000, "material_id": 1,
         "recorte": {"desde_ms": 2000, "hasta_ms": 5000},
         "transicion": {"tipo": "fundido", "duracion_ms": 500}},
        {"id": "c3", "inicio_ms": 5000, "duracion_ms": 2000, "material_id": 1,
         "recorte": {"desde_ms": 5000, "hasta_ms": 7000}},
    ]
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {1: "/m/clon.mp4"}, con_ass=False)
    # el corte seco entre c1 y c2 necesita su propio timebase antes del xfade
    # que sigue (concat sale a 1/1000000; xfade exige 1/fps en ambas patas).
    assert "concat=n=2:v=1:a=0,settb=1/30[vx1]" in plan.filtergraph
    assert "xfade=transition=fade:duration=0.500:offset=5.000[vc]" in plan.filtergraph
    assert plan.duracion_ms == 7000


def test_dos_voces_en_una_pista_se_suman():
    doc = _doc()
    doc["pistas"][2]["clips"] = [
        {"id": "v1", "inicio_ms": 0, "duracion_ms": 3000, "material_id": 2, "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 3000}, "audio": {"volumen": 1.0}},
        {"id": "v2", "inicio_ms": 3500, "duracion_ms": 3500, "material_id": 2, "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 3500}, "audio": {"volumen": 1.0}},
    ]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "adelay=3500|3500" in plan.filtergraph
    assert "amix=inputs=2:normalize=0[au_voz]" in plan.filtergraph
    # una vez como salida del amix, otra vez como entrada de la mezcla final.
    assert plan.filtergraph.count("[au_voz]") == 2


def test_voz_que_empieza_tarde_lleva_adelay():
    doc = _doc()
    doc["pistas"][2]["clips"][0]["inicio_ms"] = 1500
    doc["pistas"][2]["clips"][0]["duracion_ms"] = 5500
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "adelay=1500|1500" in plan.filtergraph


def test_keyframes_de_posicion_generan_expresion_en_t():
    doc = _doc()
    # t1 ya tiene x=0.5 de base; con >= 2 keyframes de posición la expresión
    # deja de ser la constante de _expr_animacion y pasa a ser lineal por
    # tramos en t. x=0.2 -> px=216, caja 400 px centrada -> 216-200=16;
    # x=0.8 -> px=864 -> 864-200=664 (formato 9:16, lienzo 1080 de ancho).
    doc["pistas"][1]["clips"][0]["keyframes"] = [
        {"t_ms": 0, "transform": {"x": 0.2}},
        {"t_ms": 2000, "transform": {"x": 0.8}},
    ]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "if(lt(t," in plan.filtergraph
    assert "16.000" in plan.filtergraph
    assert "664.000" in plan.filtergraph


def test_fundidos_de_audio_solo_en_bordes_reales():
    # ventana=(0,3500) corta la voz y la música (que duran 7000) a mitad de
    # camino: ese corte no es su fin real, así que no debe sonar el fundido
    # de salida (sonaría a mitad de frase, y el tramo siguiente entraría
    # sin la mitad que ya se "gastó" en este fundido).
    plan = c.compilar(_doc(), RUTAS, ventana=(0, 3500), con_ass=False)
    assert "afade=t=out" not in plan.filtergraph


def test_ventana_sin_clips_de_audio_emite_silencio_si_el_documento_tiene_audio():
    # La voz y la música terminan con el primer tramo (3500): la ventana
    # (3500, 7000) no tiene ningún clip de audio activo, pero el documento sí
    # tiene audio en general — sin relleno, ese tramo saldría sin stream de
    # audio y `concat -c copy` cortaría el audio del video entero ahí.
    doc = _doc()
    doc["pistas"][2]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][2]["clips"][0]["recorte"]["hasta_ms"] = 3500
    doc["pistas"][3]["clips"][0]["duracion_ms"] = 3500
    doc["pistas"][3]["clips"][0]["recorte"]["hasta_ms"] = 3500
    plan = c.compilar(doc, RUTAS, ventana=(3500, 7000), con_ass=False)
    assert "anullsrc=r=48000:cl=stereo[aout]" in plan.filtergraph
    assert plan.salida_audio is True


def test_documento_sin_audio_no_inventa_silencio():
    doc = _doc()
    doc["pistas"] = doc["pistas"][:2]  # solo video y texto, sin pistas de audio
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "anullsrc" not in plan.filtergraph
    assert plan.salida_audio is False


def test_dos_fuentes_en_la_principal_es_error():
    doc = _doc()
    doc["pistas"][0]["clips"][1]["material_id"] = 99
    with pytest.raises(ValueError, match="más de una fuente"):
        c.compilar(doc, {**RUTAS, 99: "/m/otro.mp4"}, con_ass=False)


def test_ruta_faltante_es_error_con_el_clip():
    rutas_incompletas = {k: v for k, v in RUTAS.items() if k != "png:t1"}
    with pytest.raises(ValueError, match="t1"):
        c.compilar(_doc(), rutas_incompletas, con_ass=False)


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
