"""PND-006: unicidad por proyecto con biblioteca global independiente."""
import pytest
import sqlalchemy as sa
from tests.test_migracion_0029 import _cfg


def _insertar(con, cliente, aid="compartido"):
    import db
    return con.execute(db.referente.insert().values(cliente=cliente, anuncio_id=aid, fuente="apify",
        creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="imagen", estado_imagen="ok", clasificacion="pendiente"))


def test_migracion_0030_sube_y_baja_sin_perder_filas(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig30.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0029")
        with db.conectar() as con:
            rid = _insertar(con, "acme").inserted_primary_key[0]
        command.upgrade(_cfg(), "0030")
        with db.conectar() as con:
            assert con.execute(sa.select(db.referente.c.id)).scalar() == rid
            _insertar(con, "otro")
            _insertar(con, None)
            for cliente in ("acme", None):
                with pytest.raises(sa.exc.IntegrityError), con.begin_nested():
                    _insertar(con, cliente)
        # Bajar no puede decidir qué proyecto pierde sus referentes.
        with pytest.raises(RuntimeError, match="duplicados"):
            command.downgrade(_cfg(), "0029")
        with db.conectar() as con:
            assert con.execute(sa.select(sa.func.count()).select_from(db.referente)).scalar() == 3
            con.execute(db.referente.delete().where(db.referente.c.id != rid))
        command.downgrade(_cfg(), "0029")
        with db.conectar() as con:
            assert con.execute(sa.select(db.referente.c.id)).scalar() == rid
            with pytest.raises(sa.exc.IntegrityError), con.begin_nested():
                _insertar(con, "otro")
        command.upgrade(_cfg(), "0030")
        migrados = {i["name"]: i["column_names"] for i in sa.inspect(db.engine()).get_indexes("referente") if i["unique"]}
        declarados = {i.name: [c.name for c in i.columns] for i in db.referente.indexes if i.unique}
        assert migrados == declarados
    finally:
        db._reset_para_tests()
