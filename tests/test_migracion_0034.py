"""Migración 0034 (spec tarjetas §3; era la 0033 antes de mezclar 0033_cobros de main): crea tw_creativo y
tw_analisis encima de las tablas de cobros, y la bajada quita solo las suyas."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg

COBROS = {"cuenta_saldo", "movimiento_saldo", "reserva_saldo", "recarga", "pago_evento"}


def test_migracion_0034_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig34.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0034")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            assert {"tw_creativo", "tw_analisis"} <= tablas
            ddl = con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name='tw_analisis'")).scalar()
            assert "AUTOINCREMENT" in ddl.upper()
            assert COBROS <= tablas                      # las de 0033_cobros (main) siguen debajo
        command.downgrade(_cfg(), "0033")
        with db.conectar() as con:
            tablas = set(sa.inspect(con).get_table_names())
            assert not {"tw_creativo", "tw_analisis"} & tablas
            assert COBROS <= tablas                      # bajar 0034 no toca lo de cobros
    finally:
        db._reset_para_tests()
