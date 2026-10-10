"""El final de «Producir» como función compartida (spec 2026-10-09 §4.6.4): la ruta del editor y la tarea de los
ganchos encolan igual. Las pruebas de la ruta (tests/test_rutas_editor.py) no se tocan y siguen en verde."""
from tests.test_rutas_editor import _edicion_con_pieza, dashboard, encolados  # noqa: F401  (fixtures)


def test_encolar_producciones_crea_la_final_y_encola_el_render(dashboard, encolados):  # noqa: F811
    import creative_flow
    import ediciones
    from final_edition import rutas_editor
    ed, cf = _edicion_con_pieza()
    version = ediciones.versionar("acme", ed["id"], motivo="producir")
    out = rutas_editor.encolar_producciones("acme", ed["id"], ed, version, ["es_CO"])
    assert out == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": True}]
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_producir"]
    assert args[0] == f"acme__ed{ed['id']}__es_CO__producir"
    assert args[2] == {"cliente": "acme", "edicion_id": ed["id"], "version_id": version["id"],
                       "final_id": f"{cf}__es_CO", "idioma": "es", "pais": "CO"}
    assert kw["max_intentos"] == 1 and kw["cliente"] == "acme" and kw["duracion_estimada"] >= 1
    assert creative_flow.final_por_legado("acme", f"{cf}__es_CO")["estado"] == "generando"


def test_encolar_producciones_no_repite_un_render_vivo(dashboard, encolados, monkeypatch):  # noqa: F811
    import creative_flow
    import ediciones
    import trabajos
    from final_edition import rutas_editor
    ed, cf = _edicion_con_pieza()
    version = ediciones.versionar("acme", ed["id"], motivo="producir")
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: job_id.endswith("__producir"))
    out = rutas_editor.encolar_producciones("acme", ed["id"], ed, version, ["es_CO"])
    assert out == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": False}]
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]
    assert creative_flow.final_por_legado("acme", f"{cf}__es_CO") is None        # ni siquiera reinicia la final
