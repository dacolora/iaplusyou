import copy
import json
import os

import pytest

from final_edition import documento as d

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def cargar(nombre):
    with open(os.path.join(FIX, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_valida_el_fixture_basico_y_deriva_duracion():
    doc = d.validar(cargar("video_basico.json"))
    assert d.duracion_ms(doc) == 7000


def test_imagen_sin_clips_de_tiempo_dura_cero():
    doc = d.nuevo_imagen("1:1")
    assert d.validar(doc)["formato"] == "1:1"
    assert d.duracion_ms(doc) == 0


def test_rechaza_formato_desconocido():
    doc = cargar("video_basico.json")
    doc["formato"] = "3:2"
    with pytest.raises(d.DocumentoInvalido, match="formato"):
        d.validar(doc)


def test_rechaza_mas_de_ocho_pistas():
    doc = cargar("video_basico.json")
    base = doc["pistas"][1]
    for i in range(6):
        p = copy.deepcopy(base); p["id"] = f"extra{i}"; p["clips"] = []
        doc["pistas"].append(p)
    with pytest.raises(d.DocumentoInvalido, match="8 pistas"):
        d.validar(doc)


def test_rechaza_tiempos_no_enteros_y_negativos():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["inicio_ms"] = 0.5
    with pytest.raises(d.DocumentoInvalido, match="inicio_ms"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["duracion_ms"] = -1
    with pytest.raises(d.DocumentoInvalido, match="duracion_ms"):
        d.validar(doc)


def test_rechaza_posicion_fuera_de_0_1():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["transform"]["x"] = 1.2
    with pytest.raises(d.DocumentoInvalido, match="transform.x"):
        d.validar(doc)


def test_rechaza_clips_solapados_en_la_pista_principal():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][1]["inicio_ms"] = 3000
    with pytest.raises(d.DocumentoInvalido, match="solapa"):
        d.validar(doc)


def test_texto_debe_ser_literal_o_variable():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["texto"] = {"literal": "Hola", "variable": "hook"}
    with pytest.raises(d.DocumentoInvalido, match="literal o variable"):
        d.validar(doc)


def test_precio_nunca_se_convierte():
    doc = d.validar(cargar("video_basico.json"))
    assert doc["variables"]["precios"] == {"es_CO": 89900, "en_US": 24.99}
    assert "es_MX" not in doc["variables"]["precios"]


def test_nuevo_video_es_valido_y_vacio():
    doc = d.nuevo_video("9:16")
    doc = d.validar(doc)
    assert doc["esquema"] == d.ESQUEMA_ACTUAL
    assert [p["tipo"] for p in doc["pistas"]] == ["video"]
    assert d.duracion_ms(doc) == 0
