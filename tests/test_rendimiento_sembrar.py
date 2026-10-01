"""rendimiento/sembrar.py: los datos de la prueba de carga se siembran y se
borran sin dejar nada, y nunca contra un PLATAFORMA_URL que no sea local."""
import pytest
import sqlalchemy as sa


@pytest.fixture()
def carpetas(tmp_path, monkeypatch, base_temporal):
    import catalogo_productos
    import proyectos
    from rendimiento import sembrar
    monkeypatch.setattr(sembrar, "BASE", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    return sembrar


def _cuentas(db):
    with db.conectar() as con:
        return {t: con.execute(sa.select(sa.func.count()).select_from(db.metadata.tables[t])).scalar()
                for t in ("concepto", "pieza", "gasto", "tarea", "experimento", "experimento_pieza", "metrica_snapshot")}


def test_siembra_y_limpia(carpetas, base_temporal, usuarios_tmp, tmp_path):
    sembrar = carpetas
    clientes = sembrar.sembrar(proyectos_n=2, piezas=20, dias=2, productos=2)
    assert clientes == ["carga01", "carga02"]
    n = _cuentas(base_temporal)
    assert n["concepto"] == n["pieza"] == 40 and n["experimento"] == 4 and n["metrica_snapshot"] > 0
    assert usuarios_tmp.obtener("carga01")["cliente"] == "carga01" and usuarios_tmp.obtener("cargaadmin")["rol"] == "admin"
    assert (tmp_path / "clientes" / "carga01" / "productos" / "producto_00" / "negro").is_dir()
    sembrar.sembrar(proyectos_n=2, piezas=20, dias=2, productos=2)       # idempotente
    assert _cuentas(base_temporal)["concepto"] == 40
    sembrar.limpiar()
    assert all(v == 0 for v in _cuentas(base_temporal).values())
    assert not (tmp_path / "clientes" / "carga01").exists()
    assert usuarios_tmp.obtener("carga01") is None and usuarios_tmp.obtener("admin") is not None


def test_se_niega_si_la_plataforma_no_es_local(carpetas, monkeypatch):
    sembrar = carpetas
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.creatvmachine.com")
    assert not sembrar.es_local()
    with pytest.raises(SystemExit):
        sembrar.main(["--proyectos", "1"])
    monkeypatch.setenv("PLATAFORMA_URL", "http://127.0.0.1:5050")
    assert sembrar.es_local()
