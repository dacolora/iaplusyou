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


def test_preferencias_flowplus_traen_idioma_y_duracion_por_defecto(monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "es" and p["duracion_defecto"] == 8
    proyectos.guardar_preferencias_flowplus("acme", "kling_o3_pro", "seedream_v5_pro", idioma_prompt="en", duracion_defecto=10)
    p = proyectos.preferencias_flowplus("acme")
    assert p == {"modelo_video": "kling_o3_pro", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "en", "duracion_defecto": 10}
    # valores raros se normalizan: idioma desconocido -> es; duración fuera de la lista -> 8
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="fr", duracion_defecto=7)
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "es" and p["duracion_defecto"] == 8
