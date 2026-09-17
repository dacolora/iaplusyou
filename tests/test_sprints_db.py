import sqlalchemy as sa


def test_tablas_de_sprints_existen(base_temporal):
    db = base_temporal
    nombres = set(sa.inspect(db.engine()).get_table_names())
    assert {"persona", "temporada", "sprint", "campana", "referencia", "campana_pieza", "sprint_evento"} <= nombres


def _sprint_basico(db):
    ahora = db.ahora()
    with db.conectar() as con:
        pid = con.execute(db.persona.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                     nombre="Premium", origen="manual")).inserted_primary_key[0]
        tid = con.execute(db.temporada.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                       nombre="Verano", inicio="2026-06-01", fin="2026-07-15", tipo="propia")).inserted_primary_key[0]
        sid = con.execute(db.sprint.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                    nombre="Octubre", inicio="2026-10-01", fin="2026-10-31", estado="planeando")).inserted_primary_key[0]
    return pid, tid, sid


def test_campana_unica_por_combinacion(base_temporal):
    db = base_temporal
    pid, tid, sid = _sprint_basico(db)
    ahora = db.ahora()
    fila = dict(cliente="acme", creado_en=ahora, actualizado_en=ahora, sprint_id=sid, persona_id=pid,
                catalogo_id="espejo_led", temporada_id=tid, n_videos=10, n_imagenes=5, estado="planeada")
    with db.conectar() as con:
        con.execute(db.campana.insert().values(**fila))
    import pytest
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(db.campana.insert().values(**fila))
    # Misma persona y producto en OTRA temporada sí entra.
    with db.conectar() as con:
        tid2 = con.execute(db.temporada.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                        nombre="Navidad", inicio="2026-11-15", fin="2026-12-31", tipo="comercial")).inserted_primary_key[0]
        con.execute(db.campana.insert().values(**dict(fila, temporada_id=tid2)))


def test_migracion_0006_crea_las_tablas(tmp_path, monkeypatch):
    """La migración real (no metadata.create_all) deja las mismas tablas."""
    import os
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    nombres = set(sa.inspect(db.engine()).get_table_names())
    assert {"persona", "temporada", "sprint", "campana", "referencia", "campana_pieza", "sprint_evento"} <= nombres
    indices = {i["name"] for i in sa.inspect(db.engine()).get_indexes("campana")} | \
              {u["name"] for u in sa.inspect(db.engine()).get_unique_constraints("campana")}
    assert "uq_campana_combinacion" in indices
    db._reset_para_tests()


def test_alembic_tiene_una_sola_cabeza():
    """Dos ramas que parten de la misma revisión (0005 bloque 5, 0006 sprints)
    dejan dos cabezas y `upgrade head` deja de ser inequívoco; 0007 las une.
    Si vuelve a pasar, este test lo dice antes que el despliegue."""
    import os
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    heads = ScriptDirectory.from_config(Config(os.path.join(raiz, "alembic.ini"))).get_heads()
    assert len(heads) == 1, heads


def test_migracion_0008_agrega_prioridad(tmp_path, monkeypatch):
    import os
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig8.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    cols = {c["name"] for c in sa.inspect(db.engine()).get_columns("tarea")}
    assert "prioridad" in cols
    db._reset_para_tests()
