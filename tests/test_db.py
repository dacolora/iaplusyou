import sqlalchemy as sa


def test_crea_todas_las_tablas(base_temporal):
    db = base_temporal
    nombres = set(sa.inspect(db.engine()).get_table_names())
    esperadas = {"producto", "concepto", "pieza", "experimento", "experimento_pieza",
                 "metrica_snapshot", "evento", "propuesta", "tarea", "tienda", "pedido", "kv"}
    assert esperadas <= nombres


def test_wal_activado(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        modo = con.execute(sa.text("PRAGMA journal_mode")).scalar()
    assert modo == "wal"


def test_conectar_hace_commit(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        con.execute(db.kv.insert().values(clave="a", valor="1", actualizado_en=db.ahora()))
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "a")).scalar()
    assert valor == "1"


def test_asegurar_carpeta_crea_el_directorio(monkeypatch):
    """migrations/env.py la llama antes de abrir su propio engine: en un
    checkout limpio data/ no existe y sqlite no crea carpetas."""
    import os
    import tempfile
    import db
    base = tempfile.mkdtemp(prefix="creatv_dir_")
    carpeta = os.path.join(base, "sub", "data")
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{os.path.join(carpeta, 'creatv.db')}")
    assert not os.path.isdir(carpeta)
    db.asegurar_carpeta()
    assert os.path.isdir(carpeta)
    db.asegurar_carpeta()  # idempotente


def test_asegurar_carpeta_ignora_memory(monkeypatch):
    import db
    monkeypatch.setenv("CREATV_DB_URL", "sqlite:///:memory:")
    db.asegurar_carpeta()  # no debe reventar
