import json
import os

import pytest

from final_edition import geometria as g

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "geometria_casos.json")


def _casos():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("caso", _casos(), ids=lambda c: c["nombre"])
def test_caja_coincide_con_la_tabla_compartida(caso):
    ancho, alto = caso["capa"]
    assert g.caja(caso["transform"], ancho, alto, caso["formato"]) == caso["esperado"]


def test_casos_expuestos_para_js():
    assert g.CASOS == _casos()


def test_interpolar_sin_keyframes_devuelve_base():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    assert g.interpolar([], 1234, base) == base


def test_interpolar_lineal_entre_dos_keyframes():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    kfs = [{"t_ms": 0, "transform": {**base, "opacidad": 0.0, "y": 0.6}},
           {"t_ms": 300, "transform": {**base, "opacidad": 1.0, "y": 0.5}}]
    r = g.interpolar(kfs, 150, base)
    assert r["opacidad"] == pytest.approx(0.5)
    assert r["y"] == pytest.approx(0.55)


def test_interpolar_fuera_del_rango_se_clava_en_los_extremos():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    kfs = [{"t_ms": 100, "transform": {**base, "opacidad": 0.2}},
           {"t_ms": 200, "transform": {**base, "opacidad": 0.8}}]
    assert g.interpolar(kfs, 0, base)["opacidad"] == 0.2
    assert g.interpolar(kfs, 999, base)["opacidad"] == 0.8
