import copy
import json
import os

import pytest

from final_edition import documento as d
from final_edition.motor import tramos as tr

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def _con_textos(n, inicio_ms=0, dur_ms=7000):
    doc = _doc()
    pista = doc["pistas"][1]
    base = pista["clips"][0]
    pista["clips"] = []
    for i in range(n):
        c = copy.deepcopy(base); c["id"] = f"t{i}"; c["inicio_ms"] = inicio_ms; c["duracion_ms"] = dur_ms
        c["texto"] = {"literal": f"texto {i}"}
        pista["clips"].append(c)
    return doc


def test_capas_cuenta_textos_imagenes_superpuestos_no_subtitulos():
    doc = _doc()
    capas = tr.capas_overlay(doc)
    assert [c["clip_id"] for c in capas] == ["t1"]


def test_un_tramo_si_cabe():
    assert tr.partir(_doc()) == [(0, 7000)]


def test_parte_en_fronteras_de_clips_cuando_se_pasa():
    # 40 textos en los primeros 3,5 s y 40 en los últimos: 80 > 60 en total,
    # pero cada mitad cabe → 2 tramos en la frontera del clip principal.
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"][0]["transicion"] = None
    assert tr.partir(doc) == [(0, 3500), (3500, 7000)]


def test_no_corta_dentro_de_una_transicion():
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    # transición de 500 ms en el clip 1: ocupa [3500, 4000); ningún corte cae ahí
    cortes = tr.partir(doc)
    fines = [b for _a, b in cortes]
    assert not any(3500 <= c < 4000 for c in fines)
    assert 4000 in fines
    assert cortes[-1][1] == 7000


def test_punto_medio_dentro_de_transicion_se_empuja_y_acepta_el_tramo():
    # clip 1: 0–1500 con transición de 1500 ms → ocupa [1500, 3000); clip 2: 1500–7000.
    # 40 textos en [0,1500) y 40 en [1500,7000): el tramo (0,3000) toca 80 capas (> 60),
    # su punto medio 0 + max(2000, 1500) = 2000 cae dentro de la transición y se empuja
    # a 3000 = fin del tramo, así que el tramo se acepta entero en vez de cortarse en 2000.
    doc = _con_textos(40, 0, 1500)
    extra = _con_textos(40, 1500, 5500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    principal = doc["pistas"][0]
    principal["clips"][0]["duracion_ms"] = 1500
    principal["clips"][0]["recorte"] = {"desde_ms": 0, "hasta_ms": 1500}
    principal["clips"][0]["transicion"] = {"tipo": "fundido", "duracion_ms": 1500}
    principal["clips"][1]["inicio_ms"] = 1500
    principal["clips"][1]["duracion_ms"] = 5500
    principal["clips"][1]["recorte"] = {"desde_ms": 1500, "hasta_ms": 7000}
    cortes = tr.partir(doc)
    assert cortes == [(0, 3000), (3000, 7000)]
    assert tr.contar(doc, 0, 3000) == 80  # aceptado por encima del presupuesto a propósito


def test_clip_largo_se_parte_por_tiempo():
    doc = _con_textos(50, 0, 2000)
    extra = _con_textos(50, 2000, 5000)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"] = [doc["pistas"][0]["clips"][0]]
    doc["pistas"][0]["clips"][0]["duracion_ms"] = 7000
    doc["pistas"][0]["clips"][0]["recorte"]["hasta_ms"] = 7000
    doc["pistas"][0]["clips"][0]["transicion"] = None
    cortes = tr.partir(doc)
    assert cortes[0] == (0, 2000) and cortes[-1][1] == 7000
    for a, b in cortes:
        assert tr.contar(doc, a, b) <= tr.PRESUPUESTO_OVERLAYS


def test_instante_imposible_lanza_error():
    with pytest.raises(ValueError, match="mismo instante"):
        tr.partir(_con_textos(61, 0, 7000))


def test_fronteras_usan_la_misma_pista_principal_que_el_compilador():
    # documento.pista_principal: la primera pista `video` NO oculta (una
    # imagen listada antes es una capa). Una pista de video oculta que va
    # primero no debe aportar fronteras.
    doc = _doc()
    doc["pistas"].insert(0, {"id": "p_img", "tipo": "imagen", "oculta": False, "clips": []})
    doc["pistas"].insert(0, {"id": "p_vieja", "tipo": "video", "oculta": True, "clips": [
        {"id": "x1", "inicio_ms": 0, "duracion_ms": 1000, "material_id": 1, "transicion": None}]})
    assert tr._fronteras_seguras(doc, 7000) == [4000]
    assert tr._intervalos_transicion(doc) == [(3500, 4000)]
