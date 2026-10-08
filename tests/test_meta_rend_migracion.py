"""Migración 0033 (spec 2026-10-08 meta rendimiento §4): las seis tablas existen
con sus restricciones únicas, y el downgrade las borra."""
import os
import subprocess
import sys

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLAS = ("meta_cuenta", "meta_cuenta_dia", "meta_anuncio_dia", "meta_objeto", "meta_alcance", "tasa_cambio")


def _alembic(tmp_path, *args):
    env = dict(os.environ, CREATV_DB_URL=f"sqlite:///{tmp_path / 'm.db'}")
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=RAIZ, env=env, check=True,
                   capture_output=True, text=True)
    return sa.create_engine(env["CREATV_DB_URL"])


def test_upgrade_crea_las_tablas_y_downgrade_las_borra(tmp_path):
    eng = _alembic(tmp_path, "upgrade", "head")
    nombres = set(sa.inspect(eng).get_table_names())
    assert set(TABLAS) <= nombres
    uq = {u["name"] for u in sa.inspect(eng).get_unique_constraints("meta_anuncio_dia")}
    assert "uq_meta_anuncio_dia" in uq
    indices = {i["name"]: i for i in sa.inspect(eng).get_indexes("meta_cuenta")}
    assert indices["uq_meta_cuenta_act"]["unique"]
    eng.dispose()
    eng = _alembic(tmp_path, "downgrade", "0032")
    assert not set(TABLAS) & set(sa.inspect(eng).get_table_names())


def test_db_crear_todo_coincide(base_temporal):
    nombres = set(sa.inspect(base_temporal.engine()).get_table_names())
    assert set(TABLAS) <= nombres
