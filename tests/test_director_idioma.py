"""El director escribe los planos en el idioma del proyecto (spec §B4)."""
import idiomas
import director


def test_system_del_director_en_ingles():
    sistema = director._system("kling", "cierre", 2, 8, "en")
    assert "Idioma de los textos: inglés" in sistema


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
