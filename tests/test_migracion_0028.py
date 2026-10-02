"""Migración 0028 (spec 2026-10-02 §3.1): metrica_dia y metrica_desglose suben,
bajan y db.py declara exactamente las mismas columnas e índices únicos."""
import os

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLS_DIA = {"id", "experimento_pieza_id", "fecha", "impresiones", "alcance", "frecuencia", "clics", "clics_enlace",
            "gasto", "cpm", "vistas_3s", "reproducciones", "p25", "p50", "p75", "p95", "p100", "thruplay",
            "tiempo_medio_s", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta", "ingresos_meta",
            "actualizado_en"}
COLS_DESGLOSE = {"id", "experimento_pieza_id", "dimension", "clave", "impresiones", "clics_enlace", "gasto",
                 "vistas_3s", "thruplay", "compras_meta", "ingresos_meta", "actualizado_en"}


def _cols(engine, tabla):
    return {c["name"] for c in sa.inspect(engine).get_columns(tabla)}


def _unicos(engine, tabla):
    insp = sa.inspect(engine)
    nombres = {u["name"] for u in insp.get_unique_constraints(tabla)}
    nombres |= {i["name"] for i in insp.get_indexes(tabla) if i.get("unique")}
    return nombres


def test_0028_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'm.db'}")
    db._reset_para_tests()
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    command.upgrade(cfg, "head")
    assert _cols(db.engine(), "metrica_dia") == COLS_DIA
    assert _cols(db.engine(), "metrica_desglose") == COLS_DESGLOSE
    assert "uq_metrica_dia_pieza_fecha" in _unicos(db.engine(), "metrica_dia")
    assert "uq_metrica_desglose_pieza_dim_clave" in _unicos(db.engine(), "metrica_desglose")
    db._reset_para_tests()
    command.downgrade(cfg, "0027")
    tablas = sa.inspect(db.engine()).get_table_names()
    assert "metrica_dia" not in tablas and "metrica_desglose" not in tablas
    db._reset_para_tests()


def test_db_py_declara_lo_mismo(base_temporal):
    db = base_temporal
    assert _cols(db.engine(), "metrica_dia") == COLS_DIA
    assert _cols(db.engine(), "metrica_desglose") == COLS_DESGLOSE
    assert "uq_metrica_dia_pieza_fecha" in _unicos(db.engine(), "metrica_dia")
    assert "uq_metrica_desglose_pieza_dim_clave" in _unicos(db.engine(), "metrica_desglose")
