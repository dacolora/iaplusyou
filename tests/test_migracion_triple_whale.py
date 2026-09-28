"""Migraciones 0023 y 0024 (spec 2026-09-28): tablas de Triple Whale, `triple_whale.extra` y ventas por producto.
(Eran 0022/0023 hasta que main tomó el 0022 para `familia.descripcion_en`.)"""
import os

import sqlalchemy as sa


def _config():
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Config(os.path.join(raiz, "alembic.ini"))


def test_migracion_0023_sube_conserva_la_conexion_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "0021")
    with db.engine().begin() as con:
        con.execute(sa.text("INSERT INTO triple_whale (cliente, creado_en, actualizado_en, dominio_tienda, "
                            "modelo_atribucion, ventana_atribucion) VALUES ('acme', 'x', 'x', 'acme.myshopify.com', "
                            "'First Touch', '7')"))
    command.upgrade(_config(), "head")
    insp = sa.inspect(db.engine())
    assert {"tw_anuncio_dia", "tw_tienda_dia", "tw_evaluacion"} <= set(insp.get_table_names())
    assert "extra" in {c["name"] for c in insp.get_columns("triple_whale")}
    assert "uq_tw_anuncio_dia" in {u["name"] for u in insp.get_unique_constraints("tw_anuncio_dia")}
    # La base migrada y la de los tests (db.crear_todo) tienen las mismas columnas.
    for tabla in ("tw_anuncio_dia", "tw_tienda_dia", "tw_evaluacion", "triple_whale"):
        assert {c["name"] for c in insp.get_columns(tabla)} == {c.name for c in db.metadata.tables[tabla].columns}
    import triple_whale_tiendas
    c = triple_whale_tiendas.obtener("acme")
    assert c["modelo_atribucion"] == "First Click" and c["ventana_atribucion"] == "7_days" and c["extra"] == {}
    command.downgrade(_config(), "0021")
    insp = sa.inspect(db.engine())
    assert "tw_anuncio_dia" not in insp.get_table_names()
    assert "extra" not in {c["name"] for c in insp.get_columns("triple_whale")}
    db._reset_para_tests()


def test_migracion_0024_crea_ventas_por_producto_y_baja(tmp_path, monkeypatch):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig23.db'}")
    db._reset_para_tests()
    command.upgrade(_config(), "head")
    insp = sa.inspect(db.engine())
    assert "tw_producto_dia" in insp.get_table_names()
    assert {c["name"] for c in insp.get_columns("tw_producto_dia")} == {c.name for c in db.metadata.tables["tw_producto_dia"].columns}
    assert "uq_tw_producto_dia" in {u["name"] for u in insp.get_unique_constraints("tw_producto_dia")}
    command.downgrade(_config(), "0023")
    assert "tw_producto_dia" not in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()
