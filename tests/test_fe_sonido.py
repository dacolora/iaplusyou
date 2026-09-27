import idiomas
from final_edition import sonido


def test_sugerir_descripcion_arma_el_prompt_y_limpia_la_respuesta(monkeypatch):
    vistos = {}

    def _llamar(texto, max_tokens=200):
        vistos["texto"] = texto
        return "  \"Risas de niños, pasos descalzos sobre baldosa; respiración agitada al final.\"\n"
    monkeypatch.setattr(sonido, "_llamar", _llamar)
    r = sonido.sugerir_descripcion("una niña descubre el producto y salta", "persona", persona={"resumen": "Mamás jóvenes"})
    assert r == "Risas de niños, pasos descalzos sobre baldosa; respiración agitada al final."
    assert "una niña descubre el producto" in vistos["texto"] and "Mamás jóvenes" in vistos["texto"]
    assert "Sin diálogo" in vistos["texto"] and "sin música" in vistos["texto"].lower()
    assert sonido.sugerir_descripcion("   ", "producto") == ""   # sin escena no llama


def test_sugerir_descripcion_recorta(monkeypatch):
    monkeypatch.setattr(sonido, "_llamar", lambda t, max_tokens=200: "x" * 500)
    assert len(sonido.sugerir_descripcion("gira", "producto")) == sonido.MAX_CARACTERES


def test_sugerir_descripcion_manda_la_orden_de_idioma_al_principio_y_al_final(monkeypatch):
    """Spec 2026-09-26 §B4: la orden de idioma va al inicio Y al final del
    texto que recibe Claude (como `doctrina.bloque_system`) — no solo al
    final, porque el español largo del PROMPT de en medio arrastraría la
    salida si solo estuviera al final."""
    vistos = {}

    def _llamar(texto, max_tokens=200):
        vistos["texto"] = texto
        return "waves"
    monkeypatch.setattr(sonido, "_llamar", _llamar)
    sonido.sugerir_descripcion("a wave crashes", "producto", idioma="en")
    orden = idiomas.orden_idioma("en")
    assert vistos["texto"].startswith(orden) and vistos["texto"].endswith(orden)
    # en español (por defecto) también, con el texto de siempre en medio.
    sonido.sugerir_descripcion("una ola rompe", "producto")
    orden_es = idiomas.orden_idioma("es")
    assert vistos["texto"].startswith(orden_es) and vistos["texto"].endswith(orden_es)
    assert "en español" in vistos["texto"]
