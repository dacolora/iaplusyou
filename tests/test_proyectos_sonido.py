import idiomas
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


def test_preferencias_flowplus_traen_duracion_por_defecto_y_el_idioma_ya_no_vive_ahi(monkeypatch, tmp_path):
    """Fase 3 (spec 2026-09-26 §B4): el idioma del prompt lo reemplaza el
    idioma del proyecto (`idiomas.de_proyecto`/`guardar_de_proyecto`) — ya no
    es una preferencia de FlowPlus. El caso inválido ("fr") ya lo prueba
    tests/test_idiomas.py::test_proyecto."""
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    p = proyectos.preferencias_flowplus("acme")
    assert p == {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "duracion_defecto": 8}
    proyectos.guardar_preferencias_flowplus("acme", "kling_o3_pro", "seedream_v5_pro", duracion_defecto=10)
    p = proyectos.preferencias_flowplus("acme")
    assert p == {"modelo_video": "kling_o3_pro", "modelo_imagen": "seedream_v5_pro", "duracion_defecto": 10}
    # duración fuera de la lista -> 8
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", duracion_defecto=7)
    assert proyectos.preferencias_flowplus("acme")["duracion_defecto"] == 8
    # el idioma es del proyecto, no de FlowPlus
    assert idiomas.de_proyecto("acme") == "es"
    idiomas.guardar_de_proyecto("acme", "en")
    assert idiomas.de_proyecto("acme") == "en"
    assert "idioma_prompt" not in proyectos.preferencias_flowplus("acme")


def test_preferencias_flowplus_filtra_un_idioma_prompt_viejo_del_json(monkeypatch, tmp_path):
    """Un proyecto.json de antes de la fase 3 puede traer `idioma_prompt`
    dentro de `preferencias_flowplus`: no debe colarse en lo que devuelve la
    función (spec 2026-09-26 §B4)."""
    import _json_store
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", duracion_defecto=8)
    datos = proyectos.cargar("acme")
    datos["preferencias_flowplus"]["idioma_prompt"] = "en"
    _json_store.guardar(proyectos._path("acme"), datos)
    assert "idioma_prompt" not in proyectos.preferencias_flowplus("acme")
