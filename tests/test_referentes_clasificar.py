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


# --- Topes de salida (2026-09-25): Claude Sonnet 5 piensa antes de responder y
# eso sale del mismo max_tokens. Medido en producción: una clasificación usó
# 162 y 299 tokens de salida (tope viejo: 500).

class _RespuestaCortada:
    def __init__(self, texto, stop_reason):
        self.content = [type("Bloque", (), {"type": "text", "text": texto})()]
        self.stop_reason = stop_reason
        self.usage = type("Uso", (), {"input_tokens": 3976, "output_tokens": 500})()


def _con_cliente(monkeypatch, respuesta, pedidos=None):
    class _ClienteFalso:
        class messages:
            @staticmethod
            def create(**kw):
                if pedidos is not None:
                    pedidos.append(kw)
                return respuesta
    monkeypatch.setattr("referentes.clasificar.anthropic.Anthropic", lambda api_key: _ClienteFalso())
    monkeypatch.setattr("referentes.clasificar._api_key", lambda: "sk-test")


_REFERENTE = {"marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en", "imagen_url": "https://cdn.example/x.jpg"}


def test_clasificar_cortada_por_max_tokens_lanza_con_tokens(monkeypatch):
    _con_cliente(monkeypatch, _RespuestaCortada('{"etapa": "TOF", "consciencia": "unaware", "firma": "Muestra', "max_tokens"))
    with pytest.raises(clasificar.ClasificacionInvalida, match="se cortó") as exc:
        clasificar.clasificar(_REFERENTE, [])
    assert (exc.value.tokens_entrada, exc.value.tokens_salida) == (3976, 500)


def test_clasificar_rechazada_lanza_con_tokens(monkeypatch):
    _con_cliente(monkeypatch, _RespuestaCortada("", "refusal"))
    with pytest.raises(clasificar.ClasificacionInvalida, match="rechazó") as exc:
        clasificar.clasificar(_REFERENTE, [])
    assert exc.value.tokens_entrada == 3976


def test_clasificar_da_espacio_para_pensar_y_responder(monkeypatch):
    pedidos = []
    _con_cliente(monkeypatch, _RespuestaFalsa('{"etapa": "TOF", "consciencia": "unaware", "familia": null, '
                                              '"familia_nueva": {"nombre": "N", "descripcion": "d"}, '
                                              '"dolor": "x", "firma": "y"}'), pedidos)
    clasificar.clasificar(_REFERENTE, [])
    assert 299 * 5 <= pedidos[0]["max_tokens"] <= 16000


def test_validar_acepta_lead_y_descarta_el_raro():
    base = {"etapa": "TOF", "consciencia": "unaware", "familia": None,
            "familia_nueva": {"nombre": "X", "descripcion": "d"}, "dolor": "x", "firma": "f"}
    assert clasificar.validar(dict(base, lead="historia"), [])["lead"] == "historia"
    assert clasificar.validar(dict(base, lead="grito"), [])["lead"] is None
    assert clasificar.validar(base, [])["lead"] is None


def test_clasificar_manda_la_doctrina_de_clasificar_y_pide_el_lead(monkeypatch):
    import doctrina
    vistos = []
    respuesta = _RespuestaFalsa('{"etapa": "TOF", "consciencia": "unaware", "familia": null, '
                                '"familia_nueva": {"nombre": "X", "descripcion": "d"}, "dolor": "d", "firma": "f", '
                                '"lead": "secreto"}')

    class _ClienteFalso:
        class messages:
            @staticmethod
            def create(**kw):
                vistos.append(kw)
                return respuesta

    monkeypatch.setattr("referentes.clasificar.anthropic.Anthropic", lambda api_key: _ClienteFalso())
    monkeypatch.setattr("referentes.clasificar._api_key", lambda: "sk-test")
    r, _, _ = clasificar.clasificar({"marca": "M", "titular": "T", "cuerpo": "", "idioma": "en",
                                     "imagen_url": "https://r2/x.jpg"}, [])
    assert r["lead"] == "secreto"
    assert vistos[0]["system"][0]["text"] == doctrina.texto("clasificar")
    assert '"lead"' in vistos[0]["messages"][0]["content"][0]["text"]
