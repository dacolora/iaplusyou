"""PND-308: en «Cómo mejorarlo» el `lead` (y a veces la `consciencia`) del ángulo de la versión salía inválido. Las
respuestas crudas medidas el 2026-10-15 (`docs/superpowers/evals/2026-10-15-mejorar-lead.md`) muestran por qué: Claude
escribe el arranque y la consciencia como los nombra la rebanada `angulo` de la doctrina, con tildes, guiones y
mayúsculas («problema-solución», «Consciente de la solución»), y la validación solo aceptaba la clave sin tildes.
Ahora se aceptan esos valores; los de la lista y los que ya pasaban siguen igual."""
import json

import pytest

import doctrina

# Los valores crudos de las 4 respuestas de la línea base (2026-10-15), tal cual.
CRUDOS = [("problema-solución", "consciente del problema"), ("problema-solución", "Consciente de la solución"),
          ("problema-solucion", "problem-aware"), ("promesa", "consciente del producto")]


@pytest.mark.parametrize("valor, clave", [
    ("problema-solución", "problema_solucion"), ("Problema-Solución", "problema_solucion"),
    ("problema solución", "problema_solucion"), ("problema_solucion", "problema_solucion"),
    ("proclamación", "proclamacion"), ("Historia", "historia"), ("oferta", "oferta"),
    ("problem-solution", "problema_solucion"), ("story", "historia"), ("offer", "oferta"), ("promise", "promesa"),
    ("secret", "secreto"), ("proclamation", "proclamacion"),
])
def test_normalizar_lead_acepta_como_lo_escribe_claude(valor, clave):
    assert doctrina.normalizar_lead(valor) == clave


@pytest.mark.parametrize("valor", ["grito", "", None, "problema", "oferta irresistible"])
def test_normalizar_lead_rechaza_lo_que_no_es_un_arranque(valor):
    assert doctrina.normalizar_lead(valor) is None


def test_normalizar_consciencia_acepta_tildes_y_mayusculas():
    assert doctrina.normalizar_consciencia("Consciente de la solución") == "consciente_de_la_solucion"
    assert doctrina.normalizar_consciencia("CONSCIENTE DEL PROBLEMA") == "consciente_del_problema"
    assert doctrina.normalizar_consciencia("problem-aware") == "consciente_del_problema"
    assert doctrina.normalizar_consciencia("dormido") is None


@pytest.mark.parametrize("lead, consciencia", CRUDOS)
def test_los_valores_crudos_medidos_validan(lead, consciencia):
    limpio, errores = doctrina.validar_angulo({
        "audiencia": "mamás que trabajan de pie", "consciencia": consciencia, "sofisticacion": 2,
        "deseo": "pies descansados", "promesa": "Pies descansados al final del día", "mecanismo": None,
        "pruebas": [{"texto": "suela de espuma", "fuente": "Demostración"}], "lead": lead,
        "gancho": "¿Te duelen los pies?", "faltantes": []})
    assert not [e for e in errores if e.startswith(("valor_invalido", "campo_faltante"))], errores
    assert limpio["lead"] in doctrina.LEADS and limpio["consciencia"] in doctrina.CONSCIENCIAS
    assert limpio["pruebas"] == [{"texto": "suela de espuma", "fuente": "demostracion"}]


def test_un_arranque_inventado_sigue_siendo_invalido():
    _, errores = doctrina.validar_angulo({"lead": "grito", "consciencia": "inventada"})
    assert "valor_invalido:lead" in errores and "valor_invalido:consciencia" in errores


def test_como_mejorarlo_guarda_el_angulo_con_lo_que_escribe_claude():
    from tests.test_tw_mejorar import respuesta
    from triple_whale import mejorar
    version = json.loads(respuesta())["version"]
    version["angulo"] = dict(version["angulo"], lead="problema-solución", consciencia="Consciente de la solución")
    r = mejorar.parsear(respuesta(version=version), "datos")
    angulo = r["version"]["angulo"]
    assert angulo["lead"] == "problema_solucion" and angulo["consciencia"] == "consciente_de_la_solucion"
    assert not [f for f in angulo["faltantes"] if f.startswith("error: valor_invalido")]
