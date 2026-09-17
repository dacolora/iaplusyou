"""La pestaña Crear muestra la tarifa con sonido y el indicador 🔊/🔇 de cada
video (spec estudio S1, núcleo)."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def test_crear_muestra_tarifa_con_sonido_e_indicador(app):
    import creative_flow as cf
    con = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", con, estado="video_listo", tipo="video", modelo="kling_o3_pro", video_url="https://r2/v.mp4",
                  usd=0.7, sonido={"proveedor": "kling_o3_pro", "estado": "ok"})
    mudo = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", mudo, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/m.mp4",
                  sonido={"proveedor": "wan3", "estado": "ausente"})
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-usd-seg="0.14"' in html and "$0.140/s con sonido" in html
    assert 'data-usd-seg="0.1"' in html
    assert "🔊" in html and "🔇 sin sonido" in html
