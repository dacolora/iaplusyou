# tests/test_migracion_0025.py
"""Migración 0025 (spec 2026-09-28 §8; nació como 0022 y se renumeró al
traer main, que ya tenía 0022–0024): las filas `producto` de colores
(`activo_catalogo_id` con `/`) pasan a ser del producto."""
import json
import os

import sqlalchemy as sa


def test_migracion_0025_reparte_las_filas_por_producto(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig25.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "0024")
    ahora = "2026-09-28T10:00:00"
    with db.engine().begin() as con:
        def fila(**kw):
            base = dict(ahora=ahora, cliente="hf", fuente="manual", precio=None, url=None, prioridad=0, en_prueba=0, extra="{}")
            base.update(kw)
            con.execute(sa.text(
                "INSERT INTO producto (cliente, creado_en, actualizado_en, fuente, fuente_id, nombre, precio, url_compra, "
                "activo_catalogo_id, prioridad, en_prueba, archivado, extra) VALUES (:cliente, :ahora, :ahora, :fuente, "
                ":fuente_id, :nombre, :precio, :url, :activo, :prioridad, :en_prueba, 0, :extra)"), base)
        fila(fuente_id="horiginal/beige", nombre="HOriginal — Beige", activo="horiginal/beige")   # 1: pasa a ser la del producto
        fila(fuente_id="horiginal/rose", nombre="HOriginal — Rose", activo="horiginal/rose")      # 2: vacía → se borra
        fila(fuente_id="horiginal/sky", nombre="HOriginal — Sky", activo="horiginal/sky",
             precio=34.95, extra=json.dumps({"pruebas": [{"id": "p1"}]}))                          # 3: con datos → archivada
        fila(fuente_id="cojin", nombre="Cojín", activo="cojin")                                    # 4: sin «/»: intacta
        fila(fuente="csv", fuente_id="777", nombre="Gorra", activo="gorra/roja")                   # 5: importada: solo el activo
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    with db.engine().connect() as con:
        filas = {r["id"]: dict(r) for r in con.execute(sa.text("SELECT * FROM producto ORDER BY id")).mappings()}
    assert set(filas) == {1, 3, 4, 5}
    assert filas[1]["activo_catalogo_id"] == "horiginal" and filas[1]["fuente_id"] == "horiginal" and not filas[1]["archivado"]
    assert filas[3]["activo_catalogo_id"] == "horiginal" and filas[3]["archivado"]
    assert json.loads(filas[3]["extra"])["archivado_por"] == "manual" and json.loads(filas[3]["extra"])["pruebas"]
    assert filas[4]["activo_catalogo_id"] == "cojin" and filas[4]["fuente_id"] == "cojin"
    assert filas[5]["activo_catalogo_id"] == "gorra" and filas[5]["fuente_id"] == "777" and not filas[5]["archivado"]
    db._reset_para_tests()
