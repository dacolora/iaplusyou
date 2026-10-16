"""El director escribe los planos (el prompt del modelo de video) siempre en inglés y lo que lee la persona
(«diferencia_b») en el idioma del proyecto (spec §B4; PND-239, regla 3)."""
import idiomas
import director


def test_system_del_director_en_ingles():
    sistema = director._system("kling", "cierre", 2, 8, "en")
    assert '"plano", "accion" y "sonido" van SIEMPRE en inglés' in sistema and '"diferencia_b" va en inglés' in sistema
    sistema_es = director._system("kling", "cierre", 2, 8, "es")
    assert '"plano", "accion" y "sonido" van SIEMPRE en inglés' in sistema_es and '"diferencia_b" va en español' in sistema_es


def test_compilar_manda_la_orden_de_idioma(monkeypatch):
    # Misma costura que tests/test_director.py: se parchea anthropic.Anthropic
    # para no llamar a Claude de verdad.
    from tests.test_director import _instalar_fake, _respuesta, _sesion

    reg = _instalar_fake(monkeypatch, [_respuesta()])
    director.compilar("acme", _sesion(), idioma="en")
    bloques = reg.kwargs[0]["system"]
    orden = idiomas.orden_idioma("en")
    ultimo = bloques[-1]["text"]
    assert ultimo.startswith(orden) and ultimo.endswith(orden)
