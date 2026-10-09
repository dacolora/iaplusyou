"""Migración 0035 (spec 2026-10-09 §4.2): crea tw_gancho encima de 0034 y la bajada la quita sola."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0035_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig35.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0035")
        with db.conectar() as con:
            insp = sa.inspect(con)
            assert {"tw_gancho", "tw_analisis"} <= set(insp.get_table_names())
            ddl = con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='tw_gancho'")).scalar()
            assert "AUTOINCREMENT" in ddl.upper() and "uq_tw_gancho_tanda" in ddl
            indices = {i["name"] for i in insp.get_indexes("tw_gancho")}
            assert {"ix_tw_gancho_cliente", "ix_tw_gancho_analisis", "ix_tw_gancho_estado"} <= indices
        command.downgrade(_cfg(), "0034")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            assert "tw_gancho" not in tablas and "tw_analisis" in tablas
    finally:
        db._reset_para_tests()
