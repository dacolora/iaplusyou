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


def test_migracion_0021_conserva_el_funnel_y_la_fk_de_referencia(tmp_path, monkeypatch):
    """F10 (ronda final): `batch_alter_table` recrea la tabla completa en
    SQLite (agrega columnas + quita el UNIQUE) -- hay que probar que ese
    recreado no pierde una columna ya existente con su VALOR (`funnel`, de la
    migración 0014) ni rompe la FK de `referencia` hacia `campana`."""
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
        con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, "
                            "catalogo_id, n_videos, n_imagenes, estado, funnel) "
                            "VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada', 'mof')"))
        con.execute(sa.text("INSERT INTO referencia (cliente, creado_en, actualizado_en, campana_id, tipo, url, "
                            "origen, estado) VALUES ('acme', 'x', 'x', 1, 'imagen', 'https://r2/x.jpg', 'archivo', "
                            "'borrador')"))
    command.upgrade(_config(), "head")
    with db.engine().begin() as con:
        assert con.execute(sa.text("SELECT funnel FROM campana WHERE id = 1")).scalar() == "mof"
        assert con.execute(sa.text("SELECT campana_id FROM referencia WHERE id = 1")).scalar() == 1
        problemas = con.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
    assert problemas == []
    db._reset_para_tests()


def test_migracion_0021_downgrade_no_choca_con_repetidas_sin_temporada(tmp_path, monkeypatch):
    """F10 (ronda final): el docstring decía que el downgrade «falla si ya hay
    campañas repetidas», pero SQL nunca choca dos NULL en un UNIQUE -- dos
    campañas repetidas SIN temporada (posible desde la 0020) pasan el
    downgrade sin aviso, silenciosamente."""
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "head")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO persona (cliente, creado_en, actualizado_en, nombre, origen, archivada) "
                            "VALUES ('acme', 'x', 'x', 'Premium', 'manual', 0)"))
        con.execute(sa.text("INSERT INTO sprint (cliente, creado_en, actualizado_en, nombre, inicio, fin, estado) "
                            "VALUES ('acme', 'x', 'x', 'Octubre', '2026-10-01', '2026-10-31', 'planeando')"))
        for _ in range(2):
            con.execute(sa.text("INSERT INTO campana (cliente, creado_en, actualizado_en, sprint_id, persona_id, "
                                "catalogo_id, n_videos, n_imagenes, estado) "
                                "VALUES ('acme', 'x', 'x', 1, 1, 'espejo_led', 2, 1, 'planeada')"))
    command.downgrade(_config(), "0020")   # sin temporada_id: NULL no choca con NULL -- no debe fallar
    with db.engine().begin() as con:
        total = con.execute(sa.text("SELECT COUNT(*) FROM campana")).scalar()
    assert total == 2
    db._reset_para_tests()
