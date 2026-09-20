"""Forma elegida por el cliente para conectar Meta (spec §1): vive en
clientes/<c>/proyecto.json y es independiente del modo real de meta.json."""
import pytest


@pytest.fixture()
def proyectos_tmp(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return proyectos


def test_sin_forma_devuelve_none(proyectos_tmp):
    assert proyectos_tmp.meta_forma("acme") is None


def test_guardar_y_leer_forma(proyectos_tmp):
    proyectos_tmp.guardar_meta_forma("acme", "agencia")
    assert proyectos_tmp.meta_forma("acme") == "agencia"
    proyectos_tmp.guardar_meta_forma("acme", "propia")
    assert proyectos_tmp.meta_forma("acme") == "propia"
    # No pisa el resto del proyecto.json.
    proyectos_tmp.guardar_nombre("acme", "Acme SA")
    assert proyectos_tmp.meta_forma("acme") == "propia" and proyectos_tmp.nombre_visible("acme") == "Acme SA"


def test_none_borra_y_valor_raro_rechaza(proyectos_tmp):
    proyectos_tmp.guardar_meta_forma("acme", "agencia")
    proyectos_tmp.guardar_meta_forma("acme", None)
    assert proyectos_tmp.meta_forma("acme") is None
    with pytest.raises(ValueError):
        proyectos_tmp.guardar_meta_forma("acme", "otra")


def test_valor_corrupto_en_disco_cuenta_como_sin_forma(proyectos_tmp):
    import _json_store
    _json_store.guardar(proyectos_tmp._path("acme"), {"meta_forma": "lo-que-sea"})
    assert proyectos_tmp.meta_forma("acme") is None
