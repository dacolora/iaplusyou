"""Rutas de Crear con el director (spec 2026-09-18 §7)."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(referencias_flowplus, "listar",
                        lambda c: [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def test_settings_guarda_idioma_y_duracion_por_defecto(app):
    import proyectos
    r = app["c"].post("/cliente/acme/preferencias_flowplus/guardar", data={
        "modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "en", "duracion_defecto": "10"})
    assert r.status_code == 302
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "en" and p["duracion_defecto"] == 10
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="idioma_prompt"' in html and '<option value="en" selected>' in html
    assert 'name="duracion_defecto"' in html
