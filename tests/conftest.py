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


@pytest.fixture(autouse=True)
def _sin_cache_meta():
    """Los cachés por proceso de meta_conexion (estado y Pixel) no deben
    filtrarse entre tests: un `error` cacheado para "acme" en una suite
    cambiaría la atribución sugerida en la siguiente. Solo si el módulo ya
    está importado (no se fuerza el import de requests en tests que no lo
    necesitan)."""
    def limpiar():
        mod = sys.modules.get("meta_conexion")
        if mod is not None:
            mod._cache_pixel.clear()
            mod._cache_estado.clear()
        # El tablero cacheado (dashboard, 60 s por proyecto) tampoco: cada
        # test trae su base y la clave (ids, cuentas) se repite entre bases.
        dash = sys.modules.get("dashboard")
        if dash is not None and hasattr(dash, "invalidar_tablero"):
            dash.invalidar_tablero()
    limpiar()
    yield
    limpiar()
