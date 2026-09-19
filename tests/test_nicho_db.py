import os

import sqlalchemy as sa


def test_migracion_0011_crea_las_tablas(tmp_path, monkeypatch):
    """La migración real (no metadata.create_all) deja las tres tablas y la unicidad."""
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig11.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command.upgrade(Config(os.path.join(raiz, "alembic.ini")), "head")
    insp = sa.inspect(db.engine())
    assert {"estudio", "comentario", "avatar"} <= set(insp.get_table_names())
    unicos = {u["name"] for u in insp.get_unique_constraints("comentario")} | {i["name"] for i in insp.get_indexes("comentario")}
    assert "uq_comentario_fuente" in unicos
    cols = {c["name"] for c in insp.get_columns("avatar")}
    assert {"padre_id", "tipo", "base", "identidad", "soluciones_previas", "conciencia", "evidencia", "sin_evidencia",
            "persona_id", "generacion"} <= cols
    db._reset_para_tests()


def test_crear_todo_incluye_las_tablas(base_temporal):
    insp = sa.inspect(base_temporal.engine())
    assert {"estudio", "comentario", "avatar"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("estudio")} >= {"nombre", "producto", "catalogo_id", "tema", "idioma",
                                                                  "estado", "archivado", "generacion", "extra"}
