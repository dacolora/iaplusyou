import json
import os

from final_edition import documento as d, estimar

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def test_estimado_crece_con_duracion_capas_y_transiciones():
    doc = _doc()
    base = estimar.segundos(doc)
    assert base >= estimar.MIN_S
    doc2 = _doc(); doc2["pistas"][0]["clips"][0]["transicion"] = None
    assert estimar.segundos(doc2) < base


def test_mas_nucleos_reduce_casi_proporcional():
    # Con 7 s el mínimo de 20 s pisa el estimado; se mide con un video largo.
    doc = _doc()
    doc["pistas"][0]["clips"][1]["duracion_ms"] = 53500          # total 57 s
    doc["pistas"][0]["clips"][1]["recorte"]["hasta_ms"] = 57000
    assert estimar.segundos(doc, nucleos=4) <= estimar.segundos(doc) // 2


def test_texto_humano():
    assert estimar.texto_humano(45) == "~1 min"
    assert estimar.texto_humano(150) == "~3 min"
    assert estimar.texto_humano(15) == "~20 s"
