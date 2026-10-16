"""Migración 0040 (pospago, Daniel 2026-10-12): agrega cuenta_saldo.pospago en 0 sin tocar las cuentas que ya
existen (cobrar, margen y umbral intactos) y la bajada la quita sola."""
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0040_sube_sin_cambiar_cuentas_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig40.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0039")
        with db.conectar() as con:
            con.execute(sa.text("INSERT INTO cuenta_saldo (cliente, cobrar, margen, umbral_aviso) "
                                "VALUES ('happyflops', 1, 3.0, 5000)"))
        command.upgrade(_cfg(), "0040")
        with db.conectar() as con:
            fila = con.execute(sa.text("SELECT cobrar, margen, umbral_aviso, pospago FROM cuenta_saldo")).one()
            assert tuple(fila) == (1, 3.0, 5000, 0)
            con.execute(sa.text("INSERT INTO cuenta_saldo (cliente, cobrar, umbral_aviso) VALUES ('nuevo', 0, 5000)"))
            assert con.execute(sa.text("SELECT pospago FROM cuenta_saldo WHERE cliente='nuevo'")).scalar() == 0
        command.downgrade(_cfg(), "0039")
        with db.conectar() as con:
            columnas = {c["name"] for c in sa.inspect(con).get_columns("cuenta_saldo")}
            assert "pospago" not in columnas and {"cobrar", "margen", "umbral_aviso"} <= columnas
            assert con.execute(sa.text("SELECT count(*) FROM cuenta_saldo")).scalar() == 2
    finally:
        db._reset_para_tests()


def test_la_0040_sigue_debajo_de_la_0041():
    import os
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(raiz, "migrations"))
    assert ScriptDirectory.from_config(cfg).get_revision("0041").down_revision == "0040"
