"""Lo que Claude escribe desde Catálogo, orgánico y la guía de marca sale en
el idioma del proyecto (spec 2026-09-26 §B4, §B5). Sin red: se reemplaza el
cliente de anthropic del módulo."""
import generador_prompts as gp
import idiomas


class _Resp:
    def __init__(self, texto):
        self.content = [type("B", (), {"type": "text", "text": texto})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()
        self.stop_reason = "end_turn"


def _cliente_falso(monkeypatch, texto):
    capturado = {}

    class _Cliente:
        def __init__(self, api_key=None):
            pass

        class messages:
            @staticmethod
            def create(**kw):
                capturado.update(kw)
                return _Resp(texto)

    monkeypatch.setattr(gp.anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(gp, "_api_key", lambda: "sk-test")
    return capturado


def _texto(system):
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


def test_regla_de_fidelidad_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Keep the exact blue.")
    assert gp.regla_fidelidad("Cushion", "Blue linen", "Home", "en") == "Keep the exact blue."
    s, orden = _texto(cap["system"]), idiomas.orden_idioma("en")
    assert s.startswith(orden) and s.endswith(orden) and "Escribe, en inglés, una regla" in s


def test_regla_de_fidelidad_en_espanol_por_defecto(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Mismo azul.")
    gp.regla_fidelidad("Cojín", "Lino azul", "Hogar")
    assert "Escribe, en español, una regla" in _texto(cap["system"])


def test_guia_de_marca_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Warm light.")
    gp.analizar_marca(["https://cdn.example/a.jpg"], idioma="en")
    texto, orden = cap["messages"][0]["content"][0]["text"], idiomas.orden_idioma("en")
    assert texto.startswith(orden) and texto.endswith(orden)


def test_caption_organico_con_orden_y_link_in_bio(monkeypatch):
    cap = _cliente_falso(monkeypatch, '{"instagram": {"titulo": "T", "caption": "C"}}')
    gp.caption_organico({"nombre_producto": "Slipper", "idioma": "en"}, ["instagram"])
    s = _texto(cap["system"])
    assert idiomas.orden_idioma("en") in s and '"Link in bio"' in s and '"Link en bio"' not in s


def test_caption_organico_pt_sin_orden_de_idioma(monkeypatch):
    """Un idioma que no es es/en (ej. portugués: pieza de un destino que
    todavía no tiene su propio catálogo de idiomas de interfaz) no lleva la
    orden §B4 -- forzaría español o inglés sobre esa pieza -- pero sí dice
    «Idioma: pt» tal cual, como hacía main antes de la fase 4 (revisión
    final fase 4, hallazgo I1)."""
    cap = _cliente_falso(monkeypatch, '{"instagram": {"titulo": "T", "caption": "C"}}')
    gp.caption_organico({"nombre_producto": "Chinelo", "idioma": "pt"}, ["instagram"])
    s = _texto(cap["system"])
    assert idiomas.orden_idioma("es") not in s and idiomas.orden_idioma("en") not in s
    assert '"Link na bio"' in s
    assert "Idioma: pt" in cap["messages"][0]["content"]


def test_generar_prompts_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, '["a", "b"]')
    gp.generar_prompts("a dog runs", n=2, idioma="en")
    s = _texto(cap["system"])
    # (la orden de idioma dice «aunque estas instrucciones estén en español»: se mira la frase del prompt)
    assert "variantes de prompt en inglés" in s and "variantes de prompt en español" not in s
