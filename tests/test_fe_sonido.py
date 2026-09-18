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
