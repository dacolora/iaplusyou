"""Validaciones V1-V6 y E1-E4 del plan de clips, con el plan de ejemplo y sus variantes rotas."""
import copy

import pytest

from guiones import clips, lectura, plantillas
from tests.fixtures_guiones import CONFIG, GUION_CRUDO, HOOKS, PLAN, TEXTO

LEC = lectura.numerar(GUION_CRUDO, TEXTO)


def _correr(plan, config=CONFIG, quitadas=()):
    esperados = clips.hooks_esperados(LEC, config)
    p = clips.validar_forma(copy.deepcopy(plan), esperados)
    cs, hs = clips.calcular(p, LEC, config)
    renders = clips.renderizar(cs, hs, config, p["bloque_video"], plantillas.BLOQUE_GLOBAL_FABRICA)
    val, avisos = clips.validar(cs, hs, LEC, config, list(quitadas), renders, esperados)
    return {v["regla"]: v for v in val}, avisos, cs, hs


def test_plan_de_ejemplo_pasa_todo():
    val, avisos, cs, hs = _correr(PLAN)
    assert all(v["ok"] for v in val.values()), [v for v in val.values() if not v["ok"]]
    assert avisos == []
    assert [c["duracion"] for c in cs] == [10, 13] and cs[-1]["es_final"] and not cs[0]["es_final"]
    assert hs["hook_2"]["duracion"] == 11 and hs["hook_2"]["duracion_total_video"] == 24
    assert hs["hook_3"]["momentos"][0]["texto"] == HOOKS[1]


def test_hooks_esperados_cuando_se_elige_otro():
    assert clips.hooks_esperados(LEC, CONFIG) == ["hook_2", "hook_3"]
    assert clips.hooks_esperados(LEC, dict(CONFIG, hook="hook_2")) == ["original", "hook_3"]


def test_hook_elegido_reemplaza_la_linea_1():
    plan = copy.deepcopy(PLAN)
    plan["hooks"] = {"original": plan["hooks"].pop("hook_2"), "hook_3": plan["hooks"]["hook_3"]}
    val, _, cs, hs = _correr(plan, config=dict(CONFIG, hook="hook_2"))
    assert val["V1 fidelidad"]["ok"] and cs[0]["momentos"][0]["texto"] == HOOKS[0]
    assert hs["original"]["momentos"][0]["texto"] == GUION_CRUDO["lineas"][0]


def test_clip_de_mas_de_15_s_falla_v3_y_objetivo_v6():
    plan = copy.deepcopy(PLAN)
    plan["clips"][1]["momentos"][2]["aire"] = 5.0
    val, *_ = _correr(plan, config=dict(CONFIG, duracion_objetivo=20))
    assert not val["V3 duración"]["ok"] and "clip 2" in val["V3 duración"]["detalle"]
    assert not val["V6 total"]["ok"]


def test_linea_faltante_falla_v1_v2_y_e1():
    plan = copy.deepcopy(PLAN)
    plan["clips"][1]["momentos"][2]["dice"] = [5]
    val, *_ = _correr(plan)
    assert not val["V1 fidelidad"]["ok"] and not val["V2 cobertura"]["ok"] and not val["E1 líneas por clip"]["ok"]
    assert "6" in val["V2 cobertura"]["detalle"]


def test_linea_quitada_que_sigue_en_el_plan_falla_v2():
    val, *_ = _correr(PLAN, quitadas=[4])
    assert not val["V2 cobertura"]["ok"] and "sobran 4" in val["V2 cobertura"]["detalle"]


def test_final_con_dialogo_falla_v5():
    plan = copy.deepcopy(PLAN)
    plan["clips"][1]["momentos"] = plan["clips"][1]["momentos"][:3]
    val, *_ = _correr(plan)
    assert not val["V5 cierre"]["ok"]


def test_e2_e3_e4():
    plan = copy.deepcopy(PLAN)
    plan["clips"][0]["entornos"] = [1]
    del plan["hooks"]["hook_3"]
    plan["hooks"]["hook_2"]["estado_fin"] = "Holding a shoe."
    val, *_ = _correr(plan)
    assert not val["E3 entornos"]["ok"]
    assert not val["E4 hooks alternativos"]["ok"] and "hook_3" in val["E4 hooks alternativos"]["detalle"]
    plan2 = copy.deepcopy(PLAN)
    plan2["clips"][0]["momentos"].reverse()
    val2, *_ = _correr(plan2)
    assert not val2["E2 hook al inicio"]["ok"]


def test_aviso_de_continuidad_no_bloquea():
    plan = copy.deepcopy(PLAN)
    plan["clips"][1]["estado_inicio"] = "Holding a shoe."
    val, avisos, *_ = _correr(plan)
    assert all(v["ok"] for v in val.values()) and "Continuidad" in avisos[0]


def test_validar_forma():
    with pytest.raises(ValueError):
        clips.validar_forma({"clips": []}, [])
    with pytest.raises(ValueError):
        clips.validar_forma({"clips": [{"momentos": [{"dice": [1], "visual": " "}]}]}, [])
    p = clips.validar_forma({"clips": [{"momentos": [{"dice": ["1"], "aire": 99, "visual": "x"}, {"dice": [], "visual": "y"}]}],
                             "hooks": {"hook_9": {"momentos": [{"visual": "z"}]}}}, ["hook_2"])
    assert p["clips"][0]["momentos"][0] == {"dice": [1], "aire": 6.0, "visual": "x"}
    assert p["clips"][0]["momentos"][1]["dice"] is None and p["clips"][0]["titulo"] == "Clip 1"
    assert p["hooks"] == {} and p["bloque_video"]["props"] == clips.DEFECTOS_BLOQUE["props"]
