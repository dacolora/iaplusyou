"""Migración 0036 (spec 2026-10-09 §4.2; era la 0035 en la rama tw-ganchos, renumerada al mezclar main, que trajo
0035_meta_rendimiento): crea tw_gancho encima de 0035 y la bajada la quita sola."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0036_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig36.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0036")
        with db.conectar() as con:
            insp = sa.inspect(con)
            assert {"tw_gancho", "tw_analisis", "meta_cuenta"} <= set(insp.get_table_names())
            ddl = con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='tw_gancho'")).scalar()
            assert "AUTOINCREMENT" in ddl.upper() and "uq_tw_gancho_tanda" in ddl
            indices = {i["name"] for i in insp.get_indexes("tw_gancho")}
            assert {"ix_tw_gancho_cliente", "ix_tw_gancho_analisis", "ix_tw_gancho_estado"} <= indices
        command.downgrade(_cfg(), "0035")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            # la bajada quita solo tw_gancho: la 0035 (Meta rendimiento) y la 0034 (tarjetas) siguen en pie
            assert "tw_gancho" not in tablas and {"tw_analisis", "meta_cuenta"} <= tablas
    finally:
        db._reset_para_tests()
