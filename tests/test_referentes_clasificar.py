import pytest

import referentes.clasificar as clasificar


def test_validar_familia_del_vocabulario():
    data = {"etapa": "TOF", "consciencia": "unaware", "familia": "Villain Made Visible",
            "familia_nueva": None, "dolor": "bloating", "firma": "Muestra el problema antes de ofrecer la solución."}
    r = clasificar.validar(data, ["Villain Made Visible", "Before/After Diptych"])
    assert r["familia"] == "Villain Made Visible" and r["familia_nueva"] is None


def test_validar_familia_nueva_cuando_ninguna_encaja():
    data = {"etapa": "MOF", "consciencia": "problem-aware", "familia": None,
            "familia_nueva": {"nombre": "Recipe Card", "descripcion": "Formato de receta paso a paso."},
            "dolor": "ninguno-oferta", "firma": "Presenta el producto como un ingrediente de una receta."}
    r = clasificar.validar(data, ["Villain Made Visible"])
    assert r["familia"] is None
    assert r["familia_nueva"]["nombre"] == "Recipe Card"


def test_validar_familia_fuera_del_vocabulario_falla():
    data = {"etapa": "TOF", "consciencia": "unaware", "familia": "Formato Inventado",
            "familia_nueva": None, "dolor": "x", "firma": "f"}
    with pytest.raises(clasificar.ClasificacionInvalida):
        clasificar.validar(data, ["Villain Made Visible"])


def test_validar_etapa_invalida_falla():
    data = {"etapa": "XOF", "consciencia": "unaware", "familia": None,
            "familia_nueva": {"nombre": "X", "descripcion": "d"}, "dolor": "x", "firma": "f"}
    with pytest.raises(clasificar.ClasificacionInvalida):
        clasificar.validar(data, [])


def test_validar_sin_familia_ni_familia_nueva_falla():
    data = {"etapa": "TOF", "consciencia": "unaware", "familia": None, "familia_nueva": None,
            "dolor": "x", "firma": "f"}
    with pytest.raises(clasificar.ClasificacionInvalida):
        clasificar.validar(data, [])


def test_validar_recorta_firma_a_40_palabras():
    firma_larga = " ".join(f"palabra{i}" for i in range(60))
    data = {"etapa": "TOF", "consciencia": "unaware", "familia": None,
            "familia_nueva": {"nombre": "X", "descripcion": "d"}, "dolor": "x", "firma": firma_larga}
    r = clasificar.validar(data, [])
    assert len(r["firma"].split(" ")) == 40


class _RespuestaFalsa:
    def __init__(self, texto):
        self.content = [type("Bloque", (), {"type": "text", "text": texto})()]
        self.usage = type("Uso", (), {"input_tokens": 900, "output_tokens": 60})()


def test_clasificar_llamada_completa(monkeypatch):
    respuesta = _RespuestaFalsa('{"etapa": "TOF", "consciencia": "unaware", "familia": "Villain Made Visible", '
                                '"familia_nueva": null, "dolor": "bloating", "firma": "Muestra el problema."}')

    class _ClienteFalso:
        class messages:
            @staticmethod
            def create(**kw):
                assert kw["model"]
                assert any(b.get("type") == "image" for b in kw["messages"][0]["content"])
                return respuesta

    monkeypatch.setattr("referentes.clasificar.anthropic.Anthropic", lambda api_key: _ClienteFalso())
    monkeypatch.setattr("referentes.clasificar._api_key", lambda: "sk-test")
    referente = {"marca": "WholeSupp", "titular": "T", "cuerpo": "C", "idioma": "en",
                "imagen_url": "https://cdn.example/x.jpg"}
    resultado, ent, sal = clasificar.clasificar(referente, ["Villain Made Visible"])
    assert resultado["etapa"] == "TOF" and resultado["familia"] == "Villain Made Visible"
    assert ent == 900 and sal == 60


def test_clasificar_json_invalido_lanza_con_tokens(monkeypatch):
    respuesta = _RespuestaFalsa("esto no es json")

    class _ClienteFalso:
        class messages:
            @staticmethod
            def create(**kw):
                return respuesta

    monkeypatch.setattr("referentes.clasificar.anthropic.Anthropic", lambda api_key: _ClienteFalso())
    monkeypatch.setattr("referentes.clasificar._api_key", lambda: "sk-test")
    referente = {"marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en", "imagen_url": "https://cdn.example/x.jpg"}
    with pytest.raises(clasificar.ClasificacionInvalida) as exc:
        clasificar.clasificar(referente, [])
    assert exc.value.tokens_entrada == 900 and exc.value.tokens_salida == 60
