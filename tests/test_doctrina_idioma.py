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


# -------------------------------------------------------------- bloque 4 ---

def test_diagnostico_en_ingles(monkeypatch):
    """Doctrina, bloque 4: la orden de idioma rodea las instrucciones del
    diagnóstico y las pistas salen por el catálogo."""
    from doctrina import diagnostico
    from sprints import analisis
    vistos = []
    respuesta = json.dumps({"causas": [{"codigo": "gancho", "detalle": "d", "evidencia": "e"}],
                            "siguiente": {"que": "gancho", "porque": "p", "hipotesis": "h"}, "aprendizaje": "a"})
    monkeypatch.setattr(analisis, "_llamar_contando",
                        lambda content, max_tokens, system: vistos.append(system) or (respuesta, 10, 5))
    diagnostico.diagnosticar({"pais": "CO", "nombre": "x"}, {"motivo": "m", "numeros": {}}, [], {}, idioma="en")
    s = vistos[0][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN) and "inglés simple" in s and "spañol simple" not in s
    diagnostico.diagnosticar({"pais": "CO", "nombre": "x"}, {"motivo": "m", "numeros": {}}, [], {})
    assert "español simple" in vistos[1][1]["text"]
    pistas = lambda: diagnostico.pistas([{"thruplay_rate": 0.1}], {"thruplay_min": 0.2}, {})[0]["texto"]
    assert pistas() == "Pocos pasan de los primeros segundos: ThruPlay 10 % (mínimo 20 %)."
    with idiomas.en_idioma("en"):
        assert pistas() == "Few get past the first seconds: ThruPlay 10 % (minimum 20 %)."
        motivo = diagnostico.decision_rescate({"causas": [{"codigo": "landing"}], "siguiente": {"que": "landing"}})["motivo"]
        assert motivo.startswith("Diagnosis: the landing page doesn't continue the ad — next: review the landing page")


def test_aprendizaje_del_motor_en_ingles():
    from doctrina import aprendizajes
    pz = {"pais": "CO", "nombre": "x", "angulo": {"gancho": "Cold feet?", "lead": "secreto", "consciencia": "consciente_del_problema"},
          "productos_ids": ["Hcozy"]}
    v = {"veredicto": "ganador", "motivo": "m", "numeros": {"ctr": 2.15, "thruplay_rate": 0.34}}
    assert aprendizajes.desde_veredicto(pz, v)["texto"] == \
        "Ganó en CO: «Cold feet?» (arranque secreto, audiencia consciente del problema) para Hcozy — CTR 2,1 %, ThruPlay 34 %."
    with idiomas.en_idioma("en"):
        assert aprendizajes.desde_veredicto(pz, v)["texto"] == \
            "Won in CO: «Cold feet?» (secret lead, problem aware audience) for Hcozy — CTR 2.1 %, ThruPlay 34 %."
