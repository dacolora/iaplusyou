import proyectos


def test_preferencias_sonido_defecto_y_guardado(tmp_path, monkeypatch):
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    assert proyectos.preferencias_sonido("acme") == {"con_sonido": True, "musica_al_crear": ""}
    proyectos.guardar_preferencias_sonido("acme", False, "calmado")
    assert proyectos.preferencias_sonido("acme") == {"con_sonido": False, "musica_al_crear": "calmado"}
    # otras preferencias del proyecto no se pisan
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro")
    assert proyectos.preferencias_sonido("acme")["musica_al_crear"] == "calmado"
    assert proyectos.preferencias_flowplus("acme")["modelo_video"] == "wan3"
