"""Migración 0041 (sumas precalculadas de Rendimiento, 2026-10-15): crea `tw_memo` vacía, con las columnas del modelo
de `db.py`, y la bajada la quita sin tocar las copias de Triple Whale."""
import os

import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg


def test_migracion_0041_crea_tw_memo_como_el_modelo_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig41.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), "0040")
        command.upgrade(_cfg(), "0041")
        with db.conectar() as con:
            columnas = {c["name"] for c in sa.inspect(con).get_columns("tw_memo")}
            assert columnas == {c.name for c in db.tw_memo.columns}
            unicas = sa.inspect(con).get_unique_constraints("tw_memo")
            assert [sorted(u["column_names"]) for u in unicas] == [["clave", "cliente"]]
            assert con.execute(sa.text("SELECT count(*) FROM tw_memo")).scalar() == 0
        command.downgrade(_cfg(), "0040")
        with db.conectar() as con:
            assert "tw_memo" not in sa.inspect(con).get_table_names()
            assert "tw_anuncio_dia" in sa.inspect(con).get_table_names()
    finally:
        db._reset_para_tests()


def test_la_0041_es_la_unica_cabeza():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(raiz, "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0041"]
