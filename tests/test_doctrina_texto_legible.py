"""PND-264: un campo del ángulo que Claude manda como dict o lista llegaba con su `repr` («{'quien': …}», «['a', 'b']»)
y la idea se pintaba con corchetes. `doctrina._texto` lo vuelve texto legible; se prueba en sus tres usos: «Evaluar con
IA» de Triple Whale (`triple_whale.analisis.parsear`), la «Evaluación con IA» de Meta (`meta_rendimiento.analisis.
parsear`, que reusa el de Triple Whale) y las ideas de Sprints (`sprints.ideas.parsear`)."""
import json

import doctrina

AUDIENCIA = {"quien": "mamás con niños chicos", "edad": "30-45"}
DESEO = ["orden en casa", " sin   esfuerzo "]
LEGIBLE_AUDIENCIA = "mamás con niños chicos; 30-45"
LEGIBLE_DESEO = "orden en casa; sin esfuerzo"


def _sin_repr(angulo):
    for campo in ("audiencia", "deseo", "promesa", "gancho"):
        texto = angulo[campo] or ""
        assert not any(c in texto for c in "{}[]'\""), (campo, texto)


def test_texto_de_un_dict_o_una_lista_es_legible():
    assert doctrina._texto(AUDIENCIA) == LEGIBLE_AUDIENCIA
    assert doctrina._texto(DESEO) == LEGIBLE_DESEO
    assert doctrina._texto({"a": ["x", {"b": "y"}], "c": None, "d": "", "e": []}) == "x; y"
    assert doctrina._texto(None) == "" and doctrina._texto(3) == "3" and doctrina._texto("  a   b ") == "a b"
    assert doctrina._texto(["uno", "dos", "tres"], tope=8) == "uno; dos"


def test_validar_angulo_deja_texto_legible_en_cada_campo():
    limpio, errores = doctrina.validar_angulo({
        "audiencia": AUDIENCIA, "consciencia": "consciente_del_problema", "sofisticacion": 2, "deseo": DESEO,
        "promesa": "Ordena el cajón en 5 minutos", "gancho": ["¿Tu cajón", "es un caos?"], "lead": ["problema_solucion"],
        "pruebas": [{"texto": ["cajones de 40 cm", "tela lavable"], "fuente": "ficha"}], "faltantes": []})
    assert limpio["audiencia"] == LEGIBLE_AUDIENCIA and limpio["deseo"] == LEGIBLE_DESEO
    assert limpio["gancho"] == "¿Tu cajón; es un caos?" and limpio["lead"] == "problema_solucion"
    assert limpio["pruebas"] == [{"texto": "cajones de 40 cm; tela lavable", "fuente": "ficha"}]
    assert "valor_invalido:lead" not in errores
    # Una promesa que llega como lista son varias promesas (Regla de Uno), no una frase con corchetes.
    _, errores = doctrina.validar_angulo({"promesa": ["Ordena rápido", "Dura años"], "audiencia": "x", "deseo": "y",
                                          "gancho": "z"})
    assert "promesa_multiple" in errores


def test_evaluar_con_ia_de_triple_whale_pinta_la_idea_sin_corchetes():
    from tests.test_triple_whale_analisis import respuesta
    from triple_whale import analisis
    idea = json.loads(respuesta())["ideas"][0]
    idea["angulo"] = dict(idea["angulo"], audiencia=AUDIENCIA, deseo=DESEO)
    r = analisis.parsear(respuesta(ideas=[idea]), {"A1", "A2", "A3"}, "datos 5")
    angulo = r["ideas"][0]["angulo"]
    assert angulo["audiencia"] == LEGIBLE_AUDIENCIA and angulo["deseo"] == LEGIBLE_DESEO
    _sin_repr(angulo)


def test_evaluacion_con_ia_de_meta_pinta_la_idea_sin_corchetes():
    from meta_rendimiento import analisis
    from tests.test_meta_rend_analisis import _idea, respuesta
    idea = _idea(1)
    idea["angulo"] = dict(idea["angulo"], audiencia=AUDIENCIA, deseo=DESEO)
    r = analisis.parsear(respuesta(ideas=[idea, _idea(2), _idea(3)]), {"A1", "A2"}, {"R1", "R2"}, "datos 1")
    angulo = r["ideas"][0]["angulo"]
    assert angulo["audiencia"] == LEGIBLE_AUDIENCIA and angulo["deseo"] == LEGIBLE_DESEO
    _sin_repr(angulo)


def test_ideas_de_sprints_guardan_el_angulo_sin_corchetes():
    from sprints import ideas
    from tests.test_sprints_ideas import ANGULO, IDEA_V
    idea = dict(IDEA_V, angulo=dict(ANGULO, audiencia=AUDIENCIA, deseo=DESEO))
    (i,) = ideas.parsear(json.dumps({"ideas": [idea]}), set(), (8,))
    assert i["angulo"]["audiencia"] == LEGIBLE_AUDIENCIA and i["angulo"]["deseo"] == LEGIBLE_DESEO
    _sin_repr(i["angulo"])
