import pytest
import meta_conexion as mc


def test_guardar_y_cargar_app_anunciada(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_dir", lambda cliente: str(tmp_path / cliente))
    assert mc.cargar_app_anunciada("acme") is None
    mc.guardar_app_anunciada("acme", " 1234567890 ")
    assert mc.cargar_app_anunciada("acme") == "1234567890"
    assert not (tmp_path / "acme" / "meta_app.json").exists()  # no pisa la app de inicio de sesión


@pytest.mark.parametrize("malo", ["", "abc", "12", "12 34", "1" * 30])
def test_app_anunciada_invalida(tmp_path, monkeypatch, malo):
    monkeypatch.setattr(mc, "_dir", lambda cliente: str(tmp_path / cliente))
    with pytest.raises(mc.MetaConexionError):
        mc.guardar_app_anunciada("acme", malo)
