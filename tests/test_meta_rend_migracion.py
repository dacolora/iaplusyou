"""Migración 0035 (spec 2026-10-08 meta rendimiento §4; era la 0033 en la rama, la 0034 tras mezclar main, que
trajo 0033_cobros, y la 0035 tras la segunda mezcla, que trajo 0034_tw_tarjetas): las seis tablas existen con sus
restricciones únicas, y el downgrade las borra sin tocar las de Cobros ni las de las tarjetas de Triple Whale."""
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
    eng = _alembic(tmp_path, "downgrade", "0034")
    nombres = set(sa.inspect(eng).get_table_names())
    assert not set(TABLAS) & nombres
    assert "cuenta_saldo" in nombres   # la 0033 (Cobros) sigue en pie
    assert {"tw_creativo", "tw_analisis"} <= nombres   # y la 0034 (tarjetas de Triple Whale) también


def test_db_crear_todo_coincide(base_temporal):
    nombres = set(sa.inspect(base_temporal.engine()).get_table_names())
    assert set(TABLAS) <= nombres
