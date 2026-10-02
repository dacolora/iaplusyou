# tests/test_migracion_0028.py
"""Migración 0028 (Alertas, spec 2026-09-20-alertas-design.md §4 y §12): la
tabla `alerta_descartada`, con clave primaria (cliente, clave)."""
import os

import sqlalchemy as sa


def _cfg():
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Config(os.path.join(raiz, "alembic.ini"))


def test_migracion_0028_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig28.db'}")
    db._reset_para_tests()
    cfg = _cfg()
    command.upgrade(cfg, "head")
    insp = sa.inspect(db.engine())
    assert "alerta_descartada" in insp.get_table_names()
    cols = {c["name"]: c for c in insp.get_columns("alerta_descartada")}
    assert set(cols) == {"cliente", "clave", "huella", "descartada_en"}
    assert not any(c["nullable"] for c in cols.values())
    assert insp.get_pk_constraint("alerta_descartada")["constrained_columns"] == ["cliente", "clave"]
    db._reset_para_tests()
    command.downgrade(cfg, "0027")
    assert "alerta_descartada" not in sa.inspect(db.engine()).get_table_names()
    assert "error_app" in sa.inspect(db.engine()).get_table_names()      # solo bajó la 0028
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    assert "alerta_descartada" in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()


def test_la_tabla_de_la_migracion_coincide_con_la_declarada_en_db(tmp_path, monkeypatch):
    """Lo que crea alembic y lo que declara db.py (crear_todo en los tests) no se desalinean."""
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig28b.db'}")
    db._reset_para_tests()
    command.upgrade(_cfg(), "head")
    insp = sa.inspect(db.engine())
    migrada = {c["name"]: (c["type"].length, c["nullable"]) for c in insp.get_columns("alerta_descartada")}
    declarada = {c.name: (c.type.length, c.nullable) for c in db.alerta_descartada.columns}
    assert migrada == declarada
    assert [c.name for c in db.alerta_descartada.primary_key.columns] == ["cliente", "clave"]
    db._reset_para_tests()
