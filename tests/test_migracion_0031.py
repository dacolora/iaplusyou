"""PND-040: conservar identidad y filas al habilitar AUTOINCREMENT."""
import sqlalchemy as sa
from tests.test_migracion_0029 import _cfg
from tests.test_voces_propias import _voz


def _ddl_material(con):
    return con.execute(sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name='material'")).scalar()


def test_pnd040_migracion_conserva_datos_y_no_reutiliza(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv('CREATV_DB_URL', f"sqlite:///{tmp_path / 'mig31.db'}")
    db._reset_para_tests()
    try:
        command.upgrade(_cfg(), '0030')
        vieja = _voz(voice_id='vieja')
        with db.conectar() as con:
            assert 'AUTOINCREMENT' not in _ddl_material(con).upper()
        command.upgrade(_cfg(), '0031')
        with db.conectar() as con:
            assert 'AUTOINCREMENT' in _ddl_material(con).upper()
            fila = dict(con.execute(sa.select(db.material)).first()._mapping)
            assert fila['id'] == vieja['id'] and fila['extra'] == vieja['extra']
            con.execute(db.material.delete())
        nueva = _voz(voice_id='nueva')
        assert nueva['id'] > vieja['id']
        command.downgrade(_cfg(), '0030')
        with db.conectar() as con:
            # la bajada de verdad quita AUTOINCREMENT (no basta con conservar las filas)
            assert 'AUTOINCREMENT' not in _ddl_material(con).upper()
            assert con.execute(sa.select(db.material.c.id)).scalar() == nueva['id']
    finally:
        db._reset_para_tests()
