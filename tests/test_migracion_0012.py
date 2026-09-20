import os

import sqlalchemy as sa


def test_tablas_del_editor_existen_en_metadata(base_temporal):
    import db
    nombres = set(db.metadata.tables)
    assert {"edicion", "edicion_version", "material"} <= nombres
    assert "edicion_version_id" in db.pieza.c


def test_material_unico_por_cliente_y_hash(base_temporal):
    import db
    with db.conectar() as con:
        con.execute(db.material.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", origen="subida",
            url="https://r2/x.mp4", hash="abc", bytes=10))
    with db.conectar() as con:
        try:
            con.execute(db.material.insert().values(
                cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", origen="subida",
                url="https://r2/y.mp4", hash="abc", bytes=10))
            assert False, "debía fallar por hash repetido"
        except sa.exc.IntegrityError:
            pass


def test_migracion_0012_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig11.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "head")
    insp = sa.inspect(db.engine())
    assert {"edicion", "edicion_version", "material"} <= set(insp.get_table_names())
    assert "edicion_version_id" in {c["name"] for c in insp.get_columns("pieza")}
    assert "uq_material_hash" in {u["name"] for u in insp.get_unique_constraints("material")}
    db._reset_para_tests()
    command.downgrade(cfg, "0011")
    insp = sa.inspect(db.engine())
    assert "material" not in insp.get_table_names()
    assert "edicion_version_id" not in {c["name"] for c in insp.get_columns("pieza")}
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    assert "edicion" in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()
