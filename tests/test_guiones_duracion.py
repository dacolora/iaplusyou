"""Fórmula de duración del spec del cliente §2.2-§2.3 (puro)."""
import pytest

from guiones import duracion

LEC = {"lineas": [{"n": 1, "texto": "uno dos tres"}, {"n": 2, "texto": "cuatro cinco"}, {"n": 3, "texto": "seis"},
                  {"n": 4, "texto": "siete ocho"}],
       "hooks": [{"id": "hook_2", "texto": "otro gancho distinto"}]}


def test_textos_efectivos_y_hook():
    assert duracion.textos_efectivos(LEC)[1] == "uno dos tres"
    assert duracion.textos_efectivos(LEC, "hook_2")[1] == "otro gancho distinto"
    with pytest.raises(ValueError):
        duracion.textos_efectivos(LEC, "hook_9")


def test_conservadas_y_bloques_quitados():
    textos = duracion.textos_efectivos(LEC)
    assert duracion.conservadas(textos, [2]) == [(1, "uno dos tres"), (3, "seis"), (4, "siete ocho")]
    assert duracion.bloques_quitados(textos, [2, 3]) == ["cuatro cinco seis"]
    assert duracion.bloques_quitados(textos, [4, 2]) == ["cuatro cinco", "siete ocho"]


def test_estimado_previo():
    lineas = [(1, "a b c d e f"), (2, "g h i j k l")]          # 12 palabras
    assert duracion.estimado_previo(lineas, 2.4, 0.6) == round(12 / 2.4 + 1.2 + 1.0, 1)
    assert duracion.estimado_previo([], 2.4, 0.6) == 0.0


def test_calcular_clip_ejemplo_del_spec():
    textos = {3: " ".join(["w"] * 12), 6: " ".join(["w"] * 16)}  # 5 s y 6,67 s a 2,4 palabras/s
    momentos = [{"dice": None, "aire": 0.5, "visual": "He lifts ONE pair."},
                {"dice": [3], "aire": 0.1, "visual": "He holds it up."},
                {"dice": [6], "aire": 0.6, "visual": "Insert macro."}]
    c = duracion.calcular_clip(momentos, textos, 2.4)
    assert c["duracion"] == 13 and c["palabras"] == 28
    assert [(m["t_ini"], m["t_fin"]) for m in c["momentos"]] == [(0.0, 0.5), (0.5, 5.6), (5.6, 13.0)]
    assert c["momentos"][0]["texto"] == "" and c["momentos"][0]["dice"] == []
    assert c["momentos"][1]["textos"] == [textos[3]]


def test_calcular_clip_minimo_y_exceso():
    corto = duracion.calcular_clip([{"dice": [1], "aire": 0.2, "visual": "x"}], {1: "a b c d e f"}, 2.4)
    assert corto["duracion"] == 5 and corto["momentos"][-1]["t_fin"] == 5.0
    largo = duracion.calcular_clip([{"dice": [1], "aire": 1.0, "visual": "x"}], {1: " ".join(["w"] * 38)}, 2.4)
    assert largo["duracion"] == 17


def test_calcular_clip_numero_exacto_no_sube():
    c = duracion.calcular_clip([{"dice": [1], "aire": 0.0, "visual": "x"}], {1: " ".join(["w"] * 24)}, 2.4)
    assert c["duracion"] == 10
