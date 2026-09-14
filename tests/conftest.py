import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


@pytest.fixture()
def base_temporal(monkeypatch):
    """Base SQLite nueva por test, en archivo (WAL necesita archivo, no :memory:)."""
    carpeta = tempfile.mkdtemp(prefix="creatv_test_")
    ruta = os.path.join(carpeta, "creatv.db")
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{ruta}")
    import db
    db._reset_para_tests()
    db.crear_todo()
    yield db
    db._reset_para_tests()
