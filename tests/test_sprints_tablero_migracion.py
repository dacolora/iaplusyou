"""Migración 0021 (tablero de Sprints, spec 2026-09-26): mercado, marcas y
momento en el sprint; enfoque en la campaña; sin la unicidad persona +
producto + temporada."""
import os

import sqlalchemy as sa


def _config():
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Config(os.path.join(raiz, "alembic.ini"))


def test_migracion_0021_agrega_columnas_y_quita_la_unicidad(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "head")
    insp = sa.inspect(db.engine())
    assert {"pais", "idioma", "marcas", "momento"} <= {c["name"] for c in insp.get_columns("sprint")}
    assert {"consciencia", "dolor", "familias", "pais", "idioma", "marcas"} <= {c["name"] for c in insp.get_columns("campana")}
    assert "uq_campana_combinacion" not in {u["name"] for u in insp.get_unique_constraints("campana")}
    assert {"sprint", "persona", "temporada", "producto"} <= {f["referred_table"] for f in insp.get_foreign_keys("campana")}
    db._reset_para_tests()


def test_migracion_0021_conserva_las_campanas_existentes(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "0020")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO persona (cliente, creado_en, actualizado_en, nombre, origen, archivada) "
                            "VALUES ('acme', 'x', 'x', 'Premium', 'manual', 0)"))
        con.execute(sa.text("INSERT INTO sprint (cliente, creado_en, actualizado_en, nombre, inicio, fin, estado) "
                            "VALUES ('acme', 'x', 'x', 'Octubre', '2026-10-01', '2026-10-31', 'planeando')"))
        con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, catalogo_id, "
                            "n_videos, n_imagenes, estado) VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada')"))
    command.upgrade(_config(), "head")
    with db.engine().begin() as con:
        fila = con.execute(sa.text("SELECT catalogo_id, n_videos, consciencia, familias, pais FROM campana")).one()
        # La misma combinación entra otra vez: ya no hay UNIQUE.
        con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, catalogo_id, "
                            "n_videos, n_imagenes, estado) VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada')"))
    assert tuple(fila) == ("espejo_led", 2, None, None, None)
    db._reset_para_tests()
