"""Migración 0033 (spec tarjetas §3): crea tw_creativo y tw_analisis y la bajada las quita."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0033_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig33.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0033")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            assert {"tw_creativo", "tw_analisis"} <= tablas
            ddl = con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='tw_analisis'")).scalar()
            assert "AUTOINCREMENT" in ddl.upper()
        command.downgrade(_cfg(), "0032")
        with db.conectar() as con:
            assert not {"tw_creativo", "tw_analisis"} & set(sa.inspect(con).get_table_names())
    finally:
        db._reset_para_tests()
