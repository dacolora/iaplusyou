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


# ---------------------------------------------------------------- E2: migración 0036 (spec E2 §4) ---

TABLAS_E2 = ("meta_desglose", "meta_evaluacion")


def test_una_sola_cabeza_de_alembic_y_es_la_0036():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0036"]


def test_0036_arriba_abajo_arriba(tmp_path):
    eng = _alembic(tmp_path, "upgrade", "head")
    insp = sa.inspect(eng)
    assert set(TABLAS_E2) <= set(insp.get_table_names())
    uq = {u["name"]: u for u in insp.get_unique_constraints("meta_desglose")}
    assert uq["uq_meta_desglose"]["column_names"] == ["cliente", "ad_account_id", "ventana", "dimension", "clave"]
    ix = {i["name"]: i for i in insp.get_indexes("meta_evaluacion")}
    assert ix["ix_meta_evaluacion_cliente_creado"]["column_names"] == ["cliente", "creado_en"]
    eng.dispose()

    # Abajo: las dos tablas de E2 se van; las seis de E1 (0035) y la 0034 siguen.
    eng = _alembic(tmp_path, "downgrade", "0035")
    nombres = set(sa.inspect(eng).get_table_names())
    assert not set(TABLAS_E2) & nombres
    assert set(TABLAS) <= nombres
    eng.dispose()

    # Arriba otra vez: vuelven (la migración se puede repetir).
    eng = _alembic(tmp_path, "upgrade", "head")
    assert set(TABLAS_E2) <= set(sa.inspect(eng).get_table_names())
    eng.dispose()


def test_0036_coincide_con_db_py(tmp_path, base_temporal):
    """Las columnas de la base migrada son las de `db.py` (lo que usan las pruebas): sin deriva entre los dos."""
    eng = _alembic(tmp_path, "upgrade", "head")
    real, modelo = sa.inspect(eng), sa.inspect(base_temporal.engine())
    for tabla in TABLAS_E2:
        assert {c["name"] for c in real.get_columns(tabla)} == {c["name"] for c in modelo.get_columns(tabla)}
    eng.dispose()
