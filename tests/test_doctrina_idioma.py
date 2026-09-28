"""Doctrina, bloque 3: la revisión de la pieza, los pedidos al cliente y los
avisos de la revisión rápida en el idioma del proyecto (spec 2026-09-26 §B4,
§B8). Sin red: `analisis._llamar_contando` y `pedidos._llamar` falsos."""
import json

import idiomas
from tests.test_doctrina_revisor import _datos, _pieza, _preparar_revision, _respuesta

ORDEN_EN = idiomas.orden_idioma("en")


def test_revisar_en_ingles(base_temporal, monkeypatch):
    from doctrina import revisor
    cf_id = _pieza(monkeypatch)
    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    revisor.revisar("acme", cf_id)
    s = llamadas[0]["system"][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Escribe en inglés simple" in s and "Escribe en español" not in s


def test_revisar_en_espanol_por_defecto(base_temporal, monkeypatch):
    from doctrina import revisor
    cf_id = _pieza(monkeypatch)
    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
    revisor.revisar("acme", cf_id)
    assert "Escribe en español simple" in llamadas[0]["system"][1]["text"]


def test_pedidos_en_ingles(base_temporal, monkeypatch):
    from doctrina import pedidos
    from tests.test_doctrina_pedidos import _producto_con_piezas
    fila = _producto_con_piezas(monkeypatch)
    vistos = []
    monkeypatch.setattr(pedidos, "_llamar", lambda mensaje, system: vistos.append(system) or (
        json.dumps({"pedidos": [{"texto": "Paste a real review", "para_que": "proof"}]}), 700, 900))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    pedidos.resumir("acme", fila)
    s = vistos[0][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN) and "para el cliente, en inglés, en imperativo" in s


def test_avisos_de_la_revision_rapida_en_ingles_y_espanol_intacto():
    from doctrina import revisor
    datos = _datos(guion={"bloques": [{"rol": "hook", "texto_voz": "x"}]})
    assert revisor.reglas(datos)[-1]["texto"] == "El guion no termina con una llamada a la acción."
    with idiomas.en_idioma("en"):
        assert revisor.reglas(datos)[-1]["texto"] == "The script doesn't end with a call to action."
